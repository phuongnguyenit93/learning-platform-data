# Vẽ mô hình khái niệm cho khách hàng, sản phẩm, đơn hàng và thanh toán

## Mục tiêu và sản phẩm thực hành

Trong học phần **DATABASE_DATA_MODELING**, chúng ta chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ và ràng buộc đến lược đồ logic/vật lý; đồng thời so sánh các phương án quan hệ, document, đồ thị và phân tích để thiết kế có thể tiến hóa và kiểm chứng. Bài thuộc chương **Thực hành tổng hợp** này đưa bạn đi từ một mô tả bán hàng ngắn đến **mô hình khái niệm (conceptual data model)** có thể trao đổi với người hiểu nghiệp vụ.

**Đề bài:** Một cửa hàng bán sản phẩm cho khách. Khách có thể đặt đơn hàng gồm nhiều sản phẩm; mỗi đơn có thể chưa thanh toán, được thanh toán một lần hoặc thành nhiều lần. Hệ thống cần nhớ những sản phẩm đã được đặt, số lượng và số tiền theo thỏa thuận tại thời điểm đặt; cần theo dõi các lần thanh toán kể cả khi một lần thanh toán thất bại.

**Đầu ra cần hoàn thành:**

1. Danh sách **thực thể** với định nghĩa nghiệp vụ và định danh.
2. Sơ đồ **ER khái niệm** thể hiện quan hệ, tính bắt buộc/tùy chọn và lực lượng kết hợp (*cardinality*).
3. Bộ **quy tắc nghiệp vụ** diễn đạt thành câu có thể kiểm tra bằng ví dụ.
4. Ba tới năm **kịch bản phản ví dụ** kiểm chứng mô hình có giữ được sự thật lịch sử và không đếm trùng.
5. Danh sách **giả định còn cần xác nhận** trước khi triển khai lược đồ logic hoặc vật lý.

Đây là bài dựng mô hình từ yêu cầu giả định, **không phải** mô tả quy trình của một doanh nghiệp cụ thể. Trong một dự án thật, các lựa chọn như khách mua không cần tài khoản, hoàn tiền, đơn nháp hay nhiều người thanh toán **phải được chủ sở hữu nghiệp vụ xác nhận**.

### Kiến thức bạn sẽ dùng

- **Thực thể (entity):** một loại đối tượng hoặc sự việc có danh tính và vòng đời riêng.
- **Thuộc tính (attribute):** thông tin mô tả một thực thể, với ý nghĩa và phạm vi rõ.
- **Định danh (identifier):** đặc điểm giúp phân biệt các thể hiện của cùng một thực thể.
- **Quan hệ (relationship):** cách các thực thể liên kết theo một quy tắc nghiệp vụ.
- **Cardinality/optionality:** số lượng tối thiểu và tối đa mà một đối tượng được phép liên kết.
- **Thực thể liên kết (associative entity):** một mối quan hệ nhiều-nhiều có danh tính/thuộc tính riêng, chẳng hạn **Dòng đơn hàng**.
- **Bất biến (invariant):** điều kiện phải giữ đúng trong mọi trạng thái hợp lệ theo phạm vi đã thỏa thuận.

## 1. Đọc đề và gạch chân các sự thật nghiệp vụ

Đọc câu mô tả sau trước khi xem đáp án:

> “Một khách hàng có thể tạo nhiều đơn. Mỗi đơn đã gửi mua thuộc một khách hàng và gồm ít nhất một dòng hàng. Mỗi dòng ghi một sản phẩm, số lượng và đơn giá tại thời điểm đặt. Một sản phẩm có thể xuất hiện trong nhiều đơn khác nhau. Đơn hàng có thể có nhiều lần thử thanh toán, bao gồm lần thất bại. Một lần thử thanh toán thuộc về đúng một đơn.”

Tách các mệnh đề:

| Phát biểu | Điều cần đưa vào mô hình | Câu hỏi kiểm chứng |
|---|---|---|
| Một khách có thể tạo nhiều đơn | **Customer → Order** là một-nhiều | Khách mới có 0 đơn được không? |
| Mỗi đơn đã gửi mua thuộc một khách | Mỗi **Order** có đúng một **Customer** | Có hỗ trợ guest checkout không? |
| Một đơn gồm nhiều sản phẩm | Liên hệ **Order ↔ Product** nhiều-nhiều ở mức ý niệm | Mối liên hệ có số lượng/đơn giá không? |
| Dòng hàng mang số lượng và đơn giá đã chốt | Cần thực thể **OrderLine** | Giá danh mục thay đổi có được làm đổi đơn cũ? |
| Sản phẩm có thể xuất hiện ở nhiều đơn | **Product → OrderLine** một-nhiều | Sản phẩm chưa bán có được tồn tại? |
| Một đơn có nhiều lần thử thanh toán | **Order → Payment** một-nhiều | Có thể chưa có lần thanh toán nào? |
| Thanh toán có kết quả khác nhau | Payment có **trạng thái/diễn biến** | Một lần thất bại có phải tiền đã thu? |
| Một lần thanh toán thuộc một đơn | Mỗi **Payment** có đúng một **Order** trong phạm vi bài | Có cho phép một giao dịch trả nhiều đơn? |

Không bắt đầu bằng câu “phải có bốn bảng”. Người dùng nói tới **bốn đối tượng lớn**, nhưng việc một đơn chứa sản phẩm có số lượng và giá đã thỏa thuận buộc ta phải xem xét một **thực thể nghiệp vụ thứ năm: OrderLine**.

### 1.1. Chốt giả định cho lời giải chính

Để sơ đồ có một đáp án kiểm chứng được, ta thống nhất:

1. Đơn được mô hình hóa là **đơn đã gửi/đặt hợp lệ**, không gồm giỏ hàng và nháp chưa có dòng. Mỗi đơn vì vậy có **ít nhất một dòng**.
2. Mỗi đơn có **đúng một khách hàng đã định danh**. Guest checkout chưa thuộc phạm vi sơ đồ chính.
3. Mỗi dòng gắn với **đúng một sản phẩm** trong danh mục, nhưng **số lượng và đơn giá đã chốt** là thông tin của **dòng giao dịch**, không phải thuộc tính thay đổi theo giá hiện tại của sản phẩm.
4. Một sản phẩm có thể **chưa từng được bán** hoặc xuất hiện trong nhiều dòng của nhiều đơn.
5. Một `Payment` biểu diễn **một lần xử lý/thử thanh toán riêng biệt** của một đơn, có trạng thái như `PENDING`, `FAILED`, `CAPTURED`. Một lần xử lý thất bại **không** được tính là tiền đã thu.
6. Một đơn có thể **chưa có payment**, có một payment hoặc nhiều payment do thử lại hay chia đợt. Trong bài chính, **một payment chỉ thuộc một đơn**.
7. Đơn hàng và sản phẩm đã xuất hiện trong lịch sử không được làm mất dấu vết chỉ vì khách hoặc sản phẩm đổi thông tin hay ngừng hoạt động.
8. Các khoản thuế, phí vận chuyển, hoàn tiền, coupon dùng chung và thanh toán gộp nhiều đơn **chưa** thuộc sơ đồ tối thiểu; chúng sẽ được xem như phần mở rộng.

**Phải công bố giả định trước khi vẽ.** Nếu thay giả định số 1 hoặc số 6, cardinality của sơ đồ có thể đổi; không có một sơ đồ ER “đúng tuyệt đối” cho mọi hệ bán hàng.

## 2. Chọn thực thể theo danh tính và vòng đời

### 2.1. Bốn thực thể được nêu trong yêu cầu

| Thực thể | Định nghĩa trong bài | Ví dụ một thể hiện | Không nên nhầm với |
|---|---|---|---|
| **Customer — Khách hàng** | Đối tượng được nhận diện là người/chủ tài khoản đặt đơn | Khách `C101` | Tên/email: có thể trùng hoặc thay đổi |
| **Product — Sản phẩm** | Mặt hàng danh mục có mã ổn định | Sản phẩm `P220` | Giá giao dịch tại từng lần mua |
| **SalesOrder — Đơn hàng** | Một yêu cầu mua hàng đã được gửi hợp lệ | Đơn `O9001` | Giỏ hàng, thanh toán hoặc vận chuyển |
| **Payment — Lần xử lý thanh toán** | Một lần thử thu tiền cho một đơn, với trạng thái riêng | Payment `PAY-17` thất bại | Toàn bộ trạng thái thanh toán của đơn |

### 2.2. Vì sao thêm OrderLine?

Xét đơn `O9001`:

~~~text
Sản phẩm P220: số lượng 2, đơn giá đã chốt 120.000 VND
Sản phẩm P310: số lượng 1, đơn giá đã chốt 80.000 VND
~~~

Nếu chỉ vẽ `SalesOrder — Product` nhiều-nhiều mà không mô tả dòng hàng, **số lượng và đơn giá** không có nơi gắn một cách rõ ràng. Cùng sản phẩm có thể được mua ở hai đơn với giá khác nhau. Vì thế cần:

**OrderLine — Dòng đơn hàng:** một mục hàng được ghi nhận trong một đơn cụ thể, có sản phẩm, số lượng, đơn giá/giảm giá được chốt và thứ tự dòng.

~~~text
SalesOrder(O9001)
    ├── OrderLine(1) → Product(P220), quantity=2, unitPrice=120000
    └── OrderLine(2) → Product(P310), quantity=1, unitPrice=80000
~~~

OrderLine là **thực thể liên kết** giữa Order và Product, nhưng **không phải chỉ là một bảng trung gian vô nghĩa**. Nó diễn đạt sự thật “sản phẩm này đã được đặt theo các điều kiện này trong một đơn cụ thể”.

### 2.3. Phân biệt thực thể và thuộc tính

Một khái niệm là **thuộc tính** khi chỉ mô tả một thực thể và không có danh tính/vòng đời cần quản lý độc lập trong phạm vi bài. Ví dụ:

- `customerName`: thuộc tính hiển thị của Customer.
- `orderedAt`: thời điểm nghiệp vụ của SalesOrder.
- `quantity`: thuộc tính của OrderLine.
- `paymentStatus`: trạng thái của một lần Payment.

Một khái niệm có thể trở thành **thực thể riêng** khi yêu cầu đủ chi tiết:

- `PaymentMethod` thành thực thể nếu cần quản lý phương tiện thanh toán qua nhiều lần sử dụng.
- `Address` thành thực thể/giá trị sở hữu nếu nhiều địa chỉ và lịch sử giao hàng cần quản lý.
- `Refund` thành thực thể nếu phải theo dõi từng giao dịch hoàn tiền độc lập.

Không thêm thực thể chỉ vì một danh từ xuất hiện trong giao diện; phải kiểm tra **danh tính, vòng đời, quan hệ và nhu cầu truy vấn**.

## 3. Vẽ ERD khái niệm đầu tiên

### 3.1. Sơ đồ khuyến nghị trong phạm vi bài

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : "dat"
    SALES_ORDER ||--|{ ORDER_LINE : "bao_gom"
    PRODUCT ||--o{ ORDER_LINE : "duoc_mua_trong"
    SALES_ORDER ||--o{ PAYMENT : "co_lan_thanh_toan"
~~~

Đây là **sơ đồ khái niệm**: nêu **loại đối tượng và quy tắc liên hệ**, chưa chốt tên cột khóa ngoại, kiểu SQL, chỉ mục hay cách phân vùng dữ liệu.

### 3.2. Đọc ký hiệu Crow's Foot ở từng đầu quan hệ

| Ký hiệu phía đầu thực thể | Số lượng | Ý nghĩa |
|---|---|---|
| `||` | **1..1** | Đúng một, bắt buộc |
| `o|` | **0..1** | Không hoặc một |
| `|{` | **1..N** | Một hoặc nhiều |
| `o{` | **0..N** | Không hoặc nhiều |

Ví dụ `CUSTOMER ||--o{ SALES_ORDER` nghĩa:

- Nhìn từ **một SalesOrder** sang Customer: đơn có **đúng một Customer**.
- Nhìn từ **một Customer** sang SalesOrder: khách có thể có **0 hoặc nhiều SalesOrder**.

Tương tự `SALES_ORDER ||--|{ ORDER_LINE` nghĩa:

- Một OrderLine phải thuộc **đúng một SalesOrder**.
- Một SalesOrder trong phạm vi “đơn đã gửi hợp lệ” có **ít nhất một OrderLine**.

Khi đọc ERD, luôn diễn giải **cả hai chiều**. Đừng nhìn dấu chân quạ rồi kết luận “hai bên đều nhiều”.

### 3.3. Bảng cardinality và optionality

| Quan hệ | Một đối tượng phía trái liên kết bao nhiêu đối tượng phía phải? | Một đối tượng phía phải liên kết bao nhiêu đối tượng phía trái? |
|---|---|---|
| Customer — SalesOrder | 0..N đơn cho một khách | 1 khách cho một đơn |
| SalesOrder — OrderLine | 1..N dòng cho một đơn hợp lệ | 1 đơn cho một dòng |
| Product — OrderLine | 0..N dòng cho một sản phẩm | 1 sản phẩm cho một dòng |
| SalesOrder — Payment | 0..N lần thử thanh toán cho một đơn | 1 đơn cho một payment |

**Cardinality mô tả điều được phép theo nghiệp vụ, không phải số dòng đang nhìn thấy trong dữ liệu mẫu.** Nếu dữ liệu mẫu hiện chỉ có một payment cho mỗi đơn, vẫn không đủ kết luận quan hệ là 1:1.

## 4. Định danh và thuộc tính có ý nghĩa nghiệp vụ

### 4.1. Mô tả thuộc tính ở cấp khái niệm

| Thực thể | Định danh ứng viên / danh tính | Thuộc tính nghiệp vụ tiêu biểu |
|---|---|---|
| Customer | `customerId` ổn định trong phạm vi nguồn | Tên hiển thị, trạng thái hoạt động, kênh liên hệ được phép |
| Product | `productId` hoặc SKU/biến thể ổn định đã định nghĩa | Tên, mô tả, trạng thái bán, giá danh mục hiện hành |
| SalesOrder | `orderId` ổn định; `orderNumber` hiển thị có thể khác | Thời điểm đặt, trạng thái đơn, currency, địa chỉ giao tại lúc đặt nếu cần |
| OrderLine | `(orderId,lineNo)` khi một đơn có nhiều dòng | Sản phẩm, quantity, agreedUnitPrice, lineDiscount |
| Payment | `paymentId` nội bộ/được công bố và tham chiếu provider thích hợp | Amount, currency, method, status, requestedAt, capturedAt |

Ở **mức khái niệm**, `orderId`, `lineNo` được dùng để nói **danh tính nghiệp vụ**. Chưa cần quyết định `UUID` hay `BIGINT`, khóa ghép vật lý hay surrogate key. Những quyết định đó thuộc **mô hình logic/vật lý**.

**Không mặc định email là khóa Customer.** Email có thể thay đổi, dùng chung hoặc không được cung cấp; `customerId` ổn định thường là danh tính thích hợp hơn trong bài này. Tương tự, mã hiển thị `orderNumber` có thể chỉ duy nhất trong một cửa hàng/tenant.

### 4.2. Một sản phẩm có thể có nhiều định danh theo cấp

Trong thực tế, “Sản phẩm” có thể là:

~~~text
Product: Áo thun cơ bản
  Variant / SKU: Áo thun - M - Xanh
  Variant / SKU: Áo thun - L - Xanh
~~~

Nếu khách đặt **biến thể cụ thể**, một OrderLine phải tham chiếu **SKU/Variant** chứ không chỉ tên Product chung. Có hai lựa chọn:

- **Giả định đơn giản của bài:** mỗi `Product` đã là một mặt hàng có thể bán, với mã ổn định và đơn giá tại dòng.
- **Mở rộng thực tế:** thêm `ProductVariant`; OrderLine tham chiếu chính xác Variant để không nhầm size/màu.

Không tự thêm Variant vào sơ đồ chính khi đề chưa cần, nhưng ghi giả định này để sơ đồ không đánh lừa người triển khai.

### 4.3. Thông tin nào cần giữ tại thời điểm đặt?

Giá niêm yết của Product có thể đổi từ 120.000 lên 150.000 sau khi khách đặt. Vẫn phải trả lời được: **khách đã đặt với giá nào?**

Vì vậy `agreedUnitPrice` thuộc **OrderLine**, không chỉ lưu `currentPrice` của Product.

Nếu yêu cầu đối soát chứng từ khi Product đổi tên hoặc ngừng bán, OrderLine/đơn có thể cần thêm **snapshot tên, SKU, mô tả/thuế suất tại thời điểm bán**, theo chính sách. Đây là quyết định về **lịch sử giao dịch**, không phải sao chép mọi thuộc tính Product vô điều kiện.

## 5. Hướng dẫn vẽ sơ đồ khái niệm theo các bước

### Bước 1 — Liệt kê danh từ, xác định thực thể ứng viên

Gạch chân *khách hàng, sản phẩm, đơn hàng, thanh toán*. Kiểm tra từng danh từ có danh tính riêng, có thể tồn tại độc lập và được truy vấn hay không.

### Bước 2 — Tìm sự thật ở quan hệ nhiều-nhiều

“Đơn hàng có nhiều sản phẩm; sản phẩm xuất hiện trong nhiều đơn” tạo quan hệ M:N. Hỏi: **số lượng và giá thuộc về đâu?** Nếu thuộc về lần mua cụ thể, tạo **OrderLine** làm thực thể liên kết.

### Bước 3 — Viết hai câu cho mỗi quan hệ

Ví dụ:

~~~text
Một Customer có thể có 0..N SalesOrder.
Một SalesOrder phải thuộc đúng 1 Customer.

Một SalesOrder hợp lệ gồm 1..N OrderLine.
Một OrderLine phải thuộc đúng 1 SalesOrder.

Một Product có thể xuất hiện trong 0..N OrderLine.
Một OrderLine phải tham chiếu đúng 1 Product.

Một SalesOrder có thể có 0..N Payment.
Một Payment phải thuộc đúng 1 SalesOrder.
~~~

### Bước 4 — Bổ sung danh tính và thuộc tính tối thiểu

Ghi `customerId`, `productId`, `orderId`, `(orderId,lineNo)`, `paymentId`; sau đó đặt `quantity` và `agreedUnitPrice` trên **OrderLine**, `amount` và `status` trên **Payment**.

### Bước 5 — Thử một phản ví dụ cho mỗi ký hiệu

Nếu vẽ Order–Payment 1:1, thử đơn **chưa trả tiền**, hoặc một lần payment **thất bại rồi thử lại**. Nếu sơ đồ không biểu diễn được, chỉnh quan hệ thành 0..N theo giả định đã chọn.

### Bước 6 — Ghi phạm vi và điều chưa chốt

Chỉ đánh dấu sơ đồ là “phương án đề xuất” khi đã ghi **guest checkout, đơn nháp, hoàn tiền, thanh toán gộp, sản phẩm/biến thể và trạng thái** là những câu cần xác nhận.

### Bước 7 — Review cùng người hiểu nghiệp vụ

Đừng hỏi chung “sơ đồ đúng chưa?”. Hỏi bằng **tình huống thật**: “Khách có 0 đơn thì sao?”, “Một đơn có 2 thẻ thanh toán được không?”, “Hai lần thử cùng provider trả về trùng callback thì sao?”.

## 6. Dùng một bộ dữ liệu nhỏ để thẩm định sơ đồ

Giả sử cửa hàng có:

### 6.1. Khách hàng

| Customer | Tên |
|---|---|
| `C101` | An |
| `C102` | Bình |
| `C103` | Chi |

`C103` mới đăng ký, **chưa đặt đơn**. Sự tồn tại của khách này là bằng chứng vì sao đầu SalesOrder trong quan hệ Customer–SalesOrder phải cho phép **0**.

### 6.2. Sản phẩm

| Product | Tên | Giá danh mục hiện hành |
|---|---|---:|
| `P220` | Sổ tay | 150.000 VND |
| `P310` | Bút | 80.000 VND |
| `P450` | Bình nước | 200.000 VND |

`P450` chưa có đơn nào; vẫn là Product hợp lệ. `P220` hiện giá 150.000 nhưng từng bán theo giá 120.000.

### 6.3. Đơn hàng

| Order | Customer | Trạng thái | Thời điểm đặt |
|---|---|---|---|
| `O9001` | `C101` | `CONFIRMED` | 2026-11-20 09:00 UTC |
| `O9002` | `C101` | `CONFIRMED` | 2026-11-21 10:00 UTC |
| `O9003` | `C102` | `CONFIRMED` | 2026-11-21 11:00 UTC |

`C101` có **hai đơn**, `C102` có **một đơn**, `C103` có **không đơn**.

### 6.4. Dòng hàng

| Order | Line | Product | Số lượng | Đơn giá đã chốt | Thành tiền dòng |
|---|---:|---|---:|---:|---:|
| `O9001` | 1 | `P220` | 2 | 120.000 | 240.000 |
| `O9001` | 2 | `P310` | 1 | 80.000 | 80.000 |
| `O9002` | 1 | `P220` | 1 | 150.000 | 150.000 |
| `O9003` | 1 | `P310` | 3 | 80.000 | 240.000 |

Giả định đơn giản: chưa có chiết khấu/thuế/phí vận chuyển, tất cả tính bằng VND. Do đó:

\[
\text{lineAmount}=\text{quantity}\times\text{agreedUnitPrice}.
\]

Và:

\[
\begin{aligned}
\text{O9001 total}&=240.000+80.000=320.000,\\
\text{O9002 total}&=150.000,\\
\text{O9003 total}&=240.000.
\end{aligned}
\]

**Giá hiện hành của P220 không được tính lại cho O9001.** Nếu không lưu đơn giá đã chốt trong OrderLine, chỉ cần Product đổi giá, số tiền đơn cũ sẽ bị biến dạng.

### 6.5. Các lần xử lý thanh toán

| Payment | Order | Số tiền yêu cầu | Trạng thái | Tiền được coi là đã thu? |
|---|---|---:|---|---:|
| `PAY-01` | `O9001` | 320.000 | `FAILED` | 0 |
| `PAY-02` | `O9001` | 200.000 | `CAPTURED` | 200.000 |
| `PAY-03` | `O9001` | 120.000 | `CAPTURED` | 120.000 |
| `PAY-04` | `O9003` | 240.000 | `PENDING` | 0 tại thời điểm xét |

`O9002` chưa có lần thanh toán nào. Với giả định **CAPTURED = đã ghi nhận thu tiền thành công**, ta có:

~~~text
O9001:
    Tiền hàng theo dòng = 320.000
    Tổng yêu cầu qua các lần thử = 640.000
    Tiền thực thu được ghi nhận = 200.000 + 120.000 = 320.000

O9002:
    Tiền hàng theo dòng = 150.000
    Chưa có Payment => tiền thực thu = 0

O9003:
    Tiền hàng theo dòng = 240.000
    Payment PENDING => chưa cộng vào tiền thực thu
~~~

**Điểm mấu chốt:** `SUM(Payment.amount)` trên **mọi trạng thái** không phải “tiền đã thu”. Với `O9001`, tổng số tiền của ba lần thử là 640.000 nhưng thực thu theo quy tắc ví dụ chỉ 320.000.

Nếu thanh toán có các trạng thái `AUTHORIZED`, `PARTIALLY_CAPTURED`, `VOIDED`, `REFUNDED` hoặc có nhiều capture cho một authorization, phải định nghĩa lại **grain của Payment** hoặc thêm **PaymentCapture/Refund** để không nhầm “đã cho phép giữ tiền” với “đã thu”.

## 7. Kiểm tra sơ đồ bằng những câu hỏi “có thể xảy ra không?”

### 7.1. Khách chưa từng mua

**Tình huống:** `C103` tồn tại nhưng chưa có đơn.

**Kỳ vọng:** Hợp lệ. Quan hệ Customer → SalesOrder có phía đơn là **0..N**, không phải **1..N**.

### 7.2. Sản phẩm chưa từng bán

**Tình huống:** `P450` đã được công bố lên danh mục nhưng chưa nằm trong OrderLine nào.

**Kỳ vọng:** Hợp lệ. Product → OrderLine cho phép **0..N**. Xóa Product chỉ vì chưa được bán là quyết định nghiệp vụ riêng.

### 7.3. Một đơn có nhiều loại sản phẩm

**Tình huống:** `O9001` có P220 và P310.

**Kỳ vọng:** Hợp lệ. Một SalesOrder liên kết **nhiều OrderLine**. Mỗi OrderLine nối tới một Product; không cố lưu `productId1`, `productId2` trực tiếp trong SalesOrder.

### 7.4. Một sản phẩm xuất hiện trong nhiều đơn với giá khác nhau

**Tình huống:** P220 trong `O9001` có giá 120.000; trong `O9002` có giá 150.000.

**Kỳ vọng:** Hợp lệ. Giá giao dịch thuộc **OrderLine**. Một giá trên Product không đủ diễn đạt lịch sử mua.

### 7.5. Đơn chưa thanh toán

**Tình huống:** `O9002` đã được đặt nhưng chưa bấm thanh toán.

**Kỳ vọng:** Hợp lệ. SalesOrder → Payment cho phép **0**.

### 7.6. Thanh toán bị từ chối rồi thử lại

**Tình huống:** `PAY-01` thất bại; hai lần sau `PAY-02`, `PAY-03` thu tiền đủ theo hai đợt.

**Kỳ vọng:** Có **ba Payment** liên kết với cùng Order; mỗi Payment mang trạng thái và số tiền riêng. Không cập nhật đè `PAY-01` thành thành công nếu nghiệp vụ cần giữ lịch sử thử thanh toán.

### 7.7. Một dòng hàng không có đơn

**Tình huống:** Có `OrderLine` cho P220 nhưng không xác định được SalesOrder.

**Kỳ vọng:** Không hợp lệ theo phạm vi bài. Mỗi OrderLine thuộc **đúng một** SalesOrder. Dòng nằm trong giỏ hàng hoặc báo giá chưa phải OrderLine của đơn đã đặt, trừ khi mở rộng mô hình.

### 7.8. Một Payment không thuộc đơn nào

**Tình huống:** Provider gửi giao dịch chưa map được `orderId`.

**Kỳ vọng:** Hệ tích hợp có thể cần giữ thông điệp trong **vùng chờ đối soát**; nhưng **Payment nghiệp vụ đã được chấp nhận vào sơ đồ chính** phải liên kết đúng một SalesOrder. Không tự gán giao dịch đó vào đơn ngẫu nhiên chỉ để thỏa quan hệ.

## 8. Chuyển sơ đồ thành quy tắc nghiệp vụ có thể kiểm tra

Một sơ đồ ER không thể tự diễn đạt tất cả các bất biến. Hãy viết các quy tắc thành câu:

| Mã | Quy tắc | Phép thử/đối chiếu |
|---|---|---|
| BR-01 | Mỗi đơn đã đặt thuộc đúng một khách đã định danh | Không có đơn không biết Customer |
| BR-02 | Một khách có thể không có đơn | Khách C103 hợp lệ |
| BR-03 | Một đơn đã đặt có ít nhất một dòng | Không nhận đơn confirmed với 0 OrderLine |
| BR-04 | Mỗi OrderLine thuộc đúng một Order và tham chiếu một Product | Không có dòng mồ côi |
| BR-05 | Một Product có thể chưa được đặt | P450 hợp lệ |
| BR-06 | Quantity của dòng là số dương theo phạm vi bài | Không có dòng quantity = 0 hay âm |
| BR-07 | Giá giao dịch được chốt ở OrderLine, không tính lại từ Product | O9001 giữ giá P220 = 120.000 |
| BR-08 | Mỗi Payment biểu diễn một lần xử lý riêng | Payment ID phân biệt các lần thử |
| BR-09 | Đơn có thể có 0..N Payment | O9002 có 0; O9001 có 3 |
| BR-10 | Payment thuộc đúng một Order trong phạm vi bài | Không phân bổ một Payment cho nhiều đơn |
| BR-11 | Payment `FAILED`/`PENDING` không cộng vào tiền đã thu | O9001 không cộng PAY-01 |
| BR-12 | Currency và công thức tiền của đơn/payment phải nhất quán | Không cộng hai tiền tệ khác nhau |
| BR-13 | Không xóa lịch sử đơn khi sản phẩm đổi giá hoặc ẩn khỏi danh mục | Đơn cũ vẫn tra cứu, đối soát được |
| BR-14 | Callback/payment request gửi lại không tạo bản ghi giao dịch logic trùng | Idempotency theo khóa từ provider |

Một số quy tắc là **ràng buộc đơn giản** (mỗi OrderLine có một Product), nhưng có quy tắc cần **ứng dụng hoặc transaction** (đơn phải có ít nhất một dòng khi confirm), hay **tích hợp với provider** (thanh toán bị gửi lặp). Mô hình khái niệm giúp chúng ta nhận ra quy tắc; **không có nghĩa tất cả có thể được biểu diễn chỉ bằng FK**.

### 8.1. “Tổng tiền đơn” không phải lúc nào cũng bằng tổng tiền Payment

Đừng viết một bất biến chung kiểu:

~~~text
SUM(OrderLine.amount) = SUM(Payment.amount) ở mọi thời điểm
~~~

Nó sai khi đơn chưa thanh toán, thanh toán thất bại, thanh toán dở dang, thanh toán nhiều đợt, thuế/phí, giảm giá cấp đơn, hoàn tiền hoặc giao dịch chờ đối soát.

Thay vào đó, tài liệu phải phân biệt:

- **Merchandise subtotal:** tổng tiền hàng đã chốt theo OrderLine.
- **Payable amount:** số tiền đơn phải trả sau các thành phần áp dụng.
- **Captured amount:** tổng tiền đã thực thu theo các giao dịch/capture hợp lệ.
- **Refunded amount:** tổng tiền đã hoàn, nếu mô hình hỗ trợ hoàn.
- **Outstanding balance:** số còn phải thu theo định nghĩa tài chính được phê duyệt.

Ở ví dụ tối giản, *payable* tạm bằng *subtotal*, nhưng **không ép thành quy tắc áp dụng mọi cửa hàng**.

### 8.2. Tính nhất quán của trạng thái đơn và trạng thái thanh toán

Order có thể mang:

~~~text
OrderStatus: CONFIRMED, CANCELLED, FULFILLED ...
~~~

Payment có thể mang:

~~~text
PaymentStatus: PENDING, FAILED, CAPTURED ...
~~~

Đây là **hai vòng đời khác nhau**. Đơn `CONFIRMED` chưa chắc `PAID`. Một payment `CAPTURED` cũng không tự chứng minh sản phẩm đã giao.

Nếu cần trạng thái “`PAID`” ở cấp đơn, phải xác định nó là **trạng thái nghiệp vụ được quản lý** hay **trạng thái suy ra từ số đã thu và khoản phải trả**. Nếu lưu cả hai, cần quy tắc cập nhật và đối soát để không lệch.

## 9. Hai sơ đồ sai thường gặp và cách sửa

### Sai lầm A — Gắn sản phẩm trực tiếp vào đơn

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : "dat"
    SALES_ORDER }o--o{ PRODUCT : "mua"
    SALES_ORDER ||--o{ PAYMENT : "thanh_toan"
~~~

Sơ đồ này diễn đạt quan hệ Order–Product nhiều-nhiều, nhưng **chưa chỉ ra nơi lưu số lượng, đơn giá chốt, thứ tự dòng và chiết khấu theo dòng**. Nếu hệ chỉ cần “đơn có liên hệ với sản phẩm nào” thì M:N đơn thuần có thể đủ. Với đề thực hành này, **không đủ**.

**Sửa:** tạo `OrderLine` và đưa các thuộc tính của một lần mua lên thực thể này. Sau đó quan hệ còn hai cạnh 1:N với đối tượng OrderLine.

### Sai lầm B — Buộc mỗi đơn có đúng một Payment

~~~mermaid
erDiagram
    SALES_ORDER ||--|| PAYMENT : "chi_mot_lan"
~~~

Một đơn chưa thanh toán không thể tồn tại; một đơn bị từ chối rồi thử lại không thể ghi đủ các lần xử lý. Sơ đồ sai ngay trên bộ dữ liệu ví dụ.

**Sửa:** `SALES_ORDER ||--o{ PAYMENT`, đồng thời thống nhất Payment là **một lần thử/giao dịch**, không phải trạng thái tổng hợp của cả đơn.

### Sai lầm C — Đặt số lượng vào Product

Nếu Product có một thuộc tính `quantity` mà không làm rõ ý nghĩa, câu hỏi “đơn O9001 mua bao nhiêu P220?” không thể trả lời bằng số lượng tồn kho hay số lượng trong danh mục. **Số lượng đặt** thuộc **OrderLine**; **số lượng tồn kho** thuộc mô hình kho tại địa điểm/thời gian riêng nếu hệ cần.

### Sai lầm D — Dùng tên hoặc mã hiển thị làm khóa

Khách trùng tên, sản phẩm có tên giống nhau và số đơn có thể lặp giữa cửa hàng. Dùng `customerName` hoặc `productName` làm định danh khiến hai đối tượng hợp lệ bị gộp. Chọn một **ID ổn định có namespace rõ** trước khi chuyển sang lược đồ logic.

## 10. Vẽ lại ERD có thuộc tính để hoàn thiện bài nộp

Sau khi chốt quan hệ, có thể bổ sung những thuộc tính quan trọng lên sơ đồ. Ở đây `string`, `number`, `money`, `datetime` chỉ là **nhãn kiểu mô tả để minh họa trong Mermaid**, không phải cam kết về kiểu SQL hoặc quy tắc tiền tệ trên DBMS.

~~~mermaid
erDiagram
    CUSTOMER {
        string customerId
        string displayName
        string lifecycleStatus
    }
    PRODUCT {
        string productId
        string productName
        money currentListPrice
        string catalogStatus
    }
    SALES_ORDER {
        string orderId
        string orderNumber
        datetime placedAt
        string currency
        string orderStatus
    }
    ORDER_LINE {
        number lineNo
        number quantity
        money agreedUnitPrice
        money lineDiscount
    }
    PAYMENT {
        string paymentId
        string providerReference
        money requestedAmount
        string currency
        string paymentStatus
        datetime requestedAt
    }

    CUSTOMER ||--o{ SALES_ORDER : "dat"
    SALES_ORDER ||--|{ ORDER_LINE : "chua"
    PRODUCT ||--o{ ORDER_LINE : "co_trong"
    SALES_ORDER ||--o{ PAYMENT : "thu_thanh_toan"
~~~

### Cách đọc sơ đồ thuộc tính

- `CUSTOMER.customerId` xác định một Customer, **không lấy tên** làm khóa.
- `SALES_ORDER.orderId` xác định một Order, còn `orderNumber` có thể là mã chứng từ.
- `ORDER_LINE.lineNo` được hiểu **trong phạm vi một order**; nó không được thiết kế như một số độc lập duy nhất toàn hệ. Danh tính ví dụ là `(orderId,lineNo)`.
- `ORDER_LINE.agreedUnitPrice` và `lineDiscount` mô tả điều kiện mua; số tiền dòng có thể dẫn xuất theo công thức.
- `PRODUCT.currentListPrice` mô tả danh mục **hiện hành**; không được thay giá đã chốt của dòng.
- `PAYMENT.requestedAmount` là số tiền yêu cầu xử lý, **không** đồng nghĩa tiền đã thu trong mọi trạng thái.

**Ghi chú về bản vẽ:** Mermaid đòi một cách biểu diễn thuộc tính có nhãn kiểu; ở đây ta chưa đặt `PRIMARY KEY`, `FOREIGN KEY`, `VARCHAR(40)`, kiểu index hay constraint SQL. Các quyết định đó thuộc những bước thiết kế tiếp theo.

## 11. Những câu hỏi làm mô hình thay đổi

Không phải mọi biến thể của hệ bán hàng đều nên ép vào một ERD tối thiểu. Người học cần biết **khi nào phải sửa giả định**.

### 11.1. Cửa hàng cho mua không cần tài khoản

Đề mới: “Khách có thể mua không cần đăng ký. Một đơn vẫn có người mua và thông tin liên lạc tại lúc đặt.”

Có ít nhất hai cách:

**Cách A — Customer là mọi định danh người mua:** tạo một Customer/Buyer identity ổn định cho cả guest, với chính sách riêng về thông tin liên hệ và quyền. Khi đó quan hệ mỗi SalesOrder thuộc đúng một Customer có thể giữ nguyên, nhưng **định nghĩa Customer thay đổi**.

**Cách B — Order có thể không tham chiếu Customer đăng ký:** điều chỉnh quan hệ tới `REGISTERED_CUSTOMER` thành **0..1**, đồng thời giữ những trường thông tin giao dịch tối thiểu của khách vãng lai theo chính sách:

~~~mermaid
erDiagram
    REGISTERED_CUSTOMER o|--o{ SALES_ORDER : "co_the_dat"
    SALES_ORDER ||--|{ ORDER_LINE : "chua"
~~~

Một đơn guest có thể không có RegisteredCustomer; một đơn khách đăng ký có tối đa một RegisteredCustomer. Trường hợp có thông tin người đặt hoặc người nhận hàng phải được biểu diễn **riêng theo yêu cầu nghiệp vụ**, không lấy `NULL customerId` làm bằng chứng đơn không có người mua.

**Không chọn một cách chỉ vì dễ thêm cột.** Cần hỏi hệ có nhận diện guest quay lại, quyền truy cập đơn guest, chính sách PII/retention và chuyện guest sau đó đăng ký thành tài khoản như thế nào.

### 11.2. Đơn nháp hoặc giỏ hàng chưa có dòng

Nếu cùng thực thể `SalesOrder` được tạo ngay khi mở giỏ, ban đầu có thể có **0 OrderLine**. Quan hệ Order → OrderLine phải là **0..N** ở mức toàn bộ vòng đời; quy tắc **“đơn CONFIRMED có ít nhất một dòng”** trở thành ràng buộc **phụ thuộc trạng thái**.

Một lựa chọn khác là tạo thực thể `Cart` độc lập với `SalesOrder`; khi checkout hợp lệ mới tạo đơn với ít nhất một dòng. Hai phương án khác nhau về vòng đời, đồng bộ tồn kho, định danh và nhu cầu lưu lịch sử giỏ.

**Sơ đồ 1..N của lời giải chính chỉ áp dụng cho đơn đã đặt**, không khẳng định mọi hệ cần tạo Order khi giỏ có ít nhất một sản phẩm.

### 11.3. Một sản phẩm có thể lặp trong cùng một đơn

Một đơn có hai dòng cùng `productId=P220`, chẳng hạn:

~~~text
lineNo=1: P220, quantity=1, giá thường
lineNo=2: P220, quantity=1, gói quà hoặc giá khuyến mại khác
~~~

Nếu điều này hợp lệ, khóa `(orderId,productId)` **không được chọn làm danh tính dòng hàng**. `(orderId,lineNo)` hoặc một `orderLineId` ổn định phù hợp hơn. Nếu nghiệp vụ bắt buộc gộp mọi sản phẩm giống nhau thành một dòng, quy tắc đó phải được viết và kiểm chứng.

### 11.4. Một giao dịch ngân hàng thanh toán cho nhiều đơn

Lời giải chính giả định một `Payment` thuộc đúng một Order. Nhưng nếu một chuyển khoản có thể thanh toán cho `O9001` và `O9002` cùng lúc, quan hệ này **không còn đúng**.

Cần thực thể liên kết **PaymentAllocation**, với ngữ nghĩa “một phần của giao dịch thanh toán được phân bổ cho một đơn”. Phương án khái niệm:

~~~mermaid
erDiagram
    SALES_ORDER ||--o{ PAYMENT_ALLOCATION : "duoc_phan_bo"
    PAYMENT ||--o{ PAYMENT_ALLOCATION : "duoc_phan_bo_vao"
~~~

Giờ:

- Một Payment có thể có **0..N PaymentAllocation** khi mới nhận và còn đợi đối soát; có thể thành **1..N** nếu yêu cầu chỉ công nhận giao dịch sau khi gắn đơn.
- Một SalesOrder có thể nhận phân bổ từ nhiều Payment.
- Mỗi PaymentAllocation gắn **đúng một** Payment và **đúng một** SalesOrder.
- Phải có **allocatedAmount, currency, trạng thái và bất biến chống phân bổ vượt tiền hợp lệ** theo chính sách tài chính.

Đừng chỉ vẽ `SALES_ORDER }o--o{ PAYMENT` mà quên số tiền của **mỗi phần phân bổ**. Chính PaymentAllocation là nơi mang thuộc tính của quan hệ M:N.

### 11.5. Hoàn tiền một phần hoặc nhiều lần

Nếu một lần `CAPTURED` có thể được hoàn lại thành hai đợt, không nên chỉ đổi Payment từ `CAPTURED` sang `REFUNDED` rồi mất dấu tiền đã thu và từng lần hoàn.

Một mô hình mở rộng:

~~~mermaid
erDiagram
    SALES_ORDER ||--o{ PAYMENT : "co_thanh_toan"
    PAYMENT ||--o{ REFUND : "co_hoan_tien"
~~~

Giả định mỗi Refund gắn với đúng một Payment đã được thu và **một Payment có thể có 0..N Refund**. Thêm `refundId`, số tiền hoàn, trạng thái, thời điểm, tham chiếu provider và quy tắc chống hoàn quá mức. Nếu provider cho phép hoàn trả ở cấp đơn hoặc phân bổ xuyên payment, lại cần mô hình khác.

**Không tự cộng số `Refund.requestedAmount` vào tổng đã hoàn** nếu các refund chưa thực hiện thành công.

### 11.6. Mỗi đơn có nhiều người tham gia

Người mua, người nhận, người được xuất hóa đơn và người thanh toán **không nhất thiết là cùng một Customer**. Nếu nghiệp vụ cần phân biệt, đặt tên vai trò `Buyer`, `Recipient`, `BillToParty`, `Payer` và quyết định họ là các loại quan hệ hay thực thể riêng.

Không sử dụng một `customer_id` chung để mặc định thay thế mọi vai trò. **Tên giống nhau không có nghĩa hai khái niệm có cùng danh tính hoặc trách nhiệm**.

### 11.7. Mặt hàng ngừng bán hoặc khách được ẩn danh

Product `P220` có thể ngừng bán vào tháng sau, Customer `C101` có thể yêu cầu đóng tài khoản. Điều đó **không mặc nhiên cho phép xóa tất cả OrderLine và Payment liên quan**, vì các giao dịch có thể cần được giữ theo nghĩa vụ đối soát/hợp đồng.

Mô hình khái niệm cần mô tả **vòng đời**:

- Product có thể chuyển trạng thái `INACTIVE` mà lịch sử đặt hàng vẫn tham chiếu được.
- Dòng đơn đã chốt có thể giữ dữ liệu chứng từ tối thiểu/đúng thẩm quyền.
- Customer có thể bị ẩn danh hoặc tách dữ liệu cá nhân tùy chính sách; không tùy tiện giữ PII ngoài thời hạn hợp lệ.
- Dữ liệu Payment thường chứa thông tin nhạy cảm. Contract dữ liệu không nên sao chép token/thẻ vào Order một cách vô thức.

Chi tiết retention và xóa cần quyết định cùng chủ sở hữu dữ liệu/pháp lý; **ERD không tự giải quyết các yêu cầu bảo vệ dữ liệu**.

## 12. Phân biệt mô hình khái niệm với logic và vật lý

### 12.1. Cấp độ khái niệm — *đang làm trong bài*

Trả lời **đối tượng nào tồn tại, liên hệ thế nào và quy tắc nào đúng**:

~~~text
Customer 1 — 0..N SalesOrder
SalesOrder 1 — 1..N OrderLine
Product 1 — 0..N OrderLine
SalesOrder 1 — 0..N Payment
~~~

Không cần quyết định `BIGINT`/UUID, chuẩn index, partition, tên cột FK, vị trí lưu hoặc chọn PostgreSQL/MySQL/document DB.

### 12.2. Cấp độ logic — triển khai ý nghĩa thành lược đồ có khóa

Nếu lựa chọn mô hình quan hệ, một **phác thảo logic**, chưa phải SQL sản xuất, có thể là:

~~~text
Customer(
    customer_id [identifier],
    display_name,
    lifecycle_status
)

Product(
    product_id [identifier],
    product_name,
    current_list_price,
    catalog_status
)

SalesOrder(
    order_id [identifier],
    customer_id [references Customer],
    placed_at,
    currency,
    order_status
)

OrderLine(
    order_id [references SalesOrder],
    line_no,
    product_id [references Product],
    quantity,
    agreed_unit_price,
    line_discount
)

Payment(
    payment_id [identifier],
    order_id [references SalesOrder],
    provider_reference,
    amount,
    currency,
    status,
    requested_at
)
~~~

Điểm khác biệt:

- `OrderLine` có định danh ví dụ `(order_id,line_no)`.
- `SalesOrder.customer_id`, `OrderLine.product_id`, `Payment.order_id` là các **liên kết logic** tương ứng với ERD.
- Những điều như **một Order phải có ít nhất một Line khi CONFIRMED**, **không thu vượt chính sách** và **idempotency callback** có thể cần transaction/ứng dụng, không chỉ FK.
- Giá trị `current_list_price` là thuộc tính danh mục hiện hành, không phải `agreed_unit_price` của từng dòng.

### 12.3. Cấp độ vật lý — tối ưu cho một DBMS và workload

Sau khi mô hình logic đã được duyệt, mới quyết định:

- `customer_id`, `order_id` dùng UUID, BIGINT hay ID có namespace?
- Các cột tiền dùng `NUMERIC` hay số nguyên đơn vị tiền nhỏ nhất? Ràng buộc currency và precision?
- Index nào hỗ trợ truy vấn “đơn của khách”, “thanh toán chưa đối soát”?
- `UNIQUE(provider, providerReference)` có đúng phạm vi và vòng đời giao dịch không?
- Số lượng dòng/Payment lớn đến mức nào; có cần phân vùng theo thời gian?
- Có cần transaction, foreign key, outbox, audit, retention và encryption riêng?

**Đừng lấy đặc điểm ORM hoặc DBMS làm lý do thay đổi cardinality nghiệp vụ.** Một công nghệ khác có thể lưu OrderLine trong mảng document, nhưng sự thật “một đơn có nhiều dòng và một sản phẩm có thể có trong nhiều đơn” vẫn phải được mô hình hóa đúng.

## 13. Từ mô hình khái niệm đến các phép kiểm thử có thể chạy

**ERD là một giả thuyết về cấu trúc nghiệp vụ.** Để chứng minh nó phù hợp, hãy chuyển các quan hệ thành các trường hợp đầu vào hợp lệ/không hợp lệ rồi kiểm chứng tại lớp ứng dụng và cơ sở dữ liệu tương ứng.

### 13.1. Bảng quyết định cho một đơn đã đặt

| Khách có tồn tại? | Số dòng | Mỗi dòng có Product hợp lệ? | Kết quả theo giả định bài |
|---|---:|---|---|
| Có | 1 | Có | Chấp nhận, nếu các điều kiện khác hợp lệ |
| Có | 3 | Có | Chấp nhận |
| Có | 0 | — | Từ chối **xác nhận đơn** |
| Không | 1 | Có | Từ chối trong phạm vi không hỗ trợ guest |
| Có | 1 | Không | Từ chối hoặc giữ lại để sửa dữ liệu nguồn; không tự gán Product |

Nếu hệ hỗ trợ đơn nháp, dòng `số dòng = 0` có thể được phép khi `orderStatus='DRAFT'` nhưng vẫn không được phép khi chuyển `CONFIRMED` theo chính sách đã chọn.

### 13.2. Bảng quyết định thanh toán

| Đơn | Số Payment | Tình huống | Hợp lệ về mặt cấu trúc? |
|---|---:|---|---|
| `O9002` | 0 | Chưa thử thanh toán | Có |
| `O9003` | 1 | Một payment đang chờ | Có |
| `O9001` | 3 | Một FAILED, hai CAPTURED | Có |
| `O9001` | 2 | Hai Payment khác ID nhưng cùng event provider được gửi lại | Có thể là **dữ liệu trùng logic**, cần idempotency |
| Không có Order tương ứng | 1 | Payment chưa gán đơn | Không thuộc Payment đã được chấp nhận ở mô hình tối thiểu |

**“Hợp lệ về mặt cấu trúc” chưa đồng nghĩa “hợp lệ về nghiệp vụ tiền”.** Ví dụ một Payment `CAPTURED` có `amount=-100` không hợp lệ theo giả định số tiền thu không âm; Payment cùng provider reference có thể là callback trùng. Những quy tắc ấy phải được kiểm tra thêm.

### 13.3. Pseudo-code kiểm tra một lần checkout

~~~text
confirmOrder(customerId, draftLines):
    assert customerId identifies an eligible Customer
    assert draftLines contains at least one line

    for each line:
        assert product exists and may be ordered
        assert quantity > 0
        assert agreedUnitPrice is accepted and currency is defined

    in one consistent operation / transaction:
        create SalesOrder with stable ID
        create its OrderLine records
        persist agreed prices and quantities
        record a valid order state transition

    return orderId
~~~

Đây là **mã giả quy tắc nghiệp vụ**, chưa phải thiết kế transaction phân tán với tồn kho hay payment. Nếu cần giữ chỗ tồn kho, tính khuyến mại, vận chuyển hoặc thuế, đó là những bước/miền dữ liệu có bất biến bổ sung.

### 13.4. SQL minh họa kiểm tra grain và tổng tiền

Giả sử nhóm triển khai lược đồ quan hệ logic ở phần trước và thêm khóa/kiểu vật lý tương ứng. Những câu SQL sau là **minh họa bước kiểm chứng sau khi đã triển khai**, không phải lệnh bắt buộc trong ERD khái niệm.

Kiểm tra không có hai dòng có cùng danh tính `(order_id,line_no)`:

~~~sql
SELECT order_id, line_no, COUNT(*) AS occurrences
FROM order_line
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

Nếu `order_id` chỉ duy nhất theo tenant, câu truy vấn và khóa phải thêm `tenant_id`; đừng dùng `order_id` riêng chỉ vì dữ liệu thử chưa trùng.

Kiểm tra đơn đã xác nhận mà thiếu dòng hàng:

~~~sql
SELECT o.order_id
FROM sales_order AS o
LEFT JOIN order_line AS l
  ON l.order_id = o.order_id
WHERE o.order_status = 'CONFIRMED'
GROUP BY o.order_id
HAVING COUNT(l.line_no) = 0;
~~~

Đây là phép **kiểm tra hậu kỳ**. Ràng buộc “không xác nhận đơn rỗng” tốt nhất được bảo vệ trong quy trình chuyển trạng thái có transaction/ràng buộc phù hợp; **FK từ OrderLine tới Order tự nó không bắt buộc Order phải có ít nhất một Line**.

Tính subtotal cấp đơn và tiền thu **trong hai phép tổng hợp riêng**:

~~~sql
WITH line_subtotals AS (
    SELECT
        order_id,
        SUM(
            quantity * agreed_unit_price - line_discount
        ) AS merchandise_subtotal
    FROM order_line
    GROUP BY order_id
),
captured_payments AS (
    SELECT
        order_id,
        SUM(amount) AS captured_amount
    FROM payment
    WHERE payment_status = 'CAPTURED'
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(l.merchandise_subtotal, 0) AS merchandise_subtotal,
    COALESCE(p.captured_amount, 0) AS captured_amount
FROM sales_order AS o
LEFT JOIN line_subtotals AS l ON l.order_id = o.order_id
LEFT JOIN captured_payments AS p ON p.order_id = o.order_id;
~~~

**Tại sao tổng hợp riêng?** Một đơn có 2 OrderLine và 3 Payment. JOIN trực tiếp:

~~~text
SalesOrder
   JOIN OrderLine   → 2 dòng
   JOIN Payment     → 2 × 3 = 6 dòng
~~~

Nếu `SUM(lineAmount)` trên 6 dòng nối, mỗi khoản tiền hàng có thể lặp **3 lần**; nếu `SUM(paymentAmount)`, mỗi payment có thể lặp **2 lần**. Đây là lỗi **fanout**. Phải giữ grain và tổng hợp mỗi nguồn đến **cấp đơn** trước khi nối hai measure.

Trong ví dụ, `COALESCE` từ không có payment thành 0 được dùng **có chủ đích** cho báo cáo “tổng tiền đã ghi nhận thu”, không có nghĩa ta được biến mọi giá trị `NULL` của mọi nghiệp vụ thành số 0.

### 13.5. Kiểm tra số tiền bằng ca kiểm thử đầu cuối

~~~text
Given:
    O9001 has lines: 2 × 120000 and 1 × 80000
    PAY-01: FAILED, 320000
    PAY-02: CAPTURED, 200000
    PAY-03: CAPTURED, 120000

When:
    compute order merchandise subtotal
    compute captured amount

Then:
    merchandise subtotal = 320000 VND
    captured amount = 320000 VND
    captured payment count = 2
    payment attempt count = 3
~~~

Nếu báo cáo trả `payment attempt count=2`, nó đã bỏ sót lần thất bại. Nếu trả `captured amount=640000`, nó đã cộng cả yêu cầu thất bại hoặc làm nhân dòng qua JOIN.

## 14. API, sự kiện và thời gian: những ranh giới không nên bỏ qua

Mô hình khái niệm có thể được dùng để tạo hợp đồng cho dịch vụ khác, nhưng **API response và event không bắt buộc trùng cấu trúc lưu trữ**.

### 14.1. API xem đơn hiện tại

Một API dành cho khách có thể trả một phép chiếu:

~~~json
{
  "orderId": "O9001",
  "status": "CONFIRMED",
  "currency": "VND",
  "lines": [
    {"lineNo": 1, "productCode": "P220", "quantity": 2, "agreedUnitPrice": "120000.00"},
    {"lineNo": 2, "productCode": "P310", "quantity": 1, "agreedUnitPrice": "80000.00"}
  ],
  "merchandiseSubtotal": "320000.00",
  "paymentSummary": {
    "capturedAmount": "320000.00"
  }
}
~~~

Hợp đồng này không cần tiết lộ toàn bộ thông tin Provider, các lần FAILED hoặc dữ liệu kỹ thuật, nếu mục đích chỉ là hiển thị tổng hợp. Nhưng **bộ phận đối soát** có thể cần API riêng xem lịch sử Payment chi tiết.

### 14.2. Sự kiện không phải bản sao bảng

Ví dụ:

~~~json
{
  "eventId": "evt-001",
  "eventType": "order.confirmed",
  "occurredAt": "2026-11-20T09:00:00Z",
  "orderId": "O9001",
  "schemaVersion": 1
}
~~~

Event biểu diễn **đơn đã được xác nhận tại một thời điểm**, không phải toàn bộ trạng thái hiện tại của đơn. Sự kiện có ID riêng để xử lý trùng; một đơn có thể có nhiều sự kiện như xác nhận, hủy, giao hàng. Khi thực tế một hệ cho phép “thanh toán trước khi xác nhận”, lại cần quy trình/ràng buộc vòng đời khác giả định bài.

### 14.3. Thời gian và lịch sử phải có nghĩa

Phân biệt:

- `placedAt`: lúc đơn được đặt.
- `agreedUnitPrice`: giá áp dụng tại thời điểm chốt dòng.
- `payment.requestedAt`: lúc tạo lần thử thanh toán.
- `payment.capturedAt`: lúc lần xử lý được xác nhận đã thu, nếu có.
- `ingestedAt`: lúc pipeline nhận dữ liệu, nếu tích hợp dữ liệu sang kho phân tích.

Đừng lấy `ingestedAt` làm ngày bán hay ngày thu. Nếu Product đổi tên, giá hoặc trạng thái sau khi đặt, chứng từ lịch sử phải giữ ý nghĩa tại thời điểm giao dịch theo quy tắc đã thỏa thuận.

### 14.4. Các lựa chọn bảo vệ dữ liệu

ERD thường chỉ vẽ quan hệ, nhưng triển khai thật còn cần:

- Kiểm tra quyền: khách `C101` chỉ xem những đơn họ được phép xem; biết `orderId` không tự cấp quyền.
- Không nhúng số thẻ/tokens thanh toán nhạy cảm vào các bảng đơn thông thường.
- Tách dữ liệu danh tính hiện hành và dữ liệu chứng từ cần lưu theo chính sách.
- Có quy tắc ẩn danh/xóa dữ liệu khách và retention các bản ghi dẫn xuất.
- Idempotency khi provider gửi callback cùng `providerReference` nhiều lần; phạm vi duy nhất của reference có thể phụ thuộc provider/account và loại sự kiện.

Đây là các **yêu cầu liên quan** được ghi để chuyển sang mô hình logic và thiết kế tích hợp, không phải lý do biến ERD khái niệm thành một bản liệt kê mọi API, index hoặc giao thức.

## 15. Một biểu mẫu review ERD cho nhóm học

Trước khi nộp, có thể tự điền bảng:

| Câu hỏi review | Trả lời của lời giải chính |
|---|---|
| Đơn vị nghiệp vụ đang mô hình hóa? | Khách, sản phẩm, đơn đã đặt, dòng đã đặt, lần xử lý thanh toán |
| Có tổng cộng bao nhiêu loại thực thể? | **5 loại** trong sơ đồ tối thiểu |
| Thực thể liên kết bắt buộc? | **OrderLine** |
| Một Customer có bao nhiêu Order? | **0..N** |
| Mỗi Order có mấy Customer? | **1** trong giả định không guest |
| Một Order có bao nhiêu OrderLine? | **1..N** khi chỉ mô hình hóa đơn đã đặt |
| Mỗi OrderLine có bao nhiêu Product? | **1** |
| Một Product thuộc bao nhiêu OrderLine? | **0..N** |
| Một Order có bao nhiêu Payment? | **0..N** |
| Mỗi Payment thuộc bao nhiêu Order? | **1** |
| Giá mua thực tế đặt ở đâu? | **OrderLine.agreedUnitPrice** |
| Có đếm FAILED như tiền thu không? | **Không** |
| Có cộng giá hàng và tiền Payment sau JOIN trực tiếp không? | **Không**, tổng hợp theo grain trước |
| Những gì cần hỏi thêm? | Guest/draft/variant/refund/allocation/currency/tax/retention |

Một bài nộp tốt không chỉ có sơ đồ; nên có **một trang quyết định thiết kế**:

~~~text
Model: Customer – Product – SalesOrder – OrderLine – Payment
Scope: confirmed/placed orders, identified customer, no refunds
Grain:
  SalesOrder = one placed order
  OrderLine = one item line within one placed order
  Payment = one distinct payment-processing attempt
Identity:
  Customer.customerId, Product.productId, SalesOrder.orderId
  OrderLine(orderId,lineNo), Payment.paymentId
Relationships:
  Customer 1 — 0..N SalesOrder
  SalesOrder 1 — 1..N OrderLine
  Product 1 — 0..N OrderLine
  SalesOrder 1 — 0..N Payment
History:
  agreedUnitPrice stays on OrderLine
Money:
  capturedAmount excludes FAILED/PENDING
Open questions:
  guest checkout, drafts, product variants, refunds,
  split/aggregated payments, currency, taxes, PII retention
~~~

**Cách đánh giá:** Nếu một người chưa tham gia thảo luận vẫn đọc được phạm vi, quan hệ, điều kiện biên và những giả định chưa quyết, tài liệu mô hình đã có khả năng dùng làm cơ sở cho bước thiết kế logic.

## 16. Bài luyện tập tổng hợp có lời giải

Bạn nên **tự vẽ hoặc tự trả lời trước**, sau đó dùng lời giải để so **cách lập luận** chứ không chỉ so tên thực thể.

### Bài 1 — Xác định thực thể cần thiết

Đề nêu khách hàng, sản phẩm, đơn hàng và thanh toán. Mỗi đơn chứa nhiều sản phẩm, với số lượng/giá mua có thể khác nhau giữa các đơn. Có thể thiết kế chỉ bốn thực thể không? Hãy nêu thực thể bổ sung và giải thích.

**Lời giải:** Cần **OrderLine** để diễn đạt **một dòng mua hàng trong một đơn** và lưu `quantity`, `agreedUnitPrice`, `lineDiscount`. Order ↔ Product là M:N; OrderLine biến mỗi phía thành quan hệ 1:N có nơi gắn các thuộc tính của lần mua. Bốn thực thể chỉ đủ nếu không có nhu cầu quản lý các dòng/điều kiện mua, trái với đề.

### Bài 2 — Đọc Crow's Foot hai chiều

Cho `CUSTOMER ||--o{ SALES_ORDER`. Một khách có thể có bao nhiêu đơn? Một đơn có bao nhiêu khách?

**Lời giải:** Một Customer có **0..N SalesOrder**; mỗi SalesOrder có **đúng 1 Customer**. Không suy ngược rằng một Order có nhiều Customer chỉ vì một đầu có dấu chân quạ.

### Bài 3 — Kiểm tra optionality bằng khách chưa mua

Khách `C103` mới đăng ký nhưng chưa có đơn. Mô hình `CUSTOMER ||--|{ SALES_ORDER` có phù hợp không?

**Lời giải:** **Không**, vì ký hiệu `|{` phía SalesOrder bắt buộc mỗi Customer phải có **ít nhất một đơn**. Trong phạm vi bài, khách tồn tại độc lập với đơn; sửa thành `CUSTOMER ||--o{ SALES_ORDER`.

### Bài 4 — Chọn độ hạt và định danh OrderLine

`O9001` có hai dòng cho cùng `P220`, một dòng giá thường, một dòng có gói quà. Nhóm đề xuất dùng `(orderId,productId)` làm khóa OrderLine. Có đủ không?

**Lời giải:** **Không** nếu hai dòng cùng sản phẩm được phép tồn tại. `(orderId,productId)` sẽ coi chúng là một, mất khác biệt về ưu đãi/gói quà. Dùng `(orderId,lineNo)` hoặc `orderLineId` ổn định và giữ quan hệ từ mỗi dòng tới Product. Nếu nghiệp vụ bắt buộc gộp dòng giống sản phẩm, phải ghi ràng buộc riêng.

### Bài 5 — Product đổi giá sau khi đặt

An mua hai sổ P220 với giá 120.000/chiếc hôm qua. Hôm nay Product được cập nhật `currentListPrice=150.000`. Hỏi đơn cũ có subtotal bao nhiêu nếu không có giảm giá/phí?

**Lời giải:** \(2\times120.000=240.000\) VND. Giá giao dịch đã chốt thuộc `OrderLine.agreedUnitPrice`, không truy xuất lại `Product.currentListPrice` để sửa lịch sử.

### Bài 6 — Một sản phẩm chưa bán có tồn tại không?

Sản phẩm P450 mới nhập danh mục, chưa có ai đặt. Nếu vẽ `PRODUCT ||--|{ ORDER_LINE` thì sao?

**Lời giải:** Sơ đồ buộc mỗi Product có **ít nhất một OrderLine**, trái tình huống. Cần `PRODUCT ||--o{ ORDER_LINE`: một sản phẩm có thể xuất hiện trong **0..N** dòng; mỗi OrderLine vẫn cần đúng một Product.

### Bài 7 — Đơn đã đặt có 0 dòng

Hệ tạo một Order trạng thái `CONFIRMED` nhưng không có OrderLine. Có hợp lệ theo giả định bài chính không? Nếu hệ cho phép nháp thì phải sửa gì?

**Lời giải:** Không hợp lệ với **đơn đã đặt** theo phạm vi bài. Nếu Order có thể là draft, toàn bộ vòng đời có thể cho **0..N** dòng, và quy tắc chuyển `DRAFT → CONFIRMED` phải kiểm tra **ít nhất một dòng**. Có thể tách `Cart` khỏi `SalesOrder` để giữ nghĩa đơn đã đặt.

### Bài 8 — Đơn chưa có lần thanh toán

`O9002` có một dòng P220 nhưng chưa gọi nhà cung cấp thanh toán. Quan hệ Order–Payment 1:1 có phù hợp không?

**Lời giải:** Không. Một đơn có thể có **0 Payment**; quan hệ tối thiểu là `SALES_ORDER ||--o{ PAYMENT` theo quy tắc “mỗi Payment thuộc một Order”. Không tạo Payment giả 0 đồng chỉ để có liên kết.

### Bài 9 — Thử thanh toán thất bại và thanh toán thành công

Một đơn có `PAY-01 FAILED 320000`, `PAY-02 CAPTURED 200000`, `PAY-03 CAPTURED 120000`. Có bao nhiêu payment attempt? Bao nhiêu tiền được xem là thu thành công?

**Lời giải:** Có **3 lần thử/giao dịch**, trong đó **2 CAPTURED**. Tiền thu thành công \(200.000+120.000=320.000\) VND. `FAILED` không cộng vào số đã thu. Nếu provider có trạng thái `AUTHORIZED` nhưng chưa capture, cũng phải định nghĩa riêng.

### Bài 10 — Fanout khi tính tổng tiền

Đơn `O9001` có 2 OrderLine và 3 Payment. JOIN trực tiếp OrderLine với Payment theo `orderId` tạo bao nhiêu dòng? Tại sao `SUM(OrderLine.amount)` có thể sai?

**Lời giải:** Có thể tạo **6 dòng**, tức mỗi OrderLine lặp 3 lần. Nếu cộng từ kết quả JOIN, subtotal 320.000 có thể bị nhân thành **960.000**. Phải tính subtotal ở grain cấp dòng rồi gom về **một dòng mỗi Order**, tính captured payment riêng ở grain Payment rồi gom về **một dòng mỗi Order**, sau đó mới JOIN.

### Bài 11 — Mã đơn chỉ duy nhất trong cửa hàng

Cửa hàng A và B đều có `orderNumber=000123`. Làm sao tránh nhầm hai đơn?

**Lời giải:** Dùng `orderId` được bảo đảm duy nhất trong phạm vi phù hợp hoặc danh tính ghép như `(storeId,orderNumber)`/`(tenantId,orderNumber)` nếu đó là quy tắc thực. Tên trường `orderNumber` không tự chứng minh tính duy nhất toàn hệ.

### Bài 12 — Guest checkout

Hệ cho người mua không đăng ký tài khoản. Mỗi đơn vẫn phải biết một người mua và cách gửi xác nhận. Có thể chỉ xóa mối quan hệ Order–Customer trong ERD không?

**Lời giải:** Không nên tùy tiện xóa quan hệ mà mất nghĩa người mua. Hai hướng hợp lệ: (1) định nghĩa Customer/Buyer identity bao gồm guest; (2) Order có liên kết **0..1 RegisteredCustomer** và lưu dữ liệu người mua tại thời điểm đặt theo chính sách. Cần xác nhận quyền xem đơn guest, liên hệ, liên kết khi guest đăng ký và retention PII.

### Bài 13 — Một Payment trả nhiều đơn

Khách chuyển khoản một lần 470.000 VND để trả đơn O9001 (320.000) và O9002 (150.000). Quan hệ “một Payment thuộc đúng một Order” có còn đúng không? Hãy sửa mô hình.

**Lời giải:** **Không** còn đúng nếu giao dịch thanh toán ngân hàng được mô hình hóa nguyên khối. Thêm **PaymentAllocation** với grain **một khoản phân bổ từ Payment tới Order**; hai dòng ví dụ phân bổ 320.000 và 150.000, tổng bằng 470.000 nếu chính sách yêu cầu phân bổ hết. Cần kiểm soát trạng thái thanh toán, currency và chống phân bổ vượt tiền hợp lệ.

### Bài 14 — Hoàn tiền hai đợt

Payment `PAY-02` đã capture 200.000, sau đó hoàn 50.000 và 30.000 ở hai giao dịch khác nhau. Có nên ghi đè `PAY-02.amount=120000` để biểu diễn số dư?

**Lời giải:** Không nếu cần lịch sử thu/hoàn độc lập. Giữ thông tin **Payment CAPTURED=200.000**, thêm **Refund** cho hai lần hoàn thành công, mỗi lần có định danh và trạng thái riêng. Tổng hoàn 80.000; **net captured theo giao dịch đó** là 120.000 theo cách tính minh họa, không làm mất dấu đã thu 200.000 ban đầu.

### Bài 15 — Vai trò khách hàng khác nhau

Một người mua gửi quà cho bạn, hóa đơn xuất cho doanh nghiệp, thanh toán bằng thẻ của một người khác. Có thể dùng một `customerId` để mặc định cả bốn vai trò không?

**Lời giải:** Không. `buyer`, `recipient`, `billToParty`, `payer` là **những vai trò khác nhau**; tùy nghiệp vụ có thể là cùng hoặc khác đối tượng. Phải hỏi quyền/trách nhiệm của từng vai trò và bổ sung quan hệ/định danh thích hợp thay vì ép vào một cột mơ hồ.

### Bài 16 — Chuyển conceptual sang logic

Tại sao sơ đồ khái niệm dùng `SalesOrder 1 — 0..N Payment` mà không chỉ định kiểu `payment.order_id BIGINT`?

**Lời giải:** Mô hình khái niệm tập trung vào **nghĩa và cardinality**. `payment.order_id` là biểu diễn **logic** của liên kết trong một lược đồ quan hệ; chọn `BIGINT`, UUID, FK index, storage engine là quyết định **vật lý**. Những quyết định này phải phục vụ, không được thay đổi, quy tắc nghiệp vụ đã xác nhận.

### Bài 17 — Kiểm chứng nguồn thanh toán bị gửi lặp

Provider gửi lại callback `CAPTURED` của cùng giao dịch ba lần. Hệ đã lưu ba Payment khác ID và tăng tiền thu ba lần. Vấn đề nằm ở đâu?

**Lời giải:** Có lỗi **idempotency/danh tính sự kiện/giao dịch** ở tích hợp. Cần xác định provider transaction reference và phạm vi duy nhất, phân biệt ba lần delivery với **một giao dịch logic**, xử lý retry an toàn. ERD có Payment entity nhưng **không tự ngăn** trùng callback; kiểm thử nghiệp vụ phải bổ sung.

### Bài 18 — Mô hình nguồn khác vẫn phải giữ cùng sự thật

Nhóm định lưu Orders trong document DB, mỗi document nhúng `lines[]` và `payments[]`. Họ kết luận “đã là document thì không cần OrderLine”. Có đúng không?

**Lời giải:** Không đúng về **ngữ nghĩa**. Có thể không cần collection vật lý riêng cho OrderLine nếu nhúng vào Order document, nhưng mỗi phần tử `lines[]` vẫn đại diện cho **một dòng mua** với danh tính, giá, số lượng và quan hệ Product. Mô hình khái niệm vẫn cần thể hiện sự thật đó; biểu diễn vật lý là chuyện khác.

## 17. Checklist tự đánh giá sơ đồ trước khi nộp

- [ ] Đã viết rõ **phạm vi**: đơn đã đặt, khách định danh, Payment là một lần thử, chưa xét refund.
- [ ] Đã chỉ ra **5 thực thể** trong lời giải chính: Customer, Product, SalesOrder, OrderLine, Payment.
- [ ] Đã định nghĩa **grain** của SalesOrder, OrderLine và Payment.
- [ ] Đã tách **Customer ID** khỏi tên/email và **Order ID** khỏi số đơn hiển thị.
- [ ] Đã biểu diễn Customer → Order **0..N**, Order → Customer **1**.
- [ ] Đã biểu diễn Order → OrderLine **1..N** khi chỉ xét đơn đã đặt.
- [ ] Đã biểu diễn Product → OrderLine **0..N**, OrderLine → Product **1**.
- [ ] Đã biểu diễn Order → Payment **0..N**, Payment → Order **1** theo phạm vi.
- [ ] Đã lưu **quantity** và **agreedUnitPrice** ở OrderLine, không chỉ ở Product.
- [ ] Đã phân biệt **giá danh mục hiện hành** với **giá giao dịch lúc đặt**.
- [ ] Đã nêu Payment `FAILED`/`PENDING` không tự tạo số tiền đã thu.
- [ ] Đã phân biệt tổng tiền hàng, số phải trả, đã thu và hoàn tiền.
- [ ] Đã thử khách chưa mua, sản phẩm chưa bán, đơn chưa thanh toán và thanh toán thất bại.
- [ ] Đã thử một Product ở nhiều đơn, giá khác nhau, và một Product lặp nhiều dòng nếu nghiệp vụ cho phép.
- [ ] Đã kiểm tra không nhân tiền khi JOIN hai tập 1:N là OrderLine và Payment.
- [ ] Đã xác định namespace ID theo tenant/store và cách xử lý callback trùng.
- [ ] Đã ghi **câu hỏi mở** về guest, draft, SKU/variant, thuế, hoàn tiền và thanh toán gộp.
- [ ] Đã nhận diện các trường hợp cần **PaymentAllocation**, Refund hoặc quan hệ vai trò.
- [ ] Đã xác định ai sở hữu dữ liệu khách/sản phẩm/đơn/thanh toán và những thông tin cần giữ theo thời gian.
- [ ] Đã phân biệt **sơ đồ khái niệm** với lược đồ logic, FK, index và lựa chọn DBMS.
- [ ] Đã đặt ra **phép thử chấp nhận** và những kịch bản phản ví dụ cho cardinality chính.

## 18. Tổng kết: từ bốn danh từ đến một mô hình có thể kiểm chứng

Từ yêu cầu “khách hàng, sản phẩm, đơn hàng và thanh toán”, ta không dừng ở việc vẽ bốn hộp. Để mô tả một lần mua có số lượng và giá được chốt, cần thêm **OrderLine**:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : "dat"
    SALES_ORDER ||--|{ ORDER_LINE : "gom"
    PRODUCT ||--o{ ORDER_LINE : "xuat_hien_trong"
    SALES_ORDER ||--o{ PAYMENT : "co"
~~~

Sơ đồ này được chấp nhận **trong phạm vi đã công bố**: đơn đã đặt có ít nhất một dòng, mỗi đơn thuộc một khách định danh, một Payment là một lần xử lý thuộc một đơn, và đơn có thể chưa hoặc đã thử thanh toán nhiều lần.

**Năm bài học rút ra:**

1. **Thực thể phải phản ánh sự thật nghiệp vụ**, không chỉ tương ứng với một danh từ trong đề. OrderLine có ý nghĩa riêng vì lưu giá và số lượng của một lần mua.
2. **Cardinality phải đọc hai chiều và kiểm bằng phản ví dụ.** Khách chưa mua, sản phẩm chưa bán và đơn chưa thanh toán đều là ca bình thường.
3. **Trạng thái và thời gian của đơn khác với thanh toán.** Đơn đã đặt không mặc nhiên đã trả đủ; lần payment thất bại không tính tiền đã thu.
4. **Lịch sử giao dịch phải được giữ theo nghĩa đã chốt.** Product đổi giá hoặc ngừng bán không được âm thầm sửa đơn cũ.
5. **Không có một ERD đúng cho mọi biến thể.** Guest checkout, đơn nháp, thanh toán gộp, hoàn tiền và nhiều vai trò sẽ làm thay đổi hoặc mở rộng mô hình.

**Ghi nhớ:** Một **mô hình khái niệm tốt** không được đánh giá chỉ vì đường nối và ký hiệu đẹp. Nó phải giúp người hiểu nghiệp vụ trả lời chính xác **“một bản ghi đại diện cho điều gì, mỗi đối tượng được liên kết với bao nhiêu đối tượng khác, và quy tắc nào phải luôn đúng?”**. Khi các giả định, grain, quan hệ và phép kiểm chứng đã rõ, việc chuyển sang mô hình quan hệ, document, đồ thị hay hệ phân tích mới có cơ sở đúng đắn và dễ tiến hóa.




