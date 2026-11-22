# Biên dịch DSL

Ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) được thiết kế để diễn đạt một nhóm vấn đề cụ thể bằng cú pháp và khái niệm gần với miền đó. Người dùng có thể viết quy tắc nghiệp vụ, truy vấn dữ liệu, cấu hình hạ tầng, workflow hoặc mô hình tính toán bằng DSL thay vì phải lập trình trực tiếp bằng một ngôn ngữ đa dụng.

Để một chương trình DSL có thể chạy được, hệ thống phải biến văn bản nguồn thành một dạng biểu diễn mà máy có thể phân tích, kiểm tra và thực thi. Quá trình chuyển đổi này được gọi là **biên dịch** (*compilation*). Tùy thiết kế, compiler có thể tạo mã máy, mã bytecode, mã nguồn của một ngôn ngữ khác, cấu hình cho một engine hoặc một biểu diễn trung gian để runtime xử lý.

Biên dịch DSL thường gồm nhiều giai đoạn: phân tích từ vựng, phân tích cú pháp, xây dựng mô hình trừu tượng, phân giải tên, kiểm tra kiểu và ngữ nghĩa, tạo biểu diễn trung gian, tối ưu và sinh đầu ra. Một số DSL không tạo mã độc lập mà được thông dịch trực tiếp từ AST hoặc IR. Dù chọn cách nào, hệ thống vẫn cần một pipeline rõ ràng để bảo đảm chương trình được hiểu nhất quán.

## 1. Biên dịch DSL là gì?

### 1.1. Từ văn bản nguồn đến chương trình có thể thực thi

Người dùng viết chương trình DSL dưới dạng văn bản:

~~~text
rule MemberDiscount {
    when customer.tier is GOLD
         and order.total >= 2000000 VND
    then applyDiscount(order, 0.10)
}
~~~

Văn bản này chứa những từ khóa, tên, literal, biểu thức và cấu trúc miền. Máy không thể thực thi trực tiếp chuỗi ký tự như cách con người đọc. Compiler phải xác định các thành phần, kiểm tra quan hệ giữa chúng và chuyển chúng sang một dạng thực thi được.

Một pipeline đơn giản:

~~~mermaid
flowchart LR
    A["DSL source"] --> B["Front end"]
    B --> C["Intermediate representation"]
    C --> D["Optimization"]
    D --> E["Code generation"]
    E --> F["Runtime"]
~~~

Trong đó:

- **Source:** văn bản DSL do người dùng viết.
- **Front end:** phân tích token, cú pháp, tên, kiểu và quy tắc ngữ nghĩa.
- **Intermediate representation (IR):** mô hình trung gian đã được chuẩn hóa.
- **Optimization:** cải thiện biểu diễn hoặc kế hoạch thực thi khi có thể.
- **Code generation:** tạo mã hoặc đầu ra cho môi trường đích.
- **Runtime:** cung cấp môi trường thực hiện chương trình, dữ liệu và dịch vụ cần thiết.

Không phải DSL nào cũng cần tất cả các bước. Một DSL cấu hình có thể chỉ parse thành object rồi serialize sang JSON. Một DSL truy vấn có thể tạo SQL. Một DSL tính toán có thể sinh bytecode hoặc mã máy.

### 1.2. Compiler không chỉ là bộ chuyển cú pháp

Một bộ chuyển cú pháp có thể đổi một cấu trúc từ dạng này sang dạng khác mà không hiểu đầy đủ ý nghĩa. Compiler thường làm nhiều hơn:

- Xác định tên tham chiếu đến khai báo nào.
- Kiểm tra biểu thức có đúng kiểu không.
- Xác nhận quy tắc miền có hợp lệ không.
- Phát hiện những cấu trúc không thể thực thi.
- Chuẩn hóa chương trình về mô hình thống nhất.
- Chọn cách triển khai phù hợp với môi trường đích.

Ví dụ, compiler có thể nhận diện một truy vấn DSL, kiểm tra trường dữ liệu theo schema, sau đó sinh SQL có tham số. Việc kiểm tra schema và tạo tham số truy vấn là một phần của quá trình biên dịch, không chỉ là thay thế từ khóa.

### 1.3. Các kiểu đầu ra của compiler DSL

| Đầu ra | Mô tả | Trường hợp sử dụng |
|---|---|---|
| Mã máy | Lệnh thực thi trực tiếp trên kiến trúc phần cứng | DSL hiệu năng cao hoặc hệ thống nhúng |
| Bytecode | Mã trung gian chạy trên virtual machine | DSL có runtime riêng hoặc dùng VM hiện có |
| Mã nguồn khác | Chuyển DSL sang Java, JavaScript, C, SQL hoặc ngôn ngữ đích | Tận dụng compiler và thư viện sẵn có |
| IR hoặc AST đã kiểm tra | Mô hình được runtime hoặc engine diễn giải | Rule engine, workflow engine |
| Cấu hình có cấu trúc | JSON, YAML, XML hoặc định dạng cấu hình đích | DSL khai báo và công cụ hạ tầng |
| Kế hoạch thực thi | Mô tả các bước cần thực hiện | Query planner, pipeline dữ liệu |

Đầu ra cần phù hợp với mục tiêu DSL. Sinh mã máy không tự động làm DSL tốt hơn nếu người dùng chỉ cần khai báo quy tắc và engine có thể thực thi IR một cách an toàn.

## 2. Kiến trúc compiler cho DSL

### 2.1. Front end

Front end tiếp nhận văn bản nguồn và xác định ý nghĩa cấu trúc của chương trình. Các thành phần thường có:

1. Lexer: chuyển ký tự thành token.
2. Parser: xây dựng cấu trúc cú pháp.
3. AST builder: tạo cây cú pháp trừu tượng.
4. Name resolver: liên kết tên với khai báo.
5. Type checker: suy luận và kiểm tra kiểu.
6. Semantic analyzer: kiểm tra ràng buộc ngữ nghĩa của DSL.

Một số compiler tích hợp các bước này trong một parser hoặc semantic pass duy nhất. Tuy vậy, phân biệt trách nhiệm giúp mã nguồn dễ bảo trì và diagnostic chính xác hơn.

### 2.2. Middle end

Middle end làm việc với IR thay vì văn bản nguồn. Nó có thể:

- Chuẩn hóa biểu thức.
- Hạ cấu trúc cấp cao thành thao tác cơ bản.
- Tối ưu biểu thức hằng.
- Loại bỏ phép tính không cần thiết.
- Tổ chức truy vấn hoặc workflow thành kế hoạch thực thi.
- Kiểm tra những bất biến của IR.

Tách middle end khỏi cú pháp giúp nhiều dạng DSL hoặc nhiều front end có thể dùng chung backend.

### 2.3. Back end

Backend chuyển IR sang đầu ra cụ thể:

- Mã cho virtual machine.
- Mã nguồn Java hoặc JavaScript.
- SQL cho cơ sở dữ liệu.
- Bytecode cho engine riêng.
- Cấu hình hoặc mô hình triển khai.

Backend cần hiểu hợp đồng của IR và môi trường đích. Nếu backend sinh SQL, nó phải xử lý đúng kiểu dữ liệu, tham số và quy tắc của hệ quản trị cơ sở dữ liệu.

### 2.4. Runtime

Runtime cung cấp các dịch vụ mà chương trình DSL cần khi thực thi:

- Truy cập dữ liệu và context.
- Gọi hàm miền.
- Quản lý trạng thái workflow.
- Kiểm tra quyền.
- Xử lý lỗi và timeout.
- Ghi log, tracing và metrics.
- Quản lý tài nguyên và giới hạn thực thi.

Compiler và runtime có thể được phát hành cùng nhau hoặc độc lập. Nếu độc lập, cần có hợp đồng tương thích giữa phiên bản IR, bytecode hoặc metadata mà compiler tạo ra và runtime đọc vào.

## 3. Phân tích từ vựng

### 3.1. Token là gì?

Lexer đọc văn bản nguồn và nhóm các ký tự thành token. Token có thể là:

- Từ khóa như rule, when, then.
- Định danh như customer hoặc applyDiscount.
- Literal số, chuỗi, ngày và Boolean.
- Toán tử như +, >=, and.
- Dấu phân cách như ngoặc, dấu phẩy và dấu chấm.
- Comment hoặc khoảng trắng, tùy cách lexer xử lý.

Ví dụ nguồn:

~~~text
let total = order.amount + 10
~~~

Một chuỗi token khái niệm:

~~~text
LET
IDENTIFIER("total")
EQUALS
IDENTIFIER("order")
DOT
IDENTIFIER("amount")
PLUS
NUMBER(10)
~~~

Token thường lưu loại, giá trị và vị trí nguồn. Vị trí này giúp compiler trỏ chính xác đến phần gây lỗi.

### 3.2. Token không đồng nghĩa với cú pháp

Lexer có thể xác định order là identifier và + là toán tử. Nó chưa cần biết phép cộng đó có hợp lệ giữa hai kiểu hay không.

Phân tích từ vựng tập trung vào việc nhận diện các đơn vị ký hiệu. Việc kết hợp token thành biểu thức thuộc trách nhiệm parser.

### 3.3. Xử lý literal

Lexer hoặc một thành phần liên quan có thể đọc:

~~~text
name = "Weekend offer"
rate = 0.10
active = true
date = 2026-11-15
~~~

DSL cần định nghĩa định dạng số, dấu thập phân, dấu phân cách hàng nghìn, escape trong chuỗi, timezone và cách biểu diễn đơn vị.

Nếu cùng một văn bản số có thể được hiểu khác nhau theo locale, compiler cần có chính sách locale rõ ràng hoặc dùng cú pháp độc lập với locale để tránh chương trình thay đổi ý nghĩa giữa môi trường.

### 3.4. Diagnostic từ lexer

Lexer có thể phát hiện:

- Chuỗi chưa đóng.
- Ký tự không được hỗ trợ.
- Literal số sai định dạng.
- Escape sequence không hợp lệ.
- Định danh vi phạm quy tắc ký tự.

Thông báo nên gắn với đúng vùng nguồn. Nếu có thể phục hồi, lexer có thể tạo token lỗi để parser tiếp tục và tìm thêm vấn đề độc lập.

## 4. Phân tích cú pháp

### 4.1. Grammar mô tả cấu trúc hợp lệ

Parser dùng grammar để xác định cách các token kết hợp thành câu lệnh và biểu thức. Một grammar rút gọn có thể mô tả khai báo biến:

~~~text
variableDeclaration =
    "let", identifier, [":", typeName], "=", expression ;
~~~

Grammar xác định vị trí của từ khóa let, tên biến, kiểu tùy chọn và biểu thức khởi tạo.

### 4.2. Parser tạo cây cú pháp

Với:

~~~text
let total = order.amount + 10
~~~

AST có thể có dạng:

~~~text
VariableDeclaration
  name: total
  initializer:
    BinaryExpression
      operator: +
      left:
        MemberAccess
          object: order
          member: amount
      right:
        NumberLiteral: 10
~~~

AST bỏ qua nhiều chi tiết không cần thiết cho xử lý ngữ nghĩa như khoảng trắng và comment, nhưng thường giữ source span để phục vụ diagnostic và công cụ phát triển.

### 4.3. AST và parse tree

Parse tree phản ánh các quy tắc grammar đã được áp dụng, có thể chứa nhiều node trung gian. AST chỉ giữ cấu trúc có ý nghĩa đối với những bước sau.

Ví dụ, dấu ngoặc dùng để nhóm biểu thức có thể không cần giữ thành một node riêng nếu AST đã thể hiện thứ tự kết hợp. Tuy nhiên, vị trí nguồn của dấu ngoặc vẫn có thể được lưu nếu formatter hoặc diagnostic cần.

### 4.4. Lỗi cú pháp

Một biểu thức:

~~~text
when order.total > 1000000
then applyDiscount(order, 0.10
~~~

thiếu dấu đóng ngoặc. Parser cần chỉ ra vị trí mong đợi dấu đóng và có thể đồng bộ ở điểm bắt đầu câu lệnh tiếp theo.

### 4.5. Parser và phục hồi lỗi

Compiler dùng trong IDE thường cần tiếp tục phân tích khi nguồn chưa hoàn chỉnh. Nó có thể:

- Chèn token giả để tiếp tục.
- Bỏ qua token không phù hợp.
- Đồng bộ tại dấu phân cách hoặc đầu khai báo tiếp theo.
- Tạo node lỗi trong AST.

Phục hồi cần thận trọng để không biến một lỗi cú pháp thành nhiều lỗi giả ở các dòng sau.

## 5. Xây dựng AST và mô hình nguồn

### 5.1. AST biểu diễn cấu trúc có ý nghĩa

AST là nền tảng cho phân giải tên, kiểm tra kiểu, tối ưu và sinh mã. Một node thường có:

- Loại node.
- Các node con hoặc thuộc tính.
- Kiểu dữ liệu nếu đã được suy luận.
- Tham chiếu đến symbol nếu đã phân giải.
- Source span.
- Metadata phục vụ compiler hoặc runtime.

### 5.2. AST có kiểu

Sau semantic analysis, node có thể mang kiểu kết quả:

~~~text
BinaryExpression
  operator: +
  left: Expression<Money>
  right: Expression<Money>
  resultType: Money
~~~

Nếu hai toán hạng không tương thích, compiler không nên coi node là một biểu thức hợp lệ. Có thể gắn ErrorType để tiếp tục phân tích các phần khác.

### 5.3. AST không nhất thiết là định dạng lưu trữ

AST nội bộ có thể thay đổi theo phiên bản compiler. Nếu cần lưu chương trình lâu dài hoặc trao đổi giữa dịch vụ, nên cân nhắc một schema tài liệu ổn định riêng.

Tài liệu lưu trữ có thể được parse và chuyển thành AST hiện tại khi đọc. Điều này tách vòng đời định dạng lưu trữ khỏi cấu trúc nội bộ của compiler.

### 5.4. Giữ liên kết với nguồn

Source span giúp:

- Gạch chân lỗi trong editor.
- Hiển thị nguồn của một node IR.
- Tạo source map cho mã sinh ra.
- Hỗ trợ debug.
- Điều hướng từ kết quả thực thi về dòng DSL.

Nếu compiler bỏ toàn bộ thông tin vị trí quá sớm, việc chẩn đoán lỗi sau tối ưu hoặc khi runtime thất bại sẽ khó hơn.

## 6. Phân giải tên và xây dựng symbol

### 6.1. Symbol là gì?

Symbol đại diện cho một khai báo có thể được tham chiếu. Nó có thể mô tả biến, hàm, kiểu, thuộc tính, module hoặc quy tắc.

Một symbol thường lưu tên, loại khai báo, kiểu, phạm vi, quyền truy cập và vị trí khai báo.

### 6.2. Scope

Scope xác định nơi một khai báo có thể được nhìn thấy. DSL có thể có:

- Scope toàn cục.
- Scope module.
- Scope của rule hoặc function.
- Scope block.
- Scope của biểu thức lambda.
- Scope riêng cho kiểu hoặc namespace.

Resolver tra cứu tên theo quy tắc scope và import đã được định nghĩa.

### 6.3. Phân giải tham chiếu

Với:

~~~text
customer.address.city
~~~

Resolver có thể:

1. Tìm symbol customer trong scope hiện tại.
2. Xác định kiểu của customer.
3. Tìm thuộc tính address trên kiểu đó.
4. Xác định kiểu của address.
5. Tìm thuộc tính city trên kiểu address.

Nếu một bước thất bại, diagnostic cần gắn với thành phần cụ thể và tránh báo lỗi dây chuyền cho các phần phụ thuộc.

### 6.4. Hàm và overload

Một tên hàm có thể ánh xạ đến nhiều chữ ký. Compiler cần phân tích kiểu đối số, số lượng tham số và quy tắc chuyển đổi để chọn overload.

Nếu không có chữ ký phù hợp, compiler báo lỗi. Nếu nhiều chữ ký cùng phù hợp mà không có quy tắc ưu tiên xác định, lời gọi là mơ hồ.

### 6.5. Import và module

Import đưa symbol từ module khác vào phạm vi hiện tại. Compiler cần xác định:

- Module có tồn tại không?
- Symbol có được export không?
- Alias có trùng tên không?
- Có vòng phụ thuộc giữa module không?
- Phiên bản module có tương thích không?

Đối với DSL plugin, việc nạp module có thể phụ thuộc cấu hình hoặc registry. Compiler nên kiểm soát nguồn module và không thực thi plugin tùy tiện chỉ để phân giải tên.

## 7. Kiểm tra kiểu

### 7.1. Kiểu của biểu thức

Type checker xác định kiểu của literal, biến, truy cập thuộc tính, lời gọi hàm và biểu thức kết hợp.

Ví dụ:

~~~text
order.total + shippingFee
~~~

Nếu cả hai thuộc kiểu Money và cùng đơn vị, kết quả có thể là Money. Nếu một vế là Customer, phép cộng không hợp lệ.

### 7.2. Kiểm tra phép gán

~~~text
let total: Money = order.total
~~~

Kiểu thực tế của biểu thức bên phải phải có thể gán cho kiểu khai báo. Hệ kiểu có thể hỗ trợ subtype hoặc chuyển đổi an toàn, nhưng các quy tắc này cần được định nghĩa.

### 7.3. Suy luận kiểu

DSL có thể cho phép suy luận kiểu từ biểu thức khởi tạo:

~~~text
let retryCount = 3
let customerName = customer.name
~~~

Compiler suy ra retryCount là Integer và customerName là String nếu schema miền cung cấp những kiểu đó.

Khi không đủ thông tin, compiler có thể yêu cầu khai báo kiểu tường minh.

### 7.4. Generic

Các kiểu như List<T>, Optional<T> hoặc Result<T, E> cho phép giữ quan hệ kiểu trong cấu trúc tổng quát. Type checker cần giải các tham số kiểu và kiểm tra bound nếu DSL hỗ trợ generic.

### 7.5. Kiểu nullable

Nếu một biểu thức có thể không có giá trị, type checker cần buộc người dùng xử lý trường hợp vắng mặt hoặc dùng một phép truy cập an toàn theo quy tắc của DSL.

### 7.6. Đơn vị và kiểu miền

Hai giá trị có cùng kiểu số chưa chắc có thể kết hợp. Money, Distance, Duration và Percentage có thể cần kiểu riêng hoặc metadata đơn vị để compiler phát hiện phép toán không phù hợp.

### 7.7. Kiểm tra chữ ký hàm

Compiler kiểm tra số lượng đối số, kiểu, tham số bắt buộc, tham số tùy chọn và kiểu kết quả. Nếu DSL hỗ trợ generic function, nó còn phải suy luận và giải ràng buộc kiểu.

## 8. Kiểm tra ngữ nghĩa miền

### 8.1. Ngữ nghĩa vượt ra ngoài hệ kiểu

Một biểu thức có thể đúng kiểu nhưng vi phạm quy tắc nghiệp vụ. Ví dụ, discountRate là Decimal nhưng giá trị phải nằm trong khoảng 0 đến 1.

Compiler có thể kiểm tra giá trị hằng ở thời điểm biên dịch và tạo validation runtime cho giá trị động.

### 8.2. Bất biến

Một mô hình có thể yêu cầu:

~~~text
type DateRange {
    start: Date
    end: Date
    invariant end >= start
}
~~~

Bất biến có thể được kiểm tra khi tạo đối tượng, trước khi lưu hoặc trước khi thực hiện hành động.

### 8.3. Trạng thái và chuyển tiếp

Workflow DSL có thể mô hình hóa các trạng thái và chuyển tiếp. Compiler có thể kiểm tra trạng thái đích tồn tại, chuyển tiếp hợp lệ và một số trạng thái không thể đạt tới.

### 8.4. Quyền và điều kiện thực thi

Quy tắc yêu cầu vai trò MANAGER có thể cần context xác thực lúc chạy. Compiler có thể xác nhận rằng tên vai trò được định nghĩa, nhưng runtime phải xác minh người dùng thực sự có vai trò đó.

### 8.5. Ràng buộc phụ thuộc dữ liệu

Nếu quy tắc phụ thuộc vào số dư, tồn kho hoặc trạng thái từ dịch vụ ngoài, compiler không thể luôn chứng minh điều kiện đúng. Runtime cần xác thực tại thời điểm thực thi và xử lý trạng thái thay đổi.

## 9. Biểu diễn trung gian (IR)

### 9.1. Vì sao cần IR?

IR là một dạng biểu diễn chương trình nằm giữa nguồn DSL và đầu ra cuối. Nó giúp tách front end khỏi backend.

Nếu có nhiều cú pháp DSL cùng diễn đạt một ý nghĩa, mỗi cú pháp có thể được chuyển về một IR chung. Nhiều backend cũng có thể tiêu thụ cùng IR để sinh mã cho những môi trường khác nhau.

### 9.2. Ví dụ hạ AST xuống IR

AST nguồn:

~~~text
order.total > 1000000 and customer.tier == GOLD
~~~

IR khái niệm:

~~~text
AND
  GREATER_THAN
    LOAD_FIELD order.total
    CONSTANT Money(1000000, VND)
  EQUALS
    LOAD_FIELD customer.tier
    CONSTANT CustomerTier.GOLD
~~~

IR có thể dùng những thao tác ít phụ thuộc cú pháp hơn và biểu diễn rõ kiểu, đơn vị, tham chiếu và thứ tự đánh giá.

### 9.3. IR cấp cao và cấp thấp

IR cấp cao giữ những khái niệm gần miền như ApplyDiscount, ValidateCustomer hoặc QueryOrders.

IR cấp thấp dùng các thao tác tổng quát như LOAD_FIELD, COMPARE, CALL và BRANCH.

Một compiler có thể dùng nhiều tầng IR:

~~~text
DSL AST
  -> Domain IR
  -> Generic IR
  -> Target IR
  -> Bytecode hoặc mã nguồn
~~~

### 9.4. IR cần có hợp đồng rõ

IR nên định nghĩa:

- Các loại node và operand.
- Kiểu dữ liệu của từng thao tác.
- Quy tắc đánh giá và thứ tự thực hiện.
- Quy tắc lỗi và giá trị vắng mặt.
- Cách biểu diễn hằng số và metadata.
- Phiên bản và khả năng tương thích nếu được lưu trữ.

Nếu IR không có hợp đồng ổn định, backend và runtime có thể hiểu khác nhau về cùng một chương trình.

### 9.5. IR và source mapping

Một node IR nên giữ nguồn gốc từ AST hoặc DSL khi có thể. Khi runtime báo lỗi tại một lệnh IR, hệ thống có thể tìm lại dòng DSL tương ứng để hiển thị cho người dùng.

## 10. Tối ưu hóa chương trình DSL

### 10.1. Mục tiêu tối ưu

Tối ưu hóa nhằm cải thiện một hoặc nhiều đặc tính:

- Thời gian thực thi.
- Bộ nhớ sử dụng.
- Số lần truy cập dữ liệu.
- Kích thước mã hoặc kế hoạch.
- Số lời gọi dịch vụ.
- Khả năng tận dụng backend.

Tối ưu phải giữ nguyên ngữ nghĩa quan sát được của chương trình theo hợp đồng DSL.

### 10.2. Constant folding

Biểu thức chỉ gồm hằng có thể được tính trước:

~~~text
let maxAttempts = 2 + 3 * 4
~~~

Compiler có thể thay bằng 14 nếu quy tắc ưu tiên toán tử và kiểu số đã được xác định.

### 10.3. Constant propagation

Nếu compiler biết một giá trị không thay đổi:

~~~text
let threshold = 100
if order.count > threshold {
    ...
}
~~~

Nó có thể thay tham chiếu threshold bằng hằng 100 trong IR nếu việc thay thế không làm thay đổi hành vi.

### 10.4. Loại bỏ mã không thể đạt tới

Nếu điều kiện được chứng minh luôn sai:

~~~text
if false {
    applyDiscount(order, 0.10)
}
~~~

Compiler có thể loại bỏ nhánh không thể chạy. Tuy nhiên, nếu biểu thức điều kiện có tác dụng phụ, cần xét ngữ nghĩa trước khi xóa.

### 10.5. Common subexpression elimination

Nếu cùng một biểu thức thuần được tính nhiều lần:

~~~text
let a = order.total * rate
let b = order.total * rate + shippingFee
~~~

Compiler có thể tái sử dụng kết quả order.total * rate nếu giá trị đầu vào không thay đổi và biểu thức không có tác dụng phụ.

### 10.6. Tối ưu truy vấn

Với DSL truy vấn, compiler có thể:

- Đẩy bộ lọc xuống gần nguồn dữ liệu.
- Chỉ chọn các trường cần thiết.
- Kết hợp điều kiện.
- Chọn thứ tự join.
- Dùng chỉ mục phù hợp.
- Tránh đọc dữ liệu thừa.

Một số tối ưu phụ thuộc database và thống kê dữ liệu, do đó có thể diễn ra tại runtime hoặc query planner.

### 10.7. Tác dụng phụ và thứ tự đánh giá

Không được đổi thứ tự hoặc loại bỏ lời gọi có tác dụng phụ nếu điều đó thay đổi hành vi.

Ví dụ, hai hàm cùng ghi log hoặc cập nhật trạng thái không thể mặc nhiên đổi thứ tự. Compiler cần biết biểu thức nào thuần, biểu thức nào có tác dụng phụ hoặc có hợp đồng effect riêng.

### 10.8. Tối ưu không phải sửa chương trình sai

Compiler chỉ nên tối ưu chương trình đã đáp ứng những điều kiện ngữ nghĩa cần thiết. Tối ưu không được che giấu lỗi kiểu, lỗi miền hoặc lỗi truy cập.

## 11. Sinh mã (code generation)

### 11.1. Mục tiêu sinh mã

Code generation chuyển IR thành một dạng đầu ra mà môi trường đích hiểu được. Backend phải ánh xạ thao tác IR sang khả năng của target.

Ví dụ, một IR có thao tác so sánh có thể được sinh thành:

- Lệnh bytecode.
- Câu lệnh Java.
- Biểu thức SQL.
- Lệnh gọi API của engine.
- Cấu hình khai báo.

### 11.2. Sinh mã nguồn khác

Một DSL có thể được biên dịch sang Java:

~~~text
DSL:
let eligible = order.total >= 1000000 VND
~~~

Mã Java minh họa:

~~~java
boolean eligible =
    order.getTotal().compareTo(Money.of(1_000_000, "VND")) >= 0;
~~~

Backend cần tạo mã đúng cú pháp, đúng kiểu và giữ ngữ nghĩa của phép so sánh tiền tệ. Không nên chỉ thay tên toán tử hoặc nối chuỗi mà không xét quy tắc target.

### 11.3. Sinh SQL

Một DSL truy vấn có thể:

~~~text
select customer.name
from Customer
where customer.tier == GOLD
~~~

được chuyển thành SQL có tham số:

~~~sql
SELECT customer_name
FROM customers
WHERE tier = ?
~~~

Giá trị GOLD được truyền qua tham số thay vì nối trực tiếp vào chuỗi SQL. Backend cần ánh xạ tên bảng, cột, kiểu và hàm theo database đích.

### 11.4. Sinh bytecode

Bytecode là tập lệnh trung gian được một virtual machine thực thi. Compiler có thể sinh bytecode riêng cho DSL để kiểm soát môi trường, giới hạn và kiểu dữ liệu.

Một instruction bytecode thường có opcode và operand. Ví dụ khái niệm:

~~~text
LOAD_FIELD 0
PUSH_CONST 1000000
GREATER_OR_EQUAL
JUMP_IF_FALSE 12
CALL_ACTION 3
~~~

Đây chỉ là minh họa. Một bytecode thực tế cần định nghĩa stack hoặc register model, kiểu operand, kiểm tra giới hạn và phiên bản định dạng.

### 11.5. Sinh mã máy

Nếu DSL yêu cầu hiệu năng rất cao hoặc nhắm đến phần cứng cụ thể, backend có thể sinh mã máy hoặc dùng một compiler nền tảng. Cách này đòi hỏi quản lý ABI, kiến trúc, bộ nhớ, calling convention và nhiều chi tiết nền tảng hơn.

Không nên chọn mã máy chỉ vì đó là hình thức biên dịch thấp nhất. Cần cân nhắc lợi ích thực tế so với chi phí phát triển và duy trì.

### 11.6. Kiểm tra target capability

Một IR có thể chứa tính năng mà target không hỗ trợ. Backend cần phát hiện và báo rõ:

- Tính năng nào không được hỗ trợ.
- Target hiện tại là gì.
- Có cách hạ cấp hoặc thay thế không.
- Có backend khác đáp ứng được không.

Không nên âm thầm bỏ qua thao tác không hỗ trợ vì có thể làm chương trình chạy sai.

## 12. Biên dịch DSL sang Java: ví dụ từng bước

### 12.1. Nguồn DSL

~~~text
rule FreeShipping {
    when order.total >= 500000 VND
    then setShippingFee(order, Money.zero("VND"))
}
~~~

### 12.2. Token

Lexer có thể tạo các token:

~~~text
RULE
IDENTIFIER("FreeShipping")
LBRACE
WHEN
IDENTIFIER("order")
DOT
IDENTIFIER("total")
GREATER_EQUAL
MONEY_LITERAL(500000, "VND")
THEN
IDENTIFIER("setShippingFee")
LPAREN
IDENTIFIER("order")
COMMA
IDENTIFIER("Money")
DOT
IDENTIFIER("zero")
LPAREN
STRING("VND")
RPAREN
RPAREN
RBRACE
~~~

### 12.3. AST

~~~text
RuleDeclaration
  name: FreeShipping
  condition:
    GreaterOrEqual
      MemberAccess(order, total)
      MoneyLiteral(500000, VND)
  action:
    Call(setShippingFee)
      Argument(order)
      Argument(Call(Money.zero, "VND"))
~~~

### 12.4. Phân giải và kiểm tra kiểu

Compiler xác định:

- FreeShipping là tên rule duy nhất trong module.
- order là đầu vào có kiểu Order.
- total là thuộc tính Money.
- Literal có kiểu Money và đơn vị VND.
- Hai vế phép so sánh tương thích.
- setShippingFee là hàm có thể gọi với Order và Money.
- Money.zero nhận mã tiền tệ hợp lệ.

Nếu total có đơn vị khác VND mà không có chuyển đổi, compiler cần báo lỗi đơn vị.

### 12.5. IR

~~~text
RULE FreeShipping
  CONDITION:
    GE
      LOAD_FIELD order.total
      CONST_MONEY 500000 VND
  ACTION:
    CALL setShippingFee
      LOAD order
      CALL Money.zero
        CONST_STRING "VND"
~~~

### 12.6. Mã Java minh họa

~~~java
if (order.getTotal().compareTo(
        Money.of(500_000, Currency.getInstance("VND"))) >= 0) {
    setShippingFee(order, Money.zero(Currency.getInstance("VND")));
}
~~~

Mã sinh ra chỉ minh họa cách hạ quy tắc. Một backend thật cần tạo tên biến an toàn, quản lý import, xử lý exception, bảo toàn vị trí nguồn và không sinh mã có thể bị chèn cú pháp từ tên hoặc literal người dùng.

## 13. Biên dịch, thông dịch và mô hình lai

### 13.1. Thông dịch trực tiếp AST

Interpreter có thể duyệt AST và thực hiện từng node:

~~~text
evaluate(BinaryExpression):
    left = evaluate(node.left)
    right = evaluate(node.right)
    return apply(node.operator, left, right)
~~~

Ưu điểm là dễ triển khai và phù hợp với DSL nhỏ hoặc môi trường cần thay đổi nhanh. Nhược điểm là runtime có thể phải xử lý nhiều cấu trúc cấp cao lặp đi lặp lại và khó tối ưu toàn chương trình.

### 13.2. Biên dịch sang IR rồi thông dịch

Một mô hình phổ biến là parse và kiểm tra DSL một lần, tạo IR rồi interpreter chạy IR:

~~~text
Source -> AST -> Semantic checks -> IR -> IR Interpreter
~~~

Cách này tách cú pháp khỏi runtime và có thể tối ưu IR trước khi chạy. Interpreter không cần hiểu mọi chi tiết của cú pháp nguồn.

### 13.3. Biên dịch trước (AOT)

Ahead-of-time compilation tạo đầu ra trước khi chương trình chạy. Ví dụ, DSL được biên dịch thành bytecode hoặc mã nguồn trong giai đoạn build.

Ưu điểm:

- Phát hiện nhiều lỗi trước khi triển khai.
- Giảm công việc phân tích khi runtime.
- Có thể tối ưu toàn chương trình.
- Dễ kiểm tra artifact trước khi phát hành.

Nhược điểm:

- Cần bước build hoặc compile riêng.
- Có thể cần build lại khi schema hoặc module thay đổi.
- Artifact cần tương thích với runtime đích.

### 13.4. Biên dịch đúng lúc (JIT)

Just-in-time compilation biên dịch một phần chương trình khi runtime cần. Có thể bắt đầu bằng interpreter rồi biên dịch những đoạn được thực thi nhiều.

JIT có thể cải thiện hiệu năng cho chương trình chạy lâu, nhưng cần quản lý cache mã, thời gian biên dịch, an toàn bộ nhớ và hành vi khi môi trường thay đổi.

### 13.5. Mô hình lai

Một hệ thống có thể:

1. Parse và kiểm tra DSL khi nạp.
2. Tạo IR đã chuẩn hóa.
3. Thông dịch các node ít dùng.
4. Biên dịch các nhánh hoặc biểu thức nóng.
5. Cache artifact cho lần chạy tiếp theo.

Mô hình lai cho phép cân bằng thời gian khởi động, hiệu năng và tính linh hoạt.

## 14. Quản lý lỗi trong quá trình biên dịch

### 14.1. Diagnostic theo giai đoạn

Mỗi pass có thể phát lỗi riêng:

| Giai đoạn | Lỗi điển hình |
|---|---|
| Lexer | Token hoặc literal không hợp lệ |
| Parser | Thiếu thành phần cú pháp |
| Name resolution | Tên chưa khai báo hoặc mơ hồ |
| Type checking | Kiểu không tương thích |
| Semantic validation | Vi phạm ràng buộc miền |
| Optimization | IR không thỏa bất biến hoặc phép biến đổi không hợp lệ |
| Code generation | Target không hỗ trợ tính năng |
| Runtime | Lỗi dữ liệu, dịch vụ hoặc môi trường |

### 14.2. Diagnostic có cấu trúc

Một diagnostic nên có:

- Mã lỗi ổn định.
- Mức độ.
- Thông điệp hướng người dùng.
- Vị trí nguồn.
- Vị trí liên quan.
- Kiểu hoặc ràng buộc mong đợi và thực tế.
- Gợi ý sửa khi có căn cứ.

Ví dụ:

~~~text
Diagnostic {
    code: "TYPE_MISMATCH"
    severity: Error
    message: "Không thể cộng Money với String"
    primarySpan: source:8:20-8:21
    expectedType: Money
    actualType: String
}
~~~

### 14.3. Tránh lỗi dây chuyền

Nếu một tên chưa được phân giải, những kiểm tra phụ thuộc vào kiểu của tên đó nên dùng ErrorType hoặc ErrorSymbol để tránh báo nhiều lỗi giả.

Compiler vẫn nên tiếp tục kiểm tra những biểu thức độc lập để người dùng nhận được nhiều thông tin hữu ích trong một lượt.

### 14.4. Không sinh artifact khi còn lỗi nghiêm trọng

Nếu chương trình có lỗi làm thay đổi ý nghĩa hoặc không thể thực thi an toàn, compiler thường nên dừng trước code generation hoặc đánh dấu artifact không thể chạy.

Một số công cụ có thể sinh output một phần để phục vụ IDE, nhưng output đó phải được đánh dấu là không hoàn chỉnh và không được đưa vào runtime như artifact hợp lệ.

## 15. Source map và debug mã sinh ra

### 15.1. Vấn đề của mã sinh ra

Khi DSL được biên dịch sang Java hoặc SQL, lỗi runtime có thể chỉ ra dòng trong mã sinh ra. Người dùng DSL thường không làm việc trực tiếp với file đó.

Compiler cần một cách liên kết lệnh đích với vị trí nguồn.

### 15.2. Source map

Source map ánh xạ vị trí trong đầu ra về vị trí trong nguồn DSL. Nó có thể ghi:

- File DSL gốc.
- Dòng và cột của node nguồn.
- Vùng mã sinh ra tương ứng.
- Quan hệ giữa một node nguồn và nhiều đoạn mã đích.

### 15.3. Ánh xạ nhiều-một và một-nhiều

Một biểu thức DSL có thể sinh ra nhiều câu lệnh Java. Ngược lại, nhiều biểu thức DSL có thể được tối ưu thành một thao tác IR hoặc một câu SQL.

Source map cần hỗ trợ các quan hệ này thay vì giả định mỗi dòng nguồn tương ứng đúng một dòng đích.

### 15.4. Diagnostic runtime về nguồn DSL

Nếu một lệnh sinh ra thất bại, runtime có thể dùng source map để báo:

~~~text
Không thể áp dụng ưu đãi cho đơn hàng.
Nguồn DSL: discounts.dsl, dòng 18, cột 9.
Nguyên nhân: trạng thái đơn hàng đã thay đổi.
~~~

Điều này giúp người vận hành tìm đúng quy tắc mà không cần đọc mã sinh ra.

### 15.5. Debug symbol và metadata

Compiler có thể lưu tên symbol, kiểu, biến nguồn và thông tin scope để hỗ trợ debug. Metadata cần được quản lý theo phiên bản và không nên làm lộ dữ liệu nhạy cảm ngoài phạm vi được phép.

## 16. Biên dịch tăng dần và cache

### 16.1. Vì sao cần incremental compilation?

Trong dự án DSL lớn, một thay đổi nhỏ không nên buộc compiler phân tích và sinh mã lại toàn bộ mọi module nếu phần còn lại không bị ảnh hưởng.

Biên dịch tăng dần chỉ xử lý những thành phần thay đổi và những thành phần phụ thuộc vào chúng.

### 16.2. Đồ thị phụ thuộc

Compiler có thể xây dựng đồ thị:

~~~text
discounts.dsl -> customer-schema
discounts.dsl -> pricing-functions
shipping.dsl  -> order-schema
shipping.dsl  -> shipping-functions
~~~

Nếu pricing-functions thay đổi, compiler có thể đánh dấu discounts.dsl cần kiểm tra lại. shipping.dsl có thể không bị ảnh hưởng nếu không phụ thuộc vào module đó.

### 16.3. Cache kết quả

Cache có thể lưu:

- Token hoặc parse result.
- AST.
- Symbol table hoặc metadata module.
- Kết quả type checking.
- IR.
- Artifact đã sinh.

Mỗi cache cần khóa dựa trên nội dung nguồn và những đầu vào ảnh hưởng đến kết quả như phiên bản compiler, schema, module và cấu hình target.

### 16.4. Cache invalidation

Không chỉ file nguồn mới làm kết quả cũ mất hiệu lực. Thay đổi schema, thư viện, phiên bản compiler, locale, feature flag hoặc cấu hình target cũng có thể yêu cầu biên dịch lại.

Nếu khóa cache thiếu một đầu vào, hệ thống có thể dùng artifact cũ cho chương trình mới và tạo lỗi khó tái hiện.

### 16.5. Build xác định

Với cùng nguồn, dependency và cấu hình, compiler nên tạo kết quả giống nhau nếu hợp đồng yêu cầu tính xác định.

Không nên để thứ tự file hệ thống, thời gian hiện tại hoặc dữ liệu môi trường không được khai báo ảnh hưởng ngầm đến mã sinh ra.

## 17. Biên dịch module và dependency

### 17.1. Module độc lập

DSL có thể chia chương trình thành module để tái sử dụng và quản lý quyền:

~~~text
module pricing
module customer
module shipping
~~~

Compiler cần xác định thứ tự phân tích và những khai báo được export.

### 17.2. Đồ thị phụ thuộc và vòng lặp

Nếu module A import B và B import A, compiler cần quy định có cho phép vòng phụ thuộc hay không.

Một số hệ thống có thể hỗ trợ vòng phụ thuộc bằng cách tách bước thu thập khai báo khỏi bước kiểm tra nội dung. Hệ thống khác yêu cầu đồ thị module không có chu trình.

### 17.3. Phiên bản dependency

Một module có thể được biên dịch với phiên bản thư viện hoặc schema cụ thể. Artifact cần ghi nhận dependency để runtime biết những thành phần nào cần thiết.

### 17.4. Dependency có thể không đáng tin cậy

Nếu DSL nạp plugin hoặc module từ bên ngoài, compiler cần kiểm tra nguồn, chữ ký, quyền và phiên bản. Việc phân giải dependency không nên tự động chạy mã không đáng tin cậy.

### 17.5. Tái sử dụng artifact

Module đã biên dịch có thể được lưu dưới dạng artifact. Artifact cần có metadata về phiên bản IR, compiler, target và dependency. Khi những điều kiện này không tương thích, cần biên dịch lại hoặc từ chối nạp.

## 18. An toàn khi biên dịch và thực thi DSL

### 18.1. Không tin tưởng văn bản nguồn

DSL có thể được người dùng nhập từ giao diện, file tải lên hoặc hệ thống khác. Compiler phải kiểm tra đầu vào thay vì giả định mọi chương trình đều đáng tin.

### 18.2. Giới hạn tài nguyên

Một chương trình có thể tạo AST quá sâu, literal quá dài, biểu thức đệ quy hoặc yêu cầu tối ưu tốn tài nguyên. Compiler nên có giới hạn:

- Kích thước nguồn.
- Độ sâu lồng nhau.
- Số lượng node.
- Thời gian biên dịch.
- Bộ nhớ.
- Số vòng lặp tối ưu hoặc giới hạn suy luận.

### 18.3. Runtime sandbox

Nếu DSL cho phép thực thi hành động, runtime có thể cần sandbox:

- Giới hạn thời gian và bộ nhớ.
- Giới hạn số lần gọi dịch vụ.
- Kiểm soát file và network access.
- Whitelist hàm được phép.
- Kiểm tra quyền tại thời điểm thực thi.
- Hủy hoặc timeout tác vụ.

### 18.4. Không dùng sinh mã nối chuỗi thiếu kiểm soát

Khi sinh Java, SQL hoặc shell command, không nên ghép trực tiếp tên và giá trị người dùng vào chuỗi mã. Cần validate identifier, escape theo đúng ngữ cảnh hoặc dùng API tham số hóa và AST builder.

### 18.5. Phân biệt compile-time và runtime authority

Compiler có thể kiểm tra một hành động được khai báo trong API, nhưng runtime vẫn cần xác minh quyền của người thực hiện và trạng thái tài nguyên thực tế.

### 18.6. Không thực thi hàm tùy ý trong constant evaluation

Nếu compiler đánh giá biểu thức hằng, chỉ nên cho phép các thao tác thuần và an toàn đã được quy định. Không nên chạy tùy tiện plugin, truy cập mạng hoặc ghi dữ liệu trong giai đoạn build.

## 19. Kiểm thử compiler DSL

### 19.1. Kiểm thử lexer

Kiểm tra token cho:

- Từ khóa và định danh.
- Số, chuỗi, ngày và đơn vị.
- Escape sequence.
- Comment và khoảng trắng.
- Ký tự Unicode.
- Token lỗi và vị trí nguồn.

### 19.2. Kiểm thử parser

Kiểm tra:

- Cấu trúc hợp lệ.
- Độ ưu tiên toán tử.
- Kết hợp trái/phải.
- Khối lồng nhau.
- Biểu thức thiếu token.
- Phục hồi sau lỗi.

### 19.3. Kiểm thử semantic analyzer

Kiểm tra:

- Tên hợp lệ và không hợp lệ.
- Kiểu tương thích và không tương thích.
- Overload.
- Generic và suy luận kiểu.
- Ràng buộc miền.
- Luồng điều khiển.
- Đơn vị và bất biến.

### 19.4. Kiểm thử IR

Kiểm tra AST đầu vào được chuyển thành IR mong đợi. Có thể so sánh cấu trúc IR hoặc dạng in chuẩn hóa.

### 19.5. Kiểm thử backend

Kiểm tra mã sinh ra:

- Có cú pháp hợp lệ.
- Bảo toàn giá trị và thứ tự đánh giá.
- Xử lý đúng literal và tên.
- Tương thích với target.
- Giữ source map.

### 19.6. Kiểm thử end-to-end

Chạy chương trình DSL qua toàn bộ pipeline và so sánh kết quả với hành vi mong đợi. Với DSL quy tắc, có thể kiểm tra quyết định và hành động. Với DSL truy vấn, có thể so sánh kết quả truy vấn trên fixture.

### 19.7. Kiểm thử differential

Nếu có cả interpreter và compiler backend, chạy cùng một chương trình trên hai đường thực thi và so sánh kết quả. Khác biệt có thể chỉ ra lỗi trong optimizer, code generator hoặc runtime.

### 19.8. Kiểm thử regression

Mỗi lỗi compiler đã sửa nên có một ví dụ tái hiện để bảo đảm thay đổi sau này không làm lỗi quay lại.

## 20. Hiệu năng và quan sát pipeline

### 20.1. Đo theo từng giai đoạn

Không nên chỉ đo tổng thời gian compile. Có thể ghi nhận:

- Thời gian lexer.
- Thời gian parser.
- Thời gian name resolution.
- Thời gian type checking.
- Thời gian optimization.
- Thời gian code generation.
- Số node AST và IR.
- Kích thước artifact.

Thông tin này giúp xác định giai đoạn đang là nút thắt.

### 20.2. Tránh tối ưu sớm

Trước khi thêm cache hoặc thuật toán phức tạp, cần đo workload thực tế. Với DSL nhỏ, thời gian parse có thể không đáng kể; chi phí lớn hơn có thể nằm ở truy vấn schema hoặc sinh SQL.

### 20.3. Compiler telemetry

Telemetry có thể ghi số liệu tổng hợp về thời gian và lỗi, nhưng không nên gửi toàn bộ nguồn DSL hoặc dữ liệu nghiệp vụ nhạy cảm nếu không có cơ sở và chính sách phù hợp.

### 20.4. Theo dõi runtime riêng

Thời gian biên dịch và thời gian thực thi là hai đại lượng khác nhau. Một chương trình compile nhanh có thể chạy chậm; một chương trình compile lâu có thể chạy rất nhanh nhờ tối ưu.

## 21. Phiên bản compiler, IR và tương thích

### 21.1. Phiên bản ngôn ngữ

DSL có thể thay đổi grammar hoặc ngữ nghĩa qua phiên bản. Source có thể ghi language version hoặc nhận phiên bản từ cấu hình dự án.

### 21.2. Phiên bản compiler

Compiler version nhận diện implementation đã tạo artifact. Hai compiler cùng hỗ trợ một phiên bản DSL vẫn có thể tạo IR khác nhau do thay đổi backend hoặc tối ưu.

### 21.3. Phiên bản IR

Nếu IR được lưu hoặc trao đổi, nó cần version. Runtime phải biết cách đọc version đó và từ chối hoặc chuyển đổi khi không tương thích.

### 21.4. Phiên bản target

Một backend có thể sinh mã cho nhiều target. Artifact cần ghi target và những capability cần thiết.

### 21.5. Tái biên dịch

Khi compiler hoặc schema thay đổi, hệ thống cần quyết định artifact cũ còn hợp lệ không. Không nên mặc nhiên nạp artifact chỉ vì file vẫn tồn tại.

## 22. Những lựa chọn kiến trúc phổ biến

### 22.1. AST interpreter

Phù hợp khi DSL nhỏ, thay đổi nhanh và cần triển khai đơn giản. Runtime duyệt AST trực tiếp.

### 22.2. AST sang IR rồi interpreter

Phù hợp khi muốn tách cú pháp và thực thi, chuẩn hóa nhiều dạng nguồn hoặc áp dụng tối ưu cơ bản.

### 22.3. IR sang bytecode

Phù hợp khi cần runtime riêng, kiểm soát thực thi, cache artifact và có thể tối ưu theo instruction.

### 22.4. Transpiler

Phù hợp khi có thể tận dụng compiler, thư viện và công cụ của ngôn ngữ đích. Cần quản lý source map, tương thích target và an toàn khi sinh mã.

### 22.5. Compiler truy vấn

Phù hợp với DSL truy vấn hoặc phân tích dữ liệu. Backend thường tạo query plan hoặc SQL, còn database thực hiện phần lớn công việc.

### 22.6. Chọn kiến trúc theo mục tiêu

| Nhu cầu | Hướng thường phù hợp |
|---|---|
| DSL cấu hình đơn giản | Parse thành object hoặc cấu hình |
| Quy tắc cần thay đổi linh hoạt | AST hoặc IR interpreter |
| Chương trình chạy lâu, cần hiệu năng | IR, bytecode hoặc JIT |
| Tận dụng nền tảng có sẵn | Transpiler |
| Truy vấn dữ liệu | Query planner hoặc SQL backend |
| Chạy mã không đáng tin cậy | IR/bytecode có sandbox và giới hạn rõ |

Không có kiến trúc duy nhất phù hợp cho mọi DSL. Quyết định nên dựa trên độ phức tạp ngôn ngữ, hiệu năng, tính linh hoạt, khả năng debug và yêu cầu an toàn.

## 23. Những lỗi thiết kế thường gặp

### 23.1. Gộp mọi bước vào một hàm lớn

Một hàm vừa parse, tra tên, kiểm tra kiểu và sinh mã sẽ khó kiểm thử và khó xác định nguyên nhân lỗi. Tách pass theo trách nhiệm giúp compiler dễ mở rộng.

### 23.2. Sinh mã trước khi kiểm tra ngữ nghĩa

Nếu backend nhận AST chưa được kiểm tra, nó có thể phải tự xử lý tên chưa biết, kiểu sai hoặc cấu trúc không hợp lệ. Nên xác định hợp đồng đầu vào rõ cho backend.

### 23.3. Dùng chuỗi thay thế để sinh mã

Thay từ khóa bằng chuỗi khác không đủ để biên dịch DSL có cấu trúc. Nó dễ nhầm tên, literal, comment, precedence và escaping. Nên sinh mã từ AST hoặc IR.

### 23.4. Không giữ source span

Nếu bỏ vị trí nguồn, diagnostic và debug sẽ khó liên kết với chương trình người dùng viết.

### 23.5. Tối ưu làm thay đổi ngữ nghĩa

Tái sắp xếp phép tính có thể thay đổi kết quả khi có số thực, overflow hoặc tác dụng phụ. Mỗi phép tối ưu cần điều kiện áp dụng rõ.

### 23.6. Không version hóa artifact

IR hoặc bytecode cũ có thể bị runtime mới diễn giải sai. Cần metadata version và chính sách tương thích.

### 23.7. Tin cậy đầu vào khi sinh mã

Tên hoặc literal người dùng có thể tạo ra cú pháp đích không hợp lệ hoặc injection nếu được nối chuỗi thiếu kiểm soát. Backend cần dùng builder, escaping theo ngữ cảnh và validation.

### 23.8. Không phân biệt compile error với runtime error

Lỗi compile cho biết chương trình không đáp ứng hợp đồng tĩnh. Lỗi runtime cho biết một hành động không hoàn tất trong điều kiện thực tế. Trộn hai loại khiến người dùng khó xác định nơi sửa.

## 24. Quy trình xây dựng compiler DSL

Một quy trình phát triển có thể đi theo các bước:

1. **Xác định hợp đồng ngôn ngữ:** grammar, kiểu, ngữ nghĩa và giới hạn.
2. **Xác định target:** interpreter, IR, bytecode, SQL, mã nguồn khác hoặc cấu hình.
3. **Thiết kế AST:** node rõ ràng, giữ source span và metadata cần thiết.
4. **Xây lexer và parser:** tạo token, parse tree và AST.
5. **Xây symbol model:** scope, import, khai báo và phân giải tên.
6. **Xây type checker:** suy luận kiểu, kiểm tra phép toán, hàm và generic.
7. **Xây semantic validation:** kiểm tra bất biến và quy tắc miền.
8. **Thiết kế IR:** xác định thao tác, kiểu và semantics của IR.
9. **Xây optimizer:** chỉ áp dụng phép biến đổi bảo toàn ngữ nghĩa.
10. **Xây backend:** sinh đầu ra theo target và giữ source mapping.
11. **Xây runtime:** cung cấp context, API, quyền và xử lý lỗi.
12. **Kiểm thử pipeline:** unit test từng pass, end-to-end, differential và regression.
13. **Quản lý version và cache:** ràng buộc artifact với compiler, schema và target.
14. **Quan sát và vận hành:** đo hiệu năng, diagnostic và giới hạn tài nguyên.

## 25. Ví dụ tổng hợp: compiler cho DSL tính phí vận chuyển

Giả sử DSL cho phép mô tả quy tắc:

~~~text
rule FreeShippingForGold {
    when customer.tier == GOLD
         and order.total >= 1000000 VND
    then shippingFee = Money.zero("VND")
}
~~~

### 25.1. Lexer

Lexer nhận diện từ khóa rule, when, and, then; tên FreeShippingForGold, customer, tier, order, total, shippingFee; toán tử so sánh; literal tiền và chuỗi VND.

### 25.2. Parser

Parser tạo RuleDeclaration có điều kiện AND và một phép gán ở phần hành động.

### 25.3. Name resolution

Resolver tìm customer và order trong context của rule, tra thuộc tính tier và total, đồng thời xác định shippingFee có thể được gán trong ngữ cảnh hiện tại hay không.

### 25.4. Type checking

Compiler xác nhận:

- customer.tier có kiểu CustomerTier.
- GOLD là một giá trị CustomerTier.
- order.total có kiểu Money.
- Literal 1000000 VND có kiểu Money.
- Phép AND nhận hai Boolean.
- Phép gán shippingFee nhận Money.

### 25.5. Domain validation

Compiler hoặc runtime kiểm tra quy tắc miễn phí vận chuyển có được phép với loại khách hàng và đơn hàng tương ứng hay không. Nếu điều kiện phụ thuộc dữ liệu thực tế, phần kiểm tra đó diễn ra lúc chạy.

### 25.6. IR

~~~text
RULE FreeShippingForGold
  CONDITION:
    AND
      EQUALS
        LOAD customer.tier
        CONST CustomerTier.GOLD
      GREATER_OR_EQUAL
        LOAD order.total
        CONST Money(1000000, VND)
  ACTION:
    STORE shippingFee
      CALL Money.zero(VND)
~~~

### 25.7. Thực thi

Runtime nhận context gồm customer và order, đánh giá điều kiện, rồi thực hiện hành động nếu điều kiện đúng. Runtime cần kiểm tra context, quyền và trạng thái tài nguyên theo hợp đồng.

### 25.8. Lỗi và source mapping

Nếu runtime không thể cập nhật phí vận chuyển, nó có thể báo lỗi gắn với hành động gán shippingFee trong file DSL. Nếu compiler phát hiện total có kiểu String, diagnostic xuất hiện trước khi tạo artifact có thể thực thi.

Ví dụ này thể hiện ranh giới giữa compile-time validation và runtime validation, đồng thời cho thấy vì sao AST, IR và source mapping cần được phối hợp.

## 26. Câu hỏi tự đánh giá

1. Biên dịch DSL khác với thay thế văn bản như thế nào?
2. Front end, middle end và backend đảm nhiệm những việc gì?
3. Lexer và parser tạo ra những dạng dữ liệu nào?
4. AST khác parse tree ở điểm nào?
5. Vì sao compiler cần name resolution và type checking trước code generation?
6. IR giúp tách front end khỏi backend như thế nào?
7. Constant folding và common subexpression elimination là gì?
8. Khi nào nên thông dịch AST, thông dịch IR hoặc sinh bytecode?
9. Source map giúp debug mã sinh ra như thế nào?
10. Vì sao cache compiler phải phụ thuộc vào schema, compiler version và target?
11. Những giới hạn nào cần có khi biên dịch và thực thi DSL không đáng tin cậy?
12. Làm thế nào để kiểm tra interpreter và compiler backend cho kết quả tương đương?

## Kết luận

Biên dịch DSL là quá trình chuyển văn bản đặc tả miền thành một dạng biểu diễn có thể thực thi hoặc được hệ thống khác tiếp nhận. Một compiler thường phân tích token và cú pháp, xây dựng AST, phân giải tên, kiểm tra kiểu và ngữ nghĩa, tạo IR, tối ưu rồi sinh mã hoặc artifact. Runtime cung cấp dữ liệu, API, quyền và môi trường thực thi.

Kiến trúc có thể dùng interpreter, IR interpreter, bytecode, transpiler, AOT hoặc JIT. Lựa chọn phụ thuộc mục tiêu của DSL về hiệu năng, tính linh hoạt, khả năng debug, bảo mật và chi phí duy trì. Một pipeline tốt giữ rõ trách nhiệm giữa các pass, bảo toàn liên kết với nguồn, tạo diagnostic hữu ích, version hóa artifact và chỉ áp dụng tối ưu khi ngữ nghĩa được giữ nguyên. Nhờ vậy, DSL có thể phát triển thành một ngôn ngữ chuyên biệt đáng tin cậy thay vì chỉ là tập quy tắc thay thế văn bản.
