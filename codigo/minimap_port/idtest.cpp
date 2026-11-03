#include <windows.h>
#include <cstdio>
#include "client_1_0_profile.h"

int wmain(int argc, wchar_t** argv)
{
    const std::filesystem::path exe = argv[1];
    using namespace MinimapClient10;
    const auto p = IdentifyFile(exe);
    std::printf("hash exato: %d\n", MatchesExactFile(exe, CurrentSha256) ? 1 : 0);
    std::printf("layout (assinaturas + call do Vulkan): %d\n", FileLayout::MatchesCurrentProfileLayout(exe) ? 1 : 0);
    std::printf("perfil: %s\n", p == Profile::Build26082781 ? "atual (porta nova)" : p == Profile::Build25988036 ? "antigo" : "NAO SUPORTADO");
    std::printf("vulkan call=%llx alvo=%llx\n", (unsigned long long)VulkanStartupCallsiteRva(p), (unsigned long long)VulkanStartupInitializerRva(p));
    std::printf("Rva(0x2b29c0) camera=%llx\n", (unsigned long long)Rva(p, 0x2b29c0));
    return p == Profile::Build26082781 ? 0 : 1;
}
