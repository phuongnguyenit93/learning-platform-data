# Chuyển sang API công khai thay cho cách truy cập nội bộ khi nâng cấp lên Java 17

Khi nâng cấp ứng dụng lên Java 17, code có thể lỗi do phụ thuộc vào API nội bộ của JDK. Hướng xử lý là thay các phụ thuộc đó bằng API công khai được tài liệu hóa và có hợp đồng tương thích.

JDK 17 là mốc quan trọng vì JEP 403 bật strong encapsulation cho phần lớn thành phần nội bộ của JDK theo mặc định. Vì vậy, thư viện từng đọc field private của JDK hoặc gọi class nội bộ có thể gặp lỗi lúc biên dịch hoặc runtime. Bài viết trình bày cách nhận diện phụ thuộc, chọn API thay thế và chuyển đổi theo từng use case.

## 1. API công khai và API nội bộ khác nhau thế nào?

**API công khai** là API được công bố trong tài liệu chính thức và có hợp đồng sử dụng. Ví dụ:

- Java SE API trong các package như `java.util`, `java.nio`, `java.lang.invoke`, `java.security`.
- API được tài liệu hóa trong các module JDK, chẳng hạn một số API thuộc `jdk.jfr` hoặc `jdk.httpserver`. Đây có thể là API JDK được hỗ trợ nhưng không nhất thiết thuộc Java SE chuẩn.

**API nội bộ** là thành phần phục vụ implementation của JDK, không phải hợp đồng công khai dành cho ứng dụng. Những package thường cần kiểm tra gồm:

- `jdk.internal.*`.
- Nhiều package `sun.*`.
- Một số package `com.sun.*`.
- Các class, field hoặc method không được export/open dù có thể tìm thấy bằng reflection.

Không nên kết luận chỉ dựa vào prefix. Một số package `com.sun.*` có tài liệu API công khai, ví dụ API được cung cấp qua module JDK và được mô tả trong Javadoc. Hãy kiểm tra tài liệu chính thức, module sở hữu package và kết quả `jdeps` trước khi phân loại.

### 1.1. Vì sao không nên phụ thuộc vào API nội bộ?

Phụ thuộc nội bộ gây ra một số rủi ro:

1. **Không có cam kết tương thích:** implementation có thể đổi tên class, field, method hoặc cấu trúc dữ liệu.
2. **Khác biệt giữa nhà cung cấp:** một package nội bộ có thể tồn tại trong một bản JDK nhưng không có hoặc hoạt động khác ở bản khác.
3. **Bị giới hạn bởi module:** package không export không thể được truy cập như API thông thường từ module khác.
4. **Deep reflection bị chặn:** mở quyền truy cập field/method private của JDK có thể ném `InaccessibleObjectException`.
5. **Khó bảo trì và bảo mật:** code phụ thuộc cấu trúc nội bộ khiến JDK khó thay đổi implementation an toàn.

Việc code chạy được trên một bản JDK không chứng minh API đó được hỗ trợ. Điều cần kiểm tra là API có được tài liệu hóa và công bố như một hợp đồng cho ứng dụng hay không.

### 1.2. JEP 403 và Java 17

JEP 403, *Strongly Encapsulate JDK Internals by Default*, được áp dụng từ Java 17. Phần lớn thành phần nội bộ của JDK được đóng gói mạnh theo mặc định. Điều này có nghĩa:

- Code không thể mặc định truy cập các package nội bộ như API công khai.
- Reflection vào field/method không public của nhiều class JDK có thể bị từ chối.
- Việc một package được export cho truy cập kiểu public không đồng nghĩa package đó được open cho deep reflection.
- Tùy chọn `--illegal-access` đã lỗi thời trong Java 17; nếu xuất hiện trên command line, JVM phát cảnh báo và không dùng nó để nới quyền truy cập.

JEP 403 có một số ngoại lệ quan trọng cho các API nội bộ được giữ lại vì lý do tương thích, trong đó có `sun.misc.Unsafe`. Việc một class vẫn truy cập được không biến nó thành API công khai được hỗ trợ. Không nên dùng ngoại lệ này làm cơ sở cho code mới.

## 2. Xác định code đang phụ thuộc API nội bộ

Trước khi thay code, hãy lập danh sách phụ thuộc trong source, thư viện và runtime. Chỉ tìm trong source của ứng dụng là chưa đủ vì dependency bên thứ ba cũng có thể dùng JDK internals.

### 2.1. Dùng jdeps --jdk-internals

`jdeps` là công cụ phân tích phụ thuộc class và module đi kèm JDK. Tùy chọn `--jdk-internals` tìm tham chiếu tới API nội bộ của JDK.

Ví dụ phân tích một JAR:

~~~bash
jdeps --jdk-internals application.jar
~~~

Nếu ứng dụng có dependency ở classpath:

~~~bash
jdeps --jdk-internals --class-path "lib/*" application.jar
~~~

Với multi-release JAR, chỉ định phiên bản class cần phân tích:

~~~bash
jdeps --jdk-internals --multi-release 17 application.jar
~~~

Tên ngắn `-jdkinternals` cũng được hỗ trợ, nhưng nên dùng tên dài `--jdk-internals` trong script mới để dễ đọc.

Kết quả có thể cho biết class nào tham chiếu package nội bộ và gợi ý API thay thế. Ví dụ, tham chiếu tới `sun.misc.BASE64Encoder` được thay bằng `java.util.Base64`.

### 2.2. Phân tích cả dependency

Ứng dụng có thể không import API nội bộ trực tiếp nhưng một thư viện cũ lại dùng chúng. Hãy phân tích toàn bộ artifact triển khai:

~~~bash
jdeps --jdk-internals --class-path "lib/*" application.jar
~~~

Đối với ứng dụng modular, bổ sung module path phù hợp:

~~~bash
jdeps --jdk-internals --module-path "mods:lib" application.jar
~~~

Dấu phân cách đường dẫn trong ví dụ trên là dấu hai chấm của Linux/macOS. Trên Windows, classpath và module path thường dùng dấu chấm phẩy.

Hãy dùng đúng phiên bản `jdeps` trong JDK 17 hoặc toolchain mục tiêu để phân tích artifact theo môi trường sẽ triển khai.

### 2.3. Giới hạn của jdeps

`jdeps` phân tích bytecode tĩnh. Công cụ hữu ích nhưng không phát hiện mọi đường truy cập nội bộ. Cần rà soát thêm:

- Reflection dùng tên class hoặc member được ghép từ chuỗi.
- `Class.forName`, `getDeclaredField`, `getDeclaredMethod` hoặc `MethodHandles` để truy cập class nội bộ.
- Tên package/class nằm trong file cấu hình, plugin descriptor hoặc script.
- JNI/native code tự tìm symbol hoặc truy cập cấu trúc nội bộ.
- Dependency được nạp động mà không có trong artifact đang phân tích.

Tìm kiếm sơ bộ trong source có thể giúp phát hiện các import đáng ngờ:

~~~bash
rg -n "sun[.]|jdk[.]internal[.]|com[.]sun[.]" src
~~~

Tìm chuỗi reflection:

~~~bash
rg -n "Class[.]forName|getDeclared(Field|Method|Constructor)|setAccessible|privateLookupIn" src
~~~

Các lệnh tìm kiếm này tạo danh sách cần xem xét, không phải bằng chứng rằng mọi kết quả đều là API nội bộ. Có thể có package công khai mang prefix tương tự hoặc reflection được dùng hợp lệ trong code của chính ứng dụng.

### 2.4. Kiểm tra ở compile time và runtime

Khi build bằng JDK 17, compiler có thể báo package không được export hoặc không tìm thấy class đã bị loại bỏ. Nhưng phụ thuộc reflection có thể chỉ lỗi khi chạy.

Vì vậy, cần kết hợp:

1. Phân tích bytecode và dependency bằng `jdeps`.
2. Biên dịch với toolchain Java 17.
3. Chạy test trên JDK 17 thực tế.
4. Kiểm tra log startup và các đường code dùng reflection/plugin.
5. Thử những chức năng chỉ chạy trong production như serialization, logging, proxy, driver và instrumentation.

## 3. Bảng chuyển đổi từ API nội bộ sang API công khai

Bảng dưới đây là các trường hợp phổ biến khi nâng cấp. Không phải mọi API nội bộ đều có một thay thế tương đương một-một; một số trường hợp cần thay đổi thiết kế.

| Cách truy cập nội bộ | API công khai nên xem xét | Ghi chú |
| --- | --- | --- |
| `sun.misc.BASE64Encoder` / `BASE64Decoder` | `java.util.Base64` | Có encoder/decoder cơ bản, URL-safe và MIME |
| `sun.reflect.Reflection.getCallerClass` | `java.lang.StackWalker` | API stack walking có từ Java 9 |
| Nhiều thao tác field/array atomic của `sun.misc.Unsafe` | `VarHandle` hoặc `java.util.concurrent.atomic` | Phải giữ đúng memory ordering và atomic semantics |
| `sun.misc.Cleaner` | `java.lang.ref.Cleaner` | Cleaner là cơ chế fallback; vẫn ưu tiên đóng tài nguyên tường minh |
| Định nghĩa class qua internal API | `MethodHandles.Lookup.defineClass` hoặc `defineHiddenClass` | Bị ràng buộc package, lookup và class loader |
| Truy cập bộ nhớ qua internal direct-buffer class | `ByteBuffer`, `ByteBuffer.allocateDirect` | Không cung cấp mọi khả năng của Unsafe/native pointer |
| Đọc private field/method của class JDK | Public method/API chính thức tương ứng | `MethodHandles` không phải cách vượt qua module boundary |
| `sun.security.*` | `java.security`, `java.security.cert`, `javax.crypto`, `javax.net.ssl` | Chọn API theo thao tác security cụ thể |
| Parser XML nội bộ của JDK | JAXP, StAX, DOM, SAX | Dùng API parser được tài liệu hóa |
| Compiler implementation nội bộ | `javax.tools`, `javax.lang.model` và API compiler được tài liệu hóa | Chọn API theo nhu cầu compile hoặc phân tích source |

## 4. Thay Base64 nội bộ bằng java.util.Base64

Một ví dụ migration rõ ràng là `sun.misc.BASE64Encoder` và `sun.misc.BASE64Decoder`. Các class này đã bị loại bỏ từ JDK 9. API công khai `java.util.Base64` có từ Java 8 và là lựa chọn phù hợp trên Java 17.

### 4.1. Mã hóa và giải mã cơ bản

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Base64Example {
    public static void main(String[] args) {
        String message = "Hello Java 17";
        byte[] input = message.getBytes(StandardCharsets.UTF_8);

        String encoded = Base64.getEncoder().encodeToString(input);
        byte[] decoded = Base64.getDecoder().decode(encoded);

        String result = new String(decoded, StandardCharsets.UTF_8);
        System.out.println(encoded);
        System.out.println(result);
    }
}
~~~

Không dùng charset mặc định khi chuyển văn bản sang byte. Chỉ định UTF-8 nếu đó là encoding của giao thức hoặc dữ liệu.

### 4.2. Chọn đúng biến thể encoder

`Base64` có ba biến thể:

| API | Trường hợp sử dụng |
| --- | --- |
| `Base64.getEncoder()` / `getDecoder()` | Base64 cơ bản theo alphabet chuẩn |
| `Base64.getUrlEncoder()` / `getUrlDecoder()` | Dữ liệu dùng trong URL hoặc tên file |
| `Base64.getMimeEncoder()` / `getMimeDecoder()` | Dữ liệu MIME, có quy tắc ngắt dòng |

Không thay thế máy móc chỉ tên class. Hãy kiểm tra định dạng cũ có chèn line break, dùng alphabet URL-safe hoặc thêm padding ra sao. Chọn encoder tương ứng và kiểm thử với dữ liệu đã lưu hoặc giao thức bên ngoài.

## 5. Thay Reflection.getCallerClass bằng StackWalker

Một số thư viện cũ dùng `sun.reflect.Reflection.getCallerClass` để tìm class gọi vào helper. API công khai `StackWalker` được giới thiệu từ Java 9 và cho phép duyệt stack theo cách có kiểm soát.

### 5.1. Lấy caller class

~~~java
import java.lang.StackWalker;

public final class CallerInfo {
    private static final StackWalker WALKER =
            StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

    private CallerInfo() {
    }

    public static Class<?> callerClass() {
        return WALKER.getCallerClass();
    }
}
~~~

Khi gọi `CallerInfo.callerClass()`, phương thức trả về class gọi phương thức helper này. `RETAIN_CLASS_REFERENCE` cho phép giữ tham chiếu `Class<?>` trong stack frame.

### 5.2. Lọc stack frame

Nếu cần bỏ qua một số lớp trung gian, dùng `walk` và xử lý stream:

~~~java
Class<?> caller = StackWalker.getInstance(
        StackWalker.Option.RETAIN_CLASS_REFERENCE)
        .walk(frames -> frames
                .map(StackWalker.StackFrame::getDeclaringClass)
                .filter(type -> type != CallerInfo.class)
                .findFirst()
                .orElseThrow());
~~~

Đoạn minh họa cần điều chỉnh bộ lọc theo stack thực tế của ứng dụng. Stack có thể chứa proxy, framework hoặc lớp adapter; không nên giả định vị trí cố định bằng một chỉ số frame nếu cấu trúc call stack có thể đổi.

Stack walking cũng không phải cơ chế xác thực người dùng hoặc phân quyền. Caller class chỉ là thông tin kỹ thuật về luồng gọi hiện tại.

## 6. Thay một số thao tác Unsafe bằng VarHandle

`sun.misc.Unsafe` cung cấp nhiều thao tác cấp thấp như đọc/ghi field theo offset, compare-and-set, truy cập mảng và memory fence. Java 17 vẫn giữ một số API Unsafe vì tương thích, nhưng đây là API nội bộ và không phải hợp đồng công khai để xây dựng ứng dụng mới.

`VarHandle` được giới thiệu từ Java 9 để truy cập biến với các chế độ memory ordering được định nghĩa. Nó hỗ trợ field instance, static field, phần tử array và một số dạng biến khác.

### 6.1. Atomic counter bằng AtomicInteger

Nếu nhu cầu chỉ là bộ đếm đồng thời, lớp atomic thường đơn giản hơn VarHandle:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class RequestCounter {
    private final AtomicInteger count = new AtomicInteger();

    public int increment() {
        return count.incrementAndGet();
    }

    public int current() {
        return count.get();
    }
}
~~~

Không cần truy cập field offset hoặc tự viết compare-and-swap loop cho trường hợp phổ biến này.

### 6.2. VarHandle cho một field

Khi cần kiểm soát trực tiếp các access mode, có thể dùng VarHandle:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class Counter {
    private int count;

    private static final VarHandle COUNT;

    static {
        try {
            COUNT = MethodHandles.lookup().findVarHandle(
                    Counter.class, "count", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public int increment() {
        return (int) COUNT.getAndAdd(this, 1) + 1;
    }

    public int current() {
        return (int) COUNT.getVolatile(this);
    }
}
~~~

`MethodHandles.lookup()` ở trong class `Counter` có quyền tìm private field của chính class đó. Lookup được tạo từ code của class khác có thể không có cùng quyền.

VarHandle có các access mode như:

- `get`, `set`: truy cập plain.
- `getVolatile`, `setVolatile`: truy cập volatile.
- `getAcquire`, `setRelease`: cung cấp acquire/release semantics.
- `compareAndSet`, `compareAndExchange`: cập nhật nguyên tử có điều kiện.
- `getAndAdd`, `getAndSet`: cập nhật nguyên tử theo giá trị.

### 6.3. Không thay Unsafe bằng VarHandle một cách máy móc

Các thao tác cấp thấp có thể dựa vào memory ordering rất cụ thể. Khi chuyển sang VarHandle:

1. Xác định field hoặc vùng dữ liệu thực sự được truy cập.
2. Xác định thao tác plain, opaque, acquire/release hay volatile mà code cần.
3. Chọn access mode tương ứng.
4. Giữ nguyên thứ tự quan sát giữa các thread theo Java Memory Model.
5. Kiểm thử các trường hợp cạnh tranh, không chỉ kiểm tra kết quả trong một thread.

Không nên đổi mọi lời gọi Unsafe thành `getVolatile` hoặc `compareAndSet` theo một quy tắc chung. Hai API có thể khác về semantics và yêu cầu đồng bộ.

### 6.4. Không có thay thế một-một cho mọi Unsafe method

Một số thao tác Unsafe không có API Java SE tương đương trực tiếp. Ví dụ, cấp phát object mà không chạy constructor hoặc thao tác với native address tùy ý thường đòi hỏi thay đổi thiết kế.

Các lựa chọn nên cân nhắc:

- Dùng constructor, factory hoặc builder để tạo object theo hợp đồng công khai.
- Dùng `System.arraycopy`, array API hoặc `ByteBuffer` cho thao tác dữ liệu phù hợp.
- Dùng `AtomicInteger`, `AtomicLong`, `AtomicReference` hoặc `VarHandle` cho đồng bộ.
- Dùng JNI hoặc một thư viện native có hợp đồng rõ ràng khi thật sự cần tương tác native.

Không chọn một API chỉ vì tên hoặc khả năng có vẻ gần giống. Phải xác định chính xác hành vi cần giữ.

## 7. Thay Cleaner nội bộ bằng java.lang.ref.Cleaner

Nếu code dùng `sun.misc.Cleaner` hoặc một internal cleaner để giải phóng tài nguyên, API công khai hiện có là `java.lang.ref.Cleaner`, được thêm từ Java 9.

Tuy nhiên, Cleaner không nên thay thế việc đóng tài nguyên tường minh. Nếu tài nguyên có thể đóng chủ động, hãy cung cấp `close()` và triển khai `AutoCloseable` để caller dùng try-with-resources. Cleaner chỉ là cơ chế dự phòng khi object bị thu gom mà caller quên đóng.

Ví dụ cấu trúc:

~~~java
import java.lang.ref.Cleaner;

public final class NativeResource implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private long handle;

        State(long handle) {
            this.handle = handle;
        }

        @Override
        public synchronized void run() {
            if (handle != 0) {
                releaseNativeHandle(handle);
                handle = 0;
            }
        }
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    public NativeResource(long handle) {
        this.state = new State(handle);
        this.cleanable = CLEANER.register(this, state);
    }

    @Override
    public void close() {
        cleanable.clean();
    }

    private static void releaseNativeHandle(long handle) {
        // Gọi API native được quản lý bởi ứng dụng.
    }
}
~~~

`State` không giữ tham chiếu tới `NativeResource`, tránh tạo vòng tham chiếu khiến Cleaner không thể thu gom object sở hữu. Trong ứng dụng thực tế, việc giải phóng native handle phải bảo đảm an toàn khi gọi lặp lại và đồng bộ với các thao tác đang dùng handle.

Caller sử dụng:

~~~java
try (NativeResource resource = new NativeResource(handle)) {
    useResource(resource);
}
~~~

## 8. Định nghĩa class bằng MethodHandles.Lookup

Một số framework cũ dùng internal API để định nghĩa class vào class loader. Java cung cấp các API công khai trong `MethodHandles.Lookup`:

- `Lookup.defineClass(byte[])` từ Java 9.
- `Lookup.defineHiddenClass(...)` từ Java 15.

Ví dụ:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> generated = lookup.defineClass(classBytes);
~~~

`defineClass` định nghĩa class trong cùng runtime package, class loader và protection domain tương ứng với lookup class. Bytecode phải có package phù hợp; lookup phải có quyền cần thiết.

Với class được sinh ra chỉ để runtime dùng nội bộ và không cần tên nhị phân thông thường, có thể xem `defineHiddenClass`. Hidden class có vòng đời và quy tắc liên kết khác class thông thường, nên không phải thay thế chung cho mọi tình huống.

Không dùng API này để định nghĩa class tùy ý vào package của JDK. Module, package và quyền của Lookup vẫn được áp dụng.

## 9. Thay truy cập bộ nhớ nội bộ bằng ByteBuffer và API phù hợp

Một số thư viện dùng internal class như `sun.nio.ch.DirectBuffer` hoặc Unsafe để truy cập trực tiếp bộ nhớ. Nếu nhu cầu là đọc/ghi dữ liệu theo buffer, hãy xem `java.nio.ByteBuffer`.

~~~java
import java.nio.ByteBuffer;

ByteBuffer heapBuffer = ByteBuffer.allocate(1024);
ByteBuffer directBuffer = ByteBuffer.allocateDirect(1024);

directBuffer.putInt(42);
directBuffer.flip();
int value = directBuffer.getInt();
~~~

`ByteBuffer.allocateDirect` tạo direct buffer phù hợp cho một số luồng I/O hoặc tương tác native có hỗ trợ. Nó không cung cấp API công khai để tùy ý lấy và thao tác mọi native address như Unsafe. Vòng đời giải phóng bộ nhớ direct buffer cũng không tương đương với một API close tường minh trên ByteBuffer.

Nếu cần quản lý tài nguyên native có vòng đời xác định, hãy đóng gói native handle trong một abstraction `AutoCloseable`. Nếu cần truy cập native function hoặc native memory theo một hợp đồng khác, đánh giá JNI hoặc giải pháp native được duy trì. Không dùng một package nội bộ chỉ để lấy địa chỉ buffer.

## 10. Chuyển từ sun.security.* sang Java Security API

Các package `sun.security.*` chứa implementation của JDK, không phải API chung cho ứng dụng. Khi xử lý certificate, key, signature hoặc TLS, hãy chọn API theo nghiệp vụ:

| Nhu cầu | API công khai |
| --- | --- |
| Đọc và parse certificate | `java.security.cert.CertificateFactory` |
| Truy cập certificate và certificate path | `java.security.cert` |
| Quản lý key và key pair | `java.security.Key`, `KeyPair`, `KeyStore`, `KeyFactory` |
| Tạo/kiểm tra chữ ký | `java.security.Signature` |
| Mã hóa và giải mã | `javax.crypto.Cipher` |
| MAC và key derivation phù hợp | `javax.crypto.Mac`, `SecretKeyFactory` |
| TLS client/server | `javax.net.ssl.SSLContext`, `SSLSocket`, `SSLEngine` |
| Thuật toán/provider | `java.security.Provider` và provider API được tài liệu hóa |

Không phải mọi thao tác tạo certificate hoặc cấu trúc X.509 đều có một method Java SE đơn giản thay cho class nội bộ cũ. Nếu API công khai không đáp ứng nghiệp vụ, dùng thư viện bảo mật được duy trì với hợp đồng và chính sách tương thích rõ ràng. Tránh tự thao tác cấu trúc private của JDK.

## 11. Chuyển parser XML nội bộ sang JAXP, StAX, DOM hoặc SAX

Một ứng dụng có thể tham chiếu trực tiếp parser được đóng gói bên trong JDK, ví dụ implementation Xerces nội bộ. Thay vì phụ thuộc implementation, hãy lập trình theo API XML công khai:

- `javax.xml.parsers`: tạo DOM parser hoặc SAX parser.
- `javax.xml.stream`: StAX streaming API.
- `org.w3c.dom`: mô hình cây DOM.
- `org.xml.sax`: callback SAX.
- `javax.xml.transform`: chuyển đổi XML.

Ví dụ tạo DOM parser:

~~~java
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
DocumentBuilder builder = factory.newDocumentBuilder();
var document = builder.parse(inputStream);
~~~

Đối với XML không đáng tin cậy, cấu hình parser an toàn theo yêu cầu của ứng dụng: tắt external entities hoặc external DTD khi không cần, giới hạn truy cập external schema và kiểm tra chính sách XXE. Việc chuyển sang API công khai không tự động bảo đảm cấu hình parser an toàn.

## 12. Chuyển compiler implementation sang API được tài liệu hóa

Nếu công cụ build hoặc plugin phụ thuộc trực tiếp vào implementation nội bộ của javac, hãy xem các API:

- `javax.tools.JavaCompiler` để gọi compiler.
- `javax.tools.DiagnosticCollector` để thu thập lỗi/cảnh báo.
- `javax.lang.model` để truy cập model của chương trình.
- `com.sun.source.tree` và `com.sun.source.util` cho các API compiler tree được tài liệu hóa trong module `jdk.compiler`.

Ví dụ lấy compiler chuẩn:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("A full JDK is required");
}
~~~

Các API này cho phép công cụ tích hợp với compiler mà không cần truy cập class implementation nội bộ. Kiểm tra module và tài liệu JDK 17 cho API cụ thể đang dùng; một API được tài liệu hóa trong module JDK vẫn có thể không thuộc Java SE chuẩn.

## 13. Strong encapsulation: exports, opens và các tùy chọn tạm thời

Java Platform Module System phân biệt truy cập API công khai với deep reflection.

### 13.1. --add-exports

`--add-exports` cho phép một module đọc truy cập các kiểu public trong package mà module nguồn chưa export cho module đích.

Cú pháp:

~~~text
--add-exports source.module/package=target.module
~~~

Ví dụ:

~~~bash
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -jar application.jar
~~~

Đây là ví dụ minh họa một package nội bộ cụ thể; chỉ dùng khi đã xác định rõ dependency cần nó. `ALL-UNNAMED` áp dụng cho code chạy trên classpath. Tùy chọn `--add-exports` cũng có thể được truyền cho compiler khi cần biên dịch code phụ thuộc package đó.

### 13.2. --add-opens

`--add-opens` mở package cho deep reflection vào các thành viên không public tại runtime:

~~~text
--add-opens source.module/package=target.module
~~~

Ví dụ:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar application.jar
~~~

Tùy chọn này thường dùng tạm thời khi thư viện cũ cần reflection vào field/method private của class JDK. Nó không phải giải pháp thay thế API công khai và không sửa source code phụ thuộc nội bộ.

### 13.3. --illegal-access không còn là giải pháp trên Java 17

Trong Java 9 đến Java 16, `--illegal-access` từng hỗ trợ giai đoạn chuyển tiếp cho một số truy cập reflection. Từ Java 17, tùy chọn này đã obsolete: JVM phát cảnh báo và không thay đổi chính sách encapsulation.

Không thêm `--illegal-access=permit` hoặc các biến thể khác vào command line để sửa lỗi Java 17. Hãy cập nhật dependency, thay API nội bộ hoặc xác định package cụ thể cần mở trong thời gian chuyển tiếp.

### 13.4. Khi nào có thể dùng add-exports/add-opens?

Chỉ cân nhắc chúng như biện pháp tương thích tạm thời khi:

- Dependency chưa có bản sửa và chưa thể thay thế ngay.
- Đã xác định chính xác module/package cần quyền.
- Có giới hạn phạm vi và kế hoạch nâng cấp dependency.
- Có test xác nhận cấu hình hoạt động trên runtime mục tiêu.

Hạn chế mở package rộng. Mỗi package được export/open bổ sung làm tăng phạm vi code có thể truy cập vào implementation nội bộ.

## 14. Quy trình migration thực tế

Một quy trình nâng cấp có thể chia thành các bước sau.

### Bước 1: Lập baseline

- Ghi nhận JDK hiện tại và JDK đích.
- Ghi lại các dependency, plugin, agent và native library.
- Lưu command line và module/classpath đang triển khai.
- Chạy test hiện tại để có baseline hành vi.

### Bước 2: Tìm tham chiếu nội bộ

- Chạy `jdeps --jdk-internals` trên application JAR và các dependency.
- Tìm import `sun.*`, `jdk.internal.*` và các package `com.sun.*` cần kiểm tra.
- Rà soát reflection, string-based class loading và JNI.
- Ghi nhận class, thư viện, module và chức năng bị ảnh hưởng.

### Bước 3: Chọn API thay thế

- Tra Javadoc Java SE 17 và JDK 17.
- Dùng bảng mapping làm điểm bắt đầu, sau đó kiểm tra semantics thực tế.
- Nếu không có API một-một, thiết kế lại abstraction hoặc dùng thư viện được duy trì.
- Không chọn API chỉ vì package name trông giống hoặc class có mặt trong JDK.

### Bước 4: Nâng cấp dependency

Kiểm tra phiên bản framework, ORM, logging, bytecode library, JSON/XML parser, monitoring agent và plugin build. Chọn bản hỗ trợ Java 17 và đã loại bỏ truy cập nội bộ không còn hợp lệ.

Nếu dependency không có bản tương thích, đánh giá thay thế thư viện hoặc biện pháp add-opens/add-exports tạm thời. Đừng chỉnh sửa class nội bộ của JDK để giữ nguyên dependency cũ.

### Bước 5: Sửa code và build

- Thay import/internal reflection bằng API công khai.
- Biên dịch với JDK 17.
- Dùng `javac --release 17` hoặc cấu hình build tool tương ứng để kiểm soát API nền tảng.
- Bỏ các cờ `--illegal-access` không còn tác dụng.
- Giữ các cờ add-opens/add-exports còn cần trong một danh sách ngắn có chủ sở hữu và lý do.

### Bước 6: Kiểm thử runtime

Chạy test trên JDK 17 thực tế, gồm các đường code ít được dùng: khởi tạo framework, reflection, proxy, serialization, TLS, parser, dynamic class generation và plugin loading.

### Bước 7: Loại bỏ workaround

Khi dependency đã được cập nhật hoặc code đã chuyển sang API công khai:

- Gỡ từng cờ `--add-opens` và `--add-exports`.
- Chạy lại test để xác nhận không còn phụ thuộc.
- Chạy lại `jdeps --jdk-internals`.
- Theo dõi log startup và production sau khi triển khai.

## 15. Ví dụ trước và sau khi chuyển đổi

### 15.1. Base64

Trước đây, code cũ có thể dùng class đã bị loại bỏ:

~~~java
// API nội bộ cũ, không còn trong JDK 17.
// sun.misc.BASE64Encoder encoder = new sun.misc.BASE64Encoder();
~~~

Code mới:

~~~java
String encoded = Base64.getEncoder().encodeToString(bytes);
byte[] decoded = Base64.getDecoder().decode(encoded);
~~~

### 15.2. Tìm caller

Trước đây, một số thư viện dùng:

~~~java
// Internal API; không dùng cho code mới.
// sun.reflect.Reflection.getCallerClass(2);
~~~

Code mới dùng StackWalker:

~~~java
private static final StackWalker WALKER =
        StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

static Class<?> caller() {
    return WALKER.getCallerClass();
}
~~~

### 15.3. Atomic field

Nếu nhu cầu chỉ là đếm:

~~~java
private final AtomicLong requests = new AtomicLong();

long nextRequestNumber() {
    return requests.incrementAndGet();
}
~~~

Nếu cần access mode tùy chỉnh trên field, dùng VarHandle và kiểm tra rõ memory semantics. Không giữ một field offset hoặc native address chỉ vì code cũ đã dùng Unsafe.

## 16. Những lỗi thường gặp khi chuyển sang API công khai

| Vấn đề | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Compile báo package không export | Code tham chiếu package nội bộ hoặc package module chưa export | Tìm API công khai thay thế; kiểm tra module và jdeps |
| Runtime ném `InaccessibleObjectException` | Reflection cố truy cập thành viên không public trong package bị đóng | Dùng API công khai; chỉ mở package tạm thời nếu có lý do |
| Thêm `--illegal-access=permit` nhưng lỗi vẫn còn | Tùy chọn đã obsolete và không có tác dụng trên Java 17 | Bỏ cờ này, sửa dependency hoặc dùng workaround package-specific tạm thời |
| `jdeps` không báo lỗi nhưng runtime vẫn lỗi | Truy cập qua reflection, JNI hoặc dynamic loading | Rà soát chuỗi class/member và test runtime |
| Đổi Unsafe sang VarHandle nhưng concurrency test lỗi | Memory ordering hoặc atomic semantics thay đổi | Chọn access mode phù hợp và kiểm thử đa luồng |
| Đổi Base64 nhưng chuỗi output khác | Encoder cũ dùng line wrapping hoặc alphabet khác | Chọn basic, URL hoặc MIME encoder theo giao thức |
| Dùng StackWalker nhưng caller khác mong đợi | Framework/proxy thêm stack frame hoặc helper nằm ở vị trí khác | Lọc stack frame theo class/method có chủ đích |
| Dependency vẫn cần add-opens | Thư viện chưa hỗ trợ Java 17 hoặc dùng deep reflection vào JDK | Nâng cấp hoặc thay dependency; quản lý cờ tạm thời |
| Nhầm mọi package com.sun là nội bộ | Một số package com.sun được tài liệu hóa và export | Kiểm tra Javadoc, module và hợp đồng hỗ trợ |

## 17. Nguyên tắc giữ code tương thích lâu dài

1. Ưu tiên Java SE API khi có thể để tăng khả năng chạy trên nhiều JDK vendor.
2. Nếu dùng API thuộc module JDK, kiểm tra tài liệu, module dependency và chính sách tương thích.
3. Không import package nội bộ hoặc đọc private field của class JDK.
4. Không dựa vào một cờ launcher để nới encapsulation toàn cục.
5. Giữ danh sách add-opens/add-exports nhỏ, có lý do và có kế hoạch loại bỏ.
6. Nâng cấp dependency trước khi nâng runtime production.
7. Chạy jdeps trên cả ứng dụng và thư viện đóng gói.
8. Bổ sung kiểm thử runtime cho các tính năng dùng reflection, plugin và native code.
9. Với VarHandle/atomic code, bảo toàn Java Memory Model semantics thay vì chỉ làm cho compiler hết lỗi.
10. Theo dõi cảnh báo deprecated và tài liệu migration của JDK mục tiêu trong mỗi lần nâng cấp.

## 18. Câu hỏi tự kiểm tra

**1. Vì sao nên chuyển khỏi API nội bộ của JDK?**  
Vì chúng không có cam kết tương thích như API công khai, có thể thay đổi hoặc bị đóng gói mạnh và làm ứng dụng phụ thuộc implementation.

**2. JEP 403 thay đổi điều gì trong Java 17?**  
Strong encapsulation được bật theo mặc định cho phần lớn thành phần nội bộ của JDK.

**3. `--illegal-access` có còn mở quyền reflection trên Java 17 không?**  
Không. Tùy chọn obsolete, chỉ phát cảnh báo và không thay đổi chính sách truy cập.

**4. Dùng công cụ nào để tìm tham chiếu bytecode tới JDK internals?**  
`jdeps --jdk-internals`.

**5. `jdeps` có phát hiện mọi truy cập reflection không?**  
Không. Đây là phân tích tĩnh; reflection dựa trên chuỗi, JNI và dynamic loading có thể không được phát hiện.

**6. Thay `sun.misc.BASE64Encoder` bằng gì?**  
`java.util.Base64`, chọn basic, URL-safe hoặc MIME encoder theo định dạng dữ liệu.

**7. Thay `sun.reflect.Reflection.getCallerClass` bằng gì?**  
`java.lang.StackWalker`.

**8. Khi nào nên dùng VarHandle?**  
Khi cần truy cập field/array với atomic operation hoặc memory ordering cụ thể; nếu chỉ cần counter thông thường, lớp Atomic có thể đơn giản hơn.

**9. `sun.misc.Unsafe` còn truy cập được trong Java 17 có nghĩa là API công khai không?**  
Không. Một số API nội bộ được giữ lại vì tương thích nhưng vẫn không phải hợp đồng công khai được hỗ trợ.

**10. Khác biệt giữa `--add-exports` và `--add-opens` là gì?**  
`--add-exports` cho phép truy cập kiểu public trong package; `--add-opens` cho phép deep reflection vào package tại runtime.

**11. `--add-opens` có phải giải pháp cuối cùng khi nâng Java 17 không?**  
Không. Nó chỉ là workaround hẹp trong giai đoạn chuyển đổi khi dependency chưa thể cập nhật.

**12. Có phải mọi package `com.sun.*` đều là API nội bộ?**  
Không. Cần kiểm tra Javadoc và module; một số package có API được tài liệu hóa.

**13. Khi nào nên dùng ByteBuffer thay cho truy cập direct buffer nội bộ?**  
Khi nhu cầu là đọc/ghi dữ liệu qua buffer theo API NIO công khai; ByteBuffer không thay thế mọi thao tác native address tùy ý.

**14. Vì sao cần test trên JDK 17 runtime sau khi jdeps không còn cảnh báo?**  
Vì jdeps không phát hiện mọi truy cập động và không kiểm chứng hành vi thực tế của reflection, native code hoặc dependency.

## Tài liệu tham khảo chính thức

- [JEP 403 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/403): thay đổi strong encapsulation từ Java 17 và các ngoại lệ được giữ lại.
- [Java SE 17 Migration Guide — Preparing for Migration](https://docs.oracle.com/en/java/javase/17/migrate/preparing-migration.html): nhận diện phụ thuộc internal API, dùng jdeps và lựa chọn replacement.
- [Java SE 17 Migration Guide — Removed APIs](https://docs.oracle.com/en/java/javase/17/migrate/removed-apis.html): các API nội bộ đã bị loại bỏ và hướng thay thế như Base64, VarHandle, StackWalker.
- [Java SE 17 — The jdeps Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): tùy chọn --jdk-internals, classpath, module path và multi-release JAR.
- [Java SE 17 API — Base64](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html): encoder/decoder basic, URL-safe và MIME.
- [Java SE 17 API — StackWalker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.html): API stack walking và lấy caller class.
- [Java SE 17 API — VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): access modes, atomic operations và memory ordering.
- [Java SE 17 API — Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): quản lý hành động cleanup khi object được thu gom.
- [Java SE 17 API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): định nghĩa class và quyền lookup.
- [JEP 193 — Variable Handles](https://openjdk.org/jeps/193) và [JEP 259 — Stack-Walking API](https://openjdk.org/jeps/259): thiết kế các API công khai thay thế một số use case nội bộ.
