# Thông tin vị trí trong expression bị lỗi

## 1. Vì sao cần biết vị trí lỗi?

Khi SpEL không thể phân tích hoặc đánh giá một biểu thức, thông báo lỗi thường cho biết loại vấn đề. Vị trí lỗi giúp xác định phần source cần kiểm tra.

Ví dụ:

    customer.address.city
    orders[10].total
    T(java.lang.Math).max(, 5)
    #normalizeCode(#region

Các lỗi có thể xuất phát từ cú pháp sai, property không tồn tại, object trung gian null, method không tìm thấy, index vượt giới hạn hoặc chuyển đổi kiểu thất bại.

Spring Expression Language cung cấp exception chứa thông tin như:

- Chuỗi expression liên quan đến lỗi, nếu exception lưu thông tin đó.
- Vị trí xảy ra lỗi trong expression.
- Mã thông báo lỗi và các giá trị bổ sung đối với exception SpEL chuyên biệt.
- Nguyên nhân gốc nếu lỗi được bọc từ một exception khác.

Thông tin này hỗ trợ log, hiển thị lỗi cấu hình và debug. Tuy nhiên, vị trí là một điểm đánh dấu do parser hoặc node evaluation cung cấp; nó không phải lúc nào cũng là một khoảng source chính xác bao trọn toàn bộ lỗi.

## 2. Hai giai đoạn có thể phát sinh lỗi

Quá trình dùng SpEL thường có hai giai đoạn riêng:

1. Parsing: ExpressionParser phân tích source và tạo Expression.
2. Evaluation: Expression đánh giá trên EvaluationContext và root object.

Hai giai đoạn có loại exception khác nhau:

| Giai đoạn | API | Exception cơ bản | Ví dụ lỗi |
| --- | --- | --- | --- |
| Parsing | parser.parseExpression(...) | ParseException | Thiếu dấu ngoặc, token không hợp lệ, chuỗi chưa đóng |
| Evaluation | expression.getValue(...) | EvaluationException | Property không đọc được, method không tìm thấy, null reference, conversion error |

Ví dụ:

    ExpressionParser parser =
        new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("customer.address.city");

    Object city = expression.getValue(context);

Nếu source sai cú pháp, lỗi xảy ra ở parseExpression và không có Expression hợp lệ để đánh giá.

Nếu source hợp lệ nhưng customer.address là null, parsing vẫn thành công. Lỗi chỉ xuất hiện khi getValue truy cập object tại runtime.

Phân biệt hai giai đoạn giúp chọn đúng exception để xử lý và tránh tìm lỗi runtime trong parser khi source đã parse thành công.

## 3. ExpressionException và getPosition()

ParseException và EvaluationException đều kế thừa ExpressionException.

Các API quan trọng:

| API | Ý nghĩa |
| --- | --- |
| getExpressionString() | Source expression được gắn với exception; có thể null |
| getPosition() | Vị trí trong expression nơi vấn đề xảy ra |
| getMessage() | Thông báo chi tiết; tương đương toDetailedString() |
| getSimpleMessage() | Thông báo ngắn, không kèm source expression |
| toDetailedString() | Mô tả chi tiết gồm source và vị trí nếu có |

Ví dụ:

    try {
        parser.parseExpression("customer.address.city");
    }
    catch (ExpressionException ex) {
        String source = ex.getExpressionString();
        int position = ex.getPosition();

        System.out.println(ex.getSimpleMessage());
        System.out.println(ex.toDetailedString());
    }

getPosition() trả về một vị trí dạng số trong source expression. Vị trí này là offset theo chuỗi Java, không phải trực tiếp là số dòng và số cột.

Trong implementation parser, vị trí được tính theo chỉ số ký tự của String. Khi hiển thị cho người dùng, ứng dụng có thể chuyển offset đó thành dòng/cột. Cần nhớ Java String dùng UTF-16 code units; ký tự Unicode ngoài Basic Multilingual Plane có thể chiếm hai vị trí char.

Không phải exception nào cũng có source hoặc vị trí hữu ích. ExpressionException dùng -1 để biểu thị vị trí không xác định trong những trường hợp có source nhưng không biết vị trí. Một số exception được tạo mà không gắn expression string. Hãy kiểm tra cả source và vị trí trước khi tạo marker.

## 4. SpelParseException: lỗi trong lúc parsing

SpelParseException là exception SpEL chuyên biệt, kế thừa ParseException.

Nó lưu:

- Mã SpelMessage mô tả loại lỗi.
- Các inserts chứa giá trị bổ sung cho thông báo.
- Vị trí và source expression thông qua ExpressionException.

Ví dụ:

    try {
        parser.parseExpression("T(java.lang.Math).max(, 5)");
    }
    catch (SpelParseException ex) {
        System.out.println(ex.getMessageCode());
        System.out.println(Arrays.toString(ex.getInserts()));
        System.out.println(ex.getPosition());
        System.out.println(ex.getExpressionString());
    }

Mã lỗi có thể cho biết parser gặp token không mong đợi, thiếu ký tự, thiếu đối số hoặc chuỗi literal chưa kết thúc.

Nếu dùng một ParserContext template, một số lỗi cấu trúc delimiter được tạo dưới dạng ParseException tổng quát thay vì SpelParseException. Vì vậy, khi xử lý lỗi parsing ở mức API, hãy bắt ParseException; chỉ đọc getMessageCode() và getInserts() khi exception thực tế là SpelParseException.

## 5. SpelEvaluationException: lỗi trong lúc evaluation

SpelEvaluationException là exception SpEL chuyên biệt, kế thừa EvaluationException.

Nó cũng lưu mã SpelMessage và các inserts giúp nhận diện lỗi. Vị trí thường gắn với node trong expression đang thực hiện thao tác thất bại.

Ví dụ:

    try {
        Expression expression =
            parser.parseExpression("customer.address.city");

        expression.getValue(context);
    }
    catch (SpelEvaluationException ex) {
        System.out.println(ex.getMessageCode());
        System.out.println(Arrays.toString(ex.getInserts()));
        System.out.println(ex.getPosition());
        System.out.println(ex.getCause());
    }

Một số tình huống evaluation có thể phát sinh:

- Property không tồn tại hoặc không đọc được.
- Property được truy cập trên object null.
- Method không tìm thấy hoặc không thể gọi.
- Function chưa được đăng ký.
- Index nằm ngoài giới hạn.
- Không chuyển đổi được kiểu dữ liệu.
- Bean reference không có BeanResolver hoặc bean lookup thất bại.
- Constructor không phù hợp với các đối số.

Không phải mọi EvaluationException đều là SpelEvaluationException. Nếu dùng custom resolver hoặc code tích hợp riêng, ứng dụng có thể nhận EvaluationException tổng quát. Khi đó, hãy dùng API của lớp cha và kiểm tra cause.

## 6. getMessageCode() và getInserts()

SpelParseException và SpelEvaluationException không chỉ giữ một chuỗi thông báo cố định. Chúng lưu mã SpelMessage và các giá trị được chèn vào thông báo.

Ví dụ một số mã:

| Mã SpelMessage | Ý nghĩa |
| --- | --- |
| TYPE_NOT_FOUND | Không tìm thấy kiểu được tham chiếu |
| PROPERTY_OR_FIELD_NOT_READABLE | Property hoặc field không đọc được |
| METHOD_NOT_FOUND | Không tìm thấy method phù hợp |
| FUNCTION_NOT_DEFINED | Function chưa được đăng ký |
| CANNOT_INDEX_INTO_NULL_VALUE | Không thể indexing trên null |
| COLLECTION_INDEX_OUT_OF_BOUNDS | Index collection vượt giới hạn |
| TYPE_CONVERSION_ERROR | Chuyển đổi kiểu thất bại |
| NO_BEAN_RESOLVER_REGISTERED | Context chưa có BeanResolver |
| CONSTRUCTOR_NOT_FOUND | Không tìm thấy constructor phù hợp |

Ví dụ, khi property không đọc được, inserts có thể chứa tên property và kiểu object. Với lỗi index, inserts có thể chứa kích thước collection và index được yêu cầu.

Dùng mã lỗi để phân loại và xử lý theo chương trình:

    if (ex.getMessageCode() ==
            SpelMessage.PROPERTY_OR_FIELD_NOT_READABLE) {
        // Xử lý lỗi property không đọc được
    }

Không nên phân loại lỗi bằng cách so sánh nguyên văn getMessage(). Nội dung thông báo có thể thay đổi theo phiên bản hoặc locale, trong khi SpelMessage cung cấp định danh rõ ràng hơn.

getInserts() là dữ liệu bổ sung để giải thích lỗi. Không mặc định rằng mọi mã lỗi có cùng số lượng hoặc cùng kiểu insert.

## 7. getMessage(), getSimpleMessage() và toDetailedString()

Ba API này phục vụ những mục đích khác nhau.

    ex.getMessage()
    ex.getSimpleMessage()
    ex.toDetailedString()

getMessage() trả về dạng chi tiết, thường gồm expression, vị trí và thông báo.

getSimpleMessage() chỉ trả về phần mô tả lỗi, không kèm source expression.

toDetailedString() trả về mô tả đầy đủ hơn, gồm source expression và vị trí khi exception có lưu chúng.

Ví dụ dạng chi tiết có thể trông như sau:

    Expression [customer.address.city] @18: ...

Phần @18 là vị trí được exception lưu lại. Phần thông báo sau đó mô tả nguyên nhân cụ thể.

Khi hiển thị cho lập trình viên, toDetailedString() thường hữu ích. Khi log trong hệ thống production, cần cân nhắc source expression có chứa dữ liệu nhạy cảm hay không. getSimpleMessage() giúp tránh tự động đưa toàn bộ expression vào log, nhưng các inserts và cause cũng cần được xem xét.

## 8. Bắt lỗi ở đúng giai đoạn

Một cách tổ chức rõ ràng là tách parse và evaluation thành hai khối xử lý:

    Expression expression;

    try {
        expression = parser.parseExpression(source);
    }
    catch (ParseException ex) {
        reportParseError(ex, source);
        return;
    }

    try {
        Object result = expression.getValue(context);
        useResult(result);
    }
    catch (EvaluationException ex) {
        reportEvaluationError(ex, source);
    }

Có thể xử lý riêng exception SpEL cụ thể:

    private void reportParseError(
            ParseException ex,
            String originalSource) {

        String expressionSource =
            ex.getExpressionString() != null
                ? ex.getExpressionString()
                : originalSource;

        int position = ex.getPosition();

        if (ex instanceof SpelParseException spel) {
            SpelMessage code = spel.getMessageCode();
            Object[] inserts = spel.getInserts();

            logParseDiagnostic(
                code,
                inserts,
                expressionSource,
                position
            );
        }
        else {
            logGenericParseDiagnostic(
                expressionSource,
                position,
                ex.getSimpleMessage()
            );
        }
    }

Với evaluation, dùng cách tương tự và kiểm tra SpelEvaluationException trước khi truy cập message code và inserts.

Giữ lại source mà ứng dụng đã gửi vào parser. Điều này đặc biệt hữu ích khi getExpressionString() trả về null hoặc exception chỉ gắn với một phần của template.

## 9. Tạo đoạn source có dấu chỉ vị trí lỗi

getPosition() chỉ trả về một offset. Ứng dụng có thể trích một đoạn ngắn quanh vị trí đó và thêm dấu ^ để người đọc tìm nhanh.

Ví dụ helper:

    static String createErrorExcerpt(
            String source,
            int position) {

        if (source == null
                || position < 0
                || position > source.length()) {
            return "Không có vị trí source hợp lệ";
        }

        int start = Math.max(0, position - 20);
        int end = Math.min(source.length(), position + 20);

        String excerpt = source.substring(start, end);

        StringBuilder marker = new StringBuilder();

        for (int i = start; i < position; i++) {
            marker.append(source.charAt(i) == '\t' ? '\t' : ' ');
        }

        marker.append('^');

        return excerpt
            + System.lineSeparator()
            + marker;
    }

Ví dụ kết quả minh họa:

    customer.address.city
                      ^

Đây là đoạn hiển thị hỗ trợ debug, không phải source range chính thức do SpEL trả về. Một position có thể chỉ đánh dấu điểm bắt đầu node hoặc nơi parser phát hiện lỗi; nó không xác định toàn bộ token hay khoảng văn bản cần thay thế.

Khi hiển thị dấu caret trong giao diện, hãy tính đến tab, ký tự kết hợp Unicode và ký tự supplementary. Chúng có thể chiếm độ rộng hiển thị khác số lượng UTF-16 code units.

## 10. Chuyển offset thành dòng và cột

Expression có thể được viết trên nhiều dòng. getPosition() vẫn là offset tính từ đầu source, không phải số dòng.

Có thể tính dòng và cột bằng cách duyệt source từ đầu đến offset:

    static int[] toLineAndColumn(
            String source,
            int position) {

        int line = 1;
        int column = 1;
        int limit = Math.min(position, source.length());

        for (int i = 0; i < limit; i++) {
            char ch = source.charAt(i);

            if (ch == '\n') {
                line++;
                column = 1;
            }
            else if (ch != '\r') {
                column++;
            }
        }

        return new int[] {line, column};
    }

Ví dụ:

    #customer.active and
    #customer.address.city

Nếu vị trí lỗi nằm trên dòng thứ hai, helper trả về dòng và cột tương ứng với offset trong toàn bộ source.

Đây là quy ước hiển thị của ứng dụng. Với tab hoặc Unicode nhiều code units, cột hiển thị trên editor có thể khác cột đếm bằng Java char. Nếu cần marker khớp chính xác editor, hãy dùng cùng quy ước offset và độ rộng ký tự mà editor sử dụng.

Không thay đổi hoặc normalize source trước khi tính vị trí. Việc xóa khoảng trắng, đổi line ending hoặc thay thế ký tự trước khi parse sẽ làm offset không còn khớp với source gốc.

## 11. Vị trí lỗi trong template expression

SpEL hỗ trợ template bằng ParserContext, ví dụ TemplateParserContext mặc định nhận diện các block #{...} bên trong văn bản.

Ví dụ:

    Expression template = parser.parseExpression(
        "Xin chào #{#customer.name}!",
        new TemplateParserContext()
    );

Có hai nhóm lỗi cần phân biệt:

- Lỗi cấu trúc template, chẳng hạn thiếu dấu đóng delimiter hoặc ngoặc không khớp trong template. Template parser có thể báo vị trí trên toàn bộ chuỗi template.
- Lỗi cú pháp bên trong block SpEL. Template parser trích nội dung block rồi chuyển phần expression đó cho SpEL parser; exception parsing có thể lưu source và position tương đối với phần expression bên trong.

Template parser cũng loại bỏ delimiter và trim phần expression trước khi parse. Vì vậy, không nên cộng position của exception vào source template một cách máy móc.

Nếu cần highlight trên template gốc, hãy giữ metadata của từng block: vị trí bắt đầu delimiter, độ dài prefix, khoảng trắng bị trim và source expression thực tế được parse. Từ đó mới ánh xạ offset của block về offset tuyệt đối trong template.

Với nhiều block, cần biết exception phát sinh từ block nào. Nếu không giữ mapping này, hãy hiển thị source fragment mà exception cung cấp thay vì đánh dấu sai vị trí trên toàn bộ template.

## 12. Position không phải lúc nào cũng có

Một số exception được tạo bởi custom integration hoặc code bên ngoài parser có thể không gắn source string hay position chính xác.

Trước khi tạo snippet, hãy kiểm tra:

    String source = ex.getExpressionString();
    int position = ex.getPosition();

Nếu source null, dùng source gốc mà ứng dụng giữ lại nếu chắc chắn đó là cùng expression đang được đánh giá.

Nếu position nhỏ hơn 0 hoặc vượt quá source.length(), không tạo substring bằng vị trí đó.

Nếu exception là một EvaluationException tổng quát, không giả định nó có getMessageCode() hoặc getInserts(). Các API này chỉ có trên các exception SpEL chuyên biệt.

Khi vị trí không có, hãy dựa vào simple message, cause, stack trace đã được làm sạch và thông tin rule ID để tiếp tục điều tra.

## 13. Cause và lỗi từ method được gọi

Một expression có thể gọi method Java:

    #customerService.calculateDiscount(#order)

Nếu method ném exception, lỗi có thể được bọc trong exception của quá trình invocation. Vị trí SpEL giúp xác định node method call, còn cause cho biết lỗi thực sự bên trong method.

Ví dụ:

    catch (EvaluationException ex) {
        Throwable cause = ex.getCause();

        if (cause != null) {
            log.error(
                "Evaluation failed: {}",
                ex.getSimpleMessage(),
                cause
            );
        }
    }

Không nên chỉ nhìn position rồi kết luận parser sai. Nếu lỗi xảy ra trong method, hãy kiểm tra cause, tham số đầu vào và logic Java được gọi.

Tương tự, lỗi từ PropertyAccessor, MethodResolver, BeanResolver hoặc TypeConverter có thể được bọc trong SpEL exception. Mã lỗi và cause giúp phân biệt lỗi truy cập expression với lỗi bên trong thành phần tích hợp.

## 14. Kiểm thử vị trí và thông tin lỗi

Khi viết test cho expression, nên kiểm tra mã lỗi và vị trí nếu vị trí là một phần quan trọng của trải nghiệm debug.

Ví dụ:

    assertThatThrownBy(
        () -> parser.parseExpression("T(java.lang.Math).max(, 5)")
    )
    .isInstanceOf(SpelParseException.class)
    .satisfies(error -> {
        SpelParseException ex =
            (SpelParseException) error;

        assertThat(ex.getMessageCode())
            .isEqualTo(SpelMessage.RUN_OUT_OF_ARGUMENTS);

        assertThat(ex.getPosition())
            .isGreaterThanOrEqualTo(0);
    });

Đoạn test minh họa cách kiểm tra exception type, mã lỗi và việc position có giá trị. Khi cần xác nhận chính xác một vị trí, hãy viết assertion theo source và phiên bản Spring mà dự án đang dùng.

Không nên kiểm thử bằng cách so sánh toàn bộ getMessage() nếu nội dung thông báo không phải hợp đồng ổn định của ứng dụng. Ưu tiên exception type, SpelMessage code, inserts cần thiết và position.

Với custom PropertyAccessor hoặc MethodResolver, hãy kiểm tra cả trường hợp resolver thành công, resolver từ chối target và resolver ném lỗi. Vị trí trong custom exception có thể khác nếu implementation không cung cấp offset.

## 15. Log lỗi mà không làm lộ dữ liệu

Expression có thể chứa tên biến, dữ liệu literal hoặc giá trị do người dùng nhập. Ghi toàn bộ source và message chi tiết vào log có thể làm lộ thông tin không nên lưu.

Một log hữu ích thường gồm:

- Rule ID hoặc expression ID.
- Phiên bản rule.
- Giai đoạn parse hay evaluation.
- Exception class và SpelMessage code nếu có.
- Position nếu hợp lệ.
- Simple message đã được làm sạch.
- Cause class hoặc mã lỗi nội bộ.
- Correlation ID để truy vết.

Không log toàn bộ EvaluationContext hoặc object graph chỉ để tìm vị trí lỗi. Nếu cần lưu source expression để điều tra, hãy xác định rõ quyền truy cập, thời gian lưu và quy tắc redact dữ liệu nhạy cảm.

Với expression do người dùng cung cấp, tránh hiển thị nguyên văn nội dung cho người dùng khác hoặc đưa vào hệ thống log có phạm vi truy cập rộng.

## 16. Lỗi thường gặp khi đọc position

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| getPosition() luôn là số dòng | Đây là offset trong expression string |
| Position luôn tồn tại | Có exception không lưu source hoặc không biết vị trí |
| Mọi lỗi đều là SpelParseException | Template parser và tích hợp khác có thể ném ParseException tổng quát |
| Mọi lỗi evaluation đều là SpelEvaluationException | Có thể nhận EvaluationException hoặc exception invocation khác |
| Position là toàn bộ vùng source sai | API chỉ cung cấp một vị trí, không phải start/end range |
| getMessage() chỉ là thông báo ngắn | Nó thường chứa source và position qua toDetailedString() |
| getSimpleMessage() có đầy đủ source | Nó loại bỏ expression string và vị trí |
| Có thể so sánh message text để phân loại | Dùng SpelMessage code khi exception hỗ trợ |
| Template block position luôn là offset tuyệt đối của template | Expression block có thể được parse như source fragment riêng |
| Parse thành công nghĩa là evaluation chắc chắn thành công | Lỗi runtime chỉ xuất hiện khi getValue() chạy |

## 17. Quy trình debug đề xuất

Khi expression lỗi, thực hiện theo thứ tự:

1. Xác định lỗi xảy ra ở parseExpression hay getValue.
2. Bắt ParseException hoặc EvaluationException tương ứng.
3. Lấy exception type, getSimpleMessage() và cause.
4. Nếu là SpelParseException hoặc SpelEvaluationException, đọc getMessageCode() và getInserts().
5. Lấy getExpressionString() và getPosition(); dùng source gốc làm fallback khi cần.
6. Kiểm tra position hợp lệ trước khi trích snippet.
7. Với expression nhiều dòng, chuyển offset thành line/column theo quy ước hiển thị của ứng dụng.
8. Nếu dùng template, xác định lỗi thuộc cấu trúc template hay expression block.
9. Kiểm tra root object, variable, property accessor, method resolver hoặc converter nếu lỗi xảy ra khi evaluation.
10. Làm sạch source và inserts trước khi ghi log hoặc hiển thị.

Quy trình này tách lỗi cú pháp, lỗi runtime và lỗi từ các thành phần tích hợp, giúp tìm nguyên nhân nhanh hơn.

## 18. Những điểm cần nhớ

- parseExpression() có thể ném ParseException; getValue() có thể ném EvaluationException.
- SpelParseException và SpelEvaluationException là các exception SpEL chuyên biệt.
- ExpressionException cung cấp getExpressionString(), getPosition(), getSimpleMessage() và toDetailedString().
- getPosition() là offset trong expression string, không phải trực tiếp là dòng/cột.
- Position có thể không xác định; kiểm tra source và giới hạn offset trước khi tạo snippet.
- SpelParseException và SpelEvaluationException cung cấp getMessageCode() và getInserts().
- Dùng SpelMessage code để phân loại thay vì so sánh nguyên văn thông báo.
- getMessage() thường chứa source và vị trí; getSimpleMessage() không chứa source.
- Cause giúp tìm lỗi bên trong method, accessor, resolver hoặc converter.
- Template có thể tạo exception trên toàn bộ template hoặc trên expression fragment bên trong block.
- Position chỉ là một điểm, không phải source range hoàn chỉnh.
- Không log source, inserts hoặc context có dữ liệu nhạy cảm nếu chưa redact.
- Kiểm thử exception type, message code và position theo phiên bản Spring của dự án.

Khi xử lý lỗi SpEL, hãy phân biệt parsing với evaluation, lấy position từ exception và đối chiếu với đúng source đã parse. Dùng message code, inserts và cause để hiểu loại lỗi; chỉ tạo marker khi source và offset hợp lệ. Cách này giúp thông tin lỗi hữu ích mà không đưa ra vị trí sai hoặc làm lộ dữ liệu trong expression.

## Tài liệu tham khảo

- Spring Framework Reference — Evaluation and Exceptions: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Javadoc — ExpressionException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ExpressionException.html
- Spring Framework Javadoc — ParseException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParseException.html
- Spring Framework Javadoc — SpelParseException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParseException.html
- Spring Framework Javadoc — SpelEvaluationException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelEvaluationException.html
- Spring Framework Source — ExpressionException: https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/ExpressionException.java
- Spring Framework Source — TemplateAwareExpressionParser: https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/common/TemplateAwareExpressionParser.java
