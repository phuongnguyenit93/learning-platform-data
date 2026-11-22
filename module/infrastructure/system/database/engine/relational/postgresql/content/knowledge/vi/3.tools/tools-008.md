# Đọc SQLSTATE và thông báo lỗi từ máy chủ

Khi chạy SQL trên PostgreSQL, ứng dụng không chỉ nhận kết quả thành công hoặc thất bại. Nếu xảy ra lỗi, máy chủ trả về **mã SQLSTATE**, **mức độ thông báo**, **thông điệp lỗi** và trong nhiều trường hợp còn có **DETAIL**, **HINT**, vị trí câu SQL, tên bảng hoặc ràng buộc. Biết cách đọc đúng các trường này giúp tìm nguyên nhân nhanh hơn, xây dựng xử lý lỗi đáng tin cậy trong Java và tránh viết logic phụ thuộc vào câu chữ có thể thay đổi.

Ví dụ, nếu chèn hai tài khoản cùng email vào cột có `UNIQUE`, PostgreSQL thường trả **SQLSTATE `23505`** với tên điều kiện `unique_violation`. Nội dung `duplicate key value violates unique constraint ...` có thể rất hữu ích để giải thích cho con người, nhưng **`23505` mới là mã ổn định nên dùng để phân loại lỗi trong chương trình**. Nếu câu SQL tiếp theo gặp `25P02`, vấn đề không nhất thiết nằm ở câu mới: transaction đã ở trạng thái thất bại do một lỗi xảy ra trước đó.

Bài học tập trung vào **công cụ đọc và khai thác lỗi PostgreSQL**: định dạng mã SQLSTATE, các trường phản hồi từ máy chủ, thao tác trong `psql`, tìm SQLSTATE qua JDBC/pgJDBC, đọc lỗi trong PL/pgSQL, phân biệt lỗi gốc với hậu quả và xây dựng quy trình chẩn đoán có khả năng lặp lại.

> Ví dụ được viết cho PostgreSQL hiện đại và ứng dụng Java dùng JDBC. Thao tác tạo bảng và phát sinh lỗi có chủ đích chỉ nên chạy trong **database thử nghiệm**. Thông điệp cụ thể thay đổi theo phiên bản, ngôn ngữ, tên đối tượng và ngữ cảnh, vì vậy không nên sao chép nguyên văn message ví dụ thành điều kiện kiểm tra trong production.

## 1. PostgreSQL thông báo lỗi gồm những gì?

Máy chủ PostgreSQL sử dụng các phản hồi có cấu trúc theo giao thức kết nối. Với lỗi và những thông báo không phải lỗi, client có thể nhận một tập **trường chẩn đoán**. Không phải lần báo lỗi nào cũng cung cấp tất cả trường.

| Trường khái niệm | Ví dụ | Dùng để làm gì? |
|---|---|---|
| **Severity** | `ERROR`, `FATAL`, `WARNING`, `NOTICE` | Mức độ của thông báo, giúp phân biệt lỗi thực thi, lỗi phiên kết nối hoặc thông báo thông tin. |
| **SQLSTATE** | `23505` | Mã gồm **5 ký tự**, giúp nhận diện loại tình trạng mà không phải phân tích chuỗi message. |
| **Message** | `duplicate key value violates unique constraint "uq_accounts_email"` | Mô tả chính, dễ đọc cho con người. |
| **Detail** | `Key (email)=(an@example.com) already exists.` | Dữ liệu bổ sung giải thích nguyên nhân. |
| **Hint** | `...` | Gợi ý sửa lỗi, khi máy chủ có cung cấp. |
| **Position** | `42` | Vị trí ký tự trong câu truy vấn gây lỗi; hữu ích khi sai cú pháp hoặc tên cột. |
| **Where/Context** | `PL/pgSQL function ... line ...` | Ngữ cảnh bên trong function, trigger hoặc SQL lồng nhau. |
| **Schema/Table/Column/Constraint** | `public` / `accounts` / `email` / `uq_accounts_email` | Định danh đối tượng liên quan, nếu được cung cấp. |
| **File/Line/Routine nội bộ** | Tên file và hàm mã nguồn PostgreSQL | Dành nhiều hơn cho chẩn đoán chuyên sâu, nhất là lỗi bên trong máy chủ. |

Ví dụ output mặc định của `psql` trong một lần chèn trùng khóa có thể giống:

```text
ERROR:  duplicate key value violates unique constraint "uq_accounts_email"
DETAIL:  Key (email)=(an@example.com) already exists.
```

Ở chế độ mặc định, người dùng có thể **chưa thấy SQLSTATE**, mặc dù máy chủ đã gửi mã đó. Ta có thể yêu cầu `psql` in thêm, hoặc truy xuất trực tiếp trường này bằng API JDBC.

### Sự khác biệt quan trọng giữa mã và message

**Thông điệp** cung cấp ngữ cảnh để đọc hiểu. **SQLSTATE** cung cấp định danh ổn định để máy tính ra quyết định. Một ứng dụng không nên kiểm tra:

```java
// Không nên: dựa vào chuỗi thông báo có thể thay đổi.
if (ex.getMessage().contains("duplicate key value")) {
    // ...
}
```

Thay vào đó, sử dụng:

```java
// Cách phân loại phù hợp hơn khi exception là SQLException.
if ("23505".equals(ex.getSQLState())) {
    // Vi phạm unique; xác định đúng ràng buộc trước khi quyết định xử lý.
}
```

Ngay cả `23505` cũng chưa đủ để suy ra **đó là email trùng**, vì một bảng có thể có nhiều unique constraint. Khi nghiệp vụ cần phân biệt cụ thể, đọc thêm **tên constraint**, tên bảng và câu lệnh đang thực thi.

## 2. SQLSTATE có cấu trúc như thế nào?

Một SQLSTATE gồm **5 ký tự chữ số/chữ cái**. Trong cách phân loại thường dùng, hai ký tự đầu xác định **class** (nhóm điều kiện), ba ký tự còn lại xác định **subclass** hoặc tình trạng cụ thể trong nhóm đó.

```text
SQLSTATE = 23505
           ├─ "23"  → class: vi phạm ràng buộc toàn vẹn
           └─ "505" → subclass: unique_violation

Biểu diễn đơn giản:
       23        505
      class    subclass
```

Ví dụ `23505` thuộc lớp `23` (*integrity constraint violation*), tình trạng cụ thể `unique_violation`. Với `42P01`, hai ký tự đầu là `42`, ba ký tự cuối là `P01`; **không phải mọi mã SQLSTATE đều chỉ gồm chữ số**.

Để đọc chính xác, có thể chia:

```text
23505  →  23 | 505  → integrity constraint violation / unique_violation
23503  →  23 | 503  → integrity constraint violation / foreign_key_violation
40P01  →  40 | P01  → transaction rollback / deadlock_detected
42P01  →  42 | P01  → syntax/access rule / undefined_table
P0001  →  P0 | 001  → PL/pgSQL / raise_exception
```

Mã `00000` thể hiện **successful completion** trong hệ thống mã SQLSTATE. Đối với lỗi SQL thông thường, client sẽ nhận mã lỗi khác `00000`. Một số thông báo mức `NOTICE` hoặc `WARNING` có thể đi qua kênh thông báo riêng thay vì phát exception như lỗi `ERROR`.

### Vì sao mã theo class hữu ích?

Cùng một nhóm có thể cho biết hướng điều tra:

| Class | Nhóm lỗi hoặc tình trạng | Hướng nghĩ ban đầu |
|---|---|---|
| `00` | Successful completion | Thao tác thành công theo mã trạng thái. |
| `01` | Warning | Cảnh báo; không nhất thiết hủy câu lệnh. |
| `02` | No data | Không có dữ liệu trong những ngữ cảnh nhất định. |
| `08` | Connection exception | Kết nối hoặc luồng giao tiếp tới máy chủ. |
| `22` | Data exception | Giá trị/biểu diễn dữ liệu không hợp lệ. |
| `23` | Integrity constraint violation | Vi phạm `NOT NULL`, `UNIQUE`, khóa ngoại, `CHECK`. |
| `25` | Invalid transaction state | Transaction đang không ở trạng thái cho phép thao tác. |
| `28` | Invalid authorization specification | Xác thực và quyền đăng nhập. |
| `3D` | Invalid catalog name | Database đích không tồn tại. |
| `40` | Transaction rollback | Cần xử lý lỗi transaction, thường liên quan đồng thời. |
| `42` | Syntax error or access rule violation | Sai cú pháp, tên bảng/cột, quyền hoặc các quy tắc truy cập. |
| `55` | Object not in prerequisite state | Đối tượng/khóa chưa ở trạng thái phù hợp. |
| `57` | Operator intervention | Hủy truy vấn hoặc hành động vận hành khác. |
| `P0` | PL/pgSQL error | Tình huống do PL/pgSQL phát sinh. |
| `XX` | Internal error | Lỗi bên trong hoặc tình trạng cần điều tra đặc biệt. |

**Lưu ý:** Hai ký tự đầu giúp định hướng, không thay thế mã đầy đủ. Ví dụ `23505` và `23503` cùng class `23` nhưng cần quyết định nghiệp vụ khác nhau. Với nhóm `40`, cũng không nên retry mọi tình huống một cách vô hạn.

## 3. Các mã SQLSTATE thường gặp trong PostgreSQL

Đây là một tập mã hữu ích khi đọc log, dùng `psql` hoặc xử lý ngoại lệ trong Java:

| SQLSTATE | Tên điều kiện PostgreSQL | Tình huống phổ biến |
|---|---|---|
| `23505` | `unique_violation` | Thêm/sửa giá trị trùng unique hoặc primary key. |
| `23503` | `foreign_key_violation` | Ghi tham chiếu tới bản ghi cha không tồn tại hoặc xóa bản ghi đang được tham chiếu. |
| `23502` | `not_null_violation` | Ghi `NULL` vào cột `NOT NULL`. |
| `23514` | `check_violation` | Giá trị không đáp ứng điều kiện `CHECK`. |
| `22P02` | `invalid_text_representation` | Chuỗi không chuyển được thành `integer`, `uuid`... |
| `22003` | `numeric_value_out_of_range` | Giá trị số vượt phạm vi kiểu dữ liệu. |
| `22001` | `string_data_right_truncation` | Chuỗi vượt độ dài cột trong tình huống bị từ chối. |
| `22012` | `division_by_zero` | Chia cho 0 trong phép tính. |
| `42601` | `syntax_error` | Câu lệnh SQL sai cú pháp. |
| `42P01` | `undefined_table` | Không tìm thấy relation được tham chiếu. |
| `42703` | `undefined_column` | Không có cột được chỉ định. |
| `42501` | `insufficient_privilege` | Tài khoản thiếu quyền cần thiết. |
| `40001` | `serialization_failure` | Giao dịch không thể hoàn thành do xung đột theo ngữ nghĩa mức cô lập. |
| `40P01` | `deadlock_detected` | PostgreSQL phát hiện chu trình chờ khóa. |
| `55P03` | `lock_not_available` | Không lấy được khóa theo yêu cầu, ví dụ với `NOWAIT`. |
| `57014` | `query_canceled` | Truy vấn bị hủy do yêu cầu người dùng hoặc timeout phù hợp. |
| `25P02` | `in_failed_sql_transaction` | Transaction đã lỗi, các lệnh sau bị từ chối tới khi rollback. |
| `08006` | `connection_failure` | Lỗi kết nối; có thể đến từ máy chủ hoặc driver. |
| `28P01` | `invalid_password` | Xác thực bằng mật khẩu thất bại. |
| `3D000` | `invalid_catalog_name` | Database được yêu cầu không tồn tại. |
| `P0001` | `raise_exception` | Exception do PL/pgSQL `RAISE EXCEPTION` mặc định phát ra. |

Danh sách này không phải toàn bộ tập mã PostgreSQL. Cần ưu tiên **SQLSTATE thực tế được trả về** cho trường hợp cụ thể thay vì đoán mã chỉ từ dạng câu lệnh.

### Ba nhóm cần đặc biệt chú ý khi viết ứng dụng

**Lỗi dữ liệu/ràng buộc:** `22...` và `23...` thường cần sửa input, áp dụng quy tắc trùng khóa hoặc báo lỗi nghiệp vụ. Retry nguyên một request không sửa input thường không giải quyết được.

**Lỗi transaction/đồng thời:** `40001`, `40P01`, `55P03` có thể liên quan cạnh tranh. Một số lỗi phù hợp với chính sách retry có giới hạn, nhưng phải retry **đúng đơn vị transaction** và bảo đảm an toàn nghiệp vụ.

**Lỗi kết nối hoặc hủy:** `08...`, `57014` có thể khiến ứng dụng chưa biết một thao tác ghi đã commit hay chưa nếu kết nối bị mất trong thời điểm nhạy cảm. Cần kiểm tra kết quả theo khóa nghiệp vụ/idempotency thay vì thực hiện lại mù quáng.

## 4. Tạo ví dụ lỗi có chủ đích trong PostgreSQL

Các ví dụ dưới đây dành cho một database **lab riêng**.

```sql
CREATE TABLE demo_accounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
    CONSTRAINT uq_demo_accounts_email UNIQUE (email),
    CONSTRAINT chk_demo_accounts_balance CHECK (balance >= 0)
);

INSERT INTO demo_accounts (email, balance)
VALUES ('an@example.com', 100.00);

-- Lỗi do email đã tồn tại: SQLSTATE 23505.
INSERT INTO demo_accounts (email, balance)
VALUES ('an@example.com', 50.00);
```

Lệnh đầu tạo bảng với một số ràng buộc; lệnh `INSERT` đầu thành công, lệnh cuối cố ý gây **unique violation**.

Ví dụ output với các trường cơ bản:

```text
ERROR:  duplicate key value violates unique constraint "uq_demo_accounts_email"
DETAIL:  Key (email)=(an@example.com) already exists.
```

Ở đây:

- **ERROR** là severity.
- **SQLSTATE `23505`** xác định lỗi unique, dù chưa được in trong chế độ output này.
- **uq_demo_accounts_email** là tên unique constraint bị vi phạm.
- **DETAIL** nêu khóa và giá trị cụ thể gây trùng.

Không nên log `DETAIL` một cách không kiểm soát: giá trị khóa có thể chứa email, token, định danh tài khoản hoặc dữ liệu nhạy cảm.

### Thử các lỗi khác

```sql
-- 23502: not_null_violation.
INSERT INTO demo_accounts (email, balance)
VALUES (NULL, 25.00);

-- 23514: check_violation.
INSERT INTO demo_accounts (email, balance)
VALUES ('binh@example.com', -1.00);

-- 22P02: invalid_text_representation.
SELECT 'khong-phai-so'::INTEGER;

-- 22012: division_by_zero.
SELECT 10 / 0;

-- 42P01: undefined_table.
SELECT * FROM demo_table_does_not_exist;
```

Khi chạy từng câu trong `psql` ở chế độ autocommit thông thường, chúng có thể phát lỗi riêng để ta quan sát. **Nếu đặt tất cả vào cùng một `BEGIN ... COMMIT`**, câu đầu lỗi làm transaction chuyển sang trạng thái thất bại; những câu sau thường chỉ trả `25P02` cho đến khi `ROLLBACK`. Đó là nội dung quan trọng ở phần sau.

## 5. Hiển thị SQLSTATE trong psql bằng VERBOSITY

`psql` là client dòng lệnh phổ biến của PostgreSQL. Nó hỗ trợ các **meta-command** bắt đầu bằng dấu gạch chéo ngược, dùng để điều khiển cách hiển thị lỗi.

### 5.1. Chế độ mặc định

Trong một phiên `psql` tương tác:

```text
\set VERBOSITY default
```

Khi tạo lỗi `23505`, `psql` thường hiển thị mức `ERROR`, thông điệp chính, và `DETAIL` nếu server gửi. Chế độ mặc định ưu tiên khả năng đọc cho con người.

### 5.2. Chế độ verbose

```text
\set VERBOSITY verbose
```

Sau đó chạy:

```sql
INSERT INTO demo_accounts (email, balance)
VALUES ('an@example.com', 50.00);
```

Output có thể chứa:

```text
ERROR:  23505: duplicate key value violates unique constraint "uq_demo_accounts_email"
DETAIL:  Key (email)=(an@example.com) already exists.
SCHEMA NAME:  public
TABLE NAME:  demo_accounts
CONSTRAINT NAME:  uq_demo_accounts_email
LOCATION:  ..., ...:...
```

Đoạn này là ví dụ minh họa định dạng; các dòng metadata xuất hiện tùy phiên bản và lỗi cụ thể. **Điểm khác biệt quan trọng** là `23505` được hiển thị, cùng những trường bổ sung như vị trí trong mã nguồn PostgreSQL hoặc tên đối tượng liên quan khi có.

Chế độ verbose đặc biệt hữu ích khi:

- Cần phân biệt chính xác `23505` với `23503` hoặc `23514`.
- Cần xác định tên constraint bị lỗi.
- Đang chẩn đoán lỗi trong trigger, function, extension hoặc truy vấn phức tạp.
- Cần gửi báo cáo sự cố có mã trạng thái chính xác.

### 5.3. Chế độ terse

```text
\set VERBOSITY terse
```

`terse` rút gọn các thông tin bổ trợ để log giao diện ít rối hơn. Nó có ích khi đang cần một thông báo ngắn, nhưng không phải lựa chọn phù hợp nhất nếu đang tìm metadata và mã lỗi chi tiết.

### 5.4. Chế độ sqlstate

```text
\set VERBOSITY sqlstate
```

Chế độ này tập trung vào **mã SQLSTATE**, thay vì nội dung văn bản chi tiết. Phù hợp khi cần quan sát loại lỗi một cách ngắn gọn, hoặc đang đối chiếu hành vi giữa các môi trường có ngôn ngữ hiển thị khác nhau.

### 5.5. Xem lại lỗi gần nhất bằng \errverbose

Trong `psql` tương tác:

```text
\errverbose
```

Meta-command này in lại thông tin của **lỗi máy chủ gần nhất** với mức chi tiết cao, kể cả khi chế độ `VERBOSITY` thông thường đang đặt ở dạng ngắn.

Ví dụ thao tác theo thứ tự:

```text
\set VERBOSITY terse
```

```sql
INSERT INTO demo_accounts(email) VALUES ('an@example.com');
```

```text
\errverbose
```

Nhờ đó có thể làm việc với output ngắn hằng ngày và chỉ yêu cầu chi tiết khi xảy ra tình huống cần chẩn đoán.

**Đừng nhầm** `\errverbose` với câu SQL chạy trên server: đó là lệnh riêng của chương trình `psql`, không thể gửi nguyên văn từ JDBC `Statement.execute(...)`.

## 6. Biến SQLSTATE và ERROR trong psql script

`psql` có các biến đặc biệt giúp theo dõi kết quả lệnh SQL đã chạy, đáng chú ý là `SQLSTATE` và `ERROR`.

Khi thao tác trong `psql`, có thể thử:

```text
\set VERBOSITY default
```

```sql
SELECT 1;
```

```text
\echo :SQLSTATE
```

Giá trị thường là `00000` sau câu SQL thành công. Với câu lỗi:

```sql
SELECT 'abc'::integer;
```

```text
\echo :SQLSTATE
```

Khi đó `SQLSTATE` được cập nhật theo lỗi SQL gần nhất, thường là `22P02` đối với chuỗi không thể chuyển thành số nguyên.

### Chú ý giới hạn ngữ cảnh

- `SQLSTATE` là **biến phía `psql`**, không phải một system variable mà ứng dụng SQL có thể truy vấn bằng `SELECT SQLSTATE` tùy ý.
- Nó theo dõi kết quả lệnh SQL được client xử lý; đừng dùng giá trị lưu lại này như lịch sử mọi lỗi đã xảy ra.
- Meta-command khác, truy vấn kế tiếp và cách chạy script có thể ảnh hưởng thời điểm quan sát. Nếu cần mã lỗi trong automation, hãy lấy ngay sau câu SQL liên quan và ghi cùng ngữ cảnh.
- Với chương trình Java, lấy `SQLException.getSQLState()` thay vì dùng cơ chế biến `psql`.

### Chạy script và dừng khi gặp lỗi

Khi chạy file SQL trong pipeline, có thể dùng:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 \
  -p 5432 \
  -U app_user \
  -d appdb \
  -f migration.sql
```

Các tham số:

- `-X`: không đọc file cấu hình startup của `psql` để hành vi script bớt phụ thuộc môi trường người chạy.
- `-v ON_ERROR_STOP=1`: dừng xử lý script khi có lỗi SQL thay vì tiếp tục qua những câu kế tiếp.
- `-f migration.sql`: thực thi lệnh SQL từ file.

Trong trường hợp script đang được xử lý và `ON_ERROR_STOP` làm dừng vì lỗi, `psql` dùng exit status **3** cho tình huống đó. Các lỗi khác như sự cố phía client hoặc lỗi kết nối có exit status khác theo ngữ cảnh. **Đừng hiểu exit code = 3 là “SQLSTATE 00003”.** Đây là hai hệ thống mã độc lập: exit code thuộc chương trình `psql` của hệ điều hành, còn SQLSTATE thuộc chẩn đoán lệnh PostgreSQL.

Tài khoản và host ở lệnh trên chỉ là ví dụ. Không đưa mật khẩu trực tiếp vào tham số lệnh hoặc log CI; dùng cơ chế xác thực/secret phù hợp.

## 7. Phân biệt lỗi gốc với lỗi 25P02 trong transaction

Đây là một trong những tình huống gây hiểu nhầm nhiều nhất:

```sql
BEGIN;

-- Lệnh thứ nhất gặp lỗi 23505.
INSERT INTO demo_accounts(email)
VALUES ('an@example.com');

-- Lệnh thứ hai về bản chất hợp lệ,
-- nhưng transaction hiện đã bị đánh dấu thất bại.
SELECT COUNT(*) FROM demo_accounts;
```

Trong PostgreSQL, sau một **ERROR** xảy ra bên trong transaction block, transaction thường chuyển sang trạng thái **aborted/failed**. Lệnh `SELECT COUNT(*)` tiếp theo không được thực thi theo ý nghĩa bình thường; PostgreSQL báo:

```text
ERROR:  current transaction is aborted, commands ignored until end of transaction block
```

Mã của lỗi này là **`25P02` — `in_failed_sql_transaction`**.

Sơ đồ:

```text
BEGIN
  │
  ▼
INSERT trùng email
  │
  ├── lỗi gốc: 23505
  │
  ▼
Transaction chuyển sang FAILED
  │
  ▼
SELECT hợp lệ vẫn bị từ chối
  │
  └── lỗi hệ quả: 25P02
  │
  ▼
ROLLBACK để thoát khỏi trạng thái lỗi
```

### Cách xử lý đúng

Trong `psql` tương tác:

```sql
ROLLBACK;

-- Sau rollback, một transaction mới hoặc
-- lệnh ở chế độ autocommit có thể thực thi bình thường.
SELECT COUNT(*) FROM demo_accounts;
```

**Không sửa câu `SELECT COUNT(*)` chỉ vì nó nhận `25P02`.** Hãy tìm **lỗi đầu tiên trong transaction**, đó mới thường là nguyên nhân gốc. Một exception xuất hiện muộn trong Java/Hibernate có thể chỉ là hậu quả của một câu SQL lỗi trước đã bị bắt rồi bỏ qua.

Nếu gặp `25P02` trong ứng dụng:

1. Xem log đầu transaction, tìm SQLSTATE xuất hiện **trước** `25P02`.
2. Đảm bảo transaction được `ROLLBACK` theo cơ chế của JDBC/Spring.
3. Không trả connection đang có transaction lỗi về pool mà chưa giải quyết trạng thái.
4. Chỉ retry toàn đơn vị nghiệp vụ khi lỗi gốc có thể retry và trạng thái ghi được kiểm soát.

### SAVEPOINT giúp phục hồi một nhánh mà không bỏ toàn transaction

Trong một số nghiệp vụ, bạn muốn thử một thao tác có thể thất bại dự kiến, nhưng vẫn tiếp tục transaction với những công việc khác. Có thể dùng `SAVEPOINT`:

```sql
BEGIN;

SAVEPOINT before_optional_insert;

-- Cố ý gây 23505.
INSERT INTO demo_accounts(email)
VALUES ('an@example.com');

-- Ở psql tương tác, lệnh tiếp theo được phép
-- đưa transaction trở lại trạng thái tại savepoint.
ROLLBACK TO SAVEPOINT before_optional_insert;

SELECT COUNT(*) FROM demo_accounts;

RELEASE SAVEPOINT before_optional_insert;
COMMIT;
```

Nếu chạy ví dụ bằng `psql -v ON_ERROR_STOP=1`, client sẽ **dừng tại lỗi** và không tự đi tiếp đến `ROLLBACK TO SAVEPOINT`; lúc đó cần cơ chế xử lý của ứng dụng hoặc script chủ động tiếp tục theo thiết kế.

SAVEPOINT không phải cách che giấu mọi lỗi. Nếu lỗi có nghĩa toàn bộ nghiệp vụ phải hủy, **rollback toàn transaction** rõ ràng hơn. Nếu dùng nhiều savepoint ở mức ứng dụng, cần cân nhắc chi phí và độ phức tạp.

## 8. Đọc lỗi từ Java JDBC bằng SQLException

Trong ứng dụng Java, PostgreSQL JDBC Driver (*pgJDBC*) đưa lỗi SQL qua `SQLException` và các lớp chuyên biệt. API quan trọng nhất để lấy mã lỗi là **`SQLException.getSQLState()`**.

Ví dụ:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class AccountWriter {
    public static void addEmail(Connection connection, String email)
            throws SQLException {
        String sql = "INSERT INTO demo_accounts(email) VALUES (?)";

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, email);
            statement.executeUpdate();
        } catch (SQLException exception) {
            String sqlState = exception.getSQLState();

            if ("23505".equals(sqlState)) {
                // Đây là lỗi unique_violation.
                // Cần xác định đúng constraint trước khi ánh xạ
                // thành lỗi email đã tồn tại trong nghiệp vụ.
            }

            throw exception;
        }
    }
}
```

Trong ví dụ, exception được **ném lại** để tầng quản lý transaction/caller xử lý. Chỉ bắt lỗi rồi tiếp tục không rollback có thể khiến connection còn ở trạng thái transaction thất bại và sinh `25P02`.

### Đừng nhầm SQLSTATE với mã lỗi số của hệ quản trị khác

`SQLException` còn có phương thức `getErrorCode()`. Trong nhiều tài liệu về MySQL, người ta dựa vào mã lỗi số như `1062` để nhận diện trùng khóa. **PostgreSQL phân loại lỗi chính bằng mã SQLSTATE 5 ký tự**, không nên mong đợi `getErrorCode()` trả một mã số PostgreSQL tương đương với các lỗi của MySQL.

Một mẫu điều kiện nên viết:

```java
if ("23505".equals(exception.getSQLState())) {
    // PostgreSQL unique_violation
}
```

Không viết:

```java
// Không đúng nếu đang dùng pgJDBC và giả định mã MySQL.
if (exception.getErrorCode() == 1062) {
    // ...
}
```

### Trường hợp mã không đến trực tiếp từ server

Không phải mọi `SQLException` đều do PostgreSQL máy chủ phát ra một **ErrorResponse** hoàn chỉnh. Lỗi mở connection, lỗi client, pool timeout, lỗi driver hoặc socket bị cắt có thể được tạo ở phía client và có lượng metadata khác nhau.

Do đó:

- `getSQLState()` có thể `null` trong một số trường hợp không có mã được cung cấp.
- `SQLSTATE` thuộc nhóm `08` có thể phản ánh sự cố kết nối mà không có tên bảng/constraint nào.
- Không khẳng định một exception có `getMessage()` là có đầy đủ `DETAIL`, `HINT` và tên constraint.
- Nếu cần truy cập trường cụ thể, xác định exception có thực sự là loại máy chủ của pgJDBC hay không.

## 9. Lấy trường chẩn đoán có cấu trúc trong pgJDBC

Khi ứng dụng dùng pgJDBC, lỗi máy chủ thường được biểu diễn bằng `org.postgresql.util.PSQLException`. Lớp này có `getServerErrorMessage()`, trả về đối tượng `ServerErrorMessage` khi driver nhận được cấu trúc lỗi từ server.

Ví dụ cách đọc có kiểm soát:

```java
import org.postgresql.util.PSQLException;
import org.postgresql.util.ServerErrorMessage;

import java.sql.SQLException;

public final class PostgreSqlErrorInfo {
    public static void inspect(SQLException exception) {
        String state = exception.getSQLState();
        System.out.println("SQLSTATE = " + state);

        if (exception instanceof PSQLException pgException) {
            ServerErrorMessage server =
                    pgException.getServerErrorMessage();

            if (server != null) {
                System.out.println("Severity = " + server.getSeverity());
                System.out.println("Constraint = " + server.getConstraint());
                System.out.println("Schema = " + server.getSchema());
                System.out.println("Table = " + server.getTable());
                System.out.println("Column = " + server.getColumn());
                // Hạn chế in getDetail(), getMessage() trong log thật
                // vì chúng có thể chứa dữ liệu người dùng.
            }
        }
    }
}
```

Đây là ví dụ Java có phụ thuộc **pgJDBC** và cú pháp `instanceof` pattern matching của những phiên bản Java hỗ trợ. Với Java cũ hơn, dùng `instanceof` thường rồi ép kiểu.

Trong hệ thống production, không nên `System.out.println` trực tiếp metadata lỗi như ví dụ: đưa vào logger có cấu trúc, áp dụng chính sách bảo mật và loại dữ liệu có thể định danh người dùng.

### Các getter thông dụng

| API pgJDBC | Dữ liệu thường lấy được |
|---|---|
| `exception.getSQLState()` | SQLSTATE, khi exception có mã. |
| `server.getSeverity()` | Mức độ thông báo từ máy chủ. |
| `server.getMessage()` | Message chính do PostgreSQL cung cấp. |
| `server.getDetail()` | Detail, nếu có. |
| `server.getHint()` | Hint, nếu có. |
| `server.getPosition()` | Vị trí lỗi trong câu SQL, nếu máy chủ cung cấp. |
| `server.getWhere()` | Ngữ cảnh lỗi trong function hoặc stack thực thi. |
| `server.getSchema()` | Schema liên quan, nếu có. |
| `server.getTable()` | Bảng liên quan, nếu có. |
| `server.getColumn()` | Cột liên quan, nếu có. |
| `server.getConstraint()` | Tên constraint liên quan, nếu có. |

**Không phải lỗi nào cũng có tên constraint hoặc tên bảng.** Một lỗi `syntax_error` có thể chủ yếu trả message/position, còn lỗi `unique_violation` thường có constraint. Thậm chí khi trường có mặt, ứng dụng phải đối chiếu đúng schema/table/constraint của câu SQL để không ánh xạ sai nghiệp vụ.

### Phân biệt vi phạm unique theo constraint

Giả sử bảng tài khoản có hai unique constraint: `uq_demo_accounts_email` và `uq_demo_accounts_external_id`. Cùng `23505` có thể do một trong hai.

Logic tốt hơn:

```java
if ("23505".equals(exception.getSQLState())
        && exception instanceof PSQLException pgException) {
    ServerErrorMessage server =
            pgException.getServerErrorMessage();

    if (server != null
            && "uq_demo_accounts_email".equals(server.getConstraint())) {
        // Chỉ trường hợp unique email, không phải mọi lỗi 23505.
    }
}
```

Khi thiết kế API, nên đặt **tên constraint ổn định** trong migration nếu tầng ứng dụng phụ thuộc vào tên ấy. Đồng thời cần xem xét tác động khi đổi schema/rename constraint.

## 10. SQLSTATE và chiến lược xử lý lỗi ở tầng ứng dụng

Không phải mã lỗi nào cũng nên được chuyển thành cùng một HTTP status hoặc cùng một chính sách retry. Cần tách các loại phản ứng.

| Mã / nhóm | Hướng xử lý phổ biến | Điều cần tránh |
|---|---|---|
| `23505` | Xác định unique constraint; trả xung đột nghiệp vụ hoặc xử lý thao tác idempotent. | Tự động giả định mọi lỗi unique đều là email trùng. |
| `23503` | Trả thông báo tham chiếu không hợp lệ hoặc xung đột xóa dữ liệu. | Cố xóa dữ liệu cha bằng cách tắt foreign key tùy tiện. |
| `23502`, `23514` | Xác định input vi phạm hoặc lỗi lập trình nghiệp vụ; sửa dữ liệu hoặc validation. | Retry cùng input vô hạn. |
| `22P02` | Kiểm tra chuyển kiểu dữ liệu và validate input. | Nối chuỗi SQL trực tiếp; chỉ xử lý bằng cắt message. |
| `40001` | Thường retry **toàn transaction** với giới hạn, backoff và idempotency. | Chỉ retry một statement trong transaction đã thất bại. |
| `40P01` | Rollback transaction, cân nhắc retry có giới hạn và thứ tự khóa nhất quán. | Retry vô hạn hoặc tăng concurrency khi deadlock đã cao. |
| `55P03` | Xem chính sách NOWAIT/lock timeout; có thể chờ, báo bận hoặc retry phù hợp. | Coi đây là lỗi “không có hàng dữ liệu”. |
| `57014` | Xác định ai hủy/trạng thái timeout; cân nhắc giảm tải hoặc tối ưu truy vấn. | Retry ngay một truy vấn chậm mà không thay đổi điều kiện. |
| `25P02` | Tìm **lỗi đầu tiên** trong transaction, rollback hoặc xử lý savepoint đúng cách. | Chỉ chữa lệnh cuối báo 25P02. |
| `08...` | Xem kết nối, trạng thái commit chưa rõ, cơ chế retry có idempotency. | Giả định mọi lần disconnect đều đồng nghĩa transaction chưa commit. |
| `42P01`, `42703` | Kiểm tra migration, schema, `search_path`, tên bảng/cột. | Chuyển thành lỗi dữ liệu đầu vào cho người dùng mà không điều tra triển khai. |

**Bảng chỉ là định hướng**, không phải luật ánh xạ HTTP hoặc retry áp dụng cho mọi dự án. Ví dụ `23505` có thể trả HTTP 409 cho thao tác tạo tài nguyên nếu đúng nghĩa xung đột, nhưng một service nội bộ khác có thể xem bản ghi đã tồn tại là kết quả idempotent bình thường.

### Retry transaction đúng cách

Với `40001` hoặc `40P01`, PostgreSQL thường yêu cầu transaction hiện tại không tiếp tục như thể chưa có lỗi. Một vòng retry đúng về ý nghĩa phải:

1. Kết thúc transaction thất bại bằng rollback hoặc để transaction manager xử lý.
2. Tạo một transaction mới.
3. **Thực hiện lại toàn bộ logic** cần quyết định từ dữ liệu giao dịch: đọc, kiểm tra, tính toán và ghi.
4. Có giới hạn retry và backoff, không tạo vòng lặp vô hạn.
5. Đảm bảo tác dụng phụ ngoài database không bị lặp trái quy tắc; dùng idempotency/outbox khi phù hợp.

Đặc biệt trong Java/Spring, retry **bên trong cùng một transaction đã abort** thường chỉ tạo thêm `25P02`. Nếu dùng `@Transactional` và một thư viện retry, phải thiết kế rõ **thứ tự interceptor và ranh giới transaction**.

## 11. SQLSTATE trong PL/pgSQL: đọc và phát lại lỗi

PostgreSQL hỗ trợ xử lý lỗi bên trong khối `PL/pgSQL` bằng `EXCEPTION`, cùng các biến chẩn đoán như `SQLSTATE`, `SQLERRM` và câu lệnh `GET STACKED DIAGNOSTICS`.

Đây là cơ chế **phía server**, khác với cách `psql` hiển thị ErrorResponse hoặc `SQLException` phía Java.

### 11.1. Dùng EXCEPTION WHEN theo tên điều kiện

Một khối `DO` minh họa xử lý lỗi unique:

```sql
DO $$
DECLARE
    v_was_duplicate BOOLEAN := FALSE;
BEGIN
    BEGIN
        INSERT INTO demo_accounts(email)
        VALUES ('an@example.com');

    EXCEPTION WHEN unique_violation THEN
        v_was_duplicate := TRUE;
        RAISE NOTICE 'Da gap unique_violation: SQLSTATE=%', SQLSTATE;
    END;

    IF v_was_duplicate THEN
        RAISE NOTICE 'Khong tao them tai khoan trung email';
    END IF;
END;
$$;
```

Trong handler `EXCEPTION`, biến đặc biệt `SQLSTATE` cho biết mã lỗi đang được xử lý; `SQLERRM` chứa thông điệp lỗi. Khi handler xử lý xong và không phát lại, khối ngoài có thể tiếp tục.

**Lưu ý:** Khối `BEGIN ... EXCEPTION ... END` của PL/pgSQL có ngữ nghĩa rollback các thay đổi SQL của khối thất bại (triển khai qua cơ chế subtransaction). Đây không giống một câu lệnh `CONTINUE HANDLER` của MySQL; không nên bê nguyên cách hiểu xử lý lỗi từ một hệ quản trị khác.

### 11.2. Bắt đúng SQLSTATE

Ngoài tên điều kiện `unique_violation`, có thể viết:

```sql
DO $$
BEGIN
    BEGIN
        INSERT INTO demo_accounts(email)
        VALUES ('an@example.com');

    EXCEPTION WHEN SQLSTATE '23505' THEN
        RAISE NOTICE 'Bat loi PostgreSQL SQLSTATE 23505';
    END;
END;
$$;
```

Trong một thiết kế tốt, chỉ hấp thụ lỗi nếu **thao tác thay thế thực sự hợp lệ**. Nếu không biết constraint nào lỗi hoặc logic nghiệp vụ cần báo thất bại, hãy phát lại thay vì tiếp tục với dữ liệu chưa được ghi.

### 11.3. GET STACKED DIAGNOSTICS

Để thu thập nhiều trường lỗi cùng lúc:

```sql
DO $$
DECLARE
    v_state   TEXT;
    v_message TEXT;
    v_detail  TEXT;
    v_hint    TEXT;
    v_context TEXT;
BEGIN
    BEGIN
        INSERT INTO demo_accounts(email)
        VALUES ('an@example.com');

    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state   = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_detail  = PG_EXCEPTION_DETAIL,
            v_hint    = PG_EXCEPTION_HINT,
            v_context = PG_EXCEPTION_CONTEXT;

        RAISE NOTICE 'SQLSTATE trong handler: %', v_state;

        -- Khi không có chính sách hấp thụ lỗi hợp lệ,
        -- phát lại để caller thấy lỗi gốc.
        RAISE;
    END;
END;
$$;
```

Các giá trị:

- `RETURNED_SQLSTATE`: mã điều kiện, ví dụ `23505`.
- `MESSAGE_TEXT`: thông điệp chính.
- `PG_EXCEPTION_DETAIL`: chi tiết bổ sung nếu có.
- `PG_EXCEPTION_HINT`: gợi ý bổ sung nếu có.
- `PG_EXCEPTION_CONTEXT`: ngữ cảnh nơi lỗi được phát sinh.

Lệnh `RAISE;` không có tham số **bên trong exception handler** phát lại lỗi đang được xử lý. Cách này phù hợp khi muốn ghi nhận metadata rồi vẫn để caller quản lý thất bại. Với ứng dụng thực tế, tránh in toàn bộ `v_message` hoặc `v_detail` nếu chúng chứa thông tin riêng tư.

### 11.4. RAISE EXCEPTION với ERRCODE có chủ đích

Bạn có thể chủ động tạo lỗi nghiệp vụ kèm mã:

```sql
CREATE OR REPLACE FUNCTION require_positive_amount(p_amount NUMERIC)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'So tien phai lon hon 0',
            HINT = 'Kiem tra gia tri amount truoc khi goi ham';
    END IF;
END;
$$;

SELECT require_positive_amount(0);
```

`22023` là mã `invalid_parameter_value`, thích hợp để diễn đạt input không hợp lệ trong ví dụ. Nếu chỉ dùng `RAISE EXCEPTION '...'` mà không chỉ định `ERRCODE`, PL/pgSQL thường phát mã `P0001` (`raise_exception`).

**Không nên lấy mã tùy ý trùng với một mã PostgreSQL đã mang nghĩa khác** nếu bạn muốn khách hàng JDBC phân loại nhất quán. Với lỗi nghiệp vụ đặc thù, hãy có quy ước mã và thông tin bổ sung rõ, đồng thời không gây hiểu nhầm với lỗi dữ liệu/transaction có sẵn.

### 11.5. Không biến EXCEPTION thành nơi nuốt mọi lỗi

Ví dụ sau có rủi ro:

```sql
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Co loi nhung tiep tuc';
```

Đây chỉ là **mảnh code trong một khối PL/pgSQL**, không phải câu SQL độc lập. Nếu áp dụng rộng, nó có thể che giấu lỗi ràng buộc, sai lược đồ và sai logic, khiến caller tưởng thao tác thành công dù dữ liệu không được ghi.

Chỉ bắt lỗi cần xử lý với quy tắc rõ. Khi phải dừng nghiệp vụ, **`RAISE;`** giúp giữ nguyên nguồn lỗi cho caller.

## 12. NOTICE, WARNING và ERROR khác nhau thế nào?

PostgreSQL có những mức severity cho thông báo từ server, chẳng hạn `DEBUG`, `LOG`, `INFO`, `NOTICE`, `WARNING`, `ERROR`, `FATAL` và `PANIC`. Cần phân biệt **severity** với **SQLSTATE**:

| Severity | Ý nghĩa thực tế thường gặp |
|---|---|
| `NOTICE` | Thông báo bổ sung, ví dụ chương trình PL/pgSQL dùng `RAISE NOTICE`. |
| `WARNING` | Cảnh báo có thể cần chú ý nhưng không nhất thiết làm câu lệnh thất bại. |
| `ERROR` | Lỗi câu lệnh hoặc thao tác đang thực thi; có thể làm transaction bị abort. |
| `FATAL` | Lỗi đủ nghiêm trọng để chấm dứt phiên kết nối tương ứng. |
| `PANIC` | Tình trạng nghiêm trọng ở mức máy chủ, thường dẫn tới kết thúc tiến trình và recovery. |

**Severity trả lời “mức nghiêm trọng ra sao?”, SQLSTATE trả lời “đây là loại tình trạng nào?”** Hai trường có mục đích khác nhau.

### Ví dụ NOTICE

```sql
DO $$
BEGIN
    RAISE NOTICE 'Dang kiem tra du lieu demo';
END;
$$;
```

Client có thể nhận một thông báo `NOTICE` mà khối `DO` vẫn hoàn thành. Trong JDBC, thông báo không gây exception có thể xuất hiện qua cơ chế **`SQLWarning`** hoặc API tương ứng, tùy driver.

### client_min_messages

Biến PostgreSQL `client_min_messages` điều khiển ngưỡng nhiều loại thông báo được gửi tới client:

```sql
SHOW client_min_messages;

-- Chỉ trong phiên lab; có thể thay đổi ngưỡng hiển thị NOTICE.
SET client_min_messages = warning;

DO $$
BEGIN
    RAISE NOTICE 'Thong bao nay co the khong hien thi voi client';
END;
$$;

RESET client_min_messages;
```

Không nên dùng thay đổi ngưỡng client để **che lỗi ERROR** của một thao tác. Tương tự, `log_min_messages` và `log_error_verbosity` liên quan tới **server log**, khác với cách `psql` hiển thị ErrorResponse.

### log_error_verbosity

Người vận hành PostgreSQL có thể cấu hình mức chi tiết log lỗi phía server, ví dụ `terse`, `default` hoặc `verbose` qua `log_error_verbosity`. Chế độ verbose của server log có thể bao gồm SQLSTATE và vị trí mã nguồn phục vụ phân tích sâu.

Đây là **cấu hình server**, không phải cùng một biến với meta-command `\set VERBOSITY verbose` trong `psql`. Thay đổi logging server cần cân nhắc chi phí log và thông tin nhạy cảm, đồng thời tuân thủ quyền/phương thức triển khai cấu hình PostgreSQL.

## 13. Thông tin Position, Context và Hint giúp sửa SQL

Không phải lỗi nào cũng liên quan tới ràng buộc dữ liệu. Ví dụ câu SQL có tên cột sai:

```sql
SELECT unknown_col
FROM demo_accounts;
```

PostgreSQL có thể trả `42703` (`undefined_column`), message và vị trí SQL. Trong `psql`, một số lỗi hiển thị dấu `^` chỉ khu vực có vấn đề. Khi driver nhận `Position`, IDE hoặc hệ thống hiển thị lỗi có thể dùng vị trí này để đánh dấu câu SQL liên quan.

Ví dụ khác:

```sql
SELEC id FROM demo_accounts;
```

PostgreSQL trả `42601` (`syntax_error`), thường kèm vị trí phát hiện cú pháp không hợp lệ.

### HINT không phải lúc nào cũng có

Một số lỗi có gợi ý, ví dụ khi PostgreSQL nghi người dùng đánh sai tên cột hoặc cần ép kiểu dữ liệu phù hợp. Trường `HINT` hữu ích để sửa câu SQL, nhưng không phải lời bảo đảm máy chủ luôn đưa ra cách khắc phục hoàn chỉnh.

### Context trong PL/pgSQL

Khi lỗi xuất hiện bên trong stored function/trigger, phần `CONTEXT` hoặc `Where` có thể cho biết tên function, số dòng PL/pgSQL và câu lệnh đang thực thi.

Điều này đặc biệt hữu ích khi ứng dụng chỉ gọi:

```sql
SELECT process_order(123);
```

nhưng lỗi thực nằm ở một lệnh `INSERT` hoặc `UPDATE` sâu trong function. Với những tình huống đó, **SQLSTATE và context** thường giải thích nguyên nhân tốt hơn một dòng error message đơn lẻ.

## 14. Một bảng dữ liệu có nhiều lỗi khác nhau

Thêm quan hệ khóa ngoại để minh họa vì sao cần phân biệt các lỗi cùng nhóm:

```sql
CREATE TABLE demo_orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL
        REFERENCES demo_accounts(id),
    quantity INTEGER NOT NULL
        CHECK (quantity > 0)
);
```

Các lệnh minh họa:

```sql
-- 23503: account_id tham chiếu bản ghi không tồn tại.
INSERT INTO demo_orders(account_id, quantity)
VALUES (999999999, 1);

-- 23502: account_id bị NULL.
INSERT INTO demo_orders(account_id, quantity)
VALUES (NULL, 1);

-- 23514: quantity không thỏa CHECK (> 0).
-- Giả định account_id = 1 có tồn tại trong lab.
INSERT INTO demo_orders(account_id, quantity)
VALUES (1, 0);
```

Nhận xét:

1. Cả ba đều thuộc **class `23`**.
2. `23503`, `23502` và `23514` mang ý nghĩa khác nhau nên không nên ánh xạ giống hệt nhau nếu ứng dụng cần thông báo chính xác.
3. Nếu cùng một lệnh vi phạm nhiều constraint, **không có lời hứa server sẽ báo tất cả cùng lúc**. Bạn thường nhận lỗi đầu tiên mà đường xử lý phát hiện.
4. Chi tiết lỗi có thể chứa tên constraint và giá trị; cần hạn chế đưa nguyên văn vào log công khai.

Để thử `23514` chắc chắn, hãy kiểm tra account ID thực tế trong môi trường lab:

```sql
SELECT id, email FROM demo_accounts ORDER BY id;
```

Sau đó dùng một `id` hợp lệ. Không nên dùng một ID giả định khi database test đã được chạy lại nhiều lần và identity sequence không còn giá trị ban đầu.

## 15. Đọc lỗi trong Spring và các lớp bao bọc SQLException

Ứng dụng Spring JDBC hoặc Spring Data thường chuyển một số `SQLException` thành các lớp exception ở tầng framework, chẳng hạn:

- `DuplicateKeyException` cho tình huống phù hợp với lỗi trùng unique.
- `DataIntegrityViolationException` cho một nhóm lỗi toàn vẹn dữ liệu.
- Những exception liên quan lock, resource hoặc thao tác DB theo cách dịch lỗi của framework/driver.

Những lớp này có thể giúp code nghiệp vụ ít phụ thuộc chi tiết driver, nhưng không nên mặc định mọi lỗi PostgreSQL có một ánh xạ **duy nhất và bất biến** qua mọi phiên bản Spring.

Nếu cần chính xác SQLSTATE:

1. Xem exception gốc hoặc cause chain nếu framework đã bọc lỗi.
2. Truy xuất `SQLException.getSQLState()` khi tìm được `SQLException`.
3. Nếu dùng pgJDBC và cần constraint, lấy `ServerErrorMessage` khi có.
4. Xác định transaction manager đã rollback hay chưa.
5. Tránh tiếp tục dùng cùng transaction sau một SQL error không được xử lý.

### Ví dụ tìm SQLException trong cause chain

```java
import java.sql.SQLException;

public final class SqlErrorClassifier {
    public static String findSqlState(Throwable failure) {
        Throwable current = failure;

        while (current != null) {
            if (current instanceof SQLException sqlException) {
                return sqlException.getSQLState();
            }
            current = current.getCause();
        }

        return null;
    }
}
```

Đây là bản minh họa đơn giản. Trong hệ thống thực tế, `SQLException` còn có **`getNextException()`** để truy cập lỗi bổ sung theo chuỗi JDBC, không phải lúc nào cũng nằm trong `getCause()`. Với batch hoặc nhiều statement, nên kiểm tra cả chuỗi exception và ngữ cảnh statement để không bỏ sót mã quan trọng.

Không tự động chuyển mọi exception JDBC thành HTTP 500; ngược lại cũng không trả nguyên message server ra API vì có thể lộ dữ liệu và cấu trúc database. Nên dùng mã lỗi nghiệp vụ của ứng dụng và giữ SQLSTATE để phục vụ giám sát/điều tra phía server.

## 16. Ghi log chẩn đoán mà không làm lộ dữ liệu nhạy cảm

SQLSTATE rất hữu ích để tạo **log có cấu trúc** và metric theo nhóm lỗi. Một bản ghi sự cố phù hợp có thể gồm:

```text
timestamp: 2026-11-14T10:20:00Z
service: order-api
operation: create_account
database_role: app_writer
sqlstate: 23505
error_class: 23
constraint: uq_demo_accounts_email
transaction_id: <id noi bo cua ung dung>
request_id: <id truy vet>
retry_count: 0
outcome: failed
```

Đây là **mẫu log minh họa**, không phải sự kiện từ một hệ thống thật. Thông tin request/transaction ID nên được tạo theo chính sách quan sát và bảo mật của ứng dụng.

### Nên ghi gì?

- **SQLSTATE đầy đủ** thay vì chỉ class hoặc message.
- Thao tác nghiệp vụ và tên thành phần đang chạy.
- Tên schema/table/constraint khi cần và khi không gây lộ thông tin.
- Loại kết quả: thất bại vĩnh viễn, rollback, đã retry, hay trạng thái commit chưa rõ.
- Mã yêu cầu để ghép với log phía ứng dụng và server.

### Không nên ghi gì mặc định?

- Chuỗi SQL kèm dữ liệu đầu vào nhạy cảm chưa được lọc.
- Mật khẩu, token, connection string có secret.
- Toàn bộ `DETAIL` khi chứa email, địa chỉ hoặc nội dung khách hàng.
- Thông điệp lỗi PostgreSQL nguyên văn trả thẳng cho client công khai.

Một message hữu ích với DBA chưa chắc phù hợp làm thông điệp gửi người dùng cuối. Chẳng hạn API có thể trả “Email đã được sử dụng” dựa trên mã `23505` **và đúng unique constraint**, nhưng không cần tiết lộ cấu trúc bảng hay tên constraint.

## 17. Quy trình chẩn đoán một lỗi PostgreSQL từ đầu đến cuối

Khi một truy vấn hoặc API thất bại, có thể theo trình tự:

```text
Lỗi xuất hiện tại ứng dụng / psql
               │
               ▼
Lấy SQLSTATE, severity và operation
               │
               ▼
Đọc message, detail, hint, position, context
               │
               ▼
Lỗi hiện tại có phải 25P02?
           ┌───┴────┐
         Có         Không
          │           │
          ▼           ▼
Tìm lỗi đầu tiên   Phân loại mã (22,23,40,42,08...)
trong transaction        │
          │              ▼
          └────────► Xác định nguyên nhân / constraint
                         │
                         ▼
                 Kiểm tra transaction state
                         │
                         ▼
               Rollback / xử lý savepoint nếu cần
                         │
                         ▼
         Quyết định sửa input, sửa schema, retry hoặc báo lỗi
                         │
                         ▼
             Ghi log an toàn và xác nhận kết quả
```

### Bước 1 — Bắt đúng lỗi gốc

Trong `psql`, dùng `\errverbose` sau lỗi để xem mã. Trong Java, đọc `SQLException.getSQLState()` hoặc exception gốc nếu framework đã bọc.

Nếu chỉ thấy `25P02`, hãy tìm câu lệnh đầu tiên tạo lỗi trong transaction trước khi phân tích SQL hiện tại.

### Bước 2 — Tách lỗi lập trình với dữ liệu đầu vào

`42P01` có thể là thiếu bảng do migration chưa chạy hoặc `search_path` không đúng. `23514` có thể do input không hợp lệ hoặc logic validation thiếu. Cần kiểm tra schema, phiên bản ứng dụng, SQL và tập dữ liệu trước khi quyết định trả lỗi cho người dùng.

### Bước 3 — Xem những trường chẩn đoán có thể tin cậy hơn message

SQLSTATE phù hợp để phân nhánh, tên constraint giúp nhận diện quy tắc bị vi phạm, `Position` giúp sửa cú pháp, `Context` giúp định vị PL/pgSQL. Message vẫn rất cần để người vận hành hiểu nhưng không nên là khóa logic ổn định.

### Bước 4 — Xác định trạng thái transaction và kết quả ghi

Nếu câu lệnh lỗi trong transaction, cần rollback đúng cách. Nếu kết nối bị mất gần lúc commit, không mặc định thao tác chưa được ghi; phải dùng định danh nghiệp vụ hoặc bảng trạng thái giao dịch để xác minh.

### Bước 5 — Chỉ retry lỗi được thiết kế để retry

Với `40001`/`40P01`, chính sách retry có thể giúp, nhưng phải bao bọc **toàn transaction**, giới hạn số lần và có backoff. Với `23502` hoặc `22P02`, retry cùng dữ liệu thường chỉ lặp lại lỗi.

### Bước 6 — Đối chiếu với log server khi cần

Nếu client không có đủ context, người vận hành có thể xem log PostgreSQL tương ứng timestamp, process/session và request. Nên cấu hình logging có kiểm soát, tránh tăng verbosity không giới hạn trên môi trường nhiều dữ liệu nhạy cảm.

## 18. Những hiểu nhầm thường gặp

**“Message lỗi là mã ổn định cho chương trình.”** Không. Nội dung có thể thay đổi hoặc được bản địa hóa; SQLSTATE là cơ chế phân loại phù hợp hơn.

**“SQLSTATE luôn là 5 chữ số.”** Không. `42P01`, `40P01`, `22P02` và `P0001` đều chứa chữ cái.

**“Mọi lỗi 23xxx đều là duplicate key.”** Không. Class `23` gồm nhiều tình huống khác nhau, bao gồm foreign key, not null và check violation.

**“Một lỗi 23505 luôn nghĩa là email trùng.”** Không. Cần biết unique constraint nào bị vi phạm.

**“psql mặc định lúc nào cũng hiển thị SQLSTATE.”** Không. Đổi `VERBOSITY` hoặc dùng `\errverbose` để xem thông tin chi tiết.

**“Một lỗi 25P02 chứng minh câu SELECT vừa chạy bị sai.”** Không. Thường nó cho biết transaction đã thất bại do lỗi **trước đó**.

**“Có thể tiếp tục cùng transaction sau lỗi bằng cách bắt exception trong Java.”** Không. Nếu transaction đã abort, phải rollback hoặc xử lý savepoint được thiết kế phù hợp.

**“Bắt và nuốt mọi EXCEPTION trong PL/pgSQL làm hệ thống ổn định.”** Không. Nó có thể che mất lỗi dữ liệu, tạo kết quả thành công giả và khiến người gọi khó khắc phục.

**“SQLException.getErrorCode() dùng để nhận diện lỗi PostgreSQL như MySQL 1062.”** Không. Với PostgreSQL, sử dụng SQLSTATE 5 ký tự.

**“Mọi lỗi 40001 đều retry một statement là xong.”** Không. Với serialization failure, cần retry **toàn bộ transaction**, bao gồm phần đọc và quyết định nghiệp vụ.

**“Lỗi mất kết nối chắc chắn nghĩa là không commit.”** Không. Có trường hợp commit đã hoàn tất nhưng client không nhận phản hồi.

**“NOTICE luôn là SQLException.”** Không. Những thông báo không gây lỗi có thể qua kênh thông báo/cảnh báo của client.

**“getServerErrorMessage luôn khác null.”** Không. Một số lỗi xảy ra phía driver/kết nối có thể không có ErrorResponse từ server.

**“In toàn bộ DETAIL vào log là vô hại.”** Không. DETAIL có thể chứa dữ liệu nhạy cảm của hàng bị từ chối.

## 19. Bài tập thực hành

### Bài 1 — Phân tích một thông báo unique_violation

Cho output:

```text
ERROR:  duplicate key value violates unique constraint "uq_demo_accounts_email"
DETAIL:  Key (email)=(an@example.com) already exists.
```

Hãy giải thích severity, SQLSTATE mong đợi, tên constraint và lý do không nên đưa toàn bộ DETAIL vào response công khai.

### Bài 2 — Đổi mức chi tiết trong psql

Trong `psql`, chạy lại lỗi trùng email với `\set VERBOSITY default`, `verbose`, `terse` và `sqlstate`. Dùng `\errverbose` sau một lần lỗi, ghi nhận khác biệt giữa mã SQLSTATE và thông điệp. Cho biết meta-command này có thể được gửi thẳng qua JDBC như SQL hay không.

### Bài 3 — Xác định lỗi gốc thay vì 25P02

Một transaction thực thi:

```sql
BEGIN;
INSERT INTO demo_accounts(email) VALUES ('an@example.com');
SELECT COUNT(*) FROM demo_accounts;
UPDATE demo_accounts SET balance = 10 WHERE email = 'an@example.com';
```

Nếu `INSERT` đầu bị `23505`, dự đoán lỗi của các lệnh tiếp theo. Đưa ra câu lệnh SQL để phục hồi trạng thái transaction và giải thích vì sao chỉ thay câu `UPDATE` sẽ không sửa được vấn đề.

### Bài 4 — Phân biệt SQLSTATE theo nghiệp vụ

Hãy gắn mỗi tình huống với mã thích hợp: ghi `NULL` vào cột `NOT NULL`, sửa khóa ngoại tới bản ghi không tồn tại, `CHECK` từ chối số âm, ép chuỗi `abc` sang integer, và gọi bảng chưa được tạo.

*Gợi ý:* `23502`, `23503`, `23514`, `22P02`, `42P01`.

### Bài 5 — Thiết kế xử lý lỗi JDBC

Viết phương thức Java nhận `SQLException`, trả về enum gồm `DUPLICATE`, `INVALID_INPUT`, `RETRYABLE_TRANSACTION` và `OTHER` dựa trên SQLSTATE. Giải thích vì sao cần biết tên constraint để biến `DUPLICATE` thành thông điệp nghiệp vụ cụ thể.

### Bài 6 — Đề xuất retry an toàn

Ứng dụng chuyển điểm thưởng gặp `40001` trong một transaction gồm đọc số dư, kiểm tra hạn mức và cập nhật hai tài khoản. Hãy mô tả ranh giới rollback/retry, số lần thử tối đa, idempotency và cách bảo đảm không gửi hai thông báo ngoài database.

### Bài 7 — Phân tích PL/pgSQL

Một function có `EXCEPTION WHEN unique_violation` rồi `RAISE NOTICE` và trả về thành công. Hãy giải thích khi nào hành vi này hợp lệ, khi nào cần `RAISE;` để chuyển lỗi cho caller. Mở rộng function để đọc `RETURNED_SQLSTATE` và `PG_EXCEPTION_CONTEXT`.

### Bài 8 — Xây quy trình giám sát

Thiết kế cấu trúc log có `timestamp`, `service`, `operation`, `sqlstate`, `constraint`, `request_id` và `outcome`, nhưng không lộ thông tin nhạy cảm. Nêu ít nhất hai loại metric hữu ích: số lỗi `23505` theo thao tác và số lần `40P01` theo đơn vị thời gian, đồng thời lưu ý việc tăng đột biến có thể do thay đổi workload.

## Kết luận

**SQLSTATE là chìa khóa để đọc và xử lý lỗi PostgreSQL một cách nhất quán.** Mã 5 ký tự cho biết loại tình trạng, trong khi **severity, message, DETAIL, HINT, Position, Context và tên đối tượng** giúp xác định nguyên nhân cụ thể. Tại `psql`, các meta-command `\set VERBOSITY verbose`, `\set VERBOSITY sqlstate` và `\errverbose` giúp nhìn thấy thông tin mà output mặc định có thể lược bớt; trong Java, `SQLException.getSQLState()` và `ServerErrorMessage` của pgJDBC cung cấp các trường để phân loại có cấu trúc.

Khi điều tra sự cố, hãy **tìm lỗi đầu tiên**, nhất là trước `25P02`, kiểm tra trạng thái transaction và chọn phản ứng đúng: sửa input, sửa schema, rollback hoặc retry toàn transaction khi phù hợp. Tránh rẽ nhánh theo câu chữ message và hạn chế ghi log chi tiết có thể lộ dữ liệu. Đọc đúng SQLSTATE không chỉ giúp gỡ lỗi nhanh hơn mà còn là nền tảng cho **API đáng tin cậy, vận hành có thể quan sát và giao dịch PostgreSQL được xử lý an toàn**.
