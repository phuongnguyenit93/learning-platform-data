# Exception chaining và ý nghĩa của quan hệ `cause` trong Java

**Exception chaining** (liên kết chuỗi ngoại lệ) là kỹ thuật để một đối tượng ngoại lệ **giữ tham chiếu đến ngoại lệ đã gây ra nó**. Trong Java, liên kết này được biểu diễn chủ yếu qua `Throwable.getCause()` và các constructor nhận tham số `Throwable cause`.

Giả sử lúc khởi động một ứng dụng, tầng đọc tệp thất bại vì `IOException`. Tầng cấu hình hiểu rằng *không thể nạp cấu hình*, còn tầng dịch vụ hiểu rằng *không thể khởi động dịch vụ*. Nếu mỗi tầng chỉ thay lỗi cũ bằng một lỗi mới mà không giữ nguyên nhân, thông tin chẩn đoán sẽ mất. Exception chaining cho phép vừa **diễn đạt vấn đề đúng ngữ cảnh của mỗi tầng**, vừa **giữ nguyên dấu vết nguyên nhân gốc**.

~~~text
StartupException: Không thể khởi động dịch vụ
    |
    +-- cause --> ConfigurationException: Không thể nạp cấu hình
                      |
                      +-- cause --> IOException: Không tìm thấy tệp
~~~

Ở ví dụ trên, người dùng tầng dịch vụ nhìn thấy lỗi `StartupException`, trong khi người điều tra vẫn có thể lần theo `getCause()` để biết lỗi I/O ban đầu.

**Điểm cốt lõi:** `cause` là **liên kết đến một đối tượng `Throwable` khác**, không phải chuỗi thông điệp được sao chép, không phải stack trace và cũng không phải danh sách suppressed exceptions. Bài học này giải thích cách xây dựng chuỗi ngoại lệ, ý nghĩa của từng tầng, những lựa chọn khi xử lý và các lỗi thiết kế thường gặp trong Java 17+.

## 1. Vì sao cần exception chaining?

Một chức năng phần mềm thường trải qua nhiều tầng:

~~~text
Ứng dụng / giao diện
    |
    v
Service / nghiệp vụ
    |
    v
Repository / cấu hình
    |
    v
File system / database / network
~~~

Khi tầng thấp gặp lỗi, tầng cao có thể không muốn để lộ trực tiếp loại lỗi thấp tầng trong API. Ví dụ, API khởi động dịch vụ có thể chọn `ServiceStartupException` thay vì bắt bên gọi hiểu tất cả các biến thể `IOException`.

Nhưng nếu chỉ làm:

~~~java
catch (java.io.IOException error) {
    throw new IllegalStateException("Khởi động thất bại");
}
~~~

thì ngoại lệ mới không có cause. `getCause()` trả `null`; stack trace và thông điệp của `IOException` ban đầu không được giữ trong quan hệ nguyên nhân của ngoại lệ mới.

Một cách biểu đạt tốt hơn:

~~~java
catch (java.io.IOException error) {
    throw new IllegalStateException(
            "Khởi động thất bại vì không đọc được cấu hình", error);
}
~~~

Các đoạn này là **mảnh mã trong ngữ cảnh một `try` có thể ném `IOException`**, không phải chương trình độc lập. Đoạn thứ hai giữ:

- **Kiểu của lỗi tầng ngoài:** `IllegalStateException`.
- **Message tầng ngoài:** tại sao thao tác ở tầng này thất bại.
- **Cause:** chính đối tượng `IOException` ban đầu.
- **Stack trace riêng:** đường gọi tại nơi tạo ngoại lệ tầng ngoài.
- **Stack trace của cause:** nguồn gốc lỗi ở tầng thấp, được giữ trong đối tượng cause.

Nhờ vậy, phần mềm có thể tách **hợp đồng xử lý ở tầng cao** khỏi **thông tin kỹ thuật để chẩn đoán**.

## 2. Một mắt xích của chuỗi được biểu diễn như thế nào?

Mỗi `Throwable` có thể giữ một nguyên nhân trực tiếp:

~~~java
java.io.IOException root =
        new java.io.IOException("Không tìm thấy tệp");

IllegalStateException outer =
        new IllegalStateException("Không thể tải cấu hình", root);

System.out.println(outer.getCause() == root); // true
~~~

Kết quả `true` chứng minh `getCause()` trả về **cùng tham chiếu đối tượng** `root`, không phải một ngoại lệ mới được sao chép từ message.

Các API liên quan:

| API | Vai trò |
| --- | --- |
| `getMessage()` | Trả thông điệp của **chính ngoại lệ đang xét** |
| `getCause()` | Trả **nguyên nhân trực tiếp** của ngoại lệ, nếu có |
| `initCause(Throwable)` | Thiết lập cause một lần nếu trạng thái cause chưa được khởi tạo |
| `getStackTrace()` | Trả dấu vết lời gọi đã ghi cho **chính đối tượng đó** |
| `getSuppressed()` | Trả danh sách các lỗi phụ được đính kèm, **khác cause** |
| `printStackTrace()` | Hiển thị lỗi và thường cả thông tin cause/suppressed để chẩn đoán |

**`getCause()` chỉ đi một tầng.** Nếu A bọc B và B bọc C, thì:

~~~text
A.getCause() == B
B.getCause() == C
C.getCause() == null
~~~

Nếu muốn tìm lỗi gốc sâu nhất, cần đi qua từng `getCause()`. Việc “sâu nhất” thường hữu ích để điều tra, nhưng **lỗi quan trọng nhất cho người gọi chưa chắc là lỗi sâu nhất**. Tầng nghiệp vụ có thể cần xử lý theo loại ngoại lệ bên ngoài chứ không theo nguồn gốc vật lý thấp tầng.

## 3. Constructor thông thường để thiết lập cause

Các lớp ngoại lệ phổ biến có một số dạng constructor như:

~~~java
new IllegalStateException("Thông điệp");
new IllegalStateException("Thông điệp", original);
new IllegalStateException(original);
~~~

Đây là mảnh minh họa có biến `original` là `Throwable` phù hợp.

### Dạng `(String message, Throwable cause)`

Thường là lựa chọn rõ ràng nhất khi **bọc lỗi và bổ sung ngữ cảnh**:

~~~java
throw new IllegalStateException(
        "Không thể hoàn tất nghiệp vụ nhập dữ liệu", original);
~~~

- Message mô tả thất bại ở tầng hiện tại.
- Cause giữ ngoại lệ trước đó.
- Caller có thể đọc riêng từng phần.

### Dạng `(Throwable cause)`

Một số lớp, như `IllegalStateException`, có overload cause-only:

~~~java
IllegalStateException wrapper =
        new IllegalStateException(
                new java.io.IOException("Kết nối bị ngắt"));
~~~

Với các constructor cause-only dựa trên `Throwable`, message của wrapper thường được tạo từ `cause.toString()` nếu cause khác `null`. Điều đó thường tạo chuỗi có **tên lớp của cause** lẫn message.

Nếu tầng hiện tại có một hành động thất bại cần diễn giải, nên cân nhắc overload `(String, Throwable)`.

### Constructor không được kế thừa

Không phải mọi lớp con của `Throwable` đều có sẵn mọi overload. Constructor **không được kế thừa** như phương thức thông thường. Nếu khai báo exception riêng, cần chủ động cung cấp overload nhận cause khi phù hợp:

~~~java
public class ConfigurationException extends Exception {
    public ConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đoạn trên là một **lớp độc lập** nếu lưu trong `ConfigurationException.java`. Việc gọi `super(message, cause)` mới chuyển dữ liệu chẩn đoán tới cơ chế của `Throwable`.

## 4. Ba cách xử lý lỗi: phục hồi, ném lại, bọc với cause

Không phải mọi ngoại lệ xuất hiện đều nên được bọc. Khi viết khối `catch`, hãy xem tầng hiện tại có đủ thông tin để giải quyết vấn đề hay không.

### Cách A — Phục hồi: không cần lan truyền lỗi

~~~java
static int readLimitOrDefault(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return 10;
    }
}
~~~

Phương thức minh họa này chọn `10` nếu chuỗi không phải số. Cách đó chỉ hợp lý nếu hợp đồng cho phép một giá trị mặc định khi dữ liệu hỏng. Khi đã phục hồi thành công, **không cần ném một wrapper chỉ để cho thấy đã từng có ngoại lệ**.

Nếu dữ liệu bắt buộc chính xác, việc trả mặc định có thể che lỗi — phải thiết kế theo yêu cầu nghiệp vụ.

### Cách B — Ném lại: giữ đúng đối tượng và loại lỗi

~~~java
static String readRequired(java.nio.file.Path path)
        throws java.io.IOException {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException e) {
        System.err.println("Không đọc được tệp bắt buộc");
        throw e;
    }
}
~~~

Đây là phương thức Java hợp lệ; `throw e;` ném lại **cùng đối tượng `IOException`**, không tạo một mắt xích cause mới. Nó giữ loại checked exception ban đầu theo hợp đồng.

Cần tránh ghi cùng một lỗi ở quá nhiều tầng: có thể gây log trùng, nhiễu tín hiệu và khó đếm số sự cố thực tế. Nếu tầng hiện tại không bổ sung quyết định hữu ích, đôi khi **không bắt rồi ném lại** là cách đơn giản hơn.

### Cách C — Bọc: đổi ý nghĩa lỗi nhưng giữ nguyên nhân

~~~java
static String loadServiceConfig(java.nio.file.Path path) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Không thể chuẩn bị cấu hình dịch vụ", cause);
    }
}
~~~

Phương thức này đổi từ checked `IOException` sang unchecked `IllegalStateException`. Đây là một **quyết định API**: caller tầng trên giờ nhận lỗi thuộc hợp đồng khác, nhưng có thể truy tìm `IOException` thông qua cause.

Không nên tự động dùng kiểu unchecked chỉ để khỏi viết `throws`. Nếu caller thực sự có cách xử lý lỗi I/O, việc giữ checked `IOException` hoặc dùng checked exception nghiệp vụ có thể thích hợp hơn.

## 5. Exception chaining qua nhiều tầng

Giả sử:

- Tầng I/O phát sinh `IOException`.
- Tầng cấu hình đổi nó thành `ConfigurationException`.
- Tầng khởi tạo dịch vụ đổi nó thành `StartupException`.

Mô hình mã:

~~~java
static void initializeService() {
    try {
        loadConfiguration();
    } catch (ConfigurationException cause) {
        throw new StartupException(
                "Không thể khởi động dịch vụ", cause);
    }
}
~~~

Đây là đoạn minh họa; `loadConfiguration()` và hai lớp ngoại lệ cần được định nghĩa. Chuỗi có thể mang ý nghĩa:

| Tầng | Loại lỗi | Message | Vai trò |
| --- | --- | --- | --- |
| Service | `StartupException` | Dịch vụ không thể khởi động | Hợp đồng tầng ứng dụng |
| Configuration | `ConfigurationException` | Không nạp được cấu hình | Ngữ cảnh xử lý cấu hình |
| I/O | `IOException` | Thiếu tệp hoặc kết nối hỏng | Nguyên nhân kỹ thuật ban đầu |

Mỗi tầng tạo một wrapper **chỉ khi có giá trị**. Nếu mọi tầng đều tạo một lỗi với message mơ hồ như `"Failed"`, chain sẽ dài nhưng không bổ sung thông tin.

### Cause là quan hệ “vì sao”, không nhất thiết là quan hệ subtype

Không cần mọi ngoại lệ trong chuỗi phải cùng lớp hoặc có quan hệ kế thừa. `StartupException`, `ConfigurationException` và `IOException` có thể thuộc các nhánh khác nhau của cây lớp ngoại lệ; chúng liên kết với nhau bằng **tham chiếu đối tượng cause**.

Do đó:

~~~java
Throwable cause = outer.getCause();
~~~

là quan hệ đối tượng, không phải phép ép `outer` thành kiểu của nguyên nhân. Đừng nhầm **quan hệ `extends`** giữa lớp với **quan hệ `getCause()`** giữa những lần lỗi cụ thể.

## 6. Cause tác động thế nào đến `catch`?

Một ngoại lệ được bắt theo **kiểu của đối tượng đang truyền tại thời điểm đó**, không tự động theo các kiểu nằm sâu trong cause.

~~~java
try {
    throw new IllegalStateException(
            "Không chạy được",
            new java.io.IOException("Không có tệp"));
} catch (IllegalStateException e) {
    System.out.println("Bắt được lỗi tầng ngoài");
}
~~~

Đoạn này hợp lệ trong một phương thức Java và khối `catch` sẽ được chạy.

Nhưng:

~~~java
try {
    throw new IllegalStateException(
            "Không chạy được",
            new java.io.IOException("Không có tệp"));
} catch (java.io.IOException e) {
    System.out.println("Không tới đây");
}
~~~

Đây là **phản ví dụ không biên dịch** vì khối `try` ở mã trên không có đường ném checked `IOException` trực tiếp; việc một `IllegalStateException` chứa `IOException` làm cause không biến nó thành một `IOException` được ném. Ngay cả khi bố cục `catch` hợp lệ do khối `try` còn lời gọi khác ném I/O, nhánh `catch (IOException e)` **không nhận được riêng đối tượng `IllegalStateException`** đang truyền.

Nếu API muốn caller xử lý tùy nguyên nhân, cần quyết định cách thiết kế hợp đồng: có thể giữ loại checked exception, sử dụng loại lỗi nghiệp vụ riêng hoặc có cơ chế kiểm tra cause **có kiểm soát** tại ranh giới thích hợp. Không biến việc duyệt chuỗi cause thành cách thay thế bừa bãi cho hợp đồng ngoại lệ rõ ràng.

## 7. Cause khác với việc nối chuỗi message

Phản ví dụ:

~~~java
catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "Không tải được cấu hình: " + cause.getMessage());
}
~~~

Đoạn trên chỉ nhúng **văn bản** của lỗi gốc vào message mới; `getCause()` của wrapper vẫn thường là `null`.

Phiên bản giữ quan hệ nguyên nhân:

~~~java
catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "Không tải được cấu hình", cause);
}
~~~

Hai đoạn là **những mảnh catch minh họa**, không phải một tệp Java độc lập. Phiên bản thứ hai cho phép công cụ:

- Lần theo nguyên nhân gốc có cấu trúc.
- Đọc stack trace riêng của lỗi thấp tầng.
- Nhận biết kiểu lỗi gốc mà không phải phân tích chuỗi.
- Đọc đầy đủ chuỗi cause của nhiều tầng.

Bạn vẫn có thể bổ sung thông tin an toàn vào message như tên tác vụ, tên tham số hoặc mã thao tác, nhưng **đừng chỉ dùng message thay cho cause**.

## 8. Java 17+ — chương trình chạy độc lập

Chương trình sau cố ý mô phỏng thất bại ở ba tầng. Nó có ví dụ thành công, ném lại không bọc, bọc nhiều tầng, cách làm mất liên kết và trường hợp lỗi đóng tài nguyên được giữ ở `suppressed` thay vì `cause`.

Lưu thành tệp **`ExceptionChainingDemo.java`**:

~~~java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class ExceptionChainingDemo {

    static final class ConfigurationException extends Exception {
        ConfigurationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class StartupException extends RuntimeException {
        StartupException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class ClosingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failure");
        }
    }

    public static void main(String[] args) {
        System.out.println("== success ==");
        System.out.println("status=" + start(false));

        System.out.println("== chained failure ==");
        try {
            start(true);
        } catch (StartupException e) {
            printChain(e);
            System.out.println("root="
                    + rootCause(e).getClass().getSimpleName());
        }

        System.out.println("== rethrow ==");
        try {
            rethrowOriginal();
        } catch (IOException e) {
            System.out.println("caught=" + e.getMessage());
        }

        System.out.println("== lost cause ==");
        try {
            loseCause();
        } catch (StartupException e) {
            System.out.println("message=" + e.getMessage());
            System.out.println("cause=" + e.getCause());
        }

        System.out.println("== suppressed ==");
        try (ClosingResource ignored = new ClosingResource()) {
            throw new ConfigurationException(
                    "work failed", new IOException("read failure"));
        } catch (Exception e) {
            System.out.println("primary=" + e.getMessage());
            System.out.println("cause=" + e.getCause().getMessage());
            System.out.println(
                    "suppressed=" + e.getSuppressed().length);
            System.out.println(
                    "suppressedMessage="
                            + e.getSuppressed()[0].getMessage());
        }
    }

    static String readFile(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("config missing");
        }
        return "ready";
    }

    static String loadConfig(boolean fail)
            throws ConfigurationException {
        try {
            return readFile(fail);
        } catch (IOException cause) {
            throw new ConfigurationException(
                    "load configuration failed", cause);
        }
    }

    static String start(boolean fail) {
        try {
            return loadConfig(fail);
        } catch (ConfigurationException cause) {
            throw new StartupException(
                    "service startup failed", cause);
        }
    }

    static void rethrowOriginal() throws IOException {
        try {
            readFile(true);
        } catch (IOException e) {
            throw e;
        }
    }

    static void loseCause() {
        try {
            loadConfig(true);
        } catch (ConfigurationException e) {
            throw new StartupException(
                    "text only: " + e.getMessage(), null);
        }
    }

    static void printChain(Throwable error) {
        Set<Throwable> visited =
                Collections.newSetFromMap(
                        new IdentityHashMap<Throwable, Boolean>());
        int depth = 0;
        Throwable current = error;

        while (current != null && visited.add(current)) {
            System.out.println(
                    "level" + depth + "="
                            + current.getClass().getSimpleName()
                            + ": " + current.getMessage());
            current = current.getCause();
            depth++;
        }
        if (current != null) {
            System.out.println("cycle detected");
        }
    }

    static Throwable rootCause(Throwable error) {
        Set<Throwable> visited =
                Collections.newSetFromMap(
                        new IdentityHashMap<Throwable, Boolean>());
        Throwable current = error;
        Throwable last = error;

        while (current != null && visited.add(current)) {
            last = current;
            current = current.getCause();
        }
        return last;
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ExceptionChainingDemo.java
java ExceptionChainingDemo
~~~

**Stdout chính xác:**

~~~text
== success ==
status=ready
== chained failure ==
level0=StartupException: service startup failed
level1=ConfigurationException: load configuration failed
level2=IOException: config missing
root=IOException
== rethrow ==
caught=config missing
== lost cause ==
message=text only: load configuration failed
cause=null
== suppressed ==
primary=work failed
cause=read failure
suppressed=1
suppressedMessage=close failure
~~~

### Giải thích từng tình huống

**Thành công:** `start(false)` gọi qua các tầng, `readFile(false)` trả `"ready"` và không có ngoại lệ nào được tạo trong các khối `catch`.

**Lỗi được liên kết:** `readFile(true)` ném `IOException("config missing")`. `loadConfig` bắt lỗi và tạo `ConfigurationException` có cause là đối tượng `IOException` ấy. `start` bắt `ConfigurationException` rồi tạo `StartupException` chứa nó làm cause. `printChain` đọc từng tầng và `rootCause` tìm tầng cuối.

**Ném lại nguyên bản:** `rethrowOriginal()` bắt `IOException` rồi `throw e;`. Không tạo wrapper hoặc chuỗi cause mới, do đó caller nhận đúng lỗi I/O và message gốc.

**Làm mất cause:** `loseCause()` tạo `StartupException` với tham số cause là `null`, chỉ sao chép một phần message. Caller không thể đi từ wrapper về `ConfigurationException` và `IOException` bằng `getCause()`. Đây là phản ví dụ có chủ đích.

**Lỗi phụ:** Try-with-resources có `ConfigurationException("work failed", IOException("read failure"))` làm lỗi chính; khi `ClosingResource.close()` ném `IOException("close failure")`, Java giữ lỗi đóng trong `getSuppressed()`. Cause của lỗi chính vẫn là `IOException("read failure")`; lỗi suppressed là một đối tượng khác.

## 9. Cách tìm nguyên nhân gốc an toàn

Cách đơn giản, khi bạn kiểm soát hoàn toàn chuỗi và biết nó không có vòng:

~~~java
Throwable current = error;
while (current.getCause() != null) {
    current = current.getCause();
}
~~~

Đây là **mảnh minh họa** giả định `error` không null và chuỗi không có vòng. `current` cuối cùng là một ngoại lệ không có cause.

Nhưng với những lớp `Throwable` tùy biến hoặc dữ liệu từ nhiều nguồn, một chuỗi cause có thể không kết thúc như kỳ vọng. `initCause` ngăn **tự làm cause trực tiếp**, nhưng không phải là lời hứa mọi chuỗi tùy ý đều không có vòng gián tiếp.

Mã độc lập nên có cơ chế phát hiện vòng bằng **identity của tham chiếu** (như `IdentityHashMap` trong chương trình chính). Không phụ thuộc vào `equals()` khi câu hỏi là “đây có phải cùng một đối tượng ngoại lệ hay không?”.

### Nguyên nhân sâu nhất không nhất thiết là kết luận nghiệp vụ

Một `IOException` sâu nhất chỉ nói rằng có lỗi I/O ở tầng thấp; ứng dụng có thể cần xử lý vấn đề ở mức `ConfigurationException` để thông báo cho người dùng hoặc quyết định retry. Đừng tự động bỏ qua mọi mắt xích ngoài và chỉ hiển thị exception cuối.

Ngoài ra, việc đọc chain và chọn thông điệp hiển thị cần cân nhắc dữ liệu nhạy cảm: cause sâu có thể chứa đường dẫn, thông tin kết nối, dữ liệu nhập hoặc thông tin kỹ thuật không nên đưa thẳng ra UI công khai.

## 10. `initCause`: phương án dự phòng khi không có constructor nhận cause

Một số lớp ngoại lệ cũ chỉ có constructor message. Nếu lớp cho phép, `Throwable.initCause(Throwable)` có thể gắn cause **một lần** sau khi tạo đối tượng:

~~~java
Throwable wrapped = new Throwable("legacy wrapper");
wrapped.initCause(new java.io.IOException("original"));
System.out.println(wrapped.getCause().getMessage());
// original
~~~

Dạng này thường ít được ưu tiên hơn:

~~~java
Throwable wrapped = new Throwable(
        "legacy wrapper",
        new java.io.IOException("original"));
~~~

Constructor giúp đối tượng hoàn chỉnh ngay từ đầu và giảm nguy cơ quên gắn nguyên nhân.

### Hai trạng thái có cùng `getCause() == null`

Một khác biệt rất quan trọng:

~~~java
Throwable open = new Throwable("message");
Throwable locked = new Throwable("message", null);

System.out.println(open.getCause());   // null
System.out.println(locked.getCause()); // null
~~~

Dù getter trả `null` ở cả hai, trạng thái cause khác nhau:

- `open`: constructor không nhận cause, vì vậy cause **chưa được khởi tạo**; `initCause(root)` có thể hợp lệ.
- `locked`: constructor có tham số cause đã **khởi tạo cause bằng null**; `initCause(root)` sẽ ném `IllegalStateException`.

Quy tắc `initCause`:

1. Chỉ dùng khi trạng thái cause chưa từng được khởi tạo.
2. Không đặt chính đối tượng đang xét thành cause trực tiếp của nó.
3. Sau lần thiết lập thành công, kể cả `initCause(null)`, không thể thiết lập lần nữa.

### Những lỗi `initCause` có thể ném

~~~java
Throwable a = new Throwable("A");
Throwable b = new Throwable("B");

a.initCause(b);     // Thành công.
a.initCause(null);  // IllegalStateException.
~~~

Đây là đoạn **minh họa có lỗi runtime ở câu cuối**, không phải ví dụ để chạy liên tục mà không xử lý lỗi.

Tự làm cause:

~~~java
Throwable a = new Throwable("A");
a.initCause(a); // IllegalArgumentException.
~~~

Không nên đưa cấu trúc cause vào trạng thái vòng lặp hoặc thay đổi nó ở nhiều vị trí trong luồng xử lý. Thiết kế tốt thường thiết lập cause **lúc tạo exception**, sau đó chỉ đọc nó.

## 11. Chuỗi nguyên nhân và checked/unchecked exceptions

Khi một ngoại lệ được bọc, **kiểu của wrapper** xác định nghĩa vụ checked/unchecked ở ranh giới phương thức hiện tại.

~~~java
static String loadConfiguration(java.nio.file.Path path) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Cấu hình không khả dụng", cause);
    }
}
~~~

Đây là một phương thức minh họa đầy đủ về cú pháp. `Files.readString` có thể ném checked `IOException`, nhưng phương thức bọc nó thành unchecked `IllegalStateException`. Vì vậy, caller của `loadConfiguration` không bị trình biên dịch yêu cầu `catch IOException` chỉ do cause là `IOException`.

Nếu muốn caller **phải** cân nhắc thất bại của bước cấu hình, có thể dùng lớp riêng kế thừa `Exception`:

~~~java
public class ConfigurationLoadException extends Exception {
    public ConfigurationLoadException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Lớp trên có thể lưu trong `ConfigurationLoadException.java`. Phương thức ném nó cần bắt hoặc khai báo theo quy tắc checked exception của Java.

**Cause không thay đổi loại checked/unchecked của wrapper.** `catch` ở caller xét kiểu của đối tượng được ném ra ngoài, không tự động duyệt cause để so khớp.

### Không bọc một ngoại lệ chỉ để thoát quy tắc `throws`

Việc đổi checked thành unchecked cần có lý do thiết kế: tầng gọi có khả năng phục hồi hay không, hợp đồng API muốn biểu đạt điều gì, và liệu việc buộc caller bắt ngoại lệ có mang lại lợi ích hay không.

Một câu hỏi hữu ích: **“Caller của tầng này cần biết loại thất bại nào để quyết định hành động tiếp theo?”** Câu trả lời thường quan trọng hơn việc giảm số dòng `try/catch`.

## 12. Exception chaining khác suppressed exceptions

Suppressed exceptions là **lỗi phụ được giữ lại** khi một lỗi chính vẫn được ưu tiên, đặc biệt trong try-with-resources. Chúng **không phải** những mắt xích cause tiếp theo.

Ví dụ:

~~~java
Throwable primary = new Throwable(
        "Lưu dữ liệu thất bại",
        new java.io.IOException("Ghi tệp thất bại"));

primary.addSuppressed(
        new java.io.IOException("Đóng luồng thất bại"));
~~~

Đây là đoạn Java minh họa. Kết quả:

~~~text
Throwable: Lưu dữ liệu thất bại
    |
    +-- cause --> IOException: Ghi tệp thất bại
    |
    +-- suppressed --> IOException: Đóng luồng thất bại
~~~

| Quan hệ | Phương thức đọc | Ý nghĩa |
| --- | --- | --- |
| Cause | `getCause()` | Một lỗi làm nguyên nhân cho lỗi khác |
| Suppressed | `getSuppressed()` | Một hoặc nhiều lỗi phụ được giữ lại mà không thay thế lỗi chính |

Không dùng `addSuppressed` thay cho việc lưu cause khi đang bọc lỗi giữa các tầng. Tương tự, lỗi khi đóng tài nguyên xuất hiện trong cùng quá trình dọn dẹp thường không nên được ép thành cause của lỗi nghiệp vụ ban đầu.

**Một ngoại lệ có thể đồng thời có cause và nhiều suppressed exceptions.** Khi phân tích log, cả hai có thể quan trọng.

## 13. Stack trace qua các mắt xích

Mỗi đối tượng `Throwable` thường có **stack trace riêng**, được ghi lúc tạo đối tượng theo cơ chế mặc định. Khi tạo wrapper mới:

~~~java
try {
    readFile();
} catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "Không thể khởi tạo", cause);
}
~~~

Đây là mảnh mã minh họa trong một phương thức có `readFile()` phù hợp.

- Stack trace của `cause` có thể chỉ ra nơi lỗi I/O được tạo/ném ban đầu.
- Stack trace của wrapper có thể cho biết nơi một tầng đã quyết định chuyển lỗi thành `IllegalStateException`.
- `printStackTrace()` thường trình bày thông tin nhiều tầng dưới dạng quan hệ `Caused by:`.

Không nên kiểm thử đầu ra `printStackTrace()` bằng cách so khớp từng dòng số thứ tự, đường dẫn tệp hay tên frame, vì chúng phụ thuộc điểm chạy và môi trường biên dịch. Trong ví dụ Java chạy được ở phần trên, đầu ra được xây bằng `getMessage()`, `getCause()` và tên lớp để có tính xác định.

### Dùng `throw e;` không tạo wrapper

Nếu ném lại cùng một đối tượng bằng `throw e;`, Java không tự thêm một mắt xích `getCause()` mới. Stack trace của đối tượng đó cũng không tự được viết lại hoàn toàn mỗi lần ném. Khi muốn bổ sung bối cảnh bằng một đối tượng ngoại lệ mới, hãy tạo wrapper với message và cause rõ nghĩa.

### Đừng biến stack trace thành hợp đồng máy đọc

Cause và stack trace có cấu trúc khác nhau. Dựa vào tên frame để chọn cách xử lý nghiệp vụ dễ hỏng khi refactor hoặc thay đổi JVM. Nếu cần quyết định máy móc, thiết kế mã lỗi hoặc loại exception cụ thể.

## 14. Khi nào nên tạo một mắt xích mới?

Một wrapper nên có mục đích. Cân nhắc các câu hỏi sau:

1. **Có ranh giới abstraction không?** Ví dụ từ I/O sang cấu hình, từ cấu hình sang khởi động dịch vụ.
2. **Message mới có bổ sung bối cảnh không?** Ví dụ thông báo tên thao tác hoặc trạng thái nghiệp vụ hợp lệ, không chỉ `"error"`.
3. **Caller sẽ xử lý loại ngoại lệ mới khác loại cũ không?**
4. **Cause có được giữ lại đầy đủ không?**
5. **Việc bọc có làm lộ chi tiết nội bộ vào API công khai không?** Có thể giữ cause cho log nội bộ nhưng dùng thông điệp người dùng riêng ở ranh giới UI.
6. **Có thêm giá trị chẩn đoán hay chỉ lặp lại một lỗi qua nhiều tầng?**

Bảng quyết định:

| Tình huống | Hướng thường hợp lý |
| --- | --- |
| Caller hiểu và xử lý được ngoại lệ gốc | Cho lan truyền hoặc ném lại |
| Tầng hiện tại có fallback hợp lệ | Xử lý và trả kết quả theo hợp đồng |
| Tầng hiện tại cần thay đổi abstraction | Bọc thành loại lỗi phù hợp, giữ cause |
| Chỉ muốn thêm log | Cân nhắc ghi một lần ở ranh giới giám sát, tránh catch/rethrow vô ích |
| Lỗi khi đóng tài nguyên phụ trong lúc đã có lỗi chính | Sử dụng suppressed exceptions theo cơ chế thích hợp |
| Muốn bọc lỗi nhưng chỉ có constructor message | Dùng `initCause` nếu được hỗ trợ hoặc cải tiến loại ngoại lệ |

Một chuỗi lỗi tốt **ngắn vừa đủ nhưng đủ ngữ cảnh**. Mỗi tầng mới cần giúp người đọc hiểu thêm *tại sao thao tác ở tầng đó không thành công*.

## 15. Khai báo lỗi của API và trải nghiệm người dùng

Exception chaining phục vụ hai đối tượng khác nhau:

- **Lập trình viên vận hành:** cần cause, stack trace, mã lỗi và bối cảnh kỹ thuật để điều tra.
- **Người dùng cuối:** cần câu trả lời rõ ràng, an toàn, có thể hành động — chẳng hạn “Không thể tải dữ liệu. Hãy thử lại sau.”

Không nên hiển thị nguyên toàn bộ `toString()` hoặc `printStackTrace()` của chuỗi cause ra giao diện công cộng. Các thông điệp kỹ thuật có thể vô tình chứa đường dẫn tệp, chuỗi kết nối, tham số truy vấn hoặc dữ liệu nhạy cảm.

Ở API công khai, có thể dùng:

- Một mã lỗi ổn định, ví dụ `CONFIG_UNAVAILABLE`.
- Thông điệp cho người dùng không tiết lộ nội bộ.
- Correlation/request ID để tìm log nội bộ tương ứng.
- Cause chain được lưu và xử lý ở hệ thống quan sát đáng tin cậy theo chính sách riêng tư.

**Không phải mọi chi tiết hữu ích trong log đều phù hợp để trả về cho bên gọi bên ngoài.**

## 16. Cẩn thận khi log nhiều lần qua các tầng

Một sai lầm phổ biến:

~~~java
catch (java.io.IOException e) {
    e.printStackTrace();
    throw new IllegalStateException("Service failed", e);
}
~~~

Đoạn này ghi lỗi tại tầng dưới rồi còn chuyển nó lên tầng trên. Nếu tầng trên cũng in stack trace, cùng sự cố có thể xuất hiện nhiều lần, gây khó đếm và làm log dài.

Cách tổ chức thường phù hợp:

- Tầng thấp **giữ nguyên cause**, không nhất thiết log mỗi lần chuyển lỗi.
- Tầng trung gian **bổ sung ngữ cảnh** khi thực sự thay đổi hợp đồng.
- Tầng biên của ứng dụng **ghi lỗi một lần** với đầy đủ chuỗi cause và correlation ID, khi cần.

Ngoại lệ có thể cần log ở nhiều nơi vì các mục tiêu khác nhau, nhưng đó nên là quyết định có chủ ý, không phải mặc định mọi `catch` đều `printStackTrace()`.

## 17. Một số loại wrapper thường gặp trong thư viện Java

Không phải exception chaining chỉ xuất hiện trong ngoại lệ tùy biến. Nhiều API Java dùng wrapper để biểu diễn sự khác biệt giữa lỗi gốc và bối cảnh gọi.

Ví dụ:

- `java.util.concurrent.ExecutionException` thường bọc lỗi của một tác vụ được lấy qua `Future.get()`.
- `java.util.concurrent.CompletionException` có thể bọc lỗi khi một chuỗi xử lý bất đồng bộ hoàn tất bất thường.
- `java.lang.reflect.InvocationTargetException` có thể giữ ngoại lệ được ném bởi phương thức được gọi qua reflection.

Khi làm việc với các API này, cần hiểu **loại wrapper của API** và cách truy cập cause theo hợp đồng. Tuy nhiên, không nên tùy tiện “unwrap” toàn bộ lỗi ở mọi tầng: một số wrapper mang ý nghĩa về cơ chế gọi hoặc ranh giới đồng bộ/bất đồng bộ cần được giữ.

Ví dụ tổng quát:

~~~java
try {
    future.get();
} catch (java.util.concurrent.ExecutionException e) {
    Throwable taskFailure = e.getCause();
    // Xử lý theo hợp đồng của tác vụ và tầng gọi.
}
~~~

Đây là đoạn minh họa; `future` cần là một `Future` và phương thức bao quanh còn phải đáp ứng các ngoại lệ checked khác của `get()` như `InterruptedException`. Đừng xem nó là chương trình độc lập.

## 18. Những sai lầm thường gặp

### Sai lầm 1 — Sao chép message nhưng bỏ cause

`new IllegalStateException("Failed: " + e.getMessage())` có thể làm mất quan hệ nguyên nhân. Dùng overload nhận cause khi cần bảo toàn lỗi gốc.

### Sai lầm 2 — Nhầm cause với lớp cha của exception

`getCause()` trả một **đối tượng lỗi**, không trả superclass trong cây kế thừa. Loại wrapper và loại cause có thể không liên quan về `extends`.

### Sai lầm 3 — Tưởng `catch` so khớp theo toàn chuỗi cause

Không. Handler nhận theo loại ngoại lệ đang truyền. `IOException` nằm trong cause không tự biến wrapper thành `IOException`.

### Sai lầm 4 — Bọc mọi lỗi qua mọi lớp

Chuỗi quá dài, message mơ hồ và log trùng làm việc điều tra khó hơn. Chỉ bọc khi cần ý nghĩa/hợp đồng mới.

### Sai lầm 5 — Thay đổi checked thành unchecked mà không xét hợp đồng

Wrapper quyết định nghĩa vụ biên dịch của caller. Đừng dùng unchecked chỉ để tránh xử lý lỗi được kỳ vọng.

### Sai lầm 6 — Dùng `getCause() == null` để đoán quyền gọi `initCause`

Cause có thể **đã được khởi tạo bằng null**. Getter trả null không chứng minh còn được gọi `initCause(...)`.

### Sai lầm 7 — Gọi `initCause` hai lần

`initCause` không phải setter thay đổi nguyên nhân liên tục. Gọi lại sau khi cause đã khởi tạo ném `IllegalStateException`.

### Sai lầm 8 — Tạo cause tự trỏ tới chính đối tượng

`error.initCause(error)` bị từ chối. Vòng gián tiếp giữa các đối tượng khác nhau cũng có thể khiến công cụ duyệt cause không an toàn nếu không phòng ngừa.

### Sai lầm 9 — Nhầm suppressed exception với cause

Lỗi đóng tài nguyên được giữ làm suppressed **không tự trở thành cause** của lỗi chính.

### Sai lầm 10 — Cho rằng lỗi gốc sâu nhất luôn là lỗi duy nhất quan trọng

Ngoại lệ ở tầng cao có thể mô tả hợp đồng nghiệp vụ rõ hơn, trong khi lỗi sâu nhất chỉ cung cấp chi tiết kỹ thuật.

### Sai lầm 11 — Tưởng wrapper có cause là chỉ cần in message wrapper

Message không thay thế stack trace và thông tin chuỗi nguyên nhân. Khi điều tra, dùng logging có cấu trúc và truyền nguyên đối tượng ngoại lệ đến bộ ghi log phù hợp.

### Sai lầm 12 — Đưa toàn bộ cause ra API công khai

Thông tin cause có thể lộ dữ liệu nội bộ. Tách thông điệp dành cho người dùng với dữ liệu quan sát nội bộ.

### Sai lầm 13 — Tái sử dụng một đối tượng exception cho nhiều sự cố

Cause, message và stack trace của một đối tượng thường phản ánh một bối cảnh cụ thể. Dùng lại cho những lỗi không liên quan dễ khiến việc chẩn đoán sai.

### Sai lầm 14 — Duyệt cause không kiểm tra vòng tham chiếu

Nếu lớp tùy biến hoặc nguồn dữ liệu bất thường tạo vòng, vòng lặp `while (getCause() != null)` có thể không dừng. Các tiện ích chung nên chặn vòng bằng identity.

### Sai lầm 15 — Nghĩ ném lại `throw e;` tạo thêm một mắt xích

Không. Nó ném lại **cùng đối tượng**, không tạo wrapper mới và không tự cập nhật cause.

## 19. Câu hỏi tự kiểm tra

1. Exception chaining giải quyết vấn đề gì khi lỗi đi qua nhiều tầng?
2. `getCause()` trả trực tiếp loại dữ liệu nào?
3. Một exception có thể có message và cause độc lập với nhau không?
4. `outer.getCause() == original` nói lên điều gì?
5. `getCause()` đi đến lỗi sâu nhất hay chỉ một tầng?
6. Khi nào nên `throw e;` thay vì `throw new WrapperException("...", e);`?
7. Khi nào nên phục hồi và không cần lan truyền lỗi?
8. Nếu chỉ nối `e.getMessage()` vào chuỗi, điều gì có thể bị mất?
9. Vì sao `catch (IOException)` không bắt `IllegalStateException` có cause là `IOException`?
10. Quan hệ `extends` giữa lớp và quan hệ cause giữa đối tượng khác nhau thế nào?
11. Nếu wrapper là unchecked nhưng cause là checked, caller có buộc bắt cause theo quy tắc checked không?
12. Suppressed exceptions được dùng cho tình huống nào khác cause?
13. Có thể đồng thời có cause và suppressed exceptions không?
14. Dùng `initCause` trong trường hợp nào là hợp lý?
15. Vì sao `new Throwable("x", null)` không cho `initCause(...)` lần nữa?
16. Việc ném lại cùng một exception có tự tạo wrapper và cause mới không?
17. Tại sao logger có thể cần cả stack trace của wrapper và cause?
18. Vì sao một phương thức tìm lỗi gốc nên bảo vệ khỏi vòng cause?
19. Nguyên nhân sâu nhất có luôn là thông báo tốt nhất cho người dùng không?
20. Tại sao cần tránh in toàn bộ cause chain ra API công khai?
21. Nêu ví dụ một wrapper của thư viện chuẩn Java và vai trò của cause.
22. Tại sao ghi cùng exception ở mọi tầng thường gây vấn đề?
23. Nếu chỉ có một nguyên nhân I/O đơn giản đã phù hợp hợp đồng, có nhất thiết phải bọc không?
24. Khi lớp ngoại lệ tùy biến cần cause, constructor nên gọi phương thức nào của lớp cha?
25. Khi nhìn thấy `getSuppressed().length > 0`, có thể suy ra `getCause() != null` không?

### Đáp án gợi ý

1. Giữ nguyên nhân kỹ thuật khi bổ sung ngữ cảnh ở các tầng cao.
2. Một tham chiếu `Throwable` hoặc `null`.
3. Có; constructor nhận `(String, Throwable)` thể hiện điều đó.
4. Cause là **cùng đối tượng** `original`.
5. Chỉ một tầng.
6. Ném lại khi giữ nguyên hợp đồng/loại lỗi phù hợp; bọc khi cần đổi abstraction và thêm ngữ cảnh.
7. Khi tầng hiện tại có kết quả thay thế hợp lệ theo hợp đồng.
8. Liên kết cause, kiểu lỗi gốc và stack trace có cấu trúc.
9. Handler so khớp loại ngoại lệ đang truyền, không tự duyệt cause.
10. `extends` là quan hệ giữa lớp; cause là liên kết giữa những đối tượng lỗi cụ thể.
11. Không chỉ vì cause; nghĩa vụ checked phụ thuộc lỗi đang được ném và chữ ký API.
12. Những lỗi phụ được giữ khi ưu tiên một lỗi chính, ví dụ lỗi đóng tài nguyên.
13. Có.
14. Khi API không có constructor nhận cause nhưng đối tượng chưa khởi tạo cause và lớp cho phép.
15. Constructor đã khởi tạo cause bằng null.
16. Không.
17. Chúng mô tả những vị trí/ngữ cảnh khác nhau trên đường xảy ra và chuyển đổi lỗi.
18. Để tránh duyệt vô hạn khi có liên kết nguyên nhân vòng.
19. Không; lỗi tầng nghiệp vụ có thể phù hợp hơn.
20. Có thể lộ thông tin kỹ thuật và dữ liệu nhạy cảm.
21. Ví dụ `ExecutionException` giữ lỗi tác vụ làm cause.
22. Gây log trùng, nhiễu tín hiệu và khó đếm sự cố.
23. Không, có thể truyền tiếp hoặc ném lại.
24. `super(message, cause)` khi có overload phù hợp.
25. Không; cause và suppressed là hai quan hệ độc lập.

## 20. Ghi nhớ

**Exception chaining bảo toàn quan hệ “lỗi này xảy ra vì lỗi nào” qua `Throwable.getCause()`.** Khi chuyển một lỗi từ tầng kỹ thuật sang tầng nghiệp vụ, hãy bổ sung message có ý nghĩa và giữ chính ngoại lệ gốc làm cause bằng constructor `(String, Throwable)`. Chỉ dùng `initCause` cho trường hợp đặc biệt chưa được khởi tạo nguyên nhân. Phân biệt **cause** với **suppressed exceptions**, **throw lại cùng đối tượng** với **tạo wrapper mới**, và **kiểu lỗi tầng ngoài** với **loại nguyên nhân nằm bên trong**. Một chuỗi ngoại lệ tốt giúp API rõ ràng và quá trình chẩn đoán chính xác mà không làm lộ thông tin nội bộ không cần thiết.