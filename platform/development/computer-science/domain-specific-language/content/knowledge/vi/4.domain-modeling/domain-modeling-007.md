# Thuộc tính và siêu dữ liệu

Trong mô hình miền, mỗi khái niệm cần được mô tả đủ rõ để người đọc hiểu nó đại diện cho điều gì và hệ thống có thể xử lý nó nhất quán. Một khái niệm như `Order` (đơn hàng) có thể có mã định danh, ngày tạo, trạng thái, tổng tiền và danh sách dòng hàng. Những đặc điểm mô tả đối tượng đó được gọi là **thuộc tính**. Bên cạnh chúng, mô hình có thể lưu thông tin giúp giải thích, quản lý hoặc kiểm soát dữ liệu và định nghĩa, chẳng hạn nguồn gốc, phiên bản, người chịu trách nhiệm hay mức độ nhạy cảm. Những thông tin mô tả dữ liệu hoặc định nghĩa dữ liệu này thường được gọi là **siêu dữ liệu (metadata)**.

Trong thiết kế Domain-Specific Language (DSL), phân biệt rõ hai nhóm thông tin giúp ngôn ngữ có mô hình miền chính xác. Thuộc tính diễn tả sự thật hoặc đặc điểm của đối tượng trong miền. Siêu dữ liệu cung cấp ngữ cảnh để con người và công cụ hiểu, quản lý, kiểm tra hoặc xử lý các định nghĩa đó.

## 1. Thuộc tính trong mô hình miền là gì?

**Thuộc tính (attribute)** là một đặc điểm có tên, được dùng để mô tả một khái niệm miền. Thuộc tính có thể biểu diễn giá trị đơn giản, một tập giá trị, hoặc tham chiếu đến khái niệm khác. Mỗi thuộc tính cần có ý nghĩa xác định trong ngữ cảnh của khái niệm sở hữu nó.

Ví dụ, mô hình miền bán hàng có thể chứa:

```text
Customer
  customerId
  fullName
  email
  registeredAt

Order
  orderId
  placedAt
  status
  totalAmount
```

`customerId` định danh khách hàng; `fullName` lưu tên hiển thị; `email` là địa chỉ liên hệ; `placedAt` cho biết thời điểm đặt hàng; `status` biểu diễn trạng thái của đơn; `totalAmount` là tổng tiền theo quy tắc tính toán của miền.

Một thuộc tính không chỉ là tên cột trong cơ sở dữ liệu. Nó là một phần của ý nghĩa mô hình. Ví dụ, `totalAmount` có thể được tính từ các dòng hàng, thuế và chiết khấu. Việc lưu nó hay tính tại thời điểm cần dùng là quyết định triển khai; ý nghĩa nghiệp vụ của tổng tiền vẫn phải được định nghĩa rõ.

### 1.1. Thuộc tính gắn với một khái niệm

Thuộc tính luôn cần được hiểu trong ngữ cảnh. Tên `status` đứng riêng không cho biết nó là trạng thái đơn hàng, thanh toán hay giao vận. Khi gắn với `Order.status`, mô hình phải định nghĩa những trạng thái hợp lệ và ý nghĩa chuyển đổi của chúng.

| Khái niệm | Thuộc tính | Ý nghĩa trong miền |
|---|---|---|
| `Customer` | `email` | Địa chỉ dùng để liên hệ với khách hàng |
| `Order` | `placedAt` | Thời điểm đơn hàng được đặt |
| `Order` | `status` | Trạng thái xử lý của đơn hàng |
| `OrderLine` | `quantity` | Số lượng sản phẩm trên dòng hàng |
| `Money` | `currency` | Loại tiền tệ của một khoản tiền |

Không nên dùng một thuộc tính có tên chung chung cho nhiều ý nghĩa khác nhau chỉ vì kiểu dữ liệu giống nhau. `createdAt` của khách hàng và `createdAt` của đơn hàng có thể cùng kiểu thời gian, nhưng chúng nói về hai sự kiện khác nhau.

### 1.2. Thuộc tính và quan hệ

Không phải mọi thông tin liên quan đến một đối tượng đều nên được mô hình hóa thành một giá trị đơn. Một đơn hàng thuộc về một khách hàng là **quan hệ** giữa hai khái niệm. Trong một mô hình hướng đối tượng, quan hệ có thể được biểu diễn bằng thuộc tính tham chiếu như `order.customer`. Trong mô hình khái niệm, điều quan trọng là nêu rõ đây là liên kết giữa `Order` và `Customer`, cùng số lượng và quy tắc của liên kết.

Ví dụ:

```text
Order
  orderId: OrderId
  customer: Customer
  lines: List<OrderLine>
```

`customer` tham chiếu đến một khách hàng; `lines` là tập các dòng hàng của đơn. Mô hình cần nói rõ một đơn có đúng một khách hàng hay có thể chưa gắn khách hàng, và danh sách dòng hàng có được phép rỗng hay không.

## 2. Mô tả đầy đủ một thuộc tính

Chỉ ghi tên thuộc tính là chưa đủ để triển khai và kiểm tra. Một định nghĩa tốt thường làm rõ kiểu, ý nghĩa, tính bắt buộc, số lượng giá trị, miền giá trị hợp lệ và các quy tắc liên quan.

### 2.1. Tên và ý nghĩa

Tên thuộc tính nên thể hiện khái niệm mà nó lưu trữ. Ưu tiên tên rõ nghĩa như `orderDate`, `unitPrice`, `shippingAddress` thay cho `value`, `data` hoặc `info`. Tên cần nhất quán về cách viết và thuật ngữ giữa các phần của mô hình.

Mỗi thuộc tính nên có định nghĩa ngắn, đặc biệt khi tên có thể được hiểu theo nhiều cách. Ví dụ, `orderDate` có thể là ngày khách đặt hàng, ngày hệ thống ghi nhận đơn hoặc ngày đơn được xác nhận. Nếu những mốc này khác nhau trong nghiệp vụ, hãy mô hình hóa riêng.

### 2.2. Kiểu dữ liệu

Kiểu dữ liệu cho biết loại giá trị mà thuộc tính có thể nhận. Các kiểu phổ biến gồm:

| Nhóm kiểu | Ví dụ | Lưu ý khi mô hình hóa |
|---|---|---|
| Văn bản | `String`, `EmailAddress` | Phân biệt văn bản tự do với chuỗi có định dạng hoặc quy tắc miền |
| Số nguyên | `Integer`, `Quantity` | Xác định đơn vị, dấu âm có hợp lệ không và giới hạn |
| Số thập phân | `Decimal`, `Percentage` | Quy định độ chính xác và cách làm tròn |
| Boolean | `Boolean` | Dùng khi chỉ có hai trạng thái có nghĩa; tránh dùng để thay cho nhiều trạng thái |
| Ngày và thời gian | `Date`, `Instant`, `LocalDateTime` | Phân biệt ngày lịch, thời điểm tuyệt đối và giờ địa phương |
| Liệt kê | `OrderStatus` | Xác định danh sách giá trị được phép và ý nghĩa của từng giá trị |
| Kiểu miền | `Money`, `Address`, `CustomerId` | Gói quy tắc và ý nghĩa đặc thù của miền vào một kiểu có tên |
| Tập hợp | `List<OrderLine>`, `Set<Tag>` | Xác định thứ tự, tính duy nhất và số lượng phần tử |

Kiểu dữ liệu nên phản ánh ý nghĩa, không chỉ cách lưu trữ. Chẳng hạn, mã bưu chính có thể gồm chữ và số, vì vậy không nên mặc định coi nó là số nguyên chỉ vì thường nhìn thấy chữ số. Mã định danh cũng không phải đại lượng để cộng hoặc so sánh theo giá trị số học.

### 2.3. Kiểu miền và kiểu nguyên thủy

Kiểu nguyên thủy như `String`, `Integer` và `Boolean` tiện dụng nhưng có thể quá rộng. Nếu một giá trị có quy tắc riêng, hãy cân nhắc tạo kiểu miền:

```text
type EmailAddress = String
  constraint matchesEmailFormat

type OrderId = String
  constraint isNonEmpty

type Money = {
  amount: Decimal
  currency: CurrencyCode
}
```

Đây là cú pháp minh họa, không phải chuẩn ngôn ngữ cụ thể. `EmailAddress` có ý nghĩa rõ hơn một chuỗi bất kỳ; `Money` gom số tiền và loại tiền tệ thành một giá trị có cấu trúc. Một hệ thống thực tế cần định nghĩa chính xác các ràng buộc và cách xác thực chúng.

### 2.4. Bắt buộc, tùy chọn và giá trị chưa biết

Mô hình cần phân biệt thuộc tính bắt buộc với thuộc tính tùy chọn. Ví dụ, một đơn hàng phải có mã định danh và thời điểm đặt, nhưng có thể chưa có mã vận đơn nếu chưa được giao cho đơn vị vận chuyển.

```text
Order
  orderId: OrderId required
  placedAt: Instant required
  trackingNumber: String optional
```

Không nên đồng nhất các trạng thái sau:

- Không có giá trị vì thuộc tính không áp dụng.
- Chưa có giá trị vì thông tin chưa được cung cấp.
- Không biết giá trị vì không thể xác định.
- Có giá trị rỗng theo đúng ý nghĩa nghiệp vụ.

Ví dụ, `middleName` có thể không áp dụng với một số hồ sơ, trong khi `deliveryDate` có thể chưa biết vì đơn chưa được giao. Nếu hệ thống cần phân biệt các trường hợp này, mô hình phải thể hiện chúng bằng kiểu hoặc trạng thái riêng thay vì dùng chung một giá trị `null` không rõ nghĩa.

### 2.5. Số lượng và tính duy nhất

Một thuộc tính có thể chứa một giá trị hoặc nhiều giá trị. Mô hình cần làm rõ số lượng tối thiểu và tối đa:

- `email: EmailAddress` — một địa chỉ email.
- `aliases: List<String>` — danh sách bí danh, có thứ tự.
- `tags: Set<Tag>` — tập nhãn không lặp.
- `lines: List<OrderLine>` — danh sách dòng hàng; thường cần ít nhất một dòng.

`List` và `Set` không tương đương. Danh sách giữ thứ tự và có thể chứa phần tử trùng lặp; tập hợp thường không cho phép trùng lặp và không nhất thiết có thứ tự. Chọn cấu trúc theo ý nghĩa nghiệp vụ.

### 2.6. Ràng buộc và bất biến

Ràng buộc (constraint) quy định điều kiện mà giá trị phải thỏa mãn. Ví dụ:

- `quantity` phải là số nguyên dương.
- `discountRate` nằm trong khoảng từ 0 đến 1.
- `email` phải theo định dạng được chấp nhận.
- `currency` phải thuộc danh mục tiền tệ mà hệ thống hỗ trợ.
- `totalAmount` không được âm nếu miền không cho phép hoàn tiền biểu diễn bằng tổng âm.

Có thể biểu diễn một số ràng buộc bằng cú pháp giả định:

```text
attribute quantity: Integer
  required
  min 1

attribute discountRate: Decimal
  min 0
  max 1
```

Ràng buộc cũng có thể áp dụng giữa nhiều thuộc tính. Ví dụ, `endDate` phải sau hoặc bằng `startDate`; tổng tiền đơn hàng phải phù hợp với các dòng hàng, thuế và chiết khấu. Các điều kiện này thường là bất biến của khái niệm hoặc quy tắc miền, không chỉ là kiểm tra riêng lẻ trên một trường.

### 2.7. Giá trị mặc định, giá trị dẫn xuất và khả năng thay đổi

Giá trị mặc định được dùng khi người tạo không cung cấp giá trị, nhưng cần phân biệt mặc định kỹ thuật với quy tắc nghiệp vụ. `status = DRAFT` có thể là mặc định hợp lệ khi tạo đơn; tự đặt `discountRate = 0` có thể che giấu trường hợp dữ liệu chiết khấu chưa được tính.

Thuộc tính dẫn xuất (derived attribute) được tính từ dữ liệu khác. Ví dụ `totalAmount` có thể bằng tổng thành tiền các dòng hàng cộng thuế và phí rồi trừ chiết khấu. Mô hình cần nêu công thức, thời điểm tính và cách xử lý làm tròn. Nếu giá trị được lưu lại để tăng hiệu năng, phải xác định cách đồng bộ khi dữ liệu nguồn thay đổi.

Ngoài ra, hãy xác định thuộc tính có được sửa sau khi tạo hay không. Mã đơn hàng có thể bất biến; địa chỉ giao hàng có thể được sửa trước khi gửi; trạng thái đơn hàng chỉ được thay đổi qua các chuyển trạng thái hợp lệ.

## 3. Siêu dữ liệu là gì?

**Siêu dữ liệu (metadata)** là dữ liệu cung cấp thông tin về dữ liệu, cấu trúc, định nghĩa hoặc tài nguyên được mô tả. Trong mô hình miền và DSL, siêu dữ liệu có thể giúp con người hiểu một định nghĩa, giúp công cụ tạo tài liệu, xác thực, phân quyền, quản lý phiên bản hoặc theo dõi nguồn gốc.

Ví dụ, một thuộc tính `email` có thể có siêu dữ liệu cho biết:

- Mô tả: địa chỉ email liên hệ của khách hàng.
- Chủ sở hữu nghiệp vụ: bộ phận chăm sóc khách hàng.
- Mức phân loại: dữ liệu cá nhân.
- Nguồn: hệ thống quản lý khách hàng.
- Phiên bản định nghĩa: bắt đầu áp dụng từ một phiên bản mô hình cụ thể.

Những thông tin này giúp quản lý thuộc tính nhưng không nhất thiết là giá trị email của từng khách hàng.

### 3.1. Các nhóm siêu dữ liệu thường gặp

| Nhóm siêu dữ liệu | Mô tả | Ví dụ |
|---|---|---|
| Mô tả (descriptive) | Giải thích ý nghĩa và cách sử dụng | Mô tả, nhãn hiển thị, ví dụ |
| Cấu trúc (structural) | Mô tả hình dạng và quan hệ của dữ liệu | Kiểu, trường con, số lượng, quan hệ |
| Nguồn gốc (provenance) | Cho biết dữ liệu đến từ đâu và được biến đổi thế nào | Hệ thống nguồn, tác giả, lịch sử chuyển đổi |
| Vận hành và kiểm toán | Ghi nhận hoạt động trong vòng đời dữ liệu | Thời điểm tạo, lần cập nhật, tác nhân thay đổi |
| Quản trị và bảo mật | Hướng dẫn kiểm soát và sử dụng dữ liệu | Mức nhạy cảm, chính sách lưu giữ, quyền truy cập |
| Phiên bản và vòng đời | Theo dõi sự thay đổi của mô hình hoặc định nghĩa | Phiên bản, ngày hiệu lực, trạng thái ngừng dùng |
| Ngữ nghĩa | Làm rõ cách diễn giải và quan hệ với thuật ngữ chuẩn | Mã thuật ngữ, đơn vị, từ đồng nghĩa |

Các nhóm này có thể chồng lấn. Ví dụ, thông tin chủ sở hữu vừa phục vụ mô tả vừa hỗ trợ quản trị. Điều quan trọng là xác định ai sử dụng siêu dữ liệu và quy tắc nào áp dụng cho nó.

### 3.2. Siêu dữ liệu của mô hình và siêu dữ liệu của bản ghi

Cần phân biệt siêu dữ liệu mô tả **định nghĩa** với siêu dữ liệu mô tả **một bản ghi cụ thể**.

- Siêu dữ liệu của mô hình: mô tả thuộc tính `Customer.email`, ví dụ nhãn, hướng dẫn nhập, phân loại nhạy cảm hoặc phiên bản định nghĩa.
- Siêu dữ liệu của bản ghi: mô tả một giá trị email cụ thể, ví dụ hệ thống nguồn, thời điểm nhập hoặc trạng thái xác minh của địa chỉ đó.

Ví dụ, `@sensitive(personal)` gắn vào định nghĩa thuộc tính `email` có thể nói rằng mọi giá trị email thuộc loại dữ liệu cá nhân. Trong khi đó, `verifiedAt` của một khách hàng là sự kiện nghiệp vụ về thời điểm địa chỉ của khách hàng đó được xác minh. Hai thông tin này ở hai cấp độ khác nhau.

### 3.3. Metadata không phải lúc nào cũng là một trường dữ liệu

Một số siêu dữ liệu được lưu trong bảng mô tả lược đồ, tệp định nghĩa hoặc phần chú giải của DSL, không nằm trong từng bản ghi nghiệp vụ. Chẳng hạn, mô tả “Địa chỉ email liên hệ của khách hàng” thường là metadata của định nghĩa thuộc tính, không cần lặp lại trong mỗi bản ghi khách hàng.

Ngược lại, một trường như `createdAt` có thể là thuộc tính nghiệp vụ nếu thời điểm tạo là sự thật có ý nghĩa đối với miền, chẳng hạn thời điểm đơn hàng được đặt để xác định thời hạn giao hàng. Nếu thời điểm đó chỉ được hệ thống ghi lại nhằm vận hành hoặc kiểm toán, nó có thể được xem là metadata quản trị. Cách phân loại phụ thuộc vào ngữ nghĩa và mục đích sử dụng, không chỉ dựa vào tên trường.

## 4. Phân biệt thuộc tính và siêu dữ liệu

Ranh giới giữa hai khái niệm cần được quyết định theo câu hỏi: thông tin này có mô tả sự thật hoặc đặc điểm của đối tượng trong miền hay chủ yếu mô tả cách dữ liệu/định nghĩa được quản lý và diễn giải?

| Tiêu chí | Thuộc tính miền | Siêu dữ liệu |
|---|---|---|
| Đối tượng được mô tả | Đối tượng, sự kiện hoặc khái niệm nghiệp vụ | Dữ liệu, định nghĩa, lược đồ hoặc tài nguyên |
| Vai trò | Tham gia vào trạng thái, hành vi hoặc quyết định của miền | Giải thích, phân loại, quản lý, kiểm soát hoặc theo dõi |
| Ví dụ trên `Customer.email` | Giá trị địa chỉ email | Mô tả trường, mức nhạy cảm, chủ sở hữu dữ liệu |
| Nơi lưu | Thường nằm trong bản ghi hoặc mô hình miền | Có thể nằm trong lược đồ, annotation, catalog hoặc bản ghi kiểm toán |
| Người sử dụng | Quy tắc nghiệp vụ và ứng dụng miền | Con người, công cụ thiết kế, quản trị, bảo mật và tích hợp |

Ví dụ về đơn hàng:

```text
Order
  orderId: OrderId
  placedAt: Instant
  status: OrderStatus
  totalAmount: Money
```

Các thuộc tính trên mô tả đơn hàng. Một số metadata có thể gắn với định nghĩa:

```text
@description("Đơn hàng do khách hàng tạo trong cửa hàng")
@owner("Sales Operations")
@since("2.1")
entity Order {
  @description("Mã định danh duy nhất của đơn hàng")
  orderId: OrderId

  @sensitivity("internal")
  status: OrderStatus
}
```

Đây là ví dụ cú pháp giả định. `@description`, `@owner`, `@since` và `@sensitivity` là metadata của định nghĩa; chúng không tự động trở thành các trường `description`, `owner`, `since` hay `sensitivity` trên từng đơn hàng. Muốn metadata tạo ra hành vi thực thi, DSL phải định nghĩa rõ ý nghĩa và bộ xử lý tương ứng.

## 5. Siêu dữ liệu giúp ích gì trong thiết kế DSL?

### 5.1. Làm rõ ý nghĩa cho người đọc

Một định nghĩa thuộc tính với tên và kiểu có thể chưa đủ để người dùng hiểu. Mô tả, nhãn, ví dụ và hướng dẫn giúp người viết DSL chọn đúng khái niệm.

Ví dụ, `amount: Decimal` không cho biết đây là giá trước thuế, tổng thanh toán hay số tiền hoàn lại. Metadata mô tả và đơn vị có thể làm rõ, nhưng nếu sự khác biệt ảnh hưởng đến logic nghiệp vụ thì nên dùng tên hoặc kiểu miền riêng, không chỉ dựa vào chú thích.

### 5.2. Sinh tài liệu và công cụ hỗ trợ

Các công cụ có thể đọc metadata để tạo tài liệu tham khảo, danh mục thuật ngữ, biểu mẫu nhập liệu, gợi ý trong trình soạn thảo hoặc thông báo lỗi thân thiện. Nhờ đó, cùng một định nghĩa có thể phục vụ cả người viết DSL và công cụ phát triển.

Ví dụ, metadata `@displayName("Ngày đặt hàng")` và `@description("Thời điểm khách xác nhận đặt hàng")` có thể giúp giao diện quản trị hiển thị nhãn và hướng dẫn nhất quán.

### 5.3. Quản trị và bảo vệ dữ liệu

Metadata về phân loại dữ liệu có thể giúp hệ thống xác định trường nào chứa thông tin cá nhân, trường nào không được ghi vào log hoặc trường nào chỉ một số vai trò được xem. Tuy nhiên, annotation chỉ là khai báo. Bộ thực thi và hạ tầng phải thực sự áp dụng chính sách tương ứng; gắn nhãn `@sensitive` không tự nó bảo vệ dữ liệu.

### 5.4. Theo dõi nguồn gốc và phiên bản

Khi dữ liệu được nhập từ nhiều hệ thống, metadata về nguồn gốc giúp tìm hiểu dữ liệu đến từ đâu và qua bước biến đổi nào. Metadata phiên bản giúp xác định định nghĩa nào được dùng khi tạo một bản ghi hoặc thực thi một quy tắc.

Điều này quan trọng khi DSL thay đổi theo thời gian. Nếu một thuộc tính được đổi kiểu hoặc ý nghĩa, hệ thống cần biết dữ liệu cũ được tạo theo định nghĩa nào để diễn giải và chuyển đổi đúng.

## 6. Biểu diễn thuộc tính và metadata trong DSL

Một DSL có thể định nghĩa thuộc tính bằng cấu trúc khai báo và metadata bằng annotation, khối mô tả hoặc tệp catalog riêng. Cách chọn phụ thuộc vào người sử dụng, công cụ cần tích hợp và mức độ phức tạp của mô hình.

### 6.1. Khai báo thuộc tính

Ví dụ cú pháp giả định:

```text
entity Product {
  productId: ProductId required
  name: String required
  unitPrice: Money required
  tags: Set<Tag> optional
}
```

Định nghĩa này nêu tên khái niệm, tên thuộc tính, kiểu và tính bắt buộc. Một DSL đầy đủ còn cần quy định cú pháp, quy tắc phân tích, cách xử lý tên trùng và ngữ nghĩa của `required` hoặc `optional`.

### 6.2. Gắn metadata bằng annotation

```text
entity Product {
  @displayName("Mã sản phẩm")
  @description("Mã định danh duy nhất trong catalog")
  @immutable
  productId: ProductId required

  @displayName("Giá bán")
  @unit("VND")
  @sensitivity("internal")
  unitPrice: Money required
}
```

Annotation gắn thông tin vào định nghĩa ngay tại nơi khai báo, thuận tiện khi metadata ngắn và gắn trực tiếp với một phần tử. Cần quy định annotation nào được phép, kiểu giá trị của nó, phạm vi gắn và cách xử lý khi lặp lại.

### 6.3. Tách metadata ra catalog

Khi metadata nhiều hoặc do nhóm quản trị riêng sở hữu, có thể lưu nó trong catalog tách biệt:

```yaml
entity: Product
attributes:
  unitPrice:
    displayName: Giá bán
    description: Giá niêm yết cho một đơn vị sản phẩm
    sensitivity: internal
    owner: Product Operations
```

Đây là YAML minh họa. Khi tách metadata, hệ thống phải có cách liên kết chính xác giữa catalog và định nghĩa gốc, ví dụ bằng tên đầy đủ, định danh ổn định hoặc phiên bản schema. Nếu tên thuộc tính thay đổi mà liên kết không được cập nhật, metadata có thể gắn nhầm hoặc bị mất.

### 6.4. Quy tắc thiết kế annotation

- Dùng tên có ý nghĩa ổn định và thống nhất, chẳng hạn `@description`, `@owner`, `@deprecated`.
- Định nghĩa kiểu dữ liệu và giá trị hợp lệ cho từng annotation.
- Quy định phần tử nào được gắn annotation: mô hình, entity, thuộc tính, kiểu, quy tắc hay toàn bộ module.
- Nêu rõ annotation có được kế thừa hay không; nếu có thì quy tắc ghi đè là gì.
- Phân biệt annotation chỉ phục vụ tài liệu với annotation làm thay đổi hành vi thực thi.
- Báo lỗi khi metadata bắt buộc bị thiếu, sai kiểu hoặc tham chiếu đến giá trị không tồn tại.

Không nên để metadata có tên giống thuộc tính nghiệp vụ nhưng ý nghĩa mơ hồ. Ví dụ, `@status("active")` có thể nói về trạng thái của định nghĩa schema, trong khi `status: CustomerStatus` là trạng thái của khách hàng. Nên làm rõ phạm vi và dùng tên đủ cụ thể.

## 7. Kiểu, đơn vị và ngữ nghĩa của thuộc tính

Một lỗi phổ biến trong mô hình là coi hai giá trị cùng kiểu lưu trữ là cùng ý nghĩa. `Decimal` có thể biểu diễn giá tiền, tỷ lệ phần trăm, trọng lượng hoặc điểm số. Nếu không mô hình hóa đơn vị và ngữ nghĩa, phép tính có thể hợp lệ về mặt cú pháp nhưng sai trong nghiệp vụ.

### 7.1. Đơn vị đo

Với thuộc tính số, cần xác định đơn vị: VND, USD, kilogram, gram, mét, giây hay phần trăm. Ví dụ, cộng `500 gram` với `2 kilogram` cần chuyển đổi đơn vị trước. Một giá trị `10` không đủ ý nghĩa nếu không biết nó là 10 đồng, 10 phần trăm hay 10 kilogram.

Với tiền tệ, nên coi số tiền và mã tiền tệ là một cặp có kiểu. Không cộng trực tiếp hai khoản tiền khác loại tiền nếu chưa có quy tắc quy đổi và thời điểm áp dụng tỷ giá.

### 7.2. Thời gian và múi giờ

Các trường ngày giờ cần phân biệt:

- `Date`: ngày lịch, không nhất thiết có giờ hoặc múi giờ.
- `Instant`: một thời điểm xác định trên dòng thời gian, thường lưu theo chuẩn thống nhất.
- `LocalDateTime`: ngày giờ theo đồng hồ địa phương, chưa tự xác định được một thời điểm toàn cầu nếu thiếu múi giờ hoặc độ lệch.

Ví dụ, ngày sinh thường là `Date`; thời điểm một giao dịch được ghi nhận thường cần `Instant`; giờ mở cửa của cửa hàng có thể là giờ địa phương gắn với múi giờ của địa điểm. Chọn sai kiểu có thể tạo lỗi khi so sánh, sắp xếp hoặc tính thời hạn.

### 7.3. Giá trị liệt kê và trạng thái

Với một thuộc tính trạng thái, nên dùng kiểu liệt kê có tập giá trị được xác định:

```text
enum OrderStatus {
  DRAFT
  CONFIRMED
  PAID
  SHIPPED
  CANCELLED
}
```

Ngoài tập giá trị, miền có thể quy định chuyển trạng thái nào được phép. Ví dụ, đơn hàng đã hủy không thể chuyển sang `SHIPPED` nếu không có quy trình khôi phục rõ ràng. Danh sách enum mô tả giá trị hợp lệ; máy trạng thái hoặc quy tắc miền mô tả chuyển đổi hợp lệ.

## 8. Quản lý thay đổi thuộc tính và metadata

Mô hình miền phát triển theo thời gian. Thuộc tính có thể được thêm, đổi tên, đổi kiểu, tách hoặc ngừng sử dụng. Metadata cũng thay đổi khi chủ sở hữu, chính sách hoặc định nghĩa thuật ngữ thay đổi.

### 8.1. Thay đổi tương thích và không tương thích

| Thay đổi | Tác động có thể có |
|---|---|
| Thêm thuộc tính tùy chọn | Thường ít ảnh hưởng hơn nếu hệ thống cũ bỏ qua trường chưa biết |
| Thêm thuộc tính bắt buộc | Có thể khiến dữ liệu và biểu thức cũ không hợp lệ |
| Đổi tên thuộc tính | Có thể làm hỏng truy vấn, quy tắc và tích hợp đang tham chiếu tên cũ |
| Đổi kiểu | Có thể cần chuyển đổi dữ liệu và kiểm tra lại phép toán |
| Thu hẹp miền giá trị | Một số giá trị cũ có thể không còn hợp lệ |
| Thay đổi ý nghĩa nhưng giữ nguyên tên và kiểu | Nguy hiểm vì hệ thống vẫn chạy nhưng diễn giải dữ liệu khác đi |
| Thay đổi mô tả hoặc nhãn | Thường ít ảnh hưởng logic, nhưng có thể ảnh hưởng tài liệu và giao diện |

Đổi ý nghĩa là trường hợp đặc biệt cần chú ý. Nếu `totalAmount` trước đây bao gồm thuế nhưng sau đó chỉ còn là tổng trước thuế, giữ nguyên tên và kiểu có thể khiến các quy tắc cũ cho kết quả sai mà không phát hiện lỗi kiểu.

### 8.2. Phiên bản và thời gian hiệu lực

Có thể gắn phiên bản cho mô hình hoặc định nghĩa thuộc tính. Nếu quy tắc thay đổi theo thời gian, cần xác định bản ghi dùng định nghĩa nào và định nghĩa có hiệu lực từ khi nào.

```text
@version("3")
@effectiveFrom("2026-01-01")
entity Order {
  totalAmount: Money
}
```

Đoạn mã trên chỉ minh họa ý tưởng. Trong hệ thống thực tế, phiên bản schema và thời gian hiệu lực cần có định dạng, quy tắc so sánh và chính sách tương thích được xác định. Không nên dùng một chuỗi version tùy ý nếu công cụ cần hiểu thứ tự phiên bản.

### 8.3. Ngừng sử dụng thuộc tính

Khi thuộc tính không còn được khuyến nghị, metadata như `@deprecated` có thể thông báo lý do và hướng thay thế:

```text
@deprecated("Use billingAddress instead")
legacyAddress: String optional
```

Ngừng sử dụng không đồng nghĩa xóa ngay. Cần có giai đoạn chuyển đổi, cảnh báo khi tham chiếu, kế hoạch di chuyển dữ liệu và thời điểm loại bỏ. Nếu metadata này được công cụ hiểu, trình biên dịch hoặc trình kiểm tra có thể cảnh báo người viết DSL.

## 9. Ví dụ tổng hợp: mô hình khách hàng và đơn hàng

Ví dụ sau kết hợp thuộc tính miền, kiểu dữ liệu và metadata. Cú pháp chỉ nhằm minh họa cách tổ chức thông tin:

```text
@description("Người mua hàng trong hệ thống")
@owner("Customer Domain Team")
entity Customer {
  @description("Mã định danh khách hàng")
  @immutable
  customerId: CustomerId required

  @description("Tên đầy đủ dùng để hiển thị")
  fullName: String required

  @description("Địa chỉ email liên hệ")
  @sensitivity("personal")
  email: EmailAddress optional
}

@description("Đơn hàng do khách hàng đặt")
entity Order {
  orderId: OrderId required
  customer: Customer required
  placedAt: Instant required
  status: OrderStatus required
  lines: List<OrderLine> minSize 1
  totalAmount: Money derived
}
```

Trong ví dụ:

- `customerId`, `fullName`, `email`, `orderId`, `placedAt`, `status`, `lines` và `totalAmount` là thuộc tính của các khái niệm miền.
- `CustomerId`, `EmailAddress`, `OrderStatus`, `Money` là kiểu miền giúp biểu đạt ý nghĩa và giới hạn giá trị.
- `@description`, `@owner`, `@immutable` và `@sensitivity` là metadata gắn với định nghĩa.
- `derived` cho biết `totalAmount` được tính từ dữ liệu khác; công thức chính xác vẫn phải được định nghĩa trong mô hình hoặc quy tắc miền.

Để DSL thực sự hữu ích, bộ xử lý phải kiểm tra kiểu, tính bắt buộc, số lượng phần tử và annotation. Nó cũng cần hiểu quan hệ giữa `Order` và `Customer`, cũng như quy tắc tính `totalAmount`. Nếu annotation chỉ là chú thích, công cụ có thể hiển thị hoặc tạo tài liệu; nếu annotation điều khiển quyền hoặc hành vi, ngữ nghĩa và cơ chế thực thi phải được quy định rõ.

## 10. Những lỗi thường gặp khi mô hình hóa

| Lỗi | Vì sao gây vấn đề | Cách xử lý |
|---|---|---|
| Dùng tên chung chung như `value` hoặc `data` | Người đọc không biết giá trị đại diện cho điều gì | Đặt tên theo khái niệm miền và ghi định nghĩa |
| Dùng kiểu nguyên thủy cho mọi thứ | Mất ràng buộc và ý nghĩa như tiền tệ, mã định danh, địa chỉ email | Tạo kiểu miền khi có quy tắc hoặc ngữ nghĩa riêng |
| Không xác định đơn vị | Các phép tính có thể đúng cú pháp nhưng sai thực tế | Ghi đơn vị và quy tắc chuyển đổi |
| Dùng `null` cho nhiều trạng thái | Không phân biệt chưa biết, không áp dụng và chưa cung cấp | Mô hình hóa trạng thái rõ ràng |
| Lưu giá trị dẫn xuất mà không có quy tắc đồng bộ | Dữ liệu có thể không nhất quán với nguồn | Định nghĩa công thức và thời điểm tính lại |
| Coi mọi trường thời gian là giống nhau | Có thể sai khi xử lý múi giờ và ngày lịch | Chọn kiểu thời gian theo ý nghĩa |
| Biến metadata thành trường nghiệp vụ | Bản ghi bị trộn dữ liệu quản trị với sự thật miền | Xác định đúng cấp độ và mục đích của thông tin |
| Dùng metadata để thay thế mô hình rõ ràng | Chú thích không đủ để định nghĩa logic quan trọng | Đưa quy tắc ảnh hưởng hành vi vào mô hình hoặc DSL có ngữ nghĩa rõ |
| Annotation không có quy tắc | Các công cụ hiểu cùng metadata theo cách khác nhau | Định nghĩa kiểu, phạm vi, kế thừa và hành vi |
| Thay đổi ý nghĩa mà không đổi phiên bản | Dữ liệu và quy tắc cũ có thể bị diễn giải sai | Quản lý phiên bản và kế hoạch chuyển đổi |

## 11. Nguyên tắc thiết kế thực tế

Khi xây dựng mô hình thuộc tính và metadata cho DSL, có thể áp dụng các nguyên tắc sau:

1. **Bắt đầu từ ý nghĩa nghiệp vụ.** Xác định thuộc tính đang mô tả sự thật nào, ai sử dụng nó và quyết định nào phụ thuộc vào nó.
2. **Chọn kiểu có ý nghĩa.** Dùng kiểu miền khi một giá trị có đơn vị, định dạng, tập giá trị hoặc quy tắc riêng.
3. **Nêu rõ tính bắt buộc và số lượng.** Đừng để người triển khai tự đoán một trường có thể vắng mặt hoặc chứa bao nhiêu giá trị.
4. **Mô hình hóa ràng buộc ở đúng cấp.** Ràng buộc đơn trường gắn với thuộc tính; bất biến nhiều trường gắn với khái niệm hoặc quy tắc miền.
5. **Tách dữ liệu nghiệp vụ khỏi thông tin quản trị.** Chỉ đưa metadata thành thuộc tính bản ghi khi nó thực sự có ý nghĩa trong miền.
6. **Định nghĩa ngữ nghĩa metadata.** Annotation phải có kiểu, phạm vi, quy tắc kế thừa và hành vi rõ ràng.
7. **Quản lý nguồn gốc và phiên bản.** Giữ được thông tin về nơi định nghĩa hoặc dữ liệu xuất phát và phiên bản đã áp dụng.
8. **Kiểm tra bằng ví dụ.** Dùng bản ghi hợp lệ, không hợp lệ, thiếu dữ liệu và trường hợp biên để kiểm chứng mô hình.
9. **Tránh lặp thông tin.** Nếu cùng một mô tả được ghi ở nhiều nơi, xác định một nguồn chuẩn để tránh sai lệch.
10. **Thiết kế cho thay đổi có kiểm soát.** Xác định cách thêm, đổi tên, thay kiểu và ngừng dùng thuộc tính mà không làm hỏng dữ liệu hoặc biểu thức cũ.

## 12. Kết luận

Thuộc tính mô tả đặc điểm và sự thật của các khái niệm trong miền. Một định nghĩa thuộc tính cần nêu rõ tên, ý nghĩa, kiểu, tính bắt buộc, số lượng, ràng buộc, đơn vị và cách thay đổi hoặc tính toán giá trị. Siêu dữ liệu cung cấp ngữ cảnh về dữ liệu và định nghĩa, hỗ trợ mô tả, tìm kiếm, quản trị, bảo mật, kiểm toán và quản lý phiên bản.

Trong DSL, hai nhóm thông tin cần được phân biệt và liên kết có chủ đích. Thuộc tính tạo nên nội dung của mô hình miền; metadata giúp con người và công cụ hiểu, quản lý và sử dụng mô hình đó. Khi ngữ nghĩa, kiểu và phạm vi của cả hai được định nghĩa rõ, DSL sẽ dễ đọc, dễ kiểm tra và có khả năng phát triển theo thay đổi của miền.
