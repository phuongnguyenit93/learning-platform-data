# Biểu thức Boolean có giá trị null trong SpEL

## Mục tiêu

Trong Java, một thuộc tính kiểu `Boolean` có thể nhận ba trạng thái: `true`, `false` hoặc `null`. `null` thường có nghĩa là chưa được thiết lập, chưa biết hoặc không có dữ liệu. Khi dùng các giá trị này trong Spring Expression Language (SpEL), cần phân biệt việc đọc một giá trị Boolean trực tiếp, so sánh nó với `true`/`false`, và đưa nó vào toán tử logic.

Điểm quan trọng: SpEL không tự coi `null` là `false` trong toán tử `and`, `or` hoặc `not`. Toán tử logic cần một giá trị Boolean không null; nếu một toán hạng được đánh giá thành `null`, SpEL phát sinh `SpelEvaluationException` do không thể chuyển `null` thành `boolean`. Hãy kiểm tra null hoặc chọn giá trị mặc định một cách tường minh.

## 1. Boolean và Boolean có thể null

Java có hai kiểu thường gặp:

| Kiểu | Có thể null? | Ý nghĩa |
| --- | --- | --- |
| `boolean` | Không | Chỉ có `true` hoặc `false`; giá trị mặc định của field là `false`. |
| `Boolean` | Có | Có thể là `true`, `false` hoặc `null`; thường dùng khi trạng thái có thể chưa được cung cấp. |

Ví dụ, một cột database nullable, một field JSON bị bỏ qua hoặc một cấu hình tùy chọn có thể được ánh xạ vào `Boolean`. Nếu ứng dụng dùng `Boolean` để biểu diễn trạng thái ba giá trị, đừng tự động gộp `null` với `false` nếu nghiệp vụ cần phân biệt “chưa biết” và “đã tắt”.

## 2. Đọc trực tiếp một giá trị Boolean null

Giả sử root object có property `enabled` kiểu `Boolean` và giá trị hiện tại là `null`. Đọc property trực tiếp vẫn có thể trả về `null` nếu yêu cầu kiểu kết quả là `Boolean`:

```java
ExpressionParser parser = new SpelExpressionParser();
Feature feature = new Feature(); // feature.getEnabled() trả về null
StandardEvaluationContext context = new StandardEvaluationContext(feature);

Boolean rawValue = parser.parseExpression("enabled")
        .getValue(context, Boolean.class);
// rawValue == null
```

Đây là một lần đọc giá trị, chưa phải phép toán logic. Vì vậy có thể nhận được `null` mà không có lỗi. Cần giữ kiểu kết quả là `Boolean` nếu giá trị null là hợp lệ; đừng gán trực tiếp vào biến Java primitive `boolean`, vì Java sẽ phải unbox `null` và có thể ném `NullPointerException`.

## 3. Dùng toán tử logic với null

SpEL hỗ trợ `and` (`&&`), `or` (`||`) và `not` (`!`). Các toán tử này cần giá trị Boolean không null. Nếu toán hạng thực sự được đánh giá thành `null`, SpEL báo lỗi chuyển đổi kiểu thay vì áp dụng logic ba giá trị.

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `true and false` | `false` | Cả hai toán hạng đều là Boolean hợp lệ. |
| `true and null` | Lỗi | Toán hạng bên phải là null và cần chuyển thành boolean. |
| `false and null` | `false` | AND short-circuit: vế phải không được đánh giá. |
| `false or null` | Lỗi | OR phải đánh giá vế phải vì vế trái là false. |
| `true or null` | `true` | OR short-circuit: vế phải không được đánh giá. |
| `!null` | Lỗi | NOT cần một giá trị Boolean không null. |

Ví dụ khi property `enabled` là null:

```spel
enabled and true
enabled or false
!enabled
```

Cả ba biểu thức trên đều cần dùng `enabled` như một toán hạng logic và sẽ phát sinh `SpelEvaluationException` khi giá trị của property là null. Short-circuit chỉ giúp bỏ qua vế phải trong trường hợp vế trái đã quyết định kết quả (`false and ...`, `true or ...`); nó không biến một vế trái null thành false.

### Short-circuit vẫn có ý nghĩa

SpEL đánh giá vế trái trước. Với `and`, nếu vế trái là `false`, vế phải không được chạy. Với `or`, nếu vế trái là `true`, vế phải không được chạy. Điều này có thể dùng để bảo vệ một phép truy cập hoặc lời gọi method ở vế phải, nhưng vế trái vẫn phải là Boolean hợp lệ.

```spel
enabled != null and enabled
```

Nếu `enabled` là null, vế trái `enabled != null` trả về false và SpEL dừng đánh giá; nếu `enabled` không null, vế phải là Boolean true hoặc false. Tuy nhiên, trong nhiều trường hợp `enabled == true` dễ đọc và trực tiếp hơn.

## 4. So sánh null với true và false

Để kiểm tra trạng thái nullable, hãy so sánh property với `null`, `true` hoặc `false`. Phép so sánh bằng/khác phân biệt rõ null với hai giá trị Boolean:

| Biểu thức khi `enabled` là null | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `enabled == null` | `true` | Không có trạng thái được thiết lập. |
| `enabled != null` | `false` | Không có giá trị Boolean cụ thể. |
| `enabled == true` | `false` | Không thể khẳng định trạng thái bật. |
| `enabled == false` | `false` | Không thể khẳng định trạng thái tắt. |
| `enabled != true` | `true` | Không phải trạng thái true; bao gồm cả false và null. |

Ví dụ, nếu nghiệp vụ chỉ cho phép thực hiện thao tác khi feature được bật, dùng:

```spel
enabled == true
```

Không nên thay bằng `enabled != false` nếu null phải bị từ chối: với `enabled == null`, biểu thức `enabled != false` là true. Hãy viết điều kiện theo đúng ý nghĩa nghiệp vụ thay vì dựa vào cách diễn đạt phủ định.

## 5. Cung cấp giá trị mặc định bằng Elvis hoặc ternary

Nếu nghiệp vụ quy định null phải được xem như false, hãy thể hiện quy tắc đó rõ ràng trong biểu thức. Elvis operator (`?:`) trả về vế trái khi nó không null, và vế phải khi vế trái null:

```spel
enabled ?: false
```

Điều này giữ nguyên `true` và `false`, chỉ thay `null` bằng `false`. Có thể dùng kết quả đó trong toán tử logic:

```spel
(enabled ?: false) and (verified ?: false)
```

Nếu cần cú pháp tường minh hoặc phải hỗ trợ một phiên bản Spring chưa có Elvis operator, dùng toán tử ba ngôi:

```spel
enabled != null ? enabled : false
```

Không dùng cách mặc định này khi null có ý nghĩa nghiệp vụ riêng, chẳng hạn “chưa xác nhận”. Trong trường hợp đó, giữ nguyên ba trạng thái và xử lý từng nhánh:

```spel
enabled == null ? 'UNSPECIFIED' : (enabled ? 'ENABLED' : 'DISABLED')
```

Ví dụ trên trả về nhãn riêng cho trạng thái chưa xác định, bật và tắt.

## 6. Ví dụ Java hoàn chỉnh

Giả sử `Feature` có getter `getEnabled()` trả về `Boolean`. Có thể phân tích nhiều biểu thức để kiểm tra từng trạng thái:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(feature);

Boolean raw = parser.parseExpression("enabled")
        .getValue(context, Boolean.class);

Boolean isUnspecified = parser.parseExpression("enabled == null")
        .getValue(context, Boolean.class);

Boolean isEnabled = parser.parseExpression("enabled == true")
        .getValue(context, Boolean.class);

Boolean isDisabled = parser.parseExpression("enabled == false")
        .getValue(context, Boolean.class);

Boolean enabledWithDefault = parser.parseExpression("enabled ?: false")
        .getValue(context, Boolean.class);
```

Khi `feature.getEnabled()` trả về null, các kết quả lần lượt là `null`, `true`, `false`, `false` và `false`. Cách này giữ riêng thông tin gốc (`raw`) và giá trị đã áp dụng chính sách mặc định (`enabledWithDefault`).

Nếu biểu thức cần kết hợp nhiều cờ nullable, có thể chuẩn hóa từng cờ trước khi dùng `and`/`or`:

```java
Boolean allowed = parser.parseExpression(
        "(enabled ?: false) and (verified ?: false)")
        .getValue(context, Boolean.class);
```

Đoạn mã trên chỉ cho kết quả true khi cả hai cờ đều true; null được xử lý theo chính sách mặc định là false. Nếu muốn trạng thái null được giữ như “chưa xác định”, hãy kiểm tra null riêng trước khi thực hiện logic.

## 7. Kết hợp với safe navigation

Safe navigation (`?.`) giúp truy cập property mà không gây lỗi chỉ vì object ở bên trái là null. Tuy nhiên, kết quả của một phép truy cập an toàn có thể chính là null; safe navigation không biến kết quả đó thành false.

```spel
customer?.preferences?.marketingEnabled
```

Nếu `customer`, `preferences` hoặc `marketingEnabled` là null, kết quả có thể là null. Dùng phép so sánh để kiểm tra rõ ràng:

```spel
customer?.preferences?.marketingEnabled == true
```

Hoặc nếu nghiệp vụ xem null là false:

```spel
customer?.preferences?.marketingEnabled ?: false
```

Không nên viết `customer?.preferences?.marketingEnabled and consentGiven` nếu một trong các giá trị có thể null; hãy so sánh với true hoặc áp dụng giá trị mặc định trước.

## 8. Phân biệt lỗi SpEL và lỗi unboxing trong Java

Có hai tình huống lỗi khác nhau cần nhận diện:

1. **Lỗi trong biểu thức:** một toán tử logic như `and`, `or` hoặc `!` nhận toán hạng null. SpEL ném `SpelEvaluationException` với lỗi chuyển đổi `null` sang `boolean`.
2. **Lỗi sau khi đánh giá:** biểu thức chỉ trả về property null, `getValue(..., Boolean.class)` trả về null, nhưng code Java gán kết quả vào primitive `boolean`. Java unbox null và ném `NullPointerException`.

Ví dụ nên dùng kiểu wrapper nếu cần giữ null:

```java
Boolean result = parser.parseExpression("enabled")
        .getValue(context, Boolean.class);
```

Nếu hợp đồng của method yêu cầu kết quả primitive, hãy quyết định default ở một nơi rõ ràng:

```java
boolean result = Boolean.TRUE.equals(
        parser.parseExpression("enabled")
                .getValue(context, Boolean.class));
```

`Boolean.TRUE.equals(result)` chỉ trả về true khi giá trị là `Boolean.TRUE`; cả false và null đều cho kết quả false. Đây là một chính sách rõ ràng khi ứng dụng muốn chỉ chấp nhận trạng thái bật.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `SpelEvaluationException` khi dùng `enabled and ...` | `enabled` là `Boolean` null. | Kiểm tra `enabled != null`, so sánh `enabled == true`, hoặc áp dụng default trước khi dùng logic. |
| `!enabled` lỗi khi dữ liệu chưa có | NOT cần Boolean không null. | Dùng `enabled == false` nếu chỉ muốn kiểm tra false; dùng `!(enabled ?: false)` nếu chính sách xem null là false. |
| `enabled != false` cho kết quả true khi enabled null | `null` khác `false`; phép khác trả về true. | Dùng `enabled == true` nếu chỉ trạng thái bật mới hợp lệ. |
| `NullPointerException` ở code Java sau `getValue` | Giá trị Boolean null bị unbox vào primitive `boolean`. | Nhận kết quả bằng `Boolean` hoặc áp dụng default rõ ràng bằng `Boolean.TRUE.equals(...)`. |
| Safe navigation vẫn dẫn đến lỗi trong `and`/`or` | Safe navigation trả về null; toán tử logic không tự xử lý null. | So sánh kết quả với true hoặc dùng Elvis để chọn default. |
| Null bị âm thầm coi là false dù nghiệp vụ cần phân biệt | Biểu thức đã áp dụng default hoặc phủ định không phù hợp. | Giữ lại giá trị gốc và xử lý nhánh null riêng. |

## Ghi nhớ

- `Boolean` có thể null; primitive `boolean` chỉ có true/false.
- Đọc trực tiếp property nullable bằng kiểu `Boolean` có thể trả về null.
- `and`, `or`, `not` cần toán hạng Boolean không null; null trong toán hạng được đánh giá sẽ gây `SpelEvaluationException`.
- Short-circuit chỉ bỏ qua vế phải khi `false and ...` hoặc `true or ...`; nó không biến null thành false.
- Dùng `== null`, `== true`, `== false` để diễn đạt rõ từng trạng thái.
- `enabled ?: false` áp dụng chính sách default false mà vẫn giữ nguyên giá trị false.
- Safe navigation tránh lỗi truy cập object null nhưng kết quả vẫn có thể null.
- Phân biệt lỗi chuyển đổi bên trong SpEL với `NullPointerException` do Java unboxing.

## Tài liệu tham khảo

- [Spring Framework Reference — Operators](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)
- [Spring Framework Reference — Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html)
- [Spring Framework Reference — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework source — OpAnd](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/OpAnd.java)
- [Spring Framework source — OpOr](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/OpOr.java)
- [Spring Framework source — OperatorNot](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/OperatorNot.java)