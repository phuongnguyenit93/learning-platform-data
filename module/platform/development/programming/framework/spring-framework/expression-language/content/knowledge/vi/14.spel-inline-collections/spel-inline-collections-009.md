# Giới hạn kích thước và dữ liệu do người dùng cung cấp

SpEL có thể tạo list, map, array, truy cập object và gọi method trong lúc đánh giá biểu thức. Những khả năng này hữu ích khi biểu thức do ứng dụng kiểm soát, nhưng cần được giới hạn cẩn thận nếu chuỗi biểu thức hoặc dữ liệu đầu vào đến từ người dùng.

Một biểu thức ngắn vẫn có thể yêu cầu cấp phát một mảng rất lớn, duyệt một collection lớn hoặc gọi method tốn tài nguyên. Ngược lại, một biểu thức dài chưa chắc nguy hiểm, nhưng làm tăng chi phí parse, lưu trữ, log và kiểm tra. Vì vậy, cần kiểm soát riêng kích thước biểu thức, kích thước dữ liệu, quyền truy cập của EvaluationContext và chi phí thực thi.

**Giới hạn kích thước là một phần của thiết kế đầu vào; nó không thay thế việc giới hạn những gì biểu thức được phép làm.**

## 1. Xác định nguồn dữ liệu và mức độ tin cậy

Trước khi đánh giá biểu thức, cần phân biệt dữ liệu nào do ứng dụng tạo và dữ liệu nào do người dùng kiểm soát:

| Thành phần | Ví dụ | Cách quản lý |
|---|---|---|
| Chuỗi biểu thức | Điều kiện do người dùng nhập | Giới hạn độ dài, kiểm tra cú pháp và quyền biểu thức |
| Giá trị đầu vào | Tên, mã, số lượng, danh sách | Kiểm tra kiểu, độ dài, số phần tử và miền giá trị |
| Root object | Order, Customer, Report | Chỉ cung cấp object cần thiết, tránh lộ toàn bộ domain |
| Biến context | #limit, #selectedIds | Gán giá trị đã xác thực và đúng kiểu |
| Object có thể gọi method | Service hoặc policy | Chỉ cung cấp method cần thiết, giới hạn tác dụng phụ |
| Kết quả biểu thức | List, Map, Array, Boolean | Kiểm tra kiểu, kích thước và nội dung trước khi sử dụng |

Một chuỗi biểu thức do đội phát triển viết sẵn có thể được tin cậy theo quy trình review của ứng dụng. Biểu thức do người dùng nhập, lưu trong database hoặc nhận từ API cần được xem là đầu vào không tin cậy cho đến khi đã qua chính sách kiểm tra.

Không nên đánh đồng “parse thành công” với “an toàn”. Parser chỉ xác nhận cú pháp có thể được chuyển thành Expression; nó không xác nhận biểu thức có quyền truy cập phù hợp hoặc chi phí thực thi hợp lý.

## 2. Giới hạn độ dài biểu thức trước khi parse

### 2.1. Kiểm tra ở ranh giới đầu vào

Độ dài biểu thức nên được giới hạn ngay khi nhận dữ liệu, trước khi gọi parser. Ví dụ:

~~~java
private static final int MAX_EXPRESSION_LENGTH = 10_000;

static Expression parseUserExpression(
        String source,
        ExpressionParser parser) {

    if (source == null) {
        throw new IllegalArgumentException(
                "Expression must not be null"
        );
    }

    if (source.length() > MAX_EXPRESSION_LENGTH) {
        throw new IllegalArgumentException(
                "Expression is too long"
        );
    }

    if (source.isBlank()) {
        throw new IllegalArgumentException(
                "Expression must not be blank"
        );
    }

    return parser.parseExpression(source);
}
~~~

Giới hạn 10.000 ký tự trong ví dụ chỉ là một chính sách minh họa. Ứng dụng cần chọn con số theo chức năng, độ phức tạp biểu thức, tài nguyên và trải nghiệm người dùng. Không nên sao chép một ngưỡng mà chưa đo bằng dữ liệu thực tế.

Trong Java, **String.length()** đếm UTF-16 code unit, không phải số byte UTF-8 hay số ký tự hiển thị. Nếu giới hạn được đặt ở HTTP/API gateway theo byte, cần kiểm tra cả kích thước payload theo byte tại ranh giới truyền dữ liệu. Nếu giới hạn theo số ký tự người dùng nhìn thấy, cần thống nhất cách đếm Unicode với giao diện.

### 2.2. Không chỉ dựa vào giới hạn của parser

Một số phiên bản Spring Framework cung cấp cấu hình giới hạn độ dài biểu thức trong SpelParserConfiguration. Nếu phiên bản đang dùng có hỗ trợ, hãy cấu hình giới hạn phù hợp và kiểm tra hành vi thực tế của phiên bản đó.

Dù parser có giới hạn riêng, ứng dụng vẫn nên xác thực đầu vào ở tầng API hoặc service. Lý do:

- Có thể từ chối payload quá lớn trước khi tạo các object xử lý.
- Có thể trả thông báo lỗi nhất quán với hợp đồng API.
- Có thể áp dụng giới hạn khác nhau cho từng loại biểu thức.
- Có thể giới hạn cả dữ liệu đầu vào đi kèm, không chỉ chuỗi SpEL.
- Có thể ghi nhận số liệu và phát hiện nguồn gửi biểu thức bất thường.

Không nên tăng giới hạn parser chỉ để một biểu thức quá lớn có thể chạy. Hãy xem lại liệu biểu thức có đang chứa dữ liệu hoặc logic nên được chuyển sang Java hay không.

## 3. Giới hạn kích thước list, map và array

### 3.1. Biểu thức ngắn vẫn có thể tạo dữ liệu lớn

Ví dụ:

~~~java
new int[100000000]
~~~

Chuỗi này rất ngắn nhưng yêu cầu cấp phát một mảng có một trăm triệu phần tử. Tùy môi trường, nó có thể gây tiêu thụ bộ nhớ lớn hoặc làm ứng dụng thất bại vì không đủ heap.

Một biểu thức khác có thể tạo collection với nhiều phần tử literal hoặc lồng nhiều collection. Vì vậy, giới hạn độ dài chuỗi không đủ để giới hạn bộ nhớ và chi phí đánh giá.

### 3.2. Xác thực kích thước trước khi đánh giá

Nếu kích thước mảng hoặc số phần tử được lấy từ dữ liệu người dùng, hãy kiểm tra ở Java trước khi đưa vào context:

~~~java
private static final int MAX_ARRAY_SIZE = 256;

static int validateArraySize(Integer requestedSize) {
    if (requestedSize == null) {
        throw new IllegalArgumentException(
                "Array size is required"
        );
    }

    if (requestedSize < 0 || requestedSize > MAX_ARRAY_SIZE) {
        throw new IllegalArgumentException(
                "Array size is outside the allowed range"
        );
    }

    return requestedSize;
}
~~~

Sau khi xác thực, mới đặt giá trị vào context:

~~~java
int size = validateArraySize(requestedSize);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("size", size);
~~~

Nếu biểu thức được phép cấp phát array theo biến, kích thước phải được giới hạn trước khi gọi **getValue**. Không nên chỉ kiểm tra kích thước sau khi array đã được tạo vì lúc đó chi phí cấp phát đã xảy ra.

Với inline list hoặc map có phần tử được viết trực tiếp trong biểu thức, cần giới hạn độ phức tạp và số phần tử được phép. Với dữ liệu collection được truyền từ bên ngoài, kiểm tra số phần tử trước khi đặt vào context.

### 3.3. Giới hạn nhiều chiều và cấu trúc lồng nhau

Một mảng nhiều chiều có thể tiêu thụ bộ nhớ lớn hơn nhiều so với kích thước từng chiều nhìn riêng lẻ:

~~~java
new int[100][100][100]
~~~

Số phần tử tổng cộng là tích của các chiều. Nếu cho phép nhiều chiều, hãy kiểm tra:

- Số chiều tối đa.
- Kích thước tối đa của mỗi chiều.
- Tổng số phần tử sau khi nhân các chiều.
- Giới hạn bộ nhớ dự kiến.
- Kiểu phần tử và kích thước thực tế của object.

Khi tính tổng số phần tử, cần dùng kiểu số đủ rộng và kiểm tra tràn số trước khi cấp phát. Không nhân các giá trị int rồi giả định kết quả luôn chính xác.

Với list/map lồng nhau, cần giới hạn cả độ sâu và tổng số node, không chỉ số phần tử ở cấp ngoài cùng. Một collection có ít phần tử cấp một vẫn có thể chứa một cây dữ liệu rất lớn ở các cấp con.

### 3.4. Auto-grow của SpEL

SpelParserConfiguration có các tùy chọn điều khiển việc tự mở rộng tham chiếu null và collection khi truy cập index vượt giới hạn. Ví dụ cấu hình giới hạn auto-grow:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                false,
                false,
                256
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Ba tham số trong constructor ví dụ lần lượt tắt auto-grow null reference, tắt auto-grow collection và đặt giới hạn kích thước auto-grow tối đa.

Auto-grow có thể hữu ích khi ứng dụng chủ động muốn SpEL mở rộng cấu trúc dữ liệu trong một số thao tác ghi. Tuy nhiên, với biểu thức không tin cậy hoặc chỉ cần đọc dữ liệu, nên tắt tính năng này để tránh việc truy cập ngoài phạm vi vô tình làm collection tăng kích thước.

**maximumAutoGrowSize** chỉ giới hạn hành vi auto-grow tương ứng. Không được coi nó là giới hạn chung cho mọi array construction, inline list, inline map hoặc collection được truyền sẵn vào context. Những nguồn dữ liệu đó cần được kiểm tra riêng.

## 4. Giới hạn kích thước dữ liệu đầu vào

### 4.1. Giới hạn chuỗi

Chuỗi lớn có thể làm tăng chi phí lưu trữ, so sánh, chuẩn hóa, parse và log. Hãy đặt giới hạn theo từng trường:

~~~java
private static final int MAX_NAME_LENGTH = 200;
private static final int MAX_TEXT_LENGTH = 4_000;

static String validateText(String value, int maxLength) {
    if (value == null) {
        return null;
    }

    if (value.length() > maxLength) {
        throw new IllegalArgumentException(
                "Text exceeds the allowed length"
        );
    }

    return value;
}
~~~

Không nên dùng cùng một giới hạn cho mọi trường. Tên hiển thị, mã định danh, ghi chú và nội dung tìm kiếm có nhu cầu khác nhau.

Nếu cần giới hạn theo byte để phù hợp với storage hoặc giao thức, hãy đo kích thước sau khi encode bằng charset được sử dụng, thường là UTF-8.

### 4.2. Giới hạn số phần tử collection

Ví dụ kiểm tra list trước khi đưa vào context:

~~~java
private static final int MAX_ITEMS = 500;

static <T> List<T> validateItems(List<T> items) {
    if (items == null) {
        return List.of();
    }

    if (items.size() > MAX_ITEMS) {
        throw new IllegalArgumentException(
                "Too many items"
        );
    }

    return List.copyOf(items);
}
~~~

Ví dụ này trả về list bất biến và không chấp nhận phần tử null vì **List.copyOf** không cho phép null. Nếu null là dữ liệu hợp lệ trong domain, hãy dùng cách copy khác và xác định chính sách null rõ ràng.

Với Map, cần giới hạn số entry, độ dài key, kích thước value và kiểu dữ liệu được phép. Đừng chỉ kiểm tra map có bao nhiêu entry nếu mỗi value lại là một list hoặc map lồng nhau.

### 4.3. Kiểm tra kiểu dữ liệu

Không nên đưa object bất kỳ từ request vào context. Hãy chuyển dữ liệu sang các kiểu đơn giản hoặc DTO chỉ chứa trường cần thiết:

~~~java
public record ExpressionInput(
        String customerCode,
        int quantity,
        List<String> tags
) {
}
~~~

Sau khi validate, có thể tạo context chỉ chứa các giá trị cần thiết:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customerCode", input.customerCode());
context.setVariable("quantity", input.quantity());
context.setVariable("tags", List.copyOf(input.tags()));
~~~

Cách này giới hạn những gì biểu thức có thể quan sát và giảm nguy cơ vô tình cấp quyền truy cập tới service, entity hoặc object nội bộ.

## 5. Không ghép dữ liệu người dùng trực tiếp vào chuỗi SpEL

### 5.1. Rủi ro biểu thức bị thay đổi

Không nên tạo biểu thức bằng cách nối trực tiếp dữ liệu người dùng:

~~~java
String source =
        "customer.name == '" + userInput + "'";

Expression expression =
        parser.parseExpression(source);
~~~

Nếu userInput chứa dấu nháy hoặc cú pháp SpEL, cấu trúc biểu thức có thể thay đổi ngoài dự kiến. Đây là lỗi trộn dữ liệu với mã biểu thức.

### 5.2. Dùng biến trong EvaluationContext

Hãy giữ biểu thức cố định và truyền dữ liệu qua biến:

~~~java
String source = "#customerName == #expectedName";

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customerName", customerName);
context.setVariable("expectedName", userInput);

Boolean matches = parser
        .parseExpression(source)
        .getValue(context, Boolean.class);
~~~

Giá trị người dùng lúc này là dữ liệu được truyền vào context, không được phân tích lại như cú pháp SpEL.

Nếu cần truyền list hoặc map, hãy đặt collection đã được xác thực vào biến:

~~~java
context.setVariable("allowedCodes", validatedCodes);
context.setVariable("settings", validatedSettings);
~~~

Sau đó biểu thức chỉ truy cập những giá trị đã được cấp:

~~~java
#allowedCodes.contains(#customerCode)
~~~

Việc dùng biến không tự động làm biểu thức an toàn nếu người dùng vẫn được phép kiểm soát toàn bộ chuỗi expression. Nó chỉ ngăn việc ghép giá trị dữ liệu thành mã. Quyền biểu thức vẫn cần được giới hạn riêng.

## 6. Giới hạn quyền của EvaluationContext

### 6.1. Không đưa toàn bộ ứng dụng vào context

StandardEvaluationContext có thể hỗ trợ truy cập property, method, constructor, type và bean tùy cấu hình. Nếu root object là một service lớn hoặc một entity có nhiều quan hệ, biểu thức có thể tiếp cận nhiều dữ liệu hơn nhu cầu.

Nên cung cấp một object nhỏ, có phạm vi rõ ràng:

~~~java
public record CustomerExpressionView(
        String code,
        String displayName,
        boolean active
) {
}
~~~

Tạo context từ view đã được chuẩn bị:

~~~java
CustomerExpressionView view =
        new CustomerExpressionView(
                customer.getCode(),
                customer.getDisplayName(),
                customer.isActive()
        );

StandardEvaluationContext context =
        new StandardEvaluationContext(view);
~~~

Biểu thức chỉ có thể truy cập các property mà view cung cấp và các khả năng khác được context cho phép.

### 6.2. Cân nhắc SimpleEvaluationContext

Khi chỉ cần một tập con tính năng SpEL, có thể dùng SimpleEvaluationContext. Context này được thiết kế để giới hạn quyền so với StandardEvaluationContext.

Ví dụ tạo context chỉ đọc:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

SimpleEvaluationContext không cung cấp đầy đủ các khả năng như tham chiếu kiểu, constructor và bean reference. Việc hỗ trợ method invocation còn phụ thuộc cấu hình builder và resolver được cho phép.

Hãy chọn cấu hình cụ thể theo biểu thức thực sự cần chạy. Không nên bật method resolver hoặc quyền truy cập bổ sung chỉ để làm một biểu thức tùy ý hoạt động.

SimpleEvaluationContext cũng không phải bộ giới hạn tài nguyên tổng quát. Ứng dụng vẫn cần giới hạn độ dài biểu thức, dữ liệu và chi phí đánh giá.

### 6.3. Hạn chế method có tác dụng phụ

Nếu biểu thức có thể gọi method, chỉ cung cấp các method cần thiết. Tránh đưa vào context các method có thể:

- Gửi request mạng hoặc truy cập hệ thống tệp.
- Ghi database hoặc thay đổi trạng thái nghiệp vụ.
- Khởi chạy tác vụ nền.
- Truy cập dữ liệu nhạy cảm.
- Tạo collection hoặc array lớn.
- Thực hiện vòng lặp hoặc truy vấn không có giới hạn.

Method được gọi từ SpEL nên có tên và hợp đồng rõ ràng, ưu tiên không có tác dụng phụ. Việc chuyển đổi kiểu thành công hoặc method được phân giải thành công không phải là kiểm tra quyền.

## 7. Giới hạn chi phí đánh giá

### 7.1. Hạn chế biểu thức phức tạp

Biểu thức có thể chứa nhiều tầng lồng nhau, nhiều phép toán, nhiều lời gọi method hoặc truy cập collection. Độ dài không phản ánh đầy đủ chi phí thực thi.

Hãy đặt các giới hạn phù hợp cho:

- Độ dài chuỗi biểu thức.
- Số lượng và độ sâu cấu trúc lồng nhau.
- Kích thước array/list/map.
- Số phần tử được duyệt.
- Số lần gọi method.
- Thời gian và tài nguyên mà các method được phép sử dụng.

SpEL không phải môi trường sandbox để chạy mã tùy ý. Không nên cho phép người dùng không tin cậy tạo biểu thức có thể gọi method không giới hạn rồi kỳ vọng parser tự ngăn mọi trường hợp tốn tài nguyên.

### 7.2. Không dựa vào timeout đơn lẻ

Một timeout ở tầng gọi không tự động dừng được method Java đang chạy. Nếu method có vòng lặp không kiểm tra interrupt hoặc đang thực hiện I/O không giới hạn, việc hết thời gian chờ không bảo đảm công việc bên dưới đã dừng.

Cách tốt hơn là:

- Không cho phép gọi method tùy ý.
- Giới hạn dữ liệu và số phần tử trước khi đánh giá.
- Dùng API có giới hạn thời gian cho các thao tác I/O.
- Thiết kế method có thể kết thúc nhanh và có kiểm soát.
- Với trường hợp phải thực thi biểu thức không tin cậy có rủi ro cao, cân nhắc cô lập ở tiến trình hoặc môi trường riêng với giới hạn CPU, bộ nhớ và thời gian.

Không dùng thread interruption như một cơ chế cưỡng chế an toàn cho mã tùy ý.

### 7.3. Compiler mode không phải ranh giới bảo mật

SpEL có chế độ biên dịch để cải thiện hiệu năng trong một số trường hợp. Compiler mode là quyết định về thực thi và hiệu năng; nó không thay thế việc kiểm soát type, method, dữ liệu hay quyền của EvaluationContext.

Không bật compiler mode chỉ với mục đích làm cho biểu thức không tin cậy an toàn hơn. Hãy xác định cấu hình dựa trên cách sử dụng, kiểm thử và phiên bản Spring thực tế.

## 8. Kiểm tra và xử lý lỗi đầu vào

Cần phân biệt các lỗi xảy ra ở từng bước:

| Giai đoạn | Ví dụ lỗi | Cách xử lý |
|---|---|---|
| Nhận request | Payload quá lớn | Từ chối trước khi parse |
| Validate dữ liệu | Collection quá nhiều phần tử | Trả lỗi validation |
| Parse | Cú pháp SpEL không hợp lệ | Bắt ParseException |
| Phân giải quyền | Type hoặc method không được phép | Từ chối theo chính sách context |
| Evaluate | Property/method không hợp lệ | Xử lý EvaluationException |
| Cấp phát/collection | Kích thước vượt giới hạn hoặc hết bộ nhớ | Ngăn từ đầu bằng giới hạn tài nguyên |
| Sử dụng kết quả | Kết quả có kiểu hoặc kích thước ngoài dự kiến | Kiểm tra trước khi đưa vào nghiệp vụ tiếp theo |

Ví dụ validate đầu vào trước khi parse:

~~~java
public Object evaluate(
        String source,
        ExpressionInput input) {

    if (source == null || source.length() > 10_000) {
        throw new IllegalArgumentException(
                "Expression is missing or too long"
        );
    }

    if (input.tags() != null && input.tags().size() > 500) {
        throw new IllegalArgumentException(
                "Too many tags"
        );
    }

    ExpressionParser parser =
            new SpelExpressionParser(
                    new SpelParserConfiguration(false, false, 256)
            );

    Expression expression = parser.parseExpression(source);

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("customerCode", input.customerCode());
    context.setVariable("quantity", input.quantity());
    context.setVariable(
            "tags",
            input.tags() == null ? List.of() : List.copyOf(input.tags())
    );

    return expression.getValue(context);
}
~~~

Đây là ví dụ minh họa các điểm kiểm tra, không phải một sandbox đầy đủ cho biểu thức không tin cậy. Nếu người dùng được phép tự viết source, cần giới hạn cú pháp và quyền truy cập theo allowlist trước khi đánh giá.

Thông báo trả về cho người dùng nên nêu trường hoặc quy tắc bị vi phạm mà không tiết lộ stack trace, tên class nội bộ, đường dẫn hoặc dữ liệu nhạy cảm.

## 9. Checklist giới hạn đầu vào

Trước khi đưa SpEL vào một API hoặc tính năng cho phép người dùng nhập biểu thức, hãy kiểm tra:

- Độ dài biểu thức được giới hạn trước khi parse.
- Payload được giới hạn theo byte tại tầng giao tiếp nếu cần.
- Chuỗi, số, list, map và array đều có giới hạn riêng.
- Collection lồng nhau có giới hạn độ sâu và tổng số phần tử.
- Kích thước array được xác thực trước khi đánh giá.
- Auto-grow được tắt nếu không cần; nếu bật thì có giới hạn cụ thể.
- Root object chỉ chứa dữ liệu cần thiết.
- Biến context chứa dữ liệu đã xác thực và đúng kiểu.
- Dữ liệu người dùng được truyền qua biến, không nối vào chuỗi SpEL.
- Method, type, constructor và bean access được giới hạn theo nhu cầu.
- Method được phép gọi có chi phí và tác dụng phụ được kiểm soát.
- Parse error và evaluate error được xử lý riêng.
- Kết quả được kiểm tra kiểu và kích thước trước khi sử dụng.
- Có kiểm thử với đầu vào biên, collection lớn và dữ liệu sai định dạng.

## 10. Tổng kết

Khi biểu thức hoặc dữ liệu do người dùng cung cấp, cần quản lý nhiều giới hạn độc lập:

- Giới hạn độ dài biểu thức trước khi parse.
- Giới hạn kích thước chuỗi, collection, số phần tử, độ sâu lồng nhau và kích thước array.
- Tắt auto-grow nếu không cần và hiểu rằng giới hạn auto-grow không giới hạn mọi cách tạo collection.
- Truyền dữ liệu qua biến EvaluationContext thay vì nối trực tiếp vào chuỗi biểu thức.
- Chỉ cung cấp root object và method cần thiết; cân nhắc SimpleEvaluationContext cho tập tính năng giới hạn.
- Không coi parser, compiler mode hoặc timeout đơn lẻ là sandbox.
- Kiểm tra kết quả và xử lý lỗi tại đúng giai đoạn.

SpEL phù hợp để diễn đạt quy tắc có phạm vi rõ ràng. Khi người dùng được phép điều khiển biểu thức, ứng dụng phải kiểm soát cả dữ liệu, cú pháp, quyền truy cập và chi phí thực thi trước khi sử dụng kết quả trong nghiệp vụ.