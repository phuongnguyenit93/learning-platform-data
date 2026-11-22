# Ưu tiên ràng buộc cơ sở dữ liệu cho bất biến có thể biểu diễn trực tiếp

Một hệ thống giao dịch thường có những quy tắc mà dữ liệu phải luôn tuân thủ: mã định danh không được trùng, email phải duy nhất, đơn hàng phải tham chiếu đến khách hàng tồn tại, số dư không được âm hoặc mỗi ghế chỉ được đặt một lần. Những quy tắc như vậy được gọi là **bất biến dữ liệu** (*data invariants*).

Khi một bất biến có thể biểu diễn trực tiếp bằng ràng buộc của cơ sở dữ liệu, hãy ưu tiên để cơ sở dữ liệu thực thi nó. `PRIMARY KEY`, `UNIQUE`, `NOT NULL`, `CHECK`, `FOREIGN KEY` và các ràng buộc hoặc chỉ mục chuyên biệt giúp bảo vệ dữ liệu ngay tại nơi lưu trữ, kể cả khi nhiều transaction hoặc nhiều ứng dụng cùng ghi.

Kiểm tra trong ứng dụng vẫn hữu ích để đưa ra thông báo sớm và cải thiện trải nghiệm người dùng. Nhưng một câu `SELECT` kiểm tra trước khi `INSERT` không thể tự bảo đảm tính duy nhất khi hai transaction chạy đồng thời. Cả hai có thể cùng đọc rằng dữ liệu chưa tồn tại rồi cùng insert. Ràng buộc ở database là lớp bảo vệ cuối cùng cho bất biến mà database có thể kiểm tra một cách nguyên tử và đúng với ngữ nghĩa giao dịch.

## 1. Bất biến dữ liệu và nguồn bảo đảm

Bất biến là điều kiện phải đúng đối với trạng thái dữ liệu được chấp nhận. Ví dụ:

- Mỗi hàng trong `accounts` có một `id` duy nhất.
- Mỗi email đăng nhập chỉ thuộc về một tài khoản.
- Một đơn hàng phải tham chiếu đến khách hàng đang tồn tại.
- Số lượng tồn kho không được nhỏ hơn `0`.
- Một ghế trong một chuyến đi không được có hai lượt đặt đang hoạt động.
- Một bản ghi đang hoạt động trong một nhóm phải là duy nhất.

Nếu chỉ kiểm tra trong Java hoặc ở tầng API, mọi đường ghi phải nhớ thực hiện đúng cùng một logic. Một batch job, script quản trị, service mới hoặc câu SQL chạy trực tiếp có thể bỏ qua kiểm tra đó. Ràng buộc database được áp dụng cho các đường ghi đi qua database và có thể bảo vệ dữ liệu dù caller là ứng dụng nào.

Một cách phân chia trách nhiệm hữu ích:

| Lớp | Trách nhiệm |
|---|---|
| Giao diện/API | Kiểm tra đầu vào sớm, giải thích lỗi dễ hiểu, phản hồi nhanh. |
| Application/domain service | Thực thi quy trình nghiệp vụ, kiểm tra quyền, điều phối nhiều bước và quyết định hành động. |
| Database constraint | Từ chối trạng thái dữ liệu vi phạm bất biến mà schema có thể biểu diễn. |
| Transaction/concurrency control | Điều phối các thao tác đồng thời và bảo vệ những quy tắc phụ thuộc nhiều thao tác hoặc nhiều hàng. |

Các lớp này bổ sung cho nhau. Kiểm tra ở ứng dụng giúp người dùng biết vấn đề trước khi gửi dữ liệu; ràng buộc database bảo đảm kết quả cuối không phụ thuộc vào việc một caller có nhớ kiểm tra hay không.

## 2. Các ràng buộc cơ bản

### PRIMARY KEY

`PRIMARY KEY` xác định danh tính của mỗi hàng. Giá trị khóa chính phải duy nhất và không được `NULL`.

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);
```

Database tự tạo hoặc sử dụng một unique index phù hợp để bảo đảm không có hai hàng cùng `id`. Không cần chạy `SELECT` kiểm tra xem `id` đã tồn tại trước mỗi lần insert rồi mới tin rằng insert sẽ thành công; chính `PRIMARY KEY` xử lý cuộc đua giữa các transaction.

### UNIQUE

`UNIQUE` bảo đảm giá trị hoặc tổ hợp giá trị không trùng theo quy tắc của hệ quản trị:

```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    CONSTRAINT uq_users_email UNIQUE (email)
);
```

Nếu hai transaction đồng thời insert cùng một email, database phải điều phối xung đột trên unique key. Không thể để cả hai cùng commit một trạng thái vi phạm unique constraint.

Ràng buộc nhiều cột:

```sql
CREATE TABLE room_bookings (
    id BIGINT PRIMARY KEY,
    room_id BIGINT NOT NULL,
    booking_date DATE NOT NULL,
    slot_code VARCHAR(30) NOT NULL,
    CONSTRAINT uq_room_booking_slot
        UNIQUE (room_id, booking_date, slot_code)
);
```

Ràng buộc trên bảo đảm một phòng không có hai lượt đặt trùng cùng ngày và cùng slot. Nó biểu diễn một bất biến trực tiếp bằng các giá trị nằm trong cùng một hàng hoặc khóa duy nhất.

**Lưu ý về `NULL`:** cách `UNIQUE` xử lý nhiều giá trị `NULL` khác nhau giữa các hệ quản trị và tùy chọn của chúng. Nếu bất biến yêu cầu mọi hàng đều có giá trị, hãy khai báo `NOT NULL` rõ ràng thay vì dựa vào hành vi của unique constraint đối với `NULL`.

### NOT NULL

`NOT NULL` yêu cầu cột phải có giá trị:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL
);
```

Không nên chỉ kiểm tra `sku != null` trong Java. Một script hoặc service khác vẫn có thể insert `NULL`. `NOT NULL` bảo vệ trực tiếp điều kiện này.

`NOT NULL` khác với chuỗi rỗng hoặc chuỗi chỉ chứa khoảng trắng. Nếu nghiệp vụ không cho phép các giá trị đó, cần thêm kiểm tra phù hợp, ví dụ `CHECK (length(trim(name)) > 0)` ở hệ quản trị hỗ trợ cú pháp tương ứng, đồng thời kiểm tra quy tắc collation và Unicode nếu cần.

### CHECK

`CHECK` bảo đảm một biểu thức trên hàng thỏa điều kiện khi insert hoặc update:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(19, 2) NOT NULL,
    CONSTRAINT ck_accounts_balance_nonnegative
        CHECK (balance >= 0)
);
```

Nếu hai transaction cùng cập nhật một tài khoản, database không chấp nhận một trạng thái hàng có `balance < 0`. Ứng dụng có thể kiểm tra số dư trước để đưa ra thông báo thân thiện, nhưng `CHECK` bảo vệ điều kiện cuối cùng ở database.

Một điểm quan trọng của SQL là biểu thức `CHECK` thường được xem là hợp lệ khi kết quả là `TRUE` hoặc `UNKNOWN`; chỉ `FALSE` làm vi phạm constraint. Vì vậy, `CHECK (balance >= 0)` một mình không nhất thiết từ chối `NULL`. Muốn cột bắt buộc có giá trị và không âm, hãy kết hợp:

```sql
balance DECIMAL(19, 2) NOT NULL
    CHECK (balance >= 0)
```

`CHECK` phù hợp với bất biến trên chính hàng đó: số lượng không âm, ngày kết thúc không trước ngày bắt đầu, phần trăm nằm trong khoảng cho phép hoặc trạng thái thuộc một tập giá trị được chấp nhận.

```sql
CREATE TABLE promotions (
    id BIGINT PRIMARY KEY,
    starts_at TIMESTAMP NOT NULL,
    ends_at TIMESTAMP NOT NULL,
    discount_percent DECIMAL(5, 2) NOT NULL,
    CONSTRAINT ck_promotion_period CHECK (ends_at > starts_at),
    CONSTRAINT ck_promotion_discount
        CHECK (discount_percent > 0 AND discount_percent <= 100)
);
```

## 3. FOREIGN KEY bảo vệ quan hệ giữa các bảng

`FOREIGN KEY` bảo đảm giá trị tham chiếu phải khớp với khóa được tham chiếu, theo quy tắc `NULL` và hành động xóa/cập nhật đã khai báo.

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total DECIMAL(19, 2) NOT NULL CHECK (total >= 0),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

Không thể commit một đơn hàng tham chiếu đến `customer_id` không tồn tại. Nếu transaction khác đồng thời xóa khách hàng hoặc tạo khách hàng, database sẽ điều phối kiểm tra tham chiếu theo semantics của foreign key và transaction.

### Hành vi khi hàng cha bị xóa

Foreign key có thể khai báo hành vi khi hàng được tham chiếu bị xóa hoặc khóa được tham chiếu thay đổi. Các lựa chọn phổ biến:

| Hành vi | Ý nghĩa |
|---|---|
| `RESTRICT` / `NO ACTION` | Từ chối hoặc trì hoãn việc xóa/thay đổi nếu vẫn còn hàng con tham chiếu, tùy engine và thời điểm kiểm tra. |
| `CASCADE` | Xóa hoặc cập nhật các hàng con tương ứng. |
| `SET NULL` | Đặt cột tham chiếu của hàng con thành `NULL`; cột đó phải cho phép `NULL`. |
| `SET DEFAULT` | Đặt cột tham chiếu về giá trị mặc định; giá trị đó vẫn phải thỏa foreign key nếu có kiểm tra. |

Ví dụ:

```sql
FOREIGN KEY (customer_id)
REFERENCES customers(id)
ON DELETE RESTRICT
```

Chọn hành vi theo vòng đời dữ liệu. `CASCADE` hữu ích khi hàng con không có ý nghĩa độc lập với hàng cha, nhưng có thể xóa nhiều dữ liệu ngoài dự kiến nếu quan hệ được thiết kế sai. Với dữ liệu tài chính hoặc lịch sử đơn hàng, thường cần giữ lịch sử và ngăn xóa khách hàng đang được tham chiếu.

Foreign key không thay thế kiểm tra quyền truy cập. Nó chỉ bảo đảm tính toàn vẹn tham chiếu; người dùng có quyền tạo đơn hàng hay xem khách hàng vẫn là quyết định của ứng dụng hoặc lớp bảo mật tương ứng.

## 4. Bất biến duy nhất trong các tình huống đồng thời

Một lý do quan trọng để ưu tiên constraint là kiểm tra trước bằng truy vấn thông thường có race condition.

Giả sử hệ thống cần bảo đảm mỗi khách hàng chỉ có một subscription đang hoạt động. Cách triển khai chỉ dùng application check:

```text
T1: SELECT xem customer 42 đã có subscription ACTIVE chưa -> không
T2: SELECT xem customer 42 đã có subscription ACTIVE chưa -> không
T1: INSERT subscription ACTIVE
T2: INSERT subscription ACTIVE
T1: COMMIT
T2: COMMIT
```

Hai transaction có thể cùng thấy chưa tồn tại hàng. Nếu không có constraint phù hợp, cả hai có thể commit và tạo trạng thái trùng.

Với hệ quản trị hỗ trợ unique partial index, có thể biểu diễn trực tiếp:

```sql
CREATE UNIQUE INDEX uq_one_active_subscription_per_customer
ON subscriptions (customer_id)
WHERE status = 'ACTIVE';
```

Chỉ các hàng có `status = 'ACTIVE'` tham gia unique index. Khi hai transaction cùng insert subscription active cho một khách hàng, index bảo đảm không thể có hai hàng cùng thỏa điều kiện sau khi cả hai commit. Cú pháp partial index này có tính đặc thù theo hệ quản trị; cần kiểm tra tài liệu engine đang dùng.

Nếu hệ quản trị không hỗ trợ partial unique index, có thể cân nhắc mô hình hóa trạng thái active bằng một bảng liên kết riêng với `customer_id` là khóa chính hoặc unique, hoặc dùng một hàng điều phối/transaction locking phù hợp. Không nên giả định một truy vấn `NOT EXISTS` đơn lẻ bảo vệ được quy tắc khi có nhiều transaction.

### Duy nhất theo giá trị chuẩn hóa

Nếu email được xem là không phân biệt chữ hoa/chữ thường, `UNIQUE(email)` có thể không biểu diễn đúng quy tắc tùy collation. Một lựa chọn là lưu giá trị chuẩn hóa trong một cột riêng và đặt unique constraint lên cột đó:

```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    CONSTRAINT uq_users_email_normalized UNIQUE (email_normalized)
);
```

Ứng dụng hoặc database phải bảo đảm `email_normalized` được tính nhất quán từ email. Nếu có thể, dùng generated/computed column hoặc functional unique index theo hỗ trợ của engine để tránh hai đường ghi tạo giá trị chuẩn hóa khác nhau.

Không tự ý dùng `LOWER(email)` làm quy tắc chuẩn hóa cho mọi hệ thống mà chưa xác định chính sách Unicode, IDN, dấu cách và collation. Quy tắc định danh phải được thống nhất giữa đăng ký, đăng nhập, cập nhật và import dữ liệu.

## 5. Ràng buộc cho khoảng thời gian và các điều kiện chuyên biệt

Một số bất biến phức tạp hơn `UNIQUE` trên một cột nhưng vẫn có thể được database biểu diễn bằng constraint hoặc index chuyên biệt.

### Không cho phép hai lịch đặt chồng thời gian

Giả sử một phòng không được có hai booking giao nhau về thời gian. Kiểm tra bằng `SELECT` trước khi insert có thể gặp race: hai transaction cùng kiểm tra và không thấy booking của nhau.

Ở PostgreSQL, có thể dùng exclusion constraint với kiểu range:

```sql
-- Ví dụ PostgreSQL; cần extension btree_gist cho phép so sánh room_id
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_bookings (
    id BIGINT PRIMARY KEY,
    room_id BIGINT NOT NULL,
    during TSTZRANGE NOT NULL,
    CONSTRAINT ex_room_booking_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            during WITH &&
        )
);
```

Constraint này từ chối hai hàng có cùng `room_id` và khoảng `during` giao nhau. Đây là ví dụ theo PostgreSQL, không phải cú pháp SQL portable. Với hệ quản trị khác, có thể cần range lock, khóa điều phối, Serializable hoặc mô hình dữ liệu khác.

### Duy nhất có điều kiện

Quy tắc “mỗi nhóm chỉ có tối đa một bản ghi được đánh dấu mặc định” cũng có thể dùng unique partial index:

```sql
CREATE UNIQUE INDEX uq_one_default_address_per_customer
ON addresses (customer_id)
WHERE is_default = TRUE;
```

Index bảo vệ bất biến khi các transaction đồng thời đánh dấu hai địa chỉ khác nhau là mặc định cho cùng khách hàng. Nếu không có hỗ trợ partial index, có thể lưu `default_address_id` trên hàng customer và bảo đảm khóa ngoại phù hợp, hoặc dùng một cơ chế đồng bộ khác.

## 6. Ràng buộc database và các bất biến liên nhiều hàng

Không phải mọi quy tắc nghiệp vụ đều có thể viết thành một `CHECK` đơn giản. `CHECK` thông thường được thiết kế để kiểm tra biểu thức trên hàng đang được insert hoặc update. Nó không phải công cụ tổng quát để tính `SUM` trên bảng, đếm số hàng hoặc kiểm tra các hàng khác.

Ví dụ bất biến:

> Tổng số chỗ đã đặt cho một sự kiện không được vượt quá sức chứa của sự kiện.

Một ý tưởng viết `CHECK` dựa trên `SELECT SUM(...)` từ bảng booking thường không được hỗ trợ hoặc không an toàn trong ngữ nghĩa constraint của hệ quản trị. Ngay cả khi một trigger thực hiện truy vấn tổng, hai transaction có thể cùng đọc tổng cũ rồi cùng insert, dẫn đến write skew nếu trigger không khóa hoặc đồng bộ đúng cách.

Đối với bất biến liên hàng, hãy cân nhắc theo thứ tự:

1. Có thể biến quy tắc thành `UNIQUE`, `FOREIGN KEY`, `EXCLUDE` hoặc constraint được database hỗ trợ không?
2. Có thể biểu diễn tài nguyên cần kiểm soát bằng một hàng duy nhất và dùng cập nhật có điều kiện nguyên tử không?
3. Có thể dùng khóa hàng điều phối hoặc khóa phạm vi với đúng semantics của engine không?
4. Có cần mức `SERIALIZABLE` hoặc cơ chế phát hiện phụ thuộc tương đương không?
5. Nếu dùng trigger, trigger có xử lý cạnh tranh đồng thời và deadlock đúng cách không?

### Ví dụ giới hạn sức chứa

Giả sử sự kiện có `capacity = 100` và `reserved = 98`. Hai transaction cùng muốn đặt ba chỗ. Nếu cả hai cùng đọc `reserved = 98` rồi insert ba booking, tổng có thể thành `104`.

Một cách mô hình hóa là lưu bộ đếm `reserved` trên hàng sự kiện và cập nhật có điều kiện:

```sql
UPDATE events
SET reserved = reserved + 3
WHERE id = :eventId
  AND reserved + 3 <= capacity;
```

Database thực hiện phép kiểm tra và cập nhật trên cùng hàng. Chỉ transaction cập nhật thành công mới được tiếp tục tạo booking trong cùng transaction. Nếu số hàng cập nhật bằng `0`, sức chứa không đủ hoặc sự kiện không tồn tại. Có thể thêm:

```sql
CHECK (reserved >= 0 AND reserved <= capacity)
```

để bảo vệ miền giá trị của bộ đếm. Tuy nhiên, ứng dụng phải bảo đảm mọi đường tạo/hủy booking đều cập nhật `reserved` cùng transaction; nếu có đường ghi bỏ qua bộ đếm, dữ liệu tổng hợp có thể lệch so với chi tiết booking.

Một cách khác là dùng hàng booking và cơ chế khóa/Serializable bảo vệ toàn bộ tập booking. Lựa chọn phù hợp phụ thuộc lưu lượng, mô hình dữ liệu, độ chính xác cần thiết và khả năng của hệ quản trị.

## 7. Constraint có thể trì hoãn đến cuối transaction

Một số hệ quản trị hỗ trợ constraint có thể trì hoãn (*deferrable constraints*). Thay vì kiểm tra ngay sau từng câu lệnh, database kiểm tra ở thời điểm được chỉ định, thường là cuối transaction.

Điều này hữu ích khi một transaction cần đi qua trạng thái trung gian tạm thời vi phạm constraint nhưng trạng thái cuối vẫn hợp lệ.

Ví dụ đổi vị trí hai hàng trong một danh sách có ràng buộc duy nhất `(list_id, position)`. Nếu cập nhật hàng thứ nhất sang vị trí đang thuộc hàng thứ hai trước, unique constraint không trì hoãn có thể từ chối ngay. Một constraint có thể trì hoãn cho phép transaction thực hiện các bước đổi chỗ rồi kiểm tra trạng thái cuối khi commit.

Ví dụ PostgreSQL:

```sql
CREATE TABLE list_items (
    id BIGINT PRIMARY KEY,
    list_id BIGINT NOT NULL,
    position INTEGER NOT NULL,
    CONSTRAINT uq_list_item_position
        UNIQUE (list_id, position)
        DEFERRABLE INITIALLY DEFERRED
);
```

Có thể điều khiển thời điểm kiểm tra bằng `SET CONSTRAINTS` trong các hệ quản trị hỗ trợ. Không phải mọi loại constraint hoặc mọi engine đều hỗ trợ trì hoãn. Deferrable cũng không có nghĩa là bỏ kiểm tra; trạng thái cuối vẫn phải thỏa constraint khi transaction commit.

## 8. Constraint và kiểm tra trong ứng dụng nên phối hợp ra sao?

Một ứng dụng tốt thường kiểm tra ở nhiều thời điểm, với mục tiêu khác nhau.

**Trước khi ghi:** kiểm tra đầu vào để trả thông báo sớm, ví dụ email sai định dạng hoặc số lượng đặt vượt giới hạn mà người dùng nhập.

**Trong quy trình nghiệp vụ:** kiểm tra quyền, trạng thái, điều kiện nhiều bước và các chính sách không thể biểu diễn bằng constraint đơn giản.

**Tại database:** khai báo các bất biến cấu trúc và dữ liệu có thể thực thi trực tiếp. Database là nơi cuối cùng quyết định liệu trạng thái được commit có vi phạm constraint hay không.

Ví dụ với email:

```text
API nhận email
    ↓
Kiểm tra cú pháp để phản hồi sớm
    ↓
INSERT users(email, ...)
    ↓
UNIQUE(email) bảo vệ khi có hai request đồng thời
    ↓
Nếu vi phạm unique: chuyển thành lỗi nghiệp vụ phù hợp
```

Không nên dựa vào:

```sql
SELECT COUNT(*) FROM users WHERE email = :email;
-- nếu bằng 0 thì INSERT
```

như một bảo đảm duy nhất. Truy vấn có thể hữu ích để hiển thị thông báo trước, nhưng giữa `SELECT` và `INSERT`, transaction khác có thể insert cùng email. `UNIQUE` mới là bảo vệ có tính quyết định.

## 9. Xử lý lỗi constraint trong ứng dụng

Khi database từ chối một câu lệnh, ứng dụng cần nhận diện loại vi phạm và ánh xạ thành phản hồi phù hợp. Không nên biến mọi lỗi SQL thành thông báo “dữ liệu không hợp lệ” chung chung.

Một số nhóm lỗi thường gặp:

| Loại constraint | Ví dụ | Phản hồi nghiệp vụ có thể phù hợp |
|---|---|---|
| `UNIQUE` | Email hoặc mã booking đã được sử dụng | Thông báo giá trị đã tồn tại hoặc yêu cầu tải lại. |
| `PRIMARY KEY` | ID đã tồn tại | Sinh ID khác hoặc báo xung đột dữ liệu. |
| `FOREIGN KEY` | Khách hàng được tham chiếu không tồn tại hoặc đã bị xóa | Yêu cầu chọn lại đối tượng hợp lệ. |
| `NOT NULL` | Thiếu trường bắt buộc | Trả lỗi validation cho trường tương ứng. |
| `CHECK` | Số lượng âm hoặc phần trăm ngoài miền | Trả thông báo vi phạm quy tắc miền. |
| Exclusion/constraint chuyên biệt | Hai lịch đặt chồng nhau | Thông báo tài nguyên không còn khả dụng. |

Một số driver hoặc hệ quản trị cung cấp SQLSTATE và mã constraint cụ thể. Ví dụ, PostgreSQL thường dùng `23505` cho unique violation, `23503` cho foreign key violation, `23514` cho check violation và `23502` cho not-null violation. Đây là mã theo PostgreSQL; với engine khác, cần dùng mã lỗi và metadata của driver tương ứng. Nếu có thể, ánh xạ theo tên constraint thay vì phân tích chuỗi thông báo lỗi vốn có thể thay đổi theo ngôn ngữ hoặc phiên bản.

### Transaction sau khi gặp lỗi

Phạm vi transaction bị ảnh hưởng bởi lỗi phụ thuộc hệ quản trị. Ví dụ, PostgreSQL đánh dấu transaction ở trạng thái lỗi sau một statement thất bại; caller phải rollback hoặc rollback về savepoint trước khi tiếp tục. Một số engine và framework có cơ chế khác.

Ứng dụng không nên bắt lỗi unique violation rồi tiếp tục dùng persistence context hoặc transaction như thể chưa có gì xảy ra. Hãy xác định trạng thái transaction, rollback khi cần, và chỉ retry khi nghiệp vụ cho phép.

### Không retry mù quáng constraint violation

Nếu insert vi phạm `UNIQUE` vì một tài khoản khác đã đăng ký email đó, lặp lại cùng câu `INSERT` sẽ tiếp tục thất bại. Đây thường là kết quả nghiệp vụ cần trả về, không phải lỗi tạm thời cần retry.

Deadlock hoặc serialization failure có thể là lỗi tạm thời phù hợp để retry toàn bộ transaction. Constraint violation thường phản ánh trạng thái hoặc đầu vào không thỏa quy tắc; phải xử lý theo loại constraint.

## 10. UPSERT không thay thế việc thiết kế constraint

Nhiều hệ quản trị hỗ trợ UPSERT, chẳng hạn `INSERT ... ON CONFLICT` hoặc cú pháp tương đương. UPSERT thường dựa vào unique constraint hoặc unique index để xác định xung đột.

Ví dụ theo PostgreSQL:

```sql
INSERT INTO user_preferences (user_id, theme)
VALUES (:userId, :theme)
ON CONFLICT (user_id)
DO UPDATE SET theme = EXCLUDED.theme;
```

Unique constraint trên `user_id` bảo đảm mỗi người có tối đa một hàng preference. UPSERT định nghĩa cách ứng dụng phản ứng khi insert gặp unique conflict: cập nhật hàng hiện có.

Điều này không có nghĩa mọi xung đột đều nên tự động update. Với email đăng nhập, một email đã thuộc về người khác không nên bị ghi đè bằng thông tin người dùng mới. Với preference, cập nhật theo giá trị mới nhất có thể là chính sách hợp lý. Cần xác định ý nghĩa nghiệp vụ trước khi chọn `DO UPDATE`, `DO NOTHING` hoặc trả lỗi.

UPSERT cũng không tự giải quyết các bất biến liên hàng, write skew hoặc các thay đổi trên nhiều bảng. Nó chỉ giải quyết một dạng xung đột insert/update theo unique key được chỉ định.

## 11. Những giới hạn cần hiểu khi chọn constraint

### CHECK không phải công cụ tổng quát cho truy vấn nhiều hàng

Một `CHECK` thông thường nên kiểm tra giá trị của hàng hiện tại. Không dùng nó như cách tổng quát để truy vấn bảng khác, đếm hàng hoặc tính tổng các bản ghi liên quan. Cách database hỗ trợ subquery trong check cũng có giới hạn và có thể không bảo đảm tính đúng đắn khi dữ liệu ở bảng khác thay đổi.

### Trigger phải được thiết kế cho concurrency

Trigger có thể thực thi logic phức tạp hơn constraint khai báo, nhưng trigger không tự động làm một truy vấn kiểm tra trở nên an toàn khi có nhiều transaction. Trigger kiểu “đếm hàng rồi insert nếu số lượng dưới giới hạn” vẫn có thể gặp write skew nếu hai transaction cùng đọc tổng cũ.

Nếu dùng trigger để bảo vệ bất biến liên hàng, phải thiết kế khóa, thứ tự truy cập, isolation level và xử lý deadlock/serialization rõ ràng. Kiểm thử bằng các transaction thực sự chạy đồng thời.

### Constraint không thay thế mọi quy tắc nghiệp vụ

Các quy tắc như “người quản lý phải phê duyệt trước khi thanh toán”, “chỉ nhân viên thuộc phòng ban mới được sửa hồ sơ” hoặc “gửi email sau khi đơn hàng được xác nhận” cần logic nghiệp vụ, kiểm tra quyền và điều phối tác dụng phụ. Một số trạng thái có thể được ràng buộc bằng `CHECK` hoặc foreign key, nhưng constraint không thể thay thế toàn bộ quy trình.

### Hành vi phụ thuộc hệ quản trị

Các khác biệt cần kiểm chứng gồm:

- Nhiều `NULL` trong unique constraint được xử lý như thế nào.
- Có hỗ trợ partial/filtered unique index, functional index và exclusion constraint không.
- `CHECK` có hỗ trợ biểu thức nào và được kiểm tra ở thời điểm nào.
- Constraint có thể `DEFERRABLE` hay không.
- Foreign key lấy khóa và phối hợp với delete/update đồng thời ra sao.
- Mã lỗi, SQLSTATE, phạm vi rollback và khả năng retry.

Không nên lấy một ví dụ PostgreSQL rồi giả định nó chạy hoặc có cùng semantics trên MySQL, SQL Server, Oracle hay SQLite.

## 12. Đưa constraint vào schema và migration

Thêm constraint vào một bảng đang có dữ liệu là thay đổi có thể thất bại nếu dữ liệu hiện tại đã vi phạm quy tắc. Một migration an toàn cần xem xét cả dữ liệu và lưu lượng ghi trong lúc triển khai.

Quy trình tổng quát:

1. **Xác định bất biến:** viết rõ điều kiện phải đúng, phạm vi dữ liệu và ngoại lệ được phép.
2. **Tìm dữ liệu vi phạm:** truy vấn các hàng trùng, `NULL`, giá trị ngoài miền hoặc tham chiếu mồ côi.
3. **Quyết định xử lý dữ liệu cũ:** sửa, gộp, xóa hoặc đưa vào quy trình nghiệp vụ; không tự chọn bản ghi thắng nếu chưa có quy tắc.
4. **Triển khai constraint:** chọn loại constraint/index và thời điểm kiểm tra phù hợp với engine.
5. **Đánh giá tác động vận hành:** tạo unique index hoặc thêm foreign key trên bảng lớn có thể cần thời gian, khóa hoặc tài nguyên đáng kể. Dùng cơ chế online/concurrent nếu engine hỗ trợ và phù hợp.
6. **Cập nhật ứng dụng:** chuyển lỗi constraint thành kết quả nghiệp vụ, đồng thời giữ kiểm tra đầu vào sớm khi cần.
7. **Kiểm chứng sau triển khai:** thử cả dữ liệu hợp lệ, dữ liệu vi phạm và hai transaction cạnh tranh.

Ví dụ tìm email trùng trước khi thêm unique constraint:

```sql
SELECT email, COUNT(*) AS occurrences
FROM users
GROUP BY email
HAVING COUNT(*) > 1;
```

Tìm hàng con không có hàng cha:

```sql
SELECT o.id, o.customer_id
FROM orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE c.id IS NULL;
```

Tìm số dư âm trước khi thêm check:

```sql
SELECT id, balance
FROM accounts
WHERE balance < 0;
```

Kết quả cần được xử lý theo chính sách dữ liệu trước khi constraint có thể được bật thành công. Với bảng có ghi liên tục, cũng phải kiểm soát các transaction mới trong giai đoạn làm sạch và tạo constraint để không phát sinh vi phạm mới giữa hai bước.

### Đặt tên constraint có ý nghĩa

Tên rõ ràng giúp log, metric và xử lý lỗi dễ hiểu:

```text
pk_users
uq_users_email
fk_orders_customer
ck_accounts_balance_nonnegative
uq_room_booking_slot
```

Tên cụ thể theo bảng và bất biến thường hữu ích hơn tên tự sinh khó đọc. Tên cần duy nhất trong phạm vi mà hệ quản trị yêu cầu.

## 13. Kiểm thử constraint dưới tải đồng thời

Kiểm tra một câu `INSERT` sai rồi xác nhận database trả lỗi là chưa đủ. Bất biến concurrency cần được thử bằng nhiều transaction độc lập.

### Test hai request đăng ký cùng email

Chuẩn bị một email chưa tồn tại. Dùng hai connection cùng cố insert email đó:

```text
T1: BEGIN
T2: BEGIN

T1: INSERT users(email = 'same@example.test')
T2: INSERT users(email = 'same@example.test')

T1: COMMIT
T2: COMMIT hoặc nhận unique violation
```

Kết quả cuối phải có đúng một hàng mang email đó. Test cũng cần xác nhận ứng dụng chuyển lỗi của transaction thua thành phản hồi phù hợp và không tạo hồ sơ phụ hoặc tác dụng phụ không nhất quán.

### Test hai transaction đặt cùng ghế

Với `UNIQUE(event_id, seat_no)`, cho hai transaction cùng insert một ghế cho cùng sự kiện. Kết quả cuối chỉ có một booking. Không dùng truy vấn “ghế đã có ai đặt chưa?” như bằng chứng bảo đảm; unique constraint phải là lớp quyết định cuối.

### Test khóa ngoại với xóa hàng cha

Cho một transaction insert hàng con trong khi transaction khác xóa hàng cha. Kết quả phải tuân theo chính sách foreign key đã khai báo: một thao tác chờ hoặc thất bại, hoặc hành vi cascade tương ứng. Không được để lại hàng con mồ côi.

### Test CHECK với cập nhật cạnh tranh

Cho nhiều transaction trừ tồn kho. Sau khi tất cả hoàn tất, xác nhận `available >= 0` và các đơn hàng được xác nhận khớp với số lượng đã trừ. `CHECK` là hàng rào cho miền giá trị; logic cập nhật nguyên tử và transaction bảo đảm các thay đổi liên quan được lưu nhất quán.

### Test bất biến liên hàng

Nếu quy tắc phụ thuộc tổng hoặc nhiều hàng, hãy tạo tình huống tương tự write skew. Xác nhận cơ chế khóa, constraint chuyên biệt hoặc Serializable thực sự ngăn trạng thái cuối sai. Một `CHECK` trên từng hàng không chứng minh được bất biến tổng thể.

Để test có thể lặp lại, dùng barrier/latch để điều khiển hai transaction cùng vượt qua bước đọc trước khi ghi. Tránh chỉ dùng `sleep`, vì thời gian lập lịch của thread không bảo đảm thứ tự mong muốn.

## 14. Những sai lầm thường gặp

- **Chỉ kiểm tra bằng `SELECT` trước khi insert:** hai transaction có thể cùng thấy chưa tồn tại. Dùng `UNIQUE` hoặc cơ chế database phù hợp.
- **Cho rằng `CHECK` tự loại bỏ `NULL`:** kết quả `UNKNOWN` thường không bị xem là vi phạm. Kết hợp `NOT NULL` khi cần.
- **Dùng `CHECK` để kiểm tra tổng nhiều hàng:** đây không phải cơ chế tổng quát và có thể không được hỗ trợ hoặc không an toàn khi concurrency. Dùng constraint chuyên biệt, hàng điều phối, khóa hoặc Serializable.
- **Cho rằng trigger luôn an toàn:** trigger vẫn có thể gặp race condition nếu chỉ đọc dữ liệu rồi quyết định ghi mà không đồng bộ.
- **Bắt mọi lỗi database rồi retry:** unique violation thường là xung đột nghiệp vụ cần phản hồi; retry mù sẽ thất bại lặp lại.
- **Chỉ khai báo constraint trong ORM:** annotation không đảm bảo schema production đã có constraint, đặc biệt khi dùng migration hoặc native SQL. Kiểm tra schema thật.
- **Đặt `ON DELETE CASCADE` mà không hiểu phạm vi:** có thể xóa lịch sử hoặc dữ liệu phụ thuộc không nên mất.
- **Thêm constraint vào dữ liệu cũ mà chưa làm sạch:** migration có thể thất bại hoặc phải khóa bảng lâu.
- **Chỉ test từng transaction riêng lẻ:** không kiểm chứng được cuộc đua giữa nhiều transaction.

## 15. Cách quyết định có nên dùng constraint hay không

Khi gặp một quy tắc dữ liệu, hãy xác định rõ:

1. Quy tắc có thể biểu diễn trên một hàng bằng `NOT NULL` hoặc `CHECK` không?
2. Quy tắc là duy nhất theo một hoặc nhiều cột, hoặc duy nhất có điều kiện, để dùng `UNIQUE`/unique index không?
3. Quy tắc là quan hệ tham chiếu để dùng `FOREIGN KEY` không?
4. Quy tắc về khoảng hoặc chồng lấn có constraint chuyên biệt trong engine không?
5. Nếu quy tắc phụ thuộc nhiều hàng, có thể biến nó thành constraint duy nhất, một hàng bộ đếm/điều phối hoặc một thao tác cập nhật nguyên tử không?
6. Nếu không, cần khóa phạm vi, Serializable, trigger có đồng bộ hoặc một giao thức nghiệp vụ nào?
7. Ứng dụng sẽ xử lý lỗi constraint và trạng thái transaction ra sao?

Nếu bất biến có thể được database biểu diễn trực tiếp, hãy khai báo nó trong schema và xem đó là hợp đồng dữ liệu. Giữ kiểm tra ở ứng dụng để cải thiện trải nghiệm, nhưng đừng để tính đúng đắn phụ thuộc hoàn toàn vào các lần kiểm tra trước khi ghi. Với quy tắc không thể biểu diễn trực tiếp, hãy thiết kế cơ chế concurrency có phạm vi bao trùm mọi dữ liệu liên quan và kiểm thử bằng các transaction thực sự chạy đồng thời.
