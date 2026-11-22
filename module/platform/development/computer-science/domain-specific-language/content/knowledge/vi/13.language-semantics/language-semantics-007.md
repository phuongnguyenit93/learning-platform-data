# Tính xác định

Trong ngữ nghĩa của một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), **tính xác định** (*determinism*) mô tả khả năng một chương trình tạo ra cùng một kết quả khi được đánh giá nhiều lần với cùng đầu vào và cùng trạng thái ban đầu, trong cùng các điều kiện thực thi đã được xác định. Một DSL có ngữ nghĩa xác định giúp người dùng dự đoán hành vi, tái hiện lỗi, kiểm thử kết quả và giải thích vì sao một quy tắc được áp dụng.

Ví dụ, nếu DSL mô tả chính sách tính phí giao hàng và đầu vào gồm cùng địa chỉ, trọng lượng, loại dịch vụ cùng bảng giá, người dùng thường mong muốn kết quả phí không thay đổi giữa các lần chạy. Nếu kết quả phụ thuộc vào thứ tự duyệt một tập hợp không có thứ tự, thời điểm hệ thống, một dịch vụ bên ngoài hoặc cuộc đua giữa các luồng, cùng một chương trình có thể cho ra các kết quả khác nhau.

Tính xác định không chỉ là thuộc tính của một hàm hoặc một phép tính. Nó liên quan đến toàn bộ ngữ nghĩa DSL: cách chọn quy tắc, thứ tự đánh giá, xử lý xung đột, lịch thực thi, dữ liệu bên ngoài, tác dụng phụ, lỗi và các thao tác đồng thời. Vì vậy, khi thiết kế DSL, cần xác định rõ đầu vào nào được xem là giống nhau, kết quả nào được xem là quan sát được và những nguồn biến thiên nào được cho phép.

## 1. Tính xác định là gì?

Một chương trình có tính xác định nếu cùng một cấu hình đầu vào đầy đủ dẫn đến cùng một hành vi theo tiêu chí quan sát đã chọn. Cấu hình đầu vào không chỉ là các tham số được truyền trực tiếp. Nó có thể bao gồm:

- Dữ liệu và trạng thái miền tại thời điểm bắt đầu.
- Phiên bản chương trình DSL, mô hình miền và chính sách được sử dụng.
- Cấu hình môi trường và các tham số thực thi.
- Giá trị đồng hồ, múi giờ và locale nếu chương trình sử dụng chúng.
- Trạng thái hoặc snapshot của hệ thống bên ngoài.
- Seed của bộ sinh số ngẫu nhiên nếu có sử dụng tính ngẫu nhiên.
- Các sự kiện đầu vào và thứ tự sự kiện được quy định.

Nếu các yếu tố này không được cố định hoặc đưa vào mô hình đầu vào, hai lần chạy có thể không thực sự có cùng điều kiện ban đầu dù văn bản DSL giống nhau.

### Ví dụ đơn giản

Xét biểu thức DSL:

~~~text
shippingFee = weightKg * ratePerKg;
~~~

Nếu `weightKg` và `ratePerKg` là hai giá trị số đã xác định, phép nhân có quy tắc rõ ràng và không phụ thuộc trạng thái bên ngoài, kết quả sẽ xác định.

Ngược lại:

~~~text
shippingFee = weightKg * currentRate();
~~~

Nếu `currentRate()` truy vấn bảng giá có thể thay đổi giữa hai lần gọi, cùng một `weightKg` vẫn có thể tạo ra phí khác nhau. Biểu thức chỉ trở nên xác định khi bảng giá được cố định bằng snapshot, phiên bản hoặc một đầu vào rõ ràng.

### Cùng mã nguồn chưa chắc là cùng đầu vào

Hai lần chạy cùng một tệp DSL không đảm bảo cùng kết quả nếu trạng thái môi trường khác nhau. Ví dụ, chính sách:

~~~text
if currentTime() < promotion.endsAt then applyDiscount;
~~~

có thể cho kết quả khác nhau vào hai thời điểm khác nhau. Nếu thời gian hiện tại là một đầu vào được cung cấp rõ ràng, cùng giá trị thời gian sẽ tạo kết quả nhất quán. Nếu DSL tự đọc đồng hồ hệ thống, thời gian là một nguồn biến thiên bên ngoài.

## 2. Định nghĩa hình thức

Có thể mô tả một chương trình DSL bằng một trạng thái ban đầu và quan hệ đánh giá. Gọi `P` là chương trình, `S` là trạng thái ban đầu và `E` là môi trường thực thi. Kết quả quan sát được được ký hiệu là `O`.

~~~text
evaluate(P, S, E) = O
~~~

Ngữ nghĩa xác định khi với cùng `P`, `S` và `E`, chỉ có một kết quả quan sát được:

~~~text
evaluate(P, S, E) = O1
evaluate(P, S, E) = O2
therefore O1 = O2
~~~

Trong ngữ nghĩa thao tác, có thể mô tả bằng quan hệ chuyển trạng thái. Nếu một cấu hình `C` có thể chuyển sang `C1` và cũng có thể chuyển sang `C2` trong cùng điều kiện, quan hệ chuyển được xem là xác định khi hai trạng thái tiếp theo thực chất giống nhau:

~~~text
C -> C1  and  C -> C2  implies  C1 = C2
~~~

Đây là cách diễn đạt đơn giản cho tính xác định của một bước đánh giá. Với hệ thống có nhiều bước, cần xem xét cả chuỗi chuyển trạng thái hoặc kết quả cuối cùng.

### Kết quả quan sát được gồm những gì?

Tùy mục tiêu DSL, kết quả không chỉ là giá trị trả về. Nó có thể gồm:

- Giá trị hoặc dữ liệu được tạo ra.
- Trạng thái miền sau thực thi.
- Các sự kiện được phát ra và thứ tự phát.
- Các lời gọi dịch vụ hoặc tác dụng phụ bên ngoài.
- Lỗi, ngoại lệ, mã từ chối và thời điểm thất bại.
- Nhật ký kiểm toán hoặc thông tin truy vết có ý nghĩa nghiệp vụ.
- Việc chương trình kết thúc hay tiếp tục chạy.

Ví dụ, hai lần chạy có thể tạo cùng trạng thái cuối `OrderStatus.CONFIRMED`, nhưng lần thứ nhất phát sự kiện `PaymentCaptured` trước `OrderConfirmed`, còn lần thứ hai phát theo thứ tự ngược lại. Nếu hệ thống tích hợp quan sát thứ tự sự kiện, hai lần chạy không tương đương về hành vi.

Do đó, đặc tả DSL cần nói rõ tính xác định được xét ở mức giá trị cuối, trạng thái cuối, toàn bộ trace sự kiện hay một tập các quan sát khác.

## 3. Tính xác định ở các lớp của DSL

Tính xác định có thể được xem xét ở nhiều lớp. Một lớp xác định không tự động bảo đảm toàn bộ hệ thống xác định.

| Lớp | Câu hỏi về tính xác định | Ví dụ nguồn gây khác biệt |
|---|---|---|
| Cú pháp | Một văn bản có được phân tích theo một cấu trúc duy nhất không? | Ngữ pháp mơ hồ, độ ưu tiên toán tử chưa rõ. |
| Phân giải tên và kiểu | Một tên hoặc biểu thức có được liên kết đến cùng một khai báo và kiểu không? | Nhiều khai báo cùng tên, import xung đột, phụ thuộc thứ tự tải module. |
| Ngữ nghĩa tĩnh | Kiểm tra cùng một chương trình có đưa ra cùng kết luận không? | Tập quy tắc kiểm tra không ổn định hoặc phụ thuộc dữ liệu môi trường. |
| Ngữ nghĩa đánh giá | Cùng trạng thái có chọn cùng bước hoặc quy tắc tiếp theo không? | Nhiều rule cùng khớp nhưng không có chính sách ưu tiên. |
| Thực thi | Chương trình có tạo cùng trạng thái và tác dụng phụ không? | Race condition, dữ liệu ngoài, thời gian, retry. |
| Sinh mã | Cùng mô hình có tạo cùng mã hoặc cấu hình không? | Thứ tự duyệt map không ổn định, timestamp tự sinh, ID ngẫu nhiên. |
| Triển khai | Các môi trường chạy có cùng hành vi không? | Phiên bản runtime, locale, timezone, số học hoặc thư viện khác nhau. |

Một parser xác định có thể tạo cùng AST, nhưng interpreter vẫn có thể không xác định nếu lịch chạy các tác vụ song song không được quy định. Ngược lại, một runtime có thể xử lý ổn định một AST được tạo từ nhiều cách viết cụ thể, nếu các cách viết đó được chuẩn hóa về cùng mô hình.

## 4. Phân biệt tính xác định với các khái niệm gần nghĩa

### Determinism và predictability

**Tính xác định** là thuộc tính về số lượng kết quả hoặc hành vi được phép trong cùng điều kiện. **Khả năng dự đoán** (*predictability*) là mức độ người dùng có thể hiểu và dự đoán hành vi đó.

Một chương trình có thể xác định nhưng khó dự đoán nếu quy tắc phức tạp hoặc có nhiều bước ẩn. Ngược lại, người dùng có thể dự đoán một hệ thống thường hoạt động theo cách quen thuộc, nhưng hệ thống vẫn không xác định nếu có nhiều kết quả hợp lệ do đồng thời.

### Determinism và reproducibility

**Khả năng tái lập** (*reproducibility*) là khả năng chạy lại một phép tính hoặc quy trình với cùng điều kiện để thu được kết quả tương đương. Tính xác định hỗ trợ khả năng tái lập, nhưng muốn tái lập thực tế còn cần lưu đầy đủ phiên bản, dữ liệu, cấu hình, seed và phụ thuộc môi trường.

Ví dụ, một chương trình ngẫu nhiên có thể được tái lập nếu seed và thuật toán sinh số được cố định. Bản thân chương trình vẫn có chủ đích sử dụng tính ngẫu nhiên; đầu vào đầy đủ bao gồm seed.

### Determinism và idempotency

**Idempotency** (tính lũy đẳng) có nghĩa là áp dụng một thao tác nhiều lần có cùng hiệu ứng như áp dụng một lần:

~~~text
f(f(x)) = f(x)
~~~

Idempotency không đồng nghĩa với determinism. Một thao tác có thể xác định nhưng không lũy đẳng, chẳng hạn tăng bộ đếm thêm một đơn vị. Một thao tác lũy đẳng có thể vẫn phụ thuộc trạng thái bên ngoài nếu cách xác định hiệu ứng không được cố định.

### Determinism và purity

Một hàm thuần (*pure function*) thường cho cùng kết quả với cùng đối số và không gây tác dụng phụ quan sát được. Tính thuần là một cách mạnh để xây dựng các thành phần xác định. Tuy nhiên, một chương trình gồm nhiều hàm thuần vẫn có thể không xác định nếu hệ thống chọn thứ tự đánh giá hoặc kết hợp kết quả theo cách không ổn định.

### Determinism và concurrency

Đồng thời (*concurrency*) là việc nhiều tác vụ có thể tiến triển chồng lấn hoặc xen kẽ. Đồng thời không nhất thiết gây bất định. Một mô hình đồng thời có thể xác định nếu lịch, thứ tự giao tiếp hoặc quy tắc giải quyết xung đột được định nghĩa. Vấn đề xuất hiện khi nhiều lịch hợp lệ có thể tạo ra kết quả quan sát khác nhau.

## 5. Tính xác định của cú pháp và ngữ pháp

Trước khi bàn về hành vi lúc chạy, cần bảo đảm chương trình được hiểu theo một cấu trúc cú pháp duy nhất. Một ngữ pháp mơ hồ có thể cho phép một chuỗi đầu vào có nhiều cây phân tích.

Ví dụ:

~~~text
a + b * c
~~~

Nếu ngữ pháp không quy định độ ưu tiên, biểu thức có thể được hiểu là:

~~~text
Add(a, Multiply(b, c))
~~~

hoặc:

~~~text
Multiply(Add(a, b), c)
~~~

Hai cây có thể tạo kết quả khác nhau. DSL cần xác định độ ưu tiên toán tử, tính kết hợp hoặc yêu cầu người dùng dùng dấu ngoặc.

### Xác định độ ưu tiên và tính kết hợp

Một bảng quy tắc có thể quy định:

| Nhóm toán tử | Ví dụ | Độ ưu tiên tương đối | Tính kết hợp thường gặp |
|---|---|---:|---|
| Nhân/chia | `*`, `/` | Cao | Trái |
| Cộng/trừ | `+`, `-` | Trung bình | Trái |
| So sánh | `>`, `==`, `<=` | Thấp hơn số học | Thường không kết hợp hoặc giới hạn chuỗi |
| AND | `and` | Thấp hơn so sánh | Trái hoặc theo quy tắc logic DSL |
| OR | `or` | Thấp hơn AND | Trái hoặc theo quy tắc logic DSL |

Quy tắc cụ thể tùy DSL. Quan trọng là cùng một chuỗi luôn tạo cùng cấu trúc trừu tượng. Nếu DSL hỗ trợ parser có lựa chọn hoặc cú pháp phân tích phụ thuộc ngữ cảnh, các lựa chọn đó cũng cần được giải quyết bằng quy tắc rõ ràng.

### Phân giải tên xác định

Nếu một định danh có thể tham chiếu đến nhiều khai báo, DSL phải xác định quy tắc phạm vi, shadowing, import và ưu tiên. Ví dụ, nếu cả module hiện tại và module được import đều khai báo `Order`, cần quy định lỗi xung đột hoặc cách viết tên có namespace.

Không nên để kết quả phân giải tên phụ thuộc thứ tự ngẫu nhiên mà các module được tải. Nếu thứ tự import có ý nghĩa, phải quy định rõ; nếu không, tập khai báo nên được xây dựng theo cách không phụ thuộc thứ tự tải.

## 6. Tính xác định trong thứ tự đánh giá

Một DSL cần quy định thứ tự đánh giá biểu thức, điều kiện và hành động. Nếu không, cùng chương trình có thể được thực thi theo nhiều thứ tự hợp lệ.

### Đánh giá tuần tự

Ví dụ:

~~~text
step validateOrder;
step reserveInventory;
step createShipment;
~~~

Nếu DSL quy định các bước được thực hiện theo thứ tự văn bản, thứ tự đã rõ. Nếu DSL cho phép runtime tự sắp xếp các bước dựa trên phụ thuộc, cần xác định cách chọn thứ tự khi nhiều bước cùng sẵn sàng.

### Đánh giá biểu thức

Xét:

~~~text
checkBalance() and reserveFunds()
~~~

Nếu `and` dùng short-circuit và đánh giá từ trái sang phải, `reserveFunds()` chỉ được gọi khi `checkBalance()` trả về true. Nếu DSL không xác định thứ tự, runtime có thể đánh giá hai vế theo nhiều cách. Khi các hàm có tác dụng phụ, kết quả có thể khác.

Một DSL có thể chọn một trong các chính sách:

- Đánh giá trái sang phải và short-circuit.
- Đánh giá cả hai vế theo một thứ tự được định nghĩa.
- Chỉ cho phép biểu thức thuần trong các toán tử logic.
- Cho phép đánh giá song song nhưng yêu cầu biểu thức không có tác dụng phụ và kết quả có thể kết hợp an toàn.

Chính sách phải được ghi trong đặc tả ngữ nghĩa và phản ánh trong interpreter hoặc code generator.

### Thứ tự duyệt tập hợp

Nếu DSL cho phép:

~~~text
for each item in order.items do reserve(item);
~~~

thì cần biết `order.items` có thứ tự hay không. Nếu là danh sách có thứ tự, DSL có thể quy định duyệt theo thứ tự danh sách. Nếu là tập hợp không có thứ tự, không nên ngầm giả định thứ tự ổn định.

Điều này đặc biệt quan trọng khi `reserve(item)` có tác dụng phụ hoặc khi lỗi ở phần tử đầu tiên khiến các phần tử sau không được xử lý.

## 7. Thứ tự quy tắc và giải quyết xung đột

DSL chính sách, luật nghiệp vụ hoặc cấu hình thường cho phép khai báo nhiều quy tắc. Nếu nhiều quy tắc cùng khớp một tình huống, runtime cần biết áp dụng quy tắc nào và theo thứ tự nào.

Ví dụ:

~~~text
rule "gold customer discount" priority 10
    when customer.tier == GOLD then discount 10%;

rule "large order discount" priority 10
    when order.total >= 5000000 then discount 8%;
~~~

Một đơn hàng của khách GOLD có tổng tiền lớn có thể khớp cả hai quy tắc. DSL cần quy định:

- Áp dụng cả hai mức giảm, lấy mức cao nhất hay chọn một quy tắc?
- Nếu cùng priority thì thứ tự khai báo có được dùng làm tie-break không?
- Nếu hai quy tắc tạo hành động xung đột thì báo lỗi, từ chối hay chọn theo chính sách?
- Có cho phép nhiều quy tắc cùng cập nhật một thuộc tính không?

### Các chiến lược phổ biến

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Thứ tự khai báo | Áp dụng theo thứ tự xuất hiện trong tệp. | Khi thứ tự văn bản là một phần rõ ràng của ngữ nghĩa. |
| Priority | Quy tắc có độ ưu tiên cao hơn được xét trước. | Khi nghiệp vụ có mức ưu tiên được xác định. |
| First match | Chỉ áp dụng quy tắc đầu tiên thỏa điều kiện. | Khi các quy tắc đại diện cho các nhánh loại trừ nhau. |
| Apply all | Áp dụng mọi quy tắc khớp theo một thứ tự đã quy định. | Khi hành động có thể kết hợp và thứ tự an toàn. |
| Conflict detection | Phát hiện nhiều quy tắc xung đột và yêu cầu sửa cấu hình. | Khi chọn tùy ý có thể gây hậu quả nghiệp vụ. |
| Explicit tie-break | Dùng khóa phụ ổn định như mã quy tắc hoặc thứ tự được khai báo. | Khi cần kết quả duy nhất dù priority bằng nhau. |

Không có chiến lược nào phù hợp cho mọi miền. Ví dụ, hệ thống định giá có thể cộng dồn một số ưu đãi nhưng không cho cộng dồn ưu đãi khác. Chính sách xung đột cần gắn với loại quy tắc và quy tắc nghiệp vụ thực tế.

### Không dùng thứ tự của cấu trúc không có thứ tự làm tie-break ngầm

Nếu các rule được lưu trong `HashMap` hoặc một tập hợp không cam kết thứ tự, việc chọn rule đầu tiên có thể thay đổi giữa runtime hoặc phiên bản. Nếu thứ tự có ý nghĩa, hãy dùng cấu trúc có thứ tự hoặc khóa ưu tiên được định nghĩa rõ.

## 8. Các nguồn gây bất định lúc thực thi

Một chương trình DSL có thể phụ thuộc vào nhiều yếu tố bên ngoài. Nếu các yếu tố này không được kiểm soát hoặc mô hình hóa, cùng chương trình có thể tạo kết quả khác nhau.

### Thời gian hệ thống

Các hàm như `now()`, `today()` hoặc `currentTime()` trả về giá trị thay đổi theo thời điểm gọi. Chúng có thể làm thay đổi kết quả điều kiện, hạn chót, phí trễ hoặc thời gian hiệu lực.

Ví dụ:

~~~text
if order.createdAt < now() - 30 days then markOverdue;
~~~

Để tái lập, nên đưa thời gian hiện tại vào execution context hoặc sử dụng một clock có thể thay thế trong kiểm thử. Cũng cần quy định timezone và lịch ngày làm việc nếu nghiệp vụ phụ thuộc chúng.

### Số ngẫu nhiên

Các hàm như `random()` hoặc `chooseRandom()` cố ý tạo biến thiên. Nếu DSL cần hành vi có thể tái lập, seed và thuật toán sinh số phải là một phần của đầu vào hoặc được lưu cùng kết quả chạy.

~~~text
assignAgent = chooseRandom(availableAgents);
~~~

Nếu mục tiêu nghiệp vụ là phân công ngẫu nhiên, kết quả thay đổi có thể là chủ đích. Tuy nhiên, để điều tra một lần phân công cụ thể, cần lưu seed, tập ứng viên và phiên bản thuật toán.

### Dữ liệu bên ngoài

Giá trị lấy từ cơ sở dữ liệu, API, dịch vụ thanh toán, bảng giá hoặc hệ thống danh tính có thể thay đổi giữa các lần chạy. Cần xác định snapshot, phiên bản dữ liệu hoặc thời điểm đọc.

### Môi trường và cấu hình

Biến môi trường, feature flag, cấu hình triển khai, locale, timezone, phiên bản thư viện và chính sách quyền có thể ảnh hưởng kết quả. Nếu chúng tác động đến ngữ nghĩa, cần ghi nhận hoặc truyền chúng rõ ràng.

### Thứ tự của cấu trúc dữ liệu

Map, set hoặc truy vấn cơ sở dữ liệu không có `ORDER BY` có thể trả phần tử theo thứ tự không được bảo đảm. Nếu DSL dùng thứ tự đó để chọn hành động hoặc phát sự kiện, kết quả có thể không ổn định.

### Retry và timeout

Một thao tác mạng có thể thành công ở lần thử đầu, thất bại ở lần khác hoặc timeout dù phía dịch vụ đã xử lý yêu cầu. Nếu retry không có khóa idempotency hoặc hợp đồng rõ ràng, tác dụng phụ có thể bị lặp hoặc kết quả quan sát khác nhau.

## 9. Đồng thời và tính xác định

Đồng thời là nguồn gây bất định quan trọng trong DSL mô tả workflow, xử lý sự kiện, quy tắc hoặc tác vụ song song.

### Race condition

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự xen kẽ của các thao tác đồng thời. Ví dụ, hai đơn cùng kiểm tra số lượng tồn kho là 1 rồi cùng giữ một đơn vị. Nếu việc kiểm tra và cập nhật không nguyên tử, cả hai có thể được xác nhận dù chỉ còn một đơn vị.

~~~text
Task A: read available = 1
Task B: read available = 1
Task A: reserve 1
Task B: reserve 1
~~~

Kết quả có thể vi phạm bất biến tồn kho. Cần dùng giao dịch, khóa, thao tác compare-and-set hoặc cơ chế đồng bộ thích hợp để bảo vệ điều kiện nghiệp vụ.

### Thứ tự hoàn thành không đồng nghĩa với thứ tự bắt đầu

Trong workflow song song:

~~~text
parallel {
    verifyAddress(order);
    checkInventory(order);
    authorizePayment(order);
}
continue createShipment(order);
~~~

Ba tác vụ có thể hoàn thành theo thứ tự khác nhau ở mỗi lần chạy. Nếu `createShipment` chỉ phụ thuộc vào việc cả ba thành công, thứ tự hoàn thành có thể không ảnh hưởng kết quả cuối. Nếu tác vụ đầu tiên hoàn thành được ghi vào log hoặc kích hoạt hành động khác, trace có thể khác nhau.

DSL cần phân biệt rõ:

- Các tác vụ nào độc lập và có thể chạy song song?
- Điều kiện nào cho phép bước tiếp theo bắt đầu?
- Khi nhiều tác vụ lỗi, lỗi nào được báo trước?
- Có hủy các tác vụ còn lại khi một tác vụ thất bại không?
- Thứ tự sự kiện đầu ra có được bảo đảm không?
- Các tác vụ có chia sẻ trạng thái có thể thay đổi không?

### Đồng thời xác định

Một DSL có thể cho phép thực thi song song nhưng vẫn bảo đảm kết quả xác định bằng cách:

- Giới hạn các tác vụ song song chỉ đọc dữ liệu bất biến.
- Dùng các phép biến đổi thuần và kết hợp kết quả theo một quy tắc ổn định.
- Đồng bộ các điểm ghi trạng thái.
- Quy định thứ tự commit hoặc thứ tự phát sự kiện.
- Dùng scheduler xác định trong môi trường cần tái lập.
- Phát hiện và từ chối các truy cập xung đột không được bảo vệ.

Không phải lúc nào cũng cần tuần tự hóa toàn bộ. Mục tiêu là cho phép song song ở nơi an toàn và xác định rõ các điểm có thể ảnh hưởng kết quả quan sát.

## 10. Số học và khác biệt giữa môi trường

Một số phép tính tưởng như xác định có thể cho kết quả khác giữa nền tảng hoặc thứ tự thực hiện.

### Số dấu phẩy động

Số dấu phẩy động có độ chính xác hữu hạn. Phép cộng không luôn có tính kết hợp:

~~~text
(a + b) + c  may differ from  a + (b + c)
~~~

Vì vậy, nếu DSL cho phép cộng song song và gom nhóm theo thứ tự khác nhau, tổng cuối có thể lệch ở các chữ số cuối. Điều này đặc biệt quan trọng với tính tiền, tỷ lệ và các phép tổng hợp lớn.

Với miền tài chính, thường nên dùng kiểu số thập phân có quy tắc làm tròn rõ ràng hoặc kiểu tiền tệ chuyên biệt thay vì dựa vào số nhị phân dấu phẩy động. Nếu vẫn dùng floating point, cần xác định độ chính xác, thứ tự phép tính và cách so sánh.

### Tràn số và độ rộng kiểu

Kiểu số nguyên có độ rộng cố định có thể tràn. Nếu runtime khác nhau xử lý tràn theo cách khác hoặc DSL không định nghĩa hành vi, tính xác định giữa môi trường bị ảnh hưởng. Nên quy định rõ tràn là wrap, saturate hay lỗi.

### Thời gian và múi giờ

Một ngày lịch không luôn tương ứng 24 giờ do quy tắc múi giờ và thay đổi giờ mùa hè ở một số vùng. DSL xử lý thời hạn nên phân biệt instant, local date-time, date và duration; không nên mặc định mọi phép cộng ngày/giờ đều có cùng ý nghĩa.

### Locale và định dạng

Phân tích số, ngày tháng hoặc chuỗi phụ thuộc locale có thể cho kết quả khác. Ví dụ dấu phẩy có thể là dấu thập phân trong một locale và dấu phân cách hàng nghìn trong locale khác. DSL nên dùng định dạng literal không phụ thuộc locale hoặc ghi rõ locale của tài liệu.

## 11. Ngữ nghĩa xác định cho rule engine

DSL dạng luật thường cần giải quyết xung đột, thứ tự kích hoạt và việc một luật có được kích hoạt lại hay không.

### Forward chaining và agenda

Trong forward chaining, engine xét các điều kiện dựa trên dữ kiện hiện tại và đưa các luật thỏa điều kiện vào một agenda. Khi một luật chạy, nó có thể thay đổi dữ kiện và làm các luật khác được kích hoạt.

Nếu nhiều luật cùng nằm trong agenda, engine cần chiến lược chọn luật tiếp theo. Các chiến lược có thể dựa trên priority, độ mới của dữ kiện, thứ tự kích hoạt hoặc thứ tự khai báo. Nếu tie-break không được xác định, hành vi có thể không ổn định.

### Salience và priority

Một luật có thể được gán mức ưu tiên:

~~~text
rule "fraud review" priority 100
    when order.riskScore >= 90 then holdOrder;

rule "standard approval" priority 10
    when order.paymentAccepted then approveOrder;
~~~

DSL cần quy định priority lớn hơn hay nhỏ hơn được chạy trước, cách xử lý khi bằng nhau và liệu một luật đã chạy có thể chạy lại sau khi dữ kiện thay đổi hay không.

### Chính sách kích hoạt lại

Một luật có thể:

- Chỉ chạy một lần cho mỗi sự kiện.
- Chạy mỗi khi điều kiện chuyển từ false sang true.
- Chạy mỗi khi điều kiện còn true sau một thay đổi dữ kiện.
- Chạy lại cho đến khi không còn luật nào có thể kích hoạt.

Những lựa chọn này có thể tạo ra số lần chạy và trạng thái cuối khác nhau. Đặc tả DSL phải nêu rõ điều kiện kích hoạt và cơ chế chống lặp.

### Chấm dứt và vòng lặp kích hoạt

Hai luật có thể kích hoạt lẫn nhau vô hạn:

~~~text
rule A when flagA then set flagB;
rule B when flagB then set flagA;
~~~

Nếu mỗi lần cập nhật đều tạo một sự kiện mới, engine có thể chạy mãi. Tính xác định không đồng nghĩa với việc chương trình chắc chắn kết thúc. DSL cần xác định giới hạn lượt, phát hiện chu kỳ, điều kiện hội tụ hoặc cơ chế dừng rõ ràng.

## 12. Determinism trong xử lý sự kiện và workflow

DSL mô tả sự kiện thường nhận các sự kiện đến từ nhiều nguồn. Thứ tự đến có thể khác thứ tự phát sinh hoặc thứ tự nghiệp vụ.

### Event ordering

Giả sử hệ thống nhận:

~~~text
PaymentAccepted(orderId)
OrderCancelled(orderId)
~~~

Nếu hai sự kiện đến gần như đồng thời, engine cần xác định cách xử lý. Có thể dùng sequence number, timestamp có nguồn tin cậy, phiên bản aggregate hoặc quy tắc ưu tiên nghiệp vụ. Chỉ dùng thời gian đến ở máy nhận có thể không phản ánh thứ tự sự kiện thực tế.

### Event time và processing time

- **Event time:** thời điểm sự kiện thực sự xảy ra theo nguồn phát.
- **Processing time:** thời điểm hệ thống xử lý sự kiện.

Hai thời điểm có thể khác nhau do mạng, hàng đợi hoặc retry. DSL phân tích dữ liệu luồng cần xác định cửa sổ thời gian dựa trên loại thời gian nào và cách xử lý sự kiện đến muộn.

### Event sourcing và replay

Nếu hệ thống lưu các sự kiện và tái phát lại để dựng trạng thái, handler cần có ngữ nghĩa xác định theo chuỗi sự kiện đã lưu. Nếu handler đọc thêm dữ liệu hiện tại từ dịch vụ ngoài trong lúc replay, kết quả lịch sử có thể thay đổi.

Để replay tái lập, nên lưu đủ dữ liệu cần thiết trong sự kiện hoặc snapshot, cố định phiên bản handler và cô lập các phụ thuộc bên ngoài. Các lệnh gửi ra ngoài trong lúc replay thường cần được vô hiệu hóa hoặc mô phỏng để tránh lặp tác dụng phụ.

## 13. Tác dụng phụ và thứ tự thực thi

Tác dụng phụ (*side effect*) là thay đổi hoặc tương tác có thể quan sát bên ngoài giá trị trả về của biểu thức. Ví dụ gồm ghi cơ sở dữ liệu, gửi email, gọi API, cập nhật trạng thái, ghi log kiểm toán hoặc phát sự kiện.

Khi một DSL cho phép biểu thức có tác dụng phụ, thứ tự đánh giá trở nên quan trọng.

Ví dụ:

~~~text
if reserveInventory(order) and chargePayment(order) then createShipment(order);
~~~

Nếu `reserveInventory` thành công nhưng `chargePayment` thất bại, hệ thống cần biết có hoàn tác việc giữ hàng hay không. Nếu đổi thứ tự hai thao tác, hành vi và rủi ro có thể khác.

### Tách biểu thức thuần và hành động

Một thiết kế thường giúp tăng tính xác định là tách:

- **Biểu thức thuần:** tính toán giá trị hoặc điều kiện từ dữ liệu đầu vào đã biết.
- **Hành động:** thực hiện tác dụng phụ theo thứ tự và hợp đồng đã định nghĩa.

Ví dụ:

~~~text
let canFulfill = inventory.available >= order.quantity
                 and payment.status == ACCEPTED;

if canFulfill then
    reserveInventory(order);
    capturePayment(order);
    createShipment(order);
~~~

Điều kiện được tính từ dữ liệu; các hành động có thứ tự tuần tự. Cách tách này giúp xác định điểm nào có thể đánh giá song song và điểm nào cần giao dịch hoặc bù trừ.

### Transaction và compensation

Nếu nhiều hành động phải thành công như một đơn vị, DSL có thể cung cấp khối transaction:

~~~text
transaction {
    reserveInventory(order);
    capturePayment(order);
    createShipment(order);
}
~~~

Nhưng transaction phân tán qua nhiều dịch vụ không tự động có tính nguyên tử như giao dịch cơ sở dữ liệu cục bộ. DSL cần quy định commit, rollback, retry và compensation. Nếu một bước không thể hoàn tác, cần mô tả cách khôi phục nghiệp vụ.

## 14. Tính xác định và truy vấn dữ liệu

Một DSL truy vấn cần xác định kết quả và thứ tự khi người dùng yêu cầu một tập kết quả.

### Thứ tự kết quả

Truy vấn:

~~~text
select order from Orders where order.status == PAID;
~~~

chỉ xác định tập đơn hàng thỏa điều kiện. Nếu không có yêu cầu sắp xếp, thứ tự kết quả có thể không được bảo đảm. Nếu người dùng cần kết quả ổn định, DSL nên yêu cầu hoặc mặc định một thứ tự rõ ràng.

~~~text
select order from Orders
where order.status == PAID
order by order.createdAt ascending, order.id ascending;
~~~

Khóa phụ `order.id` giúp phân biệt các đơn có cùng `createdAt`. Nếu chỉ sắp xếp theo thời gian và nhiều bản ghi có cùng giá trị, thứ tự giữa chúng vẫn có thể không xác định.

### Pagination

Phân trang bằng offset có thể trả kết quả khác nếu dữ liệu thay đổi giữa các lần truy vấn. Một DSL cần phân biệt phân trang trên snapshot cố định với phân trang trên dữ liệu đang thay đổi. Cursor dựa trên khóa sắp xếp ổn định có thể giảm vấn đề, nhưng vẫn cần xác định tính nhất quán dữ liệu.

### Aggregation song song

Một phép tổng hợp có thể được chia thành nhiều phần chạy song song. Nếu phép kết hợp không kết hợp được hoặc thứ tự gộp thay đổi kết quả, kết quả cuối có thể khác. Với số thực dấu phẩy động, tổng theo thứ tự khác có thể lệch. DSL nên định nghĩa kiểu số, phép kết hợp và mức độ bảo đảm chính xác.

## 15. Tính xác định trong sinh mã và build

Một DSL có thể sinh mã, cấu hình hoặc artifact. Tính xác định ở giai đoạn này có nghĩa cùng mô hình đầu vào và cùng cấu hình sinh tạo ra cùng artifact theo quy ước đã chọn.

Các nguồn gây khác biệt gồm:

- Thứ tự duyệt map hoặc tập hợp không có thứ tự.
- Timestamp hiện tại được chèn vào header.
- ID hoặc tên tạm được sinh ngẫu nhiên.
- Đường dẫn tuyệt đối phụ thuộc máy phát triển.
- Phiên bản thư viện hoặc compiler khác nhau.
- Locale, newline hoặc encoding khác nhau.
- Nội dung metadata phụ thuộc môi trường.

### Reproducible generation

Để tạo artifact tái lập:

- Sắp xếp các khai báo theo khóa ổn định khi thứ tự nguồn không có ý nghĩa.
- Không chèn timestamp hoặc đường dẫn máy cục bộ nếu không cần thiết.
- Cố định phiên bản compiler, plugin và dependency.
- Định nghĩa encoding, newline và formatter.
- Dùng ID ổn định thay cho UUID ngẫu nhiên nếu ID không cần ngẫu nhiên.
- Ghi lại cấu hình và phiên bản mô hình đầu vào.

Nếu thứ tự khai báo có ý nghĩa, không được sắp xếp lại chỉ để artifact giống nhau. Tính tái lập phải bảo toàn ngữ nghĩa DSL.

## 16. Ngữ nghĩa xác định và các mô hình không xác định có chủ đích

Không phải mọi DSL đều cần kết quả duy nhất. Một số lĩnh vực cần mô tả lựa chọn, tìm kiếm, tối ưu hóa, xác suất hoặc nhiều lịch thực thi hợp lệ.

Ví dụ:

- DSL lập lịch có thể cho phép nhiều lịch thỏa các ràng buộc.
- DSL truy vấn logic có thể trả về nhiều nghiệm.
- DSL tối ưu hóa có thể tìm một trong nhiều phương án có cùng chi phí.
- DSL mô phỏng có thể sử dụng biến ngẫu nhiên để mô hình hóa thế giới thực.
- DSL đồng thời có thể cho phép nhiều interleaving hợp lệ.

Trong các trường hợp này, bất định có thể là một phần chủ ý của ngữ nghĩa. Điều quan trọng là phải nói rõ chương trình trả về một nghiệm, tất cả nghiệm, một nghiệm theo thứ tự ưu tiên hay một nghiệm được chọn theo seed.

### Nondeterministic choice

Một cấu trúc như:

~~~text
choose one available route;
~~~

có thể cho phép runtime chọn bất kỳ tuyến nào trong tập hợp hợp lệ. Nếu người dùng cần kết quả ổn định, DSL có thể cung cấp tiêu chí:

~~~text
choose route with minimum estimatedCost;
tieBreak by route.id ascending;
~~~

Khi đó, việc chọn trở nên xác định nếu dữ liệu và tiêu chí so sánh đã được cố định.

### Kết quả là tập nghiệm

Một DSL logic có thể định nghĩa ngữ nghĩa trả về tập nghiệm thay vì một nghiệm duy nhất. Nếu tập nghiệm được xem là không có thứ tự, hai lần chạy có thể liệt kê nghiệm theo thứ tự khác nhau nhưng vẫn có cùng kết quả về mặt ngữ nghĩa. Nếu giao diện hoặc hệ thống downstream quan sát thứ tự, cần quy định cách sắp xếp.

## 17. Confluence và tính xác định

Trong hệ thống viết lại (*term rewriting system*), hai khái niệm **determinism** và **confluence** có liên hệ nhưng không đồng nghĩa.

- **Determinism:** tại một trạng thái, có tối đa một bước tiếp theo được phép theo quan hệ đánh giá đã chọn.
- **Confluence:** nếu từ một trạng thái có nhiều đường biến đổi khác nhau, các đường đó có thể tiếp tục hội tụ về một trạng thái chung.

Ví dụ, một hệ thống rewrite có thể cho phép áp dụng quy tắc A trước hoặc quy tắc B trước. Hệ thống không xác định ở từng bước vì có nhiều lựa chọn, nhưng vẫn có thể confluence nếu mọi đường đều dẫn đến cùng dạng chuẩn.

Nếu hệ thống rewrite vừa terminating vừa confluent, kết quả chuẩn cuối cùng thường không phụ thuộc thứ tự áp dụng các quy tắc. Đây là cách đạt kết quả cuối xác định dù quá trình trung gian có nhiều lựa chọn.

### Ví dụ khái niệm

~~~text
      term
      /  \
   stepA stepB
      \  /
    common
~~~

Sơ đồ cho thấy hai bước khác nhau có thể dẫn đến các trạng thái sau đó cùng hội tụ. Confluence hữu ích khi tối ưu hoặc chuẩn hóa cây, nhưng không tự động bảo đảm các tác dụng phụ trong lúc biến đổi là tương đương. Nếu rewrite chỉ thao tác trên biểu thức thuần và chỉ quan sát dạng chuẩn cuối, lập luận confluence có thể phù hợp hơn.

### Khi nào cần determinism, khi nào cần confluence?

- Dùng determinism khi cần biết chính xác bước tiếp theo, thứ tự rule hoặc lịch thực thi.
- Dùng confluence khi nhiều thứ tự biến đổi có thể được chấp nhận miễn là kết quả chuẩn cuối giống nhau.
- Dùng cả hai khi hệ thống cần vừa có bước xử lý duy nhất vừa bảo đảm kết quả cuối ổn định.

## 18. Các cách thiết kế DSL để tăng tính xác định

### Đưa phụ thuộc môi trường thành đầu vào tường minh

Thay vì để biểu thức tự đọc thời gian, locale hoặc cấu hình toàn cục, có thể đưa các giá trị đó vào context:

~~~text
evaluate OrderPolicy with {
    clock: fixedInstant("2026-11-15T09:00:00Z"),
    pricing: priceList(version = "2026-11"),
    locale: "vi-VN"
}
~~~

Cùng chương trình và cùng context sẽ có điều kiện tái lập rõ ràng hơn.

### Dùng dữ liệu snapshot hoặc phiên bản

Nếu chính sách dựa trên bảng giá, danh mục hoặc trạng thái tài khoản, nên xác định phiên bản dữ liệu hoặc snapshot được sử dụng. Điều này giúp giải thích tại sao một quyết định đã được đưa ra trong quá khứ.

### Quy định thứ tự một cách tường minh

Đối với rule, event, danh sách hoặc query, cần xác định thứ tự khai báo, priority, khóa sắp xếp hoặc chính sách tie-break. Tránh dựa vào thứ tự tình cờ của container hoặc runtime.

### Tách pure computation và effect

Đưa điều kiện và phép tính thuần vào phần có thể đánh giá độc lập. Tác dụng phụ nên nằm trong các action có thứ tự, giao dịch và hợp đồng lỗi rõ ràng.

### Hạn chế trạng thái dùng chung có thể thay đổi

Ưu tiên dữ liệu bất biến hoặc context riêng cho mỗi lần chạy. Nếu nhiều tác vụ cần cập nhật cùng trạng thái, dùng cơ chế đồng bộ hoặc transaction có quy tắc rõ ràng.

### Định nghĩa lỗi và retry

Quy định lỗi nào có thể retry, số lần retry, backoff, idempotency key và cách xử lý khi không biết dịch vụ ngoài đã hoàn tất thao tác hay chưa. Không để retry tự động làm thay đổi số lần tác dụng phụ mà người dùng quan sát.

## 19. Kiểm thử tính xác định

Tính xác định cần được kiểm tra bằng các thử nghiệm có cùng điều kiện đầu vào và bằng chứng về kết quả quan sát. Một lần chạy thành công không đủ để chứng minh hành vi ổn định.

### Repeated-run test

Chạy cùng chương trình nhiều lần với cùng snapshot dữ liệu, cấu hình, seed và clock. So sánh các kết quả theo tiêu chí đã chọn:

- Giá trị trả về.
- Trạng thái miền cuối.
- Trace sự kiện.
- Tác dụng phụ được ghi nhận.
- Mã lỗi và loại thất bại.

Nếu chỉ so sánh trạng thái cuối, có thể bỏ sót sự khác biệt trong thứ tự sự kiện hoặc log kiểm toán.

### Deterministic replay

Ghi lại đầu vào và các phụ thuộc bên ngoài trong một lần chạy. Sau đó phát lại cùng dữ liệu trong môi trường kiểm thử và xác nhận cùng trace hoặc kết quả. Cách này hữu ích với workflow, event processing và rule engine.

### Property-based testing

Sinh nhiều bộ đầu vào để kiểm tra các thuộc tính tổng quát. Ví dụ, với cùng context, đánh giá chính sách hai lần phải cho cùng kết quả; hoặc thay đổi thứ tự các phần tử trong một tập hợp được định nghĩa là không có thứ tự không được làm thay đổi quyết định.

### Differential testing

Chạy cùng chương trình trên hai backend hoặc hai phiên bản interpreter và so sánh kết quả. Điều này giúp phát hiện ngữ nghĩa khác nhau giữa môi trường, nhưng cần bảo đảm đầu vào và phụ thuộc được cố định.

### Concurrency stress test

Chạy nhiều lần với các lịch xen kẽ khác nhau, tải khác nhau và điểm đồng bộ khác nhau. Kiểm tra bất biến miền, trace và trạng thái cuối. Stress test có thể phát hiện race nhưng không chứng minh đã loại bỏ mọi lịch lỗi.

### Model checking và exhaustive exploration

Với hệ thống nhỏ hoặc mô hình trạng thái hữu hạn, có thể liệt kê các trạng thái và lịch thực thi hợp lệ để tìm đường dẫn tạo kết quả khác nhau hoặc vi phạm bất biến. Cách này mạnh hơn kiểm thử ngẫu nhiên nhưng chi phí tăng nhanh theo số trạng thái.

## 20. Ví dụ kiểm thử tính xác định cho DSL chính sách

Giả sử DSL tính mức giảm giá cho đơn hàng. Chính sách ban đầu:

~~~text
rule "gold tier" priority 10
    when customer.tier == GOLD then discount 10%;

rule "large order" priority 10
    when order.total >= 5000000 then discount 8%;
~~~

Đầu vào có thể thỏa cả hai quy tắc. Nếu DSL chưa định nghĩa cách xử lý hai rule cùng priority, kết quả có thể phụ thuộc thứ tự duyệt.

### Bổ sung quy tắc xung đột

Ví dụ, đặc tả quy định chỉ áp dụng mức giảm cao nhất và tie-break bằng ID quy tắc:

~~~text
discountPolicy OrderDiscount {
    selection: maximumDiscount;
    tieBreak: ruleId ascending;
}
~~~

Khi cùng đầu vào và cùng tập quy tắc, kết quả chọn sẽ ổn định nếu ID là duy nhất và phép tính giảm giá được xác định.

### Kịch bản kiểm thử

| Đầu vào | Điều kiện khớp | Kết quả mong đợi |
|---|---|---|
| Khách GOLD, đơn 2 triệu | Chỉ `gold tier` | Giảm 10%. |
| Khách thường, đơn 6 triệu | Chỉ `large order` | Giảm 8%. |
| Khách GOLD, đơn 6 triệu | Cả hai quy tắc | Chọn 10% theo maximum discount. |
| Cả hai cùng cho 10% | Hai rule cùng mức giảm | Chọn theo `ruleId ascending`. |
| Không có rule khớp | Không rule nào áp dụng | Không giảm giá. |

### Kiểm tra lặp

Với cùng customer, order, phiên bản chính sách và snapshot dữ liệu, chạy đánh giá nhiều lần và xác nhận:

- Cùng rule được chọn.
- Cùng mức giảm được tính.
- Cùng mã giải thích hoặc decision trace được tạo.
- Không có phụ thuộc vào thứ tự vật lý của map hoặc tập hợp chứa rule.

## 21. Ví dụ về thời gian và môi trường thực thi

Xét chính sách:

~~~text
if order.createdAt < now() - 30 days then markOverdue;
~~~

Hai lần chạy cách nhau vài phút có thể cho kết quả khác nếu đơn nằm gần ngưỡng 30 ngày. Đây không nhất thiết là lỗi; chính sách phụ thuộc thời gian hiện tại theo chủ đích.

Nếu cần kiểm thử tái lập, có thể truyền clock:

~~~text
evaluate OverduePolicy with {
    now: instant("2026-11-15T00:00:00Z"),
    timezone: "Asia/Ho_Chi_Minh"
}
~~~

Khi clock và timezone được cố định, cùng `createdAt` sẽ được đánh giá nhất quán. Trong môi trường thực tế, runtime có thể cung cấp clock hệ thống; nhưng lần chạy cần lưu giá trị thực tế đã dùng nếu muốn tái lập quyết định sau này.

## 22. Xử lý bất định có chủ đích

Nếu DSL hỗ trợ ngẫu nhiên hoặc nhiều nghiệm, không nên che giấu sự bất định. Hãy làm cho nó rõ ràng trong cú pháp và kết quả.

### Seed tường minh

~~~text
simulation RunA {
    randomSeed: 481516;
    run 1000 iterations;
}
~~~

Seed cho phép tái lập chuỗi số ngẫu nhiên nếu thuật toán và phiên bản runtime cũng được cố định.

### Trả về nhiều kết quả

~~~text
routes = find all routes where
    route.cost <= budget
    and route.arrivalTime <= deadline;
~~~

DSL có thể trả về một tập nghiệm. Nếu thứ tự không có ý nghĩa, kết quả nên được so sánh như tập hợp. Nếu người dùng cần danh sách ổn định, hãy thêm `order by` với khóa phụ đủ phân biệt.

### Chọn nghiệm theo tiêu chí

~~~text
route = choose route minimizing cost
    tieBreak by arrivalTime ascending, route.id ascending;
~~~

Việc đưa tiêu chí lựa chọn vào chương trình giúp biến một lựa chọn không xác định thành một quyết định xác định trong cùng điều kiện.

## 23. Đặc tả tính xác định trong tài liệu ngôn ngữ

Tính xác định cần được mô tả như một phần của đặc tả ngữ nghĩa, không chỉ là một thuộc tính ngầm trong code runtime.

Các nội dung nên xác định:

1. **Đầu vào đầy đủ:** dữ liệu, trạng thái, context, phiên bản, clock, seed và phụ thuộc ngoài nào ảnh hưởng đánh giá.
2. **Thứ tự đánh giá:** biểu thức, toán tử logic, câu lệnh, rule, event và các bước workflow.
3. **Thứ tự duyệt:** collection nào có thứ tự, collection nào không, cách sắp xếp khi cần ổn định.
4. **Giải quyết xung đột:** priority, tie-break, apply-all, first-match hoặc lỗi khi có xung đột.
5. **Đồng thời:** tác vụ nào có thể chạy song song, thứ tự commit, đồng bộ và cách xử lý race.
6. **Tác dụng phụ:** thứ tự gọi, transaction, rollback, compensation và retry.
7. **Thời gian và ngẫu nhiên:** clock, timezone, seed và thuật toán.
8. **Số học:** kiểu số, độ chính xác, tràn số, làm tròn và đơn vị.
9. **Lỗi:** điều kiện phát sinh, thứ tự chọn lỗi, khả năng retry và trạng thái sau thất bại.
10. **Kết quả quan sát:** giá trị, trạng thái, trace, sự kiện và các tác dụng phụ được xem là một phần của ngữ nghĩa.

Nếu một hành vi không được bảo đảm, tài liệu nên nói rõ hành vi đó là không xác định, phụ thuộc triển khai hay được phép thay đổi. Không nên để người dùng suy luận từ một lần chạy tình cờ.

## 24. Những sai lầm thường gặp

**Cho rằng cùng mã nguồn luôn cho cùng kết quả.** Dữ liệu, clock, seed, cấu hình và dịch vụ ngoài cũng là một phần của điều kiện đánh giá.

**Nhầm tính xác định với tính lũy đẳng.** Một thao tác tăng bộ đếm có thể xác định nhưng không lũy đẳng; hai khái niệm giải quyết vấn đề khác nhau.

**Dựa vào thứ tự của map hoặc set.** Nếu thứ tự không được cam kết, dùng nó để chọn rule hoặc phát sự kiện có thể tạo kết quả khác nhau.

**Không định nghĩa tie-break.** Hai quy tắc cùng priority hoặc hai bản ghi cùng khóa sắp xếp có thể được chọn theo thứ tự tình cờ.

**Coi chạy song song luôn an toàn.** Hai tác vụ cùng cập nhật trạng thái có thể tạo race condition và vi phạm bất biến.

**Tái sắp xếp biểu thức có tác dụng phụ.** Các phép biến đổi logic hoặc số học chỉ an toàn khi ngữ nghĩa và tính thuần cho phép.

**Không cố định phụ thuộc ngoài khi replay.** Đọc lại API hiện tại trong lúc tái phát sự kiện lịch sử có thể tạo kết quả khác lần đầu.

**Bỏ qua khác biệt số học và locale.** Floating point, timezone, định dạng số và làm tròn có thể làm thay đổi kết quả giữa môi trường.

**Cho rằng confluence đồng nghĩa với determinism.** Nhiều đường biến đổi có thể hội tụ về cùng dạng chuẩn dù từng bước vẫn có nhiều lựa chọn.

**Chỉ kiểm tra trạng thái cuối.** Trace sự kiện, thứ tự tác dụng phụ và lỗi cũng có thể là kết quả quan sát được.

**Để hành vi không xác định mà không tài liệu hóa.** Người dùng sẽ phụ thuộc vào hành vi tình cờ của một runtime và gặp lỗi khi nâng cấp.

## 25. Quy trình thiết kế và triển khai tính xác định

Một quy trình thực tế có thể thực hiện như sau:

1. **Xác định quan sát:** quyết định những gì được xem là kết quả — giá trị, trạng thái, sự kiện, lỗi hay toàn bộ trace.
2. **Xác định đầu vào đầy đủ:** liệt kê dữ liệu, context, clock, seed, phiên bản và phụ thuộc môi trường.
3. **Đặc tả cú pháp và phân giải:** bảo đảm ngữ pháp, độ ưu tiên, phạm vi và quy tắc tên không mơ hồ.
4. **Đặc tả thứ tự đánh giá:** quy định thứ tự biểu thức, collection, rule, workflow và event.
5. **Thiết kế giải quyết xung đột:** chọn priority, tie-break, first-match, apply-all hoặc phát hiện xung đột.
6. **Kiểm soát trạng thái và tác dụng phụ:** xác định transaction, thứ tự hành động, retry, rollback và compensation.
7. **Thiết kế đồng thời:** xác định tác vụ độc lập, điểm đồng bộ và cơ chế bảo vệ trạng thái chia sẻ.
8. **Cố định các yếu tố biến thiên khi cần:** clock, seed, snapshot, timezone, locale và phiên bản phụ thuộc.
9. **Xây dựng kiểm thử tái lập:** repeated-run, replay, property-based, differential và concurrency tests.
10. **Quan sát và ghi dấu vết:** lưu context, phiên bản, decision trace và dữ liệu cần thiết để giải thích kết quả.
11. **Tài liệu hóa mức bảo đảm:** nêu rõ hành vi nào xác định, hành vi nào có thể không xác định và điều kiện áp dụng.

Không phải mọi DSL đều cần loại bỏ tất cả bất định. Với DSL mô phỏng hoặc tìm kiếm, tính không xác định có thể là một tính năng. Khi đó, nhiệm vụ thiết kế là xác định ranh giới và cách quan sát sự lựa chọn, đồng thời cung cấp phương thức tái lập khi cần.

## 26. Mẫu checklist đặc tả ngữ nghĩa xác định

Có thể dùng các câu hỏi sau khi viết đặc tả hoặc xem xét một cấu trúc mới của DSL:

- Cùng chương trình, cùng dữ liệu và cùng context có tạo cùng kết quả không?
- Những phụ thuộc ngầm nào có thể thay đổi giữa hai lần chạy?
- Thứ tự đánh giá toán tử và biểu thức đã rõ chưa?
- Collection nào có thứ tự và collection nào không?
- Khi nhiều rule cùng khớp, cách chọn đã được định nghĩa chưa?
- Khi nhiều tác vụ chạy song song, thứ tự commit hoặc kết quả gộp được xác định thế nào?
- Các thao tác có tác dụng phụ có được sắp thứ tự hoặc bảo vệ bằng transaction không?
- Retry có thể lặp tác dụng phụ không? Có idempotency key không?
- Clock, timezone, random seed và snapshot dữ liệu có được cung cấp hoặc ghi nhận không?
- Quy tắc số học, làm tròn và tràn số có ổn định giữa môi trường không?
- Khi có nhiều lỗi, cách chọn lỗi và trạng thái sau lỗi có rõ không?
- Kiểm thử có so sánh cả trace nếu thứ tự sự kiện quan trọng không?
- Người dùng có thể tái lập một quyết định lịch sử từ dữ liệu và phiên bản đã lưu không?

## 27. Kết quả cần có sau khi xác định tính xác định

Một thiết kế DSL có xem xét đầy đủ tính xác định thường tạo ra:

- **Đặc tả đầu vào và môi trường:** dữ liệu, context, snapshot, clock, seed và phiên bản phụ thuộc.
- **Quy tắc đánh giá:** độ ưu tiên, tính kết hợp, thứ tự biểu thức, câu lệnh và tập hợp.
- **Chính sách rule và conflict resolution:** priority, tie-break, first-match, apply-all hoặc lỗi xung đột.
- **Mô hình đồng thời:** các tác vụ song song, đồng bộ, transaction và bảo vệ trạng thái.
- **Hợp đồng tác dụng phụ:** thứ tự hành động, retry, rollback, compensation và idempotency.
- **Định nghĩa kết quả quan sát:** giá trị, trạng thái, sự kiện, trace và lỗi.
- **Bộ kiểm thử xác định:** repeated-run, replay, property-based, differential và concurrency tests.
- **Thông tin truy vết:** phiên bản chương trình, dữ liệu, cấu hình và decision trace để tái lập kết quả.

Tính xác định giúp ngữ nghĩa DSL trở nên rõ ràng và có thể kiểm chứng. Khi người thiết kế định nghĩa đầy đủ đầu vào, thứ tự đánh giá, cách giải quyết xung đột, hành vi đồng thời và các yếu tố môi trường, người dùng có thể hiểu điều gì sẽ xảy ra trong cùng điều kiện. Với những miền cần ngẫu nhiên hoặc nhiều nghiệm, DSL vẫn có thể cho phép bất định có chủ đích, nhưng phải mô tả rõ phạm vi và cách tái lập. Điều quan trọng là hành vi của ngôn ngữ phải xuất phát từ quy tắc đã công bố, không phụ thuộc vào những chi tiết tình cờ của runtime.
