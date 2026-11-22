# Kiểm soát nguồn cung thư viện, extension và image container

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở chương **Bảo mật**, kiểm soát nguồn cung thư viện, extension và image container giúp bảo đảm tiến trình migration chỉ chạy những thành phần đã được xác minh, có nguồn gốc rõ ràng và được cập nhật theo chính sách bảo mật.

Một Liquibase runner có quyền đọc credential database và thực thi DDL/DML. Vì vậy, thư viện, JDBC driver, extension, script cài đặt hoặc image bị thay thế có thể làm lộ secret, sửa schema, đọc dữ liệu hoặc gửi thông tin ra ngoài. Một changelog được review kỹ vẫn có thể bị thực thi bằng runtime đã bị cài cắm nếu dependency hoặc container image không đáng tin cậy.

Mục tiêu là kiểm soát toàn bộ chuỗi từ mã nguồn đến môi trường chạy:

1. Chỉ lấy dependency và image từ nguồn đã phê duyệt.
2. Khóa phiên bản và xác minh tính toàn vẹn của dependency trực tiếp lẫn bắc cầu.
3. Kiểm tra lỗ hổng, giấy phép và nguồn gốc build.
4. Tạo SBOM, provenance và chữ ký cho artifact.
5. Đóng gói Liquibase cùng extension/JDBC driver trong image bất biến.
6. Chỉ triển khai artifact đã được xác minh, với secret và quyền database tối thiểu.

## 1. Chuỗi cung ứng phần mềm của một lần migration

Một lần migration production thường đi qua nhiều thành phần:

~~~text
Source repository
  | changelog, SQL, extension source, build config
  v
Build system
  | Maven/Gradle, plugins, dependency resolver
  v
Package repository
  | Liquibase core, JDBC driver, extensions, libraries
  v
Build artifact
  | migration bundle / JAR / container image
  v
Security checks
  | tests, SCA, SBOM, provenance, signature
  v
Artifact registry
  | immutable version + digest
  v
CI/CD deployment runner
  | verify signature + policy + secret injection
  v
Liquibase process
  | changelog + extensions + JDBC driver
  v
Target database
  | DATABASECHANGELOG + schema + data
~~~

Mỗi mũi tên là một ranh giới tin cậy. Nếu build agent tải nhầm package, registry cho phép ghi đè artifact, image tag trỏ sang nội dung mới hoặc runner nhận secret từ pull request không đáng tin cậy, kiểm soát ở bước review changelog không đủ bảo vệ hệ thống.

### 1.1. Thành phần nào có thể tác động đến database?

| Thành phần | Vai trò | Rủi ro nếu bị thay thế |
|---|---|---|
| Liquibase core/CLI | Đọc changelog, điều phối changeset, ghi metadata | Thay đổi cách diễn giải hoặc thực thi migration |
| JDBC driver | Tạo kết nối và gửi lệnh tới DBMS | Đọc/ghi dữ liệu, lạm dụng kết nối hoặc thực thi hành vi không mong muốn |
| Liquibase extension | Bổ sung change type, precondition, parser hoặc executor | Chạy code tùy chỉnh trong tiến trình migration |
| Thư viện bắc cầu | Hỗ trợ runtime và extension | Lỗ hổng hoặc hành vi không mong muốn được kéo vào gián tiếp |
| Build plugin/action | Resolve, compile, package, scan hoặc publish | Có thể đọc secret, sửa artifact hoặc phát hành gói giả |
| Container base image | Cung cấp OS/JRE/công cụ nền | Có thể chứa binary độc hại hoặc lỗ hổng hệ điều hành |
| Changelog và SQL | Mô tả thay đổi database | Có thể phá hủy dữ liệu hoặc cấp quyền quá rộng |
| Deployment runner | Cấp secret và kết nối môi trường | Có thể làm lộ credential hoặc chạy nhầm target |

Một extension được nạp trong cùng JVM với Liquibase thường có quyền của tiến trình đó. Không nên coi extension là một cấu hình dữ liệu thụ động. Hãy review và xác minh nó như một thư viện thực thi có khả năng truy cập filesystem, network, environment và database connection mà runner được cấp.

## 2. Xác định ranh giới tin cậy và threat model

Trước khi chọn công cụ scan, hãy xác định tài sản cần bảo vệ và đối tượng có thể tác động.

**Tài sản quan trọng:**

- Credential migration và runtime database.
- Dữ liệu, schema, metadata và audit history.
- Changelog, SQL, CSV và release artifact.
- Khóa ký artifact, token registry và secret của CI/CD.
- Build agent, container registry và deployment runner.
- Tính toàn vẹn của DATABASECHANGELOG và nội dung changeset.

**Các tình huống cần tính đến:**

- Package giả mạo có tên gần giống dependency thật.
- Dependency bắc cầu chứa CVE hoặc được thay bằng bản độc hại.
- Repository proxy bị cấu hình sai hoặc bị chiếm quyền.
- Build plugin/action tải script không được review.
- Extension mới có quyền đọc credential hoặc gửi dữ liệu ra network.
- Image tag bị ghi đè sau khi staging đã kiểm thử.
- Pull request từ fork đọc được secret của pipeline.
- Artifact được publish mà không có SBOM/provenance hoặc chữ ký.
- Runner có quyền Docker socket, host mount hoặc quyền root không cần thiết.
- Log chứa URL, username, password, SQL literal hoặc dữ liệu nhạy cảm.

### 2.1. Đánh giá theo khả năng gây tác động

Không phải mọi lỗ hổng trong một dependency đều có cùng mức rủi ro. Cần xem:

- Dependency có thực sự được đưa vào runtime migration không?
- Code bị ảnh hưởng có được gọi bởi Liquibase hoặc extension không?
- Runner có network egress tới đâu?
- Credential có quyền DDL trên database nào?
- Artifact có chạy trên production hay chỉ dùng ở test?
- Có exploit công khai, điều kiện khai thác và biện pháp giảm thiểu nào?
- Có thể nâng cấp mà không làm thay đổi hành vi migration không?

Đánh giá khả năng khai thác giúp ưu tiên xử lý, nhưng không được dùng để bỏ qua lỗ hổng nghiêm trọng trong thành phần có quyền cao.

## 3. Quản lý dependency Liquibase

Một ứng dụng hoặc migration runner có thể phụ thuộc vào:

- Liquibase core hoặc CLI.
- JDBC driver tương ứng với DBMS.
- Extension chính thức hoặc extension nội bộ.
- Thư viện logging, YAML/XML parser và utility.
- Plugin build, plugin kiểm tra và plugin đóng gói.
- Java runtime và thư viện hệ thống trong container.

Hãy lập danh sách dependency thực tế của runtime, không chỉ xem file khai báo dependency trực tiếp. Một thư viện có thể xuất hiện qua nhiều nhánh bắc cầu.

### 3.1. Khóa version cụ thể

Không dùng version động như latest, release range hoặc SNAPSHOT trong migration runtime production. Ví dụ Maven:

~~~xml
<properties>
    <liquibase.version>PINNED_LIQUIBASE_VERSION</liquibase.version>
    <jdbc.driver.version>PINNED_DRIVER_VERSION</jdbc.driver.version>
    <custom.extension.version>PINNED_EXTENSION_VERSION</custom.extension.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.liquibase</groupId>
        <artifactId>liquibase-core</artifactId>
        <version>PINNED_LIQUIBASE_VERSION</version>
    </dependency>

    <dependency>
        <groupId>com.example.database</groupId>
        <artifactId>database-jdbc-driver</artifactId>
        <version>PINNED_DRIVER_VERSION</version>
    </dependency>

    <dependency>
        <groupId>com.example.liquibase</groupId>
        <artifactId>approved-liquibase-extension</artifactId>
        <version>PINNED_EXTENSION_VERSION</version>
    </dependency>
</dependencies>
~~~

Các groupId, artifactId và version trong ví dụ là placeholder; thay bằng package thực sự đã được phê duyệt. Không copy dependency không rõ chủ sở hữu vào dự án chỉ vì nó giải quyết nhanh một change type.

Pin version giúp build có thể tái tạo hơn, nhưng chưa đủ: cùng tọa độ package vẫn có thể bị thay nội dung nếu repository cho phép ghi đè. Cần kết hợp checksum verification, repository policy và artifact immutability.

### 3.2. Khóa dependency bắc cầu

Dependency graph cần được lưu và kiểm tra. Dùng lockfile hoặc cơ chế dependency locking/verification phù hợp build tool để ghi nhận phiên bản bắc cầu đã resolve.

Ví dụ nguyên tắc:

- Mọi dependency runtime có version xác định.
- Dependency bắc cầu có lock/verification metadata.
- Thay đổi graph được review trong pull request.
- Không tự động cập nhật toàn bộ graph trong một release migration khẩn cấp.
- Dependency không dùng được loại khỏi runtime package.
- Plugin build cũng được khóa và kiểm soát như dependency thực thi.

Nếu chỉ pin liquibase-core nhưng để một parser hoặc extension bắc cầu tự chọn version mới nhất, artifact vẫn có thể thay đổi giữa hai lần build.

### 3.3. Tránh dependency nhầm tên và typosquatting

Trước khi thêm package mới, xác minh:

- Namespace/groupId có thuộc publisher dự kiến không?
- Repository phát hành có phải nguồn chính thức hoặc proxy được tổ chức kiểm soát không?
- Tên package, website, repository source và lịch sử release có nhất quán không?
- Package có bị bỏ hoang hoặc đổi chủ sở hữu không?
- Có dependency tương đương đã được tổ chức phê duyệt không?
- Package có yêu cầu quyền hoặc network access không cần thiết không?

Không lấy package chỉ dựa trên kết quả tìm kiếm hoặc tên giống một extension quen thuộc.

## 4. Chỉ sử dụng repository dependency được phê duyệt

Build nên lấy package từ repository proxy hoặc registry nội bộ đã được quản lý, thay vì cho phép mỗi runner truy cập tùy ý Internet.

Một chính sách repository có thể:

- Allowlist repository Maven/NuGet/npm hoặc registry cần thiết.
- Chặn repository không xác định và mirror ngoài chính sách.
- Cache package đã được xác minh.
- Ghi log publisher, tọa độ, version và checksum.
- Chặn package SNAPSHOT hoặc version động trong release.
- Quét package trước khi đưa vào repository nội bộ.
- Hạn chế ai được publish/overwrite artifact.
- Có quy trình quarantine khi phát hiện package đáng ngờ.

### 4.1. Repository proxy không tự động bảo đảm an toàn

Một proxy chỉ chuyển tiếp mọi package từ Internet vẫn có thể cache package độc hại. Cần kiểm soát upstream, quyền publish, checksum, scan và quy trình phê duyệt.

Không cho developer hoặc build agent tùy ý thêm repository URL vào cấu hình release mà không review. Một repository không tin cậy có thể cung cấp package cùng tọa độ với package mong muốn nếu thứ tự ưu tiên resolve không được kiểm soát.

### 4.2. Tách quyền đọc và quyền publish

Build job thông thường chỉ cần quyền đọc dependency. Chỉ release job có phê duyệt mới được publish artifact. Dùng token riêng cho từng chức năng, scope tối thiểu và thời hạn ngắn nếu registry hỗ trợ.

Không dùng cùng một token có quyền đọc, ghi, xóa mọi package cho tất cả developer và pipeline.

## 5. Xác minh tính toàn vẹn dependency

Checksum giúp phát hiện package có nội dung khác với nội dung đã được phê duyệt. Nguồn checksum phải đáng tin cậy; tải package và checksum từ cùng một nguồn đã bị xâm nhập không tạo ra bảo đảm độc lập.

Các cách kiểm soát:

- Dependency verification metadata được review và lưu trong source control.
- Repository nội bộ lưu checksum đã xác minh.
- Package được ký nếu publisher cung cấp chữ ký có thể kiểm tra.
- Build thất bại khi checksum không khớp.
- Thay đổi checksum yêu cầu review và lý do rõ ràng.
- Không tự động chấp nhận checksum mới khi download thất bại.

### 5.1. Checksum artifact khác Liquibase checksum

Cần phân biệt hai loại checksum:

| Loại | Đối tượng được kiểm tra | Mục đích |
|---|---|---|
| Dependency/artifact checksum | JAR, extension, driver, image hoặc bundle | Xác minh nội dung package có đúng artifact đã phê duyệt |
| Liquibase changeset checksum | Nội dung changeset theo cách Liquibase tính | Phát hiện changeset lịch sử đã thay đổi |

Liquibase checksum không chứng minh JDBC driver hoặc container image an toàn. Ngược lại, image digest đúng cũng không chứng minh SQL trong changelog có ý nghĩa nghiệp vụ đúng. Cần kiểm soát cả hai lớp.

### 5.2. Không dùng clear-checksums để xử lý lỗi supply chain

Nếu checksum mismatch xuất hiện sau khi dependency, Liquibase version hoặc resource thay đổi, hãy điều tra nguồn gốc artifact và lịch sử changeset. Không chạy clear-checksums chỉ để bỏ qua cảnh báo.

Clear-checksums có thể khiến Liquibase tính lại checksum cho các changeset đã triển khai. Nó không xác minh package mới là đáng tin cậy và không sửa được artifact bị thay thế. Chỉ sử dụng khi có kế hoạch kỹ thuật riêng, review và bằng chứng tương ứng.

## 6. Kiểm soát Liquibase extension

Extension có thể cung cấp change type, precondition, parser, snapshot generator, database support hoặc executor tùy chỉnh. Chúng giúp mở rộng khả năng Liquibase nhưng cũng mở rộng bề mặt tấn công.

### 6.1. Vì sao extension cần được review nghiêm ngặt?

Extension thường được nạp trong tiến trình Liquibase. Code có thể:

- Đọc environment variables hoặc system properties.
- Truy cập file và thư mục chứa changelog.
- Mở kết nối network.
- Đọc thông tin cấu hình database.
- Thực thi SQL hoặc tạo statement.
- Ghi log dữ liệu mà nó xử lý.
- Thay đổi cách Liquibase parse hoặc thực thi changeset.

Vì vậy, extension cần được đánh giá như code ứng dụng có quyền migration, không phải chỉ là một file cấu hình.

### 6.2. Allowlist extension

Duy trì danh sách extension được phê duyệt:

| Trường | Nội dung cần lưu |
|---|---|
| Tên/package | Tọa độ artifact chính xác |
| Publisher | Tổ chức/cá nhân phát hành đã xác minh |
| Version | Version được pin |
| Digest/checksum | Dấu vân tay package đã kiểm tra |
| Source repository | URL nguồn và commit/tag tương ứng |
| Chức năng | Change type/precondition/executor được cung cấp |
| Quyền cần thiết | Filesystem/network/database access |
| Người phê duyệt | Chủ sở hữu kỹ thuật và bảo mật |
| Ngày rà soát | Thời điểm kiểm tra gần nhất |
| Trạng thái | Approved, deprecated hoặc blocked |

Không cho phép extension mới tự động được nạp chỉ vì JAR xuất hiện trong thư mục lib. Việc phát hiện extension qua Java service loader hoặc cơ chế discovery tương tự cần nằm trong chính sách kiểm soát package và classpath.

### 6.3. Tự viết extension nội bộ

Nếu phải viết extension:

- Source code nằm trong repository được bảo vệ.
- Pull request cần review bởi người hiểu Liquibase và bảo mật.
- Unit/integration test kiểm tra SQL được sinh và hành vi lỗi.
- Không đọc secret hoặc gọi network nếu không có lý do.
- Không thực thi command shell từ dữ liệu changelog.
- Không ghép chuỗi SQL từ input chưa được xác thực.
- Xử lý exception an toàn, không log credential.
- Build artifact có version, SBOM, digest và chữ ký.
- Có owner và kế hoạch cập nhật dependency.

Không coi extension nội bộ là đáng tin cậy mặc định. Nó vẫn cần cùng quy trình kiểm soát như package bên ngoài.

### 6.4. Đánh giá compatibility khi nâng cấp extension

Nâng version extension có thể thay đổi SQL sinh ra, parser behavior hoặc cách kiểm tra precondition. Trước khi nâng cấp:

1. Đọc release notes và breaking changes.
2. So dependency graph và vulnerability findings.
3. Chạy test trên database đại diện.
4. Kiểm tra update-sql.
5. Kiểm tra changeset lịch sử trên bản sao database.
6. Xác minh rollback/forward-fix.
7. Build image mới và scan lại.
8. Promote cùng artifact đã kiểm thử.

Không nâng Liquibase core, JDBC driver và nhiều extension cùng lúc nếu có thể tách thay đổi để dễ xác định nguyên nhân.

## 7. Quản lý JDBC driver và database client

JDBC driver là thành phần thực thi quan trọng vì nó nhận credentials, tạo kết nối và truyền câu lệnh tới DBMS.

Chính sách nên bao gồm:

- Chọn driver từ publisher và repository tin cậy.
- Pin version theo DBMS/version được hỗ trợ.
- Kiểm tra CVE và release notes.
- Kiểm tra TLS certificate validation và hostname verification.
- Không bật chế độ trust-all certificate trong production.
- Không đưa credentials vào JDBC URL hoặc log.
- Không đóng gói driver không sử dụng.
- Test migration bằng đúng driver sẽ chạy production.

Nếu một migration runner hỗ trợ nhiều DBMS, chỉ đóng gói driver cần thiết cho target hoặc kiểm soát rõ classpath. Driver thừa làm tăng bề mặt tấn công và có thể gây xung đột classloading.

### 7.1. TLS và kết nối database

Kết nối migration phải xác minh danh tính database qua TLS theo cấu hình DBMS/driver. Tránh cấu hình bỏ qua xác minh chứng thư hoặc hostname để sửa nhanh lỗi kết nối.

Credential nên được lấy từ secret manager hoặc cơ chế workload identity phù hợp. Khi log lỗi, redact JDBC URL và tham số có thể chứa username, password, token hoặc thông tin nội bộ.

## 8. Phân tích lỗ hổng và cập nhật dependency

SCA (Software Composition Analysis) kiểm tra dependency đã resolve với cơ sở dữ liệu lỗ hổng và chính sách license. Nên quét cả dependency ứng dụng, migration runtime, extension và image.

### 8.1. Các thời điểm cần scan

- Khi pull request thay đổi dependency.
- Khi build release artifact.
- Theo lịch định kỳ kể cả khi source không đổi.
- Khi có CVE mới ảnh hưởng đến dependency đang dùng.
- Trước khi promote image sang production.
- Khi nâng Java runtime, Liquibase, JDBC driver hoặc extension.

Một package an toàn lúc build có thể bị công bố lỗ hổng sau vài tuần. Vì vậy, scan chỉ một lần không đủ cho hệ thống sống lâu.

### 8.2. Ưu tiên theo mức độ và khả năng khai thác

Khi có finding, ghi nhận:

- CVE/advisory và package bị ảnh hưởng.
- Phiên bản hiện tại và phiên bản đã sửa.
- Dependency trực tiếp hay bắc cầu.
- Có nằm trong runtime image không?
- Code path bị ảnh hưởng có thể được gọi không?
- Runner có quyền database/network/filesystem nào?
- Có exploit công khai hoặc dấu hiệu khai thác không?
- Có biện pháp giảm thiểu tạm thời nào?
- Owner và hạn xử lý.

Không đóng finding chỉ vì package là dependency bắc cầu hoặc scanner đánh dấu chưa reachable. Cần ghi lý do, bằng chứng và thời hạn xem xét lại.

### 8.3. Exception có thời hạn

Nếu chưa thể nâng cấp ngay do compatibility:

- Tạo exception được phê duyệt.
- Ghi package/version/CVE cụ thể.
- Nêu tác động và điều kiện khai thác.
- Hạn chế network/secret/privilege để giảm tác động.
- Đặt owner, deadline và ngày hết hạn.
- Theo dõi trong dashboard.
- Tạo issue nâng cấp và test.

Không dùng exception vô thời hạn hoặc wildcard cho mọi CVE trong một thư viện.

### 8.4. Nâng cấp an toàn

Nâng cấp dependency là một thay đổi cần kiểm thử, nhất là với Liquibase:

1. Tạo nhánh thay đổi version.
2. So release notes, dependency tree và CVE.
3. Build artifact mới.
4. Chạy validate và update-sql.
5. Test fresh install và upgrade path.
6. Test trên DBMS/version đại diện.
7. Xác minh DATABASECHANGELOG/checksum không bị thay đổi ngoài dự kiến.
8. Scan SBOM và image.
9. Ký và publish artifact mới.
10. Promote artifact đó qua môi trường.

Không thay JAR trực tiếp bên trong container production hoặc sửa lib trên runner đang chạy. Hãy tạo image mới có digest mới.

## 9. SBOM: biết chính xác artifact chứa gì

SBOM (Software Bill of Materials) là danh mục thành phần phần mềm trong artifact. Với Liquibase runner, SBOM nên bao gồm:

- Liquibase core/CLI và version.
- JDBC driver.
- Extension và dependency bắc cầu.
- Java runtime/base image.
- OS package trong container.
- Công cụ hoặc thư viện bổ sung.
- License và thông tin publisher khi có.

Các định dạng thường gặp gồm CycloneDX và SPDX. Chọn định dạng mà scanner, registry và quy trình kiểm toán của tổ chức hỗ trợ.

### 9.1. Tạo SBOM cho cả dependency và container

Một SBOM chỉ quét file pom.xml có thể bỏ sót package trong image runtime hoặc OS layer. Cần tạo/kiểm tra SBOM từ artifact thực tế và image digest được phát hành.

Đối chiếu:

- Dependency khai báo so với dependency thực tế trong classpath.
- Extension JAR có nằm trong image không.
- JDBC driver có đúng version không.
- Base image và OS package có được liệt kê không.
- Có binary hoặc package lạ không được giải thích không.
- SBOM có gắn với đúng digest artifact không.

### 9.2. Lưu SBOM cùng release

Lưu SBOM, digest và provenance cùng artifact trong registry hoặc hệ thống quản lý release. Khi có CVE mới, có thể tìm tất cả artifact đang chứa package bị ảnh hưởng mà không cần đoán từ source hiện tại.

SBOM không chứng minh package an toàn; nó cung cấp khả năng nhìn thấy thành phần để scan, điều tra và phản ứng.

## 10. Provenance và reproducible build

Provenance mô tả artifact được tạo từ source nào, bởi pipeline nào, dùng builder và dependency nào, theo quy trình nào. Nó giúp phân biệt artifact được build từ repository/pipeline tin cậy với file được tải lên thủ công.

Một provenance record nên liên kết:

- Repository và commit source.
- Build workflow và build identity.
- Builder image/version.
- Dependency lock/verification metadata.
- Build parameters không nhạy cảm.
- Artifact name/version/digest.
- SBOM và scan result.
- Thời điểm build và người/identity khởi tạo.
- Test result và approval liên quan.

### 10.1. Reproducible build

Mục tiêu là cùng source và dependency được khóa sẽ tạo ra artifact giống nhau hoặc có thể giải thích sự khác biệt. Để tiến gần mục tiêu này:

- Pin toolchain và builder image.
- Pin dependency và plugin.
- Tránh download script không version.
- Không dùng biến môi trường không được ghi nhận để thay nội dung build.
- Kiểm soát timestamp và resource filtering.
- Dùng repository nội bộ có checksum verification.
- Lưu build log và artifact digest.

Không phải mọi JAR/container đều mặc nhiên bit-for-bit reproducible. Hãy đo và ghi nhận khả năng thực tế; không tuyên bố reproducible nếu chưa kiểm chứng.

### 10.2. Attestation không thay thế review

Một build attestation chứng minh artifact được tạo theo một quy trình/identity nhất định, không tự chứng minh changelog đúng nghiệp vụ hoặc dependency không có lỗ hổng. Cần kết hợp source review, test, SCA, SBOM và approval.

## 11. Ký và xác minh artifact

Chữ ký số giúp xác minh artifact đến từ publisher/identity được tin cậy và nội dung không bị thay đổi sau khi ký.

Có thể ký:

- JAR hoặc migration bundle.
- Container image.
- SBOM.
- Provenance/attestation.

Quy trình:

1. Build artifact trong pipeline tin cậy.
2. Tạo digest.
3. Tạo SBOM và provenance.
4. Scan và áp dụng policy.
5. Ký artifact/attestation bằng key hoặc workload identity được bảo vệ.
6. Publish vào registry bất biến.
7. Trước deployment, xác minh chữ ký, signer identity và digest.
8. Chỉ chạy nếu mọi policy bắt buộc đạt.

### 11.1. Bảo vệ khóa ký

- Không commit private key vào repository.
- Hạn chế ai được sử dụng signing identity.
- Dùng KMS/HSM hoặc keyless signing có trust policy phù hợp nếu nền tảng hỗ trợ.
- Tách quyền build và quyền phê duyệt phát hành khi cần.
- Có rotation và revocation procedure.
- Audit mọi lần ký.
- Không cho pull request không tin cậy truy cập signing secret.

Chữ ký chỉ đáng tin khi public key/trust root và danh tính signer được bảo vệ. Không xác minh bằng một public key lấy từ cùng nguồn có thể bị attacker thay đổi.

### 11.2. Kiểm tra digest khi promote

Một tag image như release-2.8.0 có thể bị trỏ sang image khác nếu registry cho phép overwrite. Deployment nên tham chiếu digest bất biến:

~~~text
registry.example.com/platform/liquibase-runner@sha256:<verified-image-digest>
~~~

Nếu hệ thống dùng tag để dễ đọc, vẫn cần resolve tag thành digest và xác minh chữ ký/digest trước khi chạy. Staging và production phải dùng cùng digest đã được kiểm thử.

## 12. Bảo vệ container image của Liquibase

Container image đóng gói Liquibase runtime, JDBC driver, extension và resource changelog. Nó cũng chứa OS package, Java runtime và công cụ hỗ trợ. Vì vậy, image là một phần của chuỗi cung ứng migration.

### 12.1. Chọn base image tin cậy

- Chọn publisher chính thức hoặc registry nội bộ đã phê duyệt.
- Ưu tiên image tối giản có runtime cần thiết.
- Pin base image bằng digest, không chỉ tag.
- Kiểm tra chữ ký/provenance nếu publisher cung cấp.
- Scan OS packages và runtime libraries.
- Theo dõi lifecycle và security update của base image.
- Không dùng image không rõ nguồn chỉ vì dung lượng nhỏ.

Image tối giản giảm package thừa nhưng không tự bảo đảm an toàn. Cần biết cách cập nhật CA certificates, timezone data và runtime dependency mà Liquibase/JDBC cần.

### 12.2. Pin cả base image và image cuối

Nếu Dockerfile dùng FROM image:tag, cùng Dockerfile có thể build ra nội dung khác khi tag được cập nhật. Dùng digest cho base image và publish image cuối với digest được lưu trong release manifest.

Ví dụ:

~~~dockerfile
FROM registry.example.com/platform/liquibase-runtime:4.x@sha256:<approved-base-digest>

WORKDIR /workspace

COPY --chown=10001:10001 changelog/ /workspace/changelog/

USER 10001:10001

ENTRYPOINT ["/opt/liquibase/liquibase"]
~~~

Đây là ví dụ cấu trúc; đường dẫn executable và base image phải khớp image đã chọn. Placeholder digest phải được thay bằng digest đã xác minh. Không đưa password hoặc JDBC URL có credential vào Dockerfile.

### 12.3. Dùng multi-stage build khi cần biên dịch extension

Nếu extension nội bộ cần compile, dùng build stage riêng có compiler/toolchain và runtime stage chỉ chứa JRE, Liquibase, driver, extension cùng resource cần thiết. Không copy Maven cache, source tree, SSH key, build token hoặc toolchain không cần vào image runtime.

Chỉ copy các artifact đã được kiểm tra. Scan image cuối cùng vì dependency có thể xuất hiện ở runtime stage dù không có trong manifest source ban đầu.

### 12.4. Không cài package bằng script không xác minh

Tránh các mẫu tải script tùy ý rồi pipe thẳng vào shell. Nếu cần cài Liquibase hoặc driver:

- Lấy package từ nguồn được phê duyệt.
- Xác minh checksum/chữ ký.
- Pin version.
- Lưu build recipe.
- Kiểm tra package trước khi copy vào runtime.
- Không để script cài đặt nhận token có quyền rộng hơn cần thiết.

## 13. Hardening container runtime

Image an toàn vẫn có thể bị khai thác nếu container chạy với quyền quá rộng.

Cấu hình runtime nên cân nhắc:

- Chạy bằng non-root UID/GID.
- Filesystem read-only khi có thể.
- Chỉ mount changelog/config cần thiết.
- Dùng tmpfs hoặc thư mục tạm có giới hạn nếu Liquibase cần ghi.
- Drop Linux capabilities không cần.
- Không mount Docker socket.
- Không dùng privileged mode.
- Không mount host filesystem rộng.
- Dùng seccomp/AppArmor/SELinux policy phù hợp.
- Giới hạn CPU, memory, process và thời gian chạy.
- Giới hạn network egress tới database, secret provider và registry cần thiết.
- Không để container tự tải dependency lúc startup.

### 13.1. Tách build container và migration container

Build container có thể cần compiler, package manager, source và quyền đọc repository. Migration container chỉ cần runtime và artifact đã phát hành.

Không chạy production migration bằng container build đầy đủ nếu không cần. Giảm công cụ và package trong runtime image giúp giảm bề mặt tấn công và số CVE phải theo dõi.

### 13.2. Không để container ghi lại artifact đã phê duyệt

Mount changelog ở chế độ read-only nếu khả thi. Tách thư mục output/log tạm khỏi thư mục artifact. Sau khi chạy, digest của artifact phải không đổi.

Không cho phép startup script tự sửa changelog, tải extension mới hoặc thay JDBC driver dựa trên URL động.

## 14. Quản lý secret cho migration runner

Migration credential thường có quyền DDL, vì vậy có giá trị cao hơn credential runtime thông thường.

Nguyên tắc:

- Lấy secret từ secret manager hoặc workload identity.
- Chỉ cấp secret cho job đã được phê duyệt.
- Dùng credential riêng cho từng database/environment.
- Ưu tiên token/credential ngắn hạn nếu DBMS và nền tảng hỗ trợ.
- Không lưu secret trong image, JAR, changelog, properties đã commit hoặc SBOM.
- Không truyền secret dưới dạng command-line argument dễ xuất hiện trong process list/log.
- Redact log và lỗi.
- Thu hồi/rotate sau sự cố hoặc khi runner không còn cần quyền.
- Không cho PR từ fork nhận production credential.

### 14.1. Secret injection lúc runtime

Ví dụ cấu hình minh họa:

~~~yaml
liquibase:
  url: MIGRATION_JDBC_URL_FROM_SECRET_PROVIDER
  username: MIGRATION_DB_USER_FROM_SECRET_PROVIDER
  password: MIGRATION_DB_PASSWORD_FROM_SECRET_PROVIDER
  changeLogFile: changelog/db.changelog-master.yaml
~~~

Đây là biểu diễn khái niệm; cách bind property tùy CLI, Spring Boot hoặc wrapper được dùng. Các giá trị secret được cấp bởi runtime secret provider. Không đưa file chứa giá trị thật vào image layer.

### 14.2. Giảm quyền database

Migration role chỉ nên có quyền trên database/schema mà artifact cần thay đổi:

- Quyền tạo/sửa/xóa đối tượng trong schema thuộc sở hữu.
- Quyền đọc/ghi bảng metadata Liquibase.
- Quyền cần thiết cho DML migration cụ thể.
- Không có quyền quản trị server hoặc truy cập database khác nếu không cần.
- Không dùng runtime application user cho DDL nếu có thể tách.
- Có quy trình phê duyệt riêng cho changeset phá hủy.

Nếu một migration cần quyền đặc biệt, hãy cấp tạm thời hoặc qua role chuyên biệt theo quy trình DBA; không giữ quyền superuser trong mọi pipeline.

## 15. CI/CD an toàn cho dependency và image

Một pipeline có thể tổ chức:

~~~text
Pull request
   |
   v
Review changelog + build config + extension
   |
   v
Resolve dependencies từ repository allowlist
   |
   v
Verify versions/checksums/lock
   |
   v
Build migration artifact và container image
   |
   v
Generate SBOM + provenance
   |
   v
SCA + image scan + license policy
   |
   v
Tests: validate / fresh install / upgrade path
   |
   v
Sign artifact + publish immutable digest
   |
   v
Approval + verify signature/policy
   |
   v
Inject short-lived secret
   |
   v
Run Liquibase với least-privilege identity
   |
   v
Post-check + audit evidence
~~~

### 15.1. Tách job build khỏi job deploy

Build job không nên có production database credential. Nó chỉ cần quyền đọc dependency và publish artifact vào repository theo quyền được cấp.

Deploy job nhận artifact đã publish, xác minh digest/chữ ký, rồi mới nhận secret để kết nối database. Điều này hạn chế việc code trong pull request có thể đọc secret production.

### 15.2. Không chạy untrusted pull request với quyền phát hành

- Fork PR không được nhận signing key hoặc publish token.
- Không chạy script từ PR trong runner có quyền production.
- Dùng runner ephemeral hoặc workspace được làm sạch giữa job.
- Pin CI actions/plugins theo version hoặc commit đã review.
- Bảo vệ branch và environment approval.
- Tách quyền publish, sign và deploy.
- Không cho job build truy cập Docker socket của host nếu không cần.

### 15.3. Policy gate trước production

Có thể chặn deployment khi:

- Image không pin digest.
- Signature không hợp lệ hoặc signer không nằm trong allowlist.
- SBOM thiếu hoặc không gắn với đúng digest.
- Có CVE vượt ngưỡng chính sách mà chưa có exception.
- Extension chưa được phê duyệt.
- Artifact provenance không đạt.
- Image chạy bằng root hoặc có privileged setting ngoài chính sách.
- SQL preview không khớp artifact được ký.
- Deployment target hoặc migration role không đúng phạm vi.

Policy nên có thông báo rõ finding, owner và cách khắc phục. Không biến một scanner thành cổng mù: cần lưu bằng chứng, exception có hạn và cơ chế review.

## 16. Quản lý license và nguồn gốc package

Ngoài CVE, dependency có thể có license không tương thích với chính sách tổ chức hoặc không rõ nguồn gốc. Với Liquibase extension và JDBC driver, kiểm tra:

- License identifier và nghĩa vụ phân phối.
- Publisher và repository source.
- Source code có sẵn khi license yêu cầu không.
- Package có chứa binary không rõ nguồn không.
- Notice/attribution cần đi cùng artifact.
- Có package bị cấm hoặc license exception không.

Không giả định package miễn phí đồng nghĩa license phù hợp. Nếu không xác định được license, chuyển sang review thay vì tự suy diễn.

## 17. Theo dõi và ứng phó khi phát hiện dependency bị xâm nhập

Nếu một extension, JDBC driver hoặc base image bị phát hiện độc hại/lỗ hổng nghiêm trọng:

1. Xác định mọi artifact/image đang chứa package/version/digest đó bằng SBOM và registry metadata.
2. Dừng promotion và tạm ngừng migration runner bị ảnh hưởng.
3. Thu hồi token/credential có thể đã bị lộ.
4. Kiểm tra log CI/CD, registry pull, deployment và network egress.
5. Xác định database nào đã được truy cập bởi runner đó.
6. Kiểm tra changeset history, schema, grants và audit log DBMS.
7. Giữ lại evidence phục vụ điều tra; không ghi đè image/artifact cũ.
8. Build lại từ dependency đã xác minh và runner sạch.
9. Tạo SBOM/provenance/chữ ký mới.
10. Triển khai artifact mới theo quy trình phê duyệt.
11. Xoay secret và rà soát quyền.
12. Ghi nhận nguyên nhân gốc và cập nhật allowlist/policy.

### 17.1. Không chỉ nâng version rồi coi sự cố đã xong

Nếu package độc hại đã chạy với quyền DDL, cần điều tra trạng thái database và khả năng dữ liệu bị đọc hoặc thay đổi. Nâng version không tự hoàn tác câu SQL đã thực thi hoặc khôi phục credential bị đánh cắp.

Liquibase DATABASECHANGELOG chỉ cho biết những changeset mà Liquibase ghi nhận; nó không phải audit log đầy đủ của mọi câu lệnh mà extension hoặc process có thể thực hiện. Đối chiếu thêm database audit, network logs, runner logs và registry records.

## 18. Những lỗi thường gặp trong kiểm soát nguồn cung

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Build hôm nay khác build hôm qua | Version động hoặc dependency bắc cầu không khóa | Lock graph, pin plugin và xác minh checksum |
| Extension mới xuất hiện trong runtime | Classpath tự động nạp JAR ngoài allowlist | Kiểm tra image contents và quản lý extension allowlist |
| Scan source sạch nhưng image có CVE | OS package hoặc runtime layer chưa được scan | Scan image digest và tạo SBOM container |
| Image tag staging khác production | Tag bị ghi đè hoặc resolve ở thời điểm khác | Promote digest bất biến |
| Chữ ký hợp lệ nhưng artifact sai | Trust policy cho phép signer không đúng | Ràng buộc signer identity/repository/workflow |
| SBOM không khớp image | SBOM tạo từ source thay vì artifact cuối | Gắn SBOM với digest và scan image thực tế |
| Secret xuất hiện trong layer | Docker ARG/ENV hoặc COPY file properties chứa secret | Dùng secret injection lúc runtime; rebuild image sạch |
| PR đọc được token | Runner cấp secret cho untrusted code | Tách job/runner và giới hạn secret theo environment |
| CVE bị bỏ qua vô thời hạn | Exception không owner/deadline | Exception cụ thể, hết hạn và review định kỳ |
| JDBC TLS bị tắt để kết nối được | Cấu hình trust-all hoặc bỏ xác minh host | Cài CA đúng và bật xác minh certificate/hostname |
| Rollback không khắc phục package độc hại | SQL đã chạy hoặc dữ liệu đã bị truy cập | Incident response, audit DB, rotate secret và recovery plan |

## 19. Bài thực hành: tạo migration image có thể xác minh

**Mục tiêu:** đóng gói một Liquibase runner với dependency được pin, image digest bất biến, SBOM và quy trình xác minh trước khi chạy. Chỉ dùng registry/database lab.

### Bước 1. Lập dependency manifest

Ghi lại:

- Liquibase version.
- JDBC driver version.
- Extension được phép và version.
- Java runtime.
- Build plugin và version.
- Repository nguồn.
- Checksum verification metadata.

Loại dependency không sử dụng khỏi runtime image.

### Bước 2. Review extension

Với mỗi extension, xác minh publisher, source repository, version, digest, license, CVE và quyền cần thiết. Nếu là extension nội bộ, review code và test change type/precondition/executor.

Không thêm extension chỉ để thử nghiệm vào image production.

### Bước 3. Build image từ base image đã pin

Dùng base image digest được phê duyệt. Copy Liquibase runtime, driver, extension và changelog artifact đã build. Chạy bằng non-root user; không copy secret, build cache hoặc source credential vào image.

### Bước 4. Scan và tạo SBOM

Tạo SBOM từ image cuối cùng. Scan OS packages, Java dependencies và extension. Lưu kết quả cùng image digest. Xử lý finding theo policy hoặc tạo exception có hạn và owner.

### Bước 5. Ký và publish

Tạo digest image, ký bằng signing identity được bảo vệ và publish vào registry bất biến. Lưu provenance, SBOM và scan result liên kết với digest.

### Bước 6. Verify trước khi chạy

Deployment job:

- Chọn image bằng digest.
- Xác minh chữ ký và signer.
- Kiểm tra SBOM/provenance.
- Kiểm tra policy CVE/license.
- Kiểm tra non-root, capabilities, mounts và network policy.
- Chỉ sau khi đạt mới inject secret database lab.

### Bước 7. Chạy migration trong lab

Dùng image đã xác minh để chạy:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Xác minh changeset, schema, dữ liệu và metadata. Lưu image digest, dependency manifest, SBOM, signature verification result và deployment ID.

### Bước 8. Kiểm tra promotion

Promote cùng image digest sang một database lab thứ hai với secret/config riêng. Không rebuild hoặc dùng tag mới có nội dung khác. Xác nhận hai lần chạy dùng cùng image digest và root changelog.

## 20. Checklist bảo mật trước khi phát hành

- [ ] Liquibase, JDBC driver, extension và build plugin có version được pin.
- [ ] Dependency bắc cầu được khóa và xác minh checksum.
- [ ] Chỉ dùng repository/registry đã được phê duyệt.
- [ ] Publisher và nguồn của extension đã được xác minh.
- [ ] Extension nằm trong allowlist và có owner.
- [ ] Không có dependency động/SNAPSHOT trong release production.
- [ ] SCA và license scan đã chạy trên dependency thực tế.
- [ ] SBOM được tạo từ artifact và image cuối cùng.
- [ ] CVE được xử lý hoặc có exception cụ thể, owner và expiry.
- [ ] Base image được pin bằng digest và có nguồn gốc tin cậy.
- [ ] Image runtime không chứa build tool/cache/secret không cần thiết.
- [ ] Container chạy non-root, không privileged và không mount Docker socket.
- [ ] Filesystem, capabilities, network egress và resource limit được kiểm soát.
- [ ] Artifact có digest, provenance và chữ ký.
- [ ] Deployment xác minh signer identity và digest trước khi chạy.
- [ ] Build job và deploy job tách quyền.
- [ ] Pull request không tin cậy không nhận secret/signing token.
- [ ] Migration credential được inject lúc runtime, có scope tối thiểu.
- [ ] JDBC TLS xác minh certificate và hostname.
- [ ] Log không chứa password, token hoặc dữ liệu nhạy cảm.
- [ ] Fresh-install/upgrade-path test chạy bằng image đã phát hành.
- [ ] Có quy trình xử lý khi dependency/image bị xâm nhập.
- [ ] Artifact và SBOM được giữ để điều tra theo retention policy.

## 21. Kết luận

Kiểm soát nguồn cung cho Liquibase phải bao phủ **dependency, extension, JDBC driver, build pipeline, container image và artifact được triển khai**. Pin version, khóa dependency bắc cầu, xác minh checksum, dùng repository tin cậy và allowlist extension giúp giảm nguy cơ package bị thay thế hoặc nạp code không được review. SCA, SBOM, provenance và chữ ký cung cấp bằng chứng về thành phần, lỗ hổng, nguồn gốc và tính toàn vẹn của release.

Container cần được build từ base image đã xác minh, pin digest, tối giản, chạy non-root và giới hạn filesystem/network/capability. Deployment chỉ nên chạy image đã được xác minh bằng digest, nhận secret lúc runtime và dùng migration role có quyền tối thiểu. Khi phát hiện package bị xâm nhập, phải điều tra cả runner, credential và database đã truy cập; thay version đơn thuần không khôi phục được những thay đổi hoặc dữ liệu đã bị tác động. Kết hợp các kiểm soát này với review changelog, kiểm thử Liquibase và CI/CD có audit sẽ giúp migration đáng tin cậy qua toàn bộ vòng đời phát hành.
