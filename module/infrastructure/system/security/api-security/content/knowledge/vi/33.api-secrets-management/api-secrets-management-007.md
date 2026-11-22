# Quét secret trong source, image và artifact

Secret như API key, access token, private key, mật khẩu database, OAuth client secret và webhook signing key thường xuất hiện trong quá trình phát triển, build và phát hành phần mềm. Một secret có thể bị commit vào Git, đóng gói trong JAR, nằm trong một layer cũ của container image, xuất hiện trong source map hoặc bị ghi vào build log. Xóa dòng chứa secret khỏi source hiện tại không có nghĩa secret đã biến mất khỏi Git history, image layer, cache hoặc artifact đã được phát hành.

Quét secret (secret scanning) là quá trình tìm credential và dữ liệu xác thực nhạy cảm trong các nguồn lưu trữ và sản phẩm build, đánh giá mức độ phơi lộ, rồi xử lý bằng cách thu hồi/thay thế credential và loại bỏ đường phát tán. Việc quét cần bao phủ toàn bộ vòng đời: **source repository, lịch sử Git, pull request, build context, container image, image layer, package và artifact phát hành**.

Secret scanning không chỉ là tìm chuỗi giống API key. Một chương trình hiệu quả phải kết hợp pattern detection, entropy/context, provider verification có kiểm soát, phân loại false positive, quản lý ngoại lệ, quy trình rotation và kiểm tra lại sau remediation. Không để báo cáo scanner làm lộ chính secret mà nó phát hiện.

## 1. Mục tiêu và phạm vi quét

Một chương trình secret scanning cần trả lời:

- Secret nào đang tồn tại trong source, Git history, image hoặc artifact?
- Secret thuộc loại nào, provider/service nào và môi trường nào?
- Secret nằm trong file, layer, package hay build metadata nào?
- Nó đã được commit, push, publish hoặc deploy chưa?
- Credential còn hiệu lực không, có quyền gì và có thể truy cập tài nguyên nào?
- Ai là owner chịu trách nhiệm thu hồi và thay thế?
- Secret đã xuất hiện ở những bản build, image digest, release hoặc registry nào?
- Sau khi xử lý, còn bản sao trong cache, history, fork, mirror hoặc artifact cũ không?

Phạm vi tối thiểu nên gồm:

| Vùng | Nội dung cần quét |
|---|---|
| Source working tree | File đang được theo dõi, file mới, config, test fixture và script |
| Git repository | Branch, tag, commit history, merge request/pull request và ref khác |
| Build context | File được gửi vào Docker/build system, generated config và dependency bundle |
| Container image | Image config, metadata, filesystem và tất cả layer có thể kiểm tra |
| Package | JAR, WAR, ZIP, TAR, wheel, npm package, binary và archive lồng nhau |
| Release artifact | Static bundle, source map, debug symbol, installer, chart và manifest |
| Artifact/Container registry | Artifact đã publish, các version cũ và digest đang được deploy |
| CI/CD output | Build log, test report, cache, workspace snapshot và exported environment |

Chỉ quét thư mục source hiện tại sẽ bỏ sót secret trong lịch sử, image layer cũ và gói phát hành. Chỉ quét container filesystem cuối cùng cũng có thể bỏ sót dữ liệu đã bị xóa ở layer trên nhưng vẫn tồn tại trong layer dưới.

## 2. Secret nào cần phát hiện?

Secret không chỉ là password. Các loại thường gặp:

| Loại | Ví dụ | Rủi ro |
|---|---|---|
| API key | Key của payment, email, maps hoặc SaaS API | Gọi API thay mặt tổ chức, tiêu tốn quota hoặc đọc dữ liệu |
| OAuth credential | Client secret, refresh token, access token | Giả danh client/user hoặc truy cập resource server |
| Signing key | JWT HMAC secret, RSA/EC private key | Ký token hoặc assertion giả |
| Encryption key | KEK/DEK, application encryption key | Giải mã dữ liệu hoặc phá vỡ bảo mật dữ liệu |
| Database credential | Username/password, connection string | Truy cập, sửa hoặc xóa dữ liệu |
| Cloud credential | Access key, service account key, workload token | Truy cập cloud resource và control plane |
| Webhook secret | HMAC signing secret | Giả mạo webhook hoặc xác thực callback |
| SSH/TLS key | Private key, client certificate key | Giả danh máy chủ, workload hoặc operator |
| Personal access token | Git hosting, package registry, CI token | Đọc repository, publish package hoặc thay đổi pipeline |
| Session/bearer token | Cookie, bearer token, temporary credential | Chiếm phiên hoặc gọi API bằng quyền của người khác |

Một chuỗi có vẻ ngẫu nhiên chưa chắc là secret; ngược lại, secret có thể có entropy thấp hoặc được lưu trong file có tên bình thường. Hãy dùng nhiều tín hiệu thay vì chỉ dựa vào regex hoặc entropy.

## 3. Các vị trí secret thường bị bỏ sót trong source

Secret có thể xuất hiện trong:

- File cấu hình như YAML, JSON, TOML, XML, properties và dotenv.
- Source code, comment, test, sample, fixture, mock và notebook.
- Script shell, PowerShell, SQL migration và automation.
- Dockerfile, compose file, build script và pipeline YAML.
- Helm chart, Kubernetes manifest, Terraform/Pulumi configuration và plan/state.
- README, tài liệu nội bộ, code snippet và generated documentation.
- Frontend JavaScript bundle, source map và static configuration.
- File certificate/private key, keystore, PEM, P12/PFX và JKS.
- Binary, archive, backup, dump và file export.

Các tên file như **.env.example**, **application-test.yml** hoặc **config.sample.json** không tự động an toàn. Developer có thể copy secret thật vào ví dụ rồi quên thay bằng placeholder. Test credential cũng có thể được dùng lại ở staging/production.

Không chỉ quét phần mở rộng file quen thuộc. Có thể đổi tên file, nhúng secret vào binary hoặc archive. Scanner nên nhận diện file theo nội dung/magic bytes khi phù hợp, đồng thời có giới hạn kích thước, độ sâu giải nén và thời gian để tránh bị lợi dụng bằng archive bomb.

## 4. Quét Git working tree và pull request

Quét working tree giúp phát hiện secret trước khi commit. Quét pull request giúp chặn secret mới trước khi merge vào nhánh chính.

Các điểm kiểm soát:

1. Developer chạy scanner ở pre-commit hoặc pre-push để nhận phản hồi sớm.
2. CI quét diff của pull request, gồm file mới, file sửa và rename.
3. Branch protection yêu cầu secret scan pass trước khi merge.
4. Scanner kiểm tra cả file tracked và các loại file được đưa vào build context.
5. Báo cáo chỉ chứa path, line, rule ID, fingerprint và phần giá trị đã mask.
6. Bypass phải có owner, lý do, thời hạn và audit.

Pre-commit hook là lớp hỗ trợ, không phải ranh giới tin cậy: hook có thể bị bỏ qua, máy developer có thể không cài scanner hoặc commit được tạo từ automation khác. CI ở phía server cần là kiểm soát bắt buộc.

Không chỉ scan dòng diff khi một secret có thể được ghép từ nhiều phần hoặc được đưa vào file qua generated step. Hãy chọn chế độ quét phù hợp: diff scan cho phản hồi nhanh, full repository scan theo lịch và khi cấu hình scanner thay đổi.

## 5. Quét toàn bộ Git history

Xóa secret khỏi file hiện tại không xóa commit cũ. Git lưu snapshot trong các commit; secret có thể còn trong:

- Commit cũ và nhánh chưa merge.
- Tag/release và branch đã bị bỏ quên.
- Merge commit, reflog hoặc object chưa được garbage collect.
- Fork, mirror, clone của developer và CI workspace.
- Pull request diff, review comment hoặc patch đã lưu.
- Git LFS object hoặc submodule repository.

Full-history scan giúp tìm secret đã tồn tại trước khi scanner được đưa vào CI. Nên quét tất cả ref mà hệ thống có thể truy cập, không chỉ default branch. Với Git LFS và submodule, cần quét nội dung ở kho tương ứng theo quyền được cấp.

Nếu phát hiện secret trong history:

1. Xem secret là đã bị lộ; ưu tiên thu hồi hoặc rotate ngay.
2. Xác định commit, branch, tag, thời gian push và ai có thể đã clone.
3. Kiểm tra audit log của provider để đánh giá việc sử dụng.
4. Sau khi credential đã bị vô hiệu hóa, mới cân nhắc rewrite history để giảm phát tán.
5. Phối hợp developer, CI, mirror, fork và downstream consumer để đồng bộ lịch sử mới.
6. Quét lại tất cả ref và artifact có liên quan.

History rewrite không thu hồi credential và không thể xóa bản sao đã được clone hoặc cache. Rotation/revocation mới là biện pháp vô hiệu hóa secret bị lộ. Không yêu cầu rewrite history trước rồi mới xử lý credential vì thao tác đó làm chậm containment.

## 6. Phát hiện secret: pattern, entropy và ngữ cảnh

Scanner thường kết hợp nhiều kỹ thuật:

| Kỹ thuật | Cách hoạt động | Điểm yếu |
|---|---|---|
| Pattern/regex | Nhận diện prefix, cấu trúc hoặc tên field của provider | Có thể bỏ sót secret tùy biến hoặc phát hiện placeholder |
| Entropy | Tìm chuỗi có độ ngẫu nhiên cao | Hash, ID, checksum và dữ liệu ngẫu nhiên khác có thể bị false positive |
| Context | Xét tên biến, key, file path và vị trí như api_key, Authorization | Secret có thể dùng tên biến chung hoặc bị encode |
| Provider-specific detector | Nhận diện format token/key của một dịch vụ cụ thể | Không bao phủ credential tự tạo và format mới |
| Validation/check | Gọi provider để kiểm tra credential còn hiệu lực | Có thể tạo audit event, rate limit, lockout hoặc phát sinh side effect |
| Custom rule | Pattern riêng cho secret nội bộ | Cần bảo trì và kiểm soát false positive |

Không có một kỹ thuật nào phát hiện được mọi secret. Ví dụ private key có marker rõ; API token có thể có prefix; một password có thể chỉ là chuỗi ngắn trong URL; credential nội bộ có thể không theo format công khai.

### Secret verification có kiểm soát

Một số scanner hỗ trợ xác minh credential với provider. Chỉ bật khi có quy trình được phê duyệt và scanner dùng kênh an toàn. Cần cân nhắc:

- Có gửi credential tới bên thứ ba hay không và dữ liệu được lưu thế nào.
- Credential bị kiểm tra có thể tạo audit event hoặc trigger alert không.
- Provider có rate limit, account lockout hoặc side effect không.
- Có thể dùng endpoint read-only hoặc metadata introspection không.
- Kết quả có lưu raw token trong report hay log không.

Nếu không thể xác minh an toàn, đánh dấu trạng thái unverified và xử lý theo exposure/risk. Không thử gọi API bằng credential nghi ngờ trên production tùy tiện.

## 7. Quét container image: filesystem cuối cùng chưa đủ

Container image thường gồm nhiều layer bất biến. Ví dụ:

~~~dockerfile
FROM eclipse-temurin:21-jre
COPY application.jar /app/application.jar
RUN echo "temporary credential" > /tmp/build-token
RUN rm -f /tmp/build-token
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Lệnh xóa file ở layer sau không nhất thiết loại bỏ byte của file khỏi layer trước. Khi image được phân phối, các layer có thể vẫn chứa dữ liệu cũ. Vì vậy, quét chỉ filesystem sau khi tất cả layer được áp dụng có thể không nhìn thấy file đã bị xóa, trong khi người có image vẫn có thể truy xuất nội dung từ layer.

Quét image nên xem xét:

- Filesystem sau khi unpack.
- Từng layer và whiteout/deletion metadata.
- Image configuration, history, labels và environment metadata.
- Entrypoint/CMD, build arguments bị lưu hoặc render vào config.
- File được copy vào image trong build stage rồi bị xóa ở stage sau.
- Multi-stage build và intermediate image nếu được lưu trong cache/registry.
- Image tag cũ, digest cũ và image đang được deploy.

Quét image cuối cùng là cần thiết nhưng không thay thế việc quét build context, layer và build cache. Nếu secret từng tồn tại trong layer đã publish, cần xử lý credential và phát hành image mới sạch; chỉ xóa tag không đảm bảo mọi bản sao đã biến mất.

## 8. Các cách secret lọt vào Docker build

Những pattern thường gặp:

~~~dockerfile
# Không an toàn: secret bị lưu trong image layer/config.
ARG API_TOKEN
ENV API_TOKEN=$API_TOKEN

# Không an toàn: secret bị copy vào image.
COPY .env /app/.env

# Không an toàn: secret có thể lưu trong layer hoặc build log.
RUN curl -H "Authorization: Bearer $API_TOKEN" https://service.example/
~~~

ARG và ENV không phải secret store. Build argument có thể xuất hiện trong metadata, build history hoặc log tùy builder và cách dùng; ENV thường được lưu trong image configuration. Không truyền secret qua command line hoặc ghi vào layer.

Các biện pháp:

- Giữ secret ngoài build context; kiểm tra .dockerignore nhưng không xem đây là kiểm soát duy nhất.
- Dùng BuildKit secret mount hoặc cơ chế secret mount tương đương của builder.
- Không echo secret, bật shell tracing hoặc in environment trong build step.
- Không dùng secret để tạo file config chứa credential trong final image nếu runtime có thể inject.
- Dùng multi-stage build để loại bỏ tool và file tạm, nhưng vẫn quét intermediate layers/cache.
- Xóa build cache có chứa secret sau khi credential đã rotate và theo quy trình của builder.
- Dùng workload identity/short-lived credential thay vì long-lived key khi có thể.

Ví dụ BuildKit secret mount:

~~~dockerfile
# syntax=docker/dockerfile:1
FROM alpine:3.20 AS build
RUN --mount=type=secret,id=repo_token \
    TOKEN="$(cat /run/secrets/repo_token)" && \
    fetch-private-dependency --token "$TOKEN"
~~~

Secret mount giúp không đưa secret thành một layer thông thường, nhưng command vẫn có thể làm lộ token qua process arguments, output, crash dump hoặc file do tool tạo ra. Công cụ được gọi phải hỗ trợ cách nhận credential an toàn; không in token ra log.

## 9. Quét package và build artifact

Artifact có thể chứa source, cấu hình, metadata hoặc tài liệu đã được đóng gói. Các dạng cần quan tâm:

- Java: JAR, WAR, EAR, executable archive và nested JAR.
- JavaScript: npm tarball, browser bundle, source map và static asset.
- Python: wheel, sdist, virtual environment và bytecode package.
- .NET: assembly, publish directory, NuGet package và config transform.
- Native: executable, shared library, debug symbol và installer.
- Archive: ZIP, TAR, GZIP, 7z và archive lồng nhau.
- Deployment: Helm chart, Kubernetes manifest, Terraform plan/state và generated YAML.
- Release: CLI bundle, desktop/mobile package, backup và export.

Quét artifact sau build giúp phát hiện secret được sinh ra bởi template, resource filtering, code generation hoặc packaging. Cần scan đúng artifact cuối cùng được upload/publish, không chỉ source trước build.

### Kiểm tra nested archive an toàn

Artifact có thể chứa archive khác. Scanner cần:

- Giới hạn tổng số file, số cấp lồng nhau và tổng dung lượng sau giải nén.
- Chặn path traversal và symlink trỏ ra ngoài workspace.
- Không thực thi file hoặc script trong artifact để tìm secret.
- Xác định file type theo nội dung khi phù hợp.
- Không giải nén vô hạn hoặc theo symlink tùy ý.
- Ghi nhận file không thể scan do giới hạn hoặc định dạng không hỗ trợ.

Kết quả scan passed chỉ có nghĩa là các vùng đã quét không có finding theo rule hiện tại. Nếu một phần artifact bị bỏ qua do quá lớn hoặc định dạng không hỗ trợ, trạng thái phải thể hiện partial/incomplete, không báo pass tuyệt đối.

## 10. Frontend bundle, source map và cấu hình public

Mọi giá trị được đóng gói vào browser bundle đều có thể được người dùng tải xuống và đọc. Không đưa private API key, OAuth client secret, signing key, database password hoặc service token vào JavaScript frontend.

Các vị trí dễ bỏ sót:

- File .env.production được build tool inject vào bundle.
- Source map chứa source gốc và comment có credential.
- Static JSON config được copy nguyên vào output.
- Public runtime config có trường nội bộ do template render.
- Debug endpoint hoặc sourcemap public từ release.

Một số key được thiết kế để public (ví dụ publishable key có giới hạn domain/API) không tương đương secret. Cần xác nhận semantics của provider và quyền thực tế. Đừng gắn nhãn mọi API key là an toàn để public chỉ vì nó được gọi là client key.

Quét thư mục output cuối cùng, source map, manifest và asset đã minify. Kiểm tra cả domain allowlist, quota và restriction của public key. Nếu một credential có thể thực hiện thao tác privileged hoặc đọc dữ liệu, nó không được đặt trong browser bundle.

## 11. Quét Terraform, Helm và deployment artifact

Deployment artifact có thể chứa secret ngay cả khi source application không có:

- Terraform state/plan lưu giá trị resource argument, đôi khi gồm password hoặc token.
- Helm values và rendered manifest có thể chứa Secret data hoặc inline credential.
- Kubernetes manifest có thể chứa base64-encoded Secret; Base64 không phải encryption.
- Cloud-init/user-data và startup script có thể chứa credential.
- CI-generated config có thể ghi secret vào file rồi publish cùng artifact.

Scanner cần decode các encoding được hỗ trợ trong giới hạn an toàn để phát hiện secret được che bằng Base64 hoặc escape. Không xem encoding là biện pháp bảo vệ.

Với Kubernetes Secret, kiểm tra source of truth, manifest được render và artifact đã publish. Tránh lưu raw secret trong chart hoặc Git. Dùng external secret controller, workload identity hoặc secret store integration phù hợp. Terraform state cần backend được mã hóa, access-controlled và có retention phù hợp; secret vẫn phải được rotate nếu state bị lộ.

## 12. Tổ chức pipeline secret scanning

Một pipeline nhiều lớp giúp phát hiện sớm và bao phủ cả sản phẩm cuối:

~~~mermaid
flowchart TD
    A[Developer workspace] --> B[Pre-commit scan]
    B --> C[Pull request diff scan]
    C --> D[Full repository/history scan]
    D --> E[Build with secret-safe mounts]
    E --> F[Scan build output and packages]
    F --> G[Build container image]
    G --> H[Scan image config and layers]
    H --> I[Publish to artifact registry]
    I --> J[Registry rescan and deployment gate]
    J --> K[Periodic inventory and incident response]
    C --> X[Finding triage]
    F --> X
    H --> X
    J --> X
    X --> R[Revoke, rotate, rebuild and verify]
~~~

Các lớp có vai trò khác nhau:

| Điểm quét | Mục tiêu | Điều kiện gate gợi ý |
|---|---|---|
| Developer/pre-commit | Phản hồi nhanh trước commit | Cảnh báo và hướng dẫn sửa |
| Pull request | Chặn secret mới trước merge | Block finding có confidence cao, trừ exception được duyệt |
| Scheduled full-history | Tìm secret cũ và ref bị bỏ sót | Tạo finding theo severity/owner |
| Build output | Tìm secret do build/generate/package | Không publish artifact có secret nghiêm trọng |
| Container image | Quét layer/config/history | Không deploy image có credential rủi ro cao |
| Registry | Quét lại image/artifact đã publish | Cách ly digest có finding mới |
| Periodic inventory | Theo dõi artifact tồn tại lâu và scanner rule mới | Mở lại finding nếu secret mới được phát hiện |

Không dùng một kết quả scan cũ cho mọi digest. Mỗi artifact nên được nhận diện bằng immutable digest, scanner version, rule-set version, thời điểm scan và trạng thái coverage.

## 13. Ví dụ công cụ và cách dùng

Các công cụ phổ biến có thể đảm nhiệm những phần khác nhau:

| Công cụ/nhóm | Công dụng thường gặp |
|---|---|
| Gitleaks | Quét secret trong Git repository và commit history |
| TruffleHog | Phát hiện secret trong repository và một số nguồn dữ liệu khác; có detector/verification tùy cấu hình |
| detect-secrets | Baseline và phát hiện secret trong file/repository |
| GitHub/GitLab secret scanning | Quét repository, pull request hoặc push theo tính năng nền tảng |
| Trivy | Quét image/filesystem, có secret scanner cùng các loại scan khác |
| Scanner của cloud/provider | Phát hiện credential của provider và hỗ trợ quy trình revoke |

Ví dụ lệnh minh họa, cần pin phiên bản và kiểm tra cú pháp theo công cụ đang triển khai:

~~~bash
# Quét Git repository; yêu cầu scanner không in giá trị secret.
gitleaks detect --source . --redact

# Quét image với secret scanner; dùng digest bất biến trong pipeline.
trivy image --scanners secret registry.example.com/team/api@sha256:...
~~~

Tên lệnh, cờ và mặc định có thể thay đổi theo phiên bản. Cần chạy scanner trong CI với output đã redact, không đưa token của registry/provider vào command line hoặc report. Một scanner quét Git không thay thế scanner hiểu image layer; một image scanner cũng không thay thế full Git history scan.

## 14. Quản lý finding và false positive

Scanner có thể phát hiện:

- Credential thật đang hoạt động.
- Credential đã hết hạn hoặc đã revoke nhưng vẫn tồn tại trong history.
- Test token chỉ dùng trong môi trường cô lập.
- Placeholder/documentation sample.
- Random ID, hash hoặc checksum bị nhận nhầm.

Mỗi finding nên có metadata:

| Trường | Mục đích |
|---|---|
| Finding ID | Định danh không chứa secret |
| Detector/rule ID | Biết rule nào phát hiện |
| Repository/artifact digest | Xác định nguồn |
| File path/layer/package | Xác định vị trí |
| Line/range hoặc layer index | Hỗ trợ remediation |
| Secret type/provider | Phân loại credential |
| Fingerprint | Gộp finding trùng mà không lưu raw secret |
| Confidence/status | Confirmed, likely, unverified, false positive |
| Exposure | Local, committed, pushed, published, deployed |
| Owner/severity/deadline | Điều phối xử lý |
| First seen/last seen | Theo dõi thời gian tồn tại |

### Allowlist có kiểm soát

Không tắt rule hoặc ignore toàn bộ file chỉ vì có false positive. Exception nên:

- Gắn với fingerprint cụ thể và rule ID.
- Giới hạn path/repository/artifact cần thiết.
- Có owner, lý do và ngày hết hạn.
- Được review khi secret type hoặc detector thay đổi.
- Không chứa raw secret trong cấu hình exception.
- Có audit người tạo, người duyệt và lần gia hạn.

Không dùng một allowlist rộng như **/*.yml hoặc test/** nếu trong đó vẫn có thể xuất hiện credential thật. Test fixture nên dùng giá trị giả không thể xác thực ở bất kỳ provider nào.

## 15. Đánh giá mức độ nghiêm trọng

Không phải mọi finding đều có cùng rủi ro. Có thể đánh giá theo:

- **Credential type:** signing/encryption key, cloud admin key hoặc production token thường có tác động cao.
- **Privilege:** read-only, write, admin, publish, impersonation hay key management.
- **Environment:** production, staging, development hoặc local.
- **Exposure:** chỉ local, commit chưa push, đã push, public repository, published artifact hay image đang deploy.
- **Validity:** active, expired, revoked hoặc chưa xác minh.
- **Scope:** một resource, một tenant hay toàn bộ organization.
- **Age:** thời gian tồn tại và khả năng đã bị sao chép.
- **Evidence of use:** provider audit log cho thấy credential được sử dụng bất thường hay không.

Một private signing key production đã push vào public repository cần ưu tiên cao ngay cả khi chưa có bằng chứng bị sử dụng. Một test placeholder trong fixture có thể là false positive nếu chứng minh không phải credential và không thể dùng được.

Không hạ severity chỉ vì secret đã bị xóa khỏi source hiện tại. Nếu credential vẫn active hoặc artifact cũ vẫn được phân phối, rủi ro vẫn tồn tại.

## 16. Xử lý khi phát hiện secret

Quy trình ứng phó nên theo thứ tự ưu tiên:

1. **Xác nhận finding an toàn:** xem detector, fingerprint, vị trí và context đã mask; không copy secret vào ticket/chat.
2. **Xác định owner/provider:** tìm service owner và nơi credential được cấp.
3. **Contain credential:** revoke, disable hoặc rotate theo khả năng provider; với key dùng để ký, chuẩn bị key rollover và xử lý token/certificate liên quan.
4. **Đánh giá exposure:** local/commit/push/public/artifact/deployed; xác định branch, image digest, release và người có thể đã tải.
5. **Kiểm tra hoạt động:** xem provider audit log, API usage, source IP, scope và thời gian sử dụng.
6. **Thay thế an toàn:** chuyển sang secret manager, workload identity hoặc short-lived credential; cập nhật consumer.
7. **Loại bỏ nguồn phát tán:** sửa source/config, build lại artifact/image và loại bỏ release có secret.
8. **Xử lý bản sao:** registry, cache, mirror, fork, package CDN, CI workspace và backup theo retention policy.
9. **Quét lại:** source, Git history, artifact, image digest mới và registry.
10. **Đóng finding:** chỉ đóng khi credential đã vô hiệu hóa/thay thế, artifact rủi ro đã được xử lý và evidence được ghi nhận.

Không coi việc xóa file, rotate scanner baseline hoặc thêm ignore rule là remediation hoàn chỉnh. Nếu secret từng được public, giả định attacker có thể đã sao chép nó.

## 17. Xử lý secret trong Git history và bản sao

Sau khi credential đã được revoke/rotate, có thể cân nhắc rewrite history để giảm việc secret tiếp tục xuất hiện trong clone mới:

- Thống nhất thời điểm rewrite và thông báo cho contributor/CI.
- Rewrite các branch/tag liên quan bằng công cụ phù hợp.
- Force-push theo quy trình được phê duyệt và xử lý branch protection.
- Yêu cầu developer clone/fetch lại lịch sử sạch; tránh merge lại commit cũ.
- Làm sạch mirror, fork và automation cache trong phạm vi tổ chức kiểm soát.
- Kiểm tra pull request, issue, comment, CI log và package đã phát hành.
- Chạy full-history scan sau rewrite.

Không thể đảm bảo xóa mọi bản sao đã được clone, fork hoặc archive bên ngoài. Vì vậy, credential phải được coi là compromised và rotation là bắt buộc theo mức rủi ro. Việc rewrite history chủ yếu giảm tái phát tán và giảm khả năng secret bị copy lại.

## 18. Làm sạch container image và registry

Nếu secret xuất hiện trong image:

1. Revoke/rotate credential trước.
2. Xác định digest, tag, layer và pipeline đã tạo image.
3. Sửa Dockerfile/build script/build context để secret không được đưa vào layer/config.
4. Build image mới từ base và dependency phù hợp, không tái sử dụng cache có nguy cơ chứa secret.
5. Scan image mới, bao gồm layer và metadata.
6. Publish image mới, ký/attest digest theo quy trình release.
7. Cập nhật deployment để dùng digest mới.
8. Xóa/retire tag cũ và image không còn cần theo chính sách registry.
9. Kiểm tra node cache, mirror và registry replication.

Xóa tag không nhất thiết xóa manifest/layer đã được tham chiếu bởi digest khác hoặc cache. Registry garbage collection và retention phải theo cơ chế của nền tảng. Nếu image cũ đã được tải xuống, không thể thu hồi bản sao đó; credential phải bị vô hiệu hóa.

## 19. Bảo vệ scanner và kết quả scan

Scanner cũng có thể trở thành nguồn rò rỉ secret nếu được cấu hình sai:

- Không in raw match vào CI console hoặc pull request comment.
- Dùng chế độ redact; chỉ lưu fingerprint, loại secret, path và line.
- Giới hạn quyền truy cập report/SARIF và artifact chứa finding.
- Không gửi toàn bộ repository/artifact lên dịch vụ bên ngoài nếu chưa đánh giá data handling.
- Dùng scanner credential có quyền read-only tối thiểu và thời hạn ngắn.
- Không cho scanner credential có quyền publish, merge hoặc revoke nếu không cần.
- Không cho untrusted pull request đọc secret của pipeline.
- Tránh đưa secret vào command-line arguments, environment dump hoặc debug trace.
- Pin scanner version và quản lý rule updates.
- Ghi nhận scan coverage, scanner version, ruleset và exit status.

Với pull request từ fork, pipeline không nên expose production secret chỉ để chạy scanner. Có thể dùng scan mode không cần credential, sandbox hoặc token chỉ đọc repository được cấp scope phù hợp.

## 20. Quản lý coverage và trạng thái scan

Không nên chỉ lưu kết quả pass/fail. Cần thể hiện scanner đã kiểm tra những gì:

| Trạng thái | Ý nghĩa |
|---|---|
| passed | Toàn bộ phạm vi bắt buộc đã scan, không có finding chặn |
| findings | Có một hoặc nhiều secret finding cần triage |
| partial | Một phần file/layer/archive không được scan hoặc bị giới hạn |
| failed | Scanner lỗi, timeout hoặc không đọc được nguồn |
| not_scanned | Chưa có lần scan hợp lệ |
| suppressed | Finding cụ thể được exception có kiểm soát; cần expiry/review |

Các metadata nên lưu:

- Source commit/ref hoặc artifact/image digest.
- Scanner name/version và ruleset version.
- Thời gian bắt đầu/kết thúc và pipeline run ID.
- Scope: branch/history/layer/package/path.
- File/layer bị bỏ qua, lý do và giới hạn áp dụng.
- Số finding theo severity/confidence/type.
- Kết quả exception/allowlist.

Không đánh dấu release là sạch nếu scanner không chạy, chỉ quét filesystem cuối cùng nhưng bỏ layer, hoặc archive không được giải nén. Gate release có thể quy định mức coverage tối thiểu theo loại artifact.

## 21. Ngăn secret xuất hiện trở lại

Phòng ngừa hiệu quả hơn việc liên tục xóa secret sau khi đã phát hiện:

- Dùng secret manager hoặc platform secret store thay cho hardcode.
- Ưu tiên workload identity, federated identity và short-lived credential.
- Dùng build secret mount, không truyền secret qua Docker ARG/ENV hoặc image layer.
- Giữ secret ngoài repository và build context; .gitignore/.dockerignore là hỗ trợ, không phải secret store.
- Tạo test credential riêng, có scope thấp và tự hết hạn; không dùng lại production secret.
- Dùng template placeholder rõ ràng, ví dụ REPLACE_WITH_TEST_VALUE, không dùng credential thật đã revoke.
- Bật secret scanning ở pull request và registry.
- Có custom detector cho format nội bộ.
- Đào tạo developer cách xử lý khi commit nhầm secret.
- Có playbook revoke/rotate đã được diễn tập.

Không tạo long-lived credential cho pipeline nếu có thể dùng OIDC/workload federation. Nếu buộc phải dùng token, giới hạn repository, environment, action và lifetime; không cấp quyền admin chỉ để chạy build.

## 22. Chỉ số và cảnh báo cho chương trình secret scanning

Nên theo dõi:

- Số finding mới theo source, image, artifact và environment.
- Số secret đã xác nhận active, expired, revoked hoặc chưa xác minh.
- Thời gian từ first seen tới revoke/rotate.
- Thời gian remediation theo severity.
- Số artifact/image digest có finding đang được deploy.
- Tỷ lệ repository/branch/tag/registry được scan.
- Tỷ lệ scan partial/failed và số file/layer bị bỏ qua.
- Số exception còn hiệu lực, sắp hết hạn và quá hạn review.
- Số secret tái xuất hiện sau remediation.
- Số credential có provider audit event bất thường sau khi phát hiện.

Alert ngay khi production signing key, cloud admin credential hoặc credential có quyền truy cập dữ liệu bị phát hiện trong public source/artifact. Cảnh báo riêng khi scanner không chạy hoặc coverage giảm; một pipeline im lặng do scanner outage không phải là trạng thái an toàn.

Không dùng raw secret hoặc fingerprint có thể đảo ngược làm metric label. Dùng detector type, severity, repository/service, environment và status với cardinality có kiểm soát.

## 23. Kiểm thử chương trình secret scanning

Test nên bao phủ cả khả năng phát hiện, khả năng không làm lộ secret và quy trình remediation:

| Nhóm test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Source | Credential test giả trong file code/config | Scanner phát hiện đúng rule/path |
| Git history | Secret đã xóa ở commit cũ | Full-history scan vẫn phát hiện |
| Pull request | Secret mới trong diff | CI gate chặn merge theo policy |
| Branch/tag | Secret chỉ có ở branch/tag không mặc định | Full-ref scan phát hiện |
| Archive | Secret nằm trong ZIP/JAR nested archive | Scanner tìm thấy trong giới hạn an toàn |
| Image layer | Secret được tạo ở layer rồi xóa ở layer sau | Layer-aware scan phát hiện |
| Image config | Secret nằm trong ENV/label/history | Image metadata scan phát hiện |
| Build output | Secret được template/codegen tạo ra | Artifact scan phát hiện trước publish |
| Frontend | Secret trong bundle/source map | Release scan phát hiện |
| IaC | Base64 Secret/Terraform state có credential | Scanner decode/parse và phát hiện |
| False positive | Placeholder hoặc hash ngẫu nhiên | Có thể triage/allowlist theo fingerprint |
| Redaction | CI report và console output | Không có raw secret |
| Scanner failure | Timeout, file quá lớn, unsupported format | Trạng thái partial/failed, không báo pass |
| Exception expiry | Allowlist quá hạn | Finding được mở lại hoặc gate cảnh báo |
| Rotation | Credential bị lộ được revoke/thay mới | Credential cũ không còn dùng được |
| Re-scan | Source/image/artifact sau remediation | Không còn finding active trong phạm vi đã scan |
| Registry | Image digest cũ vẫn được lưu/deploy | Finding được gắn đúng digest và deployment |

Nên dùng canary/test secret do tổ chức tự tạo, không thể truy cập tài nguyên thật và có thể revoke. Không dùng secret production để kiểm tra scanner. Test integration phải xác nhận report được redact trước khi ghi ra log hoặc upload.

## 24. Checklist quét secret trong source, image và artifact

- [ ] Xác định secret types và custom detector phù hợp với hệ thống.
- [ ] Quét working tree, pull request và toàn bộ Git history/ref cần quản lý.
- [ ] Bao gồm branch, tag, fork/mirror, submodule và Git LFS trong phạm vi cho phép.
- [ ] Quét build context, generated config, test fixture và pipeline output.
- [ ] Quét image filesystem, config, history và từng layer; không chỉ filesystem cuối cùng.
- [ ] Quét package/archive lồng nhau, frontend bundle, source map và deployment artifact.
- [ ] Có giới hạn an toàn cho giải nén, file size, nesting depth và symlink.
- [ ] Gắn finding với fingerprint, path/layer, artifact digest, owner và exposure.
- [ ] Không in raw secret vào CI log, PR comment, ticket hoặc scanner report.
- [ ] Có triage false positive và allowlist hẹp, có owner/expiry/audit.
- [ ] Ưu tiên revoke/rotate trước khi rewrite Git history hoặc xóa artifact.
- [ ] Rebuild image/artifact sạch và cập nhật deployment sang digest mới.
- [ ] Xem xét fork, mirror, cache, registry, CDN và bản sao đã phát hành.
- [ ] Quét lại sau remediation và xác minh credential cũ không còn hiệu lực.
- [ ] Theo dõi scanner coverage, version, ruleset và trạng thái partial/failed.
- [ ] Dùng secret manager/workload identity và short-lived credential để ngăn tái phát.
- [ ] Có alert cho secret production nghiêm trọng và scanner pipeline bị lỗi.

## Kết luận

Quét secret phải bao phủ toàn bộ đường đi của phần mềm: source và Git history, build context, container image/layer, package, release artifact và registry. Pattern, entropy, context và provider-specific detector bổ sung cho nhau; kết quả cần được triage mà không làm lộ raw credential. Khi phát hiện secret, hãy thu hồi hoặc rotate trước, đánh giá exposure, thay thế bằng secret manager/workload identity, build lại artifact sạch và quét lại mọi digest liên quan. Quét định kỳ cùng CI/CD gate, coverage rõ ràng, exception có thời hạn và audit remediation giúp giảm khả năng secret lọt vào production hoặc tiếp tục tồn tại trong các bản phát hành cũ.
