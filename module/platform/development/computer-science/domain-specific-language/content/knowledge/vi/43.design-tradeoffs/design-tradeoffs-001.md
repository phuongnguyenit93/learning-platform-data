# Tính dễ đọc

Khi thiết kế một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), người thiết kế thường phải cân bằng nhiều mục tiêu: biểu đạt đúng nghiệp vụ, dễ viết, dễ học, dễ phân tích, dễ tối ưu, an toàn và dễ bảo trì. Một cú pháp ngắn có thể giúp tác giả viết nhanh nhưng khiến người đọc phải suy luận nhiều. Một cú pháp tường minh có thể dài hơn nhưng làm rõ điều kiện, tác động và thứ tự thực thi. Vì vậy, **tính dễ đọc** (*readability*) là một đánh đổi thiết kế quan trọng, không phải một thuộc tính tự động xuất hiện khi DSL có ít từ khóa hoặc ít dòng code.

Tính dễ đọc là mức độ mà người đọc có thể nhanh chóng hiểu cấu trúc, ý nghĩa, luồng điều khiển, dữ liệu và tác động của một chương trình. Nó phụ thuộc vào cú pháp, naming, formatting, abstraction, diagnostics, documentation, convention và kiến thức của nhóm người sử dụng. Với DSL, người đọc có thể là developer, analyst nghiệp vụ, operator, reviewer hoặc người quản trị; mỗi nhóm có mục tiêu và vốn từ khác nhau.

Ví dụ hai cách mô tả cùng một quy tắc:

~~~text
when c.a >= 18 && c.s && !c.b then p(c.id);
~~~

~~~text
rule ApproveEligibleCustomer {
    when customer.age >= 18
         and customer.isActive
         and not customer.isBlocked;

    then approve(customer.id);
}
~~~

Cách đầu ngắn hơn, nhưng người đọc phải biết c, a, s, b và p đại diện cho gì. Cách thứ hai dài hơn nhưng tên miền nghiệp vụ và cấu trúc rule rõ hơn. Tuy nhiên, nếu một DSL yêu cầu lặp lại quá nhiều boilerplate hoặc dùng từ ngữ dài không cần thiết, nó cũng làm giảm khả năng đọc. Mục tiêu là giảm nỗ lực nhận thức để hiểu đúng chương trình, không phải tối đa hóa độ dài hoặc độ ngắn.

## 1. Tính dễ đọc là gì?

Tính dễ đọc mô tả mức độ dễ hiểu của source code đối với người đọc dự kiến. Nó khác với việc code có chạy đúng hay không. Một chương trình có thể đúng về semantics nhưng rất khó hiểu; ngược lại, code trông rõ ràng vẫn có thể chứa logic sai.

Một chương trình dễ đọc thường giúp người đọc trả lời nhanh:
- Đoạn này đang mô tả nghiệp vụ hoặc hành động nào?
- Dữ liệu nào được sử dụng và đến từ đâu?
- Điều kiện nào khiến một nhánh được thực hiện?
- Bước nào xảy ra trước/sau?
- Có side effect hoặc external call nào?
- Khi nào chương trình hoàn tất, thất bại hoặc chờ?
- Thay đổi một phần có ảnh hưởng đến phần nào khác?

### Readability và correctness

Correctness xác định chương trình có tuân thủ semantics/specification hay không. Readability giúp con người nhận ra và duy trì correctness. Hai yếu tố hỗ trợ nhau nhưng không thay thế nhau.

### Readability và writability

Writability là mức độ dễ viết chương trình. Syntax ngắn, autocomplete tốt và API fluent có thể tăng writability. Nhưng một biểu thức quá cô đọng có thể khó đọc với reviewer hoặc operator.

### Readability và learnability

Learnability là mức độ dễ học language. Một DSL có vocabulary gần nghiệp vụ có thể dễ tiếp cận với analyst, nhưng vẫn cần quy tắc cú pháp nhất quán và ví dụ để tránh người học phải đoán.

### Readability và maintainability

Maintainability là khả năng sửa đổi an toàn theo thời gian. Readability là một yếu tố lớn vì người sửa thường không phải tác giả ban đầu. Naming, module boundary, comment và diagnostics giúp giảm thời gian hiểu code.

### Readability và visual appearance

Code được format đẹp chưa chắc dễ hiểu. Căn lề, màu syntax và line break giúp scan, nhưng semantics, naming và abstraction mới quyết định người đọc có hiểu đúng không.

## 2. Vì sao readability là một design trade-off?

DSL phục vụ nhiều mục tiêu. Một lựa chọn làm cú pháp ngắn hơn có thể tăng ambiguity; một lựa chọn làm semantics tường minh hơn có thể tăng boilerplate.

### Concision và explicitness

Cú pháp ngắn giúp giảm lượng ký tự cần viết. Cú pháp tường minh giúp thể hiện rõ ý định. Cần chọn điểm cân bằng phù hợp với domain và người dùng.

### Flexibility và predictability

Một language quá linh hoạt có nhiều cách biểu đạt cùng ý tưởng, khiến reviewer khó nhận ra convention. Một language quá cứng có thể buộc người dùng viết workaround dài.

### Abstraction và transparency

Abstraction giúp che chi tiết lặp lại. Nhưng abstraction quá sâu có thể giấu luồng điều khiển, side effect hoặc nguồn dữ liệu.

### Familiarity và domain fit

Cú pháp giống Java/SQL/JSON có thể quen với developer. Từ khóa gần ngôn ngữ nghiệp vụ có thể phù hợp analyst. Không có lựa chọn đúng cho mọi audience.

### Power và cognitive load

Feature như macro, operator overloading, implicit conversion hoặc metaprogramming có thể tăng khả năng biểu đạt nhưng làm người đọc phải hiểu nhiều quy tắc ẩn.

### Local clarity và global consistency

Một biểu thức có thể rõ khi nhìn riêng nhưng dùng convention khác phần còn lại của language. Consistency toàn DSL thường giúp người đọc học một lần rồi áp dụng ở nhiều nơi.

## 3. Người đọc là ai?

Readability không có một tiêu chuẩn duy nhất cho mọi người. Cần xác định audience trước khi chọn cú pháp và vocabulary.

| Người đọc | Câu hỏi chính | Thiết kế nên ưu tiên |
|---|---|---|
| Developer | Cấu trúc, type, control flow và API là gì? | Consistency, tooling, diagnostics, abstraction. |
| Business analyst | Quy tắc nghiệp vụ có đúng ý định không? | Domain vocabulary, câu điều kiện rõ, ít chi tiết kỹ thuật. |
| Operator | Process đang làm gì, chờ gì, tác động ra sao? | State, side effect, retry, timeout và trace rõ. |
| Reviewer | Thay đổi này ảnh hưởng điều kiện nào? | Diff dễ đọc, naming, scope và explicit behavior. |
| Platform engineer | Dependency và runtime capability nào được dùng? | Import, version, permission và execution model. |
| Auditor | Ai quyết định điều gì, theo policy nào? | Provenance, rule identity, version và explanation. |

### Một DSL có nhiều audience

Một language có thể có syntax authoring dành cho developer, form builder cho analyst và visualization cho operator. Không nhất thiết buộc mọi người đọc cùng một representation. Tuy nhiên, các view cần có mapping rõ về cùng một source/model để tránh diễn giải khác nhau.

### Vocabulary của domain

Từ ngữ nghiệp vụ cần được xác nhận với domain owner. Một tên có vẻ tự nhiên với developer có thể mang nghĩa khác trong ngành. Glossary và examples giúp thống nhất.

### Tránh tối ưu cho tác giả duy nhất

DSL thường tồn tại lâu hơn người viết ban đầu. Naming và convention nên giúp người mới vào dự án hiểu mà không cần hỏi tác giả mọi dòng.

## 4. Cú pháp tường minh và cú pháp cô đọng

Cú pháp tường minh thường bộc lộ cấu trúc; cú pháp cô đọng giảm boilerplate. Mỗi kiểu có giá trị riêng.

### Tường minh

~~~text
rule HighValueOrder {
    when order.total >= 1000
         and order.currency == "USD";

    then requireManagerApproval(order.id);
}
~~~

Người đọc nhìn thấy tên rule, condition và action. Cấu trúc phù hợp cho business rule cần review hoặc audit.

### Cô đọng

~~~text
HighValueOrder := total >= 1000 USD && managerApproval
~~~

Biểu thức ngắn và có thể dễ đọc nếu người dùng quen DSL. Nhưng cần biết managerApproval là boolean, action hay shorthand cho một policy; đơn vị USD được hiểu như thế nào; điều kiện có side effect không.

### Khi nào nên chọn explicit syntax?

- Khi rule có tác động tài chính, bảo mật hoặc pháp lý.
- Khi điều kiện gồm nhiều predicate.
- Khi evaluation order hoặc side effect quan trọng.
- Khi người đọc không chuyên về programming.
- Khi source cần được audit hoặc giải thích.

### Khi nào concise syntax phù hợp?

- Biểu thức nhỏ và có convention rõ.
- Người dùng chuyên môn đã quen language.
- Syntax có semantics đơn giản, không có side effect ẩn.
- Boilerplate lặp lại đã được chuẩn hóa.
- Tooling cung cấp hover, completion và formatted view.

### Không đánh đồng ngắn với dễ đọc

Một dòng có thể chứa nhiều phép biến đổi và nested conditional, trong khi nhiều dòng có thể thể hiện cùng logic theo từng bước. Độ dài chỉ là một tín hiệu yếu; cognitive complexity và semantics mới quan trọng.

## 5. Naming và domain vocabulary

Tên là một trong những yếu tố có tác động lớn nhất đến khả năng hiểu code.

### Tên thể hiện ý nghĩa

So sánh:

~~~text
if x > 0 and y == 1 then z();
~~~

với:

~~~text
if invoice.balance > 0
   and customer.accountStatus == ACTIVE
then notifyCollections(invoice.id);
~~~

Tên tốt giúp người đọc hiểu vai trò của dữ liệu và hành động mà không phải lần theo định nghĩa ở nơi khác.

### Consistent naming

Nếu một khái niệm được gọi là customer ở nơi này, client ở nơi khác và accountHolder ở nơi thứ ba, người đọc phải tự xác định chúng có cùng nghĩa hay không. Domain glossary giúp thống nhất.

### Verb và noun

Nên dùng noun cho entity/value và verb cho action/operation. Ví dụ customer, invoice, eligibility; approve, reserve, dispatch. Naming convention nên nhất quán.

### Tránh abbreviation không phổ biến

Abbreviation có thể tiết kiệm không gian nhưng tạo chi phí giải mã. Chỉ dùng viết tắt đã phổ biến trong domain hoặc được định nghĩa trong glossary.

### Tránh tên quá chung

Tên như data, value, result hoặc process có thể phù hợp trong scope nhỏ, nhưng thiếu ý nghĩa khi xuất hiện trong DSL lớn.

### Boolean naming

Tên predicate nên gợi câu hỏi yes/no như isActive, hasPermission hoặc canShip. Điều này giúp condition đọc tự nhiên.

### Action naming

Tên action nên thể hiện side effect: sendInvoice, reserveInventory, cancelSubscription. Một function tên calculate có thể thuần; một action tên process có thể quá mơ hồ.

### Naming collision

DSL cần namespace, qualification hoặc import alias để tên rõ nguồn gốc. Không nên để cùng tên function từ nhiều extension được chọn ngẫu nhiên.

## 6. Grammar nhất quán

Grammar là hệ thống quy tắc định hình cách người dùng đọc và dự đoán cú pháp.

### Một ý tưởng, một pattern chính

Nếu cùng một loại declaration có ba cách viết không cần thiết, người đọc phải nhớ nhiều convention. Cho phép variation khi nó có giá trị rõ, không chỉ vì parser có thể hỗ trợ.

### Keyword nhất quán

Nếu language dùng when/then cho rule, không nên dùng if/do cho cấu trúc tương tự mà không có khác biệt semantics rõ ràng.

### Delimiter và block

Brace, indentation hoặc keyword block đều có thể dùng. Quan trọng là cách mở/đóng scope nhất quán và parser/formatter hiển thị rõ.

### Operator precedence

Precedence phải dễ dự đoán và được tài liệu hóa. Với biểu thức dài hoặc operator ít quen, ngoặc tường minh có thể tăng readability dù parser không bắt buộc.

### Associativity

Các chain như a - b - c hoặc a ?? b ?? c cần quy tắc rõ. Nếu người đọc phải nhớ quy tắc đặc biệt cho từng operator, nên cân nhắc cú pháp hoặc formatting hỗ trợ.

### Contextual keyword

Contextual keyword giúp giữ identifier cũ hợp lệ, nhưng cần giải thích khi nào token là keyword và khi nào là identifier.

### Grammar extension

Plugin thêm syntax có thể làm người đọc khó dự đoán grammar. Cần namespace, import hoặc explicit activation để syntax mở rộng không xuất hiện ngoài ý muốn.

## 7. Precedence, grouping và expression readability

Expression là nơi readability dễ suy giảm khi nhiều operator được ghép trong một dòng.

Ví dụ:

~~~text
eligible = active && age >= 18 || premium && !blocked
~~~

Người đọc phải nhớ precedence giữa AND/OR và hiểu nhóm điều kiện.

Có thể viết:

~~~text
eligible =
    (active and age >= 18)
    or (premium and not blocked)
~~~

### Dùng ngoặc theo ý nghĩa

Ngoặc có thể không cần cho parser nhưng giúp người đọc thấy nhóm logic. Không nên thêm ngoặc dư thừa đến mức che cấu trúc chính.

### Tách predicate có tên

~~~text
isAdult = customer.age >= 18;
isInGoodStanding = customer.accountStatus == ACTIVE;
isEligible = isAdult and isInGoodStanding;
~~~

Cách này hữu ích khi predicate có ý nghĩa nghiệp vụ hoặc được dùng lại. Không nên tạo biến trung gian cho mọi biểu thức nhỏ vì có thể làm flow bị vụn.

### Tránh nested ternary

Nhiều conditional lồng nhau khó scan. Có thể dùng match/switch, if/else hoặc rule table để thể hiện mapping.

### Short-circuit và side effect

Nếu AND/OR có short-circuit, documentation cần nêu rõ. Không đặt side-effect function ở vế phải rồi kỳ vọng người đọc tự đoán lúc nào nó chạy.

### Unit và literal

Giá trị 30 có thể là seconds, minutes hoặc count. Literal có unit như 30 seconds dễ đọc hơn số trần.

## 8. Control flow dễ theo dõi

Người đọc cần hiểu đường đi của chương trình.

### Sequential flow

Các bước tuần tự nên được thể hiện theo thứ tự thực thi. Tránh implicit ordering dựa trên thứ tự file nếu điều đó không rõ trong language.

### Branch

Điều kiện branch nên có tên hoặc comment khi nghiệp vụ phức tạp. Tránh nhiều nested if không có cấu trúc.

### Parallelism

Parallel block cần cho biết các nhánh chạy đồng thời và điều kiện join. Từ parallel hoặc fork/join rõ hơn một ký hiệu ngắn không phổ biến.

### Loop

Loop cần thể hiện nguồn collection, iteration variable và điều kiện dừng. Với loop có side effect, nên dễ nhận ra số lần lặp và phạm vi.

### Early exit

Return, break, continue hoặc terminate cần semantics nhất quán. Các lệnh kết thúc sớm nên dễ nhận ra khi đọc block.

### Exception/error flow

Error handler, retry và compensation nên được phân biệt với success path. Không giấu retry trong một annotation khó thấy nếu nó ảnh hưởng thời gian và side effect.

### Async/wait

Một workflow có thể chờ event, timer hoặc human input. Syntax nên thể hiện rõ điểm suspend/resume và dữ liệu được giữ qua thời gian.

## 9. Abstraction: giảm lặp nhưng không che logic

Abstraction giúp người đọc tập trung vào mục tiêu thay vì chi tiết lặp lại. Nhưng abstraction không tốt có thể biến logic thành hộp đen.

### Reusable function

Một function có tên tốt đóng gói logic có ý nghĩa và có contract rõ. Ví dụ validateCustomerEligibility dễ hiểu hơn một đoạn condition dài được copy nhiều nơi.

### Subprocess/module

Subprocess phù hợp khi một phần flow có lifecycle hoặc trách nhiệm riêng. Không nên tách một block vài dòng nếu người đọc phải nhảy qua nhiều file chỉ để hiểu một thao tác đơn giản.

### Domain concept

Một abstraction tốt biểu diễn khái niệm có thật trong domain: risk assessment, credit check, shipment reservation. Một abstraction chỉ đổi tên cú pháp có thể không giảm cognitive load.

### Hidden side effect

Function call trông như phép tính thuần nhưng lại ghi database hoặc gửi message là nguồn gây hiểu nhầm. Naming, type metadata hoặc effect annotation cần thể hiện side effect.

### Abstraction depth

Nếu để hiểu một rule phải mở qua nhiều lớp helper, macro và plugin, người đọc mất context. Cần giữ abstraction depth vừa đủ và cung cấp navigation/tooling.

### Avoid generic indirection

Một function tên executeStep(handler, payload, config) có thể che hành vi thực. API chuyên biệt theo domain thường rõ hơn khi semantics khác nhau.

## 10. Explicitness và implicit behavior

Implicit behavior giảm cú pháp nhưng yêu cầu người đọc biết nhiều quy tắc ngầm.

### Implicit conversion

Tự động đổi String thành Date hoặc Integer có thể tiện, nhưng có thể tạo lỗi locale/format hoặc precision. Conversion quan trọng nên explicit.

### Default value

Default có thể giảm boilerplate. Nhưng nếu default ảnh hưởng business outcome, cần hiển thị trong documentation, editor hover hoặc generated explanation.

### Implicit import

Tự động import mọi function trong package giúp viết ngắn nhưng làm namespace không rõ và dễ collision. Explicit import có thể tăng readability.

### Implicit transaction

Một block có thể tự mở transaction. Cần biết transaction boundary, commit/rollback và side effect ngoài transaction.

### Implicit retry

Retry annotation có thể làm task chạy nhiều lần. Nên khai báo retry policy và idempotency expectation rõ ràng.

### Implicit ordering

Nếu rule hoặc declaration order ảnh hưởng kết quả, language cần làm rõ. Tốt hơn là dùng priority/order property có tên.

### Convention over configuration

Convention có thể tăng readability khi phổ biến và nhất quán. Khi convention có ngoại lệ, cần cách hiển thị hoặc override tường minh.

## 11. Type system và readability

Type có thể truyền đạt ý nghĩa dữ liệu và giới hạn operation.

### Domain type

Money, EmailAddress, CustomerId và Duration diễn tả semantics rõ hơn String hoặc Number chung.

### Unit-aware type

Một field timeout kiểu Duration rõ hơn Integer không ghi unit. Type system có thể ngăn cộng milliseconds với bytes hoặc currency khác nhau.

### Nullability

Phân biệt optional, nullable và required giúp người đọc hiểu dữ liệu có thể vắng mặt hay không. Không nên để null semantics phụ thuộc vào convention ngầm.

### Sum type và enum

Một enum như PaymentStatus thể hiện tập trạng thái. Discriminated union thể hiện các biến thể dữ liệu và giúp pattern matching rõ.

### Generic type

Generic giúp reuse nhưng cú pháp quá phức tạp có thể làm DSL khó đọc với audience không chuyên. Có thể cung cấp alias/domain type để che type expression dài.

### Type inference

Inference giảm annotation nhưng quá nhiều implicit type có thể khiến người đọc phải suy ra kiểu từ xa. Có thể hiển thị type trong editor và yêu cầu annotation ở boundary quan trọng.

### Effect type/metadata

Nếu function có network, database hoặc nondeterminism, metadata về effect giúp reviewer hiểu tác động.

## 12. Naming và tổ chức module

Cấu trúc file/module ảnh hưởng cách người đọc tìm thông tin.

### Cohesion

Một module nên nhóm các khái niệm liên quan. Đặt rule thanh toán và rule giao hàng trong cùng file chỉ vì chúng cùng workflow có thể làm module lớn và khó điều hướng.

### Bounded context

Tên module nên phản ánh domain boundary. Tránh một thư mục common chứa mọi thứ không biết đặt ở đâu.

### File size và navigation

File quá lớn làm người đọc mất overview; file quá nhỏ làm context phân tán. Tổ chức theo domain, capability hoặc lifecycle phù hợp hơn áp một ngưỡng dòng cứng.

### Import rõ ràng

Import nên cho biết source của symbol. Alias hữu ích khi tên trùng nhưng alias cần có ý nghĩa.

### Public/private surface

Phân biệt declaration public và internal giúp người đọc biết contract nào được dùng bên ngoài.

### Module graph

Dependency nên một chiều hoặc có quy tắc rõ. Circular import làm khó hiểu ownership và build order.

## 13. Formatting và visual structure

Formatting giúp mắt người đọc nhận ra cấu trúc nhanh.

### Consistent indentation

Block cùng cấp nên dùng cùng indentation. Formatter tự động giảm tranh luận về style và tránh diff chỉ do spacing.

### Line length

Line quá dài làm người đọc phải cuộn ngang hoặc khó scan. Có thể đặt line width guideline, nhưng không ngắt literal/identifier theo cách làm sai semantics.

### Blank lines

Blank line nên phân tách nhóm logic, không phải chèn ngẫu nhiên sau mọi statement.

### Alignment

Căn lề bảng/argument có thể giúp scan, nhưng không nên tạo format mong manh khiến một thay đổi nhỏ làm diff lớn.

### Table syntax

Rule table hoặc mapping table có thể dễ đọc hơn nhiều if/else. Column name và cell value cần rõ semantics.

### Comment placement

Comment nên gắn với đoạn code liên quan và giải thích lý do/constraint, không lặp lại điều source đã nói.

### Formatter as language tool

Một formatter chuẩn giúp codebase nhất quán. Nếu nhiều formatter tạo output khác nhau, readability và diff review giảm.

## 14. Comments, documentation và examples

Comment và docs bổ sung thông tin không thể hiện trực tiếp trong syntax.

### Explain why, not merely what

Comment hữu ích giải thích lý do nghiệp vụ, constraint bên ngoài hoặc trade-off. Không cần viết “increment count” cạnh câu lệnh increment hiển nhiên.

### Keep comments current

Comment lỗi thời có thể nguy hiểm hơn không có comment. Một số metadata quan trọng nên được biểu diễn thành type/constraint có thể kiểm tra.

### DSL docstring

Declaration có thể có description, owner, example và deprecation note. IDE có thể hiển thị khi hover.

### Examples

Ví dụ nên bao gồm happy path, boundary và failure behavior. Ví dụ nhỏ giúp người mới học syntax nhanh hơn.

### Living documentation

Có thể lấy example từ source hoặc executable test để tránh docs lệch với behavior. Nhưng không nên dùng mọi comment trong code làm documentation public.

### Glossary

Domain vocabulary cần có glossary thống nhất để người đọc hiểu các khái niệm như eligible, active, settled hoặc overdue.

## 15. Diagnostics và error message cũng là readability

Readability không chỉ áp dụng cho source hợp lệ. Khi source lỗi, diagnostic là phần giao tiếp giữa language và tác giả.

### Error location

Diagnostic cần line/column hoặc source range chính xác. Người đọc phải biết lỗi nằm ở token/field nào.

### Stable error code

Error code cho phép IDE, CI và documentation liên kết tới hướng dẫn sửa. Message text có thể thay đổi hoặc dịch.

### Explain expected và actual

Ví dụ “Expected Decimal but found String at payment.amount” hữu ích hơn “Type error”.

### Suggestion

Parser/type checker có thể gợi ý sửa khi confidence cao, ví dụ thiếu semicolon hoặc import chưa khai báo. Không tự sửa semantics mơ hồ.

### Avoid cascaded errors

Một lỗi parse đầu có thể tạo nhiều lỗi downstream không liên quan. Error recovery nên hạn chế noise và ưu tiên root cause.

### Domain-aware diagnostics

Thông báo “customer is blocked by compliance policy” hữu ích hơn một exception kỹ thuật nếu người đọc là business analyst. Có thể có nhiều diagnostic view cho nhiều audience.

### Explain hidden behavior

Nếu một rule bị shadowed, skipped hoặc conflict-resolved, engine có thể giải thích vì sao nó không chạy. Điều này giúp người đọc hiểu runtime behavior.

## 16. Readability và tooling

Tooling tốt làm tăng khả năng hiểu mà không buộc mọi thông tin phải nằm trong source.

### Syntax highlighting

Highlight keyword, type, literal, function, comment và deprecated symbol giúp scan.

### Completion

Autocomplete hiển thị tên và documentation của symbol, giảm typo và giúp người viết khám phá API.

### Hover information

Hover có thể hiển thị type, source module, version, description, permission và side-effect classification.

### Go to definition

Đi đến declaration của function/type/variable giảm chi phí tìm kiếm.

### Find references

Cho biết nơi symbol được dùng, hỗ trợ hiểu blast radius.

### Rename refactoring

Rename symbol theo semantic reference tránh sửa text sai hoặc bỏ sót usage.

### Outline và graph view

Workflow/rule graph có thể giúp operator nhìn flow mà source text khó thể hiện. View phải liên kết với source node để người dùng quay lại code.

### Explain/trace view

Engine có thể trình bày rule nào match, condition nào false, branch nào chọn và action nào chạy. Đây là phần readability ở runtime.

## 17. Readability trong rule DSL

Rule DSL thường có condition và action, nên tên, thứ tự và conflict policy rất quan trọng.

### Rule name

Tên nên mô tả mục tiêu nghiệp vụ, ví dụ ApproveLowRiskApplication thay vì Rule17.

### Condition grouping

Các nhóm điều kiện có thể được đặt tên hoặc chia thành predicate rõ. Tránh một dòng chứa nhiều phép AND/OR lẫn lộn.

### Action transparency

Action cần cho biết side effect. Một rule có thể update status, publish event hoặc call external service; reviewer phải nhận ra.

### Priority và conflict resolution

Nếu nhiều rule match, cần hiển thị priority/hit policy rõ. Không để thứ tự file vô tình quyết định winner nếu đó không phải contract.

### Rule table

Decision table có thể dễ đọc hơn nhiều rule lặp lại khi logic là tổ hợp condition/output. Nhưng cột/row cần có tên và hit policy.

### Explanation

Rule engine nên hỗ trợ trace để giải thích match, non-match, suppressed hoặc fired rule. Điều này giúp audit và debugging.

## 18. Readability trong workflow/process DSL

Workflow DSL mô tả chuỗi và quan hệ task.

### Step names

Tên step nên mô tả công việc: ValidateOrder, ReserveInventory, CapturePayment. Tên như StepA hoặc ProcessData khó giải thích.

### Branch clarity

Condition và branch label nên phản ánh quyết định nghiệp vụ. Branch true/false có thể không đủ khi có nhiều lựa chọn.

### Parallel join

Nêu rõ join all, any hoặc quorum. Người đọc cần biết process tiếp tục khi điều kiện nào thỏa.

### Human task

Assignment, due date, escalation và completion condition nên hiển thị rõ.

### Retry/compensation

Retry policy và compensation ảnh hưởng side effect. Không giấu trong default khó nhìn.

### Wait state

Điểm chờ external event/timer cần thể hiện rõ để người đọc biết process có thể suspend trong bao lâu và điều gì resume nó.

### Subprocess

Subprocess nên có tên và contract rõ. Quá nhiều tầng nested process khiến người đọc phải mở nhiều file để hiểu một luồng.

## 19. Readability trong schema/API DSL

Schema/API DSL cần thể hiện data contract.

### Field names

Tên field cần domain meaning và unit. amount không đủ rõ nếu không biết gross/net/currency.

### Required/optional/null

Các marker nên dễ phân biệt. Default và computed field cũng cần hiển thị.

### Constraint

Constraint quan trọng nên được đặt gần field hoặc trong block dễ tìm. Cross-field constraint cần tên và description.

### Request/response direction

Field read-only/write-only cần được thể hiện rõ để người đọc không nhầm dữ liệu client được gửi.

### Version/deprecation

Field deprecated cần có replacement và removal plan. Tooling có thể highlight để tác giả thấy ngay.

### Example payload

Ví dụ JSON/request giúp người đọc hình dung dữ liệu thực tế. Không dùng example chứa secret/PII thật.

## 20. DSL readability và host language

Một DSL embedded trong Java có thể dùng fluent API, annotation hoặc builder; một external DSL có grammar riêng.

### Fluent API

~~~java
workflow("FulfillOrder")
    .step("ValidateOrder", this::validate)
    .step("ReserveInventory", this::reserve)
    .then("CapturePayment", this::capture);
~~~

Fluent API quen với Java developer nhưng có thể bị hạn chế bởi type inference, lambda nesting và compiler diagnostics.

### External DSL

~~~text
workflow FulfillOrder {
    step ValidateOrder;
    step ReserveInventory;
    step CapturePayment;
}
~~~

External DSL có thể gần domain hơn và dễ cho tooling chuyên biệt, nhưng cần parser, formatter, versioning và diagnostics riêng.

### Embedded DSL trade-off

Tận dụng type system và IDE host language nhưng cú pháp bị giới hạn bởi host language. Error message có thể phản ánh Java type inference thay vì domain terms.

### External DSL trade-off

Kiểm soát syntax/semantics tốt hơn nhưng phải xây toàn bộ toolchain. Readability cần được thiết kế và kiểm chứng với user.

### Interoperability

Một DSL có thể gọi Java API. Cần giới hạn surface và đặt tên theo domain thay vì expose class/method nội bộ của host.

### Avoid two mental models

Nếu DSL trông giống Java nhưng semantics khác Java, người đọc dễ áp dụng nhầm giả định. Nêu rõ khác biệt quan trọng như null, equality, truthiness và evaluation order.

## 21. Đo và đánh giá readability

Readability khó đo bằng một con số duy nhất. Có thể kết hợp quan sát định tính và chỉ số hỗ trợ.

### Comprehension task

Đưa một đoạn DSL cho người dùng đại diện và yêu cầu họ trả lời: rule làm gì, branch nào chạy, field nào bắt buộc, action nào có side effect. Đo thời gian và tỷ lệ trả lời đúng.

### Review time

Quan sát thời gian reviewer hiểu và approve thay đổi. Review lâu có thể do complexity, thiếu context hoặc tool, không chỉ do syntax.

### Defect rate

Theo dõi lỗi do hiểu nhầm condition, precedence, default hoặc hidden side effect. Cần phân loại nguyên nhân thay vì quy mọi bug cho readability.

### Cognitive complexity

Có thể dùng nesting depth, branch count, expression complexity và abstraction depth như tín hiệu. Chúng không phải thước đo tuyệt đối.

### Change task

Yêu cầu người mới thêm một rule hoặc sửa một field. Đo thời gian, số lần cần hỏi và số lỗi phát sinh.

### Think-aloud study

Quan sát người dùng giải thích source trong lúc đọc để tìm tên gây nhầm, convention khó hiểu và phần semantics bị ẩn.

### Persona coverage

Thực hiện đánh giá với developer, analyst và operator nếu DSL phục vụ nhiều nhóm.

### Không tối ưu chỉ số máy móc

Giảm line count hoặc số token không đồng nghĩa tăng readability. Metric chỉ giúp phát hiện vùng cần xem xét; đánh giá cuối cùng phải gắn với task thực tế.

## 22. Readability và performance

Một số lựa chọn dễ đọc có thể tạo runtime overhead; một số tối ưu hiệu năng có thể làm source khó hiểu.

### High-level construct

Loop, query hoặc rule table có thể dễ đọc nhưng engine cần compile/optimize thành plan hiệu quả.

### Explicit intermediate value

Tạo biến trung gian giúp hiểu từng bước nhưng có thể tạo nhiều object nếu runtime không optimize. Có thể dùng immutable IR hoặc compiler lowering để giữ readability mà vẫn tối ưu.

### Macro và code generation

Macro giảm lặp nhưng source sau expansion có thể khó debug. Tooling cần hiển thị expanded view và source mapping.

### Caching

Cache giúp performance nhưng thêm lifecycle/invalidations. Không nên để cache policy xuất hiện trong mọi rule nếu đó là runtime concern.

### Abstraction cost

Một abstraction quá generic có thể làm code khó đọc và runtime chậm. Đo performance rồi tối ưu hotspot cụ thể, giữ API high-level nếu compiler có thể lower tốt.

### Optimize for readers first, measure runtime

Với DSL business-facing, source thường là tài liệu vận hành. Tối ưu readability là ưu tiên hợp lý; performance nên được đo ở compiled/runtime layer trước khi làm syntax khó hiểu.

## 23. Readability, security và auditability

Code dễ đọc giúp reviewer nhận ra quyền và tác động, nhưng cần syntax làm rõ trust boundary.

### Side-effect markers

Function có thể khai báo effect như pure, read, write, network hoặc external. Editor hiển thị effect để người đọc biết operation có tác động ngoài không.

### Permission declaration

Một workflow gọi extension cần khai báo capability/permission. Không để quyền truy cập ẩn trong plugin implementation.

### Secret handling

Tên/metadata có thể đánh dấu secret field và redaction. Source không nên chứa credential trực tiếp.

### Audit explanation

Rule decision nên liên kết với rule version, input reference, reason code và action trace. Người audit cần biết tại sao outcome xảy ra.

### Explicit trust boundary

Call external service hoặc evaluate untrusted script nên được thể hiện bằng construct rõ. Người đọc cần nhận ra dữ liệu nào đi qua boundary.

### Avoid magic behavior

Một annotation nhỏ có thể kích hoạt network call, retry hoặc permission elevation. Nếu tác động lớn, syntax hoặc tooling phải làm nó dễ thấy.

## 24. Readability và version evolution

Cú pháp thay đổi có thể làm giảm khả năng đọc nếu không có migration.

### Naming evolution

Rename keyword/function cần có deprecation alias và tooling hỗ trợ refactor.

### Grammar consistency

Thêm syntax mới cần tuân theo pattern đã học. Nếu có lý do phá convention, documentation phải giải thích.

### Default changes

Default mới có thể làm code cũ mang nghĩa khác. Hiển thị effective default trong IDE/diagnostic hoặc yêu cầu explicit config với behavior quan trọng.

### Formatter migration

Formatter mới có thể đổi toàn bộ file và tạo diff lớn. Có thể cung cấp format version hoặc migration mode.

### Deprecation warning

Warning nên chỉ rõ replacement và version removal. Tránh warning chung chung khiến người dùng không biết cách sửa.

### Mixed language version

Project lớn có thể chứa module ở language version khác nhau. Tooling cần hiển thị version tại module boundary và tránh semantics mơ hồ khi import.

## 25. Quy trình cải thiện readability của một DSL

Một quy trình thiết kế/đánh giá có thể gồm:

1. **Xác định audience:** developer, analyst, operator, reviewer hay auditor.
2. **Chọn vocabulary:** thống nhất domain terms, naming và glossary.
3. **Định nghĩa syntax principles:** explicitness, concision, consistency và precedence.
4. **Thiết kế grammar:** một pattern chính cho mỗi construct và tránh ambiguity không cần thiết.
5. **Thiết kế type/effect model:** thể hiện data meaning, unit, nullability và side effect.
6. **Tổ chức module:** cohesion, import, visibility và dependency direction.
7. **Định nghĩa formatting:** indentation, line width, blank lines, table và comment convention.
8. **Xây diagnostics/tooling:** source location, completion, hover, navigation và explain trace.
9. **Tạo examples:** happy path, boundary, error và migration.
10. **Đánh giá với người dùng:** comprehension task, review task và change task.
11. **Theo dõi maintenance:** bug do misunderstanding, review time và support question.
12. **Cải tiến có kiểm soát:** giữ semantics/version contract và cung cấp migration khi cần.

## 26. Những lỗi thiết kế thường gặp

**Tối ưu số dòng thay vì khả năng hiểu.** Cú pháp quá cô đọng có thể làm người đọc giải mã nhiều ký hiệu. Đánh giá bằng task comprehension.

**Tên ngắn và mơ hồ.** Tên x, d, p hoặc processData làm mất domain meaning. Dùng tên phản ánh vai trò.

**Nhiều cách viết cho cùng một ý.** Người đọc phải nhớ nhiều pattern. Chuẩn hóa grammar và formatter.

**Ẩn side effect trong function trông thuần.** Reviewer không nhận ra network/write/action. Dùng effect metadata và naming rõ.

**Quá nhiều abstraction.** Logic bị phân tán qua helper/module/macro. Giữ abstraction gắn với domain concept và cung cấp navigation.

**Quá ít abstraction.** Logic lặp lại làm các bản copy lệch nhau. Tạo function/rule/subprocess có contract rõ khi có ý nghĩa dùng lại.

**Dựa vào implicit default quan trọng.** Người đọc không biết timeout, retry hoặc null behavior. Làm default có thể khám phá và pin khi cần.

**Precedence không quen thuộc.** Expression parse khác cách người đọc suy luận. Dùng precedence convention phổ biến hoặc yêu cầu ngoặc tường minh.

**Diagnostic chỉ mang tính kỹ thuật.** Người viết DSL không biết sửa ở đâu. Cung cấp domain-aware message và source span.

**Comment thay cho model.** Một comment dài giải thích invariant có thể nên trở thành type/constraint có thể kiểm tra.

**Formatting tùy từng tác giả.** Source khó scan và diff nhiễu. Có formatter chuẩn.

**Chỉ đánh giá với developer.** Analyst/operator có thể không hiểu vocabulary hoặc control flow. Test với audience thật.

**Tooling không theo kịp syntax.** Parser hiểu language nhưng editor không có completion/diagnostics. Readability trong thực tế giảm.

## 27. Checklist đánh giá tính dễ đọc

Khi review một DSL hoặc một definition, có thể xem xét:

- Người đọc mục tiêu đã được xác định chưa?
- Domain vocabulary có thống nhất và dễ hiểu không?
- Tên entity, field, function, rule và action có phản ánh ý nghĩa không?
- Cùng một construct có syntax nhất quán không?
- Precedence, associativity và grouping có dễ dự đoán không?
- Side effect, retry, timeout và external call có dễ nhận ra không?
- Default, nullability, unit và implicit conversion có rõ không?
- Control flow, branch, loop, parallel join và wait state có dễ theo dõi không?
- Abstraction có giảm lặp mà không che logic không?
- Module boundary, import và ownership có rõ không?
- Formatter và code style có nhất quán không?
- Comment giải thích lý do/constraint thay vì lặp lại source không?
- Diagnostic có source location, error code và expected/actual không?
- IDE có completion, hover, navigation và explain view không?
- Example/documentation có phản ánh behavior thực tế không?
- Người mới có thể thực hiện change task mà không cần hỏi tác giả không?
- Version migration có giữ convention và cung cấp replacement rõ không?

## 28. Kết quả cần có sau khi thiết kế tính dễ đọc

Một chiến lược readability hoàn chỉnh cho DSL thường cung cấp:

- **Audience model:** persona, nhiệm vụ và kiến thức nền của người đọc.
- **Domain vocabulary:** glossary, naming convention và stable terminology.
- **Syntax principles:** explicitness/concision, grammar consistency và precedence.
- **Expression rules:** grouping, operator associativity, condition naming và side-effect clarity.
- **Control-flow model:** branch, loop, parallel, wait, retry và error path dễ nhận diện.
- **Abstraction policy:** function, module, subprocess và giới hạn indirection.
- **Type/effect semantics:** domain type, unit, nullability, default và effect metadata.
- **Module organization:** cohesion, namespace, imports, visibility và dependency direction.
- **Formatting standard:** formatter, indentation, line width, comments và table style.
- **Documentation/diagnostics:** examples, glossary, source spans, error codes và migration guidance.
- **Developer tooling:** highlighting, completion, hover, navigation, refactoring và explain trace.
- **Evaluation method:** comprehension task, review/change task, defect analysis và persona feedback.
- **Evolution policy:** deprecation, formatter migration, language version và semantic compatibility.

Tính dễ đọc của DSL là kết quả của nhiều quyết định phối hợp: vocabulary gần domain, syntax nhất quán, tên có nghĩa, control flow rõ, type/effect minh bạch, abstraction vừa đủ và tooling hỗ trợ người đọc. Cú pháp ngắn có thể giảm công sức viết nhưng không nhất thiết giảm công sức hiểu; cú pháp tường minh có thể dài hơn nhưng giúp reviewer, operator và auditor nhận ra điều kiện cùng tác động của chương trình. Vì vậy, nên đánh giá readability bằng những nhiệm vụ thực tế của các nhóm người dùng, không chỉ bằng số dòng hoặc số ký tự. Khi convention, formatter, diagnostics, examples và migration policy cùng nhất quán, DSL trở nên dễ học, dễ review và dễ bảo trì mà vẫn giữ được khả năng biểu đạt và hiệu năng ở runtime.

