# Phân biệt `cause` với `suppressed exception` trong Java

> **Chủ đề:** Java Core → Exception → Nguyên nhân và lỗi phụ. Một đối tượng `Throwable` có thể mang **nguyên nhân** qua `getCause()` và đồng thời mang **những ngoại lệ bị ghi nhận kèm** qua `getSuppressed()`. Hai cơ chế độc lập này phục vụ các câu hỏi khác nhau: **cause** trả lời “lỗi nào dẫn đến việc tạo ra lỗi hiện tại?”, còn **suppressed** trả lời “có những lỗi phụ nào xảy ra trong khi một lỗi chính đã được giữ lại?”. Trong Java, try-with-resources từ Java 7 là trường hợp điển hình tự tạo mối quan hệ suppressed khi thân `try` và `close()` cùng thất bại.

## 1. Nhìn nhanh: hai mối quan hệ khác nhau

Giả sử dịch vụ xử lý yêu cầu gặp lỗi đọc dữ liệu `IOException`, chuyển nó thành `IllegalStateException` có ngữ cảnh nghiệp vụ và đồng thời việc dọn dẹp một tài nguyên khác cũng thất bại.

```text
IllegalStateException: Không hoàn tất yêu cầu
├── cause: IOException: Không đọc được nguồn
└── suppressed: IOException: Không đóng được tài nguyên
```

Ở đây:

- `IllegalStateException` là **ngoại lệ hiện tại** mà caller có thể nhận được.
- `getCause()` trỏ đến `IOException("Không đọc được nguồn")`: nguyên nhân đã được gắn khi tạo/khởi tạo wrapper.
- `getSuppressed()` trả mảng chứa `IOException("Không đóng được tài nguyên")`: lỗi phụ được ghi lại, không thay thế ngoại lệ hiện tại.
- Caller không tự động có hai nhánh `catch` cho cause và suppressed. **Handler `catch` chọn theo kiểu thực tế của ngoại lệ đang được ném**, không tự bóc `cause` hay lặp qua `suppressed`.

Một `Throwable` có thể chỉ có cause, chỉ có suppressed, có cả hai hoặc không có mối quan hệ nào.

### 1.1. Bảng so sánh cốt lõi

| Tiêu chí | `cause` | `suppressed exception` |
| --- | --- | --- |
| Câu hỏi trả lời | “Lỗi nào gây ra lỗi này?” | “Lỗi nào khác cần ghi nhận mà không thay thế lỗi chính?” |
| API để đọc | `Throwable.getCause()` | `Throwable.getSuppressed()` |
| Kiểu trả về | `Throwable` hoặc `null` | `Throwable[]`, có thể rỗng |
| Cách gắn | Constructor nhận `cause` hoặc `initCause(...)` | `addSuppressed(...)` hoặc tự động bởi try-with-resources |
| Số lượng trực tiếp | Tối đa một cause trực tiếp | Có thể có nhiều suppressed trực tiếp |
| Quan hệ thường thấy | Lỗi hạ tầng được bọc thành lỗi tầng cao | Lỗi đóng tài nguyên khi đã có lỗi chính |
| Có thay kiểu exception đang ném không? | Không | Không |
| Tự tham gia chọn `catch` không? | Không | Không |
| Cấu trúc | Một chuỗi liên kết nguyên nhân (cause chain) | Một danh sách gắn vào mỗi Throwable; phần tử có thể có cause/suppressed riêng |
| Tự động có mọi lúc không? | Không; phải gắn/cấu trúc bởi API | Không; try-with-resources tự gắn trong điều kiện phù hợp |

**Cách nhớ:** `cause` biểu đạt **quan hệ nguyên nhân**; `suppressed` biểu đạt **những thất bại được giữ lại bên cạnh lỗi chính**. Không nên gọi một exception trong `getSuppressed()` là “cause thứ hai” vì đó là quan hệ dữ liệu khác.

## 2. Bối cảnh: `Throwable` lưu thông tin nào?

Trong hệ thống Java, `java.lang.Throwable` là lớp gốc của `Exception` và `Error`. Nó cung cấp các API hữu ích:

- `getMessage()`: thông điệp mô tả lỗi.
- `getCause()`: đối tượng gây ra lỗi này nếu được thiết lập.
- `getSuppressed()`: mảng các exception bị ghi nhận phụ.
- `getStackTrace()`: các `StackTraceElement` thuộc trace của chính Throwable.
- `printStackTrace()`: in báo cáo lỗi cho người đọc, có thể gồm cause và suppressed.
- `initCause(Throwable cause)`: thiết lập nguyên nhân trong những trường hợp API cho phép.
- `addSuppressed(Throwable exception)`: gắn một ngoại lệ phụ.

Những thông tin trên **không phải một cấu trúc phẳng**. Mỗi `Throwable` có message và stack trace của riêng mình; `cause` trỏ tới Throwable khác; mảng suppressed có thể chứa nhiều Throwable, và mỗi phần tử lại có stack, cause hoặc suppressed riêng.

### 2.1. Cause không phải một `StackTraceElement`

`getCause()` trả **một đối tượng Throwable**, không phải frame trong stack. Hai ngoại lệ wrapper và cause thường có hai trace riêng: trace wrapper phản ánh vị trí tạo wrapper, trace cause phản ánh vị trí được ghi nhận của lỗi gốc.

Tương tự, `getSuppressed()` trả **các đối tượng Throwable**, không phải stack frame hay thông điệp chuỗi. Khi cần phân tích chi tiết, duyệt đối tượng và xem message, type, stack theo mục đích.

## 3. `cause`: nguyên nhân dẫn đến exception hiện tại

Tình huống phổ biến: API tầng đọc file ném `IOException`, còn tầng dịch vụ muốn thông báo lỗi có ý nghĩa hơn đối với caller. Thay vì làm mất exception gốc, tầng dịch vụ tạo wrapper:

```java
try {
    readSettings();
} catch (java.io.IOException original) {
    throw new IllegalStateException(
            "Không tải được cấu hình", original);
}
```

Đây là mảnh code minh họa; `readSettings()` phải được định nghĩa. Ở đây:

1. `original` là đối tượng `IOException` đã bắt.
2. `new IllegalStateException("...", original)` tạo **đối tượng mới** và gắn cause là `original`.
3. `throw` ném **wrapper**, không trực tiếp ném lại `original`.
4. Caller có thể bắt `IllegalStateException` hoặc kiểu cha, sau đó dùng `getCause()` để truy nguyên.

**Ý nghĩa:** nguyên nhân lưu dấu failure thấp hơn đã được chuyển thành ngữ cảnh cao hơn, không phải một lỗi “thứ hai phát sinh song song”.

### 3.1. Java 17 — ví dụ chạy được về cause và wrapper

Tạo file **`CauseWrapperDemo.java`**:

```java
import java.io.IOException;

public class CauseWrapperDemo {
    static void loadFile() throws IOException {
        throw new IOException("Nguồn không đọc được");
    }

    static void loadService() {
        try {
            loadFile();
        } catch (IOException original) {
            throw new IllegalStateException(
                    "Không tải được dịch vụ", original);
        }
    }

    public static void main(String[] args) {
        try {
            loadService();
        } catch (IllegalStateException e) {
            System.out.println("Đang bắt: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
        }
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac -encoding UTF-8 CauseWrapperDemo.java
java CauseWrapperDemo
```

Stdout chính xác:

```text
Đang bắt: IllegalStateException
Message: Không tải được dịch vụ
Cause: IOException
Cause message: Nguồn không đọc được
Suppressed count: 0
```

Chương trình không tạo lỗi phụ nào, vì vậy mảng suppressed của wrapper rỗng. `getCause()` trả đúng đối tượng được truyền cho constructor wrapper, giữ nguyên loại và message từ tầng đọc file.

### 3.2. Chọn kiểu wrapper có chủ đích

`IllegalStateException` chỉ là lựa chọn ví dụ. Trong API thật có thể dùng exception tùy biến, ví dụ `ConfigurationLoadException`, để biểu đạt hợp đồng. Không tự động bọc mọi `IOException` thành `RuntimeException` chỉ để “né” checked exception. Hãy cân nhắc ai có khả năng xử lý lỗi, phạm vi API và nguyên nhân nào cần caller thấy.

Cấu trúc wrapper hợp lý thường là:

```java
class ConfigurationLoadException extends Exception {
    ConfigurationLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **khai báo lớp hợp lệ**, không có `main`. Caller của method ném loại checked này cần bắt hoặc khai báo theo quy tắc Java.

## 4. `initCause()` và giới hạn của quan hệ nguyên nhân

Ngoài constructor nhận cause, `Throwable` có phương thức:

```java
Throwable initCause(Throwable cause)
```

Phương thức cho phép thiết lập cause **một lần** trong trường hợp đối tượng chưa được khởi tạo cause. Đây là API cần thiết khi sử dụng những lớp exception/constructor không nhận cause.

### 4.1. Java 17 — thiết lập cause đúng một lần

Tạo file **`InitCauseDemo.java`**:

```java
import java.io.IOException;

public class InitCauseDemo {
    public static void main(String[] args) {
        IOException root = new IOException("Lỗi đọc");
        IllegalArgumentException wrapper =
                new IllegalArgumentException("Không hợp lệ");

        wrapper.initCause(root);
        System.out.println("Cause: "
                + wrapper.getCause().getClass().getSimpleName());

        try {
            wrapper.initCause(new IOException("Lỗi mới"));
        } catch (IllegalStateException e) {
            System.out.println("Gắn lần hai: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 InitCauseDemo.java
java InitCauseDemo
```

Stdout:

```text
Cause: IOException
Gắn lần hai: IllegalStateException
```

Sau lần gọi đầu, cause đã được khởi tạo. Việc gọi `initCause(...)` lần hai bị từ chối, không âm thầm thay thế nguyên nhân cũ.

### 4.2. Khi nào không gọi được `initCause()`?

- Nếu constructor đã khởi tạo cause (kể cả một constructor nhận `null` nhưng đã đánh dấu trạng thái cause được khởi tạo), `initCause(...)` có thể ném `IllegalStateException`.
- Không thể dùng chính Throwable làm cause của nó: `e.initCause(e)` không hợp lệ, gây `IllegalArgumentException`.
- Nên ưu tiên constructor nhận cause nếu API cung cấp; không tạo wrapper rồi quên gắn nguyên nhân.
- Chỉ dùng `initCause()` khi có lý do tương thích hoặc thiết kế API cụ thể; đừng coi nó là setter tự do thay đổi lịch sử lỗi.

**Chú ý khác biệt:** `getCause() == null` không tự chứng minh rằng `initCause(...)` vẫn được phép. Một exception có thể đã được khởi tạo cause bằng `null` nên API không cho thay đổi nữa.

## 5. `suppressed exception`: ngoại lệ phụ được ghi nhận mà không thay thế lỗi chính

Một Throwable có thể nhận nhiều ngoại lệ phụ:

```java
Throwable primary = new IllegalStateException("Lỗi chính");
primary.addSuppressed(new java.io.IOException("Lỗi đóng A"));
primary.addSuppressed(new java.io.IOException("Lỗi đóng B"));
```

Đây là mảnh code minh họa trong method. Nếu duyệt `primary.getSuppressed()`, ta thấy hai đối tượng `IOException`. Nhưng:

- `primary.getCause()` vẫn có thể là `null`.
- `getSuppressed()[0]` không tự trở thành cause.
- `addSuppressed(...)` **không ném** exception phụ theo luồng điều khiển Java. Nó chỉ lưu thông tin vào đối tượng chính.
- Handler `catch` đang chạy không tự chuyển sang xử lý suppressed exception như một exception mới.
- Các đối tượng phụ giữ message và stack trace riêng, phục vụ phân tích nếu cần.

### 5.1. Vì sao cần suppressed?

Trong một thao tác có hai giai đoạn, lỗi gốc xảy ra trong lúc **làm việc**, sau đó một lỗi khác xảy ra trong lúc **dọn dẹp**. Nếu code chỉ giữ lỗi cuối, có thể mất thông tin quan trọng nhất về thất bại ban đầu.

Ví dụ:

```text
Đọc dữ liệu thất bại         → IOException("read failed")   [primary]
Đóng luồng cũng thất bại      → IOException("close failed")  [suppressed]
```

Java 7 đưa cơ chế suppressed vào `Throwable` và dùng nó trong try-with-resources. Nó cho phép bảo toàn lỗi làm việc **và** không quên lỗi đóng, mà không nhất thiết ghi đè lỗi thứ nhất bằng lỗi thứ hai.

### 5.2. Java 17 — thao tác `addSuppressed` trực tiếp

Tạo file **`ManualSuppressedDemo.java`**:

```java
import java.io.IOException;

public class ManualSuppressedDemo {
    public static void main(String[] args) {
        IllegalStateException primary =
                new IllegalStateException("Xử lý thất bại");

        primary.addSuppressed(new IOException("Đóng A thất bại"));
        primary.addSuppressed(new IOException("Đóng B thất bại"));

        System.out.println("Primary: " + primary.getMessage());
        System.out.println("Cause: " + primary.getCause());
        System.out.println("Suppressed count: "
                + primary.getSuppressed().length);

        for (Throwable e : primary.getSuppressed()) {
            System.out.println("Suppressed: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ManualSuppressedDemo.java
java ManualSuppressedDemo
```

Stdout:

```text
Primary: Xử lý thất bại
Cause: null
Suppressed count: 2
Suppressed: Đóng A thất bại
Suppressed: Đóng B thất bại
```

`getCause()` trả `null` vì code không thiết lập cause; hai lỗi phụ được giữ riêng. Chương trình này không ném `primary` — ta chỉ tạo đối tượng và ghi thông tin để quan sát API. Trong thực tế thường một Throwable được ném/bắt rồi ghi suppressed theo yêu cầu xử lý.

## 6. Try-with-resources: nơi suppressed phát sinh tự động

Đây là tình huống phải hiểu rõ nhất.

```java
try (MyResource resource = open()) {
    perform(resource);
}
```

Đây là mã mẫu; `MyResource`/`open`/`perform` chưa được định nghĩa.

Nếu `perform(...)` ném một Throwable **P**, Java vẫn gọi `resource.close()`. Nếu `close()` cũng ném Throwable **C**, TWR ưu tiên giữ **P làm primary** và gắn **C vào danh sách suppressed của P**. Do đó:

- `catch` ở tầng ngoài nhận đối tượng P đang lan truyền.
- `P.getSuppressed()` chứa C nếu việc gắn suppressed diễn ra theo cơ chế bình thường.
- `P.getCause()` không tự đổi thành C.
- Lỗi C không kích hoạt riêng `catch` dựa trên kiểu của C, vì C không trở thành exception chính đang bay ra.

Nếu thân thành công nhưng `close()` thất bại, lỗi đóng có thể trở thành **primary** vì trước đó không có Throwable từ thân để ưu tiên.

### 6.1. Java 17 — thân và close đều lỗi

Tạo file **`TwrBodyAndCloseDemo.java`**:

```java
import java.io.IOException;

public class TwrBodyAndCloseDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đóng tài nguyên");
            throw new IOException("Không đóng được");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Xử lý dữ liệu");
            throw new IllegalStateException("Dữ liệu không hợp lệ");
        } catch (Exception e) {
            System.out.println("Primary type: "
                    + e.getClass().getSimpleName());
            System.out.println("Primary message: " + e.getMessage());
            System.out.println("Cause: " + e.getCause());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed type: "
                    + e.getSuppressed()[0].getClass().getSimpleName());
            System.out.println("Suppressed message: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Biên dịch/chạy Java 17:

```bash
javac -encoding UTF-8 TwrBodyAndCloseDemo.java
java TwrBodyAndCloseDemo
```

Stdout chính xác:

```text
Xử lý dữ liệu
Đóng tài nguyên
Primary type: IllegalStateException
Primary message: Dữ liệu không hợp lệ
Cause: null
Suppressed count: 1
Suppressed type: IOException
Suppressed message: Không đóng được
```

Đây là ví dụ **không có cause**, nhưng có **một suppressed exception**. Nó chứng minh vì sao “lỗi nào ném trước thì là cause, lỗi sau là suppressed” không phải định nghĩa chính xác: lỗi thân chính không được bọc, lỗi đóng là phụ; **không có chuỗi cause nào được thiết lập**.

### 6.2. Quy tắc quan trọng của handler `catch`

Trong ví dụ, handler `catch (Exception e)` nhận `IllegalStateException`, vì đó là đối tượng primary đang được ném. Việc suppressed là `IOException` **không** khiến chương trình tự gọi `catch (IOException)`.

Nếu viết các handler riêng, `catch (IllegalStateException)` nhận lỗi thân; `catch (IOException)` có thể nhận lỗi đóng nếu lỗi đóng trở thành primary **trong tình huống thân thành công**. Trong một source file thực, compiler còn xét các nguồn checked exception từ `close()`.

## 7. Nếu thân thành công nhưng đóng thất bại: close trở thành primary

Tạo **`TwrClosePrimaryDemo.java`**:

```java
import java.io.IOException;

public class TwrClosePrimaryDemo {
    static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đang đóng");
            throw new IOException("Lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (FailingClose r = new FailingClose()) {
            System.out.println("Thân thành công");
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TwrClosePrimaryDemo.java
java TwrClosePrimaryDemo
```

Stdout:

```text
Thân thành công
Đang đóng
Primary: Lỗi đóng
Suppressed count: 0
```

**Giải thích:** không có lỗi từ thân `try`, nên `IOException("Lỗi đóng")` là exception chính thoát khỏi TWR. Nó không thể “bị suppressed dưới một primary của thân” vì primary như vậy không tồn tại.

Điều này quan trọng với writer, buffered output, transaction-adjacent resources và các API mà `close()` có thể thực hiện công việc cuối cùng. “Đã in dòng thành công trong thân try” không bảo đảm operation đã thành công đến cuối vòng đời resource.

## 8. Nhiều tài nguyên: suppressed có thể là một danh sách

Java khởi tạo tài nguyên trong `try (...)` theo thứ tự khai báo (trái sang phải), đóng **ngược thứ tự khai báo** (phải sang trái).

Với hai resource A và B:

```text
Khởi tạo A → Khởi tạo B → Thân try
                               ↓
                            Đóng B
                               ↓
                            Đóng A
                               ↓
                        catch ở bên ngoài
```

Nếu thân đã ném primary P, cả B và A đóng đều lỗi, P có thể có hai suppressed, thường theo thứ tự đóng B rồi A.

### 8.1. Java 17 — hai lỗi đóng phụ bên cạnh lỗi thân

Tạo **`TwrMultipleSuppressedDemo.java`**:

```java
import java.io.IOException;

public class TwrMultipleSuppressedDemo {
    static final class Failing implements AutoCloseable {
        private final String name;

        Failing(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("Đóng " + name);
            throw new IOException("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Failing a = new Failing("A");
             Failing b = new Failing("B")) {
            System.out.println("Thân try");
            throw new IllegalArgumentException("body");
        } catch (Exception e) {
            System.out.println("Primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("Suppressed: "
                        + suppressed.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TwrMultipleSuppressedDemo.java
java TwrMultipleSuppressedDemo
```

Stdout:

```text
Mở A
Mở B
Thân try
Đóng B
Đóng A
Primary: body
Suppressed: close B
Suppressed: close A
```

Khi cả thân và hai lần đóng đều thất bại, lỗi thân vẫn là primary. Cả hai lỗi đóng được lưu trong mảng suppressed theo thứ tự B → A, đúng thứ tự đóng resource của TWR.

### 8.2. Nếu thân thành công nhưng nhiều lần đóng đều lỗi?

Khi không có lỗi thân, exception của **resource được đóng đầu tiên** có thể làm primary; exception phát sinh từ việc đóng các resource tiếp theo được suppressed vào nó.

Trong ví dụ A và B, B đóng trước, nên `IOException("close B")` thường là primary, còn `IOException("close A")` suppressed. Đừng mặc định suppressed luôn “lỗi đóng tài nguyên thứ hai” theo thứ tự khai báo; hãy đọc **thứ tự đóng ngược**.

### 8.3. Nếu khởi tạo tài nguyên thứ hai thất bại?

TWR vẫn đóng những tài nguyên **đã khởi tạo thành công trước đó**. Nếu khởi tạo B ném lỗi P rồi `A.close()` lại ném C, P thường là primary, C bị suppressed.

Resource chưa được khởi tạo thành công **không** được TWR bên ngoài gọi `close()` như một đối tượng đã nhận quyền quản lý. Nếu constructor tự mở resource phụ rồi ném giữa chừng, trách nhiệm dọn dẹp nội bộ là của implementation đó.

## 9. Cause và suppressed có thể tồn tại đồng thời

Không có quy tắc cấm một `Throwable` vừa có cause, vừa có suppressed. Ví dụ: tầng dịch vụ bọc một `IOException` thành lỗi dịch vụ, đồng thời có một lỗi dọn dẹp phụ phải giữ lại.

Tạo file **`CauseAndSuppressedTogetherDemo.java`**:

```java
import java.io.IOException;

public class CauseAndSuppressedTogetherDemo {
    public static void main(String[] args) {
        IOException source = new IOException("Nguồn hỏng");
        IllegalStateException service =
                new IllegalStateException("Dịch vụ thất bại", source);

        service.addSuppressed(new IOException("Dọn tệp lỗi"));
        service.addSuppressed(new IOException("Dọn kết nối lỗi"));

        System.out.println("Current: "
                + service.getClass().getSimpleName());
        System.out.println("Cause: "
                + service.getCause().getMessage());
        System.out.println("Suppressed count: "
                + service.getSuppressed().length);
        System.out.println("Suppressed 0: "
                + service.getSuppressed()[0].getMessage());
        System.out.println("Suppressed 1: "
                + service.getSuppressed()[1].getMessage());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CauseAndSuppressedTogetherDemo.java
java CauseAndSuppressedTogetherDemo
```

Stdout:

```text
Current: IllegalStateException
Cause: Nguồn hỏng
Suppressed count: 2
Suppressed 0: Dọn tệp lỗi
Suppressed 1: Dọn kết nối lỗi
```

**Điểm cốt lõi:** `getCause()` là một giá trị, còn `getSuppressed()` là một mảng. Cả hai đều được đọc từ **cùng đối tượng hiện tại** là `service`.

Một exception suppressed cũng có thể có **cause của riêng nó**. Vì thế khi làm công cụ phân tích lỗi, không nên giả định cấu trúc luôn là một chuỗi phẳng. Cần quan sát các mối quan hệ theo từng đối tượng.

## 10. `getCause()` có thể tạo thành chuỗi nguyên nhân

Nếu exception được bọc qua nhiều tầng:

```text
ApplicationException("request failed")
    └── cause: ServiceException("load failed")
            └── cause: IOException("read failed")
```

`getCause()` trên exception ngoài cùng trả cause trực tiếp, không tự trả lỗi sâu nhất. Nếu cần đi sâu, duyệt từng tầng.

### 10.1. Java 17 — duyệt cause chain

Tạo **`CauseChainDemo.java`**:

```java
import java.io.IOException;

public class CauseChainDemo {
    public static void main(String[] args) {
        IOException root = new IOException("read failed");
        IllegalStateException middle =
                new IllegalStateException("load failed", root);
        RuntimeException outer =
                new RuntimeException("request failed", middle);

        Throwable current = outer;
        int depth = 0;

        while (current != null) {
            System.out.println(depth + ": "
                    + current.getClass().getSimpleName()
                    + " / " + current.getMessage());
            current = current.getCause();
            depth++;
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CauseChainDemo.java
java CauseChainDemo
```

Stdout:

```text
0: RuntimeException / request failed
1: IllegalStateException / load failed
2: IOException / read failed
```

Ví dụ dùng chuỗi cause thông thường không có vòng lặp. Khi viết công cụ phân tích Throwable **không đáng tin hoặc có cấu trúc tùy biến**, nên sử dụng tập các đối tượng đã thăm nếu đệ quy qua cả cause và suppressed để tránh lặp vô hạn. Tránh suy đoán “depth càng lớn thì lỗi càng nghiêm trọng”; chuỗi chỉ phản ánh các lần bọc lỗi.

### 10.2. Có nên luôn lấy cause sâu nhất để hiển thị?

Không mặc định. Lỗi ngoài cùng mang **ngữ cảnh nghiệp vụ** hữu ích, ví dụ thất bại khi tải cấu hình; lỗi gốc mang thông tin kỹ thuật, ví dụ đọc file thất bại. Một báo cáo tốt có thể giữ cả hai. Nếu chỉ hiển thị root cause cho người dùng cuối, đôi khi lộ thông tin nội bộ hoặc làm mất ngữ cảnh ở tầng cao.

## 11. `printStackTrace()` thể hiện hai quan hệ ra sao?

`Throwable.printStackTrace()` là phương tiện hiển thị cho con người. Trong một báo cáo thông thường:

- Throwable hiện tại xuất hiện ở dòng đầu cùng trace của nó.
- Suppressed exceptions được chú thích **`Suppressed:`** và hiển thị theo cấp lồng phù hợp.
- Cause được hiển thị qua **`Caused by:`** cùng stack trace của cause.
- Các phần chung của stack có thể được rút gọn ở dạng **`... N more`**.

Ví dụ mô tả:

```text
java.lang.IllegalStateException: Dịch vụ thất bại
    at example.Service.run(Service.java:42)
    Suppressed: java.io.IOException: Lỗi đóng
        at example.Resource.close(Resource.java:18)
Caused by: java.io.IOException: Nguồn hỏng
    at example.Reader.read(Reader.java:27)
```

**Đây là sơ đồ minh họa**, không phải stdout/stderr cố định của một chương trình. Đường dẫn nguồn, dòng, số frame và thứ tự rút gọn phụ thuộc cấu trúc Throwable và môi trường thực thi.

Nếu chạy `printStackTrace()` không tham số, Java thường in ra `System.err`. Không nên so sánh nguyên văn stack trace trong unit test bằng line number và chuỗi `toString()` khi điều cần kiểm tra là loại exception hoặc quan hệ cause/suppressed.

### 11.1. `getStackTrace()` không thay cho `getCause()` và `getSuppressed()`

`getStackTrace()` trả **mảng `StackTraceElement[]` của chính Throwable hiện tại**, không tự gom trace của các ngoại lệ khác thành một mảng. Muốn phân tích quan hệ nguyên nhân/phụ:

```java
Throwable cause = failure.getCause();
Throwable[] suppressed = failure.getSuppressed();
StackTraceElement[] ownFrames = failure.getStackTrace();
```

Đây là mảnh code minh họa giả sử biến `failure` là `Throwable`. Ba API trả ba loại dữ liệu khác nhau. Tùy yêu cầu logging, có thể dùng logger ghi nguyên đối tượng Throwable để không đánh mất cause/suppressed, thay vì chỉ log `failure.getMessage()`.

## 12. Quy tắc và các lỗi thường gặp của `addSuppressed()`

`addSuppressed(Throwable exception)` không cho phép mọi tham số.

- `addSuppressed(null)` không hợp lệ; ném `NullPointerException`.
- `e.addSuppressed(e)` không hợp lệ vì tự-suppression; ném `IllegalArgumentException`.
- Có thể gắn **nhiều Throwable** vào cùng đối tượng primary.
- API không tự kết luận rằng mọi phần tử được gắn là lỗi close. Người viết code có thể chủ động gắn exception từ một bước phụ khác khi hợp đồng phù hợp.
- Không nên dùng `addSuppressed` làm kho lưu các lỗi validation thông thường nếu một cấu trúc kết quả lỗi có danh sách thông báo sẽ diễn đạt rõ hơn.

### 12.1. Java 17 — kiểm tra tham số không hợp lệ

Tạo file **`SuppressedValidationDemo.java`**:

```java
public class SuppressedValidationDemo {
    public static void main(String[] args) {
        Throwable primary = new IllegalStateException("primary");

        try {
            primary.addSuppressed(null);
        } catch (NullPointerException e) {
            System.out.println("null: "
                    + e.getClass().getSimpleName());
        }

        try {
            primary.addSuppressed(primary);
        } catch (IllegalArgumentException e) {
            System.out.println("self: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("Suppressed count: "
                + primary.getSuppressed().length);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SuppressedValidationDemo.java
java SuppressedValidationDemo
```

Stdout:

```text
null: NullPointerException
self: IllegalArgumentException
Suppressed count: 0
```

Cả hai thao tác gắn không hợp lệ đều bị từ chối, nên danh sách suppressed vẫn rỗng.

### 12.2. Mảng `getSuppressed()` là bản sao

`getSuppressed()` trả một mảng mới; sửa mảng do caller giữ **không sửa danh sách nội bộ của Throwable**. Vì phần tử là các tham chiếu tới Throwable, việc thay một phần tử của mảng sao chép không tự thay danh sách suppressed bên trong primary. Tuy nhiên đối tượng Throwable được tham chiếu vẫn có trạng thái riêng, nên không coi việc trả mảng sao chép là sao chép sâu mọi Throwable.

### 12.3. Không có API `setSuppressed(...)`

Trong API chuẩn, thao tác thêm là `addSuppressed(...)`. Không có setter công khai để thay toàn bộ danh sách suppressed theo kiểu `setSuppressed(Throwable[])`. Nếu cần một báo cáo lỗi có thể sửa/xóa các phần tử tùy ý, hãy sử dụng cấu trúc dữ liệu nghiệp vụ riêng thay vì cố biến Throwable thành container tổng quát.

## 13. Vô hiệu hóa suppression: trường hợp nâng cao

`Throwable` có constructor được bảo vệ:

```java
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
```

Các lớp con có thể chọn **`enableSuppression = false`**. Khi suppression bị vô hiệu hóa, việc gọi `addSuppressed(...)` không thêm ngoại lệ vào mảng; `getSuppressed()` trả mảng rỗng. Trường hợp này đặc thù và thường không cần với exception nghiệp vụ thông thường.

### 13.1. Java 17 — minh họa suppression bị tắt

Tạo file **`SuppressionDisabledDemo.java`**:

```java
import java.io.IOException;

public class SuppressionDisabledDemo {
    static final class QuietException extends Exception {
        QuietException(String message) {
            super(message, null, false, true);
        }
    }

    public static void main(String[] args) {
        QuietException error = new QuietException("primary");
        error.addSuppressed(new IOException("cleanup"));

        System.out.println("Primary: " + error.getMessage());
        System.out.println("Suppressed count: "
                + error.getSuppressed().length);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SuppressionDisabledDemo.java
java SuppressionDisabledDemo
```

Stdout:

```text
Primary: primary
Suppressed count: 0
```

**Cảnh báo thiết kế:** tắt suppression có thể làm mất thông tin lỗi đóng tài nguyên rất hữu ích. Tính năng dành cho những tình huống ngoại lệ được thiết kế đặc biệt, không phải tối ưu mặc định.

### 13.2. `cause` có phụ thuộc vào suppression không?

Không. Hai cơ chế được điều khiển/thiết lập riêng. Một Throwable được vô hiệu hóa suppression vẫn có thể có cause nếu constructor/`initCause` cho phép. Một Throwable có suppression bình thường cũng không tự có cause.

## 14. Thứ tự thời gian không đồng nghĩa với cause

Một hiểu nhầm phổ biến:

> “Exception thứ nhất luôn là cause; exception thứ hai luôn là suppressed.”

Điều này **không đúng**.

- Trong TWR, exception từ **thân `try`** được ưu tiên làm primary khi đã tồn tại. Exception phát sinh sau trong `close()` có thể bị suppressed, **không** phải cause.
- Khi tầng service bọc exception hạ tầng thành exception nghiệp vụ, lỗi gốc được gắn làm cause, dù thao tác bọc diễn ra **sau** khi lỗi gốc được ném.
- Khi chỉ có lỗi `close()`, lỗi đóng có thể trở thành **primary** dù nó xảy ra muộn trong vòng đời resource.
- Một Throwable có thể vừa có cause vừa có suppressed, nên không thể phân loại dựa trên “đầu tiên/thứ hai” mà bỏ ngữ nghĩa API.

**Quy tắc thực hành:** đọc quan hệ bằng **`getCause()`** và **`getSuppressed()`**. Đừng suy ra quan hệ chỉ từ thứ tự các dòng log.

## 15. Lỗi khi dùng `finally` so với try-with-resources

Mẫu cũ:

```java
Resource resource = open();
try {
    perform(resource);
} finally {
    resource.close();
}
```

Đây là mảnh minh họa. Nếu `perform` đã ném P và `resource.close()` ném C trong `finally`, lỗi C có thể **che mất** lỗi P vì `finally` hoàn tất bất thường.

TWR:

```java
try (Resource resource = open()) {
    perform(resource);
}
```

Khi được áp dụng đúng, TWR tự cố gắng đóng resource và gắn lỗi C thành suppressed của P khi P đã có. Đó là một lợi ích quan trọng ngoài việc giảm số dòng.

Không có nghĩa TWR tự phục hồi/rollback: dữ liệu có thể đã bị thay đổi trước khi exception phát sinh. Primary và suppressed chủ yếu bảo toàn **thông tin chẩn đoán**, còn tính nhất quán nghiệp vụ cần transaction, kiểm tra trước thay đổi, hoặc cơ chế phục hồi phù hợp.

### 15.1. `finally` vẫn có giá trị

`finally` hữu ích cho các công việc không thuộc giao thức `AutoCloseable`, ví dụ ghi nhận trạng thái một phiên xử lý hay khôi phục context. Chỉ cần tránh đóng resource TWR lần hai và tránh `return` hoặc ném lỗi mới trong `finally` nếu mục tiêu là giữ exception gốc.

Nếu một công việc trong `finally` có thể ném, thiết kế riêng cách lưu lỗi này mà không vô tình che primary. Đừng thêm `addSuppressed` thủ công khắp nơi nếu TWR đã xử lý close theo hợp đồng.

## 16. Thiết kế chiến lược xử lý khi có cả hai loại dữ liệu lỗi

Tình huống giả định: một giao dịch đọc file thất bại, kết nối logging bị lỗi trong lúc dọn dẹp. Thiết kế xử lý cần trả lời:

1. **Lỗi chính là gì?** Kiểu và message của Throwable đang được ném.
2. **Cause là gì?** Exception nào đã dẫn đến wrapper ở tầng hiện tại?
3. **Suppressed gồm gì?** Có lỗi đóng/dọn dẹp phụ cần báo cáo không?
4. **Trạng thái sau lỗi ra sao?** Resource có thể đã đóng một phần; các side effect nghiệp vụ có thể đã thực hiện.
5. **Tầng nào chịu trách nhiệm xử lý?** Tầng hạ tầng có thể chuyển lỗi, tầng API có thể báo failure, tầng vận hành có thể log và cảnh báo.

Một chiến lược tốt thường **không** bắt `Throwable` rồi chuyển mọi thứ thành “OK”. Nên bắt kiểu phù hợp hoặc để lỗi lan lên boundary, bảo đảm trạng thái thất bại được truyền đến caller và giữ cause/suppressed cho điều tra.

### 16.1. Duyệt quan hệ mà không nhầm với kiểm soát luồng

Ví dụ phương thức minh họa:

```java
static void inspect(Throwable error) {
    System.out.println("Current: " + error.getMessage());

    Throwable cause = error.getCause();
    if (cause != null) {
        System.out.println("Cause: " + cause.getMessage());
    }

    for (Throwable suppressed : error.getSuppressed()) {
        System.out.println("Suppressed: "
                + suppressed.getMessage());
    }
}
```

Đây là method có thể đặt trong một lớp. Nó chỉ **đọc** quan hệ lỗi; không ném lại, không tự đóng resource và không biến suppressed thành exception đang xử lý. Nếu cần ném tiếp, thực hiện `throw` theo hợp đồng checked/unchecked phù hợp.

### 16.2. Những thông tin nào nên log?

Ở boundary ứng dụng, logger nên có thể ghi đối tượng Throwable đầy đủ, để không mất:

- Loại và message của exception ngoài cùng.
- Trace và cause chain.
- Các suppressed exceptions và trace của chúng.
- Ngữ cảnh request/job (theo chính sách bảo mật và quyền riêng tư).

Chỉ ghi `getMessage()` là chưa đủ khi chẩn đoán lỗi phức tạp. Nhưng cũng không nên trả toàn bộ trace và chuỗi cause cho client công khai vì có thể lộ class, file, đường gọi, nguồn dữ liệu hoặc thông tin nhạy cảm. Trả lỗi có cấu trúc/mã tham chiếu cho client và lưu chi tiết ở hệ thống log được kiểm soát thường hợp lý hơn.

## 17. Các lỗi thường gặp cần tránh

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Cause và suppressed là hai tên cho cùng một lỗi.” | Là hai quan hệ độc lập, đọc qua hai API khác nhau. |
| “`getCause()` trả một mảng các lỗi.” | Trả một `Throwable` hoặc `null`. |
| “`getSuppressed()` trả một Throwable hoặc `null`.” | Trả `Throwable[]`, có thể rỗng. |
| “Lỗi `close()` luôn là cause.” | TWR thường gắn lỗi close thành suppressed khi đã có primary. |
| “Thân thành công, close lỗi thì close vẫn là suppressed.” | Khi không có primary trước đó, lỗi close có thể làm primary. |
| “Có suppressed thì `getCause()` không thể có dữ liệu.” | Một Throwable có thể có cả cause và suppressed. |
| “`catch(IOException)` tự bắt suppressed IOException.” | Handler so kiểu primary Throwable đang lan truyền. |
| “`throw new RuntimeException(e.getMessage())` đã giữ nguyên nhân.” | Chỉ sao chép message; cần constructor truyền cause để liên kết ngoại lệ gốc. |
| “`initCause` là setter gọi bao nhiêu lần cũng được.” | Cause chỉ được khởi tạo một lần theo hợp đồng. |
| “`addSuppressed(null)` sẽ bị bỏ qua.” | Ném `NullPointerException`. |
| “`e.addSuppressed(e)` hợp lệ vì muốn ghi cùng lỗi.” | Tự-suppression bị cấm và ném `IllegalArgumentException`. |
| “`getSuppressed()` là stack trace phụ.” | Chứa các đối tượng Throwable; mỗi cái có stack riêng. |
| “Có nhiều suppressed thì phải có nhiều cause.” | Một Throwable có tối đa một cause trực tiếp; suppressed là danh sách riêng. |
| “TWR bảo đảm tự rollback trạng thái.” | TWR tự quản lý `close()`; rollback cần cơ chế khác. |
| “`printStackTrace()` chỉ in trace của wrapper.” | Dạng in thường có `Caused by` và `Suppressed` để thể hiện quan hệ. |
| “Nếu lỗi đóng được suppressed thì không quan trọng.” | Lỗi phụ vẫn có thể chỉ ra rò rỉ tài nguyên, ghi không hoàn tất hoặc vấn đề hệ thống cần điều tra. |
| “Có thể dùng cause chain làm danh sách mọi lỗi đồng thời.” | Cause mô tả chuỗi nguyên nhân; cần cấu trúc tổng hợp riêng nếu muốn lưu nhiều lỗi ngang hàng theo nghiệp vụ. |

## 18. Bài tập thực hành

### Bài 1 — Nhận diện loại quan hệ

Cho sơ đồ:

```text
IllegalStateException("service")
  cause → IOException("read")
  suppressed → IOException("closeA")
  suppressed → IOException("closeB")
```

Hỏi:

1. `getCause()` trả gì?
2. `getSuppressed().length` bằng bao nhiêu?
3. `catch(IOException)` có tự bắt primary `IllegalStateException` không?
4. Muốn in các lỗi đóng thì duyệt API nào?

**Đáp án:** cause là `IOException("read")`; suppressed count là `2`; handler `IOException` không bắt primary; dùng `getSuppressed()`.

### Bài 2 — Thay đổi tình huống TWR

Chạy `TwrBodyAndCloseDemo` rồi bỏ câu lệnh ném `IllegalStateException` trong thân. Dự đoán loại primary và suppressed count. **Định hướng:** chỉ còn lỗi close, nên primary thường là `IOException` từ `close()`, suppressed rỗng.

### Bài 3 — Thêm tài nguyên thứ ba

Trong `TwrMultipleSuppressedDemo`, thêm resource C vào cuối danh sách. Giữ thân ném `IllegalArgumentException`. Nếu cả A/B/C đóng lỗi, dự đoán thứ tự đóng và mảng suppressed. **Đáp án:** đóng C → B → A; suppressed lần lượt `close C`, `close B`, `close A`.

### Bài 4 — Cause chain ba tầng

Dùng `CauseChainDemo`, thêm một wrapper có thông điệp `"API failed"`. Duyệt `getCause()` và in depth, type, message. Xác nhận wrapper mới có thể có cause là wrapper cũ mà không làm thay đổi cause gốc đã lưu.

### Bài 5 — `initCause` không phải setter tự do

Trong `InitCauseDemo`, giải thích vì sao gọi `initCause` lần thứ hai bị từ chối. Sau đó thử tạo `new IllegalArgumentException("wrapper", root)` rồi gọi `initCause(other)` và dự đoán vì sao constructor đã khởi tạo quan hệ cause.

### Bài 6 — Bảo toàn thông tin khi bọc exception

Viết một method `loadConfiguration()` gọi API đọc có thể ném `IOException`. Bắt nó rồi ném `ConfigurationLoadException("Cannot load config", e)` với constructor truyền cause. Tại caller, in loại wrapper và loại cause. Nếu còn lỗi dọn dẹp, hãy phân biệt rõ cơ chế suppressed thay vì gắn lỗi đó thành cause mới vô nghĩa.

### Bài 7 — Mảng suppressed là bản sao

Tạo `Throwable primary`, gắn hai suppressed. Gọi `getSuppressed()` hai lần lấy hai mảng. Thay phần tử đầu của mảng thứ nhất, rồi đọc lại trên primary. Vì sao danh sách suppressed của primary không bị thay đổi?

### Bài 8 — Thiết kế logging

Một request API gặp `IllegalStateException` với cause là lỗi đọc file và hai suppressed từ dọn dẹp. Thiết kế phản hồi lỗi gửi client và thông tin log nội bộ. **Định hướng:** client nhận mã lỗi/correlation id phù hợp; logger ghi Throwable đầy đủ, không đẩy stack trace và đường file nội bộ ra ngoài.

### Bài 9 — Lỗi chính và tính toàn vẹn dữ liệu

Giả sử `writer.write(...)` ném `IOException("write")` và `writer.close()` lại ném `IOException("close")`. Trình bày primary và suppressed nếu dùng TWR. Sau đó giải thích tại sao việc giữ thông tin lỗi **không chứng minh** file đã rollback hoặc không chứa dữ liệu ghi dở.

## 19. Checklist hiểu và vận dụng đúng

- [ ] Tôi giải thích được `cause` là nguyên nhân được gắn vào lỗi hiện tại, còn `suppressed` là lỗi phụ được lưu kèm chưa?
- [ ] Tôi biết `getCause()` trả một Throwable hoặc `null`, còn `getSuppressed()` trả mảng không-null không?
- [ ] Tôi hiểu `getCause()` có thể tạo chuỗi wrapper, còn suppressed có thể chứa nhiều Throwable chưa?
- [ ] Tôi sử dụng constructor nhận `cause` và không làm mất lỗi gốc khi chuyển tầng chưa?
- [ ] Tôi hiểu `initCause` chỉ được gọi hợp lệ một lần trong điều kiện thích hợp chưa?
- [ ] Tôi biết `addSuppressed(null)`/tự-suppression không hợp lệ chưa?
- [ ] Tôi phân biệt primary của TWR với lỗi đóng bị suppressed chưa?
- [ ] Tôi hiểu khi thân TWR thành công nhưng close lỗi, lỗi đóng có thể là primary chưa?
- [ ] Tôi biết với nhiều resource Java đóng ngược thứ tự khai báo và có thể tích lũy nhiều suppressed chưa?
- [ ] Tôi đã kiểm tra `getSuppressed()` thay vì chỉ đọc message của primary khi dọn dẹp cũng lỗi chưa?
- [ ] Tôi hiểu `catch` dựa trên kiểu exception đang ném, không dựa vào cause hoặc suppressed chưa?
- [ ] Tôi tránh dùng `finally` để đóng lại resource TWR hoặc vô tình che lỗi chính chưa?
- [ ] Tôi không nhầm bảo toàn thông tin exception với rollback/khôi phục trạng thái nghiệp vụ chưa?
- [ ] Tôi log Throwable đầy đủ ở nơi phù hợp nhưng không để lộ stack trace nội bộ ra client công khai chứ?
- [ ] Tôi đã test các tình huống chỉ có cause, chỉ có suppressed, cả hai, không có cái nào, và nhiều lỗi đóng chưa?

**Ghi nhớ cuối:** **Cause** nối lỗi hiện tại với **nguyên nhân** (`getCause()`, constructor nhận cause hoặc `initCause()`); **suppressed exceptions** giữ **các thất bại phụ** (`getSuppressed()`, `addSuppressed()`), đặc biệt khi try-with-resources đang đóng tài nguyên sau khi thân đã lỗi. Cả hai quan hệ cùng tồn tại được, không tự thay đổi handler `catch`, và phải được giữ lại khi chẩn đoán lỗi.