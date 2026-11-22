# Lỗi parse và vị trí lỗi trong biểu thức

Khi làm việc với Spring Expression Language (SpEL), parser biến chuỗi biểu thức thành một đối tượng **Expression** để ứng dụng có thể đánh giá sau đó. Nếu chuỗi không đúng cú pháp SpEL, lỗi xuất hiện ngay trong bước parse. Việc đọc đúng loại exception và vị trí lỗi giúp xác định token nào không hợp lệ, phần cú pháp nào còn thiếu và cách sửa biểu thức.

Một điểm cần phân biệt xuyên suốt bài này: **parse lỗi cú pháp; evaluate thực thi biểu thức trong một context**. Một biểu thức có thể parse thành công nhưng vẫn thất bại khi đánh giá vì property không tồn tại, method không gọi được, giá trị null hoặc không chuyển đổi được kiểu.

## 1. Parse diễn ra ở giai đoạn nào?

Luồng xử lý thông thường gồm ba bước:

1. Tạo **ExpressionParser**.
2. Gọi **parseExpression(...)** để phân tích chuỗi và nhận về **Expression**.
3. Gọi **getValue(...)** khi cần đánh giá biểu thức với root object hoặc **EvaluationContext**.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("order.total > 100");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Boolean result = expression.getValue(context, Boolean.class);
~~~

Nếu biểu thức có cú pháp không hợp lệ, lỗi phát sinh ở lời gọi **parseExpression**. Ví dụ:

~~~java
parser.parseExpression("order.total >");
~~~

Biểu thức trên kết thúc bằng toán tử so sánh nhưng thiếu toán hạng bên phải. Parser không thể tạo một expression hợp lệ và ném lỗi parse.

Ngược lại, biểu thức sau có thể parse thành công:

~~~java
Expression expression =
        parser.parseExpression("order.unknownProperty > 100");
~~~

Parser có thể tạo được cây biểu thức mà không cần biết **order** có property **unknownProperty** hay không. Khi gọi **getValue**, SpEL mới truy cập root object và có thể phát sinh lỗi đánh giá nếu property đó không tồn tại.

Vì vậy, khi điều tra lỗi, hãy xác định exception xuất hiện ở **parseExpression** hay **getValue**. Không nên gom hai giai đoạn vào cùng một thông báo chung như “biểu thức không hợp lệ”.

## 2. Các loại exception khi parse SpEL

### 2.1. ParseException

**org.springframework.expression.ParseException** là exception nền cho lỗi phân tích biểu thức. Nó kế thừa **EvaluationException** và cung cấp thông tin về chuỗi biểu thức cùng vị trí xảy ra lỗi.

Các thông tin hữu ích gồm:

- **getExpressionString()**: chuỗi biểu thức liên quan đến lỗi.
- **getPosition()**: vị trí parser báo lỗi.
- **getMessage()**: thông báo giải thích lỗi.

Có thể bắt **ParseException** nếu mã xử lý chỉ cần một kiểu exception chung cho bước parse.

### 2.2. SpelParseException

**org.springframework.expression.spel.SpelParseException** là loại exception cụ thể của parser SpEL. Ngoài thông tin cơ bản từ **ParseException**, nó cung cấp thông tin chẩn đoán theo mã thông báo của SpEL:

- **getMessageCode()**: mã **SpelMessage** mô tả nhóm lỗi.
- **getInserts()**: các giá trị bổ sung được dùng để tạo thông báo lỗi.
- **getPosition()**: vị trí parser phát hiện vấn đề.

Ví dụ, parser có thể báo một token không được mong đợi, thiếu dấu đóng hoặc còn dữ liệu phía sau một biểu thức đã hợp lệ. Mã thông báo giúp phân biệt các trường hợp này mà không phải phân tích chuỗi tiếng Anh trong **getMessage()**.

Thông báo đầy đủ thường chứa biểu thức, vị trí và mã lỗi. Nội dung chính xác có thể thay đổi theo phiên bản Spring và ngữ cảnh lỗi. Khi viết chương trình, hãy dùng các thuộc tính có cấu trúc của exception thay vì tách chuỗi **getMessage()** để suy ra vị trí hoặc loại lỗi.

### 2.3. Bắt lỗi parse và lấy thông tin chẩn đoán

~~~java
import java.util.Arrays;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.ParseException;
import org.springframework.expression.spel.SpelParseException;
import org.springframework.expression.spel.standard.SpelExpressionParser;

public class SpelParseDiagnostic {

    public static void main(String[] args) {
        String source = "order.total >";

        ExpressionParser parser = new SpelExpressionParser();

        try {
            Expression expression = parser.parseExpression(source);
            System.out.println("Parsed: " + expression.getExpressionString());
        } catch (ParseException ex) {
            System.out.println("Expression: " + ex.getExpressionString());
            System.out.println("Position: " + ex.getPosition());
            System.out.println("Message: " + ex.getMessage());

            if (ex instanceof SpelParseException spelEx) {
                System.out.println("Message code: "
                        + spelEx.getMessageCode());
                System.out.println("Inserts: "
                        + Arrays.toString(spelEx.getInserts()));
            }
        }
    }
}
~~~

Trong ví dụ, **ParseException** xử lý trường hợp tổng quát. Khi exception thực tế là **SpelParseException**, chương trình có thể lấy thêm mã lỗi và các tham số chẩn đoán.

Không cần bắt rồi tạo một **SpelParseException** mới chỉ để đổi thông báo. Hãy giữ exception gốc làm nguyên nhân (**cause**) nếu cần chuyển nó sang exception thuộc tầng ứng dụng.

## 3. Hiểu vị trí lỗi (position)

**getPosition()** trả về một offset trong chuỗi biểu thức mà parser đang phân tích. Đây là vị trí phục vụ chẩn đoán cú pháp, không nhất thiết là vị trí của nguyên nhân đầu tiên khiến người viết biểu thức sai.

Ví dụ:

~~~java
String source = "price + * quantity";
~~~

Parser có thể phát hiện token **\*** không hợp lệ trong vị trí đang chờ toán hạng. Tuy nhiên, nguyên nhân mà người viết định diễn đạt có thể là đã đặt thừa dấu **+** hoặc thiếu một giá trị ở giữa. Hãy đọc cả biểu thức và thông báo, không chỉ nhìn một ký tự tại offset.

### 3.1. Offset và chỉ số ký tự

Trong Java, chuỗi được đánh chỉ số bằng đơn vị UTF-16 code unit. Vì vậy, offset của exception nên được dùng trực tiếp với chính chuỗi Java đã truyền vào parser:

~~~java
int position = ex.getPosition();

if (position >= 0 && position <= source.length()) {
    char characterAtPosition =
            position < source.length()
                    ? source.charAt(position)
                    : '\0';
}
~~~

Một số lưu ý:

- Offset thường được hiểu là chỉ số bắt đầu từ 0 trong chuỗi đầu vào.
- Giá trị có thể nằm tại cuối chuỗi khi parser đang chờ một token nhưng không còn ký tự nào.
- Nếu vị trí âm hoặc nằm ngoài phạm vi chuỗi, không tạo caret bằng cách gọi **substring** trực tiếp.
- Ký tự Unicode ngoài Basic Multilingual Plane chiếm hai UTF-16 code unit. Do đó, offset Java không luôn bằng số Unicode code point mà người dùng nhìn thấy.
- Tab, ký tự tổ hợp và font hiển thị có thể làm cột caret trên giao diện lệch khỏi vị trí nhìn bằng mắt.

Cách an toàn là giữ nguyên chuỗi đầu vào và dùng **getPosition()** trên đúng chuỗi đó. Không trim, chuẩn hóa khoảng trắng hoặc xóa ký tự trước khi đối chiếu offset. Nếu ứng dụng biến đổi biểu thức trước khi parse, cần lưu ánh xạ từ chuỗi đã biến đổi về chuỗi gốc.

### 3.2. Vị trí parser báo và vị trí cần sửa

Parser thường báo nơi nó không thể tiếp tục theo grammar hiện tại. Vị trí này hữu ích để khoanh vùng nhưng không bảo đảm là ký tự duy nhất cần sửa.

Ví dụ:

~~~text
price + * quantity
        ^
~~~

Dấu **\*** là token parser gặp khi đang chờ toán hạng. Cách sửa phụ thuộc ý định:

~~~text
price * quantity
~~~

hoặc:

~~~text
price + discount * quantity
~~~

Không nên tự động xóa token tại **position** rồi parse lại. Thao tác đó có thể làm biểu thức trở thành một cú pháp khác nhưng sai ý nghĩa nghiệp vụ.

## 4. Hiển thị caret tại vị trí lỗi

Một cách chẩn đoán dễ hiểu là hiển thị dòng chứa lỗi và một dấu **^** bên dưới offset. Với biểu thức một dòng, có thể dùng helper đơn giản:

~~~java
static String formatCaret(String source, int position) {
    if (position < 0 || position > source.length()) {
        return source;
    }

    int lineStart = source.lastIndexOf('\n', position - 1) + 1;
    int lineEnd = source.indexOf('\n', position);

    if (lineEnd < 0) {
        lineEnd = source.length();
    }

    String line = source.substring(lineStart, lineEnd);
    if (line.endsWith("\r")) {
        line = line.substring(0, line.length() - 1);
    }

    int column = Math.min(position - lineStart, line.length());

    return line + System.lineSeparator()
            + " ".repeat(column) + "^";
}
~~~

Sử dụng:

~~~java
String source = "price + * quantity";

try {
    parser.parseExpression(source);
} catch (ParseException ex) {
    System.out.println(ex.getMessage());
    System.out.println(formatCaret(source, ex.getPosition()));
}
~~~

Kết quả minh họa:

~~~text
price + * quantity
        ^
~~~

Helper này phục vụ log hoặc ví dụ đơn giản. Với biểu thức nhiều dòng, giao diện nên hiển thị thêm số dòng và cột. Với tab, nên tính vị trí hiển thị sau khi mở rộng tab theo quy tắc của editor. Với Unicode, cần chuyển offset UTF-16 sang chỉ số hiển thị phù hợp nếu giao diện đếm theo code point hoặc grapheme cluster.

Nếu biểu thức chứa dữ liệu nhạy cảm do người dùng nhập, cân nhắc che hoặc rút gọn nội dung trước khi ghi log. Có thể lưu mã lỗi, offset và một đoạn ngữ cảnh đã được làm sạch thay vì ghi toàn bộ chuỗi.

## 5. Những nguyên nhân parse lỗi thường gặp

| Nhóm lỗi | Ví dụ không hợp lệ | Cách kiểm tra |
|---|---|---|
| Thiếu toán hạng | **price +** | Kiểm tra toán tử cuối biểu thức và phần biểu thức ngay sau nó |
| Toán tử đặt sai chỗ | **price + * quantity** | Kiểm tra thứ tự toán tử và toán hạng |
| Thiếu dấu ngoặc đóng | **(price + tax** | Ghép cặp dấu ngoặc tròn |
| Thiếu dấu ngoặc vuông | **items[0** | Kiểm tra biểu thức truy cập phần tử |
| Chuỗi chưa đóng | **'Spring** | Kiểm tra dấu nháy đơn hoặc nháy kép |
| Method call thiếu dấu đóng | **customer.getName(** | Kiểm tra danh sách argument và dấu ngoặc |
| Dấu phẩy thừa hoặc thiếu | **max(10,,20)** | Kiểm tra dấu phân cách argument |
| Token thừa ở cuối | **price 123** | Kiểm tra xem sau biểu thức hợp lệ còn ký tự nào không |
| Sai cú pháp truy cập property | **customer.first-name** | Nếu tên property có dấu gạch nối, cân nhắc truy cập bằng cú pháp index/key phù hợp |
| Sai delimiter template | **Hello #{name** | Kiểm tra prefix/suffix của ParserContext |

Một số chuỗi trông giống cú pháp Java hoặc SQL nhưng không có nghĩa giống nhau trong SpEL. Khi một tên property chứa dấu gạch nối, biểu thức:

~~~java
customer.first-name
~~~

có thể được parser hiểu theo cấu trúc truy cập property kết hợp toán tử trừ, thay vì một tên property duy nhất. Nếu property là một key trong map, có thể viết theo dạng:

~~~java
customer['first-name']
~~~

Cú pháp truy cập cần phù hợp với kiểu object thực tế và accessor được cấu hình trong evaluation context.

## 6. Parse biểu thức thường và template expression

**ExpressionParser** có overload nhận **ParserContext**. Tham số này cho parser biết chuỗi đầu vào là biểu thức thông thường hay template có chứa các đoạn biểu thức.

Biểu thức thông thường:

~~~java
Expression expression =
        parser.parseExpression("user.name.toUpperCase()");
~~~

Template expression có thể chứa văn bản tĩnh và phần SpEL được đánh dấu bằng delimiter:

~~~java
import org.springframework.expression.common.TemplateParserContext;

Expression template = parser.parseExpression(
        "Hello #{user.name}",
        new TemplateParserContext()
);
~~~

**TemplateParserContext** mặc định dùng **#{** làm prefix và **}** làm suffix. Nếu ứng dụng định nghĩa delimiter riêng, phải dùng cùng một **ParserContext** khi parse để tránh chẩn đoán sai rằng biểu thức bị thiếu hoặc thừa delimiter.

Khi debug template:

1. Giữ nguyên toàn bộ chuỗi template đã truyền vào.
2. Xác định parser đang dùng **ParserContext** nào.
3. Kiểm tra cặp prefix/suffix và phần biểu thức nằm giữa chúng.
4. Đọc **getPosition()** cùng thông báo của exception để biết parser báo ở vùng nào.
5. Nếu hiển thị lỗi cho người dùng, ánh xạ offset về đoạn template tương ứng trước khi đánh dấu trong editor.

Không nên tự bỏ phần văn bản tĩnh rồi parse phần **#{...}** bằng parser thường nếu mục tiêu là tái hiện đúng lỗi của lần chạy ban đầu. Việc thay đổi đầu vào hoặc **ParserContext** có thể làm offset và lỗi thu được khác đi.

## 7. Phân biệt ParseException với lỗi khi evaluate

Hai giai đoạn có exception khác nhau và cần được xử lý riêng:

| Giai đoạn | Exception thường gặp | Ví dụ |
|---|---|---|
| Parse | **ParseException**, cụ thể hơn là **SpelParseException** | **price +** |
| Evaluate | **EvaluationException**, cụ thể hơn là **SpelEvaluationException** | Đọc property không tồn tại hoặc gọi method không hợp lệ |
| Chuyển kiểu trong lúc evaluate | Có thể phát sinh **EvaluationException** | Không chuyển được giá trị sang kiểu tham số |

Ví dụ tách hai giai đoạn:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("customer.age > 18");
} catch (ParseException ex) {
    // Cú pháp không hợp lệ: xử lý vị trí và thông tin parse.
    throw new IllegalArgumentException(
            "Invalid SpEL syntax at position " + ex.getPosition(),
            ex
    );
}

try {
    Boolean result = expression.getValue(context, Boolean.class);
    System.out.println(result);
} catch (EvaluationException ex) {
    // Cú pháp đã parse được, nhưng đánh giá trong context thất bại.
    throw new IllegalStateException(
            "Cannot evaluate the configured expression",
            ex
    );
}
~~~

Ví dụ trên cố ý tách hai khối **try/catch**. Trong mã thực tế, có thể dùng exception nghiệp vụ riêng cho từng giai đoạn, nhưng nên giữ nguyên exception gốc làm **cause** để không mất stack trace và thông tin chẩn đoán.

Một biểu thức parse thành công không chứng minh rằng:

- Root object có đầy đủ property được tham chiếu.
- Method được gọi tồn tại hoặc có thể truy cập.
- Giá trị runtime có kiểu phù hợp.
- ConversionService có converter cần thiết.
- Phép toán có thể thực hiện với các giá trị thực tế.

Những điều kiện đó chỉ được kiểm tra đầy đủ khi đánh giá biểu thức trong context cụ thể.

## 8. Quy trình điều tra một lỗi parse

Khi nhận được **SpelParseException**, có thể đi theo trình tự sau:

1. **Lưu đầu vào nguyên gốc.** Ghi nhận đúng chuỗi và **ParserContext** được truyền vào parser. Không trim hoặc sửa chuỗi trước khi tái hiện.
2. **Xác nhận đúng giai đoạn.** Kiểm tra exception có xuất hiện ngay trong **parseExpression** hay sau khi gọi **getValue**.
3. **Đọc offset và mã lỗi.** Lấy **getPosition()**, **getMessageCode()** và **getInserts()** khi exception là **SpelParseException**.
4. **Khoanh vùng cú pháp.** Hiển thị dòng chứa lỗi với caret; kiểm tra toán tử, dấu ngoặc, dấu nháy và dấu phân cách.
5. **Tạo biểu thức tối thiểu.** Rút gọn biểu thức trong môi trường thử nghiệm để tìm token hoặc cấu trúc gây lỗi.
6. **Viết kiểm thử hồi quy.** Giữ lại một trường hợp không hợp lệ để xác nhận parser báo lỗi và một trường hợp hợp lệ để xác nhận cách viết đã sửa.
7. **Kiểm tra giai đoạn evaluate riêng.** Sau khi parse thành công, đánh giá với root object và context đại diện để phát hiện lỗi runtime.

Không nên dựa hoàn toàn vào nội dung **getMessage()** để viết logic xử lý. Thông báo phục vụ con người có thể thay đổi theo phiên bản và locale. Dùng kiểu exception, offset và mã thông báo cho chẩn đoán có cấu trúc; chỉ hiển thị thông báo thân thiện ở tầng giao diện.

## 9. Thiết kế thông báo lỗi cho ứng dụng

Nếu ứng dụng cho phép người dùng nhập biểu thức, nên chuẩn hóa kết quả parse lỗi thành một cấu trúc chẩn đoán của ứng dụng:

~~~java
public record ExpressionDiagnostic(
        String code,
        int position,
        String message
) {
}
~~~

Ví dụ cách chuyển exception thành diagnostic:

~~~java
static ExpressionDiagnostic toDiagnostic(ParseException ex) {
    String code = "SPEL_PARSE_ERROR";

    if (ex instanceof SpelParseException spelEx) {
        code = spelEx.getMessageCode().name();
    }

    return new ExpressionDiagnostic(
            code,
            ex.getPosition(),
            "Biểu thức không đúng cú pháp"
    );
}
~~~

Cấu trúc này giúp API hoặc giao diện không phụ thuộc trực tiếp vào toàn bộ chuỗi exception của Spring. Có thể gửi **position** về editor để đánh dấu vùng lỗi, còn thông báo hiển thị được dịch theo ngôn ngữ ứng dụng.

Khi thiết kế diagnostic, cần lưu ý:

- **position** phải gắn với đúng phiên bản chuỗi mà parser đã nhận.
- Không đưa nội dung expression nhạy cảm vào response hoặc log công khai.
- Không coi **code** là một chuỗi tự do để phân tích; lấy mã từ exception cụ thể.
- Giữ exception gốc ở log nội bộ có kiểm soát nếu cần điều tra sâu.
- Nếu ứng dụng tự sửa hoặc chuẩn hóa biểu thức, cần ánh xạ vị trí giữa chuỗi đầu vào và chuỗi parser nhận được.

## 10. Giới hạn an toàn khi xử lý biểu thức do người dùng cung cấp

Thông báo parse lỗi chỉ nói rằng chuỗi không đúng grammar. Nó không chứng minh biểu thức hợp lệ là an toàn để chạy.

Nếu ứng dụng nhận SpEL từ người dùng, cần thiết kế **EvaluationContext** với quyền hạn phù hợp, giới hạn những property, method, type hoặc khả năng truy cập mà biểu thức được phép sử dụng. Không đánh giá biểu thức không tin cậy trong context có toàn bộ quyền của ứng dụng chỉ vì bước parse đã thành công.

Một số nguyên tắc:

- Chỉ cho phép các tính năng biểu thức mà nghiệp vụ cần.
- Hạn chế type reference, constructor, method và bean access khi không cần.
- Xem xét **SimpleEvaluationContext** nếu chỉ cần tập tính năng SpEL giới hạn.
- Không dùng việc bắt **SpelParseException** làm cơ chế kiểm soát bảo mật.
- Giới hạn kích thước đầu vào và xử lý lỗi có kiểm soát để tránh biểu thức quá lớn gây tốn tài nguyên.
- Không tự động thực thi lại biểu thức đã được sửa theo phỏng đoán của parser.

## 11. Tổng kết

Lỗi parse xuất hiện khi parser không thể phân tích chuỗi theo cú pháp SpEL. **ParseException** cung cấp thông tin chung về biểu thức và vị trí; **SpelParseException** bổ sung mã lỗi cùng các tham số chẩn đoán riêng của SpEL.

Khi xử lý lỗi, hãy giữ nguyên chuỗi đầu vào, đọc **getPosition()** và mã thông báo, hiển thị caret nếu phù hợp, sau đó kiểm tra lại grammar. Luôn phân biệt parse với evaluate: parse thành công chỉ xác nhận cấu trúc cú pháp có thể được tạo thành **Expression**, còn việc truy cập property, gọi method và tính toán chỉ được xác nhận khi đánh giá trong **EvaluationContext** thực tế.
