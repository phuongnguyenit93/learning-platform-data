# Đóng gói và kiểm tra đường dẫn changelog trong JAR

Một changelog Liquibase có thể chạy bình thường trên máy lập trình nhưng thất bại sau khi đóng gói ứng dụng Spring Boot thành JAR. Nguyên nhân thường không nằm ở SQL mà ở **tài nguyên không được đưa vào artifact, đường dẫn được phân giải khác với lúc chạy trong IDE, tên file sai chữ hoa/chữ thường hoặc các file con không nằm đúng vị trí trong classpath**.

Trong ứng dụng Spring Boot, changelog, các file được include, SQL script, CSV và tài nguyên migration liên quan cần được đóng gói như một bộ thống nhất. Khi chạy từ executable JAR, các tài nguyên thường nằm bên trong archive, không còn là những file rời trong thư mục làm việc. Vì vậy, không nên thiết kế changelog dựa trên đường dẫn tuyệt đối của máy phát triển hoặc giả định rằng một classpath resource luôn là một file hệ thống có thể mở bằng File.

Bài thuộc chương **Spring Boot** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu toàn module là nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào cách tổ chức tài nguyên, khai báo classpath changelog, giải quyết đường dẫn tương đối của include/sqlFile/loadData, kiểm tra nội dung JAR và xác minh ứng dụng thực sự khởi chạy migration từ artifact đã phát hành.

## 1. Vì sao changelog chạy trong IDE nhưng lỗi trong JAR?

Khi chạy ứng dụng từ IDE, classpath thường chứa thư mục tài nguyên đã được build, ví dụ:

~~~text
target/classes/
  application.properties
  db/
    changelog/
      db.changelog-master.yaml
      changes/
        001-create-customer.yaml
      sql/
        create-customer-view.sql
      data/
        countries.csv
~~~

Hoặc với một build Gradle, tài nguyên đã xử lý có thể nằm trong:

~~~text
build/resources/main/
  db/changelog/...
~~~

Khi đóng gói Spring Boot executable JAR, tài nguyên ứng dụng thường được đặt bên trong archive ở vùng:

~~~text
application.jar
  BOOT-INF/
    classes/
      application.properties
      db/
        changelog/
          db.changelog-master.yaml
          changes/
            001-create-customer.yaml
          sql/
            create-customer-view.sql
          data/
            countries.csv
    lib/
      liquibase-core-<version>.jar
      ...
~~~

Điều này tạo ra một số khác biệt:

- Đường dẫn tương đối theo thư mục làm việc của terminal có thể không còn đúng.
- Một tài nguyên classpath nằm trong JAR không nhất thiết có đường dẫn filesystem thông thường.
- File SQL hoặc CSV được tham chiếu gián tiếp có thể bị bỏ khỏi artifact dù changelog gốc vẫn có.
- Windows thường không phân biệt hoa/thường trong một số đường dẫn, trong khi môi trường Linux/container thường phân biệt.
- IDE có thể dùng tài nguyên mới nhất trong thư mục build, còn JAR đang chạy là artifact cũ.
- Một file được include bằng đường dẫn tương đối có thể bị phân giải khác nếu thay đổi vị trí changelog con.

Do đó, kiểm tra “chạy được trong IDE” chưa đủ. Phải kiểm tra **chính JAR sẽ được triển khai**.

## 2. Cấu trúc thư mục tài nguyên nên dùng

Một cấu trúc đơn giản và dễ kiểm tra:

~~~text
src/
  main/
    resources/
      application.yml
      db/
        changelog/
          db.changelog-master.yaml
          changes/
            001-create-customer.yaml
            002-add-customer-email.yaml
            003-create-customer-view.yaml
          sql/
            create-customer-view.sql
            drop-customer-view.sql
          data/
            countries.csv
~~~

Vai trò:

- **db.changelog-master.yaml**: changelog gốc mà Spring Boot cấu hình để Liquibase nạp.
- **changes/**: các changelog con chứa changeset theo nhóm hoặc phiên bản.
- **sql/**: SQL script được gọi từ sqlFile hoặc phần rollback tương ứng.
- **data/**: CSV phục vụ loadData/loadUpdateData nếu dự án dùng dữ liệu seed.
- **application.yml**: cấu hình datasource và Liquibase theo môi trường.

Tên thư mục không bắt buộc phải giống ví dụ. Điều quan trọng là:

1. Tất cả tài nguyên cần thiết nằm dưới source resource root được build tool đóng gói.
2. Các đường dẫn trong changelog khớp với cấu trúc thực tế.
3. File include, SQL, CSV và rollback được kiểm tra cùng changelog gốc.
4. Tên và đường dẫn được giữ ổn định sau khi changeset đã triển khai.

Không đặt changelog trong thư mục source Java rồi giả định build tool tự đưa chúng vào classpath. Với cấu hình mặc định phổ biến, thư mục tài nguyên ứng dụng là src/main/resources.

## 3. Cấu hình changelog gốc bằng classpath

Trong Spring Boot, cấu hình Liquibase có thể khai báo rõ đường dẫn changelog:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Hoặc trong application.properties:

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.yaml
~~~

Thuộc tính change-log xác định tài nguyên gốc mà Spring Boot chuyển cho tích hợp Liquibase. Prefix **classpath:** chỉ tài nguyên nằm trên classpath của ứng dụng, thay vì một đường dẫn tương đối phụ thuộc thư mục hiện tại.

Một số lưu ý:

- Dùng một đường dẫn tuyệt đối trong classpath, bắt đầu từ root tài nguyên như /db/changelog/...
- Tên file phải đúng chính tả và đúng chữ hoa/chữ thường.
- Không thêm tiền tố src/main/resources vào classpath path; thư mục đó là source root, không phải một phần của tên tài nguyên.
- Không dùng đường dẫn máy phát triển như C:\work\project\src\main\resources\... trong cấu hình runtime.
- Nếu thay đổi changelog root giữa các profile, phải bảo đảm từng profile dùng đúng tài nguyên được đóng gói.

Spring Boot thường có đường dẫn changelog mặc định là classpath:/db/changelog/db.changelog-master.yaml, nhưng dự án nên khai báo tường minh khi cần kiểm soát cấu trúc. Kiểm tra tài liệu của Spring Boot version đang dùng nếu cấu hình đã được tùy chỉnh.

## 4. Phân biệt classpath:, file: và đường dẫn tương đối

Ba cách tham chiếu tài nguyên có ngữ nghĩa khác nhau.

| Kiểu tham chiếu | Ví dụ | Nơi tìm tài nguyên | Phù hợp với |
|---|---|---|---|
| Classpath | classpath:/db/changelog/master.yaml | Classpath của ứng dụng/JAR | Changelog đóng gói cùng ứng dụng |
| File URL | file:/opt/app/changelog/master.yaml | Filesystem của máy chạy | Tài nguyên được mount ngoài JAR |
| Relative path | db/changelog/master.yaml | Phụ thuộc resource accessor và cấu hình phân giải | Chỉ dùng khi quy tắc phân giải đã được xác định |

Với changelog nằm trong executable JAR, ưu tiên classpath resource. Một file: URL có thể phù hợp nếu tổ chức chủ động mount changelog ngoài artifact, nhưng khi đó phải triển khai và version control file ngoài JAR như một dependency riêng.

**Không trộn hai mô hình mà không có lý do.** Ví dụ changelog root nằm trong classpath nhưng SQL file được trỏ tới một đường dẫn tương đối theo thư mục hiện hành của container. Cấu hình đó có thể chạy trong IDE vì thư mục làm việc tình cờ đúng, nhưng thất bại khi chạy từ systemd, Kubernetes hoặc một working directory khác.

Ngoài ra, không giả định mọi classpath resource đều có thể chuyển thành java.io.File hoặc java.nio.file.Path. Khi tài nguyên nằm bên trong JAR, nó thường được đọc qua resource accessor hoặc stream. Mã ứng dụng tùy chỉnh nếu cần đọc tài nguyên nên dùng Spring Resource/ResourceLoader hoặc API tương ứng, không ép URL dạng jar: thành filesystem path.

## 5. Include changelog con bằng relativeToChangelogFile

Changelog gốc có thể include nhiều file con:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true

  - include:
      file: changes/002-add-customer-email.yaml
      relativeToChangelogFile: true
~~~

Với cấu trúc ở mục 2, file được tìm tương đối so với changelog chứa include. Khi db.changelog-master.yaml nằm trong db/changelog, đường dẫn changes/001-create-customer.yaml trỏ tới db/changelog/changes/001-create-customer.yaml.

Ưu điểm của relativeToChangelogFile:

- Đường dẫn gắn với vị trí changelog, không phụ thuộc nơi terminal khởi chạy.
- Có thể di chuyển toàn bộ thư mục changelog cùng cấu trúc tương đối.
- Dễ review khi các file con được chia theo chức năng.
- Giảm rủi ro khác biệt giữa IDE, CLI và JAR.

Nếu bỏ relativeToChangelogFile hoặc đặt false, cách phân giải phụ thuộc search path/resource accessor và cấu hình runtime. Không dựa vào hành vi tình cờ trong IDE; hãy khai báo rõ để người đọc biết file được tìm ở đâu.

### 5.1. Include nhiều tầng

Một changelog con có thể include changelog khác:

~~~yaml
databaseChangeLog:
  - include:
      file: customer/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: order/001-create-order.yaml
      relativeToChangelogFile: true
~~~

Nếu file cha nằm trong changes, các đường dẫn tương đối phải được tính từ file cha đó. Khi lồng nhiều tầng, hãy vẽ cây tài nguyên và kiểm tra từng cạnh include. Không lấy đường dẫn tương đối của master để áp dụng cho mọi file con.

## 6. Đường dẫn sqlFile trong JAR

Một changeset có thể gọi SQL script:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-customer-view
      author: database-team
      changes:
        - sqlFile:
            path: ../sql/create-customer-view.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
            endDelimiter: ";"
      rollback:
        - sqlFile:
            path: ../sql/drop-customer-view.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
            endDelimiter: ";"
~~~

Giả sử changelog này nằm tại db/changelog/changes/010-create-customer-view.yaml và hai SQL file nằm trong db/changelog/sql. Đường dẫn ../sql/... đi lên từ changes rồi vào sql.

Các thuộc tính cần hiểu:

- **path**: tên tài nguyên SQL cần đọc.
- **relativeToChangelogFile**: xác định cách tính đường dẫn tương đối so với changelog đang khai báo sqlFile.
- **encoding**: cách giải mã nội dung SQL.
- **splitStatements**: có tách nội dung thành nhiều câu SQL hay không.
- **endDelimiter**: delimiter được dùng khi chia câu lệnh trong những trường hợp cấu hình phù hợp.

File rollback cũng là tài nguyên độc lập. Việc SQL tiến có trong JAR không chứng minh SQL rollback cũng được đóng gói. Cần kiểm tra cả hai.

Nếu SQL có PL/SQL, PostgreSQL DO block, function body hoặc delimiter đặc thù, không mặc định splitStatements=true với dấu chấm phẩy là an toàn. Kiểm tra cách parser xử lý nội dung thực tế và thử trên DBMS đích.

## 7. Đường dẫn CSV trong loadData và loadUpdateData

Tài nguyên CSV phải được đóng gói cùng changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-load-country-reference
      author: database-team
      changes:
        - loadData:
            file: ../data/countries.csv
            relativeToChangelogFile: true
            tableName: country
            encoding: UTF-8
            separator: ","
            quotchar: '"'
            columns:
              - column:
                  header: code
                  name: code
                  type: STRING
              - column:
                  header: name
                  name: name
                  type: STRING
~~~

Nếu changelog con ở db/changelog/changes, đường dẫn ../data/countries.csv trỏ tới db/changelog/data/countries.csv.

Các lỗi thường gặp:

- CSV có trong source nhưng không có trong JAR.
- Header file có BOM hoặc encoding khác.
- File path đúng ở Windows nhưng sai chữ hoa/thường trên Linux.
- File CSV được đặt cạnh master nhưng đường dẫn lại được tính từ changelog con.
- Changelog loadData đã được include nhưng file dữ liệu không được đóng gói.
- Một profile dùng changelog khác nhưng không có CSV tương ứng.

Nếu CSV chứa dữ liệu tham chiếu, hãy giữ file đã phát hành bất biến. Thay đổi dữ liệu ở bản phát hành sau bằng changeset và file mới; không sửa CSV cũ rồi kỳ vọng mọi database đã triển khai tự nạp lại.

## 8. IncludeAll và việc đóng gói cả thư mục

Một số dự án dùng includeAll để nạp các changelog trong một thư mục:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: changes
      relativeToChangelogFile: true
~~~

Khi dùng includeAll, không chỉ file master mà toàn bộ changelog con trong thư mục cần được đóng gói và có thể được resource accessor tìm thấy. Các điểm cần kiểm tra:

- Thư mục rỗng hoặc bị loại khỏi artifact.
- Một file changelog mới chưa được build/đóng gói.
- Tên file có chữ hoa/thường không nhất quán.
- Thứ tự xử lý có ảnh hưởng dependency.
- Có file SQL/README/tệp không phải changelog vô tình nằm trong thư mục includeAll.
- Có nhiều tài nguyên trùng tên trên classpath từ dependency JAR khác.

Đặt tên file có thứ tự rõ ràng và kiểm tra hành vi includeAll trên đúng phiên bản Liquibase. Không dựa vào thứ tự thư mục hiển thị trong IDE hoặc file explorer. Với thay đổi quan trọng, include tường minh thường giúp reviewer nhìn thấy thứ tự và dependency rõ hơn.

## 9. Đóng gói tài nguyên với Maven

Maven mặc định coi src/main/resources là resource root và sao chép nội dung vào output classes, sau đó đóng gói vào JAR. Nếu dự án thay đổi cấu hình resources, cần kiểm tra rằng thư mục db/changelog không bị bỏ qua.

Ví dụ cấu hình resource không bật filtering:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
    </resources>
</build>
~~~

Cấu hình này là ví dụ tối giản. Dự án có thể cần filtering cho một số file cấu hình khác, nhưng changelog và SQL/CSV thường nên được đóng gói nguyên vẹn trừ khi có một quy trình thay thế được thiết kế rõ.

### 9.1. Vì sao resource filtering có thể gây rủi ro?

Maven resource filtering có thể thay thế placeholder theo cú pháp cấu hình. Changelog Liquibase cũng có thể chứa placeholder hoặc chuỗi có ký tự đặc biệt. Nếu filtering tác động ngoài ý muốn:

- Nội dung changelog trong JAR khác nội dung source.
- SQL script có thể bị thay thế chuỗi.
- CSV có thể bị biến đổi.
- Checksum của changeset hoặc nội dung file có thể khác giữa các artifact.
- Một migration chạy được trong IDE nhưng lỗi khi chạy JAR.

Nếu cần filtering, tách rõ nhóm tài nguyên được filter và không filter. Không bật filtering toàn bộ resources chỉ vì application.properties cần thay biến. Kiểm tra byte/nội dung sau build và quản lý placeholder bằng một cơ chế nhất quán.

## 10. Đóng gói tài nguyên với Gradle

Với Gradle Java plugin hoặc Spring Boot plugin, src/main/resources thường được đưa vào source set main và copy vào resources output rồi đóng gói vào JAR.

Nếu dự án có custom sourceSets, processResources hoặc exclude pattern, hãy kiểm tra chúng có loại bỏ db/changelog hay file con không. Một rule exclude chung như **/*.sql hoặc **/*.csv có thể vô tình loại SQL rollback hoặc dữ liệu seed khỏi artifact.

Không cần đặt changelog vào một thư mục ngoài source resources rồi tự thêm classpath nếu không có lý do. Nếu dùng resource directory tùy chỉnh, phải khai báo nó trong sourceSets và xác minh output thực tế.

Đối với Spring Boot executable JAR, plugin đóng gói đưa classes và resources ứng dụng vào vùng BOOT-INF/classes. Thư viện Liquibase/JDBC driver thường nằm trong BOOT-INF/lib. Tên và cấu trúc chính xác có thể phụ thuộc kiểu archive và plugin version; kiểm tra JAR được tạo ra thay vì giả định.

## 11. Kiểm tra nội dung executable JAR

Sau khi build artifact, dùng công cụ liệt kê nội dung JAR để xác minh:

~~~bash
jar tf target/application.jar
~~~

Trên Windows PowerShell, có thể lọc các tài nguyên changelog:

~~~powershell
jar tf target/application.jar | Select-String "BOOT-INF/classes/db/changelog"
~~~

Kết quả mong đợi có dạng:

~~~text
BOOT-INF/classes/db/changelog/db.changelog-master.yaml
BOOT-INF/classes/db/changelog/changes/001-create-customer.yaml
BOOT-INF/classes/db/changelog/changes/002-add-customer-email.yaml
BOOT-INF/classes/db/changelog/sql/create-customer-view.sql
BOOT-INF/classes/db/changelog/sql/drop-customer-view.sql
BOOT-INF/classes/db/changelog/data/countries.csv
~~~

Nếu file nằm ở vị trí khác, đối chiếu với cấu hình classpath và đường dẫn trong changelog. Không chỉ kiểm tra master file. Hãy kiểm tra mọi tài nguyên được tham chiếu gián tiếp, bao gồm rollback, CSV và file trong includeAll.

Nếu artifact là JAR thông thường không phải Spring Boot executable, cấu trúc bên trong khác; tài nguyên có thể nằm ở root package thay vì BOOT-INF/classes. Cần phân biệt loại JAR đang kiểm tra.

### 11.1. Kiểm tra một tài nguyên cụ thể

Có thể dùng jar tool để đọc nội dung file bên trong archive mà không giải nén toàn bộ:

~~~bash
jar xf target/application.jar BOOT-INF/classes/db/changelog/db.changelog-master.yaml
~~~

Lệnh này giải nén tài nguyên tương ứng vào thư mục làm việc. Chỉ dùng trong workspace kiểm thử phù hợp; không giải nén ghi đè file nguồn đang làm việc. Với Spring Boot executable JAR, đây là entry bên trong archive.

Công cụ unzip cũng có thể liệt kê hoặc đọc entry. Điều quan trọng là xác nhận nội dung đã đóng gói đúng, không phải chỉ xác nhận tên file tồn tại.

## 12. Vì sao không nên dùng File hoặc Path cho classpath resource?

Một lỗi thường gặp trong mã Java tùy chỉnh:

~~~java
File changelog = new File(
    getClass().getClassLoader()
        .getResource("db/changelog/db.changelog-master.yaml")
        .getFile()
);
~~~

Cách này có thể chạy khi tài nguyên nằm trong thư mục classes, nhưng thất bại khi tài nguyên nằm bên trong JAR vì URL có dạng archive resource chứ không phải đường dẫn filesystem thông thường. Cách giải mã khoảng trắng, ký tự đặc biệt và nested JAR cũng có thể gây lỗi.

Nếu cần đọc một resource trong ứng dụng:

~~~java
Resource resource = resourceLoader.getResource(
    "classpath:/db/changelog/db.changelog-master.yaml"
);

try (InputStream input = resource.getInputStream()) {
    // Đọc nội dung từ stream khi thật sự cần.
}
~~~

Ví dụ này dành cho mã ứng dụng dùng Spring ResourceLoader. Trong tích hợp Spring Boot chuẩn, thường không cần tự đọc changelog bằng Java; SpringLiquibase và resource accessor của Liquibase đảm nhiệm việc tìm tài nguyên. Không viết một lớp tự chuyển classpath URL thành File để truyền cho Liquibase.

## 13. Tên file, chữ hoa/thường và ký tự đường dẫn

Một đường dẫn được viết là:

~~~text
db/changelog/changes/001-create-customer.yaml
~~~

nhưng file thực tế lại tên:

~~~text
db/changelog/changes/001-Create-Customer.yaml
~~~

Có thể không phát hiện lỗi trên một số môi trường Windows, nhưng container Linux có thể không tìm thấy file. Tên thư mục cũng chịu quy tắc tương tự.

Quy ước nên áp dụng:

- Dùng tên file chữ thường và dấu gạch ngang nhất quán.
- Tránh khoảng trắng trong tên tài nguyên.
- Không đổi tên file changelog đã được triển khai nếu chưa đánh giá identity changeset và logicalFilePath.
- Không dùng dấu phân cách Windows trong resource path; ưu tiên dấu /.
- Không viết path có ký tự ổ đĩa hoặc thư mục máy cá nhân trong classpath.
- Kiểm tra tên thật sau khi đóng gói, nhất là khi build trên Windows và chạy trên Linux.

Liquibase nhận diện changeset dựa trên ID, author và đường dẫn changelog (trừ khi logicalFilePath được cấu hình). Vì vậy, đổi vị trí hoặc tên changelog sau khi deploy có thể ảnh hưởng cách Liquibase nhận diện lịch sử. Hãy giữ đường dẫn ổn định hoặc thiết kế logicalFilePath có chủ đích từ đầu.

## 14. Kiểm tra version và dependency trong JAR

Một executable JAR cần có các thành phần tương thích:

- Spring Boot runtime.
- Liquibase core.
- JDBC driver cho DBMS.
- Extension Liquibase nếu changelog dùng change type đặc thù.
- Các dependency cần cho resource loading hoặc cấu hình datasource.

Nếu chạy CLI riêng để kiểm tra changelog, CLI có thể dùng Liquibase version khác với version nằm trong ứng dụng. Một changelog có thể validate bằng CLI nhưng ứng dụng chạy JAR lại lỗi vì parser/extension khác phiên bản.

Kiểm tra dependency tree và manifest/build metadata để xác định runtime thực tế. Dùng cùng version Liquibase core/extension trong test và production. Không chỉ dựa vào phiên bản được khai báo trong build file; dependency mediation có thể chọn version khác.

Đối với driver, phải kiểm tra JAR chứa đúng JDBC driver và URL scheme tương ứng. Lỗi “no suitable driver” là vấn đề classpath/dependency, không phải lỗi đường dẫn changelog.

## 15. Cấu hình profile Spring Boot và đường dẫn changelog

Một dự án có thể dùng chung changelog root nhưng cấu hình datasource khác theo profile:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml

---
spring:
  config:
    activate:
      on-profile: test
  datasource:
    url: jdbc:postgresql://localhost:5432/app_test

---
spring:
  config:
    activate:
      on-profile: production
  datasource:
    url: jdbc:postgresql://db-prod:5432/app
~~~

Ví dụ này chỉ minh họa cấu trúc profile; credentials phải được cấp qua secret store hoặc môi trường an toàn. Đường dẫn changelog có thể giữ nguyên trong mọi profile, nhưng database đích và quyền khác nhau.

Nếu profile thay changelog root, hãy xác nhận file tương ứng tồn tại trong JAR. Không dùng một root changelog cho staging rồi giả định profile production có file khác mà chưa đóng gói.

### 15.1. Tách bật/tắt Liquibase

Thuộc tính spring.liquibase.enabled có thể được dùng để bật/tắt tích hợp trong một profile. Ví dụ, nếu pipeline chạy migration bằng job riêng, ứng dụng runtime có thể không tự chạy migration khi startup. Khi đó cần bảo đảm job riêng hoàn tất trước khi ứng dụng nhận traffic.

Không để một profile vô tình tắt Liquibase ở production chỉ vì profile test đã đặt false. Kiểm tra effective configuration của artifact và môi trường triển khai.

## 16. Test tài nguyên changelog trong packaged application

Một bài kiểm thử chỉ dùng classpath trong IDE có thể bỏ qua lỗi đóng gói. Nên có bước kiểm tra artifact thực tế:

1. Build JAR theo quy trình CI của dự án.
2. Liệt kê nội dung JAR và xác nhận master changelog tồn tại.
3. Xác nhận mọi include, SQL file, CSV và rollback file được tham chiếu đều có mặt.
4. Chạy ứng dụng từ chính JAR trên database test dùng một lần hoặc môi trường tích hợp.
5. Xác nhận Liquibase tìm được changelog, kết nối đúng DB và chạy changeset mong đợi.
6. Kiểm tra DATABASECHANGELOG, schema và dữ liệu sau migration.
7. Dừng và tạo lại database test, chạy fresh install để kiểm tra đường đi từ đầu.
8. Với database có lịch sử, chạy thêm upgrade test từ phiên bản trước.

Ví dụ khởi chạy artifact:

~~~bash
java -jar target/application.jar --spring.profiles.active=test
~~~

Chỉ chạy trên database test đã xác minh. Không dùng lệnh này với cấu hình production trong một bước smoke test.

### 16.1. Integration test với database tạm

Có thể dùng Testcontainers hoặc database test riêng để khởi tạo Spring context và xác nhận migration. Kiểm thử nên xác minh không chỉ context khởi động thành công mà còn có đối tượng mong đợi và dữ liệu seed chính xác.

Ví dụ dạng kiểm thử khái niệm:

~~~java
@SpringBootTest
class LiquibasePackagingIT {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void migrationCreatesExpectedTable() {
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM information_schema.tables " +
            "WHERE table_name = 'customer'",
            Integer.class
        );

        assertThat(count).isEqualTo(1);
    }
}
~~~

Đây là ví dụ minh họa; truy vấn metadata cần điều chỉnh theo DBMS và schema. Nếu test dùng cùng datasource mà Liquibase tự chạy trước Spring context, assertion có thể xác nhận migration đã hoàn tất. Nên bổ sung assertion cho cột, constraint, index hoặc seed data có ý nghĩa, thay vì chỉ kiểm tra một bảng tồn tại.

## 17. Phân biệt lỗi đường dẫn với lỗi kết nối và lỗi SQL

Khi ứng dụng báo Liquibase startup failed, không kết luận ngay là changelog sai. Hãy phân loại:

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Cannot find changelog | Sai classpath root hoặc file không có trong JAR | jar tf, kiểm tra change-log property |
| Cannot find included changelog | Path tương đối sai hoặc file con bị loại khỏi artifact | Kiểm tra include và entry tương ứng |
| Cannot find SQL file | sqlFile path sai hoặc thiếu SQL resource | Kiểm tra path theo changelog chứa nó |
| Cannot find CSV | loadData file path sai hoặc thiếu CSV | Kiểm tra resource và encoding |
| Chạy trong IDE, lỗi trong Linux | Khác biệt hoa/thường hoặc working directory | So sánh path chính xác và artifact |
| File tồn tại nhưng nội dung sai | Resource filtering hoặc artifact cũ | Đọc entry bên trong JAR, so với source |
| No suitable driver | Thiếu JDBC driver hoặc dependency sai | Kiểm tra BOOT-INF/lib và dependency |
| Authentication failed | Secret/profile/datasource sai | Kiểm tra target identity và credentials |
| SQL syntax error | DBMS/version hoặc SQL script không tương thích | Xem câu SQL, driver và DBMS |
| Checksum mismatch | Changeset đã triển khai bị chỉnh | Kiểm tra artifact/lịch sử, không tự xóa history |
| Update thành công nhưng dữ liệu thiếu | loadData/changeset không được chọn hoặc seed path/filter sai | Kiểm tra changeset history và truy vấn dữ liệu |

Cách điều tra theo thứ tự:

1. Xác nhận JAR đúng release.
2. Kiểm tra changelog root có trong JAR.
3. Kiểm tra từng tài nguyên được tham chiếu.
4. Kiểm tra cấu hình Spring profile và classpath.
5. Kiểm tra Liquibase/driver version.
6. Kiểm tra kết nối, quyền và database identity.
7. Đọc SQL lỗi và trạng thái DATABASECHANGELOG.
8. Kiểm tra schema/data thực tế sau khi process thất bại.

Không sửa DATABASECHANGELOG hoặc clear-checksums chỉ vì ứng dụng không tìm thấy file.

## 18. Checksum và tính bất biến của tài nguyên sau khi đóng gói

Changelog và file SQL được phát hành cần được xem là một phần của artifact bất biến. Nếu source có một nội dung nhưng JAR chứa nội dung khác do resource filtering hoặc build cũ, checksum và hành vi migration có thể không như reviewer mong đợi.

Những nguyên tắc quan trọng:

- Dùng một artifact đã build và review xuyên suốt promotion từ test tới staging/production.
- Không rebuild từ source khác nhau cho từng môi trường nếu cần đảm bảo cùng một nội dung migration.
- Giữ changelog và file SQL đã triển khai bất biến.
- Không đổi tên/path changeset đã chạy nếu chưa có kế hoạch quản lý identity.
- Khi thêm migration, tạo changeset mới và đóng gói trong release mới.
- Có thể lưu hash artifact hoặc manifest tài nguyên để truy vết.
- Nếu file CSV được tham chiếu, quản lý phiên bản dữ liệu tương ứng với changeset.

Một checksum của changeset không phải hash toàn bộ JAR và không chứng minh mọi resource trong archive giống nhau. Kiểm tra checksum, lịch sử và nội dung artifact là các việc bổ trợ nhau.

## 19. Spring Boot executable JAR, container image và externalized resources

Trong triển khai container, JAR thường được copy vào image rồi chạy bằng java -jar. Cần xác minh:

- Image chứa đúng JAR đã được CI tạo và review.
- Không có volume mount ghi đè thư mục tài nguyên hoặc cấu hình changelog ngoài ý muốn.
- Profile và environment variables trỏ tới đúng datasource.
- Nếu changelog nằm trong JAR, không cần mount thêm source tree của repository.
- Nếu SQL/CSV được mount ngoài JAR, đường dẫn và version của chúng phải được quản lý như artifact riêng.
- Read-only filesystem không cản trở Liquibase ghi log hoặc tạo file tạm cần thiết; tài nguyên changelog chỉ đọc vẫn phải được truy cập qua resource accessor.

Với một số hệ thống, nhóm chủ động mount changelog ngoài image để tách migration release khỏi application release. Đây là mô hình hợp lệ nếu được thiết kế rõ, nhưng phải quản lý tương thích version, checksum, đường dẫn và quyền truy cập. Không dùng classpath path để tham chiếu file mount ngoài filesystem.

## 20. Bài thực hành: xác minh đường dẫn từ source tới JAR

Thực hiện trên dự án Spring Boot và database test riêng. Không sử dụng production.

### Bước 1 — Tạo cấu trúc tài nguyên

Tạo master YAML trong src/main/resources/db/changelog, một changelog con trong changes, một SQL script trong sql và một CSV trong data. Dùng tên file chữ thường.

### Bước 2 — Cấu hình classpath root

Đặt spring.liquibase.change-log thành classpath:/db/changelog/db.changelog-master.yaml. Chạy ứng dụng trong môi trường phát triển để xác nhận cấu trúc changelog hợp lệ.

### Bước 3 — Khai báo đường dẫn tương đối

Trong master, include changelog con với relativeToChangelogFile=true. Trong changelog con, tham chiếu sqlFile hoặc loadData bằng đường dẫn tương đối tương ứng và bật encoding UTF-8.

### Bước 4 — Kiểm tra resource output

Sau build, xác nhận các file có trong thư mục output resources. Đối chiếu với source, đặc biệt các file SQL rollback và CSV.

### Bước 5 — Kiểm tra executable JAR

Dùng jar tf để liệt kê BOOT-INF/classes/db/changelog. Đảm bảo master, include, SQL và CSV đều có mặt. Đọc nội dung các entry quan trọng để phát hiện filtering hoặc artifact cũ.

### Bước 6 — Chạy chính JAR

Chạy java -jar với profile test và datasource database dùng một lần. Xác nhận log cho thấy Liquibase đọc đúng changelog và các changeset được áp dụng.

### Bước 7 — Kiểm tra trạng thái database

Đọc DATABASECHANGELOG, kiểm tra bảng/cột/index và dữ liệu seed. Xác minh rollback file cũng tồn tại trong JAR dù chưa được sử dụng ở lần update.

### Bước 8 — Mô phỏng lỗi đường dẫn

Đổi sai chữ hoa/thường hoặc tạm bỏ một file trong artifact test. Quan sát lỗi, sau đó khôi phục cấu trúc và giải thích vì sao IDE có thể không phát hiện.

### Bước 9 — Kiểm tra upgrade

Dùng một database test đã chạy phiên bản trước, chạy JAR mới và xác nhận changeset bổ sung được thực hiện mà không chạy lại lịch sử cũ.

Điều kiện hoàn thành: người học có thể giải thích classpath resource trong executable JAR, xác định đường dẫn include/sqlFile/loadData tương đối, chứng minh mọi tài nguyên có trong artifact và chạy migration từ chính JAR trên database test.

## 21. Checklist trước khi phát hành JAR có Liquibase

| Câu hỏi | Bằng chứng cần có |
|---|---|
| spring.liquibase.change-log trỏ đúng classpath root? | Effective configuration của profile |
| Master changelog nằm trong JAR? | jar tf hoặc kiểm tra archive |
| Tất cả include/includeAll có tài nguyên? | Danh sách entry và đường dẫn được đối chiếu |
| SQL forward và rollback đều được đóng gói? | Kiểm tra từng sqlFile path |
| CSV/loadData có trong artifact? | Kiểm tra entry, encoding và header |
| relativeToChangelogFile được khai báo đúng? | Đối chiếu vị trí changelog cha/con |
| Tên file có phân biệt hoa/thường chính xác? | Kiểm tra trên Linux/container |
| Resource filtering có làm thay đổi nội dung? | Đọc nội dung entry trong JAR và so sánh |
| Liquibase core, extension và JDBC driver đúng version? | Dependency report và BOOT-INF/lib |
| Có chạy smoke test từ chính executable JAR? | Kết quả java -jar trên database test |
| Có fresh install và upgrade test? | Kết quả trên database mới và database cũ |
| DATABASECHANGELOG và schema sau migration đúng? | SQL assertion và log |
| JAR được promotion bất biến giữa môi trường? | Artifact digest/release identity |
| External mount nếu có được quản lý riêng? | Path, version, quyền và kế hoạch rollback |
| Secrets không nằm trong archive/log? | Kiểm tra cấu hình và artifact |

**Nguyên tắc cuối cùng:** hãy coi changelog, file include, SQL, rollback và CSV là một bộ tài nguyên phát hành. Đặt chúng trong resource root, dùng classpath cho changelog gốc, khai báo đường dẫn tương đối rõ ràng và kiểm tra mọi tài nguyên được tham chiếu trong executable JAR. Chỉ khi chính artifact đã đóng gói chạy thành công trên database test, xác minh được schema/data và lịch sử Liquibase, nhóm mới có bằng chứng đáng tin cậy rằng đường dẫn changelog sẽ hoạt động trong môi trường triển khai.

