# Phân biệt văn bản nguyên bản với phần được SpEL đánh giá

## 1. Ba loại nội dung cần phân biệt

Spring Expression Language (SpEL) cho phép ứng dụng mô tả giá trị, điều kiện và thao tác trên object bằng một chuỗi biểu thức. Tuy nhiên, một chuỗi ký tự chỉ được đánh giá khi nó đi qua parser hoặc một điểm tích hợp của Spring có hỗ trợ SpEL.

Trong thực tế có ba loại nội dung:

- **Văn bản nguyên bản (raw text):** chuỗi được giữ nguyên như dữ liệu. Ví dụ `"Xin chào khách hàng"` không tự trở thành biểu thức.
- **Biểu thức SpEL:** toàn bộ chuỗi được parser hiểu theo grammar SpEL. Ví dụ `2 + 3 * 4`.
- **Template:** chuỗi gồm văn bản nguyên bản và một hoặc nhiều đoạn biểu thức được đánh dấu bằng delimiter. Ví dụ `"Xin chào #{#customer.name}"`.

Sự khác biệt này quyết định parser hiểu chuỗi như thế nào, kết quả trả về có kiểu gì và nội dung nào thực sự được thực thi.

## 2. Java string không tự chạy SpEL

Một chuỗi Java chỉ là dữ liệu:

    String message = "Xin chào #{#customer.name}";

    System.out.println(message);

Kết quả vẫn là:

    Xin chào #{#customer.name}

Java compiler và JVM không tự tìm dấu `#{...}` để đánh giá biểu thức. Nếu muốn thay thế phần động, ứng dụng phải gọi một API xử lý template, hoặc chuyển chuỗi qua một điểm tích hợp Spring có hỗ trợ SpEL.

Điều này rất quan trọng khi debug. Nếu một thông báo vẫn chứa nguyên văn `#{...}`, cần xác định xem chuỗi đã được chuyển qua đúng bộ xử lý hay mới chỉ được lưu, đọc hoặc truyền qua các method Java.

## 3. Parsing thông thường xem toàn bộ đầu vào là biểu thức

Khi gọi `ExpressionParser.parseExpression(String)` mà không truyền `ParserContext`, parser xem toàn bộ chuỗi đầu vào là một biểu thức SpEL.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression("2 + 3 * 4");
    Integer result = expression.getValue(Integer.class);

    // result = 14

Toàn bộ chuỗi `2 + 3 * 4` là cú pháp SpEL. Parser không chia nó thành text và expression.

Nếu truyền một câu văn thông thường:

    Expression expression =
        parser.parseExpression("Xin chào khách hàng");

parser vẫn cố diễn giải các từ đó như identifier hoặc thành phần cú pháp. Chuỗi này không tự động trở thành thông điệp văn bản; thông thường nó sẽ gây lỗi parse vì không phải một biểu thức SpEL hợp lệ.

Nếu muốn biểu thức trả về một chuỗi literal, hãy dùng cú pháp literal của SpEL:

    Expression expression =
        parser.parseExpression("'Xin chào khách hàng'");

    String message = expression.getValue(String.class);

Dấu nháy đơn thuộc cú pháp biểu thức. Giá trị trả về là chuỗi `Xin chào khách hàng`, không bao gồm dấu nháy.

Hãy dùng parsing thông thường khi toàn bộ đầu vào chính là logic hoặc một giá trị SpEL. Nếu đầu vào là câu văn có chèn giá trị động, hãy dùng template parsing.

## 4. Template giữ nguyên text bên ngoài delimiter

Spring cung cấp `TemplateParserContext`, một implementation của `ParserContext`. Theo cấu hình mặc định, template dùng:

- Prefix: `#{`
- Suffix: `}`

Chỉ nội dung nằm giữa hai delimiter mới được parse như SpEL. Những đoạn bên ngoài được giữ nguyên như văn bản.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Expression template = parser.parseExpression(
        "Xin chào, #{'Spring'}!",
        new TemplateParserContext()
    );

    String message = template.getValue(String.class);

    // message = "Xin chào, Spring!"

Có thể phân tích chuỗi đầu vào thành ba phần:

| Đoạn | Cách xử lý |
| --- | --- |
| `Xin chào, ` | Raw text, giữ nguyên |
| `#{'Spring'}` | SpEL, được đánh giá thành `Spring` |
| `!` | Raw text, giữ nguyên |

Kết quả cuối cùng là chuỗi được ghép từ các đoạn văn bản và giá trị do biểu thức trả về.

Có thể đặt nhiều biểu thức trong một template:

    String source =
        "Đơn hàng #{#order.id} có tổng tiền #{#order.total}.";

    Expression template = parser.parseExpression(
        source,
        new TemplateParserContext()
    );

    String message = template.getValue(context, String.class);

Mỗi đoạn nằm trong delimiter được đánh giá trong context đã cung cấp. Phần text bên ngoài không được hiểu là SpEL.

## 5. Phần biểu thức lấy dữ liệu từ EvaluationContext

Template xác định ranh giới giữa text và expression. Nó không tự tạo ra dữ liệu cho các biến được tham chiếu bên trong biểu thức.

Ví dụ sử dụng variables:

    ExpressionParser parser = new SpelExpressionParser();

    Expression template = parser.parseExpression(
        "Xin chào #{#customerName}, mã đơn là #{#orderId}.",
        new TemplateParserContext()
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("customerName", "Lan");
    context.setVariable("orderId", "ORD-2026-001");

    String message = template.getValue(context, String.class);

Kết quả:

    Xin chào Lan, mã đơn là ORD-2026-001.

Cần phân biệt hai cách dùng ký hiệu:

- `#{...}` là delimiter xác định ranh giới biểu thức trong template.
- `#customerName` là variable reference bên trong biểu thức.

Có thể dùng root object thay cho variables:

    Expression template = parser.parseExpression(
        "Khách hàng #{name} có điểm #{score}.",
        new TemplateParserContext()
    );

    String message = template.getValue(customer, String.class);

Ở ví dụ này, `name` và `score` được truy cập trên root object theo property accessor của evaluation context. Cách truy cập thực tế phụ thuộc vào object và các accessor được cấu hình.

## 6. Có thể dùng delimiter tùy chỉnh

`ParserContext` mô tả cách parser nhận biết một template. Nếu ứng dụng cần delimiter khác, có thể dùng constructor của `TemplateParserContext` để cấu hình prefix và suffix.

Ví dụ dùng `[[` và `]]`:

    ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

    Expression template = parser.parseExpression(
        "Xin chào [[#customerName]]!",
        parserContext
    );

Delimiter trong ví dụ này chỉ có hiệu lực vì parser được truyền `parserContext` tương ứng. Nếu nguồn template và parser không thống nhất delimiter, đoạn động có thể bị giữ nguyên như text hoặc parser có thể xử lý chuỗi theo cách khác dự kiến.

Đổi delimiter không tự động thay đổi grammar SpEL bên trong. Nó chỉ thay đổi cách template nhận diện ranh giới giữa text và expression.

## 7. Phân biệt SpEL với property placeholder

Trong ứng dụng Spring, hai dạng ký hiệu thường gặp là:

- `${property.name}`: placeholder dùng để tra cứu giá trị cấu hình từ `Environment` hoặc nguồn property đã đăng ký.
- `#{expression}`: biểu thức SpEL được đánh giá tại những điểm tích hợp hỗ trợ expression.

Ví dụ placeholder:

    @Value("${app.display-name}")
    private String displayName;

Spring thay placeholder bằng giá trị của property `app.display-name` nếu cơ chế placeholder resolution đã được thiết lập trong môi trường ứng dụng.

Ví dụ SpEL:

    @Value("#{systemProperties['user.name']}")
    private String operatingSystemUser;

Nội dung bên trong `#{...}` là biểu thức SpEL. Spring đánh giá nó trong context của bean factory rồi chuyển kết quả sang kiểu field hoặc tham số đích nếu cần.

Có thể kết hợp cả hai trong một giá trị được Spring xử lý:

    @Value("Ứng dụng: ${app.display-name}, người dùng: #{systemProperties['user.name']}")
    private String startupMessage;

Trong ví dụ này:

- `${app.display-name}` được xử lý như property placeholder.
- `#{systemProperties['user.name']}` được xử lý như SpEL.
- `Ứng dụng: ` và `, người dùng: ` là text cố định.

Đây là hành vi của cơ chế xử lý giá trị trong Spring, không phải quy tắc của Java string. Nếu gán chuỗi đó vào một biến Java thông thường, các ký tự `${...}` và `#{...}` vẫn được giữ nguyên.

Không nên đồng nhất placeholder resolution với SpEL evaluation. Hai cơ chế có thể cùng xuất hiện trong một giá trị cấu hình, nhưng chúng có mục đích và thành phần xử lý khác nhau.

## 8. Mỗi ngữ cảnh có quy tắc xử lý riêng

Cùng một chuỗi có thể cho kết quả khác nhau tùy nơi sử dụng:

| Ngữ cảnh | Hành vi |
| --- | --- |
| Java string thông thường | Giữ nguyên ký tự; không tự evaluate |
| `parseExpression(source)` | Xem toàn bộ source là một biểu thức |
| `parseExpression(source, new TemplateParserContext())` | Giữ text ngoài delimiter và đánh giá phần trong `#{...}` |
| `@Value` trong Spring | Spring xử lý placeholder và expression theo cơ chế tích hợp của container |
| API nghiệp vụ tự viết | Chỉ evaluate nếu API chủ động gọi parser hoặc resolver |

Ví dụ, chuỗi:

    "Chào #{#name}"

có thể có ba cách xử lý:

1. Trong Java string thông thường, nó vẫn là nguyên văn `Chào #{#name}`.
2. Khi parse như biểu thức độc lập, parser cố hiểu toàn bộ chuỗi là SpEL và thường báo lỗi cú pháp.
3. Khi parse bằng template context và cung cấp variable `name`, kết quả là `Chào Lan` nếu variable có giá trị `Lan`.

Khi debug một chuỗi chưa được thay thế, hãy xác định thành phần nào đang xử lý nó: Java, Spring placeholder resolver, SpEL parser hay API tùy chỉnh.

## 9. Kiểu kết quả của expression và template

Một expression độc lập có thể trả về giá trị có kiểu cụ thể:

    Expression expression = parser.parseExpression("#quantity * 2");

    Integer doubled =
        expression.getValue(context, Integer.class);

Template dùng để tạo chuỗi tổng hợp. Các biểu thức bên trong có thể trả về số, boolean hoặc object; kết quả được chuyển thành nội dung tương ứng trong chuỗi cuối cùng.

Ví dụ:

    Expression template = parser.parseExpression(
        "Số lượng: #{#quantity}, còn hàng: #{#available}",
        new TemplateParserContext()
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("quantity", 3);
    context.setVariable("available", true);

    String message = template.getValue(context, String.class);

Kết quả:

    Số lượng: 3, còn hàng: true

Hãy dùng template cho nội dung hiển thị hoặc chuỗi tổng hợp. Dùng expression độc lập khi ứng dụng cần một giá trị có kiểu để tiếp tục xử lý logic.

Nếu yêu cầu kiểu kết quả không tương thích với giá trị thực tế, evaluation hoặc chuyển đổi kiểu có thể thất bại. Không nên giả định mọi biểu thức đều có thể chuyển thành kiểu mong muốn.

## 10. Lỗi thường gặp khi trộn raw text và SpEL

### Đưa text thường vào parser thông thường

Ví dụ:

    parser.parseExpression("Xin chào #{#name}");

Nếu không truyền template context, parser xem cả chuỗi là SpEL. Phần text có thể khiến parsing thất bại.

Nếu muốn trộn text và expression, hãy dùng:

    parser.parseExpression(
        "Xin chào #{#name}",
        new TemplateParserContext()
    );

### Đặt variable ngoài delimiter

Chuỗi:

    "Xin chào #name"

không tương đương với:

    "Xin chào #{#name}"

Trong template, chỉ phần nằm trong delimiter mới được đánh giá. `#name` đứng ngoài delimiter chỉ là ký tự text.

### Nhầm variable marker với template marker

`#name` là cách tham chiếu variable trong SpEL. `#{...}` là delimiter mặc định đánh dấu expression trong template. Thiếu một dấu hoặc đặt sai vị trí có thể làm thay đổi cách parser hiểu chuỗi.

### Nghĩ rằng Java tự evaluate

Gán chuỗi chứa `#{...}` vào field hoặc truyền qua method Java không làm SpEL chạy. Cần có thành phần chủ động gọi parser hoặc điểm tích hợp Spring hỗ trợ expression.

### Dùng nhầm placeholder và SpEL

`${app.name}` tra cứu property cấu hình. `#{...}` đánh giá biểu thức SpEL. Nếu chỉ cần lấy giá trị cấu hình, placeholder thường rõ ràng hơn. Nếu cần tính toán hoặc truy cập object theo biểu thức, dùng SpEL tại điểm tích hợp phù hợp.

## 11. Giữ ranh giới giữa dữ liệu và logic

Template có thể thực thi logic. Nếu người dùng cung cấp nội dung chứa delimiter `#{...}` và ứng dụng parse toàn bộ nội dung đó như template, biểu thức do người dùng chèn vào có thể được đánh giá.

Một số nguyên tắc:

- Không tự động parse nội dung người dùng nhập như một SpEL template.
- Phân biệt template do ứng dụng kiểm soát với dữ liệu text đến từ người dùng.
- Chỉ đưa vào context các variable và object cần thiết.
- Giới hạn property accessor, method resolver và các khả năng truy cập theo nghiệp vụ.
- Dùng `SimpleEvaluationContext` khi chỉ cần một tập tính năng data binding giới hạn.
- Nếu cần hiển thị nguyên văn ký hiệu giống delimiter, hãy quy định cách escape hoặc xử lý nội dung trước khi đưa vào parser.

Đổi delimiter không tự tạo ra một ranh giới bảo mật. Nếu dữ liệu không tin cậy vẫn được đưa vào parser với delimiter mới, biểu thức vẫn có thể được đánh giá.

## 12. Chọn cách xử lý phù hợp

| Nhu cầu | Cách xử lý |
| --- | --- |
| Giữ nguyên một câu văn | Dùng Java string hoặc dữ liệu text |
| Trả về chuỗi literal từ SpEL | Dùng string literal, ví dụ `'Xin chào'` |
| Tính toán hoặc lấy giá trị có kiểu | Dùng `parseExpression` thông thường |
| Ghép text với giá trị động | Dùng template parsing với `TemplateParserContext` |
| Đọc property cấu hình | Dùng `${...}` tại điểm Spring hỗ trợ placeholder |
| Tạo giá trị động trong `@Value` | Dùng biểu thức `#{...}` |
| Hiển thị nội dung người dùng nhập | Giữ nội dung như data; không tự động parse thành SpEL |

Trước khi xử lý một chuỗi, hãy xác định toàn bộ chuỗi có phải biểu thức hay chỉ một vài đoạn là biểu thức. Câu trả lời quyết định nên dùng parser thông thường, template parser hay không dùng SpEL.

## 13. Những điểm cần nhớ

- Java string không tự chạy SpEL.
- `parseExpression(String)` xem toàn bộ đầu vào là biểu thức.
- `TemplateParserContext` mặc định dùng `#{` và `}` để phân tách expression khỏi raw text.
- Text bên ngoài delimiter được giữ nguyên; nội dung bên trong được parse và evaluate.
- `#name` là variable reference, khác với delimiter `#{...}`.
- `${...}` là property placeholder; `#{...}` là SpEL trong các điểm tích hợp Spring hỗ trợ.
- Template tạo chuỗi tổng hợp; expression độc lập có thể trả về giá trị có kiểu.
- Không parse template không đáng tin cậy nếu chưa kiểm soát quyền trong evaluation context.

Phân biệt raw text, expression và template giúp tránh lỗi parsing, nhầm lẫn giữa placeholder với SpEL, đồng thời kiểm soát rõ nội dung nào được phép thực thi trong ứng dụng.
