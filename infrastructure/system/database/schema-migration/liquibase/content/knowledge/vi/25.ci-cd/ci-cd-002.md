# Đóng gói changelog và công cụ thành artifact có phiên bản

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **CI/CD**, migration chỉ có thể triển khai lặp lại và kiểm toán được khi nhóm biết chính xác **changelog nào**, **phiên bản Liquibase nào**, **JDBC driver nào** và **extension nào** đã tạo ra thay đổi trên database. Nếu pipeline tải changelog trực tiếp từ nhánh đang thay đổi, dùng CLI mới nhất ở mỗi lần chạy hoặc cài driver theo trạng thái máy runner, cùng một release có thể tạo kết quả khác nhau giữa staging và production.

Cách tiếp cận đáng tin cậy là đóng gói changelog cùng công cụ và dependency cần thiết thành **artifact có phiên bản bất biến**. Artifact phải xác định entry point, phiên bản Liquibase, driver/extension, phạm vi DBMS, commit nguồn, checksum gói và hướng dẫn thực thi. CI xây dựng và kiểm thử artifact một lần; CD lấy đúng artifact đó để triển khai lần lượt qua các môi trường. Mỗi môi trường chỉ cung cấp cấu hình kết nối, secret và tham số vận hành bên ngoài artifact.

Bài học này giải thích cách chọn loại artifact, tổ chức changelog, khóa phiên bản công cụ, đóng gói CLI/JDBC driver/extension, lập manifest, xác minh tính toàn vẹn, kiểm thử và promote cùng một gói qua các môi trường. Nội dung gắn với mục tiêu của **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**: quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Vì sao cần artifact migration có phiên bản?

Changelog là mã triển khai database. Nó quyết định bảng, cột, index, constraint, dữ liệu và các đối tượng database được tạo hoặc thay đổi. Công cụ Liquibase và JDBC driver cũng ảnh hưởng tới cách changelog được đọc và SQL được sinh/thực thi.

Nếu chỉ lưu changelog trong Git rồi để pipeline tự lấy mã nguồn và cài công cụ tại thời điểm deploy, có thể gặp các vấn đề:

- Runner dùng phiên bản Liquibase khác nhau giữa hai lần chạy.
- Driver JDBC hoặc extension tự thay đổi theo dependency resolution.
- Changelog trên nhánh đã bị cập nhật sau khi staging chạy, khiến production không còn dùng cùng nội dung.
- File SQL phụ trợ hoặc changelog con không được đưa vào gói triển khai.
- Người vận hành không biết artifact nào đã được dùng cho một database.
- Không thể xác minh gói đã triển khai có đúng với gói đã kiểm thử.
- Rollback không có đúng phiên bản công cụ, changelog và tài nguyên cần thiết.

Artifact có phiên bản giải quyết vấn đề nhận diện và phân phối. Mỗi artifact đại diện cho một tập nội dung xác định tại một thời điểm build. Khi release được promote, hệ thống dùng cùng nội dung và digest, còn URL database, credential, schema đích và các tham số theo môi trường được cấp riêng.

### 1.1. Artifact không chỉ là một file changelog

Một gói migration hoàn chỉnh có thể bao gồm:

| Thành phần | Mục đích |
|---|---|
| Master changelog | Entry point của chuỗi changeset |
| Changelog con | Changeset theo miền nghiệp vụ hoặc release |
| SQL phụ trợ | Procedure, view, backfill hoặc script phức tạp |
| Liquibase runtime/CLI | Bộ máy đọc changelog và thực thi migration |
| JDBC driver | Kết nối đúng DBMS |
| Liquibase extension | Change type hoặc chức năng bổ sung nếu sử dụng |
| Manifest | Phiên bản, commit, entry point, dependency và checksum |
| Hướng dẫn vận hành | Lệnh validate, preview, update, kiểm tra và rollback |
| SBOM/provenance | Danh sách dependency và nguồn gốc build nếu quy trình yêu cầu |

Không đưa password, token, private key, truststore có bí mật hoặc file cấu hình production vào artifact. Những giá trị đó được cấp khi chạy.

## 2. Chọn hình thức đóng gói phù hợp

Có ba mô hình phổ biến. Nhóm nên chọn một mô hình chuẩn cho mỗi loại dịch vụ để dễ vận hành.

| Hình thức | Nội dung | Phù hợp khi |
|---|---|---|
| **Changelog trong application JAR** | Spring Boot app, changelog, Liquibase core và JDBC driver trong runtime classpath | Ứng dụng tự chạy Liquibase lúc khởi động |
| **Migration ZIP/distribution** | Liquibase CLI, driver, extension, changelog, SQL, manifest và script chạy | Pipeline có migration job độc lập với application |
| **OCI/container image** | Runtime, Liquibase, dependency và changelog được đóng gói thành image | Nền tảng triển khai theo container và muốn cố định môi trường thực thi |

### 2.1. Changelog trong application JAR

Nếu Spring Boot auto-configuration chạy Liquibase khi ứng dụng khởi động, changelog thường nằm dưới:

~~~text
src/main/resources/
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        ├── changes/
        │   ├── 001-create-customer.yaml
        │   └── 002-create-order.yaml
        └── sql/
            └── create-order-function.sql
~~~

Build application JAR sẽ đóng gói resource và dependency runtime. Cấu hình entry point:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Ưu điểm là code ứng dụng và changelog được phát hành cùng phiên bản. Nhược điểm là migration gắn với vòng đời khởi động ứng dụng; nhóm cần quyết định có muốn mọi instance ứng dụng đều tham gia migration hay tách một migration job chuyên trách.

Không đặt changelog ở thư mục chỉ dành cho test resources nếu ứng dụng production cần đọc nó. Kiểm tra artifact cuối cùng, không chỉ kiểm tra file nguồn trong IDE.

### 2.2. Migration ZIP/distribution độc lập

Một gói ZIP có thể tổ chức như sau:

~~~text
liquibase-migration-2.4.0/
├── bin/
│   ├── migrate.sh
│   └── migrate.ps1
├── liquibase/
│   ├── liquibase
│   └── lib/
│       ├── liquibase-core.jar
│       ├── postgresql-driver.jar
│       └── approved-extension.jar
├── changelog/
│   ├── db.changelog-master.yaml
│   ├── changes/
│   └── sql/
├── config/
│   └── liquibase.properties.example
├── manifest/
│   └── release-manifest.yaml
└── docs/
    ├── README.md
    └── rollback.md
~~~

Đây là layout minh họa, không phải cấu trúc bắt buộc của mọi bản phân phối Liquibase. Đường dẫn executable, thư mục lib và cách nạp driver phải phù hợp với bản CLI thực tế được nhóm lựa chọn.

Mô hình này phù hợp khi nhóm muốn triển khai database trước application, dùng tài khoản migration riêng hoặc phát hành schema độc lập với lịch release của ứng dụng. Gói phải chứa đủ tài nguyên để chạy trong runner/container được hỗ trợ, không dựa vào file ngẫu nhiên có sẵn trên máy build.

### 2.3. OCI image

Có thể xây dựng image chứa Liquibase runtime, JDBC driver, extension và changelog. Image được gắn tag theo release và được tham chiếu bằng digest trong pipeline. Ưu điểm là runtime, filesystem và dependency được đóng gói cùng nhau; nhược điểm là phải quản lý base image, cập nhật bảo mật, quyền chạy và kích thước image.

Dù dùng ZIP hay image, nguyên tắc vẫn giống nhau: artifact được build một lần, được kiểm tra, lưu trong registry và promote nguyên vẹn. Không build lại image riêng cho production chỉ để thay URL hoặc password.

## 3. Chốt phiên bản Liquibase và dependency

Artifact cần ghi nhận phiên bản công cụ và dependency. Ít nhất phải xác định:

- Liquibase CLI hoặc Liquibase core.
- Java runtime nếu công cụ cần JVM.
- JDBC driver cho từng DBMS mục tiêu.
- Liquibase extension hoặc custom change type.
- Các thư viện phụ thuộc trực tiếp của extension.
- Plugin build tạo artifact.
- Hệ điều hành/architecture nếu gói chứa executable native hoặc image base.

Ví dụ dependency trong Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.liquibase</groupId>
        <artifactId>liquibase-core</artifactId>
        <version>4.31.1</version>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>42.7.5</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Các số phiên bản chỉ minh họa cách pin dependency. Dự án phải chọn phiên bản đã được kiểm thử và được chính sách dependency của tổ chức phê duyệt. Không dùng phiên bản động, range không kiểm soát hoặc tag latest trong release build.

### 3.1. Không trộn Liquibase CLI và Liquibase core tùy tiện

Có hai cách chạy thường gặp:

- **Liquibase CLI**: dùng bản phân phối CLI, driver và extension được cấu hình cho CLI.
- **Liquibase trong ứng dụng Java**: dùng liquibase-core cùng JDBC driver trong runtime classpath và cấu hình Spring Boot.

Không giả định thêm một JAR vào dependency của ứng dụng sẽ tự thay đổi phiên bản CLI cài trên runner. Tương tự, CLI trên máy developer không nhất thiết dùng đúng liquibase-core trong application JAR.

Ghi rõ mô hình thực thi trong manifest. Nếu cùng một release có cả migration job và application auto-run, cần khóa phiên bản Liquibase tương thích và kiểm thử cả hai đường chạy.

### 3.2. Khóa JDBC driver và extension

Driver ảnh hưởng tới TLS, kiểu dữ liệu, metadata và cách thực thi SQL. Extension có thể thêm change type hoặc behavior. Vì vậy:

- Pin version driver và extension.
- Không tải dependency mới nhất trong lúc deploy.
- Kiểm tra license và nguồn tải dependency.
- Quét lỗ hổng dependency trước release.
- Ghi checksum của file JAR trong manifest hoặc SBOM.
- Kiểm thử trên đúng DBMS/version mục tiêu.
- Không để hai phiên bản khác nhau của cùng driver xuất hiện trong classpath.

Một classpath có hai version JDBC driver có thể gây hành vi khó dự đoán. Kiểm tra dependency tree và nội dung artifact cuối cùng.

## 4. Định danh artifact và quy ước version

Một version cần giúp người vận hành trả lời: gói này được tạo từ commit nào, thuộc release nào và có thể tải lại chính xác không?

Có thể dùng version theo SemVer hoặc quy ước release nội bộ:

~~~text
liquibase-migration: 2.4.0
source commit: 8f4a2c1
build number: 1842
artifact digest: sha256:...
~~~

Ví dụ:

- **2.4.0**: release migration chính thức.
- **2.4.1**: bản sửa artifact hoặc nội dung được phát hành theo chính sách version của nhóm.
- **2.5.0-rc.1**: bản candidate để kiểm thử trước release.
- **2.5.0+build.1842**: metadata build nếu hệ thống registry hỗ trợ quy ước này.

Không tái sử dụng cùng version cho hai nội dung khác nhau. Nếu build thất bại hoặc artifact sai, phát hành version mới theo chính sách; không ghi đè file đã được môi trường khác tham chiếu.

### 4.1. Git tag không phải artifact identity duy nhất

Git tag hữu ích để xác định source release, nhưng artifact còn phụ thuộc toolchain và dependency. Hai build từ cùng commit có thể khác nhau nếu dependency không được pin, base image thay đổi, plugin build thay đổi, timestamp/metadata làm gói không tái lập, resource filtering thay đổi hoặc driver/extension được tải từ repository khác.

Vì vậy cần lưu cả commit nguồn, build metadata, dependency manifest và digest của artifact.

### 4.2. Không dùng tag mutable

Các nhãn như latest, stable hoặc production có thể trỏ tới nội dung khác theo thời gian. Có thể dùng chúng làm alias cho con người nếu registry hỗ trợ, nhưng pipeline production nên tham chiếu version bất biến và tốt nhất là digest.

## 5. Tổ chức changelog bên trong artifact

Master changelog là entry point duy nhất của một release. Ví dụ:

~~~text
changelog/
├── db.changelog-master.yaml
├── baseline/
│   └── baseline.yaml
├── releases/
│   ├── 2.3/
│   │   └── db.changelog-2.3.yaml
│   └── 2.4/
│       └── db.changelog-2.4.yaml
├── changes/
│   ├── customer/
│   └── orders/
└── sql/
    ├── views/
    └── procedures/
~~~

Master có thể include các file theo thứ tự:

~~~yaml
databaseChangeLog:
  - include:
      file: baseline/baseline.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2.3/db.changelog-2.3.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2.4/db.changelog-2.4.yaml
      relativeToChangelogFile: true
~~~

Cấu trúc folder chỉ giúp tổ chức. Liquibase thực thi theo changelog và thứ tự include, không tự hiểu folder 2.4 là phiên bản mới nhất nếu master không include file đó.

### 5.1. Đóng gói toàn bộ resource phụ thuộc

Mọi file được tham chiếu phải có trong artifact hoặc được cung cấp qua filesystem path đã định nghĩa:

- Changelog con từ include.
- Thư mục includeAll.
- SQL file từ sqlFile.
- CSV/JSON/XML seed data được loadData hoặc change type tham chiếu.
- File properties hoặc tài nguyên bổ trợ cần thiết.
- Custom extension nếu changeset dùng change type riêng.

Một lỗi thường gặp là master changelog có trong JAR nhưng SQL file không được đóng gói. CI nên kiểm tra danh sách file trong artifact và chạy validate bằng chính artifact đã tạo.

### 5.2. Path ổn định và logicalFilePath

Path của changelog tham gia định danh changeset trong lịch sử Liquibase. Khi di chuyển file hoặc thay đổi cách đóng gói, cần xem xét logicalFilePath theo phiên bản Liquibase đang dùng để bảo toàn identity. Không thêm logical path chỉ để chữa resource not found.

Artifact release phải giữ cùng đường dẫn logic đã được sử dụng ở các môi trường trước. Nếu đổi cấu trúc folder, hãy thử trên database có DATABASECHANGELOG trước khi phát hành để tránh changeset bị nhận diện như mới và chạy lại.

### 5.3. Không sửa changeset đã triển khai

Khi artifact 2.3.0 đã chạy trên staging hoặc production, nội dung changeset đã phát hành cần được xem là lịch sử bất biến. Nếu có lỗi, tạo changeset mới hoặc release sửa chữa theo quy trình. Không rebuild cùng version với nội dung changeset đã thay đổi, vì checksum và lịch sử ở các môi trường có thể không còn khớp.

## 6. Manifest mô tả artifact

Mỗi artifact nên có manifest máy đọc được. Manifest giúp pipeline và người vận hành biết nội dung, dependency và môi trường tương thích.

Ví dụ:

~~~yaml
artifact:
  name: liquibase-migration
  version: 2.4.0
  sourceCommit: 8f4a2c1
  buildNumber: 1842
  createdAt: 2026-11-19T10:30:00Z
  changelog:
    entryPoint: changelog/db.changelog-master.yaml
    format: yaml
    logicalPathPolicy: preserve-existing
  runtime:
    liquibaseVersion: 4.31.1
    javaVersion: 21
  drivers:
    - name: postgresql
      version: 42.7.5
  extensions: []
  targets:
    - dbms: postgresql
      supportedVersions: "16.x"
  integrity:
    archiveSha256: "<computed-by-build>"
~~~

Manifest là metadata mô tả, không phải nguồn bí mật. Không đưa password, token, private key, connection string chứa credential hoặc giá trị secret vào đây.

Các trường nên được điều chỉnh theo thực tế dự án. Nếu artifact hỗ trợ nhiều DBMS, liệt kê driver, extension, DBMS version và kiểm thử tương ứng. Nếu chỉ hỗ trợ PostgreSQL 16, không để manifest ghi chung chung all databases.

### 6.1. Manifest và checksum của Liquibase khác nhau

Có hai loại checksum cần phân biệt:

- **Artifact digest** như SHA-256: xác minh bytes của ZIP/JAR/image có đúng artifact đã phát hành hay không.
- **Liquibase changeset checksum** trong DATABASECHANGELOG: phát hiện nội dung changeset đã thay đổi so với lần được ghi nhận.

Artifact digest không thay thế changeset checksum. Ngược lại, checksum changeset không chứng minh toàn bộ gói CLI, driver, extension và script là đúng. Cần quản lý cả hai ở đúng lớp.

## 7. Kiểm tra tính toàn vẹn, chữ ký và nguồn gốc build

Sau khi build, tạo digest cho artifact và lưu trong registry/release metadata. Khi deploy, pipeline xác minh digest trước khi thực thi.

Ví dụ lệnh kiểm tra SHA-256:

~~~bash
sha256sum liquibase-migration-2.4.0.zip
~~~

Trên Windows có thể dùng công cụ hệ thống phù hợp, miễn là thuật toán và encoding đầu ra được thống nhất. Digest cần được lưu ở nơi tin cậy và gắn với version; không chỉ lưu bên cạnh file trong cùng một thư mục mà bất kỳ ai sửa artifact cũng có thể sửa digest.

Với hệ thống yêu cầu supply-chain security, có thể ký artifact hoặc image và xác minh chữ ký trước deploy. Kèm theo provenance cho biết:

- Repository và commit nguồn.
- Workflow/job đã tạo artifact.
- Builder identity và thời điểm build.
- Dependency/SBOM.
- Digest của artifact.
- Kết quả kiểm thử và policy gate.

Chữ ký xác minh nguồn gốc và tính toàn vẹn. Nó không chứng minh migration đúng về mặt nghiệp vụ; vẫn cần review, test và approval.

## 8. Đóng gói CLI, JDBC driver và extension

Nếu dùng migration ZIP độc lập, hãy xác định runtime mà ZIP cần. Ví dụ một gói có:

~~~text
liquibase-migration-2.4.0/
├── liquibase/
│   ├── liquibase
│   └── lib/
│       ├── liquibase-core.jar
│       ├── postgresql.jar
│       └── liquibase-extension.jar
├── changelog/
├── manifest/
└── bin/
~~~

Cần bảo đảm:

- Liquibase CLI version được pin.
- Driver tương thích với DBMS và Java runtime.
- Extension tương thích với Liquibase version.
- Không có duplicate JAR hoặc dependency conflict.
- Script launcher sử dụng đúng thư mục lib.
- File thực thi có quyền phù hợp trên Linux.
- Gói Windows/Linux có launcher và path convention tương ứng nếu cần hỗ trợ cả hai.
- Tất cả resource changelog/SQL được đọc thành công trong môi trường sạch.

Không giả định chỉ cần đặt JDBC driver vào một thư mục bất kỳ là Liquibase CLI sẽ tự nạp. Cách nạp driver phụ thuộc bản phân phối và classpath của CLI; hãy kiểm tra đúng cấu hình runtime đã chọn.

### 8.1. Script launcher

Launcher có thể chuẩn hóa working directory và entry point:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PACKAGE_DIR"

exec "$PACKAGE_DIR/liquibase/liquibase" \
  --changelog-file=changelog/db.changelog-master.yaml \
  "$@"
~~~

Đây là ví dụ cho gói có cấu trúc đã nêu. Launcher không chứa credential. URL, username và password được cung cấp từ secret store/environment hoặc cấu hình runtime được bảo vệ.

Không ghi secret vào command line trong script. Nếu cần dùng defaults file, tạo hoặc mount file runtime với quyền đọc hạn chế và bảo đảm không được đóng gói vào artifact.

## 9. Đóng gói cho Spring Boot

Nếu Liquibase chạy trong Spring Boot, application JAR có thể là migration artifact nếu nó chứa master changelog, toàn bộ changelog con và SQL/seed data phụ trợ, liquibase-core đúng phiên bản, JDBC driver đúng phiên bản, extension cần thiết và cấu hình mặc định không chứa secret.

Ví dụ cấu hình:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  datasource:
    url: $DB_URL
    username: $DB_USER
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Các biến môi trường trong ví dụ được cấp khi chạy. Password có thể được cung cấp bằng property riêng hoặc secret integration của nền tảng. Không nhúng giá trị thật trong application.yml.

Nếu application JAR đồng thời chứa changelog và chạy migration khi startup, cần xác định rõ instance nào được phép thực thi. Với nhiều replica, Liquibase lock điều phối các tiến trình cùng database, nhưng không thay thế chiến lược triển khai schema tương thích với phiên bản ứng dụng cũ/mới. Một migration job chuyên trách thường giúp kiểm soát thời điểm và quyền DDL tốt hơn.

### 9.1. Artifact ứng dụng và artifact migration riêng

Có thể phát hành hai artifact:

- **Application artifact**: mã ứng dụng, entity, repository và runtime dependencies.
- **Migration artifact**: changelog, Liquibase CLI/runtime, JDBC driver và extension.

Khi tách, manifest phải ghi rõ migration artifact nào tương thích với application release nào. Không để application version 2.4 chạy với schema release 2.2 nếu mapping cần cột mới. Cũng không chạy migration artifact mới trước khi các điều kiện rollout và tương thích được xác nhận.

## 10. Đóng gói OCI image

Với nền tảng container, image có thể chứa Liquibase CLI và changelog. Quy tắc quan trọng:

- Pin base image theo version và digest.
- Pin Liquibase, driver và extension.
- Chỉ copy resource cần thiết.
- Không copy file .env, password hoặc private key vào image.
- Chạy bằng user không phải root nếu khả thi.
- Không ghi credential trong Docker build ARG/ENV.
- Quét image và dependency trước khi phát hành.
- Gắn version tag và lưu digest.
- Dùng digest trong deployment manifest.

Image tag có thể được dùng để đọc, nhưng pipeline nên xác minh và triển khai đúng digest đã kiểm thử. Không build image lại ở production để thay cấu hình kết nối; cấu hình môi trường được inject khi chạy.

## 11. CI: validate, kiểm thử và tạo artifact

Pipeline CI nên kiểm tra changelog trước khi đóng gói. Một luồng mẫu:

~~~text
Commit / Pull Request
        |
        v
Static checks
        |
        v
Liquibase validate
        |
        v
Generate SQL preview
        |
        v
Provision disposable database
        |
        v
Run update and verify schema/data
        |
        v
Test rollback where applicable
        |
        v
Package changelog + runtime + dependencies
        |
        v
Generate manifest, digest, SBOM/provenance
        |
        v
Publish immutable artifact
~~~

Các bước quan trọng:

1. Kiểm tra format, YAML/XML và include path.
2. Chạy Liquibase validate với đúng runtime/driver.
3. Sinh SQL preview cho DBMS mục tiêu.
4. Chạy migration trên database tạm đúng DBMS/version.
5. Kiểm tra schema, dữ liệu, constraint và ứng dụng.
6. Thử rollback trên database có thể hủy.
7. Đóng gói tất cả resource và dependency.
8. Tạo manifest, digest, SBOM và provenance.
9. Kiểm tra nội dung artifact trước khi publish.
10. Lưu artifact bất biến trong registry.

CI không nên chỉ validate changelog bằng dependency trong IDE rồi đóng gói một tập file khác. Bài test cuối nên chạy bằng chính artifact được tạo, hoặc ít nhất xác minh artifact chứa đúng resource và dependency đã kiểm thử.

### 11.1. Kiểm thử từ database trống và database nâng cấp

Hai trạng thái cần được kiểm tra:

- **Database trống**: toàn bộ master changelog có thể tạo schema mới.
- **Database nâng cấp**: changeset mới chạy được từ baseline/version cũ có dữ liệu.

Một gói có thể chạy trên database trống nhưng thất bại khi upgrade vì precondition, dữ liệu NULL, constraint cũ hoặc object đã tồn tại. Ghi lại kết quả test theo DBMS/version trong metadata release.

### 11.2. Kiểm thử rollback

Nếu changeset có rollback, thử trên database tạm và kiểm tra trạng thái sau rollback. Với migration dữ liệu hoặc DDL không thể đảo an toàn, cần ghi rõ giới hạn và phương án roll-forward/restore.

Không tuyên bố artifact rollback được hoàn toàn chỉ vì lệnh rollback sinh được SQL. Cần xác minh dữ liệu có được bảo toàn và ứng dụng version nào tương thích với schema sau rollback.

## 12. CD: promote cùng một artifact qua các môi trường

Một nguyên tắc quan trọng là **build once, promote many**: artifact đã kiểm thử ở CI phải được đưa qua dev, staging và production mà không rebuild nội dung.

~~~text
Artifact 2.4.0 (digest SHA-256 X)
          |
          v
Development deployment
          |
          v
Verify migration and application
          |
          v
Staging deployment (same digest X)
          |
          v
Approval / release gate
          |
          v
Production deployment (same digest X)
          |
          v
Record artifact digest + changeset history
~~~

Chỉ cấu hình theo môi trường thay đổi:

- JDBC URL và database/schema đích.
- Secret và identity được cấp.
- TLS trust configuration.
- Context/label hoặc tham số release được phê duyệt.
- Timeout, lock wait và cửa sổ triển khai.
- Approval/maintenance window.

Không thay changelog hoặc driver trong gói sau khi staging đã xác nhận. Nếu cần sửa, tạo version artifact mới, chạy lại CI và promote version mới qua quy trình.

### 12.1. Registry và retention

Lưu artifact ở package registry, artifact repository hoặc OCI registry được tổ chức quản lý. Cần version/tag bất biến; quyền publish tách với quyền deploy; audit download và promotion; retention đủ lâu để điều tra; replication/backup registry nếu cần; digest được lưu trong deployment record; và không xóa version đang được database hoặc release record tham chiếu.

Không phụ thuộc vào file ZIP nằm trong workspace của runner đã kết thúc.

## 13. Cấu hình môi trường và secret bên ngoài artifact

Artifact phải portable. Không đóng gói credential hoặc URL production. Có thể truyền tham số khi chạy qua environment, secret manager, workload identity hoặc file cấu hình runtime có kiểm soát.

Ví dụ config template không có password:

~~~properties
changeLogFile=changelog/db.changelog-master.yaml
url=jdbc:postgresql://DB_HOST:5432/DB_NAME
username=liquibase_migrator
# Password được cấp ngoài artifact tại runtime
~~~

Đây chỉ là template. Không dùng literal DB_HOST hoặc placeholder chưa được resolve để chạy production. Pipeline phải xác minh biến cấu hình bắt buộc có giá trị và trỏ tới endpoint được phép trước khi gọi Liquibase.

### 13.1. Tách cấu hình và secret

| Dữ liệu | Đặt ở đâu |
|---|---|
| Changelog và SQL migration | Artifact có version |
| Liquibase version, driver, extension | Artifact/manifest |
| JDBC URL không có credential | Cấu hình môi trường hoặc deployment config |
| Username | Secret/config store theo chính sách |
| Password/token | Secret manager hoặc workload identity |
| CA certificate công khai | Trust bundle được quản lý |
| Private key và keystore password | Secret store/secure mount |
| Context/label được duyệt | Release parameters có audit |

Không ghi giá trị secret vào manifest, artifact metadata, shell history hoặc CI output. Secret rotation không nên yêu cầu build lại artifact nếu chỉ thay đổi credential runtime.

## 14. Chạy migration bằng đúng artifact

Khi deploy, pipeline nên lấy version hoặc digest cụ thể, xác minh tính toàn vẹn rồi chạy. Các lệnh minh họa:

~~~bash
liquibase --version
liquibase --changelog-file=changelog/db.changelog-master.yaml validate
liquibase --changelog-file=changelog/db.changelog-master.yaml update-sql
liquibase --changelog-file=changelog/db.changelog-master.yaml update
~~~

Các tùy chọn kết nối và đường dẫn phải khớp phiên bản CLI và layout artifact. Không copy lệnh mẫu mà bỏ qua cấu hình JDBC driver, classpath hoặc secret injection.

Trước update:

- Xác nhận artifact version và digest.
- Xác nhận manifest/target DBMS tương thích.
- Xác nhận changelog entry point có trong artifact.
- Kiểm tra kết nối TLS và identity.
- Xác nhận tài khoản migration có quyền đúng.
- Chạy validate và SQL preview.
- Kiểm tra lock và cửa sổ triển khai.
- Xác nhận backup/restore readiness theo mức độ rủi ro.
- Yêu cầu approval nếu release policy cần.

Sau update:

- Kiểm tra DATABASECHANGELOG và trạng thái lock.
- Kiểm tra schema/data invariant.
- Chạy smoke test và application compatibility check.
- Lưu artifact digest, commit, environment, thời gian và changeset đã áp dụng.
- Không đánh dấu release thành công chỉ vì process trả exit code 0 nếu kiểm tra hậu triển khai chưa hoàn tất.

## 15. Quản lý artifact khi có nhiều DBMS

Nếu module hỗ trợ nhiều DBMS, cần xác định artifact chung hay artifact riêng.

| Mô hình | Ưu điểm | Điều kiện |
|---|---|---|
| **Một artifact đa DBMS** | Một version changelog và runtime dễ promote | Phải chứa/resolve đúng driver và có kiểm thử riêng cho từng DBMS |
| **Artifact theo DBMS** | Dependency và cấu hình cụ thể, ít thành phần thừa | Cần liên kết version, commit và release record giữa các gói |
| **Artifact chung, runtime driver ngoài** | Gói nhỏ hơn | Driver version phải được pin và kiểm soát ngoài gói; giảm tính tự chứa |

Nếu changeset dùng thuộc tính dbms, precondition hoặc SQL đặc thù, pipeline phải kiểm tra từng target. Không chỉ kiểm thử PostgreSQL rồi tuyên bố artifact hỗ trợ MySQL/SQL Server.

Manifest nên liệt kê DBMS, phiên bản được hỗ trợ, driver version, extension và kết quả test tương ứng. Một release có thể được promote tới nhiều môi trường dùng cùng DBMS; nếu khác DBMS, cần chứng cứ tương thích riêng.

## 16. Versioning changelog và versioning application

Version artifact migration và version application có thể khác nhau. Một ứng dụng release 5.7 có thể yêu cầu schema tối thiểu 5.4; một ứng dụng cũ vẫn chạy trên schema 5.5 trong thời gian rolling deployment.

Nên ghi quan hệ tương thích:

~~~text
Application release: 5.7.0
Migration artifact: 2.4.0
Schema baseline: 2.3
Schema target: 2.4
Supported DBMS: PostgreSQL 16
~~~

Các giá trị trên chỉ minh họa. Hệ thống thực tế cần quy ước version và compatibility matrix rõ ràng.

Không dùng một con số version duy nhất cho tất cả thành phần nếu chúng có vòng đời độc lập. Nhưng deployment record phải liên kết được application artifact, migration artifact, database environment, Liquibase runtime/driver, changeset đã áp dụng, commit nguồn và digest.

### 16.1. Expand-contract và rolling deployment

Artifact migration có thể được phát hành trước application artifact:

1. Thêm cột/bảng mới theo cách tương thích ngược.
2. Deploy application có thể đọc/ghi cấu trúc mới.
3. Backfill và kiểm tra dữ liệu.
4. Chuyển toàn bộ reader/writer.
5. Phát hành artifact migration khác để loại bỏ cấu trúc cũ.

Không gộp bước expand và contract vào cùng một migration nếu application cũ còn cần schema cũ. Artifact version giúp xác định chính xác bước schema nào đã được promote và khi nào.

## 17. Rollback và khôi phục artifact

Giữ artifact cũ trong registry giúp điều tra và tái hiện migration, nhưng không có nghĩa có thể chạy lại artifact cũ để tự động đảo database.

Rollback phụ thuộc:

- Changeset có rollback logic hay không.
- Có dữ liệu mới được ghi sau migration không.
- Object mới có bị application version khác sử dụng không.
- Database có backup/PITR phù hợp không.
- Artifact rollback có tương thích với schema hiện tại không.
- Liquibase history và logical file path có còn nhất quán không.

Quy trình rollback cần dùng đúng artifact, đúng phiên bản công cụ và tham số release đã kiểm tra. Với changeset không thể đảo an toàn, chọn roll-forward hoặc restore theo kế hoạch được phê duyệt.

### 17.1. Giữ artifact và manifest của release trước

Không xóa artifact cũ ngay sau khi production deploy. Lưu đủ lâu để tái hiện nội dung đã chạy, xác minh digest và dependency, điều tra lỗi migration, thực hiện rollback/roll-forward đã được phê duyệt và đối chiếu với DATABASECHANGELOG.

Artifact cũ không thay thế backup dữ liệu. Cần retention riêng cho artifact, log và backup.

## 18. Bảo mật và supply-chain của artifact

Artifact migration có quyền tác động trực tiếp tới database. Người có thể thay changelog, CLI hoặc driver có thể thay đổi SQL được thực thi. Vì vậy:

- Chỉ pipeline được bảo vệ mới được publish release artifact.
- Tách quyền ghi registry và quyền deploy production.
- Bảo vệ branch/tag và workflow release.
- Review changeset và SQL preview.
- Quét dependency và image.
- Sinh SBOM/provenance.
- Ký artifact hoặc image nếu tổ chức yêu cầu.
- Xác minh chữ ký/digest trước deploy.
- Chạy migration bằng identity riêng có quyền tối thiểu.
- Không chứa secret trong ZIP/JAR/image.
- Lưu audit ai publish, approve và deploy artifact.

Không chạy artifact do pull request chưa tin cậy tạo ra bằng credential production. CI có thể kiểm thử với database tạm và credential thử nghiệm; production secret chỉ được cấp trong release workflow đã được bảo vệ.

## 19. Chẩn đoán lỗi đóng gói và phát hành

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| CI validate được, deployment không tìm thấy changelog | Artifact thiếu resource hoặc entry point khác | Kiểm tra ZIP/JAR/image và manifest |
| Master có nhưng SQL file missing | File phụ trợ không được đóng gói | Kiểm tra include/sqlFile và danh sách artifact |
| Local chạy, runner lỗi driver | JDBC driver không nằm trong classpath artifact | Pin và đóng gói driver đúng runtime |
| Extension không được nhận diện | Extension thiếu hoặc không tương thích Liquibase | Kiểm tra version và classpath |
| Staging và production có kết quả khác | Hai môi trường dùng artifact/tool khác nhau | So sánh digest, manifest và deployment record |
| Artifact cùng version nhưng nội dung khác | Registry cho phép ghi đè version | Bật immutable version và phát hành version mới |
| JAR chạy được, CLI lỗi | CLI dùng runtime/classpath khác application | Khóa và kiểm thử CLI độc lập |
| Container chạy trên máy này nhưng không chạy máy khác | Base image/architecture hoặc dependency khác | Pin image digest và platform |
| Changelog bị chạy lại sau di chuyển folder | Logical path/changeset identity thay đổi | Kiểm tra logicalFilePath và DATABASECHANGELOG |
| Digest mismatch | Artifact bị thay đổi hoặc tải nhầm | Dừng deploy, lấy lại artifact từ registry tin cậy |
| Production thiếu biến kết nối | Runtime config/secret chưa được cấp | Kiểm tra binding secret và preflight |
| Rollback không tương thích | Artifact cũ không thể đảo dữ liệu/schema hiện tại | Chọn roll-forward/restore theo kế hoạch |

### 19.1. Quy trình điều tra

1. Lấy artifact version và digest từ deployment record.
2. Tải đúng artifact từ registry và xác minh digest.
3. Đọc manifest để xác định entry point, Liquibase version, driver và extension.
4. Kiểm tra resource changelog/SQL có trong gói.
5. Xác minh runtime Java/OS/architecture.
6. Xác minh cấu hình kết nối đã được inject mà không in secret.
7. Chạy validate bằng đúng artifact.
8. So sánh Liquibase log và DATABASECHANGELOG của môi trường.
9. Nếu artifact không đúng, dừng deploy và phát hành bản mới qua CI.
10. Nếu artifact đúng nhưng DB lỗi, chuyển sang điều tra schema, quyền, dữ liệu và SQL.

Không sửa trực tiếp file bên trong artifact đã publish để chạy cho qua. Mọi sửa đổi phải tạo artifact mới, có version/digest và kiểm thử lại.

## 20. Bài thực hành: đóng gói và promote migration artifact

**Bối cảnh:** Nhóm có ứng dụng Spring Boot dùng PostgreSQL. Muốn phát hành một migration độc lập để tạo bảng customer, thêm index và tạo view. CI cần tạo artifact version 2.4.0; CD promote cùng gói qua development, staging và production.

### Bước 1 — Chuẩn bị changelog

Tạo master changelog, changelog con và SQL file nếu cần. Đảm bảo include path ổn định, ID/author duy nhất và rollback được review.

### Bước 2 — Khóa runtime

Chọn Liquibase CLI/core, Java runtime, PostgreSQL JDBC driver và extension. Ghi version chính xác trong build configuration. Không dùng latest hoặc version range không kiểm soát.

### Bước 3 — Tạo package

Đóng gói CLI, dependency, changelog, SQL, manifest và launcher thành ZIP hoặc OCI image. Kiểm tra gói không chứa password, token, private key hoặc config production.

### Bước 4 — Kiểm thử artifact

Dùng đúng artifact vừa build để kiểm tra version Liquibase, chạy validate, sinh SQL preview, chạy update trên PostgreSQL tạm, kiểm tra bảng/index/view và DATABASECHANGELOG, thử rollback trên database test, xác minh mọi resource có trong package.

### Bước 5 — Tạo metadata

Ghi version, source commit, build ID, entry point, driver version, Liquibase version, target DBMS, SHA-256 và SBOM/provenance theo chính sách.

### Bước 6 — Publish bất biến

Publish liquibase-migration:2.4.0 vào registry. Lưu digest và ngăn ghi đè cùng version.

### Bước 7 — Promote

- Development: tải artifact 2.4.0, xác minh digest, chạy migration và kiểm tra ứng dụng.
- Staging: dùng đúng digest đã chạy ở development; chạy preflight, approval và smoke test.
- Production: tải cùng digest, lấy secret production qua secret manager, chạy migration job và xác minh sau deploy.

### Bước 8 — Ghi deployment record

Lưu artifact version/digest, commit, DBMS, Liquibase version, environment, người/job phê duyệt, thời gian, changeset đã áp dụng và kết quả hậu kiểm.

### Bước 9 — Thử xử lý sự cố

Tạo một bản artifact test bị thiếu SQL file và xác nhận preflight phát hiện trước khi update. Tạo một digest không khớp và xác nhận pipeline dừng. Không dùng production để thử lỗi đóng gói.

## 21. Checklist review artifact trước release

- Artifact có version bất biến và không bị ghi đè?
- Manifest có source commit, build ID, entry point và runtime version?
- Liquibase CLI/core đã được pin?
- Java runtime và JDBC driver tương thích DBMS mục tiêu?
- Extension và dependency đã được pin, kiểm tra xung đột?
- Master changelog, changelog con, SQL, CSV và resource phụ trợ đều có trong package?
- Resource path và logicalFilePath được giữ ổn định?
- Artifact có chứa secret hoặc private key không?
- Cấu hình theo môi trường được inject khi chạy?
- Digest SHA-256 được lưu ở nơi tin cậy và xác minh trước deploy?
- SBOM/provenance/chữ ký được tạo và kiểm tra theo chính sách?
- Validate và SQL preview chạy bằng đúng artifact?
- Có test database trống và database nâng cấp?
- Rollback/roll-forward được kiểm tra và ghi rõ giới hạn?
- Artifact đã được publish vào registry có retention và audit?
- Dev, staging và production dùng cùng digest?
- Deployment record liên kết application version, migration artifact và DATABASECHANGELOG?
- Quyền publish và quyền deploy production được tách?
- CI không cấp secret production cho mã chưa tin cậy?
- Runtime image/CLI không phụ thuộc file có sẵn trên runner?
- Có quy trình phát hành artifact mới khi cần sửa, không thay nội dung version đã publish?

**Kết luận:** Đóng gói changelog và công cụ thành artifact có phiên bản giúp Liquibase migration có thể tái hiện, kiểm toán và promote nhất quán. Artifact cần chứa entry point, toàn bộ changelog/SQL phụ trợ, Liquibase runtime, JDBC driver, extension và manifest; version cùng digest xác định chính xác nội dung đã kiểm thử. CI phải validate và thử migration bằng chính gói đó; CD promote cùng digest qua các môi trường, chỉ inject cấu hình và secret theo môi trường khi chạy. Kết hợp versioning bất biến, dependency pinning, kiểm tra chữ ký/digest, quyền tối thiểu và deployment record sẽ giúp quản lý schema/data an toàn trong quy trình Spring Boot hoặc CI/CD.

