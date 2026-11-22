# Kiểm tra bảng chân trị của biểu thức logic trong SpEL

## 1. Vai trò của toán tử logic

Spring Expression Language (SpEL) hỗ trợ các biểu thức Boolean để kết hợp nhiều điều kiện thành một kết quả duy nhất. Toán tử logic thường được dùng sau một phép so sánh, khi kiểm tra trạng thái của object hoặc khi cần diễn đạt quy tắc nghiệp vụ như quyền truy cập, điều kiện kích hoạt và trạng thái hợp lệ.

SpEL có ba toán tử logic:

| Ý nghĩa | Dạng chữ | Dạng ký hiệu | Số toán hạng |
|---|---|---|---:|
| AND — và | `and` | `&&` | 2 |
| OR — hoặc | `or` | `||` | 2 |
| NOT — phủ định | `not` | `!` | 1 |

Dạng chữ và dạng ký hiệu có cùng ý nghĩa. Các từ khóa `and`, `or`, `not` không phân biệt chữ hoa/chữ thường. Ví dụ, `true AND false` có cùng kết quả với `true and false`.

Toán tử AND và OR là toán tử nhị phân vì cần hai biểu thức Boolean. NOT là toán tử một ngôi vì chỉ phủ định một biểu thức Boolean.

## 2. Bảng chân trị cơ bản

Bảng chân trị liệt kê kết quả của một biểu thức logic với mọi tổ hợp giá trị đầu vào có thể có. Với hai biến Boolean A và B, có bốn tổ hợp: cả hai đúng, chỉ A đúng, chỉ B đúng và cả hai sai.

### 2.1. AND — cả hai điều kiện phải đúng

Biểu thức `A and B` chỉ trả về `true` khi cả A và B đều là `true`:

| A | B | A AND B |
|---|---|---|
| true | true | **true** |
| true | false | false |
| false | true | false |
| false | false | false |

Có thể đọc AND như một quy tắc yêu cầu đồng thời: tất cả điều kiện phải được thỏa mãn.

Ví dụ:

```java
boolean result = parser.parseExpression("true and false")
        .getValue(Boolean.class);
// result == false
```

Dạng ký hiệu tương đương:

```java
boolean result = parser.parseExpression("true && false")
        .getValue(Boolean.class);
// result == false
```

Ứng dụng thường gặp: người dùng phải đang hoạt động **và** có quyền quản trị mới được thực hiện thao tác.

```text
active and administrator
```

Nếu một trong hai điều kiện sai, toàn bộ biểu thức AND sai.

### 2.2. OR — chỉ cần ít nhất một điều kiện đúng

Biểu thức `A or B` trả về `true` khi A đúng, B đúng hoặc cả hai cùng đúng. Nó chỉ sai khi cả A và B đều sai:

| A | B | A OR B |
|---|---|---|
| true | true | **true** |
| true | false | **true** |
| false | true | **true** |
| false | false | false |

OR trong SpEL là OR bao hàm (inclusive OR), không phải XOR. Vì vậy, trường hợp cả hai điều kiện cùng đúng vẫn cho kết quả `true`.

Ví dụ:

```java
boolean result = parser.parseExpression("true or false")
        .getValue(Boolean.class);
// result == true
```

Dạng ký hiệu tương đương:

```java
boolean result = parser.parseExpression("true || false")
        .getValue(Boolean.class);
// result == true
```

Ứng dụng thường gặp: người dùng được phép truy cập nếu là chủ sở hữu **hoặc** là quản trị viên.

```text
owner or administrator
```

Chỉ khi cả hai điều kiện đều sai, kết quả OR mới là `false`.

### 2.3. NOT — đảo ngược giá trị Boolean

NOT chỉ nhận một toán hạng và đảo giá trị của nó:

| A | NOT A |
|---|---|
| true | false |
| false | true |

Ví dụ:

```java
boolean result = parser.parseExpression("!true")
        .getValue(Boolean.class);
// result == false
```

Dạng chữ tương đương:

```java
boolean result = parser.parseExpression("not true")
        .getValue(Boolean.class);
// result == false
```

NOT hữu ích khi cần diễn đạt điều kiện phủ định, ví dụ `not disabled` hoặc `!blocked`. Với biểu thức phức tạp, nên đặt toán hạng trong ngoặc để xác định rõ phạm vi phủ định: `not (A and B)`.

## 3. Cách tự lập và kiểm tra bảng chân trị

Để kiểm tra một biểu thức logic có nhiều biến, hãy liệt kê tất cả tổ hợp đầu vào rồi tính kết quả theo từng toán tử.

Với n biến Boolean độc lập, có (2^n) tổ hợp cần kiểm tra. Ví dụ:

- 1 biến: 2 tổ hợp.
- 2 biến: 4 tổ hợp.
- 3 biến: 8 tổ hợp.
- 4 biến: 16 tổ hợp.

Xét biểu thức:

```text
(A and B) or not C
```

Thực hiện theo thứ tự:

1. Tính `A and B`.
2. Tính `not C`.
3. Lấy kết quả của hai bước trên để tính OR.

Bảng chân trị đầy đủ:

| A | B | C | A AND B | NOT C | (A AND B) OR NOT C |
|---|---|---|---|---|---|
| false | false | false | false | true | **true** |
| false | false | true | false | false | false |
| false | true | false | false | true | **true** |
| false | true | true | false | false | false |
| true | false | false | false | true | **true** |
| true | false | true | false | false | false |
| true | true | false | true | true | **true** |
| true | true | true | true | false | **true** |

Kết quả cuối cùng chỉ sai khi C đúng đồng thời A và B không cùng đúng. Khi A và B đều đúng, biểu thức luôn đúng bất kể C.

## 4. Đánh giá biểu thức bằng Java

Có thể dùng `SpelExpressionParser` để kiểm tra một biểu thức trực tiếp mà không cần root object:

```java
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

public class LogicExpressionExample {
    public static void main(String[] args) {
        ExpressionParser parser = new SpelExpressionParser();

        boolean andResult = parser.parseExpression(
                "true and false").getValue(Boolean.class);

        boolean orResult = parser.parseExpression(
                "true or false").getValue(Boolean.class);

        boolean notResult = parser.parseExpression(
                "not false").getValue(Boolean.class);

        System.out.println(andResult); // false
        System.out.println(orResult);  // true
        System.out.println(notResult); // true
    }
}
```

Để kiểm tra cả bốn trường hợp của AND và OR, có thể tạo biểu thức từ các giá trị đầu vào:

```java
ExpressionParser parser = new SpelExpressionParser();

boolean[] values = {false, true};

for (boolean a : values) {
    for (boolean b : values) {
        String andExpression = a + " and " + b;
        String orExpression = a + " or " + b;

        Boolean andResult = parser.parseExpression(andExpression)
                .getValue(Boolean.class);
        Boolean orResult = parser.parseExpression(orExpression)
                .getValue(Boolean.class);

        System.out.printf(
                "A=%s, B=%s, AND=%s, OR=%s%n",
                a, b, andResult, orResult);
    }
}
```

Vòng lặp sinh đủ bốn tổ hợp của hai biến. Kết quả in ra có thể đối chiếu trực tiếp với bảng chân trị ở phần trước.

## 5. Kết hợp toán tử logic với phép so sánh

Trong ứng dụng, toán hạng của AND/OR/NOT thường là biểu thức so sánh thay vì literal `true` hoặc `false`.

Ví dụ, một đơn hàng chỉ được duyệt khi tổng tiền đạt ngưỡng và trạng thái là `READY`:

```text
total >= 100000 and status == 'READY'
```

Ví dụ, tài khoản được phép thao tác nếu là quản trị viên hoặc chủ sở hữu tài nguyên:

```text
administrator or owner
```

Ví dụ, tài khoản không bị khóa và đã xác minh email:

```text
not locked and emailVerified
```

Các phép so sánh như `==`, `!=`, `>`, `>=`, `<`, `<=` tạo ra kết quả Boolean, có thể dùng trực tiếp làm toán hạng logic. Các biểu thức property như `active` cũng có thể dùng trực tiếp nếu giá trị đọc được là Boolean hoặc chuyển đổi được sang Boolean.

### 5.1. Đánh giá với root object

Giả sử ứng dụng có lớp người dùng:

```java
public class User {
    private int age;
    private boolean active;
    private boolean administrator;

    public int getAge() {
        return age;
    }

    public boolean isActive() {
        return active;
    }

    public boolean isAdministrator() {
        return administrator;
    }
}
```

Có thể đặt đối tượng làm root object rồi đánh giá biểu thức:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context =
        new StandardEvaluationContext();

User user = loadUser();

Expression expression = parser.parseExpression(
        "age >= 18 and active and (administrator or age >= 21)");

Boolean allowed = expression.getValue(context, user, Boolean.class);
```

Biểu thức yêu cầu người dùng từ 18 tuổi, đang hoạt động và đồng thời là quản trị viên hoặc từ 21 tuổi trở lên. Việc dùng ngoặc quanh phần OR giúp thể hiện rõ nhóm điều kiện.

## 6. Thứ tự kết hợp và dấu ngoặc

Khi một biểu thức có nhiều toán tử, dấu ngoặc giúp người đọc xác định chính xác nhóm điều kiện cần tính trước. Hãy dùng dấu ngoặc chủ động thay vì để quy tắc ưu tiên toán tử trở thành giả định khó nhận ra.

Ví dụ:

```text
(active and verified) or administrator
```

Biểu thức này có nghĩa là người dùng được chấp nhận nếu vừa hoạt động vừa xác minh, hoặc là quản trị viên.

Trong khi đó:

```text
active and (verified or administrator)
```

Biểu thức này yêu cầu người dùng phải hoạt động; sau đó chỉ cần đã xác minh hoặc là quản trị viên.

Hai biểu thức không tương đương:

| active | verified | administrator | (active AND verified) OR administrator | active AND (verified OR administrator) |
|---|---|---|---|---|
| false | false | false | false | false |
| false | false | true | true | false |
| false | true | false | false | false |
| false | true | true | true | false |
| true | false | false | false | false |
| true | false | true | true | true |
| true | true | false | true | true |
| true | true | true | true | true |

Khác biệt rõ nhất xuất hiện khi `administrator = true` nhưng `active = false`: biểu thức thứ nhất cho phép, còn biểu thức thứ hai từ chối.

## 7. Các quy luật logic hữu ích

Các quy luật đại số Boolean giúp rút gọn hoặc kiểm tra biểu thức.

### 7.1. Luật đồng nhất

```text
A and true  = A
A or false  = A
```

AND với `true` và OR với `false` giữ nguyên giá trị ban đầu.

### 7.2. Luật triệt tiêu

```text
A and false = false
A or true   = true
```

AND với `false` luôn sai; OR với `true` luôn đúng.

### 7.3. Luật phủ định kép

```text
not (not A) = A
```

Phủ định hai lần khôi phục giá trị ban đầu.

### 7.4. Luật De Morgan

```text
not (A and B) = (not A) or (not B)
not (A or B)  = (not A) and (not B)
```

Ví dụ, phủ định câu “người dùng hoạt động và đã xác minh” tương đương với “người dùng không hoạt động hoặc chưa xác minh”:

```text
not (active and verified)
```

tương đương:

```text
not active or not verified
```

Có thể dùng các quy luật này để phát hiện lỗi khi chuyển một điều kiện nghiệp vụ sang biểu thức SpEL.

## 8. Short-circuit: bỏ qua toán hạng không cần thiết

SpEL đánh giá AND và OR theo cơ chế short-circuit:

- Với `A and B`, nếu A là `false`, SpEL đã biết kết quả cuối là `false`, nên không cần đánh giá B.
- Với `A or B`, nếu A là `true`, SpEL đã biết kết quả cuối là `true`, nên không cần đánh giá B.

Ví dụ:

```text
false and checkPermission()
true or loadFallback()
```

Trong biểu thức thứ nhất, `checkPermission()` không được gọi. Trong biểu thức thứ hai, `loadFallback()` không được gọi.

Short-circuit có ý nghĩa thực tế khi toán hạng bên phải có thể tốn chi phí, phụ thuộc dữ liệu hoặc có side effect. Vì toán hạng bên phải có thể bị bỏ qua, không đặt thao tác bắt buộc phải chạy vào vị trí đó. Hãy sắp xếp điều kiện để kiểm tra đơn giản và an toàn trước khi thực hiện thao tác tốn kém.

Ví dụ, kiểm tra một tham chiếu trước khi đọc thuộc tính sâu:

```text
user != null and user.active
```

Nếu `user != null` là `false`, phần `user.active` không được đánh giá. Đây là cách bảo vệ biểu thức khỏi việc truy cập thuộc tính trên root object null trong trường hợp này.

Short-circuit không thay đổi bảng chân trị; nó chỉ thay đổi việc có cần tính toán toán hạng bên phải hay không.

## 9. Boolean, null và lỗi kiểu dữ liệu

Toán tử logic cần các toán hạng có thể được đánh giá thành Boolean. Với biểu thức Boolean thông thường, hãy dùng literal `true` và `false` không có dấu nháy:

```text
true and false
```

Không nhầm chúng với chuỗi:

```text
'true' and 'false'
```

Hai giá trị có dấu nháy là String literal, không phải Boolean literal. SpEL có thể áp dụng cơ chế chuyển đổi kiểu trong một số trường hợp, nhưng không nên dựa vào chuyển đổi ngầm để viết điều kiện logic dễ hiểu.

Một toán hạng có giá trị `null` không phải là giá trị Boolean thứ ba trong bảng chân trị. Khi SpEL không thể chuyển giá trị đó thành Boolean, quá trình đánh giá có thể phát sinh `SpelEvaluationException` do lỗi chuyển đổi kiểu. Vì vậy, không áp dụng trực tiếp bảng chân trị hai giá trị cho dữ liệu null như thể null đồng nghĩa với false.

Ví dụ, nếu `user` có thể null, kiểm tra trước khi truy cập thuộc tính:

```text
user != null and user.active
```

Nếu một property Boolean có thể chứa null (ví dụ `Boolean` thay vì `boolean`), hãy xử lý null rõ ràng trước khi dùng property đó làm toán hạng:

```text
enabled != null and enabled
```

Khi kiểm tra null, dùng toán tử so sánh `== null` hoặc `!= null`; không viết `not null` để thay cho kiểm tra giá trị null.

## 10. Những lỗi thường gặp

| Lỗi hoặc kết quả bất ngờ | Nguyên nhân | Cách xử lý |
|---|---|---|
| AND trả về false dù một điều kiện đúng | AND yêu cầu cả hai điều kiện đều đúng. | Kiểm tra từng toán hạng theo bảng chân trị AND. |
| OR trả về true khi cả hai điều kiện đều đúng | OR là phép hoặc bao hàm, không phải XOR. | Nếu cần loại trừ lẫn nhau, viết biểu thức XOR bằng các tổ hợp AND/OR/NOT. |
| NOT phủ định sai phần biểu thức mong muốn | Phạm vi toán hạng chưa rõ. | Dùng ngoặc, ví dụ `not (A and B)`. |
| Viết `&` hoặc `|` nhưng không hoạt động như mong muốn | Dạng ký hiệu của SpEL là `&&` và `||`. | Dùng đúng toán tử hai ký tự hoặc dạng chữ. |
| Chuỗi `'true'` không hoạt động như Boolean | Giá trị có dấu nháy là String. | Dùng literal `true`/ `false` hoặc chuyển đổi kiểu một cách rõ ràng. |
| Đánh giá lỗi khi một property là null | Toán hạng logic không có giá trị Boolean hợp lệ. | Kiểm tra null trước bằng `!= null`. |
| Gọi method bên phải nhưng method không chạy | Short-circuit đã xác định kết quả từ toán hạng bên trái. | Không đặt side effect bắt buộc ở toán hạng có thể bị bỏ qua. |
| Biểu thức dài khó đọc hoặc sai nhóm | Không thể hiện nhóm điều kiện bằng dấu ngoặc. | Chia thành nhóm có ngoặc và kiểm tra bảng chân trị. |
| So sánh cho kết quả khác mong đợi | Giá trị hoặc kiểu của toán hạng không như dự kiến. | Kiểm tra giá trị runtime, phép so sánh và kiểu dữ liệu trước khi kết hợp logic. |

## 11. Quy trình kiểm tra một biểu thức logic

Khi nhận một biểu thức nghiệp vụ cần kiểm tra, có thể làm theo quy trình sau:

1. Xác định tất cả biến Boolean hoặc phép so sánh tạo ra Boolean.
2. Đặt dấu ngoặc để biểu diễn các nhóm điều kiện rõ ràng.
3. Liệt kê mọi tổ hợp đầu vào; với n biến, dùng (2^n) dòng.
4. Tính NOT trước trên toán hạng tương ứng, sau đó tính các nhóm AND/OR theo cấu trúc biểu thức.
5. Đối chiếu kết quả với ý nghĩa nghiệp vụ bằng các trường hợp đúng, sai và biên.
6. Kiểm tra thêm trường hợp null hoặc dữ liệu không đúng kiểu vì các trường hợp này có thể gây lỗi đánh giá thay vì tạo kết quả true/false.
7. Chạy lại biểu thức bằng `SpelExpressionParser` với context và root object giống môi trường ứng dụng.

Bảng chân trị giúp chứng minh logic cho các đầu vào Boolean. Việc kiểm thử trong SpEL còn phải tính đến cách property, method, converter và EvaluationContext cung cấp giá trị cho các toán hạng.

## 12. Ghi nhớ

- SpEL có AND (`and`/`&&`), OR (`or`/`||`) và NOT (`not`/`!`).
- AND chỉ đúng khi cả hai toán hạng đúng; OR đúng khi ít nhất một toán hạng đúng; NOT đảo giá trị.
- OR là inclusive OR: cả hai toán hạng cùng đúng vẫn cho kết quả đúng.
- Với n biến Boolean, bảng chân trị có (2^n) tổ hợp.
- Dùng dấu ngoặc để thể hiện nhóm điều kiện và tránh nhầm ý nghĩa biểu thức.
- AND/OR có short-circuit: toán hạng bên phải có thể không được đánh giá.
- Toán hạng phải trả về giá trị Boolean hợp lệ; null và dữ liệu sai kiểu có thể gây lỗi chuyển đổi.
- Dùng bảng chân trị để kiểm tra logic và dùng SpEL parser để kiểm tra hành vi đánh giá thực tế.

## Tài liệu tham khảo

- [Spring Framework Reference — Operators](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [SpEL OpAnd Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/OpAnd.html)
- [SpEL OpOr Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/OpOr.html)
