# Khởi tạo SpEL parser và tạo Expression

## 1. Vai trò của parser và expression

Spring Expression Language (SpEL) cung cấp một ngôn ngữ biểu thức để đọc property, truy cập collection, so sánh, tính toán và gọi method trên object lúc chạy. Khi dùng SpEL trực tiếp trong Java, hai abstraction quan trọng nhất là:

- `ExpressionParser`: nhận chuỗi biểu thức và phân tích cú pháp đó.
- `Expression`: đại diện cho biểu thức đã được phân tích; ta dùng nó để lấy giá trị hoặc cập nhật giá trị trên một evaluation context/root object.

`SpelExpressionParser` là implementation phổ biến của `ExpressionParser`. Luồng sử dụng cơ bản gồm ba bước: tạo parser, gọi `parseExpression(...)` để nhận `Expression`, rồi gọi `getValue(...)` với dữ liệu cần đánh giá.

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("'Hello, SpEL!'");
String message = expression.getValue(String.class);

System.out.println(message); // Hello, SpEL!
~~~

Chuỗi `'Hello, SpEL!'` là một biểu thức SpEL hợp lệ: nó trả về một string literal. Dấu nháy đơn thuộc cú pháp của SpEL. Dấu `#{...}` thường thấy trong annotation Spring như `@Value` không cần thiết khi ta gọi `parseExpression` trực tiếp với một biểu thức thông thường.

## 2. Dependency cần có

Nếu ứng dụng không dùng một module Spring khác kéo theo SpEL, có thể khai báo module `spring-expression` trực tiếp:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-expression</artifactId>
</dependency>
~~~

Nếu dự án dùng Spring Boot dependency management hoặc Spring Framework BOM, để BOM quản lý version của module nhằm giữ các module Spring cùng phiên bản. Trong ứng dụng Spring thông thường, `spring-expression` thường đã có trên classpath thông qua các dependency liên quan.

Các import chính trong ví dụ parser:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
~~~

## 3. Tạo parser

Cách khởi tạo mặc định là gọi constructor không tham số:

~~~java
ExpressionParser parser = new SpelExpressionParser();
~~~

Parser mặc định xử lý cú pháp SpEL thông thường. Có thể giữ parser trong một thành phần dùng chung của ứng dụng nếu phù hợp với vòng đời và cách tổ chức code. Việc phân tích cú pháp và việc đánh giá là hai thao tác khác nhau: `parseExpression` tạo ra `Expression`, còn `getValue` đánh giá expression trên dữ liệu/context cụ thể.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression taxExpression = parser.parseExpression("price * 0.1");
Expression labelExpression = parser.parseExpression("'Order-' + #orderId");
~~~

Một expression có thể được đánh giá với các root object hoặc evaluation context khác nhau, miễn là dữ liệu được cung cấp phù hợp với các property và biến mà biểu thức tham chiếu.

## 4. Tạo Expression từ chuỗi

Phương thức thường dùng nhất là:

~~~java
Expression expression = parser.parseExpression("2 + 3 * 4");
~~~

`parseExpression(String)` nhận chuỗi chứa một biểu thức SpEL hoàn chỉnh và trả về đối tượng `Expression`. Một số ví dụ:

| Chuỗi đầu vào | Ý nghĩa |
|---|---|
| `"42"` | Số nguyên literal |
| `"'Spring'"` | Chuỗi literal |
| `"true"` | Boolean literal |
| `"2 + 3 * 4"` | Phép tính số học |
| `"'spring'.toUpperCase()"` | Gọi method trên string |
| `"items[0]"` | Truy cập phần tử đầu tiên |
| `"customer.address.city"` | Truy cập property lồng nhau |
| `"total >= 1000 and active"` | Kết hợp điều kiện logic |

Sau khi parse, lấy kết quả bằng `getValue`:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("2 + 3 * 4");

Object rawValue = expression.getValue();
Integer result = expression.getValue(Integer.class);

System.out.println(rawValue); // 14
System.out.println(result);   // 14
~~~

`getValue()` trả về `Object`; overload nhận `Class<T>` yêu cầu kết quả theo kiểu mong muốn và sử dụng cơ chế chuyển đổi kiểu của SpEL nếu cần. Nên chỉ định kiểu đích khi ứng dụng đã biết kiểu dữ liệu mong đợi, để code thể hiện rõ hợp đồng đầu ra.

## 5. Đánh giá expression trên root object

Khi biểu thức tham chiếu property như `name` hoặc `address.city`, parser cần biết object gốc để phân giải những tên đó. Có thể truyền root object trực tiếp vào `getValue`.

Ví dụ một JavaBean:

~~~java
public class Person {
    private String name;

    public Person(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Tạo expression và đánh giá trên object:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

Person person = new Person("Lan");
String name = expression.getValue(person, String.class);

System.out.println(name); // Lan
~~~

Ở đây `person` là root object. SpEL phân giải `name` thông qua property accessors của evaluation mechanism. Có thể đi sâu vào object graph nếu các property trung gian tồn tại:

~~~java
Expression cityExpression =
        parser.parseExpression("address.city");

String city = cityExpression.getValue(person, String.class);
~~~

Ví dụ thứ hai chỉ đánh giá thành công nếu object được truyền vào có property `address` và object đó có property `city`. Nếu một property không tồn tại hoặc giá trị trung gian là null, việc đánh giá có thể phát sinh lỗi tùy biểu thức và cấu hình parser.

## 6. Dùng EvaluationContext cho root object và biến

Khi cần khai báo biến hoặc tùy chỉnh cách expression truy cập dữ liệu, hãy dùng `EvaluationContext`. `StandardEvaluationContext` cung cấp khả năng đánh giá đầy đủ hơn, bao gồm root object, variables, property accessors, method resolvers, type locator và bean resolver khi được cấu hình.

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

ExpressionParser parser = new SpelExpressionParser();

Person person = new Person("Lan");
StandardEvaluationContext context =
        new StandardEvaluationContext(person);

context.setVariable("prefix", "Hello");

Expression expression =
        parser.parseExpression("#prefix + ' ' + name");

String greeting = expression.getValue(context, String.class);

System.out.println(greeting); // Hello Lan
~~~

Một số quy tắc cần nhớ:

- Tên biến trong context được tham chiếu bằng tiền tố `#`, ví dụ `#prefix`.
- Root object được truy cập trực tiếp bằng tên property, ví dụ `name`.
- `#root` đại diện cho root object hiện tại.
- `#this` đại diện cho object đang được xử lý ở vị trí hiện tại trong một phép chiếu hoặc lựa chọn collection.

Có thể đặt nhiều biến:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("quantity", 3);
context.setVariable("unitPrice", 12.5);

Expression expression =
        parser.parseExpression("#quantity * #unitPrice");

Double subtotal = expression.getValue(context, Double.class);
~~~

Việc tách dữ liệu đầu vào thành variables giúp biểu thức không phải nhúng dữ liệu thực tế vào chuỗi. Cách này cũng giúp tái sử dụng cùng một expression với nhiều bộ giá trị khác nhau.

## 7. Phân biệt parse expression và evaluate expression

Hai thao tác này có trách nhiệm khác nhau:

~~~java
Expression expression = parser.parseExpression("total * 1.1");
BigDecimal amount = expression.getValue(order, BigDecimal.class);
~~~

- `parseExpression` kiểm tra và phân tích cú pháp chuỗi. Nó tạo một biểu diễn `Expression` để sử dụng về sau.
- `getValue` đánh giá biểu thức trên root object hoặc evaluation context cụ thể. Lỗi do property không tồn tại, dữ liệu null, method không thể gọi hoặc chuyển đổi kiểu thường xuất hiện ở bước này.

Vì vậy, một chuỗi có cú pháp hợp lệ vẫn có thể không đánh giá được với một object cụ thể. Ví dụ `customer.name` có thể parse thành công nhưng thất bại khi root object không có property `customer`, hoặc property đó không thể cung cấp giá trị phù hợp.

Nếu ứng dụng đánh giá cùng một biểu thức nhiều lần, có thể parse trước rồi giữ lại `Expression` để tái sử dụng thay vì parse lại chuỗi ở mỗi lần gọi:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression discountExpression =
        parser.parseExpression("total > 1000 ? total * 0.9 : total");

// Mỗi lần đánh giá, truyền object đơn hàng tương ứng.
BigDecimal firstDiscount =
        discountExpression.getValue(firstOrder, BigDecimal.class);
BigDecimal secondDiscount =
        discountExpression.getValue(secondOrder, BigDecimal.class);
~~~

Cách này phân tách phần cấu trúc biểu thức khỏi dữ liệu runtime và làm luồng xử lý dễ đọc hơn.

## 8. Dùng ParserContext khi chuỗi là template

Mặc định, `parseExpression(String)` hiểu toàn bộ chuỗi là một biểu thức. Nếu chuỗi có văn bản cố định xen kẽ các đoạn SpEL, hãy truyền thêm `ParserContext`, thường là `TemplateParserContext`:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ParserContext;
import org.springframework.expression.common.TemplateParserContext;

ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
        "Hello #{#person.name}, your score is #{#score}",
        templateContext);
~~~

Khi đánh giá, các đoạn nằm trong `#{...}` được xử lý như SpEL; văn bản nằm ngoài được giữ nguyên và ghép vào kết quả:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("person", new Person("Lan"));
context.setVariable("score", 95);

String message = expression.getValue(context, String.class);
// Hello Lan, your score is 95
~~~

Có thể chọn prefix và suffix khác bằng constructor của `TemplateParserContext`:

~~~java
ParserContext customTemplate =
        new TemplateParserContext("${", "}");

Expression expression = parser.parseExpression(
        "Hello ${#person.name}",
        customTemplate);
~~~

Chỉ dùng template context khi đầu vào thực sự là template. Nếu truyền chuỗi có cả văn bản thông thường vào parser mặc định, parser sẽ cố phân tích toàn bộ chuỗi như một biểu thức và có thể báo lỗi cú pháp.

## 9. Cấu hình parser khi cần tự động mở rộng object/collection

Trong một số tình huống, SpEL cần tự khởi tạo property null hoặc mở rộng collection khi truy cập index vượt kích thước hiện tại. Có thể cấu hình hành vi này bằng `SpelParserConfiguration`:

~~~java
import org.springframework.expression.spel.SpelParserConfiguration;
import org.springframework.expression.spel.standard.SpelExpressionParser;

SpelParserConfiguration configuration =
        new SpelParserConfiguration(true, true);

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Hai cờ trong constructor này lần lượt bật auto-grow cho null references và collections. Khi bật, việc đánh giá một expression có thể làm thay đổi object graph hoặc kích thước collection để đáp ứng đường dẫn truy cập. Chỉ bật khi hành vi đó phù hợp với mô hình dữ liệu và giới hạn của ứng dụng; không nên coi nó là cơ chế khởi tạo object thay thế cho thiết kế domain rõ ràng.

## 10. Cập nhật giá trị qua Expression

Ngoài đọc giá trị, `Expression` còn có thể ghi vào property có thể ghi được:

~~~java
Person person = new Person("Lan");

Expression nameExpression = parser.parseExpression("name");
nameExpression.setValue(person, "Minh");

System.out.println(person.getName()); // Minh
~~~

Hoặc truyền evaluation context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(person);

Expression nameExpression = parser.parseExpression("name");
nameExpression.setValue(context, "Minh");
~~~

Thao tác ghi chỉ thành công khi property đích có thể được cập nhật thông qua property accessor phù hợp. Với object bất biến, property chỉ đọc hoặc collection không cho phép sửa, lời gọi có thể phát sinh lỗi. Hãy dùng `setValue` có chủ đích vì nó thay đổi trạng thái của object tại runtime.

## 11. Xử lý lỗi parse và lỗi evaluation

Có hai nhóm lỗi thường gặp:

- **Parse error**: chuỗi không đúng cú pháp SpEL, ví dụ thiếu dấu ngoặc, toán tử hoặc dấu nháy.
- **Evaluation error**: cú pháp hợp lệ nhưng không thể đánh giá trên dữ liệu/context hiện tại, ví dụ property không tồn tại, truy cập qua null, gọi method không phù hợp hoặc chuyển đổi kiểu thất bại.

API dùng các exception trong package `org.springframework.expression`, trong đó `ParseException` đại diện lỗi phân tích và `EvaluationException` đại diện lỗi đánh giá. Các exception cụ thể của SpEL có thể cung cấp vị trí ký tự và thông tin chi tiết hơn.

~~~java
import org.springframework.expression.EvaluationException;
import org.springframework.expression.ParseException;

try {
    Expression expression = parser.parseExpression("customer..name");
    String name = expression.getValue(order, String.class);
} catch (ParseException ex) {
    // Ghi nhận biểu thức có cú pháp không hợp lệ.
} catch (EvaluationException ex) {
    // Ghi nhận lỗi khi đánh giá trên dữ liệu/context.
}
~~~

Trong code thực tế, nên ghi log đủ thông tin để xác định biểu thức và ngữ cảnh lỗi nhưng tránh ghi dữ liệu nhạy cảm của object. Nếu biểu thức đến từ cấu hình, hãy kiểm tra cấu hình sớm khi ứng dụng khởi động để phát hiện lỗi trước khi request thật đi qua luồng xử lý.

## 12. Lưu ý về quyền truy cập và biểu thức không đáng tin cậy

`StandardEvaluationContext` có thể cho phép truy cập property, gọi method, tham chiếu type hoặc bean tùy các resolver/accessor được cấu hình. Vì vậy, không nên lấy chuỗi SpEL tùy ý từ người dùng rồi đánh giá với context đầy đủ quyền của ứng dụng.

Nếu chỉ cần data binding với tập property giới hạn, hãy cân nhắc `SimpleEvaluationContext` và cấu hình rõ những khả năng được phép. Việc chọn evaluation context cần dựa trên loại dữ liệu và thao tác mà biểu thức được phép thực hiện. Giới hạn context là một phần của thiết kế bảo mật, không chỉ là lựa chọn cú pháp.

## 13. Quy trình sử dụng thường gặp

Khi tích hợp SpEL trong một class Java, có thể đi theo trình tự sau:

1. Tạo `SpelExpressionParser` hoặc parser với cấu hình phù hợp.
2. Gọi `parseExpression` với biểu thức thuần; truyền `ParserContext` nếu đang xử lý template.
3. Chuẩn bị root object hoặc `EvaluationContext`, bao gồm variables cần dùng.
4. Gọi `getValue` với kiểu kết quả mong muốn.
5. Xử lý riêng lỗi parse và lỗi evaluation ở ranh giới phù hợp.
6. Tái sử dụng `Expression` khi cùng cấu trúc biểu thức được đánh giá nhiều lần.

Ví dụ tổng hợp:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "#quantity * #unitPrice");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("quantity", 4);
context.setVariable("unitPrice", 25);

BigDecimal total = expression.getValue(context, BigDecimal.class);
~~~

Ở ví dụ này, parser chỉ chịu trách nhiệm phân tích chuỗi. Context cung cấp dữ liệu đầu vào và expression trả về kết quả đã được đánh giá. Khi thay đổi quantity hoặc unitPrice, có thể cập nhật variables trong context rồi đánh giá lại cùng expression.

## 14. Ghi nhớ

- `SpelExpressionParser` là implementation dùng để phân tích chuỗi SpEL.
- `parseExpression` tạo `Expression`; `getValue` mới thực sự đánh giá expression trên dữ liệu.
- Với root object, property có thể được tham chiếu trực tiếp như `name`; variables trong context dùng tiền tố `#`.
- Dùng `StandardEvaluationContext` khi cần các khả năng đánh giá đầy đủ và `SimpleEvaluationContext` khi muốn giới hạn khả năng truy cập.
- Dùng `ParserContext`/`TemplateParserContext` khi chuỗi chứa văn bản cố định xen kẽ biểu thức.
- Có thể cấu hình auto-grow bằng `SpelParserConfiguration`, nhưng cần hiểu tác động lên object/collection.
- Phân biệt lỗi parse với lỗi evaluation để xử lý đúng nguyên nhân.
- Không đánh giá expression không đáng tin cậy bằng context có quyền truy cập rộng.
