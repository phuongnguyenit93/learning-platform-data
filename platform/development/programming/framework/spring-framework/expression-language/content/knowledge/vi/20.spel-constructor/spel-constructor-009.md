# Đánh giá rủi ro khi expression tạo object hoặc tài nguyên

## Mục tiêu

Sau bài này, bạn có thể nhận diện những rủi ro khi Spring Expression Language (SpEL) tạo object hoặc tài nguyên trong lúc đánh giá biểu thức; phân biệt thời điểm parse với thời điểm constructor thực sự chạy; ước lượng tác động của cấp phát bộ nhớ và tác dụng phụ; và chọn cách giới hạn quyền tạo object trong EvaluationContext. Bạn cũng sẽ biết vì sao tài nguyên cần vòng đời quản lý rõ ràng, cách tránh tạo object lặp lại trong collection operation và cách kiểm soát biểu thức đến từ nguồn bên ngoài.

## 1. SpEL có thể tạo object bằng constructor

SpEL hỗ trợ toán tử `new` để gọi constructor của một lớp Java. Cú pháp cơ bản:

~~~text
new fully.qualified.ClassName(constructorArguments)
~~~

Ví dụ tạo một đối tượng ngày:

~~~text
new java.util.Date()
~~~

Với lớp trong gói `java.lang`, SpEL mặc định có thể tìm thấy tên lớp mà không cần viết đầy đủ package:

~~~text
new String('hello')
~~~

Với các lớp ở package khác, thông thường cần dùng tên lớp đầy đủ:

~~~text
new java.math.BigDecimal('125.50')
~~~

Constructor có thể nhận literal, biến, thuộc tính hoặc kết quả của biểu thức khác:

~~~text
new com.example.Invoice(#order.id, #order.total)
~~~

Điều này tiện khi biểu thức cần tạo một giá trị trung gian hoặc một DTO nhỏ. Tuy nhiên, constructor là mã Java thực sự. Khi được gọi, nó chạy logic trong constructor và có thể cấp phát bộ nhớ, gọi phương thức khác hoặc tạo tác dụng phụ.

Không nên coi `new` chỉ là cú pháp tạo dữ liệu vô hại. Mức rủi ro phụ thuộc vào lớp được tạo, constructor được gọi và các đối tượng mà constructor sử dụng.

## 2. Phân biệt parseExpression và getValue

Khi ứng dụng gọi:

~~~java
Expression expression =
    parser.parseExpression("new java.util.Date()");
~~~

SpEL phân tích chuỗi và tạo cấu trúc biểu thức. Việc parse không đồng nghĩa constructor đã chạy.

Constructor được gọi khi ứng dụng đánh giá biểu thức:

~~~java
Date created = expression.getValue(Date.class);
~~~

Nếu gọi `getValue(...)` nhiều lần, biểu thức constructor có thể tạo một instance mới ở mỗi lần đánh giá:

~~~java
Date first = expression.getValue(Date.class);
Date second = expression.getValue(Date.class);
~~~

Hai biến trên nhận kết quả từ hai lần đánh giá riêng. Không nên giả định SpEL lưu một object được tạo bởi constructor rồi dùng lại như singleton.

Sự khác biệt này quan trọng khi biểu thức được parse một lần nhưng đánh giá nhiều lần trong vòng đời ứng dụng. Việc cache đối tượng Expression giúp tránh parse lại; nó không tự biến object mà biểu thức tạo ra thành object dùng chung.

## 3. Constructor có thể có tác dụng phụ

Một constructor Java có thể chỉ khởi tạo các field, nhưng cũng có thể thực hiện công việc bên ngoài:

- Đọc hoặc ghi file.
- Mở stream hoặc kết nối mạng.
- Tạo kết nối hoặc client tới dịch vụ.
- Đăng ký listener hoặc callback.
- Cấp phát một cấu trúc dữ liệu lớn.
- Khởi tạo pool, bộ lập lịch hoặc tài nguyên cần đóng.
- Gọi một thành phần khác có tác dụng phụ.

Ví dụ, tạo một đối tượng `File` chỉ tạo object mô tả đường dẫn:

~~~text
new java.io.File(#path)
~~~

Constructor của `File` không tự tạo file trên đĩa. Ngược lại, constructor của `FileInputStream` mở file để đọc:

~~~text
new java.io.FileInputStream(#path)
~~~

Biểu thức thứ hai có thể mở một file ngay khi được đánh giá và có thể thất bại nếu file không tồn tại, quyền truy cập không đủ hoặc hệ thống gặp lỗi I/O.

Một số constructor khác có thể kết nối tới hệ thống bên ngoài hoặc giữ tài nguyên trong thời gian dài. Vì vậy, cần xem xét hành vi thực tế của lớp và constructor, không chỉ nhìn vào tên kiểu dữ liệu.

## 4. Rủi ro cấp phát bộ nhớ và CPU

Ngay cả constructor không có I/O cũng có thể tạo rủi ro nếu nó cấp phát quá nhiều bộ nhớ hoặc thực hiện công việc tốn CPU.

Ví dụ tạo một mảng:

~~~text
new int[1000]
~~~

Kích thước nhỏ có thể phù hợp. Nhưng nếu kích thước được lấy trực tiếp từ input:

~~~text
new byte[#requestedSize]
~~~

một giá trị rất lớn có thể gây tiêu thụ bộ nhớ quá mức, làm tăng thời gian garbage collection hoặc khiến ứng dụng hết bộ nhớ.

Tương tự, tạo nhiều object trong một biểu thức lặp có thể làm tăng số lần cấp phát. Nếu mỗi phần tử cần một object nặng, chi phí sẽ tăng theo kích thước collection.

Hãy kiểm tra giới hạn đầu vào ở Java trước khi truyền biến vào SpEL. Giới hạn số lượng, kích thước mảng, độ dài chuỗi và độ sâu cấu trúc dữ liệu phải xuất phát từ yêu cầu nghiệp vụ và khả năng của hệ thống.

## 5. Rủi ro khi tạo object trong selection hoặc projection

Selection và projection đánh giá biểu thức trên từng phần tử của collection. Nếu constructor nằm trong projection, nó có thể được gọi một lần cho mỗi phần tử được xử lý.

Ví dụ:

~~~text
#orders.![new com.example.OrderSummary(#this.id, #this.total)]
~~~

Với N đơn hàng, biểu thức có thể tạo N đối tượng OrderSummary. Đây có thể là cách hợp lý để tạo DTO nhỏ, nhưng sẽ tốn bộ nhớ theo số lượng phần tử.

Nếu constructor tạo tài nguyên, gọi dịch vụ hoặc thực hiện I/O, việc lặp qua collection có thể kích hoạt hàng loạt tác dụng phụ ngoài dự kiến.

Tránh đưa constructor nặng vào projection hoặc điều kiện được đánh giá nhiều lần. Hãy tạo dữ liệu tổng hợp trong Java khi cần kiểm soát số lần tạo, xử lý lỗi từng phần tử, tái sử dụng object hoặc giải phóng tài nguyên.

## 6. Mảng và cấu trúc dữ liệu có kích thước lớn

SpEL hỗ trợ tạo mảng bằng constructor-style array expression:

~~~text
new int[4]
~~~

Có thể tạo mảng với giá trị khởi tạo:

~~~text
new int[]{1, 2, 3}
~~~

Và mảng nhiều chiều:

~~~text
new int[2][3]
~~~

Kích thước mảng phải là giá trị phù hợp với kiểu dữ liệu và giới hạn bộ nhớ. Với kích thước lấy từ biến, hãy xác thực trước khi đánh giá:

~~~java
if (requestedSize < 0 || requestedSize > MAX_ARRAY_SIZE) {
    throw new IllegalArgumentException("Array size is out of range");
}
~~~

Không nên cho phép biểu thức tự quyết định kích thước không giới hạn dựa trên dữ liệu bên ngoài. Nếu cần mảng lớn, hãy cân nhắc cấu trúc dữ liệu, cách phân trang hoặc xử lý theo luồng trong Java.

## 7. Tài nguyên cần được quản lý vòng đời

Một object thông thường có thể được thu hồi khi không còn tham chiếu. Tài nguyên bên ngoài như file stream, socket, database connection hoặc executor có vòng đời riêng.

SpEL trả về object được constructor tạo ra, nhưng bản thân biểu thức không tự thiết kế một quy trình đóng tài nguyên sau khi sử dụng. Nếu biểu thức tạo một stream và ứng dụng không đóng nó, tài nguyên có thể bị giữ lâu hơn dự kiến.

Ví dụ, việc tạo stream:

~~~text
new java.io.FileInputStream(#path)
~~~

cần đi cùng thao tác đóng stream ở phía Java. Nên dùng try-with-resources:

~~~java
try (FileInputStream input =
         new FileInputStream(path)) {
    // Đọc dữ liệu và xử lý trong phạm vi này.
}
~~~

Đối với kết nối, client hoặc pool, cần xác định rõ ai sở hữu object, ai đóng nó và thời điểm đóng. Nếu tài nguyên cần được chia sẻ hoặc tái sử dụng, hãy để Spring quản lý bean theo lifecycle phù hợp thay vì tạo mới trong mỗi lần đánh giá SpEL.

## 8. Constructor có thể ném ngoại lệ

Constructor Java có thể thất bại do dữ liệu không hợp lệ, thiếu cấu hình, không đủ quyền hoặc lỗi hệ thống. Khi SpEL gọi constructor và constructor phát sinh lỗi, lần đánh giá biểu thức có thể thất bại với exception của SpEL hoặc exception được bọc từ quá trình gọi constructor.

Ví dụ:

~~~text
new java.math.BigDecimal(#amountText)
~~~

Nếu `#amountText` không phải chuỗi số hợp lệ, việc tạo BigDecimal sẽ thất bại.

Các tình huống khác có thể gồm:

- Thiếu đối số hoặc sai kiểu đối số.
- Không tìm thấy constructor phù hợp.
- Không thể chuyển đổi đối số sang kiểu tham số.
- Constructor ném exception.
- Không thể tải hoặc truy cập lớp được yêu cầu.

Hãy xác thực dữ liệu và cấu hình trước khi đánh giá. Ở Java, bắt và xử lý lỗi ở ranh giới gọi biểu thức; ghi nhận đủ ngữ cảnh để xác định constructor hoặc dữ liệu nào gây lỗi. Không nên nuốt mọi exception rồi trả về một object mặc định nếu điều đó che giấu lỗi cấu hình.

## 9. Quyền tạo object phụ thuộc EvaluationContext

Khả năng tạo object không chỉ phụ thuộc cú pháp. Nó còn phụ thuộc loại EvaluationContext và cơ chế phân giải kiểu hoặc constructor.

`StandardEvaluationContext` cung cấp bộ phân giải constructor mặc định và hỗ trợ các tính năng SpEL đầy đủ hơn. Khi dùng context này, biểu thức có thể tham chiếu kiểu bằng `T(...)` và gọi constructor bằng `new` theo các resolver được cấu hình.

Ví dụ:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("new java.math.BigDecimal('10.25')");

BigDecimal amount =
    expression.getValue(context, BigDecimal.class);
~~~

`SimpleEvaluationContext` được thiết kế cho tập tính năng giới hạn, chẳng hạn data binding và truy cập property được chọn. Nó không hỗ trợ tham chiếu kiểu và constructor invocation như StandardEvaluationContext.

Nếu một biểu thức chỉ cần đọc thuộc tính, hãy dùng context giới hạn phù hợp. Đừng mở rộng sang StandardEvaluationContext chỉ để biểu thức có thể tạo tùy ý object nếu ứng dụng không có nhu cầu đó.

## 10. TypeLocator và ConstructorResolver

Trong StandardEvaluationContext, SpEL dùng TypeLocator để tìm lớp theo tên và ConstructorResolver để xác định constructor có thể gọi.

Có thể thay đổi TypeLocator:

~~~java
context.setTypeLocator(customTypeLocator);
~~~

Và cấu hình danh sách ConstructorResolver:

~~~java
context.setConstructorResolvers(customConstructorResolvers);
~~~

Những điểm mở rộng này cho phép ứng dụng kiểm soát lớp nào có thể được tham chiếu và constructor nào được phép gọi. Có thể xây dựng một TypeLocator hoặc ConstructorResolver theo allowlist cho các kiểu dữ liệu được phê duyệt.

Một allowlist cần được thiết kế cẩn thận:

1. Chỉ cho phép những lớp cần thiết cho biểu thức.
2. Chỉ cho phép constructor có tham số và hành vi đã hiểu rõ.
3. Không cho phép lớp có khả năng thực hiện I/O hoặc thay đổi trạng thái nếu không có yêu cầu rõ ràng.
4. Kiểm tra kiểu và kích thước đối số.
5. Kiểm thử cả trường hợp lớp hoặc constructor bị từ chối.

Không nên coi việc giới hạn tên package là đủ nếu trong package đó vẫn có lớp thực hiện tác dụng phụ. Chính sách nên dựa trên kiểu và hành vi được phép, không chỉ dựa trên chuỗi tên lớp.

## 11. Không đánh giá expression không đáng tin cậy với quyền rộng

Nếu người dùng có thể gửi chuỗi SpEL, họ có thể kiểm soát cú pháp mà parser đánh giá. Với context có quyền rộng, biểu thức có thể truy cập nhiều loại đối tượng và khả năng tạo object hơn dự kiến.

Rủi ro tăng khi kết hợp:

- Constructor invocation bằng `new`.
- Type reference bằng `T(...)`.
- Bean reference bằng `@beanName`.
- Method invocation trên object có quyền thực hiện hành động.
- Property accessor hoặc resolver tùy chỉnh có phạm vi rộng.

Không nên đánh giá expression không đáng tin cậy bằng StandardEvaluationContext được cấu hình mặc định rồi giả định rằng chỉ vì biểu thức đến từ một trường cấu hình nên nó an toàn.

Nếu cần cho phép người dùng viết công thức, hãy thiết kế một ngôn ngữ con có tập toán tử và dữ liệu cho phép rõ ràng, hoặc dùng SimpleEvaluationContext với khả năng cần thiết được bật có chủ đích. Không cung cấp bean, resolver, root object hoặc phương thức không liên quan.

## 12. Kiểm soát nguồn dữ liệu và đối số constructor

Constructor có thể nhận dữ liệu từ biến, property hoặc kết quả của lời gọi khác. Vì vậy, ngay cả khi lớp được phép tạo, đối số vẫn cần được kiểm soát.

Ví dụ:

~~~text
new com.example.ReportOptions(#format, #maxRows)
~~~

Ứng dụng cần kiểm tra:

- `#format` thuộc danh sách định dạng được hỗ trợ.
- `#maxRows` nằm trong giới hạn hợp lý.
- Các chuỗi không vượt giới hạn độ dài.
- Đối tượng đầu vào có đúng kiểu và trạng thái cần thiết.
- Không truyền đường dẫn, URL hoặc thông tin nhạy cảm nếu constructor không cần chúng.

Đừng nối trực tiếp dữ liệu người dùng vào tên lớp hoặc toàn bộ chuỗi expression. Hãy truyền dữ liệu qua biến trong EvaluationContext và kiểm tra trước khi đánh giá. Điều này giúp tách mã biểu thức khỏi dữ liệu đầu vào và dễ áp dụng validation hơn.

## 13. Auto-grow cũng có thể tạo object

Ngoài `new` tường minh, cấu hình SpEL có thể cho phép tự mở rộng tham chiếu null hoặc collection khi truy cập property/indexer.

`SpelParserConfiguration` có các tùy chọn như:

- `autoGrowNullReferences`: cho phép tạo đối tượng ở một số tham chiếu null khi cần tiếp tục truy cập.
- `autoGrowCollections`: cho phép mở rộng collection khi truy cập vị trí vượt kích thước hiện tại.
- `maximumAutoGrowSize`: giới hạn kích thước mở rộng tối đa.

Ví dụ cấu hình:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        true,
        true,
        128
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Cấu hình trên bật hai cơ chế auto-grow và giới hạn kích thước mở rộng tối đa theo giá trị được truyền vào. Hành vi cụ thể còn phụ thuộc kiểu property, collection và khả năng tạo phần tử.

Auto-grow có thể thuận tiện cho data binding, nhưng cũng làm thay đổi object graph trong lúc đánh giá. Chỉ bật khi cần, đặt giới hạn rõ ràng và không cho phép kích thước tăng theo input không được kiểm soát.

## 14. So sánh các cách tạo và quản lý object

| Cách làm | Khi phù hợp | Điều cần kiểm soát |
|---|---|---|
| `new` trong SpEL | Tạo giá trị nhỏ, đơn giản, constructor thuần | Kiểu được phép, số lần đánh giá, đối số |
| Tạo DTO trong Java | Cần validation, nhiều bước hoặc kiểu rõ ràng | Constructor và logic nghiệp vụ |
| Spring bean được inject | Object dùng chung hoặc có lifecycle | Scope, cấu hình và quyền gọi phương thức |
| Factory method do ứng dụng kiểm soát | Cần quy tắc tạo tập trung | Allowlist đầu vào và hành vi factory |
| Tạo tài nguyên trong Java với try-with-resources | File, stream hoặc tài nguyên có thời hạn | Đóng tài nguyên và xử lý exception |

SpEL phù hợp với biểu thức khai báo ngắn. Java và Spring container phù hợp hơn khi cần quản lý vòng đời, transaction, cleanup, retry, logging hoặc xử lý lỗi chi tiết.

## 15. Ví dụ: dùng constructor cho DTO đơn giản

Giả sử một DTO chỉ lưu mã và tổng tiền, constructor không thực hiện I/O hoặc thay đổi trạng thái bên ngoài:

~~~java
public class OrderSummary {
    private final String id;
    private final BigDecimal total;

    public OrderSummary(String id, BigDecimal total) {
        this.id = id;
        this.total = total;
    }

    public String getId() {
        return id;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Có thể tạo DTO từ root object:

~~~text
new com.example.OrderSummary(id, total)
~~~

Hoặc tạo một DTO cho mỗi đơn hàng trong projection:

~~~text
#orders.![new com.example.OrderSummary(#this.id, #this.total)]
~~~

Cách này có thể phù hợp với collection nhỏ và constructor đơn giản. Nếu collection lớn, cần xử lý lỗi riêng từng phần tử hoặc DTO cần validation phức tạp, hãy tạo kết quả trong Java để kiểm soát việc cấp phát và lỗi rõ ràng hơn.

## 16. Checklist trước khi cho phép constructor invocation

Trước khi bật khả năng tạo object trong một biểu thức, hãy trả lời:

1. Lớp nào được phép tạo?
2. Constructor nào có thể được gọi?
3. Constructor có đọc/ghi file, mở kết nối hoặc gọi dịch vụ không?
4. Object được tạo sẽ được dùng trong bao lâu?
5. Ai chịu trách nhiệm đóng hoặc giải phóng tài nguyên?
6. Biểu thức được đánh giá bao nhiêu lần và trên bao nhiêu phần tử?
7. Đối số có giới hạn kích thước, kiểu và giá trị không?
8. Biểu thức có đến từ người dùng hoặc nguồn không đáng tin cậy không?
9. Có thể tạo object trong Java hoặc inject bean thay thế không?
10. Có thể giới hạn TypeLocator hoặc ConstructorResolver theo allowlist không?

Nếu không thể xác định rõ hành vi và vòng đời của object, không nên để SpEL tự tạo object đó.

## 17. Kiểm thử rủi ro tạo object

Kiểm thử nên xác nhận cả kết quả lẫn số lần tạo và hành vi phụ:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Constructor đơn giản | Đúng kiểu và giá trị field |
| Hai lần getValue | Xác nhận có thể tạo hai instance riêng |
| Đối số null | Hành vi đúng với hợp đồng constructor |
| Đối số sai kiểu | Lỗi chuyển đổi hoặc constructor được báo rõ |
| Constructor ném exception | Lỗi được xử lý ở ranh giới gọi biểu thức |
| Kích thước mảng lớn | Bị giới hạn trước khi cấp phát |
| Constructor mở tài nguyên | Tài nguyên được đóng đúng cách |
| Projection trên collection | Số object tạo tương ứng số phần tử được xử lý |
| Lớp không nằm trong allowlist | Constructor bị từ chối |
| SimpleEvaluationContext | Constructor invocation không được hỗ trợ |
| Auto-grow | Object/collection chỉ được mở rộng trong giới hạn đã cấu hình |

Với constructor có tác dụng phụ, hãy dùng test double hoặc môi trường kiểm thử cô lập. Không chạy kiểm thử tạo kết nối, ghi file hoặc cấp phát lớn trên môi trường production.

## 18. Ghi nhớ

SpEL có thể tạo object bằng `new` và tạo mảng bằng cú pháp array construction. Việc parse expression chỉ xây dựng cấu trúc biểu thức; constructor chạy khi getValue đánh giá. Mỗi lần đánh giá có thể tạo instance mới, vì vậy biểu thức được gọi lặp lại có thể phát sinh nhiều lần cấp phát.

Constructor là mã Java và có thể thực hiện I/O, mở tài nguyên, gọi hệ thống bên ngoài hoặc tiêu thụ nhiều bộ nhớ/CPU. SpEL không tự quản lý vòng đời đóng tài nguyên cho object được tạo. Tài nguyên như stream, socket và connection nên được quản lý trong Java hoặc bởi Spring container.

StandardEvaluationContext hỗ trợ constructor invocation thông qua cơ chế phân giải kiểu và constructor. SimpleEvaluationContext không cung cấp khả năng tạo object này. Khi cần dùng constructor, hãy giới hạn TypeLocator/ConstructorResolver, kiểm tra đối số, số lần đánh giá và tác dụng phụ; không đánh giá expression không đáng tin cậy với quyền rộng.

Dùng `new` cho object nhỏ, thuần và có hành vi dự đoán được. Với tài nguyên, logic tạo phức tạp, cleanup hoặc object có lifecycle dài, hãy để Java và Spring quản lý việc khởi tạo và giải phóng.

## Tài liệu tham khảo

- [Spring Framework Reference — Constructors](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)