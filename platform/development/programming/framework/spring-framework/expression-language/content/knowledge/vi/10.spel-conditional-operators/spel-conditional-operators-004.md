# Elvis với chuỗi rỗng, null và giá trị false

## 1. Elvis operator dùng để làm gì?

Spring Expression Language (SpEL) cung cấp toán tử Elvis \`?:\` để chọn một giá trị mặc định khi giá trị bên trái không có nội dung phù hợp.

Cú pháp:

    value ?: defaultValue

SpEL đánh giá vế trái trước. Nếu vế trái có giá trị được chấp nhận, kết quả là giá trị đó. Nếu vế trái là \`null\` hoặc là chuỗi rỗng \`""\`, kết quả là vế phải.

Ví dụ:

    #displayName ?: 'Guest'

Biểu thức trên trả về \`Guest\` nếu \`#displayName\` là null hoặc chuỗi rỗng. Nếu có tên, biểu thức trả về chính tên đó.

Elvis giúp rút gọn những trường hợp thường phải viết điều kiện kiểm tra null hoặc chuỗi rỗng. Tuy nhiên, cần hiểu rõ giá trị nào được xem là thiếu. Đặc biệt, Boolean \`false\` không phải giá trị thiếu đối với toán tử này.

## 2. Hành vi với null

Khi vế trái là \`null\`, Elvis trả về vế phải.

    null ?: 'Unknown'

Kết quả:

    Unknown

Ví dụ với variable:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("#name ?: 'Unknown'");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("name", null);

    String result =
        expression.getValue(context, String.class);

    // result = "Unknown"

Nếu variable có giá trị:

    context.setVariable("name", "Lan");

    String result =
        expression.getValue(context, String.class);

Kết quả là:

    Lan

Elvis không thay đổi giá trị của variable. Nó chỉ chọn giá trị trả về cho expression đang được đánh giá.

Nếu expression truy cập property qua một object trung gian có thể null, hãy cân nhắc safe navigation trước khi áp dụng Elvis. Ví dụ:

    #customer?.name ?: 'Guest'

Nếu \`#customer\` là null, safe navigation trả về null và Elvis chọn \`Guest\`. Nếu bỏ safe navigation:

    #customer.name ?: 'Guest'

thì việc truy cập \`name\` có thể thất bại ngay khi \`#customer\` là null; Elvis không thể xử lý một lỗi xảy ra trước khi giá trị vế trái được tạo ra.

## 3. Hành vi với chuỗi rỗng

SpEL cũng xem chuỗi rỗng \`""\` là trường hợp cần dùng giá trị mặc định.

    '' ?: 'Unknown'

Kết quả:

    Unknown

Ví dụ:

    Expression expression =
        parser.parseExpression("#displayName ?: 'Guest'");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("displayName", "");

    String result =
        expression.getValue(context, String.class);

    // result = "Guest"

Khi chuỗi có nội dung, giá trị đó được giữ nguyên:

    context.setVariable("displayName", "Spring");

Kết quả là:

    Spring

Điểm này hữu ích khi dữ liệu đầu vào có thể là null hoặc chuỗi rỗng, chẳng hạn tên hiển thị, nhãn, mô tả ngắn hoặc một giá trị cấu hình tùy chọn.

## 4. Chuỗi chỉ chứa khoảng trắng không phải chuỗi rỗng

Elvis kiểm tra chuỗi rỗng, không tự động trim hoặc kiểm tra chuỗi có phải blank hay không.

Ví dụ:

    '   ' ?: 'Unknown'

Vế trái là một chuỗi có ba ký tự khoảng trắng, nên không phải chuỗi rỗng. Kết quả vẫn là chuỗi khoảng trắng, không phải \`Unknown\`.

Đây là khác biệt quan trọng khi xử lý dữ liệu form hoặc dữ liệu nhập từ người dùng. Chuỗi chỉ chứa khoảng trắng có thể trông giống như không có nội dung, nhưng Elvis vẫn giữ nó.

Nếu nghiệp vụ cần coi cả chuỗi chỉ có khoảng trắng là thiếu, hãy kiểm tra rõ ràng:

    #name != null and !#name.trim().isEmpty()
        ? #name
        : 'Unknown'

Điều kiện kiểm tra null đứng trước phép gọi \`trim()\`. Nhờ short-circuit của AND, vế sau không cần được đánh giá khi \`#name\` là null.

Trên môi trường Java hỗ trợ \`String.isBlank()\`, có thể dùng phương thức đó để biểu diễn quy tắc blank rõ hơn:

    #name != null and !#name.isBlank()
        ? #name
        : 'Unknown'

Hãy chọn quy tắc phù hợp với yêu cầu dữ liệu: chỉ chuỗi rỗng, hay cả chuỗi trắng.

## 5. Hành vi với Boolean false

Một điểm dễ nhầm là Elvis không xem Boolean \`false\` là giá trị thiếu.

    false ?: true

Kết quả vẫn là:

    false

Lý do: \`false\` là một giá trị Boolean hợp lệ. Nó không phải null và cũng không phải chuỗi rỗng.

Ví dụ với variable:

    Expression expression =
        parser.parseExpression("#enabled ?: true");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("enabled", false);

    Boolean enabled =
        expression.getValue(context, Boolean.class);

Kết quả:

    false

Nếu \`#enabled\` là null, cùng biểu thức sẽ trả về true. Nếu \`#enabled\` là false, nó vẫn trả về false.

Điều này đặc biệt quan trọng với các cờ cấu hình, trạng thái bật/tắt, quyền truy cập và lựa chọn của người dùng. Không nên dùng Elvis nếu nghiệp vụ muốn xem false tương đương với việc chưa cung cấp giá trị.

## 6. So sánh null, chuỗi rỗng, false và các giá trị khác

Bảng dưới đây tóm tắt hành vi của Elvis khi dùng vế phải là \`'DEFAULT'\` hoặc một giá trị mặc định tương ứng:

| Giá trị vế trái | Elvis có dùng vế phải? | Lý do |
| --- | --- | --- |
| \`null\` | Có | Giá trị null |
| \`""\` | Có | Chuỗi rỗng |
| \`"Lan"\` | Không | Chuỗi có nội dung |
| \`"   "\` | Không | Chuỗi có ký tự khoảng trắng |
| \`false\` | Không | Boolean false là giá trị hợp lệ |
| \`true\` | Không | Boolean true là giá trị hợp lệ |
| \`0\` | Không | Số 0 là giá trị hợp lệ |
| Collection rỗng | Không | Elvis không xem collection rỗng là chuỗi rỗng |

Ví dụ:

    false ?: true       // false
    0 ?: 10             // 0
    '' ?: 'Unknown'     // Unknown
    null ?: 'Unknown'   // Unknown
    '   ' ?: 'Unknown'  // chuỗi ba khoảng trắng

Không nên suy luận Elvis hoạt động giống toán tử truthy/falsy của JavaScript hoặc một số ngôn ngữ khác. SpEL có quy tắc cụ thể: null và chuỗi rỗng được thay bằng vế phải; Boolean false, số 0 và collection rỗng vẫn là giá trị hiện tại.

## 7. Elvis khác gì với toán tử ternary?

Toán tử ternary có dạng:

    condition ? valueIfTrue : valueIfFalse

Nó chọn một trong hai nhánh dựa trên điều kiện boolean.

Ví dụ:

    #score >= 80 ? 'Pass' : 'Fail'

Nếu điểm đạt ít nhất 80, kết quả là \`Pass\`; ngược lại là \`Fail\`.

Elvis có dạng:

    value ?: defaultValue

Nó không nhận một điều kiện boolean riêng. Nó kiểm tra giá trị bên trái có phải null hoặc chuỗi rỗng hay không.

| Tiêu chí | Ternary | Elvis |
| --- | --- | --- |
| Cú pháp | \`condition ? a : b\` | \`value ?: default\` |
| Mục đích | Chọn nhánh theo điều kiện | Cung cấp giá trị thay thế cho null/chuỗi rỗng |
| Với false | Là điều kiện false nếu dùng làm condition | Giữ nguyên false nếu false là vế trái |
| Với chuỗi rỗng | Phụ thuộc điều kiện do người viết đặt | Dùng vế phải |
| Với null | Phụ thuộc điều kiện và cách so sánh | Dùng vế phải |

Nếu cần default cho Boolean chỉ khi null nhưng vẫn giữ false, có thể dùng Elvis:

    #enabled ?: true

Hoặc dùng ternary để thể hiện điều kiện rõ ràng:

    #enabled != null ? #enabled : true

Cả hai cách đều giữ false và chỉ dùng true khi giá trị là null.

Nếu nghiệp vụ muốn coi false cũng là trường hợp cần thay thế, hãy viết điều kiện rõ ràng thay vì dùng Elvis:

    #enabled == true ? #enabled : #defaultEnabled

Biểu thức này trả về \`#defaultEnabled\` khi \`#enabled\` là false hoặc null. Điều kiện boolean phải phản ánh đúng quy tắc nghiệp vụ.

## 8. Dùng Elvis với property của object

Elvis thường được dùng để tạo giá trị mặc định khi đọc property có thể null hoặc rỗng.

Ví dụ root object là Customer:

    public class Customer {
        private String displayName;

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
    }

Đánh giá:

    Expression expression =
        parser.parseExpression("displayName ?: 'Guest'");

    String result =
        expression.getValue(customer, String.class);

Nếu \`displayName\` là null hoặc \`""\`, kết quả là \`Guest\`. Nếu property có tên thật, kết quả là tên đó.

Với property lồng nhau, cần xử lý khả năng object trung gian null:

    address?.city ?: 'Unknown'

Safe navigation giúp biểu thức trả về null khi address không tồn tại, sau đó Elvis có thể chọn giá trị mặc định.

Nếu chỉ viết:

    address.city ?: 'Unknown'

thì truy cập \`city\` vẫn cần object \`address\`. Khi address là null, evaluation có thể phát sinh lỗi trước khi Elvis nhận được giá trị.

## 9. Dùng Elvis trong template và annotation Spring

Elvis có thể xuất hiện bên trong template SpEL:

    Expression template = parser.parseExpression(
        "Xin chào #{#displayName ?: 'Guest'}!",
        new TemplateParserContext()
    );

    String message =
        template.getValue(context, String.class);

Nếu \`#displayName\` là null hoặc chuỗi rỗng, template tạo ra:

    Xin chào Guest!

Nếu có tên, tên đó được chèn vào chuỗi.

Trong các điểm tích hợp Spring hỗ trợ SpEL, có thể dùng Elvis trong annotation:

    @Value("#{systemProperties['app.user'] ?: 'Guest'}")
    private String userName;

Spring đánh giá biểu thức trong quá trình xử lý bean. Nếu system property có giá trị null hoặc chuỗi rỗng, field nhận \`Guest\`.

Cần nhớ đây là hành vi tại điểm tích hợp Spring có xử lý expression. Nếu chỉ lưu cùng chuỗi đó trong một Java string thông thường, SpEL không tự chạy.

## 10. Dùng Elvis với các phép toán và biểu thức kết hợp

Vế trái của Elvis có thể là một biểu thức phức tạp, miễn là kết quả có thể được kiểm tra theo quy tắc của Elvis.

Ví dụ:

    (#order?.customer?.displayName) ?: 'Guest'

Hoặc:

    (#config?.label) ?: 'Default label'

Dùng ngoặc khi biểu thức có nhiều toán tử hoặc nhiều bước truy cập để người đọc nhìn rõ phần nào là vế trái của Elvis.

Có thể kết hợp Elvis với ternary:

    (#customer?.name ?: 'Guest') == 'Admin'
        ? 'Administrator'
        : 'User'

Trong biểu thức này:

1. SpEL lấy tên customer nếu có.
2. Nếu tên null hoặc rỗng, Elvis thay bằng Guest.
3. Kết quả được so sánh với Admin.
4. Ternary chọn nhãn Administrator hoặc User.

Nếu biểu thức trở nên khó đọc, hãy tách thành các expression nhỏ hoặc đưa logic nghiệp vụ vào Java method rõ ràng thay vì tạo một chuỗi SpEL quá dài.

## 11. Những lỗi và hiểu nhầm thường gặp

### Nghĩ false sẽ kích hoạt default

Sai kỳ vọng:

    #enabled ?: true

Nếu \`#enabled\` là false, kết quả vẫn là false. Elvis chỉ thay null hoặc chuỗi rỗng.

Nếu muốn false cũng dùng default, hãy viết điều kiện ternary phù hợp với quy tắc nghiệp vụ.

### Nghĩ chuỗi khoảng trắng là rỗng

    '   ' ?: 'Unknown'

Kết quả vẫn là chuỗi khoảng trắng. Nếu cần coi blank là thiếu, hãy trim hoặc dùng isBlank trong một điều kiện tường minh.

### Nghĩ Elvis tự xử lý mọi null reference

    #customer.name ?: 'Guest'

Nếu customer null, việc truy cập name có thể thất bại trước khi Elvis được áp dụng. Dùng safe navigation:

    #customer?.name ?: 'Guest'

### Nhầm Elvis với phép OR

Elvis không phải phép OR logic. Nó chọn giá trị thay thế cho null hoặc chuỗi rỗng, không kiểm tra một trong hai vế có true hay không.

### Dùng default sai kiểu

Nếu expression được yêu cầu trả về Integer nhưng vế phải là chuỗi, việc chuyển đổi kiểu có thể thất bại. Hãy chọn giá trị mặc định tương thích với kiểu kết quả mong muốn.

### Bỏ qua việc evaluation vẫn có thể lỗi

Elvis không bắt mọi exception phát sinh trong quá trình đánh giá vế trái. Property không tồn tại, method không gọi được hoặc lỗi truy cập object vẫn có thể làm expression thất bại.

## 12. Kiểm tra và debug

Khi Elvis trả về giá trị không như mong muốn, hãy kiểm tra lần lượt:

1. Vế trái thực tế là null, chuỗi rỗng, false hay một giá trị khác?
2. Có phải chuỗi chỉ chứa khoảng trắng nhưng không rỗng?
3. Có object trung gian nào null trước khi Elvis được áp dụng?
4. Variable đã được đưa vào EvaluationContext chưa?
5. Vế phải có kiểu dữ liệu phù hợp với kết quả mong muốn không?
6. Expression có được đánh giá trong đúng context không?

Có thể kiểm tra bằng các expression nhỏ:

    null ?: 'fallback'
    '' ?: 'fallback'
    'Lan' ?: 'fallback'
    false ?: true
    0 ?: 10

Các trường hợp này giúp xác nhận trực tiếp quy tắc null, empty String và false mà không cần thêm object model phức tạp.

Phân biệt parse error với evaluation error cũng rất hữu ích. Cú pháp sai sẽ thất bại khi parse; property hoặc variable không hợp lệ thường chỉ bộc lộ khi evaluation cần truy cập chúng.

## 13. Những điểm cần nhớ

- Elvis có cú pháp \`value ?: defaultValue\`.
- Vế phải được dùng khi vế trái là null hoặc chuỗi rỗng.
- Chuỗi có nội dung được giữ nguyên.
- Chuỗi chỉ chứa khoảng trắng không tự động được xem là rỗng.
- Boolean false là giá trị hợp lệ và không kích hoạt default.
- Số 0 và collection rỗng cũng không kích hoạt default chỉ vì chúng rỗng hoặc bằng zero.
- Dùng safe navigation khi object trung gian có thể null.
- Dùng ternary khi cần quyết định dựa trên một điều kiện boolean, đặc biệt nếu false cũng được xem là trường hợp cần xử lý riêng.
- Elvis không thay thế validation, không bắt mọi evaluation exception và không tự tạo object graph.

Khi chọn giá trị mặc định trong SpEL, hãy xác định rõ nghiệp vụ xem những trạng thái nào là thiếu: null, chuỗi rỗng, chuỗi blank hay cả Boolean false. Viết biểu thức theo đúng quy tắc đó để tránh vô tình thay đổi dữ liệu hợp lệ.
