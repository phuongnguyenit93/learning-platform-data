# AND, OR và NOT trong SpEL

Các toán tử logic AND, OR và NOT cho phép kết hợp nhiều điều kiện thành một biểu thức boolean trong Spring Expression Language (SpEL). Chúng thường được dùng để kiểm tra trạng thái, xác định quyền hoặc quyết định một quy tắc cấu hình có được thỏa mãn hay không.

SpEL hỗ trợ cả dạng từ khóa dễ đọc là and, or, not và dạng ký hiệu ngắn là &&, ||, !. Để viết biểu thức đúng và dễ bảo trì, cần hiểu bảng chân trị, thứ tự ưu tiên, cách nhóm bằng dấu ngoặc và hành vi short-circuit khi đánh giá vế phải.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Dùng and, or, not và các dạng ký hiệu tương ứng.
- Xác định kết quả của biểu thức logic bằng bảng chân trị.
- Hiểu thứ tự ưu tiên giữa NOT, AND và OR.
- Dùng dấu ngoặc để thể hiện rõ điều kiện bắt buộc và điều kiện thay thế.
- Giải thích short-circuit và cách nó ảnh hưởng đến việc đánh giá vế phải.
- Kiểm tra null trước khi truy cập thuộc tính lồng nhau.
- Kết hợp toán tử logic với biến, property, collection và điều kiện nghiệp vụ.
- Viết test cho cả nhánh đúng, sai và các trường hợp biên.

Bạn nên biết cách parse một biểu thức SpEL, truyền biến qua EvaluationContext và đọc giá trị boolean từ Expression.

## 2. Ba toán tử logic cơ bản

SpEL có ba phép logic chính:

| Ý nghĩa | Dạng từ khóa | Dạng ký hiệu |
|---|---|---|
| AND — và | and | && |
| OR — hoặc | or | \|\| |
| NOT — phủ định | not | ! |

Hai dạng trong mỗi hàng có cùng ý nghĩa logic. Dạng từ khóa thường dễ đọc trong biểu thức cấu hình; dạng ký hiệu quen thuộc với người đã biết Java. Nên chọn một phong cách nhất quán trong cùng dự án.

### 2.1. AND — tất cả điều kiện đều phải đúng

AND chỉ trả về true khi cả hai toán hạng đều true.

~~~text
#active and #verified
~~~

Điều kiện này yêu cầu tài khoản vừa đang hoạt động vừa đã được xác minh.

Bảng chân trị:

| A | B | A and B |
|---|---|---|
| false | false | false |
| false | true | false |
| true | false | false |
| true | true | true |

Dùng AND khi mỗi điều kiện là một yêu cầu bắt buộc. Ví dụ, một đơn hàng chỉ được xử lý khi đã thanh toán và chưa bị hủy:

~~~text
#order.paid and not #order.cancelled
~~~

### 2.2. OR — chỉ cần ít nhất một điều kiện đúng

OR trả về true khi ít nhất một toán hạng là true. Nó chỉ trả về false khi cả hai đều false.

~~~text
#isAdmin or #isOwner
~~~

Điều kiện này cho phép truy cập nếu người dùng là admin hoặc là chủ sở hữu tài nguyên.

Bảng chân trị:

| A | B | A or B |
|---|---|---|
| false | false | false |
| false | true | true |
| true | false | true |
| true | true | true |

Dùng OR khi các nhánh là lựa chọn thay thế. Ví dụ, đơn hàng được ưu tiên nếu thuộc nhóm VIP hoặc có tổng tiền vượt ngưỡng:

~~~text
#customer.vip or #order.total >= #priorityThreshold
~~~

### 2.3. NOT — đảo ngược giá trị boolean

NOT đảo true thành false và false thành true.

~~~text
not #disabled
~~~

Dạng ký hiệu tương đương:

~~~text
!#disabled
~~~

NOT là toán tử một ngôi, tức chỉ áp dụng lên một biểu thức ở phía sau. Khi phủ định một điều kiện phức tạp, nên đặt điều kiện đó trong dấu ngoặc:

~~~text
not (#blocked or #expired)
~~~

Biểu thức trên chỉ true khi cả blocked và expired đều false.

## 3. Kết hợp nhiều toán tử và thứ tự ưu tiên

Khi một biểu thức có nhiều toán tử logic, SpEL áp dụng thứ tự ưu tiên:

1. NOT được xử lý trước.
2. AND được xử lý sau NOT.
3. OR được xử lý sau AND.

Các phép so sánh như ==, !=, >, >=, < và <= được nhóm trước khi kết hợp với toán tử logic.

Ví dụ:

~~~text
#age >= 18 and #verified or #isAdmin
~~~

Được hiểu như sau:

~~~text
((#age >= 18) and #verified) or #isAdmin
~~~

Do AND có độ ưu tiên cao hơn OR, biểu thức đúng nếu người dùng đủ tuổi và đã xác minh, hoặc người dùng là admin.

Nếu nghiệp vụ yêu cầu phải xác minh trong mọi trường hợp, còn tuổi hoặc quyền admin là hai lựa chọn thay thế, hãy viết:

~~~text
(#age >= 18 or #isAdmin) and #verified
~~~

Hai biểu thức không tương đương. Với age = 16, verified = false và isAdmin = true, biểu thức đầu tiên trả về true; biểu thức thứ hai trả về false.

### 3.1. Dấu ngoặc để nhóm điều kiện

Dấu ngoặc tròn làm rõ phạm vi của một nhóm logic và có thể thay đổi kết quả theo ý định nghiệp vụ.

Ví dụ:

~~~text
#enabled and (#role == 'ADMIN' or #role == 'MANAGER')
~~~

Người dùng phải được bật và có một trong hai vai trò. Nếu bỏ dấu ngoặc:

~~~text
#enabled and #role == 'ADMIN' or #role == 'MANAGER'
~~~

Do AND được ưu tiên hơn OR, biểu thức sẽ tương đương:

~~~text
(#enabled and #role == 'ADMIN') or #role == 'MANAGER'
~~~

Khi đó MANAGER có thể thỏa điều kiện dù enabled là false. Đây thường là lỗi logic khó nhận ra nếu biểu thức được viết trên một dòng dài.

### 3.2. Phủ định một nhóm điều kiện

De Morgan giúp chuyển đổi cách viết logic:

- NOT (A AND B) tương đương NOT A OR NOT B.
- NOT (A OR B) tương đương NOT A AND NOT B.

Ví dụ:

~~~text
not (#paid and #confirmed)
~~~

Tương đương:

~~~text
not #paid or not #confirmed
~~~

Còn:

~~~text
not (#blocked or #expired)
~~~

Tương đương:

~~~text
not #blocked and not #expired
~~~

Khi dùng các quy tắc này, hãy giữ dấu ngoặc quanh nhóm được phủ định. Điều đó giúp người đọc kiểm tra chính xác phạm vi của NOT.

## 4. Short-circuit: có thể bỏ qua vế phải

AND và OR đánh giá từ trái sang phải và có thể dừng ngay khi đã xác định được kết quả. Đây là hành vi short-circuit.

- Với AND, nếu vế trái là false thì toàn biểu thức chắc chắn false; vế phải không cần đánh giá.
- Với OR, nếu vế trái là true thì toàn biểu thức chắc chắn true; vế phải không cần đánh giá.

Ví dụ:

~~~text
#customer != null and #customer.active
~~~

Nếu customer là null, vế trái false nên vế phải không được đánh giá. Nhờ vậy biểu thức tránh truy cập active trên một đối tượng null.

Một ví dụ OR:

~~~text
#isAdmin or #account.owner
~~~

Nếu isAdmin là true, SpEL không cần đánh giá vế phải để xác định kết quả. Tuy nhiên, ví dụ này chỉ phù hợp khi root object và thuộc tính owner đã được thiết kế rõ ràng.

### 4.1. Thứ tự vế trái và vế phải có ý nghĩa

Hãy đặt điều kiện bảo vệ ở bên trái:

~~~text
#order != null and #order.total > 0
~~~

Cách viết này kiểm tra order tồn tại trước khi đọc total.

Tránh viết theo thứ tự ngược:

~~~text
#order.total > 0 and #order != null
~~~

Vế trái có thể lỗi trước khi phép kiểm tra null được thực hiện.

### 4.2. Không dựa vào vế phải để tạo side effect

Vì short-circuit có thể bỏ qua vế phải, không nên đặt hành động bắt buộc vào một method call ở đó:

~~~text
#enabled and #service.updateStatus()
~~~

Nếu enabled là false, updateStatus có thể không được gọi. Nếu enabled là true, biểu thức lại có thể thay đổi trạng thái trong lúc kiểm tra điều kiện.

Nên thực hiện hành động bằng Java theo luồng rõ ràng, sau đó đánh giá điều kiện chỉ đọc. Biểu thức logic nên mô tả một điều kiện và trả về kết quả dễ dự đoán.

## 5. Sử dụng biến trong EvaluationContext

Biến SpEL có tiền tố #. Ứng dụng đăng ký biến trong context trước khi đánh giá:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#age >= 18 and #verified and not #blocked");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("age", 21);
context.setVariable("verified", true);
context.setVariable("blocked", false);

Boolean allowed =
    expression.getValue(context, Boolean.class);
~~~

Kết quả là true.

Có thể thay đổi giá trị biến cho lần đánh giá khác:

~~~java
context.setVariable("blocked", true);
Boolean allowedAgain =
    expression.getValue(context, Boolean.class);
~~~

Kết quả lần này là false.

Đưa dữ liệu vào context giúp tách quy tắc khỏi dữ liệu. Không nên ghép dữ liệu người dùng trực tiếp vào chuỗi biểu thức, vì điều đó dễ gây lỗi escape và có thể làm input bị hiểu thành cú pháp SpEL.

## 6. Kết hợp logic với property và collection

### 6.1. Kiểm tra property lồng nhau

Với object có nhiều tầng thuộc tính, hãy kiểm tra object trung gian trước khi truy cập tiếp:

~~~text
#customer != null and #customer.address != null and #customer.address.city == 'Hanoi'
~~~

Do AND short-circuit, nếu customer null thì các phần phía sau không được đánh giá. Nếu customer tồn tại nhưng address null, điều kiện thứ ba được bỏ qua.

Có thể dùng safe navigation:

~~~text
#customer?.address?.city == 'Hanoi'
~~~

Cách viết này ngắn hơn, nhưng cần hiểu kết quả null khi đường dẫn không tồn tại và cách toán tử so sánh xử lý giá trị đó. Với quy tắc quan trọng, hãy chọn cách viết thể hiện rõ chính sách null.

### 6.2. Lọc collection bằng predicate

Toán tử selection dùng dấu .?[...] để lọc phần tử. Bên trong predicate có thể kết hợp AND, OR và NOT:

~~~text
#orders.?[active and total >= 100]
~~~

Ví dụ lọc đơn hàng đang hoạt động và có tổng tiền ít nhất 100.

Một điều kiện khác:

~~~text
#orders.?[(priority == 'HIGH' or customer.vip) and not cancelled]
~~~

Dấu ngoặc nhóm hai lựa chọn ưu tiên trước khi kết hợp với điều kiện chưa bị hủy. Trong predicate, #this đại diện cho phần tử đang được xét; tên thuộc tính không có tiền tố được phân giải theo phần tử hiện tại.

Giữ predicate ngắn. Nếu điều kiện có nhiều tầng, nhiều lời gọi method hoặc cần truy cập dịch vụ, hãy chuyển logic lọc sang Java để dễ kiểm thử và tối ưu.

## 7. Kết hợp với biểu thức điều kiện

Toán tử điều kiện ternary dùng cú pháp:

~~~text
condition ? valueIfTrue : valueIfFalse
~~~

Có thể dùng logic để xây dựng condition:

~~~text
#active and #verified ? 'READY' : 'PENDING'
~~~

Ví dụ có nhiều lựa chọn cần nhóm rõ ràng:

~~~text
(#isAdmin or #isOwner) and #resource.enabled
    ? 'ALLOW'
    : 'DENY'
~~~

Toàn bộ điều kiện đứng trước dấu ? được đánh giá trước khi chọn nhánh. Dấu ngoặc quanh nhóm OR giúp thể hiện rằng cả admin và owner đều phải thỏa điều kiện resource.enabled.

## 8. Dùng toán tử logic trong Spring

SpEL được dùng ở nhiều điểm tích hợp Spring. Trong một số ngữ cảnh, biểu thức có thể đọc property, bean hoặc thông tin do framework cung cấp. Cú pháp logic vẫn tuân theo quy tắc SpEL, nhưng root object và quyền truy cập phụ thuộc vào nơi biểu thức được đánh giá.

Ví dụ trong annotation @Value:

~~~java
@Value("#{ @featureFlags.enabled and @featureFlags.verified }")
private boolean featureReady;
~~~

Trong cấu hình này, Spring cung cấp bean resolver để biểu thức tham chiếu bean có tên featureFlags. Bean và các thuộc tính tương ứng phải tồn tại trong ApplicationContext.

Một số annotation như @PreAuthorize cũng dùng SpEL, nhưng context của Spring Security cung cấp các biến và hàm riêng như authentication hoặc hasRole. Không giả định các tên đó có sẵn trong một StandardEvaluationContext tự tạo. Khi dùng biểu thức trong annotation bảo mật, hãy kiểm tra chính xác root object, role prefix và quyền được cấu hình trong Security expression handler.

## 9. Kiểu dữ liệu và giá trị null

Các toán tử logic cần kết quả boolean-compatible. Hãy ưu tiên truyền Boolean rõ ràng thay vì dựa vào các chuyển đổi ngầm không cần thiết.

Các trường hợp nên xử lý:

- Biến chưa được đăng ký trong context.
- Biến có giá trị null.
- Property không tồn tại.
- Property trả về kiểu không phù hợp với điều kiện logic.
- Method được gọi trong biểu thức ném exception.
- Collection hoặc phần tử collection là null.

Ví dụ kiểm tra biến null trước khi so sánh:

~~~text
#score != null and #score >= 60
~~~

Nếu score là null, phép so sánh phía sau được bỏ qua nhờ short-circuit. Nếu dữ liệu có thể null, hãy xác định null có nghĩa là chưa có dữ liệu, không hợp lệ hay cần dùng giá trị mặc định.

Elvis có thể cung cấp giá trị thay thế:

~~~text
(#score ?: 0) >= 60
~~~

Chỉ dùng giá trị mặc định khi nó phản ánh đúng nghiệp vụ. Thay null bằng 0 có thể làm thay đổi ý nghĩa của một điều kiện nếu null thực sự là trạng thái chưa xác định.

## 10. Kiểm thử biểu thức logic

Bắt đầu với bảng chân trị của từng toán tử:

| A | B | A AND B | A OR B |
|---|---|---|---|
| false | false | false | false |
| false | true | false | true |
| true | false | false | true |
| true | true | true | true |

NOT có hai trường hợp: NOT false là true và NOT true là false.

Sau đó kiểm thử các nhóm nghiệp vụ:

| Trường hợp | Dữ liệu | Kết quả mong đợi |
|---|---|---|
| Tất cả điều kiện bắt buộc đúng | active=true, verified=true | true |
| Một điều kiện AND sai | active=true, verified=false | false |
| Một nhánh OR đúng | isAdmin=true, isOwner=false | true |
| Cả hai nhánh OR sai | isAdmin=false, isOwner=false | false |
| NOT đảo true | blocked=true | false |
| Object null được bảo vệ | customer=null | false, không truy cập customer.active |
| Nhóm OR rồi AND | admin=true, enabled=false | false nếu enabled là điều kiện bắt buộc |

Một test short-circuit có thể dùng method theo dõi số lần được gọi trong test fixture. Với biểu thức false AND methodCall() hoặc true OR methodCall(), xác nhận method ở vế phải không được gọi. Chỉ dùng method test không có tác dụng phụ ngoài bộ đếm; không dùng side effect nghiệp vụ để điều khiển luồng.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Điều kiện OR cho true ngoài dự kiến | AND có độ ưu tiên cao hơn OR | Nhóm nhánh OR bằng dấu ngoặc |
| Truy cập property null gây lỗi | Kiểm tra null đặt sau phép truy cập | Đưa guard sang vế trái hoặc dùng safe navigation |
| NOT phủ định sai phạm vi | Thiếu ngoặc quanh nhóm logic | Viết not (A or B) hoặc not (A and B) |
| Biểu thức trả lỗi kiểu | Toán hạng không phải boolean-compatible | Kiểm tra kiểu biến và property |
| Vế phải không chạy | Short-circuit đã xác định được kết quả | Kiểm tra giá trị vế trái và thứ tự điều kiện |
| Method chạy không ổn định | Method nằm trong nhánh có thể bị short-circuit | Không đặt hành động bắt buộc trong biểu thức |
| Biểu thức dài khó hiểu | Quá nhiều nhóm AND/OR lồng nhau | Đặt ngoặc, dùng tên biến rõ hoặc chuyển logic về Java |

Khi debug, hãy đánh giá riêng từng điều kiện thành Boolean, sau đó kết hợp từng nhóm. Đừng sửa bằng cách thêm ngoặc ngẫu nhiên; hãy viết lại điều kiện theo ngôn ngữ nghiệp vụ rồi chuyển từng nhóm thành SpEL.

## 12. Bài tập thực hành

1. Viết biểu thức yêu cầu tài khoản active và verified.
2. Viết biểu thức cho phép admin hoặc owner truy cập tài nguyên.
3. Sửa biểu thức để yêu cầu enabled trong mọi trường hợp, dù người dùng là admin hay owner.
4. Dùng NOT để loại tài khoản blocked hoặc expired.
5. Dùng biến trong EvaluationContext để đánh giá điều kiện tuổi, xác minh và trạng thái.
6. Dùng short-circuit để bảo vệ truy cập property khi object có thể null.
7. Lọc danh sách order bằng selection, kết hợp AND, OR và NOT.
8. Viết test chứng minh vế phải được bỏ qua khi AND có vế trái false và OR có vế trái true.

## 13. Checklist khi sử dụng trong ứng dụng

- [ ] Đã chọn đúng dạng từ khóa hoặc ký hiệu và giữ phong cách nhất quán chưa?
- [ ] Đã hiểu precedence NOT, AND và OR chưa?
- [ ] Đã nhóm các nhánh OR và điều kiện bắt buộc bằng ngoặc chưa?
- [ ] Đã đặt điều kiện null guard ở vế trái chưa?
- [ ] Đã hiểu short-circuit có thể bỏ qua vế phải chưa?
- [ ] Có method side effect nào nằm trong biểu thức không?
- [ ] Các biến và property có kiểu boolean-compatible không?
- [ ] Đã kiểm thử mọi nhánh true/false và dữ liệu null chưa?
- [ ] Đã xác định đúng root object và biến của Spring integration context chưa?
- [ ] Biểu thức có đủ ngắn để người khác bảo trì không?

## 14. Kết luận

AND yêu cầu mọi điều kiện đúng, OR yêu cầu ít nhất một điều kiện đúng và NOT đảo giá trị boolean. SpEL áp dụng NOT trước AND, rồi OR; dấu ngoặc giúp thể hiện rõ nhóm điều kiện theo nghiệp vụ. Short-circuit cho phép bỏ qua vế phải khi kết quả đã xác định, vì vậy hãy đặt null guard ở bên trái và tránh giấu hành động có tác dụng phụ trong biểu thức. Khi dùng trong Spring, luôn hiểu root object và quyền của EvaluationContext tại điểm tích hợp cụ thể.