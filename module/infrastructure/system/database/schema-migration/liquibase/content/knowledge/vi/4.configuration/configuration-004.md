# Xác định changelog gốc, classpath và search path

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog và changeset. Mô tả module bao gồm precondition, checksum, lịch sử triển khai, migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Để các quy trình đó hoạt động nhất quán, trước hết Liquibase phải tìm đúng changelog gốc và giải quyết chính xác mọi tài nguyên mà changelog tham chiếu.

Ba khái niệm thường bị nhầm lẫn là **changelog gốc**, **classpath** và **search path**. Changelog gốc là điểm bắt đầu của cây migration. Classpath là vùng tài nguyên mà JVM và cơ chế nạp tài nguyên của ứng dụng có thể truy cập. Search path là danh sách vị trí Liquibase dùng để tìm các file khi chạy theo cơ chế hỗ trợ của nó. Chọn sai một trong ba có thể khiến lệnh migration không tìm thấy file, tìm nhầm file trùng tên hoặc chạy được trong IDE nhưng thất bại sau khi đóng gói ứng dụng.

## 1. Changelog gốc là điểm vào của toàn bộ migration

Changelog gốc (root changelog hoặc master changelog) là file Liquibase nhận làm đầu vào cho một lần cập nhật. File này thường chứa các khai báo `include` hoặc `includeAll` để tập hợp những changelog nhỏ hơn theo một cấu trúc có tổ chức.

Ví dụ, một module có thể bố trí tài nguyên như sau:

```text
src/
└── main/
    └── resources/
        └── db/
            └── changelog/
                ├── db.changelog-master.yaml
                ├── changes/
                │   ├── 001-create-customer.yaml
                │   ├── 002-create-orders.yaml
                │   └── 003-add-orders-customer-fk.yaml
                └── sql/
                    └── backfill-customer-code.sql
```

File `db.changelog-master.yaml` là điểm vào. Các file bên dưới chứa từng nhóm thay đổi. Cách chia này giúp changelog gốc ngắn gọn, dễ review và thể hiện được thứ tự phụ thuộc giữa các thay đổi.

Ví dụ nội dung root changelog:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-orders.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-add-orders-customer-fk.yaml
      relativeToChangelogFile: true
```

Trong ví dụ này, Liquibase bắt đầu từ file gốc, lần lượt nạp các changelog con theo thứ tự khai báo. Thuộc tính `relativeToChangelogFile: true` yêu cầu giải quyết đường dẫn file được include tương đối với file changelog đang khai báo nó. Nhờ đó, khi di chuyển cả thư mục changelog sang một vị trí khác nhưng vẫn giữ cấu trúc tương đối, các tham chiếu con vẫn dễ duy trì.

`includeAll` có thể dùng khi muốn nạp tất cả file trong một thư mục:

```yaml
databaseChangeLog:
  - includeAll:
      path: changes
      relativeToChangelogFile: true
```

Với `includeAll`, cần thống nhất quy tắc đặt tên file để thứ tự quét dễ dự đoán, chẳng hạn tiền tố `001-`, `002-`, `003-`. Không nên để các file phụ thuộc nhau nhưng thiếu quy ước tên hoặc dựa vào thứ tự tạo file. Với các migration quan trọng, khai báo `include` tường minh thường giúp người review nhận ra thứ tự và phạm vi thay đổi rõ hơn.

Changelog con có thể tiếp tục include các changelog khác. Khi đó, mỗi file là một nút trong cây changelog; đường dẫn tương đối nên được xác định từ đúng file đang khai báo include. Tránh dùng các đường dẫn tương đối phụ thuộc vào thư mục làm việc của máy cá nhân.

## 2. Phân biệt classpath và search path

### 2.1. Classpath là nơi ứng dụng/JVM tìm tài nguyên

Classpath là tập hợp thư mục và JAR được JVM sử dụng để nạp lớp Java và tài nguyên. Trong dự án Maven hoặc Gradle, nội dung của `src/main/resources` thường được sao chép vào gốc classpath khi build.

Ví dụ, file nguồn:

```text
src/main/resources/db/changelog/db.changelog-master.yaml
```

sẽ được đóng gói thành tài nguyên có đường dẫn:

```text
db/changelog/db.changelog-master.yaml
```

Vì vậy, trong Spring Boot, đường dẫn classpath thường được cấu hình như sau:

```yaml
spring:
  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Không thêm `src/main/resources` vào đường dẫn classpath. Đó là thư mục nguồn của dự án, không phải một phần của tên tài nguyên sau khi build. Khi ứng dụng chạy từ IDE, từ thư mục classes hoặc từ executable JAR, tài nguyên vẫn được truy cập qua cùng đường dẫn classpath nếu được đóng gói đúng.

Classpath cũng có vai trò với các lớp Java và thư viện mà Liquibase cần nạp, chẳng hạn JDBC driver hoặc extension. Việc một file nằm trong search path không tự động đưa các lớp Java trong file JAR đó vào classloader.

### 2.2. Search path là nơi Liquibase tìm file

Search path là danh sách thư mục Liquibase dùng để tìm changelog và các file được changelog tham chiếu trong những môi trường hỗ trợ cơ chế này, ví dụ file SQL bên ngoài hoặc changelog con. Với Liquibase CLI, có thể chỉ định search path bằng tham số `--search-path` hoặc thuộc tính cấu hình `searchPath`.

Ví dụ chạy từ thư mục gốc repository:

```bash
liquibase \
  --search-path=src/main/resources,./database-migrations \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --url="jdbc:postgresql://localhost:5432/appdb" \
  --username=app \
  --password=secret \
  update
```

Trong ví dụ, `--changelog-file` chọn changelog gốc; `--search-path` chỉ ra các vị trí để Liquibase tìm tài nguyên theo tên tương đối. Cần dùng dấu phân cách danh sách theo cú pháp phiên bản Liquibase đang cài đặt; CLI Liquibase hiện hành dùng danh sách phân tách bằng dấu phẩy. Trên Windows, hãy đặt giá trị có dấu cách trong dấu nháy kép và kiểm tra cách shell truyền dấu phẩy, dấu gạch chéo và ký tự ổ đĩa.

Có thể lưu cấu hình dùng chung trong `liquibase.properties`:

```properties
changeLogFile: db/changelog/db.changelog-master.yaml
searchPath: src/main/resources,./database-migrations
url: jdbc:postgresql://localhost:5432/appdb
username: app
password: secret
```

Khi triển khai, thông tin kết nối và thông tin nhạy cảm nên được cung cấp từ biến môi trường hoặc secret store của CI/CD thay vì ghi mật khẩu thật vào file được commit. Cấu hình đường dẫn có thể dùng chung nếu pipeline luôn chạy từ một thư mục làm việc đã xác định; nếu thư mục làm việc thay đổi, cần điều chỉnh đường dẫn hoặc dùng đường dẫn tuyệt đối phù hợp với môi trường.

Search path không phải là tên khác của classpath. Search path giúp Liquibase tìm file theo cơ chế tìm kiếm tài nguyên; classpath giúp JVM tìm lớp và tài nguyên đã được đóng gói. Chúng có thể cùng tham gia vào một lần chạy nhưng phục vụ những mục đích khác nhau.

## 3. Chọn changelog gốc theo cách chạy

### 3.1. Chạy Liquibase CLI

Với CLI, tham số `--changelog-file` xác định file gốc cần thực thi. Hãy truyền đường dẫn tương thích với search path hoặc đường dẫn file mà Liquibase có thể truy cập. Không nên phụ thuộc vào việc lệnh được gọi từ thư mục nào nếu pipeline hoặc người phát triển có thể chạy ở nhiều vị trí khác nhau.

Một cách tổ chức dễ kiểm soát là luôn chạy lệnh từ repository root:

```bash
liquibase \
  --search-path=src/main/resources \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  validate

liquibase \
  --search-path=src/main/resources \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  status --verbose

liquibase \
  --search-path=src/main/resources \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update-sql
```

Các lệnh trên dùng cùng một root changelog và cùng search path. `validate` kiểm tra tính hợp lệ của changelog; `status --verbose` cho biết các changeset chưa được áp dụng; `update-sql` sinh SQL dự kiến để review. Sau khi xem xét kết quả và xác nhận đúng database đích, pipeline mới thực hiện `update`.

Có thể cấu hình tham số mặc định trong `liquibase.properties`, sau đó ghi đè các giá trị khác nhau qua tham số dòng lệnh hoặc cấu hình pipeline. Cần xác nhận phiên bản Liquibase và cách phân cấp cấu hình đang dùng, vì tên tham số, vị trí file cấu hình và một số hành vi tìm tài nguyên có thể khác giữa các phiên bản.

### 3.2. Chạy từ Spring Boot

Với Spring Boot, cấu hình `spring.liquibase.change-log` xác định root changelog. Khi tài nguyên nằm trong `src/main/resources`, dùng đường dẫn classpath:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Spring Boot sử dụng cơ chế nạp tài nguyên của Spring để truy cập file trong classpath. Các changelog con và file SQL cần được đóng gói cùng ứng dụng hoặc được đặt tại vị trí mà resource loader của ứng dụng truy cập được. Vì vậy, một cấu hình chạy được ở IDE chưa đủ chứng minh executable JAR có đầy đủ tài nguyên; cần kiểm tra artifact sau build.

Nếu chủ đích lưu changelog bên ngoài artifact, Spring hỗ trợ các kiểu resource location phù hợp như `file:` trong những cấu hình tương ứng. Ví dụ:

```yaml
spring:
  liquibase:
    change-log: file:/opt/app/liquibase/db.changelog-master.yaml
```

Cách này hữu ích khi đội vận hành muốn quản lý file migration bên ngoài JAR, nhưng phải bảo đảm tất cả changelog con và SQL được tham chiếu cũng có mặt ở vị trí tương ứng. Cần kiểm soát quyền đọc file, phiên bản changelog và cách đồng bộ tài nguyên giữa các máy chạy ứng dụng.

Không nên trộn đường dẫn dành cho CLI với đường dẫn classpath của Spring Boot mà không kiểm tra. CLI có thể chạy từ repository root và tìm file qua search path; Spring Boot có thể đọc tài nguyên đã đóng gói trong JAR. Cùng một root changelog có thể dùng ở cả hai nơi nếu cấu trúc tài nguyên và các đường dẫn include được thiết kế tương thích, nhưng cách khởi tạo resource accessor của hai môi trường không hoàn toàn giống nhau.

## 4. Giải quyết đường dẫn của include, includeAll và sqlFile

### 4.1. Đường dẫn tương đối với changelog

Một changelog có thể tham chiếu đến file SQL:

```yaml
databaseChangeLog:
  - changeSet:
      id: 010-backfill-customer-code
      author: platform
      changes:
        - sqlFile:
            path: ../sql/backfill-customer-code.sql
            relativeToChangelogFile: true
            splitStatements: true
            stripComments: true
```

Với `relativeToChangelogFile: true`, đường dẫn SQL được giải quyết tương đối với changelog chứa changeset. Nếu file changelog nằm tại `db/changelog/changes/customer.yaml`, đường dẫn `../sql/backfill-customer-code.sql` trỏ đến thư mục `db/changelog/sql` trong cây ví dụ ở trên. Hãy đặt file SQL đúng vị trí và giữ nguyên cấu trúc thư mục trong artifact triển khai.

Cùng nguyên tắc áp dụng cho `include` và `includeAll`. Khi changelog được lồng nhiều cấp, hãy tính đường dẫn từ file đang chứa khai báo, không phải luôn từ root changelog. Việc ghi rõ `relativeToChangelogFile` giúp ý định của người viết dễ hiểu và giảm phụ thuộc vào working directory hoặc search path.

### 4.2. Đường dẫn được tìm qua search path

Trong một số cấu hình, đường dẫn không đặt tương đối với changelog mà được Liquibase tìm qua search path hoặc resource accessor. Ví dụ, nếu search path chứa thư mục `database-migrations`, một file có thể được tìm từ thư mục đó theo đường dẫn tương ứng. Cách này thuận tiện khi tài nguyên được tổ chức ngoài source tree ứng dụng, nhưng cũng tạo nguy cơ trùng tên.

Nếu có hai thư mục trong search path cùng chứa `db.changelog-master.yaml` hoặc `seed-data.sql`, Liquibase có thể chọn tài nguyên theo thứ tự tìm kiếm của cấu hình. Điều này khiến cùng một câu lệnh chạy ở hai máy có kết quả khác nhau nếu search path khác nhau. Hãy tránh trùng tên tài nguyên quan trọng, giới hạn search path ở các thư mục cần thiết và giữ nguyên thứ tự cấu hình trong CI/CD.

### 4.3. SQL, CSV và tài nguyên đi kèm

Các change dạng `sqlFile`, `loadData` hoặc `loadUpdateData` có thể phụ thuộc vào file bên ngoài. Không chỉ root changelog mà tất cả tài nguyên tham chiếu đều phải có mặt trong môi trường thực thi. Một changelog tìm thấy được nhưng thiếu file SQL hoặc CSV vẫn khiến migration thất bại.

Khi build ứng dụng, kiểm tra các file được đưa vào artifact. Với JAR, có thể xem nội dung bằng công cụ liệt kê archive:

```bash
jar tf build/libs/application.jar
```

Đường dẫn thực tế của file trong JAR cần khớp với vị trí mà classpath resource loader tìm kiếm. Với CLI chạy từ filesystem, kiểm tra file tồn tại ở đúng search path và quyền đọc của tiến trình.

## 5. Giữ đường dẫn ổn định giữa các môi trường

Đường dẫn changelog có thể ảnh hưởng đến danh tính changeset được Liquibase lưu trong `DATABASECHANGELOG`, cùng với `id` và `author`. Nếu thay đổi vị trí hoặc cách nhận diện file sau khi đã triển khai, Liquibase có thể xem một changeset cũ như một changeset mới vì đường dẫn logic đã khác. Điều này có thể dẫn đến chạy lại thay đổi đã thực hiện.

Vì vậy:

1. Chọn một root changelog ổn định và cấu hình nhất quán cho CLI, Spring Boot và CI/CD.
2. Giữ cấu trúc thư mục changelog và SQL đi kèm ổn định sau khi triển khai.
3. Dùng đường dẫn tương đối rõ ràng cho các file con, ưu tiên `relativeToChangelogFile: true` khi tài nguyên thuộc cùng cây changelog.
4. Không dùng tên file chung chung dễ trùng giữa nhiều search path.
5. Nếu bắt buộc di chuyển changelog, đánh giá tác động đến đường dẫn logic và sử dụng `logicalFilePath` theo hướng dẫn của phiên bản Liquibase đang dùng để duy trì danh tính changeset khi phù hợp.
6. Không sửa trực tiếp lịch sử `DATABASECHANGELOG` chỉ để che giấu vấn đề đường dẫn.

`logicalFilePath` cho phép khai báo đường dẫn logic dùng để nhận diện changeset độc lập với vị trí vật lý trong một số trường hợp. Hãy lên kế hoạch và kiểm thử thay đổi này trên database thử nghiệm trước khi áp dụng rộng rãi; không tự ý thay đổi giá trị logic ở các changelog đã triển khai mà chưa đánh giá lịch sử hiện hữu.

## 6. Cấu hình theo môi trường mà không nhân bản changelog

Thông thường, các môi trường development, test, staging và production nên dùng cùng một bộ changelog. Thông tin kết nối, schema mặc định, context, label và những tùy chọn vận hành được cấu hình theo môi trường. Ví dụ, Spring Boot có thể đọc cấu hình profile:

```yaml
# application.yml
spring:
  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml

---
# application-test.yml
spring:
  liquibase:
    enabled: true
    contexts: test

---
# application-prod.yml
spring:
  liquibase:
    enabled: true
    contexts: production
```

Cấu hình profile chỉ là ví dụ minh họa. Cần bảo đảm changeset tạo schema nền tảng không vô tình bị loại khỏi một môi trường bởi context hoặc label, trong khi changeset phụ thuộc vẫn được chạy. Các giá trị kết nối và secret nên được inject từ môi trường triển khai.

Trong CI/CD, nên có một bước migration riêng hoặc một tác vụ được kiểm soát rõ ràng. Bước đó dùng đúng artifact changelog, đúng cấu hình kết nối và cùng quy tắc đường dẫn với bước kiểm tra. Pipeline có thể thực hiện:

1. Kiểm tra file root changelog tồn tại trong workspace hoặc artifact.
2. Kiểm tra các file con và file SQL/CSV được tham chiếu cũng có mặt.
3. Chạy `liquibase validate`.
4. Chạy `liquibase status --verbose` để xem changeset pending.
5. Chạy `liquibase update-sql` để tạo SQL dự kiến.
6. Review SQL, sau đó chạy `liquibase update` tới đúng database.
7. Xác minh lịch sử trong `DATABASECHANGELOG` và kiểm tra schema sau migration.

Điều quan trọng là mọi bước phải dùng cùng root changelog và cùng cách phân giải đường dẫn. Nếu bước validate chạy trong repository root còn bước update chạy trong thư mục con với search path khác, kết quả kiểm tra trước đó không còn đại diện cho lệnh triển khai.

## 7. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| Không tìm thấy root changelog | Sai `--changelog-file`, sai `change-log`, working directory hoặc search path | In ra cấu hình lệnh, xác nhận file tồn tại và kiểm tra vị trí chạy |
| IDE chạy được nhưng JAR không chạy | Tài nguyên chưa được đóng gói hoặc đường dẫn còn chứa `src/main/resources` | Liệt kê nội dung JAR, sửa đường dẫn về gốc classpath |
| Tìm thấy root nhưng không tìm thấy changelog con | `include` trỏ sai vị trí hoặc thiếu `relativeToChangelogFile` phù hợp | Kiểm tra cấu trúc thư mục, đường dẫn tính từ file khai báo và search path |
| Không tìm thấy file SQL/CSV | File tham chiếu không có trong artifact hoặc đường dẫn không đúng | Kiểm tra `sqlFile`, `loadData`, `relativeToChangelogFile` và quyền đọc |
| CLI và Spring Boot tìm ra hai file khác nhau | Search path và classpath khác nhau hoặc có file trùng tên | Thu hẹp search path, chuẩn hóa resource path và kiểm tra artifact |
| Migration hoạt động trên máy cá nhân nhưng thất bại ở CI | Working directory, phân biệt chữ hoa/thường hoặc đường dẫn tuyệt đối khác nhau | Chạy pipeline từ working directory đã xác định và dùng đường dẫn tương thích môi trường |
| Changeset cũ bị nhận diện như mới sau khi di chuyển file | Đường dẫn logic thay đổi | Kiểm tra `DATABASECHANGELOG` và lập kế hoạch dùng `logicalFilePath` phù hợp |
| Changelog con tồn tại nhưng includeAll không nạp như dự kiến | Sai thư mục quét hoặc bộ lọc/định dạng file | Kiểm tra path, cấu trúc file, quy tắc quét và log của Liquibase |

Khi chẩn đoán, hãy xác định chính xác Liquibase đang chạy trong môi trường nào, root changelog thực tế là gì, search path hoặc classpath được cấu hình ra sao và file bị thiếu là file nào. Không giải quyết lỗi bằng cách thêm hàng loạt thư mục vào search path hoặc sao chép cùng một changelog vào nhiều nơi; cách đó dễ che khuất nguyên nhân và tạo ra kết quả khác nhau giữa môi trường.

## 8. Checklist trước khi chạy migration

- [ ] Đã chọn đúng một root changelog và cấu hình rõ trong CLI hoặc Spring Boot.
- [ ] Đường dẫn classpath bắt đầu từ gốc tài nguyên đã đóng gói, không chứa `src/main/resources`.
- [ ] Search path chỉ gồm những thư mục cần thiết và có thứ tự ổn định.
- [ ] Các `include`, `includeAll`, `sqlFile`, `loadData` trỏ đến tài nguyên thực sự tồn tại.
- [ ] Đã xác định đường dẫn tương đối với changelog hay được tìm qua search path.
- [ ] Cấu trúc thư mục và file tài nguyên được đóng gói đầy đủ trong artifact.
- [ ] CLI, Spring Boot và CI/CD dùng cùng bộ changelog và quy tắc phân giải đường dẫn.
- [ ] Đã xem xét tác động đến đường dẫn logic khi di chuyển hoặc đổi tên changelog.
- [ ] Đã chạy `validate`, `status` và `update-sql` trước khi áp dụng vào database đích.
- [ ] Đã xác minh database đích, context, label và thông tin kết nối của môi trường.

Khi root changelog, classpath và search path được xác định rõ, Liquibase có thể tìm đúng toàn bộ tài nguyên migration từ máy phát triển đến CI/CD và Spring Boot. Cấu trúc đường dẫn ổn định còn giúp giữ nguyên danh tính changeset trong lịch sử triển khai, giảm lỗi do môi trường và làm cho việc kiểm chứng hoặc rollback đáng tin cậy hơn.

