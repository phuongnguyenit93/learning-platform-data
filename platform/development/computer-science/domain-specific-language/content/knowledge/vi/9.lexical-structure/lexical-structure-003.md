# Tên định danh

## 1. Khái niệm và vai trò trong DSL

**Tên định danh (*identifier*)** là tên dùng để nhận diện một thành phần có ý nghĩa trong ngôn ngữ, chẳng hạn biến, thuộc tính, hàm, kiểu dữ liệu, bảng, trường, quy tắc, workflow hoặc thực thể miền. Trong một ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*), tên định danh tạo cầu nối giữa cú pháp và khái niệm nghiệp vụ: người viết dùng tên để chỉ đúng đối tượng hoặc hành động mà hệ thống hiểu.

Ví dụ trong một DSL quản lý đơn hàng:

```text
rule "vip-discount" {
    when customer.tier == "GOLD"
    then order.discountPercent = 10
}
```

Trong ví dụ:

- `customer` và `order` là các tên định danh biểu thị đối tượng hoặc biến có sẵn trong ngữ cảnh.
- `tier` và `discountPercent` là tên thuộc tính.
- `rule`, `when` và `then` là từ khóa do ngôn ngữ định nghĩa, không phải tên định danh tự do trong vị trí này.
- `"vip-discount"` là một chuỗi ký tự dùng làm nhãn quy tắc. Nó không tự động là identifier chỉ vì được dùng để đặt tên một quy tắc.

Một DSL có thể dùng identifier cho nhiều loại thực thể. Quy tắc từ vựng quyết định chuỗi ký tự nào được xem là tên; phân tích cú pháp quyết định tên xuất hiện ở vị trí nào; phân tích ngữ nghĩa xác định tên đó tham chiếu đến đối tượng nào và có hợp lệ hay không.

Tên định danh vì vậy có ba lớp cần phân biệt:

1. **Hình thức từ vựng:** chuỗi ký tự có thỏa quy tắc tạo tên không?
2. **Vị trí cú pháp:** tên có xuất hiện ở vị trí mà grammar cho phép không?
3. **Ý nghĩa:** tên có được khai báo, có đúng phạm vi và đúng loại đối tượng không?

Một chuỗi có thể hợp lệ về từ vựng nhưng vẫn không hợp lệ về ngữ nghĩa. Ví dụ, `unknownCustomer` có thể là một identifier hợp lệ, nhưng nếu không có khai báo hoặc binding tương ứng thì semantic analyzer phải báo lỗi.

## 2. Identifier khác gì với keyword, literal và tên hiển thị?

Các thành phần từ vựng có thể trông giống nhau nhưng mang vai trò khác nhau.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Identifier | Tham chiếu đến ký hiệu hoặc thành phần được đặt tên | `customer`, `totalAmount`, `calculateTax` |
| Keyword | Từ dành riêng có ý nghĩa cú pháp cố định | `rule`, `when`, `then` |
| Literal | Giá trị được viết trực tiếp trong chương trình | `42`, `"GOLD"`, `true` |
| Comment | Văn bản chú thích bị bỏ qua hoặc giữ lại cho công cụ | `// apply only to active orders` |
| Display label | Nhãn cho người dùng đọc, có thể không dùng để phân giải ký hiệu | `"Khách hàng VIP"` |

Ví dụ:

```text
let customerName = "An";
let orderTotal = 250000;
```

`customerName` và `orderTotal` là identifier; `let` có thể là keyword tùy DSL; `"An"` và `250000` là literal.

Tên hiển thị có thể chứa dấu cách, dấu câu hoặc ngôn ngữ tự nhiên. Không nên mặc định rằng nhãn hiển thị là identifier. Một hệ thống có thể dùng identifier ổn định như `vip_customer` nhưng hiển thị nhãn `"Khách hàng thân thiết"`. Cách tách biệt này giúp đổi tên giao diện mà không làm hỏng tham chiếu trong tài liệu DSL.

## 3. Quy tắc từ vựng của identifier

### 3.1. Ký tự bắt đầu và ký tự tiếp theo

Một quy tắc thường gặp là tên phải bắt đầu bằng chữ cái hoặc dấu gạch dưới, các ký tự tiếp theo có thể gồm chữ cái, chữ số và dấu gạch dưới.

Ví dụ grammar ASCII đơn giản:

```text
IDENTIFIER = LETTER (LETTER | DIGIT | "_")*
LETTER     = "A".."Z" | "a".."z" | "_"
DIGIT      = "0".."9"
```

Theo quy tắc minh họa này:

| Chuỗi | Hợp lệ? | Giải thích |
|---|---|---|
| `customer` | Có | Bắt đầu bằng chữ cái |
| `_internal` | Có | Bắt đầu bằng dấu gạch dưới |
| `order2` | Có | Chữ số xuất hiện sau ký tự đầu |
| `customer_name` | Có | Dấu gạch dưới nằm bên trong |
| `2ndOrder` | Không | Bắt đầu bằng chữ số |
| `order-total` | Không | Dấu gạch nối chưa được cho phép |
| `customer name` | Không | Có dấu cách |
| `total.amount` | Không phải một identifier đơn | Có thể là biểu thức truy cập thuộc tính gồm nhiều phần |

Đây chỉ là một lựa chọn thiết kế. Một DSL có thể cho phép dấu gạch nối, ký tự Unicode hoặc các quy tắc khác. Điều quan trọng là grammar phải quy định rõ và lexer phải áp dụng thống nhất.

### 3.2. Quy tắc EBNF tổng quát

Có thể mô tả identifier bằng EBNF:

```text
Identifier ::= IdentifierStart IdentifierContinue*
IdentifierStart ::= Letter | "_"
IdentifierContinue ::= Letter | Digit | "_"
```

Nếu DSL hỗ trợ tên phân cấp dạng `customer.address.city`, đó thường là một cú pháp khác được xây dựng từ nhiều identifier:

```text
QualifiedName ::= Identifier ("." Identifier)*
```

Trong trường hợp này, `customer`, `address` và `city` là ba identifier riêng; dấu chấm là token phân cách. Parser có thể xây dựng một node truy cập thuộc tính hoặc một tên định danh đầy đủ tùy ngữ nghĩa DSL.

### 3.3. Phân biệt chữ hoa và chữ thường

DSL phải quyết định identifier có phân biệt chữ hoa và chữ thường (*case-sensitive*) hay không.

Nếu phân biệt:

```text
customer
Customer
CUSTOMER
```

là ba tên khác nhau.

Nếu không phân biệt, các cách viết trên có thể được xem là cùng một tên. Khi đó hệ thống cần quy định cách chuẩn hóa, ví dụ chuyển về chữ thường theo một quy tắc locale-independent trước khi tra cứu symbol table.

Phân biệt hoa thường có thể hữu ích với DSL dành cho lập trình viên vì phù hợp với nhiều ngôn ngữ chủ. Không phân biệt hoa thường có thể thuận tiện với DSL cấu hình do chuyên gia miền viết, nhưng dễ gây va chạm tên và làm khó việc hiển thị nguyên văn. Không nên thay đổi chính sách này tùy tiện sau khi đã có tài liệu DSL được lưu trữ.

### 3.4. Khoảng trắng và dấu phân cách

Thông thường, dấu cách không nằm trong identifier đơn. Parser dùng khoảng trắng để tách token:

```text
customer tier
```

có thể là hai identifier riêng, không phải một tên có dấu cách. Nếu DSL cần tên có khoảng trắng, có thể dùng *quoted identifier* hoặc một trường nhãn dạng string:

```text
field "Customer tier" {
    type = string
}
```

Cần quy định rõ chuỗi trong dấu ngoặc kép ở vị trí này là tên được trích dẫn hay chỉ là nhãn. Hai khái niệm không nên dùng lẫn lộn.

## 4. Tên định danh có trích dẫn (quoted identifiers)

Một số DSL cho phép tên chứa dấu cách, dấu gạch nối, ký tự đặc biệt hoặc trùng với keyword bằng cách đặt tên trong dấu phân cách đặc biệt.

Ví dụ cú pháp giả định:

```text
select [Order Total], [Customer Name]
from [Sales Report]
where [Order Status] == "PAID"
```

Trong ví dụ này, dấu ngoặc vuông xác định quoted identifier. Một DSL khác có thể dùng dấu ngoặc kép hoặc dấu backtick:

```text
select [order-total]
from [monthly sales]
```

Không có một quy ước chung cho mọi DSL. Nhóm thiết kế cần xác định:

- Ký tự mở và đóng tên được trích dẫn.
- Cách escape chính ký tự phân cách bên trong tên.
- Tên có phân biệt hoa thường không.
- Có chuẩn hóa Unicode hay không.
- Quoted identifier có thể dùng ở những vị trí nào.
- Quoted identifier có thể trùng keyword không.
- Có được dùng tên rỗng hoặc tên chỉ chứa khoảng trắng không.

Quoted identifier giúp biểu đạt tên theo cách người dùng mong muốn, nhưng làm grammar và thông báo lỗi phức tạp hơn. Chỉ nên bổ sung khi miền thực sự cần tên có ký tự ngoài tập identifier thông thường.

## 5. Keyword và tên định danh

### 5.1. Reserved keywords

*Reserved keyword* là từ được dành riêng cho cú pháp của DSL. Nếu `rule` là keyword, người dùng không thể khai báo một biến thông thường có tên `rule` ở vị trí mà lexer nhận diện keyword.

Ví dụ:

```text
rule "discount" {
    when order.total > 100000
    then discount.percent = 10
}
```

Các từ `rule`, `when` và `then` có vai trò cấu trúc. Việc dành riêng chúng giúp grammar dễ phân tích và giảm nhập nhằng.

### 5.2. Contextual keywords

Một số DSL chỉ xem một từ là keyword trong một ngữ cảnh nhất định. Ví dụ `from` có thể là keyword trong câu truy vấn, nhưng vẫn có thể là tên định danh trong một cấu trúc khác nếu grammar cho phép.

```text
query {
    from orders
}

variable from = "source"
```

Đây là ví dụ giả định cho contextual keyword. Cách thiết kế này giảm số từ bị dành riêng, nhưng parser phải hiểu ngữ cảnh chính xác hơn. Cần tránh tạo ra quá nhiều ngoại lệ khiến người viết không thể đoán từ nào được phép dùng làm tên.

### 5.3. Xử lý xung đột keyword

Có một số chiến lược:

1. **Dành riêng hoàn toàn:** keyword không được dùng làm identifier thông thường.
2. **Cho phép quoted identifier:** người dùng có thể viết tên trùng keyword trong dấu trích dẫn.
3. **Contextual keyword:** chỉ dành riêng từ trong một số vị trí cú pháp.
4. **Không dùng keyword phổ biến làm tên điều khiển:** chọn từ khóa đặc thù của miền để giảm xung đột.

Ví dụ nếu `order` là keyword, người dùng có thể cần viết tên đó trong dấu ngoặc vuông hoặc một dạng quoted identifier khác để khai báo biến. Quy tắc cụ thể phụ thuộc DSL.

## 6. Quy ước đặt tên trong DSL

Quy tắc từ vựng quyết định tên nào hợp lệ; quy ước đặt tên giúp tên hợp lệ dễ đọc và nhất quán.

### 6.1. Các phong cách phổ biến

| Phong cách | Ví dụ | Thường dùng cho |
|---|---|---|
| camelCase | `customerName`, `totalAmount` | Biến, thuộc tính, hàm trong nhiều API lập trình |
| PascalCase | `CustomerAccount`, `OrderPolicy` | Kiểu dữ liệu, entity, cấu trúc |
| snake_case | `customer_name`, `total_amount` | Tên trường, biến hoặc cấu hình |
| kebab-case | `customer-name`, `monthly-report` | Slug, tên cấu hình hoặc định danh được trích dẫn |
| UPPER_SNAKE_CASE | `MAX_RETRY`, `DEFAULT_LIMIT` | Hằng số hoặc tên cấu hình đặc biệt |

Đây là quy ước, không phải yêu cầu cú pháp bắt buộc. Một DSL nên chọn phong cách phù hợp với người dùng và dùng thống nhất trong tài liệu, ví dụ và công cụ.

### 6.2. Chọn tên có ý nghĩa miền

Tên nên mô tả khái niệm mà người dùng hiểu:

```text
customer
invoice
shippingAddress
taxRate
approvalStatus
```

Tránh những tên mơ hồ như `x1`, `tmp` hoặc `data2` trong các quy tắc nghiệp vụ dài hạn. Tên viết tắt có thể hữu ích khi phổ biến trong lĩnh vực, nhưng nên có quy ước và tài liệu.

### 6.3. Phân biệt tên miền và tên kỹ thuật

Một DSL dành cho nghiệp vụ nên ưu tiên ngôn ngữ miền thay vì buộc người dùng biết cấu trúc nội bộ của ứng dụng.

Ví dụ:

```text
when customer.isPreferred
then apply loyaltyBenefit
```

có thể dễ hiểu hơn một biểu thức dựa trên mã bảng, cột hoặc tên class của hệ thống lưu trữ. Lớp ánh xạ giữa identifier trong DSL và mô hình nội bộ giúp nhóm thay đổi triển khai mà không buộc người dùng sửa mọi tài liệu DSL.

### 6.4. Tránh tên quá giống nhau

Các tên như `userId`, `userID`, `userid` và `user_id` có thể gây nhầm lẫn, nhất là trong DSL không phân biệt hoa thường. Cần có quy tắc kiểm tra tên gần giống hoặc tên chỉ khác cách viết khi miền có nhiều ký hiệu.

## 7. Phạm vi và phân giải tên

Một identifier chỉ có ý nghĩa khi hệ thống xác định nó tham chiếu đến ký hiệu nào. Công việc này gọi là **phân giải tên (*name resolution*)**.

### 7.1. Symbol table

Semantic analyzer thường dùng symbol table để lưu thông tin về các ký hiệu đã khai báo: tên, loại, kiểu, phạm vi, vị trí khai báo và metadata liên quan.

Ví dụ:

```text
let taxRate = 0.08

rule "calculate-total" {
    let subtotal = order.subtotal
    let tax = subtotal * taxRate
    return subtotal + tax
}
```

Symbol table có thể ghi nhận:

| Tên | Loại ký hiệu | Phạm vi |
|---|---|---|
| `taxRate` | Biến hoặc hằng | Phạm vi module |
| `calculate-total` | Tên quy tắc | Danh sách quy tắc |
| `subtotal` | Biến cục bộ | Thân quy tắc |
| `tax` | Biến cục bộ | Thân quy tắc |
| `order` | Biến/context được cung cấp | Phạm vi thực thi |

Bảng trên chỉ minh họa. Cách khai báo và phạm vi thực tế phụ thuộc grammar và mô hình thực thi của DSL.

### 7.2. Scope

*Scope* (phạm vi) xác định nơi một tên có thể được nhìn thấy và sử dụng. DSL có thể có:

- Phạm vi toàn cục hoặc module.
- Phạm vi trong một rule hoặc workflow.
- Phạm vi cục bộ của block.
- Phạm vi tham số của hàm hoặc biểu thức lambda.
- Phạm vi namespace hoặc package.

Ví dụ:

```text
let currency = "VND"

rule "order-total" {
    let subtotal = order.subtotal
    let tax = subtotal * taxRate
    return subtotal + tax
}
```

`currency` có thể thuộc phạm vi module; `subtotal` và `tax` có thể chỉ tồn tại trong thân rule. Nếu người viết tham chiếu `tax` ở ngoài rule, semantic analyzer cần báo lỗi nếu DSL không có quy tắc đưa tên đó ra phạm vi bên ngoài.

### 7.3. Shadowing

*Shadowing* xảy ra khi một khai báo trong phạm vi bên trong có cùng tên với khai báo ở phạm vi bên ngoài. Ví dụ:

```text
let status = "NEW"

rule "check-order" {
    let status = order.status
    return status
}
```

Trong thân rule, `status` có thể tham chiếu đến biến cục bộ và che khuất biến ngoài. Một DSL có thể cho phép, cảnh báo hoặc cấm shadowing. Nếu cho phép, quy tắc phân giải phải xác định rõ ưu tiên phạm vi gần nhất.

Shadowing tiện lợi trong một số ngôn ngữ, nhưng có thể khiến người đọc khó biết tên đang tham chiếu đến đâu. Với DSL cấu hình hoặc nghiệp vụ, hạn chế shadowing thường giúp giảm nhầm lẫn.

### 7.4. Namespace và qualified name

Namespace nhóm các ký hiệu liên quan và tránh xung đột tên.

Ví dụ:

```text
sales.Order
inventory.Stock
billing.Invoice
```

Đây có thể là qualified name gồm namespace và tên thành phần. Dấu chấm thường là dấu phân cách, không nhất thiết là một phần của identifier đơn.

Nếu hai module đều khai báo `Status`, tên đầy đủ có thể là `sales.Status` và `shipping.Status`. DSL cần quy định cách import, alias và ưu tiên khi có nhiều tên trùng nhau.

### 7.5. Import và alias

Một DSL có thể hỗ trợ import để sử dụng ký hiệu từ module khác:

```text
import sales.Order as SalesOrder
import billing.Invoice

rule "invoice-check" {
    when SalesOrder.total > 0
    then Invoice.validate()
}
```

Ví dụ trên minh họa ý tưởng, không phải cú pháp của một DSL cụ thể. Khi có alias, symbol table cần lưu quan hệ giữa tên được dùng trong tài liệu và ký hiệu gốc. Lỗi import nên chỉ rõ module không tìm thấy, tên không được export hoặc alias bị trùng.

## 8. Unicode và tên định danh đa ngôn ngữ

### 8.1. Có nên cho phép Unicode?

Một DSL dành cho người dùng toàn cầu có thể cần identifier chứa ký tự Unicode:

```text
kháchHàng
địa_chỉ
café
商品
```

Cho phép Unicode giúp tên gần với ngôn ngữ người dùng, nhưng làm tăng yêu cầu về lexer, chuẩn hóa, hiển thị và bảo mật. Một lựa chọn khác là chỉ cho phép identifier ASCII nhưng hỗ trợ tên hiển thị đa ngôn ngữ qua string hoặc metadata.

Không có lựa chọn duy nhất phù hợp mọi DSL. Hãy cân nhắc đối tượng sử dụng, hệ thống tích hợp, công cụ editor và khả năng kiểm soát rủi ro.

### 8.2. Unicode normalization

Một số ký tự có thể được biểu diễn bằng nhiều chuỗi code point tương đương về mặt hiển thị. Ví dụ ký tự có dấu có thể được biểu diễn bằng ký tự dựng sẵn hoặc chữ cái kết hợp dấu.

Nếu DSL so sánh tên theo chuỗi code point thô, hai cách biểu diễn có thể bị xem là hai identifier khác nhau dù hiển thị gần như giống nhau. Chuẩn hóa Unicode, thường cân nhắc dạng NFC, giúp giảm loại sai khác này.

Chính sách cần được áp dụng nhất quán ở khai báo, tham chiếu, lưu trữ và phân giải tên. Không nên chuẩn hóa một phía nhưng giữ nguyên phía còn lại.

### 8.3. Ký tự gây nhầm lẫn

Một số ký tự thuộc các bảng chữ cái khác nhau có hình dạng gần giống nhau, ví dụ chữ Latin và chữ Cyrillic. Kẻ tấn công hoặc người dùng vô tình có thể tạo ra hai identifier trông giống nhau nhưng thực chất khác nhau.

Với DSL có quyền thực thi hành động, cần cân nhắc:

- Phát hiện các ký tự confusable trong tên quan trọng.
- Cảnh báo tên gần giống nhau trong cùng phạm vi.
- Hạn chế trộn nhiều hệ chữ trong một identifier nếu không cần.
- Hiển thị code point hoặc cảnh báo trong công cụ quản trị khi cần điều tra.
- Không bỏ qua các ký tự điều khiển hướng văn bản không phù hợp trong identifier.

### 8.4. Quy tắc Unicode rõ ràng

Nếu hỗ trợ Unicode, nên dựa trên các thuộc tính ký tự được chuẩn hóa như `XID_Start` và `XID_Continue` thay vì tự đoán phạm vi chữ cái bằng một dải mã. Cần quy định riêng cách xử lý dấu kết hợp, ký tự nối và chuẩn hóa.

Tài liệu DSL phải nêu rõ hỗ trợ Unicode đến mức nào và phiên bản dữ liệu Unicode được sử dụng nếu hành vi phụ thuộc phiên bản đó.

## 9. Lexer nhận diện identifier như thế nào?

Lexer (*bộ phân tích từ vựng*) đọc chuỗi nguồn và tạo token. Một lexer thường nhận diện identifier dựa trên quy tắc bắt đầu và tiếp tục, sau đó kiểm tra xem từ vừa đọc có thuộc danh sách keyword hay không.

Ví dụ quy trình:

```text
Nguồn: customer.tier == "GOLD"

Token:
IDENTIFIER("customer")
DOT(".")
IDENTIFIER("tier")
EQUAL_EQUAL("==")
STRING("GOLD")
```

Một lexer đơn giản có thể thực hiện:

1. Đọc ký tự đầu tiên.
2. Nếu ký tự hợp lệ để bắt đầu identifier, tiếp tục đọc các ký tự hợp lệ tiếp theo.
3. Thu được chuỗi đầy đủ.
4. Tra cứu chuỗi trong bảng keyword.
5. Nếu là keyword, phát token keyword; nếu không, phát token IDENTIFIER.
6. Ghi vị trí nguồn để parser và diagnostics sử dụng.

Quy tắc *longest match* (khớp dài nhất) thường được áp dụng để lexer lấy chuỗi token dài nhất hợp lệ. Ví dụ `customerName` phải được nhận diện là một identifier, không bị tách thành `customer` và `Name` chỉ vì cả hai phần đều có thể là tên.

### 9.1. Ví dụ grammar lexer

Grammar lexer minh họa cho identifier ASCII:

```antlr
IDENTIFIER
    : [a-zA-Z_] [a-zA-Z_0-9]*
    ;

INTEGER
    : [0-9]+
    ;

WS
    : [ \t\r\n]+ -> skip
    ;
```

Nếu có keyword, cần đặt quy tắc keyword và identifier sao cho kết quả token đúng theo công cụ parser đang sử dụng. Nhiều lexer generator áp dụng thứ tự rule và độ dài khớp theo quy tắc riêng; cần đọc tài liệu công cụ và kiểm thử các trường hợp như `rule`, `ruleName` và `Rule`.

Ví dụ, nếu `rule` là keyword, lexer không được vô tình nhận `ruleName` thành keyword `rule` cộng với identifier `Name`. Khớp dài nhất thường giúp xử lý đúng trường hợp này.

### 9.2. Tách lexical validation khỏi semantic validation

Lexer kiểm tra hình thức tên, nhưng không nên gánh mọi quy tắc nghiệp vụ. Ví dụ:

- `customer_1` có thể hợp lệ về từ vựng.
- `unknownCustomer` có thể hợp lệ về từ vựng nhưng chưa được khai báo.
- `order.total` có thể là cú pháp truy cập thuộc tính hợp lệ nhưng kiểu của `total` có thể không cho phép so sánh với chuỗi.
- `deleteAllData` có thể là một tên hàm hợp lệ về từ vựng nhưng không được phép gọi trong sandbox.

Phân chia trách nhiệm rõ ràng giúp thông báo lỗi chính xác và giữ lexer đơn giản.

## 10. Identifier trong AST và semantic analysis

Parser thường tạo node riêng cho identifier thay vì chỉ lưu chuỗi văn bản rời rạc.

Ví dụ cấu trúc AST khái quát:

```text
PropertyAccess
├── Identifier("customer")
└── Identifier("tier")
```

Semantic analyzer sau đó giải quyết tên:

1. Tìm `customer` trong phạm vi hiện tại hoặc context được cấp.
2. Xác định kiểu của `customer`.
3. Kiểm tra kiểu có thuộc tính `tier` hay không.
4. Xác định kiểu và quyền truy cập của thuộc tính đó.
5. Gắn liên kết từ node AST đến symbol đã tìm thấy.

Sau khi resolve, node có thể lưu symbol ID hoặc tham chiếu đến symbol metadata thay vì chỉ dựa vào tên chuỗi. Cách này hữu ích khi có rename, go to definition, diagnostics và code completion.

### 10.1. Lỗi tên chưa khai báo

Ví dụ:

```text
rule "check" {
    when customer.unknownField == "X"
    then allow()
}
```

Nếu kiểu Customer không có thuộc tính `unknownField`, semantic analyzer nên báo lỗi tại đúng tên đó và có thể gợi ý các thuộc tính gần giống như `customer.tier` hoặc `customer.status`.

### 10.2. Lỗi tên trùng

Nếu DSL không cho phép khai báo trùng trong cùng scope:

```text
let amount = 100
let amount = 200
```

thì khai báo thứ hai cần được báo lỗi. Diagnostic nên chỉ ra vị trí khai báo mới và có thể dẫn đến vị trí khai báo cũ.

### 10.3. Phân giải overload

Nếu một DSL cho phép nhiều hàm cùng tên nhưng khác tham số, semantic analyzer phải chọn đúng hàm dựa trên số lượng và kiểu đối số. Nếu không có ứng viên phù hợp hoặc có nhiều ứng viên ngang nhau, cần báo lỗi mơ hồ thay vì tự chọn một cách không dự đoán được.

## 11. Đổi tên và tính ổn định của identifier

Tên có thể xuất hiện ở nhiều vị trí. Khi đổi tên một ký hiệu, công cụ nên biết những chỗ nào thực sự tham chiếu đến cùng symbol.

Ví dụ:

```text
let taxRate = 0.08

rule "invoice-total" {
    let tax = invoice.subtotal * taxRate
    return invoice.subtotal + tax
}
```

Nếu người dùng đổi tên `taxRate`, công cụ rename nên cập nhật đúng khai báo và tham chiếu, không thay thế mọi chuỗi ký tự có nội dung giống nhau trong comment hoặc string literal.

Để làm được điều đó, language server hoặc IDE cần symbol resolution và thông tin vị trí trong AST. Thay thế chuỗi bằng tìm kiếm văn bản đơn giản có thể sửa nhầm literal, comment hoặc một identifier khác có tên gần giống.

### 11.1. Tên kỹ thuật và định danh ổn định

Trong một số hệ thống, tên định danh có thể được đổi theo thời gian. Nếu tài liệu DSL được lưu lâu dài hoặc được tham chiếu từ hệ thống ngoài, nên cân nhắc phân biệt:

- **Tên hiển thị:** người dùng có thể đổi để dễ đọc.
- **Identifier trong DSL:** tên được dùng trong mã nguồn và có quy tắc tương thích.
- **ID ổn định:** khóa nội bộ không phụ thuộc tên, dùng để liên kết dữ liệu hoặc giữ tham chiếu qua lần đổi tên.

Không phải DSL nào cũng cần ba lớp. Nhưng với hệ thống có nhiều tài liệu, nhiều người dùng và lịch sử dài, tách ID ổn định khỏi tên hiển thị có thể giảm chi phí migration.

### 11.2. Thay đổi quy tắc identifier

Khi DSL đã có người dùng, thay đổi quy tắc tên có thể làm tài liệu cũ không phân tích được. Ví dụ, phiên bản mới cho phép dấu gạch nối hoặc Unicode nhưng phiên bản cũ không cho phép.

Cần có chiến lược versioning:

- Giữ parser tương thích với phiên bản cũ trong thời gian chuyển tiếp.
- Cung cấp công cụ tìm và sửa identifier không còn hợp lệ.
- Cảnh báo trước khi bỏ hỗ trợ cú pháp cũ.
- Quy định cách xử lý tên trùng sau khi chuẩn hóa hoặc chuyển đổi chữ hoa thường.
- Có test fixtures cho tài liệu DSL của các phiên bản đã phát hành.

## 12. Bảo mật và độ tin cậy của tên định danh

Identifier là đầu vào của parser và đôi khi được chuyển tiếp đến cơ sở dữ liệu, hệ thống tệp, API hoặc runtime. Vì vậy, cần xem xét cả độ an toàn.

### 12.1. Không ghép identifier vào câu lệnh bên ngoài một cách tùy tiện

Nếu DSL cho phép người dùng chọn tên bảng hoặc trường rồi ứng dụng chuyển thành SQL, không nên nối trực tiếp chuỗi tên vào câu lệnh mà không kiểm tra. Tham số truy vấn thường bảo vệ giá trị dữ liệu, nhưng tên bảng/cột thường cần một bước xác thực riêng vì không phải mọi vị trí định danh đều hỗ trợ bind parameter.

Nên ánh xạ identifier DSL sang metadata hoặc allowlist đã được kiểm soát. Nếu cần quote tên trong SQL, phải dùng cơ chế quoting phù hợp với hệ quản trị dữ liệu và vẫn xác minh tên được phép.

### 12.2. Ngăn truy cập ký hiệu không được phép

Một identifier có thể trỏ đến hàm hoặc tài nguyên nhạy cảm. Semantic analyzer và runtime cần kiểm tra quyền, không chỉ kiểm tra tên có tồn tại.

Ví dụ, DSL cho phép `readReport` nhưng không cho phép `deleteAccount` đối với vai trò chỉ đọc. Quyền nên được gắn với capability hoặc policy rõ ràng, và phải được kiểm tra ở runtime khi cần, bởi quyền có thể thay đổi sau lúc validate.

### 12.3. Giới hạn độ dài và số lượng tên

Tên quá dài, quá nhiều khai báo hoặc namespace lồng quá sâu có thể làm tăng chi phí phân tích và lưu trữ. DSL nên đặt giới hạn phù hợp cho độ dài identifier, số lượng ký hiệu, độ sâu namespace và kích thước tài liệu.

Giới hạn cần đủ rộng cho nhu cầu hợp lệ nhưng ngăn đầu vào bất thường gây tiêu thụ tài nguyên không kiểm soát.

### 12.4. Unicode spoofing và ký tự điều khiển

Với identifier Unicode, cần cảnh giác ký tự đồng hình, ký tự điều khiển hướng văn bản và các ký tự vô hình. Chúng có thể khiến mã hiển thị khác với thứ tự ký tự thực hoặc khiến hai tên trông giống nhau nhưng resolve đến hai symbol khác nhau.

Có thể cảnh báo, từ chối một số ký tự điều khiển hoặc cung cấp chế độ hiển thị an toàn trong editor và công cụ review.

## 13. Thông báo lỗi và trải nghiệm người viết DSL

Thông báo lỗi về identifier nên chỉ rõ:

- Tên nào gây lỗi.
- Lỗi thuộc loại nào: không hợp lệ về từ vựng, chưa khai báo, trùng tên, sai scope, sai kiểu hay không đủ quyền.
- Vị trí trong tài liệu.
- Khai báo liên quan nếu có.
- Gợi ý sửa khi có thể xác định một cách đáng tin cậy.

Ví dụ:

```text
rules.dsl:12:18: error E102: Unknown property 'custmer.tier'
Did you mean 'customer.tier'?
```

Gợi ý chỉ nên đưa ra khi có ứng viên đủ gần và không mơ hồ. Không nên tự động sửa nếu có nhiều lựa chọn có khả năng đúng.

Với editor, diagnostics cần có range chính xác. Nếu lexer và parser giữ source span, IDE có thể gạch chân đúng identifier và hiển thị thông tin khi người dùng di chuột.

## 14. Kiểm thử quy tắc identifier

Một DSL nên có bộ kiểm thử riêng cho lexer, parser và semantic analyzer.

### 14.1. Kiểm thử từ vựng

| Nhóm | Ví dụ đầu vào | Kết quả kỳ vọng |
|---|---|---|
| Chữ thường | `customer` | Identifier hợp lệ |
| Chữ hoa | `Customer` | Theo chính sách case của DSL |
| Dấu gạch dưới | `_private` | Theo grammar |
| Chữ số ở cuối | `field2` | Hợp lệ với grammar thông thường |
| Chữ số ở đầu | `2field` | Không hợp lệ với grammar ASCII minh họa |
| Ký tự phân cách | `customer-name` | Hợp lệ nếu grammar cho phép hoặc quoted |
| Khoảng trắng | `customer name` | Hai token hoặc lỗi tùy vị trí |
| Keyword | `rule` | Keyword hoặc identifier theo chính sách |
| Unicode | `kháchHàng` | Theo chính sách Unicode |
| Tên trích dẫn | `"Customer tier"` | Theo grammar quoted identifier |

### 14.2. Kiểm thử phân giải tên

Cần có test cho:

- Tên đã khai báo và chưa khai báo.
- Tên trong scope lồng nhau.
- Shadowing được phép hoặc bị cấm.
- Namespace, import và alias.
- Tên trùng sau khi chuẩn hóa Unicode hoặc case folding.
- Overload có một ứng viên, không có ứng viên hoặc nhiều ứng viên mơ hồ.
- Quyền truy cập ký hiệu theo vai trò.

### 14.3. Property-based và fuzz testing

Có thể sinh chuỗi identifier ngẫu nhiên theo grammar để kiểm tra lexer không crash, không lặp vô hạn và phân loại token nhất quán. Với quoted identifier, cần thử ký tự escape, dấu đóng bị thiếu, Unicode kết hợp và đầu vào rất dài.

Một thuộc tính hữu ích là nếu lexer chấp nhận một identifier, serialize rồi parse lại theo chính sách chuẩn hóa phải tạo ra cùng một symbol name theo quy tắc của DSL.

## 15. Quy trình thiết kế tên định danh cho một DSL

Có thể thực hiện theo các bước sau:

1. **Xác định đối tượng được đặt tên:** biến, thuộc tính, hàm, rule, kiểu, namespace hay tài nguyên.
2. **Chọn tập ký tự:** ASCII hay Unicode; quy định ký tự đầu và ký tự tiếp theo.
3. **Quy định case:** phân biệt hoa thường hay chuẩn hóa khi phân giải.
4. **Định nghĩa keyword:** reserved hay contextual; quyết định có hỗ trợ quoted identifier hay không.
5. **Xác định cấu trúc tên:** tên đơn, qualified name, namespace, import và alias.
6. **Thiết kế scope:** phạm vi khai báo, shadowing, lifetime và quy tắc tra cứu.
7. **Định nghĩa semantic resolution:** kiểm tra tồn tại, kiểu, overload và quyền truy cập.
8. **Chuẩn hóa và bảo mật:** xử lý Unicode, ký tự đồng hình, giới hạn độ dài và tên dùng khi sinh câu lệnh bên ngoài.
9. **Tích hợp công cụ:** lưu source span, symbol metadata để hỗ trợ completion, rename, hover và go to definition.
10. **Kiểm thử và versioning:** kiểm tra tài liệu hợp lệ/không hợp lệ và duy trì tương thích khi thay đổi quy tắc.

Quy tắc tên nên được quyết định sớm vì chúng ảnh hưởng trực tiếp đến grammar, tài liệu, API, editor và các tệp DSL đã lưu.

## 16. Kết luận

Tên định danh là thành phần từ vựng dùng để đặt tên và tham chiếu đến các ký hiệu trong DSL. Một thiết kế identifier tốt cần quy định rõ ký tự hợp lệ, chữ hoa/thường, keyword, quoted identifier, Unicode, namespace và phạm vi. Lexer nhận diện hình thức tên; parser xác định vị trí cú pháp; semantic analyzer phân giải tên và kiểm tra kiểu, khai báo cùng quyền truy cập.

Tên định danh cũng là một phần của trải nghiệm người dùng DSL. Tên dễ hiểu, nhất quán và gắn với khái niệm miền giúp tài liệu dễ đọc và dễ bảo trì. Khi DSL phát triển lâu dài, cần quan tâm đến đổi tên, tương thích phiên bản, chuẩn hóa Unicode và bảo mật để các tham chiếu luôn rõ ràng và đáng tin cậy.

