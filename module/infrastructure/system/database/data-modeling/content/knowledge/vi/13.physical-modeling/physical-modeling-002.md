# Thiết kế cột bắt buộc, giá trị mặc định và ràng buộc kiểm tra

## 1. Vì sao ba quyết định này quan trọng trong mô hình vật lý?

Trong module `DATABASE_DATA_MODELING`, mục tiêu là chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng và có thể kiểm chứng: từ thực thể, quan hệ, ràng buộc, chuẩn hóa, khóa và chỉ mục đến lược đồ vật lý. Khi triển khai trên một hệ quản trị cơ sở dữ liệu (DBMS), ba cơ chế căn bản giúp bảo vệ ý nghĩa của **từng cột và từng hàng** là:

- **`NOT NULL`**: một cột có bắt buộc phải có giá trị hay không.
- **`DEFAULT`**: hệ quản trị lấy giá trị gì khi câu lệnh ghi **không cung cấp** giá trị cho cột.
- **`CHECK`**: giá trị hoặc tổ hợp giá trị trong một hàng có thỏa điều kiện cho phép không.

Ba cơ chế giải quyết **ba câu hỏi khác nhau**. Một cột có `DEFAULT` chưa chắc đã bắt buộc; một cột có `CHECK` cũng chưa chắc đã cấm `NULL`. Thiết kế đúng phải bắt đầu bằng ngữ nghĩa nghiệp vụ, rồi chọn kiểu dữ liệu và ràng buộc mà DBMS thực sự hỗ trợ.

**Kết quả cần đạt:** từ một yêu cầu như “mỗi lượt đặt lịch có ít nhất một người tham dự, trạng thái ban đầu là nháp, thời điểm kết thúc sau thời điểm bắt đầu”, người học có thể quyết định cột nào `NOT NULL`, cột nào có `DEFAULT`, dùng `CHECK` ra sao, và kiểm thử dữ liệu không hợp lệ ở biên.

## 2. Bước đầu: xác định ý nghĩa của “thiếu giá trị”

Xét hệ thống đặt lịch tư vấn. Một lượt đặt lịch có khách hàng, thời điểm bắt đầu/kết thúc, số người tham dự, trạng thái, phí đã chốt và lý do hủy (nếu có). Trước khi viết SQL, cần xác định:

| Thuộc tính logic | Có được thiếu? | Giá trị mặc định hợp lý? | Quy tắc hợp lệ |
|---|---|---|---|
| Mã lượt đặt lịch | Không | Có thể để DBMS sinh | Định danh duy nhất |
| Khách hàng | Không | Không | Phải tham chiếu khách hàng tồn tại |
| Bắt đầu và kết thúc | Không | Không | Kết thúc phải sau bắt đầu |
| Số người tham dự | Không | `1` nếu nghiệp vụ thật sự xác định “không nhập nghĩa là một người” | Từ 1 đến 12 |
| Trạng thái | Không | `DRAFT` | Chỉ `DRAFT`, `CONFIRMED`, `CANCELLED` |
| Phí đã chốt | Không | **Không tự giả định là 0** | Không âm; có độ chính xác tiền tệ phù hợp |
| Lý do hủy | Có điều kiện | Không | Bắt buộc có nội dung khi đã hủy, phải để trống khi chưa hủy |
| Thời điểm tạo | Không | Thời điểm do hệ thống ghi nhận | Diễn đạt một thời điểm thực, có quy ước múi giờ |

Phân biệt các tình huống:

1. **Chưa biết:** chưa có ngày giao dự kiến; `NULL` có thể mang nghĩa hợp lệ.
2. **Không áp dụng:** lý do hủy chưa tồn tại vì lịch chưa bị hủy; `NULL` có thể hợp lệ với điều kiện phụ thuộc trạng thái.
3. **Người dùng không nhập nhưng có quy tắc suy ra:** số người tham dự mặc định là một; có thể dùng `DEFAULT 1`.
4. **Dữ liệu bắt buộc nhưng chưa được cung cấp:** khách hàng hoặc phí chưa chốt; phải từ chối thao tác hoặc chưa tạo bản ghi hoàn chỉnh.

Không dùng một giá trị giả như ngày `1970-01-01`, chuỗi `'UNKNOWN'`, `-1` hay `0` thay cho “chưa biết” chỉ để tránh `NULL`. Các giá trị giả sẽ tham gia lọc, tổng hợp và so sánh như dữ liệu thật, dẫn đến sai lệch khó phát hiện.

## 3. `NOT NULL`: cột bắt buộc có giá trị

### 3.1. Ngữ nghĩa của `NULL`

Trong SQL, `NULL` biểu diễn thiếu hoặc không xác định một giá trị; nó không bằng số `0`, chuỗi rỗng `''`, khoảng trắng, `FALSE` hay ngày mặc định. So sánh thông thường với `NULL` có thể cho kết quả **UNKNOWN**.

```sql
-- PostgreSQL: cả hai biểu thức sau không trả TRUE/FALSE thông thường.
SELECT NULL = NULL;  -- NULL (UNKNOWN)
SELECT 5 > NULL;     -- NULL (UNKNOWN)

-- Muốn kiểm tra sự hiện diện của dữ liệu:
SELECT NULL IS NULL;     -- TRUE
SELECT 5 IS NOT NULL;    -- TRUE
```

Với một cột được khai báo `NOT NULL`, DBMS không cho chèn hoặc cập nhật hàng nếu giá trị kết quả của cột là `NULL`. Nó bảo vệ cả khi dữ liệu đến từ ứng dụng, script SQL, tác vụ nhập liệu hoặc một hệ thống tích hợp khác.

```sql
CREATE TABLE consultation_customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name   VARCHAR(120) NOT NULL,
    email       VARCHAR(254) NOT NULL,
    CONSTRAINT uq_consultation_customer_email UNIQUE (email),
    CONSTRAINT ck_consultation_customer_name
        CHECK (char_length(btrim(full_name)) > 0)
);
```

Ở đây, `full_name NOT NULL` chỉ cấm `NULL`. Nó vẫn cho phép `''` hoặc `'   '` nếu không có `CHECK` bổ sung. Ràng buộc `char_length(btrim(full_name)) > 0` xử lý chuỗi rỗng và chuỗi chỉ chứa dấu cách thông thường; `btrim` mặc định của PostgreSQL không thay thế mọi quy tắc chuẩn hóa Unicode hay mọi loại ký tự trắng. Chính sách tên hợp lệ phải được mô tả rõ nếu yêu cầu chặt chẽ hơn.

### 3.2. Chọn cột bắt buộc theo trạng thái nghiệp vụ

Đừng gắn `NOT NULL` chỉ vì UI hiện tại có dấu sao. Hãy hỏi: bản ghi có bao giờ được lưu khi chưa đủ thông tin không? Một đơn hàng `DRAFT` có thể chưa có địa chỉ giao hàng; một đơn đã `CONFIRMED` có thể yêu cầu địa chỉ. Khi đó, địa chỉ không phải “bắt buộc cho mọi hàng”, mà **bắt buộc có điều kiện theo trạng thái**; có thể kết hợp cột cho phép `NULL` với `CHECK` liên cột hoặc thiết kế vòng đời tách bảng.

Ngược lại, nếu cột là khóa ngoại bắt buộc, cần cả `NOT NULL` **và** `FOREIGN KEY`: khóa ngoại đơn thuần có thể cho phép `NULL` khi cột tham chiếu không bắt buộc.

### 3.3. Hệ quả khi thêm `NOT NULL` vào bảng có sẵn

Nếu bảng đã có dữ liệu `NULL`, câu lệnh bổ sung `NOT NULL` có thể thất bại; phải kiểm tra, xử lý từng nhóm dữ liệu cũ và xác định ai có thẩm quyền điền giá trị. Đổi mọi `NULL` thành `0` hoặc `'N/A'` chưa chắc đúng nghiệp vụ. Trên bảng lớn, việc kiểm tra và khóa trong quá trình sửa schema còn tác động đến thời gian đáp ứng, nên cần lên kế hoạch migration.

## 4. `DEFAULT`: hành vi khi giá trị không được cung cấp

`DEFAULT` định nghĩa giá trị mà DBMS sử dụng cho cột nếu `INSERT` bỏ qua cột đó hoặc ghi rõ từ khóa `DEFAULT`. Đây là tiện ích có ngữ nghĩa nghiệp vụ, **không phải** cách thay thế `NOT NULL` hay sửa mọi dữ liệu thiếu.

```sql
CREATE TABLE default_demo (
    demo_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label   TEXT NOT NULL,
    active  BOOLEAN NOT NULL DEFAULT TRUE
);

-- Bỏ qua active: DBMS dùng TRUE.
INSERT INTO default_demo (label) VALUES ('A');

-- Ghi rõ DEFAULT: DBMS cũng dùng TRUE.
INSERT INTO default_demo (label, active)
VALUES ('B', DEFAULT);

-- Ghi rõ NULL: không dùng DEFAULT; lệnh bị NOT NULL từ chối.
INSERT INTO default_demo (label, active)
VALUES ('C', NULL);
```

Ví dụ trên minh họa bằng PostgreSQL. Câu `INSERT` cuối **cố ý gây lỗi** và cần chạy riêng nếu thực hành trên cơ sở dữ liệu thử nghiệm.

### 4.1. Những loại mặc định thường gặp

| Kiểu mặc định | Ví dụ PostgreSQL | Khi nên dùng |
|---|---|---|
| Hằng số | `DEFAULT 1`, `DEFAULT 'DRAFT'`, `DEFAULT FALSE` | Nghiệp vụ xác nhận giá trị áp dụng cho mọi thao tác ghi bỏ qua cột |
| Thời điểm ghi | `DEFAULT CURRENT_TIMESTAMP` | Ghi thời điểm tạo nếu cơ sở dữ liệu là nguồn chuẩn |
| ID do DBMS sinh | `GENERATED ALWAYS AS IDENTITY` | Định danh kỹ thuật không cần người dùng cung cấp |
| Biểu thức/hàm hệ thống | Một hàm sinh UUID được DBMS/extension hỗ trợ | Cần thống nhất tính tương thích, cách sinh, độ duy nhất và phiên bản |

Những lựa chọn cần cân nhắc:

- **Giá trị mặc định phải có ý nghĩa đúng.** `status DEFAULT 'CONFIRMED'` nguy hiểm nếu “không chỉ định trạng thái” thực tế nghĩa là chưa được duyệt. `DRAFT` thường phù hợp hơn khi có bước xác nhận.
- **Không mặc định phí là 0** nếu chưa chốt phí; miễn phí là một thông tin thực sự, khác chưa biết phí. Muốn cho phép bản nháp chưa chốt phí, có thể để phí `NULL` ở giai đoạn nháp và thêm ràng buộc có điều kiện khi xác nhận.
- **Giá trị mặc định không cập nhật tự động trên mọi `UPDATE`.** `DEFAULT CURRENT_TIMESTAMP` cho `created_at` chỉ hỗ trợ khi tạo hàng. Muốn có `updated_at` phản ánh cập nhật, cần thiết kế cơ chế ứng dụng/trigger/hệ thống phù hợp và kiểm thử.
- **Thời điểm phụ thuộc DBMS.** Trong PostgreSQL, `CURRENT_TIMESTAMP` phản ánh thời điểm bắt đầu giao dịch, nên nhiều hàng cùng giao dịch có thể nhận cùng mốc. Nếu cần thời gian đồng hồ tại lúc gọi thực sự, phải cân nhắc hàm khác và yêu cầu vận hành.
- **Mặc định có thể che lỗi tích hợp.** Nếu tất cả sự kiện đều cần phân biệt kênh bán hàng, đặt `channel DEFAULT 'WEB'` sẽ âm thầm biến dữ liệu từ các kênh khác thành dữ liệu web khi bên gửi quên trường.

### 4.2. `DEFAULT` ở cơ sở dữ liệu hay ứng dụng?

Ứng dụng có thể gợi ý giá trị và hiển thị trên biểu mẫu; DBMS vẫn nên có mặc định nếu **mọi nguồn ghi** đều dùng chung chính sách. Hai nơi phải thống nhất để tránh tình huống API tạo `DRAFT` nhưng job nhập liệu tạo `CONFIRMED`. Khi cần biết người dùng có chủ động chọn một giá trị hay chỉ chấp nhận mặc định, hãy xem xét lưu nguồn gốc quyết định; `DEFAULT` tự nó không ghi lại “ai đã chọn”.

## 5. `CHECK`: cấm giá trị hoặc tổ hợp giá trị không hợp lệ

`CHECK` đặt biểu thức điều kiện trên hàng dữ liệu. Ví dụ:

```sql
-- Chỉ chấp nhận số người từ 1 đến 12.
CHECK (attendee_count BETWEEN 1 AND 12)

-- Phí không âm.
CHECK (agreed_fee >= 0)

-- Kết thúc sau bắt đầu.
CHECK (ends_at > starts_at)

-- Trạng thái thuộc tập cho phép.
CHECK (booking_status IN ('DRAFT', 'CONFIRMED', 'CANCELLED'))
```

Phạm vi phù hợp của `CHECK` là **bất biến của một hàng**: miền số, tập trạng thái, giới hạn chuỗi, quan hệ giữa hai thời điểm, quan hệ điều kiện giữa trạng thái và lý do hủy. Đặt tên như `ck_booking_time_order` giúp dễ tìm hiểu thông báo lỗi và migration.

### 5.1. Bẫy lớn nhất: SQL có ba giá trị logic

`CHECK` trong PostgreSQL và nhiều DBMS được thỏa khi biểu thức trả **TRUE** hoặc **UNKNOWN**; nó từ chối khi trả **FALSE**. Vì vậy:

| Giá trị `quantity` | `CHECK (quantity > 0)` | Kết quả |
|---|---|---|
| `5` | `TRUE` | Chấp nhận |
| `0` | `FALSE` | Từ chối |
| `-3` | `FALSE` | Từ chối |
| `NULL` | `UNKNOWN` | **Vẫn được chấp nhận** nếu không có `NOT NULL` |

Muốn `quantity` bắt buộc và dương, khai báo **cả hai**:

```sql
quantity INTEGER NOT NULL,
CONSTRAINT ck_quantity_positive CHECK (quantity > 0)
```

Tương tự, `CHECK (status IN (...))` không cấm `NULL`. Quy tắc “không thể để trống” là trách nhiệm của `NOT NULL`, còn `CHECK` bảo vệ miền giá trị.

Một biểu thức liên cột cũng phải xét `NULL` rõ ràng. Chẳng hạn `CHECK (cancelled_at > created_at)` không cấm `cancelled_at` thiếu, vì so sánh khi thiếu có kết quả `UNKNOWN`. Nếu quy tắc là “đã hủy thì phải có thời điểm hủy”, phải thêm điều kiện `IS NOT NULL` tương ứng.

### 5.2. Bất biến liên cột trong cùng một hàng

Quy tắc như “khi `booking_status = 'CANCELLED'` thì phải ghi lý do; còn khi không hủy thì không có lý do” là điều kiện có thể kiểm chứng bằng một `CHECK`:

```sql
CHECK (
    (
        booking_status = 'CANCELLED'
        AND cancellation_reason IS NOT NULL
        AND char_length(btrim(cancellation_reason)) > 0
    )
    OR
    (
        booking_status <> 'CANCELLED'
        AND cancellation_reason IS NULL
    )
)
```

Đây là ràng buộc **hai chiều**: hủy thì phải có lý do; không hủy thì không được gắn lý do. Nó giả định `booking_status NOT NULL`. Nếu không muốn buộc xóa lý do khi khôi phục lịch, cần đổi yêu cầu nghiệp vụ hoặc thiết kế bảng lịch sử hủy, thay vì âm thầm bỏ ràng buộc.

### 5.3. Điều `CHECK` không làm được

- **Không thay thế khóa duy nhất.** Quy tắc “không có hai khách hàng cùng email” cần `UNIQUE` hoặc cơ chế unique tương đương, kèm chính sách so sánh chữ hoa/chữ thường.
- **Không thay thế khóa ngoại.** Quy tắc “khách hàng phải tồn tại” cần `FOREIGN KEY`/tham chiếu thích hợp.
- **Không bảo vệ quan hệ giữa nhiều hàng bằng một `CHECK` thông thường.** Quy tắc “một phòng không có hai lịch trùng nhau” cần thiết kế riêng: ràng buộc loại trừ khi DBMS hỗ trợ, giao dịch/khóa đúng mức cô lập, hoặc cơ chế đồng bộ khác.
- **Không tự bảo vệ trạng thái lịch sử.** `CHECK (status IN (...))` không xác nhận chuyển trạng thái `DRAFT → CONFIRMED → CANCELLED` có hợp lệ hay không, vì mỗi hàng chỉ biểu diễn trạng thái hiện tại. Quy tắc chuyển trạng thái cần logic giao dịch hoặc mô hình lịch sử sự kiện.
- **Không nên phụ thuộc vào điều kiện thay đổi theo thời gian.** Một `CHECK` kiểu `starts_at > CURRENT_TIMESTAMP` có thể đúng lúc chèn nhưng sai sau một giờ, trong khi dữ liệu không được kiểm tra lại tự động. PostgreSQL còn giả định biểu thức `CHECK` có tính ổn định đối với dữ liệu của hàng. Với quy tắc “chỉ cho đặt lịch trong tương lai”, hãy xác thực tại thời điểm thực hiện thao tác nghiệp vụ.

## 6. Ví dụ hoàn chỉnh: thiết kế lược đồ PostgreSQL 16

Lược đồ sau giả định dịch vụ tư vấn giới hạn **1–12 người** mỗi lượt, mỗi lượt có một khách hàng, phí đã được chốt trước khi lưu lượt, và trạng thái mới là `DRAFT`. DDL này dùng một số cơ chế PostgreSQL, đặc biệt `IDENTITY`, `TIMESTAMPTZ` và `btrim`; DBMS khác cần ánh xạ lại.

```sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name   VARCHAR(120) NOT NULL,
    email       VARCHAR(254) NOT NULL,
    CONSTRAINT uq_customer_email UNIQUE (email),
    CONSTRAINT ck_customer_full_name_nonblank
        CHECK (char_length(btrim(full_name)) > 0)
);

CREATE TABLE booking (
    booking_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id         BIGINT NOT NULL,
    starts_at           TIMESTAMPTZ NOT NULL,
    ends_at             TIMESTAMPTZ NOT NULL,
    attendee_count      INTEGER NOT NULL DEFAULT 1,
    booking_status      VARCHAR(16) NOT NULL DEFAULT 'DRAFT',
    agreed_fee          NUMERIC(12, 2) NOT NULL,
    cancellation_reason TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_booking_customer
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id),
    CONSTRAINT ck_booking_attendee_count
        CHECK (attendee_count BETWEEN 1 AND 12),
    CONSTRAINT ck_booking_time_order
        CHECK (starts_at < ends_at),
    CONSTRAINT ck_booking_status
        CHECK (booking_status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    CONSTRAINT ck_booking_agreed_fee
        CHECK (agreed_fee >= 0 AND agreed_fee <> 'NaN'::NUMERIC),
    CONSTRAINT ck_booking_cancellation_reason
        CHECK (
            (
                booking_status = 'CANCELLED'
                AND cancellation_reason IS NOT NULL
                AND char_length(btrim(cancellation_reason)) > 0
            )
            OR
            (
                booking_status <> 'CANCELLED'
                AND cancellation_reason IS NULL
            )
        )
);
```

Ở đây, điều kiện `agreed_fee <> 'NaN'::NUMERIC` chặn giá trị đặc biệt `NaN` mà PostgreSQL cho phép với kiểu `NUMERIC`; nó là chi tiết vật lý của DBMS, không phải cú pháp SQL chung. `NUMERIC(12,2)` được chọn để minh họa, **không** bảo đảm phù hợp mọi loại tiền hoặc chính sách làm tròn. Nếu tính tiền nhiều loại tiền tệ, cần lưu đồng tiền, chính sách số chữ số thập phân và cách quy đổi; mô hình trên chỉ giả định một loại tiền đã được thống nhất ngoài bảng.

**Diễn giải theo hợp đồng dữ liệu:**

| Cột/nhóm cột | `NOT NULL` | `DEFAULT` | `CHECK` và ý nghĩa |
|---|---|---|---|
| `customer_id` | Có | Không | `FOREIGN KEY` xác nhận khách hàng tồn tại |
| `starts_at`, `ends_at` | Có | Không | `starts_at < ends_at` bảo vệ thứ tự thời gian |
| `attendee_count` | Có | `1` | Giới hạn từ 1 đến 12 |
| `booking_status` | Có | `'DRAFT'` | Chỉ ba giá trị hợp lệ |
| `agreed_fee` | Có | Không | Không âm và không chứa `NaN` trên PostgreSQL |
| `cancellation_reason` | Không | Không | Phụ thuộc điều kiện vào trạng thái |
| `created_at` | Có | `CURRENT_TIMESTAMP` | Phải được giữ làm dấu thời gian tạo |

Ví dụ chèn một khách hàng và lượt đặt lịch trong **cùng câu lệnh**; các cột `attendee_count`, `booking_status`, `created_at` đều bị lược bỏ nên DBMS sử dụng mặc định:

```sql
WITH new_customer AS (
    INSERT INTO customer (full_name, email)
    VALUES ('Minh An', 'minh-an@example.test')
    RETURNING customer_id
)
INSERT INTO booking (customer_id, starts_at, ends_at, agreed_fee)
SELECT
    customer_id,
    '2027-03-05 09:00:00+07'::TIMESTAMPTZ,
    '2027-03-05 10:00:00+07'::TIMESTAMPTZ,
    250000.00
FROM new_customer
RETURNING booking_id, attendee_count, booking_status, created_at;
```

Kết quả kỳ vọng ở ba cột liên quan mặc định là `attendee_count = 1`, `booking_status = 'DRAFT'` và `created_at` do DBMS ghi nhận. Giá trị `booking_id` được sinh từ `IDENTITY`.

Nếu sau đó thực hiện `UPDATE booking SET attendee_count = NULL WHERE ...`, thao tác bị `NOT NULL` từ chối; DBMS không lấy `DEFAULT 1` để thay thế `NULL`. Khi có chủ đích áp dụng lại mặc định, PostgreSQL cho phép `UPDATE booking SET attendee_count = DEFAULT WHERE ...`.

### Điều gì chưa được bảo vệ trong lược đồ?

Lược đồ không tự xác nhận email theo đặc tả gửi thư; `UNIQUE(email)` cũng không đương nhiên coi `A@example.test` và `a@example.test` là trùng. Chưa có quy tắc chống đặt trùng phòng, kiểm soát trạng thái chuyển đổi, quyền hủy và lịch sử thay đổi. Các quy tắc đó cần được mô hình hóa riêng theo nhu cầu nghiệp vụ; không nên tuyên bố lược đồ đã đáp ứng chúng chỉ vì có `CHECK`.

## 7. Bộ kiểm thử biên phải chạy trên DBMS thật

Không chỉ kiểm tra `INSERT` thành công. Hãy tạo cơ sở dữ liệu thử nghiệm, chạy các trường hợp độc lập và xác nhận DBMS thực sự từ chối hoặc chấp nhận đúng như yêu cầu. Sau mỗi lệnh dự kiến gây lỗi, cần kết thúc hoặc rollback giao dịch lỗi trước khi tiếp tục trên PostgreSQL.

| Tình huống | Kỳ vọng và ràng buộc chịu trách nhiệm |
|---|---|
| Bỏ `booking_status`, `attendee_count`, `created_at` trong `INSERT` | Nhận mặc định `DRAFT`, `1`, thời điểm tạo |
| Gửi `attendee_count = NULL` | Từ chối bởi `NOT NULL` dù có `DEFAULT 1` |
| Gửi `attendee_count = 0` hoặc `13` | Từ chối bởi `ck_booking_attendee_count` |
| Gửi `booking_status = 'DONE'` | Từ chối bởi `ck_booking_status` |
| Gửi `agreed_fee = -0.01` hoặc `'NaN'` | Từ chối bởi `ck_booking_agreed_fee` |
| Gửi `ends_at = starts_at` hoặc sớm hơn | Từ chối bởi `ck_booking_time_order` |
| `CANCELLED` với `cancellation_reason = NULL` hoặc `'   '` | Từ chối bởi `ck_booking_cancellation_reason` |
| `DRAFT` với `cancellation_reason = 'Khách yêu cầu hủy'` | Từ chối vì trạng thái và lý do mâu thuẫn |
| `CONFIRMED` với lý do hủy `NULL` | Chấp nhận |
| `customer_id = NULL` | Từ chối bởi `NOT NULL` |
| `customer_id` không tồn tại | Từ chối bởi `FOREIGN KEY` |
| `full_name = ''` hoặc chuỗi chỉ gồm dấu cách thông thường | Từ chối bởi `ck_customer_full_name_nonblank` |

Ví dụ truy vấn kiểm tra metadata thực tế trên PostgreSQL:

```sql
-- Kiểu dữ liệu, khả năng NULL, mặc định sau khi tạo bảng.
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'booking'
ORDER BY ordinal_position;

-- Định nghĩa ràng buộc được DBMS lưu.
SELECT
    conname,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.booking'::regclass
ORDER BY conname;
```

Ngoài giá trị âm/0/ngoài miền, cần kiểm thử Unicode, chuỗi rỗng, ký tự trắng đặc biệt, số sát giới hạn kiểu `NUMERIC`, chuyển đổi múi giờ và đường ghi dữ liệu không đi qua form UI. Những trường hợp này giúp phân biệt lỗi tại UI, lỗi ứng dụng và ràng buộc cơ sở dữ liệu.

## 8. Quyết định thay đổi khi chuyển DBMS

`NOT NULL`, `DEFAULT`, `CHECK` là khái niệm có tính phổ biến trong hệ quan hệ, nhưng hỗ trợ và cú pháp có khác biệt theo **sản phẩm, phiên bản, chế độ SQL và engine**.

| Câu hỏi | PostgreSQL 16 | MySQL 8.0/InnoDB | SQL Server 2022 |
|---|---|---|---|
| Thực thi `CHECK`? | Có; hỗ trợ ràng buộc hàng | Các bản **8.0.16 trở lên** mới thực thi `CHECK`; cần kiểm tra phiên bản thực tế | Có |
| Cột tự sinh ID? | `GENERATED ... AS IDENTITY` | `AUTO_INCREMENT` | `IDENTITY(1,1)` |
| Giá trị thời điểm hiện tại? | `CURRENT_TIMESTAMP` có ngữ nghĩa theo giao dịch | `CURRENT_TIMESTAMP`/`NOW()` và quy tắc múi giờ tùy kiểu | `SYSDATETIMEOFFSET()`/`SYSUTCDATETIME()` theo nhu cầu |
| Boolean có kiểu riêng? | `BOOLEAN` | `BOOLEAN` là bí danh của `TINYINT(1)` | `BIT` |
| Kiểu thời điểm dùng trong ví dụ | `TIMESTAMPTZ` | Chọn `TIMESTAMP` hay `DATETIME` dựa trên ngữ nghĩa | Thường cân nhắc `DATETIMEOFFSET` |
| Kiểm tra dữ liệu ngoài hàng? | `CHECK` không dùng cho tham chiếu liên bảng | Cần `FOREIGN KEY`/`UNIQUE` hoặc cơ chế chuyên biệt | Cần `FOREIGN KEY`/`UNIQUE` hoặc cơ chế chuyên biệt |

Vì khác biệt này, không nên sao chép trực tiếp biểu thức `'NaN'::NUMERIC`, `btrim(...)` hoặc cú pháp `IDENTITY` sang DBMS khác. Khi dùng MySQL, còn phải kiểm tra SQL mode, charset/collation và cách xử lý giá trị sai kiểu. Khi dùng SQL Server, `TIMESTAMP` không phải kiểu ngày giờ; đó là tên cũ của `ROWVERSION`.

Để đánh giá hỗ trợ của DBMS, kiểm tra ít nhất: phiên bản thực tế, khả năng thực thi `CHECK`, quy tắc nhận `NULL` trong `CHECK`, cú pháp mặc định, kiểu thời gian, độ chính xác số, cách ép kiểu và xử lý lỗi. Viết **thử nghiệm thất bại có chủ đích** quan trọng hơn giả định rằng DDL chạy được nghĩa là ràng buộc đã được thực thi.

## 9. Thêm ràng buộc an toàn vào bảng đã có dữ liệu

Chuyển cột `NULL` sang `NOT NULL` hoặc thêm `CHECK` có thể thất bại vì dữ liệu cũ, và có thể làm tăng thời gian khóa bảng. Quy trình migration nên đi từ khảo sát đến khắc phục rồi mới siết ràng buộc:

1. **Đọc ngữ nghĩa hiện tại:** những bản ghi bị thiếu có ý nghĩa gì? Có thể suy ra chính xác từ nguồn khác, cần xử lý thủ công hay phải chấp nhận trạng thái nháp?
2. **Đo dữ liệu vi phạm:** đếm `NULL`, giá trị ngoài miền, chuỗi chỉ chứa khoảng trắng và mâu thuẫn liên cột; đánh giá lượng dữ liệu/traffic trong giờ cao điểm.
3. **Chốt chính sách mới:** thống nhất `DEFAULT`, kiểm tra UI/API/job ghi dữ liệu, và phương án chuyển dữ liệu cũ có thể kiểm toán.
4. **Cập nhật nguồn ghi và backfill:** đảm bảo bản ghi mới theo quy tắc mới, xử lý dữ liệu cũ từng lô nếu cần.
5. **Áp ràng buộc và xác nhận:** kiểm tra DBMS, hiệu ứng khóa/thời gian; chạy test âm và theo dõi lỗi ghi sau triển khai.

Ví dụ các bước dưới đây **độc lập với lệnh `CREATE TABLE` ở mục 6**: giả sử có bảng cũ tên `legacy_booking`, cột `attendee_count` hiện cho phép `NULL` và chưa có giới hạn 1–12. Đây là lộ trình minh họa cho PostgreSQL, cần điều chỉnh theo dữ liệu thật:

```sql
-- 1. Quan sát trước khi thay đổi.
SELECT
    COUNT(*) FILTER (WHERE attendee_count IS NULL) AS missing_count,
    COUNT(*) FILTER (
        WHERE attendee_count IS NOT NULL
          AND attendee_count NOT BETWEEN 1 AND 12
    ) AS out_of_range_count
FROM legacy_booking;

-- 2. Chỉ thực hiện nếu nghiệp vụ xác nhận NULL cũ thật sự có nghĩa là 1.
UPDATE legacy_booking
SET attendee_count = 1
WHERE attendee_count IS NULL;

-- 3. Giá trị mặc định cho bản ghi mới không cung cấp cột.
ALTER TABLE legacy_booking
    ALTER COLUMN attendee_count SET DEFAULT 1;

-- 4. Chặn giá trị mới không hợp lệ; dữ liệu cũ sẽ được kiểm tra sau.
ALTER TABLE legacy_booking
    ADD CONSTRAINT ck_legacy_booking_attendees
    CHECK (attendee_count BETWEEN 1 AND 12) NOT VALID;

-- 5. Khi đã sửa mọi giá trị ngoài miền, xác minh dữ liệu tồn tại.
ALTER TABLE legacy_booking
    VALIDATE CONSTRAINT ck_legacy_booking_attendees;

-- 6. Khi không còn NULL và đã kiểm tra tác động vận hành:
ALTER TABLE legacy_booking
    ALTER COLUMN attendee_count SET NOT NULL;
```

Trong PostgreSQL, `CHECK ... NOT VALID` vẫn được kiểm tra đối với hàng mới chèn/cập nhật, nhưng chưa quét xác nhận toàn bộ hàng cũ; `VALIDATE CONSTRAINT` thực hiện bước xác nhận phần dữ liệu cũ. Tùy phiên bản và quy mô, các thao tác `ALTER TABLE` có thể giữ khóa và quét dữ liệu; cần thử trên bản sao có phân bố dữ liệu và tải tương đương. Nếu bản ghi cũ có `attendee_count = 0` hoặc `13`, phải sửa có căn cứ **trước** khi `VALIDATE` thành công.

Không mặc định mọi `NULL` cũ bằng `1`. Nếu không chứng minh được, có thể phải giữ `NULL`, tách trạng thái dữ liệu chưa hoàn chỉnh, hoặc xây công cụ đối soát và sửa dữ liệu. Một migration thành công về cú pháp nhưng bịa giá trị lịch sử vẫn là migration sai.

## 10. Những sai lầm thường gặp

| Thiết kế dễ mắc | Vì sao sai | Cách sửa |
|---|---|---|
| `quantity INTEGER CHECK (quantity > 0)` được xem là “bắt buộc” | `NULL` làm điều kiện thành `UNKNOWN`, nên có thể lọt | Thêm `NOT NULL` |
| `status NOT NULL DEFAULT 'CONFIRMED'` khi chưa có bước duyệt | Thiếu dữ liệu đầu vào lại thành đã duyệt | Đặt mặc định phù hợp vòng đời, thường `DRAFT` |
| `fee NOT NULL DEFAULT 0` khi phí chưa được tính | Dễ nhầm miễn phí với chưa xác định | Yêu cầu cung cấp phí hoặc mô hình trạng thái chưa chốt |
| `email NOT NULL` được xem là đủ hợp lệ | Vẫn nhận chuỗi rỗng và dữ liệu không đúng chuẩn | Bổ sung kiểm tra đúng cấp độ, chuẩn hóa và xác minh email theo nghiệp vụ |
| `CHECK (a < b)` trên hai cột tùy chọn | Một giá trị `NULL` có thể khiến điều kiện thành `UNKNOWN` | Quy định rõ tính tùy chọn; thêm `NOT NULL` hay điều kiện `IS NULL/IS NOT NULL` |
| Dùng `CHECK` để cấm hai lịch trùng phòng | Mỗi hàng không biết chắc sự tồn tại của hàng khác | Thiết kế ràng buộc liên hàng và chiến lược giao dịch phù hợp |
| Dùng điều kiện `created_at <= CURRENT_TIMESTAMP` làm bất biến vĩnh viễn | Thời gian trôi nhưng DBMS không tự kiểm tra lại hàng | Xác thực vào lúc phát sinh thao tác, lưu dấu vết quyết định |
| Thêm `NOT NULL` thẳng vào bảng cũ | Có thể gặp `NULL`, lỗi ghi hoặc khóa lâu | Khảo sát, sửa dữ liệu, thử migration, mới siết ràng buộc |

## 11. Checklist thiết kế và bài luyện tập

Trước khi bàn giao lược đồ vật lý, đối với **mỗi cột** hãy trả lời được:

- Giá trị này có được vắng mặt không? `NULL` biểu diễn “chưa biết”, “không áp dụng”, hay một lỗi?
- Nếu bên ghi không gửi cột, có tồn tại **một giá trị suy ra đúng trong mọi trường hợp** để dùng `DEFAULT` không?
- Miền giá trị và điều kiện liên cột nào phải luôn đúng? Đã xét `NULL` trong biểu thức `CHECK` chưa?
- Ràng buộc cần kiểm tra một hàng, nhiều hàng, hay dữ liệu ở bảng khác? Có cần `UNIQUE`, `FOREIGN KEY` hoặc giao dịch thay cho `CHECK` không?
- Phiên bản DBMS có thực thi chính xác cơ chế này không? Có khác biệt về kiểu số, timezone, biểu thức chuỗi, ép kiểu hoặc tính tương thích không?
- Dữ liệu cũ và các đường ghi khác ngoài UI có tuân thủ được quy tắc mới? Có kiểm thử lỗi có chủ đích và kế hoạch migration không?

**Bài luyện tập:** một ứng dụng đặt phòng có `room_id`, `start_at`, `end_at`, `seat_count`, `status` và `cancelled_at`. Yêu cầu: phòng và thời gian là bắt buộc; `seat_count` từ 1 đến sức chứa của phòng; mặc định trạng thái là `PENDING`; khi hủy phải có `cancelled_at`; một phòng không được có hai lượt đã xác nhận trùng thời gian.

1. Phân nhóm quy tắc nào xử lý được bằng `NOT NULL`, `DEFAULT`, `CHECK` trên cùng hàng; quy tắc nào cần `FOREIGN KEY` hoặc cơ chế liên hàng.
2. Viết `CHECK` cho `start_at < end_at` và điều kiện trạng thái/hủy, nêu rõ các cột nào phải `NOT NULL` để tránh `UNKNOWN`.
3. Giải thích vì sao “`seat_count` không vượt sức chứa phòng” không thể viết như một `CHECK` hàng đơn giản nếu sức chứa nằm ở bảng `room`; đề xuất cách giữ tính toàn vẹn phù hợp.
4. Liệt kê tối thiểu sáu trường hợp kiểm thử bao gồm một giá trị `NULL` được gửi rõ ràng, một giá trị mặc định, một giá trị ngoài miền, một mốc thời gian sai thứ tự và hai lượt đặt phòng bị trùng.

Một mô hình vật lý tốt không chỉ định nghĩa cột chứa được loại dữ liệu gì, mà còn diễn đạt được **khi nào giá trị bắt buộc, khi nào được suy ra và tổ hợp nào bị cấm**. Dùng `NOT NULL`, `DEFAULT` và `CHECK` đúng ngữ nghĩa giúp dữ liệu giữ được những bất biến quan trọng ngay cả khi ứng dụng và luồng tích hợp tiếp tục thay đổi.
