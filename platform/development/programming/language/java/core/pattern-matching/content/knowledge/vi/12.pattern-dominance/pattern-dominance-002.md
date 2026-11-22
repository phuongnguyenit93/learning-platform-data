# Vì sao pattern tổng quát phải đặt sau trong `switch` Java?

**Chủ đề:** Java Core Pattern Matching → Dominance  
**Yêu cầu môi trường:** JDK 21 trở lên để dùng pattern matching for `switch` theo cú pháp chính thức của JEP 441. Ví dụ sử dụng `case Type variable` và guard `when`.

## 1. Trả lời ngắn gọn

**Một `case` có pattern tổng quát, nếu đứng trước, có thể khớp toàn bộ những giá trị mà `case` đặc thù phía sau cần xử lý.** Khi compiler chứng minh được điều đó theo quy tắc *dominance*, nhánh phía sau bị coi là không thể được chọn và Java báo **lỗi biên dịch** (*dominated case label*).

Ví dụ, `String` triển khai `CharSequence`. Vì vậy mọi `String` đều là `CharSequence`, nhưng không phải mọi `CharSequence` đều là `String`.

```java
// KHÔNG BIÊN DỊCH trên Java 21:
static String broken(Object input) {
    return switch (input) {
        case CharSequence chars -> "SEQUENCE";
        case String text -> "STRING"; // Lỗi: bị case CharSequence chi phối.
        default -> "OTHER";
    };
}
```

Nếu `input` là `"Java"`, nhánh `CharSequence` đầu tiên đã đủ điều kiện nhận nó. Nhánh `String` sau không thể có cơ hội xử lý một giá trị `String`. Java phát hiện tình huống ngay khi biên dịch, thay vì chờ người dùng phát hiện một nhánh “chết” lúc chạy.

**Cách sửa:** đặt nhánh cụ thể trước, nhánh bao quát sau.

```java
static String fixed(Object input) {
    return switch (input) {
        case String text -> "STRING:" + text;
        case CharSequence chars -> "SEQUENCE:" + chars.length();
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Ở đây `"Java"` chọn `String`; `new StringBuilder("abc")` chọn `CharSequence`; một đối tượng khác không thuộc hai kiểu đó vào `default`; `null` được xử lý riêng. Đây là **phương thức minh họa**, có thể đặt trong class Java 21.

## 2. Phân biệt “thứ tự kiểm tra” và “dominance”

Khi một `switch` có các nhãn pattern có khả năng cùng áp dụng cho một giá trị, thứ tự nhãn góp phần quyết định nhánh được chọn. Tuy nhiên, dominance không chỉ là lời khuyên viết code đẹp: Java có **quy tắc kiểm tra tĩnh** để cấm một nhãn bị che hoàn toàn bởi một nhãn trước đó.

- **Match runtime:** một pattern có khớp giá trị cụ thể đang được kiểm tra ở thời điểm chạy hay không?
- **Dominance compile time:** xét quan hệ kiểu/pattern, compiler có thể kết luận rằng nhãn trước bao phủ mọi giá trị mà nhãn sau có thể chọn hay không?
- **Hệ quả:** nếu nhãn sau bị dominated theo quy định của Java, cả `switch` bị từ chối khi biên dịch, dù test thực tế chưa chạy.

Mô hình tập hợp giúp ghi nhớ:

```text
Number
  ├── Integer
  ├── Double
  ├── Long
  └── ...

CharSequence
  ├── String
  ├── StringBuilder
  └── StringBuffer
```

`Integer` là tập con của `Number`; `String` là tập con của `CharSequence`. Đặt case của tập con **trước** case tập cha cho phép xử lý chuyên biệt mà không bị che mất.

Đây là một **quan hệ bao phủ từng phần**, không phải yêu cầu sắp xếp *mọi* case theo “độ tổng quát” chung. `Integer` và `String` không có quan hệ subtype giữa nhau, nên vị trí tương đối của hai nhánh đó có thể chọn theo mục đích đọc hiểu và yêu cầu nghiệp vụ.

## 3. Hai ví dụ dominance cơ bản

### 3.1. `Number` che `Integer`

```java
// KHÔNG BIÊN DỊCH:
return switch (value) {
    case Number number -> "Number";
    case Integer integer -> "Integer"; // Bị case Number che.
    default -> "Other";
};
```

Giả định `value` có kiểu tĩnh `Object`. Mọi đối tượng `Integer` không null đều khớp `Number`; vì thế nhánh `Integer` phía sau bị dominated.

Sửa:

```java
return switch (value) {
    case Integer integer -> "Integer:" + integer;
    case Number number -> "Number:" + number;
    case null -> "Null";
    default -> "Other";
};
```

Kết quả minh họa:

| Input | Nhánh chọn | Lý do |
| --- | --- | --- |
| `42` | `Integer` | Pattern hẹp đứng trước |
| `3.14` | `Number` | `Double` là `Number`, không phải `Integer` |
| `"42"` | `default` | Là `String`, không thuộc `Number` |
| `null` | `case null` | Không khớp type pattern cấp ngoài |

### 3.2. `CharSequence` che `String`

```java
// KHÔNG BIÊN DỊCH:
case CharSequence chars -> chars.length();
case String text -> text.length(); // Bị dominated.
```

Sửa:

```java
case String text -> text.length();
case CharSequence chars -> chars.length();
```

Khi `input` là `new StringBuilder("abc")`, nhánh `String` không khớp nhưng nhánh `CharSequence` khớp. Nhờ vậy cả kiểu con cụ thể và những kiểu khác thuộc interface chung đều được xử lý.

**Không nhầm với overload resolution của phương thức:** `switch` không tự ưu tiên “pattern cụ thể nhất” bất kể nó nằm ở đâu. Bạn phải tổ chức nhãn hợp lệ; compiler cấm một số thứ tự tạo nhánh bị chi phối.

## 4. Type pattern match-all: `Object` và kiểu selector

Khi selector khai báo `Object`, type pattern `case Object obj` bao phủ các **đối tượng không null**. Nếu đặt ở đầu, nhiều nhánh kiểu cụ thể phía sau sẽ bị dominated:

```java
// KHÔNG BIÊN DỊCH:
return switch (input) {
    case Object obj -> "OBJECT";
    case String text -> "STRING"; // Không bao giờ được chọn.
};
```

Một pattern vô điều kiện (*unconditional*) cho kiểu selector cũng có thể làm `switch` exhaustive đối với giá trị không null, tương tự tác dụng bao phủ của nhánh dự phòng. Vì vậy, không được tùy tiện thêm cả `case Object obj` lẫn `default` để có hai nhánh match-all: ngôn ngữ áp dụng quy tắc chống nhãn match-all trùng lặp/dominated.

Viết rõ mục đích hơn:

```java
static String category(Object input) {
    return switch (input) {
        case null -> "NULL";
        case String s -> "STRING";
        case Number n -> "NUMBER";
        case Object other -> "OTHER_OBJECT";
    };
}
```

Ví dụ này liệt kê hai kiểu chuyên biệt trước rồi đặt `Object` sau cùng để xử lý mọi đối tượng không null còn lại. Nhánh `case null` vẫn cần riêng: **`null` không phải instance của `Object`** và không khớp type pattern `Object other` ở cấp ngoài.

Trong một số bài toán, `default` là lựa chọn ngắn hơn `case Object other`. Nếu không cần biến `other`, `default` thường diễn đạt ý “trường hợp chưa được liệt kê” dễ hiểu hơn.

## 5. Guard `when` là ngoại lệ quan trọng của quy tắc sắp xếp

Không phải cứ một pattern có kiểu rộng xuất hiện sớm hơn là chắc chắn lỗi. Với một nhãn **có guard không luôn đúng**, Java chỉ chọn nó nếu vừa khớp pattern vừa thỏa điều kiện `when`.

Mẫu thường dùng:

```java
case String text when text.isBlank() -> "BLANK";
case String text -> "NON_BLANK";
```

Nhánh đầu nhận chuỗi blank; khi `text.isBlank()` trả `false`, `switch` có thể tiếp tục sang nhánh `String` tổng quát. Compiler cho phép thứ tự này vì guard không làm nhánh đầu bao phủ toàn bộ các chuỗi.

Đảo ngược là lỗi:

```java
// KHÔNG BIÊN DỊCH:
case String text -> "ANY_STRING";
case String text when text.isBlank() -> "BLANK"; // Bị dominated.
```

Nhánh `String` không guard đã nhận mọi `String` không null, nên nhánh sau không còn miền giá trị cần xử lý.

Cũng có thể dùng một guard theo kiểu cha trước một subtype, **nếu guard thật sự có thể sai**:

```java
case Number n when n.doubleValue() < 0 -> "NEGATIVE_NUMBER";
case Integer i -> "NONNEGATIVE_INTEGER";
case Number n -> "OTHER_NUMBER";
```

Cấu trúc này hợp lệ về ý tưởng và có **ưu tiên nghiệp vụ** rõ: mọi số âm (kể cả `Integer`) được phân loại trước; tiếp theo xử lý `Integer` còn lại; cuối cùng là những `Number` khác. Trong chương trình, nên viết test cho `-1`, `0`, `1`, `-1.5`, `1.5` để chứng minh ý định.

**Chi tiết của JLS:** guard có giá trị hằng `true` được xem như *unguarded* trong quy tắc dominance. Vì vậy:

```java
// KHÔNG BIÊN DỊCH:
case String s when true -> "ALL_STRINGS";
case String s -> "STRING"; // Vẫn bị dominated.
```

Đừng giả định compiler hiểu mọi biểu thức `when` tùy ý như một định lý toán học. Trình biên dịch tuân theo quy tắc ngôn ngữ về guarded/unguarded và mối quan hệ giữa pattern, chứ không “giải bài toán logic tổng quát” để suy luận mọi miền dữ liệu.

## 6. Cẩn thận với hằng số và enum constant

Dominance không chỉ xảy ra giữa hai type pattern. Một nhãn hằng cũng có thể bị một type pattern đặt trước bao phủ hoàn toàn.

Ví dụ với selector có kiểu `Integer`:

```java
// KHÔNG BIÊN DỊCH:
return switch (number) {
    case Integer n -> "ANY_INTEGER";
    case 0 -> "ZERO"; // Hằng 0 bị pattern Integer đứng trước chi phối.
};
```

Muốn xử lý `0` riêng, hãy đặt nhãn hằng `case 0` trước nhãn type tổng quát `case Integer n` (và xử lý `null` nếu API cần):

```java
return switch (number) {
    case null -> "NULL";
    case 0 -> "ZERO";
    case Integer n -> "OTHER_INTEGER";
};
```

Các đoạn trên là **phần thân minh họa** trong một phương thức có `Integer number` phù hợp. Với `enum`, một type pattern bao phủ kiểu enum cũng có thể che những nhãn enum constant được đặt sau; tương tự, hãy đặt trường hợp chuyên biệt trước trường hợp bao quát nếu thực sự muốn cả hai.

Việc xếp hằng số trước type pattern tương thích với ý tưởng “giá trị cụ thể trước, nhóm kiểu tổng quát sau”.

## 7. Record pattern và sealed hierarchy cũng cần nghĩ về mức bao phủ

Record pattern có thể bóc tách component:

```java
record Point(int x, int y) {}
```

Đặt một type pattern tổng quát của cùng record trước record pattern cụ thể có thể làm nhãn sau bị chi phối:

```java
// KHÔNG BIÊN DỊCH trong switch(Object input):
case Point point -> "POINT";
case Point(int x, int y) -> "POINT_COMPONENTS"; // Bị dominated.
```

Lý do: mọi đối tượng khớp record pattern `Point(int x, int y)` đều là `Point`, do đó nhãn `case Point point` trước đã bao phủ chúng.

Đảo thứ tự nếu muốn deconstruction trước:

```java
case Point(int x, int y) -> "AT:" + x + "," + y;
case Point p -> "POINT";
```

Tuy nhiên, nếu record pattern đã bao phủ mọi instance không null của `Point` đó, nhánh `case Point p` phía sau có thể tiếp tục bị coi là dominated. **Không được coi “đảo thứ tự” là biện pháp tự động sửa mọi cặp pattern:** phải xem chính xác miền giá trị từng pattern có thể khớp. Với một `record Point(int x, int y)` chỉ gồm hai primitive component, record pattern `Point(int x, int y)` có thể nhận mọi instance không null của `Point`; trong thiết kế này, hãy **chọn một cách biểu diễn**, thay vì cố giữ hai case tương đương.

Với sealed hierarchy, nên liệt kê các subtype chuyên biệt để compiler kiểm tra exhaustiveness:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(int radius) implements Shape {}
record Rectangle(int width, int height) implements Shape {}
```

Nếu `switch (Shape shape)` đã có `case Shape s` đứng trước `case Circle c`, `Circle` bị che. Nếu chỉ có hai subtype `Circle` và `Rectangle`, nhiều khi không cần `case Shape s` hoặc `default` nữa: các case subtype không guard có thể làm `switch` exhaustive và compiler sẽ cảnh báo khi thiếu subtype mới sau này.

## 8. `default`, `case null` và thứ tự nhãn

`default` là nhãn dự phòng cho các giá trị không khớp các case khác. Nó không phải một type pattern cần kiểm tra kiểu; không nên nhầm *dominance giữa các pattern* với “luôn phải có default sau mọi dòng vì thế”.

Với input có thể null:

```java
static String status(Object input) {
    return switch (input) {
        case null -> "NULL";
        case String s -> "STRING";
        case Number n -> "NUMBER";
        default -> "OTHER";
    };
}
```

Một số điểm cần nhớ:

- `case null` xử lý selector bằng `null`; `default` đứng riêng **không** tự bắt `null` trên Java 21.
- `case null, default -> "OTHER"` là cú pháp đặc biệt được phép khi nghiệp vụ coi `null` và các giá trị còn lại như nhau.
- Với selector kiểu mở như `Object`, `default` thường giúp `switch` expression exhaustive.
- Với enum hoặc sealed hierarchy đóng và các case đã bao phủ đủ, `default` có thể không cần thiết. Bỏ `default` khi phù hợp giúp compiler phát hiện trường hợp mới chưa được xử lý.
- Nếu đã có một pattern *match-all* cho selector, không thêm nhãn match-all thứ hai. Việc di chuyển `default` ngẫu nhiên không thay thế được phân tích độ bao phủ.

## 9. Chương trình thực hành Java 21: kiểm chứng thứ tự case

Đây là chương trình chạy độc lập có bài test cho **type con trước type cha**, **guard trước nhánh không guard**, **null riêng**, và **sealed hierarchy** không cần `default`.

Tạo tệp **`GeneralPatternOrderDemo.java`**:

```java
public class GeneralPatternOrderDemo {
    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}
    record Rectangle(int width, int height) implements Shape {}

    static String classify(Object input) {
        return switch (input) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s -> "STRING:" + s.length();
            case Integer n when n < 0 -> "NEGATIVE_INT:" + n;
            case Integer n -> "INTEGER:" + n;
            case Number n -> "NUMBER:" + n.getClass().getSimpleName();
            case CharSequence seq -> "CHARSEQ:" + seq.length();
            default -> "OTHER:" + input.getClass().getSimpleName();
        };
    }

    static String draw(Shape shape) {
        return switch (shape) {
            case null -> "NO_SHAPE";
            case Circle c when c.radius() < 0 -> "INVALID_CIRCLE";
            case Circle c -> "CIRCLE:" + c.radius();
            case Rectangle r ->
                    "RECTANGLE:" + r.width() + "x" + r.height();
        };
    }

    static void check(String name, String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=" + expected + " actual=" + actual);
        }
        System.out.println(name + "=" + actual);
    }

    public static void main(String[] args) {
        check("null", classify(null), "NULL");
        check("blank", classify("  "), "BLANK");
        check("string", classify("Java"), "STRING:4");
        check("negative", classify(-3), "NEGATIVE_INT:-3");
        check("zero", classify(0), "INTEGER:0");
        check("double", classify(2.5), "NUMBER:Double");
        check("builder", classify(new StringBuilder("abc")), "CHARSEQ:3");
        check("boolean", classify(true), "OTHER:Boolean");

        check("no-shape", draw(null), "NO_SHAPE");
        check("bad-circle", draw(new Circle(-1)), "INVALID_CIRCLE");
        check("circle", draw(new Circle(4)), "CIRCLE:4");
        check("rectangle", draw(new Rectangle(2, 5)), "RECTANGLE:2x5");

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy bằng JDK 21+:

```bash
javac --release 21 GeneralPatternOrderDemo.java
java GeneralPatternOrderDemo
```

**Standard output:**

```text
null=NULL
blank=BLANK
string=STRING:4
negative=NEGATIVE_INT:-3
zero=INTEGER:0
double=NUMBER:Double
builder=CHARSEQ:3
boolean=OTHER:Boolean
no-shape=NO_SHAPE
bad-circle=INVALID_CIRCLE
circle=CIRCLE:4
rectangle=RECTANGLE:2x5
ALL CHECKS PASSED
```

### Vì sao từng dòng quan trọng?

1. `null`: không khớp các type pattern, vào nhánh `case null`.
2. `"  "`: khớp `String` có guard `isBlank()`; vì nhánh này trước `String` chung nên trả `BLANK`.
3. `"Java"`: guard blank sai, tiếp tục tới `case String s`, trả `STRING:4`. Nó cũng là `CharSequence`, nhưng nhánh `String` có ưu tiên.
4. `-3`: khớp `Integer` có guard âm; `0`: guard âm sai, khớp `Integer` chung.
5. `2.5`: `Double` là `Number` nhưng không phải `Integer`, nên vào `Number`.
6. `new StringBuilder("abc")`: không phải `String`, nhưng có interface `CharSequence`, trả `CHARSEQ:3`.
7. `true`: `Boolean` không thuộc các type pattern trên, vào `default`.
8. `draw` kiểm tra null, `Circle` có radius âm, `Circle` còn lại và `Rectangle`. Hai subtype của sealed `Shape` đã được bao phủ nên không cần `default`.

Phương thức `check` ném `AssertionError` nếu bất kỳ expected result nào khác thực tế. Dòng cuối `ALL CHECKS PASSED` chỉ xuất hiện khi 12 phép kiểm tra trước đó đều qua. Đây là **self-test bằng Java SE**, không cần thư viện test bên ngoài. Chương trình sử dụng tính năng chính thức ở Java 21, không dùng cú pháp preview.

## 10. Ma trận test để phát hiện lỗi do sai thứ tự

| Input | Case mong muốn | Vì sao cần test |
| --- | --- | --- |
| `"Java"` | `String` chung | Chứng minh `String` được xử lý chuyên biệt thay vì lẫn vào `CharSequence` |
| `new StringBuilder("abc")` | `CharSequence` | Chứng minh nhánh cha vẫn nhận subtype không phải `String` |
| `-3` | `Integer` có guard | Kiểm tra guard thật sự có cơ hội chạy |
| `0` | `Integer` chung | Kiểm tra guard false không làm mất nhánh kiểu |
| `2.5` | `Number` | Kiểm tra nhánh kiểu cha nhận loại số khác |
| `true` | `default` | Kiểm tra fallback cho kiểu chưa liệt kê |
| `null` | `case null` | Không nhầm `Object` hoặc `default` với chính sách null |
| `new Circle(-1)` | `Circle` có guard | Kiểm tra trường hợp đặc biệt của subtype |
| `new Circle(4)` | `Circle` chung | Kiểm tra phạm vi còn lại của subtype |
| `new Rectangle(2,5)` | `Rectangle` | Kiểm tra exhaustiveness của sealed hierarchy |

Để phát hiện lỗi ngay ở thời điểm biên dịch, nên chủ động thử **một cặp case đảo ngược** trong một bản ví dụ tách biệt (không chỉnh sửa chương trình đang chạy tốt) và đọc thông báo `this case label is dominated by a preceding case label`. Đây là lỗi compiler, không thể được “test runtime” vì chương trình lỗi không thể biên dịch.

## 11. Phân biệt dominance và exhaustiveness

Hai câu hỏi rất khác nhau:

- **Dominance:** có `case` nào phía sau bị nhánh trước bao phủ tới mức nó không thể được chọn không?
- **Exhaustiveness:** các nhãn hợp lệ cộng lại có bao phủ tất cả giá trị mà `switch` yêu cầu xử lý không?

Một `switch` có thể **exhaustive nhưng sai dominance**, ví dụ `case Number n` trước `case Integer i`, rồi có `default`: tổng thể có vẻ “đủ nhánh” nhưng vẫn không biên dịch do nhãn `Integer` bị dominated.

Một `switch` cũng có thể **không có dominance nhưng thiếu exhaustiveness**, ví dụ `switch (Object)` chỉ có `case String` và `case Integer`, không có nhánh bao quát còn lại. Khi là `switch` expression, compiler yêu cầu bổ sung nhãn cần thiết.

Tập sealed như `Shape` cho phép compiler chứng minh đủ `Circle` và `Rectangle`. Nếu muốn thêm `record Triangle(...) implements Shape`, phải bổ sung vào `permits` và cập nhật các `switch` exhaustive liên quan khi biên dịch lại. Nhờ không có `default` hấp thụ subtype mới, các miền nghiệp vụ quan trọng ít bị quên nhánh xử lý.

## 12. Cách tổ chức `case` dễ bảo trì

Khi gặp một `switch` mới có nhiều kiểu dữ liệu, làm theo quy trình:

1. **Liệt kê miền giá trị của selector:** `Object`, interface, sealed hierarchy, enum hay một kiểu cụ thể?
2. **Xác định quan hệ subtype:** ghi rõ `String <: CharSequence`, `Integer <: Number`, `Circle <: Shape`. Chỉ so sánh quan hệ bao phủ thực sự, không “đoán” kiểu nào nghe có vẻ tổng quát.
3. **Ưu tiên tình huống chuyên biệt:** hằng số/điều kiện guard/kiểu con khi cần hành vi riêng.
4. **Sau đó đặt pattern bao quát:** kiểu cha hoặc một nhánh không guard của cùng kiểu.
5. **Cuối cùng thiết kế phần còn lại:** `default`, pattern match-all, hoặc enum/sealed exhaustive. Không tự thêm hai match-all.
6. **Xử lý null theo hợp đồng:** `case null`, `case null, default` hay từ chối đầu vào.
7. **Biên dịch rồi mới chạy test:** lỗi dominated là lỗi tĩnh; test runtime chỉ có ý nghĩa sau khi toàn bộ pattern hợp lệ.
8. **Test cả nhánh hẹp lẫn nhánh rộng:** `Integer` + `Double`; `String` + `StringBuilder`; guard true + guard false.

Điều này không đồng nghĩa “mọi `switch` bắt buộc có case ở cùng thứ tự” — đây là cách bố trí **phù hợp quan hệ bao phủ và ưu tiên nghiệp vụ**.

## 13. Những hiểu nhầm thường gặp

| Hiểu nhầm | Sự thật |
| --- | --- |
| “Compiler sẽ tự chọn pattern cụ thể nhất bất kể vị trí.” | `switch` tuân theo quy tắc nhãn và dominance; nhánh cụ thể bị che có thể tạo lỗi compile. |
| “`case Number n` nhận `Integer` và `Double`, nên đặt trước `Integer` cũng không sao.” | `Integer` phía sau bị dominated nếu nhánh `Number` trước không có guard hạn chế. |
| “Cứ đặt mọi pattern hẹp lên trên là luôn đủ.” | Phải xét guard, record pattern, null, match-all và exhaustiveness; hai pattern có miền khớp giống nhau không thể cùng tồn tại chỉ nhờ đảo thứ tự. |
| “`when` luôn được xem là nhánh hạn chế.” | Guard hằng `true` được xem là unguarded trong quy tắc dominance; guard không tự động loại bỏ lỗi. |
| “`null` sẽ được `case Object o` nhận.” | Type pattern cấp ngoài `Object o` không khớp null. |
| “`default` giải quyết mọi lỗi dominance.” | `default` giúp bao phủ phần còn lại nhưng không cứu case bị dominated. |
| “`case String s` có thể dùng `s` cả bên ngoài switch.” | Pattern variable chỉ nằm trong phạm vi được Java xác nhận đã match. |
| “Dominance luôn được quyết định bằng test input.” | Đây là quy tắc compile time. Test chỉ giúp xác nhận các nhánh hợp lệ xử lý đúng nghiệp vụ. |
| “Mọi interface không liên quan tên gọi đều không thể chồng nhau.” | Hai interface có thể cùng được một class triển khai; phải phân tích khả năng khớp và quan hệ kiểu, không chỉ tên. |
| “Chỉ `case ->` mới có dominance.” | Quy tắc về nhãn case của pattern cũng quan trọng khi dùng dạng colon `case ...:`; arrow chỉ giúp luồng rõ hơn. |

## 14. Bài tập tự luyện

1. Viết `switch(Object)` nhận `String`, `CharSequence` và `default`. Thử cố ý đặt `CharSequence` trước `String` và ghi lại thông báo compiler. Sửa thứ tự, thử `"abc"` và `new StringBuilder("abc")`.
2. Viết phiên bản `Number`/ `Integer`. Kiểm tra `42`, `3.14`, `null`, rồi giải thích vì sao `Integer` phải đứng trước `Number` nếu không có guard hạn chế.
3. Đặt `case String s when s.length() > 3` trước `case String s`. Test các chuỗi có độ dài `3`, `4` và `5`. Sau đó đảo hai nhánh để quan sát lỗi dominance.
4. Thử `case Number n when n.doubleValue() < 0` trước `case Integer i`, rồi `case Number n`. Test cả số nguyên âm lẫn dương để xác nhận guard rộng nhưng không phải nhánh match-all.
5. Với `record Point(int x, int y)`, thử hai nhãn `case Point p` và `case Point(int x, int y)`; dự đoán lỗi dominance. Sửa bằng cách chọn một pattern phù hợp với mục đích, thay vì giữ hai nhánh trùng miền.
6. Dùng `sealed interface Shape` có `Circle`, `Rectangle` như chương trình mẫu. Cố ý đặt `case Shape s` trước `case Circle c`; biên dịch và đọc lỗi. Quay lại các case subtype cụ thể.
7. Bổ sung `case Object obj` vào một switch đang có `default` và phân tích quy tắc match-all. Thiết kế lại để chỉ còn một nhánh bao quát thích hợp.
8. Viết unit test phân biệt hành vi `null` so với `default`, và kiểm tra `Integer`/ `Double`/ `String`/ `StringBuilder`.
9. Chỉ ra một `switch` exhaustive nhưng có lỗi dominance và một `switch` không có lỗi dominance nhưng thiếu exhaustiveness. Giải thích hai thông báo compiler khác nhau.

**Tiêu chí hoàn thành:** giải thích được tại sao pattern cha không guard che pattern con, biết trường hợp guard làm thay đổi ưu tiên, phân biệt `case null`/`default`/match-all, và tự xây dựng một `switch` Java 21 vừa biên dịch được vừa có test cho nhánh cụ thể lẫn nhánh tổng quát.

**Nguồn chính thức để đối chiếu:**

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Pattern Matching for switch, Pattern Label Dominance](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — `switch` labels và dominance (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21 — Pattern matching và dominance (§14.30)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
