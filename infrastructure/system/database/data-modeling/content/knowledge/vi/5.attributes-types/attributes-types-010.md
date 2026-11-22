# Nhóm thuộc tính lặp lại và dấu hiệu cần tách thành cấu trúc riêng

Trong module **DATABASE_DATA_MODELING**, một mô hình dữ liệu tốt phải phản ánh đúng đối tượng nghiệp vụ, các quy tắc và cách dữ liệu được sử dụng. Khi phân tích thuộc tính, đôi khi ta phát hiện một thực thể có nhiều nhóm thông tin cùng loại: một khách hàng có nhiều số liên hệ, một đơn hàng có nhiều dòng hàng, một nhân viên có nhiều chứng chỉ hoặc một sản phẩm có nhiều biến thể. Đây là lúc cần nhận diện **nhóm thuộc tính lặp lại** và quyết định có nên tách chúng thành cấu trúc riêng.

Nếu mô hình giữ các nhóm lặp thành những cột cố định như `phone_1`, `phone_2`, `phone_3`, số lượng bị giới hạn bởi thiết kế và mỗi lần mở rộng phải sửa lược đồ. Nếu nhét cả danh sách vào một chuỗi hoặc một trường JSON mà không xem xét quy tắc, việc tìm kiếm, xác thực và cập nhật từng phần tử có thể trở nên khó khăn. Ngược lại, tách mọi nhóm nhỏ thành bảng riêng cũng làm mô hình phức tạp và tăng chi phí truy vấn. Cần quyết định dựa trên số lượng phần tử, ý nghĩa của từng phần tử, vòng đời, quan hệ và workload.

## 1. Nhóm thuộc tính lặp lại là gì?

**Nhóm thuộc tính lặp lại (repeating group)** là một tập thuộc tính có cấu trúc giống nhau có thể xuất hiện nhiều lần đối với cùng một thực thể hoặc cùng một đối tượng nghiệp vụ.

Ví dụ, một hồ sơ nhân viên có thể chứa các nhóm:

- Chứng chỉ: tên chứng chỉ, đơn vị cấp, ngày cấp, ngày hết hạn.
- Số liên hệ: loại liên hệ, giá trị, nhãn, trạng thái xác minh.
- Lịch sử công tác: tổ chức, chức danh, ngày bắt đầu, ngày kết thúc.
- Kỹ năng: tên kỹ năng, mức độ, thời gian kinh nghiệm.

Mỗi lần xuất hiện của nhóm có cùng hình dạng nhưng giá trị khác nhau. Một nhân viên có thể có hai chứng chỉ, ba số liên hệ hoặc nhiều giai đoạn công tác.

~~~mermaid
flowchart TD
    E["Nhân viên"] --> G["Nhóm chứng chỉ lặp lại"]
    G --> C1["Chứng chỉ 1"]
    G --> C2["Chứng chỉ 2"]
    G --> C3["Chứng chỉ 3"]
    C1 --> A1["Tên / Đơn vị cấp / Ngày cấp / Hết hạn"]
    C2 --> A2["Tên / Đơn vị cấp / Ngày cấp / Hết hạn"]
    C3 --> A3["Tên / Đơn vị cấp / Ngày cấp / Hết hạn"]
~~~

Điểm quan trọng là mỗi lần lặp có cùng cấu trúc thuộc tính. Nếu một khách hàng có cả địa chỉ thanh toán và địa chỉ giao hàng, đó chưa chắc là nhóm lặp. Hai địa chỉ có thể mang vai trò nghiệp vụ khác nhau, có quy tắc riêng và số lượng cố định. Nếu khách hàng có thể lưu tùy ý nhiều địa chỉ với cùng cấu trúc, đó mới là một tập phần tử lặp.

### Nhận diện qua cấu trúc dữ liệu

Các dấu hiệu thường gặp trong yêu cầu, bảng tính, biểu mẫu hoặc lược đồ cũ:

- Các cột có hậu tố số: `phone_1`, `phone_2`, `phone_3`.
- Các cặp cột lặp theo mẫu: `certificate_name_1`, `certificate_issuer_1`, `certificate_name_2`, `certificate_issuer_2`.
- Các trường như `item1`, `item2`, `item3` hoặc `address_a`, `address_b`.
- Một trường chứa danh sách phân cách bằng dấu phẩy, dấu chấm phẩy hoặc ký tự tùy chọn.
- Một nhóm thông tin có thể được thêm nhiều lần trong giao diện, nhưng cơ sở dữ liệu chỉ có vài cột cố định.
- Logic ứng dụng lặp lại các nhánh điều kiện theo từng vị trí: xử lý số điện thoại thứ nhất, thứ hai, thứ ba.

Tên cột lặp là dấu hiệu để điều tra, không phải bằng chứng duy nhất rằng phải tách bảng. Hãy xác nhận quy tắc nghiệp vụ: số lượng có cố định không, mỗi phần tử có cùng cấu trúc không và người dùng có cần thao tác độc lập trên từng phần tử không.

## 2. Phân biệt nhóm lặp với các cấu trúc gần giống

Một số cấu trúc trông giống nhau nhưng có ý nghĩa khác nhau.

| Cấu trúc | Bản chất | Ví dụ |
|---|---|---|
| Thuộc tính phức hợp | Một giá trị gồm nhiều thành phần | Một địa chỉ gồm đường, thành phố và quốc gia |
| Thuộc tính nhiều giá trị đơn | Một thực thể có nhiều giá trị cùng loại | Một khách hàng có nhiều số điện thoại |
| Nhóm thuộc tính lặp lại | Một thực thể có nhiều lần xuất hiện của cùng một nhóm trường | Một nhân viên có nhiều chứng chỉ, mỗi chứng chỉ có tên, nơi cấp và ngày hết hạn |
| Hai vai trò cố định | Các thuộc tính khác nhau theo vai trò, số lượng được định nghĩa rõ | Địa chỉ thanh toán và địa chỉ giao hàng trên một đơn |
| Quan hệ nhiều-nhiều | Nhiều thực thể ở hai phía có thể liên kết với nhau | Sinh viên đăng ký nhiều học phần và mỗi học phần có nhiều sinh viên |

Một nhóm lặp thường có thể được mô hình hóa thành một thực thể con, một đối tượng giá trị con hoặc một collection. Không nên mặc định mọi nhóm lặp đều là thực thể độc lập; việc tách cấu trúc là quyết định về cách biểu diễn và trách nhiệm dữ liệu.

### Ví dụ: địa chỉ giao hàng và địa chỉ thanh toán

Nếu nghiệp vụ luôn có đúng hai vai trò, mỗi vai trò có quy tắc riêng, mô hình có thể biểu diễn thành hai thuộc tính phức hợp:

- `billing_address`: địa chỉ dùng cho hóa đơn.
- `shipping_address`: địa chỉ dùng để giao hàng.

Nếu khách hàng có thể lưu nhiều địa chỉ và gán từng địa chỉ vào các mục đích khác nhau, nên cân nhắc một tập địa chỉ có trường loại hoặc bảng liên kết vai trò. Cấu trúc sau linh hoạt hơn khi một địa chỉ có thể vừa là địa chỉ giao hàng vừa là địa chỉ thanh toán.

## 3. Vì sao cột lặp và danh sách nhúng có thể gây vấn đề?

### Cột lặp cố định

Giả sử bảng nhân viên có các cột:

~~~sql
CREATE TABLE employee_legacy (
    employee_id BIGINT PRIMARY KEY,
    certificate_name_1 VARCHAR(200),
    certificate_issuer_1 VARCHAR(200),
    certificate_expiry_1 DATE,
    certificate_name_2 VARCHAR(200),
    certificate_issuer_2 VARCHAR(200),
    certificate_expiry_2 DATE,
    certificate_name_3 VARCHAR(200),
    certificate_issuer_3 VARCHAR(200),
    certificate_expiry_3 DATE
);
~~~

Thiết kế này có một số hạn chế:

- Số chứng chỉ tối đa bị cố định bởi số nhóm cột.
- Khi cần thêm nhóm thứ tư, phải thay đổi lược đồ và ứng dụng.
- Nhiều cột có thể NULL, gây khó hiểu liệu chưa có chứng chỉ hay chưa thu thập thông tin.
- Truy vấn, sắp xếp và lọc trên mọi vị trí phải lặp điều kiện.
- Không dễ gắn trạng thái xác minh, tệp đính kèm hoặc lịch sử cho từng chứng chỉ.
- Ràng buộc duy nhất cho tên chứng chỉ hoặc mã chứng chỉ khó áp dụng nhất quán trên các vị trí.

### Danh sách phân cách trong một cột

Ví dụ lưu `certificates = "AWS,Oracle,Java"` hoặc `phones = "090...,091..."` có thể nhìn đơn giản nhưng gây ra các vấn đề:

- Không thể dùng khóa ngoại để tham chiếu từng phần tử.
- Khó bảo vệ tính duy nhất và miền giá trị của từng phần tử.
- Khó cập nhật hoặc xóa đúng một giá trị.
- Tìm kiếm có thể nhầm một giá trị là phần của giá trị khác.
- Không thể gắn metadata riêng cho từng phần tử một cách rõ ràng.
- Phải tự định nghĩa cách escape dấu phân cách, khoảng trắng và ký tự đặc biệt.

### Khi danh sách JSON vẫn có thể phù hợp

Document hoặc JSON array có thể là lựa chọn tốt nếu nhóm giá trị được đọc và cập nhật cùng một aggregate, cấu trúc thay đổi linh hoạt và không cần quan hệ tham chiếu hay ràng buộc mạnh trên từng phần tử. Tuy nhiên, phải xem xét kích thước, tần suất cập nhật, cách truy vấn và khả năng xác thực từng phần tử. JSON không tự loại bỏ nhu cầu định nghĩa schema và quy tắc dữ liệu.

## 4. Dấu hiệu cần tách nhóm lặp thành cấu trúc riêng

Không có một tiêu chí đơn lẻ quyết định mọi trường hợp. Các dấu hiệu sau cho thấy nên xem xét tách nhóm lặp.

### Số lượng phần tử không cố định

Nếu số phần tử có thể tăng hoặc giảm theo nghiệp vụ, cấu trúc cột cố định không phản ánh tự nhiên cardinality. Ví dụ, một đơn hàng có thể có một đến hàng trăm dòng hàng; không nên tạo `item_1` đến `item_100`.

### Mỗi phần tử có thuộc tính riêng

Nếu từng phần tử có ngày tạo, trạng thái, loại, người xác minh, mức ưu tiên hoặc ghi chú riêng, phần tử đã có cấu trúc riêng. Tách thành bản ghi con giúp ràng buộc và cập nhật chính xác hơn.

### Cần truy vấn hoặc cập nhật từng phần tử

Nếu người dùng cần tìm nhân viên có chứng chỉ còn hiệu lực, xóa một số liên hệ, sửa ngày hết hạn của một chứng chỉ hoặc thống kê số phần tử theo loại, cấu trúc riêng hỗ trợ tốt hơn.

### Có quy tắc toàn vẹn trên tập phần tử

Ví dụ:

- Không được có hai chứng chỉ trùng số hiệu trong cùng một nhân viên.
- Mỗi khách hàng chỉ có tối đa một số điện thoại chính đang hoạt động.
- Một dòng đơn hàng phải có số lượng dương.
- Một nhân viên không được có hai giai đoạn công tác chồng lấn nếu chính sách cấm.
- Tổng tỷ lệ phân bổ của các thành phần phải bằng 100%.

Những quy tắc này thường khó thể hiện bằng các cột lặp hoặc chuỗi danh sách.

### Phần tử có vòng đời hoặc quan hệ riêng

Nếu một chứng chỉ có thể được xác minh, thu hồi, đính kèm tài liệu, được tham chiếu bởi hồ sơ năng lực hoặc có lịch sử trạng thái, nó có thể cần danh tính riêng. Khi đó, mô hình hóa thành thực thể con là hợp lý.

### Cần giữ lịch sử

Nếu mỗi lần thay đổi phần tử cần lưu thời điểm hiệu lực, người sửa hoặc trạng thái trước đó, cấu trúc con cho phép quản lý lịch sử rõ ràng. Không nên ghi đè một giá trị cũ nếu nghiệp vụ cần truy vết.

## 5. Chọn cấu trúc riêng: thực thể con hay đối tượng giá trị?

Sau khi quyết định không giữ nhóm lặp trong các cột cố định, cần chọn mức cấu trúc phù hợp.

| Câu hỏi | Đối tượng giá trị con | Thực thể con |
|---|---|---|
| Có danh tính độc lập không? | Thường không | Có |
| Có vòng đời riêng không? | Thường gắn với chủ thể | Có thể độc lập trong phạm vi chủ thể |
| Có được tham chiếu từ nơi khác không? | Thường không | Có thể |
| Có metadata riêng không? | Có thể có, nhưng phụ thuộc chủ thể | Thường có |
| Xóa chủ thể cha | Thường xóa cùng | Phụ thuộc quy tắc sở hữu và lưu trữ |
| Ví dụ | Một địa chỉ snapshot trong đơn | Chứng chỉ được xác minh và tham chiếu từ nhiều hồ sơ |

**Đối tượng giá trị con** phù hợp khi phần tử chỉ có ý nghĩa trong ngữ cảnh của chủ thể, được tạo và xóa cùng chủ thể, và không cần tham chiếu độc lập. Ví dụ, các dòng hàng của một đơn có thể là thành phần thuộc aggregate đơn hàng; số dòng được nhận diện bằng số thứ tự trong đơn.

**Thực thể con** phù hợp khi phần tử có danh tính riêng, được quản lý độc lập hoặc được tham chiếu từ nhiều nơi. Ví dụ, một chứng chỉ đã xác minh có thể được liên kết với hồ sơ nhân viên, hồ sơ năng lực và quy trình kiểm toán.

Có thể bắt đầu bằng đối tượng giá trị và nâng lên thành thực thể khi yêu cầu về vòng đời, tham chiếu hoặc lịch sử xuất hiện. Điều quan trọng là phải giữ được ý nghĩa nghiệp vụ và có kế hoạch chuyển đổi nếu cấu trúc đã được sử dụng.

## 6. Mô hình hóa nhóm lặp trong cơ sở dữ liệu quan hệ

Trong mô hình quan hệ, một nhóm lặp thường được tách thành bảng con. Bảng con chứa khóa ngoại về thực thể cha và các cột mô tả một lần xuất hiện của nhóm.

Thay vì dành sẵn các vị trí như `certificate_1`, `certificate_2`, `certificate_3`, mỗi lần xuất hiện được lưu thành một hàng trong bảng con. Cách này biểu diễn số lượng phần tử bằng số hàng, cho phép thêm phần tử mà không phải thay đổi lược đồ mỗi khi nhu cầu tăng. Các cột trong một hàng vẫn mô tả một phần tử cụ thể của nhóm.

### Ví dụ: nhân viên có nhiều chứng chỉ

~~~mermaid
erDiagram
    EMPLOYEE ||--o{ EMPLOYEE_CERTIFICATE : holds
    EMPLOYEE {
        bigint employee_id PK
        string employee_name
    }
    EMPLOYEE_CERTIFICATE {
        bigint certificate_id PK
        bigint employee_id FK
        string certificate_code
        string certificate_name
        string issuer
        date issued_on
        date expires_on
        string status
    }
~~~

DDL minh họa:

~~~sql
CREATE TABLE employee (
    employee_id BIGINT PRIMARY KEY,
    employee_name VARCHAR(160) NOT NULL
);

CREATE TABLE employee_certificate (
    certificate_id BIGINT PRIMARY KEY,
    employee_id BIGINT NOT NULL,
    certificate_code VARCHAR(100) NOT NULL,
    certificate_name VARCHAR(200) NOT NULL,
    issuer VARCHAR(200) NOT NULL,
    issued_on DATE,
    expires_on DATE,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_certificate_employee
        FOREIGN KEY (employee_id) REFERENCES employee(employee_id),
    CONSTRAINT uq_employee_certificate_code
        UNIQUE (employee_id, certificate_code),
    CONSTRAINT ck_certificate_dates
        CHECK (expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on)
);
~~~

Mỗi hàng employee_certificate là một lần xuất hiện của nhóm thuộc tính chứng chỉ. Khóa ngoại xác định chủ thể sở hữu. Khóa thay thế certificate_id được dùng vì chứng chỉ có thể được xác minh hoặc tham chiếu độc lập; UNIQUE(employee_id, certificate_code) bảo vệ quy tắc mã chứng chỉ không lặp trong cùng hồ sơ theo giả định ví dụ.

Nếu chứng chỉ không có danh tính riêng và không được tham chiếu từ nơi khác, khóa ghép (employee_id, certificate_code) có thể đủ. Chọn khóa thay thế không loại bỏ các ràng buộc nghiệp vụ.

### Ví dụ: đơn hàng có nhiều dòng hàng

~~~mermaid
erDiagram
    CUSTOMER_ORDER ||--|{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : identifies
    CUSTOMER_ORDER {
        bigint order_id PK
        datetime placed_at
        string status
    }
    ORDER_LINE {
        bigint order_id PK, FK
        int line_no PK
        bigint product_id FK
        int quantity
        decimal unit_price_snapshot
    }
~~~

Ở đây, mỗi dòng hàng là một nhóm gồm sản phẩm, số lượng và giá tại thời điểm đặt. Dòng hàng thuộc về đơn hàng; số thứ tự dòng có ý nghĩa trong phạm vi đơn. Có thể dùng khóa ghép (order_id, line_no) nếu dòng không cần ID độc lập. Nếu các hệ thống khác phải tham chiếu từng dòng, có thể bổ sung line_id nhưng vẫn giữ ràng buộc UNIQUE(order_id, line_no).

Nếu cần DDL cho bảng dòng hàng, giả sử `customer_order` và `product` đã tồn tại, có thể dùng khóa ghép như sau:

~~~sql
CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_snapshot DECIMAL(12, 2) NOT NULL,
    CONSTRAINT pk_order_line PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id) REFERENCES customer_order(order_id),
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id) REFERENCES product(product_id),
    CONSTRAINT ck_line_quantity CHECK (quantity > 0),
    CONSTRAINT ck_line_price CHECK (unit_price_snapshot >= 0)
);
~~~

### Chỉ mục cho bảng con

Các truy vấn thường gặp có thể là:

- Lấy tất cả chứng chỉ của một nhân viên.
- Tìm nhân viên có một loại chứng chỉ hoặc chứng chỉ còn hiệu lực.
- Lấy các dòng hàng của một đơn.
- Tìm đơn hàng có chứa một sản phẩm.

Khóa chính hoặc chỉ mục bắt đầu bằng khóa ngoại thường hỗ trợ truy vấn theo chủ thể cha. Chỉ mục trên các thuộc tính lọc như status, expires_on hoặc product_id chỉ nên thêm khi workload cần. Mỗi chỉ mục tiêu tốn dung lượng và làm tăng chi phí ghi; cần kiểm tra bằng truy vấn và dữ liệu đại diện.

## 7. Mô hình hóa trong document, đồ thị và phân tích

Việc tách nhóm lặp thành cấu trúc riêng không nhất thiết có nghĩa phải tạo một bảng quan hệ riêng trong mọi họ mô hình.

| Họ mô hình | Cách biểu diễn nhóm lặp | Khi phù hợp |
|---|---|---|
| Quan hệ | Bảng con với FK; mỗi lần lặp là một hàng | Cần truy vấn từng phần tử, ràng buộc, nối hoặc cập nhật độc lập |
| Document | Array các object hoặc document con trong collection riêng | Các phần tử thường được đọc/ghi cùng aggregate hoặc cần vòng đời độc lập |
| Đồ thị | Nhiều edge hoặc node con liên kết với node cha | Phần tử có quan hệ nhiều bước, được chia sẻ hoặc tham chiếu |
| Phân tích | Bảng fact, dimension hoặc bridge ở grain xác định | Cần tổng hợp, phân tích lịch sử hoặc liên kết một bản ghi với nhiều giá trị |

### Document: nhúng hay tham chiếu?

Một hồ sơ nhân viên có thể chứa mảng chứng chỉ nếu số lượng vừa phải, chứng chỉ được đọc cùng hồ sơ và các cập nhật thường diễn ra trong cùng aggregate. Nếu chứng chỉ có tài liệu lớn, được nhiều hồ sơ tham chiếu hoặc cần truy vấn độc lập với khối lượng cao, collection riêng có thể phù hợp hơn.

~~~json
{
  "employeeId": "emp_102",
  "name": "Le Minh",
  "certificates": [
    {
      "code": "DB-2025-01",
      "name": "Database Fundamentals",
      "issuer": "Training Institute",
      "issuedOn": "2025-03-10",
      "expiresOn": "2028-03-10",
      "status": "VERIFIED"
    },
    {
      "code": "SEC-2024-09",
      "name": "Security Essentials",
      "issuer": "Professional Board",
      "issuedOn": "2024-08-01",
      "expiresOn": null,
      "status": "PENDING"
    }
  ]
}
~~~

Mảng certificates là nhóm lặp có cấu trúc. Mỗi phần tử có metadata riêng. Nếu cập nhật một phần tử phải bảo đảm tính nhất quán với hồ sơ cha, hãy xác định ranh giới aggregate và cơ chế cập nhật nguyên tử của hệ quản trị.

### Đồ thị: node hay edge?

Nếu một nhóm lặp chỉ là danh sách giá trị thuộc một thực thể, có thể biểu diễn bằng nhiều cạnh từ node cha đến các node con hoặc bằng thuộc tính trên edge. Nếu phần tử có danh tính riêng, có thể liên kết với nhiều node khác, tạo thành node riêng.

Ví dụ, kỹ năng của nhân viên có thể là node Skill dùng chung. Quan hệ HAS_SKILL có thể chứa mức độ, thời điểm đánh giá và người xác nhận. Khi đó, mức độ không phải thuộc tính chung của Skill mà là thuộc tính của quan hệ giữa một nhân viên và kỹ năng cụ thể.

~~~mermaid
flowchart LR
    E["Employee"] -->|HAS_SKILL| S1["Skill: SQL"]
    E -->|HAS_SKILL| S2["Skill: Data Modeling"]
    S1 --> M1["level: ADVANCED"]
    S2 --> M2["level: INTERMEDIATE"]
~~~

### Phân tích: chú ý grain và nhân bản số đo

Nếu mỗi nhân viên có nhiều chứng chỉ, một bảng bridge có thể liên kết employee dimension với certificate dimension. Trước khi nối bảng, cần xác định grain của fact. Nếu fact ở mức một nhân viên nhưng join với ba chứng chỉ, doanh thu hoặc số lượng của nhân viên có thể bị lặp ba lần.

Hãy quyết định báo cáo cần đếm số nhân viên, số chứng chỉ hay phân bổ số đo cho từng chứng chỉ. Không được mặc định phép join một-nhiều giữ nguyên tổng của bảng phía một.

## 8. Quy tắc nghiệp vụ của nhóm lặp

Khi tách nhóm lặp, phải mô tả các quy tắc liên quan đến toàn bộ tập phần tử và từng phần tử.

### Cardinality

Ghi số lượng tối thiểu và tối đa, ví dụ:

- Nhân viên có 0..N chứng chỉ.
- Đơn hàng nháp có thể có 0..N dòng; đơn đã xác nhận có 1..N dòng.
- Mỗi khách hàng có 0..N số liên hệ.
- Một tài khoản có đúng một định danh chính đang hoạt động nếu quy tắc yêu cầu.

Đừng đặt NOT NULL hoặc giới hạn tối đa trong lược đồ nếu nghiệp vụ chưa xác nhận. Quy tắc có thể phụ thuộc trạng thái hoặc thời điểm.

### Tính duy nhất

Cần xác định phần tử nào không được lặp:

- Mã chứng chỉ có duy nhất trong một nhân viên hay toàn tổ chức?
- Một số điện thoại có thể gắn với nhiều khách hàng không?
- Một sản phẩm có thể xuất hiện nhiều lần trong cùng đơn hàng hay phải gộp số lượng?
- Một nhân viên có thể có nhiều kỹ năng cùng tên nhưng khác cấp độ hoặc nguồn đánh giá không?

Phạm vi duy nhất thường là tổ hợp giữa khóa cha và thuộc tính của phần tử, nhưng phải dựa trên nghiệp vụ.

### Thứ tự

Một nhóm lặp có thứ tự khi vị trí mang ý nghĩa: các bước trong quy trình, ưu tiên địa chỉ, thứ tự dòng hiển thị hoặc các giai đoạn theo thời gian. Khi đó, cần lưu vị trí hoặc thời điểm. Nếu thứ tự không có ý nghĩa, không nên dựa vào thứ tự vật lý của hàng hoặc phần tử mảng.

### Hiệu lực và lịch sử

Một phần tử có thể đang hoạt động, hết hạn, bị thu hồi hoặc đã thay thế. Cần xác định liệu hệ thống lưu trạng thái hiện tại hay mọi phiên bản theo thời gian. Nếu lưu lịch sử, hãy định nghĩa ngày hiệu lực, ngày kết thúc, người thay đổi và quy tắc không chồng lấn nếu nghiệp vụ yêu cầu.

### Quy tắc trên toàn tập

Ví dụ, tối đa một số liên hệ chính đang hoạt động hoặc tổng tỷ lệ phân bổ bằng 100% là quy tắc trên nhiều hàng. Một CHECK đơn giản trên từng hàng không bảo đảm được điều đó. Cần dùng cơ chế phù hợp của hệ quản trị, transaction, constraint nâng cao hoặc quy trình nghiệp vụ có kiểm soát đồng thời. Phải kiểm tra cả trường hợp hai giao dịch cùng cập nhật tập phần tử.

## 9. Khi nào không nên tách thành cấu trúc riêng?

Tách cấu trúc có lợi khi giải quyết được nhu cầu cụ thể, nhưng cũng tạo thêm quan hệ, truy vấn và quy tắc quản lý. Có thể giữ nhóm trong cấu trúc cha khi:

- Số lượng phần tử cố định và nhỏ, được xác định bởi nghiệp vụ chứ không phải giới hạn tùy tiện.
- Các phần tử có vai trò khác nhau, không cùng một loại lặp.
- Các thành phần luôn được đọc/ghi như một đơn vị.
- Không cần truy vấn, ràng buộc hoặc tham chiếu từng phần tử độc lập.
- Phần tử không có vòng đời hoặc lịch sử riêng.
- Cấu trúc nhúng có giới hạn kích thước và cập nhật phù hợp với hệ quản trị.

Ví dụ, địa chỉ giao hàng và địa chỉ thanh toán có thể là hai thuộc tính phức hợp riêng nếu mỗi đơn chỉ có đúng hai vai trò này và các quy tắc khác nhau. Việc tách thành bảng con chỉ để “chuẩn hóa cho đẹp” có thể làm tăng join mà không tạo lợi ích nghiệp vụ.

Một cấu trúc có thể bắt đầu đơn giản và được tách khi workload hoặc quy tắc thay đổi. Tuy nhiên, nên ghi lại giả định và theo dõi dấu hiệu như số phần tử tăng, truy vấn từng phần tử, nhu cầu chia sẻ và lịch sử để biết khi nào cần tiến hóa.

## 10. Quy trình quyết định tách nhóm lặp

Có thể áp dụng các bước sau khi phân tích một nhóm trường:

1. **Nhận diện mẫu lặp:** tìm các trường có hậu tố, danh sách nhúng hoặc nhóm dữ liệu được nhập nhiều lần.
2. **Xác nhận ngữ nghĩa:** hỏi mỗi lần lặp có cùng ý nghĩa và cấu trúc hay đại diện cho các vai trò cố định khác nhau.
3. **Xác định cardinality:** số lượng tối thiểu/tối đa có cố định không, có thể tăng theo thời gian không.
4. **Xác định metadata:** mỗi phần tử có trạng thái, thời gian, thứ tự, người tạo, nhãn hoặc thuộc tính riêng không.
5. **Kiểm tra vòng đời:** phần tử có được tạo, sửa, xác minh, thu hồi hoặc xóa độc lập không.
6. **Kiểm tra quan hệ:** phần tử có được tham chiếu từ nơi khác hoặc chia sẻ giữa nhiều chủ thể không.
7. **Xác định workload:** cần tìm, lọc, thống kê hoặc cập nhật riêng từng phần tử ở mức nào.
8. **Chọn dạng cấu trúc:** bảng con, thực thể liên kết, object lồng trong document, collection riêng, node/edge hoặc bridge phân tích.
9. **Đặt quy tắc toàn vẹn:** khóa, duy nhất, cardinality, thứ tự, hiệu lực và ràng buộc trên toàn tập.
10. **Kiểm chứng trade-off:** dùng dữ liệu và truy vấn đại diện, thử đồng thời và đánh giá chi phí thay đổi.

### Ma trận quyết định nhanh

| Dấu hiệu | Giữ trong cấu trúc cha | Tách cấu trúc riêng |
|---|---|---|
| Số lượng | Cố định, ít, có ý nghĩa vai trò | Biến đổi hoặc không giới hạn trước |
| Metadata | Không có hoặc rất ít | Mỗi phần tử có nhiều thuộc tính riêng |
| Truy vấn | Luôn đọc cùng cha | Cần tìm/lọc/thống kê từng phần tử |
| Vòng đời | Phụ thuộc hoàn toàn vào cha | Có trạng thái, lịch sử hoặc xử lý riêng |
| Quan hệ | Không được tham chiếu riêng | Có thể liên kết với thực thể khác |
| Toàn vẹn | Quy tắc đơn giản trong cha | Cần khóa, duy nhất hoặc quy tắc trên tập |
| Kích thước | Nhỏ và có giới hạn | Tăng đáng kể hoặc có tài liệu/tệp lớn |

Ma trận này hỗ trợ thảo luận. Quyết định cuối cùng cần giải thích được bằng quy tắc nghiệp vụ và truy vấn thực tế.

## 11. Kiểm chứng mô hình sau khi tách

Sau khi chuyển nhóm lặp thành cấu trúc riêng, cần kiểm tra:

- Dữ liệu cha không có phần tử con có hợp lệ không?
- Có thể tạo nhiều phần tử con cho cùng một cha không?
- Ràng buộc duy nhất có đúng phạm vi không?
- Xóa hoặc lưu trữ cha thì phần tử con được xử lý thế nào?
- Có ngăn được phần tử mồ côi không?
- Các quy tắc như tối đa một phần tử chính có được bảo vệ khi cập nhật đồng thời không?
- Truy vấn thường dùng có chỉ mục phù hợp không?
- Dữ liệu lịch sử có được giữ khi phần tử thay đổi hoặc bị thu hồi không?

Ví dụ truy vấn tìm nhân viên có chứng chỉ đã hết hạn:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    c.certificate_name,
    c.expires_on
FROM employee e
JOIN employee_certificate c
  ON c.employee_id = e.employee_id
WHERE c.expires_on < CURRENT_DATE
  AND c.status = 'VERIFIED';
~~~

Truy vấn này minh họa lợi ích của việc lưu mỗi chứng chỉ thành một hàng: có thể lọc và trả về từng chứng chỉ theo ngày hết hạn và trạng thái. Khi thiết kế chỉ mục, hãy dựa trên phân bố dữ liệu, bộ lọc và kế hoạch thực thi của hệ quản trị thực tế.

Nếu chuyển từ cột lặp sang bảng con, migration cần xác định rõ thứ tự ánh xạ: mỗi nhóm cột cũ trở thành một hàng con; nhóm trống được xử lý ra sao; dữ liệu không đầy đủ có được giữ không; bản ghi trùng được hợp nhất theo quy tắc nào. Sau khi backfill, đối chiếu số lượng phần tử và giá trị từng thành phần trước khi chuyển ứng dụng sang cấu trúc mới.

## 12. Bài tập thực hành và tiêu chí đánh giá

### Bài 1 — Hồ sơ nhân viên

Một nhân viên có nhiều số liên hệ, chứng chỉ, kỹ năng và giai đoạn công tác. Mỗi chứng chỉ có tên, đơn vị cấp, mã, ngày cấp và ngày hết hạn. Mỗi kỹ năng có mức độ và ngày đánh giá.

Hãy phân loại các nhóm lặp, xác định nhóm nào là đối tượng giá trị và nhóm nào cần thực thể riêng. Đề xuất cardinality, khóa và quy tắc duy nhất.

### Bài 2 — Đơn hàng

Một đơn hàng có nhiều dòng hàng. Mỗi dòng có sản phẩm, số lượng, đơn giá tại thời điểm mua, chiết khấu và ghi chú. Một sản phẩm có thể xuất hiện tối đa một lần trong một đơn, hoặc có thể xuất hiện nhiều lần nếu là các đợt giao khác nhau.

Hãy giải thích hai giả định dẫn đến hai mô hình khác nhau. Đề xuất khóa và ràng buộc cho từng trường hợp.

### Bài 3 — Sản phẩm có nhiều ảnh

Mỗi ảnh có URL, loại ảnh, thứ tự hiển thị, trạng thái kiểm duyệt và thời điểm tải lên. Một ảnh có thể được dùng lại ở nhiều sản phẩm.

Hãy xác định ảnh nên là thuộc tính nhiều giá trị đơn, nhóm object nhúng, hay thực thể độc lập. Giải thích dựa trên việc chia sẻ, vòng đời và kiểm duyệt.

### Bài 4 — Chuyển đổi lược đồ

Một bảng cũ có các cột `phone_1`, `phone_2`, `phone_3`. Hãy thiết kế bảng con mới, quy tắc backfill, cách xử lý số trùng và các truy vấn đối chiếu trước khi bỏ cột cũ.

### Rubric tự đánh giá

| Tiêu chí | Đạt yêu cầu khi |
|---|---|
| Nhận diện | Phát hiện được nhóm trường lặp và giải thích ý nghĩa |
| Phân loại | Phân biệt nhóm lặp với thuộc tính phức hợp, nhiều giá trị và vai trò cố định |
| Ranh giới | Chọn đúng giữa đối tượng giá trị và thực thể con |
| Cardinality | Xác định số lượng, thứ tự và tính duy nhất |
| Toàn vẹn | Bảo vệ khóa ngoại, phần tử chính và quy tắc trên toàn tập |
| Workload | Cách biểu diễn hỗ trợ truy vấn và cập nhật thực tế |
| Tiến hóa | Có thể thêm phần tử, lưu lịch sử và migration an toàn |

Một nhóm thuộc tính nên được tách khi cách biểu diễn hiện tại không còn diễn tả tốt số lượng, cấu trúc, quan hệ hoặc vòng đời của từng phần tử. Mục tiêu là chọn cấu trúc vừa đủ để bảo vệ ý nghĩa nghiệp vụ, truy vấn và thay đổi dữ liệu có kiểm soát. Khi các quyết định này được ghi rõ, mô hình quan hệ, document, đồ thị và phân tích có thể được so sánh trên cùng một nền tảng yêu cầu.

