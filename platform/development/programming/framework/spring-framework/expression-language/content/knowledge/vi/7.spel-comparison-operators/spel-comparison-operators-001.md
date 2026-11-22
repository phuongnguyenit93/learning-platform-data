# Phép bằng và khác trong SpEL

Spring Expression Language (SpEL) cung cấp hai toán tử so sánh bằng và khác để kiểm tra quan hệ giữa hai giá trị:

- **==**: bằng nhau.
- **!=**: khác nhau.

Chúng thường được dùng trong điều kiện, biểu thức chọn dữ liệu, kiểm tra trạng thái và quy tắc nghiệp vụ. Tuy nhiên, cần hiểu cách SpEL so sánh số, chuỗi, object và giá trị null để tránh kết quả ngoài dự kiến.

Điểm quan trọng là toán tử bằng của SpEL không nên được hiểu đơn giản là phép so sánh tham chiếu của Java. Với các giá trị số, SpEL có xử lý so sánh số riêng; với object thông thường, phép so sánh dựa trên quy tắc equals của đối tượng.

## 1. Cú pháp toán tử bằng và khác

### 1.1. Toán tử bằng (==)

Toán tử **==** trả về true khi hai toán hạng được xem là bằng nhau:

~~~java
1 == 1
'Spring' == 'Spring'
true == true
~~~

Ví dụ với parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean result = parser
        .parseExpression("10 == 10")
        .getValue(Boolean.class);
~~~

Kết quả là **true**.

Có thể dùng toán tử này trong điều kiện phức tạp:

~~~java
order.status == 'PAID'
~~~

hoặc:

~~~java
customer.age == 18
~~~

Kết quả của phép so sánh là Boolean và có thể được dùng trong toán tử logic, biểu thức điều kiện hoặc các API nhận giá trị Boolean.

### 1.2. Toán tử khác (!=)

Toán tử **!=** là phép phủ định của phép bằng:

~~~java
10 != 20
'Spring' != 'Spring Boot'
true != false
~~~

Ví dụ:

~~~java
Boolean result = parser
        .parseExpression("10 != 20")
        .getValue(Boolean.class);
~~~

Kết quả là **true**.

Có thể kiểm tra một trạng thái không thuộc giá trị mong muốn:

~~~java
order.status != 'CANCELLED'
~~~

Cần lưu ý rằng điều kiện này đúng với mọi trạng thái khác CANCELLED, kể cả khi status là null. Nếu nghiệp vụ yêu cầu status phải có giá trị trước khi kiểm tra, hãy thêm điều kiện null rõ ràng.

### 1.3. Thứ tự ưu tiên và dấu ngoặc

Các toán tử bằng và khác thường được kết hợp với toán tử logic:

~~~java
order.status == 'PAID' && order.total != null
~~~

Khi biểu thức có nhiều toán tử, nên dùng dấu ngoặc để thể hiện rõ nhóm điều kiện:

~~~java
(order.status == 'PAID' || order.status == 'SHIPPED')
        && order.total != null
~~~

Dấu ngoặc giúp người đọc nhận ra ý nghĩa nghiệp vụ ngay cả khi đã biết thứ tự ưu tiên của toán tử.

## 2. So sánh các kiểu dữ liệu

### 2.1. So sánh số

SpEL xử lý các toán hạng số theo giá trị số, kể cả khi chúng có kiểu Number khác nhau:

~~~java
1 == 1
1 == 1.0
10 != 9
~~~

Ví dụ:

~~~java
parser.parseExpression("1 == 1.0")
        .getValue(Boolean.class);
~~~

Phép so sánh số có thể trả về true dù hai literal được biểu diễn bằng các kiểu số khác nhau. Vì vậy, không nên dùng kết quả của phép bằng số để suy luận rằng hai toán hạng có cùng kiểu Java.

Nếu nghiệp vụ cần phân biệt kiểu dữ liệu, hãy kiểm tra kiểu riêng hoặc chuẩn hóa kiểu trước khi so sánh.

### 2.2. So sánh chuỗi

Với chuỗi, phép bằng có phân biệt chữ hoa và chữ thường:

~~~java
'Spring' == 'Spring'
'Spring' != 'spring'
~~~

Kết quả của biểu thức thứ nhất là true; biểu thức thứ hai cũng là true vì hai chuỗi khác nhau về chữ hoa/chữ thường.

Nếu cần so sánh không phân biệt hoa thường, có thể gọi method của String:

~~~java
name != null && name.equalsIgnoreCase('spring')
~~~

Điều kiện null ở đầu bảo đảm không gọi method trên một tham chiếu null. Nếu ứng dụng có quy tắc chuẩn hóa chuỗi theo locale, hãy thực hiện chuẩn hóa theo chính sách nghiệp vụ thay vì mặc định dùng một cách chuyển chữ hoa/chữ thường cho mọi ngôn ngữ.

### 2.3. So sánh Boolean

Hai giá trị Boolean được so sánh theo giá trị:

~~~java
true == true
true != false
~~~

Trong điều kiện, thường không cần viết phép so sánh với true:

~~~java
order.confirmed
~~~

Biểu thức trên đã trả về Boolean nếu property confirmed có kiểu boolean hoặc Boolean phù hợp.

Viết **order.confirmed == true** vẫn có thể đọc được trong một số ngữ cảnh, nhưng thường dài hơn cần thiết. Với Boolean có thể null, hãy xác định rõ null có nghĩa là chưa xác định, không áp dụng hay false.

### 2.4. So sánh object

Với object thông thường, phép bằng SpEL sử dụng quy tắc equals của đối tượng. Vì vậy, kết quả phụ thuộc cách class triển khai equals.

Ví dụ, record Java tự cung cấp equals dựa trên các thành phần dữ liệu:

~~~java
public record CustomerId(String value) {
}
~~~

Hai object CustomerId được tạo riêng nhưng có cùng value được xem là bằng nhau:

~~~java
new CustomerId('C-100') == new CustomerId('C-100')
~~~

Trong biểu thức thực tế, có thể so sánh các object lấy từ root object hoặc biến:

~~~java
order.customerId == currentCustomer.id
~~~

Nếu kiểu miền không triển khai equals đúng theo định nghĩa nghiệp vụ, phép bằng có thể cho kết quả khác mong đợi. Hãy kiểm tra equals/hashCode của class trước khi dựa vào phép so sánh object.

### 2.5. List và Map

List và Map chuẩn của Java có quy tắc equals riêng:

- Hai List bằng nhau khi có cùng số phần tử và các phần tử tương ứng bằng nhau theo thứ tự.
- Hai Map bằng nhau khi chứa cùng các ánh xạ key-value, không phụ thuộc thứ tự duyệt entry.
- Các phép so sánh lồng nhau tiếp tục phụ thuộc equals của từng phần tử, key và value.

Ví dụ:

~~~java
{1, 2, 3} == {1, 2, 3}
~~~

Không nên chỉ dựa vào hình thức literal để kết luận mọi cấu trúc collection đều có cùng kết quả. Kết quả phụ thuộc kiểu collection và cách kiểu đó triển khai equals. Với collection tùy chỉnh, hãy kiểm tra hợp đồng equals của implementation.

### 2.6. Mảng Java

Mảng Java kế thừa equals từ Object và không so sánh nội dung phần tử theo cách List.equals. Hai mảng khác instance thường không bằng nhau chỉ vì chứa cùng dữ liệu:

~~~java
new int[2] == new int[2]
~~~

Trong ví dụ này, hai mảng được cấp phát độc lập. Nếu cần so sánh nội dung mảng, hãy dùng method phù hợp trong Java như Arrays.equals hoặc chuyển dữ liệu sang collection có quy tắc equals phù hợp trước khi đánh giá.

Không nên nhầm phép bằng của SpEL với phép so sánh nội dung sâu của mọi cấu trúc dữ liệu.

## 3. So sánh với null

### 3.1. null bằng null

Trong SpEL, hai giá trị null được xem là bằng nhau:

~~~java
null == null
~~~

Một giá trị null và một giá trị khác null không bằng nhau:

~~~java
null != 'Spring'
'Spring' == null
~~~

Do đó, phép so sánh null có thể dùng để kiểm tra một property chưa có giá trị:

~~~java
order.note == null
~~~

### 3.2. Phân biệt null với chuỗi rỗng

Chuỗi rỗng là một String có độ dài bằng 0, không phải null:

~~~java
'' == null
'' != null
~~~

Nếu cần kiểm tra chuỗi không có nội dung, cần xác định rõ có bao gồm chuỗi chỉ chứa khoảng trắng hay không:

~~~java
name == null || name.trim().isEmpty()
~~~

Nếu tên có thể null, nhánh đầu tiên bảo đảm method trim chỉ được gọi khi name khác null nhờ cơ chế đánh giá ngắn mạch của toán tử OR.

Với ứng dụng dùng Java 11 trở lên, có thể dùng method isBlank nếu muốn coi chuỗi chỉ chứa whitespace là rỗng:

~~~java
name == null || name.isBlank()
~~~

### 3.3. Null trong property chain

Một property trung gian có thể null:

~~~java
order.customer.address.city
~~~

Nếu customer hoặc address là null, truy cập tiếp theo có thể phát sinh lỗi khi đánh giá. Có thể kiểm tra từng bước:

~~~java
order.customer != null
        && order.customer.address != null
        && order.customer.address.city == 'Hanoi'
~~~

Toán tử AND đánh giá ngắn mạch, vì vậy các vế sau chỉ được đánh giá khi những vế trước đúng. Đây là một cách bảo vệ chuỗi truy cập khi không dùng safe navigation.

Nếu phiên bản Spring và cú pháp đang dùng hỗ trợ safe navigation, có thể viết gọn:

~~~java
order.customer?.address?.city == 'Hanoi'
~~~

Hãy chọn cách thể hiện rõ ràng nhất với phiên bản Spring của dự án và quy tắc null của domain.

## 4. So sánh object theo equals và theo định danh

### 4.1. == không phải phép kiểm tra cùng tham chiếu cho mọi object

Trong Java, toán tử **==** trên hai object reference kiểm tra chúng có cùng tham chiếu hay không. SpEL có ngữ nghĩa so sánh riêng: với object thông thường, phép bằng dựa trên equals.

Ví dụ hai chuỗi được tạo từ hai object String khác nhau nhưng có cùng nội dung vẫn có thể được xem là bằng nhau:

~~~java
new String('Spring') == new String('Spring')
~~~

Vì vậy, không dùng **==** trong SpEL để kiểm tra hai biến có trỏ tới đúng cùng một object trong bộ nhớ.

Trong phần lớn quy tắc nghiệp vụ, so sánh theo giá trị là điều mong muốn. Nếu nghiệp vụ thật sự phụ thuộc vào định danh object, hãy cung cấp một method hoặc thuộc tính có ý nghĩa rõ ràng trong model, chẳng hạn so sánh một identifier ổn định.

### 4.2. Thiết kế equals cho kiểu miền

Với các kiểu như CustomerId, Money, OrderNumber hoặc EmailAddress, equals nên phản ánh định nghĩa bằng nhau của miền nghiệp vụ.

Ví dụ:

~~~java
public record OrderNumber(String value) {
}
~~~

Khi hai OrderNumber có cùng value, phép so sánh SpEL sẽ sử dụng quy tắc equals được sinh cho record.

Với class thông thường, cần triển khai equals và hashCode nhất quán. Nếu equals chỉ so sánh một phần dữ liệu, hãy chắc chắn phần dữ liệu đó chính là tiêu chí bằng nhau mà biểu thức nghiệp vụ cần dùng.

Không nên viết logic nghiệp vụ phức tạp trong equals. Nếu một điều kiện cần nhiều quy tắc, hãy tạo method có tên rõ ràng và gọi method đó trong SpEL.

## 5. Dùng phép bằng trong điều kiện nghiệp vụ

### 5.1. Kiểm tra trạng thái

~~~java
order.status == 'PAID'
~~~

Đây là điều kiện cơ bản để kiểm tra đơn hàng đã thanh toán.

Nếu chấp nhận nhiều trạng thái:

~~~java
order.status == 'PAID' || order.status == 'SETTLED'
~~~

Có thể nhóm điều kiện cùng ý nghĩa:

~~~java
(order.status == 'PAID' || order.status == 'SETTLED')
        && order.total > 0
~~~

Dấu ngoặc giúp tách nhóm trạng thái hợp lệ khỏi điều kiện về tổng tiền.

### 5.2. Kiểm tra identifier

~~~java
order.customerId == currentCustomer.id
~~~

Đây là cách so sánh hai identifier nếu kiểu của chúng có equals đúng. Nếu hai bên có kiểu khác nhau, hãy chuẩn hóa hoặc chuyển đổi rõ ràng thay vì dựa vào chuyển kiểu ngầm.

### 5.3. Kết hợp bằng và khác với logic

~~~java
order.status != 'CANCELLED'
        && order.customerId == currentCustomer.id
~~~

Điều kiện chỉ đúng khi đơn hàng không bị hủy và thuộc khách hàng hiện tại.

Khi biểu thức dài, hãy tách các nhóm điều kiện bằng dấu ngoặc hoặc chuyển một nhóm quy tắc sang method có tên rõ nghĩa. Điều này giúp người đọc hiểu mục đích nghiệp vụ thay vì chỉ phải phân tích một chuỗi toán tử.

## 6. Dùng equalsIgnoreCase và method so sánh chuyên biệt

Toán tử **==** so sánh String có phân biệt hoa thường. Nếu nghiệp vụ không phân biệt hoa thường, gọi method tương ứng:

~~~java
username != null && username.equalsIgnoreCase('admin')
~~~

Nếu cần chuẩn hóa khoảng trắng:

~~~java
username != null
        && username.trim().equalsIgnoreCase('admin')
~~~

Nếu dữ liệu có quy tắc chuẩn hóa phức tạp hơn, nên xử lý ở tầng domain hoặc tạo method tiện ích được kiểm soát. Tránh lặp lại các chuỗi chuẩn hóa dài trong nhiều biểu thức.

Đối với giá trị số tiền, ngày giờ hoặc mã nghiệp vụ, hãy chọn phép so sánh phù hợp với kiểu dữ liệu. Ví dụ, so sánh khoảng thời gian có thể cần so sánh trước/sau thay vì bằng chính xác; so sánh mã không phân biệt hoa thường có thể cần một kiểu value object đã chuẩn hóa.

## 7. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hai object có cùng dữ liệu nhưng kết quả false | Class chưa triển khai equals theo giá trị | Kiểm tra equals/hashCode hoặc dùng identifier |
| Hai mảng cùng nội dung nhưng kết quả false | Array.equals không so sánh nội dung | Dùng Arrays.equals trong Java hoặc chuyển thành collection phù hợp |
| String khác chữ hoa/thường không bằng nhau | String equality phân biệt hoa thường | Dùng equalsIgnoreCase nếu nghiệp vụ yêu cầu |
| null gây lỗi khi gọi method | Gọi method trực tiếp trên giá trị null | Kiểm tra null trước hoặc dùng safe navigation khi phù hợp |
| Điều kiện status != CANCELLED chấp nhận null | null khác CANCELLED | Thêm kiểm tra status != null nếu bắt buộc phải có trạng thái |
| Số có kiểu khác nhau bị hiểu sai | Nhầm kết quả so sánh giá trị với cùng kiểu Java | Kiểm tra kiểu riêng nếu nghiệp vụ cần |
| Biểu thức dài và khó hiểu | Trộn nhiều điều kiện bằng/khác | Dùng dấu ngoặc, nhóm điều kiện hoặc method có tên rõ nghĩa |

## 8. Kiểm thử biểu thức bằng và khác

Nên kiểm thử cả trường hợp đúng, sai và dữ liệu biên. Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("10 == 10").getValue(Boolean.class)
);

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("10 != 20").getValue(Boolean.class)
);

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("null == null").getValue(Boolean.class)
);

assertEquals(
        Boolean.FALSE,
        parser.parseExpression("'' == null").getValue(Boolean.class)
);
~~~

Với object miền, kiểm thử equals độc lập trước rồi mới kiểm thử biểu thức SpEL. Với collection và array, thêm trường hợp hai instance khác nhau nhưng cùng nội dung để xác nhận đúng semantics của kiểu dữ liệu.

Khi kiểm thử biểu thức lấy dữ liệu từ root object, nên chuẩn bị cả các trường hợp:

- Property có giá trị thông thường.
- Property là null.
- Hai object có cùng identifier nhưng khác instance.
- String có khác biệt chữ hoa/chữ thường.
- Collection rỗng và collection có phần tử.
- Array được cấp phát riêng nhưng chứa cùng giá trị.

## 9. Tổng kết

SpEL dùng **==** để kiểm tra bằng nhau và **!=** để kiểm tra khác nhau. Cách so sánh phụ thuộc kiểu toán hạng: giá trị số được so sánh theo số; object thông thường dựa trên equals; String phân biệt chữ hoa/chữ thường; array Java không tự so sánh nội dung.

Khi viết biểu thức nghiệp vụ, hãy xác định rõ null có ý nghĩa gì, kiểu miền định nghĩa equals ra sao và liệu có cần so sánh không phân biệt hoa thường hay không. Dùng dấu ngoặc để làm rõ nhóm điều kiện, và chuyển logic phức tạp sang method có tên cụ thể khi biểu thức bắt đầu khó đọc.