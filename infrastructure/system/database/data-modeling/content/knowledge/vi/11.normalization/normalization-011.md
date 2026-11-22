# Khi nào chuẩn hóa là đủ và cách tránh chia bảng thiếu mục đích

## Mục tiêu học tập

Trong **DATABASE_DATA_MODELING**, chuẩn hóa không phải cuộc thi tạo ra nhiều bảng hay đạt dạng chuẩn cao nhất bằng mọi giá. Mục tiêu thực sự là chuyển **quy tắc nghiệp vụ** thành cấu trúc dữ liệu rõ ràng, nhất quán, có thể cưỡng chế và đủ hiệu quả cho các tác vụ đọc/ghi. Một thiết kế tốt còn phải dễ tiến hóa khi nghiệp vụ thay đổi, dễ kiểm chứng bằng ràng buộc và phép thử, cũng như phù hợp với mô hình quan hệ, document, đồ thị hoặc phân tích.

Sau bài này, bạn có thể:

1. Xác định **điểm dừng hợp lý** của chuẩn hóa dựa trên phụ thuộc dữ liệu, bất thường cập nhật, ràng buộc và nhu cầu truy vấn.
2. Phân biệt **tách bảng có ý nghĩa** với các kiểu chia bảng chỉ làm tăng số phép nối.
3. Hiểu vì sao đạt **3NF hoặc BCNF** thường là một điểm xuất phát tốt cho hệ thống giao dịch, nhưng không phải quy tắc tuyệt đối; biết khi nào cần xét **4NF/5NF**.
4. Đánh giá các đánh đổi giữa **nối không mất mát**, **bảo toàn phụ thuộc**, khả năng cưỡng chế nghiệp vụ và hiệu năng.
5. Chủ động chọn hình thức phi chuẩn hóa có kiểm soát khi có bằng chứng, thay vì sao chép dữ liệu tùy tiện.
6. Dùng checklist, ví dụ SQL và tình huống thực tế để bảo vệ quyết định thiết kế trước khi triển khai.

## 1. Chuẩn hóa đủ là đủ cho mục đích nào?

**Chuẩn hóa** (*normalization*) tổ chức các thuộc tính và quan hệ sao cho những phụ thuộc dữ liệu đã xác nhận được thể hiện hợp lý, giảm dư thừa gây **bất thường chèn, cập nhật và xóa**.

Nhưng **không tồn tại một số lượng bảng “chuẩn” áp dụng cho mọi hệ thống**. Khi hỏi “đã chuẩn hóa đủ chưa?”, cần trả lời đồng thời:

- **Đúng ngữ nghĩa:** mỗi bảng biểu diễn rõ thực thể, quan hệ hoặc sự kiện nào; mỗi dòng có mức hạt nào.
- **Đúng ràng buộc:** các khóa, phụ thuộc hàm (FD), phụ thuộc đa trị (MVD) hoặc phụ thuộc nối (JD) quan trọng có được phản ánh và kiểm soát không.
- **Không có bất thường có hại:** một sự thật nghiệp vụ có phải sửa ở nhiều dòng độc lập dễ gây mâu thuẫn không; có lưu được sự kiện khi thực thể liên quan chưa phát sinh không.
- **Phân rã an toàn:** nếu tách bảng, phép chiếu rồi nối phải **khôi phục đúng dữ liệu**, không tạo bộ giả.
- **Chi phí chấp nhận được:** truy vấn chính, cập nhật, vận hành, migration, quyền truy cập và lưu lịch sử có đáp ứng yêu cầu hay không.

Một điểm dừng thực dụng là: **đã giải quyết được những bất thường quan trọng do phụ thuộc dữ liệu thực sự gây ra; mọi bảng có ý nghĩa, các ràng buộc cần thiết được kiểm soát, và việc tách thêm không tạo giá trị đáng kể so với chi phí của nó**.

Đây là **tiêu chí ra quyết định**, không phải định nghĩa hình thức của một dạng chuẩn.

## 2. Phân biệt “đạt dạng chuẩn” với “mô hình đã phù hợp”

| Mức chuẩn hóa | Tập trung xử lý | Câu hỏi khi ra quyết định |
|---|---|---|
| **1NF** | Miền giá trị và cấu trúc thuộc tính theo mô hình quan hệ | Mỗi cột có ý nghĩa và miền giá trị rõ ràng, không có nhóm lặp như các cột `phone_1,phone_2,...`? |
| **2NF** | Phụ thuộc **bộ phận** của thuộc tính không khóa vào khóa ứng viên | Có thuộc tính ở mức hạt khác nhưng bị lặp trong từng dòng của khóa ghép? |
| **3NF** | Phụ thuộc hàm gây dư thừa thông qua thuộc tính không là siêu khóa | Có phụ thuộc `X → A` không tầm thường mà `X` không là siêu khóa và `A` không thuộc khóa ứng viên nào? |
| **BCNF** | Mọi FD không tầm thường phải có vế trái là siêu khóa | Có FD làm mất nhất quán dù quan hệ đạt 3NF? Phân rã có làm khó bảo toàn phụ thuộc? |
| **4NF** | Phụ thuộc **đa trị** không tầm thường | Có hai tập giá trị độc lập bị lưu chung thành mọi tổ hợp, khiến dữ liệu phình theo tích? |
| **5NF** | Phụ thuộc **nối** không tầm thường không suy từ khóa ứng viên | Có quy tắc nghiệp vụ thật sự cho phép tái tạo quan hệ nhiều chiều từ các phép chiếu nhỏ hơn? |

Với **3NF**, điều kiện hình thức là với mỗi FD không tầm thường `X → A` được suy ra từ các quy tắc hợp lệ: **`X` là siêu khóa hoặc `A` là thuộc tính khóa** (*prime attribute*, thuộc ít nhất một khóa ứng viên). Với **BCNF**, vế trái phải là siêu khóa. Vì vậy **BCNF mạnh hơn 3NF**, nhưng một phân rã BCNF đôi khi không bảo toàn toàn bộ FD để kiểm soát cục bộ.

**Gợi ý khởi đầu:** nhiều hệ thống OLTP chọn **3NF làm mục tiêu nền tảng**, cân nhắc **BCNF** nếu phân rã phù hợp và các ràng buộc vẫn kiểm soát được. Chỉ xét **4NF/5NF** khi các quy tắc đa trị/nối có thật gây ra vấn đề. Đây là một **chiến lược mặc định để khảo sát**, không phải tuyên bố 3NF luôn tối ưu hoặc mọi bảng phải được nâng lên BCNF.

### Khi nào không cần tách tiếp?

Nếu bảng chỉ có các thuộc tính phụ thuộc vào **khóa của chính bảng**, không có phụ thuộc nghiệp vụ độc lập nào gây bất thường, và dữ liệu được cập nhật theo cùng vòng đời, việc tách tiếp thường không đem lại lợi ích về chuẩn hóa.

Chẳng hạn:

~~~text
ORDERS(order_id, customer_id, ordered_at, status)
~~~

Nếu `order_id` xác định toàn bộ các thuộc tính còn lại, `status` là **trạng thái hiện hành của đơn**, và không có FD khác giữa các thuộc tính này, việc tách:

~~~text
ORDERS(order_id, customer_id, ordered_at)
ORDER_STATUS(order_id, status)
~~~

không tự giải quyết bất thường chuẩn hóa nào. Hai bảng có thể nối một-một bằng `order_id`, nhưng tạo thêm thao tác ghi, khóa ngoại và phép nối để đọc một đơn hoàn chỉnh.

Điều đó **không có nghĩa mọi tách bảng một-một đều sai**: có thể cần tách vì bảo mật, dữ liệu lớn/ít đọc, quyền sở hữu khác nhau, tần suất cập nhật, hoặc vòng đời độc lập. Lý do lúc đó là **kiến trúc, vận hành hoặc quyền truy cập**, không phải một FD bắt buộc phải tách.

## 3. Tình huống cần chuẩn hóa: bảng đơn hàng gộp

Giả sử dữ liệu bán hàng ban đầu được xuất trong một bảng:

~~~text
ORDER_LINE_FLAT(
    order_id, ordered_at,
    customer_id, customer_name_current,
    line_no, product_id, product_name_current,
    quantity, unit_price_at_sale
)
~~~

**Mức hạt:** mỗi dòng là **một dòng sản phẩm của đơn hàng**, không phải một đơn hàng.

Quy tắc nghiệp vụ được xác nhận:

~~~text
order_id             → ordered_at, customer_id
customer_id          → customer_name_current
product_id           → product_name_current
(order_id, line_no)  → product_id, quantity, unit_price_at_sale
~~~

Giả sử `order_id` duy nhất toàn hệ thống, `line_no` duy nhất **trong một đơn**, tên khách và tên sản phẩm trong bảng gộp đều là **thông tin hiện hành**. Cùng sản phẩm có thể được bán nhiều lần với đơn giá khác nhau.

### Bất thường dữ liệu trong bảng gộp

| Vấn đề | Biểu hiện | Nguyên nhân |
|---|---|---|
| Cập nhật | Khách đổi tên nhưng chỉ một vài dòng đơn được sửa | `customer_name_current` bị lặp ở nhiều dòng dù phụ thuộc vào `customer_id` |
| Cập nhật | Đổi tên sản phẩm phải sửa hàng nghìn dòng hàng lịch sử | Thông tin sản phẩm hiện hành nằm trong từng dòng giao dịch |
| Chèn | Khó tạo đơn trước khi có sản phẩm nếu bảng bắt buộc chứa `line_no` | Trộn mức hạt **đơn** và **dòng đơn** |
| Xóa | Xóa dòng hàng cuối có thể làm mất cả thông tin đơn | Thông tin đơn chỉ sống trong dòng hàng |
| Không nhất quán | Hai dòng cùng đơn chứa `customer_id` khác nhau | Bảng cho phép vi phạm `order_id → customer_id` nếu thiếu kiểm soát |

Ở đây chuẩn hóa **có mục đích rõ ràng** vì nó tách những sự thật có **khóa và vòng đời khác nhau**.

### Phân rã có căn cứ

~~~text
CUSTOMERS(customer_id, customer_name_current)
PRODUCTS(product_id, product_name_current)
ORDERS(order_id, ordered_at, customer_id)
ORDER_ITEMS(order_id, line_no, product_id, quantity, unit_price_at_sale)
~~~

Với quy tắc trên:

- `customer_id` định danh một khách hàng và tên hiện hành.
- `product_id` định danh một sản phẩm và tên hiện hành.
- `order_id` định danh thông tin **cấp đơn**.
- `(order_id,line_no)` định danh thông tin **cấp dòng hàng**.

Đây là một phân rã có cơ sở từ FD, thay vì chia bảng tùy ý theo cảm giác “bảng có nhiều cột”.

### Ví dụ lược đồ SQL

~~~sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name_current VARCHAR(200) NOT NULL
);

CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    product_name_current VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    ordered_at TIMESTAMP NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_sale DECIMAL(12, 2) NOT NULL
        CHECK (unit_price_at_sale >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Việc thêm `status` vào `orders` phục vụ trạng thái **hiện hành**; nó không tạo thêm bảng riêng khi chưa có nhu cầu. `unit_price_at_sale` vẫn ở dòng hàng vì đây là **đơn giá giao dịch**, không phải thuộc tính được `product_id` xác định qua mọi đơn.

Trong dữ liệu đã triển khai, một đơn có thể tồn tại trước khi có dòng hàng. Điều này là một **trạng thái nghiệp vụ mới mà mô hình tách bảng biểu diễn được**; nó không mâu thuẫn với việc phân rã lossless của bảng gộp ban đầu theo các FD giả định. Nếu nghiệp vụ cấm đơn rỗng, cần có quy trình hoặc ràng buộc phù hợp ngoài các khóa ngoại đơn giản.

## 4. Phân rã phải chứng minh được hai điều khác nhau

### 4.1. Nối không mất mát (*lossless join*)

Một phân rã \(R(U)\rightarrow R_1(U_1),\ldots,R_n(U_n)\) nối không mất mát theo các ràng buộc đã xác nhận nếu:

\[
\forall r\text{ hợp lệ},\quad
r=\pi_{U_1}(r)\bowtie\cdots\bowtie\pi_{U_n}(r).
\]

Điều này bảo đảm các phép chiếu rồi nối lại **khôi phục chính xác các bộ của bảng gốc**, không sinh **bộ giả**.

Đối với **phân rã hai quan hệ theo FD**, điều kiện cần và đủ là:

\[
(U_1\cap U_2)\rightarrow U_1
\quad\text{hoặc}\quad
(U_1\cap U_2)\rightarrow U_2
\]

được suy ra từ tập FD \(F\). Ví dụ, tách dữ liệu đơn và dòng đơn trên `order_id` là lossless khi `order_id → ordered_at, customer_id` đúng và hai quan hệ con được hình thành từ các phép chiếu phù hợp.

Với phân rã nhiều quan hệ, có thể chứng minh qua **chuỗi các bước phân rã nhị phân lossless** hoặc phương pháp *chase*. Khi MVD/JD tham gia, phải dùng đúng loại phụ thuộc; không được đánh đồng “không thỏa điều kiện FD hai bảng” với “luôn lossy”.

### 4.2. Bảo toàn phụ thuộc (*dependency preservation*)

Một phân rã có thể nối đúng nhưng khiến việc kiểm tra một FD ban đầu phải **nối nhiều bảng**. Hai tiêu chí khác nhau:

| Tiêu chí | Câu hỏi | Hệ quả thực tế nếu không đạt |
|---|---|---|
| **Lossless** | Phép chiếu rồi nối có khôi phục **đúng dữ liệu** không? | Sinh bộ giả hoặc mất thông tin về tổ hợp thật |
| **Bảo toàn phụ thuộc** | Có thể suy ra các FD gốc từ những FD kiểm tra trên **từng bảng con** không? | Phải dùng kiểm tra liên bảng, trigger hoặc quy trình khác |

Ví dụ hình thức:

~~~text
R(A,B,C)
F = { AB → C, C → B }
~~~

Tách thành `R1(C,B)` và `R2(A,C)` là **lossless** vì giao `C` xác định `B`. Nhưng phụ thuộc `AB → C` **không được bảo toàn chỉ bằng các FD cục bộ**.

Do đó **đừng tách tiếp chỉ vì muốn đạt BCNF** nếu việc đánh mất khả năng kiểm tra một quy tắc quan trọng ở cấp bảng sẽ khiến hệ thống phải xử lý ngoại lệ liên bảng khó hơn. Thuật toán tổng hợp **3NF** chuẩn có thể bảo đảm vừa lossless vừa bảo toàn các FD; đó là một lý do chính đáng để giữ 3NF trong một số thiết kế.

## 5. Dấu hiệu chia bảng thiếu mục đích

### 5.1. Mỗi trường một bảng

Giả sử thiết kế:

~~~text
USER_IDENTITY(user_id, email)
USER_DISPLAY_NAME(user_id, display_name)
USER_TIMEZONE(user_id, timezone)
USER_PREFERENCES(user_id, theme)
~~~

Trong khi tất cả đều là thuộc tính đơn trị hiện hành được cập nhật trong cùng vòng đời người dùng, và chỉ có:

~~~text
user_id → email, display_name, timezone, theme
~~~

Việc tách thành bốn bảng **không khắc phục phụ thuộc bộ phận hay bắc cầu** nào. Nó làm tăng số phép nối, khả năng thiếu bản ghi vệ tinh và độ phức tạp của transaction.

Có thể một bảng:

~~~text
USERS(user_id, email, display_name, timezone, theme)
~~~

đã đủ về chuẩn hóa. Nếu `email` được nghiệp vụ xác nhận là duy nhất, thêm `UNIQUE(email)` phù hợp; không cần tạo một bảng email chỉ để cưỡng chế tính duy nhất.

**Ngoại lệ có căn cứ:** tách thông tin nhạy cảm để giới hạn quyền đọc, tách blob rất lớn ít khi dùng, tách dữ liệu do subsystem khác sở hữu, hoặc tách lịch sử nhiều phiên bản.

### 5.2. Tách “mọi danh từ” thành thực thể độc lập

Ví dụ tên đường, màu sắc hoặc trạng thái không tự động phải có bảng tra cứu riêng. Trước khi tạo `STATUS_LOOKUP`, `COLOR_LOOKUP` hoặc `UNIT_LOOKUP`, hỏi:

- Giá trị có **định danh và vòng đời riêng** không?
- Có mô tả, phân cấp, quy tắc chuyển trạng thái, đa ngôn ngữ hoặc người quản lý riêng không?
- Cần **tham chiếu nhất quán** ở nhiều nơi hay chỉ là một miền giá trị nhỏ, ổn định?
- Dữ liệu có thể được kiểm soát bằng `CHECK`, kiểu enum phù hợp hoặc validation ứng dụng không?

Nếu câu trả lời là “chỉ để bảng có ít cột hơn”, việc tách có thể thiếu mục đích. Nếu trạng thái có **quy trình phê duyệt và cấu hình vận hành** riêng, một bảng thực thể/trạng thái có thể phù hợp.

### 5.3. Lạm dụng cột định danh nhân tạo để che mất khóa nghiệp vụ

Ví dụ:

~~~text
ENROLLMENTS(enrollment_id, student_id, course_id, enrolled_at)
~~~

Nếu nghiệp vụ quy định **một sinh viên chỉ được đăng ký một lần vào một môn**, việc thêm `enrollment_id` làm khóa chính **không xóa yêu cầu** `(student_id,course_id)` là duy nhất. Phải giữ `UNIQUE(student_id,course_id)` với các cột không NULL thích hợp.

Nếu cho phép học lại, cần xác nhận khóa nghiệp vụ mới, ví dụ `(student_id,course_id,attempt_no)`. Không chọn định danh nhân tạo rồi chấp nhận các bản ghi trùng vô nghĩa.

### 5.4. Chia bảng dựa trên một phụ thuộc suy ra từ dữ liệu mẫu

Một mẫu chỉ có một sản phẩm trên mỗi đơn khiến `order_id → product_id` trông có vẻ đúng. Nếu tách `ORDER_PRODUCTS(order_id,product_id)` với một sản phẩm cho mỗi đơn, mô hình sẽ chặn hoặc làm sai các đơn có nhiều dòng. **FD phải đến từ quy tắc nghiệp vụ**, không từ sự tình cờ trong mẫu.

### 5.5. Tạo mô hình EAV mà không có nhu cầu

`ENTITY_ATTRIBUTE_VALUE(entity_id,attribute_name,value)` có thể phù hợp với thuộc tính động hiếm khi được định nghĩa trước, nhưng nếu dùng thay bảng sản phẩm có cấu trúc ổn định, nó làm khó kiểu dữ liệu, `NOT NULL`, `CHECK`, khóa ứng viên, chỉ mục và truy vấn.

“Bảng nào cũng có ba cột” không đồng nghĩa “đã chuẩn hóa tốt”. Khi lược đồ nghiệp vụ ổn định, các cột có kiểu rõ ràng thường dễ kiểm chứng và vận hành hơn.

## 6. Khi có nhiều giá trị: tách đúng quan hệ, không tách bừa thuộc tính

Giả sử người dùng có nhiều địa chỉ giao hàng:

~~~text
USER_SHIPPING_ADDRESSES(
    user_id, address_id, recipient_name, street, city, is_default
)
~~~

Nếu một người có thể có nhiều địa chỉ, đây là **tập thực thể con**, không phải một thuộc tính đơn trị của `USERS`. Bảng riêng hợp lý vì mỗi địa chỉ có định danh, vòng đời và dữ liệu riêng.

Ngược lại, một địa chỉ hiện hành duy nhất có các phần `street, city, postal_code` không bắt buộc phải được tách thành ba bảng chỉ vì nó gồm ba cột. Có thể biểu diễn trong bảng cha hoặc một value object tùy mức sử dụng và yêu cầu nghiệp vụ.

### Hai tập độc lập và 4NF

Xét:

~~~text
EMPLOYEE_PROFILE(employee_id, skill, language)
~~~

Nếu mỗi nhân viên có nhiều **kỹ năng** và nhiều **ngôn ngữ** **độc lập**, các tổ hợp kỹ năng–ngôn ngữ có thể làm bảng tăng theo tích số lượng. Phụ thuộc đa trị `employee_id ↠ skill` có thể dẫn đến phân rã:

~~~text
EMPLOYEE_SKILLS(employee_id, skill)
EMPLOYEE_LANGUAGES(employee_id, language)
~~~

Đây là tách **có mục đích**, giải quyết dư thừa MVD và giúp đạt 4NF theo các quy tắc đã xác nhận.

Nhưng nếu `SKUS(product_id,color,size)` chỉ chứa những **biến thể màu–kích thước thật sự được bán**, không được tự tách thành danh sách màu và danh sách kích thước rồi nối thành mọi tổ hợp. Phép nối có thể tạo biến thể không có thật. Tách bảng theo 4NF/5NF đòi hỏi **MVD/JD có căn cứ**, không chỉ thấy hai cột đều có nhiều giá trị.

## 7. Một ngoại lệ quan trọng: dữ liệu lịch sử và ảnh chụp giao dịch

Chuẩn hóa không có nghĩa “cấm lặp một giá trị ở mọi bảng”. Cần phân biệt **giá trị hiện hành** và **giá trị tại thời điểm sự kiện**.

Ví dụ:

~~~text
PRODUCTS(product_id, current_name, current_list_price)
ORDER_ITEMS(order_id, line_no, product_id, product_name_at_sale,
            quantity, unit_price_at_sale)
~~~

Tên sản phẩm hiện hành có thể thay đổi. Nhưng hóa đơn đã phát hành phải thể hiện **tên và giá tại lúc bán**. Trong `ORDER_ITEMS`, các giá trị snapshot được xác định bởi **khóa dòng giao dịch**, chẳng hạn `(order_id,line_no)`; chúng **không bắt buộc** tuân theo phụ thuộc `product_id → product_name_at_sale` trên mọi dòng giao dịch.

Từ chối lưu snapshot vì “đã có bảng sản phẩm” có thể làm báo cáo lịch sử thay đổi khi danh mục sản phẩm được sửa. Đây là **lặp dữ liệu có ý nghĩa ngữ nghĩa khác**, không nhất thiết là bất thường chuẩn hóa.

Điều cần ghi rõ:

- Nguồn chân lý của **thông tin hiện hành** là bảng sản phẩm.
- Nguồn chân lý của **ảnh chụp giao dịch** là bản ghi giao dịch tại thời điểm xác nhận.
- Quy tắc tạo snapshot: ghi một lần khi chốt, có hay không được hiệu chỉnh, cách lưu dấu vết nếu cần sửa.
- Các truy vấn phải chọn đúng cột hiện hành hay tại thời điểm sự kiện.

Tương tự, **bảng lịch sử trạng thái** `ORDER_STATUS_EVENTS(order_id,event_no,status,occurred_at)` có thể cần thiết khi lưu mọi lần chuyển trạng thái. Nó khác việc tách `ORDERS.status` thành một bảng một-một chỉ để “chuẩn hóa thêm”.

## 8. Bao nhiêu phép nối là chấp nhận được?

Mệnh đề “join chậm” không đủ để bác bỏ chuẩn hóa; mệnh đề “chuẩn hóa luôn nhanh” cũng không đúng. Hiệu năng phụ thuộc số dòng, lực chọn lọc của điều kiện lọc, chỉ mục, phép nối nhiều-nhiều, kiểu truy vấn và hệ quản trị.

Ví dụ truy vấn chi tiết đơn hàng:

~~~sql
SELECT
    o.order_id,
    o.ordered_at,
    c.customer_name_current,
    i.line_no,
    p.product_name_current,
    i.quantity,
    i.unit_price_at_sale
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
JOIN order_items AS i
    ON i.order_id = o.order_id
JOIN products AS p
    ON p.product_id = i.product_id
WHERE o.order_id = 1001
ORDER BY i.line_no;
~~~

Một truy vấn có vài `JOIN` theo **khóa chính/khóa ngoại** có thể hoạt động tốt với chỉ mục và thống kê phù hợp. Việc gộp lại tất cả cột thành bảng gốc để tránh join có thể tái tạo bất thường cập nhật và chi phí lưu trữ.

Ngược lại, nếu truy vấn báo cáo phải nối hàng chục quan hệ nhiều-nhiều và quét hàng tỷ dòng, mô hình đọc **riêng** như materialized view hoặc data mart có thể cần thiết.

### Cách đo trước khi tách/gộp

Định nghĩa các chỉ số thực tế:

| Nhóm chỉ số | Ví dụ cần đo | Ý nghĩa |
|---|---|---|
| Đọc | p50/p95/p99 độ trễ, số dòng đọc, thời gian CPU/I/O | Có thật sự bị join chi phối không? |
| Ghi | Số hàng cập nhật mỗi thao tác, tranh chấp, deadlock, số transaction | Dữ liệu lặp có khiến ghi nhiều nơi hoặc khó đồng bộ không? |
| Lưu trữ | Dung lượng bảng/chỉ mục, tốc độ tăng trưởng, số bộ trung gian | Tách/gộp ảnh hưởng quy mô ra sao? |
| Tính đúng | Số vi phạm ràng buộc, lỗi đồng bộ, bản ghi mồ côi | Mô hình nào giảm rủi ro mâu thuẫn? |
| Tiến hóa | Số ứng dụng cần sửa khi schema đổi, độ phức tạp migration | Tách có thực sự giảm coupling không? |

Sử dụng kế hoạch truy vấn như `EXPLAIN` hoặc công cụ quan sát tương ứng của DBMS, chạy với dữ liệu đại diện và mẫu truy vấn quan trọng. Đừng suy hiệu năng chỉ từ **số bảng**.

## 9. Phi chuẩn hóa có kiểm soát khi có bằng chứng

**Phi chuẩn hóa** (*denormalization*) chủ động tạo một cách biểu diễn dư thừa hoặc tổng hợp để phục vụ truy vấn. Nó khác với **quên chuẩn hóa** ở chỗ: phải biết nguồn chân lý, mục đích và cơ chế đồng bộ.

Ví dụ cần hiển thị số dòng của mỗi đơn trên trang danh sách. Hệ thống có thể:

1. Tính từ `ORDER_ITEMS` khi truy vấn nếu khối lượng phù hợp.
2. Dùng **view** để tái sử dụng truy vấn tổng hợp.
3. Dùng **materialized view** hoặc bảng đọc riêng `ORDER_SUMMARY(order_id,item_count,total_amount)` khi có bằng chứng lợi ích.
4. Duy trì cache ở tầng ứng dụng với chính sách hết hạn và xử lý dữ liệu cũ.

Nếu lưu `item_count` trong `ORDERS`, phải định nghĩa **bất biến**:

\[
\text{ORDERS.item\_count}
=\#\{\text{dòng hợp lệ của đơn trong ORDER\_ITEMS}\}.
\]

Cần làm rõ khi thêm/xóa/hoàn/hủy dòng hàng, `item_count` có thay đổi thế nào; cập nhật cùng transaction hay bất đồng bộ; khi lỗi đồng bộ thì tái đối soát ra sao.

### Mẫu quyết định phi chuẩn hóa

| Câu hỏi | Điều cần ghi |
|---|---|
| Vì sao cần? | Truy vấn cụ thể không đạt mục tiêu đo lường nào |
| Nguồn chân lý? | Bảng/luồng nào chứa dữ liệu gốc được phép cập nhật |
| Dữ liệu sao chép/tổng hợp? | Cột, mức hạt và phạm vi thời gian rõ ràng |
| Mức nhất quán? | Mạnh trong một transaction hay chấp nhận trễ có giới hạn |
| Cách đồng bộ? | Transaction, trigger, CDC, event, batch hoặc view |
| Cách phục hồi? | Chạy đối soát định kỳ, tính lại và phát hiện lệch |
| Cách đo thành công? | Độ trễ, tài nguyên, số lỗi trước/sau |

Nếu không trả lời được những câu hỏi này, việc gộp lại bảng để “nhanh hơn” thường là **nợ kỹ thuật chưa được kiểm soát**.

## 10. So sánh lựa chọn theo loại workload

| Tình huống | Điểm xuất phát phù hợp | Cẩn trọng |
|---|---|---|
| **OLTP: đơn hàng, thanh toán, tồn kho** | Quan hệ 3NF/BCNF tùy phụ thuộc, khóa và giao dịch rõ | Khóa nghiệp vụ, khóa ngoại, tính nhất quán và tránh cập nhật nhiều bản sao |
| **Danh mục có nhiều thuộc tính không bắt buộc** | Quan hệ rõ kiểu dữ liệu, tách thực thể con nếu có vòng đời riêng; cân nhắc document cho nhóm thuộc tính linh hoạt | Không biến mọi cột NULL thành một bảng một-một hoặc EAV tùy tiện |
| **Hồ sơ có các danh sách độc lập** | Bảng liên kết riêng hoặc mảng document có ngữ nghĩa độc lập | Không nhân tích các tập giá trị rồi coi tổ hợp là sự kiện |
| **Quan hệ mạng lưới nhiều bước** | Mô hình đồ thị khi truy vấn duyệt quan hệ là trọng tâm | Không coi mọi cạnh hai ngôi là bằng chứng cho sự kiện nhiều ngôi |
| **BI/OLAP: tổng hợp doanh thu** | Fact theo mức hạt sự kiện + dimension, thường dùng **star schema** | Tránh join nhiều-nhiều làm nhân số liệu; kiểm soát lịch sử dimension |
| **Báo cáo đọc cực nhiều, cập nhật ít** | Read model/materialized view dựa trên nguồn đã chuẩn hóa | Đồng bộ, thời gian trễ và quy trình tái tạo |

Trong kho phân tích, **star schema** có thể có dimension chứa nhiều mô tả được gộp để đơn giản hóa truy vấn. Đó là lựa chọn theo **workload đọc và mức hạt phân tích**, không phải tuyên bố các phụ thuộc dữ liệu không còn quan trọng. Với document, nhúng thông tin đơn hàng có thể hợp lý để đọc trọn đơn, nhưng phải xác định đó là **snapshot** hay **thông tin hiện hành**.

## 11. Sơ đồ quyết định: giữ, tách hay tạo read model?

~~~mermaid
flowchart TD
    A["Bắt đầu: hiểu mức hạt và quy tắc nghiệp vụ"] --> B{"Có phụ thuộc gây bất thường dữ liệu?"}
    B -->|Có| C["Đề xuất phân rã theo phụ thuộc đã xác nhận"]
    C --> D{"Lossless và ràng buộc còn kiểm soát được?"}
    D -->|Không| E["Sửa thiết kế, xem lại giả định hoặc cách cưỡng chế"]
    D -->|Có| F["Kiểm thử workload, quyền truy cập và lịch sử"]
    B -->|Không| G{"Có lý do kiến trúc/hiệu năng đo được để tách?"}
    G -->|Không| H["Giữ bảng, không chia chỉ vì có nhiều cột"]
    G -->|Có| F
    F --> I{"Đạt mục tiêu?"}
    I -->|Có| J["Chốt cấu trúc và ràng buộc"]
    I -->|Không| K["Tối ưu truy vấn/chỉ mục hoặc tạo read model có đối soát"]
    K --> F
~~~

Sơ đồ chỉ là **quy trình tư duy**. Nếu nghiệp vụ đặc thù hoặc có ràng buộc an toàn, pháp lý, quản trị dữ liệu, quyết định có thể khác; cần ghi lại căn cứ thay vì ép mọi hệ thống qua một khuôn.

## 12. Một bảng quyết định thiết kế có thể đem đi review

Giả sử nhóm đề xuất tách `ORDERS.status` thành bảng riêng. Không chỉ hỏi “có đạt BCNF không?” mà lập bảng:

| Tiêu chí | Ghi nhận với đề xuất tách `ORDER_STATUS(order_id,status)` |
|---|---|
| Quy tắc FD mới cần xử lý | **Không có** nếu `order_id → status` đã đúng và không có FD khác |
| Bất thường được loại bỏ | **Chưa chứng minh được** |
| Khóa và vòng đời độc lập | Cùng `order_id`, thường cùng vòng đời một đơn |
| Lợi ích vận hành | Có thể có nếu phân quyền riêng hoặc cập nhật status rất thường xuyên |
| Chi phí | Thêm join, bản ghi có thể bị thiếu, migration, transaction cập nhật |
| Bằng chứng hiệu năng | Cần số liệu cập nhật/tranh chấp hoặc truy vấn thực tế |
| Kết luận mặc định | **Giữ `status` ở `ORDERS`** nếu chưa có nhu cầu cụ thể |

Ngược lại, nếu cần lưu **lịch sử chuyển trạng thái**, hãy đề xuất:

~~~text
ORDER_STATUS_EVENTS(
    order_id, event_no, previous_status, new_status, changed_at, changed_by
)
~~~

với khóa nghiệp vụ được xác nhận (ví dụ `(order_id,event_no)`). Đây là **quan hệ sự kiện nhiều dòng**, phục vụ chức năng mới; không phải tách một-một vô cớ.

## 13. Migration và kiểm chứng trước khi thay lược đồ

Không chỉ thiết kế trên sơ đồ. Một thay đổi từ bảng gộp sang các bảng con cần kế hoạch chuyển dữ liệu:

1. **Chốt ngữ nghĩa và mức hạt**: xác định những FD nào thực sự được bảo đảm, nguồn dữ liệu hiện hành/lịch sử và trường hợp ngoại lệ.
2. **Kiểm tra khóa và dữ liệu lỗi**: phát hiện trùng `order_id`, trùng `(order_id,line_no)`, mã tham chiếu không tồn tại, `NULL` không hợp lệ.
3. **Tạo lược đồ con và ràng buộc**: khóa chính, khóa ngoại, `UNIQUE`, `NOT NULL`, `CHECK` phù hợp.
4. **Chuyển dữ liệu trong phạm vi kiểm soát**: đảm bảo backfill không làm mất bản ghi và xử lý các thay đổi phát sinh trong quá trình migration.
5. **So sánh tập dữ liệu**: nối các phép chiếu sau chuyển đổi với dữ liệu gốc và tìm sai khác; dùng phép kiểm tra tập hợp, không chỉ so số dòng.
6. **Chạy các kịch bản ghi/đọc**: thêm đơn chưa có dòng, nhiều dòng cùng đơn, đổi tên sản phẩm, hoàn/hủy đơn, thay đổi thông tin lịch sử.
7. **Đo và theo dõi**: latency, số lỗi ràng buộc, lỗi đồng bộ, độ phình join, đồng thời có phương án quay lại khi cần.

### SQL tìm vi phạm phụ thuộc trước khi tách

Giả sử bảng nguồn `staging_order_lines` cần thỏa `order_id → customer_id`:

~~~sql
SELECT order_id, COUNT(DISTINCT customer_id) AS customers_per_order
FROM staging_order_lines
WHERE order_id IS NOT NULL
  AND customer_id IS NOT NULL
GROUP BY order_id
HAVING COUNT(DISTINCT customer_id) > 1;
~~~

Kết quả chỉ ra những đơn có **nhiều mã khách không NULL** trên dữ liệu staging; cần kiểm tra xem đó là lỗi nguồn, thiếu phạm vi `tenant_id`/cửa hàng hay một ngoại lệ hợp lệ. Không có kết quả **không chứng minh** FD đúng theo mọi trạng thái nghiệp vụ.

### SQL so sánh sau phân rã

Khi đã có bảng gộp nguồn `staging_order_lines(order_id,customer_id,line_no,product_id,quantity)` và hai bảng `orders`, `order_items`, có thể đối chiếu **tập bộ không NULL** bằng hiệu tập hợp:

~~~sql
WITH original_rows AS (
    SELECT DISTINCT
        order_id, customer_id, line_no, product_id, quantity
    FROM staging_order_lines
    WHERE order_id IS NOT NULL
      AND customer_id IS NOT NULL
      AND line_no IS NOT NULL
      AND product_id IS NOT NULL
      AND quantity IS NOT NULL
),
reconstructed_rows AS (
    SELECT DISTINCT
        o.order_id, o.customer_id, i.line_no, i.product_id, i.quantity
    FROM orders AS o
    JOIN order_items AS i ON i.order_id = o.order_id
),
missing_rows AS (
    SELECT * FROM original_rows
    EXCEPT
    SELECT * FROM reconstructed_rows
),
extra_rows AS (
    SELECT * FROM reconstructed_rows
    EXCEPT
    SELECT * FROM original_rows
)
SELECT 'missing' AS issue, * FROM missing_rows
UNION ALL
SELECT 'extra' AS issue, * FROM extra_rows;
~~~

**Lưu ý:** ví dụ SQL này dùng `EXCEPT` (có thể phải đổi cú pháp tùy DBMS), `DISTINCT` để so tập giá trị, và chủ ý giới hạn nguồn gốc ở các dòng không NULL. Khi chuyển dữ liệu thật, phải đối soát thêm **NULL, bản ghi trùng, khóa mồ côi và sai khác theo thời gian cập nhật**. Kết quả rỗng chứng minh hai tập bằng nhau **trên snapshot được so sánh**, không tự chứng minh phân rã lossless cho mọi dữ liệu tương lai.

## 14. Các lỗi ra quyết định thường gặp

| Sai lầm | Vì sao rủi ro | Cách sửa |
|---|---|---|
| “Càng nhiều bảng thì càng chuẩn hóa tốt” | Có thể chỉ tạo các bảng một-một không giải quyết bất thường | Mỗi bảng mới phải có **lý do nghiệp vụ hoặc vận hành** |
| “Bảng có nhiều cột là sai” | Số cột không phải tiêu chí của 3NF/BCNF | Kiểm tra khóa, FD, MVD/JD và mức hạt |
| “Đã đạt 3NF thì không cần quan tâm nữa” | Có thể còn FD vi phạm BCNF, MVD hay JD có thật | Xét tiếp **khi có quy tắc và vấn đề cụ thể** |
| “BCNF luôn tốt hơn 3NF” | Có trường hợp không bảo toàn được FD khi phân rã | Cân nhắc chi phí cưỡng chế liên bảng |
| “Lưu snapshot là vi phạm chuẩn hóa” | Snapshot mô tả **thời điểm khác** dữ liệu hiện hành | Định nghĩa rõ ngữ nghĩa và nguồn chân lý |
| “Join nhiều thì phải gộp lại mọi bảng” | Có thể tái tạo bất thường và chưa chắc nhanh hơn | Đo, thêm chỉ mục, tối ưu truy vấn, tạo read model |
| “Đổi khóa chính thành UUID là đã giải quyết trùng dữ liệu” | Khóa nhân tạo không thay thế tính duy nhất nghiệp vụ | Duy trì `UNIQUE` và khóa ứng viên phù hợp |
| “Một bảng lookup cho mọi giá trị là tối ưu” | Tăng join và logic ánh xạ khi giá trị không có vòng đời | Chỉ tách khi có nhu cầu quản trị/tham chiếu |
| “Tách xong thì FK đảm bảo mọi quy tắc” | FK không diễn đạt hết FD, JD, kiểm soát thời gian hoặc điều kiện nghiệp vụ | Liệt kê ràng buộc và cách thực thi cho từng quy tắc |
| “Truy vấn trên mẫu không sai nghĩa là phân rã đúng” | Mẫu nhỏ có thể chưa bộc lộ bộ giả | Chứng minh lossless theo phụ thuộc thật, rồi dùng SQL hỗ trợ |

## 15. Bài luyện tập có lời giải

### Bài 1 — Tách một-một có bắt buộc không?

Cho `EMPLOYEES(employee_id,full_name,department_id,hire_date)`. Chỉ xác nhận `employee_id → full_name,department_id,hire_date`, không có FD khác. Có cần tách `EMPLOYEE_HIRE_DATES(employee_id,hire_date)` để đạt 3NF?

**Lời giải:** Không. Tập thuộc tính đều phụ thuộc vào khóa đơn `employee_id` và không có FD không tầm thường nào khác vi phạm 3NF theo giả định. Tách một-một có thể được cân nhắc vì quyền truy cập hoặc vận hành, nhưng **không bắt buộc vì chuẩn hóa**.

### Bài 2 — Tách có mục đích

Cho `ORDER_LINE_FLAT(order_id,customer_id,line_no,product_id,quantity)` với `order_id → customer_id` và `(order_id,line_no) → product_id,quantity`. Nên tách thế nào?

**Lời giải:** Tạo `ORDERS(order_id,customer_id)` và `ORDER_ITEMS(order_id,line_no,product_id,quantity)`. Giao của hai bảng là `order_id`; từ FD `order_id → customer_id` suy ra giao xác định toàn bộ `ORDERS`. Vì vậy phép tách **lossless**, đồng thời tách thông tin cấp đơn khỏi dòng hàng.

### Bài 3 — Dữ liệu giống nhưng ngữ nghĩa khác

Trong `PRODUCTS` có `current_name`; trong `ORDER_ITEMS` có `name_at_sale`. Có nên xóa `name_at_sale` để tránh trùng tên?

**Lời giải:** Không nên tự động xóa. `name_at_sale` là **ảnh chụp tại giao dịch**, được xác định bởi khóa dòng hàng, còn `current_name` là giá trị hiện hành của sản phẩm. Xóa snapshot có thể khiến hóa đơn lịch sử thay đổi khi đổi tên sản phẩm. Cần quy tắc lưu và sửa snapshot rõ ràng.

### Bài 4 — Kiểm tra quyết định BCNF

Cho `R(A,B,C)` với `F=\{AB→C,\ C→B\}\). Hai khóa ứng viên là `AB` và `AC`. Quan hệ đạt 3NF nhưng không BCNF. Có thể tách thành `CB` và `AC` mà vẫn lossless không? Có bảo toàn `AB→C` không?

**Lời giải:** Phân rã **lossless** vì phần giao `C` xác định `CB`. Nhưng `AB→C` **không được bảo toàn** bằng các FD cục bộ. Nếu quy tắc này quan trọng và khó kiểm tra liên bảng, giữ thiết kế **3NF** có thể là lựa chọn hợp lý.

### Bài 5 — Hai danh sách độc lập

Hệ thống lưu `PROFILE(user_id,skill,language)`, trong đó kỹ năng và ngôn ngữ là hai danh sách độc lập. Có cần lưu mọi tổ hợp kỹ năng–ngôn ngữ không?

**Lời giải:** Trong mô hình quan hệ chuẩn hóa, nên tách `USER_SKILLS(user_id,skill)` và `USER_LANGUAGES(user_id,language)` nếu MVD độc lập đúng. Điều này tránh tích Descartes và phù hợp 4NF. Nhưng nếu mỗi bộ `(skill,language)` là một năng lực ghép cặp thực sự, thì **không** được tự tách và sinh các tổ hợp không tồn tại.

### Bài 6 — Khi nào tạo bảng tổng hợp?

Trang danh sách đơn hàng đọc `item_count` mỗi giây hàng nghìn lần. Tính `COUNT(*)` từ bảng dòng hàng là nguyên nhân đã đo được khiến truy vấn không đạt mục tiêu độ trễ. Có nên sao chép `item_count` vào bảng đọc?

**Lời giải:** Có thể cân nhắc read model/materialized view hoặc cột tổng hợp, **sau khi** thử tối ưu truy vấn/chỉ mục. Phải chỉ rõ nguồn chân lý là `ORDER_ITEMS`, định nghĩa dòng nào được đếm, thời điểm cập nhật, xử lý hủy đơn, mức nhất quán và quy trình đối soát. Đây là **phi chuẩn hóa có kiểm soát**.

### Bài 7 — Dữ liệu mẫu và khóa nghiệp vụ

Trong 100 dòng `ENROLLMENTS`, không có cặp `(student_id,course_id)` trùng. Có thể đặt `UNIQUE(student_id,course_id)` ngay không?

**Lời giải:** Chưa đủ căn cứ. Hỏi nghiệp vụ có cho phép sinh viên học lại cùng môn không, có phân biệt học kỳ/lần học không. Nếu mỗi cặp được phép một lần, ràng buộc phù hợp; nếu có học lại, cần thêm thuộc tính định danh lần học hoặc cấu trúc tương ứng.

### Bài 8 — Bảng nhiều cột nhưng chỉ một khóa

Một bảng `DEVICE_READING(reading_id,device_id,observed_at,temperature,humidity,battery_level)` lưu một lần đo, mỗi `reading_id` là duy nhất. Dữ liệu đo cùng phát sinh trong một sự kiện; không có FD khác được xác nhận. Có nên tách mỗi đại lượng đo thành một bảng một-một?

**Lời giải:** Không cần để đạt 3NF. Việc tách có thể làm phức tạp ghi nhất quán và đọc nguyên một lần đo. Nếu về sau các đại lượng có tần suất lấy mẫu/nguồn/vòng đời khác nhau, cần xem lại **mức hạt sự kiện**, không tách vì số cột.

## 16. Checklist kết luận “chuẩn hóa đã đủ”

- [ ] Đã xác định **mức hạt** của từng quan hệ và phạm vi của mọi mã định danh.
- [ ] Đã liệt kê **phụ thuộc nghiệp vụ được xác nhận**, không tự suy từ dữ liệu mẫu.
- [ ] Đã tìm tất cả khóa ứng viên cần thiết và thể hiện chúng qua `PRIMARY KEY`/`UNIQUE` thích hợp.
- [ ] Các bất thường chèn, cập nhật, xóa quan trọng đã được loại bỏ hoặc có biện pháp kiểm soát rõ.
- [ ] Mọi phép phân rã được đề xuất đều có lý do và được kiểm tra **nối không mất mát**.
- [ ] Đã xem xét **bảo toàn phụ thuộc** và cách cưỡng chế quy tắc còn lại.
- [ ] Việc tiến tới BCNF/4NF/5NF xuất phát từ phụ thuộc **thật sự tồn tại** và vấn đề **có ích để giải quyết**.
- [ ] Không tạo các bảng một-một, lookup hoặc EAV chỉ để làm giảm số cột.
- [ ] Đã phân biệt **dữ liệu hiện hành** với **ảnh chụp giao dịch** và **lịch sử phiên bản**.
- [ ] Các truy vấn quan trọng đã được kiểm thử bằng dữ liệu đại diện, kế hoạch thực thi và chỉ số cụ thể.
- [ ] Nếu phi chuẩn hóa, đã xác định **nguồn chân lý, cơ chế đồng bộ, mức nhất quán và cách đối soát**.
- [ ] Có kế hoạch migration, kiểm tra dữ liệu và khả năng khôi phục khi thay đổi schema.

**Ghi nhớ:** Chuẩn hóa **đủ** không có nghĩa “dừng ở đúng 3NF” hay “cố đạt 5NF”. Đó là thời điểm mô hình đã thể hiện **đúng quy tắc và mức hạt**, giảm được dư thừa gây lỗi, giữ được khả năng khôi phục dữ liệu và kiểm soát ràng buộc, trong khi những lần chia bảng tiếp theo **không có lợi ích nghiệp vụ hoặc vận hành đủ rõ**. Hãy dùng phụ thuộc dữ liệu làm căn cứ, số liệu workload làm phép thử và chủ đích thiết kế làm tiêu chí dừng.
