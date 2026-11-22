# Định dạng biểu thức trong chuỗi cấu hình

SpEL thường xuất hiện bên trong những chuỗi cấu hình của Spring: giá trị inject bằng @Value, thuộc tính trong XML hoặc chuỗi được ứng dụng tự phân tích. Khi đó, cần phân biệt hai trường hợp: toàn bộ chuỗi là một biểu thức SpEL, hoặc chuỗi có văn bản cố định xen kẽ các đoạn biểu thức. Trường hợp thứ hai được gọi là template expression.

Việc phân tích một chuỗi template cần thêm thông tin về dấu phân cách. SpEL cung cấp TemplateParserContext cho mục đích này. Trong Spring, các tích hợp như @Value cũng có cơ chế nhận diện biểu thức theo quy ước của chúng. Hiểu đúng lớp cấu hình này giúp tránh nhầm cú pháp placeholder với SpEL và tránh đánh giá một chuỗi ở sai thời điểm.

## 1. Hai dạng chuỗi thường gặp

### 1.1. Chuỗi chỉ chứa một biểu thức

Khi toàn bộ đầu vào là biểu thức, parser nhận trực tiếp phần biểu thức:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "T(java.lang.Math).max(12, 30)"
);

Integer result = expression.getValue(Integer.class);
~~~

Ở đây chuỗi đầu vào là cú pháp SpEL thuần. Không cần đặt biểu thức trong cặp dấu #{...} khi gọi trực tiếp parseExpression(String).

Trong Spring, @Value có thể dùng cú pháp biểu thức:

~~~java
@Value("#{T(java.lang.Math).max(12, 30)}")
private int pageSize;
~~~

Dấu #{...} là quy ước để Spring nhận ra phần SpEL trong giá trị annotation. Nó không có nghĩa mọi lời gọi parseExpression(String) đều tự động bỏ cặp dấu này.

### 1.2. Văn bản cố định xen kẽ biểu thức

Có lúc kết quả cần là một chuỗi hoàn chỉnh gồm cả phần văn bản và dữ liệu động, ví dụ:

~~~text
Đơn hàng 1024 có tổng tiền là 250000.
~~~

Thay vì tự nối chuỗi trong Java, có thể viết một template:

~~~text
Đơn hàng #{#root.orderNumber} có tổng tiền là #{#root.total}.
~~~

Parser cần biết đoạn nào là văn bản thông thường và đoạn nào cần được đánh giá như SpEL. TemplateParserContext cung cấp quy ước dấu mở đầu và kết thúc cho những đoạn đó.

## 2. TemplateParserContext và dấu phân cách mặc định

TemplateParserContext là một ParserContext dành cho chế độ template. Constructor mặc định dùng:

- Prefix: #{
- Suffix: }

Mọi nội dung nằm giữa cặp dấu phân cách được xem là một biểu thức SpEL. Nội dung nằm ngoài các đoạn đó được giữ lại như văn bản cố định.

Ví dụ hoàn chỉnh:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Order order = new Order(1024L, new BigDecimal("250000"));

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Expression template = parser.parseExpression(
        "Đơn hàng #{#root.orderNumber} có tổng tiền là #{#root.total}.",
        new TemplateParserContext()
);

String message = template.getValue(context, String.class);
~~~

Trong ví dụ này, parser tạo một biểu thức template gồm ba phần: văn bản trước biểu thức đầu tiên, giá trị orderNumber, phần văn bản ở giữa, giá trị total và dấu chấm cuối. Khi gọi getValue, các đoạn SpEL được đánh giá bằng EvaluationContext đã cung cấp, sau đó ghép với phần văn bản cố định thành kết quả.

Nếu chỉ gọi parseExpression(String) mà không truyền TemplateParserContext, chuỗi có chứa văn bản như ví dụ trên không được hiểu theo chế độ template. Hãy truyền ParserContext rõ ràng khi tự phân tích chuỗi có nhiều phần văn bản và biểu thức.

## 3. Một template có thể chứa nhiều biểu thức

Một chuỗi template có thể chứa một hoặc nhiều đoạn SpEL. Các đoạn được đánh giá trong cùng môi trường đánh giá, nên có thể dùng chung root object, biến và những khả năng đã cấu hình trong EvaluationContext.

~~~java
String source =
        "Khách hàng #{#root.customer.name} đặt "
        + "#{#root.lines.size()} sản phẩm, tổng tiền "
        + "#{#root.total}.";

Expression template = parser.parseExpression(
        source,
        new TemplateParserContext()
);

String summary = template.getValue(context, String.class);
~~~

Mỗi đoạn trong cặp dấu phân cách là một biểu thức riêng. Phần văn bản giữa các đoạn được giữ nguyên. Điều này phù hợp với thông báo, nhãn hiển thị, mô tả hoặc nội dung cấu hình cần chèn một vài giá trị động.

Hãy giữ mỗi đoạn biểu thức ngắn và dễ đọc. Nếu một đoạn cần nhiều nhánh điều kiện hoặc tính toán nghiệp vụ dài, hãy cân nhắc chuyển phần logic đó vào một phương thức có tên rõ ràng hoặc chuẩn bị sẵn dữ liệu trên object đầu vào. Template nên thể hiện cách trình bày kết quả, không nên trở thành nơi chứa toàn bộ nghiệp vụ.

## 4. Dùng dấu phân cách tùy chỉnh

Nếu chuỗi cấu hình đã sử dụng #{ hoặc } cho một mục đích khác, có thể chọn cặp dấu phân cách khác bằng constructor của TemplateParserContext.

~~~java
ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

Expression template = parser.parseExpression(
        "Xin chào [[#root.displayName]], mã của bạn là [[#root.code]].",
        parserContext
);

String message = template.getValue(context, String.class);
~~~

Trong ví dụ này, chỉ nội dung nằm giữa [[ và ]] được phân tích như biểu thức. Văn bản còn lại được giữ nguyên.

Dấu phân cách tùy chỉnh hữu ích khi template được lưu trong file cấu hình hoặc được chia sẻ với một hệ thống khác đã có quy ước ký tự riêng. Hãy chọn cặp dấu ít xuất hiện trong văn bản thông thường, thống nhất giữa nơi tạo template và nơi phân tích, đồng thời ghi rõ quy ước đó trong tài liệu cấu hình.

ParserContext chỉ mô tả cách parser chia chuỗi thành văn bản và biểu thức. Nó không cấp quyền truy cập dữ liệu và cũng không thay thế EvaluationContext. Khi đánh giá template, vẫn cần cung cấp root object, biến và các resolver phù hợp.

## 5. Phân biệt ParserContext với EvaluationContext

Hai tên này thường xuất hiện cạnh nhau nhưng chịu trách nhiệm ở hai thời điểm khác nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| ParserContext | Phần nào của chuỗi là biểu thức, phần nào là văn bản? | TemplateParserContext với prefix #{ và suffix } |
| EvaluationContext | Khi chạy biểu thức, có thể nhìn thấy dữ liệu và gọi khả năng nào? | StandardEvaluationContext với root object, biến và accessor |

Có thể hình dung trình tự như sau:

~~~text
Chuỗi cấu hình
      |
      v
ExpressionParser + ParserContext
      |
      v
Expression / template đã phân tích
      |
      v
getValue(EvaluationContext)
      |
      v
Văn bản kết quả
~~~

ParserContext không biết object đơn hàng hoặc người dùng hiện tại là ai. EvaluationContext không quyết định dấu phân cách nào dùng để nhận diện các đoạn biểu thức trong chuỗi đầu vào. Tách rõ hai trách nhiệm này giúp chẩn đoán lỗi dễ hơn: lỗi nhận diện template thường nằm ở parser hoặc ParserContext; lỗi không tìm thấy thuộc tính, biến hoặc bean thường nằm ở EvaluationContext.

## 6. Biểu thức trong các chuỗi cấu hình Spring

Spring cung cấp các điểm tích hợp có thể xử lý SpEL. Một ví dụ phổ biến là @Value.

### 6.1. Giá trị động trong @Value

~~~java
@Component
public class RuntimeInfo {

    @Value("#{systemProperties['java.version']}")
    private String javaVersion;

    @Value("Phiên bản Java đang chạy: #{systemProperties['java.version']}")
    private String description;
}
~~~

Trường đầu tiên nhận giá trị của biểu thức. Trường thứ hai minh họa chuỗi có văn bản cố định xen kẽ biểu thức. Spring xử lý biểu thức trong quá trình tạo và inject bean.

Có thể dùng biểu thức để tính một giá trị:

~~~java
@Value("#{T(java.lang.Math).max(10, 20)}")
private int limit;
~~~

Kết quả của biểu thức được chuyển sang kiểu đích nếu cơ chế chuyển đổi của Spring hỗ trợ. Hãy chọn kiểu field hoặc tham số phù hợp với kết quả thực tế.

### 6.2. Placeholder và SpEL là hai cơ chế khác nhau

Spring còn hỗ trợ placeholder để lấy giá trị từ cấu hình. Ví dụ trong application.properties:

~~~properties
app.name=Order Service
app.max-items=50
~~~

Có thể inject các giá trị này bằng placeholder:

~~~java
@Value("${app.name}")
private String applicationName;

@Value("${app.max-items}")
private int maxItems;
~~~

Placeholder dùng dấu đô la và cặp ngoặc nhọn để tham chiếu thuộc tính cấu hình. SpEL dùng dấu # và cặp ngoặc nhọn để biểu diễn biểu thức. Hai cú pháp có mục đích khác nhau:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| ${...} | Tra cứu thuộc tính trong Environment/property sources | ${app.name} |
| #{...} | Phân tích và đánh giá biểu thức SpEL tại điểm tích hợp Spring hỗ trợ | #{T(java.lang.Math).max(10, 20)} |

Không nên mặc định rằng mọi giá trị trong application.properties hoặc application.yml có chứa #{...} sẽ tự được đánh giá. Việc đánh giá SpEL phụ thuộc vào thành phần Spring đang đọc giá trị đó. Chẳng hạn, lấy chuỗi bằng Environment.getProperty(...) không đồng nghĩa với việc yêu cầu Spring chạy chuỗi đó như một biểu thức.

Khi một giá trị cần cả placeholder và SpEL, hãy xác định rõ thứ tự phân giải tại điểm tích hợp đang dùng và kiểm tra kết quả bằng một cấu hình nhỏ. Tránh tự nối chuỗi cấu hình vào mã biểu thức nếu có thể truyền dữ liệu qua biến hoặc root object.

### 6.3. Chuỗi cấu hình trong XML

Các cấu hình XML của Spring cũng có thể dùng SpEL trong những thuộc tính mà container hỗ trợ expression:

~~~xml
<bean id="runtimeInfo" class="example.RuntimeInfo">
    <property name="javaVersion"
              value="#{systemProperties['java.version']}" />
</bean>
~~~

Cần phân biệt cú pháp XML với cú pháp SpEL bên trong giá trị thuộc tính. XML chịu quy tắc escape của XML; nội dung biểu thức chịu quy tắc cú pháp của SpEL. Nếu một chuỗi chứa ký tự đặc biệt, phải xử lý đúng ở cả hai lớp.

### 6.4. Giá trị YAML và thời điểm đánh giá

YAML chỉ định dạng dữ liệu cấu hình. Một chuỗi như sau tự nó vẫn là một giá trị văn bản:

~~~yaml
app:
  welcome-template: "Xin chào #{#root.displayName}"
~~~

Việc đọc chuỗi này từ Environment không tự động tạo ra một SpEL template. Nếu muốn đánh giá nó, ứng dụng cần chủ động đưa chuỗi tới ExpressionParser với TemplateParserContext và cung cấp EvaluationContext phù hợp, hoặc dùng một điểm tích hợp Spring có hỗ trợ SpEL theo hợp đồng của điểm đó.

Đây là khác biệt quan trọng giữa lưu một chuỗi có ký hiệu giống biểu thức và thực sự yêu cầu một thành phần đánh giá biểu thức.

## 7. Dấu nháy và các lớp escape

Một biểu thức có thể nằm đồng thời trong nhiều lớp cú pháp: Java, XML, YAML, properties và SpEL. Mỗi lớp có quy tắc escape riêng.

### 7.1. Chuỗi literal bên trong SpEL

SpEL dùng dấu nháy đơn cho string literal:

~~~text
#{'Xin chào'}
#{#root.name == 'admin'}
~~~

Nếu biểu thức được viết bên trong một Java String, dấu nháy kép dùng để bao chuỗi Java còn dấu nháy đơn có thể giữ nguyên cho SpEL:

~~~java
String source = "Tên người dùng: #{#root.name}";
~~~

Nếu nội dung biểu thức cần dấu nháy kép hoặc dấu gạch chéo ngược, phải escape theo cú pháp Java trước khi chuỗi tới parser. Khi đặt trong XML hoặc YAML, tiếp tục tuân theo quy tắc escape của định dạng tương ứng.

### 7.2. Không giả định một dấu gạch chéo xử lý được mọi lớp

Một ký tự có thể cần escape ở lớp ngoài nhưng lại có ý nghĩa khác ở lớp trong. Ví dụ, dấu nháy kép có thể là ký tự phân cách thuộc tính XML, ký tự trong chuỗi Java hoặc ký tự của nội dung biểu thức. Hãy xác định chuỗi thực tế mà ExpressionParser nhận được trước khi kết luận cú pháp SpEL sai.

Với template có nội dung văn bản chứa chính cặp dấu phân cách, đừng tự giả định rằng thêm dấu gạch chéo ngược luôn có tác dụng escape giống nhau ở mọi parser hoặc mọi phiên bản. Nếu delimiter xung đột với nội dung, cân nhắc chọn delimiter tùy chỉnh hoặc ghép phần văn bản cố định ở bên ngoài template.

## 8. Tách dữ liệu động khỏi chuỗi biểu thức

Không nên đưa trực tiếp dữ liệu do người dùng nhập vào nội dung biểu thức bằng cách nối chuỗi. Ví dụ, ghép tên người dùng vào một đoạn SpEL có thể làm dữ liệu được hiểu nhầm thành cú pháp.

Thay vào đó, giữ biểu thức cố định và truyền dữ liệu qua root object hoặc biến:

~~~java
Expression expression = parser.parseExpression(
        "Xin chào #{#displayName}",
        new TemplateParserContext()
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("displayName", userSuppliedName);

String message = expression.getValue(context, String.class);
~~~

Trong cách làm này, userSuppliedName là dữ liệu được đưa vào context, không phải một phần của mã biểu thức. Điều đó giúp tránh lỗi dấu nháy, lỗi cú pháp do đầu vào và giảm nguy cơ biểu thức bị thay đổi ngoài dự kiến.

Nếu biểu thức được lưu trong database hoặc file cấu hình có thể bị chỉnh sửa bởi người không tin cậy, hãy xem nội dung đó như mã có thể thực thi. Giới hạn root object, accessor, method và resolver theo đúng nhu cầu. Ưu tiên SimpleEvaluationContext cho data binding hạn chế; chỉ dùng context đầy đủ khi tính năng yêu cầu và đã kiểm soát nguồn biểu thức.

## 9. Parse một lần, đánh giá theo dữ liệu

Với template cấu hình ổn định, nên phân tích chuỗi một lần khi khởi tạo cấu hình hoặc component, rồi tái sử dụng Expression cho nhiều lần đánh giá nếu phù hợp. Mỗi lần đánh giá có thể truyền root object hoặc context chứa dữ liệu của lần đó.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression messageTemplate = parser.parseExpression(
        "Đơn hàng #{#root.id} có trạng thái #{#root.status}.",
        new TemplateParserContext()
);

String render(Order order) {
    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    return messageTemplate.getValue(context, String.class);
}
~~~

Cách tổ chức này tránh parse lặp lại cùng một chuỗi cấu hình. Đồng thời, context được tạo theo dữ liệu của từng lần render nên không vô tình dùng lại root object của request trước.

Nếu cấu hình có thể thay đổi trong thời gian chạy, cần xác định rõ thời điểm nạp lại và phân tích lại template. Khi parser báo lỗi, nên ghi nhận tên cấu hình hoặc vị trí nguồn để người vận hành biết chuỗi nào không hợp lệ; tránh ghi log dữ liệu nhạy cảm đã được chèn vào biểu thức hoặc kết quả.

## 10. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Chuỗi có #{...} nhưng không được thay thế | Đang đọc chuỗi như giá trị cấu hình thông thường | Kiểm tra thành phần nào thực sự gọi SpEL parser |
| Template bị báo lỗi cú pháp | Dùng parseExpression(String) cho chuỗi có văn bản xen kẽ biểu thức | Truyền TemplateParserContext hoặc ParserContext phù hợp |
| Không tìm thấy thuộc tính trong đoạn template | Root object hoặc EvaluationContext không có dữ liệu cần thiết | Kiểm tra root object, tên thuộc tính và accessor |
| Không tìm thấy biến | Biểu thức dùng #name nhưng context chưa đặt biến tương ứng | Kiểm tra setVariable và chính tả tên biến |
| Kết quả không đúng kiểu mong đợi | Giá trị biểu thức khác kiểu đích hoặc không chuyển đổi được | Kiểm tra getValue với kiểu kết quả và converter |
| Văn bản chứa dấu phân cách bị parse nhầm | Nội dung literal xung đột với prefix/suffix | Chọn delimiter khác hoặc ghép phần literal bên ngoài |
| Placeholder không được thay thế | Property source hoặc placeholder configurer chưa được cấu hình | Kiểm tra nguồn thuộc tính và cơ chế resolve placeholder |

Khi debug, hãy tách hai bước: trước tiên xác nhận parser tạo được Expression từ chuỗi; sau đó xác nhận getValue đánh giá đúng với context và dữ liệu thực tế. Nếu dùng tích hợp Spring, hãy kiểm tra quy tắc của tích hợp đó thay vì giả định nó hoạt động giống lời gọi parser thủ công.

## 11. Quy tắc thiết kế chuỗi cấu hình có SpEL

- Dùng biểu thức thuần khi toàn bộ giá trị là một phép tính hoặc một giá trị động.
- Dùng TemplateParserContext khi chuỗi có văn bản cố định xen kẽ các đoạn biểu thức.
- Giữ delimiter nhất quán; chỉ tùy chỉnh prefix/suffix khi định dạng chứa delimiter mặc định.
- Phân biệt placeholder thuộc tính với SpEL và chỉ dựa vào cơ chế được hỗ trợ tại điểm tích hợp.
- Giữ biểu thức ngắn, dễ đọc và tránh nhúng nghiệp vụ phức tạp vào chuỗi.
- Truyền dữ liệu qua root object hoặc biến, không nối đầu vào người dùng vào mã biểu thức.
- Cấu hình EvaluationContext với quyền truy cập tối thiểu và không đánh giá chuỗi không đáng tin cậy bằng context đầy đủ.
- Parse cấu hình ổn định một lần và xử lý rõ ràng lỗi parse khi khởi động hoặc khi nạp lại cấu hình.

## 12. Ghi nhớ

Một chuỗi cấu hình có thể là biểu thức SpEL thuần hoặc một template gồm văn bản cố định và nhiều đoạn biểu thức. Khi tự phân tích template, TemplateParserContext xác định prefix/suffix; EvaluationContext cung cấp dữ liệu và khả năng cần thiết lúc đánh giá. Trong Spring, @Value và một số điểm tích hợp khác có thể xử lý SpEL theo quy ước riêng, còn việc đọc một property thông thường không tự động đồng nghĩa với đánh giá SpEL.

Hãy luôn xác định ai phân tích chuỗi, delimiter nào được dùng, dữ liệu nào được cung cấp lúc chạy và nguồn cấu hình có đáng tin cậy hay không. Khi bốn điều đó rõ ràng, biểu thức trong cấu hình sẽ dễ đọc, dễ bảo trì và ít gây bất ngờ khi triển khai.