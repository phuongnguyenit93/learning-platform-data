# Tính chi phối và các chuyển đổi luôn chính xác

Trong pattern matching, một giá trị chỉ nên được gán vào biến pattern khi việc chuyển đổi sang kiểu đích không làm mất thông tin. Java 26 mở rộng quy tắc này cho primitive type patterns, `instanceof` và `switch`; đồng thời siết chặt kiểm tra **dominance** để compiler phát hiện nhãn `case` không bao giờ có cơ hội được chọn.

Hai khái niệm gắn chặt với nhau:

- **Exact testing conversion**: phép chuyển đổi kiểm tra chỉ thành công nếu không làm mất thông tin và không ném exception.
- **Unconditionally exact conversion**: compiler có thể chứng minh trước rằng phép chuyển đổi luôn chính xác, hoặc chính xác với một constant expression cụ thể. Quy tắc này giúp compiler xác định pattern nào chi phối pattern khác.

## 1. Trạng thái tính năng cần biết

Primitive Types in Patterns, `instanceof`, and `switch` vẫn là **preview language feature** trong JDK 26 và JDK 27. Lịch sử các vòng preview:

| JDK | JEP | Trạng thái |
| --- | --- | --- |
| 23 | JEP 455 | Preview lần đầu |
| 24 | JEP 488 | Preview lần hai |
| 25 | JEP 507 | Preview lần ba |
| 26 | JEP 530 | Preview lần thứ tư; bổ sung định nghĩa unconditional exactness và siết dominance |
| 27 | JEP 532 | Preview lần thứ năm; JLS không có thay đổi quy phạm so với bản thứ tư |

Vì vậy, cú pháp primitive pattern được mô tả ở đây vẫn cần bật preview. Các tính năng pattern matching đã final trước đó, chẳng hạn pattern matching for `switch` với kiểu tham chiếu, vẫn dùng bình thường mà không cần cờ preview. Không được suy luận rằng toàn bộ pattern matching đều là preview chỉ vì phần primitive pattern chưa final.

## 2. Exact testing conversion là gì?

Trong testing context của `instanceof` hoặc `case` pattern, Java có thể thử chuyển giá trị từ kiểu nguồn sang kiểu mà pattern khai báo. Phép thử chỉ được xem là khớp khi chuyển đổi **exact**: kết quả giữ nguyên thông tin và không phát sinh exception. Nếu chuyển đổi bị mất thông tin, pattern không khớp; Java không âm thầm lấy giá trị đã bị cắt cụt để khởi tạo biến pattern.

Ví dụ với `int` và `byte`:

```java
static void printByteIfExact(int value) {
    if (value instanceof byte b) {
        System.out.println("Byte value: " + b);
    } else {
        System.out.println("Cannot represent this int exactly as byte");
    }
}
```

Với `value = 10`, chuyển đổi `int` sang `byte` giữ nguyên giá trị nên pattern khớp và `b` nhận `10`. Với `value = 1000`, ép kiểu thông thường `(byte) 1000` cho kết quả `-24`, làm thay đổi giá trị; vì vậy pattern `byte b` không khớp và nhánh `else` chạy.

Điều này khác với ép kiểu primitive thông thường:

```java
int value = 1000;
byte truncated = (byte) value; // -24: mất thông tin nhưng vẫn thực hiện
```

Pattern matching dùng phép thử an toàn. Khi phép chuyển đổi không chính xác, nó chỉ trả về kết quả không khớp; không đưa giá trị sai vào biến pattern.

Exactness có thể bị ảnh hưởng bởi nhiều dạng mất thông tin:

- **Magnitude**: độ lớn của giá trị thay đổi, ví dụ `1000` thành `-24` khi ép `int` sang `byte`.
- **Precision**: mất các bit có nghĩa, ví dụ một số `int` lớn được chuyển sang `float`.
- **Range**: giá trị vượt miền biểu diễn của kiểu đích.
- **Sign**: mất dấu, ví dụ `-0.0f` chuyển sang kiểu số nguyên thành `0`.

Với `float` sang `int`, `100.0f` có thể chuyển đổi chính xác thành `100`; `100.25f` không chính xác vì phép chuyển đổi số nguyên sẽ bỏ phần thập phân. `NaN`, hai giá trị vô cực và `-0.0f` cũng không chuyển đổi exact sang kiểu số nguyên: kết quả lần lượt có thể mất thông tin về giá trị đặc biệt hoặc dấu âm. Nếu phép thử không exact, primitive pattern không khớp.

## 3. Hai loại unconditionally exact conversion

Phần lớn testing conversion chỉ có thể xác định exact hay inexact khi có giá trị thực tại runtime. Tuy nhiên, có những trường hợp compiler chứng minh được tính chính xác ngay từ compile time. JLS gọi chúng là *unconditionally exact testing conversions* và chia thành hai loại.

### Type-based unconditionally exact

Đây là chuyển đổi luôn chính xác chỉ dựa trên hai kiểu nguồn và đích, bất kể giá trị cụ thể. Theo JLS, các trường hợp gồm:

- Identity conversion: kiểu nguồn và đích giống nhau.
- Exact widening primitive conversion: mở rộng primitive mà luôn giữ nguyên giá trị.
- Widening reference conversion: chuyển từ kiểu tham chiếu con sang kiểu cha/interface phù hợp.
- Boxing conversion: chuyển primitive sang wrapper tương ứng.
- Boxing conversion tiếp theo là widening reference conversion: ví dụ `int` sang `Integer`, rồi `Integer` sang `Number`.

Một số ví dụ chuyển đổi primitive luôn exact:

| Kiểu nguồn | Kiểu đích | Luôn exact? | Lý do |
| --- | --- | --- | --- |
| `byte` | `int` | Có | Mọi giá trị byte đều biểu diễn được bằng int |
| `short` | `long` | Có | Mở rộng miền biểu diễn, không mất giá trị |
| `int` | `double` | Có | double có đủ độ chính xác để biểu diễn mọi giá trị int |
| `float` | `double` | Có | Mọi giá trị float đều biểu diễn chính xác bằng double |
| `int` | `float` | Không | Một số int lớn mất bit chính xác khi chuyển sang float |
| `long` | `double` | Không | Một số long không thể biểu diễn chính xác bằng double |

Chú ý: *widening* không đồng nghĩa với *exact*. Các widening primitive conversion exact gồm chuyển giữa các kiểu số nguyên, `byte`/`short`/`char` sang kiểu dấu phẩy động, `int` sang `double`, và `float` sang `double`. `int` sang `float` và `long` sang `double` đều là widening primitive conversion nhưng có thể mất precision; chúng không thuộc loại type-based unconditionally exact.

### Value-based unconditionally exact

Một số chuyển đổi có thể mất thông tin với nhiều giá trị cùng kiểu, nhưng lại chính xác với một constant expression cụ thể. Compiler có thể tính trước giá trị đó và chứng minh phép chuyển đổi không mất thông tin. Đây là *value-based unconditionally exact conversion*.

Loại này chỉ áp dụng khi giá trị nguồn là constant expression và phép testing conversion của chính giá trị đó exact. Các nhóm chuyển đổi có thể xuất hiện gồm:

- Narrowing primitive conversion.
- Widening-and-narrowing primitive conversion.
- Widening primitive conversion vốn không exact với mọi giá trị của kiểu nguồn.

Ví dụ:

```java
// int -> byte là narrowing, nhưng literal 42 nằm trong miền byte.
// Compiler chứng minh được chuyển đổi này exact.
```

`int` literal `42` có thể chuyển sang `byte` mà không thay đổi giá trị. Tương tự, `int` literal `16_777_216` có thể chuyển sang `float` chính xác. Ngược lại, `16_777_217` không thể được biểu diễn chính xác bằng `float`; nó bị làm tròn thành giá trị float lân cận.

Một biến chỉ tình cờ đang chứa giá trị `42` không tự động trở thành constant expression. Ví dụ `int value = 42;` là biến có thể thay đổi; compiler không thể dựa vào giá trị hiện tại để kết luận một chuyển đổi luôn exact. Một constant variable như `static final int LIMIT = 42;` được khởi tạo bằng constant expression có thể được dùng như hằng compile-time.

## 4. Dominance trong switch

Một `case` bị **dominated** nếu mọi giá trị có thể khớp với nhãn đó đều đã khớp với một nhãn `case` đứng trước. Compiler báo lỗi compile-time vì nhãn phía sau không bao giờ được chọn.

Với pattern, một pattern `p` dominates pattern `q` khi mọi giá trị khớp `q` cũng khớp `p`. Quy tắc này dựa trên khả năng chuyển đổi chính xác giữa các kiểu, không dựa trên việc thử một vài giá trị runtime.

Ví dụ với kiểu tham chiếu:

```java
static String describe(Object value) {
    return switch (value) {
        case Object object -> "An object";
        case String text -> "A string"; // Compile-time error: dominated
    };
}
```

Mọi `String` đều là `Object`, nên `case Object object` đứng trước đã nhận tất cả giá trị mà `case String text` có thể nhận. Đặt pattern cụ thể trước pattern tổng quát:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "A string";
        case Object object -> "An object";
    };
}
```

Quy tắc tương tự áp dụng cho primitive pattern, nhưng compiler phải xét exactness của chuyển đổi primitive.

## 5. Type-based exactness quyết định dominance giữa primitive patterns

Xét switch có selector kiểu `float`:

```java
static String classify(float value) {
    return switch (value) {
        case int i -> "int: " + i;
        case byte b -> "byte: " + b; // Compile-time error: dominated
        default -> "not exactly representable as int";
    };
}
```

Compiler báo lỗi ở `case byte b`. Lý do không phải vì mọi `float` đều chuyển được thành `int` hay `byte`. Cả hai pattern đều chỉ khớp với các giá trị có thể chuyển đổi exact. Nhưng mọi giá trị `float` có thể chuyển đổi exact thành `byte` cũng chuyển đổi exact thành `int`, bởi `byte` sang `int` là exact widening primitive conversion.

Vì thế, bất cứ giá trị nào có thể khớp `case byte b` đều đã khớp `case int i` trước đó. `case int i` dominates `case byte b`.

Đổi thứ tự để pattern hẹp hơn được xét trước:

```java
static String classify(float value) {
    return switch (value) {
        case byte b -> "byte: " + b;
        case int i -> "int: " + i;
        default -> "not exactly representable as int";
    };
}
```

Ví dụ, `100.0f` khớp `byte` trước; `1000.0f` không thể biểu diễn bằng byte nhưng có thể chuyển exact thành int nên khớp nhánh int; `100.25f` không chuyển exact thành int nên đi vào `default`.

Điều này cũng giải thích vì sao `case int i` là unconditional khi selector có kiểu `int`: chuyển đổi identity luôn exact, nên pattern khớp mọi giá trị selector. Một pattern unconditional hoạt động như `default` và dominates các pattern hoặc `default` đặt sau nó:

```java
static String invalid(int value) {
    return switch (value) {
        case int i -> "int";
        case float f -> "float"; // Compile-time error: int pattern là unconditional
    };
}
```

Ngược lại, `case float f` không unconditional cho selector kiểu `int`, vì chuyển `int` sang `float` có thể mất precision. Nó chỉ khớp những giá trị int có thể biểu diễn chính xác bằng float.

## 6. Value-based exactness quyết định dominance với case constant

Một pattern đứng trước cũng có thể dominate một `case` constant nếu compiler chứng minh constant đó chuyển sang kiểu pattern một cách exact.

Ví dụ narrowing `int` sang `byte`:

```java
static String invalid(int value) {
    return switch (value) {
        case byte b -> "byte: " + b;
        case 42 -> "the number 42"; // Compile-time error: dominated
        default -> "outside byte range";
    };
}
```

`case byte b` chỉ khớp các giá trị int nằm trong miền byte. Literal `42` chắc chắn nằm trong miền đó, nên chuyển đổi từ int sang byte cho constant `42` là value-based unconditionally exact. Vì vậy nhánh `case 42` không thể được chọn.

Ví dụ widening `int` sang `float`:

```java
static String invalid(int value) {
    return switch (value) {
        case float f -> "exact float: " + f;
        case 16_777_216 -> "integer constant"; // Compile-time error: dominated
        default -> "not exactly representable as float";
    };
}
```

`16_777_216` biểu diễn chính xác được bằng `float`, nên nó đã khớp pattern `float f`. Đây là value-based unconditionally exact: kiểu `int` nói chung không chuyển sang `float` luôn chính xác, nhưng compiler biết literal cụ thể này chuyển chính xác.

Giá trị `16_777_217` thì khác: nó không biểu diễn chính xác được bằng float. Vì vậy pattern `float f` không nhận giá trị đó; compiler không xem một nhãn constant chứa giá trị này là bị pattern float dominate. Đừng khái quát rằng mọi số nguyên lớn hơn `16_777_216` đều không biểu diễn được bằng float; một số giá trị lớn hơn vẫn biểu diễn chính xác, nhưng không phải mọi số nguyên liên tiếp.

## 7. Guard và thứ tự nhãn case

Dominance chỉ xét nhãn pattern không guard, hoặc guard là constant expression `true`. Một guard thông thường có thể trả về `false`, vì vậy compiler không xem nó là nhãn bao phủ toàn bộ pattern.

Ví dụ hợp lệ:

```java
static String classify(int value) {
    return switch (value) {
        case int i when i > 0 -> "positive";
        case 1 -> "one";
        case int i -> "other integer";
    };
}
```

Guard `i > 0` không được xem là unconditional; compiler không kết luận nó dominates `case 1`. Tuy nhiên, khi `case int i` không có guard xuất hiện, pattern đó unconditional với selector int và phải là nhãn cuối cùng có thể nhận giá trị int.

Nếu guard là constant expression `true`, nhãn đó được xem như unguarded:

```java
switch (value) {
    case int i when true -> "all integers";
    case int i -> "unreachable"; // Compile-time error: dominated
}
```

> Một thứ tự dễ đọc trong nhiều switch có guard là: case constant cụ thể, pattern có guard, rồi pattern không guard tổng quát. Dù vậy, hãy kiểm tra dominance theo kiểu và exactness thực tế, không áp dụng thứ tự này như một quy tắc thay thế cho JLS.

## 8. Cách bật preview để thử trên JDK 26 và 27

Primitive Types in Patterns, `instanceof`, and `switch` chưa phải tính năng permanent. Cần dùng cùng một phiên bản JDK ở compile time và runtime, đồng thời bật preview ở cả hai bước.

Với JDK 26:

```bash
javac --enable-preview --release 26 -d out src/PrimitivePatternDemo.java
java --enable-preview -cp out PrimitivePatternDemo
```

Với JDK 27:

```bash
javac --enable-preview --release 27 -d out src/PrimitivePatternDemo.java
java --enable-preview -cp out PrimitivePatternDemo
```

Không biên dịch preview bằng JDK 26 rồi chạy class file đó trên JDK 27. Preview class file gắn với bản phát hành đã tạo ra nó; chuyển sang JDK khác cần đọc JEP/JLS của bản đích và biên dịch lại bằng đúng JDK đó.

## 9. Quy trình phân tích lỗi dominance

Khi compiler báo `this case label is dominated by a preceding case label`, hãy kiểm tra theo trình tự:

1. Xác định kiểu selector của `switch` và kiểu mà từng pattern khai báo.
2. Xác định testing conversion từ selector đến từng pattern có thể exact với những giá trị nào.
3. Với hai pattern, kiểm tra xem mọi giá trị có thể khớp pattern phía sau có luôn khớp pattern phía trước hay không.
4. Với case constant, kiểm tra pattern đứng trước có unconditional cho kiểu constant hay có value-based unconditionally exact conversion cho chính constant đó không.
5. Kiểm tra guard: guard không phải constant `true` thường không tạo dominance vì có thể thất bại.
6. Di chuyển nhãn cụ thể hơn lên trước, hoặc sửa pattern tổng quát khiến nhãn sau không còn reachable.

Nếu compiler báo lỗi chuyển đổi hoặc pattern không applicable, đó là vấn đề khác với dominance: trước tiên phải xác nhận testing conversion được phép giữa kiểu nguồn và kiểu pattern. Một conversion có thể tồn tại nhưng vẫn không exact với giá trị runtime.

## 10. Áp dụng vào mã production

Primitive pattern trong JDK 26 và 27 vẫn là preview. Nếu dự án cần ngôn ngữ ổn định, không bật preview chỉ để dùng cú pháp mới trong thư viện hoặc API công khai. Có thể dùng kiểm tra miền giá trị rõ ràng rồi mới ép kiểu:

```java
static Byte toByteIfInRange(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        return null;
    }
    return (byte) value;
}
```

Đây là cách hiện hành, không phụ thuộc preview. Khi tính năng được final ở một JDK tương lai, hãy kiểm tra lại JEP và tài liệu ngôn ngữ của phiên bản đó trước khi thay thế logic đã kiểm chứng.

## Ghi nhớ

- Testing conversion chỉ khớp khi không mất thông tin và không ném exception; phép chuyển đổi inexact làm pattern không khớp.
- Type-based unconditionally exact được chứng minh từ kiểu nguồn/đích; value-based unconditionally exact được chứng minh cho một constant expression cụ thể.
- Widening không luôn exact: `int` sang `float` và `long` sang `double` có thể mất precision.
- Một pattern không guard đứng trước dominates pattern phía sau nếu mọi giá trị khớp pattern sau cũng khớp pattern trước.
- Unconditional pattern hoạt động như `default`; constant có thể bị pattern trước dominate nếu chuyển đổi của constant exact.
- Guard không phải constant `true` thường không được dùng để kết luận dominance.
- Primitive Types in Patterns vẫn là preview trong JDK 26 (JEP 530) và JDK 27 (JEP 532); cần `--enable-preview` ở cả compile và run.

## Tài liệu tham khảo

- [Java Language Changes by Release, Java SE 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html) — thay đổi của JEP 530 trong JDK 26.
- [Pattern Matching with switch, Java SE 26](https://docs.oracle.com/en/java/javase/26/language/pattern-matching-switch.html) — dominance và unconditionally exact conversions, kèm ví dụ compile-time error.
- [Safe Casting with instanceof and switch, Java SE 26](https://docs.oracle.com/en/java/javase/26/language/safe-casting-instanceof-switch.html) — exact testing conversion giữa primitive types.
- [JLS Preview Specification, Java SE 26: Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/javase/specs/jls/se26/preview/specs/primitive-types-in-patterns-instanceof-switch-jls.html) — mục 5.7.1, 5.7.2, 14.11.1 và 14.30.3.
- [Java Language Changes by Release, Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html) — JEP 532, preview lần thứ năm.
- [JLS Preview Specification, Java SE 27: Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/javase/specs/jls/se27/preview/specs/primitive-types-in-patterns-instanceof-switch-jls.html) — xác nhận vòng preview thứ năm không có thay đổi quy phạm.
- [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530) và [JEP 532 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://openjdk.org/jeps/532) — mục tiêu và vòng đời tính năng.
