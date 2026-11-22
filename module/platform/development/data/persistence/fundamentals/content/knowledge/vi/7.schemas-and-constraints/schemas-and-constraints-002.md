# Kiểu cột, miền giá trị và trường bắt buộc

## 1. Từ yêu cầu nghiệp vụ đến lược đồ lưu trữ

Trong ứng dụng Java, một đơn hàng có thể được mô tả bằng đối tượng gồm mã đơn, mã khách hàng, trạng thái, số tiền, loại tiền tệ và thời điểm tạo. Đưa đối tượng này vào cơ sở dữ liệu không đơn thuần là tạo các cột có tên giống thuộc tính Java. Cần xác định **giá trị nào được phép tồn tại**, **giá trị nào bắt buộc phải có**, **giá trị nào có thể chưa biết**, và **hệ quản trị sẽ từ chối điều gì khi nhiều đường ghi cùng truy cập dữ liệu**.

Ba quyết định liên quan chặt chẽ:

1. **Kiểu cột (*column type*):** số nguyên, thập phân chính xác, chuỗi, ngày, thời điểm, boolean, byte... Kiểu cột quyết định cách DB biểu diễn, so sánh và xử lý giá trị.
2. **Miền giá trị (*domain of values*):** tập giá trị hợp lệ theo ý nghĩa nghiệp vụ; ví dụ số lượng phải dương, trạng thái thuộc một tập cho phép, tổng tiền không âm.
3. **Tính bắt buộc (*requiredness*):** giá trị có thể là `NULL` không? Nếu thiếu dữ liệu khi tạo, DB dùng mặc định hay phải trả lỗi? Việc chưa biết một giá trị có khác với giá trị rỗng hoặc `0` không?

Bài học thuộc chương **Lược đồ và ràng buộc** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Những quyết định này tạo nền tảng cho mô hình dữ liệu, truy vấn và chỉ mục, giao dịch, cô lập và đồng thời; chúng cũng ảnh hưởng trực tiếp đến ranh giới persistence của Java, xử lý lỗi kết nối, migration, bảo mật, sao lưu và hiệu năng.

### Tình huống xuyên suốt

Một dịch vụ bán khóa học ghi nhận đơn hàng có các quy tắc:

- Mỗi đơn hàng có `id` ổn định do DB tạo và một khách hàng hiện hữu.
- `status` chỉ được nhận `DRAFT`, `PAID` hoặc `CANCELLED`.
- `total` là số tiền thập phân **chính xác**, không âm; `currency` là mã tiền tệ được hệ thống hỗ trợ.
- Đơn ở trạng thái `PAID` phải có `paid_at`; đơn chưa thanh toán có thể chưa có thời điểm đó.
- Ghi chú của khách hàng được phép không có, nhưng không được mặc nhiên biến `NULL` thành chuỗi `"null"`.
- Khi khách hàng không nhập trạng thái lúc tạo đơn, giá trị mặc định là `DRAFT`. Trường bắt buộc như `customer_id` không được suy đoán.

Một thiết kế đúng cần biến các câu trên thành kiểu cột, ràng buộc DB và quy tắc Java có thể thử được.

## 2. Kiểu dữ liệu SQL là một phần của hợp đồng

Cùng là “số”, nhưng `INTEGER`, `BIGINT`, `NUMERIC` và kiểu dấu phẩy động có những đặc tính khác nhau. Cùng là “ngày giờ”, nhưng `DATE` và thời điểm tuyệt đối không thể thay cho nhau. Chọn kiểu theo **ý nghĩa và biên giá trị**, không theo thói quen đặt mọi cột là `VARCHAR`.

### 2.1. Nhóm kiểu thường gặp

| Nhu cầu | Kiểu PostgreSQL minh họa | Biểu diễn Java thường gặp | Lưu ý |
| --- | --- | --- | --- |
| Số đếm, số lượng | `INTEGER`, `BIGINT` | `int`, `long` | Có giới hạn phạm vi; phải chống âm/tràn bằng ràng buộc |
| Khóa định danh số | `BIGINT GENERATED ... AS IDENTITY` | `long` | Không dùng số thực để làm ID |
| Tiền và số thập phân chính xác | `NUMERIC(p,s)` | `BigDecimal` | Khai báo precision/scale; kiểm tra làm tròn |
| Phép đo cho phép sai số | `REAL`, `DOUBLE PRECISION` | `float`, `double` | Không phù hợp cho quyết định tiền chính xác |
| Chuỗi có độ dài tối đa | `VARCHAR(n)` | `String` | Cân nhắc Unicode, chuẩn hóa và collation |
| Văn bản dài | `TEXT` | `String` | Vẫn nên có giới hạn payload ở API nếu cần |
| Đúng/sai | `BOOLEAN` | `boolean` / `Boolean` | `NULL` có thể đại diện “chưa biết”, khác `FALSE` |
| Ngày lịch | `DATE` | `LocalDate` | Không tự chứa giờ/múi giờ |
| Thời điểm tuyệt đối | `TIMESTAMPTZ` | `OffsetDateTime` hoặc `Instant` qua mapping thích hợp | Quy định cách chuẩn hóa UTC và timezone |
| Giờ trong ngày | `TIME` | `LocalTime` | Không đủ để biểu diễn một thời điểm tuyệt đối |
| Định danh UUID | `UUID` | `UUID` | Xác định ai sinh ID và cách lưu |
| Dữ liệu có cấu trúc linh hoạt | `JSONB` | DTO/JSON qua serializer | Trường bên trong JSON không tự hưởng ràng buộc cột SQL |
| Dữ liệu nhị phân | `BYTEA` | `byte[]` / stream | Quy định giới hạn kích thước và quyền truy cập |

Bảng sử dụng PostgreSQL để minh họa; các hệ quản trị quan hệ khác có cú pháp, kiểu và quy tắc chuyển đổi riêng. Không sao chép nguyên DDL nếu chưa kiểm tra DB thực tế.

### 2.2. Chọn kiểu số: phạm vi và độ chính xác

Giả sử hệ thống lưu `quantity = 12`. Dùng `INTEGER` thường đủ nếu giới hạn tối đa của nghiệp vụ phù hợp. Dùng `BIGINT` khi có lý do cần phạm vi lớn hơn. Nhưng `BIGINT` không giải quyết quy tắc “số lượng không âm”; vẫn cần `CHECK (quantity >= 0)`.

Với tổng tiền, `NUMERIC(18,2)` trong PostgreSQL cho phép tối đa 18 chữ số có nghĩa, trong đó có 2 chữ số sau dấu thập phân. Điều này khác `DOUBLE PRECISION`: số thực nhị phân không biểu diễn chính xác mọi số thập phân như `0.1`.

```sql
CREATE TABLE numeric_examples (
    quantity    INTEGER NOT NULL CHECK (quantity >= 0),
    unit_price  NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0)
);
```

Trong PostgreSQL, giá trị nhập vào `NUMERIC(p,s)` có thể được **làm tròn tới scale** trước khi lưu. Nếu nghiệp vụ yêu cầu từ chối `12.345` thay vì lưu `12.35`, hãy kiểm tra scale ở Java hoặc áp dụng quy tắc riêng phù hợp trước khi gửi dữ liệu vào DB. Không mặc định DB sẽ từ chối mọi chữ số thập phân vượt scale.

Tiền tệ còn cần đơn vị: số `100` chưa đầy đủ nếu chưa biết đó là VND hay USD. Không tự áp scale hai chữ số cho mọi đồng tiền; số chữ số đơn vị nhỏ nhất tùy mã tiền và chính sách nghiệp vụ.

### 2.3. Chuỗi ký tự, Unicode và đối chiếu

`VARCHAR(200)` giới hạn độ dài theo ký tự theo quy tắc PostgreSQL, không đồng nghĩa với “200 byte UTF-8”. Một ký tự tiếng Việt có thể chiếm nhiều byte khi lưu/truyền. Java `String.length()` đếm đơn vị mã UTF-16, không phải byte UTF-8 hay nhất thiết là số ký tự người dùng nhìn thấy.

Ngoài độ dài, cần biết:

- **Chuẩn hóa đầu vào:** bỏ khoảng trắng đầu/cuối có nên được phép? Có chấp nhận chuỗi chỉ gồm khoảng trắng?
- **Collation và so sánh:** hai chuỗi khác hoa/thường hay dấu có được coi là bằng nhau không? Quy tắc phụ thuộc DB/collation và yêu cầu nghiệp vụ.
- **Mã định danh:** có cần phân biệt `"abc"` với `"ABC"`? Không tùy tiện dùng `lower(...)` cho mọi loại mã.
- **Nội dung dài:** `TEXT` linh hoạt nhưng không có nghĩa ứng dụng nên nhận payload không giới hạn.

`CHAR(n)` có quy tắc đệm khoảng trắng ở một số hệ quản trị, nên không mặc định nó tốt hơn `VARCHAR(n)` chỉ vì một trường luôn có 3 ký tự. Với mã tiền tệ có độ dài cố định, `VARCHAR(3)` kèm `CHECK` rõ nghĩa cũng là một lựa chọn.

### 2.4. Ngày lịch và thời điểm

Một khóa học bắt đầu vào **ngày** 25 tháng 11 nên có thể dùng `DATE`. Một thanh toán diễn ra ở **thời điểm** cụ thể cần kiểu thời gian thể hiện thời điểm tuyệt đối, chẳng hạn `TIMESTAMPTZ` với PostgreSQL.

`TIMESTAMPTZ` lưu thời điểm theo cơ chế của PostgreSQL; tên múi giờ gốc mà người dùng chọn không được tự động giữ lại. Nếu nghiệp vụ cần biết người dùng đã chọn `Asia/Ho_Chi_Minh`, hãy lưu timezone ID riêng. Khi tích hợp Java, quy định rõ thời điểm nào là UTC và tránh tự giả định thời gian máy chủ.

### 2.5. Boolean và trạng thái ba giá trị

`BOOLEAN NOT NULL DEFAULT FALSE` có hai trạng thái nghiệp vụ `TRUE`/`FALSE`. Nhưng `BOOLEAN` cho phép `NULL` có thể biểu diễn “chưa trả lời” — khác với “đã trả lời không”. Ví dụ:

- `marketing_consent = TRUE`: đã đồng ý.
- `marketing_consent = FALSE`: đã từ chối.
- `marketing_consent IS NULL`: chưa có quyết định hoặc chưa thu thập.

Chỉ dùng ba trạng thái khi nghiệp vụ thật sự phân biệt chúng; nếu không, `NOT NULL` thường làm logic và truy vấn đơn giản hơn.

## 3. Miền giá trị: kiểu đúng vẫn có thể sai nghiệp vụ

Một số nguyên `-50` hợp lệ với kiểu `INTEGER` nhưng có thể vô nghĩa với số lượng hàng hóa. Một chuỗi `"UNKNOWN_AND_NOT_SUPPORTED"` hợp lệ với `VARCHAR(30)` nhưng không hợp lệ với trạng thái đơn hàng được định nghĩa. Vì vậy **kiểu cột** là lớp đầu tiên; **miền giá trị** bổ sung điều kiện nghiệp vụ.

Các ràng buộc phổ biến:

| Ràng buộc | Bảo vệ điều gì? | Ví dụ |
| --- | --- | --- |
| `NOT NULL` | Trường không được mang giá trị SQL `NULL` | `customer_id BIGINT NOT NULL` |
| `CHECK` | Điều kiện hợp lệ trên một hàng | `total >= 0` |
| `DEFAULT` | Giá trị dùng khi bỏ qua cột hoặc dùng `DEFAULT` trong câu ghi | `status DEFAULT 'DRAFT'` |
| `PRIMARY KEY` | Nhận diện hàng, không null và duy nhất | `id BIGINT PRIMARY KEY` |
| `UNIQUE` | Không có hai hàng mang cùng khóa logic theo quy tắc DB | `UNIQUE (order_number)` |
| `FOREIGN KEY` | Tham chiếu tới bản ghi cha hợp lệ | `customer_id REFERENCES customers(id)` |
| `CREATE DOMAIN` (PostgreSQL) | Tái sử dụng một kiểu nền và các ràng buộc chung | Domain cho mã hoặc số lượng |

Các loại này bổ sung nhau. `NOT NULL` không giới hạn số âm. `CHECK (total >= 0)` không nhất thiết chặn `NULL`. `DEFAULT` không làm cột trở thành bắt buộc. Cả ba có thể cần xuất hiện trên cùng một cột.

### 3.1. Biểu diễn miền bằng CHECK

```sql
CREATE TABLE course_seats (
    id           BIGINT PRIMARY KEY,
    capacity     INTEGER NOT NULL CHECK (capacity BETWEEN 0 AND 10000),
    seats_taken  INTEGER NOT NULL CHECK (seats_taken >= 0),
    CONSTRAINT ck_seats_not_exceed_capacity
        CHECK (seats_taken <= capacity)
);
```

Ở đây, `capacity` và `seats_taken` cùng nằm trên một hàng, nên `CHECK` có thể bảo vệ quan hệ giữa chúng. Nếu số lượng đăng ký nằm trên nhiều hàng ở bảng khác, một `CHECK` thông thường không thể thay thế giao dịch và cơ chế chống tranh chấp để bảo đảm tổng đăng ký không vượt giới hạn.

`CHECK` phù hợp với bất biến của hàng hiện tại. Đừng cố đưa một truy vấn sang bảng khác hoặc một hàm phụ thuộc trạng thái bên ngoài vào `CHECK` rồi tin rằng DB sẽ tự kiểm tra lại mỗi khi dữ liệu bên ngoài đổi.

### 3.2. Enum, bảng tham chiếu và mã trạng thái

Có ba cách thường gặp để ràng buộc mã trạng thái:

1. `VARCHAR` kết hợp `CHECK (status IN (...))`, rõ ràng khi tập giá trị nhỏ và ít đổi.
2. Kiểu `ENUM` riêng của DB, có lợi thế về typing nhưng cần kế hoạch migration khi thêm/đổi giá trị.
3. Bảng tham chiếu `order_status_codes` và `FOREIGN KEY`, phù hợp khi mã đi kèm metadata, trạng thái kích hoạt hoặc được quản lý riêng.

Không có lựa chọn duy nhất cho mọi hệ thống. Nếu trạng thái nghiệp vụ cần lịch sử chuyển đổi phức tạp, chỉ kiểm tra giá trị nằm trong danh sách chưa đủ. Ví dụ `DRAFT → PAID` có thể hợp lệ, nhưng `CANCELLED → PAID` có thể bị cấm; đó là quy tắc về **chuyển trạng thái** cần được bảo vệ ở đường cập nhật với kiểm soát đồng thời.

### 3.3. Domain trong PostgreSQL

Có thể tái sử dụng một quy tắc được đặt tên với `CREATE DOMAIN`:

```sql
CREATE DOMAIN nonnegative_amount AS NUMERIC(18, 2)
    CHECK (VALUE >= 0);

CREATE TABLE sample_fees (
    id     BIGINT PRIMARY KEY,
    amount nonnegative_amount NOT NULL
);
```

`VALUE` là giá trị đang được kiểm tra theo domain. Ràng buộc `CHECK` của domain không tự loại `NULL`: ví dụ dùng thêm `NOT NULL` ở cột để biểu đạt tính bắt buộc. Domain giúp tái sử dụng một ý nghĩa chung, nhưng không nên dùng cho những quy tắc đặc thù theo bảng hoặc phụ thuộc các cột khác; cũng cần cân nhắc tính di động giữa các DB và quy trình thay đổi domain có thể ảnh hưởng nhiều bảng.

## 4. NULL, NOT NULL và sự khác nhau giữa “thiếu”, “rỗng” và “mặc định”

Trong SQL, `NULL` biểu thị **không có giá trị được xác định tại cột đó**. Nó không phải số `0`, chuỗi rỗng `''` hay trạng thái `"UNKNOWN"` do ứng dụng tự đặt.

| Giá trị | Ý nghĩa có thể có | Truy vấn kiểm tra |
| --- | --- | --- |
| `NULL` | Chưa biết, không áp dụng hoặc chưa cung cấp — cần hợp đồng cụ thể | `IS NULL` |
| `''` | Chuỗi có độ dài bằng 0 | `= ''` |
| `'   '` | Chuỗi chỉ có khoảng trắng | `btrim(col) = ''` trong PostgreSQL |
| `0` | Một số thực sự bằng 0 | `= 0` |
| `FALSE` | Một quyết định phủ định rõ ràng | `= FALSE` |
| `'UNKNOWN'` | Một mã trạng thái có nghĩa do ứng dụng định nghĩa | `= 'UNKNOWN'` |

Không sử dụng `0` làm “không có ID”, hoặc `1970-01-01` làm “chưa thanh toán” trừ khi có hợp đồng dữ liệu rất rõ; các giá trị giả như thế thường làm báo cáo, truy vấn và migration khó tin cậy.

### 4.1. Logic ba giá trị của SQL

Biểu thức so sánh với `NULL` thường cho `UNKNOWN` (không phải `TRUE` hoặc `FALSE`):

```sql
SELECT NULL = NULL;       -- UNKNOWN, kết quả hiển thị NULL
SELECT 10 > NULL;         -- UNKNOWN
SELECT NULL IS NULL;      -- TRUE
SELECT NULL IS NOT NULL;  -- FALSE
```

Trong mệnh đề `WHERE`, chỉ những hàng có điều kiện `TRUE` mới được chọn. Trong PostgreSQL, một ràng buộc `CHECK` được coi là thỏa khi biểu thức là `TRUE` **hoặc `UNKNOWN`**; nó chỉ từ chối khi biểu thức trả `FALSE`.

Ví dụ nguy hiểm:

```sql
CREATE TABLE broken_orders (
    total NUMERIC(18, 2) CHECK (total >= 0)
);
```

Câu lệnh sau **có thể thành công**:

```sql
INSERT INTO broken_orders (total) VALUES (NULL);
```

Lý do là `total >= 0` thành `UNKNOWN`. Nếu nghiệp vụ yêu cầu có số tiền, khai báo rõ:

```sql
total NUMERIC(18, 2) NOT NULL CHECK (total >= 0)
```

**Quy tắc học quan trọng:** `CHECK` bảo vệ miền giá trị khi đã có giá trị; `NOT NULL` bảo vệ tính bắt buộc. Đừng dùng một vế `CHECK` đơn giản để thay thế `NOT NULL` mà không phân tích ba giá trị.

### 4.2. DEFAULT không đồng nghĩa NOT NULL

```sql
status VARCHAR(16) NOT NULL DEFAULT 'DRAFT'
```

- Khi câu `INSERT` **bỏ qua** cột `status`, DB dùng `'DRAFT'`.
- Khi câu `INSERT` dùng cú pháp `DEFAULT` cho cột, DB dùng mặc định.
- Khi client gửi **tường minh `NULL`**, `NOT NULL` sẽ từ chối; `DEFAULT` không tự thay `NULL` thành `'DRAFT'`.

```sql
-- Với bảng orders bên dưới:
INSERT INTO orders (customer_id, currency, total)
VALUES (1, 'VND', 120000.00);
-- status mặc định = DRAFT

INSERT INTO orders (customer_id, currency, total, status)
VALUES (1, 'VND', 120000.00, NULL);
-- Lỗi NOT NULL; không tự chuyển thành DRAFT
```

Nếu một giá trị chỉ nên được cung cấp bởi DB, có thể để DB sinh khóa/timestamp; API không nên cho client tự sửa các trường đó. Đừng đặt mặc định giả cho một trường thực sự bắt buộc như `customer_id` chỉ để câu `INSERT` dễ chạy.

### 4.3. Bắt buộc theo điều kiện

`paid_at` có thể `NULL` khi đơn chưa thanh toán, nhưng không được `NULL` khi `status = 'PAID'`. Đây là yêu cầu **bắt buộc theo trạng thái**, có thể diễn đạt bằng `CHECK` trên cùng hàng:

```sql
CHECK (status <> 'PAID' OR paid_at IS NOT NULL)
```

Vì `status` phải `NOT NULL`, điều kiện này sẽ từ chối hàng `PAID` thiếu `paid_at`. Nếu muốn bảo đảm mọi trạng thái khác `PAID` không có `paid_at`, có thể dùng điều kiện hai chiều, nhưng chỉ làm vậy khi nghiệp vụ thực sự cấm giữ thời gian thanh toán trong trạng thái hoàn tiền/hủy.

### 4.4. Trường tùy chọn cần có ngữ nghĩa

Một trường `note TEXT` không có `NOT NULL` cho phép null. Nhưng quy tắc trả dữ liệu từ API cần làm rõ:

- Trong request tạo: trường vắng mặt và trường bằng `null` có được coi giống nhau không?
- Trong request PATCH: trường vắng mặt có nghĩa “giữ nguyên”, còn `null` có nghĩa “xóa ghi chú”?
- Khi đọc: trả `note: null` hay bỏ thuộc tính khỏi JSON?
- Khi thống kê: có cần phân biệt người dùng để trống với người dùng chưa từng nhập?

Đây là hợp đồng giữa API, mô hình Java và DB. Không để thư viện serialize quyết định thay nghiệp vụ.

## 5. Một lược đồ mẫu có đủ kiểu, miền và trường bắt buộc

Dưới đây là DDL minh họa cho **PostgreSQL**. Một người dùng có thể có nhiều đơn hàng; `orders` tham chiếu `customers` bằng khóa ngoại. Câu lệnh được viết để có thể chạy từ trên xuống trong DB thử nghiệm.

```sql
CREATE TABLE customers (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email        VARCHAR(320) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    phone        VARCHAR(32),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_customer_email_not_blank
        CHECK (length(btrim(email)) > 0),
    CONSTRAINT ck_customer_name_not_blank
        CHECK (length(btrim(display_name)) > 0)
);

CREATE TABLE orders (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    currency    VARCHAR(3) NOT NULL,
    total       NUMERIC(18, 2) NOT NULL,
    status      VARCHAR(16) NOT NULL DEFAULT 'DRAFT',
    note        TEXT,
    paid_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version     BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT ck_order_currency
        CHECK (currency IN ('VND', 'USD')),
    CONSTRAINT ck_order_total
        CHECK (total >= 0),
    CONSTRAINT ck_order_status
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELLED')),
    CONSTRAINT ck_order_paid_at
        CHECK (status <> 'PAID' OR paid_at IS NOT NULL),
    CONSTRAINT ck_order_version
        CHECK (version >= 0)
);

CREATE INDEX idx_orders_customer_created
    ON orders (customer_id, created_at DESC, id DESC);
```

Ở đây:

- `id` là khóa chính do DB sinh; nó định danh hàng và không được thay đổi như tiêu đề/ghi chú.
- `customer_id` vừa `NOT NULL` vừa có `FOREIGN KEY`. Đây là hai điều kiện khác nhau: **bắt buộc có ID** và **ID phải tham chiếu khách hàng hiện hữu**.
- `currency` bị giới hạn trong tập tiền tệ mà ví dụ hỗ trợ. Một ứng dụng thực tế phải định nghĩa cách hỗ trợ mã mới và quy tắc số lẻ tương ứng.
- `total` là decimal chính xác, không âm và không được `NULL`.
- `status` có mặc định `DRAFT` nhưng vẫn phải thuộc tập mã hợp lệ.
- `paid_at` là trường tùy chọn, có quy tắc phụ thuộc trạng thái.
- `note` cho phép `NULL`, không tự gán chuỗi rỗng.
- `version` sẵn sàng cho optimistic locking khi hai yêu cầu cập nhật đồng thời.
- `created_at`/`updated_at` được khởi tạo lúc insert. **DEFAULT không tự làm mới `updated_at` khi UPDATE**; logic ghi cần cập nhật nó hoặc sử dụng trigger được thiết kế rõ ràng.

Bảng `customers` chưa đặt ràng buộc unique trên email vì quy tắc so sánh địa chỉ email có thể cần làm rõ. Hệ thống phải quyết định việc email trùng hoa/thường, chuẩn hóa và nhiều tài khoản dùng cùng email trước khi thêm unique thích hợp. Nếu chính sách yêu cầu email duy nhất theo chuỗi lưu trữ nguyên văn, có thể dùng `UNIQUE (email)`; nếu yêu cầu không phân biệt hoa/thường, cần thiết kế normalized key/collation/index phù hợp.

### 5.1. Kiểm thử trực tiếp bằng SQL

```sql
-- Tạo khách hàng, giả sử DB trả id = 1.
INSERT INTO customers (email, display_name)
VALUES ('student@example.com', 'Người học Java')
RETURNING id;

-- Hợp lệ: bỏ qua status và note, DB dùng DRAFT và NULL.
INSERT INTO orders (customer_id, currency, total)
VALUES (1, 'VND', 120000.00)
RETURNING id, status, note, version;

-- Không hợp lệ: tổng tiền âm.
INSERT INTO orders (customer_id, currency, total)
VALUES (1, 'VND', -5.00);

-- Không hợp lệ: tiền tệ ngoài tập hỗ trợ.
INSERT INTO orders (customer_id, currency, total)
VALUES (1, 'XYZ', 100.00);

-- Không hợp lệ: PAID nhưng không có thời gian thanh toán.
INSERT INTO orders (customer_id, currency, total, status)
VALUES (1, 'VND', 100.00, 'PAID');

-- Không hợp lệ: customer_id = NULL.
INSERT INTO orders (customer_id, currency, total)
VALUES (NULL, 'VND', 100.00);

-- Không hợp lệ: customer_id không có trong customers.
INSERT INTO orders (customer_id, currency, total)
VALUES (999999, 'VND', 100.00);
```

Các câu lệnh lỗi được trình bày để **chạy riêng từng trường hợp**. Nếu công cụ chạy tất cả trong một transaction và một câu vi phạm ràng buộc, PostgreSQL có thể đặt transaction vào trạng thái lỗi cho tới khi `ROLLBACK` hoặc xử lý bằng savepoint. Không chạy một chuỗi có lỗi rồi tự kết luận các câu sau sai do schema.

### 5.2. Quan sát NULL và mặc định

```sql
SELECT
    id,
    status,
    note,
    note IS NULL AS note_was_absent,
    paid_at,
    total
FROM orders
ORDER BY id;
```

Đơn hàng tạo mà bỏ qua `note` sẽ có `note IS NULL = TRUE`. Giá trị `status` mặc định `DRAFT` là một trạng thái nghiệp vụ thật, khác với “không biết trạng thái”.

### 5.3. CHECK bảo vệ cùng hàng nhưng chưa đủ cho toàn hệ thống

Một đơn có nhiều dòng chi tiết:

```sql
CREATE TABLE order_items (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id   BIGINT NOT NULL REFERENCES orders(id),
    product_id BIGINT NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT uq_order_item_product UNIQUE (order_id, product_id)
);
```

Những ràng buộc trên bảo vệ từng dòng hàng, ID liên quan và việc trùng sản phẩm trong cùng đơn. Nhưng `orders.total` có bằng `SUM(quantity * unit_price)` của các dòng không? **Không có ràng buộc CHECK đơn giản trên hàng `orders` nào tự bảo vệ phép tổng đa hàng đó**. Cần thiết kế quy trình ghi trong transaction, cách khóa/chống tranh chấp hoặc tính lại tổng từ nguồn có thẩm quyền. Nếu cho phép nhiều dịch vụ sửa chi tiết đơn độc lập, bất biến tổng tiền càng phải được quy định rõ.

## 6. UNIQUE, PRIMARY KEY và FOREIGN KEY: ranh giới của miền dữ liệu

### 6.1. PRIMARY KEY và danh tính

`PRIMARY KEY` kết hợp tính duy nhất và không cho phép `NULL`. Một bảng có thể dùng khóa tự nhiên hoặc khóa thay thế; lựa chọn cần tính đến việc giá trị có thể đổi hay không. Email hay tên sản phẩm thường dễ thay đổi, vì vậy một `id` ổn định giúp tránh phải đổi khóa ngoại trên nhiều bảng khi người dùng sửa dữ liệu.

### 6.2. UNIQUE và trường tùy chọn

`UNIQUE` có thể áp dụng cho một hoặc nhiều cột:

```sql
ALTER TABLE customers
ADD CONSTRAINT uq_customer_email UNIQUE (email);
```

Trong PostgreSQL, unique mặc định cho phép nhiều giá trị `NULL` vì các null được xem là phân biệt trong kiểm tra unique. Điều đó **không ảnh hưởng ví dụ email** vì `email` đã `NOT NULL`, nhưng có ý nghĩa với trường như `phone` nếu sau này thêm unique. Nếu nghiệp vụ yêu cầu “chỉ được có tối đa một hàng có null” thì cần cấu trúc/ràng buộc phù hợp (PostgreSQL có hỗ trợ `NULLS NOT DISTINCT` ở các phiên bản tương ứng).

Chú ý **collation và chuẩn hóa**: `'Alice@Example.com'` và `'alice@example.com'` có được coi trùng không? Câu trả lời phụ thuộc chính sách, dữ liệu được chuẩn hóa và cách DB so sánh. Không giải quyết bằng một câu regex đơn giản; kiểm tra độ hợp lệ địa chỉ email và quy tắc duy nhất là hai vấn đề riêng.

### 6.3. FOREIGN KEY và trường bắt buộc

Một `FOREIGN KEY` chỉ bảo đảm giá trị tham chiếu hợp lệ **khi có giá trị cần kiểm tra**; với FK một cột cho phép `NULL`, hàng có null có thể không tham chiếu ai cả. Nếu mỗi đơn bắt buộc thuộc một khách hàng, phải ghi `customer_id BIGINT NOT NULL REFERENCES customers(id)`.

Khi xóa khách hàng, DB có thể chặn xóa vì còn đơn hàng, hoặc thực hiện hành vi `ON DELETE` đã khai báo. Không tự đặt `ON DELETE CASCADE` cho dữ liệu giao dịch cần giữ lịch sử; cần quyết định theo quyền sở hữu, nghĩa vụ lưu trữ và quy tắc xóa dữ liệu. Nếu có quy tắc xóa mềm, FK thông thường không tự coi một hàng có `deleted_at` là không tồn tại.

### 6.4. Ràng buộc mạnh trong DB và validation ở Java cùng tồn tại

- Java kiểm tra sớm để trả thông báo dễ hiểu và giảm số request lỗi tới DB.
- DB là lớp bảo vệ cho mọi đường ghi, kể cả batch, job nền, script và yêu cầu đồng thời.
- Không tin rằng validation ở controller đã bảo vệ được một biến toàn cục hoặc quan hệ đa hàng trước race condition.
- Khi DB từ chối dữ liệu, service cần ánh xạ lỗi thành thông điệp nghiệp vụ; không hiển thị stack trace, SQL và tham số nhạy cảm cho người dùng.

## 7. Biểu diễn trường bắt buộc trong Java và JDBC

Một schema tốt chỉ thực sự phát huy tác dụng khi ranh giới Java ánh xạ kiểu và null nhất quán. Các tình huống thường gặp:

| PostgreSQL | Java | Lỗi dễ gặp |
| --- | --- | --- |
| `BIGINT NOT NULL` | `long` / `Long` | Dùng `long` mặc định `0` để che việc request thiếu ID |
| `NUMERIC(18,2)` | `BigDecimal` | Dùng `double` rồi sinh sai số |
| `VARCHAR NOT NULL` | `String` được validate | Java `String` vẫn có thể `null`; type Java không tự ngăn |
| `BOOLEAN NOT NULL` | `boolean` | Không phân biệt “không gửi” với `false` ở request DTO |
| `BOOLEAN` có thể null | `Boolean` | `boolean` không diễn đạt được “chưa biết” |
| `DATE` | `LocalDate` | Nhầm ngày lịch với timestamp |
| `TIMESTAMPTZ` | `OffsetDateTime` hoặc mapper sang `Instant` | Giả định timezone mặc định của JVM |
| `TEXT` nullable | `String` có thể null | Viết chuỗi `"null"` vào DB hoặc tự chuyển null thành rỗng |

### 7.1. DTO đầu vào khác với thực thể đã hợp lệ

Một request từ mạng là dữ liệu **chưa đáng tin cậy**. Nếu JSON không có trường `customerId` và framework ánh xạ nó thành `long` nguyên thủy mặc định `0`, ứng dụng có thể trả lỗi “không thấy khách hàng 0” thay vì “thiếu customerId”. Dùng `Long` trong DTO đầu vào để phân biệt giá trị vắng mặt, kiểm tra `null` rồi mới chuyển sang `long` khi đã hợp lệ.

Đối với số tiền, dùng `BigDecimal` và kiểm tra âm, scale và phạm vi. Đừng chuyển một JSON number qua `double` nếu yêu cầu chính xác từng đơn vị tiền tệ.

### 7.2. JDBC minh họa: ghi dữ liệu có kiểu

Ví dụ dùng Java 17, PostgreSQL và bảng `orders` ở trên. `RETURNING id` là cú pháp PostgreSQL.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Set;
import javax.sql.DataSource;

record NewOrder(
        Long customerId,
        String currency,
        BigDecimal total,
        String note
) {}

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long create(NewOrder input) throws SQLException {
        if (input.customerId() == null || input.customerId() <= 0) {
            throw new IllegalArgumentException("Thiếu customerId hợp lệ");
        }
        if (input.currency() == null
                || !Set.of("VND", "USD").contains(input.currency())) {
            throw new IllegalArgumentException("currency không được hỗ trợ");
        }
        if (input.total() == null || input.total().signum() < 0) {
            throw new IllegalArgumentException("total phải không âm");
        }

        BigDecimal total;
        try {
            total = input.total().setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "total có quá nhiều chữ số thập phân", ex);
        }
        if (total.precision() > 18) {
            throw new IllegalArgumentException("total vượt NUMERIC(18,2)");
        }

        String sql = """
            INSERT INTO orders (customer_id, currency, total, note)
            VALUES (?, ?, ?, ?)
            RETURNING id
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, input.customerId());
            statement.setString(2, input.currency());
            statement.setBigDecimal(3, total);

            if (input.note() == null) {
                statement.setNull(4, Types.VARCHAR);
            } else {
                statement.setString(4, input.note());
            }

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    throw new SQLException("DB không trả order ID");
                }
                return rows.getLong(1);
            }
        }
    }
}
```

Cần hiểu rõ các lựa chọn:

1. DTO dùng `Long customerId` để nhận diện trường thiếu; repository dùng `long` đã qua kiểm tra.
2. `setBigDecimal` giữ ý nghĩa decimal. `setScale(2, UNNECESSARY)` từ chối trường hợp cần làm tròn, đồng thời cho phép mở rộng những biểu diễn tương đương chính xác như `10` thành `10.00`.
3. `setNull` dùng SQL type để gửi null, khác với `setString(4, "null")`.
4. Câu lệnh bỏ qua `status`, `created_at`, `updated_at` và `version` để DB áp dụng giá trị mặc định; ứng dụng không phải truyền `NULL` cho các cột này.
5. `try-with-resources` đóng statement, result set và trả connection về pool.
6. Kiểm tra ở Java giúp lỗi sớm; DB vẫn giữ `NOT NULL`, `CHECK` và FK làm lớp bảo vệ độc lập. Nếu khách hàng bị xóa hoặc đổi trạng thái sau khi client kiểm tra, DB có thể từ chối FK/logic khác khi ghi.

Ví dụ chỉ minh họa thao tác tạo một hàng. Khi thao tác gồm đơn hàng, nhiều `order_items` và outbox, service phải đặt những lệnh ghi có liên quan trong **cùng transaction**; nhiều phương thức repository mỗi phương thức tự mở kết nối auto-commit riêng không tạo thành một transaction.

### 7.3. Đọc SQL NULL đúng cách

Với `ResultSet.getLong("customer_id")`, nếu cột SQL là null thì primitive trả `0` và phải kiểm tra `wasNull()` để phân biệt; tốt hơn là schema bắt buộc làm `customer_id` không thể null. Với cột nullable, dùng cách lấy giá trị phù hợp và kiểm tra null rõ ràng; `getObject` với loại hỗ trợ có thể hữu ích.

Ví dụ:

```java
String note = rows.getString("note");
if (note == null) {
    // Không có ghi chú; không đánh đồng với chuỗi rỗng.
}
```

Không tự thay mọi giá trị thiếu bằng `0` hoặc `""` trong mapper nếu nghiệp vụ cần phân biệt sự vắng mặt.

## 8. Tương tác giữa ràng buộc, giao dịch và đồng thời

### 8.1. Vi phạm constraint khi ghi

Ràng buộc DB được đánh giá theo quy tắc của hệ quản trị trong lúc ghi. Với PostgreSQL, một câu `INSERT` vi phạm `NOT NULL`, `CHECK` hoặc FK sẽ trả lỗi. Nếu đang ở trong transaction, ứng dụng phải xử lý bằng rollback hoặc savepoint phù hợp; không tiếp tục coi giao dịch đã thành công.

Một `SQLException` có thể chứa SQLState và thông tin chi tiết từ driver. Ở PostgreSQL, các mã phổ biến:

| SQLSTATE | Loại lỗi | Cách xử lý ở service |
| --- | --- | --- |
| `23502` | not_null_violation | Trả lỗi trường bắt buộc hoặc lỗi dữ liệu server |
| `23503` | foreign_key_violation | Tham chiếu không hợp lệ hoặc thao tác xóa bị chặn |
| `23505` | unique_violation | Trùng khóa hoặc xung đột yêu cầu |
| `23514` | check_violation | Giá trị nằm ngoài miền đã quy định |
| `22003` | numeric_value_out_of_range | Giá trị số ngoài phạm vi |
| `40001` | serialization_failure | Có thể thử lại toàn transaction nếu an toàn |
| `40P01` | deadlock_detected | Rollback và cân nhắc retry có giới hạn |

Ánh xạ lỗi theo **constraint name** thường giúp báo thông điệp rõ hơn; tuy nhiên không nên dựa vào văn bản lỗi của DB như một API ổn định. Không gửi trực tiếp câu SQL, khóa bí mật hoặc dữ liệu nhạy cảm từ driver cho client.

### 8.2. Constraint bảo vệ miền nhưng không giải quyết toàn bộ race condition

Ví dụ số chỗ còn lại:

```sql
CREATE TABLE workshops (
    id              BIGINT PRIMARY KEY,
    seats_remaining INTEGER NOT NULL CHECK (seats_remaining >= 0)
);
```

Hai request cùng nhìn thấy một chỗ. Nếu Java đọc `1` rồi cả hai cùng đặt giá trị `0` bằng một lệnh `UPDATE` không điều kiện, constraint vẫn thấy số không âm, nhưng hệ thống có thể xác nhận **hai** đăng ký cho một suất. Vì vậy cần kiểm tra và cập nhật một cách nguyên tử:

```sql
UPDATE workshops
SET seats_remaining = seats_remaining - 1
WHERE id = :workshop_id
  AND seats_remaining > 0;
```

Service tiếp tục tạo đăng ký **chỉ nếu cập nhật đúng một hàng**, và phải chạy cùng transaction với `INSERT` đăng ký. Ràng buộc `CHECK` ngăn số âm như lớp bảo vệ cuối, còn cập nhật điều kiện và transaction giải quyết bất biến khi có tranh chấp.

Đối với bất biến nhiều hàng hoặc nhiều bảng, cần xem xét cô lập giao dịch, khóa và nguy cơ `write skew`; một `CHECK` trên từng hàng không thể chứng minh quy tắc tổng hợp luôn đúng.

### 8.3. CHECK và khóa đồng thời

`CHECK (version >= 0)` ngăn phiên bản âm, nhưng không phát hiện được một người dùng đang ghi đè chỉnh sửa của người khác. Với optimistic locking, thêm điều kiện phiên bản ngay trong câu `UPDATE`:

```sql
UPDATE orders
SET note = :note,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :order_id
  AND version = :expected_version;
```

Nếu cập nhật 0 hàng, có thể đơn không tồn tại hoặc phiên bản đã thay đổi. Service phải phân loại theo quyền, trạng thái và hợp đồng API. Đừng tự coi 0 hàng là thành công khi người dùng yêu cầu cập nhật một bản ghi cụ thể.

## 9. Trường bắt buộc thay đổi theo vòng đời nghiệp vụ

Một đơn mới có thể chưa có `paid_at`, nhưng khi chuyển sang `PAID` nó bắt buộc có. Yêu cầu như vậy nên được diễn tả theo **trạng thái của bản ghi**, không dùng một mặc định giả kiểu thời gian `1970-01-01`.

Ví dụ chuyển trạng thái có kiểm soát:

```sql
UPDATE orders
SET status = 'PAID',
    paid_at = CURRENT_TIMESTAMP,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version;
```

Lệnh này chỉ chuyển `DRAFT → PAID` khi phiên bản còn đúng và cập nhật thời gian thanh toán cùng lúc. `CHECK (status <> 'PAID' OR paid_at IS NOT NULL)` ở DB chặn một đường ghi khác cố chuyển sang `PAID` mà thiếu thời điểm.

Tuy nhiên, chỉ có `CHECK` chưa cấm được mọi chuyển trạng thái sai, vì nó chỉ quan sát hàng **sau** thay đổi. Quy tắc “không chuyển CANCELLED về PAID” nên được bảo vệ trong đường cập nhật có điều kiện, transaction hoặc cơ chế phù hợp với kiến trúc.

Nếu một trường chỉ bắt buộc trong một vài trạng thái, không nên khai báo `NOT NULL` vô điều kiện rồi nhét giá trị giả. Hãy thiết kế trạng thái, kiểm tra điều kiện và thời điểm cập nhật một cách tường minh.

## 10. Tiến hóa lược đồ khi cần thêm trường bắt buộc

Trong DB đã có nhiều hàng, yêu cầu mới “mỗi đơn phải có `sales_channel`” không thể được triển khai an toàn bằng cách thêm cột `NOT NULL` rồi giả định mọi dữ liệu cũ đã có giá trị. Cần lên kế hoạch tương thích giữa phiên bản ứng dụng, schema và dữ liệu đang lưu.

### 10.1. Mẫu mở rộng → điền dữ liệu → siết ràng buộc

Ví dụ sử dụng PostgreSQL:

```sql
-- Giai đoạn 1: thêm cột nullable để ứng dụng cũ chưa bị lỗi.
ALTER TABLE orders
ADD COLUMN sales_channel VARCHAR(20);

-- Giai đoạn 2: triển khai ứng dụng mới bắt đầu ghi sales_channel.
-- Giai đoạn 3: backfill dữ liệu cũ bằng giá trị có cơ sở nghiệp vụ.
-- Ví dụ minh họa, chỉ khi thực sự biết các đơn cũ đến từ web:
UPDATE orders
SET sales_channel = 'WEB'
WHERE sales_channel IS NULL;

-- Giai đoạn 4: chặn giá trị ngoài miền hợp lệ.
ALTER TABLE orders
ADD CONSTRAINT ck_order_sales_channel
CHECK (sales_channel IN ('WEB', 'MOBILE', 'PARTNER')) NOT VALID;

-- PostgreSQL: kiểm tra các hàng cũ và đánh dấu constraint đã validate.
ALTER TABLE orders
VALIDATE CONSTRAINT ck_order_sales_channel;

-- Giai đoạn 5: sau khi mọi hàng đã có giá trị và writer mới tuân thủ,
-- có thể siết tính bắt buộc.
ALTER TABLE orders
ALTER COLUMN sales_channel SET NOT NULL;
```

**Lưu ý:** giai đoạn 4 chỉ kiểm tra tập giá trị **khi trường có dữ liệu**; `NULL` vẫn không bị `CHECK` này từ chối. Phải kiểm tra/backfill đủ trước khi `SET NOT NULL`. Tính khả thi của `SET NOT NULL`, thời gian quét bảng và mức khóa khi thay schema phụ thuộc phiên bản PostgreSQL, kích thước bảng và kế hoạch triển khai; không mặc định thao tác tức thời hoặc không khóa.

Trong PostgreSQL, một `CHECK ... NOT VALID` mới vẫn được áp dụng cho các hàng mới/được sửa; `VALIDATE CONSTRAINT` kiểm tra dữ liệu đã tồn tại. Cần phân biệt các tính năng DB hỗ trợ `NOT VALID` với việc thêm `NOT NULL`.

Nếu dữ liệu cũ có đơn qua nhiều kênh không thể suy ra, **không được gán toàn bộ thành `WEB`** chỉ để lấp null. Cần dữ liệu nguồn để backfill, hoặc định nghĩa rõ trạng thái `UNKNOWN` nếu nghiệp vụ cho phép.

### 10.2. Thay đổi miền giá trị và độ rộng

Khi thêm `status = 'REFUNDED'`, cả DB và ứng dụng phải được triển khai theo thứ tự tương thích. Nếu DB cho phép giá trị mới nhưng consumer/ứng dụng cũ không biết đọc, có thể gây lỗi. Nếu app mới ghi trước khi DB nới `CHECK`, ghi sẽ thất bại. Cần kế hoạch cho giai đoạn nhiều phiên bản chạy song song.

Khi tăng từ `INTEGER` sang `BIGINT` hoặc đổi `NUMERIC(12,2)` thành `NUMERIC(18,2)`, phải kiểm tra tác động lên Java DTO, API, chỉ mục, tệp xuất, báo cáo và bản sao. Những thao tác thay kiểu có thể phải viết lại dữ liệu hoặc khóa bảng; cần đo và triển khai theo quy trình migration có phiên bản.

### 10.3. Không sửa dữ liệu lịch sử bằng một mặc định sai

Đổi một cột nullable thành bắt buộc là thay đổi ý nghĩa nghiệp vụ. Trước khi backfill, hãy hỏi:

- Dữ liệu cũ có thực sự thiếu hay giá trị bị mất khi nhập?
- Có nguồn khác giúp khôi phục giá trị thật không?
- Có cần thêm trạng thái “không xác định” thay vì suy đoán?
- Hệ thống báo cáo có đang coi `NULL` theo một cách cụ thể không?
- Bản sao lưu và log cũ có thể phục hồi vào schema mới không?

Migration chỉ hoàn thành khi ứng dụng có thể **ghi và đọc đúng cả dữ liệu cũ lẫn dữ liệu mới**, không chỉ khi câu `ALTER TABLE` chạy thành công.

## 11. Chỉ mục và hiệu năng gắn với kiểu cột

Các lựa chọn kiểu và ràng buộc ảnh hưởng chi phí truy cập:

- `BIGINT` thường chiếm nhiều byte hơn `INTEGER`; không cần dùng vô hạn độ rộng nếu hệ thống biết giới hạn, nhưng cũng không chọn quá nhỏ rồi tràn.
- `NUMERIC` phù hợp số chính xác nhưng có chi phí xử lý khác với số nguyên/dấu phẩy động; chọn theo tính đúng đắn trước rồi đo.
- `VARCHAR` và `TEXT` có đặc điểm chỉ mục, collation và so sánh; index một biểu thức chuẩn hóa như `lower(email)` cần được đánh giá bằng truy vấn thực tế.
- `UNIQUE` và `PRIMARY KEY` thường được DB hỗ trợ bằng chỉ mục; ghi thêm phải duy trì cấu trúc ấy.
- `FOREIGN KEY` không mặc nhiên tạo chỉ mục trên cột tham chiếu ở bảng con trong PostgreSQL; có thể cần thêm index khi thường xuyên join, truy vấn hoặc xóa/sửa hàng cha.
- `CHECK` phức tạp có thể tăng chi phí ghi; các hàm trong constraint cần được chọn cẩn thận.
- Dữ liệu có nhiều `NULL` có thể ảnh hưởng thống kê và kế hoạch truy vấn; lập chỉ mục/partial index nên dựa trên workload thật.

Ví dụ:

```sql
-- Hữu ích nếu thường xuyên tìm đơn theo khách và thời điểm mới nhất.
CREATE INDEX idx_orders_customer_recent
ON orders (customer_id, created_at DESC, id DESC);
```

**Không tạo lại chỉ mục trên cùng cột nếu đã tồn tại chỉ mục tương đương.** Lược đồ mẫu đã khai báo `idx_orders_customer_created` cho truy vấn này; câu SQL trên chỉ minh họa hình dạng chỉ mục, không phải yêu cầu chạy thêm trong cùng DB. Trước khi thêm, xem `EXPLAIN`, số hàng và chi phí ghi, rồi đo lại sau thay đổi.

Tăng chỉ mục giúp nhiều truy vấn đọc nhưng có thể làm chậm insert/update, tăng dung lượng và thời gian migration. Khi có tải ghi cao, cân đối theo độ trễ p95/p99 và tốc độ xử lý thực tế.

## 12. Bảo mật và tính đúng đắn ở ranh giới dữ liệu

Một kiểu cột đúng không tự đảm bảo dữ liệu được sử dụng an toàn. Các quy tắc nền:

1. **Truy vấn tham số hóa:** sử dụng `PreparedStatement`/query parameter thay vì chắp chuỗi đầu vào vào SQL. Ràng buộc `CHECK` không chống được SQL injection.
2. **Phân quyền:** người dùng có quyền sửa ghi chú chưa chắc có quyền đổi `status`, `total` hoặc `customer_id`. Chỉ cho phép thay đổi các trường được công khai trong API.
3. **Quyền DB tối thiểu:** tài khoản ứng dụng không nên có quyền thay đổi schema tùy ý hoặc tắt ràng buộc.
4. **Đa tenant:** mọi truy vấn và cập nhật phải kiểm soát phạm vi sở hữu/tenant. `NOT NULL` trên `tenant_id` là cần thiết nếu mọi bản ghi bắt buộc có tenant, nhưng tự nó không ngăn người dùng truy cập tenant khác.
5. **Giới hạn payload và bảo vệ bí mật:** dùng giới hạn kích thước ở API, phân quyền dữ liệu nhạy cảm, bảo vệ kết nối và tránh log SQL có tham số nhạy cảm.
6. **Kiểm tra định dạng và đơn vị:** các trường số tiền, thời điểm, email và mã định danh cần quy tắc parse/normalize rõ, không nhận mù mọi chuỗi chỉ vì DB cho phép `VARCHAR`.
7. **Sao lưu và phục hồi:** bản sao lưu phải giữ schema và constraints tương ứng; diễn tập phục hồi, kiểm tra checksum và xác minh dữ liệu sau khôi phục.

Một hệ thống có thể có ràng buộc đầy đủ nhưng vẫn sai nếu service cho người dùng đổi `customer_id` sang khách hàng của người khác; DB chỉ biết ID đó tồn tại, không biết người gọi có quyền hay không. Quy tắc phân quyền phải được kiểm soát theo ngữ cảnh người dùng và nghiệp vụ.

## 13. Những lỗi thiết kế thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách tránh |
| --- | --- | --- |
| Dùng `VARCHAR` cho mọi giá trị | Mất kiểm tra kiểu, sắp xếp/truy vấn số có thể sai | Dùng kiểu SQL đúng theo ý nghĩa |
| Dùng `DOUBLE` để lưu tiền chính xác | Sai số nhị phân, tổng cộng/so sánh khó tin cậy | `NUMERIC/DECIMAL` và `BigDecimal` |
| Dùng `CHECK (x >= 0)` nhưng không `NOT NULL` | `NULL` có thể lọt qua vì logic ba giá trị | Khai báo tính bắt buộc riêng |
| Dùng `DEFAULT` để giả định client truyền `NULL` sẽ được thay | DEFAULT không tự áp khi gửi null tường minh | Thiết kế DTO và câu INSERT rõ |
| Dùng chuỗi rỗng hoặc `0` để thay mọi `NULL` | Mất thông tin “chưa biết” và thống kê sai | Xác định ý nghĩa từng trạng thái |
| Chỉ validate ở frontend | Job/batch và luồng ghi khác có thể bỏ qua | Ràng buộc tại DB và validation Java |
| Đặt unique email mà không định nghĩa chính sách so sánh | Trùng logic hoặc từ chối sai tùy collation | Làm rõ canonicalization/unique key |
| Thêm `NOT NULL` vào bảng cũ không backfill | Migration lỗi hoặc dữ liệu bị gán mặc định sai | Expand, backfill dựa trên bằng chứng, validate, contract |
| Dùng `CHECK` như cơ chế kiểm tổng nhiều bảng | Không bảo vệ được thay đổi đồng thời giữa nhiều hàng | Transaction, khóa, điều kiện ghi và thiết kế tổng |
| Dùng `@NotNull` của Java làm thay thế ràng buộc DB | Validator có thể không chạy trên mọi đường ghi | Giữ `NOT NULL`/constraints trong schema |
| Gộp `created_at` và `updated_at` | Không phân biệt thời điểm tạo và sửa | Hai cột với quy tắc cập nhật rõ |
| Trả lỗi SQL nguyên văn cho client | Có thể lộ dữ liệu và chi tiết hệ thống | Phân loại SQLSTATE/constraint, thông điệp an toàn |

## 14. Quy trình chọn kiểu và tính bắt buộc cho một trường mới

Trước khi thêm một trường vào schema, trả lời lần lượt:

1. **Ý nghĩa:** dữ liệu mô tả điều gì? Đơn vị, múi giờ, phạm vi hay danh tính nào?
2. **Kiểu và giới hạn:** có cần số nguyên, decimal chính xác, ngày lịch, thời điểm, chuỗi hay JSON? Phạm vi tối đa là bao nhiêu?
3. **Tính bắt buộc:** khi tạo có bắt buộc không? Có khi nào chưa biết/không áp dụng? `NULL` khác giá trị rỗng thế nào?
4. **Mặc định:** có giá trị mặc định **thật sự đúng về nghiệp vụ** không? Ai tạo mặc định: app hay DB?
5. **Miền và quan hệ:** có thể dùng `CHECK`, `UNIQUE`, FK hay bảng tham chiếu không? Có quy tắc chuyển trạng thái?
6. **Đồng thời và giao dịch:** điều kiện có liên quan nhiều hàng/bảng hay trạng thái trước cập nhật không?
7. **API và Java:** parser, DTO, validation, mapper JDBC/ORM xử lý null và kiểu đúng chưa?
8. **Tiến hóa schema:** dữ liệu cũ sẽ được backfill thế nào? App cũ có còn ghi trong lúc triển khai?
9. **Vận hành:** chỉ mục nào phục vụ truy vấn, backup/schema lịch sử khôi phục được không, quyền và retention được quản lý thế nào?
10. **Kiểm thử:** tạo trường hợp hợp lệ, biên, null, giá trị ngoài miền, lỗi đồng thời và rollback để chứng minh quy tắc.

Đặt tên constraints có ý nghĩa, ví dụ `ck_order_total`, giúp điều tra lỗi và viết migration dễ hơn so với chỉ dựa vào tên tự sinh khó hiểu.

## 15. Bài thực hành tổng hợp

Dùng PostgreSQL thử nghiệm và ứng dụng Java nhỏ. Thực hiện trên dữ liệu giả lập; lưu DDL trong migration có phiên bản nếu môi trường học tập sử dụng công cụ migration.

### Phần A — Phân loại trường và miền

Với thực thể `orders`, lập bảng mô tả:

| Trường | Kiểu đề xuất | Bắt buộc? | Miền/nguồn giá trị |
| --- | --- | --- | --- |
| `id` | `BIGINT IDENTITY` | Có | DB sinh, khóa chính |
| `customer_id` | `BIGINT` | Có | FK đến khách hàng hiện hữu |
| `currency` | `VARCHAR(3)` | Có | `VND`/`USD` trong ví dụ |
| `total` | `NUMERIC(18,2)` | Có | `>= 0`, đúng scale |
| `status` | `VARCHAR(16)` | Có | `DRAFT`/`PAID`/`CANCELLED`, mặc định `DRAFT` |
| `note` | `TEXT` | Không | `NULL` hoặc chuỗi, theo giới hạn API |
| `paid_at` | `TIMESTAMPTZ` | Có điều kiện | Bắt buộc nếu `PAID` |
| `version` | `BIGINT` | Có | `>=0`, tăng khi cập nhật |

Giải thích trường hợp nào cần `NOT NULL`, `DEFAULT`, `CHECK`, FK hoặc ràng buộc ở service.

### Phần B — Chạy các trường hợp biên

1. Tạo khách hàng với tên hợp lệ, thử tên rỗng/chỉ khoảng trắng.
2. Tạo đơn không truyền `status`; xác nhận nhận `DRAFT`.
3. Gửi `status = NULL` tường minh; xác nhận lỗi `NOT NULL`.
4. Gửi `total = -0.01`, `NULL` và giá trị quá lớn; ghi nhận loại lỗi.
5. Thử `total = 1.234`; so sánh hành vi DB với validation `RoundingMode.UNNECESSARY` ở Java.
6. Tạo đơn `PAID` không có `paid_at`; xác nhận `CHECK` từ chối.
7. Tạo đơn tham chiếu `customer_id` không tồn tại; xác nhận FK.
8. Đọc `note` là `NULL` và `''`; chứng minh hai kết quả khác nhau.
9. Gọi hai cập nhật cùng `expected_version`; chỉ một lệnh thành công khi có điều kiện phiên bản.
10. Viết một trường hợp SQL cố tính làm `CHECK` có biểu thức `UNKNOWN`; giải thích vì sao `NOT NULL` cần thiết.

### Phần C — Migration

Giả sử muốn thêm `sales_channel` bắt buộc:

1. Thêm cột nullable.
2. Triển khai đường ghi mới theo một hợp đồng rõ.
3. Tìm nguồn dữ liệu để backfill hàng cũ, ghi nhận những hàng không thể suy ra.
4. Thêm và validate kiểm tra miền giá trị, xác minh không còn null trước khi `SET NOT NULL`.
5. Kiểm thử phiên bản ứng dụng cũ và mới trên cùng schema trong giai đoạn chuyển tiếp.
6. Thử phục hồi backup của schema cũ và cách nâng dữ liệu lên schema mới.

### Phần D — Câu hỏi tự đánh giá

1. `NUMERIC(18,2)` và `DOUBLE PRECISION` khác nhau thế nào khi lưu tiền?
2. `NOT NULL` và `CHECK (x > 0)` có trùng chức năng không?
3. Tại sao `CHECK (total >= 0)` có thể cho phép `NULL`?
4. Khi `status` có `DEFAULT 'DRAFT'`, câu INSERT gửi `NULL` có nhận `DRAFT` không?
5. `''`, `NULL`, `0` và `FALSE` nên được xử lý như thế nào?
6. Vì sao khóa ngoại nullable không bảo đảm một đơn hàng phải thuộc khách hàng?
7. Nếu hai giao dịch cùng giảm tồn kho, `CHECK (stock >= 0)` có đủ bảo vệ số đơn được xác nhận không?
8. `@NotNull` trong Java có thay được `NOT NULL` của DB không?
9. Vì sao một trường bắt buộc mới cần chiến lược backfill trước khi siết schema?
10. Khi nào nên dùng `VARCHAR + CHECK`, bảng tham chiếu hay enum riêng của DB?
11. Vì sao `updated_at DEFAULT CURRENT_TIMESTAMP` không tự cập nhật khi chạy `UPDATE`?
12. Làm sao phân loại lỗi input sai, FK không tồn tại và xung đột đồng thời mà không tiết lộ SQL nội bộ?

Một schema bền vững phải mô tả **ý nghĩa dữ liệu**, không chỉ kích thước vùng lưu. Kiểu cột quyết định cách biểu diễn; miền giá trị xác định dữ liệu nào hợp lệ; `NOT NULL` và `DEFAULT` xác định cách xử lý khi trường thiếu; `CHECK`, khóa duy nhất và khóa ngoại bảo vệ các quy tắc tương ứng. Kết hợp chúng với validation Java, transaction, kiểm soát đồng thời và migration giúp dữ liệu tiếp tục đúng khi ứng dụng lớn lên và có nhiều nguồn ghi.
