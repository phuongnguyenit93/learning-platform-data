# Phụ thuộc tầm thường, đầy đủ, bộ phận và bắc cầu

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, nhận diện đúng các loại phụ thuộc hàm giúp chuyển quy tắc nghiệp vụ thành mô hình dữ liệu có khóa rõ ràng, ít dư thừa và dễ kiểm chứng. Đây là nền tảng để phân tích chuẩn hóa, lựa chọn ràng buộc và xây dựng lược đồ vật lý trong hệ quản trị cơ sở dữ liệu quan hệ. Tư duy xác định dữ liệu nào phụ thuộc vào dữ liệu nào cũng hữu ích khi cân nhắc mô hình document, đồ thị hoặc phân tích, dù các hệ đó không nhất thiết thực thi phụ thuộc hàm như SQL.

Sau bài này, bạn có thể:

1. Phân biệt **phụ thuộc tầm thường**, **không tầm thường**, **đầy đủ**, **bộ phận** và **bắc cầu** bằng định nghĩa chính xác.
2. Kiểm tra phụ thuộc bằng **bao đóng thuộc tính**, thay vì chỉ quan sát vài dòng dữ liệu.
3. Nhận ra phụ thuộc bộ phận và bắc cầu dẫn đến các bất thường cập nhật, chèn, xóa.
4. Liên hệ phụ thuộc với khóa ứng viên, **2NF**, **3NF** và **BCNF**; chuyển kết quả thành các bảng và ràng buộc cụ thể.

## 1. Bối cảnh chung: phụ thuộc hàm phản ánh quy tắc nghiệp vụ

Xét một bảng xuất dữ liệu chi tiết đơn hàng:

~~~text
ORDER_LINE_FLAT(
    order_id, line_no, order_date,
    customer_id, customer_name,
    product_id, product_name,
    quantity, unit_price_at_sale
)
~~~

**Mức hạt** của bảng là một dòng hàng trong một đơn. Giả sử bộ phận nghiệp vụ xác nhận:

- Mỗi `order_id` định danh một đơn hàng với một ngày đặt và một khách hàng.
- Trong **mỗi đơn hàng**, `line_no` là duy nhất. Mỗi cặp `(order_id, line_no)` xác định một sản phẩm, số lượng và đơn giá tại lúc bán.
- Mỗi `customer_id` có một tên hiện hành `customer_name`; mỗi `product_id` có một tên hiện hành `product_name`.
- Một đơn có nhiều dòng; một sản phẩm có thể được bán ở nhiều mức giá, và có thể xuất hiện nhiều lần trong cùng đơn.

Từ đó, ta có tập phụ thuộc hàm cơ sở \(F\):

~~~text
F1: order_id             → order_date, customer_id
F2: customer_id          → customer_name
F3: product_id           → product_name
F4: (order_id, line_no)  → product_id, quantity, unit_price_at_sale
~~~

Ký hiệu \(X \rightarrow Y\) nghĩa là: với **mọi cặp dòng hợp lệ**, nếu hai dòng trùng giá trị trên tất cả thuộc tính của \(X\), chúng bắt buộc trùng giá trị trên tất cả thuộc tính của \(Y\).

\[
\forall t_1,t_2 \in r,\quad
t_1[X]=t_2[X]\Rightarrow t_1[Y]=t_2[Y].
\]

Ví dụ, `order_id → customer_id` nói rằng cùng một đơn không thể có hai mã khách khác nhau. Đây là quy tắc về **mọi trạng thái hợp lệ của dữ liệu**, không chỉ về các dòng đang lưu.

Để phân loại phụ thuộc, cần giữ cố định **lược đồ, tập quy tắc \(F\), phạm vi định danh và thời điểm dữ liệu**. Nếu `order_id` chỉ duy nhất trong một cửa hàng, phải xét `(store_id, order_id)`; nếu bảng lưu lịch sử đổi tên, giả định về `customer_id → customer_name` có thể không còn đúng.

## 2. Phụ thuộc tầm thường (trivial functional dependency)

Một phụ thuộc \(X\rightarrow Y\) là **tầm thường** khi:

\[
Y\subseteq X.
\]

Điều này có nghĩa các thuộc tính ở vế phải vốn đã nằm trong vế trái. Ví dụ:

~~~text
(order_id, line_no) → order_id
(order_id, line_no) → line_no
(order_id, line_no) → (order_id, line_no)
customer_id         → customer_id
~~~

Chúng **luôn đúng về logic**, bất kể hệ thống đang bán hàng, quản lý kho hay quản lý nhân sự. Nếu hai dòng bằng nhau trên `(order_id, line_no)`, chúng tất nhiên bằng nhau trên `order_id`. Đây là **tiên đề phản xạ** của Armstrong.

### Không tầm thường và hoàn toàn không tầm thường

Phụ thuộc **không tầm thường** khi \(Y\nsubseteq X\). Chẳng hạn:

~~~text
order_id                    → customer_id
(order_id, line_no)         → quantity
(order_id, customer_id)     → (customer_id, order_date)
~~~

Ví dụ cuối **không tầm thường** vì `order_date` không nằm ở vế trái, dù `customer_id` có xuất hiện ở cả hai vế.

Phụ thuộc **hoàn toàn không tầm thường** khi \(X\cap Y=\varnothing\), chẳng hạn `product_id → product_name`. Đây là khái niệm khác với **phụ thuộc đầy đủ** ở phần tiếp theo: “hoàn toàn không tầm thường” nói về **giao giữa hai vế**; “đầy đủ” nói về việc **có bỏ được thuộc tính ở vế trái không**.

**Ý nghĩa thiết kế:** phụ thuộc tầm thường không giúp phát hiện thuộc tính nghiệp vụ mới do một khóa xác định, nên khi tìm khóa, phủ tối thiểu hoặc phân tích chuẩn hóa, ta thường tập trung vào phụ thuộc không tầm thường.

## 3. Phụ thuộc đầy đủ (full functional dependency)

Giả sử \(X\rightarrow Y\) đúng theo \(F\). Đây là **phụ thuộc đầy đủ** nếu **không có tập con thực sự** \(X'\subset X\) nào vẫn xác định \(Y\):

\[
X\rightarrow Y
\quad\text{và}\quad
\forall X'\subset X:\; X'\not\rightarrow Y.
\]

Với \(X=\{\text{order_id},\text{line_no}\}\), xét:

~~~text
(order_id, line_no) → quantity
~~~

Đây là phụ thuộc đầy đủ trong ví dụ đã cho:

- Cặp `(order_id, line_no)` xác định duy nhất một dòng, nên xác định `quantity`.
- Chỉ biết `order_id` thì đơn hàng có thể có nhiều dòng với số lượng khác nhau.
- Chỉ biết `line_no` thì dòng số 1 của hai đơn hàng có thể có số lượng khác nhau.

Không có vế trái nào ngắn hơn còn đủ để xác định `quantity`.

### Cách kiểm chứng bằng bao đóng

Bao đóng \(X^+\) theo \(F\) là tất cả thuộc tính có thể suy ra từ \(X\). Từ F1–F4:

~~~text
{order_id}+ =
  {order_id, order_date, customer_id, customer_name}

{line_no}+ = {line_no}

{order_id, line_no}+ =
  {order_id, line_no, order_date, customer_id, customer_name,
   product_id, product_name, quantity, unit_price_at_sale}
~~~

Vì `quantity` nằm trong `{order_id, line_no}+` nhưng không nằm trong bao đóng của một trong hai tập con thực sự `{order_id}` và `{line_no}`, phụ thuộc này là **đầy đủ** theo \(F\). Bao đóng của cặp thuộc tính cũng chứa cả chín thuộc tính trong bảng, nên cặp đó là một **siêu khóa**; vì cả hai thành phần đều cần thiết, đó là một **khóa ứng viên**.

Lưu ý: với vế trái nhiều thuộc tính, phải kiểm tra mọi cách bỏ thuộc tính, chứ không chỉ một cách. Khi vế phải có nhiều thuộc tính, nên **tách thành từng thuộc tính** trước khi phân tích chuẩn hóa; có thể một thuộc tính phụ thuộc bộ phận trong khi thuộc tính khác phụ thuộc đầy đủ.

## 4. Phụ thuộc bộ phận (partial functional dependency)

Một phụ thuộc \(X\rightarrow Y\) là **bộ phận** nếu có **ít nhất một tập con thực sự** \(X'\subset X\) cũng xác định \(Y\):

\[
\exists X'\subset X:\; X'\rightarrow Y.
\]

Trong bảng gộp, khóa ứng viên là `(order_id, line_no)`. Xét:

~~~text
(order_id, line_no) → order_date
~~~

Phụ thuộc này đúng, nhưng **bộ phận**, vì:

~~~text
order_id → order_date
~~~

Chỉ `order_id`, một phần của khóa ghép, đã đủ xác định ngày đặt. Tương tự:

~~~text
(order_id, line_no) → customer_id
~~~

là phụ thuộc bộ phận vì `order_id → customer_id`.

Ngược lại, `(order_id, line_no) → quantity` là đầy đủ theo các quy tắc đã cho. Không được kết luận tất cả thuộc tính của một bảng đều phụ thuộc đầy đủ vào khóa chỉ vì chúng nằm trên cùng một dòng.

### Vì sao phụ thuộc bộ phận gây dư thừa?

| order_id | line_no | order_date | customer_id | quantity |
|---|---:|---|---|---:|
| DH01 | 1 | 2026-11-01 | KH01 | 2 |
| DH01 | 2 | 2026-11-01 | KH01 | 1 |
| DH02 | 1 | 2026-11-02 | KH02 | 3 |

Các thông tin `order_date` và `customer_id` của `DH01` lặp lại ở **mỗi dòng hàng**. Nếu sửa ngày đặt nhưng chỉ sửa một dòng, bảng sẽ mâu thuẫn với `order_id → order_date`. Nếu chưa có dòng sản phẩm nào, rất khó lưu thông tin đơn hàng mà không tạo một dòng giả.

### Phụ thuộc bộ phận và dạng chuẩn 2NF

Một quan hệ ở **dạng chuẩn 2NF** khi đã ở 1NF và **mọi thuộc tính không khóa** (*non-prime attribute*: thuộc tính không nằm trong bất kỳ khóa ứng viên nào) **phụ thuộc đầy đủ vào mọi khóa ứng viên**.

Trong ví dụ, `order_date` và `customer_id` là thuộc tính không khóa nhưng phụ thuộc vào `order_id` — một phần của khóa `(order_id, line_no)`. Vì thế bảng gộp **vi phạm 2NF**.

Những điểm dễ nhầm:

- Phải xét **mọi khóa ứng viên**, không chỉ khóa chính được chọn triển khai.
- Phụ thuộc bộ phận chỉ gây vi phạm **2NF** theo tiêu chí trên khi vế phải là thuộc tính **không khóa**. Một phụ thuộc vào thuộc tính khóa (*prime attribute*) cần được đánh giá đúng theo định nghĩa của dạng chuẩn.
- Với khóa ứng viên chỉ gồm một thuộc tính, không thể bỏ bớt một thành phần **khác rỗng** để tạo phụ thuộc bộ phận thông thường; tuy nhiên cần xét các khóa ứng viên khác và các phụ thuộc từ tập rỗng nếu mô hình có thuộc tính hằng.

## 5. Phụ thuộc bắc cầu (transitive functional dependency)

Nếu \(X\rightarrow Y\) và \(Y\rightarrow Z\), thì suy ra \(X\rightarrow Z\). Đây là **quy tắc bắc cầu** trong các tiên đề Armstrong.

Ví dụ:

~~~text
order_id → customer_id
customer_id → customer_name
--------------------------------
order_id → customer_name
~~~

Mỗi mã đơn xác định một khách hàng, và mỗi mã khách xác định một tên hiện hành; vì vậy mã đơn xác định tên hiện hành của khách. Tương tự:

~~~text
(order_id, line_no) → product_id
product_id          → product_name
-----------------------------------
(order_id, line_no) → product_name
~~~

Các chuỗi này có một thuộc tính hoặc tập thuộc tính **trung gian**. Chúng cho thấy vì sao tên khách hoặc tên sản phẩm có thể xuất hiện nhiều lần trên các dòng hàng.

~~~mermaid
flowchart LR
  A["order_id"] --> B["customer_id"]
  B --> C["customer_name"]
  D["(order_id, line_no)"] --> E["product_id"]
  E --> F["product_name"]
~~~

### Phân biệt suy diễn bắc cầu với vi phạm 3NF

**Bắc cầu** là một tính chất suy diễn rất rộng. **Không phải mọi chuỗi bắc cầu đều làm một quan hệ vi phạm 3NF.** Khi đánh giá chuẩn hóa, cần xem thuộc tính trung gian có là siêu khóa hay không và thuộc tính ở vế phải có thuộc một khóa ứng viên hay không.

Ở ví dụ bảng gộp, `customer_id` **không** là siêu khóa của bảng dòng hàng và `customer_name` **không** thuộc khóa ứng viên. Vì thế phụ thuộc không tầm thường `customer_id → customer_name` là một nguyên nhân cụ thể khiến bảng gộp **không đạt 3NF**.

Định nghĩa 3NF theo phụ thuộc hàm: với **mọi phụ thuộc không tầm thường** \(X\rightarrow A\) (vế phải là một thuộc tính) suy ra từ \(F\), phải thỏa **ít nhất một** điều kiện:

1. \(X\) là **siêu khóa**; hoặc
2. \(A\) là **thuộc tính khóa** (*prime attribute*), tức thuộc ít nhất một khóa ứng viên.

Chẳng hạn, ngay cả khi có phụ thuộc bắc cầu, nếu mọi phụ thuộc không tầm thường đều thỏa một trong hai điều kiện trên thì quan hệ vẫn có thể đạt 3NF.

Ví dụ nâng cao với `R(A, B, C)` và `F = {AB → C, C → B}`: các khóa ứng viên là `AB` và `AC`. Phụ thuộc `C → B` có vế trái **không** là siêu khóa, nhưng `B` là thuộc tính khóa vì có mặt trong khóa ứng viên `AB`; do đó quan hệ có thể đạt **3NF nhưng không đạt BCNF**. BCNF đòi hỏi vế trái của **mọi phụ thuộc không tầm thường** phải là siêu khóa.

## 6. Bảng so sánh: bốn loại phản ánh các câu hỏi khác nhau

| Loại phụ thuộc | Câu hỏi kiểm tra | Dấu hiệu trên ví dụ |
|---|---|---|
| **Tầm thường** | Vế phải có nằm hoàn toàn trong vế trái? | `(order_id, line_no) → order_id` |
| **Đầy đủ** | Bỏ bất kỳ phần nào của vế trái thì còn xác định được vế phải? **Không** | `(order_id, line_no) → quantity` |
| **Bộ phận** | Có tập con thực sự của vế trái vẫn xác định vế phải? **Có** | `(order_id, line_no) → order_date` |
| **Bắc cầu** | Có thể đi qua thuộc tính trung gian \(Y\), theo \(X→Y→Z\)? | `order_id → customer_id → customer_name` |

**Bốn loại không tạo thành bốn nhóm loại trừ nhau.** “Tầm thường / không tầm thường” xét quan hệ tập hợp giữa hai vế; “đầy đủ / bộ phận” xét sự **tối thiểu của vế trái**; “bắc cầu” xét **đường suy diễn**. Ví dụ `(order_id, line_no) → customer_name` vừa là phụ thuộc **bộ phận** (vì `order_id → customer_name`), vừa có thể suy ra qua **bắc cầu** `order_id → customer_id → customer_name`.

Với vế phải gồm nhiều thuộc tính, ví dụ `(order_id, line_no) → (quantity, order_date)`, có một điểm tinh tế:

- Không tập con nào của `(order_id, line_no)` xác định **đồng thời cả hai** `quantity` và `order_date`, nên phụ thuộc với **toàn bộ** vế phải có thể được xem là đầy đủ theo định nghĩa tập hợp.
- Nhưng khi phân rã vế phải, `(order_id, line_no) → order_date` lại là **bộ phận**, còn `(order_id, line_no) → quantity` là **đầy đủ**.

Vì thế, khi phân tích 2NF hoặc tìm phủ tối thiểu, hãy **phân rã vế phải thành từng thuộc tính** trước khi phân loại.

## 7. Quy trình phân loại có thể kiểm chứng

### Bước 1 — Liệt kê phụ thuộc đã xác nhận

Hỏi người hiểu nghiệp vụ: “Một mã này có thể chỉ đến hai giá trị khác nhau trong trường hợp nào?” Xác định phạm vi (toàn hệ thống, cửa hàng, năm), tính hiện hành/lịch sử và ngoại lệ hợp lệ.

### Bước 2 — Tìm khóa bằng bao đóng

Đặt `closure = X`; lặp qua các phụ thuộc \(L\rightarrow R\) trong \(F\), nếu \(L\subseteq closure\) thì thêm \(R\) vào `closure`, cho đến khi không còn thuộc tính mới. Nếu \(X^+\) chứa tất cả thuộc tính của quan hệ, \(X\) là **siêu khóa**; tiếp tục thử bỏ từng thuộc tính để kiểm tra tính tối thiểu của **khóa ứng viên**.

~~~text
attributeClosure(X, F):
    result := X
    repeat:
        previous := result
        for each (L → R) in F:
            if L ⊆ result:
                result := result ∪ R
    until result = previous
    return result
~~~

### Bước 3 — Phân rã và kiểm tra vế trái

Tách `X → A,B` thành `X → A` và `X → B`. Với mỗi `X → A`:

1. Nếu \(A\in X\), ghi nhận **tầm thường**.
2. Nếu không tầm thường, kiểm tra \(A\in (X-\{x\})^+\) cho từng \(x\in X\).
3. Nếu có thể bỏ ít nhất một \(x\), đây là phụ thuộc **bộ phận** theo tập \(F\); nếu không, là **đầy đủ**.
4. Kiểm tra các đường suy diễn \(X\rightarrow Y\rightarrow A\) khi muốn tìm phụ thuộc **bắc cầu** và các nguyên nhân dư thừa.

Lưu ý quy tắc kiểm tra từng phần tử vế trái chỉ áp dụng sau khi đã xác nhận phụ thuộc đang xét đúng; với phụ thuộc nhiều thuộc tính ở vế phải, phải phân rã như trên.

### Bước 4 — Liên hệ chuẩn hóa

| Kiểm tra | Câu hỏi chính |
|---|---|
| **1NF** | Các giá trị cột có tính nguyên tử theo mô hình đã chọn, không có nhóm lặp? |
| **2NF** | Thuộc tính không khóa có phụ thuộc vào chỉ một phần của **bất kỳ** khóa ứng viên không? |
| **3NF** | Có phụ thuộc không tầm thường `X → A` mà `X` không là siêu khóa và `A` không là thuộc tính khóa không? |
| **BCNF** | Có phụ thuộc không tầm thường `X → A` nào mà `X` không là siêu khóa không? |

Đây là các tiêu chí đánh giá khác nhau, không phải nhãn thay thế cho các kiểu phụ thuộc. Khi tách bảng, còn cần xét **nối không mất mát dữ liệu** (*lossless join*) và, nếu quan trọng, **bảo toàn phụ thuộc** (*dependency preservation*).

## 8. Từ phân loại sang thiết kế bảng

Trong `ORDER_LINE_FLAT`, có hai nhóm thông tin bị trộn:

- Phụ thuộc **bộ phận** `order_id → order_date, customer_id` cho biết thông tin đơn hàng nên được lưu ở mức một đơn.
- Các phụ thuộc `customer_id → customer_name` và `product_id → product_name` cho biết tên hiện hành thuộc về thực thể khách hàng và sản phẩm; việc lặp chúng trên mỗi dòng hàng tạo đường phụ thuộc bắc cầu qua mã định danh.

Với giả định mỗi mã là duy nhất toàn hệ thống và tên là **tên hiện hành**, có thể tách thành:

~~~text
CUSTOMERS(customer_id PK, customer_name)
PRODUCTS(product_id PK, product_name)
ORDERS(order_id PK, order_date, customer_id FK)
ORDER_ITEMS((order_id, line_no) PK, product_id FK,
            quantity, unit_price_at_sale)
~~~

Ví dụ DDL:

~~~sql
CREATE TABLE customers (
    customer_id VARCHAR(30) PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);

CREATE TABLE products (
    product_id VARCHAR(30) PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id VARCHAR(30) PRIMARY KEY,
    order_date DATE NOT NULL,
    customer_id VARCHAR(30) NOT NULL REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_id VARCHAR(30) NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(30) NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_sale DECIMAL(12, 2) NOT NULL
        CHECK (unit_price_at_sale >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Các khóa chính bảo đảm mỗi mã định danh xác định duy nhất một dòng ở bảng tương ứng. Khóa ngoại thể hiện mối liên hệ giữa các thực thể; ràng buộc `CHECK` thể hiện quy tắc miền giá trị mà bản thân phụ thuộc hàm **không** mô tả.

`unit_price_at_sale` nằm ở **dòng giao dịch**, vì nghiệp vụ cho phép cùng sản phẩm có nhiều giá bán. Không đặt `UNIQUE(order_id, product_id)` nếu một đơn được phép có hai dòng cùng sản phẩm; đó sẽ là một ràng buộc nghiệp vụ sai. Chỉ mục bổ sung cho truy vấn theo `customer_id` hoặc `product_id` nên được quyết định theo mẫu truy vấn và kế hoạch thực thi, không suy ra tự động từ ký hiệu phụ thuộc hàm.

Ở mô hình document, có thể nhúng các dòng hàng vào đơn để đọc cả đơn một lần, nhưng vẫn phải xác định rõ dữ liệu nào là **ảnh chụp tại lúc giao dịch** và dữ liệu nào được đọc từ nguồn hiện hành. Với mô hình phân tích, mức hạt của fact và cách lưu lịch sử dimension sẽ ảnh hưởng trực tiếp đến những phụ thuộc đúng tại mỗi thời điểm.

## 9. Sai lầm thường gặp

**Sai lầm 1 — “Vế trái dài thì phụ thuộc đầy đủ”.** Không đúng. `(order_id, line_no) → order_date` có hai thuộc tính ở vế trái nhưng vẫn bộ phận vì `order_id` đã đủ.

**Sai lầm 2 — “Phụ thuộc bắc cầu luôn vi phạm 3NF”.** Không đúng. Phải xét phụ thuộc không tầm thường với vế trái là siêu khóa hay vế phải là thuộc tính khóa. Ví dụ 3NF nhưng không BCNF ở trên cho thấy sự khác nhau.

**Sai lầm 3 — “Tầm thường nghĩa là sai hoặc vô ích”.** Phụ thuộc tầm thường **luôn đúng** theo logic. Nó hữu ích cho suy diễn hình thức, nhưng tự nó không cung cấp thêm một quy tắc nghiệp vụ.

**Sai lầm 4 — “Không thấy vi phạm trong dữ liệu thì phụ thuộc đúng”.** Một mẫu nhỏ không chứng minh phụ thuộc đúng ở mọi trạng thái hợp lệ; cần quy tắc nghiệp vụ. Dữ liệu mẫu chỉ có thể cung cấp **phản ví dụ** khi có hai dòng cùng \(X\) nhưng khác \(Y\).

**Sai lầm 5 — “Chỉ cần xét khóa chính”.** Chuẩn hóa cần xét **tất cả khóa ứng viên**. Một thuộc tính là *prime* nếu nằm trong ít nhất một khóa ứng viên, không nhất thiết thuộc khóa chính.

**Sai lầm 6 — “Các loại phụ thuộc loại trừ nhau”.** Một phụ thuộc có thể vừa bộ phận vừa suy ra theo bắc cầu. Đừng cố gán mỗi mũi tên vào đúng một nhóm.

## 10. Bài luyện tập có lời giải

### Bài 1 — Phân loại phụ thuộc

Cho quan hệ `ENROLLMENT(student_id, course_id, student_name, course_title, grade)`, giả sử:

~~~text
student_id → student_name
course_id  → course_title
(student_id, course_id) → grade
~~~

Mỗi sinh viên có thể học nhiều môn, mỗi môn có nhiều sinh viên. Hãy phân loại:

1. `(student_id, course_id) → student_id`
2. `(student_id, course_id) → grade`
3. `(student_id, course_id) → student_name`

**Lời giải:** (1) **tầm thường** vì vế phải thuộc vế trái. (2) **đầy đủ** theo các phụ thuộc đã cho, vì một sinh viên có nhiều điểm và một môn có điểm của nhiều sinh viên. (3) **bộ phận** vì `student_id → student_name`. Khi đánh giá 2NF, `student_name` và `course_title` nên tách sang các bảng thông tin riêng theo thực thể.

### Bài 2 — Tìm đường bắc cầu

Cho:

~~~text
employee_id   → department_id
department_id → department_name
~~~

Hãy suy ra phụ thuộc mới và nêu điều kiện khiến một bảng gộp `(employee_id, department_id, department_name)` vi phạm 3NF.

**Lời giải:** Suy ra `employee_id → department_name` qua bắc cầu. Nếu `employee_id` là khóa ứng viên của bảng, `department_id` không là siêu khóa và `department_name` là thuộc tính không khóa, thì `department_id → department_name` vi phạm tiêu chí 3NF. Có thể tách `EMPLOYEES(employee_id, department_id)` và `DEPARTMENTS(department_id, department_name)`, với khóa ngoại nối giữa hai bảng.

### Bài 3 — Đừng phân loại cả vế phải quá sớm

Cho `(order_id, line_no) → (quantity, order_date)` cùng các quy tắc ở đầu bài. Từng thuộc tính vế phải phụ thuộc như thế nào?

**Lời giải:** `quantity` phụ thuộc **đầy đủ** vào khóa ghép; `order_date` phụ thuộc **bộ phận** vì `order_id → order_date`. Phải tách vế phải để thấy được vấn đề 2NF.

### Bài 4 — Kiểm tra giả định thời gian

Hệ thống cho phép khách hàng đổi tên và lưu **tên tại thời điểm đặt hàng** trong `customer_name_at_order`. Có thể khẳng định `customer_id → customer_name_at_order` không?

**Lời giải:** Không. Cùng một khách có thể có nhiều tên ở các thời điểm đặt khác nhau. Nếu mỗi đơn chỉ lưu một ảnh chụp tên, `order_id → customer_name_at_order` có thể đúng theo quy tắc đó. Kết luận phụ thuộc phụ thuộc vào **ý nghĩa thuộc tính** và **phạm vi thời gian**.

## 11. Checklist áp dụng vào mô hình dữ liệu

- [ ] Xác định đúng mức hạt của mỗi quan hệ và phạm vi của mã định danh.
- [ ] Lập tập phụ thuộc từ quy tắc nghiệp vụ đã xác nhận, làm rõ dữ liệu hiện hành và lịch sử.
- [ ] Xác định tất cả khóa ứng viên bằng bao đóng.
- [ ] Tách từng thuộc tính ở vế phải trước khi xét đầy đủ và bộ phận.
- [ ] Phân biệt phụ thuộc tầm thường với các phụ thuộc mang thông tin nghiệp vụ.
- [ ] Tìm các phụ thuộc bắc cầu và kiểm tra điều kiện 3NF/BCNF chính xác.
- [ ] Đánh giá bất thường dữ liệu, nối không mất mát và bảo toàn phụ thuộc khi tách bảng.
- [ ] Ánh xạ sang khóa chính, khóa ngoại, `UNIQUE`, `CHECK` và chỉ mục theo đúng mục đích.

**Ghi nhớ:** Phụ thuộc **tầm thường** hỏi “vế phải đã có sẵn ở vế trái chưa?”; phụ thuộc **đầy đủ** và **bộ phận** hỏi “vế trái có thể rút gọn không?”; phụ thuộc **bắc cầu** hỏi “giá trị này được xác định qua thuộc tính trung gian nào?”. Phân biệt được ba câu hỏi đó giúp bạn phát hiện đúng rủi ro dư thừa và chọn cấu trúc dữ liệu phù hợp.
