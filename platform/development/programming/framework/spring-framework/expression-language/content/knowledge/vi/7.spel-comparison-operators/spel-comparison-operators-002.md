# So sánh lớn hơn, nhỏ hơn và các biến thể có bằng

Trong Spring Expression Language (SpEL), các toán tử **lớn hơn**, **nhỏ hơn**, **lớn hơn hoặc bằng** và **nhỏ hơn hoặc bằng** dùng để so sánh hai giá trị và trả về kết quả Boolean. Chúng thường xuất hiện trong điều kiện nghiệp vụ, cấu hình bean, biểu thức cache hoặc các điểm tích hợp như Spring Security.

Bốn toán tử tương ứng là **>**, **<**, **>=** và **<=**. Điểm cần chú ý là kiểu dữ liệu của hai toán hạng phải hỗ trợ phép so sánh. Một biểu thức có cú pháp hợp lệ vẫn có thể thất bại khi đánh giá nếu dữ liệu thực tế không thể so sánh theo quy tắc của SpEL.

## Bốn toán tử quan hệ

| Toán tử | Ý nghĩa | Ví dụ | Kết quả |
|---|---|---|---|
| **>** | Lớn hơn | **10 > 5** | true |
| **<** | Nhỏ hơn | **3 < 8** | true |
| **>=** | Lớn hơn hoặc bằng | **10 >= 10** | true |
| **<=** | Nhỏ hơn hoặc bằng | **5 <= 4** | false |

Hai toán tử **>** và **<** là so sánh nghiêm ngặt: hai giá trị bằng nhau thì kết quả false. Hai toán tử **>=** và **<=** bao gồm trường hợp bằng nhau.

Ví dụ đánh giá trực tiếp:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean greater = parser.parseExpression("10 > 5")
        .getValue(Boolean.class);

Boolean less = parser.parseExpression("3 < 8")
        .getValue(Boolean.class);

Boolean greaterOrEqual = parser.parseExpression("10 >= 10")
        .getValue(Boolean.class);

Boolean lessOrEqual = parser.parseExpression("5 <= 4")
        .getValue(Boolean.class);
~~~

Mỗi biểu thức trả về một Boolean. Có thể dùng kết quả này để quyết định nhánh xử lý trong Java hoặc để Spring đánh giá điều kiện tại một điểm tích hợp hỗ trợ SpEL.

## So sánh số nguyên và số thực

Khi hai toán hạng là số, SpEL thực hiện so sánh theo giá trị số. Kiểu số có thể đến từ literal, property của root object hoặc biến trong EvaluationContext.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean result1 =
        parser.parseExpression("100 > 80")
                .getValue(Boolean.class);

Boolean result2 =
        parser.parseExpression("19.5 <= 20.0")
                .getValue(Boolean.class);

Boolean result3 =
        parser.parseExpression("10 >= 10.0")
                .getValue(Boolean.class);
~~~

Ví dụ thứ ba minh họa việc so sánh một literal nguyên với một literal thập phân. SpEL hỗ trợ so sánh các giá trị số có kiểu khác nhau thông qua cơ chế so sánh số của nó.

Với dữ liệu lấy từ object, hãy để kiểu property phản ánh đúng ý nghĩa dữ liệu. Một giá trị số được lưu dưới dạng String không nên được xem như số chỉ vì nội dung của nó trông giống số. Hãy chuyển đổi và xác thực dữ liệu tại ranh giới đầu vào trước khi đánh giá biểu thức.

## Dùng toán tử so sánh với root object

Trong ứng dụng, ngưỡng so sánh thường được áp dụng lên một thuộc tính của object. Ví dụ, kiểm tra điểm của học viên có đạt mức tối thiểu hay không:

~~~java
public class ExamResult {
    private final String studentName;
    private final int score;

    public ExamResult(String studentName, int score) {
        this.studentName = studentName;
        this.score = score;
    }

    public String getStudentName() {
        return studentName;
    }

    public int getScore() {
        return score;
    }
}
~~~

~~~java
ExamResult result = new ExamResult("An", 85);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("score >= 80");

Boolean passed =
        expression.getValue(result, Boolean.class);
~~~

Ở đây, **result** là root object. SpEL đọc property **score**, so sánh với literal 80 và trả về true. Nếu điểm là 79, cùng biểu thức sẽ trả về false.

Biểu thức có thể được parse một lần rồi đánh giá trên nhiều đối tượng:

~~~java
Expression passedExpression =
        parser.parseExpression("score >= 80");

for (ExamResult item : results) {
    Boolean passed =
            passedExpression.getValue(item, Boolean.class);
    // Xử lý kết quả
}
~~~

Literal 80 giữ nguyên giá trị trong mọi lần đánh giá, còn property score thay đổi theo root object. Do đó, kết quả Boolean có thể khác nhau giữa các học viên.

## Dùng biến làm ngưỡng so sánh

Nếu ngưỡng thay đổi theo cấu hình hoặc từng yêu cầu, không nên ghi cứng nó trong chuỗi biểu thức. Có thể đưa ngưỡng vào EvaluationContext dưới dạng biến:

~~~java
ExamResult result = new ExamResult("An", 85);

StandardEvaluationContext context =
        new StandardEvaluationContext(result);

context.setVariable("passingScore", 80);

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("score >= #passingScore");

Boolean passed =
        expression.getValue(context, Boolean.class);
~~~

Dấu **#** dùng để tham chiếu biến trong evaluation context. Property **score** được lấy từ root object, còn **#passingScore** lấy từ biến mà ứng dụng đã cung cấp.

Cách này tách quy tắc so sánh khỏi giá trị ngưỡng. Cùng một Expression có thể được tái sử dụng với các context có ngưỡng khác nhau, miễn là dữ liệu và kiểu của biến phù hợp.

## So sánh chuỗi

String trong Java triển khai Comparable, vì vậy SpEL có thể thực hiện các phép so sánh quan hệ trên hai chuỗi tương thích. Việc so sánh theo thứ tự tự nhiên của String là so sánh từ điển theo giá trị ký tự, không phải so sánh ngữ nghĩa như thứ tự phiên bản hay ngày tháng.

~~~java
Boolean result =
        parser.parseExpression("'apple' < 'banana'")
                .getValue(Boolean.class);
~~~

Kết quả là true theo thứ tự so sánh chuỗi. Tuy nhiên, chữ hoa và chữ thường có giá trị khác nhau trong phép so sánh này. Ví dụ, không nên dùng trực tiếp phép so sánh String để xác định tên người dùng nào “lớn hơn” theo ngôn ngữ tự nhiên.

Nếu cần so sánh không phân biệt hoa thường, chuẩn hóa dữ liệu trước hoặc dùng một phương thức so sánh được ứng dụng kiểm soát. Nếu so sánh phiên bản, ngày tháng hoặc mã nghiệp vụ có quy tắc riêng, hãy chuyển dữ liệu sang kiểu có semantics phù hợp thay vì dựa vào thứ tự ký tự.

## Kết hợp nhiều điều kiện

Các toán tử quan hệ thường được kết hợp với toán tử logic để tạo điều kiện có nhiều ngưỡng:

~~~java
Expression expression = parser.parseExpression(
        "score >= 80 and score <= 100");
~~~

Biểu thức trên kiểm tra score nằm trong đoạn từ 80 đến 100, bao gồm cả hai đầu mút.

Có thể viết điều kiện phân loại:

~~~java
Expression expression = parser.parseExpression(
        "age >= 18 and age < 65");
~~~

Điều kiện đúng khi age từ 18 trở lên và nhỏ hơn 65. Sự khác nhau giữa **<** và **<=** quyết định chính xác giá trị biên có được chấp nhận hay không.

Khi kết hợp nhiều toán tử, có thể dùng dấu ngoặc để làm rõ nhóm điều kiện:

~~~java
"active == true and (score >= 80 or bonus >= 10)"
~~~

Dấu ngoặc làm rõ rằng chỉ cần score đạt ngưỡng hoặc bonus đạt ngưỡng, đồng thời active phải đúng.

## Xử lý giá trị null

Không nên giả định rằng null có thể được so sánh lớn hơn hoặc nhỏ hơn như một số thông thường. Nếu property có thể null, hãy kiểm tra null rõ ràng trước khi thực hiện phép so sánh:

~~~java
Expression expression = parser.parseExpression(
        "score != null and score >= 80");
~~~

Biểu thức kiểm tra score khác null rồi mới áp dụng ngưỡng. Cách này giúp thể hiện điều kiện nghiệp vụ rõ ràng và tránh lỗi evaluation do dữ liệu thiếu.

Nếu giá trị null có ý nghĩa riêng, hãy quyết định chính sách trong ứng dụng: xem như không đạt, bỏ qua bản ghi hay trả về trạng thái chưa xác định. Không nên để hành vi null ngầm định thay thế cho quy tắc nghiệp vụ.

## Kiểu dữ liệu không tương thích

Các phép toán quan hệ cần hai toán hạng có thể so sánh được. Với kiểu số, SpEL dùng quy tắc so sánh số. Với các kiểu đối tượng khác, việc so sánh thường dựa trên khả năng so sánh của kiểu, chẳng hạn Comparable và tính tương thích giữa hai toán hạng.

Ví dụ, so sánh một số với một chuỗi chứa chữ số không có nghĩa là SpEL luôn tự hiểu chuỗi đó là số:

~~~java
Expression expression =
        parser.parseExpression("score > '80'");
~~~

Không nên dựa vào phép chuyển đổi ngầm để xử lý dữ liệu không đồng nhất. Nếu một phía là String và phía còn lại là Integer, biểu thức có thể không đánh giá được vì hai toán hạng không tương thích với phép so sánh đang thực hiện.

Hãy chuyển đổi dữ liệu sang cùng một kiểu trước khi đánh giá:

~~~java
Integer score = Integer.valueOf(inputScore);

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("score", score);
context.setVariable("threshold", 80);

Expression expression =
        parser.parseExpression("#score > #threshold");

Boolean aboveThreshold =
        expression.getValue(context, Boolean.class);
~~~

Việc chuyển đổi và xác thực đầu vào trong Java giúp biểu thức SpEL tập trung vào quy tắc so sánh, đồng thời làm lỗi dữ liệu dễ chẩn đoán hơn.

## So sánh BigDecimal và các giá trị cần độ chính xác

Với dữ liệu tài chính, có thể dùng BigDecimal làm toán hạng. SpEL hỗ trợ so sánh các giá trị số theo giá trị số học của chúng:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("price", new BigDecimal("100.00"));
context.setVariable("limit", new BigDecimal("100.0"));

Expression expression =
        parser.parseExpression("#price >= #limit");

Boolean withinLimit =
        expression.getValue(context, Boolean.class);
~~~

Hai giá trị BigDecimal trên bằng nhau về mặt số học dù scale khác nhau. Đây là điểm cần phân biệt với việc gọi trực tiếp **BigDecimal.equals(...)** trong Java, vốn còn xét scale. Khi cần quy tắc chính xác cho tiền tệ, hãy xác định rõ scale, rounding mode và điều kiện biên của nghiệp vụ.

Với Float và Double, sai số biểu diễn dấu phẩy động có thể khiến một giá trị nằm rất gần ngưỡng nhưng không đúng bằng ngưỡng mong đợi. Nếu điều kiện phụ thuộc ranh giới chính xác, nên dùng BigDecimal hoặc chuẩn hóa giá trị theo quy tắc nghiệp vụ trước khi so sánh.

## So sánh ngày tháng và các kiểu Comparable

Các kiểu dữ liệu có thứ tự tự nhiên, chẳng hạn một số lớp ngày giờ Java, có thể được so sánh nếu hai toán hạng tương thích với cơ chế so sánh của SpEL. Ví dụ, một property kiểu LocalDate có thể được so sánh với một biến LocalDate khác để kiểm tra hạn:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable(
        "deadline",
        LocalDate.of(2026, 12, 31));

Expression expression =
        parser.parseExpression("deliveryDate <= #deadline");

Boolean onTime =
        expression.getValue(context, Boolean.class);
~~~

Biểu thức so sánh deliveryDate với deadline. Cả hai cần là kiểu ngày tương thích. Không nên so sánh ngày tháng đã chuyển thành chuỗi tùy ý vì thứ tự ký tự của định dạng chuỗi không phải lúc nào cũng trùng thứ tự thời gian.

Với các kiểu tùy chỉnh, nếu muốn dùng toán tử quan hệ, cần bảo đảm kiểu có quy tắc so sánh phù hợp. Không nên tạo một Comparable có thứ tự không nhất quán với ý nghĩa nghiệp vụ rồi mong biểu thức tự hiểu quy tắc đó.

## Kiểm tra kiểu và xử lý lỗi

Một biểu thức so sánh có thể parse thành công nhưng thất bại khi evaluate nếu property không tồn tại, giá trị null ở vị trí không hợp lệ hoặc hai toán hạng không tương thích.

Có thể tách lỗi parse và lỗi evaluation:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("score >= #passingScore");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    Boolean passed =
            expression.getValue(context, Boolean.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException("Cannot compare values", ex);
}
~~~

ParseException cho biết chuỗi biểu thức không hợp lệ về cú pháp. EvaluationException cho biết biểu thức không thể được đánh giá trong context hoặc trên dữ liệu hiện tại. Khi xử lý lỗi, nên ghi nhận mã biểu thức, loại dữ liệu và ngữ cảnh cần thiết; tránh ghi toàn bộ object nếu có thông tin nhạy cảm.

## Khi nào nên dùng toán tử quan hệ trong SpEL?

Các toán tử quan hệ phù hợp với những điều kiện ngắn, dễ đọc và có dữ liệu đầu vào rõ ràng, chẳng hạn:

- Kiểm tra một giá trị có vượt ngưỡng cấu hình hay không.
- Kiểm tra số lượng, điểm, giá hoặc tỷ lệ nằm trong một khoảng.
- Kiểm tra thời điểm hiện tại có trước hoặc sau một mốc thời gian.
- Kết hợp nhiều điều kiện để bật/tắt một hành vi tại điểm tích hợp Spring hỗ trợ SpEL.

Nếu quy tắc có nhiều nhánh, nhiều kiểu dữ liệu, chính sách null phức tạp hoặc cần giải thích lý do từ chối, nên chuyển phần quyết định vào một phương thức Java có tên rõ ràng. Biểu thức SpEL nên thể hiện điều kiện ngắn gọn mà người đọc có thể hiểu ngay.

## Kết luận

SpEL cung cấp bốn toán tử quan hệ **>**, **<**, **>=** và **<=** để so sánh số, chuỗi và các kiểu dữ liệu có quy tắc so sánh tương thích. Hai toán tử đầu loại trừ trường hợp bằng nhau; hai toán tử sau bao gồm giá trị biên. Biểu thức có thể đọc dữ liệu từ root object, biến trong EvaluationContext hoặc literal.

Để kết quả dễ dự đoán, hãy chuẩn hóa kiểu dữ liệu trước khi so sánh, kiểm tra null rõ ràng và chú ý độ chính xác của số thực. Với điều kiện có nhiều ngưỡng, dấu ngoặc và toán tử logic giúp biểu thức dễ đọc. Khi quy tắc trở nên phức tạp, đưa logic vào Java sẽ giúp kiểm thử và chẩn đoán dễ hơn.
