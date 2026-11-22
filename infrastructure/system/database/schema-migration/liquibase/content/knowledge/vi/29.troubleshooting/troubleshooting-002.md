# Không tìm thấy changelog, include hoặc tài nguyên SQL

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Xử lý sự cố**, lỗi không tìm thấy changelog hoặc tài nguyên SQL thường xuất hiện khi Liquibase được chạy từ một môi trường khác với môi trường phát triển: chạy trong IDE thì thành công nhưng đóng gói thành JAR lại thất bại; chạy bằng Liquibase CLI thì tìm thấy master changelog nhưng không tìm thấy file được include; hoặc changelog được nạp nhưng file SQL được tham chiếu bởi sqlFile không được resolve.

Các lỗi này thường liên quan đến **đường dẫn và cơ chế phân giải tài nguyên**. Liquibase có thể đọc tài nguyên từ filesystem, classpath hoặc ResourceAccessor do ứng dụng cung cấp. Một đường dẫn tương đối có thể được tính từ thư mục làm việc hiện tại, thư mục chứa changelog hoặc gốc classpath tùy loại tài nguyên và cấu hình. Vì vậy, một path đúng trong máy developer chưa chắc đúng trong container, CI runner hoặc Spring Boot executable JAR.

Bài học này trình bày cách phân biệt changelog gốc, file include/includeAll và file SQL được tham chiếu bởi sqlFile; cách hiểu relativeToChangelogFile; cách tổ chức tài nguyên cho Spring Boot và Liquibase CLI; cách kiểm tra resource đã được đóng gói; cùng quy trình điều tra theo từng lớp. Mục tiêu là khôi phục đúng đường dẫn và nguồn tài nguyên, giúp Liquibase đọc được toàn bộ changelog để thực hiện migration có kiểm chứng, giữ lịch sử changeset và hỗ trợ rollback trong các môi trường.

## 1. Phân biệt ba loại tài nguyên

Trước khi sửa lỗi, cần xác định chính xác Liquibase đang không tìm thấy loại file nào.

| Loại tài nguyên | Khai báo thường gặp | Vai trò |
|---|---|---|
| **Changelog gốc** | spring.liquibase.change-log, --changelog-file hoặc cấu hình Liquibase API | Điểm bắt đầu của chuỗi migration |
| **Changelog được include** | include hoặc includeAll trong master changelog | Nạp thêm changeset từ file khác |
| **Tài nguyên SQL** | sqlFile.path trong một changeset | Đọc SQL được lưu ở file riêng để thực thi |

Ví dụ cấu trúc:

~~~text
src/main/resources/
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        ├── changes/
        │   ├── 001-create-customer.yaml
        │   └── 002-create-order.yaml
        └── sql/
            ├── refresh-customer-view.sql
            └── create-order-function.sql
~~~

Master changelog có thể include hai changelog con; một changeset trong 002-create-order.yaml có thể gọi sqlFile tới create-order-function.sql. Khi lỗi xảy ra, hãy xác định file nào đang bị thiếu:

- Không mở được db.changelog-master.yaml: kiểm tra cấu hình điểm vào và classpath/filesystem.
- Master mở được nhưng báo không tìm thấy 001-create-customer.yaml: kiểm tra khai báo include.
- Changelog con mở được nhưng báo không tìm thấy create-order-function.sql: kiểm tra sqlFile.path.
- Tất cả file đều được nạp nhưng SQL lỗi cú pháp: đó là lỗi thực thi SQL, không còn là lỗi resource resolution.

Phân loại đúng giúp tránh sửa nhầm spring.liquibase.change-log khi lỗi thật nằm ở một file SQL lồng sâu.

## 2. Liquibase phân giải tài nguyên từ đâu?

Liquibase sử dụng cơ chế truy cập tài nguyên để tìm changelog và file phụ trợ. Nguồn có thể là:

- **Filesystem**: đường dẫn tới file trên máy hoặc trong container.
- **Classpath**: tài nguyên được đóng gói trong ứng dụng hoặc nằm trong thư mục classpath.
- **ResourceAccessor của nền tảng tích hợp**: Spring Boot hoặc runtime khác cung cấp cách đọc resource.
- **Search path**: danh sách vị trí bổ sung mà một số cách chạy/phiên bản Liquibase hỗ trợ.

Một path như db/changelog/db.changelog-master.yaml có thể được resolve khác nhau tùy đang chạy từ classpath hay filesystem. Không thể chỉ nhìn chuỗi path để kết luận nguồn tìm kiếm.

### 2.1. Filesystem path

Filesystem path trỏ tới file vật lý. Ví dụ:

~~~text
/opt/app/config/db.changelog-master.yaml
C:\deploy\liquibase\db.changelog-master.yaml
~~~

Path tuyệt đối ít phụ thuộc thư mục làm việc, nhưng phụ thuộc file có được triển khai vào đúng vị trí trên máy/container hay không. Nếu dùng path tương đối, kết quả thường phụ thuộc working directory hoặc quy tắc resolve của công cụ.

Một lệnh chạy từ repository root có thể tìm thấy db/changelog/master.yaml; cùng lệnh chạy từ thư mục scripts/ có thể không tìm thấy file. Vì vậy cần ghi nhận **working directory thực tế của process**, không suy từ vị trí terminal mà developer đang nhìn.

### 2.2. Classpath resource

Trong ứng dụng Java, tài nguyên dưới src/main/resources thường được đưa vào classpath khi build. Ví dụ:

~~~text
src/main/resources/db/changelog/db.changelog-master.yaml
~~~

sẽ được tham chiếu trong Spring Boot bằng:

~~~yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

classpath: cho biết resource được tìm qua classloader/ResourceAccessor của ứng dụng. Trong executable JAR, tài nguyên thường nằm bên trong archive; nó không nhất thiết tồn tại dưới dạng file vật lý có thể mở bằng File thông thường.

Do đó, code hoặc script tự xử lý changelog bằng đường dẫn filesystem có thể hoạt động khi chạy từ IDE nhưng lỗi trong JAR. Với tích hợp Spring Boot, nên dùng classpath resource và API tương thích với ResourceAccessor thay vì giả định resource luôn có một đường dẫn file tuyệt đối.

### 2.3. Container và runtime đóng gói

Trong container, filesystem khác với máy developer. Những đường dẫn sau chỉ có ý nghĩa nếu file thật sự được copy hoặc mount vào image/container:

~~~text
/app/config/db/changelog/master.yaml
/run/config/db/changelog/
~~~

Nếu changelog nằm trong JAR thì không cần mount lại như file ngoài. Nếu changelog nằm ngoài JAR, Dockerfile hoặc volume mount phải đưa file vào đúng đường dẫn mà cấu hình runtime tham chiếu.

Hãy kiểm tra từ **bên trong đúng container** đang chạy ứng dụng hoặc migration job. Việc file tồn tại trên host không chứng minh container nhìn thấy nó.

## 3. Hiểu đúng relativeToChangelogFile

Một nguồn lỗi phổ biến là nhầm đường dẫn tương đối của file include với đường dẫn tương đối từ thư mục chạy lệnh.

Thuộc tính relativeToChangelogFile cho phép chỉ định path của tài nguyên được resolve tương đối với file changelog đang khai báo nó. Khi đặt true, path thường được tính từ vị trí changelog chứa khai báo; khi không bật, resource resolution dùng cơ chế tìm kiếm của Liquibase/ResourceAccessor theo cấu hình runtime.

Ví dụ:

~~~text
db/changelog/
├── db.changelog-master.yaml
├── changes/
│   ├── 001-create-customer.yaml
│   └── 002-create-order.yaml
└── sql/
    └── create-order-function.sql
~~~

Master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-order.yaml
      relativeToChangelogFile: true
~~~

Changelog con changes/002-create-order.yaml:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-020-create-function"
      author: "platform"
      changes:
        - sqlFile:
            path: ../sql/create-order-function.sql
            relativeToChangelogFile: true
            splitStatements: false
~~~

Ở ví dụ này, ../sql/create-order-function.sql được tính từ thư mục chứa changelog con changes/. Nếu chuyển file changelog con sang folder khác mà không cập nhật path, resource sẽ không còn ở vị trí cũ.

### 3.1. Cách tính path theo từng cấp

Hãy tính đường dẫn theo file đang chứa khai báo:

1. Xác định file changelog gốc được nạp.
2. Mở khai báo include bên trong file đó.
3. Xác định giá trị relativeToChangelogFile.
4. Tính path từ vị trí file changelog chứa include nếu bật relative.
5. Với changelog con, lặp lại quy trình cho include hoặc sqlFile bên trong nó.
6. Kiểm tra tên file và chữ hoa/thường trên filesystem/runtime thực tế.

Không tính mọi path từ master changelog nếu khai báo nằm trong file con. Mỗi cấp include có thể có vị trí tương đối riêng.

### 3.2. Khi nào dùng relativeToChangelogFile: true?

Nên cân nhắc bật khi:

- Các file được tổ chức thành một cây thư mục có quan hệ rõ.
- Changelog con và SQL phụ trợ được đặt cạnh nhau hoặc trong thư mục con tương đối.
- Muốn di chuyển cả một thư mục changelog mà không phụ thuộc working directory.
- Cùng changelog được chạy từ IDE, CLI hoặc Spring Boot và muốn đường dẫn theo vị trí file.

Tuy vậy, resource vẫn phải có trong classpath/filesystem mà runtime cung cấp. relativeToChangelogFile không tự đóng gói file vào JAR, không mount file vào container và không sửa sai tên path.

## 4. Cấu hình changelog gốc trong Spring Boot

Với tài nguyên nằm trong src/main/resources, cấu hình thường dùng:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Các điểm cần xác minh:

- Tên property là spring.liquibase.change-log.
- Resource path tính từ gốc classpath, không thêm src/main/resources vào chuỗi.
- File thật sự nằm dưới src/main/resources/db/changelog/.
- Tên file và phần mở rộng đúng với file thực tế.
- Build resource configuration không loại thư mục db/ khỏi artifact.
- Runtime đang chạy đúng JAR/version vừa build.
- Nếu có nhiều application profile, profile không ghi đè change-log sang path cũ.

Ví dụ sai thường gặp:

~~~yaml
spring:
  liquibase:
    change-log: classpath:src/main/resources/db/changelog/db.changelog-master.yaml
~~~

src/main/resources là đường dẫn trong source tree, không phải prefix của classpath resource. Khi build, nội dung thư mục này được đặt ở gốc classpath/archive; vì vậy cấu hình thường là classpath:db/changelog/db.changelog-master.yaml.

### 4.1. Đường dẫn mặc định và cấu hình tường minh

Spring Boot có giá trị mặc định cho changelog ở một số cấu hình/version, nhưng dự án nên đặt rõ spring.liquibase.change-log khi dùng cấu trúc riêng. Cấu hình tường minh giúp reviewer và người vận hành biết chính xác entry point.

Không suy ra rằng file tồn tại chỉ vì ứng dụng khởi động được ở một môi trường. Profile có thể vô hiệu hóa Liquibase hoặc chọn một datasource khác. Hãy xem startup log và xác nhận changelog thực sự được nạp.

### 4.2. Nhiều datasource

Nếu ứng dụng có nhiều datasource, Liquibase có thể cần datasource được chỉ định riêng. Cần kiểm tra:

- Liquibase đang dùng URL và datasource nào.
- JPA/repository đang dùng datasource nào.
- Changelog có được nạp từ classpath đúng không.
- Hai datasource có cùng database/schema đích theo thiết kế không.
- ResourceAccessor được tạo bởi cấu hình Spring Boot hay cấu hình tùy chỉnh.

Lỗi kết nối tới database khác thường bị nhầm với lỗi changelog; ngược lại, changelog không tìm thấy file không thể sửa bằng cách đổi JDBC URL.

## 5. Chạy Liquibase CLI từ filesystem

Khi chạy Liquibase CLI, điểm vào thường được truyền bằng tùy chọn --changelog-file hoặc cấu hình tương ứng của phiên bản CLI:

~~~bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --url=jdbc:postgresql://localhost:5432/appdb \
  --username=liquibase_migrator \
  validate
~~~

Đây là ví dụ minh họa. Path db/changelog/... được resolve theo cách CLI/resource accessor và cấu hình search path của phiên bản đang dùng. Nếu chạy từ repository root thì có thể tìm thấy; nếu chạy từ thư mục khác, hãy xác nhận working directory hoặc truyền path phù hợp.

Không đưa password thật vào command line vì có thể lộ qua shell history, process arguments hoặc log. Cấp credential qua secret manager, environment hoặc cơ chế bảo vệ của Liquibase CLI.

### 5.1. Phân biệt --changelog-file và spring.liquibase.change-log

| Cách chạy | Điểm cấu hình |
|---|---|
| Spring Boot auto-configuration | spring.liquibase.change-log |
| Liquibase CLI | --changelog-file hoặc cấu hình CLI tương ứng |
| Liquibase API tự tạo | ResourceAccessor và changelog path được truyền vào API |

Không copy nguyên cấu hình classpath: của Spring Boot sang CLI nếu CLI không sử dụng cùng ResourceAccessor. Ngược lại, không dùng đường dẫn filesystem chỉ tồn tại trên máy build trong cấu hình Spring Boot executable JAR.

### 5.2. Working directory và search path

Khi CLI không tìm thấy changelog, ghi lại:

- Lệnh được gọi đầy đủ sau khi đã loại bỏ/che secret.
- Working directory thực tế.
- Giá trị changelog file.
- Search path và defaults file được nạp.
- Phiên bản Liquibase CLI.
- User chạy lệnh và quyền đọc file.

Một số phiên bản Liquibase hỗ trợ search path để bổ sung vị trí tìm resource. Cú pháp, thứ tự ưu tiên và cách truyền tham số có thể khác theo phiên bản; hãy kiểm tra liquibase --help và tài liệu của đúng runtime. Search path chỉ giúp Liquibase tìm ở vị trí đã tồn tại, không sửa lỗi thiếu file trong artifact.

## 6. Xử lý include không tìm thấy changelog con

Một khai báo include:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
~~~

Các nguyên nhân phổ biến:

1. Tên file sai một ký tự hoặc sai phần mở rộng.
2. File nằm ở folder khác với path đã khai báo.
3. relativeToChangelogFile không đúng với cách tổ chức path.
4. Changelog con chưa được đưa vào classpath/JAR.
5. File có chữ hoa/thường khác với khai báo.
6. Working directory hoặc search path khác giữa các môi trường.
7. Changelog được di chuyển nhưng include chưa được cập nhật.
8. File bị loại khỏi build resources hoặc bị thiếu trong container image.

### 6.1. Ví dụ cấu trúc và path đúng

Cấu trúc:

~~~text
src/main/resources/db/changelog/
├── db.changelog-master.yaml
└── changes/
    └── customer.yaml
~~~

Master:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/customer.yaml
      relativeToChangelogFile: true
~~~

Không viết src/main/resources/db/changelog/changes/customer.yaml khi master đang được nạp từ classpath và path được tính tương đối với changelog. Đó là source-tree path, không phải vị trí tương đối bên trong resource tree.

### 6.2. Include lồng nhau

Ví dụ master include features/customer/customer.yaml; file customer lại include changes/create-table.yaml. Path thứ hai được tính theo vị trí file customer.yaml nếu relativeToChangelogFile: true được bật ở include đó.

Khi điều tra, vẽ cây resource:

~~~text
db.changelog-master.yaml
  └── features/customer/customer.yaml
        └── changes/create-table.yaml
~~~

Kiểm tra từng cạnh include. Một path đúng ở master không chứng minh path bên trong changelog con cũng đúng.

### 6.3. Định dạng changelog và phần mở rộng

Liquibase hỗ trợ nhiều định dạng changelog như XML, YAML, JSON và formatted SQL tùy phiên bản/tính năng. Tên file và định dạng phải khớp nội dung thật. Ví dụ file YAML bị đặt nhầm .xml có thể gây lỗi parser sau khi tìm thấy file; đây là lỗi nhận diện định dạng, không phải file missing.

Nếu log nói parser không đọc được nội dung, hãy kiểm tra định dạng, encoding và cú pháp. Nếu log nói resource không tồn tại, tập trung vào path và packaging trước.

## 7. Xử lý includeAll và thư mục changelog

includeAll nạp các changelog trong một thư mục theo quy tắc của Liquibase. Ví dụ:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: changes/
      relativeToChangelogFile: true
~~~

Cần kiểm tra:

- Thư mục changes/ có tồn tại trong resource tree không.
- File bên trong có đúng định dạng mà Liquibase nhận diện không.
- Các file tạm, backup hoặc file không phải changelog có bị đặt nhầm vào folder không.
- Thứ tự include có ổn định theo phiên bản và cấu hình không.
- Filter/comparator có loại hoặc sắp xếp file ngoài dự kiến không.
- Những file con có include hoặc sqlFile path riêng cần xác minh tiếp không.

includeAll không có nghĩa mọi file trong repository sẽ được nạp. Nó quét phạm vi thư mục được chỉ định theo quy tắc resource accessor. Đừng đặt file SQL phụ trợ hoặc file ghi chú trong folder changelog được quét nếu không muốn Liquibase xem xét chúng như changelog.

### 7.1. Thứ tự file và dependency

Nếu changeset tạo bảng phải chạy trước changeset tạo foreign key, hãy bảo đảm thứ tự include ổn định. Có thể dùng tên có prefix số hoặc comparator được cấu hình, nhưng phải kiểm tra hành vi thực tế của phiên bản Liquibase.

Nếu thứ tự là quan trọng đối với release, include tường minh thường dễ review hơn includeAll. Không dùng tên file như cơ chế thay thế cho precondition và kiểm thử dependency.

## 8. Xử lý sqlFile không tìm thấy file SQL

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "DB-040-create-report-view"
      author: "platform"
      changes:
        - sqlFile:
            path: sql/create-report-view.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
            stripComments: false
~~~

Nếu changeset nằm trong db/changelog/reports/reporting.yaml, path tương đối được tính từ vị trí file changelog đó. Cần xác nhận sql/create-report-view.sql có đúng vị trí tương ứng.

### 8.1. Các nguyên nhân thường gặp

- File SQL không nằm trong thư mục dự kiến.
- Path được tính từ master changelog thay vì changelog con chứa sqlFile.
- relativeToChangelogFile chưa bật dù path được viết tương đối với file con.
- File SQL không được copy vào src/main/resources hoặc artifact.
- Tên file có khác biệt chữ hoa/thường.
- Container không mount thư mục SQL ngoài JAR.
- File SQL bị đổi tên nhưng path chưa cập nhật.
- encoding không phù hợp nội dung file; sau khi tìm thấy file có thể phát sinh lỗi ký tự.
- Một script có delimiter/procedure phức tạp nhưng splitStatements hoặc endDelimiter không phù hợp.

### 8.2. Tách lỗi tìm file và lỗi thực thi SQL

| Thông báo/triệu chứng | Lớp cần kiểm tra |
|---|---|
| Resource/file not found | path, classpath, filesystem, packaging |
| Access denied / permission denied | Quyền đọc file hoặc mount |
| Unsupported encoding / ký tự lỗi | Encoding và nội dung file |
| SQL syntax error | Nội dung SQL, dialect và phiên bản DBMS |
| Statement bị tách sai | splitStatements, endDelimiter, executor |
| SQL chạy nhưng object không xuất hiện | Schema đích, quyền, transaction hoặc logic SQL |

Không thay splitStatements để sửa lỗi file không tồn tại. Liquibase phải đọc được file trước khi có thể phân tích hoặc thực thi câu SQL trong đó.

### 8.3. Procedure và delimiter

File chứa procedure/function có thể có nhiều dấu chấm phẩy bên trong body. Cần chọn splitStatements, endDelimiter và executor theo DBMS, driver và loại script. Đây là vấn đề xử lý nội dung SQL sau khi resource đã được tìm thấy.

Khi log chỉ rõ không tìm thấy sqlFile, hãy giải quyết path trước. Khi log đã hiển thị câu SQL hoặc báo lỗi tại một dòng SQL, resource đã được nạp và cần chuyển sang chẩn đoán nội dung.

## 9. File có trong source nhưng không có trong JAR

Một lỗi điển hình: developer thấy file dưới src/main/resources/db/changelog/ và chạy trong IDE thành công, nhưng khi triển khai executable JAR thì Liquibase báo không tìm thấy.

Nguyên nhân có thể:

- Build resource filter/exclude loại file .sql hoặc folder db/changelog.
- File nằm ngoài src/main/resources và không được khai báo là resource.
- Chỉ có trong thư mục test resources nhưng ứng dụng runtime không đóng gói.
- Tên file khác chữ hoa/thường; filesystem Windows không phân biệt như Linux.
- Build artifact cũ được deploy thay vì artifact mới.
- Multi-module build copy resource từ module không được đưa vào runtime dependency.
- Docker image chứa JAR khác với file đã kiểm tra trên máy build.

### 9.1. Kiểm tra nội dung artifact

Với executable JAR, có thể kiểm tra danh sách entry bằng công cụ archive/JDK phù hợp, ví dụ:

~~~bash
jar tf application.jar
~~~

Tìm các entry:

~~~text
BOOT-INF/classes/db/changelog/db.changelog-master.yaml
BOOT-INF/classes/db/changelog/changes/001-create-customer.yaml
BOOT-INF/classes/db/changelog/sql/create-order-function.sql
~~~

Tên entry cụ thể phụ thuộc kiểu đóng gói. Điều cần xác nhận là master, changelog con và SQL phụ trợ đều có mặt trong artifact runtime.

Nếu entry thiếu, sửa cấu hình build resources hoặc vị trí file nguồn rồi tạo artifact mới. Nếu entry có mặt nhưng Liquibase không tìm được, kiểm tra path classpath, ResourceAccessor, chữ hoa/thường và cấu hình changelog.

Không sửa path trong runtime để trỏ về source tree trên máy build. Production phải chạy bằng tài nguyên đã được đóng gói hoặc được mount rõ ràng.

### 9.2. Multi-module project

Trong dự án nhiều module, changelog có thể nằm trong module migration riêng hoặc module application. Cần bảo đảm resource module đó được đưa vào runtime classpath dependency. Một file có trong JAR của module A không tự có trong JAR/module runtime B nếu dependency hoặc packaging không bao gồm nó.

Kiểm tra dependency graph và artifact cuối cùng được deploy, không chỉ kiểm tra module chứa changelog.

## 10. Khác biệt chữ hoa/thường và đường dẫn giữa Windows, Linux

Windows thường sử dụng filesystem không phân biệt chữ hoa/thường trong cấu hình mặc định, còn Linux thường phân biệt. Vì vậy:

~~~text
changes/CreateCustomer.yaml
changes/createcustomer.yaml
changes/create-customer.yaml
~~~

có thể được xem như cùng một tên trong một số môi trường Windows nhưng là ba tên khác nhau trên Linux.

Các lỗi tương tự xảy ra với .YAML so với .yaml, SQL/ so với sql/, Customer.sql so với customer.sql, dấu gạch nối, dấu gạch dưới và khoảng trắng, backslash so với slash.

Trong changelog, nên dùng **forward slash /** cho resource path để dễ portable. Không dùng đường dẫn Windows tuyệt đối trong changelog dùng chung cho Linux/container/CI.

Ví dụ:

~~~yaml
- include:
    file: changes/customer.yaml
    relativeToChangelogFile: true
~~~

thường dễ portable hơn:

~~~yaml
- include:
    file: changes\customer.yaml
    relativeToChangelogFile: true
~~~

Không tự đổi toàn bộ tên file trên filesystem case-insensitive mà không kiểm tra Git. Git có thể không ghi nhận một số thay đổi chỉ khác chữ hoa/thường theo cách developer mong muốn. Hãy dùng tên canonical, commit thay đổi tên rõ ràng và kiểm tra trong môi trường Linux.

## 11. Quyền đọc file và mount trong container

Nếu file đã tồn tại đúng path nhưng Liquibase vẫn báo không đọc được, kiểm tra quyền:

- User chạy JVM/CLI có quyền đọc file.
- Thư mục cha có quyền traverse.
- File mount không bị mount theo cách gây lỗi đọc hoặc không có trong container.
- Volume mount không ghi đè thư mục chứa resource trong image bằng một thư mục rỗng.
- SELinux/AppArmor hoặc policy runtime không chặn truy cập nếu nền tảng sử dụng.
- Secret/config volume có quyền và ownership phù hợp.

Một tình huống dễ nhầm:

~~~text
Image:
  /app/config/db/changelog/master.yaml
  /app/config/db/changelog/changes/customer.yaml

Runtime volume mount:
  mount rỗng vào /app/config/db/changelog/
~~~

Volume mount có thể che khuất nội dung đã có trong image. Trên host, file vẫn tồn tại trong image layer nhưng process nhìn thấy nội dung mount. Kiểm tra filesystem từ bên trong container.

Không cấp quyền đọc toàn bộ filesystem để sửa lỗi permission. Chỉ cấp quyền tối thiểu cho thư mục và file Liquibase cần.

## 12. Encoding và ký tự trong resource

Sau khi tìm thấy file, Liquibase còn phải đọc nội dung đúng encoding. Với Markdown/YAML/SQL được lưu UTF-8, cần giữ encoding thống nhất giữa editor, build và runtime.

Với sqlFile, có thể chỉ rõ:

~~~yaml
- sqlFile:
    path: sql/backfill-customer-name.sql
    relativeToChangelogFile: true
    encoding: UTF-8
~~~

Các dấu hiệu lỗi encoding khác với lỗi file missing:

- Ký tự tiếng Việt hoặc ký tự đặc biệt bị biến dạng.
- Parser báo ký tự không hợp lệ.
- SQL literal bị thay đổi.
- File có BOM hoặc encoding khác kỳ vọng.

Hãy xác nhận byte/file encoding và thuộc tính encoding nếu được hỗ trợ. Không đổi encoding mù quáng vì có thể làm hỏng dữ liệu literal hoặc checksum của changeset đã phát hành.

## 13. Changelog path thay đổi và logicalFilePath

Di chuyển changelog sau khi đã triển khai có thể ảnh hưởng định danh changeset. Liquibase ghi nhận changeset theo tổ hợp định danh bao gồm ID, author và đường dẫn logic của changelog. Nếu path thay đổi mà logical path không được bảo toàn, Liquibase có thể nhận diện changeset như một thay đổi mới.

Phân biệt:

- **Resource path**: vị trí Liquibase cần đọc file.
- **Logical file path**: định danh logic được dùng để nhận diện changeset trong lịch sử.

Hai khái niệm liên quan nhưng không đồng nhất. Không thêm logicalFilePath để chữa lỗi resource not found; nó không tạo file và không sửa vị trí vật lý. Chỉ điều chỉnh logical path khi có kế hoạch bảo toàn lịch sử, thử nghiệm trên database đã có DATABASECHANGELOG và hiểu hành vi của phiên bản Liquibase.

Khi di chuyển thư mục changelog:

1. Ghi lại resource path cũ và mới.
2. Cập nhật mọi include và sqlFile path bị ảnh hưởng.
3. Xác định changeset đã được triển khai ở môi trường nào.
4. Bảo toàn logical identity theo cách phù hợp phiên bản.
5. Chạy kiểm tra trên database có lịch sử.
6. So sánh DATABASECHANGELOG trước và sau.

Không đổi filename/đường dẫn rồi xóa DATABASECHANGELOG để buộc chạy lại migration.

## 14. Cách đọc log và tìm resource đang thất bại

Thông báo lỗi thường cho biết loại resource hoặc path mà Liquibase đang tìm. Hãy lấy phần log có:

- Changelog gốc được cấu hình.
- Resource path đang được resolve.
- File include hoặc SQL file liên quan.
- Lớp exception gốc và nguyên nhân sâu nhất.
- Working directory, classpath hoặc search path nếu có.
- Liquibase version và cách khởi chạy.

Ví dụ các nhóm thông báo:

| Nhóm thông báo | Diễn giải | Hướng điều tra |
|---|---|---|
| Cannot find/read changelog | Không nạp được entry point | Cấu hình change-log/changelog-file và resource root |
| Include file not found | Master đọc được, file con không resolve | Path của include và vị trí changelog chứa nó |
| SQL file not found | Changeset đã được parse nhưng file SQL không resolve | sqlFile.path, relative flag và packaging |
| Unsupported file format/parser error | Resource đã tìm thấy nhưng định dạng/cú pháp không hợp lệ | Extension, YAML/XML/JSON/formatted SQL và encoding |
| Access denied | Đã xác định path nhưng không có quyền đọc | User, ACL, mount và policy |
| SQL exception | File đã được nạp, câu SQL gặp lỗi khi thực thi | Dialect, schema, quyền DB và nội dung SQL |

Bật log debug có thể giúp nhìn thấy quá trình tìm resource, nhưng log chi tiết cũng có thể chứa thông tin môi trường. Che credential, token và thông tin nhạy cảm trước khi chia sẻ log.

### 14.1. Ghi nhận cách chạy có thể tái hiện

Khi so sánh IDE, CLI và JAR, hãy ghi cùng một bộ thông tin:

| Thuộc tính | IDE | CLI | Spring Boot JAR |
|---|---|---|---|
| Entry point | Classpath hoặc filesystem | --changelog-file | spring.liquibase.change-log |
| Working directory | IDE run config | Thư mục chạy CLI | Thư mục process/container |
| Resource source | IDE classpath | Filesystem/search path | JAR classpath hoặc mount |
| Runtime | IDE classpath | Liquibase CLI version | JAR, Spring Boot, Liquibase |
| SQL phụ trợ | IDE resources | Filesystem/resource accessor | JAR resource hoặc mount |

Chỉ thay đổi một yếu tố mỗi lần kiểm tra. Ví dụ, giữ nguyên artifact và DB nhưng đổi cách resolve resource; hoặc giữ nguyên cách chạy và kiểm tra artifact có chứa file không.

## 15. Quy trình chẩn đoán từng bước

Khi gặp lỗi không tìm thấy changelog, include hoặc SQL, thực hiện theo thứ tự:

### Bước 1 — Xác định file bị thiếu

Đọc exception gốc để biết tên resource. Phân loại đó là master changelog, include, thư mục includeAll hay sqlFile. Không sửa mọi path cùng lúc.

### Bước 2 — Xác nhận entry point

Kiểm tra spring.liquibase.change-log, --changelog-file hoặc cấu hình API. Xác định nguồn classpath hay filesystem. Xác nhận profile thực tế đã nạp đúng cấu hình.

### Bước 3 — Xác nhận file tồn tại trong nguồn runtime

- Filesystem: kiểm tra path từ đúng working directory/container.
- Classpath: kiểm tra file dưới resource root hoặc trong JAR.
- Container: kiểm tra file và mount từ bên trong container.
- Multi-module: kiểm tra resource module có trong runtime classpath.

### Bước 4 — Tính lại đường dẫn tương đối

Mở changelog chứa khai báo include/sqlFile. Kiểm tra relativeToChangelogFile. Tính path từ đúng thư mục của file chứa khai báo, không mặc định từ master.

### Bước 5 — Kiểm tra tên và quyền

So sánh từng ký tự, phần mở rộng, chữ hoa/thường và dấu /. Xác minh user runtime có quyền đọc file và thư mục cha.

### Bước 6 — Kiểm tra packaging

Nếu chạy JAR, xác nhận tất cả changelog con và SQL file đã vào artifact. Nếu chạy CLI, xác nhận search path/working directory. Nếu chạy container, xác nhận image/volume đúng.

### Bước 7 — Chạy validation và SQL preview

Khi resource resolution đã đúng, chạy validate để kiểm tra cấu trúc changelog. Dùng update-sql hoặc lệnh tương ứng theo phiên bản để xem SQL dự kiến trên DBMS mục tiêu. Đây là kiểm tra tiếp theo sau khi đã tìm được tài nguyên.

### Bước 8 — Chạy thử trên database phù hợp

Thử update trên database tạm hoặc môi trường tích hợp được phê duyệt. Kiểm tra DATABASECHANGELOG, log và schema. Không dùng production làm nơi thử path.

### Bước 9 — Kiểm tra lịch sử sau khi sửa path

Nếu chỉ sửa resource path mà giữ nguyên logical identity, xác nhận changeset cũ không bị chạy lại. Nếu di chuyển file đã phát hành, kiểm tra logicalFilePath và DATABASECHANGELOG cẩn thận.

## 16. Ví dụ tổ chức resource portable cho Spring Boot

Một cấu trúc rõ ràng:

~~~text
src/main/resources/
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        ├── changes/
        │   ├── 001-create-customer.yaml
        │   └── 002-create-order.yaml
        └── sql/
            ├── create-customer-view.sql
            └── create-order-function.sql
~~~

Master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-order.yaml
      relativeToChangelogFile: true
~~~

Changelog con tham chiếu SQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-030-create-order-function"
      author: "platform"
      changes:
        - sqlFile:
            path: ../sql/create-order-function.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: false
            stripComments: false
~~~

Cấu hình Spring Boot:

~~~yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Trong cấu trúc này, master path tính từ classpath root; include path tính từ master vì relativeToChangelogFile được bật; sqlFile path tính từ changelog con trong changes/. Tất cả resource phải được đóng gói vào runtime classpath.

### 16.1. Khi cần SQL ngoài JAR

Có thể đặt changelog hoặc SQL ở một thư mục cấu hình ngoài ứng dụng, ví dụ được mount vào /opt/app/liquibase/. Khi đó phải cấu hình filesystem path rõ ràng và đảm bảo thư mục được triển khai cùng release artifact.

Cần quyết định nhất quán:

- **Đóng gói cùng ứng dụng**: dễ đảm bảo code và changelog cùng phiên bản.
- **Tài nguyên ngoài JAR**: linh hoạt cho deployment riêng, nhưng cần versioning, checksum/artifact và mount path được kiểm soát.

Không trộn lẫn hai mô hình mà không ghi rõ file nào nằm trong JAR và file nào đến từ filesystem.

## 17. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
|---|---|---|
| IDE chạy được, JAR không tìm thấy master | Resource không được đóng gói hoặc dùng filesystem path | Kiểm tra JAR và dùng classpath resource |
| Master có, include không có | Relative path tính sai hoặc file con bị loại khỏi artifact | Kiểm tra include.file và packaging |
| Changelog con có, sqlFile không có | Path tính từ sai changelog hoặc SQL không được đóng gói | Kiểm tra sqlFile.path và relativeToChangelogFile |
| Windows chạy, Linux lỗi | Sai chữ hoa/thường hoặc separator | Chuẩn hóa tên file và dùng / |
| CLI chạy từ root được, chạy từ scripts lỗi | Working directory thay đổi | Truyền path rõ hoặc chuẩn hóa working directory/search path |
| Container báo file missing dù host có | File không được copy/mount hoặc mount che nội dung image | Kiểm tra filesystem trong container |
| IncludeAll nạp file ngoài dự kiến | Folder có file thừa hoặc thứ tự không ổn định | Thu hẹp folder, filter hoặc dùng include tường minh |
| Parser báo lỗi sau khi tìm thấy file | Sai định dạng hoặc YAML/XML không hợp lệ | Kiểm tra extension, cú pháp và encoding |
| SQL file đọc được nhưng lỗi delimiter | Procedure bị split thành nhiều statement | Cấu hình splitStatements/endDelimiter phù hợp |
| Permission denied | User runtime không có quyền đọc file/thư mục | Cấp quyền tối thiểu và kiểm tra mount |
| Chạy sau khi di chuyển file thì changeset bị chạy lại | Logical file path thay đổi | Điều tra và bảo toàn logical identity |
| Liquibase nạp nhầm master | Profile hoặc config override chọn entry point khác | Kiểm tra effective configuration và startup log |

## 18. Bài thực hành: sửa lỗi sqlFile trong Spring Boot JAR

**Bối cảnh:** Ứng dụng chạy trên máy developer nhưng khi triển khai JAR thì Liquibase báo không tìm thấy file create-order-function.sql.

### Bước 1 — Xác định resource bị thiếu

Log chỉ ra changeset ORD-030-create-order-function không resolve được file SQL. Master changelog và changelog con đã được nạp, nên entry point không phải nguyên nhân.

### Bước 2 — Kiểm tra cấu trúc nguồn

Xác nhận cấu trúc:

~~~text
src/main/resources/db/changelog/
├── db.changelog-master.yaml
├── changes/
│   └── order.yaml
└── sql/
    └── create-order-function.sql
~~~

### Bước 3 — Kiểm tra path trong changelog con

Nếu order.yaml nằm trong changes/, path tương đối cần đi lên một cấp rồi vào sql/:

~~~yaml
- sqlFile:
    path: ../sql/create-order-function.sql
    relativeToChangelogFile: true
    splitStatements: false
~~~

Nếu path đang là sql/create-order-function.sql với relative flag bật, Liquibase sẽ tìm dưới changes/sql/, không phải db/changelog/sql/.

### Bước 4 — Kiểm tra JAR

Dùng công cụ archive để xác nhận JAR có entry BOOT-INF/classes/db/changelog/sql/create-order-function.sql. Nếu thiếu, sửa resource packaging hoặc vị trí file trong source rồi build artifact mới.

### Bước 5 — Kiểm tra runtime

Xác nhận deployment đang chạy đúng artifact mới. Nếu dùng container, kiểm tra image digest/tag và không để volume mount che thư mục resource.

### Bước 6 — Validate và thử migration

Chạy validate trên artifact mới; xem SQL preview và thử update trên database tạm đúng DBMS. Kiểm tra changeset được ghi vào DATABASECHANGELOG và function được tạo đúng schema.

### Bước 7 — Giữ nguyên lịch sử

Nếu chỉ sửa path của một changeset chưa từng chạy, kiểm tra checksum và định danh trước khi phát hành. Nếu changeset đã chạy ở môi trường khác, không tùy tiện sửa nội dung/path khiến Liquibase nhận diện nó là changeset mới; cần đánh giá logicalFilePath và thêm changeset sửa chữa khi cần.

## 19. Checklist trước khi phát hành

- Đã xác định resource bị thiếu là master changelog, include/includeAll hay sqlFile?
- Entry point Spring Boot/CLI/API đã được cấu hình rõ?
- classpath: có trỏ từ classpath root, không chứa src/main/resources?
- File thật sự tồn tại trong source resource hoặc filesystem runtime?
- Mỗi include/sqlFile có path được tính từ đúng file changelog chứa nó?
- relativeToChangelogFile có phù hợp với cách tổ chức folder?
- Changelog con và SQL phụ trợ đều được đóng gói trong JAR hoặc mount đúng?
- Multi-module runtime classpath có chứa resource module migration?
- Case, extension và dấu / khớp trên Linux?
- Working directory/search path của Liquibase CLI đã được ghi nhận?
- Container có nhìn thấy file từ bên trong runtime?
- Quyền đọc file và thư mục cha đã đúng?
- Encoding của YAML/SQL được thống nhất?
- includeAll không quét file backup, SQL phụ trợ hoặc file ngoài ý muốn?
- Đã phân biệt lỗi resource resolution với parser error và SQL execution error?
- Nếu di chuyển changelog, logicalFilePath và DATABASECHANGELOG đã được đánh giá?
- Artifact deploy là bản đã kiểm tra?
- validate và SQL preview đã chạy sau khi sửa resource?
- Migration đã được thử trên database tạm/đúng DBMS?
- Log được redact trước khi chia sẻ, không chứa secret?

**Kết luận:** Khi Liquibase báo không tìm thấy changelog, include hoặc SQL, hãy xác định chính xác resource nào bị thiếu và nguồn mà runtime dùng để tìm nó. Phân biệt classpath với filesystem, tính relativeToChangelogFile từ đúng changelog chứa khai báo, kiểm tra include/includeAll và sqlFile.path, rồi xác minh resource có trong JAR/container và process có quyền đọc. Khi chạy được trên IDE nhưng thất bại trong CLI hoặc production, hãy so sánh working directory, classpath, search path và artifact thực tế. Sửa đúng resource path mà vẫn bảo toàn định danh changeset sẽ giúp Liquibase tiếp tục quản lý schema, checksum và lịch sử triển khai nhất quán giữa các môi trường.

