# Nhận diện pipeline là một phần của chuỗi cung ứng phần mềm

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vì sao CI/CD pipeline là một mắt xích có quyền lực cao trong chuỗi cung ứng phần mềm.
- Mô tả các tài sản, tác nhân, ranh giới tin cậy và luồng dữ liệu trong quá trình từ mã nguồn đến production.
- Nhận diện các đường tấn công thường gặp qua mã nguồn, dependency, build script, plugin, runner, cache, artifact và credential.
- Phân biệt bảo mật mã ứng dụng với bảo mật quy trình tạo và phát hành ứng dụng.
- Áp dụng nguyên tắc least privilege, cô lập runner, bảo vệ secret và kiểm soát thay đổi pipeline.
- Thiết kế cách xác minh nguồn gốc và tính toàn vẹn của artifact trước khi triển khai.
- Xây dựng góc nhìn threat modeling để ưu tiên kiểm soát theo rủi ro của sản phẩm.

## 1. Chuỗi cung ứng phần mềm không kết thúc ở mã nguồn

Khi nói đến bảo mật phần mềm, đội ngũ thường nghĩ đến lỗi trong mã ứng dụng: injection, lỗi xác thực, phân quyền sai hoặc xử lý dữ liệu không an toàn. Những vấn đề này rất quan trọng, nhưng phần mềm đến tay người dùng còn đi qua nhiều thành phần khác.

Một phiên bản phần mềm thường được tạo ra qua chuỗi hoạt động:

1. Nhà phát triển viết và thay đổi mã nguồn.
2. Git lưu lịch sử và tiếp nhận pull request.
3. CI pipeline kiểm tra mã, tải dependency và chạy build script.
4. Build tool, compiler, plugin và runner tạo artifact.
5. Artifact được lưu trong registry hoặc kho phân phối.
6. Release pipeline chọn artifact và triển khai lên môi trường.
7. Hệ thống vận hành xác minh phiên bản, theo dõi và cập nhật.

Tất cả thành phần, con người, quy trình và dịch vụ tham gia vào việc tạo, kiểm tra, đóng gói, phân phối và triển khai phần mềm tạo thành **software supply chain (chuỗi cung ứng phần mềm)**.

CI/CD pipeline nằm ở vị trí đặc biệt trong chuỗi này. Nó tiếp nhận mã nguồn và dependency, thực thi mã build, có thể đọc credential, tạo artifact được tin cậy và có quyền thay đổi môi trường. Nếu pipeline bị chiếm quyền, kẻ tấn công có thể làm phần mềm bị thay đổi trước khi đến người dùng mà không cần khai thác trực tiếp ứng dụng đang chạy.

Vì vậy, bảo mật pipeline là một phần của bảo mật chuỗi cung ứng phần mềm. Một pipeline xanh không tự động có nghĩa artifact an toàn. Cần biết pipeline đã chạy mã nào, trong môi trường nào, dùng dependency nào, với quyền gì và tạo ra artifact nào.

## 2. Pipeline là một thành phần có quyền lực cao

Pipeline thường được cấp nhiều quyền hơn một tiến trình ứng dụng thông thường:

- Đọc repository và các nhánh mã nguồn.
- Tải package hoặc image từ registry.
- Truy cập signing key hoặc credential để publish artifact.
- Đọc secret của môi trường.
- Đẩy image, package hoặc release lên kho phân phối.
- Triển khai lên cluster hoặc máy chủ.
- Thay đổi cấu hình, hạ tầng hoặc feature flag.

Một workflow có thể vừa thực thi mã do pull request cung cấp, vừa giữ token có quyền ghi vào repository hoặc credential production. Khi hai điều kiện này xuất hiện cùng nhau, mã không đáng tin cậy có thể tận dụng quyền của pipeline.

Hãy xem pipeline như một **control plane** của hoạt động giao phần mềm. Nó quyết định mã nào được kiểm tra, artifact nào được tạo, ai được phép phát hành và môi trường nào bị thay đổi.

Điều này tạo ra hai yêu cầu:

- Bảo vệ pipeline khỏi việc bị thay đổi hoặc thực thi trái phép.
- Giới hạn tác động nếu một job, plugin, dependency hoặc runner bị xâm nhập.

Không nên giả định pipeline an toàn chỉ vì nó chạy trong dịch vụ CI được quản lý. Dịch vụ có thể bảo vệ nền tảng, nhưng cấu hình workflow, action/plugin, script, dependency, quyền token và cách dùng secret vẫn thuộc trách nhiệm của đội ngũ.

## 3. Nhìn toàn bộ chuỗi cung ứng như một đồ thị tin cậy

Một cách hữu ích để hiểu pipeline security là vẽ các thành phần và mối quan hệ tin cậy giữa chúng.

~~~mermaid
flowchart LR
    A["Developer / Reviewer"] --> B["Source repository"]
    B --> C["CI workflow"]
    C --> D["Runner / Build environment"]
    D --> E["Build tools, plugins, dependencies"]
    E --> D
    D --> F["Artifact + test evidence"]
    F --> G["Artifact registry"]
    G --> H["Release / Deployment pipeline"]
    H --> I["Target environment"]
    I --> J["Running service"]
    C --> K["Secrets / identity provider"]
    H --> K
    K --> H
~~~

Sơ đồ cho thấy artifact không tự nhiên trở nên đáng tin chỉ vì nó nằm trong registry. Độ tin cậy phụ thuộc vào toàn bộ đường đi:

- Mã nguồn có được review và bảo vệ không?
- Workflow có được kiểm soát thay đổi không?
- Runner có sạch và cô lập không?
- Dependency có đến từ nguồn tin cậy không?
- Build tool và plugin có được quản lý phiên bản không?
- Artifact có được gắn với commit và bằng chứng build không?
- Registry có bảo vệ quyền ghi và tính bất biến không?
- Deployment pipeline có xác minh artifact trước khi triển khai không?

Nếu một mắt xích có thể bị thay đổi âm thầm, bằng chứng ở các mắt xích khác có thể mất giá trị.

## 4. Tài sản cần bảo vệ trong pipeline

Threat modeling bắt đầu bằng việc xác định tài sản. Không chỉ artifact production mới có giá trị; nhiều dữ liệu và quyền trong pipeline có thể giúp kẻ tấn công chiếm quyền sâu hơn.

| Tài sản | Ví dụ | Tác động nếu bị xâm phạm |
|---|---|---|
| Source code | Repository, branch, tag | Chèn mã độc hoặc sửa logic |
| Pipeline definition | Workflow YAML, build script | Thay đổi điều kiện kiểm tra hoặc hành vi phát hành |
| Build environment | Runner, container, workspace | Can thiệp mã hoặc artifact trong lúc build |
| Credentials | Token, SSH key, cloud credential | Đọc dữ liệu hoặc thực hiện hành động trái phép |
| Dependency | Package, plugin, action, base image | Đưa mã độc vào quá trình build hoặc runtime |
| Cache | Dependency cache, build cache | Đầu độc dữ liệu được tái sử dụng |
| Artifact | JAR, image, package, binary | Phát hành phần mềm bị thay đổi |
| Provenance/evidence | Build metadata, test report, attestation | Làm sai lệch bằng chứng về nguồn gốc |
| Registry | Package/image repository | Thay thế, xóa hoặc phát tán artifact |
| Deployment identity | Service account, workload identity | Thay đổi môi trường đích |
| Audit log | Run history, approval, deployment record | Che giấu hoặc gây khó điều tra |

Cần xác định tài sản nào là bí mật, tài sản nào cần tính toàn vẹn và tài sản nào cần tính sẵn sàng. Ví dụ token cần tính bí mật và khả năng thu hồi; artifact cần tính toàn vẹn; log cần tính toàn vẹn và khả năng truy cập khi điều tra.

## 5. Xác định tác nhân và ranh giới tin cậy

Một pipeline có thể nhận đầu vào từ nhiều nguồn với mức độ tin cậy khác nhau.

Các tác nhân thường gặp:

- Developer nội bộ.
- Contributor từ fork hoặc repository bên ngoài.
- Reviewer và maintainer.
- Tài khoản bot hoặc automation.
- Nhà cung cấp CI/CD.
- Nhà cung cấp package, plugin hoặc action.
- Người vận hành production.
- Kẻ tấn công đã chiếm tài khoản, dependency hoặc runner.

Không phải mọi thay đổi đều có cùng mức tin cậy. Một pull request từ fork có thể chứa mã và workflow không đáng tin. Một branch đã được bảo vệ và merge sau review có mức tin cậy cao hơn, nhưng vẫn cần kiểm tra. Một package tải từ public registry cũng cần được xem là đầu vào bên ngoài.

Các ranh giới tin cậy cần nhận diện:

1. Từ máy nhà phát triển đến repository.
2. Từ pull request bên ngoài đến CI runner.
3. Từ workflow definition đến runner có quyền thực thi.
4. Từ runner đến package registry và dịch vụ bên ngoài.
5. Từ build job đến artifact registry.
6. Từ artifact registry đến release pipeline.
7. Từ deployment identity đến môi trường đích.
8. Từ hệ thống CI đến secret manager hoặc cloud identity provider.

Tại mỗi ranh giới, cần hỏi: dữ liệu nào đi qua, ai kiểm soát nó, nó có thể bị sửa không và quyền nào được sử dụng?

## 6. Những đường tấn công phổ biến

### 6.1. Sửa workflow hoặc build script

Kẻ tấn công có thể thay đổi workflow để bỏ qua test, chạy lệnh tải mã ngoài, xuất secret ra ngoài hoặc publish artifact khác với dự kiến.

Điều kiện hỗ trợ tấn công có thể là branch protection yếu, thiếu review bắt buộc hoặc pipeline production được chạy từ branch không được kiểm soát.

Kiểm soát phù hợp:

- Bảo vệ branch và file workflow nhạy cảm.
- Yêu cầu review từ owner của pipeline hoặc platform team.
- Giới hạn quyền của workflow.
- Kiểm tra thay đổi workflow như thay đổi mã có ảnh hưởng bảo mật.
- Tách quyền build thông thường khỏi quyền release production.

### 6.2. Thực thi mã không đáng tin từ pull request

Build và test thường thực thi mã do pull request cung cấp. Mã đó có thể chạy script, plugin, test helper hoặc dependency có hành vi tùy ý trong runner.

Nếu job có secret hoặc token quyền cao, mã không đáng tin có thể tìm cách đọc hoặc gửi chúng ra ngoài.

Kiểm soát phù hợp:

- Không cấp secret nhạy cảm cho job chạy mã từ fork hoặc nguồn không tin cậy.
- Dùng token chỉ đọc cho các job kiểm tra pull request.
- Chạy job trên runner dùng một lần hoặc được cô lập.
- Tách workflow kiểm tra mã bên ngoài khỏi workflow phát hành có quyền cao.
- Chỉ cấp quyền ghi và credential phát hành sau khi thay đổi đã qua điều kiện tin cậy.

### 6.3. Dependency hoặc plugin bị xâm phạm

Ứng dụng có thể tải package, plugin, action hoặc base image từ bên ngoài. Nếu một thành phần bị chiếm quyền hoặc bị thay thế, mã độc có thể chạy trong lúc build.

Rủi ro bao gồm package giả mạo tên, dependency confusion, maintainer account bị chiếm, release bị cài mã độc và plugin có quyền quá rộng.

Kiểm soát phù hợp:

- Quản lý phiên bản dependency và plugin.
- Dùng registry/repository được tin cậy và quy tắc namespace rõ ràng.
- Kiểm tra checksum, chữ ký hoặc verification metadata khi hệ sinh thái hỗ trợ.
- Quét dependency và image.
- Review thay đổi dependency nhạy cảm.
- Hạn chế quyền mạng và secret của build job.

### 6.4. Runner bị chiếm quyền hoặc giữ trạng thái cũ

Runner tự quản lý có thể giữ workspace, process, credential hoặc file từ lần chạy trước. Nếu nhiều job không cùng mức tin cậy dùng chung máy, job sau có thể đọc hoặc thay đổi dữ liệu còn sót.

Một runner bị xâm nhập cũng có thể sửa artifact sau build, đánh cắp token hoặc can thiệp các job tiếp theo.

Kiểm soát phù hợp:

- Ưu tiên runner ephemeral hoặc workspace sạch cho job nhạy cảm.
- Cô lập job theo repository, branch và mức tin cậy.
- Xóa credential và dữ liệu tạm sau khi job kết thúc.
- Cập nhật runner image và giới hạn quyền hệ điều hành.
- Không chạy job không tin cậy trên máy có quyền truy cập production.
- Giám sát hành vi và vòng đời runner.

### 6.5. Cache poisoning

Cache có thể được dùng lại giữa nhiều lần chạy để tăng tốc. Nếu job không đáng tin có quyền ghi cache mà job phát hành đáng tin sau đó sử dụng, dữ liệu độc hại có thể được tái sử dụng.

Kiểm soát phù hợp:

- Phân vùng cache theo repository, branch hoặc trust level.
- Không để job từ fork ghi vào cache được release job tin cậy sử dụng.
- Dùng cache key gắn với lockfile, toolchain và cấu hình.
- Có quy trình xóa hoặc làm mới cache khi nghi ngờ bị đầu độc.
- Không coi cache là nguồn chuẩn của artifact phát hành.

### 6.6. Thay thế artifact hoặc làm giả bằng chứng

Nếu registry cho phép ghi đè tag hoặc deployment pipeline chỉ kiểm tra tên tag, artifact có thể bị thay đổi sau khi test. Báo cáo test cũng có thể không còn gắn với nội dung được deploy.

Kiểm soát phù hợp:

- Dùng digest hoặc định danh bất biến.
- Bảo vệ quyền ghi registry.
- Gắn artifact với commit và build run.
- Lưu provenance và test evidence.
- Xác minh chữ ký hoặc attestation theo policy trước deploy.
- Promote cùng artifact đã được kiểm thử qua các môi trường.

## 7. Bí mật và danh tính là điểm trọng yếu

Pipeline thường cần credential để publish package, ký artifact, truy cập cloud hoặc triển khai. Nếu dùng một token quản trị chung cho nhiều job, một bước bị xâm nhập có thể gây ảnh hưởng rộng.

### 7.1. Least privilege

Mỗi job chỉ nên có quyền cần thiết cho nhiệm vụ:

- Job lint và unit test thường chỉ cần đọc mã nguồn.
- Job publish cần quyền ghi vào đúng repository artifact.
- Job deploy staging cần quyền vào staging.
- Job deploy production cần danh tính riêng và điều kiện bảo vệ bổ sung.
- Job tạo báo cáo không nên nhận quyền triển khai.

Không cấp quyền ghi repository, quyền quản trị cloud hoặc secret production cho toàn workflow nếu chỉ một bước cần dùng.

### 7.2. Credential ngắn hạn

Khi nền tảng hỗ trợ, ưu tiên workload identity hoặc OIDC để đổi identity của job lấy credential ngắn hạn. Cách này giảm nhu cầu lưu token dài hạn trong CI.

Credential cần bị giới hạn theo:

- Repository hoặc project.
- Workflow hoặc job.
- Branch hoặc tag được bảo vệ.
- Environment đích.
- Audience và thời hạn.
- Quyền cụ thể trên cloud hoặc registry.

Không chỉ dựa vào tên workflow do người dùng tự khai báo. Provider cần xác minh claim và điều kiện trust tương ứng.

### 7.3. Quản lý secret

Nếu phải dùng secret tĩnh:

- Lưu trong secret manager hoặc kho bí mật của nền tảng.
- Chỉ cấp cho job cần sử dụng.
- Không đưa vào command line hoặc output.
- Tránh in toàn bộ environment.
- Rotate và revoke khi có dấu hiệu lộ.
- Không cấp cho pull request từ fork hoặc nguồn không tin cậy.
- Kiểm tra cả log, artifact và cache có thể chứa dữ liệu nhạy cảm.

Secret masking chỉ là lớp hỗ trợ. Không được xem nó là bảo đảm rằng mọi giá trị bí mật sẽ tự động bị che trong mọi dạng log.

## 8. Bảo vệ pipeline definition và quy trình review

Pipeline as code giúp cấu hình được review, version và audit, nhưng cũng khiến workflow trở thành mã có thể thực thi với quyền của CI.

Một thay đổi nhỏ trong workflow có thể:

- Bỏ qua test bắt buộc.
- Thêm action bên ngoài.
- Thay đổi branch filter.
- Cấp quyền ghi cho token.
- Đưa secret vào job mới.
- Thay đổi nơi artifact được publish.
- Chạy deploy trên sự kiện không phù hợp.

Vì vậy:

- Dùng branch protection cho nhánh chính và nhánh release.
- Yêu cầu review của owner đối với workflow, build script và policy nhạy cảm.
- Giới hạn quyền mặc định của token.
- Pin action hoặc plugin quan trọng bằng revision bất biến khi nền tảng hỗ trợ.
- Review thay đổi version của action, runner image và build tool.
- Không để contributor không tin cậy tự thay đổi policy phát hành.
- Ghi lại workflow revision đã tạo ra artifact.

Một file workflow được review không đồng nghĩa mọi script nó gọi đều an toàn. Cần xem các script, plugin, dependency và action thực tế được thực thi.

## 9. Cô lập job và runner theo mức độ tin cậy

Cô lập là cách giảm tác động nếu một bước build bị xâm phạm.

Một mô hình đơn giản:

| Loại job | Nguồn mã | Quyền gợi ý | Runner gợi ý |
|---|---|---|---|
| Pull request validation | Có thể từ fork | Chỉ đọc, không có production secret | Ephemeral, cô lập |
| Build trên protected branch | Mã đã qua review | Đọc dependency, publish artifact nếu cần | Ephemeral hoặc nhóm runner tin cậy |
| Security scan | Source/artifact cụ thể | Đọc artifact và metadata | Runner giới hạn mạng/quyền |
| Release | Artifact đã được xác minh | Quyền release có kiểm soát | Runner tin cậy, ephemeral nếu có |
| Production deploy | Artifact và snapshot được duyệt | Quyền đúng một môi trường | Runner và identity riêng |

Không nên để job pull request không tin cậy chạy trên runner persistent có quyền truy cập vào máy chủ, registry hoặc secret của tổ chức.

Nếu dùng self-hosted runner, cần xác định:

- Runner có được tái sử dụng giữa repository hoặc tenant không?
- Workspace có được dọn sau mỗi job không?
- Process nền có thể tồn tại sau khi job kết thúc không?
- Job có quyền truy cập metadata service hoặc network nội bộ không?
- Ai được phép đăng ký runner mới hoặc thay đổi runner labels?
- Runner image được cập nhật và xác minh ra sao?

Cô lập runner không chỉ là tạo container. Container có thể vẫn chia sẻ kernel, network hoặc credential của host. Mức cô lập cần tương xứng với mức độ không tin cậy của workload.

## 10. Dependency, action và build tool là đầu vào của chuỗi cung ứng

Pipeline không chỉ build mã của dự án. Nó còn thực thi nhiều thành phần bên ngoài:

- Package từ Maven, Gradle, npm, PyPI hoặc registry khác.
- Plugin của build tool.
- CI action, reusable workflow hoặc extension.
- Base image và toolchain.
- Script cài đặt và công cụ tải trong lúc build.

Mỗi thành phần có thể chạy mã hoặc ảnh hưởng đến nội dung artifact.

Một chính sách dependency cơ bản nên gồm:

1. Xác định nguồn package và namespace tin cậy.
2. Pin phiên bản dependency, plugin và action quan trọng.
3. Dùng lockfile hoặc dependency locking khi hệ sinh thái hỗ trợ.
4. Kiểm tra checksum/chữ ký hoặc dependency verification.
5. Quét lỗ hổng và theo dõi trạng thái hỗ trợ.
6. Review thay đổi package có quyền hoặc phạm vi lớn.
7. Giới hạn network egress của job khi có thể.
8. Lưu danh sách thành phần trong artifact nếu yêu cầu.

Pin theo tag có thể giảm bất ngờ nhưng tag vẫn có thể thay đổi ở một số hệ thống. Với action hoặc image có khả năng thay đổi, dùng commit SHA hoặc digest bất biến theo cơ chế nền tảng hỗ trợ và có quy trình cập nhật được review.

## 11. Artifact cần có nguồn gốc và tính toàn vẹn

Artifact là đầu ra được kiểm thử và đưa đến môi trường. Cần đảm bảo artifact được triển khai chính là artifact đã được tạo và kiểm tra.

Một luồng đáng tin cậy cần liên kết:

- Source repository và commit.
- Workflow revision và run ID.
- Build tool, compiler và dependency graph.
- Test, scan và policy results.
- Artifact digest.
- SBOM hoặc inventory thành phần khi cần.
- Provenance hoặc attestation về cách artifact được tạo.
- Chữ ký nếu chính sách yêu cầu.

**Provenance** là thông tin mô tả nguồn và quá trình tạo artifact, chẳng hạn mã nguồn, builder, workflow và tham số build. **Attestation** là một tuyên bố có cấu trúc về một đối tượng hoặc quy trình, thường được xác thực bằng chữ ký hoặc cơ chế tin cậy tương ứng.

**SBOM (Software Bill of Materials)** là danh sách thành phần phần mềm có trong một artifact hoặc sản phẩm. SBOM giúp kiểm tra thành phần và đánh giá ảnh hưởng khi có lỗ hổng mới.

Các khái niệm này bổ sung cho nhau:

- Digest nhận diện nội dung artifact.
- Signature giúp xác minh nguồn ký và tính toàn vẹn.
- Provenance mô tả cách artifact được tạo.
- SBOM mô tả các thành phần có trong artifact.
- Test evidence cho biết những kiểm tra nào đã chạy và kết quả.

Không nên coi việc có SBOM hoặc chữ ký là bằng chứng tuyệt đối rằng phần mềm an toàn. Cần xác minh nguồn tạo, policy, phạm vi kiểm tra và tính hợp lệ của bằng chứng.

## 12. Xác minh trước khi triển khai

Release pipeline cần kiểm tra artifact và bằng chứng trước khi có quyền tác động đến môi trường.

Các câu hỏi cần xác minh:

- Artifact digest có đúng với yêu cầu phát hành không?
- Artifact có đến từ registry được tin cậy không?
- Commit và repository có nằm trong nguồn được phép không?
- Provenance có chỉ ra builder/workflow được chấp nhận không?
- Chữ ký có hợp lệ và signer có được tin cậy không?
- Test và scan evidence có gắn với đúng digest hoặc commit không?
- Artifact có bị thu hồi hoặc có cảnh báo mới không?
- Approval có gắn với đúng artifact, cấu hình và môi trường không?

Nếu một bằng chứng bắt buộc không có hoặc không thể xác minh, pipeline cần dừng theo policy. Không nên coi một tag có tên release hoặc trạng thái workflow xanh là đủ để triển khai.

Nguyên tắc **build once, promote the same artifact** giúp giảm nguy cơ staging kiểm thử một gói nhưng production nhận một gói khác. Cấu hình môi trường có thể khác, nhưng artifact cần được định danh và giữ nguyên qua các bước promote.

## 13. Bảo vệ cache và dữ liệu trung gian

Cache, workspace, log và file tạm cũng là một phần của chuỗi cung ứng.

Rủi ro có thể gồm:

- Cache bị ghi bởi job không tin cậy.
- Job sau đọc file hoặc credential còn sót.
- Artifact tạm chứa secret hoặc dữ liệu nhạy cảm.
- Log lưu command có token.
- Báo cáo scan chứa đường dẫn nội bộ hoặc thông tin không nên công khai.
- Workspace bị thay đổi sau khi artifact được kiểm tra.

Biện pháp cơ bản:

- Phân vùng cache theo trust boundary.
- Dùng cache key gắn với lockfile và toolchain.
- Không lưu secret vào cache.
- Dọn workspace và credential sau job.
- Giới hạn thời gian lưu log và artifact trung gian.
- Phân quyền đọc báo cáo và log.
- Chỉ publish artifact từ bước có nguồn gốc rõ ràng.
- Xác minh digest trước khi sử dụng lại artifact.

Không dùng cache làm kho phát hành. Cache được tối ưu cho hiệu năng và có thể bị xóa hoặc tạo lại; artifact release cần kho lưu trữ, retention và kiểm soát quyền riêng.

## 14. Threat modeling cho một pipeline

Threat modeling giúp chuyển từ danh sách khuyến nghị chung sang kiểm soát dựa trên đường tấn công thực tế.

Có thể bắt đầu bằng năm câu hỏi:

1. **What are we protecting?** Tài sản nào quan trọng nhất: source, secret, artifact, registry hay production?
2. **Who can affect it?** Developer, contributor bên ngoài, maintainer, bot, nhà cung cấp hay kẻ tấn công?
3. **Where are the trust boundaries?** Đầu vào không tin cậy đi vào runner hoặc job có quyền ở đâu?
4. **What can go wrong?** Mã độc chạy trong build, secret bị lấy, artifact bị thay, bằng chứng bị giả hay deploy sai?
5. **How do we know and respond?** Có log, alert, revoke, rollback và quy trình điều tra nào?

Có thể dùng STRIDE để rà soát các nhóm đe dọa:

| Nhóm | Ví dụ trong CI/CD |
|---|---|
| Spoofing | Giả danh workflow, runner, publisher hoặc identity |
| Tampering | Sửa source, pipeline, cache, artifact hoặc deployment manifest |
| Repudiation | Không có audit để xác định ai thay đổi hoặc phát hành |
| Information disclosure | Lộ secret, token, log hoặc dữ liệu nội bộ |
| Denial of service | Làm cạn runner, quota hoặc registry |
| Elevation of privilege | Job pull request lấy được quyền ghi hoặc quyền production |

STRIDE là cách phân loại để đặt câu hỏi, không phải checklist chứng minh hệ thống đã an toàn. Mỗi phát hiện cần gắn với tài sản, điều kiện khai thác, tác động và kiểm soát cụ thể.

## 15. Ví dụ một kịch bản tấn công

Giả sử repository cho phép pull request từ fork. Workflow chạy unit test trên mọi pull request. Job được cấp token có quyền ghi repository và một secret dùng để publish package.

Một pull request độc hại có thể thay đổi test script hoặc build script để thực thi lệnh trong runner. Nếu job có quyền đọc secret, mã đó có thể tìm cách gửi token ra ngoài. Kẻ tấn công sau đó có thể dùng token để sửa release hoặc publish package không được phép.

Chuỗi nguyên nhân không nằm ở một lỗi duy nhất:

1. Mã không tin cậy được thực thi trong runner.
2. Job nhận secret không cần thiết.
3. Token có quyền rộng.
4. Runner hoặc network không được cô lập đủ.
5. Quy trình publish không tách khỏi kiểm tra pull request.
6. Artifact registry không yêu cầu xác minh nguồn phát hành.

Thiết kế an toàn hơn:

- Pull request từ fork chỉ chạy kiểm tra với quyền đọc và không có secret nhạy cảm.
- Runner dùng một lần, không chứa credential từ job trước.
- Workflow release chạy sau khi mã được chấp nhận vào nhánh được bảo vệ.
- Publish job nhận identity ngắn hạn chỉ có quyền ghi đúng repository.
- Artifact được gắn digest và provenance.
- Production deploy chỉ dùng artifact đã xác minh và được phê duyệt.

Bài học là phải kết hợp nhiều lớp kiểm soát. Chỉ che secret trong log không ngăn mã độc đọc secret trong process. Chỉ bảo vệ branch không ngăn dependency bị xâm phạm. Chỉ ký artifact không chứng minh artifact được build từ mã đúng nếu signer hoặc builder bị chiếm quyền.

## 16. Mô hình pipeline có ranh giới bảo mật rõ

Một pipeline có thể tách thành các vùng tin cậy:

~~~mermaid
flowchart TD
    A["Untrusted pull request"] --> B["Read-only validation job"]
    B --> C["Test results"]
    C --> D["Protected branch after review"]
    D --> E["Trusted build job"]
    E --> F["Artifact + provenance + SBOM"]
    F --> G["Protected artifact registry"]
    G --> H["Release verification"]
    H --> I{"Digest, signature, policy and evidence valid?"}
    I -- "No" --> X["Block release and alert"]
    I -- "Yes" --> J["Environment approval / policy"]
    J --> K["Deploy with scoped identity"]
    K --> L["Post-deploy verification"]
~~~

Một số đặc điểm của mô hình:

- Job xử lý mã không tin cậy không có quyền publish hoặc deploy.
- Build đáng tin cậy chạy trên nguồn đã qua điều kiện review.
- Artifact được tạo một lần và lưu trong registry được bảo vệ.
- Release pipeline xác minh digest và bằng chứng trước khi nhận quyền triển khai.
- Deployment identity chỉ có quyền trên môi trường cần thiết.
- Kết quả triển khai được xác minh và ghi nhận.

Trong thực tế, có thể có nhiều workflow và nhiều nền tảng. Ranh giới bảo mật cần được thể hiện bằng quyền, identity, runner, registry và policy chứ không chỉ bằng cách đặt tên stage.

## 17. Các kiểm soát nên triển khai theo thứ tự ưu tiên

Không phải tổ chức nào cũng có thể triển khai toàn bộ cơ chế nâng cao ngay lập tức. Có thể bắt đầu từ những kiểm soát giảm rủi ro lớn nhất.

| Ưu tiên | Kiểm soát | Mục tiêu |
|---|---|---|
| 1 | Bảo vệ branch và workflow nhạy cảm | Ngăn thay đổi pipeline trái phép |
| 2 | Token và quyền theo job | Giảm phạm vi tác động khi job bị xâm phạm |
| 3 | Không cấp secret cho mã không tin cậy | Ngăn exfiltration từ pull request |
| 4 | Runner sạch và cô lập | Giảm persistence và cross-job contamination |
| 5 | Pin và review dependency/action/plugin | Giảm rủi ro từ thành phần bên ngoài |
| 6 | Bảo vệ registry và dùng digest bất biến | Ngăn thay thế artifact |
| 7 | Provenance, SBOM và signature theo nhu cầu | Tăng khả năng truy vết và xác minh |
| 8 | Verify trước deploy | Chỉ triển khai artifact đáp ứng policy |
| 9 | Audit, alert và quy trình ứng phó | Phát hiện và xử lý sự cố |

Thứ tự này là gợi ý ưu tiên, không phải quy tắc cứng. Một tổ chức có yêu cầu tuân thủ hoặc rủi ro cao có thể cần provenance và ký artifact ngay từ đầu.

## 18. Kết nối với các khung thực hành chuỗi cung ứng

Một số khung và sáng kiến giúp tổ chức hệ thống hóa bảo mật chuỗi cung ứng:

- **SLSA (Supply-chain Levels for Software Artifacts):** cung cấp mô hình mức độ bảo đảm cho quy trình tạo artifact và provenance. Có thể dùng để đánh giá builder, build process và khả năng chống sửa đổi.
- **NIST SSDF:** đưa ra thực hành phát triển phần mềm an toàn trong toàn vòng đời, bao gồm bảo vệ môi trường phát triển và quy trình phát hành.
- **SBOM:** cung cấp inventory thành phần phần mềm để hỗ trợ quản lý lỗ hổng và trách nhiệm thành phần.
- **Sigstore và các cơ chế ký/attestation:** hỗ trợ ký và xác minh artifact hoặc bằng chứng theo mô hình tin cậy phù hợp.

Không nên chỉ gắn nhãn “đạt SLSA” hoặc “có SBOM” để kết luận pipeline an toàn. Cần xác định phiên bản khung, yêu cầu cụ thể, phạm vi áp dụng và bằng chứng thực tế. Các framework bổ trợ cho threat model và chính sách nội bộ, không thay thế việc hiểu kiến trúc pipeline của chính sản phẩm.

## 19. Chỉ số và bằng chứng để quan sát pipeline security

Bảo mật pipeline cần được vận hành liên tục. Có thể theo dõi:

| Chỉ số / bằng chứng | Điều cần quan sát |
|---|---|
| Workflow change review | Thay đổi pipeline có đúng reviewer và policy không |
| Token permission | Job nào đang có quyền ghi hoặc quyền production |
| Secret exposure | Job nào nhận secret, secret có bị đưa vào log/artifact không |
| Runner lifecycle | Runner có được tái tạo, cập nhật và dọn sau job không |
| Dependency status | Dependency, plugin và action có lỗ hổng hoặc phiên bản bị thu hồi không |
| Artifact provenance | Artifact có liên kết đến commit và builder tin cậy không |
| Signature verification | Release có xác minh signer và digest không |
| Registry audit | Ai publish, thay tag hoặc xóa artifact |
| Deployment evidence | Artifact nào, config revision nào và identity nào đã triển khai |
| Incident response | Thời gian revoke credential, chặn release và khôi phục |

Không nên chỉ đếm số lượng công cụ security scan. Cần biết cảnh báo nào được xử lý, quyền nào thực sự được dùng và có thể truy vết từ production về nguồn tạo artifact hay không.

## 20. Checklist nhận diện pipeline là một phần của chuỗi cung ứng

Khi đánh giá pipeline, hãy kiểm tra:

- [ ] Đã vẽ luồng từ source đến artifact registry và production.
- [ ] Đã xác định tài sản quan trọng và owner.
- [ ] Đã phân loại nguồn đầu vào theo mức độ tin cậy.
- [ ] Đã nhận diện trust boundary giữa pull request, runner, registry và deployment.
- [ ] Workflow và build script được bảo vệ bằng review và branch policy.
- [ ] Job xử lý mã không tin cậy không nhận secret hoặc quyền ghi không cần thiết.
- [ ] Token được giới hạn theo job và môi trường.
- [ ] Credential ngắn hạn hoặc workload identity được dùng khi phù hợp.
- [ ] Runner được cô lập, cập nhật và dọn trạng thái sau job.
- [ ] Dependency, plugin, action và base image có nguồn cùng phiên bản được kiểm soát.
- [ ] Cache được phân vùng theo trust level và không chứa secret.
- [ ] Artifact có digest bất biến và registry có kiểm soát quyền ghi.
- [ ] Provenance, SBOM hoặc signature được tạo theo yêu cầu.
- [ ] Release pipeline xác minh artifact và bằng chứng trước deploy.
- [ ] Deployment identity chỉ có quyền cần thiết.
- [ ] Log và audit trail hỗ trợ truy vết mà không lộ bí mật.
- [ ] Có quy trình revoke credential, chặn release và xử lý artifact bị nghi ngờ.

## 21. Bài tập tự đánh giá

Một nhóm phát triển có pipeline như sau:

- Mọi pull request đều chạy trên một self-hosted runner dùng chung.
- Job kiểm thử nhận token có quyền ghi repository để tải submodule riêng.
- Build tải dependency và action theo tag có thể thay đổi.
- Artifact được publish với tag latest.
- Release job triển khai latest lên production mà không kiểm tra digest hoặc provenance.
- Log lưu toàn bộ biến môi trường khi build thất bại.

Hãy phân tích:

1. Những tài sản nào đang có nguy cơ cao nhất?
2. Ranh giới tin cậy nào bị bỏ qua khi pull request chạy trên runner dùng chung?
3. Token ghi repository có thể được thay bằng cơ chế nào hoặc giới hạn ra sao?
4. Dependency và action theo tag mutable tạo ra rủi ro gì?
5. Vì sao tag latest không đủ để nhận diện artifact đã kiểm thử?
6. Release pipeline cần xác minh những bằng chứng nào?
7. Log toàn bộ environment có thể làm lộ dữ liệu gì?
8. Nên tách workflow validation, trusted build và production deploy như thế nào?
9. Nếu nghi ngờ runner bị xâm nhập, cần cô lập runner, revoke credential và xác định artifact bị ảnh hưởng ra sao?

Một câu trả lời tốt cần chỉ ra đường tấn công từ đầu vào không tin cậy đến quyền và artifact, sau đó đề xuất kiểm soát tại từng ranh giới. Không chỉ liệt kê công cụ bảo mật; hãy giải thích tài sản được bảo vệ và rủi ro mà từng kiểm soát giảm xuống.

## Kết luận

CI/CD pipeline là một mắt xích có quyền lực cao trong chuỗi cung ứng phần mềm vì nó thực thi mã, sử dụng dependency, truy cập credential, tạo artifact và thay đổi môi trường. Bảo mật pipeline vì vậy phải bao phủ source, workflow, runner, plugin, dependency, cache, secret, registry và deployment identity.

Hãy bắt đầu bằng việc xác định tài sản, tác nhân và ranh giới tin cậy. Sau đó áp dụng least privilege, cô lập job, bảo vệ secret, kiểm soát dependency, dùng artifact bất biến và xác minh provenance trước khi triển khai. Khi mỗi bước có bằng chứng và audit trail, đội ngũ có thể truy vết phần mềm từ production về đúng nguồn tạo ra nó, đồng thời giới hạn tác động nếu một mắt xích bị xâm phạm.

