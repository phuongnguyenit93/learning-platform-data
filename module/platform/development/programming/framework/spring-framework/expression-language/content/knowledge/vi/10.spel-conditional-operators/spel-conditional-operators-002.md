# Toán tử Elvis cho giá trị mặc định

Trong Spring Expression Language (SpEL), toán tử **Elvis** có cú pháp **?:** và được dùng để cung cấp giá trị thay thế khi biểu thức bên trái không có giá trị phù hợp. Đây là cách viết gọn cho tình huống: nếu một giá trị có sẵn thì dùng nó, nếu không thì dùng giá trị mặc định.

Ví dụ:

~~~text
#customerName ?: 'Guest'
~~~

Nếu customerName có giá trị, SpEL trả về giá trị đó. Nếu biến là null hoặc là chuỗi rỗng, SpEL trả về Guest. Elvis hữu ích khi đọc dữ liệu có thể thiếu, tạo tên hiển thị, lấy cấu hình dự phòng hoặc xây dựng một phần của cache key.

## 1. Cú pháp và cách hoạt động

Cú pháp tổng quát:

~~~text
expression ?: defaultExpression
~~~

SpEL đánh giá biểu thức bên trái trước:

1. Nếu kết quả bên trái không null và không phải chuỗi rỗng, kết quả đó được trả về.
2. Nếu kết quả bên trái là null hoặc chuỗi rỗng, SpEL đánh giá và trả về biểu thức mặc định bên phải.

Ví dụ:

~~~text
#nickname ?: 'Anonymous'
~~~

Có thể hiểu là: nếu nickname có giá trị thì trả về nickname, ngược lại trả về Anonymous. Biểu thức mặc định chỉ cần được đánh giá khi nhánh bên trái cần fallback.

## 2. Những giá trị nào kích hoạt fallback?

Elvis trong SpEL có hai trường hợp quan trọng khiến vế phải được chọn:

- Giá trị bên trái là **null**.
- Giá trị bên trái là **chuỗi rỗng** (empty String, độ dài bằng 0).

Các trường hợp còn lại thường được giữ nguyên, kể cả khi ứng dụng có thể xem chúng là “không có dữ liệu” theo một quy ước nghiệp vụ khác.

| Giá trị bên trái | Biểu thức | Kết quả |
| --- | --- | --- |
| null | **#value ?: 'default'** | 'default' |
| chuỗi rỗng | **#value ?: 'default'** | 'default' |
| 'Spring' | **#value ?: 'default'** | 'Spring' |
| '   ' | **#value ?: 'default'** | Chuỗi gồm dấu cách |
| 0 | **#value ?: 100** | 0 |
| false | **#value ?: true** | false |
| Danh sách rỗng | **#items ?: #fallbackItems** | Danh sách rỗng ban đầu |
| Optional.empty() | **#optional ?: #fallback** | Optional.empty() |

Điểm dễ nhầm nhất là **chuỗi chỉ chứa dấu cách không phải chuỗi rỗng**. Elvis không tự trim chuỗi và không kiểm tra whitespace-only theo nghĩa “blank”.

Tương tự, số 0, boolean false, collection rỗng và Optional rỗng đều khác null. Chúng không tự động kích hoạt fallback chỉ vì ứng dụng có thể xem chúng là “không có dữ liệu”.

## 3. Ví dụ với biến trong EvaluationContext

Có thể kiểm tra Elvis độc lập bằng SpEL parser và một EvaluationContext:

~~~java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("nickname", null);

String result = parser
        .parseExpression("#nickname ?: 'Guest'")
        .getValue(context, String.class);

System.out.println(result); // Guest
~~~

Đổi giá trị biến:

~~~java
context.setVariable("nickname", "Linh");

String result = parser
        .parseExpression("#nickname ?: 'Guest'")
        .getValue(context, String.class);

System.out.println(result); // Linh
~~~

Với chuỗi rỗng:

~~~java
context.setVariable("nickname", "");

String result = parser
        .parseExpression("#nickname ?: 'Guest'")
        .getValue(context, String.class);

System.out.println(result); // Guest
~~~

Với chuỗi chỉ chứa dấu cách:

~~~java
context.setVariable("nickname", "   ");

String result = parser
        .parseExpression("#nickname ?: 'Guest'")
        .getValue(context, String.class);

System.out.println("[" + result + "]"); // [   ]
~~~

Các ví dụ cho thấy Elvis kiểm tra null và empty String theo quy tắc của SpEL. Nếu muốn coi cả chuỗi chỉ có whitespace là thiếu dữ liệu, cần thêm bước kiểm tra blank riêng.

## 4. So sánh Elvis với toán tử ternary

Ternary operator có cú pháp:

~~~text
condition ? valueIfTrue : valueIfFalse
~~~

Ví dụ dùng ternary để cung cấp tên mặc định:

~~~text
#nickname != null ? #nickname : 'Guest'
~~~

Elvis viết ngắn hơn:

~~~text
#nickname ?: 'Guest'
~~~

| Tiêu chí | Ternary | Elvis |
| --- | --- | --- |
| Cú pháp | condition ? A : B | A ?: B |
| Điều kiện | Biểu thức điều kiện phải trả về boolean | Dựa trên kết quả của A |
| Trường hợp dùng phổ biến | Chọn hai nhánh theo điều kiện bất kỳ | Dùng giá trị dự phòng khi vế trái null hoặc chuỗi rỗng |
| Lặp lại biểu thức trái | Thường phải viết lại biểu thức | Chỉ viết biểu thức trái một lần |
| Kiểm tra chuỗi rỗng | Phải bổ sung điều kiện | Được hỗ trợ trực tiếp |

Ternary phù hợp khi điều kiện không chỉ là null/empty:

~~~text
#score >= 50 ? 'PASS' : 'FAIL'
~~~

Elvis phù hợp khi mục tiêu là lấy giá trị hiện có hoặc dùng giá trị mặc định:

~~~text
#displayName ?: 'Anonymous'
~~~

Không nên thay ternary bằng Elvis nếu điều kiện thực sự là một quy tắc nghiệp vụ, ví dụ phân loại theo điểm, trạng thái hoặc quyền truy cập.

## 5. Kết hợp Elvis với safe navigation

Safe-navigation operator **?.** cho phép truy cập property hoặc gọi method mà không gây lỗi chỉ vì đối tượng nhận đang null. Khi đối tượng bên trái là null, phần truy cập đó trả về null.

Elvis có thể nhận kết quả null này và cung cấp giá trị thay thế:

~~~text
#customer?.nickname ?: 'Guest'
~~~

Cách đọc:

1. Lấy biến customer.
2. Nếu customer khác null, đọc nickname.
3. Nếu customer null, kết quả của phần safe navigation là null.
4. Nếu nickname là null hoặc chuỗi rỗng, trả về Guest.

Với object lồng nhau, dùng safe navigation ở từng bước có thể null:

~~~text
#order?.shippingAddress?.city ?: 'Unknown'
~~~

Cách này tránh lỗi khi order hoặc shippingAddress là null, đồng thời cung cấp Unknown nếu city không có giá trị hoặc là chuỗi rỗng.

Một ví dụ với tên hiển thị:

~~~text
#profile?.nickname ?: #profile?.fullName ?: 'Anonymous'
~~~

SpEL lần lượt ưu tiên nickname, sau đó fullName, cuối cùng dùng Anonymous. Có thể thêm dấu ngoặc khi biểu thức fallback dài để người đọc thấy rõ thứ tự lựa chọn:

~~~text
#profile?.nickname ?: (#profile?.fullName ?: 'Anonymous')
~~~

Safe navigation và Elvis giải quyết hai việc khác nhau:

- **?.** bảo vệ thao tác truy cập khi đối tượng nhận có thể null.
- **?:** cung cấp giá trị thay thế khi kết quả bên trái là null hoặc chuỗi rỗng.

Không nên dùng một toán tử để thay thế vai trò của toán tử còn lại.

## 6. Dùng Elvis cho giá trị cấu hình và @Value

Một ứng dụng có thể cần giá trị dự phòng nếu system property không được thiết lập. Với @Value, biểu thức SpEL có thể đọc system property rồi dùng Elvis:

~~~java
@Component
class RuntimeSettings {

    @Value("#{systemProperties['app.region'] ?: 'ap-southeast-1'}")
    private String region;
}
~~~

Nếu system property app.region không tồn tại hoặc là chuỗi rỗng, region nhận giá trị ap-southeast-1. Nếu property có giá trị, giá trị đó được sử dụng.

Có thể dùng cách tương tự để cung cấp nhãn mặc định:

~~~java
@Value("#{systemProperties['app.display-name'] ?: 'Spring Application'}")
private String displayName;
~~~

Cần phân biệt Elvis với default value của property placeholder:

~~~java
@Value("${{app.region:ap-southeast-1}")
private String region;
~~~

Hai cơ chế đều có thể tạo giá trị mặc định nhưng hoạt động ở các lớp khác nhau:

- **Property placeholder** lấy giá trị từ nguồn cấu hình của Spring và cho phép khai báo fallback ngay trong cú pháp placeholder.
- **SpEL Elvis** đánh giá một expression. Vế trái có thể là property, biến, phép truy cập object hoặc lời gọi method mà EvaluationContext cho phép.

Nếu chỉ cần đọc một property và đặt giá trị mặc định, placeholder thường đơn giản hơn. Dùng Elvis khi cần kết hợp nhiều giá trị hoặc xử lý kết quả của một biểu thức.

## 7. Dùng Elvis với Map, request và cache key

### 7.1. Lấy giá trị mặc định từ Map

Khi đọc một key có thể không tồn tại:

~~~text
#settings['locale'] ?: 'vi-VN'
~~~

Nếu map không có key locale, giá trị truy cập trả về null và Elvis chọn vi-VN. Nếu key có giá trị là chuỗi rỗng, Elvis cũng chọn vi-VN.

Có thể kết hợp với giá trị khác:

~~~text
#settings['locale'] ?: #user?.preferredLocale ?: 'vi-VN'
~~~

Thứ tự ưu tiên là locale trong settings, preferredLocale của user, rồi mới đến vi-VN.

### 7.2. Tạo cache key có giá trị mặc định

Trong cache annotation, Elvis có thể giúp tránh một phần key bị null:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#request?.tenantId ?: 'public'"
)
public Product findProduct(ProductRequest request) {
    // ...
}
~~~

Nếu tenantId không có hoặc là chuỗi rỗng, expression dùng public làm phần tenant của key.

Khi dùng kiểu này, cần bảo đảm giá trị mặc định thực sự đại diện cho một tenant hoặc namespace công khai hợp lệ. Nếu nhiều tenant bị gộp chung vào key public, dữ liệu có thể bị dùng chung ngoài ý muốn. Với cache đa tenant, hãy chọn fallback theo đúng quy tắc phân vùng dữ liệu.

### 7.3. Kết hợp với điều kiện nghiệp vụ

Elvis chỉ chọn giá trị mặc định; nó không thay thế kiểm tra nghiệp vụ. Ví dụ:

~~~text
(#request?.tenantId ?: 'public') == 'public'
~~~

Expression trên lấy tenantId hoặc public, sau đó so sánh kết quả với public. Nếu cần kiểm tra người dùng có quyền truy cập tenant, phải thực hiện thêm điều kiện authorization phù hợp.

## 8. Khi nào Elvis không đủ để xử lý blank?

Elvis chỉ coi null và chuỗi rỗng là thiếu dữ liệu. Trong nhiều ứng dụng, chuỗi chỉ chứa dấu cách, tab hoặc newline cũng cần được xem là blank.

Ví dụ:

~~~text
#name ?: 'Guest'
~~~

Với name bằng ba dấu cách, expression trả về ba dấu cách. Nếu yêu cầu là null, empty hoặc whitespace-only đều phải dùng Guest, hãy dùng helper có tên thể hiện rõ quy tắc:

~~~java
@Component("stringPolicy")
class StringPolicy {

    public String defaultIfBlank(String value, String fallback) {
        if (value == null || value.trim().isEmpty()) {
            return fallback;
        }
        return value;
    }
}
~~~

Expression:

~~~text
@stringPolicy.defaultIfBlank(#name, 'Guest')
~~~

Trong một ứng dụng Spring, bean phải có tên stringPolicy và EvaluationContext phải cho phép bean reference. Nếu muốn hỗ trợ đầy đủ Unicode whitespace theo định nghĩa của ứng dụng, hãy chọn API kiểm tra blank phù hợp với phiên bản Java và quy ước dữ liệu của dự án.

Không nên viết một expression dài để mô phỏng toàn bộ chính sách chuẩn hóa chuỗi nếu logic đó được dùng ở nhiều nơi. Đưa quy tắc vào helper Java giúp tái sử dụng và kiểm thử dễ hơn.

## 9. Những trường hợp cần cẩn thận

### 9.1. Vế trái có thể gây lỗi trước khi Elvis được áp dụng

Elvis chỉ xử lý kết quả của biểu thức bên trái sau khi biểu thức đó đã được đánh giá. Nếu phép truy cập property hoặc method ở bên trái ném exception, Elvis không thể tự biến exception đó thành giá trị mặc định.

Không an toàn:

~~~text
#customer.address.city ?: 'Unknown'
~~~

Nếu customer null, việc truy cập address có thể lỗi trước khi Elvis nhận kết quả.

An toàn hơn:

~~~text
#customer?.address?.city ?: 'Unknown'
~~~

### 9.2. Không dùng Elvis để che lỗi dữ liệu

Nếu một property bắt buộc phải tồn tại, việc âm thầm thay bằng giá trị mặc định có thể che giấu lỗi cấu hình hoặc lỗi dữ liệu. Hãy dùng fallback cho trường hợp thiếu dữ liệu đã được chấp nhận trong nghiệp vụ; với dữ liệu bắt buộc, nên xác thực và báo lỗi rõ ràng.

### 9.3. Kiểu trả về của hai nhánh cần tương thích

Biểu thức Elvis có thể trả về giá trị bên trái hoặc bên phải. Khi lấy kết quả theo một kiểu Java cụ thể, hai nhánh cần có kiểu tương thích hoặc có thể chuyển đổi theo cơ chế conversion của SpEL.

Ví dụ:

~~~java
Integer limit = parser
        .parseExpression("#configuredLimit ?: 100")
        .getValue(context, Integer.class);
~~~

Nếu configuredLimit có kiểu không tương thích với Integer, việc chuyển đổi có thể thất bại. Hãy giữ kiểu dữ liệu của giá trị mặc định nhất quán với kiểu kết quả mong muốn.

### 9.4. Optional rỗng không đồng nghĩa null

Một Optional.empty() vẫn là một object Optional khác null. Vì vậy:

~~~text
#optional ?: #fallback
~~~

không tự động lấy fallback chỉ vì Optional không chứa giá trị. Hãy unwrap Optional trước hoặc gọi helper xử lý Optional theo đúng quy tắc nghiệp vụ.

## 10. Kiểm thử Elvis expression

Có thể viết unit test nhỏ để kiểm tra các trường hợp fallback:

~~~java
class ElvisExpressionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private final StandardEvaluationContext context =
            new StandardEvaluationContext();

    @Test
    void returnsFallbackForNull() {
        context.setVariable("name", null);

        String result = parser
                .parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class);

        assertEquals("Guest", result);
    }

    @Test
    void returnsFallbackForEmptyString() {
        context.setVariable("name", "");

        String result = parser
                .parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class);

        assertEquals("Guest", result);
    }

    @Test
    void preservesNonEmptyString() {
        context.setVariable("name", "Spring");

        String result = parser
                .parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class);

        assertEquals("Spring", result);
    }

    @Test
    void preservesWhitespaceOnlyString() {
        context.setVariable("name", "   ");

        String result = parser
                .parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class);

        assertEquals("   ", result);
    }
}
~~~

Các test trên kiểm tra parser và hành vi expression trong EvaluationContext độc lập. Nếu Elvis được dùng trong @Value, @Cacheable hoặc một integration point khác, nên có kiểm thử ở đúng thành phần đó để xác nhận context và thời điểm đánh giá.

## 11. Ghi nhớ nhanh

- Elvis có cú pháp **A ?: B**: lấy A nếu A có giá trị, nếu không lấy B.
- Trong SpEL, fallback được dùng khi vế trái là null hoặc chuỗi rỗng.
- Chuỗi chỉ có whitespace không tự động được coi là empty.
- Số 0, boolean false, collection rỗng và Optional.empty() không tự kích hoạt fallback.
- Ternary **condition ? A : B** dùng điều kiện boolean; Elvis ngắn gọn cho lựa chọn giá trị dự phòng.
- Kết hợp **?.** với **?:** để truy cập object có thể null rồi cung cấp giá trị mặc định.
- Elvis không bắt exception phát sinh trong lúc đánh giá vế trái.
- Dùng property placeholder khi chỉ cần default cho cấu hình; dùng SpEL Elvis khi cần fallback cho kết quả expression.
- Với quy tắc blank hoặc nghiệp vụ phức tạp, gọi helper Java có tên rõ ràng.
- Kiểm thử cả null, empty string, whitespace-only và giá trị hợp lệ.

## 12. Tài liệu tham khảo chính thức

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-ternary.html)
- [Spring Framework — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework — @Value Annotation](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
