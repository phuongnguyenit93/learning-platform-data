# Mô hình hóa dữ liệu (data modeling) là gì và giải quyết vấn đề nào

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích mô hình hóa dữ liệu là gì, nhận ra những vấn đề phát sinh khi hệ thống không có mô hình dữ liệu rõ ràng, và mô tả cách chuyển một yêu cầu nghiệp vụ thành các thành phần dữ liệu có ý nghĩa. Bạn cũng sẽ biết vì sao cùng một miền nghiệp vụ có thể được biểu diễn bằng mô hình quan hệ, document, đồ thị hoặc phân tích tùy theo cách hệ thống sử dụng dữ liệu.

## 1. Mô hình hóa dữ liệu là gì?

**Mô hình hóa dữ liệu (data modeling)** là quá trình khám phá, mô tả và tổ chức dữ liệu của một miền nghiệp vụ: dữ liệu nào cần được lưu, mỗi dữ liệu có ý nghĩa gì, chúng liên hệ với nhau ra sao, quy tắc nào phải luôn đúng và hệ thống cần đọc hoặc thay đổi dữ liệu theo cách nào.

Kết quả của quá trình này là một **mô hình dữ liệu**. Mô hình là bản mô tả có cấu trúc về dữ liệu và các quy tắc của nó. Tùy mức độ chi tiết, mô hình có thể là sơ đồ khái niệm, mô hình logic, lược đồ cơ sở dữ liệu, từ điển dữ liệu, các ràng buộc hoặc hợp đồng dữ liệu giữa những thành phần phần mềm.

Có thể hình dung mô hình dữ liệu trả lời sáu câu hỏi:

1. **Dữ liệu nào tồn tại?** Ví dụ: khách hàng, đơn hàng, sản phẩm, thanh toán.
2. **Dữ liệu có ý nghĩa gì?** Ví dụ: “đơn hàng đã xác nhận” khác với “đơn hàng đã thanh toán”.
3. **Dữ liệu liên hệ thế nào?** Một khách hàng có thể có nhiều đơn hàng; mỗi dòng hàng thuộc về một đơn hàng.
4. **Điều gì phải luôn đúng?** Số lượng đặt mua phải lớn hơn 0; một dòng hàng phải thuộc về một đơn hàng hợp lệ.
5. **Dữ liệu thay đổi theo thời gian ra sao?** Giá sản phẩm hiện tại có thể thay đổi, nhưng giá đã áp dụng cho đơn hàng cũ cần được giữ lại.
6. **Hệ thống sử dụng dữ liệu như thế nào?** Ghi nhận giao dịch, tìm kiếm, truy vết quan hệ hay tổng hợp báo cáo đều tạo ra những yêu cầu khác nhau.

Mô hình hóa dữ liệu không đơn thuần là đặt tên bảng hoặc chọn kiểu cột. Nó bắt đầu từ cách hiểu nghiệp vụ và kết thúc bằng một cấu trúc đủ rõ để con người, ứng dụng và cơ sở dữ liệu cùng tuân theo.

### Mô hình dữ liệu khác lược đồ cơ sở dữ liệu như thế nào?

Hai khái niệm có liên quan nhưng không đồng nhất:

- **Mô hình dữ liệu** mô tả ý nghĩa, cấu trúc, quan hệ và quy tắc của dữ liệu. Nó có thể độc lập với một công nghệ lưu trữ cụ thể.
- **Lược đồ cơ sở dữ liệu (database schema)** là cách mô hình được triển khai trong một hệ quản trị dữ liệu cụ thể, chẳng hạn bảng, cột, kiểu dữ liệu, khóa, chỉ mục và ràng buộc SQL.

Ví dụ, nghiệp vụ quy định một đơn hàng thuộc về một khách hàng và có nhiều dòng hàng. Đó là quy tắc trong mô hình. Khi triển khai bằng cơ sở dữ liệu quan hệ, quy tắc có thể được thể hiện bằng bảng `orders`, bảng `order_items`, khóa ngoại và các ràng buộc. Khi triển khai bằng document database, một đơn hàng có thể được lưu thành một document chứa mảng `items`.

Một mô hình tốt có thể dẫn đến những lược đồ vật lý khác nhau. Ngược lại, một lược đồ chạy được chưa chắc đã phản ánh đúng nghiệp vụ.

## 2. Vì sao hệ thống cần mô hình dữ liệu?

Khi hệ thống còn nhỏ, nhóm phát triển đôi khi lưu dữ liệu theo cách thuận tiện nhất cho màn hình hoặc đoạn code đang làm. Cách này có thể hoạt động trong thời gian ngắn, nhưng các giả định ngầm sẽ tích tụ. Khi thêm chức năng, tích hợp hoặc báo cáo, những giả định đó bắt đầu mâu thuẫn.

Mô hình hóa dữ liệu giải quyết các nhóm vấn đề sau.

### 2.1. Tạo cách hiểu thống nhất về nghiệp vụ

Một từ có thể mang nhiều nghĩa nếu không được định nghĩa rõ. “Khách hàng” có thể là người mua, người nhận hàng, người thanh toán hoặc một tổ chức có nhiều tài khoản. “Doanh thu” có thể được tính theo thời điểm đặt hàng, thanh toán hay hoàn tất giao hàng.

Mô hình giúp nhóm thống nhất các khái niệm, định nghĩa và mối quan hệ. Nhờ vậy, API, giao diện, báo cáo và dịch vụ nền không tự diễn giải cùng một khái niệm theo những cách khác nhau.

Ví dụ, hệ thống bán hàng cần phân biệt:

- `Order`: yêu cầu mua hàng được ghi nhận.
- `Payment`: một lần hoặc một bản ghi thanh toán cho đơn hàng.
- `Shipment`: việc giao một phần hoặc toàn bộ hàng hóa.
- `Customer`: chủ thể đặt hàng.

Nếu gộp tất cả vào một đối tượng “đơn hàng”, hệ thống sẽ khó biểu diễn trường hợp thanh toán thất bại rồi thử lại, hoặc một đơn hàng được giao thành nhiều đợt.

### 2.2. Bảo đảm tính đúng đắn và nhất quán

Dữ liệu có thể sai theo nhiều cách: tham chiếu đến bản ghi không tồn tại, số lượng âm, mã định danh trùng, trạng thái không hợp lệ hoặc hai bản sao của cùng một thông tin có giá trị khác nhau.

Mô hình chỉ ra các quy tắc cần bảo vệ. Khi triển khai, các quy tắc đó có thể được thực thi bằng:

- khóa chính và khóa ngoại;
- ràng buộc `NOT NULL`, `UNIQUE`, `CHECK`;
- kiểu dữ liệu và miền giá trị;
- logic nghiệp vụ trong transaction hoặc dịch vụ miền;
- validation ở biên API và các hợp đồng dữ liệu.

Không phải quy tắc nào cũng có thể hoặc nên được thực thi chỉ bằng một ràng buộc cơ sở dữ liệu. Tuy nhiên, mô hình phải chỉ rõ quy tắc và xác định lớp nào chịu trách nhiệm bảo vệ nó.

### 2.3. Giảm dư thừa và tránh cập nhật mâu thuẫn

Giả sử tên và địa chỉ khách hàng được sao chép vào mọi dòng đơn hàng. Khi khách hàng đổi địa chỉ, hệ thống phải quyết định cập nhật tất cả bản sao hay giữ lại địa chỉ lịch sử. Nếu không có chủ đích, các bản sao dễ lệch nhau.

Mô hình giúp xác định đâu là dữ liệu gốc, đâu là dữ liệu tham chiếu, đâu là ảnh chụp tại một thời điểm và đâu là dữ liệu được phép lặp lại để phục vụ truy vấn. Đây là nền tảng để áp dụng chuẩn hóa hoặc phi chuẩn hóa có kiểm soát.

Lưu ý: **không phải mọi dữ liệu lặp lại đều là lỗi**. Ví dụ, địa chỉ giao hàng và đơn giá tại thời điểm mua thường cần được lưu như một ảnh chụp trong đơn hàng. Điều quan trọng là hiểu lý do lặp lại và quy định nguồn sự thật cho từng trường.

### 2.4. Hỗ trợ truy vấn và quy trình nghiệp vụ

Cấu trúc dữ liệu ảnh hưởng trực tiếp đến cách ứng dụng truy vấn và cập nhật. Một mô hình tốt giúp trả lời những câu hỏi quan trọng:

- Lấy các đơn hàng của một khách hàng trong khoảng thời gian?
- Tìm tất cả sản phẩm thường được mua cùng nhau?
- Truy vết các tài khoản có liên hệ với một giao dịch?
- Tổng hợp doanh số theo ngày, sản phẩm và khu vực?

Nếu chỉ thiết kế dữ liệu theo thao tác ghi, truy vấn quan trọng có thể rất phức tạp hoặc tốn kém. Nếu chỉ tối ưu một màn hình, những quy trình khác có thể bị buộc phải đọc quá nhiều dữ liệu hoặc ghép nối khó khăn.

Vì vậy, mô hình phải xét cả dữ liệu và cách dữ liệu được sử dụng.

### 2.5. Giúp hệ thống thay đổi an toàn

Nghiệp vụ thay đổi: đơn hàng có thể tách giao, sản phẩm có biến thể, khách hàng có nhiều địa chỉ, hoặc thanh toán hỗ trợ nhiều nhà cung cấp. Mô hình rõ ràng giúp nhóm nhận ra thay đổi tác động đến thực thể, quan hệ, quy tắc và dữ liệu lịch sử nào.

Khi mô hình và lược đồ có chủ đích, việc thêm trường, thay đổi quan hệ, chuyển đổi dữ liệu và duy trì tương thích API sẽ dễ đánh giá hơn. Mô hình không loại bỏ chi phí thay đổi, nhưng giúp phát hiện sớm phạm vi ảnh hưởng và giảm những phụ thuộc ngầm.

## 3. Từ yêu cầu nghiệp vụ đến mô hình dữ liệu

Hãy xét yêu cầu: “Khách hàng có thể đặt sản phẩm. Mỗi đơn hàng có một hoặc nhiều dòng hàng. Giá bán có thể thay đổi theo thời gian. Khách hàng có thể thanh toán nhiều lần nếu lần đầu thất bại.”

Nếu bắt đầu ngay bằng câu lệnh tạo bảng, ta có thể bỏ sót các khái niệm quan trọng. Thay vào đó, hãy phân tích theo từng bước.

### Bước 1: Làm rõ ngôn ngữ và phạm vi

Hỏi những câu hỏi cụ thể:

- “Khách hàng” là cá nhân, doanh nghiệp hay cả hai?
- Một đơn hàng có được tạo trước khi thanh toán không?
- Một đơn hàng có thể có nhiều lần thử thanh toán không?
- Giá nào được dùng để tính tiền: giá hiện tại hay giá tại thời điểm đặt hàng?
- Đơn hàng có thể không có dòng hàng không?
- Hệ thống có cần lưu lịch sử trạng thái hay chỉ trạng thái hiện tại?

Các câu hỏi này biến câu mô tả chung thành quy tắc có thể kiểm chứng. Nếu câu trả lời chưa rõ, hãy ghi lại giả định và người cần xác nhận thay vì tự coi giả định là sự thật.

### Bước 2: Nhận diện thực thể và giá trị

**Thực thể (entity)** là một đối tượng nghiệp vụ cần được nhận diện và quản lý xuyên suốt, thường có định danh riêng. Trong ví dụ có thể có `Customer`, `Order`, `Product` và `Payment`.

**Giá trị (value)** mô tả một đặc tính hoặc khái niệm không nhất thiết có vòng đời định danh độc lập. Ví dụ, `Money` có thể gồm số tiền và đơn vị tiền tệ; `ShippingAddress` có thể là một nhóm thuộc tính của địa chỉ giao hàng tại thời điểm đặt hàng.

Không phải danh từ nào trong yêu cầu cũng cần trở thành bảng hoặc collection. Một danh từ có thể chỉ là thuộc tính, một giá trị, một vai trò hoặc một thuật ngữ cần làm rõ.

### Bước 3: Xác định thuộc tính và định danh

Một số thuộc tính có thể là:

- `Customer`: mã khách hàng, tên hiển thị, email liên hệ.
- `Product`: mã sản phẩm, tên, trạng thái kinh doanh, giá hiện tại.
- `Order`: mã đơn hàng, khách hàng đặt, thời điểm tạo, trạng thái.
- `OrderItem`: sản phẩm, số lượng, đơn giá tại thời điểm đặt.
- `Payment`: đơn hàng, số tiền, phương thức, kết quả và thời điểm xử lý.

Mỗi thực thể cần một cách nhận diện ổn định. Có thể dùng **khóa tự nhiên** nếu giá trị có ý nghĩa nghiệp vụ và thực sự ổn định, hoặc **khóa thay thế (surrogate key)** như số nguyên hay UUID nếu muốn định danh độc lập với thuộc tính có thể thay đổi.

Email thường không phải định danh lâu dài lý tưởng: người dùng có thể đổi email, email có thể được chia sẻ hoặc tái sử dụng theo chính sách. Chọn khóa phải dựa trên quy tắc miền nghiệp vụ, không chỉ dựa vào việc trường nào đang có vẻ duy nhất.

### Bước 4: Mô tả quan hệ và lực lượng quan hệ

**Quan hệ (relationship)** mô tả cách các thực thể liên hệ với nhau. Với ví dụ trên:

- Một khách hàng có thể có 0 đến nhiều đơn hàng.
- Mỗi đơn hàng thuộc về đúng một khách hàng.
- Một đơn hàng có một hoặc nhiều dòng hàng khi đã được xác nhận.
- Mỗi dòng hàng tham chiếu một sản phẩm.
- Một đơn hàng có thể có nhiều lần thanh toán.

Khi mô tả quan hệ, cần nêu rõ:

- **Bội số (cardinality):** một-một, một-nhiều hay nhiều-nhiều.
- **Tính tùy chọn (optionality):** quan hệ bắt buộc hay có thể vắng mặt.
- **Vòng đời:** đối tượng có thể tồn tại độc lập hay phụ thuộc vào đối tượng khác.

Quan hệ nhiều-nhiều thường cần một thực thể liên kết nếu bản thân quan hệ có thuộc tính. Ví dụ, quan hệ giữa đơn hàng và sản phẩm có thêm số lượng, đơn giá và chiết khấu; do đó `OrderItem` là một khái niệm nghiệp vụ hữu ích, không chỉ là một bảng nối kỹ thuật.

### Bước 5: Viết các quy tắc bất biến

**Bất biến (invariant)** là điều kiện phải luôn đúng trong phạm vi nghiệp vụ đã xác định. Ví dụ:

- Số lượng của một dòng hàng phải là số nguyên dương.
- Đơn giá tại thời điểm đặt hàng không được âm.
- Mỗi dòng hàng phải thuộc về một đơn hàng tồn tại.
- Tổng tiền thanh toán phải tuân theo quy tắc tiền tệ và làm tròn của hệ thống.
- Chỉ những chuyển trạng thái được phép mới có thể xảy ra.

Phân biệt một ràng buộc trên một giá trị với một quy trình chuyển trạng thái. `CHECK (quantity > 0)` có thể bảo vệ số lượng ở cấp cơ sở dữ liệu. Nhưng quy tắc “đơn hàng đã hủy không được chuyển thẳng sang đã giao” thường cần được bảo vệ trong logic chuyển trạng thái hoặc một cơ chế nghiệp vụ phù hợp.

### Bước 6: Xác định cách dữ liệu được đọc và ghi

Liệt kê các thao tác và truy vấn quan trọng trước khi chọn cấu trúc lưu trữ:

- Tạo đơn hàng cùng các dòng hàng.
- Xem chi tiết đơn hàng và lịch sử thanh toán.
- Tra cứu đơn hàng theo khách hàng hoặc mã đơn.
- Thống kê doanh số theo ngày và sản phẩm.
- Tìm các sản phẩm thường xuất hiện trong cùng đơn hàng.

Cùng một dữ liệu có thể cần những cách truy cập khác nhau. Mô hình phải hỗ trợ các luồng chính và giữ được quy tắc đúng đắn khi có cập nhật đồng thời.

## 4. Ba mức độ của mô hình dữ liệu

Trong thực tế, nhóm thường đi từ mô hình ít phụ thuộc công nghệ đến mô hình có thể triển khai.

| Mức độ | Tập trung vào | Ví dụ đầu ra |
|---|---|---|
| Mô hình khái niệm (conceptual) | Các khái niệm nghiệp vụ và quan hệ lớn | Sơ đồ Customer — Order — Product |
| Mô hình logic (logical) | Thuộc tính, định danh, quan hệ, bội số và quy tắc | Mô tả thực thể, ERD, từ điển dữ liệu |
| Mô hình vật lý (physical) | Cách triển khai trên công nghệ cụ thể | Bảng/cột, document, kiểu dữ liệu, khóa, chỉ mục, phân vùng |

**Mô hình khái niệm** giúp chuyên gia nghiệp vụ và kỹ sư thống nhất phạm vi. Ở mức này, chưa cần quyết định bảng dùng `BIGINT` hay `UUID`.

**Mô hình logic** làm rõ cấu trúc và quy tắc mà không gắn chặt vào một hệ quản trị cơ sở dữ liệu. Đây là nơi xác định thuộc tính, khóa, quan hệ nhiều-nhiều, tính bắt buộc và các khái niệm cần tách riêng.

**Mô hình vật lý** chuyển thiết kế thành cấu trúc triển khai. Lúc này mới quyết định kiểu cột, cú pháp khóa ngoại, chỉ mục, phân vùng, chiến lược lưu trữ và các lựa chọn phụ thuộc hệ quản trị.

Ba mức này không nhất thiết phải là ba tài liệu riêng. Với hệ thống nhỏ, chúng có thể được thể hiện trong một tài liệu; với hệ thống lớn, tách mức độ giúp quản lý thay đổi và trao đổi với các nhóm khác rõ ràng hơn.

## 5. Chọn cách biểu diễn dữ liệu phù hợp

Không có một kiểu cơ sở dữ liệu phù hợp nhất cho mọi bài toán. Việc chọn mô hình cần dựa trên bản chất dữ liệu, quy tắc nhất quán, kiểu truy vấn, khối lượng đọc ghi và yêu cầu tiến hóa.

### 5.1. Mô hình quan hệ (relational model)

Mô hình quan hệ tổ chức dữ liệu thành các quan hệ, thường được triển khai dưới dạng bảng gồm hàng và cột. Các bảng liên kết qua khóa chính và khóa ngoại. SQL hỗ trợ truy vấn kết hợp, ràng buộc và transaction.

Ví dụ đơn giản:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12, 2) NOT NULL CHECK (unit_price >= 0)
);
```

Bảng `order_items` thể hiện mỗi dòng hàng là một phần của đơn hàng. `unit_price` được lưu tại thời điểm mua để lịch sử đơn hàng không thay đổi khi giá hiện tại của sản phẩm được cập nhật. Trong một hệ thống hoàn chỉnh, `product_id` cũng sẽ tham chiếu đến bảng sản phẩm và đơn giá thường đi kèm đơn vị tiền tệ.

Mô hình quan hệ phù hợp khi dữ liệu có cấu trúc rõ, quan hệ giữa các đối tượng quan trọng, cần ràng buộc toàn vẹn và transaction đáng tin cậy. Điểm cần cân nhắc là các cấu trúc linh hoạt hoặc dữ liệu lồng sâu có thể cần nhiều phép nối và thiết kế bảng cẩn thận.

### 5.2. Mô hình document

Mô hình document lưu một đối tượng cùng các thuộc tính và dữ liệu lồng bên trong, thường dưới dạng JSON hoặc cấu trúc tương tự. Một document có thể gom những dữ liệu thường được đọc hoặc cập nhật cùng nhau.

Ví dụ một document đơn hàng:

```json
{
  "orderId": "ORD-1042",
  "customerId": "CUS-18",
  "status": "CONFIRMED",
  "shippingAddress": {
    "recipient": "Nguyen An",
    "city": "Da Nang"
  },
  "items": [
    {
      "productId": "P-20",
      "productName": "Keyboard",
      "quantity": 2,
      "unitPrice": 850000,
      "currency": "VND"
    }
  ]
}
```

Thông tin địa chỉ giao hàng và tên sản phẩm được chụp lại trong đơn hàng để giữ ngữ cảnh tại thời điểm mua. Các thông tin này có thể khác với địa chỉ hoặc tên hiện tại trong hồ sơ khách hàng và danh mục sản phẩm.

Document phù hợp khi dữ liệu thường được truy cập theo từng aggregate hoặc đối tượng nghiệp vụ, cấu trúc có thể thay đổi theo loại bản ghi và việc đọc toàn bộ đối tượng là phổ biến. Cần cân nhắc khi nhiều document cùng sao chép một thông tin thường xuyên thay đổi, khi cần truy vấn liên kết phức tạp hoặc khi cập nhật xuyên nhiều document đòi hỏi tính nguyên tử.

### 5.3. Mô hình đồ thị (graph model)

Mô hình đồ thị biểu diễn dữ liệu bằng **nút (node)**, **cạnh (edge)** và thuộc tính. Nút đại diện cho đối tượng; cạnh biểu diễn quan hệ có hướng hoặc không có hướng giữa các đối tượng.

Ví dụ trong hệ thống bán hàng:

```text
(Customer: CUS-18)
       |
       | PLACED
       v
(Order: ORD-1042)
       |
       | CONTAINS {quantity: 2, unitPrice: 850000}
       v
(Product: P-20)
```

Cấu trúc này hữu ích khi câu hỏi tập trung vào đường đi và mạng lưới quan hệ: khách hàng có liên hệ với tài khoản nào, sản phẩm nào thường được mua cùng nhau, hoặc một thực thể có thể được truy vết qua bao nhiêu bước quan hệ.

Mô hình đồ thị phù hợp với truy vấn nhiều bước quan hệ và dữ liệu mà chính các liên kết có ý nghĩa lớn. Nếu phần lớn truy vấn chỉ là đọc một bản ghi theo khóa hoặc tổng hợp bảng lớn, đồ thị có thể không đem lại lợi ích tương xứng với chi phí vận hành và mô hình hóa.

### 5.4. Mô hình phân tích (analytical model)

Mô hình phân tích tổ chức dữ liệu để tổng hợp, so sánh và phân tích theo các chiều như thời gian, sản phẩm, khách hàng hoặc khu vực. Một cách thiết kế phổ biến là **lược đồ hình sao (star schema)** gồm bảng sự kiện (fact) và bảng chiều (dimension).

Ví dụ, một dòng trong `FactSales` có thể đại diện cho một dòng hàng đã bán. Đây là **mức chi tiết (grain)** của bảng. Bảng sự kiện lưu các số đo như số lượng và doanh thu; các bảng chiều mô tả ngày, sản phẩm, khách hàng và cửa hàng.

```text
                 DimDate
                    |
DimProduct -- FactSales -- DimCustomer
                    |
                 DimStore
```

Mô hình này hỗ trợ câu hỏi như “doanh thu theo tháng và nhóm sản phẩm” hoặc “số lượng bán theo khu vực”. Điều quan trọng là định nghĩa grain trước khi chọn số đo. Nếu một hàng đại diện cho một dòng hàng, không thể tùy tiện trộn thêm số liệu ở mức toàn đơn hàng mà không xử lý nguy cơ đếm lặp.

Mô hình phân tích thường nhận dữ liệu từ hệ thống giao dịch qua pipeline ETL/ELT hoặc luồng dữ liệu. Nó tối ưu cho đọc và tổng hợp khối lượng lớn; không nhất thiết là nơi phù hợp để ứng dụng nghiệp vụ cập nhật trạng thái đơn hàng trực tiếp.

### 5.5. So sánh nhanh

| Mô hình | Phù hợp khi | Điểm mạnh | Cần cân nhắc |
|---|---|---|---|
| Quan hệ | Giao dịch, dữ liệu có quan hệ và ràng buộc rõ | Transaction, khóa, ràng buộc, truy vấn kết hợp | Thiết kế quan hệ và phép nối; thay đổi cấu trúc cần quản lý |
| Document | Đọc/ghi theo đối tượng hoặc aggregate | Dữ liệu lồng nhau, cấu trúc linh hoạt, truy cập theo document | Dữ liệu lặp, cập nhật xuyên document, truy vấn liên kết |
| Đồ thị | Truy vấn phụ thuộc nhiều bước quan hệ | Biểu diễn và duyệt quan hệ tự nhiên | Mô hình vận hành và truy vấn tổng hợp dạng bảng |
| Phân tích | Báo cáo, tổng hợp và phân tích lịch sử | Truy vấn theo chiều và số đo trên dữ liệu lớn | Pipeline cập nhật, grain, độ trễ và tính nhất quán với nguồn |

Một hệ thống có thể dùng nhiều mô hình cho những mục đích khác nhau. Ví dụ, cơ sở dữ liệu quan hệ quản lý đơn hàng giao dịch, document lưu một số cấu hình linh hoạt, graph phục vụ truy vết quan hệ và kho phân tích phục vụ báo cáo. Khi đó cần xác định nguồn dữ liệu gốc, cách đồng bộ, độ trễ chấp nhận được và cách xử lý dữ liệu sai lệch.

## 6. Chuẩn hóa, phi chuẩn hóa và lựa chọn vật lý

Sau khi có cấu trúc logic, nhóm cần quyết định cách tổ chức dữ liệu vật lý.

**Chuẩn hóa (normalization)** phân rã dữ liệu để giảm dư thừa và tránh các bất thường khi thêm, sửa hoặc xóa. Ví dụ, thông tin khách hàng thường được lưu một lần trong bảng `customers`, còn bảng `orders` tham chiếu bằng `customer_id`.

**Phi chuẩn hóa (denormalization)** chủ động lặp hoặc tổng hợp dữ liệu để cải thiện cách đọc, giảm phép nối hoặc phục vụ một workload cụ thể. Ví dụ, lưu tên sản phẩm và đơn giá vào dòng đơn hàng có thể cần thiết để giữ lịch sử giao dịch, hoặc một bản chiếu có thể lưu tổng doanh số để truy vấn báo cáo nhanh hơn.

Cả hai đều là quyết định thiết kế. Khi phi chuẩn hóa, cần trả lời: dữ liệu nào là nguồn gốc, bản sao được cập nhật lúc nào, điều gì xảy ra nếu đồng bộ thất bại và làm sao kiểm tra chênh lệch?

Ở mức vật lý, còn cần cân nhắc:

- **Kiểu dữ liệu:** đủ miền giá trị và độ chính xác; tiền tệ không nên dùng số thực dấu phẩy động cho phép tính cần chính xác thập phân.
- **Khóa và ràng buộc:** bảo vệ tính duy nhất, tham chiếu và miền giá trị.
- **Chỉ mục (index):** hỗ trợ truy vấn thực tế; chỉ mục tăng tốc một số thao tác đọc nhưng tiêu tốn dung lượng và làm tăng chi phí ghi.
- **Phân vùng (partitioning):** có thể giúp quản lý và truy vấn tập dữ liệu lớn khi khóa phân vùng phù hợp với workload.
- **Lịch sử và thời gian:** xác định cần lưu trạng thái hiện tại, các sự kiện thay đổi hay ảnh chụp theo thời điểm.
- **Bảo vệ dữ liệu:** phân loại dữ liệu nhạy cảm, giới hạn quyền truy cập và xác định thời hạn lưu trữ.

Không nên chọn chỉ mục, phân vùng hoặc kỹ thuật lưu trữ chỉ vì chúng phổ biến. Hãy dựa trên truy vấn, dữ liệu đo được và mục tiêu vận hành.

## 7. Kiểm chứng một mô hình dữ liệu

Một mô hình chỉ có vẻ hợp lý trên sơ đồ vẫn có thể thất bại khi gặp tình huống thật. Hãy kiểm chứng bằng các ví dụ cụ thể:

1. **Luồng bình thường:** khách hàng tạo đơn, thêm hai dòng hàng, thanh toán thành công.
2. **Luồng lỗi:** thanh toán thất bại, khách hàng thử lại; hệ thống lưu được cả hai lần xử lý.
3. **Thay đổi theo thời gian:** giá sản phẩm thay đổi sau khi đơn hàng được xác nhận; lịch sử đơn hàng vẫn giữ đúng đơn giá cũ.
4. **Trường hợp biên:** khách hàng chưa có đơn hàng, đơn hàng có nhiều dòng hàng, một sản phẩm ngừng kinh doanh.
5. **Cập nhật đồng thời:** hai yêu cầu cùng cập nhật tồn kho hoặc cùng xử lý một đơn hàng.
6. **Truy vấn quan trọng:** tìm đơn theo khách hàng, xem chi tiết đơn và tổng hợp doanh thu theo tháng.

Với mỗi tình huống, kiểm tra:

- Mô hình có biểu diễn được dữ liệu cần thiết không?
- Có thể xác định duy nhất mỗi đối tượng không?
- Các quan hệ bắt buộc có được bảo vệ không?
- Quy tắc nào được bảo vệ ở database, quy tắc nào ở tầng nghiệp vụ?
- Có thể truy vấn dữ liệu với chi phí hợp lý không?
- Khi dữ liệu thay đổi, lịch sử nào phải được giữ lại?
- Có thể di chuyển và chuyển đổi dữ liệu khi lược đồ tiến hóa không?

Một mô hình có thể được xem là sẵn sàng triển khai khi các khái niệm và quy tắc chính đã được xác nhận, các luồng quan trọng được biểu diễn đầy đủ và các lựa chọn vật lý đáp ứng workload dự kiến. Sau khi triển khai, cần tiếp tục quan sát truy vấn, lỗi dữ liệu và thay đổi nghiệp vụ để điều chỉnh mô hình.

## 8. Những sai lầm thường gặp

- **Thiết kế theo màn hình:** tạo một cấu trúc riêng cho từng trang giao diện khiến cùng một khái niệm bị lưu nhiều cách. Hãy bắt đầu từ nghiệp vụ và các luồng dữ liệu dùng chung.
- **Biến mọi danh từ thành bảng:** một danh từ có thể chỉ là thuộc tính hoặc value object. Chỉ tách thực thể khi có ý nghĩa định danh, vòng đời hoặc quan hệ cần quản lý riêng.
- **Chọn công nghệ trước khi hiểu truy vấn:** dùng document, graph hay relational chỉ vì xu hướng có thể khiến mô hình không phù hợp với workload.
- **Bỏ qua quy tắc và lịch sử:** chỉ lưu trạng thái hiện tại hoặc giá hiện tại có thể làm mất khả năng giải thích một giao dịch trong quá khứ.
- **Dùng định danh dễ thay đổi làm khóa:** email, tên hoặc mã có quy tắc tái sử dụng có thể gây lỗi tham chiếu khi thay đổi.
- **Phi chuẩn hóa không có nguồn sự thật:** sao chép dữ liệu mà không có quy tắc đồng bộ sẽ tạo ra các phiên bản mâu thuẫn.
- **Không kiểm tra tình huống biên:** mô hình chỉ chạy với dữ liệu mẫu đẹp có thể hỏng khi gặp bản ghi thiếu, cập nhật đồng thời hoặc quy trình thất bại.

## 9. Kết luận

Mô hình hóa dữ liệu chuyển hiểu biết nghiệp vụ thành cấu trúc dữ liệu có ý nghĩa, quan hệ rõ ràng và quy tắc có thể kiểm chứng. Nó giúp nhóm thống nhất ngôn ngữ, bảo vệ tính đúng đắn, hỗ trợ truy vấn và kiểm soát chi phí thay đổi.

Một mô hình tốt không được đánh giá chỉ bằng số lượng bảng hay mức độ phức tạp của sơ đồ. Hãy đánh giá nó qua khả năng biểu diễn đúng nghiệp vụ, bảo toàn lịch sử cần thiết, hỗ trợ các cách sử dụng dữ liệu quan trọng và tiến hóa an toàn khi yêu cầu thay đổi.

## Tự kiểm tra

1. Vì sao mô hình dữ liệu không đồng nghĩa với lược đồ cơ sở dữ liệu?
2. Trong ví dụ bán hàng, vì sao `OrderItem` có thể là một thực thể riêng?
3. Nếu giá sản phẩm thay đổi, dữ liệu nào cần giữ để giải thích đơn hàng cũ?
4. Khi nào mô hình document có thể phù hợp hơn mô hình quan hệ? Khi nào mô hình đồ thị có lợi thế?
5. Vì sao cần xác định grain trước khi thiết kế bảng fact trong mô hình phân tích?
6. Hãy chọn một quy trình nghiệp vụ quen thuộc, liệt kê thực thể, thuộc tính, quan hệ, bất biến và ba truy vấn quan trọng của quy trình đó.

