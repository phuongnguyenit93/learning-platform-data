# Pattern trong `for` statement của Java

## 1. Pattern matching xuất hiện ở đâu trong vòng lặp `for`?

Trong Java, **pattern** mô tả một phép kiểm tra cấu trúc/kiểu và có thể tạo *pattern variable* khi matching thành công. Với vòng lặp `for`, phải phân biệt hai loại cú pháp:

```java
// Basic for: ba phần init, condition, update
for (int i = 0; condition; i++) {
    // body
}

// Enhanced for: duyệt từng phần tử
for (Object item : items) {
    // body
}
```

Ở **basic `for`**, biểu thức điều kiện có thể chứa `instanceof` kết hợp type pattern hoặc record pattern. Khi biểu thức điều kiện khớp và trả `true`, pattern variable được dùng **trong thân vòng lặp và trong phần `ForUpdate`**, theo quy tắc *flow scoping* của Java (§6.3.2.5).

Ở **enhanced `for`**, phần `Object item` trong header là **khai báo biến lặp thông thường**, không phải pattern. Có thể đặt `instanceof`, record pattern, hoặc `switch` có `case` pattern **bên trong thân vòng lặp** để xử lý mỗi phần tử.

Một điểm dễ nhầm về phiên bản: Java 20 từng preview record pattern trực tiếp trong header enhanced `for`; **Java 21 đã bỏ cú pháp đó** khi record patterns trở thành tính năng chính thức. Vì vậy, `for (Point(var x, var y) : points)` **không hợp lệ trong Java 21**. Các ví dụ hoàn chỉnh trong bài dùng JDK 21 trở lên và không cần bật preview.

## 2. Basic `for`: pattern ở biểu thức điều kiện

Ví dụ ngắn:

```java
Object[] values = {"ab", "c", 42, "z"};

for (int i = 0;
     i < values.length && values[i] instanceof String word;
     i++) {
    System.out.println(word.toUpperCase());
}
```

Phân tích thứ tự:

1. `int i = 0` chạy một lần khi bắt đầu vòng lặp.
2. Java kiểm tra `i < values.length`. Nếu sai, điều kiện kết thúc ngay nhờ `&&`.
3. Khi còn phần tử, Java kiểm tra `values[i] instanceof String word`. Nếu là `String`, pattern variable `word` được ràng buộc.
4. **Chỉ khi toàn bộ điều kiện `true`**, thân vòng lặp được chạy và có thể dùng `word` mà không cần cast.
5. Sau thân vòng lặp, `i++` chạy và Java đánh giá lại điều kiện.

Điểm khác biệt quan trọng so với việc đặt `if` trong body: **pattern không khớp ở điều kiện sẽ kết thúc cả vòng lặp**. Với mảng trên, vòng lặp xử lý `"ab"` và `"c"`, rồi dừng tại số `42`; nó **không tự bỏ qua** `42` để đến `"z"`.

Với `null`, biểu thức `value instanceof String word` trả `false`, do đó vòng lặp cũng kết thúc nếu kiểm tra kiểu nằm trong điều kiện.

## 3. Ví dụ đầy đủ: pattern variable dùng cả ở body và `ForUpdate`

Quy tắc ít được chú ý là biến pattern sinh từ điều kiện khi `true` nằm trong phạm vi **của cả phần cập nhật**. `ForUpdate` có thể gồm nhiều *statement expression*, chẳng hạn lời gọi phương thức và phép tăng chỉ số, phân cách bằng dấu phẩy.

Lưu vào `ForConditionDemo.java`:

```java
public class ForConditionDemo {
    public static void main(String[] args) {
        Object[] items = {"ab", "c", 42, "z"};

        for (int i = 0;
             i < items.length && items[i] instanceof String word;
             System.out.println("length=" + word.length()), i++) {

            System.out.println("body=" + word);
        }

        System.out.println("stopped");
    }
}
```

Chạy bằng JDK 21 trở lên:

```bash
javac --release 21 ForConditionDemo.java
java ForConditionDemo
```

Kết quả:

```text
body=ab
length=2
body=c
length=1
stopped
```

`word` hiện diện hợp lệ trong `System.out.println("body=" + word)` **và** `System.out.println("length=" + word.length())` của phần cập nhật. Phần cập nhật chạy **sau** body của mỗi lượt, giải thích thứ tự các dòng output.

Ở lượt kiểm tra phần tử `42`, type pattern không khớp; body và `ForUpdate` của lượt đó **không được chạy**. Mệnh đề `i < items.length` bảo đảm không truy cập ngoài giới hạn trước khi thử `instanceof`.

Đây là ví dụ trực tiếp cho quy tắc JLS 21 §6.3.2.5: *pattern variable introduced by the condition when true* được definitely matched tại `ForUpdate` và contained statement.

## 4. Khi muốn bỏ qua phần tử không khớp, đặt pattern trong body

Nhiều tác vụ thực tế là duyệt một collection chứa nhiều kiểu dữ liệu, chỉ xử lý những phần tử thuộc kiểu cần tìm. Với yêu cầu này, cách thường rõ ràng hơn là dùng enhanced `for` rồi kiểm tra pattern bằng `if`:

```java
for (Object item : items) {
    if (item instanceof String word) {
        System.out.println(word);
    }
}
```

Ở đây, `item` là **biến lặp**, còn `word` là **pattern variable**. Nếu `item` không khớp, chỉ nhánh `if` bị bỏ qua; enhanced `for` vẫn chuyển sang phần tử kế tiếp.

Một kiểu viết hữu ích hơn nữa là **guard clause** bằng `continue`.

Lưu vào `ForSkipDemo.java`:

```java
import java.util.Locale;

public class ForSkipDemo {
    public static void main(String[] args) {
        Object[] values = {"alpha", 42, null, "beta"};

        for (Object value : values) {
            if (!(value instanceof String word)) {
                continue;
            }

            System.out.println("word="
                    + word.toUpperCase(Locale.ROOT));
        }
    }
}
```

```bash
javac --release 21 ForSkipDemo.java
java ForSkipDemo
```

Kết quả:

```text
word=ALPHA
word=BETA
```

Điều kiện `!(value instanceof String word)` là `true` khi phần tử không phải `String`; `continue` chuyển sang phần tử kế tiếp. Để đi đến `System.out.println(...)` phía sau, Java biết rằng nhánh `continue` không được đi vào, tức matching phải thành công. Vì vậy, `word` nằm trong phạm vi hợp lệ ở dòng in.

Đây là hiệu ứng **flow scoping**, không phải việc biến `word` tồn tại vô điều kiện. `null` không khớp type pattern `String word`, nên cũng được bỏ qua an toàn.

## 5. Record pattern trong enhanced `for` — cách hợp lệ ở Java 21

Record pattern hỗ trợ giải cấu trúc component của record. Trong vòng lặp enhanced `for`, Java 21 cho phép dùng nó ở biểu thức `instanceof` **bên trong body**.

Lưu vào `ForRecordDemo.java`:

```java
public class ForRecordDemo {
    record Point(int x, int y) {}

    public static void main(String[] args) {
        Object[] values = {
            new Point(2, 5),
            "skip",
            new Point(3, 4)
        };

        for (Object value : values) {
            if (value instanceof Point(var x, var y)) {
                System.out.println("Point sum=" + (x + y));
            }
        }
    }
}
```

```bash
javac --release 21 ForRecordDemo.java
java ForRecordDemo
```

Kết quả:

```text
Point sum=7
Point sum=7
```

Ở các lượt có `Point`, record pattern `Point(var x, var y)` kiểm tra record, lấy component thông qua accessor tương ứng và ràng buộc `x`, `y` (ở đây đều suy luận thành `int`). Với chuỗi `"skip"`, matching thất bại, nhưng **vòng lặp vẫn tiếp tục**.

Nếu đầu vào có `null`, record pattern cũng không khớp `null`; kết quả `instanceof` là `false`.

Một cách dùng record pattern trong điều kiện basic `for` cũng hợp lệ:

```java
for (int i = 0;
     i < values.length
         && values[i] instanceof Point(var x, var y);
     i++) {
    System.out.println(x + y);
}
```

**Khác biệt về hành vi:** vòng lặp basic `for` trên sẽ dừng ngay khi gặp phần tử đầu tiên không phải `Point`. Nó phù hợp khi danh sách cần được xử lý là một **đoạn liên tiếp** gồm những phần tử khớp ở đầu; còn với tập dữ liệu pha trộn cần duyệt hết, nên dùng `if` trong body.

## 6. Cú pháp không hợp lệ: record pattern ngay trong enhanced `for` header

Dù nhìn giống giải cấu trúc từng phần tử, **đoạn sau không biên dịch với Java 21**:

```java
record Point(int x, int y) {}

void print(Point[] points) {
    // Sai cú pháp trong Java 21:
    for (Point(var x, var y) : points) {
        System.out.println(x + y);
    }
}
```

`Point(var x, var y)` là record pattern, nhưng vị trí khai báo biến ở đầu enhanced `for` của Java 21 không nhận record pattern. Đó là khác biệt giữa **cú pháp preview của Java 20** và **cú pháp cuối cùng của Java 21**.

Cách viết đúng trong Java 21:

```java
void print(Point[] points) {
    for (Point point : points) {
        if (point instanceof Point(var x, var y)) {
            System.out.println(x + y);
        }
    }
}
```

Đoạn này là **minh họa trong một lớp/phạm vi đã khai báo record `Point`**; không phải một tệp Java độc lập. Nếu mảng chỉ chứa các đối tượng `Point` hợp lệ, cách đơn giản nhất thường là dùng accessor trực tiếp `point.x()` và `point.y()`. Dùng record pattern khi nó giúp diễn đạt kiểm tra kiểu/giải cấu trúc hoặc dùng cùng logic xử lý nhiều kiểu dữ liệu.

Nếu `point` có thể là `null`, `instanceof Point(...)` trả `false`, trong khi gọi `point.x()` trực tiếp sẽ ném `NullPointerException`.

## 7. Phạm vi biến: không phải mọi vị trí trong `for` đều nhìn thấy pattern variable

Với basic `for`:

```java
for (int i = 0;
     i < values.length && values[i] instanceof String word;
     i++) {
    System.out.println(word.length()); // Hợp lệ.
}
```

`word` được giới thiệu khi điều kiện đúng, nên compiler cho phép sử dụng trong body và `ForUpdate`. Nó **không mặc nhiên tồn tại trong phần `ForInit`** (vốn chạy trước khi điều kiện matching), và **không mặc nhiên tồn tại ở mã sau vòng lặp**. Sau khi vòng lặp kết thúc, điều kiện có thể sai do hết phần tử hoặc do pattern thất bại.

Với enhanced `for`, phạm vi của pattern variable được kiểm soát theo nơi pattern xuất hiện:

```java
for (Object item : values) {
    if (item instanceof String word) {
        System.out.println(word);
    }
    // Không được giả định `word` luôn đã khớp ở đây.
}
```

Một cách khác là đặt điều kiện phụ bằng `&&`, vốn chỉ kiểm tra vế phải khi matching thành công:

```java
for (Object item : values) {
    if (item instanceof String word && !word.isBlank()) {
        System.out.println(word.trim());
    }
}
```

Tại `!word.isBlank()`, `word` đã được xác định là `String`. Đây là tổ hợp quen thuộc giữa pattern matching và short-circuit evaluation.

## 8. Trường hợp nâng cao: pattern variable có thể ở sau basic `for`

JLS 21 còn quy định một trường hợp ít gặp nhưng hợp lệ: **nếu điều kiện `for` trở thành `false` chính khi một pattern được xác nhận khớp**, và thân vòng lặp **không có `break` nhắm tới vòng lặp đó**, pattern variable có thể được đưa vào phạm vi sau vòng lặp.

Ví dụ dùng biểu thức phủ định `!(... instanceof String result)` để tìm chuỗi đầu tiên:

Lưu vào `ForFindDemo.java`:

```java
import java.util.Locale;

public class ForFindDemo {
    public static void main(String[] args) {
        Object[] values = {1, 2, "done"};
        int index = 0;
        Object current = values[index];

        for (;
             !(current instanceof String result);
             current = values[++index]) {
            // Tiếp tục cho đến khi current khớp String.
        }

        System.out.println("found="
                + result.toUpperCase(Locale.ROOT));
    }
}
```

```bash
javac --release 21 ForFindDemo.java
java ForFindDemo
```

Kết quả:

```text
found=DONE
```

`for` chỉ kết thúc bình thường khi `!(current instanceof String result)` bằng `false`, nghĩa là `current` **đã khớp** `String result`. Do đó `result` hợp lệ ở câu lệnh phía sau vòng lặp.

**Điều kiện tiên quyết của ví dụ:** ta biết chắc mảng chứa `"done"` trước khi vượt giới hạn. Nếu không có phần tử khớp, phần cập nhật `values[++index]` có thể ném `ArrayIndexOutOfBoundsException`. Đoạn mã này nhằm minh họa chính xác quy tắc phạm vi của ngôn ngữ; khi viết chương trình thực tế, cách an toàn thường là dùng vòng lặp có kiểm tra chỉ số và biến kết quả tường minh.

Thêm `break` nhắm tới vòng lặp, hoặc ghép điều kiện khiến vòng lặp cũng có thể dừng vì một nguyên nhân khác, có thể làm compiler **không còn bảo đảm** rằng pattern đã khớp khi ra khỏi vòng lặp. Không áp dụng máy móc quy tắc `result` sau `for` cho mọi câu lệnh lặp.

## 9. Dùng `switch` pattern trong thân vòng lặp

`for` cũng thường kết hợp với **pattern matching for `switch`** (chuẩn hóa ở Java 21). `switch` ở đây là một statement/expression **bên trong body**, chứ không thay thế cú pháp header của `for`.

Lưu vào `ForSwitchDemo.java`:

```java
public class ForSwitchDemo {
    public static void main(String[] args) {
        Object[] values = {"hi", 2, null, 3.5};

        for (Object value : values) {
            String description = switch (value) {
                case String text -> "S:" + text;
                case Integer number -> "I:" + number;
                case null -> "NULL";
                default -> "OTHER";
            };

            System.out.println(description);
        }
    }
}
```

```bash
javac --release 21 ForSwitchDemo.java
java ForSwitchDemo
```

Kết quả:

```text
S:hi
I:2
NULL
OTHER
```

Đây là cách đọc dễ hiểu khi cần phân loại mỗi phần tử theo nhiều kiểu. `case null` xử lý giá trị `null` chủ động; pattern variable `text` hoặc `number` chỉ dùng được ở nhánh `case` tương ứng.

## 10. Chọn cấu trúc nào trong tình huống thực tế?

| Mục tiêu | Cách viết phù hợp | Điểm cần chú ý |
| --- | --- | --- |
| Xử lý đoạn liên tiếp gồm các phần tử khớp từ đầu danh sách | Basic `for` với `instanceof` ở condition | Dừng ngay ở phần tử đầu tiên không khớp |
| Quét toàn bộ danh sách pha nhiều kiểu | Enhanced `for` + `if (item instanceof T t)` | Phần tử không khớp được bỏ qua |
| Quét danh sách record và giải cấu trúc component | Enhanced `for` + record pattern trong body | Java 21 không nhận record pattern ở enhanced-for header |
| Phân loại nhiều kiểu trong mỗi lượt lặp | Enhanced `for` + `switch` pattern | Chú ý `null`, `default`, phạm vi mỗi `case` |
| Cần dùng pattern variable cả trong cập nhật của basic `for` | Pattern ở condition của basic `for` | Biến chỉ chắc chắn khớp khi điều kiện đúng |
| Tìm đến phần tử đầu tiên phù hợp | Vòng lặp có điều kiện kiểm tra pattern hoặc duyệt rồi `break` | Duy trì kiểm tra bounds và kết quả khi không tìm thấy |

Nếu chỉ cần xử lý chuỗi đã biết là `String`, việc thêm `instanceof String s` không làm code tốt hơn. Pattern hữu ích khi đầu vào có kiểu tổng quát (`Object`, interface hoặc kiểu cha) hoặc cần giải cấu trúc record có nhiều component.

## 11. Những lỗi phổ biến

1. **Đọc nhầm cú pháp preview:** `for (Point(var x, var y) : points)` xuất hiện trong một số tài liệu Java 20 preview, nhưng đã bị loại khỏi Java 21.
2. **Tưởng `instanceof` trong điều kiện là bộ lọc bỏ qua phần tử:** với basic `for`, condition `false` **kết thúc vòng lặp**. Muốn bỏ qua thì dùng `if`/`continue` trong body.
3. **Dùng pattern variable khi chưa chắc matching thành công:** compiler chỉ cho phép ở nơi flow scoping bảo đảm đã được ràng buộc.
4. **Dùng biến pattern ngay ở `ForInit`:** biến đến từ điều kiện chưa tồn tại trước khi điều kiện được đánh giá.
5. **Cho rằng biến pattern luôn tồn tại sau `for`:** chỉ các trường hợp flow scoping đặc biệt mới đủ điều kiện, như ví dụ phủ định và vòng lặp không có `break`.
6. **Quên kiểm tra chỉ số mảng trước `items[i]`:** đặt `i < items.length` trước `&&` để bảo vệ truy cập, đặc biệt với đầu vào rỗng.
7. **Nhầm `null` với match thành công:** `null instanceof String word` và `null instanceof Point(var x, var y)` đều `false`. Trong `switch`, cân nhắc `case null`.
8. **Cho rằng enhanced `for (String value : strings)` là type pattern:** đây là cú pháp khai báo biến lặp chuẩn; `String value` không có phép kiểm tra `instanceof` của pattern matching.
9. **Bỏ qua tính toán của `ForUpdate`:** phần cập nhật chạy sau body (bao gồm đường đi `continue` đối với basic `for`) và chỉ khi vòng lặp thực hiện lượt tiếp theo; nó không chạy khi condition ban đầu `false`.
10. **Dùng record pattern trên JDK 17 rồi ngạc nhiên vì lỗi:** type pattern của `instanceof` đã ổn định trước đó, còn **record patterns** trở thành chính thức từ Java 21.

## 12. Checklist khi viết pattern trong vòng lặp

Trước khi chọn cú pháp, nên xác định:

- Bạn muốn **dừng** khi gặp phần tử không khớp hay muốn **tiếp tục duyệt**?
- Pattern variable được cần trong **body**, **ForUpdate**, hay chỉ trong một nhánh `if`/`switch`?
- Kiểu đầu vào có thể là `null`, và collection có thể rỗng hay không?
- Bạn đang viết code cho **Java 21** hay đang đọc tài liệu preview của Java 20?
- Nếu dùng record pattern, nó nằm trong **`instanceof` hoặc `switch`** ở một vị trí cú pháp hợp lệ hay đang đặt nhầm ngay trong enhanced-for header?

**Ghi nhớ:** với Java 21, **basic `for` có thể giới thiệu pattern variable từ condition để dùng trong body và update**; còn **enhanced `for` duyệt phần tử bằng biến lặp thường**, và pattern matching được đặt trong thân vòng lặp khi cần kiểm tra hoặc giải cấu trúc.

## Tham khảo chính thức

- [Java Language Specification 21 — §6.3.2.5 Scope for Pattern Variables in `for` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2.5)
- [Java Language Specification 21 — §14.14.1 Basic `for` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.14.1)
- [Java Language Specification 21 — §14.14.2 Enhanced `for` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.14.2)
- [Oracle Java SE 21 — Java Language Changes (record pattern header của enhanced `for` đã bị loại)](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
