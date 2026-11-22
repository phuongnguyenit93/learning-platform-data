# Scope pattern variable qua block trong Java (Java 21+)

## 1. Scope không chỉ phụ thuộc dấu ngoặc nhọn

Khi gặp một **pattern variable**, nhiều người có thói quen đoán phạm vi của biến bằng cách tìm cặp dấu `{ ... }` gần nhất. Cách này chưa đủ. Trong Java, phạm vi của biến khai báo bởi pattern còn phụ thuộc **luồng điều khiển**: trình biên dịch chỉ cho phép dùng biến tại nơi nó biết chắc pattern đã **khớp**.

Xét hai ví dụ:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`text` dùng được trong thân `if`, vì nhánh này chỉ chạy khi `value` là `String` không-null. Với đoạn dưới, `text` cũng dùng được **sau khi kết thúc block `if`**:

```java
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length());
```

Lý do: nếu điều kiện phủ định đúng, phương thức đã `return`; muốn đi tới dòng in thì pattern bắt buộc phải khớp. Đây là **flow scoping** — phạm vi được suy ra từ đường đi của chương trình, không chỉ từ vị trí của dấu ngoặc.

Trong bài này ta xem pattern variable trong **statement**: `if/else`, điều kiện `&&` và `||`, `while`, nested block và các nhánh `switch`. Ta cũng phân biệt phạm vi biến được tách từ record pattern so với biến cục bộ thông thường.

**Phiên bản:** Type patterns với `instanceof` là tính năng chính thức từ Java 16; record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) ổn định từ **Java 21**. Các chương trình hoàn chỉnh bên dưới dùng JDK 21+, không cần `--enable-preview`.

## 2. Pattern variable là gì?

Pattern variable được giới thiệu cùng một **type pattern** hoặc một **record pattern**, ví dụ:

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Ở đây `String text` kiểm tra kiểu và khai báo biến `text`. Ta không phải tự viết `(String) value`, và compiler có thể xác định tại đâu `text` chắc chắn đã có giá trị.

Record pattern Java 21 cho phép tách thêm các component:

```java
record Point(int x, int y) {}

if (value instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

`x` và `y` là hai pattern variable, suy luận kiểu `int` từ khai báo `Point`. **Chúng chỉ có phạm vi khi pattern `Point(...)` thành công**, chứ không phải mọi nơi mà một biến tên `x` được nhắc tới.

### Scope, lifetime và definite matching khác nhau thế nào?

- **Scope (phạm vi tên):** các vị trí trong mã nguồn mà trình biên dịch cho phép tham chiếu tới tên biến đó.
- **Lifetime (thời gian tồn tại):** vấn đề vận hành ở runtime; không nên đồng nhất với vị trí mở/đóng dấu ngoặc trong source.
- **Definitely matched:** kết luận của trình biên dịch rằng pattern đã khớp trên đường đi đến một biểu thức hoặc statement. Flow scoping tận dụng kết luận này để xác định nơi biến được phép sử dụng.

Đừng nhầm pattern variable với field của một đối tượng, hay với biến cục bộ có thể truy cập bên ngoài nhánh chỉ vì nó được gán ở đâu đó trong chương trình.

## 3. `if`: biến chỉ dùng ở nhánh đảm bảo pattern đúng

Ví dụ cơ bản:

```java
static void inspect(Object input) {
    if (input instanceof String s) {
        System.out.println("Độ dài: " + s.length());
    } else {
        System.out.println("Không phải chuỗi");
    }
}
```

- Trong điều kiện `input instanceof String s`, `s` chỉ được ràng buộc khi pattern đúng.
- Trong block `then`, `s` ở trong scope.
- Trong block `else`, `s` **không ở trong scope** vì nhánh này chạy khi pattern sai.
- Sau toàn bộ `if/else` với hai nhánh đều có thể kết thúc bình thường, `s` **không ở trong scope**: đường đi từ nhánh `else` không bảo đảm pattern khớp.

Ví dụ **cố ý không biên dịch**:

```java
if (input instanceof String s) {
    System.out.println(s);
} else {
    System.out.println(s); // Lỗi: s không có phạm vi ở else.
}
System.out.println(s);     // Lỗi: sau if có thể đi từ nhánh false.
```

Không sửa bằng cách ép kiểu vô điều kiện, vì khi `input` không phải `String` có thể ném `ClassCastException`. Hãy đặt hành động cần biến vào nhánh thật sự biết pattern đúng, hoặc tổ chức lại luồng điều khiển.

### Hai block lồng nhau

```java
if (input instanceof String s) {
    int len = s.length();
    {
        String first = len > 0 ? s.substring(0, 1) : "(rỗng)";
        System.out.println(first);
    }
    System.out.println("Số ký tự: " + len);
    // first KHÔNG còn scope tại đây.
}
// s và len KHÔNG ở scope tại đây.
```

Ở đây `s` được đưa vào phạm vi thân `if` nhờ matching; `len` là biến cục bộ của block `if`; `first` là biến cục bộ của block lồng nhỏ hơn. Vì thế **scope của pattern variable** và **scope của biến cục bộ thông thường** có thể cùng tồn tại trong một đoạn mã nhưng được xác định bởi các quy tắc khác nhau.

## 4. `&&`: vế phải biết pattern đã khớp

Xét:

```java
if (input instanceof String s && s.length() >= 3) {
    System.out.println("Chuỗi có ít nhất 3 ký tự: " + s);
}
```

`&&` đánh giá **ngắn mạch**:
1. Kiểm tra `input instanceof String s`.
2. Nếu false, dừng; không đọc `s.length()`.
3. Nếu true, `s` chắc chắn được ràng buộc nên điều kiện thứ hai hợp lệ.
4. Nếu cả hai true, thân `if` dùng được `s`.

Bạn có thể kết hợp nhiều điều kiện:

```java
if (input instanceof String s
        && !s.isBlank()
        && s.startsWith("J")) {
    System.out.println("Chuỗi J: " + s.strip());
}
```

Có thể thêm ngoặc cho các nhóm logic mà không phá đảm bảo matching:

```java
if (input instanceof String s
        && (s.startsWith("J") || s.startsWith("K"))) {
    System.out.println(s);
}
```

Ở đây `||` **nằm sau** điều kiện `instanceof ... &&` và bên trong một nhóm chỉ được đánh giá khi `s` đã tồn tại. Điều đáng quan tâm không phải “cứ có `||` là sai”, mà là liệu vị trí dùng biến có được đảm bảo pattern đã khớp hay chưa.

### Lỗi thường gặp với `||`

Ví dụ **không biên dịch**:

```java
if (input instanceof String s || s.isEmpty()) {
    System.out.println("...");
}
```

Vế phải `s.isEmpty()` chỉ được đánh giá khi vế trái false, tức khi `s` **chưa được ràng buộc**. Compiler không chấp nhận tham chiếu ấy.

Một cách sửa là đặt điều kiện cần `s` sau `&&`. Nếu bài toán là “không phải chuỗi hoặc chuỗi rỗng”, diễn đạt tường minh:

```java
if (!(input instanceof String)) {
    System.out.println("Không phải chuỗi");
} else if (((String) input).isEmpty()) {
    System.out.println("Chuỗi rỗng");
}
```

Trong Java 21, có thể dùng sẵn pattern variable và nhánh `else` của một điều kiện phủ định (xem mục sau), tránh phải ép kiểu thủ công.

## 5. Điều kiện phủ định và early return: biến có thể đi qua ranh giới block

**Điểm dễ gây bất ngờ:** có những trường hợp pattern variable sử dụng được **sau block `if`**, nếu compiler chứng minh mọi đường đi tiếp tục đều đã khớp pattern.

```java
static String uppercase(Object input) {
    if (!(input instanceof String s)) {
        return "Không phải chuỗi";
    }
    return s.strip().toUpperCase(java.util.Locale.ROOT);
}
```

Đọc luồng:

- Nếu không phải `String`, điều kiện phủ định đúng, phương thức trả về ngay.
- Muốn tới `return s.strip()...`, điều kiện phủ định phải sai.
- Nghĩa là `input instanceof String s` **đã đúng**; vì vậy `s` có scope tại dòng thứ hai.

Đây là ví dụ điển hình của **flow scoping** qua ranh giới một block. Việc dấu `}` của `if` xuất hiện trước `return s` **không** đồng nghĩa biến `s` hết scope.

### Biến thể với `throw`

```java
static int lengthOrFail(Object input) {
    if (!(input instanceof String s)) {
        throw new IllegalArgumentException("Expected String");
    }
    return s.length();
}
```

`throw` cũng kết thúc luồng bình thường của nhánh lỗi. Nếu đến dòng cuối thì pattern chắc chắn đã khớp.

### `else` của điều kiện phủ định

```java
if (!(input instanceof String s)) {
    System.out.println("Không phải chuỗi");
} else {
    System.out.println("Độ dài: " + s.length());
}
```

Nhánh `else` chạy khi phủ định sai, nên `s` được ràng buộc. Đây là cách diễn đạt điều kiện “không phải chuỗi hoặc chuỗi rỗng” mà không ép kiểu:

```java
if (!(input instanceof String s)) {
    System.out.println("Không phải chuỗi");
} else if (s.isEmpty()) {
    System.out.println("Chuỗi rỗng");
} else {
    System.out.println("Chuỗi có nội dung");
}
```

**Chú ý:** không suy luận rằng pattern variable luôn sống qua mọi `if` phủ định. Nếu nhánh sai của phép matching vẫn có thể **tiếp tục bình thường** sau block, compiler không thể bảo đảm biến được ràng buộc. Chính `return`/`throw` hoặc cấu trúc nhánh rõ ràng mới làm việc này trở nên an toàn.

## 6. Pattern variable trong `while` statement

Điều kiện `while` được đánh giá lại trước mỗi lượt lặp. Pattern variable có scope trong thân `while` khi phép matching ở điều kiện là true.

```java
static int countCharacters(Object input) {
    int count = 0;
    while (input instanceof String s && !s.isEmpty()) {
        count++;
        input = s.substring(1);
    }
    return count;
}
```

Giải thích:
- Nếu `input` không phải chuỗi, không vào vòng lặp.
- Nếu là chuỗi không rỗng, `s` đã tồn tại trong thân loop.
- Sau mỗi lượt, `input` được thay bằng chuỗi bỏ ký tự đầu; vòng lặp kiểm tra lại pattern ở vòng tiếp theo.
- Khi chuỗi rỗng, guard sai và vòng lặp kết thúc. **`s` không có scope ở câu lệnh sau vòng `while`** trong ví dụ này.

Ví dụ `countCharacters("abc")` trả về `3`, `countCharacters("")` và `countCharacters(42)` đều trả về `0`.

```java
// Cố ý KHÔNG biên dịch nếu đặt ngay sau while ở trên:
System.out.println(s); // s không ở scope sau vòng lặp.
```

Không nhầm giữa biến `input` đã tồn tại ngoài vòng lặp với `s` được giới thiệu mới trong điều kiện. Đầu vào có thể được gán lại, nhưng điều đó không mở rộng scope của `s`.

Với vòng lặp thực tế, chú ý tránh `while` vô hạn: nếu điều kiện pattern luôn true và thân không thay đổi trạng thái liên quan, vòng lặp có thể không bao giờ kết thúc. Đây là lỗi thuật toán, không phải lỗi scope.

## 7. Pattern variables trong `switch` statement và các block `case`

Với pattern matching `switch`, pattern variable của một nhánh có scope trong **guard `when` và phần thân của nhánh đó**. Cách viết `case ... -> { ... }` giúp phạm vi rõ ràng và tránh fall-through:

```java
record Point(int x, int y) {}

static void print(Object input) {
    switch (input) {
        case null -> System.out.println("null");
        case Point(var x, var y) when x == 0 && y == 0 -> {
            String label = "gốc tọa độ";
            System.out.println(label);
        }
        case Point(var x, var y) -> {
            int sum = x + y;
            System.out.println("Tổng tọa độ: " + sum);
        }
        case String s -> {
            System.out.println("Chuỗi: " + s);
        }
        default -> System.out.println("Kiểu khác");
    }
}
```

**Cách đọc phạm vi:**
- Ở `case Point(var x, var y) when ...`, `x`, `y` đã được ràng buộc sau matching nên dùng trong guard.
- Trong block bên phải `->`, `x`, `y` dùng được. Biến `label` chỉ tồn tại trong block của nhánh đầu.
- Ở nhánh `case Point(var x, var y)` kế tiếp, đó là **hai pattern variable khác**, dù trùng tên `x`, `y`; không chuyển giá trị từ nhánh trước.
- `s` của `case String s` chỉ liên quan nhánh chuỗi; không được gọi ở nhánh `Point` hay sau `switch`.
- Khi selector là `null`, `case null` xử lý riêng. Không dựa vào `default` để tự động nhận null trong enhanced switch.

**Không có fall-through** ở các nhánh dùng `->`. Cú pháp `case ... :` vẫn thuộc `switch` statement, nhưng với pattern variables phải đặc biệt chú ý các quy tắc về phạm vi và cấm đi xuyên vào một nhánh có pattern chưa khớp; dùng `->` thường dễ review hơn.

### Điều kiện `when` không mở rộng scope ra ngoài nhánh

```java
case String s when s.length() > 5 -> {
    System.out.println("Chuỗi dài: " + s);
}
```

`s` dùng được trong guard và block vì chỉ được xem xét sau matching. Nhưng `s` không tồn tại trong `default` hoặc câu lệnh phía sau `switch`.

**Thứ tự nhánh:** đặt pattern có guard cụ thể ở trước pattern tổng quát. Đoạn sau **không biên dịch** vì dominance:

```java
switch (input) {
    case String s -> System.out.println("Mọi chuỗi");
    case String s when s.length() > 5 ->
        System.out.println("Chuỗi dài"); // dominated
    default -> System.out.println("Khác");
}
```

Mẫu `case String s` đầu tiên đã nhận mọi chuỗi không-null, khiến nhánh sau không thể tới. Đổi thứ tự hai nhánh để bảo đảm xử lý ưu tiên hợp lý. Đây là quy tắc **khả năng tới nhánh**, tách biệt với khái niệm scope nhưng thường cùng xuất hiện khi tổ chức nhiều block `case`.

## 8. Record patterns lồng nhau và scope của biến ở lá

Trong Java 21, record pattern có thể lồng nhau:

```java
record Point(int x, int y) {}
record Route(String name, Point start, Point end) {}

if (input instanceof Route(
        var name,
        Point(var x1, var y1),
        Point(var x2, var y2))) {
    System.out.println(name + ": (" + x1 + ", " + y1
        + ") -> (" + x2 + ", " + y2 + ")");
}
```

Dòng `println` chỉ được thực thi khi **Route, start và end** cùng khớp các record patterns. Nếu `start == null` hoặc `end == null`, một trong hai `Point(...)` không khớp; thân `if` không chạy. Các biến `x1, y1, x2, y2` vì vậy không thể dùng ở đường đi mà nested pattern thất bại.

Đôi khi ta cần giữ nguyên component thay vì yêu cầu nó là record không-null:

```java
if (input instanceof Route(var name, var start, var end)) {
    System.out.println("Có Route: " + name);
    if (start == null || end == null) {
        System.out.println("Thiếu điểm đầu hoặc cuối");
    }
}
```

Ở đây `start` và `end` được lấy từ component bằng `var`; một component tham chiếu null vẫn có thể được ràng buộc bởi pattern vô điều kiện tương ứng. Trong block `if`, chúng đã có scope để dùng trong kiểm tra null. **Scope** và **giá trị có thể null** là hai chuyện khác nhau: một biến đang ở trong scope vẫn có thể chứa null.

Nếu cần truy cập `start.x()`, phải đảm bảo `start != null` bằng guard hoặc điều kiện. Biến “tồn tại” về mặt scope không có nghĩa mọi phép gọi phương thức trên nó đều an toàn.

## 9. Ví dụ Java 21 hoàn chỉnh: `if`, early return, `while` và `switch`

Tạo tệp **`PatternVariableBlockScopeDemo.java`**:

```java
public class PatternVariableBlockScopeDemo {
    record Point(int x, int y) {}
    record Box(Point point, String label) {}

    static void readIf(Object value) {
        if (value instanceof String s && s.length() >= 3) {
            int len = s.length();
            System.out.println("if: " + s + " (" + len + ")");
        } else {
            System.out.println("if: không khớp");
        }
    }

    static String normalize(Object value) {
        if (!(value instanceof String text)) {
            return "không phải chuỗi";
        }
        // Chỉ còn nhánh đã khớp String nên text vẫn ở scope.
        return text.strip().toUpperCase(java.util.Locale.ROOT);
    }

    static int countCharacters(Object value) {
        int count = 0;
        while (value instanceof String s && !s.isEmpty()) {
            count++;
            value = s.substring(1);
        }
        return count;
    }

    static void readSwitch(Object value) {
        switch (value) {
            case null -> System.out.println("switch: null");

            case Point(var x, var y) when x == 0 && y == 0 -> {
                String kind = "gốc";
                System.out.println("switch: " + kind);
            }

            case Point(var x, var y) -> {
                int sum = x + y;
                System.out.println("switch: điểm (" + x + "," + y
                        + "), tổng=" + sum);
            }

            case Box(Point(var x, var y), var label)
                    when label != null && !label.isBlank() -> {
                System.out.println("switch: hộp " + label
                        + " tại (" + x + "," + y + ")");
            }

            case Box b ->
                System.out.println("switch: hộp thiếu dữ liệu");

            case String s -> {
                String trimmed = s.strip();
                System.out.println("switch: chuỗi '" + trimmed + "'");
            }

            default -> System.out.println("switch: kiểu khác");
        }
    }

    public static void main(String[] args) {
        readIf("Java");
        readIf("Hi");
        System.out.println("guard: " + normalize("  java  "));
        System.out.println("guard: " + normalize(42));

        readSwitch(new Point(0, 0));
        readSwitch(new Point(2, 5));
        readSwitch(new Box(new Point(1, 3), "A"));
        readSwitch(new Box(null, "A"));
        readSwitch("  ok  ");
        readSwitch(null);
        readSwitch(10);

        System.out.println("while: " + countCharacters("abc"));
    }
}
```

Biên dịch và chạy bằng JDK 21 hoặc mới hơn từ thư mục chứa tệp:

```bash
javac --release 21 -encoding UTF-8 PatternVariableBlockScopeDemo.java
java PatternVariableBlockScopeDemo
```

Đầu ra:

```text
if: Java (4)
if: không khớp
guard: JAVA
guard: không phải chuỗi
switch: gốc
switch: điểm (2,5), tổng=7
switch: hộp A tại (1,3)
switch: hộp thiếu dữ liệu
switch: chuỗi 'ok'
switch: null
switch: kiểu khác
while: 3
```

### Phân tích scope theo kết quả

- **Hai lệnh `readIf`:** ở `"Java"`, pattern khớp và `len` được khai báo trong block `then`; ở `"Hi"`, mẫu `String s` khớp nhưng `s.length() >= 3` sai nên vào `else`. `s` không được sử dụng ở `else`.
- **Hai lệnh `normalize`:** nhánh phủ định `return` sớm. Chỉ đầu vào chuỗi mới đi tới dòng sử dụng `text` sau block `if`.
- **`Point(0,0)`:** nhánh có guard sử dụng `x` và `y` của chính nhánh đó; biến `kind` tồn tại trong block `case` đầu.
- **`Point(2,5)`:** guard đầu sai, nhánh `Point(var x, var y)` tiếp theo tạo bộ biến pattern **riêng**, tính `sum = 7` trong block tương ứng.
- **`Box(Point(1,3),"A")`:** pattern lồng tách `x`, `y` và `label`; guard yêu cầu nhãn không-null, không trống.
- **`Box(null,"A")`:** record pattern lồng `Point(...)` không khớp; nhánh `case Box b` nhận Box còn lại, cho thấy việc loại một nhánh không làm rò rỉ biến `x`/`y` sang nhánh dự phòng.
- **`String`, `null` và số nguyên:** mỗi kiểu được xử lý bởi case phù hợp hoặc `default`; biến `trimmed` chỉ nằm trong block chuỗi.
- **Vòng `while`:** `s` được ràng buộc lại theo giá trị của `value` ở mỗi lần kiểm tra điều kiện, và chỉ được dùng trong loop khi pattern đúng.

Kết quả minh họa cách **dấu ngoặc tạo block thông thường**, còn **sự thành công của pattern cùng luồng điều khiển** quyết định vị trí pattern variable có thể dùng.

## 10. Bảng tra nhanh phạm vi biến

| Cấu trúc | Biến pattern dùng ở đâu? | Không dùng ở đâu? |
| --- | --- | --- |
| `if (obj instanceof String s) { ... }` | Thân `then` | `else` thông thường; sau một `if` mà đường false còn đi tiếp |
| `if (obj instanceof String s && s.length()>0)` | Vế phải `&&`, thân `then` khi điều kiện đúng | Vế phải `||` thay cho `&&` trong điều kiện tương tự |
| `if (!(obj instanceof String s)) return;` | Phần code phía sau `if` trong cùng luồng khi nhánh lỗi đã kết thúc | Thân nhánh phủ định (nơi pattern không khớp) |
| `if (!(obj instanceof String s)) { ... } else { ... }` | Block `else` | Block `then` của điều kiện phủ định |
| `while (obj instanceof String s && ...) { ... }` | Vế phải `&&` và thân vòng lặp | Sau vòng lặp trong ví dụ thông thường |
| `case String s when ... -> { ... }` | Guard `when` và block của đúng `case` | Các `case` khác và sau `switch` |
| `case Route(..., Point(var x, var y)) -> ...` | Nhánh/guard sau khi mọi pattern lồng khớp | Những đường đi mà `Point(...)` không khớp |

**Điểm cốt lõi:** phạm vi một biến pattern không được quyết định bằng một dấu `}` duy nhất. Hãy hỏi: **“Có tồn tại đường đi nào đến dòng này mà pattern chưa khớp không?”** Nếu có, compiler thường không cho dùng biến ở dòng đó.

## 11. Những lỗi compile và cách sửa

### Lỗi 1: dùng pattern variable bên ngoài nhánh không bảo đảm khớp

```java
if (value instanceof String s) {
    System.out.println(s.length());
}
System.out.println(s); // SAI: value có thể không phải String.
```

Sửa bằng cách đặt thao tác cần `s` trong thân `if`; hoặc dùng phủ định + `return`/`throw` nếu cần xử lý thành công ở cuối phương thức.

### Lỗi 2: đọc biến ở `else` của matching dương

```java
if (value instanceof String s) {
    System.out.println(s);
} else {
    System.out.println(s); // SAI: chưa có String s.
}
```

Nếu yêu cầu là mô tả đầu vào không phù hợp, dùng chính `value` hoặc thông báo lỗi trong `else`. Nếu muốn dùng `s` ở nhánh `else`, hãy cân nhắc đổi sang dạng phủ định như mục 5.

### Lỗi 3: dùng `||` khi pattern chưa chắc khớp

```java
if (value instanceof String s || s.length() > 3) { // SAI
    // ...
}
```

Sửa với `&&` khi logic muốn nối điều kiện bổ sung **sau khi matching thành công**. `||` chỉ an toàn với tham chiếu `s` khi toàn bộ cấu trúc biểu thức bảo đảm `s` đã ràng buộc trước đó.

### Lỗi 4: dùng biến của `case` khác

```java
switch (value) {
    case String s -> System.out.println(s.length());
    case Integer n -> System.out.println(s); // SAI: s không thuộc nhánh này.
    default -> System.out.println("other");
}
```

Dùng `n` trong nhánh `Integer` hoặc một biến khai báo ở phạm vi ngoài nếu thực sự cần dữ liệu dùng chung. Không cố gắng chia sẻ pattern variables giữa các `case`.

### Lỗi 5: nhầm scope với null-safety

```java
record Message(String text) {}
if (value instanceof Message(var text)) {
    System.out.println(text.length()); // Có thể NPE nếu text null.
}
```

`text` **đang ở trong scope**, nhưng component `Message.text` có thể null. Sửa bằng `text != null` trước khi gọi phương thức hoặc xác thực ngay khi tạo record. Scope hợp lệ không bảo đảm nội dung luôn khác null.

### Lỗi 6: redeclare tên trong block đang có pattern variable

```java
if (value instanceof String s) {
    String s = "new"; // SAI: trùng tên biến đang trong scope.
}
```

Chọn tên khác hoặc giữ một tên duy nhất. Các biến độc lập giữa những block/`case` thật sự không chồng lấn phạm vi có thể được đặt lại tên, nhưng không nên lạm dụng trùng tên đến mức khó đọc.

### Lỗi 7: biến cục bộ trong block con bị dùng ở block cha

```java
if (value instanceof String s) {
    {
        int size = s.length();
        System.out.println(size);
    }
    System.out.println(size); // SAI: size chỉ có scope trong block con.
}
```

Đây là lỗi phạm vi **biến cục bộ thông thường**, không phải quy tắc đặc biệt của pattern variable. Cách sửa là đưa khai báo `size` ra block ngoài nếu cần sử dụng ở cả hai chỗ.

## 12. Phương pháp đọc và review phạm vi biến

Khi review một đoạn code chứa pattern, có thể đi theo quy trình:

1. **Tìm chỗ khai báo pattern variable**: `String s`, `Point(var x, var y)`, `case Box b`, v.v.
2. **Xác định điều kiện pattern khớp**: đầu vào phải mang kiểu nào; với nested record pattern, từng record con nào phải không-null?
3. **Liệt kê các nhánh luồng điều khiển**: `then`, `else`, vế phải `&&`/`||`, vòng `while`, guard và thân từng `case`.
4. **Đối với dòng sử dụng biến, hỏi có thể tới đây nếu pattern false không**. Nếu không thể, phạm vi có thể hợp lệ; nếu có thể, cần bố trí lại.
5. **Xem xét block cục bộ**: biến do `int len`, `String first`... khai báo theo phạm vi từ dấu ngoặc của chính block; không tự mở rộng ra ngoài.
6. **Kiểm tra null riêng**: một biến pattern hợp lệ có thể giữ component tham chiếu null; đừng đồng nhất `scope` với an toàn khi gọi phương thức.
7. **Xem thứ tự `switch case` và sự bao phủ**: không đặt case tổng quát che case có guard; thêm `case null`/`default` đúng chính sách.

Tổ chức code nên làm nổi bật đường đi hợp lệ. Một câu lệnh phủ định kèm `return` rõ ràng có thể giúp phần “happy path” ít lồng hơn; tuy nhiên không nên biến mỗi condition thành hàng loạt phủ định phức tạp. Với `switch`, dùng nhánh `-> { ... }` đủ ngắn giúp người đọc thấy ngay biến nào thuộc nhánh nào.

## 13. Bài tập có đáp án gợi ý

**Bài 1.** Đoạn nào hợp lệ? Vì sao?

```java
// A
if (obj instanceof String s && s.length() > 2) {
    System.out.println(s);
}

// B: KHÔNG hợp lệ
if (obj instanceof String s || s.length() > 2) {
    System.out.println(s);
}
```

Đáp án: **A**. Vế phải `&&` chỉ được đánh giá nếu `instanceof` true, nên `s` đã có giá trị. Ở B, vế phải `||` được đánh giá khi `instanceof` false, nên `s` chưa chắc tồn tại.

**Bài 2.** Vì sao dòng cuối hợp lệ?

```java
if (!(obj instanceof String s)) {
    throw new IllegalArgumentException("not a string");
}
System.out.println(s);
```

Đáp án: nếu code đi tới dòng cuối, nhánh thất bại đã không đi tiếp; compiler có thể kết luận pattern `String s` chắc chắn khớp.

**Bài 3.** Sửa lỗi ở `else`:

```java
if (obj instanceof Integer n) {
    System.out.println(n + 1);
} else {
    System.out.println(n); // sai
}
```

Gợi ý: trong `else` chỉ in thông báo `"Không phải Integer"` hoặc dữ liệu `obj`, vì `n` không tồn tại ở nhánh thất bại.

**Bài 4.** Với `record Box(Point point, String label) {}`, nếu `new Box(null, "A")` được đưa vào `switch` ở ví dụ hoàn chỉnh, nhánh nào chạy? Đáp án: `case Box b`, vì nested `Point(var x, var y)` không khớp null.

**Bài 5.** Mở rộng `readSwitch`: thêm nhánh `case String s when s.isBlank() -> ...` trước nhánh `case String s -> ...`. Dự đoán output cho chuỗi chỉ gồm khoảng trắng. Giải thích vì sao nhánh có guard phải xuất hiện trước nhánh String tổng quát.

**Bài 6.** Đặt câu lệnh `System.out.println(s);` sau vòng `while` trong `countCharacters`. Nó có hợp lệ không? Đáp án: **không**, bởi đường đi thoát loop không đảm bảo pattern còn khớp và `s` không còn scope ở đó.

## 14. Ghi nhớ và tài liệu tham khảo

- **Block scope** của biến cục bộ thông thường và **flow scoping** của pattern variable đều ảnh hưởng nơi một tên biến được phép xuất hiện.
- `if (x instanceof T v)` cho dùng `v` ở nhánh thành công.
- `&&` cho phép dùng biến pattern ở điều kiện sau nhờ short-circuit; `||` không tự bảo đảm điều tương tự.
- `if (!(x instanceof T v)) return;` là mẫu quan trọng: biến `v` còn scope **sau block `if`** trên đường đi hợp lệ.
- Trong `while`, pattern variable dùng được khi điều kiện hiện tại đã khớp; không mặc nhiên tồn tại sau vòng lặp.
- Trong `switch` statement dùng `case ... -> { ... }`, biến pattern và guard thuộc **đúng nhánh đó**. Nested record patterns thêm biến ở lá nhưng không làm chúng tồn tại ở các nhánh không khớp.
- **Biến trong scope vẫn có thể chứa null** nếu nó nhận một component tham chiếu nullable.

Nguồn chính thức:
- [Oracle Java 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 — Scope of a Declaration (`6.3)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
