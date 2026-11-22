# Khóa bi quan và phạm vi tài nguyên bị khóa

**Khóa bi quan** (*pessimistic locking*) là cách kiểm soát đồng thời trong đó giao dịch yêu cầu cơ sở dữ liệu giữ một hoặc nhiều khóa để các thao tác xung đột phải **chờ, thất bại hoặc bỏ qua tài nguyên đang bận**, tùy loại khóa và cách truy vấn. Mục đích là bảo vệ quá trình đọc–kiểm tra–ghi khi nhiều tác nhân có thể thay đổi cùng dữ liệu.

Điểm quan trọng nhất không chỉ là "có khóa hay không", mà là **khóa tài nguyên nào, với chế độ khóa nào, được giữ trong bao lâu và ngăn được những thao tác nào**. Khóa một hàng đang tồn tại không đồng nghĩa với khóa mọi hàng sẽ thỏa cùng điều kiện trong tương lai. Khóa hàng cũng không đồng nghĩa với việc chặn mọi câu `SELECT` của người khác.

Bài học thuộc chương **Kiểm soát đồng thời** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Mô-đun hướng đến hiểu nền tảng lưu trữ bền vững trong ứng dụng, từ mô hình dữ liệu, schema, truy vấn, chỉ mục đến transaction, mức cô lập và kiểm soát đồng thời; đồng thời thiết kế ranh giới persistence trong Java, ứng phó lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng. Bài này tập trung vào việc **chọn đúng phạm vi khóa cho bất biến nghiệp vụ**, triển khai an toàn trong Java và đánh giá ảnh hưởng của khóa đến khả năng xử lý đồng thời.

Các ví dụ SQL chính dùng **PostgreSQL**. Các DBMS khác như MySQL/InnoDB và SQL Server có ngữ nghĩa khóa, phạm vi khóa và cú pháp không hoàn toàn giống nhau; các khác biệt quan trọng được nêu riêng.

## 1. Khi nào cần khóa bi quan?

Giả sử hai khách hàng đồng thời đặt mua một sản phẩm chỉ còn **5 đơn vị**. Mỗi khách hàng muốn mua **4 đơn vị**:

```text
T1: SELECT available = 5
T2: SELECT available = 5
T1: thấy đủ hàng, chuẩn bị trừ 4
T2: cũng thấy đủ hàng, chuẩn bị trừ 4
```

Nếu ứng dụng kiểm tra số tồn từ một lần đọc rồi cập nhật thiếu điều kiện đồng thời, một hoặc cả hai quyết định có thể dựa trên **thông tin đã cũ**. Vấn đề là quy trình nghiệp vụ cần nhìn thấy một trạng thái có ý nghĩa tại lúc quyết định ghi và cần bảo đảm bất biến `available >= 0`.

Khóa bi quan có thể tuần tự hóa phần công việc tranh chấp:

```text
T1: BEGIN
T1: SELECT sản phẩm 10 FOR UPDATE  -> giữ khóa hàng
T1: kiểm tra available = 5
T2: BEGIN
T2: SELECT sản phẩm 10 FOR UPDATE  -> phải chờ T1
T1: trừ 4; COMMIT
T2: được tiếp tục, thấy available = 1; từ chối mua 4
```

Ở PostgreSQL `READ COMMITTED`, câu đọc khóa của T2 sau khi chờ cập nhật đồng thời thường được đánh giá theo phiên bản hàng đã commit phù hợp. Trong hệ hoặc mức cô lập khác, giao dịch có thể nhận lỗi xung đột và phải thử lại. **Khóa là một phương tiện bảo vệ bất biến, không phải thay thế cho kiểm tra điều kiện tại bước ghi**.

Khóa bi quan đặc biệt hữu ích khi:

- Nhiều request thường tranh chấp cùng đối tượng, chẳng hạn số dư, tồn kho hoặc một bản ghi trạng thái.
- Giao dịch cần **đọc trạng thái hiện tại, kiểm tra nhiều điều kiện rồi cập nhật** các hàng liên quan.
- Chi phí để một quyết định ghi thất bại muộn cao hơn chi phí đợi khóa có kiểm soát.
- Có thể giữ transaction ngắn, số tài nguyên phải khóa ít và thứ tự lấy khóa rõ ràng.

Trong trường hợp chỉ cần một phép cập nhật có điều kiện trên một hàng, **`UPDATE` nguyên tử** đôi khi đủ bảo vệ nghiệp vụ mà không cần một câu `SELECT ... FOR UPDATE` riêng. Sẽ xét kỹ ở phần 9.

## 2. Khái niệm cốt lõi: tài nguyên, chế độ khóa và vòng đời khóa

Một khóa có ít nhất bốn thuộc tính cần xác định:

| Thành phần | Câu hỏi thiết kế | Ví dụ |
|---|---|---|
| **Tài nguyên** (*resource*) | Phần dữ liệu hay cấu trúc nào được bảo vệ? | Một hàng `inventory`, nhiều hàng `accounts`, một bảng, một khoảng khóa trong chỉ mục |
| **Chế độ khóa** (*mode*) | Thao tác nào có thể đồng thời, thao tác nào xung đột? | Khóa đọc chia sẻ, khóa cập nhật/độc quyền, `FOR UPDATE`, `FOR SHARE` |
| **Phạm vi khóa** (*scope/granularity*) | Một hàng, tập hàng, vùng khóa chỉ mục hay toàn bảng? | Hàng có `product_id = 10` so với mọi sản phẩm trong kho |
| **Thời gian giữ** (*duration*) | Khi nào khóa được giải phóng? | Thông thường sau `COMMIT`/`ROLLBACK` của transaction chứa lệnh khóa |

**Granularity** là mức chi tiết của tài nguyên bị khóa. Khóa quá rộng làm các giao dịch không liên quan phải chờ nhau; khóa quá hẹp có thể bỏ sót dữ liệu cần bảo vệ. Cả hai đều là lỗi thiết kế nếu không phù hợp với bất biến nghiệp vụ.

Trong PostgreSQL, cần phân biệt **khóa cấp hàng** và **khóa cấp bảng đi kèm**: `SELECT ... FOR UPDATE` lấy row-level locks trên các hàng liên quan, đồng thời lấy một table-level lock mode `ROW SHARE` trên bảng được đọc để khóa. Tên `ROW SHARE` ở đây là **tên chế độ khóa cấp bảng**, không có nghĩa là khóa chia sẻ trên từng hàng. Một câu `UPDATE` còn lấy khóa cấp bảng `ROW EXCLUSIVE` và khóa cấp hàng theo loại cập nhật.

Các khóa thường được giữ đến khi transaction kết thúc; cơ chế timeout, `NOWAIT`, `SKIP LOCKED`, savepoint và sự cố kết nối có thể thay đổi cách câu lệnh kết thúc hoặc giải phóng một số khóa. Không dựa vào việc Java trả về khỏi một method trong khi transaction vẫn còn mở để cho rằng khóa đã được thả.

## 3. Các cấp tài nguyên bị khóa

### 3.1. Khóa cấp hàng (*row-level lock*)

Đây là cấp thường dùng cho thao tác đọc–sửa–ghi một thực thể cụ thể. Trong PostgreSQL, một câu:

```sql
BEGIN;

SELECT product_id, available
FROM inventory
WHERE product_id = 10
FOR UPDATE;

-- Kiểm tra nghiệp vụ, sau đó UPDATE và COMMIT/ROLLBACK.
```

sẽ giữ khóa cập nhật trên **hàng tìm thấy** cho đến khi transaction kết thúc. Một transaction khác định `UPDATE`, `DELETE` hoặc `SELECT ... FOR UPDATE` lên cùng hàng phải phối hợp với khóa đó: chờ, thất bại hoặc bỏ qua tùy truy vấn. Nhưng `SELECT` thông thường của PostgreSQL dưới MVCC **thường vẫn đọc được phiên bản đã commit đang nhìn thấy** của hàng, không nhất thiết đợi khóa cập nhật được thả.

Nếu `WHERE product_id = 10` **không tìm thấy hàng nào**, truy vấn trên không tạo ra khóa cấp hàng cho sản phẩm `10`. Nó không ngăn một transaction khác `INSERT` hàng `product_id = 10` sau đó. Đây là giới hạn rất quan trọng khi muốn bảo đảm "không có hàng nào thỏa điều kiện".

Nếu truy vấn trả về 500 hàng và tất cả đều được khóa, phạm vi thực tế là một **tập 500 hàng**, không phải chỉ một hàng vì câu lệnh có `FOR UPDATE`. Điều kiện `WHERE`, phép join, kế hoạch thực thi và hành vi của DBMS đều ảnh hưởng đến số hàng và tài nguyên được khóa. Trong PostgreSQL, thông thường `FOR UPDATE` khóa các hàng được chọn; khi có `LIMIT`, thứ tự và vị trí khóa có thể ảnh hưởng số hàng bị khóa, nên cần kiểm chứng kế hoạch và hành vi thực tế.

### 3.2. Khóa cấp bảng (*table-level lock*)

Khóa cấp bảng giúp phối hợp DML, DDL và các thao tác khác trên cấu trúc bảng. Trong PostgreSQL, *mode* của khóa bảng nhiều hơn hai nhãn "đọc"/"ghi"; ví dụ:

| Câu lệnh PostgreSQL | Khóa cấp bảng thường liên quan | Ý nghĩa |
|---|---|---|
| `SELECT` thông thường | `ACCESS SHARE` | Tương thích với nhiều hoạt động khác; xung đột với `ACCESS EXCLUSIVE` |
| `SELECT ... FOR UPDATE` | `ROW SHARE` | Đi kèm khóa trên các hàng được chọn |
| `INSERT` / `UPDATE` / `DELETE` | `ROW EXCLUSIVE` | Phối hợp ghi, vẫn có thể cho phép DML trên hàng khác chạy song song |
| `LOCK TABLE ... IN ACCESS EXCLUSIVE MODE` | `ACCESS EXCLUSIVE` | Chặn nhiều thao tác đọc/ghi khác cho đến khi kết thúc transaction |

Một câu `UPDATE` có **table-level `ROW EXCLUSIVE`** không có nghĩa nó chiếm toàn bộ bảng để cấm mọi `UPDATE` khác; các mode bảng này thường vẫn tương thích với những `ROW EXCLUSIVE` khác. Xung đột cụ thể trên các hàng bị sửa được kiểm soát bằng khóa cấp hàng. Trái lại, một số thao tác DDL có thể cần khóa cấp bảng mạnh và phải chờ các transaction đang đọc/ghi. Đó là lý do migration schema cần đánh giá thời gian giữ khóa và hoạt động đang chạy.

Chỉ dùng khóa cấp bảng mạnh khi nghiệp vụ/thao tác quản trị thực sự cần. Tránh biến một kiểm tra trên một bản ghi thành khóa toàn bảng vì dễ làm giảm thông lượng và tăng độ trễ hệ thống.

### 3.3. Khóa khoảng, khóa khe và khóa dự đoán (*range/gap/predicate*)

Các truy vấn theo điều kiện nhiều khi cần bảo vệ **tập hàng có thể xuất hiện**, không chỉ các hàng đã tồn tại. Ví dụ:

```sql
SELECT id FROM reservations
WHERE room_id = 7
  AND start_at < :requested_end
  AND end_at > :requested_start;
```

Nếu kết quả hiện tại rỗng, một giao dịch khác vẫn có thể thêm đặt phòng trùng thời gian. Khóa cấp hàng trên "không hàng nào" không bảo vệ được tính không chồng lấn.

DBMS dùng các cơ chế khác nhau:

- **MySQL/InnoDB:** các *locking read* và thao tác ghi có thể dùng **record locks**, **gap locks** hoặc **next-key locks** trên chỉ mục, phụ thuộc điều kiện truy vấn, chỉ mục, mức cô lập và loại thao tác. Ở `REPEATABLE READ`, truy vấn phạm vi thường có phạm vi khóa lớn hơn một hàng đơn lẻ; tìm chính xác trên chỉ mục unique với đủ cột có thể chỉ khóa record tương ứng. Chỉ mục và kế hoạch truy vấn có ảnh hưởng đáng kể.
- **SQL Server:** có thể sử dụng khóa **key-range** trong những điều kiện/mức cô lập phù hợp, chẳng hạn `SERIALIZABLE` với chỉ mục phù hợp; hệ thống còn có thể khóa trang, bảng hoặc thực hiện *lock escalation*. Các gợi ý `ROWLOCK`, `UPDLOCK`, `HOLDLOCK` cần được hiểu theo ngữ nghĩa SQL Server, không chuyển trực tiếp thành cú pháp PostgreSQL.
- **PostgreSQL:** `SELECT ... FOR UPDATE` không tự động tạo gap lock để chặn mọi insert có thể thỏa điều kiện trong tương lai. `SERIALIZABLE` dùng **Serializable Snapshot Isolation (SSI)** với *predicate locks/SIREAD* để theo dõi phụ thuộc đọc–ghi và phát hiện lịch thực thi không tuần tự hóa được; các khóa này **không hoạt động như khóa chặn insert tức thì**, mà có thể khiến transaction bị hủy với lỗi serialization.

Vì thế, **"khóa một truy vấn" không phải khái niệm đồng nhất giữa các DBMS**. Phải chỉ rõ khóa hàng hiện có, vùng chỉ mục, hay bất biến của cả tập dữ liệu; không suy luận từ việc SQL trông giống nhau.

### 3.4. Khóa ở tầng ứng dụng và advisory locks

PostgreSQL hỗ trợ **advisory locks** theo khóa do ứng dụng định nghĩa (ví dụ một số nguyên đại diện cho một tài nguyên logic). Đây là cách phối hợp công việc không khớp trực tiếp với một hàng, nhưng DB **không tự buộc mọi câu `INSERT/UPDATE` tôn trọng advisory lock**. Mọi code path liên quan phải cùng tuân thủ quy ước.

Phân biệt advisory lock theo **session** và theo **transaction**: khóa theo session có thể tồn tại sau commit, đặc biệt nguy hiểm nếu trả connection vào pool mà không giải phóng. Nếu dùng transaction-scoped advisory lock, hãy xác định khóa được cấp và giải phóng trong ranh giới giao dịch thích hợp. Khi cần bảo vệ tính duy nhất hoặc ràng buộc dữ liệu, ưu tiên **constraint tại DB** thay vì chỉ dựa vào một khóa quy ước ở ứng dụng.

## 4. Các chế độ khóa hàng thường gặp trong PostgreSQL

PostgreSQL có nhiều mức khóa hàng phục vụ các tình huống khác nhau:

| Cú pháp | Ý nghĩa thực dụng | Tình huống thường gặp |
|---|---|---|
| `FOR UPDATE` | Khóa mạnh để bảo vệ hàng trước cập nhật/xóa; xung đột với các khóa hàng khác | Đọc–kiểm tra–ghi trên hàng sắp sửa |
| `FOR NO KEY UPDATE` | Khóa phục vụ cập nhật mà không thay đổi các cột khóa quan trọng; yếu hơn `FOR UPDATE` | Cập nhật thuộc tính thường, vẫn phối hợp với writer |
| `FOR SHARE` | Khóa đọc chia sẻ, ngăn những thay đổi hàng xung đột trong transaction | Cần dữ liệu tham chiếu ổn định trước thao tác khác |
| `FOR KEY SHARE` | Khóa chia sẻ nhẹ hơn, chủ yếu bảo vệ giá trị khóa khỏi bị xóa/thay đổi theo cách ảnh hưởng tham chiếu | Cơ chế liên quan tham chiếu khóa ngoại và khóa định danh |

Các mode có **ma trận tương thích riêng**. Ví dụ, một `FOR KEY SHARE` trên hàng có thể cùng tồn tại với một cập nhật không thay đổi khóa ở mode `FOR NO KEY UPDATE`, trong khi `FOR UPDATE` mạnh hơn và xung đột với `FOR KEY SHARE`. Không khái quát tất cả `FOR ...` thành "độc quyền".

Chẳng hạn, khi cập nhật hàng trong PostgreSQL, DB thường dùng mức khóa hàng tương ứng với việc có thay đổi cột khóa được dùng bởi chỉ mục unique đủ điều kiện hay không; `DELETE` có mức mạnh hơn. Các ràng buộc khóa ngoại có thể kéo theo khóa ở **bảng hoặc hàng được tham chiếu** mà truy vấn SQL của ứng dụng không thể hiện rõ. Khi phân tích tranh chấp, phải xem cả những khóa DB tự lấy để duy trì tính toàn vẹn.

## 5. Phạm vi bị khóa không tự động bằng phạm vi nghiệp vụ

### 5.1. Chọn đúng hàng trong truy vấn có `JOIN`

Giả sử cần khóa hàng tồn kho, đồng thời đọc tên sản phẩm:

```sql
SELECT i.product_id, i.available, p.name
FROM inventory AS i
JOIN products AS p ON p.id = i.product_id
WHERE i.product_id = 10
FOR UPDATE OF i;
```

`FOR UPDATE OF i` trong PostgreSQL giới hạn **các hàng được yêu cầu khóa cập nhật** vào bảng có alias `i`; không tự thêm row-level `FOR UPDATE` trên hàng `products p`. Nếu dùng `FOR UPDATE` không chỉ rõ bảng đích, PostgreSQL có thể lấy khóa hàng trên các bảng được phép khóa trong truy vấn. Đây là một cách tránh khóa rộng không cần thiết khi `JOIN` chỉ để lấy thông tin tham khảo.

Đừng hiểu `OF i` có nghĩa toàn hệ thống chỉ có đúng một khóa: vẫn có **khóa cấp bảng**, khóa do ràng buộc và những khóa khác mà kế hoạch thực thi cần. Nếu nghiệp vụ cũng yêu cầu khóa hàng `products`, phải mô hình hóa và khóa rõ phần đó.

### 5.2. Không có hàng để khóa

Mẫu kiểm tra rồi tạo có thể xảy ra race condition:

```sql
BEGIN;

SELECT id
FROM customer_profiles
WHERE customer_id = 42
FOR UPDATE;
-- Không có hàng -> không khóa được một hàng profile chưa tồn tại.

INSERT INTO customer_profiles(customer_id, display_name)
VALUES (42, 'Lan');

COMMIT;
```

Hai giao dịch có thể cùng thấy không có profile rồi cùng insert. Giải pháp cốt lõi là đặt `UNIQUE (customer_id)` và dùng `INSERT ... ON CONFLICT ...` theo hợp đồng nghiệp vụ. Nếu cần phối hợp nhiều bước trước khi tạo, có thể khóa **một hàng cha đã tồn tại** (ví dụ hàng `customers.id = 42`) theo quy ước chung, hoặc dùng `SERIALIZABLE` kèm retry. Không coi `SELECT ... FOR UPDATE` trên kết quả rỗng là bằng chứng đã bảo vệ tính duy nhất.

### 5.3. Bất biến trải nhiều hàng

Ví dụ hai bác sĩ phải có ít nhất một người trực. Mỗi giao dịch khóa **chỉ hàng của bác sĩ mình** rồi đọc cả danh sách:

```text
T1: thấy A và B đều trực -> khóa A -> chuyển A nghỉ
T2: thấy A và B đều trực -> khóa B -> chuyển B nghỉ
```

Nếu các lần đọc và ghi diễn ra dưới snapshot cho phép tình huống *write skew*, hai transaction có thể cùng commit và để lại **không ai trực**, dù từng hàng riêng lẻ đã được khóa đúng. Đối tượng cần bảo vệ ở đây là **bất biến của cả nhóm**, không chỉ một hàng. Các hướng giải quyết gồm khóa hàng đại diện cho nhóm, áp đặt ràng buộc dữ liệu phù hợp nếu mô hình cho phép, hoặc transaction `SERIALIZABLE` với xử lý retry đúng cách. Khi khóa nhiều hàng, bảo đảm mọi đường ghi tuân thủ cùng quy ước.

Một câu hỏi thiết kế có ích là: **"Nếu một transaction khác sửa hoặc thêm tài nguyên nào, quyết định của transaction hiện tại sẽ sai?"** Câu trả lời giúp xác định tập tài nguyên hoặc ràng buộc thật sự phải bảo vệ.

## 6. Ví dụ đầy đủ: đặt hàng với khóa bi quan

Tạo bảng tồn kho:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available  INTEGER NOT NULL CHECK (available >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO inventory(product_id, available) VALUES (10, 5);
INSERT INTO inventory(product_id, available) VALUES (11, 7);
```

**Giao dịch T1, kết nối A:**

```sql
BEGIN;

SELECT available
FROM inventory
WHERE product_id = 10
FOR UPDATE;
-- Trả về 5, giữ row lock tới khi kết thúc transaction.

UPDATE inventory
SET available = available - 4,
    updated_at = now()
WHERE product_id = 10 AND available >= 4;
-- Kiểm tra số hàng UPDATE là 1.

-- Giữ transaction mở trong khi chạy bước T2.
```

**Giao dịch T2, kết nối B:**

```sql
BEGIN;

SELECT available
FROM inventory
WHERE product_id = 10
FOR UPDATE;
-- Chờ T1 vì hàng này đang bị khóa xung đột.
```

**Quay lại kết nối A:**

```sql
COMMIT;
```

Khi T1 commit, kết nối B tiếp tục, nhận `available = 1` trong điều kiện minh họa PostgreSQL `READ COMMITTED`. T2 không thể đặt mua 4 đơn vị và phải kết thúc transaction, ví dụ:

```sql
ROLLBACK;
```

Sơ đồ thời gian:

```mermaid
sequenceDiagram
    participant A as T1 / Connection A
    participant DB as PostgreSQL
    participant B as T2 / Connection B
    A->>DB: BEGIN; SELECT inventory(10) FOR UPDATE
    DB-->>A: available=5; giữ khóa
    A->>DB: UPDATE available = 1
    B->>DB: BEGIN; SELECT inventory(10) FOR UPDATE
    Note over B,DB: T2 chờ row lock
    A->>DB: COMMIT
    Note over DB: Nhả khóa T1
    DB-->>B: available=1
    B->>DB: ROLLBACK
```

**Điều gì được bảo vệ?** Hàng `inventory.product_id = 10` trong transaction của A, và sau đó hàng đó trong transaction của B. Không có lý do mặc định để khóa các sản phẩm khác. Một giao dịch cập nhật `product_id = 11` có thể chạy song song nếu không có khóa hoặc ràng buộc khác gây xung đột.

**Điều gì không được bảo vệ?** Tác dụng ngoài DB như gọi cổng thanh toán, gửi email, phát thông điệp, hoặc các bất biến liên quan một nhóm sản phẩm không được bao phủ bởi tập hàng đã khóa. Thiết kế API cần phối hợp transaction với idempotency/outbox nếu có thao tác bên ngoài DB.

## 7. Khi có nhiều tài nguyên: khóa theo thứ tự cố định

Ví dụ chuyển tiền giữa tài khoản 101 và 202 yêu cầu kiểm tra số dư nguồn và cập nhật cả hai tài khoản. Để giảm deadlock, mọi nơi thực hiện chuyển tiền nên khóa các hàng **theo thứ tự định danh tăng dần** bất kể hướng chuyển:

```text
Trước khi chuyển 101 -> 202: khóa 101, rồi 202
Trước khi chuyển 202 -> 101: vẫn khóa 101, rồi 202
```

Một cách thực thi đơn giản, dễ xác minh là lấy từng khóa theo ID đã sắp xếp ngay trong cùng transaction:

```sql
BEGIN;

SELECT balance FROM accounts WHERE id = 101 FOR UPDATE;
SELECT balance FROM accounts WHERE id = 202 FOR UPDATE;

-- Kiểm tra cả hai hàng đều có, số dư đủ và mọi bất biến khác.
-- Thực hiện UPDATE tài khoản nguồn/đích rồi COMMIT.
```

Nếu hai bên chuyển theo hai hướng ngược nhau nhưng cùng tuân thủ thứ tự, một bên sẽ chờ trên tài khoản 101 trước khi lấy khóa 202; tránh kiểu mỗi giao dịch giữ một tài khoản rồi chờ tài khoản của bên kia. **Thứ tự nhất quán giảm nguy cơ deadlock, không loại bỏ mọi deadlock**: khóa do foreign key, trigger, DDL hoặc đường ghi khác vẫn có thể tạo chu trình chờ.

Đừng kéo dài transaction để gọi dịch vụ ngoài mạng trong lúc đang giữ khóa trên số dư. Nên tách giai đoạn quyết định DB khỏi tác dụng bên ngoài và dùng cơ chế phối hợp giao dịch phù hợp; nếu nghiệp vụ bắt buộc phải làm nhiều bước, hãy đặt timeout và thiết kế phục hồi rõ ràng.

## 8. Chờ khóa, `NOWAIT`, `SKIP LOCKED` và timeout

Khi gặp khóa xung đột, mặc định nhiều câu lệnh có thể **đợi** cho đến khi khóa được thả hoặc xảy ra lỗi. Sự chờ này gây *lock contention* và tăng thời gian phản hồi. Có ba cách kiểm soát thường gặp trong PostgreSQL.

### 8.1. `NOWAIT`: phản hồi nhanh khi tài nguyên đang bận

```sql
BEGIN;

SELECT available
FROM inventory
WHERE product_id = 10
FOR UPDATE NOWAIT;

-- Nếu không lấy được row lock ngay, PostgreSQL trả lỗi thay vì đợi.
```

Phù hợp khi API cần trả trạng thái "đang bận, thử lại sau" hoặc chuyển yêu cầu sang hàng đợi. Trong PostgreSQL, `NOWAIT` của locking clause áp dụng cho khóa **cấp hàng**; khóa cấp bảng cần thiết vẫn được lấy theo cơ chế thông thường và có thể đợi. Vì vậy `NOWAIT` không đồng nghĩa mọi bước của câu SQL đều bảo đảm không chờ.

### 8.2. `SKIP LOCKED`: bỏ qua hàng đang bận khi xử lý hàng đợi

Ví dụ worker nhận một nhóm công việc đang chờ:

```sql
BEGIN;

SELECT id, payload
FROM jobs
WHERE state = 'PENDING'
ORDER BY created_at, id
LIMIT 10
FOR UPDATE SKIP LOCKED;

-- Đánh dấu chính các job đã chọn là PROCESSING trong cùng transaction.
-- Sau đó COMMIT nhanh để worker khác nhận job khác.
```

`SKIP LOCKED` cho phép nhiều worker chọn các hàng khác nhau mà không cùng đợi một hàng đang bị khóa. Nhưng nó cố ý cung cấp **góc nhìn thiếu các hàng đang bận**, nên không thích hợp cho báo cáo tổng hợp, đếm chính xác hoặc xử lý cần thứ tự toàn cục tuyệt đối. Việc phân phối công việc vẫn cần trạng thái, lease/timeout phục hồi job bị bỏ dở và idempotency của handler; khóa hàng sẽ được nhả sau commit và không thay thế cơ chế khôi phục job.

Nếu có nhiều worker, `ORDER BY` làm rõ thứ tự ưu tiên ở mức có thể, nhưng một job cũ đang bị khóa có thể bị bỏ qua nhiều lần. Hãy kiểm soát starvation và thử lại job lỗi; đừng suy ra `SKIP LOCKED` đảm bảo fairness.

### 8.3. Giới hạn thời gian chờ

PostgreSQL hỗ trợ `lock_timeout` để dừng câu lệnh khi chờ khóa quá lâu và `statement_timeout` để giới hạn tổng thời gian câu lệnh. Trong transaction, có thể cấu hình tạm thời:

```sql
BEGIN;

SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '3s';

SELECT available
FROM inventory
WHERE product_id = 10
FOR UPDATE;

-- Kiểm tra kết quả, tiếp tục và COMMIT hoặc ROLLBACK.
```

Nếu một statement bị lỗi timeout trong transaction PostgreSQL, transaction thường vào trạng thái failed cho đến khi rollback hoặc xử lý savepoint thích hợp. Không coi timeout là chứng cứ rằng thao tác nghiệp vụ không bao giờ có hiệu lực nếu timeout xảy ra gần ranh giới commit hoặc nếu có tác dụng ngoài DB; cần phân loại theo giai đoạn và kiểm chứng trạng thái.

## 9. Chọn khóa bi quan hay `UPDATE` nguyên tử?

Không phải cứ có tranh chấp là nên thêm một câu `SELECT ... FOR UPDATE`. Với một hàng và điều kiện đơn giản, có thể đưa bất biến thẳng vào SQL:

```sql
UPDATE inventory
SET available = available - :quantity,
    updated_at = now()
WHERE product_id = :product_id
  AND available >= :quantity
RETURNING available;
```

Với PostgreSQL, trong transaction ở `READ COMMITTED`, câu `UPDATE` phối hợp khóa trên hàng và đánh giá điều kiện trên phiên bản phù hợp khi gặp cập nhật đồng thời. Nếu `quantity > 0` đã được kiểm tra và câu lệnh trả về `0` hàng, nghiệp vụ không được coi là trừ kho thành công. Mô hình này giảm một vòng đọc riêng và tránh khoảng thời gian giữa đọc và ghi.

| Cách tiếp cận | Khi phù hợp | Giới hạn cần nhớ |
|---|---|---|
| `UPDATE ... WHERE` nguyên tử | Bất biến diễn đạt được trong một câu ghi trên hàng hoặc tập tài nguyên thích hợp | Phải kiểm tra affected rows; nhiều hàng/bảng có thể cần transaction và ràng buộc bổ sung |
| `SELECT ... FOR UPDATE` rồi ghi | Cần đọc hiện trạng để thực hiện nhiều bước nghiệp vụ có quan hệ trước khi ghi | Tăng thời gian giữ khóa, có thể gây chờ và deadlock |
| Optimistic locking (`version`) | Ít tranh chấp, cần phát hiện dữ liệu đổi giữa đọc và ghi | Khi version lệch phải đọc lại và tính toán lại quyết định, không ghi đè mù quáng |
| `SERIALIZABLE` + retry | Bất biến nhiều hàng/range khó biểu diễn bằng khóa cục bộ | Có thể phát sinh lỗi serialization; phải retry toàn bộ transaction |

Ví dụ optimistic locking:

```sql
UPDATE documents
SET content = :new_content,
    version = version + 1
WHERE id = :document_id
  AND version = :version_read_before;
```

Nếu không có hàng được cập nhật, caller phải xử lý xung đột phiên bản. Khóa bi quan và optimistic locking không đối lập tuyệt đối: có hệ thống dùng điều kiện ghi nguyên tử, transaction lock và version cùng nhau ở những ranh giới khác nhau. Chọn công cụ theo **bất biến, tần suất tranh chấp, độ dài transaction và chi phí retry**.

## 10. Chỉ mục và điều kiện truy vấn ảnh hưởng diện khóa thực tế

Chỉ mục thường giúp tìm nhanh tài nguyên phải khóa, nhưng tác động của nó còn phụ thuộc DBMS:

1. **PostgreSQL:** một truy vấn `SELECT ... FOR UPDATE` có thể dùng chỉ mục để tìm hàng nhanh hơn và giảm thời gian xử lý. Tuy nhiên, phạm vi **row locks** chủ yếu liên quan đến hàng được khóa bởi truy vấn, không thể suy ra chỉ vì dùng `Seq Scan` là PostgreSQL đã khóa cập nhật **mọi hàng đã quét**. Các khóa cấp bảng và ràng buộc vẫn có thể ảnh hưởng khác.
2. **InnoDB:** vì khóa thường gắn với **index records**, việc thiếu chỉ mục phù hợp cho locking read hoặc `UPDATE` phạm vi có thể khiến hệ thống khóa nhiều bản ghi/vùng khóa hơn dự kiến. Một truy vấn tìm một đối tượng nghiệp vụ nhưng phải quét nhiều vùng chỉ mục có thể làm giảm mạnh tính đồng thời. Đây là lý do nên kiểm tra index và execution plan trên MySQL khi phân tích lock contention.
3. **SQL Server:** kế hoạch truy cập, hints, key-range locks và lock escalation có thể làm phạm vi khóa trở nên rộng hơn, tới mức trang hoặc bảng. Điều này khác mô hình thông thường của PostgreSQL, nơi không tự thực hiện lock escalation từ row locks sang table locks theo cùng cách.

Ngay cả với chỉ mục tốt, một transaction `FOR UPDATE` hàng tồn kho nhưng giữ khóa trong lúc gọi API bên ngoài 10 giây vẫn tạo nút thắt. **Giảm thời gian giữ khóa** thường hiệu quả hơn chỉ tinh chỉnh cú pháp truy vấn.

Đối với truy vấn theo khoảng và nghiệp vụ chống xuất hiện hàng mới (chẳng hạn đặt chỗ không chồng lấn), không lấy việc "đã có index và `FOR UPDATE`" làm bằng chứng đủ. Xác định **phantom/insert race** và thêm constraint hoặc chọn mức cô lập phù hợp. PostgreSQL có thể áp dụng `EXCLUDE` constraint cho một số ràng buộc khoảng thời gian nếu mô hình dữ liệu và toán tử thích hợp.

## 11. Dùng khóa bi quan trong Java/JDBC

Ở JDBC, ranh giới transaction phải rõ ràng. Nếu `autoCommit=true`, câu `SELECT ... FOR UPDATE` có thể kết thúc transaction và nhả khóa ngay sau chính statement đó, **trước khi ứng dụng chạy câu `UPDATE` kế tiếp**. Vì vậy muốn bảo vệ cả quá trình đọc–kiểm tra–ghi, cần dùng cùng connection với `autoCommit=false`.

Ví dụ giao dịch đặt mua sản phẩm, với số lượng được xác thực dương trước khi ghi:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class InventoryService {
    private final DataSource dataSource;

    public InventoryService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean reserve(long productId, int quantity) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int available;
                String select = "SELECT available FROM inventory " +
                        "WHERE product_id = ? FOR UPDATE";
                try (PreparedStatement statement = connection.prepareStatement(select)) {
                    statement.setLong(1, productId);
                    try (ResultSet result = statement.executeQuery()) {
                        if (!result.next()) {
                            connection.rollback();
                            return false;
                        }
                        available = result.getInt("available");
                    }
                }

                if (available < quantity) {
                    connection.rollback();
                    return false;
                }

                String update = "UPDATE inventory SET available = available - ? " +
                        "WHERE product_id = ? AND available >= ?";
                try (PreparedStatement statement = connection.prepareStatement(update)) {
                    statement.setInt(1, quantity);
                    statement.setLong(2, productId);
                    statement.setInt(3, quantity);
                    if (statement.executeUpdate() != 1) {
                        throw new SQLException("Inventory update did not affect one row");
                    }
                }

                connection.commit();
                return true;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
```

Ví dụ này minh họa khóa trên **một hàng** và câu cập nhật có điều kiện bảo vệ thêm bất biến. Mã production cần có chính sách rõ ràng cho **lỗi phát sinh tại `commit()`**: nếu kết nối đứt lúc commit, `rollback()` hoặc exception không chứng minh DB chưa commit. Với nghiệp vụ có tác dụng không được lặp, hãy gắn operation ID/idempotency vào dữ liệu và đối soát kết quả trước khi retry. Đồng thời đặt timeout, xử lý deadlock và trả connection về pool đúng hợp đồng; đừng giữ transaction trong khi gọi dịch vụ ngoài DB.

Ví dụ code dùng Java và PostgreSQL JDBC phổ biến; cú pháp `FOR UPDATE` và phương thức xác định khóa phải được điều chỉnh nếu DBMS khác. Đặt `lock_timeout`/statement timeout phù hợp nếu yêu cầu độ trễ chặt chẽ.

## 12. Spring/JPA: `PESSIMISTIC_WRITE` và phạm vi transaction

JPA cung cấp `LockModeType.PESSIMISTIC_WRITE` để yêu cầu khóa bi quan khi tải entity:

```java
public interface InventoryRepository extends JpaRepository<Inventory, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.productId = :id")
    Optional<Inventory> findLockedById(@Param("id") Long id);
}

@Service
public class InventoryApplicationService {
    private final InventoryRepository repository;

    public InventoryApplicationService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(long productId, int quantity) {
        if (quantity <= 0) throw new IllegalArgumentException("invalid quantity");
        Inventory item = repository.findLockedById(productId).orElseThrow();
        if (item.getAvailable() < quantity) {
            throw new IllegalStateException("insufficient inventory");
        }
        item.setAvailable(item.getAvailable() - quantity);
    }
}
```

Đoạn code giả định các kiểu `Inventory`, `JpaRepository`, `Lock`, `Query`, `Param`, `Service` và `Transactional` đã được khai báo/import phù hợp trong dự án. Với Hibernate trên PostgreSQL, khóa bi quan ghi thường được triển khai bằng `SELECT ... FOR UPDATE` hoặc biến thể tương ứng, nhưng **SQL thực tế và phạm vi khóa** phụ thuộc provider, dialect, truy vấn join/fetch và cấu hình. Hãy kiểm tra SQL sinh ra khi hành vi khóa ảnh hưởng tính đúng đắn.

Các lưu ý cần kiểm chứng:

- **Transaction phải đang mở** khi lấy lock và còn mở tới lúc xử lý xong quyết định ghi. Nếu gọi repository mà không có transaction thích hợp, JPA có thể báo lỗi hoặc khóa không bảo vệ được phần việc tiếp theo.
- **Không mặc định mọi lời gọi `@Transactional` đều tạo transaction mới**: propagation có thể khiến method tham gia transaction bên ngoài; thời gian giữ khóa khi đó dài hơn thời gian chạy method con.
- **Self-invocation và proxy:** lời gọi một phương thức `@Transactional` qua `this.method()` trong cùng bean có thể bỏ qua interceptor ở cấu hình proxy mặc định của Spring; cần thiết kế ranh giới service rõ ràng.
- **Tránh khóa rộng do join/fetch:** câu truy vấn ORM có thể khóa các hàng từ nhiều bảng hoặc phát nhiều câu SQL. Nếu chỉ cần khóa `inventory`, truy vấn riêng theo khóa chính thường dễ kiểm soát hơn.
- **Timeout và retry:** `PESSIMISTIC_WRITE` không loại bỏ deadlock, mất kết nối hoặc serialization failure. Xử lý lỗi bằng transaction mới; không retry lặp vô hạn ở bên trong transaction đã lỗi.

Chú ý `PESSIMISTIC_WRITE` **khác** `@Version` của optimistic locking. `@Version` thường bảo vệ cập nhật bằng điều kiện phiên bản; nó không nhất thiết giữ khóa trên hàng ngay từ lúc đọc. Hai cơ chế có thể dùng bổ sung nhau nhưng không nên nhầm bảo đảm.

## 13. Deadlock: khi mỗi transaction giữ khóa mà bên kia cần

Deadlock xuất hiện nếu tồn tại một chu trình chờ khóa. Ví dụ:

```text
T1: khóa account 101
T2: khóa account 202
T1: đợi khóa account 202  (T2 đang giữ)
T2: đợi khóa account 101  (T1 đang giữ)

T1 đợi T2, T2 đợi T1 -> deadlock
```

PostgreSQL thường phát hiện deadlock sau một khoảng thời gian kiểm tra và hủy một trong các giao dịch, báo SQLSTATE `40P01`. Điều này không tự động có nghĩa toàn bộ yêu cầu nghiệp vụ đã hoàn thành. Ứng dụng cần rollback transaction bị lỗi và nếu thao tác cho phép, thử lại **toàn bộ công việc đọc–quyết định–ghi** bằng transaction mới, có giới hạn số lần thử và backoff.

Các cách giảm deadlock và lock contention:

1. **Khóa theo thứ tự cố định** giữa mọi đường ghi có liên quan.
2. **Giữ transaction ngắn**; tính toán hoặc gọi dịch vụ ngoài DB ngoài thời gian giữ khóa khi có thể.
3. **Khóa đúng tài nguyên**; tránh khóa dư vì join, truy vấn phạm vi quá rộng hoặc thiếu chỉ mục phù hợp với DBMS.
4. **Có timeout và retry có kiểm soát**; phân biệt lỗi tranh chấp với lỗi đầu vào hoặc dữ liệu không hợp lệ.
5. **Dùng ràng buộc tại DB** cho tính duy nhất, khóa ngoại và các bất biến có thể mô tả trực tiếp, thay vì tin hoàn toàn vào quy ước khóa trong code.

Không sửa deadlock bằng cách đặt timeout cực dài. Timeout quá dài khiến các request và connection bị giữ lại, tăng áp lực lên pool, gây lỗi dây chuyền cho những request khác.

## 14. Quan sát và kiểm chứng phạm vi khóa

Với PostgreSQL, bắt đầu bằng **hai kết nối độc lập** trong môi trường thử nghiệm, dùng lịch thực thi có kiểm soát để tái hiện chờ khóa. Các công cụ chính:

```sql
-- Quan sát các khóa của phiên và giao dịch (quyền truy cập tùy vai trò).
SELECT pid, locktype, mode, granted, relation::regclass AS relation_name
FROM pg_locks
WHERE relation IS NOT NULL
ORDER BY pid, relation_name, mode;

-- Quan sát ai đang bị chặn và bởi phiên nào.
SELECT pid, state, wait_event_type, wait_event,
       pg_blocking_pids(pid) AS blocking_pids,
       query
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
```

**Giới hạn khi đọc `pg_locks`:** row-level locks của PostgreSQL thường được ghi trong tuple và không phải mọi hàng đang bị khóa đều hiện thành một dòng `tuple` trong `pg_locks`. Một giao dịch đang chờ khóa hàng có thể biểu hiện là chờ `transactionid`. Vì thế đừng suy luận "không thấy tuple lock nghĩa là không có row lock". Phối hợp `pg_stat_activity`, `pg_blocking_pids`, log chờ khóa và tái hiện hành vi để xác định nguyên nhân.

Trong hệ thống thật, theo dõi **lock wait time**, số request timeout, deadlock, transaction dài, số connection đang chờ, thông lượng và tác động đến p95/p99 latency. PostgreSQL có thể ghi log chờ khóa khi bật `log_lock_waits` với ngưỡng `deadlock_timeout` thích hợp; nên cấu hình theo môi trường và lưu ý dữ liệu nhạy cảm có thể có trong nội dung câu SQL.

Khi dùng `EXPLAIN (ANALYZE, BUFFERS)` để xem truy vấn, nhớ rằng `ANALYZE` **thực thi truy vấn**. Execution plan giúp phân tích cách truy cập dữ liệu, nhưng **không phải bản đồ đầy đủ của mọi khóa**. Muốn xác minh phạm vi tranh chấp, cần một giao dịch giữ khóa, giao dịch khác thử thao tác lên hàng cùng/hàng khác và quan sát wait/timeout; chỉ nhìn `Index Scan` không đủ.

### Thử nghiệm tối thiểu nên thực hiện

| Lượt thử | Connection A | Connection B | Kỳ vọng (PostgreSQL `READ COMMITTED`) |
|---|---|---|---|
| 1 | `BEGIN; SELECT ... WHERE product_id=10 FOR UPDATE` | `BEGIN; UPDATE` hàng 10 | B đợi A hoặc gặp timeout; sau `COMMIT` của A, B được tiếp tục theo trạng thái thực tế |
| 2 | Mở transaction mới và khóa lại hàng 10 | `SELECT` thông thường hàng 10 trên connection mới | B thường đọc được phiên bản đã commit phù hợp, không phải đợi row lock của A |
| 3 | Mở transaction mới và khóa lại hàng 10 | `UPDATE` hàng 11 đã tồn tại trên connection mới | B thường cập nhật được hàng 11 nếu không có xung đột khác |

**Mỗi dòng là một lượt thử độc lập**: kết thúc transaction ở cả hai connection, reset fixture nếu cần, rồi bắt đầu lượt tiếp theo. Đặc biệt không cố gửi lệnh mới trên một connection còn đang bị chặn trong lúc chờ khóa. Lượt thử số 3 yêu cầu fixture có hàng `product_id = 11` như ở phần 6.

Muốn kiểm thử `SKIP LOCKED`, dùng một bảng `jobs` và hai worker cùng transaction riêng. Muốn kiểm thử race khi **không có hàng**, cho hai giao dịch cùng kiểm tra thiếu profile rồi thử insert, kiểm tra `UNIQUE` và cách xử lý `ON CONFLICT`. Các thí nghiệm phải chủ động đồng bộ thứ tự câu lệnh; không dựa vào `sleep` để suy luận tính đúng đắn.

## 15. Các nhầm lẫn thường gặp

- **"`SELECT ... FOR UPDATE` khóa toàn bảng."** Không mặc nhiên. Nó lấy row locks trên các hàng được chọn và table-level lock ở mode tương ứng; nhiều hàng có thể bị khóa nếu truy vấn trả nhiều hàng, còn DDL có thể bị ảnh hưởng bởi table lock.
- **"Khóa hàng nghĩa là mọi người khác không đọc được hàng."** Không đúng với `SELECT` thông thường của PostgreSQL dùng MVCC; người đọc có thể quan sát phiên bản đã commit phù hợp.
- **"Không tìm thấy hàng thì `FOR UPDATE` đã khóa khả năng tạo hàng mới."** Không đúng đối với row lock thông thường của PostgreSQL; cần constraint, khóa một tài nguyên đại diện hoặc cơ chế bảo vệ tập điều kiện.
- **"Chỉ cần khóa từng hàng là mọi bất biến nhiều hàng đều an toàn."** Không đúng nếu bỏ sót hàng/tập dữ liệu trong bất biến; write skew và insert race đòi hỏi giải pháp rộng hơn.
- **"`NOWAIT` hoặc `SKIP LOCKED` đảm bảo thao tác luôn tức thì hoặc công bằng."** Không đúng; còn khóa cấp bảng, I/O, tính sẵn có của job và nguy cơ starvation.
- **"Có chỉ mục tức là DB chỉ khóa đúng một record."** Không thể kết luận giữa các hệ quản trị; đặc biệt InnoDB có thể khóa khoảng hoặc nhiều index records.
- **"Đã dùng `@Transactional` thì có thể giữ khóa trong lúc gọi service ngoài."** Có thể làm, nhưng thường gây chờ dài và vẫn không tạo tính nguyên tử cho dịch vụ bên ngoài.
- **"Rollback sau exception luôn chứng minh chưa có tác dụng."** Phải phân biệt lỗi trước commit với lỗi mất phản hồi khi commit; idempotency và đối soát vẫn quan trọng.

## 16. Cách chọn phạm vi khóa theo nghiệp vụ

Khi thiết kế thao tác persistence có tranh chấp, hãy trả lời lần lượt:

1. **Bất biến cần giữ là gì?** Ví dụ `available >= 0`, "không có hai profile cùng customer" hay "ít nhất một bác sĩ trực".
2. **Những tác nhân nào có thể làm bất biến sai?** Một `UPDATE` trên hàng hiện tại, `INSERT` hàng mới, `DELETE`, thay đổi nhiều hàng hay dịch vụ ngoài DB?
3. **Tập tài nguyên nào cần được bảo vệ?** Một hàng hiện có, nhiều hàng đã biết ID, hàng đại diện của nhóm, hoặc tập kết quả theo phạm vi/điều kiện.
4. **DBMS và mức cô lập thực tế hỗ trợ gì?** Khóa hàng, key-range locks, predicate/SSI, constraint, `SERIALIZABLE`, `NOWAIT`, `SKIP LOCKED`?
5. **Cần giữ khóa trong bao lâu và khi không lấy được khóa thì sao?** Chọn transaction ngắn, thứ tự khóa, timeout, backoff, retry và phương án báo lỗi nghiệp vụ.
6. **Làm sao chứng minh hoạt động đúng?** Kiểm tra bằng ít nhất hai connection độc lập, lịch cạnh tranh có kiểm soát, bất biến sau commit và công cụ quan sát khóa.

Khóa bi quan hiệu quả khi **mỗi transaction khóa đủ tài nguyên cần thiết, ở mức phù hợp và trong thời gian ngắn nhất hợp lý**. Trong Java, điều đó cần được thể hiện nhất quán qua transaction boundary, SQL hoặc ORM, ràng buộc tại DB và chính sách xử lý lỗi. Chọn sai phạm vi khóa có thể vừa làm nghẽn hệ thống vừa **không bảo vệ được bất biến**; chọn đúng giúp các giao dịch có liên quan được phối hợp an toàn mà vẫn giữ khả năng xử lý song song cho dữ liệu không tranh chấp.
