# `getMessage()`, `getLocalizedMessage()` và `toString()` của đối tượng `Throwable` trong Java

Khi một ngoại lệ xuất hiện trong Java, ba phương thức của `Throwable` thường được dùng để giải thích lỗi: `getMessage()`, `getLocalizedMessage()` và `toString()`. Chúng liên quan nhau nhưng **không đồng nghĩa**, và không phương thức nào tự trả về toàn bộ stack trace.

- **`getMessage()`** trả **thông điệp chi tiết** (detail message) của đối tượng ngoại lệ, kiểu `String`; kết quả có thể là `null`.
- **`getLocalizedMessage()`** được thiết kế để hỗ trợ **thông điệp bản địa hóa**. Với triển khai mặc định của `Throwable`, nó chỉ gọi `getMessage()`, nên **không có dịch ngôn ngữ tự động**.
- **`toString()`** trong triển khai mặc định của `Throwable` tạo **mô tả ngắn có tên lớp ngoại lệ**, thường là `tên-lớp: thông-điệp-localized`. Nếu localized message là `null`, nó chỉ trả về tên lớp.

Bài này giải thích chính xác ý nghĩa, giá trị trả về, cách các phương thức tương tác khi kế thừa/override, khác biệt giữa message và cause/stack trace, và cách dùng trong log, ứng dụng nhiều ngôn ngữ và xử lý exception. Các ví dụ hoàn chỉnh ưu tiên Java 17 trở lên.

## 1. `Throwable` là lớp nền của đối tượng ngoại lệ

Hệ phân cấp Java có dạng rút gọn:

```text
java.lang.Throwable
├── java.lang.Error
│   └── ...
└── java.lang.Exception
    ├── java.io.IOException
    └── java.lang.RuntimeException
        ├── java.lang.IllegalArgumentException
        └── ...
```

Mọi ngoại lệ và lỗi có thể ném theo hệ thống exception Java đều thuộc nhánh `Throwable`. Vì vậy ba phương thức đang học xuất hiện trong những lớp con như `IOException`, `IllegalArgumentException` hoặc `IllegalStateException`.

Một đối tượng `Throwable` còn có những dữ liệu và phương thức quan trọng khác:

| Thành phần | Trả lời câu hỏi |
| --- | --- |
| `getClass()` | Đối tượng có loại runtime thực tế nào? |
| `getMessage()` | Thông điệp chi tiết của lỗi là gì? |
| `getLocalizedMessage()` | Có thông điệp bản địa hóa cho lỗi không? |
| `toString()` | Mô tả ngắn gồm loại lỗi và localized message là gì? |
| `getCause()` | Ngoại lệ nguyên nhân được gắn với lỗi hiện tại là gì? |
| `getSuppressed()` | Những ngoại lệ phụ nào được giữ lại, chẳng hạn khi cleanup? |
| `getStackTrace()` | Những stack frame nào đã được ghi cho ngoại lệ? |
| `printStackTrace()` | Làm thế nào in stack trace và các quan hệ cause/suppressed? |

**Một message không phải một exception.** Message chỉ là dữ liệu `String` mô tả lỗi. Đối tượng ngoại lệ còn có kiểu, quan hệ nguyên nhân, stack trace, suppressed exception và các đặc điểm khác.

## 2. `getMessage()`: thông điệp chi tiết

`Throwable.getMessage()` có dạng khái niệm:

```java
public String getMessage()
```

Phương thức trả về chuỗi chi tiết gắn với exception. Nhiều constructor cho phép bạn truyền message:

```java
IllegalArgumentException error =
        new IllegalArgumentException("Số lượng phải dương");

String message = error.getMessage();
// message == "Số lượng phải dương"
```

Đây là **đoạn mã minh họa**, không phải chương trình độc lập. Thông điệp thông thường được giữ tại thời điểm tạo đối tượng, nhưng những lớp con có thể override `getMessage()` với hành vi riêng. Vì vậy không nên coi mọi lớp con đều có cùng cách xây dựng message bên trong.

Message thường nên trả lời: thao tác nào vi phạm hợp đồng, tham số/trạng thái nào không hợp lệ, hoặc chuyện gì thất bại. Ví dụ:

```java
throw new IllegalArgumentException(
        "quantity phải lớn hơn 0: " + quantity);
```

Đây là **câu lệnh minh họa** trong phạm vi có biến `quantity`. Một thông điệp có ngữ cảnh hữu ích hơn các message quá chung như `"error"`, nhưng tuyệt đối tránh ghép mật khẩu, token, dữ liệu cá nhân hoặc nội dung nhạy cảm vào thông điệp.

**Quan trọng:** `getMessage()` có thể trả `null`, đặc biệt khi object được tạo bằng constructor không cung cấp detail message. Kết quả `null` không có nghĩa “không xảy ra lỗi”; đối tượng ngoại lệ vẫn tồn tại.

## 3. `getLocalizedMessage()`: không phải API dịch tự động

`Throwable.getLocalizedMessage()` cũng có kiểu trả về `String`:

```java
public String getLocalizedMessage()
```

Trong triển khai mặc định của `Throwable`, phương thức này **trả về kết quả của `getMessage()`**. Java không tự lấy câu tiếng Anh rồi dịch sang tiếng Việt dựa trên `Locale.getDefault()`.

Ví dụ, nếu tạo:

```java
Exception e = new Exception("Connection failed");
```

thì theo triển khai mặc định của `Throwable`:

- `e.getMessage()` là `"Connection failed"`.
- `e.getLocalizedMessage()` cũng là `"Connection failed"`, bất kể bạn mong giao diện bằng tiếng Việt.
- Muốn trả một chuỗi đã được địa phương hóa theo ngôn ngữ, một **lớp con cần chủ động override** phương thức hoặc một tầng hiển thị cần dịch thông qua cơ chế như `ResourceBundle`.

Điểm tinh tế: khi lớp con override `getMessage()` nhưng không override `getLocalizedMessage()`, triển khai mặc định `getLocalizedMessage()` gọi `getMessage()` theo cơ chế đa hình Java, nên phản ánh giá trị từ override đó. Khi lớp con override riêng `getLocalizedMessage()`, hai phương thức có thể trả hai chuỗi **khác nhau**.

Việc bản địa hóa là **hợp đồng do class/thư viện thiết kế**, không thể suy ra chỉ từ tên `getLocalizedMessage` rằng exception nào cũng được dịch.

## 4. `toString()`: tên lớp kèm thông điệp localized

Theo triển khai chuẩn của `Throwable`, kết quả `toString()` được hình thành từ:

1. **Tên lớp runtime đầy đủ** của đối tượng, tức `getClass().getName()`.
2. Nếu `getLocalizedMessage()` khác `null`, nối `": "` và localized message.
3. Nếu localized message là `null`, chỉ trả tên lớp.

Có thể hình dung logic (đây là **mã minh họa**, không phải đoạn cài đặt thư viện cần sao chép):

```java
String className = getClass().getName();
String localized = getLocalizedMessage();
return localized == null
        ? className
        : className + ": " + localized;
```

Ví dụ `IllegalArgumentException` nằm ở gói `java.lang`:

```java
IllegalArgumentException e =
        new IllegalArgumentException("Sai tham số");

System.out.println(e.getMessage());
// Sai tham số

System.out.println(e.toString());
// java.lang.IllegalArgumentException: Sai tham số
```

Đây là **các câu lệnh minh họa** trong một phương thức, không chứa `main`. Khi truyền trực tiếp một exception vào `System.out.println(e)`, Java gọi cơ chế chuyển object thành chuỗi, thường dùng `toString()`.

**Không nhầm tên lớp trong `toString()` với `getClass().getSimpleName()`.** `Throwable.toString()` dùng tên trả về từ `getClass().getName()` theo triển khai chuẩn, thường gồm package. Với nested class, tên nhị phân có thể có ký tự `$`; với class nằm trong package, tên package cũng xuất hiện.

Nếu **lớp con override `toString()`** thì kết quả có thể khác công thức mặc định. Những ví dụ và quy tắc trong bài nói đến triển khai mặc định của `Throwable` trừ khi ghi rõ override.

## 5. Ví dụ đầy đủ: so sánh ba phương thức và message `null`

Lưu chương trình thành **`ThrowableMessagesDemo.java`**:

```java
public class ThrowableMessagesDemo {
    public static void main(String[] args) {
        Throwable withMessage =
                new IllegalArgumentException("Số lượng phải dương");

        System.out.println("message: " + withMessage.getMessage());
        System.out.println("localized: "
                + withMessage.getLocalizedMessage());
        System.out.println("toString: " + withMessage.toString());

        Throwable noMessage = new IllegalArgumentException();

        System.out.println("null message: "
                + (noMessage.getMessage() == null));
        System.out.println("null localized: "
                + (noMessage.getLocalizedMessage() == null));
        System.out.println("toString null: " + noMessage.toString());
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 ThrowableMessagesDemo.java
java ThrowableMessagesDemo
```

**Stdout chính xác** trên console UTF-8:

```text
message: Số lượng phải dương
localized: Số lượng phải dương
toString: java.lang.IllegalArgumentException: Số lượng phải dương
null message: true
null localized: true
toString null: java.lang.IllegalArgumentException
```

Giải thích: hai object cùng loại runtime `IllegalArgumentException` nhưng khác detail message. Khi có message, `toString()` ghép tên lớp và message; khi message `null`, phiên bản mặc định chỉ trả tên lớp. Cả hai vẫn là đối tượng ngoại lệ thực sự.

Đây cũng là lý do không được mặc định gọi `e.getMessage().length()` mà không xét `null`: chính phương thức quan sát message có thể khiến chương trình gặp một `NullPointerException` mới nếu code dereference kết quả `null`.

## 6. Phân biệt thông điệp `null` và chuỗi rỗng

`null` và `""` là hai giá trị khác nhau:

- **`null`**: không có đối tượng `String` detail message.
- **`""`**: có chuỗi `String` nhưng độ dài bằng 0.

Trong triển khai chuẩn, `Throwable.toString()` kiểm tra **`localizedMessage == null`**, không kiểm tra chuỗi có rỗng hay không. Vì vậy nếu message là `""`, kết quả vẫn chứa dấu `": "` dù không có ký tự nào phía sau.

Lưu **`EmptyMessageDemo.java`**:

```java
public class EmptyMessageDemo {
    public static void main(String[] args) {
        Throwable noMessage = new IllegalStateException();
        Throwable emptyMessage = new IllegalStateException("");

        System.out.println("Null? "
                + (noMessage.getMessage() == null));
        System.out.println("Empty? "
                + emptyMessage.getMessage().isEmpty());
        System.out.println("Null toString: " + noMessage);
        System.out.println("Empty suffix: "
                + emptyMessage.toString().endsWith(": "));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 EmptyMessageDemo.java
java EmptyMessageDemo
```

**Stdout chính xác:**

```text
Null? true
Empty? true
Null toString: java.lang.IllegalStateException
Empty suffix: true
```

Dòng cuối dùng `endsWith(": ")` thay vì in trực tiếp một dấu cách cuối dòng khó nhìn thấy. Cách đó xác nhận chính xác công thức của `toString()` với chuỗi rỗng.

Khi thiết kế API, nên phân biệt “không có message” với “message được cung cấp nhưng rỗng” nếu hợp đồng cần. Khi hiển thị cho người dùng, cả hai trường hợp thường cần một fallback được định nghĩa rõ.

## 7. Bảng so sánh nhanh

| Câu hỏi | `getMessage()` | `getLocalizedMessage()` | `toString()` |
| --- | --- | --- | --- |
| Kiểu trả về | `String` | `String` | `String` |
| Nội dung mặc định | Detail message | Gọi `getMessage()` | Tên lớp, tùy chọn cộng `": "` và localized message |
| Có thể trả `null`? | Có | Có | Với triển khai chuẩn `Throwable`, không |
| Tự gồm tên lớp exception? | Không theo mặc định | Không theo mặc định | Có |
| Tự cung cấp stack frames? | Không | Không | Không |
| Tự gồm nguyên nhân `getCause()`? | Không nói chung | Không nói chung | Không nói chung |
| Có tự dịch theo `Locale`? | Không | Không theo mặc định | Không; dùng localized message hiện có |
| Có thể thay đổi do subclass override? | Có | Có | Có |
| Phù hợp cho | Message kỹ thuật theo hợp đồng | Message bản địa hóa khi class hỗ trợ | Mô tả ngắn để nhận diện loại và thông điệp |

Bảng mô tả **hành vi mặc định**, không cam kết mọi subclass tự viết lại ba phương thức đều giữ đúng công thức đó. Khi dùng một exception từ thư viện bên thứ ba, hãy đọc tài liệu API nếu cần chính xác tuyệt đối về message.

## 8. Bản địa hóa thật sự: override `getLocalizedMessage()`

Một lớp ngoại lệ tùy chỉnh có thể giữ **thông điệp kỹ thuật ổn định** qua `getMessage()`, đồng thời trả thông điệp tiếng Việt hoặc tiếng Anh qua `getLocalizedMessage()`.

Lưu thành **`LocalizedMessageDemo.java`**. Tệp có một lớp `public` chứa `main` và một lớp package-private cùng tệp:

```java
import java.util.Locale;

class LocalizedProblem extends Exception {
    private final Locale locale;

    LocalizedProblem(Locale locale) {
        super("Missing configuration");
        this.locale = locale;
    }

    @Override
    public String getLocalizedMessage() {
        if ("vi".equals(locale.getLanguage())) {
            return "Thiếu cấu hình";
        }
        return getMessage();
    }
}

public class LocalizedMessageDemo {
    public static void main(String[] args) {
        LocalizedProblem vi =
                new LocalizedProblem(Locale.forLanguageTag("vi-VN"));
        LocalizedProblem en =
                new LocalizedProblem(Locale.ENGLISH);

        System.out.println("VI message: " + vi.getMessage());
        System.out.println("VI localized: " + vi.getLocalizedMessage());
        System.out.println("VI toString: " + vi.toString());
        System.out.println("EN localized: " + en.getLocalizedMessage());
        System.out.println("EN toString: " + en.toString());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 LocalizedMessageDemo.java
java LocalizedMessageDemo
```

**Stdout chính xác:**

```text
VI message: Missing configuration
VI localized: Thiếu cấu hình
VI toString: LocalizedProblem: Thiếu cấu hình
EN localized: Missing configuration
EN toString: LocalizedProblem: Missing configuration
```

Điểm nổi bật:

- `super("Missing configuration")` thiết lập message kỹ thuật của exception.
- `getMessage()` không bị override nên vẫn trả `"Missing configuration"`.
- `getLocalizedMessage()` được override và chọn thông điệp từ `Locale` được truyền vào constructor.
- **`toString()` mặc định gọi `getLocalizedMessage()`**, nên cùng một lớp có thể tạo mô tả tiếng Việt hoặc tiếng Anh tùy object.
- `LocalizedProblem` nằm ở default package, vì thế tên lớp trong output là `LocalizedProblem`. Nếu đặt vào package `com.example` thì `toString()` mặc định sẽ thêm tên package.

Bài này dùng điều kiện `if` đơn giản để output dễ xác minh. Ứng dụng nhiều ngôn ngữ thực sự thường cần **message key**, `ResourceBundle` hoặc hệ thống quản lý bản dịch, fallback theo ngôn ngữ và chính sách tham số hóa thay vì hard-code các chuỗi trong lớp ngoại lệ.

## 9. Khi nào nên dùng `ResourceBundle`?

`ResourceBundle` hỗ trợ tìm chuỗi theo `Locale` từ tập tài nguyên được quản lý riêng. Một hướng thiết kế có thể là:

```java
// Minh họa ý tưởng trong một phương thức.
String template = bundle.getString("error.config.missing");
String localized = String.format(locale, template, configName);
```

Đây là **đoạn minh họa**, giả định `bundle`, `locale` và `configName` đã được định nghĩa. Không có tệp bản dịch kèm theo nên không coi đây là chương trình chạy độc lập.

Một lựa chọn khác là giữ exception chỉ chứa **mã lỗi ổn định và tham số có cấu trúc**, rồi để tầng giao diện sử dụng `ResourceBundle` để hiển thị theo ngôn ngữ của người dùng. Cách này hữu ích trong web server có nhiều request với ngôn ngữ khác nhau: exception kỹ thuật không buộc phải quyết định ngôn ngữ hiển thị cuối cùng.

Cần chú ý:

1. **Không dựa vào `Locale.getDefault()` toàn cục cho mọi request** nếu mỗi request có locale riêng; thay đổi locale toàn cục có thể làm các request ảnh hưởng nhau.
2. Nếu lưu `Locale` trong exception, hãy cân nhắc exception được tạo ở tầng nào và ai quyết định ngôn ngữ.
3. Thông điệp hiển thị cho người dùng cần được rà soát về tính dễ hiểu và an toàn, không chỉ được dịch.
4. Message kỹ thuật ở log và localized message cho giao diện có thể khác nhau một cách có chủ đích.
5. Không phân tích chương trình bằng cách so khớp văn bản bản dịch vì ngôn ngữ và câu chữ có thể thay đổi.

**`getLocalizedMessage()` là điểm mở rộng có sẵn, không bắt buộc mọi ứng dụng phải override nó.** Nếu API của bạn tách dịch thuật khỏi exception, điều đó vẫn có thể là thiết kế tốt.

## 10. Kế thừa và override: thứ tự lời gọi có ý nghĩa

Theo mã chuẩn của `Throwable`:

```text
getMessage()
      ▲
      │ mặc định
getLocalizedMessage()
      ▲
      │ được gọi trong công thức mặc định
toString()
```

Sơ đồ này mô tả **quan hệ lời gọi trong triển khai mặc định**, không phải quan hệ kế thừa của các lớp.

Các trường hợp:

- **Không override gì**: `getLocalizedMessage()` bằng `getMessage()`; `toString()` ghép tên lớp với localized message nếu khác `null`.
- **Override `getMessage()` nhưng không override `getLocalizedMessage()`**: localized message mặc định thường phản ánh giá trị mới từ `getMessage()`.
- **Override `getLocalizedMessage()`**: `toString()` mặc định dùng localized message mới, kể cả khi nó khác detail message kỹ thuật.
- **Override `toString()`**: định dạng chuỗi có thể thay đổi hoàn toàn; code khác không nên giả định công thức mặc định còn áp dụng.
- **Override `getLocalizedMessage()` trả `null`**: `toString()` mặc định trả tên lớp, ngay cả khi `getMessage()` khác `null`.

Có thể xác minh trường hợp cuối bằng lớp tùy chỉnh, nhưng cần tránh override các phương thức chỉ để che lỗi khi không có lý do thiết kế rõ. Một exception có message kỹ thuật tốt mà `toString()` lại bỏ message có thể khiến log thiếu thông tin.

Một điểm kỹ thuật quan trọng: `toString()` và `getLocalizedMessage()` là phương thức có thể được gọi từ code log hoặc từ nơi xây dựng thông báo lỗi. Vì thế override nên **đơn giản, không ném lỗi mới và không làm I/O nặng**. Nếu quá trình dịch thuật thất bại ngay trong lúc chẩn đoán một exception khác, chương trình có thể mất thêm thông tin quan trọng.

## 11. `getCause()` không nằm tự động trong `getMessage()`

Một exception có thể **bọc một nguyên nhân** (cause). Điều đó không có nghĩa message của exception ngoài sẽ tự kết hợp mọi message trong chuỗi cause. Ví dụ:

```java
IOException original = new IOException("Không đọc được tệp");
IllegalStateException wrapper =
        new IllegalStateException("Không thể khởi tạo", original);
```

Đây là các khai báo minh họa, cần import `java.io.IOException`. Với constructor `IllegalStateException(String, Throwable)`:

- `wrapper.getMessage()` là `"Không thể khởi tạo"`.
- `wrapper.getCause()` trỏ tới `original`.
- `wrapper.toString()` theo mặc định là `"java.lang.IllegalStateException: Không thể khởi tạo"`.
- `original.getMessage()` là `"Không đọc được tệp"`.

Thông điệp của wrapper và nguyên nhân là **hai dữ liệu khác nhau**. Muốn giải thích đầy đủ cần xem `getCause()` hoặc in/thu thập stack trace có cấu trúc. Cũng không nên bọc lỗi bằng `new RuntimeException(e.getMessage())` nếu mục tiêu bảo toàn nguyên nhân; cách đó không truyền object gốc làm cause.

## 12. Ví dụ đầy đủ: cause và message của wrapper

Lưu thành **`CauseAndMessageDemo.java`**:

```java
import java.io.IOException;

public class CauseAndMessageDemo {
    public static void main(String[] args) {
        IOException root =
                new IOException("Không đọc được tệp");
        IllegalStateException wrapper =
                new IllegalStateException("Không thể khởi tạo", root);

        System.out.println("Wrapper message: "
                + wrapper.getMessage());
        System.out.println("Wrapper localized: "
                + wrapper.getLocalizedMessage());
        System.out.println("Wrapper toString: "
                + wrapper.toString());
        System.out.println("Cause type: "
                + wrapper.getCause().getClass().getSimpleName());
        System.out.println("Cause message: "
                + wrapper.getCause().getMessage());

        RuntimeException derived = new RuntimeException(root);
        System.out.println("Cause-only constructor: "
                + derived.getMessage().equals(root.toString()));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 CauseAndMessageDemo.java
java CauseAndMessageDemo
```

**Stdout chính xác:**

```text
Wrapper message: Không thể khởi tạo
Wrapper localized: Không thể khởi tạo
Wrapper toString: java.lang.IllegalStateException: Không thể khởi tạo
Cause type: IOException
Cause message: Không đọc được tệp
Cause-only constructor: true
```

Dòng cuối minh họa một **biến thể constructor quan trọng**: `new RuntimeException(root)` sử dụng `root.toString()` làm detail message của exception mới (khi cause khác `null`). Vì vậy đôi khi message của wrapper **có chứa tên loại và message của cause**, nhưng đó là hành vi constructor cụ thể, **không phải** vì `getMessage()` tự duyệt mọi cause.

So sánh:

| Constructor | Message của wrapper |
| --- | --- |
| `new RuntimeException("Tầng dịch vụ thất bại", cause)` | Chuỗi được truyền: `"Tầng dịch vụ thất bại"` |
| `new RuntimeException(cause)` | `cause.toString()`, nếu cause khác `null` |
| `new RuntimeException()` | Thường là `null` theo constructor mặc định |
| `new RuntimeException("Tầng dịch vụ thất bại")` | Chuỗi được truyền, không có cause tự động |

Khi thiết kế API, thường hữu ích hơn nếu truyền **message ở tầng hiện tại cùng cause** qua constructor `(String, Throwable)`: vừa diễn đạt thao tác đang thất bại, vừa giữ object nguyên nhân cho chẩn đoán.

## 13. `getSuppressed()` là danh sách lỗi phụ, không phải phần của message

Từ Java 7, `Throwable` có thể giữ các **suppressed exceptions**, thường xuất hiện khi một lỗi trong thân `try-with-resources` đã xảy ra, sau đó `close()` cũng thất bại. Những lỗi này không tự động được nối vào `getMessage()` hoặc `toString()` của exception chính.

Ví dụ, lưu **`SuppressedMessageDemo.java`**:

```java
public class SuppressedMessageDemo {
    public static void main(String[] args) {
        IllegalStateException main =
                new IllegalStateException("Lỗi xử lý");
        main.addSuppressed(
                new IllegalArgumentException("Lỗi cleanup"));

        System.out.println("Message: " + main.getMessage());
        System.out.println("toString: " + main.toString());
        System.out.println("Số suppressed: "
                + main.getSuppressed().length);
        System.out.println("Suppressed message: "
                + main.getSuppressed()[0].getMessage());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 SuppressedMessageDemo.java
java SuppressedMessageDemo
```

**Stdout chính xác:**

```text
Message: Lỗi xử lý
toString: java.lang.IllegalStateException: Lỗi xử lý
Số suppressed: 1
Suppressed message: Lỗi cleanup
```

Thông điệp `"Lỗi cleanup"` chỉ xuất hiện khi đọc trực tiếp `getSuppressed()[0].getMessage()`; `main.getMessage()` và `main.toString()` không tự liệt kê nó. Khi viết logging có cấu trúc, đừng chỉ lưu một chuỗi `e.toString()` rồi cho rằng đã giữ đủ cause và suppressed.

Ví dụ cố tình thêm một suppressed exception nên có đúng một phần tử; mã thực cần kiểm tra độ dài mảng, không mặc định mọi exception đều có suppressed.

## 14. `toString()` khác `printStackTrace()` như thế nào?

Đây là nhầm lẫn rất phổ biến:

- **`e.getMessage()`**: một `String` chi tiết, có thể `null`.
- **`e.getLocalizedMessage()`**: một `String` bản địa hóa nếu lớp hỗ trợ, có thể `null`.
- **`e.toString()`**: một `String` mô tả ngắn (theo mặc định: tên lớp và localized message).
- **`e.printStackTrace()`**: **thực hiện thao tác in** thông tin lỗi và stack trace; phương thức trả về `void`, không trả một chuỗi để bạn gán.

Theo mặc định, `printStackTrace()` không đối số in ra **standard error stream** (`System.err`), bao gồm dòng mô tả exception và các stack frames; nó cũng có thể trình bày cause và suppressed exceptions. Số dòng, đường dẫn, định dạng và thứ tự các frame có thể khác theo môi trường, cách build và JVM, nên không gắn một bản stdout cố định cho ví dụ in stack trace.

Ví dụ:

```java
try {
    throw new IllegalStateException("Lỗi xử lý");
} catch (IllegalStateException e) {
    System.out.println(e.toString()); // Một dòng trên stdout.
    e.printStackTrace();              // Nhiều dòng trên stderr.
}
```

Đây là **khối minh họa** có thể đặt trong `main`. Do stdout và stderr có thể được thu gom/hiển thị xen kẽ bởi terminal, thứ tự xuất hiện trên màn hình không phải hợp đồng đáng dùng để kiểm thử khi hai luồng được tách biệt.

Nếu muốn lấy trace thành một chuỗi cho mục đích đặc biệt, có thể in vào `StringWriter` thông qua `PrintWriter`, nhưng thư viện logging hiện đại thường cho phép truyền trực tiếp object `Throwable`, tốt hơn là tự định dạng stack trace bằng tay.

## 15. Vì sao log chỉ có `getMessage()` thường chưa đủ?

Giả sử hai loại exception khác nhau đều có cùng message `"invalid input"`. Nếu log chỉ ghi message, bạn không biết lỗi là `NumberFormatException`, `IllegalArgumentException` hay loại ứng dụng tùy chỉnh.

Ngược lại, log chỉ ghi `toString()` có tên loại nhưng vẫn **không có stack frames hoặc cause/suppressed**. Khi điều tra lỗi kỹ thuật, những dữ liệu đó thường quan trọng hơn một dòng mô tả.

Thông thường cần:

1. **Loại exception** và ngữ cảnh thao tác.
2. **Message** có nội dung đủ hữu ích, không lộ dữ liệu nhạy cảm.
3. **Stack trace** khi lỗi cần chẩn đoán đường gọi.
4. **Cause** khi ngoại lệ được wrapping giữa các tầng.
5. **Suppressed exceptions** nếu cleanup hoặc nhiều tài nguyên cũng thất bại.
6. **Mã tương quan/request ID hoặc mã lỗi ổn định**, thay vì suy diễn từ câu chữ tự do.

Ví dụ khung cho API logging có hỗ trợ `Throwable`:

```java
// Pseudocode, tùy API của thư viện logging đang dùng:
logger.error("Không thể xử lý request {}", requestId, e);
```

Đây là **pseudocode**, không phải ví dụ Java thuần chạy độc lập. Tùy thư viện và overload cụ thể, cách truyền `Throwable` có thể khác nhau; cần đọc API logging sử dụng thực tế.

**Không dùng message làm khóa logic nghiệp vụ**, ví dụ `if (e.getMessage().contains("not found"))`. Một thay đổi wording hoặc ngôn ngữ sẽ phá logic. Hãy dùng loại exception, error code có cấu trúc hoặc kiểu kết quả nghiệp vụ rõ ràng.

## 16. Dùng thông điệp với giao diện người dùng

Một message được viết cho lập trình viên có thể không phù hợp để hiển thị trực tiếp cho người dùng. Ví dụ:

```java
throw new IllegalStateException(
        "DB_CONN_02: connection pool exhausted, host=db.internal");
```

Đây là **câu lệnh minh họa**. Message chứa chi tiết hệ thống; đưa thẳng `e.getMessage()` vào giao diện có thể làm lộ thông tin triển khai. Ngay cả `e.getLocalizedMessage()` cũng không bảo đảm an toàn nếu lớp không được thiết kế cho giao diện người dùng.

Cách thiết kế là tách:

- **Thông tin kỹ thuật** cho quan sát và sửa lỗi: loại exception, message, stack trace, cause, suppressed.
- **Mã lỗi ổn định** để ứng dụng quyết định loại phản hồi, kiểm thử, API và quy trình hỗ trợ.
- **Thông điệp người dùng** được biên soạn và bản địa hóa theo locale của request hoặc người dùng, sau khi kiểm tra tính bảo mật.

Một số exception domain có thể mang `errorCode` và tham số riêng, thay vì bắt giao diện phân tích `toString()`. Khi API cần trả thông điệp cho người dùng, ưu tiên tầng có hiểu biết về locale, quyền hạn và ngữ cảnh thay vì mặc định expose toàn bộ chuỗi exception.

## 17. Trường hợp đặc biệt: message có thể được JVM tạo

Không phải mọi exception đều được tạo bằng constructor có message tường minh trong mã ứng dụng. Ví dụ, `NullPointerException` có thể được JVM phát sinh khi chương trình dereference `null`.

Trong các phiên bản JVM hiện đại, **một số `NullPointerException` do JVM phát sinh** có thể có thông điệp chẩn đoán chi tiết hơn (thường gọi *helpful NullPointerExceptions*) để chỉ ra biểu thức nào có giá trị `null`. Nhưng điều đó **phụ thuộc phiên bản và cấu hình JVM, cách lỗi được tạo**, không phải hợp đồng cố định cho mọi `NullPointerException`.

Vì vậy:

- Không suy luận rằng mọi `NullPointerException` đều có `getMessage() != null`.
- Không so sánh đúng nguyên văn message JVM như một “mã lỗi” ổn định.
- Không phụ thuộc vào tên biến và wording trong message để quyết định phục hồi.
- Khi cần thông điệp đặc thù cho tiền điều kiện API, hãy kiểm tra rõ ràng và đưa ra hợp đồng riêng.

Một lỗi có message `null` vẫn có loại exception và stack trace (tùy cơ chế tạo), nên các phương pháp chẩn đoán khác không phụ thuộc message vẫn có giá trị.

## 18. Override `toString()` có nên không?

Có thể override `toString()` trên một lớp exception tùy chỉnh vì đây là phương thức được kế thừa từ `Object` và `Throwable` đã cung cấp triển khai riêng. Tuy nhiên, việc đổi định dạng nên có lý do rõ ràng:

```java
class TaggedException extends RuntimeException {
    private final String code;

    TaggedException(String code, String message) {
        super(message);
        this.code = code;
    }

    @Override
    public String toString() {
        return code + ": " + getMessage();
    }
}
```

Đây là **lớp minh họa không có `main`**. Nếu tạo `new TaggedException("E100", "Thiếu cấu hình")`, `toString()` của class này trả `"E100: Thiếu cấu hình"` thay vì tên lớp runtime theo công thức của `Throwable`.

Đổi `toString()` có thể làm mất tên lớp trong các log hoặc header của stack trace; các công cụ giám sát có thể dựa vào cấu trúc cũ. Nếu mục tiêu là thêm mã lỗi, thường tốt hơn là giữ mã lỗi trong **field + getter** (`getCode()`) để hệ thống logging/response sử dụng có cấu trúc, còn `toString()` không bị tái định nghĩa quá xa hợp đồng mong đợi.

Tương tự, override `getLocalizedMessage()` không nên thực hiện I/O mạng hay truy cập môi trường có thể thất bại chỉ để dựng một chuỗi chẩn đoán. Nếu formatter ném thêm exception ngay khi đang xử lý lỗi ban đầu, quá trình quan sát sẽ trở nên khó tin cậy.

## 19. Những hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “`getMessage()` luôn trả về chuỗi.” | Nó trả kiểu `String` nhưng **có thể là `null`**. |
| “`getLocalizedMessage()` tự dịch theo ngôn ngữ hệ điều hành.” | Mặc định `Throwable` chỉ gọi `getMessage()`; phải có override/cơ chế bản địa hóa riêng. |
| “`getMessage()` và `toString()` giống nhau.” | Mặc định `toString()` thêm tên lớp runtime và dùng localized message. |
| “`toString()` luôn trả `getMessage()`.” | Với `Throwable` mặc định, `toString()` dùng **`getLocalizedMessage()`**. |
| “`toString()` có đầy đủ stack trace.” | Không; chỉ là mô tả ngắn. |
| “`getMessage()` luôn chứa thông tin cause.” | Không; cause là dữ liệu riêng, trừ các constructor/override cụ thể tự dựng message từ cause. |
| “`getSuppressed()` tự xuất hiện trong `toString()`.” | Không; danh sách suppressed nằm riêng và thường được thể hiện trong `printStackTrace()`. |
| “`printStackTrace()` trả String.” | Không, nó trả `void` và in thông tin ra stream. |
| “Message null nghĩa là exception vô hại.” | Không; loại lỗi và đường thực thi vẫn cần xử lý theo hợp đồng. |
| “Message rỗng giống message null đối với `toString()`.” | Không. Chuỗi rỗng vẫn làm `toString()` thêm `": "`. |
| “Có thể bắt lỗi bằng cách so nội dung message.” | Dễ hỏng do bản địa hóa, wording và phiên bản; dùng loại hoặc mã lỗi có cấu trúc. |
| “`getLocalizedMessage()` chắc chắn dùng được cho người dùng cuối.” | Không; thông điệp có thể chứa chi tiết nội bộ và có thể không được dịch. |
| “Tên lớp trong `toString()` luôn là `getSimpleName()`.” | Triển khai mặc định của `Throwable` dùng `getClass().getName()`. |
| “Một subclass không thể thay đổi các kết quả.” | Các phương thức có thể được override; cần xét hợp đồng lớp cụ thể. |

## 20. Tình huống luyện tập và đáp án

**Câu 1.** `new IllegalArgumentException("Sai tham số").getMessage()` trả gì?  
**Đáp án:** `"Sai tham số"`.

**Câu 2.** Cùng exception trên, `toString()` mặc định trả gì?  
**Đáp án:** `"java.lang.IllegalArgumentException: Sai tham số"`, vì class nằm trong `java.lang` và localized message mặc định bằng message.

**Câu 3.** `new IllegalArgumentException().getMessage()` có luôn là chuỗi rỗng không?  
**Đáp án:** Không. Với constructor mặc định của class này, message là `null`.

**Câu 4.** Với message `null`, `Throwable.toString()` mặc định có thêm dấu `": "` không?  
**Đáp án:** Không. Nó chỉ trả tên lớp.

**Câu 5.** Với message là `""`, `toString()` mặc định có thêm dấu `": "` không?  
**Đáp án:** Có, vì chuỗi rỗng **khác** `null`.

**Câu 6.** Nếu subclass override `getLocalizedMessage()` thành `"Không tìm thấy tệp"` mà không override `toString()`, `toString()` dùng giá trị nào?  
**Đáp án:** Dùng localized message của override đó và tên lớp runtime; không bắt buộc dùng detail message gốc.

**Câu 7.** Vì sao việc đổi `Locale.getDefault()` không làm mọi exception tự dịch message?  
**Đáp án:** Vì triển khai mặc định `getLocalizedMessage()` chỉ gọi `getMessage()`; không có cơ chế dịch tự động.

**Câu 8.** Một wrapper có cause là `IOException`. `getMessage()` có tự in toàn bộ cause không?  
**Đáp án:** Không nói chung. Constructor có `(String, Throwable)` thường giữ message riêng; cause truy qua `getCause()`. Một số constructor chỉ nhận cause đặt message bằng `cause.toString()`, nhưng đó là hành vi cụ thể.

**Câu 9.** `e.toString()` có in `getSuppressed()` không?  
**Đáp án:** Không trong triển khai mặc định của `Throwable`. Dùng `getSuppressed()` hoặc cơ chế in stack trace hỗ trợ suppressed.

**Câu 10.** Vì sao không dùng `e.getMessage().contains("not found")` để quyết định lỗi nào có thể retry?  
**Đáp án:** Message là văn bản có thể thay đổi/được dịch, không phải mã lỗi ổn định. Nên dùng loại exception, error code hoặc hợp đồng trả kết quả.

**Câu 11.** Muốn ghi log để điều tra một lỗi kỹ thuật, chỉ `getMessage()` có đủ không?  
**Đáp án:** Thường không. Cần xét loại lỗi, stack trace, cause và suppressed, cùng ngữ cảnh thích hợp.

**Câu 12.** `Throwable.getLocalizedMessage()` có thể trả `null` khi `getMessage()` không `null` không?  
**Đáp án:** Có nếu subclass chủ động override để trả `null`. Khi đó `Throwable.toString()` mặc định sẽ chỉ trả tên lớp.

**Câu 13.** Nếu subclass override `toString()` thì công thức tên lớp + localized message còn luôn đúng không?  
**Đáp án:** Không; subclass có thể định nghĩa định dạng khác.

**Câu 14.** `System.out.println(e)` với `e` là Throwable có giống `e.printStackTrace()` không?  
**Đáp án:** Không. `println(e)` in biểu diễn chuỗi ngắn, còn `printStackTrace()` in stack frames, có thể kèm cause/suppressed.

## 21. Checklist khi viết và dùng message của exception

Trước khi hoàn tất mã xử lý `Throwable`, kiểm tra:

1. **Có thể `null` không?** Không gọi trực tiếp `e.getMessage().trim()` hoặc `.length()` nếu chưa xét `null`.
2. **Cần thông điệp kỹ thuật hay bản địa hóa?** Không mặc định `getLocalizedMessage()` đã dịch.
3. **Cần biết loại lỗi không?** Chọn `getClass()` hoặc `toString()` tùy mục đích; không parse tên lớp từ văn bản nếu có thể tránh.
4. **Cần nguyên nhân gốc không?** Dùng `getCause()` và giữ cause khi wrapping.
5. **Có cleanup lỗi không?** Kiểm tra `getSuppressed()` khi phù hợp.
6. **Cần stack trace không?** Dùng logger nhận `Throwable` hoặc `getStackTrace()`/`printStackTrace()` theo ngữ cảnh.
7. **Có lộ dữ liệu nội bộ không?** Rà soát message trước khi log và đặc biệt trước khi trả ra giao diện.
8. **Có phụ thuộc văn bản message để ra quyết định không?** Chuyển sang mã lỗi/loại exception có cấu trúc.
9. **Có class tùy chỉnh override `getMessage()`, `getLocalizedMessage()` hoặc `toString()` không?** Kiểm tra tương tác giữa chúng, nhất là `toString()` dùng localized message.
10. **Có kiểm thử các biến thể message `null`, chuỗi rỗng và bản địa hóa không?** Những khác biệt nhỏ này có thể làm hỏng formatter hoặc log.
11. **Có yêu cầu hỗ trợ nhiều locale đồng thời không?** Tránh dựa vào locale toàn cục; cân nhắc dịch ở tầng giao diện.
12. **Code test có so nguyên văn stack trace không?** Tránh phụ thuộc số dòng và định dạng JVM; kiểm tra các thành phần có cấu trúc khi có thể.

## 22. Tổng kết

`getMessage()`, `getLocalizedMessage()` và `toString()` đều trả **chuỗi mô tả ngoại lệ**, nhưng khác hợp đồng:

- **`getMessage()`** là detail message, có thể `null`.
- **`getLocalizedMessage()`** là điểm mở rộng cho nội dung bản địa hóa, mặc định chỉ gọi `getMessage()`.
- **`toString()`** mặc định ghép **tên lớp runtime** với **localized message** nếu khác `null`, nhưng **không** tự chứa stack frames, cause hoặc suppressed.

Khi cần chẩn đoán nguyên nhân, đừng dừng ở chuỗi. Hãy xét **kiểu exception, `getCause()`, `getSuppressed()` và stack trace**. Khi cần phản hồi cho người dùng, hãy dùng thông điệp đã được rà soát, mã lỗi ổn định và cơ chế bản địa hóa phù hợp. Hiểu rõ sự khác nhau giữa ba phương thức giúp xử lý lỗi vừa chính xác về Java vừa hữu ích cho bảo trì và vận hành.
