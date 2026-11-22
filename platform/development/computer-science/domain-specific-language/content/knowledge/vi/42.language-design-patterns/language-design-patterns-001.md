# Ngôn ngữ nhỏ và tập trung trong thiết kế DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích ý nghĩa của một ngôn ngữ nhỏ và tập trung trong thiết kế Domain-Specific Language (DSL).
- Xác định ranh giới miền và nhóm vấn đề mà ngôn ngữ cần biểu đạt.
- Chọn một tập khái niệm, từ khóa, kiểu dữ liệu và phép toán vừa đủ cho mục tiêu.
- Thiết kế grammar tối giản, nhất quán và dễ học.
- Phân biệt ngôn ngữ nhỏ với ngôn ngữ thiếu khả năng diễn đạt.
- Xác định semantic core và xây dựng các abstraction có thể kết hợp.
- Chọn giữa external DSL, internal DSL, cấu hình khai báo và API tổng quát.
- Giữ các khả năng nguy hiểm hoặc ngoài miền ở ranh giới rõ ràng.
- Mở rộng DSL mà không biến nó thành một ngôn ngữ đa mục đích khó kiểm soát.
- Kiểm thử tính dễ học, tính đúng, khả năng kết hợp và khả năng bảo trì của DSL.

## 1. Ngôn ngữ nhỏ và tập trung là gì?

Một DSL tốt thường có phạm vi hẹp và tập trung vào một nhóm tác vụ có ý nghĩa. Nó cung cấp một số ít khái niệm có sức biểu đạt cao, thay vì cố gắng mô phỏng mọi khả năng của một ngôn ngữ lập trình đa mục đích.

Ngôn ngữ nhỏ (small language) có grammar, từ khóa, kiểu và mô hình thực thi vừa đủ để mô tả bài toán trong phạm vi đã chọn. Ngôn ngữ tập trung (focused language) có các khái niệm gắn chặt với một miền cụ thể và tránh đưa vào những tính năng không phục vụ mục tiêu đó.

Ví dụ, một DSL định nghĩa quy tắc chiết khấu có thể chỉ cần:

~~~text
rule "discount_for_members" {
    when customer.isMember and order.total >= 1000000
    then discount = order.total * 0.1
}
~~~

Người dùng có thể mô tả điều kiện và hành động của quy tắc mà không cần tự viết class, vòng lặp, thread, socket hay thao tác quản lý bộ nhớ.

Một ngôn ngữ nhỏ không nhất thiết có ít dòng code trong mọi tình huống. Điều quan trọng là tập khái niệm, grammar và semantics được giới hạn rõ ràng. Một DSL có thể có nhiều built-in operation nhưng vẫn tập trung nếu tất cả đều phục vụ cùng một miền và tuân theo một mô hình thống nhất.

### 1.1. Small không có nghĩa là đơn giản hóa quá mức

Nếu ngôn ngữ thiếu khái niệm cần thiết, người dùng sẽ phải tạo workaround, lặp logic hoặc nhúng đoạn code của ngôn ngữ chủ. Khi đó, DSL nhỏ có thể trở nên khó dùng hơn một DSL có abstraction phù hợp.

### 1.2. Focused không có nghĩa là chỉ có một chức năng

Một DSL có thể hỗ trợ nhiều thao tác miễn là chúng thuộc cùng một miền và có thể kết hợp tự nhiên. Query DSL có thể hỗ trợ filter, projection, join, group, sort và aggregate; tất cả đều phục vụ việc truy vấn dữ liệu.

### 1.3. Phạm vi hẹp giúp giảm số giả định

Khi DSL chỉ xử lý một miền, thiết kế có thể quy định rõ kiểu dữ liệu, quyền, thứ tự thực thi, lỗi và giới hạn. Người dùng ít phải suy đoán hành vi hơn.

## 2. Vì sao nên thiết kế DSL nhỏ và tập trung?

Một DSL chuyên biệt thường được dùng bởi nhiều người có mức độ hiểu biết lập trình khác nhau. Ngôn ngữ nhỏ giúp người dùng học nhanh và giúp hệ thống kiểm soát hành vi.

Các lợi ích chính:

- **Dễ học:** ít keyword, rule và kiểu dữ liệu cần ghi nhớ.
- **Dễ đọc:** source thể hiện trực tiếp ý định trong miền.
- **Dễ kiểm tra:** grammar và semantics có phạm vi nhỏ hơn.
- **An toàn hơn:** chỉ cung cấp capability được phép.
- **Dễ tối ưu:** compiler hiểu cấu trúc và ý nghĩa của các operation.
- **Dễ tài liệu hóa:** ví dụ có thể bao phủ phần lớn cách dùng.
- **Dễ tiến hóa:** thay đổi có thể được đánh giá trong phạm vi rõ.
- **Dễ tích hợp:** DSL có thể sinh query, workflow, API call hoặc cấu hình có cấu trúc.

### 2.1. Giảm cognitive load

Người dùng cần hiểu ít khái niệm hơn để hoàn thành một tác vụ. Ví dụ, một DSL cấu hình alert có thể chỉ cần condition, threshold, window và action. Người dùng không cần học toàn bộ API của hệ thống scheduling nếu không trực tiếp dùng đến.

### 2.2. Giảm accidental complexity

Accidental complexity là độ phức tạp không thuộc bản chất bài toán, phát sinh từ cách triển khai. DSL có thể ẩn đi boilerplate, resource management và chi tiết giao thức để người dùng tập trung vào quyết định nghiệp vụ.

### 2.3. Giới hạn capability

Nếu người dùng chỉ được phép khai báo truy vấn đọc, DSL không cần cung cấp thao tác ghi file tùy ý hoặc chạy shell command. Phạm vi ngôn ngữ có thể trở thành một phần của security boundary, với điều kiện runtime cũng thực thi giới hạn đó.

### 2.4. Tăng khả năng kiểm chứng

Một DSL nhỏ có thể định nghĩa invariants rõ ràng, kiểm tra tĩnh nhiều hơn và tạo bộ test bao phủ các trường hợp quan trọng.

## 3. Bắt đầu từ miền vấn đề

Thiết kế ngôn ngữ không nên bắt đầu bằng danh sách keyword. Hãy bắt đầu bằng việc hiểu công việc mà người dùng cần mô tả.

### 3.1. Xác định người dùng

Người dùng chính có thể là:
- Domain expert.
- Developer.
- Data analyst.
- System operator.
- Business analyst.
- Người cấu hình quy trình.
- Một công cụ hoặc service khác sinh DSL tự động.

Mỗi nhóm có kiến thức, mục tiêu và giới hạn khác nhau. DSL dành cho domain expert cần từ vựng gần nghiệp vụ; DSL dành cho developer có thể cho phép abstraction kỹ thuật hơn.

### 3.2. Xác định tác vụ thường gặp

Thu thập các ví dụ thực tế:
- Tác vụ được thực hiện thường xuyên nhất.
- Quy tắc được thay đổi thường xuyên nhất.
- Loại lỗi người dùng hay mắc.
- Input và output phổ biến.
- Các ngoại lệ quan trọng.
- Quyết định cần kiểm soát hoặc audit.

Những tác vụ lặp lại thường là ứng viên tốt cho DSL.

### 3.3. Xác định ranh giới miền

Hỏi rõ DSL chịu trách nhiệm đến đâu. Một workflow DSL có thể mô tả thứ tự step, branch, retry và compensation, nhưng việc thực hiện HTTP request có thể thuộc connector riêng.

Ranh giới tốt giúp DSL tránh ôm cả scheduling, persistence, security, network và user interface vào một grammar duy nhất.

### 3.4. Xác định non-goals

Liệt kê những gì DSL không nhằm giải quyết. Ví dụ, một DSL định nghĩa policy có thể không hỗ trợ tạo giao diện hoặc truy cập filesystem tùy ý.

Non-goals giúp từ chối feature không phù hợp một cách có căn cứ.

### 3.5. Thu thập ngôn ngữ của miền

Ghi lại các danh từ, động từ, trạng thái và quan hệ mà chuyên gia miền dùng. Ví dụ trong quản lý đơn hàng: order, item, reserve, authorize, ship, cancel và refund.

Từ vựng này có thể trở thành tên type, operation và event trong DSL.

## 4. Chọn đúng mức độ chuyên biệt

Không phải mọi bài toán đều cần một DSL mới. Có thể chọn giữa API tổng quát, cấu hình, internal DSL và external DSL.

| Cách tiếp cận | Phù hợp khi | Điểm cần cân nhắc |
|---|---|---|
| API của ngôn ngữ chủ | Người dùng chủ yếu là developer | Cú pháp phụ thuộc ngôn ngữ chủ |
| Configuration format | Chủ yếu khai báo giá trị và lựa chọn | Không phù hợp logic phức tạp |
| Internal DSL | Muốn tận dụng type system và toolchain hiện có | Grammar bị giới hạn bởi host language |
| External DSL | Cần cú pháp riêng gần ngôn ngữ miền | Cần parser, compiler và tooling |
| General-purpose language | Bài toán rộng và thay đổi khó dự đoán | Nhiều capability hơn nhu cầu miền |

### 4.1. Khi cấu hình là đủ

Nếu người dùng chỉ cần chọn endpoint, timeout và retry count, YAML hoặc JSON có thể đã đủ. Không cần tạo parser mới chỉ để khai báo vài giá trị.

### 4.2. Khi cần biểu thức

Nếu người dùng cần kết hợp điều kiện, tính toán và chọn nhánh, một DSL biểu thức có thể phù hợp hơn file cấu hình thuần.

### 4.3. Khi cần workflow

Nếu có step, dependency, parallel branch, timeout và compensation, workflow DSL có thể biểu đạt rõ hơn một cấu hình phẳng.

### 4.4. Khi cần logic tùy ý

Nếu người dùng cần thuật toán không dự đoán trước hoặc tương tác với nhiều API tổng quát, một ngôn ngữ đa mục đích có thể phù hợp hơn. DSL vẫn có thể gọi extension được kiểm soát.

## 5. Xác định semantic core

Semantic core là tập khái niệm và quy tắc nền tảng quyết định cách DSL hoạt động. Những feature khác nên được xây dựng trên core này.

Ví dụ một query DSL có thể có core:
- Source.
- Expression.
- Predicate.
- Projection.
- Join.
- Aggregation.
- Ordering.

Một workflow DSL có thể có core:
- Workflow.
- Step.
- Transition.
- State.
- Branch.
- Event.
- Failure policy.

### 5.1. Core nhỏ nhưng có sức biểu đạt

Core nên có ít primitive, nhưng các primitive phải kết hợp được để biểu diễn nhiều use case trong miền.

### 5.2. Không nhân đôi semantics

Nếu hai keyword có hành vi gần như giống nhau, hãy cân nhắc liệu chúng có thực sự cần thiết. Hai cách viết cho cùng một thao tác có thể làm tài liệu và tooling phức tạp.

### 5.3. Phân biệt primitive và convenience syntax

Primitive là thao tác nền tảng mà runtime hiểu trực tiếp. Convenience syntax là cách viết ngắn hơn được hạ xuống primitive.

Ví dụ, một operation sortBy có thể là sugar cho ordering expression và sort operator.

### 5.4. Định nghĩa semantics trước syntax

Trước khi chọn dấu ngoặc hoặc tên keyword, hãy mô tả:
- Input và output.
- Điều kiện thực hiện.
- Side effect.
- Error behavior.
- Evaluation order.
- Null behavior.
- Resource limit.

Khi semantics rõ, grammar dễ được thiết kế nhất quán hơn.

## 6. Thiết kế grammar tối giản

Grammar quy định các câu lệnh và biểu thức hợp lệ. Grammar của DSL nhỏ nên có cấu trúc dễ học, tránh quá nhiều ngoại lệ.

### 6.1. Dùng block nhất quán

Ví dụ:

~~~text
rule "high_value_order" {
    when order.total >= 1000000
    then markForReview(order)
}
~~~

Các block có thể dùng cùng quy tắc mở và đóng, giúp người đọc nhận ra cấu trúc.

### 6.2. Tránh keyword đồng nghĩa

Nếu DSL đã dùng when cho điều kiện, không nên thêm if, where và condition chỉ để diễn đạt cùng một ý mà không có khác biệt semantics.

### 6.3. Giữ precedence đơn giản

Một grammar có nhiều mức precedence và operator overload có thể khó học. Hãy cung cấp quy tắc nhất quán và khuyến khích dùng ngoặc khi biểu thức phức tạp.

### 6.4. Ưu tiên cấu trúc có thể đọc được

Một DSL không cần tối thiểu số ký tự. Tên rõ và block tường minh thường hữu ích hơn cú pháp quá ngắn.

### 6.5. Quy định comment và format

Comment, indentation, quote style và line continuation cần được mô tả. Formatter tự động giúp source thống nhất.

### 6.6. Error recovery

Parser nên đưa ra lỗi gần vị trí sai và cố gắng tiếp tục phân tích để hiển thị nhiều diagnostic có ích. Không nên tạo hàng loạt lỗi phụ gây nhiễu.

## 7. Giữ từ vựng gần miền

Tên type và operation nên phản ánh ngôn ngữ mà người dùng miền đã hiểu.

Ví dụ trong DSL đặt lịch:

~~~text
schedule "daily_report" {
    at = "08:00"
    on = weekdays
    run generateReport()
}
~~~

Người dùng có thể hiểu schedule, at, weekdays và run mà không cần biết thread scheduler hoạt động thế nào.

### 7.1. Dùng danh từ cho resource

Tên như Customer, Order, Invoice hoặc Dataset giúp nhận diện đối tượng.

### 7.2. Dùng động từ cho operation

Tên như reserve, approve, publish hoặc archive mô tả hành động.

### 7.3. Dùng trạng thái có nghĩa

Enum như PENDING, APPROVED, REJECTED và COMPLETED thể hiện lifecycle. Tránh dùng chuỗi tự do nếu tập trạng thái đã được xác định.

### 7.4. Tránh thuật ngữ mơ hồ

Tên như process, handle hoặc execute có thể quá chung. Nếu có thể, chọn tên mô tả tác động thực tế.

### 7.5. Nhất quán ngôn ngữ

Không nên trộn nhiều cách đặt tên hoặc viết tắt tùy tiện. Tài liệu nên quy định cách đặt tên và từ vựng chính thức.

## 8. Kiểu dữ liệu và hệ thống kiểu nhỏ

Một DSL tập trung thường không cần hàng trăm type. Nó cần những type phù hợp với miền và có semantics rõ.

### 8.1. Primitive type

Có thể gồm:
- Boolean.
- Integer.
- Decimal.
- String.
- Date.
- Instant.
- Duration.

### 8.2. Domain type

Domain type biểu diễn khái niệm miền:
- Money.
- CustomerId.
- OrderStatus.
- EmailAddress.
- Percentage.
- DatasetRef.

Dùng domain type giúp compiler phát hiện nhầm lẫn giữa các giá trị cùng representation nhưng khác ý nghĩa.

### 8.3. Collection

List, Set và Map có thể đủ cho nhiều DSL. Chỉ thêm loại collection khác khi có use case cụ thể.

### 8.4. Optional và nullable

Cần phân biệt field có thể vắng mặt với field có thể chứa null. Nếu DSL không cần nullable, loại bỏ complexity này có thể làm semantics đơn giản hơn.

### 8.5. Type inference

Type inference giảm cú pháp khai báo, nhưng diagnostic cần cho biết kiểu compiler đã suy luận. Với contract quan trọng, type annotation có thể hữu ích.

### 8.6. Conversion

Chỉ cho phép implicit conversion khi không gây bất ngờ. Chuyển đổi có thể mất precision hoặc thay đổi timezone nên thường cần viết tường minh.

## 9. Giới hạn expression và control flow

Một DSL nhỏ không cần sao chép toàn bộ control flow của ngôn ngữ đa mục đích.

### 9.1. Expression

Có thể hỗ trợ:
- Literal.
- Field access.
- Arithmetic.
- Comparison.
- Boolean logic.
- Function call.
- Conditional expression.
- Collection expression.

### 9.2. Control flow có giới hạn

Một rule DSL có thể chỉ cần when/then. Một workflow DSL có thể cần sequence, branch, parallel và join. Không nhất thiết phải hỗ trợ arbitrary loop hoặc recursion nếu miền không cần.

### 9.3. Bảo đảm kết thúc

Với policy hoặc rule engine, giới hạn loop hoặc recursion giúp tránh chương trình không kết thúc. Nếu không cần loop, không đưa nó vào core.

### 9.4. Side effect rõ ràng

Tách expression thuần khỏi action có side effect. Điều này giúp compiler và người dùng biết expression nào có thể tính trước, cache hoặc đánh giá lại.

### 9.5. Evaluation order

Quy định short-circuit, thứ tự argument, thứ tự action và behavior khi có exception. Các quy tắc nhỏ nhưng ảnh hưởng lớn đến tính đúng.

## 10. Composability: kết hợp primitive để tạo use case

Composability là khả năng kết hợp các thành phần nhỏ thành cấu trúc lớn hơn mà vẫn giữ semantics nhất quán.

Ví dụ query DSL:

~~~text
orders
    .filter(status == PAID)
    .filter(createdAt >= startOfMonth())
    .groupBy(customerId)
    .sum(total)
~~~

Mỗi operation làm một việc:
- filter chọn record.
- groupBy tạo nhóm.
- sum tổng hợp giá trị.

Các operation có thể kết hợp mà không cần tạo keyword mới cho từng câu truy vấn.

### 10.1. Function composition

Kết quả của một operation có thể là input của operation tiếp theo nếu type tương thích.

### 10.2. Reuse abstraction

Một predicate có thể được đặt tên và tái sử dụng:

~~~text
let isActiveCustomer = customer.active and customer.verified

customers.filter(isActiveCustomer)
~~~

### 10.3. Pipeline

Pipeline làm rõ luồng dữ liệu từ source qua transformation đến result.

### 10.4. Composition cần type compatibility

Không phải hai operation bất kỳ đều kết hợp được. Type system phải xác định output của operation trước có phù hợp input của operation sau hay không.

### 10.5. Tránh combinatorial syntax

Nếu mỗi tổ hợp có một keyword riêng, grammar sẽ tăng rất nhanh. Hãy xây một số primitive có thể kết hợp thay vì thêm syntax cho mọi trường hợp.

## 11. Abstraction và escape hatch

DSL cần abstraction đủ cao để đơn giản hóa công việc, nhưng đôi khi người dùng cần truy cập khả năng thấp hơn.

### 11.1. Abstraction

Abstraction che chi tiết triển khai và đưa ra khái niệm có ý nghĩa trong miền. Ví dụ reserveInventory thay vì tự viết SQL update và lock record.

### 11.2. Escape hatch

Escape hatch là cách truy cập một khả năng ngoài core DSL, chẳng hạn gọi function được viết trong host language.

~~~text
rule "custom_check" {
    when extension("risk-engine").evaluate(customer, order)
    then approveIfSafe(order)
}
~~~

### 11.3. Kiểm soát extension

Extension cần contract, type, permission, timeout và error mapping. Không nên cho phép mọi source tùy ý chạy với toàn bộ quyền của host process.

### 11.4. Không để escape hatch trở thành đường chính

Nếu phần lớn chương trình phải gọi host code để thực hiện tác vụ cơ bản, DSL có thể thiếu abstraction quan trọng hoặc đã chọn sai ranh giới miền.

### 11.5. Versioning extension

Extension API cần version và compatibility policy. DSL runtime nên phát hiện extension không tương thích trước khi chạy workflow.

## 12. Phạm vi an toàn và capability

Một DSL tập trung có thể giới hạn những gì chương trình được phép làm.

### 12.1. Capability-based design

Thay vì cho chương trình quyền truy cập toàn bộ hệ thống, runtime cấp capability cụ thể như:
- ReadCustomer.
- WriteOrder.
- PublishEvent.
- QueryDataset.
- CallApprovedConnector.

### 12.2. Least privilege

Một rule chỉ cần đọc customer và tính điểm không cần quyền gửi thanh toán. Giới hạn capability giảm hậu quả khi rule sai hoặc bị lợi dụng.

### 12.3. Resource budget

DSL có thể giới hạn:
- Execution time.
- Số record đọc.
- Số lần gọi connector.
- Memory.
- Số step.
- Độ sâu expression.
- Số nhánh song song.

### 12.4. Không dựa vào grammar như cơ chế bảo mật duy nhất

Ngay cả khi grammar không có câu lệnh đọc file, extension hoặc runtime vẫn có thể làm điều đó. Security boundary phải được thực thi tại runtime và hệ điều hành.

### 12.5. Audit

Các action có side effect cần ghi nhận identity, operation, resource, thời điểm và kết quả theo chính sách audit.

## 13. Semantic core và interpreter/compiler

Một ngôn ngữ nhỏ có thể có interpreter đơn giản hoặc compiler riêng. Lựa chọn phụ thuộc mục tiêu hiệu năng, tooling và cách triển khai.

### 13.1. Interpreter

Interpreter đọc AST hoặc IR rồi thực hiện operation. Nó thường dễ xây dựng ban đầu và phù hợp khi:
- DSL nhỏ.
- Chương trình thay đổi thường xuyên.
- Compile-time optimization chưa cần thiết.
- Cần tương tác hoặc debug từng node.

### 13.2. Compiler

Compiler chuyển source DSL thành code hoặc bytecode. Nó có thể phù hợp khi:
- Có nhiều lần thực thi cùng một chương trình.
- Cần tối ưu mạnh.
- Cần target cụ thể.
- Muốn kiểm tra tĩnh trước runtime.

### 13.3. IR dùng chung

Một semantic core có thể được biểu diễn thành IR rồi thực thi bởi interpreter hoặc sinh code cho nhiều target.

~~~text
DSL Source
    |
    v
Parser
    |
    v
Typed AST / IR
    |             |
    v             v
Interpreter   Code Generator
    |             |
    v             v
Execution     Target Runtime
~~~

### 13.4. Giữ core độc lập backend

Không nên đưa chi tiết JVM hoặc database cụ thể vào semantics của DSL nếu ngôn ngữ cần hỗ trợ nhiều target. Backend có thể có capability riêng nhưng phải tuân thủ contract chung.

## 14. Tách ngôn ngữ khỏi host application

DSL thường được nhúng trong một ứng dụng lớn hơn. Cần xác định trách nhiệm của DSL và host.

### 14.1. DSL chịu trách nhiệm

Ví dụ:
- Biểu diễn policy.
- Chọn branch.
- Mô tả query.
- Định nghĩa workflow.
- Xác định input/output của operation.

### 14.2. Host chịu trách nhiệm

Host có thể quản lý:
- Authentication.
- Secret.
- Connection pool.
- Database transaction.
- Scheduling.
- Persistence.
- Observability.
- Runtime resource limits.

### 14.3. Boundary contract

DSL chỉ nên nhìn thấy operation và type mà host công bố. Host chịu trách nhiệm thực thi và kiểm soát capability.

### 14.4. Giảm coupling

Không để source DSL phụ thuộc class nội bộ hoặc tên package không ổn định của host application. Dùng API contract hoặc extension interface được version hóa.

## 15. Tính dễ học và khả năng khám phá

Một DSL nhỏ cần giúp người dùng đoán được cách dùng từ những gì họ đã biết.

### 15.1. Principle of least surprise

Cùng một cấu trúc nên có hành vi nhất quán. Nếu dấu bằng trong một block có nghĩa assignment, không nên dùng cùng ký hiệu với semantics khác mà không có lý do rõ.

### 15.2. Discoverability

Editor có thể gợi ý:
- Keyword hợp lệ.
- Field và type.
- Function có thể gọi.
- Argument name.
- Enum value.
- Error explanation.

### 15.3. Diagnostics hữu ích

Thông báo lỗi nên chỉ rõ:
- Vị trí lỗi.
- Cấu trúc mong đợi.
- Kiểu thực tế và kiểu mong đợi.
- Gợi ý sửa nếu có.
- Link tới tài liệu liên quan.

### 15.4. Quick start

Một quick start nên cho phép người mới viết và chạy một ví dụ nhỏ trong thời gian ngắn, sau đó mở rộng dần sang khái niệm khác.

### 15.5. Consistent examples

Ví dụ tài liệu nên dùng cùng tên type, field và status để người học không phải suy luận nhiều bộ thuật ngữ.

## 16. Mở rộng DSL mà không mất tập trung

Một DSL có thể phát triển theo thời gian. Mỗi feature mới cần được đánh giá theo lợi ích, complexity và tác động đến semantic core.

### 16.1. Feature request

Với mỗi yêu cầu, hỏi:
- Có phải use case phổ biến trong miền không?
- Có thể biểu diễn bằng primitive hiện có không?
- Feature có tạo semantics mới không?
- Có làm grammar khó học hơn không?
- Có ảnh hưởng security hoặc runtime không?
- Có cách triển khai ở library hoặc extension không?

### 16.2. Library trước syntax mới

Nếu một thao tác có thể được cung cấp bằng function hoặc library mà không làm cú pháp khó hiểu, hãy cân nhắc library trước khi thêm keyword.

### 16.3. Syntax sugar có giới hạn

Syntax sugar giúp source dễ viết nhưng không nên có quá nhiều cách viết tương đương. Mỗi dạng mới tăng gánh nặng cho parser, formatter, documentation và tooling.

### 16.4. Experimental feature

Feature thử nghiệm có thể được đặt trong namespace hoặc version flag để thu thập phản hồi mà không cam kết lâu dài.

### 16.5. Deprecation

Khi thay feature, đưa ra cảnh báo, migration guide và thời gian chuyển tiếp. Không xóa cú pháp đang dùng mà không có policy version rõ.

### 16.6. Complexity budget

Có thể duy trì một ngân sách complexity định tính: số keyword, số loại block, số cách khai báo cùng một khái niệm, số exception trong grammar và số behavior phụ thuộc context. Feature mới phải chứng minh giá trị tương xứng.

## 17. Ví dụ thiết kế: DSL nhỏ cho policy truy cập

Giả sử cần mô tả policy cho một ứng dụng nội bộ. Mục tiêu là quyết định người dùng có thể đọc một resource hay không.

### 17.1. Phạm vi

DSL chỉ mô tả:
- Subject.
- Resource.
- Action.
- Condition.
- Effect.

DSL không tự quản lý identity provider hoặc database.

### 17.2. Grammar minh họa

~~~text
policy "read_own_profile" {
    subject = user
    action = READ
    resource = CustomerProfile

    when resource.ownerId == user.id

    effect = ALLOW
}
~~~

### 17.3. Semantic core

Core chỉ cần:
- Policy declaration.
- Subject reference.
- Resource reference.
- Action enum.
- Boolean expression.
- Effect ALLOW hoặc DENY.

### 17.4. Ví dụ thứ hai

~~~text
policy "admin_read_all_profiles" {
    subject = user
    action = READ
    resource = CustomerProfile

    when user.role == ADMIN

    effect = ALLOW
}
~~~

Hai policy có thể dùng chung type và expression. Không cần một keyword riêng cho từng vai trò.

### 17.5. Runtime contract

Runtime cung cấp subject và resource context, đánh giá policy và trả decision. Runtime chịu trách nhiệm lấy identity đáng tin cậy và thực thi decision ở endpoint.

### 17.6. Kiểm tra conflict

Nếu một policy ALLOW và một policy DENY cùng match, DSL cần định nghĩa precedence hoặc combining algorithm. Không nên để thứ tự file vô tình quyết định quyền truy cập.

### 17.7. Giới hạn an toàn

Không cung cấp function tùy ý có side effect trong điều kiện policy. Điều kiện nên thuần và có resource budget để tránh request authorization bị treo.

## 18. Ví dụ thiết kế: DSL nhỏ cho pipeline dữ liệu

Một pipeline DSL có thể mô tả nguồn dữ liệu và các transformation.

~~~text
pipeline "monthly_sales" {
    source orders

    filter status == PAID
    filter createdAt in currentMonth()

    group by customerId
    aggregate totalSales = sum(total)

    sort totalSales descending
    output monthly_customer_sales
}
~~~

### 18.1. Khái niệm miền

- Source.
- Filter.
- Group.
- Aggregate.
- Sort.
- Output.

Đây là một semantic core nhỏ nhưng đủ diễn đạt một nhóm tác vụ phân tích phổ biến.

### 18.2. Type checking

Compiler kiểm tra:
- Source orders tồn tại.
- status là field hợp lệ.
- total có kiểu số.
- customerId có thể dùng làm group key.
- Output schema phù hợp với aggregate.

### 18.3. Optimization

Engine có thể push filter xuống database, chỉ đọc field cần thiết và thực hiện aggregate gần nơi dữ liệu lưu trữ.

### 18.4. Giới hạn

Nếu người dùng cần thuật toán thống kê đặc biệt, có thể gọi một extension đã được đăng ký thay vì thêm toàn bộ thư viện toán học vào grammar.

## 19. Ví dụ thiết kế: DSL nhỏ cho workflow

Một workflow DSL có thể mô tả sequence và nhánh có giới hạn.

~~~text
workflow "publish_article" {
    step validateContent

    if content.isApproved {
        step publishArticle
        step notifySubscribers
    } else {
        step requestChanges
    }
}
~~~

### 19.1. Core

- Workflow.
- Step.
- Condition.
- Sequence.
- Branch.

Nếu cần retry, timeout hoặc compensation, có thể thêm chúng như policy gắn với step.

### 19.2. Không nhúng mọi chi tiết runtime

Source không cần mô tả thread pool, database connection hay message broker internals. Runtime quản lý những chi tiết này.

### 19.3. State và resume

Nếu workflow cần chạy lâu, runtime lưu state và step completion. DSL chỉ mô tả các transition và policy có ý nghĩa với người thiết kế quy trình.

### 19.4. Side effect boundary

Action như publishArticle có side effect. Runtime cần ghi trạng thái và định nghĩa retry/idempotency để tránh publish trùng khi process crash.

## 20. Kiểm thử một DSL nhỏ và tập trung

Một DSL nhỏ vẫn cần kiểm thử ở nhiều lớp.

### 20.1. Grammar test

Kiểm tra source hợp lệ và không hợp lệ. Đảm bảo parser tạo AST đúng cấu trúc.

### 20.2. Semantic test

Kiểm tra type, scope, precedence, null behavior và evaluation order.

### 20.3. Interpreter/compiler equivalence

Nếu có cả interpreter và compiler, chạy cùng chương trình và input rồi so sánh kết quả cùng side effect.

### 20.4. Composition test

Kiểm tra primitive có thể kết hợp như dự kiến. Ví dụ filter rồi groupBy rồi aggregate phải có type và output hợp lệ.

### 20.5. Negative test

Kiểm tra operation ngoài miền, field không tồn tại, type sai, capability thiếu và resource vượt giới hạn.

### 20.6. Usability test

Đưa DSL cho người dùng mục tiêu và yêu cầu họ hoàn thành một tác vụ. Quan sát:
- Họ có hiểu từ vựng không?
- Có đoán được cấu trúc không?
- Có mắc lỗi lặp lại không?
- Thông báo lỗi có giúp họ sửa không?
- Họ có cần host code cho tác vụ phổ biến không?

### 20.7. Evolution test

Khi thêm feature, kiểm tra grammar cũ, migration, formatter, editor support và backward compatibility.

## 21. Đánh giá mức độ tập trung của DSL

Có thể dùng các câu hỏi sau để đánh giá thiết kế:

- Phần lớn feature có phục vụ cùng một miền không?
- Người dùng có thể hoàn thành tác vụ phổ biến mà không thoát khỏi DSL không?
- Có nhiều keyword hoặc syntax trùng ý nghĩa không?
- Có quá nhiều trường hợp đặc biệt trong grammar không?
- Người dùng có cần biết implementation detail không?
- Có thể mô tả core bằng một tập nhỏ khái niệm không?
- Security boundary có rõ không?
- Có thể kiểm tra source trước khi thực thi không?
- Feature mới có thể được thêm qua library thay vì syntax không?
- Có thể giải thích toàn bộ semantics cho người mới bằng tài liệu có cấu trúc không?

Một DSL không cần đạt số lượng keyword thấp nhất. Mục tiêu là tỷ lệ tốt giữa khả năng biểu đạt và complexity mà người dùng phải hiểu.

## 22. Những dấu hiệu DSL đang mất tập trung

### 22.1. Mỗi use case cần một keyword mới

Nếu mỗi nghiệp vụ mới đều yêu cầu keyword riêng, có thể semantic core chưa đủ tổng quát hoặc abstraction đang quá cụ thể.

### 22.2. Có nhiều cách viết cùng một việc

Quá nhiều alias và syntax sugar khiến người học khó biết nên dùng dạng nào.

### 22.3. Cú pháp bắt đầu giống ngôn ngữ đa mục đích

Nếu DSL bổ sung class, inheritance, thread, pointer, arbitrary file I/O và dynamic code execution mà không phục vụ miền cụ thể, có thể đã vượt phạm vi.

### 22.4. Người dùng thường xuyên thoát sang host code

Điều này có thể cho thấy DSL thiếu một primitive quan trọng. Cần phân tích pattern trước khi thêm feature.

### 22.5. Documentation và diagnostics tăng phức tạp nhanh

Nếu mỗi feature tạo nhiều ngoại lệ và tương tác khó giải thích, complexity đang tăng nhanh hơn giá trị.

### 22.6. Không thể xác định ai sở hữu semantics

Nếu DSL, host application và plugin cùng định nghĩa hành vi cho một operation, người dùng khó biết contract nào có thẩm quyền.

## 23. Quy trình thiết kế một ngôn ngữ nhỏ

Một quy trình có thể thực hiện như sau:

1. Chọn một miền và một nhóm người dùng rõ.
2. Thu thập các tác vụ thực tế và ngôn ngữ chuyên môn.
3. Xác định non-goals và ranh giới host application.
4. Liệt kê khái niệm miền cốt lõi.
5. Chọn semantic core nhỏ nhất đủ cho use case.
6. Định nghĩa type, expression và side effect.
7. Viết grammar nhất quán.
8. Xây một interpreter hoặc compiler prototype.
9. Viết ví dụ cho tác vụ phổ biến và trường hợp lỗi.
10. Kiểm thử composition và semantics.
11. Thử với người dùng mục tiêu.
12. Loại bỏ syntax trùng lặp hoặc abstraction không cần.
13. Bổ sung extension point có kiểm soát.
14. Version hóa và xây migration policy.
15. Theo dõi cách dùng thực tế trước khi thêm feature lớn.

## 24. Các trade-off cần cân nhắc

| Quyết định | Lợi ích | Chi phí hoặc rủi ro |
|---|---|---|
| Grammar rất nhỏ | Dễ học và parse | Có thể thiếu khả năng biểu đạt |
| Nhiều syntax sugar | Source ngắn | Tăng grammar và tài liệu |
| Type system mạnh | Bắt lỗi sớm | Tăng complexity của compiler |
| Escape hatch rộng | Linh hoạt | Giảm khả năng kiểm soát |
| External DSL | Cú pháp phù hợp miền | Cần parser và tooling riêng |
| Internal DSL | Tận dụng host language | Bị giới hạn bởi host syntax |
| Interpreter | Dễ prototype | Có thể chậm khi chạy nhiều |
| Compiler | Tối ưu và kiểm tra sâu | Chi phí xây dựng cao |
| Primitive ít | Semantic core gọn | Cần composition tốt |
| Extension nhiều | Dễ mở rộng | Khó quản lý compatibility và security |

Không có lựa chọn tốt nhất cho mọi DSL. Hãy ưu tiên mục tiêu và người dùng cụ thể.

## 25. Bài tập tự kiểm tra

### Bài 1: Xác định miền

Chọn một bài toán như phân loại đơn hàng, truy vấn dữ liệu hoặc lập lịch. Xác định người dùng, input, output và non-goals của DSL.

### Bài 2: Core concepts

Liệt kê năm đến bảy khái niệm cốt lõi cho miền đã chọn. Giải thích vì sao mỗi khái niệm cần thiết.

### Bài 3: Grammar

Thiết kế một grammar nhỏ cho một operation. Chỉ ra keyword, identifier, literal và block.

### Bài 4: Primitive và syntax sugar

Chọn một cú pháp thuận tiện và mô tả cách hạ nó xuống primitive. Nêu lợi ích của việc giữ primitive đơn giản.

### Bài 5: Type system

Xác định type cần thiết và một lỗi type mà compiler nên phát hiện trước runtime.

### Bài 6: Composability

Kết hợp ba primitive để giải quyết một use case mới mà không thêm keyword. Giải thích type giữa các bước.

### Bài 7: Escape hatch

Đề xuất một extension point cho khả năng ngoài core. Xác định permission, input/output contract và timeout.

### Bài 8: Security boundary

Thiết kế capability cho một policy DSL chỉ được đọc một nhóm dữ liệu. Nêu cách runtime thực thi giới hạn.

### Bài 9: Usability test

Thiết kế một bài kiểm tra với người dùng mục tiêu để đánh giá họ có thể viết một chương trình nhỏ mà không cần trợ giúp hay không.

### Bài 10: Feature review

Có đề xuất thêm loop, class và arbitrary file I/O vào một rule DSL. Dùng tiêu chí về domain fit, complexity và security để quyết định feature nào nên được thêm.

## Kết luận

Ngôn ngữ nhỏ và tập trung là một mẫu thiết kế quan trọng của DSL: giới hạn phạm vi vào một miền rõ ràng, chọn semantic core gọn và cung cấp các primitive có thể kết hợp để giải quyết nhiều tác vụ liên quan. Thiết kế tốt bắt đầu từ người dùng, công việc và ranh giới miền, sau đó mới quyết định từ vựng, grammar, type system, runtime và extension point. Ngôn ngữ cần đủ khả năng diễn đạt use case phổ biến nhưng không mang theo những capability và cú pháp không phục vụ mục tiêu. Khi có escape hatch, nó phải được kiểm soát bằng contract, permission và resource limit. Việc kiểm thử grammar, semantics, composition và usability giúp xác nhận DSL thực sự dễ học và dễ dùng. Qua từng phiên bản, library, syntax sugar và feature mới cần được đánh giá theo giá trị thực tế để DSL tiếp tục phát triển mà vẫn giữ được sự tập trung và nhất quán.
