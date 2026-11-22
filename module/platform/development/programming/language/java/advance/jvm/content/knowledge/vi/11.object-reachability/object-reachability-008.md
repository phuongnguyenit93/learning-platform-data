# Finalization, deprecation và lựa chọn `try-with-resources` hoặc `Cleaner` trong Java

**Finalization** là cơ chế lâu đời của Java: một object có thể định nghĩa phương thức `finalize()`, và JVM có thể gọi nó sau khi xác định object không còn được truy cập theo những điều kiện nhất định của GC. Nó từng được dùng để đóng file, socket, database connection hoặc giải phóng native handle khi lập trình viên quên cleanup.

Tuy nhiên, **finalization không cung cấp thời điểm thực thi đáng tin cậy, có nguy cơ làm sống lại object, tạo lỗi concurrency, deadlock, rò tài nguyên và ảnh hưởng hiệu năng**. Java hiện khuyến nghị **không viết finalizer mới**. Với tài nguyên phải giải phóng đúng hạn, dùng **`AutoCloseable` + `try-with-resources`**; khi thực sự cần một tuyến dọn dẹp dự phòng lúc object không còn reachable, dùng **`java.lang.ref.Cleaner`**, đồng thời vẫn ưu tiên `close()` rõ ràng.

Bài học thuộc phần **Khả năng truy cập** trong JVM, tập trung vào reachability, vòng đời object và lựa chọn API phù hợp. Ví dụ chính chạy với **Java 17+**, chỉ minh họa kết quả stdout khi kiểm soát được thời điểm, **không giả định JVM chắc chắn chạy GC/finalizer/Cleaner trước một deadline**.

## 1. Phân biệt GC, finalization và cleanup tài nguyên

Có ba công việc thường bị nói gộp:

1. **GC memory reclamation:** JVM nhận ra object trên Java heap không còn cần thiết theo quy tắc reachability và có thể thu hồi vùng nhớ heap của object.
2. **Finalization:** cơ chế legacy có thể gọi override `Object.finalize()` trên một object đủ điều kiện, trước khi vùng nhớ của object được thu hồi theo trình tự hỗ trợ finalization.
3. **Resource cleanup:** đóng socket, file descriptor, transaction, native pointer hoặc lock/connection. Nhiều tài nguyên này **không tự được giải phóng đúng hạn chỉ vì Java object wrapper trở nên unreachable**.

```text
Java object trên heap
       │
       ├─ vẫn strongly reachable
       │     └─ ứng dụng đang giữ và sử dụng object
       │
       └─ không còn strong reachability
             │
             ├─ GC có thể phân tích reachability và xử lý references
             ├─ legacy finalization có thể chạy (nếu object có finalizer,
             │   runtime vẫn bật, và các điều kiện áp dụng)
             ├─ Cleaner có thể nhận phantom reachability notification
             │   và chạy cleaning action được đăng ký
             └─ heap storage có thể được tái sử dụng khi GC cho phép

Không nhầm:
  "object có thể được collect"
       ≠ "finalize chắc chắn đã chạy"
       ≠ "native/socket resource đã đóng đúng thời hạn".
```

GC có trách nhiệm với **Java heap**, nhưng connection pool, file descriptor, native allocation và OS handle còn có chính sách sở hữu/đóng riêng. Thiết kế chỉ dựa vào finalization có thể khiến một ứng dụng cạn file descriptors dù heap vẫn còn nhiều dung lượng và collector chưa muốn chạy.

### 1.1. Tại sao mạnh-yếu-ảo quan trọng?

Package `java.lang.ref` mô tả **strong, soft, weak, phantom reachability**. Finalization lịch sử có mối liên hệ với các giai đoạn reachability và xử lý object; `Cleaner` dùng cơ chế **phantom references** cùng reference queue để nhận thông báo khi đối tượng đăng ký không còn được truy cập bình thường.

Điểm khác cốt lõi: **Cleaner không gọi method của referent bằng cách lấy lại object qua `PhantomReference.get()`**. Cleaning action phải cầm **state độc lập** cần thiết để cleanup, vì phantom `get()` luôn trả `null`.

## 2. Tình trạng deprecated qua các JDK releases

Cần phân biệt việc **một API đánh dấu deprecated**, **deprecated for removal**, **disabled by default** và **removed**. Đó là bốn tình trạng khác nhau.

| Phiên bản / mốc | Tình trạng đáng nhớ |
| --- | --- |
| **Java 9** | `Object.finalize()` được đánh dấu **`@Deprecated(since="9")`**; `Cleaner` được giới thiệu |
| **JDK 17** | `Object.finalize()` vẫn tồn tại nhưng **deprecated**; finalization là cơ chế legacy, không nên dùng cho code mới |
| **JDK 18 – JEP 421** | Finalization được **deprecated for removal**; nhiều API liên quan được đánh dấu tương ứng; có tùy chọn `--finalization=disabled` để kiểm thử sự phụ thuộc |
| **JDK 26 (tài liệu migration 2026)** | Oracle vẫn mô tả finalization là **deprecated for removal**; không được khẳng định nó đã bị loại bỏ hoàn toàn chỉ vì có JEP 421 |
| **Một release tương lai** | Dự kiến cơ chế sẽ bị vô hiệu hóa theo mặc định rồi được gỡ bỏ theo quá trình chuyển đổi của nền tảng; thời điểm cụ thể phải kiểm chứng theo release notes tương ứng |

**Kết luận quan trọng:** “`Object.finalize()` deprecated” không có nghĩa compiler Java 17 không nhận diện method nữa. Ngược lại, compiler chấp nhận mã tương thích nhưng **cảnh báo**, và API được đánh dấu không nên dùng. Mốc **deprecated for removal ở JDK 18** là tín hiệu tương thích mạnh hơn, không phải một lời bảo đảm rằng code sẽ hỏng đúng ở bản JDK kế tiếp.

### 2.1. Thử vô hiệu hóa finalization ở JDK 18+

JEP 421 đưa ra công tắc kiểm thử khi runtime hỗ trợ:

```bash
# JDK 18+ có hỗ trợ tùy chọn theo JEP 421:
java --finalization=disabled -cp out MyApplication
```

Nó giúp phát hiện code hoặc dependency đang **phụ thuộc ngầm vào finalization**. Không sử dụng lệnh trên làm một ví dụ bắt buộc chạy được bằng Java 17: **JDK 17 không có `--finalization=disabled` được giới thiệu ở JDK 18**.

Lưu ý:

- Không được hiểu disabled finalization là disabled GC.
- Việc tắt finalization không tự động gọi `close()` thay bạn.
- Nếu ứng dụng có tài nguyên chỉ được đóng bằng `finalize()`, việc vô hiệu hóa có thể làm lộ resource leak hoặc thay đổi hành vi; đó là vấn đề cần sửa trong code/lifecycle.
- Không nên dùng tùy chọn JVM để né việc di trú khỏi finalizers trong codebase.
- Tài liệu JVM mới có thể đổi cờ/trạng thái qua các phiên bản; khi triển khai luôn kiểm tra `java -version` và release notes đúng vendor.

### 2.2. Vì sao “bị gỡ” khác “bị deprecated”?

**Deprecated:** lời gọi API vẫn có thể tồn tại và hoạt động, nhưng có cảnh báo/tài liệu khuyến cáo tránh dùng.

**Deprecated for removal:** API/cơ chế có kế hoạch bị gỡ; mã phụ thuộc nên được di trú sớm và kiểm thử tương thích.

**Disabled:** runtime có thể giữ code/API tương thích nhưng **không thực hiện công việc finalization**; logic dựa vào side effect của `finalize()` sẽ thất bại.

**Removed:** API/cơ chế không còn được cung cấp trong phạm vi phát hành cụ thể; source, binary compatibility hoặc runtime behavior có thể phải thay đổi.

Đừng suy trạng thái chỉ từ tên `finalize` trong stack trace hoặc mã thư viện cũ: phải xác định release và class thực sự được nạp.

## 3. `Object.finalize()` từng hoạt động ra sao?

Java 17 `Object.finalize()` có chữ ký:

```java
@Deprecated(since = "9")
protected void finalize() throws Throwable
```

Một class legacy có thể override:

```java
// ĐOẠN MÃ LỊCH SỬ ĐỂ ĐỌC/DI TRÚ, KHÔNG KHUYẾN NGHỊ VIẾT MỚI:
class LegacyResource {
    @Override
    protected void finalize() throws Throwable {
        try {
            // cleanupLegacyHandle();  // Giả định code cũ có native handle.
        } finally {
            super.finalize();
        }
    }
}
```

Đây là **snippet minh họa**, không phải file có `main`; cố ý không thực hiện tác vụ cleanup. Việc gọi `super.finalize()` trong một override `finalize()` không được Java tự chèn như cách constructor chain hoạt động.

### 3.1. Không có bảo đảm về thời điểm

Ngay cả khi finalization được bật:

- JVM không hứa gọi `finalize()` ngay khi một local variable ra khỏi scope.
- Có thể trì hoãn rất lâu hoặc **không chạy trước khi process kết thúc**.
- Không có thứ tự gọi finalizers giữa các objects khác nhau.
- Không được xây business rule giả định finalizer thực hiện trong thread hiện tại.
- Một exception không được xử lý ném từ `finalize()` bị bỏ qua theo quy tắc `Object.finalize()`; nó không tự chuyển về lời gọi business code để catch.

**Đừng dùng `System.gc()` hoặc `System.runFinalization()` như “đồng hồ” buộc finalizer chạy.** Các lời gọi đó không cung cấp SLA cho cleanup. `System.runFinalization()` cũng nằm trong nhóm API liên quan cần tránh và đã được deprecated for removal trong JDK 18.

### 3.2. Finalizer có thể làm object sống lại (resurrection)

Một finalizer legacy có thể đặt `this` vào static field/list rồi khiến object trở lại strongly reachable:

```java
// CHỈ LÀ MÔ HÌNH LỖI LỊCH SỬ — KHÔNG CHẠY VỚI GC TIMING CỐ ĐỊNH:
static Object resurrected;

@Override
protected void finalize() throws Throwable {
    resurrected = this; // Làm đối tượng có strong path trở lại.
}
```

Ở đây object từng đủ điều kiện finalization nhưng sau đó **resurrect**. Một finalizer **không được tự động gọi lại nhiều lần** cho cùng object đã finalizable theo hợp đồng. Vì vậy việc “dọn dẹp object lần nữa khi nó chết lần hai” không thể xem là đáng tin.

Không nên thử resurrection trong code production: nó làm phức tạp lifecycle, khó dự đoán thời điểm release native resources và là lý do cơ chế finalization bị phản đối.

### 3.3. Finalizer thread, locks và concurrency

Finalizer không chạy trên Java caller thread theo một thời điểm do bạn chọn. Nếu một finalizer cố chờ lock/thread trong khi một thread khác đang giữ lock và đợi GC-related work hoặc resource, ứng dụng có thể gặp deadlock hoặc hang. Finalization cũng gây áp lực lên GC/reference processing và làm objects cần sống lâu hơn để đi qua chu trình finalization.

Một finalizer làm I/O blocking kéo dài có thể khiến việc xử lý các finalizers khác bị trễ. Đây là vấn đề của thiết kế: **lifecycle không nên phụ thuộc vào một thread dọn dẹp bất định** khi tài nguyên cần đóng ngay sau khi xong việc.

## 4. Vì sao finalization không phù hợp cho quản lý tài nguyên?

### 4.1. Java heap không phản ánh số file descriptors

Ví dụ chương trình mở hàng nghìn file streams rồi bỏ reference:

```java
// Ví dụ PHẢN MẪU, không nên dùng:
for (int i = 0; i < 100_000; i++) {
    java.io.FileInputStream stream =
            new java.io.FileInputStream("data.txt");
    stream.read();
    // Không close(), chỉ bỏ reference.
}
```

Đây là **snippet không độc lập**, giả sử file tồn tại. Có thể hết OS file descriptors **trước khi** GC quyết định thu hồi các wrappers; ngoài ra exception ở `read()` càng khiến code bỏ qua đường cleanup.

Giải pháp đúng là **close tài nguyên tại thời điểm biết đã dùng xong**, không đợi heap thiếu chỗ. Chính Javadoc Java 17 của `FileInputStream` khuyến cáo đóng trực tiếp hoặc dùng try-with-resources.

### 4.2. Native pointer và use-after-free

Một Java wrapper có thể giữ `long handle` trỏ tới native resource. Nếu finalizer cleanup chạy sau khi optimizer thấy wrapper không còn live, trong khi mã native vẫn xử lý handle, có thể xảy ra **use-after-free**.

`Reference.reachabilityFence(wrapper)` có thể giữ wrapper strongly reachable tới một điểm xác định trong Java code, nhưng đây là công cụ bổ sung cho lifetime correctness, **không thay thế việc quản lý ownership và close có kiểm soát**.

### 4.3. Security và khả năng object nửa khởi tạo bị lợi dụng

Một số class có constructor ném exception trước khi khởi tạo hoàn chỉnh vẫn có thể gặp rủi ro liên quan finalization trong thiết kế legacy. Những cơ chế có khả năng làm đối tượng sống lại hoặc thực thi code lúc trạng thái chưa hoàn tất có thể mở lỗ hổng và làm khó lập luận bảo mật. Đây là một lý do được nêu trong JEP 421 khi deprecate finalization.

**Không dùng finalizer để thực hiện authorization, flush bắt buộc, commit transaction hoặc lưu trạng thái quan trọng**: bạn không có bảo đảm code ấy sẽ chạy đúng thời điểm, đúng thứ tự hoặc chắc chắn hoàn thành.

## 5. Lựa chọn số một: `AutoCloseable` + `try-with-resources`

Một resource có thể được đóng tường minh qua `close()`. Interface `AutoCloseable` định nghĩa:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Nhiều Java APIs như `InputStream`, `OutputStream`, `Reader`, JDBC `Connection`, `Statement`, `ResultSet` và `java.nio` resources hỗ trợ cơ chế đóng theo scope (cần xem contract riêng từng API).

`try-with-resources` trong Java giúp compiler gọi `close()` khi control rời `try`, kể cả:

- Hoàn tất bình thường.
- `return` từ thân `try`.
- Exception trong thân `try`.
- Những luồng điều khiển hợp lệ khác rời statement theo ngữ nghĩa Java.

Đây là **cleanup deterministic theo luồng điều khiển**, không phụ thuộc GC nhận ra object unreachable.

### 5.1. Thứ tự đóng khi có nhiều tài nguyên

Resources được **khởi tạo từ trái qua phải** và **đóng theo thứ tự ngược lại** (LIFO-like).

Tạo file **`TryWithResourcesOrderDemo.java`**:

```java
public class TryWithResourcesOrderDemo {
    static final class Tracer implements AutoCloseable {
        private final String name;

        Tracer(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Tracer first = new Tracer("A");
             Tracer second = new Tracer("B")) {
            System.out.println("body");
        }
        System.out.println("after");
    }
}
```

Biên dịch/chạy trên Java 17+:

```bash
javac --release 17 TryWithResourcesOrderDemo.java
java TryWithResourcesOrderDemo
```

**Stdout chính xác:**

```text
open A
open B
body
close B
close A
after
```

**Giải thích:** code tạo `A` rồi `B`, vào thân `try` và sau đó đóng `B` trước `A`. Đây là cơ chế `try-with-resources` theo ngôn ngữ Java, không phải JVM đợi GC trước khi gọi `close()`.

### 5.2. Nếu constructor resource thứ hai ném exception?

Nếu `new Tracer("B")` ném exception trong lúc resource acquisition, Java vẫn **đóng những resource trước đó đã khởi tạo thành công**, trong ví dụ là `A`. Như vậy try-with-resources bảo vệ cả trường hợp chưa vào phần body.

Đó là một lý do tạo resource ngay trong header `try` thay vì mở nhiều resources bằng `new` trước rồi dựa vào một `finally` viết tay.

### 5.3. Reusing effectively final resource (Java 9+)

Java 9 cho phép dùng biến tài nguyên `final` hoặc **effectively final** đã được khởi tạo trước:

```java
var stream = java.nio.file.Files.newInputStream(path);
try (stream) {
    // Đọc dữ liệu...
}
```

Đây là **snippet**, cần biến `path` kiểu `java.nio.file.Path` và xử lý `IOException`. Nó minh họa cú pháp `try (stream)` hỗ trợ Java 9+, trong khi các ví dụ độc lập của bài đều dùng Java 17.

**Lưu ý:** Resource phải thực hiện `AutoCloseable`, không thể chỉ có một method tên `close` không liên quan interface rồi mong compiler tự xử lý.

## 6. `try-with-resources` và suppressed exceptions

Có một tình huống quan trọng: **thân try ném exception, rồi `close()` cũng ném exception**. Java không đơn giản thay lỗi gốc bằng lỗi đóng (trong trường hợp thông thường):

- Exception từ phần thân try là **primary exception**.
- Exception từ `close()` được **suppressed** vào primary bằng cơ chế `Throwable.addSuppressed`.
- Caller catch primary và có thể xem các lỗi phụ qua `Throwable.getSuppressed()`.

### 6.1. Ví dụ Java 17 đầy đủ và stdout xác định

Tạo file **`SuppressedCloseDemo.java`**:

```java
public class SuppressedCloseDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource ignored = new FailingResource()) {
            throw new IllegalStateException("body failed");
        } catch (Exception ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" +
                    ex.getSuppressed().length);
            System.out.println("suppressedMessage=" +
                    ex.getSuppressed()[0].getMessage());
        }
    }
}
```

Chạy:

```bash
javac --release 17 SuppressedCloseDemo.java
java SuppressedCloseDemo
```

Stdout:

```text
primary=body failed
suppressedCount=1
suppressedMessage=close failed
```

`IllegalStateException` từ body vẫn là lỗi gốc. Exception từ `close` được giữ dưới dạng suppressed, không bị nuốt mất. Trong code production, đừng giả định `getSuppressed()[0]` luôn tồn tại; chương trình demo biết chắc resource được thiết kế để ném từ `close`.

### 6.2. `getCause()` không phải `getSuppressed()`

- **Cause chain:** thường chỉ nguyên nhân tạo ra một exception wrapper (ví dụ `new IOException("failed", cause)`).
- **Suppressed exceptions:** các lỗi phát sinh trong cleanup, được giữ thêm bên cạnh primary exception.

Khi chẩn đoán thất bại trong nhiều resources, đọc **exception chính**, **cause** và **suppressed exceptions**. Một log chỉ in `ex.getMessage()` có thể bỏ qua lỗi close quan trọng.

### 6.3. Trái ngược với `finally` viết tay

Một `finally` tự viết:

```java
try {
    throw new IllegalStateException("body failed");
} finally {
    throw new IllegalStateException("cleanup failed");
}
```

Đây là **snippet phản mẫu**; lỗi `cleanup failed` thay thế normal/abrupt completion trước đó và có thể che lấp lỗi `body failed` nếu không giữ lại thủ công. Try-with-resources được thiết kế để tránh mất primary exception trong tình huống đóng resource.

## 7. Lựa chọn số hai: `Cleaner` khi thật sự cần cleanup dự phòng

`java.lang.ref.Cleaner` xuất hiện từ Java 9, quản lý **phantom references và reference queues** để liên kết một object với **`Runnable` cleaning action**. Khi object đăng ký trở thành phantom-reachable theo quy tắc, Cleaner có thể thực hiện action trên thread phù hợp. API cũng cung cấp `Cleanable.clean()` để gọi action **một cách chủ động**.

Cleaner **tốt hơn finalization** về khả năng tách cleanup state khỏi referent và tránh trực tiếp gọi method của một object đang chết, nhưng **automatic Cleaner cleanup vẫn không có deadline đáng tin**.

### 7.1. API quan trọng

```java
Cleaner cleaner = Cleaner.create();
Cleaner.Cleanable cleanable = cleaner.register(owner, cleanupAction);
cleanable.clean();
```

- `owner` là object được theo dõi về phantom reachability.
- `cleanupAction` là `Runnable` thực hiện giải phóng state riêng.
- `cleanable.clean()` yêu cầu thực hiện cleanup **một lần nếu chưa thực hiện trước đó**.
- Action được Cleaner gọi **tối đa một lần** đối với registration tương ứng; nếu không explicit clean và object không trở thành phantom-reachable trong thời gian JVM chạy, action có thể **không chạy**.
- Khi automatic processing, action có thể chạy trên thread riêng do Cleaner quản lý và có thể đồng thời với code còn chạy; hành vi khi `System.exit` không có bảo đảm mọi action sẽ được chạy.
- Exception từ cleaning action được Cleaner bỏ qua theo API; logging/monitoring cần được thiết kế nếu cleanup có thể thất bại.

### 7.2. Sơ đồ không giữ owner sống sai cách

```text
ĐÚNG:
   Cleaner/registration ──strong──► State (handle/resource data)
            │
            └──phantom──► Owner
   State không có strong path trở lại Owner.

SAI:
   Cleaner/registration ──strong──► lambda cleanup
                                      │
                                      └──strong capture this──► Owner
   Owner vẫn strongly reachable → automatic Cleaner không thể kích hoạt.
```

**Điểm then chốt:** Không cho `cleanupAction` giữ strong reference tới `owner` — kể cả gián tiếp qua inner class, lambda `() -> this.close()`, hay field của `State` trỏ về owner. Nếu có, owner không thành phantom-reachable và cleanup sẽ không chạy tự động.

Dùng **`static` nested class chứa state cần đóng** là mô hình an toàn dễ hiểu.

## 8. Chương trình Cleaner + try-with-resources Java 17 hoàn chỉnh

Tạo file **`CleanerResourceDemo.java`**:

```java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

public class CleanerResourceDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final AtomicBoolean released = new AtomicBoolean();

        @Override
        public void run() {
            if (released.compareAndSet(false, true)) {
                System.out.println("release");
            }
        }
    }

    static final class Resource implements AutoCloseable {
        private final State state = new State();
        private final Cleaner.Cleanable cleanable =
                CLEANER.register(this, state);

        void use() {
            if (state.released.get()) {
                throw new IllegalStateException("closed");
            }
            System.out.println("using");
        }

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            resource.use();
        }
        System.out.println("after");
    }
}
```

Lệnh Java 17:

```bash
javac --release 17 CleanerResourceDemo.java
java CleanerResourceDemo
```

**Stdout xác định:**

```text
using
release
after
```

Giải thích:

1. `CLEANER` sống đủ lâu nhờ static reference.
2. Mỗi `Resource` tạo một `State` **không giữ reference ngược tới Resource**.
3. Cleaner đăng ký theo dõi `Resource` cùng `state`.
4. `try-with-resources` đảm bảo `close()` chạy khi rời body.
5. `close()` gọi `cleanable.clean()`, action chạy tại thời điểm rõ ràng khi method này được gọi.
6. `AtomicBoolean` mô tả một guard cho tình huống cleanup lặp/đồng thời; action không in/release hai lần. Dù `clean()` đã là at-most-once theo Cleanable, guard vẫn giúp minh họa việc state dọn dẹp nên idempotent.
7. Không cần `System.gc()` hoặc finalizer để ra stdout mong đợi.

**Đây là demo quản lý một resource giả lập**. `State.run()` chỉ in thông báo, không thực sự giải phóng native memory hoặc file descriptor. Ứng dụng thật cần logic `free(handle)`/`close(fd)`/release connection phù hợp, xử lý errors, thread-safety và đảm bảo code không dùng resource sau close.

### 8.1. Vì sao không khai báo non-static inner `State`?

`class State implements Runnable` nằm **bên trong `Resource` nhưng không có `static`** có thể có implicit strong reference tới outer `Resource`. Cleaner giữ `State` → `State` giữ owner → owner không phantom-reachable.

Trong ví dụ, `State` là **static nested class** thuộc `CleanerResourceDemo`, nên không có implicit outer instance reference. Nó cũng không giữ explicit field nào có loại `Resource`.

### 8.2. Vì sao cleaner không thay thế `close()`?

Cleaner chỉ có thể chạy tự động khi owner đủ điều kiện xử lý phantom reachability và runtime xử lý notification. GC thường kích hoạt bởi **heap memory pressure**, không bởi việc hệ điều hành sắp hết file handles. Một resource có thể ngừng được ứng dụng sử dụng nhưng vẫn giữ file descriptor lâu nếu chờ GC.

Vì thế thiết kế đúng thường là:

```text
Application lifecycle:
  acquire resource
       │
       ▼
  use resource trong try-with-resources
       │
       ▼
  close() → Cleanable.clean() → release đúng lúc

Fallback:
  application quên close()
       │
       ▼
  owner có thể phantom-reachable về sau
       │
       ▼
  Cleaner có thể chạy action ở thời điểm không bảo đảm
```

Fallback có thể giúp hạn chế một số leak, nhưng **không được là đường duy nhất cho tài nguyên quan trọng**.

## 9. Finalization và Cleaner: đừng so sánh nhầm trách nhiệm

| Thuộc tính | Legacy `finalize()` | `Cleaner` | `AutoCloseable` / try-with-resources |
| --- | --- | --- | --- |
| API / tình trạng | Deprecated; finalization deprecated for removal từ JDK 18 | Java 9+, API đang được khuyến nghị cho cleanup dự phòng | Chuẩn cho explicit lifecycle |
| Trigger thông thường | GC/finalization processing sau reachability conditions | Phantom reachability & reference processing | Scope exit / explicit `close()` |
| Thời điểm xác định? | **Không** | **Không** cho automatic cleanup | **Có**, theo luồng điều khiển Java |
| Có thể đảm bảo chạy trước JVM exit? | **Không** | **Không** (automatic) | Có khi control thực sự đi qua `close`/`try`, không phải nếu process bị kill |
| Có method trên object đang finalizing? | `finalize()` được gọi trên chính object | Action tách khỏi owner; **không** giữ owner | `close()` gọi khi object còn được code quản lý |
| Object resurrection? | Có thể trong finalizer legacy | Không được truy cập lại referent qua phantom `get()` | Không có finalizer resurrection pattern |
| Exception semantics | Uncaught finalizer exception bị bỏ qua | Exceptions từ cleaning action bị bỏ qua theo API | `close()` có thể throw và caller xử lý; suppressed exceptions |
| Có thể gọi cleanup chủ động? | Không dùng `finalize()` như close API | `Cleanable.clean()` | `close()` hoặc try-with-resources |
| Khi nào phù hợp? | **Không viết mới; chỉ xử lý/migrate legacy** | Fallback cho native/off-heap state khi không luôn kiểm soát được caller | File/socket/JDBC/native handle có rõ ownership và scope |

**Thực hành:** Nếu thư viện đã hỗ trợ `Closeable`/`AutoCloseable`, hãy dùng nó. Đừng tự bọc thư viện trong finalizer. Cleaner chỉ cần thiết khi thiết kế **một wrapper có state ngoại heap đặc thù**, muốn một lớp bảo vệ bổ sung khi consumer quên close.

## 10. Rủi ro nâng cấp: thư viện legacy phụ thuộc finalization

Một số code cũ đã ghi cleanup trong `finalize()` mà không có public `close()`. Khi migrate:

1. **Tìm override `finalize()`** trong codebase và bytecode của dependency khi có thể, không chỉ tìm những chỗ gọi `System.gc()`.
2. Xác định loại resource được giữ: OS file descriptor, native memory, executor, socket, registry entries hoặc data structure Java thuần.
3. Làm rõ **ai sở hữu resource** và thời điểm kết thúc sử dụng.
4. Bổ sung **`AutoCloseable`/`close()`** và sửa callers để dùng try-with-resources hoặc `finally`.
5. Nếu không kiểm soát được mọi client hoặc có native resource cần fallback, thiết kế Cleaner với **independent state** không giữ owner.
6. Kiểm tra idempotency và concurrency giữa explicit close, automatic cleanup và code đang sử dụng tài nguyên.
7. Loại bỏ finalizer legacy sau khi đảm bảo các đường cleanup khác bao phủ nhu cầu.
8. Kiểm thử trên JDK có hỗ trợ `--finalization=disabled` (JDK 18+) để phát hiện giả định còn sót.
9. Quan sát file handle/native memory metrics và integration tests trong môi trường thực, không chỉ số lượng objects còn trên heap.

### 10.1. Migration pattern trước – sau

**Trước (chỉ minh họa pattern legacy):**

```java
class LegacyHandle {
    private long nativeHandle;

    @Override
    protected void finalize() throws Throwable {
        try {
            releaseNative(nativeHandle);
        } finally {
            super.finalize();
        }
    }

    private static native void releaseNative(long handle);
}
```

Đây không phải chương trình độc lập và cố ý minh họa thiết kế cần bỏ. Nó thiếu close API và dựa vào GC timing.

**Sau — khung thiết kế phù hợp:**

```java
final class HandleOwner implements AutoCloseable {
    private final Cleaner.Cleanable cleanable;

    HandleOwner(long handle) {
        // State là static nested class, giữ handle độc lập,
        // dùng guard atomic để release at most once.
        State state = new State(handle);
        this.cleanable = CLEANER.register(this, state);
    }

    @Override
    public void close() {
        cleanable.clean();
    }
}
```

Đây là **pseudocode minh họa**, không phải Java file standalone: cần định nghĩa `CLEANER`, `State`, quyền sở hữu `handle` và native release logic. Chương trình `CleanerResourceDemo.java` ở mục 8 là phiên bản đầy đủ biên dịch/chạy để quan sát pattern và output.

### 10.2. Ownership phải rõ để tránh double-free

Đối với native handle, các phương thức như `releaseNative(handle)` có thể không an toàn nếu chạy hai lần. Thiết kế cần đồng bộ và chuyển trạng thái **OPEN → CLOSED** đúng một lần, không cho mượn raw handle sau close, và bảo đảm fail-safe trên đường exception.

Chỉ thêm một `boolean closed` bình thường không đủ khi nhiều threads có thể chạy đồng thời. Dùng AtomicBoolean/CAS hoặc synchronization phù hợp với API contract; nếu native resource được dùng song song, guard cho cleanup một lần cũng **chưa đủ** để chống use-after-close — còn cần thiết kế ownership/lifetime hoặc lock cho concurrent operations.

## 11. Trường hợp khó: resource phải sống đến sau thao tác native

GC/JIT có thể xem một wrapper Java không còn được dùng **sớm hơn cuối lexical scope**, nếu thread chỉ còn dùng primitive `long handle` được lấy từ wrapper. Cleaner có thể chạy trước khi một native operation sử dụng handle kết thúc nếu không bảo vệ lifetime.

Java cung cấp `Reference.reachabilityFence(Object)`:

```java
// Đoạn minh họa, giả định owner và nativeUse đã được khai báo:
long handle = owner.getHandle();
try {
    nativeUse(handle);
} finally {
    java.lang.ref.Reference.reachabilityFence(owner);
}
```

Phương thức fence giữ `owner` strongly reachable ít nhất đến vị trí fence. Nó **không gọi GC, không đóng resource**, cũng không thay thế việc khóa/đảm bảo đồng bộ khi `close()` có thể chạy từ thread khác.

Đặt fence trong `finally` giúp bảo đảm nó được gọi cả khi native operation ném Java exception. Hãy áp dụng khi có lifecycle cần thiết; không thêm một cách máy móc ở mọi nơi rồi coi đó là giải pháp toàn diện cho resource safety.

## 12. Tại sao không tự gọi `finalize()` để làm cleanup?

Một method tên `finalize()` về mặt Java vẫn có thể được gọi trực tiếp trong những tình huống access phù hợp, nhưng làm vậy **không biến nó thành API đóng tài nguyên có contract chuẩn**:

- Nó có visibility thường là `protected`, không dành cho consumer bên ngoài.
- Nếu JVM còn bật finalization, đường tự gọi không có nghĩa cơ chế GC sẽ không bao giờ gọi finalizer về sau.
- Code override có thể phụ thuộc vào các trạng thái chưa được chuẩn bị cho nhiều lần gọi.
- Một method dọn dẹp nên có tên/API rõ như `close()`, được gọi theo ownership và có trạng thái idempotent phù hợp.

**Không dùng** `object.finalize()`, `System.runFinalization()` hay `System.gc()` để xử lý một resource mà chính bạn biết đã dùng xong.

## 13. Cách kiểm tra mã legacy và cảnh báo compiler

### 13.1. Java 17 cảnh báo deprecated

Ví dụ đọc một class cũ có override `finalize()` (không khuyến khích chạy):

```java
class DeprecatedFinalizerDemo {
    @Override
    protected void finalize() throws Throwable {
        System.out.println("legacy cleanup");
        super.finalize();
    }
}
```

Nếu lưu thành `DeprecatedFinalizerDemo.java`, có thể biên dịch để **quan sát cảnh báo**:

```bash
javac --release 17 -Xlint:deprecation DeprecatedFinalizerDemo.java
```

Chương trình trên không có `main` và **không được dùng để đo số lần/timing finalizer**. Output cảnh báo của `javac` thay đổi theo compiler/version/locale, nên không đưa một stderr “chuẩn tuyệt đối”.

Trên JDK 18+, `finalize()`/finalization được đánh dấu deprecated for removal theo JEP 421, và compiler có thể hiển thị cảnh báo cụ thể hơn. Đừng dựa vào text warning cố định để quyết định application correctness.

### 13.2. Tìm override/bytecode

Có thể rà soát code sở hữu theo công cụ repository:

```bash
# Tìm các method declarations/overrides trong source (chỉ định hướng):
grep -R "finalize(" src

# Phân tích method trong một class đã compile:
javap -p YourClass
javap -c -p YourClass
```

Text search chỉ là bước đầu: một thư viện transitive có thể chứa finalizer mà source không nằm trong repository. Khi dùng `javap`, tên `finalize` trong binary không tự chứng minh nó thực sự quản lý tài nguyên hay finalization luôn đang được bật.

Một số APIs quản lý resource của JDK đã di trú khỏi finalization hoặc dùng cleanup khác; đọc Javadoc của **API/JDK release cụ thể** trước khi kết luận mọi `InputStream` “vẫn có finalizer”.

### 13.3. Kiểm thử khi disabled finalization

Một test có giá trị là: trên JDK 18+ có hỗ trợ `--finalization=disabled`, chạy integration suite mô phỏng tạo/dùng/đóng tài nguyên và khẳng định **không có file descriptor/native memory tăng vô hạn**. Test phải tập trung explicit cleanup và quota, **không** cần chờ GC để thành công.

Nếu test chỉ kiểm tra object bị thu hồi khi gọi `System.gc()` rồi không xem tài nguyên thực, có thể bỏ qua leak ở file descriptors, sockets hoặc native allocations.

## 14. Những nhầm lẫn thường gặp

1. **“Finalization đã bị xóa khỏi Java 17.”** Sai. `Object.finalize()` vẫn có trong Java 17 nhưng deprecated.
2. **“JEP 421 ra đời ở Java 9.”** Sai. Java 9 đánh dấu `Object.finalize()` deprecated; **JEP 421 thuộc JDK 18** và deprecate finalization for removal.
3. **“Deprecated for removal nghĩa là JDK kế tiếp chắc chắn xóa ngay.”** Sai. Không có ngày xóa cố định trong trạng thái này.
4. **“Finalization và garbage collection là cùng thao tác.”** Sai. GC có thể thu hồi heap; finalizer là callback legacy có chính sách xử lý riêng.
5. **“Một object vừa mất strong reference thì `finalize()` sẽ chạy ngay.”** Sai. Finalizer timing không được đảm bảo.
6. **“`System.gc()` là lệnh chạy đồng bộ hết finalizers.”** Sai. Không có SLA như vậy.
7. **“Finalizer có thể an toàn đảm nhiệm commit transaction.”** Sai. Không thể dựa vào thời điểm và bảo đảm hoàn thành.
8. **“Exception từ finalizer sẽ xuất hiện trong `catch` của caller.”** Sai. Uncaught finalizer exceptions thường bị bỏ qua theo contract.
9. **“Finalizer không thể giữ object sống lại.”** Sai. Legacy finalization có khả năng resurrection.
10. **“Nếu không có heap leak thì không thể có resource leak.”** Sai. File descriptors/native handles còn ngoài heap.
11. **“Mọi tài nguyên nên gắn `Cleaner` thay vì có `close()`.”** Sai. Explicit close là đường chính.
12. **“Cleaner action có thể gọi `owner.close()` thoải mái.”** Sai. Capture owner có thể khiến automatic cleanup không thể kích hoạt.
13. **“Cleaner chạy đúng khi scope kết thúc.”** Sai. Automatic cleaning phụ thuộc phantom reachability/GC; chỉ explicit clean có timing xác định.
14. **“Cleaner chắc chắn chạy trước `System.exit()`.”** Sai. Javadoc không đảm bảo.
15. **“Cleaning action được thực hiện bao nhiêu lần cũng được.”** Không nên. `Cleanable` có semantics at-most-once cho registration; state cleanup nên idempotent để bảo vệ resource.
16. **“try-with-resources chỉ gọi close khi không có exception.”** Sai. Nó đóng cả exceptional paths theo quy tắc.
17. **“Tài nguyên khai báo đầu tiên sẽ được đóng đầu tiên.”** Sai. Resources đóng theo thứ tự đảo.
18. **“Một exception từ close luôn xóa exception gốc của try.”** Sai. Try-with-resources dùng suppressed exceptions cho tình huống phù hợp.
19. **“`AutoCloseable` và `Closeable` là hai interface hoàn toàn không liên quan.”** Sai. `java.io.Closeable` mở rộng `AutoCloseable`, tinh chỉnh contract.
20. **“`reachabilityFence` chạy GC và giải phóng tài nguyên.”** Sai. Nó giữ strong reachability đến vị trí call.
21. **“Cứ dùng AtomicBoolean là hết race giữa use và close.”** Sai. Guard một lần release không tự giải quyết concurrent use-after-close.
22. **“Có Cleaner thì ứng dụng đã được miễn trách nhiệm xử lý suppressed exceptions.”** Sai. Exceptions trên explicit close, Cleaner action và business code có contract khác nhau.
23. **“Đọc tên `finalize()` trong bytecode là bằng chứng luôn có finalizer thread chạy.”** Sai. Runtime có thể tắt finalization theo JDK/flags; code có thể không thực thi.
24. **“JDK 17 có thể chạy lệnh `--finalization=disabled` như JDK 18.”** Sai. Cờ được giới thiệu ở JDK 18.

## 15. Tự kiểm tra và đáp án

**Câu 1.** Vì sao không nên đóng file/socket trong `finalize()`?

**Đáp án:** JVM không đảm bảo thời điểm hay việc finalizer sẽ chạy trước process exit; OS handles có thể cạn dù Java heap vẫn ổn.

**Câu 2.** `Object.finalize()` deprecated ở mốc nào, và JEP 421 làm gì?

**Đáp án:** Method được đánh dấu deprecated từ Java 9; JEP 421 ở JDK 18 đánh dấu finalization **deprecated for removal** và thêm phương án kiểm thử tắt cơ chế.

**Câu 3.** Ba resources `A`, `B`, `C` được khởi tạo thành công trong cùng `try` header. Đóng theo thứ tự nào?

**Đáp án:** **C → B → A**.

**Câu 4.** Thân `try` ném lỗi `E1`, `close()` ném `E2`. Với try-with-resources, lỗi nào là primary?

**Đáp án:** `E1` thường là primary; `E2` được suppressed vào `E1`, truy cập qua `getSuppressed()`.

**Câu 5.** Tại sao Cleaner action dạng `() -> this.release()` là bẫy?

**Đáp án:** Lambda capture `this`, Cleaner giữ action và qua đó giữ owner strongly reachable; owner có thể không bao giờ đạt phantom reachability để automatic action chạy.

**Câu 6.** `CleanerResourceDemo` in `release` do GC chạy đúng giờ hay do explicit close?

**Đáp án:** Do `try-with-resources` gọi `close()` và `close()` gọi `Cleanable.clean()`, nên stdout không cần GC timing.

**Câu 7.** `Cleaner` có bảo đảm mọi action sẽ chạy khi `System.exit()` không?

**Đáp án:** Không. Java 17 Javadoc nói behavior khi exit là implementation-specific; automatic cleanup không có deadline.

**Câu 8.** Một thư viện legacy cần test bỏ finalizer nhưng ứng dụng dùng JDK 17. Có dùng `--finalization=disabled` trực tiếp không?

**Đáp án:** Không. Flag đó được giới thiệu từ JDK 18. Chạy test trên một JDK có hỗ trợ flag hoặc di trú resource lifecycle sang explicit close.

**Câu 9.** `Reference.reachabilityFence(wrapper)` giúp xử lý tình huống nào?

**Đáp án:** Bảo đảm Java wrapper còn strongly reachable tới vị trí fence, hữu ích khi native operation vẫn cần resource gắn với wrapper dù optimizer không còn thấy use Java-level khác.

**Câu 10.** Vì sao atomic guard trong State không đủ để làm native resource thread-safe?

**Đáp án:** Nó giúp ngăn release hai lần, nhưng nếu thread khác vẫn đang sử dụng handle trong khi close, vẫn có nguy cơ use-after-close; cần ownership/synchronization policy.

**Câu 11.** Điều gì xảy ra khi code viết `finalize()` ném exception chưa bắt?

**Đáp án:** Theo `Object.finalize()` API contract, exception không được xử lý sẽ bị bỏ qua và việc finalization của object đó kết thúc; không trả về caller business code.

**Câu 12.** Khi nào nên dùng Cleaner thay vì chỉ có try-with-resources?

**Đáp án:** Khi thiết kế một wrapper quản lý state ngoài heap/native cần **cleanup dự phòng** nếu người dùng API quên close, đồng thời vẫn có explicit `close()` làm cơ chế chính. Nếu resource đã có close/lifecycle tốt, Cleaner thường không cần tự thêm.

## 16. Tổng kết bằng quyết định kiến trúc

```text
Bạn đang quản lý tài nguyên gì?
       │
       ├─ Object Java thuần, không có resource phải đóng?
       │       └─ Giữ references đúng nhu cầu, để GC quản lý heap.
       │
       └─ File/socket/JDBC/native handle/OS resource cần đóng?
               │
               ▼
       Có thể xác định owner và thời điểm kết thúc dùng?
               │
           Có  ├──► Implement AutoCloseable
               │     + try-with-resources / explicit close
               │     + test exceptional paths / suppressed exceptions
               │
           Không/khó kiểm soát mọi client?
               └──► Vẫn cung cấp explicit close
                     + cân nhắc Cleaner fallback
                     + State độc lập không capture owner
                     + đồng bộ và idempotent release
                     + chấp nhận automatic cleanup không có deadline

Legacy finalize():
    CHỈ để nhận diện, đánh giá và migrate;
    không chọn làm giải pháp thiết kế mới.
```

**Chốt kiến thức:** Garbage collection thu hồi **Java heap memory**, nhưng không cam kết tài nguyên hệ điều hành được đóng kịp thời. `Object.finalize()` là cơ chế đã deprecated và finalization bị **deprecated for removal từ JDK 18**, vì hành vi bất định, resurrection, security/reliability risks và chi phí. Với Java hiện đại, **`try-with-resources`/`AutoCloseable` là lựa chọn chính** cho lifecycle rõ ràng; **`Cleaner` chỉ bổ sung cleanup dự phòng** qua phantom reachability, với action không giữ owner và không có bảo đảm thời điểm. Thiết kế đúng phải chú ý ownership, exception preservation, race giữa use/close và kiểm thử khi finalization bị tắt.

### Tài liệu tham khảo chính thức

- [Java SE 17 — `Object.finalize()` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#finalize()): deprecated, timing/ordering/exception limitations và đề xuất alternatives.
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): mốc JDK 18, lý do và `--finalization=disabled`.
- [Oracle JDK 26 Migration Guide — Finalization Deprecated for Removal](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): trạng thái migration được tài liệu 2026 mô tả.
- [Java SE 17 — `Cleaner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): phantom reachability, no-reference-to-owner và at-most-once actions.
- [Java SE 17 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html).
- [JLS Java SE 17 — `try-with-resources` (§14.20.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): close order và suppressed exceptions.
- [Java SE 17 — `Throwable.getSuppressed()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()).
- [Java SE 17 — `Reference.reachabilityFence`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)).
- [Java SE 17 — `FileInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileInputStream.html): resource release guidance.
- [Oracle JDK 18 Release Notes — JEP 421](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html).
