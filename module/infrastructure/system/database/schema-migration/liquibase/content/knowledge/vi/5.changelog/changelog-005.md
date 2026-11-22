# Đường dẫn tương đối, tài nguyên classpath và khả năng đóng gói changelog trong Liquibase

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một nền tảng quan trọng cho mọi hoạt động này là **Liquibase phải tìm đúng changelog và mọi tài nguyên mà changelog tham chiếu**, bất kể chạy từ máy lập trình viên, một job CI hay file JAR được đóng gói.

Đường dẫn sai có thể khiến ứng dụng không khởi động, một changeset không được tìm thấy, hoặc tệ hơn là Liquibase xem changeset cũ như changeset mới vì *đường dẫn định danh* đã thay đổi. Bài này phân biệt rõ đường dẫn trên đĩa, đường dẫn tương đối, tài nguyên Java classpath và định danh logic của changeset; sau đó xây dựng một cấu trúc changelog có thể mang từ môi trường local sang artifact triển khai.

## 1. Hiểu bốn loại đường dẫn thường gặp

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Đường dẫn trên hệ thống file | `src/main/resources/db/changelog/master.yaml` | Xác định file trong mã nguồn của máy phát triển hoặc workspace CI |
| Đường dẫn tương đối từ changelog | `changes/001-create-customer.yaml` | Cho phép một changelog tìm file con dựa trên vị trí của chính nó |
| Đường dẫn tài nguyên classpath | `db/changelog/master.yaml` | Tìm tài nguyên mà Java classloader hoặc Liquibase ResourceAccessor có thể nhìn thấy, kể cả trong JAR |
| Đường dẫn dùng để nhận diện changeset | `db/changelog/changes/001-create-customer.yaml` | Góp phần vào định danh lịch sử cùng với `id` và `author`; có thể cố định bằng `logicalFilePath` |

Đừng đánh đồng bốn cách biểu diễn này. Chẳng hạn, `src/main/resources` là **thư mục trong dự án**, nhưng sau khi biên dịch, nội dung của nó thường được copy vào **gốc classpath**. Vì vậy tài nguyên `src/main/resources/db/changelog/master.yaml` ở mã nguồn sẽ được tìm với tên `db/changelog/master.yaml` trong ứng dụng Java đã đóng gói.

Một quy tắc có thể sử dụng ngay: **file changelog cha cần có đường dẫn ổn định, file con nên được tham chiếu tương đối với changelog cha, và tên logic của changeset cần ổn định qua các lần đóng gói**.

## 2. Đặt changelog trong cấu trúc dễ đóng gói

Ví dụ dự án Java/Spring Boot:

```text
my-app/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── ...
        └── resources/
            ├── application.yml
            └── db/
                └── changelog/
                    ├── master.yaml
                    ├── changes/
                    │   ├── 001-create-customer.yaml
                    │   ├── 002-add-customer-email.yaml
                    │   └── 003-create-customer-index.yaml
                    └── sql/
                        └── customer-email-index.sql
```

Trong ví dụ này, tên tài nguyên của master trên classpath là `db/changelog/master.yaml`. File `changes/001-create-customer.yaml` nằm cạnh thư mục `changes` tính từ thư mục chứa `master.yaml`. Khi đóng gói ứng dụng theo cấu hình chuẩn, cả YAML và SQL trong `src/main/resources` cần được đưa vào tài nguyên runtime.

Vì sao nên bố trí như vậy?

1. Changelog ở khu vực tài nguyên runtime, độc lập với thư mục chứa mã Java.
2. Các changeset được phân chia thành file nhỏ, dễ review và ít xung đột khi nhiều thành viên làm việc.
3. Các file SQL bổ trợ có vị trí rõ ràng, được mang theo artifact.
4. Cùng một bộ changelog có thể được thử bằng CLI và chạy trong Spring Boot nếu cấu hình đường dẫn thống nhất.

Nếu dự án dùng Gradle, thư mục tài nguyên mặc định vẫn thường là `src/main/resources`. Với một layout tùy biến, hãy kiểm tra cấu hình build để chắc chắn tài nguyên thật sự được copy vào output và package. Không nên giả định file tồn tại trong mã nguồn là đã có trong artifact.

## 3. Tham chiếu file con bằng `include`

File master sau chủ động khai báo thứ tự chạy của từng changelog con:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-customer-email.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-create-customer-index.yaml
      relativeToChangelogFile: true
```

Thuộc tính `relativeToChangelogFile: true` là điểm mấu chốt. Nếu master ở `db/changelog/master.yaml`, Liquibase sẽ tìm `changes/001-create-customer.yaml` theo vị trí của master, tức tài nguyên `db/changelog/changes/001-create-customer.yaml`. Cơ chế này giúp các file di chuyển cùng thư mục cha mà không phải sửa từng include vì thay đổi thư mục làm việc của CLI.

Nếu không bật `relativeToChangelogFile`, tên file có thể được giải quyết theo các vị trí trong *search path* hoặc ResourceAccessor mà Liquibase được cấu hình. Kết quả phụ thuộc cách công cụ được khởi chạy và các root được cung cấp. Một include dường như chạy tốt trong IDE có thể thất bại trong CI vì working directory hoặc classpath khác. Hãy kiểm tra quy tắc tìm tài nguyên của đúng phiên bản Liquibase khi để giá trị mặc định.

Lưu ý: `relativeToChangelogFile` điều khiển cách **tìm file con**. Nó không làm thay đổi vị trí của bảng trong database, không chọn schema và cũng không phải một cơ chế để bỏ qua checksum.

### 3.1. Ví dụ file changeset độc lập

Nội dung `db/changelog/changes/001-create-customer.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: database-team
      logicalFilePath: db/changelog/changes/001-create-customer.yaml
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: full_name
                  type: VARCHAR(200)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: customer
```

Nội dung `db/changelog/changes/002-add-customer-email.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-email
      author: database-team
      logicalFilePath: db/changelog/changes/002-add-customer-email.yaml
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: email
                  type: VARCHAR(255)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: email
```

Trong ví dụ, `logicalFilePath` được đặt nhất quán ngay từ đầu để xác định một đường dẫn logic ổn định. Đây là lựa chọn hữu ích khi cùng một changelog có thể được chạy từ thư mục `src/main/resources`, từ classpath hoặc từ một artifact. Tuy nhiên, nếu hệ thống của bạn đã triển khai changeset từ trước, **không tự đổi `logicalFilePath`**: trước tiên phải đối chiếu tên file đang được lưu trong `DATABASECHANGELOG` và lên kế hoạch tương thích với lịch sử hiện có.

`include` phù hợp nhất khi thứ tự changeset cần được review tường minh hoặc giữa các changeset có phụ thuộc quan trọng, ví dụ phải tạo bảng trước khi thêm cột, tạo khóa ngoại hay index.

### 3.2. Tránh đường dẫn tuyệt đối và lạm dụng `../`

Các kiểu tham chiếu sau thường gây khó bảo trì:

```yaml
# Phụ thuộc đường dẫn riêng của một máy
file: /home/developer/project/src/main/resources/db/changelog/changes/001.yaml

# Dễ gãy nếu di chuyển thư mục hoặc đổi cấu trúc module
file: ../../../../../db/changelog/changes/001.yaml
```

Đường dẫn tuyệt đối trên Windows còn có ký tự ổ đĩa và dấu phân cách khác Linux. Hãy dùng `/` trong đường dẫn tài nguyên và đặt changelog cùng các file con thành một cụm. Nếu cần dùng file nằm ngoài cụm đó, hãy xác định rõ root được cấp cho ResourceAccessor hoặc search path và lý do kỹ thuật thay vì tạo chuỗi `../` dài.

## 4. Dùng `includeAll` khi có nhiều file

Khi mỗi thành viên tạo một file migration mới, có thể yêu cầu Liquibase đọc các changelog trong một thư mục:

```yaml
databaseChangeLog:
  - includeAll:
      path: changes/
      relativeToChangelogFile: true
```

Với cấu trúc đã nêu, Liquibase tìm các tài nguyên phù hợp trong `db/changelog/changes/`. Cách này giảm thao tác sửa master mỗi khi có file mới. Tuy nhiên, thứ tự đọc thường được xác định theo tên tài nguyên; vì vậy cần quy ước tên có tiền tố tuần tự, chẳng hạn `001-`, `002-`, `003-`, và tránh tên gây thứ tự không như dự kiến như `1-`, `10-`, `2-`.

Đối chiếu `include` và `includeAll`:

| Tiêu chí | `include` | `includeAll` |
|---|---|---|
| Thứ tự | Theo thứ tự khai báo trong master | Theo cơ chế sắp xếp tài nguyên của Liquibase, thường theo tên |
| Khi thêm file | Cần bổ sung include tương ứng | Tài nguyên phù hợp trong thư mục có thể được nạp tự động |
| Kiểm soát phụ thuộc | Dễ nhìn thấy trong code review | Cần quy ước tên và kiểm tra chặt chẽ |
| Đóng gói | Cần file được tham chiếu nằm trong artifact hoặc root tìm kiếm | Cần cả thư mục và mọi file đủ điều kiện nằm trong artifact |
| Rủi ro | Sai tên file hoặc thiếu include | Vô tình nạp file không mong muốn, thứ tự không như thiết kế, hành vi tìm thư mục khác nhau theo cách đóng gói |

Nếu dùng `includeAll`, chỉ đặt trong thư mục những changelog thực sự cần chạy; không trộn tài liệu mẫu, file tạm, changelog thử nghiệm hay các file được sinh không kiểm soát. Với cấu trúc thư mục lồng nhau, hãy xác minh chính sách duyệt thư mục của phiên bản Liquibase, tránh để một file được tìm nhiều lần.

Một điểm dễ bị bỏ qua: Liquibase không chạy lại những changeset đã ghi nhận chỉ để khớp thứ tự tên file sau khi nhóm thêm một file mới ở giữa danh sách. Nếu migration mới phụ thuộc vào một thứ tự đặc biệt, đặt tên tuần tự theo dòng phát hành, không chèn ngược file rồi kỳ vọng các môi trường đã triển khai sẽ tự đổi lịch sử. Với chuỗi phụ thuộc quan trọng, khai báo `include` tường minh thường dễ kiểm soát hơn.

## 5. File SQL tham chiếu bằng `sqlFile` cũng cần đường dẫn đúng

Một changeset có thể gọi SQL nằm trong file riêng, ví dụ dành cho index đặc thù DBMS. Với changeset lưu ở `db/changelog/changes/003-create-customer-index.yaml`, nếu dùng:

```yaml
databaseChangeLog:
  - changeSet:
      id: 003-create-customer-index
      author: database-team
      dbms: postgresql
      logicalFilePath: db/changelog/changes/003-create-customer-index.yaml
      changes:
        - sqlFile:
            path: ../sql/customer-email-index.sql
            relativeToChangelogFile: true
            splitStatements: true
      rollback:
        - sql:
            sql: DROP INDEX IF EXISTS idx_customer_email
```

Thì `../sql/customer-email-index.sql` được giải quyết từ thư mục chứa **file changeset 003**, tức `db/changelog/changes/`, đến `db/changelog/sql/`. Ví dụ SQL trong file được tham chiếu:

```sql
CREATE INDEX idx_customer_email ON customer (email);
```

Khác với `include`, `sqlFile` nạp nội dung câu lệnh SQL để thực thi như một thay đổi. File SQL ấy phải tồn tại trong runtime artifact. Nếu đóng gói YAML nhưng bỏ quên SQL, quá trình validate/update có thể thất bại vì tài nguyên bị thiếu. SQL đặc thù DBMS cần được kiểm tra trên đúng hệ quản trị và phiên bản máy chủ; rollback thủ công phải được thử trên database dùng riêng trước khi đưa vào môi trường dùng chung.

Ví dụ này sử dụng `../` ngắn vì SQL và changeset là hai thư mục anh em trong cùng một cụm changelog. Nếu muốn tránh hoàn toàn việc đi lên thư mục cha, có thể đặt SQL ngay cạnh file changeset và tham chiếu `customer-email-index.sql`, miễn là quy ước đóng gói của dự án rõ ràng.

## 6. Java classpath là gì và Liquibase tìm tài nguyên ra sao?

Classpath là tập vị trí mà Java sử dụng để tìm lớp và tài nguyên lúc chạy. Vị trí đó có thể là thư mục biên dịch, file JAR hoặc tập nhiều JAR. Spring Boot thường đưa nội dung `src/main/resources` vào classpath runtime, vì vậy:

```text
Trong source:   src/main/resources/db/changelog/master.yaml
Trên classpath: db/changelog/master.yaml
Trong Boot JAR: BOOT-INF/classes/db/changelog/master.yaml
```

Trong ứng dụng Spring Boot, cấu hình changelog gốc thông dụng là:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/master.yaml
```

Tiền tố `classpath:` ở đây là cú pháp resource location của Spring, chỉ cho Spring tìm **changelog gốc** trong tài nguyên classpath. Bên trong changelog, tiếp tục dùng đường dẫn `changes/...` và `relativeToChangelogFile: true` theo quy tắc Liquibase. Không mặc định rằng phải thêm `classpath:` trước mọi giá trị `include.file`: cú pháp và cách phân giải đường dẫn của Spring ở property cấu hình gốc khác với cơ chế ResourceAccessor của Liquibase dành cho file con.

Sau khi Spring Boot khởi tạo Liquibase, nó sử dụng cơ chế truy cập tài nguyên phù hợp với môi trường chạy. Với JAR có cấu trúc Spring Boot, classloader và resource loader phải đọc được cả master lẫn mọi include, SQL file và changelog lồng nhau. Nếu bạn tự viết mã nhúng Liquibase hoặc tạo một launcher không theo cơ chế mặc định của Spring Boot, cần cung cấp ResourceAccessor thích hợp; một đường dẫn classpath có tồn tại không có nghĩa rằng cách gọi Liquibase tùy biến sẽ tự tìm được nó.

Không sử dụng `src/main/resources` trong giá trị `spring.liquibase.change-log` của ứng dụng đã đóng gói. Thư mục nguồn không nhất thiết tồn tại trong container hoặc máy production.

## 7. Chạy CLI khi tài nguyên vẫn nằm trên hệ thống file

Khi chạy Liquibase CLI trực tiếp từ repository, một lựa chọn đơn giản là chỉ rõ file gốc theo đường dẫn của source tree:

```bash
liquibase --changelog-file=src/main/resources/db/changelog/master.yaml validate
liquibase --changelog-file=src/main/resources/db/changelog/master.yaml update-sql
```

Ví dụ giả định bạn đang đứng ở thư mục gốc dự án, đã có JDBC driver và cấu hình kết nối qua tham số, defaults file hoặc biến môi trường. Với `relativeToChangelogFile: true`, các include được giải quyết dựa trên vị trí master, không lệ thuộc việc file con nằm ở đâu so với thư mục chứa CLI.

CLI và Spring Boot có thể nhìn cùng một nội dung dưới các tên resource khác nhau: CLI đi từ `src/main/resources/...`, còn Spring Boot thường đi từ `db/changelog/...`. Vì định danh của changeset có liên quan đến tên file, **đừng dùng xen kẽ hai cách chạy vào một database thật khi chưa xác minh lịch sử**. Đặt `logicalFilePath` ổn định từ đầu hoặc chuẩn hóa root/search path sao cho tên changelog thống nhất giữa các môi trường. Nếu dự án đã có lịch sử, đối chiếu `FILENAME` trong `DATABASECHANGELOG` trước khi chuyển cơ chế thực thi.

Một số phiên bản Liquibase hỗ trợ cấu hình search path để CLI coi `src/main/resources` hoặc thư mục chứa artifact giải nén là root tìm kiếm. Ví dụ hình thức:

```bash
liquibase --search-path=src/main/resources \
  --changelog-file=db/changelog/master.yaml validate
```

Hãy kiểm tra lệnh `liquibase --help` và tài liệu CLI của đúng phiên bản đang dùng để biết tên và vị trí tham số được hỗ trợ. Mục tiêu là đưa CLI về cùng tên resource `db/changelog/master.yaml` mà Spring Boot sử dụng, đồng thời giữ nguyên cách tham chiếu tương đối của các file con.

## 8. Đóng gói changelog vào JAR, Docker và artifact CI/CD

Một ứng dụng được triển khai thường không còn các thư mục nguồn của repository. Đó là lý do cấu trúc classpath đáng tin cậy hơn đường dẫn tuyệt đối trên máy phát triển.

### 8.1. Kiểm tra tài nguyên trong JAR

Với ứng dụng Spring Boot JAR, một danh sách minh họa các entry cần có:

```text
BOOT-INF/classes/application.yml
BOOT-INF/classes/db/changelog/master.yaml
BOOT-INF/classes/db/changelog/changes/001-create-customer.yaml
BOOT-INF/classes/db/changelog/changes/002-add-customer-email.yaml
BOOT-INF/classes/db/changelog/changes/003-create-customer-index.yaml
BOOT-INF/classes/db/changelog/sql/customer-email-index.sql
```

Bạn có thể xem danh sách entry sau khi build bằng công cụ JDK, ví dụ:

```bash
jar tf target/my-app.jar
```

Tên thư mục output và artifact khác nhau tùy Maven, Gradle hoặc plugin đóng gói. Dùng lệnh chỉ để kiểm tra nội dung JAR đã tạo, không giả định tên artifact mẫu là tên thực tế. Với Spring Boot executable JAR, phần tài nguyên thường nằm dưới `BOOT-INF/classes`; với JAR thư viện thông thường, tài nguyên có thể ở root của JAR.

Nếu file YAML có trong source nhưng vắng mặt trong JAR, kiểm tra quy tắc resource filtering, include/exclude, source set và bước copy resource. Với SQL file, cũng phải kiểm tra việc copy tài nguyên không làm biến đổi nội dung hoặc line ending ngoài ý muốn.

### 8.2. Docker và working directory

Khi chạy `java -jar` trong container, classpath tài nguyên được nạp từ artifact, vì vậy việc đổi `WORKDIR` thường không ảnh hưởng đến `classpath:db/changelog/master.yaml`. Ngược lại, nếu startup script gọi CLI với `src/main/resources/...`, container có thể không có đường dẫn đó. Khi dùng CLI riêng trong container, hãy copy changelog hoặc gắn artifact chứa changelog và cấu hình search path rõ ràng.

Trong CI/CD, cấu trúc nguồn, path sau build và cách phát hành artifact phải thống nhất:

```text
Git repository
   |
   v
Build: copy src/main/resources -> classes
   |
   v
Package: JAR / container image / migration artifact
   |
   v
Deploy: resource loader + JDBC -> database
```

Đối với mô hình tách migration thành job triển khai độc lập, có thể đóng gói changelog thành artifact riêng và cấu hình CLI đọc chính artifact đó. Nếu changelog nằm trong một JAR phụ thuộc hoặc nhiều module, bảo đảm JAR phù hợp được đưa vào classpath của tiến trình chạy Liquibase và dùng tên tài nguyên không va chạm với module khác.

### 8.3. Những trường hợp cần lưu ý

- **Executable JAR với thư viện lồng nhau**: việc truy cập resource bên trong nested JAR phụ thuộc cách khởi động và ResourceAccessor; hãy kiểm tra trong artifact cuối cùng, không chỉ chạy từ IDE.
- **Changelog nằm trong dependency JAR**: hai dependency có thể vô tình có cùng đường dẫn tài nguyên; khi đó một resource có thể che resource khác. Dùng namespace riêng theo module, ví dụ `db/changelog/customer/...`.
- **Native image hoặc cơ chế đóng gói khác JAR**: một số runtime cần cấu hình inclusion của resource riêng. Xác minh trực tiếp trên định dạng artifact thật.
- **Nạp file bằng đường dẫn hệ thống tuyệt đối**: điều đó tạo phụ thuộc vào layout của host/container; nếu cần thiết, quản lý đường dẫn như một phần của cấu hình triển khai.

## 9. Đường dẫn còn là một phần của lịch sử migration

Liquibase thường nhận diện một changeset thông qua bộ ba **`id` + `author` + đường dẫn file changelog**. Bảng `DATABASECHANGELOG` ghi các thông tin này cùng trạng thái chạy và checksum. Hai changeset cùng `id` và `author` nhưng được nhìn thấy qua hai đường dẫn khác nhau có thể bị xem là hai changeset khác nhau.

Hình dung lần triển khai đầu tiên lưu:

```text
ID:       001-create-customer
AUTHOR:   database-team
FILENAME: src/main/resources/db/changelog/changes/001-create-customer.yaml
```

Sau khi chuyển sang Spring Boot JAR, nếu Liquibase nhìn thấy file với tên `db/changelog/changes/001-create-customer.yaml`, nó có thể không khớp với bản ghi cũ trong `DATABASECHANGELOG`. Hậu quả có thể là cố tạo lại bảng đã tồn tại hoặc báo lỗi liên quan đến trạng thái migration.

Thuộc tính `logicalFilePath` cho phép khai báo một tên file logic ổn định cho việc nhận diện changeset, độc lập với vị trí vật lý. Với dự án mới, đặt giá trị này nhất quán trên các changeset cần chia sẻ giữa CLI và ứng dụng. Với dự án đã triển khai, thực hiện các bước trước khi di chuyển file hoặc đổi công cụ chạy:

1. Truy vấn `ID`, `AUTHOR`, `FILENAME`, `MD5SUM` trong `DATABASECHANGELOG` của từng môi trường.
2. Xác định bộ định danh đã dùng ở thời điểm changeset chạy lần đầu.
3. Giữ lại tên logic tương ứng với lịch sử đã lưu nếu cấu hình `logicalFilePath`; đừng tùy tiện đổi sang tên mới chỉ vì thư mục đổi.
4. Thử `validate`, `status` và SQL preview trên bản sao database có lịch sử thật.
5. Chỉ chuyển cơ chế đóng gói hoặc đường dẫn khi đã xác nhận Liquibase không nhận changeset cũ là changeset mới.

Checksum dùng để kiểm tra nội dung của changeset đã lưu có còn phù hợp với lịch sử không. Nó **không phải** công cụ bảo đảm rằng mọi file có tên khác nhau sẽ được gộp thành một changeset. Đổi đường dẫn có thể tác động đến định danh ngay cả khi nội dung SQL không đổi. Ngược lại, cố tình chỉnh nội dung changeset đã chạy có thể gây lỗi checksum dù đường dẫn vẫn giữ nguyên.

Nếu cần bổ sung schema hoặc sửa dữ liệu ở một hệ thống đã triển khai, hãy tạo changeset mới. Không xóa bảng `DATABASECHANGELOG`, không xóa checksum hàng loạt hoặc sửa thủ công metadata để vượt qua lỗi đường dẫn khi chưa điều tra nguyên nhân và có kế hoạch tương thích.

## 10. Quy tắc đường dẫn khi dùng nhiều môi trường

| Thành phần | Local | CI/CD | Spring Boot JAR |
|---|---|---|---|
| Master | File dưới `src/main/resources` hoặc search root rõ ràng | File/artifact được checkout hoặc phân phối | `classpath:db/changelog/master.yaml` |
| File con | Đường dẫn tương đối từ master | Cùng cấu trúc tương đối đã review | Resource bên trong classpath, tìm theo master |
| JDBC URL và credential | Cấu hình local, secret riêng | Secret của job | Environment/secret manager của ứng dụng |
| Định danh changeset | `id`, `author`, `logicalFilePath` ổn định | Giữ đúng bộ định danh | Giữ đúng bộ định danh |
| Kiểm tra | `validate`, SQL preview, thử rollback | Kiểm tra artifact và chạy test migration | Kiểm tra runtime đọc được resource trong package |

Đường dẫn changelog là một phần của logic ứng dụng, nên cần ổn định qua môi trường. Những thứ cần thay theo môi trường chủ yếu là thông tin kết nối, schema mục tiêu, quyền, context/label triển khai và secret. Không nên có một master changelog khác biệt tùy máy chỉ vì filesystem của các runner không giống nhau.

Với hệ thống nhiều schema hoặc nhiều dịch vụ, phân vùng các changelog theo namespace rõ ràng. Nếu nhiều ứng dụng cập nhật chung một database, xác định ai sở hữu schema, bảng lịch sử và thứ tự triển khai; tránh để hai artifact khác nhau dùng cùng tên đường dẫn changelog cho nội dung không tương thích.

## 11. Thực hành kiểm chứng trên đường chạy thực tế

Trước khi đưa một thay đổi vào release, có thể dùng quy trình sau. Các lệnh minh họa giả định CLI đã có kết nối JDBC và driver hợp lệ.

**Bước 1 – Kiểm tra tài nguyên:** xác nhận master, file include và SQL file đều có trong source lẫn artifact sau build. Nếu chạy Spring Boot, xem cấu trúc JAR; nếu chạy CLI riêng, xác nhận `--changelog-file` và search root.

**Bước 2 – Kiểm tra changelog:**

```bash
liquibase --changelog-file=src/main/resources/db/changelog/master.yaml validate
```

**Bước 3 – Xem trước thay đổi:**

```bash
liquibase --changelog-file=src/main/resources/db/changelog/master.yaml update-sql
```

Đọc SQL sẽ thực thi, thứ tự changeset và đối tượng bị ảnh hưởng. Trên môi trường dùng chung, cũng đối chiếu với lịch sử changeset đã chạy và kế hoạch rollback.

**Bước 4 – Chạy trong database thử nghiệm:**

```bash
liquibase --changelog-file=src/main/resources/db/changelog/master.yaml update
```

**Bước 5 – Kiểm tra bản ghi lịch sử:**

```sql
SELECT ID, AUTHOR, FILENAME, EXECTYPE, MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
```

Với PostgreSQL, tên cột và bảng không dùng dấu nháy kép thường không phân biệt chữ hoa/chữ thường trong biểu thức SQL. Với các DBMS khác, chú ý quy tắc đặt tên và schema chứa bảng metadata. Đối chiếu `FILENAME` với giá trị mong đợi; bước này đặc biệt quan trọng nếu lần đầu chạy bằng CLI nhưng sau đó chuyển sang Spring Boot.

**Bước 6 – Chạy cùng changelog từ artifact:** dùng cùng database thử nghiệm đã được migration, mở ứng dụng JAR trong môi trường tương đương production hoặc dùng job migration đóng gói. Không nên có changeset đã thực thi bị nhận diện lại là mới. Nếu có sai khác, ngừng triển khai, xác minh đường dẫn vật lý và `logicalFilePath` trước khi chạm vào metadata.

## 12. Chẩn đoán lỗi đường dẫn và đóng gói

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý phù hợp |
|---|---|---|
| Không tìm thấy master | Cấu hình `changeLogFile`/`spring.liquibase.change-log` dùng sai root | Kiểm tra working directory, classpath hoặc nội dung artifact |
| Không tìm thấy file trong `include` | Thiếu `relativeToChangelogFile`, đường dẫn tương đối sai, file không được copy | Đối chiếu vị trí master và file con; đặt `relativeToChangelogFile: true` khi có chủ đích |
| CLI chạy được nhưng JAR thất bại | Changelog nằm ngoài resources, SQL file bị exclude hoặc loader không đọc được nested resource | Kiểm tra entry thực tế trong JAR và cách ResourceAccessor được khởi tạo |
| `includeAll` thiếu hoặc lặp file | Khác biệt tìm thư mục, file không được đóng gói, layout trùng nhau | Kiểm tra resource tree và cấu hình tìm kiếm; cân nhắc `include` tường minh |
| Lần chạy mới đòi tạo lại bảng cũ | Đổi tên file/đường dẫn hoặc chạy từ search root khác gây đổi định danh | So sánh `FILENAME` trong `DATABASECHANGELOG`, xác định `logicalFilePath` tương thích |
| Lỗi checksum sau khi chuyển file | Có thay đổi nội dung changeset, hoặc tên logic/lịch sử không nhất quán | So sánh changeset gốc, đường dẫn logic và release hiện tại; không sửa metadata tùy tiện |
| Một changelog khác được nạp | Nhiều dependency JAR có tên resource giống nhau | Dùng namespace tài nguyên riêng, kiểm tra classpath thực tế và artifact |
| Chạy tốt local nhưng lỗi trong container | `WORKDIR`, mount hoặc hostname khác; file nguồn không có trong image | Dùng classpath resources hoặc copy artifact migration với root được khai báo rõ |

Khi xử lý lỗi, hãy phân biệt ba câu hỏi: *file có trong artifact không?*, *ResourceAccessor có tìm đúng file không?*, và *file được nhận diện dưới tên logic nào?*. Câu thứ nhất thuộc về build/packaging, câu thứ hai thuộc về cấu hình tìm resource, còn câu thứ ba thuộc về tính nhất quán lịch sử migration.

## 13. Quy ước thực tế cho nhóm phát triển

Một bộ quy tắc ngắn giúp phòng phần lớn sự cố:

- Lưu changelog dùng lúc chạy trong vùng tài nguyên được đóng gói, thường là `src/main/resources/db/changelog/`.
- Dùng `include` với `relativeToChangelogFile: true` khi muốn thứ tự triển khai rõ ràng; nếu dùng `includeAll`, thống nhất quy tắc đặt tên và duy trì thứ tự ổn định.
- Dùng đường dẫn tương đối, dấu `/` và tên resource nhất quán giữa Windows, Linux, container và JAR.
- Ghi nhận `id`, `author`, tên file logic và checksum; không đổi định danh của changeset đã chạy.
- Đặt `logicalFilePath` có chủ đích từ sớm nếu cùng bộ changelog được thực thi qua nhiều kiểu resource root.
- Đưa mọi file `.yaml`, `.xml`, `.json`, formatted SQL hoặc file SQL tham chiếu vào artifact cần triển khai; kiểm tra bằng cách liệt kê entry của JAR hoặc container.
- Giữ secret, JDBC URL và cấu hình môi trường bên ngoài changelog; không hardcode đường dẫn máy cá nhân hoặc thông tin xác thực vào file migration.
- Trước mỗi đợt triển khai, chạy `validate`, xem SQL dự kiến và kiểm tra trên artifact giống production, bao gồm lịch sử database đã tồn tại.

**Kết luận:** Đường dẫn trong Liquibase vừa là cách tìm tài nguyên, vừa ảnh hưởng đến danh tính lịch sử của changeset. Thiết kế changelog theo cấu trúc classpath có thể đóng gói, tham chiếu file con tương đối với file cha, và bảo toàn tên logic giữa các môi trường là điều kiện để migration, checksum, rollback và lịch sử triển khai trong `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` hoạt động đáng tin cậy.
