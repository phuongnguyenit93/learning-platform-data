# Guard ảnh hưởng đến dominance thế nào trong Java Pattern Matching?

Trong Java 21+, một nhãn `case` của `switch` có thể chứa **pattern** và một điều kiện bảo vệ **guard `when`**:

```java
case String text when text.length() >= 5 -> "long string";
```

Guard ảnh hưởng đến **dominance** (quan hệ thống trị giữa các nhãn `case`) theo một cách rất cụ thể: **một pattern có guard không hằng đúng có thể không bao phủ hết các giá trị mà pattern gốc khớp**, bởi vì guard có thể trả về `false`. Do đó Java thường cho phép những nhánh cùng kiểu, hoặc một nhánh kiểu hẹp phía sau một pattern kiểu rộng **đã có guard**, để xử lý các trường hợp guard không đạt.

Ngược lại, một pattern **không guard** hoặc được bảo vệ bằng guard là **biểu thức hằng `true`** vẫn được compiler xem là bao phủ đầy đủ các giá trị của pattern ấy khi xét dominance. Một nhánh bị bao phủ hoàn toàn phía sau sẽ gây **lỗi biên dịch**, dù code runtime của nhánh trước có vẻ đơn giản hay phức tạp.

> **Quy tắc trọng tâm:** Khi kiểm tra dominance, Java phân biệt *pattern có thể match* và *case chắc chắn được áp dụng sau khi pattern match*. Một guard bình thường có thể sai; guard hằng `true` là ngoại lệ được xem như không guard. Compiler không chứng minh các điều kiện boolean tùy ý để loại bỏ nhánh.

Bài này tập trung vào **dominance của pattern case labels trong `switch`** và liên hệ trực tiếp với guard `when`, bao gồm cơ chế compile time, hành vi runtime, thứ tự nhánh, tính đầy đủ và các lỗi thường gặp. Cú pháp `when` của `switch` được chuẩn hóa từ **Java 21**; các ví dụ runnable bên dưới cần JDK 21+.

## 1. Dominance là gì?

Một nhãn `case` trước **dominate** một nhãn `case` sau nếu theo quy tắc tĩnh của ngôn ngữ, nhãn sau bị nhãn trước bao phủ đến mức không còn cơ hội được chọn. Java dùng **dominance checking** khi biên dịch để ngăn những nhánh pattern bị che khuất do đặt sai thứ tự.

Ví dụ **không hợp lệ** (bỏ comment từng dòng để thử trong một `switch` Java 21+):

```java
// static String bad(Object value) {
//     return switch (value) {
//         case CharSequence seq -> "any sequence";
//         case String text -> "a string"; // LỖI: bị nhánh CharSequence trước dominate
//         default -> "other";
//     };
// }
```

`String` triển khai `CharSequence`; mọi đối tượng `String` khác `null` đều khớp pattern `CharSequence seq` ở trên. Nhánh `case String text` nằm sau không thể được chọn theo thứ tự ấy.

Cách sửa là **đặt nhánh cụ thể trước nhánh rộng**:

```java
static String good(Object value) {
    return switch (value) {
        case String text -> "a string";
        case CharSequence seq -> "other sequence";
        default -> "other";
    };
}
```

Đây là một **phương thức minh họa**, giả định đặt trong lớp Java 21+. Nếu `value` là `StringBuilder`, nó đi vào nhánh `CharSequence`. Nếu `value` là `String`, nó đi vào nhánh `String` trước.

**Không phải mọi nhánh đi sau một nhánh có thể cùng khớp đều bị dominate.** Trọng tâm là khả năng nhánh trước **bao phủ chắc chắn** các trường hợp của nhánh sau theo quy tắc biên dịch. Guard `when` làm thay đổi đánh giá này.

## 2. `when` biến một nhãn pattern thành nhãn có điều kiện

So sánh hai dạng:

```java
case CharSequence seq -> "any sequence";
```

và

```java
case CharSequence seq when seq.length() >= 5 -> "long sequence";
```

Ở dạng đầu, một đối tượng `CharSequence` khác `null` khớp thì nhánh có thể được chọn ngay (giả sử không có nhãn trước được áp dụng).

Ở dạng thứ hai, type pattern `CharSequence seq` phải khớp **và** biểu thức `seq.length() >= 5` phải trả về `true`. Nếu giá trị là chuỗi `"Go"`, pattern có thể khớp, nhưng guard là `false`; case này **không được chọn**. Java có lý do để giữ các nhánh xử lý `String` hoặc `CharSequence` khác phía sau.

Vì thế cặp sau **hợp lệ**, dù pattern rộng có trước:

```java
static String classify(Object value) {
    return switch (value) {
        case CharSequence seq when seq.length() >= 5 -> "long sequence";
        case String text -> "string: " + text;
        case CharSequence seq -> "other sequence";
        default -> "other";
    };
}
```

Các tình huống:

- `"Spring"`: khớp `CharSequence` và guard đúng, nên chọn `long sequence` ngay.
- `"Go"`: khớp `CharSequence` nhưng guard sai; nhánh `case String text` tiếp theo được chọn.
- `new StringBuilder("ok")`: không qua guard, không phải `String`; nhánh `CharSequence` không guard ở sau xử lý.
- Một `Integer`: không khớp `CharSequence` hay `String`; chọn `default`.

**Lưu ý:** guard cho phép nhánh hẹp phía sau tồn tại, nhưng không đảm bảo nhánh hẹp luôn được chọn. Với `"Spring"`, nhánh rộng có guard vẫn **giành quyền chọn trước** vì guard đạt. Nếu muốn `String` luôn ưu tiên hơn các loại `CharSequence` khác, phải sắp xếp hoặc điều chỉnh các case cho phù hợp ý định.

## 3. Bảng quy tắc nhanh: có guard hay không, có dominance hay không?

| Các nhãn theo thứ tự | Kết quả | Vì sao |
| --- | --- | --- |
| `case CharSequence cs -> ...; case String s -> ...;` | **Lỗi biên dịch** | Pattern `CharSequence` không guard bao phủ `String` |
| `case CharSequence cs when cs.length() > 3 -> ...; case String s -> ...;` | **Hợp lệ** | Guard có thể `false`, nhánh `String` còn cơ hội chạy |
| `case String s -> ...; case String t when t.isBlank() -> ...;` | **Lỗi biên dịch** | `String` không guard đứng trước đã bao phủ toàn bộ `String` |
| `case String s when s.isBlank() -> ...; case String t -> ...;` | **Hợp lệ** | Khi guard sai, case `String` phía sau xử lý phần còn lại |
| `case String s when true -> ...; case String t -> ...;` | **Lỗi biên dịch** | Guard hằng `true` được xem tương đương không guard khi xét dominance |
| `case String s when false -> ...;` | **Lỗi biên dịch** | Guard là biểu thức hằng có giá trị `false`, bị Java cấm |
| `case String s when s.isBlank() -> ...; case String t when t.isBlank() -> ...;` | **Hợp lệ về dominance** | Compiler không chứng minh các predicate tùy ý trùng nhau; thực tế nhánh sau có thể không tới với predicate thuần |

Các cặp trên là **mảnh cú pháp minh họa**, không phải các chương trình Java hoàn chỉnh. Để chạy, cần đặt trong `switch` có kiểu selector và các nhánh còn lại phù hợp; với `switch expression`, phải bảo đảm exhaustive.

Điểm đáng lưu ý: dominance là **kiểm tra tĩnh của compiler**, không đơn thuần là đo xem một tập dữ liệu test có bao giờ chảy vào case nào hay không.

## 4. Phân biệt compile-time dominance với việc chọn nhánh runtime

Một case có guard thông thường gồm các bước:

1. **Đánh giá selector** của `switch` để lấy giá trị cần phân nhánh.
2. **Thử pattern** của nhãn case theo quy tắc chọn nhánh.
3. Nếu pattern không match, guard **không được đánh giá**.
4. Nếu pattern match, **binding pattern variables** như `seq` hoặc `text`.
5. **Đánh giá guard `when`**: `true` thì case được chọn; `false` thì tiếp tục xét nhãn case khác theo ngữ nghĩa `switch`.
6. Nếu guard ném exception, exception **lan ra**; không tự xem như `false` và không tự vào `default`.

```text
                     COMPILE TIME
            Xét dominance giữa case labels
       +------------------------------------+
       | unguarded hoặc guard hằng true:    |
       | có thể dominate pattern phía sau   |
       | guard thường: có thể false         |
       +------------------------------------+
                          |
                          v
                       RUNTIME
                 Đánh giá selector
                          |
                          v
                     Thử pattern
                       /      \
                   không     match
                   match       |
                     |         v
                     |      binding biến
                     |         |
                     |         v
                     |      đánh giá when
                     |        /      \
                     |    true       false
                     |      |          |
                     v      v          v
                 case khác chọn case  case khác
```

Ở cấp compile time, Java không cần biết dữ liệu runtime là `"Java"` hay `"Spring"` để phát hiện một `case CharSequence` không guard đặt trước `case String`. Ở runtime, Java mới đánh giá kết quả `seq.length() > 3` cho một giá trị cụ thể.

Hai tầng này có liên hệ nhưng **không phải một thuật toán giống nhau**.

## 5. Ví dụ hoàn chỉnh: guarded và unguarded patterns cùng một kiểu

Lưu tệp **`DominanceRulesDemo.java`**, biên dịch/chạy bằng Java 21+:

```java
public class DominanceRulesDemo {
    static String classify(Object input) {
        return switch (input) {
            case String s when s.isBlank() -> "blank";
            case String s when s.length() >= 5 -> "long:" + s;
            case String s -> "short:" + s;

            case CharSequence cs when cs.length() >= 5 ->
                    "long-other-sequence";
            case CharSequence cs -> "other-sequence";

            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("  "));
        System.out.println(classify("Java"));
        System.out.println(classify("Spring"));
        System.out.println(classify(new StringBuilder("hello")));
        System.out.println(classify(new StringBuilder("go")));
        System.out.println(classify(5));
        System.out.println(classify(null));
    }
}
```

```bash
javac DominanceRulesDemo.java
java DominanceRulesDemo
```

Đầu ra chính xác:

```text
blank
short:Java
long:Spring
long-other-sequence
other-sequence
other
null
```

**Giải thích từng nhóm:**

- Hai guarded `String` đứng **trước** case `String` không guard. Chúng mô tả chuỗi blank và chuỗi đủ dài; nếu không đạt guard nào, case `String` cuối nhóm nhận các chuỗi còn lại.
- Nhánh `case String s -> ...` không guard bao phủ mọi `String` và đứng **trước** `case CharSequence cs ...`: điều này hợp lệ vì `CharSequence` còn có các kiểu khác, như `StringBuilder`. Nhánh `CharSequence` ở sau không bị `String` dominate.
- Nhánh guarded `CharSequence` phải đứng trước nhánh `CharSequence` không guard. Nếu đổi ngược lại, guarded case cùng kiểu phía sau sẽ bị dominate.
- `Integer 5` không phải `CharSequence`, nên chọn `default`.
- `null` được `case null` nhận riêng. `default` **không tự bắt selector `null`** trong Java 21.

**Điểm học được:** thứ tự từ **guarded chuyên biệt → unguarded còn lại** thường là cách tổ chức rõ ràng cho các case có cùng type pattern. Với thứ tự này, compiler chấp nhận và runtime chọn nhánh theo điều kiện thực tế.

## 6. Ví dụ hoàn chỉnh: pattern rộng có guard đứng trước pattern hẹp

Lưu tệp **`StrictGuardOrdering.java`**:

```java
public class StrictGuardOrdering {
    static String classify(Object input) {
        return switch (input) {
            case CharSequence cs when cs.length() >= 5 -> "long-cs";
            case String s -> "string:" + s;
            case CharSequence cs -> "remaining-cs";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("Spring"));
        System.out.println(classify("Go"));
        System.out.println(classify(new StringBuilder("small")));
    }
}
```

```bash
javac StrictGuardOrdering.java
java StrictGuardOrdering
```

Đầu ra:

```text
long-cs
string:Go
long-cs
```

Ở đây:

- `"Spring"` là `String` và cũng là `CharSequence`; guard của nhánh rộng đầu đúng, nên **nhánh `String` ở sau không chạy**.
- `"Go"` cũng là `CharSequence` nhưng guard đầu sai, nên Java thử nhánh `String` và trả về `string:Go`.
- `StringBuilder("small")` là `CharSequence` có độ dài 5, qua ngay guard đầu và trả về `long-cs`.

Lớp này cho thấy **một guarded pattern rộng có thể đứng trước pattern hẹp mà không tạo lỗi dominance**, nhưng vẫn **ưu tiên nhánh rộng** cho các giá trị thỏa guard. Nếu yêu cầu nghiệp vụ là mọi `String` cần đi vào case `String`, nên viết case `String` trước khi xét `CharSequence` có guard, hoặc điều chỉnh các điều kiện.

## 7. Guard hằng `true`: ngoại lệ quan trọng

Câu lệnh:

```java
case String s when true -> "string";
```

có vẻ là một guarded pattern vì có chữ `when`. Nhưng **`true` là một biểu thức hằng đúng**, vì thế trong **dominance checking**, Java xử lý pattern như trường hợp **không guard**.

Đoạn sau **không biên dịch**:

```java
// static String bad(Object input) {
//     return switch (input) {
//         case String s when true -> "any-string";
//         case String s when s.length() > 3 -> "long-string"; // Dominated
//         default -> "other";
//     };
// }
```

Về logic, case đầu tiên đã chấp nhận mọi chuỗi khác `null`; case sau không bao giờ có cơ hội. Java nhận ra bằng quy tắc dành cho guard hằng đúng.

Không chỉ literal `true`: những biểu thức mà compiler xem là **constant expression với giá trị `true`** cũng cần được hiểu theo quy tắc tương ứng. Đừng thêm `when true` với mục đích “biến pattern không guard thành guarded pattern” để vượt qua lỗi dominance.

Với type pattern bao phủ toàn bộ miền kiểu selector, guard hằng `true` cũng có thể khiến `switch` có **unconditional pattern**. Ví dụ sau **không biên dịch**:

```java
// static String invalid(Object input) {
//     return switch (input) {
//         case Object obj when true -> "object";
//         default -> "other"; // LỖI: unconditional pattern + default
//     };
// }
```

Hãy loại bỏ nhánh `default` thừa hoặc sửa cấu trúc phân loại; `when true` không phải một cách vô hiệu hóa kiểm tra thống trị.

## 8. Guard hằng `false`: không phải lối tạo một nhánh “không bao giờ chạy”

Câu lệnh:

```java
// KHÔNG HỢP LỆ:
// case String s when false -> "unreachable";
```

bị compiler từ chối vì guard là **constant expression có giá trị `false`**. Không nên dùng nó để giữ lại code tạm hoặc thử biến đổi dominance. Nếu một case không còn áp dụng, hãy xóa nó hoặc viết lại quy tắc nghiệp vụ.

Một guard không hằng nhưng luôn trả `false` theo trực giác của người viết **không đồng nghĩa compiler sẽ chứng minh điều đó**. Ví dụ `when isNeverEligible(s)` có thể là một phương thức, và compiler thường không phân tích logic toàn bộ phương thức ấy để loại bỏ case. Vì vậy dominance không thay thế review nghiệp vụ hoặc test thực tế.

## 9. Compiler không chứng minh mọi quan hệ logic giữa các guard

Xét:

```java
static String classify(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> "first";
        case String s when s.isBlank() -> "second";
        case String s -> "otherwise";
        default -> "not a string";
    };
}
```

Trong Java 21+, đoạn này **có thể biên dịch**: compiler không coi hai lời gọi `s.isBlank()` là chứng minh tĩnh rằng nhánh thứ hai bị dominance. Với `String` bất biến và predicate `isBlank()` thuần khiết, nếu nhánh đầu đã không áp dụng do `false` thì nhánh thứ hai cũng sẽ trả `false`; nếu `true` thì nhánh đầu đã nhận rồi. Nhánh `"second"` vì vậy không có ý nghĩa thực tế trong ví dụ.

Điều đó **không phải lỗi compiler**: quy tắc dominance chỉ xét những quan hệ được ngôn ngữ quy định, không yêu cầu suy luận tương đương giữa các biểu thức boolean tùy ý. Với guard có trạng thái hoặc side effect, hai lần gọi biểu thức còn có thể cho kết quả khác nhau.

Tương tự:

```java
case Integer n when n >= 90 -> "A";
case Integer n when n >= 60 -> "PASS";
case Integer n -> "FAIL";
```

Hai guard đầu có miền giá trị **giao nhau**. Java cho phép vì chúng có thể cùng đúng hoặc chỉ một đúng; nếu cả hai đúng thì case phù hợp đầu tiên được chọn. Ở đây `95` nhận `A`, `75` nhận `PASS`. Nếu đảo thứ tự hai guard, `95` có thể bị phân loại thành `PASS`. Compiler không tự sắp xếp theo “độ cụ thể” của điều kiện boolean.

**Quy tắc thực hành:** xem guard như các điều kiện có thứ tự ưu tiên; test các điểm ranh giới và vùng chồng lấp, thay vì tin rằng dominance sẽ phát hiện mọi logic thừa hoặc sai thứ tự.

## 10. Ví dụ hoàn chỉnh: guard chồng lấp nhưng không gây lỗi dominance

Lưu **`ScoreGuardDemo.java`** (Java 21+):

```java
public class ScoreGuardDemo {
    static String band(Object value) {
        return switch (value) {
            case null -> "missing";
            case Integer n when n >= 90 -> "excellent";
            case Integer n when n >= 60 -> "passed";
            case Integer n -> "failed";
            default -> "not-an-integer";
        };
    }

    public static void main(String[] args) {
        System.out.println(band(95));
        System.out.println(band(75));
        System.out.println(band(50));
        System.out.println(band(null));
        System.out.println(band("95"));
    }
}
```

```bash
javac ScoreGuardDemo.java
java ScoreGuardDemo
```

Đầu ra:

```text
excellent
passed
failed
missing
not-an-integer
```

- `95` thỏa cả `n >= 90` và `n >= 60`, nhưng **nhánh guarded đầu tiên** được chọn.
- `75` không đạt `>= 90` nhưng đạt `>= 60`, nên chọn nhánh thứ hai.
- `50` không đạt guard nào, nhưng vẫn là `Integer`, nên được nhánh `case Integer n` không guard xử lý.
- `null` có nhãn riêng; chuỗi `"95"` không khớp `Integer` nên dùng `default`.

Nếu đặt `case Integer n -> "failed"` **trước** các nhánh guarded `Integer`, compiler sẽ báo dominance. Nếu đổi thứ tự hai guard `>= 60` và `>= 90`, compiler **không nhất thiết báo lỗi**, nhưng đầu ra cho `95` sẽ đổi. Đây là điểm phân biệt rõ ràng giữa **lỗi dominance tĩnh** và **bug phân loại nghiệp vụ**.

## 11. Guard và exhaustiveness là hai điều liên quan nhưng khác nhau

Một `switch expression` phải **exhaustive**: compiler cần chứng minh mọi giá trị thuộc miền thông thường được xử lý theo quy tắc Java. Guard có thể `false`, nên **guard thường không đủ để được xem là bao phủ chắc chắn**.

Ví dụ sau **không biên dịch** (Java 21+):

```java
// static String bad(Object value) {
//     return switch (value) {
//         case null -> "null";
//         case Object obj when obj != null -> "object";
//     };
// }
```

Một lập trình viên có thể lập luận: “Nếu không null thì `obj != null` luôn đúng”. Nhưng guard `obj != null` **không phải constant expression `true`**, và Java không chứng minh điều này để biến nhánh có guard thành một unconditional pattern cho mục đích exhaustive. Compiler báo thiếu nhánh bao phủ.

Có hai hướng sửa:

**Cách A — Thêm `default` cho trường hợp compiler chưa chứng minh được:**

```java
static String good(Object value) {
    return switch (value) {
        case null -> "null";
        case Object obj when obj != null -> "object";
        default -> "fallback";
    };
}
```

Với giá trị `Object` bình thường khác `null`, guard đúng và trả `"object"`. `default` ở đây đáp ứng yêu cầu bao phủ tĩnh.

**Cách B — Bỏ guard dư thừa và để type pattern thực sự unconditional:**

```java
static String simpler(Object value) {
    return switch (value) {
        case null -> "null";
        case Object obj -> "object";
    };
}
```

`case Object obj` bao phủ các đối tượng khác `null`; `case null` bao phủ `null`. Không cần `default`.

**Sắc thái đặc biệt:** nếu dùng `case Object obj when true`, compiler coi guard hằng đúng như không guard và có thể chứng minh bao phủ như ví dụ B. Nhưng cách B ngắn gọn hơn và rõ ý định hơn.

Đừng đánh đồng “đoạn code của tôi luôn đúng ở runtime” với “compiler xem case là unconditional khi xét dominance/exhaustiveness”.

## 12. Ảnh hưởng của dominance đến `default` và `case null`

Dominance chủ yếu nói về **một nhãn case có che nhãn khác** theo luật của compiler. Hai nhãn đặc biệt cần được xem riêng:

- **`case null`** tiếp nhận selector `null`. Type pattern như `String s` hoặc `Object obj` **không match `null`**, dù được bảo vệ bằng guard nào.
- **`default`** nhận các giá trị còn lại khi không có nhãn áp dụng theo quy tắc của `switch`. Trong Java 21, `default` **không tự xử lý selector `null`**; nếu thiếu `case null`, selector `null` dẫn đến `NullPointerException`.

Ví dụ hợp lệ:

```java
static String inspect(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when !s.isBlank() -> "nonblank string";
        case String s -> "other string";
        default -> "not a string";
    };
}
```

Một case `String` có guard bình thường đứng trước case `String` không guard là cách sắp xếp phổ biến. Nhưng nếu dùng một **unconditional pattern cho toàn bộ selector**, không được thêm `default` riêng (như minh họa với `case Object obj`).

Không phải mọi câu lệnh có `default` đều là “an toàn hơn”: `default` có thể che một trường hợp kiểu mới nên được xử lý riêng, hoặc bản thân nhãn `default` bị cấm do unconditional pattern. Cân nhắc theo tính đầy đủ và khả năng mở rộng của domain.

## 13. Liên hệ với record patterns và generic patterns

Trong Java 21, record pattern cũng có thể đi kèm guard. Ví dụ minh họa:

```java
record Order(String category, int total) {}

static String route(Object value) {
    return switch (value) {
        case Order(String category, int total) when total >= 100 ->
                "priority:" + category;
        case Order(var category, var total) ->
                "standard:" + category;
        case null -> "missing";
        default -> "unsupported";
    };
}
```

Đây là **đoạn minh họa phương thức Java 21+** với `Order` được khai báo trong cùng môi trường biên dịch; không phải một chương trình độc lập.

Guard `total >= 100` làm nhánh đầu **chỉ áp dụng khi record pattern đã match và số tiền đạt điều kiện**. Nhánh record pattern tiếp theo xử lý những record còn lại, theo phạm vi thực tế của pattern.

Lưu ý thêm: `String category` ở component pattern yêu cầu thành phần khác `null` và đúng kiểu; `var category` có thể binding component `null`. Vì vậy hai record pattern trên **không hoàn toàn giống nhau ngay cả khi bỏ guard**. Muốn suy luận dominance chính xác, phải tính đến **quan hệ giữa toàn bộ pattern** (bao gồm component pattern) chứ không nhìn mỗi tên record và điều kiện `when`.

Trong ứng dụng thực tế, cách an toàn là đặt case có điều kiện chi tiết trước case rộng hơn, biên dịch để bắt lỗi dominance và kiểm thử cả trường hợp record component không khớp hoặc có giá trị `null`.

## 14. Khi nào compiler sẽ báo lỗi, khi nào phải tự viết test?

| Tình huống | Compiler có thể phát hiện? | Hành động |
| --- | --- | --- |
| `CharSequence` không guard trước `String` | **Có, dominance error** | Đổi thứ tự hoặc thêm điều kiện nghiệp vụ ở nhánh rộng nếu thực sự cần |
| `String` không guard trước `String when ...` | **Có, dominance error** | Đặt guarded case lên trước |
| `String when true` trước `String` | **Có, như trường hợp không guard** | Bỏ `when true` hoặc đổi thiết kế |
| `String when false` | **Có, constant-false guard error** | Bỏ nhánh không thể áp dụng |
| Hai guard trùng predicate `isBlank()` | **Không nhất thiết** | Code review và test để loại nhánh vô nghĩa |
| Hai guard chồng lấp `>= 90` và `>= 60` | **Không phải dominance error mặc định** | Kiểm thử ngưỡng và kiểm tra thứ tự ưu tiên |
| Guard ném exception | **Không được chuyển thành guard false** | Xử lý dữ liệu/exception tại đúng vị trí |
| Guard thường trên `Object` dùng thay unconditional pattern | **Có thể gây lỗi non-exhaustive** | Thêm case còn lại hoặc bỏ guard dư |
| `case Object obj when true` cùng `default` | **Có, xung đột unconditional pattern với default** | Loại default hoặc thay đổi cấu trúc |

**Không nên cố “đánh lừa” compiler bằng guard không hằng** chỉ để một nhánh bị che khuất có thể biên dịch. Nếu điều kiện không thể đúng trong logic ứng dụng, compiler có thể không nhận ra, nhưng đây vẫn là code thừa hoặc bug khó bảo trì.

## 15. Checklist để review guard và dominance

Khi đọc một `switch` Java 21+ có nhiều pattern cases:

1. **Ghi lại kiểu selector và tập giá trị có thể đến.** `Object`, `CharSequence`, sealed hierarchy, enum, record hay dữ liệu hỗn hợp?
2. **Xác định quan hệ subtype/bao phủ của các pattern.** Nhánh nào có khả năng khớp mọi giá trị mà nhánh khác khớp?
3. **Đánh dấu các case không guard.** Đặt pattern hẹp trước rộng hoặc phân lại quy tắc khi có nguy cơ dominance.
4. **Đánh dấu các guard là constant `true`.** Đừng coi chúng là guard thông thường khi suy luận dominance.
5. **Phát hiện constant `false`.** Java từ chối ngay từ bước biên dịch; bỏ nhánh không thể chọn.
6. **Xét khả năng guard thông thường trả về `false`.** Đó là lý do nhánh khác phía sau còn cơ hội được chọn.
7. **Xét guard chồng lấp.** Với một giá trị thỏa nhiều guard, nhánh nào đứng trước sẽ được ưu tiên? Có đúng nghiệp vụ không?
8. **Kiểm tra tính exhaustive.** Đừng dùng một guard trông “luôn đúng” nhưng không hằng để thay cho unconditional pattern; bổ sung fallback khi cần.
9. **Kiểm tra null.** Có `case null` nếu selector `null` hợp lệ? `default` không tự tiếp nhận null.
10. **Kiểm tra code ở runtime.** Guard có thể ném exception, tốn chi phí hoặc có side effect; test thứ tự nhánh và các điểm ranh giới.
11. **Đảm bảo phiên bản Java.** `when` trong `switch` cần Java 21+; trong Java 17 nên dùng `instanceof` với `if`/`&&` hoặc `switch` hằng số phù hợp.
12. **Biên dịch các ví dụ nhỏ.** Với dominance, compiler là nguồn kiểm chứng quan trọng; không chỉ dựa vào suy luận từ các giá trị chạy thử.

### Tóm tắt bằng ba cặp

```java
// 1. SAI: nhánh rộng không guard bao phủ nhánh hẹp.
// case CharSequence cs -> "any";
// case String s -> "string";

// 2. ĐÚNG: guard có thể false nên nhánh hẹp vẫn có cơ hội.
// case CharSequence cs when cs.length() > 3 -> "long";
// case String s -> "string";

// 3. SAI: hằng true được xem như không guard khi xét dominance.
// case String s when true -> "any";
// case String s when s.isBlank() -> "blank";
```

**Kết luận:** Guard `when` **làm giảm phạm vi áp dụng thực tế của một case**, do đó một guarded pattern với điều kiện không hằng đúng thường **không dominate** các pattern hẹp/cùng kiểu phía sau như một pattern không guard. Riêng **`when true`** được coi là không guard cho dominance, còn **`when false`** là lỗi biên dịch. Sau khi qua kiểm tra tĩnh, **thứ tự nhánh và kết quả guard runtime** quyết định case nào được chọn; compiler không thay bạn chứng minh mọi quan hệ logic giữa các predicate.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): guarded patterns, dominance, thứ tự nhánh và exhaustive switch.
- [Java Language Specification 21 — `14.11 Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): ngữ nghĩa chọn nhãn, guard và quan hệ dominance.
- [Java Language Specification 21 — `15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): tính exhaustive và kết quả của `switch expression`.
