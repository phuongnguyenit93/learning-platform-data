# Chuẩn hóa cấu trúc không thay thế định nghĩa đúng thuật ngữ và quy tắc nghiệp vụ

Một lược đồ có thể **đạt 3NF, BCNF hoặc thậm chí 5NF** về mặt cấu trúc nhưng vẫn mô tả **sai hoạt động kinh doanh**. Ví dụ: bảng **shipments** chỉ lưu một chuyến giao cho mỗi đơn vì người thiết kế tin rằng “mỗi đơn chỉ giao một lần”; trong thực tế đơn có thể tách làm nhiều kiện giao vào những ngày khác nhau. Các khóa và phụ thuộc hàm được xây dựng theo giả định sai sẽ khiến hệ thống mất khả năng lưu một trạng thái nghiệp vụ hợp lệ.

**Chuẩn hóa** giúp tổ chức dữ liệu dựa trên những phụ thuộc **đã xác nhận**. Nó **không tự định nghĩa** “khách hàng” là ai, thế nào là “đơn hoàn tất”, giá nào được dùng để tính doanh thu, một mã có duy nhất trên phạm vi nào, hoặc thông tin nào phải giữ theo thời điểm giao dịch.

Bài thuộc chương **Chuẩn hóa** của mô-đun **DATABASE_DATA_MODELING**. Mục tiêu là kết hợp tư duy mô hình dữ liệu với kỹ năng làm rõ thuật ngữ, ràng buộc, thời gian và phạm vi dữ liệu, rồi kiểm chứng bằng mô hình quan hệ, SQL và các kịch bản nghiệp vụ.

## 1. Hai lớp đúng đắn khác nhau

| Lớp | Câu hỏi cần trả lời | Một lỗi có thể xảy ra |
| --- | --- | --- |
| **Đúng về ngữ nghĩa (semantic correctness)** | Một hàng biểu diễn sự thật gì? Thuật ngữ, phạm vi, vòng đời, quy tắc và ngoại lệ đã đúng chưa? | Đồng nhất “đơn hàng” với “chuyến giao”; bỏ mất trường hợp giao nhiều đợt |
| **Đúng về cấu trúc (structural correctness)** | Khóa ứng viên, phụ thuộc hàm, các dạng chuẩn, phép phân rã và ràng buộc có phù hợp với ngữ nghĩa ấy không? | Chép tên khách hàng hiện hành vào mọi dòng hàng rồi cập nhật không nhất quán |

Hai lớp **bổ sung**, không thay thế nhau. Một mô hình có thể:

- **Đúng nghiệp vụ nhưng dư thừa:** mỗi dòng giao hàng lưu cả tên kho hiện hành, dẫn đến bất thường cập nhật.
- **Đẹp về chuẩn hóa nhưng sai nghiệp vụ:** gắn **UNIQUE(order_id)** lên bảng chuyến giao trong khi một đơn có thể có nhiều chuyến.
- **Đúng cả hai theo hiện tại nhưng khó tiến hóa:** giả định một tiền tệ hoặc một thị trường, không ghi rõ phạm vi để khi mở rộng hệ thống thì khóa và dữ liệu lịch sử trở nên mơ hồ.

Một lược đồ chuẩn hóa chỉ bảo vệ **những quy tắc đã được phát biểu và mô hình hóa**. Nếu quy tắc ban đầu sai, chuẩn hóa có thể khiến hệ thống thực thi **rất chặt chẽ một giả định sai**.

## 2. Thuật ngữ nghiệp vụ phải có định nghĩa vận hành

Một từ trong tài liệu thường có nhiều cách hiểu hợp lệ. Người thiết kế phải chuyển nó thành **định nghĩa có thể kiểm chứng bằng dữ liệu**.

### 2.1. Một từ, nhiều khái niệm

| Từ thường gặp | Câu hỏi cần làm rõ | Hệ quả đối với mô hình |
| --- | --- | --- |
| **Khách hàng** | Là cá nhân, tài khoản, tổ chức ký hợp đồng hay người nhận hàng? Người mua vãng lai có được đặt đơn không? | Có thể cần **customers**, **accounts**, **organizations**, **recipients** riêng; không mặc định một email = một khách hàng |
| **Sản phẩm** | Là dòng sản phẩm, biến thể SKU, gói dịch vụ hay phiên bản danh mục? SKU có được dùng lại không? | Quyết định grain, khóa và mối quan hệ **product–variant–SKU** |
| **Đơn hàng** | Là giỏ đang soạn, cam kết mua đã xác nhận hay đợt thanh toán? | Ảnh hưởng thời điểm tạo, trạng thái, khóa và quan hệ với thanh toán |
| **Dòng hàng** | Một sản phẩm chỉ xuất hiện một lần mỗi đơn, hay có thể có nhiều dòng cùng SKU với giá/ưu đãi khác nhau? | Chọn **(order_id, line_no)** thay vì mặc định **(order_id, product_id)** |
| **Giao hàng** | Một đơn tương ứng một chuyến giao, nhiều chuyến, hay một chuyến gộp nhiều đơn? | Quyết định tính một-nhiều/nhiều-nhiều và khóa của **shipments** |
| **Giá** | Giá niêm yết hiện hành, giá được báo, giá sau giảm, hay giá đã chốt lúc mua? | Không đồng nhất **current_price** và **unit_price_at_order** |
| **Doanh thu** | Theo ngày đặt, ngày thanh toán, ngày giao, xuất hóa đơn hay hoàn thành nghĩa vụ? Đã trừ hoàn tiền chưa? | Cần grain sự kiện và chính sách tính toán, không chỉ một cột **amount** |
| **Đã hoàn tất** | Đã nhận tiền, giao đủ số lượng, khách xác nhận hay hết thời hạn đổi trả? | Phải định nghĩa điều kiện chuyển trạng thái; không chỉ thêm một chuỗi **COMPLETED** |

Ví dụ, hai phòng ban có thể đều nói “khách hàng đang hoạt động” nhưng:

- Bộ phận chăm sóc khách hàng hiểu là tài khoản chưa bị khóa.
- Bộ phận kinh doanh hiểu là đã mua ít nhất một lần trong 90 ngày.
- Bộ phận tài chính hiểu là có công nợ hoặc hợp đồng đang hiệu lực.

Ba cách hiểu có thể dẫn tới **ba tiêu chí truy vấn khác nhau**. Thêm cột **is_active BOOLEAN** mà không định nghĩa “active” và nguồn sự thật chỉ biến mơ hồ nghiệp vụ thành một cột có giá trị đúng/sai tùy người ghi.

### 2.2. Bản ghi thuật ngữ tối thiểu

Mỗi thuật ngữ quan trọng nên có:

1. **Tên chính thức và tên đồng nghĩa:** ví dụ “chuyến giao”, “shipment”, khác với “đơn hàng”.
2. **Định nghĩa tích cực:** nó biểu diễn điều gì.
3. **Điều không bao gồm:** chuyến giao không đồng nghĩa hóa đơn, không đồng nghĩa một lần thanh toán.
4. **Đơn vị/grain:** một mã đại diện một chuyến giao, một dòng hay một sự kiện.
5. **Vòng đời và thời điểm:** khi nào tạo, cập nhật, chốt, hủy; điều gì là hiện hành/lịch sử.
6. **Phạm vi định danh:** mã duy nhất toàn hệ thống, theo cửa hàng, theo đối tác hay theo kỳ.
7. **Chủ sở hữu quy tắc:** bộ phận hoặc vai trò xác nhận và chịu trách nhiệm thay đổi định nghĩa.
8. **Ví dụ hợp lệ/không hợp lệ:** đặc biệt các ngoại lệ và trường hợp biên.

**Ví dụ từ điển thuật ngữ:**

| Thuật ngữ | Định nghĩa trong ví dụ | Phạm vi / thời gian |
| --- | --- | --- |
| **order_id** | Định danh một cam kết mua đã đặt, có thể chứa nhiều dòng và nhiều chuyến giao | Duy nhất trong một hệ thống bán hàng |
| **line_no** | Số thứ tự dòng trong một đơn, có thể lặp ở đơn khác | Duy nhất theo **order_id** |
| **shipment_no** | Số thứ tự chuyến giao của một đơn | Duy nhất theo **order_id** |
| **unit_price_vnd_at_order** | Đơn giá VND đã chốt cho dòng hàng khi đặt | Sự thật lịch sử của **(order_id, line_no)** |
| **ship_to_address_snapshot** | Địa chỉ sử dụng khi tạo chuyến giao, không tự thay khi khách sửa hồ sơ | Sự thật của **(order_id, shipment_no)** |
| **shipment_status** | Trạng thái xử lý của một chuyến giao theo các bước đã được định nghĩa | Giá trị hiện hành; có thể cần nhật ký chuyển trạng thái |

Chữ **snapshot** trong tên cột thể hiện rõ quyết định không cập nhật ngược lịch sử khi thông tin hiện hành thay đổi. Tên cột tốt không thay thế đặc tả, nhưng giúp giảm nhập nhằng khi đọc dữ liệu.

## 3. Quy tắc nghiệp vụ phải được phát biểu thành bất biến và các ngoại lệ

**Bất biến (invariant)** là điều phải đúng đối với mọi trạng thái dữ liệu mà hệ thống cho phép. Những lời mô tả không đủ chính xác rất khó chuyển thành khóa và ràng buộc.

So sánh:

| Phát biểu mơ hồ | Phát biểu có thể kiểm chứng |
| --- | --- |
| “Mỗi đơn có địa chỉ giao.” | “Mỗi **chuyến giao** có đúng một địa chỉ chốt; một đơn có thể có nhiều chuyến đến các địa chỉ khác nhau.” |
| “Mỗi sản phẩm có một giá.” | “Giá niêm yết hiện hành có thể khác theo kênh bán và thời điểm hiệu lực; đơn giá đã chốt thuộc từng dòng đơn.” |
| “Không giao quá số lượng đặt.” | “Tổng **shipped_quantity** của các chuyến giao hợp lệ cho cùng **(order_id, line_no)** không vượt **ordered_quantity**, sau khi xét quy tắc hủy/điều chỉnh.” |
| “Mã hàng là duy nhất.” | “SKU duy nhất trong một danh mục cửa hàng tại một thời điểm; chỉ được tái sử dụng theo chính sách đã xác nhận.” |
| “Đơn hoàn tất.” | “Đơn được đánh dấu COMPLETED khi tất cả dòng cần giao đã giao đủ và các điều kiện thanh toán/hủy theo chính sách được đáp ứng.” |

Cần hỏi thêm:

- **Ngoại lệ:** có đơn đặt trước, hàng tặng giá 0, chia giao, đổi trả hay đơn vãng lai không?
- **Tần suất, vòng đời:** một thuộc tính có thể đổi theo thời gian nhưng không được sửa hồi tố chứ?
- **Quyền ghi:** nhiều hệ thống cùng ghi một sự thật, hay có nguồn chuẩn duy nhất?
- **Đồng thời:** hai tiến trình có thể giao cùng dòng hàng trong một thời điểm không?
- **Biên phạm vi:** quy tắc áp dụng trong một cửa hàng hay trên toàn hệ thống đa cửa hàng?

Một ràng buộc tốt phải đi cùng **ví dụ âm tính**: một trạng thái hệ thống cần từ chối, không chỉ ví dụ hợp lệ. Nhờ đó ta tránh biến một cách hiểu ngầm của người thiết kế thành quy định vĩnh viễn trong cơ sở dữ liệu.

## 4. Phụ thuộc hàm không thể suy ra chỉ từ dữ liệu mẫu

Phụ thuộc hàm **X → Y** có nghĩa: trong **mọi trạng thái hợp lệ** của quan hệ, nếu hai hàng có cùng X thì chúng phải có cùng Y.

Ví dụ:

~~~text
order_id -> customer_id
(order_id, line_no) -> product_id, ordered_quantity, unit_price_vnd_at_order
~~~

Các phụ thuộc đó hợp lý **khi** định nghĩa một đơn thuộc một khách, và mỗi cặp số đơn–số dòng định danh một dòng.

Ngược lại, các phát biểu sau không nên tự chấp nhận:

~~~text
customer_id -> ship_to_address_snapshot   -- thường SAI: khách có thể giao nhiều nơi
product_id  -> unit_price_vnd_at_order    -- thường SAI: giá phụ thuộc giao dịch
order_id    -> shipment_no               -- SAI nếu đơn được chia nhiều chuyến
email       -> customer_id               -- tùy quy tắc tài khoản và email
~~~

### 4.1. Dữ liệu giống nhau chưa tạo ra phụ thuộc

Nếu 500 đơn đầu đều được giao một chuyến, dữ liệu hiện tại có thể làm **order_id → shipment_no** trông đúng. Nhưng **một đơn được phép chia giao** là đủ để bác bỏ phụ thuộc đó theo nghiệp vụ, ngay cả khi tình huống chưa từng xảy ra trong dữ liệu mẫu.

Nếu những khách hàng hiện tại đều có email khác nhau, điều đó cũng không chứng minh email là định danh không đổi hoặc luôn có mặt. Email có thể đổi, bị dùng chung, chưa xác minh, được tái sử dụng hoặc không có đối với người mua tại quầy.

### 4.2. Đổi ngữ nghĩa làm đổi khóa ứng viên

Giả sử bản thiết kế cũ ghi:

~~~text
shipments(order_id, shipped_at, address, ...)
PRIMARY KEY (order_id)
~~~

Điều này chỉ biểu diễn **tối đa một chuyến giao trên một đơn**. Nếu yêu cầu mới cho phép nhiều chuyến, grain phải đổi thành **một chuyến giao của một đơn**, có thể dùng:

~~~text
shipments(order_id, shipment_no, shipped_at, address, ...)
PRIMARY KEY (order_id, shipment_no)
~~~

Thay đổi này không phải “tối ưu chuẩn hóa” theo nghĩa thuần túy. Đây là **sửa một khẳng định nghiệp vụ** về số lượng sự kiện có thể tồn tại.

### 4.3. Dạng chuẩn là kết luận có điều kiện

2NF, 3NF, BCNF, 4NF và 5NF đều dựa trên các phụ thuộc và khóa **đúng trong phạm vi nghiệp vụ đã xác nhận**. Một bảng có thể đạt 3NF theo một tập phụ thuộc sai và vẫn không lưu được các trạng thái hợp lệ; ngược lại, một bảng bị cho là “chưa chuẩn” có thể đang lưu các giá trị ở **những thời điểm khác nhau**, không phải sao chép cùng một sự thật.

Do đó, thứ tự đúng là **xác nhận thuật ngữ → xác nhận phụ thuộc/ràng buộc → xác định khóa → kiểm tra dạng chuẩn → kiểm chứng các kịch bản sử dụng**.

## 5. Tình huống xuyên suốt: một đơn, nhiều dòng, nhiều chuyến giao

Các giả định minh họa để xây dựng lược đồ:

- Mỗi khách hàng đăng ký có **customer_id** duy nhất; một khách có thể có nhiều đơn.
- Mỗi sản phẩm có **product_id** duy nhất; tên sản phẩm hiện hành không định danh sản phẩm.
- Một đơn thuộc về một khách và có thể có nhiều dòng; dòng được đánh số bằng **line_no** trong phạm vi đơn.
- Một đơn có thể giao bằng nhiều chuyến; mỗi chuyến có **shipment_no** trong phạm vi đơn.
- Một dòng đơn có thể được chia giao qua nhiều chuyến; một chuyến có thể chứa một hoặc nhiều dòng **của chính đơn đó**.
- Đơn giá VND đã chốt thuộc dòng đơn; địa chỉ giao đã chốt thuộc chuyến giao.
- Số lượng đặt là số nguyên dương; số lượng giao trong một lần phân bổ là số nguyên dương.
- Một đơn có thể chưa có chuyến giao; một dòng đã đặt có thể chưa được giao.

Theo các định nghĩa trên, có ba grain nghiệp vụ độc lập quan trọng:

| Quan hệ | Grain | Khóa ứng viên |
| --- | --- | --- |
| **orders** | Một đơn hàng | **order_id** |
| **order_lines** | Một dòng thuộc một đơn | **(order_id, line_no)** |
| **shipments** | Một chuyến giao thuộc một đơn | **(order_id, shipment_no)** |
| **shipment_items** | Một phần của dòng đơn được giao trong một chuyến | **(order_id, shipment_no, line_no)** |

Điều này không buộc mỗi đơn có đúng một chuyến, cũng không buộc mỗi dòng được giao trọn trong một chuyến.

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : "đặt"
    ORDERS ||--o{ ORDER_LINES : "có dòng"
    PRODUCTS ||--o{ ORDER_LINES : "được đặt"
    ORDERS ||--o{ SHIPMENTS : "chia thành"
    SHIPMENTS ||--o{ SHIPMENT_ITEMS : "gồm"
    ORDER_LINES ||--o{ SHIPMENT_ITEMS : "được phân bổ"
    CUSTOMERS {
        varchar customer_id PK
        varchar display_name
    }
    ORDERS {
        varchar order_id PK
        varchar customer_id FK
        timestamptz placed_at
    }
    ORDER_LINES {
        varchar order_id PK, FK
        integer line_no PK
        varchar product_id FK
        integer ordered_quantity
        bigint unit_price_vnd_at_order
    }
    SHIPMENTS {
        varchar order_id PK, FK
        integer shipment_no PK
        text ship_to_address_snapshot
        varchar status
    }
    SHIPMENT_ITEMS {
        varchar order_id PK, FK
        integer shipment_no PK, FK
        integer line_no PK, FK
        integer shipped_quantity
    }
~~~

**Ý nghĩa của bảng shipment_items:** Nó không chỉ là “bảng nối kỹ thuật” giữa hai ID. Mỗi hàng có sự thật **shipped_quantity** của một dòng trong một chuyến; nếu xóa nó, ta mất thông tin phân bổ lượng hàng. Các khóa ngoại phải bảo đảm dòng được giao và chuyến giao **cùng thuộc một đơn**, chứ không chỉ mỗi ID tồn tại ở đâu đó trong cơ sở dữ liệu.

## 6. Chuyển quy tắc đã xác nhận thành lược đồ PostgreSQL

Lược đồ sau là ví dụ **có giới hạn chủ đích**: chỉ một danh mục sản phẩm, một tiền tệ VND, khách đã đăng ký, không mô hình đổi trả và không hỗ trợ một chuyến giao gom nhiều đơn. Những giới hạn này phải được nêu rõ, không xem là chân lý phổ quát.

### 6.1. Khóa và quan hệ tham chiếu

~~~sql
CREATE TABLE customers (
    customer_id VARCHAR(12) PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    contact_phone VARCHAR(32)
);

CREATE TABLE products (
    product_id VARCHAR(12) PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL
);

CREATE TABLE orders (
    order_id VARCHAR(12) PRIMARY KEY,
    customer_id VARCHAR(12) NOT NULL
        REFERENCES customers(customer_id),
    placed_at TIMESTAMPTZ NOT NULL,
    order_status VARCHAR(16) NOT NULL
        CHECK (order_status IN ('PLACED', 'CANCELLED', 'CLOSED'))
);

CREATE TABLE order_lines (
    order_id VARCHAR(12) NOT NULL
        REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(12) NOT NULL
        REFERENCES products(product_id),
    ordered_quantity INTEGER NOT NULL
        CHECK (ordered_quantity > 0),
    unit_price_vnd_at_order BIGINT NOT NULL
        CHECK (unit_price_vnd_at_order >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE shipments (
    order_id VARCHAR(12) NOT NULL
        REFERENCES orders(order_id),
    shipment_no INTEGER NOT NULL CHECK (shipment_no > 0),
    ship_to_address_snapshot TEXT NOT NULL,
    shipped_at TIMESTAMPTZ NOT NULL,
    shipment_status VARCHAR(16) NOT NULL
        CHECK (shipment_status IN ('DISPATCHED', 'DELIVERED')),
    PRIMARY KEY (order_id, shipment_no)
);

CREATE TABLE shipment_items (
    order_id VARCHAR(12) NOT NULL,
    shipment_no INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    shipped_quantity INTEGER NOT NULL
        CHECK (shipped_quantity > 0),
    PRIMARY KEY (order_id, shipment_no, line_no),
    FOREIGN KEY (order_id, shipment_no)
        REFERENCES shipments(order_id, shipment_no),
    FOREIGN KEY (order_id, line_no)
        REFERENCES order_lines(order_id, line_no)
);
~~~

Điểm đáng chú ý:

- **order_id** chỉ định danh đơn; **(order_id, shipment_no)** mới định danh chuyến giao theo quy tắc ví dụ.
- Một chuyến giao có thể chứa nhiều dòng, và một dòng có thể có mặt ở nhiều chuyến; **shipment_items** lưu số lượng thực tế đã xuất.
- Hai **FOREIGN KEY ghép** của **shipment_items** dùng **cùng order_id**, bảo đảm mỗi bản ghi phân bổ chỉ có thể nối chuyến giao và dòng hàng **trong cùng đơn**.
- **contact_phone** không có ràng buộc **UNIQUE** vì ví dụ **không** giả định số điện thoại định danh duy nhất một khách hàng.
- **UNIQUE(sku)** là **giả định nghiệp vụ của danh mục đơn cửa hàng này**; nếu SKU duy nhất theo nhà bán, theo phiên bản hay theo thời gian, ràng buộc phải đổi.
- **CHECK** trên trạng thái chỉ kiểm tra **giá trị thuộc danh sách cho phép**, không kiểm tra thứ tự chuyển trạng thái hoặc việc có giao đủ hàng hay chưa.

Các cột **shipped_at** và **shipment_status** trong ví dụ biểu diễn một chuyến **đã xuất kho**; chưa mô hình phiếu dự kiến chưa xuất, giao thất bại, hoàn hàng hay đổi lịch. Khi bổ sung các tình huống đó, grain, trạng thái và quy tắc cộng trừ số lượng phải được xét lại.

### 6.2. Dữ liệu mẫu chứng minh một đơn chia nhiều chuyến

~~~sql
INSERT INTO customers (customer_id, display_name, contact_phone)
VALUES ('C01', 'An', '+84901234567');

INSERT INTO products (product_id, sku, product_name) VALUES
    ('P10', 'KB-001', 'Bàn phím'),
    ('P20', 'MS-001', 'Chuột');

INSERT INTO orders (order_id, customer_id, placed_at, order_status)
VALUES (
    'O1001',
    'C01',
    TIMESTAMPTZ '2026-11-20 09:00:00+07',
    'PLACED'
);

INSERT INTO order_lines
    (order_id, line_no, product_id,
     ordered_quantity, unit_price_vnd_at_order)
VALUES
    ('O1001', 1, 'P10', 3, 300000),
    ('O1001', 2, 'P20', 1, 200000);

INSERT INTO shipments
    (order_id, shipment_no, ship_to_address_snapshot,
     shipped_at, shipment_status)
VALUES
    ('O1001', 1, '12 Nguyễn Huệ, TP.HCM',
     TIMESTAMPTZ '2026-11-21 10:00:00+07', 'DELIVERED'),
    ('O1001', 2, '99 Lê Lợi, TP.HCM',
     TIMESTAMPTZ '2026-11-22 11:00:00+07', 'DISPATCHED');

INSERT INTO shipment_items
    (order_id, shipment_no, line_no, shipped_quantity)
VALUES
    ('O1001', 1, 1, 2),
    ('O1001', 2, 1, 1),
    ('O1001', 2, 2, 1);
~~~

Một đơn có hai chuyến giao và hai địa chỉ khác nhau. Dòng 1 đặt ba bàn phím, được chia thành **hai chiếc ở chuyến 1** và **một chiếc ở chuyến 2**. Không thể biểu diễn đầy đủ thông tin này bằng giả định **order_id → shipment_no** hoặc **order_id → ship_to_address_snapshot**.

Truy vấn xác nhận lượng hàng đã xuất trên từng dòng:

~~~sql
SELECT
    ol.order_id,
    ol.line_no,
    p.product_name,
    ol.ordered_quantity,
    COALESCE(SUM(si.shipped_quantity), 0) AS shipped_quantity,
    ol.ordered_quantity
      - COALESCE(SUM(si.shipped_quantity), 0) AS remaining_quantity
FROM order_lines AS ol
JOIN products AS p
  ON p.product_id = ol.product_id
LEFT JOIN shipment_items AS si
  ON si.order_id = ol.order_id
 AND si.line_no = ol.line_no
GROUP BY ol.order_id, ol.line_no, p.product_name,
         ol.ordered_quantity
ORDER BY ol.order_id, ol.line_no;
~~~

Kết quả với dữ liệu mẫu:

| order_id | line_no | ordered_quantity | shipped_quantity | remaining_quantity |
| --- | ---: | ---: | ---: | ---: |
| O1001 | 1 | 3 | 3 | 0 |
| O1001 | 2 | 1 | 1 | 0 |

Trong ví dụ, **shipped_quantity** là lượng đã xuất kho; không đồng nghĩa toàn bộ lượng **đã giao thành công**, vì chuyến 2 mới ở trạng thái **DISPATCHED**. Nếu báo cáo cần lượng đã giao, phải lọc hoặc tính theo trạng thái giao thành công và quy tắc hoàn trả phù hợp.

### 6.3. Lược đồ này đã ngăn được những lỗi nào?

| Tình huống | Ràng buộc bảo vệ |
| --- | --- |
| Hai dòng cùng **(order_id, line_no)** | **PRIMARY KEY** trên **order_lines** |
| Hai chuyến cùng **(order_id, shipment_no)** | **PRIMARY KEY** trên **shipments** |
| Số lượng đặt hoặc xuất bằng 0/âm | **CHECK** tại cột tương ứng |
| Ghi chuyến cho đơn không tồn tại | **FOREIGN KEY** trên **shipments** |
| Phân bổ một dòng không thuộc đơn của chuyến | **Hai FOREIGN KEY ghép** trong **shipment_items** |
| Ghi trạng thái hoàn toàn không có trong danh sách | **CHECK** trên **order_status**, **shipment_status** |

Ví dụ, nếu **O1002** có một dòng số 3, hệ thống **không** được phép dùng dòng đó cho chuyến **(O1001, 2)** chỉ vì cả chuyến và dòng đều tồn tại ở đâu đó. Khóa ghép buộc phân bổ cùng một **order_id**.

### 6.4. Điều gì vẫn chưa được DDL bảo vệ?

Định nghĩa nghiệp vụ yêu cầu **tổng lượng đã xuất trên các chuyến cho một dòng không vượt số lượng đặt**:

~~~text
Với mọi (order_id, line_no):

SUM(shipment_items.shipped_quantity)
  <= order_lines.ordered_quantity
~~~

Đây là **ràng buộc tổng hợp qua nhiều hàng**. Một **CHECK** thông thường trên **shipment_items.shipped_quantity > 0** không đủ.

Thử trong giao dịch rồi rollback:

~~~sql
BEGIN;

INSERT INTO shipments
    (order_id, shipment_no, ship_to_address_snapshot,
     shipped_at, shipment_status)
VALUES
    ('O1001', 3, '12 Nguyễn Huệ, TP.HCM',
     TIMESTAMPTZ '2026-11-22 12:00:00+07', 'DISPATCHED');

-- Dòng 1 đã xuất đủ 3 chiếc ở hai chuyến đầu.
-- Bảng vẫn nhận thêm 1 chiếc nếu chỉ có các CHECK/FK/PK trên.
INSERT INTO shipment_items
    (order_id, shipment_no, line_no, shipped_quantity)
VALUES ('O1001', 3, 1, 1);

ROLLBACK;
~~~

Sau hai câu INSERT trong giao dịch minh họa, tổng lượng xuất ở dòng 1 là **4 > 3**, nhưng các khóa, khóa ngoại và CHECK trên từng hàng đều không báo lỗi. Đây là **lỗ hổng ràng buộc nghiệp vụ**, không phải nhất thiết là vi phạm 3NF.

Cách bảo vệ cần **quy trình ghi giao dịch** hoặc cơ chế ràng buộc bổ sung được thiết kế cho tổng theo nhóm. Ví dụ:

1. Bắt đầu giao dịch.
2. **Khóa hàng order_lines tương ứng** bằng **SELECT ... FOR UPDATE** (hoặc cơ chế đồng bộ tương đương).
3. Đọc **SUM(shipped_quantity)** hiện có cho dòng đó.
4. Chỉ ghi thêm khi tổng mới không vượt **ordered_quantity**.
5. Commit; mọi luồng ghi lượng xuất **bắt buộc tuân theo cùng giao thức khóa**, và phải xét cả thao tác sửa số lượng đặt, hủy hay hoàn hàng.

~~~sql
-- Phác thảo bước khóa, gọi với tham số từ ứng dụng:
BEGIN;

SELECT ordered_quantity
FROM order_lines
WHERE order_id = :order_id AND line_no = :line_no
FOR UPDATE;

SELECT COALESCE(SUM(shipped_quantity), 0) AS already_shipped
FROM shipment_items
WHERE order_id = :order_id AND line_no = :line_no;

-- Ứng dụng kiểm tra:
-- already_shipped + requested_quantity <= ordered_quantity.
-- Chỉ sau kiểm tra thành công mới INSERT/UPDATE shipment_items.
-- Tất cả luồng ghi liên quan phải dùng cùng giao thức.

COMMIT;
~~~

Khối SQL này **là phác thảo có tham số**, không phải một script chạy độc lập; nó chưa có câu INSERT. Trong hệ thống nhiều luồng ghi, cần thực thi quy tắc bằng transaction/trigger/procedure hoặc cơ chế đồng bộ được kiểm thử, không dựa vào một câu **SELECT** kiểm tra trước bên ngoài transaction. Nếu luật kiểm tra được thực thi chỉ ở một phần ứng dụng, luồng nhập liệu khác vẫn có thể vi phạm.

### 6.5. Trạng thái là một máy trạng thái, không chỉ là một cột

**CHECK (order_status IN (...))** không ngăn được trường hợp chuyển trực tiếp **CANCELLED → CLOSED** khi nghiệp vụ cấm việc đó. Cần đặc tả chuyển trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> PLACED
    PLACED --> CANCELLED : "được phép hủy"
    PLACED --> CLOSED : "đủ điều kiện đóng"
    CANCELLED --> [*]
    CLOSED --> [*]
~~~

Đây là **sơ đồ quy trình ví dụ**, chưa chứa xử lý hoàn hàng hoặc mở lại đơn. Muốn kiểm toán các thay đổi, có thể lưu **order_status_events(order_id, event_no, from_status, to_status, changed_at, actor_id)** với khóa, thời điểm và tính bất biến của sự kiện được quy định rõ.

Hai câu hỏi khác nhau cần được trả lời:

- **Trạng thái hiện tại** có nằm trong tập giá trị hợp lệ không? Đây là kiểm tra miền dữ liệu.
- **Quá trình chuyển trạng thái** và điều kiện mở/đóng có hợp lệ không? Đây là quy tắc nghiệp vụ liên quan trạng thái trước, sự kiện, quyền thực hiện và có thể cả thông tin ở bảng khác.

## 7. Phạm vi định danh và ngữ nghĩa thời gian

Hai thuộc tính dễ bị hiểu sai nhất khi mô hình hóa dữ liệu thực tế là **tính duy nhất** và **thời điểm hiệu lực**.

### 7.1. “Duy nhất” phải có phạm vi rõ

Giả sử hệ thống mở rộng từ một cửa hàng sang nhiều nhà bán độc lập. Nếu SKU **KB-001** được phép có ở hai nhà bán với ý nghĩa khác nhau, khóa duy nhất toàn cục trên **sku** trong ví dụ mục 6 không còn đúng.

Một quy tắc mới có thể là:

~~~text
(seller_id, sku) -> product_id
~~~

với giả định SKU chỉ duy nhất **trong phạm vi một nhà bán** tại một thời điểm và không tái sử dụng. Khi đó:

~~~sql
CREATE TABLE seller_products (
    seller_id VARCHAR(12) NOT NULL,
    product_id VARCHAR(12) NOT NULL,
    sku VARCHAR(30) NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (seller_id, product_id),
    UNIQUE (seller_id, sku)
);
~~~

Đây là **ví dụ thiết kế khác** cho một hệ thống đa nhà bán, **không phải** lệnh sửa trực tiếp bảng **products** của mục 6. Nếu SKU có thể tái sử dụng sau khi ngừng bán, **UNIQUE(seller_id, sku)** vẫn quá chặt đối với việc lưu lịch sử; cần thiết kế phiên bản hoặc khoảng hiệu lực và kiểm soát trùng lặp theo thời gian.

Người thiết kế cần hỏi “duy nhất ở đâu, trong bao lâu, với ngoại lệ nào?” trước khi đặt **PRIMARY KEY** hoặc **UNIQUE**.

### 7.2. Hai loại thời gian thường bị trộn

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Thời điểm xảy ra/hiệu lực nghiệp vụ** | Khi giá, quyền hoặc trạng thái được xem là đúng trong thế giới nghiệp vụ | Giá áp dụng từ ngày 1/12 |
| **Thời điểm ghi nhận trong hệ thống** | Khi cơ sở dữ liệu nhận được hoặc sửa bản ghi | Ngày 3/12 mới nhập dữ liệu giá có hiệu lực 1/12 |
| **Ảnh chụp lúc giao dịch** | Giá trị đã chốt để giải thích giao dịch ở thời điểm ấy | Đơn giá trên dòng hàng đã đặt ngày 20/11 |

Các thời điểm có thể khác nhau. Nếu giao dịch được nhập muộn hoặc điều chỉnh hồi tố, cột **updated_at** không đủ cho mọi câu hỏi lịch sử.

Một bảng giá theo thời gian có thể có grain:

~~~text
(product_id, price_list_id, valid_from)
    -> unit_price, valid_to
~~~

nhưng đó **chưa đủ** để ngăn hai khoảng hiệu lực chồng nhau cho cùng sản phẩm và bảng giá. Quy tắc “mỗi thời điểm có tối đa một mức giá hiệu lực” cần kiểm tra **khoảng thời gian**, có thể bằng ràng buộc nâng cao hoặc quy trình ghi có kiểm soát, tùy cơ sở dữ liệu.

Với đơn giá **unit_price_vnd_at_order**, không nên tính lại một đơn cũ từ bảng giá hiện hành nếu điều đó làm thay đổi hợp đồng giao dịch đã chốt.

### 7.3. Định nghĩa một chỉ số không thuộc riêng lược đồ

Giả sử báo cáo hỏi **doanh thu tháng 11**. Có ít nhất các khả năng:

- Tổng giá trị **đơn đặt trong tháng**, gồm cả đơn chưa giao.
- Giá trị hàng **đã xuất kho trong tháng**.
- Giá trị hàng **đã giao thành công trong tháng**.
- Tiền **đã thanh toán trong tháng**.
- Doanh thu kế toán **được ghi nhận theo chính sách kế toán** trong tháng, có điều chỉnh trả hàng và hoàn tiền.

Những thước đo này khác nhau về **grain sự kiện, thời gian, số tiền, lọc trạng thái và điều chỉnh**. Chuẩn hóa đến 3NF không quyết định chỉ số nào là “doanh thu”.

Thay vì dùng tên mơ hồ **revenue**, nên viết đặc tả chỉ số: nguồn dữ liệu, công thức, múi giờ, thời điểm chốt, hoàn/hủy, tiền tệ, chính sách ghi nhận và người phê duyệt. Nếu phục vụ kho phân tích, mô hình **fact** cũng cần grain đã định nghĩa trước khi chọn bảng dimension và khóa.

## 8. Một lược đồ đúng cần nhiều lớp bảo vệ

| Loại quy tắc | Cơ chế khả thi | Giới hạn cần biết |
| --- | --- | --- |
| Bắt buộc nhập | **NOT NULL** | Không giải thích giá trị có đúng nghĩa không |
| Miền số lượng/giá trị | **CHECK**, kiểu dữ liệu | Chỉ kiểm tra điều kiện theo hàng hoặc biểu thức được hệ quản trị cho phép |
| Tính duy nhất trong phạm vi | **PRIMARY KEY**, **UNIQUE** | Phạm vi, NULL và thời gian hiệu lực phải được mô hình hóa đúng |
| Quan hệ tồn tại giữa thực thể | **FOREIGN KEY** | Không tự bảo đảm trạng thái hay hành vi hợp lệ của hai thực thể |
| Không chồng khoảng hiệu lực | Ràng buộc khoảng thời gian, exclusion constraint hoặc giao dịch phù hợp | Không thay thế định nghĩa về lúc bắt đầu/kết thúc hiệu lực |
| Tổng lượng xuất không vượt lượng đặt | Giao dịch có khóa phù hợp, trigger/procedure hoặc thiết kế giữ tổng có kiểm soát | Phải xử lý ghi đồng thời và mọi đường cập nhật |
| Chuyển trạng thái hợp lệ | Máy trạng thái cùng cơ chế ghi nhất quán và kiểm toán | **CHECK(status IN ...)** chỉ kiểm tra giá trị cuối |
| Quyền chuyển trạng thái, phê duyệt | Phân quyền, chính sách nghiệp vụ và nhật ký sự kiện | Khóa ngoại không quyết định ai được phép thao tác |
| Định nghĩa doanh thu, khách hàng hoạt động | Từ điển chỉ số, quy tắc tính và kiểm thử báo cáo | Không thể suy ra từ tên cột |

**Chuẩn hóa và ràng buộc không phải hai bước thay thế nhau**: chuẩn hóa giúp đặt sự thật ở đúng quan hệ; ràng buộc và quy trình ghi giúp ngăn những trạng thái không phù hợp với quy tắc thực tế.

### 8.1. Truy vấn giám sát chỉ kiểm tra dữ liệu hiện có

Ví dụ kiểm tra các dòng đã xuất quá số lượng đặt:

~~~sql
SELECT
    ol.order_id,
    ol.line_no,
    ol.ordered_quantity,
    COALESCE(SUM(si.shipped_quantity), 0) AS shipped_quantity
FROM order_lines AS ol
LEFT JOIN shipment_items AS si
  ON si.order_id = ol.order_id
 AND si.line_no = ol.line_no
GROUP BY ol.order_id, ol.line_no, ol.ordered_quantity
HAVING COALESCE(SUM(si.shipped_quantity), 0)
       > ol.ordered_quantity;
~~~

Không có hàng trả về nghĩa là **chưa phát hiện** vi phạm trong snapshot dữ liệu được truy vấn; nó **không chứng minh** cơ chế ghi có thể ngăn vi phạm trong tương lai. Hãy phân biệt **phát hiện**, **ngăn chặn** và **khôi phục/sửa sai**.

### 8.2. Không đánh đồng dạng chuẩn với tính đúng của ứng dụng

Bảng **orders** có thể đạt 3NF nhưng ứng dụng vẫn ghi sai ngày đặt do nhầm múi giờ. Bảng **shipments** có thể đạt BCNF nhưng ứng dụng có thể gắn nhãn **DELIVERED** quá sớm. Một mô hình hoàn toàn không dư thừa có thể thiếu dữ liệu để tính hoàn tiền.

Vì vậy, việc xác nhận thiết kế phải xét:

- **Cấu trúc:** khóa, phụ thuộc, các dạng chuẩn, phép nối.
- **Quy tắc:** bất biến, trạng thái, quyền, ngoại lệ, lịch sử.
- **Hành vi:** tạo/sửa/xóa/hủy/hoàn, đồng thời, chuyển giao giữa hệ thống.
- **Vận hành:** kiểm toán, giám sát dữ liệu, sửa lỗi, thay đổi định nghĩa qua thời gian.

## 9. Quy trình từ ngôn ngữ nghiệp vụ đến mô hình có thể kiểm chứng

### Bước 1 — Phỏng vấn qua tình huống, không chỉ qua danh từ

Thay vì hỏi “có bảng đơn hàng không?”, hãy hỏi:

- Một đơn có thể giao bao nhiêu chuyến? Một chuyến có thể chứa hàng của nhiều đơn không?
- Hàng có thể giao một phần, trả lại, thất bại hay chuyển địa chỉ sau khi đặt không?
- Tên sản phẩm đổi thì hóa đơn cũ phải hiển thị tên cũ hay tên mới?
- Khách hàng không có số điện thoại hoặc dùng chung số với người khác có được tạo không?
- Thế nào là “đã thanh toán”, “đã giao”, “hoàn thành”?

### Bước 2 — Viết từ điển thuật ngữ và ghi rõ giả định

Một bản ghi đơn giản có thể dùng dạng:

~~~text
TERM: Shipment
MEANING: Một lần xuất hàng để giao cho một đơn.
GRAIN: (order_id, shipment_no)
CARDINALITY: Một Order có 0..n Shipment.
TEMPORAL: shipped_at là thời điểm xuất hàng thực tế.
EXCLUDES: Không đồng nghĩa thanh toán hoặc giao thành công.
OWNER: Nhóm vận hành giao nhận.
EXCEPTION: Hoàn hàng, gộp đơn chưa thuộc phạm vi phiên bản này.
~~~

Giả định chưa xác minh cần được đánh dấu rõ, không lặng lẽ biến thành **NOT NULL** hay **UNIQUE**.

### Bước 3 — Viết quy tắc dưới dạng kiểm thử

Ví dụ:

~~~text
Given: Một đơn O có hai dòng, dòng 1 đặt 3 chiếc.
When: Xuất 2 chiếc ở chuyến 1 và 1 chiếc ở chuyến 2.
Then: Hệ thống chấp nhận, tổng xuất = 3.

Given: Tổng xuất của dòng 1 đã bằng 3.
When: Một luồng khác xuất thêm 1 chiếc.
Then: Hệ thống từ chối theo quy tắc tổng lượng.

Given: Một chuyến thuộc đơn O1 và dòng thuộc đơn O2.
When: Cố phân bổ dòng O2 vào chuyến O1.
Then: Hệ thống từ chối.

Given: Khách đổi địa chỉ liên hệ hôm nay.
When: Mở lịch sử chuyến đã xuất tuần trước.
Then: Địa chỉ snapshot của chuyến vẫn giữ nguyên.
~~~

### Bước 4 — Xác định grain, lực lượng quan hệ và khóa ứng viên

Với mỗi thực thể và quan hệ, trả lời một hàng là gì, điều gì định danh duy nhất hàng và khóa có hiệu lực trong phạm vi nào. Ghi rõ **0..1**, **1..n**, **0..n** cùng các ngoại lệ: câu “mỗi đơn có chuyến giao” có thể sai ngay khi đơn vừa được đặt.

### Bước 5 — Xác nhận các phụ thuộc và chuẩn hóa

Viết các FD/MVD/JD hợp lệ từ quy tắc đã được kiểm chứng. Sau đó mới xét 1NF, 2NF, 3NF, BCNF, 4NF hoặc 5NF theo yêu cầu. Khi phân rã, kiểm tra **lossless join**, **bảo toàn các phụ thuộc** có ý nghĩa và khả năng tạo các trạng thái nghiệp vụ mới.

### Bước 6 — Chọn cách thực thi từng bất biến

Gán quy tắc với cơ chế tương ứng: kiểu dữ liệu, **CHECK**, **UNIQUE**, **FOREIGN KEY**, giao dịch, procedure, trigger, phân quyền hoặc kiểm toán. Phân biệt quy tắc được **cơ sở dữ liệu bảo vệ ngay** với quy tắc đang chỉ được **ứng dụng** thực hiện.

### Bước 7 — Thử dữ liệu hợp lệ và phản ví dụ

Không chỉ kiểm tra ví dụ phổ biến. Cần tạo ca có nhiều chuyến, nhiều giá, thiếu số điện thoại, hai khách dùng chung số, trạng thái hủy, ghi đồng thời, giao một phần, mã cũ và lịch sử thay đổi.

### Bước 8 — Đánh giá tiến hóa và mô hình đọc

Nếu nghiệp vụ đổi thành chuyến giao gộp nhiều đơn, **(order_id, shipment_no)** có thể không còn là định danh tốt cho một chuyến thực tế; cần cân nhắc **shipment_id** độc lập và bảng nối đơn–chuyến. Nếu mở nhiều nhà bán, khóa SKU cần phạm vi rõ. Nếu cần số liệu phân tích theo ngày giao, phải thêm đúng grain sự kiện và quy tắc chốt.

Mô hình quan hệ, document, đồ thị và kho phân tích đều cần **định nghĩa thuật ngữ nhất quán**:

- **Quan hệ:** mạnh về khóa và toàn vẹn tham chiếu; cần thiết kế transaction cho luật liên quan nhiều hàng.
- **Document:** có thể nhúng dòng vào đơn để tối ưu thao tác theo aggregate; vẫn phải làm rõ lịch sử và quy tắc xuyên document.
- **Đồ thị:** hữu ích khi trọng tâm là quan hệ nhiều bước; tên cạnh và ngữ nghĩa của cạnh phải được định nghĩa chính xác.
- **Phân tích:** fact và dimension có thể phi chuẩn hóa phục vụ truy vấn; cần xác định grain, thời gian hiệu lực và cách tính chỉ số.

Không có dạng lưu trữ nào sửa được việc gọi hai sự kiện khác nhau bằng cùng một thuật ngữ mơ hồ.

## 10. Những nhầm lẫn làm mô hình “đúng chuẩn nhưng sai việc”

| Nhầm lẫn | Hậu quả | Cách sửa |
| --- | --- | --- |
| “Tất cả dữ liệu đều có khóa chính nên mô hình đúng.” | Khóa có thể đang chặn một trạng thái nghiệp vụ hợp lệ | Xác nhận grain, tính duy nhất và các ngoại lệ trước khi đặt khóa |
| “Chưa thấy đơn nào giao hai chuyến nên mỗi đơn chỉ có một chuyến.” | Không lưu được giao một phần hoặc giao lại | Hỏi về khả năng, không chỉ quan sát dữ liệu hiện tại |
| “Mọi giá trị trùng nhau đều cần tách bảng.” | Mất ảnh chụp lịch sử hoặc làm thay đổi hóa đơn cũ | Phân biệt giá trị hiện hành với giá trị đã chốt và thời điểm hiệu lực |
| “Tên cột **status** đủ để ai cũng hiểu.” | Các bộ phận cập nhật và báo cáo theo tiêu chí khác nhau | Định nghĩa trạng thái, chuyển tiếp, điều kiện và người chịu trách nhiệm |
| “Một CHECK hợp lệ bảo đảm toàn bộ quy tắc.” | Không chặn tổng xuất vượt số lượng hoặc ghi sai trình tự trạng thái | Phân loại ràng buộc theo hàng, theo nhóm, theo lịch sử và theo giao dịch |
| “UNIQUE(email) là chuẩn hóa khách hàng.” | Từ chối tài khoản dùng chung email hoặc thiếu email dù nghiệp vụ cho phép | Xác nhận email có phải định danh, thuộc ai, bắt buộc hay có thể đổi không |
| “Kết quả JOIN đúng ở dữ liệu mẫu nghĩa là phân rã luôn lossless.” | Bộ giả có thể xuất hiện khi một trạng thái nghiệp vụ khác xảy ra | Chứng minh phụ thuộc phù hợp với **mọi trạng thái hợp lệ** |
| “Sau khi đạt BCNF thì không cần kiểm thử nghiệp vụ.” | Lỗi trạng thái, thời gian, quyền và ghi đồng thời vẫn tồn tại | Kiểm thử bất biến và hành vi, không chỉ dạng chuẩn |
| “Chọn mô hình document sẽ hết vấn đề chuẩn hóa.” | Thông tin nhúng có thể không đồng bộ hoặc diễn giải sai | Xác định nguồn chuẩn, vòng đời và tính nhất quán trước khi chọn công nghệ |

**Dấu hiệu cảnh báo:** yêu cầu chứa các từ “luôn”, “duy nhất”, “hiện tại”, “đã”, “tất cả”, “mới nhất”, “không bao giờ”, “mỗi” mà chưa có phạm vi, ngoại lệ hoặc mốc thời gian. Những từ này thường che giấu một phụ thuộc hoặc ràng buộc cần được xác nhận.

## 11. Bài tập vận dụng

### Bài 1 — Bảng đã chuẩn hóa nhưng sai cardinality

Nhóm thiết kế tạo:

~~~sql
CREATE TABLE deliveries_bad (
    order_id VARCHAR(12) PRIMARY KEY,
    delivered_at TIMESTAMPTZ,
    delivered_address TEXT NOT NULL
);
~~~

Nhóm cho rằng bảng chỉ có một khóa đơn, không có phụ thuộc hàm không khóa và có thể đạt BCNF. Sau đó bộ phận vận hành thông báo một đơn có thể được giao **hai lần vào hai ngày và địa chỉ khác nhau**.

**Yêu cầu:**

1. Giải thích vì sao kết luận đạt BCNF (trên các phụ thuộc giả định) không chứng minh mô hình đúng.
2. Xác định grain phù hợp và khóa ứng viên.
3. Đề xuất cấu trúc để lưu một đơn có nhiều chuyến, kể cả chưa giao chuyến nào.
4. Nêu một kiểm thử hệ thống phải vượt qua.

<details>
<summary>Gợi ý lời giải bài 1</summary>

Trong bảng cũ, **order_id** là khóa chính nên chỉ lưu được **một bản ghi giao trên một đơn**, bất kể nó đạt dạng chuẩn nào dưới giả định ấy. Quy tắc nghiệp vụ mới bác bỏ phụ thuộc **order_id → delivered_at, delivered_address** trong quan hệ giao hàng.

Nếu mỗi chuyến thuộc một đơn, có thể tạo:

~~~text
orders(order_id, ...)
shipments(
    order_id,
    shipment_no,
    delivered_at,
    ship_to_address_snapshot,
    PRIMARY KEY(order_id, shipment_no),
    FOREIGN KEY(order_id) REFERENCES orders(order_id)
)
~~~

**shipments** có grain một chuyến giao của đơn. Một đơn có thể có 0, 1 hoặc nhiều hàng shipments. Kiểm thử: tạo một đơn, thêm hai chuyến có ngày/địa chỉ khác nhau, đọc lại đủ hai chuyến mà không ghi đè hoặc buộc xóa đơn.

</details>

### Bài 2 — Thuật ngữ “khách hàng hoạt động”

Phòng marketing yêu cầu danh sách **active customers**. Nhóm phát triển định thêm **customers.is_active BOOLEAN** và cập nhật thủ công mỗi tháng. Phòng kinh doanh lại hiểu “active” là **đã đặt ít nhất một đơn hợp lệ trong 90 ngày gần nhất**, còn bộ phận hỗ trợ muốn lọc **tài khoản chưa bị khóa**.

**Yêu cầu:**

1. Tại sao một cột **is_active** không đủ biểu diễn cả hai nghĩa?
2. Viết hai thuật ngữ khác nhau, gồm định nghĩa và phạm vi thời gian.
3. Nếu marketing muốn số liệu theo từng ngày trong quá khứ, cần hỏi thêm gì trước khi thiết kế?

<details>
<summary>Gợi ý lời giải bài 2</summary>

Hai khái niệm là:

- **account_enabled:** tài khoản hiện tại được phép truy cập hoặc giao dịch theo quy tắc khóa/mở khóa. Có thể là trạng thái quản lý tài khoản, cần định nghĩa lịch sử nếu muốn xem thời điểm trước.
- **purchased_in_last_90_days(as_of):** tồn tại ít nhất một **đơn được tính là hợp lệ** có **placed_at** trong 90 ngày trước thời điểm **as_of**, theo múi giờ, ranh giới thời gian và chính sách loại đơn hủy được xác nhận.

Nếu cần tính lại tại các ngày quá khứ, cần dữ liệu sự kiện đặt đơn, thời gian hiệu lực của quy tắc và dữ liệu hủy/điều chỉnh liên quan. Một **BOOLEAN** hiện hành không đủ để khôi phục mọi trạng thái lịch sử.

</details>

### Bài 3 — Khóa ngoại đúng nhưng tổng số lượng sai

Đơn O1001 có một dòng đặt **3 chiếc**. Chuyến 1 xuất 2 chiếc, chuyến 2 xuất 1 chiếc. Một tiến trình khác muốn xuất thêm một chiếc ở chuyến 3.

**Yêu cầu:**

1. Vì sao **PRIMARY KEY**, **FOREIGN KEY** và **CHECK(shipped_quantity > 0)** đều có thể hợp lệ khi tổng xuất vượt 3?
2. Ràng buộc nghiệp vụ nào cần bảo vệ?
3. Nêu một phương án ngăn hai tiến trình đồng thời cùng cấp phần lượng cuối.

<details>
<summary>Gợi ý lời giải bài 3</summary>

Các ràng buộc hiện có chỉ kiểm tra **mỗi hàng phân bổ** có khóa duy nhất, tham chiếu hợp lệ và lượng dương. Chúng không cộng tất cả lượng giao của một dòng để so sánh với lượng đặt.

Bất biến cần bảo vệ:

~~~text
SUM(shipped_quantity theo order_id và line_no)
  <= ordered_quantity của đúng dòng đó
~~~

Một cách là mọi luồng sửa lượng xuất phải chạy trong giao dịch, **khóa hàng order_lines** tương ứng, tính tổng hiện tại và chỉ ghi nếu không vượt giới hạn. Phải đảm bảo toàn bộ các đường ghi và thay đổi số lượng đặt cùng tuân thủ giao thức; nếu không, cần ràng buộc/procedure cấp cơ sở dữ liệu và kiểm thử cạnh tranh ghi.

</details>

### Bài 4 — Phát biểu “doanh thu đơn hàng”

Một báo cáo dùng:

~~~text
SUM(order_lines.ordered_quantity * order_lines.unit_price_vnd_at_order)
~~~

và đặt tên là **revenue**. Hệ thống có đơn chưa thanh toán, đơn hủy sau khi đặt, giao một phần và hoàn tiền.

**Yêu cầu:** nêu ít nhất bốn câu hỏi phải làm rõ để biết biểu thức trên có đại diện đúng cho **doanh thu** hay không. Đề xuất tên an toàn hơn cho giá trị đang tính.

**Hướng giải:** hỏi thời điểm ghi nhận doanh thu, điều kiện loại đơn hủy/chưa thanh toán, cách xử lý giao một phần, trả hàng/hoàn tiền, thuế, khuyến mại, vận chuyển và kỳ kế toán. Biểu thức trên chỉ phản ánh **tổng giá trị dòng hàng đã đặt trước các điều chỉnh khác** theo đơn giá chốt; tên như **ordered_merchandise_value_vnd** rõ hơn **revenue**. Để tính doanh thu kế toán cần quy tắc ghi nhận đã được xác nhận bởi nghiệp vụ tài chính.

## 12. Checklist bàn giao thiết kế

Trước khi một lược đồ được xem là sẵn sàng để triển khai, người thiết kế và các bên nghiệp vụ nên thống nhất:

| Nội dung | Bằng chứng tối thiểu |
| --- | --- |
| Thuật ngữ | Từ điển thuật ngữ, chủ sở hữu, các nghĩa bị loại trừ |
| Grain | Câu mô tả chính xác “một hàng là gì” cho mỗi bảng |
| Cardinality | Các quan hệ 0..1, 1..n, n..m và ngoại lệ |
| Khóa và phạm vi | Mọi khóa ứng viên, tính duy nhất theo tổ chức/kỳ/thời gian |
| Phụ thuộc hàm và các dạng chuẩn | Bộ quy tắc đã xác nhận, phân rã có giải thích và kiểm tra lossless |
| Thời gian | Trường hiện hành, ảnh chụp lịch sử, hiệu lực và thời điểm ghi nhận |
| Bất biến | Quy tắc theo hàng, theo nhóm, theo trạng thái và theo giao dịch |
| Kiểm thử | Ca hợp lệ, ca bị từ chối, ca cạnh tranh ghi, ca thay đổi lịch sử |
| Truy vấn/chỉ số | Công thức, nguồn, đơn vị, múi giờ, điều kiện lọc và đối soát |
| Tiến hóa | Kịch bản thay đổi yêu cầu, cách chuyển dữ liệu, tương thích và rollback |

## 13. Kết luận

**Chuẩn hóa cấu trúc chỉ đúng khi các phụ thuộc và khóa được xây dựng từ thuật ngữ, grain và quy tắc nghiệp vụ đúng.** Các dạng chuẩn giúp giảm dư thừa, phát hiện phụ thuộc không phù hợp và thiết kế phép phân rã có thể kiểm chứng; chúng không quyết định thế nào là một khách hàng, một chuyến giao, một khoản doanh thu hay một trạng thái hoàn tất.

Trong ví dụ đơn hàng, phân biệt **đơn**, **dòng hàng**, **chuyến giao** và **phần hàng được giao** cho phép biểu diễn giao nhiều đợt, địa chỉ theo chuyến và số lượng phân bổ mà một giả định “mỗi đơn có một chuyến” sẽ loại bỏ. Sau khi mô hình đúng, hệ thống vẫn cần kiểm tra **tổng lượng xuất**, **quy tắc chuyển trạng thái**, **phạm vi khóa**, **thời gian hiệu lực** và **ghi đồng thời**.

Thứ tự làm việc đáng tin cậy là: **định nghĩa thuật ngữ → xác nhận bất biến và ngoại lệ → xác định grain/khóa/phụ thuộc → chuẩn hóa và ràng buộc → kiểm thử dữ liệu cùng hành vi → tối ưu cấu trúc vật lý và mô hình đọc**. Đây là nền tảng để xây dựng mô hình quan hệ, document, đồ thị hoặc phân tích vừa dễ tiến hóa vừa phản ánh đúng thế giới nghiệp vụ.
