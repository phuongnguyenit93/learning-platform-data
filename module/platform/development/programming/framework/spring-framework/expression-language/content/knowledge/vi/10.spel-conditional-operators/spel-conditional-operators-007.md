# Kiểm thử tất cả nhánh của biểu thức điều kiện trong SpEL

## 1. Vai trò của toán tử điều kiện

Spring Expression Language (SpEL) hỗ trợ biểu thức điều kiện để chọn một giá trị hoặc thực hiện một nhánh biểu thức dựa trên kết quả của một điều kiện Boolean. Đây là cách diễn đạt logic if-then-else ngay trong một expression, hữu ích khi xây dựng nhãn hiển thị, giá trị mặc định, quy tắc phân loại hoặc cấu hình phụ thuộc trạng thái.

Hai toán tử điều kiện chính trong SpEL là:

| Toán tử | Cú pháp | Ý nghĩa |
|---|---|---|
| Ternary (if-then-else) | `condition ? valueIfTrue : valueIfFalse` | Chọn một trong hai nhánh theo điều kiện. |
| Elvis | `value ?: defaultValue` | Dùng giá trị bên trái nếu hợp lệ; nếu null hoặc chuỗi rỗng thì dùng giá trị mặc định. |

Ternary có hai nhánh tường minh. Elvis là dạng rút gọn thường dùng để thay thế mẫu kiểm tra null/chuỗi rỗng rồi chọn giá trị dự phòng.

Khi kiểm thử, cần chạy đủ các đường đi có thể xảy ra. Với ternary, phải kiểm tra cả nhánh true và false. Với Elvis, cần kiểm tra giá trị có sẵn, null và chuỗi rỗng. Nếu biểu thức lồng nhau, mỗi điều kiện con cũng cần được đi qua cả hai kết quả.

## 2. Ternary operator: cú pháp và cách đánh giá

Cú pháp:

```text
condition ? expressionIfTrue : expressionIfFalse
```

- `condition` phải đánh giá thành Boolean.
- Nếu điều kiện là `true`, SpEL đánh giá và trả về `expressionIfTrue`.
- Nếu điều kiện là `false`, SpEL đánh giá và trả về `expressionIfFalse`.

Ví dụ đơn giản:

```java
ExpressionParser parser = new SpelExpressionParser();

String result = parser.parseExpression(
        "true ? 'approved' : 'rejected'")
        .getValue(String.class);

// result = "approved"
```

Đổi điều kiện thành `false` sẽ chọn nhánh sau dấu hai chấm:

```java
String result = parser.parseExpression(
        "false ? 'approved' : 'rejected'")
        .getValue(String.class);

// result = "rejected"
```

Điều kiện và hai nhánh đều là biểu thức SpEL. Vì vậy, mỗi nhánh có thể là literal, phép nối chuỗi, phép tính, property access, method invocation hoặc một biểu thức điều kiện khác.

### 2.1. Chỉ nhánh được chọn mới được đánh giá

Ternary chỉ đánh giá nhánh tương ứng với kết quả của điều kiện. Nhánh còn lại không được thực thi. Điều này quan trọng khi một nhánh gọi method, truy cập dữ liệu có thể không tồn tại hoặc thực hiện một phép tính có chi phí.

Ví dụ:

```text
#isMember ? #memberMessage : #guestMessage
```

Khi `#isMember` là true, chỉ `#memberMessage` được đánh giá. Khi false, chỉ `#guestMessage` được đánh giá.

Không đặt side effect bắt buộc phải chạy vào một nhánh có thể không được chọn. Cũng cần nhớ rằng nếu nhánh được chọn có lỗi, việc đánh giá expression sẽ thất bại dù nhánh còn lại có giá trị hợp lệ.

### 2.2. Điều kiện có thể là phép so sánh hoặc biểu thức logic

Điều kiện thường không phải literal Boolean mà là phép so sánh trên dữ liệu:

```java
int score = 82;

String grade = parser.parseExpression(
        "#score >= 50 ? 'PASS' : 'FAIL'")
        .getValue(context, String.class);
```

Có thể kết hợp nhiều điều kiện:

```text
(active and verified) ? 'ACTIVE_VERIFIED' : 'REVIEW_REQUIRED'
```

Điều kiện phải có kết quả Boolean hợp lệ. Nếu condition trả về null hoặc một giá trị không thể chuyển đổi thành Boolean, SpEL có thể phát sinh lỗi đánh giá; không nên coi null mặc nhiên là false.

## 3. Kiểm thử cả hai nhánh của ternary

Một kiểm thử chỉ chạy biểu thức với điều kiện true mới chứng minh được nhánh true. Nó không chứng minh nhánh false hoạt động. Để có branch coverage cơ bản, hãy dùng dữ liệu làm cho condition nhận cả hai kết quả và dùng giá trị đầu ra khác nhau để nhận biết nhánh nào đã chạy.

Ví dụ với biến trong EvaluationContext:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "#isMember ? 'MEMBER' : 'GUEST'");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("isMember", true);
String memberResult = expression.getValue(context, String.class);
// MEMBER

context.setVariable("isMember", false);
String guestResult = expression.getValue(context, String.class);
// GUEST
```

Có thể viết kiểm thử JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.expression.Expression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class TernaryExpressionTest {

    @Test
    void evaluatesBothTernaryBranches() {
        var parser = new SpelExpressionParser();
        Expression expression = parser.parseExpression(
                "#isMember ? 'MEMBER' : 'GUEST'");

        var context = new StandardEvaluationContext();

        context.setVariable("isMember", true);
        assertEquals("MEMBER",
                expression.getValue(context, String.class));

        context.setVariable("isMember", false);
        assertEquals("GUEST",
                expression.getValue(context, String.class));
    }
}
```

Hai assertion chứng minh cả hai kết quả. Nên giữ output của hai nhánh khác nhau; nếu cả hai cùng trả về một chuỗi, kiểm thử có thể vượt qua dù biểu thức chọn nhầm nhánh.

## 4. Kiểm thử biểu thức lồng nhau

Một ternary có thể chứa ternary khác ở một trong hai nhánh. Đây là cách biểu diễn nhiều mức phân loại mà không cần viết nhiều biểu thức riêng.

Ví dụ phân loại điểm:

```text
#score >= 80 ? 'A' : (#score >= 60 ? 'B' : 'C')
```

Luồng đánh giá:

1. Nếu `#score >= 80` đúng, kết quả là `A`; biểu thức bên trong nhánh false không cần đánh giá.
2. Nếu điều kiện đầu sai, SpEL kiểm tra `#score >= 60`.
3. Nếu điều kiện thứ hai đúng, kết quả là `B`.
4. Nếu cả hai điều kiện sai, kết quả là `C`.

Bộ dữ liệu nên đi qua đủ ba đường ra:

| Điểm | Điều kiện đầu `>= 80` | Điều kiện thứ hai `>= 60` | Kết quả mong đợi |
|---:|---|---|---|
| 90 | true | Không đánh giá | A |
| 70 | false | true | B |
| 50 | false | false | C |

Để kiểm tra chính xác các ngưỡng, bổ sung các giá trị biên:

| Điểm | Kết quả mong đợi | Mục đích |
|---:|---|---|
| 80 | A | Kiểm tra đúng tại ngưỡng A. |
| 79 | B | Kiểm tra ngay dưới ngưỡng A. |
| 60 | B | Kiểm tra đúng tại ngưỡng B. |
| 59 | C | Kiểm tra ngay dưới ngưỡng B. |

JUnit test có thể đặt nhiều giá trị vào cùng một biến context:

```java
@Test
void evaluatesEveryGradeBranchAndBoundary() {
    var parser = new SpelExpressionParser();
    var expression = parser.parseExpression(
            "#score >= 80 ? 'A' : (#score >= 60 ? 'B' : 'C')");
    var context = new StandardEvaluationContext();

    context.setVariable("score", 90);
    assertEquals("A", expression.getValue(context, String.class));

    context.setVariable("score", 70);
    assertEquals("B", expression.getValue(context, String.class));

    context.setVariable("score", 50);
    assertEquals("C", expression.getValue(context, String.class));

    context.setVariable("score", 80);
    assertEquals("A", expression.getValue(context, String.class));

    context.setVariable("score", 79);
    assertEquals("B", expression.getValue(context, String.class));

    context.setVariable("score", 60);
    assertEquals("B", expression.getValue(context, String.class));

    context.setVariable("score", 59);
    assertEquals("C", expression.getValue(context, String.class));
}
```

Đối với biểu thức lồng nhau, branch coverage yêu cầu mỗi decision có cả kết quả true và false. Việc chỉ nhận được đủ các giá trị đầu ra đôi khi chưa đủ nếu một decision có nhiều đường đi khác nhau; hãy kiểm tra từng điều kiện con theo thiết kế biểu thức.

## 5. Elvis operator: giá trị mặc định cho null và chuỗi rỗng

Elvis có cú pháp:

```text
value ?: defaultValue
```

SpEL trả về vế trái nếu vế trái không null và không phải chuỗi rỗng. Nếu vế trái là null hoặc `""`, SpEL trả về vế phải.

Ví dụ:

```java
String displayName = parser.parseExpression(
        "#name ?: 'Anonymous'")
        .getValue(context, String.class);
```

Bảng hành vi:

| Giá trị `#name` | Kết quả của `#name ?: 'Anonymous'` |
|---|---|
| `"Lan"` | `"Lan"` |
| `null` | `"Anonymous"` |
| `""` | `"Anonymous"` |
| `" "` | `" "` |

Một chuỗi chỉ chứa dấu cách không phải chuỗi rỗng, nên Elvis giữ nguyên chuỗi đó. Nếu nghiệp vụ muốn xem chuỗi chỉ có khoảng trắng là thiếu dữ liệu, hãy chuẩn hóa hoặc kiểm tra `trim()` một cách tường minh trước khi dùng Elvis.

Elvis không kiểm tra truthiness như một số ngôn ngữ khác. Giá trị Boolean `false` và số `0` không phải null hoặc chuỗi rỗng, vì vậy chúng được giữ lại:

| Giá trị bên trái | Kết quả |
|---|---|
| `false` | `false` |
| `0` | `0` |
| `null` | Dùng giá trị mặc định |
| `""` | Dùng giá trị mặc định |

### 5.1. Kiểm thử đủ các trường hợp Elvis

```java
@Test
void evaluatesElvisFallbackCases() {
    var parser = new SpelExpressionParser();
    var expression = parser.parseExpression(
            "#name ?: 'Anonymous'");
    var context = new StandardEvaluationContext();

    context.setVariable("name", "Lan");
    assertEquals("Lan", expression.getValue(context, String.class));

    context.setVariable("name", null);
    assertEquals("Anonymous",
            expression.getValue(context, String.class));

    context.setVariable("name", "");
    assertEquals("Anonymous",
            expression.getValue(context, String.class));

    context.setVariable("name", " ");
    assertEquals(" ",
            expression.getValue(context, String.class));
}
```

Bốn trường hợp trên kiểm tra giá trị bình thường, null, chuỗi rỗng và chuỗi chỉ có khoảng trắng. Nếu chỉ kiểm tra null, bạn sẽ bỏ sót hành vi đặc biệt của Elvis đối với chuỗi rỗng.

### 5.2. Dùng Elvis để cấu hình giá trị mặc định

Elvis thường được dùng trong `@Value`:

```java
@Value("#{systemProperties['pop3.port'] ?: 25}")
private int port;
```

Nếu system property `pop3.port` không có giá trị hoặc là chuỗi rỗng, giá trị mặc định `25` được chọn. Nếu có giá trị, SpEL trả về giá trị đó và Spring thực hiện chuyển đổi phù hợp với kiểu trường đích.

## 6. Elvis và ternary: chọn đúng dạng biểu thức

Elvis là dạng rút gọn của một mẫu ternary kiểm tra null/chuỗi rỗng. Hai biểu thức sau tương đương về ý nghĩa đối với chuỗi:

```text
#name != null and #name != '' ? #name : 'Anonymous'
```

```text
#name ?: 'Anonymous'
```

Elvis ngắn gọn hơn và xử lý cả chuỗi rỗng. Một ternary chỉ kiểm tra `#name != null` sẽ trả về chuỗi rỗng nếu `#name` là `""`, nên không hoàn toàn tương đương.

Dùng ternary khi có một điều kiện nghiệp vụ rõ ràng và hai nhánh mang ý nghĩa khác nhau, ví dụ:

```text
#order.total >= 100000 ? 'VIP' : 'STANDARD'
```

Dùng Elvis khi chỉ cần giá trị dự phòng cho dữ liệu null hoặc chuỗi rỗng:

```text
#order.note ?: 'No note'
```

Nếu điều kiện có nhiều tiêu chí, hãy viết biểu thức logic rõ ràng trong phần condition và đặt ngoặc quanh các nhóm con:

```text
(#order.total >= 100000 and #customer.active) ? 'PRIORITY' : 'NORMAL'
```

## 7. Kiểm thử giá trị trả về và kiểu dữ liệu

Hai nhánh ternary có thể trả về các giá trị khác nhau. Ví dụ:

```text
#isEnabled ? 1 : 0
```

Kết quả runtime phụ thuộc vào nhánh được chọn. Nếu Java code cần một kiểu cụ thể, hãy yêu cầu kiểu đó khi gọi `getValue()`:

```java
Integer enabledCode = parser.parseExpression(
        "#isEnabled ? 1 : 0")
        .getValue(context, Integer.class);
```

Nên thiết kế hai nhánh có kiểu kết quả tương thích với mục đích sử dụng. Nếu một nhánh trả về String còn nhánh kia trả về một object khác kiểu, caller phải xử lý kiểu kết quả thực tế hoặc cung cấp conversion phù hợp.

Condition phải đánh giá thành Boolean. Ví dụ sau là biểu thức điều kiện hợp lệ:

```text
#quantity > 0 ? 'IN_STOCK' : 'OUT_OF_STOCK'
```

Một giá trị String như `'true'` không nên được dùng thay cho Boolean condition. Hãy dùng Boolean thực hoặc một phép so sánh trả về Boolean.

## 8. Null và lỗi đánh giá trong biểu thức điều kiện

Ternary và Elvis có cách xử lý null khác nhau:

- Ternary cần condition Boolean. Nếu condition không thể đánh giá thành Boolean, SpEL phát sinh lỗi thay vì tự chọn nhánh false.
- Elvis chủ động xem null là trường hợp cần dùng giá trị dự phòng.
- Elvis cũng xem chuỗi rỗng là trường hợp cần dùng giá trị dự phòng.
- Một chuỗi chỉ có khoảng trắng vẫn là chuỗi không rỗng.
- Giá trị false hoặc 0 không kích hoạt fallback của Elvis.

Ví dụ, nếu `#user` có thể null, không nên truy cập `#user.active` trực tiếp trong condition. Có thể dùng short-circuit trong condition hoặc chọn nhánh bằng một kiểm tra null:

```text
#user != null and #user.active ? 'ACTIVE' : 'UNKNOWN'
```

Nếu một property Boolean có thể null, cần kiểm tra null trước:

```text
#enabled != null ? #enabled : false
```

Đừng nhầm Elvis với safe navigation. Safe navigation `?.` bảo vệ việc truy cập property/method khi đối tượng bên trái null; Elvis `?:` chọn giá trị thay thế khi chính giá trị bên trái null hoặc chuỗi rỗng. Chúng giải quyết hai nhu cầu khác nhau và có thể kết hợp khi cần.

## 9. Optional và khác biệt phiên bản

Từ Spring Framework 7.0, Elvis hỗ trợ `java.util.Optional` với cơ chế unwrap:

- Nếu vế trái là `Optional.empty()`, Elvis dùng vế phải.
- Nếu vế trái là Optional có giá trị, expression trả về giá trị bên trong Optional.

Ví dụ:

```java
context.setVariable("nickname", Optional.empty());

String displayName = parser.parseExpression(
        "#nickname ?: 'Anonymous'")
        .getValue(context, String.class);
// Anonymous
```

Với `Optional.of("Lan")`, kết quả là `"Lan"`.

Đây là khả năng được bổ sung từ Spring Framework 7.0. Nếu ứng dụng chạy Spring Framework 6.x hoặc cũ hơn, không dựa vào hành vi unwrap Optional này; hãy unwrap Optional trong Java hoặc tạo expression tương thích với phiên bản đang dùng.

## 10. Ma trận kiểm thử nhánh

Trước khi đưa một biểu thức điều kiện vào cấu hình hoặc ứng dụng, lập ma trận đầu vào/đầu ra để xác định từng nhánh phải chạy.

| Loại biểu thức | Trường hợp cần kiểm tra | Kết quả cần xác nhận |
|---|---|---|
| Ternary đơn | Condition true | Nhánh sau dấu `?` được trả về. |
| Ternary đơn | Condition false | Nhánh sau dấu `:` được trả về. |
| Ternary lồng nhau | Condition ngoài true | Nhánh ngoài true được chọn. |
| Ternary lồng nhau | Condition ngoài false, condition trong true | Nhánh true bên trong được chọn. |
| Ternary lồng nhau | Cả condition ngoài và trong false | Nhánh false cuối cùng được chọn. |
| Ternary có ngưỡng | Ngay dưới, tại và ngay trên mỗi ngưỡng | Không sai lệch ở điều kiện biên. |
| Elvis | Giá trị không null, không rỗng | Giữ nguyên giá trị trái. |
| Elvis | Null | Dùng giá trị mặc định. |
| Elvis | Chuỗi rỗng | Dùng giá trị mặc định. |
| Elvis | Chuỗi khoảng trắng | Giữ nguyên chuỗi khoảng trắng. |
| Elvis | false hoặc 0 | Giữ nguyên giá trị, không fallback. |
| Elvis với Optional (Spring 7.0+) | Optional rỗng và Optional có giá trị | Fallback hoặc unwrap đúng. |

Một ma trận kiểm thử tốt cần ghi cả đầu vào và kết quả mong đợi. Không chỉ ghi “đã chạy biểu thức”; cần chứng minh từng đường đi đã được kích hoạt.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Luôn nhận nhánh false | Condition luôn sai, đọc nhầm property hoặc dữ liệu test không bao phủ true. | Tạo test data khiến condition đúng và kiểm tra riêng giá trị condition. |
| Nhánh true hoạt động nhưng nhánh false lỗi | Nhánh false chưa được chạy trong kiểm thử trước đó. | Thêm test case condition false và kiểm tra expression của nhánh này. |
| Ternary lồng nhau trả kết quả sai | Thiếu ngoặc hoặc nhóm điều kiện không như ý. | Đặt ngoặc cho từng ternary con và lập bảng đường đi. |
| Không dùng được condition null | Null không phải Boolean false. | Kiểm tra null tường minh trước khi dùng condition. |
| Elvis trả về chuỗi chỉ có khoảng trắng | Chuỗi đó không rỗng. | Chuẩn hóa chuỗi hoặc kiểm tra trim theo quy tắc nghiệp vụ. |
| Elvis giữ lại false hoặc 0 | Đây là giá trị hợp lệ, không phải null hoặc empty String. | Nếu nghiệp vụ muốn fallback cả false/0, viết điều kiện ternary rõ ràng. |
| Elvis với Optional không unwrap | Phiên bản Spring chưa hỗ trợ. | Chỉ dựa vào Optional support từ Spring Framework 7.0; phiên bản cũ cần unwrap trong Java. |
| Nhánh được chọn phát sinh lỗi | Expression trong nhánh đó sai hoặc dữ liệu không đáp ứng yêu cầu. | Kiểm thử riêng từng nhánh và xác nhận object/property/method được dùng. |
| Kiểu kết quả không như mong đợi | Hai nhánh trả về kiểu khác nhau hoặc caller yêu cầu kiểu không tương thích. | Dùng kiểu đầu ra nhất quán hoặc chuyển đổi rõ ràng bằng `getValue()`/ConversionService. |
| Kiểm thử pass nhưng chưa đủ branch coverage | Chỉ chạy một kết quả condition hoặc bỏ qua nhánh con. | Theo dõi từng decision và thêm test cho true/false ở mỗi cấp. |

## 12. Quy trình kiểm thử thực tế

1. Viết biểu thức với tên condition và nhánh có ý nghĩa, tránh các literal giống nhau khiến khó nhận biết kết quả.
2. Liệt kê từng decision trong biểu thức, kể cả decision nằm trong ternary lồng nhau.
3. Với mỗi decision, chuẩn bị ít nhất một bộ dữ liệu làm condition true và một bộ làm condition false.
4. Với điều kiện so sánh ngưỡng, kiểm tra giá trị ngay dưới, đúng bằng và ngay trên ngưỡng.
5. Với Elvis, kiểm tra null, chuỗi rỗng, chuỗi có nội dung và chuỗi khoảng trắng; kiểm tra false/0 nếu kiểu dữ liệu cho phép.
6. Kiểm tra nhánh được chọn có thể đánh giá thành công và trả đúng kiểu.
7. Chạy lại expression với cùng EvaluationContext hoặc cập nhật biến context giữa các lần chạy để chứng minh mỗi nhánh.
8. Đối chiếu kết quả thực tế với ma trận mong đợi và lưu các trường hợp biên thành automated tests.

Tách việc kiểm thử expression khỏi logic nghiệp vụ của ứng dụng giúp xác định lỗi nằm ở condition, dữ liệu đầu vào, nhánh được chọn hay quá trình chuyển đổi kiểu.

## 13. Ghi nhớ

- Ternary có dạng `condition ? trueExpression : falseExpression`; condition phải là Boolean.
- SpEL chỉ đánh giá nhánh được chọn, nên cả hai nhánh cần được kiểm thử riêng.
- Với ternary lồng nhau, kiểm tra true/false của từng decision và các giá trị biên.
- Elvis có dạng `value ?: defaultValue`; fallback khi giá trị bên trái null hoặc chuỗi rỗng.
- Chuỗi khoảng trắng, Boolean false và số 0 không kích hoạt fallback của Elvis.
- Spring Framework 7.0 hỗ trợ unwrap Optional trong Elvis; kiểm tra phiên bản trước khi sử dụng.
- Safe navigation `?.` khác Elvis `?:`: một toán tử bảo vệ truy cập, toán tử kia chọn giá trị mặc định.
- Dùng ma trận đầu vào/đầu ra để chứng minh tất cả nhánh và lưu chúng thành automated tests.

## Tài liệu tham khảo

- [Spring Framework Reference — Ternary Operator (If-Then-Else)](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-ternary.html)
- [Spring Framework Reference — The Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpEL Ternary AST Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/Ternary.html)
- [SpEL Elvis AST Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/Elvis.html)
