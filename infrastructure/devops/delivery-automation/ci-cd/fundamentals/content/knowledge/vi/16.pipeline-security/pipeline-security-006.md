# Tích hợp kiểm tra phụ thuộc, mã nguồn và thông tin bí mật

## 1. Vì sao cần tích hợp các kiểm tra bảo mật vào CI/CD?

Một pipeline có quyền truy cập mã nguồn, tải dependency, tạo artifact và đôi khi triển khai vào môi trường thật. Nếu chỉ kiểm thử chức năng mà không kiểm tra bảo mật, một thay đổi có thể đưa vào hệ thống thư viện chứa lỗ hổng, đoạn mã có nguy cơ khai thác hoặc credential bị commit nhầm.

Ba nhóm kiểm tra nền tảng cần được kết hợp trong luồng CI/CD là:

- **Kiểm tra mã nguồn (SAST và các kiểm tra tĩnh liên quan):** tìm dấu hiệu lỗi bảo mật trong mã do nhóm phát triển, chẳng hạn SQL injection, xử lý dữ liệu không an toàn, cấu hình mã hóa yếu hoặc sử dụng API nguy hiểm.
- **Kiểm tra phụ thuộc (SCA):** xác định thư viện trực tiếp và bắc cầu, phát hiện phiên bản có lỗ hổng, license không phù hợp hoặc nguồn package không được phép.
- **Quét thông tin bí mật (secret scanning):** phát hiện token, mật khẩu, private key và credential có nguy cơ bị đưa vào repository, lịch sử Git, log hoặc artifact.

Ba nhóm này bổ sung cho nhau. SAST xem xét cách mã được viết; SCA xem xét thành phần bên ngoài mà ứng dụng sử dụng; secret scanning tìm thông tin xác thực có thể trao quyền truy cập cho người khác. Không một nhóm kiểm tra nào có thể thay thế hai nhóm còn lại.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, mục tiêu là xây dựng luồng phát hành có truy vết từ sự kiện Git, pipeline dưới dạng mã, build và kiểm thử tự động đến quản lý artifact, môi trường, cổng chất lượng, bảo vệ bí mật, xác minh sau triển khai và khả năng quay lui. Các kiểm tra bảo mật cần chạy tại thời điểm phù hợp, tạo bằng chứng gắn với commit và artifact, đồng thời đưa ra quyết định rõ ràng trước khi thay đổi được phát hành.

## 2. Ba nhóm kiểm tra và phạm vi của chúng

| Nhóm | Đối tượng kiểm tra | Phát hiện điển hình | Kết quả cần lưu |
|---|---|---|---|
| SAST / source checks | Mã nguồn và một số cấu hình được phân tích tĩnh | Injection, xử lý đầu vào yếu, mật mã không an toàn, lỗi phân quyền | Finding, vị trí mã, quy tắc, mức độ và phiên bản scanner |
| SCA / dependency checks | Dependency trực tiếp, bắc cầu và package được đóng gói | CVE, license, package không được phép, phiên bản lỗi thời | Dependency graph, SBOM, finding và nguồn dữ liệu |
| Secret scanning | Diff, repository, lịch sử Git và một số đầu ra | Token, password, private key, connection string | Loại secret, vị trí, commit và trạng thái xử lý đã được làm sạch |

Các nhóm kiểm tra có thể mở rộng sang container image, Infrastructure as Code, cấu hình Kubernetes, API hoặc ứng dụng đang chạy. Tuy nhiên, cần phân biệt rõ:

- **SAST** phân tích mã mà không cần chạy ứng dụng.
- **DAST** kiểm tra hành vi ứng dụng đang chạy bằng cách gửi request có kiểm soát.
- **SCA** kiểm tra thành phần và dependency của phần mềm.
- **Secret scanning** tìm credential bị lộ trong nội dung được quét.
- **Container scanning** kiểm tra image, package hệ điều hành, cấu hình và đôi khi cả secret trong image layer.
- **IaC scanning** kiểm tra cấu hình hạ tầng trước khi áp dụng.

Bài này tập trung vào cách phối hợp SAST, SCA và secret scanning thành một luồng kiểm soát thống nhất.

## 3. Đặt kiểm tra ở đúng thời điểm trong vòng đời thay đổi

Không nên đợi đến ngày phát hành mới chạy toàn bộ kiểm tra bảo mật. Khi phản hồi đến muộn, thay đổi đã có thể đi qua nhiều nhánh, được tích hợp với nhiều tính năng khác và khó xác định nguyên nhân.

Một mô hình thực tế chia kiểm tra thành nhiều lớp:

| Thời điểm | Kiểm tra chính | Mục tiêu |
|---|---|---|
| Trước khi commit | Hook hoặc công cụ local tùy chọn | Phản hồi nhanh cho nhà phát triển |
| Pull request | Secret scan trên diff, SAST nhanh, SCA trên lockfile, lint và test | Ngăn lỗi rõ ràng trước khi hợp nhất |
| Sau khi merge | Quét đầy đủ mã nguồn và dependency graph, build, tạo SBOM | Xác minh trạng thái tích hợp |
| Theo lịch | Quét lại dependency và repository với dữ liệu lỗ hổng mới | Phát hiện rủi ro mới xuất hiện sau khi mã không đổi |
| Trước khi publish/release | Scan artifact/image, kiểm tra license, provenance và policy | Chứng minh đúng artifact được phát hành |
| Sau triển khai | Theo dõi cảnh báo runtime và xác minh dịch vụ | Phát hiện tác động trong môi trường thật |

Các lần quét có thể dùng cùng bộ quy tắc nhưng khác thời gian và mức độ sâu. Pull request cần kết quả đủ nhanh để không làm gián đoạn nhịp phát triển. Release pipeline có thể chạy thêm phân tích toàn diện và kiểm tra trên artifact cuối cùng.

Quét theo lịch đặc biệt quan trọng với SCA. Một dependency hôm nay chưa có CVE có thể được công bố lỗ hổng vào tuần sau dù repository không thay đổi. Vì vậy, bảo mật dependency là quá trình liên tục chứ không chỉ là một bước trong pull request.

## 4. Thiết kế luồng kiểm tra thống nhất

Một luồng tổng quát có thể triển khai như sau:

~~~mermaid
flowchart TD
    A["Pull request hoặc thay đổi Git"] --> B["Kiểm tra nguồn và ngữ cảnh sự kiện"]
    B --> C["Secret scan"]
    B --> D["SAST và lint bảo mật"]
    B --> E["SCA: dependency và license"]
    C --> F["Tổng hợp finding"]
    D --> F
    E --> F
    F --> G{"Quality gate"}
    G -- "Vi phạm bị chặn" --> H["Chặn merge, trả hướng xử lý"]
    G -- "Đạt hoặc có cảnh báo được phép" --> I["Build artifact"]
    I --> J["Scan artifact và tạo SBOM"]
    J --> K{"Release policy đạt?"}
    K -- "Không" --> H
    K -- "Có" --> L["Publish artifact bất biến"]
    L --> M["Deploy theo chính sách"]
    M --> N["Verify và theo dõi"]
~~~

Các bước có thể chạy song song khi độc lập. Tuy nhiên, bước publish phải phụ thuộc vào những kiểm tra bắt buộc và phải dùng đúng artifact đã được kiểm tra. Nếu pipeline build lại sau khi scan, kết quả scan trước đó có thể không còn áp dụng cho artifact được phát hành.

Mỗi lần chạy cần ghi lại:

- Repository, branch, event và commit SHA.
- Pull request hoặc change request liên quan.
- Phiên bản scanner, ruleset và dữ liệu lỗ hổng.
- Dependency lockfile hoặc dependency graph.
- Finding và trạng thái xử lý.
- Artifact digest, SBOM và provenance.
- Quyết định của quality gate và ngoại lệ được duyệt.

## 5. Kiểm tra mã nguồn bằng SAST

SAST phân tích mã nguồn hoặc bytecode mà không cần thực thi ứng dụng. Công cụ có thể dùng quy tắc, pattern, data-flow hoặc taint analysis để tìm đường đi từ dữ liệu không đáng tin cậy đến thao tác nhạy cảm.

Một số nhóm lỗi thường gặp:

- SQL injection do nối chuỗi đầu vào vào câu truy vấn.
- Cross-site scripting do hiển thị dữ liệu không được encode.
- Path traversal khi tên file từ người dùng được dùng trực tiếp để truy cập filesystem.
- Command injection khi dữ liệu bên ngoài được ghép vào lệnh hệ điều hành.
- Kiểm tra quyền không đầy đủ trước khi truy cập tài nguyên.
- Sử dụng thuật toán hoặc cấu hình mật mã yếu.
- Xử lý lỗi làm lộ thông tin nội bộ.
- Dùng API không an toàn hoặc cấu hình bảo mật mặc định yếu.

SAST có thể phân tích ngữ cảnh của ngôn ngữ và framework. Một quy tắc tìm chuỗi SQL nguy hiểm có thể báo nhiều cảnh báo nếu không nhận biết prepared statement hoặc lớp truy cập dữ liệu đã kiểm soát đầu vào. Vì vậy, kết quả cần được triage theo luồng dữ liệu, khả năng khai thác và ngữ cảnh ứng dụng.

### 5.1. Tổ chức SAST theo lớp

Có thể chia kiểm tra mã nguồn thành:

1. **Lint và quy tắc an toàn cơ bản:** phát hiện API nguy hiểm, cấu hình không phù hợp và lỗi dễ sửa.
2. **SAST nhanh trên diff:** ưu tiên dòng mã mới hoặc vùng bị thay đổi để phản hồi sớm.
3. **SAST toàn repository:** phân tích đầy đủ các luồng dữ liệu và thành phần liên quan sau khi merge hoặc theo lịch.
4. **Kiểm tra tùy chỉnh:** quy tắc riêng cho framework, kiến trúc hoặc yêu cầu bảo mật của sản phẩm.

Không nên chỉ quét dòng mới rồi bỏ qua nợ bảo mật cũ. Có thể áp dụng chính sách không đưa thêm lỗi mới vượt ngưỡng, đồng thời tạo kế hoạch xử lý finding tồn đọng theo mức độ và thời hạn.

### 5.2. Đọc finding đúng cách

Một finding SAST nên có các thông tin:

- Quy tắc hoặc loại điểm yếu.
- File và vị trí liên quan.
- Nguồn dữ liệu và điểm sử dụng nếu công cụ hỗ trợ.
- Đường đi dữ liệu hoặc bằng chứng.
- Mức độ nghiêm trọng.
- Khả năng khai thác trong ngữ cảnh ứng dụng.
- Hướng sửa và liên kết tài liệu.

Không nên kết luận một lỗi có thể khai thác chỉ dựa trên tên quy tắc. Cần xem dữ liệu có thực sự do người dùng kiểm soát không, có lớp validation/encoding phù hợp không và đoạn mã có thể được gọi trong môi trường thật không.

## 6. Kiểm tra dependency bằng SCA

SCA xác định những package mà ứng dụng sử dụng, bao gồm dependency trực tiếp và dependency bắc cầu. Công cụ đối chiếu tên package, phiên bản và hệ sinh thái với dữ liệu lỗ hổng, license hoặc chính sách package.

Một dependency có thể xuất hiện trong dự án qua nhiều đường:

~~~text
Ứng dụng
  ├── thư viện A
  │     └── thư viện C
  └── thư viện B
        └── thư viện C
~~~

Thư viện C là dependency bắc cầu. Nhà phát triển có thể không khai báo trực tiếp nhưng ứng dụng vẫn đóng gói và sử dụng nó. Chỉ kiểm tra danh sách dependency trực tiếp sẽ bỏ sót rủi ro này.

### 6.1. Lockfile và dependency graph

Lockfile ghi lại phiên bản dependency đã được giải quyết. Nó giúp hai lần build sử dụng cùng phiên bản trong điều kiện phù hợp và tạo đầu vào đáng tin cậy cho SCA.

Một quy trình nên:

- Tạo hoặc cập nhật lockfile bằng package manager chính thức.
- Review thay đổi dependency graph trong pull request.
- Kiểm tra cả package trực tiếp và bắc cầu.
- Ghi lại registry hoặc nguồn package.
- Pin phiên bản và xác minh checksum/chữ ký theo chính sách.
- Tránh dynamic version trong release build nếu cần tái lập.

Ví dụ các lệnh xem dependency graph:

~~~bash
./mvnw dependency:tree
./gradlew dependencies
npm ls --all
pipdeptree
~~~

Các lệnh này giúp xem quan hệ package; chúng không tự thay thế vulnerability scan hoặc license policy. Kết quả cần được kết hợp với scanner và SBOM của artifact.

### 6.2. Đánh giá lỗ hổng dependency

Không phải mọi CVE đều có cùng mức rủi ro đối với một ứng dụng. Khi đánh giá finding, cần xem:

- Mức độ nghiêm trọng theo nguồn dữ liệu.
- Phiên bản package có thực sự bị ảnh hưởng không.
- Dependency có được đóng gói vào artifact hay chỉ dùng trong build/test.
- Thành phần bị ảnh hưởng có được gọi trong ứng dụng không.
- Điều kiện khai thác có tồn tại trong môi trường triển khai không.
- Có phiên bản đã sửa hoặc biện pháp giảm thiểu không.
- Package có bị đánh dấu đã bị khai thác thực tế hay không, nếu dữ liệu đó có sẵn.

CVSS là một tín hiệu quan trọng nhưng không phải quyết định duy nhất. Khả năng khai thác, mức phơi bày, vai trò của package và tác động nghiệp vụ cũng cần được xem xét.

### 6.3. License và nguồn package

SCA có thể kiểm tra license để phát hiện điều khoản không phù hợp với chính sách phân phối sản phẩm. Nhóm cần phân biệt license của dependency trực tiếp và bắc cầu, cũng như cách license áp dụng cho sản phẩm được phân phối.

Ngoài license, cần kiểm tra nguồn package:

- Chỉ cho phép registry đã được phê duyệt.
- Kiểm soát namespace package nội bộ.
- Ngăn dependency confusion.
- Dùng repository proxy hoặc mirror nội bộ nếu phù hợp.
- Ghi lại checksum, chữ ký và provenance.
- Không fallback tùy tiện sang registry công khai khi nguồn nội bộ lỗi.

## 7. Quét thông tin bí mật

Secret scanning tìm credential có thể trao quyền truy cập vào hệ thống hoặc dữ liệu. Ví dụ:

- API token và access key.
- Mật khẩu database hoặc message broker.
- Private key và certificate chứa khóa riêng.
- Token truy cập repository hoặc cloud.
- Connection string có username/password.
- Credential trong script, tệp cấu hình, log hoặc tài liệu.

Một scanner có thể kết hợp pattern đã biết, checksum của token, entropy và quy tắc theo nhà cung cấp. Tuy nhiên, không có scanner nào phát hiện mọi secret. Token tùy biến hoặc credential được mã hóa có thể không khớp quy tắc.

### 7.1. Quét nhiều phạm vi

Nên kết hợp các phạm vi sau:

- **Pre-commit:** phát hiện sớm trên máy nhà phát triển.
- **Pull request diff:** ngăn secret mới đi vào nhánh được bảo vệ.
- **Repository scan:** kiểm tra các file hiện tại.
- **Git history scan:** tìm secret còn nằm trong commit cũ dù file hiện tại đã xóa.
- **Artifact/image scan:** tìm credential bị đóng gói trong binary, layer hoặc file cấu hình.
- **Log và output scan:** kiểm tra pipeline có vô tình in credential không.

Pre-commit là lớp hỗ trợ. Người dùng có thể bỏ qua hook hoặc commit từ môi trường khác, nên server-side scan vẫn cần thiết.

### 7.2. Phân biệt secret thật và dữ liệu giả

Ví dụ trong tài liệu hoặc test có thể chứa chuỗi trông giống token. Để giảm cảnh báo giả:

- Dùng giá trị giả có định dạng rõ ràng như EXAMPLE_TOKEN_DO_NOT_USE.
- Không sao chép credential thật vào test fixture.
- Đánh dấu ngoại lệ ở phạm vi nhỏ và có lý do.
- Không thêm allowlist rộng theo tên file hoặc thư mục nếu chưa đánh giá.
- Kiểm tra lại ngoại lệ khi quy tắc scanner thay đổi.

Không nên đưa secret thật vào tài liệu hướng dẫn rồi trông chờ scanner tự nhận ra ngữ cảnh minh họa.

## 8. Phản ứng khi secret bị phát hiện

Khi scanner tìm thấy credential có khả năng thật, cần xử lý như một sự cố bảo mật cho đến khi xác minh được ngược lại.

Trình tự xử lý:

1. **Ngăn sử dụng tiếp:** chặn merge hoặc publish nếu secret nằm trong thay đổi chưa phát hành.
2. **Xác minh loại credential:** xác định dịch vụ, chủ sở hữu, quyền và phạm vi ảnh hưởng mà không in giá trị secret ra log.
3. **Thu hồi hoặc xoay vòng:** vô hiệu hóa credential đã lộ và cấp credential mới qua secret manager.
4. **Kiểm tra dấu hiệu sử dụng:** xem audit log của dịch vụ để phát hiện truy cập bất thường.
5. **Xử lý repository:** xóa secret khỏi mã hiện tại; nếu cần, làm sạch lịch sử Git theo quy trình có kiểm soát.
6. **Tìm bản sao:** kiểm tra branch, fork, cache, artifact, log, image và bản sao đã tải.
7. **Xác minh:** chạy lại secret scan và kiểm tra credential cũ không còn hiệu lực.
8. **Phòng ngừa:** xác định nguyên nhân và bổ sung kiểm tra, quyền hoặc hướng dẫn.

Xóa một dòng khỏi commit mới không làm credential cũ mất hiệu lực. Việc rewrite Git history cũng không thay thế thu hồi token, vì bản sao có thể đã tồn tại ở fork, clone, log hoặc artifact.

## 9. Bảo vệ secret mà pipeline cần sử dụng

Pipeline có thể cần token để tải dependency private, đẩy artifact hoặc truy cập cloud. Những credential này phải được cấp có kiểm soát.

Nguyên tắc cơ bản:

- Lưu secret trong secret manager hoặc kho bí mật của nền tảng CI.
- Không commit secret vào Git hoặc tệp cấu hình.
- Cấp secret ở job thực sự cần dùng.
- Ưu tiên credential ngắn hạn hoặc workload identity/OIDC khi có thể.
- Tách token đọc dependency khỏi token publish artifact.
- Tách quyền staging và production.
- Giới hạn quyền theo repository, environment, audience và hành động.
- Không truyền secret qua artifact, cache hoặc job output không cần thiết.
- Che giá trị nhạy cảm trong log và không bật debug dump tùy tiện.
- Có quy trình xoay vòng và thu hồi.

Một job SAST hoặc unit test thường không cần credential production. Nếu mọi job đều nhận cùng một bộ secret, một dependency hoặc script bị xâm nhập có thể sử dụng quyền vượt xa mục đích ban đầu.

### 9.1. OIDC và credential ngắn hạn

Khi nền tảng CI và cloud provider hỗ trợ OIDC, job có thể nhận token danh tính ngắn hạn rồi đổi lấy quyền truy cập có phạm vi giới hạn. Điều này giảm nhu cầu lưu access key dài hạn trong CI.

Trust policy cần kiểm tra các thuộc tính như:

- Repository hoặc project được phép.
- Branch hoặc tag được phép.
- Environment đích.
- Workflow hoặc workload identity.
- Audience và thời hạn token.

Không nên chỉ cho phép mọi repository trong tổ chức nhận quyền cloud. Cần giới hạn danh tính theo đúng pipeline và môi trường.

## 10. Ranh giới tin cậy của pull request và runner

Mã trong pull request có thể chưa được tin cậy, đặc biệt khi đến từ fork hoặc cộng tác viên bên ngoài. Một workflow có quyền secret mà chạy script do pull request sửa có thể làm lộ credential.

Các nguyên tắc:

- Job chạy mã từ fork không nhận secret nhạy cảm.
- Dùng permission tối thiểu, thường chỉ cần đọc source để lint và test.
- Tách job kiểm tra mã chưa tin cậy khỏi job publish hoặc deploy.
- Không dùng cơ chế trigger có quyền cao để thực thi trực tiếp mã pull request chưa được review.
- Review thay đổi workflow, script build và action bên ngoài.
- Pin action/plugin quan trọng theo commit đã kiểm tra khi nền tảng hỗ trợ.
- Ưu tiên runner tạm thời cho job có quyền cao.
- Hủy workspace và credential sau khi job hoàn tất.
- Tách cache giữa nhánh tin cậy và không tin cậy.

Runner là môi trường thực thi mã. Nếu runner được tái sử dụng mà không làm sạch, tiến trình hoặc file còn sót có thể ảnh hưởng lần chạy sau. Job phát hành nên dùng runner có vòng đời ngắn, quyền giới hạn và đường kết nối được kiểm soát.

## 11. Xây dựng quality gate từ kết quả scanner

Scanner tạo finding; quality gate quyết định finding nào ảnh hưởng đến việc hợp nhất hoặc phát hành.

Một chính sách có thể phân loại:

- **BLOCK:** vi phạm có rủi ro cao hoặc điều kiện bắt buộc không đạt.
- **WARN:** cần chú ý nhưng có thể tiếp tục trong phạm vi policy cho phép.
- **INFO:** thông tin phục vụ cải tiến, không chặn luồng.
- **EXEMPTED:** ngoại lệ đã được phê duyệt, có phạm vi và thời hạn.
- **UNKNOWN/ERROR:** scanner không chạy được hoặc không có đủ dữ liệu.

Ví dụ tiêu chí:

| Finding | Cách xử lý thường gặp |
|---|---|
| Secret hợp lệ trong diff hoặc lịch sử mới | BLOCK, thu hồi/rotate và điều tra |
| Dependency có lỗ hổng nghiêm trọng, có thể khai thác trong runtime | BLOCK hoặc yêu cầu giảm thiểu trước release |
| Dependency có CVE nhưng chỉ dùng trong test, không đóng gói | Đánh giá phạm vi; có thể WARN hoặc đưa vào backlog |
| SAST finding có đường dữ liệu tới sink nguy hiểm | BLOCK theo mức độ và chính sách |
| Finding SAST chưa xác minh hoặc có khả năng false positive | Triage, không tự động miễn trừ |
| License bị cấm theo chính sách phân phối | BLOCK trước publish |
| Scanner không truy cập được nguồn dữ liệu | UNKNOWN/ERROR; xử lý theo mức rủi ro và chính sách fail-open/fail-closed |

Không nên dùng một ngưỡng CVSS duy nhất cho mọi trường hợp. Cần kết hợp mức độ, khả năng khai thác, phạm vi ảnh hưởng, tính phơi bày và khả năng khắc phục.

### 11.1. Khi scanner lỗi hoặc thiếu dữ liệu

Scanner có thể lỗi do timeout, license hết hạn, nguồn dữ liệu CVE không truy cập được hoặc cấu hình sai. Không nên biến lỗi công cụ thành kết quả PASS.

Có thể xác định policy riêng:

- Release production: yêu cầu các scan bắt buộc có kết quả hợp lệ.
- Pull request không nhạy cảm: có thể cho một số kiểm tra advisory tiếp tục nhưng phải ghi trạng thái UNKNOWN.
- Secret scanning hoặc kiểm tra quyền quan trọng: có thể chặn khi không thể xác minh.
- Ngoại lệ tạm thời: phải có owner, lý do, phạm vi và thời hạn.

Điểm quan trọng là phân biệt "không tìm thấy lỗi" với "không kiểm tra được".

## 12. Triage, sửa lỗi và quản lý ngoại lệ

Một finding cần được quản lý như công việc có chủ sở hữu, thay vì chỉ xuất hiện trong dashboard.

Quy trình triage:

1. Xác minh finding có đúng với mã hoặc package hiện tại không.
2. Xác định component, phiên bản, vị trí và phạm vi ảnh hưởng.
3. Đánh giá khả năng khai thác và tác động.
4. Xác định bản sửa, bản nâng cấp hoặc biện pháp giảm thiểu.
5. Gán owner và thời hạn.
6. Cập nhật dependency, mã nguồn hoặc cấu hình.
7. Chạy lại scan và test liên quan.
8. Lưu bằng chứng đã xử lý.

Ngoại lệ chỉ nên dùng khi có lý do được đánh giá, chẳng hạn chưa có bản sửa tương thích hoặc finding không áp dụng với cách sử dụng thực tế. Một ngoại lệ tốt cần ghi:

- Finding hoặc quy tắc được miễn.
- Component, repository và phiên bản bị ảnh hưởng.
- Lý do và bằng chứng.
- Người phê duyệt.
- Biện pháp giảm thiểu.
- Ngày hết hạn hoặc thời điểm đánh giá lại.

Không nên dùng allowlist toàn cục để làm biến mất một finding ở mọi repository. Ngoại lệ cần có phạm vi hẹp và có thể truy vết.

## 13. Bằng chứng bảo mật gắn với artifact

Kết quả scan chỉ có ý nghĩa với đúng nội dung đã được quét. Nếu pipeline quét commit A rồi build lại từ commit B hoặc tạo image khác, kết quả trước đó không chứng minh cho artifact mới.

Mỗi release nên gắn:

- Commit SHA và repository.
- Pipeline run ID.
- Phiên bản scanner và ruleset.
- Thời điểm và trạng thái SAST.
- Dependency graph, lockfile và kết quả SCA.
- SBOM của artifact.
- Secret scan status và phạm vi đã quét.
- Danh sách ngoại lệ còn hiệu lực.
- Artifact digest.
- Provenance và chữ ký nếu có.

Bằng chứng này giúp trả lời: artifact nào đã được quét, bằng quy tắc nào, finding nào được chấp nhận và ai đã phê duyệt ngoại lệ.

SBOM hỗ trợ theo dõi thành phần trong artifact. Provenance cho biết artifact được tạo từ commit và builder nào. Kết hợp chúng với kết quả SCA giúp nhóm xác định nhanh phiên bản đang chạy có bị ảnh hưởng khi một lỗ hổng mới được công bố hay không.

## 14. Ví dụ pipeline kiểm tra tích hợp

Ví dụ dưới đây là **mã giả trung lập nền tảng** để minh họa quan hệ giữa các job. Tên lệnh và schema thực tế cần điều chỉnh theo scanner và nền tảng CI đang sử dụng.

~~~yaml
events:
  pull_request:
    permissions:
      source: read
      secrets: none
    jobs:
      - secret_scan_diff
      - sast_changed_code
      - sca_lockfiles
      - unit_tests

  push_to_protected_branch:
    jobs:
      - secret_scan_repository
      - sast_full
      - sca_full_dependency_graph
      - build
      - test

pipeline:
  security_gate:
    requires:
      - secret_scan_passed
      - sast_policy_passed
      - sca_policy_passed
      - test_passed
    on_missing_result: UNKNOWN

  publish:
    depends_on: security_gate
    outputs:
      - immutable_artifact
      - artifact_digest
      - sbom
      - provenance

  release_gate:
    requires:
      - artifact_scan_passed
      - signature_or_provenance_verified
      - approved_exceptions_current

  deploy:
    depends_on: release_gate
    credentials:
      source: short_lived_identity
      scope: target_environment
~~~

Mã giả thể hiện một số nguyên tắc:

- Pull request không nhận secret.
- Kiểm tra mã nguồn, dependency và secret có thể chạy song song.
- Gate tổng hợp kết quả và phân biệt thiếu dữ liệu với đạt.
- Publish chỉ chạy sau gate bắt buộc.
- Release kiểm tra đúng artifact và metadata.
- Credential triển khai được cấp ngắn hạn và giới hạn theo môi trường.

Trong hệ thống thực tế, cần bảo đảm job publish và deploy không thể được gọi bằng một đường đi bỏ qua gate. Các rule bắt buộc cũng cần được bảo vệ ở nền tảng Git và CI.

## 15. Ví dụ luồng cho dự án Java

Giả sử một dịch vụ Java dùng Maven, có dependency nội bộ và công khai.

Khi mở pull request:

1. Secret scanner quét diff và kiểm tra secret mới.
2. SAST phân tích mã Java thay đổi và các luồng dữ liệu liên quan.
3. SCA đọc POM và dependency graph để phát hiện CVE và license.
4. Unit test và integration test chạy.
5. Gate đánh giá finding mới, mức độ và ngoại lệ.
6. Nếu đạt, pull request mới được phép hợp nhất.

Sau khi merge:

1. Pipeline quét toàn repository và dependency graph đầy đủ.
2. Maven build từ commit xác định.
3. Artifact JAR được scan và kiểm tra nội dung.
4. Pipeline tạo SBOM, provenance và digest.
5. Artifact được publish vào repository bất biến.
6. Release pipeline xác minh lại metadata trước khi promote.
7. Production nhận đúng artifact digest đã được phê duyệt.

Ví dụ lệnh hỗ trợ kiểm tra dependency:

~~~bash
./mvnw -B dependency:tree
./mvnw -B verify
~~~

Dependency tree giúp hiểu phiên bản trực tiếp và bắc cầu; verify chạy các bước build và test được cấu hình trong Maven lifecycle. Cần thêm scanner chuyên dụng để kiểm tra CVE, license, SAST và secret. Hai lệnh trên không tự chứng minh ứng dụng an toàn.

## 16. Các lỗi triển khai kiểm tra bảo mật thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ chạy scanner trước release | Lỗi được phát hiện muộn và khó sửa | Quét sớm trên pull request và quét lại trước release |
| Chỉ kiểm tra dependency trực tiếp | Bỏ sót lỗ hổng bắc cầu | Quét dependency graph và SBOM |
| Xem CVSS là quyết định duy nhất | Không phản ánh khả năng khai thác trong ứng dụng | Kết hợp reachability, exposure và tác động |
| Secret scan chỉ trên file hiện tại | Secret trong Git history vẫn tồn tại | Quét lịch sử và thu hồi credential |
| Xóa secret khỏi mã nhưng không rotate | Credential cũ vẫn có thể sử dụng | Thu hồi hoặc xoay vòng ngay |
| Mọi job đều nhận secret production | Tăng tác động khi job bị xâm nhập | Cấp secret theo job và environment |
| Mã từ fork được chạy với quyền cao | Pull request có thể đánh cắp credential | Tách trust boundary và bỏ secret khỏi job đó |
| Bỏ qua finding bằng allowlist rộng | Rủi ro bị che trên nhiều dự án | Ngoại lệ hẹp, có owner và expiry |
| Scanner lỗi nhưng pipeline vẫn xanh | Không có bằng chứng kiểm tra | Ghi UNKNOWN/ERROR và áp dụng policy rõ ràng |
| Scan một artifact rồi publish artifact khác | Bằng chứng không khớp sản phẩm | Scan và publish cùng digest |
| Không lưu phiên bản scanner/ruleset | Khó tái hiện quyết định gate | Ghi tool version, ruleset và thời điểm |

## 17. Checklist tích hợp SAST, SCA và secret scanning

**Mã nguồn**

- [ ] SAST chạy trên pull request và có lịch quét toàn repository.
- [ ] Quy tắc phù hợp với ngôn ngữ và framework.
- [ ] Finding có vị trí, mức độ và hướng sửa.
- [ ] Có quy trình triage false positive và ngoại lệ.
- [ ] Các kiểm tra bắt buộc được bảo vệ ở nhánh chính.

**Dependency**

- [ ] Quét dependency trực tiếp và bắc cầu.
- [ ] Lockfile được review và commit.
- [ ] Package đến từ nguồn được kiểm soát.
- [ ] Có vulnerability và license policy.
- [ ] Có SBOM gắn với artifact.
- [ ] Có quét định kỳ để phát hiện CVE mới.

**Thông tin bí mật**

- [ ] Secret scan chạy trên diff, repository và phạm vi lịch sử phù hợp.
- [ ] Có kiểm tra artifact, image hoặc log khi cần.
- [ ] Secret thật không nằm trong Git, cache hoặc output.
- [ ] Khi phát hiện secret, có quy trình rotate/revoke và điều tra.
- [ ] Ngoại lệ secret có phạm vi nhỏ và được review.

**Pipeline và credential**

- [ ] Pull request từ fork không nhận secret nhạy cảm.
- [ ] Job có permission tối thiểu.
- [ ] Secret chỉ được cấp cho job cần dùng.
- [ ] Ưu tiên OIDC hoặc credential ngắn hạn.
- [ ] Action, plugin và script bên ngoài được review và pin theo chính sách.
- [ ] Runner có vòng đời và cơ chế làm sạch phù hợp.

**Gate và truy vết**

- [ ] BLOCK, WARN, INFO, UNKNOWN và EXEMPTED được định nghĩa.
- [ ] Lỗi scanner không bị hiểu thành PASS.
- [ ] Ngoại lệ có owner, lý do và thời hạn.
- [ ] Finding và kết quả scan gắn với commit, pipeline run và artifact digest.
- [ ] Artifact được publish chính là artifact đã được kiểm tra.

## 18. Kết luận

Tích hợp SAST, SCA và secret scanning giúp CI/CD kiểm tra ba nguồn rủi ro quan trọng: mã do nhóm viết, thành phần bên ngoài và thông tin xác thực. Các kiểm tra cần được đặt ở nhiều thời điểm: phản hồi nhanh trên pull request, quét đầy đủ sau merge, quét lại dependency theo lịch và xác minh artifact trước khi phát hành.

Một quy trình đáng tin cậy không chỉ chạy scanner mà còn phân biệt kết quả đạt, vi phạm, cảnh báo và trạng thái không thể kiểm tra. Credential cần được cấp theo ranh giới tin cậy, secret bị lộ phải được thu hồi hoặc xoay vòng, và mọi finding hoặc ngoại lệ cần có chủ sở hữu cùng bằng chứng. Khi kết quả bảo mật gắn với commit và digest của artifact, nhóm có thể giải thích vì sao một thay đổi được phép đi tiếp và kiểm soát rủi ro trong toàn bộ vòng đời phát hành.
