# Biến dùng chung giữa nhiều phần của expression

Trong Spring Expression Language (SpEL), **variable** là một giá trị được cung cấp cho expression thông qua **EvaluationContext**. Expression tham chiếu variable bằng ký hiệu **#** theo sau là tên biến, ví dụ **#order**, **#minimumTotal** hoặc **#currentUser**.

Một variable có thể được dùng ở nhiều vị trí trong cùng một expression: điều kiện, nhánh ternary, đối số method, biểu thức selection hoặc projection. Nếu nhiều expression được đánh giá bằng cùng một EvaluationContext, chúng cũng có thể dùng chung các variable đã đăng ký trong context đó.

Cơ chế này giúp tách dữ liệu đầu vào khỏi chuỗi expression. Thay vì lặp lại một giá trị hoặc nhúng trực tiếp dữ liệu vào chuỗi, ứng dụng đăng ký variable một lần rồi tham chiếu nó ở những phần cần thiết.

## 1. Cú pháp variable

Cú pháp tham chiếu:

~~~text
#variableName
~~~

Ví dụ:

~~~text
#order
#minimumTotal
#currentUser
#featureEnabled
~~~

Ký hiệu **#** phân biệt variable với property của root object và bean reference:

- **#order**: variable tên order trong EvaluationContext.
- **order**: property order trên root object hiện tại.
- **@orderService**: bean tên orderService trong Spring container, được phân giải qua BeanResolver.

Tên variable phân biệt chữ hoa và chữ thường theo tên đã đăng ký. Nếu đăng ký biến minimumTotal thì expression cần tham chiếu đúng tên đó bằng #minimumTotal.

Variable có thể chứa nhiều loại giá trị: String, số, boolean, domain object, collection, Map hoặc một object bất kỳ mà EvaluationContext có thể cung cấp. SpEL không yêu cầu mọi variable phải là kiểu đơn giản.

## 2. Đăng ký variable trong EvaluationContext

Cách thông dụng là dùng StandardEvaluationContext và gọi setVariable():

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("region", "APAC");
context.setVariable("enabled", true);

Boolean accepted = parser
        .parseExpression("#minimumTotal >= 100")
        .getValue(context, Boolean.class);
~~~

Ở đây, ba variable được đăng ký vào context. Expression dùng #minimumTotal để đọc giá trị đã đăng ký. Các variable còn lại có thể được dùng trong những expression khác đánh giá bằng cùng context.

Có thể đăng ký root object riêng với variables:

~~~java
context.setRootObject(order);
context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("taxRate", new BigDecimal("0.08"));
~~~

Khi đó, expression có thể kết hợp property của root object và variables:

~~~text
total >= #minimumTotal and #taxRate > 0
~~~

Trong ví dụ, total được đọc từ root object order, còn minimumTotal và taxRate được lấy từ EvaluationContext.

### 2.1. Đọc và cập nhật variable bằng Java

StandardEvaluationContext hỗ trợ đọc variable bằng lookupVariable() và cập nhật bằng setVariable():

~~~java
context.setVariable("region", "APAC");

Object currentRegion = context.lookupVariable("region");

context.setVariable("region", "EMEA");
~~~

Expression được đánh giá sau khi cập nhật sẽ đọc giá trị hiện tại trong context:

~~~text
#region
~~~

Việc cập nhật variable tác động đến EvaluationContext. Nếu nhiều expression cùng dùng context đó, những lần đánh giá tiếp theo sẽ thấy giá trị mới.

Nên đặt tên variable thể hiện đúng ý nghĩa và kiểu dữ liệu. Điều này giúp người đọc biết expression đang phụ thuộc vào dữ liệu nào mà không phải lần theo các chuỗi literal nằm rải rác trong biểu thức.

## 3. Dùng chung variable giữa nhiều phần của một expression

Một expression có thể chứa nhiều subexpression, chẳng hạn điều kiện logic, toán tử ternary, lời gọi method, selection hoặc projection. Variable đã đăng ký có thể được tham chiếu ở mỗi phần đó.

Ví dụ:

~~~text
#order.total >= #minimumTotal
    and #currentUser.active
    and #region == 'APAC'
~~~

Ba variable có thể được dùng trong cùng điều kiện:

- #minimumTotal cung cấp ngưỡng tổng tiền.
- #currentUser cung cấp người dùng đang thực hiện thao tác.
- #region cung cấp vùng xử lý.

Không cần đăng ký một bản sao variable cho từng phần. Các phần của expression đều đọc cùng giá trị từ EvaluationContext.

### 3.1. Dùng một variable nhiều lần trong ternary

~~~text
#order.total >= #minimumTotal
    ? #order.total * #taxRate
    : #minimumTotal * #taxRate
~~~

Variable taxRate và minimumTotal được dùng ở cả điều kiện lẫn hai nhánh kết quả. Điều này làm cho một giá trị cấu hình có thể được tái sử dụng mà không phải viết lặp giá trị thực tế vào expression.

### 3.2. Dùng variable trong lời gọi method

~~~text
@pricingService.calculate(#order, #customerTier, #currency)
~~~

Các đối số đều lấy từ variables hoặc dữ liệu được context cung cấp. Nếu cùng customerTier còn được dùng ở một điều kiện khác trong expression, vẫn tham chiếu bằng #customerTier.

### 3.3. Dùng variable bên trong selection và projection

Ví dụ lọc các đơn hàng theo một ngưỡng rồi chuyển mỗi đơn thành giá trị đã tính thuế:

~~~text
#orders.?[total >= #minimumTotal]
       .![total * (1 + #taxRate)]
~~~

Trong selection, #minimumTotal là biến dùng chung để lọc từng Order. Trong projection, #taxRate được dùng để tính giá trị cho từng Order còn lại.

Các variable được đọc từ cùng EvaluationContext, ngay cả khi expression đang đánh giá một phần tử collection. Việc thay đổi evaluation object hiện tại không làm mất các variable đã đăng ký.

## 4. Ví dụ đầy đủ: tái sử dụng variable trong nhiều bước

Giả sử ứng dụng cần lọc các đơn hàng đạt ngưỡng, sau đó lấy tổng tiền sau thuế:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orders", orders);
context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("taxRate", new BigDecimal("0.08"));

Expression expression = parser.parseExpression(
        "#orders.?[total >= #minimumTotal].![total * (1 + #taxRate)]"
);

List<?> totals = expression.getValue(context, List.class);
~~~

Quy trình:

1. #orders lấy collection nguồn.
2. Selection .?[total >= #minimumTotal] giữ lại các Order có total đạt ngưỡng.
3. Projection .![total * (1 + #taxRate)] tính tổng tiền sau thuế cho mỗi Order còn lại.
4. Kết quả là một List các giá trị được tính từ những đơn hàng đã chọn.

minimumTotal và taxRate được đăng ký đúng một lần. Chúng được dùng ở những phần khác nhau của cùng expression và vẫn giữ nguyên ý nghĩa trong suốt quá trình đánh giá.

## 5. Dùng chung variable giữa nhiều Expression object

Không chỉ các subexpression trong cùng một chuỗi mới dùng chung variable. Nhiều đối tượng Expression đã parse riêng cũng có thể đọc cùng variable nếu chúng được đánh giá bằng cùng một EvaluationContext.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("currency", "VND");

Expression checkMinimum =
        parser.parseExpression("#amount >= #minimumTotal");

Expression formatLabel =
        parser.parseExpression(
            "#currency + ' ' + #amount"
        );

context.setVariable("amount", new BigDecimal("250.00"));

Boolean accepted = checkMinimum.getValue(context, Boolean.class);
String label = formatLabel.getValue(context, String.class);
~~~

Hai Expression được parse độc lập, nhưng cùng dùng context nên đều có thể đọc minimumTotal, currency và amount.

Nếu tạo một EvaluationContext mới, các variable đã đăng ký trong context cũ không tự động xuất hiện trong context mới. Cần đăng ký lại các giá trị cần dùng hoặc tạo context mới từ một hàm khởi tạo chung.

### 5.1. Cập nhật giá trị giữa hai lần evaluate

Có thể thay đổi variable rồi đánh giá lại cùng Expression:

~~~java
Expression checkMinimum =
        parser.parseExpression("#amount >= #minimumTotal");

context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("amount", new BigDecimal("120.00"));

Boolean first = checkMinimum.getValue(context, Boolean.class);

context.setVariable("minimumTotal", new BigDecimal("150.00"));

Boolean second = checkMinimum.getValue(context, Boolean.class);
~~~

Lần đánh giá đầu đọc ngưỡng 100.00; lần tiếp theo đọc ngưỡng 150.00. Expression đã parse không cần tạo lại chỉ vì giá trị variable thay đổi.

Điều này hữu ích khi một expression template được tái sử dụng với nhiều bộ dữ liệu đầu vào. Tuy nhiên, phải bảo đảm context chứa đúng dữ liệu cho từng lần evaluate.

## 6. Phân biệt variable với #root và #this

SpEL có hai biến đặc biệt thường xuất hiện trong expression:

- **#root** đại diện cho root object của EvaluationContext.
- **#this** đại diện cho evaluation object hiện tại và có thể thay đổi khi SpEL đi vào một phần expression khác, chẳng hạn selection hoặc projection.

Các variable do ứng dụng đăng ký như #minimumTotal hoặc #currentUser là những giá trị riêng trong context. Chúng không thay thế root object và cũng không thay đổi theo phần tử hiện tại.

Ví dụ root object là một ReportRequest chứa collection orders và tên báo cáo:

~~~java
context.setRootObject(reportRequest);
context.setVariable("minimumTotal", new BigDecimal("100.00"));
~~~

Expression:

~~~text
#orders.?[
    total >= #minimumTotal
    and #this.customer.active
]
~~~

Trong selection:

- #this là Order đang được kiểm tra.
- #minimumTotal là variable được đăng ký trong context và giữ nguyên giá trị trong từng lần kiểm tra.
- #root vẫn là ReportRequest gốc nếu cần tham chiếu dữ liệu ở cấp báo cáo.

Có thể dùng root và variable trong cùng một expression:

~~~text
#root.reportName + ': ' + #minimumTotal
~~~

Khi đi vào selection hoặc projection, #this có thể thay đổi, nhưng #root và các variable đã đăng ký vẫn tham chiếu đến context tương ứng.

## 7. Variable trong các integration point của Spring

Một số module Spring tự tạo EvaluationContext và cung cấp variables theo ngữ cảnh của annotation hoặc thao tác đang thực hiện. Những variable này có thể dùng chung giữa nhiều phần của expression trong chính integration point đó.

Tập variable có sẵn phụ thuộc module. Không nên giả định một tên biến xuất hiện trong Spring Cache cũng có mặt trong Spring Security hoặc trong @Value.

### 7.1. Spring Cache

Trong các annotation cache dựa trên method, SpEL có thể truy cập tham số method theo tên nếu Spring phát hiện được tên tham số. Có thể dùng các alias theo vị trí như #p0 hoặc #a0 khi cần.

Ví dụ:

~~~java
@Cacheable(
    cacheNames = "customer",
    key = "#tenantId + ':' + #customerId",
    condition = "#customerId != null and #tenantId != null"
)
public Customer find(String tenantId, String customerId) {
    // ...
}
~~~

tenantId và customerId được dùng trong cả key lẫn condition. Cả hai phần expression đều lấy dữ liệu từ context do Spring Cache tạo cho lần gọi method.

Nếu tên tham số không được phát hiện, hãy dùng alias theo vị trí hoặc cấu hình biên dịch/metadata phù hợp. Không nên giả định tên tham số Java luôn có sẵn trong mọi cấu hình build.

### 7.2. Spring Method Security

Method Security cũng cung cấp các tham số method vào EvaluationContext. Ví dụ:

~~~java
@PreAuthorize(
    "#request.tenantId == authentication.principal.tenantId"
    + " and #request.ownerId == authentication.principal.id"
)
public Document read(DocumentRequest request) {
    // ...
}
~~~

Trong expression, request được dùng ở hai điều kiện. Nó là dữ liệu tham số method do context của Spring Security cung cấp.

Khả năng tham chiếu tham số bằng tên phụ thuộc cách Spring lấy được tên tham số, ví dụ metadata biên dịch hoặc annotation tham số được hỗ trợ. Nếu không có tên, có thể dùng các alias theo vị trí mà module cung cấp.

### 7.3. Tự tạo EvaluationContext

Nếu ứng dụng tự parse và evaluate expression, ứng dụng chịu trách nhiệm đăng ký các variable cần thiết:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("currentUser", currentUser);
context.setVariable("tenantId", tenantId);
context.setVariable("permissions", permissions);
~~~

Expression:

~~~text
#currentUser.active
    and #tenantId == #currentUser.tenantId
    and #permissions.contains('document:read')
~~~

Không có một danh sách variable tự động dùng chung cho mọi ứng dụng. Context là nơi xác định chính xác dữ liệu nào được cung cấp cho expression.

## 8. Variable có giữ nguyên giá trị hay được sao chép?

EvaluationContext lưu giá trị được đăng ký cho variable. Khi giá trị là một object, context giữ reference đến object đó; SpEL không tự deep-copy object khi setVariable().

Ví dụ:

~~~java
Customer customer = new Customer("CUS-001");

context.setVariable("customer", customer);

customer.setName("CUS-002");
~~~

Một expression được đánh giá sau khi thay đổi object có thể đọc trạng thái mới thông qua #customer:

~~~text
#customer.name
~~~

Tương tự, nếu variable chứa List hoặc Map, thay đổi nội dung collection cũng có thể ảnh hưởng kết quả của những lần evaluate tiếp theo.

Điều này hữu ích khi expression cần đọc trạng thái mới nhất của một object, nhưng cần chú ý nếu context được tái sử dụng. Nếu muốn expression dùng snapshot dữ liệu, hãy truyền một object bất biến hoặc bản sao được tạo rõ ràng ở phía Java.

## 9. Vòng đời và phạm vi chia sẻ của variable

Variable thuộc về EvaluationContext mà nó được đăng ký. Nó không tự trở thành biến global, static hay dữ liệu dùng chung cho mọi expression trong toàn ứng dụng.

Có thể phân biệt các trường hợp:

| Trường hợp | Variable có sẵn không? |
| --- | --- |
| Nhiều subexpression trong cùng lần evaluate | Có, nếu cùng dùng EvaluationContext |
| Nhiều Expression object được evaluate bằng cùng context | Có |
| Expression được evaluate bằng một context mới | Không tự có; phải đăng ký lại |
| Expression chạy trong integration point Spring khác | Phụ thuộc context mà integration point cung cấp |
| Một context được tái sử dụng sau khi setVariable() | Giá trị hiện tại được dùng cho lần evaluate tiếp theo |

Nếu ứng dụng tái sử dụng một StandardEvaluationContext, hãy quản lý rõ thời điểm cập nhật và xóa dữ liệu đầu vào. Không nên dùng chung một context mutable cho nhiều request đồng thời khi mỗi request cần các variable khác nhau; điều đó có thể khiến một lần evaluate đọc nhầm dữ liệu của lần khác.

Một cách đơn giản là tạo context riêng cho mỗi lần xử lý hoặc mỗi đơn vị công việc:

~~~java
StandardEvaluationContext createContext(
        Order order,
        BigDecimal minimumTotal,
        User currentUser) {

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", minimumTotal);
    context.setVariable("currentUser", currentUser);

    return context;
}
~~~

Các Expression đã parse có thể được tái sử dụng, trong khi mỗi lần xử lý nhận một EvaluationContext riêng với các variable phù hợp.

## 10. Variable và function trong SpEL

Variable thường chứa dữ liệu: object, số, chuỗi, collection hoặc boolean. SpEL cũng có khả năng đăng ký một method Java làm function trong EvaluationContext. Function được gọi bằng cú pháp có dấu # và dấu ngoặc:

~~~text
#normalizeCode(#rawCode)
~~~

Function không giống một variable dữ liệu thông thường, dù tên function cũng được đăng ký trong context. Khi cần một phép biến đổi có thể tái sử dụng, function có thể phù hợp hơn việc lưu một giá trị.

Ví dụ, với StandardEvaluationContext có thể đăng ký Method:

~~~java
Method normalizeMethod =
        CodeFunctions.class.getDeclaredMethod("normalize", String.class);

context.registerFunction("normalizeCode", normalizeMethod);
~~~

Class CodeFunctions có thể định nghĩa method tĩnh:

~~~java
public class CodeFunctions {

    public static String normalize(String code) {
        return code == null ? null : code.trim().toUpperCase();
    }
}
~~~

Sau đó expression có thể gọi:

~~~text
#normalizeCode(#rawCode)
~~~

Method được đăng ký phải có chữ ký phù hợp với cách gọi và có thể được reflection truy cập. Hãy kiểm tra API theo phiên bản Spring đang dùng nếu ứng dụng dựa vào function registration.

Nếu logic có nhiều dependency hoặc cần truy cập service Spring, một bean method được gọi qua @beanName thường thể hiện ý định rõ hơn function tĩnh.

## 11. Kiểm thử variable được dùng chung

Có thể viết unit test để xác nhận nhiều phần của expression đọc cùng một variable:

~~~java
class SharedExpressionVariableTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void reusesVariablesInSelectionAndProjection() {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setVariable("orders", List.of(
                new Order("A-1", new BigDecimal("120.00")),
                new Order("A-2", new BigDecimal("80.00")),
                new Order("A-3", new BigDecimal("200.00"))
        ));
        context.setVariable("minimumTotal", new BigDecimal("100.00"));
        context.setVariable("taxRate", new BigDecimal("0.10"));

        List<?> totals = parser
                .parseExpression(
                    "#orders.?[total >= #minimumTotal]"
                    + ".![total * (1 + #taxRate)]"
                )
                .getValue(context, List.class);

        assertEquals(
                List.of(
                    new BigDecimal("132.0000"),
                    new BigDecimal("220.0000")
                ),
                totals
        );
    }

    @Test
    void separateExpressionsCanShareOneContext() {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setVariable("limit", 10);
        context.setVariable("value", 15);

        Expression condition =
                parser.parseExpression("#value >= #limit");

        Expression message =
                parser.parseExpression(
                    "'value=' + #value + ', limit=' + #limit"
                );

        assertEquals(Boolean.TRUE,
                condition.getValue(context, Boolean.class));

        assertEquals("value=15, limit=10",
                message.getValue(context, String.class));
    }
}
~~~

Test đầu dùng minimumTotal trong selection và taxRate trong projection. Test thứ hai parse hai Expression riêng nhưng truyền cùng EvaluationContext khi evaluate.

Khi kiểm thử, nên xác nhận cả trường hợp cập nhật variable giữa hai lần evaluate và trường hợp tạo context mới. Điều đó giúp phát hiện lỗi do dữ liệu cũ còn nằm trong context hoặc do quên đăng ký variable cho lần xử lý mới.

## 12. Những lỗi thường gặp khi dùng variable

1. **Quên ký hiệu #:** viết minimumTotal thay vì #minimumTotal khi muốn đọc variable.
2. **Chưa đăng ký variable:** expression tham chiếu #currentUser nhưng context không được cung cấp giá trị đó.
3. **Đăng ký sai tên:** tên trong setVariable() không khớp tên được tham chiếu trong expression.
4. **Nhầm variable với bean:** #pricingService là variable; @pricingService là bean reference cần BeanResolver.
5. **Nhầm variable với root property:** order là property của root object; #order là variable.
6. **Cho rằng context mới kế thừa variable cũ:** mỗi EvaluationContext có dữ liệu riêng, trừ khi ứng dụng đăng ký lại.
7. **Tái sử dụng context với dữ liệu request khác nhau:** variable cũ có thể còn tồn tại hoặc bị cập nhật không đúng thời điểm.
8. **Giả định variable là bản sao:** nếu variable chứa object mutable, thay đổi object có thể được thấy trong lần evaluate sau.
9. **Giả định mọi annotation có cùng variable:** mỗi integration point Spring định nghĩa EvaluationContext và tập variable riêng.
10. **Đưa dữ liệu không tin cậy vào expression context quá rộng:** chỉ cung cấp những object và quyền truy cập cần thiết.

## 13. Ghi nhớ nhanh

- Variable trong SpEL được tham chiếu bằng cú pháp **#variableName**.
- Đăng ký variable bằng **EvaluationContext.setVariable(name, value)**.
- Có thể đọc giá trị từ Java bằng **lookupVariable(name)** trên StandardEvaluationContext.
- Nhiều phần của cùng expression có thể dùng chung variable từ EvaluationContext.
- Nhiều Expression object cũng có thể dùng chung variable nếu được evaluate bằng cùng context.
- Variable có thể được dùng trong điều kiện, ternary, method argument, selection và projection.
- Trong collection operation, **#this** có thể thay đổi theo phần tử; variable như #minimumTotal vẫn là giá trị được cung cấp trong context.
- **#root** là root object; **#this** là evaluation object hiện tại; variable do ứng dụng đăng ký là dữ liệu riêng.
- Context mới không tự kế thừa variable của context cũ.
- Object hoặc collection được đăng ký thường được giữ dưới dạng reference, không phải deep copy.
- Tạo context riêng cho đơn vị xử lý khi các lần evaluate cần bộ variable khác nhau.
- Spring Cache, Method Security và các integration point khác có thể cung cấp variable riêng; cần xem đúng context của module.

## 14. Tài liệu tham khảo chính thức

- [Spring Framework — Variables in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework — Collection Selection and Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework — Cache Annotation SpEL Context](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Security — Method Security Expressions](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
