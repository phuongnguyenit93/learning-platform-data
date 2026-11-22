# Exhaustiveness trong pattern switch statement (Java 21)

**Exhaustiveness** nghĩa là trình biên dịch có thể chứng minh một `switch` **bao phủ mọi giá trị thuộc kiểu selector mà ngôn ngữ yêu cầu phải xử lý**. Trong Java 21, một **enhanced switch statement** — trong đó có `switch statement` sử dụng `case` pattern — **bắt buộc exhaustive**. Khác với `switch statement` kiểu cũ, không thể chỉ viết vài nhánh pattern rồi để mặc các kiểu khác mà không có nhánh bao phủ.

Ví dụ, khi selector là `Object`, mã này **không biên dịch**:

```java
// Ví dụ CỐ Ý SAI trong Java 21:
static void incomplete(Object value) {
    switch (value) {
        case String text -> System.out.println(text);
        case Integer number -> System.out.println(number);
        // Thiếu nhánh bao phủ các Object khác.
    }
}
```

`Object` có thể chứa `Double`, `Boolean`, một class tùy ý và nhiều kiểu khác. `String` cùng `Integer` không bao phủ hết các trường hợp; compiler sẽ báo switch không exhaustive.

Cách sửa thông thường:

```java
static void complete(Object value) {
    switch (value) {
        case String text -> System.out.println("text:" + text);
        case Integer number -> System.out.println("integer:" + number);
        default -> System.out.println("other");
    }
}
```

Lúc này mọi **giá trị không null** đều có một nhánh phù hợp. Nhưng có một chi tiết quan trọng: **exhaustive ở compile-time không đồng nghĩa `null` tự được xử lý an toàn**. Với phương thức trên, truyền `null` sẽ ném `NullPointerException`; muốn xử lý riêng cần `case null` hoặc `case null, default` phù hợp.

Bài này đi từ quy tắc compile-time, vai trò của `default`, `sealed`, `enum`, `when`, cho đến hành vi lúc chạy và ví dụ Java 21 hoàn chỉnh.

## 1. Traditional switch statement và enhanced switch statement khác nhau ra sao?

Java có `switch statement` trước khi có pattern matching. Một traditional switch statement có thể **không exhaustive**:

```java
static void traditional(int value) {
    switch (value) {
        case 1 -> System.out.println("one");
        case 2 -> System.out.println("two");
        // Không có default vẫn hợp lệ.
    }
}
```

Nếu `value == 3`, không nhãn nào khớp và `switch statement` này hoàn thành bình thường, không in gì. Đây là hành vi được cho phép với traditional switch statement.

Ngược lại, `switch statement` sử dụng pattern là **enhanced switch statement**:

```java
static void enhanced(Object value) {
    switch (value) {
        case String s -> System.out.println(s.length());
        default -> System.out.println("not String");
    }
}
```

Nó phải exhaustive: `case String s` chỉ bao phủ một phần miền kiểu; `default` bao phủ những giá trị còn lại theo quy tắc chọn nhãn.

| Tiêu chí | Traditional switch statement | Enhanced switch statement có pattern |
| --- | --- | --- |
| Nhãn `case` | Hằng số thuộc kiểu selector truyền thống | Có thể chứa pattern, guard, `null` và hằng phù hợp |
| Compiler bắt buộc exhaustive? | **Không** | **Có** |
| Không nhãn nào khớp | Có thể hoàn thành bình thường | Không được để khoảng trống có thể chứng minh ở compile-time; tình huống thay đổi nhị phân có thể gây lỗi runtime |
| Có thể dùng `default`? | Có | Có, và là cách dễ nhất để bao phủ phần còn lại |
| Có thể exhaustive mà không `default`? | Không bắt buộc exhaustive; vẫn có thể liệt kê mọi hằng | Có, ví dụ khi bao phủ đủ các nhánh của `sealed` type |

Thuật ngữ *enhanced* rộng hơn việc có pattern: Java 21 còn xem một số dạng switch có `case null` hoặc selector thuộc kiểu tham chiếu rộng là enhanced. Đối với bài này, trọng tâm là **một switch statement đã có pattern label thì phải exhaustive**.

Đừng nhầm với `switch expression`: **mọi switch expression đều phải exhaustive**, dù sử dụng pattern hay chỉ nhãn hằng số. Sự khác biệt đáng học ở đây là quy tắc exhaustive mới được áp dụng cho **enhanced switch statement**.

## 2. Exhaustiveness là phân tích kiểu tại thời điểm biên dịch

Trình biên dịch không chạy thử các đối tượng để kiểm tra switch. Nó suy luận dựa trên:

1. **Kiểu tĩnh của selector**, ví dụ `Object`, `Shape`, `Color`.
2. **Tập các nhãn**: hằng số, type pattern, record pattern, `default`, `case null`.
3. **Quan hệ subtype và các hạn chế của kiểu**, nhất là kiểu `sealed` có tập subtype trực tiếp đã khai báo.
4. **Guard `when`** và việc liệu một nhánh có thực sự bao phủ mọi giá trị kiểu đó hay không.
5. **Dominance** và các quy tắc hợp lệ khác của nhãn, ví dụ không được đặt nhánh hẹp bị một nhánh rộng trước đó che khuất.

Nhìn từ góc độ kiểm tra kiểu, cần trả lời: “Có thể có một giá trị selector thuộc miền cần xét mà **không nhãn nào** được chọn hay không?”. Nếu có, một enhanced switch statement không có nhánh bao phủ sẽ bị từ chối.

Ví dụ, `case Number n` bao phủ các đối tượng `Number` nhưng không bao phủ một `String`, `Boolean` hay đối tượng thông thường nếu selector có kiểu tĩnh `Object`. Vì vậy nó không đủ thay cho `default`:

```java
// KHÔNG BIÊN DỊCH: selector Object còn nhiều kiểu khác Number.
static void invalid(Object value) {
    switch (value) {
        case Number n -> System.out.println(n);
    }
}
```

Đây là đoạn minh họa cố ý sai, không chép vào chương trình chạy cuối.

## 3. `default`: lựa chọn dễ hiểu khi selector có miền rộng

Với `Object`, cách phổ biến nhất để đảm bảo exhaustive là thêm `default`:

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "string";
        case Number n -> "number";
        default -> "other";
    };
}
```

Mã trên là một **switch expression** minh họa; nếu chuyển thành `switch statement` với cùng ba nhãn và các lệnh thực thi, compiler cũng nhận thấy tính exhaustive. `default` giúp xử lý những đối tượng không thuộc `String` hoặc `Number`.

Tuy nhiên:

- `default` **không mặc nhiên bắt `null`** trong pattern switch của Java 21.
- Một type pattern chỉ khớp khi selector là giá trị không null phù hợp với kiểu pattern.
- Nếu `value == null` mà không có nhánh xử lý `null`, `switch` sẽ ném `NullPointerException`.

Nếu muốn phân loại cả `null`, có thể viết tường minh:

```java
static void classifyNullable(Object value) {
    switch (value) {
        case null -> System.out.println("missing");
        case String s -> System.out.println("string:" + s);
        case Number n -> System.out.println("number:" + n);
        default -> System.out.println("other");
    }
}
```

Hoặc nếu `null` và mọi kiểu còn lại có **cùng hành vi**, dùng nhãn đặc biệt của Java 21:

```java
static void classifyNullableTogether(Object value) {
    switch (value) {
        case String s -> System.out.println("string:" + s);
        case Number n -> System.out.println("number:" + n);
        case null, default -> System.out.println("misc");
    }
}
```

`case null, default` là cú pháp kết hợp đặc biệt; đừng suy rộng thành “có thể gộp mọi pattern khác nhau bằng dấu phẩy” trong Java 21.

## 4. Sealed types: exhaustive không cần default

**Sealed class/interface** giới hạn những kiểu được phép trực tiếp mở rộng hoặc triển khai nó. Compiler có thể sử dụng danh sách `permits` để xác định xem các case pattern đã bao phủ đầy đủ các kiểu có thể gặp hay chưa.

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}

record Rectangle(double width, double height) implements Shape {}
```

Ba khai báo trên là ví dụ minh họa; có thể đặt chúng trong cùng một class Java. `Circle` và `Rectangle` là record, do đó là class `final` và có thể trực tiếp triển khai sealed interface này.

Một enhanced switch statement exhaustive:

```java
static void showArea(Shape shape) {
    switch (shape) {
        case Circle c ->
                System.out.println(Math.PI * c.radius() * c.radius());
        case Rectangle r ->
                System.out.println(r.width() * r.height());
    }
}
```

**Không cần `default`** vì mọi đối tượng `Shape` không null đều thuộc `Circle` hoặc `Rectangle`, theo mô hình sealed hierarchy tại thời điểm biên dịch.

### Thiếu một nhánh sẽ bị báo lỗi

```java
// KHÔNG BIÊN DỊCH vì thiếu Rectangle:
static void incompleteShape(Shape shape) {
    switch (shape) {
        case Circle c -> System.out.println(c.radius());
    }
}
```

Đây là lợi thế lớn của pattern switch trên sealed hierarchy: nếu bạn thêm một subtype được phép và biên dịch lại nơi chứa switch, compiler có thể yêu cầu cập nhật các nhánh còn thiếu.

### Khi thêm default có thể làm mất cảnh báo hữu ích

```java
static void showAreaWithDefault(Shape shape) {
    switch (shape) {
        case Circle c -> System.out.println("circle");
        case Rectangle r -> System.out.println("rectangle");
        default -> System.out.println("unrecognized");
    }
}
```

Cú pháp này vẫn hợp lệ. Nhưng nếu sau này thêm `Triangle` vào sealed hierarchy, `default` đã cung cấp nhánh dự phòng, nên compiler không nhất thiết bắt buộc bạn thêm `case Triangle t`. Vì vậy, với một tập subtype **đóng** và yêu cầu nghiệp vụ cần xử lý riêng từng kiểu, **bỏ `default` là lựa chọn giúp compiler kiểm tra tính đầy đủ**.

Điều kiện quan trọng: phải thật sự có phạm vi kiểu đóng đủ để compiler chứng minh. Nếu selector là `Object` hoặc một interface thường có nhiều implementation tùy ý, không thể chỉ liệt kê vài subtype rồi mong có exhaustiveness.

## 5. Exhaustive trên sealed type vẫn không tự xử lý null

Ví dụ `showArea(Shape shape)` ở phần trên là exhaustive theo các subtype hợp lệ, nhưng `showArea(null)` sẽ ném `NullPointerException`.

Để xử lý mọi đầu vào, kể cả nullable reference:

```java
static void showAreaOrMissing(Shape shape) {
    switch (shape) {
        case null -> System.out.println("missing shape");
        case Circle c -> System.out.println("circle:" + c.radius());
        case Rectangle r -> System.out.println("rectangle:" + r.width());
    }
}
```

Đoạn này vẫn exhaustive mà không cần `default`. `case null` xử lý `null` trước, còn hai pattern bảo đảm bao phủ tất cả các implementation được phép.

Phân biệt hai mục tiêu:

- **Exhaustiveness compile-time**: bộ nhãn có đủ theo quy tắc kiểu của Java hay không?
- **Null-safety runtime**: selector có thể là `null` không, và nếu có thì chương trình phải làm gì?

Một switch có thể đạt mục tiêu thứ nhất nhưng vẫn ném exception đối với `null`. Đây **không phải** lỗi xác minh exhaustive của compiler; đó là đặc điểm cách chọn nhãn trên giá trị null.

## 6. Guard `when` không tự bao phủ toàn bộ một kiểu

Guard làm cho pattern **chỉ được chọn khi điều kiện bổ sung đúng**. Do vậy, nhánh có guard thường không thể thay cho một nhánh bao phủ mọi instance của kiểu đó.

```java
// KHÔNG BIÊN DỊCH: Circle có radius không dương và Rectangle chưa được xử lý.
static void badGuard(Shape shape) {
    switch (shape) {
        case Circle c when c.radius() > 0 ->
                System.out.println("positive circle");
        case Rectangle r ->
                System.out.println("rectangle");
    }
}
```

Compiler không thể kết luận mọi `Circle` sẽ thỏa `c.radius() > 0`. Ví dụ `Circle(0)` vẫn là một `Circle` nhưng không chọn được nhánh đó. Nếu không có nhánh dự phòng, switch không exhaustive.

Sửa bằng một nhánh `Circle` không có guard **sau** nhánh có guard:

```java
static void handleGuarded(Shape shape) {
    switch (shape) {
        case Circle c when c.radius() > 0 ->
                System.out.println("positive circle");
        case Circle c ->
                System.out.println("other circle");
        case Rectangle r ->
                System.out.println("rectangle");
    }
}
```

Hai nhánh `Circle` tách biệt: nhánh đầu dành cho bán kính dương, nhánh sau bắt mọi `Circle` còn lại; cộng với `Rectangle`, hierarchy được bao phủ.

**Thứ tự nhãn cũng quan trọng.** Nếu đặt `case Circle c` không guard **trước** `case Circle c when ...`, nhánh guard phía sau sẽ bị **dominated** vì `case Circle c` trước đã bắt mọi `Circle`; Java báo lỗi biên dịch.

Tương tự, với `Object`, chỉ có `case String s when !s.isBlank()` và `case Integer i` chưa đủ; ngoài chuỗi blank còn nhiều kiểu đối tượng khác.

## 7. Enum và tính exhaustive trong switch statement

Một `switch statement` truyền thống trên enum **không bắt buộc** xử lý mọi hằng enum:

```java
enum State { NEW, RUNNING, FINISHED }

static void legacy(State state) {
    switch (state) {
        case NEW -> System.out.println("new");
        // RUNNING và FINISHED không được xử lý; statement truyền thống vẫn hợp lệ.
    }
}
```

Nhưng một `switch expression` trên enum phải exhaustive:

```java
static String label(State state) {
    return switch (state) {
        case NEW -> "new";
        case RUNNING -> "running";
        case FINISHED -> "done";
    };
}
```

Khi xét **enhanced switch statement**, cũng có thể dùng enum với pattern type hoặc nhãn `null` và phải bảo đảm exhaustiveness. Ví dụ:

```java
static void enhancedEnum(State state) {
    switch (state) {
        case null -> System.out.println("null");
        case NEW -> System.out.println("new");
        case RUNNING -> System.out.println("running");
        case FINISHED -> System.out.println("done");
    }
}
```

Có `case null`, nên statement này thuộc dạng enhanced; các enum constant còn lại được liệt kê đủ. Trái lại, chỉ viết `case null` và `case NEW` sẽ không bao phủ `RUNNING` và `FINISHED`.

Lưu ý: việc liệt kê tất cả enum constant có thể đủ để compiler chứng minh exhaustive, nhưng nếu kiểu enum thay đổi giữa thời điểm biên dịch và chạy, vẫn phải xét khả năng mất đồng bộ nhị phân giống các miền kiểu đóng khác.

## 8. Một type pattern đủ rộng cũng có thể exhaustive

Không bắt buộc mọi enhanced switch statement đều phải có `default`. Nếu một **unguarded type pattern** bao phủ toàn bộ miền selector không null, compiler cũng có thể chứng minh tính exhaustive:

```java
static void inspect(CharSequence value) {
    switch (value) {
        case CharSequence sequence ->
                System.out.println(sequence.length());
    }
}
```

Với selector `CharSequence`, mỗi giá trị không null đều là một `CharSequence`, nên chỉ cần pattern ấy để bao phủ miền kiểu. Giá trị `null` vẫn ném `NullPointerException` nếu không có `case null`.

Một pattern quá rộng có thể khiến các nhánh sau bị dominated:

```java
// KHÔNG BIÊN DỊCH: String là CharSequence, case String bị che.
static void dominated(CharSequence value) {
    switch (value) {
        case CharSequence c -> System.out.println("any chars");
        case String s -> System.out.println("text");
    }
}
```

Nếu mục tiêu là ưu tiên `String` rồi xử lý mọi `CharSequence` còn lại, đặt `case String s` **trước** `case CharSequence c`.

Khả năng dùng supertype là công cụ rất hữu ích khi bạn không cần xử lý riêng từng subtype. Nhưng nếu muốn compiler buộc kiểm tra từng loại con trong sealed hierarchy, một nhánh supertype quá rộng có thể làm mất lợi thế đó giống như `default`.

## 9. Record pattern và kiểm tra tính bao phủ

Java 21 còn hỗ trợ record pattern, cho phép vừa kiểm tra record type vừa tách các component:

```java
record Point(int x, int y) {}

static void show(Object value) {
    switch (value) {
        case Point(int x, int y) ->
                System.out.println(x + "," + y);
        default ->
                System.out.println("not Point");
    }
}
```

Đây là một method minh họa trong cùng class với `record Point`. Nhánh `Point(int x, int y)` có thể khớp mọi đối tượng `Point` phù hợp với component primitive `int`, nhưng `Object` còn có vô số kiểu khác, nên `default` vẫn cần để switch trên `Object` exhaustive.

Với record pattern lồng nhau, compiler phải xem **cả kiểu record lẫn khả năng khớp của các component**. Một pattern hẹp trên component có thể bỏ sót giá trị hợp lệ, nhất là khi component có kiểu tham chiếu rộng. Đừng tự kết luận rằng “đã có case record thì bao phủ toàn bộ record” nếu pattern còn ràng buộc kiểu con hay cấu trúc dữ liệu.

Cách chắc chắn là đánh giá toàn bộ các biến thể component, hoặc dùng một pattern bao phủ record type khi bạn muốn xử lý chung cả record. Không dùng `default` một cách vô thức chỉ để tắt lỗi; hãy quyết định xem các trường hợp chưa xử lý có cần phát hiện rõ lúc biên dịch hay không.

## 10. Exhaustiveness là bắt buộc khi dùng colon group nữa

Quy tắc không chỉ dành cho cú pháp `case ... ->`. Với **colon group**, switch statement có pattern vẫn phải exhaustive:

```java
static void classifyWithColon(Object input) {
    switch (input) {
        case null:
            System.out.println("missing");
            break;
        case String s:
            System.out.println("text:" + s);
            break;
        default:
            System.out.println("other");
    }
}
```

`default` làm cho statement exhaustive đối với các giá trị không null còn lại, còn `case null` xử lý tham chiếu null.

Hai vấn đề khác nhau cần kiểm tra:

1. **Exhaustiveness**: các nhãn có bao phủ mọi giá trị cần thiết không?
2. **Fall-through và definite matching**: một nhóm có thể rơi vào nhóm sau chứa pattern variable chưa khớp hay không?

`break` trong colon group ngăn fall-through, nhưng **không tạo ra một case mới** để bao phủ kiểu còn thiếu. Ngược lại, thêm `default` có thể làm switch exhaustive nhưng không tự sửa một đường fall-through không hợp lệ. Vì vậy, phải kiểm tra riêng hai nhóm quy tắc.

Trong `switch expression` dùng colon group, các đường đi cho kết quả phải `yield` hoặc `throw`; `break` không thay cho `yield`. Đây là vấn đề khác với exhaustiveness của nhãn.

## 11. Exhaustive về kiểu khác với xử lý đầy đủ về nghiệp vụ

Một switch có thể **đúng cú pháp và exhaustive** nhưng chưa xử lý đủ các tình huống nghiệp vụ:

```java
static void process(Object value) {
    switch (value) {
        case String s -> System.out.println("string");
        default -> System.out.println("other");
    }
}
```

Compiler chấp nhận nhờ `default`, nhưng ví dụ này:

- không phân biệt chuỗi rỗng và chuỗi có nội dung;
- không phân biệt `Integer`, `Double`, `Boolean`;
- ném `NullPointerException` nếu nhận `null`.

Do đó, “exhaustive” chỉ nói lên **khả năng chọn nhãn theo quy tắc Java**, không chứng minh code đã thực hiện hết validation, phân quyền hay tính toán cần thiết. Nếu API nhận nullable data hoặc sealed subtype có ý nghĩa riêng, hãy thể hiện điều đó thành các nhánh tường minh và kiểm thử.

## 12. Hành vi runtime khi hierarchy thay đổi

Một switch trên sealed type có thể được compiler đánh giá exhaustive dựa vào tập subtype tại lúc biên dịch. Trong hệ thống biên dịch và triển khai từng phần, có khả năng các class liên quan đã thay đổi giữa hai thời điểm đó.

Ví dụ, mã switch được biên dịch khi `Shape` chỉ cho phép `Circle` và `Rectangle`, nhưng sau đó thư viện được cập nhật thêm một subtype mới mà **client chứa switch không được biên dịch lại**. Nếu runtime gặp trường hợp mới không có case phù hợp, Java 21 có thể ném **`MatchException`** ở enhanced switch.

Điều này khác với việc thiếu nhánh ở thời điểm compile-time: khi biên dịch lại toàn bộ source theo hierarchy mới, compiler có thể phát hiện không exhaustive và từ chối. Runtime `MatchException` là một cơ chế bảo vệ khi giả định exhaustiveness ở binary cũ không còn đúng.

Không nên dùng `default` trong mọi switch chỉ để tránh tình huống đó nếu yêu cầu nghiệp vụ là **bắt buộc cập nhật handler khi thêm subtype**. Hãy quyết định giữa hai chiến lược: *fail fast khi xuất hiện kiểu mới* hoặc *định nghĩa hành vi dự phòng*. Kiểm thử triển khai theo phiên bản giúp giảm rủi ro bất đồng bộ binary.

## 13. Ví dụ hoàn chỉnh chạy trên Java 21

Tạo file **`ExhaustiveSwitchStatementDemo.java`**:

```java
public class ExhaustiveSwitchStatementDemo {
    sealed interface Command permits Open, Close {}

    record Open(String path) implements Command {}

    record Close(int code) implements Command {}

    static void handle(Command command) {
        // Exhaustive nhờ bao phủ đủ hai subtype được phép.
        switch (command) {
            case Open open ->
                    System.out.println("open:" + open.path());
            case Close close ->
                    System.out.println("close:" + close.code());
        }
    }

    static void handleNullable(Command command) {
        switch (command) {
            case null -> System.out.println("missing command");
            case Open open ->
                    System.out.println("open:" + open.path());
            case Close close ->
                    System.out.println("close:" + close.code());
        }
    }

    static void classify(Object input) {
        // Exhaustive với Object nhờ default.
        switch (input) {
            case null -> System.out.println("null");
            case String s when s.isBlank() ->
                    System.out.println("blank");
            case String s ->
                    System.out.println("text:" + s.strip());
            case Integer n ->
                    System.out.println("integer:" + n);
            default ->
                    System.out.println("other");
        }
    }

    static void traditional(int value) {
        // Traditional switch statement: không bắt buộc exhaustive.
        switch (value) {
            case 1 -> System.out.println("one");
        }
    }

    public static void main(String[] args) {
        handle(new Open("report.txt"));
        handle(new Close(7));
        handleNullable(null);

        classify(null);
        classify("  ");
        classify("  Java  ");
        classify(4);
        classify(2.5);

        traditional(2); // Không in gì.
        System.out.println("done");
    }
}
```

Biên dịch và chạy bằng **JDK 21**:

```bash
javac --release 21 ExhaustiveSwitchStatementDemo.java
java ExhaustiveSwitchStatementDemo
```

Không cần `--enable-preview`: pattern matching for switch đã được chuẩn hóa trong Java 21.

**Stdout:**

```text
open:report.txt
close:7
missing command
null
blank
text:Java
integer:4
other
done
```

Đối chiếu kết quả:

1. `handle(new Open(...))` và `handle(new Close(...))` dùng sealed hierarchy gồm đúng hai subtype. Compiler chứng minh `switch statement` exhaustive mà không cần `default`.
2. `handleNullable(null)` dùng `case null` để xử lý reference rỗng, vẫn không cần `default`.
3. `classify(...)` dùng hai nhánh `String` (một nhánh có guard), một nhánh `Integer`, `case null` và `default`; không có đầu vào `Object` nào bị bỏ qua theo quy tắc chọn nhãn.
4. `traditional(2)` dùng switch statement cổ điển chỉ có `case 1`; lời gọi không in gì và không bị compiler từ chối vì không exhaustive.
5. `"  "` được `s.isBlank()` xác định là blank, còn `"  Java  "` đi vào `case String s` tiếp theo và được `strip()` thành `"Java"`.
6. Giá trị `4` được boxing thành `Integer` khi truyền vào tham số `Object`; `2.5` thành `Double` và đi vào `default`.

Để tự kiểm tra rule, hãy lần lượt thử **xóa `default` trong `classify`** hoặc **xóa `case Close close` trong `handle`**, rồi biên dịch lại. Cả hai thao tác đều làm một enhanced switch statement trở nên không exhaustive. Đừng chỉnh sửa class demo cuối nếu cần giữ một ví dụ chạy được.

## 14. Checklist để đọc exhaustiveness nhanh

Khi thấy một `switch statement` có pattern, nên kiểm tra theo thứ tự:

1. **Selector có kiểu tĩnh gì?** `Object` mở rộng, `sealed interface` đóng tương đối, `enum` hữu hạn hay một supertype khác?
2. **Đây có phải enhanced switch statement không?** Nếu có pattern label, câu trả lời là có, và compiler bắt buộc exhaustiveness.
3. **Có `default` không?** Nếu có, thông thường nhánh đó bao phủ các giá trị không null còn lại; nếu không, phải chứng minh các pattern/hằng đã bao phủ đủ.
4. **Nếu selector là sealed type, đã bao phủ mọi subtype được phép chưa?** Một subtype thiếu có thể làm switch không exhaustive.
5. **Nhánh có `when` chỉ xử lý một phần kiểu không?** Nên có nhánh cùng kiểu không guard phía sau nếu cần bao phủ phần còn lại.
6. **`null` được xử lý thế nào?** Không nhầm exhaustive compile-time với null-safety; xem `case null` hoặc `case null, default`.
7. **Các case có bị dominated không?** Nhánh kiểu rộng không guard ở trước có thể che nhánh hẹp phía sau.
8. **Có fall-through bất hợp lệ trong colon group không?** Scope của pattern variable là quy tắc độc lập với exhaustiveness.
9. **Có nên bỏ `default` để nhận cảnh báo khi mở rộng sealed hierarchy không?** Tùy yêu cầu nghiệp vụ: nếu thêm subtype là thay đổi phải xử lý tường minh, nhánh dự phòng có thể che giấu nhu cầu cập nhật.
10. **Đã kiểm tra trường hợp dữ liệu thực tế và binary thay đổi chưa?** Compiler hỗ trợ rất nhiều, nhưng không thay thế kiểm thử `null`, guard, validation và tương thích phiên bản.

**Kết luận:** Trong Java 21, **pattern switch statement phải exhaustive** vì đó là một enhanced switch statement. Với selector mở như `Object`, `default` là cách bao phủ rõ ràng; với sealed type, có thể liệt kê đủ các subtype để **không cần `default`** và nhận hỗ trợ kiểm tra từ compiler. Nhưng `when`, `null`, dominance và khả năng thay đổi hierarchy đều cần được xét riêng — exhaustive không đồng nghĩa chương trình đã an toàn trước mọi lỗi runtime hoặc đầy đủ mọi quy tắc nghiệp vụ.

### Tài liệu tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21, §14.11 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification 21, §14.11.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
