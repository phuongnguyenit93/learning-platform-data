# Ký hiệu hướng người dùng trong DSL

Ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) được tạo ra để người dùng diễn đạt công việc bằng những khái niệm quen thuộc của một lĩnh vực. Một phần quan trọng quyết định DSL có dễ sử dụng hay không là **ký hiệu hướng người dùng** (*user-facing notation*): cách các khái niệm, quy tắc và thao tác được thể hiện ra bên ngoài để người dùng đọc, viết và trao đổi.

Ký hiệu hướng người dùng bao gồm từ khóa, tên định danh, toán tử, dấu phân cách, cách nhóm biểu thức, cách viết giá trị, quy tắc xuống dòng và những quy ước trình bày khác. Nó là bề mặt mà người dùng trực tiếp tiếp xúc. Phía sau bề mặt đó, hệ thống có thể phân tích văn bản thành cây cú pháp, mô hình trung gian hoặc cấu trúc dữ liệu để kiểm tra và thực thi.

Thiết kế ký hiệu không chỉ là chọn dấu ngoặc hay tên lệnh. Cần hiểu ai sẽ viết DSL, họ biết thuật ngữ nào, loại lỗi nào dễ xảy ra, nội dung có cần được đọc bởi người không phải lập trình viên hay không, và cú pháp sẽ được duy trì trong bao lâu. Một ký hiệu tốt giúp người dùng nhận ra ý nghĩa và dự đoán được hành vi; một ký hiệu tùy tiện có thể khiến DSL khó học, khó đọc và khó mở rộng.

## 1. Ký hiệu hướng người dùng là gì?

### 1.1. Phần bề mặt của ngôn ngữ

Ký hiệu hướng người dùng là cách một DSL biểu diễn nội dung ở dạng mà người dùng có thể đọc hoặc tạo ra. Ví dụ, một quy tắc giảm giá có thể được viết:

~~~text
rule WeekendDiscount {
    when order.day is Saturday or Sunday
    then apply discount 10%
}
~~~

Trong ví dụ này:

- **rule**, **when**, **then**, **is**, **or** là các từ khóa hoặc từ nối có ý nghĩa cú pháp.
- **WeekendDiscount** là tên định danh của quy tắc.
- **order.day** là cách tham chiếu đến một thuộc tính miền.
- **Saturday**, **Sunday** là các giá trị được DSL hiểu theo một kiểu dữ liệu.
- **10%** là một giá trị phần trăm.
- Dấu ngoặc nhọn và xuống dòng giúp nhóm phần điều kiện với phần hành động.

Người viết có thể đọc quy tắc này như một câu mô tả chính sách. Parser có thể chuyển nó thành AST, còn runtime thực hiện hành động theo ngữ nghĩa đã định nghĩa.

### 1.2. Phân biệt ký hiệu bên ngoài và biểu diễn bên trong

Một khái niệm miền có thể được trình bày theo nhiều cách. Ví dụ, người dùng viết:

~~~text
order.total >= 500000
~~~

Parser có thể tạo ra một node so sánh với hai toán hạng. Hệ thống không cần giữ nguyên cách viết ban đầu để đánh giá biểu thức; nó có thể dùng một cấu trúc nội bộ chuẩn hóa.

| Lớp | Vai trò | Ví dụ |
|---|---|---|
| Ký hiệu hướng người dùng | Cách người dùng viết và đọc | order.total >= 500000 |
| Cấu trúc cú pháp | Mô tả quan hệ giữa các thành phần | Node GreaterThan với hai toán hạng |
| Biểu diễn ngữ nghĩa | Mô tả ý nghĩa sau khi kiểm tra kiểu và miền | So sánh tổng đơn hàng với ngưỡng tiền |
| Cách thực thi | Thực hiện hoặc chuyển đổi biểu thức | Đánh giá trong runtime hoặc sinh điều kiện truy vấn |

Tách các lớp này giúp nhóm có thể cải thiện parser, tối ưu hoặc thay backend mà không nhất thiết phải thay đổi cú pháp người dùng đang sử dụng. Tuy nhiên, nếu ký hiệu bên ngoài thay đổi, nội dung DSL đã lưu có thể cần được chuyển đổi hoặc tiếp tục được hỗ trợ.

### 1.3. Ký hiệu văn bản và các dạng biểu diễn khác

DSL thường dùng văn bản, nhưng ký hiệu hướng người dùng không bắt buộc chỉ là văn bản thuần.

| Dạng biểu diễn | Cách người dùng tương tác | Ví dụ thường gặp |
|---|---|---|
| Văn bản | Gõ từ khóa, biểu thức và dấu phân cách | SQL, biểu thức chính quy, ngôn ngữ quy tắc |
| Cấu hình có cấu trúc | Điền trường, khóa và giá trị | YAML hoặc JSON được giới hạn theo schema miền |
| Bảng | Chỉnh sửa hàng và cột theo mẫu | Bảng điều kiện và hành động trong công cụ quy tắc |
| Trực quan | Nối khối, nút hoặc mũi tên | Trình thiết kế workflow hoặc sơ đồ quy trình |
| Kết hợp | Chỉnh sửa bằng giao diện và xem dạng văn bản | Trình soạn thảo có form, bảng và chế độ DSL text |

Các dạng biểu diễn có thể cùng mô tả một mô hình miền. Dù chọn dạng nào, cần định nghĩa một ngữ nghĩa nhất quán để nội dung được hiểu giống nhau.

## 2. Mục tiêu của ký hiệu hướng người dùng

### 2.1. Giúp người dùng diễn đạt đúng ý định

Người dùng thường nghĩ bằng các khái niệm của miền, chẳng hạn khách hàng, đơn hàng, hạn mức, vai trò hoặc thời hạn. Ký hiệu nên cho phép họ diễn đạt những khái niệm đó trực tiếp.

Ví dụ, trong DSL chính sách:

~~~text
when customer.tier is GOLD
and order.total >= 2000000
then grant freeShipping
~~~

Người dùng có thể nhận ra đây là điều kiện áp dụng giao hàng miễn phí cho khách hàng hạng GOLD khi đơn hàng đạt ngưỡng quy định.

Nếu cùng quy tắc phải viết bằng các chỉ số nội bộ, mã trường hoặc tên hàm khó hiểu, người dùng sẽ phải ghi nhớ thêm một lớp ánh xạ giữa nghiệp vụ và kỹ thuật.

### 2.2. Giảm tải nhận thức

Ký hiệu quen thuộc giúp người dùng dành sự chú ý cho nội dung nghiệp vụ thay vì phải giải mã cú pháp.

Ví dụ, toán tử so sánh **>=** thường quen thuộc với người đã học lập trình hoặc toán học. Nhưng với người dùng nghiệp vụ, cách viết **at least** hoặc **greater than or equal to** có thể dễ hiểu hơn.

Không có một cách viết tốt nhất cho mọi đối tượng. Một DSL dành cho kỹ sư dữ liệu có thể ưu tiên biểu thức ngắn và toán tử quen thuộc. Một DSL dành cho nhân viên vận hành có thể ưu tiên câu lệnh gần với ngôn ngữ tự nhiên và biểu mẫu có hướng dẫn.

### 2.3. Tạo tính nhất quán

Cùng một ý nghĩa nên được biểu diễn theo cùng một quy ước. Nếu DSL dùng **is** để so sánh trạng thái ở một nơi nhưng dùng **equals** ở nơi khác mà không có khác biệt ngữ nghĩa, người dùng phải học hai cách viết cho cùng một thao tác.

Tính nhất quán cần được giữ ở:

- Tên từ khóa và tên thuộc tính.
- Cách viết giá trị và đơn vị.
- Cách nhóm điều kiện.
- Cách biểu diễn hành động.
- Quy tắc đặt tên và namespace.
- Cách hiển thị lỗi và cảnh báo.

### 2.4. Hỗ trợ khám phá và học tập

Một ký hiệu tốt giúp người dùng khám phá khả năng của DSL. Tên hàm rõ ràng, gợi ý hoàn thành, ví dụ gần với nghiệp vụ và thông báo lỗi cụ thể đều hỗ trợ quá trình học.

Nếu DSL có nhiều chức năng, không nên yêu cầu người dùng nhớ toàn bộ danh sách từ khóa. Trình soạn thảo có thể cung cấp autocomplete, mô tả tham số, ví dụ và gợi ý theo ngữ cảnh.

### 2.5. Dễ đọc lại và trao đổi

DSL thường được lưu trong kho mã, cơ sở dữ liệu hoặc hệ thống quản lý quy tắc. Một người khác có thể đọc nó sau nhiều tháng hoặc nhiều năm.

Ký hiệu nên giúp người đọc hiểu:

- Quy tắc áp dụng cho đối tượng nào.
- Điều kiện nào phải đúng.
- Hành động nào sẽ xảy ra.
- Giá trị và đơn vị được sử dụng.
- Phần nào là tùy chọn và phần nào bắt buộc.

Tính dễ đọc lại quan trọng không kém tốc độ viết ban đầu. Cú pháp quá ngắn có thể tiết kiệm ký tự nhưng khiến người đọc phải đoán ý nghĩa.

## 3. Những thành phần cơ bản của ký hiệu

### 3.1. Từ khóa

Từ khóa là những từ có ý nghĩa đặc biệt trong cú pháp, ví dụ:

- **rule** để khai báo một quy tắc.
- **when** để bắt đầu điều kiện.
- **then** để bắt đầu hành động.
- **and**, **or**, **not** để kết hợp biểu thức logic.
- **true**, **false**, **null** để biểu diễn giá trị đặc biệt.

Từ khóa nên ngắn, nhất quán và tránh trùng với tên định danh phổ biến. Nếu DSL cho phép mở rộng từ khóa, cần có quy tắc namespace hoặc cơ chế tránh xung đột.

Không nên thêm từ khóa chỉ để làm cú pháp trông giống ngôn ngữ tự nhiên. Mỗi từ khóa nên có vai trò rõ và không gây hiểu lầm về ngữ nghĩa.

### 3.2. Tên định danh

Tên định danh (*identifier*) dùng để đặt tên cho quy tắc, biến, trường dữ liệu, hàm hoặc module.

Ví dụ:

~~~text
rule HighValueCustomer
let orderTotal = order.total
call finance.calculateTax(orderTotal)
~~~

Quy tắc đặt tên cần trả lời:

- Có phân biệt chữ hoa và chữ thường không?
- Có cho phép chữ số ở đầu tên không?
- Có cho phép dấu gạch dưới hoặc dấu gạch ngang không?
- Có hỗ trợ Unicode không?
- Tên có thể trùng từ khóa không?
- Tên dài tối đa bao nhiêu?
- Có quy ước đặt tên theo miền hoặc namespace không?

Tên nên phản ánh ý nghĩa của miền. **customerStatus** thường dễ hiểu hơn một tên mã hóa như **cst_st** nếu không có tài liệu giải thích.

### 3.3. Giá trị literal

Literal là giá trị được viết trực tiếp trong biểu thức. Các loại thường gặp gồm:

| Loại | Ví dụ | Lưu ý thiết kế |
|---|---|---|
| Số nguyên | 12, 1000 | Quy định dấu, dấu phân nhóm và phạm vi |
| Số thập phân | 12.5 | Quy định dấu thập phân và độ chính xác |
| Chuỗi | "Hồ Chí Minh" | Quy định dấu nháy và cách escape |
| Boolean | true, false | Tránh nhiều cách viết cho cùng giá trị |
| Ngày | 2026-11-15 | Quy định định dạng và múi giờ nếu có |
| Phần trăm | 10% | Xác định 10% được lưu là 0.1 hay 10 |
| Tiền tệ | 500000 VND | Gắn giá trị với đơn vị tiền |
| Giá trị rỗng | null | Quy định cách so sánh và lan truyền |

Định dạng literal cần nhất quán với cách người dùng nhập dữ liệu và với quy tắc lưu trữ. Ví dụ, nếu DSL cho phép dấu phẩy làm dấu thập phân trong một ngôn ngữ địa phương, parser phải phân biệt rõ dấu phẩy đó với dấu phân cách tham số.

### 3.4. Toán tử

Toán tử biểu diễn phép tính hoặc quan hệ giữa các giá trị.

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| Số học | +, -, *, / | Tính toán số |
| So sánh | ==, !=, <, <=, >, >= | So sánh hai giá trị |
| Logic | and, or, not | Kết hợp điều kiện |
| Thành viên | in, contains | Kiểm tra phần tử hoặc sự hiện diện |
| Phạm vi | between, within | Kiểm tra khoảng hoặc thời gian |
| Null | is null, is not null | Kiểm tra giá trị rỗng |

Không phải mọi toán tử đều phù hợp với mọi miền. Một DSL tài chính có thể cần toán tử so sánh tiền tệ nhưng không cho phép cộng hai giá trị khác đơn vị. Một DSL thời gian có thể cần **before**, **after** và **within** để diễn đạt rõ ràng.

### 3.5. Dấu phân cách và ký hiệu nhóm

Dấu ngoặc, dấu phẩy, dấu hai chấm và dấu chấm phẩy giúp xác định ranh giới cấu trúc.

Ví dụ:

~~~text
calculateTax(amount: 1000000, region: "VN")
~~~

Dấu ngoặc tròn nhóm tham số; dấu phẩy phân cách đối số; dấu hai chấm gắn tên tham số với giá trị.

Một số quy ước phổ biến:

- Dấu ngoặc tròn cho nhóm biểu thức hoặc danh sách tham số.
- Dấu ngoặc vuông cho danh sách hoặc chỉ mục.
- Dấu ngoặc nhọn cho khối khai báo.
- Dấu hai chấm cho ánh xạ tên với giá trị hoặc khai báo kiểu.
- Dấu chấm cho truy cập thuộc tính hoặc namespace.
- Dấu phẩy hoặc xuống dòng cho ranh giới phần tử.

Không nên dùng cùng một dấu cho nhiều vai trò khó phân biệt nếu người dùng thường xuyên phải đọc biểu thức phức tạp.

### 3.6. Khoảng trắng và xuống dòng

Khoảng trắng có thể chỉ dùng để phân tách token hoặc có thể mang ý nghĩa cú pháp.

Ví dụ, DSL có thể cho phép:

~~~text
when order.total > 1000000
and customer.tier is GOLD
~~~

hoặc:

~~~text
when order.total > 1000000 and customer.tier is GOLD
~~~

Nếu xuống dòng không có ý nghĩa, parser nên xử lý hai cách viết như nhau. Nếu xuống dòng dùng để kết thúc câu lệnh hoặc nhóm khối, quy tắc đó phải được công bố rõ ràng.

Việc dựa vào thụt lề có thể làm văn bản gọn và dễ đọc, nhưng cần quy định tab và dấu cách, cách xử lý dòng trống và lỗi thụt lề. Nếu người dùng thường sao chép nội dung qua nhiều công cụ, cú pháp phụ thuộc thụt lề cần được thiết kế cẩn thận.

### 3.7. Chú thích

Chú thích (*comment*) cho phép giải thích ý định mà không ảnh hưởng đến thực thi.

Ví dụ:

~~~text
# Áp dụng ưu đãi trong chiến dịch cuối tuần
rule WeekendDiscount {
    when order.day is Saturday or Sunday
    then apply discount 10%
}
~~~

DSL cần quy định cách bắt đầu chú thích, chú thích kéo dài đến đâu và có hỗ trợ chú thích nhiều dòng hay không. Nếu nội dung DSL được dùng làm tài liệu hoặc cần kiểm toán, chú thích có thể là một phần quan trọng của khả năng bảo trì.

## 4. Chọn phong cách ký hiệu

### 4.1. Ký hiệu gần ngôn ngữ tự nhiên

Ví dụ:

~~~text
when order total is at least 1000000
then apply free shipping
~~~

Ưu điểm:

- Gần với cách diễn đạt của chuyên gia miền.
- Dễ đọc với người không quen toán tử lập trình.
- Có thể trình bày quy tắc như một câu nghiệp vụ.

Hạn chế:

- Câu dài và có thể mơ hồ.
- Cần quy tắc ngữ pháp chặt chẽ để tránh nhiều cách hiểu.
- Khó hỗ trợ mọi cấu trúc biểu thức phức tạp.

Ngôn ngữ tự nhiên không tự động tạo ra cú pháp dễ hiểu. Nếu một câu có nhiều mệnh đề, ngoại lệ hoặc phủ định lồng nhau, người đọc vẫn có thể hiểu sai.

### 4.2. Ký hiệu toán học và lập trình

Ví dụ:

~~~text
order.total >= 1000000 && order.status == PAID
~~~

Ưu điểm:

- Ngắn gọn.
- Có quy ước quen thuộc với lập trình viên.
- Dễ kết hợp biểu thức và công cụ phân tích.

Hạn chế:

- Có thể khó đọc với người dùng nghiệp vụ.
- Một số ký hiệu có nhiều ý nghĩa trong các ngữ cảnh khác nhau.
- Người dùng phải hiểu thứ tự ưu tiên và kiểu dữ liệu.

Phong cách này phù hợp khi đối tượng sử dụng có nền tảng kỹ thuật hoặc biểu thức cần khả năng kết hợp cao.

### 4.3. Ký hiệu khai báo dạng khóa và giá trị

Ví dụ:

~~~yaml
rule:
  name: WeekendDiscount
  condition:
    field: order.day
    operator: in
    value:
      - Saturday
      - Sunday
  action:
    type: applyDiscount
    percent: 10
~~~

Ưu điểm:

- Cấu trúc rõ ràng.
- Dễ kiểm tra bằng schema.
- Phù hợp với công cụ tạo biểu mẫu và xử lý dữ liệu.

Hạn chế:

- Nhiều dòng và nhiều khóa.
- Biểu thức phức tạp có thể khó biểu diễn.
- Người dùng phải biết cấu trúc dữ liệu và quy tắc lồng nhau.

Định dạng YAML hoặc JSON chỉ trở thành một dạng DSL khi ứng dụng gán cho cấu trúc đó ngữ nghĩa miền cụ thể. Một tệp cấu hình thông thường chưa chắc là DSL.

### 4.4. Ký hiệu dạng bảng

Một quy tắc có thể được trình bày bằng bảng:

| Điều kiện | Toán tử | Giá trị | Hành động |
|---|---|---|---|
| order.total | lớn hơn hoặc bằng | 1.000.000 VND | Giao hàng miễn phí |
| customer.tier | bằng | GOLD | Áp dụng ưu đãi thành viên |

Bảng phù hợp với tập điều kiện có cấu trúc lặp lại và người dùng cần chỉnh sửa trực quan. Tuy nhiên, điều kiện lồng nhau, nhóm OR phức tạp hoặc hành động có nhiều bước có thể khiến bảng khó sử dụng.

### 4.5. Ký hiệu trực quan

Một trình thiết kế workflow có thể biểu diễn bước xử lý bằng các khối và mũi tên. Người dùng kéo nối các bước thay vì viết văn bản.

Ưu điểm là luồng xử lý được nhìn thấy trực tiếp. Hạn chế là sơ đồ lớn có thể khó bố trí, khó so sánh bằng diff văn bản và khó thao tác bằng bàn phím nếu công cụ không hỗ trợ accessibility tốt.

### 4.6. Kết hợp nhiều phong cách

Một sản phẩm có thể cung cấp form để nhập dữ liệu cơ bản, bảng để chỉnh sửa điều kiện và chế độ văn bản để xem hoặc sửa biểu thức nâng cao.

Nếu hỗ trợ nhiều cách biểu diễn, cần xác định một mô hình ngữ nghĩa chung. Chuyển đổi giữa các chế độ phải bảo toàn thông tin, bao gồm chú thích, thứ tự, metadata và các cấu trúc mà một chế độ không trực tiếp hiển thị.

## 5. Thiết kế quy tắc ngữ pháp rõ ràng

### 5.1. Ngữ pháp mô tả cách viết hợp lệ

Ngữ pháp (*grammar*) định nghĩa cách token được kết hợp thành cấu trúc hợp lệ. Một DSL nhỏ có thể mô tả ngữ pháp bằng EBNF.

Ví dụ đơn giản:

~~~text
rule        = "rule", identifier, "{", condition, action, "}" ;
condition   = "when", expression ;
action      = "then", actionExpression ;
expression  = comparison, { logicalOperator, comparison } ;
comparison  = reference, comparisonOperator, literal ;
reference   = identifier, { ".", identifier } ;
~~~

Đây là ngữ pháp minh họa. Nó cho thấy một rule gồm tên, khối, điều kiện và hành động; điều kiện có thể gồm nhiều phép so sánh kết hợp bằng toán tử logic.

Ngữ pháp cần mô tả rõ:

- Token nào được chấp nhận.
- Thành phần nào bắt buộc hoặc tùy chọn.
- Thứ tự các thành phần.
- Cách lồng khối và biểu thức.
- Quy tắc ưu tiên toán tử.
- Cách xử lý phần tử lặp và danh sách rỗng.

### 5.2. Ưu tiên toán tử

Khi biểu thức có nhiều toán tử, cần quy định thứ tự thực hiện.

Ví dụ:

~~~text
customer.tier == GOLD or order.total > 1000000 and order.isPaid
~~~

Nếu **and** có độ ưu tiên cao hơn **or**, biểu thức được hiểu là:

~~~text
customer.tier == GOLD
or
(order.total > 1000000 and order.isPaid)
~~~

Nếu người dùng không biết quy tắc này, họ có thể hiểu sai điều kiện. Dấu ngoặc nên được hỗ trợ để người viết diễn đạt nhóm logic một cách tường minh.

Một tài liệu DSL cần có bảng ưu tiên toán tử, chiều kết hợp và ví dụ. Không nên để người dùng suy luận quy tắc chỉ từ cách viết.

### 5.3. Cú pháp tối thiểu và cú pháp thay thế

Một DSL có thể hỗ trợ nhiều cách viết cho cùng một ý nghĩa. Ví dụ:

~~~text
order.total >= 1000000
~~~

và:

~~~text
order.total is at least 1000000
~~~

Hai cách có thể cùng biểu diễn một phép so sánh. Tuy nhiên, quá nhiều cú pháp thay thế làm tăng chi phí học, kiểm thử và tài liệu.

Nên chọn một dạng chuẩn để lưu hoặc định dạng tự động. Các dạng thay thế chỉ nên được hỗ trợ khi chúng cải thiện đáng kể khả năng tiếp cận hoặc phù hợp với nhóm người dùng cụ thể.

### 5.4. Cú pháp đường tắt và cú pháp chuẩn

Syntax sugar là cách viết ngắn hơn cho một cấu trúc có thể biểu diễn bằng cú pháp chuẩn.

Ví dụ:

~~~text
order.total between 100000 and 500000
~~~

có thể tương đương với:

~~~text
order.total >= 100000 and order.total <= 500000
~~~

Cú pháp đường tắt giúp biểu thức dễ đọc nếu nó phản ánh một khái niệm miền rõ ràng. Nhưng mọi dạng đường tắt cần có định nghĩa chính xác về ngữ nghĩa, cách xử lý biên và cách chuyển đổi sang biểu diễn chuẩn.

### 5.5. Cú pháp phiên bản

Khi ngữ pháp thay đổi, chương trình DSL đã lưu có thể được đọc bởi phiên bản mới. Có thể khai báo phiên bản cú pháp ở đầu tài liệu hoặc gắn phiên bản trong metadata.

Ví dụ minh họa:

~~~text
syntaxVersion 2

rule WeekendDiscount {
    when order.day in [Saturday, Sunday]
    then apply discount 10%
}
~~~

Parser có thể dùng phiên bản để chọn grammar hoặc áp dụng quy tắc tương thích. Không nên âm thầm diễn giải nội dung cũ theo một ngữ nghĩa mới nếu điều đó làm thay đổi kết quả nghiệp vụ.

## 6. Đặt tên và dùng thuật ngữ miền

### 6.1. Tên nên phản ánh khái niệm nghiệp vụ

Tên trường và hàm là một phần của ngôn ngữ. Nếu mô hình miền dùng thuật ngữ **deliveryAddress**, DSL cũng nên ưu tiên tên đó thay vì tự tạo một từ khác như **shipTo** nếu không có lý do.

Một từ vựng chung giúp tài liệu, mã nguồn, giao diện và quy tắc thống nhất với nhau.

### 6.2. Tránh viết tắt khó đoán

Các tên như **custTyp**, **ordAmt** hoặc **dscPct** có thể ngắn nhưng khó hiểu với người mới. Viết đầy đủ thường giúp giảm nhu cầu tra cứu.

Viết tắt chỉ nên dùng khi đó là thuật ngữ phổ biến trong miền và được định nghĩa rõ trong tài liệu.

### 6.3. Namespace và tên trùng

Khi DSL có nhiều module, tên có thể được tổ chức theo namespace:

~~~text
sales.customerTier
finance.taxRate
shipping.deliveryZone
~~~

Namespace làm rõ nguồn gốc và tránh xung đột. Cần quy định cách import, alias và cách xử lý tên không đầy đủ.

### 6.4. Phân biệt tên hiển thị và tên kỹ thuật

Một sản phẩm có thể hiển thị nhãn **Khách hàng ưu tiên** nhưng dùng định danh ổn định **PRIORITY_CUSTOMER** trong DSL.

Tách nhãn hiển thị khỏi định danh giúp giao diện có thể dịch ngôn ngữ mà không buộc thay đổi chương trình DSL. Nếu định danh bị thay đổi theo ngôn ngữ giao diện, nội dung đã lưu có thể trở nên khó di chuyển hoặc không còn phân tích được.

## 7. Đơn vị, ngày giờ và giá trị có ngữ cảnh

### 7.1. Giá trị phải gắn với đơn vị khi cần

Một số 100 có thể là 100 đồng, 100 kilogram, 100 phần trăm hoặc 100 ngày. Nếu DSL chỉ lưu số mà không thể hiện đơn vị, biểu thức có thể bị hiểu sai.

Ví dụ:

~~~text
order.total >= 1000000 VND
shipment.weight <= 20 kg
discount.rate = 10%
subscription.duration = 30 days
~~~

DSL nên định nghĩa các đơn vị hợp lệ, phép chuyển đổi và quy tắc làm tròn. Không nên tự động cộng hoặc so sánh hai giá trị khác đơn vị nếu không có quy tắc chuyển đổi rõ ràng.

### 7.2. Ngày và thời gian

Ngày giờ thường có nhiều cách biểu diễn. Một DSL cần quy định:

- Ngày theo định dạng nào.
- Thời điểm có chứa múi giờ không.
- Giá trị thời gian không có múi giờ được hiểu ra sao.
- Khoảng thời gian có tính điểm đầu và điểm cuối không.
- Cách tính ngày làm việc và ngày nghỉ.

Ví dụ, biểu thức **within last 30 days** cần xác định tính từ thời điểm nào và dùng múi giờ nào. Nếu kết quả ảnh hưởng đến nghiệp vụ, nguồn thời gian nên được kiểm soát và có thể thay thế khi kiểm thử.

### 7.3. Định dạng số theo địa phương

Một số quốc gia dùng dấu chấm để phân nhóm hàng nghìn và dấu phẩy làm dấu thập phân; nơi khác dùng quy ước ngược lại.

Nếu DSL cho phép người dùng nhập số theo locale, parser cần biết locale áp dụng. Không nên đoán định dạng từ chuỗi vì **1,234** có thể được hiểu khác nhau.

Với tệp DSL dùng trong kho mã hoặc tích hợp tự động, một định dạng chuẩn hóa thường dễ trao đổi và kiểm thử hơn. Giao diện có thể hiển thị số theo locale rồi chuyển thành giá trị chuẩn khi lưu.

## 8. Ký hiệu thân thiện với người dùng không có nghĩa là cú pháp tùy ý

### 8.1. Ngôn ngữ tự nhiên có thể mơ hồ

Một câu như:

~~~text
Give discount to large orders from loyal customers
~~~

có thể có nhiều cách hiểu:

- Đơn hàng lớn và khách hàng trung thành đều là điều kiện bắt buộc.
- Đơn hàng lớn hoặc khách hàng trung thành là đủ.
- Chỉ áp dụng khi khách hàng trung thành đặt đơn hàng lớn hơn một ngưỡng nào đó.

DSL cần cấu trúc để biểu diễn rõ quan hệ logic, ngưỡng và phạm vi điều kiện.

### 8.2. Tránh từ khóa có nhiều nghĩa

Một từ như **active** có thể mô tả tài khoản, đơn hàng hoặc chiến dịch. Nếu cùng một từ có ý nghĩa khác nhau tùy ngữ cảnh, cần xác định kiểu hoặc namespace để người đọc biết đối tượng đang được nói đến.

### 8.3. Cú pháp cần được phân tích xác định

Một nội dung DSL hợp lệ nên có cách phân tích rõ ràng. Nếu một chuỗi có thể được hiểu theo hai cấu trúc khác nhau mà không có quy tắc phân giải, parser có thể báo lỗi mơ hồ hoặc chọn một cách không như người viết mong đợi.

Thiết kế grammar cần tránh xung đột không cần thiết, quy định độ ưu tiên và cung cấp dấu phân cách khi ranh giới thành phần chưa rõ.

### 8.4. Không đánh đồng dễ đọc với giống tiếng Anh

DSL có thể dùng tiếng Anh, tiếng Việt hoặc một tập thuật ngữ chuyên môn. Điều quan trọng là người dùng mục tiêu hiểu được và các khái niệm được sử dụng nhất quán.

Một cú pháp dùng các từ tiếng Anh nhưng tên miền, thông báo lỗi và tài liệu không nhất quán vẫn có thể khó học. Một cú pháp ngắn với toán tử quen thuộc có thể phù hợp hơn với người dùng kỹ thuật.

## 9. Thiết kế ký hiệu cho khả năng tiếp cận

### 9.1. Không chỉ dựa vào màu sắc

Nếu trình soạn thảo dùng màu để phân biệt từ khóa, lỗi và giá trị, cần có thêm dấu hiệu như biểu tượng, gạch chân, nhãn hoặc thông báo văn bản. Người không phân biệt được một số màu vẫn cần hiểu trạng thái.

### 9.2. Hỗ trợ bàn phím và công nghệ hỗ trợ

Với DSL có giao diện trực quan, mọi thao tác quan trọng nên có thể thực hiện bằng bàn phím. Các nút, trường nhập và khối cần có tên dễ hiểu để trình đọc màn hình nhận biết.

### 9.3. Thông báo lỗi dễ hiểu

Lỗi nên chỉ ra vị trí, nội dung không hợp lệ và cách sửa. Không nên chỉ hiển thị mã parser hoặc stack trace.

Ví dụ:

**Thông báo khó dùng:** Unexpected token at position 42.

**Thông báo hữu ích hơn:** Thuộc tính **order.deliverDate** không tồn tại. Bạn có thể dùng **order.deliveryDate**.

Gợi ý sửa cần dựa trên schema và ngữ cảnh thật. Không nên đề xuất một tên trường chỉ vì nó giống về mặt chữ nếu kiểu dữ liệu hoặc miền không phù hợp.

### 9.4. Hỗ trợ người dùng mới

Trình soạn thảo có thể cung cấp:

- Mẫu quy tắc khởi đầu.
- Gợi ý từ khóa theo vị trí con trỏ.
- Mô tả hàm và tham số.
- Ví dụ hợp lệ.
- Kiểm tra trực tiếp khi nhập.
- Xem trước tác động của quy tắc nếu an toàn và khả thi.

Các hỗ trợ này giúp người dùng học cú pháp từ chính môi trường làm việc.

## 10. Quốc tế hóa và bản địa hóa ký hiệu

### 10.1. Ngôn ngữ hiển thị và ngôn ngữ cú pháp

Một DSL có thể giữ từ khóa cố định bằng tiếng Anh trong khi giao diện, tài liệu và thông báo lỗi được dịch. Cách này giúp nội dung DSL nhất quán giữa các môi trường.

Ví dụ, định danh **customerTier** vẫn giữ nguyên trong chương trình, còn giao diện hiển thị nhãn **Hạng khách hàng**.

### 10.2. Khi nào nên dịch từ khóa?

Nếu DSL dành cho một nhóm người dùng không chuyên kỹ thuật, từ khóa bản địa hóa có thể giúp học nhanh hơn. Tuy nhiên, nếu cùng một chương trình cần được trao đổi giữa nhiều quốc gia hoặc chạy trên nhiều môi trường, nhiều bộ từ khóa sẽ làm tăng chi phí hỗ trợ.

Một lựa chọn là giữ một cú pháp chuẩn và cung cấp giao diện dịch, tài liệu cùng gợi ý theo locale. Nếu cho phép nhiều bộ từ khóa, cần quy định cách chuẩn hóa khi lưu và cách chuyển đổi giữa các phiên bản ngôn ngữ.

### 10.3. Unicode và tên định danh

Hỗ trợ Unicode giúp tên hiển thị và chú thích dùng được nhiều ngôn ngữ. Nhưng tên định danh cần được xử lý nhất quán:

- Quy định chuẩn hóa Unicode.
- Xác định ký tự nào được phép trong tên.
- Tránh ký tự nhìn giống nhau nhưng có mã khác nhau.
- Quy định so sánh có phân biệt hoa thường hay không.
- Có chính sách cho ký tự điều khiển và ký tự vô hình.

Với hệ thống có yêu cầu bảo mật cao, nên kiểm tra tên định danh để hạn chế trường hợp ký tự đồng hình gây nhầm lẫn.

## 11. Thông báo lỗi và khả năng gỡ lỗi

### 11.1. Lỗi cú pháp

Lỗi cú pháp xảy ra khi nội dung không tuân theo grammar.

Ví dụ:

~~~text
rule WeekendDiscount {
    when order.day is Saturday
    then
}
~~~

Phần hành động bị thiếu. Parser nên chỉ ra rằng sau **then** cần có một biểu thức hành động, thay vì chỉ báo một lỗi chung chung.

### 11.2. Lỗi ngữ nghĩa

Một biểu thức có thể đúng cú pháp nhưng sai ngữ nghĩa:

~~~text
when order.total contains "high"
then apply discount 10%
~~~

Nếu **order.total** là kiểu Money, toán tử **contains** có thể không hợp lệ. Semantic analyzer nên chỉ rõ kiểu hiện tại và các phép toán được hỗ trợ.

### 11.3. Lỗi thời điểm thực thi

Một hàm mở rộng có thể thất bại khi gọi dịch vụ bên ngoài hoặc khi dữ liệu thực tế không đáp ứng điều kiện. Runtime cần phân biệt lỗi nghiệp vụ với lỗi kỹ thuật và gắn chúng với biểu thức hoặc hành động liên quan.

### 11.4. Giữ vị trí nguồn qua các bước biến đổi

Nếu DSL được chuyển qua AST, IR và nhiều pass, cần giữ thông tin vị trí nguồn hoặc source map. Khi backend phát hiện lỗi, hệ thống vẫn có thể trỏ về dòng và cột trong nội dung người dùng đã viết.

Đây là một phần của trải nghiệm ký hiệu: người dùng cần biết lỗi nằm ở đâu trong cách viết của họ, không phải trong cấu trúc nội bộ mà họ không nhìn thấy.

## 12. Định dạng tự động và quy ước trình bày

### 12.1. Một kiểu định dạng chuẩn

Định dạng tự động giúp nội dung nhất quán về khoảng trắng, xuống dòng và thụt lề. Ví dụ, nhiều người có thể viết cùng một quy tắc theo các kiểu khác nhau; formatter chuyển về một dạng chuẩn để dễ đọc và so sánh.

### 12.2. Formatter không được đổi ngữ nghĩa

Formatter chỉ nên thay đổi cách trình bày. Nó không được tự ý đổi giá trị, thứ tự điều kiện hoặc cách nhóm biểu thức.

Nếu DSL có nhiều cú pháp tương đương, formatter có thể chuyển về dạng chuẩn nhưng phải bảo toàn ý nghĩa. Các trường hợp không thể bảo toàn cần được giữ nguyên hoặc báo rõ.

### 12.3. Quy ước trình bày

Tài liệu DSL nên quy định:

- Cách thụt lề khối.
- Vị trí xuống dòng.
- Khoảng trắng quanh toán tử.
- Cách đặt dấu phẩy và dấu chấm phẩy.
- Cách trình bày danh sách dài.
- Cách viết chuỗi nhiều dòng.
- Cách sắp xếp thuộc tính nếu thứ tự không có ý nghĩa.

Một formatter thống nhất giúp code review tập trung vào thay đổi nghiệp vụ thay vì khác biệt trình bày.

## 13. Tiến hóa ký hiệu mà không phá vỡ nội dung cũ

### 13.1. Vì sao cần tương thích ngược?

Nội dung DSL có thể tồn tại trong cơ sở dữ liệu, file cấu hình, kho mã hoặc hệ thống khách hàng. Khi thay đổi cú pháp, chương trình cũ vẫn cần được đọc hoặc chuyển đổi có kiểm soát.

### 13.2. Thêm cú pháp mới

Việc thêm một từ khóa hoặc hàm mới thường ít rủi ro nếu tên đó chưa được dùng làm định danh trong nội dung cũ. Tuy nhiên, nếu từ khóa mới trùng với tên người dùng đã đặt, parser có thể diễn giải chương trình cũ khác đi.

Có thể dùng từ khóa ngữ cảnh, namespace hoặc cú pháp có tiền tố để giảm xung đột.

### 13.3. Thay đổi cú pháp hiện có

Nếu cần đổi tên hoặc bỏ cú pháp cũ:

1. Công bố dạng mới và lý do thay đổi.
2. Hỗ trợ dạng cũ trong một giai đoạn chuyển tiếp nếu có thể.
3. Hiển thị cảnh báo có vị trí nguồn.
4. Cung cấp công cụ chuyển đổi tự động khi quy tắc đủ xác định.
5. Ghi nhận phiên bản cú pháp của nội dung đã lưu.

### 13.4. Không thay đổi ngữ nghĩa âm thầm

Một thay đổi nhỏ trong toán tử, giá trị mặc định hoặc cách xử lý null có thể làm quy tắc nghiệp vụ cho kết quả khác. Cần coi thay đổi ngữ nghĩa là thay đổi hợp đồng và kiểm thử hồi quy các chương trình đang sử dụng.

## 14. Quy trình thiết kế ký hiệu hướng người dùng

Có thể đi theo quy trình sau:

1. **Xác định người dùng:** ai sẽ viết, đọc, xem xét và bảo trì DSL?
2. **Thu thập thuật ngữ miền:** lập danh sách khái niệm và cách người dùng hiện gọi tên chúng.
3. **Chọn phong cách biểu diễn:** văn bản, cấu hình, bảng, trực quan hoặc kết hợp.
4. **Xác định cấu trúc cốt lõi:** khai báo, điều kiện, hành động, biểu thức và nhóm.
5. **Định nghĩa token và quy tắc tên:** từ khóa, identifier, literal, toán tử và dấu phân cách.
6. **Viết grammar:** xác định thứ tự, phần bắt buộc, phần tùy chọn và độ ưu tiên.
7. **Định nghĩa ngữ nghĩa:** quy định kiểu dữ liệu, đơn vị, null, ngày giờ và cách đánh giá.
8. **Thiết kế thông báo lỗi:** gắn lỗi với vị trí nguồn và khái niệm miền.
9. **Thử với người dùng mục tiêu:** yêu cầu họ đọc, viết và sửa các quy tắc thực tế.
10. **Chuẩn hóa và quản lý phiên bản:** có formatter, tài liệu, ví dụ và chính sách migration.

Nên dùng ví dụ thật từ công việc của người dùng thay vì chỉ đánh giá cú pháp qua các biểu thức nhân tạo. Một cú pháp có vẻ đẹp trong tài liệu có thể khó dùng khi phải xử lý hàng chục điều kiện, trường hợp biên và quy tắc ngoại lệ.

## 15. Ví dụ hoàn chỉnh: thiết kế ký hiệu cho DSL chính sách ưu đãi

Giả sử nhóm cần một DSL để nhân viên kinh doanh đọc và chỉnh sửa chính sách ưu đãi.

### 15.1. Cú pháp ban đầu

~~~text
rule LoyalCustomerOffer {
    description "Ưu đãi dành cho khách hàng thành viên"

    when customer.tier is GOLD
         and order.total >= 2000000 VND

    then grant discount 10%
         and grant freeShipping
}
~~~

Ký hiệu sử dụng:

- **rule** để khai báo chính sách.
- **description** để ghi mô tả cho người đọc.
- **when** và **then** để phân tách điều kiện với hành động.
- **is** và **and** để kết hợp điều kiện.
- **>=** để biểu diễn ngưỡng.
- **VND** và **%** để thể hiện đơn vị.

### 15.2. Cách đọc theo nghiệp vụ

Quy tắc có nghĩa: khách hàng thuộc hạng GOLD và tổng đơn hàng đạt ít nhất 2.000.000 VND sẽ nhận giảm giá 10% cùng dịch vụ giao hàng miễn phí.

Ký hiệu này giúp nhân viên kinh doanh đọc được điều kiện chính. Lập trình viên vẫn có thể phân tích cú pháp thành AST và kiểm tra kiểu dữ liệu trước khi lưu quy tắc.

### 15.3. Những câu hỏi phải được định nghĩa

- Nếu khách hàng có hạng GOLD nhưng tổng đơn hàng chưa đạt ngưỡng thì sao?
- Giảm giá được tính trước hay sau thuế?
- 10% được áp dụng cho toàn bộ đơn hàng hay chỉ sản phẩm đủ điều kiện?
- Nếu hai quy tắc ưu đãi cùng khớp, quy tắc nào được ưu tiên?
- Có được cộng dồn ưu đãi hay không?
- Nếu khách hàng đổi hạng trong lúc đơn hàng đang thanh toán thì dùng hạng nào?

Các câu hỏi này thuộc ngữ nghĩa nghiệp vụ, không thể giải quyết chỉ bằng cách làm cú pháp trông tự nhiên hơn. Ký hiệu tốt phải giúp người dùng thể hiện các quyết định đó một cách rõ ràng.

### 15.4. Mở rộng quy tắc bằng nhóm điều kiện

Khi chính sách phức tạp hơn, DSL có thể cho phép nhóm:

~~~text
when (
    customer.tier is GOLD
    or customer.hasLoyaltyVoucher
)
and order.total >= 2000000 VND
then grant discount 10%
~~~

Dấu ngoặc làm rõ rằng khách hàng chỉ cần thỏa một trong hai điều kiện thành viên hoặc phiếu ưu đãi, đồng thời đơn hàng vẫn phải đạt ngưỡng giá trị.

### 15.5. Định dạng chuẩn

Formatter có thể chuẩn hóa biểu thức thành:

~~~text
rule LoyalCustomerOffer {
    description "Ưu đãi dành cho khách hàng thành viên"

    when (
        customer.tier is GOLD
        or customer.hasLoyaltyVoucher
    ) and order.total >= 2000000 VND

    then grant discount 10%
         and grant freeShipping
}
~~~

Việc chuẩn hóa giúp các quy tắc có cùng phong cách trình bày, hỗ trợ so sánh và xem xét thay đổi.

## 16. Những lỗi thường gặp khi thiết kế ký hiệu

### 16.1. Quá nhiều cách viết cho cùng một ý nghĩa

Nếu DSL cho phép **is**, **equals**, **==** và **same as** cùng biểu diễn một phép so sánh mà không có khác biệt, người dùng phải nhớ nhiều biến thể. Nên chọn một dạng chuẩn và chỉ hỗ trợ biến thể khi có lý do rõ ràng.

### 16.2. Tên từ khóa quá kỹ thuật

Các tên như **evalNode**, **invokeHandler** hoặc **resolveRef** có thể phù hợp trong API nội bộ nhưng không nhất thiết phù hợp với người dùng nghiệp vụ. Ký hiệu hướng người dùng nên phản ánh khái niệm miền.

### 16.3. Dùng từ gần nghĩa nhưng khác ngữ nghĩa

Ví dụ, **active**, **enabled** và **available** có thể mô tả những trạng thái khác nhau. Nếu dùng thay thế tùy tiện, người đọc không biết điều kiện nào thực sự được kiểm tra.

### 16.4. Không quy định đơn vị và giá trị mặc định

Biểu thức **duration > 30** không rõ 30 là giây, phút hay ngày. Giá trị mặc định không được công bố có thể khiến cùng một quy tắc cho kết quả khác nhau giữa các môi trường.

### 16.5. Thông báo lỗi chỉ dành cho người viết parser

Thông báo lỗi kỹ thuật không giúp người dùng miền sửa quy tắc. Cần chuyển lỗi thành thông điệp có ngữ cảnh, nêu tên khái niệm và cách khắc phục.

### 16.6. Thay đổi cú pháp mà không xét nội dung đã lưu

Thêm từ khóa hoặc đổi cách phân tích có thể làm chương trình cũ không còn hợp lệ hoặc mang nghĩa khác. Cần kiểm thử tương thích và có kế hoạch migration.

### 16.7. Cú pháp ngắn nhưng không thể đọc lại

Việc rút gọn quá mức có thể khiến biểu thức phụ thuộc vào kiến thức ngầm. Nên ưu tiên khả năng hiểu khi đọc lại, đặc biệt với quy tắc ảnh hưởng đến tiền, quyền truy cập hoặc quy trình quan trọng.

## 17. Câu hỏi tự đánh giá

1. Ký hiệu hướng người dùng khác AST và biểu diễn ngữ nghĩa như thế nào?
2. Những thành phần nào tạo nên bề mặt cú pháp của một DSL?
3. Khi nào nên dùng cú pháp gần ngôn ngữ tự nhiên và khi nào nên dùng toán tử lập trình?
4. Vì sao cần quy định thứ tự ưu tiên toán tử?
5. Syntax sugar mang lại lợi ích gì và tạo ra chi phí nào?
6. Vì sao giá trị tiền tệ và thời gian cần được biểu diễn cùng đơn vị hoặc ngữ cảnh?
7. Phân biệt tên hiển thị đã bản địa hóa với định danh kỹ thuật ổn định.
8. Một thông báo lỗi tốt cần chứa những thông tin nào?
9. Formatter cần bảo đảm điều gì để không làm thay đổi ý nghĩa chương trình?
10. Khi thay đổi cú pháp, cần làm gì để nội dung DSL cũ tiếp tục được hỗ trợ?

## Kết luận

Ký hiệu hướng người dùng là bề mặt mà người dùng dùng để đọc, viết và trao đổi các mô hình hoặc quy tắc trong DSL. Nó bao gồm từ khóa, tên định danh, literal, toán tử, dấu phân cách, khoảng trắng, chú thích và quy ước trình bày. Thiết kế ký hiệu cần phù hợp với kiến thức của người dùng mục tiêu, thuật ngữ miền và độ phức tạp của công việc.

Một ký hiệu hiệu quả có ngữ pháp xác định, ngữ nghĩa rõ, cách đặt tên nhất quán, hỗ trợ lỗi dễ hiểu và có thể tiến hóa mà không làm nội dung cũ thay đổi âm thầm. Cú pháp gần ngôn ngữ tự nhiên, toán tử lập trình, cấu hình, bảng và giao diện trực quan đều có thể phù hợp tùy ngữ cảnh. Điều quan trọng là người dùng có thể diễn đạt đúng ý định, đọc lại chính xác và dự đoán được hệ thống sẽ hiểu nội dung đó như thế nào.
