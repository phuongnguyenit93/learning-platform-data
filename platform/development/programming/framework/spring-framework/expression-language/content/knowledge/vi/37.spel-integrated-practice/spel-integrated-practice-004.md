# Xây expression điều kiện với Elvis và toán tử ba ngôi

## 1. Mục tiêu của expression điều kiện

Spring Expression Language (SpEL) hỗ trợ các toán tử điều kiện để chọn giá trị theo dữ liệu runtime. Hai cú pháp thường dùng là:

- **Toán tử ba ngôi (ternary):** condition ? valueIfTrue : valueIfFalse.
- **Toán tử Elvis:** value ?: defaultValue.

Ternary phù hợp khi cần chọn giữa hai nhánh theo một điều kiện Boolean. Elvis phù hợp khi cần dùng một giá trị mặc định nếu biểu thức bên trái không có giá trị hữu ích.

Ví dụ:

    #score >= 50 ? 'PASS' : 'FAIL'

    #customerName ?: 'Guest'

Expression đầu tiên quyết định kết quả PASS hoặc FAIL. Expression thứ hai trả về customerName nếu có giá trị phù hợp, nếu không thì dùng Guest.

Hai toán tử có mục đích khác nhau. Hãy chọn cú pháp theo quyết định cần biểu đạt thay vì cố gộp mọi trường hợp vào một expression dài.

## 2. Toán tử ba ngôi: condition ? trueValue : falseValue

Cú pháp tổng quát:

    condition ? valueIfTrue : valueIfFalse

SpEL đánh giá condition. Nếu kết quả là true, expression trả về valueIfTrue; nếu false, trả về valueIfFalse.

Ví dụ:

    #age >= 18 ? 'ADULT' : 'MINOR'

Nếu age là 20, kết quả là ADULT. Nếu age là 16, kết quả là MINOR.

Ví dụ với số:

    #quantity > 0 ? #price * #quantity : 0

Nếu quantity lớn hơn 0, expression tính thành tiền. Nếu không, kết quả là 0.

Điều kiện phải cho ra giá trị Boolean hoặc giá trị có thể được chuyển đổi phù hợp thành Boolean theo EvaluationContext. Nếu điều kiện là null hoặc không thể đánh giá thành Boolean, evaluation có thể thất bại.

## 3. Ví dụ Java đầy đủ với EvaluationContext

Có thể parse expression một lần rồi đánh giá với các variable khác nhau.

    ExpressionParser parser =
        new SpelExpressionParser();

    Expression expression =
        parser.parseExpression(
            "#score >= #passMark ? 'PASS' : 'FAIL'"
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("score", 82);
    context.setVariable("passMark", 60);

    String result =
        expression.getValue(context, String.class);

    // result = "PASS"

Thay đổi dữ liệu:

    context.setVariable("score", 45);

    String nextResult =
        expression.getValue(context, String.class);

    // nextResult = "FAIL"

Expression source không đổi. Mỗi lần getValue, SpEL đánh giá điều kiện theo giá trị variable hiện tại rồi chọn đúng một nhánh kết quả.

Đây là cách sử dụng dễ kiểm thử và tránh việc ghép dữ liệu đầu vào vào source expression.

## 4. Hai nhánh có thể trả về giá trị khác kiểu

Ternary trả về giá trị của nhánh được chọn. Hai nhánh có thể là các expression khác nhau, nhưng nên có kiểu kết quả tương thích với mục đích sử dụng.

Ví dụ:

    #active ? 'ENABLED' : 'DISABLED'

Cả hai nhánh đều trả về String.

Ví dụ:

    #hasDiscount ? #discountAmount : 0

Một nhánh có thể trả về BigDecimal, nhánh kia là số nguyên. SpEL có thể áp dụng chuyển đổi kiểu tùy context và kiểu đích, nhưng không nên dựa vào chuyển đổi ngầm nếu kiểu kết quả quan trọng.

Có thể chỉ định kiểu đích khi gọi getValue:

    BigDecimal amount =
        expression.getValue(context, BigDecimal.class);

Nếu hai nhánh không tương thích, conversion có thể thất bại. Hãy dùng literal và variable có kiểu nhất quán, hoặc chuyển đổi rõ ràng trước khi trả kết quả.

## 5. Toán tử Elvis: value ?: defaultValue

Elvis là cách viết ngắn cho trường hợp muốn dùng giá trị mặc định khi vế trái không có giá trị phù hợp.

Cú pháp:

    expression ?: defaultValue

Ví dụ:

    #displayName ?: 'Anonymous'

Nếu displayName có giá trị, expression trả về giá trị đó. Nếu displayName là null hoặc chuỗi rỗng, Elvis trả về Anonymous.

Cách viết tương đương với ý tưởng dùng ternary:

    #displayName != null and #displayName != ''
        ? #displayName
        : 'Anonymous'

Elvis giúp tránh lặp lại cùng một expression ở cả điều kiện và nhánh true.

Ví dụ Java:

    context.setVariable("displayName", null);

    Expression expression =
        parser.parseExpression(
            "#displayName ?: 'Anonymous'"
        );

    String result =
        expression.getValue(context, String.class);

    // result = "Anonymous"

Elvis đặc biệt hữu ích khi đọc property hoặc variable tùy chọn và cần một giá trị fallback.

## 6. Elvis xử lý null và chuỗi rỗng

Trong SpEL, Elvis chọn vế phải khi vế trái là null hoặc là một chuỗi rỗng.

Ví dụ:

    #name ?: 'Unknown'

Các trường hợp:

| Giá trị name | Kết quả |
| --- | --- |
| 'Lan' | 'Lan' |
| null | 'Unknown' |
| '' | 'Unknown' |
| '   ' | '   ' |

Chuỗi chỉ chứa khoảng trắng không phải chuỗi rỗng, vì vậy Elvis giữ nguyên giá trị đó.

Nếu nghiệp vụ coi chuỗi chỉ có khoảng trắng là thiếu dữ liệu, hãy chuẩn hóa bằng trim() hoặc kiểm tra isBlank() trước khi áp dụng default:

    #name != null and !#name.isBlank()
        ? #name
        : 'Unknown'

Hoặc chuẩn hóa ở Java trước khi đưa variable vào context.

Elvis không tự hiểu mọi loại collection rỗng là null. Một List hoặc Map rỗng vẫn là một object collection. Nếu cần fallback cho collection rỗng, hãy kiểm tra isEmpty() rõ ràng.

## 7. Elvis với property có thể null

Giả sử object customer có property nickname có thể null.

Có thể viết:

    #customer.nickname ?: #customer.name

Nếu nickname có giá trị, dùng nickname. Nếu null hoặc rỗng, dùng name.

Nếu customer cũng có thể null, cần bảo vệ đường dẫn:

    #customer?.nickname ?: 'Guest'

Safe navigation trả về null khi customer là null; Elvis sau đó chọn Guest.

Với nhiều tầng property:

    #customer?.profile?.displayName ?: 'Guest'

Expression này tránh lỗi khi customer hoặc profile null, rồi chọn giá trị mặc định nếu displayName null hoặc rỗng.

Hãy phân biệt null của object trung gian với giá trị null của property cuối. Safe navigation xử lý receiver null; Elvis xử lý kết quả bên trái không có giá trị phù hợp.

## 8. Kết hợp ternary với toán tử logic

Điều kiện của ternary có thể là một biểu thức Boolean kết hợp AND, OR và NOT.

Ví dụ:

    #customer.active and #order.total >= #minimum
        ? 'APPROVED'
        : 'REVIEW'

Có thể dùng ngoặc để làm rõ nhóm điều kiện:

    (#customer.active and #customer.verified)
        ? 'TRUSTED'
        : 'CHECK_REQUIRED'

Nếu điều kiện dài, hãy viết từng nhóm trên dòng riêng và dùng ngoặc tường minh.

AND và OR có quy tắc short-circuit. Khi kết quả đã được xác định, SpEL không cần đánh giá phần còn lại của cùng phép logic. Điều này hữu ích khi vế sau chỉ hợp lệ nếu vế trước đã xác nhận object tồn tại.

Ví dụ:

    #customer != null and #customer.active
        ? 'ACTIVE'
        : 'INACTIVE'

Nếu customer là null, vế sau của AND không được đánh giá.

## 9. Kết hợp Elvis và ternary

Có thể dùng Elvis để chuẩn hóa giá trị trước khi dùng ternary, hoặc dùng ternary để chọn giữa các giá trị có điều kiện.

Ví dụ:

    (#customer?.membershipLevel ?: 'STANDARD') == 'GOLD'
        ? 'PREMIUM_SHIPPING'
        : 'NORMAL_SHIPPING'

Đầu tiên, expression lấy membershipLevel. Nếu null hoặc rỗng, dùng STANDARD. Sau đó so sánh với GOLD và chọn kết quả.

Ví dụ khác:

    #order?.total ?: 0

Expression trả về total nếu có giá trị, nếu không dùng 0. Có thể đặt nó trong một phép tính:

    (#order?.total ?: 0) >= #freeShippingThreshold
        ? 'FREE'
        : 'CHARGED'

Dùng ngoặc khi kết hợp nhiều toán tử để người đọc hiểu rõ thứ tự xử lý và tránh nhầm precedence.

## 10. Dùng ternary cho nhãn hoặc trạng thái hiển thị

Ternary phù hợp với quyết định đơn giản có hai kết quả.

Ví dụ trạng thái đơn hàng:

    #paid ? 'PAID' : 'UNPAID'

Ví dụ phân quyền hiển thị:

    #isAdmin ? 'FULL_ACCESS' : 'READ_ONLY'

Ví dụ chọn nhãn theo số lượng:

    #stock > 0 ? 'IN_STOCK' : 'OUT_OF_STOCK'

Nếu cần nhiều hơn hai trạng thái, có thể dùng ternary lồng nhau nhưng nên cân nhắc chuyển sang Java method hoặc mapping.

Ví dụ ba trạng thái:

    #stock > 10
        ? 'AVAILABLE'
        : (#stock > 0 ? 'LOW_STOCK' : 'OUT_OF_STOCK')

Biểu thức này vẫn ngắn và có mục tiêu rõ ràng. Khi số nhánh tăng, việc lồng ternary sẽ khó bảo trì.

## 11. Tránh nested ternary quá sâu

Một expression như:

    #score >= 90
        ? 'EXCELLENT'
        : #score >= 80
            ? 'GOOD'
            : #score >= 60
                ? 'PASS'
                : 'FAIL'

có thể chạy nhưng khó đọc hơn khi thêm điều kiện hoặc thay đổi thứ tự ngưỡng.

Với nhiều mức phân loại, hãy chuyển logic sang Java:

    String classifyScore(int score) {
        if (score >= 90) {
            return "EXCELLENT";
        }
        if (score >= 80) {
            return "GOOD";
        }
        if (score >= 60) {
            return "PASS";
        }
        return "FAIL";
    }

Nếu rule cần cấu hình động, có thể expose một function nhỏ, thuần và có tên rõ ràng:

    #classifyScore(#score)

Không nên biến một expression thành một chương trình nhiều nhánh chỉ để tránh viết Java.

## 12. Elvis với collection và Map

Elvis không coi mọi collection rỗng là thiếu dữ liệu.

Ví dụ:

    #members ?: {}

Nếu members là null, kết quả là List rỗng. Nhưng nếu members đã là một List rỗng, Elvis giữ nguyên List đó; nó không tự thay thế chỉ vì collection không có phần tử.

Nếu muốn dùng fallback khi List rỗng:

    #members != null and !#members.isEmpty()
        ? #members
        : #defaultMembers

Với Map:

    #settings != null and !#settings.isEmpty()
        ? #settings
        : {:}

Nếu chỉ muốn default khi Map null, có thể dùng:

    #settings ?: {:}

Hãy phân biệt ba trạng thái:

- Null: không có object collection.
- Empty: collection tồn tại nhưng không có phần tử.
- Non-empty: collection có ít nhất một phần tử.

Chọn điều kiện theo đúng ý nghĩa nghiệp vụ.

## 13. Kết hợp với selection và projection

Ternary hoặc Elvis có thể dùng trên kết quả của selection/projection.

Ví dụ chọn collection kết quả hoặc fallback:

    #orders.?[status == 'PAID'] ?: {}

Selection trả về List các đơn hàng phù hợp. Nếu không có kết quả và collection rỗng, Elvis có thể dùng List rỗng mặc định.

Ví dụ lấy tên khách hàng đầu tiên có giá trị:

    #customers.?[active == true].![name][0] ?: 'Unknown'

Tuy nhiên, truy cập index [0] trên collection rỗng có thể phát sinh lỗi trước khi Elvis nhận được kết quả. Elvis không bảo vệ một thao tác index đã thất bại.

Hãy kiểm tra collection trước hoặc dùng select first:

    #customers.^[active == true]?.name ?: 'Unknown'

Cách này lấy phần tử active đầu tiên, dùng safe navigation nếu không có phần tử và chọn Unknown khi kết quả null hoặc rỗng.

Với collection lớn, hãy cân nhắc chi phí selection/projection và tạo collection trung gian. Nếu chỉ cần một phần tử, select first thường thể hiện ý định tốt hơn.

## 14. Kiểm soát kiểu và giá trị null

Khi dùng Elvis hoặc ternary, hãy xác định rõ kiểu của từng nhánh và kiểu kết quả.

Ví dụ:

    #discount != null ? #discount : 0

Nếu discount là BigDecimal còn 0 là Integer, conversion có thể được yêu cầu khi caller lấy kết quả dưới kiểu BigDecimal.

Cách rõ ràng hơn:

    #discount != null
        ? #discount
        : T(java.math.BigDecimal).ZERO

Hoặc chuẩn hóa kiểu dữ liệu ở Java:

    context.setVariable(
        "discount",
        discount != null ? discount : BigDecimal.ZERO
    );

    BigDecimal result =
        parser.parseExpression("#discount")
            .getValue(context, BigDecimal.class);

Đối với giá trị tiền tệ, nên dùng BigDecimal và quy tắc scale/rounding rõ ràng. Tránh trộn Integer, Double và BigDecimal trong các nhánh nếu phép tính cần độ chính xác tài chính.

Nếu giá trị có thể null, hãy quyết định null có nghĩa là thiếu dữ liệu, không hợp lệ hay giá trị mặc định. Không dùng Elvis để âm thầm biến một lỗi dữ liệu thành một giá trị hợp lệ nếu nghiệp vụ cần báo lỗi.

## 15. Thứ tự ưu tiên và ngoặc

Expression có nhiều toán tử sẽ được phân tích theo precedence của SpEL. Khi kết hợp ternary, Elvis, AND, OR, so sánh và phép toán số học, hãy dùng ngoặc để thể hiện ý định.

Ví dụ:

    (#active and #verified)
        ? (#discount ?: 0)
        : 0

Expression này:

1. Kiểm tra active và verified.
2. Nếu cả hai đúng, lấy discount hoặc 0 nếu thiếu.
3. Nếu điều kiện sai, trả về 0.

Nếu bỏ ngoặc ở expression phức tạp, người đọc có thể hiểu sai thứ tự kết hợp dù parser vẫn có quy tắc xác định.

Không nên dựa vào trí nhớ về precedence khi một cặp ngoặc có thể làm rõ ý định.

## 16. Tách điều kiện và giá trị mặc định để dễ kiểm thử

Với rule quan trọng, hãy giữ source cố định và truyền variable qua EvaluationContext.

Ví dụ:

    Expression expression =
        parser.parseExpression(
            "#active and #verified"
                + " ? (#displayName ?: 'Guest')"
                + " : 'ACCESS_DENIED'"
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("active", true);
    context.setVariable("verified", true);
    context.setVariable("displayName", "");

    String result =
        expression.getValue(context, String.class);

    // result = "Guest"

Có thể kiểm thử riêng các trường hợp:

- active và verified đều true, displayName có nội dung.
- active và verified đều true, displayName null.
- active và verified đều true, displayName rỗng.
- Một trong hai điều kiện false.
- Variable bắt buộc chưa được đăng ký.
- Kiểu variable không phù hợp.

Nếu expression dài đến mức khó viết test cho từng nhánh, hãy tách các facts hoặc logic nhiều bước sang Java.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ternary báo lỗi điều kiện | Condition null hoặc không thể chuyển thành Boolean | Kiểm tra kiểu và null trước khi dùng |
| Chọn sai nhánh | Điều kiện hoặc nhóm AND/OR không rõ | Dùng ngoặc và kiểm tra từng điều kiện |
| Elvis không dùng fallback cho List rỗng | Collection rỗng không đồng nghĩa null | Kiểm tra isEmpty() |
| Elvis giữ chuỗi khoảng trắng | Chuỗi không rỗng | trim hoặc isBlank trước khi chọn default |
| Index lỗi trước Elvis | Indexer thất bại trước khi Elvis chạy | Kiểm tra size hoặc dùng select first với safe navigation |
| Conversion error ở hai nhánh | Kiểu kết quả không tương thích | Dùng kiểu thống nhất hoặc conversion rõ ràng |
| Nested ternary khó đọc | Quá nhiều nhánh | Chuyển sang Java method hoặc mapping |
| Default che mất lỗi dữ liệu | Dùng Elvis cho field bắt buộc | Validate và báo lỗi thay vì âm thầm fallback |
| Variable không tìm thấy | Chưa đăng ký hoặc sai tên | Kiểm tra EvaluationContext |

Khi debug, hãy tách condition khỏi nhánh kết quả, kiểm tra giá trị từng variable và xác nhận kiểu của expression bên trái Elvis.

## 18. Những điểm cần nhớ

- Ternary có cú pháp condition ? trueValue : falseValue.
- Ternary chọn đúng một nhánh dựa trên điều kiện Boolean.
- Elvis có cú pháp value ?: defaultValue.
- Elvis chọn default khi vế trái là null hoặc chuỗi rỗng.
- Chuỗi chỉ có khoảng trắng không phải chuỗi rỗng.
- Collection rỗng không tự động kích hoạt Elvis; dùng isEmpty() khi cần.
- Safe navigation bảo vệ thao tác trên receiver null; Elvis xử lý kết quả null/rỗng ở vế trái.
- Indexer có thể thất bại trước khi Elvis được đánh giá; kiểm tra collection trước khi truy cập index.
- Hai nhánh ternary nên trả về kiểu tương thích với caller.
- Dùng ngoặc để làm rõ precedence khi kết hợp AND, OR, ternary và Elvis.
- Tránh nested ternary nhiều tầng; chuyển logic nhiều nhánh sang Java.
- Giữ expression source cố định và truyền dữ liệu qua variables.
- Kiểm thử cả true, false, null, empty string, whitespace, collection rỗng và kiểu không hợp lệ.
- Không dùng default để che giấu dữ liệu bắt buộc đang thiếu.

Ternary phù hợp để chọn giữa hai kết quả theo một quyết định rõ ràng. Elvis phù hợp để cung cấp fallback cho giá trị null hoặc chuỗi rỗng. Khi kết hợp hai toán tử, hãy xác định rõ điều kiện, kiểu dữ liệu và ý nghĩa của giá trị mặc định để expression dễ đọc, dễ kiểm thử và không che giấu lỗi nghiệp vụ.

## Tài liệu tham khảo

- Spring Framework Reference — The Ternary Operator: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-ternary.html
- Spring Framework Reference — The Elvis Operator: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html
- Spring Framework Reference — Operators: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html
- Spring Framework Reference — Safe Navigation Operator: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html
- Spring Framework Reference — Collection Selection and Projection: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html
