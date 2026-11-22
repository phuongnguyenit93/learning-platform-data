# Đóng gói changelog cùng phiên bản phát hành

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở chương **Cộng tác**, việc đóng gói changelog cùng phiên bản phát hành bảo đảm đội phát triển, kiểm thử và vận hành triển khai **đúng một bộ định nghĩa migration đã được review và kiểm chứng**, thay vì vô tình chạy một file khác với file đã được build hoặc phê duyệt.

Một release không chỉ có mã ứng dụng. Nó còn phụ thuộc vào root changelog, các changelog được include, SQL/CSV được tham chiếu, extension cần thiết và cấu hình runtime để Liquibase hiểu đúng những thay đổi cần chạy. Nếu thiếu một file, dùng nhầm phiên bản changelog hoặc chỉnh file sau khi preview, kết quả triển khai có thể khác với kết quả kiểm thử.

Nguyên tắc xuyên suốt là: **đóng gói đầy đủ dependency của migration thành artifact có phiên bản, giữ artifact bất biến sau khi phát hành, và dùng chính artifact đó từ bước kiểm thử đến bước triển khai từng môi trường**.

## 1. Vì sao changelog phải đi cùng phiên bản phát hành?

Giả sử phiên bản ứng dụng 2.4.0 yêu cầu thêm cột orders.delivery_status. Pull request đã được review, pipeline chạy thử changelog và tạo SQL preview. Nhưng khi triển khai production, một người vận hành lấy file changelog mới nhất từ nhánh main thay vì file trong artifact 2.4.0.

Có thể xảy ra các tình huống:

- Production chạy một changeset mới hơn chưa được kiểm thử trong release.
- Changelog gọi đến một file sqlFile không có trong thư mục triển khai.
- SQL preview được tạo từ commit A nhưng update lại chạy từ commit B.
- Một file CSV đã bị sửa sau khi test, khiến dữ liệu seed khác với dự kiến.
- Phiên bản Liquibase hoặc extension khác với phiên bản đã dùng trong pipeline.
- Changelog path thay đổi làm Liquibase nhận diện changeset khác với lịch sử đã ghi nhận.
- Một môi trường chạy migration bằng resource trong JAR, môi trường khác dùng file rời trong workspace.

Việc gắn changelog vào release giúp xác định **mã ứng dụng nào yêu cầu schema nào**, **artifact nào đã được kiểm thử**, và **database đã được cập nhật bằng đúng bộ migration nào**.

### 1.1. Ba thứ cần liên kết trong một release

| Thành phần | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Application artifact | Binary nào sẽ chạy? | Version, commit, digest của JAR/container image |
| Migration artifact | Root changelog và toàn bộ tài nguyên nào sẽ được dùng? | Version, commit, digest, manifest nội dung |
| Deployment configuration | Artifact được chạy trên DBMS/môi trường nào, với filter nào? | DBMS/version, root path, context/label, properties đã redacted |

Có dự án đóng gói changelog ngay trong Spring Boot JAR; có dự án tạo một migration bundle hoặc container riêng. Cả hai đều có thể phù hợp. Điều quan trọng là **quan hệ phiên bản và nguồn gốc phải rõ ràng**, không để deployment tự lấy changelog mới nhất từ một thư mục dùng chung.

### 1.2. Artifact bất biến sau khi phát hành

Khi artifact đã được kiểm thử và phê duyệt, không chỉnh trực tiếp nội dung bên trong để sửa lỗi triển khai. Nếu cần thay đổi changelog hoặc SQL:

1. Tạo commit hoặc bản sửa mới.
2. Build artifact mới.
3. Chạy lại validation và kiểm thử.
4. Gắn version/digest mới.
5. Phát hành theo quy trình phê duyệt.

Không dùng cùng một nhãn latest hoặc một URL tải xuống có nội dung thay đổi để đại diện cho migration đã kiểm thử. Một version number không đủ nếu hệ thống cho phép ghi đè artifact cùng version; nên lưu digest hoặc checksum của artifact để xác minh tính bất biến.

## 2. Changelog là một tập tài nguyên, không chỉ một file YAML

Một root changelog có thể tham chiếu nhiều loại tài nguyên. Ví dụ cấu trúc dự án:

~~~text
db/
  changelog/
    db.changelog-master.yaml
    schema/
      001-create-customers.yaml
      002-create-orders.yaml
      003-add-order-constraints.yaml
    data/
      010-seed-reference-data.yaml
      reference/
        order-status.csv
    sql/
      create-order-report-view.sql
      create-orders-trigger.sql
      rollback-orders-trigger.sql
    functions/
      normalize-order-code.sql
~~~

Root changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/schema/001-create-customers.yaml
  - include:
      file: db/changelog/schema/002-create-orders.yaml
  - include:
      file: db/changelog/schema/003-add-order-constraints.yaml
  - include:
      file: db/changelog/data/010-seed-reference-data.yaml
  - include:
      file: db/changelog/objects/020-create-report-view.yaml
~~~

Ví dụ chỉ minh họa cách phân chia. Các đường dẫn phải khớp với cấu trúc thực tế và cách Liquibase resolve resource. Một changelog con lại có thể include file khác; vì vậy, phải đóng gói **toàn bộ cây dependency**, không chỉ root file.

Các tài nguyên thường phải có trong artifact:

- Root changelog và mọi file include/includeAll được chọn.
- File SQL được tham chiếu bằng sqlFile.
- CSV hoặc file dữ liệu được dùng bởi loadData/loadUpdateData.
- File properties hoặc cấu hình cần thiết, nếu đó là cấu hình không nhạy cảm và được quản lý theo release.
- Extension Liquibase, driver JDBC hoặc thư viện cần để thực thi change type đặc thù.
- Script rollback, snapshot hoặc tài liệu phục hồi nếu quy trình phát hành yêu cầu đóng gói chúng.
- Metadata release giúp liên kết artifact với commit, version và digest.

**Một file YAML parse được không chứng minh artifact đầy đủ.** Chỉ khi mọi resource được tham chiếu đều tồn tại ở đúng vị trí trong artifact và có thể được Liquibase nạp, gói migration mới đủ điều kiện kiểm thử.

## 3. Chọn mô hình đóng gói

Có hai mô hình phổ biến.

### 3.1. Đóng gói changelog cùng application artifact

Với Spring Boot, changelog thường nằm trong classpath, ví dụ:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      schema/
        001-create-customers.yaml
      sql/
        create-order-report-view.sql
      data/
        order-status.csv
~~~

Cấu hình:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Khi build ứng dụng, các resource trong src/main/resources được đưa vào JAR theo cấu hình build. Spring Boot/Liquibase có thể đọc changelog từ classpath trong artifact.

Ưu điểm:

- Mã ứng dụng và changelog được phát hành cùng version.
- Giảm nguy cơ dùng nhầm changelog từ workspace hoặc thư mục bên ngoài.
- Một artifact có thể được kiểm thử và triển khai xuyên suốt các môi trường.
- Dễ truy ngược changelog về commit tạo ra JAR.

Hạn chế:

- Artifact ứng dụng có thể phải build lại chỉ để phát hành một thay đổi database độc lập.
- Nếu migration job cần quyền cao hơn runtime, không nên tự động trao quyền DDL cho mọi instance ứng dụng.
- Việc triển khai schema và rollout ứng dụng có thể cần thứ tự riêng.

### 3.2. Đóng gói thành migration artifact riêng

Một số hệ thống tạo bundle hoặc container chuyên chạy Liquibase:

~~~text
release/
  migration/
    db/
      changelog/
        db.changelog-master.yaml
        schema/
        data/
        sql/
    liquibase.properties.template
    release-manifest.yaml
~~~

Migration artifact có version riêng nhưng phải được liên kết rõ với application release mà nó phục vụ. CI/CD tải artifact đã được phê duyệt, chạy validate/status/update-sql, sau đó update bằng cùng artifact.

Ưu điểm:

- Tách quyền migration khỏi quyền runtime.
- Có thể phát hành schema trước hoặc sau ứng dụng theo chiến lược rollout.
- Dễ kiểm soát phiên bản Liquibase, JDBC driver và extension trong một môi trường thực thi chuyên biệt.
- Có thể triển khai migration qua một job duy nhất thay vì để nhiều instance tự chạy.

Hạn chế:

- Phải quản lý tương thích giữa version ứng dụng và version migration.
- Cần bảo đảm resource paths được đóng gói đúng.
- Có thêm một artifact và quy trình phát hành cần theo dõi.
- Không được để migration bundle trôi khỏi application release hoặc bị thay thế không kiểm soát.

### 3.3. Chọn mô hình theo cách vận hành

| Tiêu chí | Cùng application JAR/image | Migration bundle riêng |
|---|---|---|
| Liên kết version | Trực tiếp theo application release | Qua manifest/release metadata |
| Quyền DDL | Cần tách cấu hình và quyền nếu runtime cũng có Liquibase | Dễ dùng migration role riêng |
| Rollout nhiều instance | Cần điều phối startup/lock | Một job migration có thể chạy trước rollout |
| Phát hành DB độc lập | Ít linh hoạt hơn nếu phải build app | Linh hoạt hơn |
| Truy vết | Một artifact chứa cả app và changelog | Phải lưu quan hệ giữa hai artifact |
| Rủi ro chính | Runtime tự chạy migration không mong muốn | Migration artifact lệch version ứng dụng |

Không có mô hình duy nhất cho mọi hệ thống. Hãy chọn theo quyền, tần suất thay đổi schema, yêu cầu rollout, khả năng rollback và kiến trúc CI/CD.

## 4. Đóng gói file include đúng đường dẫn

Liquibase cần tìm được file include từ root changelog. Ví dụ:

~~~yaml
databaseChangeLog:
  - include:
      file: schema/001-create-customers.yaml
  - include:
      file: schema/002-create-orders.yaml
~~~

Nếu root changelog ở db/changelog/db.changelog-master.yaml, đường dẫn tương đối trên phải được resolve theo resource accessor/cấu hình của Liquibase. Không tự ý đổi cấu trúc thư mục sau khi đã triển khai.

Khi đóng gói, kiểm tra:

- File con có nằm trong JAR/bundle không?
- Đường dẫn và chữ hoa/thường có khớp không?
- Chạy trên Linux có khác máy Windows không do phân biệt case?
- File có bị loại bởi cấu hình resource filtering hoặc packaging không?
- Include lồng nhau có tìm thấy file tiếp theo không?
- Root changelog đang dùng là file trong artifact hay file rời trên filesystem?

### 4.1. include và includeAll

include khai báo file cụ thể, thuận tiện để review thứ tự dependency và biết rõ tập tài nguyên cần phát hành.

includeAll nạp các changelog từ một thư mục theo quy tắc sắp xếp của Liquibase. Nó tiện cho dự án có quy ước tên file, nhưng dễ tạo bất ngờ nếu:

- Một file tạm hoặc fixture được thêm vào cùng thư mục.
- Một file mới có tên làm thay đổi thứ tự.
- Build artifact chứa thêm file mà source branch hiện tại không có.
- Thư mục bị đóng gói thiếu hoặc có file ngoài phạm vi.

Với migration production, cần giới hạn thư mục includeAll vào vùng được kiểm soát, kiểm tra danh sách file sau build và không trộn changelog test/demo vào cùng một folder.

### 4.2. Giữ thứ tự và định danh lịch sử

Liquibase nhận diện changeset bằng id, author và đường dẫn logic của changelog. Khi di chuyển file hoặc thay đổi cấu trúc include, cần đánh giá logicalFilePath theo khả năng hỗ trợ của phiên bản đang dùng để giữ định danh lịch sử phù hợp.

Không đổi đường dẫn file trong artifact giữa các môi trường. Nếu dev dùng db/changelog/schema/001.yaml còn production dùng một bản copy ở migrations/001.yaml, Liquibase có thể xem filename là khác và nhận diện changeset như một mục mới.

## 5. Đóng gói sqlFile, CSV và tài nguyên dữ liệu

Một changelog có thể parse được nhưng update vẫn thất bại vì file SQL/CSV được tham chiếu không nằm trong artifact.

### 5.1. sqlFile

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: release-020-create-report-view
      author: database-team
      dbms: postgresql
      changes:
        - sqlFile:
            path: sql/create-order-report-view.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: false
~~~

Khi relativeToChangelogFile: true, đường dẫn được resolve tương đối với changelog chứa change theo quy tắc Liquibase. Phải kiểm tra resource thực tế có ở đúng vị trí sau đóng gói.

Các điểm review:

- Nội dung SQL đúng commit và DBMS.
- Encoding và line ending phù hợp.
- splitStatements/endDelimiter phù hợp với function/procedure hoặc script nhiều statement.
- SQL không chứa credentials, token hoặc dữ liệu thật.
- File rollback liên quan cũng có sẵn nếu được tham chiếu.
- Không sửa file SQL sau khi artifact đã được phê duyệt.

### 5.2. loadData và CSV

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: release-021-load-reference-data
      author: database-team
      changes:
        - loadData:
            schemaName: app
            tableName: order_status
            file: data/order-status.csv
            relativeToChangelogFile: true
            encoding: UTF-8
            separator: ","
~~~

CSV là một phần của dependency. Nếu thiếu file, sai encoding, header không khớp hoặc nội dung bị thay sau build, kết quả migration có thể khác với test.

Chỉ đưa reference data hợp lệ vào artifact production. Fixture test cần root changelog và artifact test riêng, hoặc được tạo trong bước test setup. Không đóng gói dữ liệu production export vào bundle migration nếu không có quy trình xử lý và phê duyệt dữ liệu.

### 5.3. Tài nguyên được tham chiếu gián tiếp

Một file include có thể tham chiếu file SQL khác; file SQL có thể gọi function hoặc đối tượng được tạo từ một changeset khác. Manifest tài nguyên nên phản ánh dependency thực tế, không chỉ liệt kê các file trực tiếp dưới root.

Nếu dự án dùng extension hoặc custom change type, extension đó cũng là một dependency của môi trường thực thi. Cùng changelog nhưng chạy bằng bộ extension khác có thể tạo hành vi khác.

## 6. Changelog properties và cấu hình môi trường

Artifact nên chứa **định nghĩa migration ổn định**, còn thông tin thay đổi theo môi trường được cung cấp qua cấu hình runtime phù hợp.

Ví dụ changelog dùng property:

~~~yaml
databaseChangeLog:
  - property:
      name: appSchema
      value: app

  - changeSet:
      id: release-030-create-audit
      author: database-team
      changes:
        - createTable:
            schemaName: \${appSchema}
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Nếu một môi trường cần schema khác, hãy xác định nguồn override và kiểm tra giá trị cuối cùng. Không đóng gói một file properties có password hoặc URL production trong artifact.

### 6.1. Phân biệt nội dung artifact và deployment configuration

| Nội dung | Nên quản lý ở đâu? |
|---|---|
| Root changelog, changeset, SQL, CSV | Source control và migration/application artifact |
| Version Liquibase, extension, driver | Dependency/build/runtime image được khóa phiên bản |
| Database URL theo môi trường | Secret/configuration của môi trường |
| Username/password | Secret manager hoặc cơ chế bảo mật tương đương |
| Context/label | Deployment configuration được review |
| Property như schema name hoặc feature parameter | Cấu hình runtime không nhạy cảm, được ghi nhận theo release |
| Log và SQL preview | Artifact/log store có phân quyền và retention |

Một artifact có thể giống nhau ở dev/staging/production trong khi cấu hình kết nối khác nhau. Điều đó giúp đảm bảo **cùng một định nghĩa migration được thử và phát hành**, nhưng vẫn phải kiểm tra SQL sau property substitution trên từng môi trường.

### 6.2. Không ghép secret vào changelog

Không viết password, access token, private key hoặc credential trực tiếp vào YAML, XML, SQL, CSV hay file properties được commit. Secret có thể bị lưu trong Git history, JAR, container image, log, SQL preview và backup.

Dùng secret manager/biến môi trường được bảo vệ để cung cấp thông tin kết nối lúc chạy. Redact URL và cấu hình khi tạo release manifest hoặc báo cáo CI.

## 7. Giữ changeset và checksum nhất quán giữa artifact

Khi một changeset đã được triển khai, DATABASECHANGELOG lưu định danh và checksum. Nếu artifact mới chứa nội dung changeset đã sửa, Liquibase có thể báo checksum mismatch hoặc nhận diện khác nếu id/author/path thay đổi.

Vì vậy:

- Giữ changeset đã phát hành bất biến.
- Thêm changeset mới cho thay đổi tiếp theo.
- Đóng gói đúng file SQL/CSV đã được kiểm thử.
- Không chỉnh file ngoài sau khi tạo artifact.
- Không copy MD5SUM hoặc bảng DATABASECHANGELOG giữa môi trường.
- Không dùng clear-checksums để hợp thức hóa một artifact bị thay đổi ngoài quy trình.
- Với runOnChange, xác định rõ đối tượng được phép thay thế và hành vi chạy lại.

### 7.1. Vì sao phải dùng cùng artifact cho update-sql và update?

Giả sử update-sql được tạo từ artifact migration-2.4.0 nhưng lệnh update dùng folder workspace mới nhất. Hai lệnh không còn mô tả cùng một nội dung. Reviewer đã phê duyệt SQL của một bộ changeset, nhưng production lại chạy bộ khác.

Quy tắc:

1. Tải hoặc chọn artifact theo version/digest.
2. Chạy validate bằng artifact đó.
3. Chạy status và update-sql bằng cùng root, cùng artifact và cùng filter.
4. Lưu SQL preview cùng release metadata theo chính sách bảo mật.
5. Chạy update bằng đúng artifact và cấu hình đã được phê duyệt.
6. Đối chiếu DATABASECHANGELOG và hậu điều kiện.

Không lấy lại changelog từ Git sau bước preview nếu không chứng minh đó là cùng commit và nội dung.

### 7.2. Chuyển đổi định dạng hoặc đường dẫn là thay đổi cần review

Đổi YAML sang XML, chuyển file sang folder khác, đổi logicalFilePath hoặc đổi cách include có thể ảnh hưởng định danh, parser và checksum. Hãy test trên database có lịch sử trước khi đưa vào release.

## 8. Khóa phiên bản Liquibase và dependency thực thi

Một release cần xác định phiên bản Liquibase, JDBC driver, extension và runtime hỗ trợ changelog.

Ví dụ manifest phụ thuộc (minh họa):

~~~text
Migration runtime:
  Liquibase: <pinned-version>
  Java runtime: <pinned-version>
  JDBC driver: <pinned-version>
  Liquibase extensions: <explicit list and versions>
  Target DBMS: PostgreSQL <supported version range>
~~~

Không dùng phiên bản latest không được khóa trong môi trường production. Nếu CLI và Spring Boot JAR dùng hai phiên bản Liquibase khác nhau, chúng có thể xử lý changelog hoặc checksum khác nhau.

Các bước kiểm soát:

- Pin version Liquibase trong build/dependency management.
- Pin JDBC driver tương thích DBMS.
- Khai báo extension và version cụ thể nếu có.
- Ghi version thực tế vào release manifest.
- Chạy test bằng runtime giống môi trường triển khai.
- Nâng cấp Liquibase như một thay đổi được kiểm thử riêng.
- Không nâng Liquibase đồng thời với refactor lớn changelog nếu khó phân biệt nguyên nhân lỗi.

### 8.1. CLI và Spring Boot phải dùng cùng dependency model

Nếu pipeline dùng Liquibase CLI còn ứng dụng dùng Spring Boot integration, hãy xác nhận version Liquibase và extension tương thích. Một lần validate bằng CLI không đủ chứng minh Spring Boot JAR có thể nạp resource hoặc xử lý changelog giống hệt.

Có thể chọn một migration runner duy nhất (CLI/container hoặc job chuyên dụng) để giảm khác biệt runtime, sau đó tắt auto-migration ở ứng dụng nếu kiến trúc yêu cầu. Nếu Spring Boot tự chạy Liquibase, phải kiểm thử trực tiếp startup từ JAR/image đã build.

## 9. Đóng gói trong Spring Boot JAR

Khi changelog nằm trong src/main/resources, build artifact có thể chứa các file đó trong JAR. Cấu hình thường dùng:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Các file include, SQL và CSV cũng cần được đóng gói vào resource path mà Liquibase có thể truy cập.

Ví dụ cây resource:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      schema/
        001-create-customers.yaml
      sql/
        create-order-report-view.sql
      data/
        order-status.csv
~~~

### 9.1. Kiểm tra nội dung JAR sau build

Không chỉ kiểm tra source folder. Hãy kiểm tra artifact đã build có chứa:

- db/changelog/db.changelog-master.yaml
- Tất cả file YAML/XML/JSON/SQL được include.
- CSV được tham chiếu bởi loadData.
- File properties không nhạy cảm nếu thật sự cần.
- Các resource có đúng case và đường dẫn.

Có thể dùng công cụ liệt kê nội dung JAR hoặc kiểm tra artifact bằng test tự động. Ví dụ lệnh quan sát:

~~~bash
jar tf application.jar
~~~

Đây chỉ là lệnh minh họa để liệt kê nội dung JAR; không thay thế test Liquibase thực tế. Với Spring Boot executable JAR, resource ứng dụng thường nằm dưới BOOT-INF/classes/; vị trí cụ thể cần kiểm tra theo kiểu packaging.

### 9.2. Kiểm tra classpath từ chính artifact

Một test tích hợp nên chạy Liquibase với resource từ JAR đã build, không chỉ từ src/main/resources. Điều này phát hiện:

- File include bị bỏ khỏi artifact.
- Path hoạt động trên filesystem nhưng không hoạt động trong classpath.
- File SQL/CSV không được đóng gói.
- Case-sensitive path lỗi trên Linux.
- Runtime Liquibase trong JAR khác CLI đã dùng để preview.

Không dùng một file changelog tạm ở workspace làm bằng chứng cho artifact đã phát hành.

## 10. Đóng gói migration bundle riêng

Nếu migration được chạy bằng job riêng, một bundle có thể gồm:

~~~text
migration-bundle-2.4.0/
  changelog/
    db.changelog-master.yaml
    schema/
    data/
    sql/
  runtime/
    liquibase-version.txt
    extension-manifest.txt
  release-manifest.yaml
~~~

Các thư mục chỉ là ví dụ. Có thể đóng gói bundle thành ZIP, container image hoặc artifact repository package theo chuẩn của tổ chức.

Yêu cầu:

- Root changelog xác định rõ.
- Toàn bộ resource dependency có mặt.
- Runtime và extension được khóa.
- Không chứa secret hoặc dữ liệu production.
- Version/digest liên kết với application release.
- Có quy trình kiểm tra tính toàn vẹn và quyền tải.
- Bundle không bị ghi đè sau khi phê duyệt.
- Có khả năng truy xuất lại artifact cũ khi cần điều tra hoặc rollback.

Nếu bundle dùng container image, deployment nên tham chiếu image digest hoặc version bất biến thay vì một tag có thể bị di chuyển. Với ZIP/JAR, lưu checksum/digest và metadata trong artifact repository.

## 11. Release manifest: ghi rõ changelog nào thuộc release nào

Một manifest giúp người vận hành và auditor xác định đúng bộ migration. Ví dụ:

~~~yaml
release:
  applicationVersion: "2.4.0"
  applicationCommit: "abc1234"
  applicationArtifact: "orders-service:2.4.0"
  migrationVersion: "2.4.0"
  migrationArtifact: "orders-migration:2.4.0"
  migrationDigest: "sha256:<artifact-digest>"
  liquibaseVersion: "<pinned-version>"
  rootChangelog: "db/changelog/db.changelog-master.yaml"
  dbms:
    product: "PostgreSQL"
    testedVersions:
      - "<supported-version>"
  filters:
    contexts: "prod"
    labels: ""
~~~

Các giá trị trên là placeholder minh họa, không phải version hoặc digest thực. Manifest production không nên chứa password, token, private key hoặc JDBC URL có credential.

Các trường hữu ích khác có thể gồm:

- Commit source của changelog.
- Danh sách resource hoặc digest manifest.
- Phiên bản Java/JDBC driver/extension.
- Build ID, thời điểm tạo artifact và nguồn pipeline.
- Migration job ID và deployment ID.
- Môi trường đã kiểm thử và kết quả test.
- Người phê duyệt, change ticket và liên kết SQL preview đã redacted.
- Tag rollback hoặc recovery artifact nếu quy trình yêu cầu.

### 11.1. Manifest không thay thế chữ ký hoặc quyền truy cập

Một YAML manifest có thể bị sửa giống các file khác. Với hệ thống yêu cầu bảo đảm nguồn gốc, cần artifact repository có kiểm soát, chữ ký hoặc provenance attestation theo nền tảng tổ chức. Kiểm tra digest chỉ chứng minh nội dung khớp digest đã biết; phải bảo vệ nguồn phát hành digest.

## 12. Quy trình phát hành từ build đến production

Một quy trình có thể triển khai:

~~~text
Commit + review
      |
      v
Build application / migration artifact
      |
      v
Kiểm tra root changelog và resource dependencies
      |
      v
Tạo version + digest + release manifest
      |
      v
Fresh-install và upgrade-path test
      |
      v
Validate / status / update-sql bằng artifact đó
      |
      v
Review SQL + phê duyệt
      |
      v
Triển khai staging bằng cùng artifact
      |
      v
Kiểm tra schema, data, application
      |
      v
Promote cùng artifact sang production
      |
      v
Update + hậu kiểm + lưu lịch sử release
~~~

**Promote artifact** nghĩa là dùng lại đúng artifact đã được kiểm thử, không build lại từ source khác hoặc lấy changelog mới nhất ở từng môi trường. Cấu hình kết nối/secret có thể thay đổi theo môi trường; nội dung migration artifact phải giữ nguyên.

### 12.1. Tại sao không build lại khi lên production?

Nếu build lại, dù cùng tag Git, đầu ra có thể khác do dependency không khóa, resource filtering, timestamp, biến môi trường build hoặc thay đổi trong pipeline. Khi đó digest và nội dung có thể không còn là artifact đã được staging kiểm thử.

Thực hành tốt là build một lần, kiểm tra artifact, lưu vào repository và promote cùng digest qua các môi trường. Nếu buộc phải build lại, phải coi đó là artifact mới và chạy lại các cổng kiểm tra cần thiết.

### 12.2. SQL preview và update phải dùng cùng cấu hình

Cùng artifact nhưng khác context, label, DBMS hoặc property có thể sinh tập changeset/SQL khác. Do đó, lưu lại cấu hình không nhạy cảm dùng cho preview và update. Đối chiếu root changelog, version, filter và giá trị property trước khi thực thi.

Không đưa secrets vào manifest hoặc log để chứng minh cấu hình; dùng reference/secret version đã redacted.

## 13. Fresh-install và upgrade-path phải chạy trên artifact đã đóng gói

Có hai luồng kiểm thử chính:

### Fresh install

1. Tạo database test mới.
2. Dùng root changelog trong artifact đã build.
3. Chạy validate/status/update-sql/update.
4. Kiểm tra bảng, cột, constraint, index, sequence, view, function và dữ liệu tham chiếu.
5. Chạy update lần hai để kiểm tra không tạo thay đổi ngoài dự kiến.
6. Chạy smoke test ứng dụng từ artifact tương ứng.

### Upgrade path

1. Tạo database từ artifact/release cũ hoặc snapshot đại diện.
2. Ghi nhận lịch sử DATABASECHANGELOG ban đầu.
3. Chạy artifact migration mới.
4. Kiểm tra changeset pending, SQL preview và checksum.
5. Xác minh dữ liệu cũ được bảo toàn/chuyển đổi đúng.
6. Chạy ứng dụng mới và kiểm tra tương thích.
7. Thử rollback/forward-fix trên bản sao nếu phạm vi yêu cầu.

Cả hai luồng phải dùng **chính artifact dự kiến phát hành**. Test từ source folder rồi deploy JAR/bundle khác không kiểm tra được packaging errors.

## 14. CI/CD: xác minh artifact và dependency trước update

Các cổng pipeline nên bao gồm:

| Giai đoạn | Kiểm tra |
|---|---|
| Source review | Changeset cũ có bị sửa? Có resource mới chưa được include? |
| Build | Artifact chứa root changelog và mọi file dependency |
| Dependency | Liquibase, JDBC driver và extension được pin |
| Integrity | Digest/manifest được tạo và lưu |
| Static validation | Không có secret, fixture hoặc file dữ liệu không được phép |
| Fresh test | Database mới dựng thành công bằng artifact |
| Upgrade test | Database cũ nâng cấp thành công bằng artifact |
| Preview | validate/status/update-sql với đúng runtime/config |
| Staging | Promote cùng artifact/digest, kiểm tra hậu điều kiện |
| Production | Phê duyệt, đúng DB đích, update và hậu kiểm |
| Audit | Lưu version, digest, commit, exit code và deployment evidence |

### 14.1. Kiểm tra resource dependency tự động

Một pipeline có thể:

- Parse root changelog và thu thập include.
- Theo dõi include lồng nhau và includeAll.
- Thu thập path của sqlFile, loadData và resource liên quan.
- Xác nhận từng path có mặt trong artifact.
- So sánh digest resource trong build manifest.
- Từ chối artifact nếu có dependency thiếu.
- Kiểm tra root production không include fixture/test path.
- Chạy một smoke test Liquibase từ artifact đã đóng gói.

Việc parse dependency cần hiểu định dạng changelog và cách Liquibase resolve resource; không chỉ tìm chuỗi .sql bằng grep. Với dynamic/custom resource accessor hoặc extension, cần test tích hợp bổ sung.

### 14.2. Không bỏ qua lỗi packaging vì source test đã qua

Một unit test trên source có thể thấy file trong src/main/resources, nhưng packaging rule có thể loại nó khỏi JAR. Do đó, kiểm thử artifact phải thực sự nạp changelog từ JAR/container hoặc migration bundle sau khi build.

### 14.3. Job migration phải truyền exit code

Nếu pipeline gọi Liquibase qua script hoặc wrapper, phải giữ exit code. Không dùng continue-on-error cho migration bắt buộc rồi vẫn promote ứng dụng. Khi update thất bại, database có thể đã thay đổi một phần tùy DBMS/transaction; dừng rollout và kiểm tra trạng thái trước khi retry.

## 15. Spring Boot: kiểm soát version và thời điểm migration

Khi Spring Boot tự chạy Liquibase lúc khởi động, changelog được nạp từ classpath hoặc resource path cấu hình. Artifact ứng dụng và migration vì vậy gắn chặt với nhau.

Ví dụ:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    contexts: prod
~~~

Các điểm cần review:

- Root changelog có thực sự nằm trong JAR không?
- Các file include/sqlFile/CSV có cùng classpath tương đối không?
- Liquibase dependency trong JAR có đúng version đã test không?
- Profile active và context có đúng môi trường không?
- Runtime instance có quyền DDL không?
- Nhiều instance có cùng artifact và metadata schema không?
- Nếu migration job riêng đã chạy, ứng dụng có vô tình chạy lại với cấu hình khác không?

### 15.1. Migration job riêng trước rollout

Với hệ thống nhiều instance, có thể dùng một job migration chuyên trách:

1. Chọn migration artifact cùng application release.
2. Chạy job với migration role.
3. Kiểm tra exit code, history và hậu điều kiện.
4. Chỉ rollout ứng dụng khi schema tương thích.
5. Runtime role chỉ có quyền cần thiết cho hoạt động ứng dụng.
6. Tắt auto-migration ở runtime nếu thiết kế đã giao trách nhiệm cho job riêng.

Không có một lựa chọn đúng cho mọi hệ thống. Điều quan trọng là **một nguồn điều phối rõ ràng**, không để nhiều runner khác nhau dùng changelog hoặc version khác nhau.

## 16. Quản lý rollback artifact và lịch sử release

Đóng gói changelog theo release giúp truy xuất migration cũ, nhưng không có nghĩa rollback chỉ cần lấy artifact cũ và chạy lại. DATABASECHANGELOG đã ghi nhận changeset; Liquibase sẽ không tự thực thi ngược nội dung chỉ vì dùng một artifact cũ.

Cần chuẩn bị:

- Artifact của release trước và release hiện tại.
- Changelog/SQL rollback được review nếu có.
- Tag hoặc phạm vi rollback được xác định.
- Backup/snapshot/PITR khi thay đổi có nguy cơ mất dữ liệu.
- Phiên bản ứng dụng tương thích với schema sau rollback.
- Kế hoạch forward-fix nếu rollback không an toàn.
- Hướng dẫn phục hồi resource và dependency.

### 16.1. Không chỉnh artifact cũ để làm rollback

Giữ artifact đã phát hành bất biến. Nếu cần sửa rollback script hoặc bổ sung forward-fix, tạo một artifact mới có version/digest mới, kiểm thử và phê duyệt.

### 16.2. Rollback SQL cũng là một dependency

Nếu rollback được khai báo trong changeset, nội dung rollback thường nằm cùng changelog. Nếu dùng file SQL ngoài hoặc script vận hành riêng, cần đóng gói và lưu version của nó cùng release metadata. Không dựa vào một file rollback trên máy cá nhân hoặc thư mục chia sẻ có thể bị sửa.

### 16.3. Artifact cũ không bảo đảm database có thể quay lại

Một release cũ có thể không tương thích với schema mới hoặc dữ liệu đã được chuyển đổi. Trước rollback ứng dụng, kiểm tra khả năng tương thích. Nếu migration đã drop cột hoặc biến đổi dữ liệu mất thông tin, cần restore/forward-fix thay vì chỉ chạy binary cũ.

## 17. Bảo mật artifact và dữ liệu trong changelog

Migration artifact có thể chứa dữ liệu literal, tên bảng/schema nội bộ, câu SQL, thông tin vận hành hoặc file fixture. Không phải mọi nội dung changelog đều công khai.

Các nguyên tắc:

- Không đóng gói mật khẩu, token, private key hoặc JDBC URL chứa credential.
- Không đưa bản dump production hoặc CSV PII vào artifact.
- Phân tách fixture test khỏi root production và bundle production.
- Giới hạn quyền tải artifact và log pipeline.
- Redact SQL preview nếu có dữ liệu nhạy cảm.
- Ký hoặc xác minh digest theo cơ chế tổ chức nếu cần bảo đảm provenance.
- Có retention và quy trình thu hồi artifact cũ.
- Không chia sẻ migration bundle qua link công khai không kiểm soát.
- Kiểm tra nội dung container image và lớp filesystem, không chỉ source repository.

Checksum của Liquibase giúp theo dõi tính nhất quán changeset; digest artifact giúp xác định toàn bộ gói. Hai cơ chế có phạm vi khác nhau và không thay thế kiểm soát quyền truy cập.

## 18. Những lỗi thường gặp khi đóng gói

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Liquibase không tìm thấy root changelog | Sai classpath/path hoặc artifact thiếu resource | Kiểm tra cấu hình runtime và nội dung JAR/bundle |
| Root đọc được nhưng include lỗi | File con không được đóng gói hoặc đường dẫn sai | Kiểm tra dependency path và resource accessor |
| sqlFile/CSV không tồn tại | Build loại file hoặc relative path không đúng | Kiểm tra artifact sau build và cấu hình relativeToChangelogFile |
| Chạy được Windows nhưng lỗi Linux | Case-sensitive path, separator hoặc encoding | Kiểm tra tên file chính xác và test trên môi trường tương đương |
| Staging thành công nhưng production checksum mismatch | Artifact/changelog khác, path/property/version khác | So digest, commit, filename, MD5SUM và cấu hình |
| Update-sql khác update thực tế | Hai lệnh dùng artifact hoặc filter khác nhau | Cố định artifact, root, context, label, properties |
| Spring Boot không nạp resource như CLI | Khác classpath hoặc Liquibase version | Test trực tiếp từ JAR và so dependency |
| Migration bundle thiếu extension | Runtime image không chứa extension/driver | So manifest runtime và image digest |
| Changeset chạy lại ngoài ý muốn | Filename/id/author thay đổi hoặc metadata khác | Kiểm tra định danh và DATABASECHANGELOG |
| Fixture test xuất hiện production | Root production include nhầm test folder | Kiểm tra cây include, filter và CI assertion |
| Rollback không tìm thấy script | Script rollback ngoài artifact hoặc path không ổn định | Đóng gói dependency và version hóa rollback |
| Artifact cùng version nhưng nội dung khác | Repository cho phép ghi đè version | Dùng immutable repository, digest và provenance |

### 18.1. Phân biệt lỗi đóng gói và lỗi kết nối

Nếu Liquibase không tìm thấy changelog hoặc sqlFile, thường là lỗi resource/path. Nếu không kết nối được database, lỗi thuộc URL, DNS, TLS, credentials, network hoặc driver. Không đổi path khi lỗi thực chất là authentication, và không thay credentials khi artifact thiếu resource.

Đọc root cause trong log, xác định lệnh và runtime đang dùng, rồi kiểm tra đúng lớp.

## 19. Bài thực hành: build một migration release có thể tái tạo

**Mục tiêu:** chứng minh root changelog và mọi dependency đều có trong một artifact bất biến, rồi dùng cùng artifact để preview và triển khai database thử nghiệm. Không dùng production.

### Bước 1. Chuẩn bị cây tài nguyên

Giả định source dự án có:

~~~text
src/main/resources/db/changelog/
  db.changelog-master.yaml
  schema/
    001-create-products.yaml
  sql/
    create-product-view.sql
  data/
    product-category.csv
~~~

Root changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: schema/001-create-products.yaml
  - include:
      file: data/010-load-product-category.yaml
  - include:
      file: objects/020-create-product-view.yaml
~~~

File con có thể tham chiếu CSV hoặc SQL. Xác nhận toàn bộ path trong cây tài nguyên tồn tại và không có fixture test trong root production.

### Bước 2. Tạo version và manifest

Chọn một version release cho application/migration. Tạo manifest ghi commit, artifact, digest, root changelog, Liquibase version, DBMS được test và filter. Không điền password hoặc secret.

### Bước 3. Kiểm tra artifact sau build

Liệt kê nội dung JAR hoặc bundle. Xác nhận:

- Root changelog có mặt.
- Tất cả include file có mặt.
- SQL và CSV được tham chiếu có mặt.
- Case và đường dẫn khớp.
- Runtime Liquibase, JDBC driver và extension đúng version.
- Không có dữ liệu thật hoặc secret trong gói.

### Bước 4. Chạy validation từ artifact

Dùng chính artifact đã tạo, không dùng source folder thay thế:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Kiểm tra root path, changeset pending và SQL preview. Lưu digest của artifact cùng kết quả. Nếu preview được tạo từ một bundle khác, không dùng nó làm bằng chứng phê duyệt cho bundle hiện tại.

### Bước 5. Thực thi trên database test

Sau khi review SQL và cấu hình đích:

~~~bash
liquibase update
liquibase history
~~~

Xác minh bảng, cột, constraint, view, dữ liệu và DATABASECHANGELOG. Nếu dùng Spring Boot, chạy smoke test từ chính JAR đã build để xác nhận classpath resource hoạt động.

### Bước 6. Chạy lại cùng artifact

Không rebuild hoặc sửa file. Chạy validate/status/update lần thứ hai và xác nhận changeset thông thường không bị thực thi lại ngoài dự kiến. Ghi lại artifact digest trước và sau để chứng minh nội dung không đổi.

### Bước 7. Thử promotion sang môi trường khác

Dùng cùng artifact/digest cho một database test thứ hai với cấu hình kết nối riêng. So sánh tập changeset được chọn, SQL sau property substitution và hậu điều kiện. Chỉ thay đổi cấu hình môi trường đã được phép; không thay changelog.

### Bước 8. Ghi kết quả

| Bằng chứng | Kết quả cần lưu |
|---|---|
| Artifact version/digest | Giá trị thật của gói |
| Root changelog | Đường dẫn và file tồn tại |
| Dependency | Include/sqlFile/CSV đầy đủ |
| Liquibase/runtime | Phiên bản và extension |
| Validation | Exit code và log đã redacted |
| SQL preview | Artifact/config dùng để tạo |
| Update | Exit code và deployment ID |
| History | Changeset được ghi nhận |
| Postconditions | Schema/data/smoke test |
| Repeat run | Không có thay đổi ngoài dự kiến |

Không điền kết quả giả. Bài lab hoàn thành khi có thể chứng minh **cùng một artifact** đã được kiểm tra, preview và dùng để update trên database thử nghiệm.

## 20. Checklist trước khi phát hành

- [ ] Root changelog và toàn bộ cây include được đóng gói.
- [ ] Tất cả sqlFile, CSV, resource và extension dependency đều có mặt.
- [ ] Đường dẫn, case, encoding và relativeToChangelogFile đã được kiểm tra.
- [ ] Không có fixture test hoặc dữ liệu production nhạy cảm trong artifact.
- [ ] Changeset id/author/filename/logicalFilePath ổn định.
- [ ] Liquibase, JDBC driver, Java runtime và extension được khóa version.
- [ ] Application artifact và migration artifact được liên kết qua release manifest.
- [ ] Artifact có version/digest bất biến và provenance phù hợp.
- [ ] Spring Boot classpath hoặc migration bundle đã được test từ artifact sau build.
- [ ] validate/status/update-sql dùng đúng artifact và cùng cấu hình với update.
- [ ] Fresh-install và upgrade-path test đều đạt.
- [ ] SQL preview đã được review và lưu an toàn.
- [ ] Staging và production promote cùng artifact/digest.
- [ ] Secrets chỉ được cấp lúc runtime từ nguồn bảo mật.
- [ ] Rollback/recovery script và dependency được version hóa.
- [ ] CI/CD truyền exit code và dừng khi migration bắt buộc thất bại.
- [ ] Hậu kiểm DATABASECHANGELOG, schema, dữ liệu và ứng dụng đã đạt.
- [ ] Artifact cũ được giữ theo retention và có thể truy xuất khi cần điều tra.

## 21. Kết luận

**Đóng gói changelog cùng phiên bản phát hành giúp biến migration thành một phần có thể truy vết và tái tạo của release.** Một artifact đúng phải chứa root changelog, toàn bộ file include, SQL/CSV và dependency runtime; đồng thời phải giữ định danh changeset, version Liquibase và cấu hình triển khai nhất quán.

Hãy build một lần, kiểm tra nội dung artifact sau build, chạy fresh-install và upgrade-path test từ chính artifact, tạo SQL preview rồi update bằng cùng version/digest. Cấu hình môi trường và secret được cung cấp lúc runtime; nội dung migration đã phê duyệt được giữ bất biến. Kết hợp manifest, CI/CD, Spring Boot, checksum và hậu kiểm database sẽ giúp đội phát triển và vận hành triển khai cùng một thay đổi có thể kiểm toán qua dev, staging và production.
