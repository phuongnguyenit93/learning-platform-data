# System.gc() là yêu cầu gợi ý và không thay thế quản lý vòng đời đối tượng

> **Module:** Java Core — class/object  
> **Nhóm:** Vòng đời đối tượng  
> **Chủ đề chính:** Hiểu `System.gc()`, giới hạn của garbage collection và cách chủ động quản lý vòng đời tài nguyên  
> **Yêu cầu chạy ví dụ:** JDK 17+, không dùng preview features.

## 1. Thông điệp quan trọng nhất

Java có **garbage collector (GC)** để tự động thu hồi **bộ nhớ heap của những object không còn reachable theo cơ chế runtime**. Lời gọi:

~~~java
System.gc();
~~~

**chỉ gợi ý JVM nỗ lực thực hiện garbage collection**. Nó không là mệnh lệnh đồng bộ bắt buộc JVM phải thu gom một object cụ thể, không bảo đảm mọi object đủ điều kiện sẽ được thu hồi ngay, không bảo đảm giảm resident memory của tiến trình và **không có nghĩa các tài nguyên như socket, tệp, database connection được đóng đúng thời điểm**.

Vì vậy cần tách ba việc:

1. **Khi nào một object còn được chương trình tham chiếu?** Đây là vấn đề reachability, ownership và retaining references.
2. **Khi nào heap memory của object trở nên đủ điều kiện được GC thu hồi?** Khi không còn reachable qua các GC roots theo runtime semantics; đủ điều kiện không đồng nghĩa được thu hồi ngay.
3. **Khi nào tài nguyên bên ngoài heap được giải phóng?** Phần lớn trường hợp cần lifecycle API rõ ràng như `close()`, `shutdown()`, `unsubscribe()`, `remove()`; không chờ GC.

Nguyên tắc vận hành:

- Không dùng `System.gc()` để thay thế `try-with-resources`.
- Không viết unit test dựa trên giả định “gọi `System.gc()` là object đã bị thu hồi”.
- Không chèn `System.gc()` vào mỗi vòng lặp/transaction với kỳ vọng “chữa memory leak”.
- Không nhầm việc xóa một Java reference với việc đóng một OS resource.
- Giữ lifetime của các strong references đúng nhu cầu; quản lý cache, listeners, threads và registries có chính sách giải phóng rõ.
- Nếu thật sự cần đo/tối ưu GC, dùng **dữ liệu đo đạc và GC diagnostics**, không suy đoán từ một lời gọi API.

Các phần tiếp theo giải thích tại sao những nguyên tắc này đúng, rồi đi từ ví dụ đơn giản đến mẫu quản lý tài nguyên, Cleaner, weak references và các ca memory retention thường gặp.

## 2. Vòng đời object nhìn từ Java source và JVM

Một cách hiểu hữu ích, không đồng nhất với các phase tuyệt đối của tất cả garbage collectors:

~~~text
Tạo object
    |
    v
Có reference reachable từ chương trình
    |
    |  Có thể có nhiều aliases/owners, local variables, fields, collections
    v
Không còn reachable từ GC roots
    |
    v
Đủ điều kiện được garbage collector thu hồi
    |
    |  GC được chọn thời điểm, có thể không chạy ngay
    v
Heap storage có thể được thu hồi/tái sử dụng bởi JVM
~~~

Lưu ý: Java language/runtime không cam kết rằng mỗi object sẽ lần lượt xuất hiện trong một trạng thái có thể quan sát như sơ đồ trên. Đây là mô hình tư duy giúp phân biệt **khả năng reach** và **thời điểm reclamation**.

### 2.1. Tạo object không có nghĩa tự quản lý heap allocation

Với:

~~~java
User user = new User("Lan");
~~~

`new` tạo một instance theo Java semantics. JVM và garbage collector quản lý vùng nhớ thực tế, có thể sử dụng các kỹ thuật như allocation buffers, escape analysis, scalar replacement hoặc các tối ưu khác. Đừng coi mọi lệnh `new` bắt buộc tạo một đối tượng vật lý tồn tại suốt một thời điểm có thể quan sát bằng công cụ.

### 2.2. Reference variable khác object

~~~java
User first = new User("Lan");
User second = first;
first = null;
~~~

`first` đã không còn trỏ tới object nhưng `second` vẫn giữ một strong reference. Object **vẫn reachable**. Phép gán null chỉ thay giá trị của biến first, **không phải lệnh delete object**.

### 2.3. Object có thể sống lâu hơn scope mà bạn dự đoán

Một object tạo trong method có thể được trả về, đặt trong field, static collection, event listener, background task hoặc callback. Khi ấy nó có thể tiếp tục reachable sau khi method kết thúc.

Ngược lại, JVM có thể xác định một local không còn được sử dụng trước lexical end của scope trong một số tối ưu. Khi cần chủ động đảm bảo object **còn strongly reachable tới một mốc cụ thể** trong mã tương tác native/weak references, `Reference.reachabilityFence(object)` là API chuyên dụng.

### 2.4. Mất reference chưa chắc đóng tài nguyên

Ngay cả khi một object bọc file/socket trở nên unreachable, underlying file descriptor hay socket state không có một **deadline đóng** do `System.gc()` cung cấp. Hãy dùng resource API rõ ràng.

## 3. Reachability và GC roots

Garbage collectors thường phân tích **đồ thị references** từ những điểm gốc (GC roots). Mô hình khái quát:

~~~text
GC roots
  |
  +---- local variables / thread frames (khi runtime xem là live)
  |
  +---- static fields / class-related roots khi classes còn live
  |
  +---- runtime, JNI, synchronization và các roots khác
  |
  v
Object A ---> Object B ---> Object C
      \
       ----> Object D
~~~

Nếu JVM có thể tìm đường strong-reference từ một root đến object, object đó còn reachable theo cơ chế thích hợp. GC không được phép tùy ý xóa một object còn phải có thể được truy cập hợp lệ qua strong references.

### 3.1. GC roots không phải một List trong source code

Không có public Java API đơn giản để hỏi “toàn bộ roots cho object này là gì”. Roots là khái niệm của JVM runtime/collector, biến đổi theo runtime execution. Công cụ heap dump và reference analysis có thể giúp phân tích retaining paths.

### 3.2. Static field có thể giữ objects sống rất lâu

~~~java
static final java.util.List<Object> CACHE =
        new java.util.ArrayList<>();
~~~

Nếu bạn liên tục gọi `CACHE.add(...)` mà không xóa/bound entries, các objects trong List còn reachable qua static field chừng nào holder class và references liên quan còn live. `System.gc()` không thể tự quyết định rằng các entries “đã cũ” và được phép xóa chúng khỏi collection.

### 3.3. Listeners và callbacks cũng giữ references

Khi một event dispatcher giữ listener trong List, listener có thể capture một object lớn. Nếu không unsubscribe khi screen/session/service kết thúc, dispatcher vẫn có đường strong reference tới captured state. Đây có thể là **retention leak**, dù garbage collector hoạt động đúng.

### 3.4. ThreadLocal và long-lived threads

`ThreadLocal` giúp gắn value vào từng thread. Với threads sống lâu, đặc biệt trong thread pools, quên gọi `remove()` khi một task kết thúc có thể kéo dài lifetime của values (chi tiết còn phụ thuộc cách ThreadLocal map giữ keys/values). Đúng giải pháp thường là `try/finally { threadLocal.remove(); }`, không phải gọi `System.gc()`.

### 3.5. Cyclic references không tự là leak

~~~java
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;
~~~

Một chu trình A↔B vẫn có thể được GC thu hồi **nếu không còn strong-reference path từ roots đến chu trình**. Bạn không cần tự phá mọi reference cycle chỉ để GC nhận ra unreachable cycle. Nhưng nếu một static field vẫn trỏ tới A, cả chu trình vẫn reachable.

## 4. Chương trình hoàn chỉnh 1 — mất local reference chưa chứng minh object đã được thu hồi

Tạo tệp **`ReachabilityBasicsDemo.java`**:

~~~java
public class ReachabilityBasicsDemo {
    static final class Node {
        static int created;
        Node next;

        Node() {
            created++;
        }
    }

    public static void main(String[] args) {
        Node a = new Node();
        Node b = new Node();

        a.next = b;
        b.next = a;

        System.out.println("Created = " + Node.created);
        System.out.println("Cycle = "
                + (a.next == b && b.next == a));

        a = null;
        b = null;

        System.out.println("Variables cleared = "
                + (a == null && b == null));
        System.out.println("GC timing = not asserted");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ReachabilityBasicsDemo.java
java ReachabilityBasicsDemo
~~~

**Stdout chính xác:**

~~~text
Created = 2
Cycle = true
Variables cleared = true
GC timing = not asserted
~~~

### 4.1. Điều demo chứng minh

- Hai Node constructors đã được chạy.
- Có một object graph với cycle.
- Hai variables được gán null.
- Không có phép kiểm tra nào trong demo khẳng định garbage collector đã thu hồi hai objects.

### 4.2. Điều demo không thể chứng minh

Nó **không** cho biết chính xác GC có chạy hay không, thời điểm heap space được reclaim, hay bytecode/JIT đã giữ một reference tới node cuối cùng đến mốc nào. Đó là chủ ý: đừng biến garbage collection timing thành expected output của Java business program.

### 4.3. Không nhầm biến `created` với số object hiện còn sống

`created` là số lần constructor chạy theo chương trình ví dụ, **không phải live instance count**. Giảm số references không tự giảm static counter. Một static counter tự duy trì sẽ không được GC cập nhật sau khi object mất reachability.

## 5. System.gc() thực sự là gì?

`System.gc()` là một static method của `java.lang.System`. Nó **gợi ý** JVM nỗ lực thu hồi bộ nhớ của những objects không còn được sử dụng. Lời gọi này về mặt hiệu ứng API tương đương:

~~~java
Runtime.getRuntime().gc();
~~~

JVM/collector được quyền quyết định cách phản hồi với gợi ý, chịu ảnh hưởng của implementation, flags, workload và các ràng buộc runtime.

### 5.1. “Gợi ý” không có nghĩa luôn bỏ qua

Trong một số JVM configurations, explicit GC request có thể kích hoạt nỗ lực garbage collection và tốn chi phí đáng kể, thậm chí có pauses. Không nên nói “System.gc() vô tác dụng trong mọi JVM”.

### 5.2. “Gợi ý” không có nghĩa luôn thực thi một full GC

Không được hứa rằng mỗi call sẽ kích hoạt một “full GC” theo cách thống nhất. Các collectors khác nhau, JVM flags khác nhau và phiên bản JDK khác nhau có thể phản ứng khác nhau, hoặc cho phép vô hiệu hóa explicit GC.

### 5.3. Không có cam kết thu hồi object cụ thể

Không có API contract kiểu “sau khi System.gc() trả về, weak reference X chắc chắn null” hoặc “object Y đã được dọn xong”. JVM có thể đã nỗ lực nhưng một object vẫn reachable; hoặc không reclaim theo thời điểm mà test giả định.

### 5.4. Không có cam kết heap memory được trả lại OS

Ngay cả khi GC thu hồi internal heap space cho JVM tái sử dụng, process resident set size/committed heap có thể không giảm theo điều người quan sát mong đợi. JVM thường quản lý reserved/committed memory và collector policies riêng. **Heap free space, committed heap và bộ nhớ vật lý của tiến trình là các số đo khác nhau.**

### 5.5. Gọi nhiều lần không tạo deadline

~~~java
for (int i = 0; i < 100; i++) {
    System.gc();
}
~~~

Không tạo ra một bảo đảm mạnh hơn về “tất cả resources được giải phóng trước thời gian T”. Ngược lại có thể tăng overhead hoặc pause tùy JVM; đừng dùng đây làm production cleanup loop.

## 6. Chương trình hoàn chỉnh 2 — gọi hint mà không suy diễn kết quả

Tệp **`ExplicitGcHintDemo.java`**:

~~~java
public class ExplicitGcHintDemo {
    public static void main(String[] args) {
        System.out.println("Before hints");

        System.gc();
        Runtime.getRuntime().gc();

        System.out.println("After hints");
        System.out.println("Collected object count = unknown");
        System.out.println("Resource closure = separate contract");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ExplicitGcHintDemo.java
java ExplicitGcHintDemo
~~~

**Stdout chính xác:**

~~~text
Before hints
After hints
Collected object count = unknown
Resource closure = separate contract
~~~

### 6.1. Vì sao không in số objects đã thu hồi?

Java SE không cung cấp một method “System.gc() trả lại số objects vừa bị reclaim”. In một số tùy đo được sẽ dễ gây nhầm rằng đó là kết quả được bảo đảm của method.

### 6.2. Vì sao System.gc và Runtime.gc cùng xuất hiện?

Chỉ để minh họa liên hệ API. Trong code thực tế hiếm khi có lý do gọi cả hai liên tiếp; chúng không phải hai công đoạn bắt buộc.

### 6.3. Có thể mất thời gian chạy khác nhau dù stdout giống nhau

Tùy JVM configuration và machine, explicit GC call có thể là một nỗ lực đáng kể, một thao tác được điều chỉnh bởi collector, hoặc gần như không có tác dụng. Vì thế demo chỉ hứa **stdout**, không hứa timings hay collection counts.

## 7. Điều kiện đủ để “đủ điều kiện GC” không phải là gọi System.gc()

Một object có thể đủ điều kiện garbage collection khi nó không còn reachable từ GC roots dưới các reference-processing rules thích hợp. Lời gọi `System.gc()` không làm các strong references tự mất đi.

Ví dụ:

~~~java
static final List<byte[]> BUFFERS = new ArrayList<>();

static void addBuffer() {
    BUFFERS.add(new byte[1024]);
}
~~~

Nếu mã cứ thêm buffers mà giữ List này trong một live static owner, các buffers vẫn reachable dù bạn gọi System.gc sau mỗi lần thêm. Bản thân collector **không có quyền xóa dữ liệu mà chương trình vẫn tham chiếu mạnh và có thể sử dụng**.

### 7.1. Gán null có thể giúp giải phóng reference nhưng không bảo đảm reclamation

~~~java
buffer = null;
~~~

Chỉ thay reference ở biến buffer. Nếu còn alias trong List hoặc object field khác, object vẫn reachable. Nếu không còn alias, object có thể đủ điều kiện GC, nhưng không có deadline.

### 7.2. Loại bỏ khỏi collection quan trọng hơn hint

~~~java
BUFFERS.clear();
~~~

giải phóng những strong references từ List tới elements (nếu không còn alias nào khác). Nó có thể giúp elements không còn reachable, **không đồng nghĩa hệ điều hành nhận lại bộ nhớ ngay**.

### 7.3. Đừng nhầm clear collection với close resources

Nếu List chứa các objects AutoCloseable đang quản lý sockets/files, `clear()` **không gọi close()**. Cần thiết kế cách đóng từng resource trước hoặc đồng thời loại bỏ reference, theo ownership policy.

## 8. Chương trình hoàn chỉnh 3 — static retention và cleanup đúng chỗ

Tệp **`RetentionReleaseDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RetentionReleaseDemo {
    static final List<byte[]> RETAINED = new ArrayList<>();

    static void createAndRetain() {
        RETAINED.add(new byte[8]);
        RETAINED.add(new byte[16]);
    }

    static void releaseRetention() {
        RETAINED.clear();
    }

    public static void main(String[] args) {
        createAndRetain();

        System.out.println("Retained entries = "
                + RETAINED.size());
        System.out.println("First buffer bytes = "
                + RETAINED.get(0).length);

        System.gc(); // Không loại bỏ phần tử khỏi RETAINED.

        System.out.println("After GC hint entries = "
                + RETAINED.size());

        releaseRetention();

        System.out.println("After clear entries = "
                + RETAINED.size());
        System.out.println("Reclamation time = unspecified");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 RetentionReleaseDemo.java
java RetentionReleaseDemo
~~~

**Stdout chính xác:**

~~~text
Retained entries = 2
First buffer bytes = 8
After GC hint entries = 2
After clear entries = 0
Reclamation time = unspecified
~~~

### 8.1. Vì sao System.gc không xóa List elements?

`RETAINED` vẫn là static List giữ references đến hai arrays. GC không tự xóa dữ liệu mà code vẫn có thể đọc hợp lệ; ArrayList.size vẫn là 2.

### 8.2. Vì sao clear xong không in “bytes freed = 24”?

List.clear loại bỏ entries, nhưng không trực tiếp đo heap reclamation. JVM có thể reclaim arrays vào thời điểm khác, compiler/JIT có thể tối ưu allocation và số bytes thực tế của array object còn gồm header/alignment. In 24 bytes freed sẽ là một khẳng định sai.

### 8.3. Vấn đề sản xuất là retention policy

Nếu một cache cần giữ buffers để tăng throughput, phải có giới hạn dung lượng, eviction, TTL và observability phù hợp. Không nên cứ giữ vô hạn rồi gọi `System.gc()` như một cơ chế giảm size.

## 9. GC-managed heap memory khác tài nguyên phải quản lý chủ động

Một Java object có thể vừa:

- có fields nằm trên heap (GC tự thu hồi khi unreachable), và
- **sở hữu hoặc tham chiếu tài nguyên khác** có lifecycle riêng.

Ví dụ:

| Loại | Java object đại diện | Thao tác lifecycle thích hợp |
| --- | --- | --- |
| Stream đọc/ghi file | `InputStream`, `OutputStream` | `close()` / try-with-resources |
| Socket/network connection | `Socket` hoặc client-specific resource | `close()`, theo API tương ứng |
| JDBC connection/statement/result set | `Connection`, `Statement`, `ResultSet` | `close()`, pooling lifecycle đúng |
| File channel | `FileChannel` | `close()` |
| Executor service | `ExecutorService` | `shutdown()` / `shutdownNow()` hoặc `close()` trên API/version phù hợp |
| Listener registration | callback/subscription handle | `removeListener`/`unsubscribe`/`close` theo API |
| Lock | `Lock` | `unlock()` trong finally sau khi lock được acquire |
| ThreadLocal value | `ThreadLocal<T>` | `remove()` khi hết scope ứng dụng |
| Cache entries | `Map`, caching library | remove/eviction/size policy |
| Temporary files | `Path` / filesystem | `Files.deleteIfExists()` theo policy |

**Điểm chung:** GC không thay business-level ownership semantics. Một số frameworks có background cleaners/final fallback, nhưng đó không phải lý do bỏ explicit resource management.

### 9.1. AutoCloseable không có nghĩa JVM tự gọi close khi unreachable

`AutoCloseable` chỉ là một interface có method `close()`. Java không tự gọi close dựa trên GC reachability. **Try-with-resources** mới là cấu trúc ngôn ngữ chủ động gọi close khi thoát khỏi scope, kể cả khi có exception.

### 9.2. Close không đồng nghĩa object bị GC ngay

Sau `resource.close()`, biến resource vẫn có thể trỏ tới Java wrapper object; GC có thể thu hồi object ấy về sau khi unreachable. `close` và GC giải quyết hai loại trách nhiệm khác nhau.

### 9.3. Không phải AutoCloseable nào cũng idempotent theo contract chung

Một số resource implementations cho phép gọi close nhiều lần an toàn; không nên mặc định mọi AutoCloseable trong mọi library đều cho phép. Thiết kế riêng của bạn có thể chủ động chọn close idempotent, và document nếu điều đó là contract.

## 10. Try-with-resources: công cụ chính để đóng resources đúng scope

Cú pháp:

~~~java
try (Resource resource = acquire()) {
    use(resource);
}
~~~

Yêu cầu Resource implements `AutoCloseable` (hoặc subtype `Closeable`). Khi thoát scope, Java gọi `close()` tự động theo language rules. Điều này áp dụng khi block kết thúc bình thường hoặc throw exception.

### 10.1. Nhiều resources đóng theo thứ tự đảo ngược

~~~java
try (A first = acquireA();
     B second = acquireB()) {
    use(first, second);
}
~~~

`second.close()` chạy trước `first.close()`. Đây là quy tắc hữu ích khi resource B phụ thuộc A và cần đóng theo reverse acquisition order.

### 10.2. Khác với finally thủ công

Có thể viết:

~~~java
Resource resource = acquire();
try {
    use(resource);
} finally {
    resource.close();
}
~~~

Đây là fragment chỉ minh họa; nếu exception xảy ra trong cả use và close, xử lý primary/suppressed exception cần cẩn thận. Try-with-resources cung cấp quy tắc chuẩn cho việc giữ primary exception và ghi close exceptions thành **suppressed exceptions** khi phù hợp.

### 10.3. Scope càng rõ, lifecycle càng dễ kiểm tra

Đừng giữ một `InputStream` trong static field rồi hy vọng JVM đóng sớm. Tạo resource ở nơi có owner rõ ràng và ràng buộc lifetime bằng try-with-resources khi API cho phép.

## 11. Chương trình hoàn chỉnh 4 — thứ tự đóng và số resource còn mở

Tệp **`TryWithResourcesLifecycleDemo.java`**:

~~~java
public class TryWithResourcesLifecycleDemo {
    static final class Tracker {
        int open;
    }

    static final class Resource implements AutoCloseable {
        private final String name;
        private final Tracker tracker;
        private boolean closed;

        Resource(String name, Tracker tracker) {
            this.name = name;
            this.tracker = tracker;
            tracker.open++;
            System.out.println("open " + name);
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            System.out.println("use " + name);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                tracker.open--;
                System.out.println("close " + name);
            }
        }
    }

    public static void main(String[] args) {
        Tracker tracker = new Tracker();

        try (Resource first = new Resource("A", tracker);
             Resource second = new Resource("B", tracker)) {
            first.use();
            second.use();
            System.out.println("inside open = " + tracker.open);
        }

        System.out.println("outside open = " + tracker.open);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 TryWithResourcesLifecycleDemo.java
java TryWithResourcesLifecycleDemo
~~~

**Stdout chính xác:**

~~~text
open A
open B
use A
use B
inside open = 2
close B
close A
outside open = 0
~~~

### 11.1. Vì sao stdout đáng tin?

Thứ tự constructor/body/close được xác định bởi Java try-with-resources semantics. Không cần đo thời điểm object bị GC và không phụ thuộc collector chạy hay không.

### 11.2. Vì sao counter bằng 0 sau try?

`close()` được gọi trên hai resources và mỗi lần trừ tracker.open một lần. Đây là **trạng thái resource do chương trình quản lý**, không phải số heap objects đã bị garbage collected.

### 11.3. Vì sao code chống đóng hai lần?

Field `closed` ngăn việc giảm counter lần hai. Đây là một **idempotent close implementation của ví dụ**, không phải khẳng định AutoCloseable nào cũng idempotent.

### 11.4. Thêm System.gc vào chương trình có ích không?

Không cho mục tiêu “đóng A và B”. Java đã đóng cả hai đúng thứ tự bằng try-with-resources. System.gc không cải thiện correctness của resource lifecycle này.

## 12. Exceptions khi đóng tài nguyên: primary và suppressed

Nếu code trong try block ném exception, và `close()` cũng ném exception, Java ưu tiên bảo toàn exception của try block là **primary exception**. Exception từ close có thể được thêm vào danh sách **suppressed exceptions**.

### 12.1. Vì sao điều này quan trọng?

Nếu viết cleanup sai với finally, lỗi close có thể che lỗi thực sự của work, làm debugging khó. Try-with-resources cung cấp cơ chế chuẩn để giữ cả hai thông tin lỗi.

### 12.2. Khi nào cần log suppressed exceptions?

Nếu debugging một failure trong pipeline gồm nhiều resources, kiểm tra `Throwable.getSuppressed()`. Một exception primary có thể mang nhiều suppressed exceptions từ các close() calls theo reverse order.

### 12.3. Chương trình hoàn chỉnh 5 — exception vẫn đóng resource

Tệp **`SuppressedCloseDemo.java`**:

~~~java
import java.io.IOException;

public class SuppressedCloseDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing resource");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) throws Exception {
        try (FailingResource resource = new FailingResource()) {
            System.out.println("work started");
            throw new IllegalStateException("work failed");
        } catch (IllegalStateException ex) {
            System.out.println("primary = " + ex.getMessage());
            System.out.println("suppressed count = "
                    + ex.getSuppressed().length);
            System.out.println("suppressed message = "
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SuppressedCloseDemo.java
java SuppressedCloseDemo
~~~

**Stdout chính xác:**

~~~text
work started
closing resource
primary = work failed
suppressed count = 1
suppressed message = close failed
~~~

### 12.4. Điểm cần ghi nhớ

Resource vẫn được yêu cầu close khi body throw. Body exception là primary; close exception được giữ như suppressed. Đó là **quản lý tài nguyên xác định bởi cấu trúc ngôn ngữ**, hoàn toàn khác với việc chờ System.gc.

## 13. Lỗi thiết kế: dựa vào finalize() để đóng resource

Trước đây, một số code override `finalize()` để thử cleanup khi object sắp bị garbage collected. Cách này có nhiều vấn đề:

- Không có đảm bảo finalizer sẽ chạy đúng lúc hoặc chạy trước program termination.
- GC timing không xác định, còn finalization có cơ chế/queue/thread xử lý riêng.
- Có nguy cơ resource exhaustion vì file/socket được giữ quá lâu.
- Finalization phức tạp về concurrency, exception behavior và object resurrection.
- Có thể gây performance/security concerns.
- Java đã đánh dấu finalization là cơ chế lỗi thời; đừng thiết kế code mới dựa vào `finalize()`.

**Không viết production cleanup dựa trên `finalize()`, và không nghĩ rằng `System.gc()` sẽ khiến finalizer chạy ngay.**

### 13.1. Vòng đời resource phải do owner quyết định

Nếu một method mở file, nó thường nên sở hữu phạm vi đóng bằng try-with-resources. Nếu object giữ connection trong suốt lifetime của service, service cần lifecycle hooks rõ như start/stop/close và shutdown coordination.

### 13.2. Không tự gọi finalize() như close()

`finalize()` không phải API điều khiển lifetime chuẩn. Gọi trực tiếp một method finalize (nếu accessible) không thay thế resource-specific close và còn làm code khó hiểu.

### 13.3. API thay thế là gì?

- **`AutoCloseable` + try-with-resources:** giải phóng xác định trong logical scope.
- **`Cleaner`:** fallback cleanup action khi referent đạt điều kiện phù hợp; thời điểm chạy tự động **không đảm bảo**, không thay explicit close.
- **`PhantomReference` + `ReferenceQueue`:** xây cơ chế theo dõi post-reachability chuyên dụng khi thực sự cần; không tự tạo deterministic cleanup.
- **Lifecycle hooks của framework/service:** shutdown pools, subscriptions, transactions theo owner.

## 14. Cleaner là hỗ trợ dự phòng, không phải “GC-controlled close” có deadline

Từ Java 9, `java.lang.ref.Cleaner` cung cấp API đăng ký cleanup action liên kết với reachability của một object.

Các ý quan trọng:

1. `Cleaner.create()` tạo một Cleaner.
2. `cleaner.register(referent, action)` trả `Cleaner.Cleanable`.
3. Khi referent đạt trạng thái phù hợp, cleaner **có thể** thực hiện action thông qua cơ chế background cleanup.
4. `cleanable.clean()` cho phép yêu cầu chạy action tường minh; mỗi registration được clean tối đa một lần theo contract.
5. Action **không được giữ strong reference tới referent**, nếu không referent có thể không bao giờ đủ điều kiện cho automatic cleanup.
6. Cleanup action phải xử lý lifecycle/concurrency phù hợp; không dựa vào background timing để đảm bảo correctness của resource.

### 14.1. Khi nào Cleaner có ích?

Khi bạn xây một abstraction có native resource/handle đặc biệt và muốn **safety net** nếu client quên close. Nó không có nghĩa developer nên bỏ `close()` rồi chỉ đợi Cleaner thread chạy.

### 14.2. Không dùng cleanup action capture `this`

Sai về thiết kế:

~~~java
cleaner.register(this, () -> release(this.handle));
~~~

Lambda có thể capture `this`; action được Cleaner giữ reference làm referent reachable, phá mục tiêu automatic cleanup.

Thay vào đó, tách state/action owner thành một object độc lập không giữ referent:

~~~java
State state = new State(nativeHandle);
cleaner.register(this, state);
~~~

Đây là **conceptual fragment**, với State phải không giữ strong reference trở lại referent và tự xử lý giải phóng handle một lần.

### 14.3. Không in output của background Cleaner rồi gọi đó là deterministic

Một unit test viết `System.gc(); assert cleanupPrinted;` có thể pass trên một máy nhưng fail trên máy khác. Demo dưới đây dùng `clean()` chủ động để kiểm chứng semantics once-only, không dựa vào GC timing.

## 15. Chương trình hoàn chỉnh 6 — Cleaner explicit clean có kết quả xác định

Tệp **`CleanerExplicitDemo.java`**:

~~~java
import java.lang.ref.Cleaner;
import java.lang.ref.Reference;
import java.util.concurrent.atomic.AtomicInteger;

public class CleanerExplicitDemo {
    public static void main(String[] args) {
        Cleaner cleaner = Cleaner.create();

        Object referent = new Object();
        AtomicInteger cleanupCount = new AtomicInteger();

        Cleaner.Cleanable cleanable =
                cleaner.register(referent,
                        cleanupCount::incrementAndGet);

        System.out.println("Before clean = "
                + cleanupCount.get());

        cleanable.clean();
        cleanable.clean();

        System.out.println("After clean = "
                + cleanupCount.get());

        Reference.reachabilityFence(referent);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CleanerExplicitDemo.java
java CleanerExplicitDemo
~~~

**Stdout chính xác:**

~~~text
Before clean = 0
After clean = 1
~~~

### 15.1. Vì sao action không giữ referent?

Method reference `cleanupCount::incrementAndGet` chỉ giữ AtomicInteger, không capture referent. `Reference.reachabilityFence(referent)` ở cuối bảo đảm referent được xem còn strongly reachable tới mốc đó; auto cleanup không chạy sớm thay `clean()` trong minh họa này.

### 15.2. Vì sao gọi clean hai lần chỉ tăng một?

Một Cleaner registration được clean tối đa một lần. `clean()` lần hai không chạy action lại.

### 15.3. Điều demo không khẳng định

Không có lời gọi `System.gc()`, không đo background Cleaner thread, và không hứa JVM sẽ clean một unreachable referent trong một deadline nào. Đây là **minh họa API once-only và explicit cleanup**, không thay try-with-resources cho các file/socket thật.

### 15.4. Khi nào cần tránh Cleaner hẳn?

Nếu resource không đòi safety net native cleanup, hoặc framework đã cung cấp lifecycle manager đáng tin, thêm Cleaner có thể chỉ làm tăng độ phức tạp và overhead. Hãy dùng thiết kế đơn giản nhất đáp ứng ownership contract.

## 16. Strong, soft, weak và phantom references: ảnh hưởng reachability khác nhau

Java có các kiểu reference đặc biệt trong `java.lang.ref` để xây caches và công cụ quản lý lifecycle:

| Reference | Ý tưởng chính | Có nên dùng thay `close()`? |
| --- | --- | --- |
| Strong reference | Tham chiếu thông thường giữ object strongly reachable | Không, chỉ là ownership/reachability |
| `SoftReference<T>` | Có thể được GC clear theo memory-pressure policy | Không |
| `WeakReference<T>` | Không giữ referent mạnh; có thể được GC clear khi weakly reachable | Không |
| `PhantomReference<T>` | Theo dõi trạng thái reachability chuyên dụng qua ReferenceQueue; `get()` không trả referent | Không |
| `Cleaner.Cleanable` | Cleanup registration dựa trên phantom reachability/explicit clean | Fallback, không thay deterministic close |

### 16.1. WeakReference không phải “một strong reference nhẹ hơn”

Nếu chỉ còn weak references tới object (và không có references khác giữ nó strongly/softly reachable theo runtime rules), collector có thể clear weak references khi phát hiện trạng thái thích hợp. **Không có nghĩa weak.get() tự đổi null ngay sau System.gc() trên mọi JVM.**

### 16.2. SoftReference không là cache policy bảo đảm hiệu năng

Có thể dùng cho một số cache-related designs, nhưng soft-reference clearing phụ thuộc GC/memory policies, không thay một size-bounded cache với metrics/eviction rõ ràng. Không hứa rằng một cached value sẽ ở lại cho đến khi “heap gần hết” theo threshold cố định.

### 16.3. PhantomReference dùng với queue và reference processing

Phantom references thường được dùng khi triển khai cleanup/tracking chuyên sâu. `get()` không cung cấp referent để thao tác; phải xây code có state riêng. Đó không phải lựa chọn mặc định cho application-level resource ownership.

### 16.4. ReferenceQueue cũng không có deadline

Khi reference được enqueue phụ thuộc garbage collector/reference processing. Không viết logic correctness-critical “chờ queue nhận đúng trong 100 ms” chỉ vì đã gọi System.gc().

## 17. Chương trình hoàn chỉnh 7 — WeakReference và assert đúng điều có thể biết

Tệp **`WeakReferenceHintDemo.java`**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceHintDemo {
    static final class Data {
        final String text;

        Data(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        Data strong = new Data("Java");
        WeakReference<Data> weak =
                new WeakReference<>(strong);

        System.out.println("Before release = "
                + (weak.get() == strong));

        Reference.reachabilityFence(strong);
        strong = null;

        System.gc();

        System.out.println("After hint = unspecified");
        System.out.println("No deterministic null assertion");
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 WeakReferenceHintDemo.java
java WeakReferenceHintDemo
~~~

**Stdout chính xác:**

~~~text
Before release = true
After hint = unspecified
No deterministic null assertion
~~~

### 17.1. Vì sao “Before release” là true?

Biến strong vẫn giữ object, và weak reference trỏ tới cùng referent. `Reference.reachabilityFence(strong)` giúp bảo đảm strongly reachable đến điểm gọi, tránh ý định demonstration bị tối ưu liveness làm khó hiểu.

### 17.2. Vì sao không in `weak.get()==null` ở cuối?

Kết quả phụ thuộc thời điểm collector chạy và cách xử lý weak references. Một chương trình có thể in true hoặc false tại thời điểm đó; đưa một trong hai như stdout “chính xác” là một lời hứa không đúng.

### 17.3. Đừng dùng `System.gc()` để đồng bộ hóa weak cache

Một weak cache cần chấp nhận entries tự biến mất không theo deadline ứng dụng. Logic phải luôn xử lý cache miss bằng cách xây lại value, không phụ thuộc vào khi nào weak reference bị clear.

## 18. Vấn đề tài nguyên và bộ nhớ là hai trục độc lập

So sánh:

~~~text
Một object còn strongly reachable nhưng close() đã chạy
    → Java wrapper còn tồn tại, resource có thể đã đóng.

Một object unreachable nhưng chưa được garbage collected
    → Heap space có thể chưa thu hồi; resource có thể vẫn chưa đóng.

Một object được garbage collected
    → Heap memory liên quan có thể được tái sử dụng,
      nhưng không có quy tắc chung rằng external resource
      nhất định đã được đóng đúng hạn.

Một object bị giữ trong static cache mãi
    → GC không thể tự giải phóng object như một leak fix,
      vì chương trình vẫn giữ nó reachable.
~~~

### 18.1. Cặp câu hỏi đúng khi debug

- **Memory leak / heap pressure?** Ai đang giữ strong references? Heap dumps/dominators/retained size cho biết gì? Cache có bounds không?
- **Resource leak / connection exhaustion?** Owner có đóng resource trong mọi nhánh exception không? Pool trả connection đúng contract không? Listeners có được unsubscribe? Threads/executors có được shutdown?

Có thể xảy ra cả hai cùng lúc. Ví dụ giữ một Connection object trong static collection mà quên close vừa kéo dài object lifetime vừa giữ external resource.

### 18.2. System.gc không “đóng” được dead references trong collection

GC không thể chọn xóa entries mà List vẫn nắm giữ. Hãy xác định lifecycle của collection và chính sách remove/evict. Đây là root-cause fix hơn việc gọi explicit GC.

## 19. Chương trình hoàn chỉnh 8 — close làm mất strong reference tới buffer nội bộ

Một pattern hữu ích khi object còn có thể tồn tại sau khi đóng resource là làm rõ trạng thái closed và không giữ data lớn không còn cần thiết.

Tệp **`BufferLifecycleDemo.java`**:

~~~java
public class BufferLifecycleDemo {
    static final class BufferOwner implements AutoCloseable {
        private byte[] data;
        private boolean closed;

        BufferOwner(int size) {
            data = new byte[size];
        }

        int size() {
            if (closed) {
                throw new IllegalStateException("Buffer closed");
            }
            return data.length;
        }

        boolean isClosed() {
            return closed;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                data = null;
            }
        }
    }

    public static void main(String[] args) {
        BufferOwner owner = new BufferOwner(8);

        try (owner) {
            System.out.println("Inside size = " + owner.size());
        }

        owner.close(); // Idempotent theo implementation này.

        System.out.println("Closed = " + owner.isClosed());

        try {
            owner.size();
        } catch (IllegalStateException ex) {
            System.out.println("Use after close rejected");
        }

        System.out.println("Reclaimed bytes = not asserted");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BufferLifecycleDemo.java
java BufferLifecycleDemo
~~~

**Stdout chính xác:**

~~~text
Inside size = 8
Closed = true
Use after close rejected
Reclaimed bytes = not asserted
~~~

### 19.1. Vì sao explicit null ở đây có ý nghĩa?

`BufferOwner` vẫn được giữ bởi variable owner để kiểm tra isClosed sau scope. Nhưng sau close, việc gán `data = null` bỏ strong reference từ owner tới array cũ. Nếu không có aliases khác, array có thể trở nên GC-eligible sớm hơn so với owner.

### 19.2. Đây có phải cách mọi class đều nên dùng?

Không. Lạm dụng `field = null` ở khắp code làm giảm readability và thường không cần. Trong ví dụ này, close **có business meaning rõ**: object chuyển trạng thái closed, không được đọc buffer nữa, và có thể chủ động bỏ retention của buffer lớn. Trong ordinary short-lived locals, không cần null chỉ để “ép GC”.

### 19.3. Không thể kết luận 8 bytes đã trả về OS

`new byte[8]` có object header/alignment, JVM allocation rules và GC timing riêng. Setting field null không trả memory trực tiếp. Demo không in số reclaimed bytes vì điều đó không được bảo đảm.

## 20. Listener leak: tháo đăng ký thay vì gọi GC

Một kiểu retention leak thực tế là event bus giữ listeners sau khi screen/session lẽ ra đã kết thúc.

Sơ đồ:

~~~text
Long-lived EventBus (rooted by service)
    |
    v
List<Consumer<Event>>
    |
    v
listener lambda
    |
    v
captured Screen/Session/Controller
    |
    v
large model/view graph
~~~

Nếu screen đóng nhưng listener vẫn ở trong List, event bus có thể giữ screen và toàn bộ captured graph reachable. `System.gc()` không thể sửa logic đăng ký/dỡ đăng ký ấy.

### 20.1. Trả subscription handle implements AutoCloseable

Một API tốt có thể dùng:

~~~java
try (Subscription sub = bus.subscribe(listener)) {
    // Listener chỉ sống trong scope này.
}
~~~

Sau scope, `Subscription.close()` thực hiện unsubscribe. Một loại cleanup khác cần thiết kế bằng lifecycle hooks nếu subscription phải sống lâu hơn một lexical try block.

### 20.2. Listener registration có thể cần thread safety

Nếu bus nhận events trên nhiều threads, danh sách listeners và unsubscribe phải đồng bộ theo API. Ví dụ dưới đây là single-threaded để stdout deterministic và tập trung lifecycle; không coi nó là một event bus concurrent production-ready.

## 21. Chương trình hoàn chỉnh 9 — unsubscribe là lifecycle action xác định

Tệp **`ListenerLifecycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class ListenerLifecycleDemo {
    static final class EventBus {
        private final List<Consumer<String>> listeners =
                new ArrayList<>();

        Subscription subscribe(Consumer<String> listener) {
            listeners.add(listener);
            return new Subscription(this, listener);
        }

        void publish(String event) {
            for (Consumer<String> listener : listeners) {
                listener.accept(event);
            }
        }

        int listenerCount() {
            return listeners.size();
        }

        private void unsubscribe(Consumer<String> listener) {
            listeners.remove(listener);
        }
    }

    static final class Subscription implements AutoCloseable {
        private final EventBus bus;
        private final Consumer<String> listener;
        private boolean closed;

        Subscription(EventBus bus, Consumer<String> listener) {
            this.bus = bus;
            this.listener = listener;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                bus.unsubscribe(listener);
            }
        }
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();

        try (Subscription subscription =
                     bus.subscribe(e ->
                             System.out.println("received " + e))) {
            System.out.println("During = " + bus.listenerCount());
            bus.publish("hello");
        }

        System.out.println("After = " + bus.listenerCount());
        bus.publish("ignored");
        System.out.println("Publish after close finished");
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 ListenerLifecycleDemo.java
java ListenerLifecycleDemo
~~~

**Stdout chính xác:**

~~~text
During = 1
received hello
After = 0
Publish after close finished
~~~

### 21.1. Vì sao publish cuối không in "received ignored"?

Listener đã được remove bởi Subscription.close khi try-with-resources kết thúc. EventBus không còn callback để gọi.

### 21.2. Lợi ích hơn System.gc

Cleanup có observable contract: `listenerCount()==0` sau close. Bất kể GC chạy lúc nào, chương trình không còn nhận event ngoài lifetime. Đây là correctness của business behavior, không chỉ là tiết kiệm heap.

### 21.3. Subscriptions có thể vẫn được tham chiếu nhưng không còn đăng ký

Sau close, Subscription instance có thể còn trong local variable ở implementation khác, nhưng EventBus đã remove listener. Điều đó tách rõ **lifecycle của đăng ký** với **lifecycle của Java wrapper object**.

## 22. OutOfMemoryError: gọi System.gc có chữa được không?

`OutOfMemoryError` xảy ra khi JVM không đáp ứng được yêu cầu cấp phát trong những điều kiện nhất định. Không nên dựa vào:

~~~java
try {
    // Allocate indefinitely.
} catch (OutOfMemoryError error) {
    System.gc();
    // Continue as if fixed.
}
~~~

Đây là **anti-pattern**, không phải demo cần chạy. Khi một ứng dụng thiếu memory nghiêm trọng, việc phục hồi tùy trạng thái hệ thống và loại OOME; gọi explicit GC không giải quyết một graph còn bị giữ bởi leak hoặc capacity budget sai.

### 22.1. Tìm root cause, không chỉ triệu chứng

Có thể nguyên nhân là:

- **Bộ nhớ thực sự cần nhiều hơn cấu hình heap**.
- Retention leak: cache, listeners, queues, static maps giữ objects không còn hữu ích.
- Unbounded workload hoặc concurrency.
- Classloader/metaspace leak hoặc native memory/direct buffers, không nhất thiết do Java heap object count.
- Gần đủ memory nhưng allocation patterns/fragmentation/collector constraints phù hợp tình huống cụ thể.
- Các memory areas khác nhau: thông báo OOME và metrics cần được đọc đúng loại.

### 22.2. System.gc không thể làm collector xóa reachable objects

Nếu 1 triệu objects vẫn nằm trong static Map được chương trình sử dụng, explicit GC request không biến chúng thành unreachable. Root cause là retention policy/map lifecycle.

### 22.3. Khi production có OOME

Thường cần phối hợp heap dump/GC logs/JFR, code profiling, capacity planning và cấu hình collector/JVM phù hợp. Đừng viết logic ứng dụng bắt OOME rồi tiếp tục như không có vấn đề, đặc biệt đối với server state quan trọng.

## 23. Memory metrics: đừng kết luận từ một con số trước/sau System.gc

Java có APIs như:

~~~java
Runtime runtime = Runtime.getRuntime();
long total = runtime.totalMemory();
long free = runtime.freeMemory();
long max = runtime.maxMemory();
~~~

Đây là **fragment**. Chúng trả thông tin runtime heap vào thời điểm quan sát, không tự là một thước đo trực tiếp “toàn bộ object còn sống theo business logic”.

### 23.1. `totalMemory()`

Thông thường là memory heap hiện có sẵn cho JVM trong một nghĩa implementation-specific được API mô tả; không đồng nghĩa “heap bytes toàn bộ Java objects đã tạo từ lúc startup”.

### 23.2. `freeMemory()`

Free memory trong managed JVM heap tại thời điểm query; có thể biến động do allocations, collection, expansion/contraction và concurrent collector activity.

### 23.3. `maxMemory()`

Ước lượng giới hạn tối đa JVM cố dùng cho memory management theo configured runtime; không phải RAM vật lý chính xác mà tiến trình sẽ dùng.

### 23.4. `used = total - free` cũng chỉ là một snapshot

Có thể dùng để quan sát xu hướng trong benchmark có kiểm soát, nhưng không chứng minh object A đã collected. JVM/JIT/collector hoạt động concurrent có thể làm các giá trị biến động, và allocations ngầm có thể xuất hiện.

### 23.5. Không đưa stdout số memory bytes cứng

Một demo in `totalMemory()`, `freeMemory()` sẽ có kết quả khác trên máy, heap flags và thời điểm. Nếu trình bày, hãy ghi rõ **số đo phụ thuộc môi trường** thay vì bịa một giá trị cố định.

## 24. Chẩn đoán JVM bằng công cụ và logging phù hợp

Khi cần phân tích GC behavior:

- **GC unified logging** trên HotSpot JDK 17: ví dụ `-Xlog:gc*` để quan sát GC events/configurations theo mức phù hợp; output phụ thuộc JVM.
- **Java Flight Recorder (JFR)**: thu thập events và phân tích allocation/GC/pause profiles khi được bật/cho phép.
- **`jcmd`**: công cụ JDK cho các lệnh diagnostic phù hợp với process/JVM, ví dụ xem VM flags, thread/heap information; phải kiểm tra lệnh hỗ trợ trên phiên bản hiện tại.
- **Heap dump + dominator/retained-size analysis**: tìm những strong-reference paths giữ objects.
- **Application telemetry**: queue sizes, cache hit/eviction, number of open connections, active tasks, listener counts và request patterns.

Ví dụ khởi chạy một ứng dụng HotSpot đã biên dịch với GC logging:

~~~bash
java -Xlog:gc* MyApplication
~~~

**Đây chỉ là command minh họa**, không phải một program của bài, và không có stdout cố định; actual logs, tags, format, pauses và timing phụ thuộc runtime.

### 24.1. Đừng nhầm GC count với live object count

Số collection events không phải số objects được reclaim. Một collection có thể xử lý nhiều heap regions và work khác nhau. Dữ liệu từ `GarbageCollectorMXBean` cũng không tự nói object cụ thể đã bị thu hồi.

### 24.2. Heap dump chứa dữ liệu nhạy cảm

Heap dumps có thể chứa session tokens, identifiers, payloads và secrets. Thu thập, lưu trữ, chuyển giao và xóa theo chính sách bảo mật; đừng đính kèm heap dump thật vào tài liệu công khai.

### 24.3. Đo application workload trước khi tuning

Nếu ứng dụng hết database connections, GC log không thay việc xem pool usage và missing close. Nếu heap tăng, đo retained objects và cache sizes trước khi thêm System.gc. Tuning collector không sửa semantic leaks của resource owners.

## 25. Cấu hình JVM có thể ảnh hưởng explicit GC

Các JVM distributions và GC implementations có configuration knobs. Với một số HotSpot configurations, cờ như:

~~~bash
java -XX:+DisableExplicitGC MyApplication
~~~

có thể làm explicit `System.gc()`/`Runtime.gc()` requests không khởi động GC theo cách thông thường. Cờ này **không tắt automatic GC**, vì JVM vẫn cần garbage collection để đáp ứng allocation/memory management.

Một số HotSpot collectors/configurations còn có options điều chỉnh cách explicit GC được thực thi, ví dụ những cơ chế liên quan concurrent explicit collection. Những options không phải guarantees portable cho mọi Java VM.

### 25.1. Không code phụ thuộc vào flags

Application correctness không được thay đổi chỉ vì admin bật hoặc tắt explicit GC. Nếu resource correctness cần System.gc, design đã sai.

### 25.2. Explicit GC có thể tăng pauses

Trên một số collectors, explicit request có thể kích hoạt work đáng kể. Đặt System.gc trong request handlers, mỗi transaction hoặc tests có thể khiến throughput/latency tệ hơn.

### 25.3. Không có một câu lệnh cấu hình tối ưu cho mọi trường hợp

Heap sizes, garbage collector selection, application allocation rate, pause targets và CPU/memory budgets đều ảnh hưởng kết quả. Quyết định tuning phải dựa trên metrics của workload thực.

## 26. GC tuning khác sửa memory leak

Hãy phân loại:

| Triệu chứng | Câu hỏi cần trả lời | Hướng giải quyết |
| --- | --- | --- |
| Heap usage tăng dài hạn | Objects nào giữ retained size và vì sao? | Sửa strong refs, cache policy, queue bounds |
| Frequent GC/pause | Allocation rate, live set, collector/heap config? | Profile + tối ưu allocation và tuning |
| File descriptors tăng | Streams/sockets có đóng đúng mọi nhánh? | AutoCloseable/try-with-resources |
| Database pool hết connections | Borrowed connections có trả pool? | try-with-resources, timeout, ownership |
| Listener count chỉ tăng | Có unsubscribe khi kết thúc screen/session? | Subscription.close hoặc remove |
| ThreadLocal memory tăng | Threads sống lâu; values được remove chưa? | try/finally remove |
| Executor threads không dừng | Có shutdown/await lifecycle? | shutdown, awaitTermination, cancel tasks |
| Weak cache hit rate thấp | Weak references bị clear hay logic cache miss? | Chọn cache policy phù hợp |
| OOME với static map lớn | Reachability từ map có vượt business need? | Bound entries, eviction, ownership |
| Test mong weak.get null ngay | Đang giả định System.gc deterministic? | Test invariant logic, không test collection deadline |

Một số vấn đề có thể chồng lên nhau. Nhưng **System.gc() không phải giải pháp chung của bất kỳ hàng nào trong bảng**.

## 27. Unit tests: kiểm tra điều bảo đảm được

### 27.1. Không viết test như sau

~~~java
Object value = new Object();
WeakReference<Object> weak = new WeakReference<>(value);
value = null;
System.gc();
assert weak.get() == null;
~~~

Đây là **mã cố ý minh họa sai kỳ vọng**. Test phụ thuộc vào collector timing, JVM flags và runtime liveness. Nó có thể pass/fail không ổn định dù ứng dụng đúng.

### 27.2. Test close() được gọi đúng một lần

Thay vì mong GC dọn connection, dùng fake resource với counter/flag; chạy code qua try-with-resources và assert counter/flag. Đây là deterministic unit test về lifecycle contract.

### 27.3. Test unsubscribe

Khi đóng Subscription, assert listenerCount về 0; publish event tiếp theo không còn callback. Không cần gọi System.gc để xác nhận owner đã giải phóng registration.

### 27.4. Test retention policy

Với cache bounded, assert size không vượt capacity hoặc entries bị evict theo policy; đừng phụ thuộc weak-reference clear timing cho expected values nếu không cần.

### 27.5. Khi thật sự test GC-sensitive infrastructure

Những libraries triển khai Cleaner/weak cache có thể cần integration/stress tests với timeout, polling và acceptance criteria phù hợp, song kết quả phải được diễn giải cẩn trọng vì JVM không cam kết thu hồi mọi object trong deadline tùy chọn. Không biến một flaky GC test thành cơ chế correctness của business code.

## 28. Vòng đời trong API: ai sở hữu trách nhiệm đóng?

Một thiết kế resource rõ ràng thường đặt các câu hỏi:

1. **Ai tạo resource?**
2. **Ai sử dụng?** Có nhiều consumers chia sẻ không?
3. **Ai là owner phải close/shutdown/unsubscribe?**
4. **Scope nào đánh dấu “xong việc”?**
5. **Nếu exception xảy ra giữa chừng thì cleanup ở đâu?**
6. **Có idempotent close contract không?**
7. **Có alias nào vẫn dùng resource sau close?**
8. **Có cần pool/lease semantics, không phải physical close?**
9. **Cleanup có phải thread-safe không?**
10. **Phản hồi người dùng/thao tác shutdown có deadline rõ không?**

Đó là những câu hỏi GC không thể tự trả lời. JVM biết về reachability của Java objects, không biết business moment “transaction hoàn tất”, “tab UI đóng”, “request bị hủy” theo quy tắc domain.

### 28.1. “Who opens closes” chỉ là heuristic

Method tạo resource thường đóng nó trong scope đó, nhưng có khi factory trả resource cho caller; lúc ấy **ownership được chuyển rõ qua API contract**. Quan trọng là luôn có một owner chịu trách nhiệm, không phải bắt buộc cùng method tạo và đóng trong mọi kiến trúc.

### 28.2. Pooling semantics

`Connection.close()` trong JDBC connection pool thường có thể trả logical connection về pool thay vì đóng physical TCP connection ngay. Điều đó vẫn là lifecycle operation đúng contract. GC không biết khi nào phải return lease cho pool.

### 28.3. Asynchronous scopes

Với CompletableFuture, reactive streams hoặc callbacks, lexical try block có thể kết thúc trước công việc async. Khi đó owner có thể cần attach cleanup trong completion handler/structured scope, đảm bảo resource sống đủ lâu và được close đúng lúc. **Không dùng System.gc để đồng bộ hóa completion của async tasks.**

## 29. Các lỗi phổ biến khi học System.gc và vòng đời object

### 29.1. “System.gc() buộc JVM thu gom ngay”

**Sai.** Đây là hint/best-effort request, không guarantee timing hoặc một collection cụ thể.

### 29.2. “Sau System.gc(), mọi unreachable object đã bị xóa”

**Sai.** Không có cam kết exact per-object reclamation thời điểm trả về.

### 29.3. “GC sẽ đóng file khi object hết scope”

**Không phải contract resource ownership.** Dùng close và try-with-resources.

### 29.4. “Gọi obj=null là giải phóng bộ nhớ”

**Không trực tiếp.** Chỉ bỏ một reference. Object có thể còn aliases; reclaim do GC và JVM quyết định.

### 29.5. “Nếu hai objects tham chiếu vòng nhau thì bị leak”

**Không tự động.** Unreachable cycles có thể được garbage collected; vấn đề là còn đường reference từ roots hay không.

### 29.6. “Một static List bị đầy thì GC tự xóa items không cần thiết”

**Sai.** Entries vẫn strongly reachable qua List; phải có eviction/clear/remove logic.

### 29.7. “GC memory free tăng chắc chắn bằng lượng object X vừa bị xóa”

**Sai.** Heap metrics có nhiều yếu tố, allocation headers, collector policies và allocations khác; không thể suy exact object reclamation từ hai snapshots.

### 29.8. “System.gc luôn là full stop-the-world GC”

**Sai về guarantee.** JVM/collector/configuration quyết định behavior; có thể tốn pause nhưng không có một outcome portable duy nhất.

### 29.9. “Dùng Cleaner thì không cần close”

**Sai.** Cleaner là fallback, auto execution không có deadline cho correctness-critical cleanup.

### 29.10. “finalize là cách chuẩn để cleanup trong Java 17”

**Sai.** Finalization không đáng tin và bị coi là cơ chế lỗi thời. Dùng explicit lifecycle API.

### 29.11. “WeakReference.get sẽ null ngay sau System.gc”

**Sai.** Đừng viết test giả định thời điểm clear.

### 29.12. “SoftReference là bộ nhớ cache có TTL bảo đảm”

**Sai.** Clearing phụ thuộc runtime policies; không có một TTL business contract.

### 29.13. “close xong Java object bị thu hồi ngay”

**Sai.** Object wrapper có thể vẫn strongly reachable và được GC về sau.

### 29.14. “Thêm System.gc vào finally là cách cleanup”

**Sai.** Finally cần gọi close/remove/unsubscribe cụ thể, không đưa GC hint làm thay.

### 29.15. “GC càng thường xuyên thì app càng tiết kiệm RAM”

Không có bảo đảm. Frequent collections có thể gây overhead và ảnh hưởng throughput/latency; cần data measurements để kết luận.

### 29.16. “Chỉ cần nâng -Xmx là hết memory leak”

Không xử lý root cause nếu unbounded retention tiếp tục tăng. Nâng capacity có thể giúp workload thật nhưng leak sẽ xuất hiện trở lại.

### 29.17. “Dùng System.gc để xử lý OutOfMemoryError là đủ”

Không đáng tin. Phân tích loại OOME và retaining paths/capacity, tránh bắt OOME rồi coi app đã hồi phục.

### 29.18. “List.clear sẽ close từng AutoCloseable element”

Không. List.clear chỉ sửa collection references, không gọi resource-specific close.

### 29.19. “ThreadLocal key yếu nên values không thể bị giữ lâu”

Sai theo general assumption. Long-lived threads/ThreadLocal maps có lifecycle riêng; gọi remove đúng scope khi cần.

### 29.20. “Try-with-resources chỉ close khi chạy hết block bình thường”

Sai. Nó còn close khi block exits do exception; suppressed exceptions giữ thông tin close failure phù hợp.

## 30. Bài tập kiểm tra có đáp án

**Câu 1.** `System.gc()` trả về gì?

**Đáp án:** Return type `void`; không trả số bytes/objects reclaimed hoặc boolean “GC xong”.

**Câu 2.** System.gc có đồng nghĩa Runtime.getRuntime().gc không?

**Đáp án:** Về API effect, System.gc là cách yêu cầu tương đương Runtime.gc, đều là gợi ý nỗ lực GC.

**Câu 3.** Có chắc collector chạy full GC mỗi lần gọi không?

**Đáp án:** Không; còn phụ thuộc JVM, collector, flags và runtime policy.

**Câu 4.** Có chắc object bị thu hồi trước khi method trả về không?

**Đáp án:** Không có bảo đảm cụ thể với từng object.

**Câu 5.** Object vẫn trong static List có được GC xóa chỉ vì gọi System.gc không?

**Đáp án:** Không nếu nó còn strongly reachable qua List theo runtime semantics.

**Câu 6.** `object = null` có xóa object khỏi heap không?

**Đáp án:** Không trực tiếp; chỉ bỏ một reference, object có thể còn aliases.

**Câu 7.** Java GC có thể thu hồi object cycle không còn reachable không?

**Đáp án:** Có; circular references không tự là memory leak.

**Câu 8.** Một `InputStream` có nên chờ GC để đóng file không?

**Đáp án:** Không; dùng close/try-with-resources theo ownership.

**Câu 9.** Try-with-resources cần interface nào?

**Đáp án:** AutoCloseable hoặc subtype như Closeable.

**Câu 10.** Nhiều resources trong try-with-resources đóng theo thứ tự nào?

**Đáp án:** Đảo ngược thứ tự khai báo/khởi tạo resource variables.

**Câu 11.** Nếu cả body và close ném exception, cái nào là primary?

**Đáp án:** Body exception thường là primary; close exception được thêm vào suppressed exceptions theo rules.

**Câu 12.** Close resource có làm wrapper Java object unreachable ngay không?

**Đáp án:** Không nhất thiết; aliases/owner vẫn có thể giữ reference.

**Câu 13.** Cleaner có bảo đảm automatic cleanup ngay sau System.gc không?

**Đáp án:** Không; không có deadline.

**Câu 14.** Có thể gọi Cleanable.clean tường minh không?

**Đáp án:** Có; action cho một registration được clean tối đa một lần.

**Câu 15.** Cleanup action capture referent bằng `this` có vấn đề gì?

**Đáp án:** Có thể giữ referent strongly reachable, khiến automatic cleanup không chạy như mong đợi.

**Câu 16.** Có thể test `weak.get()==null` ngay sau GC hint như invariant không?

**Đáp án:** Không; clearing/timing không deterministic.

**Câu 17.** Có nên dùng finalize cho production cleanup mới không?

**Đáp án:** Không; finalization lỗi thời/không đáng tin.

**Câu 18.** Heap reclamation và native file handle close có cùng lifecycle không?

**Đáp án:** Không; chúng là trách nhiệm khác nhau.

**Câu 19.** Một leak do listener vẫn đăng ký nên sửa thế nào?

**Đáp án:** Unsubscribe/removeListener/Subscription.close đúng owner scope.

**Câu 20.** Một leak do unbounded cache nên sửa thế nào?

**Đáp án:** Giới hạn size, eviction, TTL, clear/remove và quan sát retaining references theo domain.

**Câu 21.** Có nên gọi System.gc sau mọi HTTP request không?

**Đáp án:** Thường không; không thay lifecycle management và có thể tăng overhead.

**Câu 22.** `-XX:+DisableExplicitGC` có phải tắt mọi automatic GC không?

**Đáp án:** Không; nó liên quan explicit requests theo HotSpot behavior, automatic GC vẫn hoạt động.

**Câu 23.** `Runtime.freeMemory()` có chính là số bytes object A vừa được reclaim không?

**Đáp án:** Không; đó là một runtime heap snapshot không gắn với object A.

**Câu 24.** Heap dump giúp tìm gì trong retention leak?

**Đáp án:** Retaining paths, dominant owners, large reachable graphs và số lượng objects, theo khả năng công cụ.

**Câu 25.** GC logging có output cố định giữa mọi JDK/collector không?

**Đáp án:** Không; flags, runtime events và log formats khác nhau.

**Câu 26.** ThreadLocal trong pool cần cleanup thế nào?

**Đáp án:** Thường `remove()` trong finally sau task scope nếu không muốn value sống sang task sau.

**Câu 27.** Có thể dùng try-with-resources với custom subscription không?

**Đáp án:** Có nếu Subscription implements AutoCloseable và close giải phóng registration.

**Câu 28.** Nếu một reference vẫn giữ object, System.gc có thể bắt JVM xem object là dead không?

**Đáp án:** Không theo strong reachability semantics hợp lệ.

**Câu 29.** Đo GC bằng System.nanoTime trước/sau System.gc là đủ để benchmark collector không?

**Đáp án:** Không; JVM flags, JIT, allocation profile, warm-up và concurrent events gây nhiễu. Dùng phương pháp profiling/benchmark phù hợp.

**Câu 30.** Phân biệt ý nghĩa của `close()` và `System.gc()` trong một câu?

**Đáp án:** Close thực hiện resource lifecycle operation theo API contract; System.gc chỉ gợi ý JVM nỗ lực reclaim unreachable heap objects khi thích hợp.

## 31. Bài tập thực hành

### Bài 1 — alias và reachability

Tạo một Node object, giữ hai references, gán một biến null. Giải thích vì sao object còn reachable qua biến kia. Sau đó xóa alias còn lại và phân biệt “eligible” với “collected”. Không dùng assert về GC timing.

### Bài 2 — sửa memory retention leak

Viết một static List lưu arrays, quan sát size tăng sau nhiều calls. Thêm bound/clear để duy trì size theo policy. Chứng minh `System.gc()` không tự giảm List.size.

### Bài 3 — xây AutoCloseable resource

Tạo FakeConnection với `opened/closed` counters, sử dụng try-with-resources trên hai connections, xác minh close thứ tự đảo ngược và số còn mở trở về 0.

### Bài 4 — exception safety

Tạo một AutoCloseable ném exception trong close và try body cũng ném exception. In primary cùng getSuppressed; giải thích vì sao cách này tốt hơn gọi close tùy tiện trong finally mà không bảo vệ primary exception.

### Bài 5 — Cleaner

Tạo Cleaner với cleanup action chỉ giữ state độc lập, không capture referent. Gọi Cleanable.clean hai lần và assert count=1; giải thích tại sao không chờ System.gc để làm một unit test deterministic.

### Bài 6 — weak reference

Tạo WeakReference đến một object, drop strong reference rồi gọi System.gc. In thông báo rằng `weak.get` có thể null hoặc non-null tại thời điểm check; **không assert một kết quả cố định**.

### Bài 7 — listener subscription

Xây EventBus với subscribe trả AutoCloseable subscription; kiểm tra listenerCount giảm khi close. So sánh với trường hợp quên close làm long-lived bus giữ callback.

### Bài 8 — phân tích GC một cách có phương pháp

Chạy một chương trình Java với GC logging của JDK và số liệu application-level như cache size/active connections. Phân biệt giữa một collector event và semantic cleanup. Không lấy số đo của một laptop làm guarantee cho mọi máy.

## 32. Checklist triển khai thực tế

1. Đã xác định tài nguyên nào do GC quản lý và tài nguyên nào cần explicit close chưa?
2. Nếu API tạo AutoCloseable, owner có rõ ràng không?
3. Có try-with-resources hoặc finally đúng cho mọi nhánh exceptions không?
4. Nhiều resources có đóng theo thứ tự hợp lý không?
5. Có xử lý suppressed exceptions khi debug close failures không?
6. Có dùng close idempotent ở những nơi contract thực sự cần không?
7. Có code dựa vào finalize không? Nếu có, cần thay thế.
8. Có dựa Cleaner vào deadline business không? Nếu có, cần thay thiết kế.
9. Cleaner action có vô tình giữ referent mạnh không?
10. Weak/soft refs có bị dùng như storage bảo đảm tồn tại không?
11. Có unit tests giả định System.gc làm weak.get null ngay không?
12. Có static maps/lists/registries giữ dữ liệu quá lâu không?
13. Cache có bounded size/TTL/eviction policy và metrics không?
14. Listeners có unsubscribe khi owner hết scope không?
15. ThreadLocal values có remove ở đúng scope không?
16. Executor pools có shutdown/await lifecycle rõ không?
17. Có object graph lớn bị giữ bởi callbacks/lambdas/queues không?
18. Có tránh gán null vô ích chỉ để “tăng tốc GC” ở local variables không?
19. Có lúc nào null field thể hiện state closed thực sự, hợp lý về contract không?
20. Có nhận diện aliases còn giữ object dù một reference đã null không?
21. Có phân biệt reachable, eligible và reclaimed không?
22. Có hiểu System.gc chỉ là hint, không phải memory deletion operation không?
23. Có tránh gọi System.gc trong request loops hoặc routine cleanup không?
24. Có xét JVM flags/collector implementation khi giải thích behavior không?
25. Có tránh đồng nhất used heap và OS resident set size không?
26. Có dựa vào real GC logs/JFR/heap dumps thay giả định khi production issue không?
27. Có đảm bảo heap dumps/logs được xử lý bảo mật không?
28. Có phân biệt memory leak với file/socket/connection resource leak không?
29. Có giải pháp correctness không phụ thuộc GC timing không?
30. Có tài liệu hóa ownership và resource lifecycle contract cho callers không?

## 33. Kết luận

**`System.gc()` là một lời gợi ý cho JVM nỗ lực thực hiện garbage collection; nó không phải cách xóa object theo lệnh, không cung cấp deadline và không thể biến object còn strongly reachable thành unreachable.** Cùng một chương trình có thể có nhiều kết quả GC timing hợp lệ tùy JVM, collector và configuration.

Một object chỉ có thể được thu hồi khi runtime nhận thấy nó không còn được dùng theo reachability semantics phù hợp. Xóa một local reference, xóa entry khỏi collection và thực sự chạy collector là những sự kiện khác nhau. Cycles không nhất thiết là leak, nhưng static caches, event listeners, ThreadLocal values hoặc long-lived queues có thể giữ references ngoài ý muốn.

**Quản lý vòng đời tài nguyên phải chủ động:** dùng `AutoCloseable`, `try-with-resources`, `close()`, `shutdown()`, `unsubscribe()`, `remove()` và ownership policy đúng thời điểm. Cleaner và specialized references có thể là công cụ hỗ trợ ở trường hợp nâng cao, không phải cam kết cleanup deterministic. Finalization không phải lựa chọn thiết kế mới đáng tin.

Khi ứng dụng tốn memory hoặc gặp OOME, đừng bắt đầu bằng việc “thêm System.gc”. Hãy tìm **ai đang giữ references, có cần giữ không, resource owner nào phải close, workload có vượt capacity không**, sau đó đo bằng profiling/GC logs/JFR/heap analysis thích hợp. Java GC giải quyết thu hồi bộ nhớ tự động; **lifecycle correctness vẫn là trách nhiệm của thiết kế ứng dụng**.
