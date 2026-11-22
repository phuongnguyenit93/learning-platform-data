# Toán tử matches với biểu thức chính quy

## Mục tiêu

Toán tử **matches** trong Spring Expression Language (SpEL) kiểm tra một chuỗi có khớp với một biểu thức chính quy hay không. Kết quả là Boolean, vì vậy toán tử này thường được dùng để xác thực định dạng, phân loại mã, kiểm tra quy tắc đầu vào hoặc kết hợp với các điều kiện nghiệp vụ khác.

Sau bài này, bạn có thể:

- Viết cú pháp matches với chuỗi và regular expression.
- Hiểu cách SpEL sử dụng Java regular expression và quy tắc khớp toàn bộ chuỗi.
- Chọn character class, quantifier, group và alternation phù hợp.
- Kết hợp matches với biến, property, điều kiện null và toán tử logic.
- Tránh lỗi do kiểu dữ liệu, escaping và pattern quá phức tạp.
- Kiểm thử trường hợp hợp lệ, không hợp lệ và các giá trị biên.

## 1. Cú pháp cơ bản

Cú pháp của toán tử:

~~~text
stringExpression matches 'regular-expression'
~~~

Vế trái phải đánh giá thành chuỗi cần kiểm tra. Vế phải là chuỗi chứa regular expression. Toán tử trả về Boolean:

- **true** nếu toàn bộ chuỗi đầu vào khớp với pattern.
- **false** nếu chuỗi không khớp.

Ví dụ:

~~~text
'12345' matches '[0-9]{5}'
'AB-1234' matches '[A-Z]{2}-[0-9]{4}'
'hello' matches '[a-z]+'
~~~

Cả ba ví dụ đều trả về true. Ví dụ đầu yêu cầu đúng năm chữ số; ví dụ thứ hai yêu cầu hai chữ cái in hoa, dấu gạch nối và bốn chữ số; ví dụ cuối yêu cầu một hoặc nhiều chữ cái thường.

**matches kiểm tra toàn bộ chuỗi**, tương ứng với thao tác match toàn bộ của Java regular expression. Pattern **[0-9]{5}** không chấp nhận chuỗi **Code 12345**, dù bên trong có một đoạn gồm năm chữ số. Muốn cho phép tiền tố hoặc hậu tố, hãy đưa chúng vào pattern một cách tường minh, hoặc dùng cơ chế tìm kiếm một phần chuỗi ở Java nếu đó mới là mục đích.

Có thể viết thêm dấu neo **^** và **$** để làm rõ ý định:

~~~text
'12345' matches '^[0-9]{5}$'
~~~

Với toán tử matches, việc khớp toàn bộ chuỗi đã được yêu cầu; dấu neo vẫn hữu ích khi người đọc quen với cú pháp regular expression và muốn thể hiện rõ ranh giới mong đợi.

## 2. SpEL sử dụng Java regular expression

SpEL dùng cú pháp regular expression của Java, được cung cấp bởi lớp Pattern trong package java.util.regex. Vì vậy, các quy tắc về character class, quantifier, group, alternation và flag của Java Pattern cũng áp dụng cho toán tử matches.

Một số thành phần thường gặp:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **[0-9]** | Một chữ số từ 0 tới 9 | **[0-9]{4}** |
| **[A-Z]** | Một chữ cái in hoa ASCII | **[A-Z]+** |
| **[a-z]** | Một chữ cái thường ASCII | **[a-z]+** |
| **[A-Za-z]** | Một chữ cái hoa hoặc thường ASCII | **[A-Za-z]+** |
| **.** | Một ký tự bất kỳ, ngoại trừ line terminator theo chế độ mặc định | **A.B** |
| **+** | Một hoặc nhiều lần | **[0-9]+** |
| **\*** | Không hoặc nhiều lần | **[A-Z]\*** |
| **?** | Không hoặc một lần | **colou?r** |
| **{n}** | Chính xác n lần | **[0-9]{6}** |
| **{m,n}** | Từ m tới n lần | **[A-Z]{2,4}** |
| **(...)** | Nhóm các thành phần | **(AB)** |
| **^ và $** | Neo đầu và cuối chuỗi trong regex | **^[A-Z]+$** |

Dấu gạch đứng trong regex biểu diễn alternation, tức lựa chọn giữa các nhánh. Ví dụ **(red|blue)** chấp nhận một trong hai từ. Các dấu như dấu chấm, ngoặc, dấu cộng và dấu sao có ý nghĩa đặc biệt. Nếu muốn coi chúng là ký tự thông thường, cần escape theo cú pháp Java Pattern hoặc đặt trong character class phù hợp.

### Character class

Character class mô tả một ký tự thuộc một tập cho trước:

~~~text
[A-Z]
[a-z]
[0-9]
[A-F0-9]
~~~

Có thể kết hợp các dải ký tự:

~~~text
[A-Za-z0-9]
~~~

Pattern trên chấp nhận chữ cái ASCII và chữ số. Nó không tự động bao gồm mọi chữ cái có dấu trong các ngôn ngữ khác. Nếu nghiệp vụ cần hỗ trợ Unicode, hãy chọn pattern và chính sách Unicode phù hợp thay vì giả định **[A-Za-z]** bao phủ mọi tên người hoặc văn bản quốc tế.

### Quantifier

Quantifier xác định số lần một thành phần xuất hiện:

~~~text
[0-9]{5}
[A-Z]{2,4}
[A-Za-z0-9]+
~~~

- **[0-9]{5}** yêu cầu đúng năm chữ số.
- **[A-Z]{2,4}** yêu cầu từ hai tới bốn chữ cái in hoa.
- **[A-Za-z0-9]+** yêu cầu ít nhất một chữ cái ASCII hoặc chữ số.

Chọn giới hạn có ý nghĩa nghiệp vụ. Pattern **[0-9]+** chấp nhận chuỗi dài tùy ý, trong khi mã bưu chính, mã đơn hàng hoặc mã chi nhánh thường có độ dài quy định rõ.

### Group và alternation

Ngoặc tròn nhóm các thành phần, còn dấu gạch đứng biểu diễn lựa chọn:

~~~text
(AB|CD)-[0-9]{4}
~~~

Pattern chấp nhận mã bắt đầu bằng AB hoặc CD, theo sau là dấu gạch nối và bốn chữ số. Có thể kết hợp nhiều group, nhưng nên giữ cấu trúc dễ đọc và tránh lồng quá sâu.

### Flag

Java Pattern hỗ trợ flag để thay đổi cách so khớp. Ví dụ, flag inline **(?i)** làm cho phần pattern theo sau không phân biệt chữ hoa và chữ thường:

~~~text
'Spring' matches '(?i)spring'
~~~

Chỉ bật flag khi nghiệp vụ yêu cầu. Nếu so khớp cần phân biệt hoa/thường, không thêm **(?i)** chỉ để làm pattern dễ khớp hơn.

## 3. Ví dụ kiểm tra định dạng

### Mã gồm hai chữ cái và bốn chữ số

~~~text
'AB-1234' matches '[A-Z]{2}-[0-9]{4}'
~~~

Kết quả là true. Những giá trị như **ab-1234**, **ABC-1234**, **AB1234** hoặc **AB-123** không khớp vì khác chữ hoa/thường, độ dài hoặc dấu phân cách.

### Mã gồm đúng sáu chữ số

~~~text
'012345' matches '[0-9]{6}'
~~~

Kết quả là true. Số 0 ở đầu được giữ lại vì đầu vào là chuỗi. Nếu chuyển mã sang kiểu số trước khi kiểm tra, số 0 đầu có thể bị mất; mã định danh thường nên được xử lý dưới dạng String.

### Username đơn giản

~~~text
'lan_2026' matches '[A-Za-z][A-Za-z0-9_]{2,19}'
~~~

Pattern yêu cầu ký tự đầu là chữ cái ASCII, sau đó có từ hai tới mười chín chữ cái, chữ số hoặc dấu gạch dưới. Tổng chiều dài vì thế nằm trong khoảng từ ba tới hai mươi ký tự.

Đây chỉ là một quy tắc username mẫu. Quy định thực tế có thể cần cho phép dấu gạch ngang, Unicode hoặc các ký tự khác. Hãy xác định chính sách trước khi chọn pattern.

### Mã có một trong hai tiền tố

~~~text
'INV-2026-0012' matches '(INV|ORD)-[0-9]{4}-[0-9]{4}'
~~~

Pattern chấp nhận tiền tố INV hoặc ORD, năm gồm bốn chữ số và phần số thứ tự gồm bốn chữ số. Nếu có nhiều loại mã, alternation giúp thể hiện các lựa chọn được phép trong cùng một pattern.

### Kiểm tra khoảng trắng

~~~text
'Hello World' matches '[A-Za-z]+[ ][A-Za-z]+'
~~~

Pattern này chấp nhận đúng hai nhóm chữ cái ASCII, ngăn cách bằng một dấu cách. Nó không chấp nhận nhiều khoảng trắng, tab hoặc nhiều từ. Nếu cần các loại khoảng trắng khác, hãy chọn character class tương ứng của Java Pattern và kiểm thử dữ liệu thực tế.

## 4. Dùng matches với root object và biến

Vế trái của matches có thể là property của root object hoặc một biến trong EvaluationContext.

Ví dụ với biến:

~~~text
#postalCode matches '[0-9]{5}'
~~~

Ví dụ với property:

~~~text
customer.code matches '[A-Z]{2}-[0-9]{4}'
~~~

Ví dụ với một đối tượng được truyền vào làm root:

~~~java
public class Customer {
    private String code;

    public String getCode() {
        return code;
    }
}
~~~

Biểu thức **code matches '[A-Z]{2}-[0-9]{4}'** đọc property code của root Customer rồi kiểm tra định dạng.

Cách đánh giá bằng Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#postalCode matches '[0-9]{5}'");

SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("postalCode", "10001");

Boolean valid = expression.getValue(context, Boolean.class);
~~~

Biến postalCode được cung cấp qua context, còn kết quả được yêu cầu dưới dạng Boolean. Việc chỉ rõ kiểu kết quả giúp ứng dụng và bài kiểm thử thể hiện đúng hợp đồng của biểu thức.

Nếu pattern cũng được cung cấp qua biến, có thể viết:

~~~text
#value matches #pattern
~~~

Cách này hữu ích khi ứng dụng quản lý một tập pattern cấu hình được. Tuy nhiên, cần kiểm soát nguồn pattern, độ dài và độ phức tạp của nó. Một pattern được cung cấp tự do có thể gây ra chi phí xử lý lớn hoặc hành vi không mong muốn.

## 5. Kết hợp matches với toán tử logic

matches trả về Boolean nên có thể kết hợp với **and**, **or** và **not**.

Ví dụ kiểm tra cả việc có dữ liệu và định dạng:

~~~text
#code != null and #code matches '[A-Z]{2}-[0-9]{4}'
~~~

Biểu thức chỉ kiểm tra pattern khi code không null. Toán tử and trong SpEL đánh giá có điều kiện, vì vậy vế phải không cần được đánh giá khi vế trái đã false.

Nếu giá trị null được xem là hợp lệ vì trường là tùy chọn, có thể diễn đạt:

~~~text
#optionalCode == null or #optionalCode matches '[A-Z]{2}-[0-9]{4}'
~~~

Biểu thức trả về true khi trường không được cung cấp hoặc khi giá trị có định dạng hợp lệ. Hãy phân biệt rõ trường bắt buộc và trường tùy chọn; hai chính sách này không nên dùng cùng một biểu thức.

Có thể kết hợp nhiều điều kiện:

~~~text
#age >= 18 and #memberCode matches '[A-Z]{2}[0-9]{6}'
~~~

Biểu thức yêu cầu tuổi ít nhất 18 và memberCode có hai chữ cái in hoa theo sau bởi sáu chữ số. Dùng ngoặc khi biểu thức có nhiều nhánh and/or để thể hiện nhóm điều kiện một cách rõ ràng.

Phủ định kết quả bằng toán tử not:

~~~text
not (#code matches '[A-Z]{2}-[0-9]{4}')
~~~

Biểu thức trả về true khi code không khớp pattern. Nếu code có thể null hoặc không phải String, hãy xử lý các trường hợp đó trước khi phủ định; một lỗi đánh giá không đồng nghĩa với kết quả false.

## 6. Kiểu dữ liệu và lỗi thường gặp

Toán tử matches được thiết kế để kiểm tra chuỗi. Hãy bảo đảm vế trái đánh giá thành String và vế phải cung cấp một pattern String hợp lệ.

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Biểu thức không parse được | Sai cú pháp SpEL hoặc dấu nháy trong literal không cân bằng | Kiểm tra toán tử, dấu nháy và biểu thức hai vế |
| Lỗi khi đánh giá pattern | Regular expression không hợp lệ | Kiểm tra cú pháp Java Pattern độc lập |
| Vế trái không phải String | Property/biến có kiểu số, Boolean hoặc object khác | Chuyển đổi có chủ đích trong Java hoặc dùng property String phù hợp |
| Giá trị null gây lỗi | Vế trái không có chuỗi để so khớp | Kiểm tra null trước khi dùng matches |
| Chuỗi có đoạn khớp nhưng kết quả false | matches yêu cầu khớp toàn bộ chuỗi | Viết pattern bao phủ toàn bộ định dạng cần chấp nhận |
| Chỉ sai chữ hoa/thường | Pattern mặc định phân biệt hoa/thường | Xác định chính sách và cân nhắc flag **(?i)** |
| Kết quả không như mong đợi với dấu chấm hoặc dấu gạch | Ký tự có ý nghĩa đặc biệt trong regex | Escape ký tự hoặc dùng character class thích hợp |

### Phân biệt lỗi cú pháp và lỗi đánh giá

Lỗi parse xuất hiện khi SpEL không thể phân tích chuỗi biểu thức. Ví dụ, thiếu dấu nháy đóng hoặc đặt toán tử sai vị trí có thể gây lỗi trước khi biểu thức chạy.

Lỗi đánh giá xuất hiện khi biểu thức đã parse nhưng dữ liệu hoặc pattern tại runtime không phù hợp. Ví dụ, property trả về null, kiểu dữ liệu không phải String hoặc pattern động không hợp lệ.

Nên kiểm tra pattern ngay khi nạp cấu hình, thay vì chờ tới khi có yêu cầu thực tế đầu tiên. Khi lưu pattern trong hệ thống quản trị, hãy xác thực nó trước khi cho phép kích hoạt.

## 7. Escaping và dấu nháy

Pattern được đặt trong một String literal của SpEL, thường dùng dấu nháy đơn:

~~~text
#code matches '[A-Z]{2}-[0-9]{4}'
~~~

Có hai lớp cú pháp cần lưu ý khi biểu thức được viết trong mã Java:

1. Java xử lý chuỗi nguồn trước khi gửi nội dung cho SpEL parser.
2. SpEL xử lý String literal rồi mới chuyển pattern cho Java regular-expression engine.

Vì vậy, một dấu gạch chéo ngược trong pattern có thể cần được escape ở cả hai lớp. Nếu không chắc chuỗi cuối cùng là gì, hãy kiểm tra giá trị expression string ngay trước khi parse và thử pattern độc lập bằng Java Pattern.

Với các trường hợp đơn giản, character class có thể giúp tránh một số escape khó đọc. Ví dụ, **[.]** biểu diễn dấu chấm theo nghĩa đen mà không cần viết escape. Dù vậy, không nên thay đổi pattern chỉ để tránh escape nếu điều đó làm ý nghĩa trở nên khó hiểu hơn.

Nếu pattern chứa dấu nháy đơn, cần xử lý theo quy tắc String literal của SpEL. Nên viết kiểm thử cho chính chuỗi expression sau khi Java đã tạo ra nó, vì lỗi có thể nằm ở bước tạo chuỗi chứ không nằm ở regex.

## 8. An toàn và hiệu năng

Regular expression có thể trở nên tốn kém khi pattern phức tạp và đầu vào dài. Một số cấu trúc lặp lồng nhau hoặc có nhiều nhánh mơ hồ có thể khiến thời gian so khớp tăng mạnh với dữ liệu được chọn có chủ đích. Đây là rủi ro thường được gọi là regular-expression denial of service (ReDoS).

Để giảm rủi ro:

- Chỉ dùng pattern do ứng dụng kiểm soát hoặc đã được xác thực.
- Giới hạn độ dài đầu vào trước khi đánh giá.
- Giới hạn độ dài và độ phức tạp của pattern cấu hình.
- Tránh các quantifier lồng nhau hoặc các nhánh chồng lấn có thể tạo nhiều cách backtrack.
- Dùng pattern cụ thể với giới hạn số lượng ký tự thay vì pattern quá rộng.
- Kiểm thử thời gian đánh giá với dữ liệu biên và dữ liệu có kích thước lớn.
- Không cho phép người dùng cuối gửi pattern tùy ý vào một context có quyền rộng mà không có chính sách kiểm soát.

Java Pattern không cung cấp tham số timeout trực tiếp cho từng lần gọi matches. Vì vậy, không nên dựa vào timeout giả định để bảo vệ ứng dụng. Nếu pattern đến từ người dùng hoặc quản trị viên, hãy giới hạn ngôn ngữ biểu thức được phép và cân nhắc cơ chế kiểm tra khác có giới hạn tài nguyên rõ ràng.

Không dùng regex để thay thế mọi dạng xác thực. Đối với email, URL, số điện thoại, địa chỉ hoặc dữ liệu có quy tắc nghiệp vụ phức tạp, pattern đơn giản thường chỉ kiểm tra được một phần định dạng. Hãy kết hợp parser hoặc thư viện xác thực phù hợp khi cần kiểm tra ngữ nghĩa sâu hơn.

## 9. Kiểm thử biểu thức matches

Một bài kiểm thử tốt nên bao phủ giá trị hợp lệ, không hợp lệ và các ranh giới của pattern.

Ví dụ:

~~~java
@Test
void matchesPostalCodePattern() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
        parser.parseExpression("#postalCode matches '[0-9]{5}'");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    context.setVariable("postalCode", "10001");
    assertEquals(Boolean.TRUE, expression.getValue(context, Boolean.class));

    context.setVariable("postalCode", "1000A");
    assertEquals(Boolean.FALSE, expression.getValue(context, Boolean.class));
}
~~~

Trong bài kiểm thử, cùng một Expression được đánh giá với hai giá trị khác nhau. Điều này giúp xác minh pattern và cách lấy biến từ context.

Với mỗi pattern, hãy kiểm tra các trường hợp phù hợp với nghiệp vụ:

| Nhóm kiểm thử | Ví dụ với mã hai chữ cái và bốn số |
|---|---|
| Giá trị hợp lệ | **AB-1234** |
| Chữ thường | **ab-1234** |
| Thiếu ký tự | **A-1234** |
| Thừa ký tự | **ABC-1234** |
| Sai dấu phân cách | **AB_1234** |
| Có tiền tố ngoài định dạng | **Code AB-1234** |
| Có hậu tố ngoài định dạng | **AB-1234-extra** |
| Giá trị rỗng | Chuỗi rỗng |
| Giá trị null | Kiểm tra nhánh null trước matches |
| Đầu vào quá dài | Chuỗi vượt giới hạn nghiệp vụ |

Đối với pattern Unicode, kiểm thử chữ cái có dấu, ký tự kết hợp và các dạng chuẩn hóa nếu dữ liệu có thể đến từ nhiều hệ thống. Hai chuỗi nhìn giống nhau có thể có cách mã hóa Unicode khác nhau.

Nếu pattern được lưu ngoài mã nguồn, hãy có bước kiểm tra cú pháp trước khi kích hoạt. Có thể lưu phiên bản pattern, thời điểm thay đổi và người sở hữu để truy vết khi kết quả xác thực thay đổi.

## 10. Quy trình đưa pattern vào sử dụng

Khi thêm hoặc sửa một quy tắc matches:

1. **Mô tả định dạng bằng lời.** Ghi rõ ký tự nào được phép, độ dài, thứ tự và việc phân biệt hoa/thường.
2. **Viết ví dụ hợp lệ và không hợp lệ.** Các ví dụ giúp phát hiện trường hợp bị bỏ sót trước khi chuyển sang regex.
3. **Viết pattern đơn giản nhất đáp ứng yêu cầu.** Dùng character class, quantifier và group có giới hạn rõ ràng.
4. **Kiểm tra pattern bằng Java Pattern.** Xác nhận cú pháp và hành vi với bộ ví dụ đã chuẩn bị.
5. **Đưa pattern vào biểu thức SpEL.** Xác minh dấu nháy, escaping, biến và kiểu kết quả Boolean.
6. **Kiểm thử trong EvaluationContext thực tế.** Dùng cùng root object, biến và cấu hình context như ứng dụng.
7. **Đánh giá chi phí xử lý.** Thử đầu vào dài và trường hợp biên để phát hiện pattern có thể gây backtracking lớn.
8. **Triển khai có kiểm soát.** Nếu pattern được quản lý ngoài mã nguồn, lưu phiên bản trước và có cách quay lại khi quy tắc mới gây lỗi.

Khi quy tắc thay đổi, hãy so sánh tập đầu vào được chấp nhận trước và sau thay đổi. Một thay đổi nhỏ trong quantifier hoặc alternation có thể mở rộng hoặc thu hẹp đáng kể tập giá trị hợp lệ.

## 11. Checklist review

Trước khi chấp nhận biểu thức sử dụng matches, hãy kiểm tra:

- [ ] Vế trái luôn có kiểu String theo hợp đồng dữ liệu.
- [ ] Vế phải là một regular expression hợp lệ theo Java Pattern.
- [ ] Pattern khớp toàn bộ chuỗi theo đúng yêu cầu nghiệp vụ.
- [ ] Character class và quantifier có giới hạn phù hợp.
- [ ] Chính sách hoa/thường và Unicode đã được xác định.
- [ ] Null và chuỗi rỗng được xử lý có chủ đích.
- [ ] Dấu nháy và escaping đã được kiểm tra sau khi tạo expression string.
- [ ] Có kiểm thử giá trị hợp lệ, không hợp lệ, ranh giới và đầu vào quá dài.
- [ ] Pattern động được xác thực và kiểm soát nguồn.
- [ ] Độ phức tạp regex không tạo rủi ro backtracking không cần thiết.
- [ ] Kết quả Boolean được kết hợp với các điều kiện khác theo đúng logic.

## Kết luận

Toán tử matches giúp SpEL kiểm tra một chuỗi bằng Java regular expression và trả về Boolean. Vì phép so khớp yêu cầu toàn bộ chuỗi, pattern cần mô tả đầy đủ định dạng được phép. Hãy chọn character class và quantifier có giới hạn, xử lý null và kiểu dữ liệu trước khi so khớp, kiểm tra escaping qua cả Java và SpEL, đồng thời kiểm thử pattern với dữ liệu biên. Khi pattern được cấu hình từ bên ngoài, cần kiểm soát nguồn và độ phức tạp để tránh biến một quy tắc xác thực đơn giản thành rủi ro hiệu năng.
