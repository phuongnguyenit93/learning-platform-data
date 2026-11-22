# Điều kiện để expression có thể biên dịch trong SpEL

## 1. Biên dịch SpEL là gì?

Spring Expression Language (SpEL) thường đánh giá expression bằng interpreter. Interpreter thực hiện từng thao tác trên object và dữ liệu tại runtime. Cách này linh hoạt vì SpEL không yêu cầu khai báo kiểu tĩnh cho mọi phần của biểu thức, nhưng có thể tốn chi phí khi cùng một expression được đánh giá rất nhiều lần.

SpEL compiler có thể tạo một Java class chứa hành vi của expression và dùng class đó ở những lần đánh giá sau. Mục tiêu là giảm chi phí lặp lại trong các luồng có expression được dùng thường xuyên.

Compiler không thể biên dịch mọi expression. Để sinh bytecode, nó cần biết đủ thông tin về các node trong expression, đặc biệt là kiểu của property, kết quả method và toán hạng. Vì SpEL có tính động, một phần thông tin kiểu thường chỉ được biết sau khi expression đã chạy bằng interpreter.

Expression phù hợp để biên dịch thường có các đặc điểm:

- Được đánh giá lặp lại đủ nhiều để chi phí biên dịch có ý nghĩa.
- Cấu trúc object và kiểu dữ liệu ổn định giữa các lần đánh giá.
- Các property và method được truy cập có kiểu rõ ràng.
- Không phụ thuộc vào cú pháp hoặc resolver mà compiler chưa hỗ trợ.
- Không thay đổi kiểu dữ liệu đầu vào theo cách làm bytecode đã sinh ra không còn phù hợp.

Biên dịch là một tối ưu hóa hiệu năng. Expression vẫn cần đúng khi chạy ở chế độ interpreted; không nên dựa vào compiler để sửa lỗi dữ liệu hoặc thay đổi semantics.

## 2. Compiler lấy thông tin kiểu từ đâu?

SpEL không có hệ thống kiểu tĩnh đầy đủ như Java. Với expression:

~~~text
payload.customer.name
~~~

Parser biết tên các property nhưng không nhất thiết biết kiểu runtime của payload, customer và name chỉ từ chuỗi expression.

Khi interpreter đánh giá expression với một root object thật, nó quan sát được kiểu của các giá trị trung gian và kết quả truy cập. Compiler có thể dùng thông tin đã thu thập này để tạo bytecode tương ứng.

Ví dụ:

~~~java
public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}

public class Payload {
    private final Customer customer;

    public Payload(Customer customer) {
        this.customer = customer;
    }

    public Customer getCustomer() {
        return customer;
    }
}

public class Message {
    private final Payload payload;

    public Message(Payload payload) {
        this.payload = payload;
    }

    public Payload getPayload() {
        return payload;
    }
}
~~~

Đánh giá expression:

~~~java
Expression expression = parser.parseExpression("payload.customer.name");

Message message = new Message(
        new Payload(new Customer("Lan")));

String name = expression.getValue(message, String.class);
~~~

Sau lần interpreted evaluation, SpEL có thêm thông tin runtime về các property trong đường dẫn. Nếu những kiểu này tiếp tục ổn định, expression có thể phù hợp để compiler sinh bytecode.

Nếu một lần đánh giá dùng Customer nhưng lần khác property customer trả về một kiểu object khác, thông tin đã dùng để biên dịch có thể không còn đúng. Đây là lý do type stability là điều kiện quan trọng.

## 3. Những dạng expression thường phù hợp

Compiler hướng tới những biểu thức phổ biến trong đường chạy hiệu năng cao. Các trường hợp thường phù hợp khi kiểu dữ liệu ổn định gồm:

- Đọc property từ root object hoặc object lồng nhau.
- Truy cập phần tử array bằng index trong các dạng được hỗ trợ.
- Thực hiện phép toán số học và so sánh trên kiểu đã xác định.
- Đánh giá điều kiện logic hoặc biểu thức điều kiện đơn giản.
- Gọi method có thể phân giải rõ ràng với kiểu target và kiểu đối số ổn định.
- Dùng giá trị và kiểu mà compiler có thể xác định từ những lần interpreted evaluation.

Ví dụ một expression có property access, index access và phép toán:

~~~java
Expression expression = parser.parseExpression(
        "measurements[0].value * 1.8 + 32");

Double fahrenheit = expression.getValue(
        sensorReading,
        Double.class);
~~~

Nếu measurements luôn là array hoặc collection có kiểu phần tử ổn định, phần tử đầu tiên luôn có property value với kiểu tương thích và phép toán luôn nhận kiểu đã biết, expression có thể là ứng viên cho compilation.

Không có quy tắc đơn giản kiểu “expression càng ngắn càng dễ biên dịch”. Điều quyết định là compiler có thể sinh bytecode từ các node và thông tin kiểu đã thu thập hay không.

## 4. Những expression không được compiler hỗ trợ

SpEL compiler hiện không hỗ trợ biên dịch các dạng sau:

- Expression có phép gán.
- Expression phụ thuộc vào ConversionService.
- Expression sử dụng custom resolver.
- Expression dùng overloaded operator.
- Expression dùng Optional cùng null-safe operator hoặc Elvis operator.
- Expression dùng cú pháp tạo array.
- Expression dùng selection hoặc projection.
- Expression dùng bean reference.

Ví dụ các dạng cần tiếp tục được đánh giá bằng interpreter:

~~~text
quantity = 10
items.?[active]
items.![name]
@pricingService.calculate(amount)
~~~

Nếu expression chứa thao tác không được hỗ trợ, compiler không thể tạo compiled form cho expression đó. Bật compiler mode không có nghĩa mọi expression tự động được tối ưu.

Expression dựa vào ConversionService hoặc custom resolver cần giữ đúng cơ chế chuyển đổi/phân giải của interpreter. Hãy kiểm tra danh sách giới hạn của phiên bản Spring Framework mà ứng dụng đang sử dụng vì phạm vi hỗ trợ có thể thay đổi theo phiên bản.

## 5. Kiểu dữ liệu phải ổn định giữa các lần đánh giá

Compiler sử dụng kiểu được quan sát từ những lần interpreted evaluation. Nếu dữ liệu đầu vào thay đổi kiểu, compiled expression có thể không còn tương thích.

Ví dụ, cùng một property có thể trả về các kiểu khác nhau:

~~~java
public class DynamicMessage {
    private Object payload;

    public Object getPayload() {
        return payload;
    }

    public void setPayload(Object payload) {
        this.payload = payload;
    }
}
~~~

Expression:

~~~text
payload.toString()
~~~

Lần đầu payload có thể là String, lần sau có thể là một object khác. Với expression phụ thuộc vào kiểu runtime, compiler có thể sinh bytecode dựa trên kiểu của lần đánh giá trước và thất bại khi kiểu thay đổi.

Các trường hợp cần chú ý:

- Property khai báo kiểu Object nhưng runtime trả về nhiều kiểu không liên quan.
- Method trả về kiểu khác nhau theo nhánh hoặc trạng thái dữ liệu.
- Collection có phần tử thuộc nhiều kiểu khác nhau.
- Root object thay đổi cấu trúc hoặc kiểu giữa các lần đánh giá.
- Giá trị có thể null ở một số lần nhưng là object có kiểu cụ thể ở lần khác.
- Proxy hoặc implementation runtime thay đổi theo môi trường.

Nếu kiểu dữ liệu không ổn định, giữ compiler ở OFF hoặc cân nhắc MIXED sau khi kiểm thử hành vi và side effect. Không nên dùng IMMEDIATE chỉ dựa trên một mẫu dữ liệu đại diện.

## 6. Null và đường dẫn property

Null cần được xem xét riêng khi đánh giá khả năng biên dịch. Một lần interpreted evaluation có thể quan sát một kiểu object cụ thể, nhưng lần sau property trung gian có thể null hoặc trả về dữ liệu khác.

Ví dụ:

~~~text
customer.address.city
~~~

Nếu customer hoặc address có thể null, expression thông thường có thể phát sinh lỗi evaluation. Null-safe navigation:

~~~text
customer?.address?.city
~~~

có thể giúp expression xử lý các điểm null theo ý định nghiệp vụ. Tuy nhiên, việc dùng null-safe operator không tự bảo đảm expression được compiler hỗ trợ. Compiler có danh sách giới hạn riêng; cần kiểm tra cú pháp cụ thể và phiên bản framework.

Nên kiểm thử ít nhất các trường hợp:

- Root object có đầy đủ property.
- Property trung gian là null.
- Property cuối cùng là null.
- Cùng expression được đánh giá với các root object có kiểu thực tế khác nhau.

Nếu dữ liệu có nhiều trạng thái null và kiểu thay đổi thường xuyên, interpreter có thể là lựa chọn dễ dự đoán hơn. Không bật compilation chỉ để né xử lý null trong model.

## 7. Cấu hình SpelCompilerMode

Compiler có ba chế độ trong enum SpelCompilerMode:

| Chế độ | Hành vi |
|---|---|
| OFF | Tắt compiler; mọi expression được đánh giá bằng interpreter. Đây là mặc định. |
| IMMEDIATE | Biên dịch expression sớm nhất có thể, thường sau lần interpreted evaluation đầu tiên. Lỗi khi chạy compiled form được trả về caller. |
| MIXED | Sau một số lần interpreted evaluation thành công, expression được biên dịch. Nếu compiled form thất bại, SpEL chuyển lại interpreter và có thể thử biên dịch lại sau đó. |

OFF phù hợp khi expression ít được đánh giá, kiểu dữ liệu thay đổi hoặc compiler không mang lại lợi ích đáng kể.

IMMEDIATE phù hợp hơn với expression có kiểu ổn định, đã được kiểm chứng và không có side effect khó lặp lại. Nếu compiled form thất bại, exception được đưa ra cho caller.

MIXED cho phép chuyển đổi giữa interpreted và compiled trong quá trình chạy. Nó có thể phù hợp khi muốn tối ưu dần nhưng vẫn cần khả năng quay lại interpreter nếu compiled form gặp vấn đề. Tuy nhiên, fallback có thể đánh giá lại expression sau một phần thực thi; cần thận trọng với side effect.

## 8. Cấu hình compiler bằng SpelParserConfiguration

Có thể cấu hình mode và class loader khi tạo parser:

~~~java
import org.springframework.expression.spel.SpelCompilerMode;
import org.springframework.expression.spel.SpelParserConfiguration;
import org.springframework.expression.spel.standard.SpelExpressionParser;

SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                MyApplication.class.getClassLoader());

SpelExpressionParser parser =
        new SpelExpressionParser(configuration);

Expression expression =
        parser.parseExpression("payload.customer.name");
~~~

Cấu hình này áp dụng cho các expression được tạo bởi parser tương ứng. Parser không tự làm thay đổi mọi parser khác trong ứng dụng.

Có thể dùng OFF, IMMEDIATE hoặc MIXED tùy yêu cầu. Nếu không chỉ định mode, compiler mặc định tắt.

Trong các phiên bản Spring Framework mới có builder API cho SpelParserConfiguration. Hãy dùng API phù hợp với phiên bản dependency thực tế; constructor ở trên là cách cấu hình phổ biến qua nhiều phiên bản.

## 9. Chọn ClassLoader cho compiled expression

Compiled expression được định nghĩa trong một child ClassLoader. Child loader được tạo dựa trên class loader mà ứng dụng cung cấp; nó cần nhìn thấy tất cả kiểu tham gia vào quá trình đánh giá expression.

Có thể truyền class loader của ứng dụng:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.IMMEDIATE,
                MyApplication.class.getClassLoader());
~~~

Nếu không truyền class loader, SpEL dùng class loader mặc định, thường là context ClassLoader của thread đang đánh giá expression.

Class loader đặc biệt quan trọng khi ứng dụng chạy trong:

- Application server có nhiều class loader.
- Plugin system hoặc module có class loader riêng.
- Môi trường chạy có proxy hoặc class được sinh động.
- Ứng dụng có domain type nằm trong module không nhìn thấy từ thread context class loader.

Nếu compiled expression không nhìn thấy class của root object hoặc property, compilation hoặc class loading có thể thất bại. Hãy chọn class loader có thể truy cập tất cả kiểu liên quan và kiểm thử trong môi trường chạy thật.

## 10. Bật compiler bằng system property

Khi SpEL được sử dụng bên trong module khác và không dễ cấu hình parser trực tiếp, có thể đặt property:

~~~text
spring.expression.compiler.mode=off
spring.expression.compiler.mode=immediate
spring.expression.compiler.mode=mixed
~~~

Ví dụ cấu hình JVM:

~~~text
-Dspring.expression.compiler.mode=mixed
~~~

Spring cũng hỗ trợ cơ chế SpringProperties cho property này. Giá trị hợp lệ tương ứng với các mode OFF, IMMEDIATE và MIXED.

Đây là cấu hình ảnh hưởng tới cách các parser tích hợp lấy compiler mode mặc định. Hãy cân nhắc phạm vi tác động trước khi bật ở cấp JVM hoặc SpringProperties, đặc biệt khi ứng dụng có nhiều module dùng SpEL với các loại EvaluationContext khác nhau.

Nếu chỉ một luồng expression cần compilation, cấu hình parser cụ thể thường dễ giới hạn và kiểm soát hơn việc bật toàn cục.

## 11. Chủ động yêu cầu compilation cho một expression

Với SpelExpression, có thể yêu cầu biên dịch expression sau khi đã đánh giá interpreted và có đủ thông tin kiểu:

~~~java
SpelExpressionParser parser = new SpelExpressionParser();

SpelExpression expression = (SpelExpression) parser.parseExpression(
        "payload.customer.name");

Message message = TestData.message("Lan");

// Thu thập thông tin kiểu qua interpreted evaluation.
String firstResult = expression.getValue(message, String.class);

// Yêu cầu compiler tạo compiled form.
boolean compiled = expression.compileExpression();

if (compiled) {
    String nextResult = expression.getValue(message, String.class);
}
~~~

compileExpression trả về true nếu expression đã có hoặc vừa tạo được compiled form. Nó có thể trả về false nếu compiler chưa có đủ thông tin hoặc expression chứa node không được hỗ trợ.

Có thể đưa expression trở lại interpreted mode:

~~~java
expression.revertToInterpreted();
~~~

API này hữu ích cho kiểm thử hoặc khi ứng dụng quản lý compilation chủ động. Trong phần lớn trường hợp, cấu hình compiler mode ở parser là đủ; không cần tự quản lý compile/revert nếu không có lý do rõ ràng.

## 12. IMMEDIATE và MIXED có hành vi lỗi khác nhau

Hai mode này khác nhau ở cách xử lý lỗi của compiled expression.

Trong IMMEDIATE:

- Expression được compile sớm.
- Nếu compiled form thất bại khi evaluate, exception được trả về caller.
- Caller nhìn thấy lỗi và có thể xử lý theo chính sách ứng dụng.

Trong MIXED:

- Expression được đánh giá interpreted một số lần trước khi compile.
- Nếu compiled form thất bại, lỗi được xử lý nội bộ và expression quay lại interpreted mode.
- Sau đó compiler có thể thử lại; nếu tiếp tục thất bại đủ nhiều, expression có thể được giữ ở interpreted mode.

MIXED có thể che giấu việc compiled form không còn phù hợp với kiểu dữ liệu. Vì vậy, cần quan sát hiệu năng và lỗi runtime thay vì chỉ bật mode rồi giả định mọi expression đều đã compile thành công.

## 13. Vì sao MIXED cần thận trọng với side effect?

MIXED có thể quay lại interpreter sau khi compiled expression gặp lỗi. Nếu expression đã thực hiện một phần thao tác có side effect trước khi lỗi, lần đánh giá interpreted tiếp theo có thể thực hiện lại một phần logic.

Ví dụ, expression gọi method thay đổi trạng thái:

~~~text
counter.incrementAndGet()
~~~

Nếu compiled form thực hiện được một phần thao tác rồi thất bại, fallback có thể khiến method được gọi thêm lần nữa. Điều đó có thể làm số đếm hoặc trạng thái thay đổi nhiều hơn dự kiến.

Với expression có side effect:

- Ưu tiên expression thuần, chỉ đọc dữ liệu và tính kết quả.
- Tránh gọi method ghi dữ liệu, gửi message hoặc thực hiện giao dịch từ expression.
- Nếu không thể loại bỏ side effect, hiểu rõ rủi ro fallback của MIXED.
- Cân nhắc OFF hoặc IMMEDIATE tùy contract và cách xử lý lỗi.

IMMEDIATE tồn tại một phần vì caller có thể muốn nhận exception rõ ràng thay vì để MIXED âm thầm chạy lại expression bằng interpreter.

## 14. Cách xác định expression có thể compile hay không

Không nên suy luận khả năng compile chỉ từ cú pháp nhìn thấy. Có thể dùng API compileExpression sau một lần evaluate để kiểm tra kết quả thực tế:

~~~java
SpelExpression expression = (SpelExpression) parser.parseExpression(
        "payload.customer.name");

Message message = TestData.message("Lan");
expression.getValue(message);

boolean compilable = expression.compileExpression();
~~~

Nếu compilable là false, giữ expression ở interpreted mode. Không nên thay đổi logic chỉ để ép compiler nhận một expression vốn phụ thuộc custom resolver hoặc conversion service.

Trong test, ghi nhận:

- Expression source.
- Parser configuration và compiler mode.
- Root object cùng kiểu runtime.
- Kết quả của interpreted evaluation.
- Kết quả compileExpression.
- Kết quả evaluate sau khi compile.
- Hành vi khi dữ liệu đổi kiểu hoặc có null.

Việc kiểm tra này là kiểm thử kỹ thuật của compiler, không phải cam kết rằng expression sẽ luôn compile trong mọi runtime environment.

## 15. Đo hiệu năng trước và sau khi compile

Compiler hướng tới các expression được đánh giá thường xuyên. Với expression chỉ chạy một lần, chi phí parse, khởi tạo context và compilation có thể lớn hơn phần thời gian tiết kiệm được.

Quy trình đo nên gồm:

1. Xác định expression nằm trong đường chạy nóng bằng profiling.
2. Dùng dữ liệu đại diện và kiểu ổn định.
3. Đo interpreter sau khi JVM đã warm up.
4. Đo compiled mode với cùng dữ liệu và cùng workload.
5. So sánh throughput, latency và chi phí bộ nhớ/class loading.
6. Kiểm tra hành vi khi dữ liệu có null hoặc kiểu khác với dữ liệu warm-up.

Không dùng một microbenchmark đơn lẻ làm bằng chứng rằng compiler cải thiện toàn bộ ứng dụng. Hãy đo trên workload thực tế và tính cả chi phí khởi động, compilation và class loading.

## 16. Kiểm thử các điều kiện biên

Một expression có thể compile với dữ liệu warm-up nhưng thất bại khi dữ liệu thực tế thay đổi. Test nên bao phủ các kiểu và trạng thái có thể xuất hiện:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Root object chuẩn | Kết quả interpreted và compiled tương đương |
| Property trung gian null | Hành vi null/error theo expression |
| Collection rỗng | Kết quả và lỗi index theo contract |
| Runtime type thay đổi | Compiled mode có thể thất bại; MIXED fallback đúng chính sách |
| Custom resolver hoặc ConversionService | Xác nhận expression cần interpreter nếu compiler không hỗ trợ |
| Bean reference | Không giả định compiled form được tạo |
| Selection/projection | Giữ interpreter vì compiler không hỗ trợ các node này |
| Expression có side effect | Tránh fallback có thể lặp lại thao tác |

Nên kiểm thử cả dữ liệu warm-up và dữ liệu xuất hiện sau khi expression đã được compile. Chỉ kiểm tra lần đầu không phát hiện được lỗi do type assumption.

## 17. Giới hạn compiler và lựa chọn chế độ

| Tình huống | Hướng xử lý |
|---|---|
| Expression đơn giản, chạy ít lần | OFF |
| Expression đọc property và tính toán lặp lại, kiểu ổn định | Thử MIXED hoặc IMMEDIATE sau benchmark |
| Expression có kiểu runtime thay đổi | OFF hoặc MIXED sau khi kiểm thử |
| Expression dùng selection/projection | Interpreter |
| Expression phụ thuộc custom resolver hoặc ConversionService | Interpreter |
| Expression có bean reference | Interpreter |
| Expression có side effect | Ưu tiên OFF hoặc lựa chọn mode sau khi phân tích khả năng chạy lặp |
| Expression không đủ thông tin kiểu để compile | Giữ interpreted mode |

Không cần bật compiler cho toàn bộ ứng dụng để tối ưu một expression. Hãy giới hạn compilation vào những parser và luồng thực sự cần hiệu năng đó.

## 18. Lưu ý bảo mật với SimpleEvaluationContext

SimpleEvaluationContext được thiết kế để giới hạn các khả năng của SpEL, thường dùng cho data binding hoặc property access có kiểm soát. Không nên giả định rằng bật compiler cho một context giới hạn luôn giữ nguyên mọi safety guard của interpreter.

Spring đã công bố CVE-2026-59283 vào ngày 20-08-2026 về khả năng bypass safety guard khi SpEL compiler hoạt động với SimpleEvaluationContext. Advisory mô tả trường hợp ứng dụng dùng SimpleEvaluationContext đồng thời bật compiler mode IMMEDIATE hoặc MIXED, qua parser configuration hoặc property toàn cục. Compiled expression có thể bỏ qua safety guard được áp dụng trong interpreted evaluation; advisory cũng nêu nguy cơ tăng trưởng class loading không giới hạn khi nhiều expression khác nhau được compile.

Các phiên bản bị ảnh hưởng được advisory liệt kê gồm:

- Spring Framework 7.0.0 đến 7.0.8.
- Spring Framework 6.2.0 đến 6.2.19.
- Spring Framework 6.1.0 đến 6.1.28.
- Spring Framework 6.0.0 đến 6.0.30.
- Spring Framework 5.3.0 đến 5.3.49.
- Spring Framework 5.2.25.RELEASE và các phiên bản cũ hơn.

Các phiên bản sửa lỗi được advisory nêu gồm 7.0.9, 6.2.20, 6.1.29, 6.0.31, 5.3.50 và 5.2.26; một số nhánh chỉ có bản Enterprise Support. Hãy kiểm tra advisory chính thức để xác nhận nhánh hỗ trợ và bản vá phù hợp với ứng dụng.

Ở các phiên bản đã sửa, SimpleEvaluationContext không hỗ trợ expression compilation theo mặc định, bất kể compiler mode được cấu hình ở đâu. Ứng dụng chỉ nên chủ động gọi withCompilationSupported() trên builder nếu expression đáng tin cậy và đã đánh giá rõ việc loại bỏ safety guard trong compiled evaluation.

Không bật compilation cho SimpleEvaluationContext khi đánh giá expression không tin cậy. Cập nhật lên phiên bản đã vá là bước xử lý chính nếu ứng dụng dùng cấu hình bị ảnh hưởng.

## 19. Lỗi thường gặp

**Cho rằng mọi expression đều có thể compile**

Compiler chỉ hỗ trợ một tập con của SpEL. Expression dùng assignment, selection, projection, bean reference, custom resolver hoặc conversion service không thuộc nhóm được hỗ trợ hiện tại.

**Compile trước khi có thông tin kiểu**

Compiler có thể chưa biết đủ kiểu runtime để sinh bytecode. Hãy đánh giá interpreted trước và kiểm tra kết quả compileExpression.

**Dùng một mẫu dữ liệu để kết luận kiểu luôn ổn định**

Dữ liệu production có thể có null, subclass, proxy hoặc kiểu khác. Kiểm thử các biến thể thực tế trước khi bật compiler.

**Bật IMMEDIATE cho expression có side effect**

Compiled failure sẽ được trả về caller; nhưng side effect đã xảy ra trước lỗi vẫn có thể tồn tại. Hãy thiết kế expression thuần và có thể dự đoán.

**Bật MIXED mà không hiểu fallback**

MIXED có thể quay lại interpreter sau lỗi compiled form và có thể thử compile lại. Nếu expression có side effect, việc đánh giá lại cần được xem xét cẩn thận.

**Chỉ bật system property mà không kiểm tra các module**

Property toàn cục có thể ảnh hưởng parser được tạo bên trong module khác. Hãy xác định module nào dùng SpEL và context nào sẽ chịu ảnh hưởng.

**Bỏ qua ClassLoader**

Compiled class cần nhìn thấy mọi kiểu được dùng trong expression. ClassLoader không phù hợp có thể gây lỗi compilation hoặc loading.

**Bỏ qua advisory bảo mật**

SimpleEvaluationContext có safety guard riêng. Kiểm tra phiên bản Spring Framework và advisory CVE-2026-59283 trước khi bật compiler trong context này.

## 20. Ví dụ tổng hợp

Ví dụ dưới đây tạo parser ở MIXED mode, đánh giá expression trên object có kiểu ổn định và kiểm tra khả năng compile:

~~~java
import org.springframework.expression.spel.SpelCompilerMode;
import org.springframework.expression.spel.SpelParserConfiguration;
import org.springframework.expression.spel.standard.SpelExpression;
import org.springframework.expression.spel.standard.SpelExpressionParser;

SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                MyApplication.class.getClassLoader());

SpelExpressionParser parser =
        new SpelExpressionParser(configuration);

SpelExpression expression =
        (SpelExpression) parser.parseExpression(
                "payload.customer.name");

Message message = TestData.message("Lan");

// Lần đầu chạy bằng interpreter để thu thập thông tin kiểu.
String interpretedResult =
        expression.getValue(message, String.class);

// Có thể yêu cầu compile một cách tường minh sau khi có type information.
boolean compiled = expression.compileExpression();

String nextResult =
        expression.getValue(message, String.class);

System.out.println(interpretedResult); // Lan
System.out.println(nextResult);        // Lan
System.out.println(compiled);          // true nếu compile thành công
~~~

Trong ứng dụng thực tế, không cần gọi compileExpression thủ công nếu parser mode đã quản lý compilation. Ví dụ này minh họa cách quan sát khả năng compile và so sánh kết quả trên cùng một kiểu root object.

Nếu expression không được hỗ trợ hoặc thiếu thông tin kiểu, compileExpression có thể trả về false. Hãy tiếp tục dùng interpreter và giữ đúng hành vi của expression.

## 21. Ghi nhớ

- SpEL compiler tạo bytecode để tăng tốc expression được đánh giá lặp lại.
- Compiler dùng thông tin kiểu thu thập từ interpreted evaluation; kiểu runtime cần ổn định.
- Compiler không hỗ trợ mọi cú pháp; assignment, selection, projection, bean reference, custom resolver và ConversionService-dependent expressions nằm trong nhóm không compile được.
- OFF là mặc định; IMMEDIATE trả lỗi compiled evaluation cho caller; MIXED có thể quay lại interpreter và thử compile lại.
- MIXED cần thận trọng với side effect vì fallback có thể khiến expression được đánh giá lại.
- Cấu hình parser qua SpelParserConfiguration và chọn ClassLoader nhìn thấy tất cả kiểu liên quan.
- Có thể dùng compileExpression và revertToInterpreted khi cần quản lý compilation tường minh.
- Benchmark trên workload thật trước khi bật compiler.
- Kiểm thử kiểu dữ liệu thay đổi, null, collection rỗng và các expression không được hỗ trợ.
- Không bật compilation với SimpleEvaluationContext trong phiên bản bị ảnh hưởng bởi CVE-2026-59283; cập nhật bản vá và chỉ opt-in khi expression đáng tin cậy.
- Tách tối ưu hiệu năng khỏi thiết kế bảo mật và quyền của EvaluationContext.

## Tài liệu tham khảo

- Spring Framework Reference: SpEL Evaluation and Compilation — https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Security Advisory CVE-2026-59283 — https://spring.io/security/cve-2026-59283/
