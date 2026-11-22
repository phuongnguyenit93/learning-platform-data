# Phân biệt sản phẩm build với mã nguồn và tệp tạm

## 1. Vì sao cần phân biệt các loại đầu ra?

Một lần build có thể tạo ra rất nhiều tệp: file JAR, container image, file đã biên dịch, mã nguồn được sinh tự động, báo cáo kiểm thử, log, cache và các thư mục làm việc trung gian. Những tệp này không có cùng vai trò. Có tệp là đầu vào để tạo phần mềm, có tệp là sản phẩm có thể triển khai, có tệp chỉ phục vụ chẩn đoán và có tệp chỉ tồn tại trong lúc build.

Nếu không phân biệt rõ, pipeline CI/CD dễ gặp những vấn đề như:

- Đưa nhầm mã nguồn hoặc tệp tạm lên môi trường production.
- Lưu toàn bộ workspace làm artifact khiến dung lượng tăng và khó xác định tệp nào được phát hành.
- Triển khai một file build cũ còn sót lại từ lần chạy trước.
- Mỗi môi trường build lại theo cách khác nhau nên sản phẩm staging không giống production.
- Không thể truy ngược một bản phát hành về commit và lần build đã tạo ra nó.
- Cache hoặc tệp log chứa dữ liệu nhạy cảm bị đóng gói vào artifact.
- Khi cần rollback, nhóm không còn artifact trước đó và phải build lại từ mã nguồn.

Vì vậy, cần phân biệt ít nhất bốn nhóm: **mã nguồn**, **đầu ra build**, **artifact phát hành** và **tệp tạm**. Đây là nền tảng để kiểm soát những gì được lưu, kiểm thử, ký, chuyển giữa môi trường và triển khai.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, mục tiêu là thiết kế luồng phát hành có truy vết từ sự kiện Git, pipeline dưới dạng mã, build và kiểm thử tự động đến quản lý artifact, môi trường, cổng chất lượng, bảo vệ bí mật, xác minh sau triển khai và khả năng quay lui. Việc xác định đúng sản phẩm build giúp mỗi bước trong luồng có đầu vào và đầu ra rõ ràng.

## 2. Bốn khái niệm cần phân biệt

| Nhóm | Bản chất | Ví dụ | Vai trò |
|---|---|---|---|
| Mã nguồn (source) | Nội dung con người hoặc công cụ duy trì để mô tả phần mềm | Java, TypeScript, cấu hình, tài liệu, script build | Đầu vào được quản lý bằng Git |
| Đầu ra build (build output) | Tệp được tạo ra trong quá trình biên dịch, đóng gói hoặc kiểm thử | Class, JAR, bundle frontend, image, báo cáo test | Có thể là sản phẩm cuối hoặc chỉ là đầu ra trung gian |
| Artifact phát hành (release artifact) | Đầu ra đã được chọn, xác minh, định danh và lưu để phân phối hoặc triển khai | JAR đã kiểm thử, container image theo digest, package đã ký | Đơn vị được promote qua môi trường và triển khai |
| Tệp tạm (temporary file) | Dữ liệu phục vụ một bước xử lý và không cần tồn tại như sản phẩm lâu dài | File trung gian, thư mục giải nén, socket, file scratch, cache cục bộ | Có thể xóa sau khi công việc hoàn tất |

Không phải mọi build output đều là release artifact. Một thư mục build có thể chứa cả file cần phát hành lẫn báo cáo, file trung gian, metadata và tệp debug. Pipeline cần chọn chính xác đầu ra nào được publish.

Một số loại tệp có vai trò đặc biệt:

- **Mã nguồn được sinh tự động:** có thể là đầu vào cho bước biên dịch tiếp theo, nhưng thường được tạo từ schema hoặc mã nguồn gốc. Cần quyết định có lưu trong Git hay tái tạo trong build.
- **Báo cáo kiểm thử và scan:** là bằng chứng của chất lượng, thường được lưu như artifact phục vụ kiểm toán nhưng không phải sản phẩm triển khai.
- **Source archive:** là gói mã nguồn được đóng gói để phân phối hoặc đáp ứng yêu cầu phát hành. Nó vẫn là artifact, nhưng khác với binary dùng để chạy ứng dụng.
- **Debug symbols:** có thể cần cho việc chẩn đoán production, nhưng cần quản lý quyền và retention riêng.
- **Cache:** là dữ liệu tối ưu hiệu năng, không phải bằng chứng nguồn gốc hay bản phát hành chính thức.

## 3. Mã nguồn là đầu vào có lịch sử, artifact là đầu ra có định danh

Mã nguồn thường được quản lý trong Git. Một commit xác định trạng thái nội dung tại một thời điểm và cung cấp lịch sử thay đổi, tác giả, review và quan hệ với pull request.

Artifact là kết quả của một quy trình build cụ thể. Nó phụ thuộc vào nhiều yếu tố ngoài mã nguồn:

- Commit hoặc source tree đầu vào.
- Phiên bản compiler, runtime và build tool.
- Dependency trực tiếp và bắc cầu.
- Cấu hình build, profile và feature flag ở thời điểm build.
- Hệ điều hành, kiến trúc và môi trường thực thi của builder.
- Biến môi trường được phép ảnh hưởng đến build.
- Script, plugin và action được pipeline sử dụng.

Vì vậy, biết commit chưa chắc đã đủ để tái tạo chính xác artifact. Ngược lại, có một file JAR mà không biết commit và môi trường build cũng chưa đủ để tin cậy nó.

Mối liên hệ cần được lưu lại:

~~~mermaid
flowchart TD
    A["Git commit và source tree"] --> B["Pipeline run"]
    C["Toolchain và build configuration"] --> B
    D["Dependency graph đã giải quyết"] --> B
    B --> E["Build output"]
    E --> F["Test và security checks"]
    F --> G{"Đạt quality gate?"}
    G -- "Không" --> H["Giữ báo cáo, sửa lỗi"]
    G -- "Có" --> I["Chọn release artifact"]
    I --> J["Digest, metadata và provenance"]
    J --> K["Artifact repository"]
    K --> L["Promote cùng artifact"]
    L --> M["Deploy và verify"]
~~~

Mỗi lần build cần có định danh riêng. Ví dụ, cùng một commit có thể được build lại với toolchain mới, dependency khác hoặc tham số khác. Không nên chỉ dùng commit SHA làm tên artifact rồi ghi đè đầu ra cũ.

## 4. Build output được tạo ở đâu?

Mỗi build tool có quy ước thư mục đầu ra khác nhau. Điều quan trọng là pipeline phải biết đâu là sản phẩm cần publish và đâu là dữ liệu trung gian.

| Hệ sinh thái/công cụ | Thư mục hoặc đầu ra thường gặp | Lưu ý |
|---|---|---|
| Maven | target/ | Có JAR/WAR, class, generated source, report và file trung gian |
| Gradle | build/ | Có archive, class, reports, cache và output của task |
| Node.js | dist/, build/ | Có thể là bundle triển khai hoặc output của một bước build |
| .NET | bin/, obj/ | bin có output; obj thường chứa dữ liệu trung gian |
| Go | Binary do lệnh build tạo ra | Cần xác định tên, kiến trúc và thư mục đích |
| Docker/BuildKit | Container image hoặc OCI layout | Image cần được gắn tag và digest trong registry |
| Terraform | Plan file; state được quản lý riêng | Plan có thể chứa dữ liệu nhạy cảm; state phải được lưu trong backend bảo vệ, không coi là artifact ứng dụng |

Các thư mục trên chỉ là quy ước phổ biến, không phải cam kết rằng mọi file trong đó đều là artifact phát hành.

Ví dụ với Maven, thư mục target có thể chứa:

- File JAR chính của ứng dụng.
- File JAR nguồn hoặc Javadoc.
- Class đã biên dịch.
- Mã nguồn được sinh.
- Báo cáo Surefire hoặc Failsafe.
- File tạm do plugin tạo ra.

Nếu pipeline upload toàn bộ target, người nhận có thể không biết file nào là gói triển khai. Tốt hơn là chọn chính xác file JAR hoặc WAR đã được xác minh, sau đó lưu báo cáo test riêng.

Với Gradle, thư mục build có thể chứa nhiều output từ các task khác nhau. Cần xác định task tạo archive phát hành và dùng output của task đó thay vì nén toàn bộ thư mục build.

## 5. Artifact phát hành phải có hợp đồng rõ ràng

Một artifact được coi là sẵn sàng phát hành khi nhóm biết chính xác:

1. Nó là loại sản phẩm gì và dùng để làm gì.
2. Được tạo từ commit và pipeline run nào.
3. Được build bằng toolchain và dependency nào.
4. Đã vượt qua những kiểm tra nào.
5. Được lưu ở đâu và định danh bằng giá trị nào.
6. Ai hoặc hệ thống nào được phép publish và deploy.
7. Cách xác minh nội dung và nguồn gốc.
8. Thời gian lưu giữ và quy trình thu hồi.
9. Có thể triển khai hoặc khôi phục bằng cách nào.

Có thể định nghĩa một hợp đồng artifact cho dịch vụ như sau:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| Artifact name | Tên sản phẩm | checkout-service |
| Version | Phiên bản con người đọc được | 2.8.1 |
| Type | Định dạng | JAR, OCI image, ZIP |
| Source revision | Commit nguồn | Git commit SHA |
| Build run | Lần chạy pipeline | CI run identifier |
| Digest | Định danh nội dung bất biến | SHA-256 hoặc OCI digest |
| Provenance | Bằng chứng quá trình tạo | Builder, source, parameters |
| SBOM | Danh sách thành phần | SPDX hoặc CycloneDX |
| Test evidence | Bằng chứng kiểm tra | Unit, integration, security reports |
| Storage location | Kho lưu trữ | Maven repository hoặc container registry |

Không phải dự án nào cũng cần mọi trường ở cùng mức chi tiết. Tuy nhiên, tên, phiên bản, nguồn commit, pipeline run và digest là những thông tin cơ bản để truy vết artifact.

## 6. Định danh artifact: version, tag và digest

Tên phiên bản giúp con người nhận biết sản phẩm. Digest giúp xác định chính xác nội dung.

Ví dụ:

- Version: 2.8.1
- Image tag: checkout-service:2.8.1
- Image digest: sha256:...

Tag có thể được gắn lại hoặc ghi đè tùy chính sách registry. Digest được tính từ nội dung image và thay đổi khi nội dung thay đổi. Vì vậy, trong luồng triển khai cần ưu tiên digest hoặc định danh bất biến tương đương.

Với package Maven hoặc file ZIP, có thể lưu checksum SHA-256 cùng artifact. Khi tải về, pipeline hoặc hệ thống triển khai tính lại checksum và so sánh với metadata đã lưu.

Một số nguyên tắc:

- Không tái sử dụng version release đã công bố cho nội dung khác.
- Không ghi đè artifact phát hành.
- Gắn digest với release record.
- Lưu tag phục vụ con người cùng digest phục vụ xác minh.
- Xác minh checksum sau khi tải hoặc sao chép giữa các kho.
- Khi một bản build lại tạo ra digest khác, lưu nó như một lần build mới và điều tra nguyên nhân.

Digest chỉ xác định nội dung. Nó không tự chứng minh ai đã tạo artifact hoặc quy trình có đáng tin cậy hay không. Cần kết hợp provenance, chữ ký và chính sách builder.

## 7. Phân biệt artifact, cache và workspace

Ba khái niệm này thường bị nhầm vì đều chứa tệp được tạo trong lúc build.

| Khái niệm | Mục đích | Vòng đời | Có dùng để triển khai? |
|---|---|---|---|
| Workspace | Không gian làm việc của job CI | Thường chỉ trong một lần chạy | Không trực tiếp |
| Cache | Giữ dữ liệu có thể tái sử dụng để tăng tốc | Có thể tồn tại qua nhiều lần chạy và bị xóa | Không |
| Artifact | Lưu đầu ra hoặc bằng chứng của một lần chạy | Theo retention và chính sách phát hành | Có, nếu được phân loại là deployable artifact |

Workspace có thể chứa mã nguồn checkout, dependency đã tải, file tạm và output. Cache có thể chứa dependency hoặc dữ liệu build được tái sử dụng. Artifact cần được chọn lọc, định danh và lưu theo mục đích.

Không nên upload workspace hoặc cache như thể chúng là sản phẩm phát hành. Làm vậy có thể:

- Đưa secret hoặc credential vào kho artifact.
- Đưa file cũ từ lần chạy trước vào package.
- Tăng dung lượng lưu trữ.
- Làm artifact không thể tái tạo hoặc khó kiểm tra.
- Khiến người triển khai chọn nhầm file.

Cần làm sạch workspace trước build nếu runner được tái sử dụng và bảo đảm pipeline không lấy output còn sót từ lần chạy trước.

## 8. Artifact ứng dụng và artifact bằng chứng

Không phải artifact nào cũng được triển khai. Nên phân loại rõ để retention và quyền truy cập phù hợp.

| Loại artifact | Ví dụ | Người hoặc hệ thống sử dụng |
|---|---|---|
| Deployable artifact | JAR, WAR, container image, frontend bundle | Release pipeline và môi trường chạy |
| Test evidence | JUnit XML, coverage report, integration test log | Nhóm phát triển và quality gate |
| Security evidence | SAST, dependency scan, container scan, SBOM | Nhóm bảo mật và kiểm toán |
| Build metadata | Build manifest, toolchain version, dependency graph | Điều tra và tái tạo |
| Source package | Source archive hoặc package mã nguồn | Người nhận source distribution |
| Debug artifact | Symbol file, crash dump đã làm sạch | Nhóm điều tra sự cố |

Bằng chứng kiểm thử cần được gắn với cùng commit và build run đã tạo deployable artifact. Nếu test chạy trên một build nhưng pipeline publish một build khác, báo cáo test không chứng minh chất lượng của artifact được phát hành.

Với báo cáo chứa dữ liệu nhạy cảm, cần giới hạn quyền đọc và thời gian lưu. Log test có thể chứa URL nội bộ, dữ liệu test hoặc thông tin xác thực bị in nhầm.

## 9. Build một lần, promote cùng artifact

Một nguyên tắc quan trọng của CI/CD là build artifact một lần rồi đưa chính artifact đó qua các môi trường.

Luồng đề xuất:

1. Pipeline lấy mã nguồn từ commit xác định.
2. Resolve dependency từ nguồn được kiểm soát.
3. Build package hoặc image.
4. Chạy test và scan trên đầu ra cần phát hành.
5. Tính digest và tạo metadata/provenance.
6. Publish artifact vào kho có kiểm soát.
7. Deploy staging bằng digest đó.
8. Xác minh hành vi và chất lượng ở staging.
9. Sau khi đạt điều kiện, promote cùng digest sang production.
10. Ghi release record và xác minh sau triển khai.

Nếu staging và production tự build riêng, có thể xảy ra khác biệt do dependency, toolchain, thời điểm hoặc biến môi trường. Khi đó, việc staging đã kiểm thử thành công không chứng minh artifact production có cùng nội dung.

Cấu hình môi trường nên được cung cấp khi triển khai, theo cơ chế có kiểm soát, thay vì đóng gói bí mật hoặc endpoint production vào artifact. Cùng một image có thể chạy ở staging và production với cấu hình, secret và quyền khác nhau.

~~~mermaid
flowchart LR
    A["Commit đã review"] --> B["Build một lần"]
    B --> C["Test và scan"]
    C --> D{"Quality gate đạt?"}
    D -- "Không" --> E["Sửa và build lại"]
    E --> B
    D -- "Có" --> F["Digest và provenance"]
    F --> G["Artifact repository"]
    G --> H["Deploy staging"]
    H --> I["Verify staging"]
    I --> J{"Được promote?"}
    J -- "Không" --> K["Giữ lại, điều tra"]
    J -- "Có" --> L["Deploy cùng digest production"]
    L --> M["Post-deploy verification"]
~~~

Promotion không cần tạo một artifact mới. Nó thay đổi trạng thái hoặc vị trí sử dụng của cùng một artifact đã được xác minh.

## 10. Lưu trữ artifact trong repository phù hợp

Artifact cần được lưu trong kho phù hợp với loại sản phẩm:

- Maven repository cho JAR, WAR, POM và các package JVM.
- npm registry cho package JavaScript.
- NuGet repository cho package .NET.
- OCI/container registry cho image.
- Generic artifact repository cho ZIP, binary hoặc file phát hành khác.
- Kho báo cáo riêng cho test, scan và evidence.

Một repository manager có thể hỗ trợ proxy, hosted và group repository. Với artifact phát hành, cần tách quyền publish và read. Build job thông thường chỉ cần quyền đọc dependency; job phát hành có quyền ghi vào đúng namespace.

Các thuộc tính cần xem xét:

- Authentication và authorization.
- TLS và bảo vệ dữ liệu lưu trữ.
- Immutability hoặc chính sách không overwrite.
- Retention và cleanup.
- Replication, backup và restore.
- Audit log.
- Scan lỗ hổng và license.
- Metadata và provenance.
- Phân tách snapshot, staging và release repository.

Không nên dùng cùng một quyền ghi cho mọi pipeline. Nếu một job kiểm thử bị xâm nhập, quyền của nó không nên cho phép thay thế artifact release đã công bố.

## 11. Provenance, chữ ký và SBOM

Artifact có thể đúng checksum nhưng vẫn không rõ nguồn gốc. Để tăng niềm tin, cần ghi nhận quy trình tạo và xác minh danh tính.

### 11.1. Provenance

Provenance là thông tin mô tả artifact được tạo từ đâu và bằng cách nào. Một provenance có thể chứa:

- Repository và commit nguồn.
- Builder hoặc danh tính pipeline.
- Pipeline run và thời điểm.
- Tham số hoặc cấu hình build quan trọng.
- Dependency hoặc materials được sử dụng.
- Định danh artifact đầu ra.
- Quan hệ giữa source, build và package.

Provenance giúp trả lời: artifact này có thực sự được tạo bởi pipeline được phép từ commit đã review không?

### 11.2. Chữ ký số

Chữ ký số có thể gắn với artifact hoặc metadata. Hệ thống triển khai xác minh chữ ký trước khi chấp nhận package.

Cần quản lý:

- Khóa ký hoặc danh tính ký.
- Phạm vi hệ thống được phép ký.
- Cách phân phối và tin cậy khóa công khai.
- Xoay vòng và thu hồi khóa.
- Log kết quả xác minh.
- Quy trình xử lý artifact có chữ ký không hợp lệ.

Không nên lưu khóa ký dài hạn trực tiếp trong repository hoặc image. Ưu tiên dịch vụ ký hoặc credential ngắn hạn nếu nền tảng hỗ trợ.

### 11.3. SBOM

SBOM liệt kê các thành phần phần mềm có trong artifact. Nó giúp:

- Xác định artifact nào chứa dependency có lỗ hổng.
- Theo dõi license.
- Hỗ trợ kiểm toán chuỗi cung ứng.
- Lập kế hoạch nâng cấp dependency.
- Liên kết thành phần với sản phẩm đã phát hành.

SBOM cần được tạo từ artifact hoặc dependency graph tương ứng với lần build. Không nên gắn một SBOM của commit khác hoặc build khác vào release record.

## 12. Artifact bất biến và khả năng tái tạo build

Artifact bất biến nghĩa là nội dung đã publish không bị thay đổi tại cùng một định danh phát hành. Nếu cần sửa, pipeline tạo version mới hoặc digest mới.

Điều này giúp:

- Người triển khai biết chính xác nội dung đang chạy.
- Rollback chọn được artifact cũ.
- Audit trail không bị thay đổi ngược.
- Cache và registry không làm thay đổi ý nghĩa của version.
- Có thể đối chiếu digest giữa staging và production.

Reproducible build là khả năng tạo ra cùng nội dung artifact từ cùng đầu vào và điều kiện build đã được kiểm soát. Không phải dự án nào cũng đạt được ngay tính tái lập bit-for-bit, nhưng có thể tăng dần bằng cách:

- Pin toolchain và dependency.
- Dùng lockfile hoặc dependency verification.
- Kiểm soát biến môi trường ảnh hưởng build.
- Chuẩn hóa timestamp và metadata khi công cụ hỗ trợ.
- Tránh tải nội dung động trong quá trình build.
- Lưu build configuration và provenance.
- Dùng builder nhất quán và được quản lý.

Cần phân biệt reproducible build với build lại thành công. Build lại thành công chỉ cho biết quá trình có thể chạy lại; reproducible build yêu cầu đầu ra có thể đối chiếu với kết quả trước đó theo tiêu chí xác định.

## 13. Bảo mật artifact trong suốt vòng đời

Artifact có thể chứa mã độc, lỗ hổng, dữ liệu nhạy cảm hoặc thông tin nội bộ. Bảo mật cần được áp dụng từ lúc tạo đến lúc xóa.

Một số biện pháp:

- Scan dependency và binary trước khi publish.
- Scan container image và kiểm tra base image.
- Kiểm tra secret trong file đóng gói.
- Không đưa file cấu hình môi trường thật vào package.
- Hạn chế quyền đọc artifact nhạy cảm.
- Ký artifact hoặc provenance theo chính sách.
- Dùng digest khi triển khai.
- Theo dõi artifact bị thu hồi hoặc có lỗ hổng.
- Có quy trình cách ly hoặc chặn artifact không còn được phép sử dụng.
- Ghi nhận người hoặc danh tính đã publish, download và deploy.

Nếu phát hiện artifact bị xâm phạm, cần xác định các môi trường đã triển khai digest đó, dừng promotion, đánh giá tác động và phát hành bản thay thế. Xóa tag khỏi registry chưa chắc đã thu hồi được các bản sao đã tải xuống hoặc đang chạy.

## 14. Retention, cleanup và vòng đời artifact

Không nên giữ mọi tệp build mãi mãi, cũng không nên xóa mọi thứ ngay sau pipeline. Chính sách retention cần phân biệt loại artifact và mức độ quan trọng.

| Loại dữ liệu | Chính sách thường cần |
|---|---|
| Release artifact production | Giữ theo vòng đời hỗ trợ, yêu cầu kiểm toán và khả năng rollback |
| Snapshot hoặc development build | TTL ngắn hơn, có cleanup định kỳ |
| Test report | Giữ đủ lâu để review và điều tra lỗi |
| Security report và SBOM | Giữ theo yêu cầu kiểm toán và quản lý lỗ hổng |
| Temporary file | Xóa sau job hoặc khi workspace bị hủy |
| Cache | Có giới hạn dung lượng, TTL và quy trình invalidation |
| Debug symbols | Giữ theo thời gian hỗ trợ chẩn đoán phiên bản |

Trước khi xóa artifact, cần xem xét:

- Nó có đang được môi trường production sử dụng không?
- Có release nào cần nó để rollback không?
- Có yêu cầu lưu giữ từ khách hàng hoặc kiểm toán không?
- Có bản sao dự phòng đã xác minh không?
- Có thể tái tạo từ source và dependency còn tồn tại không?
- Có cần lưu SBOM hoặc provenance lâu hơn binary không?

Cleanup phải tránh xóa artifact đang được tham chiếu bởi release record hoặc deployment hiện hành. Có thể dùng lifecycle policy theo repository, version và trạng thái phát hành.

## 15. Tải và triển khai artifact an toàn

Hệ thống triển khai cần biết artifact nào được phép nhận và cách xác minh nó.

Một quy trình triển khai nên:

1. Nhận artifact identifier hoặc digest từ release record.
2. Kiểm tra repository và namespace nguồn.
3. Xác minh digest sau khi tải.
4. Xác minh chữ ký và provenance theo chính sách.
5. Kiểm tra artifact đã vượt qua các cổng bắt buộc.
6. Lấy cấu hình và secret của môi trường từ nguồn được bảo vệ.
7. Triển khai đúng digest đã được phê duyệt.
8. Ghi lại release ID, digest, môi trường và thời điểm.
9. Xác minh dịch vụ sau triển khai.

Không nên để job deploy tự tìm artifact mới nhất bằng tag chung như latest. Điều đó có thể khiến lần triển khai nhận một nội dung khác với nội dung đã được review hoặc phê duyệt.

Với container image, nên triển khai theo digest. Với JAR hoặc ZIP, lưu checksum trong release metadata và kiểm tra sau khi tải. Với package có chữ ký, xác minh chữ ký trước khi cài hoặc triển khai.

## 16. Artifact và rollback

Rollback cần một artifact trước đó đã được lưu, xác minh và còn tương thích với môi trường.

Khi một release gặp lỗi:

- Xác định digest đang chạy.
- Xác định digest ổn định trước đó.
- Kiểm tra phiên bản schema và dữ liệu.
- Triển khai lại artifact trước đó hoặc thực hiện roll-forward theo runbook.
- Xác minh health, smoke test và chỉ số nghiệp vụ.
- Ghi lại sự kiện rollback và nguyên nhân.

Không nên build lại từ commit cũ trong lúc sự cố rồi mặc định kết quả tương đương. Dependency, toolchain, image base hoặc metadata có thể đã thay đổi. Triển khai lại artifact đã lưu giúp khôi phục đúng nội dung trước đó.

Database migration có thể làm rollback mã nguồn trở nên không an toàn. Nếu phiên bản mới đã thay đổi schema hoặc ghi dữ liệu theo định dạng mới, cần kiểm tra tương thích trước khi đưa artifact cũ trở lại. Một số trường hợp phải roll-forward hoặc phục hồi dữ liệu theo quy trình riêng.

## 17. Ví dụ pipeline phân biệt source, output, report và release artifact

Ví dụ dưới đây là mã giả mô tả cách chọn đầu ra từ một dự án Java. Cú pháp upload artifact cụ thể phụ thuộc nền tảng CI.

~~~yaml
pipeline:
  checkout:
    output:
      - source_tree
      - commit_sha

  build:
    input:
      - source_tree
    outputs:
      - application_jar
      - generated_sources
      - temporary_classes

  test:
    input:
      - application_jar
    outputs:
      - junit_report
      - coverage_report

  security_scan:
    input:
      - application_jar
    outputs:
      - dependency_report
      - sbom

  publish:
    requires:
      - application_jar
      - test_passed
      - security_policy_passed
    publish:
      - immutable_application_jar
      - sbom
      - build_provenance
    exclude:
      - temporary_classes
      - local_cache
      - workspace
      - secret_files

  deploy:
    input:
      - artifact_digest
    verify:
      - checksum
      - provenance
      - release_approval
~~~

Mã giả làm rõ rằng source tree, generated sources, temporary classes, reports và JAR có vòng đời khác nhau. Chỉ JAR đã vượt qua điều kiện mới được chọn làm deployable artifact. Báo cáo và SBOM có thể được lưu riêng như evidence; cache và workspace không được publish như sản phẩm.

### 17.1. Ví dụ với Maven

Một dự án Maven có thể tạo JAR trong target. Pipeline nên tham chiếu chính xác file JAR phát hành thay vì upload toàn bộ target. Ví dụ lệnh kiểm tra file:

~~~powershell
mvn -B clean verify
Get-ChildItem target -Filter "*.jar"
~~~

Lệnh thứ hai là ví dụ PowerShell để liệt kê JAR; trong runner Linux có thể dùng lệnh tương đương. Không nên giả định tên file nếu dự án có nhiều module hoặc tạo nhiều classifier. Hãy xác định artifact bằng cấu hình build và metadata của dự án.

### 17.2. Ví dụ với Gradle

Với Gradle, task archive tạo JAR có thể được truy xuất thông qua output của task. Pipeline nên dùng output task hoặc pattern đã được xác nhận, thay vì nén cả thư mục build.

~~~bash
./gradlew clean build
./gradlew tasks --all
~~~

Task build có thể tạo test report và các đầu ra khác. Cần kiểm tra task graph và cấu hình archive để xác định file nào là release artifact. Với multi-project build, nên xác định module và variant cụ thể.

## 18. Đo lường chất lượng quản lý artifact

Có thể theo dõi một số chỉ số để đánh giá artifact pipeline:

- Tỷ lệ build tạo được artifact hợp lệ.
- Tỷ lệ artifact có đầy đủ commit, run ID, digest và provenance.
- Thời gian từ build đến publish.
- Tỷ lệ deploy dùng đúng digest đã được phê duyệt.
- Số lần artifact bị từ chối do scan hoặc policy.
- Tỷ lệ lỗi tải artifact từ repository.
- Thời gian khôi phục khi cần rollback.
- Dung lượng artifact theo loại và tuổi.
- Số artifact không còn được tham chiếu nhưng chưa cleanup.
- Số lần build lại cùng commit tạo ra digest khác.

Chỉ số cần giúp tìm vấn đề, không nên trở thành mục tiêu làm đẹp báo cáo. Ví dụ, giảm dung lượng bằng cách xóa mọi artifact cũ có thể làm mất khả năng rollback. Tăng tỷ lệ publish bằng cách bỏ qua scan sẽ làm suy yếu chất lượng.

## 19. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Coi toàn bộ thư mục build là artifact | Lẫn sản phẩm, report và tệp tạm | Chọn chính xác đầu ra cần publish |
| Triển khai trực tiếp từ workspace | Khó truy vết và dễ dùng file sót | Publish artifact rồi triển khai từ repository |
| Dùng tag latest làm định danh duy nhất | Nội dung có thể thay đổi | Lưu version và digest |
| Build lại ở từng môi trường | Staging và production có thể khác nhau | Build một lần, promote cùng artifact |
| Ghi đè release artifact | Mất tính bất biến và audit trail | Tạo version hoặc digest mới |
| Không lưu provenance | Khó xác minh nguồn gốc | Gắn commit, builder và pipeline run |
| Đưa secret vào package | Bí mật có thể phát tán qua registry | Inject cấu hình và secret khi deploy |
| Cache được xem như artifact | Không bảo đảm nội dung hoặc nguồn gốc | Tách cache, workspace và release storage |
| Không có retention policy | Mất khả năng rollback hoặc tốn dung lượng | Retention theo loại và trạng thái |
| Rollback bằng cách build lại mã cũ | Đầu ra có thể không giống phiên bản trước | Triển khai lại artifact đã lưu và xác minh |

## 20. Checklist trước khi publish artifact

**Phân loại và lựa chọn đầu ra**

- [ ] Mã nguồn, build output, report, cache và temporary file được phân biệt.
- [ ] Đã xác định chính xác file hoặc image được phát hành.
- [ ] Không upload toàn bộ workspace nếu không có lý do.
- [ ] Artifact không chứa secret hoặc cấu hình môi trường nhạy cảm.
- [ ] Report và SBOM được lưu như evidence riêng.

**Định danh và truy vết**

- [ ] Artifact có tên, version và type rõ ràng.
- [ ] Có commit SHA và pipeline run ID.
- [ ] Có digest hoặc checksum.
- [ ] Có provenance phù hợp với mức rủi ro.
- [ ] Có SBOM hoặc dependency report theo yêu cầu.
- [ ] Kết quả test và scan gắn với cùng lần build.

**Lưu trữ và bảo mật**

- [ ] Artifact được publish vào repository phù hợp.
- [ ] Quyền đọc và ghi được phân tách.
- [ ] Release artifact không bị overwrite.
- [ ] Có TLS, authentication và audit trail.
- [ ] Có retention, backup và cleanup policy.
- [ ] Artifact có thể được xác minh sau khi tải.

**Triển khai và khôi phục**

- [ ] Staging và production dùng cùng digest.
- [ ] Release record xác định artifact được phê duyệt.
- [ ] Có xác minh sau triển khai.
- [ ] Có artifact trước đó để rollback.
- [ ] Tương thích database và dữ liệu đã được xem xét.

## 21. Kết luận

Mã nguồn mô tả phần mềm và được quản lý theo lịch sử Git. Build output là những gì công cụ tạo ra, nhưng có thể gồm sản phẩm, báo cáo và tệp trung gian. Release artifact là đầu ra đã được chọn lọc, xác minh, định danh và lưu để phân phối hoặc triển khai. Temporary file chỉ phục vụ một bước xử lý và không nên bị nhầm với sản phẩm phát hành.

Khi pipeline xác định chính xác artifact, gắn nó với commit, build run, digest, provenance và kết quả kiểm tra, nhóm có thể build một lần, promote cùng một nội dung qua các môi trường và rollback có kiểm soát. Đây là cơ sở để phát hành có truy vết, bảo vệ chuỗi cung ứng và duy trì khả năng tái tạo phần mềm.
