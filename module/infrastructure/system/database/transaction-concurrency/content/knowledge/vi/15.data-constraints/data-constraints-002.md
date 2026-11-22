# UNIQUE và tranh chấp chèn cùng khóa nghiệp vụ

Trong nhiều nghiệp vụ, một giá trị phải xác định duy nhất một đối tượng: email đăng ký tài khoản, mã đơn hàng từ hệ thống đối tác, mã nhân viên trong một công ty hoặc mã sản phẩm trong một cửa hàng. Giá trị như vậy thường được gọi là **business key (khóa nghiệp vụ)**.

Khi nhiều giao dịch cùng tạo bản ghi với một khóa nghiệp vụ, chúng có thể chạy đồng thời và cùng kiểm tra rằng khóa đó chưa tồn tại. Nếu chỉ dựa vào câu `SELECT` kiểm tra trước khi `INSERT`, cả hai giao dịch có thể cùng nhìn thấy kết quả “chưa có” rồi cùng thử chèn. Cách bảo vệ chắc chắn là đặt **UNIQUE constraint hoặc UNIQUE index** ở cơ sở dữ liệu. Cơ chế duy nhất của DBMS sẽ điều phối các lần chèn cạnh tranh và chỉ cho phép dữ liệu cuối cùng thỏa mãn quy tắc duy nhất.

## 1. Khóa nghiệp vụ và yêu cầu duy nhất

Giả sử ứng dụng đăng ký tài khoản bằng email. Mỗi email đã chuẩn hóa chỉ được gắn với một tài khoản.

| id | email | full_name |
|---:|---|---|
| 101 | an@example.com | An |
| 102 | binh@example.com | Bình |

Trong ví dụ này:

- `id` là khóa chính (primary key), thường do hệ thống sinh ra.
- `email` là khóa nghiệp vụ vì người dùng hoặc hệ thống bên ngoài dùng nó để nhận diện tài khoản.
- Hai tài khoản không được có cùng email theo quy tắc nghiệp vụ.

Khóa chính và khóa nghiệp vụ có vai trò khác nhau. Một tài khoản có thể có `id` khác nhau nhưng vẫn vi phạm quy tắc nếu hai hàng cùng chứa một email. Vì vậy, chỉ đặt `PRIMARY KEY(id)` là chưa đủ.

## 2. Định nghĩa UNIQUE constraint

Có thể khai báo tính duy nhất ngay trong cấu trúc bảng:

```sql
CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    CONSTRAINT uq_users_email UNIQUE (email)
);
```

`UNIQUE(email)` yêu cầu các giá trị email thuộc phạm vi ràng buộc không trùng nhau theo quy tắc so sánh của DBMS và kiểu dữ liệu/collation được sử dụng. DBMS thường triển khai constraint bằng một unique index để kiểm tra hiệu quả khi chèn và cập nhật.

Nếu bảng đã tồn tại, có thể thêm constraint:

```sql
ALTER TABLE users
ADD CONSTRAINT uq_users_email UNIQUE (email);
```

Lệnh này sẽ thất bại nếu dữ liệu hiện tại đã có các giá trị trùng theo quy tắc của constraint. Trước khi triển khai trên bảng lớn, cần kiểm tra dữ liệu trùng và chọn quy trình tạo index/constraint phù hợp với DBMS để giảm ảnh hưởng đến ghi và thời gian khóa.

Một unique index cũng có thể được tạo trực tiếp:

```sql
CREATE UNIQUE INDEX ux_users_email
ON users (email);
```

Constraint diễn đạt quy tắc toàn vẹn dữ liệu ở mức schema; unique index là cấu trúc hỗ trợ kiểm tra và tìm kiếm. Khả năng thêm constraint dựa trên index có sẵn, tên đối tượng và cú pháp phụ thuộc DBMS.

## 3. Vì sao SELECT kiểm tra trước khi INSERT không đủ?

Một cách triển khai thường gặp là:

```sql
SELECT id
FROM users
WHERE email = 'an@example.com';

-- Nếu không tìm thấy thì INSERT.
```

Vấn đề là hai giao dịch có thể thực hiện câu `SELECT` trước khi một giao dịch nào chèn dữ liệu.

### Lịch thực thi có tranh chấp

Giả sử email `new@example.com` chưa tồn tại. Hai yêu cầu đăng ký đến gần như đồng thời:

```text
Thời gian ↓

T1                                      T2
-----------------------------------     -----------------------------------
BEGIN                                   BEGIN
SELECT email → không có hàng            
                                        SELECT email → không có hàng
Kết luận: email còn trống                Kết luận: email còn trống
INSERT new@example.com                  
                                        INSERT new@example.com
COMMIT                                  COMMIT
```

Nếu không có ràng buộc duy nhất, cả hai lần chèn có thể thành công. Bảng sẽ có hai tài khoản mang cùng email dù mỗi giao dịch đều đã kiểm tra trước.

Đây là một **race condition (điều kiện tranh chấp)** giữa bước kiểm tra và bước ghi. Kết quả đọc “không có hàng” chỉ đúng tại thời điểm truy vấn quan sát dữ liệu. Nó không đặt chỗ cho giá trị đó và cũng không tự ngăn một giao dịch khác chèn cùng khóa sau thời điểm đọc.

### Vì sao khóa hàng không tìm thấy không tự giải quyết được?

Nếu truy vấn không trả về hàng, thông thường không có hàng hiện hữu nào để khóa bằng `SELECT ... FOR UPDATE`. Hai giao dịch có thể cùng nhận kết quả rỗng. Một số DBMS và isolation level có cơ chế khóa khoảng hoặc predicate để bảo vệ phạm vi chưa có hàng, nhưng hành vi phụ thuộc chỉ mục, điều kiện và cấu hình. Không nên dựa vào giả định chung rằng truy vấn tìm không thấy đã khóa được giá trị còn trống.

Với quy tắc “không được có hai hàng cùng khóa nghiệp vụ”, UNIQUE constraint/index là hàng rào toàn vẹn dữ liệu trực tiếp và rõ ràng nhất.

## 4. UNIQUE xử lý hai lần INSERT cạnh tranh như thế nào?

Khi có unique index, DBMS phải kiểm tra giá trị khóa mới với các khóa đã có, kể cả các thao tác ghi cạnh tranh chưa commit mà giao dịch khác chưa nhìn thấy trong snapshot đọc thông thường.

Với hai giao dịch cùng chèn `new@example.com`, một diễn biến phổ biến là:

1. `T1` chèn giá trị khóa nghiệp vụ vào unique index.
2. `T2` thử chèn cùng giá trị và phát hiện một giao dịch khác đang tạo khóa trùng chưa có kết quả cuối cùng.
3. `T2` phải chờ kết quả của `T1` hoặc được DBMS xử lý theo cơ chế tương ứng.
4. Nếu `T1` commit, `T2` nhận lỗi vi phạm tính duy nhất.
5. Nếu `T1` rollback, `T2` có thể tiếp tục và chèn thành công vì giá trị trùng chưa được commit.

Sơ đồ khái niệm:

```text
T1: INSERT key = K ─────────────── COMMIT
              │
              └── unique index ghi nhận khóa K

T2: INSERT key = K ── chờ kết quả T1 ── UNIQUE violation
                                         (nếu T1 commit)
```

Nếu giao dịch giữ khóa `K` rollback, kết quả của `T2` có thể là thành công thay vì vi phạm UNIQUE. Vì vậy, không nên mô tả rằng giao dịch đến sau luôn thất bại: kết quả phụ thuộc giao dịch đang cạnh tranh commit hay rollback.

Điểm cốt lõi là việc kiểm tra và bảo vệ tính duy nhất được thực hiện như một phần của thao tác ghi trong DBMS. Ứng dụng không cần tự tạo một khoảng thời gian “khóa giá trị chưa tồn tại” bằng logic kiểm tra trước.

## 5. Ví dụ hoàn chỉnh: đăng ký email

Định nghĩa bảng:

```sql
CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    CONSTRAINT uq_users_email UNIQUE (email)
);
```

Giao dịch đăng ký:

```sql
BEGIN;

INSERT INTO users (email, full_name)
VALUES ('an@example.com', 'An');

COMMIT;
```

Nếu email chưa được sử dụng, giao dịch có thể commit. Nếu một tài khoản khác đã có email đó hoặc một giao dịch cạnh tranh commit trước với cùng khóa, DBMS từ chối lần chèn vi phạm UNIQUE.

Trong ứng dụng, lỗi duy nhất thường được chuyển thành phản hồi nghiệp vụ như “Email đã được đăng ký”. Không nên coi mọi lỗi `INSERT` là lỗi trùng khóa; cần phân biệt vi phạm UNIQUE với lỗi kết nối, lỗi kiểu dữ liệu, vi phạm khóa ngoại, hết dung lượng hoặc các lỗi khác.

### Xử lý lỗi theo DBMS

Một số mã lỗi thường gặp:

| DBMS | Mã lỗi phổ biến cho vi phạm duy nhất |
|---|---|
| PostgreSQL | SQLSTATE `23505` |
| MySQL / InnoDB | Error `1062` |
| SQL Server | Error `2601` hoặc `2627` |

Ứng dụng nên dựa trên mã lỗi/loại lỗi có cấu trúc do driver cung cấp, không phân tích chuỗi thông báo lỗi để quyết định logic nghiệp vụ nếu có thể tránh.

Trong PostgreSQL, một câu lệnh vi phạm UNIQUE làm transaction hiện tại rơi vào trạng thái lỗi. Ứng dụng phải rollback transaction hoặc quay về savepoint trước khi tiếp tục các câu lệnh khác trong transaction đó. Một số DBMS có cách xử lý khác; hãy dùng đúng quy tắc transaction của hệ thống đang chạy.

## 6. Composite UNIQUE: khóa nghiệp vụ gồm nhiều cột

Không phải khóa nghiệp vụ nào cũng nằm trong một cột. Ví dụ, mã nhân viên có thể chỉ duy nhất bên trong từng công ty. Khi đó, `employee_code` có thể lặp ở hai công ty khác nhau, nhưng cặp `(company_id, employee_code)` phải duy nhất.

```sql
CREATE TABLE employees (
    id BIGINT PRIMARY KEY,
    company_id BIGINT NOT NULL,
    employee_code VARCHAR(40) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    CONSTRAINT uq_employee_company_code
        UNIQUE (company_id, employee_code)
);
```

Dữ liệu sau hợp lệ:

| company_id | employee_code | Ý nghĩa |
|---:|---|---|
| 10 | E001 | Nhân viên E001 của công ty 10 |
| 20 | E001 | Nhân viên E001 của công ty 20 |
| 10 | E002 | Nhân viên E002 của công ty 10 |

Nhưng thêm một hàng `(10, E001)` nữa sẽ vi phạm UNIQUE. Thứ tự cột trong composite index cũng ảnh hưởng đến cách DBMS sử dụng index cho truy vấn, dù tập cột của ràng buộc vẫn xác định cùng quy tắc duy nhất.

Một khóa nghiệp vụ gồm nhiều phần phải được định nghĩa đầy đủ. Nếu bỏ `company_id` khỏi constraint, mã nhân viên giống nhau giữa hai công ty sẽ bị từ chối dù nghiệp vụ cho phép.

## 7. NULL và UNIQUE

`NULL` biểu diễn giá trị chưa biết hoặc không áp dụng. Quy tắc so sánh `NULL` không giống một giá trị thông thường, vì vậy cách UNIQUE xử lý nhiều `NULL` phụ thuộc DBMS và tùy chọn của index/constraint.

- PostgreSQL mặc định cho phép nhiều hàng có `NULL` trong cột UNIQUE; phiên bản hỗ trợ `NULLS NOT DISTINCT` có thể yêu cầu các `NULL` được xem là trùng nhau.
- MySQL cho phép nhiều `NULL` trong unique index.
- SQL Server thường cho phép một giá trị `NULL` trong unique index một cột; với index nhiều cột, quy tắc áp dụng trên tổ hợp khóa và cần kiểm tra cụ thể.

Nếu email bắt buộc phải có và duy nhất, hãy khai báo cả hai điều kiện:

```sql
email VARCHAR(320) NOT NULL,
CONSTRAINT uq_users_email UNIQUE (email)
```

Chỉ có `UNIQUE(email)` chưa chắc đã ngăn nhiều hàng có email `NULL`. Cần quyết định rõ nghiệp vụ có cho phép giá trị thiếu hay không, rồi dùng `NOT NULL` hoặc quy tắc phù hợp.

## 8. Chuẩn hóa khóa nghiệp vụ trước khi so sánh

Hai chuỗi có thể khác nhau về hình thức nhưng được nghiệp vụ xem là cùng một khóa. Ví dụ:

```text
An@example.com
an@example.com
```

Hoặc mã khách hàng có thể chứa khoảng trắng ở đầu/cuối. Nếu hệ thống muốn coi các giá trị đó là một, phải định nghĩa quy tắc chuẩn hóa và bảo đảm UNIQUE được áp dụng trên cùng biểu diễn chuẩn.

Một cách thiết kế là lưu giá trị đã chuẩn hóa:

```text
email_input      = chuỗi người dùng nhập
email_normalized = giá trị đã trim và chuẩn hóa theo quy tắc ứng dụng
```

Sau đó đặt UNIQUE trên `email_normalized`. Với PostgreSQL, có thể dùng expression index nếu quy tắc phù hợp:

```sql
CREATE UNIQUE INDEX ux_users_email_lower
ON users (LOWER(email));
```

Collation (quy tắc so sánh chuỗi), Unicode normalization, cách xử lý dấu và chữ hoa/thường có thể khác nhau giữa DBMS. Đừng tự giả định `LOWER()` đã giải quyết mọi dạng tương đương của Unicode hoặc mọi quy tắc email. Hãy chọn một canonicalization rule có chủ đích và dùng thống nhất ở mọi đường ghi.

## 9. UNIQUE với soft delete và bản ghi đang hoạt động

Một hệ thống có thể cho phép tài khoản đã xóa mềm giải phóng email để tài khoản mới sử dụng lại. Khi đó, quy tắc không phải “email duy nhất trong toàn bộ lịch sử”, mà là “email duy nhất trong các tài khoản đang hoạt động”.

Trong PostgreSQL, có thể biểu diễn bằng partial unique index:

```sql
CREATE UNIQUE INDEX ux_users_active_email
ON users (email)
WHERE deleted_at IS NULL;
```

Index chỉ kiểm tra các hàng có `deleted_at IS NULL`. Khi tài khoản bị xóa mềm, hàng không còn tham gia index; một tài khoản hoạt động khác có thể sử dụng email đó.

Không phải DBMS nào cũng hỗ trợ partial index với cú pháp tương tự. Một số hệ thống có filtered index hoặc yêu cầu thiết kế cột tính toán/index riêng. Cần kiểm tra tính năng cụ thể.

Quy tắc này cũng có hệ quả nghiệp vụ: nếu khôi phục tài khoản cũ sau khi email đã được cấp cho tài khoản mới, thao tác khôi phục có thể vi phạm UNIQUE. Ứng dụng phải xử lý xung đột khi restore, không chỉ khi insert.

## 10. INSERT ... ON CONFLICT và UPSERT

Một số DBMS hỗ trợ thao tác kết hợp chèn và xử lý khi khóa đã tồn tại, thường gọi là **UPSERT**. UPSERT hữu ích khi nghiệp vụ muốn “tạo mới nếu chưa có, nếu đã có thì giữ nguyên hoặc cập nhật”. Nó vẫn dựa trên cơ chế duy nhất ở DBMS.

### PostgreSQL: ON CONFLICT

Không làm gì nếu email đã tồn tại:

```sql
INSERT INTO users (email, full_name)
VALUES ('an@example.com', 'An')
ON CONFLICT (email) DO NOTHING
RETURNING id;
```

Nếu không có hàng được trả về, có thể lần chèn đã không tạo hàng do xung đột. Ứng dụng có thể truy vấn bản ghi hiện có nếu nghiệp vụ cần lấy `id` của tài khoản đã tồn tại.

Hoặc cập nhật khi xung đột:

```sql
INSERT INTO user_preferences (user_id, theme)
VALUES (101, 'dark')
ON CONFLICT (user_id)
DO UPDATE SET theme = EXCLUDED.theme;
```

`EXCLUDED` đại diện cho giá trị định chèn nhưng bị xung đột. Cần cân nhắc kỹ `DO UPDATE`: cập nhật bản ghi hiện có có thể kích hoạt trigger, thay đổi `updated_at`, tăng version hoặc ghi đè dữ liệu do người dùng khác sửa. Nếu nghiệp vụ chỉ cần báo “đã tồn tại”, `DO NOTHING` thường diễn đạt đúng hơn.

### MySQL: ON DUPLICATE KEY UPDATE

MySQL có cú pháp:

```sql
INSERT INTO user_preferences (user_id, theme)
VALUES (101, 'dark')
ON DUPLICATE KEY UPDATE theme = 'dark';
```

Mệnh đề này được kích hoạt khi trùng một khóa chính hoặc unique key. Nếu bảng có nhiều unique key, cần chú ý xung đột xảy ra trên khóa nào và tác động của nhánh UPDATE.

### SQL Server

SQL Server có `MERGE`, nhưng không nên xem một câu `MERGE` đơn giản là bảo đảm mọi tình huống tranh chấp chèn đều an toàn nếu thiếu thiết kế khóa và ràng buộc thích hợp. Một lựa chọn rõ ràng là vẫn giữ UNIQUE constraint/index, thử `INSERT`, rồi xử lý lỗi duplicate key; với logic cần đọc rồi quyết định cập nhật, có thể cần transaction và locking/isolation phù hợp.

UPSERT không thay thế việc hiểu khóa nghiệp vụ. Phải xác định rõ khi trùng thì bỏ qua, trả bản ghi hiện có, cộng dồn, cập nhật hay báo lỗi.

## 11. UNIQUE constraint và tính idempotent

Một yêu cầu từ client có thể được gửi lại vì timeout, mất kết nối hoặc client không nhận được phản hồi dù server đã commit. Nếu lần gửi lại tạo một đối tượng nghiệp vụ mới, hệ thống có thể ghi nhận hai lần cùng một yêu cầu.

Một **idempotency key (khóa chống xử lý lặp)** là một khóa nghiệp vụ được client gửi kèm để nhận diện cùng một yêu cầu. DBMS có thể bảo vệ tính duy nhất của khóa đó:

```sql
CREATE TABLE payment_requests (
    id BIGINT PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL,
    CONSTRAINT uq_payment_idempotency_key UNIQUE (idempotency_key)
);
```

Khi cùng một yêu cầu được gửi lại, lần chèn thứ hai gặp unique conflict. Ứng dụng có thể tìm bản ghi đã xử lý và trả lại kết quả trước đó.

Không nên chỉ dựa vào unique conflict rồi trả kết quả cũ mà không xác minh nội dung yêu cầu. Nếu cùng một idempotency key được gửi với payload khác, ứng dụng nên so sánh `request_hash` hoặc dữ liệu tương đương và từ chối việc tái sử dụng key sai mục đích.

UNIQUE bảo vệ rằng một key chỉ xuất hiện một lần. Idempotency ở cấp nghiệp vụ còn cần định nghĩa trạng thái đang xử lý, đã thành công, thất bại có thể thử lại hay kết quả cuối cùng, cũng như cách xử lý side effect bên ngoài transaction.

## 12. UNIQUE có thể bị vi phạm khi UPDATE

Ràng buộc duy nhất không chỉ kiểm tra `INSERT`. Một lệnh `UPDATE` có thể thay đổi khóa nghiệp vụ thành giá trị đang được một hàng khác sử dụng:

```sql
UPDATE users
SET email = 'binh@example.com'
WHERE id = 101;
```

Nếu `binh@example.com` đã thuộc về hàng khác, DBMS từ chối cập nhật. Ứng dụng cần xử lý lỗi tương tự như khi chèn trùng.

Khi một giao dịch đổi nhiều khóa cùng lúc, thứ tự cập nhật có thể gây xung đột tạm thời hoặc vi phạm constraint tùy DBMS. Một số hệ thống hỗ trợ deferrable unique constraint để kiểm tra ở cuối transaction; tính năng và cú pháp phụ thuộc DBMS. Chỉ dùng khi nghiệp vụ thực sự cần hoán đổi khóa trong một transaction và hiểu rõ thời điểm kiểm tra.

## 13. Những điều UNIQUE không tự giải quyết

UNIQUE là cơ chế mạnh cho một quy tắc duy nhất cụ thể, nhưng không phải bộ giải quyết mọi loại tranh chấp.

- Nó không tự bảo đảm các điều kiện tổng hợp như “tổng số ghế đã đặt không vượt quá sức chứa” nếu điều kiện không được mô hình hóa thành một khóa duy nhất.
- Nó không thay thế khóa ngoại, `CHECK`, `NOT NULL` hoặc các ràng buộc khác.
- Nó không tự quyết định ứng dụng nên bỏ qua, cập nhật hay báo lỗi khi gặp duplicate key.
- Nó không bảo vệ những giá trị được chuẩn hóa không thống nhất giữa các luồng ghi.
- Nó không loại bỏ deadlock khi giao dịch cùng cập nhật nhiều unique key hoặc nhiều bảng theo thứ tự khác nhau.
- Nó không bảo đảm một thao tác ngoài database như gửi email hoặc gọi cổng thanh toán chỉ được thực hiện một lần.

Hãy chọn đúng constraint cho bất biến dữ liệu. Với điều kiện liên quan đến nhiều hàng hoặc nhiều bảng, có thể cần Serializable Isolation, khóa điều phối, thiết kế dữ liệu khác hoặc cơ chế transaction bổ sung.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `SELECT` không tìm thấy rồi `INSERT` là đủ để bảo đảm duy nhất. | Hai giao dịch có thể cùng đọc kết quả rỗng. UNIQUE constraint/index mới là hàng rào toàn vẹn cuối cùng. |
| Giao dịch đến sau luôn thất bại khi cùng chèn một khóa. | Nó có thể chờ; nếu giao dịch trước rollback, giao dịch sau có thể thành công. |
| Chỉ cần khóa chính là đủ. | Khóa nghiệp vụ như email hoặc mã đối tác cần UNIQUE riêng nếu nghiệp vụ yêu cầu. |
| UNIQUE luôn coi hai `NULL` là trùng nhau. | Quy tắc `NULL` khác nhau theo DBMS và tùy chọn. Dùng `NOT NULL` nếu giá trị bắt buộc. |
| UPSERT luôn có nghĩa là bỏ qua bản ghi trùng. | UPSERT có thể bỏ qua hoặc cập nhật; phải chọn hành vi đúng với nghiệp vụ. |
| UNIQUE trên email tự xử lý chữ hoa/thường và Unicode. | Cần xác định collation và quy tắc chuẩn hóa/canonicalization rõ ràng. |
| Có UNIQUE thì không cần xử lý lỗi ở ứng dụng. | Ứng dụng vẫn phải nhận diện duplicate key và chuyển thành phản hồi nghiệp vụ phù hợp. |

## 15. Tự kiểm tra

**Tình huống 1:** Hai giao dịch cùng chạy `SELECT` kiểm tra `employee_code = 'E100'` và đều không tìm thấy hàng. Sau đó cả hai cùng `INSERT`. Điều gì bảo vệ dữ liệu khỏi có hai nhân viên mang cùng mã?

**Đáp án:** UNIQUE constraint/index trên `employee_code` (hoặc trên tổ hợp cột xác định khóa nghiệp vụ) buộc DBMS điều phối hai lần ghi cạnh tranh. Một giao dịch có thể thành công; giao dịch còn lại nhận duplicate-key error nếu giao dịch thắng commit.

**Tình huống 2:** `T1` đang chèn khóa `K` nhưng chưa commit. `T2` cũng chèn `K`. Nếu `T1` rollback, `T2` có nhất thiết phải thất bại không?

**Đáp án:** Không. Sau khi DBMS xác định `T1` rollback và khóa `K` không được giữ lại, `T2` có thể tiếp tục và chèn thành công.

**Tình huống 3:** Một nhân viên có mã `E100` ở công ty 10 và một nhân viên khác cũng có mã `E100` ở công ty 20. Nếu mã chỉ cần duy nhất trong từng công ty, nên đặt UNIQUE trên cột nào?

**Đáp án:** Đặt composite UNIQUE trên `(company_id, employee_code)`. UNIQUE chỉ trên `employee_code` sẽ áp dụng phạm vi toàn bảng và từ chối trường hợp hợp lệ giữa hai công ty.

**Tình huống 4:** Bảng tài khoản cho phép nhiều hàng có email `NULL` theo DBMS đang dùng. Điều đó có vi phạm `UNIQUE(email)` không?

**Đáp án:** Không nhất thiết. Cách xử lý nhiều `NULL` phụ thuộc DBMS. Nếu email bắt buộc, khai báo `NOT NULL` cùng UNIQUE.

**Tình huống 5:** Một API nhận `idempotency_key` giống nhau hai lần nhưng payload lần thứ hai khác payload đầu. Có nên chỉ trả lại kết quả của lần đầu không?

**Đáp án:** Cần xác minh payload hoặc request hash. Tái sử dụng cùng key cho một yêu cầu khác phải bị phát hiện và xử lý theo quy tắc API, tránh nhầm hai nghiệp vụ khác nhau thành một yêu cầu lặp.

Khi bảo vệ một khóa nghiệp vụ, hãy xác định chính xác cột hoặc tổ hợp cột tạo nên danh tính, chuẩn hóa giá trị theo một quy tắc thống nhất, đặt UNIQUE ở database và xử lý duplicate-key như một kết quả cạnh tranh bình thường. Bước kiểm tra trước khi chèn có thể cải thiện trải nghiệm người dùng, nhưng chỉ ràng buộc duy nhất ở DBMS mới bảo vệ dữ liệu khi nhiều giao dịch cùng ghi.
