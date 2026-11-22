# Kết hợp pattern với phép phủ định trong Java 21

## 1. Mục tiêu bài học

**Pattern matching** giúp kiểm tra hình dạng/kiểu của một giá trị và, khi khớp, đưa các thành phần cần thiết vào biến pattern. **Phép phủ định** `!` lại làm việc trên kết quả boolean. Khi kết hợp chúng, điều quan trọng nhất là phân biệt **nhánh nào chứng minh pattern đã khớp** với **nhánh nào chỉ biết pattern không khớp**. Sự khác biệt quyết định phạm vi hợp lệ của biến pattern và tính an toàn của biểu thức kết hợp `&&`, `||`.

Sau bài này, bạn có thể:

- Viết điều kiện `!(value instanceof String s)`, phủ định một **record pattern** và áp dụng guard clause (thoát sớm).
- Hiểu **flow scoping**: vì sao có lúc dùng được `s` sau câu lệnh `if` hoặc bên phải `||`, có lúc trình biên dịch báo không tìm thấy biến.
- Kết hợp `!`, `&&`, `||` với điều kiện phụ, áp dụng luật De Morgan và tránh `NullPointerException`.
- Dùng phủ định trong **guard `when`** của pattern `switch`, đồng thời hiểu rằng `case !Pattern` không phải cú pháp pattern của Java 21.
- Phân biệt input `null`, record lồng nhau chứa `null`, pattern không khớp và điều kiện guard không đạt.

**Phiên bản:** Type pattern với `instanceof` ổn định từ Java 16 (JEP 394). Record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) được chuẩn hóa trong **Java 21**. Bài sử dụng JDK 21+ và không cần bật preview.

## 2. Phủ định pattern chính là phủ định *kết quả match*

Một pattern có thể được kiểm tra bằng toán tử `instanceof`:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

Điều kiện `value instanceof String text` có hai ý nghĩa liên quan: giá trị thực sự khớp kiểu `String` và khi thành công, biến pattern `text` được ràng buộc với giá trị đó.

Đặt `!` ở ngoài biểu thức `instanceof` để đảo boolean:

```java
Object value = 42;
if (!(value instanceof String text)) {
    System.out.println("Khong phai String");
}
```

Biểu thức phủ định sẽ `true` khi `value` không phải `String` **hoặc bằng `null`**. Tuy nhiên, trong nhánh đúng của điều kiện đã phủ định, **`text` không được bảo đảm có giá trị** nên không thể dùng nó ở đó. `!` không biến "String pattern" thành một kiểu pattern âm có biến riêng; nó chỉ đảo kết quả kiểm tra.

Có thể hình dung:

| Giá trị `value` | `value instanceof String text` | `!(value instanceof String text)` | Có thể dùng `text` ở đâu? |
| --- | --- | --- | --- |
| `"Hi"` | `true`, bind `text` | `false` | Nhánh sau khi đã chứng minh pattern đúng |
| `123` | `false` | `true` | Không thể dùng `text` chỉ từ nhánh phủ định |
| `null` | `false` | `true` | Không thể dùng `text` chỉ từ nhánh phủ định |

**Cú pháp đúng:** `!(value instanceof String text)`. Viết `!value instanceof String text` là sai vì `!` chỉ nhận biểu thức boolean, không thể phủ định trực tiếp một biến `Object` theo cách đó.

## 3. Flow scoping: biến pattern phụ thuộc đường đi chương trình

Khác với biến cục bộ được khai báo thông thường, phạm vi của biến pattern được trình biên dịch xác định theo **những đường thực thi mà pattern chắc chắn khớp**.

### 3.1. Phủ định + nhánh thoát sớm

Đây là cách sử dụng phổ biến nhất:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "not a String";
    }
    // Đến đây chỉ có thể là trường hợp đã match String.
    return text.trim().toUpperCase();
}
```

Khi nhánh `if` chạy, hàm đã `return`. Nếu chương trình đến dòng sau `if`, điều kiện `!(...)` phải là `false`, nghĩa là `value instanceof String text` đã `true`. Do đó **`text` nằm trong phạm vi sử dụng hợp lệ sau `if`**.

Tương tự, có thể dùng `throw` trong nhánh không khớp:

```java
if (!(value instanceof String text)) {
    throw new IllegalArgumentException("Expected String");
}
System.out.println(text.length());
```

Các đoạn trên là ví dụ trong thân phương thức. Chúng minh họa ý tưởng **guard clause**: xử lý trường hợp bị loại trước, để phần còn lại không cần lồng sâu bên trong nhánh dương.

### 3.2. Sử dụng `else`

Không bắt buộc phải `return` ngay. Nếu dùng `else`, biến pattern cũng được bảo đảm đã bind trong nhánh đó:

```java
if (!(value instanceof String text)) {
    System.out.println("Different type or null");
} else {
    System.out.println(text.length());
}
```

Nhánh `else` chỉ chạy khi phủ định là `false`, tức match thật đã thành công.

### 3.3. Những vị trí không hợp lệ

Các đoạn sau **cố ý có lỗi biên dịch**:

```java
// SAI: nhánh true của !(...) không bảo đảm text tồn tại.
if (!(value instanceof String text)) {
    System.out.println(text.length());
}

// SAI: vế trái đúng của || chưa hề bảo đảm text được bind.
if (value instanceof String text || text.isBlank()) {
    // ...
}

// SAI: vế trái đúng của && là trường hợp pattern không khớp.
if (!(value instanceof String text) && text.isBlank()) {
    // ...
}
```

Trình biên dịch thường báo không tìm thấy `text` tại chỗ sử dụng sai. Thực chất vấn đề nằm ở **dòng chảy thông tin về pattern**, không phải chỉ là dấu ngoặc hoặc vị trí khai báo.

## 4. Kết hợp phủ định với `&&` và `||`

Java đánh giá `&&` và `||` từ trái sang phải theo quy tắc **short-circuit**:

- `a && b`: chỉ đánh giá `b` nếu `a` là `true`.
- `a || b`: chỉ đánh giá `b` nếu `a` là `false`.

Nhờ vậy, ta có thể viết điều kiện sử dụng biến pattern một cách hợp lệ khi đường thực thi dẫn tới vế phải đã chứng minh pattern khớp.

### 4.1. Pattern dương với `&&`

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
```

Vế phải chỉ chạy nếu `value instanceof String text` là `true`. `text` đã tồn tại và không `null`, vì thế `text.isBlank()` an toàn.

### 4.2. Pattern phủ định với `||`

```java
if (!(value instanceof String text) || text.isBlank()) {
    return "invalid";
}
return text.trim();
```

Vế phải `text.isBlank()` chỉ chạy khi `!(value instanceof String text)` là `false`, tức pattern dương đã match. Do nhánh `if` luôn `return` khi điều kiện đúng, mã sau `if` biết `text` là `String` không blank.

Ví dụ thực tế khi có nhiều tiêu chí:

```java
record User(String name, int age) {}

static String check(Object value) {
    if (!(value instanceof User(String name, int age))
            || name.isBlank()
            || age < 18) {
        return "not eligible";
    }
    return "eligible: " + name;
}
```

- Nếu `value` không phải `User`, hoặc component `name` bằng `null` nên nested `String name` không khớp, vế đầu đúng và các vế còn lại **không chạy**.
- Nếu match thành công, `name` và `age` đã được bind, nên các điều kiện phụ có thể chạy an toàn.
- Nếu không bị loại, các biến pattern tiếp tục dùng được sau câu lệnh `if`.

### 4.3. Bảng kiểm tra cách ghép điều kiện

| Điều kiện | Dùng biến pattern ở vế phải? | Lý do |
| --- | --- | --- |
| `value instanceof String s && !s.isBlank()` | Có | Vế phải chỉ chạy sau match thành công |
| `!(value instanceof String s) &#124;&#124; s.isBlank()` | Có | Vế phải chỉ chạy khi phủ định sai, tức match thành công |
| `value instanceof String s &#124;&#124; s.isBlank()` | Không | Khi vế phải chạy, match đã thất bại |
| `!(value instanceof String s) && s.isBlank()` | Không | Khi vế phải chạy, match đã thất bại |

**Quan trọng:** Không đảo một toán tử tùy tiện rồi giữ nguyên vế phải. Trước khi dùng biến pattern, hãy hỏi: *mọi đường đi tới biểu thức này có bảo đảm pattern gốc đã khớp chưa?*

## 5. Phủ định record pattern và nested pattern

Java 21 cho phép tách component của record ngay trong pattern:

```java
record Point(int x, int y) {}

Object value = new Point(-1, 3);
if (!(value instanceof Point(var x, var y))) {
    // value không khớp Point (hoặc value là null).
    return;
}
// x và y có thể dùng được ở đây.
System.out.println(x + "," + y);
```

Đoạn trên chỉ minh họa trong phương thức trả `void`. `!` phủ định **toàn bộ** phép match, gồm điều kiện đối tượng là record `Point` và phép tách các component. Nếu `value` là `Point`, vế phủ định `false` và các biến `x`/`y` dùng được sau nhánh `return`.

Với nested record:

```java
record Segment(Point start, Point end) {}

if (!(value instanceof Segment(
        Point(var x1, var y1),
        Point(var x2, var y2)))) {
    return "not a complete Segment";
}
return x1 + "," + y1 + " -> " + x2 + "," + y2;
```

Đoạn trên minh họa trong phương thức trả `String` với biến `value` có kiểu phù hợp, ví dụ `Object`. Phép match thất bại nếu:

1. `value` không phải `Segment`, hoặc `value == null`.
2. `start` hoặc `end` là `null`, nên nested pattern `Point(...)` tương ứng không khớp.
3. Một component nested không đáp ứng pattern đã viết.

Nhánh phủ định xử lý chung các trường hợp không khớp. Chỉ khi record và cả hai `Point` lồng nhau đã match thành công, bốn biến `x1`, `y1`, `x2`, `y2` mới được dùng để tạo kết quả.

Cần phân biệt **record pattern không khớp** với **record khớp nhưng dữ liệu không đáp ứng điều kiện nghiệp vụ**. Ví dụ `Point(-1, 3)` vẫn **khớp** `Point(var x, var y)`; việc tọa độ âm phải được kiểm tra sau đó hoặc trong guard `when`.

## 6. Toán tử `!` trong pattern `switch` với `when`

Java 21 hỗ trợ pattern matching cho `switch` và mệnh đề `when` để thêm điều kiện boolean sau khi pattern đã match:

```java
return switch (value) {
    case Point(var x, var y) when !(x >= 0 && y >= 0) ->
            "point outside quadrant";
    case Point(var x, var y) ->
            "point inside quadrant";
    case null -> "null";
    default -> "other";
};
```

Ý nghĩa:

- `case Point(var x, var y)` tách tọa độ trước.
- `when !(x >= 0 && y >= 0)` phủ định **điều kiện của tọa độ**, không phủ định kiểu `Point`.
- Nếu là `Point` mà guard đầu tiên sai, nhánh `Point` tổng quát phía sau tiếp tục có cơ hội khớp.
- `case null` xử lý đối tượng đầu vào `null`; `default` không tự thay thế nhánh `null` theo cách xử lý thông thường của pattern `switch`.

Một ví dụ với `String`:

```java
return switch (value) {
    case String text when !text.isBlank() -> "nonblank";
    case String text -> "blank";
    case null -> "null";
    default -> "other";
};
```

Ở đây `!text.isBlank()` hợp lệ vì guard `when` chỉ được đánh giá **sau khi** `case String text` match thành công. Đặt nhánh `case String text` tổng quát lên trước sẽ khiến nhánh chuyên biệt phía sau bị che (dominated).

**Không có cú pháp `case !Point(...)` hoặc `case !(String s)` để tạo "negative type pattern" trong Java 21.** Muốn xử lý các giá trị không phải kiểu nào đó, thường dùng nhánh `default` (và nhánh `null` nếu cần) hoặc một `if (!(value instanceof ...))` bên ngoài. Dùng `when !condition` khi muốn phủ định **thuộc tính của giá trị đã match**.

## 7. Chương trình Java 21 hoàn chỉnh

Tạo tệp **`NegatedPatternDemo.java`** như sau. Chương trình kết hợp phủ định type pattern, record pattern, nested record pattern, điều kiện phụ và pattern `switch` trong cùng một bài thực hành.

```java
import java.util.Locale;

public class NegatedPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record User(String name, int age) {}

    static String inspectText(Object value) {
        if (!(value instanceof String text)) {
            return "not a String";
        }
        if (text.isBlank()) {
            return "blank";
        }
        return "text: " + text.trim().toUpperCase(Locale.ROOT);
    }

    static String eligible(Object value) {
        if (!(value instanceof User(String name, int age))
                || name.isBlank()
                || age < 18) {
            return "not eligible";
        }
        return "eligible: " + name;
    }

    static String inspectPoint(Object value) {
        if (!(value instanceof Point(var x, var y))) {
            return "not a Point";
        }
        if (x < 0 || y < 0) {
            return "negative coordinate";
        }
        return "point=" + x + "," + y;
    }

    static String segmentInfo(Object value) {
        if (!(value instanceof Segment(
                Point(var x1, var y1),
                Point(var x2, var y2)))) {
            return "not a complete Segment";
        }
        return x1 + "," + y1 + " -> " + x2 + "," + y2;
    }

    static String classify(Object value) {
        return switch (value) {
            case Point(var x, var y) when !(x >= 0 && y >= 0) ->
                    "point outside quadrant";
            case Point(var x, var y) -> "point inside quadrant";
            case String s when !s.isBlank() -> "nonblank string";
            case String s -> "blank string";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspectText(null));
        System.out.println(inspectText("  java  "));
        System.out.println(inspectText("  "));

        System.out.println(eligible(new User("An", 20)));
        System.out.println(eligible(new User("", 20)));
        System.out.println(eligible("other"));

        System.out.println(inspectPoint(new Point(-1, 3)));
        System.out.println(inspectPoint(new Point(2, 3)));

        System.out.println(segmentInfo(new Segment(
                new Point(1, 2), new Point(5, 6))));
        System.out.println(segmentInfo(new Segment(
                null, new Point(5, 6))));

        System.out.println(classify(new Point(-1, 2)));
        System.out.println(classify(new Point(1, 2)));
        System.out.println(classify("hi"));
        System.out.println(classify(""));
        System.out.println(classify(null));
    }
}
```

Biên dịch/chạy trên JDK 21 hoặc mới hơn:

```bash
javac --release 21 NegatedPatternDemo.java
java NegatedPatternDemo
```

**Kết quả thực tế:**

```text
not a String
text: JAVA
blank
eligible: An
not eligible
not eligible
negative coordinate
point=2,3
1,2 -> 5,6
not a complete Segment
point outside quadrant
point inside quadrant
nonblank string
blank string
null
```

Phân tích:

1. `inspectText(null)` trả `"not a String"` vì `instanceof` với `null` là `false`; phép phủ định biến kết quả thành `true`.
2. Với `"  java  "`, pattern `String text` match; `text` vẫn có thể truy cập sau nhánh `return` dành cho trường hợp không khớp.
3. `eligible` dùng `||` theo thứ tự: không phải `User` thì trả về ngay, còn khi đã match mới dùng `name.isBlank()` và `age < 18`. Không có lỗi truy cập biến pattern.
4. `inspectPoint(new Point(-1, 3))` không rơi vào nhánh phủ định type pattern vì đối tượng thật sự là `Point`; kết quả `"negative coordinate"` đến từ kiểm tra dữ liệu riêng.
5. `segmentInfo` trả `"not a complete Segment"` cho `Segment(null, ...)` vì nested `Point(...)` không khớp với component `null`.
6. `classify` cho thấy `when !(...)` phù hợp khi cần phủ định điều kiện tọa độ hoặc `!s.isBlank()`, rồi nhường trường hợp còn lại cho pattern tổng quát.
7. Chương trình chạy hoàn toàn bằng mã Java 21 đã được chuẩn hóa, không cần flags preview.

## 8. Luật De Morgan và cách viết dễ đọc

Khi biểu thức phủ định gồm nhiều điều kiện, hai luật logic hữu ích là:

```text
!(A && B)  ==  !A || !B
!(A || B)  ==  !A && !B
```

Ví dụ với tọa độ:

```java
!(x >= 0 && y >= 0)
```

tương đương:

```java
x < 0 || y < 0
```

Hai biểu thức trên nhận diện điểm nằm ngoài góc phần tư có cả hai tọa độ không âm (giả định `x`, `y` là `int`). Với code thực tế, cách viết `x < 0 || y < 0` thường trực tiếp và dễ đọc hơn; cách phủ định có ích khi diễn đạt "không thỏa toàn bộ quy tắc".

Nhưng **De Morgan áp dụng cho biểu thức boolean, không phải cú pháp biến pattern**. Việc biến một phần điều kiện từ `true` sang `false` có thể làm thay đổi điểm mà biến được bảo đảm đã bind. Ví dụ hai kiểu viết sau đều hợp lệ vì vẫn kiểm tra kiểu trước khi gọi `isBlank()`:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}

if (!(value instanceof String text) || text.isBlank()) {
    return;
}
// text đã bind và không blank.
System.out.println(text);
```

Đoạn thứ hai minh họa trong phương thức trả `void`; không thể chỉ đổi `&&` thành `||` rồi bỏ qua logic phủ định và quyền truy cập biến. Đối với phép kiểm tra có side effect, nên giữ thứ tự và cấu trúc short-circuit rõ ràng.

## 9. Các lỗi thường gặp và cách sửa

### Lỗi 1: Truy cập biến trong nhánh match thất bại

Sai:

```java
if (!(value instanceof String text)) {
    System.out.println(text.length()); // không biên dịch
}
```

Sửa: xử lý trường hợp thất bại rồi `return`/`throw`, hoặc sử dụng `text` trong nhánh `else`.

### Lỗi 2: Dùng `||` sau pattern dương

Sai:

```java
if (value instanceof String text || text.isBlank()) {
    // không biên dịch do text chưa chắc đã bind ở vế phải
}
```

Sửa theo mục tiêu: nếu muốn chấp nhận chuỗi không blank, dùng `value instanceof String text && !text.isBlank()`. Nếu muốn loại giá trị không phải chuỗi hoặc chuỗi blank, dùng `!(value instanceof String text) || text.isBlank()`.

### Lỗi 3: Nhầm null với pattern phủ định

`null instanceof String` và `null instanceof Point` đều là `false`; `!(...)` do đó là `true`. Nếu `null` có nghĩa nghiệp vụ riêng, tách nhánh xử lý sớm hoặc dùng `case null` trong `switch`.

### Lỗi 4: Coi phủ định một nested pattern là phủ định riêng một component

`!(value instanceof Segment(Point(...), Point(...)))` phủ định cả phép match. Có thể thất bại vì đối tượng ngoài sai kiểu, vì một component bằng `null` hoặc vì nested pattern không khớp. Nếu cần thông báo lỗi chính xác cho từng trường hợp, hãy chia thành các bước kiểm tra nhỏ hơn.

### Lỗi 5: Dùng phủ định như một `case` độc lập

Viết `case !String s` hoặc `case !Point(...)` không phải pattern syntax hợp lệ của Java 21. Hãy dùng `default`/`case null` cho loại đối tượng khác và `when !predicate` cho thuộc tính phủ định của đối tượng đã match.

### Lỗi 6: Sai thứ tự các nhánh của `switch`

Đặt `case String s` trước `case String s when !s.isBlank()` làm nhánh có guard trở thành không thể tới được theo quy tắc dominance. Hãy đặt trường hợp cụ thể trước, tổng quát sau.

### Lỗi 7: Cho rằng pattern matching làm thay đổi dữ liệu

`instanceof`, record patterns và phủ định `!` chỉ quyết định luồng điều khiển và tách giá trị; chúng không tự chuyển đổi, sao chép hay làm bất biến object. Khi component là mảng/`List` mutable, biến pattern có thể tham chiếu tới chính object đó. Nếu cần bất biến, phải thiết kế record và defensive copy phù hợp.

## 10. Khi nào nên dùng phủ định?

- **Guard clause**: dùng `if (!(input instanceof ExpectedType matched)) return ...;` để xử lý đầu vào không hợp lệ, giữ phần xử lý chính ít lồng nhau.
- **Quy tắc loại trừ**: dùng `||` và phủ định pattern để loại mọi trường hợp không thỏa kiểu, định dạng hoặc quyền, theo thứ tự kiểm tra an toàn.
- **Record lồng nhau**: dùng phủ định toàn bộ record pattern khi chỉ cần phân biệt "cấu trúc hợp lệ" với "cấu trúc khác"; tách nhiều nhánh nếu cần chẩn đoán từng component.
- **Pattern `switch`**: dùng `when !predicate` để định nghĩa nhóm dữ liệu đặc biệt trong một kiểu đã match; có nhánh tổng quát theo sau.
- **Biểu thức đơn giản**: nếu chỉ cần kiểm tra giá trị `x < 0`, hãy viết trực tiếp; không cần thêm pattern hoặc tầng phủ định nếu chúng không cải thiện tính rõ ràng.

## 11. Câu hỏi tự kiểm tra

1. **Khi `obj == null`, `!(obj instanceof String s)` là gì?**  
   Là `true` vì `instanceof` không match `null`.

2. **Vì sao `s` có thể xuất hiện sau `if (!(obj instanceof String s)) return;`?**  
   Chỉ đường đi mà `instanceof` đã match mới vượt qua lệnh `return`.

3. **Vì sao `if (!(obj instanceof String s) && s.isBlank())` không biên dịch?**  
   Vế phải chỉ chạy khi pattern đã thất bại; `s` không được bảo đảm đã bind.

4. **Nếu `value` là `Point(-2, 3)`, `!(value instanceof Point(var x, var y))` là gì?**  
   Là `false`. Đối tượng match kiểu `Point`; tọa độ âm không làm pattern thất bại.

5. **`when !(x >= 0 && y >= 0)` trong `case Point(var x, var y)` kiểm tra điều gì?**  
   Sau khi match `Point`, guard chọn trường hợp có ít nhất một tọa độ âm.

6. **Có thể dùng `case !(String s)` trong Java 21 không?**  
   Không. `!` dùng trong biểu thức boolean, chẳng hạn guard `when`, không phải dạng pattern phủ định độc lập.

7. **Tại sao `Segment(Point(...), Point(...))` không match `Segment(null, new Point(1,2))`?**  
   Nested `Point(...)` không match component `null`.

## Tham khảo

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 Language Specification §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
- [Java SE 21 Language Specification §15.20.2 — Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
