# Biến có giá trị null trong SpEL

## 1. Null trong biểu thức SpEL

Spring Expression Language (SpEL) có thể đọc variables từ `EvaluationContext`, property từ root object và kết quả từ method call. Những giá trị này có thể là null vì dữ liệu chưa được cung cấp, property chưa được khởi tạo hoặc method không tìm thấy kết quả.

Trong SpEL, từ khóa `null` biểu diễn giá trị không có tham chiếu. Nó khác với chuỗi ký tự `"null"` và khác với chuỗi rỗng `''`.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object nullValue = parser.parseExpression("null").getValue();
String textValue = parser.parseExpression("'null'").getValue(String.class);
String emptyValue = parser.parseExpression("''").getValue(String.class);

System.out.println(nullValue);  // null
System.out.println(textValue);  // null
System.out.println(emptyValue); // chuỗi rỗng
~~~

Dòng đầu trả về giá trị null thực sự. Dòng thứ hai trả về một đối tượng `String` có nội dung gồm bốn ký tự `null`. Dòng thứ ba trả về một `String` có độ dài bằng 0. Khi xử lý dữ liệu tùy chọn, cần phân biệt ba trường hợp này vì phép so sánh và điều kiện mặc định có thể cho kết quả khác nhau.

## 2. Đưa variable vào EvaluationContext

Variable trong SpEL được tham chiếu bằng tiền tố `#`. Ví dụ `#nickname` là variable có tên `nickname` trong evaluation context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("nickname", "Lan");

Expression expression = parser.parseExpression("#nickname");
String nickname = expression.getValue(context, String.class);

System.out.println(nickname); // Lan
~~~

Nếu giá trị Java truyền vào là null, `StandardEvaluationContext.setVariable(name, null)` gỡ binding của variable đó khỏi context. Khi expression tham chiếu một variable chưa được gắn giá trị, kết quả lookup là null:

~~~java
context.setVariable("nickname", null);

Expression expression = parser.parseExpression("#nickname");
Object nickname = expression.getValue(context);

System.out.println(nickname); // null
~~~

Vì vậy, khi một biến nghiệp vụ có thể không có giá trị, hãy hiểu rõ trạng thái của nó tại thời điểm đánh giá. `#nickname` có thể cho kết quả null vì binding chưa được thiết lập hoặc đã bị gỡ; expression đơn thuần không cho biết lý do nào đã xảy ra.

Nếu cần phân biệt “không có binding” với “đã có dữ liệu nhưng giá trị là null”, hãy truyền thêm một variable trạng thái, chẳng hạn `#nicknameProvided`, hoặc biểu diễn trạng thái bằng một object/wrapper không null. Không nên dựa vào một phép so sánh `#nickname == null` để suy ra nguồn gốc của null.

## 3. Kiểm tra null bằng toán tử so sánh

Có thể kiểm tra một variable hoặc property có null hay không bằng `== null` và `!= null`:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("nickname", null);

Expression isNullExpression =
        parser.parseExpression("#nickname == null");

Expression hasValueExpression =
        parser.parseExpression("#nickname != null");

Boolean isNull = isNullExpression.getValue(context, Boolean.class);
Boolean hasValue = hasValueExpression.getValue(context, Boolean.class);

System.out.println(isNull);   // true
System.out.println(hasValue); // false
~~~

Có thể dùng cùng cách kiểm tra với property của root object:

~~~java
Expression expression = parser.parseExpression("email == null");

Boolean emailMissing = expression.getValue(customer, Boolean.class);
~~~

Ở ví dụ này, `email` được đọc từ root object `customer`. Không có tiền tố `#` vì đây là property của root object, không phải variable trong context.

Khi viết điều kiện, nên kiểm tra null trước khi gọi method hoặc truy cập property phụ thuộc vào giá trị đó. Phép so sánh `== null` giúp biểu đạt ý định rõ ràng và dễ đọc hơn việc cố gọi method trên một giá trị có thể null.

## 4. Chọn giá trị thay thế bằng toán tử ba ngôi

Toán tử ba ngôi cho phép chọn một kết quả khi variable có giá trị và một kết quả khác khi variable là null:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("nickname", null);

Expression expression = parser.parseExpression(
        "#nickname != null ? #nickname : 'Guest'");

String displayName = expression.getValue(context, String.class);
System.out.println(displayName); // Guest
~~~

Khi `#nickname != null` là true, SpEL chọn nhánh giữa `?` và `:`. Khi điều kiện false, SpEL chọn nhánh sau `:`. Chỉ nhánh được chọn mới được đánh giá để tạo kết quả.

Có thể dùng giá trị thay thế là số, Boolean hoặc một biểu thức khác:

~~~java
Expression retryExpression = parser.parseExpression(
        "#retryCount != null ? #retryCount : 3");

Expression enabledExpression = parser.parseExpression(
        "#featureEnabled != null ? #featureEnabled : false");
~~~

Khi hai nhánh trả về kiểu khác nhau, hãy kiểm tra kiểu kết quả mà ứng dụng mong đợi và dùng overload `getValue(..., TargetType.class)` phù hợp. Với expression dùng trong nhiều nơi, giữ kiểu kết quả nhất quán giúp tránh lỗi chuyển đổi lúc runtime.

## 5. Dùng Elvis operator để viết giá trị mặc định ngắn gọn

Elvis operator `?:` là cách viết ngắn để cung cấp giá trị thay thế khi vế trái là null:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("nickname", null);

Expression expression =
        parser.parseExpression("#nickname ?: 'Guest'");

String displayName = expression.getValue(context, String.class);
System.out.println(displayName); // Guest
~~~

Với trường hợp đơn giản, Elvis tương đương với việc kiểm tra null bằng toán tử ba ngôi. Nó giúp expression ngắn hơn khi chỉ cần một giá trị mặc định.

Trong SpEL, Elvis operator cũng xem chuỗi rỗng là trường hợp cần dùng giá trị mặc định:

~~~java
context.setVariable("nickname", "");

Expression expression =
        parser.parseExpression("#nickname ?: 'Guest'");

String displayName = expression.getValue(context, String.class);
System.out.println(displayName); // Guest
~~~

Elvis không xem mọi giá trị “trống” là null. Giá trị Boolean `false` và số `0` vẫn là những giá trị không null; chúng được giữ lại thay vì chuyển sang nhánh mặc định. Nếu muốn xử lý chuỗi chỉ chứa khoảng trắng, có thể trim trước:

~~~java
Expression expression =
        parser.parseExpression("#nickname?.trim() ?: 'Guest'");
~~~

Ở ví dụ này, `?.` tránh gọi `trim()` khi `#nickname` là null. Nếu chuỗi sau khi trim trở thành rỗng, Elvis trả về `Guest`.

## 6. Phân biệt null, chuỗi rỗng và giá trị mặc định

Các trường hợp thường gặp:

| Giá trị | `#value == null` | `#value ?: 'default'` |
|---|---:|---|
| null | true | `default` |
| `''` | false | `default` |
| `'Lan'` | false | `Lan` |
| `false` | false | `false` |
| `0` | false | `0` |

Điều này quan trọng khi variable là Boolean hoặc số. Không nên dùng Elvis với suy nghĩ rằng false hoặc zero cũng có nghĩa là thiếu dữ liệu.

Ví dụ, nếu `#enabled` có giá trị false, expression sau vẫn trả về false:

~~~java
Expression expression =
        parser.parseExpression("#enabled ?: true");
~~~

Nếu nghiệp vụ muốn false được thay bằng true, hãy viết điều kiện rõ ràng cho trường hợp đó. Elvis phù hợp với null và chuỗi rỗng; nó không thay thế cho một quy tắc kiểm tra Boolean hay số học.

## 7. Truy cập property hoặc gọi method khi object có thể null

Một variable có thể tham chiếu tới object null. Nếu gọi property hoặc method trực tiếp trên object đó, SpEL có thể phát sinh lỗi evaluation:

~~~text
#customer.name
#customer.getName()
~~~

Dùng null-safe navigation `?.` khi target có thể null:

~~~java
Expression nameExpression =
        parser.parseExpression("#customer?.name");

Expression methodExpression =
        parser.parseExpression("#customer?.getName()");
~~~

Nếu `#customer` là null, các biểu thức null-safe trả về null. Nếu object tồn tại, SpEL tiếp tục đọc property hoặc gọi method tương ứng.

Với đường dẫn nhiều cấp, mỗi object trung gian có thể null cần được bảo vệ ở vị trí phù hợp:

~~~text
#customer?.address?.city
~~~

Chỉ viết `#customer?.address.city` nếu đã bảo đảm `address` không thể null. Null-safe operator bảo vệ thao tác ngay sau nó; nó không tự biến toàn bộ phần còn lại của đường dẫn thành an toàn.

## 8. Kết hợp null-safe navigation với giá trị mặc định

Có thể kết hợp `?.` và Elvis `?:` để đọc một property tùy chọn và cung cấp giá trị thay thế:

~~~java
Expression expression = parser.parseExpression(
        "#customer?.address?.city ?: 'Unknown city'");

String city = expression.getValue(context, String.class);
~~~

Quá trình xử lý:

1. SpEL đọc variable `#customer`.
2. Nếu customer là null, phần null-safe trả về null.
3. Nếu customer tồn tại, SpEL đọc address; nếu address null, kết quả tiếp tục là null.
4. Nếu city có giá trị phù hợp, kết quả là city.
5. Nếu kết quả bên trái là null hoặc chuỗi rỗng, Elvis trả về `Unknown city`.

Cách viết này phù hợp với các đường dẫn dữ liệu tùy chọn ngắn. Nếu có nhiều nhánh mặc định hoặc nhiều quy tắc nghiệp vụ, hãy tách logic sang method Java để dễ đặt tên và kiểm thử.

## 9. Xử lý null trong collection variable

Variable trỏ tới một collection cũng có thể null. Khi gọi selection hoặc projection trên target null bằng cú pháp thông thường, expression có thể lỗi. Với phiên bản Spring Framework hỗ trợ null-safe collection operators, có thể dùng `?.?` và `?.!`:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("items", null);

Expression selection = parser.parseExpression("#items?.?[active]");
Expression projection = parser.parseExpression("#items?.![name]");

Object activeItems = selection.getValue(context);
Object itemNames = projection.getValue(context);

System.out.println(activeItems); // null
System.out.println(itemNames);   // null
~~~

Null-safe collection selection và projection được bổ sung trong Spring Framework 6.2. Với phiên bản cũ hơn, hãy kiểm tra null trong Java trước khi đánh giá expression hoặc dùng cấu trúc được phiên bản đó hỗ trợ.

Cần phân biệt target null với collection rỗng. Target null cho kết quả null khi dùng null-safe operator; collection rỗng không null sẽ tạo kết quả collection rỗng. Hai trạng thái này có thể mang ý nghĩa nghiệp vụ khác nhau, ví dụ “chưa tải dữ liệu” và “đã tải nhưng không có phần tử”.

## 10. Lọc phần tử null trong collection

Collection có thể tồn tại nhưng chứa một hoặc nhiều phần tử null. Null-safe operator trên collection gốc không tự bảo vệ từng phần tử.

Ví dụ, lọc các phần tử khác null và có property `name` khác null:

~~~java
List<Item> items = Arrays.asList(
        new Item("A"),
        null,
        new Item(null));

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("items", items);

Expression expression = parser.parseExpression(
        "#items?.?[#this != null and #this.name != null]");

List<?> namedItems = expression.getValue(context, List.class);
~~~

Trong predicate, `#this` đại diện cho phần tử đang được xét. Điều kiện đầu kiểm tra phần tử không null; điều kiện tiếp theo mới đọc property `name`.

Có thể dùng null-safe property access nếu muốn giữ phần tử nhưng lấy một property có thể null:

~~~text
#items?.![#this?.name]
~~~

Selection lọc phần tử theo điều kiện; projection tạo collection giá trị mới. Hãy chọn thao tác theo kết quả cần nhận và bảo vệ cả collection lẫn phần tử nếu cả hai cấp đều có thể null.

## 11. Dùng biến trạng thái để phân biệt thiếu dữ liệu và null

Một phép kiểm tra `#value == null` chỉ cho biết kết quả hiện tại là null. Nó không cho biết dữ liệu chưa được cung cấp, đã bị gỡ khỏi context hay property có giá trị null.

Nếu nghiệp vụ cần phân biệt các trạng thái đó, hãy truyền thêm biến trạng thái rõ ràng:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();

String nickname = loadNickname();
boolean nicknameWasProvided = wasNicknameProvided();

context.setVariable("nickname", nickname);
context.setVariable("nicknameWasProvided", nicknameWasProvided);

Expression expression = parser.parseExpression(
        "#nicknameWasProvided ? (#nickname ?: 'Unnamed') : 'Not provided'");
~~~

`#nicknameWasProvided` cho biết dữ liệu có được cung cấp hay không. `#nickname` chứa giá trị thực tế nếu có. Nếu nickname null hoặc chuỗi rỗng, Elvis có thể cung cấp `Unnamed`; nếu dữ liệu chưa được cung cấp, expression trả về `Not provided`.

Có thể dùng một object request hoặc wrapper có property trạng thái thay vì nhiều variables rời rạc nếu trạng thái này được dùng ở nhiều biểu thức. Tên trạng thái nên thể hiện rõ ý nghĩa nghiệp vụ, không chỉ là một cờ kỹ thuật chung chung.

## 12. Null trong method call và kết quả tính toán

Method được gọi từ expression có thể trả về null ngay cả khi target object không null. Ví dụ một method tra cứu có thể không tìm thấy kết quả:

~~~java
public class CustomerDirectory {
    public Customer findByCode(String code) {
        // Có thể trả về null nếu không tìm thấy.
        return lookup(code);
    }
}
~~~

Nếu evaluation context cho phép truy cập bean hoặc object đó, kết quả method call vẫn có thể null. Hãy xử lý kết quả trước khi tiếp tục truy cập property:

~~~text
@customerDirectory.findByCode(#code)?.name ?: 'Unknown'
~~~

Tương tự, một phép tính hoặc method call có thể tạo ra null từ dữ liệu đầu vào tùy cách class được thiết kế. Không giả định mọi property và method đều luôn trả về một object hợp lệ; hãy xác định contract của dữ liệu và cung cấp giá trị mặc định tại ranh giới phù hợp.

## 13. Lỗi thường gặp khi xử lý null

**Dùng chuỗi 'null' thay cho giá trị null**

`'null'` là string literal. Dùng từ khóa `null` khi muốn biểu diễn tham chiếu null.

**Gọi property trên object null**

`#customer.name` có thể lỗi nếu `#customer` null. Dùng `#customer?.name` hoặc kiểm tra điều kiện trước.

**Nghĩ rằng setVariable(name, null) giữ một binding null**

Với `StandardEvaluationContext`, truyền null vào `setVariable` sẽ gỡ variable khỏi context. Nếu cần biểu diễn trạng thái, dùng thêm cờ hoặc wrapper không null.

**Nhầm null với chuỗi rỗng**

`''` không bằng null. Elvis xử lý cả null và chuỗi rỗng; phép so sánh `== null` chỉ nhận diện null.

**Nghĩ rằng false hoặc zero sẽ kích hoạt Elvis**

False và zero là giá trị không null, vì vậy Elvis giữ nguyên chúng. Viết điều kiện riêng nếu nghiệp vụ muốn xử lý false hoặc zero như trường hợp đặc biệt.

**Chỉ bảo vệ object đầu tiên trong đường dẫn**

`#customer?.address.city` vẫn có thể lỗi nếu address null. Đặt null-safe operator tại từng chặng có thể null.

**Giả định collection null giống collection rỗng**

Null-safe selection trên target null trả về null; selection trên collection rỗng trả về collection rỗng. Hãy giữ khác biệt nếu nghiệp vụ cần.

## 14. Ví dụ tổng hợp

Ví dụ sau đọc variable tùy chọn, xử lý customer null, chọn tên mặc định và lọc collection có phần tử null:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("customer", null);
context.setVariable("nickname", "");
context.setVariable("items", Arrays.asList(
        new Item("A"),
        null,
        new Item(null),
        new Item("B")));

Expression displayExpression = parser.parseExpression(
        "#customer?.name ?: (#nickname ?: 'Guest')");

Expression namedItemsExpression = parser.parseExpression(
        "#items?.?[#this != null and #this.name != null]");

String displayName =
        displayExpression.getValue(context, String.class);

List<?> namedItems =
        namedItemsExpression.getValue(context, List.class);

System.out.println(displayName); // Guest
System.out.println(namedItems.size()); // 2
~~~

Trong ví dụ này, customer null khiến `#customer?.name` trả về null. Nickname là chuỗi rỗng nên Elvis tiếp tục chọn `Guest`. Collection items không null; selection giữ lại hai phần tử có name khác null và loại bỏ phần tử null cùng phần tử có name null.

## 15. Ghi nhớ

- Từ khóa `null` biểu diễn giá trị null; `'null'` là một string literal và `''` là chuỗi rỗng.
- Variables được tham chiếu bằng `#name`; property của root object được tham chiếu trực tiếp bằng tên property.
- `StandardEvaluationContext.setVariable(name, null)` gỡ binding variable; lookup của variable không có giá trị trả về null.
- Dùng `#value == null` và `#value != null` để kiểm tra null.
- Dùng ternary hoặc Elvis `?:` để cung cấp giá trị thay thế; Elvis xử lý null và chuỗi rỗng, nhưng giữ false và zero.
- Dùng `?.` cho property hoặc method call trên object có thể null; bảo vệ từng chặng trong đường dẫn nhiều cấp.
- Null-safe collection selection/projection yêu cầu Spring Framework 6.2 trở lên.
- Collection null khác collection rỗng; collection cũng có thể chứa phần tử null.
- Nếu cần phân biệt dữ liệu chưa được cung cấp với giá trị null, truyền thêm trạng thái rõ ràng hoặc dùng wrapper.
- Kiểm tra contract của method và property vì chúng cũng có thể trả về null.
