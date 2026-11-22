# Đối tượng `null` và lời gọi qua tham chiếu interface trong Java

Một biến kiểu interface có thể giữ tham chiếu tới đối tượng của lớp triển khai **hoặc giá trị `null`**. Khi biến chứa đối tượng, Java dùng cơ chế **đa hình** để chọn phần cài đặt phương thức instance phù hợp lúc chạy. Khi biến chứa `null`, không có đối tượng nào để thực hiện phương thức: lời gọi instance method qua tham chiếu đó gây `NullPointerException` (`NPE`).

Bài học làm rõ điều gì được kiểm tra **khi biên dịch**, điều gì xảy ra **khi chạy**, vì sao phương thức `default` cũng không gọi được qua tham chiếu `null`, và cách xử lý null theo hợp đồng API.

## 1. `null` không phải là một đối tượng triển khai interface

Ví dụ:

```java
interface Notifier {
    void send(String message);
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("Console: " + message);
    }
}
```

Những khai báo sau đều hợp lệ khi đặt trong một phương thức hoặc phần mã phù hợp:

```java
Notifier active = new ConsoleNotifier();
Notifier absent = null;
Notifier another = active;
```

`active` và `another` giữ tham chiếu tới **cùng một đối tượng** `ConsoleNotifier`. `absent` không trỏ tới bất kỳ đối tượng nào. Kiểu khai báo của cả ba biến đều là `Notifier`, nhưng giá trị thực tế có thể khác nhau.

Cần phân biệt:

- **Interface** là một kiểu tham chiếu định nghĩa hợp đồng. Không thể tạo đối tượng trực tiếp bằng `new Notifier()`.
- **Đối tượng** được tạo bởi lớp cụ thể, ví dụ `new ConsoleNotifier()`, rồi có thể được giữ trong biến kiểu interface.
- **`null`** là giá trị biểu thị không có tham chiếu đến đối tượng; nó không phải một instance của `Notifier`, `ConsoleNotifier` hay `Object`.
- Gán `null` cho biến kiểu interface được phép: `Notifier absent = null;`. Khai báo đó **không tạo** một đối tượng có phương thức rỗng và cũng không tự gọi constructor.
- Bản thân việc khai báo, gán, truyền hoặc trả về `null` thông qua kiểu tham chiếu thường không gây `NullPointerException`. Lỗi xảy ra khi mã thực hiện thao tác cần một đối tượng thật.

Một biến được khai báo là interface **không đảm bảo luôn khác null**. Hệ thống kiểu tham chiếu thông thường của Java 17 cho phép giá trị `null` trừ khi ứng dụng áp dụng hợp đồng hoặc công cụ kiểm tra bổ sung.

## 2. Hai giai đoạn: kiểm tra kiểu lúc biên dịch và dispatch lúc chạy

Xét lời gọi:

```java
Notifier notifier = new ConsoleNotifier();
notifier.send("hello");
```

**Lúc biên dịch**, trình biên dịch biết kiểu khai báo của `notifier` là `Notifier`. Nó xác minh rằng `Notifier` có phương thức instance `send(String)` mà mã hiện tại được quyền gọi.

**Lúc chạy**, Java xem đối tượng thực tế mà biến tham chiếu tới. Vì đối tượng ở đây là `ConsoleNotifier`, JVM thực thi `ConsoleNotifier.send(String)` và in:

```text
Console: hello
```

Thay giá trị đối tượng bằng `null`:

```java
Notifier notifier = null;
notifier.send("hello");
```

Đoạn mã vẫn **biên dịch hợp lệ**: `Notifier` khai báo `send(String)`. Nhưng khi chạy sẽ phát sinh **`NullPointerException`**, bởi không có đối tượng đích để thực hiện phương thức.

Quy tắc quan trọng:

> Kiểu interface quyết định những phương thức có thể **gọi về mặt cú pháp và kiểu**; đối tượng thực tế quyết định phần cài đặt **được thực thi**. Nếu tham chiếu bằng `null`, không có đối tượng để dispatch.

Đừng nhầm `null` với “một lớp không override phương thức”. Khi không có đối tượng, Java không thể chạy phương thức instance của bất kỳ lớp nào. Ngoại lệ được ném tại thao tác gọi, trước khi phần thân phương thức đích bắt đầu.

## 3. Ví dụ Java 17+ chạy được: `null`, `default`, `static`, và đa hình

Tạo tệp **`NullInterfaceDemo.java`**:

```java
interface Notifier {
    String CHANNEL = "message";

    void send(String text);

    default void ping() {
        System.out.println("Notifier ping");
    }

    static String category() {
        return "notification";
    }
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String text) {
        System.out.println("Console: " + text);
    }
}

public class NullInterfaceDemo {
    public static void main(String[] args) {
        Notifier missing = null;

        System.out.println("is null: " + (missing == null));
        System.out.println("instanceof Notifier: "
                + (missing instanceof Notifier));

        // Truy cập thành viên static bằng tên interface.
        System.out.println("channel: " + Notifier.CHANNEL);
        System.out.println("category: " + Notifier.category());

        try {
            missing.send("hello");
        } catch (NullPointerException e) {
            System.out.println("send: NullPointerException");
        }

        try {
            missing.ping();
        } catch (NullPointerException e) {
            System.out.println("ping: NullPointerException");
        }

        Notifier active = new ConsoleNotifier();
        active.send("hello");
        active.ping();
    }
}
```

Biên dịch và chạy:

```bash
javac NullInterfaceDemo.java
java NullInterfaceDemo
```

Kết quả:

```text
is null: true
instanceof Notifier: false
channel: message
category: notification
send: NullPointerException
ping: NullPointerException
Console: hello
Notifier ping
```

Giải thích từng nhóm kết quả:

1. `missing == null` là `true` vì biến không tham chiếu đối tượng nào.
2. `missing instanceof Notifier` là `false`. Toán tử `instanceof` không xem `null` là một thể hiện của bất kỳ kiểu nào.
3. `Notifier.CHANNEL` là trường `public static final` của interface; `Notifier.category()` là phương thức `static` của interface. Cả hai đều được truy cập qua **tên kiểu**, không cần một đối tượng `Notifier`.
4. `missing.send(...)` gây `NullPointerException` dù `send` được khai báo hợp lệ trong interface. Trình biên dịch kiểm tra chữ ký thành công nhưng không tạo ra đối tượng cho `missing`.
5. `missing.ping()` cũng gây `NullPointerException`, mặc dù phương thức `default` có phần thân ngay trong interface. **`default` vẫn là phương thức instance**, cần đối tượng đích.
6. Sau khi `active` giữ `new ConsoleNotifier()`, `active.send(...)` chạy phương thức override của lớp cụ thể; `active.ping()` dùng triển khai `default` được kế thừa từ interface.

Trong mã ứng dụng thông thường, không nên dùng `try/catch (NullPointerException)` để kiểm tra xem tham chiếu có null hay không. `try/catch` ở đây chỉ minh họa **hai lời gọi đều ném lỗi** để chương trình tiếp tục chạy và hiển thị đầy đủ kết quả.

## 4. Lời gọi nào cần đối tượng? Trường và phương thức static khác gì?

Hãy phân biệt các dạng thành viên sau:

| Biểu thức | Có cần một đối tượng không? | Khi biến tham chiếu đang `null` |
| --- | --- | --- |
| `ref.send("x")` (instance method) | Có | `NullPointerException` |
| `ref.ping()` (`default` method) | Có | `NullPointerException` |
| `ref.toString()` (`Object` instance method) | Có | `NullPointerException` |
| `ref == null` | Không | Trả về `true` |
| `ref instanceof Notifier` | Không cần dereference | Trả về `false` |
| `Notifier.CHANNEL` (static field) | Không | Truy cập được qua tên interface |
| `Notifier.category()` (static method) | Không | Gọi được qua tên interface |

`toString()` trong bảng là phương thức instance của `Object` và cũng yêu cầu đối tượng. Một tham chiếu interface khác `null` có thể gọi những phương thức public thích hợp từ `Object` theo quy tắc Java; nhưng một biến `null` không thể thực thi `toString()`.

Đối với **static method được khai báo trong interface**, cách gọi đúng là `Notifier.category()`. Không được nhầm với phương thức `default`; phương thức static của interface không được kế thừa như một instance method để gọi qua biến `Notifier`. Vì vậy ví dụ tập trung vào cú pháp có kiểu tên interface, tránh viết `missing.category()`.

Dù biểu thức `Notifier.CHANNEL` và `Notifier.category()` được gọi khi `missing == null`, chúng **không sử dụng** giá trị của `missing`. Khả năng truy cập static member không làm cho `missing` trở thành đối tượng hợp lệ.

## 5. `null` khi truyền tham số, trả về và gán lại tham chiếu

Interface thường là kiểu tham số hoặc kiểu trả về để tách mã gọi khỏi lớp triển khai:

```java
static void dispatch(Notifier notifier) {
    notifier.send("start");
}
```

Đoạn trên là **một phương thức minh họa**, đặt cùng ngữ cảnh khai báo `Notifier` ở mục 3. `dispatch(new ConsoleNotifier())` hoạt động bình thường, trong khi `dispatch(null)` vẫn qua được bước kiểm tra kiểu ở lời gọi nhưng sẽ gây `NullPointerException` khi `dispatch` cố gọi `notifier.send(...)`.

Điều này áp dụng tương tự cho phương thức trả về interface:

```java
static Notifier findNotifier(boolean enabled) {
    return enabled ? new ConsoleNotifier() : null;
}
```

Trình biên dịch cho phép cả đối tượng `ConsoleNotifier` và `null` trở thành giá trị trả về kiểu `Notifier`. **Người gọi** phải hiểu hợp đồng: phương thức này có thể trả về `null`, hay bảo đảm luôn trả về một triển khai hợp lệ?

Một biến có thể thay đổi giá trị qua thời gian:

```java
Notifier first = new ConsoleNotifier();
Notifier second = first;
first = null;

second.send("still works");
```

Ở đây `first = null` **không hủy đối tượng** đang được `second` tham chiếu. `second.send(...)` vẫn chạy bình thường và in `Console: still works`. `null` là giá trị của **biến tham chiếu**; gán lại một biến không xóa hay làm `null` những tham chiếu khác cùng trỏ tới đối tượng.

## 6. Các cách kiểm tra và xử lý `null` an toàn

Cách thích hợp phụ thuộc vào **hợp đồng nghiệp vụ**. Có hai tình huống rất khác nhau:

### Trường hợp A — không có đối tượng là hợp lệ

Nếu yêu cầu cho phép không có notifier, chỉ gọi khi tồn tại:

```java
static void notifyIfPresent(Notifier notifier) {
    if (notifier != null) {
        notifier.send("ready");
    }
}
```

Nếu đầu vào có thể hợp lệ là `null`, phương thức trên thực hiện chính sách “không có notifier thì bỏ qua”. Đừng mặc định dùng chính sách này cho mọi API; việc bỏ qua âm thầm có thể che giấu lỗi cấu hình hoặc dữ liệu.

Có thể viết theo nhánh thoát sớm:

```java
static void notifyIfPresent(Notifier notifier) {
    if (notifier == null) {
        return;
    }
    notifier.send("ready");
}
```

Về hành vi, hai đoạn trên giống nhau đối với phương thức ví dụ này. Không cần bắt exception để làm một phép kiểm tra `null` đơn giản.

### Trường hợp B — bắt buộc phải có đối tượng

Dùng `Objects.requireNonNull` để kiểm tra đầu vào tại ranh giới API và phát hiện lỗi sớm:

```java
import java.util.Objects;

static void notifyRequired(Notifier notifier) {
    Objects.requireNonNull(notifier, "notifier");
    notifier.send("ready");
}
```

Đây là các dòng minh họa nằm trong class có quyền sử dụng `Notifier` đã khai báo; không phải một tệp Java độc lập. Khi `notifier` là `null`, `Objects.requireNonNull` ném `NullPointerException` với thông điệp `"notifier"`. Khi khác `null`, nó trả về chính tham chiếu và phương thức tiếp tục.

Nếu cần hợp đồng ngoại lệ khác, bạn có thể chủ động ném `IllegalArgumentException` hoặc exception riêng phù hợp. Chọn một quy ước nhất quán và mô tả rõ trong API.

### Trường hợp C — cung cấp hành vi thay thế rõ ràng

Nếu chính sách là “không có nơi nhận thì dùng nơi nhận mặc định”, có thể chọn một triển khai thay thế:

```java
static void notifyWithFallback(Notifier preferred, Notifier fallback) {
    Notifier chosen = preferred != null ? preferred
                                        : java.util.Objects.requireNonNull(fallback);
    chosen.send("ready");
}
```

Cách này vẫn sử dụng đa hình bình thường: `chosen` có kiểu interface và giữ một đối tượng triển khai thực tế. Không cần nhét logic đặc biệt vào lời gọi qua `null`.

Trong những API có nghĩa rõ ràng cho hành vi “không làm gì”, có thể cân nhắc một triển khai **Null Object** (đối tượng thật thực hiện thao tác rỗng). Một Null Object là **instance hợp lệ** của interface; nó khác hoàn toàn với giá trị `null`. Việc thay `null` bằng Null Object chỉ phù hợp nếu bỏ qua thao tác là một chính sách đúng đắn.

## 7. `instanceof` và pattern matching không nhận `null`

Toán tử `instanceof` hữu ích khi cần xác định kiểu thực tế trước một thao tác chuyên biệt:

```java
Notifier value = null;

if (value instanceof ConsoleNotifier console) {
    console.send("ok");
} else {
    System.out.println("Not a ConsoleNotifier instance");
}
```

Đoạn minh họa này dùng **pattern matching for `instanceof`**, có mặt ổn định trong Java 17. Khi `value` là `null`, điều kiện là `false`, biến pattern `console` không được gán để sử dụng trong nhánh `if`, và chương trình in:

```text
Not a ConsoleNotifier instance
```

Với `value = new ConsoleNotifier()`, điều kiện trở thành `true`; `console` tham chiếu tới chính đối tượng đó và gọi `send("ok")`.

Một số biểu thức cần phân biệt:

```java
Notifier value = null;

boolean noReference = (value == null);          // true
boolean hasNotifier = (value instanceof Notifier); // false
Notifier castValue = (Notifier) value;           // vẫn là null
```

Ép kiểu một tham chiếu `null` sang interface là hợp lệ và **không tạo đối tượng**. Vì vậy `castValue.send("x")` vẫn gây `NullPointerException`. Ép kiểu chỉ yêu cầu/kiểm tra cách nhìn kiểu của một giá trị tham chiếu, không cung cấp instance khi giá trị là `null`.

## 8. Một số nhầm lẫn thường gặp với `equals`, `toString` và method reference

### Kiểm tra null bằng cách gọi phương thức trên chính biến

Cách sau không an toàn:

```java
Notifier notifier = null;
// notifier.equals(null);  // Gây NullPointerException khi chạy
// notifier.toString();    // Gây NullPointerException khi chạy
```

Để kiểm tra null, dùng `notifier == null` hoặc `notifier != null`. Nếu mục đích là so sánh hai giá trị có thể null, `java.util.Objects.equals(a, b)` có thể hữu ích, vì phương thức tĩnh này xử lý `null` theo hợp đồng của nó.

Ví dụ:

```java
String a = null;
System.out.println(java.util.Objects.equals(a, null)); // true
System.out.println("ok".equals(a));                    // false
```

Ở dòng thứ hai, receiver là chuỗi literal `"ok"` vốn không null, nên lời gọi an toàn. Đảo lại thành `a.equals("ok")` sẽ gây `NullPointerException`.

### Method reference gắn vào đối tượng và lambda có thể khác thời điểm lỗi

Xét interface có phương thức `send(String)` như mục 3:

```java
Notifier missing = null;

// Biểu thức method reference bị ràng buộc vào receiver null:
// java.util.function.Consumer<String> direct = missing::send;

// Lambda chỉ cố gọi receiver khi được thực thi:
// java.util.function.Consumer<String> delayed = text -> missing.send(text);
```

Dòng `missing::send` ở đây được comment để tránh dừng chương trình: với **bound instance method reference**, biểu thức method reference cần receiver và sẽ gây `NullPointerException` **ngay khi đánh giá biểu thức** nếu receiver là `null`. Với lambda `text -> missing.send(text)`, việc tạo lambda không tự gọi phương thức; lỗi xảy ra **khi lambda được thực thi** (nếu `missing` vẫn là `null` lúc đó).

Hai cách viết trông tương tự nhưng có thời điểm sử dụng receiver khác nhau. Khi phân tích NPE, cần xác định **biểu thức nào** đã cố dùng receiver, không chỉ xem kiểu khai báo interface.

## 9. Thứ tự đánh giá biểu thức: tham số có thể chạy trước khi NPE xuất hiện

Một chi tiết Java đáng chú ý: trong lời gọi phương thức instance, biểu thức receiver được đánh giá, sau đó các biểu thức đối số được đánh giá theo thứ tự trái sang phải. Nếu receiver được đánh giá ra `null`, ngoại lệ thường được phát hiện **sau khi các đối số đã được đánh giá**, ngay trước khi thực hiện lời gọi.

Lưu ví dụ độc lập vào **`ArgumentOrderDemo.java`**:

```java
interface Task {
    void execute(int number);
}

public class ArgumentOrderDemo {
    static int argument() {
        System.out.println("Evaluating argument");
        return 5;
    }

    public static void main(String[] args) {
        Task task = null;

        try {
            task.execute(argument());
        } catch (NullPointerException e) {
            System.out.println("NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ArgumentOrderDemo.java
java ArgumentOrderDemo
```

Kết quả:

```text
Evaluating argument
NullPointerException
```

`argument()` đã được gọi và in ra thông báo, nhưng **`Task.execute` không được thực hiện**, vì đối tượng đích không tồn tại. Điều này quan trọng nếu biểu thức đối số có hiệu ứng phụ, chẳng hạn ghi log hoặc thay đổi trạng thái.

Không nên dựa vào ngoại lệ như một cơ chế điều khiển luồng để “bảo vệ” tác dụng phụ. Nếu null có thể xuất hiện, hãy kiểm tra hoặc xác thực receiver **trước** khi chuẩn bị các đối số có chi phí hay hiệu ứng phụ đáng kể.

## 10. Khi nào `NullPointerException` xuất hiện và khi nào không?

| Tình huống | Biên dịch | Khi chạy |
| --- | --- | --- |
| `Notifier n = null;` | Hợp lệ | Chỉ gán giá trị, không có NPE |
| `Notifier n = new ConsoleNotifier();` | Hợp lệ | Tạo đối tượng thật |
| `n.send("x")` khi `n` chứa đối tượng | Hợp lệ | Dispatch đến cài đặt phù hợp |
| `n.send("x")` khi `n == null` | Hợp lệ | Ném `NullPointerException` |
| `n.ping()` khi `n == null` | Hợp lệ nếu có `default ping()` | Vẫn ném `NullPointerException` |
| `n == null` | Hợp lệ | Trả về `true` hoặc `false` |
| `n instanceof Notifier` khi `n == null` | Hợp lệ | Trả về `false` |
| `(Notifier) null` | Hợp lệ | Kết quả là `null`, chưa có NPE |
| `new Notifier()` | Không hợp lệ | Không chạy |
| `Notifier.category()` với `category()` static | Hợp lệ | Chạy phương thức static theo tên interface |
| `n.category()` với `category()` static trong interface | Không hợp lệ | Không chạy |

Nếu chương trình ném `NullPointerException` ở `n.send("x")`, điều cần tìm là **vì sao `n` đang là null tại điểm gọi**. Trình biên dịch không đảm bảo đối tượng hợp lệ chỉ vì phương thức có trong interface.

## 11. Thiết kế API nhận hoặc trả về interface để tránh lỗi null

Một interface giúp code giảm phụ thuộc vào lớp triển khai, nhưng bản thân nó không bảo đảm giá trị luôn tồn tại. Nên xác lập hợp đồng cụ thể:

1. **Đầu vào bắt buộc:** xác thực sớm bằng `Objects.requireNonNull`, hướng dẫn nơi gọi truyền đối tượng hợp lệ và kiểm thử trường hợp null để API thất bại rõ ràng.
2. **Đầu vào tùy chọn:** tài liệu hóa ý nghĩa của null, kiểm tra trước khi gọi hoặc cung cấp giá trị dự phòng. Tránh bỏ qua âm thầm nếu thiếu dependency là lỗi cấu hình.
3. **Kết quả có thể không tồn tại:** có thể trả `null` nếu hợp đồng quy định rõ, hoặc cân nhắc `Optional<Notifier>` đối với **giá trị trả về** khi nó giúp diễn tả trạng thái vắng mặt. Tránh tạo `Optional` chỉ để che đi thiết kế chưa rõ ràng.
4. **Không dùng `instanceof` làm kiểm tra null bắt buộc:** `instanceof` trả false với null nhưng còn có ý nghĩa kiểm tra kiểu thực tế; nếu chỉ hỏi có đối tượng không, `!= null` rõ ràng hơn.
5. **Không bắt NPE để thay cho kiểm tra dữ liệu:** NPE có thể bắt nguồn từ **bất kỳ thao tác dereference null nào** bên trong lời gọi phức tạp, nên bắt quá rộng có thể che mất lỗi khác.
6. **Dùng phương thức static qua tên interface:** `Notifier.category()` khác cơ chế với `notifier.send(...)`. Một bên không cần instance, một bên cần.
7. **Ghi rõ trạng thái hợp lệ trong kiểm thử:** ít nhất có ca truyền lớp triển khai hợp lệ, ca truyền null nếu được cho phép, và ca null bị từ chối nếu API yêu cầu tham chiếu bắt buộc.

Một cách thiết kế dễ bảo trì là yêu cầu dependency bắt buộc ngay tại constructor của đối tượng sử dụng nó, thay vì để một field kiểu interface ở trạng thái null rồi chờ khi có lời gọi mới phát hiện lỗi. Ví dụ:

```java
import java.util.Objects;

final class NotificationService {
    private final Notifier notifier;

    NotificationService(Notifier notifier) {
        this.notifier = Objects.requireNonNull(notifier, "notifier");
    }

    void notifyUser() {
        notifier.send("welcome");
    }
}
```

Đoạn code trên cần đặt trong cùng môi trường có khai báo `Notifier` ở mục 3. Nó bảo đảm constructor của `NotificationService` **từ chối null ngay lúc tạo**. Sau khi tạo thành công và nếu field không bị thay đổi bằng cơ chế bên ngoài bất thường, các phương thức của service có thể dùng `notifier` mà không cần kiểm tra null lặp lại.

## 12. Lỗi phổ biến khi làm việc với interface reference

| Lỗi hoặc ngộ nhận | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Biến kiểu interface có phương thức `send`, nên gọi được kể cả khi null” | Kiểu hợp lệ lúc biên dịch không bảo đảm có đối tượng đích | Kiểm tra hợp đồng và xác thực tham chiếu trước khi gọi |
| “Interface có `default`, Java sẽ tự chạy nó cho null” | `default` vẫn là instance method cần receiver | Chỉ gọi qua đối tượng hợp lệ |
| “`null` là đối tượng của interface” | `null` không phải instance của kiểu nào | Dùng `== null`, không gán cho nó hành vi hay runtime class |
| “Ép `(Notifier) null` sẽ tạo `Notifier`” | Cast không tạo instance | Dùng `new LớpTriểnKhai()` khi cần đối tượng |
| “`instanceof Notifier` sẽ true nếu biến được khai báo `Notifier`” | `instanceof` xét đối tượng tại runtime; null cho false | Kiểm tra bằng giá trị thực tế và mục đích |
| “Bắt NPE là cách chuẩn để phát hiện thiếu notifier” | Có thể che giấu lỗi xuất phát từ vị trí khác | Xác thực `null` trước khi dispatch hoặc theo hợp đồng API |
| “Truy cập `static` của interface cần biến khác null” | Thành viên static thuộc về interface | Dùng cú pháp `TênInterface.thànhViên` |
| “Sau `first = null`, mọi biến từng trỏ đến đối tượng cũng null” | Gán biến chỉ đổi một tham chiếu | Theo dõi từng biến tham chiếu độc lập |
| “Lỗi NPE luôn xảy ra trước khi đánh giá đối số” | Lời gọi instance có thứ tự đánh giá xác định | Kiểm tra receiver trước khi chuẩn bị đối số có hiệu ứng phụ |

## 13. Bài tập tự kiểm tra

**Bài 1 — dự đoán kết quả.** Với `Notifier` của mục 3:

```java
Notifier notifier = null;
System.out.println(notifier == null);
System.out.println(notifier instanceof Notifier);
System.out.println(Notifier.category());
```

Kết quả là gì? Tại sao không có NPE? **Đáp án:** In lần lượt `true`, `false`, `notification`. Không có dòng nào gọi instance method qua `notifier`.

**Bài 2 — giải thích lỗi.**

```java
Notifier notifier = null;
notifier.ping();
```

Đây là lỗi biên dịch hay lỗi lúc chạy? Có thay đổi gì nếu `ping()` là phương thức `default`? **Đáp án:** Mã biên dịch hợp lệ; lúc chạy ném `NullPointerException`. `default` cung cấp phần thân mặc định cho **instance method**, không làm null trở thành receiver hợp lệ.

**Bài 3 — giữ đúng hành vi.** Viết phương thức `sendIfAvailable(Notifier notifier, String text)` theo hợp đồng: nếu `notifier == null`, bỏ qua; nếu khác null, gọi `send(text)` đúng một lần. Sau đó viết `sendRequired(...)` để từ chối null bằng `Objects.requireNonNull`.

Một cách giải:

```java
static void sendIfAvailable(Notifier notifier, String text) {
    if (notifier != null) {
        notifier.send(text);
    }
}

static void sendRequired(Notifier notifier, String text) {
    java.util.Objects.requireNonNull(notifier, "notifier").send(text);
}
```

Hai phương thức này là đoạn để đặt **trong một class** có thể sử dụng `Notifier`. Chọn phiên bản nào dựa trên hợp đồng; không thể chỉ nhìn chữ ký `Notifier` mà suy ra null có hợp lệ hay không.

**Bài 4 — đa hình và thay đổi tham chiếu.** Dự đoán kết quả:

```java
Notifier one = new ConsoleNotifier();
Notifier two = one;
one = null;
two.send("A");
```

**Đáp án:** In `Console: A`. Hai biến từng trỏ tới cùng đối tượng, và chỉ `one` được gán lại `null`. `two` vẫn giữ tham chiếu tới `ConsoleNotifier`.

### Điều cần nhớ

- Biến kiểu interface có thể chứa **đối tượng triển khai hoặc `null`**.
- Kiểu interface cho phép trình biên dịch kiểm tra phương thức; **đa hình** chọn phần cài đặt từ đối tượng thực tế. Với `null`, **không có đối tượng để dispatch**, nên lời gọi instance gây `NullPointerException`.
- Phương thức `default` vẫn cần instance; trường và phương thức `static` của interface dùng qua **tên interface**.
- `null instanceof Interface` luôn cho `false`; ép kiểu `null` không tạo đối tượng.
- Xử lý null theo **hợp đồng API**: bỏ qua có chủ ý, dùng đối tượng dự phòng hoặc từ chối sớm. Không dùng `catch (NullPointerException)` làm phương thức kiểm tra null mặc định.