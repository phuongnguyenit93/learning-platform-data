# Giới hạn của CHECK đối với bất biến liên quan nhiều hàng

Ràng buộc `CHECK` giúp DBMS từ chối một hàng có giá trị không thỏa điều kiện. Chúng rất phù hợp để bảo vệ quy tắc nằm ngay trong hàng đó, chẳng hạn số lượng không âm hoặc ngày kết thúc sau ngày bắt đầu. Tuy nhiên, nhiều quy tắc nghiệp vụ phụ thuộc vào **nhiều hàng, nhiều giao dịch hoặc tổng hợp dữ liệu trên cả một nhóm**. Một `CHECK` thông thường không thể tự bảo đảm các bất biến đó.

Ví dụ, các quy tắc sau không chỉ phụ thuộc vào một hàng:

- Một ca trực luôn phải có ít nhất một bác sĩ đang trực.
- Tổng số ghế đã đặt không được vượt sức chứa của phòng.
- Một phòng không được có hai lượt đặt chỗ trùng thời gian.
- Một khách hàng chỉ được có tối đa ba đơn hàng đang xử lý.
- Tổng số tiền phân bổ cho các hạng mục phải bằng ngân sách của dự án.

Nếu mỗi transaction chỉ kiểm tra dữ liệu mà nó nhìn thấy rồi cập nhật một hàng riêng, nhiều transaction có thể cùng vượt qua kiểm tra và kết hợp lại tạo ra trạng thái sai. Vì vậy, cần hiểu `CHECK` bảo vệ được điều gì, khi nào nên dùng `UNIQUE`, khóa ngoại hoặc exclusion constraint, và khi nào phải phối hợp transaction bằng khóa tường minh hay `SERIALIZABLE`.

## 1. CHECK được thiết kế để kiểm tra điều kiện trên một hàng

Một `CHECK` constraint gắn với bảng và biểu thức điều kiện. DBMS đánh giá biểu thức khi hàng được chèn hoặc cập nhật. Nếu điều kiện không đạt, thao tác ghi bị từ chối.

Ví dụ:

```sql
CREATE TABLE product (
    product_id bigint PRIMARY KEY,
    price      numeric(12, 2) NOT NULL,
    quantity   integer NOT NULL,
    CONSTRAINT ck_product_price_nonnegative CHECK (price >= 0),
    CONSTRAINT ck_product_quantity_nonnegative CHECK (quantity >= 0)
);
```

Hai ràng buộc trên kiểm tra các cột của chính hàng `product` đang được ghi. Chúng bảo vệ được quy tắc `price >= 0` và `quantity >= 0` cho từng sản phẩm.

Một ví dụ khác là bảo đảm khoảng thời gian của từng lượt đặt chỗ có thứ tự hợp lệ:

```sql
CREATE TABLE reservation (
    reservation_id bigint PRIMARY KEY,
    room_id        bigint NOT NULL,
    starts_at      timestamp NOT NULL,
    ends_at        timestamp NOT NULL,
    CONSTRAINT ck_reservation_time CHECK (ends_at > starts_at)
);
```

`CHECK (ends_at > starts_at)` không cần đọc hàng khác. Mỗi hàng tự mô tả một khoảng thời gian hợp lệ.

### 1.1. CHECK không phải truy vấn kiểm tra toàn bảng

Một biểu thức `CHECK` thông thường không được dùng như một truy vấn con để đếm hoặc tìm các hàng khác trong cùng bảng. Ví dụ ý tưởng sau không phải một cách khai báo `CHECK` hợp lệ, có tính khả chuyển trong các DBMS phổ biến:

```sql
-- Ý tưởng không được CHECK thông thường hỗ trợ:
CHECK (
    (SELECT count(*)
     FROM doctor_on_call
     WHERE on_call = true) >= 1
)
```

Lý do không chỉ là giới hạn cú pháp. DBMS cần có một cơ chế đồng bộ để bảo đảm điều kiện vẫn đúng khi nhiều transaction cùng thêm, xóa hoặc cập nhật hàng. Một phép đếm tại thời điểm ghi không tự khóa toàn bộ tập dữ liệu và không ngăn transaction khác thay đổi kết quả ngay sau đó.

Trong PostgreSQL, biểu thức `CHECK` không được chứa subquery và được giả định là bất biến theo cùng đầu vào. Các hệ quản trị khác cũng giới hạn `CHECK` chủ yếu ở biểu thức trên hàng; cú pháp và chi tiết hỗ trợ có thể khác. Không nên dùng hàm tùy chỉnh đọc bảng khác bên trong `CHECK` để lách giới hạn này.

### 1.2. CHECK và giá trị NULL

Trong SQL, biểu thức điều kiện có thể cho kết quả `TRUE`, `FALSE` hoặc `UNKNOWN` do `NULL`. Ở các DBMS phổ biến, `CHECK` thường chỉ từ chối khi biểu thức trả về `FALSE`; `UNKNOWN` được chấp nhận. Vì vậy, `CHECK (quantity >= 0)` không tự cấm `quantity` là `NULL`.

Nếu cột bắt buộc phải có giá trị, kết hợp `NOT NULL`:

```sql
quantity integer NOT NULL CHECK (quantity >= 0)
```

`NOT NULL` bảo vệ sự hiện diện của giá trị; `CHECK` bảo vệ miền giá trị hợp lệ. Hai ràng buộc có vai trò khác nhau.

## 2. Bất biến một hàng và bất biến nhiều hàng

Một cách phân loại hữu ích là xem phạm vi dữ liệu cần thiết để đánh giá quy tắc.

| Loại bất biến | Ví dụ | Công cụ phù hợp thường gặp |
|---|---|---|
| Trên một cột | Giá không âm | `CHECK`, `NOT NULL` |
| Giữa các cột trong cùng hàng | `ends_at > starts_at` | `CHECK` |
| Duy nhất giữa các hàng | Mỗi email chỉ thuộc một tài khoản | `UNIQUE`, unique index |
| Tham chiếu giữa các bảng | Đơn hàng phải thuộc khách hàng tồn tại | `FOREIGN KEY` |
| Không chồng lấn giữa các hàng | Hai lượt đặt cùng phòng không trùng giờ | Exclusion constraint hoặc khóa/Serializable tùy DBMS |
| Tổng hợp trên một nhóm hàng | Tổng ghế đã đặt không vượt sức chứa | Hàng counter/guard, cập nhật nguyên tử, khóa hoặc Serializable |
| Tồn tại ít nhất một hàng thỏa điều kiện | Mỗi ca trực còn ít nhất một bác sĩ | Mô hình dữ liệu, guard/counter, khóa hoặc Serializable |

`UNIQUE` và `FOREIGN KEY` cũng là constraint, nhưng chúng có semantics chuyên biệt để DBMS đồng bộ các thao tác liên quan giữa nhiều hàng hoặc bảng. Không thể suy ra rằng vì `CHECK` không phù hợp với bất biến nhiều hàng thì mọi loại constraint đều chỉ kiểm tra một hàng.

## 3. Ví dụ write skew: mỗi hàng hợp lệ nhưng quy tắc chung bị phá vỡ

Giả sử một ca trực phải luôn có ít nhất một bác sĩ đang trực. Bảng dữ liệu ban đầu:

| shift_id | doctor_id | on_call |
|---:|---|---|
| 10 | A | true |
| 10 | B | true |

T1 và T2 cùng đọc số bác sĩ trực là 2. T1 cập nhật A thành nghỉ; T2 cập nhật B thành nghỉ. Hai transaction ghi vào hai hàng khác nhau nên không có xung đột ghi trực tiếp trên cùng hàng.

```text
T1                                      T2
-----------------------------------     -----------------------------------
Đọc số người trực = 2                  Đọc số người trực = 2
Đặt A.on_call = false                  Đặt B.on_call = false
COMMIT                                  COMMIT
```

Kết quả cuối cùng có 0 bác sĩ trực. Mỗi hàng vẫn có giá trị boolean hợp lệ, nhưng bất biến của cả ca trực đã bị vi phạm.

Đây là **write skew**: mỗi transaction ra quyết định dựa trên snapshot hợp lệ của riêng nó, rồi cập nhật một phần khác nhau của tập dữ liệu. Một `CHECK (on_call IN (true, false))` không thể ngăn tình huống này vì điều kiện đó chỉ xác nhận kiểu giá trị của từng hàng.

Ví dụ này cho thấy phải bảo vệ điều kiện ở đúng phạm vi. Nếu quy tắc liên quan đến mọi hàng có `shift_id = 10`, cơ chế đồng bộ cũng phải bao quát mọi thao tác có thể làm thay đổi tập hàng đó.

## 4. Đừng dùng CHECK để đọc bảng khác qua hàm tùy chỉnh

Một cách lách thường được nghĩ đến là tạo hàm `count_active_doctors(shift_id)` rồi gọi hàm đó trong `CHECK`. Ý tưởng có thể trông như sau:

```sql
-- Minh họa một cách thiết kế không nên dựa vào:
CHECK (count_active_doctors(shift_id) >= 1)
```

Thiết kế này có nhiều vấn đề:

- Một số DBMS không cho phép subquery hoặc hàm truy cập dữ liệu khác trong biểu thức `CHECK`.
- DBMS có thể chỉ đánh giá constraint khi hàng đang ghi thay đổi; cập nhật một hàng khác trong bảng tham chiếu có thể không kích hoạt việc kiểm tra lại hàng này.
- Hàm có thể đọc một snapshot không thấy các thay đổi chưa commit của transaction khác.
- Hai transaction đồng thời có thể cùng đọc kết quả đếm cũ và cùng ghi, dẫn đến write skew.
- DBMS thường không biết hàm phụ thuộc vào những bảng nào để lập kế hoạch khóa hoặc kiểm tra lại constraint khi các bảng đó thay đổi.
- Trong PostgreSQL, `CHECK` được giả định là biểu thức bất biến với cùng giá trị đầu vào; dùng hàm đọc bảng khác vi phạm giả định này và có thể khiến dữ liệu trở nên không nhất quán khi hàm hoặc bảng khác thay đổi.

Nếu cần kiểm tra nhiều hàng, hãy dùng constraint chuyên biệt, thiết kế lưu trữ tổng hợp, trigger có cơ chế đồng bộ đúng, hoặc isolation/locking phù hợp. Một hàm trả về `TRUE` tại thời điểm gọi không tự tạo ra bảo đảm đồng thời.

## 5. Những constraint khác có thể bảo vệ dữ liệu liên hàng

Trước khi viết trigger hoặc khóa thủ công, hãy xem quy tắc có thể biểu diễn bằng constraint chuyên biệt hay không.

### 5.1. UNIQUE: không cho phép trùng khóa

Nếu mỗi khách hàng chỉ được có một hồ sơ cho một loại tài khoản, dùng unique constraint:

```sql
ALTER TABLE customer_account
ADD CONSTRAINT uq_customer_account_type
UNIQUE (customer_id, account_type);
```

DBMS điều phối các lần insert/update cạnh tranh để không thể commit hai hàng có cùng cặp giá trị theo semantics của unique constraint. Cách này đáng tin cậy hơn việc chạy `SELECT` kiểm tra trước rồi `INSERT`, vì hai transaction có thể cùng thấy chưa có hàng nào.

Trong PostgreSQL, unique partial index có thể áp dụng cho một phần hàng, chẳng hạn chỉ cho phép một hồ sơ đang hoạt động:

```sql
CREATE UNIQUE INDEX uq_one_active_profile
ON profile (customer_id)
WHERE status = 'ACTIVE';
```

Các DBMS khác có thể hỗ trợ filtered/partial unique index với cú pháp hoặc giới hạn riêng. Cần kiểm tra phiên bản đang sử dụng.

### 5.2. FOREIGN KEY: bảo vệ quan hệ tham chiếu

Một đơn hàng phải tham chiếu đến khách hàng tồn tại:

```sql
CREATE TABLE orders (
    order_id    bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
```

Khóa ngoại bảo vệ tính toàn vẹn tham chiếu khi insert/update đơn hàng và khi xóa/cập nhật khách hàng được tham chiếu. DBMS có cơ chế phối hợp các thao tác liên quan. Nó không tự bảo đảm các quy tắc tổng hợp như “một khách hàng có tối đa ba đơn hàng đang xử lý”.

### 5.3. Exclusion constraint: ngăn các khoảng dữ liệu xung đột

Một quy tắc đặt phòng thường là hai reservation của cùng phòng không được chồng lấn thời gian. PostgreSQL hỗ trợ exclusion constraint cho kiểu bất biến này.

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_reservation (
    reservation_id bigint PRIMARY KEY,
    room_id        bigint NOT NULL,
    starts_at      timestamptz NOT NULL,
    ends_at        timestamptz NOT NULL,
    status         text NOT NULL,
    CONSTRAINT ck_reservation_interval CHECK (ends_at > starts_at),
    CONSTRAINT ex_room_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        )
        WHERE (status <> 'CANCELLED')
);
```

`btree_gist` cung cấp hỗ trợ GiST cho phép so sánh bằng trên `room_id` với các kiểu phù hợp. Toán tử `&&` trên range kiểm tra hai khoảng có giao nhau hay không. Khoảng `[)` bao gồm thời điểm bắt đầu và không bao gồm thời điểm kết thúc, nên một lượt đặt kết thúc lúc 10:00 có thể nối tiếp lượt khác bắt đầu đúng 10:00.

Exclusion constraint được DBMS thực thi trong điều kiện đồng thời, tránh cuộc đua “cùng kiểm tra chưa có reservation trùng rồi cùng insert”. Đây là công cụ phù hợp hơn một `CHECK` hoặc trigger chỉ đếm các hàng hiện tại.

Exclusion constraint là tính năng có tính đặc thù DBMS. Với hệ quản trị không hỗ trợ, có thể cần thiết kế hàng guard theo phòng, khóa range phù hợp hoặc transaction Serializable.

## 6. Bất biến tổng hợp: tổng số đã đặt không vượt sức chứa

Giả sử phòng có sức chứa 100 người. Mỗi reservation lưu số ghế được đặt. Quy tắc là:

\[
\sum_{r \in Reservations(room)} r.seats \le capacity(room)
\]

Một `CHECK (seats > 0)` trên từng reservation chỉ bảo đảm mỗi hàng có số ghế dương. Nó không bảo đảm tổng các hàng không vượt 100.

### 6.1. Vì sao SELECT SUM rồi INSERT không an toàn?

Giả sử còn 5 chỗ. T1 muốn đặt 4 chỗ, T2 cũng muốn đặt 4 chỗ. Nếu cả hai transaction cùng chạy:

```sql
SELECT 100 - SUM(seats)
FROM reservation
WHERE room_id = 8;
```

T1 có thể thấy còn 5 chỗ; T2 cũng thấy còn 5 chỗ. Cả hai đều insert 4 ghế và cùng commit. Tổng mới tăng 8, vượt sức chứa.

```text
T1                                      T2
-----------------------------------     -----------------------------------
Đọc tổng đã đặt = 95                   Đọc tổng đã đặt = 95
Tính còn 5 chỗ                         Tính còn 5 chỗ
INSERT 4 ghế                           INSERT 4 ghế
COMMIT                                  COMMIT

Tổng cuối = 103 > 100
```

Việc chạy `SELECT SUM` trước khi insert chỉ là kiểm tra ứng dụng. Nếu không có đồng bộ trên tài nguyên chung hoặc Serializable, hai transaction không biết quyết định của nhau.

### 6.2. Lưu counter trên một hàng đại diện

Một cách phổ biến là lưu `capacity` và `reserved_seats` trên hàng `room`. Mỗi lần đặt hoặc hủy chỗ, transaction cập nhật hàng này cùng với reservation.

```sql
CREATE TABLE room (
    room_id        bigint PRIMARY KEY,
    capacity       integer NOT NULL,
    reserved_seats integer NOT NULL DEFAULT 0,
    CONSTRAINT ck_room_capacity CHECK (capacity >= 0),
    CONSTRAINT ck_room_reserved CHECK (
        reserved_seats >= 0 AND reserved_seats <= capacity
    )
);
```

`CHECK` ở đây bảo vệ các giá trị trên **một hàng room**. Bất biến tổng hợp được duy trì bằng cách mọi thao tác thay đổi reservation phải cập nhật counter trong cùng transaction.

Đặt 4 ghế:

```sql
BEGIN;

UPDATE room
SET reserved_seats = reserved_seats + 4
WHERE room_id = 8
  AND reserved_seats + 4 <= capacity;

-- Ứng dụng phải xác nhận đúng một hàng được cập nhật.
-- Nếu là 0 hàng: hết chỗ hoặc phòng không tồn tại; ROLLBACK.

INSERT INTO reservation(room_id, seats, status)
VALUES (8, 4, 'CONFIRMED');

COMMIT;
```

Hai transaction cùng đặt chỗ phải cập nhật cùng hàng `room`. Row lock trên hàng này tuần tự hóa việc thay đổi counter. Khi một transaction chờ transaction kia, DBMS đánh giá cập nhật trên giá trị hiện hành theo semantics của câu `UPDATE`; điều kiện `reserved_seats + 4 <= capacity` được kiểm tra cùng phép tăng counter. Chỉ transaction còn đủ sức chứa mới cập nhật được.

Nếu `UPDATE room` không cập nhật hàng nào, ứng dụng không được insert reservation. Nếu insert reservation thất bại, transaction phải rollback để counter cũng được hoàn nguyên.

Hủy reservation cũng phải giảm counter trong cùng transaction và chỉ giảm khi reservation chuyển từ trạng thái có tính vào tổng sang trạng thái không còn tính. Nếu cho phép sửa số ghế, cần cập nhật phần chênh lệch một cách nguyên tử.

### 6.3. Counter chỉ đúng nếu mọi đường ghi cùng tuân thủ giao thức

Nếu một API, tác vụ import hoặc script quản trị insert reservation mà không tăng `reserved_seats`, counter sẽ lệch. Nếu một luồng hủy reservation giảm counter hai lần, giá trị cũng sai.

Để giảm rủi ro:

- Đóng gói thay đổi reservation và counter trong một stored procedure hoặc một lớp dịch vụ dùng chung.
- Hạn chế quyền ghi trực tiếp vào các bảng nếu ứng dụng cần tuân thủ một giao thức cụ thể.
- Dùng transaction để cập nhật cả counter và reservation.
- Ghi nhận chuyển trạng thái bằng điều kiện, tránh xử lý lặp cùng một chuyển đổi.
- Có tác vụ đối soát định kỳ so sánh counter với `SUM(seats)` để phát hiện sai lệch.

Counter là một mô hình dữ liệu được chuẩn hóa có chủ ý để biến bất biến tổng hợp thành điều kiện trên một hàng điều phối. Nó tăng tốc kiểm tra và tạo điểm đồng bộ rõ ràng, nhưng cần quản lý tính nhất quán của counter.

## 7. Bất biến “ít nhất một bác sĩ đang trực”

Với quy tắc ca trực, có thể dùng hàng guard hoặc counter đại diện cho từng ca. Hàng guard tạo một điểm đồng bộ cho mọi transaction thay đổi trạng thái bác sĩ trong ca đó.

Ví dụ:

```sql
CREATE TABLE shift_guard (
    shift_id       bigint PRIMARY KEY,
    on_call_count  integer NOT NULL,
    version        bigint NOT NULL DEFAULT 0,
    CONSTRAINT ck_shift_on_call_count CHECK (on_call_count >= 1)
);
```

Khi một bác sĩ chuyển từ đang trực sang nghỉ, transaction có thể cập nhật counter có điều kiện:

```sql
BEGIN;

UPDATE doctor_on_call
SET on_call = false
WHERE shift_id = 10
  AND doctor_id = 'A'
  AND on_call = true;

-- Nếu không cập nhật đúng một hàng, ROLLBACK.

UPDATE shift_guard
SET on_call_count = on_call_count - 1,
    version = version + 1
WHERE shift_id = 10
  AND on_call_count > 1;

-- Nếu không cập nhật đúng một hàng, ROLLBACK:
-- ca trực không thể giảm thêm người.

COMMIT;
```

Thứ tự thực tế có thể được đảo lại tùy thiết kế, nhưng cả hai cập nhật phải nằm trong cùng transaction và lỗi ở bước nào cũng phải rollback toàn bộ. Câu `UPDATE shift_guard ... WHERE on_call_count > 1` tuần tự hóa các lần giảm counter trên cùng ca. Nếu hai bác sĩ cuối cùng cùng xin nghỉ, chỉ một transaction có thể giảm từ 2 xuống 1; transaction còn lại không thể giảm tiếp xuống 0.

Khi bác sĩ bắt đầu trực, transaction cập nhật hàng bác sĩ và tăng `on_call_count` trong cùng transaction. Các thao tác đổi trạng thái phải chỉ tác động khi trạng thái cũ đúng như dự kiến, để không tăng/giảm counter lặp.

### 7.1. Nếu dùng guard lock rồi mới đếm?

Một cách khác là khóa hàng `shift_guard` trước, rồi đếm số bác sĩ đang trực và quyết định cập nhật. Mọi transaction thay đổi bác sĩ trong ca phải khóa cùng hàng guard.

```sql
BEGIN;

SELECT shift_id
FROM shift_guard
WHERE shift_id = 10
FOR UPDATE;

SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10 AND on_call = true;

-- Chỉ cho phép nghỉ nếu số người trực sau cập nhật vẫn >= 1.

COMMIT;
```

Mẫu này cần chú ý isolation level. Ở PostgreSQL `READ COMMITTED`, nếu khóa guard là thao tác đầu và truy vấn đếm chạy sau khi lấy được khóa, câu `SELECT count(*)` tiếp theo nhận snapshot mới và có thể thấy transaction trước đã commit. Ở `REPEATABLE READ`, snapshot của transaction được giữ ổn định; nếu chỉ khóa mà không thay đổi guard row, một transaction chờ có thể vẫn đọc snapshot cũ. Có thể buộc xung đột ghi bằng cách cập nhật `version`, dùng counter nguyên tử như ví dụ trên, hoặc chọn `SERIALIZABLE` và xử lý serialization failure. Chi tiết tương ứng phải được kiểm tra theo DBMS.

Một hàng guard chỉ hữu ích khi mọi thao tác có thể làm thay đổi bất biến đều tham gia cùng giao thức. Nếu một tác vụ nền bỏ qua guard/counter, quy tắc vẫn có thể bị phá vỡ.

## 8. Trigger không tự động giải quyết cuộc đua đồng thời

Trigger có thể giúp gom logic kiểm tra vào DBMS để mọi đường ghi đều kích hoạt. Nhưng trigger chỉ là nơi chạy mã; nó không tự tạo ra một cơ chế tuần tự hóa cho nhiều transaction.

Ví dụ một trigger `AFTER INSERT` trên `reservation` chạy `SELECT SUM(seats)` rồi báo lỗi nếu tổng vượt capacity. Nếu T1 và T2 cùng insert, trigger của mỗi transaction có thể không nhìn thấy hàng chưa commit của transaction còn lại. Cả hai có thể cùng tính tổng dưới ngưỡng rồi cùng commit.

```text
T1                                      T2
-----------------------------------     -----------------------------------
INSERT reservation 4 ghế               INSERT reservation 4 ghế
Trigger đọc SUM cũ                     Trigger đọc SUM cũ
Thấy còn đủ                            Thấy còn đủ
Trigger cho qua                        Trigger cho qua
COMMIT                                  COMMIT
```

Trigger phù hợp để tự động duy trì counter hoặc buộc mọi thay đổi đi qua một quy tắc chung, nhưng phần đồng bộ vẫn phải đúng. Ví dụ trigger có thể cập nhật hàng `room` bằng phép tăng counter có điều kiện; vì các transaction cùng cập nhật một hàng, row lock giúp tuần tự hóa việc thay đổi. Nếu trigger chỉ đếm bảng rồi quyết định, cuộc đua vẫn tồn tại.

Khi dùng trigger, cần xem:

- Trigger chạy theo từng hàng hay từng statement.
- Các transaction có thể cùng chạy trigger trên những hàng khác nhau không.
- Trigger có cập nhật một hàng guard/counter chung để tạo điểm đồng bộ không.
- Isolation level và snapshot mà truy vấn trong trigger sử dụng.
- Thứ tự khóa giữa trigger và câu lệnh gọi nó có thể tạo deadlock không.
- Có đường ghi nào bỏ qua trigger hoặc thay đổi counter trực tiếp không.

Trong PostgreSQL, deferred constraint trigger có thể trì hoãn kiểm tra đến cuối transaction, nhưng thời điểm kiểm tra muộn không tự bảo đảm chống write skew giữa các transaction đồng thời. Vẫn cần constraint chuyên biệt, khóa hoặc Serializable để xử lý cuộc đua.

## 9. Dùng SERIALIZABLE khi bất biến khó khóa thủ công

Nếu quy tắc phụ thuộc vào một tập hàng động hoặc nhiều predicate, việc chọn một hàng guard và bắt mọi đường ghi tuân thủ giao thức có thể phức tạp. `SERIALIZABLE` cho DBMS trách nhiệm bảo đảm kết quả commit tương đương một thứ tự thực thi tuần tự.

Ví dụ, hai transaction cùng đọc số bác sĩ trực rồi cập nhật hai hàng khác nhau. Ở PostgreSQL `SERIALIZABLE`, SSI theo dõi các phụ thuộc đọc/ghi có thể tạo serialization anomaly. Một transaction có thể bị hủy với SQLSTATE `40001` thay vì cả hai cùng commit.

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10 AND on_call = true;

-- Kiểm tra bất biến và cập nhật hàng của bác sĩ.

COMMIT;
```

Ứng dụng phải rollback và retry **toàn bộ transaction** khi gặp serialization failure. Không chỉ chạy lại câu `UPDATE`, vì quyết định phải được tính lại trên snapshot mới.

`SERIALIZABLE` không có cùng cách triển khai ở mọi DBMS. PostgreSQL dùng SSI; một số hệ thống dùng range/key-range lock; hệ quản trị khác có cơ chế kiểm tra xung đột riêng. Có thể phát sinh blocking, deadlock hoặc serialization failure tùy sản phẩm và lịch thực thi.

## 10. Dùng advisory lock khi cần khóa một tài nguyên logic

Đôi khi bất biến liên quan đến một tài nguyên không có hàng đại diện phù hợp, hoặc ứng dụng cần khóa theo một khóa logic như `shift_id`, `account_group_id` hay tên một quy trình. Một số DBMS cung cấp application lock/advisory lock.

Advisory lock là khóa do ứng dụng định nghĩa. DBMS không tự biết khóa đó đại diện cho bất biến nào và không tự động bắt mọi câu lệnh ghi phải lấy khóa. Mọi đường ghi liên quan phải tuân thủ cùng quy ước.

Trong PostgreSQL, ví dụ dùng transaction-level advisory lock:

```sql
BEGIN;

-- Khóa logic đại diện cho ca trực số 10.
SELECT pg_advisory_xact_lock(7001, 10);

-- Đọc trạng thái ca, kiểm tra bất biến, cập nhật các hàng liên quan.

COMMIT;
```

Transaction-level advisory lock được giải phóng khi transaction kết thúc. Cặp số trong ví dụ chỉ là khóa namespace do ứng dụng quy ước; cần chọn ánh xạ không va chạm với tài nguyên logic khác. Nếu một transaction quên lấy advisory lock, DBMS vẫn cho phép nó cập nhật bảng theo quyền thông thường.

Advisory lock hữu ích khi cần điều phối logic, nhưng một unique constraint hoặc constraint chuyên biệt vẫn nên được ưu tiên nếu có thể mô tả trực tiếp bất biến.

## 11. So sánh các cách bảo vệ bất biến nhiều hàng

| Cách tiếp cận | Cách bảo vệ | Ưu điểm | Chi phí/giới hạn |
|---|---|---|---|
| `UNIQUE`/unique index | DBMS không cho phép giá trị khóa trùng | Khai báo rõ, đồng bộ ở DBMS, bảo vệ mọi đường ghi | Chỉ phù hợp quy tắc duy nhất có thể biểu diễn bằng key |
| `FOREIGN KEY` | DBMS điều phối thay đổi ở hai phía quan hệ tham chiếu | Bảo vệ tính toàn vẹn tham chiếu | Không bảo vệ tổng hoặc điều kiện aggregate |
| Exclusion constraint | DBMS từ chối các hàng có quan hệ xung đột theo operator | Phù hợp khoảng thời gian/vùng dữ liệu không được giao nhau | Hỗ trợ và cú pháp phụ thuộc DBMS, loại dữ liệu/operator |
| Counter/guard row | Mọi thay đổi cập nhật cùng hàng đại diện trong transaction | Phạm vi đồng bộ rõ, có thể dùng `CHECK` trên counter | Điểm nóng; phải duy trì counter qua mọi đường ghi |
| Trigger có đồng bộ | Tự động chạy logic và cập nhật tài nguyên chung | Gom logic ở DBMS, tránh quên ở một số caller | Trigger không tự chống race; cần lock/counter/Serializable |
| Explicit/advisory lock | Các transaction cùng khóa một tài nguyên trước khi kiểm tra | Kiểm soát rõ thứ tự và phạm vi | Phải tuân thủ giao thức; có thể blocking/deadlock |
| `SERIALIZABLE` | DBMS ngăn hoặc phát hiện lịch không tuần tự hóa | Bảo vệ predicate và quan hệ nhiều lần đọc/ghi | Có thể abort/retry hoặc blocking; cần xử lý lỗi |

## 12. Các lỗi thiết kế thường gặp

- **Dùng CHECK để kiểm tra `COUNT(*)` hoặc `SUM(...)` trên bảng khác.** `CHECK` thông thường không có semantics để bảo vệ tập hàng liên quan.
- **Đếm trước rồi mới ghi.** Hai transaction có thể cùng đọc một tổng cũ và cùng vượt qua kiểm tra.
- **Dùng trigger chỉ để SELECT COUNT rồi báo lỗi.** Trigger vẫn chạy trong transaction đồng thời và có thể gặp write skew.
- **Khóa các hàng hiện có nhưng quên hàng mới.** `SELECT FOR UPDATE` trên tập kết quả rỗng không tự khóa khoảng trống trong mọi DBMS.
- **Dùng counter nhưng có đường ghi bỏ qua counter.** Counter lệch khiến constraint trên hàng đại diện không còn phản ánh dữ liệu thật.
- **Cập nhật counter và dữ liệu chi tiết ở hai transaction riêng.** Một lỗi giữa chừng có thể làm hai phần không khớp.
- **Không xử lý NULL.** `CHECK` thường chấp nhận kết quả `UNKNOWN`; dùng `NOT NULL` khi cần giá trị bắt buộc.
- **Cho rằng kiểm tra lúc commit tự giải quyết concurrency.** Deferred trigger/constraint chỉ thay đổi thời điểm kiểm tra; vẫn cần đồng bộ giữa transaction.
- **Dùng Serializable nhưng chỉ retry một câu lệnh.** Cần retry toàn bộ transaction để tính lại quyết định trên trạng thái mới.
- **Cho rằng mọi ứng dụng đều dùng cùng một giao thức khóa.** Một script quản trị hoặc job nền có thể phá bất biến nếu bỏ qua guard/advisory lock.

## 13. Quy trình lựa chọn cơ chế phù hợp

Khi cần bảo vệ một quy tắc dữ liệu, hãy đi theo trình tự:

1. **Viết bất biến thành câu rõ ràng.** Nêu phạm vi, nhóm hàng, điều kiện và thời điểm quy tắc phải đúng.
2. **Xác định phạm vi dữ liệu.** Quy tắc nằm trong một hàng, giữa các hàng có khóa chung, trên một khoảng hay trên tổng hợp động?
3. **Dùng constraint chuyên biệt nếu có.** Kiểm tra `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY`, exclusion constraint hoặc filtered unique index.
4. **Nếu là aggregate, cân nhắc counter/guard row.** Chuyển điều kiện tổng hợp thành phép cập nhật nguyên tử trên một hàng đại diện.
5. **Nếu cần khóa logic, xác định một giao thức chung.** Dùng row lock hoặc advisory lock và buộc mọi đường ghi tham gia.
6. **Nếu phạm vi khó mô tả hoặc dễ bỏ sót, cân nhắc SERIALIZABLE.** Thiết kế retry toàn bộ transaction khi có serialization failure.
7. **Kiểm tra trigger và tác vụ nền.** Mọi thành phần có thể thay đổi dữ liệu đều phải bảo vệ cùng bất biến.
8. **Kiểm thử các transaction chạy đồng thời.** Dùng barrier để hai transaction cùng đọc trước khi ghi, tái hiện write skew và xác nhận chỉ một lịch hợp lệ có thể commit.
9. **Đối soát dữ liệu hiện có.** Thêm constraint hoặc counter vào hệ thống đang chạy cần kiểm tra và xử lý các hàng vi phạm trước.

## 14. Kiểm thử bất biến dưới tải đồng thời

Một kiểm thử tuần tự không đủ để chứng minh cơ chế bảo vệ hoạt động. Hãy tạo hai session độc lập và điều khiển thứ tự để chúng cùng đọc trạng thái ban đầu trước khi cập nhật.

Với ví dụ bác sĩ trực:

```text
Session T1                              Session T2
-----------------------------------     -----------------------------------
BEGIN                                   BEGIN
Đọc on_call_count = 2                   Đọc on_call_count = 2
Chờ tín hiệu đồng bộ                    Chờ tín hiệu đồng bộ
UPDATE bác sĩ A nghỉ                    UPDATE bác sĩ B nghỉ
COMMIT                                  COMMIT
```

Chạy cùng kịch bản ở các chế độ khác nhau:

- Chỉ `CHECK` trên từng hàng: xác nhận nó không ngăn write skew.
- Counter với conditional `UPDATE`: xác nhận một transaction không thể giảm tổng xuống dưới giới hạn.
- Guard lock: xác nhận mọi writer lấy cùng khóa và đọc trạng thái mới theo semantics isolation đã chọn.
- `SERIALIZABLE`: xác nhận một transaction bị abort khi lịch tạo serialization anomaly và ứng dụng retry đúng cách.
- Trigger: xác nhận trigger có đồng bộ trên tài nguyên chung, không chỉ đếm snapshot riêng của mỗi transaction.

Sau kiểm thử, truy vấn dữ liệu để xác nhận bất biến cuối cùng, kiểm tra số transaction commit/abort, và kiểm tra counter có khớp với dữ liệu chi tiết. Nên chạy cả trường hợp insert, update, delete, hủy và retry vì mỗi đường chuyển trạng thái có thể tác động đến bất biến theo cách khác nhau.

## 15. Những điểm cần ghi nhớ

- `CHECK` phù hợp với điều kiện trên chính hàng đang được ghi, ví dụ giá không âm hoặc thời gian kết thúc sau thời gian bắt đầu.
- `CHECK` thông thường không đếm hoặc tổng hợp các hàng khác và không tự bảo vệ một tập dữ liệu trước transaction đồng thời.
- `CHECK` thường chấp nhận kết quả `UNKNOWN` do `NULL`; dùng `NOT NULL` nếu cột bắt buộc có giá trị.
- Dùng `UNIQUE`, `FOREIGN KEY` hoặc exclusion constraint khi quy tắc khớp với semantics của các constraint đó.
- Với bất biến tổng hợp, counter/guard row có thể tạo một điểm đồng bộ; cập nhật counter và dữ liệu chi tiết phải nằm trong cùng transaction.
- Trigger chỉ là nơi thực thi logic. Trigger đếm bảng mà không khóa hoặc tuần tự hóa vẫn có thể gặp race condition.
- Khóa tường minh hoặc advisory lock chỉ bảo vệ được bất biến nếu mọi đường ghi cùng tuân thủ giao thức.
- `SERIALIZABLE` phù hợp với bất biến phức tạp trên nhiều hàng hoặc predicate, nhưng ứng dụng phải retry toàn bộ transaction khi DBMS báo serialization failure.
- Kiểm thử concurrency phải tái hiện nhiều transaction cùng đọc và ghi, không chỉ kiểm tra từng câu lệnh chạy riêng lẻ.

Khi thiết kế ràng buộc dữ liệu, hãy chọn công cụ theo phạm vi của bất biến. `CHECK` giữ cho từng hàng hợp lệ; constraint chuyên biệt bảo vệ các quan hệ mà DBMS hiểu được; counter, khóa hoặc Serializable bảo vệ quy tắc tổng hợp và phụ thuộc vào nhiều hàng. Việc xác định đúng phạm vi giúp dữ liệu vẫn hợp lệ ngay cả khi nhiều transaction thay đổi nó cùng lúc.
