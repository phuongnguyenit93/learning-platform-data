# Bao đóng tập thuộc tính và xác định khóa ứng viên

## Mục tiêu học tập

Trong **DATABASE_DATA_MODELING**, việc chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu đáng tin cậy đòi hỏi xác định được **tập thuộc tính nào đủ định danh một bản ghi**. Phép tính **bao đóng tập thuộc tính** (*attribute closure*) giúp trả lời câu hỏi đó bằng suy luận từ phụ thuộc hàm, thay vì đoán khóa theo tên cột hoặc vài dòng dữ liệu mẫu.

Sau bài học, bạn có thể:

- Giải thích \(X^+\) theo tập phụ thuộc hàm \(F\) và tính bao đóng bằng thuật toán lặp tới điểm cố định.
- Kiểm tra một phụ thuộc hàm có được suy ra từ \(F\) hay không.
- Phân biệt **siêu khóa**, **khóa ứng viên**, **khóa chính** và **khóa thay thế**.
- Tìm và chứng minh **tất cả khóa ứng viên** của một quan hệ nhỏ, kể cả khi có nhiều khóa.
- Áp dụng kết quả vào ràng buộc SQL, chuẩn hóa, lựa chọn khóa và thiết kế lược đồ có thể tiến hóa.

## 1. Vì sao cần bao đóng thuộc tính?

Giả sử hệ thống bán hàng lưu dữ liệu xuất báo cáo theo từng dòng hàng:

~~~text
ORDER_LINE_FLAT(
    order_id, line_no, order_date,
    customer_id, customer_name,
    product_id, product_name,
    quantity, unit_price_at_sale
)
~~~

Mỗi bản ghi biểu diễn **một dòng hàng trong một đơn hàng**. Từ các quy tắc nghiệp vụ đã được xác nhận:

1. Một `order_id` xác định đúng một ngày đặt và một khách hàng.
2. `line_no` chỉ duy nhất **trong phạm vi một đơn**; cặp `(order_id, line_no)` xác định sản phẩm, số lượng và đơn giá của dòng hàng.
3. Mỗi `customer_id` xác định một tên khách hiện hành; mỗi `product_id` xác định một tên sản phẩm hiện hành.
4. Một khách có thể đặt nhiều đơn; một đơn có nhiều dòng; một sản phẩm có thể được bán nhiều lần với các mức giá khác nhau.

Ta có tập phụ thuộc hàm \(F\):

~~~text
F1: order_id             → order_date, customer_id
F2: customer_id          → customer_name
F3: product_id           → product_name
F4: (order_id, line_no)  → product_id, quantity, unit_price_at_sale
~~~

**Câu hỏi:** Liệu `(order_id, line_no)` xác định được *tất cả* cột của bảng không? Có thể bỏ `order_id` hoặc `line_no` khỏi khóa không? Nếu có một khóa khác thì tìm bằng cách nào?

Phép tính bao đóng sẽ cho câu trả lời có thể kiểm chứng.

## 2. Định nghĩa \(X^+\) và quan hệ với suy diễn phụ thuộc hàm

Xét lược đồ quan hệ \(R(U)\), với \(U\) là tập thuộc tính, và tập phụ thuộc hàm \(F\) được xác nhận đúng trong mọi trạng thái hợp lệ của quan hệ.

**Bao đóng của tập thuộc tính \(X\) theo \(F\)**, ký hiệu \(X_F^+\) hoặc ngắn gọn \(X^+\), là **tập tất cả thuộc tính có thể xác định từ \(X\)** bằng các phụ thuộc trong \(F\) và các quy tắc suy diễn hợp lệ:

\[
X_F^+ = \{ A \in U \mid F \models X \rightarrow A \}.
\]

Ở đây \(F \models X\rightarrow A\) nghĩa là: trong mọi trạng thái dữ liệu thỏa \(F\), phụ thuộc \(X\rightarrow A\) đều đúng.

Hai tính chất quan trọng:

1. **Phản xạ:** \(X\subseteq X^+\). Tập bao đóng luôn chứa các thuộc tính ban đầu.
2. **Kiểm tra phụ thuộc:** \(F\models X\rightarrow Y\) **khi và chỉ khi** \(Y\subseteq X^+\).

Ví dụ, nếu `order_id → customer_id` và `customer_id → customer_name`, thì `customer_name` thuộc `{order_id}+`. Vì vậy ta suy ra `order_id → customer_name` theo **bắc cầu**, dù quy tắc này không được viết tường minh trong \(F\).

### Bao đóng \(X^+\) khác với bao đóng \(F^+\)

| Ký hiệu | Ý nghĩa | Đầu ra |
|---|---|---|
| \(X_F^+\) | Bao đóng **một tập thuộc tính \(X\)** theo \(F\) | Một **tập thuộc tính** |
| \(F^+\) | Bao đóng **tập phụ thuộc hàm \(F\)** | Tất cả **phụ thuộc hàm** suy ra từ \(F\) |

Ta thường **không cần liệt kê toàn bộ \(F^+\)** vì số phụ thuộc suy ra có thể rất lớn. Muốn kiểm tra một phụ thuộc \(X\rightarrow Y\), chỉ cần tính \(X^+\) và xem \(Y\) có nằm trong đó không.

## 3. Thuật toán tính bao đóng tới điểm cố định

Phương pháp chuẩn là bắt đầu với \(X\) và liên tục bổ sung vế phải của mọi phụ thuộc có vế trái đã nằm trong tập kết quả:

~~~text
ATTRIBUTE_CLOSURE(X, F):
    closure := copy(X)

    repeat:
        changed := false

        for each dependency (L → R) in F:
            if L ⊆ closure and R ⊈ closure:
                closure := closure ∪ R
                changed := true

    until changed = false

    return closure
~~~

Các phép toán ở đây đều là thao tác **trên tập hợp**: kiểm tra tập con (\(\subseteq\)), hợp (\(\cup\)), so sánh bằng. Không cần thứ tự duyệt phụ thuộc cố định để có kết quả đúng.

Vì `closure` **chỉ tăng** và không thể có hơn \(|U|\) thuộc tính, thuật toán sẽ dừng. Khi không có phụ thuộc nào thêm được thuộc tính, ta đã đạt **điểm cố định**. Thuật toán cho đúng tập thuộc tính có thể suy ra từ \(X\) theo các tiên đề Armstrong.

Với cách triển khai đơn giản, mỗi lần duyệt \(F\) có thể thêm ít nhất một thuộc tính mới nếu chưa dừng; do đó số vòng thêm thuộc tính không vượt quá \(|U|-|X|\). Chi phí thực tế phụ thuộc cách biểu diễn tập hợp và số phụ thuộc được kiểm tra. Không cần sinh tất cả các phụ thuộc trong \(F^+\).

### Tính bao đóng từng bước trên đơn hàng

Lấy:

\[
X=\{\text{order_id},\text{line_no}\}.
\]

| Bước | Quy tắc áp dụng | Thuộc tính mới |
|---|---|---|
| Khởi tạo | Bắt đầu từ \(X\) | `order_id, line_no` |
| 1 | F1: `order_id → order_date, customer_id` | `order_date, customer_id` |
| 2 | F4: `(order_id, line_no) → product_id, quantity, unit_price_at_sale` | `product_id, quantity, unit_price_at_sale` |
| 3 | F2: `customer_id → customer_name` | `customer_name` |
| 4 | F3: `product_id → product_name` | `product_name` |
| Kết thúc | Không còn thuộc tính mới | Bao đóng đạt điểm cố định |

Ta thu được:

~~~text
{order_id, line_no}+ =
{
    order_id, line_no, order_date,
    customer_id, customer_name,
    product_id, product_name,
    quantity, unit_price_at_sale
}
~~~

Đó chính là **toàn bộ chín thuộc tính** của `ORDER_LINE_FLAT`. Suy ra cặp `(order_id, line_no)` xác định được mọi thuộc tính của quan hệ.

Thử các tập nhỏ hơn:

~~~text
{order_id}+ =
    {order_id, order_date, customer_id, customer_name}

{line_no}+ =
    {line_no}
~~~

Cả hai tập đều không bao trùm \(U\). Do đó không thể bỏ riêng `order_id` hoặc `line_no` khỏi cặp mà vẫn xác định được tất cả cột.

## 4. Từ bao đóng đến siêu khóa và khóa ứng viên

### Siêu khóa (superkey)

Một tập thuộc tính \(K\subseteq U\) là **siêu khóa** của \(R(U)\) theo \(F\) nếu:

\[
K^+=U.
\]

Tức là từ giá trị của \(K\) ta xác định được mọi thuộc tính của một dòng. Nếu `(order_id, line_no)` là siêu khóa, thì `(order_id, line_no, product_id)` cũng là siêu khóa: thêm thuộc tính không làm mất khả năng xác định.

### Khóa ứng viên (candidate key)

Một **khóa ứng viên** là siêu khóa **tối thiểu theo phép bao hàm tập hợp**:

\[
K^+=U
\quad\text{và}\quad
\forall K'\subset K:\ (K')^+\ne U.
\]

Nói cách khác, **không thể bỏ bất kỳ thuộc tính nào khỏi \(K\)** mà vẫn giữ tính siêu khóa. Do tính đơn điệu của bao đóng, chỉ cần thử bỏ **từng thuộc tính một**: nếu mọi tập \(K-\{a\}\) đều không là siêu khóa, thì không tập con thực sự nào của \(K\) có thể là siêu khóa.

Trong ví dụ đơn hàng:

- `(order_id, line_no)` là **siêu khóa** vì bao đóng bằng \(U\).
- `order_id` riêng lẻ và `line_no` riêng lẻ đều **không** là siêu khóa.
- Vì vậy `(order_id, line_no)` là **khóa ứng viên** theo các quy tắc đã cho.
- `(order_id, line_no, product_id)` chỉ là siêu khóa **không tối thiểu**.

**“Tối thiểu” không đồng nghĩa “có ít cột nhất trong mọi khóa”.** Một quan hệ có thể có nhiều khóa ứng viên với số thuộc tính khác nhau. Chỉ cần không khóa nào chứa một siêu khóa nhỏ hơn của chính nó.

### Khóa chính và khóa thay thế

**Khóa chính** (*primary key*) là một khóa ứng viên được chọn để triển khai. Các khóa ứng viên còn lại thường gọi là **khóa thay thế** (*alternate keys*). Đừng nhầm “khóa thay thế” với **khóa thay thế nhân tạo** (*surrogate key*), ví dụ một cột `id` tự sinh. Một `id` có thể là khóa chính, nhưng không tự động làm mất yêu cầu duy nhất của khóa nghiệp vụ.

Trong mô hình quan hệ lý thuyết, khóa phải định danh một dòng và không chứa giá trị không xác định. Khi triển khai SQL, cần chú ý `NULL`: ràng buộc `UNIQUE` với cột cho phép `NULL` có cách xử lý khác nhau giữa các hệ quản trị. Nếu dùng `UNIQUE` để thể hiện khóa ứng viên, hãy bảo đảm các cột khóa đáp ứng chính sách **không NULL**.

## 5. Ví dụ có nhiều khóa ứng viên: không chỉ chọn khóa đầu tiên tìm thấy

Xét quan hệ trừu tượng:

\[
R(A,B,C,D,E)
\]

với tập phụ thuộc:

~~~text
F = {
    A  → B,
    B  → A,
    BC → D,
    D  → E
}
~~~

Giả sử \(F\) đã được nghiệp vụ xác nhận. Ta muốn tìm **tất cả** khóa ứng viên.

### Bước 1 — Xem thuộc tính bắt buộc xuất hiện

Thuộc tính `C` **không xuất hiện ở vế phải của bất kỳ phụ thuộc nào**. Nếu không có `C` ngay từ đầu, không quy tắc nào thêm được `C` vào bao đóng. Vì vậy **mọi khóa ứng viên đều phải chứa `C`**.

Đây là mẹo cắt giảm không gian tìm kiếm; lưu ý rằng việc một thuộc tính *có xuất hiện* ở vế phải **không có nghĩa** nó chắc chắn không nằm trong khóa.

### Bước 2 — Thử các tập chứa `C`

| Tập thử | Bao đóng tính được | Là siêu khóa? |
|---|---|---|
| `{C}` | `{C}` | Không |
| `{A,C}` | `{A,B,C,D,E}` | Có |
| `{B,C}` | `{A,B,C,D,E}` | Có |
| `{C,D}` | `{C,D,E}` | Không |
| `{C,E}` | `{C,E}` | Không |

Giải thích `{A,C}+`:

~~~text
Khởi đầu:     {A, C}
Theo A → B:   {A, B, C}
Theo BC → D:  {A, B, C, D}
Theo D → E:   {A, B, C, D, E}
~~~

Giải thích `{B,C}+`:

~~~text
Khởi đầu:     {B, C}
Theo B → A:   {A, B, C}
Theo BC → D:  {A, B, C, D}
Theo D → E:   {A, B, C, D, E}
~~~

### Bước 3 — Kiểm tra tối thiểu và đầy đủ

- `{A}+` chỉ chứa `A,B`; `{C}+` chỉ chứa `C`. Vậy `{A,C}` là khóa ứng viên.
- `{B}+` chỉ chứa `A,B`; `{C}+` chỉ chứa `C`. Vậy `{B,C}` là khóa ứng viên.
- Không có khóa một thuộc tính vì `C` bắt buộc nhưng `{C}+\ne U`.
- Các tổ hợp chứa `C` và cả `A` hoặc `B` cùng thuộc tính khác đều **không tối thiểu**, vì chúng chứa `{A,C}` hoặc `{B,C}`.
- Tổ hợp chỉ thêm `D` và/hoặc `E` vào `C` không thể suy ra `A` hay `B`.

Vậy **tất cả khóa ứng viên** là:

\[
\boxed{\{A,C\}\quad\text{và}\quad\{B,C\}}
\]

Hai khóa cùng hợp lệ; ta có thể chọn một làm khóa chính và giữ khóa còn lại dưới dạng ràng buộc duy nhất phù hợp.

### Hình dung đường suy diễn

~~~mermaid
flowchart LR
  A["A"] --> B["B"]
  B --> A
  B --> BC["BC (cần cả B và C)"]
  C["C"] --> BC
  BC --> D["D"]
  D --> E["E"]
~~~

Sơ đồ giúp thấy đường suy diễn nhưng **không thay thế phép bao đóng**: cạnh `BC → D` chỉ áp dụng khi **đã có đồng thời B và C**, chứ không phải chỉ một trong hai.

## 6. Quy trình tìm tất cả khóa ứng viên

Với lược đồ \(U\) và các phụ thuộc \(F\), có thể thực hiện theo các bước:

1. **Chốt quy tắc nghiệp vụ.** Xác nhận phạm vi khóa, tính duy nhất theo thời gian và các ngoại lệ. Dữ liệu mẫu không đủ chứng minh một phụ thuộc.
2. **Tách vế phải nếu cần.** Có thể viết `A → B,C` thành `A → B`, `A → C` để đọc và xử lý dễ hơn; phép tính bao đóng vẫn đúng với cả hai cách biểu diễn.
3. **Tìm thuộc tính bắt buộc.** Tập \(M=U-\operatorname{RHS}(F)\) (các thuộc tính không xuất hiện ở bất kỳ vế phải nào) phải nằm trong mọi khóa ứng viên.
4. **Tính \(M^+\).** Nếu \(M^+=U\) thì \(M\) đã là khóa ứng viên; nếu chưa, xét các tổ hợp bổ sung từ \(U-M\).
5. **Thử từ tập ít thuộc tính bổ sung đến tập nhiều hơn.** Với mỗi tập \(S\), tính \((M\cup S)^+\). Nếu bằng \(U\) và không chứa một khóa đã tìm thấy, kiểm tra tối thiểu rồi ghi nhận khóa.
6. **Loại các siêu tập của khóa đã tìm thấy.** Chúng có thể là siêu khóa nhưng chắc chắn không là khóa ứng viên.
7. **Kiểm tra đã tìm đủ.** Đảm bảo các tổ hợp còn lại không thể là khóa tối thiểu, rồi mới kết luận danh sách hoàn chỉnh.

Một dạng mã giả cho bài toán nhỏ:

~~~text
FIND_CANDIDATE_KEYS(U, F):
    mandatory := U - union_of_all_right_hand_sides(F)
    optional  := U - mandatory
    keys := empty_set_of_sets

    for each subset S of optional in ascending subset size:
        candidate := mandatory ∪ S

        if any known key K ⊆ candidate:
            continue

        if ATTRIBUTE_CLOSURE(candidate, F) = U:
            keys.add(candidate)

    return keys
~~~

Vì các tập được duyệt theo **số lượng thuộc tính tăng dần**, khi tìm được một siêu khóa chưa chứa khóa đã biết, ta có thể ghi nhận nó là khóa ứng viên: mọi tập con nhỏ hơn đã được xét. Trường hợp \(M=\varnothing\), thuật toán vẫn xét tập rỗng đầu tiên; đây là trường hợp biên hợp lệ về mặt hình thức.

**Độ phức tạp:** Một phép bao đóng có thể tính hiệu quả trên các tập hữu hạn, nhưng **liệt kê toàn bộ khóa ứng viên** có thể tốn thời gian theo cấp số mũ vì số tổ hợp và số khóa ứng viên có thể rất lớn. Hãy dùng các thuộc tính bắt buộc và loại siêu tập để cắt giảm; không nên vét cạn mọi tổ hợp trên lược đồ hàng trăm cột nếu chưa phân tích cấu trúc phụ thuộc.

## 7. Dùng bao đóng để làm ba việc khác

### 7.1. Kiểm tra phụ thuộc có suy ra được hay không

Quy tắc:

\[
F\models X\rightarrow Y\iff Y\subseteq X^+.
\]

Với ví dụ đơn hàng, `customer_name` thuộc `{order_id}+`, nên `order_id → customer_name` suy ra được. Ngược lại `product_id` không thuộc `{order_id}+`; từ tập \(F\) hiện tại **không thể suy ra** `order_id → product_id`. Đây cũng phù hợp với nghiệp vụ một đơn có nhiều dòng sản phẩm.

“Không suy ra từ \(F\)” chưa tự nó chứng minh phụ thuộc sai trong nghiệp vụ. Nếu chưa biết đủ quy tắc, cần hỏi người sở hữu nghiệp vụ và bổ sung tập \(F\) chính xác.

### 7.2. Tìm thuộc tính thừa ở vế trái

Cho quan hệ \(R(A,B,C,D,E)\) với:

~~~text
F = {
    A  → B,
    B  → C,
    AC → D,
    D  → E
}
~~~

Xét phụ thuộc `AC → D`. Để biết `C` có thừa trong vế trái hay không, tính `{A}+`:

~~~text
{A}
  → {A,B}         nhờ A → B
  → {A,B,C}       nhờ B → C
  → {A,B,C,D}     nhờ AC → D
  → {A,B,C,D,E}   nhờ D → E
~~~

Vì `D ∈ {A}+`, ta suy ra `A → D`; do đó `C` **thừa** trong vế trái của `AC → D` đối với tập \(F\). Việc này hữu ích khi tìm **phủ tối thiểu** (*minimal cover*), giảm số phụ thuộc cần xét và làm rõ yếu tố xác định thực sự.

Lưu ý: thuật toán kiểm tra thuộc tính thừa cần dùng **đúng tập phụ thuộc đang xét** và xử lý nhất quán việc thay thế phụ thuộc. Không nên xóa tùy ý cả phụ thuộc chỉ vì thấy nhiều mũi tên liên quan đến nhau.

### 7.3. Phân tích chuẩn hóa

Bao đóng giúp:

- Tìm tất cả khóa ứng viên để biết thuộc tính nào là **thuộc tính khóa** (*prime*: thuộc ít nhất một khóa ứng viên).
- Kiểm tra phụ thuộc **bộ phận**: một phần thực sự của khóa đã đủ xác định thuộc tính không khóa hay chưa.
- Xác định phụ thuộc vi phạm **3NF**: với `X → A` không tầm thường, `X` không là siêu khóa và `A` không là thuộc tính khóa.
- Xác định phụ thuộc vi phạm **BCNF**: với `X → A` không tầm thường, `X` không là siêu khóa.

Với `ORDER_LINE_FLAT`, `order_id → order_date` thể hiện thông tin ở cấp **đơn hàng**, không ở cấp **dòng hàng**; `customer_id → customer_name` thể hiện thông tin ở cấp **khách hàng**. Các phụ thuộc đó giải thích dư thừa dữ liệu, nhưng để phân rã quan hệ còn cần xem khả năng **nối không mất mát** và **bảo toàn phụ thuộc**.

## 8. Ánh xạ khóa ứng viên vào lược đồ SQL

### Khóa ghép theo quy tắc đơn hàng

Một thiết kế quan hệ phù hợp:

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

Trong `order_items`, khóa ghép `(order_id, line_no)` thể hiện chính quy tắc “mỗi số dòng duy nhất trong một đơn”. Không tạo `UNIQUE(line_no)`, vì số dòng 1 có thể lặp ở nhiều đơn. Cũng không tạo `UNIQUE(order_id, product_id)` nếu cùng sản phẩm được phép nằm ở nhiều dòng trong cùng đơn.

Các khóa ngoại và `CHECK` là **ràng buộc bổ sung**, không thể suy ra toàn bộ từ phụ thuộc hàm. Khóa chính thường được hỗ trợ bằng cấu trúc chỉ mục, nhưng loại chỉ mục và hiệu quả truy vấn còn phụ thuộc hệ quản trị và workload.

### Một thực thể có khóa nhân tạo và khóa nghiệp vụ

Giả sử mỗi sinh viên chỉ được đăng ký **một lần** cho một môn học:

~~~sql
CREATE TABLE students (
    student_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);

CREATE TABLE courses (
    course_id BIGINT PRIMARY KEY,
    course_title VARCHAR(200) NOT NULL
);

CREATE TABLE enrollments (
    enrollment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(student_id),
    course_id BIGINT NOT NULL REFERENCES courses(course_id),
    enrolled_at DATE NOT NULL,
    UNIQUE (student_id, course_id)
);
~~~

Ở bảng `enrollments`, cả `{enrollment_id}` và `{student_id, course_id}` đều là **khóa ứng viên** theo ràng buộc đã nêu. `enrollment_id` được chọn làm khóa chính, còn cặp khóa nghiệp vụ được giữ bằng `UNIQUE` và `NOT NULL`.

Nếu nghiệp vụ cho phép **học lại cùng môn**, ràng buộc `UNIQUE(student_id, course_id)` sẽ sai. Khi đó cần làm rõ khóa nghiệp vụ mới, chẳng hạn thêm `attempt_no` nếu số lần học được định danh rõ ràng. Không tự thêm thuộc tính vào khóa chỉ để né dữ liệu trùng mà chưa xác minh yêu cầu.

### Kiểm tra dữ liệu nhập có vi phạm khóa hay không

Trong bảng nhập tạm `staging_order_lines`, có thể tìm các cặp mã đơn và số dòng bị trùng:

~~~sql
SELECT order_id, line_no, COUNT(*) AS occurrences
FROM staging_order_lines
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

Truy vấn phát hiện **phản ví dụ** đối với quy tắc duy nhất nếu dữ liệu cần có tối đa một bản ghi cho một cặp. Nó không thể chứng minh khóa đúng cho dữ liệu tương lai; tính đúng đắn phải đến từ yêu cầu nghiệp vụ và được cưỡng chế bằng ràng buộc phù hợp. Cần xử lý riêng `NULL` trong dữ liệu staging trước khi chốt khóa.

## 9. Những tình huống khiến việc xác định khóa dễ sai

| Sai lầm | Vấn đề | Cách xử lý |
|---|---|---|
| Nhìn dữ liệu mẫu thấy `email` không trùng nên chọn làm khóa | Dữ liệu ít chưa chứng minh email luôn duy nhất, bất biến | Xác nhận quy tắc và cách xử lý đổi email, tài khoản dùng chung |
| Thấy `X^+=U` rồi kết luận ngay \(X\) là khóa ứng viên | \(X\) mới chắc chắn là **siêu khóa**, có thể chứa cột thừa | Thử bỏ từng thuộc tính của \(X\) |
| Chỉ tìm một khóa rồi dừng | Có thể tồn tại nhiều khóa ứng viên | Liệt kê các tập tối thiểu hoặc chứng minh đã bao phủ các trường hợp |
| Lầm siêu khóa nhiều cột là khóa “mạnh hơn” | Siêu tập của khóa chỉ thêm cột dư thừa | Chọn khóa theo tối thiểu và tính ổn định nghiệp vụ |
| Chọn mã duy nhất trong từng cửa hàng làm mã toàn cục | Thiếu phạm vi định danh | Đưa `store_id` hoặc `tenant_id` vào quy tắc nếu nghiệp vụ yêu cầu |
| Trộn dữ liệu hiện hành với lịch sử | Phụ thuộc có thể thay đổi theo thời gian | Tách phiên bản/thời điểm hoặc dùng ảnh chụp ở đúng mức hạt |
| Dùng `UNIQUE` trên cột có `NULL` như một khóa ứng viên lý thuyết | Ngữ nghĩa `NULL` của SQL khác mô hình quan hệ cổ điển | Xác định `NOT NULL` và cơ chế ràng buộc tương thích DBMS |

Các bài toán tương tự xuất hiện khi so sánh mô hình quan hệ, document, đồ thị và phân tích:

- Với **document**, khóa document phải phù hợp phạm vi duy nhất, đồng thời tránh nhầm ảnh chụp dữ liệu nhúng với thuộc tính hiện hành.
- Với **đồ thị**, định danh đỉnh/cạnh và thuộc tính duy nhất phụ thuộc quy tắc của từng loại đối tượng; không mặc nhiên suy từ ID lưu trữ nội bộ ra khóa nghiệp vụ.
- Với **phân tích**, mức hạt của fact table và khóa dimension (bao gồm phiên bản lịch sử khi có) quyết định tổ hợp thuộc tính nào thực sự xác định một dòng.

Bao đóng là công cụ hình thức cho **phụ thuộc hàm trong quan hệ**; với các mô hình khác, cần chuyển tư duy định danh và phụ thuộc sang cơ chế ràng buộc tương ứng, không giả định chúng hoạt động giống SQL.

## 10. Bài luyện tập có lời giải

### Bài 1 — Bao đóng và khóa đơn

Cho \(R(A,B,C,D)\) và:

~~~text
F = { A → B, B → C, AC → D }
~~~

**Yêu cầu:** Tính `{A}+`. `A` có phải khóa ứng viên không?

**Lời giải:** Bắt đầu `{A}`; thêm `B` nhờ `A → B`; thêm `C` nhờ `B → C`; khi đã có `A,C`, thêm `D` nhờ `AC → D`. Vậy `{A}+ = {A,B,C,D} = U`. Tập một thuộc tính `{A}` là siêu khóa, và không có tập con thực sự khác rỗng để bỏ. Với các phụ thuộc đã cho, `A` là khóa ứng viên. `A` cũng là thuộc tính bắt buộc vì không xuất hiện ở vế phải của \(F\).

### Bài 2 — Hai khóa ứng viên

Cho \(R(P,Q,R,S)\) và:

~~~text
F = { P → Q, Q → P, R → S }
~~~

**Yêu cầu:** Tìm tất cả khóa ứng viên.

**Lời giải:** `R` không nằm trong vế phải nên phải có trong mọi khóa. `{P,R}+` có `Q` nhờ `P→Q` và `S` nhờ `R→S`, nên bằng \(U\). Tương tự `{Q,R}+=U` vì `Q→P`. Không thể chỉ dùng `R`; không thể lấy `P` hoặc `Q` mà thiếu `R`. Vậy các khóa ứng viên là **`{P,R}` và `{Q,R}`**. `{P,Q,R}` là siêu khóa nhưng không tối thiểu.

### Bài 3 — Phân biệt siêu khóa và khóa ứng viên

Cho \(R(A,B,C)\), \(F=\{A\rightarrow B,\ B\rightarrow C\}\). Xét tập `{A,B}`.

**Lời giải:** `{A,B}+=\{A,B,C\}`, nên đó là **siêu khóa**. Nhưng `{A}+=\{A,B,C\}` cũng bằng \(U\), do đó `{A,B}` **không** là khóa ứng viên. Khóa ứng viên là **`{A}`**.

### Bài 4 — Kiểm tra phụ thuộc suy ra

Cho \(R(A,B,C,D,E)\), \(F=\{A\rightarrow BC,\ C\rightarrow D,\ D\rightarrow E\}\). Có suy ra `A → E` và `B → E` không?

**Lời giải:** `{A}+` lần lượt nhận `B,C`, rồi `D`, rồi `E`, nên **có** `A → E`. Trong khi đó `{B}+ = {B}` theo \(F\), nên **không suy ra được** `B → E`. Không được suy ra chiều ngược của `A → B` khi chưa có quy tắc bổ sung.

### Bài 5 — Thiếu phạm vi khóa

Nền tảng nhiều cửa hàng dùng `order_no` tăng dần từ 1 ở từng cửa hàng. Mỗi đơn có nhiều dòng `line_no` duy nhất trong đơn. Nên chọn khóa dòng hàng như thế nào?

**Lời giải:** Nếu `order_no` được phép trùng giữa các cửa hàng, khóa nghiệp vụ phù hợp có thể là **`(store_id, order_no, line_no)`**, với điều kiện tổ hợp đó thực sự duy nhất và ổn định. Chỉ `(order_no, line_no)` không đủ định danh toàn hệ thống. Nếu hệ thống có `order_id` toàn cục, vẫn có thể dùng `(order_id, line_no)` theo quy tắc tương ứng. Phải xác nhận phạm vi của mã trước khi chốt khóa.

## 11. Checklist khi thực hành

- [ ] Đã xác nhận mỗi dòng dữ liệu đại diện cho một thực thể/sự kiện ở mức hạt nào.
- [ ] Tập phụ thuộc \(F\) xuất phát từ quy tắc nghiệp vụ, có ghi rõ phạm vi và thời điểm hiệu lực.
- [ ] Thuật toán bao đóng bắt đầu từ \(X\), duyệt phụ thuộc và dừng ở điểm cố định.
- [ ] Đã dùng \(Y\subseteq X^+\) để kiểm tra phụ thuộc suy ra.
- [ ] Đã phân biệt `X+ = U` (siêu khóa) với phép kiểm tra **tối thiểu** (khóa ứng viên).
- [ ] Đã xét thuộc tính bắt buộc và các tổ hợp còn lại để tìm **tất cả** khóa ứng viên.
- [ ] Đã tách khóa chính, khóa nghiệp vụ khác và khóa nhân tạo; không bỏ quên ràng buộc duy nhất hợp lệ.
- [ ] Đã đối chiếu khóa với `NULL`, phạm vi tenant/cửa hàng, phiên bản lịch sử và các ngoại lệ.
- [ ] Đã áp dụng kết quả vào chuẩn hóa, khóa ngoại, `UNIQUE` và nhu cầu truy vấn thực tế.

**Ghi nhớ:** Tính bao đóng trả lời “**từ tập \(X\), ta suy ra được những thuộc tính nào?**”. Nếu \(X^+=U\), \(X\) là siêu khóa. Chỉ khi **không thể bỏ bất kỳ thành phần nào** mà vẫn giữ được \(X^+=U\), đó mới là khóa ứng viên. Để thiết kế dữ liệu đúng, phép suy diễn phải bắt đầu bằng **những phụ thuộc hàm thật sự được nghiệp vụ bảo đảm**.
