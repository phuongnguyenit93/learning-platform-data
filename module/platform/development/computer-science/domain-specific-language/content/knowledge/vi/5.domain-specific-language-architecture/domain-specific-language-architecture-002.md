# Tiền xử lý và frontend

## Vị trí của tiền xử lý và frontend trong kiến trúc DSL

Một ngôn ngữ chuyên miền (domain-specific language, DSL) cần một chuỗi thành phần để tiếp nhận nội dung do người dùng viết, hiểu cấu trúc của nội dung đó và chuyển nó thành biểu diễn mà phần còn lại của hệ thống có thể kiểm tra hoặc thực thi. Chuỗi thành phần này thường được gọi là *frontend* của DSL.

Frontend là cửa vào của hệ thống ngôn ngữ. Nó làm việc với văn bản nguồn và tạo ra một biểu diễn có cấu trúc, chẳng hạn cây cú pháp trừu tượng (Abstract Syntax Tree, AST), đồng thời phát hiện và báo cáo lỗi. Tùy kiến trúc, frontend có thể tiếp tục kiểm tra ngữ nghĩa và chuyển AST thành một dạng trung gian (Intermediate Representation, IR) để backend xử lý.

Tiền xử lý (preprocessing) là bước tùy chọn đứng trước hoặc đan xen với một số hoạt động phân tích cú pháp. Nó biến đổi, kết hợp hoặc chuẩn bị văn bản nguồn theo những quy tắc đã định nghĩa. Ví dụ, một DSL cấu hình có thể hỗ trợ chỉ thị include để ghép nội dung từ tệp khác; DSL quy tắc có thể hỗ trợ hằng số hoặc macro; một ngôn ngữ mô tả triển khai có thể hỗ trợ chỉ thị theo môi trường.

Một pipeline thường gặp có thể hình dung như sau:

```text
Tệp / văn bản nguồn
        |
        v
Đọc nguồn, xác định encoding và vị trí
        |
        v
Tiền xử lý (nếu DSL có hỗ trợ)
  - chỉ thị / include
  - macro / hằng số
  - điều kiện theo môi trường
        |
        v
Lexer (phân tích từ vựng)
        |
        v
Parser (phân tích cú pháp)
        |
        v
AST (cây cú pháp trừu tượng)
        |
        v
Phân tích ngữ nghĩa và kiểm tra miền
        |
        v
IR / mô hình đã xác thực
        |
        v
Backend: diễn giải, sinh mã hoặc thực thi
```

Sơ đồ là một cách tổ chức phổ biến, không phải quy định bắt buộc. Một DSL đơn giản có thể không cần tiền xử lý, thậm chí dùng parser trực tiếp trên luồng ký tự. Một DSL khác có thể phân tích chỉ thị include bằng lexer/parser riêng thay vì thay thế văn bản trước khi phân tích chính. Điều quan trọng là xác định rõ trách nhiệm, đầu vào, đầu ra và lỗi của từng giai đoạn.

## Tiếp nhận và quản lý văn bản nguồn

Trước khi phân tích nội dung, frontend cần biết chính xác dữ liệu nào đang được xử lý và vị trí của từng phần trong dữ liệu đó. Đây là nền tảng cho thông báo lỗi, xử lý include, hỗ trợ IDE và truy vết nguồn gốc biểu thức.

### Đọc nguồn và encoding

Nguồn DSL có thể đến từ một tệp, nhiều tệp, chuỗi trong giao diện, cơ sở dữ liệu hoặc một luồng do chương trình khác cung cấp. Thành phần đọc nguồn cần xác định encoding, xử lý lỗi giải mã và đưa nội dung về dạng ký tự mà lexer có thể sử dụng.

Các quyết định cần được quy định rõ:

- DSL chấp nhận encoding nào, ví dụ UTF-8.
- Byte sequence không hợp lệ sẽ bị từ chối hay thay bằng ký tự thay thế.
- Có cho phép ký tự BOM ở đầu tệp hay không.
- Quy tắc xuống dòng là LF, CRLF hay chấp nhận cả hai.
- Số dòng và cột trong thông báo lỗi được tính theo byte, code point hay đơn vị UTF-16.
- Tab, ký tự kết hợp và ký tự Unicode được hiển thị vị trí như thế nào.

Việc thống nhất cách tính vị trí rất quan trọng. Nếu parser báo lỗi ở cột 12 nhưng editor hiển thị cột 11 do khác quy ước đếm ký tự, người dùng sẽ khó tìm đúng vị trí.

### Source file, source unit và source location

Frontend nên biểu diễn nguồn bằng một cấu trúc có định danh và nội dung ổn định. Một source unit có thể chứa:

- ID hoặc URI của nguồn, chẳng hạn đường dẫn tệp hoặc định danh tài liệu.
- Nội dung đã giải mã.
- Encoding ban đầu và thông tin phiên bản nếu cần.
- Bảng ánh xạ offset ký tự sang dòng/cột.
- Quan hệ với nguồn cha nếu nội dung đến từ include hoặc macro expansion.

Một vị trí nguồn (source location) thường được biểu diễn bằng source ID cùng khoảng offset bắt đầu và kết thúc. Dùng khoảng thay vì chỉ một số dòng giúp frontend đánh dấu chính xác token hoặc biểu thức gây lỗi.

Ví dụ một mô hình dữ liệu khái quát:

```text
SourceFile
  id: "file:///rules/discount.dsl"
  text: "RULE ..."
  lineStarts: [0, 18, 42, ...]

SourceSpan
  sourceId: "file:///rules/discount.dsl"
  startOffset: 42
  endOffset: 55
```

Đây là biểu diễn minh họa. Hệ thống thực tế có thể dùng byte offset, code point offset hoặc một kiểu offset riêng, miễn là các thành phần cùng tuân theo một quy ước.

## Tiền xử lý là gì và khi nào cần dùng?

Tiền xử lý là giai đoạn thực hiện các phép biến đổi nguồn được DSL quy định trước khi hoặc trong lúc phân tích cú pháp chính. Mục đích thường là tái sử dụng nội dung, cấu hình theo môi trường, khai báo hằng số, mở rộng cú pháp tiện dụng hoặc chuẩn bị đầu vào cho parser.

Không phải DSL nào cũng cần tiền xử lý. Nếu ngôn ngữ chỉ có một tập cấu trúc nhỏ và không cần ghép nguồn hay macro, việc đưa thêm một tầng tiền xử lý có thể làm kiến trúc phức tạp và thông báo lỗi khó hiểu hơn. Chỉ nên bổ sung khi có nhu cầu thực tế, có ngữ nghĩa rõ và có thể kiểm soát tác động của phép biến đổi.

### Các chức năng tiền xử lý thường gặp

**Ghép hoặc include nguồn.** Một tệp có thể yêu cầu nội dung từ tệp khác. Chức năng này giúp chia cấu hình lớn thành các phần có thể tái sử dụng. Frontend cần xử lý đường dẫn tương đối, vòng lặp include, tệp không tồn tại và quyền truy cập.

**Định nghĩa hằng số hoặc tham số.** Người dùng có thể khai báo giá trị được dùng ở nhiều nơi, chẳng hạn ngưỡng, tên môi trường hoặc mã quy tắc. Cần quyết định việc thay thế diễn ra ở giai đoạn tiền xử lý hay được giữ thành nút trong AST để kiểm tra kiểu và phạm vi.

**Macro hoặc template.** Một cấu trúc có tên có thể được mở rộng thành nhiều biểu thức. Macro có thể giảm lặp nhưng làm thay đổi vị trí và hình dạng nguồn. Hệ thống cần quy định tham số, phạm vi, cách lồng nhau và giới hạn mở rộng.

**Biên dịch có điều kiện.** Một số phần nguồn có thể được chọn dựa trên profile hoặc biến cấu hình. Ví dụ, cấu hình môi trường thử nghiệm và môi trường sản xuất có thể dùng các giá trị khác nhau. Cần tránh để cùng một DSL có hành vi khó dự đoán do điều kiện môi trường không được công khai.

**Chuẩn hóa đầu vào.** Có thể cần loại bỏ BOM, chuẩn hóa xuống dòng hoặc xử lý một số ký tự điều khiển. Các phép chuẩn hóa phải giữ được ánh xạ vị trí về nguồn gốc để báo lỗi chính xác.

## Thiết kế chỉ thị tiền xử lý

Nếu DSL hỗ trợ chỉ thị, cần xác định cú pháp và ngữ nghĩa của chúng. Một số DSL đặt chỉ thị ở đầu dòng bằng ký hiệu đặc biệt; một số khác coi include hoặc import là cấu trúc cú pháp thông thường. Ví dụ giả định:

```text
include "common/customer.dsl"

define MIN_ORDER_TOTAL = 1000000

RULE "VIP shipping"
WHEN order.total >= MIN_ORDER_TOTAL
  AND customer.segment IS "VIP"
THEN shipment.fee = 0
```

Trong ví dụ, `include` và `define` là cú pháp giả định của DSL. Cách viết thực tế phải được quy định trong ngữ pháp. Cần quyết định chỉ thị được nhận diện trước lexer chính hay được parser đọc như các node bình thường.

### Include và import

Include thường đưa nội dung của một tệp vào vị trí đang khai báo. Import thường gắn với việc nạp một module hoặc namespace có danh tính, phạm vi và quy tắc tham chiếu riêng. Hai khái niệm này có thể được thiết kế khác nhau:

| Khía cạnh | Include | Import/module |
|---|---|---|
| Mục đích thường gặp | Kết hợp nội dung nguồn | Sử dụng khai báo từ module khác |
| Cách xử lý | Có thể mở rộng thành nội dung tại vị trí include | Có thể giữ tham chiếu đến module hoặc symbol |
| Phạm vi tên | Có thể chia sẻ cùng phạm vi sau khi ghép | Thường có namespace hoặc quy tắc xuất/nhập |
| Truy vết | Cần biết nội dung đến từ tệp nào | Cần biết symbol được khai báo ở module nào |

Không có một quy tắc phổ quát rằng include luôn là thay thế văn bản hay import luôn là module độc lập. Đó là quyết định thiết kế của DSL và cần được mô tả trong đặc tả.

Một bộ xử lý include nên kiểm tra:

- Đường dẫn được phân giải tương đối với tệp hiện tại hay một thư mục gốc cố định.
- Có cho phép đường dẫn tuyệt đối không.
- Có cho phép truy cập ra ngoài thư mục dự án không.
- Cách xử lý tệp được include nhiều lần.
- Cách phát hiện vòng lặp include, trực tiếp hoặc gián tiếp.
- Giới hạn độ sâu, số tệp và tổng dung lượng nguồn.
- Cách báo lỗi khi tệp không tồn tại hoặc không đọc được.

Ví dụ về vòng lặp:

```text
// a.dsl
include "b.dsl"

// b.dsl
include "a.dsl"
```

Frontend cần phát hiện vòng lặp và chỉ ra chuỗi include dẫn đến lỗi. Một giới hạn độ sâu đơn thuần có thể ngăn chương trình chạy vô hạn, nhưng thông báo tốt nên cho biết các tệp liên quan.

### Hằng số, macro và template

Hằng số thường chỉ thay một tên bằng một giá trị. Macro có thể mở rộng thành một biểu thức hoặc nhóm câu lệnh. Template có thể sinh văn bản hoặc cấu trúc dựa trên tham số. Những cơ chế này khác nhau về độ mạnh và rủi ro.

Ví dụ hằng số:

```text
define MAX_RETRY = 3
```

Ví dụ macro giả định:

```text
macro IS_VIP(customer) = customer.segment IS "VIP"

RULE "Priority processing"
WHEN IS_VIP(order.customer)
THEN order.priority = "HIGH"
```

Khi thiết kế macro, cần trả lời:

- Tham số được thay thế bằng văn bản hay bằng node AST đã phân tích?
- Macro có thể khai báo macro khác hoặc gọi đệ quy không?
- Tên nội bộ được tạo trong quá trình mở rộng có nguy cơ trùng tên không?
- Macro có được phép tạo chỉ thị, khai báo hoặc thay đổi phạm vi không?
- Khi mở rộng thất bại, lỗi được gắn với định nghĩa hay vị trí gọi macro?
- Người dùng có thể xem kết quả mở rộng để gỡ lỗi không?

Thay thế văn bản đơn giản dễ triển khai nhưng có thể tạo ra lỗi token, lỗi ưu tiên toán tử hoặc lỗi do chuỗi ký tự. Mở rộng trên token hoặc AST giúp giữ cấu trúc và kiểu dữ liệu tốt hơn, nhưng cần một mô hình macro rõ ràng hơn.

### Biên dịch có điều kiện

Một DSL có thể hỗ trợ chọn phần cấu hình dựa trên profile:

```text
if profile == "production":
    endpoint = "https://service.example"
else:
    endpoint = "https://test.example"
```

Đây là ví dụ giả định, không phải cú pháp chuẩn. Khi có biên dịch có điều kiện, cần xác định biến profile đến từ đâu, giá trị nào được phép, nhánh không được chọn có được phân tích cú pháp không và công cụ có kiểm tra được cả hai nhánh không.

Nếu chỉ phân tích nhánh đang hoạt động, lỗi cú pháp ở nhánh còn lại có thể không được phát hiện cho đến khi profile thay đổi. Nếu phân tích tất cả các nhánh nhưng chỉ kiểm tra ngữ nghĩa nhánh được chọn, cần mô tả rõ sự khác nhau đó.

## Giữ lại nguồn gốc sau khi biến đổi

Một vấn đề quan trọng của tiền xử lý là văn bản sau biến đổi có thể không còn giống nguồn người dùng đã viết. Nếu parser báo lỗi ở văn bản đã mở rộng mà không có ánh xạ ngược, người dùng sẽ khó tìm lỗi trong tệp ban đầu.

### Source map và expansion trace

Source map là cấu trúc ánh xạ một đoạn trong văn bản hoặc AST sau biến đổi về vị trí nguồn ban đầu. Khi nội dung được include, mỗi đoạn vẫn cần gắn với tệp xuất phát. Khi macro mở rộng, một node sinh ra có thể liên hệ với cả vị trí định nghĩa và vị trí gọi macro.

Ví dụ, macro được định nghĩa ở dòng 2 nhưng được gọi ở dòng 20. Nếu phần mở rộng sinh ra biểu thức không hợp lệ, thông báo có thể chỉ ra:

- Vị trí lời gọi macro ở dòng 20.
- Vị trí định nghĩa macro ở dòng 2.
- Vị trí của phần tham số gây ra vấn đề nếu có thể xác định.

Một expansion trace có thể lưu chuỗi biến đổi:

```text
discount.dsl:20:5
  -> macro IS_VIP defined at common/macros.dsl:2:1
  -> expanded expression at generated source offset 145
```

Đây là cách trình bày minh họa. Hệ thống có thể lưu cấu trúc máy đọc được rồi tạo thông báo thân thiện ở lớp diagnostics.

### Giữ comment và khoảng trắng

Comment và khoảng trắng có thể không ảnh hưởng đến ngữ nghĩa chương trình nhưng rất hữu ích cho tài liệu, định dạng, review và công cụ IDE. Nếu tiền xử lý loại bỏ chúng hoàn toàn, một số chức năng có thể mất thông tin cần thiết.

Có thể chọn một trong các chiến lược:

- Giữ comment và trivia (khoảng trắng, dòng mới, comment) trong token stream.
- Lưu chúng ở cấu trúc phụ gắn với token hoặc node AST.
- Dùng concrete syntax tree (CST) để giữ chi tiết cú pháp, đồng thời tạo AST gọn hơn cho phân tích ngữ nghĩa.

Không nhất thiết phải giữ mọi chi tiết trong AST. Cần chọn cấu trúc phù hợp với nhu cầu định dạng lại, refactoring, IDE và thông báo lỗi.

## Frontend: các thành phần chính

Sau khi nguồn được chuẩn bị, frontend phân tích văn bản thành các cấu trúc có ý nghĩa. Những thành phần phổ biến gồm lexer, parser, AST builder, phân tích ngữ nghĩa và diagnostics. Một số kiến trúc gộp hoặc tách các thành phần này tùy độ phức tạp của ngôn ngữ.

### Lexer — phân tích từ vựng

Lexer (còn gọi là tokenizer hoặc lexical analyzer) đọc chuỗi ký tự và tạo ra dãy token. Token là đơn vị có ý nghĩa ở cấp từ vựng, chẳng hạn định danh, số, chuỗi, từ khóa, toán tử hoặc dấu phân cách.

Ví dụ nguồn:

```text
WHEN order.total >= 1000000 AND customer.active
```

Có thể được chuyển thành token stream:

```text
WHEN_KEYWORD
IDENTIFIER("order")
DOT
IDENTIFIER("total")
GREATER_EQUAL
NUMBER(1000000)
AND_KEYWORD
IDENTIFIER("customer")
DOT
IDENTIFIER("active")
```

Danh sách token cụ thể phụ thuộc ngữ pháp của DSL. Lexer thường thực hiện các nhiệm vụ:

- Bỏ qua hoặc lưu khoảng trắng và comment theo chính sách của ngôn ngữ.
- Nhận diện từ khóa, định danh, literal, toán tử và dấu phân cách.
- Xử lý chuỗi có escape, số có dấu thập phân hoặc hậu tố đơn vị.
- Phát hiện ký tự không hợp lệ và chuỗi chưa đóng.
- Gắn source span vào từng token.

Lexer cần có quy tắc rõ cho các trường hợp dễ nhầm, chẳng hạn `-` là toán tử trừ hay dấu của số âm, `.` là dấu truy cập thuộc tính hay dấu thập phân, hoặc một từ có được xem là từ khóa trong mọi ngữ cảnh hay không.

### Parser — phân tích cú pháp

Parser nhận dãy token và kiểm tra chúng có tạo thành cấu trúc được ngữ pháp cho phép hay không. Nếu hợp lệ, parser xây dựng CST hoặc AST. Nếu không hợp lệ, nó tạo diagnostics và có thể cố gắng phục hồi để tiếp tục phân tích phần còn lại.

Ví dụ một quy tắc đơn giản có thể có ngữ pháp dạng EBNF:

```ebnf
rule        = "RULE", string, "WHEN", expression,
              "THEN", action ;

expression  = comparison, { ("AND" | "OR"), comparison } ;

comparison  = operand, comparisonOperator, operand ;

operand     = identifier, { ".", identifier }
            | number
            | string ;

action      = identifier, "=", operand ;
```

Đây là ngữ pháp rút gọn để minh họa. Ngữ pháp thực tế phải quy định độ ưu tiên và tính kết hợp của toán tử, ngoặc, biểu thức lồng nhau, kiểu literal và cấu trúc action. Nếu có biểu thức số học, parser cần phân biệt rõ `a + b * c` được hiểu là `a + (b * c)` hay `(a + b) * c` theo bảng precedence.

Hai họ parser thường gặp:

- **Top-down:** bắt đầu từ ký hiệu gốc và dự đoán cấu trúc cần đọc. Recursive descent là cách phổ biến, dễ viết bằng tay và dễ gắn thông báo lỗi theo từng quy tắc.
- **Bottom-up:** bắt đầu từ token và rút gọn thành cấu trúc lớn hơn. Các parser LR và biến thể có thể xử lý ngữ pháp phức tạp, thường được sinh bởi parser generator.

Lựa chọn phụ thuộc độ phức tạp ngữ pháp, khả năng bảo trì, yêu cầu thông báo lỗi và công cụ hiện có. Không có một kỹ thuật luôn tốt nhất cho mọi DSL.

### AST — cây cú pháp trừu tượng

AST biểu diễn cấu trúc và ý nghĩa cú pháp của chương trình dưới dạng cây. Nó bỏ qua nhiều chi tiết không cần thiết cho phân tích ngữ nghĩa, chẳng hạn một số dấu ngoặc hoặc khoảng trắng, nhưng giữ các quan hệ quan trọng.

Ví dụ biểu thức:

```text
order.total >= 1000000 AND customer.active
```

Có thể được biểu diễn khái quát:

```text
LogicalAnd
├── GreaterThanOrEqual
│   ├── MemberAccess(order, total)
│   └── NumberLiteral(1000000)
└── MemberAccess(customer, active)
```

AST giúp các bước sau làm việc với cấu trúc thay vì phải phân tích chuỗi văn bản lặp lại. Các node thường chứa:

- Loại node, ví dụ RuleDeclaration, BinaryExpression hoặc FunctionCall.
- Các node con và quan hệ thứ tự.
- Source span của cú pháp gốc.
- Thông tin phụ như symbol đã phân giải hoặc kiểu dữ liệu sau phân tích ngữ nghĩa.

Nên phân biệt AST cú pháp với mô hình ngữ nghĩa đã phân giải. Một AST vừa được parser tạo ra có thể chứa tên `customer` nhưng chưa biết nó tham chiếu đến biến, đối tượng hay module nào. Việc phân giải tên thường thuộc giai đoạn ngữ nghĩa.

### CST và AST khác nhau như thế nào?

Concrete Syntax Tree giữ sát cấu trúc cú pháp mà người dùng đã viết, thường gồm cả dấu ngoặc, dấu phân cách và node trung gian theo ngữ pháp. AST chỉ giữ cấu trúc cần thiết cho ý nghĩa và các thao tác tiếp theo.

| Tiêu chí | CST | AST |
|---|---|---|
| Mức độ gần nguồn | Gần với văn bản và ngữ pháp | Trừu tượng hóa chi tiết cú pháp |
| Dấu ngoặc, dấu phân cách | Thường được giữ thành node/token | Có thể được lược bỏ nếu không ảnh hưởng cấu trúc |
| Định dạng lại và refactoring | Thuận lợi vì giữ chi tiết nguồn | Có thể cần thông tin phụ hoặc CST gốc |
| Phân tích ngữ nghĩa và sinh mã | Có thể nhiều node phụ | Thường thuận tiện hơn |
| Bộ nhớ và độ phức tạp | Có thể lớn hơn | Thường gọn hơn |

Một công cụ DSL hướng đến IDE có thể giữ cả CST và AST. Một bộ xử lý cấu hình nhỏ chỉ cần AST có thể không cần CST.

## Phân tích ngữ nghĩa sau parser

Parser xác nhận cấu trúc cú pháp, nhưng một biểu thức đúng cú pháp vẫn có thể vô nghĩa trong miền. Phân tích ngữ nghĩa kiểm tra các quan hệ và ràng buộc không thể hoặc không nên mô tả hoàn toàn bằng ngữ pháp.

Các nhiệm vụ thường gặp:

- **Phân giải tên (name resolution):** xác định một tên tham chiếu đến biến, thuộc tính, hàm, quy tắc hoặc module nào.
- **Quản lý phạm vi (scope):** xác định nơi một khai báo có hiệu lực và quy tắc che khuất tên.
- **Kiểm tra kiểu (type checking):** xác nhận kiểu của toán hạng và kết quả phép toán tương thích.
- **Kiểm tra chữ ký thao tác:** số lượng, tên và kiểu tham số của hàm hoặc action có hợp lệ không.
- **Kiểm tra quy tắc miền:** trạng thái, vai trò, giới hạn và điều kiện nghiệp vụ có được đáp ứng không.
- **Kiểm tra tính nhất quán:** tham chiếu, khai báo, phụ thuộc và quy tắc có xung đột không.

Ví dụ:

```text
WHEN order.total >= "one million"
THEN shipment.fee = 0
```

Biểu thức có thể hợp lệ về cú pháp nếu ngữ pháp cho phép so sánh hai operand, nhưng sai kiểu nếu `order.total` là Money hoặc Decimal còn vế phải là String. Tương tự, `shipment.fee = 0` có thể đúng kiểu nhưng sai quy tắc nếu phí vận chuyển không được thay đổi ở trạng thái hiện tại.

### Symbol table và scope

Symbol table lưu thông tin về các tên được khai báo hoặc được cung cấp cho DSL, chẳng hạn tên, loại symbol, kiểu dữ liệu, phạm vi, vị trí khai báo và metadata liên quan.

Ví dụ:

| Tên | Loại symbol | Kiểu hoặc ý nghĩa | Phạm vi |
|---|---|---|---|
| `order` | Domain object | Đơn hàng hiện tại | Rule |
| `customer` | Domain object | Khách hàng liên quan | Rule |
| `MIN_TOTAL` | Constant | Money | Module |
| `isEligible` | Function | `(Customer) -> Boolean` | Imported module |

Phạm vi có thể là toàn chương trình, module, rule, block hoặc biểu thức. Quy tắc scope phải nhất quán để người dùng biết tên nào có thể truy cập tại vị trí đang viết. Với DSL cấu hình, có thể không cần biến và scope phức tạp; với DSL biểu thức hoặc quy tắc, symbol table thường là thành phần quan trọng.

### Kiểm tra kiểu và kiểu miền

Ngoài kiểu cơ bản như String, Boolean, Integer và Decimal, DSL có thể cần kiểu chuyên miền như Money, Percentage, Date, Duration, Distance hoặc CustomerId. Kiểu miền giúp ngăn các phép toán vô nghĩa.

Ví dụ, cộng hai giá trị Money cùng loại tiền có thể hợp lệ; cộng Money với Duration thường không hợp lệ. So sánh hai giá trị Money khác đơn vị tiền tệ có thể yêu cầu chuyển đổi rõ ràng. Kiểm tra kiểu nên xác định những phép toán nào được hỗ trợ và cách xử lý giá trị null hoặc thiếu dữ liệu.

## Diagnostics: lỗi và cảnh báo có ích

Frontend cần báo lỗi sao cho người viết DSL có thể hiểu điều gì xảy ra và sửa ở đâu. Một thông báo tốt thường có:

- Mã hoặc loại lỗi ổn định để IDE và công cụ tự động xử lý.
- Vị trí nguồn chính xác.
- Mô tả ngắn về vấn đề.
- Thông tin mong đợi và giá trị thực tế nếu phù hợp.
- Gợi ý sửa khi có thể xác định an toàn.
- Vị trí liên quan, chẳng hạn nơi symbol được khai báo hoặc macro được định nghĩa.

Ví dụ:

```text
discount.dsl:12:18: error DSL-TYPE-004
Cannot compare Money with String.
Expected: Money
Found: String
Hint: Use a numeric money literal, for example 1000000 VND.
```

Thông báo minh họa trên cần phù hợp với kiểu và cú pháp thực tế của DSL. Không nên đưa gợi ý sửa sai hoặc tự động sửa nếu ngữ nghĩa chưa rõ.

### Phục hồi lỗi cú pháp

Parser có thể dừng ngay khi gặp lỗi đầu tiên hoặc cố gắng phục hồi để phát hiện thêm lỗi trong cùng một lần chạy. Một kỹ thuật phổ biến là *panic-mode recovery*: bỏ qua token đến một điểm đồng bộ như dấu `;`, từ khóa bắt đầu rule tiếp theo hoặc dấu đóng block.

Ví dụ, nếu một rule thiếu `THEN`, parser có thể báo lỗi rồi tìm từ khóa `RULE` kế tiếp để tiếp tục phân tích rule sau. Việc phục hồi cần thận trọng để không tạo ra hàng loạt lỗi giả do một lỗi ban đầu làm cấu trúc phía sau bị hiểu sai.

Frontend nên giới hạn số lỗi được báo trong một lần phân tích và phân biệt lỗi gốc với lỗi phát sinh từ phục hồi. Với editor, việc trả về AST một phần cùng diagnostics có thể hữu ích để tiếp tục tô màu cú pháp và hiển thị cấu trúc đang viết dở.

## Chuyển AST thành mô hình trung gian

Sau khi AST được phân tích và kiểm tra, frontend có thể chuyển nó thành IR hoặc một mô hình đã xác thực. IR thường biểu diễn các thao tác theo dạng ổn định, ít phụ thuộc cú pháp DSL và phù hợp với backend.

Ví dụ, một biểu thức DSL:

```text
WHEN order.total >= MIN_TOTAL
THEN shipment.fee = 0
```

Có thể được hạ xuống mô hình trung gian:

```text
Rule
  condition:
    Compare(GREATER_OR_EQUAL,
      LoadProperty(order, "total"),
      Constant(MIN_TOTAL))
  actions:
    Assign(LoadProperty(shipment, "fee"), Money(0, "VND"))
```

IR có thể làm rõ kiểu, đơn vị, tham chiếu đã phân giải và các phép chuyển đổi ngầm. Backend sau đó có thể diễn giải IR, sinh mã Java, sinh SQL hoặc chuyển thành cấu hình cho một hệ thống khác.

Không phải DSL nào cũng cần IR riêng. Nếu AST đã ổn định và backend đơn giản, có thể dùng AST làm đầu vào trực tiếp. IR hữu ích khi có nhiều backend, nhiều tối ưu hóa hoặc cần tách biệt ngữ nghĩa ngôn ngữ khỏi cách thực thi.

## Tích hợp tiền xử lý và frontend trong một pipeline

Các giai đoạn phải trao đổi thông tin theo hợp đồng rõ ràng. Một pipeline có thể được tổ chức như sau:

| Giai đoạn | Đầu vào | Đầu ra | Trách nhiệm chính |
|---|---|---|---|
| Source manager | URI, byte hoặc text | Source units | Đọc nguồn, encoding, vị trí và cache |
| Preprocessor | Source units, profile | Expanded source hoặc token stream | Include, macro, directive và source map |
| Lexer | Ký tự hoặc expanded source | Token stream | Nhận diện token và source span |
| Parser | Token stream | CST/AST | Kiểm tra cấu trúc ngữ pháp |
| Semantic analyzer | AST và symbol environment | AST đã phân giải hoặc diagnostics | Name resolution, type checking, quy tắc miền |
| Lowering | AST đã xác thực | IR | Chuẩn hóa thành mô hình cho backend |
| Backend | IR | Kết quả thực thi hoặc mã đích | Diễn giải, sinh mã hoặc tích hợp hệ thống |

Trong thực tế, source manager và diagnostics thường được dùng chung bởi nhiều giai đoạn. Parser có thể nhận trực tiếp source text nếu lexer được tích hợp; preprocessor có thể hoạt động trên token thay vì văn bản. Bảng trên mô tả ranh giới trách nhiệm, không bắt buộc mỗi dòng phải là một service hoặc module độc lập.

### Hợp đồng giữa các giai đoạn

Mỗi thành phần nên quy định:

- Định dạng đầu vào và đầu ra.
- Các lỗi có thể phát sinh và cách biểu diễn chúng.
- Quy tắc bảo toàn source location.
- Cách hủy tác vụ hoặc áp dụng giới hạn tài nguyên.
- Các giả định về trạng thái, cấu hình và phiên bản ngôn ngữ.

Ví dụ, preprocessor trả về expanded source nhưng không trả source map sẽ khiến diagnostics phía parser khó chỉ về tệp gốc. Parser trả AST không có source span sẽ làm việc gắn lỗi ngữ nghĩa với biểu thức trở nên khó khăn. Những hợp đồng này nên được xác định trước để tránh các thành phần tự phát triển quy ước không tương thích.

## Ví dụ pipeline hoàn chỉnh

Giả sử DSL dùng để khai báo quy tắc ưu đãi. Tệp chính:

```text
include "common/customer.dsl"
define MIN_TOTAL = 1000000

RULE "VIP discount"
WHEN order.total >= MIN_TOTAL
  AND customer.segment IS "VIP"
THEN discount.rate = 10%
```

Tệp `common/customer.dsl` có thể chứa khai báo mô hình hoặc hàm miền. Frontend xử lý theo các bước khái quát:

1. Source manager đọc tệp chính và tệp được tham chiếu, lưu ID và vị trí nguồn.
2. Preprocessor giải quyết include, kiểm tra vòng lặp và xử lý hằng số theo ngữ nghĩa đã định nghĩa.
3. Lexer nhận diện `RULE`, định danh, literal, toán tử và dấu phân cách.
4. Parser xác nhận cấu trúc rule, điều kiện và action rồi tạo AST.
5. Semantic analyzer phân giải `order`, `customer`, `MIN_TOTAL` và `discount`; kiểm tra kiểu Money, Percentage và Boolean.
6. Kiểm tra miền xác nhận quy tắc ưu đãi có được phép áp dụng cho loại đơn hàng và trạng thái hiện tại hay không.
7. Lowering chuyển AST đã xác thực thành IR cho backend.
8. Backend thực thi quy tắc hoặc sinh mã phù hợp với hệ thống đích.

Nếu `customer.segment` không tồn tại, lỗi nên chỉ ra vị trí tham chiếu trong tệp chính hoặc tệp include tương ứng. Nếu `MIN_TOTAL` có kiểu String trong khi `order.total` là Money, lỗi kiểu cần giải thích sự không tương thích. Nếu macro hoặc include làm phát sinh cấu trúc sai, diagnostics cần cung cấp cả vị trí nguồn gốc và chuỗi biến đổi liên quan.

## Bảo mật và giới hạn tài nguyên

Tiền xử lý và frontend thường xử lý nội dung do người dùng cung cấp hoặc tệp từ nhiều nguồn. Vì vậy, cần xem chúng như ranh giới đầu vào có thể chứa dữ liệu không tin cậy.

Các biện pháp thiết kế cần cân nhắc:

- Giới hạn kích thước tệp, tổng kích thước sau include và số lượng tệp được nạp.
- Giới hạn độ sâu include, macro expansion và số lượng token hoặc node AST.
- Phát hiện vòng lặp và ngăn mở rộng đệ quy không giới hạn.
- Kiểm soát thư mục gốc, đường dẫn và quyền đọc tệp; tránh path traversal.
- Không cho tiền xử lý tự do thực thi lệnh hệ điều hành hoặc truy cập mạng nếu không có yêu cầu và cơ chế kiểm soát rõ ràng.
- Hạn chế thời gian CPU và bộ nhớ cho parser, đặc biệt với biểu thức lồng sâu hoặc đầu vào cố ý gây tốn tài nguyên.
- Tránh đưa bí mật, nội dung nhạy cảm hoặc toàn bộ văn bản nguồn vào log lỗi không được bảo vệ.
- Không giả định rằng DSL chỉ có cấu hình nên không thể gây tác động nguy hiểm; backend có thể thực hiện hành động thật dựa trên nội dung đã phân tích.

Giới hạn nên được cấu hình rõ và diagnostics cần cho biết giới hạn nào bị vượt. Các kiểm tra bảo mật phải áp dụng xuyên suốt từ source manager đến backend, bởi frontend hợp lệ không đảm bảo hành động cuối cùng an toàn.

## Hiệu năng, cache và phân tích gia tăng

Với tệp nhỏ, có thể phân tích toàn bộ nguồn mỗi lần thay đổi. Khi DSL được dùng trong dự án lớn hoặc IDE, frontend cần cân nhắc cache và incremental parsing để giảm thời gian phản hồi.

### Cache kết quả tiền xử lý

Kết quả include hoặc macro expansion có thể được cache nếu đầu vào và môi trường không đổi. Cache key cần tính đến:

- Nội dung hoặc hash của nguồn.
- Phiên bản DSL và phiên bản preprocessor.
- Các tham số, macro và profile có ảnh hưởng đến kết quả.
- Phiên bản hoặc hash của mọi tệp phụ thuộc.
- Các tùy chọn cấu hình liên quan.

Nếu thiếu một phụ thuộc trong cache key, frontend có thể dùng kết quả cũ sau khi tệp include đã thay đổi. Cần lưu dependency graph để vô hiệu hóa cache khi một nguồn liên quan được cập nhật.

### Incremental parsing

IDE thường cần phân tích lại khi người dùng sửa một vùng nhỏ. Parser gia tăng có thể tái sử dụng các phần cấu trúc không bị ảnh hưởng, nhưng cần theo dõi phạm vi phụ thuộc và cách một thay đổi làm thay đổi token hoặc cấu trúc phía sau.

Không phải DSL nào cũng cần incremental parsing. Trước tiên nên có pipeline rõ ràng và đo thời gian thực tế. Nếu thời gian phân tích toàn bộ vẫn đáp ứng yêu cầu, cách làm đơn giản thường dễ bảo trì hơn. Khi cần tối ưu, có thể bắt đầu bằng cache source, cache module hoặc phân tích từng tệp trước khi triển khai parser gia tăng phức tạp.

## Hỗ trợ IDE và công cụ phát triển

Frontend có thể cung cấp nền tảng cho các tính năng giúp người viết DSL làm việc hiệu quả:

- Tô màu cú pháp dựa trên token và ngữ cảnh.
- Tự động hoàn thành từ khóa, tên miền và thuộc tính hợp lệ.
- Hiển thị lỗi và cảnh báo ngay khi nhập.
- Đi đến nơi khai báo symbol.
- Tìm tất cả nơi sử dụng một thuật ngữ hoặc biến.
- Đổi tên symbol có kiểm soát.
- Định dạng mã và giữ comment.
- Hiển thị AST hoặc kết quả tiền xử lý để hỗ trợ gỡ lỗi.
- Cung cấp tài liệu hoặc thông tin kiểu khi di chuột lên symbol.

Các chức năng này phụ thuộc vào việc frontend giữ được source location, symbol table, CST/AST và diagnostics có cấu trúc. Nếu chỉ tạo ra một chuỗi văn bản đã mở rộng rồi bỏ nguồn gốc, việc xây dựng công cụ IDE sẽ khó hơn nhiều.

Một giao diện frontend dành cho IDE thường cần hỗ trợ trạng thái nguồn chưa hoàn chỉnh. Khi người dùng đang gõ dở một biểu thức, parser có thể trả AST một phần và diagnostics tạm thời thay vì chỉ báo thất bại toàn bộ. Cần phân biệt diagnostics tạm thời trong lúc nhập với lỗi cuối cùng khi biên dịch hoặc triển khai.

## Kiểm thử tiền xử lý và frontend

Mỗi giai đoạn nên có kiểm thử phù hợp với trách nhiệm của nó, đồng thời cần kiểm thử tích hợp cho toàn pipeline.

### Kiểm thử lexer

Kiểm tra các chuỗi đầu vào và token mong đợi, bao gồm:

- Từ khóa và định danh gần giống nhau.
- Số nguyên, số thập phân, đơn vị và dấu âm.
- Chuỗi có escape, chuỗi rỗng và chuỗi chưa đóng.
- Comment, khoảng trắng, tab và xuống dòng.
- Unicode và ký tự không hợp lệ.
- Source span của token ở đầu dòng, cuối dòng và sau ký tự nhiều byte.

### Kiểm thử parser

Kiểm tra các chương trình hợp lệ, không hợp lệ, biểu thức lồng nhau, độ ưu tiên toán tử, dấu phân cách thiếu và khả năng phục hồi. Có thể dùng golden test để so sánh AST hoặc diagnostics mong đợi.

### Kiểm thử preprocessor

Các trường hợp quan trọng gồm include lồng nhau, include trùng lặp, đường dẫn không tồn tại, vòng lặp, macro lồng nhau, tham số sai, expansion vượt giới hạn và source map sau biến đổi.

### Kiểm thử ngữ nghĩa

Kiểm tra tên không tồn tại, tên trùng, sai scope, sai kiểu, chữ ký action không hợp lệ và vi phạm quy tắc miền. Nên có ví dụ xác nhận kết quả hợp lệ và lỗi mong đợi.

### Kiểm thử tích hợp

Chạy nguồn DSL từ đầu đến cuối, xác nhận AST/IR hoặc kết quả backend, đồng thời kiểm tra diagnostics trỏ về đúng tệp và vị trí gốc. Với các phép biến đổi nguồn, cần kiểm tra cả trường hợp lỗi phát sinh trong nội dung include hoặc macro expansion.

### Property-based và fuzz testing

Với lexer và parser, có thể sinh nhiều chuỗi đầu vào ngẫu nhiên hoặc biến thể từ chương trình hợp lệ để kiểm tra frontend không bị crash, treo hoặc tiêu thụ tài nguyên bất thường. Mục tiêu không chỉ là xác nhận đầu vào hợp lệ mà còn đảm bảo đầu vào sai được xử lý có kiểm soát.

## Những quyết định thiết kế cần được ghi trong đặc tả

Để frontend có hành vi nhất quán giữa các công cụ và phiên bản, đặc tả DSL nên ghi lại ít nhất:

| Nhóm quyết định | Câu hỏi cần trả lời |
|---|---|
| Nguồn | Nguồn đến từ đâu, encoding và quy tắc xuống dòng là gì? |
| Tiền xử lý | Có include, import, macro, hằng số hoặc điều kiện không? |
| Đường dẫn | Cách phân giải đường dẫn và giới hạn truy cập ra sao? |
| Token | Từ khóa, định danh, literal, comment và toán tử được định nghĩa thế nào? |
| Ngữ pháp | Cấu trúc hợp lệ, precedence và associativity là gì? |
| AST/CST | Thông tin nào được giữ để phục vụ ngữ nghĩa, IDE và định dạng? |
| Ngữ nghĩa | Tên, scope, kiểu và quy tắc miền được kiểm tra ra sao? |
| Diagnostics | Mã lỗi, vị trí, phục hồi và gợi ý sửa được tổ chức thế nào? |
| Giới hạn | Kích thước, độ sâu, số token và thời gian xử lý tối đa là bao nhiêu? |
| Tương thích | Phiên bản ngôn ngữ và cách xử lý cú pháp cũ được quản lý thế nào? |

Các quyết định này giúp người viết DSL, người xây dựng frontend và người phát triển backend cùng hiểu một chương trình sẽ được phân tích theo quy tắc nào.

## Kết luận

Tiền xử lý và frontend tạo thành phần tiếp nhận và phân tích đầu vào của DSL. Tiền xử lý chuẩn bị nguồn bằng các phép biến đổi được quy định rõ; lexer và parser nhận diện token, cấu trúc cú pháp và tạo AST; phân tích ngữ nghĩa kiểm tra tên, kiểu và quy tắc miền; sau đó frontend có thể tạo IR cho backend.

Chất lượng của pipeline phụ thuộc vào ranh giới trách nhiệm rõ ràng, source location được bảo toàn, diagnostics dễ hiểu, giới hạn tài nguyên hợp lý và kiểm thử từng giai đoạn. Một frontend được thiết kế tốt giúp DSL vừa có thể được xử lý chính xác bởi máy vừa hỗ trợ người dùng viết, đọc, sửa và gỡ lỗi chương trình một cách hiệu quả.
