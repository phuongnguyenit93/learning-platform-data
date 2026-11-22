# Thay API nội bộ bằng API công khai còn được hỗ trợ trong Java 17

## 1. Vì sao cần thay API nội bộ?

Một số thư viện hoặc ứng dụng Java cũ gọi trực tiếp các lớp nằm trong package nội bộ của JDK, chẳng hạn các tên bắt đầu bằng `sun.`, `com.sun.` hoặc những package `jdk.internal.`. Những lớp này có thể từng truy cập được trong một phiên bản JDK, nhưng **không phải tất cả đều là API công khai được Java SE cam kết hỗ trợ**. Chúng có thể thay đổi, bị đóng gói mạnh hơn hoặc bị loại bỏ khi nâng cấp JDK.

Java 9 đưa hệ thống module vào nền tảng (Project Jigsaw). Java 17 tiếp tục đóng gói mạnh các thành phần nội bộ của JDK theo JEP 403. Vì thế, một ứng dụng từng chạy nhờ truy cập sâu vào JDK có thể gặp lỗi biên dịch hoặc lỗi runtime như:

- `package ... is not visible`.
- `module ... does not export ...`.
- `InaccessibleObjectException` khi reflection cố truy cập thành viên không được mở.
- `NoSuchMethodError` hoặc `ClassNotFoundException` nếu API nội bộ đã thay đổi hoặc bị loại bỏ.

Hướng xử lý bền vững là **xác định chức năng mà mã đang cần, rồi chuyển sang API công khai có hợp đồng được tài liệu hóa**. Không nên chỉ tìm một package nội bộ khác để thay thế package cũ.

Sau bài học, người học cần:

1. Phân biệt API công khai của Java SE với API nội bộ của JDK.
2. Hiểu tác động của module system và strong encapsulation trong Java 17.
3. Kiểm kê dependency nội bộ bằng công cụ JDK.
4. Chọn API thay thế theo chức năng, ví dụ Base64, Cleaner, VarHandle, LockSupport hoặc ImageIO.
5. Biết trường hợp nào không có drop-in replacement và cần thay đổi thiết kế.
6. Phân biệt `exports`, `opens`, `--add-exports` và `--add-opens`.
7. Biên dịch, chạy và kiểm thử ứng dụng trên Java 17 mà không phụ thuộc vào quyền truy cập nội bộ.

## 2. API công khai và API nội bộ khác nhau thế nào?

### 2.1. API công khai được tài liệu hóa

API công khai là phần giao diện được nhà cung cấp công bố và tài liệu hóa để ứng dụng sử dụng. Với JDK, có thể tra cứu Java SE API Specification và Javadoc của đúng phiên bản.

Ví dụ các API công khai:

- `java.util.Base64` để mã hóa và giải mã Base64.
- `java.lang.ref.Cleaner` để đăng ký hành động dọn dẹp tài nguyên như một cơ chế dự phòng.
- `java.lang.invoke.VarHandle` để truy cập biến và mảng với các memory access mode.
- `java.util.concurrent.locks.LockSupport` để park/unpark thread.
- `javax.imageio.ImageIO` để đọc và ghi ảnh.
- `java.net.http.HttpClient` để gửi HTTP request.

Các API này có hợp đồng rõ ràng trong tài liệu Java SE hoặc tài liệu module tương ứng. Ứng dụng có thể dựa vào hợp đồng đó khi nâng cấp JDK trong phạm vi tương thích được công bố.

### 2.2. API nội bộ không phải cam kết tương thích

Tên package như `sun.misc`, `sun.reflect` hoặc `jdk.internal.*` thường là dấu hiệu cần kiểm tra kỹ. Tuy nhiên, **không nên phân loại chỉ dựa trên tiền tố tên package**: một số package `com.sun.*` được tài liệu hóa và là API công khai của module JDK, chẳng hạn HTTP server API trong `jdk.httpserver`.

Hãy xác minh từng lớp và package bằng Javadoc chính thức, module descriptor và công cụ `jdeps`. Không phải cứ tên bắt đầu bằng `com.sun` là tự động nội bộ, cũng không phải cứ một lớp đang truy cập được là API được hỗ trợ lâu dài.

### 2.3. Truy cập được không có nghĩa là được hỗ trợ

Trong Java 17, một số API nội bộ quan trọng vẫn được cung cấp qua module `jdk.unsupported` để hỗ trợ ứng dụng cũ. Ví dụ `sun.misc.Unsafe` vẫn có thể hiện diện trên JDK 17. Điều này **không biến nó thành API Java SE ổn định** và không bảo đảm các chi tiết nội bộ sẽ tiếp tục giữ nguyên.

Nguyên tắc chọn API:

1. Ưu tiên API có Javadoc công khai và thuộc Java SE hoặc module JDK được tài liệu hóa.
2. Kiểm tra API có sẵn trong phiên bản Java mục tiêu.
3. Xác định rõ hợp đồng về exception, thread safety, mutability và vòng đời tài nguyên.
4. Không coi việc thêm cờ JVM để truy cập package nội bộ là hoàn tất migration.

## 3. Strong encapsulation trong Java 17

### 3.1. Module system kiểm soát package được truy cập

Một module có thể khai báo package nào được xuất cho module khác:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Module khác có thể sử dụng các kiểu public trong package được export, nếu module đọc được module chứa chúng.

Các khái niệm quan trọng:

| Khái niệm | Ý nghĩa |
|---|---|
| Readability | Module có quyền đọc module khác hay không, thường khai báo bằng `requires` |
| `exports` | Công bố các kiểu public của package cho module khác sử dụng bình thường |
| `opens` | Cho phép reflection sâu vào package ở runtime |
| Encapsulation | Giới hạn phần triển khai nội bộ không được công bố |
| Unnamed module | Nơi chứa classpath truyền thống; các JAR trên classpath thường thuộc unnamed module |

Ví dụ module dùng HTTP client:

~~~java
module com.example.client {
    requires java.net.http;
}
~~~

`java.base` được yêu cầu ngầm định trong mọi module Java, nên không cần viết `requires java.base`.

### 3.2. JEP 403 và Java 17

JEP 403 hoàn tất việc đóng gói mạnh các thành phần nội bộ của JDK. Trong Java 17:

- Các package nội bộ không được export/open mặc định sẽ không thể được truy cập như trước.
- Reflection sâu vào thành viên private của JDK có thể bị chặn.
- Cờ `--illegal-access` không còn là cách khôi phục cơ chế truy cập rộng như các bản JDK chuyển tiếp trước đó.
- Một số API nội bộ quan trọng vẫn được expose qua `jdk.unsupported` vì lý do tương thích, nhưng vẫn là API nội bộ.

Vì vậy, khi nâng cấp lên Java 17, cần tìm và loại bỏ dependency vào JDK internals thay vì dựa vào chế độ truy cập nới lỏng.

### 3.3. Lỗi compile-time và runtime

Hai dạng lỗi có nguyên nhân khác nhau:

**Lỗi biên dịch:** mã import một package không được module chứa nó export cho module hiện tại. Compiler có thể báo package không nhìn thấy.

**Lỗi runtime:** mã dùng reflection để mở một thành viên không được module đích mở. Các thao tác như `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Không nên sửa cả hai loại lỗi bằng cùng một cờ JVM. Cần xác định đang thiếu readability, export package hay open package cho deep reflection.

## 4. Kiểm kê dependency nội bộ trước khi sửa

### 4.1. Dùng jdeps

`jdeps` là công cụ phân tích dependency của class, JAR và module. Tùy chọn `--jdk-internals` giúp phát hiện tham chiếu tĩnh đến API nội bộ của JDK.

Ví dụ:

~~~bash
jdeps --jdk-internals application.jar
~~~

Nếu muốn phân tích sâu các dependency:

~~~bash
jdeps --jdk-internals --recursive application.jar
~~~

Với JAR multi-release, có thể chỉ định phiên bản cần phân tích:

~~~bash
jdeps --jdk-internals --multi-release 17 application.jar
~~~

Đọc kết quả để xác định:

- Class nào đang phụ thuộc API nội bộ.
- Package/module nội bộ nào bị sử dụng.
- Gợi ý thay thế mà công cụ biết (nếu có).
- Dependency đến từ code của ứng dụng hay thư viện bên thứ ba.

### 4.2. jdeps không phát hiện mọi truy cập động

`jdeps` phân tích bytecode và dependency có thể nhận diện tĩnh. Nó có thể không phát hiện đầy đủ:

- Tên class hoặc package được ghép thành chuỗi rồi truyền cho `Class.forName`.
- Reflection được xây dựng từ metadata runtime.
- Mã được sinh trong lúc chạy.
- Truy cập phát sinh từ plugin hoặc dependency chỉ được nạp ở một cấu hình triển khai khác.

Do đó, kết quả jdeps là điểm khởi đầu. Hãy kết hợp tìm kiếm mã nguồn, kiểm tra dependency graph, chạy integration test và kiểm thử các luồng plugin thực tế.

### 4.3. Phân biệt jdeps với jdeprscan

`jdeprscan` tìm các API đã bị đánh dấu deprecated trong JDK. Deprecated API và internal API là hai nhóm khác nhau:

- Một API public có thể bị deprecated nhưng vẫn là API công khai.
- Một API internal có thể chưa deprecated nhưng vẫn không được cam kết hỗ trợ.

Ví dụ:

~~~bash
jdeprscan --release 17 application.jar
~~~

Có thể chạy cả hai công cụ để có bức tranh đầy đủ hơn, nhưng không dùng kết quả của công cụ này thay cho công cụ kia.

## 5. Bản đồ thay thế theo chức năng

Không có một API công khai duy nhất thay thế mọi internal API. Hãy lập bảng theo **chức năng thực sự đang dùng**:

| Cách cũ hoặc nhu cầu | Hướng thay thế công khai | Lưu ý |
|---|---|---|
| `sun.misc.BASE64Encoder` / `BASE64Decoder` | `java.util.Base64` | API chuẩn từ Java 8 |
| `sun.misc.Cleaner` | `java.lang.ref.Cleaner` | Cleaner là dự phòng; vẫn ưu tiên close rõ ràng |
| CAS/atomic field access bằng `sun.misc.Unsafe` | `VarHandle` hoặc `AtomicInteger`/`AtomicLong`/`AtomicReference` | Chọn theo loại dữ liệu và memory semantics |
| Atomic access tới phần tử mảng | `MethodHandles.arrayElementVarHandle` hoặc lớp atomic phù hợp | Không tự tính offset/index scale |
| Park/unpark thread bằng Unsafe | `LockSupport.park`/`unpark` | Hiểu permit và interruption |
| Định nghĩa class trong package của caller | `MethodHandles.Lookup.defineClass` | Bị giới hạn bởi quyền của Lookup và package |
| Đọc/ghi ảnh bằng codec nội bộ cũ | `javax.imageio.ImageIO` | Kiểm tra format và provider có sẵn |
| Truy cập private member của JDK | Dùng API public tương ứng hoặc thiết kế lại | Không có cách mở private API thành hợp đồng ổn định |
| Cấp phát native memory tùy ý bằng Unsafe | Không có drop-in replacement ổn định trong Java 17; cân nhắc DirectByteBuffer/JNI theo yêu cầu | FFM ở Java 17 còn incubator |
| Tạo instance bỏ qua constructor | Factory/constructor; serialization API phù hợp nếu đúng use case | Không có thay thế chung cho allocateInstance |

Bảng này là định hướng; trước khi thay, cần đọc Javadoc của API đích và kiểm tra khác biệt ngữ nghĩa.

## 6. Thay Base64 nội bộ bằng java.util.Base64

Các lớp Base64 cũ trong `sun.misc` là ví dụ điển hình nên thay bằng API chuẩn `java.util.Base64`.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] input = "Xin chào Java".getBytes(StandardCharsets.UTF_8);

String encoded = Base64.getEncoder().encodeToString(input);
byte[] decoded = Base64.getDecoder().decode(encoded);

String restored = new String(decoded, StandardCharsets.UTF_8);
System.out.println(restored); // Xin chào Java
~~~

Các lựa chọn phổ biến:

- `Base64.getEncoder()` / `getDecoder()`: dạng Base64 thông thường.
- `Base64.getUrlEncoder()` / `getUrlDecoder()`: alphabet an toàn hơn cho URL và tên tệp.
- `Base64.getMimeEncoder()` / `getMimeDecoder()`: dạng MIME có quy tắc line separator.

Không tự thay decoder cũ bằng decoder mới mà bỏ qua biến thể dữ liệu. Hãy xác định dữ liệu cũ là Base64 basic, URL-safe hay MIME; kiểm tra padding và line wrapping theo định dạng trao đổi.

## 7. Thay sun.misc.Cleaner bằng java.lang.ref.Cleaner

`java.lang.ref.Cleaner` là API công khai để đăng ký hành động dọn dẹp khi object được xác định là không còn reachable. Nó có từ Java 9 và có sẵn trong Java 17.

Tuy nhiên, Cleaner **không thay thế trách nhiệm đóng tài nguyên một cách xác định**. Nếu tài nguyên có thể đóng rõ ràng như file, socket hoặc channel, hãy triển khai `AutoCloseable` và khuyến khích caller dùng try-with-resources. Cleaner chỉ nên là cơ chế dự phòng khi caller quên đóng.

### 7.1. Ví dụ cấu trúc Cleaner an toàn

~~~java
import java.io.IOException;
import java.lang.ref.Cleaner;
import java.nio.channels.FileChannel;

public final class ManagedResource implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    // State không được giữ tham chiếu mạnh tới ManagedResource.
    private static final class State implements Runnable {
        private final FileChannel channel;

        State(FileChannel channel) {
            this.channel = channel;
        }

        @Override
        public void run() {
            try {
                channel.close();
            } catch (IOException ex) {
                // Ghi log theo chính sách của ứng dụng.
            }
        }
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    public ManagedResource(FileChannel channel) {
        this.state = new State(channel);
        this.cleanable = CLEANER.register(this, state);
    }

    @Override
    public void close() {
        cleanable.clean();
    }
}
~~~

Điểm quan trọng:

- Hành động cleanup không được giữ tham chiếu mạnh đến object được đăng ký, nếu không object có thể không bao giờ trở thành unreachable.
- `cleanable.clean()` có thể được gọi tường minh và hành động cleanup chỉ được thực hiện một lần.
- Cleaner chạy bất đồng bộ khi object không còn reachable; không bảo đảm thời điểm chạy chính xác.
- Không dùng Cleaner để thay cho `close()` ở luồng nghiệp vụ bình thường.

## 8. Thay Unsafe cho thao tác biến bằng VarHandle

`VarHandle` là API công khai trong `java.lang.invoke` từ Java 9. Nó cho phép truy cập biến instance, biến static và phần tử mảng với các access mode khác nhau, bao gồm volatile, acquire/release và atomic read-modify-write.

### 8.1. Atomic update một field

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class Counter {
    private volatile int value;
    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                    Counter.class, "value", int.class);
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    public int increment() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }

    public boolean setIfZero() {
        return VALUE.compareAndSet(this, 0, 1);
    }
}
~~~

`findVarHandle` tìm field theo tên và kiểu. `getAndAdd` và `compareAndSet` là các access mode atomic; field phải được truy cập với đúng receiver và kiểu giá trị.

Không phải thao tác nào của Unsafe cũng chuyển thẳng thành một lời gọi VarHandle giống hệt. Hãy chọn memory access mode dựa trên yêu cầu đồng bộ của thuật toán.

### 8.2. Atomic access tới phần tử mảng

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class AtomicArrayExample {
    private static final VarHandle ELEMENT =
            MethodHandles.arrayElementVarHandle(int[].class);

    public static void main(String[] args) {
        int[] values = {10, 20, 30};

        boolean changed = ELEMENT.compareAndSet(
                values, 1, 20, 25);

        System.out.println(changed);    // true
        System.out.println(values[1]);  // 25
    }
}
~~~

Thay vì tự tính base offset và index scale bằng Unsafe, dùng VarHandle cho kiểu mảng cần truy cập. API đảm nhiệm cách truy cập theo hợp đồng Java.

### 8.3. Chọn lớp Atomic khi nhu cầu đơn giản

Nếu chỉ cần một bộ đếm hoặc tham chiếu atomic, các lớp `AtomicInteger`, `AtomicLong` và `AtomicReference` thường dễ đọc hơn VarHandle:

~~~java
AtomicInteger counter = new AtomicInteger();
int next = counter.incrementAndGet();
~~~

VarHandle hữu ích khi cần truy cập trực tiếp field/mảng của một cấu trúc dữ liệu mà không muốn bọc từng giá trị trong một atomic object.

### 8.4. Memory fence

Một số thao tác fence của Unsafe có thể được thay bằng API fence công khai của `VarHandle`:

~~~java
VarHandle.releaseFence();
VarHandle.acquireFence();
VarHandle.fullFence();
~~~

Fence có ý nghĩa ở mức memory ordering. Không thêm fence tùy tiện để “làm cho thread-safe”; hãy hiểu happens-before, volatile và access mode trước khi thay thế. Nếu chỉ cần đồng bộ hóa thông thường, `synchronized`, lock hoặc atomic class có thể đơn giản và an toàn hơn.

## 9. Thay Unsafe.park/unpark bằng LockSupport

`java.util.concurrent.locks.LockSupport` là API công khai để tạm dừng (park) và đánh thức (unpark) thread:

~~~java
import java.util.concurrent.locks.LockSupport;

Thread worker = new Thread(() -> {
    System.out.println("Waiting");
    LockSupport.park();
    System.out.println("Resumed");
});

worker.start();

LockSupport.unpark(worker);
~~~

Một số điểm cần nhớ:

- `unpark(thread)` cấp một permit cho thread; permit không tích lũy vô hạn, tối đa một permit đang chờ.
- `park()` có thể trở về vì được unpark, bị interrupt hoặc do spurious return.
- Code dùng `park` thường phải kiểm tra điều kiện trong vòng lặp.
- Nếu thread bị interrupt, trạng thái interrupt có thể vẫn được giữ; ứng dụng phải xử lý theo hợp đồng.

Ví dụ dạng chờ điều kiện:

~~~java
while (!condition) {
    LockSupport.park(this);
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
}
~~~

Không dùng park/unpark như một cách thay thế tùy tiện cho `wait/notify` hoặc `Condition`. Với phần lớn ứng dụng, `BlockingQueue`, `CountDownLatch`, `Semaphore`, `Lock` và `Condition` dễ sử dụng hơn vì cung cấp abstraction đồng bộ hóa cao hơn.

## 10. Định nghĩa class bằng API công khai

Một số code cũ dùng `Unsafe.defineClass` để định nghĩa class động. Hướng thay thế phụ thuộc class cần được định nghĩa ở đâu và ai có quyền định nghĩa.

### 10.1. MethodHandles.Lookup.defineClass

`MethodHandles.Lookup.defineClass(byte[])` có từ Java 9. Nó định nghĩa class trong cùng package, class loader và protection domain với lookup class, với điều kiện Lookup có quyền PACKAGE phù hợp:

~~~java
import java.lang.invoke.MethodHandles;

byte[] classBytes = loadClassBytes();
Class<?> generated = MethodHandles.lookup().defineClass(classBytes);
~~~

Bytecode phải khai báo đúng package tương ứng. API này không phải cách định nghĩa class tùy ý vào bất kỳ package hoặc class loader nào.

### 10.2. ClassLoader.defineClass cho class loader riêng

Nếu ứng dụng đang xây dựng một class loader riêng, có thể mở rộng `ClassLoader` và gọi phương thức protected `defineClass` bên trong subclass:

~~~java
public final class PluginClassLoader extends ClassLoader {
    public PluginClassLoader(ClassLoader parent) {
        super(parent);
    }

    public Class<?> definePlugin(String name, byte[] bytes) {
        return defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

Việc lựa chọn package, loader constraint, protection domain, signer và quyền truy cập cần được thiết kế đúng. Không nên định nghĩa class tùy tiện vào namespace của module/JDK khác.

## 11. Thay API xử lý ảnh nội bộ bằng ImageIO

Các codec ảnh nội bộ cũ như `com.sun.image.codec.jpeg` không phải lựa chọn phù hợp cho mã mới. Java cung cấp `javax.imageio.ImageIO`:

~~~java
import java.awt.image.BufferedImage;
import java.io.InputStream;
import java.io.OutputStream;
import javax.imageio.ImageIO;

BufferedImage image;
try (InputStream input = openInput()) {
    image = ImageIO.read(input);
}

try (OutputStream output = openOutput()) {
    boolean written = ImageIO.write(image, "png", output);
    if (!written) {
        throw new IllegalStateException("No writer for PNG format");
    }
}
~~~

`ImageIO.read` có thể trả về `null` nếu không tìm được reader phù hợp; `ImageIO.write` trả về `false` nếu không có writer cho định dạng được yêu cầu. Cần kiểm tra kết quả và không giả định mọi JDK đều cài sẵn mọi codec bên thứ ba.

Nếu cần codec hoặc định dạng đặc biệt, dùng ImageIO provider hoặc thư viện được hỗ trợ có tài liệu rõ ràng.

## 12. Những trường hợp không có drop-in replacement

Không phải mọi internal API đều có phương thức công khai thay thế trực tiếp. Đôi khi giải pháp đúng là đổi thiết kế.

### 12.1. Tạo object bỏ qua constructor

`Unsafe.allocateInstance` có thể tạo object mà không chạy constructor. Java SE không cung cấp một API tổng quát tương đương để bỏ qua mọi invariant của lớp.

Hướng xử lý:

- Dùng constructor hoặc static factory để khởi tạo object hợp lệ.
- Với Java serialization, dùng cơ chế serialization chuẩn và các hook được tài liệu hóa.
- Nếu thư viện cần instantiate kiểu bên ngoài, thiết kế SPI/factory hoặc constructor công khai.
- Không dùng reflection sâu để né constructor và không mở private API của JDK.

### 12.2. Native memory tùy ý

Các thao tác như `Unsafe.allocateMemory` và `freeMemory` không có drop-in replacement ổn định trong Java 17 Java SE.

Các lựa chọn tùy yêu cầu:

- `ByteBuffer.allocateDirect` cho vùng nhớ direct có kích thước hữu hạn và phù hợp với API NIO. Tuy nhiên, Java 17 không cung cấp một phương thức public chung để giải phóng direct buffer ngay tại thời điểm tùy ý; cần quản lý vòng đời tham chiếu và không coi đây là thay thế hoàn toàn cho allocate/free memory.
- JNI hoặc thư viện native được kiểm soát nếu thật sự cần quản lý native memory ở mức thấp.
- Foreign Function & Memory API trong Java 17 vẫn là incubator API (JEP 412), chưa phải API Java SE ổn định. Không dùng nó như một hợp đồng production ổn định nếu yêu cầu là chỉ dùng API đã được chuẩn hóa trong Java 17.

Nếu cần FFM, hãy đánh giá lại phiên bản JDK mục tiêu và trạng thái chuẩn hóa của API ở phiên bản đó.

### 12.3. Truy cập private field của JDK

Không có API công khai tổng quát cho phép ứng dụng tùy ý đọc hoặc sửa private field của lớp trong JDK. Nếu ứng dụng cần thông tin đó:

- Tìm public accessor hoặc API quản lý tương ứng.
- Dùng JMX, management API hoặc diagnostic API được tài liệu hóa nếu chức năng phù hợp.
- Nếu đang phụ thuộc vào cấu trúc nội bộ để tối ưu, thay bằng abstraction công khai và đo lại hiệu năng.
- Nếu không có API tương đương, bỏ dependency hoặc thiết kế lại chức năng.

Không coi `--add-opens` là một API thay thế.

### 12.4. Xử lý signal hệ điều hành

Một số ứng dụng dùng lớp nội bộ để đăng ký signal handler. Java SE không cung cấp API portable tổng quát cho mọi POSIX signal. Nếu mục tiêu là dọn dẹp khi tiến trình kết thúc bình thường, dùng `Runtime.addShutdownHook`; nếu cần quản lý signal cụ thể, phải dựa vào cơ chế được hỗ trợ của môi trường/native layer và chấp nhận ràng buộc nền tảng.

## 13. Reflection và module: exports khác opens

### 13.1. `exports` cho API public

Module xuất package để module khác gọi public API:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

`exports` không tự cho phép truy cập private member bằng reflection.

### 13.2. `opens` cho deep reflection

Nếu framework cần reflection sâu vào package của **ứng dụng**, có thể mở package cụ thể:

~~~java
module com.example.application {
    requires some.framework;
    opens com.example.model to some.framework;
}
~~~

Đây là lựa chọn có phạm vi hẹp hơn mở toàn bộ module. Chỉ mở package thật sự cần thiết và cho đúng module đích.

### 13.3. Dùng public reflection trước

Nếu chỉ cần gọi public constructor hoặc method, hãy dùng public reflection:

~~~java
Constructor<?> constructor =
        type.getConstructor(String.class);
Object instance = constructor.newInstance("value");
~~~

Không gọi `setAccessible(true)` như thói quen nếu không cần truy cập private member. Với API mới, có thể kiểm tra `trySetAccessible()`; nó trả về boolean để cho biết quyền truy cập có được mở hay không. Nhưng việc truy cập được trong một cấu hình không có nghĩa thiết kế đó nên phụ thuộc vào private implementation.

### 13.4. MethodHandles.privateLookupIn

Khi cần quyền lookup private trong một class thuộc module khác, `MethodHandles.privateLookupIn` có thể được dùng nếu các điều kiện module và access phù hợp:

~~~java
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(targetClass, MethodHandles.lookup());
~~~

Package của class đích phải được module của nó mở cho module chứa lookup phù hợp. Đây là cơ chế có kiểm soát, không phải cách vượt qua strong encapsulation của JDK. Không yêu cầu framework mở toàn bộ package nội bộ của Java để dùng private lookup.

## 14. --add-exports và --add-opens chỉ là cầu nối chuyển đổi

Hai cờ này thường xuất hiện khi ứng dụng nâng cấp Java 9+ hoặc Java 17.

| Cờ | Tác dụng | Không làm được |
|---|---|---|
| `--add-exports module/package=target` | Cho module đích truy cập các kiểu public trong package vốn không được export | Không mở private member cho deep reflection |
| `--add-opens module/package=target` | Mở package ở runtime cho deep reflection | Không làm API nội bộ trở thành API được hỗ trợ; không thay hợp đồng JDK |

Ví dụ dạng tổng quát:

~~~bash
java --add-exports source.module/internal.package=ALL-UNNAMED -jar app.jar
java --add-opens source.module/internal.package=ALL-UNNAMED -jar app.jar
~~~

`ALL-UNNAMED` chỉ unnamed module (thường là ứng dụng chạy từ classpath). Với ứng dụng module hóa, có thể chỉ định tên module đích cụ thể.

Các cờ này có thể hữu ích để giữ hệ thống chạy trong lúc nâng cấp thư viện, điều tra hoặc chia nhỏ migration. Tuy nhiên:

1. Ghi lại chính xác package, module và dependency cần cờ.
2. Thu hẹp target, tránh mở cho `ALL-UNNAMED` nếu không cần.
3. Tạo kế hoạch bỏ cờ sau khi thư viện đã chuyển sang API công khai.
4. Kiểm thử trên JDK mục tiêu không có cờ để xác nhận migration hoàn tất.

Không dùng `--add-opens` cho package JDK như một giải pháp lâu dài để truy cập private implementation. Cờ chỉ thay đổi quyền truy cập trong một lần chạy; nó không biến thành viên nội bộ thành API ổn định.

## 15. Quy trình migration một dependency nội bộ

Một quy trình có thể áp dụng trong dự án:

### Bước 1: Tìm tất cả điểm phụ thuộc

Chạy `jdeps --jdk-internals` trên JAR và các module liên quan. Tìm trong mã nguồn các import `sun.*`, `com.sun.*`, `jdk.internal.*` và tên class được dùng qua reflection.

### Bước 2: Xác định chức năng thực sự

Không dừng ở tên class. Hãy hỏi đoạn mã đang cần làm gì:

- Encode/decode Base64?
- CAS một field?
- Dọn dẹp native resource?
- Định nghĩa class động?
- Đọc private field để lấy thông tin?
- Chuyển đổi dữ liệu ảnh?

Một class nội bộ có thể đang được dùng cho nhiều mục đích khác nhau; mỗi mục đích có thể cần API thay thế riêng.

### Bước 3: Chọn API công khai và xác định khác biệt

Đọc Javadoc Java 17 của API đích. So sánh:

- Semantics và kiểu dữ liệu.
- Exception và cách báo lỗi.
- Thread safety, memory ordering và lifecycle.
- Giới hạn hiệu năng hoặc khả năng tương thích.
- Yêu cầu module và quyền truy cập.

### Bước 4: Sửa code và dependency

Thay import, kiểu dữ liệu, lời gọi và cách quản lý tài nguyên. Nếu dependency bên thứ ba còn dùng internals, nâng cấp lên phiên bản đã hỗ trợ Java 17 hoặc thay thư viện.

### Bước 5: Kiểm thử trên JDK 17

Biên dịch với API mục tiêu:

~~~bash
javac --release 17 -d out @sources.txt
~~~

Chạy test và integration test bằng JDK 17. Kiểm thử cả lỗi, dữ liệu biên, đường đi reflection, plugin, serialization và concurrency nếu có liên quan.

### Bước 6: Xác nhận không còn dependency nội bộ

Chạy lại:

~~~bash
jdeps --jdk-internals --recursive application.jar
~~~

Kiểm tra mã nguồn và cấu hình triển khai để loại bỏ cờ truy cập nội bộ không còn cần thiết. Kết quả jdeps sạch là tín hiệu tốt cho dependency tĩnh, nhưng vẫn cần test runtime cho truy cập động.

## 16. Ví dụ trước và sau migration

### 16.1. Mã hóa Base64

**Cách phụ thuộc API nội bộ cũ** (không dùng cho mã mới):

~~~java
// Ví dụ minh họa tên API cũ, không phải API Java SE.
// sun.misc.BASE64Encoder encoder = new sun.misc.BASE64Encoder();
// String encoded = encoder.encode(data);
~~~

**Cách dùng API công khai:**

~~~java
String encoded = Base64.getEncoder().encodeToString(data);
byte[] decoded = Base64.getDecoder().decode(encoded);
~~~

### 16.2. Atomic field

Thay việc tính offset và gọi CAS qua Unsafe bằng VarHandle:

~~~java
private volatile long sequence;
private static final VarHandle SEQUENCE;

static {
    try {
        SEQUENCE = MethodHandles.lookup().findVarHandle(
                Sequence.class, "sequence", long.class);
    } catch (ReflectiveOperationException ex) {
        throw new ExceptionInInitializerError(ex);
    }
}

long next() {
    return (long) SEQUENCE.getAndAdd(this, 1L) + 1L;
}
~~~

Không còn phải biết object layout hoặc field offset của JVM.

### 16.3. Dọn dẹp tài nguyên

Thay Cleaner nội bộ bằng `java.lang.ref.Cleaner`, đồng thời cung cấp `close()` rõ ràng để caller giải phóng tài nguyên đúng lúc. Cleaner chỉ đóng vai trò dự phòng.

## 17. Những lỗi thường gặp

### 17.1. Chỉ thay package nhưng không thay hợp đồng

Chuyển một lớp nội bộ sang lớp public có tên gần giống chưa chắc giữ đúng hành vi. So sánh semantics, exception, threading và lifecycle trước khi thay.

### 17.2. Coi Unsafe là API công khai vì JDK 17 vẫn có nó

`sun.misc.Unsafe` được giữ lại vì tương thích, nhưng không phải API Java SE được cam kết. Dùng VarHandle, atomic classes hoặc abstraction phù hợp.

### 17.3. Thêm --add-opens rồi coi migration đã xong

Cờ chỉ mở quyền truy cập trong runtime. Dependency vào private implementation vẫn còn và có thể vỡ ở JDK tiếp theo.

### 17.4. Mở cả module cho framework

`open module` hoặc mở package rộng làm giảm encapsulation. Ưu tiên `opens package to module` có phạm vi hẹp và chỉ mở package dữ liệu cần reflection.

### 17.5. Dựa hoàn toàn vào jdeps

Static analysis có thể bỏ sót reflection động và plugin. Kết hợp tìm kiếm source, test và quan sát runtime.

### 17.6. Thay native memory bằng DirectByteBuffer mà không xét vòng đời

Direct buffer không phải drop-in replacement cho allocate/free memory tùy ý. Java 17 không có API public chung để free ngay; phải thiết kế vòng đời phù hợp hoặc chọn native layer có quản lý rõ.

### 17.7. Dùng FFM incubator như API ổn định của Java 17

Foreign Function & Memory API ở Java 17 là incubator. Nếu yêu cầu chỉ dùng API Java SE ổn định của Java 17, không coi nó là replacement đã chuẩn hóa.

### 17.8. Chỉ kiểm thử compile mà bỏ qua runtime

Một số lỗi chỉ xuất hiện khi reflection, serialization, class loading hoặc đường đi plugin thực sự chạy. Phải có kiểm thử runtime trên JDK mục tiêu.

## 18. Bài tập thực hành

### Bài 1 — Phân loại API

Với mỗi tên sau, hãy kiểm tra Javadoc và xác định nó là API công khai hay nội bộ: `java.util.Base64`, `sun.misc.Unsafe`, `java.lang.ref.Cleaner`, `jdk.internal.misc.Unsafe`, `javax.imageio.ImageIO`. Giải thích vì sao việc một lớp có thể truy cập trên máy không chứng minh nó được hỗ trợ lâu dài.

### Bài 2 — Dùng jdeps

Chạy `jdeps --jdk-internals` trên một JAR của dự án. Ghi lại class tham chiếu package nội bộ và tìm dependency nào đưa package đó vào. Nếu kết quả trống, nêu giới hạn của phân tích tĩnh với reflection động.

### Bài 3 — Thay Base64

Viết đoạn encode/decode bằng `java.util.Base64` cho UTF-8. Thử basic và URL-safe encoder, giải thích vì sao hai chuỗi có thể khác nhau.

### Bài 4 — Thay CAS bằng VarHandle

Viết một class có field `volatile int count`. Dùng VarHandle để tăng atomic và so sánh với `AtomicInteger`. Nêu trường hợp nào API Atomic dễ đọc hơn.

### Bài 5 — Module exports và opens

Tạo module thư viện export `com.example.api` và mở `com.example.model` cho một module framework cụ thể. Giải thích vì sao `exports` không cho phép truy cập private member bằng reflection.

### Bài 6 — Không có replacement trực tiếp

Một thư viện dùng `Unsafe.allocateMemory` và `Unsafe.freeMemory`. Hãy đề xuất các lựa chọn dựa trên yêu cầu: buffer có kích thước hữu hạn, truy cập native memory qua JNI hoặc thay đổi kiến trúc. Giải thích vì sao DirectByteBuffer và FFM incubator Java 17 không phải replacement tương đương trong mọi trường hợp.

### Bài 7 — Bỏ cờ truy cập nội bộ

Một ứng dụng chạy được nhờ `--add-opens`. Xác định package nào cần mở, vì sao reflection đang truy cập private member, và thiết kế phương án thay bằng public API hoặc `opens` có phạm vi hẹp trong module của ứng dụng. Cuối cùng chạy lại test không có cờ.

## 19. Tiêu chí hoàn thành

Người học nắm vững bài khi có thể:

1. Giải thích khác biệt giữa public supported API và internal JDK API.
2. Nêu tác động của module system và strong encapsulation trong Java 17.
3. Dùng `jdeps --jdk-internals` để tìm dependency nội bộ và giải thích giới hạn với reflection động.
4. Chọn `java.util.Base64`, `java.lang.ref.Cleaner`, `VarHandle`, `LockSupport` hoặc `ImageIO` đúng theo chức năng.
5. Biết khi nào không có drop-in replacement và cần thiết kế lại.
6. Phân biệt `exports` với `opens`, `--add-exports` với `--add-opens`.
7. Không coi `sun.misc.Unsafe` hoặc cờ truy cập nội bộ là hợp đồng ổn định.
8. Kiểm thử trên JDK 17 không có cờ mở nội bộ, bao gồm cả các đường đi reflection và runtime.
9. Xác nhận dependency tĩnh bằng jdeps và kiểm tra dependency động qua test/quan sát runtime.

## 20. Tài liệu chính thức

- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): thay đổi strong encapsulation trong Java 17.
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261): khái niệm module, exports, opens và cờ truy cập.
- [Java SE 17 API — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): field/array access modes và memory fences.
- [Java SE 17 API — `Cleaner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): cleanup action và Cleanable.
- [Java SE 17 API — `Base64`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html): encoder/decoder Basic, URL và MIME.
- [Java SE 17 API — `LockSupport`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): park/unpark.
- [Java SE 17 API — `ImageIO`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/imageio/ImageIO.html): đọc/ghi ảnh.
- [Java SE 17 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup và defineClass.
- [Java SE 17 API — `jdeps`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích dependency và JDK internals.
- [Java SE 17 API — `jdeprscan`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeprscan.html): phát hiện API deprecated.
- [OpenJDK JEP 412 — Foreign Function & Memory API (Incubator)](https://openjdk.org/jeps/412): trạng thái incubator của FFM trong Java 17.

**Ghi nhớ:** thay API nội bộ là một bước migration về hợp đồng, không chỉ là sửa import. Hãy xác định chức năng, chọn API công khai có tài liệu, hiểu khác biệt về quyền truy cập và vòng đời, rồi kiểm thử trên Java 17 mà không dựa vào cờ mở JDK internals. Nếu không có API thay thế tương đương, thiết kế lại hoặc cô lập phần phụ thuộc nền tảng thay vì giả vờ rằng một cờ JVM đã giải quyết vấn đề.
