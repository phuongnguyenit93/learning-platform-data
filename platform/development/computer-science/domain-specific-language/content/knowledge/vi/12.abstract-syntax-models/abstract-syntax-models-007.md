# Ràng buộc mô hình

## 1. Khái niệm và vai trò trong mô hình trừu tượng DSL

Trong thiết kế một ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*), **mô hình trừu tượng (*abstract model*)** mô tả những khái niệm mà ngôn ngữ biểu đạt và quan hệ giữa chúng. Mô hình có thể gồm các loại phần tử, thuộc tính, quan hệ, kiểu dữ liệu, cấu trúc lồng nhau và những quy tắc nghiệp vụ.

**Ràng buộc mô hình (*model constraint*)** là điều kiện quy định một mô hình hoặc một phần của mô hình phải thỏa mãn để được xem là hợp lệ. Ràng buộc bổ sung những yêu cầu mà cấu trúc đơn thuần chưa thể diễn đạt đầy đủ.

Ví dụ, mô hình đơn hàng có thể quy định:

- Mỗi đơn hàng phải có một mã định danh.
- Một đơn hàng phải có ít nhất một dòng hàng trước khi được xác nhận.
- Số lượng trong mỗi dòng hàng phải lớn hơn 0.
- Tổng tiền phải bằng tổng thành tiền của các dòng hàng.
- Một sản phẩm không được xuất hiện hai lần trong cùng một đơn hàng nếu miền yêu cầu gộp các dòng cùng sản phẩm.

Một meta-model có thể khai báo rằng Order chứa một tập OrderLine. Tuy nhiên, quan hệ chứa đó chưa tự nói lên rằng đơn hàng đã xác nhận phải có ít nhất một dòng hàng hoặc số lượng của mỗi dòng phải dương. Các điều kiện này cần được biểu diễn bằng ràng buộc.

Ràng buộc mô hình có ba vai trò chính:

1. **Bảo vệ tính đúng đắn:** ngăn các mô hình vi phạm quy tắc cấu trúc hoặc nghiệp vụ.
2. **Làm rõ ngữ nghĩa:** ghi lại những điều kiện mà người thiết kế ngôn ngữ mong đợi, thay vì để chúng ẩn trong mã xử lý.
3. **Hỗ trợ công cụ:** cho phép editor, validator, compiler hoặc runtime phát hiện và giải thích lỗi một cách nhất quán.

Một DSL có thể có cú pháp hợp lệ nhưng mô hình vẫn không hợp lệ. Ví dụ, parser có thể chấp nhận một quy tắc tham chiếu đến trường không tồn tại; việc kiểm tra mô hình và ngữ nghĩa phải phát hiện lỗi đó ở giai đoạn tiếp theo.

## 2. Phân biệt cú pháp, meta-model và ràng buộc

Khi xây dựng DSL, cần phân biệt ba lớp thường phối hợp với nhau.

### 2.1. Cú pháp cụ thể

Cú pháp cụ thể (*concrete syntax*) quy định cách người dùng viết chương trình hoặc tài liệu DSL. Ví dụ:

~~~text
order "ORD-100" {
    line product = "P-01" quantity = 2
    line product = "P-02" quantity = 1
}
~~~

Grammar xác định các từ khóa, dấu ngoặc, thuộc tính và thứ tự thành phần được phép xuất hiện. Parser kiểm tra chuỗi nguồn có khớp grammar hay không.

### 2.2. Mô hình trừu tượng và meta-model

Mô hình trừu tượng biểu diễn cấu trúc có ý nghĩa của tài liệu sau khi phân tích. Meta-model mô tả những loại phần tử có thể tồn tại trong mô hình và cách chúng liên kết.

Ví dụ một meta-model đơn giản:

~~~text
Order
- id: String
- status: OrderStatus
- total: Money
- lines: OrderLine [0..*]

OrderLine
- product: Product
- quantity: Integer
- unitPrice: Money
~~~

Trong đó:

- Order và OrderLine là các loại phần tử.
- id, status, total, quantity và unitPrice là thuộc tính.
- lines là quan hệ từ một đơn hàng đến các dòng hàng.
- [0..*] biểu thị một đơn hàng có thể chứa từ 0 đến nhiều dòng hàng theo cấu trúc hiện tại.

Meta-model mô tả hình dạng của mô hình. Nó chưa nhất thiết thể hiện tất cả điều kiện về trạng thái hoặc giá trị.

### 2.3. Ràng buộc mô hình

Ràng buộc bổ sung điều kiện trên phần tử và quan hệ. Ví dụ:

- Order.id không được rỗng.
- Order.lines phải không rỗng khi status = CONFIRMED.
- Mọi OrderLine.quantity phải lớn hơn 0.
- Order.total phải bằng tổng các dòng hàng.
- Các dòng hàng trong cùng đơn phải có sản phẩm khác nhau.

Có thể hình dung quan hệ giữa các lớp như sau:

~~~text
Nguồn DSL
    |
    v
Cú pháp cụ thể / Grammar
    |
    v
Parser
    |
    v
Mô hình trừu tượng (instance của meta-model)
    |
    v
Kiểm tra ràng buộc
    |
    +----> Hợp lệ
    |
    +----> Diagnostics / lỗi mô hình
~~~

Parser trả lời câu hỏi "văn bản có đúng cú pháp không?". Model validator trả lời câu hỏi "cấu trúc và dữ liệu được biểu diễn có thỏa các quy tắc của mô hình không?". Semantic analyzer có thể thực hiện thêm các kiểm tra về kiểu, tham chiếu, phạm vi và ý nghĩa miền.

## 3. Các loại ràng buộc mô hình

Ràng buộc có thể được phân loại theo mục đích. Trong thực tế, một quy tắc có thể thuộc nhiều nhóm.

### 3.1. Ràng buộc cấu trúc

Ràng buộc cấu trúc quy định phần tử nào được phép tồn tại và cách chúng liên kết với nhau.

Ví dụ:

- Một Workflow phải có ít nhất một Step.
- Một StateMachine phải có một trạng thái bắt đầu.
- Một Class không được chứa hai thuộc tính cùng tên trong cùng phạm vi.
- Một Rule phải có một điều kiện và một hành động.

Một phần ràng buộc cấu trúc có thể được biểu diễn trực tiếp trong meta-model bằng kiểu, quan hệ và bội số. Các quy tắc phức tạp hơn cần biểu thức constraint riêng.

### 3.2. Ràng buộc bội số và số lượng

Bội số (*multiplicity/cardinality*) quy định số lượng phần tử được phép liên kết.

| Quan hệ | Bội số | Ý nghĩa |
|---|---:|---|
| Project → Module | 1..* | Một project có ít nhất một module |
| Module → Rule | 0..* | Một module có thể không có rule hoặc có nhiều rule |
| Order → Customer | 1 | Mỗi đơn hàng gắn với đúng một khách hàng |
| Order → OrderLine | 1..* | Một đơn hàng hợp lệ phải có ít nhất một dòng hàng |
| User → EmailAddress | 0..2 | Một người dùng có thể có tối đa hai địa chỉ email |

Cần phân biệt bội số của cấu trúc với điều kiện phụ thuộc trạng thái. Nếu Order.lines có bội số 0..* vì đơn hàng nháp được phép chưa có dòng hàng, ta có thể thêm constraint yêu cầu danh sách không rỗng khi đơn được xác nhận.

### 3.3. Ràng buộc kiểu dữ liệu

Ràng buộc kiểu bảo đảm giá trị hoặc biểu thức phù hợp với kiểu đã khai báo.

Ví dụ:

- quantity phải là số nguyên.
- createdAt phải là ngày giờ.
- status chỉ nhận một giá trị thuộc enum OrderStatus.
- Không được cộng trực tiếp một chuỗi với một số.
- Điều kiện của when phải trả về kiểu Boolean.

Một số kiểm tra kiểu có thể thực hiện tĩnh trước khi chạy. Một số DSL động chỉ xác định được kiểu ở runtime.

### 3.4. Ràng buộc giá trị

Ràng buộc giá trị quy định miền giá trị được phép:

- Số lượng phải lớn hơn 0.
- Phần trăm giảm giá nằm trong khoảng 0 đến 100.
- Tên không được rỗng.
- Ngày kết thúc không được trước ngày bắt đầu.
- Timeout phải là số dương.
- Mã tiền tệ phải thuộc tập mã được hỗ trợ.

Các điều kiện này thường được gọi là *value constraints* hoặc *range constraints*.

### 3.5. Ràng buộc duy nhất

Ràng buộc duy nhất (*uniqueness constraint*) yêu cầu một giá trị hoặc tổ hợp giá trị không được lặp trong phạm vi xác định.

Ví dụ:

- Mã đơn hàng phải duy nhất trong hệ thống.
- Tên biến không được trùng trong cùng scope.
- Một workflow không được có hai bước cùng ID.
- Một đơn hàng không có hai dòng hàng riêng cho cùng một sản phẩm nếu miền yêu cầu gộp.

Phạm vi duy nhất phải được xác định rõ: toàn cục, trong module, trong một container, hay trong một aggregate.

### 3.6. Ràng buộc tham chiếu và toàn vẹn liên kết

Ràng buộc tham chiếu (*reference/integrity constraint*) bảo đảm các liên kết trỏ đến phần tử hợp lệ.

Ví dụ:

- Một rule chỉ được tham chiếu đến biến đã khai báo.
- Một transition phải trỏ đến trạng thái tồn tại trong state machine.
- Một workflow task phải tham chiếu đến một service đã đăng ký.
- Một dòng hàng phải trỏ đến sản phẩm có thể bán.

Các kiểm tra này thường cần symbol table, registry hoặc mô hình đã được nạp đầy đủ.

### 3.7. Ràng buộc bất biến nghiệp vụ

Bất biến (*invariant*) là điều kiện phải luôn đúng tại những thời điểm được quy định trong vòng đời mô hình.

Ví dụ:

- Đơn đã xác nhận không được rỗng.
- Tổng tiền không được âm.
- Trạng thái đã giao không thể quay về trạng thái nháp.
- Một tài khoản không được vượt giới hạn số dư âm.
- Một node trong cây cú pháp chỉ được có những loại con được meta-model cho phép.

Invariant có thể liên quan đến nhiều thuộc tính hoặc nhiều phần tử. Vì vậy, chúng thường cần ngôn ngữ biểu thức hoặc mã validator thay vì chỉ dùng kiểu và bội số.

### 3.8. Ràng buộc phụ thuộc trạng thái hoặc ngữ cảnh

Một số điều kiện chỉ có ý nghĩa trong một trạng thái hoặc ngữ cảnh cụ thể.

Ví dụ:

- Khi đơn hàng là DRAFT, có thể thay đổi dòng hàng.
- Khi đơn hàng là CONFIRMED, phải có khách hàng và ít nhất một dòng hàng.
- Khi workflow ở trạng thái RUNNING, mọi task bắt buộc phải có cấu hình thực thi.
- Khi một rule có hành động gửi email, phải khai báo người nhận.

Những điều kiện này không thể diễn đạt đầy đủ bằng một kiểm tra thuộc tính đơn lẻ; validator cần xem xét trạng thái và quan hệ liên quan.

## 4. Ràng buộc trong meta-model và ràng buộc trên model instance

Hai loại đối tượng cần được phân biệt:

- **Meta-model:** mô tả các lớp phần tử, thuộc tính, quan hệ và quy tắc mà mọi mô hình của DSL phải tuân theo.
- **Model instance:** một tài liệu hoặc mô hình cụ thể do người dùng tạo theo meta-model.

Ràng buộc có thể áp dụng ở một trong hai cấp.

### 4.1. Ràng buộc meta-model

Ràng buộc meta-model quy định bản thân định nghĩa ngôn ngữ phải nhất quán.

Ví dụ:

- Mỗi class trong meta-model phải có tên duy nhất.
- Một reference phải có kiểu đích tồn tại.
- Không được có vòng lặp kế thừa bị cấm.
- Thuộc tính bắt buộc phải có kiểu dữ liệu.
- Quan hệ containment phải tuân theo quy tắc sở hữu đã định nghĩa.

Nếu meta-model sai, mọi tài liệu được tạo theo nó có thể gặp vấn đề.

### 4.2. Ràng buộc trên model instance

Ràng buộc instance áp dụng lên một mô hình cụ thể.

Ví dụ meta-model cho phép một workflow có nhiều step. Một instance cụ thể phải bảo đảm:

- ID của từng step là duy nhất.
- Có đúng một step bắt đầu.
- Mọi cạnh chuyển tiếp trỏ đến step tồn tại.
- Không có step bắt buộc nào thiếu cấu hình.

### 4.3. Ví dụ phân biệt

| Cấp | Câu hỏi | Ví dụ ràng buộc |
|---|---|---|
| Meta-model | Định nghĩa DSL có hợp lệ không? | Mọi reference đều có kiểu đích hợp lệ |
| Model instance | Tài liệu DSL cụ thể có hợp lệ không? | Mọi reference trong workflow đều trỏ đến step tồn tại |
| Runtime state | Trạng thái hiện tại có được phép không? | Workflow đã chạy không được thiếu execution context |
| Cross-model | Các mô hình liên quan có nhất quán không? | Một rule import module đã được khai báo trong project |

Ràng buộc ở các cấp khác nhau có thể dùng chung ngôn ngữ biểu thức, nhưng thường có context và thời điểm đánh giá khác nhau.

## 5. Ràng buộc hình thức và ngôn ngữ biểu đạt constraint

### 5.1. Constraint khai báo

Ràng buộc khai báo mô tả điều kiện phải đúng, không chỉ cách kiểm tra điều kiện đó bằng các bước lệnh. Ví dụ:

~~~text
Order.total >= 0
Order.lines->notEmpty()
OrderLine.quantity > 0
~~~

Một engine có thể đánh giá các biểu thức này trên model instance. Cách khai báo giúp quy tắc độc lập hơn với ngôn ngữ triển khai.

### 5.2. Constraint mệnh lệnh

Ràng buộc cũng có thể được viết dưới dạng mã kiểm tra:

~~~java
if (order.getTotal().isNegative()) {
    errors.add("Order total must not be negative");
}
~~~

Cách mệnh lệnh dễ tích hợp với mã ứng dụng, nhưng quy tắc có thể bị phân tán trong nhiều validator. Nếu DSL cần công cụ kiểm tra, tài liệu hóa hoặc sinh code, một biểu diễn khai báo có thể thuận tiện hơn.

### 5.3. Object Constraint Language (OCL)

**Object Constraint Language (OCL)** là ngôn ngữ biểu thức khai báo được dùng cùng các mô hình hướng đối tượng, đặc biệt trong hệ sinh thái UML và mô hình hóa. OCL cho phép diễn đạt invariant, precondition, postcondition và các biểu thức truy vấn trên đối tượng.

Ví dụ OCL minh họa:

~~~ocl
context Order
inv NonNegativeTotal:
    self.total >= 0
~~~

Ràng buộc này yêu cầu tổng tiền của một Order không âm.

Một ví dụ khác:

~~~ocl
context OrderLine
inv PositiveQuantity:
    self.quantity > 0
~~~

Một invariant trên tập dòng hàng:

~~~ocl
context Order
inv HasLinesWhenConfirmed:
    self.status = OrderStatus::CONFIRMED
    implies self.lines->notEmpty()
~~~

Một ràng buộc duy nhất:

~~~ocl
context Order
inv NoDuplicateProducts:
    self.lines->isUnique(line | line.product)
~~~

Cú pháp enum, tên thuộc tính và kiểu dữ liệu phải khớp meta-model cụ thể. Các biểu thức trên minh họa phong cách OCL; khi triển khai cần dùng đúng phiên bản OCL và công cụ tương ứng.

### 5.4. Invariant, precondition và postcondition

Trong mô hình hóa, có thể phân biệt ba loại điều kiện:

- **Invariant:** phải đúng đối với đối tượng ở trạng thái hợp lệ.
- **Precondition:** điều kiện phải đúng trước khi thực hiện một operation.
- **Postcondition:** điều kiện phải đúng sau khi operation hoàn tất.

Ví dụ operation xác nhận đơn hàng:

~~~ocl
context Order::confirm()
pre DraftOnly:
    self.status = OrderStatus::DRAFT
pre MustHaveLines:
    self.lines->notEmpty()
post IsConfirmed:
    self.status = OrderStatus::CONFIRMED
~~~

Precondition giới hạn trạng thái được phép gọi thao tác. Postcondition mô tả kết quả mong đợi sau khi gọi. Invariant có thể tiếp tục áp dụng trước và sau operation.

Không nên dùng invariant thay cho mọi điều kiện thao tác. Một điều kiện chỉ cần đúng trước một hành động có thể phù hợp hơn với precondition.

## 6. Thiết kế ràng buộc cho mô hình đơn hàng

Xét meta-model đơn giản:

~~~text
Customer
- id: String
- email: String

Product
- id: String
- currentPrice: Money

Order
- id: String
- status: OrderStatus
- total: Money
- customer: Customer [1]
- lines: OrderLine [0..*]

OrderLine
- product: Product [1]
- quantity: Integer
- unitPrice: Money
~~~

Ta có thể mô tả một số quy tắc:

| Tên constraint | Context | Điều kiện |
|---|---|---|
| OrderIdRequired | Order | ID không rỗng |
| CustomerRequired | Order | Có đúng một khách hàng |
| ConfirmedOrderHasLines | Order | Đã xác nhận thì có ít nhất một dòng |
| PositiveQuantity | OrderLine | Số lượng lớn hơn 0 |
| NonNegativePrice | OrderLine | Đơn giá không âm |
| UniqueProductPerOrder | Order | Mỗi sản phẩm chỉ có một dòng |
| TotalMatchesLines | Order | Tổng bằng tổng thành tiền các dòng |

### 6.1. Diễn đạt bằng OCL

~~~ocl
context Order
inv OrderIdRequired:
    not self.id.oclIsUndefined() and self.id <> ''
~~~

~~~ocl
context Order
inv ConfirmedOrderHasLines:
    self.status = OrderStatus::CONFIRMED
    implies self.lines->notEmpty()
~~~

~~~ocl
context OrderLine
inv PositiveQuantity:
    self.quantity > 0
~~~

~~~ocl
context OrderLine
inv NonNegativeUnitPrice:
    self.unitPrice.amount >= 0
~~~

~~~ocl
context Order
inv UniqueProductPerOrder:
    self.lines->isUnique(line | line.product)
~~~

~~~ocl
context Order
inv TotalMatchesLines:
    self.total = self.lines->collect(line |
        line.quantity * line.unitPrice.amount
    )->sum()
~~~

Ví dụ tính tổng giản lược giả định mọi dòng dùng cùng đơn vị tiền tệ và quy tắc làm tròn. Một mô hình thực tế cần xét tiền tệ, thuế, chiết khấu, phí vận chuyển, độ chính xác thập phân và cách làm tròn. Không nên tính toán tiền bằng số thực nhị phân nếu yêu cầu nghiệp vụ cần độ chính xác tiền tệ; dùng kiểu decimal hoặc Money phù hợp.

### 6.2. Điều kiện theo trạng thái

Đơn nháp có thể chưa có dòng hàng, nhưng đơn đã xác nhận phải có ít nhất một dòng. Đây là lý do không nhất thiết đặt bội số của lines thành 1..* ngay trong meta-model nếu điều đó cấm cả trạng thái nháp hợp lệ.

Có thể biểu diễn:

~~~ocl
context Order
inv LinesRequiredForConfirmed:
    self.status = OrderStatus::CONFIRMED
    implies self.lines->notEmpty()
~~~

Cách này giữ được hai trạng thái:

- DRAFT: có thể chưa có dòng hàng.
- CONFIRMED: bắt buộc có ít nhất một dòng hàng.

Mô hình biểu đạt được vòng đời nghiệp vụ thay vì chỉ giới hạn cấu trúc tĩnh.

## 7. Ràng buộc liên quan đến nhiều phần tử

Một số constraint không chỉ kiểm tra một thuộc tính mà phải duyệt tập phần tử hoặc so sánh nhiều đối tượng.

### 7.1. Quan hệ tồn tại

Ví dụ, mọi transition trong state machine phải trỏ đến một trạng thái được khai báo:

~~~ocl
context StateMachine
inv TransitionTargetsExist:
    self.transitions->forAll(t |
        self.states->includes(t.target)
    )
~~~

Nếu reference được mô hình hóa bằng liên kết đối tượng thực sự, parser hoặc loader có thể đã kiểm tra được một phần. Nếu DSL dùng tên văn bản để tham chiếu, semantic resolution cần tìm đối tượng đích và báo lỗi khi không tồn tại.

### 7.2. Tính duy nhất trong một phạm vi

Ví dụ, tên biến phải duy nhất trong cùng block:

~~~ocl
context Block
inv UniqueVariableNames:
    self.variables->isUnique(v | v.name)
~~~

Điều kiện này không cấm hai block khác nhau có biến cùng tên. Phạm vi kiểm tra là tập variables của từng block.

### 7.3. Ràng buộc giữa hai thuộc tính

Ví dụ ngày bắt đầu phải không sau ngày kết thúc:

~~~ocl
context Schedule
inv ValidDateRange:
    self.startDate <= self.endDate
~~~

Hoặc một workflow phải có ít nhất một bước kết thúc:

~~~ocl
context Workflow
inv HasFinalStep:
    self.steps->exists(step | step.kind = StepKind::FINAL)
~~~

### 7.4. Ràng buộc toàn cục

Một số điều kiện liên quan toàn bộ model instance, ví dụ tất cả ID phải duy nhất trong project hoặc một project chỉ có một module chính. Những quy tắc này có thể đặt ở context gốc như Project hoặc dùng validator cấp model.

Cần tránh viết một invariant toàn cục quá rộng trong từng đối tượng nếu việc đánh giá lặp lại gây tốn kém. Có thể xây một bước kiểm tra model-level chuyên biệt.

## 8. Ràng buộc và ngữ nghĩa kiểu

Một mô hình có thể có cấu trúc đúng nhưng biểu thức trong đó sai kiểu. Vì vậy, model validation thường phối hợp với type checking.

Ví dụ:

~~~text
rule "age-check" {
    when customer.age > "eighteen"
    then allow()
}
~~~

Nếu customer.age là số nguyên còn literal "eighteen" là chuỗi, biểu thức so sánh có thể không hợp lệ theo hệ kiểu của DSL.

Một số loại kiểm tra:

- Thuộc tính được truy cập phải tồn tại trên kiểu đối tượng.
- Toán tử chỉ áp dụng cho những kiểu được hỗ trợ.
- Điều kiện của when phải trả về Boolean.
- Biểu thức gán phải có kiểu tương thích với thuộc tính đích.
- Tham số hàm phải khớp kiểu và số lượng.
- Giá trị literal phải nằm trong miền kiểu hoặc miền nghiệp vụ.

Type constraint và business constraint có liên hệ nhưng không giống nhau. Ví dụ quantity là Integer là ràng buộc kiểu; quantity > 0 là ràng buộc giá trị/nghiệp vụ.

## 9. Thời điểm và chiến lược đánh giá ràng buộc

Không phải constraint nào cũng có thể kiểm tra ở cùng một thời điểm. Một hệ thống DSL thường có nhiều giai đoạn validation.

### 9.1. Validation lúc phân tích cú pháp

Ở giai đoạn parser, hệ thống kiểm tra cấu trúc theo grammar:

- Thiếu dấu ngoặc hoặc từ khóa.
- Sai thứ tự thành phần.
- Biểu thức không hoàn chỉnh.
- Token không hợp lệ.

Đây là syntax validation, chưa phải toàn bộ model validation.

### 9.2. Validation ngay sau khi tạo mô hình

Khi đã có model instance, validator có thể kiểm tra:

- Thuộc tính bắt buộc.
- Bội số.
- Kiểu dữ liệu.
- Giá trị nằm trong giới hạn.
- Quan hệ containment.
- Tên duy nhất trong phạm vi.

Các điều kiện này thường có thể đánh giá trước khi thực thi.

### 9.3. Semantic validation

Semantic analyzer kiểm tra những điều cần hiểu ngữ cảnh:

- Identifier có được khai báo không.
- Reference có trỏ đến phần tử tồn tại không.
- Kiểu của biểu thức có tương thích không.
- Operation có được phép trong context không.
- Các quy tắc có mâu thuẫn hoặc không thể thực hiện không.

### 9.4. Validation lúc chạy

Một số điều kiện phụ thuộc dữ liệu hoặc trạng thái chỉ có khi chạy:

- Tồn kho hiện tại có đủ không.
- Người dùng hiện tại có quyền thực hiện không.
- Một dịch vụ bên ngoài có sẵn không.
- Hạn mức còn lại có đáp ứng yêu cầu không.
- Dữ liệu thực tế có thỏa điều kiện của quy trình không.

Những điều kiện này thường thuộc runtime validation hoặc business rule execution. Không nên giả định một model đã hợp lệ tĩnh thì mọi lần thực thi đều chắc chắn thành công.

### 9.5. Bảng phân chia giai đoạn

| Giai đoạn | Ví dụ kiểm tra | Kết quả |
|---|---|---|
| Lexing/parsing | Token, grammar, dấu ngoặc | Syntax diagnostics |
| Model validation | Bội số, thuộc tính bắt buộc, cấu trúc | Model diagnostics |
| Semantic analysis | Tên, reference, kiểu, phạm vi | Semantic diagnostics |
| Pre-execution validation | Quyền, cấu hình runtime, dependency | Validation result |
| Runtime | Tồn kho, trạng thái bên ngoài, giới hạn động | Kết quả hoặc lỗi thực thi |

Một constraint có thể được kiểm tra ở nhiều thời điểm nếu cần. Ví dụ, quyền có thể được kiểm tra khi validate để cảnh báo sớm và kiểm tra lại khi thực thi để tránh dùng quyền đã thay đổi.

## 10. Tổ chức bộ kiểm tra ràng buộc

### 10.1. Constraint registry

Với DSL có nhiều loại model element, có thể đăng ký các constraint theo context:

~~~java
interface ModelConstraint<T> {
    String id();
    String description();
    List<Diagnostic> validate(T element, ValidationContext context);
}
~~~

Một registry có thể ánh xạ kiểu phần tử sang danh sách validator tương ứng. Khi model được tạo, engine duyệt các phần tử và chạy các constraint phù hợp.

Ví dụ khung:

~~~java
final class OrderConstraints implements ModelConstraint<Order> {
    @Override
    public String id() {
        return "order.confirmed-has-lines";
    }

    @Override
    public String description() {
        return "Confirmed orders must contain at least one line";
    }

    @Override
    public List<Diagnostic> validate(
        Order order,
        ValidationContext context
    ) {
        if (order.status() == OrderStatus.CONFIRMED
                && order.lines().isEmpty()) {
            return List.of(Diagnostic.error(
                id(),
                "A confirmed order must have at least one line",
                order.sourceLocation()
            ));
        }

        return List.of();
    }
}
~~~

Đây là ví dụ kiến trúc bằng Java, không phải API của framework cụ thể. ValidationContext có thể cung cấp symbol table, registry, model root và chính sách kiểm tra. Diagnostic nên có mã lỗi ổn định, thông điệp, mức độ và vị trí nguồn.

### 10.2. Tách constraint khỏi phần thực thi

Không nên để logic validation chỉ nằm trong parser hoặc rải rác trong UI. Khi có một lớp constraint dùng chung, CLI, editor, CI và runtime có thể áp dụng cùng quy tắc.

Một cấu trúc dự án minh họa:

~~~text
dsl/
├── grammar/
├── metamodel/
├── constraints/
│   ├── structural/
│   ├── semantic/
│   └── business/
├── validation/
│   ├── engine/
│   └── diagnostics/
├── runtime/
└── editor/
~~~

Dự án nhỏ có thể gộp module, nhưng nên giữ ranh giới trách nhiệm rõ ràng.

### 10.3. Diagnostic có cấu trúc

Một diagnostic hữu ích nên chứa:

- Mã lỗi ổn định, ví dụ MODEL-ORDER-001.
- Severity: error, warning hoặc info.
- Thông điệp giải thích điều kiện bị vi phạm.
- Vị trí nguồn hoặc phần tử liên quan.
- Constraint ID đã phát hiện lỗi.
- Gợi ý sửa nếu có thể xác định chắc chắn.

Ví dụ:

~~~text
orders.dsl:18:5: error MODEL-ORDER-001
A confirmed order must contain at least one line.
Add a line item or keep the order in DRAFT state.
~~~

Thông điệp nên dùng thuật ngữ của miền. Người viết DSL cần hiểu phải sửa mô hình ở đâu và vì sao.

## 11. Ràng buộc, sửa mô hình và tính nhất quán

### 11.1. Validation không tự sửa mô hình

Validator thường có nhiệm vụ phát hiện và báo lỗi. Việc tự động sửa (*auto-fix*) là một hành động riêng, chỉ nên thực hiện khi cách sửa có ý nghĩa rõ ràng và không làm thay đổi nghiệp vụ ngoài ý muốn.

Ví dụ, formatter có thể tự sửa khoảng trắng; nhưng nếu đơn đã xác nhận mà thiếu dòng hàng, hệ thống không thể tự đoán sản phẩm và số lượng cần thêm.

### 11.2. Precondition trước khi thay đổi

Một thao tác trên mô hình có thể yêu cầu precondition:

~~~text
operation confirmOrder(order):
    require order.status == DRAFT
    require order.lines is not empty
    set order.status = CONFIRMED
~~~

Precondition bảo đảm thao tác chỉ được thực hiện khi mô hình ở trạng thái thích hợp. Sau khi thao tác, postcondition và invariant cần tiếp tục được bảo đảm.

### 11.3. Atomicity khi cập nhật

Nếu một thao tác thay đổi nhiều phần tử để giữ invariant, các thay đổi cần được áp dụng theo cách tránh để model ở trạng thái dở dang. Tùy kiến trúc, có thể dùng transaction, tạo bản sao rồi commit, hoặc validate trên một thay đổi dự kiến trước khi ghi.

Ví dụ, khi chuyển đơn sang CONFIRMED, hệ thống cần kiểm tra dòng hàng và tổng tiền trước khi lưu trạng thái mới. Nếu cập nhật trạng thái thành công nhưng ghi dòng hàng thất bại, mô hình có thể rơi vào trạng thái không hợp lệ.

### 11.4. Incremental validation

Với model lớn, kiểm tra lại toàn bộ mô hình sau mỗi thay đổi có thể tốn thời gian. Incremental validation chỉ đánh giá lại những constraint bị ảnh hưởng bởi phần tử vừa thay đổi và các phần tử phụ thuộc.

Muốn làm điều này, hệ thống cần biết:

- Constraint nào đọc thuộc tính nào.
- Phần tử nào phụ thuộc vào phần tử nào.
- Thay đổi nào làm mất hiệu lực kết quả validation cũ.
- Khi nào phải chạy lại kiểm tra toàn cục.

Incremental validation cải thiện phản hồi của editor nhưng làm tăng độ phức tạp quản lý dependency. Với DSL nhỏ, chạy lại validator toàn bộ có thể đơn giản và đủ nhanh.

## 12. Ràng buộc mô hình trong các công cụ và framework

### 12.1. UML và OCL

Trong UML, meta-model hoặc class model có thể mô tả class, thuộc tính, association và multiplicity. OCL bổ sung các điều kiện như invariant, precondition và postcondition.

Ví dụ, một class Account có thể có thuộc tính balance và invariant yêu cầu số dư không âm. Một operation withdraw(amount) có precondition rằng số tiền rút dương và không vượt số dư.

### 12.2. Eclipse Modeling Framework (EMF)

EMF dùng Ecore để mô tả meta-model. Các mô hình được tạo theo Ecore có thể được kiểm tra các ràng buộc cấu trúc và constraint được khai báo hoặc cài đặt. Trong hệ sinh thái EMF, OCL có thể được dùng để bổ sung các biểu thức ràng buộc cho model.

Các khái niệm như EClass, EAttribute, EReference, multiplicity và containment hỗ trợ định nghĩa cấu trúc. Ràng buộc nghiệp vụ phức tạp hơn có thể được đặt trong validator hoặc biểu thức OCL tùy kiến trúc.

### 12.3. JSON Schema và cấu hình khai báo

Nếu DSL có dạng JSON hoặc YAML, JSON Schema có thể kiểm tra cấu trúc dữ liệu như trường bắt buộc, kiểu, enum, giới hạn số và cấu trúc object/array.

Ví dụ JSON Schema rút gọn:

~~~json
{
  "type": "object",
  "required": ["id", "quantity"],
  "properties": {
    "id": { "type": "string", "minLength": 1 },
    "quantity": { "type": "integer", "minimum": 1 }
  }
}
~~~

Schema phù hợp với các ràng buộc cấu trúc và giá trị có thể mô tả bằng schema. Những quy tắc phụ thuộc nhiều đối tượng, symbol resolution, trạng thái hoặc dữ liệu bên ngoài thường cần validator riêng.

### 12.4. Constraint solver

Với những bài toán cần tìm cấu hình thỏa nhiều điều kiện hoặc chứng minh khả năng thỏa mãn, có thể biểu diễn ràng buộc thành SAT/SMT hoặc dùng constraint solver.

Ví dụ, hệ thống lập lịch có thể cần tìm thời điểm cho các task sao cho:

- Không có hai task độc quyền tài nguyên chạy đồng thời.
- Mỗi task nằm trong khung thời gian cho phép.
- Các phụ thuộc được thực hiện đúng thứ tự.
- Tổng thời lượng không vượt deadline.

Constraint solver có thể tìm một nghiệm hoặc chứng minh không có nghiệm trong mô hình đã biểu diễn. Đây là nhu cầu khác với validator thông thường, vốn chủ yếu kiểm tra một model instance đã có.

## 13. Những sai lầm thường gặp

1. **Chỉ dựa vào grammar:** cú pháp hợp lệ không bảo đảm mô hình có ý nghĩa hoặc thỏa quy tắc nghiệp vụ.
2. **Nhồi mọi điều kiện vào meta-model:** một số quy tắc phụ thuộc trạng thái hoặc nhiều phần tử cần constraint riêng.
3. **Đặt bội số quá chặt:** có thể vô tình cấm các trạng thái trung gian hợp lệ như đơn nháp chưa có dòng hàng.
4. **Không xác định context:** constraint duy nhất phải nói rõ duy nhất trong module, project hay toàn hệ thống.
5. **Lặp lại cùng quy tắc ở nhiều nơi:** parser, UI và runtime có thể cho kết quả khác nhau nếu mỗi nơi tự kiểm tra.
6. **Không phân biệt lỗi và cảnh báo:** một mô hình có thể hợp lệ nhưng có cấu hình đáng ngờ; severity cần thể hiện đúng mức độ.
7. **Báo lỗi không có vị trí:** người dùng khó tìm phần tử gây vi phạm.
8. **Tự động sửa không an toàn:** validator không nên tự suy đoán dữ liệu nghiệp vụ còn thiếu.
9. **Bỏ qua trạng thái runtime:** model hợp lệ tĩnh vẫn có thể không thực thi được do dữ liệu hoặc quyền hiện tại.
10. **Không kiểm thử constraint:** quy tắc mới có thể làm hỏng model instance cũ hoặc tạo false positive.

## 14. Kiểm thử ràng buộc mô hình

Một constraint cần có các ca kiểm thử cả khi điều kiện đúng và khi điều kiện sai.

### 14.1. Positive và negative cases

Với PositiveQuantity:

| Input | Kết quả kỳ vọng |
|---:|---|
| 1 | Hợp lệ |
| 2 | Hợp lệ |
| 0 | Không hợp lệ |
| -1 | Không hợp lệ |

Với ConfirmedOrderHasLines:

| Trạng thái | Số dòng | Kết quả kỳ vọng |
|---|---:|---|
| DRAFT | 0 | Hợp lệ |
| DRAFT | 1 | Hợp lệ |
| CONFIRMED | 0 | Không hợp lệ |
| CONFIRMED | 1 | Hợp lệ |

### 14.2. Boundary tests

Kiểm thử giá trị biên rất quan trọng với ràng buộc số:

- Giá trị nhỏ hơn giới hạn một đơn vị.
- Đúng bằng giới hạn.
- Lớn hơn giới hạn một đơn vị.
- Giá trị âm.
- Giá trị null hoặc undefined nếu kiểu cho phép.
- Giá trị rất lớn hoặc vượt khả năng biểu diễn.

### 14.3. Cross-reference tests

Kiểm thử tham chiếu:

- Đích tồn tại.
- Đích không tồn tại.
- Đích bị xóa sau khi tham chiếu được tạo.
- Tham chiếu trỏ đến sai loại phần tử.
- Hai tên trùng nhau trong các namespace khác nhau.
- Import bị thiếu hoặc alias xung đột.

### 14.4. Regression tests

Lưu các model instance đại diện làm fixture. Khi meta-model hoặc constraint thay đổi, chạy lại validator trên các fixture này để phát hiện quy tắc mới có làm tài liệu cũ không còn hợp lệ hay không.

Nếu thay đổi constraint là thay đổi nghiệp vụ có chủ ý, cần ghi rõ migration hoặc version của mô hình.

## 15. Quy trình thiết kế và triển khai ràng buộc

Có thể áp dụng quy trình sau:

1. **Xác định khái niệm mô hình:** liệt kê element, attribute, relationship và trạng thái.
2. **Mô tả điều kiện hợp lệ:** viết các quy tắc bằng ngôn ngữ miền, mỗi quy tắc nên có một ý nghĩa rõ.
3. **Phân loại constraint:** cấu trúc, bội số, kiểu, giá trị, duy nhất, tham chiếu, invariant hay điều kiện operation.
4. **Chọn cấp áp dụng:** meta-model, model instance, cross-model hay runtime state.
5. **Chọn cách biểu diễn:** multiplicity, type system, OCL, schema, declarative expression hoặc validator code.
6. **Xác định thời điểm đánh giá:** parse, model validation, semantic analysis, pre-execution hay runtime.
7. **Thiết kế diagnostics:** mã lỗi, severity, vị trí, thông điệp và gợi ý sửa.
8. **Tích hợp vào toolchain:** dùng cùng bộ quy tắc cho CLI, editor, CI và runtime khi phù hợp.
9. **Viết kiểm thử:** positive, negative, boundary, cross-reference và regression cases.
10. **Quản lý thay đổi:** version constraint, đánh giá ảnh hưởng lên model cũ và cung cấp migration nếu cần.

Một constraint tốt nên có tên rõ ràng, context cụ thể, biểu thức dễ hiểu, thời điểm kiểm tra xác định và thông báo lỗi có ích. Nếu một điều kiện quá phức tạp để diễn đạt hoặc kiểm thử, đó có thể là dấu hiệu mô hình hoặc ranh giới trách nhiệm cần được xem xét lại.

## 16. Kết luận

Ràng buộc mô hình xác định những điều kiện mà một mô hình DSL phải thỏa mãn ngoài cấu trúc cú pháp cơ bản. Chúng có thể mô tả bội số, kiểu, miền giá trị, tính duy nhất, tính toàn vẹn tham chiếu, invariant và điều kiện trước/sau operation. Ràng buộc có thể áp dụng lên meta-model, model instance hoặc trạng thái runtime, tùy nội dung quy tắc.

Trong kiến trúc DSL, grammar xác định cách viết, meta-model xác định cấu trúc trừu tượng, còn constraint xác định cấu trúc và dữ liệu nào được chấp nhận. Việc biểu diễn quy tắc một cách rõ ràng, đánh giá đúng giai đoạn và cung cấp diagnostics nhất quán giúp phát hiện lỗi sớm, bảo vệ ngữ nghĩa miền và làm cho DSL dễ sử dụng, kiểm thử và bảo trì.

