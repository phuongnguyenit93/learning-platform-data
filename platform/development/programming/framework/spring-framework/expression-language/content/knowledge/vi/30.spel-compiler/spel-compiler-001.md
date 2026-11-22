# SpEL expression compiler là gì?

## 1. Tổng quan về SpEL compiler

Spring Expression Language (SpEL) thường đánh giá expression bằng interpreter. Interpreter đọc cấu trúc expression và thực hiện từng node khi gọi `getValue()`. Cách này linh hoạt vì SpEL có thể xử lý object và kiểu dữ liệu động tại runtime, nhưng việc diễn giải lặp lại có thể tốn chi phí khi cùng một expression được đánh giá rất nhiều lần.

SpEL compiler là cơ chế tùy chọn tạo Java bytecode từ một expression để các lần đánh giá tiếp theo chạy nhanh hơn. Thay vì đi qua toàn bộ interpreter ở mỗi lần gọi, SpEL dùng class đã được sinh ra để thực hiện hành vi của expression.

Compiler phù hợp nhất khi:

- Một expression được đánh giá lặp đi lặp lại trong luồng có yêu cầu hiệu năng.
- Kiểu của các property và giá trị trung gian ổn định giữa các lần đánh giá.
- Expression thuộc nhóm cú pháp mà compiler hỗ trợ.
- Chi phí khởi tạo/biên dịch được bù lại bởi số lần đánh giá về sau.

Compiler không bật mặc định. Các expression đơn giản hoặc chỉ được đánh giá thỉnh thoảng thường không cần biên dịch.

## 2. Interpreter và compiled expression

Khi expression chạy ở interpreted mode, SpEL đánh giá cây cú pháp (AST) bằng các node interpreter. Trong quá trình đó, framework có thể biết thêm thông tin runtime như kiểu thực tế của property hoặc kiểu kết quả trung gian.

Compiler sử dụng thông tin thu được từ các lần đánh giá interpreted để sinh bytecode cho expression. Điều này quan trọng vì expression SpEL không khai báo đầy đủ kiểu tĩnh như Java. Ví dụ:

```text
payload.customer.address.city
```

Chỉ nhìn expression, compiler không nhất thiết biết kiểu runtime của `payload`, `customer` hoặc `address`. Sau khi expression được đánh giá interpreted với object thật, SpEL có thể ghi nhận kiểu cần thiết để tạo mã bytecode.

Ví dụ expression có truy cập array, nhiều property và phép toán số:

```text
someArray[0].someProperty.someOtherProperty < 0.1
```

Nếu expression này được đánh giá rất nhiều lần trên object có cấu trúc ổn định, compiler có thể giảm chi phí diễn giải. Spring Reference đưa ra một microbenchmark minh họa 50.000 lần đánh giá mất khoảng 75 ms ở interpreter và 3 ms ở compiled form. Đây chỉ là kết quả của ví dụ benchmark cụ thể, không phải cam kết tốc độ cho mọi expression hoặc ứng dụng.

## 3. Vì sao kiểu dữ liệu phải ổn định?

Compiler dựa vào kiểu mà nó quan sát được khi expression chạy interpreted. Nếu các lần đánh giá sau nhận object có kiểu khác, mã đã biên dịch có thể không còn phù hợp.

Ví dụ một property ban đầu luôn trả về String:

```java
public class Message {
    private String payload;

    public String getPayload() {
        return payload;
    }
}
```

Expression:

```text
payload.toUpperCase()
```

Sau lần đánh giá đầu, compiler có thể sinh mã dựa trên việc `payload` là String. Nếu một object khác hoặc một lần đánh giá sau cung cấp kiểu không tương thích, compiled expression có thể thất bại.

Vì vậy:

- Dùng compiler cho expression có cấu trúc và kiểu dữ liệu ổn định.
- Tránh compiled mode khi cùng expression được đánh giá trên các object có kiểu property thay đổi tùy lần.
- Kiểm tra các trường hợp null và kiểu runtime khác nhau.
- Nếu kiểu dữ liệu thay đổi thường xuyên, giữ interpreted mode hoặc cân nhắc MIXED mode tùy side effect.

## 4. Ba chế độ SpelCompilerMode

SpEL compiler có ba chế độ trong enum `org.springframework.expression.spel.SpelCompilerMode`:

| Chế độ | Hành vi |
|---|---|
| `OFF` | Tắt compiler; tất cả expression chạy interpreted. Đây là mặc định. |
| `IMMEDIATE` | Biên dịch expression sớm nhất có thể, thường sau lần đánh giá interpreted đầu tiên. Nếu compiled expression lỗi, exception được truyền cho caller. |
| `MIXED` | Tự chuyển đổi giữa interpreted và compiled theo thời gian. Nếu compiled expression lỗi, SpEL bắt lỗi nội bộ và quay lại interpreted mode; sau đó có thể thử biên dịch lại. |

### 4.1. OFF

Dùng OFF khi:

- Expression chỉ chạy thỉnh thoảng.
- Cần tính linh hoạt tối đa với object có kiểu thay đổi.
- Expression sử dụng cú pháp compiler chưa hỗ trợ.
- Không có bằng chứng đo lường cho thấy compiler đem lại lợi ích.

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.OFF)
                .build();

SpelExpressionParser parser =
        new SpelExpressionParser(config);
```

OFF cũng là lựa chọn mặc định nếu không cấu hình compiler mode.

### 4.2. IMMEDIATE

IMMEDIATE biên dịch expression sớm, thường sau lần đánh giá interpreted đầu tiên. Nếu compiled expression gặp lỗi, lỗi được truyền cho caller.

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.IMMEDIATE)
                .compilerClassLoader(getClass().getClassLoader())
                .build();

SpelExpressionParser parser =
        new SpelExpressionParser(config);

Expression expression = parser.parseExpression("payload");

Object result = expression.getValue(message);
```

Chọn IMMEDIATE khi kiểu dữ liệu ổn định và ứng dụng muốn nhận lỗi ngay nếu compiled expression không còn phù hợp. Không nên dùng IMMEDIATE chỉ để ép mọi expression biên dịch; compiler vẫn không hỗ trợ mọi cú pháp.

### 4.3. MIXED

MIXED tự chuyển giữa hai cách đánh giá. Sau một số lần chạy interpreted thành công, expression có thể được biên dịch. Nếu compiled form thất bại, SpEL quay về interpreted mode thay vì truyền lỗi biên dịch/đánh giá đó cho caller theo cách của IMMEDIATE. Sau đó framework có thể thử biên dịch lại; nếu lỗi lặp quá nhiều, expression có thể bị giữ ở interpreted mode.

MIXED hữu ích khi kiểu dữ liệu đôi lúc thay đổi và ứng dụng muốn expression tiếp tục được đánh giá. Tuy nhiên, có một lưu ý quan trọng về side effect: compiled expression có thể đã thực hiện một phần thao tác trước khi lỗi xảy ra. Nếu MIXED tự chạy lại expression interpreted, một phần hành vi có thể được thực hiện lần thứ hai.

Vì vậy, không nên dựa vào MIXED cho expression có side effect quan trọng, chẳng hạn ghi dữ liệu, gọi dịch vụ bên ngoài hoặc thay đổi trạng thái không idempotent.

## 5. Cấu hình compiler bằng SpelParserConfiguration

Cách trực tiếp nhất để bật compiler là cấu hình `SpelParserConfiguration` rồi tạo `SpelExpressionParser` từ cấu hình đó:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.IMMEDIATE)
                .compilerClassLoader(getClass().getClassLoader())
                .build();

SpelExpressionParser parser =
        new SpelExpressionParser(config);

Expression expression =
        parser.parseExpression("payload.customer.name");

String name = expression.getValue(message, String.class);
```

Các phần quan trọng:

- `compilerMode(...)` chọn OFF, IMMEDIATE hoặc MIXED.
- `compilerClassLoader(...)` chỉ định ClassLoader dùng làm parent để định nghĩa compiled expression.
- Parser được tạo từ cấu hình sẽ áp dụng chế độ compiler cho các expression mà parser phân tích.

Ở các phiên bản Spring có API constructor tương ứng, có thể cấu hình bằng constructor của `SpelParserConfiguration`:

```java
SpelParserConfiguration config =
        new SpelParserConfiguration(
                SpelCompilerMode.IMMEDIATE,
                getClass().getClassLoader());
```

Dùng API phù hợp với phiên bản Spring Framework của ứng dụng; builder và các overload có thể khác nhau theo phiên bản.

## 6. Cấu hình compiler bằng system property

Khi SpEL được nhúng trong thành phần khác và ứng dụng không trực tiếp tạo parser, có thể cấu hình compiler mode qua property:

```properties
spring.expression.compiler.mode=immediate
```

Hoặc qua JVM system property:

```text
-Dspring.expression.compiler.mode=immediate
```

Các giá trị hợp lệ tương ứng với enum là:

```text
off
immediate
mixed
```

Spring cũng hỗ trợ thiết lập qua cơ chế `SpringProperties`. Property này hữu ích cho thành phần tự tạo parser nội bộ, nhưng phạm vi ảnh hưởng có thể rộng hơn một parser được cấu hình riêng. Hãy cân nhắc tác động tới mọi expression trong process trước khi bật global mode.

Nếu ứng dụng kiểm soát được parser, cấu hình riêng bằng `SpelParserConfiguration` thường dễ giới hạn phạm vi hơn.

## 7. ClassLoader của compiled expression

SpEL compiler sinh class Java tại runtime. Compiled class được định nghĩa trong child ClassLoader được tạo bên dưới ClassLoader được cung cấp.

Nếu chỉ định ClassLoader, nó phải nhìn thấy mọi kiểu tham gia vào expression evaluation, bao gồm:

- Kiểu của root object.
- Kiểu property được truy cập.
- Kiểu tham số và kết quả method.
- Các kiểu trung gian trong phép toán.

Ví dụ:

```java
ClassLoader applicationClassLoader =
        Order.class.getClassLoader();

SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.MIXED)
                .compilerClassLoader(applicationClassLoader)
                .build();
```

Nếu không chỉ định ClassLoader, SpEL dùng ClassLoader mặc định, thường là thread context ClassLoader tại thời điểm đánh giá expression.

Trong ứng dụng có plugin, application server hoặc nhiều ClassLoader, chọn sai ClassLoader có thể khiến compiled expression không truy cập được kiểu cần thiết. Khi gặp lỗi liên quan đến class loading, kiểm tra ClassLoader của root object và các kiểu trung gian trước khi thay đổi expression.

## 8. Những loại expression compiler không hỗ trợ

SpEL compiler không biên dịch được mọi loại expression. Các nhóm sau không được hỗ trợ trong tài liệu Spring hiện hành:

- Expression có phép gán.
- Expression phụ thuộc ConversionService.
- Expression sử dụng custom resolver.
- Expression sử dụng overloaded operator.
- Expression sử dụng Optional cùng null-safe operator hoặc Elvis operator.
- Expression dùng cú pháp tạo array.
- Expression dùng collection selection hoặc projection.
- Expression dùng bean reference.

Ví dụ các dạng cần giữ interpreted:

```text
name = 'Ada'
items.?[active]
items.![name]
@pricingService.currentRate
```

Với expression không hỗ trợ, đừng giả định bật compiler mode sẽ tự biến expression đó thành compiled bytecode. Các expression không thể biên dịch vẫn cần được xử lý theo cơ chế interpreted phù hợp.

Danh sách hỗ trợ có thể thay đổi theo phiên bản Spring. Hãy kiểm tra tài liệu của phiên bản đang dùng trước khi thiết kế hệ thống phụ thuộc vào compiled expression.

## 9. Kiểm tra expression có được biên dịch hay không

Không nên suy luận rằng expression đã biên dịch chỉ vì parser được cấu hình IMMEDIATE hoặc MIXED. Compiler có thể không hỗ trợ cú pháp của expression, thiếu thông tin kiểu hoặc không biên dịch thành công.

Khi cần kiểm tra trong test hoặc chẩn đoán, có thể dùng API cụ thể của `SpelExpression`:

```java
SpelExpression expression =
        (SpelExpression) parser.parseExpression("payload");

Object first = expression.getValue(message);

// Với expression được hỗ trợ và cấu hình phù hợp,
// có thể kiểm tra trạng thái compiled:
boolean compiled = expression.isCompiled();
```

`isCompiled()` là chi tiết API của implementation `SpelExpression`, không phải phương thức trong interface tổng quát `Expression`. Nếu code chỉ giữ kiểu Expression, cần cast phù hợp hoặc quan sát bằng công cụ chẩn đoán của phiên bản đang dùng.

Không nên dùng trạng thái compiled làm điều kiện nghiệp vụ. Nó phục vụ chẩn đoán và tối ưu hiệu năng; kết quả đúng của expression mới là điều ứng dụng cần bảo đảm.

## 10. Đo hiệu năng trước và sau khi bật compiler

Compiler nhằm giảm chi phí đánh giá lặp lại. Tuy nhiên, việc biên dịch có chi phí khởi tạo và không phải expression nào cũng có thể biên dịch.

Khi đo, cần tách:

1. Thời gian parse expression.
2. Chi phí các lần đánh giá interpreted ban đầu.
3. Chi phí biên dịch.
4. Thời gian đánh giá khi đã compiled.
5. Tác động của object thực tế, số lần gọi và concurrency.

Một microbenchmark nên chạy đủ warm-up, dùng cùng dữ liệu đầu vào và cùng expression, đồng thời so sánh OFF với IMMEDIATE/MIXED. Không so sánh một lần gọi interpreted với một lần gọi compiled rồi kết luận.

Ví dụ cấu trúc benchmark đơn giản:

```java
ExpressionParser interpretedParser =
        new SpelExpressionParser(
                SpelParserConfiguration.builder()
                        .compilerMode(SpelCompilerMode.OFF)
                        .build());

ExpressionParser compiledParser =
        new SpelExpressionParser(
                SpelParserConfiguration.builder()
                        .compilerMode(SpelCompilerMode.IMMEDIATE)
                        .build());

Expression interpreted =
        interpretedParser.parseExpression("payload.amount * 1.08");

Expression compiled =
        compiledParser.parseExpression("payload.amount * 1.08");

// Warm up và đo lặp lại với cùng tập message.
```

Trong ứng dụng thực tế, dùng JMH hoặc công cụ benchmark phù hợp để tránh sai lệch do JIT, GC, class loading và warm-up. Nếu expression chỉ chạy vài lần, chi phí biên dịch có thể lớn hơn lợi ích.

## 11. Lưu ý bảo mật: SimpleEvaluationContext và CVE-2026-59283

`SimpleEvaluationContext` được thiết kế để giới hạn một số khả năng SpEL. Tuy nhiên, Spring đã công bố CVE-2026-59283 vào ngày 20-08-2026 về việc compiler có thể vượt qua safety guard của SimpleEvaluationContext trong một số cấu hình.

Điều kiện liên quan gồm:

- Ứng dụng đánh giá expression bằng SimpleEvaluationContext.
- SpEL compiler được bật bằng `IMMEDIATE` hoặc `MIXED`, thông qua `SpelParserConfiguration` hoặc property `spring.expression.compiler.mode`.

Trong các phiên bản bị ảnh hưởng, expression có thể được biên dịch âm thầm dù dùng SimpleEvaluationContext. Những lần đánh giá compiled sau đó có thể bỏ qua safety guard vốn được áp dụng trong interpreted mode. Advisory cũng đề cập khả năng tăng không giới hạn số class được load do các expression khác nhau sinh class trong child ClassLoader.

Spring công bố các phiên bản bị ảnh hưởng:

| Dòng phiên bản | Phạm vi bị ảnh hưởng |
|---|---|
| 7.0 | 7.0.0 đến 7.0.8 |
| 6.2 | 6.2.0 đến 6.2.19 |
| 6.1 | 6.1.0 đến 6.1.28 |
| 6.0 | 6.0.0 đến 6.0.30 |
| 5.3 | 5.3.0 đến 5.3.49 |
| 5.2 | 5.2.25.RELEASE và cũ hơn |

Các bản sửa lỗi được advisory liệt kê:

| Bản sửa | Tình trạng được advisory công bố |
|---|---|
| 7.0.9 | OSS |
| 7.0.8.1 | Enterprise Support Only |
| 6.2.20 | Enterprise Support Only |
| 6.1.29 | Enterprise Support Only |
| 6.0.31 | Enterprise Support Only |
| 5.3.50 | Enterprise Support Only |
| 5.2.26 | Enterprise Support Only |

Trong các bản đã sửa, SimpleEvaluationContext không hỗ trợ expression compilation theo mặc định, bất kể compiler mode được cấu hình ở parser hoặc property. Ứng dụng thật sự cần compiled expression với SimpleEvaluationContext và chỉ xử lý expression tin cậy có thể opt in bằng `withCompilationSupported()` trên builder.

Việc opt in loại bỏ các safety guard áp dụng trong interpreted evaluation. Không bật tùy chọn này khi expression có thể đến từ người dùng hoặc nguồn không tin cậy. Hãy nâng cấp lên bản Spring đã sửa phù hợp với dòng hỗ trợ của ứng dụng và đọc advisory chính thức trước khi cấu hình compiler.

## 12. Chọn chế độ phù hợp

| Tình huống | Hướng lựa chọn |
|---|---|
| Expression ít được đánh giá | OFF |
| Expression có kiểu ổn định, cú pháp được hỗ trợ và muốn lỗi compiled được truyền ra | IMMEDIATE |
| Expression có thể thay đổi kiểu và muốn tự quay lại interpreted mode | MIXED |
| Expression có side effect quan trọng | Ưu tiên OFF hoặc đánh giá cẩn thận rủi ro chạy lại trong MIXED |
| Expression dùng selection/projection, assignment hoặc custom resolver | OFF/interpreted |
| Expression được đánh giá trên dữ liệu không tin cậy bằng SimpleEvaluationContext | Không bật compiler; dùng bản Spring đã vá |
| Cần compiler cho SimpleEvaluationContext trên bản đã vá | Chỉ opt in nếu expression hoàn toàn tin cậy và hiểu việc mất safety guard |

Không có một chế độ tối ưu cho mọi ứng dụng. Chọn theo độ ổn định kiểu, loại expression, side effect và kết quả benchmark.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy cải thiện hiệu năng | Expression ít chạy, compiler chưa biên dịch được hoặc chi phí khởi tạo lớn. | Đo lặp lại sau warm-up và kiểm tra trạng thái compiled. |
| IMMEDIATE ném lỗi sau khi compile | Kiểu runtime khác với kiểu đã suy ra hoặc compiled code gặp lỗi. | Kiểm tra type stability; dùng OFF hoặc MIXED nếu phù hợp. |
| MIXED chuyển lại interpreted | Compiled expression thất bại. | Kiểm tra dữ liệu và kiểu đầu vào; xác định expression có ổn định không. |
| Expression không biên dịch | Cú pháp thuộc nhóm chưa hỗ trợ hoặc thiếu thông tin kiểu. | Giữ interpreted mode cho expression đó. |
| ClassNotFoundException/LinkageError | Compiler ClassLoader không nhìn thấy kiểu liên quan. | Chọn ClassLoader phù hợp với root object và domain classes. |
| Side effect xảy ra hai lần trong MIXED | Compiled expression thực hiện một phần trước khi lỗi và framework chạy lại interpreted. | Tránh MIXED với expression không idempotent; dùng IMMEDIATE/OFF theo yêu cầu. |
| SimpleEvaluationContext có hành vi khác giữa các bản Spring | Khác biệt bản vá CVE-2026-59283 và chính sách compilation. | Nâng cấp bản vá; không opt in compilation với expression không tin cậy. |
| Global compiler mode ảnh hưởng expression khác | Property cấu hình áp dụng cho các parser thành phần sử dụng. | Ưu tiên cấu hình parser riêng nếu cần giới hạn phạm vi. |
| Benchmark cho kết quả không ổn định | Thiếu warm-up, khác dữ liệu, JIT/GC hoặc đo lẫn parse và evaluation. | Dùng JMH, tách các pha và giữ dữ liệu so sánh tương đương. |

## 14. Quy trình bật SpEL compiler

1. Xác định expression nào được đánh giá đủ thường xuyên để đáng tối ưu.
2. Đo baseline khi compiler OFF.
3. Xác nhận expression thuộc nhóm compiler hỗ trợ.
4. Kiểm tra kiểu root object, property và kết quả có ổn định giữa các lần chạy.
5. Chọn OFF, IMMEDIATE hoặc MIXED theo hành vi lỗi và side effect.
6. Cấu hình SpelParserConfiguration cho parser cần tối ưu.
7. Nếu cần, chọn ClassLoader có thể nhìn thấy mọi kiểu liên quan.
8. Chạy test với dữ liệu hợp lệ, null và các kiểu runtime có thể xuất hiện.
9. Đo lại bằng benchmark có warm-up và nhiều lần lặp.
10. Nếu dùng SimpleEvaluationContext, kiểm tra phiên bản Spring và trạng thái bản vá CVE-2026-59283; không opt in compilation cho expression không tin cậy.
11. Theo dõi lỗi compiled evaluation, class loading và mức sử dụng bộ nhớ trong môi trường chạy thật.
12. Giữ interpreted mode cho expression không được hỗ trợ hoặc không ổn định kiểu.

## 15. Ghi nhớ

- SpEL compiler sinh Java bytecode cho expression nhằm tăng tốc đánh giá lặp lại.
- Compiler dùng thông tin kiểu thu được từ interpreted evaluation; kiểu runtime ổn định là điều kiện quan trọng.
- Compiler OFF là mặc định.
- IMMEDIATE biên dịch sớm và truyền lỗi compiled ra caller.
- MIXED tự quay lại interpreted khi compiled expression thất bại, nhưng có thể gây chạy lại side effect.
- Bật compiler bằng SpelParserConfiguration hoặc property `spring.expression.compiler.mode`.
- Compiled class được nạp qua child ClassLoader; ClassLoader cần nhìn thấy các kiểu liên quan.
- Assignment, ConversionService, custom resolver, overloaded operator, selection/projection, bean reference và một số cú pháp khác không được compiler hỗ trợ.
- Đo hiệu năng trên workload thật; không coi benchmark minh họa là cam kết.
- CVE-2026-59283 liên quan compiled SimpleEvaluationContext; nâng cấp bản đã sửa và chỉ opt in compilation cho expression tin cậy.

## Tài liệu tham khảo

- [Spring Framework Reference — SpEL Compilation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpelCompilerMode Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelCompilerMode.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/standard/SpelParserConfiguration.html)
- [SpelCompiler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/standard/SpelCompiler.html)
- [Spring Security Advisory — CVE-2026-59283](https://spring.io/security/cve-2026-59283/)
