# Đường cong học tập trong thiết kế DSL

## Mục tiêu

Đường cong học tập mô tả nỗ lực cần thiết để người dùng hiểu, áp dụng và thành thạo một ngôn ngữ chuyên biệt. Trong thiết kế DSL, đây là một trade-off giữa thời gian bắt đầu, khả năng biểu đạt, tính nhất quán, độ an toàn và chi phí bảo trì.

Một ngôn ngữ có thể rất dễ viết ví dụ đầu tiên nhưng khó khi người dùng phải hiểu kiểu dữ liệu, thứ tự thực thi, lỗi, side effect hoặc tích hợp. Ngược lại, cú pháp ban đầu tường minh hơn có thể giảm nhầm lẫn trong các tác vụ thực tế.

## 1. Các giai đoạn học

Người dùng thường trải qua các giai đoạn sau:

1. Khám phá mục đích và phạm vi DSL.
2. Cài đặt công cụ và chạy ví dụ đầu tiên.
3. Hiểu cú pháp, kiểu dữ liệu và mô hình thực thi.
4. Tự hoàn thành tác vụ phổ biến.
5. Xử lý lỗi, tích hợp và tình huống phức tạp.
6. Đọc, review và bảo trì chương trình của người khác.

Cần phân biệt time-to-first-success với time-to-proficiency. Chạy được Hello World sau vài phút không có nghĩa người dùng đã biết xây workflow có retry hoặc truy vấn dữ liệu lớn.

Learning curve cũng khác nhau theo persona. Developer quen SQL có thể học query DSL nhanh; domain expert hiểu nghiệp vụ nhưng chưa quen type system; operator hiểu cấu hình nhưng cần thêm kỹ năng debug.

## 2. Learning curve là một trade-off

Mỗi lựa chọn thiết kế ảnh hưởng đến lượng kiến thức người dùng phải nắm.

| Lựa chọn | Lợi ích | Chi phí |
|---|---|---|
| Ít keyword | Dễ ghi nhớ | Có thể thiếu khả năng biểu đạt |
| Cú pháp shorthand | Viết nhanh | Tăng quy tắc phải nhớ |
| Type inference | Ít annotation | Kiểu khó khám phá nếu diagnostic kém |
| Default mạnh | Dễ bắt đầu | Behavior có thể khó đoán |
| Generic abstraction | Tái sử dụng | Tăng độ khó của type system |
| Escape hatch | Linh hoạt | Tăng coupling và giảm kiểm soát |
| Syntax tường minh | Dễ review | Source dài hơn |

Thiết kế cần cân bằng người mới với người dùng nâng cao. Giảm mọi chi tiết có thể làm mất khả năng kiểm soát; phơi bày mọi chi tiết ngay từ đầu tạo cognitive overload.

## 3. Cognitive load

Cognitive load là lượng thông tin người học phải xử lý cùng lúc. Có thể phân biệt:

- Intrinsic load: độ phức tạp vốn có của bài toán.
- Extraneous load: độ phức tạp do notation, tài liệu hoặc tooling không tốt.
- Germane load: nỗ lực xây dựng mô hình hiểu biết.

DSL không thể loại bỏ độ phức tạp vốn có của miền, nhưng có thể giảm phần tải không cần thiết.

### 3.1. Độ khó vốn có

Một workflow thanh toán có nhiều trạng thái, timeout, retry và compensation. Những quy tắc này tồn tại trong nghiệp vụ, dù cú pháp có đơn giản đến đâu.

### 3.2. Độ khó do notation

Nếu cùng một khái niệm có nhiều cách viết hoặc block không nhất quán, người dùng phải ghi nhớ quy tắc hình thức không cần thiết.

### 3.3. Độ khó do semantics ẩn

Default, implicit conversion, null behavior và side effect không rõ làm người dùng khó dự đoán kết quả.

### 3.4. Giảm tải nhận thức

Dùng tên rõ ràng, cấu trúc block nhất quán, ví dụ có input/output, diagnostics cụ thể và editor completion để người dùng tập trung vào bài toán.

## 4. Nhất quán và khả năng dự đoán

Consistency giúp người dùng áp dụng kiến thức đã học ở một nơi sang nơi khác.

- Dùng cùng quy tắc đặt tên cho type, field và constant.
- Dùng cấu trúc block tương tự cho các khai báo cùng loại.
- Giữ error format thống nhất.
- Giữ semantics của default nhất quán.
- Quy định rõ evaluation order và short-circuit.

Nhất quán không có nghĩa mọi thứ phải giống hệt nhau. Một operation ghi dữ liệu có thể cần syntax khác operation đọc để thể hiện side effect. Sự khác biệt cần có lý do và phải dễ giải thích.

## 5. Tường minh và ngắn gọn

Ví dụ khai báo retry chỉ bằng một con số có thể ngắn nhưng mơ hồ: con số đó là tổng số attempts hay số lần retry sau lần đầu?

~~~text
retry = 3
~~~

Một dạng tường minh hơn:

~~~text
retry {
    maxAttempts = 4
    backoff = exponential
}
~~~

Cú pháp ngắn hữu ích khi ý nghĩa rõ, thao tác phổ biến và không có nhiều cách hiểu. Tường minh cần thiết khi có side effect, security implication, đơn vị đo, transaction, conversion mất thông tin hoặc default ảnh hưởng tính đúng.

Ít ký tự không đồng nghĩa ít kiến thức. Người dùng vẫn cần hiểu semantics của shorthand.

## 6. Progressive disclosure

Progressive disclosure trình bày tính năng theo từng lớp. Người mới học phần cần thiết trước; người dùng nâng cao có thể tìm hiểu thêm khi có nhu cầu.

~~~text
Cơ bản
  - Literal và field
  - Condition
  - Operation phổ biến

Trung cấp
  - Function
  - Collection
  - Reusable rule
  - Error handling

Nâng cao
  - Generic type
  - Extension
  - Concurrency
  - Optimization
  - Runtime policy
~~~

Quick start nên giới thiệu core syntax và một tác vụ nhỏ. Advanced reference vẫn phải có đường khám phá rõ. Progressive disclosure không được che giấu semantics quan trọng như side effect, permission, transaction hoặc default.

## 7. Type system và học tập

Dynamic typing có thể giúp bắt đầu nhanh nhưng một số lỗi chỉ xuất hiện lúc chạy. Static typing phát hiện nhiều lỗi sớm hơn nhưng có thể yêu cầu người dùng hiểu type inference, generic, overload và conversion.

Type inference giảm annotation:

~~~text
let total = price * quantity
~~~

Nhưng compiler và editor cần giải thích kiểu đã suy luận. Domain type như Money, CustomerId và Duration có thể cần học thêm, song giúp ngăn nhầm lẫn giữa các giá trị cùng representation.

Diagnostic tốt cần nêu expression sai, kiểu thực tế, kiểu mong đợi, nguyên nhân và cách sửa an toàn.

## 8. Default và implicit behavior

Default tốt phù hợp phần lớn use case, an toàn, nhất quán và có thể override. Default nguy hiểm cần được thể hiện rõ. Ví dụ, tự retry thao tác thanh toán mà không có idempotency có thể tạo giao dịch trùng.

Implicit conversion tiện nhưng có thể gây mất precision hoặc phụ thuộc locale. Implicit scope có thể khiến identifier tham chiếu đến object khác nhau tùy context. Chỉ nên dùng implicit behavior khi không gây bất ngờ.

## 9. Abstraction và mô hình tư duy

Abstraction quá thấp buộc người dùng viết transport, serialization, retry loop và resource management. Abstraction quá cao có thể che giấu behavior đến mức khó kiểm soát và debug.

Abstraction tốt có tên gần với miền, input/output rõ, failure behavior được mô tả, có thể kết hợp và không che giấu quyết định quan trọng.

Ví dụ:

~~~text
step reserveInventory {
    call inventory.reserve(order.items)
}
~~~

Người dùng tập trung vào ý nghĩa giữ hàng; runtime quản lý connection và serialization. Khi debug, trace hoặc expanded view nên cho biết các bước thực tế đã xảy ra.

## 10. Từ vựng và discoverability

Dùng domain vocabulary quen thuộc. Danh từ như Customer, Order, Invoice biểu diễn resource; động từ như reserve, approve, refund biểu diễn operation.

Tránh viết tắt hiếm gặp và tên quá chung. Editor completion, hover documentation, go-to-definition và suggested fix giúp người dùng khám phá cú pháp mà không cần ghi nhớ mọi chi tiết.

## 11. Diagnostics và error recovery

Một thông báo lỗi hữu ích chỉ rõ vị trí, cấu trúc mong đợi, giá trị thực tế và gợi ý sửa.

~~~text
Expected: Duration
Found: Integer
Location: service.timeout
Hint: Use an explicit unit, such as 5 seconds.
~~~

Parser nên ưu tiên lỗi gốc và tránh tạo nhiều lỗi dây chuyền. Suggested fix có thể tự áp dụng với lỗi an toàn, nhưng thay đổi semantics cần người dùng review.

## 12. Tài liệu và ví dụ

Cú pháp tốt vẫn khó học nếu tài liệu kém. Một bộ tài liệu nên có:

- Quick start để chạy ví dụ đầu tiên.
- Tutorial theo một tác vụ hoàn chỉnh.
- Concept guide giải thích mô hình tư duy.
- Reference liệt kê syntax, type, parameter, default và error.
- Ví dụ tối thiểu cho từng khái niệm.
- Ví dụ thực tế cho cách kết hợp.
- Anti-pattern và cách sửa.
- Tài liệu riêng cho từng version.

Ví dụ cần nêu input, output và giải thích tại sao kết quả như vậy. Chỉ đưa source mà không có expected result làm giảm khả năng tự kiểm tra.

## 13. Tooling hỗ trợ học

Tooling có thể giảm learning curve mà không thay đổi semantics:

- Syntax highlighting làm nổi bật cấu trúc.
- Formatter chuẩn hóa style.
- Linter cảnh báo pattern nguy hiểm.
- Language server gợi ý type, field và operation.
- Playground cho phép thử ví dụ nhỏ.
- Debugger hỗ trợ breakpoint và inspect state.
- Trace viewer cho thấy workflow thực thi.
- Generated code viewer giúp người dùng nâng cao hiểu cách compiler hoạt động.

## 14. Onboarding theo persona

| Persona | Kiến thức sẵn có | Nhu cầu | Hỗ trợ |
|---|---|---|---|
| Domain expert | Nghiệp vụ sâu, code ít | Viết rule/policy | Từ vựng miền, template |
| Developer | Biết lập trình | Tích hợp và mở rộng | Type, API reference, debugger |
| Analyst | Dữ liệu và báo cáo | Query/aggregate | Schema discovery, preview |
| Operator | Vận hành hệ thống | Cấu hình, xử lý lỗi | Validation, safe defaults, audit |
| Maintainer | Hiểu runtime | Evolution và compatibility | IR, migration, profiling |

Có thể dùng cùng semantic core nhưng cung cấp tài liệu, editor experience và capability phù hợp vai trò. Tránh tạo nhiều dialect nếu không có lý do.

## 15. Đo lường learning curve

Đo lường cần dựa trên tác vụ đại diện, không chỉ hỏi người dùng có thích cú pháp hay không.

- Time-to-task: thời gian chạy ví dụ, viết rule, tạo query, sửa lỗi.
- Error rate: số lỗi syntax, type và logic.
- Completion rate: tỷ lệ hoàn thành không cần trợ giúp.
- Help-seeking rate: số lần mở tài liệu hoặc hỏi chuyên gia.
- Retention: khả năng sử dụng lại sau một thời gian ngắt quãng.
- Transfer: khả năng áp dụng kiến thức vào use case mới.
- Maintenance comprehension: thời gian hiểu và thay đổi source của người khác.

Không nên xem mọi lần tra cứu reference là thất bại. Điều quan trọng là người dùng có tìm được thông tin và tiếp tục công việc hay không.

## 16. Usability study

Một study có thể:
1. Chọn người tham gia đại diện cho persona.
2. Giao tác vụ thực tế như viết rule, sửa query hoặc debug workflow.
3. Quan sát mà không hướng dẫn quá sớm.
4. Ghi thời gian, số lỗi, số lần chạy và lần tra cứu.
5. Phỏng vấn về điểm gây nhầm lẫn.
6. Phân tích lỗi lặp lại.
7. Sửa syntax, docs hoặc tooling.
8. Thử lại với nhóm người dùng khác.

Nếu nhiều người hiểu cùng một cú pháp theo cùng một cách sai, có thể đó là vấn đề thiết kế chứ không chỉ là thiếu kiến thức.

## 17. Ví dụ: rule DSL theo từng cấp

Ví dụ cơ bản:

~~~text
rule "adult_customer" {
    when customer.age >= 18
    then customer.category = ADULT
}
~~~

Sau khi hiểu rule, người dùng học reusable predicate:

~~~text
predicate isAdult(customer) {
    customer.age >= 18
}
~~~

Sau đó mới học missing value và routing:

~~~text
rule "unknown_age" {
    when customer.age is missing
    then routeToReview(customer)
}
~~~

Tách các ví dụ giúp người học xây dựng mô hình từng bước. Tuy nhiên, tài liệu phải giải thích rõ action routeToReview thay đổi state hoặc chuyển dữ liệu đi đâu.

## 18. Ví dụ: cú pháp ngắn và tường minh

Dạng ngắn:

~~~text
call payment.authorize(order)
~~~

Dạng tường minh:

~~~text
call payment.authorize(order) {
    timeout = 5 seconds
    idempotencyKey = order.confirmationKey
    onTimeout = queryStatus
}
~~~

Dạng ngắn phù hợp khi policy mặc định an toàn và đã được công bố. Dạng tường minh cần thiết với thanh toán vì timeout có thể tạo unknown outcome và idempotency ảnh hưởng tính đúng.

Có thể dùng policy reusable ở cấp project, nhưng IDE hoặc expanded view nên cho biết behavior thực tế của operation.

## 19. Learning curve và evolution

Mỗi feature mới làm tăng chi phí học, tài liệu, tooling và tương tác với feature cũ.

- Đánh giá use case thực tế trước khi thêm syntax.
- Ưu tiên library nếu không cần grammar mới.
- Dùng deprecation warning trước khi loại bỏ feature.
- Cung cấp migration guide và codemod.
- Giữ core semantics ổn định.
- Version hóa tài liệu.
- Đo tác động với người dùng hiện tại.

Một breaking change cần giải thích behavior trước/sau, không chỉ liệt kê cú pháp đã đổi.

## 20. Những lỗi thiết kế làm learning curve dốc hơn

1. Quá nhiều cách viết cho cùng một việc.
2. Default không nhất quán giữa các context.
3. Error message mơ hồ hoặc thiếu vị trí.
4. Ví dụ đầu tiên chứa quá nhiều abstraction.
5. Keyword thay đổi semantics theo context ngầm.
6. Implicit side effect.
7. Tài liệu chỉ mô tả syntax mà bỏ qua behavior.
8. Thiếu editor support.
9. Không có lộ trình từ cơ bản đến nâng cao.
10. Breaking change không có migration support.

## 21. Quy trình thiết kế hướng tới learning curve tốt

1. Xác định persona và tác vụ phổ biến.
2. Đánh giá kiến thức sẵn có của người dùng.
3. Xác định mô hình tư duy trung tâm.
4. Chọn semantic core và domain vocabulary.
5. Thiết kế grammar nhất quán.
6. Làm rõ type, default và side effect.
7. Tách core khỏi advanced feature.
8. Viết quick start và ví dụ theo cấp độ.
9. Xây diagnostics, formatter và editor completion.
10. Thử nghiệm với người dùng đại diện.
11. Đo time-to-task, error rate và mức tự chủ.
12. Phân tích lỗi lặp lại để tìm vấn đề thiết kế.
13. Cải thiện syntax, docs hoặc tooling dựa trên bằng chứng.
14. Theo dõi tác động khi phát hành version mới.

## 22. Bảng đánh giá

| Tiêu chí | Câu hỏi | Dấu hiệu tốt |
|---|---|---|
| First success | Người mới chạy được ví dụ trong bao lâu? | Tự làm theo quick start |
| Concept clarity | Có giải thích được semantic core không? | Dùng đúng thuật ngữ |
| Syntax predictability | Có đoán được cách viết tiếp không? | Ít thử sai |
| Error recovery | Có tự sửa được không? | Diagnostic hữu ích |
| Transfer | Có làm được use case mới không? | Không chỉ copy ví dụ |
| Maintenance | Có hiểu source người khác không? | Xác định behavior và side effect |
| Retention | Có dùng lại sau thời gian nghỉ không? | Ít phải học lại |
| Advanced path | Có tìm được feature nâng cao không? | Reference và tooling rõ |

Không nên gộp tất cả thành một điểm số nếu chúng phản ánh vấn đề khác nhau. First success tốt nhưng maintenance comprehension kém có thể cho thấy DSL dễ bắt đầu nhưng khó bảo trì.

## 23. Bài tập tự kiểm tra

### Bài 1: So sánh cú pháp

So sánh khai báo retry bằng một số với block có maxAttempts và backoff. Nêu persona và use case phù hợp.

### Bài 2: Cognitive load

Chọn một DSL. Xác định phần độ khó vốn có của miền và phần do notation hoặc tooling.

### Bài 3: Progressive disclosure

Thiết kế ba cấp độ cho query DSL: cơ bản, trung cấp và nâng cao.

### Bài 4: Default

Chọn default timeout và retry cho integration call. Chỉ ra thông tin phải tường minh và giải thích lý do.

### Bài 5: Diagnostic

Viết lỗi khi field cần Duration nhưng người dùng truyền Integer. Bao gồm vị trí, kiểu thực tế, kiểu mong đợi và gợi ý.

### Bài 6: Usability study

Thiết kế study so sánh hai cách viết cùng một rule. Chọn participant, task, metric và cách giảm bias.

### Bài 7: Maintenance

Đưa workflow có branch, retry và side effect cho người mới. Xác định câu hỏi để đánh giá khả năng hiểu source.

### Bài 8: Feature growth

Đánh giá đề xuất thêm macro, generic type và arbitrary host function vào rule DSL.

### Bài 9: Version evolution

Một version đổi default timeout và loại bỏ keyword cũ. Thiết kế deprecation window và migration support.

### Bài 10: Review

Quan sát người dùng hoàn thành một tác vụ DSL, ghi điểm dừng, lỗi, lần tra cứu và phản hồi.

## Kết luận

Đường cong học tập là một phần của chất lượng thiết kế DSL, vì nó quyết định người dùng cần bao nhiêu thời gian để bắt đầu, làm việc độc lập và bảo trì chương trình. Một DSL dễ học không nhất thiết là DSL có ít ký tự nhất; tính nhất quán, semantics dễ dự đoán, abstraction đúng mức, diagnostics hữu ích và tài liệu theo cấp độ thường quan trọng hơn shorthand. Thiết kế cần cân bằng nhu cầu của người mới với khả năng biểu đạt và kiểm soát của người dùng nâng cao, đồng thời phân biệt độ khó vốn có của miền với độ khó do notation hoặc tooling gây ra. Progressive disclosure, default an toàn, editor support và ví dụ có giải thích giúp giảm tải nhận thức mà vẫn giữ được khả năng mở rộng. Usability study và các phép đo như time-to-task, error rate, transfer và maintenance comprehension cung cấp bằng chứng để cải thiện ngôn ngữ. Khi learning curve được xem xét trong toàn bộ vòng đời DSL, từ onboarding đến version migration, ngôn ngữ sẽ dễ tiếp cận hơn mà vẫn đủ mạnh cho công việc thực tế.
