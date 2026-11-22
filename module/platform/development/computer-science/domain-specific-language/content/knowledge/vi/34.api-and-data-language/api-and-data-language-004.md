# Ràng buộc đầu vào

Trong một hệ thống có API và dữ liệu được mô tả bằng ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL), **ràng buộc đầu vào (input constraints)** là những điều kiện quy định dữ liệu nào được phép đi vào hệ thống, dữ liệu đó phải có cấu trúc và kiểu gì, nằm trong giới hạn nào và phải thỏa mãn những quy tắc nghiệp vụ nào. Ràng buộc giúp hệ thống từ chối dữ liệu không hợp lệ ngay tại ranh giới phù hợp, bảo vệ tính nhất quán của mô hình và làm cho hành vi API có thể dự đoán.

Một API có thể nhận dữ liệu từ JSON body, query parameter, path parameter, header, form, file upload hoặc message từ một hệ thống khác. Dù nguồn nào, dữ liệu đều cần được kiểm tra trước khi sử dụng. Ví dụ, trường quantity có thể bắt buộc là số nguyên dương, email phải đúng định dạng, startDate không được sau endDate, và customerId phải tham chiếu đến một khách hàng tồn tại mà người gọi có quyền sử dụng.

Ràng buộc đầu vào không chỉ là kiểm tra kiểu dữ liệu. Một contract tốt kết hợp cấu trúc, requiredness, miền giá trị, định dạng, quan hệ giữa các trường, quy tắc miền, giới hạn tài nguyên và quyền truy cập. DSL API và dữ liệu nên biểu diễn các điều kiện này theo cách rõ ràng, có thể kiểm tra tĩnh, sinh schema hoặc mã validation và dùng nhất quán ở nhiều điểm tiếp nhận dữ liệu.

## 1. Vì sao cần ràng buộc đầu vào?

Dữ liệu đầu vào thường đến từ client, người dùng, hệ thống tích hợp hoặc tệp bên ngoài. Không thể mặc định dữ liệu đó luôn đúng. Một request sai có thể gây:

- Lỗi runtime do ép kiểu hoặc truy cập trường không tồn tại.
- Dữ liệu thiếu hoặc sai định dạng được lưu vào database.
- Vi phạm bất biến nghiệp vụ.
- Tính toán sai do giá trị ngoài phạm vi.
- Tấn công injection hoặc vượt giới hạn tài nguyên.
- Khó truy vết vì lỗi chỉ xuất hiện ở một bước xử lý sâu.
- Khác biệt hành vi giữa API, batch import và message consumer.

Ví dụ một API tạo đơn hàng:

~~~json
{
  "customerId": "C-1024",
  "items": [
    { "productId": "P-88", "quantity": 2 }
  ],
  "deliveryDate": "2027-01-10"
}
~~~

Các điều kiện đầu vào có thể gồm:

- customerId là chuỗi không rỗng và tham chiếu đến khách hàng hợp lệ.
- items phải có ít nhất một phần tử.
- Mỗi productId phải tồn tại và được phép bán.
- quantity là số nguyên lớn hơn 0, không vượt giới hạn mua.
- deliveryDate phải là ngày hợp lệ và nằm trong khoảng có thể giao.
- Người gọi có quyền tạo đơn cho customer đã chỉ định.

Nếu không có contract, mỗi service có thể tự kiểm tra theo cách khác nhau. Một DSL có thể tập trung hóa các ràng buộc để tạo ra API schema, validator, form metadata, tài liệu và test cases nhất quán.

## 2. Ràng buộc đầu vào là một phần của API contract

API contract mô tả cách client tương tác với server: endpoint, method, dữ liệu gửi, dữ liệu trả về, lỗi, xác thực và semantics. Input constraints là phần xác định miền dữ liệu hợp lệ của request.

Một contract đầu vào thường mô tả:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Shape | Request là object, array, scalar hay file? |
| Requiredness | Trường có bắt buộc xuất hiện không? |
| Type | Giá trị thuộc kiểu nào? |
| Nullability | Có chấp nhận null không? |
| Cardinality | Collection có tối thiểu/tối đa bao nhiêu phần tử? |
| Range | Số hoặc ngày nằm trong giới hạn nào? |
| Format | Chuỗi phải theo định dạng nào? |
| Enumeration | Giá trị được chọn từ tập nào? |
| Relationship | Các trường có quan hệ gì với nhau? |
| Domain rule | Giá trị có hợp lệ trong nghiệp vụ không? |
| Access | Người gọi có quyền sử dụng giá trị đó không? |
| Resource limit | Kích thước, độ sâu hoặc số lượng có giới hạn không? |

Ví dụ khai báo DSL minh họa:

~~~text
api POST "/orders" {
    input CreateOrder {
        customerId: CustomerId required
        items: List<OrderItem> minItems 1 maxItems 100
        deliveryDate: LocalDate optional
    }

    constraints {
        items mustNotBeEmpty
        deliveryDate mustBeAfter(today())
    }
}
~~~

Cú pháp chỉ mang tính minh họa. DSL thực tế có thể dùng annotation, block constraint hoặc schema declaration. Điều quan trọng là contract có thể được đọc và kiểm tra mà không cần suy luận từ implementation.

## 3. Các lớp ràng buộc

Có thể chia ràng buộc thành nhiều lớp để xác định nơi kiểm tra phù hợp:

1. **Structural constraints:** cấu trúc object, trường và collection.
2. **Type constraints:** kiểu dữ liệu và khả năng chuyển đổi.
3. **Presence constraints:** required, optional, nullable và default.
4. **Value constraints:** min, max, length, pattern, enum và range.
5. **Cross-field constraints:** quan hệ giữa nhiều trường trong cùng request.
6. **Domain constraints:** quy tắc nghiệp vụ phụ thuộc mô hình hoặc trạng thái hệ thống.
7. **Authorization constraints:** người gọi có quyền thao tác trên dữ liệu được tham chiếu.
8. **Resource constraints:** giới hạn kích thước, độ sâu, số lượng và thời gian xử lý.

Các lớp này thường được thực hiện ở những tầng khác nhau. Parser hoặc deserializer xử lý cấu trúc và kiểu; validator kiểm tra giá trị; domain service kiểm tra bất biến nghiệp vụ; authorization layer kiểm tra quyền; API gateway hoặc transport layer giới hạn kích thước request.

Không nên gom mọi lỗi thành một thông báo chung như “Invalid request”. Hệ thống cần xác định điều kiện nào thất bại và trả lỗi đủ cụ thể để client có thể sửa.

## 4. Ràng buộc kiểu dữ liệu

Type constraint xác định giá trị phải thuộc kiểu nào. Ví dụ:

- String: chuỗi ký tự.
- Integer: số nguyên.
- Decimal: số thập phân chính xác theo precision/scale.
- Boolean: true hoặc false.
- LocalDate: ngày không có timezone.
- Instant: thời điểm tuyệt đối.
- UUID: định danh theo chuẩn UUID.
- Enum: một giá trị trong tập lựa chọn.
- Object: cấu trúc có các trường đã định nghĩa.
- List<T>: danh sách phần tử kiểu T.
- Map<K,V>: ánh xạ khóa K sang giá trị V.

Ví dụ:

~~~text
input RegisterUser {
    username: String
    age: Integer
    active: Boolean
    joinedAt: Instant
    role: UserRole
}
~~~

Type checker của DSL có thể xác nhận khai báo hợp lệ và generator có thể tạo validator tương ứng. Khi nhận JSON, deserializer phải xác định cách chuyển token JSON thành kiểu trong model.

Không nên coi mọi số JSON là cùng một kiểu. Giá trị 1, 1.0 và "1" có thể có semantics khác nhau. Contract cần nói rõ có chấp nhận chuỗi số hoặc chuyển đổi tự động hay không.

## 5. Required, optional và nullable

Ba khái niệm này cần được phân biệt:

- **Required:** trường phải xuất hiện trong request.
- **Optional:** trường có thể không xuất hiện.
- **Nullable:** trường có thể xuất hiện với giá trị null.

Một trường có thể optional nhưng không nullable: client có thể bỏ trường, nhưng nếu gửi thì phải gửi giá trị hợp lệ. Một trường required và nullable phải xuất hiện nhưng giá trị có thể là null.

Bảng minh họa:

| Khai báo | Trường không xuất hiện | Trường có giá trị null | Trường có giá trị hợp lệ |
|---|---|---|---|
| required, non-null | Lỗi | Lỗi | Chấp nhận |
| optional, non-null | Chấp nhận | Lỗi | Chấp nhận |
| required, nullable | Lỗi | Chấp nhận | Chấp nhận |
| optional, nullable | Chấp nhận | Chấp nhận | Chấp nhận |

Ví dụ DSL:

~~~text
input ProfileUpdate {
    displayName: String required
    nickname: String optional
    middleName: String nullable
    bio: String optional nullable
}
~~~

Cú pháp minh họa cần được hiểu theo quy tắc của DSL. Một số ngôn ngữ dùng dấu hỏi cho optional hoặc T? cho nullable. Cần tránh dùng một ký hiệu cho cả hai ý nghĩa nếu điều đó làm client không biết nên bỏ trường hay gửi null.

## 6. Default value

Default value được áp dụng khi trường không được cung cấp theo quy tắc đã định. Ví dụ:

~~~text
input SearchRequest {
    page: Integer default 1
    pageSize: Integer default 20
    sortDirection: SortDirection default ASC
}
~~~

Khi không có page, hệ thống dùng 1. Nhưng cần quy định default có được áp dụng khi client gửi null hay không. Thông thường, missing và explicit null là hai trạng thái khác nhau.

Default nên:

- Có kiểu phù hợp với trường.
- Được công bố trong schema hoặc tài liệu nếu client cần biết.
- Có tính xác định.
- Được áp dụng tại một tầng thống nhất.
- Được lưu vào normalized request nếu ảnh hưởng kết quả.
- Có version nếu thay đổi default làm thay đổi semantics API.

Tránh default phụ thuộc vào thời gian hoặc trạng thái toàn cục mà không được inject rõ ràng. Ví dụ default createdAt = now() nên được áp dụng ở service/domain layer với clock được kiểm soát nếu cần replay.

## 7. Ràng buộc miền giá trị số

Số thường cần giới hạn để tránh dữ liệu vô nghĩa hoặc lỗi tính toán.

Các ràng buộc thường gặp:

- min: giá trị nhỏ nhất.
- max: giá trị lớn nhất.
- exclusiveMin và exclusiveMax: giới hạn không bao gồm biên.
- multipleOf: giá trị phải là bội của một số.
- precision: tổng số chữ số.
- scale: số chữ số sau dấu thập phân.
- positive, nonNegative, negative.
- finite: không chấp nhận NaN hoặc infinity nếu kiểu runtime có thể biểu diễn.

Ví dụ:

~~~text
input ProductPrice {
    amount: Decimal min 0.01 max 1000000000
    quantity: Integer min 1 max 500
    discountRate: Decimal min 0 max 1
}
~~~

Với số tiền, Decimal thường phù hợp hơn floating-point. Nếu yêu cầu hai chữ số thập phân, có thể quy định scale 2 hoặc multipleOf 0.01. Cần quyết định giá trị có nhiều chữ số thập phân được từ chối, làm tròn hay chuẩn hóa. Làm tròn âm thầm có thể khiến tổng tiền khác với giá trị client gửi.

Ràng buộc số cần xác định đơn vị. 100 có thể là đồng, phần trăm, giây hoặc byte. Một kiểu miền như Money<VND>, Percentage hoặc Duration giảm nguy cơ nhầm đơn vị.

## 8. Ràng buộc chuỗi

Chuỗi thường có các điều kiện:

- minLength và maxLength.
- pattern hoặc regular expression.
- format như email, URI, UUID hoặc mã bưu chính.
- allowedValues hoặc enum.
- Không được rỗng hoặc chỉ chứa whitespace.
- Chuẩn hóa Unicode hoặc khoảng trắng.
- Prefix/suffix hoặc quy tắc ký tự.
- Chính sách phân biệt chữ hoa/thường.

Ví dụ:

~~~text
input CreateAccount {
    username: String minLength 3 maxLength 32
        pattern "^[a-zA-Z0-9_]+$"

    email: String format email
    countryCode: String pattern "^[A-Z]{2}$"
}
~~~

minLength cần xác định đếm theo byte, Unicode code point, UTF-16 code unit hay grapheme cluster. Người dùng nhìn thấy một ký tự có thể gồm nhiều code point. Đếm byte UTF-8 không giống đếm ký tự hiển thị.

Regex cũng cần giới hạn độ phức tạp hoặc dùng engine an toàn để tránh biểu thức gây backtracking quá mức. Không nên dùng regex đơn giản để thay thế parser cho một ngôn ngữ con phức tạp.

## 9. Format và validation chuyên biệt

Format constraint kiểm tra chuỗi có biểu diễn đúng một định dạng đã biết hay không. Ví dụ:

- Email.
- URI/URL.
- UUID.
- Date và date-time.
- Phone number.
- IP address.
- Locale.
- Currency code.
- Mã quốc gia.
- Mã định danh theo nghiệp vụ.

Format validation không nhất thiết xác nhận giá trị có thật hoặc có thể sử dụng. Một chuỗi có thể đúng cấu trúc email nhưng mailbox không tồn tại. Một URL có thể hợp lệ về cú pháp nhưng không truy cập được.

Nên phân biệt:
- **Syntactic format:** hình dạng chuỗi hợp lệ.
- **Existence check:** tài nguyên hoặc định danh có tồn tại.
- **Reachability check:** dịch vụ có truy cập được.
- **Business eligibility:** giá trị có được phép dùng trong nghiệp vụ.

Các kiểm tra ngoài hệ thống thường tốn thời gian và dễ thay đổi, nên không nên nhúng tất cả vào validator cấu trúc chạy đồng bộ.

## 10. Enum và tập giá trị cho phép

Enum giới hạn trường vào một tập giá trị đã biết:

~~~text
enum OrderStatus {
    DRAFT
    SUBMITTED
    APPROVED
    REJECTED
}

input UpdateOrder {
    status: OrderStatus
}
~~~

Enum giúp phát hiện typo và tạo completion trong IDE. Tuy nhiên, khi API thêm enum value mới, client cũ có thể không xử lý được. Cần xác định client có được yêu cầu bỏ qua giá trị không biết, giữ raw string hay phải nâng version.

Với tập giá trị có thể thay đổi thường xuyên, có thể dùng reference data thay vì enum đóng. Ví dụ danh sách loại sản phẩm được quản trị trong database. Khi đó validation phải kiểm tra code có tồn tại và đang active tại thời điểm xử lý.

## 11. Ràng buộc collection

List hoặc array cần giới hạn cardinality và nội dung:

- minItems, maxItems.
- uniqueItems.
- Kiểu của từng phần tử.
- Ràng buộc lồng nhau.
- Giới hạn số phần tử null.
- Thứ tự có ý nghĩa hay không.
- Có cho phép collection rỗng không.

Ví dụ:

~~~text
input BulkUpdate {
    productIds: List<UUID> minItems 1 maxItems 500 uniqueItems
    tags: List<String> maxItems 20
}
~~~

Nếu collection cần unique, cần định nghĩa equality của phần tử. Với object, uniqueness có thể dựa trên toàn bộ object hoặc một khóa như id. Không nên mặc định hai object có cùng ID là trùng nếu contract không nói rõ.

Ràng buộc collection cần được kiểm tra trước khi xử lý hàng loạt để tránh thực hiện một phần rồi mới phát hiện phần tử cuối không hợp lệ. Với batch rất lớn, có thể cần streaming validation và báo lỗi theo lô.

## 12. Ràng buộc object lồng nhau

Request thường chứa object lồng nhau. Mỗi object con có schema và constraints riêng.

~~~text
input CreateOrder {
    customer: CustomerReference required
    shippingAddress: Address required
    billingAddress: Address optional
    items: List<OrderItem> minItems 1
}

input Address {
    line1: String required maxLength 200
    city: String required maxLength 100
    postalCode: String optional maxLength 20
    country: CountryCode required
}

input OrderItem {
    productId: UUID required
    quantity: Integer min 1 max 500
}
~~~

Validator cần đi qua cấu trúc lồng nhau và tạo path chính xác cho lỗi, ví dụ items[2].quantity. Nếu object con có thể null, cần xác định có chạy nested validation hay không.

Một schema tái sử dụng như Address giúp nhiều API dùng cùng quy tắc. Tuy nhiên, không nên ép tất cả ngữ cảnh dùng chung một input model nếu yêu cầu nghiệp vụ khác nhau. Địa chỉ giao hàng có thể bắt buộc phone number trong khi địa chỉ thanh toán thì không.

## 13. Ràng buộc giữa nhiều trường

Một số điều kiện chỉ có thể kiểm tra khi xem nhiều trường cùng lúc.

Ví dụ:

- startDate phải trước endDate.
- password và confirmPassword phải giống nhau.
- Nếu paymentMethod = CARD, trường cardToken phải có.
- Nếu deliveryType = PICKUP, deliveryAddress không được gửi.
- minPrice không được lớn hơn maxPrice.
- Chỉ được gửi một trong hai trường email hoặc phone.

DSL có thể biểu diễn:

~~~text
input BookingRequest {
    startDate: LocalDate required
    endDate: LocalDate required
    paymentMethod: PaymentMethod required
    cardToken: String optional
    pickupPointId: UUID optional
}

constraints {
    startDate mustBeBefore endDate

    when paymentMethod == CARD {
        cardToken mustBePresent
    }

    when paymentMethod == CASH_ON_PICKUP {
        pickupPointId mustBePresent
    }
}
~~~

Cross-field constraints nên được gắn với input object hoặc một validator có tên, không nên đặt rải rác trong controller. Lỗi cần trỏ tới trường hoặc nhóm trường phù hợp.

## 14. Điều kiện phụ thuộc và one-of

Một số request có các nhóm trường loại trừ hoặc phụ thuộc lẫn nhau.

Các dạng phổ biến:

- **Required together:** nếu A có thì B cũng phải có.
- **One-of:** phải cung cấp đúng một trong A, B hoặc C.
- **At-least-one:** phải cung cấp ít nhất một trường.
- **Mutually exclusive:** không được cung cấp đồng thời hai trường.
- **Conditional required:** trường bắt buộc khi điều kiện khác đúng.
- **Dependent schema:** cấu trúc object thay đổi theo discriminator.

Ví dụ:

~~~text
input ContactRequest {
    email: String optional format email
    phone: String optional format phone
}

constraints {
    exactlyOneOf(email, phone)
}
~~~

Đối với payload đa hình, có thể dùng discriminator:

~~~text
input PaymentMethod {
    kind: PaymentKind

    variants {
        CARD -> CardPayment
        BANK_TRANSFER -> BankTransferPayment
        CASH -> CashPayment
    }
}
~~~

Khi kind = CARD, validator áp dụng schema CardPayment. Cách này an toàn hơn một object có hàng chục trường optional mà không rõ trường nào có ý nghĩa trong từng trường hợp.

## 15. Ràng buộc tham chiếu và tính tồn tại

Một trường có thể đúng kiểu nhưng vẫn tham chiếu đến tài nguyên không tồn tại.

Ví dụ customerId là UUID hợp lệ nhưng không có customer tương ứng. Đây là reference constraint hoặc existence constraint.

Có thể phân biệt:

- **Format:** ID có hình dạng hợp lệ.
- **Existence:** bản ghi tồn tại.
- **State:** bản ghi đang ở trạng thái cho phép.
- **Relationship:** tài nguyên thuộc đúng parent hoặc tenant.
- **Authorization:** caller có quyền truy cập tài nguyên.

Ví dụ:

~~~text
input CreateInvoice {
    customerId: UUID required
    orderId: UUID required
}

domainConstraints {
    customerId references Customer where status == ACTIVE
    orderId belongsTo customerId
}
~~~

Các kiểm tra này thường cần truy vấn dữ liệu và phải được thực hiện trong service/domain layer. Nếu kiểm tra tồn tại ở API layer rồi mới ghi database, dữ liệu có thể thay đổi giữa hai thời điểm. Database foreign key hoặc transaction constraint vẫn cần thiết để bảo vệ tính toàn vẹn.

## 16. Ràng buộc nghiệp vụ (domain constraints)

Domain constraint biểu diễn bất biến hoặc quy tắc nghiệp vụ mà dữ liệu phải thỏa mãn.

Ví dụ:
- Số lượng đặt không vượt tồn kho có thể phân bổ.
- Ngày bắt đầu hợp đồng không nằm sau ngày kết thúc.
- Tài khoản không được giao dịch khi bị khóa.
- Hạn mức tín dụng còn đủ cho giao dịch mới.
- Một mã coupon chỉ áp dụng cho sản phẩm đủ điều kiện.
- Tổng các dòng phân bổ phải bằng tổng yêu cầu.

Những điều kiện này có thể phụ thuộc vào trạng thái hiện tại của hệ thống, không chỉ request body. Vì vậy, validator thuần trên DTO không thể thay thế domain service.

Một cách tổ chức:

1. Validate shape và kiểu.
2. Validate giá trị độc lập.
3. Load aggregate/domain state cần thiết.
4. Kiểm tra bất biến nghiệp vụ trong transaction phù hợp.
5. Thực hiện command nếu mọi điều kiện còn đúng.

Không nên gọi domain rule trước khi xác thực và phân quyền đối với resource cần đọc.

## 17. Ràng buộc database và tính toàn vẹn

Validation ở API giúp trả lỗi thân thiện, nhưng database vẫn cần bảo vệ dữ liệu vì có thể có nhiều đường ghi: API, batch, migration, admin tool hoặc message consumer.

Các ràng buộc database thường gồm:

- NOT NULL.
- CHECK.
- UNIQUE.
- PRIMARY KEY.
- FOREIGN KEY.
- Exclusion hoặc constraint đặc thù của database.

Ví dụ SQL:

~~~sql
CREATE TABLE order_item (
    id UUID PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(18, 2) NOT NULL CHECK (unit_price >= 0),
    order_id UUID NOT NULL REFERENCES orders(id)
);
~~~

API validation và database constraints có mục đích khác nhau:
- API validation phát hiện lỗi sớm và giải thích cho client.
- Domain validation kiểm tra quy tắc nghiệp vụ.
- Database constraints bảo vệ trạng thái lưu trữ trước race condition và các đường ghi khác.

Không nên chỉ dựa vào API validation cho uniqueness. Hai request đồng thời có thể cùng vượt qua kiểm tra “chưa tồn tại” rồi cùng insert. Unique constraint ở database là hàng rào cuối cùng; lỗi constraint cần được chuyển thành response có ý nghĩa.

## 18. Chuẩn hóa dữ liệu (normalization)

Normalization chuyển dữ liệu về dạng chuẩn trước khi so sánh, lưu hoặc xử lý. Ví dụ:

- Trim khoảng trắng đầu/cuối.
- Chuẩn hóa Unicode.
- Chuẩn hóa mã quốc gia thành chữ hoa.
- Chuẩn hóa email theo policy.
- Chuẩn hóa số điện thoại về E.164.
- Chuẩn hóa timezone hoặc timestamp.
- Chuyển enum alias về canonical value.

Cần phân biệt normalization với validation. Validation xác định dữ liệu có hợp lệ không; normalization biến biểu diễn hợp lệ thành dạng chuẩn.

Ví dụ:

~~~text
raw username: "  Linh_Nguyen  "
normalized:   "Linh_Nguyen"
~~~

Không phải trường nào cũng nên tự động lowercase hoặc trim. Password có thể phân biệt khoảng trắng; mã định danh có thể phân biệt hoa thường theo nghiệp vụ. Nếu normalization làm thay đổi dữ liệu người dùng gửi, nên công bố semantics và có thể trả normalized value trong response.

Một pipeline thường là:

~~~mermaid
flowchart TD
    A[Raw request] --> B[Decode and parse]
    B --> C[Structural and type validation]
    C --> D[Normalize permitted fields]
    D --> E[Value and cross-field validation]
    E --> F[Domain and authorization checks]
    F --> G[Execute command]
~~~

Thứ tự cụ thể phụ thuộc contract. Ví dụ, kiểm tra độ dài có thể cần chạy sau normalization nếu giới hạn áp dụng cho giá trị chuẩn hóa.

## 19. Coercion và chuyển đổi kiểu

Coercion là chuyển giá trị từ kiểu này sang kiểu khác một cách tự động. Ví dụ chuyển chuỗi "42" thành integer 42 hoặc chuỗi ngày thành LocalDate.

Coercion tiện cho client nhưng có thể tạo mơ hồ:
- "01" có thể là số 1 hoặc mã có số 0 đầu.
- 1.9 chuyển sang integer bằng cách truncate hay reject?
- "true" có phân biệt hoa thường không?
- Chuỗi rỗng có được coi là null không?
- Timestamp không timezone được diễn giải theo timezone nào?

Một API contract tốt nên chọn policy rõ:
- Strict: từ chối kiểu không đúng.
- Controlled coercion: chỉ cho phép các chuyển đổi an toàn đã công bố.
- Lenient: chấp nhận nhiều dạng và chuẩn hóa, nhưng phải tránh mơ hồ.

Đối với ID, mã bưu chính, số tài khoản hoặc mã sản phẩm, thường nên giữ kiểu string thay vì chuyển thành số, vì số 0 đầu có thể có ý nghĩa.

## 20. Thứ tự xử lý và pipeline validation

Validation có thể được tổ chức thành pipeline:

1. Kiểm tra transport: method, content type, request size.
2. Parse payload: JSON/XML/form hoặc binary envelope.
3. Kiểm tra schema và cấu trúc.
4. Chuyển đổi kiểu theo policy.
5. Áp dụng default và normalization.
6. Kiểm tra value constraints.
7. Kiểm tra cross-field constraints.
8. Xác thực danh tính và quyền truy cập.
9. Kiểm tra domain constraints trong transaction.
10. Thực hiện command và ghi dữ liệu.

Không phải mọi hệ thống áp dụng đúng thứ tự này. Authentication thường cần xảy ra trước khi đọc resource nhạy cảm; authorization có thể phụ thuộc vào dữ liệu đã parse. Điểm quan trọng là pipeline phải có thứ tự xác định, tránh chạy domain lookup trên payload chưa được giới hạn kích thước hoặc xác thực cấu trúc.

Có thể dừng ở lỗi đầu tiên để tiết kiệm tài nguyên, hoặc thu thập nhiều lỗi độc lập trong một lần. Với form validation, trả nhiều lỗi thường hữu ích. Với dữ liệu rất lớn hoặc thao tác nhạy cảm, fail-fast có thể phù hợp hơn.

## 21. Validation fail-fast và collect-all

Hai chiến lược phổ biến:

- **Fail-fast:** dừng ngay khi gặp lỗi đầu tiên.
- **Collect-all:** tiếp tục kiểm tra các trường độc lập và trả nhiều lỗi.

Ví dụ collect-all:

~~~json
{
  "errors": [
    {
      "path": "email",
      "code": "FORMAT_EMAIL",
      "message": "Email address is invalid"
    },
    {
      "path": "age",
      "code": "MIN_VALUE",
      "message": "Age must be at least 18"
    }
  ]
}
~~~

Collect-all giúp người dùng sửa nhiều trường cùng lúc. Tuy nhiên, không nên chạy mọi validator bất kể trạng thái. Nếu parse một trường thất bại, validator phụ thuộc vào giá trị đã parse có thể không an toàn.

Có thể chia validator thành các nhóm độc lập và phụ thuộc. Chỉ chạy cross-field validator khi các trường cần thiết đã có giá trị hợp lệ.

## 22. Error model cho ràng buộc đầu vào

Lỗi validation nên có cấu trúc ổn định, không chỉ là một chuỗi tự do.

Một error item có thể gồm:

- path: đường dẫn đến trường.
- code: mã lỗi ổn định.
- message: thông điệp đọc được.
- rejectedValue: giá trị bị từ chối nếu an toàn để hiển thị.
- constraint: tên hoặc loại ràng buộc.
- expected: điều kiện mong đợi.
- source: body, query, path, header hoặc file.
- correlationId: mã truy vết request.

Ví dụ response:

~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more input constraints were violated.",
  "errors": [
    {
      "path": "items[1].quantity",
      "code": "MIN_VALUE",
      "message": "Quantity must be at least 1",
      "constraint": "min",
      "expected": 1
    },
    {
      "path": "deliveryDate",
      "code": "DATE_RANGE",
      "message": "Delivery date must be in the future"
    }
  ]
}
~~~

Mã lỗi nên ổn định hơn message vì message có thể được dịch hoặc chỉnh sửa. Client có thể dùng code để đánh dấu trường, còn người dùng đọc message.

Không nên phản hồi stack trace, SQL error, tên bảng hoặc chi tiết nội bộ. Cũng cần tránh echo password, token hoặc dữ liệu nhạy cảm trong rejectedValue.

## 23. HTTP status và validation error

Các API thường dùng:
- 400 Bad Request cho request không thể parse hoặc không đáp ứng contract.
- 422 Unprocessable Content cho payload có cú pháp hợp lệ nhưng vi phạm quy tắc nội dung, nếu API chọn semantics này.
- 401 Unauthorized khi chưa xác thực.
- 403 Forbidden khi không có quyền.
- 404 Not Found khi resource được tham chiếu không tồn tại hoặc API muốn che giấu sự tồn tại.
- 409 Conflict khi request xung đột với trạng thái hiện tại.
- 413 Content Too Large khi request vượt giới hạn kích thước.
- 415 Unsupported Media Type khi content type không được hỗ trợ.

Điều quan trọng là chọn convention nhất quán và tài liệu hóa. Không nên dùng 400 cho mọi lỗi nghiệp vụ, vì client cần phân biệt request sai cấu trúc với xung đột trạng thái hoặc thiếu quyền.

## 24. Ràng buộc ở body, path, query và header

Mỗi nguồn request có đặc điểm riêng.

### 24.1. Path parameter

Path thường chứa định danh hoặc segment:

~~~text
GET /customers/{customerId}
~~~

customerId cần format hợp lệ. Sau đó service kiểm tra tồn tại và quyền truy cập.

### 24.2. Query parameter

Query thường chứa filter, pagination và sorting:

~~~text
GET /orders?page=1&pageSize=50&status=PAID
~~~

Cần giới hạn page >= 1, pageSize trong phạm vi cho phép, sort field thuộc whitelist và filter enum hợp lệ. Không nên ghép trực tiếp sort field vào SQL.

### 24.3. Header

Header có thể chứa locale, idempotency key, version hoặc conditional request token. Cần kiểm tra format và kích thước, đồng thời phân biệt header do proxy quản lý với header do client kiểm soát.

### 24.4. Body

Body thường chứa object hoặc collection phức tạp. Cần schema validation, giới hạn nesting, kích thước, số phần tử và quy tắc cross-field.

Một DSL có thể khai báo ràng buộc theo từng nguồn để tránh nhầm trường cùng tên nhưng semantics khác nhau.

## 25. Create, replace và partial update

Input constraints có thể khác nhau theo loại thao tác.

- **Create:** trường bắt buộc cần có để tạo object hợp lệ.
- **Replace (PUT):** thường mô tả trạng thái đầy đủ mới; trường thiếu có thể được hiểu là bị xóa hoặc default tùy contract.
- **Partial update (PATCH):** chỉ các trường được gửi mới thay đổi; trường thiếu thường giữ nguyên.
- **Command/action:** payload mô tả một hành động, không nhất thiết là snapshot object.

Ví dụ:

~~~text
input CreateUser {
    name: String required
    email: String required format email
}

input PatchUser {
    name: String optional
    email: String optional nullable format email
}
~~~

Trong PATCH, cần phân biệt:
- Không gửi email: giữ nguyên.
- Gửi email: null: xóa email nếu được phép.
- Gửi email: chuỗi rỗng: chuỗi rỗng, có thể bị từ chối.

Không nên tái sử dụng nguyên schema Create cho PATCH bằng cách biến tất cả trường thành optional mà không xác định semantics của null và default.

## 26. Ràng buộc file upload và binary input

File upload cần các giới hạn riêng:

- Kích thước tối đa.
- Số lượng file.
- Phần mở rộng cho phép.
- MIME type khai báo.
- Nội dung thực tế hoặc magic bytes.
- Tên file và ký tự path.
- Giới hạn giải nén.
- Virus/malware scanning theo môi trường.
- Storage quota và retention.

Không nên tin Content-Type hoặc tên phần mở rộng do client gửi. Server cần kiểm tra nội dung thực tế khi phù hợp.

Đối với archive, cần chống zip bomb và path traversal. Khi giải nén, đường dẫn đầu ra phải nằm trong vùng storage được cấp. Với file lớn, streaming validation có thể tránh giữ toàn bộ file trong memory.

## 27. Ràng buộc kích thước và tài nguyên

Một request có thể hợp lệ về schema nhưng vẫn quá tốn tài nguyên. Ví dụ array có hàng triệu phần tử, string rất lớn hoặc object lồng sâu hàng nghìn cấp.

Các giới hạn nên gồm:

- Maximum request body size.
- Maximum string length.
- Maximum collection size.
- Maximum nesting depth.
- Maximum number of object properties.
- Maximum file upload size.
- Maximum batch size.
- Maximum validation time.
- Rate limit theo caller hoặc tenant.
- Giới hạn số external lookup trong một request.

Các giới hạn cần được áp dụng sớm ở transport/parser để tránh phải parse toàn bộ payload quá lớn trước khi từ chối. API gateway, web server và application validator có thể cùng áp dụng các lớp limit khác nhau.

## 28. Ràng buộc bảo mật và chống injection

Input validation là một phần của bảo mật, nhưng không phải cơ chế duy nhất. Một chuỗi đúng pattern vẫn có thể chứa nội dung nguy hiểm nếu được đưa vào SQL, shell, HTML hoặc template không an toàn.

Nguyên tắc:

- Dùng parameterized query cho SQL.
- Không nối chuỗi input vào shell command.
- Escape output theo ngữ cảnh HTML/JavaScript/URL.
- Validate allowlist cho enum và identifier.
- Giới hạn path và file access.
- Kiểm tra authorization trên resource reference.
- Giới hạn payload và nested structure.
- Không log secret hoặc token.
- Không tin client tự khai báo tenant/role.
- Tách dữ liệu người dùng khỏi expression hoặc code thực thi.

Ví dụ, sortBy nên chỉ chấp nhận một trong các field được công bố như createdAt, amount, status. Nếu nhận bất kỳ chuỗi nào rồi đưa vào câu SQL, input có thể tạo SQL injection.

## 29. Ràng buộc theo tenant và quyền sở hữu

Một ID hợp lệ và tồn tại không có nghĩa caller được phép sử dụng nó. Trong hệ thống multi-tenant, cần xác nhận resource thuộc tenant phù hợp.

Ví dụ:

~~~text
input UpdateProject {
    projectId: UUID required
    name: String optional maxLength 100
}

authorization {
    caller mayUpdate projectId
    projectId mustBelongTo caller.tenant
}
~~~

Tenant ID thường nên lấy từ identity/context đã xác thực, không tin một trường client gửi trong body. Nếu API cho phép chỉ định tenant thay mặt người khác, phải kiểm tra quyền tương ứng.

Không nên chỉ kiểm tra resource tồn tại rồi trả lỗi khác nhau cho mọi trường hợp nếu điều đó làm lộ resource của tenant khác. Có thể cần trả cùng một response cho “không tồn tại” và “không được phép xem” tùy threat model.

## 30. Ràng buộc bất đồng bộ và external validation

Một số validation cần gọi hệ thống ngoài:
- Kiểm tra mã coupon còn hiệu lực.
- Kiểm tra tài khoản thanh toán.
- Kiểm tra địa chỉ giao hàng.
- Kiểm tra hạn mức.
- Kiểm tra tên người dùng chưa được sử dụng.

Các kiểm tra này có độ trễ và có thể thất bại do network. Cần phân biệt:
- Invalid: dữ liệu chắc chắn không hợp lệ.
- Unavailable: chưa thể xác minh do dịch vụ phụ thuộc không sẵn sàng.
- Conflict: dữ liệu hợp lệ nhưng trạng thái đã thay đổi.
- Unauthorized: caller không có quyền.

Nếu kiểm tra uniqueness bằng một query trước insert, vẫn có race condition. Database unique constraint hoặc reservation/transaction là cơ chế quyết định cuối cùng.

Không nên biến một dependency outage thành validation error 400. Client không thể sửa payload để khắc phục lỗi dịch vụ ngoài.

## 31. Constraint composition và tái sử dụng

DSL có thể cho phép định nghĩa reusable constraint:

~~~text
constraint PositiveQuantity {
    value: Integer
    min 1
    max 500
}

constraint EmailAddress {
    value: String
    format email
    maxLength 254
}

input OrderItem {
    quantity: Integer uses PositiveQuantity
}
~~~

Reusable constraint giảm lặp và giúp nhiều API áp dụng cùng semantics. Có thể kết hợp nhiều constraint:

~~~text
input CreateUser {
    username: String uses [
        NonBlank,
        UsernameLength,
        UsernameCharacters
    ]
}
~~~

Cần định nghĩa thứ tự thực thi, cách kết hợp lỗi và cách override. Nếu một constraint dùng cho nhiều ngữ cảnh nhưng có giới hạn khác nhau, có thể tham số hóa thay vì tạo nhiều bản sao gần giống.

Không nên cho phép override làm yếu constraint bảo mật hoặc bất biến cốt lõi một cách vô tình.

## 32. Constraint metadata và sinh schema

Một DSL có thể sinh JSON Schema, OpenAPI hoặc metadata form từ input declaration. Ví dụ:

~~~text
input CreateProduct {
    name: String required minLength 1 maxLength 120
    price: Decimal required min 0
    sku: String required pattern "^[A-Z0-9-]+$"
}
~~~

Có thể ánh xạ thành schema tương đương:

~~~json
{
  "type": "object",
  "required": ["name", "price", "sku"],
  "properties": {
    "name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 120
    },
    "price": {
      "type": "number",
      "minimum": 0
    },
    "sku": {
      "type": "string",
      "pattern": "^[A-Z0-9-]+$"
    }
  },
  "additionalProperties": false
}
~~~

Không phải mọi domain constraint đều có thể biểu diễn trong JSON Schema. Ví dụ kiểm tra tồn kho hoặc quyền sở hữu cần runtime context. Generator cần phân biệt static schema constraints với runtime validation rules, tránh tuyên bố schema đã mô tả toàn bộ hành vi khi chưa đủ.

## 33. Unknown fields và forward compatibility

Khi request chứa trường không được định nghĩa, API cần chọn policy:

- **Reject unknown fields:** từ chối để phát hiện typo và tránh dữ liệu ngoài ý muốn.
- **Ignore unknown fields:** bỏ qua để hỗ trợ client mới gửi extension tới server cũ.
- **Preserve unknown fields:** giữ lại trong extension map hoặc metadata nếu contract hỗ trợ.

Reject giúp contract chặt chẽ và an toàn. Ignore có thể hữu ích cho compatibility nhưng typo có thể bị bỏ qua âm thầm. Preserve phù hợp với hệ thống plugin/extensible nhưng cần giới hạn kích thước và namespace.

Policy có thể khác nhau theo endpoint và version. Với các command nhạy cảm, reject unknown fields thường dễ kiểm soát hơn.

## 34. Versioning của input contract

Input schema thay đổi theo thời gian. Một API cần quản lý compatibility khi:
- Thêm trường bắt buộc.
- Đổi kiểu.
- Giảm max hoặc tăng min.
- Thay enum value.
- Đổi default.
- Thay semantics của null.
- Thêm cross-field constraint.
- Thay format hoặc normalization.
- Loại bỏ field cũ.

Thêm trường optional thường tương thích hơn thêm trường required. Nhưng thay đổi default có thể làm client cũ tạo kết quả khác dù request không đổi.

Có thể dùng API version, schema version hoặc media type version. Cần ghi rõ version nào được chọn và validator nào áp dụng. Nếu version được chọn từ header/path, kiểm tra format và hỗ trợ version trước khi parse body theo schema tương ứng.

## 35. Error localization và trải nghiệm client

Thông báo validation nên dễ hiểu, có thể dịch và không phụ thuộc ngôn ngữ nội bộ của server.

Một error code ổn định có thể có message theo locale:

~~~json
{
  "path": "deliveryDate",
  "code": "DATE_MUST_BE_FUTURE",
  "message": "Delivery date must be in the future"
}
~~~

Client có thể:
- Hiển thị lỗi cạnh field.
- Focus trường đầu tiên có lỗi.
- Hiển thị lỗi cấp form cho cross-field constraint.
- Dùng code để chọn hướng dẫn phù hợp.
- Gửi correlation ID cho support.

Path format cần thống nhất. Có thể dùng JSON Pointer, dot notation hoặc một format riêng được tài liệu hóa. Với collection, path cần chỉ rõ index hoặc item key.

## 36. Ví dụ Java: model và validation

Một DTO Java có thể biểu diễn cấu trúc request:

~~~java
record CreateOrderRequest(
    @NotNull UUID customerId,
    @NotEmpty List<@Valid OrderItemRequest> items,
    @Future LocalDate deliveryDate
) {}

record OrderItemRequest(
    @NotNull UUID productId,
    @Min(1) @Max(500) int quantity
) {}
~~~

Một số validation framework hỗ trợ annotation cho constraint phổ biến. Cross-field rule có thể được triển khai bằng class-level validator:

~~~java
record DateRange(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}

boolean isValid(DateRange range) {
    return range.startDate() != null
        && range.endDate() != null
        && range.startDate().isBefore(range.endDate());
}
~~~

Ví dụ minh họa cần được điều chỉnh theo framework thực tế. Annotation validation thường xử lý cấu trúc và giá trị độc lập; domain rules cần repository, transaction hoặc authorization context nên được giữ trong service/domain layer.

## 37. Ví dụ: pipeline API với input constraints

Một endpoint tạo booking có thể dùng contract:

~~~text
api POST "/bookings" {
    input CreateBooking {
        customerId: UUID required
        startDate: LocalDate required
        endDate: LocalDate required
        guests: Integer required min 1 max 12
        roomType: RoomType required
        specialRequest: String optional maxLength 1000
    }

    constraints {
        startDate mustBeOnOrAfter today()
        startDate mustBeBefore endDate
        endDate mustBeWithin 365 days
    }

    authorize {
        caller mayCreateBookingFor customerId
    }

    handle {
        bookingService.create(normalizedInput)
    }
}
~~~

Quy trình xử lý:

1. Kiểm tra content type và request size.
2. Parse JSON thành input model.
3. Kiểm tra required fields và types.
4. Áp dụng default/normalization theo contract.
5. Kiểm tra min/max và cross-field constraints.
6. Xác thực caller và quyền với customer.
7. Kiểm tra availability trong transaction.
8. Tạo booking.
9. Trả response hoặc structured error.

today() cần có timezone nghiệp vụ rõ. availability có thể thay đổi đồng thời, nên phải được kiểm tra và giữ chỗ trong một transaction hoặc cơ chế đồng bộ phù hợp.

## 38. Kiểm thử ràng buộc đầu vào

Một constraint cần test cả trường hợp hợp lệ, không hợp lệ và giá trị biên.

### 38.1. Kiểm thử kiểu và presence

- Trường required bị thiếu.
- Trường optional bị thiếu.
- Trường nullable nhận null.
- Trường non-null nhận null.
- Kiểu JSON không đúng.
- Coercion được cho phép và bị từ chối.

### 38.2. Kiểm thử boundary

Với min 1 và max 10, kiểm tra:
- 0: invalid.
- 1: valid.
- 10: valid.
- 11: invalid.

Với exclusive boundary, kiểm tra chính giá trị biên và các giá trị sát biên. Với Decimal, kiểm tra precision/scale và rounding.

### 38.3. Kiểm thử string và Unicode

- Chuỗi rỗng.
- Chỉ có whitespace.
- Ký tự Unicode.
- Combining characters.
- Emoji.
- Chuỗi vượt max length.
- Regex input gây tốn CPU.
- Chuỗi có dấu hoặc normalization form khác nhau.

### 38.4. Kiểm thử collection và nested object

- Collection rỗng.
- Ít hơn minItems.
- Nhiều hơn maxItems.
- Phần tử trùng.
- Phần tử null.
- Nested object thiếu field.
- Lỗi tại index cụ thể.

### 38.5. Kiểm thử cross-field và domain

- Ngày bắt đầu bằng ngày kết thúc.
- Giá min lớn hơn max.
- One-of không có trường nào.
- One-of có nhiều trường.
- Reference không tồn tại.
- Resource thuộc tenant khác.
- Trạng thái thay đổi giữa validation và commit.

### 38.6. Kiểm thử lỗi và security

- Error code ổn định.
- Path trỏ đúng field.
- Không lộ secret hoặc stack trace.
- Request quá lớn bị từ chối sớm.
- Unknown field theo đúng policy.
- SQL/shell injection không thay đổi query hoặc command.
- Authorization được áp dụng trước khi trả dữ liệu nhạy cảm.

## 39. Property-based và fuzz testing

Ngoài test case viết tay, có thể dùng property-based testing để tạo nhiều input và kiểm tra invariant.

Ví dụ:
- Với mọi quantity hợp lệ, quantity luôn lớn hơn 0.
- Normalization không làm thay đổi giá trị đã ở dạng chuẩn.
- Parse rồi serialize một input hợp lệ giữ semantics.
- Validator không crash với chuỗi Unicode hoặc cấu trúc lồng sâu trong giới hạn.
- Mọi input vượt maxItems đều bị từ chối.
- Cùng input và cùng context tạo cùng kết quả validation.

Fuzz testing hữu ích cho parser, regex, deserializer và nested structure. Cần giới hạn thời gian, memory và kích thước dữ liệu để test không trở thành denial-of-service trong chính pipeline CI.

## 40. Hiệu năng và thứ tự validation

Validation cũng tiêu tốn tài nguyên. Một request có hàng nghìn phần tử và mỗi phần tử gọi một API ngoài có thể tạo ra hàng nghìn request phụ.

Tối ưu có thể gồm:

- Kiểm tra kích thước và cấu trúc trước.
- Dùng validator thuần, không I/O cho constraint đơn giản.
- Batch lookup cho reference.
- Deduplicate các ID trước khi query.
- Cache reference data có version/TTL phù hợp.
- Giới hạn concurrency.
- Dừng sớm khi request vượt quota.
- Không chạy cross-field validator nếu prerequisite field không hợp lệ.
- Giới hạn số lỗi được trả về cho payload rất lớn.

Không nên đánh đổi tính đúng đắn để giảm chi phí. Ví dụ cache trạng thái tồn kho có thể stale; nếu quyết định cuối phụ thuộc tồn kho, cần kiểm tra lại trong transaction hoặc reservation.

## 41. Ràng buộc trong batch và message processing

Input không chỉ đến từ HTTP. Batch import, event stream và message queue cũng cần validation.

Với batch:
- Có thể validate từng record và trả report theo dòng.
- Cần quy định all-or-nothing hay partial success.
- Giới hạn số record mỗi batch.
- Ghi nhận source file, row number và error code.

Với message:
- Kiểm tra schema version.
- Kiểm tra event ID và idempotency.
- Validate envelope trước payload.
- Xử lý message không hợp lệ bằng dead-letter queue theo policy.
- Không retry vô hạn message có lỗi dữ liệu cố định.

Dùng chung schema và domain validator giúp API và message consumer có semantics nhất quán, nhưng error transport có thể khác nhau.

## 42. Phân biệt validation với authorization và business conflict

Các khái niệm có liên quan nhưng khác nhau:

| Loại | Ví dụ | Kết quả thường gặp |
|---|---|---|
| Validation | quantity phải >= 1 | Request không hợp lệ |
| Authorization | Caller không được sửa order này | Từ chối quyền |
| Domain invariant | Không thể hủy đơn đã giao | Hành động không hợp lệ theo trạng thái |
| Conflict | Version của resource đã thay đổi | Cần refresh hoặc retry có kiểm soát |
| Dependency failure | Dịch vụ kiểm tra bên ngoài không phản hồi | Tạm thời không thể xử lý |

Một số hệ thống gọi tất cả là validation, nhưng phân biệt chúng giúp API trả status và hướng khắc phục chính xác. Không nên báo “field invalid” khi vấn đề thực chất là caller không có quyền hoặc dữ liệu đã bị thay đổi bởi request khác.

## 43. Quy trình triển khai input constraints trong DSL

Có thể triển khai theo các bước:

1. **Mô hình hóa input:** xác định request shape, nguồn dữ liệu và kiểu.
2. **Định nghĩa presence:** required, optional, nullable và default.
3. **Định nghĩa value constraints:** range, length, format, enum và cardinality.
4. **Định nghĩa cross-field rules:** điều kiện phụ thuộc và one-of.
5. **Tách domain rules:** xác định điều kiện cần database hoặc context.
6. **Tách authorization:** xác định resource ownership và caller permission.
7. **Định nghĩa normalization/coercion:** chỉ rõ chuyển đổi được phép.
8. **Định nghĩa error contract:** path, code, message và HTTP semantics.
9. **Sinh schema/validator:** tái sử dụng DSL metadata khi có thể.
10. **Đặt giới hạn tài nguyên:** body, collection, depth, timeout và batch.
11. **Tích hợp database constraints:** bảo vệ tính toàn vẹn ở tầng lưu trữ.
12. **Version hóa contract:** quản lý thay đổi requiredness, type, default và semantics.
13. **Kiểm thử:** boundary, Unicode, nested, cross-field, security và concurrency.
14. **Quan sát production:** theo dõi tỷ lệ lỗi theo code mà không log dữ liệu nhạy cảm.

## 44. Nguyên tắc thiết kế

- **Công bố contract rõ ràng:** client cần biết cấu trúc và miền giá trị được chấp nhận.
- **Phân biệt missing, null và default:** ba trạng thái này có semantics khác nhau.
- **Dùng kiểu miền phù hợp:** tiền tệ, ngày giờ và định danh không nên bị giản lược tùy tiện.
- **Định nghĩa biên inclusive/exclusive:** min/max cần có quy tắc rõ.
- **Tách format khỏi existence:** chuỗi đúng cú pháp chưa chắc tham chiếu đến tài nguyên thật.
- **Tách validation khỏi authorization:** hợp lệ không đồng nghĩa được phép sử dụng.
- **Đặt domain invariant đúng tầng:** kiểm tra trong transaction khi trạng thái có thể thay đổi đồng thời.
- **Chuẩn hóa có chủ đích:** không biến đổi dữ liệu nhạy cảm hoặc có ý nghĩa khoảng trắng âm thầm.
- **Kiểm soát coercion:** tránh chuyển đổi mơ hồ như chuỗi sang số hoặc thời gian thiếu timezone.
- **Giới hạn kích thước sớm:** bảo vệ parser, validator và downstream service.
- **Trả lỗi có cấu trúc:** code ổn định, path chính xác và message dễ hiểu.
- **Dùng database constraint làm hàng rào cuối:** API validation không loại bỏ race condition.
- **Version hóa thay đổi contract:** đặc biệt required field, enum, default và null semantics.
- **Tái sử dụng constraint nhưng giữ đúng ngữ cảnh:** schema chung không nên xóa khác biệt nghiệp vụ.
- **Test cả trường hợp biên và đồng thời:** dữ liệu hợp lệ tại thời điểm kiểm tra có thể không còn hợp lệ khi commit.
- **Không coi validation là cơ chế bảo mật duy nhất:** parameterized query, escaping và authorization vẫn cần thiết.

Ràng buộc đầu vào biến dữ liệu bên ngoài thành một contract có thể kiểm tra trước khi hệ thống sử dụng. Khi DSL mô tả rõ kiểu, presence, miền giá trị, cấu trúc lồng nhau, quan hệ giữa trường và quy tắc miền; khi pipeline phân biệt validation, authorization và conflict; đồng thời error model, resource limits, database constraints và kiểm thử được thiết kế nhất quán, API có thể từ chối dữ liệu sai sớm, giải thích được lý do và giữ cho dữ liệu nội bộ đáng tin cậy.
