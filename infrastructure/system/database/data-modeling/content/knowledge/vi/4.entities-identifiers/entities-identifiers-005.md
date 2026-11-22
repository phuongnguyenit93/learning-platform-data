# Khóa đơn, khóa ghép và phạm vi duy nhất theo ngữ cảnh

## 1. Vì sao phải xác định khóa và phạm vi duy nhất?

Mô hình dữ liệu cần phân biệt được từng đối tượng và ngăn những bản ghi vi phạm quy tắc nhận diện của nghiệp vụ. Khóa (key) cung cấp cách nhận diện một bản ghi; ràng buộc duy nhất (unique constraint) bảo đảm một giá trị hoặc tổ hợp giá trị không bị lặp trong phạm vi đã xác định.

Có những giá trị chỉ cần duy nhất trên toàn hệ thống, chẳng hạn mã định danh của một đơn hàng. Có những giá trị chỉ duy nhất trong một ngữ cảnh: mã phòng họp duy nhất trong một tòa nhà, số dòng hàng duy nhất trong một đơn hàng, hoặc tên người dùng duy nhất trong một tổ chức. Nếu bỏ qua phạm vi, mô hình có thể từ chối dữ liệu hợp lệ hoặc cho phép dữ liệu trùng làm sai nghiệp vụ.

Bài học này tập trung vào ba quyết định liên quan:

- **Khóa đơn:** một thuộc tính đủ để nhận diện một bản ghi.
- **Khóa ghép:** hai hay nhiều thuộc tính kết hợp để nhận diện một bản ghi.
- **Phạm vi duy nhất:** các giá trị phải duy nhất ở đâu và trong điều kiện nào, ví dụ toàn cục, theo tổ chức, theo bản ghi cha, theo thời gian hoặc chỉ trong nhóm bản ghi đang hoạt động.

Các quyết định này thuộc phần cốt lõi của mô hình dữ liệu. Chúng ảnh hưởng đến khóa chính, khóa ngoại, cách liên kết bảng, khả năng nhập dữ liệu, xử lý đồng thời và cách bảo vệ tính toàn vẹn khi hệ thống phát triển.

## 2. Các khái niệm khóa cần phân biệt

### 2.1. Superkey và candidate key

Một **superkey** (siêu khóa) là một tập thuộc tính có thể xác định duy nhất một bản ghi trong quan hệ. Tập thuộc tính có thể chứa nhiều thuộc tính hơn mức cần thiết.

Một **candidate key** (khóa ứng viên) là superkey tối thiểu: không thể bỏ bớt bất kỳ thuộc tính nào mà vẫn bảo đảm nhận diện duy nhất.

Ví dụ, bảng `customer` có các thuộc tính:

- `customer_id`: mã khách hàng.
- `email_normalized`: email đã chuẩn hóa theo quy tắc của hệ thống.
- `full_name`: họ tên.
- `phone`: số điện thoại.

Giả sử `customer_id` và `email_normalized` đều duy nhất trong toàn hệ thống. Khi đó, mỗi thuộc tính riêng lẻ có thể là một candidate key. Tổ hợp `(customer_id, email_normalized)` cũng xác định duy nhất một bản ghi, nhưng không tối thiểu vì chỉ cần `customer_id` hoặc `email_normalized` đã đủ. Tổ hợp đó là superkey, không phải candidate key.

Khái niệm tối thiểu rất quan trọng khi thiết kế khóa ghép. Không nên thêm thuộc tính vào khóa chỉ để làm khóa trông "đặc biệt" hơn. Mỗi thành phần phải cần thiết cho tính duy nhất theo quy tắc đã xác định.

### 2.2. Primary key và alternate key

Trong các candidate key, mô hình chọn một khóa làm **primary key** (khóa chính). Những candidate key còn lại là **alternate key** (khóa thay thế).

Ví dụ:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    email_normalized VARCHAR(320) NOT NULL UNIQUE,
    full_name VARCHAR(200) NOT NULL
);
```

Ở đây:

- `customer_id` là primary key.
- `email_normalized` là alternate key được bảo vệ bằng ràng buộc `UNIQUE`.

Một bảng chỉ có một primary key, nhưng primary key có thể gồm nhiều cột. Bảng cũng có thể có nhiều ràng buộc unique để bảo vệ các candidate key khác.

Không nên mặc định rằng chỉ khóa chính mới cần duy nhất. Nếu email phải duy nhất theo quy tắc nghiệp vụ, việc chỉ đánh chỉ mục thường (non-unique index) sẽ không ngăn được hai bản ghi trùng email. Cần dùng ràng buộc hoặc chỉ mục unique phù hợp.

### 2.3. Khóa tự nhiên và khóa thay thế

**Khóa tự nhiên (natural key)** lấy từ dữ liệu hoặc quy tắc nghiệp vụ, ví dụ mã ISBN, mã số thuế, mã SKU hoặc mã nhân viên. Khóa tự nhiên có thể dễ hiểu và hữu ích khi trao đổi với người dùng, nhưng cần đánh giá tính ổn định, phạm vi cấp mã, khả năng sửa đổi và vấn đề bảo mật.

**Khóa thay thế (surrogate key)** là định danh kỹ thuật do hệ thống tạo ra, ví dụ số tăng tự động hoặc UUID. Nó thường không mang ý nghĩa nghiệp vụ trực tiếp và giúp liên kết bản ghi ổn định khi thuộc tính nghiệp vụ thay đổi.

Ví dụ, một khách hàng có thể đổi email nhưng `customer_id` vẫn giữ nguyên. Nếu dùng email làm khóa chính, thay đổi email sẽ kéo theo việc cập nhật mọi khóa ngoại tham chiếu đến khách hàng. Dùng khóa thay thế giúp tách định danh nội bộ khỏi thuộc tính nghiệp vụ có thể thay đổi.

Tuy nhiên, dùng khóa thay thế không làm mất nhu cầu bảo vệ khóa tự nhiên. Nếu email phải duy nhất trong một tenant, hệ thống vẫn cần ràng buộc `UNIQUE (tenant_id, email_normalized)`. Khóa thay thế trả lời "bản ghi nào?", còn unique constraint bảo vệ quy tắc "giá trị nghiệp vụ nào không được trùng?".

## 3. Khóa đơn

Khóa đơn là khóa gồm một thuộc tính. Ví dụ, `order_id` có thể nhận diện duy nhất một đơn hàng:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

Mỗi giá trị `order_id` chỉ thuộc về một đơn hàng. Khóa đơn thường dễ dùng trong khóa ngoại, URL, API và truy vấn tra cứu.

### 3.1. Khi nào khóa đơn phù hợp?

Khóa đơn phù hợp khi có một thuộc tính ổn định và đủ để nhận diện từng bản ghi. Ví dụ:

- Một UUID được hệ thống cấp cho mỗi giao dịch.
- Một mã hồ sơ được cấp duy nhất trên toàn hệ thống.
- Một số định danh nội bộ không thay đổi trong suốt vòng đời bản ghi.

Khóa đơn có thể là khóa tự nhiên hoặc khóa thay thế. Điều quan trọng là tính duy nhất phải đúng với phạm vi nghiệp vụ, giá trị không bị tái sử dụng sai cách và các bảng khác có thể tham chiếu ổn định.

### 3.2. Lưu ý khi chọn khóa đơn

Một thuộc tính có vẻ duy nhất ở thời điểm hiện tại chưa chắc là khóa tốt. Hãy kiểm tra:

- Giá trị có thể thay đổi không?
- Giá trị có thể bị cấp lại sau khi bản ghi bị xóa không?
- Có nguồn nào khác cũng tạo mã này không?
- Có giới hạn phạm vi theo tổ chức, chi nhánh hoặc quốc gia không?
- Giá trị có chứa dữ liệu nhạy cảm không?
- Kiểu dữ liệu và độ dài có phù hợp với các khóa ngoại và chỉ mục không?

Ví dụ, số điện thoại không phải lúc nào cũng là định danh ổn định: người dùng có thể đổi số hoặc một số có thể được cấp lại cho người khác. Nếu dùng số điện thoại làm candidate key, cần làm rõ quy tắc xác minh, tái sử dụng và lịch sử thay đổi.

## 4. Khóa ghép

Khóa ghép (composite key) gồm từ hai thuộc tính trở lên. Chỉ tổ hợp đầy đủ mới xác định duy nhất một bản ghi; từng thành phần riêng lẻ có thể lặp lại.

Ví dụ, một đơn hàng có nhiều dòng hàng. Số thứ tự dòng chỉ duy nhất trong từng đơn, không duy nhất trên toàn hệ thống. Có thể dùng cặp `(order_id, line_no)` làm khóa chính:

```sql
CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(18, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
```

Ví dụ dữ liệu:

| order_id | line_no | product_id | quantity |
|---:|---:|---:|---:|
| 7001 | 1 | 120 | 2 |
| 7001 | 2 | 135 | 1 |
| 7002 | 1 | 120 | 4 |

`line_no = 1` xuất hiện ở cả đơn 7001 và 7002, nên nó không duy nhất toàn cục. Nhưng cặp `(order_id, line_no)` không lặp, do đó xác định được một dòng hàng.

### 4.1. Khi nào khóa ghép phù hợp?

Khóa ghép phù hợp khi danh tính của một bản ghi thực sự được xác định bởi nhiều thành phần trong cùng một phạm vi. Ví dụ:

- `(order_id, line_no)`: dòng hàng trong một đơn.
- `(student_id, course_id, term_id)`: một lần đăng ký môn học của sinh viên trong một học kỳ.
- `(building_id, room_code)`: phòng trong một tòa nhà.
- `(tenant_id, username_normalized)`: tên người dùng trong một tenant.
- `(product_id, warehouse_id)`: số liệu tồn kho của một sản phẩm tại một kho.

Trong các ví dụ này, thành phần đầu tiên hoặc một số thành phần xác định ngữ cảnh; thành phần còn lại xác định đối tượng bên trong ngữ cảnh đó.

### 4.2. Ưu điểm và chi phí của khóa ghép

Ưu điểm:

- Diễn đạt trực tiếp quy tắc định danh của nghiệp vụ.
- Có thể loại bỏ một cột ID kỹ thuật nếu tổ hợp tự nhiên đã ổn định.
- Làm rõ quan hệ phụ thuộc vào bản ghi cha hoặc ngữ cảnh.
- Hỗ trợ bảo vệ tính duy nhất bằng constraint ngay tại cơ sở dữ liệu.

Chi phí cần cân nhắc:

- Khóa ngoại tham chiếu phải mang đủ các thành phần của khóa ghép.
- Các truy vấn và API có thể phải truyền nhiều giá trị.
- Chỉ mục trên khóa ghép có kích thước lớn hơn khóa đơn nếu chứa nhiều cột hoặc cột dài.
- Thay đổi một thành phần của khóa có thể ảnh hưởng đến nhiều quan hệ tham chiếu.
- Thứ tự cột trong chỉ mục ghép ảnh hưởng đến các mẫu truy vấn có thể tận dụng chỉ mục.

Không phải khóa ghép nào cũng xấu. Vấn đề là nó phải phản ánh đúng quy tắc nghiệp vụ và có chi phí phù hợp với cách hệ thống truy cập dữ liệu.

### 4.3. Khóa ghép trong quan hệ nhiều-nhiều

Một bảng liên kết thường có khóa ghép gồm hai khóa ngoại:

```sql
CREATE TABLE student_course (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES student(student_id),
    FOREIGN KEY (course_id) REFERENCES course(course_id)
);
```

Khóa ghép đảm bảo một sinh viên không có hai bản ghi đăng ký cho cùng một khóa học theo quy tắc trong ví dụ này.

Nếu nghiệp vụ cho phép đăng ký lại cùng một môn ở nhiều học kỳ, khóa hiện tại không còn đủ. Cần bổ sung thành phần ngữ cảnh, ví dụ:

```sql
PRIMARY KEY (student_id, course_id, term_id)
```

Đây là điểm quan trọng: khóa phải mô tả đúng định danh của sự kiện nghiệp vụ. Khi quy tắc thay đổi, candidate key cũng có thể thay đổi.

## 5. Phạm vi duy nhất theo ngữ cảnh

### 5.1. Duy nhất toàn cục và duy nhất trong phạm vi

Một giá trị có thể duy nhất trong toàn bộ hệ thống hoặc chỉ trong một nhóm bản ghi.

Ví dụ:

| Giá trị | Phạm vi duy nhất | Giải thích |
|---|---|---|
| `order_id` | Toàn hệ thống | Mỗi đơn có một mã riêng |
| `room_code` | Trong một tòa nhà | Hai tòa nhà khác nhau có thể cùng có phòng A101 |
| `username` | Trong một tenant | Hai tổ chức có thể dùng cùng tên đăng nhập |
| `line_no` | Trong một đơn hàng | Nhiều đơn có thể có dòng số 1 |
| `sku` | Theo nhà cung cấp hoặc cửa hàng | Phụ thuộc cách nghiệp vụ cấp mã sản phẩm |

Một quy tắc duy nhất phải luôn trả lời câu hỏi: **duy nhất trong phạm vi nào?** Nếu không ghi rõ phạm vi, nhóm thiết kế dễ chọn nhầm khóa hoặc constraint.

### 5.2. Duy nhất theo tenant

Trong hệ thống nhiều tenant, cùng một tên đăng nhập có thể được dùng ở các tổ chức khác nhau. Nếu mỗi tenant quản lý không gian tên riêng, cần dùng tổ hợp `(tenant_id, username_normalized)`:

```sql
CREATE TABLE app_user (
    user_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    username_normalized VARCHAR(100) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    CONSTRAINT uq_user_tenant_username
        UNIQUE (tenant_id, username_normalized)
);
```

Dữ liệu hợp lệ có thể như sau:

| tenant_id | username_normalized | user_id |
|---:|---|---:|
| 10 | an.nguyen | 1001 |
| 10 | binh.tran | 1002 |
| 20 | an.nguyen | 2001 |

Hai tenant có thể có người dùng tên `an.nguyen`, nhưng trong cùng một tenant không được trùng.

Nếu username phải duy nhất toàn hệ thống, constraint phải là `UNIQUE (username_normalized)` thay vì thêm `tenant_id`. Đây là quyết định nghiệp vụ, không nên tự suy ra từ cấu trúc hệ thống.

### 5.3. Duy nhất theo bản ghi cha

Một số mã chỉ có ý nghĩa trong một đối tượng cha. Ví dụ mã phòng trong tòa nhà hoặc số dòng trong đơn hàng. Khi đó, khóa ghép hoặc unique constraint gồm khóa cha và mã cục bộ:

```sql
CREATE TABLE building_room (
    building_id BIGINT NOT NULL,
    room_code VARCHAR(20) NOT NULL,
    floor_no INTEGER,
    PRIMARY KEY (building_id, room_code)
);
```

Nếu muốn có ID thay thế cho phòng để tham chiếu từ nhiều bảng, có thể kết hợp khóa thay thế với unique constraint theo phạm vi:

```sql
CREATE TABLE building_room (
    room_id BIGINT PRIMARY KEY,
    building_id BIGINT NOT NULL,
    room_code VARCHAR(20) NOT NULL,
    CONSTRAINT uq_room_code_per_building
        UNIQUE (building_id, room_code)
);
```

Cách thứ hai tách định danh kỹ thuật `room_id` khỏi quy tắc nghiệp vụ rằng mã phòng chỉ duy nhất trong tòa nhà. Cả hai cách đều có thể đúng; lựa chọn tùy thuộc độ ổn định của khóa tự nhiên, số quan hệ tham chiếu và nhu cầu API.

### 5.4. Duy nhất theo nhiều chiều ngữ cảnh

Phạm vi có thể gồm nhiều thành phần. Ví dụ, mã kệ hàng chỉ duy nhất trong kho thuộc một chi nhánh:

```sql
UNIQUE (branch_id, warehouse_id, shelf_code)
```

Trước khi thêm constraint, hãy xác định mỗi thành phần có thực sự cần thiết hay không. Nếu `warehouse_id` đã duy nhất toàn cục và xác định duy nhất `branch_id`, việc thêm cả `branch_id` có thể dư thừa. Tuy nhiên, nếu hệ thống yêu cầu khóa ghép để kiểm tra tenant boundary hoặc khóa ngoại ghép, tổ hợp có thể vẫn có vai trò riêng.

Không nên thêm cột vào unique key chỉ vì chúng xuất hiện trong truy vấn. Unique constraint diễn đạt quy tắc dữ liệu; chỉ mục truy vấn có thể được thiết kế riêng theo workload.

## 6. Phạm vi duy nhất có điều kiện và theo thời gian

### 6.1. Chỉ yêu cầu duy nhất với bản ghi đang hoạt động

Một số nghiệp vụ cho phép tái sử dụng mã sau khi bản ghi cũ đã bị xóa mềm hoặc ngừng hoạt động. Ví dụ, một tài khoản đã đóng có thể giải phóng tên đăng nhập để cấp cho tài khoản mới, nếu chính sách cho phép.

Nếu muốn tên đăng nhập chỉ duy nhất trong các bản ghi chưa bị xóa, có thể dùng partial unique index trong PostgreSQL:

```sql
CREATE UNIQUE INDEX uq_active_user_name
ON app_user (tenant_id, username_normalized)
WHERE deleted_at IS NULL;
```

Chỉ mục này chỉ áp dụng cho các hàng có `deleted_at IS NULL`. Nhiều hệ quản trị có cơ chế tương tự nhưng cú pháp và khả năng hỗ trợ khác nhau; cần kiểm tra theo engine đang dùng.

Nếu quy tắc yêu cầu tên đã đóng vẫn bị giữ chỗ, partial unique index trên không phù hợp. Khi đó cần constraint duy nhất không điều kiện hoặc mô hình hóa trạng thái cấp phát riêng.

### 6.2. Duy nhất theo thời gian hiệu lực

Một phòng họp có thể được đặt nhiều lần, miễn là các khoảng thời gian không chồng lấn. Đây không phải quy tắc unique đơn giản trên `(room_id, start_time)`, vì hai cuộc đặt có thể có thời điểm bắt đầu khác nhau nhưng vẫn trùng một phần thời gian.

Quy tắc cần diễn đạt là: với cùng một phòng, không được tồn tại hai khoảng thời gian hiệu lực giao nhau.

Trong PostgreSQL có thể sử dụng range type và exclusion constraint. Ví dụ minh họa:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_booking (
    booking_id BIGINT PRIMARY KEY,
    room_id BIGINT NOT NULL,
    during TSTZRANGE NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    )
);
```

Toán tử `&&` kiểm tra hai khoảng có giao nhau hay không. Exclusion constraint ngăn hai bản ghi có cùng `room_id` và khoảng thời gian giao nhau. Đây là cú pháp đặc thù PostgreSQL; với hệ quản trị khác, cần cơ chế tương đương như constraint chuyên biệt, transaction locking hoặc kiểm tra có kiểm soát để tránh hai yêu cầu đồng thời cùng đặt một khoảng trống.

Ví dụ này cho thấy phạm vi duy nhất có thể là một điều kiện trên nhiều chiều, không chỉ là so sánh bằng trên một vài cột.

### 6.3. Chuẩn hóa giá trị trước khi so sánh duy nhất

Hai chuỗi có thể nhìn giống nhau nhưng khác biểu diễn. Ví dụ email có thể khác chữ hoa/thường, tên người dùng có thể chứa khoảng trắng ở đầu/cuối, mã sản phẩm có thể có quy tắc chữ hoa/thường riêng.

Trước khi xác định unique constraint, cần thống nhất:

- Có loại bỏ khoảng trắng đầu/cuối không?
- Có chuẩn hóa Unicode không?
- Có phân biệt chữ hoa/thường không?
- Có loại bỏ dấu phân cách hoặc ký tự định dạng không?
- Có so sánh theo collation/ngôn ngữ cụ thể không?

Một cách thường dùng là lưu giá trị gốc để hiển thị và một giá trị chuẩn hóa để tra cứu, ví dụ `email_normalized`. Quy tắc chuẩn hóa phải được xác định nhất quán ở mọi luồng ghi. Nếu chỉ chuẩn hóa ở một API mà bỏ qua luồng nhập dữ liệu khác, bản ghi trùng vẫn có thể lọt vào.

Không nên tự ý chuyển mọi trường sang chữ thường hoặc loại bỏ dấu. Cần dựa trên quy tắc nghiệp vụ và semantics của từng loại mã.

## 7. Chọn khóa chính và ràng buộc unique

### 7.1. Khi nào chọn khóa đơn, khi nào chọn khóa ghép?

| Điều kiện | Khóa đơn | Khóa ghép |
|---|---|---|
| Một thuộc tính ổn định đủ nhận diện | Phù hợp | Không cần thêm thành phần |
| Danh tính phụ thuộc ngữ cảnh | Có thể dùng ID thay thế và unique theo ngữ cảnh | Diễn đạt trực tiếp phạm vi định danh |
| Bảng liên kết có khóa tự nhiên gồm nhiều FK | Có thể thêm ID thay thế | Thường phù hợp với candidate key nghiệp vụ |
| Nhiều bảng tham chiếu bản ghi | Khóa đơn thường đơn giản hơn | Khóa ngoại phải mang đủ thành phần |
| Khóa tự nhiên có thể thay đổi | ID thay thế thường ổn định hơn | Cần cân nhắc chi phí cập nhật quan hệ |
| Quy tắc nghiệp vụ cần duy nhất trong một nhóm | Cần unique constraint bổ sung | Có thể dùng tổ hợp làm khóa |

Không có lựa chọn đúng cho mọi trường hợp. Một thiết kế có thể dùng khóa thay thế đơn làm primary key và dùng unique constraint ghép để bảo vệ quy tắc nghiệp vụ.

Ví dụ:

```sql
CREATE TABLE inventory_balance (
    balance_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity DECIMAL(18, 3) NOT NULL,
    CONSTRAINT uq_inventory_scope
        UNIQUE (tenant_id, warehouse_id, product_id)
);
```

`balance_id` giúp các bảng khác tham chiếu bằng một giá trị đơn. Constraint ghép bảo đảm chỉ có một số dư cho mỗi tổ hợp tenant, kho và sản phẩm.

### 7.2. Ràng buộc duy nhất phải nằm ở nơi bảo vệ dữ liệu

Kiểm tra trùng ở giao diện hoặc trong code ứng dụng là chưa đủ. Hai yêu cầu đồng thời có thể cùng kiểm tra rằng email chưa tồn tại rồi cùng tạo bản ghi. Nếu không có unique constraint, cả hai có thể ghi thành công và tạo dữ liệu trùng.

Cơ sở dữ liệu cần là lớp bảo vệ cuối cùng cho quy tắc duy nhất:

```sql
ALTER TABLE app_user
ADD CONSTRAINT uq_user_tenant_email
UNIQUE (tenant_id, email_normalized);
```

Ứng dụng vẫn có thể kiểm tra trước để hiển thị thông báo thân thiện, nhưng cần xử lý lỗi vi phạm unique constraint khi ghi. Với thao tác tạo đồng thời, constraint giúp đảm bảo chỉ một giao dịch có thể lưu giá trị trùng trong cùng phạm vi.

### 7.3. Unique constraint, unique index và NULL

Nhiều hệ quản trị triển khai unique constraint bằng một unique index, nhưng hai khái niệm không hoàn toàn đồng nhất trong mọi engine. Constraint diễn đạt quy tắc toàn vẹn; index là cấu trúc hỗ trợ kiểm tra và truy vấn.

Cần đặc biệt lưu ý cách hệ quản trị xử lý `NULL` trong unique constraint. Nhiều hệ quản trị mặc định cho phép nhiều hàng có `NULL` trong một cột unique vì `NULL` không được xem như một giá trị bằng nhau; một số hệ quản trị hoặc tùy chọn có semantics khác. Với khóa định danh và phạm vi duy nhất bắt buộc, nên khai báo các thành phần là `NOT NULL` để tránh lỗ hổng do giá trị thiếu.

Ví dụ:

```sql
CREATE TABLE tenant_user (
    tenant_id BIGINT NOT NULL,
    username VARCHAR(100) NOT NULL,
    CONSTRAINT uq_tenant_username UNIQUE (tenant_id, username)
);
```

Nếu `tenant_id` hoặc `username` được phép NULL, cần đọc rõ semantics của hệ quản trị và quyết định liệu bản ghi thiếu giá trị có được phép tồn tại hay không.

## 8. Khóa ghép và khóa ngoại

Khi một bảng tham chiếu đến bản ghi có khóa ghép, khóa ngoại phải tham chiếu đầy đủ các cột tạo nên khóa đó.

Ví dụ, nếu `project` được nhận diện bởi `(tenant_id, project_code)`, bảng `task` phải mang cả hai thành phần khi tham chiếu:

```sql
CREATE TABLE project (
    tenant_id BIGINT NOT NULL,
    project_code VARCHAR(30) NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, project_code)
);

CREATE TABLE task (
    tenant_id BIGINT NOT NULL,
    project_code VARCHAR(30) NOT NULL,
    task_no INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, project_code, task_no),
    FOREIGN KEY (tenant_id, project_code)
        REFERENCES project (tenant_id, project_code)
);
```

Cách thiết kế này bảo đảm một task tham chiếu đến đúng project trong cùng tenant. Nếu chỉ tham chiếu `project_code` mà mã này chỉ duy nhất trong tenant, quan hệ có thể trỏ nhầm hoặc không thể được cơ sở dữ liệu bảo vệ đầy đủ.

Nếu muốn khóa ngoại đơn giản hơn, có thể dùng `project_id` làm khóa thay thế toàn cục, đồng thời giữ unique constraint `(tenant_id, project_code)` để bảo vệ mã dự án trong phạm vi tenant. Khi đó, cần cân nhắc liệu các quan hệ có yêu cầu kiểm tra tenant boundary hay không. Trong một số thiết kế nhiều tenant, khóa ngoại ghép có thể giúp ngăn liên kết chéo tenant ngay tại cơ sở dữ liệu.

## 9. Quy trình xác định khóa và phạm vi duy nhất

Thực hiện theo thứ tự sau cho từng thực thể hoặc nhóm dữ liệu:

1. **Xác định điều cần nhận diện:** bản ghi là khách hàng, đơn hàng, dòng hàng, lượt đăng ký hay một phiên bản có thời hạn?
2. **Liệt kê thuộc tính ứng viên:** tìm các mã nghiệp vụ, định danh hệ thống và tổ hợp thuộc tính có thể nhận diện.
3. **Xác minh tính duy nhất:** kiểm tra quy tắc nghiệp vụ, dữ liệu hiện có và các nguồn cấp mã.
4. **Xác minh tính tối thiểu:** thử bỏ từng thuộc tính khỏi tổ hợp; nếu vẫn duy nhất thì tổ hợp ban đầu chưa phải candidate key.
5. **Xác định phạm vi:** toàn hệ thống, theo tenant, theo tổ chức, theo bản ghi cha, theo thời gian hay theo trạng thái.
6. **Xác định tính ổn định:** giá trị có thể đổi, bị tái sử dụng hoặc bị chuẩn hóa lại không?
7. **Chọn primary key:** chọn một candidate key phù hợp với vòng đời và quan hệ tham chiếu; giữ các candidate key khác bằng unique constraint.
8. **Thiết kế khóa ngoại:** bảo đảm bảng con mang đủ thành phần cần thiết để tham chiếu đúng bản ghi cha.
9. **Đặt constraint ở cơ sở dữ liệu:** dùng PRIMARY KEY, UNIQUE, NOT NULL hoặc cơ chế phù hợp với quy tắc có điều kiện.
10. **Kiểm tra tình huống đồng thời và biên:** hai yêu cầu tạo cùng mã, giá trị NULL, đổi tenant, xóa mềm, tái sử dụng mã và thay đổi phạm vi.

Mỗi quyết định nên được ghi cùng lý do. Nếu một mã chỉ duy nhất trong chi nhánh, tài liệu cần nêu rõ chi nhánh là phạm vi và ai chịu trách nhiệm cấp mã.

## 10. Những sai lầm thường gặp

- Chọn khóa dựa trên một giá trị đang tình cờ không trùng trong dữ liệu mẫu mà chưa xác nhận quy tắc nghiệp vụ.
- Dùng email hoặc số điện thoại làm khóa chính dù chúng có thể thay đổi hoặc được tái sử dụng.
- Thêm ID thay thế nhưng quên unique constraint trên khóa nghiệp vụ.
- Dùng khóa ghép nhưng không kiểm tra từng thành phần có thực sự cần thiết.
- Coi một mã cục bộ là duy nhất toàn hệ thống, dẫn đến từ chối dữ liệu hợp lệ từ tenant hoặc tổ chức khác.
- Thiếu một thành phần phạm vi trong khóa ngoại, gây liên kết sai ngữ cảnh.
- Kiểm tra trùng ở ứng dụng nhưng không có constraint ở cơ sở dữ liệu.
- Bỏ qua NULL, collation, chữ hoa/thường và quy tắc chuẩn hóa.
- Dùng unique constraint đơn giản cho quy tắc duy nhất có điều kiện hoặc không chồng lấn theo thời gian.
- Cho phép tái sử dụng mã nhưng không xác định cách xử lý lịch sử, liên kết cũ và bản ghi đã xóa mềm.
- Thêm các cột vào unique constraint chỉ để phục vụ một truy vấn, làm thay đổi ý nghĩa của quy tắc dữ liệu.

## 11. Checklist kiểm chứng khóa và phạm vi duy nhất

Trước khi hoàn tất mô hình, hãy xác nhận:

- [ ] Mỗi thực thể có cách nhận diện rõ ràng.
- [ ] Candidate key là tập thuộc tính tối thiểu nhưng vẫn duy nhất.
- [ ] Primary key được chọn có lý do và ổn định trong vòng đời bản ghi.
- [ ] Các candidate key còn lại được bảo vệ bằng unique constraint phù hợp.
- [ ] Khóa ghép phản ánh đúng ngữ cảnh định danh và không chứa thuộc tính dư thừa.
- [ ] Phạm vi duy nhất được ghi rõ: toàn cục, tenant, cha-con, thời gian hoặc trạng thái.
- [ ] Các thành phần bắt buộc của khóa được khai báo NOT NULL.
- [ ] Quy tắc chuẩn hóa và so sánh chuỗi được xác định nhất quán.
- [ ] Khóa ngoại ghép tham chiếu đủ các cột của khóa đích.
- [ ] Các tình huống đồng thời không thể tạo dữ liệu trùng.
- [ ] Quy tắc xóa mềm, tái sử dụng mã và lưu lịch sử đã được xác định.
- [ ] Cú pháp và semantics của constraint đã được kiểm tra theo hệ quản trị mục tiêu.

Khóa đơn, khóa ghép và phạm vi duy nhất đều là cách diễn đạt danh tính dữ liệu. Khi phạm vi được xác định đúng, mô hình vừa cho phép các mã hợp lệ được lặp lại ở những ngữ cảnh khác nhau, vừa ngăn trùng lặp trong đúng phạm vi nghiệp vụ cần bảo vệ.

