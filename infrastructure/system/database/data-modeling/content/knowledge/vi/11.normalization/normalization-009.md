# Quy trình chuẩn hóa từng bước từ bảng đơn hàng chưa hợp lý

Một lược đồ đơn hàng ban đầu thường được thiết kế theo màn hình nhập liệu: **một đơn có khách hàng, địa chỉ giao, danh sách sản phẩm, số lượng, giá và danh mục**. Nếu sao chép nguyên màn hình thành một bảng lớn, ta dễ gặp các bất thường: đổi tên khách hàng phải sửa nhiều dòng, xóa dòng hàng cuối làm mất đơn hàng, thay tên danh mục phải cập nhật nhiều sản phẩm, hoặc không thể tạo một đơn chưa có sản phẩm.

**Chuẩn hóa dữ liệu** là quá trình xác định **mỗi sự thật thuộc về đối tượng nào**, viết ra các **phụ thuộc hàm**, tìm **khóa ứng viên**, rồi phân rã quan hệ để giảm dư thừa mà không làm mất thông tin. Bài thuộc chương **Chuẩn hóa** của mô-đun **DATABASE_DATA_MODELING**, tập trung vào một ví dụ xuyên suốt từ cấu trúc chưa hợp lý đến các quan hệ **1NF → 2NF → 3NF**, đồng thời phân biệt dữ liệu nghiệp vụ hiện hành với **ảnh chụp lịch sử của giao dịch**.

Sau bài học, người học có thể:

- Xác định *grain* (đơn vị ý nghĩa của một hàng) cho đơn hàng và dòng hàng.
- Nhận diện nhóm lặp, phụ thuộc bộ phận, phụ thuộc bắc cầu và bất thường thêm/sửa/xóa.
- Phân rã từng bước, đặt **PRIMARY KEY**, **FOREIGN KEY**, **UNIQUE**, **CHECK** phù hợp.
- Đối chiếu phép nối và kiểm tra dữ liệu khi chuyển từ cấu trúc cũ sang lược đồ mới.
- Giải thích vì sao giá tại thời điểm mua hoặc địa chỉ giao lúc đặt hàng **không nhất thiết là dữ liệu dư thừa sai**.

## 1. Bắt đầu bằng yêu cầu nghiệp vụ, không bắt đầu bằng lệnh CREATE TABLE

Giả sử hệ thống bán hàng tại Việt Nam có các quy tắc:

1. Một **đơn hàng** có mã **order_id** duy nhất, ngày đặt và một khách hàng đặt.
2. Một **khách hàng** có mã **customer_id** duy nhất, tên và một số điện thoại liên hệ **hiện hành** trong phạm vi ví dụ. Một khách hàng có nhiều đơn.
3. Một đơn có **nhiều dòng hàng**. **line_no** đánh số dòng trong từng đơn, nên hai đơn khác nhau có thể cùng **line_no = 1**.
4. Một **sản phẩm** có mã **product_id** duy nhất, tên hiện hành và thuộc một danh mục hiện hành. Một danh mục có nhiều sản phẩm.
5. Mỗi dòng hàng có **một sản phẩm**, **quantity** dương và **unit_price_vnd_at_order** là đơn giá VND đã chốt cho **chính dòng ấy**. Hai đơn có thể mua cùng sản phẩm với đơn giá khác nhau.
6. **ship_to_address_at_order** là địa chỉ giao đã chốt lúc đặt đơn, **không phải** địa chỉ liên hệ hiện tại trong hồ sơ khách hàng.
7. Cùng một sản phẩm **có thể xuất hiện trên nhiều dòng của một đơn**, chẳng hạn do chương trình giá hoặc điều kiện giao khác nhau. Vì vậy không mặc định **(order_id, product_id)** là khóa.
8. Đơn và sản phẩm tồn tại độc lập: có thể tạo đơn chưa có dòng; có thể khai báo sản phẩm chưa được đặt.

Một màn hình nhập đơn có thể tạo dữ liệu thô dạng:

~~~json
{
  "order_id": "O1001",
  "placed_on": "2026-11-20",
  "customer": {
    "customer_id": "C01",
    "customer_name": "An",
    "customer_phone": "+84901234567"
  },
  "ship_to_address_at_order": "12 Nguyen Hue, TP.HCM",
  "items": [
    {
      "line_no": 1,
      "product_id": "P10",
      "product_name": "Ban phim",
      "category_id": "CAT10",
      "category_name": "Ngoai vi",
      "quantity": 2,
      "unit_price_vnd_at_order": 300000
    },
    {
      "line_no": 2,
      "product_id": "P20",
      "product_name": "Chuot",
      "category_id": "CAT10",
      "category_name": "Ngoai vi",
      "quantity": 1,
      "unit_price_vnd_at_order": 200000
    }
  ]
}
~~~

JSON này **không tự nó là thiết kế sai**: trong một API hoặc cơ sở dữ liệu document, đơn hàng nhúng các dòng có thể là lựa chọn hợp lý. Vấn đề xuất hiện khi ta cố quản lý nhiều sự thật độc lập bằng một chuỗi hoặc một ô SQL duy nhất mà không có khóa, ràng buộc và thao tác riêng cho mỗi dòng. Trong bài này, mục tiêu là **lược đồ quan hệ** và cách kiểm chứng những bất biến của nó.

### 1.1. Bảng ban đầu chưa hợp lý

Giả sử người thiết kế đặt tất cả thông tin vào một bảng tưởng tượng **order_input_raw**:

~~~text
order_id
placed_on
customer_id
customer_name
customer_phone
ship_to_address_at_order
items = "P10 x 2 @ 300000; P20 x 1 @ 200000; ..."
~~~

Nếu **items** là danh sách các dòng cần tìm kiếm, thêm, xóa và kiểm tra riêng, một cột chứa cả danh sách không thể trực tiếp khai báo khóa cho từng dòng hoặc ràng buộc **quantity > 0** cho từng phần tử bằng kiểu cột số thông thường. Việc dùng dấu phân cách còn tạo khó khăn khi dữ liệu thật có dấu phân cách, giá trị thiếu hoặc định dạng không nhất quán.

Đây là điểm khởi đầu để thực hành đưa **nhóm lặp** thành các hàng độc lập.

## 2. Bước 1 — Đưa dữ liệu về 1NF: mỗi dòng hàng là một hàng quan hệ

**Dạng chuẩn thứ nhất (1NF)** yêu cầu giá trị thuộc tính được biểu diễn theo miền dữ liệu đã chọn; trong cách thực hành mô hình hóa, không giấu các phần tử nghiệp vụ cần quản lý độc lập trong một ô. “Nguyên tử” phụ thuộc vào **miền giá trị và nhu cầu nghiệp vụ**: ngày đặt là một giá trị **DATE**, còn tập dòng hàng là nhiều sự thật cần khóa riêng.

Sau khi phân tách danh sách **items**, bảng **order_lines_flat** có *grain* **một dòng hàng trong một đơn**. Ta giữ cả các cột mô tả đơn, khách hàng và sản phẩm để thấy những vấn đề chưa được giải quyết:

~~~text
order_lines_flat(
    order_id,
    line_no,
    placed_on,
    customer_id,
    customer_name,
    customer_phone,
    ship_to_address_at_order,
    product_id,
    product_name,
    category_id,
    category_name,
    quantity,
    unit_price_vnd_at_order
)
~~~

Bảng dữ liệu rút gọn dưới đây bỏ bớt những cột dài để dễ đọc; các cột bị ẩn vẫn thuộc cấu trúc vừa liệt kê:

| order_id | line_no | customer_id | customer_name | product_id | product_name | category_id | quantity | unit_price_vnd_at_order |
| --- | ---: | --- | --- | --- | --- | --- | ---: | ---: |
| O1001 | 1 | C01 | An | P10 | Bàn phím | CAT10 | 2 | 300000 |
| O1001 | 2 | C01 | An | P20 | Chuột | CAT10 | 1 | 200000 |
| O1002 | 1 | C01 | An | P10 | Bàn phím | CAT10 | 1 | 290000 |
| O1002 | 2 | C01 | An | P30 | Màn hình | CAT20 | 1 | 2500000 |
| O1003 | 1 | C02 | Bình | P20 | Chuột | CAT10 | 3 | 210000 |

**Khóa ứng viên** theo giả định ở mục 1 là **(order_id, line_no)**: nó định danh đúng một dòng. Chỉ **order_id** không đủ vì một đơn có nhiều dòng; chỉ **line_no** không đủ vì mọi đơn có thể có dòng số 1. Tập có thêm **product_id** là siêu khóa nhưng không tối thiểu. Không dùng **(order_id, product_id)** làm khóa vì nghiệp vụ cho phép cùng một sản phẩm xuất hiện ở nhiều dòng của một đơn.

Lược đồ SQL mô tả trạng thái 1NF, **chưa phải thiết kế cuối**:

~~~sql
CREATE TABLE order_lines_flat (
    order_id VARCHAR(10) NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    placed_on DATE NOT NULL,
    customer_id VARCHAR(10) NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    customer_phone VARCHAR(20),
    ship_to_address_at_order TEXT NOT NULL,
    product_id VARCHAR(10) NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    category_id VARCHAR(10) NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd_at_order BIGINT NOT NULL
        CHECK (unit_price_vnd_at_order >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Các cột đã mang giá trị riêng, có khóa chính và **CHECK** cho số lượng/đơn giá. Nhưng dữ liệu **vẫn dư thừa**: thông tin của đơn lặp theo từng dòng, tên khách hàng lặp theo nhiều đơn, tên sản phẩm và danh mục lặp theo các dòng bán.

### 2.1. Những bất thường vẫn còn sau 1NF

- **Sửa:** đổi tên hiện hành của sản phẩm P10 cần cập nhật mọi dòng có P10, nếu bảng gộp được dùng làm nguồn cho tên hiện hành.
- **Thêm:** không thể khai báo một đơn mới chưa có sản phẩm, do khóa buộc có **line_no** và các cột sản phẩm.
- **Xóa:** xóa dòng cuối cùng của O1003 đồng thời làm mất ngày đặt, mã khách hàng và địa chỉ giao của đơn O1003.

**Kết luận bước 1:** biểu diễn được từng dòng hàng bằng một hàng quan hệ là cần thiết, **nhưng chưa đủ để đạt thiết kế chuẩn hóa tốt**.

## 3. Bước 2 — Xác định phụ thuộc hàm và khóa ứng viên

Phụ thuộc hàm **X → Y** là quy tắc: trong mọi trạng thái dữ liệu hợp lệ, một giá trị X xác định tối đa một giá trị Y. Không nên suy phụ thuộc chỉ vì các giá trị trong một vài hàng tình cờ giống nhau.

Từ yêu cầu nghiệp vụ:

~~~text
order_id
  -> placed_on, customer_id, ship_to_address_at_order

customer_id
  -> customer_name, customer_phone

product_id
  -> product_name, category_id

category_id
  -> category_name

(order_id, line_no)
  -> product_id, quantity, unit_price_vnd_at_order
~~~

Các phụ thuộc bắc cầu cũng có thể suy ra, chẳng hạn:

~~~text
order_id -> customer_id -> customer_name
product_id -> category_id -> category_name
~~~

Mức hạt dữ liệu quyết định sự khác biệt:

- **order_id → placed_on** vì đơn có một ngày đặt.
- **customer_id → customer_name** vì đang mô hình hóa **tên hiện hành** của khách hàng.
- **product_id → product_name** vì đang mô hình hóa **tên hiện hành** của sản phẩm.
- **(order_id, line_no) → unit_price_vnd_at_order** vì đơn giá tại giao dịch thuộc **dòng hàng**. **Không** giả định **product_id → unit_price_vnd_at_order**: cùng sản phẩm có thể có giá khác nhau giữa các lần mua.
- **order_id → ship_to_address_at_order** vì mỗi đơn trong ví dụ có một địa chỉ giao đã chốt. **Không** gán **customer_id → ship_to_address_at_order**: một khách hàng có thể đặt nhiều đơn đến các địa chỉ khác nhau.

~~~mermaid
flowchart TD
    K["Khóa (order_id, line_no)"]
    O["order_id"]
    C["customer_id"]
    P["product_id"]
    CAT["category_id"]
    OD["placed_on, ship_to_address_at_order"]
    CN["customer_name, customer_phone"]
    PN["product_name"]
    CT["category_name"]
    LV["quantity, unit_price_vnd_at_order"]
    K -->|"chứa"| O
    K --> P
    K --> LV
    O --> OD
    O --> C
    C --> CN
    P --> PN
    P --> CAT
    CAT --> CT
~~~

Một **phụ thuộc đầy đủ vào khóa** đòi hỏi toàn bộ khóa mới xác định thuộc tính. Một **phụ thuộc bộ phận** xảy ra khi một **tập con thực sự** của khóa ứng viên đã xác định được thuộc tính không nguyên tố. Trong bảng 1NF có khóa **(order_id, line_no)**, các thuộc tính như **placed_on** và **customer_id** chỉ cần **order_id**; do đó chúng phụ thuộc bộ phận.

## 4. Bước 3 — Đạt 2NF: tách thông tin đơn và từng dòng

**2NF** yêu cầu quan hệ đã ở 1NF và **mọi thuộc tính không nguyên tố phụ thuộc đầy đủ vào mọi khóa ứng viên**. Đặc biệt cần xem xét các khóa ghép.

Từ phụ thuộc:

~~~text
order_id -> placed_on, customer_id, ship_to_address_at_order
~~~

ta chuyển phần thuộc về **đơn hàng** vào bảng riêng. Một lược đồ trung gian:

~~~text
orders_2nf(
    order_id PRIMARY KEY,
    placed_on,
    customer_id,
    customer_name,
    customer_phone,
    ship_to_address_at_order
)

order_lines_2nf(
    order_id,
    line_no,
    product_id,
    product_name,
    category_id,
    category_name,
    quantity,
    unit_price_vnd_at_order,
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES orders_2nf(order_id)
)
~~~

**orders_2nf** có *grain* một đơn hàng; **order_lines_2nf** có *grain* một dòng hàng. Nhờ vậy, đơn có thể tồn tại ngay khi chưa có dòng, và xóa dòng cuối không xóa bản ghi đơn.

Trong **orders_2nf**, khóa ứng viên **order_id** chỉ có một thuộc tính, nên không có phụ thuộc bộ phận thông thường vào khóa ghép. Trong **order_lines_2nf**, các cột mô tả sản phẩm có thể bị xác định qua **product_id**, nhưng **product_id không phải tập con của khóa (order_id,line_no)**. Đây là vấn đề phụ thuộc bắc cầu cho bước 3NF, **không phải phụ thuộc bộ phận của 2NF**.

### 4.1. 2NF khắc phục gì và chưa khắc phục gì?

| Thay đổi | Sau bước 2NF |
| --- | --- |
| Tạo đơn O1004 chưa có dòng hàng | Có thể thêm vào **orders_2nf** |
| Xóa dòng cuối của O1003 | **orders_2nf** vẫn giữ ngày đặt/khách hàng/địa chỉ |
| Đổi tên hiện hành của khách hàng C01 | Vẫn phải sửa ở nhiều đơn của C01 |
| Đổi tên hiện hành của sản phẩm P10 | Vẫn phải sửa ở nhiều dòng hàng có P10 |
| Đổi tên danh mục CAT10 | Vẫn có thể phải sửa rất nhiều dòng hàng |

Vì thế **đạt 2NF không có nghĩa đã loại bỏ hết dư thừa**.

### 4.2. Vì sao tách hai bảng không làm mất thông tin?

Quan hệ gốc có khóa **(order_id,line_no)**. Giao của hai tập thuộc tính trong phép phân rã là **{order_id}**, và **order_id** xác định toàn bộ các thuộc tính của **orders_2nf** theo các phụ thuộc đã giả định. Theo tiêu chí phân rã nhị phân, phép tách là **nối không mất thông tin (lossless join)** trên các trạng thái gốc hợp lệ.

Khi nối từng dòng với đơn theo **order_id**, mỗi dòng khớp đúng một đơn. Bảng đơn có thể lưu **đơn chưa có dòng** mà không tạo dòng hàng giả; muốn xem các đơn này, truy vấn bắt đầu từ bảng đơn và dùng **LEFT JOIN**.

## 5. Bước 4 — Đạt 3NF: đưa tên khách hàng, sản phẩm và danh mục về đúng chủ sở hữu

**3NF** kiểm soát các phụ thuộc hàm không tầm thường **X → A**: X phải là **siêu khóa** hoặc A phải là **thuộc tính nguyên tố** (thuộc ít nhất một khóa ứng viên). Với các bảng trung gian ở trên, dấu hiệu quen thuộc là **phụ thuộc bắc cầu** từ khóa sang thông tin của đối tượng khác.

Trong bảng **orders_2nf**:

~~~text
order_id -> customer_id -> customer_name, customer_phone
~~~

**customer_id** không phải siêu khóa của bảng đơn vì một khách hàng có thể đặt nhiều đơn. **customer_name** và **customer_phone** không thuộc khóa ứng viên nào của bảng đơn. Vì vậy, phụ thuộc **customer_id → customer_name, customer_phone** vi phạm 3NF của **orders_2nf**.

Trong **order_lines_2nf**:

~~~text
(order_id, line_no) -> product_id
product_id         -> product_name, category_id
category_id        -> category_name
~~~

**product_id** không phải siêu khóa của bảng dòng hàng; tên sản phẩm và mã danh mục là dữ liệu hiện hành thuộc về sản phẩm. **category_id** cũng không xác định một dòng hàng, còn **category_name** thuộc về danh mục. Do đó hai cấp thông tin này cần tách theo nghiệp vụ.

### 5.1. Lược đồ mục tiêu

~~~text
customers(
    customer_id PRIMARY KEY,
    customer_name,
    customer_phone
)

categories(
    category_id PRIMARY KEY,
    category_name
)

products(
    product_id PRIMARY KEY,
    product_name,
    category_id REFERENCES categories(category_id)
)

orders(
    order_id PRIMARY KEY,
    placed_on,
    customer_id REFERENCES customers(customer_id),
    ship_to_address_at_order
)

order_lines(
    order_id REFERENCES orders(order_id),
    line_no,
    product_id REFERENCES products(product_id),
    quantity,
    unit_price_vnd_at_order,
    PRIMARY KEY (order_id, line_no)
)
~~~

Mỗi bảng có một *grain*:

| Bảng | Một hàng là gì? | Khóa ứng viên chọn làm khóa chính |
| --- | --- | --- |
| **customers** | Một khách hàng | customer_id |
| **categories** | Một danh mục sản phẩm | category_id |
| **products** | Một sản phẩm | product_id |
| **orders** | Một đơn hàng | order_id |
| **order_lines** | Một dòng hàng của một đơn | (order_id, line_no) |

Tên khách hàng được cập nhật tại **customers**; tên sản phẩm tại **products**; tên danh mục tại **categories**. Bản ghi **orders** chứa khóa ngoại tới khách hàng, còn **order_lines** chứa khóa ngoại tới đơn và sản phẩm.

### 5.2. Sơ đồ quan hệ sau chuẩn hóa

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : "đặt"
    ORDERS ||--o{ ORDER_LINES : "gồm"
    PRODUCTS ||--o{ ORDER_LINES : "xuất hiện trong"
    CATEGORIES ||--o{ PRODUCTS : "phân loại"
    CUSTOMERS {
        varchar customer_id PK
        varchar customer_name
        varchar customer_phone
    }
    ORDERS {
        varchar order_id PK
        date placed_on
        varchar customer_id FK
        text ship_to_address_at_order
    }
    ORDER_LINES {
        varchar order_id PK, FK
        integer line_no PK
        varchar product_id FK
        integer quantity
        bigint unit_price_vnd_at_order
    }
    PRODUCTS {
        varchar product_id PK
        varchar product_name
        varchar category_id FK
    }
    CATEGORIES {
        varchar category_id PK
        varchar category_name
    }
~~~

Từ lược đồ này, việc tạo một khách hàng mới **không đòi hỏi** phải có đơn; tạo sản phẩm mới **không đòi hỏi** phải có dòng hàng; xóa một dòng hàng **không làm mất** bản ghi sản phẩm, khách hàng hay danh mục.

### 5.3. Các phụ thuộc được đặt vào đúng quan hệ

~~~text
customers:
  customer_id -> customer_name, customer_phone

categories:
  category_id -> category_name

products:
  product_id -> product_name, category_id

orders:
  order_id -> placed_on, customer_id, ship_to_address_at_order

order_lines:
  (order_id, line_no)
    -> product_id, quantity, unit_price_vnd_at_order
~~~

Mỗi phụ thuộc được xác định bởi **khóa của bảng chứa nó** theo các giả định đã cho. Vì vậy, các quan hệ này đạt **3NF**, và theo đúng tập phụ thuộc hàm đơn giản ở đây chúng cũng có thể đạt **BCNF**. Không suy kết luận 4NF hoặc 5NF nếu chưa kiểm tra thêm phụ thuộc đa trị hoặc phụ thuộc nối của nghiệp vụ.

**Bảo toàn phụ thuộc hàm:** các quy tắc chính được kiểm tra ngay trong một bảng thành phần, nhờ khóa hoặc các ràng buộc phù hợp. **Nối không mất thông tin:** mỗi dòng hàng tham chiếu tới đúng một đơn, mỗi đơn tới đúng một khách hàng, mỗi dòng tới đúng một sản phẩm, mỗi sản phẩm tới đúng một danh mục. Phép nối theo khóa ngoại tái tạo được các hàng bán hàng của dữ liệu gốc hợp lệ, trong khi những thực thể độc lập vẫn tồn tại nếu chưa có giao dịch.

## 6. Bước 5 — Triển khai lược đồ chuẩn hóa bằng PostgreSQL

Ví dụ dưới đây có thể thực hiện trên một cơ sở dữ liệu trống hoặc schema dành riêng cho bài thực hành. Tên bảng là tên **cuối cùng**, không còn hậu tố **_2nf**.

### 6.1. Tạo bảng và ràng buộc

~~~sql
CREATE TABLE customers (
    customer_id VARCHAR(10) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    customer_phone VARCHAR(20)
);

CREATE TABLE categories (
    category_id VARCHAR(10) PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL
);

CREATE TABLE products (
    product_id VARCHAR(10) PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    category_id VARCHAR(10) NOT NULL
        REFERENCES categories(category_id)
);

CREATE TABLE orders (
    order_id VARCHAR(10) PRIMARY KEY,
    placed_on DATE NOT NULL,
    customer_id VARCHAR(10) NOT NULL
        REFERENCES customers(customer_id),
    ship_to_address_at_order TEXT NOT NULL
);

CREATE TABLE order_lines (
    order_id VARCHAR(10) NOT NULL
        REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(10) NOT NULL
        REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd_at_order BIGINT NOT NULL
        CHECK (unit_price_vnd_at_order >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

**Vì sao có các ràng buộc này?**

- **PRIMARY KEY** định danh duy nhất từng thực thể hoặc dòng hàng.
- **FOREIGN KEY** ngăn đăng ký dòng cho đơn không tồn tại, gắn sản phẩm không tồn tại, hay gắn sản phẩm vào danh mục không tồn tại.
- **NOT NULL** bảo vệ những thông tin bắt buộc theo bài toán.
- **CHECK (quantity > 0)** ngăn số lượng bằng 0 hoặc âm; nếu có hàng trả lại, cần mô hình nghiệp vụ trả hàng hoặc điều chỉnh riêng thay vì ngầm dùng số lượng âm.
- **CHECK (unit_price_vnd_at_order >= 0)** ngăn giá âm. Giá 0 vẫn hợp lệ nếu doanh nghiệp có hàng tặng; nếu không, đổi điều kiện theo nghiệp vụ.
- Không thêm **UNIQUE(order_id, product_id)** vì một sản phẩm có thể xuất hiện trên nhiều dòng của một đơn. Chỉ khóa **(order_id, line_no)** là đủ theo giả định đã chọn.

Trong ví dụ, các khóa ngoại dùng hành vi mặc định của PostgreSQL. Vì vậy không tự động xóa dòng hàng chỉ khi xóa đơn hoặc sản phẩm; muốn thiết kế **ON DELETE CASCADE**, **RESTRICT** hoặc lưu trạng thái ngừng sử dụng cần đưa ra quy tắc vòng đời rõ ràng.

### 6.2. Nạp dữ liệu

~~~sql
INSERT INTO customers
    (customer_id, customer_name, customer_phone)
VALUES
    ('C01', 'An',   '+84901234567'),
    ('C02', 'Bình', '+84907654321');

INSERT INTO categories (category_id, category_name) VALUES
    ('CAT10', 'Ngoại vi'),
    ('CAT20', 'Màn hình');

INSERT INTO products (product_id, product_name, category_id) VALUES
    ('P10', 'Bàn phím', 'CAT10'),
    ('P20', 'Chuột',    'CAT10'),
    ('P30', 'Màn hình', 'CAT20');

INSERT INTO orders
    (order_id, placed_on, customer_id, ship_to_address_at_order)
VALUES
    ('O1001', DATE '2026-11-20', 'C01',
     '12 Nguyen Hue, TP.HCM'),
    ('O1002', DATE '2026-11-21', 'C01',
     '99 Le Loi, TP.HCM'),
    ('O1003', DATE '2026-11-22', 'C02',
     '7 Tran Hung Dao, Da Nang');

INSERT INTO order_lines
    (order_id, line_no, product_id, quantity, unit_price_vnd_at_order)
VALUES
    ('O1001', 1, 'P10', 2,  300000),
    ('O1001', 2, 'P20', 1,  200000),
    ('O1002', 1, 'P10', 1,  290000),
    ('O1002', 2, 'P30', 1, 2500000),
    ('O1003', 1, 'P20', 3,  210000);
~~~

Từ dữ liệu này, C01 đặt hai đơn có **hai địa chỉ giao khác nhau**; P10 được mua ở hai mức giá **300000 VND** và **290000 VND**. Hai điều đó **không mâu thuẫn** với việc C01 chỉ có một bản ghi hồ sơ khách hàng, hay P10 chỉ có một bản ghi danh mục sản phẩm.

### 6.3. Truy vấn đọc lại bảng đơn hàng cho giao diện

~~~sql
SELECT
    o.order_id,
    o.placed_on,
    c.customer_id,
    c.customer_name,
    o.ship_to_address_at_order,
    ol.line_no,
    p.product_id,
    p.product_name,
    cat.category_name,
    ol.quantity,
    ol.unit_price_vnd_at_order,
    ol.quantity::numeric * ol.unit_price_vnd_at_order
        AS line_total_vnd
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
JOIN order_lines AS ol
    ON ol.order_id = o.order_id
JOIN products AS p
    ON p.product_id = ol.product_id
JOIN categories AS cat
    ON cat.category_id = p.category_id
ORDER BY o.order_id, ol.line_no;
~~~

Truy vấn tái tạo dạng hiển thị **mỗi dòng hàng một hàng kết quả**. Việc các cột khách hàng/sản phẩm lặp lại trong **kết quả SELECT** là bình thường; khác với bảng gộp, chúng không bị sao chép làm dữ liệu nguồn ở nhiều hàng.

### 6.4. Tính tổng tiền từng đơn mà không lưu trùng

Với ví dụ chỉ tính **số lượng × đơn giá đã chốt**, chưa xét giảm giá, thuế hay phí vận chuyển:

~~~sql
SELECT
    o.order_id,
    COUNT(ol.line_no) AS line_count,
    COALESCE(
        SUM(ol.quantity::numeric * ol.unit_price_vnd_at_order),
        0
    ) AS merchandise_total_vnd
FROM orders AS o
LEFT JOIN order_lines AS ol
    ON ol.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Kết quả dự kiến:

| order_id | line_count | merchandise_total_vnd |
| --- | ---: | ---: |
| O1001 | 2 | 800000 |
| O1002 | 2 | 2790000 |
| O1003 | 1 | 630000 |

**COUNT(ol.line_no)** thay vì **COUNT(*)** giúp đơn không có dòng hàng nhận **line_count = 0** khi dùng **LEFT JOIN**. Chuyển **quantity** sang **numeric** trước phép nhân tránh dựa vào giới hạn của phép nhân số nguyên 32/64 bit khi tổng tiền rất lớn.

### 6.5. Thử lại các bất thường

**Đổi tên hiện hành của khách hàng ở đúng một nơi:**

~~~sql
UPDATE customers
SET customer_name = 'An Nguyễn'
WHERE customer_id = 'C01';
~~~

Cả O1001 và O1002 khi truy vấn cùng khách hàng sẽ hiển thị tên hiện hành mới. Không cần sửa từng đơn.

**Đổi tên danh mục ở đúng một nơi:**

~~~sql
UPDATE categories
SET category_name = 'Thiết bị ngoại vi'
WHERE category_id = 'CAT10';
~~~

Tất cả sản phẩm thuộc CAT10 sẽ tham chiếu tên hiện hành mới.

**Tạo đơn chưa có dòng:**

~~~sql
INSERT INTO orders
    (order_id, placed_on, customer_id, ship_to_address_at_order)
VALUES
    ('O1004', DATE '2026-11-22', 'C01',
     '12 Nguyen Hue, TP.HCM');
~~~

**Xóa một dòng mà không xóa đơn:**

~~~sql
DELETE FROM order_lines
WHERE order_id = 'O1003' AND line_no = 1;

SELECT order_id, placed_on, customer_id
FROM orders
WHERE order_id = 'O1003';
-- O1003 vẫn còn nguyên trong bảng orders.
~~~

Những câu lệnh này minh họa các thao tác độc lập; nếu chạy tuần tự trên dữ liệu mẫu, tổng tiền và số dòng sau khi xóa sẽ thay đổi đúng theo thao tác.

## 7. Bước 6 — Di chuyển dữ liệu cũ và kiểm chứng tính nhất quán

Trong dự án thực tế, khó nhất thường không phải viết năm lệnh **CREATE TABLE** mà là chuyển dữ liệu cũ sang các bảng mới **không mất dòng hàng, không tạo thực thể trùng và không hợp thức hóa dữ liệu đang mâu thuẫn**.

Một quy trình phù hợp:

1. **Chốt đặc tả nghiệp vụ.** Xác nhận một đơn có thể chưa có dòng hay không, mỗi khách có bao nhiêu số điện thoại, sản phẩm có được lặp dòng và các cột tên/giá là hiện hành hay lịch sử.
2. **Đưa dữ liệu thô vào staging.** Phân tích danh sách item ở bước nhập; với mỗi phần tử tạo một hàng, chuẩn hóa mã và kiểu dữ liệu, ghi lại bản ghi lỗi.
3. **Kiểm tra khóa.** Trong staging, mỗi **(order_id, line_no)** phải duy nhất và không thiếu thành phần khóa.
4. **Kiểm tra phụ thuộc hàm.** Một **customer_id** có đang mang hai tên hiện hành khác nhau? Một **product_id** bị gán hai danh mục hiện hành? Một **order_id** có nhiều ngày đặt hay khách hàng không?
5. **Giải quyết dữ liệu mâu thuẫn trước khi chèn.** Xác định nguồn đúng với nghiệp vụ hoặc chuyển bất nhất thành dữ liệu lịch sử có hiệu lực rõ ràng; **không dùng SELECT DISTINCT để che giấu lỗi**.
6. **Tải bảng cha trước bảng con.** Chèn **customers, categories**, sau đó **products, orders**, cuối cùng **order_lines** trong giao dịch phù hợp.
7. **Đối chiếu số lượng và tập bộ.** So sánh số dòng, danh sách khóa và kết quả nối từ mô hình mới với bảng staging.
8. **Chuyển đường ghi ứng dụng.** Ngừng ghi thêm dữ liệu vào bảng gộp như nguồn chuẩn; chỉ đổi sang luồng ghi mới khi đã xử lý kế hoạch chuyển tiếp, tính đồng thời và rollback.

### 7.1. Truy vấn tìm dữ liệu mâu thuẫn trong staging

Nếu dữ liệu đã được chuẩn hóa thành các hàng trong **order_lines_flat** ở mục 2, có thể chạy:

~~~sql
-- Một mã đơn có nhiều khách hàng hoặc nhiều ngày đặt?
SELECT
    order_id,
    COUNT(DISTINCT customer_id) AS customer_count,
    COUNT(DISTINCT placed_on) AS placed_date_count
FROM order_lines_flat
GROUP BY order_id
HAVING COUNT(DISTINCT customer_id) > 1
    OR COUNT(DISTINCT placed_on) > 1;

-- Một mã khách hàng có nhiều tên hiện hành?
SELECT
    customer_id,
    COUNT(DISTINCT customer_name) AS name_count
FROM order_lines_flat
GROUP BY customer_id
HAVING COUNT(DISTINCT customer_name) > 1;

-- Một mã sản phẩm có nhiều tên hiện hành hoặc nhiều danh mục?
SELECT
    product_id,
    COUNT(DISTINCT product_name) AS name_count,
    COUNT(DISTINCT category_id) AS category_count
FROM order_lines_flat
GROUP BY product_id
HAVING COUNT(DISTINCT product_name) > 1
    OR COUNT(DISTINCT category_id) > 1;

-- Một mã danh mục có nhiều tên hiện hành?
SELECT
    category_id,
    COUNT(DISTINCT category_name) AS category_name_count
FROM order_lines_flat
GROUP BY category_id
HAVING COUNT(DISTINCT category_name) > 1;
~~~

**Các truy vấn này chỉ phát hiện mâu thuẫn đã xuất hiện.** Không có kết quả **không chứng minh** một phụ thuộc hàm đúng trong mọi trạng thái tương lai; phụ thuộc phải được xác nhận bằng đặc tả nghiệp vụ và bảo vệ bằng mô hình/ràng buộc. **COUNT(DISTINCT column)** cũng bỏ qua giá trị NULL trong SQL, nên nếu staging có NULL, cần kiểm tra tính bắt buộc và tính nhất quán của NULL riêng.

### 7.2. Ví dụ chuyển từ bảng 1NF đã làm sạch

Nếu các câu kiểm tra trên đã được xử lý và các phụ thuộc nghiệp vụ đều đúng, có thể dùng cách nạp sau **thay cho** dữ liệu mẫu ở mục 6.2, trên các bảng đích đang trống:

~~~sql
BEGIN;

INSERT INTO customers
    (customer_id, customer_name, customer_phone)
SELECT DISTINCT
    customer_id, customer_name, customer_phone
FROM order_lines_flat;

INSERT INTO categories (category_id, category_name)
SELECT DISTINCT
    category_id, category_name
FROM order_lines_flat;

INSERT INTO products (product_id, product_name, category_id)
SELECT DISTINCT
    product_id, product_name, category_id
FROM order_lines_flat;

INSERT INTO orders
    (order_id, placed_on, customer_id, ship_to_address_at_order)
SELECT DISTINCT
    order_id, placed_on, customer_id, ship_to_address_at_order
FROM order_lines_flat;

INSERT INTO order_lines
    (order_id, line_no, product_id, quantity, unit_price_vnd_at_order)
SELECT
    order_id, line_no, product_id, quantity, unit_price_vnd_at_order
FROM order_lines_flat;

COMMIT;
~~~

**Điều kiện tiên quyết:** mỗi mã khách hàng, danh mục, sản phẩm và đơn phải có đúng bộ thuộc tính hiện hành được chọn. Nếu cùng một mã xuất hiện với nhiều phiên bản thông tin, **SELECT DISTINCT** có thể tạo nhiều bộ có cùng khóa và lệnh **INSERT** sẽ lỗi; đây là tín hiệu phải giải quyết dữ liệu trước, không được bỏ qua tùy tiện. Cũng cần kiểm tra các ràng buộc khác như định dạng, giá trị thiếu và dòng hàng âm/không hợp lệ.

Nếu hệ thống nguồn có **đơn chưa có dòng**, bảng staging kiểu một hàng trên mỗi dòng **không đủ để khôi phục những đơn đó**. Phải nạp thêm nguồn header của đơn hoặc nguồn sự kiện riêng; không được giả định mọi trạng thái hợp lệ đều có mặt trong bảng gộp.

### 7.3. Kiểm tra sau khi nạp

So sánh số dòng:

~~~sql
SELECT
    (SELECT COUNT(*) FROM order_lines_flat) AS old_line_count,
    (SELECT COUNT(*) FROM order_lines) AS new_line_count;
~~~

**Số dòng bằng nhau là cần nhưng chưa đủ**: hai dòng có thể bị đổi nhầm sản phẩm mà tổng số vẫn giữ nguyên. Nên so sánh nội dung các bộ, đặc biệt **(order_id, line_no, product_id, quantity, unit_price_vnd_at_order)**:

~~~sql
-- Những dòng gốc không còn khớp trong lược đồ mới.
SELECT
    order_id, line_no, product_id,
    quantity, unit_price_vnd_at_order
FROM order_lines_flat
EXCEPT
SELECT
    order_id, line_no, product_id,
    quantity, unit_price_vnd_at_order
FROM order_lines;

-- Những dòng mô hình mới không có trong bảng gốc.
SELECT
    order_id, line_no, product_id,
    quantity, unit_price_vnd_at_order
FROM order_lines
EXCEPT
SELECT
    order_id, line_no, product_id,
    quantity, unit_price_vnd_at_order
FROM order_lines_flat;
~~~

Nếu cả hai kết quả rỗng thì **phần dữ liệu dòng hàng được so sánh** khớp theo ngữ nghĩa tập hợp. Tiếp tục đối chiếu ngày đặt, mã khách hàng, địa chỉ, thông tin danh mục qua truy vấn nối; với hệ thống có yêu cầu kiểm toán, cần kiểm tra tổng tiền, số lượng đơn và dữ liệu lịch sử. **EXCEPT** theo ngữ nghĩa tập hợp loại hàng trùng, nên nếu staging không có khóa duy nhất, phải kiểm tra số lần xuất hiện của từng bộ riêng. Những kiểm tra này thực hiện **trước khi có thay đổi giao dịch mới** hoặc trên một snapshot nhất quán.

## 8. Khi nào “dữ liệu lặp” không có nghĩa là vi phạm chuẩn hóa?

Một lỗi thường gặp trong chuẩn hóa là **tách mọi giá trị trông giống nhau** và vô tình đánh mất ý nghĩa thời gian. Hãy phân biệt:

| Dữ liệu | Phụ thuộc hợp lý | Cách lưu trong ví dụ |
| --- | --- | --- |
| Tên khách hàng **hiện hành** | **customer_id → customer_name** | Một lần trong **customers** |
| Tên và danh mục sản phẩm **hiện hành** | **product_id → product_name, category_id** | Một lần trong **products** |
| Tên danh mục **hiện hành** | **category_id → category_name** | Một lần trong **categories** |
| Địa chỉ giao **đã chốt cho đơn** | **order_id → ship_to_address_at_order** | Trong **orders** |
| Đơn giá **đã chốt cho dòng hàng** | **(order_id, line_no) → unit_price_vnd_at_order** | Trong **order_lines** |

### 8.1. Đơn giá tại thời điểm mua khác giá niêm yết hiện hành

Sản phẩm P10 có thể được bán ở O1001 với giá **300000 VND** nhưng ở O1002 với giá **290000 VND**. Điều đó có thể do thời điểm mua hoặc chương trình ưu đãi. Nếu thêm bảng **product_prices** cho giá niêm yết hiện tại, **không** được mặc định thay giá đã chốt của hai dòng hàng bằng giá niêm yết mới.

Nếu báo cáo tài chính cần giá, thuế, giảm giá và đơn vị tiền tại thời điểm giao dịch, các giá trị lịch sử phải có **grain và ý nghĩa chính xác**. Có thể lưu thêm **discount_vnd_at_order**, **tax_vnd_at_order** hoặc một bảng chi tiết điều chỉnh; các giá trị này cần được xác định bởi dòng hàng, giao dịch hay quy tắc phiên bản tương ứng.

### 8.2. Địa chỉ giao đơn hàng không phải địa chỉ hiện hành của khách hàng

Cùng C01 có thể giao O1001 tới một nơi và O1002 tới nơi khác. Nếu chỉ lưu **customers.current_address** rồi truy vấn địa chỉ giao từ đó, khi khách hàng chuyển nhà, thông tin lịch sử giao hàng sẽ sai.

Đặt **ship_to_address_at_order** trong **orders** không phải sao chép sai của một thông tin hiện hành: đó là **sự thật thuộc về đơn hàng**. Với đơn giao nhiều địa điểm hoặc nhiều kiện, grain địa chỉ có thể đổi thành **shipment_id** và cần bảng **shipments** riêng.

### 8.3. Tên sản phẩm tại thời điểm mua có thể là dữ liệu lịch sử riêng

Trong ví dụ cơ bản, báo cáo hiển thị **products.product_name** hiện hành. Nếu hóa đơn cần giữ nguyên tên mặt hàng tại lúc mua, có thể bổ sung **product_name_at_order** vào dòng hàng như **ảnh chụp lịch sử**, bên cạnh product_id tham chiếu sản phẩm. Khi đó phải mô tả rõ trường này không tự động cập nhật theo tên sản phẩm hiện hành.

Không đánh giá phụ thuộc hàm chỉ dựa trên việc hai cột cùng có chữ **name** hoặc giá trị hiện tại trùng nhau. Hãy hỏi **thuộc tính biểu diễn sự thật ở thời điểm nào** và **thay đổi của đối tượng gốc có phải làm thay đổi giá trị này hay không**.

### 8.4. Tổng tiền và các giá trị dẫn xuất

Trong ví dụ, **merchandise_total_vnd** có thể được tính từ các dòng. Nếu lưu tổng tiền trong bảng đơn để phục vụ thanh toán, đối soát hoặc hóa đơn, hệ thống phải xác định quy tắc làm tròn, thuế, vận chuyển, giảm giá và thời điểm chốt. Một giá trị dẫn xuất có thể phù hợp về nghiệp vụ nhưng đòi hỏi **cơ chế cập nhật nhất quán**, không thể tự an toàn chỉ nhờ thiết kế 3NF.

## 9. Sau 3NF: kiểm tra thêm ràng buộc và tối ưu vật lý

### 9.1. Có cần BCNF, 4NF hoặc 5NF không?

Với các phụ thuộc đã giả định, năm bảng cuối có khóa rõ ràng và không còn những vi phạm 3NF đã phát hiện. Tuy nhiên, khi nghiệp vụ mở rộng cần đánh giá lại:

- **BCNF:** nếu bảng có nhiều khóa ứng viên chồng lấn, có phụ thuộc hàm không tầm thường nào mà vế trái không là siêu khóa không?
- **4NF:** nếu một sản phẩm có nhiều nhãn, nhiều kênh bán độc lập, có đang nhân mọi tổ hợp trong một bảng không?
- **5NF:** nếu bộ ba **nhà cung cấp–sản phẩm–kho** được xác định hoàn toàn bởi các quan hệ hai chiều, có phụ thuộc nối phù hợp không?

**Không tự động tách thêm các bảng** chỉ để đạt một dạng chuẩn cao hơn. Mỗi phép phân rã phải dựa trên phụ thuộc hợp lệ và kiểm tra **nối không mất thông tin** cùng khả năng bảo vệ các ràng buộc.

### 9.2. Chỉ mục phụ thuộc truy vấn, không thay thế chuẩn hóa

Ví dụ những truy vấn hay gặp:

- Liệt kê đơn theo **customer_id**, gần nhất trước.
- Xem lịch sử bán của **product_id**.
- Lấy mọi dòng của **order_id** theo **line_no**.

**PRIMARY KEY (order_id, line_no)** hỗ trợ đường truy vấn dòng theo order_id. Có thể cân nhắc:

~~~sql
CREATE INDEX idx_orders_customer_date
ON orders (customer_id, placed_on DESC);

CREATE INDEX idx_order_lines_product
ON order_lines (product_id);
~~~

Các chỉ mục chỉ là **gợi ý**. Cần dùng dữ liệu thực, khối lượng đọc/ghi và kế hoạch truy vấn để quyết định. Tăng chỉ mục giúp một số truy vấn nhưng làm tăng chi phí ghi và dung lượng; việc thêm chỉ mục không loại bỏ được một phụ thuộc hàm sai.

### 9.3. Dữ liệu quan hệ, document và mô hình phân tích

Thiết kế quan hệ tách header/dòng và danh mục thuận lợi khi nhiều luồng nghiệp vụ cập nhật khách hàng, sản phẩm, đơn hàng độc lập và cần ràng buộc tham chiếu.

Trong hệ quản trị document, có thể chọn **nhúng dòng hàng vào document đơn** khi thường đọc/ghi cả đơn và muốn cô lập giao dịch ở phạm vi document. Tuy nhiên thông tin khách hàng/sản phẩm hiện hành vẫn cần nguồn chuẩn hoặc chiến lược đồng bộ, còn những ràng buộc xuyên document phải được thiết kế rõ.

Trong kho phân tích, bảng fact dòng hàng kết hợp dimension khách hàng, sản phẩm, thời gian có thể cố ý lặp khóa hoặc ảnh chụp phục vụ báo cáo lịch sử. Khi đó thiết kế cần xác định grain của fact, phiên bản dimension và nguồn dữ liệu chuẩn, không sao chép máy móc các bảng giao dịch.

## 10. Bài tập thực hành có lời giải

### Bài 1. Nhận diện các bước chuẩn hóa

Một bảng nhập liệu có:

~~~text
order_id
order_date
buyer_id
buyer_name
items = [
  {sku, sku_name, quantity, paid_unit_price},
  ...
]
~~~

Quy tắc: một người mua có nhiều đơn; mỗi đơn có nhiều dòng được đánh số; tên SKU là **hiện hành**; giá thanh toán là **giá đã chốt của dòng**, không nhất thiết giống giá niêm yết.

**Yêu cầu:** xác định lỗi ở dạng lưu ban đầu; đề xuất khóa cho bảng dòng; viết các phụ thuộc hàm; phân rã tới 3NF và giải thích chỗ lưu **paid_unit_price**.

<details>
<summary>Gợi ý lời giải bài 1</summary>

Nếu bảng SQL lưu toàn bộ danh sách items trong một ô nhưng nghiệp vụ cần quản lý riêng từng dòng, cần tách dòng để có grain rõ và kiểm tra ràng buộc trên từng phần tử.

~~~text
(order_id, line_no) -> sku, quantity, paid_unit_price
order_id            -> order_date, buyer_id
buyer_id            -> buyer_name
sku                 -> sku_name
~~~

Từ bảng dòng phẳng 1NF, tách **orders(order_id, order_date, buyer_id)** để loại phụ thuộc bộ phận vào khóa ghép, giữ **order_lines(order_id, line_no, sku, quantity, paid_unit_price)**. Sau đó tách **buyers(buyer_id, buyer_name)** và **skus(sku, sku_name)** để dữ liệu hiện hành nằm đúng bảng sở hữu.

**paid_unit_price** vẫn nằm trong **order_lines**, vì theo nghiệp vụ nó thuộc dòng giao dịch; không giả định **sku → paid_unit_price**.

</details>

### Bài 2. Chọn khóa khi sản phẩm có thể lặp

Đơn O2001 có hai dòng cùng SKU P10: dòng 1 giá 300000, dòng 2 giá 270000 do chương trình ưu đãi.

**Câu hỏi:** **(order_id, product_id)** có còn là khóa ứng viên của dòng hàng không? Nếu thêm **order_line_id** làm khóa thay thế, còn nên giữ **UNIQUE(order_id, line_no)** không?

<details>
<summary>Gợi ý lời giải bài 2</summary>

Không. **(order_id, product_id)** xuất hiện hai lần nên không định danh duy nhất dòng. Có thể dùng **(order_id, line_no)** làm khóa chính.

Nếu dùng **order_line_id** làm khóa chính để thuận lợi tham chiếu, vẫn nên giữ **UNIQUE(order_id, line_no)** nếu quy tắc nghiệp vụ xác định **line_no** là duy nhất trong mỗi đơn; đồng thời **order_id** và **line_no** phải **NOT NULL** để bảo vệ khóa nghiệp vụ đúng nghĩa.

Khóa thay thế chỉ thay đổi cách định danh hàng, không tự loại bỏ phụ thuộc bộ phận hay bắc cầu.

</details>

### Bài 3. Kiểm chứng dữ liệu sau chuyển đổi

Bảng cũ có 120 đơn, 318 dòng hàng; một số khách được lặp lại trong nhiều đơn. Nhóm phát triển đã tạo năm bảng chuẩn hóa.

**Hãy nêu:** ba phép kiểm tra tối thiểu trước khi đóng luồng ghi dữ liệu cũ; vì sao **318 dòng sau chuyển đổi** chưa đủ chứng minh chuyển đổi chính xác; và cách phát hiện một **product_id** bị gán hai tên hiện hành trong staging.

**Hướng giải:** kiểm tra khóa và FD ở dữ liệu cũ; đối chiếu tập khóa **(order_id,line_no)** cùng product, quantity, giá theo hai chiều; đối chiếu số đơn kể cả đơn không có dòng, địa chỉ và tổng tiền. Hai tập có cùng số dòng vẫn có thể chứa bản ghi khác nhau. Nhóm theo **product_id** và lọc **COUNT(DISTINCT product_name) > 1** giúp phát hiện mâu thuẫn đã xuất hiện; phải xác nhận danh mục hiện hành với nguồn nghiệp vụ.

## 11. Checklist tự đánh giá một lược đồ đơn hàng

| Câu hỏi kiểm tra | Dấu hiệu thiết kế phù hợp |
| --- | --- |
| Một hàng **orders** mô tả gì? | Một đơn có định danh, ngày đặt, người đặt và thông tin thuộc đơn |
| Một hàng **order_lines** mô tả gì? | Một dòng trong đơn có khóa **(order_id,line_no)** hoặc khóa thay thế kèm ràng buộc nghiệp vụ |
| Danh sách item có còn bị giấu trong một ô cần thao tác riêng không? | Mỗi dòng cần cập nhật độc lập được mô hình hóa rõ |
| Khóa ghép có thuộc tính nào chỉ phụ thuộc một phần không? | Thuộc tính header đã tách khỏi dòng |
| Tên khách hàng, sản phẩm, danh mục hiện hành được lưu ở đâu? | Một nguồn chuẩn tại các bảng sở hữu tương ứng |
| Giá lúc mua có bị lấy nhầm từ giá hiện tại của sản phẩm không? | Giá lịch sử thuộc về giao dịch/dòng hàng |
| Địa chỉ giao có bị thay theo hồ sơ khách hàng không? | Lưu đúng địa chỉ chốt của đơn |
| Có thể có đơn chưa có dòng, sản phẩm chưa được đặt không? | Bảng cha tồn tại độc lập; bảng con dùng FK |
| Phép nối có nhân bản dòng hoặc tạo bộ giả không? | Các khóa và phụ thuộc bảo vệ quan hệ nối |
| Dữ liệu nhập cũ đã được kiểm tra xung đột và đối chiếu chưa? | Có báo cáo lỗi, kiểm tra khóa, FD, số lượng, bộ dữ liệu và tổng tiền |
| Chỉ mục đã dựa trên cách truy vấn thực tế chưa? | Được kiểm chứng bằng workload và kế hoạch thực thi |

## 12. Ghi nhớ

Quy trình chuẩn hóa từ bảng đơn hàng chưa hợp lý không phải thao tác cơ học “chia một bảng thành nhiều bảng”. **Bước 1** xác định grain và đưa các dòng cần quản lý độc lập ra khỏi ô danh sách để có dạng quan hệ 1NF. **Bước 2** viết khóa ứng viên và phụ thuộc hàm, sau đó tách **đơn hàng** khỏi **dòng hàng** để loại phụ thuộc bộ phận, tiến tới 2NF. **Bước 3** tách **khách hàng, sản phẩm, danh mục** theo những phụ thuộc bắc cầu, tiến tới 3NF.

Kết quả cần có **khóa chính, khóa ngoại, ràng buộc miền, phép nối không mất thông tin và chiến lược chuyển dữ liệu có kiểm chứng**. Đồng thời phải phân biệt dữ liệu hiện hành với dữ liệu lịch sử: **đơn giá tại thời điểm đặt** và **địa chỉ giao đã chốt** thuộc về giao dịch, không nên bị “chuẩn hóa mất” vào bảng sản phẩm hoặc khách hàng. Khi các quy tắc đã đúng, mới đánh giá tiếp BCNF, 4NF, 5NF, chỉ mục và các cấu trúc đọc phù hợp với nhu cầu vận hành.
