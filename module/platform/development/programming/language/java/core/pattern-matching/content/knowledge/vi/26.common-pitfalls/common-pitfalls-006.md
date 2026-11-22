# Ép kiểu lại sau khi đã match: lỗi thường gặp trong Java Pattern Matching

## 1. Vấn đề: đã có biến pattern nhưng vẫn cast lại

Khi viết Java theo thói quen cũ, một đoạn kiểm tra kiểu bằng `instanceof` thường được theo sau bởi ép kiểu (*cast*). Nhưng **pattern matching** có thể đồng thời **kiểm tra kiểu** và **ràng buộc giá trị đã khớp** vào một biến có kiểu thích hợp. Lúc đó, ép kiểu lại về đúng kiểu vừa khớp thường là **cast thừa**, không mang thêm bảo đảm nào.

```java
Object value = "Java";

if (value instanceof String text) {
    String again = (String) value; // Cast thừa: đã có biến text kiểu String.
    System.out.println(text.toUpperCase());
}
```

Với biến `text`, trình biên dịch đã biết kiểu tĩnh là `String`. Cast `(String) value` ở ví dụ trên thường vẫn biên dịch được; không nhất thiết là lỗi cú pháp. Tuy nhiên nó làm mã khó đọc hơn, tạo thêm tên biến và có thể dẫn tới lỗi nghiêm trọng hơn nếu lập trình viên **đánh giá lại biểu thức nguồn có tác dụng phụ** thay vì dùng biến đã match.

Phân biệt chính xác:

- `value instanceof String`: kiểm tra kiểu theo cách cũ; **không** tạo biến pattern. Nếu `value` được khai báo là `Object`, có thể cần cast khi gọi API `String`.
- `value instanceof String text`: **type pattern**; kiểm tra kiểu và tạo biến `text` đã có kiểu `String` trong vùng luồng điều khiển hợp lệ.
- `value instanceof Location(var name, Point(var x, var y))`: **record pattern**; kiểm tra và tách thành phần của các `record` lồng nhau.

Type patterns trong `instanceof` ổn định từ **Java 16** (JEP 394). Record patterns và pattern matching for `switch` ổn định từ **Java 21** (JEP 440, 441). Chương trình hoàn chỉnh trong bài cần **JDK 21+**, không dùng `--enable-preview`.

## 2. Trước và sau refactor: cùng logic, không cast thừa

### Cách cũ: kiểm tra `instanceof` rồi cast

```java
static String legacy(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        if (!text.isBlank()) {
            return "text:" + text.trim().toUpperCase(java.util.Locale.ROOT);
        }
    }
    return "other";
}
```

Ở đây, `value instanceof String` chỉ trả `boolean`. Mã gọi `String.isBlank()`, `String.trim()` cần đối tượng có kiểu tĩnh `String`, do đó cast sau kiểm tra là cách viết hợp lý cho Java cũ.

### Cách mới: dùng trực tiếp biến đã match

```java
static String modern(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return "text:" + text.trim().toUpperCase(java.util.Locale.ROOT);
    }
    return "other";
}
```

`text` được khai báo ngay trong type pattern. Vế phải của `&&` chỉ chạy khi vế trái khớp, nên `text.isBlank()` được gọi khi biến đã có giá trị hợp lệ.

Với `" java "`, `"   "`, `42`, và `null`, hai phiên bản lần lượt cho `text:JAVA`, `other`, `other` và `other`. Chương trình ở mục 6 có phép đối chiếu thực tế, ném `AssertionError` nếu kết quả cũ và mới khác nhau.

Điểm lợi chính là **bớt cast lặp, bớt biến trung gian và thể hiện trực tiếp bảo đảm kiểu mà compiler đã kiểm tra**. Không mặc định rằng việc xóa một cast luôn làm chương trình chạy nhanh hơn: JIT có thể tối ưu những thao tác tương đương; cần benchmark nếu hiệu năng thực sự là yêu cầu.

## 3. Cast cùng giá trị đã match thường không làm thay đổi giá trị

```java
if (value instanceof String text) {
    String again = (String) value;
    System.out.println(again == text); // true nếu value vẫn là cùng tham chiếu.
}
```

Ở tình huống nguồn là cùng một tham chiếu không bị thay đổi, cast về `String` **không tạo một String mới** và không biến đổi nội dung. Nó chỉ diễn đạt yêu cầu kiểu đã được type pattern đáp ứng. Lỗi không chỉ là thêm một dòng: nếu các phần khác của code bắt đầu sử dụng `again` thay vì `text`, ý nghĩa của bước match trở nên khó theo dõi.

Không nhầm cast với **mapping** hoặc **chuyển đổi dữ liệu**. `new Dto(text)` tạo một đối tượng đích; `text.toUpperCase()` tạo chuỗi theo API; `(String) value` chỉ cast tham chiếu, không thực hiện những chuyển đổi đó.

## 4. Flow scoping: biết khi nào dùng được biến pattern

Java áp dụng **flow scoping**: biến pattern có hiệu lực khi mọi đường thực thi tới vị trí đó đều bảo đảm pattern đã khớp.

### Trong nhánh `if` đúng

```java
static void show(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length()); // Hợp lệ.
    } else {
        System.out.println("not a String");
        // Không được dùng text ở đây.
    }
}
```

Trong `else`, pattern có thể không khớp. Việc cast `(String) value` tại đó không khắc phục được vấn đề; nó có thể ném `ClassCastException` hoặc không xử lý đúng `null`.

### Short-circuit `&&` và bẫy `||`

**Hợp lệ:**

```java
if (value instanceof String text && text.startsWith("J")) {
    System.out.println(text);
}
```

**Không hợp lệ:**

```java
// Sai: vế phải || có thể chạy khi pattern bên trái KHÔNG khớp.
if (value instanceof String text || text.isEmpty()) {
    System.out.println("found");
}
```

Vế phải của `||` chạy khi vế trái `false`; lúc đó không thể sử dụng `text`. Đừng thay bằng `((String) value).isEmpty()` vì `value` khi đó có thể không phải `String`.

### Guard clause và biến dùng sau `if`

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) return -1;
    return text.length();
}
```

Nhánh phủ định kết thúc phương thức, nên dòng cuối chỉ có thể chạy sau khi `value instanceof String text` thành công. `text` hợp lệ ở dòng cuối. Nếu nhánh phủ định chỉ in log rồi cho phương thức chạy tiếp thì bảo đảm này không còn.

**Kết luận:** Không nên cast lại nhằm “đưa biến ra ngoài scope”. Hãy tổ chức điều kiện và đường đi bằng `if`, guard clause, `&&` hoặc `switch` để compiler có thể chứng minh việc match.

## 5. Pattern matching trong `switch` và record pattern

### Type pattern của `switch`

```java
static String typeLabel(Object value) {
    return switch (value) {
        case String text -> "S:" + text;
        case Integer number -> "I:" + number;
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Mỗi case khai báo biến đúng kiểu. Không cần `(String) value` trong `case String text` hoặc `(Integer) value` trong `case Integer number`. Biến ở case khác không thể được dùng tùy tiện khi case đó không khớp.

**`null`:** `value instanceof String text` là `false` nếu `value == null`. Với `switch`, xử lý `null` phải có chủ đích; `case null` ở ví dụ giải quyết trường hợp này. Không có nhánh xử lý `null` thích hợp, switch trên tham chiếu null có thể ném `NullPointerException`.

### Record pattern với các component lồng nhau

```java
record Point(int x, int y) {}
record Location(String name, Point point) {}
```

Nếu muốn giữ đối tượng nguyên vẹn:

```java
if (value instanceof Location location) {
    Point point = location.point();
    if (point != null) {
        System.out.println(location.name() + ": " + point.x());
    }
}
```

`location` đã là `Location`. Viết `((Location) value).point()` là cast thừa. Khi mục tiêu chỉ là lấy component, dùng nested record pattern:

```java
if (value instanceof Location(var name, Point(var x, var y))) {
    System.out.println(name + ": " + x + "," + y);
}
```

`name` có kiểu `String`, `x` và `y` có kiểu `int` theo khai báo record. Không cần cast lại đối tượng nguồn hay cast từ `Object` để lấy các giá trị này. Nếu component `point == null`, pattern con `Point(...)` không khớp và toàn biểu thức `instanceof` trả `false`.

**Cẩn thận:** `Location(var name, var point)` vẫn có thể ràng buộc `point = null`; `var` tự nó không có nghĩa “component này không null”. Record pattern không tạo bản sao sâu, không tự tạo DTO mới, không tự kiểm tra quy tắc nghiệp vụ. Việc tách component tuân theo **thứ tự khai báo của record**, nên không nên đổi vị trí biến theo cảm tính.

## 6. Ví dụ đầy đủ có thể biên dịch và chạy

Tạo file **`CastAfterMatchDemo.java`**:

```java
public class CastAfterMatchDemo {
    record Point(int x, int y) {}
    record Location(String name, Point point) {}

    static String legacy(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            if (!text.isBlank()) {
                return "text:" + text.trim().toUpperCase(java.util.Locale.ROOT);
            }
        }
        return "other";
    }

    static String modern(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "text:" + text.trim().toUpperCase(java.util.Locale.ROOT);
        }
        return "other";
    }

    static boolean repeatedCastSame(Object value) {
        if (value instanceof String text) {
            String again = (String) value;
            return again == text;
        }
        return false;
    }

    static String coordinates(Object value) {
        if (value instanceof Location(var name, Point(var x, var y))) {
            return name + "@(" + x + "," + y + ")";
        }
        return "no-location";
    }

    static int lengthOrMinusOne(Object value) {
        if (!(value instanceof String text)) return -1;
        return text.length();
    }

    static String typeLabel(Object value) {
        return switch (value) {
            case String text -> "S:" + text;
            case Integer number -> "I:" + number;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    static void check(Object value) {
        String left = legacy(value);
        String right = modern(value);
        if (!left.equals(right)) {
            throw new AssertionError(left + " != " + right);
        }
        System.out.println(right);
    }

    public static void main(String[] args) {
        check(" java ");
        check("   ");
        check(42);
        check(null);
        System.out.println("same-ref:" + repeatedCastSame("hi"));
        System.out.println(coordinates(new Location("HCM", new Point(2, 3))));
        System.out.println(coordinates(new Location("HCM", null)));
        System.out.println(lengthOrMinusOne("abc"));
        System.out.println(lengthOrMinusOne(5));
        System.out.println(typeLabel("ok"));
        System.out.println(typeLabel(7));
        System.out.println(typeLabel(null));
    }
}
```

Chạy bằng JDK 21 trở lên:

```bash
javac --release 21 CastAfterMatchDemo.java
java CastAfterMatchDemo
```

**Stdout chính xác:**

```text
text:JAVA
other
other
other
same-ref:true
HCM@(2,3)
no-location
3
-1
S:ok
I:7
NULL
```

Đã chạy trên JDK 24 với cú pháp Java 21 và xác nhận đúng **12 dòng** trên. Phương thức `check` so sánh kết quả cũ với kết quả refactor; không chỉ in đầu ra mà còn ném `AssertionError` nếu chúng khác nhau.

| Ca kiểm tra | Hành vi |
| --- | --- |
| `" java "` | Hai phương thức cùng trả `text:JAVA` |
| Chuỗi blank, `Integer`, `null` | Đều trả `other` |
| Cast lại sau match cùng giá trị ổn định | `same-ref:true`, không tạo tham chiếu mới |
| `Location("HCM", Point(2,3))` | Pattern lồng tách tọa độ, trả `HCM@(2,3)` |
| `Location("HCM", null)` | Pattern con không khớp, trả `no-location` |
| Guard clause nhận `"abc"` và `5` | Trả `3` và `-1` |
| Switch với `"ok"`, `7`, `null` | Trả `S:ok`, `I:7`, `NULL` |

## 7. Lỗi nghiêm trọng hơn: đọc lại biểu thức đã match

Một lỗi dễ xuất hiện khi chuyển code cũ sang pattern matching là **gọi lại biểu thức có side effect** rồi ép kiểu giá trị mới:

```java
// Sai: hai lần removeFirst() là hai lần tiêu thụ dữ liệu khác nhau.
if (queue.removeFirst() instanceof String text) {
    String again = (String) queue.removeFirst();
    System.out.println(again);
}
```

Pattern đã kiểm tra **giá trị do lần `removeFirst()` đầu tiên trả về**, không phải mọi kết quả sau này của phương thức. Lần gọi thứ hai có thể trả `Integer` hoặc hàng đợi đã hết; cast này có thể ném `ClassCastException` (hoặc ngoại lệ từ thao tác lấy phần tử).

**Đúng nếu muốn dùng phần tử vừa match:**

```java
if (queue.removeFirst() instanceof String text) {
    System.out.println(text);
}
```

Đoạn kiểm thử riêng dưới đây có thể đặt trong phương thức hoặc chạy trong JShell:

```java
var queue = new java.util.ArrayDeque<Object>();
queue.add("first");
queue.add(99);

if (queue.removeFirst() instanceof String text) {
    try {
        String again = (String) queue.removeFirst();
        System.out.println(again);
    } catch (ClassCastException ex) {
        System.out.println("first=" + text
                + ", second-cast=ClassCastException");
    }
}
```

Đầu ra từ lệnh in trong đoạn trên:

```text
first=first, second-cast=ClassCastException
```

Đã xác minh tình huống này bằng JDK 24: `text` vẫn chứa `"first"`, nhưng lần đọc thứ hai lấy `Integer(99)` nên cast thất bại.

**Nguyên tắc quan trọng:** Dùng **biến pattern** để xử lý đúng giá trị đã được kiểm tra, nhất là khi nguồn là iterator, queue, stream-like API, truy vấn dữ liệu, API ngẫu nhiên hoặc accessor có tác dụng phụ. Đừng thay “cast dư thừa” bằng “cast kết quả mới” rồi tưởng logic không đổi.

## 8. Khi nào cast có mục đích và không nên xóa tùy tiện?

### 8.1. Chưa dùng pattern variable

```java
if (value instanceof String) {
    String text = (String) value;
}
```

Ở đây chỉ có kiểm tra kiểu kiểu cũ; nếu chưa chuyển sang cú pháp `String text` thì cast có vai trò để biến `Object` thành `String` trong nhánh đã kiểm tra.

### 8.2. Cần kiểu hẹp hơn kiểu đã match

```java
if (value instanceof CharSequence chars) {
    System.out.println(chars.length());
    if (chars instanceof String text) {
        System.out.println(text.toUpperCase());
    }
}
```

`chars` có kiểu `CharSequence`, không bảo đảm là `String`. Có thể là `StringBuilder`. Type pattern thứ hai thực hiện kiểm tra bổ sung chính đáng thay vì cast mù sang `String`.

### 8.3. Cố ý thay đổi kiểu tĩnh để chọn overload

```java
static void handle(Object value) {
    System.out.println("Object");
}

static void handle(CharSequence value) {
    System.out.println("CharSequence");
}

// Bên trong phương thức có Object input:
if (input instanceof String text) {
    handle(text);          // Chọn handle(CharSequence).
    handle((Object) text); // Chọn handle(Object).
}
```

Hai phương thức overload và đoạn `if` ở trên là **ví dụ minh họa phải đặt vào class/phương thức thích hợp**, không phải file biên dịch độc lập. Cast `(Object) text` cố ý đổi kiểu tĩnh của biểu thức nhằm chọn overload; nó khác với cast `(String) input` khi đã có `String text`.

### 8.4. Chuyển đổi dữ liệu thay vì cast tham chiếu

`new ResponseDto(text)`, `Integer.parseInt(text)` hay một phương thức formatter là **mapping hoặc conversion**. Chúng có thể cần thiết sau match, nhưng không phải cast lại cùng kiểu. Hãy đặt tên rõ cho trách nhiệm chuyển đổi, tránh sử dụng cast như một cơ chế validation không thực sự kiểm tra dữ liệu nghiệp vụ.

## 9. Generic types và những “bảo đảm kiểu” không tồn tại

Vì **type erasure**, `instanceof` không tự chứng minh mọi phần tử trong một `List` là `String`. Với biến `Object value`, cú pháp sau không dùng được để kiểm tra tham số generic:

```java
// Không hợp lệ trong ngữ cảnh Object: List<String> không reifiable.
if (value instanceof java.util.List<String> strings) {
    System.out.println(strings.size());
}
```

Cách đúng là kiểm tra container với wildcard và kiểm tra từng phần tử:

```java
if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

Đây là các đoạn minh họa bên trong một phương thức với biến `value`. Cast `List<?>` sang `List<String>` không bổ sung kiểm tra runtime thật của các phần tử; unchecked cast còn có thể che lỗi dữ liệu đến lúc sử dụng về sau.

## 10. Các sai lầm thường gặp và cách sửa

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| `if (x instanceof String s) { String t=(String)x; }` | Biến phụ và cast lặp không cần thiết | Dùng `s` trực tiếp |
| `case String s -> ((String)x).length()` | Bỏ qua biến pattern đã có kiểu | Dùng `s.length()` |
| Đã match `Location(...)` rồi cast lại `x` để gọi accessor | Code dài, mất ý nghĩa deconstruction | Dùng các component pattern hoặc giữ `Location location` nếu cần toàn bộ object |
| Đặt `s` ở vế phải `||` sau type pattern | Không có bảo đảm match | Dùng `&&` nếu điều kiện cần biến pattern |
| Dùng biến pattern trong `else` | Không chắc nó đã được gán | Chỉ dùng ở nhánh có match hoặc guard clause hợp lệ |
| Gọi `removeFirst()` hoặc `next()` hai lần để cast | Dùng hai giá trị khác nhau, gây side effect | Dùng biến pattern của lần gọi đầu |
| Giả định `instanceof` trên `null` ném lỗi | Sai về ngữ nghĩa | `null instanceof T t` trả `false` |
| Bỏ xử lý null trong pattern switch | Switch selector null có thể ném ngoại lệ | `case null` hoặc guard riêng |
| Cast `CharSequence` sang `String` không kiểm tra | Có thể `ClassCastException` | Dùng thêm `instanceof String text` |
| Cast danh sách generic để né validation | Không thực sự chứng minh kiểu phần tử | Dùng `List<?>` và kiểm tra phần tử |

## 11. Bài tập tự luyện

**Bài A — bỏ cast:** Viết lại phương thức sau bằng một type pattern và một điều kiện `&&`:

```java
static int score(Object source) {
    if (source instanceof String) {
        String text = (String) source;
        if (!text.isBlank()) return text.length();
    }
    return 0;
}
```

Đáp án:

```java
static int score(Object source) {
    if (source instanceof String text && !text.isBlank()) {
        return text.length();
    }
    return 0;
}
```

Các ca nên thử: `" Java "` cho `6` (vì không gọi `trim`), `"   "` cho `0`, `123` cho `0`, `null` cho `0`.

**Bài B — record lồng:** Cho `record Coordinate(int x, int y) {}` và `record Checkpoint(String code, Coordinate point) {}`. Viết điều kiện match để in code và tổng tọa độ, không cast.

```java
// Bên trong phương thức có Object input.
if (input instanceof Checkpoint(var code, Coordinate(var x, var y))) {
    System.out.println(code + ":" + (x + y));
}
```

Nếu `point == null`, nested record pattern không khớp và nhánh không chạy; không cần cast và không gây `NullPointerException` từ phép match này.

**Bài C — side effect:** Xác định lỗi trong đoạn:

```java
if (iterator.next() instanceof String text) {
    String again = (String) iterator.next();
    use(again);
}
```

Đáp án: không chỉ cast thừa mà `iterator.next()` đã gọi **hai lần**, có thể lấy phần tử khác hoặc hết iterator. Nếu mục tiêu xử lý phần tử vừa match, dùng `use(text);`. Đây là mã minh họa, giả sử `iterator` và `use` đã tồn tại trong ngữ cảnh.

## 12. Checklist khi refactor

1. **Có type/record pattern variable chưa?** Nếu đã có, dùng nó trước khi định viết cast đến cùng kiểu.
2. **Scope có bảo đảm match không?** Kiểm tra nhánh `if`, `&&`, guard clause, `switch` và các đường đi có thể thất bại.
3. **Nguồn có ổn định không?** Không gọi lại biểu thức có side effects để lấy một giá trị mới rồi cast.
4. **Cast có ý nghĩa khác không?** Phân biệt cast cùng kiểu dư thừa với kiểm tra subtype hẹp hơn, lựa chọn overload hoặc conversion thật sự.
5. **Có `null`, record component nullable hoặc generic type không?** Pattern không thay validation; đừng giả định thông tin runtime mà Java không kiểm tra.
6. **Đã kiểm thử hành vi cũ và mới chưa?** Bao gồm giá trị đúng kiểu, sai kiểu, `null`, dữ liệu biên và lỗi có tác dụng phụ.

**Ghi nhớ:** Khi pattern đã match, biến pattern là giá trị đã được kiểm tra kiểu. Viết code dựa trên biến đó; đừng ép kiểu lại chỉ vì thói quen cũ, đặc biệt đừng đánh giá lại biểu thức có tác dụng phụ rồi giả định kết quả vẫn là đối tượng đã match.

Tài liệu chính thức:

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
