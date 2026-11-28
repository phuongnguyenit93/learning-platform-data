# `switch` với selector nguyên thủy và các nhãn tương thích

Java 26 mở rộng `switch` để biểu thức điều khiển có thể mang mọi kiểu nguyên thủy: `byte`, `short`, `char`, `int`, `long`, `float`, `double` và `boolean`. Các kiểu đóng hộp tương ứng (`Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`, `Boolean`) cũng được hỗ trợ. Nhờ đó, có thể phân nhánh trực tiếp theo giá trị `long`, số thực hoặc boolean, đồng thời dùng primitive type pattern để kiểm tra một phép chuyển kiểu có giữ nguyên giá trị hay không.

Phần mở rộng này thuộc **preview feature** Primitive Types in Patterns, `instanceof`, and `switch`: lần preview thứ tư trong Java 26 (JEP 530). Tại ngày 27-11-2026, Java 27 tiếp tục preview lần thứ năm (JEP 532), chưa trở thành tính năng ổn định. Các ví dụ dùng selector `long`, `float`, `double`, `boolean` hoặc primitive type pattern phải biên dịch và chạy với preview được bật. [Java Language Updates 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html) · [Java Language Changes Summary 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html).

## 1. Phân biệt selector, constant label và pattern label

Một `switch` có ba phần cần đọc tách biệt:

- **Selector expression** là biểu thức trong ngoặc `switch (...)`. Kiểu tĩnh của biểu thức quyết định những nhãn `case` nào tương thích.
- **Constant label** là nhãn chứa giá trị hằng, ví dụ `case 10L`, `case 1.5f` hoặc `case true`. Nó so sánh selector với giá trị cụ thể.
- **Pattern label** là nhãn mô tả một kiểu và có thể khai báo biến mẫu, ví dụ `case byte b` hoặc `case long n`. Nó kiểm tra xem giá trị có thể được chuyển chính xác sang kiểu trong pattern hay không; nếu khớp, biến mẫu được khởi tạo bằng giá trị đã chuyển.

Ví dụ, trong `switch (amount)`, `amount` là selector. `case 100L` là constant label, còn `case long n` là pattern label. Hai loại nhãn có quy tắc tương thích khác nhau: constant phải phù hợp với kiểu selector theo assignment compatibility hoặc quy tắc kiểu chính xác của JLS; pattern phải áp dụng được với kiểu selector theo testing conversion.

Java 26 hỗ trợ cả `switch` statement và `switch` expression. Dùng cú pháp mũi tên `->` để mỗi nhánh chạy độc lập, không rơi tiếp sang nhánh kế tiếp:

```java
String result = switch (statusCode) {
    case 200 -> "OK";
    case 404 -> "Not Found";
    default -> "Other status";
};
```

`switch` expression trả về một giá trị; mọi đường đi phải tạo ra giá trị hoặc ném ngoại lệ. `switch` statement dùng để thực hiện hành động. Khi statement là enhanced switch (ví dụ selector mới `long`, `float`, `double`, `boolean`, hoặc có pattern/null label), khối switch cũng phải exhaustive. Vì vậy, hãy kiểm tra tính đầy đủ của các nhánh thay vì giả định statement luôn có thể bỏ sót một giá trị.

## 2. Selector nào chấp nhận constant label nào?

JLS phân biệt nhóm kiểu selector cũ với nhóm được mở rộng trong Java 26:

| Kiểu selector | Constant label tương thích | Ví dụ |
|---|---|---|
| `byte`, `short`, `char`, `int` | Constant expression phải assignment-compatible với kiểu selector. | `switch (int n) { case 1 -> ...; }` |
| `Byte`, `Short`, `Character`, `Integer` | Constant expression phải assignment-compatible với kiểu selector; giá trị boxed được unbox khi so sánh. | `switch (Integer n) { case 1 -> ...; }` |
| `long` | Kiểu của constant expression phải chính xác là `long`. | `case 1L -> ...` |
| `float` | Kiểu của constant expression phải chính xác là `float`. | `case 1.0f -> ...` |
| `double` | Kiểu của constant expression phải chính xác là `double`. | `case 1.0d -> ...` |
| `boolean` | Kiểu của constant expression phải chính xác là `boolean`. | `case true -> ...` |
| `Long`, `Float`, `Double`, `Boolean` | Constant expression phải có kiểu primitive tương ứng: `long`, `float`, `double`, `boolean`. | `switch (Long n) { case 1L -> ...; }` |

Với selector `long`, `float`, `double` hoặc `boolean`, không tự dựa vào chuyển đổi số thông thường để viết nhãn constant. Ví dụ, `case 1` không tương thích với selector `long`, `case 1` cũng không tương thích với selector `float`; hãy viết `case 1L` và `case 1.0f` tương ứng. Với `double`, dùng literal `double`, ví dụ `1.0d` hoặc `1.0`.

```java
static String classifyLong(long value) {
    return switch (value) {
        case 0L -> "zero";
        case 1L, 2L, 3L -> "small positive";
        default -> "other";
    };
}

static String classifyFloat(float value) {
    return switch (value) {
        case 0.0f -> "zero";
        case 1.0f, 2.0f -> "one or two";
        default -> "other";
    };
}
```

Hai ví dụ này dùng constant label nên không cần pattern variable. `case` constants phải là constant expressions theo JLS; một biến thông thường dù có giá trị không đổi trong thực tế vẫn không tự trở thành constant expression. Có thể dùng `static final` primitive constant nếu initializer là constant expression.

### Boolean selector

`boolean` có đúng hai giá trị. Vì vậy, một switch expression có thể exhaustive chỉ bằng hai nhãn `true` và `false`:

```java
static String describe(boolean enabled) {
    return switch (enabled) {
        case true -> "enabled";
        case false -> "disabled";
    };
}
```

Không thêm `default` sau khi đã có cả `case true` và `case false`; với selector kiểu `boolean` hoặc `Boolean`, JLS quy định tổ hợp có cả hai constant này và `default` là lỗi biên dịch vì `default` không còn giá trị nào để xử lý.

### Selector là kiểu đóng hộp

Các kiểu `Long`, `Float`, `Double`, `Boolean` là reference types, vì thế biến selector có thể chứa `null`. Khi dữ liệu có thể null, xử lý rõ ràng bằng `case null`:

```java
static String describe(Boolean enabled) {
    return switch (enabled) {
        case null -> "not provided";
        case true -> "enabled";
        case false -> "disabled";
    };
}
```

`default` không thay thế `case null`: nếu selector là null reference và switch không có nhãn null phù hợp, `default` không được chọn và việc thực thi switch thất bại. Nếu đầu vào có thể null, hãy biểu diễn trường hợp đó thành một nhánh riêng hoặc kiểm tra null trước switch.

## 3. Floating-point constant labels có quy tắc riêng

Với selector `float` hoặc `double`, constant label được so sánh theo **representation equivalence** của kiểu dấu phẩy động, không dùng trực tiếp phép so sánh số học `==`. Những điểm cần nhớ:

- `+0.0f` và `-0.0f` được phân biệt, nên có thể dùng làm hai constant label khác nhau.
- Dương vô cực và âm vô cực tương đương với chính chúng và khác các giá trị khác.
- Mọi bit pattern NaN đều được xem là cùng một giá trị khi xét constant label.
- Hai literal khác cách viết nhưng sau khi làm tròn thành cùng một biểu diễn `float` hoặc `double` sẽ là nhãn trùng lặp và gây lỗi biên dịch.

Ví dụ sau minh họa các giá trị đặc biệt của `float`:

```java
static final float NAN = Float.NaN;

static int classifySpecialFloat(float value) {
    return switch (value) {
        case Float.NEGATIVE_INFINITY -> -2;
        case -0.0f -> -1;
        case 0.0f -> 1;
        case Float.POSITIVE_INFINITY -> 2;
        case NAN -> 3;
        default -> 0;
    };
}
```

Không viết hai nhãn constant biểu diễn cùng một giá trị. Ví dụ `1.0f` và `0.999999999f` cùng được làm tròn thành một giá trị `float`, vì vậy compiler báo duplicate case label. Quy tắc này đặc biệt đáng chú ý khi tạo nhãn từ các literal thập phân có nhiều chữ số.

## 4. Pattern label dùng testing conversion

Pattern label không yêu cầu kiểu pattern phải giống hệt kiểu selector. JLS dùng **testing conversion** để xác định liệu giá trị có thể được chuyển sang kiểu pattern một cách chính xác hay không. Một phép chuyển được xem là khớp nếu kết quả không mất thông tin và không phát sinh ngoại lệ. Nếu phép chuyển làm mất độ lớn, độ chính xác, miền giá trị hoặc dấu, pattern không khớp và switch xét nhãn tiếp theo.

Ví dụ, selector `int` có thể được thử với pattern `byte`:

```java
static String classifyInt(int value) {
    return switch (value) {
        case byte b -> "fits in byte: " + b;
        default -> "outside byte range: " + value;
    };
}
```

Nếu `value` nằm trong miền `byte` từ `-128` đến `127`, chuyển đổi `int` sang `byte` giữ nguyên giá trị và pattern khớp. Nếu `value` là `200`, phép chuyển kiểu `byte` sẽ làm thay đổi giá trị; pattern không khớp và nhánh `default` được chọn. Pattern matching không âm thầm cắt bớt bit như phép ép kiểu `(byte) value` thông thường.

Điều này cũng áp dụng cho các chuyển đổi số thực. Với selector `float`, pattern `int i` chỉ khớp khi giá trị float có thể chuyển sang int mà không mất phần thập phân, không tràn miền và không làm mất thông tin. Ví dụ `1000.0f` có thể khớp `int`, còn `1000.25f` không khớp pattern đó.

```java
static String describeMeasurement(float value) {
    return switch (value) {
        case int whole when whole >= 0 -> "non-negative integer: " + whole;
        case int whole -> "negative integer: " + whole;
        default -> "not exactly representable as int: " + value;
    };
}
```

Các nhãn `case int whole` ở đây là primitive type patterns; `when` giới hạn giá trị sau khi pattern đã khớp. Giá trị `NaN`, vô cực hoặc số có phần thập phân không thể biểu diễn chính xác thành `int` sẽ đi tới `default`. Trong Java 26, primitive type pattern và việc dùng guard với primitive pattern ở cấp cao nhất thuộc preview feature.

## 5. Phân biệt constant compatibility với pattern applicability

Đây là khác biệt dễ gây nhầm lẫn nhất khi viết `switch` mới:

| Cách viết | Kiểu kiểm tra | Điều kiện |
|---|---|---|
| `case 10L` | Constant label | Constant expression có kiểu phù hợp chính xác với selector `long`. |
| `case 10.0f` | Constant label | Constant expression có kiểu `float`, không phải `int` hoặc `double`. |
| `case byte b` | Pattern label | Selector có testing conversion tới `byte`; tại runtime conversion phải exact. |
| `case long n` | Pattern label | Selector có testing conversion tới `long`; biến `n` nhận giá trị đã chuyển nếu exact. |
| `case int n when n > 0` | Pattern label có guard | Pattern phải khớp trước; sau đó biểu thức `when` phải trả về `true`. |

Ví dụ, với selector `float f`, nhãn constant `case 1.0f` là tương thích, còn `case 1` không tương thích vì constant có kiểu `int`. Tuy nhiên, một pattern `case int n` có thể được áp dụng cho selector `float`: nó kiểm tra từng giá trị có thể chuyển chính xác sang `int` hay không. Không dùng quy tắc của pattern để suy luận rằng constant label được phép chuyển đổi theo cách tương tự.

### Chọn kiểu pattern theo mục đích

- Chọn pattern cùng kiểu selector khi muốn bắt mọi giá trị của kiểu đó và đặt tên biến để dùng trong nhánh.
- Chọn kiểu hẹp hơn khi muốn nhận riêng các giá trị có thể biểu diễn chính xác trong kiểu hẹp đó.
- Chọn kiểu rộng hơn khi phép widening là chính xác với mọi giá trị selector và muốn xử lý ở kiểu đích.
- Dùng `when` để kiểm tra điều kiện nghiệp vụ sau khi phép chuyển đổi trong pattern đã thành công.
- Đặt nhãn constant cụ thể trước các pattern rộng khi cần xử lý giá trị đặc biệt riêng.

## 6. Pattern dominance và thứ tự nhãn

Compiler kiểm tra **dominance** để phát hiện nhãn không thể được chọn. Một nhãn bị dominated khi mọi giá trị có thể khớp nhãn đó đã được một nhãn không guard đứng trước bắt trước. Điều này có thể xảy ra giữa hai pattern primitive khác kiểu, hoặc giữa pattern và constant label.

Ví dụ sau bị lỗi biên dịch:

```java
static void invalid(float value) {
    switch (value) {
        case int i -> System.out.println("as int: " + i);
        case byte b -> System.out.println("as byte: " + b); // dominated
        default -> System.out.println("other: " + value);
    }
}
```

Mọi giá trị `float` chuyển chính xác được thành `byte` cũng chuyển chính xác được thành `int`. Do đó, `case int i` đứng trước đã bắt tất cả giá trị mà `case byte b` có thể bắt; compiler từ chối nhãn thứ hai. Nếu muốn phân loại theo miền hẹp trước, đặt `case byte b` trước `case int i`:

```java
static String classifyIntByWidth(int value) {
    return switch (value) {
        case byte b -> "byte range: " + b;
        case int i -> "remaining int range: " + i;
    };
}
```

Trong ví dụ này, `case byte b` chỉ nhận phần giá trị có thể biểu diễn chính xác bằng byte. `case int i` bắt phần int còn lại; vì pattern `int` là unconditional đối với selector `int`, switch expression đã exhaustive và không cần `default`.

Một pattern cũng có thể làm một constant label phía sau bị dominated. Ví dụ với selector `int`, `case float f` đứng trước `case 100` sẽ bắt giá trị `100` vì chuyển `100` từ int sang float là value-based unconditionally exact. Compiler vì vậy từ chối `case 100` phía sau. Khi có nhiều loại nhãn, hãy sắp xếp constant cụ thể trước pattern có phạm vi bao phủ rộng.

Guarded pattern không được xem như một nhãn unconditional cho dominance, vì compiler không thể kết luận biểu thức `when` sẽ luôn đúng chỉ bằng kiểu. Dù vậy, nên viết thứ tự dễ đọc: constant đặc biệt, pattern hẹp hoặc có guard, rồi pattern rộng không guard ở cuối. Không đặt một pattern bao phủ toàn bộ selector trước những nhánh còn cần xử lý.

## 7. Exhaustiveness của switch

`switch` expression luôn cần bao phủ mọi giá trị có thể xảy ra hoặc kết thúc bằng exception. Enhanced `switch` statement cũng phải exhaustive. Một block có thể exhaustive khi có `default`, có `case null, default`, hoặc tập constant/pattern không guard bao phủ kiểu selector.

Với selector primitive:

- `boolean` có thể exhaustive bằng cả `case true` và `case false`; không cần `default`.
- `long`, `float`, `double` thường dùng `default` để xử lý các giá trị chưa liệt kê, hoặc dùng một pattern không guard bao phủ toàn bộ kiểu ở cuối.
- Pattern cùng kiểu primitive selector, ví dụ `case long n` trong `switch (long value)`, là unconditional và bao phủ mọi giá trị của kiểu đó.
- Guarded pattern không tự bao phủ các giá trị khi guard trả về `false`; cần nhãn tiếp theo hoặc `default`.

Với wrapper selector, nhớ rằng `null` là một trường hợp riêng. `case true` và `case false` bao phủ hai giá trị Boolean không null; nếu biến kiểu `Boolean` có thể null, hãy thêm `case null`. Exhaustiveness được phân tích theo các giá trị của kiểu và không làm cho null tự động khớp một primitive pattern; hãy xử lý null tường minh trước khi dựa vào các pattern nguyên thủy.

## 8. Ví dụ tổng hợp: phân loại ngưỡng và miền giá trị

Một bộ đọc số đo có thể nhận `long` cho bộ đếm, `double` cho phép đo và `boolean` cho cờ bật/tắt. Primitive switch giúp biểu diễn nhánh giá trị rõ ràng:

```java
static String describeCounter(long count) {
    return switch (count) {
        case 0L -> "empty";
        case long n when n < 0L -> "invalid negative counter";
        case long n when n < 1_000L -> "small counter: " + n;
        case long n -> "large counter: " + n;
    };
}

static String describeRatio(double ratio) {
    return switch (ratio) {
        case Double.NaN -> "not a number";
        case Double.POSITIVE_INFINITY -> "positive infinity";
        case Double.NEGATIVE_INFINITY -> "negative infinity";
        case -0.0d -> "negative zero";
        case 0.0d -> "zero";
        case double d when d > 0.0d && d < 1.0d -> "fraction below one";
        case double d when d >= 1.0d -> "one or greater";
        case double d -> "negative finite value";
    };
}

static String describeFeature(boolean enabled) {
    return switch (enabled) {
        case true -> "feature enabled";
        case false -> "feature disabled";
    };
}
```

Trong `describeCounter`, nhãn `case long n` cuối cùng là pattern unconditional. Các pattern trước có guard nên chỉ nhận các miền đã nêu; nhánh cuối xử lý mọi giá trị còn lại. Trong `describeRatio`, các constant đặc biệt được xử lý trước, sau đó guard chia khoảng số hữu hạn. Nhãn `case double d` cuối cùng là pattern unconditional cho selector `double`, vì vậy switch exhaustive. `describeFeature` dùng hai constant boolean để bao phủ toàn bộ miền.

Khi dùng các giá trị dấu phẩy động đặc biệt, hãy kiểm tra đúng biểu diễn của hằng và thứ tự nhãn. Đặc biệt, `NaN`, vô cực và hai số 0 có dấu là những giá trị hợp lệ của `float`/`double`; đừng giả định chúng tuân theo các phép so sánh thông thường trong guard.

## 9. Preview status và cách biên dịch

Primitive types in patterns, `instanceof`, and `switch` là preview trong Java 26 (JEP 530, lần thứ tư). Java 27 tiếp tục preview (JEP 532, lần thứ năm) và tài liệu JLS 27 ghi nhận không có thay đổi chuẩn tắc đối với đề xuất so với preview Java 26. Điều này có nghĩa cú pháp và quy tắc vẫn có thể thay đổi hoặc bị rút lại trong release sau; không coi chúng là hợp đồng ngôn ngữ đã final.

Biên dịch bằng JDK 26 khi thử preview Java 26:

```bash
javac --release 26 --enable-preview -d out src/PrimitiveSwitch.java
java --enable-preview -cp out PrimitiveSwitch
```

Nếu thử preview lần thứ năm của Java 27, dùng JDK 27 để biên dịch và chạy:

```bash
javac --release 27 --enable-preview -d out src/PrimitiveSwitch.java
java --enable-preview -cp out PrimitiveSwitch
```

Preview phải được bật ở cả compiler lẫn runtime. Class file sử dụng preview được gắn với release đã biên dịch và không thể nạp trên release khác, ngay cả khi runtime mới cũng bật preview. Vì vậy, hãy biên dịch lại bằng JDK mục tiêu khi chuyển từ Java 26 sang Java 27; không dùng class file preview của Java 26 làm artifact chạy trên Java 27.

Các switch truyền thống dùng selector `byte`, `short`, `char`, `int`, enum hoặc `String` với constant label theo quy tắc đã ổn định từ trước vẫn có thể dùng bình thường mà không bật preview. Phần cần preview là việc mở rộng selector sang `long`, `float`, `double`, `boolean`, primitive type patterns và các khả năng primitive matching liên quan. Nếu một switch cũ bắt đầu dùng primitive pattern hoặc selector mới, toàn bộ class có sử dụng preview phải được biên dịch và chạy theo đúng release preview.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `case 1` không tương thích với selector `long` | Constant có kiểu `int`, trong khi selector `long` yêu cầu constant kiểu `long`. | Dùng `case 1L`. |
| `case 1` không tương thích với selector `float` | Java 26 không tự chuyển constant int sang float trong quy tắc constant label này. | Dùng `case 1.0f`. |
| Hai nhãn float bị báo trùng | Hai literal khác nhau nhưng có cùng biểu diễn `float`. | Kiểm tra làm tròn IEEE 754 và loại bỏ nhãn tương đương. |
| Pattern hẹp bị báo dominated | Một pattern đứng trước đã bắt mọi giá trị mà pattern sau có thể bắt. | Đặt pattern hẹp trước pattern rộng hoặc điều chỉnh guard. |
| Pattern primitive không khớp một số giá trị | Testing conversion sẽ mất thông tin hoặc không thể hoàn tất chính xác. | Kiểm tra miền và độ chính xác; dùng nhánh fallback. |
| Switch expression không exhaustive | Constant và pattern không bao phủ hết giá trị; guard có thể loại một phần giá trị. | Thêm `default` hoặc pattern unconditional cuối. |
| Switch với wrapper gặp null | Wrapper là reference type và selector có thể null. | Thêm `case null` hoặc xác thực null trước switch. |
| Compiler báo preview disabled | Chưa bật preview khi biên dịch. | Dùng JDK cùng release và `--enable-preview`. |
| JVM từ chối class file preview | Chạy class file preview trên release khác với release biên dịch. | Biên dịch lại bằng JDK đích và chạy cùng release đó. |

## 11. Checklist khi thiết kế primitive switch

- [ ] Đã xác định kiểu tĩnh của selector, kể cả trường hợp selector là wrapper.
- [ ] Đã phân biệt constant label với pattern label.
- [ ] Với `long`, `float`, `double`, `boolean`, đã dùng constant có kiểu tương thích chính xác.
- [ ] Với pattern, đã xác minh testing conversion có thể chính xác cho giá trị cần xử lý.
- [ ] Đã kiểm tra `float`/`double` về NaN, vô cực, signed zero và constant trùng biểu diễn.
- [ ] Đã sắp xếp pattern hẹp trước pattern rộng và kiểm tra dominance.
- [ ] Đã xử lý guard `when` và không dựa vào guarded pattern để chứng minh exhaustiveness.
- [ ] Đã bảo đảm switch expression hoặc enhanced switch statement exhaustive.
- [ ] Nếu selector là wrapper, đã quyết định rõ cách xử lý null.
- [ ] Đã xác định phần code nào dùng preview và bật preview ở cả compile lẫn runtime.
- [ ] Đã biên dịch lại với đúng JDK release khi chuyển từ Java 26 sang Java 27.

## Tài liệu tham khảo chính thức

- [Java Language Updates — Primitive Types in Patterns, `instanceof`, and `switch` (Java 26)](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html)
- [Primitive Types in Patterns, `instanceof`, and `switch` — JLS Fourth Preview (Java 26)](https://docs.oracle.com/javase/specs/jls/se26/preview/specs/primitive-types-in-patterns-instanceof-switch-jls.html)
- [Switch Expressions and Statements — Java 26](https://docs.oracle.com/en/java/javase/26/language/switch-expressions-statements.html)
- [Type Patterns — Java 26](https://docs.oracle.com/en/java/javase/26/language/type-patterns.html)
- [Safe Casting with `instanceof` and `switch` — Java 26](https://docs.oracle.com/en/java/javase/26/language/safe-casting-instanceof-switch.html)
- [Java Language Changes Summary — Java 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html)
- [Primitive Types in Patterns, `instanceof`, and `switch` — JLS Fifth Preview (Java 27)](https://docs.oracle.com/javase/specs/jls/se27/preview/specs/primitive-types-in-patterns-instanceof-switch-jls.html)
- [Preview Language and VM Features — Java 26](https://docs.oracle.com/en/java/javase/26/language/preview-language-vm-features.html)
- [The `javac` Command — Java 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [JVM Specification — Preview Features and Class File Restrictions](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-1.html)

*Cập nhật nội dung: 27-11-2026. Primitive switch selector mở rộng và primitive patterns vẫn là preview ở Java 27; kiểm tra lại Java Language Changes Summary và JLS của release mục tiêu trước khi đưa vào mã sản phẩm.*
