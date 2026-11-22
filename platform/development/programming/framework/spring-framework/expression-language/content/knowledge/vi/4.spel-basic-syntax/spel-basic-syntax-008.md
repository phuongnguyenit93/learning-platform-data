# Phân biệt văn bản nguyên bản với phần được SpEL đánh giá

## 1. Vì sao cần phân biệt hai loại nội dung?

Spring Expression Language (SpEL) cho phép ứng dụng mô tả giá trị, điều kiện và thao tác trên object bằng một chuỗi biểu thức. Tuy nhiên, không phải mọi chuỗi có chứa ký hiệu giống SpEL đều tự động được Spring đánh giá.

Cần phân biệt:

- **Văn bản nguyên bản (raw text):** nội dung được giữ như chuỗi ký tự. Ví dụ `"Xin chào khách hàng"` chỉ là text nếu chưa được chuyển qua cơ chế xử lý biểu thức.
- **Biểu thức SpEL:** phần nội dung được parser hiểu theo grammar SpEL và được đánh giá trong một `EvaluationContext`.
- **Template:** một chuỗi gồm cả văn bản nguyên bản và một hoặc nhiều đoạn SpEL được đánh dấu bằng delimiter. Văn bản bên ngoài delimiter được giữ nguyên; phần bên trong delimiter được parse và đánh giá.

Sự phân biệt này ảnh hưởng trực tiếp đến kết quả trả về, cách cấu hình parser, cách Spring xử lý annotation và cả bảo mật khi nội dung đến từ người dùng.

## 2. Parsing thông thường xem toàn bộ chuỗi là biểu thức

Khi gọi `ExpressionParser.parseExpression(String)` mà không truyền `ParserContext`, parser mặc định xem toàn bộ chuỗi đầu vào là một biểu thức SpEL.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression("2 + 3 * 4");
    Integer result = expression.getValue(Integer.class);

    // result = 14

Toàn bộ chuỗi `2 + 3 * 4` là cú pháp SpEL. Parser không coi một phần nào là lời nhắn hoặc văn bản hiển thị cho người dùng.

Nếu truyền một câu văn thông thường:

    Expression expression =
        parser.parseExpression("Xin chào khách hàng");

thì parser sẽ cố diễn giải các từ đó như các identifier hoặc cấu trúc cú pháp. Chuỗi này không tự động trở thành một thông điệp văn bản. Thông thường nó sẽ phát sinh lỗi parse vì không phải cú pháp biểu thức hợp lệ.

Nếu muốn biểu thức trả về một chuỗi literal, hãy viết chuỗi theo cú pháp literal của SpEL:

    Expression expression = parser.parseExpression("'Xin chào khách hàng'");
    String message = expression.getValue(String.class);

Trong trường hợp này, dấu nháy đơn là một phần của cú pháp SpEL; giá trị trả về là chuỗi không bao gồm dấu nháy.

Quy tắc cần nhớ: với parsing thông thường, toàn bộ đầu vào là SpEL. Muốn giữ một giá trị text, hãy dùng literal chuỗi của SpEL hoặc không đưa nội dung đó qua parser.

## 3. Template kết hợp văn bản nguyên bản và biểu thức

Khi cần tạo một chuỗi có cả text cố định và giá trị động, hãy dùng template parsing.

Spring cung cấp `TemplateParserContext`, một implementation của `ParserContext`. Mặc định, nó dùng:

- Prefix: `#{`
- Suffix: `}`

Chỉ nội dung nằm giữa cặp delimiter mới được parse như biểu thức SpEL. Phần còn lại là văn bản nguyên bản.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Expression template = parser.parseExpression(
        "Xin chào, #{'Spring'}!",
        new TemplateParserContext()
    );

    String message = template.getValue(String.class);

    // message = "Xin chào, Spring!"

Trong chuỗi đầu vào:

| Đoạn | Cách xử lý |
| --- | --- |
| `Xin chào, ` | Văn bản nguyên bản, giữ nguyên |
| `#{'Spring'}` | Biểu thức SpEL, được đánh giá thành `Spring` |
| `!` | Văn bản nguyên bản, giữ nguyên |

Kết quả cuối cùng là một chuỗi được ghép từ các đoạn văn bản và kết quả của biểu thức.

Có thể đặt nhiều biểu thức trong cùng một template:

    String source =
        "Đơn hàng #{#order.id} có tổng tiền #{#order.total}.";

    Expression template = parser.parseExpression(
        source,
        new TemplateParserContext()
    );

    String message = template.getValue(context, String.class);

Mỗi đoạn nằm trong delimiter được đánh giá trong context được cung cấp. Các phần text bên ngoài không được hiểu là SpEL.

## 4. Cung cấp dữ liệu cho phần biểu thức

Template chỉ xác định phần nào cần được đánh giá. Các giá trị động vẫn cần được cung cấp thông qua root object hoặc `EvaluationContext`.

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

Cần chú ý cú pháp variable có dấu `#`. Trong template, `#{...}` là delimiter bao quanh biểu thức; còn `#customerName` là cách biểu thức tham chiếu variable tên `customerName`.

Hai ký hiệu này có vai trò khác nhau:

- `#{...}` xác định ranh giới biểu thức trong template.
- `#name` tham chiếu variable tên `name` bên trong biểu thức.

Có thể sử dụng root object thay cho variables:

    Expression template = parser.parseExpression(
        "Khách hàng #{name} có điểm #{score}.",
        new TemplateParserContext()
    );

    String message = template.getValue(customer, String.class);

Ở ví dụ này, `name` và `score` được tìm trên root object theo cơ chế property access của evaluation context mặc định. Cách truy cập cụ thể phụ thuộc vào object và các accessor được cấu hình.

## 5. Cấu hình delimiter bằng ParserContext

`ParserContext` mô tả cách parser nhận biết một template. Ngoài `TemplateParserContext` mặc định, ứng dụng có thể định nghĩa delimiter riêng bằng cách triển khai interface này.

Ví dụ dùng prefix và suffix tùy chỉnh:

    ParserContext parserContext = new ParserContext() {
        @Override
        public boolean isTemplate() {
            return true;
        }

        @Override
        public String getExpressionPrefix() {
            return "${";
        }

        @Override
        public String getExpressionSuffix() {
            return "}";
        }
    };

    Expression template = parser.parseExpression(
        "Xin chào ${#customerName}!",
        parserContext
    );

Trong ví dụ này, cặp `${...` không phải cú pháp mặc định của `TemplateParserContext`; nó chỉ hoạt động vì ứng dụng đã cung cấp một `ParserContext` dùng delimiter đó.

Không nên tự thay delimiter trong code mà không thống nhất với nơi tạo template. Parser và nguồn template phải dùng cùng một quy ước để tránh phần text bị hiểu nhầm hoặc biểu thức không được nhận diện.

## 6. Phân biệt SpEL delimiter với property placeholder

Trong ứng dụng Spring, hai dạng ký hiệu thường gặp là:

- `${property.name}`: placeholder để lấy giá trị cấu hình từ `Environment` hoặc nguồn property đã đăng ký.
- `#{expression}`: biểu thức SpEL được Spring đánh giá trong các điểm tích hợp hỗ trợ expression.

Ví dụ:

    @Value("${app.display-name}")
    private String displayName;

Spring thay placeholder bằng giá trị property `app.display-name` nếu cấu hình placeholder đã được thiết lập theo môi trường ứng dụng.

Ví dụ dùng SpEL:

    @Value("#{systemProperties['user.name']}")
    private String operatingSystemUser;

Ở đây nội dung bên trong `#{...}` là một biểu thức SpEL. Spring đánh giá biểu thức trong context của bean factory rồi chuyển kết quả sang kiểu field hoặc tham số đích nếu cần.

Có thể kết hợp text với biểu thức trong một giá trị được Spring xử lý:

    @Value("Ứng dụng: ${app.display-name}, người dùng: #{systemProperties['user.name']}")
    private String startupMessage;

Trong ví dụ này:

- `${app.display-name}` là placeholder cấu hình.
- `#{systemProperties['user.name']}` là phần SpEL.
- `Ứng dụng: ` và `, người dùng: ` là text cố định.

Đây là hành vi của cơ chế xử lý giá trị trong Spring, không phải quy tắc mà Java string tự thực hiện. Nếu chỉ gán chuỗi đó vào một biến Java thông thường, Java giữ nguyên các ký tự `${...}` và `#{...}`; không có placeholder resolver hoặc SpEL parser nào tự chạy.

Không nên đồng nhất `${...}` với `#{...}`: placeholder resolution và SpEL evaluation là hai cơ chế riêng, dù chúng có thể cùng xuất hiện trong một giá trị cấu hình được Spring xử lý.

## 7. Những ngữ cảnh khác nhau có quy tắc xử lý khác nhau

Cùng một chuỗi có thể cho kết quả khác nhau tùy nơi nó được sử dụng.

| Ngữ cảnh | Hành vi |
| --- | --- |
| Java string thông thường | Giữ nguyên ký tự; không tự evaluate SpEL |
| `parseExpression(source)` | Xem toàn bộ source là một biểu thức |
| `parseExpression(source, new TemplateParserContext())` | Giữ text ngoài delimiter và evaluate phần trong `#{...}` |
| `@Value` trong Spring | Spring xử lý placeholder và expression theo cơ chế tích hợp của container |
| Chuỗi truyền vào API nghiệp vụ tự viết | Chỉ được evaluate nếu API đó chủ động gọi parser hoặc resolver |

Ví dụ, cùng nội dung:

    "Chào #{#name}"

có thể có ba kết quả:

1. Trong Java string thông thường, kết quả vẫn là nguyên văn `Chào #{#name}`.
2. Khi parse như biểu thức độc lập, parser cố hiểu toàn bộ chuỗi là SpEL và thường báo lỗi cú pháp.
3. Khi parse bằng template context và cung cấp variable `name`, kết quả là `Chào Lan` nếu variable có giá trị `Lan`.

Vì vậy, khi debug một chuỗi chưa được thay thế, hãy xác định trước thành phần nào đang xử lý nó: Java, Spring placeholder resolver, SpEL parser hay một API tùy chỉnh.

## 8. Giá trị trả về và kiểu dữ liệu

Khi dùng template, kết quả cuối cùng là một chuỗi đã ghép. Biểu thức bên trong vẫn có thể trả về nhiều kiểu dữ liệu; giá trị đó được chuyển thành phần nội dung tương ứng trong kết quả template.

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

Nếu muốn lấy trực tiếp một giá trị có kiểu cụ thể, dùng biểu thức độc lập và yêu cầu kiểu kết quả:

    Expression expression = parser.parseExpression("#quantity * 2");

    Integer doubled = expression.getValue(context, Integer.class);

Template phù hợp với nội dung hiển thị hoặc chuỗi tổng hợp. Expression độc lập phù hợp với phép tính hoặc giá trị có kiểu được dùng tiếp trong logic ứng dụng.

Nếu ép kiểu kết quả không tương thích, evaluation hoặc chuyển đổi kiểu có thể thất bại. Không nên dựa vào việc mọi kết quả đều tự chuyển thành kiểu mà ứng dụng mong muốn.

## 9. Lỗi thường gặp khi trộn raw text và SpEL

### Dùng text thường trong parsing thông thường

Sai:

    parser.parseExpression("Xin chào #{#name}");

Nếu không truyền template context, parser xem cả chuỗi là SpEL. Text thông thường có thể khiến parse thất bại.

Cách phù hợp khi muốn trộn text và biểu thức:

    parser.parseExpression(
        "Xin chào #{#name}",
        new TemplateParserContext()
    );

### Quên delimiter của template

Nếu dùng `TemplateParserContext`, đoạn động phải được đặt trong delimiter đã cấu hình. Một variable nằm ngoài delimiter chỉ là text.

Ví dụ:

    "Xin chào #name"

không tương đương với:

    "Xin chào #{#name}"

Trong ví dụ thứ hai, phần `#name` mới được parser nhận diện như một biểu thức.

### Nhầm variable marker với template marker

`#name` là variable reference trong SpEL. `#{...}` là delimiter mặc định để đánh dấu expression trong template. Việc thiếu một dấu hoặc đặt sai vị trí có thể làm thay đổi hoàn toàn cách parser hiểu chuỗi.

### Nghĩ rằng Java tự evaluate chuỗi

Gán một chuỗi chứa `#{...}` vào field hoặc truyền nó qua method Java không làm SpEL chạy. Phải có một thành phần chủ động gọi parser hoặc một điểm tích hợp Spring có hỗ trợ expression.

### Dùng nhầm placeholder và SpEL

`${app.name}` dùng để tra cứu property. `#{...}` dùng cho SpEL. Nếu muốn tính toán, truy cập bean hoặc đọc object theo biểu thức, hãy dùng SpEL ở điểm tích hợp hỗ trợ nó. Nếu chỉ muốn lấy một giá trị cấu hình, placeholder thường rõ ràng và phù hợp hơn.

## 10. Bảo vệ ranh giới giữa text và biểu thức

Một template có thể thực thi logic. Vì vậy, nếu người dùng cung cấp nội dung có chứa delimiter `#{...}` và ứng dụng parse toàn bộ nội dung đó như template, người dùng có thể vô tình hoặc cố ý đưa biểu thức vào luồng đánh giá.

Một số nguyên tắc an toàn:

- Không parse nội dung tùy ý do người dùng nhập như một SpEL template.
- Phân biệt template do ứng dụng kiểm soát với dữ liệu text do người dùng cung cấp.
- Chỉ cho phép các biểu thức cần thiết trong template đã được kiểm soát.
- Cung cấp evaluation context với tập biến, object, accessor và resolver tối thiểu.
- Với nhu cầu data binding giới hạn, cân nhắc `SimpleEvaluationContext` thay vì context có đầy đủ quyền.
- Nếu cần hiển thị nguyên văn ký hiệu giống delimiter, hãy xử lý hoặc escape nội dung theo quy tắc rõ ràng của ứng dụng trước khi đưa vào parser.

Việc đổi delimiter không tự động tạo ra một ranh giới bảo mật. Nếu người dùng có thể gửi nội dung chứa delimiter mới và ứng dụng vẫn parse nó, biểu thức vẫn có thể được đánh giá.

## 11. Chọn đúng cách xử lý

Có thể quyết định theo mục tiêu:

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Giữ nguyên một câu văn | Dùng Java string hoặc dữ liệu text bình thường |
| Trả về một chuỗi literal từ SpEL | Dùng string literal trong biểu thức, ví dụ `'Xin chào'` |
| Tính toán hoặc lấy một giá trị có kiểu | Dùng `parseExpression` thông thường |
| Ghép text với các giá trị động | Dùng template parsing với `TemplateParserContext` |
| Đọc property cấu hình | Dùng placeholder `${...}` tại điểm Spring hỗ trợ |
| Tạo giá trị động trong `@Value` | Dùng biểu thức `#{...}` |
| Hiển thị nội dung người dùng nhập | Giữ nội dung như data; không tự động parse thành SpEL |

Trước khi viết hoặc debug một chuỗi, hãy tự hỏi: toàn bộ chuỗi có phải là một biểu thức, chỉ một vài đoạn là biểu thức, hay tất cả chỉ là text? Câu trả lời quyết định nên dùng parser thông thường, template parser hay không dùng SpEL.

## 12. Những điểm cần nhớ

- Java string không tự chạy SpEL.
- `parseExpression(String)` xem toàn bộ đầu vào là biểu thức.
- `TemplateParserContext` mặc định dùng `#{` và `}` để phân tách phần biểu thức khỏi text.
- Text bên ngoài delimiter được giữ nguyên; nội dung bên trong được parse và evaluate.
- `#name` là variable reference, khác với delimiter `#{...}`.
- `${...}` là property placeholder; `#{...}` là SpEL trong các điểm tích hợp của Spring.
- Template parsing trả về chuỗi tổng hợp; expression thông thường có thể trả về giá trị có kiểu.
- Parse một template không đáng tin cậy có thể khiến biểu thức do người dùng chèn vào được đánh giá; cần kiểm soát nguồn template và evaluation context.

Phân biệt rõ raw text, expression và template giúp tránh lỗi parse, tránh nhầm lẫn giữa placeholder với SpEL, đồng thời giữ quyền kiểm soát đối với nội dung nào được phép thực thi trong ứng dụng.
