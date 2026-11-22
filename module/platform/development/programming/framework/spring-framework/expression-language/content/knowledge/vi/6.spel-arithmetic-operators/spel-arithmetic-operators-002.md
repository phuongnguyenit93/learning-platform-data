# Phép chia lấy dư và số mũ trong SpEL

SpEL cung cấp hai phép toán thường xuất hiện trong công thức và điều kiện: phép chia lấy dư và phép lũy thừa. Phép chia lấy dư dùng để xác định phần còn lại sau khi chia một số cho số khác; phép lũy thừa dùng để nâng một cơ số lên một số mũ. Trong SpEL, có thể viết phép chia lấy dư bằng ký hiệu % hoặc từ khóa mod, và viết phép lũy thừa bằng ký hiệu ^.

Hai phép toán này khá ngắn nhưng có một số điểm dễ nhầm: % là phép remainder theo quy tắc số học của kiểu số, không phải lúc nào cũng giống modulo luôn trả kết quả không âm; ^ trong SpEL là lũy thừa, khác ý nghĩa toán tử XOR của Java; và khi kết hợp với các phép toán khác, thứ tự ưu tiên cùng kiểu dữ liệu có thể ảnh hưởng kết quả.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Dùng % và mod để tính phần dư của phép chia.
- Dùng ^ để tính lũy thừa trong biểu thức SpEL.
- Phân biệt remainder với modulo toán học trong trường hợp số âm.
- Hiểu ý nghĩa của ^ trong SpEL và tránh nhầm với Java.
- Nhận biết ảnh hưởng của kiểu số, chuyển đổi kiểu và độ chính xác.
- Dùng dấu ngoặc để làm rõ thứ tự tính toán.
- Kiểm thử các trường hợp biên như chia cho 0, số âm, số mũ âm và số thập phân.

Bạn nên biết cách tạo SpelExpressionParser, parse một biểu thức và lấy kết quả bằng Expression.getValue(). Các ví dụ đầu tiên có thể chạy độc lập mà không cần Spring ApplicationContext.

## 2. Phép chia lấy dư: % và mod

Phép chia lấy dư trả về phần còn lại sau phép chia. Ví dụ, 17 chia cho 5 được 3 và còn dư 2:

~~~text
17 % 5
~~~

Kết quả là 2.

SpEL cũng hỗ trợ từ khóa mod để biểu diễn cùng phép toán:

~~~text
17 mod 5
~~~

Cả hai cách viết đều biểu diễn phép chia lấy dư. Ký hiệu % thường ngắn gọn, còn mod có thể dễ đọc hơn trong một biểu thức có nhiều ký hiệu toán học.

### 2.1. Ví dụ cơ bản

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("17 % 5");
Integer remainder = expression.getValue(Integer.class);
~~~

Kết quả là 2.

Một số ví dụ khác:

| Biểu thức | Kết quả | Giải thích |
|---|---:|---|
| 10 % 2 | 0 | 10 chia hết cho 2 |
| 10 % 3 | 1 | 3 nhân 3 bằng 9, còn 1 |
| 25 mod 4 | 1 | 4 nhân 6 bằng 24, còn 1 |
| 0 % 7 | 0 | 0 chia cho số khác 0 có phần dư 0 |
| 7 % 7 | 0 | Hai số bằng nhau nên chia hết |

Phép chia lấy dư hữu ích khi kiểm tra tính chẵn lẻ, chia nhóm tuần hoàn, xác định vị trí trong chu kỳ hoặc xử lý chỉ số theo vòng lặp.

### 2.2. Kiểm tra chẵn và lẻ

Một số nguyên chia cho 2 có phần dư bằng 0 nếu là số chẵn. Vì vậy:

~~~text
#number % 2 == 0
~~~

Biểu thức trên trả về true khi number là số chẵn.

Có thể dùng trong một điều kiện:

~~~text
#number % 2 == 0 ? 'EVEN' : 'ODD'
~~~

Nếu biến number là 9, kết quả là ODD; nếu number là 12, kết quả là EVEN.

Với số nguyên âm, cần nhớ phần dư có thể âm. Kiểm tra bằng 0 vẫn hoạt động để xác định chẵn lẻ:

~~~text
-8 % 2 == 0
~~~

Kết quả vẫn là true.

### 2.3. Remainder và modulo không hoàn toàn giống nhau

Trong giao tiếp hằng ngày, hai từ “phần dư” và “modulo” thường được dùng thay thế. Tuy nhiên, khi có số âm, cần phân biệt cách định nghĩa.

Phép remainder theo quy tắc phổ biến của Java giữ dấu của số bị chia. Ví dụ:

~~~text
-5 % 3
~~~

Kết quả là -2.

Trong khi đó, phép modulo theo quy ước toán học thường được định nghĩa để kết quả nằm trong một khoảng không âm khi chia cho số dương. Với cùng cặp số, modulo toán học có thể cho kết quả 1.

Do đó, nếu ứng dụng cần chỉ số vòng lặp luôn nằm trong khoảng từ 0 đến n-1, đừng mặc định % đáp ứng yêu cầu với số âm. Hãy chuẩn hóa đầu vào hoặc sử dụng một phép toán được định nghĩa rõ cho modulo không âm, chẳng hạn Math.floorMod trong Java khi context cho phép gọi method đó.

Ví dụ Java:

~~~java
int index = Math.floorMod(-5, 3); // 1
~~~

Điều quan trọng là xác định nghiệp vụ cần remainder hay modulo không âm, rồi kiểm thử rõ trường hợp số âm.

## 3. Phép lũy thừa: toán tử ^

SpEL dùng ký hiệu ^ để tính lũy thừa. Biểu thức:

~~~text
2 ^ 3
~~~

có nghĩa là 2 mũ 3, tức 2 × 2 × 2, kết quả là 8.

Đây là điểm dễ nhầm với Java: trong Java, toán tử ^ trên kiểu số nguyên là XOR theo bit. Trong SpEL, ^ là phép lũy thừa. Không chuyển trực tiếp ý nghĩa của toán tử từ ngôn ngữ Java sang cú pháp biểu thức SpEL.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("2 ^ 3");
Double result = expression.getValue(Double.class);
~~~

Với phép lũy thừa, kết quả thường được xử lý theo số học dấu phẩy động. Nếu cần kiểu kết quả cụ thể, hãy yêu cầu kiểu tường minh khi lấy giá trị và kiểm tra quy tắc chuyển đổi mà ứng dụng sử dụng.

### 3.1. Ví dụ cơ bản

| Biểu thức | Giá trị toán học |
|---|---:|
| 2 ^ 2 | 4 |
| 2 ^ 3 | 8 |
| 3 ^ 2 | 9 |
| 10 ^ 0 | 1 |
| 5 ^ 1 | 5 |
| 4 ^ 0.5 | 2 |

Số mũ bằng 0 thường cho kết quả 1 với cơ số khác 0. Số mũ bằng 1 giữ nguyên cơ số. Số mũ phân số có thể biểu diễn căn bậc tương ứng, ví dụ 4 mũ 0.5 là căn bậc hai của 4.

### 3.2. Dùng biến làm cơ số và số mũ

Trong ứng dụng, cơ số và số mũ thường là dữ liệu runtime:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#base ^ #exponent");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("base", 3);
context.setVariable("exponent", 4);

Double result = expression.getValue(context, Double.class);
~~~

Kết quả toán học là 81.

Việc dùng biến giúp tái sử dụng biểu thức với nhiều bộ dữ liệu. Không cần ghép giá trị vào chuỗi biểu thức; hãy truyền dữ liệu qua EvaluationContext để tránh lỗi định dạng và giảm nguy cơ biến input thành cú pháp ngoài dự kiến.

### 3.3. Số mũ âm và số mũ phân số

Số mũ âm biểu diễn nghịch đảo của lũy thừa dương:

~~~text
2 ^ -3
~~~

Giá trị toán học là 1/8, tức 0.125.

Số mũ phân số có thể tạo ra kết quả không phải số thực trong một số trường hợp. Ví dụ, lũy thừa phân số của một cơ số âm có thể không có kết quả thực. Các trường hợp như 0 mũ số âm cũng cần được kiểm soát theo quy tắc số học và kiểu kết quả được sử dụng.

Không nên giả định mọi biểu thức lũy thừa đều trả về một số hữu hạn. Hãy kiểm tra NaN, infinity, null hoặc exception tùy toán hạng và cách triển khai được sử dụng. Nếu kết quả được dùng trong tính tiền, lãi suất hoặc số liệu tài chính, cần chọn cách tính và quy tắc làm tròn phù hợp với yêu cầu nghiệp vụ.

## 4. Kết hợp phép chia lấy dư và số mũ

Có thể kết hợp % và ^ trong cùng biểu thức. Ví dụ:

~~~text
(2 ^ 5) % 7
~~~

Tính 2 mũ 5 trước, được 32; sau đó lấy 32 chia 7 còn dư 4.

Một ví dụ khác:

~~~text
(#base ^ #exponent) % #divisor
~~~

Biểu thức này có thể dùng trong một phép tính tuần hoàn, nhưng cần xác định rõ kiểu số và miền giá trị đầu vào. Nếu phép lũy thừa tạo ra số dấu phẩy động, phép chia lấy dư tiếp theo có thể không có ý nghĩa giống phép toán trên số nguyên. Khi cần remainder nguyên, hãy đảm bảo toán hạng là số nguyên phù hợp hoặc chuyển đổi theo quy tắc rõ ràng.

### 4.1. Dùng dấu ngoặc để thể hiện thứ tự

Khi kết hợp nhiều toán tử, nên nhóm các phần cần tính trước:

~~~text
(#base ^ #exponent) % #divisor
~~~

Không nên phụ thuộc vào việc người đọc nhớ thứ tự ưu tiên giữa ^, *, / và %. Dấu ngoặc giúp công thức thể hiện đúng ý định, đặc biệt khi có nhiều tầng phép toán.

Ví dụ tính phần dư sau khi cộng một lượng điều chỉnh:

~~~text
(#value + #offset) % #period
~~~

Nếu nghiệp vụ muốn cộng offset trước rồi mới lấy dư, nhóm phép cộng rõ ràng như trên.

### 4.2. Lũy thừa trong công thức nhiều bước

Giả sử cần tính một giá trị tăng theo hệ số lũy thừa:

~~~text
#principal * ((1 + #rate) ^ #periods)
~~~

Các bước:

1. Tính hệ số tăng trưởng 1 + rate.
2. Nâng hệ số lên số kỳ periods.
3. Nhân kết quả với principal.

Dấu ngoặc giúp nhìn rõ cơ số của phép lũy thừa và toàn bộ phần lũy thừa được nhân với principal. Với công thức tài chính thực tế, cần xác định lãi suất theo kỳ, cách làm tròn, kiểu số và các điều kiện đầu vào; biểu thức SpEL không tự xác định ý nghĩa nghiệp vụ đó.

## 5. Thứ tự ưu tiên và tính kết hợp

Trong SpEL, ^ là toán tử lũy thừa và có độ ưu tiên cao hơn nhóm nhân/chia/chia dư. Nhóm nhân, chia và chia lấy dư được xử lý trước nhóm cộng/trừ. Tuy vậy, khi biểu thức có nhiều toán tử, dùng ngoặc là cách rõ ràng nhất để thể hiện ý định.

Ví dụ:

~~~text
2 + 3 ^ 2
~~~

Phép lũy thừa được tính trước, nên kết quả là 11.

~~~text
(2 + 3) ^ 2
~~~

Dấu ngoặc buộc phép cộng thực hiện trước, kết quả là 25.

Tính kết hợp cũng quan trọng khi có nhiều toán tử cùng mức ưu tiên. Không nên viết một chuỗi phép tính dài rồi suy luận theo cách đọc tự nhiên. Hãy nhóm rõ các phần, đặc biệt với phép trừ, chia và các công thức có số mũ.

## 6. Kiểu dữ liệu và độ chính xác

SpEL làm việc với các kiểu số Java như Integer, Long, Float, Double, BigInteger và BigDecimal tùy toán hạng, operator và conversion service. Kiểu kết quả có thể khác kiểu đầu vào, đặc biệt với phép lũy thừa.

Một số nguyên tắc thực hành:

- Dùng số nguyên cho phép chia lấy dư khi cần kiểm tra chia hết, chẵn lẻ hoặc phân nhóm theo chỉ số.
- Dùng Double hoặc kiểu dấu phẩy động phù hợp khi phép lũy thừa có số mũ phân số.
- Không so sánh số dấu phẩy động bằng phép bằng tuyệt đối nếu kết quả có sai số biểu diễn; cân nhắc epsilon hoặc cách so sánh phù hợp.
- Với tiền tệ và số thập phân cần độ chính xác thập phân, dùng BigDecimal trong Java và quy định rõ scale/rounding.
- Kiểm tra kiểu kết quả bằng getValue(context, TargetType.class) và xử lý conversion failure.
- Không ép kiểu một cách mù quáng nếu biểu thức có thể trả về NaN hoặc infinity.

Ví dụ phép chia lấy dư trên số nguyên:

~~~java
Expression expression =
    parser.parseExpression("#amount % #unit");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("amount", 29);
context.setVariable("unit", 6);

Integer remainder = expression.getValue(context, Integer.class);
~~~

Kết quả là 5.

Nếu toán hạng có kiểu khác nhau, SpEL có thể thực hiện chuyển đổi để tìm phép toán phù hợp. Hãy tránh trộn kiểu tùy tiện trong cùng một biểu thức; giữ kiểu dữ liệu nhất quán làm cho kết quả dễ dự đoán hơn.

## 7. Các trường hợp biên cần xử lý

### 7.1. Chia lấy dư cho 0

Phép chia lấy dư với số chia bằng 0 không hợp lệ. Không nên dựa vào việc runtime sẽ tự xử lý theo một cách cụ thể. Hãy kiểm tra divisor trước khi đánh giá:

~~~text
#divisor != 0 ? (#value % #divisor) : 0
~~~

Giá trị mặc định 0 trong ví dụ chỉ để minh họa cú pháp; nghiệp vụ thực tế có thể cần trả lỗi validation thay vì thay thế bằng 0.

### 7.2. Cơ số bằng 0 và số mũ âm

Biểu thức có cơ số 0 và số mũ âm không có giá trị hữu hạn theo số học thông thường. Hãy kiểm tra cặp đầu vào này trước khi tính toán và xác định rõ chính sách lỗi.

### 7.3. Cơ số âm và số mũ phân số

Một cơ số âm với số mũ phân số có thể không có kết quả thực. Nếu kết quả phải là số thực, hãy xác thực miền đầu vào hoặc định nghĩa quy tắc xử lý. Không để NaN hoặc infinity âm thầm lan sang điều kiện hoặc dữ liệu lưu trữ.

### 7.4. Số rất lớn

Lũy thừa có thể làm giá trị tăng rất nhanh. Với số mũ lớn, kết quả có thể vượt phạm vi kiểu dữ liệu hoặc trở thành infinity ở kiểu dấu phẩy động. Hãy giới hạn miền đầu vào và kiểm tra kết quả trước khi sử dụng.

### 7.5. Số âm trong phép chia lấy dư

Nếu dùng % để tạo chỉ số vòng lặp, số âm có thể cho phần dư âm. Hãy kiểm thử các đầu vào âm và chọn quy tắc modulo phù hợp với nghiệp vụ thay vì giả định kết quả luôn không âm.

## 8. Ứng dụng thực tế

### 8.1. Kiểm tra chia hết

~~~text
#recordCount % #batchSize == 0
~~~

Có thể dùng để kiểm tra số bản ghi có chia hết thành các batch bằng nhau hay không. Trước khi đánh giá, cần bảo đảm batchSize khác 0 và là số nguyên dương nếu nghiệp vụ yêu cầu.

### 8.2. Phân nhóm theo chu kỳ

~~~text
#sequence % 7
~~~

Có thể xác định vị trí trong chu kỳ bảy phần tử nếu sequence là số không âm. Nếu sequence có thể âm, hãy chuẩn hóa đầu vào hoặc dùng phép modulo phù hợp.

### 8.3. Tính lũy thừa

~~~text
#base ^ #exponent
~~~

Có thể biểu diễn hệ số tăng trưởng, công thức khoa học hoặc một quy tắc cấu hình. Với công thức lớn hoặc cần độ chính xác nghiêm ngặt, cân nhắc thực hiện trong Java để quản lý kiểu số, làm tròn và kiểm tra miền giá trị tập trung hơn.

### 8.4. Kết hợp điều kiện và phép toán

~~~text
#enabled and #divisor > 0 and (#value % #divisor == 0)
~~~

Biểu thức trên yêu cầu tính năng được bật, divisor hợp lệ và value chia hết cho divisor. Dùng ngoặc quanh phép remainder và phép so sánh giúp người đọc nhận diện rõ điều kiện.

## 9. Debug biểu thức số học

Khi kết quả không như dự kiến, chia biểu thức thành các phần:

1. Kiểm tra từng biến có tồn tại và có kiểu đúng không.
2. Đánh giá riêng phép lũy thừa.
3. Đánh giá riêng phép chia lấy dư.
4. Kiểm tra kiểu kết quả sau từng phép toán.
5. Thêm lại các toán tử logic hoặc ternary sau cùng.

Ví dụ, với:

~~~text
((#base ^ #exponent) % #divisor) == #expected
~~~

Hãy kiểm tra #base ^ #exponent trước, sau đó kiểm tra kết quả remainder, cuối cùng mới so sánh với expected. Cách này giúp phân biệt lỗi dữ liệu, lỗi kiểu, lỗi chia cho 0 và lỗi grouping.

Khi parse thất bại, kiểm tra cú pháp và ký hiệu. Khi parse thành công nhưng evaluate thất bại, kiểm tra giá trị runtime, kiểu toán hạng, biến trong context và các trường hợp biên.

## 10. Kiểm thử

Tạo các test cho cả trường hợp thông thường và biên:

| Nhóm | Đầu vào | Điều cần xác nhận |
|---|---|---|
| Remainder | 17 và 5 | Kết quả là 2 |
| Chia hết | 18 và 3 | Kết quả là 0 |
| Số âm | -5 và 3 | Xác nhận quy tắc dấu của remainder |
| Số chia bằng 0 | 5 và 0 | Ứng dụng xử lý lỗi theo chính sách |
| Lũy thừa | 2 và 3 | Kết quả toán học là 8 |
| Số mũ bằng 0 | 5 và 0 | Kết quả là 1 |
| Số mũ âm | 2 và -3 | Kiểm tra kết quả phân số và kiểu |
| Số mũ phân số | 4 và 0.5 | Kết quả toán học là 2 |
| Cơ số âm, số mũ phân số | -4 và 0.5 | Kiểm tra miền kết quả không thực |
| Số rất lớn | Cơ số/số mũ lớn | Kiểm tra overflow, infinity hoặc giới hạn |

Một test nên xác nhận cả giá trị trả về và kiểu kết quả. Đặc biệt, đừng chỉ kiểm tra biểu thức bằng một cặp số dương nhỏ; các lỗi thường xuất hiện ở số âm, divisor bằng 0 và giá trị vượt phạm vi.

## 11. An toàn và bảo trì

Phép toán số học tự thân thường ít quyền hơn gọi method hoặc truy cập bean, nhưng một biểu thức vẫn có thể chứa các thành phần khác. Nếu chuỗi biểu thức đến từ nguồn không tin cậy, đừng đánh giá nó bằng EvaluationContext toàn quyền.

- Giới hạn biểu thức vào một tập toán tử và biến được phép nếu người dùng có thể tự định nghĩa công thức.
- Kiểm tra kiểu và miền giá trị của mọi biến trước khi đánh giá.
- Giới hạn số mũ và kích thước số để tránh tính toán quá tốn tài nguyên.
- Không dựa vào biểu thức để thay thế validation nghiệp vụ.
- Dùng dấu ngoặc và tên biến có ý nghĩa để người bảo trì hiểu rõ công thức.
- Chuyển công thức dài hoặc yêu cầu xử lý lỗi phức tạp về Java để có thể kiểm thử theo từng bước.

## 12. Bài tập thực hành

1. Viết biểu thức kiểm tra một số nguyên là chẵn hay lẻ bằng %.
2. Viết biểu thức tính 3 mũ 4 bằng ^ và xác nhận kết quả.
3. So sánh 2 + 3 ^ 2 với (2 + 3) ^ 2.
4. Dùng biến trong EvaluationContext để tính #base ^ #exponent.
5. Thử -5 % 3 và giải thích vì sao không nên mặc định phần dư luôn không âm.
6. Viết biểu thức bảo vệ phép chia lấy dư khi divisor bằng 0.
7. Viết test cho số mũ âm, số mũ phân số và giá trị lũy thừa rất lớn.
8. Xây dựng một biểu thức kết hợp lũy thừa, remainder và so sánh; dùng ngoặc để thể hiện rõ thứ tự.

## 13. Checklist trước khi dùng trong ứng dụng

- [ ] Đã xác định cần remainder hay modulo không âm chưa?
- [ ] Đã kiểm tra divisor khác 0 chưa?
- [ ] Đã kiểm tra dấu của các toán hạng chưa?
- [ ] Đã hiểu ^ trong SpEL là lũy thừa, không phải XOR của Java chưa?
- [ ] Đã xác định kiểu kết quả mong đợi chưa?
- [ ] Đã kiểm tra số mũ âm, số mũ phân số và cơ số âm chưa?
- [ ] Đã giới hạn giá trị đầu vào để tránh kết quả quá lớn chưa?
- [ ] Đã dùng dấu ngoặc khi biểu thức có nhiều toán tử chưa?
- [ ] Đã kiểm thử kết quả và kiểu của biểu thức chưa?
- [ ] Đã giới hạn quyền EvaluationContext nếu biểu thức không hoàn toàn tin cậy chưa?

## 14. Kết luận

Trong SpEL, % hoặc mod dùng để lấy phần dư sau phép chia, còn ^ dùng để tính lũy thừa. Cần đặc biệt chú ý dấu của phần dư khi có số âm và ý nghĩa riêng của ^ so với Java. Khi kết hợp các phép toán, hãy dùng dấu ngoặc, giữ kiểu dữ liệu nhất quán, kiểm tra các trường hợp biên và xác định rõ miền giá trị nghiệp vụ.