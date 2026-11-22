# Giá trị literal

## 1. Giá trị literal là gì?

Trong ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), **giá trị literal** là giá trị được viết trực tiếp trong văn bản nguồn. Khi đọc một chương trình DSL, parser nhận diện phần văn bản đó như một giá trị cụ thể, thay vì xem nó là tên biến, tên thuộc tính hoặc một biểu thức cần tra cứu.

Ví dụ:

~~~text
promotion "Gold member"
  discount 10
  minimum_order 2000000
  enabled true
  expires_on 2026-12-31
~~~

Trong ví dụ minh họa này:

- Gold member là literal chuỗi.
- 10 và 2000000 là literal số.
- true là literal Boolean.
- 2026-12-31 có thể được định nghĩa là literal ngày.

Các giá trị được viết trực tiếp giúp mô tả DSL dễ đọc và tự chứa. Tuy nhiên, một chuỗi ký tự trông giống số hoặc ngày chưa chắc đã mang kiểu số hoặc ngày. Ý nghĩa của literal phụ thuộc vào grammar, kiểu dữ liệu và quy tắc ngữ nghĩa mà DSL quy định.

Ví dụ, 2026-12-31 có thể được lexer nhận thành một literal ngày duy nhất, hoặc được phân tích thành phép trừ giữa ba số nếu grammar không dành riêng cú pháp ngày. Vì vậy, DSL phải xác định rõ cách nhận diện và diễn giải từng dạng literal.

## 2. Phân biệt literal, identifier và expression

Ba khái niệm thường xuất hiện cạnh nhau:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Literal | Giá trị được viết trực tiếp | 100, "ACTIVE", true |
| Identifier | Tên dùng để tham chiếu một thành phần đã được khai báo hoặc định nghĩa | customer, order_total, GOLD |
| Expression | Cấu trúc kết hợp literal, identifier, toán tử hoặc lời gọi hàm để tạo ra một giá trị | order_total >= 1000000 |

Xét biểu thức:

~~~text
order_total >= 1000000
~~~

order_total là identifier tham chiếu thuộc tính trong ngữ cảnh hiện tại; >= là toán tử; 1000000 là literal số. Toàn bộ biểu thức tạo ra một giá trị Boolean.

Một tên như GOLD có thể là identifier tham chiếu một hằng hoặc enum đã khai báo, nhưng cũng có thể được DSL định nghĩa là literal enum không cần khai báo riêng. Cần quyết định rõ để người dùng biết khi nào phải đặt tên trong dấu nháy và khi nào dùng tên định danh.

Literal thường không có danh tính độc lập. Hai lần xuất hiện của literal 10 thường biểu diễn cùng một giá trị số. Ngược lại, hai identifier giống nhau có thể tham chiếu đến cùng một biến, thuộc tính hoặc thành phần được định nghĩa trong phạm vi.

## 3. Vai trò của literal trong từ vựng DSL

Literal là một phần quan trọng của vocabulary vì chúng xuất hiện trong điều kiện, cấu hình, chính sách và hành động. Một thiết kế tốt cần xác định:

- Những loại giá trị nào người dùng được viết trực tiếp.
- Ký hiệu nào dùng để nhận diện mỗi loại.
- Kiểu dữ liệu của giá trị sau khi phân tích.
- Giới hạn và quy tắc hợp lệ của từng kiểu.
- Cách biểu diễn giá trị đặc biệt như null, ngày giờ hoặc đơn vị đo.
- Cách báo lỗi khi literal sai cú pháp hoặc không hợp lệ trong ngữ cảnh.

Không nên thêm nhiều dạng literal chỉ vì parser có thể nhận diện chúng. Mỗi dạng cần có ý nghĩa nghiệp vụ và cách xử lý rõ ràng. Ví dụ, nếu miền chỉ làm việc với ngày lịch, không nhất thiết phải hỗ trợ mọi dạng timestamp và timezone của một nền tảng.

## 4. Các nhóm literal phổ biến

### 4.1 Literal số nguyên

Literal số nguyên biểu diễn một giá trị không có phần thập phân:

~~~text
0
12
2000000
-5
~~~

DSL cần quyết định:

- Có cho phép dấu âm không?
- Có cho phép dấu cộng ở đầu không?
- Có cho phép dấu phân cách hàng nghìn không?
- Có cho phép dấu gạch dưới để dễ đọc không?
- Giới hạn giá trị là gì?
- Giá trị được lưu bằng kiểu số nguyên nào?

Nếu hỗ trợ dấu phân cách, cần quy định chính xác vị trí hợp lệ. Ví dụ, 2_000_000 có thể được chấp nhận trong DSL kỹ thuật, trong khi 2,000,000 dễ gây nhầm lẫn với dấu thập phân ở một số locale.

Số 0 ở đầu cũng cần quy định. Chuỗi 0012 có thể được hiểu là số 12, một mã có các số 0 đầu, hoặc một dạng literal không hợp lệ. Nếu giá trị là mã bưu chính, mã tài khoản hoặc mã sản phẩm, nên dùng string thay vì integer để giữ số 0 đầu và không thực hiện phép toán số học.

### 4.2 Literal số thập phân

Literal thập phân biểu diễn giá trị có phần lẻ:

~~~text
0.5
12.75
1000000.00
-0.25
~~~

DSL cần định nghĩa dấu thập phân và cách viết. Đối với ngôn ngữ cấu hình hoặc file được trao đổi giữa nhiều hệ thống, dấu chấm thường dễ chuẩn hóa hơn dấu phẩy. Không nên để cách viết phụ thuộc vào thiết lập vùng của máy đang chạy parser.

Không phải mọi kiểu số đều có cùng độ chính xác. Số thực dấu phẩy động có thể không biểu diễn chính xác nhiều phân số thập phân. Ví dụ, một phép tính tiền tệ dùng binary floating point có thể tạo sai số làm tròn.

Nếu literal được dùng cho tiền, tỷ lệ hoặc số lượng cần độ chính xác, nên định nghĩa kiểu Decimal hoặc kiểu miền tương ứng. Parser nên giữ biểu diễn thập phân chính xác cho đến khi chuyển sang kiểu đích đã xác định, thay vì chuyển sớm sang double.

### 4.3 Literal dạng khoa học

Một số DSL kỹ thuật có thể hỗ trợ ký pháp khoa học:

~~~text
1.5e3
2E-4
~~~

Ký pháp này hữu ích cho số rất lớn hoặc rất nhỏ. Tuy nhiên, với DSL dành cho người làm nghiệp vụ, nó có thể khó đọc và không cần thiết. Nếu hỗ trợ, cần xác định chữ E viết hoa hay viết thường, dấu số mũ, giới hạn exponent và kiểu dữ liệu kết quả.

### 4.4 Literal Boolean

Boolean biểu diễn hai giá trị logic:

~~~text
true
false
~~~

Nên chọn một cách viết nhất quán. Nếu DSL phân biệt chữ hoa chữ thường, TRUE hoặc True có thể không hợp lệ. Nếu không phân biệt, lexer cần chuẩn hóa cách nhận diện.

Không nên dùng các chuỗi như yes, no, on, off, 1 hoặc 0 thay cho Boolean trừ khi có lý do nghiệp vụ rõ ràng. Việc chấp nhận quá nhiều biến thể làm grammar khó đoán và dễ tạo khác biệt giữa các công cụ.

### 4.5 Literal chuỗi

Chuỗi biểu diễn văn bản:

~~~text
"Gold member"
'Gold member'
"Customer's order"
~~~

DSL cần chọn dấu nháy đơn, nháy kép hoặc cả hai. Nếu hỗ trợ cả hai, phải quy định cách thoát dấu nháy bên trong và cách chuẩn hóa.

Ví dụ với dấu nháy kép:

~~~text
message "Customer said: \"Approved\""
path "C:\\policies\\gold.dsl"
~~~

Các escape sequence thường gặp:

| Escape | Ý nghĩa |
|---|---|
| \\" | Dấu nháy kép |
| \\' | Dấu nháy đơn nếu DSL quy định |
| \\\\ | Dấu gạch chéo ngược |
| \\n | Xuống dòng |
| \\r | Carriage return |
| \\t | Tab |
| \\uXXXX | Ký tự Unicode theo dạng mã hóa được quy định |

Không nên mặc định mọi escape của Java, JSON hoặc ngôn ngữ chủ đều được hỗ trợ trong DSL. Grammar và tài liệu phải nêu rõ tập escape hợp lệ. Escape không hợp lệ cần tạo diagnostic tại vị trí phù hợp.

### 4.6 Literal chuỗi nhiều dòng

Một số DSL cho phép chuỗi nhiều dòng để viết nội dung dài:

~~~text
description """
  Discount applies to eligible members.
  It cannot be combined with other offers.
"""
~~~

Nếu hỗ trợ, cần quy định:

- Dấu mở và đóng chuỗi.
- Cách biểu diễn dấu kết thúc bên trong nội dung.
- Có giữ nguyên xuống dòng hay chuẩn hóa về LF không.
- Có loại bỏ khoảng trắng đầu dòng hay không.
- Có cho phép nội suy biểu thức hay không.

Đừng tự động loại bỏ khoảng trắng nếu nội dung có ý nghĩa định dạng, chẳng hạn template email, biểu mẫu hoặc đoạn mã.

### 4.7 Literal null hoặc giá trị vắng mặt

null thường biểu diễn việc không có giá trị hoặc một giá trị chưa được xác định:

~~~text
middle_name = null
~~~

Nhưng null không nhất thiết đồng nghĩa với:

- Thuộc tính không xuất hiện trong tài liệu.
- Chuỗi rỗng.
- Số 0.
- false.
- Giá trị chưa được người dùng nhập.
- Không áp dụng trong ngữ cảnh hiện tại.

DSL cần định nghĩa null có phải một literal riêng, kiểu nào cho phép null và các phép toán xử lý null ra sao.

Đặc biệt, cần phân biệt thuộc tính bị thiếu với thuộc tính có giá trị null nếu DSL dùng cho cấu hình hoặc dữ liệu JSON. Một cấu hình không khai báo timeout có thể yêu cầu dùng giá trị mặc định; timeout: null có thể mang nghĩa tắt timeout hoặc không xác định. Hai trường hợp chỉ giống nhau khi hợp đồng quy định như vậy.

### 4.8 Literal ngày, giờ và thời điểm

Ngày lịch có thể viết theo ISO 8601:

~~~text
2026-12-31
~~~

Thời điểm có timezone:

~~~text
2026-12-31T23:59:59Z
2026-12-31T23:59:59+07:00
~~~

Ngày lịch (LocalDate), giờ địa phương (LocalTime), ngày giờ địa phương (LocalDateTime) và thời điểm tuyệt đối (Instant) là các kiểu khác nhau. Không nên gộp tất cả thành một chuỗi rồi để backend tự suy đoán.

Khi thiết kế literal thời gian, cần xác định:

- Format được chấp nhận.
- Có bắt buộc timezone không.
- Độ chính xác phần giây.
- Cách xử lý ngày không tồn tại, ví dụ ngày 30 của tháng 2.
- Quy tắc khi chuyển đổi giữa local time và instant.
- Múi giờ mặc định nếu được phép bỏ qua.

Với lịch nghiệp vụ như ngày hết hạn, có thể chỉ cần literal ngày. Với thời điểm sự kiện phân tán, nên yêu cầu timezone hoặc offset để tránh phụ thuộc môi trường.

### 4.9 Literal thời lượng

Thời lượng có thể được viết với đơn vị:

~~~text
30 seconds
15 minutes
2 hours
7 days
~~~

Đơn vị giúp người đọc hiểu ý nghĩa và tránh nhầm giữa số 30 là giây, phút hay ngày. DSL cần định nghĩa danh sách đơn vị, cách viết số nhiều, quy tắc chuyển đổi và việc làm tròn.

Không nên xem month và year là số ngày cố định nếu miền cần xử lý lịch. Một tháng lịch có độ dài thay đổi; một năm lịch cũng có thể có 365 hoặc 366 ngày. Hãy phân biệt Duration (khoảng thời gian đo được) với Period (khoảng thời gian theo lịch) nếu nghiệp vụ cần.

### 4.10 Literal tiền tệ và phần trăm

Trong miền thương mại, literal có đơn vị thường rõ ràng hơn số trần:

~~~text
2000000 VND
19.99 USD
10 percent
0.15%
~~~

DSL cần định nghĩa:

- Mã tiền tệ và danh sách mã hợp lệ.
- Quy tắc số chữ số thập phân theo đơn vị tiền.
- Có cho phép ký hiệu tiền tệ hay chỉ mã ISO không.
- Phần trăm được lưu dưới dạng 10 hay 0.10.
- Quy tắc làm tròn khi tính toán.
- Có cho phép cộng hoặc so sánh hai giá trị khác đơn vị không.

Không nên tự động so sánh 100 USD với 2.000.000 VND nếu chưa có quy tắc tỷ giá và thời điểm quy đổi. Kiểu Money nên giữ cả amount và currency.

### 4.11 Literal enum và trạng thái

Một miền có thể dùng tập giá trị hữu hạn:

~~~text
status = ACTIVE
member_tier = GOLD
~~~

Các giá trị ACTIVE và GOLD có thể là enum literal hoặc identifier đã khai báo. Cần xác định:

- Danh sách giá trị hợp lệ.
- Phân biệt chữ hoa chữ thường hay không.
- Có cho phép alias không.
- Cách xử lý giá trị đã bị ngừng hỗ trợ.
- Cách mở rộng enum mà không phá vỡ file cũ.

Nếu giá trị là một nhãn văn bản tùy ý, hãy dùng string literal. Nếu nó thuộc tập giá trị miền được kiểm soát, enum giúp phát hiện lỗi gõ sai và hỗ trợ tự động hoàn thành tốt hơn.

### 4.12 Literal collection và object

Một số DSL cho phép viết danh sách hoặc object trực tiếp:

~~~text
supported_currencies = ["VND", "USD", "EUR"]
limits = {
  daily: 5,
  monthly: 20
}
~~~

Grammar cần xác định dấu phân cách, dấu phẩy cuối, khóa trùng, thứ tự phần tử và kiểu của từng phần tử. Nếu object có schema riêng, semantic analyzer cần kiểm tra khóa bắt buộc, khóa không được hỗ trợ và kiểu giá trị.

Không nên cho phép collection hoặc object lồng sâu không giới hạn nếu DSL không cần. Giới hạn kích thước và độ sâu giúp tránh lỗi tài nguyên và giữ cấu trúc dễ đọc.

## 5. Cú pháp literal và quy tắc lexical

Lexer thường nhận diện literal thông qua pattern token. Parser sau đó sử dụng token để xây dựng AST.

Một grammar giản lược có thể mô tả:

~~~text
literal
    : integerLiteral
    | decimalLiteral
    | stringLiteral
    | booleanLiteral
    | nullLiteral
    | dateLiteral
    | durationLiteral
    ;

booleanLiteral
    : "true"
    | "false"
    ;

nullLiteral
    : "null"
    ;

integerLiteral
    : DIGIT+
    ;

decimalLiteral
    : DIGIT+ "." DIGIT+
    ;
~~~

Đây chỉ là grammar minh họa. Grammar thực tế phải xử lý xung đột token, dấu âm, exponent, escape và các literal có hậu tố đơn vị.

### 5.1 Ưu tiên token dài nhất

Lexer thường cần áp dụng quy tắc longest match để nhận diện token dài nhất hợp lệ. Ví dụ, nếu DSL có toán tử >= và >, ký tự >= phải được nhận là một token thay vì hai token > và =.

Tương tự, nếu có literal ngày bắt đầu bằng chữ số và dấu gạch ngang, lexer cần phân biệt cú pháp ngày với phép trừ theo quy tắc grammar.

### 5.2 Dấu âm là một phần literal hay toán tử?

Trong nhiều ngôn ngữ, -5 được phân tích thành toán tử unary minus áp dụng lên literal 5, thay vì một token số âm duy nhất. Hai cách đều có thể dùng, nhưng cần nhất quán.

Nếu dấu âm là toán tử, grammar có thể biểu diễn:

~~~text
unaryExpression
    : "-" unaryExpression
    | primaryExpression
    ;
~~~

Điều này giúp xử lý biểu thức -a hoặc -(x + 1) thống nhất. Nếu DSL chỉ cho phép số âm ở dạng literal, có thể dùng token số có dấu nhưng sẽ hạn chế biểu thức.

### 5.3 Phân biệt literal với dấu phân cách

Trong cú pháp số, dấu chấm hoặc dấu phẩy có thể mang nhiều ý nghĩa. DSL cần chọn một quy tắc ổn định:

- Dấu chấm làm dấu thập phân.
- Dấu phẩy phân tách phần tử collection hoặc đối số.
- Dấu gạch dưới có thể phân tách nhóm chữ số nếu được hỗ trợ.
- Không phụ thuộc locale của máy người dùng.

Ví dụ, 1,234 có thể bị hiểu là một nghìn hai trăm ba mươi bốn hoặc hai giá trị 1 và 234. Tránh cú pháp mơ hồ bằng cách dùng dấu chấm thập phân và dấu phẩy phân cách theo một grammar rõ ràng.

## 6. Từ văn bản literal đến giá trị có kiểu

Một literal thường đi qua các bước:

1. Lexer nhận diện chuỗi ký tự và tạo token.
2. Parser tạo node literal trong AST.
3. Bộ chuyển đổi đọc biểu diễn văn bản và tạo giá trị tương ứng.
4. Semantic analyzer xác nhận kiểu và ngữ cảnh sử dụng.
5. IR hoặc mô hình miền lưu giá trị đã được chuẩn hóa.
6. Interpreter hoặc backend sử dụng giá trị đó.

Ví dụ với literal tiền:

~~~text
minimum_order >= 2000000 VND
~~~

Lexer có thể nhận 2000000 là NUMBER và VND là identifier hoặc UNIT token. Parser tạo một biểu thức có literal số kèm đơn vị. Semantic analyzer xác nhận VND là mã tiền hợp lệ và toán hạng bên trái có kiểu Money tương thích. Sau đó mô hình miền tạo Money(2000000, VND).

Không nên để mỗi backend tự đọc lại văn bản 2000000 VND. Nếu Java backend và SQL backend tự diễn giải, chúng có thể dùng kiểu số hoặc cách quy đổi khác nhau. Hãy chuẩn hóa giá trị trước khi chuyển đến backend.

### 6.1 Giữ độ chính xác khi parse

Nếu literal thập phân được dùng cho tiền hoặc tỷ lệ, tránh chuyển qua kiểu dấu phẩy động nhị phân quá sớm. Có thể giữ phần chữ số hoặc tạo BigDecimal từ chuỗi nguồn:

~~~java
BigDecimal amount = new BigDecimal("1234.56");
~~~

Không nên tạo BigDecimal từ một double đã có sai số:

~~~java
BigDecimal amount = new BigDecimal(1234.56);
~~~

Hai cách có thể tạo kết quả khác nhau do biểu diễn nhị phân của double. Quy tắc này đặc biệt quan trọng khi literal được dùng trong điều kiện ngưỡng, tính tiền hoặc tỷ lệ.

### 6.2 Kiểm tra kiểu theo ngữ cảnh

Một literal có thể hợp lệ về cú pháp nhưng không phù hợp với vị trí sử dụng:

~~~text
minimum_order = "two million"
~~~

Nếu minimum_order yêu cầu Money, string literal không hợp lệ dù chuỗi được viết đúng. Semantic analyzer cần báo lỗi kiểu thay vì để lỗi xuất hiện muộn trong backend.

Các kiểm tra thường cần có:

- Kiểu literal có tương thích với thuộc tính hoặc tham số không?
- Giá trị có nằm trong miền cho phép không?
- Đơn vị có tương thích không?
- Giá trị có cần chuyển đổi tường minh không?
- Có thể suy luận kiểu mà không gây mơ hồ không?

### 6.3 Phân biệt lỗi cú pháp và lỗi giá trị

Ví dụ:

- 12..5 có thể là lỗi cú pháp số.
- 999999999999999999999999 có thể vượt giới hạn kiểu đích.
- 2026-02-30 có dạng ngày nhưng là ngày không tồn tại.
- 10 XYZ có thể đúng cấu trúc số kèm đơn vị nhưng XYZ không được hỗ trợ.

Nên tạo mã lỗi riêng cho từng nhóm. Người dùng cần biết họ phải sửa cách viết, chọn giá trị khác hay dùng đơn vị hợp lệ.

## 7. Literal và kiểu dữ liệu miền

DSL nên dùng kiểu dữ liệu phản ánh ý nghĩa miền thay vì chỉ dựa vào kiểu nguyên thủy.

Ví dụ:

| Literal nguồn | Kiểu nguyên thủy có thể gặp | Kiểu miền phù hợp |
|---|---|---|
| 2000000 VND | Decimal hoặc integer | Money |
| 10 percent | Decimal | Percentage hoặc Rate |
| 2026-12-31 | String | LocalDate |
| 30 minutes | Integer | Duration |
| GOLD | String hoặc enum name | CustomerTier |
| ACTIVE | String | AccountStatus |
| null | null reference | Optional/nullable type theo ngữ nghĩa |

Kiểu miền giúp giới hạn phép toán hợp lệ. Ví dụ, cộng hai Money cùng currency có thể hợp lệ; cộng Money với Duration không có ý nghĩa. So sánh hai LocalDate có thể hợp lệ; cộng hai ngày có thể không hợp lệ nếu DSL chưa định nghĩa phép toán.

### 7.1 Chuyển đổi tường minh

Nếu người dùng cần chuyển kiểu, nên cung cấp cú pháp rõ:

~~~text
parse_date("2026-12-31")
to_money(2000000, VND)
percent(10)
~~~

Không nên tự chuyển mọi string thành số hoặc ngày dựa trên nội dung. Chuyển đổi ngầm có thể khiến một chuỗi mã như "0012" bị hiểu thành số 12, hoặc một ngày bị diễn giải theo locale khác.

### 7.2 Literal có đơn vị

Một giá trị có đơn vị có thể được xem là một literal ghép:

~~~text
distance = 5 km
timeout = 30 seconds
discount = 10 percent
price = 100 USD
~~~

DSL cần xác định:

- Danh sách đơn vị được hỗ trợ.
- Đơn vị chuẩn nội bộ.
- Quy tắc chuyển đổi và độ chính xác.
- Đơn vị có thể bỏ qua trong trường hợp nào.
- Có cho phép cộng hoặc so sánh khác đơn vị không.

Đơn vị nên được xử lý ở lớp ngữ nghĩa hoặc kiểu miền, không nên chỉ xóa hậu tố rồi dùng số trần.

## 8. Chuẩn hóa và tuần tự hóa literal

Một giá trị có thể có nhiều cách viết tương đương:

~~~text
1000
1_000
1000.0
~~~

Tùy kiểu và quy tắc, các cách viết trên có thể biểu diễn cùng một giá trị hoặc khác nhau về scale. DSL cần quyết định khi nào chúng tương đương.

**Canonical form** là cách biểu diễn chuẩn để lưu, so sánh hoặc sinh đầu ra. Ví dụ, một ngày có thể luôn được xuất theo YYYY-MM-DD; một thời điểm có thể được chuẩn hóa thành UTC; một mã enum có thể được xuất bằng chữ hoa.

Chuẩn hóa cần giữ nguyên ý nghĩa:

- Không bỏ số 0 đầu nếu giá trị là mã định danh.
- Không đổi currency nếu chưa có quy tắc quy đổi.
- Không làm tròn decimal nếu nghiệp vụ yêu cầu giữ scale.
- Không thay đổi timezone mà không giữ đúng instant.
- Không chuẩn hóa chuỗi theo cách làm mất ký tự có ý nghĩa.

Nếu DSL hỗ trợ serialize và deserialize, cần kiểm tra round-trip: parse nguồn, serialize mô hình, parse lại và xác nhận giá trị cũng như ngữ nghĩa không thay đổi.

## 9. Literal trong các ngữ cảnh khác nhau

Cùng một cách viết có thể mang ý nghĩa khác nhau tùy vị trí, nhưng nên tránh sự mơ hồ không cần thiết.

Ví dụ:

~~~text
retry_count = 3
timeout = 3 seconds
discount = 3 percent
status = 3
~~~

Ba giá trị đầu có thể có kiểu integer, duration và percentage; giá trị cuối có thể không hợp lệ nếu status yêu cầu enum. Nếu DSL chỉ dùng số trần, người đọc không biết 3 biểu thị đơn vị nào.

Một literal string cũng có thể là tên hiển thị, mã định danh, pattern hoặc nội dung template. Cần tránh để cùng một kiểu string mang quá nhiều ý nghĩa ngầm.

Nếu ngữ cảnh quyết định kiểu, tài liệu phải nêu rõ. Ví dụ, trong trường minimum_order, literal số có thể được hiểu là VND theo mặc định. Tuy nhiên, mặc định theo ngữ cảnh có thể gây bất ngờ khi cùng một literal xuất hiện ở nơi khác. Với giá trị quan trọng, cú pháp có đơn vị tường minh thường an toàn hơn.

## 10. Locale, Unicode và ký tự đặc biệt

Literal có thể chứa ngôn ngữ tự nhiên, ký tự có dấu, emoji hoặc ký tự ngoài ASCII. Lexer và parser cần xử lý Unicode nhất quán.

Một số điểm cần quyết định:

- Encoding của file nguồn, thường nên là UTF-8.
- Có chuẩn hóa Unicode NFC hay không.
- Identifier có cho phép ký tự Unicode không.
- String literal có giữ nguyên dạng Unicode hay escape.
- Cách tính độ dài chuỗi: byte, code point hay UTF-16 code unit.
- Có cấm ký tự điều khiển hoặc ký tự vô hình không.

Không nên tự động lowercase hoặc normalize mọi chuỗi. Tên hiển thị và nội dung văn bản có thể phân biệt chữ hoa chữ thường hoặc cần giữ nguyên chính tả.

Đối với identifier và enum, quy tắc chuẩn hóa có thể chặt hơn string literal. Cần tránh hai tên nhìn giống nhau nhưng khác code point khiến người dùng khó phát hiện.

## 11. Literal trong grammar và parser

Khi định nghĩa grammar, cần xác định literal có thể xuất hiện ở đâu:

- Vế phải của phép gán.
- Đối số hàm.
- Phần tử của list.
- Giá trị thuộc tính object.
- Điều kiện so sánh.
- Giá trị mặc định.
- Nhãn hoặc metadata.

Một grammar đơn giản:

~~~text
expression
    : literal
    | identifier
    | functionCall
    | expression operator expression
    ;

literal
    : NUMBER
    | STRING
    | BOOLEAN
    | NULL
    | DATE
    | DURATION
    ;
~~~

Grammar thật cần xử lý precedence, associativity và các token có thể trùng dạng. Ví dụ, dấu trừ vừa là unary operator vừa là binary operator; dấu ngoặc kép có thể mở string; từ khóa true có thể không được phép làm identifier.

### 11.1 Vị trí nguồn và diagnostics

AST nên giữ vị trí bắt đầu và kết thúc của literal trong file nguồn. Khi giá trị vượt giới hạn hoặc không hợp kiểu, thông báo có thể chỉ ra chính xác literal cần sửa.

Ví dụ:

~~~text
minimum_order = 999999999999999999999999999999 VND
~~~

Diagnostic tốt có thể nêu rằng giá trị vượt giới hạn được hỗ trợ và chỉ vị trí của con số, thay vì chỉ báo lỗi parse chung.

### 11.2 Không dùng parser theo kiểu đoán nội dung

Tránh cách tiếp cận đọc mọi token thành string rồi thử parse theo thứ tự integer, decimal, date hoặc enum. Cách đoán này dễ tạo kết quả không ổn định khi một giá trị hợp lệ ở nhiều kiểu.

Hãy để grammar xác định dạng literal, sau đó semantic analyzer xác định kiểu và tính hợp lệ theo ngữ cảnh.

## 12. Kiểm thử literal

Mỗi nhóm literal cần có test cho cú pháp hợp lệ, cú pháp không hợp lệ, kiểu dữ liệu và giá trị biên.

### 12.1 Kiểm thử số

Các trường hợp cần xem xét:

- Số 0 và số âm.
- Số nguyên lớn nhất và vượt giới hạn.
- Số thập phân với nhiều chữ số.
- Exponent nếu được hỗ trợ.
- Dấu phân cách sai vị trí.
- Số có dấu thập phân nhưng thiếu phần nguyên hoặc phần lẻ.
- Giá trị có scale vượt giới hạn.

### 12.2 Kiểm thử chuỗi

- Chuỗi rỗng.
- Dấu nháy bên trong chuỗi.
- Escape hợp lệ và không hợp lệ.
- Unicode và ký tự có dấu.
- Chuỗi nhiều dòng.
- Ký tự điều khiển.
- Chuỗi dài vượt giới hạn.

### 12.3 Kiểm thử ngày giờ và đơn vị

- Ngày hợp lệ và ngày không tồn tại.
- Timestamp có Z hoặc offset.
- Thiếu timezone khi timezone bắt buộc.
- Thời lượng bằng 0 hoặc âm.
- Đơn vị không hỗ trợ.
- Chuyển đổi đơn vị có phần lẻ.
- Ranh giới ngày bắt đầu và ngày kết thúc.

### 12.4 Kiểm thử null và enum

- null tại vị trí cho phép và không cho phép.
- Thuộc tính bị thiếu so với thuộc tính có null.
- Enum đúng và sai chính tả.
- Khác biệt chữ hoa chữ thường.
- Enum cũ đã bị deprecate.

### 12.5 Kiểm thử round-trip

Nếu DSL có formatter hoặc serializer:

1. Parse literal thành giá trị có kiểu.
2. Serialize giá trị thành dạng chuẩn.
3. Parse lại dạng chuẩn.
4. So sánh kiểu và giá trị.
5. Kiểm tra ngữ nghĩa không thay đổi.

Không nhất thiết chuỗi nguồn phải giống hệt sau round-trip, vì formatter có thể chuẩn hóa khoảng trắng hoặc dấu nháy. Điều cần giữ là giá trị và ý nghĩa.

## 13. Những lỗi thiết kế thường gặp

### Dùng string cho mọi thứ

Nếu mọi literal đều trở thành String, lỗi kiểu chỉ xuất hiện muộn và backend phải tự chuyển đổi.

**Cách xử lý:** định nghĩa kiểu literal rõ ràng và thực hiện type checking trước khi thực thi.

### Dùng số thực cho tiền

Binary floating point có thể gây sai số trong phép tính và so sánh ngưỡng.

**Cách xử lý:** dùng Decimal hoặc Money với độ chính xác và quy tắc làm tròn được xác định.

### Phụ thuộc locale của máy

Một file có thể parse khác nhau trên máy dùng dấu phẩy thập phân và máy dùng dấu chấm.

**Cách xử lý:** quy định format cố định, độc lập locale, và chỉ chuyển đổi ở giao diện nhập/xuất nếu cần.

### Không phân biệt null và missing

Hai trạng thái có thể mang ý nghĩa khác nhau trong cấu hình và dữ liệu.

**Cách xử lý:** định nghĩa riêng cách biểu diễn thuộc tính vắng mặt và literal null.

### Cho phép quá nhiều dạng viết tương đương

Nhiều kiểu dấu nháy, Boolean, số và đơn vị làm tăng độ phức tạp của parser và tài liệu.

**Cách xử lý:** chọn một dạng mặc định, chỉ hỗ trợ alias khi có nhu cầu thực tế.

### Tự suy đoán kiểu theo nội dung

Chuỗi "0012" có thể bị biến thành số 12; chuỗi "2026-01-01" có thể bị hiểu thành ngày dù người dùng chỉ muốn văn bản.

**Cách xử lý:** dùng dấu nháy, hậu tố đơn vị hoặc cú pháp typed literal rõ ràng.

### Để backend tự diễn giải literal

Java và SQL có thể xử lý số, null và thời gian khác nhau.

**Cách xử lý:** parse và chuẩn hóa thành giá trị có kiểu trước khi chuyển sang backend.

## 14. Quy trình thiết kế literal cho một DSL

Có thể thực hiện theo các bước:

1. **Thu thập ví dụ miền:** tìm các giá trị người dùng thường khai báo, so sánh hoặc truyền vào thao tác.
2. **Nhóm theo ý nghĩa:** phân biệt số, văn bản, Boolean, thời gian, đơn vị, enum và cấu trúc dữ liệu.
3. **Chọn kiểu miền:** xác định kiểu dữ liệu phản ánh ý nghĩa, chẳng hạn Money, Percentage, LocalDate hoặc Duration.
4. **Thiết kế cú pháp:** quy định dấu nháy, dấu phân cách, hậu tố đơn vị và format ngày giờ.
5. **Định nghĩa giới hạn:** giá trị tối đa, độ chính xác, độ dài, độ sâu và tập giá trị hợp lệ.
6. **Định nghĩa ngữ nghĩa:** null, chuyển đổi, làm tròn, timezone và phép toán được phép.
7. **Thiết kế diagnostics:** chỉ rõ lỗi cú pháp, lỗi kiểu và lỗi giá trị.
8. **Kiểm thử parser và kiểu:** dùng ví dụ hợp lệ, không hợp lệ và trường hợp biên.
9. **Chuẩn hóa đầu ra:** xác định canonical form nếu DSL cần serialize hoặc so sánh phiên bản.
10. **Tài liệu hóa:** đưa ví dụ rõ ràng để người dùng biết cách viết và giới hạn.

Không cần hỗ trợ mọi loại literal ngay từ đầu. Hãy bắt đầu với các kiểu mà miền thực sự cần và mở rộng khi có ví dụ chứng minh nhu cầu.

## 15. Ví dụ tổng hợp

Giả sử DSL mô tả chính sách khuyến mãi:

~~~text
promotion "Gold member"
  enabled true
  member_tier GOLD
  minimum_order 2000000 VND
  discount 10 percent
  starts_on 2026-12-01
  ends_on 2026-12-31
  max_uses 1000
  description "Applies to verified gold members"
~~~

Một cách phân tích có thể là:

| Nguồn | Loại literal | Kiểu miền dự kiến | Kiểm tra |
|---|---|---|---|
| "Gold member" | String | PromotionName | Không rỗng, giới hạn độ dài |
| true | Boolean | Boolean | Chỉ true hoặc false |
| GOLD | Enum literal | CustomerTier | Phải thuộc tập hạng được hỗ trợ |
| 2000000 VND | Number + unit | Money | Giá trị không âm, currency hợp lệ |
| 10 percent | Number + unit | Percentage | Nằm trong miền cho phép |
| 2026-12-01 | Date | LocalDate | Ngày lịch hợp lệ |
| 2026-12-31 | Date | LocalDate | Không trước ngày bắt đầu |
| 1000 | Integer | PositiveCount | Phải lớn hơn 0 |
| "Applies to..." | String | Description | Quy tắc độ dài và ký tự |

Sau khi parse, semantic analyzer còn cần kiểm tra quan hệ giữa các giá trị:

- Ngày kết thúc không trước ngày bắt đầu.
- Phần trăm giảm nằm trong giới hạn chính sách.
- Hạng thành viên được định nghĩa.
- Đơn vị tiền phù hợp với chiến dịch.
- Số lượt sử dụng tối đa có ý nghĩa với loại chương trình.

Như vậy, literal không chỉ là token. Nó là đầu vào cho hệ thống kiểu và các quy tắc miền.

## 16. Câu hỏi tự kiểm tra

1. Phân biệt literal, identifier và expression.
2. Vì sao một chuỗi ký tự trông giống ngày chưa chắc đã là literal ngày?
3. Nêu các loại literal thường gặp trong DSL.
4. Vì sao cần phân biệt null với thuộc tính bị thiếu?
5. Những vấn đề nào cần được quy định khi hỗ trợ string escape?
6. Vì sao không nên dùng double cho literal tiền tệ?
7. Khi nào nên dùng enum literal thay cho string?
8. Literal có đơn vị giúp tránh nhầm lẫn như thế nào?
9. Phân biệt lỗi cú pháp, lỗi kiểu và lỗi giá trị.
10. Vì sao cần chuẩn hóa literal trước khi chuyển đến nhiều backend?
11. Round-trip test xác nhận điều gì?
12. Làm thế nào để thiết kế literal ngày giờ không phụ thuộc timezone mặc định của máy?

Khi thiết kế từ vựng DSL, hãy chọn literal theo ý nghĩa của miền, xác định kiểu và giới hạn ngay từ đầu, rồi kiểm tra chúng qua parser, semantic analyzer và backend. Một literal được định nghĩa rõ giúp mô tả dễ đọc, giảm chuyển đổi ngầm và giữ cùng một ý nghĩa trong toàn bộ hệ thống.
