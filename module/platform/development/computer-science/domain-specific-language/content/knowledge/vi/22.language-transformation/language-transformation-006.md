# Mô hình trung gian cho chuyển đổi

## Vai trò của mô hình trung gian trong biến đổi ngôn ngữ

Trong phát triển DSL, một hệ thống thường cần chuyển chương trình hoặc mô hình từ ngôn ngữ này sang một biểu diễn khác. Nguồn có thể là DSL nghiệp vụ, mô hình miền, AST, sơ đồ hoặc cấu hình; đích có thể là một DSL khác, mô hình nền tảng, mã nguồn, truy vấn, workflow hay một artifact có thể thực thi.

Nếu chuyển trực tiếp từ từng loại nguồn sang từng loại đích, logic chuyển đổi dễ bị gắn chặt với cú pháp và cấu trúc riêng của mỗi ngôn ngữ. Khi số lượng ngôn ngữ nguồn và đích tăng, số ánh xạ cần xây dựng cũng tăng nhanh. **Mô hình trung gian (intermediate model)** giải quyết vấn đề này bằng cách cung cấp một biểu diễn chung ở giữa: nguồn được chuyển thành mô hình trung gian, sau đó mô hình này được chuyển tiếp sang một hoặc nhiều đích.

Một cấu trúc tổng quát:

~~~text
Source language / source model
             |
             v
     Source-to-intermediate
             |
             v
      Intermediate model
             |
             v
     Intermediate-to-target
             |
             v
       Target model / code
~~~

Mô hình trung gian không chỉ là một bản sao của mô hình nguồn với tên phần tử khác. Nó được thiết kế để giữ lại những khái niệm và quan hệ cần thiết cho mục tiêu chuyển đổi, đồng thời loại bỏ hoặc chuẩn hóa các khác biệt cú pháp không còn quan trọng.

Ví dụ, một DSL mô tả quy tắc nghiệp vụ có thể dùng cú pháp riêng cho điều kiện, thuộc tính và hành động. Hệ thống có thể chuyển các rule thành mô hình trung gian gồm điều kiện logic, phép so sánh, tham chiếu thuộc tính và thao tác cập nhật. Từ mô hình này, backend có thể sinh SQL, Java, biểu diễn cho rule engine hoặc một decision table.

Mô hình trung gian hữu ích khi:

- Có nhiều ngôn ngữ nguồn cần chuyển về cùng một dạng ngữ nghĩa.
- Một mô hình cần được sinh ra nhiều nền tảng đích.
- Các phép chuyển đổi cần chia thành nhiều bước có thể kiểm tra độc lập.
- Cần chuẩn hóa, phân tích hoặc tối ưu trước khi sinh đầu ra.
- Cần giữ liên kết từ phần tử đích về nguồn để debug và giải thích.
- Cấu trúc nguồn và đích khác nhau đáng kể.
- Nhiều nhóm phát triển cần thống nhất một hợp đồng trao đổi mô hình.

Không phải mọi chuyển đổi đều cần một mô hình trung gian riêng. Với một phép đổi tên trường đơn giản giữa hai schema nhỏ, ánh xạ trực tiếp có thể dễ hiểu hơn. Mô hình trung gian đáng đầu tư khi nó làm giảm phụ thuộc, tăng khả năng tái sử dụng hoặc tạo ra một ranh giới ngữ nghĩa ổn định.

## Mô hình trung gian là gì?

Mô hình trung gian là một mô hình được tạo ra trong quá trình chuyển đổi và dùng làm đầu vào cho các phép biến đổi tiếp theo. Nó có metamodel hoặc schema xác định các loại phần tử, thuộc tính, quan hệ và ràng buộc hợp lệ.

Một mô hình trung gian thường có các đặc điểm:

- Biểu diễn các khái niệm cần cho một hoặc nhiều mục tiêu chuyển đổi.
- Có cấu trúc độc lập tương đối với cú pháp cụ thể của nguồn.
- Chuẩn hóa những khác biệt không cần thiết giữa các nguồn.
- Giữ các thông tin ngữ nghĩa quan trọng như kiểu, quan hệ, thứ tự và điều kiện.
- Có thể được kiểm tra bằng invariant hoặc validation rule.
- Có thể được chuyển đổi tiếp mà không cần đọc lại văn bản nguồn.
- Có thể giữ trace link về phần tử nguồn và metadata phục vụ công cụ.

Mô hình trung gian có thể là cây, đồ thị, tập đối tượng có quan hệ, bảng dữ liệu, biểu diễn lệnh hoặc một schema có cấu trúc. Hình dạng phụ thuộc miền và loại chuyển đổi.

### Ví dụ đơn giản

Giả sử DSL nguồn mô tả quy tắc:

~~~text
RULE "Free shipping"
WHEN order.total >= 500000
THEN shipment.fee = 0
~~~

AST nguồn có thể giữ các chi tiết cú pháp như keyword RULE, WHEN, THEN, literal và dấu chấm trong tên thuộc tính.

Mô hình trung gian có thể chuẩn hóa thành:

~~~text
RuleModel
  name: "Free shipping"
  condition:
    GreaterThanOrEqual
      left: PropertyRef(Order.total)
      right: Constant(500000, VND)
  actions:
    SetProperty
      target: PropertyRef(Shipment.fee)
      value: Constant(0, VND)
~~~

Mô hình này diễn tả ý nghĩa của rule mà không phụ thuộc trực tiếp vào cách viết keyword hoặc dấu phân cách trong DSL. Một backend SQL có thể chuyển condition thành WHERE và action thành UPDATE; một backend Java có thể sinh biểu thức điều kiện và câu lệnh gán.

Điều quan trọng là mô hình trung gian phải giữ đủ thông tin. Nếu bỏ mất đơn vị tiền tệ, kiểu của thuộc tính hoặc thứ tự hành động, backend có thể tạo kết quả sai dù mô hình vẫn hợp lệ về mặt cấu trúc.

## Phân biệt mô hình trung gian, AST và IR

Các thuật ngữ AST, IR và intermediate model có vùng giao nhau, nhưng thường nhấn mạnh các mục đích khác nhau.

| Biểu diễn | Trọng tâm | Ví dụ |
|---|---|---|
| CST | Giữ cấu trúc cú pháp gần với văn bản | Node chứa dấu ngoặc, dấu phẩy, comment |
| AST | Cấu trúc trừu tượng của chương trình nguồn | Rule, Expression, FunctionCall |
| Intermediate model | Mô hình chung phục vụ chuyển đổi giữa các ngôn ngữ hoặc nền tảng | BusinessRule, Condition, Action |
| Compiler IR | Biểu diễn thuận tiện cho phân tích, tối ưu và sinh mã | BasicBlock, Instruction, SSA value |
| Target model | Mô hình tuân theo metamodel hoặc schema đích | SQL query model, workflow model |

Một AST có thể được dùng làm mô hình trung gian nếu nó đủ độc lập với cú pháp nguồn và đáp ứng hợp đồng của các bước sau. Ngược lại, một intermediate model có thể rất gần IR của compiler nếu mục tiêu là sinh bytecode hoặc thực thi.

Điểm phân biệt nằm ở mục đích và hợp đồng, không chỉ ở tên gọi. AST thường phản ánh ngôn ngữ nguồn; IR thường tối ưu cho compiler backend; intermediate model trong model transformation thường được thiết kế như một ngôn ngữ biểu diễn chung giữa các mô hình hoặc nền tảng.

### Khi nào AST có thể đóng vai trò mô hình trung gian?

AST có thể dùng làm mô hình trung gian khi:

- Có một ngôn ngữ nguồn chính.
- Cấu trúc AST đã biểu diễn đủ ngữ nghĩa cần cho đích.
- Các backend có thể dùng chung AST mà không phải hiểu chi tiết cú pháp.
- Thay đổi grammar không làm thay đổi hợp đồng AST quá thường xuyên.
- Các thông tin kiểu và reference được bổ sung theo cách ổn định.

Nếu AST chứa quá nhiều chi tiết cú pháp hoặc tên node phản ánh grammar cụ thể, backend sẽ bị phụ thuộc vào parser. Khi đó, một bước lowering sang mô hình ngữ nghĩa độc lập hơn có thể hữu ích.

### Khi nào cần IR riêng?

IR riêng phù hợp khi cần:

- Chuẩn hóa nhiều nguồn khác nhau.
- Hạ các cấu trúc cấp cao thành thao tác chung.
- Tối ưu hóa hoặc phân tích luồng dữ liệu.
- Biểu diễn control flow rõ ràng.
- Hỗ trợ nhiều target có semantics khác nhau.
- Tách vòng đời grammar khỏi vòng đời backend.
- Lưu hoặc trao đổi mô hình giữa công cụ độc lập.

Không nên tạo nhiều lớp biểu diễn chỉ để có thêm tầng trong sơ đồ. Mỗi tầng cần giải quyết một khác biệt hoặc nhu cầu cụ thể và có hợp đồng được mô tả rõ.

## Metamodel của mô hình trung gian

Metamodel định nghĩa ngôn ngữ mà mô hình trung gian được phép sử dụng. Nó mô tả metaclass, thuộc tính, quan hệ, kiểu dữ liệu, bội số và các ràng buộc.

Ví dụ, metamodel cho rule trung gian:

~~~text
RuleModel
  name: String
  condition: Expression [1]
  actions: Action [1..*]

Expression (abstract)
  BinaryExpression
  PropertyReference
  Constant

BinaryExpression
  operator: ComparisonOperator | LogicalOperator
  left: Expression [1]
  right: Expression [1]

PropertyReference
  ownerType: TypeReference
  property: PropertyReference

Constant
  value: Value
  valueType: TypeReference
  unit: UnitReference [0..1]

Action (abstract)
  SetProperty
  InvokeOperation
~~~

Metamodel giúp các thành phần khác nhau hiểu cùng một cấu trúc. Source-to-intermediate transformer phải tạo instance tuân theo metamodel. Intermediate-to-target transformer có thể dựa trên những invariant đã được xác nhận.

### Thành phần cốt lõi của metamodel

Một metamodel thường xác định:

- **Metaclass:** loại phần tử, ví dụ RuleModel, Expression, Action.
- **Attribute:** dữ liệu đơn giản như name, operator hoặc literal value.
- **Reference:** liên kết đến phần tử khác trong mô hình.
- **Containment:** quan hệ sở hữu cấu trúc giữa container và phần tử con.
- **Multiplicity:** số lượng phần tử được phép tham gia quan hệ.
- **Inheritance:** quan hệ kế thừa giữa các metaclass.
- **Enumeration:** tập giá trị hữu hạn như ComparisonOperator.
- **Constraint:** điều kiện mà mọi instance hợp lệ phải thỏa mãn.

Metamodel không chỉ là schema lưu trữ. Nó là hợp đồng ngữ nghĩa của mô hình trung gian. Nếu metamodel không thể biểu diễn một trường hợp hợp lệ của nguồn, transformer sẽ phải làm mất thông tin hoặc thêm ngoại lệ ngoài mô hình.

### Mô hình và metamodel

Cần phân biệt hai cấp:

- Metamodel mô tả những loại cấu trúc có thể tồn tại.
- Model là một instance cụ thể tuân theo metamodel.

Ví dụ, RuleModel là metaclass; rule "Free shipping" là một model element thuộc metaclass đó. Một mô hình trung gian hợp lệ phải conform to metamodel, tức là mọi phần tử, thuộc tính và quan hệ đều tuân thủ định nghĩa.

Trong các framework như Eclipse Modeling Framework (EMF), Ecore được dùng để mô tả metamodel; các model instance có thể được lưu dưới dạng XMI. Các công cụ có thể sinh class, editor, validator và API điều hướng từ metamodel. Với mô hình tự xây, schema có thể được biểu diễn bằng class, record, interface hoặc định dạng dữ liệu có kiểm tra.

## Các mức trừu tượng của mô hình trung gian

Một mô hình trung gian có thể giữ khái niệm ở mức nghiệp vụ hoặc hạ xuống mức gần nền tảng. Lựa chọn mức trừu tượng ảnh hưởng đến khả năng tái sử dụng.

### Mô hình trung gian cấp cao

Mô hình cấp cao giữ các khái niệm miền:

~~~text
DiscountRule
  customerSegment: VIP
  minimumOrder: Money(500000, VND)
  discount:
    Percentage(10)
~~~

Ưu điểm là gần với ý nghĩa nghiệp vụ, dễ đọc, dễ validate và có thể chuyển sang nhiều target. Nhược điểm là backend phải hiểu các khái niệm cấp cao và tự hạ chúng theo target.

### Mô hình trung gian cấp thấp

Mô hình cấp thấp biểu diễn thao tác gần với execution:

~~~text
v1 = load customer.segment
v2 = const VIP
v3 = equal v1, v2
v4 = load order.total
v5 = const 500000
v6 = greater_equal v4, v5
v7 = and v3, v6
branch_if_false v7, L1
call apply_discount, 10
L1:
~~~

Mô hình này dễ ánh xạ sang bytecode hoặc instruction set, nhưng ít giữ ý nghĩa nghiệp vụ. Một backend khác có thể phải khôi phục nhiều thông tin hoặc khó tối ưu theo domain.

### Mô hình nhiều tầng

Một kiến trúc có thể dùng high-level model rồi hạ xuống low-level model:

~~~text
Source DSL
    |
    v
Domain Intermediate Model
    |
    v
Platform-independent Model
    |
    v
Platform-specific Model
    |
    v
Target code / artifact
~~~

Mỗi tầng có một mục tiêu. Domain model giữ ngữ nghĩa nghiệp vụ; platform-independent model mô tả giải pháp không phụ thuộc công nghệ; platform-specific model bổ sung chi tiết của nền tảng; backend sinh artifact.

Cách tiếp cận này phù hợp với hệ thống có nhiều nền tảng hoặc vòng đời mô hình dài. Với DSL nhỏ, một intermediate model duy nhất có thể đủ.

## Vì sao cần mô hình trung gian khi chuyển đổi?

### Giảm phụ thuộc giữa nguồn và đích

Nếu có N ngôn ngữ nguồn và M nền tảng đích, cách chuyển đổi trực tiếp có thể cần nhiều ánh xạ riêng cho từng cặp nguồn-đích. Với một mô hình chung, mỗi nguồn chỉ cần một phép chuyển sang mô hình trung gian và mỗi đích chỉ cần một phép chuyển từ mô hình trung gian.

~~~text
Without intermediate model:

Source A ---> Target X
Source A ---> Target Y
Source B ---> Target X
Source B ---> Target Y

With intermediate model:

Source A --\
            \
Source B ----> Intermediate Model ---> Target X
            /                       \-> Target Y
Source C --/
~~~

Nếu mọi nguồn và đích đều dùng cùng một intermediate model, số transformer chính có thể giảm từ N × M xuống N + M. Đây là lợi ích về cấu trúc, không phải cam kết rằng mọi transformer đều có chi phí bằng nhau.

### Chuẩn hóa khác biệt cú pháp

Hai DSL có thể viết cùng một ý nghĩa theo cách khác nhau:

~~~text
IF order.total >= 500000 THEN freeShipping()
~~~

~~~text
WHEN order.total >= 500000
THEN shipment.fee = 0
~~~

Nếu semantics của hai nguồn tương đương theo miền, chúng có thể được chuẩn hóa thành cùng một RuleModel. Backend không cần biết nguồn dùng IF hay WHEN.

### Tách ngữ nghĩa khỏi cú pháp

Mô hình trung gian có thể lưu kiểu, đơn vị, symbol reference, thứ tự đánh giá và các ràng buộc mà cú pháp không thể hiện đầy đủ. Nhờ đó, phép chuyển đổi sau không phải đoán ý nghĩa từ chuỗi tên hoặc token.

### Tái sử dụng phép phân tích và validation

Một mô hình trung gian chung có thể được kiểm tra một lần rồi dùng cho nhiều target. Các kiểm tra như kiểu dữ liệu, quan hệ bắt buộc, khả năng truy cập hoặc tính nhất quán miền có thể được thực hiện trước khi sinh mã.

### Hỗ trợ nhiều bước biến đổi

Có thể tách chuyển đổi phức tạp thành các bước nhỏ:

- Parse nguồn thành AST.
- Resolve tên và kiểu.
- Chuẩn hóa thành domain model.
- Hạ domain model sang platform-independent model.
- Bổ sung chi tiết target.
- Sinh artifact.

Mỗi bước có thể được kiểm tra và thay thế độc lập.

## Thiết kế một mô hình trung gian tốt

Không có một metamodel chung phù hợp với mọi miền. Mô hình trung gian phải được thiết kế dựa trên ngữ nghĩa cần bảo toàn và các đích cần hỗ trợ.

### Bắt đầu từ semantics, không bắt đầu từ cú pháp

Hãy liệt kê các khái niệm mà chương trình có ý nghĩa trong miền: entity, operation, condition, constraint, event, resource, workflow step hoặc query. Sau đó xác định các quan hệ và thuộc tính cần thiết.

Ví dụ, nếu DSL mô tả workflow, mô hình trung gian nên thể hiện rõ:

- Các bước xử lý.
- Quan hệ nối giữa bước.
- Điều kiện rẽ nhánh.
- Dữ liệu vào và ra.
- Retry và timeout.
- Điểm bắt đầu và kết thúc.
- Các phụ thuộc hoặc vòng lặp được phép.

Không nên tạo metaclass cho từng từ khóa cú pháp nếu từ khóa đó không biểu diễn một khái niệm ngữ nghĩa riêng.

### Giữ đủ thông tin cần thiết

Mỗi phép chuyển đổi có thể làm mất thông tin nếu mô hình trung gian không chứa trường tương ứng. Ví dụ:

- Bỏ đơn vị của quantity có thể làm sai phép tính.
- Bỏ thứ tự action có thể thay đổi side effect.
- Bỏ kiểu của literal có thể gây suy luận khác ở target.
- Bỏ thông tin nullability có thể thay đổi hành vi.
- Bỏ timezone có thể làm thay đổi thời điểm.
- Bỏ policy hoặc permission có thể tạo hành động không hợp lệ.

Có thể dùng ma trận thông tin để ghi rõ thông tin nào được giữ, chuẩn hóa, suy ra hoặc loại bỏ ở mỗi bước.

### Tránh gắn chặt với một target

Nếu intermediate model có quá nhiều class hoặc field riêng cho một backend, các target khác sẽ phải xử lý cấu trúc không liên quan. Nên giữ mô hình độc lập với nền tảng ở phần cốt lõi và đưa chi tiết target vào một extension model hoặc bước lowering riêng.

Tuy nhiên, không cần cố tạo abstraction chung cho mọi nền tảng nếu các semantics thực sự khác nhau. Một mô hình chung quá rộng có thể trở nên mơ hồ và khó validate.

### Biểu diễn rõ kiểu và đơn vị

Các giá trị số nên có type và unit khi miền yêu cầu. Ví dụ:

~~~text
Constant
  value: 500000
  type: Decimal
  unit: VND
~~~

Không nên chỉ lưu 500000 và để backend tự suy ra đây là tiền, số lượng hay khoảng cách. Cùng một giá trị số có thể có ý nghĩa hoàn toàn khác nhau.

### Quy định danh tính và quan hệ

Mô hình cần xác định phần tử nào có ID ổn định, phần tử nào là containment và phần tử nào là reference. Nhiều nguồn có thể tham chiếu cùng một khai báo hoặc resource; không nên nhân bản đối tượng đích nếu cần giữ danh tính dùng chung.

### Giữ metadata có ích

Metadata có thể gồm:

- Source location.
- Comment hoặc documentation.
- Annotation.
- Origin của phần tử được sinh.
- Version của metamodel.
- Tên gốc và tên chuẩn hóa.
- Trạng thái validation.
- Trace identifier.
- Thông tin phục vụ debug hoặc audit.

Metadata nên được tổ chức có chủ đích. Không nên nhồi mọi dữ liệu vào một map không kiểu vì làm mất hợp đồng và khó kiểm tra.

## Chuyển đổi từ mô hình nguồn sang mô hình trung gian

Source-to-intermediate transformation chuyển model nguồn sang một biểu diễn đã chuẩn hóa. Nguồn có thể là AST của DSL, UML model, schema, JSON hoặc một mô hình được tạo bởi công cụ khác.

Một transformer thường thực hiện:

1. Đọc phần tử nguồn.
2. Xác định khái niệm ngữ nghĩa tương ứng.
3. Tạo phần tử trung gian.
4. Chuyển thuộc tính và giá trị.
5. Chuyển quan hệ containment/reference.
6. Chuẩn hóa tên, kiểu hoặc đơn vị nếu quy tắc yêu cầu.
7. Tạo trace link giữa nguồn và đích.
8. Báo lỗi nếu nguồn có cấu trúc không thể biểu diễn.

### Mapping giữa metamodel nguồn và metamodel trung gian

Giả sử metamodel nguồn có:

~~~text
SourceRule
  title
  whenExpression
  thenStatement
~~~

Metamodel trung gian có:

~~~text
RuleModel
  name
  condition
  actions
~~~

Mapping có thể được mô tả:

| Phần tử nguồn | Phần tử trung gian | Quy tắc |
|---|---|---|
| SourceRule.title | RuleModel.name | Sao chép hoặc chuẩn hóa tên |
| SourceRule.whenExpression | RuleModel.condition | Chuyển đệ quy thành Expression |
| SourceRule.thenStatement | RuleModel.actions | Chuyển thành một hoặc nhiều Action |
| SourceExpression | Expression subtype | Chọn subtype theo ngữ nghĩa toán tử |
| SourceProperty | PropertyReference | Resolve theo schema miền |

Mapping không chỉ là gán field. Ví dụ, một câu lệnh nguồn có thể được tách thành nhiều action trung gian; nhiều node nguồn có thể được gộp thành một node trung gian; một tên nguồn có thể cần resolve thành reference có kiểu.

### Xử lý phần tử không tương thích

Nếu mô hình nguồn có một construct mà intermediate model không hỗ trợ, transformer cần chính sách rõ:

- Báo lỗi và dừng chuyển đổi.
- Giữ construct dưới dạng extension node nếu mô hình cho phép.
- Chuyển thành opaque payload để bước sau xử lý.
- Hạ construct thành các phần tử cơ bản tương đương.
- Yêu cầu cấu hình hoặc plugin mở rộng.

Không nên âm thầm bỏ qua phần tử không được hỗ trợ. Điều đó có thể tạo mô hình trung gian hợp lệ về cấu trúc nhưng sai ngữ nghĩa.

## Chuyển đổi từ mô hình trung gian sang mô hình đích

Intermediate-to-target transformation ánh xạ các khái niệm chung sang cấu trúc mà nền tảng đích hiểu được.

Ví dụ, RuleModel có condition và action có thể được chuyển thành:

- Một câu SQL có WHERE và UPDATE.
- Một class Java có method evaluate.
- Một decision table.
- Một node graph cho workflow engine.
- Một cấu hình JSON cho rule runtime.

### Mapping đến nhiều target

Cùng một mô hình trung gian có thể có nhiều backend:

~~~text
                 +--> SQL model --> SQL text
Intermediate ----+--> Java model --> Java source
Rule model       +--> Decision table
                 +--> Rule bytecode
~~~

Mỗi backend cần hiểu rõ phần semantics mà target hỗ trợ. Nếu target không thể biểu diễn một tính năng, backend phải báo lỗi hoặc dùng một cơ chế runtime helper đã được định nghĩa.

### Kiểm tra khả năng biểu diễn của target

Không phải mọi mô hình trung gian đều có thể được chuyển sang mọi target. Ví dụ:

- Target không hỗ trợ vòng lặp.
- Target không có kiểu Decimal chính xác.
- Target không hỗ trợ transaction.
- Target không cho phép một loại function call.
- Target có giới hạn độ sâu hoặc số lượng node.
- Target dùng semantics null khác với DSL.

Có thể định nghĩa capability model cho backend:

~~~text
TargetCapabilities
  supportsRecursion: false
  supportsDecimal: true
  supportsTransactions: true
  maxExpressionDepth: 64
  supportedOperators: [...]
~~~

Trước hoặc trong khi chuyển đổi, backend kiểm tra capability và đưa diagnostics có vị trí nguồn. Cách này tốt hơn việc sinh artifact thiếu tính năng rồi để lỗi xuất hiện khi chạy.

## Traceability và transformation trace

Traceability là khả năng truy vết mối liên hệ giữa phần tử nguồn, phần tử trung gian và phần tử đích. Nó đặc biệt quan trọng khi một phép chuyển đổi tạo nhiều node, gộp node hoặc thay đổi cấu trúc đáng kể.

Ví dụ:

~~~text
Source Rule "Free shipping"
          |
          | trace
          v
Intermediate RuleModel #R17
          |
          +------> Target SQL predicate #P4
          |
          +------> Target update statement #U2
~~~

Một trace record có thể lưu:

~~~text
TraceLink
  sourceElementId
  intermediateElementId
  targetElementIds[]
  transformationRule
  sourceLocation
~~~

Traceability hỗ trợ:

- Điều hướng từ artifact về DSL nguồn.
- Giải thích vì sao một node đích được tạo.
- Debug lỗi chuyển đổi.
- Đồng bộ thay đổi.
- Phân tích tác động.
- Refactoring hoặc round-trip.
- Audit và chứng minh nguồn gốc của output.

### Quan hệ một-nhiều và nhiều-một

Không phải lúc nào một node nguồn cũng tương ứng với một node đích.

Một biểu thức nguồn có thể được hạ thành nhiều instruction. Ngược lại, một backend có thể gộp nhiều expression thành một predicate. Trace model cần hỗ trợ quan hệ một-nhiều, nhiều-một hoặc nhiều-nhiều nếu nghiệp vụ yêu cầu.

Không nên giả định trace là một map đơn giản từ source ID sang target ID. Khi cấu trúc biến đổi phức tạp, cần lưu loại quan hệ, vai trò và vị trí trong quá trình chuyển đổi.

### Traceability khác với source span

Source span xác định vị trí văn bản. Traceability xác định quan hệ giữa các phần tử qua nhiều mô hình. Một node trung gian có thể có source span nhưng vẫn cần trace link đến một phần tử model nguồn không phải văn bản. Hai cơ chế bổ trợ cho nhau.

## Bảo toàn ngữ nghĩa qua chuyển đổi

Mục tiêu quan trọng nhất của transformation là bảo toàn semantics theo hợp đồng. Một mô hình đích có thể khác hoàn toàn về cấu trúc nhưng vẫn phải biểu diễn hành vi tương đương của mô hình nguồn.

Ví dụ, biểu thức:

~~~text
a AND b
~~~

có thể được chuyển thành phép AND trong target. Nhưng nếu target đánh giá cả hai nhánh trong khi DSL nguồn dùng short-circuit evaluation, hành vi có thể thay đổi khi một nhánh có side effect hoặc phát sinh lỗi.

Các khía cạnh cần bảo toàn:

- Giá trị của biểu thức.
- Thứ tự đánh giá.
- Side effect.
- Exception và lỗi.
- Kiểu dữ liệu.
- Null và missing value.
- Độ chính xác số học.
- Đơn vị đo và quy tắc chuyển đổi.
- Thời gian, timezone và locale.
- Thứ tự collection nếu có ý nghĩa.
- Transaction và tính nguyên tử.
- Quyền và capability runtime.

### Quy tắc ngữ nghĩa cần được đặc tả

Một transformation không thể bảo toàn một semantics chưa được xác định. Trước khi xây mapping, cần ghi rõ những điều như:

- AND/OR có short-circuit không?
- So sánh với null trả về false, unknown hay exception?
- Phép chia số nguyên làm tròn theo cách nào?
- Hàm có thể có side effect không?
- Action được thực hiện theo thứ tự nào?
- Thứ tự kết quả truy vấn có được bảo đảm không?
- Một lỗi trong action làm dừng rule hay tiếp tục?

Nếu source và target có semantics khác nhau, transformer có thể cần sinh helper hoặc runtime adapter để mô phỏng hành vi nguồn.

### Kiểm tra tương đương

Tùy hệ thống, có thể dùng:

- So sánh kết quả thực thi trên cùng bộ dữ liệu.
- Differential testing giữa interpreter nguồn và target runtime.
- Kiểm tra property trên các biểu thức được sinh.
- Kiểm tra invariant của mô hình trước và sau transformation.
- Chứng minh tương đương hình thức cho các phép biến đổi quan trọng.
- Golden test cho artifact kết hợp test hành vi.

Không phải mọi transformation đều cần chứng minh hình thức, nhưng các quy tắc có tác động lớn nên có cách xác nhận rõ.

## Các kiểu transformation và vị trí của mô hình trung gian

### Model-to-model transformation (M2M)

M2M chuyển một model conform với metamodel nguồn thành model conform với metamodel đích. Intermediate model có thể là đích của bước đầu và nguồn của bước tiếp theo.

Ví dụ:

~~~text
Business Process Model
          |
          v
Platform-independent Workflow Model
          |
          v
Cloud Orchestration Model
~~~

M2M thường dùng trong model-driven engineering để chuyển mô hình nghiệp vụ sang mô hình kỹ thuật hoặc chuyển giữa các phiên bản metamodel.

### Model-to-text transformation (M2T)

M2T tạo văn bản từ model, chẳng hạn Java source, SQL, YAML hoặc tài liệu. Intermediate model có thể giúp backend không phải hiểu trực tiếp AST của mọi DSL.

Ví dụ:

~~~text
DSL AST
   |
   v
Typed Rule Model
   |
   v
Java source generator
   |
   v
Generated Java files
~~~

M2T cần chú ý escaping, encoding, định dạng và source mapping của mã được sinh. Một mô hình trung gian hợp lệ vẫn có thể tạo output sai nếu template hoặc generator xử lý tên và literal không an toàn.

### Text-to-model transformation (T2M)

T2M phân tích văn bản và tạo model. Parser DSL thường là một dạng T2M: source text chuyển thành AST. Một bước tiếp theo có thể chuyển AST thành intermediate model chuẩn hóa.

### Model-to-model-to-text

Một pipeline thường kết hợp nhiều kiểu:

~~~text
Text DSL
   |
   | T2M
   v
Source AST
   |
   | M2M
   v
Intermediate Model
   |
   | M2M
   v
Target Model
   |
   | M2T
   v
Generated Artifact
~~~

Việc chia tầng cho phép kiểm tra target model trước khi sinh văn bản và tái sử dụng generator cho nhiều nguồn.

## Các cách triển khai transformation

### Quy tắc mapping khai báo

Một cách tiếp cận là mô tả mapping bằng các rule khai báo. Mỗi rule xác định loại phần tử nguồn, điều kiện áp dụng và phần tử đích cần tạo.

Ví dụ giả định:

~~~text
rule MapRule {
  from: SourceRule s
  to: RuleModel r
  when: s.isEnabled
  map:
    r.name = normalize(s.title)
    r.condition = mapExpression(s.whenExpression)
    r.actions = mapActions(s.thenStatement)
}
~~~

Cách khai báo làm rõ quan hệ nguồn-đích và có thể được framework thực thi. Nó phù hợp khi mapping có tính cấu trúc và nhiều quy tắc tương tự.

### Transformation bằng mã lệnh

Có thể viết transformer bằng ngôn ngữ lập trình thông thường:

~~~java
RuleModel transform(SourceRule source) {
    RuleModel target = new RuleModel();
    target.setName(normalize(source.getTitle()));
    target.setCondition(transformExpression(source.getWhen()));
    target.getActions().addAll(transformActions(source.getThen()));
    return target;
}
~~~

Cách này linh hoạt, dễ dùng thư viện và phù hợp logic phức tạp. Tuy nhiên, mapping có thể bị phân tán trong nhiều hàm; cần giữ cấu trúc rõ và test từng quy tắc.

### Template-based transformation

Template có thể sinh model hoặc text dựa trên dữ liệu trung gian. Ví dụ, một template Java đọc RuleModel và tạo class evaluate. Template dễ đọc với output dạng văn bản, nhưng không phải lựa chọn tốt nhất cho mọi phép biến đổi cấu trúc.

### Graph transformation

Nếu model là graph, transformation có thể được mô tả bằng pattern gồm các node và edge cần khớp, sau đó áp dụng rule thay đổi graph. Cách này hữu ích khi quan hệ giữa các phần tử quan trọng hơn cấu trúc cây.

Ví dụ, một rule graph có thể tìm chuỗi node Validate -> Transform -> Persist rồi thay bằng một composite node nếu điều kiện tương đương được thỏa mãn.

## Framework và ngôn ngữ transformation

Một số framework cung cấp metamodel và ngôn ngữ chuyên dụng để mô tả phép biến đổi.

### ATL

ATL (Atlas Transformation Language) là ngôn ngữ model transformation theo hướng rule-based, thường dùng trong hệ sinh thái EMF. ATL cho phép mô tả rule ánh xạ từ metamodel nguồn sang metamodel đích, kèm helper và điều kiện.

Một rule minh họa về ý tưởng:

~~~text
rule SourceEntity2TargetEntity {
  from
    s : SOURCE!Entity
  to
    t : TARGET!Entity (
      name <- s.name
    )
}
~~~

Cú pháp trên chỉ minh họa dạng mapping. Cách tổ chức rule, resolve trace và xử lý quan hệ phụ thuộc vào ATL runtime và metamodel cụ thể.

### QVT

QVT (Query/View/Transformation) là họ chuẩn OMG cho truy vấn, view và model transformation. QVT có các hướng tiếp cận như Relations, Operational và Core, phục vụ những nhu cầu khác nhau từ mapping khai báo đến biến đổi có điều khiển.

QVT Relations có thể mô tả quan hệ giữa các model theo kiểu declarative; QVT Operational thiên về các bước biến đổi có trình tự. Khi chọn framework, cần xem khả năng hỗ trợ toolchain, trace, incremental update và debugging.

### ETL

Epsilon Transformation Language (ETL) là một ngôn ngữ trong họ Epsilon, dùng để thực hiện model-to-model transformation. Nó hỗ trợ rule chuyển đổi, truy cập model và các cơ chế liên quan trong hệ sinh thái Epsilon.

### Xtend và mã transformer

Trong hệ sinh thái Eclipse, Xtend hoặc Java có thể được dùng để viết logic transformation trực tiếp. Cách này phù hợp khi nhóm cần kiểm soát đầy đủ thuật toán hoặc tích hợp thư viện hiện có.

Không có framework nào tự động giải quyết mọi vấn đề thiết kế. Metamodel, semantics, traceability, validation và kiểm thử vẫn cần được thiết kế cho bài toán cụ thể.

## Ví dụ xuyên suốt: chuyển DSL quy tắc sang nhiều nền tảng

Giả sử một DSL mô tả rule giảm giá:

~~~text
RULE "VIP discount"
WHEN customer.segment IS "VIP"
  AND order.total >= 1000000 VND
THEN order.discountRate = 10
ELSE order.discountRate = 0
~~~

Mục tiêu là hỗ trợ hai đích: Java runtime và một rule engine lưu cấu hình JSON.

### Mô hình nguồn

Parser tạo AST gồm:

- RuleDeclaration.
- AndExpression.
- Hai ComparisonExpression.
- PropertyAccess cho customer.segment và order.total.
- Literal cho VIP và 1000000 VND.
- Hai Assignment action.

AST giữ vị trí nguồn và cấu trúc cú pháp.

### Mô hình trung gian

Transformer chuyển AST sang metamodel Rule IR:

~~~text
Rule
  id: rule-17
  name: VIP discount
  condition:
    AllOf
      - Equal
          left: Property(Customer.segment)
          right: EnumValue(CustomerSegment.VIP)
      - GreaterThanOrEqual
          left: Property(Order.total, Money<VND>)
          right: Quantity(1000000, VND)
  actions:
    - SetProperty(Order.discountRate, Percentage(10))
    - Else
      SetProperty(Order.discountRate, Percentage(0))
~~~

Mô hình trung gian chuẩn hóa tên, kiểu, đơn vị và quan hệ. Nó có thể giữ trace link đến node AST tương ứng.

### Backend Java

Backend Java có thể sinh một class hoặc biểu thức:

~~~java
boolean matches(Order order, Customer customer) {
    return customer.getSegment() == CustomerSegment.VIP
        && order.getTotal().compareTo(Money.vnd(1_000_000)) >= 0;
}

void apply(Order order, boolean matches) {
    order.setDiscountRate(matches ? 10 : 0);
}
~~~

Đây chỉ là mã minh họa. Generator thực tế cần xử lý null, kiểu Money, precision, API miền và thứ tự action đúng theo semantics DSL.

### Backend JSON rule engine

Backend khác có thể sinh:

~~~json
{
  "id": "rule-17",
  "name": "VIP discount",
  "condition": {
    "all": [
      {
        "equals": [
          { "property": "customer.segment" },
          { "enum": "CustomerSegment.VIP" }
        ]
      },
      {
        "greaterThanOrEqual": [
          { "property": "order.total", "unit": "VND" },
          { "value": 1000000, "unit": "VND" }
        ]
      }
    ]
  },
  "actions": [
    { "set": "order.discountRate", "value": 10 },
    { "elseSet": "order.discountRate", "value": 0 }
  ]
}
~~~

Cấu trúc JSON chỉ là một schema giả định. Engine thực tế có thể yêu cầu cách biểu diễn khác.

### Lợi ích của mô hình chung

Hai backend dùng cùng Rule IR. Nếu DSL nguồn thay đổi cú pháp từ AND sang ALL, source-to-intermediate transformer có thể được cập nhật trong khi backend không cần thay đổi nếu semantics vẫn giống nhau. Nếu thêm backend thứ ba, nhóm chỉ cần triển khai mapping từ Rule IR sang target mới.

Tuy nhiên, nếu một target không hỗ trợ một semantics của Rule IR, backend phải báo rõ hoặc dùng adapter được đặc tả. Mô hình chung không làm cho mọi nền tảng tự nhiên tương đương.

## Validation và invariant của mô hình trung gian

Mô hình trung gian cần được kiểm tra trước khi chuyển tiếp. Việc conform với metamodel mới chỉ bảo đảm cấu trúc; semantic invariant có thể cần kiểm tra riêng.

Ví dụ invariant:

- Mỗi Rule có đúng một condition.
- Mỗi Rule có ít nhất một action nếu semantics yêu cầu.
- Mọi PropertyReference đã resolve.
- Kiểu của giá trị gán tương thích với thuộc tính đích.
- Mọi quantity có đơn vị hoặc kiểu dimension xác định.
- Operator chỉ áp dụng cho loại operand hợp lệ.
- Reference không trỏ đến phần tử đã xóa.
- Mọi node control flow có quan hệ đầu vào/đầu ra hợp lệ.
- Không có chu trình ở nơi metamodel cấm chu trình.
- Mọi extension node được backend hỗ trợ hoặc có handler.

Có thể chia validation thành:

| Loại kiểm tra | Ví dụ |
|---|---|
| Structural | Bội số, kiểu phần tử, containment |
| Referential | Reference đã resolve, đích đúng loại |
| Type | Operand và target property tương thích |
| Domain | Rule không vượt giới hạn nghiệp vụ |
| Target capability | Backend hỗ trợ operator hoặc construct |
| Consistency | ID duy nhất, trace link hợp lệ |

Một mô hình trung gian không hợp lệ nên tạo diagnostics có thể truy về nguồn. Không nên để lỗi chỉ xuất hiện trong code generator khi có thể phát hiện ngay sau bước tạo mô hình.

## Xử lý thông tin không biểu diễn được và extension

Một mô hình trung gian dùng chung có thể không bao phủ mọi tính năng của mọi DSL. Cần có chiến lược cho phần mở rộng.

Một số cách:

- Metamodel extension cho khái niệm đặc thù.
- Annotation hoặc tagged value cho metadata phụ.
- Opaque node giữ payload của construct chưa hiểu.
- Plugin cung cấp mapping riêng.
- Capability declaration để backend thông báo hỗ trợ.
- Versioned extension namespace tránh xung đột tên.

Opaque node hữu ích khi cần bảo toàn construct chưa được xử lý, nhưng nó không thể được tối ưu hoặc chuyển sang target một cách an toàn nếu backend không hiểu semantics. Vì vậy, giữ lại payload không đồng nghĩa đã hỗ trợ chuyển đổi.

Không nên dùng một trường dữ liệu tùy ý, không có kiểu để chứa mọi thứ. Nếu extension có ảnh hưởng đến semantics, cần có schema, namespace, version và validation.

## Phiên bản và tương thích của mô hình trung gian

Metamodel có thể thay đổi khi DSL phát triển. Một thay đổi có thể thêm thuộc tính, đổi bội số, tách metaclass hoặc thay semantics của một quan hệ.

Cần xác định:

- Version của metamodel.
- Quy tắc migration từ version cũ.
- Tương thích ngược và xuôi.
- Cách xử lý field không còn hỗ trợ.
- Version của transformer và backend.
- Cách xác định artifact được tạo từ model version nào.

Ví dụ, phiên bản 1 biểu diễn action bằng một trường action; phiên bản 2 cho phép danh sách actions. Migration cần chuyển action cũ thành danh sách một phần tử hoặc có quy tắc tương thích rõ.

Một model được serialize nên ghi version schema. Không nên suy ra version chỉ từ sự hiện diện hoặc vắng mặt của một field nếu schema có thể phát triển theo nhiều hướng.

### Migration khác với transformation

Migration thay đổi model để phù hợp với phiên bản metamodel mới. Transformation chuyển model giữa các miền hoặc biểu diễn khác nhau. Hai việc có thể dùng cùng công nghệ nhưng có mục đích và hợp đồng khác nhau.

Một migration tốt nên giữ semantics và có thể kiểm tra bằng test trên các model cũ. Nếu thay đổi semantics, cần ghi nhận đó là thay đổi ngôn ngữ hoặc quy tắc miền, không chỉ là đổi cấu trúc dữ liệu.

## Incremental transformation và đồng bộ thay đổi

Trong IDE hoặc công cụ mô hình lớn, người dùng có thể sửa một phần nguồn và mong muốn mô hình trung gian được cập nhật nhanh. Incremental transformation chỉ tính lại phần bị ảnh hưởng khi có thể xác định chính xác dependency.

Một cách tiếp cận:

~~~text
Source model changed
        |
        v
Identify changed elements
        |
        v
Find dependent trace links
        |
        v
Invalidate affected intermediate elements
        |
        v
Re-transform affected region
        |
        v
Validate updated model
~~~

Cần có trace link và dependency graph đủ tin cậy để biết phần nào bị ảnh hưởng. Nếu một khai báo kiểu dùng chung thay đổi, nhiều biểu thức hoặc module có thể phải chuyển đổi lại. Nếu chỉ đổi label hiển thị của một rule, phần IR thực thi có thể không cần xây lại.

### Idempotence

Một transformation có tính idempotent nếu chạy lại với cùng input không tạo thêm thay đổi ngoài kết quả đã xác định. Tính chất này hữu ích cho build lặp lại và incremental update.

Nếu transformer luôn append node mới mà không nhận diện node cũ, chạy hai lần có thể tạo bản sao. Có thể giải quyết bằng cách tạo output mới từ đầu, dùng stable ID hoặc quản lý trace và update strategy rõ ràng.

### Đồng bộ hai chiều

Nếu người dùng có thể sửa cả source model và target model, hệ thống cần chính sách đồng bộ. Việc chuyển đổi một chiều source-to-target không đủ để xử lý xung đột khi cả hai phía cùng thay đổi.

Có thể cần bidirectional transformation hoặc synchronization engine. Những cơ chế này phải xác định nguồn sự thật, cách merge, conflict resolution và thông tin nào có thể khôi phục từ phía đích.

## Bidirectional transformation và round-trip

Transformation một chiều có dạng:

~~~text
Source Model -> Intermediate Model -> Target Model
~~~

Bidirectional transformation cho phép thay đổi ở một phía được phản ánh về phía còn lại theo các quy tắc xác định.

Ví dụ, một công cụ có thể cho phép người dùng sửa workflow graph được sinh từ DSL, sau đó đồng bộ thay đổi trở lại DSL hoặc source model.

Một số khái niệm liên quan:

- **Lens:** mô hình hóa quan hệ giữa một nguồn và một view, với các thao tác lấy view và cập nhật nguồn theo view.
- **Round-trip engineering:** chuyển đổi qua lại giữa model và code hoặc giữa các biểu diễn.
- **Synchronization:** giữ nhiều model liên quan nhất quán khi có thay đổi.
- **Consistency relation:** điều kiện mà các model ở hai phía phải cùng thỏa mãn.

Không phải mọi transformation đều đảo ngược được. Nếu bước chuyển đổi loại bỏ comment, cú pháp gốc, alias hoặc thông tin không có trong target, không thể khôi phục chính xác source ban đầu chỉ từ target.

### Quy tắc cập nhật và xung đột

Một hệ thống hai chiều cần trả lời:

- Nếu source và target cùng sửa một thuộc tính thì bên nào ưu tiên?
- Nếu target tạo một phần tử không có mapping ngược thì xử lý thế nào?
- Nếu xóa phần tử ở một bên thì bên kia có xóa theo không?
- Nếu đổi tên ở một bên, stable ID có được giữ không?
- Nếu một trường bị mất trong phép chuyển đổi, có lưu metadata phụ để khôi phục không?

Cần phân biệt round-trip theo cấu trúc, round-trip theo semantics và round-trip nguyên văn. Ba mức này có yêu cầu khác nhau.

## Kiểm thử mô hình trung gian và phép chuyển đổi

Kiểm thử cần bao phủ cả metamodel, transformer và quan hệ giữa các biểu diễn.

### Kiểm thử metamodel

Xác nhận model instance conform với metamodel:

- Đúng loại phần tử.
- Bội số hợp lệ.
- Thuộc tính bắt buộc có giá trị.
- Quan hệ containment hợp lệ.
- Reference có đích đúng kiểu.
- Invariant không bị vi phạm.

### Kiểm thử source-to-intermediate

Với mỗi construct nguồn được hỗ trợ, cần có fixture và mô hình trung gian mong đợi. Test nên kiểm tra mapping field, kiểu, đơn vị, quan hệ và trace.

### Kiểm thử intermediate-to-target

Cần kiểm tra:

- Target model conform với metamodel đích.
- Mọi construct được hỗ trợ đều được ánh xạ.
- Construct không hỗ trợ tạo diagnostics.
- Thứ tự và semantics được bảo toàn.
- Artifact hoặc model đích ổn định theo hợp đồng.

### Kiểm thử traceability

Xác nhận mỗi phần tử được sinh có trace link phù hợp và có thể truy ngược đến nguồn. Với mapping nhiều-nhiều, kiểm tra đầy đủ vai trò và quan hệ.

### Kiểm thử end-to-end

Chạy source qua toàn bộ chuỗi transformation và xác nhận target hoặc kết quả thực thi. Với nhiều backend, chạy cùng mô hình trung gian qua các target để so sánh hành vi theo semantics chung.

### Kiểm thử property và differential

Một số thuộc tính có thể kiểm tra tự động:

- Transformation không tạo model vi phạm metamodel.
- Chạy lại với cùng input tạo kết quả tương đương.
- Thứ tự collection được bảo toàn nếu có ý nghĩa.
- Mọi target element bắt buộc có origin hoặc trace.
- Interpreter trên intermediate model và backend sinh mã cho kết quả tương đương.
- Migration giữ invariant và semantics đã công bố.

Nếu có hai implementation transformer, differential testing có thể so sánh kết quả trên cùng tập model được sinh hoặc fixture.

## Hiệu năng và quản lý bộ nhớ

Một mô hình trung gian có thể lớn hơn AST nguồn vì chứa kiểu, reference, metadata và trace. Thiết kế cần cân bằng khả năng truy vết với chi phí bộ nhớ.

Các vấn đề thường gặp:

- Tạo nhiều bản sao của phần tử dùng chung.
- Lưu trace link trùng lặp.
- Giữ cả AST, HIR, IR và target model dù không còn cần.
- Duyệt graph nhiều lần không có index.
- Resolve reference lặp lại.
- Cache model không được invalidation.
- Giữ source text lớn chỉ để phục vụ diagnostics.

Có thể dùng stable ID, object interning, index ngược, lazy loading hoặc giải phóng các representation cũ sau khi hoàn thành bước cần thiết. Nếu cần giữ mô hình cho debug hoặc IDE, có thể lưu metadata ở dạng nhẹ hơn.

Không nên tối ưu bộ nhớ bằng cách loại bỏ source mapping hoặc traceability nếu chúng là yêu cầu cốt lõi của sản phẩm. Hãy đo chi phí và xác định metadata nào cần tồn tại ở từng giai đoạn.

## Những lỗi thiết kế thường gặp

### Mô hình trung gian chỉ sao chép AST

Nếu intermediate model giữ nguyên mọi chi tiết cú pháp và phụ thuộc vào tên production, backend vẫn bị gắn chặt với parser. Cần xác định rõ phần ngữ nghĩa chung mà mô hình trung gian phải biểu diễn.

### Mô hình quá tổng quát

Một metamodel cố biểu diễn mọi ngôn ngữ và mọi target có thể chứa nhiều field tùy chọn, extension không kiểu và quy tắc mơ hồ. Nên xác định phạm vi hỗ trợ và chia mô hình theo miền hoặc capability khi cần.

### Mất thông tin khi chuẩn hóa

Loại bỏ đơn vị, kiểu, thứ tự hoặc nullability có thể làm thay đổi hành vi. Cần xác định thông tin nào được giữ, suy ra hoặc cố ý loại bỏ.

### Để backend tự diễn giải cú pháp nguồn

Nếu backend phải biết keyword, token hoặc node đặc thù của từng DSL, ranh giới intermediate model chưa đủ tốt. Backend nên làm việc trên semantics đã chuẩn hóa.

### Không có traceability

Khi output sai, người dùng không biết nó đến từ node nguồn nào. Trace link cần được tạo và giữ qua các phép biến đổi quan trọng.

### Không validate trước khi sinh đích

Model trung gian có thể đúng metamodel nhưng sai kiểu hoặc thiếu reference. Cần validation cấu trúc, tham chiếu, kiểu, miền và capability của target.

### Coi transformation là phép gán field đơn giản

Nhiều mapping cần resolve tên, gộp hoặc tách node, chuẩn hóa kiểu, xử lý collection và tạo trace. Cần mô tả rule mapping thay vì chỉ copy field.

### Giả định mọi phép chuyển đổi đều đảo ngược được

Khi target không giữ thông tin nguồn, round-trip chính xác là không thể. Cần xác định mức round-trip và metadata cần giữ.

### Không quản lý version metamodel

Model được lưu có thể không còn conform với schema mới. Cần versioning và migration có kiểm soát.

### Không kiểm tra semantics

Hai model có cấu trúc khác nhau có thể tương đương, và hai model có cấu trúc giống nhau có thể khác hành vi. Cần test ngữ nghĩa, không chỉ so sánh số lượng node.

## Quy trình thiết kế mô hình trung gian cho chuyển đổi

Một quy trình thực tế có thể đi theo các bước:

1. **Xác định mục tiêu chuyển đổi:** xác định nguồn, đích, use case và kết quả cần tạo.
2. **Liệt kê semantics cần bảo toàn:** kiểu, quan hệ, thứ tự, side effect, lỗi, đơn vị và metadata.
3. **Xác định phạm vi mô hình chung:** chọn các khái niệm có ý nghĩa giữa các nguồn và đích được hỗ trợ.
4. **Thiết kế metamodel:** định nghĩa metaclass, attribute, containment, reference, multiplicity và constraint.
5. **Chọn mức trừu tượng:** quyết định mô hình cấp nghiệp vụ, platform-independent hay gần runtime.
6. **Xây source mapping:** quy định cách chuyển từng construct nguồn, bao gồm trường hợp không hỗ trợ.
7. **Xây target mapping:** xác định capability và cách hạ từng construct sang mô hình hoặc artifact đích.
8. **Thiết kế traceability:** xác định stable ID, source origin và quan hệ một-nhiều/nhiều-một.
9. **Định nghĩa validation:** kiểm tra structural, reference, type, domain và target capability.
10. **Định nghĩa versioning:** quản lý thay đổi metamodel và migration.
11. **Xem xét incremental và bidirectional:** chỉ bổ sung khi use case cần đồng bộ hoặc cập nhật từng phần.
12. **Kiểm thử:** dùng fixture, invariant, differential test, round-trip và end-to-end test.
13. **Đo hiệu năng:** đánh giá kích thước model, trace, thời gian transform và bộ nhớ trên dữ liệu thực tế.

Bảng mapping nên ghi rõ source metaclass, source feature, target metaclass, target feature, điều kiện áp dụng, phép chuẩn hóa, trace behavior và diagnostics khi không thể chuyển đổi. Tài liệu này giúp nhóm phát triển và người bảo trì hiểu được hợp đồng mà không phải suy luận từ code.

## Kết luận

Mô hình trung gian cung cấp một biểu diễn chung để chuyển đổi giữa các DSL, mô hình miền và nền tảng đích. Nó giảm phụ thuộc giữa nguồn và đích, chuẩn hóa khác biệt cú pháp, cho phép chia phép biến đổi thành nhiều bước và tạo nền tảng cho validation, tối ưu hóa, traceability và tái sử dụng backend.

Một mô hình trung gian tốt cần có metamodel rõ ràng, mức trừu tượng phù hợp và giữ đủ semantics cần thiết: kiểu, đơn vị, quan hệ, thứ tự, nullability, side effect và nguồn gốc. Các transformer cần xác định mapping, xử lý construct không hỗ trợ, kiểm tra capability và duy trì trace link. Nếu cần cập nhật gia tăng hoặc đồng bộ hai chiều, hệ thống phải định nghĩa dependency, conflict resolution và giới hạn round-trip.

Không phải mọi DSL đều cần một IR lớn hoặc nhiều tầng model. Hãy bắt đầu từ các nguồn và đích thực tế, xác định thông tin cần bảo toàn rồi thiết kế mô hình vừa đủ. Khi hợp đồng của mô hình trung gian được xác định rõ, các phép chuyển đổi trở nên dễ kiểm thử, dễ mở rộng và ít phụ thuộc vào chi tiết triển khai của từng ngôn ngữ.
