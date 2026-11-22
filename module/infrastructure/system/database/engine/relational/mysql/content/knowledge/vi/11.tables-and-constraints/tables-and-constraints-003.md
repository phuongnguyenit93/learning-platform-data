# PRIMARY KEY, UNIQUE và yêu cầu định danh dòng trong InnoDB

Mỗi hàng trong bảng cần có cách nhận diện rõ ràng để ứng dụng có thể đọc, cập nhật, xóa và tham chiếu chính xác. Trong MySQL, `PRIMARY KEY` và `UNIQUE` đều tạo ra quy tắc không trùng lặp, nhưng chúng có ý nghĩa và hành vi khác nhau. Với InnoDB, khóa chính còn quyết định cấu trúc lưu trữ dữ liệu: nó là clustered index, tức chỉ mục mà các hàng được tổ chức theo đó.

Vì vậy, chọn khóa chính không chỉ là quyết định đặt tên cột ID. Một khóa chính rộng hoặc thay đổi thường xuyên có thể làm tăng chi phí của mọi secondary index; một bảng thiếu khóa chính vẫn được InnoDB tạo định danh nội bộ nhưng ứng dụng không thể dùng định danh đó một cách ổn định. Bài học này giải thích cách chọn khóa, cách InnoDB tổ chức hàng và cách dùng `UNIQUE` để bảo vệ các quy tắc định danh nghiệp vụ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt `PRIMARY KEY`, `UNIQUE`, candidate key và surrogate key.
- Giải thích vai trò của khóa chính trong clustered index của InnoDB.
- Mô tả cách InnoDB chọn clustered index khi bảng không khai báo primary key.
- Hiểu vì sao secondary index chứa thông tin khóa chính và khóa chính rộng làm tăng chi phí lưu trữ.
- Thiết kế khóa đơn, khóa ghép và unique key theo phạm vi nghiệp vụ.
- Xử lý đúng `NULL` trong unique index và hiểu ảnh hưởng của collation đến tính duy nhất.
- Đánh giá `AUTO_INCREMENT`, UUID và khóa tự nhiên khi thiết kế định danh dòng.
- Kiểm tra bảng hiện có và lập kế hoạch bổ sung khóa cho bảng legacy.

## 1. Định danh dòng và các loại khóa

Định danh dòng là giá trị hoặc tập giá trị giúp xác định duy nhất một hàng. Một bảng khách hàng có thể dùng `customer_id`; một bảng chi tiết đơn hàng có thể dùng cặp `(order_id, line_no)`; một bảng người dùng theo tenant có thể có email duy nhất trong phạm vi từng tenant.

Các thuật ngữ cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Candidate key | Tập cột tối thiểu có thể nhận diện duy nhất một hàng theo quy tắc nghiệp vụ |
| Primary key | Candidate key được chọn làm định danh chính của bảng; mỗi bảng có tối đa một primary key |
| Alternate key | Candidate key khác không được chọn làm primary key; thường được bảo vệ bằng `UNIQUE` |
| Natural key | Khóa dùng dữ liệu có ý nghĩa nghiệp vụ, ví dụ mã quốc gia hoặc mã SKU |
| Surrogate key | Khóa nhân tạo không mang ý nghĩa nghiệp vụ, ví dụ `BIGINT AUTO_INCREMENT` |
| Composite key | Khóa gồm nhiều cột, ví dụ `(order_id, line_no)` |

Một bảng có thể có nhiều candidate key, nhưng chỉ chọn một trong số đó làm primary key. Các candidate key còn lại vẫn cần được bảo vệ bằng unique constraint nếu nghiệp vụ yêu cầu chúng không trùng.

Ví dụ, một người dùng trong hệ thống nhiều tenant có thể được định danh nội bộ bằng `user_id`; đồng thời email phải duy nhất trong từng tenant. `user_id` là primary key, còn `(tenant_id, email)` là alternate key được bảo vệ bằng `UNIQUE`.

## 2. PRIMARY KEY và UNIQUE khác nhau thế nào?

`PRIMARY KEY` bảo đảm tất cả giá trị khóa không trùng và không được `NULL`. `UNIQUE` cũng bảo đảm các giá trị khóa không trùng theo quy tắc so sánh của index, nhưng MySQL cho phép cột unique có `NULL` nếu cột không khai báo `NOT NULL`.

| Đặc điểm | PRIMARY KEY | UNIQUE |
|---|---|---|
| Số lượng trên một bảng | Tối đa một | Có thể có nhiều |
| Giá trị trùng | Không cho phép | Không cho phép đối với các khóa không NULL theo quy tắc unique index |
| NULL | Không được phép | Có thể được phép nếu cột cho phép NULL |
| Mục đích | Định danh chính của hàng | Bảo vệ các quy tắc duy nhất bổ sung |
| Index trong InnoDB | Clustered index | Secondary unique index, trừ khi được chọn làm clustered index khi bảng không có PK |

Ví dụ:

```sql
CREATE TABLE app_user (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(60) NOT NULL,
    email VARCHAR(254) NOT NULL,
    phone VARCHAR(30) NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_app_user_username (username),
    UNIQUE KEY uq_app_user_email (email),
    UNIQUE KEY uq_app_user_phone (phone)
) ENGINE = InnoDB;
```

Trong ví dụ, `user_id` định danh chính. Username, email và số điện thoại được bảo vệ bởi các unique index độc lập. `phone` cho phép `NULL`, nên nhiều hàng có thể chưa cung cấp số điện thoại mà không vi phạm unique constraint. Nếu nghiệp vụ bắt buộc mọi người dùng phải có số điện thoại duy nhất, cần khai báo `phone NOT NULL` sau khi xác định quy tắc dữ liệu.

### 2.1. UNIQUE cho phép nhiều NULL

Trong MySQL, `NULL` biểu thị giá trị chưa biết hoặc chưa có. Hai giá trị `NULL` không được xem là bằng nhau trong phép so sánh thông thường; vì vậy unique index có thể chứa nhiều `NULL`.

```sql
INSERT INTO app_user (username, email, phone)
VALUES
    ('linh01', 'linh01@example.test', NULL),
    ('minh02', 'minh02@example.test', NULL);
```

Hai hàng này hợp lệ dù cùng có `phone = NULL`. Nhưng nếu thử thêm cùng một số điện thoại đã có, câu lệnh sẽ bị từ chối:

```sql
INSERT INTO app_user (username, email, phone)
VALUES ('hoa03', 'hoa03@example.test', '0901234567');

INSERT INTO app_user (username, email, phone)
VALUES ('nam04', 'nam04@example.test', '0901234567');
```

Giả sử số `0901234567` đã được thêm ở hàng đầu tiên của bài kiểm thử, câu insert thứ hai vi phạm `uq_app_user_phone`.

Với unique index ghép, nếu một hoặc nhiều thành phần khóa là `NULL`, MySQL cũng có thể cho phép nhiều hàng có tổ hợp chứa `NULL`. Ví dụ `UNIQUE (tenant_id, external_code)` không bảo đảm chỉ có một hàng cho mỗi tenant nếu `external_code` được phép `NULL`. Nếu quy tắc nghiệp vụ yêu cầu mã ngoài phải tồn tại và duy nhất, hãy khai báo cột đó `NOT NULL`.

### 2.2. UNIQUE ghép theo phạm vi nghiệp vụ

Một giá trị có thể không cần duy nhất trên toàn hệ thống mà chỉ duy nhất trong một phạm vi. Ví dụ, hai tenant khác nhau có thể cùng dùng mã khách hàng `C001`, nhưng một tenant không được có hai khách hàng cùng mã đó.

```sql
CREATE TABLE tenant_customer (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_code VARCHAR(40) NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_tenant_customer_code (tenant_id, customer_code)
) ENGINE = InnoDB;
```

Unique index ghép bảo vệ đúng phạm vi: `(tenant_id, customer_code)`. Không nên tạo `UNIQUE(customer_code)` nếu mã chỉ duy nhất trong tenant, vì constraint toàn cục sẽ từ chối những mã hợp lệ ở tenant khác.

### 2.3. Collation ảnh hưởng đến tính duy nhất của chuỗi

Unique index trên cột chuỗi sử dụng quy tắc so sánh của collation. Với collation không phân biệt hoa thường, `Admin` và `admin` có thể được xem là cùng một giá trị. Với collation không phân biệt dấu, một số chuỗi khác dấu có thể so sánh bằng nhau theo quy tắc của collation đó.

```sql
CREATE TABLE login_name_demo (
    login_name VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    UNIQUE KEY uq_login_name (login_name)
) ENGINE = InnoDB;
```

Trong MySQL 8.0, collation `utf8mb4_0900_ai_ci` không phân biệt hoa thường và dấu. Vì vậy, cần kiểm tra quy tắc so sánh trước khi chọn collation cho email, username, mã định danh hoặc SKU. Collation không chỉ ảnh hưởng cách `ORDER BY`; nó còn ảnh hưởng việc hai giá trị có bị xem là trùng trong unique index hay không.

## 3. InnoDB dùng PRIMARY KEY làm clustered index

InnoDB lưu dữ liệu hàng trong cấu trúc B-tree của clustered index. Khi bảng có primary key, primary key là clustered index: các bản ghi trong leaf page của B-tree chứa dữ liệu hàng và được tổ chức theo khóa chính.

Điều này khác với cách một số người hình dung rằng bảng là một vùng dữ liệu riêng và tất cả index chỉ trỏ đến vị trí vật lý cố định. Trong InnoDB, secondary index tìm được giá trị khóa phụ và kèm thông tin khóa chính để xác định hàng tương ứng trong clustered index.

```text
                  PRIMARY KEY B-tree
              (clustered index của InnoDB)
                         |
             +-----------+-----------+
             |                       |
          Leaf page               Leaf page
        [PK + dữ liệu]           [PK + dữ liệu]

       SECONDARY INDEX: uq_email
             [email, PK]
                   |
                   +------> tra cứu hàng theo PK
```

Ví dụ bảng:

```sql
CREATE TABLE customer_account (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_customer_account_email (email),
    KEY idx_customer_account_created_at (created_at)
) ENGINE = InnoDB;
```

`PRIMARY KEY(account_id)` là clustered index. `uq_customer_account_email` và `idx_customer_account_created_at` là secondary index. Khi tìm một email qua unique index, InnoDB có thể tìm entry email rồi dùng `account_id` được lưu trong entry đó để đọc hàng trong clustered index.

## 4. InnoDB làm gì khi bảng không có PRIMARY KEY?

InnoDB vẫn cần một clustered index để tổ chức hàng. Khi tạo bảng không khai báo primary key, InnoDB tìm một unique index có tất cả cột thành phần đều `NOT NULL` để dùng làm clustered index. Nếu không có unique index phù hợp, InnoDB tự tạo một clustered index ẩn với row ID nội bộ 6 byte; index này thường được gọi là `GEN_CLUST_INDEX`.

Điều đó có nghĩa là bảng thiếu primary key không phải không có định danh nội bộ. Tuy nhiên, row ID ẩn do InnoDB tạo không phải cột SQL mà ứng dụng có thể truy vấn, lưu vào bảng khác hoặc dùng làm hợp đồng định danh ổn định. Ứng dụng không thể yêu cầu `SELECT hidden_row_id ...` để nhận diện hàng.

Ví dụ bảng không có primary key và không có unique key phù hợp:

```sql
CREATE TABLE raw_import_row (
    source_name VARCHAR(80) NOT NULL,
    source_record_code VARCHAR(80) NULL,
    payload JSON NOT NULL,
    imported_at DATETIME(6) NOT NULL
) ENGINE = InnoDB;
```

Trong bảng này không có primary key và cũng không có unique index toàn bộ cột `NOT NULL`. InnoDB tạo clustered index ẩn để tổ chức dữ liệu. Nhưng nếu hai hàng có cùng `source_name`, `source_record_code` và `payload`, ứng dụng không có khóa khai báo để phân biệt chúng một cách đáng tin cậy.

### 4.1. Thứ tự chọn clustered index

Về nguyên tắc, InnoDB chọn theo thứ tự:

1. Dùng `PRIMARY KEY` nếu bảng có khai báo.
2. Nếu không có primary key, dùng unique index đầu tiên mà mọi cột thành phần đều `NOT NULL`.
3. Nếu không có khóa phù hợp, tạo clustered index ẩn trên row ID nội bộ 6 byte.

Nếu InnoDB dùng một unique key làm clustered index, khóa đó phải đáp ứng điều kiện `NOT NULL` ở tất cả cột. Một unique index cho phép `NULL` không phải lựa chọn phù hợp theo quy tắc này.

## 5. Secondary index lưu thông tin khóa chính

Một đặc điểm quan trọng của InnoDB là mỗi entry trong secondary index chứa các cột của secondary key và khóa chính của hàng. Khóa chính được dùng để tìm hàng trong clustered index. Vì vậy, độ rộng của primary key ảnh hưởng đến tất cả secondary index trên bảng.

Ví dụ bảng có primary key `BIGINT` và ba secondary index:

```sql
CREATE TABLE support_ticket (
    ticket_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    ticket_code VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (ticket_id),
    UNIQUE KEY uq_ticket_tenant_code (tenant_id, ticket_code),
    KEY idx_ticket_tenant_status (tenant_id, status),
    KEY idx_ticket_created_at (created_at)
) ENGINE = InnoDB;
```

Các secondary index cần mang đủ thông tin khóa chính `ticket_id` để xác định hàng. Nếu primary key là một chuỗi dài hoặc nhiều cột, phần khóa chính đi kèm có thể làm index lớn hơn, giảm số entry trên mỗi page và tăng I/O khi đọc/ghi.

Vì vậy, primary key của InnoDB thường nên:

- Ngắn gọn để giảm kích thước secondary index.
- Ổn định, ít hoặc không thay đổi sau khi tạo hàng.
- Có giá trị luôn tồn tại (`NOT NULL`).
- Được tạo theo quy tắc duy nhất và có thể dùng làm tham chiếu từ bảng khác.
- Có kiểu dữ liệu phù hợp với quy mô dự kiến, tránh chọn kiểu quá nhỏ dẫn đến hết miền giá trị.

Đây là lý do `BIGINT` hoặc `INT` surrogate key thường được dùng làm primary key cho bảng giao dịch có nhiều secondary index. Điều đó không có nghĩa mọi bảng đều phải dùng `AUTO_INCREMENT`; khóa ghép hoặc khóa tự nhiên vẫn hợp lý khi phản ánh chính xác mô hình dữ liệu.

## 6. Chọn khóa tự nhiên hay surrogate key?

Khóa tự nhiên là dữ liệu đã có ý nghĩa nghiệp vụ, ví dụ số hộ chiếu, mã SKU hoặc mã quốc gia. Surrogate key là định danh kỹ thuật do hệ thống sinh ra, ví dụ `BIGINT AUTO_INCREMENT`.

| Tiêu chí | Khóa tự nhiên | Surrogate key |
|---|---|---|
| Ý nghĩa | Có ý nghĩa nghiệp vụ | Không mang ý nghĩa nghiệp vụ |
| Độ ổn định | Có thể thay đổi theo quy tắc nghiệp vụ | Thường ổn định nếu được thiết kế đúng |
| Độ rộng | Có thể là chuỗi dài hoặc nhiều cột | Thường nhỏ và cố định |
| Tính duy nhất | Cần constraint theo quy tắc nghiệp vụ | Cần cơ chế sinh ID và primary key |
| Khả năng tích hợp | Thuận tiện khi nguồn ngoài đã có mã chuẩn | Thuận tiện cho tham chiếu nội bộ |

Một thiết kế phổ biến là dùng surrogate key làm primary key, đồng thời giữ natural key bằng unique constraint:

```sql
CREATE TABLE product_catalog (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_product_catalog_sku (sku)
) ENGINE = InnoDB;
```

`product_id` là định danh nội bộ ổn định. `sku` vẫn duy nhất theo quy tắc catalog, nhưng nếu doanh nghiệp thay đổi mã SKU thì không phải cập nhật khóa ngoại của mọi bảng tham chiếu đến `product_id`.

Không phải lúc nào surrogate key cũng tốt hơn. Với bảng nối thể hiện quan hệ nhiều-nhiều, cặp khóa ngoại có thể chính là định danh tự nhiên của hàng:

```sql
CREATE TABLE student_course (
    student_id BIGINT UNSIGNED NOT NULL,
    course_id BIGINT UNSIGNED NOT NULL,
    enrolled_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (student_id, course_id),
    KEY idx_student_course_course (course_id)
) ENGINE = InnoDB;
```

Một hàng chỉ biểu diễn một lần ghi danh của một sinh viên vào một khóa học, vì vậy `(student_id, course_id)` là khóa ghép tự nhiên. Nếu nghiệp vụ cho phép ghi danh nhiều lần hoặc lưu lịch sử theo đợt, cần thêm thành phần như `enrollment_no` hoặc dùng surrogate key cùng unique constraint phản ánh đúng quy tắc.

## 7. Thiết kế khóa ghép và thứ tự cột

Primary key có thể gồm nhiều cột. Với khóa ghép, thứ tự cột ảnh hưởng đến thứ tự clustered index và các truy vấn có thể tận dụng leftmost prefix của index.

Ví dụ chi tiết đơn hàng:

```sql
CREATE TABLE order_line (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no SMALLINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_line_product (product_id)
) ENGINE = InnoDB;
```

Khóa `(order_id, line_no)` thể hiện dòng số mấy trong đơn hàng. Index này hỗ trợ tốt:

```sql
SELECT *
FROM order_line
WHERE order_id = 9001;

SELECT *
FROM order_line
WHERE order_id = 9001
  AND line_no = 2;
```

Nhưng nó không tương đương index bắt đầu bằng `line_no` cho truy vấn chỉ lọc theo `line_no`. Với clustered index, thứ tự khóa chính cũng là thứ tự tổ chức dữ liệu; chọn thứ tự cột theo cách truy cập thường gặp có thể cải thiện locality và phạm vi đọc.

Nếu bảng con tham chiếu khóa ghép, khai báo foreign key theo cùng thứ tự và kiểu dữ liệu tương thích:

```sql
CREATE TABLE order_line_note (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no SMALLINT UNSIGNED NOT NULL,
    note_text VARCHAR(500) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_line_note_line
        FOREIGN KEY (order_id, line_no)
        REFERENCES order_line (order_id, line_no)
) ENGINE = InnoDB;
```

Các cột tham chiếu phải tương thích về kiểu và dấu (`SIGNED`/`UNSIGNED`); với chuỗi cần chú ý charset/collation. InnoDB cần index phù hợp cho khóa ngoại. MySQL có thể tự tạo index ở phía bảng con nếu chưa có index phù hợp, nhưng nên khai báo và đặt tên index rõ ràng để quản trị schema dễ hơn.

## 8. AUTO_INCREMENT: tiện lợi nhưng không phải số thứ tự liên tục

`AUTO_INCREMENT` là cách phổ biến để sinh surrogate key số nguyên:

```sql
CREATE TABLE payment_attempt (
    attempt_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    attempted_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (attempt_id),
    KEY idx_payment_attempt_order (order_id)
) ENGINE = InnoDB;
```

Khi insert, có thể bỏ qua `attempt_id` để MySQL cấp giá trị:

```sql
INSERT INTO payment_attempt (order_id)
VALUES (9001), (9002), (9003);
```

Không được xem `AUTO_INCREMENT` là bộ đếm liên tục không có khoảng trống. Giá trị có thể bị khuyết do transaction rollback, insert thất bại, thao tác xóa, cấp phát đồng thời hoặc cách máy chủ quản lý bộ đếm. Không dùng ID để suy ra số lượng hàng, số hóa đơn liên tục hoặc thứ tự commit chính xác.

Nếu cần đọc theo thời điểm hoặc thứ tự tạo, hãy dùng `ORDER BY attempted_at, attempt_id`. Không có `ORDER BY`, SQL không bảo đảm thứ tự kết quả; thứ tự clustered index không phải hợp đồng sắp xếp của truy vấn.

`AUTO_INCREMENT` cũng có giới hạn theo kiểu số. Chọn `INT` hay `BIGINT` dựa trên tốc độ tăng và tuổi thọ bảng. Với hệ thống giao dịch có quy mô lớn, `BIGINT UNSIGNED` cung cấp miền giá trị rộng hơn, nhưng cần thống nhất kiểu đó ở các foreign key tham chiếu.

## 9. UUID và khóa phân tán

Trong hệ thống nhiều dịch vụ hoặc cần tạo ID ở nhiều node mà không chờ một database cấp số, UUID có thể là lựa chọn. UUID dạng văn bản 36 ký tự thường rộng hơn đáng kể so với `BIGINT`; lưu chuỗi dài làm primary key sẽ làm tăng kích thước clustered index và secondary index.

Nếu dùng UUID, cân nhắc:

- Lưu ở dạng nhị phân 16 byte (`BINARY(16)`) thay vì chuỗi văn bản 36 ký tự nếu ứng dụng và công cụ hỗ trợ tốt.
- Xác định phiên bản UUID và thứ tự byte nhất quán giữa các dịch vụ.
- Đánh giá tính tuần tự theo thời gian của UUID; UUID ngẫu nhiên có thể phân tán insert trên nhiều page, làm tăng page split và giảm locality so với khóa tăng dần.
- Không hy sinh tính duy nhất hoặc tính ổn định chỉ để tối ưu index; đo workload thực tế.

MySQL cung cấp `UUID_TO_BIN()` và `BIN_TO_UUID()` để chuyển đổi UUID. Tham số swap flag của `UUID_TO_BIN()` chỉ nên dùng theo quy ước nhất quán giữa ghi và đọc; không trộn UUID đã chuyển đổi theo hai cách khác nhau.

```sql
CREATE TABLE distributed_event (
    event_id BINARY(16) NOT NULL,
    event_type VARCHAR(60) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_distributed_event_time (occurred_at)
) ENGINE = InnoDB;

INSERT INTO distributed_event (event_id, event_type, occurred_at)
VALUES (UUID_TO_BIN(UUID()), 'ORDER_CREATED', CURRENT_TIMESTAMP(6));
```

Đoạn trên minh họa cách lưu UUID ở dạng nhị phân. Nếu dùng UUID ngẫu nhiên làm clustered key cho bảng có lượng insert lớn, hãy so sánh với chiến lược ID tuần tự hoặc UUID có thứ tự thời gian trước khi quyết định.

## 10. Kiểm tra khóa và index hiện có

Để xem định nghĩa đầy đủ của bảng:

```sql
SHOW CREATE TABLE customer_account;
```

Để xem các index và cột thành phần:

```sql
SHOW INDEX FROM customer_account;
```

Các cột thường cần xem trong kết quả `SHOW INDEX`:

| Cột | Ý nghĩa |
|---|---|
| `Key_name` | Tên index; `PRIMARY` là primary key |
| `Non_unique` | `0` là unique, `1` là không unique |
| `Seq_in_index` | Vị trí cột trong index ghép |
| `Column_name` | Cột tham gia index |
| `Sub_part` | Độ dài prefix nếu index chỉ một phần cột |
| `Index_type` | Kiểu index, thường là `BTREE` với index InnoDB thông thường |

Có thể kiểm kê index qua `INFORMATION_SCHEMA.STATISTICS`:

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    INDEX_TYPE
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer_account'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Để xác nhận engine và ước lượng dung lượng:

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    ROW_FORMAT,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer_account';
```

`TABLE_ROWS` với InnoDB thường là số ước lượng. Khi cần số hàng chính xác, dùng `COUNT(*)` và đánh giá chi phí trên bảng lớn.

## 11. Xử lý lỗi trùng khóa và upsert

Khi insert một giá trị đã tồn tại trong primary key hoặc unique index, MySQL trả lỗi duplicate key. Đây là cơ chế bảo vệ tính duy nhất ở database, kể cả khi nhiều request cùng ghi đồng thời.

Không nên chỉ kiểm tra trước bằng `SELECT` rồi mới `INSERT` và cho rằng không thể trùng. Hai transaction có thể cùng thấy chưa có hàng trước khi một transaction insert; unique index mới là lớp bảo vệ cuối cùng.

Nếu nghiệp vụ cho phép cập nhật khi khóa đã tồn tại, dùng `INSERT ... ON DUPLICATE KEY UPDATE`:

```sql
INSERT INTO product_catalog (sku, product_name)
VALUES ('KB-001', 'Bàn phím cơ')
ON DUPLICATE KEY UPDATE
    product_name = VALUES(product_name);
```

Trong MySQL 8.0.20 trở lên, việc dùng `VALUES(column)` trong phần cập nhật đã bị deprecated; cú pháp row alias được khuyến nghị cho phiên bản hiện đại:

```sql
INSERT INTO product_catalog (sku, product_name)
VALUES ('KB-001', 'Bàn phím cơ') AS new
ON DUPLICATE KEY UPDATE
    product_name = new.product_name;
```

Hãy chọn đúng semantics: upsert có thể cập nhật một hàng khi bất kỳ primary/unique key nào bị trùng. Nếu bảng có nhiều unique constraint, phải hiểu khóa nào có thể kích hoạt nhánh cập nhật và tránh để hai quy tắc nghiệp vụ dẫn đến cập nhật nhầm hàng.

`INSERT IGNORE` có thể biến một số lỗi thành warning và bỏ qua hàng vi phạm, nhưng cũng có thể che giấu dữ liệu không hợp lệ. Chỉ dùng khi chính sách nhập liệu xác định rõ cách xử lý bản ghi trùng và ứng dụng kiểm tra được số hàng bị bỏ qua.

## 12. Bổ sung khóa cho bảng legacy

Một bảng cũ có thể không có primary key vì được tạo từ file import, log hoặc ứng dụng đời trước. Trước khi thêm khóa, hãy xác định định danh nghiệp vụ và kiểm tra dữ liệu hiện tại.

### 12.1. Tìm hàng trùng theo khóa dự kiến

Giả sử dự kiến dùng `source_name` và `source_record_code` làm unique key:

```sql
SELECT
    source_name,
    source_record_code,
    COUNT(*) AS duplicate_count
FROM legacy_import
WHERE source_name IS NOT NULL
  AND source_record_code IS NOT NULL
GROUP BY source_name, source_record_code
HAVING COUNT(*) > 1;
```

Kiểm tra giá trị null:

```sql
SELECT COUNT(*) AS rows_with_missing_key
FROM legacy_import
WHERE source_name IS NULL
   OR source_record_code IS NULL;
```

Nếu khóa dự kiến là định danh bắt buộc, phải xử lý các hàng trùng và thiếu trước khi tạo unique constraint. Không tự xóa hàng trùng chỉ để DDL thành công; cần xác định hàng nào là bản ghi chuẩn, có thể hợp nhất hay phải giữ lịch sử.

### 12.2. Thêm surrogate key

Nếu không có natural key ổn định, có thể thêm cột surrogate:

```sql
ALTER TABLE legacy_import
    ADD COLUMN import_row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ADD PRIMARY KEY (import_row_id);
```

Trước khi chạy, kiểm tra bảng chưa có primary key, cột mới chưa tồn tại và phiên bản/engine hỗ trợ thay đổi theo kế hoạch. Với bảng lớn, thao tác có thể dựng lại clustered index, tiêu tốn I/O và gây khóa; cần thử trên bản sao và lập cửa sổ thay đổi.

Sau khi có primary key, xác định thêm unique constraint cho mã nguồn nếu nghiệp vụ yêu cầu:

```sql
ALTER TABLE legacy_import
    ADD UNIQUE KEY uq_legacy_import_source_record
        (source_name, source_record_code);
```

Chỉ thêm unique constraint sau khi xử lý dữ liệu trùng và null theo đúng quy tắc nghiệp vụ.

## 13. Các nguyên tắc thiết kế khóa cho InnoDB

Khi tạo bảng mới, hãy đánh giá các nguyên tắc sau:

**Chọn một primary key rõ ràng.** Không để InnoDB phải dựa vào row ID ẩn nếu ứng dụng cần cập nhật, xóa, tham chiếu hoặc đồng bộ từng hàng.

**Ưu tiên khóa ngắn và ổn định.** Khóa chính được mang theo secondary index. Khóa càng rộng thì chi phí lưu trữ và I/O của các index phụ càng tăng.

**Tách định danh kỹ thuật khỏi quy tắc nghiệp vụ khi cần.** Dùng surrogate key làm primary key và unique constraint cho email, SKU hoặc mã ngoài nếu chúng phải duy nhất.

**Đặt NOT NULL cho thành phần định danh bắt buộc.** Đặc biệt với unique key ghép, `NULL` có thể cho phép nhiều tổ hợp mà người thiết kế tưởng là đã được bảo vệ.

**Chọn thứ tự cột trong khóa ghép theo truy vấn và quan hệ.** Thứ tự ảnh hưởng leftmost prefix, thứ tự clustered data và cách bảng con tham chiếu khóa.

**Đồng bộ kiểu dữ liệu ở khóa ngoại.** Các cột tham chiếu cần kiểu tương thích, bao gồm dấu số và thuộc tính chuỗi.

**Không dùng ID để suy ra thứ tự nếu chưa có ORDER BY.** Khi cần thứ tự, sắp xếp rõ ràng theo thời gian và một khóa duy nhất làm tie-breaker.

**Không xem AUTO_INCREMENT là số liên tục.** Nếu nghiệp vụ cần số chứng từ liên tục, đó là một quy trình cấp số riêng với kiểm soát đồng thời và quy tắc kiểm toán.

## 14. Checklist trước khi chốt PRIMARY KEY và UNIQUE

- Đã xác định các candidate key và quy tắc duy nhất theo phạm vi nghiệp vụ.
- Đã chọn primary key không null, duy nhất và ổn định.
- Đã cân nhắc kích thước khóa chính vì InnoDB mang khóa chính trong secondary index.
- Đã xác định khóa tự nhiên hay surrogate key phù hợp với vòng đời dữ liệu.
- Đã kiểm tra unique key có cho phép `NULL` hay cần `NOT NULL`.
- Đã kiểm tra collation của cột chuỗi để hiểu chính xác quy tắc trùng lặp.
- Đã chọn thứ tự cột cho khóa ghép theo truy vấn và quan hệ tham chiếu.
- Đã đồng bộ kiểu dữ liệu của primary/foreign key.
- Đã kiểm tra bảng có primary key thực sự qua `SHOW CREATE TABLE`.
- Đã biết InnoDB dùng unique key phù hợp hoặc hidden row ID nếu thiếu primary key.
- Đã kiểm tra duplicate và null trước khi thêm unique constraint vào dữ liệu cũ.
- Đã đánh giá tác động khóa, dung lượng và thời gian khi thay đổi clustered index trên bảng lớn.

Trong InnoDB, primary key vừa là định danh logic của hàng vừa là clustered index tổ chức dữ liệu. Secondary index dựa vào khóa chính để tìm hàng, nên khóa chính ngắn, ổn định và được chọn có chủ đích sẽ giúp giảm chi phí lưu trữ và truy cập. `UNIQUE` bảo vệ các candidate key bổ sung, nhưng cần hiểu cách MySQL xử lý `NULL` và collation. Khi thiết kế cả hai loại khóa theo quy tắc nghiệp vụ và workload, bảng sẽ có định danh rõ ràng, quan hệ đáng tin cậy và dễ tối ưu hơn.
