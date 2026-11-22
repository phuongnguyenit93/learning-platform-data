# EXCLUDE và ngăn khoảng dữ liệu chồng lấn trong PostgreSQL

## 1. Bài toán: hai bản ghi hợp lệ riêng lẻ nhưng mâu thuẫn khi đứng cạnh nhau

Trong hệ thống đặt phòng họp, một phòng không thể được đặt cho hai cuộc họp tại những **khoảng thời gian giao nhau**. Tương tự, một thiết bị không thể được thuê đồng thời cho hai hợp đồng, hoặc một cấu hình hiệu lực không nên có hai phiên bản cùng áp dụng tại một thời điểm.

Giả sử phòng 101 có lịch:

| Lượt đặt | Bắt đầu | Kết thúc | Trạng thái |
|---|---|---|---|
| A | 09:00 | 10:00 | CONFIRMED |
| B | 10:00 | 11:00 | CONFIRMED |
| C | 09:30 | 10:30 | Đang đề xuất |

A và B **không chồng lấn** nếu thời gian được hiểu là các khoảng dạng `[bắt đầu, kết thúc)`: lấy đầu, không lấy cuối. Nhưng C chồng lên cả A và B nên phải bị từ chối.

Một ràng buộc `UNIQUE(room_id, start_at, end_at)` không giải quyết được bài toán, vì C có thời điểm bắt đầu/kết thúc khác A và B. Một `CHECK (start_at < end_at)` chỉ xác nhận **một hàng** có khoảng thời gian hợp lệ; nó không so sánh hàng này với mọi lượt đặt còn lại.

PostgreSQL cung cấp **exclusion constraint**, viết bằng `EXCLUDE`, để khai báo rằng **không được tồn tại hai hàng thỏa đồng thời một tập các điều kiện xung đột**.

Ví dụ cốt lõi:

```sql
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
```

Có thể đọc là:

> Không được tồn tại hai bản ghi có **cùng room_id** và **hai khoảng during giao nhau**.

Với các điều kiện và cấu hình phù hợp, PostgreSQL kiểm tra ràng buộc này cả khi có **nhiều transaction đồng thời**, giúp tránh lỗi đua khi ứng dụng chỉ thực hiện “SELECT kiểm tra trước, INSERT sau”.

### Sau bài học, bạn sẽ làm được gì?

- Hiểu sự khác nhau giữa `UNIQUE`, `CHECK` và `EXCLUDE`.
- Tạo và đọc giá trị `tstzrange`, `tsrange`, `daterange` và các kiểu range thường dùng.
- Hiểu toán tử chồng lấn `&&` cùng quy tắc biên `[)`.
- Cài extension `btree_gist` và khai báo `EXCLUDE USING gist`.
- Dùng **partial exclusion constraint** để chỉ giới hạn các bản ghi còn hiệu lực.
- Hiểu `NULL`, khoảng rỗng, khoảng không giới hạn và thời điểm có múi giờ.
- Mô phỏng hai phiên cùng cố gắng đặt một phòng và giải thích kết quả.
- Dùng `DEFERRABLE` khi cần điều chỉnh nhiều khoảng thời gian trong cùng transaction.
- Đọc lỗi PostgreSQL SQLSTATE `23P01` và thiết kế xử lý ở tầng ứng dụng.
- Xem metadata/index được sinh ra, nhận diện giới hạn về hiệu năng và mô hình dữ liệu.

Các SQL ví dụ bên dưới dành cho **PostgreSQL lab riêng**; không chạy câu tạo, sửa hoặc hủy bảng trực tiếp trên hệ thống production.

## 2. Cách diễn đạt khoảng thời gian bằng range types

PostgreSQL có những **range types** biểu diễn một khoảng liên tục hoặc rời rạc của các giá trị thuộc một kiểu phần tử. Các kiểu phổ biến:

| Kiểu range | Kiểu phần tử | Ví dụ dùng |
|---|---|---|
| `int4range` | `integer` | Khoảng số nguyên 32-bit |
| `int8range` | `bigint` | Khoảng ID hoặc số nguyên lớn |
| `numrange` | `numeric` | Khoảng giá/định lượng |
| `daterange` | `date` | Ngày hiệu lực, kỳ nghỉ |
| `tsrange` | `timestamp without time zone` | Khoảng giờ địa phương không chứa timezone |
| `tstzrange` | `timestamp with time zone` | Khoảng giữa **hai thời điểm xác định** |

Trong bài đặt phòng, ta chọn `tstzrange` vì mỗi thời điểm đặt phòng là một instant thực tế, không chỉ là dòng chữ “09:00” thiếu thông tin múi giờ.

### 2.1. Tạo range bằng constructor

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    '[)'
) AS first_booking;
```

Các tham số:

1. **Lower bound:** điểm bắt đầu.
2. **Upper bound:** điểm kết thúc.
3. **Bounds notation:** hai ký hiệu cho biết có lấy biên tương ứng hay không.

Có thể viết ngắn hơn khi đầu vào đã mang đúng kiểu:

```sql
SELECT tstzrange(
    '2026-11-14 09:00:00+07',
    '2026-11-14 10:00:00+07',
    '[)'
);
```

Để tài liệu dễ kiểm chứng, các ví dụ quan trọng sẽ thường ghi rõ `TIMESTAMPTZ` và offset.

### 2.2. Ý nghĩa của bốn kiểu biên

| Ký hiệu | Biên dưới | Biên trên | Diễn giải |
|---|---|---|---|
| `[)` | Có lấy | Không lấy | Bao gồm bắt đầu, loại trừ kết thúc |
| `[]` | Có lấy | Có lấy | Bao gồm cả hai đầu |
| `()` | Không lấy | Không lấy | Loại trừ cả hai đầu |
| `(]` | Không lấy | Có lấy | Loại trừ bắt đầu, bao gồm kết thúc |

Với lịch đặt phòng, `[)` là lựa chọn rất thông dụng:

```text
A: [09:00, 10:00)
   ██████████████
B:              [10:00, 11:00)
                 ██████████████

A ∩ B = ∅, không chồng lấn.
```

Nếu dùng hai khoảng đóng `[09:00,10:00]` và `[10:00,11:00]`, cả hai cùng chứa thời điểm 10:00 nên được coi là giao nhau. Vì thế, **quy tắc biên là một quyết định nghiệp vụ**, không chỉ là cách hiển thị.

### 2.3. Range khác hai cột thời gian rời rạc ở đâu?

Hai cột `start_at` và `end_at` có thể mô tả một khoảng, nhưng PostgreSQL range mang theo phép toán về khoảng:

- Chồng lấn với khoảng khác.
- Một khoảng chứa thời điểm nào đó.
- Một khoảng chứa toàn bộ khoảng khác.
- Hai khoảng liền kề.
- Biên dưới/trên, khoảng rỗng, khoảng không giới hạn.

Ví dụ:

```sql
SELECT
    tstzrange(
        '2026-11-14 09:00+07',
        '2026-11-14 10:00+07', '[)'
    )
    &&
    tstzrange(
        '2026-11-14 09:30+07',
        '2026-11-14 10:30+07', '[)'
    ) AS overlap_detected;
```

Kết quả là `true` vì hai khoảng giao nhau. Toán tử `&&` chính là nền tảng để ràng buộc `EXCLUDE` phát hiện lịch trùng.

## 3. Những toán tử range cần hiểu trước khi viết EXCLUDE

| Toán tử | Cách đọc | Ví dụ ý nghĩa |
|---|---|---|
| `a && b` | Hai khoảng chồng lấn | A và B có phần giao |
| `a @> b` | A chứa B hoặc chứa một phần tử B | Khoảng hiệu lực chứa thời điểm |
| `a <@ b` | A được chứa trong B | Khoảng A nằm trọn trong B |
| `a -|- b` | Hai khoảng liền kề | A kết thúc đúng khi B bắt đầu, theo ngữ nghĩa range |
| `a << b` | A hoàn toàn ở trước B | Không giao và nằm bên trái |
| `a >> b` | A hoàn toàn ở sau B | Không giao và nằm bên phải |
| `a = b` | Hai range bằng nhau | So sánh giá trị range |

### 3.1. Kiểm tra chồng lấn

```sql
SELECT
    tstzrange('2026-11-14 09:00+07',
              '2026-11-14 10:00+07', '[)')
    &&
    tstzrange('2026-11-14 09:30+07',
              '2026-11-14 10:30+07', '[)')
    AS overlaps;
```

Kết quả kỳ vọng: `true`.

### 3.2. Kiểm tra hai khoảng sát nhau

```sql
SELECT
    tstzrange('2026-11-14 09:00+07',
              '2026-11-14 10:00+07', '[)')
    &&
    tstzrange('2026-11-14 10:00+07',
              '2026-11-14 11:00+07', '[)')
    AS overlaps,

    tstzrange('2026-11-14 09:00+07',
              '2026-11-14 10:00+07', '[)')
    -|-
    tstzrange('2026-11-14 10:00+07',
              '2026-11-14 11:00+07', '[)')
    AS adjacent;
```

Kết quả kỳ vọng:

```text
overlaps = false
adjacent = true
```

Hai lượt đặt nối tiếp nhau có thể hợp lệ, vì người thuê trước trả phòng đúng lúc người thuê sau bắt đầu.

### 3.3. Kiểm tra một thời điểm thuộc khoảng

```sql
SELECT
    tstzrange('2026-11-14 09:00+07',
              '2026-11-14 10:00+07', '[)')
    @>
    TIMESTAMPTZ '2026-11-14 09:45+07'
    AS contains_time;
```

Kết quả: `true`.

Ở đúng thời điểm `10:00+07`, với khoảng `[09:00,10:00)`, kết quả chứa là `false` vì biên trên bị loại trừ.

## 4. EXCLUDE thực sự kiểm tra điều kiện gì?

Về mặt khái niệm, exclusion constraint định nghĩa một tập phép so sánh giữa **hai hàng khác nhau**. PostgreSQL không cho phép tồn tại hai hàng sao cho **tất cả** phép so sánh được chỉ định đều trả `TRUE`.

Ví dụ:

```sql
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
```

Giả sử R1 và R2 có:

- `room_id(R1) = room_id(R2)`: TRUE.
- `during(R1) && during(R2)`: TRUE.

Hai điều kiện đồng thời TRUE nghĩa là **xung đột**, nên PostgreSQL từ chối một thay đổi làm tình huống này tồn tại.

Nếu hai phòng khác nhau:

- So sánh `room_id` là FALSE.
- Khoảng thời gian có thể chồng lên nhau, nhưng không phải **tất cả** điều kiện đều TRUE.

Do đó hai phòng khác nhau vẫn có thể được đặt cùng giờ.

Nếu cùng phòng nhưng khoảng không chồng nhau:

- So sánh `room_id` là TRUE.
- So sánh `during && during` là FALSE.

Do đó hai lượt đặt hợp lệ.

### 4.1. EXCLUDE khác UNIQUE

Ràng buộc:

```sql
UNIQUE (room_id, start_at, end_at)
```

chỉ loại trừ những hàng trùng chính xác ở các cột được so sánh theo ngữ nghĩa UNIQUE. Nó **không** phát hiện:

```text
A: room 101, [09:00, 10:00)
B: room 101, [09:30, 10:30)
```

vì hai hàng có start/end khác nhau.

Ngược lại:

```sql
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
```

loại trừ bất kỳ hai khoảng giao nhau đối với cùng phòng, không cần hai khoảng giống hệt nhau.

### 4.2. EXCLUDE khác CHECK

`CHECK (start_at < end_at)` xác nhận một hàng có đầu trước cuối.

`EXCLUDE ... (room_id WITH =, during WITH &&)` xác nhận không có **hai hàng xung đột** theo điều kiện.

Hai constraint giải quyết **hai lớp tính hợp lệ** khác nhau, nên chúng thường được dùng cùng nhau.

### 4.3. Cơ chế NULL cần đặc biệt lưu ý

Vì EXCLUDE chỉ ngăn cặp hàng mà **mọi phép so sánh đều TRUE**, nếu một phép so sánh trả `FALSE` hoặc `NULL` thì cặp hàng không vi phạm theo logic của ràng buộc.

Ví dụ nếu `room_id` cho phép NULL, phép so sánh:

```sql
NULL = NULL
```

trả `NULL`, không phải TRUE. Khi đó có thể có hai bản ghi có thời gian chồng lên nhau nhưng `room_id` đều NULL mà không bị EXCLUDE ngăn theo ý định.

Vì vậy, với dữ liệu đặt phòng, các cột quan trọng nên dùng:

```sql
room_id bigint NOT NULL,
during tstzrange NOT NULL
```

Khi nghiệp vụ yêu cầu không chồng lấn, **đừng bỏ qua NOT NULL** chỉ vì đã có EXCLUDE.

## 5. Chuẩn bị môi trường thực hành với GiST và btree_gist

Đây là ví dụ lab đầy đủ để có thể đi từ bảng rỗng tới những trường hợp thành công và thất bại.

### 5.1. Vì sao cần GiST?

Exclusion constraint cần một **index access method** hỗ trợ các toán tử dùng để phát hiện xung đột. Với range, PostgreSQL thường sử dụng **GiST** (*Generalized Search Tree*).

Trong ví dụ:

```sql
room_id WITH =
during WITH &&
```

- Toán tử `&&` của range được hỗ trợ bởi operator class GiST thích hợp.
- Với `bigint`/kiểu scalar, khả năng dùng phép `=` trong GiST thường được bổ sung thông qua extension `btree_gist`.

`btree_gist` không biến GiST thành B-tree và cũng không làm cho mọi toán tử trên mọi kiểu dữ liệu tự động được hỗ trợ. Nó cung cấp những operator classes với ngữ nghĩa tương tự B-tree cho một số kiểu dữ liệu, giúp kết hợp scalar equality với range overlap trong một GiST index.

### 5.2. Cài extension trong database lab

Kết nối đến database lab đúng mục tiêu, ví dụ:

```sh
psql -h 127.0.0.1 -p 5432 -U lab_admin -d booking_lab_db
```

Giả sử role `lab_admin`, database `booking_lab_db` đã tồn tại và role có quyền cần thiết. Trong SQL:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

Điều này tạo các đối tượng của extension **trong database hiện tại**. Nó không phải cài một extension độc lập cho mọi database của cluster chỉ bằng một lần chạy trong database khác.

Tùy phiên bản, môi trường cloud và chính sách quyền, việc cài extension có thể yêu cầu owner database, quyền CREATE hoặc một vai trò quản trị thích hợp. Nếu bị từ chối, hãy yêu cầu người quản trị cài trong **database lab**; không cấp `SUPERUSER` cho runtime account chỉ để vượt qua lỗi.

Có thể xem extension đã có:

```sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'btree_gist';
```

Để bài thực hành tránh xung đột với các bảng có sẵn, tạo schema riêng:

```sql
CREATE SCHEMA IF NOT EXISTS booking_lab;
```

**Không chạy tiếp câu `CREATE TABLE` bên dưới nếu đã có bảng cùng tên chứa dữ liệu cần giữ.** Bài giả định schema lab mới, chưa có các bảng tương ứng.

## 6. Thiết kế bảng đặt phòng có EXCLUDE

### 6.1. Bảng phòng

```sql
CREATE TABLE booking_lab.rooms (
    room_id bigint PRIMARY KEY,
    room_name text NOT NULL UNIQUE
);

INSERT INTO booking_lab.rooms(room_id, room_name)
VALUES
    (101, 'Phòng họp A'),
    (102, 'Phòng họp B');
```

### 6.2. Bảng đặt phòng

```sql
CREATE TABLE booking_lab.reservations (
    reservation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    room_id bigint NOT NULL
        REFERENCES booking_lab.rooms(room_id),

    during tstzrange NOT NULL,

    status text NOT NULL DEFAULT 'CONFIRMED'
        CHECK (status IN ('HELD', 'CONFIRMED', 'CANCELLED')),

    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT reservation_period_not_empty
        CHECK (NOT isempty(during)),

    CONSTRAINT reservation_no_active_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            during WITH &&
        )
        WHERE (status IN ('HELD', 'CONFIRMED'))
        DEFERRABLE INITIALLY IMMEDIATE
);
```

Đây là ví dụ có **partial exclusion constraint**: chỉ những bản ghi trạng thái `HELD` hoặc `CONFIRMED` mới được đưa vào phạm vi cấm chồng lấn. Bản ghi `CANCELLED` không giữ chỗ.

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| `room_id bigint NOT NULL` | Xác định phòng, không cho thiếu phòng |
| `during tstzrange NOT NULL` | Khoảng thời gian đã được định nghĩa |
| `CHECK (NOT isempty(during))` | Không cho lưu khoảng rỗng |
| `status ... CHECK (...)` | Giới hạn trạng thái được phép |
| `EXCLUDE USING gist` | Yêu cầu PostgreSQL so sánh các hàng qua GiST |
| `room_id WITH =` | Chỉ cấm trùng đối với cùng phòng |
| `during WITH &&` | Hai khoảng giao nhau thì xung đột |
| `WHERE (status IN (...))` | Chỉ áp dụng với các bản ghi còn giữ chỗ |
| `DEFERRABLE INITIALLY IMMEDIATE` | Mặc định kiểm tra ngay, nhưng transaction có thể chủ động trì hoãn |

PostgreSQL **tạo index phục vụ exclusion constraint** khi tạo ràng buộc. Không cần tạo thêm một index hoàn toàn giống hệt chỉ để constraint hoạt động.

### 6.3. Vì sao dùng `HELD` và `CONFIRMED`?

Một hệ thống có thể tạm giữ phòng trước khi người dùng thanh toán hoặc xác nhận. Nếu `HELD` còn hiệu lực, nó phải ngăn người khác đặt cùng khoảng thời gian.

Khi người dùng hủy hoặc phiên giữ chỗ hết hạn và hệ thống chuyển bản ghi sang `CANCELLED`, khoảng đó mới được giải phóng theo phạm vi partial constraint.

**Quan trọng:** chỉ vì một bản ghi `HELD` có thời hạn giữ chỗ trong nghiệp vụ không có nghĩa EXCLUDE tự biết nó đã hết hạn. PostgreSQL không tự thay `status` dựa trên đồng hồ của hệ thống; cần một workflow cập nhật trạng thái hết hạn theo transaction và chính sách nghiệp vụ.

Không nên đặt biểu thức thời gian biến đổi như `now()` trực tiếp vào **partial index predicate** để mong index tự thay đổi thành viên theo thời gian: predicate index yêu cầu biểu thức phù hợp tính bất biến và index không tự cập nhật khi đồng hồ chạy.

## 7. Thực hành 1: hai lịch sát nhau được chấp nhận

Thêm lượt A cho phòng 101 từ 09:00 tới 10:00:

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:00+07',
        '[)'
    ),
    'CONFIRMED'
)
RETURNING reservation_id, room_id, during, status;
```

Thêm lượt B ngay sau đó:

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00+07',
        TIMESTAMPTZ '2026-11-14 11:00+07',
        '[)'
    ),
    'CONFIRMED'
)
RETURNING reservation_id, room_id, during, status;
```

Hai câu `INSERT` đều thành công vì:

```text
A = [09:00, 10:00)
B = [10:00, 11:00)

A && B = FALSE
```

Sử dụng khoảng nửa mở `[)` giúp hai cuộc họp “tiếp giáp” không tự bị coi là trùng thời gian.

Nếu quy trình vận hành cần **15 phút dọn phòng** giữa hai buổi, quy tắc nghiệp vụ không chỉ là “không giao nhau”. Lúc đó cần mô hình hóa cả thời gian đệm (*buffer*) vào khoảng chiếm dụng hoặc dùng chiến lược ràng buộc khác; không thể chờ EXCLUDE tự hiểu nhu cầu dọn phòng.

## 8. Thực hành 2: khoảng giao nhau bị từ chối

Thử đặt thêm lượt C cùng phòng 101:

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:30+07',
        TIMESTAMPTZ '2026-11-14 10:30+07',
        '[)'
    ),
    'CONFIRMED'
);
```

Khoảng `[09:30,10:30)` giao với cả A lẫn B.

**Kết quả mong đợi:** PostgreSQL từ chối insert với thông báo tương tự:

```text
ERROR: conflicting key value violates exclusion constraint
       "reservation_no_active_overlap"
SQLSTATE: 23P01
```

Đây là dạng thông điệp minh họa; nội dung `DETAIL`, tên bảng và cách hiển thị tùy phiên bản, client và ngôn ngữ thông báo. Mã SQLSTATE quan trọng ở đây là **`23P01` — exclusion_violation**.

### 8.1. Nếu câu lệnh lỗi trong transaction

Trong phiên `psql` autocommit, lệnh thất bại thường không làm các lệnh độc lập tiếp theo trở thành một phần transaction hỏng.

Nhưng nếu bạn chạy bên trong:

```sql
BEGIN;

INSERT INTO booking_lab.reservations(room_id, during)
VALUES (
    101,
    tstzrange('2026-11-14 09:30+07',
              '2026-11-14 10:30+07', '[)')
);

-- INSERT lỗi.
ROLLBACK;
```

transaction sẽ cần `ROLLBACK` để kết thúc trạng thái lỗi. Đừng tiếp tục gửi các lệnh nghiệp vụ khác với kỳ vọng PostgreSQL tự bỏ qua riêng statement thất bại rồi commit phần còn lại.

### 8.2. Cùng thời gian, phòng khác thì hợp lệ

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    102,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:30+07',
        TIMESTAMPTZ '2026-11-14 10:30+07',
        '[)'
    ),
    'CONFIRMED'
);
```

Lượt này thuộc phòng 102. Mặc dù chồng thời gian với lịch phòng 101, phép so sánh `room_id =` cho kết quả FALSE nên **không vi phạm** exclusion constraint.

Tổng hợp:

| Lượt mới | Phòng | Khoảng | Kết quả |
|---|---:|---|---|
| B | 101 | `[10:00,11:00)` | Cho phép — sát A |
| C | 101 | `[09:30,10:30)` | Từ chối — chồng A/B |
| D | 102 | `[09:30,10:30)` | Cho phép — phòng khác |
| E | 101 | `[11:00,12:00)` | Cho phép — sau B |
| F | 101 | `[08:00,09:00)` | Cho phép — trước A |

## 9. Thực hành 3: partial exclusion constraint theo trạng thái

Giả sử khách hàng đã hủy lịch 11:30–12:30. Lịch hủy có thể vẫn được giữ để tra cứu lịch sử mà không chặn đặt mới.

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange('2026-11-14 11:30+07',
              '2026-11-14 12:30+07', '[)'),
    'CANCELLED'
);
```

Cùng phòng, cùng khoảng, tạo một lịch đang giữ chỗ:

```sql
INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange('2026-11-14 11:30+07',
              '2026-11-14 12:30+07', '[)'),
    'CONFIRMED'
);
```

Câu thứ hai được phép nếu không có lịch active khác giao nhau, vì bản ghi `CANCELLED` **không nằm trong phạm vi** partial exclusion constraint.

### 9.1. Đổi từ CANCELLED thành CONFIRMED có thể bị chặn

Giả sử lịch hủy trên được cập nhật lại thành `CONFIRMED`:

```sql
UPDATE booking_lab.reservations
SET status = 'CONFIRMED'
WHERE room_id = 101
  AND status = 'CANCELLED'
  AND during = tstzrange(
      '2026-11-14 11:30+07',
      '2026-11-14 12:30+07',
      '[)'
  );
```

Khi hàng đi từ trạng thái không tham gia constraint sang trạng thái tham gia, PostgreSQL kiểm tra ràng buộc. Nếu đã có lượt CONFIRMED giao nhau, thao tác bị từ chối.

Điều này rất quan trọng cho các workflow “khôi phục lịch đã hủy”, “xác nhận giữ chỗ” hoặc “gia hạn”: không chỉ `INSERT`, mà **`UPDATE` cũng cần tuân thủ EXCLUDE**.

### 9.2. Thời hạn giữ chỗ không tự đổi status

Giả sử hệ thống có trường `hold_expires_at`. Một hàng `HELD` hết hạn về thời gian nhưng vẫn mang status `HELD` sẽ tiếp tục bị coi là đang giữ chỗ theo predicate hiện tại.

Workflow đúng thường cần:

1. Xác định các bản ghi HELD hết hạn.
2. Chuyển chúng sang trạng thái giải phóng hợp lệ theo transaction.
3. Sau khi trạng thái đã được cập nhật an toàn, thử tạo lịch mới.
4. Xử lý trường hợp hai tiến trình dọn giữ chỗ và tạo lịch chạy đồng thời.

Đừng cố gắn hàm thời gian phụ thuộc đồng hồ vào predicate của GiST index rồi mong dữ liệu tự “thoát khỏi index” khi thời gian trôi qua.

## 10. Tại sao EXCLUDE giúp chống lỗi đua khi đặt lịch?

Một cách tiếp cận dễ gặp trong ứng dụng:

```text
Bước 1: SELECT xem phòng còn trống không.
Bước 2: Nếu trống, INSERT lịch mới.
```

Vấn đề là hai request có thể thực hiện đồng thời:

```text
Time      Transaction A                 Transaction B
-------   ----------------------------- ------------------------------
T1        SELECT: chưa thấy lịch X
T2                                      SELECT: chưa thấy lịch X
T3        INSERT lịch X
T4                                      INSERT lịch Y chồng X
T5        COMMIT
T6                                      COMMIT
```

Nếu chỉ có phép kiểm tra bằng `SELECT` thông thường, hai transaction có thể đều thấy phòng trống trong snapshot của mình và cùng ghi lịch trùng nhau.

**Exclusion constraint chuyển quy tắc “không trùng khoảng” xuống tầng database.** PostgreSQL sử dụng index và cơ chế kiểm tra xung đột tương thích giao dịch để không cho hai giao dịch đã commit tạo ra trạng thái vi phạm constraint.

Điều này bảo vệ nhiều đường ghi khác nhau:

- HTTP API.
- Worker hàng đợi.
- Script nhập dữ liệu.
- Công cụ quản trị.
- Một service khác dùng cùng database.

Dù vậy, EXCLUDE không xác nhận người dùng có **quyền đặt phòng**, phòng có đang bảo trì hay không, hoặc có đủ tiền thanh toán. Đây vẫn là những điều kiện nghiệp vụ khác.

## 11. Lab hai phiên: hai transaction đặt cùng thời gian

### 11.1. Điều kiện ban đầu

Chọn khoảng mới chưa có lịch, ví dụ phòng 101 từ 14:00 đến 15:00 ngày 14/11/2026. Mở **hai connection PostgreSQL độc lập** tới cùng database:

- **Session A**.
- **Session B**.

Dùng hai cửa sổ `psql` hoặc hai client khác nhau. Không chạy cả hai bộ lệnh tuần tự trong cùng một connection nếu muốn kiểm tra concurrency.

### 11.2. Session A

```sql
BEGIN;

INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange('2026-11-14 14:00+07',
              '2026-11-14 15:00+07', '[)'),
    'CONFIRMED'
);

-- Giữ transaction đang mở ở bước này.
-- Chưa COMMIT hoặc ROLLBACK.
```

### 11.3. Session B

Trong lúc A chưa kết thúc transaction:

```sql
BEGIN;

INSERT INTO booking_lab.reservations(room_id, during, status)
VALUES (
    101,
    tstzrange('2026-11-14 14:30+07',
              '2026-11-14 15:30+07', '[)'),
    'CONFIRMED'
);
```

Vì hai lượt đặt giao nhau, PostgreSQL cần xác định kết quả transaction chưa commit của A để quyết định có vi phạm constraint hay không.

Tùy lịch thực thi và tình trạng khóa, câu `INSERT` của B có thể **chờ** kết quả của A. Đây là điều có thể quan sát được khi constraint phải giải quyết xung đột giữa hai transaction.

### 11.4. Kết thúc A và quan sát B

**Trường hợp 1: A COMMIT**

Trong Session A:

```sql
COMMIT;
```

Nếu A đã commit lịch 14:00–15:00, B không thể commit lịch 14:30–15:30. Sau khi xung đột được giải quyết, câu lệnh của B sẽ thất bại với `23P01` theo ngữ nghĩa ràng buộc. Trong Session B, nếu transaction đã lỗi:

```sql
ROLLBACK;
```

**Trường hợp 2: A ROLLBACK**

Nếu A rollback trước khi có lịch được commit:

```sql
ROLLBACK;
```

B có thể tiếp tục và hoàn tất nếu không có lịch active khác gây xung đột; sau đó B cần `COMMIT` nếu còn ở transaction hợp lệ.

**Không chạy cả hai kịch bản liên tiếp trên cùng dữ liệu đã commit mà chưa xác định trạng thái.** Nếu đã commit một lượt đặt ở kịch bản đầu, lần thử sau sẽ gặp lịch tồn tại; hãy dùng thời gian lab khác hoặc khôi phục dữ liệu test theo quy trình.

### 11.5. Nếu câu lệnh chờ quá lâu

Trong lab có thể đặt giới hạn chờ khóa ở session để không treo thao tác quá lâu:

```sql
SET lock_timeout TO '5s';
```

Khi `lock_timeout` hết hạn, câu lệnh có thể thất bại với lỗi timeout khóa, chứ không nhất thiết trả ngay `23P01`. Kết quả này nói rằng thao tác không đợi đủ lâu để phân định xung đột, **không** chứng minh khoảng thời gian có thể được đặt thành công.

Ứng dụng cần xử lý timeout/retry theo chính sách và không coi mọi timeout là “phòng trống”. Sau lab:

```sql
RESET lock_timeout;
```

### 11.6. Vì sao SELECT trước vẫn hữu ích?

Ứng dụng có thể chạy một câu `SELECT` để hiển thị lịch trống và đưa phản hồi người dùng nhanh. Nhưng kết quả SELECT chỉ là **ảnh chụp tại một thời điểm**. Khi chèn thực sự, database constraint mới là hàng rào quyết định.

Một mô hình hợp lý:

1. Tầng ứng dụng kiểm tra quyền, đầu vào và hiển thị lịch.
2. Gửi transaction đặt phòng.
3. Dựa vào EXCLUDE để chặn xung đột cuối cùng.
4. Nếu PostgreSQL trả `23P01`, rollback và thông báo khung giờ vừa bị đặt.
5. Nếu lỗi là timeout hoặc lỗi hạ tầng, xử lý riêng theo chính sách retry/idempotency.

## 12. Khoảng rỗng, khoảng không giới hạn và NULL

### 12.1. Khoảng rỗng

```sql
SELECT
    isempty(tstzrange(
        '2026-11-14 09:00+07',
        '2026-11-14 09:00+07',
        '[)'
    )) AS is_empty;
```

Với hai biên trùng nhau và dạng `[)`, khoảng là **rỗng**: không chứa thời điểm nào.

Khoảng rỗng không chồng lấn với khoảng thông thường theo toán tử `&&`. Nếu không ngăn, hệ thống có thể lưu hàng “đặt phòng” độ dài bằng 0 mà EXCLUDE không phát hiện xung đột.

Vì thế trong schema:

```sql
CHECK (NOT isempty(during))
```

là một kiểm tra khác với `EXCLUDE` và có ý nghĩa riêng.

### 12.2. Range có biên không giới hạn

PostgreSQL hỗ trợ khoảng mở về một phía khi bỏ cận. Ví dụ:

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00+07',
    NULL,
    '[)'
) AS open_ended_period;
```

Ở constructor range, tham số bound NULL tương ứng **biên không giới hạn** của range, không phải một mảng chứa phần tử NULL. Khoảng này về mặt logic có thể kéo dài về phía tương lai và chồng lấn nhiều lịch khác.

Nếu bài toán chỉ cho phép những lượt đặt có thời điểm bắt đầu và kết thúc hữu hạn, có thể thêm:

```sql
ALTER TABLE booking_lab.reservations
ADD CONSTRAINT reservation_bounds_required
CHECK (
    NOT lower_inf(during)
    AND NOT upper_inf(during)
);
```

Ràng buộc này ngăn các biên *unbounded*. Nếu nghiệp vụ cũng không chấp nhận các giá trị timestamp đặc biệt như `infinity`, cần đánh giá thêm vì **unbounded range** và giá trị timestamp `infinity` không phải khái niệm hoàn toàn đồng nhất.

Đừng thêm constraint này khi hệ thống thực sự cần các khoảng hiệu lực mở, ví dụ giá niêm yết áp dụng vô thời hạn.

### 12.3. Nếu cột range là NULL

`during tstzrange NOT NULL` bảo đảm mọi lượt đặt phải có giá trị range. Chỉ viết:

```sql
CHECK (NOT isempty(during))
```

**không đủ để thay thế NOT NULL**, vì một `CHECK` trả UNKNOWN/NULL thường không bị PostgreSQL xem là vi phạm. Nên giữ cả hai khi nghiệp vụ yêu cầu.

### 12.4. Hai khoảng sát nhau có chắc được phép không?

Phụ thuộc cách biểu diễn biên. Với `[)`, hai khoảng `[09:00,10:00)` và `[10:00,11:00)` không giao nhau. Với các biên đóng `[]` ở thời điểm 10:00, chúng có thể chồng lấn.

Cần chuẩn hóa hợp đồng API và dữ liệu: mọi thao tác tạo lịch, sửa lịch, import CSV và đọc lịch đều dùng **cùng quy tắc biên**.

## 13. Chọn tstzrange, tsrange hay daterange?

### 13.1. Khi nên dùng tstzrange

`tstzrange` dùng hai giá trị `timestamptz`. Nó phù hợp khi cần mô tả **những thời điểm thực tế** mà hệ thống toàn cầu phải thống nhất.

Ví dụ:

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    '[)'
);
```

Khoảng này biểu diễn cùng một khoảng thời gian dù session PostgreSQL hiển thị UTC hay múi giờ Việt Nam. Giá trị `timestamptz` được trình bày theo `TimeZone` của session, nhưng **không phải dữ liệu đã đổi bản chất thời điểm**.

### 13.2. Khi có thể dùng tsrange

`tsrange` dùng `timestamp without time zone`. Nó phù hợp cho những khoảng giờ địa phương không được hiểu là một instant toàn cầu, ví dụ “mẫu giờ làm việc 09:00–17:00” khi vùng múi giờ được quản lý riêng.

```sql
SELECT tsrange(
    TIMESTAMP '2026-11-14 09:00:00',
    TIMESTAMP '2026-11-14 10:00:00',
    '[)'
);
```

Nếu dùng `tsrange` để đặt lịch họp giữa các quốc gia mà không lưu múi giờ, rất dễ nhầm 09:00 ở thành phố này với 09:00 ở thành phố khác.

### 13.3. Khi nên dùng daterange

Dùng `daterange` khi nghiệp vụ tính theo **ngày lịch**, ví dụ kỳ nghỉ từ 14/11 đến hết 16/11.

Biểu diễn nửa mở:

```sql
SELECT daterange(
    DATE '2026-11-14',
    DATE '2026-11-17',
    '[)'
) AS vacation_period;
```

Khoảng trên chứa các ngày 14, 15, 16, và loại trừ ngày 17. Nếu API nhận ngày cuối **bao gồm** trong khoảng, phải chuyển nhất quán sang biểu diễn nửa mở hoặc dùng kiểu biên phù hợp.

Với những range rời rạc như `daterange`, PostgreSQL có quy tắc canonicalization có thể chuyển các cách viết tương đương về dạng chuẩn. Không suy ra rằng `tstzrange` có cơ chế “tự cộng thêm một đơn vị thời gian nhỏ nhất” giống các range rời rạc.

### 13.4. Daylight Saving Time và lịch ở các vùng khác nhau

Một số vùng như `America/New_York` thay đổi offset theo mùa. Khoảng “09:00–10:00 theo giờ New York” cần được xác định cùng **ngày và tên vùng múi giờ** để trở thành khoảng instant chính xác.

Không chỉ cộng một offset cố định cho mọi ngày trong năm khi lên lịch quốc tế. Với lịch lặp lại hàng tuần theo giờ địa phương, chỉ một `tstzrange` không mô tả đầy đủ toàn bộ quy tắc lặp; cần lưu lịch gốc theo vùng và sinh các lần xảy ra.

## 14. Biến thể: hai cột start_at và end_at thay vì một cột range

Nhiều ứng dụng/API đã có schema dạng:

```text
booking_id | room_id | start_at | end_at
```

PostgreSQL vẫn có thể dùng EXCLUDE trên một **biểu thức range** xây từ hai cột, thay vì thêm cột `during`.

### 14.1. DDL với biểu thức tstzrange

```sql
CREATE TABLE booking_lab.reservations_columns (
    reservation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    room_id bigint NOT NULL
        REFERENCES booking_lab.rooms(room_id),

    start_at timestamptz NOT NULL,
    end_at timestamptz NOT NULL,

    status text NOT NULL DEFAULT 'CONFIRMED'
        CHECK (status IN ('HELD', 'CONFIRMED', 'CANCELLED')),

    CONSTRAINT reservation_start_before_end
        CHECK (start_at < end_at),

    CONSTRAINT reservation_columns_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            (tstzrange(start_at, end_at, '[)')) WITH &&
        )
        WHERE (status IN ('HELD', 'CONFIRMED'))
);
```

Ý nghĩa:

- `CHECK (start_at < end_at)` loại các khoảng không hợp lệ.
- Biểu thức `tstzrange(start_at,end_at,'[)')` được dùng trong cấu trúc index của EXCLUDE.
- Các lịch active của cùng phòng không được có range giao nhau.

Điều kiện này vẫn bảo vệ thao tác `UPDATE start_at` hoặc `UPDATE end_at` làm xuất hiện chồng lấn.

### 14.2. So sánh hai cách lưu

| Thiết kế | Ưu điểm | Điều cần chú ý |
|---|---|---|
| Một cột `during tstzrange` | Trực tiếp dùng các toán tử range, mô hình rõ ngữ nghĩa khoảng | Driver/API cần hỗ trợ kiểu range; kiểm tra empty/unbounded |
| Hai cột `start_at`/`end_at` + expression EXCLUDE | Phù hợp nhiều API/ORM quen thuộc; có cột scalar rõ ràng | Phải dùng cùng biểu thức range khi cần khai thác index |
| Hai cột và thêm generated range column | Có thể tiện khi vừa cần scalar vừa cần range | Cần thiết kế ràng buộc/cột generated và khả năng tương thích phiên bản |

Trong hai cách đầu, nên nhất quán về múi giờ, biên khoảng và quy tắc thời gian tối thiểu/tối đa.

### 14.3. Không dùng CHECK chứa subquery dò hàng khác

Không nên cố viết:

```sql
-- Không phải cách dùng CHECK phù hợp để kiểm tra các hàng khác:
-- CHECK (
--     NOT EXISTS (
--         SELECT 1 FROM booking_lab.reservations_columns ...
--     )
-- )
```

PostgreSQL không hỗ trợ subquery trực tiếp theo cách này trong CHECK. Quan trọng hơn, `CHECK` được thiết kế cho điều kiện của từng hàng, không phải một bộ máy kiểm tra chéo hàng an toàn đồng thời. Với việc loại trừ các khoảng, dùng `EXCLUDE` giúp diễn đạt trực tiếp và thực thi ở database.

## 15. DEFERRABLE: trì hoãn kiểm tra đến cuối transaction

Trong nhiều tình huống, ứng dụng cần thay đổi **nhiều lịch trong một transaction**. Ví dụ hoán đổi hai khung giờ đang sát nhau.

Ban đầu:

```text
Lịch A: [09:00,10:00)
Lịch B: [10:00,11:00)
```

Mục tiêu hoán đổi:

```text
Lịch A: [10:00,11:00)
Lịch B: [09:00,10:00)
```

Nếu đổi A trước, A tạm thời giao với B. Với kiểm tra ngay, câu `UPDATE` đầu bị từ chối dù **trạng thái cuối** của cả transaction có thể hợp lệ.

### 15.1. DEFERRABLE INITIALLY IMMEDIATE

Trong DDL:

```sql
CONSTRAINT reservation_no_active_overlap
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
WHERE (status IN ('HELD', 'CONFIRMED'))
DEFERRABLE INITIALLY IMMEDIATE
```

nghĩa là:

- Mặc định, constraint được kiểm tra ở chế độ **IMMEDIATE**.
- Trong transaction, có thể chủ động chuyển kiểm tra sang **DEFERRED**.
- Khi bị trì hoãn, PostgreSQL kiểm tra ở thời điểm được yêu cầu hoặc trước khi transaction commit.

Không phải mọi constraint PostgreSQL đều có thể deferrable. Exclusion constraint có hỗ trợ; nhiều `CHECK`/`NOT NULL` thông thường không thể chuyển thành deferred theo cùng cách.

### 15.2. Hoán đổi hai khoảng trong một transaction

Giả sử đã có reservation ID 201 và 202 thuộc phòng 101, active, với các khoảng ban đầu như trên; đây là **ID minh họa**. Khi thực hành, lấy ID thật bằng `SELECT reservation_id,...` trước khi sửa.

```sql
BEGIN;

SET CONSTRAINTS reservation_no_active_overlap DEFERRED;

UPDATE booking_lab.reservations
SET during = tstzrange(
    '2026-11-14 10:00+07',
    '2026-11-14 11:00+07',
    '[)'
)
WHERE reservation_id = 201;

UPDATE booking_lab.reservations
SET during = tstzrange(
    '2026-11-14 09:00+07',
    '2026-11-14 10:00+07',
    '[)'
)
WHERE reservation_id = 202;

COMMIT;
```

Nếu ID, room và các lịch đúng như giả định, **trạng thái cuối không trùng** nên transaction có thể commit thành công. Nếu sau cùng vẫn có hai lịch giao nhau, lỗi có thể xuất hiện **tại COMMIT**.

**Lưu ý:** đổi sang deferred không có nghĩa có thể commit dữ liệu vi phạm. Nó chỉ cho phép tồn tại xung đột **tạm thời trong transaction** với điều kiện phải được giải quyết trước khi kiểm tra cuối.

### 15.3. Chuyển về IMMEDIATE để kiểm tra sớm

Trong một transaction đã deferred:

```sql
SET CONSTRAINTS reservation_no_active_overlap IMMEDIATE;
```

Khi chuyển sang IMMEDIATE, PostgreSQL có thể phải kiểm tra những thay đổi đang chờ; nếu dữ liệu còn vi phạm, lệnh này sẽ thất bại.

### 15.4. Khi nào không nên defer?

Không phải thao tác đặt phòng nào cũng cần deferred. Với một câu `INSERT` đơn giản:

- Kiểm tra ngay giúp báo lỗi gần câu SQL gây xung đột.
- Tránh transaction giữ trạng thái tạm thời vi phạm trong thời gian dài.
- Dễ định vị request và trả phản hồi hơn.

Chỉ defer khi có một quy trình transaction **thực sự yêu cầu** sửa nhiều hàng để đưa từ trạng thái hợp lệ A sang trạng thái hợp lệ B.

### 15.5. Deferrable và ON CONFLICT

PostgreSQL có `INSERT ... ON CONFLICT` nhưng cần chú ý:

- Không phải mọi constraint đều là arbiter phù hợp cho `ON CONFLICT DO UPDATE`.
- **Exclusion constraints không được hỗ trợ làm arbiter cho `ON CONFLICT DO UPDATE`** theo cách dùng thông thường.
- Constraint deferrable cũng có hạn chế khi dùng làm conflict arbiter.

Với đặt lịch, thay vì tự động “update lịch nào trùng”, thường nên xử lý `23P01` như một **business conflict** và yêu cầu khách chọn khung giờ khác. Điều này an toàn về nghiệp vụ hơn việc âm thầm ghi đè lịch đã tồn tại.

## 16. Đọc và truy vấn lịch bằng các toán tử range

### 16.1. Tìm lịch giao với một khoảng đề xuất

```sql
SELECT
    reservation_id,
    room_id,
    during,
    status
FROM booking_lab.reservations
WHERE room_id = 101
  AND status IN ('HELD', 'CONFIRMED')
  AND during && tstzrange(
      '2026-11-14 09:45+07',
      '2026-11-14 10:15+07',
      '[)'
  )
ORDER BY lower(during);
```

Kết quả trả các lịch active cùng phòng giao với khoảng được đề xuất, hữu ích để **giải thích vì sao không thể đặt**.

Đây là query hỗ trợ UI. Quyết định cuối vẫn phải dựa vào EXCLUDE khi thực hiện `INSERT`/`UPDATE`, bởi một lịch khác có thể được tạo ngay sau khi SELECT.

### 16.2. Tìm lịch tại một thời điểm cụ thể

```sql
SELECT
    reservation_id,
    room_id,
    during
FROM booking_lab.reservations
WHERE room_id = 101
  AND status IN ('HELD', 'CONFIRMED')
  AND during @> TIMESTAMPTZ '2026-11-14 09:45+07';
```

Toán tử `@>` ở đây có nghĩa khoảng `during` **chứa** thời điểm 09:45.

### 16.3. Lấy biên dưới, biên trên và thuộc tính range

```sql
SELECT
    reservation_id,
    lower(during) AS start_at,
    upper(during) AS end_at,
    lower_inc(during) AS start_inclusive,
    upper_inc(during) AS end_inclusive,
    isempty(during) AS period_is_empty
FROM booking_lab.reservations
ORDER BY reservation_id;
```

Các hàm:

| Hàm | Vai trò |
|---|---|
| `lower(r)` | Lấy biên dưới nếu có |
| `upper(r)` | Lấy biên trên nếu có |
| `lower_inc(r)` | Biên dưới có được bao gồm? |
| `upper_inc(r)` | Biên trên có được bao gồm? |
| `lower_inf(r)` | Range không có biên dưới? |
| `upper_inf(r)` | Range không có biên trên? |
| `isempty(r)` | Range rỗng? |

Những hàm này giúp chuyển giá trị range thành các trường `start_at`/`end_at` trong API. Nhưng API vẫn cần bảo toàn ngữ nghĩa biên; nếu luôn dùng `[)` thì có thể định nghĩa hợp đồng đầu vào/đầu ra rõ ràng hơn.

### 16.4. Đánh giá lịch hiện tại với TimeZone

```sql
SHOW TimeZone;

SELECT
    lower(during) AS local_start_display,
    upper(during) AS local_end_display
FROM booking_lab.reservations;
```

Giá trị `tstzrange` lưu instant và xuất các biên theo cách hiển thị của session. Nếu session đổi từ UTC sang `Asia/Ho_Chi_Minh`, **thời gian in ra có thể khác**, nhưng việc hai khoảng giao nhau không đổi chỉ do khác chế độ hiển thị.

Để hiển thị giờ của một vùng cụ thể bất kể session:

```sql
SELECT
    lower(during) AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_start_wall_time,
    upper(during) AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_end_wall_time
FROM booking_lab.reservations;
```

Kết quả `AT TIME ZONE` ở đây là giờ địa phương dạng `timestamp without time zone`; nếu API cần thông tin vùng múi giờ, truyền riêng tên vùng hoặc xuất thời gian có offset.

## 17. Exclusion constraint có tự tạo index không?

Có. Khi tạo ràng buộc `EXCLUDE USING gist (...)`, PostgreSQL tạo một GiST index liên quan để hỗ trợ kiểm tra loại trừ.

### 17.1. Xem metadata trong psql

Trong `psql`:

```text
\d+ booking_lab.reservations
```

Thông thường bạn sẽ thấy:

- Các cột và kiểu dữ liệu.
- Primary key.
- Check constraints.
- Foreign key.
- Exclusion constraint, tên index và phương pháp GiST.

Lệnh `\d+` là **meta-command của psql**, không phải SQL chuẩn gửi từ JDBC.

### 17.2. Xem exclusion constraint qua catalog

```sql
SELECT
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    pg_get_constraintdef(c.oid) AS constraint_definition
FROM pg_constraint AS c
WHERE c.conrelid = 'booking_lab.reservations'::regclass
  AND c.contype = 'x'
ORDER BY c.conname;
```

Giá trị `contype = 'x'` đại diện cho **exclusion constraint**.

Xem các index của bảng:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'booking_lab'
  AND tablename = 'reservations'
ORDER BY indexname;
```

Bảng này có thể có index cho primary key và index GiST của exclusion constraint. Đừng tạo thêm index duplicate chỉ vì nghĩ EXCLUDE không tạo index.

### 17.3. Index có thể giúp truy vấn tìm khoảng giao nhau

Một truy vấn có cùng logic:

```sql
EXPLAIN
SELECT reservation_id
FROM booking_lab.reservations
WHERE room_id = 101
  AND status IN ('HELD', 'CONFIRMED')
  AND during && tstzrange(
      '2026-11-14 09:00+07',
      '2026-11-14 10:00+07',
      '[)'
  );
```

có thể tận dụng GiST index nếu planner thấy phù hợp.

Vì index là **partial** theo `status IN ('HELD','CONFIRMED')`, query nên có điều kiện đủ rõ để planner suy luận rằng nó chỉ cần các hàng thuộc phạm vi index. Nếu query tìm mọi trạng thái, index partial không bao phủ toàn bộ dữ liệu.

Với bảng chỉ vài hàng trong lab, PostgreSQL có thể chọn sequential scan — điều đó không chứng minh index bị sai.

## 18. Chi phí GiST, concurrency và khả năng mở rộng

### 18.1. Lợi ích

GiST có thể hỗ trợ kiểm tra và tìm kiếm các khoảng hiệu quả hơn so với việc ứng dụng duyệt toàn bộ lịch trong bộ nhớ.

Constraint kiểm tra ở tầng database nên hoạt động nhất quán cho nhiều đường ghi: API, script, background job và bulk import.

### 18.2. Chi phí

Mỗi thao tác thêm/sửa một lịch active phải xét ràng buộc và cập nhật index. Với workload ghi liên tục, điều đó tạo chi phí:

- Dung lượng index.
- CPU và I/O.
- Khóa/chờ giao dịch khi lịch của cùng tài nguyên cạnh tranh.
- Chi phí VACUUM và bảo trì bảng/index theo các thay đổi dữ liệu.
- Thời gian chờ nếu transaction giữ khóa quá lâu.

Không có một con số chi phí cố định. Cần benchmark trên dữ liệu và mức cạnh tranh đại diện.

### 18.3. Tránh transaction quá dài

Một request không nên:

1. Bắt đầu transaction.
2. Chèn một lịch giữ chỗ.
3. Đợi người dùng thanh toán qua mạng trong vài phút.
4. Mới commit.

Giữ transaction mở trong khi đợi tác vụ bên ngoài có thể khiến những transaction đặt trùng bị chờ và tăng tải lock.

Thường nên:

- Commit nhanh trạng thái `HELD` có hạn dùng.
- Tích hợp thanh toán/tác vụ ngoài DB theo quy trình không giữ transaction lâu.
- Chuyển sang `CONFIRMED` khi hợp lệ.
- Hủy/giải phóng `HELD` hết hạn qua một workflow an toàn.

### 18.4. Có cần thêm locking thủ công không?

Nếu bài toán chỉ là ngăn hai lịch của cùng phòng chồng thời gian, EXCLUDE đã cung cấp ràng buộc cốt lõi. Khóa thủ công có thể cần cho các quy tắc khác như giới hạn tổng số chỗ, đặt nhiều tài nguyên trong một giỏ hay quản lý phiên giữ chỗ, nhưng không nên coi `SELECT ... FOR UPDATE` trên các hàng hiện có là thay thế đơn giản cho EXCLUDE.

Khi không có hàng lịch nào trùng trước đó, `SELECT FOR UPDATE` không tự khóa “sự vắng mặt của một khoảng” theo cách dễ suy luận. EXCLUDE diễn đạt quy tắc và cho database thực thi ràng buộc an toàn hơn trước race condition của hai transaction.

## 19. Nâng cao: nhiều tài nguyên, tenant và điều kiện theo nhóm

### 19.1. Cùng phòng mới là xung đột

Constraint:

```sql
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
```

ngăn chồng lấn trong **một phòng**, nhưng cho phép các phòng khác dùng cùng khung giờ.

### 19.2. Hệ thống đa tenant

Nếu hai tenant có thể dùng cùng giá trị `room_id` nhưng dữ liệu được chia chung bảng, cần đưa **tenant_id** vào logic loại trừ.

Ví dụ phần ràng buộc:

```sql
EXCLUDE USING gist (
    tenant_id WITH =,
    room_id WITH =,
    during WITH &&
)
```

Với `tenant_id bigint NOT NULL` và `room_id bigint NOT NULL`, extension `btree_gist` cung cấp operator class phù hợp cho phép so sánh equality theo GiST.

Ý nghĩa:

> Hai hàng chỉ xung đột khi **cùng tenant, cùng room và khoảng thời gian giao nhau**.

Không đưa `tenant_id` vào khi khóa phòng chỉ duy nhất trong từng tenant có thể khiến tenant A chặn lịch tenant B hoặc dẫn tới cấu trúc ràng buộc không phù hợp nghiệp vụ.

Trong schema đa tenant, còn phải thiết kế foreign key chứa tenant ID ở những quan hệ cần bảo đảm cùng tenant, và phân quyền/RLS phù hợp. Exclusion constraint chỉ đảm bảo **không chồng lấn**, không tự ngăn đọc dữ liệu tenant khác.

### 19.3. Khi cần nhiều điều kiện

Một ví dụ khác: một thiết bị không được cấp cho hai nhân viên cùng lúc:

```sql
EXCLUDE USING gist (
    equipment_id WITH =,
    usage_period WITH &&
)
```

Một tổ chức quản lý khóa hiệu lực dữ liệu theo mã đối tượng:

```sql
EXCLUDE USING gist (
    entity_id WITH =,
    valid_period WITH &&
)
```

Điểm chung không phải tên cột, mà là **ít nhất một điều kiện trong tập so sánh phải không TRUE giữa hai hàng bất kỳ**.

### 19.4. Nếu một tài nguyên chỉ cho phép tối đa hai lượt cùng lúc?

EXCLUDE đơn giản theo `resource_id WITH =` và `period WITH &&` thực thi **không quá một** lượt cùng thời điểm.

Bài toán “tối đa hai” hoặc “tổng công suất không vượt 30” không được biểu diễn trực tiếp bằng đúng constraint này. Cần mô hình thêm slot độc lập, capacity units, locking/transaction logic hoặc thiết kế khác phù hợp. Không cố biến toán tử `&&` thành phép đếm số hàng đang chồng.

## 20. EXCLUDE và partitioned tables

Partitioning là một trường hợp cần thiết kế thận trọng. Nếu bảng lịch được chia thành nhiều partition theo tháng hoặc theo tenant, hai hàng xung đột có thể rơi vào **hai partition khác nhau**.

Một exclusion constraint chỉ được tạo hoặc kiểm tra trong phạm vi một partition sẽ không tự bảo đảm không có xung đột **xuyên mọi partition**. Hỗ trợ constraint trên partitioned table và các yêu cầu về partition key có thể khác theo phiên bản PostgreSQL.

Khi chọn partitioning:

1. Đọc đúng khả năng exclusion constraint của **phiên bản PostgreSQL đang chạy**.
2. Kiểm tra có được phép tạo constraint ở bảng cha không và các cột partition key bắt buộc phải tham gia equality hay không.
3. Thiết kế partition key sao cho các lịch có khả năng xung đột luôn thuộc phạm vi constraint được kiểm tra.
4. Test thực tế hai khoảng giao nhau nằm ở hai bên ranh giới partition.
5. Không chỉ test hai lịch cùng ngày/cùng tháng rồi kết luận toàn bảng đã được bảo vệ.

Ví dụ nếu partition theo **ngày bắt đầu**, một lượt 23:30–00:30 và một lượt 00:00–01:00 có thể nằm ở hai partition ngày khác nhau nhưng vẫn chồng lấn. Nếu ràng buộc không bao phủ xuyên partition, dữ liệu sai có thể lọt qua.

Đối với hệ thống đơn giản, hãy làm đúng exclusion constraint trên **bảng thường** trước khi thêm partitioning.

## 21. Thêm constraint vào bảng đã có dữ liệu

Nếu bảng đã chứa lịch chồng lấn, việc thêm exclusion constraint sẽ phải kiểm tra dữ liệu hiện có và có thể **thất bại** vì xung đột.

Ví dụ về mặt cú pháp:

```sql
ALTER TABLE booking_lab.reservations
ADD CONSTRAINT another_no_overlap_rule
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
WHERE (status IN ('HELD', 'CONFIRMED'));
```

**Không chạy đoạn này trên bảng lab đã có cùng ràng buộc**: nó tạo một ràng buộc gần như trùng và index bổ sung không cần thiết.

Trong dự án thật, quy trình migration nên:

- Kiểm tra trước các cặp lịch đang chồng lấn.
- Xác định cách xử lý các trường hợp lịch sử bị sai.
- Chọn cửa sổ migration và đánh giá tác động lock/index build.
- Thực hiện migration với rollback/khôi phục được hoạch định.
- Sau migration kiểm tra bằng thao tác cạnh tranh và dữ liệu biên.

### 21.1. Truy vấn tìm xung đột hiện có

Nếu đang chuẩn bị chuyển từ schema chưa có EXCLUDE sang có EXCLUDE, một phép tự join có thể giúp tìm cặp bản ghi xung đột:

```sql
SELECT
    a.reservation_id AS first_reservation,
    b.reservation_id AS second_reservation,
    a.room_id,
    a.during AS first_period,
    b.during AS second_period
FROM booking_lab.reservations AS a
JOIN booking_lab.reservations AS b
  ON a.room_id = b.room_id
 AND a.reservation_id < b.reservation_id
 AND a.during && b.during
WHERE a.status IN ('HELD', 'CONFIRMED')
  AND b.status IN ('HELD', 'CONFIRMED')
ORDER BY a.room_id, a.reservation_id, b.reservation_id;
```

Ở schema lab đã có constraint đúng, truy vấn thường không có kết quả cho các lịch active do chính constraint ngăn xung đột. Trong database legacy, nó giúp phát hiện dữ liệu cần dọn trước khi áp ràng buộc.

Điều kiện `a.reservation_id < b.reservation_id` giúp tránh ghép một hàng với chính nó và tránh báo cùng một cặp theo hai thứ tự.

## 22. Xử lý lỗi EXCLUDE trong ứng dụng Java/JDBC

Khi PostgreSQL từ chối một lượt đặt trùng, ứng dụng nên phân biệt **xung đột nghiệp vụ** với lỗi kỹ thuật.

Ví dụ Java/JDBC rút gọn:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public class ReservationService {
    public void createReservation(
            Connection connection,
            long roomId,
            java.time.OffsetDateTime start,
            java.time.OffsetDateTime end) throws SQLException {

        String sql = """
            INSERT INTO booking_lab.reservations(room_id, during, status)
            VALUES (
                ?,
                tstzrange(?::timestamptz, ?::timestamptz, '[)'),
                'CONFIRMED'
            )
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setLong(1, roomId);
            statement.setObject(2, start);
            statement.setObject(3, end);

            try {
                statement.executeUpdate();
            } catch (SQLException error) {
                if ("23P01".equals(error.getSQLState())) {
                    // Xung đột lịch: trả thông báo nghiệp vụ phù hợp.
                    // Transaction hiện tại cần được xử lý/rollback đúng.
                    throw new IllegalStateException(
                        "Khung giờ này đã có lịch đặt xung đột",
                        error
                    );
                }
                throw error;
            }
        }
    }
}
```

Đây là ví dụ về **SQLSTATE**, không phải một chương trình Java hoàn chỉnh. Dự án cần driver PostgreSQL JDBC, datasource, validation và transaction manager phù hợp.

Một số lưu ý:

- `OffsetDateTime` có offset rõ ràng, giúp tránh nhầm múi giờ.
- Thời điểm bắt đầu phải **trước** kết thúc; API nên kiểm tra sớm và database giữ constraint.
- Khi `INSERT` lỗi trong transaction đang mở, cần rollback hoặc transaction manager xử lý.
- Nếu constraint là deferred, lỗi có thể xuất hiện lúc **COMMIT**, không phải ngay tại `executeUpdate()`. Nơi bắt lỗi phải bao trùm cả thao tác commit.
- Nếu ứng dụng có nhiều loại exclusion constraint, chỉ kiểm tra `SQLSTATE 23P01` chưa đủ để biết xung đột đến từ quy tắc nào; có thể kiểm tra **tên constraint** qua thông tin lỗi có cấu trúc của driver, tránh so khớp chuỗi thông báo được dịch.
- Không trả toàn bộ PostgreSQL `DETAIL` cho người dùng cuối nếu nó chứa thông tin lịch của người khác; thông tin lỗi có thể làm lộ dữ liệu nội bộ.
- HTTP API thường có thể ánh xạ xung đột lịch thành phản hồi nghiệp vụ như `409 Conflict`, nhưng cần thống nhất với hợp đồng API và tình huống retry/idempotency.

**Không nên xử lý SQLSTATE bằng cách chèn lại lịch ở một thời gian khác mà chưa có lựa chọn của người dùng.** Constraint chỉ xác nhận dữ liệu xung đột; việc đề xuất khung giờ thay thế là logic ứng dụng.

## 23. EXCLUDE có thay thế được SERIALIZABLE không?

Không nên xem EXCLUDE, khóa hàng và isolation level như ba cách dùng thay thế tùy ý.

### 23.1. EXCLUDE là ràng buộc dữ liệu

Nó bảo đảm một quy tắc cụ thể:

> Không có hai hàng cùng phòng với khoảng active chồng lấn.

Khi có giao dịch đồng thời, PostgreSQL xử lý xung đột để duy trì ràng buộc.

### 23.2. SERIALIZABLE là isolation level

`SERIALIZABLE` xử lý tính đúng đắn của **toàn bộ tập giao dịch** so với một lịch tuần tự theo ngữ nghĩa PostgreSQL. Nó có thể phát hiện tình huống phụ thuộc dữ liệu và yêu cầu transaction retry với lỗi serialization failure, thường có SQLSTATE `40001`.

Nhưng dùng SERIALIZABLE không khiến database tự biết quy tắc “hai lịch không được giao nhau” nếu ứng dụng không thực hiện logic kiểm tra/ghi đúng. Và dù có EXCLUDE, hệ thống vẫn có thể cần isolation level/locking thích hợp cho các nghiệp vụ khác.

### 23.3. Nên kết hợp thế nào?

- Dùng **EXCLUDE** để biểu diễn bất biến dữ liệu “không trùng khoảng”.
- Dùng **CHECK** cho các điều kiện một hàng như độ dài khoảng.
- Dùng **FOREIGN KEY** cho quan hệ phòng tồn tại.
- Dùng **transaction** để gộp tạo lịch, ghi trạng thái và các bảng liên quan.
- Chọn **isolation level** và chiến lược retry dựa trên toàn bộ nghiệp vụ.
- Dùng locking riêng khi cần phối hợp nhiều nguồn lực hoặc công việc không thể gói trong một constraint.

Đó là các lớp bảo vệ bổ sung, không phải một công cụ thay hết các công cụ khác.

## 24. Những sai lầm thường gặp

### 24.1. Dùng UNIQUE cho hai cột start/end

`UNIQUE(room_id, start_at, end_at)` chỉ chống trùng **chính xác các giá trị khóa**, không ngăn hai khoảng giao nhau một phần. Dùng EXCLUDE với `&&` hoặc mô hình khác thực thi đúng business invariant.

### 24.2. Chỉ SELECT kiểm tra trống rồi INSERT

Hai transaction có thể cùng nhìn thấy phòng trống. EXCLUDE giúp database quyết định kết quả cuối trong tình huống đồng thời.

### 24.3. Quên extension btree_gist

Khi khai báo `room_id WITH =` trên kiểu scalar như `bigint` cùng `USING gist`, PostgreSQL có thể báo thiếu operator class thích hợp nếu `btree_gist` chưa được cài trong database.

Kiểm tra:

```sql
SELECT extname
FROM pg_extension
WHERE extname = 'btree_gist';
```

Cài extension với quyền phù hợp trong đúng database, không cố đổi `USING gist` thành `USING btree` cho toán tử range overlap.

### 24.4. Cho room_id hoặc during là NULL

Khi một phép so sánh trong EXCLUDE trả NULL, cặp hàng có thể không vi phạm. Cần `NOT NULL` cho cột định danh tài nguyên và range nếu nghiệp vụ yêu cầu.

### 24.5. Quên CHECK khoảng rỗng

Một khoảng `empty` không giao với lịch khác. Nếu “đặt phòng 0 phút” không hợp lệ, thêm `CHECK (NOT isempty(during))` hoặc dùng `CHECK(start_at < end_at)` khi lưu hai cột.

### 24.6. Dùng biên [] thay vì [)

Nếu cả hai lượt đặt đều bao gồm thời điểm kết thúc/bắt đầu 10:00, chúng có thể bị xem là giao nhau. Hãy thống nhất quy tắc khoảng nửa mở khi nghiệp vụ muốn cho đặt liền kề.

### 24.7. Quên trạng thái CANCELLED trong constraint

Nếu không cần lịch hủy chiếm phòng, nên dùng partial exclusion predicate chỉ áp dụng cho trạng thái active. Ngược lại, nếu một phần trạng thái như `HELD` vẫn giữ chỗ, phải bao gồm nó trong predicate.

### 24.8. Nghĩ thời gian hết hạn tự làm thay đổi partial index

Một bản ghi HELD không tự rời index khi đồng hồ vượt thời hạn nếu predicate chỉ xét status. Phải có workflow chuyển trạng thái, không dựa vào `now()` trong index predicate.

### 24.9. Nghĩ EXCLUDE tự tạo index B-tree thường

EXCLUDE sử dụng access method đã chỉ định, trong ví dụ là **GiST**. GiST phục vụ toán tử range và kiểm tra xung đột; không thay thế mọi index B-tree cần cho truy vấn equality/sort khác.

### 24.10. Dùng DEFERRABLE mà không xử lý lỗi tại COMMIT

Một constraint deferred có thể báo lỗi khi commit. Nếu chỉ bắt lỗi ở câu INSERT, ứng dụng có thể bỏ sót thời điểm thất bại thực sự.

### 24.11. Không phân biệt SQLSTATE

`23P01` là exclusion violation; `23505` là unique violation; `40001` thường là serialization failure; lock timeout và deadlock có mã khác. Không nên xử lý mọi lỗi SQL như “đã có người đặt phòng”.

### 24.12. Tin rằng index partial phù hợp mọi truy vấn

GiST index chỉ chứa các hàng thuộc predicate. Một truy vấn muốn xem cả lịch CANCELLED có thể cần kế hoạch truy vấn/index khác; không nên ép planner dựa vào index chỉ dành cho lịch active.

### 24.13. Không tính đến partition boundary

Nếu partition theo tháng/ngày, một lịch đi qua ranh giới partition có thể chồng lên lịch ở partition khác. Cần hiểu giới hạn và quy tắc constraint trên partitioned tables theo phiên bản đang dùng.

### 24.14. Nghĩ EXCLUDE là đủ cho toàn bộ hệ thống booking

EXCLUDE ngăn xung đột một tài nguyên trong bảng dữ liệu. Nó không tự xác thực người dùng, chặn thanh toán trùng, giải quyết lịch ngoài PostgreSQL, hay giới hạn tổng số phòng/sức chứa theo nhiều hàng.

## 25. Bài tập có lời giải

### Bài 1. Hai lịch nào giao nhau?

Cho các khoảng:

```text
A = [09:00, 10:00)
B = [10:00, 11:00)
C = [09:59, 10:01)
D = [08:00, 09:00)
```

**Câu hỏi:** các cặp nào giao nhau?

**Lời giải:** A và B không giao nhau; A và D không giao nhau; C giao với A và B. D và C không giao nhau. Ký hiệu `[)` khiến thời điểm cuối không thuộc khoảng trước.

### Bài 2. Vì sao UNIQUE không đủ?

Có hai lịch:

```text
room_id=101, [09:00,10:00)
room_id=101, [09:30,10:30)
```

**Lời giải:** hai cặp start/end khác nhau nên UNIQUE theo room/start/end không phát hiện. EXCLUDE theo `room_id WITH =` và `during WITH &&` phát hiện vì cùng phòng và chồng lấn.

### Bài 3. Cho phép đặt cùng thời gian ở hai phòng

**Yêu cầu:** phòng 101 và phòng 102 được đặt 09:00–10:00 đồng thời.

**Lời giải:** EXCLUDE có điều kiện `room_id WITH =`. Khi phòng khác nhau, phép so sánh room_id FALSE nên không xung đột, dù range overlap TRUE.

### Bài 4. Lịch hủy có được giữ chỗ không?

Bảng có partial EXCLUDE:

```sql
WHERE (status IN ('HELD', 'CONFIRMED'))
```

**Lời giải:** lịch CANCELLED không thuộc phạm vi index/ràng buộc này; nó không ngăn một lịch CONFIRMED mới trùng khoảng, nếu không có lịch active khác. Nhưng nếu đổi chính lịch CANCELLED đó thành CONFIRMED, PostgreSQL sẽ kiểm tra lại và có thể từ chối.

### Bài 5. Tại sao NULL nguy hiểm?

Nếu `room_id` cho phép NULL, hai hàng đều có room_id NULL, thời gian chồng nhau.

**Lời giải:** `NULL = NULL` không TRUE; do đó EXCLUDE có thể không coi cặp hàng là xung đột. Dùng `room_id NOT NULL` hoặc mô hình định danh khác phù hợp nghiệp vụ.

### Bài 6. Vì sao cần CHECK( NOT isempty(during) )?

**Lời giải:** range rỗng không chứa thời điểm nào và không chồng với lịch khác. Nếu ứng dụng không cho đặt lịch độ dài bằng 0, ràng buộc CHECK loại trường hợp EXCLUDE không thể tự ngăn.

### Bài 7. Hai request đồng thời cùng tạo lịch

Transaction A và B đều SELECT thấy 14:00–15:00 trống, rồi đều INSERT lịch giao nhau.

**Lời giải:** bước SELECT không bảo vệ khỏi race. EXCLUDE khiến kết quả đã commit không thể chứa cả hai lịch trùng; một transaction có thể phải đợi, thất bại hoặc bị rollback tùy trình tự. Ứng dụng xử lý `23P01` để trả xung đột nghiệp vụ.

### Bài 8. Hoán đổi hai lịch với DEFERRABLE

Có A=[09:00,10:00), B=[10:00,11:00). Muốn đổi vị trí A/B trong một transaction.

**Lời giải:** với EXCLUDE `DEFERRABLE`, dùng `SET CONSTRAINTS ... DEFERRED` trong transaction, cập nhật cả hai rồi commit. Trạng thái cuối phải không chồng lấn; nếu còn xung đột, COMMIT không thành công.

### Bài 9. Phân biệt daterange và tstzrange

Một hệ thống quản lý ngày nghỉ phép từ 14/11 đến hết 16/11, không quan tâm giờ trong ngày.

**Lời giải:** `daterange(DATE '2026-11-14', DATE '2026-11-17', '[)')` phù hợp hơn `tstzrange` cho quy tắc ngày lịch. Với lịch họp có giờ bắt đầu/kết thúc và múi giờ, `tstzrange` thường đúng hơn.

### Bài 10. Có thể dùng partial predicate dựa trên now()?

Một người muốn:

```sql
-- Ý tưởng không phù hợp cho partial index:
-- WHERE hold_expires_at > now()
```

**Lời giải:** predicate của index cần biểu thức phù hợp tính bất biến, không dùng hàm thời gian biến thiên như `now()` để “tự đổi tư cách giữ chỗ” khi đồng hồ trôi qua. Dùng trạng thái được cập nhật bởi workflow và thiết kế transaction nhất quán.

### Bài 11. EXCLUDE có giải quyết giới hạn tối đa ba phòng họp cùng lúc không?

**Lời giải:** không trực tiếp. EXCLUDE trên từng room_id ngăn hai lịch của **cùng phòng** giao nhau, nhưng không đếm tổng số lịch đồng thời trên một nhóm tài nguyên. Cần mô hình capacity hoặc logic ràng buộc bổ sung.

### Bài 12. Kiểm tra cấu trúc constraint bằng SQL nào?

**Lời giải:**

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'booking_lab.reservations'::regclass
  AND contype = 'x';
```

Có thể xem index trong `pg_indexes` hoặc dùng `\d+ booking_lab.reservations` ở psql.

## 26. Bảng tra cứu nhanh

| Nhu cầu | Công cụ/cú pháp | Lưu ý |
|---|---|---|
| Biểu diễn khoảng thời gian xác định | `tstzrange(start,end,'[)')` | Từ hai instant `timestamptz` |
| Khoảng theo giờ địa phương | `tsrange(start,end,'[)')` | Không tự mang time zone |
| Khoảng ngày lịch | `daterange(start_date,end_date,'[)')` | Dùng cho ngày, có canonicalization |
| Hai range giao nhau? | `a && b` | TRUE khi có phần giao |
| Hai range sát nhau? | `a -|- b` | Không phải overlap |
| Range chứa thời điểm? | `a @> instant` | Dùng trong lịch hiện tại |
| Range rỗng? | `isempty(a)` | Cần CHECK nếu không cho phép |
| Đầu/cuối range | `lower(a)`, `upper(a)` | Có thể không có bound |
| Kiểm tra bound không giới hạn | `lower_inf(a)`, `upper_inf(a)` | Dùng khi nghiệp vụ yêu cầu hữu hạn |
| Giữ đầu, bỏ cuối | `'[)'` | Hai lịch sát nhau không giao |
| Cùng phòng và chồng thời gian | `EXCLUDE USING gist (room_id WITH =, during WITH &&)` | Cần operator classes tương thích |
| Equality bigint trong GiST | `CREATE EXTENSION btree_gist` | Cài đúng database và đủ quyền |
| Chỉ giới hạn active | `WHERE (status IN (...))` | Partial exclusion |
| Không cho NULL | `NOT NULL` | Tránh comparison UNKNOWN làm lọt xung đột |
| Cho phép trạng thái trung gian trong transaction | `DEFERRABLE` + `SET CONSTRAINTS ... DEFERRED` | Vẫn phải hợp lệ khi commit |
| Lỗi vi phạm exclusion | SQLSTATE `23P01` | Xử lý như conflict nghiệp vụ khi thích hợp |
| Kiểm tra metadata | `pg_constraint`, `pg_get_constraintdef` | `contype = 'x'` |
| Xem index | `pg_indexes`, `\d+` | GiST index được tạo cùng constraint |
| Tìm lịch chồng khoảng đề xuất | `during && tstzrange(...)` | Chỉ là query UI, không thay EXCLUDE |
| Cấm interval start>=end | `CHECK (start_at < end_at)` | Khi dùng hai cột start/end |
| Cấm range rỗng | `CHECK (NOT isempty(during))` | Bổ sung cho EXCLUDE |

## 27. Tổng kết: đưa bất biến “không chồng lấn” vào database

Để ngăn một tài nguyên có hai khoảng thời gian giao nhau, PostgreSQL cung cấp tổ hợp mạnh:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Bên trong CREATE TABLE hoặc ALTER TABLE:
CONSTRAINT no_overlap
EXCLUDE USING gist (
    resource_id WITH =,
    occupied_period WITH &&
)
```

Cần nhớ:

1. **`EXCLUDE`** biểu diễn quy tắc so sánh **giữa các hàng**, khác với `CHECK` chỉ kiểm tra điều kiện của một hàng và `UNIQUE` chỉ chặn trùng khóa.
2. **`&&`** là toán tử xác định hai khoảng giao nhau. Dùng quy tắc biên `[)` khi muốn hai lượt tiếp giáp nhau được cho phép.
3. **GiST + `btree_gist`** là tổ hợp phổ biến để kết hợp equality trên ID tài nguyên với overlap trên range.
4. **NOT NULL và kiểm tra khoảng rỗng** là những điều kiện bổ sung quan trọng; EXCLUDE không tự ngăn toàn bộ trường hợp giá trị thiếu/không hợp lệ.
5. **Partial exclusion** chỉ giới hạn những hàng phù hợp predicate, chẳng hạn HELD/CONFIRMED; cập nhật trạng thái cũng phải tuân thủ constraint.
6. **DEFERRABLE** cho phép transaction điều chỉnh nhiều hàng qua trạng thái trung gian tạm thời, nhưng dữ liệu cuối vẫn phải hợp lệ.
7. **Concurrency:** hai request có thể đều đọc thấy chỗ trống, nhưng constraint ở database mới là hàng rào cuối ngăn hai lịch trùng cùng được commit.
8. **Thiết kế ứng dụng vẫn cần đầy đủ:** xác thực quyền đặt, trạng thái giữ chỗ, xử lý SQLSTATE `23P01`, transaction ngắn, chỉ mục phù hợp và kiểm soát nguồn dữ liệu.

Khi một quy tắc nghiệp vụ là **“không được tồn tại hai hàng có cùng khóa nhóm và các khoảng chồng nhau”**, `EXCLUDE USING gist` là một công cụ PostgreSQL đặc biệt phù hợp. Nó biến một kiểm tra dễ bị bỏ sót hoặc gặp race condition trong ứng dụng thành **ràng buộc toàn vẹn có thể thực thi ngay ở cơ sở dữ liệu**.

