# Trường transient, static và trạng thái mặc định được lưu khi tuần tự hóa Java

Trong cơ chế Java Object Serialization, `ObjectOutputStream.writeObject(object)` biến trạng thái của đồ thị đối tượng được phép tuần tự hóa thành dữ liệu có thể ghi ra stream; `ObjectInputStream.readObject()` dựng lại đồ thị đối tượng khi đọc. Tuy nhiên, **không phải mọi trường nhìn thấy trong lớp đều được ghi vào stream**.

Với một lớp triển khai `Serializable` và dùng cơ chế mặc định, Java lưu các **trường instance không mang modifier `static` và không mang modifier `transient`**. Giá trị của trường `transient` không được ghi theo cơ chế mặc định; trường `static` thuộc về lớp chứ không thuộc trạng thái instance nên cũng không được lưu. Khi giải tuần tự hóa, trường `transient` có giá trị mặc định của kiểu, thay vì nhận lại giá trị đã có trước khi ghi.

Hiểu quy tắc này giúp tránh vô tình lưu dữ liệu nhạy cảm, khôi phục sai cache/session, hoặc ngộ nhận rằng serialization là một bản sao toàn bộ trạng thái của JVM.

## 1. Điều kiện nền tảng: Serializable và Object Streams

Cơ chế tuần tự hóa đối tượng chuẩn gồm:

- `java.io.Serializable`: marker interface báo lớp có thể tham gia cơ chế Java serialization mặc định. Interface này **không có phương thức cần triển khai**.
- `ObjectOutputStream`: ghi đối tượng và các đối tượng được tham chiếu hợp lệ tới một `OutputStream`.
- `ObjectInputStream`: đọc lại biểu diễn stream để tái tạo đối tượng; `readObject()` trả `Object` và caller cần kiểm tra/ép kiểu phù hợp.
- `serialVersionUID`: mã phiên bản dùng kiểm tra khả năng tương thích của lớp serializable giữa lúc ghi và đọc. Thường khai báo tường minh `private static final long serialVersionUID = 1L;`.
- `IOException`, `ClassNotFoundException`, `NotSerializableException`, `InvalidClassException`: một số lỗi cần hiểu và xử lý khi dùng object stream.

Ví dụ khung sử dụng:

```java
// Minh họa: file là Path và Account implements Serializable.
try (ObjectOutputStream out =
        new ObjectOutputStream(Files.newOutputStream(file))) {
    out.writeObject(account);
}

try (ObjectInputStream in =
        new ObjectInputStream(Files.newInputStream(file))) {
    Account restored = (Account) in.readObject();
}
```

Đây là **đoạn minh họa**, không phải chương trình Java độc lập: cần khai báo `file`, `account`, lớp `Account`, import `java.io.*` / `java.nio.file.*` và xử lý checked exceptions. Stream phải được đóng đúng vòng đời bằng `try-with-resources`.

**Quan trọng về bảo mật:** Không gọi `ObjectInputStream.readObject()` trên dữ liệu không tin cậy. Java native deserialization có thể kích hoạt code trong quá trình tái tạo đối tượng, gây nguy cơ tấn công qua object graph/gadget. Nếu buộc phải nhận dữ liệu từ nguồn bên ngoài, phải có giới hạn/filter, định dạng và mô hình tin cậy phù hợp; với giao thức công khai thường nên chọn định dạng dữ liệu tường minh như JSON hoặc Protocol Buffers thay vì native object serialization.

## 2. Chính xác trường nào thuộc trạng thái mặc định được lưu?

Một lớp như sau:

```java
import java.io.Serializable;

final class Student implements Serializable {
    private static final long serialVersionUID = 1L;

    String name;                   // Instance: được lưu mặc định.
    int score;                     // Instance: được lưu mặc định.
    final int admissionYear;       // final instance: được lưu mặc định.

    transient String loginToken;   // transient: không lưu mặc định.
    transient int failedAttempts;  // transient: không lưu mặc định.

    static String activeSemester;  // static: không thuộc instance.
    static int onlineCount;        // static: không lưu mặc định.

    Student(String name, int score, int admissionYear) {
        this.name = name;
        this.score = score;
        this.admissionYear = admissionYear;
    }
}
```

Đoạn code này là **lớp minh họa**, có thể biên dịch khi được đặt trong tệp Java phù hợp; nó chưa có phương thức `main` hay code ghi/đọc stream.

| Khai báo field | Được lưu bởi default serialization? | Kết quả khi đọc lại |
| --- | --- | --- |
| `String name` | Có | Giá trị `name` đã ghi |
| `int score` | Có | Giá trị `score` đã ghi |
| `final int admissionYear` | Có | Giá trị final đã ghi vẫn được khôi phục theo cơ chế serialization |
| `transient String loginToken` | Không | `null` nếu không được khôi phục bằng code tùy biến |
| `transient int failedAttempts` | Không | `0` nếu không được khôi phục bằng code tùy biến |
| `static String activeSemester` | Không | Giá trị đang có của **lớp** trong JVM đọc |
| `static int onlineCount` | Không | Giá trị đang có của **lớp** trong JVM đọc |
| `static final long serialVersionUID` | Không phải instance field | Được Java serialization dùng làm thông tin phiên bản trong class descriptor, không phải một giá trị field của từng đối tượng |

Đây là **quy tắc mặc định**, chưa tính các cơ chế serialization tùy biến như `private writeObject/readObject`, `Externalizable` hoặc `serialPersistentFields`. Những cơ chế đó có thể quyết định lưu thêm/khác dữ liệu. Không suy rộng “transient không bao giờ được ghi” thành lời hứa tuyệt đối nếu chính lập trình viên chủ động ghi dữ liệu đó trong phương thức tùy biến.

### Những modifier dễ gây nhầm

- `private`, `protected`, package-private, `public` **không tự quyết định** field có được lưu hay không. Private instance field vẫn được lưu mặc định nếu không static/transient.
- `final` **không loại field ra khỏi serialization**. Một instance field final vẫn có thể được lưu và khôi phục.
- `volatile` không tự loại field ra khỏi serialization; nó giải quyết quy tắc hiển thị bộ nhớ giữa luồng, không phải chính sách lưu trạng thái.
- `static` và `transient` là hai lý do độc lập khiến field không nằm trong tập instance fields mặc định được lưu.
- `serialVersionUID` là thành phần phục vụ tương thích class descriptor; nó không làm cho mọi static field khác trở thành dữ liệu của đối tượng.

## 3. transient: không lưu giá trị và nhận lại giá trị mặc định

`transient` là modifier áp dụng cho **field**, dùng khi giá trị đó không nên thuộc trạng thái tuần tự hóa mặc định của đối tượng. Trường hợp thường gặp:

1. **Thông tin phiên làm việc tạm thời:** Token đăng nhập, session ID, kết nối đang mở, context request.
2. **Cache hoặc dữ liệu có thể tính lại:** Kết quả cache, chỉ mục dẫn xuất, tổng hợp tạm.
3. **Tài nguyên không thể hoặc không nên tuần tự hóa:** Socket, stream, lock, thread pool, handle hệ điều hành.
4. **Dữ liệu chỉ có ý nghĩa trong tiến trình hiện tại:** Bộ đếm tạm, thời gian tính từ clock nội bộ, trạng thái lazy initialization.

Ví dụ:

```java
class Profile implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    String username;
    transient String sessionToken;

    Profile(String username, String sessionToken) {
        this.username = username;
        this.sessionToken = sessionToken;
    }
}
```

Nếu `Profile("an", "SECRET")` được ghi bằng `ObjectOutputStream` rồi đọc bằng `ObjectInputStream` và không có code tùy biến, `username` sẽ là `"an"`, còn `sessionToken` là `null`. Điều này chỉ nói về **stream serialization mặc định**, không có nghĩa bản thân chuỗi bí mật đã biến mất khỏi RAM, log hay những bản ghi khác.

### Mặc định của từng kiểu khi deserialize

| Kiểu field transient | Giá trị khôi phục mặc định |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` |
| `float`, `double` | `0.0` |
| `boolean` | `false` |
| `char` | `'\u0000'` (null character) |
| Mọi tham chiếu object như `String`, `List<?>` | `null` |

**Không nhầm với giá trị trước khi ghi.** Nếu `transient int retryCount = 7;` và constructor sau đó đặt nó bằng 12, giá trị 12 không được lưu mặc định. Khi đọc lại, nó thường bằng 0, **không phải 7** và không phải 12.

### Field initializer và constructor không tự chạy lại cho lớp Serializable

Đây là khác biệt rất quan trọng: Khi giải tuần tự hóa một instance của lớp triển khai `Serializable`, **constructor và instance field initializer của chính lớp serializable đó không được gọi như khi `new` một instance bình thường**. Vì vậy, field khai báo:

```java
transient String token = "new-session";
transient int cachedCount = 99;
```

sẽ **không tự nhận** `"new-session"` và 99 sau khi giải tuần tự hóa mặc định; nó có thể nhận `null` và 0. Nếu cần tái khởi tạo cache, dùng cách khôi phục rõ ràng như `readObject()` hoặc một bước khởi tạo có kiểm soát sau khi đọc.

Có ngoại lệ liên quan **non-serializable superclass**: Constructor không đối số có khả năng truy cập của lớp cha đầu tiên không triển khai `Serializable` được chạy khi giải tuần tự hóa, do đó trạng thái của phần lớp cha đó có quy tắc khởi tạo khác. Không suy luận rằng *mọi constructor của toàn bộ phân cấp* đều bị bỏ qua.

## 4. static: trạng thái của lớp không nằm trong stream của instance

`static` đại diện cho biến thuộc **lớp**, chia sẻ giữa các instance cùng lớp (trong cùng ngữ cảnh class loading), không phải trạng thái riêng của từng object. Ví dụ:

```java
class Settings implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    static String environment = "DEV"; // Không ghi theo instance.
    String owner;                       // Có ghi mặc định.
}
```

Nếu chương trình ghi một `Settings` khi `environment="DEV"`, sau đó đổi `Settings.environment="PROD"` và đọc lại object trong **chính JVM đó**, `owner` được khôi phục từ stream, nhưng `environment` vẫn là `"PROD"`. Nó không trở về `"DEV"`.

Với **JVM khác**, giá trị static phụ thuộc quá trình tải/khởi tạo lớp và các thay đổi trong JVM đọc, chứ không phụ thuộc giá trị static của JVM ghi. Không có quy tắc rằng stream chứa snapshot của các biến global/static hay cấu hình tiến trình.

Kể cả khai báo `static final` cũng không biến nó thành instance field có trong stream. `serialVersionUID` mang vai trò riêng trong giao thức serialization như đã nêu, nhưng không làm thay đổi quy tắc của những static fields thông thường.

### Một hệ quả trong ứng dụng

Nếu bạn định serialize đối tượng cấu hình:

```java
static String region = "ap-southeast-1";
String serviceName = "billing";
```

thì chỉ `serviceName` thuộc dữ liệu instance được lưu mặc định. Nếu khôi phục phải đi cùng một `region` cụ thể, hãy thiết kế nó như một instance field thực sự thuộc snapshot, hoặc lưu cấu hình độc lập bằng định dạng rõ ràng, **đừng dựa vào static serialization**.

## 5. Ví dụ Java 17+ hoàn chỉnh: so sánh trước và sau khi đọc lại

Ví dụ ghi đối tượng ra tệp tạm, đổi giá trị static sau khi ghi, rồi đọc lại trong cùng JVM. Đồng thời đếm số lần constructor được gọi để minh họa rằng quá trình `readObject()` không gọi constructor của chính lớp serializable.

Tạo tệp **`TransientStaticDemo.java`**:

```java
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.IOException;
import java.io.Serializable;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TransientStaticDemo {
    private TransientStaticDemo() {}

    private static final class Snapshot implements Serializable {
        private static final long serialVersionUID = 1L;

        static String environment = "initial";
        static int constructorCalls = 0;

        String title;
        int level;
        final int version;

        transient String sessionToken = "initializer-token";
        transient int retryCount = 77;

        Snapshot(String title, int level, int version,
                 String sessionToken, int retryCount) {
            constructorCalls++;
            this.title = title;
            this.level = level;
            this.version = version;
            this.sessionToken = sessionToken;
            this.retryCount = retryCount;
        }

        String describe() {
            return "title=" + title
                    + ", level=" + level
                    + ", version=" + version
                    + ", token=" + sessionToken
                    + ", retries=" + retryCount
                    + ", environment=" + environment;
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {
        Path file = Files.createTempFile(
                "transient-static-demo-", ".bin");

        try {
            Snapshot.environment = "before-save";
            Snapshot original =
                    new Snapshot("Java", 17, 1, "SECRET", 5);

            System.out.println("before: " + original.describe());

            try (ObjectOutputStream out = new ObjectOutputStream(
                    Files.newOutputStream(file))) {
                out.writeObject(original);
            }

            Snapshot.environment = "after-save";

            Snapshot restored;
            try (ObjectInputStream in = new ObjectInputStream(
                    Files.newInputStream(file))) {
                restored = (Snapshot) in.readObject();
            }

            System.out.println("after: " + restored.describe());
            System.out.println("constructor calls="
                    + Snapshot.constructorCalls);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac TransientStaticDemo.java
java TransientStaticDemo
```

Kết quả khi I/O tệp tạm thành công:

```text
before: title=Java, level=17, version=1, token=SECRET, retries=5, environment=before-save
after: title=Java, level=17, version=1, token=null, retries=0, environment=after-save
constructor calls=1
```

**Vì sao output như vậy?**

1. `title`, `level`, `version` là instance fields không static/transient, do đó được lưu và khôi phục. `version` có `final` nhưng vẫn được tuần tự hóa mặc định.
2. `sessionToken` và `retryCount` có `transient`, nên sau `readObject()` lần lượt là `null` và 0. Các initializer `"initializer-token"` và 77 **không chạy lại** để khôi phục đối tượng.
3. `environment` là biến `static`, nên stream không ghi giá trị `"before-save"`. Khi giải tuần tự hóa trong cùng JVM, nó là `"after-save"` theo lần gán mới nhất.
4. `constructorCalls` là biến `static` được tăng khi gọi `new Snapshot(...)` lúc tạo object đầu tiên. Nó vẫn bằng 1 sau khi `readObject()`, minh họa constructor của `Snapshot` không được gọi lần hai.
5. Chương trình đóng stream ghi trước khi mở stream đọc, đóng stream đọc và xóa tệp tạm trong `finally`. Tệp tạm chỉ phục vụ ví dụ, không chứa dữ liệu người dùng thực.

Ví dụ là phép kiểm tra hành vi serialization **trong cùng một JVM**. Trong chương trình khác hoặc lần chạy khác, static fields thuộc lớp được khởi tạo độc lập. Đừng dựa vào việc thay đổi static trong producer có tác động tới process nhận.

## 6. Default serialization lưu cả đồ thị tham chiếu, không chỉ kiểu nguyên thủy

Các instance fields không static/transient có thể là primitive, `String`, array, collections hoặc đối tượng tùy biến. Khi `ObjectOutputStream.writeObject(root)` duyệt đồ thị được phép tuần tự hóa, những đối tượng **reachable qua các field được lưu** cũng cần tương thích với serialization.

Ví dụ:

```java
final class Order implements Serializable {
    private static final long serialVersionUID = 1L;

    String orderId;       // String serializable.
    java.util.ArrayList<String> items; // ArrayList và String serializable.
    Object helper;        // Object thường không triển khai Serializable.
}
```

Đây là phần định nghĩa minh họa, cần import `Serializable`. Nếu `helper` trỏ tới một `new Object()` thông thường và không được đánh dấu `transient`, `writeObject(order)` có thể ném `NotSerializableException` khi chạm tới object này. Không đủ nếu **lớp gốc** `Order` triển khai `Serializable` nhưng một object bên dưới đồ thị lại không serializable.

Nếu `helper` chỉ là tài nguyên runtime, có thể đánh dấu:

```java
transient Object helper;
```

Khi đó default serialization không duyệt reference qua field này, tránh cố ghi `helper`. Tuy nhiên sau khi đọc, `helper` sẽ là `null` và code phải chịu trách nhiệm khởi tạo lại nếu còn cần dùng.

### Identity và tham chiếu chia sẻ

Java serialization có cơ chế nhận diện đối tượng trong stream: nếu hai field cùng tham chiếu tới một object và serialization thành công, khi đọc lại chúng thường cùng trỏ tới một object được khôi phục (giữ sharing/cycles trong đồ thị). Đây không phải deep-copy độc lập cho từng field. Ngược lại, những object chỉ có thể tiếp cận qua `transient` field sẽ không được đưa vào đồ thị theo đường reference đó.

Một `static` field giữ một object cũng không tự khiến object ấy nằm trong stream của mọi instance. Nếu object đó còn được tham chiếu bởi một **instance field** được lưu, nó vẫn có thể được serialize theo đường tham chiếu instance.

## 7. Khôi phục các field transient bằng readObject khi thật sự cần

Có những field không nên lưu mà phải **tính lại** sau khi giải tuần tự hóa, ví dụ chiều dài tên hiển thị hoặc cache dẫn xuất. Một lớp serializable có thể khai báo phương thức `private void readObject(ObjectInputStream in)` để điều chỉnh hành vi giải tuần tự hóa.

Ví dụ:

```java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.Serializable;

final class CachedName implements Serializable {
    private static final long serialVersionUID = 1L;

    private String name;
    private transient int cachedLength;

    CachedName(String name) {
        this.name = name;
        this.cachedLength = name == null ? 0 : name.length();
    }

    int length() {
        return cachedLength;
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject(); // Khôi phục các field mặc định.
        cachedLength = name == null ? 0 : name.length();
    }
}
```

Đây là **lớp minh họa có thể biên dịch** cùng các import đã cho, nhưng không có chương trình `main`. Khi đọc lại, `defaultReadObject()` lấy `name` từ stream, rồi `cachedLength` được tính lại. Không cần lưu một cache vốn có thể suy ra từ dữ liệu đã lưu.

Những điểm cần lưu ý:

- `readObject` ở đây phải là **phương thức private có đúng chữ ký** cho cơ chế serialization mặc định, không phải override của `ObjectInputStream.readObject()`.
- `in.defaultReadObject()` thực hiện khôi phục các trường mặc định của lớp; không tự phục hồi `transient`.
- Với dữ liệu đọc từ nguồn không tin cậy, code `readObject` cũng là nơi có thể bị khai thác; **không coi việc có custom readObject là hàng rào an toàn**.
- Khi lớp có invariants, các giá trị khôi phục cần được kiểm tra chặt chẽ. Nếu vi phạm, có thể ném `InvalidObjectException` theo thiết kế.
- Tránh serialize những đối tượng phụ thuộc môi trường (socket, lock, executor) rồi giả định chúng hoạt động sau khi phục hồi; hãy cấp phát lại tài nguyên runtime khi cần.

### transient có thể bị ghi thủ công nếu code quyết định như vậy

Khi lập trình viên viết `private writeObject(ObjectOutputStream out)`, họ có thể gọi `defaultWriteObject()` để lưu các instance fields mặc định **và còn có thể tự gọi** `out.writeObject(secret)` để ghi thêm dữ liệu. Vì vậy `transient` chỉ loại field khỏi **tập field mặc định**, không ngăn một custom serializer cố ý đưa giá trị đó vào stream theo cách riêng.

Nếu mục tiêu là không để bí mật xuất hiện trong file, phải kiểm tra toàn bộ đường serialization và những lớp dữ liệu liên quan, không dựa duy nhất vào một modifier.

## 8. static, dữ liệu không tuần tự hóa và tính nhất quán sau khôi phục

Khi một object dùng cả instance fields và static fields trong nghiệp vụ, hành vi sau khi khôi phục có thể khác thời điểm ghi:

```java
// Đoạn minh họa nghiệp vụ.
class PricePolicy implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    static double taxRate = 0.10; // Cấu hình của JVM hiện tại.
    double subtotal;              // Một phần trạng thái instance.

    double total() {
        return subtotal * (1 + taxRate);
    }
}
```

Nếu `subtotal` được ghi là 100 và lúc đọc trên môi trường khác `taxRate` là 0.20, `total()` có thể trả 120 thay vì 110. Stream không sai: **thông tin static không có trong snapshot**. Nhưng hệ thống sẽ sai nếu kỳ vọng phép tính luôn được tái hiện giống lúc ghi.

Cách thiết kế tùy nghiệp vụ:

1. Nếu `taxRate` là thuộc tính của **đơn hàng tại thời điểm lập**, lưu nó như instance field `taxRateApplied` hoặc một object giá trị thuộc snapshot.
2. Nếu `taxRate` cố tình là cấu hình hiện hành lúc chạy, việc giá trị thay đổi sau khôi phục có thể đúng; nên thể hiện rõ trong logic và kiểm thử.
3. Không dùng serialization của object bất kỳ để thay thế cấu hình, schema lưu trữ hoặc cơ chế migration dữ liệu lâu dài.

Cùng nguyên tắc áp dụng cho feature flags, đường dẫn hệ thống, singleton runtime, service locator và cache static.

## 9. serialVersionUID, thay đổi lớp và dữ liệu mặc định của phiên bản mới

`serialVersionUID` hỗ trợ xác định lớp đọc có tương thích với thông tin lớp trong stream hay không. Khi không khai báo, JVM có thể tính tự động từ đặc điểm lớp, dẫn tới thay đổi giá trị không mong muốn giữa các phiên bản source/build. Với lớp dự kiến tuần tự hóa, thường nên khai báo giá trị tường minh.

Ví dụ lớp cũ:

```java
class Data implements Serializable {
    private static final long serialVersionUID = 1L;
    String name;
}
```

Và phiên bản mới thêm instance field:

```java
class Data implements Serializable {
    private static final long serialVersionUID = 1L;
    String name;
    int priority;
}
```

Đây là hai **phiên bản minh họa, không được khai báo đồng thời cùng tên trong một tệp biên dịch**. Nếu hai bên tương thích theo serialization protocol và cùng `serialVersionUID`, object cũ không có trường `priority` trong stream; khi đọc bằng lớp mới, `priority` nhận `0` (giá trị mặc định cho trường mới).

Nếu thay đổi gây bất tương thích, có thể gặp `InvalidClassException`. Giữ UID bằng nhau **không bảo đảm mọi thay đổi đều tương thích**: thay kiểu field, cấu trúc phân cấp hoặc cách custom serialization có thể làm dữ liệu không đọc được hoặc làm sai invariants.

Lưu ý phân biệt hai trường hợp nhận giá trị mặc định:

- `transient` field: không được lưu bởi default mechanism, nên sau khi deserialize nhận default nếu không có khôi phục tùy biến.
- Instance field **mới thêm** vào phiên bản class đọc: không có trong stream cũ, nên có thể nhận default nếu việc chuyển phiên bản được phép.

Trong cả hai, instance initializer của lớp serializable không tự bảo đảm chạy lại để đặt một giá trị cấu hình mong muốn.

## 10. Một số sai lầm phổ biến

| Ngộ nhận / lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Nghĩ mọi field của object đều được ghi | Static/transient bị bỏ qua, snapshot thiếu dữ liệu nghiệp vụ | Xác định field thuộc trạng thái instance cần lưu |
| Nghĩ `private` có nghĩa không serialize | Bí mật trong private field thường vẫn được lưu mặc định | Dùng thiết kế dữ liệu phù hợp; cân nhắc transient và custom serializer |
| Nghĩ `final` instance field sẽ bị loại | Đánh giá sai cấu trúc stream | Final instance field vẫn được lưu mặc định |
| Nghĩ static sẽ được khôi phục về giá trị lúc ghi | Kết quả xử lý khác nhau giữa JVM ghi/đọc | Không dựa vào static như một phần snapshot |
| Nghĩ transient giữ giá trị được gán trong constructor | Sau deserialize nhận `0/null/false` | Khởi tạo lại rõ ràng khi cần |
| Dùng transient trên object runtime nhưng không khởi tạo sau khi đọc | `NullPointerException` khi dùng cache, lock, service | Dùng `readObject` hoặc post-load initialization |
| Field thường trỏ tới đối tượng không Serializable | `NotSerializableException` khi ghi graph | Kiểm tra toàn bộ graph hoặc loại reference runtime |
| Tin rằng `transient` luôn bảo mật tuyệt đối | Code custom writeObject hoặc nguồn log khác vẫn có thể lộ | Kiểm tra toàn bộ đường xuất dữ liệu và bảo mật |
| Không khai báo `serialVersionUID` khi cần lưu dài hạn | Rủi ro bất tương thích do UID mặc định thay đổi | Quản lý UID và migration có chủ đích |
| Coi deserialize là gọi constructor bình thường | Invariants, cache/initializer có thể không hợp lệ | Validate, khôi phục trạng thái runtime sau đọc |
| Đọc object stream từ nguồn không tin cậy | Nguy cơ thực thi luồng deserialization nguy hiểm | Tránh native deserialization đối với dữ liệu không tin cậy; lọc và hạn chế nơi cần |
| Cho rằng mọi instance sau khi đọc độc lập tuyệt đối | Tham chiếu chia sẻ trong graph vẫn được bảo toàn | Hiểu identity và mutable sharing của đồ thị khôi phục |

## 11. Hướng dẫn chọn field cần lưu

Một cách thực tế là chia trạng thái của lớp thành ba nhóm:

| Nhóm trạng thái | Ví dụ | Chiến lược |
| --- | --- | --- |
| Dữ liệu nghiệp vụ cần khôi phục đúng | Mã đơn hàng, danh sách mục, giá trị tại thời điểm lập | Instance fields được lưu hoặc schema tường minh |
| Dữ liệu có thể tính lại/không nên lưu | Cache tính toán, session token, connection handle, listener, lock | `transient` và quy trình tái khởi tạo |
| Trạng thái toàn cục của môi trường | Feature flag hiện hành, cấu hình service, thống kê static | Không kỳ vọng native instance serialization lưu nó; quản lý cấu hình độc lập |

Trước khi đánh dấu một field là `transient`, hãy tự hỏi:

1. Nếu field trở thành `null` hoặc `0` khi khôi phục, code có còn hoạt động đúng không?
2. Có cần khởi tạo lại field từ dữ liệu khác, hoặc nó chỉ tồn tại trong một phiên?
3. Field có là đường duy nhất tham chiếu tới những dữ liệu cần được lưu trong object graph không?
4. Nếu field không bị đánh dấu transient, đối tượng phía sau có `Serializable` không?
5. Có yêu cầu bảo mật nào khiến bản thân native serialization không phù hợp cho mục đích lưu trữ/trao đổi không?

**Ghi nhớ:** Với Java serialization mặc định, **instance field không `static` và không `transient` mới là trạng thái được lưu**. `transient` quay về giá trị mặc định của kiểu khi đọc lại nếu không có code khôi phục; `static` thuộc trạng thái lớp trong JVM đang chạy, không được phục hồi từ stream của object. Constructor và field initializer của chính lớp `Serializable` không chạy lại như lệnh `new`. Dùng các quy tắc này để thiết kế snapshot rõ ràng, tránh phụ thuộc sai vào runtime state và chỉ deserialize nguồn dữ liệu đáng tin cậy.