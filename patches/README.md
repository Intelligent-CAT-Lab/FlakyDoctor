# Patches

File structures in the directory `patches`:
- `ID` includes all patches for ID tests.
- `OD` includes all patches for OD tests.
- Each patch path is constructed as:`[Unique SHA]/goodPatches/[Project Name]/[Project SHA]/[Module]/[Test Name]/[#Iteration].patch`.  
For example, patch `ID/037c363319e33ca2a03ee32123a10597adec88a8/goodPatches/light-4j/75ad2d415c51d7b6475f1d270a66949609b125d5/registry/com.networknt.registry.URLTest.testURL/2.patch` indicates:  
In round `037c363319e33ca2a03ee32123a10597adec88a8`, Test `com.networknt.registry.URLTest.testURL` from project `light-4j` (branch `75ad2d415c51d7b6475f1d270a66949609b125d5`) in module `registry` was successfully repaired in the `2nd` iteration.