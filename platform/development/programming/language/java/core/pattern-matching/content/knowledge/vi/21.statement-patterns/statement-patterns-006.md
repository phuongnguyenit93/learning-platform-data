# Break và continue trong pattern branch (Java 21+)

## 1. Pattern branch có làm thay đổi ý nghĩa của break/continue không?

Trong Java, “pattern branch” thường chỉ nhánh được chọn bởi **pattern matching**, ví dụ `case Data(var amount)` trong `switch` hoặc nhánh `if (value instanceof String text)`. Đây là cách mô tả nhánh chương trình, không phải từ khóa Java mới. Pattern xác định **khi nào nhánh khớp**; còn `break` và `continue` vẫn tuân theo quy tắc điều khiển luồng của statement bao quanh.

Hãy nhớ ba điểm trước khi đọc code:

- `break;` không nhãn chấm dứt **vòng lặp hoặc switch statement gần nhất** chứa nó. Khi `switch` nằm trong vòng `for`, `break;` ở `case` chỉ thoát `switch` rồi tiếp tục **phần còn lại trong cùng lượt lặp**.
- `continue;` không nhãn chuyển tới **lượt lặp tiếp theo của vòng lặp gần nhất**. Nó không chuyển sang `case` khác. `switch` tự nó không phải vòng lặp.
- `break outer;` và `continue outer;` dùng nhãn để điều khiển một cấu trúc bao ngoài: `break` có thể rời khỏi statement có nhãn phù hợp; `continue` phải nhắm đến **vòng lặp** có nhãn.

**Phiên bản:** Type patterns trong `instanceof` được chuẩn hóa từ Java 16 (JEP 394); record patterns và pattern matching for `switch` từ **Java 21** (JEP 440/441). Toàn bộ ví dụ có pattern trong `switch` dưới đây dùng **JDK 21+**, không cần `--enable-preview`.

## 2. Bảng so sánh các lệnh điều khiển

| Lệnh | Tác dụng | Trong một pattern branch |
| --- | --- | --- |
| `break;` | Thoát vòng lặp hoặc `switch statement` gần nhất | Thường ra khỏi `switch`, nhưng vòng `for` ngoài vẫn chạy |
| `continue;` | Sang lượt tiếp theo của vòng lặp gần nhất | Bỏ qua phần thân vòng lặp còn lại |
| `break label;` | Thoát statement mang nhãn | Thoát hẳn vòng ngoài nếu nhãn trỏ tới vòng đó |
| `continue label;` | Tiếp tục vòng lặp mang nhãn | Hữu ích khi có nhiều vòng lặp lồng nhau |
| `return;` / `return value;` | Kết thúc phương thức | Không quay lại xử lý những event tiếp theo |
| `yield value;` | Cấp giá trị cho `switch expression` | Dùng với block của switch expression; không thay cho `break` trong vòng lặp |

`switch statement` là một **statement**; `switch expression` tạo ra một **giá trị**. Sự khác biệt này đặc biệt quan trọng khi dùng nhánh `case ... -> { ... }`.

## 3. Tạo mô hình sự kiện bằng sealed interface và record

Giả sử ta xử lý luồng sự kiện, mỗi sự kiện có một dạng:

```java
sealed interface Event permits Data, Skip, Stop {}
record Data(int amount) implements Event {}
record Skip() implements Event {}
record Stop() implements Event {}
```

- `Data` mang component `amount`.
- `Skip` yêu cầu bỏ qua phần công việc còn lại của lượt hiện tại.
- `Stop` yêu cầu thoát hoàn toàn khỏi vòng lặp đang duyệt các sự kiện.

Các kiểu được khai báo trong ví dụ độc lập về ý nghĩa, nhưng những đoạn minh họa này cần nằm trong class hoặc file Java thích hợp khi biên dịch. Chương trình chạy trọn vẹn nằm ở mục 6.

## 4. break trong case pattern của switch statement

```java
for (Event event : events) {
    switch (event) {
        case Data(var amount) -> {
            System.out.println("data:" + amount);
            break;
        }
        default -> System.out.println("other");
    }
    System.out.println("after-switch");
}
```

Đây là đoạn minh họa dùng biến `events` đã khai báo. Với `Data(3)`, case `Data(var amount)` khớp record và lấy `amount = 3`. Sau khi in `data:3`, `break;` thoát **switch statement**. Java tiếp tục thực thi `System.out.println("after-switch")` trong **cùng lượt** của vòng `for`. Nó chỉ chuyển sang sự kiện tiếp theo sau khi kết thúc lượt này.

**Vì sao có thể bỏ `break;` ở đây?** Nhánh sử dụng cú pháp mũi tên `->`, không tự động fall-through sang case tiếp theo. `break;` minh họa rõ đích nhảy, nhưng trong block chỉ có một lệnh in rồi hết nhánh, nó thường không cần thiết.

Nếu có một vòng lặp khác nằm ngay bên trong block `case`, một `break;` đặt **trong vòng lặp nhỏ đó** sẽ thoát vòng lặp nhỏ trước tiên. Cần đọc cấu trúc bao quanh, không chỉ đọc tên pattern.

## 5. continue trong case pattern và guard when

```java
for (Event event : events) {
    switch (event) {
        case Data(var amount) when amount < 0 -> {
            System.out.println("ignore:" + amount);
            continue;
        }
        default -> System.out.println("handled");
    }
    System.out.println("after-switch");
}
```

- `Data(var amount)` là **record pattern**: kiểm tra sự kiện kiểu `Data` và tách component `amount`.
- `when amount < 0` là **guard** của case: chỉ xét sau khi pattern khớp; biến `amount` dùng được trong guard.
- Khi lượng âm, `continue;` chuyển sang **lượt tiếp theo của vòng `for`**. Lệnh `after-switch` bị bỏ qua trong lượt này.
- Nếu không có vòng lặp `for`, `while` hoặc `do` bao quanh, `continue;` đặt trong `case` là **lỗi biên dịch**: `switch` không phải vòng lặp.

`continue;` tuyệt đối không có nghĩa là “thử case kế tiếp”. Việc chọn case xảy ra theo quy tắc matching của `switch`; một khi đã thực thi nhánh và gặp `continue`, quyền điều khiển được trả về vòng lặp.

**Thứ tự case:** Khi dùng `case Data(var n) when n < 0` cùng `case Data(var n)` không guard, hãy đặt case đặc biệt có guard **trước** case tổng quát. Nếu case tổng quát ở trên, compiler có thể xác định case có guard phía dưới bị che khuất (*dominated*).

## 6. Chương trình Java hoàn chỉnh, có thể chạy

Tạo file **`PatternBranchControlFlowDemo.java`**:

```java
public class PatternBranchControlFlowDemo {
    sealed interface Event permits Data, Skip, Stop {}
    record Data(int amount) implements Event {}
    record Skip() implements Event {}
    record Stop() implements Event {}

    static void process(java.util.List<Event> events) {
        int total = 0;

        outer: for (Event event : events) {
            switch (event) {
                case Data(var amount) when amount < 0 -> {
                    System.out.println("ignore:" + amount);
                    continue;
                }

                case Data(var amount) -> {
                    System.out.println("data:" + amount);
                    total += amount;
                    break;
                }

                case Skip s -> {
                    System.out.println("skip");
                    continue;
                }

                case Stop s -> {
                    System.out.println("stop");
                    break outer;
                }
            }

            System.out.println("after-switch");
        }

        System.out.println("total:" + total);
    }

    static void scan(java.util.List<Object> values) {
        for (Object value : values) {
            if (!(value instanceof String text)) continue;
            if (text.equals("END")) break;
            if (text.isBlank()) continue;
            System.out.println("text:" + text.toUpperCase());
        }
    }

    static String describe(Object value) {
        return switch (value) {
            case Integer n when n < 0 -> "negative:" + n;
            case Integer n -> {
                yield "integer:" + n;
            }
            case String s -> "string:" + s;
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        process(java.util.List.of(
            new Data(3), new Data(-2), new Skip(),
            new Data(4), new Stop(), new Data(100)
        ));

        scan(java.util.Arrays.asList("hi", 15, " ", "END", "later"));
        System.out.println(describe(-1));
        System.out.println(describe(7));
        System.out.println(describe(null));
    }
}
```

**Biên dịch và chạy bằng JDK 21 trở lên:**

```bash
javac --release 21 PatternBranchControlFlowDemo.java
java PatternBranchControlFlowDemo
```

**Stdout chính xác:**

```text
data:3
after-switch
ignore:-2
skip
data:4
after-switch
stop
total:7
text:HI
negative:-1
integer:7
null
```

Kết quả trên đã được chạy và đối chiếu bằng JDK 24; chương trình sử dụng cú pháp có từ Java 21.

### Phân tích từng sự kiện trong `process`

1. `Data(3)`: case không guard cộng `3`, in `data:3` rồi `break;` thoát `switch`. Vì vẫn đang ở trong vòng `for`, in tiếp `after-switch`.
2. `Data(-2)`: case guard âm khớp, in `ignore:-2` rồi `continue;` sang sự kiện tiếp theo; **không in** `after-switch`.
3. `Skip()`: nhánh type pattern `Skip s` được chọn, in `skip` rồi `continue;`; phần còn lại của lượt bị bỏ qua.
4. `Data(4)`: cộng `4` làm tổng bằng `7`, in `data:4`, `break;` khỏi `switch` và in `after-switch`.
5. `Stop()`: in `stop` rồi `break outer;` thoát vòng `for` có nhãn. `Data(100)` phía sau không chạy; tổng cuối cùng là `7`.

Vì `Event` là sealed interface và ba kiểu `Data`, `Skip`, `Stop` là các subtype được phép, những case không guard tương ứng bao phủ các loại sự kiện cần xử lý. Nhánh `Data` đầu tiên có guard; nhánh `Data` thứ hai bao phủ các giá trị còn lại. Do đó trong ví dụ không cần `default` để bao phủ thêm subtype hợp lệ.

**Lưu ý `null`:** `switch (event)` có thể ném `NullPointerException` nếu selector là `null` mà không có `case null`. `List.of(...)` trong ví dụ không chứa `null`, và `Event` không bảo đảm giá trị tham chiếu bất kỳ là non-null. Khác với `switch`, `value instanceof String text` luôn trả `false` khi `value == null`.

### Phân tích `scan`

`scan` duyệt danh sách `"hi"`, `15`, `" "`, `"END"` và `"later"`:

- `"hi"` khớp `String text`, không phải chuỗi rỗng/blank, in `text:HI`.
- `15` không phải `String` nên `continue` bỏ qua lượt đó.
- `" "` là chuỗi blank nên cũng bị `continue` bỏ qua.
- `"END"` kích hoạt `break;` thoát **vòng `for` của `scan`**; không xử lý `"later"`.

Ở đây không có `switch` bên trong `scan`. Vì vậy `break;` thoát vòng `for` gần nhất. Ý nghĩa thay đổi theo cấu trúc lệnh bao quanh, **không theo cách xác định nhánh bằng pattern**.

## 7. Flow scoping khi kết hợp instanceof với continue

Java áp dụng **flow scoping** cho pattern variable: biến chỉ khả dụng tại các vị trí mà luồng điều khiển bảo đảm pattern đã khớp. Xem ví dụ đã chạy trong `scan`:

```java
for (Object value : values) {
    if (!(value instanceof String text)) continue;

    // Tới đây text chắc chắn đã được gán từ một String.
    if (text.equals("END")) break;
    if (text.isBlank()) continue;
    System.out.println(text.toUpperCase());
}
```

Nếu `value` không phải `String`, nhánh phủ định đúng và `continue` kết thúc lượt lặp ngay. Mọi đường đi tới các câu lệnh dưới `if` đều buộc phải qua một lần `instanceof String text` thành công, nên Java cho phép dùng `text`.

Nếu thay `continue;` trong nhánh phủ định bằng một lệnh in mà không kết thúc luồng, biến `text` **không còn chắc chắn được gán** ở dòng phía sau và có thể gây lỗi biên dịch. Đây là vấn đề **phạm vi theo luồng**, khác với đích nhảy của `continue`.

Trong code dùng `&&`, có thể kiểm tra thêm điều kiện trên biến đã match:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

Ngược lại, không được đọc `text` ở vế phải của `||` khi vế trái là `value instanceof String text`, vì vế phải của `||` chỉ chạy khi vế trái có thể thất bại.

## 8. Khi nào cần break outer hoặc continue outer?

`break;` chọn cấu trúc breakable gần nhất. Để thoát khỏi vòng lặp ngoài một `switch statement`, dùng nhãn:

```java
outer: for (Event event : events) {
    switch (event) {
        case Stop s -> {
            break outer;
        }
        default -> System.out.println("processing");
    }
}
System.out.println("finished");
```

`break outer;` thoát statement có nhãn `outer`, vì vậy vòng lặp dừng và chương trình tiếp tục ở `finished`. Đoạn này minh họa trong phương thức có biến `events` và các kiểu `Event`, `Stop` đã định nghĩa.

Với vòng lặp lồng nhau, có thể dùng `continue outer;` để chuyển sang lượt mới của vòng lặp ngoài:

```java
outer: for (Object item : items) {
    if (!(item instanceof String text)) continue outer;

    for (char ch : text.toCharArray()) {
        if (ch == '!') {
            continue outer; // Bỏ phần còn lại của item hiện tại.
        }
        System.out.println(ch);
    }
}
```

Khác biệt nếu dùng `break;` tại vị trí đó: vì lệnh nằm trong vòng `for (char ch : ...)`, `break;` chỉ thoát **vòng lặp ký tự**, rồi chuyển xuống những câu lệnh còn lại trong vòng ngoài. Lệnh `continue outer;` nhảy thẳng tới lượt xử lý `item` tiếp theo. Nhãn của `continue` phải trỏ đến vòng lặp thích hợp.

## 9. Switch statement và switch expression khác nhau thế nào?

### Switch statement

```java
switch (value) {
    case Integer n -> {
        if (n < 0) {
            System.out.println("negative");
            break; // Thoát switch statement.
        }
        System.out.println("non-negative");
    }
    default -> System.out.println("other");
}
```

Đây là đoạn minh họa **bên trong phương thức có biến `value`**. `switch statement` thực thi các statement ở nhánh được chọn. `break;` có thể thoát `switch`. Arrow rules không tự fall-through, nên không cần `break` chỉ để ngăn chuyển nhánh.

### Switch expression

```java
static String describe(Object value) {
    return switch (value) {
        case Integer n when n < 0 -> "negative:" + n;
        case Integer n -> {
            yield "integer:" + n;
        }
        case String s -> "string:" + s;
        case null -> "null";
        default -> "other";
    };
}
```

`switch expression` phải sinh ra một giá trị trên các đường hoàn thành bình thường. Với arrow rule chứa biểu thức, giá trị biểu thức trở thành kết quả. Với arrow rule chứa **block** cần trả giá trị, dùng `yield value;`. Không dùng `break;` như cách “trả kết quả” của `switch expression`; `yield` và `break` có mục đích khác nhau.

Trong ví dụ, `describe(-1)` trả `negative:-1`, `describe(7)` trả `integer:7` và `describe(null)` trả `null` nhờ `case null`. Pattern variable `n` chỉ có phạm vi ở guard/nhánh đã khớp. Case `Integer n` không guard nằm sau case cùng kiểu có guard.

Phân biệt thêm `return`: nó kết thúc phương thức hiện tại. `yield` chỉ cung cấp kết quả cho `switch expression` bao quanh; biểu thức có thể được gán vào biến hoặc dùng trong `return` của phương thức.

## 10. Bẫy thường gặp và cách tránh

| Lỗi | Giải thích và cách xử lý |
| --- | --- |
| Dùng `break;` trong `case` và nghĩ vòng `for` ngoài cũng dừng | `break` thường thoát `switch statement` gần nhất. Dùng `break outer;` khi muốn kết thúc vòng ngoài có nhãn. |
| Dùng `continue;` để chuyển sang case kế tiếp | `continue` chuyển sang **lượt lặp mới**, không đổi nhánh switch. |
| Viết `continue;` trong `switch` không nằm trong vòng lặp | Không có vòng lặp làm đích, gây lỗi biên dịch. |
| Dùng `break;` để trả về chuỗi từ `switch expression` | Dùng `yield "value";` ở block hoặc trực tiếp `case ... -> "value"`. |
| Đặt case tổng quát `Data(var n)` trước case có `when n < 0` | Nhánh cụ thể phía sau có thể bị dominated. Đặt guard đặc biệt trước. |
| Dùng biến pattern bên ngoài nhánh chưa chắc khớp | Pattern variables có **flow scoping**; chỉ đọc khi mọi đường đi tới vị trí đó đều bảo đảm đã match. |
| Bỏ quên `null` trong `switch` pattern | Tham chiếu selector `null` cần xử lý phù hợp, thường bằng `case null` hoặc kiểm tra trước `switch`. |
| Cố chống fall-through bằng `break` trong mọi arrow rule | Với `->` các rule không fall-through; chỉ dùng `break` nếu cần kết thúc switch sớm. |
| Dùng `break;` trong một vòng con và tưởng sẽ thoát switch bên ngoài | `break` chọn cấu trúc breakable gần nhất, thường là vòng con. |

**Cú pháp `case ... :`:** Các ví dụ ưu tiên `case ... ->` vì rõ ràng và không có fall-through. Với cú pháp colon-style, quy tắc chia nhóm statement và phạm vi pattern variable có thêm giới hạn. Không nên phụ thuộc vào fall-through giữa các nhánh có pattern.

## 11. Bài tập: dự đoán kết quả trước khi chạy

Giả sử ba record sau đã được khai báo:

```java
sealed interface Action permits Value, Ignore, Halt {}
record Value(int number) implements Action {}
record Ignore() implements Action {}
record Halt() implements Action {}
```

Tạo danh sách gồm `Value(2)`, `Ignore()`, `Value(5)`, `Halt()` và `Value(99)`. Hãy dùng `switch` với record/type pattern sao cho:

1. `Value` cộng `number` vào tổng và vẫn in `visited` sau khi thoát `switch`.
2. `Ignore` bỏ qua việc in `visited` bằng `continue;`.
3. `Halt` thoát toàn bộ vòng `for` bằng nhãn; `Value(99)` không được xử lý.
4. Tổng cuối cùng phải bằng `7`.

Gợi ý đáp án (đặt trong một phương thức, `actions` là `List<Action>`):

```java
int sum = 0;
outer: for (Action action : actions) {
    switch (action) {
        case Value(var number) -> {
            sum += number;
            break;
        }
        case Ignore ignored -> {
            continue;
        }
        case Halt halted -> {
            break outer;
        }
    }
    System.out.println("visited");
}
System.out.println(sum); // 7
```

Kết quả mong đợi là hai dòng `visited` (cho `Value(2)` và `Value(5)`), sau đó một dòng `7`. Thử đổi `break;` của case `Value` thành `continue;` để kiểm tra tại sao hai dòng `visited` biến mất, dù tổng vẫn bằng `7`.

## 12. Tài liệu tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 — Statements (`14)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html)
