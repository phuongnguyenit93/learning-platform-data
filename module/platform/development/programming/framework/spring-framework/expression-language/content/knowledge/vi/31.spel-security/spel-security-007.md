# Kiểm tra độ dài, cú pháp và tài nguyên của expression trong SpEL

## 1. Vì sao phải giới hạn expression?

Spring Expression Language (SpEL) có thể đọc property, gọi method, tạo object, truy cập collection, thực hiện phép toán và tham chiếu bean tùy theo EvaluationContext. Sự linh hoạt này hữu ích cho cấu hình và quy tắc nghiệp vụ, nhưng một expression quá dài, quá phức tạp hoặc được đánh giá trên object graph rộng có thể tiêu tốn CPU, bộ nhớ và thời gian xử lý.

Khi expression đến từ cấu hình hoặc nguồn bên ngoài, cần kiểm soát ít nhất ba khía cạnh:

1. **Độ dài và cấu trúc:** giới hạn kích thước đầu vào và độ phức tạp cú pháp trước khi parse.
2. **Tài nguyên khi đánh giá:** giới hạn số thao tác, kích thước kết quả số lớn và khả năng tự mở rộng collection.
3. **Quyền truy cập:** giới hạn object, property, method, function và bean mà expression có thể chạm tới.

Một giới hạn parser không thay thế kiểm soát quyền truy cập. Expression ngắn vẫn có thể gọi method tốn kém hoặc có side effect; expression hợp cú pháp vẫn có thể không an toàn nếu được đánh giá trên object có quyền quá rộng.

## 2. Tách parse khỏi evaluation

SpEL có hai giai đoạn chính:

- `ExpressionParser.parseExpression(...)` phân tích chuỗi và tạo đối tượng Expression.
- `Expression.getValue(...)` đánh giá expression trên root object và EvaluationContext.

Ví dụ:

```java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("age >= 18");

boolean allowed = expression.getValue(
        customer, Boolean.class);
```

Nếu cú pháp sai, lỗi xuất hiện trong giai đoạn parse. Nếu cú pháp hợp lệ nhưng property không tồn tại, kiểu dữ liệu không phù hợp hoặc method không thể gọi, lỗi xuất hiện trong giai đoạn evaluation.

| Giai đoạn | API | Loại lỗi thường gặp | Ý nghĩa |
|---|---|---|---|
| Parse | `parseExpression()` | `ParseException`, thường là `SpelParseException` | Chuỗi không tuân theo grammar hoặc vượt giới hạn parse. |
| Evaluate | `getValue()` | `EvaluationException`, thường là `SpelEvaluationException` | Không thể đọc property, gọi method, chuyển kiểu hoặc thực hiện phép toán. |

Parse thành công chỉ chứng minh expression hợp cú pháp và parser chấp nhận nó. Parse không chứng minh expression có thể đánh giá trên dữ liệu thật, đáp ứng nghiệp vụ hay an toàn.

## 3. Giới hạn độ dài expression

Trong Spring Framework hiện hành, độ dài expression SpEL mặc định không vượt quá **10.000 ký tự**. Giới hạn này giúp ngăn chuỗi đầu vào quá lớn làm tăng chi phí parse và lưu trữ AST.

Khi tạo parser bằng code, cấu hình giới hạn riêng bằng `SpelParserConfiguration`:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .maximumExpressionLength(2_000)
                .build();

ExpressionParser parser =
        new SpelExpressionParser(config);
```

Ví dụ trên đặt giới hạn 2.000 ký tự cho các expression được parser đó xử lý. Chọn giá trị theo ngôn ngữ expression mà ứng dụng thực sự cho phép; không tăng giới hạn chỉ để một expression bất thường được chấp nhận.

Với expression được xử lý bên trong ApplicationContext, chẳng hạn trong XML bean definition hoặc `@Value`, có thể cấu hình Spring property:

```properties
spring.context.expression.maxLength=2000
```

Property này có thể được cung cấp qua JVM system property hoặc cơ chế SpringProperties. Với parser do ứng dụng tự tạo, ưu tiên cấu hình trực tiếp trên parser để phạm vi ảnh hưởng rõ ràng.

Nên kiểm tra kích thước đầu vào ở ranh giới request trước khi gọi parser. Giới hạn trong SpEL là lớp bảo vệ bổ sung; tầng HTTP/API vẫn cần giới hạn payload và số lượng expression mà một request được phép gửi.

## 4. Giới hạn số thao tác khi evaluation

Từ Spring Framework 6.2.19 và 7.0.8, SpEL giới hạn số thao tác được thực hiện trong một lần đánh giá expression. Giá trị mặc định hiện hành là **10.000 thao tác**. Khi vượt ngưỡng, evaluation dừng và ném lỗi SpEL.

Cấu hình qua parser:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .maximumOperations(500)
                .build();

ExpressionParser parser =
        new SpelExpressionParser(config);
```

Ví dụ giới hạn 500 thao tác cho mỗi lần evaluation bằng parser này. Chọn ngưỡng dựa trên các expression hợp lệ của ứng dụng và đo với dữ liệu đại diện.

Nếu không thể cấu hình parser trực tiếp, có thể đặt Spring/JVM property:

```properties
spring.expression.maxOperations=500
```

Giới hạn này hữu ích cho expression có nhiều node, phép toán hoặc thao tác lặp. Tuy nhiên, nó không phải timeout tổng quát cho toàn bộ chương trình Java. Một method tùy chỉnh có thể thực hiện vòng lặp dài, gọi database, truy cập mạng hoặc chờ lock bên trong một lần gọi; bộ đếm thao tác của SpEL không đo hết chi phí nội bộ của method đó.

Vì vậy, hãy tránh expose method tốn kém cho expression, đặt timeout ở các API bên ngoài nếu cần và giới hạn concurrency tại tầng thực thi.

## 5. Giới hạn kết quả BigInteger và BigDecimal của phép lũy thừa

Phép lũy thừa với `BigInteger` hoặc `BigDecimal` có thể tạo kết quả rất lớn, tiêu tốn nhiều CPU và bộ nhớ. Spring Framework 7.0.9 trở lên giới hạn kích thước kết quả của phép power trong SpEL ở mức mặc định **1.000.000 bit**.

Có thể cấu hình bằng parser:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .maximumBigPowerBits(8_192)
                .build();

ExpressionParser parser =
        new SpelExpressionParser(config);
```

Ví dụ đặt giới hạn kết quả 8.192 bit. Nếu phép tính có thể vượt giới hạn, SpEL dừng với lỗi evaluation thay vì tạo kết quả không giới hạn.

Có thể cấu hình qua Spring/JVM property:

```properties
spring.expression.maxBigPowerBits=8192
```

Không đặt `Integer.MAX_VALUE` chỉ để bỏ giới hạn trong môi trường nhận expression từ nguồn không tin cậy. Việc cho phép kết quả số rất lớn có thể làm tăng đột biến thời gian và bộ nhớ.

Giới hạn này chỉ áp dụng cho kết quả của phép power với BigInteger/BigDecimal. Nó không giới hạn mọi phép toán số, mọi chuỗi lớn hoặc mọi method được gọi từ expression.

## 6. Giới hạn tự mở rộng collection và null reference

SpEL có thể được cấu hình để tự tạo object khi property trung gian null hoặc tự mở rộng collection khi index vượt kích thước hiện tại. Tính năng này hữu ích cho data binding, nhưng có thể làm thay đổi object và cấp phát thêm bộ nhớ.

Hai tùy chọn liên quan:

- `autoGrowNullReferences()`: cho phép tự tạo null reference trong property path.
- `autoGrowCollections()`: cho phép tự mở rộng collection và array khi truy cập index.

Trong builder hiện hành, cả hai tính năng đều tắt mặc định. Nếu thật sự cần auto-grow collection, hãy đặt giới hạn kích thước:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .autoGrowCollections()
                .maximumAutoGrowSize(64)
                .build();

ExpressionParser parser =
        new SpelExpressionParser(config);
```

Khi đó, collection hoặc array được phép tự mở rộng nhưng không vượt quá 64 phần tử. `maximumAutoGrowSize` chỉ có tác dụng khi auto-grow được bật.

Builder hiện hành mặc định giới hạn auto-grow ở 256 phần tử. Lưu ý các constructor cũ của `SpelParserConfiguration` có thể dùng mặc định `Integer.MAX_VALUE` vì lý do tương thích ngược. Ưu tiên builder và đặt giới hạn rõ ràng nếu ứng dụng cho phép expression ghi dữ liệu hoặc tự mở rộng collection.

Nếu expression chỉ cần đọc dữ liệu, hãy giữ auto-grow tắt và dùng context chỉ đọc phù hợp.

## 7. Các bảo vệ bổ sung cho chuỗi, regex và array

Ngoài các giới hạn cấu hình chính, SpEL có các kiểm tra nội bộ đối với một số thao tác có thể tạo dữ liệu lớn hoặc tốn kém, bao gồm:

- Kích thước chuỗi được tạo bằng phép lặp.
- Kích thước chuỗi sau khi nối.
- Độ dài regex dùng với toán tử `matches`.
- Số phần tử được khai báo khi tạo array.
- Một số regex được nhận diện là khó đánh giá hiệu quả.

Các trường hợp vượt ngưỡng có thể phát sinh thông báo như `MAX_REPEATED_TEXT_SIZE_EXCEEDED`, `MAX_CONCATENATED_STRING_LENGTH_EXCEEDED`, `MAX_REGEX_LENGTH_EXCEEDED`, `MAX_ARRAY_ELEMENTS_THRESHOLD_EXCEEDED` hoặc `FLAWED_PATTERN`.

Ngưỡng và hành vi chi tiết phụ thuộc phiên bản Spring. Không nên dựa vào các kiểm tra nội bộ này như một giới hạn thời gian thực thi tổng quát. Đặc biệt, regex có thể gây chi phí lớn khi áp dụng lên chuỗi dài; không nhận regex tùy ý từ người dùng nếu chưa có chính sách kiểm soát pattern và dữ liệu đầu vào.

Nếu nghiệp vụ cần tìm kiếm theo regex, ưu tiên pattern được ứng dụng định nghĩa hoặc allow-list các pattern đã kiểm soát. Giới hạn cả độ dài chuỗi cần so khớp và tần suất thực hiện.

## 8. Cấu hình nhiều giới hạn cùng lúc

Có thể cấu hình các giới hạn chính trong một parser:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .maximumExpressionLength(2_000)
                .maximumOperations(500)
                .maximumBigPowerBits(8_192)
                .maximumAutoGrowSize(64)
                .build();

ExpressionParser parser =
        new SpelExpressionParser(config);
```

Trong cấu hình này:

- Expression dài tối đa 2.000 ký tự.
- Mỗi lần evaluation có tối đa 500 thao tác.
- Kết quả power của BigInteger/BigDecimal không vượt 8.192 bit.
- Nếu sau này bật collection auto-grow, kích thước tự mở rộng tối đa là 64 phần tử.
- Auto-grow vẫn tắt vì không gọi `autoGrowCollections()` hoặc `autoGrowNullReferences()`.

Đây là ví dụ giới hạn minh họa. Giá trị production cần dựa trên biểu thức hợp lệ, dữ liệu thật, độ trễ cho phép và tài nguyên triển khai. Giới hạn quá thấp có thể từ chối cả expression hợp lệ; giới hạn quá cao làm giảm tác dụng bảo vệ.

## 9. Parse để kiểm tra cú pháp trước khi lưu expression

Nếu ứng dụng cho phép administrator cấu hình expression, có thể parse ngay khi nhận cấu hình để phát hiện lỗi cú pháp trước khi expression được dùng trong request thật.

Ví dụ:

```java
public Expression parseConfiguredRule(
        String source,
        ExpressionParser parser) {

    if (source == null || source.isBlank()) {
        throw new IllegalArgumentException(
                "Expression must not be empty");
    }

    return parser.parseExpression(source);
}
```

Caller nên bắt `ParseException` và báo lỗi cấu hình có vị trí hoặc thông điệp cụ thể. Không cần gọi `getValue()` chỉ để kiểm tra cú pháp, vì evaluation có thể gọi getter/method, thay đổi state hoặc truy cập hệ thống.

Nếu cần kiểm tra khả năng chạy trên một model mẫu, hãy dùng dữ liệu test biệt lập và EvaluationContext có quyền tối thiểu. Không chạy thử expression tùy ý trên production object chỉ để xem nó có hoạt động hay không.

Parse expression một lần rồi tái sử dụng khi cùng một expression được đánh giá lặp lại trong cùng phạm vi bảo mật và cấu hình tương đương. Không dùng chung một Expression đã parse giữa context có mức quyền khác nhau; AST có thể cache accessor hoặc executor từ lần đánh giá trước.

## 10. Giới hạn cú pháp bằng grammar và allow-list

Giới hạn độ dài không đồng nghĩa giới hạn được cú pháp. Một expression ngắn vẫn có thể dùng constructor, type reference, bean reference, method invocation hoặc phép gán nếu EvaluationContext cho phép.

Nếu nghiệp vụ chỉ cần điều kiện như:

```text
age >= 18 and country == 'VN'
```

hãy xác định rõ tập cú pháp ứng dụng chấp nhận, ví dụ:

- Chỉ cho phép một danh sách property đã biết.
- Chỉ cho phép toán tử so sánh và logic được hỗ trợ.
- Chỉ cho phép literal thuộc kiểu đã quy định.
- Không cho phép constructor, type reference, bean reference, assignment hoặc method call nếu không cần.
- Giới hạn số điều kiện, số toán tử và độ sâu biểu thức ở tầng ứng dụng.

Không dùng một regex đơn giản để cố lọc mọi cú pháp SpEL nguy hiểm. Grammar SpEL có nhiều dạng lồng nhau, escape, literal và toán tử; blacklist theo chuỗi dễ bỏ sót trường hợp. Nếu cần expression do người dùng tự định nghĩa, cân nhắc một DSL nhỏ với grammar riêng rồi chuyển DSL đó thành biểu thức đã kiểm soát.

## 11. EvaluationContext là ranh giới bảo mật quan trọng

Spring phân biệt hai loại context chính:

| Context | Đặc điểm |
|---|---|
| `StandardEvaluationContext` | Cung cấp toàn bộ tính năng SpEL, bao gồm truy cập method, constructor, type, bean và các strategy có thể cấu hình. |
| `SimpleEvaluationContext` | Chỉ cung cấp tập con tính năng; loại trừ type reference, constructor và bean reference, đồng thời yêu cầu chọn rõ quyền property/method. |

Không dùng `StandardEvaluationContext` để đánh giá expression từ nguồn không tin cậy. Tài liệu Spring cảnh báo việc đánh giá SpEL không tin cậy vốn nguy hiểm vì expression có thể thực thi hành vi trong ứng dụng.

`SimpleEvaluationContext` chỉ giới hạn tính năng theo hướng best-effort, không phải sandbox an toàn tuyệt đối. Expression vẫn có thể gọi property, method hoặc function mà root object, accessor, resolver, variable hay function đã làm lộ ra.

Ngay cả property getter cũng có thể có side effect. Một method không tham số trả về giá trị có thể trông giống getter nhưng thực tế xóa file, lấy và loại bỏ phần tử queue hoặc tăng counter. Read-only data binding chỉ ngăn ghi property; nó không chứng minh việc đọc property là vô hại.

Khi phải đánh giá expression có nguồn không hoàn toàn tin cậy:

- Dùng DTO chuyên biệt, nhỏ và bất biến thay vì entity hoặc infrastructure object.
- Chỉ expose các property thực sự cần thiết.
- Kiểm tra mọi getter và accessor-shaped method có thể được gọi.
- Không đăng ký bean, function hoặc MethodResolver có quyền rộng.
- Giới hạn toàn bộ object graph mà expression có thể truy cập, kể cả object lồng nhau và phần tử collection.
- Parse thành Expression riêng cho từng phạm vi bảo mật; không tái sử dụng Expression đã chạy với context quyền rộng cho context quyền hẹp hơn.

## 12. Giới hạn thời gian và tài nguyên ngoài SpEL

Các giới hạn trong SpelParserConfiguration không tạo ra một timeout cứng cho mọi hoạt động. Một lần gọi method có thể thực hiện truy vấn database, gọi HTTP, chờ lock hoặc chạy vòng lặp dài bên trong Java code. Những chi phí đó không nhất thiết được phản ánh đầy đủ bởi bộ đếm thao tác của SpEL.

Ứng dụng cần thêm các biện pháp ở tầng bao quanh:

- Giới hạn kích thước request và số expression trong mỗi request.
- Giới hạn số lần đánh giá mỗi user/tenant trong một khoảng thời gian.
- Dùng executor có queue và concurrency hữu hạn nếu expression chạy trong tác vụ riêng.
- Đặt timeout cho các API bên ngoài mà method được phép gọi.
- Tránh cho expression gọi method thực hiện I/O hoặc thao tác có side effect.
- Theo dõi thời gian parse, thời gian evaluation, số lần bị từ chối bởi giới hạn và tỷ lệ lỗi.
- Nếu phải chạy logic hoàn toàn không tin cậy, cân nhắc không dùng SpEL trong process ứng dụng; dùng DSL an toàn hoặc thực thi trong môi trường cách ly phù hợp.

Không nên coi việc chạy evaluation trong Future với timeout là cách dừng chắc chắn một method Java không hợp tác với interrupt. Hãy thiết kế các method được expose sao cho có timeout và giới hạn tài nguyên riêng.

## 13. Phân loại lỗi parse và lỗi vượt giới hạn

Một số lỗi thường gặp:

| Hiện tượng | Giai đoạn | Hướng xử lý |
|---|---|---|
| Thiếu dấu ngoặc, quote hoặc toán tử sai vị trí | Parse | Sửa grammar và hiển thị vị trí lỗi. |
| Expression vượt maximumExpressionLength | Parse | Giảm độ dài hoặc điều chỉnh giới hạn có kiểm soát. |
| Expression có cấu trúc quá phức tạp | Parse | Đơn giản hóa grammar/biểu thức; kiểm tra giới hạn nesting theo phiên bản Spring đang dùng. |
| Property không tồn tại trên root object | Evaluation | Kiểm tra model, property path và accessor. |
| Method không tìm thấy hoặc đối số không phù hợp | Evaluation | Kiểm tra method resolver, kiểu và chữ ký method. |
| Evaluation vượt maximumOperations | Evaluation | Giảm số thao tác hoặc điều chỉnh budget sau khi đo expression hợp lệ. |
| Kết quả power vượt maximumBigPowerBits | Evaluation | Giới hạn đầu vào/exponent hoặc dùng phép tính được kiểm soát ở Java. |
| Auto-grow vượt giới hạn | Evaluation | Giảm index, tắt auto-grow hoặc đặt maximumAutoGrowSize phù hợp. |
| Regex hoặc chuỗi tạo ra vượt ngưỡng nội bộ | Parse/Evaluation tùy thao tác | Giảm pattern/đầu vào và kiểm tra mã lỗi cụ thể. |
| Evaluation kéo dài dù không vượt budget | Bên trong method hoặc hệ thống ngoài | Kiểm tra method được expose, I/O, lock và timeout ở tầng dịch vụ. |

Có thể bắt lỗi theo API tổng quát:

```java
try {
    Expression expression = parser.parseExpression(source);
    Object result = expression.getValue(context, rootObject);
}
catch (ParseException ex) {
    // Cú pháp không hợp lệ hoặc bị parser từ chối.
}
catch (EvaluationException ex) {
    // Expression hợp cú pháp nhưng không đánh giá được.
}
```

Trong hệ thống thực tế, nên chuyển exception thành mã lỗi nghiệp vụ phù hợp, không trả stack trace hoặc thông tin nội bộ cho người gửi expression.

## 14. Quy trình tiếp nhận và đánh giá expression

1. Xác định nguồn expression là developer/admin đáng tin cậy hay người dùng/hệ thống bên ngoài.
2. Nếu nguồn không tin cậy, ưu tiên DSL hoặc lựa chọn có cấu trúc thay vì nhận SpEL tùy ý.
3. Giới hạn kích thước request và độ dài expression trước khi parse.
4. Dùng SpelParserConfiguration với maximumExpressionLength phù hợp.
5. Đặt maximumOperations và maximumBigPowerBits theo ngân sách tài nguyên của ứng dụng.
6. Giữ auto-grow tắt; nếu cần bật, đặt maximumAutoGrowSize nhỏ và rõ ràng.
7. Parse expression trước khi lưu cấu hình để phát hiện lỗi grammar.
8. Dùng EvaluationContext quyền tối thiểu và root DTO chuyên biệt.
9. Không expose method có side effect, I/O hoặc chi phí không giới hạn.
10. Đánh giá với timeout/concurrency control ở tầng dịch vụ nếu cần.
11. Phân loại ParseException và EvaluationException; log mã lỗi, expression ID và thời gian xử lý thay vì ghi dữ liệu nhạy cảm.
12. Theo dõi giới hạn bị chạm tới và điều chỉnh dựa trên workload hợp lệ đã đo.

## 15. Ghi nhớ

- SpEL tách parse và evaluation; parse thành công không đồng nghĩa expression hợp lệ về nghiệp vụ hoặc an toàn.
- Spring Framework hiện hành giới hạn mặc định expression ở 10.000 ký tự.
- Từ Spring 6.2.19/7.0.8, evaluation có giới hạn mặc định 10.000 thao tác.
- Từ Spring 7.0.9, kết quả power BigInteger/BigDecimal mặc định bị giới hạn 1.000.000 bit.
- Builder hiện hành tắt auto-grow mặc định và giới hạn collection auto-grow ở 256 phần tử nếu bật.
- Có thể cấu hình maximumExpressionLength, maximumOperations, maximumBigPowerBits và maximumAutoGrowSize trên SpelParserConfiguration.
- Spring có các kiểm tra nội bộ cho regex, repeated text, concatenated string và array size; chúng không thay thế budget của ứng dụng.
- Operation budget không giới hạn chắc chắn thời gian bên trong method tùy chỉnh hoặc I/O.
- StandardEvaluationContext không dành cho expression không tin cậy; SimpleEvaluationContext cũng không phải sandbox bảo mật tuyệt đối.
- Dùng root object chuyên biệt, bất biến, giới hạn accessor và không tái sử dụng parsed Expression giữa context có quyền khác nhau.
- Với expression do người dùng định nghĩa, ưu tiên DSL/allow-list thay vì cố lọc SpEL bằng regex hoặc blacklist.

## Tài liệu tham khảo

- [Spring Framework Reference — Evaluation, Parser Configuration, and Security Considerations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpelParserConfiguration.Builder Javadoc — Spring Framework 7.0.10](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.Builder.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.html)
- [SpelMessage Source — Resource and Pattern Limit Errors](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/SpelMessage.java)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
