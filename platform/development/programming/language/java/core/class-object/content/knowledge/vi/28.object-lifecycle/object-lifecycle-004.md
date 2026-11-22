# Thu gom rác tự động và thời điểm thu gom không được bảo đảm — Java 17+

## 1. Bức tranh tổng quan

Trong Java, lập trình viên thường tạo đối tượng bằng `new` mà không phải gọi `free` để tự giải phóng từng vùng bộ nhớ như trong một số ngôn ngữ quản lý bộ nhớ thủ công. **Garbage collector (GC)** của môi trường thực thi Java có thể thu hồi vùng nhớ heap của những đối tượng **không còn reachable theo quy tắc của JVM**, phục vụ các lần cấp phát tiếp theo.

Tuy nhiên, có một khác biệt rất quan trọng:

- **Không còn tham chiếu mạnh có thể truy cập được tới một đối tượng** không đồng nghĩa đối tượng **đã bị thu gom ngay lập tức**.
- Gán biến thành `null`, rời khỏi block/method hoặc gọi `System.gc()` **không phải lời hứa về thời điểm đối tượng bị thu gom**.
- JVM được phép tối ưu cách quản lý lifetime, allocation và garbage collection; chương trình đúng không được phụ thuộc vào một GC event xảy ra ở một thời gian xác định.
- GC thu hồi **bộ nhớ được quản lý trên heap**. Nó **không phải** cơ chế đáng tin để đóng file, socket, kết nối cơ sở dữ liệu hay release các tài nguyên bên ngoài JVM.

Một ví dụ về sai kỳ vọng là tạo đối tượng, gán reference thành null, rồi khẳng định “đối tượng đã bị GC”. Kết luận đó **không được Java bảo đảm**. Đối tượng có thể trở nên *eligible for collection*, nhưng quyết định thu gom phụ thuộc implementation, tình trạng bộ nhớ, collector, các references còn tồn tại và hành vi runtime.

**Thông điệp cốt lõi:** GC tự động quản lý khả năng thu hồi bộ nhớ; **thời điểm thực sự thu gom không phải một điều kiện đúng đắn mà ứng dụng được phép giả định**.

Bài thuộc **Java core – class-object**, nhóm **Vòng đời đối tượng**, đề mục **Thu gom rác tự động và thời điểm thu gom không được bảo đảm**. Các chương trình độc lập dùng **Java 17+**; mọi stdout trình bày đều **không phụ thuộc lịch chạy GC**. Các đoạn trình diễn kỹ thuật không có `main` được ghi rõ; không có ví dụ cố ý chờ finalizer hoặc ép JVM thu gom vào một thời điểm.

## 2. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt *allocation*, *reachability*, *eligibility for GC* và *actual reclamation*.
2. Giải thích vì sao object references quyết định khả năng tiếp cận qua đồ thị đối tượng.
3. Nhận biết đối tượng có thể còn reachable thông qua static fields, stack, thread, collections, listeners và reference chains.
4. Hiểu rằng một object graph có vòng tham chiếu vẫn có thể trở thành rác khi không còn đường reachable từ GC roots.
5. Phân biệt strong, soft, weak, phantom references ở mức chính xác, không suy luận thời điểm cleanup.
6. Hiểu giới hạn của `System.gc()` và `Runtime.gc()`.
7. Không sử dụng `finalize()` để quản lý tài nguyên.
8. Dùng `try-with-resources`/`AutoCloseable` để giải phóng tài nguyên đúng luồng điều khiển.
9. Biết vai trò và giới hạn của `Cleaner` và `ReferenceQueue`.
10. Nhận diện memory leaks kiểu Java khi object vẫn reachable ngoài ý muốn.
11. Phân tích vì sao `WeakHashMap` không phù hợp cho mọi cache và weak references không bảo đảm thu gom tức thời.
12. Phân biệt số liệu GC log/heap metrics với cam kết GC sẽ xảy ra.
13. Hiểu `Reference.reachabilityFence` khi làm việc với tài nguyên ngoài heap.
14. Kiểm thử các hành vi chương trình mà không dựa vào `Thread.sleep`, `System.gc` hoặc thời điểm finalization.

## 3. Vòng đời đối tượng và những điều có thể khẳng định

Một đối tượng có thể đi qua các giai đoạn khái niệm:

~~~text
Tạo object
    |
    v
Có thể truy cập qua references từ chương trình
    |
    v
Không còn reachable qua những đường strong reachability phù hợp
    |
    v
Có thể được GC xem xét thu hồi (tùy reference category)
    |
    v
Bộ nhớ được JVM thu hồi vào thời điểm KHÔNG ĐƯỢC BẢO ĐẢM
~~~

Sơ đồ giúp hình dung chứ **không phải một state machine mà Java API cung cấp thời gian chuyển trạng thái cho từng object**. GC có thể diễn ra nhiều lần trong khi một đối tượng vẫn sống, có nhiều collection phases, hoặc object có thể chưa từng cần một thao tác thu hồi riêng biệt có thể quan sát được do các tối ưu runtime.

Đừng nhầm:

- **Scope của biến**: nơi tên biến được dùng hợp lệ trong source.
- **Lifetime của reference**: khoảng chương trình có thể giữ reference đó theo phân tích của runtime.
- **Reachability của object**: object có thể được đi tới từ các roots theo các quy tắc tham chiếu.
- **Thời gian giữ memory**: JVM có thể không trả vùng heap đã thu hồi cho hệ điều hành ngay.
- **Tài nguyên ngoài heap**: file descriptors, native buffers, sockets có chính sách lifecycle khác.

Một biến hết scope giúp ta suy nghĩ về những đường tham chiếu còn lại, nhưng không cung cấp đồng hồ chính xác về việc thu gom.

## 4. Heap, stack và GC roots: mô hình vừa đủ

Trong mô hình khái niệm Java:

- **Heap** chứa các objects/arrays do runtime quản lý.
- **Stack frames** của những Java threads có local variables và operand stack; một số references ở đây có thể giữ objects reachable.
- **Static fields** có thể giữ references tới objects còn sống suốt một phần lớn lifetime của application.
- Những references liên quan **live threads**, runtime structures, JNI/native handles và các roots khác do JVM xác định cũng có thể tham gia phân tích reachability.

Không nên rút ra quy tắc “mọi biến local còn scope luôn giữ object sống tới dấu ngoặc đóng”. Optimizing JIT có thể xác định reference không còn cần dùng sớm hơn. Trong tình huống cần giữ object mạnh tới một mốc rõ để bảo vệ native resources, `Reference.reachabilityFence` cung cấp API chuyên dụng.

**GC roots** không phải một danh sách biến Java mà user code có thể duyệt đầy đủ qua public API. Công cụ heap dump/profiler có thể phân tích retaining paths, nhưng đây là việc quan sát implementation/runtime, không phải lý do cho code ứng dụng phụ thuộc timing của GC.

## 5. Chương trình hoàn chỉnh 1 — tạo đối tượng không hàm ý thời điểm GC

Tệp **`ObjectLifetimeDemo.java`**:

~~~java
final class Note {
    private final String text;

    Note(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}

public class ObjectLifetimeDemo {
    static void createAndUse() {
        Note note = new Note("Java");
        System.out.println("during=" + note.text());
    }

    public static void main(String[] args) {
        createAndUse();
        System.out.println("method returned");
        System.out.println("GC timing unknown");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ObjectLifetimeDemo.java
java ObjectLifetimeDemo
~~~

**Stdout chính xác:**

~~~text
during=Java
method returned
GC timing unknown
~~~

Khi `createAndUse` trả về, biến local `note` của invocation đó không còn được truy cập bởi caller. Tuy nhiên, **không có dòng stdout nào chứng minh GC đã chạy hoặc đối tượng Note đã được thu hồi**. Runtime có thể thu gom sau đó hoặc tối ưu việc cấp phát/quan sát lifetime.

Thử nghiệm đúng về hành vi ở đây là ba dòng output liên quan tới điều khiển chương trình, **không phải** một event GC.

## 6. Đối tượng trở thành ứng viên thu gom khi nào?

Ví dụ:

~~~java
Object value = new Object();
value = null;
~~~

Đây là snippet hợp lệ trong method. Sau phép gán, biến `value` không còn trỏ tới object ban đầu. Nhưng kết luận **“object không còn reachable ở mọi nơi”** chỉ đúng nếu **không còn đường mạnh nào khác** tới object ấy.

Nếu trước khi gán null ta có:

~~~java
Object value = new Object();
Object alias = value;
value = null;
System.out.println(alias != null);
~~~

Object vẫn có đường truy cập qua `alias`. Dòng in là `true`, và hành động gán null cho `value` **không phá** reference từ `alias`.

**Không dùng “reference count bằng 0” như một định nghĩa chính thức của Java GC**. Một số collector dùng tracing/đồ thị reachability; nhiều objects có vòng tham chiếu vẫn có thể bị thu gom nếu không reachable từ roots. Mỗi loại reference (weak/soft/phantom) cũng có quy tắc riêng.

## 7. Chương trình hoàn chỉnh 2 — alias giữ đối tượng còn truy cập được

Tệp **`StrongAliasDemo.java`**:

~~~java
public class StrongAliasDemo {
    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");
        StringBuilder alias = source;

        source = null;
        alias.append("B");

        System.out.println("alias=" + alias);
        System.out.println("source is null=" + (source == null));

        alias = null;
        System.out.println("no local alias kept");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StrongAliasDemo.java
java StrongAliasDemo
~~~

**Stdout:**

~~~text
alias=AB
source is null=true
no local alias kept
~~~

Dù `source = null`, cùng StringBuilder vẫn được truy cập qua `alias` và thay đổi nội dung thành AB. Lệnh `alias = null` ở cuối chỉ thay một biến; nó **không gọi GC** và không trả về một trạng thái “đã giải phóng bộ nhớ”.

## 8. Reachability là vấn đề của đồ thị tham chiếu

Một object có thể gián tiếp reachable qua chuỗi references:

~~~text
GC root
  |
  v
Application.staticCache
  |
  v
HashMap
  |
  v
Entry.value
  |
  v
List
  |
  v
LargePayload
~~~

Một method chỉ gán `payload = null` ở một biến local **không làm mất đường** từ `staticCache` qua Map/List tới LargePayload. Nếu static cache tiếp tục giữ object graph, GC nhìn thấy chúng **vẫn được dùng theo nghĩa reachability**, dù logic nghiệp vụ không còn cần payload.

Đây là nguyên nhân của nhiều **memory leaks trong ngôn ngữ có GC**: không phải object “không được GC nhận ra”, mà do chương trình **vẫn giữ references quá lâu**.

Khi phân tích bộ nhớ, đặt câu hỏi “**ai đang giữ object?**” thường hữu ích hơn hỏi “**vì sao GC không chịu chạy?**”.

## 9. Chương trình hoàn chỉnh 3 — collection giữ objects đến khi bỏ references

Tệp **`CollectionRetentionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CollectionRetentionDemo {
    public static void main(String[] args) {
        List<StringBuilder> retained = new ArrayList<>();

        StringBuilder payload = new StringBuilder("item");
        retained.add(payload);
        payload = null;

        System.out.println("entries=" + retained.size());
        System.out.println("value=" + retained.get(0));

        retained.clear();
        System.out.println("after clear=" + retained.size());
        System.out.println("GC event not asserted");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CollectionRetentionDemo.java
java CollectionRetentionDemo
~~~

**Stdout:**

~~~text
entries=1
value=item
after clear=0
GC event not asserted
~~~

List giữ một strong reference tới StringBuilder nên có thể đọc object kể cả sau khi biến `payload` được gán null. `clear()` loại bỏ phần tử khỏi List theo hợp đồng collection. Nếu không còn references khác, object có thể đủ điều kiện thu gom; **không được kết luận lúc `clear()` trả về rằng bộ nhớ object đã được GC thu hồi**.

## 10. Vòng tham chiếu không nhất thiết gây memory leak

Giả sử A giữ B và B giữ A:

~~~text
        +---------------+
        |               |
        v               |
        A -----------> B
        ^               |
        +---------------+
~~~

Nếu một GC root vẫn dẫn tới A hoặc B, cả phần liên quan của graph có thể reachable. Nhưng nếu **mọi đường từ GC roots tới hai objects đều mất**, chúng có thể được coi là unreachable dù vẫn giữ references lẫn nhau.

Một collector tracing không cần “reference count bằng 0 cho từng object” mới nhận ra một nhóm objects không còn reachable. Vì thế, câu “Java không thể thu gom hai objects trỏ lẫn nhau” là **sai**.

**Giới hạn:** khẳng định “có thể thu gom” khác với “đã thu gom trong một lần GC cụ thể”. Chương trình không có API chuẩn hứa object bị thu hồi ngay sau khi mất root.

## 11. Chương trình hoàn chỉnh 4 — đồ thị có chu kỳ

Tệp **`CyclicObjectsDemo.java`**:

~~~java
final class Node {
    final String name;
    Node next;

    Node(String name) {
        this.name = name;
    }
}

public class CyclicObjectsDemo {
    static void buildCycle() {
        Node first = new Node("first");
        Node second = new Node("second");

        first.next = second;
        second.next = first;

        System.out.println("cycle="
                + (first.next.next == first));
    }

    public static void main(String[] args) {
        buildCycle();
        System.out.println("buildCycle returned");
        System.out.println("collection not promised");
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 CyclicObjectsDemo.java
java CyclicObjectsDemo
~~~

**Stdout:**

~~~text
cycle=true
buildCycle returned
collection not promised
~~~

Cặp nodes có references lẫn nhau. Sau khi `buildCycle` trả về, ví dụ không giữ một reference ứng dụng lâu dài tới chúng, nhưng **không giả định GC chạy ngay**. Cây tham chiếu có chu kỳ là một tính chất của object graph, không phải bằng chứng memory leak.

## 12. `System.gc()`: lời đề nghị, không phải “thu gom ngay”

Java cung cấp:

~~~java
System.gc();
Runtime.getRuntime().gc();
~~~

Đây là các Java statements hợp lệ. Chúng có thể được dùng để **đề nghị** JVM nỗ lực thực hiện garbage collection. Theo API, `System.gc()` gợi ý JVM nỗ lực thu hồi objects không dùng để bộ nhớ hiện chiếm dụng sẵn sàng tái sử dụng. **Không có bảo đảm** rằng một object cụ thể sẽ được thu gom trước khi lời gọi trở về.

Một số cấu hình/runtime có thể hạn chế hoặc vô hiệu hóa cách xử lý explicit GC request. Dù JVM thực sự thực hiện GC, một object còn reachable vẫn không phải là “rác” chỉ vì caller muốn thu gom nó.

Không viết production code theo giả định:

- “Gọi `System.gc()` sẽ sửa memory leak.”
- “`System.gc()` luôn tạo một full GC.”
- “Sau `System.gc()`, `WeakReference.get()` chắc chắn trả null.”
- “Sau `System.gc()`, memory usage chắc chắn giảm.”
- “Sau `System.gc()`, native resources đều được đóng.”

Các khẳng định này hoặc **không được API bảo đảm**, hoặc bỏ qua nguyên nhân giữ references.

## 13. Chương trình hoàn chỉnh 5 — đề nghị GC nhưng không đoán kết quả

Tệp **`GcRequestDemo.java`**:

~~~java
public class GcRequestDemo {
    public static void main(String[] args) {
        byte[] payload = new byte[1_024];
        System.out.println("payload size=" + payload.length);

        payload = null;
        System.out.println("reference dropped");

        System.gc();
        System.out.println("GC request returned");
        System.out.println("no object collection asserted");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GcRequestDemo.java
java GcRequestDemo
~~~

**Stdout của chương trình, khi không bật GC logging:**

~~~text
payload size=1024
reference dropped
GC request returned
no object collection asserted
~~~

Dòng `GC request returned` chỉ chứng minh lời gọi `System.gc()` đã **trả về**; nó **không chứng minh** đối tượng byte array đã bị thu hồi, bao nhiêu bytes được giải phóng, hoặc có full GC.

Đo timing xung quanh lệnh `System.gc()` rồi suy ra lịch GC chung cũng không đáng tin: JVM warmup, JIT, collector selection, tải ứng dụng và bộ nhớ khiến measurements biến thiên.

## 14. Vì sao bộ nhớ heap có thể không giảm như mong đợi?

Cần tách ba đại lượng:

1. **Object liveness/reachability:** phần object graph còn được ứng dụng/runtime giữ.
2. **Used heap:** số liệu quan sát dung lượng đã sử dụng tại một thời điểm theo công cụ/API cụ thể.
3. **Committed heap/reserved address space:** vùng heap JVM đã cam kết/dành sẵn; không bắt buộc trả lại hệ điều hành ngay khi có objects được thu hồi.

Một GC có thể thu gom objects không dùng nhưng JVM vẫn **giữ committed heap** để cấp phát tiếp. Vì vậy Task Manager hoặc biểu đồ memory process có thể không giảm theo cách người học mong đợi.

Ngược lại, used heap trong một sampling có thể tăng vì những allocations hợp lệ khác, kể cả sau lời gọi GC. Không suy luận memory leak chỉ từ **một** lần quan sát.

Hãy đánh giá xu hướng sau nhiều cycles dưới workload đại diện, xem retaining paths và phân tích collector logs/heap dumps đúng công cụ; đừng xem `System.gc()` là phép thử boolean cho một object.

## 15. `Runtime` memory methods không đo “object đã được GC”

Các methods:

~~~java
Runtime runtime = Runtime.getRuntime();
long free = runtime.freeMemory();
long total = runtime.totalMemory();
long max = runtime.maxMemory();
~~~

Đây là snippet hợp lệ trong method. Chúng mô tả các số liệu bộ nhớ của JVM theo API, không cung cấp object lifetime cụ thể. Các giá trị biến đổi theo thời điểm, cấu hình heap và runtime implementation.

**Không nên in các số liệu ấy như “expected stdout cố định” trong tài liệu học:** JVM được chạy ở những máy/cờ heap khác nhau. Để làm test có đầu ra xác định, bạn có thể kiểm tra những tính chất chung như totalMemory lớn hơn 0, thay vì so một số byte cụ thể.

Nếu muốn hiểu GC, quan sát log hoặc metrics; nếu muốn **xác minh hành vi chương trình**, thiết kế test độc lập với GC timing.

## 16. Chương trình hoàn chỉnh 6 — lấy mẫu heap mà không cố định số byte

Tệp **`HeapSnapshotDemo.java`**:

~~~java
public class HeapSnapshotDemo {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();
        long total = runtime.totalMemory();
        long free = runtime.freeMemory();
        long max = runtime.maxMemory();

        System.out.println("total positive=" + (total > 0));
        System.out.println("free nonnegative=" + (free >= 0));
        System.out.println("max positive=" + (max > 0));

        byte[] bytes = new byte[256];
        System.out.println("array length=" + bytes.length);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 HeapSnapshotDemo.java
java HeapSnapshotDemo
~~~

**Stdout trên một JVM vận hành bình thường:**

~~~text
total positive=true
free nonnegative=true
max positive=true
array length=256
~~~

`maxMemory()` có thể mang giá trị rất lớn nếu JVM chưa có giới hạn xác định theo contract; không nên dựa vào số cụ thể. Demo chỉ in các kiểm tra cơ bản và độ dài array, **không giả vờ biết lần GC xảy ra lúc nào**.

## 17. Strong reference: trường hợp thông thường

Một biến kiểu `Object`, `StringBuilder`, `List<T>` hoặc một field thông thường có thể giữ **strong reference** tới object. Nếu một đường strong reachability từ GC root tới object còn tồn tại, object ấy không được xem là freely collectible chỉ vì một biến khác bị null.

~~~java
Object item = new Object();
java.util.List<Object> list = new java.util.ArrayList<>();
list.add(item);
item = null;
~~~

Đây là snippet hợp lệ trong method. List vẫn giữ reference tới object ban đầu.

**Strong reference không giống immutable:** một object được giữ mạnh vẫn có thể mutable. Cũng không đồng nghĩa là ứng dụng “thực sự cần” object. Một cache không có eviction policy có thể giữ những objects không còn giá trị nghiệp vụ nhưng vẫn reachable từ static field.

## 18. `WeakReference`: tham chiếu yếu không giữ object sống mạnh

`java.lang.ref.WeakReference<T>` được dùng khi caller muốn có khả năng quan sát object nếu nó **chưa được thu gom**, nhưng không muốn reference đó tự nó làm object phải được giữ sống như một strong reference.

~~~java
Object object = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(object);
~~~

Snippet này hợp lệ. Trong khi biến `object` vẫn giữ strong reference, `weak.get()` có thể trả object. Nếu sau này không còn strong/soft references phù hợp, JVM có thể nhận ra weak reachability và clear weak reference trong một collection phase; khi đó `weak.get()` trả null.

**Không khẳng định** “gán `object = null` làm `weak.get()` trả null ngay”. Reference có thể chưa được clear tại thời điểm đọc, và các runtime optimizations khiến lịch sống của objects không nên được suy ra chỉ từ source-level assignments.

`WeakReference` thích hợp cho metadata liên kết tạm, canonicalizing structures hoặc một số quan hệ cache có semantics rõ. Nó không tự định nghĩa retention policy có ích cho mọi cache.

## 19. Chương trình hoàn chỉnh 7 — `WeakReference.clear()` có kết quả xác định

Tệp **`WeakReferenceDemo.java`**:

~~~java
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak =
                new WeakReference<>(strong);

        System.out.println("same=" + (weak.get() == strong));

        weak.clear();
        System.out.println("cleared=" + (weak.get() == null));
        System.out.println("strong remains="
                + (strong != null));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 WeakReferenceDemo.java
java WeakReferenceDemo
~~~

**Stdout:**

~~~text
same=true
cleared=true
strong remains=true
~~~

Demo gọi **`weak.clear()` tường minh**, nên `weak.get()` trả null là kết quả do chương trình điều khiển, **không phải một bằng chứng rằng GC đã chạy**. Biến strong vẫn trỏ tới object, và object có thể tiếp tục được dùng bình thường.

Nếu bạn thay `clear()` bằng `System.gc()`, stdout `cleared=true` **không còn được bảo đảm**. Đó là lý do ví dụ dạy GC không nên tự tạo một “bài test” dựa vào việc weak ref chắc chắn biến mất ngay.

## 20. `SoftReference`: đừng dựa vào lịch dọn cache

`SoftReference<T>` có quy tắc lifetime khác WeakReference: JVM có thể giữ object softly reachable lâu hơn và clear soft references theo chính sách liên quan memory demand. Java API đưa ra semantics nhằm hỗ trợ cache nhạy với bộ nhớ, nhưng **không cho ứng dụng kiểm soát chính xác khi nào một soft reference bị clear**.

Do đó:

- Không giả định object được SoftReference giữ tồn tại mãi tới một ngưỡng MB cụ thể.
- Không giả định một `System.gc()` luôn clear mọi soft refs.
- Không dùng SoftReference thay thế một **cache có size limit/TTL/eviction policy** khi performance hoặc giới hạn bộ nhớ phải được dự đoán.
- `get()` có thể trả null, nên caller cần đường tái tạo dữ liệu.
- Không dùng soft refs làm cơ chế release file/socket đúng hạn.

Khi cần caching trong application thực tế, hãy ưu tiên một contract cache rõ: maximum entries/weight, expiration, invalidation, metrics và ownership. Soft reference chỉ là một công cụ đặc biệt.

## 21. Chương trình hoàn chỉnh 8 — soft reference và explicit clear

Tệp **`SoftReferenceDemo.java`**:

~~~java
import java.lang.ref.SoftReference;

public class SoftReferenceDemo {
    public static void main(String[] args) {
        StringBuilder strong = new StringBuilder("cached");
        SoftReference<StringBuilder> soft =
                new SoftReference<>(strong);

        System.out.println("initial=" + soft.get());
        soft.clear();
        System.out.println("after clear=" + soft.get());
        System.out.println("original=" + strong);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SoftReferenceDemo.java
java SoftReferenceDemo
~~~

**Stdout:**

~~~text
initial=cached
after clear=null
original=cached
~~~

`soft.clear()` được gọi tường minh nên kết quả xác định. Demo **không mô phỏng memory pressure hoặc GC selection**. Strong reference giữ StringBuilder ở phía chương trình; xóa soft reference không phá object.

## 22. `PhantomReference`: theo dõi trạng thái hậu-reachability, không truy xuất object

`PhantomReference<T>` đặc biệt hơn: `get()` của một PhantomReference **luôn trả null**. Nó không cung cấp một lối đọc object như WeakReference.

Thông thường PhantomReference được dùng kết hợp `ReferenceQueue` để quan sát một mốc xử lý liên quan đến reachability và cleanup management. Nhưng:

- Nó **không** cho biết một thời điểm chắc chắn object được thu gom.
- Việc queue notification phụ thuộc vào GC và cơ chế xử lý references.
- Nó **không** giải phóng external resource theo thời hạn ứng dụng mong muốn.
- Không thể `get()` object rồi “hồi sinh” qua PhantomReference.
- Dùng `Cleaner` thường dễ hơn quản lý phantom refs trực tiếp nếu mục tiêu là backup cleanup của một state holder.

Với Java 17, không nên thiết kế logic quan trọng theo giả định một phantom ref được enqueued trước khi tiến trình kết thúc.

## 23. Chương trình hoàn chỉnh 9 — `PhantomReference.get()` luôn null

Tệp **`PhantomReferenceDemo.java`**:

~~~java
import java.lang.ref.PhantomReference;
import java.lang.ref.ReferenceQueue;

public class PhantomReferenceDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        PhantomReference<Object> phantom =
                new PhantomReference<>(strong, queue);

        System.out.println("phantom get null="
                + (phantom.get() == null));
        System.out.println("strong exists=" + (strong != null));
        System.out.println("no queue timing assumed");
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 PhantomReferenceDemo.java
java PhantomReferenceDemo
~~~

**Stdout:**

~~~text
phantom get null=true
strong exists=true
no queue timing assumed
~~~

`get()` luôn null theo contract của PhantomReference, **ngay cả khi một strong reference còn giữ object**. Do đó null từ `phantom.get()` không chứng minh object đã được GC xử lý.

## 24. `ReferenceQueue`: thông báo không phải lời hứa thời gian

Một `ReferenceQueue<T>` có thể nhận reference objects sau khi một reference bị clear/processed theo quy tắc tương ứng và đã được đăng ký với queue. Các methods như `poll()` hoặc `remove()` cho phép lấy những references đang được enqueued.

Nhưng khi không có một GC event xác định, bạn không nên viết:

~~~java
// Đoạn suy luận CỐ Ý SAI, không dùng để kiểm thử:
// weakTarget = null;
// System.gc();
// assert queue.poll() != null;
~~~

Đó là **mã minh họa sai kỳ vọng**, không phải chương trình đảm bảo pass.

Khi kiểm thử logic xử lý hàng đợi, có thể **enqueue reference một cách tường minh** bằng `Reference.enqueue()` nếu hợp đồng test cho phép, thay vì chờ GC. Như vậy bạn kiểm tra được **phần mềm xử lý queue**, không nhầm với việc đo collector.

`ReferenceQueue.remove(timeout)` có thể block tới timeout và chịu thread scheduling; tránh dùng kết quả thời gian cụ thể của nó làm test expected stdout.

## 25. Chương trình hoàn chỉnh 10 — enqueue chủ động để test queue

Tệp **`ReferenceQueueDemo.java`**:

~~~java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public class ReferenceQueueDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        WeakReference<Object> weak =
                new WeakReference<>(strong, queue);

        boolean enqueued = weak.enqueue();
        Object received = queue.poll();

        System.out.println("manual enqueue=" + enqueued);
        System.out.println("same reference=" + (received == weak));
        System.out.println("strong exists=" + (strong != null));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ReferenceQueueDemo.java
java ReferenceQueueDemo
~~~

**Stdout:**

~~~text
manual enqueue=true
same reference=true
strong exists=true
~~~

Reference object được **enqueue bằng lời gọi tường minh**; strong referent vẫn tồn tại, nên không có diễn giải “GC vừa chạy” nào. Việc gọi `poll` chứng minh queue đã nhận chính WeakReference object.

`ReferenceQueue` chỉ cung cấp thông tin liên quan tới registered reference objects; nó không phải một callback cơ bản luôn chạy đúng lúc object mất scope.

## 26. `WeakHashMap` và ownership: dùng cẩn thận

`WeakHashMap<K,V>` có những **keys được giữ bằng weak references**. Nó hữu ích khi metadata nên ngừng được giữ một cách mạnh chỉ bởi Map, sau khi không còn đường strong reference thích hợp tới key.

Tuy nhiên:

- Key entries không biến mất ngay khi code gán local key thành null.
- Việc loại bỏ entries phụ thuộc GC, reference queue processing và những thao tác của Map.
- Values được giữ mạnh thông thường; nếu value **tham chiếu ngược tới key** qua graph mạnh, key có thể vẫn reachable và entry không biến mất theo kỳ vọng.
- WeakHashMap không bảo đảm thread safety hoặc eviction schedule.
- Weak keys không phù hợp với mọi cache, đặc biệt cache cần predictable TTL/capacity và stable keys.

Không test rằng `size()` sẽ bằng 0 sau một `System.gc()` rồi coi kết quả thất thường là bug của WeakHashMap. Dùng explicit `remove`/`clear` khi cần dọn mapping ngay.

## 27. Chương trình hoàn chỉnh 11 — xóa WeakHashMap đúng hạn bằng API Map

Tệp **`WeakMapDemo.java`**:

~~~java
import java.util.Map;
import java.util.WeakHashMap;

public class WeakMapDemo {
    public static void main(String[] args) {
        Map<Object, String> metadata = new WeakHashMap<>();
        Object key = new Object();

        metadata.put(key, "tag");
        System.out.println("lookup=" + metadata.get(key));
        System.out.println("entries=" + metadata.size());

        metadata.remove(key);
        System.out.println("after remove=" + metadata.size());
        System.out.println("no GC assumption");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 WeakMapDemo.java
java WeakMapDemo
~~~

**Stdout:**

~~~text
lookup=tag
entries=1
after remove=0
no GC assumption
~~~

Object key vẫn được giữ mạnh trong method trong lúc lookup/remove nên kết quả không dựa vào collector. Dọn entry đúng thời điểm được thực hiện bằng `Map.remove`, không chờ weak-key processing.

## 28. GC không phải resource ownership: phải đóng theo công việc

GC quản lý việc thu hồi bộ nhớ của Java objects **khi chúng không còn reachable**, không biết chính xác khi nào file, socket, native handle hoặc database connection đã hoàn thành công việc theo nghĩa nghiệp vụ. Một Java object có thể vẫn reachable nhưng resource đã phải được đóng; cũng có thể object trở nên unreachable mà việc đóng resource bị trì hoãn.

**Hai mốc độc lập:**

- *Reachability*: còn đường tham chiếu từ GC roots hay không?
- *Resource lifetime*: chủ sở hữu đã sử dụng xong tài nguyên và phải gọi `close()` hoặc thao tác shutdown tương ứng chưa?

Với resource implement `AutoCloseable`, `try-with-resources` diễn đạt mốc đóng theo control flow, không đợi collector. Ví dụ ngay sau cho một bằng chứng xác định qua stdout; không dùng `System.gc()` để “kiểm tra” việc đóng.

## 29. Chương trình hoàn chỉnh 12 — `AutoCloseable` đóng đúng lúc

Tệp **`TryWithResourcesDemo.java`**:

~~~java
final class DemoResource implements AutoCloseable {
    DemoResource() {
        System.out.println("opened");
    }

    void use() {
        System.out.println("used");
    }

    @Override
    public void close() {
        System.out.println("closed");
    }
}

public class TryWithResourcesDemo {
    public static void main(String[] args) {
        try (DemoResource resource = new DemoResource()) {
            resource.use();
        }

        System.out.println("after try");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 TryWithResourcesDemo.java
java TryWithResourcesDemo
~~~

**Stdout:**

~~~text
opened
used
closed
after try
~~~

`close()` được gọi khi rời khỏi try-with-resources theo cú pháp Java; không cần có GC. Nếu body ném exception, try-with-resources vẫn cố đóng resource theo quy tắc của ngôn ngữ.

Khác với finalizer hay Cleaner, đây là cách **điều khiển lifecycle đúng thời điểm** trong ứng dụng.

## 30. Đóng nhiều resources không phụ thuộc GC scheduling

Trong một `try` khai báo nhiều resources, các expressions khởi tạo được đánh giá theo thứ tự từ trái sang phải; những resources tạo thành công được đóng **theo thứ tự ngược** khi rời phạm vi. Điều này là luật control flow của Java, không phải thứ tự collector xét object graph.

Nếu khởi tạo resource thứ hai thất bại, resource thứ nhất đã khởi tạo thành công vẫn được đóng. Nếu phần thân và các lần đóng cùng gây lỗi, Java còn có quy tắc primary/suppressed exceptions. Bài chuyên **Đóng tài nguyên bằng AutoCloseable và try-with-resources** giải thích toàn bộ các trường hợp này cùng ownership; trong bài về GC, chỉ cần nhớ: **đóng resource không phải sự kiện GC**.

Ví dụ hoàn chỉnh tiếp theo in rõ thứ tự `open A → open B → body → close B → close A`, hoàn toàn không yêu cầu bộ gom rác chạy.

## 31. Chương trình hoàn chỉnh 13 — thứ tự đóng resources

Tệp **`CloseOrderDemo.java`**:

~~~java
final class Resource implements AutoCloseable {
    private final String name;

    Resource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}

public class CloseOrderDemo {
    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("body");
        }
        System.out.println("done");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CloseOrderDemo.java
java CloseOrderDemo
~~~

**Stdout:**

~~~text
open A
open B
body
close B
close A
done
~~~

Resources đóng theo LIFO, ngay khi thoát try block bình thường. Dù một GC collector không chạy trong suốt chương trình, hành vi `close` vẫn xảy ra theo contract.

## 32. Suppressed exceptions chứng minh cleanup thuộc control flow

Khi thân `try-with-resources` ném exception và `close()` cũng ném exception, lỗi từ thân `try` là *primary exception*, còn lỗi phát sinh khi đóng được lưu qua `getSuppressed()`. Cơ chế này giúp giữ thông tin lỗi công việc chính đồng thời biết rằng cleanup cũng thất bại.

Điểm khác biệt với GC: đây là hành vi của **stack unwinding và resource close**, có thể kiểm thử xác định trên cùng input. Nó không yêu cầu object trở thành unreachable, không gửi yêu cầu tới GC và không phụ thuộc vào việc collector có chạy hay không.

Bài chuyên AutoCloseable/TWR đi sâu tình huống đóng nhiều tài nguyên, lỗi khởi tạo và ownership. Chương trình sau chỉ xác nhận chính xác **1 primary, 1 suppressed** mà không dựa vào timing GC.

## 33. Chương trình hoàn chỉnh 14 — suppressed exceptions

Tệp **`SuppressedExceptionsDemo.java`**:

~~~java
import java.io.IOException;

final class FailingResource implements AutoCloseable {
    @Override
    public void close() throws IOException {
        throw new IOException("close");
    }
}

public class SuppressedExceptionsDemo {
    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("body");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressed="
                    + ex.getSuppressed().length);
            System.out.println("suppressed message="
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SuppressedExceptionsDemo.java
java SuppressedExceptionsDemo
~~~

**Stdout:**

~~~text
primary=body
suppressed=1
suppressed message=close
~~~

Body ném IOException("body"), sau đó automatic close ném IOException("close"); exception lúc đóng được gắn vào suppressed exceptions của exception chính. Hành vi hoàn toàn xác định bởi `try-with-resources`, không chờ GC và không liên quan tới object eligibility.

## 34. Vì sao `finalize()` không phải lifecycle hook đáng tin?

Historically, Java cho phép một class override `Object.finalize()` để chạy logic liên quan object reclamation. Tuy nhiên, finalization **đã bị deprecated từ lâu** và không phù hợp để giải phóng tài nguyên.

Các vấn đề:

- Không có bảo đảm `finalize()` sẽ được gọi trong lifetime của process.
- Không có bảo đảm thời điểm finalizer chạy sau khi object không còn cần thiết.
- Thứ tự finalization giữa các objects không cung cấp resource dependency order bạn nên dựa vào.
- Finalization có thể gây latency, vấn đề an toàn và logic phức tạp.
- Finalizer code có thể làm object reachable trở lại (resurrection), gây khó khăn cho lifecycle reasoning.
- JVM process có thể kết thúc khi còn finalizable objects chưa được xử lý.

**Không viết bài kiểm thử dùng `Thread.sleep(...)` rồi kỳ vọng finalizer in một dòng cụ thể.** Không dùng finalizer để đóng connection/file hoặc hoàn tất transaction.

Một class Java có `final` **không liên quan** tới finalization: `final` ngăn kế thừa/gán lại, còn `finalize()` là legacy cleanup mechanism.

## 35. `Cleaner`: giải pháp dự phòng, không phải đóng đúng thời điểm

Java cung cấp `java.lang.ref.Cleaner` để đăng ký một cleanup action gắn với reachability của object. Đây là phương án có cấu trúc tốt hơn finalizers trong một số thư viện quản lý native state, nhưng **thời điểm automatic cleanup vẫn không được bảo đảm**.

Các nguyên tắc:

1. Cleanup action nên giữ **state cần dọn**, không giữ mạnh object đang được theo dõi (*referent*).
2. Nếu action capture referent, nó có thể vô tình giữ referent reachable, khiến cleanup tự động không được kích hoạt như mong muốn.
3. Cleanup action phải an toàn khi chỉ chạy một lần; `Cleanable.clean()` cho phép **gọi rõ ràng**.
4. Không xem việc đăng ký Cleaner là thay thế cho `close()` của resource có lifetime xác định.
5. Không được trông chờ cleanup actions chạy trước khi process chết hoặc trong một thời gian cố định.
6. Cleaner phù hợp làm **backup safety net**, không phải transaction commit/final flush mechanism.

Mục tiêu của ví dụ sau là minh họa gọi `clean()` **tường minh**, để stdout không bị ràng buộc vào GC.

## 36. Chương trình hoàn chỉnh 15 — gọi `Cleaner.Cleanable.clean()` trực tiếp

Tệp **`CleanerDemo.java`**:

~~~java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicInteger;

public class CleanerDemo {
    public static void main(String[] args) {
        Cleaner cleaner = Cleaner.create();
        AtomicInteger actions = new AtomicInteger();

        Object owner = new Object();
        Cleaner.Cleanable cleanable =
                cleaner.register(owner, actions::incrementAndGet);

        cleanable.clean();
        cleanable.clean();

        System.out.println("cleanup calls=" + actions.get());
        System.out.println("owner still exists=" + (owner != null));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CleanerDemo.java
java CleanerDemo
~~~

**Stdout:**

~~~text
cleanup calls=1
owner still exists=true
~~~

Method `Cleanable.clean()` làm action chạy đồng bộ khi được gọi tường minh; gọi lại không thực hiện cleanup lần thứ hai theo contract. Action chỉ capture AtomicInteger chứ không capture object owner.

**Không kết luận** dòng `cleanup calls=1` là bằng chứng GC chạy: hành vi đến từ hai lời gọi `clean()` trong main. Nếu chỉ đăng ký rồi bỏ owner, số lần/timing action tự động không phải điều chương trình có thể đưa vào expected stdout cố định.

## 37. `Reference.reachabilityFence`: giữ object sống đến mốc cần thiết

Trong mã tương tác native resource, một object wrapper có thể cần vẫn strongly reachable trong khi native operation sử dụng handle mà wrapper sở hữu. Optimizing JVM đôi khi có thể nhận định object không còn cần thiết theo những uses thông thường sớm hơn người đọc source tưởng tượng.

`java.lang.ref.Reference.reachabilityFence(reference)` được cung cấp để bảo đảm referent vẫn **strongly reachable ít nhất cho tới điểm invocation** theo semantics API. Ví dụ đặt nó ở cuối `finally` block sau một native operation.

~~~java
try {
    useNativeHandle(handle);
} finally {
    java.lang.ref.Reference.reachabilityFence(owner);
}
~~~

Đây là **snippet minh họa**, yêu cầu các biến owner/handle và method useNativeHandle được định nghĩa ở phạm vi phù hợp. `reachabilityFence` **không gọi GC**, không đóng resource và không kéo dài object lifetime mãi mãi.

**Chỉ dùng khi lý do reachability thật sự liên quan native/foreign resource lifecycle.** Trong code Java thuần dùng object references bình thường, bạn hiếm khi cần gọi method này.

## 38. Chương trình hoàn chỉnh 16 — dùng reachability fence đúng ý nghĩa

Tệp **`ReachabilityFenceDemo.java`**:

~~~java
import java.lang.ref.Reference;

final class HandleOwner {
    private final int handle;

    HandleOwner(int handle) {
        this.handle = handle;
    }

    int handle() {
        return handle;
    }
}

public class ReachabilityFenceDemo {
    static void useHandle(int handle) {
        System.out.println("using=" + handle);
    }

    public static void main(String[] args) {
        HandleOwner owner = new HandleOwner(7);
        int nativeHandle = owner.handle();

        try {
            useHandle(nativeHandle);
        } finally {
            Reference.reachabilityFence(owner);
        }

        System.out.println("operation complete");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ReachabilityFenceDemo.java
java ReachabilityFenceDemo
~~~

**Stdout:**

~~~text
using=7
operation complete
~~~

Code này dùng một int mô phỏng handle nên không quản lý native resource thật. Điểm cần hiểu là invocation `reachabilityFence(owner)` ở cuối `finally` giữ referent sống ít nhất tới ranh giới đó; nó **không biến `System.gc` thành một phép đo thời điểm thu gom**.

## 39. Vì sao GC không tự giải quyết memory leaks?

Một object mà chương trình vô tình tiếp tục giữ reference vẫn reachable; collector không thể biết rằng **nghiệp vụ** muốn loại bỏ nó.

Những ví dụ phổ biến:

- `static List` hoặc `static Map` tăng mãi, không có giới hạn hoặc eviction.
- Cache chỉ bổ sung items mà không có TTL/capacity policy.
- Listener/subscriber được đăng ký nhưng quên unregister.
- ThreadLocal values không được remove theo vòng đời request/thread pool khi cần.
- Task queues tích lũy jobs mà consumer xử lý chậm hơn producer.
- Một object parent dài hạn giữ reference tới toàn bộ graph của request cũ.
- Thread hoặc executor không được shutdown đúng cách và giữ task contexts.

Những trường hợp này đều là **retention problems**: collector làm đúng khi giữ objects vẫn reachable.

Cách giải quyết là **thay đổi ownership/references**: giới hạn cache, remove entries, unregister listeners, close resources, clear ThreadLocals phù hợp, shutdown executors và tránh giữ contexts quá lâu.

## 40. Chương trình hoàn chỉnh 17 — static cache phải có eviction/clear

Tệp **`RetainedCacheDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RetainedCacheDemo {
    private static final List<byte[]> CACHE = new ArrayList<>();

    static void add() {
        CACHE.add(new byte[256]);
    }

    public static void main(String[] args) {
        add();
        add();

        System.out.println("entries=" + CACHE.size());
        System.out.println("bytes per entry="
                + CACHE.get(0).length);

        CACHE.clear();
        System.out.println("after clear=" + CACHE.size());
        System.out.println("collection time unknown");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 RetainedCacheDemo.java
java RetainedCacheDemo
~~~

**Stdout:**

~~~text
entries=2
bytes per entry=256
after clear=0
collection time unknown
~~~

Static List giữ references tới hai byte arrays. `CACHE.clear()` bỏ các elements khỏi collection, nhưng không hứa process memory giảm ngay. Trong ứng dụng thật, cache có thể cần giới hạn dung lượng và eviction rõ thay vì chỉ dọn vào cuối chương trình.

## 41. GC và các kiểu `OutOfMemoryError`

GC **không hứa rằng mọi allocation đều thành công**. JVM có thể ném `OutOfMemoryError` khi không thể cấp phát thêm bộ nhớ đủ cho nhu cầu, kể cả có GC tự động.

Nhưng:
- Không phải mọi OutOfMemoryError đều là “Java heap space”: có thể có vấn đề ở native memory, metaspace, direct buffers, thread creation hoặc cấu hình tài nguyên khác.
- Không nên gọi `System.gc()` như chiến lược duy nhất xử lý lỗi OutOfMemoryError.
- Không thực hiện demo cố cấp phát vô hạn chỉ để “chứng minh GC sẽ chạy” trên máy học, vì có thể khiến JVM hoặc hệ thống thiếu tài nguyên.
- Một lần allocation thành công không chứng minh không có retention leak.
- Giới hạn heap bằng `-Xmx` dùng cho thử nghiệm cần được chọn thận trọng theo workload, không phải một số được bài học áp đặt cho mọi máy.

Khi có OOME, hãy phân tích error type/message, GC logs, heap dumps, memory pools và retaining roots phù hợp.

**Ranh giới quan trọng:** GC giải quyết việc thu hồi bộ nhớ **không còn reachable**, chứ không thể cứu một application giữ sống quá nhiều objects.

## 42. GC logs và công cụ quan sát trong Java 17

JDK 17 HotSpot hỗ trợ **Unified JVM Logging**. Bạn có thể chạy một chương trình với cờ:

~~~bash
java -Xlog:gc GcRequestDemo
~~~

Đây là một **lệnh CLI minh họa** sau khi biên dịch `GcRequestDemo.java`, áp dụng cho JVM hỗ trợ cờ này. Output GC log phụ thuộc hệ thống, collector và các events thực sự xảy ra; **không đưa log đó vào một expected stdout cố định**.

Một số công cụ khác có thể hữu ích:

- **Java Flight Recorder (JFR):** phân tích các events, allocations và GC phases theo khả năng runtime/cấu hình.
- **`jcmd`**: chẩn đoán JVM đang chạy; command cụ thể cần được kiểm tra theo phiên bản JDK và quyền truy cập.
- **Heap dump + analyzer:** xem retaining paths, dominator tree, các object graph dài hạn.
- **JMX `GarbageCollectorMXBean`/MemoryMXBeans:** thu thập số liệu runtime được cung cấp; không hứa mapping một-một giữa metric và từng object được thu gom.
- **Application metrics:** counts của cache, số tasks đang chờ, active sessions, threads, connections.

**Phân biệt observation và guarantee:** log “đã có GC event” không cho bạn quyền dự đoán thời điểm GC sẽ tiếp tục chạy; số lần GC tăng không nói rằng một resource đã được đóng.

## 43. `GarbageCollectorMXBean` không cho thời điểm kết thúc sống của từng object

Một số JVM cung cấp garbage collector beans qua ManagementFactory:

~~~java
java.lang.management.ManagementFactory
        .getGarbageCollectorMXBeans();
~~~

Đây là snippet biểu thức hợp lệ nếu đặt trong method. Các beans có thể cung cấp collection count/time, nhưng số lượng collectors, tên collectors và metric availability **không cố định giữa các JVM**.

Các chỉ số như count có thể là `-1` nếu không được hỗ trợ; số liệu tính theo hoạt động collector, **không phải** “object X đã bị free ở thời gian Y”.

Đừng viết test `getCollectionCount() > 0` rồi kết luận một object cụ thể đã được thu gom. Để kiểm thử logic cleanup, gọi close/clean tường minh; để đo performance, dùng phương pháp benchmark và profiler thích hợp.

## 44. Chương trình hoàn chỉnh 18 — đọc số lượng collector beans mà không giả định loại GC

Tệp **`GcBeansDemo.java`**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;

public class GcBeansDemo {
    public static void main(String[] args) {
        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();

        System.out.println("beans collection available="
                + (beans != null));

        for (GarbageCollectorMXBean bean : beans) {
            if (bean.getCollectionCount() >= 0) {
                // Dữ liệu đo được phụ thuộc runtime;
                // không in một số đếm cố định.
                bean.getCollectionTime();
            }
        }

        System.out.println("no GC timing promise");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GcBeansDemo.java
java GcBeansDemo
~~~

**Stdout:**

~~~text
beans collection available=true
no GC timing promise
~~~

Demo không giả định tên `G1 Young Generation` hoặc `G1 Old Generation`, cũng không áp đặt số collections. Gọi getCollectionCount/getCollectionTime chỉ để minh họa rằng metrics có thể được truy vấn, không chứng minh bất cứ đối tượng riêng nào đã bị thu gom.

## 45. Kịch bản: “Gọi GC mà heap vẫn lớn” phải chẩn đoán thế nào?

**Tình huống:** một service chạy lâu, heap sử dụng tăng và request latency tăng. Team thử gọi `System.gc()` nhưng chart bộ nhớ không giảm rõ.

Quy trình điều tra:

1. Xác định chart biểu diễn **used heap, committed heap, resident memory hay container memory**.
2. Kiểm tra các chỉ số theo khoảng thời gian đủ dài và dưới workload đại diện.
3. Kiểm tra GC logs: tần suất, pauses, heap usage trước/sau events (nếu có).
4. Tìm classes có số instance tăng không mong muốn.
5. Dùng heap dump và phân tích **retaining references**.
6. Kiểm tra static caches, queues, listeners, ThreadLocals, active requests và native memory.
7. Xem dữ liệu giữ lâu có còn cần thiết hay không.
8. Đặt retention/eviction rules theo domain thay vì lệnh “ép GC định kỳ”.
9. Đo lại latency/throughput/capacity sau khi sửa ownership.
10. Nếu cần điều chỉnh collector/heap, benchmark trên môi trường tương đương production.

**Phần kết luận hợp lệ:** “cần tìm nguyên nhân retention hoặc hiểu lại loại số liệu memory”. **Phần kết luận không hợp lệ:** “Java GC bị hỏng vì chart không giảm ngay sau System.gc”.

## 46. Kịch bản: Listener đăng ký nhưng không hủy

Giả sử một application giữ một EventBus dài hạn, EventBus giữ danh sách listeners. Mỗi request tạo một listener capturing một request context lớn rồi đăng ký vào EventBus, nhưng không unregister.

~~~text
Long-lived EventBus
    |
    +-- listener 1 --> request context 1
    +-- listener 2 --> request context 2
    +-- listener 3 --> request context 3
    +-- ...
~~~

Khi các requests kết thúc, local variables của method xử lý đã biến mất, nhưng **EventBus còn giữ listeners**, listeners lại giữ contexts. Những object graphs này vẫn strongly reachable.

GC không thể tự xóa subscriptions chỉ vì request nghiệp vụ đã xong. Giải pháp là lifecycle design: đăng ký có ownership, trả token/subscription cho caller, `unsubscribe` trong finally/close, giới hạn backlog, hoặc tổ chức weak listener nếu contract cho phép (nhưng weak listeners có semantics mất callbacks bất ngờ).

Sealed/record/final keyword không tự sửa tình huống này; đó là vấn đề **đường tham chiếu và ownership**.

## 47. Kịch bản: `ThreadLocal` trong thread pool

`ThreadLocal<T>` gắn values với execution thread. Thread pool tái sử dụng threads, vì vậy một value liên quan request A có thể còn được giữ qua lifetime của worker thread nếu không cleanup theo đúng contract.

Mẫu thường dùng:

~~~java
try {
    CONTEXT.set(requestContext);
    // thực hiện công việc theo request
} finally {
    CONTEXT.remove();
}
~~~

Đây là **snippet minh họa**, giả định CONTEXT là ThreadLocal và requestContext được định nghĩa. Không phải một chương trình hoàn chỉnh.

`remove()` bảo đảm code bỏ value gắn với thread theo API, tránh vô tình mang context sang request tiếp theo. Không nên trông chờ GC tự suy ra request đã kết thúc và loại bỏ application data khỏi live thread.

Một ThreadLocal key weak reference trong implementation **không bảo đảm** mọi values được dọn tức thời khi key không còn strong reference; tránh bỏ qua cleanup.

## 48. Chương trình hoàn chỉnh 19 — dùng `ThreadLocal.remove()` có cấu trúc

Tệp **`ThreadLocalCleanupDemo.java`**:

~~~java
public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    static void handle() {
        CONTEXT.set("request-A");

        try {
            System.out.println("inside=" + CONTEXT.get());
        } finally {
            CONTEXT.remove();
        }
    }

    public static void main(String[] args) {
        handle();
        System.out.println("after=" + CONTEXT.get());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
~~~

**Stdout:**

~~~text
inside=request-A
after=null
~~~

`remove()` là API explicit; kết quả `CONTEXT.get()` null đến từ việc xóa ThreadLocal value, **không cần GC chạy**. Trong thread pool, một pattern `try/finally` tương tự giúp quản lý request-scoped state an toàn hơn.

## 49. Chương trình hoàn chỉnh 20 — `finally` chạy không phụ thuộc GC

Tệp **`FinallyCleanupDemo.java`**:

~~~java
public class FinallyCleanupDemo {
    static void runTask() {
        try {
            System.out.println("work");
            throw new IllegalStateException("failed");
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        try {
            runTask();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FinallyCleanupDemo.java
java FinallyCleanupDemo
~~~

**Stdout:**

~~~text
work
cleanup
caught=failed
~~~

`finally` là cơ chế điều khiển được ngôn ngữ xác định, không phải callback GC. Với resource có `AutoCloseable`, ưu tiên `try-with-resources` để code tự động gọi `close`; với cleanup không nằm trong AutoCloseable, `finally` vẫn có giá trị.

Các trường hợp termination bất thường của JVM/process không phải mọi trường hợp đều cho phép finally hoặc close chạy; nếu cần độ bền dữ liệu, phải tính cả crash và transactional semantics.

## 50. Không dùng `Thread.sleep` để kiểm tra GC

Một “test GC” thường gặp:

~~~java
Object object = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(object);
object = null;

System.gc();
Thread.sleep(1000);

// KHÔNG CÓ CAM KẾT rằng weak.get() == null ở đây.
~~~

Đây là snippet minh họa, cần nằm trong method có xử lý/khai báo InterruptedException nếu chạy. Nó **không phải một test hợp lệ có kết quả ổn định**.

Thời gian chờ chỉ tạo một khoảng delay của thread, không tạo một giới hạn thời gian bắt buộc collector phải xử lý object đó. Lịch GC là một phần implementation và có thể bị ảnh hưởng bởi heap size, collector flags, tải hệ thống hoặc việc chương trình giữ references mà người viết test bỏ sót.

Để kiểm thử cleanup, **gọi cleanup API trực tiếp** và verify postconditions. Để quan sát GC, dùng logs/metrics với cách diễn giải thống kê, không dùng một assertion cho “một object phải chết trong 1 giây”.

## 51. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế trong Java 17 |
| --- | --- |
| Gán `obj=null` thì object lập tức free | Chỉ thay một reference; object có thể còn reachable hoặc chưa được GC thu hồi |
| Rời khỏi method nghĩa là heap được giải phóng ngay | Không có cam kết GC timing |
| GC chỉ dựa vào đếm references | Reachability graph quan trọng; cycles có thể collectible |
| Có vòng A↔B thì JVM không thu gom được | Cycles không tự làm objects reachable từ roots |
| `System.gc()` buộc full GC đồng bộ | Chỉ là gợi ý nỗ lực GC theo API |
| Sau `System.gc()`, WeakReference chắc chắn null | Không bảo đảm |
| `WeakReference.get()==null` luôn chứng minh vừa có GC | Có thể đã `clear()` tường minh |
| SoftReference là cache dung lượng dự đoán được | Clearing/retention policy không phải TTL/size contract |
| PhantomReference có thể dùng get object | `get()` luôn null |
| `ReferenceQueue` luôn thông báo trước khi JVM exit | Không có cam kết timing đó |
| WeakHashMap tự xóa entry ngay khi local key null | GC/queue processing không diễn ra đúng một thời điểm cố định |
| GC sẽ đóng file khi object hết scope | Dùng explicit close/try-with-resources |
| Finalizer luôn chạy trước chương trình kết thúc | Không; finalization deprecated và không đáng tin |
| Cleaner là replacement cho `close()` đúng hạn | Cleaner tự động vẫn phụ thuộc reachability/scheduling |
| `reachabilityFence` gọi GC | Không; giữ referent reachable tới mốc cụ thể |
| Process RAM không giảm nghĩa là GC không giải phóng | Used/committed/native memory khác nhau |
| Java có GC nên không thể memory leak | Retained references vẫn có thể gây leak |
| `OutOfMemoryError` chứng minh collector hỏng | Có thể do memory pressure, retention, limits hoặc pools khác |
| Static cache giữ objects vô hạn vẫn được GC dọn | GC không bỏ objects còn reachable |
| ThreadLocal values tự hết khi request xong | Thread pool giữ threads; cần lifecycle/remove thích hợp |
| GC event count xác định tuổi thọ từng object | GC metrics không có guarantee đó |

## 52. Checklist thiết kế và code review

- [ ] Có phân biệt object không còn reachable và actual garbage collection?
- [ ] Có tránh khẳng định GC chạy ngay khi biến hết scope/gán null?
- [ ] Có kiểm tra aliases, static fields, collections và event listeners giữ references?
- [ ] Khi thấy object graph có cycle, có phân tích roots thay vì chỉ đếm edges?
- [ ] Có hiểu strong, soft, weak, phantom references ở mức cần thiết?
- [ ] Có tránh dùng `System.gc()` để bảo đảm một object được thu gom?
- [ ] Có tránh assert weak ref được clear sau `Thread.sleep`?
- [ ] Có tách file/socket/database lifecycle khỏi heap GC?
- [ ] Với AutoCloseable, có dùng try-with-resources đúng nơi?
- [ ] Có xử lý suppressed exceptions khi body/close cùng thất bại?
- [ ] Không dựa vào `finalize()` để đóng tài nguyên?
- [ ] Nếu dùng Cleaner, action có tránh capture referent mạnh?
- [ ] Cleaner có phải dự phòng thay vì cơ chế đóng tài nguyên chính?
- [ ] Có dùng `reachabilityFence` chỉ khi cần bảo vệ native resource lifetime?
- [ ] Nếu dùng WeakHashMap, có xét value→key strong reference và timing?
- [ ] Các cache dài hạn có eviction/size/TTL policy?
- [ ] Listeners/subscriptions được unregister theo vòng đời?
- [ ] ThreadLocal values được remove đúng điểm kết thúc request?
- [ ] Có phân biệt heap used, heap committed và process resident memory?
- [ ] Có thu thập metrics/logs thay vì dự đoán GC schedule?
- [ ] Có tránh in số heap bytes/GC counts cố định trong expected stdout?
- [ ] Có phân tích retained paths trước khi “tuning GC”?
- [ ] Nếu có `OutOfMemoryError`, có xác định loại memory pressure?
- [ ] Các tests xác minh logic explicit cleanup, không phụ thuộc GC timing?
- [ ] Có hiểu GC không đồng nghĩa immutability, closing hoặc security?

## 53. Bài tập tự luyện

**Câu 1.** Gán một biến reference thành null có nghĩa object đã được GC thu hồi không?

**Câu 2.** Nếu một List còn lưu reference tới object, gán biến local khác thành null có làm object không reachable không?

**Câu 3.** Hai objects A và B chỉ trỏ lẫn nhau, không còn đường nào từ roots. Vòng tham chiếu có ngăn GC xử lý chúng không?

**Câu 4.** Gọi `System.gc()` có bảo đảm full GC sẽ chạy và kết thúc trước khi trả về không?

**Câu 5.** Vì sao sau một GC event process RSS vẫn có thể cao?

**Câu 6.** `WeakReference.get()` có thể trả null khi nào?

**Câu 7.** Gọi `WeakReference.clear()` rồi thấy get null có chứng minh GC chạy không?

**Câu 8.** `SoftReference` có thích hợp thay một cache bắt buộc phải giữ tối đa 1.000 entries theo TTL cố định không?

**Câu 9.** `PhantomReference.get()` có thể trả object referent không?

**Câu 10.** `ReferenceQueue.poll()` trả null có nghĩa JVM chưa từng GC không?

**Câu 11.** Vì sao việc dùng `WeakHashMap` không bảo đảm entries biến mất ngay sau khi caller bỏ local key?

**Câu 12.** Nếu Map value trỏ lại key theo strong reference, điều gì có thể xảy ra với weak key?

**Câu 13.** FileInputStream nên được đóng bằng GC/finalizer hay try-with-resources?

**Câu 14.** Hai AutoCloseable resources A rồi B trong cùng try header đóng theo thứ tự nào?

**Câu 15.** Nếu try body ném exception và close cũng ném, exception nào thường là primary?

**Câu 16.** `finalize()` có bảo đảm được gọi trước khi process exit không?

**Câu 17.** `Cleaner.register` có bảo đảm action tự động chạy trong 100 ms sau khi referent unreachable không?

**Câu 18.** Vì sao không nên để Cleaner action capture strong reference tới object đang theo dõi?

**Câu 19.** `Cleanable.clean()` được gọi trực tiếp khác gì việc chờ Cleaner tự động?

**Câu 20.** `Reference.reachabilityFence(owner)` có tác dụng gì?

**Câu 21.** Một static cache không có eviction có thể gây Java memory leak không?

**Câu 22.** Vì sao `ThreadLocal` cần cleanup riêng trong thread pool?

**Câu 23.** `Runtime.totalMemory()` là số lượng bytes của một object đã được thu gom không?

**Câu 24.** GC log ghi một collection event có chứng minh một socket đã đóng không?

**Câu 25.** Có nên dùng `Thread.sleep(1000)` để đợi một `WeakReference` chắc chắn bị clear không?

**Câu 26.** Nếu chương trình có `OutOfMemoryError`, kết luận ngay “GC bị lỗi” có chính xác không?

**Câu 27.** Việc `List.clear()` trả về có bảo đảm heap memory được trả về hệ điều hành chưa?

**Câu 28.** Phân biệt used heap, committed heap và native resource lifetime.

**Câu 29.** Trong demo GcRequestDemo, dòng “GC request returned” xác nhận điều gì?

**Câu 30.** Trong demo CleanerDemo, vì sao `cleanup calls=1` không phải minh chứng GC?

**Câu 31.** Với event listener giữ request context, đâu là giải pháp lifecycle chủ động?

**Câu 32.** Khi nào nên dùng heap dump/retaining path analysis?

### Đáp án và giải thích

1. Không; biến mất một reference không bảo đảm actual GC.
2. Không; List vẫn có strong reference tới object.
3. Không; một graph cycle có thể collectible khi không reachable từ roots.
4. Không; System.gc là lời đề nghị, không hứa đối tượng cụ thể hoặc full GC.
5. JVM có thể giữ committed heap, process còn native memory và metrics thuộc các tầng khác nhau.
6. Khi weak referent bị clear theo reference processing hoặc caller gọi clear.
7. Không; clear chủ động gây kết quả null.
8. Không. TTL/capacity cần policy cache tường minh; soft clearing không có lịch dự đoán.
9. Không; get của PhantomReference luôn null.
10. Không; queue có thể rỗng do thời điểm processing hoặc chưa có reference event.
11. Vì việc clear/enqueue phụ thuộc GC và map processing, không dựa vào local scope.
12. Value có thể giữ key sống mạnh, làm entry tồn tại lâu ngoài ý muốn.
13. Try-with-resources hoặc explicit close theo API.
14. B đóng trước, rồi A.
15. Exception từ body là primary; exception từ close là suppressed theo quy tắc.
16. Không; finalization không có timing guarantee và không được khuyến nghị.
17. Không; automatic cleaning không được bảo đảm theo thời hạn ấy.
18. Strong capture có thể giữ referent reachable, ngăn cleanup tự động.
19. Clean() là lời gọi tường minh có thể chạy action synchronously, không cần GC.
20. Giữ referent strongly reachable ít nhất cho tới invocation fence.
21. Có; objects reachable qua cache dù business không còn cần.
22. Threads được tái sử dụng và có thể tiếp tục giữ request-scoped values.
23. Không; đó là metric heap JVM, không nói object cụ thể được giải phóng.
24. Không; GC không quản lý lifecycle socket đúng hạn.
25. Không; sleep chỉ delay thread, không ép GC.
26. Không; cần xác định OOME subtype, limits, allocations và retention.
27. Không; clear thay List state, không hứa JVM trả heap cho OS.
28. Used heap là memory sử dụng trong heap; committed là phần heap đã được JVM cam kết; native resources có lifecycle độc lập.
29. Chỉ xác nhận `System.gc()` đã trả về theo lần gọi đó.
30. Vì cleanable.clean được gọi trực tiếp, không dựa vào GC.
31. Unregister listener, clear strong references và quản lý subscription lifetime.
32. Khi có retention/memory trend bất thường cần tìm object holders và paths từ roots.

## 54. Tình huống thiết kế: từ mã lỗi tới mã đúng

**Mã có nguy cơ:**

~~~java
class FileWorker {
    void process(java.nio.file.Path path)
            throws java.io.IOException {
        java.io.InputStream stream =
                java.nio.file.Files.newInputStream(path);
        // đọc stream...
        // không gọi close; mong GC dọn.
    }
}
~~~

Đây là **snippet minh họa, không phải cách quản lý tài nguyên đúng**. Nếu exception xảy ra hoặc method return, file descriptor có thể chưa được release đúng hạn. Lập trình viên không thể chứng minh stream sẽ được thu gom ngay khi method kết thúc.

**Mã có ownership rõ:**

~~~java
class FileWorker {
    void process(java.nio.file.Path path)
            throws java.io.IOException {
        try (java.io.InputStream stream =
                     java.nio.file.Files.newInputStream(path)) {
            int firstByte = stream.read();
            System.out.println("first byte=" + firstByte);
        }
    }
}
~~~

Đây là **class snippet hợp lệ**, chưa có main và cần một file path có thật để chạy. Stream được đóng khi rời try-with-resources dù thành công hay thất bại khi đọc. Giá trị firstByte phụ thuộc nội dung file, nên **không được cung cấp stdout cố định** cho snippet này.

**Bản chất cải tiến:** cleanup được gắn với **đường điều khiển và ownership** thay vì phụ thuộc lịch GC. Đó là loại bảo đảm mà code ứng dụng có thể dựa vào.

## 55. Thực hành kiểm thử không dựa vào GC

Nên viết tests theo các nguyên tắc:

- Test `close()` được gọi sau try-with-resources bằng fake resource/counter.
- Test close order rõ ràng với nhiều resources.
- Test suppressed exception count/message khi close thất bại.
- Test cache eviction bằng `remove`, `clear` hoặc expiration API có cơ chế điều khiển được.
- Test `ReferenceQueue` consumer bằng manual enqueue nơi phù hợp.
- Test `Cleanable.clean()` chạy đúng một lần, không chờ cleaner thread.
- Test `WeakReference.clear()` trả null do explicit call; không dùng làm chứng minh collector.
- Dùng JFR/GC logs/heap dumps để **quan sát** GC, không đòi log output cố định qua môi trường.
- Đừng đưa collector names, allocation bytes hoặc GC counts vào stdout expected của những ví dụ cơ bản.

Nếu buộc làm một integration test liên quan GC thực tế, hãy chấp nhận nó có thể không deterministic, dùng instrumentation chuyên biệt và không đặt correctness của ứng dụng dựa trên timeout ngắn. Việc “test run được hôm nay” không biến GC timing thành JVM guarantee.

## 56. Tài liệu Java 17 chính thức

- [JLS 17 §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): khởi tạo object, construction.
- [JLS 17 §12.6 — Finalization of Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6): ngữ nghĩa finalization lịch sử và reachability.
- [Java SE 17 — `System.gc()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()): lời đề nghị GC, không cam kết thời điểm.
- [Java SE 17 — `Runtime.gc()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#gc()): explicit GC request.
- [Java SE 17 — `Runtime.freeMemory()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#freeMemory()): mẫu metrics heap.
- [Java SE 17 — `Runtime.totalMemory()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#totalMemory()): total available JVM memory.
- [Java SE 17 — `Reference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): reference objects, `clear`, `enqueue`, `reachabilityFence`.
- [Java SE 17 — `WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weakly reachable objects.
- [Java SE 17 — `SoftReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/SoftReference.html): softly reachable objects.
- [Java SE 17 — `PhantomReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html): phantom references với get luôn null.
- [Java SE 17 — `ReferenceQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html): thông báo reference processing.
- [Java SE 17 — `WeakHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys và lưu ý map lifetime.
- [Java SE 17 — `Cleaner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): cleanup registration.
- [Java SE 17 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): resource close contract.
- [JLS 17 §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): automatic close và suppressed exceptions.
- [Java SE 17 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): thông tin GC monitoring.
- [Java SE 17 — `ManagementFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): truy vấn MXBeans.
- [Java SE 17 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): request/thread-scoped values.
- [Java SE 17 — `OutOfMemoryError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html): các tình huống resource allocation failure.
- [JDK 17 Tools — Unified JVM Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): GC logging configuration.

## 57. Tổng kết

**Java có garbage collection tự động**: JVM có thể thu hồi bộ nhớ của objects không còn reachable theo các quy tắc của runtime. Nhưng **không có một mốc thời gian bảo đảm để một object bị thu gom** ngay sau khi biến local thành null, method kết thúc, hay `System.gc()` trả về. “Đủ điều kiện được thu gom” là một nhận định về reachability; “đã được thu gom” là một sự kiện runtime không thể suy ra chỉ từ source code.

Một ứng dụng Java đúng cần tự quyết định những việc **không thể chờ GC**: đóng streams/sockets/DB resources bằng `try-with-resources`, hủy subscriptions, giới hạn caches, dọn ThreadLocal values, và quản lý lifecycle của native handles. Weak/soft/phantom references, Cleaner và các công cụ GC monitoring hữu ích khi hiểu rõ hợp đồng của chúng, nhưng không biến garbage collection thành một cơ chế cleanup có deadline.

**Quy tắc kết thúc:** hãy để GC quản lý memory reclamation, và để **API ownership cùng luồng điều khiển chương trình** quản lý những tài nguyên cần kết thúc đúng lúc. Khi kiểm thử, dựa vào điều được Java bảo đảm — không dựa vào lịch collector có thể thay đổi ở mỗi môi trường.
