# Từ khóa

Trong ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), từ khóa là những từ hoặc chuỗi ký tự có ý nghĩa đặc biệt được ngôn ngữ quy định trước. Chúng thường dùng để biểu thị cấu trúc, thao tác, điều kiện hoặc khái niệm cốt lõi của miền. Ví dụ, trong một DSL truy vấn giả định, các từ khóa như `select`, `from` và `where` có thể xác định phần dữ liệu cần lấy, nguồn dữ liệu và điều kiện lọc.

Từ khóa là một phần quan trọng của **từ vựng (lexicon)** và **phân tích từ vựng (lexical analysis)**. Chúng giúp người viết diễn đạt chương trình theo một quy ước thống nhất, đồng thời giúp bộ phân tích nhận diện cấu trúc của câu lệnh.

Tuy nhiên, từ khóa cần được thiết kế cẩn thận. Nếu có quá nhiều từ khóa, người dùng phải ghi nhớ nhiều quy tắc và dễ gặp xung đột tên. Nếu từ khóa quá ít hoặc ý nghĩa không rõ, cú pháp có thể trở nên khó đọc và khó phân tích. Một DSL tốt chọn tập từ khóa vừa đủ, dùng nhất quán và gắn với ngữ nghĩa rõ ràng của miền.

## 1. Từ khóa là gì?

Từ khóa (keyword) là một token có dạng từ hoặc ký hiệu mà ngôn ngữ dành riêng cho một mục đích cú pháp hay ngữ nghĩa. Khi bộ phân tích gặp từ khóa trong vị trí phù hợp, nó hiểu từ đó theo vai trò đã định nghĩa.

Ví dụ, một DSL mô tả quy trình xử lý đơn hàng có thể dùng cú pháp giả định:

~~~text
workflow processOrder {
  step validateOrder
  step reserveInventory
  step chargePayment
}
~~~

Trong ví dụ này:

- `workflow` mở đầu một khai báo quy trình.
- `step` giới thiệu một bước.
- `processOrder` là tên quy trình do người viết đặt.
- `validateOrder`, `reserveInventory` và `chargePayment` là tên bước.

`workflow` và `step` là từ khóa vì ngôn ngữ quy định sẵn ý nghĩa của chúng. Các tên còn lại là định danh (identifier), được người viết lựa chọn để đặt tên cho thành phần trong mô hình.

Từ khóa có thể gồm một từ như `entity`, `contains`, `where` hoặc một chuỗi ký hiệu như `->`, tùy thiết kế ngôn ngữ. Trong nhiều DSL, các ký hiệu như dấu ngoặc, dấu phẩy và toán tử cũng là token đặc biệt, nhưng không phải tất cả đều được gọi là từ khóa theo nghĩa hẹp.

### 1.1. Từ khóa và định danh

Từ khóa và định danh có thể trông giống nhau vì cả hai thường được viết bằng chữ cái. Khác biệt nằm ở vai trò của chúng trong ngôn ngữ.

| Đặc điểm | Từ khóa | Định danh |
| --- | --- | --- |
| Nguồn gốc | Được ngôn ngữ quy định trước | Do người viết đặt theo quy tắc đặt tên |
| Ý nghĩa | Có ý nghĩa cố định trong cú pháp hoặc ngữ nghĩa | Chỉ một thực thể, biến, kiểu, thuộc tính hoặc thành phần được khai báo |
| Khả năng thay đổi tên | Thường không thể đổi tùy ý | Có thể đổi tên nếu cập nhật các tham chiếu |
| Phạm vi | Thường áp dụng trên toàn ngôn ngữ hoặc trong một ngữ cảnh cú pháp | Có thể phụ thuộc phạm vi, mô-đun hoặc không gian tên |
| Ví dụ | `entity`, `contains`, `when` | `Customer`, `Order`, `customerId` |

Ví dụ:

~~~text
entity Customer {
  field customerId: Integer
  field name: String
}
~~~

Trong cú pháp giả định này, `entity` và `field` là từ khóa. `Customer`, `customerId`, `Integer` và `name` là các định danh hoặc tên kiểu được khai báo trong mô hình. Tùy DSL, một số tên kiểu dựng sẵn có thể được xem là tên đặc biệt hoặc từ khóa; điều đó phải được quy định trong đặc tả.

Một quy tắc hữu ích là không nhầm “tên thường xuất hiện trong ví dụ” với “từ khóa”. Chỉ những từ mà ngôn ngữ dành riêng mới là từ khóa. Tên miền như Customer hay Order có thể xuất hiện rất thường xuyên nhưng vẫn là định danh.

### 1.2. Từ khóa và tên dựng sẵn

Một DSL có thể cung cấp sẵn tên hàm, kiểu dữ liệu hoặc hằng số như `String`, `Integer`, `sum`, `count`, `true`, `false` và `null`. Những tên này không nhất thiết đều là từ khóa.

Ví dụ, `sum(total)` có thể là lời gọi hàm dựng sẵn. Trong trường hợp đó, `sum` được tra cứu như một tên hàm trong môi trường biểu tượng. Ngược lại, nếu grammar quy định `sum` là thành phần cú pháp đặc biệt chỉ xuất hiện sau `calculate`, nó có thể được xử lý như từ khóa.

Việc phân biệt có ích khi thiết kế khả năng mở rộng. Tên hàm dựng sẵn có thể được thay thế hoặc mở rộng qua thư viện; từ khóa thường là một phần của grammar và khó thay đổi hơn vì ảnh hưởng đến cách phân tích chương trình.

## 2. Vai trò của từ khóa trong phân tích từ vựng

Trước khi parser xây dựng cấu trúc chương trình, văn bản DSL thường được chuyển thành một chuỗi token. Bộ phân tích từ vựng (lexer hoặc scanner) đọc các ký tự và nhận diện những đơn vị có ý nghĩa như từ khóa, định danh, số, chuỗi, toán tử và dấu phân cách.

Ví dụ, với câu lệnh:

~~~text
select customerId from Customer where active == true
~~~

Lexer có thể tạo ra chuỗi token khái quát:

| Văn bản | Loại token |
| --- | --- |
| `select` | Từ khóa SELECT |
| `customerId` | Định danh |
| `from` | Từ khóa FROM |
| `Customer` | Định danh |
| `where` | Từ khóa WHERE |
| `active` | Định danh |
| `==` | Toán tử so sánh |
| `true` | Literal boolean hoặc từ khóa literal |

Parser nhận chuỗi token và kiểm tra chúng có tạo thành cấu trúc hợp lệ theo grammar hay không. Sau đó, bước phân tích ngữ nghĩa có thể xác định `customerId` có phải thuộc tính của Customer hay không, `active` có kiểu boolean hay không và phép so sánh có hợp lệ hay không.

Luồng xử lý đơn giản:

~~~text
Văn bản DSL
    |
    v
Lexer / Scanner
    |
    v
Chuỗi token
    |
    v
Parser
    |
    v
Cây cú pháp / AST
    |
    v
Kiểm tra ngữ nghĩa
    |
    v
Mô hình hoặc chương trình có thể thực thi
~~~

### 2.1. Nhận diện từ khóa

Một cách phổ biến là lexer đọc một chuỗi ký tự theo quy tắc định danh trước, sau đó tra cứu chuỗi đó trong tập từ khóa.

Ví dụ, nếu lexer đọc được chuỗi `workflow`:

- Nếu `workflow` nằm trong bảng từ khóa, phát ra token WORKFLOW.
- Nếu không, phát ra token IDENTIFIER với giá trị `workflow`.

Cách làm này giúp lexer nhận diện từ khóa mà không cần viết một quy tắc ký tự riêng cho từng từ. Parser làm việc với loại token, còn thông tin tên có thể được giữ lại để báo lỗi hoặc xây dựng AST.

Một cách khác là grammar cho phép từ khóa xuất hiện trong các quy tắc cụ thể và parser xử lý trực tiếp. Tuy nhiên, với DSL có nhiều từ khóa, việc phân loại token rõ ràng thường giúp đặc tả và thông báo lỗi dễ hiểu hơn.

### 2.2. Quy tắc khớp dài nhất

Nếu một DSL có các toán tử hoặc từ khóa có tiền tố giống nhau, lexer thường cần áp dụng quy tắc khớp dài nhất (maximal munch): chọn token hợp lệ dài nhất tại vị trí hiện tại.

Ví dụ, nếu có các toán tử `=`, `==` và `=>`, chuỗi `==` cần được nhận diện thành một token so sánh bằng, không phải hai token `=`. Tương tự, nếu ngôn ngữ có `end` và `endIf`, lexer cần xác định ranh giới token theo quy tắc định danh và grammar, tránh cắt chuỗi một cách tùy tiện.

Đối với từ khóa dạng chữ, việc nhận diện thường dựa trên ranh giới định danh. Nếu `if` là từ khóa thì `ifEnabled` vẫn nên được nhận diện là một định danh duy nhất, không phải token IF theo sau bởi IDENTIFIER `Enabled`.

### 2.3. Từ khóa không tự bảo đảm câu lệnh hợp lệ

Lexer chỉ xác định được loại token. Một câu lệnh có thể chứa các từ khóa đúng nhưng vẫn sai cú pháp hoặc sai ngữ nghĩa.

Ví dụ:

~~~text
select from where
~~~

Các từ `select`, `from` và `where` đều có thể là từ khóa hợp lệ, nhưng câu lệnh thiếu định danh và điều kiện cần thiết. Parser phải báo lỗi cú pháp.

Một ví dụ khác:

~~~text
select unknownField from Customer
~~~

Câu lệnh có thể đúng grammar, nhưng `unknownField` không tồn tại trong mô hình Customer. Đây là lỗi ngữ nghĩa hoặc lỗi kiểm tra tham chiếu, không phải lỗi nhận diện từ khóa.

## 3. Các loại từ khóa

Không phải DSL nào cũng phân loại từ khóa theo cùng một cách. Một số phân biệt từ khóa dành riêng, từ khóa theo ngữ cảnh và literal. Các nhóm này giúp kiểm soát khả năng đặt tên và mở rộng cú pháp.

### 3.1. Từ khóa dành riêng (reserved keywords)

Từ khóa dành riêng là từ không được phép dùng làm định danh thông thường ở bất kỳ vị trí nào mà grammar cho phép định danh.

Ví dụ, nếu `entity` là từ khóa dành riêng, đoạn sau không hợp lệ:

~~~text
entity entity {
  field id: Integer
}
~~~

Tên thực thể thứ hai trùng với từ khóa. Người viết cần chọn tên khác, chẳng hạn `EntityRecord`.

Ưu điểm của từ khóa dành riêng:

- Lexer và parser dễ nhận diện.
- Grammar thường rõ ràng và ít mơ hồ.
- Người đọc dễ phân biệt cấu trúc với tên do người dùng đặt.

Nhược điểm:

- Giảm không gian đặt tên.
- Một từ có thể trở thành từ khóa mới trong phiên bản sau và làm hỏng định danh cũ.
- Người dùng có thể phải đổi tên khái niệm miền vốn đã quen thuộc.

Ví dụ, nếu DSL ban đầu cho phép khai báo một entity có tên `Order` và sau đó bổ sung `order` thành từ khóa, cần xem xét chính sách phân biệt hoa thường và tương thích với mô hình cũ.

### 3.2. Từ khóa theo ngữ cảnh (contextual keywords)

Từ khóa theo ngữ cảnh chỉ được xem là từ khóa trong một vị trí hoặc cấu trúc cụ thể. Ở vị trí khác, cùng chuỗi ký tự có thể được dùng làm định danh.

Ví dụ, trong DSL giả định:

~~~text
entity Order {
  field status: String
}

query orders {
  where status == "PAID"
}
~~~

`where` có thể là từ khóa khi xuất hiện trong cấu trúc query, nhưng có thể được cho phép làm tên thuộc tính hoặc tên định danh trong ngữ cảnh khác nếu grammar quy định rõ.

Từ khóa theo ngữ cảnh giúp giảm số tên bị dành riêng và hỗ trợ mở rộng DSL mà ít ảnh hưởng đến định danh hiện có. Tuy nhiên, parser phức tạp hơn vì ý nghĩa token phụ thuộc vị trí.

Không nên biến mọi từ khóa thành contextual một cách tùy tiện. Nếu quá nhiều từ có thể vừa là từ khóa vừa là định danh, người đọc khó đoán cách phân tích và thông báo lỗi có thể khó giải thích.

### 3.3. Từ khóa literal

Một số giá trị đặc biệt như boolean hoặc giá trị rỗng thường được biểu diễn bằng literal:

~~~text
active = true
deleted = false
description = null
~~~

`true`, `false` và `null` có thể được lexer phát ra như token literal riêng, hoặc được xem là từ khóa đặc biệt trong grammar. Dù phân loại kỹ thuật nào được chọn, ngôn ngữ cần quy định rõ:

- Có phân biệt chữ hoa và chữ thường không?
- Literal có thể dùng làm định danh không?
- Giá trị rỗng có khác với trường không được khai báo không?
- Literal được chuyển thành kiểu dữ liệu nào?

Ví dụ, `null` thường biểu thị không có giá trị, trong khi việc bỏ qua một trường trong cấu hình có thể mang nghĩa “dùng mặc định”. Hai trường hợp này không nên bị đồng nhất nếu ngữ nghĩa của DSL phân biệt chúng.

### 3.4. Từ khóa cấu trúc và từ khóa miền

Có thể phân loại từ khóa theo vai trò thiết kế:

- **Từ khóa cấu trúc:** định nghĩa khối, khai báo, phạm vi hoặc luồng điều khiển, chẳng hạn `entity`, `workflow`, `if`, `else`, `end`.
- **Từ khóa thao tác:** chỉ định hành động, chẳng hạn `create`, `update`, `delete`, `select`.
- **Từ khóa quan hệ:** mô tả liên kết hoặc phụ thuộc, chẳng hạn `hasMany`, `belongsTo`, `dependsOn`.
- **Từ khóa ràng buộc:** mô tả điều kiện, chẳng hạn `required`, `unique`, `when`, `assert`.
- **Từ khóa literal:** biểu diễn giá trị đặc biệt như `true`, `false` và `null`.

Đây là cách nhóm theo mục đích để thiết kế và tài liệu hóa, không phải hệ thống phân loại bắt buộc của mọi compiler.

## 4. Từ khóa trong grammar của DSL

Từ khóa là một phần của grammar. Grammar quy định cách các token được kết hợp thành câu lệnh, khai báo hoặc biểu thức.

Ví dụ, grammar đơn giản cho khai báo entity có thể viết ở dạng EBNF:

~~~text
EntityDeclaration = "entity", Identifier, "{",
                    { FieldDeclaration },
                    "}" ;

FieldDeclaration  = "field", Identifier, ":", TypeName ;
~~~

Theo grammar này:

- `entity` phải xuất hiện ở đầu một khai báo entity.
- Sau nó là một Identifier.
- Dấu ngoặc nhọn mở và đóng phạm vi khai báo.
- Bên trong có thể có không hoặc nhiều FieldDeclaration.
- Mỗi FieldDeclaration bắt đầu bằng `field`, sau đó là tên và kiểu.

Một khai báo hợp lệ:

~~~text
entity Customer {
  field id: Integer
  field name: String
}
~~~

Một khai báo không hợp lệ:

~~~text
entity {
  field id Integer
}
~~~

Ví dụ thứ hai thiếu tên entity và dấu hai chấm giữa tên trường với kiểu. Từ khóa `entity` và `field` vẫn được nhận diện, nhưng chuỗi token không thỏa mãn grammar.

### 4.1. Từ khóa quyết định cấu trúc

Các từ khóa như `entity`, `field`, `relation` và `constraint` có thể giúp parser xác định loại khai báo đang được đọc.

~~~text
entity Customer {
  field id: Integer
}

relation places {
  from Customer
  to Order
}

constraint CustomerMustHaveName {
  require Customer.name != ""
}
~~~

Từ khóa mở đầu mỗi khối giúp người đọc nhanh chóng hiểu mục đích của đoạn DSL. Khi thiết kế, nên chọn từ ngữ nhất quán và tránh dùng cùng một từ khóa cho nhiều cấu trúc không liên quan.

### 4.2. Từ khóa trong biểu thức

Một DSL có thể có từ khóa cho toán tử logic hoặc điều kiện:

~~~text
query activeCustomers {
  from Customer
  where active == true and country == "VN"
}
~~~

Trong ví dụ, `where` giới thiệu điều kiện lọc; `and` kết hợp hai điều kiện. Nếu DSL hỗ trợ `or` và `not`, cần quy định độ ưu tiên và tính kết hợp của chúng.

Ví dụ, biểu thức:

~~~text
where active == true or country == "VN" and verified == true
~~~

có thể được hiểu theo hai cách nếu không có quy tắc ưu tiên rõ ràng. Một grammar thông thường quy định `and` có độ ưu tiên cao hơn `or`, hoặc yêu cầu dùng ngoặc để tránh mơ hồ:

~~~text
where (active == true or country == "VN")
  and verified == true
~~~

Từ khóa logic không chỉ là tên dễ đọc; chúng cần có ngữ nghĩa chính xác trong biểu thức.

## 5. Quy tắc đặt tên và phân biệt chữ hoa, chữ thường

DSL phải quy định cách nhận diện từ khóa và định danh để người viết không gặp kết quả bất ngờ.

### 5.1. Có phân biệt hoa thường không?

Một số ngôn ngữ phân biệt chữ hoa và chữ thường (case-sensitive); một số khác không phân biệt (case-insensitive).

Nếu DSL phân biệt hoa thường, `entity` và `Entity` là hai chuỗi khác nhau. Khi đó, nếu chỉ `entity` là từ khóa, `Entity` có thể được xem là định danh.

Nếu DSL không phân biệt hoa thường, `entity`, `Entity` và `ENTITY` có thể được xem là cùng một từ khóa. Lexer cần chuẩn hóa cách so sánh, nhưng vẫn có thể giữ nguyên cách viết ban đầu để hiển thị.

Ví dụ:

| Cách viết | DSL phân biệt hoa thường | DSL không phân biệt hoa thường |
| --- | --- | --- |
| `entity` | Từ khóa | Từ khóa |
| `Entity` | Có thể là định danh | Từ khóa |
| `ENTITY` | Có thể là định danh | Từ khóa |
| `myEntity` | Định danh | Định danh |

Không có lựa chọn nào phù hợp với mọi DSL. Cần chọn theo thói quen người dùng, quy ước của ngôn ngữ chủ và mục tiêu tương thích. Quan trọng nhất là ghi rõ trong tài liệu và áp dụng nhất quán.

### 5.2. Quy tắc tên định danh

Nếu định danh dùng cùng hình thức chữ với từ khóa, cần có quy tắc tránh xung đột. Ví dụ:

- Bắt đầu bằng chữ cái hoặc dấu gạch dưới.
- Các ký tự tiếp theo có thể gồm chữ, số và dấu gạch dưới.
- Không được trùng từ khóa dành riêng.
- Không chứa khoảng trắng hoặc ký tự phân cách cú pháp.
- Có quy tắc rõ ràng cho Unicode nếu cho phép tên không dùng bảng chữ cái Latin.

Ví dụ định danh hợp lệ theo một quy ước đơn giản:

~~~text
Customer
customerId
_orderStatus
OrderLine2
~~~

Ví dụ không hợp lệ theo cùng quy ước:

~~~text
2Customer
customer id
where
~~~

Các quy tắc trên chỉ là ví dụ. Đặc tả DSL phải nêu chính xác ký tự nào được phép và cách xử lý tên trùng.

### 5.3. Unicode và chuẩn hóa tên

Nếu DSL cho phép định danh Unicode, hai chuỗi có thể trông giống nhau nhưng được mã hóa bằng các chuỗi code point khác nhau. Điều này có thể gây nhầm lẫn khi tìm kiếm, so sánh hoặc kiểm soát trùng tên.

Có thể quy định chuẩn hóa Unicode, giới hạn tập ký tự hoặc khuyến nghị một quy ước đặt tên. Với DSL dùng trong hệ thống nhiều ngôn ngữ, cần cân nhắc cả khả năng đọc, công cụ biên tập và nguy cơ ký tự đồng hình (homoglyph) gây nhầm lẫn.

Không nên âm thầm thay đổi tên người dùng nhập nếu việc chuẩn hóa có thể khiến hai định danh khác nhau trở thành một. Quy tắc chuẩn hóa cần được xác định trước và áp dụng nhất quán khi khai báo lẫn tra cứu.

## 6. Khi cần dùng từ khóa làm tên định danh

Một khái niệm miền có thể trùng với từ khóa. Ví dụ, một hệ thống có thực thể tên `Order`, `Group`, `User` hoặc thuộc tính tên `type`, `value`. Nếu những tên này bị dành riêng, người dùng cần cách biểu diễn thay thế.

### 6.1. Đổi tên định danh

Cách đơn giản là chọn tên khác:

~~~text
entity OrderRecord {
  field orderType: String
}
~~~

Cách này dễ đọc nhưng đôi khi làm thay đổi thuật ngữ nghiệp vụ. Nếu tên chính thức trong miền là Order, việc bắt người dùng gọi nó là OrderRecord có thể tạo ra sự khác biệt không cần thiết giữa mô hình và nghiệp vụ.

### 6.2. Dùng tên có escape hoặc trích dẫn

Một số DSL cho phép đặt tên đặc biệt trong dấu nháy hoặc ký hiệu escape:

~~~text
entity `order` {
  field `type`: String
}
~~~

Hoặc:

~~~text
entity "order" {
  field "type": String
}
~~~

Cú pháp minh họa này cho phép phân biệt một từ khóa với một định danh có cùng văn bản. Tuy nhiên, cần quy định rõ dấu nháy nào được hỗ trợ, cách escape ký tự nằm trong tên và cách hiển thị tên đó trong AST, thông báo lỗi hoặc mã được sinh ra.

Dấu nháy cũng có thể mang ý nghĩa chuỗi literal. Vì vậy, không nên dùng cùng cú pháp cho tên định danh và giá trị chuỗi nếu không có cách phân biệt rõ ràng trong grammar.

### 6.3. Dùng contextual keyword

Nếu một từ chỉ cần có ý nghĩa đặc biệt trong một vị trí, có thể dùng từ khóa theo ngữ cảnh để tránh cấm từ đó trong mọi nơi.

Ví dụ, `where` chỉ được xem là từ khóa trong khai báo truy vấn, còn ở một vị trí tên trường hợp lệ nó có thể được dùng như định danh nếu grammar không gây mơ hồ.

Cách này cần được cân nhắc cùng khả năng đọc và độ phức tạp của parser. Nếu quy tắc quá khó đoán, escape identifier có thể là giải pháp rõ ràng hơn.

## 7. Thiết kế tập từ khóa cho DSL

Tập từ khóa cần phản ánh mô hình miền và công việc chính của ngôn ngữ. Không nên bắt đầu bằng cách thu thập thật nhiều từ tiếng Anh rồi biến chúng thành từ khóa.

### 7.1. Bắt đầu từ các cấu trúc cốt lõi

Xác định những cấu trúc người dùng cần biểu đạt thường xuyên:

- Khai báo khái niệm: entity, type, field.
- Khai báo quan hệ: relation, has, belongsTo.
- Truy vấn: select, from, where, groupBy.
- Ràng buộc: require, unique, optional.
- Điều khiển: if, else, for, while.
- Quy trình: workflow, step, dependsOn.
- Giá trị và trạng thái: true, false, null, enabled.

Không phải DSL nào cũng cần tất cả các nhóm. Một DSL chỉ mô tả schema có thể không cần từ khóa điều khiển luồng; một DSL truy vấn có thể không cần workflow hay step.

### 7.2. Ưu tiên từ ngữ nhất quán

Nếu dùng `entity` cho khái niệm miền, tránh dùng `object` cho cùng ý nghĩa ở một phần khác nếu không có khác biệt ngữ nghĩa. Tương tự, nếu dùng `field` để mô tả thuộc tính, hãy cân nhắc giữ cách gọi đó thay vì thay đổi giữa `field`, `property` và `attribute` mà không có lý do.

Một bộ từ khóa nhất quán giúp:

- Người dùng dễ học và nhớ.
- Tài liệu ít phải giải thích thuật ngữ trùng nghĩa.
- Parser và công cụ hỗ trợ dễ duy trì.
- Các phần mở rộng không tạo ra nhiều cách diễn đạt cùng một ý nghĩa.

### 7.3. Hạn chế số lượng từ khóa

Mỗi từ khóa mới làm giảm không gian đặt tên và có thể tạo ra xung đột với cấu hình cũ. Chỉ nên thêm từ khóa khi nó giúp biểu đạt một cấu trúc hoặc ý nghĩa thực sự cần thiết.

Nếu một khả năng có thể được biểu diễn rõ bằng tên hàm, tên kiểu hoặc thư viện, không nhất thiết phải đưa thêm từ khóa vào grammar.

Ví dụ, `sum` có thể là hàm dựng sẵn thay vì từ khóa. Khi đó, người thiết kế có thể mở rộng thư viện với `avg`, `min` và `max` mà không phải sửa grammar cho từng hàm.

### 7.4. Tránh từ khóa quá chung hoặc quá mơ hồ

Các từ như `do`, `run`, `process` hoặc `handle` có thể có ý nghĩa rộng. Nếu dùng làm từ khóa, cần giải thích chính xác chúng thực hiện hoặc giới thiệu cấu trúc nào.

Tên từ khóa nên phản ánh vai trò trong DSL. Chẳng hạn, `dependsOn` mô tả quan hệ phụ thuộc rõ hơn `after` nếu ngôn ngữ cần biểu đạt đồ thị phụ thuộc thay vì chỉ thứ tự văn bản.

### 7.5. Đặt từ khóa theo ngữ cảnh miền

Từ khóa của DSL nên gần với ngôn ngữ chuyên môn của người dùng. Một DSL quản lý thư viện có thể dùng `borrow`, `return` và `reservation`; DSL phân tích dữ liệu có thể dùng `dataset`, `filter`, `groupBy` và `aggregate`.

Tuy vậy, không nên đưa thuật ngữ nghiệp vụ vào tập từ khóa chỉ vì chúng quan trọng. Tên như Book, Reader, Customer hay Product thường là định danh do mô hình cụ thể khai báo. Từ khóa nên dành cho cấu trúc chung của ngôn ngữ.

## 8. Mở rộng từ khóa và tương thích phiên bản

Khi DSL phát triển, nhóm có thể cần bổ sung từ khóa. Đây là thay đổi có ảnh hưởng đến cú pháp và khả năng tương thích.

Giả sử phiên bản 1 cho phép định danh `group`. Ở phiên bản 2, nhóm muốn thêm từ khóa `group` để biểu thị phép nhóm dữ liệu. Cấu hình cũ có thể chứa:

~~~text
entity group {
  field id: Integer
}
~~~

Nếu `group` trở thành từ khóa dành riêng, cấu hình cũ có thể không còn parse được. Vì vậy, cần có chính sách quản lý từ khóa.

### 8.1. Một số chiến lược tương thích

| Chiến lược | Cách làm | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Từ khóa theo ngữ cảnh | Chỉ coi từ là từ khóa ở vị trí grammar cụ thể | Ít làm hỏng định danh cũ | Parser và grammar phức tạp hơn |
| Escape identifier | Cho phép trích dẫn tên trùng từ khóa | Người dùng vẫn giữ tên miền chính xác | Cú pháp và quy tắc escape cần tài liệu |
| Phiên bản grammar | Chọn tập từ khóa theo phiên bản tệp | Có thể giữ nguyên hành vi cũ | Phải duy trì nhiều phiên bản |
| Alias hoặc tên thay thế | Cung cấp từ khóa mới nhưng vẫn hỗ trợ cách cũ | Chuyển đổi dần | Có thể kéo dài thời gian hỗ trợ |
| Cảnh báo trước khi dành riêng | Đầu tiên cảnh báo, sau đó mới cấm trong phiên bản lớn | Người dùng có thời gian sửa | Cần quy trình phát hành và thông báo |

Không có chiến lược duy nhất phù hợp cho mọi DSL. Với cấu hình được lưu lâu dài hoặc trao đổi giữa nhiều hệ thống, phiên bản hóa và công cụ di trú thường rất quan trọng.

### 8.2. Không thay đổi ý nghĩa từ khóa âm thầm

Nếu một từ khóa đang mang ý nghĩa A và phiên bản mới muốn dùng nó cho ý nghĩa B, thay đổi này có thể khiến cùng một cấu hình tạo ra hành vi khác nhau.

Ví dụ, `optional` có thể ban đầu nghĩa là trường có thể vắng mặt, sau đó bị thay đổi thành “cho phép giá trị null”. Hai khái niệm này không luôn tương đương. Một trường không được cung cấp và một trường được cung cấp với giá trị null có thể có hành vi khác nhau.

Nếu cần đổi ngữ nghĩa, hãy cân nhắc từ khóa mới, phiên bản grammar mới hoặc quy tắc chuyển đổi tường minh.

### 8.3. Danh sách từ khóa được công bố

Đặc tả DSL nên cung cấp danh sách từ khóa, mô tả ý nghĩa, phạm vi sử dụng và trạng thái phiên bản.

Một bảng đơn giản:

| Từ khóa | Vai trò | Ngữ cảnh | Phiên bản |
| --- | --- | --- | --- |
| `entity` | Bắt đầu khai báo thực thể | Cấp cao nhất | 1 |
| `field` | Khai báo thuộc tính | Trong entity | 1 |
| `relation` | Khai báo quan hệ | Cấp cao nhất | 1 |
| `where` | Mở đầu điều kiện lọc | Trong query | 1 |
| `groupBy` | Khai báo trường nhóm | Trong query | 1 |
| `constraint` | Bắt đầu ràng buộc | Cấp cao nhất | 1 |

Danh sách này giúp người dùng biết tên nào được dành riêng, công cụ biên tập có thể tô màu đúng và nhóm phát triển có thể đánh giá tác động khi thêm từ khóa mới.

## 9. Thông báo lỗi liên quan đến từ khóa

Thông báo lỗi tốt giúp người dùng phân biệt lỗi từ khóa, lỗi cú pháp và lỗi định danh.

Ví dụ, nếu DSL gặp từ khóa không được hỗ trợ:

~~~text
entity Customer {
  field name: String
  mandatory field id: Integer
}
~~~

Nếu `mandatory` chưa phải từ khóa hợp lệ trong vị trí đó, parser có thể báo:

~~~text
Syntax error at line 3, column 3:
Unexpected keyword 'mandatory'.
Expected: 'field'.
~~~

Nếu người dùng dùng từ khóa dành riêng làm tên:

~~~text
entity where {
  field id: Integer
}
~~~

Thông báo có thể là:

~~~text
Invalid identifier 'where':
the name is reserved by the DSL.
Use a different name or quote the identifier.
~~~

Thông báo nên chỉ ra:

- Vị trí lỗi.
- Token hoặc tên đã gặp.
- Những token hoặc cấu trúc được mong đợi.
- Lý do tên bị từ chối.
- Cách sửa có thể áp dụng.

Không nên chỉ báo chung chung “Invalid syntax” nếu lexer hoặc parser có đủ thông tin để giải thích lỗi cụ thể.

## 10. Từ khóa trong công cụ biên tập và trải nghiệm người dùng

Tập từ khóa được thiết kế tốt còn giúp các công cụ hỗ trợ người viết DSL.

### 10.1. Syntax highlighting

Editor có thể tô màu từ khóa khác với định danh, literal và chuỗi. Điều này giúp người dùng nhận ra cấu trúc chương trình nhanh hơn.

Ví dụ, trong đoạn:

~~~text
entity Customer {
  field name: String
  field active: Boolean
}
~~~

Editor có thể tô màu `entity` và `field` như từ khóa; Customer, name và active như định danh; String và Boolean theo kiểu dữ liệu; dấu ngoặc theo cấu trúc.

Màu sắc chỉ hỗ trợ đọc. Việc tô màu cần dựa trên parser hoặc lexer phù hợp, không nên chỉ dùng tìm kiếm chuỗi đơn giản vì từ khóa có thể xuất hiện trong comment hoặc chuỗi literal.

### 10.2. Auto-completion

Editor có thể gợi ý từ khóa hợp lệ dựa trên vị trí con trỏ. Sau `entity`, công cụ có thể gợi ý tên định danh; bên trong entity, sau `field` có thể gợi ý tên thuộc tính và kiểu.

Gợi ý theo ngữ cảnh giúp người dùng không phải ghi nhớ toàn bộ grammar. Để làm được điều này, công cụ cần hiểu trạng thái phân tích cú pháp hoặc sử dụng Language Server Protocol (LSP) nếu DSL có hệ sinh thái editor phù hợp.

### 10.3. Tài liệu và trợ giúp

Mỗi từ khóa nên có mô tả ngắn, ví dụ hợp lệ, ngữ cảnh được phép và liên kết đến phần giải thích chi tiết. Khi người dùng đặt con trỏ lên từ khóa, editor có thể hiển thị tài liệu tương ứng.

Nếu một từ khóa đã bị đánh dấu deprecated, editor có thể hiển thị cảnh báo và gợi ý từ khóa thay thế.

## 11. Ví dụ tổng hợp: thiết kế từ khóa cho DSL mô hình miền

Giả sử xây dựng DSL để mô tả thực thể, thuộc tính, quan hệ và ràng buộc. Một tập từ khóa ban đầu có thể gồm:

| Nhóm | Từ khóa đề xuất | Mục đích |
| --- | --- | --- |
| Khai báo | `entity`, `field` | Mô tả thực thể và thuộc tính |
| Quan hệ | `relation`, `from`, `to` | Liên kết các thực thể |
| Ràng buộc | `constraint`, `require`, `unique` | Mô tả điều kiện hợp lệ |
| Truy vấn | `query`, `where`, `select` | Chọn và lọc dữ liệu |
| Logic | `and`, `or`, `not` | Kết hợp điều kiện |
| Literal | `true`, `false`, `null` | Biểu diễn giá trị đặc biệt |

Một mô hình ví dụ:

~~~text
entity Customer {
  field id: Integer
  field name: String
  field active: Boolean
}

entity Order {
  field id: Integer
  field status: String
}

relation places {
  from Customer [1]
  to Order [0..*]
}

constraint ActiveCustomerRequired {
  require Customer.active == true
}
~~~

Trong ví dụ này:

- `entity` mở đầu khai báo thực thể.
- `field` khai báo thuộc tính.
- `relation` mở đầu quan hệ.
- `from` và `to` xác định hai đầu quan hệ.
- `constraint` mở đầu ràng buộc.
- `require` giới thiệu điều kiện phải thỏa mãn.
- `true` là literal boolean.

Các tên Customer, Order, places, id, name, active và status là định danh được khai báo. Integer, String và Boolean có thể là tên kiểu dựng sẵn. Nếu DSL muốn coi các kiểu dựng sẵn là từ khóa, cần ghi rõ trong đặc tả; cũng có thể xử lý chúng như các tên trong registry kiểu.

Từ khóa được chọn phản ánh cấu trúc chính của miền. Khi cần mở rộng, nhóm có thể bổ sung cú pháp cho enum, kế thừa, thuộc tính tùy chọn hoặc truy vấn, nhưng cần đánh giá xung đột với định danh đã tồn tại và tương thích phiên bản.

## 12. Những lỗi thường gặp khi thiết kế từ khóa

**Dành riêng quá nhiều từ.** Việc biến mọi tên hàm, kiểu dữ liệu và thuật ngữ nghiệp vụ thành từ khóa làm giảm không gian đặt tên. Hãy dành từ khóa cho cấu trúc hoặc ngữ nghĩa cú pháp thật sự cần thiết.

**Không phân biệt từ khóa với định danh.** Khi tài liệu gọi mọi từ quan trọng là từ khóa, người dùng không biết tên nào có thể đổi hoặc mở rộng. Hãy công bố rõ danh sách từ khóa và các tên dựng sẵn.

**Đặt tên không nhất quán.** Dùng nhiều từ gần nghĩa cho cùng một cấu trúc làm grammar khó học. Chọn một thuật ngữ chính và dùng nhất quán.

**Không xác định chữ hoa, chữ thường.** Người dùng có thể viết `Entity` ở một tệp và `entity` ở tệp khác rồi nhận kết quả khác nhau. Đặc tả phải quy định rõ chính sách so sánh.

**Không có cách escape từ khóa.** Một tên miền hợp lệ có thể trùng từ khóa. Nếu DSL dành riêng tên rộng rãi, hãy cung cấp cách đặt tên thay thế rõ ràng.

**Thêm từ khóa mà không xét tương thích.** Tên định danh cũ có thể trở thành từ khóa mới và khiến cấu hình không còn hợp lệ. Cần đánh giá dữ liệu đã lưu và có lộ trình chuyển đổi.

**Dựa vào syntax highlighting để xác định cú pháp.** Editor tô màu không phải bằng chứng câu lệnh hợp lệ. Lexer và parser mới quyết định token và cấu trúc theo đặc tả.

**Để từ khóa có ý nghĩa không rõ.** Từ như `run` hoặc `process` cần được định nghĩa chính xác về đầu vào, kết quả, lỗi và tác động phụ. Nếu không, người dùng khó dự đoán hành vi.

## 13. Kết luận

Từ khóa là những từ hoặc ký hiệu được DSL dành cho các vai trò cú pháp hay ngữ nghĩa đã định nghĩa. Chúng giúp nhận diện cấu trúc, thao tác và quy tắc của miền, đồng thời hỗ trợ lexer, parser và công cụ biên tập. Cần phân biệt từ khóa với định danh, tên hàm dựng sẵn và literal để người dùng hiểu rõ quy tắc đặt tên.

Khi thiết kế từ khóa, hãy bắt đầu từ những cấu trúc cốt lõi của DSL, chọn thuật ngữ nhất quán, hạn chế số lượng từ khóa và quy định rõ cách phân biệt hoa thường, escape định danh, phạm vi ngữ cảnh và phiên bản. Khi bổ sung từ khóa, cần xem xét khả năng xung đột với tên đã tồn tại và cung cấp thông báo lỗi, tài liệu cũng như công cụ chuyển đổi phù hợp.

Một tập từ khóa tốt không cần thật lớn. Nó cần đủ để người dùng diễn đạt rõ công việc của miền, đủ ổn định để cấu hình có thể được duy trì qua nhiều phiên bản và đủ nhất quán để parser cũng như người đọc hiểu cùng một ý nghĩa.

