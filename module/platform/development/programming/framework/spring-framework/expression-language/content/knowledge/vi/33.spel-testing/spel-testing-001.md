# Kiểm thử expression SpEL độc lập với ApplicationContext lớn

Spring Expression Language (SpEL) có thể được kiểm thử trực tiếp mà không cần khởi động toàn bộ ứng dụng Spring. Với phần lớn biểu thức, chỉ cần một SpelExpressionParser, một EvaluationContext nhỏ và root object chứa dữ liệu cần thiết. Cách này giúp unit test chạy nhanh, xác định rõ đầu vào và phát hiện lỗi cú pháp hoặc lỗi đánh giá ngay tại nơi biểu thức được sử dụng.

Chỉ những phần phụ thuộc vào cơ chế tích hợp của Spring container, chẳng hạn xử lý annotation @Value hoặc phân giải bean reference theo cấu hình thực tế, mới cần một bean factory hoặc ApplicationContext nhỏ. Không nhất thiết phải tải toàn bộ component scan, database, web server, messaging và các dịch vụ bên ngoài để kiểm thử một expression.

Bài này trình bày cách tách kiểm thử SpEL khỏi ApplicationContext lớn, tạo root object và biến kiểm thử, đăng ký bean tối thiểu khi cần, kiểm tra kết quả và lỗi, kiểm thử collection expression, cũng như xác định khi nào cần một integration test nhẹ.

## 1. Vì sao nên kiểm thử expression độc lập?

Một expression thường chỉ cần ba thành phần:

1. Chuỗi biểu thức cần phân tích.
2. Dữ liệu đầu vào, thường là root object và các biến.
3. EvaluationContext xác định những khả năng mà biểu thức được phép sử dụng.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(
                new OrderView("PAID", new BigDecimal("150.00"))
        );

Expression expression = parser.parseExpression(
        "status == 'PAID' and total >= 100"
);

Boolean result = expression.getValue(context, Boolean.class);
~~~

Không có ApplicationContext trong ví dụ này. SpEL đọc property từ OrderView được đặt làm root object và trả về Boolean.

Nếu kiểm thử expression bằng cách khởi động toàn bộ ứng dụng, test có thể chậm và thất bại vì cấu hình không liên quan đến biểu thức, chẳng hạn kết nối database, biến môi trường hoặc dịch vụ bên ngoài. Tách expression thành unit test giúp phân biệt lỗi logic biểu thức với lỗi khởi động ứng dụng.

## 2. Phân biệt unit test và integration test

Không phải mọi kiểm thử SpEL đều cần cùng một mức Spring infrastructure.

| Loại kiểm thử | Thành phần cần dùng | Mục đích |
|---|---|---|
| Unit test expression | SpelExpressionParser, EvaluationContext, root object | Kiểm tra cú pháp và kết quả trên dữ liệu xác định |
| Unit test có bean reference | Parser, context và BeanResolver tối thiểu | Kiểm tra lời gọi bean được cung cấp cho expression |
| Integration test @Value | Một context nhỏ với cấu hình test | Kiểm tra Spring thực sự xử lý annotation và inject giá trị |
| Integration test ứng dụng | ApplicationContext gần với cấu hình thực tế | Kiểm tra các thành phần tích hợp với nhau khi điều đó là mục tiêu |

Hãy bắt đầu ở mức nhỏ nhất đáp ứng mục tiêu kiểm thử. Nếu chỉ kiểm tra phép so sánh total hoặc selection trên một List, parser và root object là đủ. Nếu cần xác nhận @Value trên tham số @Bean được xử lý đúng, hãy tạo một context nhỏ chỉ chứa cấu hình và bean liên quan.

## 3. Tạo root object kiểm thử nhỏ

Root object nên là DTO hoặc view object có các property mà expression sử dụng. Không cần đưa toàn bộ entity graph hoặc service của ứng dụng vào test.

Ví dụ:

~~~java
public class OrderView {
    private final String status;
    private final BigDecimal total;

    public OrderView(String status, BigDecimal total) {
        this.status = status;
        this.total = total;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Dùng object này trong test:

~~~java
@Test
void evaluatesAgainstRootObject() {
    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
            new StandardEvaluationContext(
                    new OrderView(
                            "PAID",
                            new BigDecimal("150.00")
                    )
            );

    Boolean result = parser.parseExpression(
            "status == 'PAID' and total >= 100"
    ).getValue(context, Boolean.class);

    assertTrue(result);
}
~~~

Test chỉ cần khởi tạo dữ liệu và đánh giá expression. Không cần tạo repository, service, controller hoặc ApplicationContext.

Nên tạo root object mới cho mỗi test khi dữ liệu có thể thay đổi. Điều này tránh một test làm thay đổi trạng thái và ảnh hưởng đến test khác.

## 4. Dùng một helper tạo EvaluationContext

Nếu nhiều test dùng cùng loại context, có thể tạo một helper nhỏ để giảm mã lặp:

~~~java
private StandardEvaluationContext contextFor(Object root) {
    return new StandardEvaluationContext(root);
}
~~~

Sử dụng:

~~~java
@Test
void checksMinimumTotal() {
    OrderView order =
            new OrderView("PAID", new BigDecimal("250.00"));

    StandardEvaluationContext context = contextFor(order);

    Boolean result = new SpelExpressionParser()
            .parseExpression("total >= 200")
            .getValue(context, Boolean.class);

    assertTrue(result);
}
~~~

Helper chỉ nên gom phần thiết lập thật sự dùng chung. Nếu một biểu thức cần biến, bean resolver hoặc converter riêng, hãy thể hiện cấu hình đó rõ ràng trong test tương ứng thay vì tạo một context dùng chung quá rộng.

## 5. Kiểm thử biến trong EvaluationContext

Khi expression sử dụng biến có tiền tố #, đăng ký giá trị bằng setVariable():

~~~java
@Test
void evaluatesWithNamedVariable() {
    OrderView order =
            new OrderView("PAID", new BigDecimal("150.00"));

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", new BigDecimal("100.00"));

    Expression expression = new SpelExpressionParser()
            .parseExpression("total >= #minimumTotal");

    Boolean result = expression.getValue(context, Boolean.class);

    assertTrue(result);
}
~~~

Test này xác nhận hai nguồn dữ liệu được kết hợp đúng: total đến từ root object, còn minimumTotal đến từ biến trong context.

Để kiểm tra trường hợp biên, thay đổi giá trị biến:

~~~java
context.setVariable("minimumTotal", new BigDecimal("200.00"));
~~~

Khi đó kết quả phải là false. Nên có test cho cả nhánh đúng và nhánh sai để biểu thức không chỉ được kiểm tra với một bộ dữ liệu.

## 6. Kiểm thử nhiều bộ dữ liệu cho cùng expression

Một Expression có thể được đánh giá nhiều lần với root object khác nhau. Điều này hữu ích khi muốn xác nhận quy tắc hoạt động trên nhiều trường hợp mà không cần parse lại chuỗi trong từng test.

~~~java
@Test
void evaluatesSameExpressionForDifferentOrders() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
            parser.parseExpression("status == 'PAID' and total >= 100");

    StandardEvaluationContext firstContext =
            new StandardEvaluationContext(
                    new OrderView("PAID", new BigDecimal("120.00"))
            );

    StandardEvaluationContext secondContext =
            new StandardEvaluationContext(
                    new OrderView("PENDING", new BigDecimal("250.00"))
            );

    assertTrue(expression.getValue(firstContext, Boolean.class));
    assertFalse(expression.getValue(secondContext, Boolean.class));
}
~~~

Mỗi context chứa root object riêng. Cách này tránh thay đổi root object trong một context đang được chia sẻ.

Có thể dùng một helper hoặc parameterized test của JUnit để kiểm tra nhiều bộ dữ liệu. Với quy tắc có nhiều trường hợp, parameterized test thường giúp bảng dữ liệu đầu vào và kết quả mong đợi dễ đọc hơn.

## 7. Kiểm thử selection và projection trên collection

Các expression làm việc với collection cũng có thể được kiểm thử mà không cần Spring container.

Ví dụ model:

~~~java
public class OrderView {
    private final String code;
    private final String status;
    private final BigDecimal total;

    public OrderView(String code, String status, BigDecimal total) {
        this.code = code;
        this.status = status;
        this.total = total;
    }

    public String getCode() {
        return code;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}

public class OrderReport {
    private final List<OrderView> orders;

    public OrderReport(List<OrderView> orders) {
        this.orders = orders;
    }

    public List<OrderView> getOrders() {
        return orders;
    }
}
~~~

Test selection rồi projection:

~~~java
@Test
void selectsPaidOrdersAndProjectsTotals() {
    OrderReport report = new OrderReport(Arrays.asList(
            new OrderView("A-1", "PAID", new BigDecimal("120.00")),
            new OrderView("A-2", "PENDING", new BigDecimal("80.00")),
            new OrderView("A-3", "PAID", new BigDecimal("250.00"))
    ));

    StandardEvaluationContext context =
            new StandardEvaluationContext(report);

    Expression expression = new SpelExpressionParser()
            .parseExpression("orders.?[status == 'PAID'].![total]");

    List<?> totals = expression.getValue(context, List.class);

    assertEquals(
            Arrays.asList(
                    new BigDecimal("120.00"),
                    new BigDecimal("250.00")
            ),
            totals
    );
}
~~~

Test này kiểm tra cả điều kiện selection và kết quả projection. Khi có lỗi, có thể tách thành hai test nhỏ: một test xác nhận các order được chọn, một test xác nhận các total được tạo ra.

Nên thêm trường hợp collection rỗng và trường hợp không có phần tử thỏa điều kiện. Điều đó giúp xác định rõ biểu thức trả về List rỗng hay null theo đúng loại toán tử đang dùng.

## 8. Kiểm thử function được đăng ký trong context

Nếu expression gọi function bằng cú pháp #functionName(...), test cần đăng ký function vào EvaluationContext.

Ví dụ function:

~~~java
public final class TestFunctions {
    private TestFunctions() {
    }

    public static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

Đăng ký function:

~~~java
@Test
void evaluatesRegisteredFunction() throws NoSuchMethodException {
    Method normalize = TestFunctions.class.getDeclaredMethod(
            "normalize",
            String.class
    );

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.registerFunction("normalize", normalize);

    String result = new SpelExpressionParser()
            .parseExpression("#normalize('  Spring  ')")
            .getValue(context, String.class);

    assertEquals("spring", result);
}
~~~

Test tự cấu hình đúng function mà expression cần. Không phải khởi tạo ứng dụng hoặc component scan lớp tiện ích.

Nếu function phụ thuộc nhiều service hoặc trạng thái ứng dụng, hãy cân nhắc chuyển logic đó sang một lớp có thể unit test trực tiếp. Một function SpEL nên có đầu vào và kết quả rõ ràng.

## 9. Kiểm thử bean reference bằng BeanFactory tối thiểu

Expression có cú pháp @beanName cần BeanResolver. Nếu chỉ muốn kiểm tra việc phân giải bean, không cần khởi động ApplicationContext lớn. Có thể dùng một DefaultListableBeanFactory nhỏ và BeanFactoryResolver.

~~~java
@Test
void resolvesOnlyTheBeanUsedByExpression() {
    DefaultListableBeanFactory beanFactory =
            new DefaultListableBeanFactory();

    beanFactory.registerSingleton(
            "pricingService",
            new PricingService(new BigDecimal("0.10"))
    );

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setBeanResolver(new BeanFactoryResolver(beanFactory));

    BigDecimal rate = new SpelExpressionParser()
            .parseExpression("@pricingService.discountRate")
            .getValue(context, BigDecimal.class);

    assertEquals(new BigDecimal("0.10"), rate);
}
~~~

BeanFactory chỉ chứa bean cần cho test. Không có component scan hoặc các dependency không liên quan.

Cách này kiểm tra cú pháp bean reference và BeanFactoryResolver. Nếu cần xác nhận cấu hình @Value, lifecycle hoặc bean post-processor của ứng dụng, hãy dùng một integration test riêng với context nhỏ.

## 10. Kiểm thử lỗi parse và lỗi evaluation

Nên kiểm tra cả expression hợp lệ và expression không hợp lệ. Có hai nhóm lỗi cần phân biệt:

- Parse error xảy ra khi chuỗi không đúng cú pháp SpEL.
- Evaluation error xảy ra khi expression được phân tích nhưng không thể đánh giá trên context hoặc dữ liệu hiện tại.

Ví dụ test lỗi cú pháp:

~~~java
@Test
void rejectsInvalidExpressionSyntax() {
    ExpressionParser parser = new SpelExpressionParser();

    assertThrows(
            SpelParseException.class,
            () -> parser.parseExpression("total >")
    );
}
~~~

Ví dụ test property không tồn tại:

~~~java
@Test
void reportsMissingPropertyDuringEvaluation() {
    StandardEvaluationContext context =
            new StandardEvaluationContext(
                    new OrderView("PAID", new BigDecimal("100.00"))
            );

    Expression expression = new SpelExpressionParser()
            .parseExpression("unknownProperty");

    assertThrows(
            SpelEvaluationException.class,
            () -> expression.getValue(context)
    );
}
~~~

Không nên chỉ kiểm tra rằng một exception bất kỳ được ném ra nếu mục tiêu là xác nhận loại lỗi cụ thể. Khi cần kiểm tra thông báo lỗi, ưu tiên kiểm tra mã lỗi hoặc phần thông tin ổn định được API cung cấp; tránh phụ thuộc vào toàn bộ chuỗi thông báo có thể thay đổi giữa các phiên bản.

## 11. Kiểm thử null và giá trị biên

Property có thể null hoặc collection có thể rỗng. Nên tạo dữ liệu test cho các tình huống này thay vì chỉ kiểm tra trường hợp bình thường.

Ví dụ safe navigation:

~~~java
public class ContactView {
    private final String email;

    public ContactView(String email) {
        this.email = email;
    }

    public String getEmail() {
        return email;
    }
}

public class CustomerView {
    private final ContactView contact;

    public CustomerView(ContactView contact) {
        this.contact = contact;
    }

    public ContactView getContact() {
        return contact;
    }
}
~~~

Test:

~~~java
@Test
void returnsNullForMissingNestedObjectWithSafeNavigation() {
    CustomerView customer = new CustomerView(null);

    StandardEvaluationContext context =
            new StandardEvaluationContext(customer);

    String email = new SpelExpressionParser()
            .parseExpression("contact?.email")
            .getValue(context, String.class);

    assertNull(email);
}
~~~

Các trường hợp nên có trong test suite:

- Root object null nếu API đánh giá cho phép tình huống đó.
- Property lồng nhau null.
- Collection rỗng.
- Không có phần tử phù hợp trong selection.
- Giá trị đúng tại ngưỡng so sánh.
- Chuỗi rỗng và chuỗi chỉ chứa khoảng trắng.
- Số âm, số 0 và giá trị lớn.
- Kiểu kết quả null hoặc không đúng kiểu hợp đồng.

Không nên mặc định null và collection rỗng có cùng ý nghĩa. Test cần phản ánh hợp đồng dữ liệu của ứng dụng.

## 12. Kiểm thử chuyển đổi kiểu

Nếu ứng dụng yêu cầu một kiểu kết quả cụ thể, kiểm tra kết quả bằng overload getValue(context, resultType) hoặc bằng cơ chế chuyển đổi được cấu hình.

~~~java
@Test
void returnsExpectedResultType() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Integer result = new SpelExpressionParser()
            .parseExpression("'42'")
            .getValue(context, Integer.class);

    assertEquals(Integer.valueOf(42), result);
}
~~~

Test này kiểm tra khả năng chuyển đổi chuỗi số thành Integer trong môi trường đánh giá đang dùng.

Nếu ứng dụng đăng ký converter tùy chỉnh, hãy viết test riêng cho converter và test expression ở mức tích hợp phù hợp. Không nên giả định một context tự tạo có cùng ConversionService với ApplicationContext của ứng dụng.

## 13. Kiểm thử @Value bằng context nhỏ

Unit test trực tiếp không kiểm tra việc Spring xử lý annotation @Value. Khi mục tiêu là xác nhận tham số @Bean hoặc field thực sự được inject, hãy tạo một context nhỏ chỉ chứa cấu hình cần thiết.

Ví dụ:

~~~java
@Configuration
static class ValueTestConfiguration {

    @Bean
    TestSettings testSettings(
            @Value("#{2 * 3}") Integer limit) {
        return new TestSettings(limit);
    }
}

static class TestSettings {
    private final Integer limit;

    TestSettings(Integer limit) {
        this.limit = limit;
    }

    Integer getLimit() {
        return limit;
    }
}
~~~

Integration test:

~~~java
@Test
void processesValueExpressionOnBeanMethodParameter() {
    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                         ValueTestConfiguration.class
                 )) {

        TestSettings settings =
                context.getBean(TestSettings.class);

        assertEquals(Integer.valueOf(6), settings.getLimit());
    }
}
~~~

Context chỉ đăng ký một cấu hình test và bean cần thiết. Test xác nhận cơ chế Spring xử lý @Value, chứ không chỉ xác nhận SpEL parser tự đánh giá biểu thức.

Nếu cần kiểm tra placeholder hoặc bean reference trong @Value, thêm đúng property source hoặc bean test vào cấu hình nhỏ. Không cần import toàn bộ cấu hình production.

## 14. Kiểm thử độc lập với database, web và dịch vụ ngoài

Một expression test thường không cần:

- Kết nối database hoặc repository thật.
- Khởi động web server.
- Gửi HTTP request.
- Kết nối message broker.
- Gọi dịch vụ bên ngoài.
- Tải toàn bộ component scan của ứng dụng.

Hãy cung cấp DTO và dữ liệu mẫu trực tiếp trong test. Nếu expression cần một service, dùng implementation nhỏ hoặc fake phù hợp với mục tiêu test.

Ví dụ, thay vì tạo toàn bộ PricingService với repository và HTTP client, tạo một đối tượng test chỉ cung cấp property discountRate mà expression cần đọc.

Nếu mục tiêu là kiểm tra tích hợp với service thật, đó là một integration test khác. Tách mục tiêu giúp test nhanh và giúp lỗi chỉ ra đúng lớp đang gặp vấn đề.

## 15. Tổ chức test theo trách nhiệm

Có thể tổ chức test suite thành các nhóm:

| Nhóm | Nội dung |
|---|---|
| Syntax tests | Expression parse thành công hoặc thất bại theo dự kiến |
| Evaluation tests | Kết quả đúng trên root object và biến |
| Collection tests | Selection, projection, map và collection rỗng |
| Resolver tests | Function hoặc bean reference được cấu hình đúng |
| Conversion tests | Kết quả được chuyển sang kiểu đích |
| Boundary tests | Null, giá trị biên và dữ liệu không hợp lệ |
| Spring integration tests | @Value, bean lifecycle và cấu hình container tối thiểu |

Tên test nên mô tả hành vi và điều kiện, chẳng hạn evaluatesPaidOrder, returnsFalseBelowMinimum hoặc rejectsUnknownProperty. Tránh đặt tên chung như testExpression1 vì khó biết test đang bảo vệ quy tắc nào.

Giữ mỗi test tập trung vào một hành vi chính. Khi một test vừa khởi động context, truy vấn database, gọi HTTP và đánh giá SpEL, lỗi sẽ khó khoanh vùng.

## 16. Quản lý parser, Expression và EvaluationContext trong test

Parser có thể được tạo một lần trong lớp test nếu cấu hình parser giống nhau. Expression có thể được tạo từ parser rồi đánh giá trên context và root object phù hợp.

EvaluationContext thường chứa trạng thái như root object, biến và resolver. Vì vậy, tránh chia sẻ một context mutable giữa các test chạy song song.

Một cách tổ chức:

~~~java
class OrderExpressionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private StandardEvaluationContext contextFor(OrderView order) {
        return new StandardEvaluationContext(order);
    }

    @Test
    void matchesPaidOrder() {
        StandardEvaluationContext context = contextFor(
                new OrderView("PAID", new BigDecimal("120.00"))
        );

        Boolean result = parser.parseExpression(
                "status == 'PAID'"
        ).getValue(context, Boolean.class);

        assertTrue(result);
    }
}
~~~

Mỗi test có context riêng và root object riêng. Nếu parser có cấu hình đặc biệt, tạo parser theo cấu hình đó và dùng cùng cấu hình trong test để kết quả phản ánh đúng ứng dụng.

Không nên lưu biến hoặc root object của một test vào context tĩnh dùng chung, vì điều đó có thể gây rò rỉ trạng thái giữa các test.

## 17. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Khởi động toàn bộ ApplicationContext cho phép so sánh đơn giản | Test kéo theo nhiều dependency không liên quan. | Dùng parser và EvaluationContext trực tiếp. |
| Root object test chứa quá nhiều dependency | Test khó cô lập và khó chuẩn bị dữ liệu. | Dùng DTO nhỏ với property expression cần. |
| Quên đăng ký biến | Expression tham chiếu #variable nhưng context chưa có giá trị. | Dùng setVariable() trong test setup. |
| Quên BeanResolver | Expression dùng @beanName nhưng context không biết cách phân giải bean. | Đăng ký resolver hoặc dùng BeanFactory tối thiểu. |
| Nghĩ unit test parser đã kiểm tra @Value | Parser không chạy annotation processing của Spring. | Dùng một context test nhỏ để kiểm tra injection. |
| Chỉ test trường hợp đúng | Lỗi null, biên và dữ liệu sai không được phát hiện. | Thêm test false, null, empty và invalid. |
| Dùng context mutable chung cho nhiều test | Biến và root object có thể rò rỉ giữa test. | Tạo context riêng cho từng test. |
| Chỉ kiểm tra exception chung | Có thể che giấu loại lỗi thực tế. | Kiểm tra parse error và evaluation error riêng. |
| Dùng database hoặc service thật không cần thiết | Test chậm và phụ thuộc môi trường. | Dùng dữ liệu mẫu, fake hoặc bean test nhỏ. |
| Kiểm tra cả ứng dụng trong một test expression | Nhiều lớp lỗi bị trộn lẫn. | Tách unit test expression và integration test Spring. |

## 18. Ghi nhớ

- Phần lớn SpEL expression có thể được unit test bằng SpelExpressionParser và EvaluationContext mà không cần ApplicationContext.
- Dùng root object nhỏ, thường là DTO, để cung cấp property cho expression.
- Dùng setVariable() khi expression tham chiếu biến bằng #name.
- Đăng ký function hoặc BeanResolver tối thiểu khi expression thực sự cần chúng.
- Dùng DefaultListableBeanFactory nhỏ để test bean reference mà không khởi động toàn bộ ứng dụng.
- Kiểm tra parse error, evaluation error, null, collection rỗng, giá trị biên và kiểu kết quả.
- Unit test parser không kiểm tra cơ chế xử lý annotation @Value của Spring.
- Dùng AnnotationConfigApplicationContext nhỏ khi cần kiểm tra @Value hoặc bean lifecycle.
- Tạo EvaluationContext riêng cho từng test, nhất là khi test chạy song song.
- Chỉ dùng ApplicationContext lớn khi mục tiêu thật sự là kiểm tra tích hợp của toàn ứng dụng.