# Cú pháp cụ thể và trừu tượng

Khi thiết kế một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), nhóm cần xác định cả cách người dùng viết hoặc nhìn thấy chương trình lẫn cấu trúc ý nghĩa mà công cụ xử lý bên trong. Hai khía cạnh này thường được gọi là **cú pháp cụ thể** (*concrete syntax*) và **cú pháp trừu tượng** (*abstract syntax*).

**Cú pháp cụ thể** quy định hình thức biểu diễn mà người dùng trực tiếp tương tác: từ khóa, dấu câu, cách viết tên, thứ tự thành phần, dấu ngoặc, bố cục hoặc ký hiệu đồ họa. **Cú pháp trừu tượng** mô tả những cấu trúc có ý nghĩa của ngôn ngữ và cách chúng kết hợp với nhau, độc lập với nhiều chi tiết trình bày cụ thể. Khi xử lý một DSL dạng văn bản, trình phân tích cú pháp thường chuyển văn bản theo cú pháp cụ thể thành cây cú pháp hoặc mô hình cú pháp trừu tượng để các bước tiếp theo kiểm tra và xử lý.

Ví dụ, người dùng có thể viết một quy tắc:

~~~text
when order.total > 1000 then approveOrder;
~~~

Ngữ pháp cụ thể xác định từ khóa `when`, biểu thức điều kiện, từ khóa `then`, hành động và dấu chấm phẩy. Cấu trúc trừu tượng tương ứng có thể là một nút `ConditionalRule` gồm một điều kiện so sánh và một hành động phê duyệt. Trình thực thi quan tâm đến quan hệ điều kiện–hành động và ý nghĩa nghiệp vụ, không cần dựa vào việc người dùng đã viết dấu chấm phẩy hay xuống dòng như thế nào.

Phân biệt hai khía cạnh này giúp DSL vừa có cách biểu diễn dễ hiểu vừa có mô hình nội bộ rõ ràng, dễ phân tích, kiểm tra, chuyển đổi, thực thi và phát triển theo phiên bản.

## 1. Cú pháp cụ thể là gì?

Cú pháp cụ thể là tập hợp quy tắc xác định một chương trình được viết hoặc trình bày như thế nào. Với DSL dạng văn bản, nó mô tả các ký hiệu và cách sắp xếp chúng thành những cấu trúc hợp lệ.

Các thành phần thường gặp gồm:

- **Từ khóa:** các từ dành riêng có ý nghĩa trong ngôn ngữ, ví dụ `policy`, `when`, `then`, `otherwise`.
- **Định danh:** tên do người viết đặt cho biến, thực thể, quy tắc hoặc thành phần, ví dụ `order`, `approveOrder`.
- **Hằng và literal:** giá trị số, chuỗi, ngày giờ, boolean hoặc giá trị miền, ví dụ `1000`, `"priority"`, `true`.
- **Toán tử:** ký hiệu hoặc từ biểu diễn phép tính và so sánh, ví dụ `+`, `>`, `and`, `in`.
- **Dấu phân cách và dấu nhóm:** dấu ngoặc, dấu phẩy, dấu chấm phẩy, dấu hai chấm hoặc dấu ngoặc nhọn.
- **Quy tắc kết hợp:** thứ tự và cấu trúc cho phép ghép các thành phần thành biểu thức, khai báo hoặc câu lệnh.
- **Quy tắc bố cục:** khoảng trắng, xuống dòng, thụt lề hoặc cách sắp xếp thành phần trên màn hình.

Ví dụ, hai đoạn sau có thể được thiết kế để biểu diễn cùng một quy tắc:

~~~text
when order.total > 1000 then approveOrder;
~~~

~~~text
rule {
    condition: order.total > 1000
    action: approveOrder
}
~~~

Đoạn thứ nhất dùng cấu trúc giống câu điều kiện; đoạn thứ hai dùng một khối có nhãn `condition` và `action`. Chúng có hình thức khác nhau nhưng có thể được ánh xạ đến cùng một cấu trúc trừu tượng nếu ngữ nghĩa được định nghĩa như nhau.

### Cú pháp cụ thể dạng văn bản

Đây là dạng thường gặp trong DSL lập trình và cấu hình. Người dùng nhập văn bản, còn công cụ phân tích các ký tự, token và cấu trúc theo ngữ pháp.

Ví dụ:

~~~text
entity Customer {
    id: CustomerId
    email: EmailAddress
    status: CustomerStatus
}
~~~

Cú pháp cụ thể quyết định từ khóa `entity`, cách viết tên `Customer`, dấu ngoặc nhọn, dấu hai chấm và cách liệt kê thuộc tính. Những lựa chọn này ảnh hưởng đến khả năng đọc, viết, định dạng và phát hiện lỗi.

### Cú pháp cụ thể dạng đồ họa

Cú pháp cụ thể không bắt buộc phải là văn bản. Một DSL đồ họa có thể dùng hộp, đường nối, biểu tượng, màu sắc và vị trí để biểu diễn quy trình hoặc mô hình.

Ví dụ, trong một DSL quy trình, hình chữ nhật có thể biểu diễn hoạt động, hình thoi biểu diễn quyết định và mũi tên biểu diễn luồng điều khiển. Người dùng kéo thả các phần tử trên màn hình; công cụ chuyển sơ đồ đó thành cấu trúc trừu tượng tương ứng.

### Cú pháp cụ thể dạng bảng hoặc biểu mẫu

Một số DSL dùng bảng, biểu mẫu hoặc cấu trúc có cột cố định. Ví dụ, một DSL định nghĩa quy tắc định giá có thể dùng bảng gồm các cột `Điều kiện`, `Mức giảm` và `Ưu tiên`. Cách biểu diễn này vẫn có cú pháp cụ thể: tiêu đề cột, kiểu ô, cách nhóm hàng, quy tắc giá trị bắt buộc và cách biểu diễn điều kiện.

Do đó, “cú pháp cụ thể” nên được hiểu là hình thức trình bày có quy tắc, không đồng nghĩa với “chuỗi ký tự”.

## 2. Cú pháp trừu tượng là gì?

Cú pháp trừu tượng mô tả những loại cấu trúc có ý nghĩa mà chương trình DSL có thể chứa và quan hệ giữa chúng. Nó tập trung vào thành phần ngữ nghĩa cần giữ lại, đồng thời bỏ qua nhiều chi tiết chỉ phục vụ cách viết hoặc cách trình bày.

Với ví dụ:

~~~text
when order.total > 1000 then approveOrder;
~~~

Mô hình trừu tượng có thể được mô tả như sau:

~~~text
ConditionalRule
  condition:
    GreaterThan
      left: PropertyAccess(Name("order"), "total")
      right: NumberLiteral(1000)
  action:
    ActionCall("approveOrder")
~~~

Mô hình này thể hiện cấu trúc và quan hệ cần thiết: một quy tắc có điều kiện; điều kiện là phép so sánh lớn hơn; vế trái truy cập thuộc tính `total` của `order`; vế phải là số `1000`; hành động là gọi `approveOrder`.

Nó không cần lưu dấu chấm phẩy, khoảng trắng hoặc việc người dùng xuống dòng ở đâu để biểu diễn ý nghĩa. Nếu công cụ cần định dạng lại văn bản hoặc hiển thị lỗi đúng vị trí, thông tin nguồn có thể được giữ ở một cấu trúc phụ trợ.

### Các loại nút trừu tượng

Một mô hình cú pháp trừu tượng thường có những loại nút tương ứng với cấu trúc của ngôn ngữ:

| Loại nút | Vai trò | Ví dụ |
|---|---|---|
| `Program` hoặc `Module` | Gốc của một chương trình hoặc đơn vị biên dịch. | Một tệp chính sách gồm nhiều khai báo. |
| `Declaration` | Khai báo khái niệm, biến, thực thể hoặc quy tắc. | `EntityDeclaration`, `PolicyDeclaration`. |
| `Statement` | Một hành động hoặc cấu trúc điều khiển. | `ConditionalRule`, `Assignment`, `ActionCall`. |
| `Expression` | Biểu thức tạo ra giá trị hoặc kết quả logic. | `GreaterThan`, `LogicalAnd`, `PropertyAccess`. |
| `Type` | Kiểu của giá trị hoặc đối tượng. | `MoneyType`, `DateType`, `OrderStatusType`. |
| `Literal` | Giá trị hằng được viết trong chương trình. | `NumberLiteral(1000)`, `BooleanLiteral(true)`. |
| `Reference` | Tham chiếu đến một khai báo hoặc phần tử miền. | Tham chiếu đến `Customer` hoặc `approveOrder`. |

Không phải DSL nào cũng cần các loại nút này. Mô hình nên phản ánh những khái niệm thực sự có trong miền và những thao tác công cụ cần hỗ trợ.

### Cú pháp trừu tượng không phải là ngữ nghĩa đầy đủ

Cấu trúc trừu tượng cho biết chương trình được tổ chức ra sao, nhưng chưa nhất thiết giải thích mọi quy tắc nghiệp vụ. Ví dụ, một nút `GreaterThan` cho biết có phép so sánh lớn hơn; việc so sánh hai giá trị `Money` có cùng đơn vị tiền tệ hay không có thể cần kiểm tra kiểu và ngữ nghĩa miền riêng.

Vì vậy, cần phân biệt:

- **Cú pháp trừu tượng:** cấu trúc hợp lệ và quan hệ giữa các thành phần.
- **Ngữ nghĩa tĩnh:** các điều kiện có thể kiểm tra mà không thực thi, chẳng hạn tên tham chiếu tồn tại, kiểu tương thích, khai báo không trùng và quy tắc cấu trúc.
- **Ngữ nghĩa động:** hành vi và kết quả khi chương trình được thực thi, chẳng hạn cách tính phí, chuyển trạng thái hoặc xử lý ngoại lệ.

Một AST hợp lệ về mặt cấu trúc vẫn có thể chứa tham chiếu không tồn tại hoặc biểu thức sai kiểu. Ngược lại, một AST đã qua kiểm tra tĩnh vẫn có thể tạo ra kết quả nghiệp vụ không mong muốn nếu ngữ nghĩa động hoặc dữ liệu đầu vào không đúng.

## 3. Cú pháp cụ thể và cú pháp trừu tượng khác nhau thế nào?

| Tiêu chí | Cú pháp cụ thể | Cú pháp trừu tượng |
|---|---|---|
| Mục tiêu | Xác định cách người dùng viết hoặc nhìn thấy chương trình. | Xác định cấu trúc ý nghĩa của chương trình. |
| Thành phần | Từ khóa, token, dấu câu, bố cục, ký hiệu hoặc thành phần giao diện. | Nút khai báo, biểu thức, câu lệnh, kiểu, quan hệ và tham chiếu. |
| Phụ thuộc cách trình bày | Phụ thuộc trực tiếp vào hình thức biểu diễn. | Ít phụ thuộc vào chi tiết trình bày. |
| Người quan tâm chính | Người viết DSL, người đọc DSL, nhà thiết kế trải nghiệm và người xây dựng parser/editor. | Nhà thiết kế ngôn ngữ, bộ kiểm tra ngữ nghĩa, trình thực thi, trình sinh mã và công cụ phân tích. |
| Thay đổi thường gặp | Đổi từ khóa, dấu phân cách, thứ tự trường, cách định dạng hoặc ký hiệu. | Thêm hoặc thay đổi loại nút, thuộc tính, quan hệ hoặc quy tắc cấu trúc. |
| Vai trò trong xử lý | Là đầu vào để phân tích và xây dựng cấu trúc. | Là biểu diễn trung gian cho kiểm tra, chuyển đổi và thực thi. |
| Ví dụ | `when ... then ...;` | `ConditionalRule(condition, action)` |

Có thể hình dung cú pháp cụ thể là “cách nói” và cú pháp trừu tượng là “cấu trúc điều được nói”. Một ý nghĩa có thể được biểu diễn bằng nhiều cách cụ thể; một cách viết chỉ hợp lệ nếu tuân theo quy tắc cú pháp cụ thể đã định nghĩa.

## 4. Từ cú pháp cụ thể đến cú pháp trừu tượng

Với DSL văn bản, quá trình chuyển đổi thường gồm các giai đoạn: phân tích từ vựng, phân tích cú pháp và xây dựng biểu diễn trừu tượng. Sau đó, bộ kiểm tra ngữ nghĩa xử lý các ràng buộc sâu hơn.

~~~mermaid
flowchart LR
    A[Văn bản DSL] --> B[Phân tích từ vựng]
    B --> C[Chuỗi token]
    C --> D[Phân tích cú pháp]
    D --> E[Cây phân tích / CST]
    E --> F[Xây dựng AST]
    F --> G[Kiểm tra ngữ nghĩa]
    G --> H[Mô hình đã kiểm tra]
    H --> I[Thực thi hoặc sinh mã]
~~~

Các công cụ và kiến trúc có thể gộp hoặc tách các giai đoạn khác nhau. Một parser có thể tạo AST trực tiếp mà không công khai CST. Với DSL đồ họa, thay vì lexer và parser văn bản, bộ xử lý giao diện có thể tạo mô hình từ các phần tử và kết nối mà người dùng thao tác.

### 4.1. Phân tích từ vựng (lexical analysis)

Phân tích từ vựng đọc chuỗi ký tự và nhóm chúng thành các đơn vị gọi là **token**. Token thường có loại, giá trị và vị trí nguồn.

Với dòng DSL:

~~~text
when order.total > 1000 then approveOrder;
~~~

Chuỗi token có thể là:

| Thứ tự | Loại token | Giá trị |
|---:|---|---|
| 1 | `WHEN` | `when` |
| 2 | `IDENTIFIER` | `order` |
| 3 | `DOT` | `.` |
| 4 | `IDENTIFIER` | `total` |
| 5 | `GREATER_THAN` | `>` |
| 6 | `NUMBER` | `1000` |
| 7 | `THEN` | `then` |
| 8 | `IDENTIFIER` | `approveOrder` |
| 9 | `SEMICOLON` | `;` |

Khoảng trắng và xuống dòng thường bị bỏ qua hoặc giữ như trivia tùy nhu cầu công cụ. Token vẫn nên mang thông tin vị trí để thông báo lỗi có thể chỉ ra dòng và cột.

### 4.2. Phân tích cú pháp (parsing)

Parser nhận chuỗi token và kiểm tra chúng có tuân theo ngữ pháp hay không. Nó xác định token nào thuộc khai báo, biểu thức, câu lệnh hoặc cấu trúc khác.

Nếu DSL quy định câu lệnh phải có dạng `when Expression then Action ;`, đoạn thiếu `then` hoặc thiếu hành động sẽ gây lỗi cú pháp. Parser có thể tạo một cây phân tích phản ánh cách các quy tắc ngữ pháp được áp dụng.

### 4.3. Xây dựng cấu trúc trừu tượng

Từ cây phân tích, công cụ có thể tạo AST chỉ giữ các thành phần cần thiết cho các bước tiếp theo. Dấu ngoặc, dấu phân cách và các nút ngữ pháp trung gian có thể được loại bỏ nếu chúng không mang ý nghĩa độc lập.

Ví dụ, cây phân tích có thể chứa các nút cho `WHEN`, `Expression`, `THEN`, `Action` và `SEMICOLON`. AST có thể chỉ còn `ConditionalRule(condition, action)` cùng các nút biểu thức và hành động.

### 4.4. Kiểm tra ngữ nghĩa

Sau khi tạo AST, bộ kiểm tra ngữ nghĩa có thể xác nhận:

- `order` đã được khai báo hoặc được cung cấp trong ngữ cảnh hiện tại.
- `total` là thuộc tính hợp lệ của kiểu `Order`.
- Kiểu của `total` có thể so sánh với literal `1000` theo quy tắc miền.
- `approveOrder` là hành động được phép gọi trong ngữ cảnh này.
- Người khai báo có quyền sử dụng hành động đó nếu DSL có quy tắc phân quyền.
- Quy tắc không mâu thuẫn với các ràng buộc khác trong cùng chính sách.

Những điều này không thể được xác định chỉ bằng việc token có đúng thứ tự hay không.

## 5. Ngữ pháp cụ thể bằng EBNF

Ngữ pháp hình thức mô tả cách các thành phần cụ thể có thể kết hợp thành chương trình hợp lệ. Một cách ghi phổ biến là EBNF (*Extended Backus–Naur Form*).

Ví dụ, DSL chính sách có thể có ngữ pháp đơn giản:

~~~ebnf
Program        = { Declaration } ;
Declaration    = PolicyDeclaration ;
PolicyDeclaration
               = "policy", Identifier, "{", { Rule }, "}" ;
Rule           = "when", Expression, "then", Action, ";" ;
Action         = Identifier ;
Expression     = Comparison ;
Comparison     = Primary, [ CompareOperator, Primary ] ;
Primary        = Identifier, [ ".", Identifier ]
               | Number
               | "(", Expression, ")" ;
CompareOperator = ">" | ">=" | "<" | "<=" | "==" | "!=" ;
Identifier     = Letter, { Letter | Digit | "_" } ;
Number         = Digit, { Digit } ;
~~~

Theo ngữ pháp trên, chương trình:

~~~text
policy OrderPolicy {
    when order.total > 1000 then approveOrder;
}
~~~

là một khai báo chính sách có một quy tắc. Ngữ pháp quy định thứ tự thành phần và những token được phép xuất hiện.

### Terminal và non-terminal

- **Terminal** là ký hiệu cuối cùng xuất hiện trong chương trình, như `policy`, `{`, `}`, `when`, `then`, `;`, `>` hoặc một token `Identifier` được lexer nhận diện.
- **Non-terminal** là ký hiệu đại diện cho một cấu trúc có thể được khai triển theo quy tắc khác, như `Program`, `PolicyDeclaration`, `Rule` hoặc `Expression`.

Trong EBNF, dấu ngoặc nhọn `{ ... }` thường biểu thị lặp không hoặc nhiều lần; dấu ngoặc vuông `[ ... ]` thường biểu thị thành phần tùy chọn. Quy ước chính xác có thể khác giữa công cụ, vì vậy tài liệu ngữ pháp cần nêu rõ ký pháp được sử dụng.

### Ngữ pháp cụ thể không tự định nghĩa toàn bộ ý nghĩa

Ngữ pháp cho biết `order.total > 1000` có cấu trúc so sánh hợp lệ. Nó chưa cho biết `order` là đối tượng nào, `total` có kiểu gì, đơn vị tiền tệ ra sao hoặc `approveOrder` có được phép gọi hay không. Các điều kiện đó thuộc mô hình trừu tượng, kiểm tra ngữ nghĩa và quy tắc miền.

## 6. Cây phân tích, CST và AST

Các khái niệm **parse tree**, **Concrete Syntax Tree (CST)** và **Abstract Syntax Tree (AST)** có liên quan nhưng không phải lúc nào cũng được dùng hoàn toàn đồng nhất giữa các công cụ.

### Cây phân tích (parse tree)

Cây phân tích thể hiện cách chuỗi token được suy dẫn từ các quy tắc ngữ pháp. Nó thường giữ lại các nút non-terminal và terminal để giải thích vì sao một chuỗi được xem là hợp lệ theo ngữ pháp.

Với quy tắc:

~~~text
when order.total > 1000 then approveOrder;
~~~

cây phân tích có thể có dạng khái quát:

~~~text
Rule
├── "when"
├── Expression
│   └── Comparison
│       ├── Primary
│       │   ├── Identifier("order")
│       │   ├── "."
│       │   └── Identifier("total")
│       ├── ">"
│       └── Number("1000")
├── "then"
├── Action
│   └── Identifier("approveOrder")
└── ";"
~~~

Cây này hữu ích để hiểu quá trình phân tích và chẩn đoán lỗi cú pháp.

### Concrete Syntax Tree (CST)

CST thường giữ chi tiết cấu trúc theo ngữ pháp cụ thể. Tùy công cụ, nó có thể bảo toàn token, dấu câu, dấu ngoặc, comment, khoảng trắng hoặc thông tin định dạng. CST đặc biệt hữu ích cho công cụ chỉnh sửa mã cần giữ nguyên cách viết của người dùng.

Ví dụ, nếu người dùng viết:

~~~text
when (order.total > 1000) then approveOrder ; // urgent orders
~~~

CST hoặc cấu trúc cú pháp có thông tin nguồn có thể giữ dấu ngoặc quanh biểu thức, khoảng trắng trước dấu chấm phẩy và comment `// urgent orders` để trình định dạng hoặc trình biên tập bảo toàn chúng.

### Abstract Syntax Tree (AST)

AST giữ cấu trúc trừu tượng cần thiết cho phân tích, chuyển đổi hoặc thực thi. Nó thường bỏ qua các chi tiết trình bày không ảnh hưởng đến ý nghĩa.

AST cho ví dụ trên có thể được biểu diễn:

~~~text
ConditionalRule
├── condition: GreaterThan
│   ├── PropertyAccess
│   │   ├── Name("order")
│   │   └── Property("total")
│   └── NumberLiteral(1000)
└── action: ActionCall("approveOrder")
~~~

Hai cách viết có hoặc không có dấu ngoặc có thể tạo cùng AST nếu dấu ngoặc chỉ dùng để nhóm biểu thức mà không thay đổi cấu trúc. Comment và khoảng trắng cũng thường không nằm trong AST thông thường.

### So sánh CST và AST

| Tiêu chí | CST | AST |
|---|---|---|
| Mục tiêu | Giữ cấu trúc theo cú pháp cụ thể. | Giữ cấu trúc ý nghĩa cần cho xử lý. |
| Terminal và dấu câu | Thường được giữ hoặc có thể truy cập. | Thường được loại bỏ nếu không mang ý nghĩa. |
| Nút trung gian của ngữ pháp | Thường được giữ theo cấu trúc parser. | Có thể được rút gọn hoặc hợp nhất. |
| Comment và khoảng trắng | Có thể được bảo toàn cùng vị trí nguồn. | Thường không được giữ trong cây AST cơ bản. |
| Định dạng lại mã | Hữu ích để giữ cách viết gốc. | Cần thông tin nguồn bổ sung hoặc formatter riêng. |
| Phân tích ngữ nghĩa và thực thi | Có thể dùng, nhưng chứa nhiều chi tiết cú pháp. | Thường thuận tiện hơn vì cấu trúc đã được rút gọn. |
| Công cụ thường dùng | Parser IDE, formatter, refactoring và bộ xử lý cú pháp cụ thể. | Type checker, optimizer, interpreter, code generator và analyzer. |

Không phải mọi hệ thống đều tạo cả CST lẫn AST. Một số parser tạo AST trực tiếp; một số công cụ lưu CST giàu thông tin rồi cung cấp API để truy cập cấu trúc trừu tượng. Điều quan trọng là xác định dữ liệu nào cần được giữ cho từng mục tiêu công cụ.

## 7. Thiết kế mô hình cú pháp trừu tượng

Mô hình cú pháp trừu tượng cần được thiết kế như một mô hình ngôn ngữ, không chỉ là cấu trúc dữ liệu tạm thời. Nó quyết định những khái niệm nào có thể biểu diễn và các bước xử lý sau đó hiểu chúng như thế nào.

### Xác định các loại cấu trúc chính

Hãy bắt đầu từ các khái niệm và hành vi trong miền. Với DSL chính sách đơn hàng, mô hình có thể gồm:

- `Policy`: một chính sách gồm tên và danh sách quy tắc.
- `Rule`: một quy tắc gồm điều kiện và hành động.
- `Expression`: biểu thức tạo ra giá trị hoặc kết quả logic.
- `PropertyAccess`: truy cập thuộc tính của một đối tượng.
- `Comparison`: so sánh hai biểu thức.
- `Action`: hành động được phép thực hiện trong miền.
- `Literal`: giá trị hằng.
- `Reference`: tham chiếu đến biến, thuộc tính hoặc hành động đã khai báo.

Các loại cấu trúc này cần có quan hệ và kiểu rõ ràng. Chẳng hạn, `Rule.condition` phải là biểu thức cho kết quả boolean; `Rule.action` phải là hành động hợp lệ trong ngữ cảnh chính sách.

### Biểu diễn bằng kiểu dữ liệu

Một cách mô hình hóa trừu tượng bằng Java có thể sử dụng sealed interface và record:

~~~java
sealed interface Expr
    permits NameExpr, PropertyExpr, NumberExpr, GreaterThanExpr {}

record NameExpr(String name) implements Expr {}

record PropertyExpr(Expr target, String property) implements Expr {}

record NumberExpr(java.math.BigDecimal value) implements Expr {}

record GreaterThanExpr(Expr left, Expr right) implements Expr {}

record ActionCall(String name) {}

record ConditionalRule(Expr condition, ActionCall action) {}

record Policy(String name, java.util.List<ConditionalRule> rules) {}
~~~

Đây là mô hình minh họa. Trong thiết kế thực tế, có thể cần nhiều loại biểu thức hơn, kiểu kết quả, định danh ổn định, thông tin vị trí nguồn, annotation và các cấu trúc cho thông báo lỗi.

### Biểu diễn bằng metamodel

Với DSL lớn hoặc DSL dựa trên mô hình, cú pháp trừu tượng có thể được định nghĩa bằng một **metamodel**. Metamodel mô tả những loại phần tử có thể tồn tại, thuộc tính của chúng, quan hệ giữa chúng, kiểu dữ liệu và ràng buộc.

Ví dụ, một metamodel có thể quy định:

| Phần tử | Thuộc tính | Quan hệ và ràng buộc |
|---|---|---|
| `Policy` | `name: String` | Có 0 hoặc nhiều `Rule`; tên không rỗng. |
| `Rule` | `description: String` | Có đúng một `condition` và một `action`. |
| `Condition` | — | Phải tạo ra kết quả boolean. |
| `Action` | `name: String` | Phải tham chiếu đến hành động đã được đăng ký. |
| `PropertyReference` | `name: String` | Phải tham chiếu đến thuộc tính có trong kiểu của đối tượng đích. |

Metamodel thường được dùng trong các nền tảng kỹ nghệ hướng mô hình (Model-Driven Engineering — MDE), nơi mô hình được xem như một sản phẩm có cấu trúc và có thể được kiểm tra, biến đổi hoặc sinh mã.

## 8. Quan hệ giữa cú pháp trừu tượng và ngữ nghĩa DSL

AST cho biết một chương trình gồm những cấu trúc nào. Để hiểu và thực thi chương trình, DSL cần định nghĩa ý nghĩa của từng cấu trúc.

Ví dụ, nút:

~~~text
GreaterThan(left, right)
~~~

chỉ thể hiện phép so sánh lớn hơn. Ngữ nghĩa phải trả lời:

- Hai vế có bắt buộc cùng kiểu không?
- Có được so sánh `Money` với số nguyên không?
- Nếu hai giá trị tiền khác đơn vị tiền tệ thì xử lý ra sao?
- Nếu một thuộc tính không có giá trị thì kết quả là `false`, lỗi hay giá trị không xác định?
- Phép so sánh được đánh giá lúc biên dịch hay lúc thực thi?

### Ngữ nghĩa tĩnh

Ngữ nghĩa tĩnh là những quy tắc có thể xác định mà không cần chạy chương trình. Ví dụ:

- Tên thực thể hoặc hành động được tham chiếu phải tồn tại.
- Kiểu của biểu thức điều kiện phải là boolean.
- Một thuộc tính chỉ được truy cập trên kiểu có thuộc tính đó.
- Một khai báo không được trùng định danh trong cùng phạm vi.
- Một hành động phải được phép xuất hiện trong loại quy tắc đang xét.

### Ngữ nghĩa động

Ngữ nghĩa động mô tả hành vi khi chương trình được thực thi. Ví dụ:

- Đánh giá điều kiện theo dữ liệu đơn hàng hiện tại.
- Gọi hành động phê duyệt khi điều kiện đúng.
- Xử lý lỗi khi dịch vụ kho không phản hồi.
- Quyết định có tiếp tục thực hiện quy tắc kế tiếp hay không.
- Ghi nhận kết quả, sự kiện hoặc lịch sử thực thi.

### Mô hình trừu tượng đã được kiểm tra

Trong một số kiến trúc, sau kiểm tra ngữ nghĩa, AST được bổ sung thông tin kiểu, tham chiếu đã phân giải hoặc metadata. Có thể xem đây là mô hình ngữ nghĩa hoặc AST đã phân giải (*resolved/typed AST*). Nó giúp interpreter và code generator không phải tìm lại thông tin tên và kiểu từ đầu.

Ví dụ, `NameExpr("order")` sau khi phân giải có thể chứa tham chiếu đến biến hoặc tham số có kiểu `Order`. `PropertyExpr(..., "total")` có thể được gắn kiểu `Money`. Khi đó, bộ kiểm tra có đủ thông tin để xác định phép so sánh có hợp lệ hay không.

## 9. Một ý nghĩa, nhiều cách viết cụ thể

Một ưu điểm của việc tách cú pháp cụ thể và trừu tượng là cho phép thay đổi cách trình bày mà không phải thay đổi mô hình ý nghĩa nếu ngữ nghĩa vẫn giữ nguyên.

Ví dụ, DSL có thể cho phép hai cách khai báo:

~~~text
when order.total > 1000 then approveOrder;
~~~

~~~text
rule {
    if: order.total > 1000
    do: approveOrder
}
~~~

Cả hai có thể ánh xạ đến:

~~~text
ConditionalRule(
    GreaterThan(PropertyAccess(order, total), NumberLiteral(1000)),
    ActionCall(approveOrder)
)
~~~

Điều này hữu ích khi một DSL hỗ trợ nhiều giao diện: cú pháp văn bản cho lập trình viên, giao diện đồ họa cho người dùng nghiệp vụ hoặc biểu mẫu cho cấu hình đơn giản. Mỗi cách biểu diễn có thể dùng cùng một mô hình trừu tượng và cùng một bộ kiểm tra ngữ nghĩa.

Tuy nhiên, hai cách viết chỉ nên ánh xạ đến cùng cấu trúc khi ý nghĩa thật sự tương đương. Nếu một dạng biểu diễn ngầm định thứ tự ưu tiên hoặc hành vi khác, cần có cấu trúc trừu tượng hoặc metadata thể hiện sự khác biệt đó.

## 10. Một cách viết cụ thể có thể có nhiều dạng chuẩn hóa

Ngược lại, cùng một chương trình có thể được viết với khác biệt về khoảng trắng, xuống dòng hoặc dấu ngoặc nhưng vẫn có cùng ý nghĩa.

~~~text
when order.total>1000 then approveOrder;
~~~

~~~text
when (order.total > 1000)
then approveOrder ;
~~~

Nếu ngữ pháp cho phép các cách viết trên, parser có thể tạo cùng AST. Công cụ định dạng có thể chọn một kiểu viết chuẩn, ví dụ:

~~~text
when order.total > 1000 then approveOrder;
~~~

Đây là lý do nên phân biệt định dạng nguồn với mô hình ý nghĩa. AST giúp so sánh cấu trúc chương trình mà không bị ảnh hưởng bởi nhiều khác biệt trình bày không quan trọng.

## 11. Biểu thức, độ ưu tiên và tính kết hợp

Một phần quan trọng khi thiết kế cú pháp cụ thể là xác định thứ tự đánh giá của biểu thức. Nếu ngữ pháp không làm rõ độ ưu tiên (*precedence*) và tính kết hợp (*associativity*), cùng một biểu thức có thể được hiểu theo nhiều cách.

Ví dụ:

~~~text
a + b * c
~~~

Thông thường, phép nhân có độ ưu tiên cao hơn phép cộng nên cấu trúc trừu tượng là:

~~~text
Add
├── Name(a)
└── Multiply
    ├── Name(b)
    └── Name(c)
~~~

Tương ứng với `a + (b * c)`, thay vì `(a + b) * c`.

### Ngữ pháp phân tầng theo độ ưu tiên

Có thể mô tả ngữ pháp biểu thức theo nhiều tầng:

~~~ebnf
Expression  = Additive ;
Additive    = Multiplicative, { ("+" | "-"), Multiplicative } ;
Multiplicative
            = Primary, { ("*" | "/"), Primary } ;
Primary     = Number
            | Identifier
            | "(", Expression, ")" ;
~~~

Trong ví dụ, `Multiplicative` nằm sâu hơn `Additive`, vì vậy toán tử nhân và chia được nhóm trước cộng và trừ. Cách cài parser khác nhau có thể sử dụng precedence table hoặc thuật toán Pratt parser thay cho ngữ pháp phân tầng tường minh.

### Tính kết hợp

Với biểu thức:

~~~text
a - b - c
~~~

nếu toán tử trừ kết hợp trái, AST sẽ là:

~~~text
Subtract
├── Subtract
│   ├── Name(a)
│   └── Name(b)
└── Name(c)
~~~

Tức là `(a - b) - c`. Nếu kết hợp phải, kết quả cấu trúc sẽ là `a - (b - c)`. DSL phải xác định quy tắc kết hợp cho từng toán tử, nhất là khi các phép toán không có tính kết hợp như trừ hoặc chia.

### Tránh ngữ pháp mơ hồ

Một ngữ pháp mơ hồ cho phép cùng một chuỗi đầu vào tạo ra nhiều cây phân tích khác nhau. Điều này làm parser khó quyết định cấu trúc ý nghĩa. Có thể xử lý bằng cách:

- Viết ngữ pháp phân tầng rõ độ ưu tiên.
- Định nghĩa precedence và associativity trong parser.
- Yêu cầu dấu ngoặc ở những chỗ cần nhóm biểu thức.
- Tránh các cấu trúc cú pháp có thể được phân tích theo nhiều cách không cần thiết.

## 12. Cú pháp trừu tượng và cú pháp cụ thể trong DSL đồ họa

Với DSL đồ họa, người dùng thao tác trên hình dạng và kết nối thay vì viết chuỗi ký tự. Tuy vậy, vẫn cần phân biệt cách trình bày với cấu trúc ý nghĩa.

Ví dụ, một sơ đồ quy trình có:

- Hình chữ nhật biểu diễn hành động `ReserveInventory`.
- Hình thoi biểu diễn quyết định `InventoryAvailable`.
- Mũi tên có nhãn `yes` và `no` biểu diễn các nhánh.
- Hình bắt đầu và kết thúc biểu diễn điểm vào/ra của quy trình.

Đó là cú pháp cụ thể đồ họa. Mô hình trừu tượng có thể chứa:

~~~text
Workflow
├── Step(ReserveInventory)
└── Decision(InventoryAvailable)
    ├── Branch(condition = true, target = CreateShipment)
    └── Branch(condition = false, target = RequestReplenishment)
~~~

Nếu người dùng di chuyển một hình chữ nhật sang vị trí khác mà không thay đổi kết nối hoặc ý nghĩa, mô hình trừu tượng không cần thay đổi. Nếu người dùng đổi nhánh `yes` sang một hoạt động khác, mô hình trừu tượng phải thay đổi.

### Vị trí đồ họa có phải là ngữ nghĩa không?

Thông thường, tọa độ, kích thước, màu nền và vị trí hiển thị là thông tin trình bày. Chúng có thể được lưu trong metadata hoặc mô hình ký hiệu (*notation model*) riêng. Tuy nhiên, một số DSL đồ họa có thể gán ý nghĩa cho vị trí hoặc cấu trúc không gian. Khi đó, vị trí là một phần của ngữ nghĩa và không được loại bỏ như metadata trang trí.

Ví dụ, trong DSL bố trí giao diện, tọa độ và kích thước của thành phần có thể trực tiếp quyết định giao diện được tạo ra. Trong DSL mô tả luồng công việc, vị trí hộp trên màn hình thường chỉ nhằm giúp sơ đồ dễ đọc, còn thứ tự điều khiển được thể hiện bằng kết nối.

## 13. Ánh xạ giữa cú pháp cụ thể và trừu tượng

Mối quan hệ giữa hai lớp cú pháp thường được gọi là ánh xạ (*mapping*). Với DSL văn bản, parser thực hiện ánh xạ từ cấu trúc cụ thể sang AST. Với công cụ mô hình, bộ xử lý giao diện có thể tạo AST từ các đối tượng đồ họa.

### Ánh xạ một-một, một-nhiều và nhiều-một

Không phải lúc nào quan hệ cũng là một-một:

- **Một cấu trúc cụ thể sang một nút trừu tượng:** một khai báo `entity Customer` có thể tạo một nút `EntityDeclaration`.
- **Một cấu trúc cụ thể sang nhiều nút:** một cú pháp rút gọn có thể được mở rộng thành nhiều nút AST hoặc nút chuẩn hóa.
- **Nhiều cấu trúc cụ thể sang một nút:** nhiều cách viết tương đương có thể tạo cùng loại AST.
- **Một nút trừu tượng sang nhiều dạng cụ thể:** cùng một AST có thể được tuần tự hóa thành văn bản, JSON, bảng hoặc sơ đồ đồ họa.

Ví dụ, cú pháp rút gọn:

~~~text
allowPaidOrders;
~~~

có thể được chuẩn hóa thành một cấu trúc tương đương:

~~~text
when order.payment.status == ACCEPTED then allowOrder;
~~~

Nếu hai cách viết được định nghĩa có cùng ý nghĩa, parser có thể tạo cùng AST. Cú pháp rút gọn giúp người dùng thường xuyên viết trường hợp phổ biến; AST vẫn giữ cấu trúc chuẩn để xử lý thống nhất.

### Chuẩn hóa (normalization)

Chuẩn hóa là chuyển nhiều cách biểu diễn hợp lệ về một dạng cấu trúc thống nhất. Ví dụ, alias hoặc cú pháp rút gọn có thể được mở rộng thành cấu trúc chuẩn trước khi kiểm tra ngữ nghĩa.

Chuẩn hóa giúp:

- Giảm số trường hợp mà bộ kiểm tra ngữ nghĩa phải xử lý.
- Đơn giản hóa trình thực thi hoặc trình sinh mã.
- So sánh chương trình dễ hơn.
- Hỗ trợ nhiều cú pháp cụ thể cùng dùng chung mô hình.

Tuy nhiên, chuẩn hóa cần giữ thông tin nguồn nếu công cụ cần hiển thị lại cách viết ban đầu hoặc chỉ ra vị trí chính xác của lỗi.

## 14. Thông tin nguồn và khả năng chẩn đoán

AST thường bỏ các chi tiết trình bày, nhưng công cụ phát triển DSL vẫn cần biết nút AST xuất phát từ đoạn văn bản nào. Vì vậy, nhiều hệ thống lưu **source location** hoặc **source span** cho từng nút.

Thông tin nguồn có thể gồm:

- Tên tệp hoặc định danh tài liệu.
- Vị trí bắt đầu và kết thúc theo offset ký tự hoặc byte.
- Dòng và cột bắt đầu/kết thúc.
- Token hoặc đoạn văn bản gốc tương ứng.
- Liên kết đến comment hoặc trivia liên quan nếu cần.

Ví dụ, nếu `order.total` không hợp lệ vì `total` không tồn tại, thông báo lỗi có thể trỏ chính xác vào đoạn `total` thay vì chỉ báo “chương trình không hợp lệ”.

~~~text
policy OrderPolicy {
    when order.totla > 1000 then approveOrder;
                 ^^^^^
}

Error: Order không có thuộc tính 'totla'. Có phải bạn muốn dùng 'total'?
~~~

Để làm được điều này, parser hoặc AST cần giữ vị trí nguồn và bộ kiểm tra ngữ nghĩa cần liên kết lỗi với nút tương ứng.

### Comment, khoảng trắng và trivia

Comment và khoảng trắng thường không ảnh hưởng đến ngữ nghĩa, nhưng lại quan trọng với công cụ định dạng, tài liệu hóa và tái cấu trúc mã. Một parser phục vụ compiler có thể loại bỏ chúng; một parser phục vụ IDE có thể lưu chúng trong CST hoặc cấu trúc trivia riêng.

Ví dụ, công cụ đổi tên một định danh cần cập nhật đúng token trong nguồn mà vẫn giữ comment và định dạng. Nếu chỉ có AST không kèm vị trí hoặc cấu trúc nguồn, việc viết lại mã có thể làm mất cách trình bày ban đầu.

## 15. Cú pháp trừu tượng trong các bước xử lý tiếp theo

Sau khi có AST, nhiều công cụ có thể hoạt động trên cùng một mô hình:

| Công cụ hoặc bước xử lý | Cách sử dụng AST |
|---|---|
| Kiểm tra tên | Duyệt các khai báo và tham chiếu để xây dựng symbol table, phát hiện tên chưa tồn tại hoặc khai báo trùng. |
| Kiểm tra kiểu | Gán kiểu cho biểu thức, kiểm tra toán tử và kiểu tham số. |
| Kiểm tra quy tắc miền | Xác minh bất biến, trạng thái, quyền và ràng buộc nghiệp vụ. |
| Trình thông dịch | Duyệt AST và thực hiện hành vi theo ngữ nghĩa DSL. |
| Trình sinh mã | Chuyển AST thành mã nguồn hoặc cấu hình của nền tảng đích. |
| Tối ưu hóa | Biến đổi cấu trúc mà vẫn giữ ngữ nghĩa. |
| Phân tích tĩnh | Tìm mã không thể đạt tới, quy tắc mâu thuẫn hoặc tham chiếu không dùng. |
| Trình trực quan hóa | Hiển thị cấu trúc DSL dưới dạng cây, đồ thị hoặc sơ đồ. |
| So sánh phiên bản | So sánh các nút và quan hệ thay vì chỉ so sánh chuỗi văn bản. |

Ví dụ, một trình sinh mã có thể chuyển `ConditionalRule` thành đoạn mã Java, cấu hình workflow hoặc lời gọi API. Vì nó làm việc trên AST, nó không cần biết người dùng đã viết cú pháp dạng `when ... then ...` hay dạng khối `rule { ... }`.

## 16. Tách mô hình trừu tượng khỏi cách lưu trữ

AST hoặc metamodel mô tả cấu trúc của chương trình, còn định dạng lưu trữ mô tả cách dữ liệu được tuần tự hóa. Hai khái niệm có liên quan nhưng không đồng nhất.

Ví dụ, một chính sách có thể được lưu dưới dạng JSON:

~~~json
{
  "kind": "ConditionalRule",
  "condition": {
    "kind": "GreaterThan",
    "left": {
      "kind": "PropertyAccess",
      "target": { "kind": "Name", "value": "order" },
      "property": "total"
    },
    "right": { "kind": "NumberLiteral", "value": 1000 }
  },
  "action": {
    "kind": "ActionCall",
    "name": "approveOrder"
  }
}
~~~

JSON là định dạng tuần tự hóa. Các giá trị `kind`, `condition`, `left`, `right` và `action` phản ánh mô hình trừu tượng đã chọn. Cùng AST đó có thể được lưu bằng định dạng nhị phân, XML, cơ sở dữ liệu hoặc được tạo trực tiếp trong bộ nhớ.

Một DSL có thể có nhiều định dạng trao đổi nhưng vẫn dùng chung một metamodel. Điều này hữu ích khi cần tích hợp với hệ thống khác, lưu phiên bản mô hình hoặc tạo giao diện đồ họa.

## 17. Kiểm tra tính hợp lệ của cú pháp cụ thể và trừu tượng

Việc xác nhận chương trình DSL nên được thực hiện ở nhiều lớp.

### Kiểm tra cú pháp cụ thể

Các câu hỏi thường gặp:

- Token có hợp lệ không?
- Từ khóa có được đặt đúng vị trí không?
- Dấu ngoặc có cân bằng không?
- Khai báo có tuân theo cấu trúc ngữ pháp không?
- Biểu thức có thể được phân tích theo một cách xác định không?
- Các ký hiệu hoặc tên có tuân theo quy tắc từ vựng không?

### Kiểm tra cấu trúc trừu tượng

Sau khi tạo AST, cần xác nhận:

- Các nút có đúng loại và đúng số lượng quan hệ không?
- Các thuộc tính bắt buộc đã có chưa?
- Một `Policy` có chứa các loại khai báo được phép không?
- Một `Rule` có đúng một điều kiện và hành động không?
- Các danh sách và quan hệ có thỏa bội số được quy định không?

### Kiểm tra ngữ nghĩa

Tiếp theo, xác nhận tên, kiểu, quy tắc nghiệp vụ, quyền và các phụ thuộc. Chẳng hạn, một `ActionCall` có thể đúng cấu trúc nhưng tên hành động không được đăng ký; một `GreaterThan` có thể đúng cấu trúc nhưng hai vế không thể so sánh.

Phân lớp lỗi giúp người dùng sửa đúng vấn đề. Lỗi thiếu dấu `;` là lỗi cú pháp; lỗi tham chiếu đến `approveOrdre` không tồn tại là lỗi phân giải tên; lỗi so sánh `Money` với `Date` là lỗi kiểu; lỗi phê duyệt đơn chưa thanh toán là vi phạm quy tắc miền khi thực thi hoặc kiểm tra ngữ nghĩa tùy dữ liệu có sẵn.

## 18. Thiết kế cú pháp cụ thể dễ sử dụng

Cú pháp cụ thể là phần người dùng nhìn thấy thường xuyên, vì vậy cần cân nhắc khả năng đọc và viết trong công việc thực tế.

### Sử dụng thuật ngữ miền nhất quán

Tên từ khóa, thuộc tính và hành động nên phản ánh cách gọi đã được xác nhận trong miền. Nếu nhóm nghiệp vụ gọi là “đơn hàng”, không nên tùy tiện dùng ba tên `order`, `purchase` và `transaction` cho cùng một khái niệm.

### Giữ cú pháp nhất quán

Các cấu trúc cùng loại nên dùng cùng quy ước. Ví dụ, nếu khai báo thuộc tính dùng dấu hai chấm thì không nên dùng dấu bằng cho cùng mục đích ở một cấu trúc khác mà không có lý do rõ ràng.

### Hạn chế sự mơ hồ

Ngữ pháp nên tránh trường hợp một chuỗi có thể được hiểu theo nhiều cách. Khi có thể, hãy xác định rõ thứ tự ưu tiên, cách nhóm biểu thức, phạm vi của khối và cách kết thúc câu lệnh.

### Đưa ra thông báo lỗi gần với thuật ngữ miền

Thông báo như “expected token 17” ít hữu ích hơn “Thiếu từ khóa `then` sau điều kiện của quy tắc”. Công cụ nên gắn lỗi với đoạn nguồn và giải thích điều kiện hợp lệ.

### Hỗ trợ định dạng chuẩn

Một formatter giúp các chương trình có cách trình bày thống nhất. Formatter nên giữ nguyên ngữ nghĩa, xử lý comment hợp lý và không tự ý thay đổi cấu trúc nghiệp vụ.

### Cân nhắc khả năng mở rộng

Từ khóa mới, cấu trúc mới và cú pháp rút gọn có thể ảnh hưởng đến chương trình cũ. Cần tránh sử dụng từ khóa có khả năng xung đột với tên người dùng và có quy tắc phiên bản rõ ràng.

## 19. Những thay đổi cú pháp và tác động đến AST

Không phải thay đổi cú pháp cụ thể nào cũng yêu cầu thay đổi cú pháp trừu tượng.

| Thay đổi | AST có cần đổi không? | Lý do |
|---|---|---|
| Đổi khoảng trắng hoặc quy tắc thụt lề | Thường không | Chỉ thay đổi định dạng. |
| Cho phép dấu `;` tùy chọn | Thường không | Cấu trúc câu lệnh và ngữ nghĩa không đổi. |
| Đổi từ khóa `when` thành `if` | Có thể không | Nếu vẫn biểu diễn cùng một loại quy tắc và không đổi ý nghĩa. |
| Thêm cú pháp rút gọn cho một quy tắc phổ biến | Có thể không | Cú pháp mới có thể được chuẩn hóa về AST hiện tại. |
| Thêm loại biểu thức mới | Thường có | AST cần biểu diễn cấu trúc và ngữ nghĩa mới. |
| Thêm trạng thái mới cho một khái niệm miền | Có thể có | Metamodel hoặc kiểu miền cần hỗ trợ trạng thái mới. |
| Thay đổi ý nghĩa của một toán tử | Có thể cần | Ngữ nghĩa AST thay đổi dù hình thức có thể giữ nguyên. |
| Chuyển từ quy tắc tuần tự sang quy tắc song song | Thường có | Mô hình cần biểu diễn quan hệ thực thi hoặc cấu trúc điều khiển mới. |

Việc phân biệt thay đổi cú pháp và thay đổi mô hình giúp kiểm soát tương thích. Một parser có thể hỗ trợ cú pháp cũ và mới nhưng tạo cùng AST; ngược lại, nếu AST thay đổi, các bộ kiểm tra, trình thực thi, trình sinh mã và công cụ liên quan có thể cần cập nhật.

## 20. Quản lý phiên bản của cú pháp và mô hình

DSL được sử dụng lâu dài thường cần phát triển cả cú pháp cụ thể lẫn mô hình trừu tượng. Cần xác định phiên bản ngôn ngữ và cách xử lý chương trình được viết bằng phiên bản cũ.

Một số chiến lược:

- Gắn phiên bản DSL vào tệp hoặc cấu hình dự án.
- Duy trì parser tương thích với cú pháp cũ trong thời gian chuyển đổi.
- Chuyển AST cũ sang metamodel mới bằng bước migration.
- Đánh dấu cú pháp cũ là deprecated và cung cấp cách viết thay thế.
- Tạo formatter hoặc công cụ migration để chuyển mã nguồn sang cú pháp mới.
- Kiểm thử rằng chương trình cũ vẫn giữ hành vi nếu thay đổi chỉ mang tính trình bày.
- Ghi nhận những thay đổi ngữ nghĩa có thể làm kết quả thực thi khác đi.

Ví dụ, phiên bản 1 dùng:

~~~text
when order.paid then confirm;
~~~

Phiên bản 2 chuẩn hóa thành:

~~~text
when order.payment.status == ACCEPTED then confirm;
~~~

Nếu hai cách viết được xác định tương đương trong miền, parser phiên bản 2 có thể hỗ trợ cú pháp cũ như alias và tạo cùng cấu trúc trừu tượng chuẩn. Nếu ý nghĩa của `paid` đã thay đổi, không thể chỉ coi đây là đổi tên cú pháp; cần quy định migration và tác động nghiệp vụ.

## 21. Quy trình thiết kế từ cú pháp cụ thể đến trừu tượng

Một quy trình thực tế có thể triển khai theo các bước sau:

1. **Khám phá khái niệm miền:** xác định thực thể, hành động, điều kiện, trạng thái và quy tắc cần biểu diễn.
2. **Xác định người sử dụng và tình huống:** ai sẽ viết hoặc chỉnh sửa DSL, họ cần diễn đạt công việc nào và công cụ nào sẽ được dùng.
3. **Phác thảo cú pháp cụ thể:** viết ví dụ đại diện, chọn từ khóa, toán tử, dấu phân cách, cách nhóm và định dạng.
4. **Định nghĩa ngữ pháp:** mô tả cấu trúc hợp lệ bằng EBNF hoặc ký pháp phù hợp; xác định độ ưu tiên và tính kết hợp của biểu thức.
5. **Thiết kế mô hình trừu tượng:** xác định loại nút, thuộc tính, quan hệ, bội số và các ràng buộc cấu trúc.
6. **Định nghĩa ánh xạ:** chỉ rõ mỗi cấu trúc cụ thể được chuyển thành nút hoặc quan hệ trừu tượng nào.
7. **Xây dựng parser hoặc bộ chuyển đổi:** tạo CST/AST và giữ thông tin nguồn cần thiết.
8. **Bổ sung kiểm tra ngữ nghĩa:** phân giải tên, kiểm tra kiểu, quy tắc miền và quyền.
9. **Tích hợp thực thi hoặc sinh mã:** xử lý AST đã hợp lệ theo ngữ nghĩa đã định nghĩa.
10. **Kiểm chứng với ví dụ:** kiểm thử cú pháp hợp lệ, cú pháp sai, AST mong đợi, lỗi ngữ nghĩa và kết quả thực thi.
11. **Duy trì phiên bản:** quản lý thay đổi cú pháp, metamodel, parser và chương trình DSL đã có.

Nên thiết kế đồng thời ví dụ cú pháp và mô hình trừu tượng. Nếu chỉ chăm chút cú pháp mà chưa biết cấu trúc nội bộ cần có, nhóm có thể tạo ra ngôn ngữ khó phân tích. Nếu chỉ thiết kế AST mà không thử viết chương trình thực tế, cú pháp cụ thể có thể trở nên cồng kềnh hoặc không phù hợp với người dùng.

## 22. Ví dụ tổng hợp: DSL mô tả chính sách đơn hàng

Giả sử cần một DSL cho phép khai báo quy tắc xác nhận đơn hàng. Một chương trình cụ thể:

~~~text
policy OrderPolicy {
    when order.payment.status == ACCEPTED
         and order.items.count > 0
    then confirmOrder;
}
~~~

### Các token chính

| Token | Giá trị |
|---|---|
| `POLICY` | `policy` |
| `IDENTIFIER` | `OrderPolicy` |
| `LBRACE` | `{` |
| `WHEN` | `when` |
| `IDENTIFIER` | `order` |
| `DOT` | `.` |
| `IDENTIFIER` | `payment` |
| `DOT` | `.` |
| `IDENTIFIER` | `status` |
| `EQUALS_EQUALS` | `==` |
| `IDENTIFIER` | `ACCEPTED` |
| `AND` | `and` |
| `IDENTIFIER` | `order` |
| `DOT` | `.` |
| `IDENTIFIER` | `items` |
| `DOT` | `.` |
| `IDENTIFIER` | `count` |
| `GREATER_THAN` | `>` |
| `NUMBER` | `0` |
| `THEN` | `then` |
| `IDENTIFIER` | `confirmOrder` |
| `SEMICOLON` | `;` |
| `RBRACE` | `}` |

Danh sách trên được rút gọn để minh họa; lexer thực tế còn lưu loại token, vị trí nguồn và có thể phân biệt identifier với từ khóa tùy cách định nghĩa ngôn ngữ.

### AST khái quát

~~~text
Policy(name = "OrderPolicy")
└── Rule
    ├── condition: LogicalAnd
    │   ├── Equal
    │   │   ├── PropertyAccess(order.payment, status)
    │   │   └── EnumLiteral(ACCEPTED)
    │   └── GreaterThan
    │       ├── PropertyAccess(order.items, count)
    │       └── NumberLiteral(0)
    └── action: ActionCall(confirmOrder)
~~~

### Các kiểm tra ngữ nghĩa

Sau khi tạo AST, công cụ cần xác nhận:

1. `OrderPolicy` là tên hợp lệ và không trùng với khai báo khác trong phạm vi.
2. `order` có tồn tại trong ngữ cảnh thực thi của chính sách.
3. `payment` và `status` là các thuộc tính hợp lệ theo mô hình `Order`.
4. Kiểu của `status` cho phép so sánh với `ACCEPTED`.
5. `items.count` trả về kiểu số có thể so sánh với `0`.
6. Hai biểu thức con của `and` đều trả về boolean.
7. `confirmOrder` là hành động được đăng ký và được phép gọi trong chính sách.
8. Điều kiện xác nhận đơn phù hợp với quy tắc nghiệp vụ đã được phê duyệt.

### Ý nghĩa khi thực thi

Nếu điều kiện đúng, interpreter hoặc thành phần thực thi có thể gọi hành động xác nhận đơn. Nếu điều kiện sai, hành động không được gọi. Chính sách cần xác định cách ghi nhận kết quả, cách xử lý lỗi khi xác nhận thất bại và liệu các quy tắc khác có tiếp tục được đánh giá hay không.

### Một cú pháp cụ thể khác

Nếu DSL cung cấp dạng khối:

~~~text
policy "OrderPolicy" {
    rule {
        condition = order.payment.status == ACCEPTED and order.items.count > 0
        action = confirmOrder
    }
}
~~~

parser có thể tạo cùng cấu trúc AST. Điều này cho phép nhóm thay đổi cách viết hoặc cung cấp một editor đồ họa mà không phải viết lại bộ kiểm tra ngữ nghĩa và trình thực thi, miễn là ánh xạ giữ nguyên ngữ nghĩa.

## 23. Những sai lầm thường gặp

**Đồng nhất cú pháp cụ thể với cú pháp trừu tượng.** Một nhóm có thể nghĩ rằng AST chỉ là bản sao của văn bản có dấu ngoặc. Thực tế, AST cần thể hiện cấu trúc ý nghĩa và có thể loại bỏ nhiều chi tiết cú pháp.

**Cho rằng AST là toàn bộ ngữ nghĩa.** AST mô tả cấu trúc; kiểu, tham chiếu, ràng buộc và hành vi cần được xác định qua các bước ngữ nghĩa khác.

**Thiết kế parser trước khi hiểu miền.** Ngữ pháp có thể rất đẹp nhưng không biểu diễn đúng thuật ngữ và quy tắc nghiệp vụ. Cần bắt đầu từ ví dụ và khái niệm miền.

**Thiết kế AST quá sát cú pháp.** Nếu AST chứa quá nhiều nút chỉ để phản ánh dấu câu hoặc từ khóa, các bước xử lý sẽ phụ thuộc vào cách viết cụ thể và khó hỗ trợ nhiều dạng biểu diễn.

**Loại bỏ toàn bộ thông tin nguồn.** Việc bỏ vị trí, comment và token gốc làm cho formatter, IDE và thông báo lỗi khó hoạt động tốt. Cần quyết định thông tin nào được giữ trong CST hoặc metadata.

**Để ngữ pháp mơ hồ.** Không xác định độ ưu tiên, tính kết hợp hoặc phạm vi khối có thể khiến parser tạo cấu trúc không mong đợi.

**Để nhiều cú pháp có ý nghĩa khác nhau nhưng ánh xạ cùng AST.** Khi ánh xạ làm mất khác biệt ngữ nghĩa, chương trình có thể thực thi sai. Chỉ chuẩn hóa những dạng thực sự tương đương.

**Trộn AST với định dạng lưu trữ.** JSON hoặc XML là cách tuần tự hóa; chúng không tự động là mô hình trừu tượng. Cần định nghĩa metamodel độc lập với định dạng nếu muốn hỗ trợ nhiều cách lưu.

**Thay đổi cú pháp mà không xem xét tương thích.** Một từ khóa mới có thể xung đột với định danh cũ; một thay đổi AST có thể ảnh hưởng parser, validator và interpreter. Cần có quy tắc phiên bản và migration.

## 24. Câu hỏi khi rà soát thiết kế

Khi xem xét một DSL, nhóm có thể thảo luận các câu hỏi sau:

- Cú pháp cụ thể có phù hợp với người dùng và thuật ngữ miền không?
- Có thể đọc một chương trình DSL mà không phải hiểu chi tiết triển khai không?
- Ngữ pháp có xác định rõ từ khóa, định danh, biểu thức và cấu trúc khối không?
- Các biểu thức có độ ưu tiên và tính kết hợp rõ ràng không?
- Cú pháp trừu tượng có phản ánh khái niệm miền thay vì sao chép từng dấu câu không?
- Các nút trừu tượng có kiểu, thuộc tính và quan hệ rõ ràng không?
- Mỗi dạng cú pháp cụ thể được ánh xạ đến AST như thế nào?
- Có nhiều dạng cụ thể nào cùng biểu diễn một ý nghĩa không?
- AST có giữ đủ thông tin nguồn để hỗ trợ lỗi, định dạng và chỉnh sửa không?
- Kiểm tra cú pháp, cấu trúc, kiểu và quy tắc nghiệp vụ được phân chia ra sao?
- Thay đổi cú pháp hoặc metamodel ảnh hưởng đến chương trình cũ và công cụ nào?
- Có ví dụ kiểm thử chứng minh parser tạo đúng AST và AST được xử lý đúng không?

## 25. Kết quả cần có khi thiết kế hai lớp cú pháp

Một thiết kế DSL rõ ràng thường tạo ra các đầu ra sau:

1. **Đặc tả cú pháp cụ thể:** ví dụ chương trình, danh sách token, quy tắc từ vựng, ngữ pháp và quy tắc định dạng.
2. **Mô hình cú pháp trừu tượng:** danh sách loại nút, thuộc tính, quan hệ, kiểu và ràng buộc cấu trúc.
3. **Đặc tả ánh xạ:** cách từng cấu trúc cụ thể được chuyển thành AST hoặc mô hình tương ứng.
4. **Quy tắc ngữ nghĩa:** phân giải tên, kiểm tra kiểu, ràng buộc miền và hành vi thực thi.
5. **Thông tin nguồn và chẩn đoán:** cách lưu vị trí, comment hoặc metadata cần thiết cho công cụ.
6. **Bộ ví dụ và kiểm thử:** chương trình hợp lệ, chương trình sai cú pháp, AST mong đợi và kết quả kiểm tra ngữ nghĩa.
7. **Quy tắc phiên bản:** cách xử lý thay đổi cú pháp, mô hình, parser và chương trình DSL hiện có.

Khi hai lớp cú pháp được tách rõ và liên kết bằng quy tắc ánh xạ có thể kiểm chứng, nhóm có thể cải tiến trải nghiệm viết DSL mà vẫn giữ mô hình ý nghĩa ổn định. Cú pháp cụ thể giúp người dùng diễn đạt công việc; cú pháp trừu tượng cung cấp cấu trúc thống nhất cho phân tích, kiểm tra, chuyển đổi và thực thi. Đây là nền tảng quan trọng để xây dựng DSL dễ dùng, có ngữ nghĩa rõ ràng và có khả năng phát triển lâu dài.
