# Thiết lập múi giờ, mã hóa và chế độ tự động xác nhận giao dịch

Một môi trường thực hành SQL đáng tin cậy cần nhiều hơn một kết nối đến cơ sở dữ liệu. Trước khi tạo bảng, nhập dữ liệu và thử các câu lệnh thay đổi dữ liệu, ta nên biết hệ quản trị đang **hiểu thời gian**, **đọc/ghi ký tự** và **xác nhận giao dịch** như thế nào. Ba thiết lập này có thể khiến hai người chạy cùng một câu SQL nhưng thấy thời điểm khác nhau, chữ tiếng Việt bị lỗi, hoặc dữ liệu được lưu vĩnh viễn dù vừa thử thao tác.

Bài học hướng dẫn cách hiểu, kiểm tra và thiết lập ba thành phần đó trong một **môi trường thực hành Database SQL**. Các ví dụ thao tác chính dùng **PostgreSQL với công cụ `psql`**; phần cuối đối chiếu MySQL và SQLite để bạn không nhầm cú pháp hoặc cơ chế giữa các hệ quản trị.

## 1. Ba nhóm cấu hình đang kiểm soát điều gì?

| Nhóm | Câu hỏi phải trả lời | Tác động dễ quan sát |
|---|---|---|
| **Múi giờ (time zone)** | Giá trị ngày giờ được diễn giải và hiển thị theo khu vực nào? | Một thời điểm hiển thị `09:00 +07` ở Việt Nam nhưng `02:00 +00` ở UTC |
| **Mã hóa (character encoding)** | Chuỗi văn bản đi từ file, ứng dụng, kết nối đến database dưới dạng byte nào? | `Nguyễn` hiển thị đúng hoặc thành ký tự lỗi |
| **Tự động xác nhận giao dịch (autocommit)** | Sau mỗi câu lệnh thay đổi dữ liệu, kết quả có tự được `COMMIT` hay cần xác nhận thủ công? | `ROLLBACK` còn có thể hoàn tác, hoặc thao tác đã được xác nhận trước đó |

Các nhóm cấu hình có **phạm vi khác nhau**:

```text
Máy / file SQL / trình soạn thảo
        │  ký tự trong file, múi giờ hệ điều hành
        ▼
Ứng dụng / driver / công cụ SQL
        │  client encoding, autocommit, kết nối
        ▼
Phiên kết nối (database session)
        │  time zone của phiên, thông số phiên
        ▼
Cơ sở dữ liệu
           encoding khi tạo DB, collation, lưu trữ dữ liệu
```

Thay đổi cài đặt của **một phiên kết nối** thường không tự thay đổi mọi phiên khác, cũng không đồng nghĩa đổi cấu hình cho toàn bộ máy chủ. Khi dùng công cụ quản trị có nhiều tab, mỗi tab có thể dùng một kết nối riêng. Vì vậy, hãy **kiểm tra ngay trên kết nối đang chạy bài tập**.

## 2. Múi giờ: phân biệt thời điểm và giờ hiển thị

### 2.1. Ba khái niệm cần tách bạch

1. **Thời điểm (instant)**: một thời khắc xác định trên trục thời gian; có thể biểu diễn bằng UTC.
2. **Giờ địa phương (local date-time)**: ngày và giờ trên đồng hồ ở một địa phương, ví dụ `15/07/2026 09:00` tại TP.HCM.
3. **Múi giờ (time zone)**: quy tắc chuyển giữa thời điểm và giờ địa phương. Tên khu vực IANA, chẳng hạn `Asia/Ho_Chi_Minh`, thể hiện quy tắc của khu vực; độ lệch `+07:00` chỉ mô tả mức lệch UTC tại một thời điểm.

Trong ví dụ ngày 15/07/2026:

```text
2026-07-15 02:00:00+00  (UTC)
                │ cùng một thời điểm
                ▼
2026-07-15 09:00:00+07  (Asia/Ho_Chi_Minh)
```

Không nên đồng nhất **múi giờ của máy chủ**, **múi giờ của ứng dụng**, **múi giờ của phiên SQL** và **múi giờ mong muốn của người đọc báo cáo**. Chúng có thể được cấu hình riêng.

Với hệ thống hoạt động trên nhiều khu vực, việc lưu một thời điểm có đủ thông tin để xác định trên trục thời gian và chuyển sang múi giờ người dùng khi hiển thị thường giúp tránh nhầm lẫn. Tuy nhiên, dữ liệu như “cửa hàng mở cửa lúc 08:00 mỗi ngày” lại là *giờ theo lịch địa phương*, không nhất thiết là một thời điểm UTC cố định.

### 2.2. PostgreSQL: kiểm tra và đổi múi giờ của phiên

Trong `psql` hoặc SQL editor kết nối đến PostgreSQL:

```sql
-- Kiểm tra cài đặt hiện tại của kết nối.
SHOW TIME ZONE;

-- Đặt múi giờ Việt Nam cho phiên hiện tại.
SET TIME ZONE 'Asia/Ho_Chi_Minh';

-- Xác nhận lại.
SHOW TIME ZONE;

-- Xem thời gian theo phiên kết nối hiện tại.
SELECT CURRENT_TIMESTAMP AS current_time_in_session;
```

Sau `SET TIME ZONE`, PostgreSQL dùng múi giờ đó khi **hiển thị và diễn giải những biểu thức có phụ thuộc múi giờ**. Câu lệnh không chuyển đổi hàng loạt các giá trị đã lưu và cũng không tự đổi múi giờ của những người dùng đang kết nối khác.

Có thể chọn UTC cho bài tập:

```sql
SET TIME ZONE 'UTC';
SHOW TIME ZONE;
```

Muốn hoàn nguyên về cấu hình mặc định áp dụng cho phiên, dùng:

```sql
RESET TIME ZONE;
```

`SET` tác động đến kết nối hiện tại; khi ngắt và kết nối lại, cài đặt sẽ được nạp từ cấu hình mặc định của database, role hoặc server. Nếu thật sự cần mặc định riêng cho tài khoản học tập, quản trị viên có thể cấu hình thông số cho role/database, ví dụ:

```sql
-- Ví dụ quản trị, cần role/database có thật và quyền phù hợp.
ALTER ROLE lab_user IN DATABASE sql_lab
SET TIME ZONE 'Asia/Ho_Chi_Minh';
```

Câu lệnh `ALTER ROLE` ở trên dành cho người quản trị môi trường; trong bài thực hành thông thường, **`SET TIME ZONE` ở phiên** là đủ và ít ảnh hưởng đến người khác.

### 2.3. `TIMESTAMP` và `TIMESTAMPTZ` không có cùng ý nghĩa

PostgreSQL cung cấp hai kiểu thường gặp:

| Kiểu | Ý nghĩa | Ảnh hưởng của `SET TIME ZONE` |
|---|---|---|
| `TIMESTAMP WITHOUT TIME ZONE` (viết ngắn `TIMESTAMP`) | Ngày và giờ trên đồng hồ, **không chứa** thông tin múi giờ | Không tự đổi giờ hiển thị khi thay múi giờ phiên |
| `TIMESTAMP WITH TIME ZONE` (viết ngắn `TIMESTAMPTZ`) | Một **thời điểm xác định**; PostgreSQL chuẩn hóa nội bộ theo UTC | Hiển thị cùng thời điểm theo múi giờ phiên |

Thử trên một giá trị có độ lệch `+07:00` rõ ràng:

```sql
SET TIME ZONE 'UTC';
SELECT TIMESTAMPTZ '2026-07-15 09:00:00+07' AS event_at;
-- Hiển thị: 2026-07-15 02:00:00+00

SET TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT TIMESTAMPTZ '2026-07-15 09:00:00+07' AS event_at;
-- Hiển thị: 2026-07-15 09:00:00+07
```

Hai kết quả trên chỉ **một thời điểm duy nhất**. Đổi múi giờ phiên làm thay đổi cách hiển thị chứ không làm đổi thời điểm.

Ngược lại:

```sql
SELECT TIMESTAMP '2026-07-15 09:00:00' AS local_wall_time;
-- Vẫn hiển thị ngày và giờ này dù phiên đang ở UTC hay +07.
```

Tên `TIMESTAMPTZ` dễ gây hiểu lầm: PostgreSQL **không lưu lại tên múi giờ gốc** như `Asia/Ho_Chi_Minh` cùng với từng giá trị. Nó lưu thông tin đủ để xác định thời điểm, rồi biểu diễn theo múi giờ phiên khi đọc. Nếu cần biết sự kiện đã được ghi nhận theo **khu vực nào**, lưu thêm cột tên múi giờ nghiệp vụ.

### 2.4. Chuyển đổi giờ cho báo cáo và lọc theo ngày địa phương

Giả sử bảng `events` có cột `occurred_at TIMESTAMPTZ`. Để hiển thị giờ tại Việt Nam bất kể múi giờ của phiên:

```sql
SELECT
    event_id,
    occurred_at,
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vietnam_local_time
FROM events;
```

Với `TIMESTAMPTZ AT TIME ZONE 'Asia/Ho_Chi_Minh'`, kết quả là **`TIMESTAMP` địa phương** tại vùng đã chọn. Đây là phép chuyển phục vụ trình bày; nó không cập nhật dữ liệu gốc.

Để tìm các sự kiện xảy ra **trong ngày 15/07/2026 theo lịch Việt Nam**, nên thể hiện rõ hai mốc địa phương:

```sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= (
    TIMESTAMP '2026-07-15 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND occurred_at < (
    TIMESTAMP '2026-07-16 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
```

Khoảng `>= ngày bắt đầu` và `< ngày kế tiếp` không phải đoán đến mili-giây cuối cùng của ngày. Việc chỉ rõ múi giờ cũng tránh trường hợp một bản báo cáo thay đổi tập kết quả khi kết nối dùng UTC thay vì giờ Việt Nam.

### 2.5. Những lưu ý khi làm việc với thời gian

- `CURRENT_DATE` và việc ép một `TIMESTAMPTZ` về ngày lịch có thể phụ thuộc múi giờ phiên; một thời điểm gần nửa đêm UTC có thể thuộc hai ngày khác nhau tại các khu vực.
- Khi nhập một thời điểm dùng `TIMESTAMPTZ`, ưu tiên giá trị có độ lệch rõ ràng, ví dụ `'2026-07-15 09:00:00+07'`, hoặc biểu diễn UTC. Giá trị thiếu độ lệch có thể được diễn giải theo múi giờ phiên.
- Không nên gắn cứng `+07:00` cho mọi khu vực trên thế giới: nhiều nơi có giờ mùa hè hoặc thay đổi quy tắc lịch sử. Dùng tên vùng IANA khi bài toán yêu cầu đúng quy tắc của địa điểm.
- `SET TIME ZONE` không nhất thiết điều khiển định dạng ngày do driver, ứng dụng hoặc máy người dùng tự chuyển đổi. Kiểm tra đường đi của dữ liệu từ SQL tới giao diện.
- Với kết nối được tái sử dụng qua connection pool, thiết lập chỉ áp dụng cho kết nối đã nhận lệnh. Thiết lập mặc định nhất quán khi tạo kết nối hoặc quy định rõ khi nhận/trả kết nối sẽ an toàn hơn việc giả định mọi phiên giống nhau.

## 3. Mã hóa: giữ nguyên tiếng Việt và ký tự Unicode

### 3.1. Phân biệt Unicode, UTF-8 và collation

**Unicode** quy định các ký tự và mã điểm ký tự (*code point*) cho nhiều ngôn ngữ. **UTF-8** là cách mã hóa các mã điểm đó thành byte để lưu trữ hoặc truyền qua hệ thống.

**Collation** là quy tắc **so sánh và sắp xếp chuỗi**, ví dụ thứ tự các tên có dấu hoặc cách xét chữ hoa/chữ thường. Collation không phải là encoding. Hai cơ sở dữ liệu cùng UTF-8 vẫn có thể cho thứ tự sắp xếp tên khác nhau nếu collation khác nhau.

```text
File SQL UTF-8
    │  đọc đúng byte
    ▼
SQL editor / terminal
    │  client encoding của kết nối
    ▼
PostgreSQL database encoding
    │  dữ liệu Unicode được lưu
    ▼
Kết quả trả về qua client encoding
    │  font và khả năng hiển thị của ứng dụng
    ▼
Người học nhìn thấy: Nguyễn, Đà Nẵng, tiếng Việt
```

Lỗi chữ có thể xảy ra ở **bất kỳ mắt xích** nào. Chỉ đặt database thành UTF-8 sẽ không sửa được file nguồn đã bị lưu bằng mã hóa sai hoặc dữ liệu đã bị biến đổi trước khi gửi tới server.

### 3.2. PostgreSQL: kiểm tra encoding của database và kết nối

```sql
-- Encoding của database hiện tại: đặt khi database được tạo.
SHOW server_encoding;

-- Encoding dùng để trao đổi chuỗi với kết nối hiện tại.
SHOW client_encoding;

-- Thiết lập encoding của kết nối hiện tại là UTF-8.
SET client_encoding TO 'UTF8';

-- Xác nhận.
SHOW client_encoding;

-- Chuỗi kiểm tra có dấu và ký tự ngoài ASCII.
SELECT 'Tiếng Việt: Nguyễn, Đà Nẵng, cà phê ☕' AS sample_text;
```

Trong PostgreSQL, giá trị encoding được viết là `UTF8`; trong tên file/công cụ thường ghi `UTF-8`. `server_encoding` thuộc **database**, không phải cài đặt có thể đổi bằng `SET` cho từng phiên. Muốn tạo database với encoding khác cần xử lý ở bước tạo database và bảo đảm tương thích locale/template; không thể đổi ý nghĩa byte của dữ liệu cũ bằng một lệnh `SET`.

Với `psql`, cũng có thể dùng lệnh riêng của client:

```text
\encoding UTF8
```

Đây là **lệnh meta của `psql`**, không phải câu SQL chuẩn để gửi từ mọi trình SQL editor. Nếu ứng dụng dùng driver, encoding của driver/kết nối và cách ứng dụng đọc file phải phù hợp.

Kiểm tra các thiết lập ảnh hưởng đến so sánh/sắp xếp:

```sql
SHOW lc_collate;
SHOW lc_ctype;
```

Trong PostgreSQL, `lc_collate` phản ánh thiết lập sắp xếp mặc định của database; `lc_ctype` liên quan phân loại ký tự. Tùy phiên bản và cách tạo collation, từng cột hoặc biểu thức có thể chọn collation khác. Vì vậy, **đừng suy luận collation chỉ từ encoding**.

### 3.3. Kiểm tra một vòng ghi và đọc dữ liệu tiếng Việt

Một câu `SELECT '...'` kiểm tra đường đi của chuỗi từ client tới server rồi về client. Để kiểm tra thêm lưu trữ, dùng một **bảng tạm**:

```sql
CREATE TEMP TABLE encoding_lab (
    id INTEGER PRIMARY KEY,
    vietnamese_text TEXT NOT NULL
);

INSERT INTO encoding_lab (id, vietnamese_text)
VALUES (1, 'Nguyễn Thị Ánh – Đà Nẵng, cà phê ☕');

SELECT id, vietnamese_text
FROM encoding_lab;
```

Bảng `TEMP` trong PostgreSQL thuộc phiên làm việc và tự biến mất khi phiên kết thúc. Mẫu này hạn chế ảnh hưởng đến dữ liệu dùng chung; nếu bảng tạm cùng tên đã được tạo trong phiên, hãy mở phiên thực hành mới hoặc chọn tên khác.

Nếu văn bản hiển thị sai, tìm điểm đầu tiên phát sinh lỗi:

1. Mở file `.sql` trong editor và kiểm tra file thực sự được lưu với UTF-8.
2. Chạy `SHOW server_encoding` và `SHOW client_encoding` trên đúng kết nối đang dùng.
3. Kiểm tra cài đặt encoding của ứng dụng SQL, terminal và quy trình import/export.
4. Đối chiếu giá trị ngay sau khi `SELECT` trực tiếp trong SQL editor với dữ liệu được ứng dụng/web hiển thị.
5. Nếu nguồn đã thành các dấu hỏi `?` hoặc bị ghi sai byte, đổi encoding ở bước cuối thường **không phục hồi** được thông tin đã mất; cần sửa lại từ nguồn gốc đúng.

### 3.4. Encoding của CSV, terminal và kết quả xuất

Đừng mặc định một file CSV là UTF-8 vì nội dung “trông có vẻ đúng”. File có thể được tạo với UTF-8, Windows-1258 hoặc mã hóa khác; chương trình mở file có thể tự đoán sai.

Với PostgreSQL, các thao tác import/export qua client như `\copy` của `psql` cần bảo đảm dữ liệu file và encoding của kết nối phù hợp. Với lệnh `COPY` phía server, phải phân biệt **file trên máy chủ** với **file ở máy client**, và có thể chỉ rõ tùy chọn encoding khi cần. Cách làm nhất quán trong môi trường học tập là: **lưu mã nguồn SQL và CSV bằng UTF-8, kiểm tra client encoding bằng `SHOW client_encoding`, sau đó kiểm tra dữ liệu có dấu bằng một truy vấn đọc lại**.

Việc sắp xếp tên có dấu là vấn đề riêng:

```sql
SELECT full_name
FROM people
ORDER BY full_name;
```

Nếu bảng `people` tồn tại, thứ tự của câu lệnh phụ thuộc collation áp dụng. SQL không hứa rằng mọi database UTF-8 sẽ sắp `Â`, `Ă`, `A` hoặc tên tiếng Việt theo cùng một quy tắc. Đề bài yêu cầu thứ tự cụ thể thì cần quy định collation phù hợp và kiểm thử ở môi trường đích.

## 4. Tự động xác nhận giao dịch (autocommit)

### 4.1. Giao dịch là đơn vị công việc gì?

Một **transaction (giao dịch)** là một nhóm thao tác dữ liệu được xử lý như một đơn vị xác nhận:

- `BEGIN` hoặc `START TRANSACTION`: bắt đầu giao dịch tường minh, tùy cú pháp hệ quản trị.
- `COMMIT`: xác nhận thay đổi đã thực hiện trong giao dịch.
- `ROLLBACK`: hủy những thay đổi của giao dịch chưa được xác nhận.
- `SAVEPOINT`: đặt mốc để có thể quay lại một phần trong giao dịch khi hệ quản trị hỗ trợ.

```text
BEGIN
  │
  ├── INSERT / UPDATE / DELETE
  │
  ├── COMMIT   → xác nhận thay đổi
  │
  └── ROLLBACK → hủy thay đổi chưa xác nhận
```

**Autocommit** thường là cơ chế của **client/driver hoặc phiên kết nối** quyết định liệu mỗi câu lệnh chạy ngoài một giao dịch tường minh có được xác nhận tự động hay không. Cơ chế và cách đặt tên thay đổi theo hệ quản trị; không có một câu lệnh `SHOW AUTOCOMMIT` thống nhất cho mọi database.

### 4.2. PostgreSQL và `psql`: mặc định tự xác nhận từng lệnh

`psql` thường bắt đầu với biến `AUTOCOMMIT` ở trạng thái bật. Khi đó một lệnh `INSERT`/`UPDATE`/`DELETE` được chạy **ngoài `BEGIN` tường minh** sẽ được thực hiện trong giao dịch ngầm và xác nhận khi lệnh hoàn tất thành công.

Trong `psql`, có thể xem và đổi cách client hoạt động:

```text
-- Đây là meta-command của psql, không phải SQL chuẩn:
\echo :AUTOCOMMIT
\set AUTOCOMMIT on
\set AUTOCOMMIT off
```

`\echo :AUTOCOMMIT` hiển thị giá trị biến của `psql`; `\set AUTOCOMMIT off` làm `psql` chủ động mở giao dịch trước các lệnh thích hợp để người dùng phải `COMMIT`/`ROLLBACK` thủ công. Khi tắt autocommit, **đừng quên kết thúc giao dịch** trước khi đóng kết nối hoặc bắt đầu bài khác.

Trong PostgreSQL server, các cú pháp sau **không phải** cách điều khiển autocommit:

```sql
-- Không dùng trong PostgreSQL:
-- SHOW AUTOCOMMIT;
-- SET AUTOCOMMIT = OFF;
```

Các công cụ GUI như DBeaver hoặc DataGrip có nút/thiết lập Auto-commit riêng; driver JDBC cũng có `Connection.setAutoCommit(boolean)`. Khi dùng công cụ khác `psql`, hãy xem chế độ giao dịch ngay trong công cụ đó.

### 4.3. Thử thay đổi dữ liệu rồi `ROLLBACK`

Để thực hành mà không ảnh hưởng bảng dùng chung, mở một phiên PostgreSQL mới và dùng bảng tạm:

```sql
-- Khi tạo bảng, bảo đảm công cụ đang ở chế độ autocommit ON
-- hoặc giao dịch tạo bảng đã được COMMIT trước bài thử bên dưới.
CREATE TEMP TABLE transaction_lab (
    id INTEGER PRIMARY KEY,
    description TEXT NOT NULL
);

BEGIN;

INSERT INTO transaction_lab (id, description)
VALUES (1, 'Thử giao dịch – chưa xác nhận');

-- Trong giao dịch này, bạn thấy dòng vừa INSERT.
SELECT * FROM transaction_lab ORDER BY id;

ROLLBACK;

-- Sau ROLLBACK, dòng id=1 không còn trong bảng tạm.
SELECT * FROM transaction_lab ORDER BY id;
```

Nếu công cụ đang để chế độ autocommit thủ công từ trước, trước tiên cần **xác nhận giao dịch tạo bảng**, nếu không `ROLLBACK` có thể làm mất luôn bảng vừa tạo. Điều đó là do bảng được tạo *trong cùng giao dịch*; không phải lỗi của `ROLLBACK`.

Thử xác nhận có chủ ý:

```sql
BEGIN;

INSERT INTO transaction_lab (id, description)
VALUES (2, 'Giao dịch đã xác nhận');

COMMIT;

SELECT * FROM transaction_lab ORDER BY id;
-- Thấy dòng id=2 trong suốt phần còn lại của phiên.
```

Kết quả của `COMMIT` không có nghĩa dữ liệu bảng tạm tồn tại sau khi đóng phiên. Hai khái niệm cần tách:

- **Xác nhận giao dịch**: dòng id=2 không còn bị `ROLLBACK` của giao dịch mới hủy.
- **Vòng đời bảng tạm**: toàn bộ `transaction_lab` bị xóa khi phiên PostgreSQL kết thúc.

Nếu thực hành bằng bảng thông thường thay vì bảng tạm, `COMMIT` xác nhận thay đổi trên bảng đó để các kết nối khác có thể quan sát theo quy tắc cách ly giao dịch.

### 4.4. Autocommit bật không ngăn bạn dùng giao dịch tường minh

Khi autocommit đang bật, ta vẫn có thể chủ động gom nhiều thao tác vào một giao dịch:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100000
WHERE account_id = 2;

COMMIT;
```

Đây chỉ là **ví dụ cấu trúc** cho hai thay đổi phải đi cùng nhau, giả sử bảng `accounts` tồn tại. Ứng dụng thực tế cần kiểm tra tài khoản, số dư, số dòng được cập nhật, cách ly giao dịch và xử lý lỗi trước khi `COMMIT`. Điểm chính: **autocommit ON** vẫn cho phép `BEGIN ... COMMIT` để xác nhận nhiều câu lệnh cùng lúc.

Nếu trong ví dụ trên có lỗi giữa hai thao tác và cần hủy toàn bộ, dùng `ROLLBACK` khi giao dịch chưa xác nhận. **Không thể dùng `ROLLBACK` để hủy một `UPDATE` đã được autocommit xác nhận trước đó**; phải thực hiện một thao tác bù đắp có chủ đích nếu thật sự cần đảo ngược.

### 4.5. `SAVEPOINT`: chỉ hủy một phần giao dịch

Khi cần thử một phần rồi quay lại mốc, PostgreSQL hỗ trợ:

```sql
BEGIN;

INSERT INTO transaction_lab (id, description)
VALUES (3, 'Giữ lại');

SAVEPOINT before_optional_step;

INSERT INTO transaction_lab (id, description)
VALUES (4, 'Sẽ hủy');

ROLLBACK TO SAVEPOINT before_optional_step;

COMMIT;

SELECT * FROM transaction_lab ORDER BY id;
-- id=3 còn; id=4 không còn.
```

`ROLLBACK TO SAVEPOINT` không hủy cả giao dịch mà chỉ hoàn tác các thao tác sau mốc. Sau đó có thể tiếp tục và `COMMIT` những thao tác còn lại.

### 4.6. Hai phiên kết nối có thể thấy dữ liệu khác nhau

Giả sử kết nối A bắt đầu giao dịch, cập nhật một dòng nhưng chưa `COMMIT`. Trên kết nối A, lệnh `SELECT` có thể thấy thay đổi do chính giao dịch A thực hiện. Kết nối B thường **chưa thấy** thay đổi chưa xác nhận đó theo mức cách ly mặc định của PostgreSQL. Sau khi A `COMMIT`, những truy vấn mới tại B có thể thấy thay đổi, tùy mức cách ly và thời điểm bắt đầu giao dịch đọc của B.

Đây là lý do khi thử autocommit, cần phân biệt:

1. Điều đang hiển thị trong **chính phiên đã sửa**.
2. Điều phiên **khác** được phép quan sát.
3. Trạng thái đã được **`COMMIT` hay chưa**.

Autocommit và **transaction isolation** là hai chủ đề liên quan nhưng khác nhau. Autocommit quyết định ranh giới xác nhận, còn isolation quyết định cách các giao dịch quan sát nhau.

### 4.7. Khi nào nên bật hoặc tắt autocommit trong môi trường thực hành?

| Tình huống | Cách phù hợp | Lý do |
|---|---|---|
| Chạy truy vấn `SELECT`, tạo dữ liệu mẫu đơn giản | Autocommit ON thường thuận tiện | Ít giao dịch mở lâu ngoài ý muốn |
| Học `BEGIN`, `COMMIT`, `ROLLBACK` | Giữ autocommit ON và viết giao dịch tường minh | Ranh giới giao dịch hiện rõ trong script |
| Chỉnh sửa nhiều bước phải đi cùng nhau | Giao dịch tường minh hoặc chế độ manual commit của client | Có thể xác nhận/hủy cả chuỗi thao tác |
| Thử `UPDATE`/`DELETE` trên dữ liệu quan trọng | Xác định điều kiện, kiểm tra trước và dùng giao dịch có chủ đích | Tránh xác nhận nhầm thao tác |
| Một script có nhiều lệnh DDL | Xem ngữ nghĩa riêng của hệ quản trị | Một số hệ, nhất là MySQL, có lệnh DDL gây implicit commit |

Không nên mặc định rằng mọi lệnh DDL có thể `ROLLBACK` trên mọi database. PostgreSQL hỗ trợ giao dịch cho nhiều thao tác DDL, nhưng cũng có ngoại lệ; MySQL có những lệnh DDL tự tạo ranh giới giao dịch. Hãy đọc tài liệu của hệ quản trị khi chuẩn bị script khởi tạo có tác động lớn.

## 5. Thực hành liền mạch với PostgreSQL

**Mục tiêu:** tạo một phiên thử có giờ Việt Nam, UTF-8 và thao tác giao dịch tường minh; kiểm tra kết quả cả trước và sau `COMMIT`/`ROLLBACK`.

**Điều kiện:** sử dụng một database thực hành, tài khoản đủ quyền tạo bảng tạm, kết nối PostgreSQL hoạt động bình thường. Với `psql`, giữ `AUTOCOMMIT` ở trạng thái `on` cho kịch bản sau; trong SQL editor khác, bật Auto-commit của kết nối trước khi bắt đầu. Các lệnh `SHOW` và `SET` sau đây chạy trên **cùng một kết nối**.

### Bước 1 — Kiểm tra trạng thái ban đầu

```sql
SELECT current_database() AS database_name,
       current_user AS connected_user;

SHOW TIME ZONE;
SHOW server_encoding;
SHOW client_encoding;
SHOW lc_collate;
SHOW lc_ctype;
```

Ghi lại kết quả, đặc biệt `TIME ZONE`, `server_encoding` và `client_encoding`. Với `psql`, có thể dùng thêm `\echo :AUTOCOMMIT` (meta-command, không phải SQL).

### Bước 2 — Thiết lập cho phiên

```sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';
SET client_encoding TO 'UTF8';

SHOW TIME ZONE;
SHOW client_encoding;
```

Kết quả mong đợi của hai lệnh `SHOW` là `Asia/Ho_Chi_Minh` và `UTF8`. Nếu database đã có `server_encoding` khác, lệnh `SET client_encoding` **không chuyển đổi encoding lưu trữ** của database.

### Bước 3 — Tạo bảng tạm và hoàn tác thử nghiệm

```sql
CREATE TEMP TABLE environment_lab (
    id INTEGER PRIMARY KEY,
    student_note TEXT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL
);

BEGIN;

INSERT INTO environment_lab (id, student_note, event_at)
VALUES (
    1,
    'Nguyễn: thử ghi và ROLLBACK',
    TIMESTAMPTZ '2026-07-15 09:00:00+07'
);

SELECT id, student_note, event_at
FROM environment_lab;
-- Lúc này nhìn thấy dòng id=1 trong giao dịch hiện tại.

ROLLBACK;

SELECT COUNT(*) AS rows_after_rollback
FROM environment_lab;
-- Dự kiến: 0.
```

Múi giờ được hiển thị trên `event_at` phản ánh phiên đang đặt ở `Asia/Ho_Chi_Minh`. Chuỗi tiếng Việt giúp nhận biết lỗi mã hóa nếu có.

### Bước 4 — Xác nhận giao dịch rồi đổi múi giờ hiển thị

```sql
BEGIN;

INSERT INTO environment_lab (id, student_note, event_at)
VALUES (
    2,
    'Đà Nẵng: bản ghi đã COMMIT',
    TIMESTAMPTZ '2026-07-15 09:00:00+07'
);

COMMIT;

SET TIME ZONE 'UTC';

SELECT id, student_note, event_at
FROM environment_lab
ORDER BY id;
-- event_at của id=2 hiển thị khoảng 2026-07-15 02:00:00+00.

SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT id, student_note, event_at
FROM environment_lab
ORDER BY id;
-- Cùng bản ghi đó, event_at hiển thị khoảng 2026-07-15 09:00:00+07.
```

Đổi múi giờ chỉ thay đổi cách đọc thời điểm. Chuỗi tiếng Việt giữ nguyên. Dòng `id=1` đã bị hủy bởi `ROLLBACK`; dòng `id=2` đã được xác nhận bằng `COMMIT` và còn tồn tại trong bảng tạm đến hết phiên.

### Bước 5 — Đưa cấu hình phiên về giá trị mặc định

```sql
RESET TIME ZONE;
RESET client_encoding;

SHOW TIME ZONE;
SHOW client_encoding;
```

Hai lệnh `RESET` đưa tham số về giá trị mặc định tương ứng của phiên hiện tại, không phải lúc nào cũng là `UTC` và `UTF8`. Bảng tạm tự xóa khi kết nối PostgreSQL kết thúc.

## 6. Đối chiếu nhanh giữa PostgreSQL, MySQL và SQLite

Các hệ quản trị cùng hỗ trợ SQL nhưng **cú pháp thiết lập môi trường và hành vi của kiểu dữ liệu không hoàn toàn giống nhau**.

| Nội dung | PostgreSQL | MySQL | SQLite |
|---|---|---|---|
| Xem múi giờ phiên | `SHOW TIME ZONE;` | `SELECT @@session.time_zone;` | Không có tham số SQL tương đương cho múi giờ phiên |
| Đặt múi giờ | `SET TIME ZONE 'Asia/Ho_Chi_Minh';` | `SET time_zone = '+07:00';` hoặc dùng tên khu vực nếu hệ thống đã nạp bảng múi giờ | Dùng các hàm ngày giờ và cấu hình môi trường ứng dụng phù hợp |
| Encoding database/kết nối | `SHOW server_encoding;`, `SHOW client_encoding;`, `SET client_encoding TO 'UTF8';` | `SHOW VARIABLES LIKE 'character_set_%';`, `SET NAMES utf8mb4;` | `PRAGMA encoding;`, database thường ở UTF-8 hoặc UTF-16 |
| Autocommit | `psql`: biến client `AUTOCOMMIT`; SQL giao dịch: `BEGIN`/`COMMIT` | `SELECT @@session.autocommit;`, `SET SESSION autocommit = 0;` | Thường tự xác nhận từng lệnh ngoài giao dịch; dùng `BEGIN`/`COMMIT`/`ROLLBACK` |
| Kiểu lưu thời gian | `TIMESTAMPTZ` phân biệt với `TIMESTAMP` | `TIMESTAMP` chuyển theo múi giờ phiên, `DATETIME` lưu ngày/giờ không kèm múi giờ | Không có kiểu lưu trữ ngày giờ độc lập như hai hệ trên; thường dùng TEXT/REAL/INTEGER |

### 6.1. MySQL: cú pháp mẫu

```sql
-- Xem cấu hình của phiên.
SELECT
    @@session.time_zone AS session_time_zone,
    @@session.autocommit AS autocommit_mode;

SHOW VARIABLES LIKE 'character_set_%';
SHOW VARIABLES LIKE 'collation_%';

-- Đặt múi giờ theo độ lệch +07:00 trong phiên.
SET time_zone = '+07:00';

-- Chuỗi Unicode đầy đủ, bao gồm ký tự ngoài BMP.
SET NAMES utf8mb4;

-- Tắt autocommit của phiên để chủ động COMMIT/ROLLBACK.
SET SESSION autocommit = 0;
```

Trong MySQL, `utf8mb4` là lựa chọn cho Unicode UTF-8 đầy đủ. Một số hệ thống cũ dùng tên `utf8` với ý nghĩa giới hạn hơn; không nên đánh đồng hai cách gọi. `SET NAMES utf8mb4` cấu hình encoding giao tiếp của kết nối; nó **không tự chuyển toàn bộ bảng/cột hiện có** sang `utf8mb4`.

Nếu dùng tên múi giờ như `Asia/Ho_Chi_Minh` trong MySQL, máy chủ cần dữ liệu bảng múi giờ đã được nạp. Nếu chưa có, cài đặt tên khu vực có thể thất bại, còn `'+07:00'` là độ lệch cố định thích hợp cho bài thử ở Việt Nam. Với ứng dụng toàn cầu và các vùng có giờ mùa hè, cần tên vùng và dữ liệu múi giờ được cập nhật.

Để trở lại chế độ tự xác nhận sau khi đã xử lý giao dịch đang mở:

```sql
-- Kết thúc giao dịch hiện tại một cách có chủ đích trước.
ROLLBACK;
SET SESSION autocommit = 1;
```

Lưu ý rằng việc đổi từ autocommit tắt sang bật trong MySQL **có thể tạo implicit commit** đối với giao dịch đang mở; không bật lại một cách tùy tiện khi vẫn còn thao tác chưa xác nhận.

### 6.2. SQLite: không có đầy đủ các tham số phiên như PostgreSQL

```sql
-- Xem encoding file database hiện tại.
PRAGMA encoding;

-- Giao dịch tường minh.
BEGIN;
CREATE TABLE example_notes (id INTEGER PRIMARY KEY, note TEXT);
INSERT INTO example_notes (id, note)
VALUES (1, 'Tiếng Việt: Đà Nẵng');
ROLLBACK;
```

Trong SQLite, `PRAGMA encoding` phản ánh encoding của file database; lựa chọn encoding phải được thực hiện ở giai đoạn tạo database, không phải cách sửa nội dung đã được lưu. Hàm ngày giờ của SQLite có cách làm việc riêng với UTC và `localtime`, phụ thuộc môi trường chạy; không có `SET TIME ZONE` theo phiên như PostgreSQL.

SQLite có chế độ autocommit khi không có giao dịch tường minh, nhưng các thư viện gọi SQLite có thể chủ động mở giao dịch theo cấu hình kết nối. Vì vậy, phải xem cả hành vi thư viện/driver, không chỉ câu SQL.

## 7. Các lỗi thường gặp và cách nhận diện

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Dữ liệu `TIMESTAMPTZ` hiển thị lệch 7 giờ giữa hai máy | Hai phiên có múi giờ khác nhau | `SHOW TIME ZONE` ở từng phiên; thống nhất biểu diễn UTC hoặc quy tắc chuyển đổi |
| Lọc “ngày hôm nay” cho ra kết quả khác nhau | Ngày lịch được tính theo múi giờ phiên | Chỉ rõ múi giờ nghiệp vụ và mốc thời gian cần lọc |
| Giá trị `TIMESTAMP` không đổi khi dùng `SET TIME ZONE` | Kiểu không chứa ngữ nghĩa thời điểm theo múi giờ | Chọn đúng kiểu theo ý nghĩa dữ liệu; chuyển đổi tường minh khi cần |
| `Nguyễn` thành chuỗi lỗi | File nguồn, client hoặc import/export dùng sai encoding | Kiểm tra từng chặng và đọc lại từ nguồn đúng |
| Chữ có dấu đúng nhưng `ORDER BY` cho thứ tự lạ | Collation khác mong đợi | Xác định quy tắc sắp xếp cần thiết |
| `ROLLBACK` nhưng dữ liệu vẫn còn | Lệnh trước đó đã autocommit | Xem chế độ của client; dùng `BEGIN` trước thao tác cần hoàn tác |
| `ROLLBACK` làm mất cả bảng thử mới tạo | Bảng được tạo trong cùng giao dịch chưa `COMMIT` | Tách giao dịch khởi tạo bảng khỏi giao dịch kiểm tra |
| Chạy `SHOW AUTOCOMMIT` trong PostgreSQL báo lỗi | Nhầm lệnh MySQL hoặc cài đặt client với tham số server | Trong `psql` xem `\echo :AUTOCOMMIT`; ở GUI xem cài đặt kết nối |
| Lệnh `SET` thành công nhưng tab khác không đổi | Tab khác dùng session/connection riêng | Kiểm tra, thiết lập trên từng kết nối hoặc cấu hình mặc định kết nối |
| Script MySQL gặp DDL rồi `ROLLBACK` không hoàn tác như dự tính | Một số DDL tạo implicit commit | Xem rõ ranh giới giao dịch của hệ quản trị |

## 8. Bài tập tự luyện

Các bài dưới đây giả định bạn đang thực hành trên PostgreSQL. Với bài dùng bảng tạm, nên mở một kết nối học tập mới.

**Bài 1 — Múi giờ.** Đặt phiên là `UTC`, chạy truy vấn với `TIMESTAMPTZ '2026-07-15 09:00:00+07'`; sau đó chuyển sang `Asia/Ho_Chi_Minh` và chạy lại. Giải thích vì sao hai kết quả hiển thị khác giờ mà vẫn là cùng một thời điểm.

**Bài 2 — Mã hóa.** Kiểm tra `server_encoding` và `client_encoding`, đặt encoding của client thành `UTF8`, rồi thử đọc chuỗi `'Trường Đại học – Hà Nội ☕'`. Nêu những thành phần phải kiểm tra nếu dữ liệu hiển thị sai.

**Bài 3 — Hoàn tác.** Tạo bảng tạm `practice_tx(id INTEGER PRIMARY KEY, note TEXT)`. Chạy `BEGIN`, `INSERT` một dòng, `SELECT`, `ROLLBACK`, sau đó `SELECT` lại. Giải thích sự thay đổi số dòng.

**Bài 4 — Xác nhận.** Trên bảng `practice_tx`, thêm một dòng khác trong `BEGIN ... COMMIT`. Thử gọi `ROLLBACK` sau `COMMIT` (ngoài giao dịch), rồi kiểm tra dòng đã thêm. Giải thích vì sao một giao dịch mới không thể hủy giao dịch cũ đã xác nhận.

**Bài 5 — Phân biệt phạm vi.** Hai tab SQL kết nối đến cùng một database; tab A dùng `SET TIME ZONE 'UTC'`, tab B dùng `SET TIME ZONE 'Asia/Ho_Chi_Minh'`. Dự đoán `SHOW TIME ZONE` và cách hiển thị một giá trị `TIMESTAMPTZ` ở mỗi tab. Giải thích điều gì xảy ra nếu cả hai tab vô tình dùng chung một kết nối.

### Gợi ý kết quả

- **Bài 1:** `02:00 +00` và `09:00 +07` cùng chỉ một thời điểm; `TIMESTAMPTZ` được diễn giải theo múi giờ phiên.
- **Bài 2:** Mã hóa file, editor/terminal, client encoding, database encoding và lớp hiển thị đều có thể ảnh hưởng; encoding và collation là hai vấn đề khác nhau.
- **Bài 3:** Dòng thấy được trong giao dịch trước `ROLLBACK`; sau khi hủy, bảng tạm trở lại 0 dòng nếu ban đầu rỗng.
- **Bài 4:** `COMMIT` đã xác nhận dòng; `ROLLBACK` sau đó không đảo ngược giao dịch trước. Trong PostgreSQL, `ROLLBACK` khi không có giao dịch đang mở chỉ cảnh báo, không làm mất dòng đã xác nhận.
- **Bài 5:** Hai kết nối riêng có tham số phiên độc lập; nếu công cụ tái dùng cùng một kết nối thật, câu `SET` sau có thể làm thay đổi cách hiển thị ở cả hai nơi.

## 9. Mẫu ghi chú cấu hình cho mỗi buổi thực hành

Trước khi làm bài SQL, có thể ghi ngắn gọn như sau:

```text
Hệ quản trị: PostgreSQL (ghi phiên bản thực tế)
Database / user: <tên database> / <tài khoản bài tập>
SQL client: psql hoặc tên công cụ đang dùng
Múi giờ của session: Asia/Ho_Chi_Minh (kiểm tra SHOW TIME ZONE)
Database encoding: kết quả SHOW server_encoding
Client encoding: UTF8 (kiểm tra SHOW client_encoding)
Autocommit: ON hoặc OFF theo chế độ của client
Quy tắc transaction: BEGIN ... COMMIT/ROLLBACK rõ ràng khi thay đổi dữ liệu
```

Việc ghi rõ các giá trị thực tế giúp tái hiện bài tập, giải thích khác biệt khi chạy trên máy khác và phân biệt lỗi SQL với lỗi cấu hình môi trường.

## 10. Ghi nhớ trước khi bắt đầu những bài SQL tiếp theo

**Múi giờ** quyết định cách diễn giải và hiển thị dữ liệu thời gian; hãy phân biệt kiểu lưu một thời điểm (`TIMESTAMPTZ`) với kiểu ngày giờ địa phương (`TIMESTAMP`) trong PostgreSQL. **Mã hóa** quyết định việc trao đổi và lưu văn bản đúng ký tự; UTF-8 của file, kết nối và database cần tương thích, còn thứ tự sắp xếp thuộc về collation. **Autocommit** quyết định thời điểm các thao tác được xác nhận; muốn thử thay đổi và có thể hoàn tác, hãy đặt ranh giới giao dịch bằng `BEGIN`, `COMMIT` và `ROLLBACK` một cách có chủ đích.

Ba thao tác kiểm tra ban đầu trong PostgreSQL thường hữu ích nhất là:

```sql
SHOW TIME ZONE;
SHOW server_encoding;
SHOW client_encoding;
```

Kết hợp với việc xác nhận chế độ autocommit của **công cụ đang kết nối**, bạn sẽ có một môi trường thực hành SQL dễ hiểu, tái lập và an toàn hơn khi chạy các ví dụ có ngày giờ, dữ liệu tiếng Việt và câu lệnh thay đổi dữ liệu.
