# Expression injection — Ngăn dữ liệu trở thành mã biểu thức

## 1. Bản chất của expression injection

**Expression injection** xảy ra khi dữ liệu từ một nguồn không đáng tin có thể thay đổi biểu thức mà ứng dụng đưa vào một bộ diễn giải. Dữ liệu đáng lẽ chỉ là giá trị lại có cơ hội trở thành toán tử, lời gọi, truy cập thuộc tính hoặc cấu trúc điều khiển của ngôn ngữ biểu thức.

Trong ứng dụng Java, ngôn ngữ biểu thức có thể xuất hiện trong điều kiện nghiệp vụ, mẫu hiển thị, cấu hình động hoặc tính năng lọc dữ liệu. Ví dụ quen thuộc là Spring Expression Language — SpEL. Có sử dụng một ngôn ngữ biểu thức không tự động đồng nghĩa có lỗ hổng; vấn đề nằm ở **nguồn của biểu thức, cách xây dựng nó và quyền mà bộ diễn giải được tiếp cận**.

CWE-917 mô tả việc xây dựng toàn bộ hoặc một phần câu lệnh expression language từ dữ liệu chịu ảnh hưởng bên ngoài mà không giữ đúng ranh giới giữa cú pháp và dữ liệu. Hậu quả phụ thuộc ngôn ngữ và ngữ cảnh thực thi, có thể gồm đọc dữ liệu ứng dụng hoặc thực hiện biểu thức ngoài ý định. [MITRE CWE-917](https://cwe.mitre.org/data/definitions/917.html).

Ví dụ về nguyên tắc:

~~~text
Ý định:
    So sánh số tiền đơn với một ngưỡng do máy chủ quản lý.

Sai ranh giới:
    Ghép text từ request vào mã biểu thức rồi evaluate.

Giữ ranh giới:
    Mã biểu thức cố định hoặc logic Java có kiểu.
    Giá trị số được truyền như dữ liệu đã kiểm tra.
~~~

Một yêu cầu bảo mật hữu ích không chỉ nói “chặn expression injection”. Nó phải quy định **nguồn nào được phép tạo mã biểu thức, dữ liệu nào chỉ được truyền như giá trị, bộ diễn giải được thấy gì và bằng chứng nào xác nhận không có evaluate ngoài ý định**.

Các dịch vụ, mã yêu cầu và giới hạn trong bài là thiết kế minh họa, không phải cấu hình mặc định của một framework.

## 2. Điều kiện tạo ra nguy cơ

Có thể phân tích nguy cơ qua ba thành phần:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Nguồn dữ liệu | Ai có thể thay đổi chuỗi hoặc cấu hình? | Request, message, bản ghi do người dùng sửa, file nhập |
| Điểm diễn giải | Thành phần nào parse hoặc evaluate chuỗi? | `parseExpression`, expression resolver, template runtime |
| Khả năng thực thi | Biểu thức có thể tiếp cận những gì? | Biến, root object, thuộc tính, hàm, resolver, dịch vụ |

Một dữ liệu có thể đi qua nhiều bước trước khi tới điểm diễn giải:

~~~mermaid
flowchart LR
    A[Request hoặc nội dung từ đối tác] --> B[Lưu vào database]
    B --> C[Job đọc lại cấu hình hoặc nội dung]
    C --> D[Ghép thành chuỗi biểu thức]
    D --> E[Parser và evaluator]
    E --> F[Quyết định hoặc dữ liệu đầu ra]
~~~

Database không làm dữ liệu tự trở thành mã đáng tin. Nếu người dùng thường có thể sửa một trường trong database và một job sau đó evaluate trường ấy, ranh giới tin cậy vẫn bị vượt qua tại job.

Tương tự, “chỉ admin mới sửa” chưa đủ cụ thể. Quản trị viên nội dung của một tenant không nhất thiết có quyền cấu hình ứng dụng hoặc chạy mã trong tiến trình máy chủ. Quyền viết công thức phải được xem như một quyền có khả năng tác động tới hệ thống, không chỉ là quyền chỉnh text.

Đặc tả cần phân biệt ít nhất:

- Mã biểu thức do nhóm phát triển quản lý trong source hoặc artifact đã duyệt.
- Cấu hình do người vận hành được cấp quyền thay đổi qua quy trình kiểm soát.
- Nội dung hoặc dữ liệu do người dùng, đối tác hay tenant quản lý.
- Dữ liệu hệ thống đã lưu nhưng có nguồn gốc từ các nhóm trên.

Không suy ra mức tin cậy chỉ từ vị trí file, tên bảng hoặc tên role.

## 3. Phân biệt với các dạng injection khác

Điểm chung của injection là dữ liệu có thể thay đổi cách một thành phần diễn giải cú pháp. Nhưng mỗi bộ diễn giải có ngữ pháp và cơ chế bảo vệ riêng.

| Loại | Thành phần diễn giải | Điều cần giữ tách biệt |
| --- | --- | --- |
| SQL injection | Database query engine | Cấu trúc truy vấn và giá trị |
| OS command injection | Shell hoặc chương trình được gọi | Chương trình/tham số theo hợp đồng |
| Expression injection | Bộ diễn giải biểu thức | Mã biểu thức và giá trị |
| Server-side template injection | Template engine trên máy chủ | Mã template và dữ liệu render |
| XSS | Trình duyệt trong ngữ cảnh HTML/JavaScript liên quan | Nội dung dữ liệu và cú pháp có thể thực thi |

Expression injection và template injection có thể giao nhau khi template engine hỗ trợ evaluation block. Tuy nhiên, không nên coi mọi công cụ có ký hiệu `${...}` là cùng một ngôn ngữ.

Ví dụ, Spring có cơ chế expression templating cho phép trộn text với các block biểu thức. Với `TemplateParserContext` mặc định, delimiter là `#{` và `}`; parser context ảnh hưởng cách chuỗi được diễn giải. [Spring Framework — Expression Templating](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/templating.html).

Điều này dẫn đến hai điểm:

**Không nhận diện lỗ hổng chỉ bằng ký hiệu.** Một chuỗi ghi chú chứa `#{6 * 7}` có thể hoàn toàn là văn bản bình thường nếu chỉ được lưu và hiển thị như dữ liệu.

**Không phòng vệ chỉ bằng chặn ký hiệu.** Khi ứng dụng gọi parser ở chế độ raw expression, biểu thức có thể không cần delimiter template. Kiểm tra không có `${` hoặc `#{` không chứng minh không có expression injection.

Bảo vệ HTML đầu ra cũng không thay thế bảo vệ bộ diễn giải phía máy chủ. Một chuỗi đã được encode để hiển thị HTML không vì thế trở thành dữ liệu an toàn để ghép vào mã SpEL.

## 4. Hai cách làm sai thường gặp

### 4.1. Đưa trực tiếp request vào parser

Đoạn mã sau là minh họa một điểm nguy hiểm, không phải cách triển khai được khuyến nghị:

~~~java
Expression expression =
        parser.parseExpression(request.getCondition());
Object result = expression.getValue(context);
~~~

Nếu `condition` là dữ liệu người dùng thường được sửa, người dùng đang cung cấp mã cho bộ diễn giải. Chỉ giới hạn chiều dài hoặc đổi evaluation context không biến mô hình này thành an toàn một cách mặc định.

Đối với một trường lẽ ra chỉ là ghi chú, dữ liệu như `6 * 7` phải tiếp tục là text. Nếu ứng dụng trả kết quả tính toán, đó là dấu hiệu đã có một bước diễn giải ngoài hợp đồng. Phép thử vô hại này chỉ có ý nghĩa trong môi trường kiểm thử được phép và không đủ để kết luận mọi quyền năng của bộ diễn giải.

### 4.2. Ghép giá trị vào một biểu thức có vẻ cố định

Một dạng khác:

~~~java
String source = "amount >= " + request.getMinimum();
Expression expression = parser.parseExpression(source);
~~~

Phần `"amount >= "` cố định không làm toàn bộ cấu trúc trở thành cố định. `minimum` vẫn có thể bổ sung cú pháp nếu được giữ dưới dạng text và đưa vào mã nguồn biểu thức.

Tương tự, đặt dữ liệu giữa dấu nháy trong biểu thức không phải một cơ chế bind biến:

~~~text
Mã biểu thức = tiền tố cố định + dấu nháy + dữ liệu + dấu nháy.
~~~

Hệ thống vẫn đang tự xây dựng mã nguồn. Tính đúng đắn khi đó phụ thuộc toàn bộ ngữ pháp, escape và các lần diễn giải tiếp theo. Không nên đặt yêu cầu phòng vệ trên giả định “đã thêm dấu nháy nên chỉ còn là string”.

Trong đặc tả, cần cấm cả **toàn bộ chuỗi không đáng tin** và **đoạn chuỗi không đáng tin** đi vào phần mã biểu thức ngoài cơ chế được duyệt.

## 5. Chọn thiết kế theo nhu cầu thật

Không phải tính năng nào cũng cần ngôn ngữ biểu thức. Có thể chọn theo thứ tự giảm khả năng diễn giải:

| Nhu cầu sản phẩm | Thiết kế nên xem xét | Bằng chứng cần có |
| --- | --- | --- |
| Một vài điều kiện cố định | Logic Java có kiểu | Không có điểm parse chuỗi từ request |
| Chọn một quy tắc trong tập hữu hạn | Rule ID ánh xạ tới mã do máy chủ quản lý | ID không biến thành tên class, method hoặc biểu thức tùy ý |
| Quy tắc do đội vận hành quản lý | Biểu thức đã duyệt, có phiên bản và quyền thay đổi | Nguồn biểu thức tách khỏi dữ liệu runtime |
| Người dùng cần tự xây bộ lọc | DSL có cấu trúc, trường và toán tử được cho phép | Không dùng trực tiếp ngôn ngữ đa năng làm sandbox |
| Người dùng được viết chương trình | Một nền tảng thực thi riêng có mô hình cách ly | Đánh giá an toàn của khả năng thực thi, quyền và ngân sách tài nguyên |

Ví dụ, nếu yêu cầu chỉ là kiểm tra một số tiền đã tính trên máy chủ có đạt ngưỡng không, Java trực tiếp có thể đủ:

~~~java
public static boolean reachesMinimum(
        BigDecimal amount, BigDecimal minimum) {
    return amount.compareTo(minimum) >= 0;
}
~~~

Đoạn này cần các tiền điều kiện về null, miền số và nguồn ngưỡng được thực hiện ở nơi phù hợp. Điểm chính là không có ngôn ngữ biểu thức để dữ liệu có thể thay đổi cú pháp.

Nếu client được chọn `ruleId`, cần ánh xạ bằng một tập cố định, chẳng hạn `MINIMUM_AMOUNT`, thay vì coi ID là đoạn mã hoặc đường dẫn tài nguyên tùy ý. Bản thân quyền chọn quy tắc cũng phải theo nghiệp vụ; người dùng không được chọn một quy tắc dễ hơn để bỏ qua kiểm soát bắt buộc.

## 6. Khi cần biểu thức: mã cố định, biến dữ liệu có kiểu

Giả sử đội phát triển có một biểu thức cố định để đánh giá điều kiện ngưỡng. Nguồn biểu thức được quản lý cùng artifact triển khai; caller không được truyền hoặc thay nó.

Cấu trúc minh họa:

~~~text
Nguồn biểu thức:
    #amount >= #minimum

Dữ liệu:
    amount  = BigDecimal từ tổng đơn do máy chủ xác định.
    minimum = BigDecimal từ chính sách do máy chủ quản lý.
~~~

Mã Java sử dụng Spring Expression có thể được tổ chức như sau:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.expression.Expression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.SimpleEvaluationContext;

public final class MinimumAmountExpression {
    private static final Expression RULE =
            new SpelExpressionParser()
                    .parseExpression("#amount >= #minimum");

    public static boolean evaluate(
            BigDecimal amount, BigDecimal minimum) {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(minimum, "minimum");

        SimpleEvaluationContext context =
                SimpleEvaluationContext
                        .forReadOnlyDataBinding()
                        .build();

        context.setVariable("amount", amount);
        context.setVariable("minimum", minimum);

        Object result = RULE.getValue(context);
        if (!(result instanceof Boolean answer)) {
            throw new IllegalStateException(
                    "UNEXPECTED_RULE_RESULT");
        }
        return answer;
    }
}
~~~

Đoạn mã minh họa điểm gọi parser nhận **literal do nhà phát triển kiểm soát**, còn số được đưa qua biến. Nó không nhận một tham số `expression` từ request và không parse lại giá trị biến thành mã.

Tiền điều kiện của ví dụ gồm: số đã có miền và độ chính xác được kiểm soát; `minimum` đến từ chính sách có thẩm quyền; kết quả quy tắc không thay thế các kiểm tra quyền khác. Code không triển khai toàn bộ service hoặc quản lý chính sách.

Context được tạo cho mỗi lần đánh giá để tránh chia sẻ biến mutable giữa các request. Biểu thức được dùng lại trong cùng một mô hình context và cấu hình tương đương; không được dùng chính instance đã được evaluate dưới cấu hình quyền rộng rồi tái sử dụng như thể nó chưa mang trạng thái đã cache.

Spring cảnh báo parsed expression có thể cache trạng thái accessor/executor; không tái sử dụng một instance qua các context có ý nghĩa bảo mật khác nhau. Khi cần hai cấu hình khác nhau, dùng các instance parse riêng. [Spring Framework — SimpleEvaluationContext API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html).

Đây không phải ví dụ “an toàn hóa expression do người dùng viết”. Sự bảo vệ cốt lõi là **người dùng không cung cấp mã biểu thức**. Context giới hạn chỉ hỗ trợ thu hẹp khả năng cần thiết cho biểu thức đã được tin cậy.

## 7. Context giới hạn không phải một sandbox mặc định

Một phát biểu dễ gây sai thiết kế là:

> Chỉ cần dùng read-only context thì có thể evaluate mọi chuỗi người dùng gửi.

Read-only thường chỉ kiểm soát một số thao tác ghi mà cơ chế đó biết tới. Một phép đọc property có thể gọi một accessor; accessor lại có thể thực hiện I/O hoặc thay đổi một hệ thống khác. Tên phương thức và hình dạng getter không chứng minh không có tác dụng phụ.

Tài liệu Spring nhấn mạnh việc evaluate SpEL từ nguồn không đáng tin vốn nguy hiểm; `SimpleEvaluationContext` giới hạn tính năng theo cơ chế best effort và không bảo đảm biến expression không đáng tin thành an toàn. Cần xét toàn bộ object có thể đi tới qua root, biến, property, hàm và resolver. [Spring Framework — Evaluation, Security Considerations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html).

Vì vậy, yêu cầu về context nên xác định cụ thể:

| Bề mặt | Câu hỏi kiểm soát |
| --- | --- |
| Root object | Có chứa service, request, session hoặc đối tượng hạ tầng không? |
| Biến | Có chỉ chứa dữ liệu nhỏ, có kiểu và được phép không? |
| Property accessor | Đọc property có thể gọi logic có tác dụng phụ không? |
| Method/function | Có khả năng gọi I/O, truy cập secret hoặc thay đổi trạng thái không? |
| Type/constructor/bean resolver | Có cần thiết không; có được cấu hình ngoài ý định không? |
| Converter | Chuyển kiểu có thực hiện logic ngoài miền dữ liệu được phép không? |
| Object lồng nhau | Từ một DTO có đi tiếp tới một object quyền rộng hơn không? |

Đối với biểu thức cố định của ví dụ, không cần truyền `ApplicationContext`, repository, HTTP client hoặc đối tượng chứa toàn bộ đơn hàng. Chỉ hai số là đủ.

Thiết kế này giảm bề mặt có thể tiếp cận và giúp yêu cầu dễ nghiệm thu. Tuy nhiên, nếu sau này ai đó thêm một biến chứa service để “tiện dùng trong rule”, đó là một thay đổi về khả năng thực thi cần được xem xét như thay đổi thiết kế bảo mật.

Không xem immutable DTO là bảo đảm tuyệt đối nếu nó chứa reference tới object khác có hành vi nguy hiểm. Phạm vi phải được xét theo dữ liệu và hành vi có thể tiếp cận, không chỉ theo việc các field có `final` hay không.

## 8. Khi người dùng thật sự cần một ngôn ngữ quy tắc

Một tính năng cho phép người dùng tự xây bộ lọc là nhu cầu khác với một ô ghi chú. Không nên triển khai bằng cách nhận tùy ý mã SpEL rồi thêm danh sách từ khóa bị cấm.

Một phương án là DSL có cấu trúc chỉ cung cấp những khả năng cần thiết:

~~~json
{
  "all": [
    {
      "field": "amount",
      "operator": "GTE",
      "value": "100.00"
    },
    {
      "field": "itemCount",
      "operator": "LTE",
      "value": 10
    }
  ]
}
~~~

Đây là minh họa cấu trúc bộ lọc, không phải một payload để tùy ý thay chính sách bảo mật. Việc ai được tạo hoặc áp dụng rule phải có quyền riêng.

Hợp đồng DSL có thể giới hạn:

- Field chỉ thuộc tập `amount` và `itemCount`.
- Operator chỉ thuộc tập so sánh do sản phẩm hỗ trợ.
- Giá trị được parse thành kiểu số xác định.
- Nhóm chỉ có `all` hoặc `any` với số phần tử bị giới hạn.
- Không có truy cập property theo đường dẫn, lời gọi hàm, gán hoặc truy cập type.
- Không có text được chèn tiếp vào một parser ngôn ngữ đa năng.

Interpreter của DSL có thể duyệt cấu trúc và gọi các phép so sánh có kiểu. Ví dụ, `GTE` ánh xạ trực tiếp tới so sánh số. Không chuyển cây DSL thành string SpEL rồi coi rằng dữ liệu đã được “làm sạch”.

Nếu phải hỗ trợ cú pháp text, parser phải xây cấu trúc được hiểu rõ và chỉ chấp nhận các node cho phép. Kiểm tra cần diễn ra trong lúc parse và trước đánh giá; độ sâu không được chỉ kiểm tra sau khi parser đã tiêu thụ tài nguyên không giới hạn.

Một tập giới hạn minh họa cho DSL nhỏ:

| Thuộc tính | Giới hạn minh họa |
| --- | --- |
| Nội dung request rule | Tối đa 4.096 byte UTF-8 |
| Độ sâu nhóm | Tối đa 8 |
| Tổng node điều kiện và nhóm | Tối đa 64 |
| Số phần tử trong một nhóm | Tối đa 16 |
| Giá trị số | Miền và độ chính xác theo từng field |
| Kết quả | Một boolean |
| Hàm tùy ý và I/O | Không được cung cấp |

Những con số này phải được lựa chọn lại theo nhu cầu thật. Chúng không phải bằng chứng rằng mọi ngôn ngữ có cùng giới hạn đều an toàn.

Nếu sản phẩm thật sự cần chương trình hoặc biểu thức từ người dùng với khả năng rộng, phải đánh giá mô hình thực thi riêng, cách ly và quyền truy cập tài nguyên. Không gọi một evaluation context trong tiến trình ứng dụng là “sandbox” khi chưa có cơ chế và bằng chứng tương ứng.

## 9. Ngăn diễn giải lần hai

Một đường đi có thể an toàn ở lần đầu nhưng sai ở lần sau:

~~~text
1. Lưu ghi chú của người dùng như string.
2. Đưa ghi chú vào dữ liệu render.
3. Lấy kết quả render làm nguồn biểu thức hoặc template mới.
4. Evaluate lần hai.
~~~

Việc bind dữ liệu đúng ở bước đầu không bảo đảm bước sau vẫn giữ ranh giới. Nếu string kết quả lại được parse thành mã, khả năng injection xuất hiện tại bước mới.

Yêu cầu cần bao phủ vòng đời dữ liệu:

- Nội dung do người dùng sửa không được trở thành template source.
- Kết quả của biểu thức không được tự động parse lại như biểu thức khác.
- Message lỗi, tên báo cáo hoặc nội dung cấu hình không được đi qua resolver ngoài hợp đồng.
- Dữ liệu lưu trữ giữ nhãn về nguồn và quyền sửa phù hợp với cách nó được dùng.
- Khi xuất dữ liệu vào ngữ cảnh hiển thị, áp dụng bảo vệ của ngữ cảnh đó, không evaluate để “thay biến” tùy tiện.

Không cần cấm người dùng viết mọi dấu ngoặc hoặc ký hiệu template trong văn bản tự do. Điều cần chứng minh là chúng vẫn là dữ liệu khi đi qua hệ thống.

Ví dụ, ghi chú `"Mã tham khảo: #{6 * 7}"` có thể được lưu và hiển thị nguyên ý nghĩa văn bản. Nếu một job biến phần đó thành `42` dù hợp đồng không có chức năng tính toán, job đã làm thay đổi cách diễn giải nội dung.

## 10. Quyền, phiên bản và nguồn chính sách

Biểu thức được lưu trong database có thể là một artifact thực thi, dù trông giống một trường text. Vì vậy, quản lý nó cần chặt hơn quản lý một nhãn hiển thị.

Với bộ quy tắc do đội vận hành quản lý, một thiết kế có thể yêu cầu:

| Thành phần | Điều cần ghi nhận |
| --- | --- |
| Rule ID và phiên bản | Xác định chính xác rule đang được dùng |
| Người có quyền sửa | Tách khỏi quyền nhập dữ liệu nghiệp vụ thông thường |
| Quy trình thay đổi | Có xem xét trước khi đưa vào thực thi |
| Nguồn biểu thức | Không bị ghi đè bởi request hoặc nội dung tenant |
| Context profile | Xác định dữ liệu và khả năng mà rule được tiếp cận |
| Trạng thái phát hành | Phân biệt bản nháp với bản được phép chạy |
| Thu hồi/rollback | Có cách quay về phiên bản đã biết |
| Bằng chứng thực thi | Liên kết kết quả với rule version và context profile |

Không cho client chỉ định một rule version cũ để tránh một chính sách mới bắt buộc. Nếu phiên bản là dữ liệu từ request, máy chủ phải xác minh phiên bản đó có được phép trong ngữ cảnh hiện tại hay không.

Cache cũng là một phần cần xem xét. Một key chỉ gồm source text có thể không đủ nếu các rule khác tenant hoặc khác context có ranh giới quyền khác nhau. Thiết kế cache phải bảo toàn quyền, vòng đời và cách ly dữ liệu; không chia sẻ mutable context của request này cho request khác.

Nâng phiên bản engine có thể thay đổi cú pháp, converter hoặc hành vi evaluation. Vì vậy, yêu cầu cần gắn với phiên bản được triển khai và có kiểm tra hồi quy phù hợp, không dựa vào mặc định nhớ từ một phiên bản khác.

## 11. Giới hạn tài nguyên và hành vi thất bại

Ngay cả khi mục tiêu chỉ là tính toán, expression có thể tạo chi phí CPU, bộ nhớ hoặc kết quả lớn. Không có truy cập mạng hay file không đồng nghĩa chi phí thực thi đã được giới hạn.

Cần xác định ngân sách riêng cho:

- Kích thước mã hoặc cấu trúc rule trước parse.
- Độ sâu và số node trong lúc parse.
- Số thao tác hoặc kích thước tập dữ liệu được đánh giá.
- Miền số, kích thước string và kết quả.
- Số lần đánh giá đồng thời và hàng đợi công việc.
- Cơ chế hủy hoặc cách ly nếu công việc vượt ngân sách.

Timeout ở caller chỉ cho biết caller ngừng chờ. Một thao tác chạy trong cùng tiến trình có thể vẫn tiếp tục sau khi timeout; yêu cầu không được coi việc đặt timeout là bảo đảm đã dừng CPU.

Tương tự, giới hạn số node không tự giới hạn chi phí của một hàm được gọi từ một node. Một hàm có thể thực hiện truy vấn hoặc I/O dài. Thiết kế DSL nhỏ của ví dụ tránh cung cấp những hàm ấy.

Khi parse hoặc evaluate thất bại, hành vi cần được xác định theo mục đích rule:

| Mục đích | Hành vi lỗi cần được quyết định |
| --- | --- |
| Rule cho phép thao tác nhạy cảm | Không tự chuyển lỗi thành cho phép |
| Rule tùy chọn để gợi ý giao diện | Có thể dùng fallback đã công bố, nhưng không thay thế kiểm soát bắt buộc |
| Rule do người dùng soạn nhưng chưa phát hành | Từ chối bản rule, phản hồi lỗi giới hạn |
| Rule máy chủ đã phát hành | Ghi nhận lỗi cấu hình/vận hành, không đổ lỗi mặc định cho input của người dùng |

Response không trả stack trace, root object, biến chứa dữ liệu nhạy cảm hoặc nội dung hệ thống. Log cần đủ xác định rule và nguyên nhân mà không ghi toàn bộ expression/dữ liệu ngoài chính sách.

## 12. Bộ yêu cầu bảo mật minh họa

Có thể chuyển thiết kế thành những yêu cầu có thể phân công và kiểm chứng:

| ID | Yêu cầu | Rủi ro được xử lý | Bằng chứng nghiệm thu |
| --- | --- | --- | --- |
| EXP-001 | Dữ liệu người dùng không được làm source của parser biểu thức ngoài tính năng đã duyệt | Dữ liệu trở thành mã | Truy vết source-to-sink và kiểm thử đường vào |
| EXP-002 | Không ghép giá trị runtime vào mã biểu thức | Thay đổi cấu trúc biểu thức | Source cố định; dữ liệu đi qua biến hoặc logic có kiểu |
| EXP-003 | Không diễn giải lại kết quả hoặc nội dung người dùng ở bước sau | Injection lưu trữ hoặc evaluate lần hai | Văn bản chỉ thị vô hại vẫn là literal qua job và render |
| EXP-004 | Context chỉ chứa dữ liệu và khả năng được phê duyệt | Truy cập ngoài phạm vi | Danh mục root, biến, accessor, function và resolver |
| EXP-005 | Không coi context read-only là sandbox cho source không đáng tin | Đánh giá sai giới hạn bảo vệ | Thiết kế không nhận SpEL tùy ý từ người dùng |
| EXP-006 | Rule được quản lý theo quyền và phiên bản | Sửa chính sách qua đường dữ liệu | Caller thường không sửa hoặc chọn policy trái phép |
| EXP-007 | DSL chỉ chấp nhận node, field và toán tử được cho phép | Mở rộng khả năng diễn giải | Node lạ bị từ chối trước evaluation |
| EXP-008 | Parse/evaluation có giới hạn tài nguyên phù hợp | Tiêu thụ tài nguyên | Ca vượt kích thước/độ sâu/ngân sách thất bại có kiểm soát |
| EXP-009 | Lỗi không mặc định trở thành quyết định cho phép | Bỏ qua kiểm soát | Rule lỗi không kích hoạt thao tác được bảo vệ |
| EXP-010 | Cache và context không làm lẫn quyền hoặc dữ liệu | Rò rỉ/chia sẻ trạng thái giữa request | Kiểm tra cách ly tenant, biến và cấu hình evaluation |
| EXP-011 | Không trả chi tiết nội bộ của engine cho client | Rò rỉ thông tin | Response chỉ có mã lỗi và định danh chẩn đoán phù hợp |
| EXP-012 | Bao phủ mọi đường vào có thể tới điểm diễn giải | Bỏ sót job, message hoặc nội dung đã lưu | Danh mục sink và mapping tới endpoint/job tương ứng |

Một yêu cầu như EXP-001 không thể được nghiệm thu chỉ bằng tìm từ khóa `SpelExpressionParser`. Một framework hoặc wrapper có thể gọi bộ diễn giải gián tiếp. Ngược lại, một điểm parse literal trong code có thể hoàn toàn phù hợp với thiết kế.

Bằng chứng cần xét **chuỗi dữ liệu thật tới sink**, không chỉ tên API hoặc một mẫu payload bị chặn.

## 13. Tiêu chí nghiệm thu trong môi trường được phép

Các ca dưới đây dùng dấu hiệu tính toán vô hại hoặc test double. Chúng mô tả tiêu chí nghiệm thu, không phải báo cáo đã thực thi.

| Ca | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Ghi chú bình thường | Lưu và hiển thị theo hợp đồng dữ liệu |
| T02 | Ghi chú chứa `6 * 7` | Vẫn là text, không tự tính toán |
| T03 | Ghi chú chứa `#{6 * 7}` hoặc `${6 * 7}` | Không được evaluate vì là trường văn bản |
| T04 | Nội dung T03 được đọc lại bởi job | Không trở thành template hoặc expression source |
| T05 | Request cố gửi field `expression` ngoài hợp đồng | Bị xử lý theo quy tắc trường dư; không tới parser |
| T06 | Chuỗi text được gửi thay một số typed | Bị từ chối theo hợp đồng kiểu; không chuyển thành source |
| T07 | Rule ID không tồn tại hoặc không được phép | Không fallback sang evaluate ID như mã |
| T08 | Rule cố định với hai bộ số hợp lệ | Kết quả thay đổi theo giá trị, source biểu thức không đổi |
| T09 | DSL có field hoặc operator lạ | Bị từ chối trước đánh giá |
| T10 | DSL chứa truy cập thuộc tính theo đường dẫn ngoài hợp đồng | Bị từ chối theo cấu trúc được phép |
| T11 | Rule vượt giới hạn kích thước hoặc độ sâu | Dừng có kiểm soát trước chi phí không giới hạn |
| T12 | Engine hoặc rule phát sinh lỗi | Không tự cấp phép thao tác nhạy cảm |
| T13 | Hai request đồng thời có bộ biến khác nhau | Không lẫn biến hoặc kết quả |
| T14 | Hai tenant dùng rule khác nhau | Không dùng nhầm phiên bản/cache/context |
| T15 | Kiểm tra object reachable trong context | Không có service hoặc đối tượng hạ tầng ngoài danh mục |
| T16 | Thử đọc một property canary trong môi trường kiểm thử | Không tiếp cận property ngoài hợp đồng; không dùng secret thật |
| T17 | Nâng engine hoặc thay context profile | Các ca hồi quy vẫn bảo toàn giới hạn đã chốt |
| T18 | Client nhận lỗi parse/evaluation | Không có stack trace, dữ liệu context hoặc chi tiết hạ tầng |

Đối với T02 và T03, không yêu cầu mọi trường văn bản phải trả lỗi. Nếu hợp đồng cho phép các ký tự đó, kết quả đúng là giữ chúng dưới dạng dữ liệu. Việc chặn một ký hiệu không phải mục tiêu cuối cùng.

Với T15, không chỉ nhìn root object. Cần xét object trả về từ property, phần tử collection, biến và converter. Có thể dùng object giả để quan sát khả năng truy cập mà không thử thao tác thật trên file, mạng hoặc dữ liệu sản xuất.

Đối với code SpEL minh họa, một bằng chứng quan trọng là source mà parser nhận luôn là literal được duyệt; những giá trị từ request không bao giờ được nối vào nó.

## 14. Telemetry và phản mẫu cần nhận diện

Một sự kiện từ chối có thể có dạng:

~~~json
{
  "event": "rule_rejected",
  "ruleId": "FILTER_17",
  "ruleVersion": "3",
  "contextProfile": "catalog-filter-v1",
  "reason": "UNSUPPORTED_OPERATOR",
  "requestId": "server-generated-id"
}
~~~

Các định danh, reason code và context profile phải lấy từ miền được kiểm soát, không dùng nguyên expression làm nhãn metric. Nếu cần lưu source để phục vụ duyệt rule, phải có quyền xem, thời hạn lưu và chính sách dữ liệu riêng.

Những phản mẫu cần tránh gồm:

**Chặn `${` rồi kết luận đã an toàn.** Raw expression có thể không dùng delimiter đó; parser còn có chế độ khác nhau.

**HTML-encode trước khi evaluate.** Encoding phải đúng bộ diễn giải đích; nó không biến việc đưa dữ liệu vào mã expression thành một thiết kế có ranh giới rõ ràng.

**Chỉ nhận expression từ database.** Cần biết ai viết database và qua đường nào, kể cả nội dung đã lưu từ lâu.

**Cấp một root object lớn cho tiện.** Một object có thể mở ra nhiều đối tượng và hành vi ngoài nhu cầu rule.

**Read-only đồng nghĩa không có tác dụng phụ.** Phải xem xét hành vi của object và accessor, không chỉ quyền gán field.

**Giới hạn chiều dài thay cho giới hạn khả năng.** Một biểu thức ngắn vẫn có thể thực hiện hành vi không được phép nếu context cho phép.

**Bọc mọi evaluation bằng timeout.** Timeout không tự bảo đảm công việc đã bị dừng hoặc không gây tác dụng phụ.

**Đánh giá lại khi lỗi bằng context quyền rộng hơn.** Fallback như vậy có thể làm mất chính sách ban đầu và khiến lỗi trở thành đường mở rộng quyền.

Phòng vệ expression injection bắt đầu từ quyết định ai được cung cấp mã biểu thức. Với phần lớn dữ liệu người dùng, yêu cầu đúng là giữ dữ liệu ở vai trò giá trị trong toàn bộ vòng đời. Khi hệ thống cần khả năng xây quy tắc, phải đặc tả riêng ngôn ngữ, quyền, context, ngân sách và tiêu chí nghiệm thu của khả năng đó.
