# Chọn kiểu dữ liệu SQL theo ý nghĩa, miền giá trị và độ chính xác

Một cột trong cơ sở dữ liệu không chỉ chứa các byte. Kiểu dữ liệu của cột còn diễn đạt **ý nghĩa của dữ liệu**, giới hạn những giá trị hợp lệ, quyết định cách so sánh và tính toán, đồng thời ảnh hưởng đến bộ nhớ, chỉ mục và khả năng mở rộng. Chọn kiểu sai có thể làm mất chữ số, cho phép trạng thái vô lý hoặc khiến truy vấn không tận dụng được chỉ mục.

Ví dụ, số điện thoại `0901234567` gồm các chữ số nhưng không phải đại lượng để cộng trừ. Giá `19.99` cần tính toán thập phân chính xác; thời điểm giao dịch cần biểu diễn thời gian; tỷ lệ đo đạc có thể chấp nhận sai số xấp xỉ. Vì vậy không nên chọn kiểu chỉ vì hình thức bề ngoài của giá trị.

> Các ví dụ dùng cú pháp SQL gần với PostgreSQL. Tên kiểu, giới hạn độ dài, hành vi `TIMESTAMP`, `BOOLEAN`, `ENUM`, `JSON`, `UUID` và cách lưu trữ có khác biệt giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite. Khi triển khai cần đối chiếu tài liệu của hệ quản trị cụ thể.

## 1. Ba câu hỏi trước khi chọn kiểu

1. **Ý nghĩa:** Đây là số lượng, tiền, tỷ lệ, mã định danh, văn bản, ngày lịch, thời điểm, trạng thái hay dữ liệu nhị phân? Những thao tác hợp lệ là gì?
2. **Miền giá trị:** Giá trị nhỏ nhất/lớn nhất, số chữ số, độ dài văn bản, tập giá trị được phép, khả năng `NULL` và mức tăng trưởng dự kiến là bao nhiêu?
3. **Độ chính xác:** Có được làm tròn không? Nếu là số thập phân, cần bao nhiêu chữ số nguyên và chữ số sau dấu phẩy? Nếu là thời gian, cần độ phân giải giây, mili giây hay micro giây? Nếu là văn bản, cần giữ nguyên mọi ký tự Unicode không?

Sau đó mới cân nhắc chi phí lưu trữ, hiệu năng truy vấn, tương thích ứng dụng và khả năng thay đổi schema.

| Dữ liệu | Kiểu thường phù hợp | Vì sao |
|---|---|---|
| Số lượng sản phẩm nguyên | `INTEGER` / `BIGINT` | Cộng, trừ, so sánh số học; có miền giá trị rõ ràng |
| Giá, số tiền có số lẻ cố định | `DECIMAL(p,s)` / `NUMERIC(p,s)` | Tính toán thập phân chính xác |
| Kết quả đo khoa học có sai số | `REAL` / `DOUBLE PRECISION` | Biểu diễn số thực xấp xỉ trên miền rất rộng |
| Số điện thoại, mã bưu chính | `VARCHAR(n)` hoặc `TEXT` | Giữ số 0 đầu, dấu `+`, dấu gạch và không tính toán số học |
| Mã SKU, mã hóa đơn | `VARCHAR(n)` | Là định danh có thể chứa chữ, số và ký tự phân tách |
| Tên, mô tả | `VARCHAR(n)` / `TEXT` | Dữ liệu văn bản Unicode |
| Ngày sinh, ngày đến hạn | `DATE` | Chỉ cần ngày lịch, không cần giờ |
| Giờ mở cửa mỗi ngày | `TIME` | Chỉ cần giờ trong ngày; múi giờ phải được xử lý theo ngữ cảnh |
| Thời điểm tạo bản ghi | `TIMESTAMP WITH TIME ZONE` hoặc tương đương | Cần xác định một thời điểm trên trục thời gian |
| Có/không | `BOOLEAN` | Thể hiện đúng miền logic hai trạng thái, có thể thêm `NULL` nếu chưa biết |
| Mã định danh ngẫu nhiên | `UUID` nếu DBMS hỗ trợ | Định danh riêng, không giả định ý nghĩa số học |
| Tệp, ảnh thô | `BLOB` / `BYTEA` | Lưu byte, không phải văn bản |

## 2. Số nguyên: chọn theo miền giá trị thực tế

Các họ kiểu phổ biến gồm `SMALLINT`, `INTEGER` (`INT`) và `BIGINT`. Trong PostgreSQL, chúng lần lượt dùng 2, 4 và 8 byte, với miền giá trị có dấu:

| Kiểu PostgreSQL | Miền giá trị |
|---|---:|
| `SMALLINT` | −32.768 đến 32.767 |
| `INTEGER` | −2.147.483.648 đến 2.147.483.647 |
| `BIGINT` | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |

Các hệ khác có thể cung cấp kiểu `TINYINT`, kiểu `UNSIGNED` hoặc giới hạn khác. Đừng mặc định rằng mọi hệ đều hỗ trợ cùng một kiểu hoặc miền số.

Nếu `quantity` không bao giờ âm, `INTEGER` kết hợp `CHECK (quantity >= 0)` diễn đạt quy tắc nghiệp vụ. Nếu bộ đếm sự kiện có thể tăng vượt 2,1 tỷ, nên cân nhắc `BIGINT` từ đầu. Khóa chính tự tăng thường dùng `BIGINT` khi quy mô lớn, nhưng nhu cầu thực tế và chi phí chỉ mục vẫn cần được cân nhắc.

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT ck_inventory_quantity CHECK (quantity >= 0)
);
```

**Phân biệt số và định danh:** `employee_number` có thể là số nguyên nếu ứng dụng thực sự coi nó như một số đếm và không có số 0 đầu. Ngược lại, `customer_code = '000047'` phải lưu kiểu chuỗi nếu 6 ký tự và số 0 đầu là một phần của mã.

## 3. Số thập phân chính xác và số thực xấp xỉ

### `DECIMAL(p,s)` / `NUMERIC(p,s)`

`p` (*precision*) là tổng số chữ số thập phân; `s` (*scale*) là số chữ số sau dấu thập phân. Vì vậy `DECIMAL(12,2)` thông thường chứa tối đa 10 chữ số phần nguyên và 2 chữ số phần thập phân, ví dụ `1234567890.12`; không thể chứa `12345678901.23` vì vượt tổng độ chính xác 12 chữ số.

```sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    unit_price NUMERIC(12, 2) NOT NULL,
    tax_rate NUMERIC(7, 6) NOT NULL,
    CONSTRAINT ck_price_nonnegative CHECK (unit_price >= 0),
    CONSTRAINT ck_tax_range CHECK (tax_rate BETWEEN 0 AND 1)
);
```

Một số hệ có thể làm tròn số nhập đến `s` chữ số trước khi kiểm tra giới hạn; không nên dựa vào `NUMERIC(12,2)` để tự động **từ chối** mọi giá trị có hơn hai chữ số lẻ. Nếu yêu cầu từ chối thay vì làm tròn, hãy kiểm tra ở lớp nhập liệu và/hoặc ràng buộc phù hợp với DBMS.

Tiền tệ không chỉ là kiểu dữ liệu: cần xác định đơn vị tiền, số chữ số nhỏ nhất, quy tắc làm tròn và phương pháp tính thuế. Chẳng hạn lưu `amount NUMERIC(18,2)` cùng `currency_code CHAR(3)` có thể phù hợp khi hệ thống chỉ hỗ trợ các đồng tiền với hai chữ số thập phân; nếu hỗ trợ nhiều đồng tiền có quy tắc phần lẻ khác nhau, phải thiết kế theo yêu cầu cụ thể. Một lựa chọn khác là lưu số đơn vị nhỏ nhất bằng `BIGINT` khi đã quy định rõ đơn vị và kiểm soát phép chuyển đổi.

### `REAL` / `FLOAT` / `DOUBLE PRECISION`

Các kiểu dấu phẩy động thường dùng biểu diễn nhị phân xấp xỉ theo chuẩn IEEE 754 (tùy DBMS). Chúng thích hợp cho đo đạc, mô phỏng, dữ liệu cảm biến và tính toán chấp nhận sai số; không thích hợp làm kiểu mặc định cho số tiền cần kết quả thập phân chính xác.

Ví dụ, giá trị thập phân `0.1` thường không biểu diễn chính xác bằng số thực nhị phân. Vì thế phép cộng `0.1 + 0.2` bằng dấu phẩy động có thể không so sánh bằng chính xác với `0.3` trong một số ngữ cảnh. Khi dùng số thực, nên so sánh có dung sai thích hợp, tránh kiểm tra bằng tuyệt đối nếu thuật toán không bảo đảm điều đó.

**Quy tắc:** giá trị cần đối soát tài chính, tính tiền, tỷ lệ chính xác theo quy định → `NUMERIC/DECIMAL`; phép đo hoặc mô phỏng cần khoảng giá trị rộng và chấp nhận sai số → số thực xấp xỉ.

## 4. Chuỗi và Unicode: độ dài phải bám vào quy tắc dữ liệu

`CHAR(n)` là chuỗi độ dài cố định, có thể được đệm khoảng trắng; `VARCHAR(n)` giới hạn độ dài; `TEXT` phù hợp cho nội dung không có giới hạn độ dài ngắn cố định. Với PostgreSQL, không nên mặc định `VARCHAR(n)` nhanh hơn `TEXT`: cách lưu trữ và hiệu năng phụ thuộc DBMS, dữ liệu, chỉ mục và truy vấn.

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    phone VARCHAR(32),
    postal_code VARCHAR(20),
    notes TEXT
);
```

Một số lưu ý quan trọng:

- Điện thoại có thể bắt đầu bằng `0`, chứa `+84`, khoảng trắng hoặc phần mở rộng. Lưu dưới dạng chuỗi, chuẩn hóa định dạng riêng nếu cần tìm kiếm.
- Mã bưu chính, mã hàng, số thẻ có ý nghĩa định danh, không làm phép cộng trừ; tránh kiểu số nguyên dù toàn chữ số.
- Tên người có dấu, nhiều hệ chữ viết và độ dài biến thiên; thiết kế Unicode và kiểm tra collation thích hợp. Độ dài theo **ký tự** không phải lúc nào bằng độ dài theo **byte** hoặc số ký tự người dùng nhìn thấy.
- `CHAR(n)` không mặc nhiên tốt hơn `VARCHAR(n)` cho mã cố định. Khoảng trắng đệm có thể ảnh hưởng so sánh và xử lý trong ứng dụng; hãy kiểm tra hành vi hệ quản trị.
- Giới hạn `VARCHAR(n)` nên xuất phát từ quy tắc nghiệp vụ hoặc giao thức, không phải một con số tùy tiện như 255 cho mọi cột.

**Collation** ảnh hưởng đến sắp xếp và so sánh, ví dụ phân biệt chữ hoa/thường và dấu. Chọn collation phù hợp với nhu cầu ngôn ngữ, đồng thời nhớ rằng quy tắc duy nhất (`UNIQUE`) có thể bị ảnh hưởng bởi phép so sánh đang dùng. Nếu cần tìm email không phân biệt chữ hoa/thường, phải xác định chính sách chuẩn hóa/so sánh và chỉ mục tương ứng.

## 5. Ngày, giờ và múi giờ

Đây là nhóm rất dễ chọn nhầm vì nhiều khái niệm cùng hiển thị dạng chữ số.

| Ý nghĩa dữ liệu | Kiểu gợi ý | Ví dụ |
|---|---|---|
| Ngày lịch độc lập với giờ | `DATE` | `2026-11-14` |
| Giờ trong ngày | `TIME` | `09:30:00` |
| Ngày giờ địa phương, chưa gắn múi giờ | `TIMESTAMP WITHOUT TIME ZONE` | Lịch họp 09:30 theo quy tắc địa phương |
| Một thời điểm xảy ra trên toàn cầu | `TIMESTAMP WITH TIME ZONE` trong PostgreSQL | Thời điểm đặt hàng được ghi nhận |

Trong PostgreSQL, `TIMESTAMP WITH TIME ZONE` (`timestamptz`) biểu diễn **một thời điểm tuyệt đối**, được chuẩn hóa nội bộ và hiển thị theo múi giờ của phiên làm việc; nó **không lưu nguyên tên múi giờ gốc** như `Asia/Ho_Chi_Minh`. Nếu nghiệp vụ cần biết múi giờ do người dùng chọn, phải lưu thêm thông tin đó. Các DBMS khác, đặc biệt SQL Server và MySQL, có kiểu và hành vi khác; không đánh đồng chỉ vì tên giống nhau.

```sql
CREATE TABLE appointments (
    appointment_id BIGINT PRIMARY KEY,
    starts_at TIMESTAMPTZ NOT NULL,
    time_zone VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Với các cuộc hẹn lặp lại lúc 09:00 mỗi sáng theo giờ địa phương, chỉ lưu một `TIMESTAMPTZ` là chưa đủ để tính các kỳ sau khi có thay đổi giờ mùa hè. Hãy lưu quy tắc lịch địa phương và tên múi giờ IANA nếu bài toán yêu cầu. Không lưu thời điểm quan trọng như một chuỗi tùy ý `VARCHAR`, vì sẽ mất kiểm tra kiểu và dễ phát sinh lỗi định dạng, sắp xếp, so sánh.

## 6. Boolean, tập trạng thái và `NULL`

`BOOLEAN` hợp với thuộc tính đúng/sai như `is_active`. Trong SQL, `NULL` thể hiện thiếu/không biết giá trị; biểu thức logic có thể có kết quả `UNKNOWN` theo logic ba giá trị. Vì thế `NULL` không đồng nghĩa `FALSE`.

```sql
CREATE TABLE user_settings (
    user_id BIGINT PRIMARY KEY,
    notifications_enabled BOOLEAN NOT NULL DEFAULT FALSE
);
```

Nếu thuộc tính có nhiều trạng thái như `PENDING`, `PAID`, `CANCELLED`, dùng `BOOLEAN` là sai miền ý nghĩa. Có thể dùng `VARCHAR` kèm `CHECK`, bảng tham chiếu với khóa ngoại, hoặc `ENUM` nếu DBMS hỗ trợ. Quyết định phụ thuộc tần suất thay đổi tập trạng thái và nhu cầu quản lý metadata.

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    CONSTRAINT ck_order_status CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
);
```

`NOT NULL` là một phần của thiết kế miền giá trị. Hãy cho phép `NULL` khi thực sự có nghĩa như “chưa cung cấp” hoặc “chưa biết”, thay vì dùng chuỗi rỗng, `0`, ngày giả `1900-01-01` làm giá trị thay thế mà không có định nghĩa nghiệp vụ.

## 7. UUID, JSON, nhị phân và các kiểu chuyên biệt

- **UUID:** hợp với khóa định danh phân tán hoặc ID khó đoán. UUID không đồng nghĩa dữ liệu được mã hóa hay bí mật; UUID ngẫu nhiên có thể làm thay đổi tính cục bộ của chỉ mục so với ID tăng tuần tự. Nếu cần UUID, ưu tiên kiểu `UUID` bản địa khi hệ quản trị hỗ trợ.
- **JSON/JSONB:** thích hợp cho thuộc tính mở rộng có cấu trúc biến đổi hoặc dữ liệu tích hợp. Các trường cốt lõi thường được lọc, nối bảng, kiểm tra ràng buộc nên có cột quan hệ rõ ràng; đừng đưa toàn bộ mô hình vào một JSON chỉ để khỏi thiết kế schema. `JSONB` là kiểu riêng của PostgreSQL và có hành vi/chỉ mục khác `JSON`.
- **BLOB/BYTEA:** lưu byte nhị phân như tài liệu hoặc ảnh; cân nhắc lưu object ở dịch vụ lưu trữ và giữ URI/metadata trong DB khi file lớn hoặc cần phân phối độc lập.
- **ARRAY, INTERVAL, kiểu không gian (GIS):** dùng khi ý nghĩa và thao tác yêu cầu, nhưng kiểm tra khả năng hỗ trợ, chỉ mục và mức phụ thuộc hệ quản trị.

## 8. Kiểu dữ liệu và ràng buộc phải đi cùng nhau

Kiểu dữ liệu chỉ giới hạn miền **kỹ thuật**; ràng buộc mới diễn đạt thêm miền **nghiệp vụ**. `INTEGER` vẫn chứa được số âm; `NUMERIC(12,2)` vẫn chứa được giá âm; `VARCHAR(3)` vẫn có thể chứa ba ký tự không hợp lệ.

```sql
CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    discount_rate NUMERIC(5, 4) NOT NULL DEFAULT 0,
    CONSTRAINT pk_order_items PRIMARY KEY (order_id, line_no),
    CONSTRAINT ck_line_no CHECK (line_no > 0),
    CONSTRAINT ck_quantity_positive CHECK (quantity > 0),
    CONSTRAINT ck_price_nonnegative CHECK (unit_price >= 0),
    CONSTRAINT ck_discount_rate CHECK (discount_rate BETWEEN 0 AND 1)
);
```

Thiết kế trên bảo đảm số lượng lớn hơn 0, đơn giá không âm và tỷ lệ giảm giá trong khoảng 0 đến 1. `discount_rate NUMERIC(5,4)` cho phép độ phân giải 0,0001; nếu cần chính xác hơn phải tăng scale. Trong hệ thống thực tế còn cần khóa ngoại tới đơn hàng/sản phẩm, quy tắc chuyển trạng thái và giao dịch phù hợp.

Không nên xem `CHECK` là giải pháp cho mọi xác thực. Ví dụ, kiểm tra email đúng chuẩn thực tế rất phức tạp, thường kết hợp xác thực ứng dụng với ràng buộc dữ liệu thiết yếu. Dùng `UNIQUE` cho quy tắc không trùng lặp và `FOREIGN KEY` cho tính toàn vẹn tham chiếu.

## 9. Từ yêu cầu nghiệp vụ đến DDL: ví dụ thực tế

Giả sử ứng dụng bán hàng cần lưu:

| Thuộc tính | Yêu cầu | Quyết định |
|---|---|---|
| Mã đơn hàng | Định danh, không tính toán | `BIGINT` làm khóa chính |
| Mã khách hàng | Có thể chứa chữ và số 0 đầu | `VARCHAR(30)` |
| Tổng tiền | Tối đa 12 chữ số phần nguyên và 2 chữ số lẻ | `NUMERIC(14,2)` |
| Tiền tệ | Mã ISO ba ký tự | `CHAR(3)` kèm kiểm tra danh mục ở tầng phù hợp |
| Thời điểm đặt | Có thể so sánh xuyên múi giờ | `TIMESTAMPTZ` (PostgreSQL) |
| Trạng thái | Chỉ một số giá trị hợp lệ | `VARCHAR(16)` + `CHECK` |
| Ghi chú | Văn bản không dự đoán được độ dài | `TEXT` |

```sql
CREATE TABLE sales_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_code VARCHAR(30) NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    note TEXT,
    CONSTRAINT ck_total_amount CHECK (total_amount >= 0),
    CONSTRAINT ck_currency_code CHECK (currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_sales_status CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
);
```

`GENERATED ALWAYS AS IDENTITY`, `TIMESTAMPTZ` và toán tử regex `~` ở đây theo PostgreSQL; phải điều chỉnh khi chuyển DBMS. Ràng buộc ba chữ cái **không bảo đảm** mã tiền tệ thực sự tồn tại trong ISO 4217: muốn bảo đảm điều đó cần danh mục hợp lệ và chính sách cập nhật danh mục.

### Cách kiểm tra trước khi chốt schema

1. Liệt kê vài giá trị hợp lệ và **không hợp lệ** cho mỗi cột, kể cả dữ liệu biên.
2. Tính giới hạn tăng trưởng theo năm: số bản ghi, giá trị tổng lớn nhất, độ dài mã dài nhất.
3. Xác định phép tính, phép so sánh, phép sắp xếp, bộ lọc và chỉ mục cần dùng.
4. Chỉ rõ chính sách làm tròn, múi giờ, Unicode, `NULL` và chuẩn hóa dữ liệu.
5. Viết `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` theo bất biến nghiệp vụ; thử chèn giá trị biên trong DBMS mục tiêu.
6. Kiểm tra kiểu tương ứng giữa cơ sở dữ liệu và ứng dụng, ví dụ Java `BigDecimal` cho `NUMERIC`, `LocalDate` cho `DATE`, `Instant` hoặc `OffsetDateTime` tùy cách ánh xạ thời điểm, `Long` cho `BIGINT`. Ánh xạ và cách xử lý múi giờ còn tùy driver/JPA và cấu hình.

## 10. Những sai lầm thường gặp

| Lựa chọn sai | Hệ quả | Hướng sửa |
|---|---|---|
| Dùng `FLOAT` cho số tiền cần đối soát | Sai số biểu diễn nhị phân | `DECIMAL/NUMERIC` với precision, scale rõ ràng |
| Dùng `INT` cho điện thoại/mã bưu chính | Mất số 0 đầu, không chứa dấu `+` | Dùng kiểu chuỗi |
| Dùng `VARCHAR` cho thời điểm | Khó kiểm tra và thao tác thời gian | Dùng kiểu ngày/giờ phù hợp |
| Dùng `TIMESTAMP` thiếu ngữ cảnh múi giờ | Sai lệch khi tích hợp nhiều vùng | Phân biệt giờ địa phương và thời điểm tuyệt đối |
| Chọn `VARCHAR(255)` cho mọi chuỗi | Không diễn đạt giới hạn nghiệp vụ | Xác định giới hạn thực tế hoặc dùng `TEXT` |
| Chọn `SMALLINT` chỉ vì tiết kiệm byte | Có nguy cơ tràn miền giá trị | Ước tính tăng trưởng và chọn miền đủ rộng |
| Dùng `BOOLEAN` cho nhiều trạng thái | Không biểu diễn đủ nghiệp vụ | Dùng tập trạng thái có ràng buộc |
| Dùng `NULL` hoặc giá trị giả không rõ nghĩa | Dữ liệu mơ hồ, truy vấn sai | Định nghĩa ngữ nghĩa `NULL`, dùng ràng buộc |
| Đưa mọi thuộc tính vào JSON | Khó kiểm tra, nối và tối ưu truy vấn | Thiết kế cột quan hệ cho thuộc tính cốt lõi |

## Kết luận

Quy trình lựa chọn kiểu dữ liệu nên bắt đầu bằng **ý nghĩa → miền giá trị → độ chính xác**, sau đó bổ sung các ràng buộc nghiệp vụ và kiểm tra trên DBMS thực tế. Một kiểu dữ liệu tốt giúp cơ sở dữ liệu ngăn dữ liệu sai ngay từ đầu, giữ đủ độ chính xác, hỗ trợ truy vấn rõ ràng và giảm chi phí thay đổi schema về sau.
