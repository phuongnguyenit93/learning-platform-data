# Tránh function có tác dụng phụ hoặc truy cập tài nguyên ngoài ý muốn trong SpEL

## Mục tiêu

SpEL cho phép ứng dụng đăng ký các Java method làm function để biểu thức có thể gọi chúng bằng cú pháp `#functionName(...)`. Cơ chế này hữu ích khi cần tái sử dụng một phép tính hoặc quy tắc nhỏ trong nhiều expression. Tuy nhiên, function được gọi trong lúc expression được đánh giá. Nếu method ghi dữ liệu, gửi message, truy cập mạng, đọc file hoặc gọi database, một biểu thức tưởng như chỉ đọc có thể gây ra hành động bên ngoài.

Vì vậy, function dành cho SpEL nên có phạm vi nhỏ, kết quả dễ dự đoán và không tạo tác dụng phụ. Các thao tác với tài nguyên bên ngoài nên được thực hiện rõ ràng ở tầng ứng dụng; expression chỉ nhận dữ liệu đã được chuẩn bị và thực hiện quyết định hoặc phép tính trên dữ liệu đó.

## 1. Function trong SpEL là gì?

Function là một Java `Method` được đăng ký trong `EvaluationContext` và được gọi từ expression bằng dấu `#`:

```spel
#normalize(name)
#isEligible(age, country)
```

Với `StandardEvaluationContext`, có thể đăng ký method bằng `registerFunction`. Method được đăng ký cần là static; nên dùng public static method với chữ ký rõ ràng:

```java
public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase(Locale.ROOT);
    }
}
```

Đăng ký và gọi function:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(customer);

Method normalize = TextFunctions.class.getMethod(
        "normalize", String.class);
context.registerFunction("normalize", normalize);

Expression expression = parser.parseExpression("#normalize(name)");
String normalizedName = expression.getValue(context, String.class);
```

Tên truyền cho `registerFunction` là `normalize`, không có dấu `#`. Dấu `#` chỉ xuất hiện khi tham chiếu function trong SpEL. Cũng có thể đăng ký `Method` như một biến bằng `setVariable`; `registerFunction` diễn đạt rõ hơn ý định dùng method đó như function.

## 2. Function nên thực hiện phép tính thuần

Function phù hợp với SpEL thường nhận các đối số, tính toán trên chúng và trả về kết quả. Với cùng một bộ đối số, function nên trả về cùng một kết quả và không làm thay đổi trạng thái bên ngoài.

Ví dụ các function thường phù hợp:

- Chuẩn hóa chuỗi, chuyển chữ hoa/thường hoặc định dạng một giá trị.
- Tính tổng, tỷ lệ, điểm số hoặc giá trị dẫn xuất từ các đối số.
- Kiểm tra một điều kiện thuần như một mã có đúng định dạng hay không.
- Chuyển đổi một enum hoặc mã nghiệp vụ sang nhãn hiển thị từ bảng dữ liệu đã có sẵn.
- Kiểm tra một giá trị thuộc một tập hợp đã được truyền vào context.

Ví dụ:

```java
public final class RuleFunctions {

    private RuleFunctions() {
    }

    public static boolean isAllowed(String role, Set<String> allowedRoles) {
        return role != null && allowedRoles.contains(role);
    }

    public static BigDecimal withTax(BigDecimal amount, BigDecimal rate) {
        if (amount == null || rate == null) {
            return null;
        }
        return amount.multiply(BigDecimal.ONE.add(rate));
    }
}
```

Những method này chỉ đọc đối số và tạo kết quả. Chúng không ghi database, thay đổi object đầu vào hoặc gọi một hệ thống khác.

## 3. Các tác dụng phụ cần tránh

Không nên đăng ký các function làm những việc sau nếu expression được dùng như một rule hoặc phép tính:

| Loại hành động | Ví dụ | Vì sao không phù hợp trong function của SpEL |
| --- | --- | --- |
| Ghi dữ liệu | `saveOrder`, `updateAccount`, `deleteRecord` | Expression có thể vô tình thay đổi trạng thái khi chỉ được kỳ vọng là đánh giá điều kiện. |
| Gửi message | `publishEvent`, `sendEmail`, `sendSms` | Việc đánh giá lại expression có thể gửi trùng thông báo. |
| Gọi mạng | HTTP client, REST API, remote service | Tạo độ trễ, timeout, lỗi phụ thuộc mạng và khó dự đoán số lần gọi. |
| Truy cập database | Repository query, transaction hoặc stored procedure | Có thể phát sinh truy vấn ẩn trong selection/projection hoặc mỗi lần `getValue`. |
| Truy cập file | Đọc/ghi file, liệt kê thư mục | Kết quả phụ thuộc trạng thái filesystem và có thể lộ hoặc thay đổi dữ liệu. |
| Thay đổi trạng thái | Tăng counter, sửa object dùng chung, cập nhật cache | Kết quả phụ thuộc lịch sử gọi và có thể khác nhau giữa các lần đánh giá. |
| Tác vụ tốn tài nguyên | Nén file, xử lý ảnh lớn, vòng lặp không giới hạn | Một expression đơn giản có thể chiếm CPU, bộ nhớ hoặc thread trong thời gian dài. |

Không phải mọi method có side effect đều luôn sai trong mọi ứng dụng. Vấn đề là function trong expression thường bị gọi ở thời điểm và số lần mà người viết expression khó nhận ra. Nếu cần thực hiện một hành động, hãy gọi nó trong luồng xử lý Java có kiểm soát, nơi ứng dụng có thể quản lý transaction, retry, logging, authorization và lỗi.

## 4. Function có thể được gọi nhiều lần

Đăng ký function không có nghĩa là SpEL chạy nó một lần rồi cache kết quả. Function được gọi khi quá trình đánh giá đi tới lời gọi đó. Nếu cùng expression được đánh giá nhiều lần, function có thể được gọi lại nhiều lần.

Điều này đặc biệt quan trọng với selection và projection:

```spel
users.?[#isEligible(#this.age, #this.country)]
products.![#formatPrice(#this.price)]
```

Trong selection, function có thể được gọi cho từng user mà điều kiện cần kiểm tra. Trong projection, function có thể được gọi cho từng product được chiếu. Nếu expression được đánh giá lại ở request khác hoặc ở một bước xử lý khác, các lời gọi cũng được thực hiện lại.

Short-circuit có thể khiến một nhánh không được đánh giá, nhưng không nên dựa vào đó để điều khiển tác dụng phụ. Việc function có được gọi hay không phụ thuộc vào đường đi đánh giá của expression và dữ liệu runtime.

Parse expression một lần chỉ tái sử dụng cấu trúc đã parse; điều đó không tự cache kết quả của function. Nếu cần gọi một dịch vụ bên ngoài đúng một lần, hãy gọi dịch vụ ở tầng ứng dụng rồi truyền kết quả vào context.

## 5. Đưa dữ liệu bên ngoài vào context trước khi đánh giá

Nếu rule cần dữ liệu từ database hoặc API, hãy tải dữ liệu trước bằng service/repository, sau đó đưa kết quả vào `EvaluationContext` dưới dạng root property hoặc variable.

Ví dụ: thay vì đăng ký function `loadCountryName(code)` để gọi database mỗi lần expression cần tên quốc gia, tải trước một map:

```java
Map<String, String> countryNames = countryRepository.findAllNames();

StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("countryNames", countryNames);
```

Expression chỉ tra dữ liệu đã có:

```spel
#countryNames[countryCode] == 'Vietnam'
```

Với cách này, truy cập map không tạo truy vấn database ẩn. Ứng dụng kiểm soát thời điểm tải, phạm vi dữ liệu, cache, lỗi và quyền truy cập trước khi expression chạy.

Nếu dữ liệu lớn hoặc cần truy vấn theo từng điều kiện, hãy thực hiện truy vấn ở service layer theo một kế hoạch rõ ràng. Không dùng function trong SpEL như một cách thay thế repository hoặc orchestration layer.

## 6. Ví dụ đầy đủ: đăng ký function thuần và dùng trong selection

Giả sử cần chọn những user có trạng thái hoạt động. Có thể viết helper thuần:

```java
public final class UserRuleFunctions {

    private UserRuleFunctions() {
    }

    public static boolean isActive(Boolean active) {
        return Boolean.TRUE.equals(active);
    }
}
```

Đăng ký và sử dụng:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(account);

Method isActive = UserRuleFunctions.class.getMethod(
        "isActive", Boolean.class);
context.registerFunction("isActive", isActive);

Expression expression = parser.parseExpression(
        "users.?[#isActive(#this.active)]");

List<?> activeUsers = expression.getValue(context, List.class);
```

`isActive` trả về true khi giá trị là `Boolean.TRUE`; false và null đều trả về false theo quy tắc được viết rõ trong helper. Function không truy cập tài nguyên, không thay đổi user và có thể được gọi nhiều lần mà không làm thay đổi trạng thái ứng dụng.

## 7. Phân biệt function với instance method và Spring bean

SpEL có nhiều cách gọi Java code. Chúng không có cùng ý nghĩa:

| Cú pháp | Cơ chế |
| --- | --- |
| `#normalize(name)` | Gọi function đã đăng ký trong evaluation context. |
| `#formatter.format(name)` | Gọi instance method trên object được đăng ký bằng variable `formatter`. |
| `@formatterBean.format(name)` | Gọi method trên Spring bean khi context có `BeanResolver` phù hợp. |
| `T(com.example.Formatters).normalize(name)` | Gọi static method qua type reference. |

Function là một method reference được expose dưới một tên trong context. Bean hoặc instance method có thể có nhiều quyền hơn, chẳng hạn truy cập repository hoặc thay đổi trạng thái. Chỉ expose chúng khi expression thực sự cần và các quyền đó đã được giới hạn.

Nếu một helper chỉ làm phép tính thuần, đăng ký function tĩnh có chữ ký hẹp thường dễ kiểm soát hơn việc expose cả một service lớn. Nếu cần thao tác nghiệp vụ hoặc tài nguyên, gọi service trong Java trước/sau khi đánh giá rule theo một luồng rõ ràng.

## 8. Thiết kế function có đầu vào và đầu ra rõ ràng

Một function an toàn nên có hợp đồng đơn giản:

- Tên thể hiện hành động hoặc phép tính cụ thể.
- Số lượng và kiểu tham số rõ ràng.
- Không phụ thuộc vào biến static mutable hoặc trạng thái toàn cục.
- Không thay đổi đối số hoặc object dùng chung.
- Xử lý null và input biên theo quy tắc đã xác định.
- Trả về giá trị có kiểu ổn định, tốt nhất là immutable/value object.
- Không giữ lại dữ liệu nhạy cảm hoặc object request sau khi trả kết quả.

Tránh các tên chung như `execute`, `process`, `invoke` hoặc `run` nếu chúng che giấu nhiều loại hành động. Tên như `normalizeCustomerCode` hoặc `isWithinLimit` giúp người đọc expression hiểu được function làm gì.

Nếu một phép tính cần nhiều dữ liệu, truyền các giá trị cần thiết làm đối số hoặc gom chúng trong một input object chỉ đọc. Tránh để function tự tìm thêm dữ liệu qua singleton, static service locator hoặc global state.

## 9. Giới hạn quyền function được đăng ký

Những gì expression có thể gọi phụ thuộc vào các function và khả năng truy cập được cung cấp trong evaluation context. Vì vậy, đăng ký function cũng là một quyết định về quyền.

Với expression đến từ người dùng, file cấu hình bên ngoài hoặc nguồn không hoàn toàn tin cậy:

- Chỉ đăng ký function thật sự cần thiết cho rule.
- Không đăng ký helper có thể chạy command, truy cập filesystem tùy ý, gọi URL tùy ý hoặc thực hiện thao tác quản trị.
- Không expose toàn bộ service/repository chỉ để expression có thể gọi một method nhỏ.
- Xác thực và giới hạn kích thước/độ dài đối số trước khi đánh giá.
- Dùng context riêng theo request nếu variables hoặc root object thay đổi theo request.
- Kiểm tra cả function được đăng ký lẫn object/method khác có thể truy cập từ root và context.

Việc chỉ đăng ký một số function là một phần của allowlist, không tự động biến mọi expression thành sandbox hoàn chỉnh. Một root object có nhiều public method hoặc một bean resolver rộng vẫn có thể mở ra đường truy cập khác.

## 10. Xử lý lỗi và tính dự đoán

Function có thể ném exception giống Java method thông thường. Lỗi trong lúc gọi function sẽ làm evaluation thất bại và được SpEL báo qua exception của quá trình đánh giá; nguyên nhân gốc thường nằm trong cause chain.

Để lỗi dễ xử lý:

- Kiểm tra input ở tầng ứng dụng trước khi gọi `getValue`.
- Giữ function ngắn và chỉ thực hiện một phép tính.
- Không nuốt exception rồi trả một giá trị mặc định không rõ nghĩa.
- Nếu một trường hợp đầu vào là hợp lệ nhưng không có kết quả, trả về một giá trị có ý nghĩa như null hoặc Optional theo hợp đồng được hỗ trợ, rồi xử lý rõ trong expression/application.
- Ghi log lỗi ở ranh giới ứng dụng với đủ ngữ cảnh nhưng không ghi dữ liệu nhạy cảm.
- Không tự retry network/database bên trong function; retry thuộc tầng có thể quản lý timeout, idempotency và giới hạn số lần.

Đặc biệt, không dùng một giá trị mặc định chung như `false` cho mọi lỗi. `false` có thể là kết quả nghiệp vụ hợp lệ và khiến lỗi hạ tầng bị che khuất.

## 11. Kiểm tra function trước khi đăng ký

Trước khi đưa một function vào evaluation context, hãy xác định:

1. Method có phải static và có chữ ký rõ ràng không?
2. Nó có đọc/ghi database, file, network, cache hoặc message broker không?
3. Nó có sửa object đầu vào, global state hoặc dữ liệu dùng chung không?
4. Nó có thể được gọi nhiều lần trong một expression hoặc trên từng phần tử collection không?
5. Kết quả có xác định với cùng bộ đối số không?
6. Input có giới hạn độ dài, kích thước và miền giá trị không?
7. Null, exception và dữ liệu không hợp lệ được xử lý thế nào?
8. Có thể tải dữ liệu cần thiết trước rồi truyền vào context thay cho việc truy cập tài nguyên từ function không?
9. Expression có đến từ nguồn không tin cậy và context có expose thêm quyền nào khác không?

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `#functionName(...)` không tìm thấy function | Function chưa được đăng ký, tên không khớp hoặc context đang dùng khác context đã cấu hình. | Đăng ký bằng `registerFunction` trước `getValue`; kiểm tra đúng tên và context. |
| Function không gọi được | Method không có chữ ký phù hợp, không static hoặc không truy cập được. | Dùng public static method và lấy đúng `Method` signature bằng reflection. |
| Function được gọi nhiều lần | Expression được đánh giá nhiều lần hoặc function nằm trong selection/projection. | Thiết kế function thuần, rẻ và không có side effect; tính trước dữ liệu bên ngoài. |
| Rule gây truy vấn database hoặc HTTP lặp lại | Function ẩn truy cập tài nguyên bên ngoài. | Tải dữ liệu ở service layer một lần theo nhu cầu rồi truyền vào context. |
| Kết quả thay đổi giữa các lần đánh giá | Function phụ thuộc clock, random, mutable global state hoặc trạng thái bên ngoài. | Truyền thời điểm/giá trị đã chốt qua variable; giữ function xác định theo đối số. |
| Exception từ function làm hỏng evaluation | Method ném lỗi hoặc input không hợp lệ. | Xác thực trước, định nghĩa hợp đồng lỗi rõ và xử lý ở ranh giới ứng dụng. |
| Expression có thể gọi quá nhiều chức năng | Context expose helper/service quá rộng. | Thu hẹp function allowlist và kiểm tra các object/method khác trong context. |
| Function sửa dữ liệu ngoài ý muốn | Helper có side effect hoặc dùng trạng thái dùng chung. | Chuyển thao tác ghi sang Java service flow; function chỉ tính toán và trả kết quả. |

## Ghi nhớ

- Function SpEL là Java `Method` được đăng ký trong evaluation context và được gọi bằng `#functionName(...)`.
- Dùng public static method có chữ ký rõ ràng; đăng ký bằng `StandardEvaluationContext.registerFunction`.
- Function nên là phép tính thuần: cùng đối số cho cùng kết quả, không sửa trạng thái và không truy cập tài nguyên ngoài.
- SpEL không tự cache kết quả function; lời gọi chạy khi evaluation đi tới function.
- Function trong selection/projection có thể được gọi cho từng phần tử; expression được đánh giá lại cũng gọi function lại.
- Không thực hiện database, HTTP, file, gửi message hoặc cập nhật trạng thái trong function của rule.
- Tải dữ liệu bên ngoài ở service layer rồi truyền vào root object hoặc context variable.
- Phân biệt function `#fn(...)`, instance method `#object.method(...)`, bean reference `@bean.method(...)` và static method `T(Class).method(...)`.
- Chỉ đăng ký function cần thiết; function allowlist không thay thế việc giới hạn các object và resolver khác trong context.
- Xác thực input, giới hạn chi phí, xử lý exception rõ ràng và tránh che lỗi hạ tầng bằng giá trị mặc định.

## Tài liệu tham khảo

- [Spring Framework Reference — Functions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/functions.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [Spring Framework API — EvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)