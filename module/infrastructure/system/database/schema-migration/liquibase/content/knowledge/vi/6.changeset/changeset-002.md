# Bộ định danh changeset và vai trò của đường dẫn

## 1. Vì sao định danh changeset quyết định tính an toàn của migration?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu bằng **changelog** và **changeset**. Người học cần hiểu precondition, checksum, lịch sử triển khai, migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Tất cả đều dựa trên một tiền đề: Liquibase phải nhận diện đúng changeset nào đã áp dụng vào database và changeset nào còn mới.

Một changeset là đơn vị thay đổi được Liquibase theo dõi trong lịch sử. Cùng một câu lệnh SQL có thể xuất hiện ở hai changeset khác nhau; ngược lại, một changeset có thể chứa nhiều thao tác. Vì vậy, Liquibase không xác định changeset bằng cách tìm xem bảng hoặc cột đã tồn tại hay chưa. Nó dùng **bộ định danh** của changeset để đối chiếu với bảng lịch sử trong cơ sở dữ liệu.

Một lỗi tưởng như nhỏ — đổi tên file changelog, thay đường dẫn include, đổi `id` hoặc `author` sau khi đã triển khai — có thể khiến Liquibase coi một changeset cũ là changeset chưa từng chạy. Nếu changeset đó tạo bảng, thêm cột, nạp dữ liệu hoặc xóa dữ liệu, hậu quả có thể là lỗi migration, ghi dữ liệu trùng lặp hoặc trạng thái schema không như dự kiến.

Sau bài này, bạn có thể phân biệt định danh với checksum, đọc được cách Liquibase ghi lịch sử, thiết kế mã changeset ổn định và xử lý an toàn khi thay đổi vị trí file changelog.

## 2. Bộ định danh là tổ hợp id + author + đường dẫn changelog

Liquibase nhận diện changeset bằng ba thành phần:

| Thành phần | Nguồn giá trị | Vai trò |
|---|---|---|
| `id` | Thuộc tính `id` trong changeset | Phân biệt changeset với các changeset khác trong cùng phạm vi tác giả và file |
| `author` | Thuộc tính `author` trong changeset | Phân biệt tác giả hoặc nhóm sở hữu changeset |
| Đường dẫn changelog | Đường dẫn logic của file chứa changeset, hoặc `logicalFilePath` nếu có cấu hình phù hợp | Phân biệt changeset thuộc những file changelog khác nhau |

Có thể hình dung khóa định danh:

```text
IDENTITY = (id, author, changelogFilePath)
```

Ví dụ, changelog `db/changelog/changes/010-create-customer.yaml` chứa:

```yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-customer
      author: platform
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: full_name
                  type: varchar(200)
```

Danh tính logic của changeset này có thể được biểu diễn là:

```text
(010-create-customer, platform, db/changelog/changes/010-create-customer.yaml)
```

Đây là ví dụ minh họa: giá trị đường dẫn thực tế được Liquibase ghi nhận phụ thuộc cách tìm tài nguyên và cấu hình đường dẫn khi thực thi. Không tự suy đoán giá trị `FILENAME` trong lịch sử; cần kiểm tra trực tiếp trên database đã triển khai.

### 2.1. id và author không cần duy nhất trên toàn bộ repository

Hai changeset sau có cùng `id` và `author` nhưng thuộc hai đường dẫn khác nhau:

```text
(001-init, platform, db/changelog/customer.yaml)
(001-init, platform, db/changelog/inventory.yaml)
```

Liquibase có thể xem chúng là hai changeset khác nhau vì thành phần đường dẫn khác nhau. Tuy nhiên, đặt mã dễ trùng gây khó khăn khi tra cứu log, review, báo lỗi và di chuyển file. Một quy ước mã chứa ngữ cảnh nghiệp vụ, ví dụ `20261119-01-create-customer`, thường dễ quản trị hơn mã `1` lặp lại ở nhiều nơi.

Trong cùng một file, hai changeset có cùng `id` và `author` thường tạo ra bộ định danh trùng, khiến quá trình validate/triển khai gặp vấn đề. Đừng dùng `id` giống nhau để biểu diễn hai phiên bản của một migration. Thay đổi mới cần changeset mới.

### 2.2. id không nhất thiết là thứ tự chạy

Giá trị `id` là một thành phần của danh tính, không phải bộ đếm mà Liquibase dùng để tự sắp thứ tự tất cả changeset. Liquibase duyệt cây changelog theo thứ tự khai báo/include, trừ các cơ chế điều chỉnh đặc biệt. Vì vậy, changeset có `id: 100` có thể được xử lý trước changeset có `id: 20` nếu changelog khai báo như vậy.

Bạn có thể dùng tiền tố ngày hoặc số thứ tự để hỗ trợ người đọc, nhưng thứ tự thực thi vẫn phải được quản lý bằng cấu trúc changelog và các điều kiện chạy phù hợp. Đổi `id` chỉ để “sắp số đẹp” sau khi đã triển khai sẽ làm đổi danh tính.

## 3. Bảng DATABASECHANGELOG lưu lịch sử nhận diện

Liquibase ghi lịch sử changeset đã thực thi hoặc được đánh dấu hợp lệ trong bảng `DATABASECHANGELOG` của database đích. Những trường quan trọng thường gồm:

| Cột | Ý nghĩa trong bài toán định danh |
|---|---|
| `ID` | Giá trị `id` trong changeset |
| `AUTHOR` | Giá trị `author` |
| `FILENAME` | Đường dẫn logic dùng để nhận diện changeset |
| `DATEEXECUTED` | Thời điểm thay đổi được ghi nhận |
| `ORDEREXECUTED` | Thứ tự thực thi được ghi nhận |
| `EXECTYPE` | Kiểu trạng thái thực thi, ví dụ `EXECUTED`, `MARK_RAN`, `RERAN` |
| `MD5SUM` | Checksum nội dung changeset được Liquibase lưu để kiểm tra thay đổi |

Ví dụ truy vấn chỉ đọc:

```sql
SELECT ID, AUTHOR, FILENAME, MD5SUM, DATEEXECUTED, EXECTYPE
FROM DATABASECHANGELOG
WHERE ID = '010-create-customer'
ORDER BY DATEEXECUTED;
```

Hãy kiểm tra cột `FILENAME` thực tế trước khi thay đổi cấu trúc changelog. Đường dẫn ở cột này là một phần của danh tính được Liquibase sử dụng, không đơn thuần là chú thích để người đọc tìm file.

Trong một lần chạy `update`, Liquibase đọc changelog và đối chiếu bộ ba (`id`, `author`, đường dẫn logic) với lịch sử. Nếu bộ ba đã được ghi nhận và không có thuộc tính yêu cầu chạy lại, changeset thường được bỏ qua. Nếu bộ ba chưa xuất hiện, Liquibase có thể xem changeset là mới và đưa vào danh sách cần áp dụng, sau khi xét bộ lọc và precondition.

Bảng `DATABASECHANGELOGLOCK` là cơ chế khóa điều phối migration đồng thời; nó **không thay thế** `DATABASECHANGELOG` và không quyết định danh tính changeset.

## 4. Đường dẫn changelog có thể thay đổi danh tính thế nào?

Giả sử lần triển khai đầu tiên có cấu trúc:

```text
db/
└── changelog/
    ├── master.yaml
    └── changes/
        └── 010-create-customer.yaml
```

File gốc `master.yaml` nạp changeset bằng:

```yaml
databaseChangeLog:
  - include:
      file: changes/010-create-customer.yaml
      relativeToChangelogFile: true
```

Sau khi migration đã chạy, lịch sử có thể ghi nhận:

```text
ID                  AUTHOR    FILENAME
010-create-customer platform  db/changelog/changes/010-create-customer.yaml
```

Bây giờ, nhóm phát triển chuyển file sang `db/changelog/releases/v1/010-create-customer.yaml` và sửa include để trỏ đến vị trí mới. Nếu không có cấu hình giữ đường dẫn logic, Liquibase có thể nhận diện tuple mới:

```text
(010-create-customer, platform, db/changelog/releases/v1/010-create-customer.yaml)
```

Hai tuple khác nhau ở thành phần thứ ba. Dù nội dung YAML và `id`/`author` giữ nguyên, Liquibase có thể xem thay đổi là chưa từng chạy. Nếu nó cố tạo lại bảng `customer`, migration có thể thất bại vì bảng đã tồn tại. Với các thay đổi có thể chạy nhiều lần nhưng không idempotent, rủi ro còn lớn hơn.

Các thay đổi dễ ảnh hưởng danh tính gồm:

- Đổi tên hoặc di chuyển file chứa changeset.
- Thay cấu trúc thư mục changelog và cách dùng `include`/`includeAll`.
- Đổi cách cung cấp changelog từ file bên ngoài sang tài nguyên classpath, dẫn đến đường dẫn logic được nhận diện khác.
- Chỉnh cấu hình search path hoặc điểm vào changelog làm thay đổi tên tài nguyên được ghi nhận.
- Thay `logicalFilePath` không đúng giá trị lịch sử.

**Điều cần kiểm tra là giá trị `FILENAME` mà Liquibase đã lưu**, không chỉ đường dẫn hiển thị trong editor hay vị trí vật lý tuyệt đối trên máy.

## 5. Dùng logicalFilePath để giữ định danh khi di chuyển file

`logicalFilePath` cho phép chỉ định đường dẫn logic dùng để nhận diện changeset, thay vì chỉ dựa vào vị trí vật lý hiện tại của changelog. Đây là cơ chế quan trọng khi cần tổ chức lại thư mục mà vẫn giữ lịch sử migration đã triển khai.

Giả sử changeset ban đầu đã được ghi với đường dẫn logic:

```text
db/changelog/changes/010-create-customer.yaml
```

Sau khi chuyển file sang thư mục `releases/v1`, có thể cấu hình đường dẫn logic ở cấp changeset như ví dụ sau:

```yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-customer
      author: platform
      logicalFilePath: db/changelog/changes/010-create-customer.yaml
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: full_name
                  type: varchar(200)
```

Khi ấy vị trí vật lý mới dùng để nạp nội dung, còn `logicalFilePath` cung cấp đường dẫn logic cũ cho danh tính changeset. Giá trị ví dụ chỉ đúng nếu nó **khớp chính xác** với đường dẫn lịch sử đã được lưu. Nếu trong `DATABASECHANGELOG` có prefix hoặc cách viết khác, phải căn cứ vào bản ghi thật.

### 5.1. Các bước di chuyển changelog an toàn

1. Đọc lịch sử ở những database đã triển khai; ghi lại chính xác `ID`, `AUTHOR`, `FILENAME` của các changeset bị ảnh hưởng.
2. Xác định vị trí vật lý mới và cập nhật các `include`/`includeAll` để Liquibase nạp đúng file.
3. Giữ nguyên `id` và `author`, giữ nguyên nội dung migration đã chạy; chỉ bổ sung cấu hình đường dẫn logic phù hợp với giá trị cũ nếu cần.
4. Chạy `validate` và kiểm tra `status --verbose` bằng đúng root changelog và database thử nghiệm có lịch sử đại diện.
5. Kiểm tra `update-sql`: changeset cũ không được xuất hiện dưới dạng thao tác “mới” vì chỉ đổi thư mục.
6. Khi có nhiều môi trường với lịch sử khác nhau, so sánh `FILENAME` thực tế từng môi trường trước khi triển khai thay đổi đường dẫn.

`logicalFilePath` không tự sửa mọi lịch sử trước đó. Nếu cùng một changeset đã được triển khai với **những đường dẫn logic khác nhau** ở các môi trường, chỉ một giá trị mới có thể không khớp cả hai. Khi đó cần thiết kế phương án đồng bộ có kiểm chứng, không tự ý sửa bảng lịch sử hoặc gắn đại một tên logic chung.

Tùy định dạng changelog và phiên bản Liquibase, `logicalFilePath` có thể được cấu hình ở các phạm vi khác nhau. Ví dụ ở trên dùng phạm vi changeset để thể hiện rõ một bộ định danh. Khi muốn áp dụng ở cấp changelog hoặc khi sử dụng các cơ chế include đặc biệt, cần xác nhận cú pháp được phiên bản Liquibase hiện dùng hỗ trợ và kiểm thử kết quả nhận diện.

### 5.2. Vì sao không dùng clearCheckSums để sửa lỗi đường dẫn?

`clearCheckSums` liên quan tới giá trị checksum đã lưu. Nó không làm cho đường dẫn logic mới trở thành đường dẫn cũ, cũng không hợp nhất các bộ định danh khác nhau. Vì vậy, dùng thao tác này khi Liquibase nhận diện nhầm changeset do đổi `FILENAME` sẽ không xử lý gốc vấn đề.

Tương tự, không nên tự xóa dòng `DATABASECHANGELOG` để ép Liquibase chạy lại; việc đó xóa bằng chứng lịch sử nhưng không hoàn tác những thay đổi schema hoặc dữ liệu đã tồn tại trong database.

## 6. Phân biệt định danh với checksum

Đây là hai cơ chế khác nhau nhưng phối hợp với nhau:

| Cơ chế | Câu hỏi Liquibase cần trả lời | Nếu thay đổi |
|---|---|---|
| Định danh: `id + author + file path` | “Đây có phải changeset đã được ghi nhận trong database?” | Có thể bị xem là changeset mới |
| Checksum của changeset | “Nội dung changeset được nhận diện này có thay đổi so với lần lưu lịch sử?” | Có thể phát sinh lỗi kiểm tra checksum hoặc hành vi chạy lại theo cấu hình |

Ví dụ: nếu giữ nguyên đường dẫn, `id` và `author` nhưng sửa một thao tác `createTable` trong changeset đã chạy, Liquibase có thể báo lỗi checksum không khớp. Ngược lại, nếu giữ nguyên toàn bộ nội dung nhưng đổi `id`, `author` hoặc đường dẫn logic, Liquibase có thể xem đó là changeset mới; checksum giống nhau không có nghĩa là cùng danh tính.

Hai thuộc tính thường gặp:

- `runOnChange: true`: cho phép chạy lại changeset đã được ghi nhận khi phần nội dung có ảnh hưởng đến checksum thay đổi theo cơ chế của Liquibase. Phù hợp hơn với một số đối tượng có thể tạo lại, chẳng hạn view hoặc stored procedure, khi được thiết kế có chủ đích.
- `runAlways: true`: yêu cầu chạy lại changeset trong các lần cập nhật phù hợp, dù bộ định danh đã có trong lịch sử.

Cả hai đều hoạt động trong ngữ cảnh **một changeset được nhận diện đúng**. Chúng không phải giải pháp để chữa bộ định danh sai, sửa file đã chạy tùy tiện hay giải quyết xung đột do đổi đường dẫn.

Quy tắc thực hành: sau khi một changeset cấu trúc/dữ liệu đã chạy ở môi trường dùng chung, hãy xem nội dung và danh tính của nó là bất biến. Muốn sửa lỗi hoặc mở rộng schema, tạo changeset mới với bộ định danh mới.

## 7. Quy ước đặt id và author cho nhóm phát triển

Quy ước tốt giúp giảm trùng lặp và dễ lần dấu lịch sử. Có thể dùng định dạng:

```text
<ngay-hoac-phien-ban>-<so-thu-tu>-<hanh-dong>-<doi-tuong>
```

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-01-create-customer
      author: platform
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
```

Có thể dùng mã ticket hoặc mã yêu cầu ở đầu `id` nếu nhóm đã có hệ thống đặt tên thống nhất. `author` có thể là tài khoản cá nhân hoặc định danh nhóm, miễn là ổn định và truy vết được. Không nên đổi `author` chỉ vì người phụ trách dự án chuyển nhóm; hành động đó thay đổi danh tính của changeset đã ghi nhận.

Một số nguyên tắc:

1. Không dùng lại cùng bộ ba (`id`, `author`, `FILENAME`) cho hai thay đổi khác nhau.
2. Không sửa `id` để phản ánh thứ tự mới, không đổi `author` để cập nhật người sở hữu.
3. Dùng mã đủ mô tả để người khác tìm changeset từ log và pull request.
4. Tách changeset mới khi cần sửa schema đã triển khai, kể cả sửa rất nhỏ.
5. Khi gộp nhánh, rà soát xung đột id/author trong cùng file hoặc trong các file sẽ có cùng đường dẫn logic.
6. Nếu dùng changelog SQL định dạng Liquibase, áp dụng cùng nguyên tắc định danh: khai báo `--changeset author:id` và giữ ổn định đường dẫn logic tương ứng.

Số thứ tự trong `id` giúp người đọc hiểu tiến trình, nhưng không làm thay Liquibase tự phát hiện mọi phụ thuộc. Thứ tự khai báo trong cây changelog, các bộ lọc môi trường và precondition vẫn quyết định thay đổi nào được xử lý.

## 8. Định danh, precondition và phụ thuộc giữa changeset

Một changeset thường phụ thuộc vào đối tượng đã được tạo bởi changeset trước đó. Khi định danh được giữ ổn định, Liquibase có thể theo dõi lịch sử chính xác và một số precondition có thể tham chiếu changeset đã thực thi.

Ví dụ precondition dạng `changeSetExecuted` có thể kiểm tra sự tồn tại của bản ghi lịch sử cụ thể:

```yaml
databaseChangeLog:
  - changeSet:
      id: 020-create-orders
      author: platform
      preConditions:
        - onFail: HALT
        - changeSetExecuted:
            id: 010-create-customer
            author: platform
            changeLogFile: db/changelog/changes/010-create-customer.yaml
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
```

Precondition này minh họa rằng đường dẫn cũng quan trọng khi tham chiếu lịch sử changeset khác. Nếu đường dẫn logic cũ bị đổi, điều kiện có thể không còn xác định đúng bản ghi đã chạy. Trong các tình huống khác, precondition kiểm tra trực tiếp bảng/cột có thể thích hợp hơn vì nó xác minh trạng thái schema thực tế. Cả hai cách đều cần xem xét theo mục tiêu migration.

Precondition không tự quản lý thứ tự thay đổi; nó chỉ đánh giá điều kiện trước khi áp dụng changeset. Nếu thiếu changeset tạo bảng, việc dừng migration sẽ an toàn hơn việc đánh dấu `MARK_RAN` một cách tùy tiện.

## 9. Tương tác với include, classpath và nhiều môi trường

Có thể hình dung một chuỗi đường dẫn:

```text
CLI / Spring Boot
      |
      v
Root changelog (changeLogFile / spring.liquibase.change-log)
      |
      +--> include changes/010-create-customer.yaml
      |        |
      |        +--> changeset (id, author, logical file path)
      |
      +--> include changes/020-create-orders.yaml
               |
               +--> changeset (id, author, logical file path)
```

Ở Liquibase CLI, root changelog có thể được tìm thông qua cấu hình `--changelog-file` và search path. Ở Spring Boot, root changelog thường được cấu hình bằng tài nguyên classpath:

```yaml
spring:
  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Changelog có thể chứa tham chiếu tương đối:

```yaml
databaseChangeLog:
  - include:
      file: changes/010-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/020-create-orders.yaml
      relativeToChangelogFile: true
```

Dùng cấu trúc thư mục ổn định giúp giảm nguy cơ Liquibase thấy các đường dẫn logic khác nhau giữa IDE, bản JAR và CI/CD. Tuy vậy, `relativeToChangelogFile: true` chỉ điều khiển cách tìm file được include; không nên mặc nhiên coi nó là cơ chế đảm bảo `FILENAME` sẽ giữ nguyên trong mọi tình huống đổi điểm vào hoặc đổi resource accessor.

Nếu một môi trường từng chạy Liquibase CLI với đường dẫn logic khác môi trường chạy Spring Boot, cần kiểm tra lịch sử `DATABASECHANGELOG` ở cả hai trước khi thống nhất phương thức triển khai. Cùng một database đích phải được kiểm soát để những lần cập nhật tiếp theo không đổi bộ định danh chỉ vì đổi cách chạy migration.

Dùng context, label hoặc thuộc tính `dbms` để chọn thay đổi theo môi trường không làm đổi trực tiếp bộ định danh changeset. Nhưng bộ lọc có thể khiến tập thay đổi đã triển khai khác nhau giữa các database. Đừng giả định “staging đã chạy” đồng nghĩa production có cùng lịch sử; hãy kiểm tra từng database.

## 10. Kịch bản kiểm chứng trước khi triển khai

Giả sử nhóm cần chuyển `010-create-customer.yaml` sang thư mục `releases/v1` sau khi changeset đã chạy trên staging. Hãy kiểm chứng theo trình tự:

1. **Chụp trạng thái lịch sử hiện tại**: truy vấn `ID`, `AUTHOR`, `FILENAME` và `MD5SUM` của changeset ở staging.
2. **Đổi vị trí vật lý và cập nhật include**: bảo đảm file mới được tìm thấy từ root changelog.
3. **Giữ bộ định danh**: nếu đường dẫn logic sẽ đổi, cấu hình `logicalFilePath` khớp đúng `FILENAME` trước đó.
4. **Kiểm tra changelog**: chạy `liquibase validate` bằng đúng kết nối và root changelog của bản triển khai.
5. **Kiểm tra changeset pending**: chạy `liquibase status --verbose`. Changeset `010-create-customer` không được xuất hiện là pending chỉ do di chuyển file.
6. **Xem SQL trước khi thực thi**: chạy `liquibase update-sql` và xác nhận không sinh lại thao tác `CREATE TABLE customer`.
7. **Đối chiếu các môi trường**: kiểm tra lịch sử của production nếu nó đã dùng một cách cấu hình khác.
8. **Triển khai có kiểm soát**: dùng pipeline đã được review; sau khi update, đối chiếu lịch sử, số changeset và trạng thái schema.

Các lệnh minh họa dùng chung cấu hình kết nối, changelog và search path đã được chuẩn hóa:

```bash
liquibase validate
liquibase status --verbose
liquibase update-sql
```

Ví dụ trên không yêu cầu chạy migration để học; điều quan trọng là biết sẽ kiểm tra điều gì khi môi trường thực tế cho phép thao tác. Trước bước `update`, hãy xác nhận database đích, credentials, context/label và file changelog mà lệnh thực sự truy cập.

Nếu kết quả `status` hoặc `update-sql` cho thấy một changeset cũ trở thành pending, cần dừng triển khai và tìm nguyên nhân nhận diện. Không cố vượt qua bằng cách thêm `if not exists` vào câu lệnh SQL hoặc đổi `onFail` thành `MARK_RAN` khi chưa hiểu lịch sử.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| Liquibase muốn tạo lại bảng đã tồn tại | `id`, `author` hoặc `FILENAME` của changeset cũ đã đổi | So sánh bộ ba hiện tại với `DATABASECHANGELOG`; khôi phục danh tính logic |
| Lỗi checksum sau khi sửa YAML | Nội dung changeset đã triển khai bị thay đổi trong khi bộ định danh giữ nguyên | Khôi phục changeset lịch sử hoặc tạo changeset mới; đánh giá `runOnChange` chỉ khi phù hợp |
| Một changeset bị coi là trùng định danh | Có hai khai báo cùng bộ ba hoặc file bị include lặp | Kiểm tra id/author, đường dẫn logic, include và phạm vi changelog |
| Staging chạy bình thường, production nhận diện khác | Hai database từng chạy bằng đường dẫn hoặc phương thức nạp khác nhau | Đọc `FILENAME` thực tế của cả hai và thiết kế cách đồng bộ đã kiểm chứng |
| Đổi tên file rồi dùng `clearCheckSums` vẫn lỗi | Đường dẫn logic là thành phần định danh, khác với checksum | Sửa cách nhận diện file, không dùng reset checksum để thay thế |
| Precondition `changeSetExecuted` không đạt | `changeLogFile` tham chiếu khác đường dẫn logic trong lịch sử | Đối chiếu với `FILENAME` và xem lại ý nghĩa điều kiện |
| Rollback không đúng tập thay đổi dự kiến | Changelog, lịch sử hoặc bộ định danh đã khác | Kiểm tra `DATABASECHANGELOG`, xác định đúng changeset/tag trước khi rollback |

Một thay đổi đường dẫn có thể làm migration bị áp dụng hai lần về mặt lịch sử, nhưng database chỉ có một trạng thái schema thực. Vì vậy, tuyệt đối không xem việc xóa hoặc sửa bản ghi lịch sử như cách hoàn tác một thay đổi. Rollback phải được thực hiện bằng quy trình và nội dung rollback phù hợp, có xét đến những thay đổi dữ liệu không thể đảo ngược.

## 12. Checklist khi review changeset

- [ ] Changeset có `id` và `author` rõ ràng, ổn định, dễ truy vết.
- [ ] Không có bộ ba định danh trùng trong tập changelog sẽ triển khai.
- [ ] File chứa changeset và cấu trúc `include` có đường dẫn dự đoán được.
- [ ] Changeset đã chạy không bị đổi `id`, `author` hoặc nội dung migration.
- [ ] Nếu di chuyển changelog, `logicalFilePath` khớp với `FILENAME` thực tế cần bảo toàn.
- [ ] Không nhầm checksum với bộ định danh và không dùng `clearCheckSums` để chữa lỗi đường dẫn.
- [ ] CLI, Spring Boot và CI/CD đều xác định cùng bộ changelog và cách tham chiếu tài nguyên hợp lệ.
- [ ] Đã kiểm tra `DATABASECHANGELOG` trên các môi trường liên quan, nhất là trước khi thay đổi cấu trúc thư mục.
- [ ] `validate`, `status --verbose` và `update-sql` không báo changeset cũ là pending ngoài ý muốn.
- [ ] Bước rollback được lên kế hoạch theo lịch sử thực tế, không phụ thuộc giả định rằng mọi database đã chạy cùng changeset.

Bộ định danh `(id, author, changelogFilePath)` là sợi dây nối một khai báo trong mã nguồn với một bản ghi lịch sử trên database. Giữ ổn định cả ba thành phần giúp Liquibase phân biệt migration mới với migration đã triển khai, kiểm tra checksum đúng đối tượng, phối hợp đa môi trường và lập kế hoạch cập nhật hoặc rollback đáng tin cậy.

