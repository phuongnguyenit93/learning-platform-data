# Tạo dự án và cấu trúc thư mục migration tối thiểu

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, bạn học cách quản lý thay đổi schema và dữ liệu bằng Liquibase, từ changelog, changeset, precondition và checksum đến lịch sử triển khai, rollback và phối hợp nhiều môi trường. Bài này hướng dẫn dựng một dự án Liquibase tối thiểu có thể khởi tạo, kiểm tra và mở rộng; đồng thời chỉ ra cách đặt changelog trong ứng dụng Spring Boot hoặc trong một bước migration riêng của CI/CD.

Mục tiêu sau khi hoàn thành là bạn có thể tạo cấu trúc thư mục dễ hiểu, cấu hình kết nối database, khai báo changelog gốc, viết changeset đầu tiên, chạy kiểm tra trước khi áp dụng và xác minh lịch sử. Ví dụ sử dụng PostgreSQL và YAML để minh họa; có thể thay bằng XML, JSON, SQL hoặc hệ quản trị cơ sở dữ liệu khác khi đã cấu hình đúng JDBC driver và kiểu dữ liệu tương ứng.

## 1. Xác định cách tổ chức dự án

Liquibase có thể được tích hợp theo hai cách phổ biến:

- **Nằm trong ứng dụng:** changelog được đóng gói cùng ứng dụng, thường đặt dưới resources. Spring Boot tự cấu hình Liquibase khi có dependency phù hợp và migration được bật.
- **Là một bước triển khai riêng:** changelog nằm trong repository của ứng dụng hoặc repository chuyên quản lý database; CI/CD chạy Liquibase trước khi triển khai phiên bản ứng dụng cần schema mới.

Cả hai cách đều dùng cùng khái niệm changelog và changeset. Khác biệt chính là tiến trình nào chịu trách nhiệm chạy migration và thời điểm chạy. Một database nên có một cơ chế triển khai migration được xác định rõ. Nếu vừa để pipeline chạy Liquibase vừa để mọi replica Spring Boot tự chạy cùng migration, quá trình phát hành sẽ khó quan sát và dễ tạo ra các bước chờ không cần thiết.

Trước khi tạo file, hãy thống nhất:

1. Database và schema đích, ví dụ PostgreSQL với schema ứng dụng.
2. Phiên bản Liquibase và Java phù hợp với môi trường build/runtime.
3. Cách cung cấp JDBC driver và thông tin kết nối.
4. Đường dẫn changelog gốc được dùng thống nhất ở máy cá nhân, CI và môi trường triển khai.
5. Tiến trình sở hữu migration: ứng dụng Spring Boot hoặc job CI/CD chuyên biệt.

Không cần dựng một hệ thống phức tạp ngay từ đầu. Một changelog gốc, một thư mục chứa các changeset và một cấu hình kết nối đã đủ để tạo nền tảng. Khi dự án lớn dần, có thể chia thư mục theo domain hoặc theo giai đoạn phát hành.

## 2. Chuẩn bị công cụ và database

Một môi trường phát triển tối thiểu cần có:

- **Java:** nếu dùng Spring Boot hoặc Liquibase CLI chạy trên JVM, cài phiên bản Java được hỗ trợ bởi phiên bản công cụ và framework đang chọn.
- **Database:** có một database phát triển riêng, ví dụ database PostgreSQL cục bộ hoặc container dùng cho thử nghiệm.
- **Liquibase:** có thể dùng Liquibase CLI, tích hợp qua Spring Boot, hoặc plugin của hệ thống build.
- **JDBC driver:** driver tương ứng với database. Ứng dụng Spring Boot thường khai báo driver trong dependency; Liquibase CLI cần driver có trong classpath của tiến trình CLI.
- **Quyền database:** tài khoản migration cần quyền tạo hoặc sửa các đối tượng schema và quyền tạo các bảng metadata Liquibase khi chạy lần đầu.

Cài Liquibase CLI từ gói phân phối hoặc trình quản lý gói được tổ chức hỗ trợ. Sau khi cài, kiểm tra lệnh:

~~~shell
liquibase --version
~~~

Kết quả giúp xác nhận CLI gọi được và cho biết phiên bản đang sử dụng. Hãy cố định phiên bản trong tài liệu dự án hoặc image CI để máy cá nhân và pipeline không vô tình chạy các phiên bản khác nhau.

Nếu dùng CLI với PostgreSQL, cần bảo đảm PostgreSQL JDBC driver được cung cấp cho CLI. Có thể truyền đường dẫn JAR bằng tùy chọn classpath theo cách cài đặt CLI đang dùng. Dependency JDBC trong ứng dụng không tự động làm driver xuất hiện trong một tiến trình CLI độc lập.

Tạo trước database rỗng và một tài khoản dành cho migration. Không dùng tài khoản superuser làm tài khoản triển khai thường xuyên. Tài khoản này phải có quyền phù hợp để Liquibase tạo bảng metadata, tạo bảng nghiệp vụ, thêm cột, index và constraint theo các changeset của dự án. Tài khoản runtime của ứng dụng có thể chỉ cần quyền đọc/ghi dữ liệu nghiệp vụ.

## 3. Cấu trúc thư mục tối thiểu

### Dự án Spring Boot

Với ứng dụng Spring Boot, cấu trúc phổ biến là:

~~~text
customer-service/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/customer/
        │       └── CustomerApplication.java
        └── resources/
            ├── application.yml
            └── db/
                └── changelog/
                    ├── db.changelog-master.yaml
                    └── changes/
                        ├── 001-create-customer.yaml
                        └── 002-add-customer-status.yaml
~~~

Thư mục **src/main/resources/db/changelog** được đóng gói vào classpath của ứng dụng. File **db.changelog-master.yaml** là điểm bắt đầu; file này include các changelog con trong thư mục **changes**. Mỗi file con chứa một hoặc một nhóm changeset có quan hệ gần nhau.

Nếu dùng Gradle, vị trí resources vẫn có thể giữ nguyên; chỉ khác file khai báo dependency. Không cần đổi cấu trúc changelog theo công cụ build.

### Dự án migration độc lập

Nếu migration được chạy riêng bởi CLI hoặc pipeline, có thể tổ chức repository như sau:

~~~text
database-migrations/
├── liquibase.properties
├── db/
│   └── changelog/
│       ├── db.changelog-master.yaml
│       └── changes/
│           ├── 001-create-customer.yaml
│           └── 002-add-customer-status.yaml
└── README.md
~~~

File README có thể mô tả phiên bản Liquibase, database được hỗ trợ, cách cấu hình kết nối và các lệnh kiểm tra. File cấu hình chỉ chứa thông tin không bí mật hoặc giá trị mặc định cho môi trường phát triển; không commit mật khẩu thật hay token vào repository.

Không nên duy trì hai changelog gốc độc lập cùng quản lý một schema nếu chúng có thể chạy chồng lấn. Nếu ứng dụng và pipeline cùng dùng một bộ migration, hãy dùng chung một file master và thống nhất đường dẫn của nó.

## 4. Tạo changelog gốc

Changelog gốc liệt kê các changelog con theo thứ tự. Ví dụ **db.changelog-master.yaml**:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-customer-status.yaml
      relativeToChangelogFile: true
~~~

Thuộc tính **relativeToChangelogFile: true** giúp Liquibase tìm file được include tương đối với file master. Nhờ đó, đường dẫn vẫn có thể được giữ ổn định khi repository được checkout ở thư mục khác.

Có thể dùng **includeAll** để nạp toàn bộ file trong một thư mục, nhưng cách này đòi hỏi quy ước tên và thứ tự file rõ ràng. Với dự án mới hoặc nhóm nhỏ, liệt kê từng file bằng **include** thường giúp review thứ tự migration dễ hơn. Khi dùng includeAll, hãy kiểm tra quy tắc sắp xếp tên file và không để file tạm hoặc file thử nghiệm lọt vào thư mục được quét.

Changelog master không phải nơi chứa mọi câu lệnh SQL. Nó đóng vai trò mục lục có thứ tự, giúp người review nhìn thấy chuỗi thay đổi mà database sẽ nhận.

## 5. Viết changeset đầu tiên

Một changeset có định danh ổn định dựa trên **id**, **author** và đường dẫn changelog. Ví dụ file **changes/001-create-customer.yaml**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: team
      preConditions:
        - onFail: HALT
        - not:
            - tableExists:
                tableName: customer
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(255)
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: timestamp
      rollback:
        - dropTable:
            tableName: customer
~~~

Ví dụ này minh họa cách tạo bảng customer với khóa chính, email bắt buộc và thời điểm tạo. Precondition dừng migration nếu bảng đã tồn tại. Điều kiện đó hữu ích để phát hiện database không ở trạng thái dự kiến; nó không tự chứng minh bảng có sẵn tương đương với cấu trúc mà changeset định tạo.

Rollback xóa bảng nên có thể làm mất dữ liệu được ghi sau khi migration chạy. Chỉ dùng rollback này khi dữ liệu có thể bỏ đi hoặc đã có phương án phục hồi được kiểm chứng. Với schema production, hãy đánh giá tác động trước khi chạy rollback.

Changeset thứ hai có thể thêm cột status trong **changes/002-add-customer-status.yaml**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-status
      author: team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
        - not:
            - columnExists:
                tableName: customer
                columnName: status
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(30)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: status
~~~

Thay đổi thứ hai phụ thuộc bảng customer được tạo trước đó. Liquibase thực thi theo thứ tự include và ghi nhận mỗi changeset đã chạy. Khi schema cần thay đổi thêm, hãy tạo changeset mới thay vì chỉnh sửa nội dung changeset đã được triển khai ở môi trường dùng chung.

Các ví dụ sử dụng kiểu dữ liệu phổ biến; kiểu dữ liệu, auto-increment, timestamp và hành vi rollback cần được kiểm tra trên DBMS đích. Với database khác PostgreSQL, có thể cần điều chỉnh kiểu dữ liệu hoặc dùng change type phù hợp.

## 6. Định nghĩa cấu hình kết nối

### Cấu hình CLI

Với dự án migration độc lập, có thể tạo **liquibase.properties**:

~~~properties
changeLogFile: db/changelog/db.changelog-master.yaml
url: jdbc:postgresql://localhost:5432/customer_db
username: customer_migrator
driver: org.postgresql.Driver
classpath: drivers/postgresql.jar
~~~

Đường dẫn classpath ở trên chỉ là ví dụ; cần thay bằng vị trí JDBC driver thực tế mà CLI có thể đọc. Không đưa mật khẩu thật vào file cấu hình được commit. Cấp password qua secret của CI/CD hoặc biến môi trường tại thời điểm chạy.

Ví dụ trên PowerShell, nếu CLI được cấu hình đọc file properties:

~~~powershell
$env:DB_PASSWORD = Read-Host "Nhap mat khau database"
liquibase --defaults-file=liquibase.properties --password="$env:DB_PASSWORD" validate
liquibase --defaults-file=liquibase.properties --password="$env:DB_PASSWORD" update-sql
liquibase --defaults-file=liquibase.properties --password="$env:DB_PASSWORD" update
~~~

Trong môi trường thật, lấy giá trị từ secret store hoặc cơ chế đăng nhập bảo mật của tổ chức. Không lưu mật khẩu mẫu vào lịch sử shell dùng chung hoặc log pipeline. Tên tham số và cách phân phối driver cần đối chiếu với phiên bản Liquibase CLI đang cài.

### Cấu hình Spring Boot

Với Spring Boot, khai báo dependency Liquibase và JDBC driver. Nếu dự án sử dụng Spring Boot dependency management, phiên bản tương thích của thư viện thường được quản lý qua BOM của Spring Boot:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.liquibase</groupId>
        <artifactId>liquibase-core</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Nếu dự án không dùng Spring Boot dependency management, cần khai báo phiên bản thư viện theo ma trận tương thích của dự án. Không tùy tiện ghép phiên bản Liquibase mới nhất với một Spring Boot cũ mà chưa kiểm tra tương thích.

Ví dụ **application.yml**:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Spring Boot đọc cấu hình datasource để kết nối database. Khi Liquibase được bật, Spring Boot chạy changelog theo đường dẫn đã cấu hình trong quá trình khởi tạo ứng dụng. Hibernate ở chế độ **validate** kiểm tra mapping với schema mà không tự cập nhật schema.

Nếu Liquibase là nguồn quản lý schema, không cấu hình Hibernate **update** để cùng thay đổi schema. Nếu pipeline chạy migration riêng, hãy cấu hình tiến trình ứng dụng để không chạy lại migration ngoài chủ đích, chẳng hạn đặt **spring.liquibase.enabled=false** ở profile của ứng dụng runtime và để job migration dùng cấu hình riêng. Chỉ chọn một nơi chịu trách nhiệm áp dụng changeset cho mỗi lần triển khai.

## 7. Chạy kiểm tra trước khi áp dụng

Khi dùng CLI, thứ tự thao tác cơ bản là:

1. **Kiểm tra phiên bản và kết nối.** Xác nhận Liquibase CLI, JDBC driver, URL, tài khoản và database đích.
2. **Validate changelog.** Chạy lệnh kiểm tra cấu trúc changelog, tham chiếu file và các lỗi định nghĩa có thể phát hiện trước khi thực thi.
3. **Xem SQL dự kiến.** Sinh SQL để review các lệnh tạo bảng, thêm cột, constraint và thao tác dữ liệu.
4. **Áp dụng trên database thử nghiệm.** Chạy update trên database dùng một lần hoặc môi trường phát triển.
5. **Xác minh kết quả.** Kiểm tra schema, dữ liệu và bảng lịch sử Liquibase.

Các lệnh thường dùng:

~~~shell
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties update-sql
liquibase --defaults-file=liquibase.properties update
liquibase --defaults-file=liquibase.properties status --verbose
~~~

**validate** kiểm tra changelog và các tham chiếu có thể xác thực; nó không chứng minh migration đã chạy thành công trên database thật. **update-sql** hiển thị SQL dự kiến mà không áp dụng thay đổi. **update** mới là lệnh thực thi changeset. **status --verbose** giúp xem các changeset còn pending theo trạng thái database hiện tại.

Sau lần chạy đầu, Liquibase tạo các bảng metadata như **DATABASECHANGELOG** và **DATABASECHANGELOGLOCK** nếu chúng chưa tồn tại và tài khoản có đủ quyền. Bảng DATABASECHANGELOG ghi nhận changeset đã chạy, checksum và thông tin triển khai. DATABASECHANGELOGLOCK điều phối để tránh các tiến trình Liquibase cùng cập nhật schema đồng thời.

Đừng tự tạo hoặc chỉnh sửa các bảng metadata bằng tay trong quy trình thông thường. Nếu Liquibase báo lock còn giữ, hãy kiểm tra tiến trình migration thực tế và log trước khi xử lý lock; không xóa lock chỉ vì một lần chạy mất nhiều thời gian.

## 8. Đưa cấu trúc vào CI/CD

Trong pipeline, migration nên là một bước có đầu vào và kết quả quan sát được:

~~~text
Checkout source
      |
      v
Resolve Liquibase version and JDBC driver
      |
      v
Validate changelog
      |
      v
Generate and review update SQL
      |
      v
Run migration against target environment
      |
      v
Verify DATABASECHANGELOG and application compatibility
      |
      v
Deploy application
~~~

Pipeline nên dùng cùng changelog đã review khi promote từ test sang staging và production. Không sửa nội dung changeset riêng cho từng môi trường; cấu hình kết nối, schema đích và secret được cung cấp theo environment.

Một quy trình phù hợp có thể gồm:

- Job kiểm tra changelog trên pull request và chạy migration trên database thử nghiệm.
- Job triển khai migration có quyền kết nối đến đúng database của môi trường đích.
- Bước review hoặc phê duyệt trước production tùy chính sách phát hành.
- Bước triển khai ứng dụng sau khi migration đạt kết quả mong đợi.
- Bước xác minh log, DATABASECHANGELOG, thời gian chạy và hành vi ứng dụng.

Nếu ứng dụng tự chạy Liquibase khi khởi động, cần tính đến việc mọi instance có thể khởi tạo gần như cùng lúc. Liquibase có cơ chế lock ở database, nhưng một job migration riêng giúp pipeline kiểm soát rõ thời điểm, tài khoản và kết quả của bước thay đổi schema.

Tài khoản migration nên có quyền DDL cần thiết. Tài khoản ứng dụng runtime không nhất thiết phải có quyền tạo hoặc xóa bảng. Tách hai tài khoản giúp giảm quyền của tiến trình phục vụ request và làm rõ trách nhiệm thay đổi schema.

## 9. Xử lý database đã có schema trước khi cài Liquibase

Không chạy changeset tạo bảng lên một database đã có các bảng nghiệp vụ mà chưa xác định trạng thái hiện tại. Trước hết, kiểm kê schema, index, constraint và dữ liệu; đối chiếu với trạng thái mà changelog đầu tiên dự định tạo.

Nếu database đã tồn tại và cấu trúc hiện tại tương đương chính xác với kết quả của một hoặc nhiều changeset ban đầu, có thể lập kế hoạch baseline. Liquibase có lệnh **changelog-sync** để ghi nhận các changeset được chọn là đã chạy mà không thực thi nội dung thay đổi. Chỉ dùng sau khi đã xác minh độc lập rằng database thật sự ở đúng trạng thái sau các changeset đó.

Nếu chỉ chạy changelog-sync để bỏ qua lỗi tạo bảng hoặc để làm cho pipeline xanh, lịch sử Liquibase sẽ không còn phản ánh chính xác schema. Hãy thử baseline trên bản sao database trước, lưu bằng chứng đối chiếu và review phạm vi changeset được đồng bộ.

Sau khi baseline, các changeset mới tiếp tục được quản lý theo quy trình thông thường. Không sửa changeset đã ghi nhận chỉ để khớp với trạng thái cũ; nếu cần điều chỉnh schema, tạo changeset mới mô tả bước chuyển đổi tiếp theo.

## 10. Quy ước đặt tên và tổ chức khi dự án phát triển

Một cấu trúc tốt cần dễ tìm, dễ review và giữ định danh ổn định. Có thể áp dụng các quy ước sau:

- Đặt tên file theo thứ tự và nội dung, ví dụ **001-create-customer.yaml**, **002-add-customer-status.yaml**.
- Đặt **id** mô tả hành động và phạm vi, ví dụ **001-create-customer**; **author** dùng tên nhóm hoặc định danh ổn định của người sở hữu.
- Mỗi changeset nên chứa một thay đổi có ý nghĩa rõ ràng; tránh gom nhiều thay đổi không liên quan vào cùng một changeset.
- Giữ đường dẫn changelog đã triển khai ổn định. Đường dẫn file tham gia nhận diện changeset; đổi tên hoặc di chuyển file cũ có thể khiến Liquibase coi chúng là changeset khác nếu không quản lý logical path một cách có chủ đích.
- Không sửa nội dung changeset đã chạy trên môi trường dùng chung. Tạo changeset mới để bổ sung hoặc sửa hành vi.
- Dùng include tường minh khi cần kiểm soát thứ tự; nếu dùng includeAll, quy định rõ tên file và thứ tự sắp xếp.
- Chia changelog theo domain khi số lượng thay đổi tăng, nhưng vẫn có một master changelog rõ ràng cho database hoặc schema được quản lý.

Ví dụ cấu trúc lớn hơn:

~~~text
db/changelog/
├── db.changelog-master.yaml
├── customer/
│   ├── 001-create-customer.yaml
│   └── 002-add-customer-status.yaml
├── order/
│   ├── 001-create-order.yaml
│   └── 002-add-order-index.yaml
└── reference-data/
    └── 001-load-customer-types.yaml
~~~

Cách phân chia này là quy ước tổ chức mã nguồn. Hãy bảo đảm file master include các file con theo thứ tự có ý nghĩa và không để hai nhóm cùng tạo hoặc sửa một đối tượng mà không có quan hệ phụ thuộc rõ ràng.

## 11. Những lỗi khởi tạo thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| CLI không nhận driver | JDBC JAR chưa có trong classpath của CLI | Xác nhận driver class và đường dẫn classpath của tiến trình CLI |
| Không kết nối được database | URL, port, credential hoặc quyền truy cập sai | Kiểm tra endpoint, secret và quyền bằng môi trường thử nghiệm |
| Không tìm thấy changelog | Sai đường dẫn, sai chữ hoa/thường hoặc include không tương đối | Xác minh changeLogFile và đường dẫn include từ master |
| YAML không hợp lệ | Sai cấu trúc thụt lề hoặc tên change type | Chạy validate và xem vị trí lỗi |
| Changeset đã chạy bị sửa | Checksum hiện tại khác giá trị đã ghi | Tạo changeset mới; chỉ xử lý checksum theo quy trình có lý do rõ ràng |
| Bảng đã tồn tại khi tạo lần đầu | Database không rỗng hoặc chưa baseline | Đối chiếu schema, xác định baseline hoặc migration phù hợp |
| Ứng dụng khởi động lỗi khi migration | Thiếu quyền DDL, changelog sai hoặc schema không như giả định | Đọc log Liquibase, kiểm tra precondition và quyền tài khoản migration |
| Nhiều tiến trình cùng chờ lock | Nhiều instance cùng chạy migration hoặc tiến trình trước còn hoạt động | Xác minh tiến trình giữ lock và thời gian chạy trước khi can thiệp |

Không dùng **MARK_RAN**, **clear-checksums** hoặc thao tác sửa trực tiếp DATABASECHANGELOG như cách chữa chung cho lỗi cài đặt. Các thao tác này tác động đến lịch sử migration và chỉ phù hợp khi có kế hoạch khôi phục trạng thái được review.

## 12. Checklist hoàn thành dự án tối thiểu

Trước khi xem cấu trúc khởi tạo là sẵn sàng, hãy xác nhận:

- [ ] Có phiên bản Java, Liquibase và JDBC driver tương thích, được cố định trong hướng dẫn dự án.
- [ ] Có database phát triển và tài khoản migration với quyền cần thiết.
- [ ] Có một changelog master duy nhất cho schema được quản lý.
- [ ] Master include đúng các file con bằng đường dẫn ổn định.
- [ ] Changeset đầu tiên có id, author, nội dung rõ ràng và precondition phù hợp.
- [ ] Rollback được xem xét theo rủi ro dữ liệu, không mặc định coi là an toàn.
- [ ] Thông tin xác thực không được commit vào repository.
- [ ] Validate và update-sql được review trước khi chạy update.
- [ ] Migration đã được chạy thử trên database tương thích và schema kết quả đã được xác minh.
- [ ] Đã xác định Spring Boot hay CI/CD là tiến trình sở hữu việc chạy migration.
- [ ] Có cách kiểm tra DATABASECHANGELOG và xử lý sự cố lock dựa trên bằng chứng.

Khi các điểm trên đã rõ, dự án có một nền tảng Liquibase tối thiểu để phát triển thêm migration dữ liệu, precondition phức tạp, rollback, cấu hình theo môi trường và quy trình phát hành. Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, changelog là lịch sử thay đổi có thể review, changeset là đơn vị triển khai có định danh, còn Spring Boot hoặc CI/CD cung cấp điểm thực thi nhất quán. Cấu trúc thư mục ổn định ngay từ đầu giúp nhóm theo dõi được thay đổi schema và dữ liệu qua từng phiên bản ứng dụng.
