# Phụ thuộc hàm (functional dependency) và cách suy ra từ quy tắc nghiệp vụ

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, phụ thuộc hàm là công cụ nối yêu cầu nghiệp vụ với thiết kế dữ liệu: từ đó xác định khóa, phát hiện dữ liệu dư thừa, chuẩn hóa bảng và chọn ràng buộc phù hợp khi triển khai lược đồ quan hệ.

Sau bài học, bạn có thể:

- Giải thích chính xác ý nghĩa của một phụ thuộc hàm \(X \rightarrow Y\).
- Đọc quy tắc nghiệp vụ và xác định vế trái, vế phải cùng **phạm vi hiệu lực** của phụ thuộc.
- Phân biệt phụ thuộc được **quy tắc nghiệp vụ bảo đảm** với sự trùng hợp trong vài dòng dữ liệu.
- Dùng phép bao đóng và các quy tắc suy diễn để kiểm tra khóa và các phụ thuộc kéo theo.
- Chuyển các kết quả đó thành thiết kế bảng, khóa và ràng buộc có thể kiểm chứng.

## 1. Vấn đề nghiệp vụ: một bảng có nhiều sự thật khác nhau

Giả sử hệ thống bán hàng xuất dữ liệu chi tiết đơn hàng dưới dạng một quan hệ:

~~~text
CHI_TIET_DON_HANG(
    order_id, line_no, order_date,
    customer_id, customer_name,
    product_id, product_name,
    quantity, unit_price_at_sale
)
~~~

**Mức hạt của một dòng** là *một dòng hàng trong một đơn hàng*, không phải một đơn hàng hay một sản phẩm. Ví dụ, đây là một số cột của bảng:

| order_id | line_no | customer_id | product_id | quantity | unit_price_at_sale |
|---|---:|---|---|---:|---:|
| DH01 | 1 | KH01 | SP01 | 2 | 6000 |
| DH01 | 2 | KH01 | SP02 | 1 | 25000 |
| DH02 | 1 | KH02 | SP01 | 3 | 6500 |

Hệ thống áp dụng các quy tắc:

1. Mỗi **mã đơn hàng** xác định đúng một ngày đặt và một khách hàng.
2. Trong mỗi đơn, **số dòng** (`line_no`) không lặp; số dòng có thể bắt đầu lại từ 1 ở đơn khác. Mỗi dòng xác định một sản phẩm, số lượng và giá bán ghi nhận lúc đặt.
3. Mỗi **mã khách hàng** tra cứu tới một tên hiện hành; mỗi **mã sản phẩm** tra cứu tới một tên hiện hành.
4. Một sản phẩm có thể được bán với **các giá khác nhau** ở các đơn khác nhau. Một đơn có thể chứa nhiều dòng, kể cả hai dòng cùng sản phẩm.

Các câu trên chứa thông tin thiết kế quan trọng hơn chính ba dòng mẫu. Chúng cho biết trường nào quyết định trường nào và ở **cấp độ** nào.

## 2. Định nghĩa phụ thuộc hàm

Với lược đồ quan hệ \(R(U)\), trong đó \(U\) là tập các thuộc tính, ký hiệu:

\[
X \rightarrow Y
\]

đọc là **\(X\) xác định hàm \(Y\)**, với \(X, Y \subseteq U\). Nó có nghĩa: đối với **mọi trạng thái dữ liệu hợp lệ theo quy tắc nghiệp vụ**, nếu hai dòng bằng nhau trên tất cả thuộc tính thuộc \(X\), chúng phải bằng nhau trên tất cả thuộc tính thuộc \(Y\).

\[
\forall t_1,t_2 \in r,\quad
t_1[X]=t_2[X] \Rightarrow t_1[Y]=t_2[Y]
\]

Ở đây \(r\) là một trạng thái hợp lệ bất kỳ của \(R\). Chẳng hạn:

- `order_id → customer_id`: hai dòng có cùng mã đơn **phải** có cùng mã khách.
- `(order_id, line_no) → quantity`: trong cùng một đơn, mỗi số dòng có đúng một số lượng.
- `product_id ↛ unit_price_at_sale`: cùng sản phẩm **có thể** được bán ở nhiều mức giá.

Mũi tên nói về **tính duy nhất của giá trị được xác định**, không nói \(Y\) phải được tính bằng công thức từ \(X\), cũng không nói \(X\) và \(Y\) có quan hệ nhân quả. Nhiều giá trị \(X\) khác nhau vẫn có thể cho cùng một giá trị \(Y\): nhiều đơn hàng cùng thuộc một khách hàng.

**Điểm cốt lõi:** dữ liệu mẫu có thể giúp *bác bỏ* một phụ thuộc khi tìm thấy hai dòng vi phạm, nhưng không thể *chứng minh* phụ thuộc đúng cho mọi dữ liệu tương lai. Muốn khẳng định phụ thuộc, cần một quy tắc nghiệp vụ hoặc một ràng buộc được xác nhận.

## 3. Chuyển câu nghiệp vụ thành phụ thuộc hàm

Một cách đọc hiệu quả là chuyển câu nghiệp vụ về dạng: **“Với mỗi giá trị \(X\), có tối đa một giá trị \(Y\) hợp lệ trong cùng phạm vi”**.

| Quy tắc đã được xác nhận | Phụ thuộc hàm | Điều kiện cần hiểu đúng |
|---|---|---|
| Mỗi đơn có một ngày đặt và một khách | `order_id → order_date, customer_id` | `order_id` là duy nhất toàn hệ thống |
| Mỗi số dòng chỉ duy nhất *trong một đơn* | `(order_id, line_no) → product_id, quantity, unit_price_at_sale` | `line_no` được phép lặp ở đơn khác |
| Mỗi mã khách có một tên hiện hành | `customer_id → customer_name` | `customer_name` là tên hiện hành, không phải tên chụp tại thời điểm mua |
| Mỗi mã sản phẩm có một tên hiện hành | `product_id → product_name` | Tên hiện hành được quản lý nhất quán |

Ngược lại, **không thể** suy ra những phụ thuộc sau từ các quy tắc trên:

| Khẳng định sai hoặc chưa có căn cứ | Phản ví dụ / lý do |
|---|---|
| `customer_id → order_id` | Một khách có thể đặt nhiều đơn |
| `order_id → product_id` | Một đơn có thể chứa nhiều sản phẩm |
| `line_no → product_id` | Dòng số 1 xuất hiện ở nhiều đơn |
| `product_id → unit_price_at_sale` | Giá giao dịch phụ thuộc từng lần bán |
| `(order_id, product_id) → line_no` | Một sản phẩm có thể xuất hiện ở nhiều dòng của cùng đơn |
| `customer_name → customer_id` | Hai khách có thể trùng tên |

Lưu ý sự khác nhau giữa **khóa định danh** và **thuộc tính mô tả**: “mã khách hàng xác định tên” không kéo theo “tên xác định mã khách hàng”.

### Phạm vi và thời gian có thể thay đổi đáp án

Trước khi ghi một phụ thuộc, luôn làm rõ:

- **Phạm vi duy nhất:** nếu mã sản phẩm chỉ duy nhất *trong một cửa hàng*, phụ thuộc đúng có thể là `(store_id, product_code) → product_name`, thay vì `product_code → product_name`.
- **Thời điểm:** `customer_id → customer_name` mô tả *tên hiện hành*. Nếu bảng lưu `customer_name_at_order` (tên chụp lại lúc đặt), cùng khách có thể có nhiều tên lịch sử. Lúc này `customer_id → customer_name_at_order` không được bảo đảm; nhưng `order_id → customer_name_at_order` có thể đúng.
- **Ngoại lệ nghiệp vụ:** nếu hệ thống cho phép sửa khách hàng gắn với đơn, phải quyết định quan hệ lưu **trạng thái hiện tại** hay **lịch sử các lần sửa**. Với lịch sử, cần thêm phiên bản hoặc thời điểm hiệu lực vào vế trái.
- **Mức hạt:** quan hệ “một dòng hàng” khác quan hệ “một lần thay đổi giá”. Chọn sai mức hạt sẽ khiến phụ thuộc trông có vẻ mâu thuẫn.

Khi quy tắc chưa rõ, hãy ghi **giả định cần xác nhận** thay vì tự đưa phụ thuộc vào mô hình.

## 4. Quy trình suy ra phụ thuộc từ yêu cầu thực tế

### Bước 1 — Xác định thực thể, thuộc tính và mức hạt

Hỏi: “Một dòng dữ liệu đại diện cho *một cái gì*?” Trong ví dụ, đó là một dòng đơn hàng. Liệt kê các thuộc tính thuộc chính dòng đó, thuộc đơn hàng, thuộc khách hàng và thuộc sản phẩm. Việc này làm lộ ra các thông tin đang bị lặp khi gộp nhiều thực thể vào một bảng.

### Bước 2 — Tìm các câu khẳng định tính duy nhất

Đọc đặc biệt kỹ các từ “mỗi”, “duy nhất”, “một”, “trong phạm vi”, “tại thời điểm”. Với câu “mỗi đơn chỉ có một khách”, thử đặt \(X = \{\text{order_id}\}\), \(Y = \{\text{customer_id}\}\).

Không biến câu “một khách **có nhiều** đơn” thành `customer_id → order_id`: nó nói về khả năng có nhiều giá trị ở vế phải, tức phủ định phụ thuộc đó.

### Bước 3 — Xác minh tính ổn định và ngoại lệ

Hỏi người phụ trách nghiệp vụ:

- Mã này là duy nhất toàn cục hay chỉ trong một tổ chức, một năm hoặc một chi nhánh?
- Một bản ghi có thể đổi người sở hữu, đổi mã, hoặc có nhiều phiên bản theo thời gian không?
- Giá trị lưu ở bảng là dữ liệu hiện tại hay **ảnh chụp lịch sử**?
- Có trường hợp ngoại lệ hợp lệ nào tạo hai giá trị \(Y\) cho cùng \(X\) không?

Một phản ví dụ **hợp lệ về nghiệp vụ** đủ để bác bỏ phụ thuộc đang xét.

### Bước 4 — Viết phụ thuộc và kiểm tra chiều ngược

Ghi theo mẫu `X → Y`, kèm định nghĩa ngắn cho \(X\), \(Y\) và phạm vi. Luôn kiểm tra `Y → X` riêng; chiều ngược không tự động đúng.

### Bước 5 — Rút gọn và xác định khóa

Nếu `(order_id, line_no) → quantity`, thử bỏ từng thuộc tính bên trái. Vì cùng một đơn có nhiều dòng và số dòng lặp giữa các đơn, không thể bỏ `order_id` hoặc `line_no`. Đây là phụ thuộc **đầy đủ** vào khóa ghép.

Nếu một vế trái còn chứa thuộc tính thừa, bỏ nó để mô hình phản ánh đúng yếu tố xác định tối thiểu. Sau đó dùng **bao đóng thuộc tính** để kiểm tra khóa.

### Bước 6 — Đối chiếu dữ liệu và thiết kế cách thực thi

Kiểm tra dữ liệu hiện có để tìm vi phạm, đối chiếu lại với người hiểu nghiệp vụ, rồi quyết định phụ thuộc nào được bảo đảm bởi khóa chính, ràng buộc duy nhất, khóa ngoại hoặc việc tách bảng. Kết quả là **tập quy tắc và giả định có thể kiểm chứng**, không chỉ là danh sách mũi tên.

## 5. Suy diễn phụ thuộc: không cần hỏi lại mọi quy tắc

Giả sử tập phụ thuộc được nghiệp vụ bảo đảm trên quan hệ `CHI_TIET_DON_HANG` là:

~~~text
F = {
  order_id              → order_date, customer_id,
  customer_id           → customer_name,
  product_id            → product_name,
  (order_id, line_no)   → product_id, quantity, unit_price_at_sale
}
~~~

Từ `order_id → customer_id` và `customer_id → customer_name`, suy ra:

~~~text
order_id → customer_name
~~~

Đó là **phụ thuộc suy diễn**: không cần một câu nghiệp vụ mới, vì nó là hệ quả logic của các phụ thuộc đã biết.

### Các tiên đề Armstrong

Ba quy tắc cơ bản, đúng cho mọi tập phụ thuộc hàm:

| Quy tắc | Phát biểu | Ví dụ |
|---|---|---|
| **Phản xạ** | Nếu \(Y \subseteq X\), thì \(X \rightarrow Y\) | `(order_id, line_no) → order_id` |
| **Tăng trưởng** | Nếu \(X \rightarrow Y\), thì \(XZ \rightarrow YZ\) | Từ `order_id → customer_id` suy ra `(order_id, line_no) → (customer_id, line_no)` |
| **Bắc cầu** | Nếu \(X \rightarrow Y\) và \(Y \rightarrow Z\), thì \(X \rightarrow Z\) | `order_id → customer_id → customer_name` |

Trong đó \(XZ\) là hợp hai tập thuộc tính \(X \cup Z\), không phải phép nhân. Từ các tiên đề này suy ra được quy tắc **phân rã** (\(X \rightarrow YZ\) kéo theo \(X \rightarrow Y\)) và **hợp** (nếu \(X \rightarrow Y\) và \(X \rightarrow Z\), thì \(X \rightarrow YZ\)).

### Tính bao đóng \(X^+\)

**Bao đóng của \(X\) theo \(F\)** là tập tất cả thuộc tính có thể suy ra từ \(X\). Thuật toán:

~~~text
closure := X
Lặp:
  Với mỗi phụ thuộc A → B trong F:
    Nếu A ⊆ closure thì thêm B vào closure.
Đến khi closure không còn thay đổi.
~~~

Với \(X = \{\text{order_id}, \text{line_no}\}\):

| Lần | Thuộc tính bổ sung | Vì sao |
|---|---|---|
| Bắt đầu | `order_id, line_no` | Chính \(X\) |
| 1 | `order_date, customer_id` | `order_id → order_date, customer_id` |
| 2 | `customer_name` | `customer_id → customer_name` |
| 3 | `product_id, quantity, unit_price_at_sale` | `(order_id, line_no) → ...` |
| 4 | `product_name` | `product_id → product_name` |

Bao đóng thu được **toàn bộ chín thuộc tính** của `CHI_TIET_DON_HANG`. Vì thế `(order_id, line_no)` là **siêu khóa**. Thử bỏ `order_id` hoặc `line_no` đều không còn xác định được toàn bộ thuộc tính, nên đây là **khóa ứng viên** (khóa tối thiểu).

Một tập \(X\) là siêu khóa khi \(X^+ = U\). Nó là khóa ứng viên khi không có tập con thực sự nào của \(X\) còn là siêu khóa. Khóa chính là một khóa ứng viên được chọn để triển khai.

### Phụ thuộc đầy đủ, bộ phận và bắc cầu

Đối với khóa ghép `(order_id, line_no)` của bảng gộp:

- **Đầy đủ:** `(order_id, line_no) → quantity`, vì không vế con nào đủ xác định `quantity`.
- **Bộ phận:** `order_id → order_date, customer_id`, vì một phần của khóa ghép đã xác định các cột đó.
- **Bắc cầu:** khóa ghép xác định `customer_id`, rồi `customer_id → customer_name`; tương tự với `product_id → product_name`.

Những trường hợp này giải thích vì sao dữ liệu tên khách, ngày đặt hoặc tên sản phẩm lặp lại trên các dòng hàng và là đầu mối để chuẩn hóa.

Khi cần tối giản tập phụ thuộc để thiết kế thuật toán, có thể tìm **phủ tối thiểu**: tách vế phải thành từng thuộc tính; loại thuộc tính thừa ở vế trái; sau đó loại phụ thuộc suy ra được từ các phụ thuộc còn lại. Một phủ tối thiểu có thể không duy nhất, nhưng phải tương đương về các phụ thuộc suy ra.

## 6. Kiểm chứng trên dữ liệu: tìm phản ví dụ, không suy luận quá mức

Giả sử dữ liệu nhập ban đầu ở bảng `staging_order_lines`. Để tìm đơn hàng xuất hiện với nhiều mã khách, chạy:

~~~sql
SELECT
    order_id,
    COUNT(DISTINCT customer_id) AS different_customers
FROM staging_order_lines
GROUP BY order_id
HAVING COUNT(DISTINCT customer_id) > 1;
~~~

Truy vấn này kiểm tra **dấu hiệu vi phạm** `order_id → customer_id` khi `customer_id` không chứa `NULL`. Ví dụ, hai dòng `DH01, KH01` và `DH01, KH02` đủ để chỉ ra dữ liệu không phù hợp với quy tắc “mỗi đơn một khách”.

Nếu không trả dòng nào, ta chỉ biết **mẫu dữ liệu đang kiểm tra chưa lộ vi phạm**. Không được kết luận phụ thuộc luôn đúng. Với `NULL`, `COUNT(DISTINCT ...)` bỏ qua giá trị thiếu; cần thống nhất chính sách xử lý `NULL` hoặc kiểm tra riêng.

Khi phát hiện vi phạm, xác minh xem đó là lỗi dữ liệu, câu nghiệp vụ chưa đầy đủ hay bảng đang gộp nhiều phiên bản/thời điểm. Không tự “sửa” nghiệp vụ bằng cách thêm cột vào khóa nếu chưa có căn cứ.

## 7. Từ phụ thuộc hàm đến lược đồ vật lý

Bảng gộp khiến cùng một `customer_name` và `product_name` xuất hiện nhiều lần. Nếu thay tên khách, phải cập nhật nhiều dòng; nếu bỏ dòng mua hàng cuối cùng, có thể mất thông tin sản phẩm. Đây là các **bất thường cập nhật, chèn và xóa** do lưu thông tin ở sai mức hạt.

Một thiết kế quan hệ phù hợp với tập phụ thuộc và các giả định nêu trên:

~~~sql
CREATE TABLE customers (
    customer_id   VARCHAR(30) PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);

CREATE TABLE products (
    product_id   VARCHAR(30) PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id    VARCHAR(30) PRIMARY KEY,
    order_date  DATE NOT NULL,
    customer_id VARCHAR(30) NOT NULL REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_id           VARCHAR(30) NOT NULL REFERENCES orders(order_id),
    line_no            INTEGER NOT NULL CHECK (line_no > 0),
    product_id         VARCHAR(30) NOT NULL REFERENCES products(product_id),
    quantity           INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_sale DECIMAL(12, 2) NOT NULL CHECK (unit_price_at_sale >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Lược đồ này thể hiện:

| Phụ thuộc / quy tắc | Cách biểu diễn |
|---|---|
| `customer_id → customer_name` | `customers.customer_id` là khóa chính |
| `product_id → product_name` | `products.product_id` là khóa chính |
| `order_id → order_date, customer_id` | `orders.order_id` là khóa chính |
| `(order_id, line_no) → product_id, quantity, unit_price_at_sale` | Khóa chính ghép của `order_items` |
| Dòng hàng phải thuộc một đơn và tham chiếu sản phẩm có thật | Khóa ngoại trong `order_items` |
| Số lượng phải dương, giá không âm | Ràng buộc `CHECK` |

**Không** đặt `UNIQUE(order_id, product_id)`, vì nghiệp vụ cho phép một sản phẩm xuất hiện nhiều dòng trong cùng đơn. **Không** đặt giá bán tại thời điểm giao dịch ở `products`, vì cùng một sản phẩm có thể được bán với nhiều giá.

Phụ thuộc hàm giúp nhận ra phụ thuộc **bộ phận** và **bắc cầu** cần xử lý khi tiến tới dạng chuẩn 2NF, 3NF. Với BCNF, yêu cầu mạnh hơn: trong mọi phụ thuộc hàm không tầm thường \(X \rightarrow Y\), \(X\) phải là siêu khóa. Tuy nhiên, bản thân phụ thuộc hàm **không thay thế** khóa ngoại, ràng buộc miền giá trị, quy tắc số lượng hay các điều kiện tồn tại. Một phụ thuộc có vế trái không phải khóa cũng không thể được thực thi đúng chỉ bằng cách tùy tiện gắn `UNIQUE` lên vế trái; cần xem lại cách tách thực thể và thiết kế bảng.

Ngoài mô hình quan hệ, tư duy “thuộc tính nào quyết định thuộc tính nào, trong phạm vi nào” còn hữu ích khi chọn khóa document, thiết kế node/edge trong đồ thị hoặc xác định mức hạt bảng phân tích. Các hệ dữ liệu đó có cơ chế ràng buộc khác nhau; không nên mặc định mọi ràng buộc SQL đều được hỗ trợ.

## 8. Bài luyện tập tự kiểm tra

**Bài 1.** Đội vận hành xác nhận: “Mỗi hóa đơn có một ngày xuất; mỗi hóa đơn có nhiều dòng; số dòng chỉ duy nhất trong một hóa đơn.” Xét `HOA_DON(invoice_id, issue_date, line_no, item_id, qty)`, với mỗi dòng xác định một mặt hàng và số lượng. Hãy viết các phụ thuộc được bảo đảm và xác định khóa.

<details>
<summary>Đáp án gợi ý</summary>

- `invoice_id → issue_date`.
- `(invoice_id, line_no) → item_id, qty`.
- `(invoice_id, line_no)` là khóa ứng viên với các quy tắc đã cho.
- Không suy ra `line_no → item_id` hoặc `invoice_id → item_id`.

</details>

**Bài 2.** “Trong mỗi cửa hàng, mỗi mã hàng có một tên hiển thị hiện hành; hai cửa hàng có thể dùng cùng mã hàng cho hai sản phẩm khác nhau.” Có thể viết `sku → display_name` không?

<details>
<summary>Đáp án gợi ý</summary>

Không. Phụ thuộc phù hợp là `(store_id, sku) → display_name` trong phạm vi dữ liệu hiện hành, nếu mỗi mã hàng chỉ ứng với một tên trong cửa hàng.

</details>

**Bài 3.** Một bảng có hai dòng cùng `product_id = SP01` nhưng `unit_price_at_sale` lần lượt là 6000 và 6500. Có thể kết luận gì?

<details>
<summary>Đáp án gợi ý</summary>

Đây là phản ví dụ bác bỏ `product_id → unit_price_at_sale` trên quan hệ chứa các giao dịch đó. Nó không bác bỏ `product_id → product_name`, và cũng không chứng minh `(product_id, order_date) → unit_price_at_sale`; một ngày vẫn có thể có nhiều mức giá.

</details>

## 9. Checklist trước khi chốt mô hình

- [ ] Đã mô tả chính xác mỗi dòng của quan hệ đại diện cho gì.
- [ ] Mỗi phụ thuộc đều có quy tắc nghiệp vụ xác nhận, không chỉ dựa vào dữ liệu mẫu.
- [ ] Đã làm rõ phạm vi định danh, thời gian hiệu lực và cách lưu dữ liệu lịch sử.
- [ ] Đã thử phản ví dụ, kiểm tra chiều ngược và bỏ thuộc tính thừa ở vế trái.
- [ ] Đã tính bao đóng để nhận diện siêu khóa và khóa ứng viên.
- [ ] Đã xem xét phụ thuộc bộ phận, bắc cầu, bất thường dữ liệu và khả năng chuẩn hóa.
- [ ] Đã ánh xạ các quy tắc sang khóa, khóa ngoại, `UNIQUE`, `CHECK` hoặc logic kiểm soát khác đúng với nghiệp vụ.

**Ghi nhớ:** Suy ra phụ thuộc hàm là quá trình làm rõ **điều gì bắt buộc đúng với mọi dữ liệu hợp lệ**. Khả năng suy diễn bằng toán học chỉ đáng tin khi các phụ thuộc đầu vào xuất phát từ quy tắc nghiệp vụ đúng và được xác định phạm vi rõ ràng.
