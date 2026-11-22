# Tham chiếu vòng và thời gian tồn tại của các đối tượng trong Java

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Mô tả **tham chiếu mạnh (strong reference)**, **đồ thị đối tượng (object graph)** và hiện tượng hai hay nhiều objects **tham chiếu vòng (cyclic references)**.
- Phân biệt **đối tượng còn truy cập được (reachable)** từ các điểm gốc (*GC roots*) với đối tượng **không còn truy cập được**; giải thích vì sao một vòng tham chiếu **không tự nó gây memory leak** trong Java.
- Đọc các sơ đồ và chương trình tạo vòng `A → B → A`, vòng dài hơn và liên kết một chiều/hai chiều; phân biệt chu kỳ trong graph với vòng lặp chương trình.
- Hiểu vòng đời: object creation, constructor, state mutations, links/references, reachability, **đủ điều kiện** cho garbage collection, thu hồi bộ nhớ và những điều không được bảo đảm về thời điểm.
- Chỉ ra các tình huống rò rỉ bộ nhớ do **tham chiếu bị giữ quá lâu** từ static collections, observers/listeners, caches, `ThreadLocal` và các objects giữ callback hoặc inner-class instance.
- Phân biệt thời gian tồn tại của Java object trong heap với **thời gian sử dụng/tắt tài nguyên** như file, socket, connection; áp dụng `AutoCloseable` và `try-with-resources`.
- Giải thích các lớp reference trong `java.lang.ref`: `WeakReference`, `SoftReference`, `PhantomReference` và `ReferenceQueue` ở mức đúng bản chất, không đưa ra dự đoán GC không chắc chắn.
- Thiết kế cập nhật liên kết hai chiều, tránh recursive `toString()`/`equals()`/traversal không dừng với graph có cycle, dùng tập visited dựa trên identity khi phù hợp.
- Hiểu `final` reference, `null`, ownership, composition UML, vòng tham chiếu của inner class, các giới hạn của `System.gc()` và concurrency.
- Biên dịch và chạy độc lập các ví dụ Java 17+ có stdout xác định.

## 1. Object có thể giữ tham chiếu tới object khác

Trong Java, một instance field có kiểu tham chiếu thường giữ **giá trị tham chiếu**, không “nhúng nguyên một object” theo cách người đọc mã nguồn cần thao tác như cấu trúc C.

~~~java
class Node {
    String name;
    Node next;

    Node(String name) {
        this.name = name;
    }
}
~~~

Đây là khai báo minh họa. Mỗi lần `new Node("A")` tạo một object `Node`. Field `next` có kiểu `Node`, ban đầu `null` nếu chưa được gán. Khi viết `a.next = b`, chương trình làm cho field của `a` giữ reference tới object mà `b` trỏ đến.

Có thể tạo hai liên kết:

~~~java
Node a = new Node("A");
Node b = new Node("B");
a.next = b;
b.next = a;
~~~

Các dòng trên cần đặt trong method hoặc initializer thích hợp. Chúng tạo **hai objects**, không tạo vô hạn objects:

~~~text
local a --> [Node A] ---next---> [Node B]
             ^                     |
             |---------next--------|
local b --------------------------> [Node B]
~~~

Hai fields `next` tạo một **chu trình trong object graph**: theo links có thể đi từ A sang B rồi từ B về A. Đó không phải một `while` chạy mãi; chương trình chỉ gán reference hai lần.

### 1.1. Tránh nhầm cycle với tự tham chiếu

Một object cũng có thể tham chiếu **chính nó**:

~~~java
Node a = new Node("A");
a.next = a;
~~~

Đây là vòng một đỉnh `A → A`, hợp lệ với kiểu Node ở trên. Java không cấm kiểu quan hệ đó; câu hỏi là **ngữ nghĩa nghiệp vụ** có cho phép nó hay không.

Nếu bạn xây dựng danh sách liên kết có invariant “không có cycle”, phải chủ động kiểm tra. Nếu mô hình là đồ thị mạng xã hội, cùng một loại reference cycle có thể là hợp lệ.

## 2. Chương trình runnable: tạo và ngắt một vòng tham chiếu

Lưu **`CyclicNodeDemo.java`**:

~~~java
public class CyclicNodeDemo {
    static final class Node {
        private final String name;
        private Node next;

        Node(String name) {
            this.name = name;
        }

        void linkTo(Node target) {
            this.next = target;
        }

        String name() {
            return name;
        }

        String nextName() {
            return next == null ? "none" : next.name;
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.linkTo(b);
        b.linkTo(a);

        System.out.println("A -> " + a.nextName());
        System.out.println("B -> " + b.nextName());
        System.out.println("cycle=" + (a == b.next));

        b.linkTo(null);
        System.out.println("after unlink B -> " + b.nextName());
        System.out.println("A -> " + a.nextName());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CyclicNodeDemo.java
java CyclicNodeDemo
~~~

Stdout chính xác:

~~~text
A -> B
B -> A
cycle=true
after unlink B -> none
A -> B
~~~

**Giải thích:**

1. `a` và `b` là hai biến local trỏ hai Node objects.
2. `a.linkTo(b)` gán reference tới B vào `A.next`.
3. `b.linkTo(a)` gán reference tới A vào `B.next`, hoàn thành vòng.
4. `a == b.next` là phép so sánh **identity của reference**: đúng vì `b.next` trỏ chính object A.
5. `b.linkTo(null)` ngắt **liên kết B → A**, nhưng không tự xóa A hoặc B. Biến local `a`, `b` còn giữ references; `A.next` vẫn trỏ B.
6. Không dòng nào trong chương trình nói rằng garbage collector đã hay sẽ lập tức thu hồi đối tượng. Output chỉ phản ánh **cấu trúc liên kết có thể quan sát qua API**.

**Điểm quan trọng:** `null` là giá trị “không tham chiếu object nào”, nhưng gán một field thành null chỉ bỏ đi **một đường đi**. Object có thể còn được tham chiếu ở nhiều nơi khác.

## 3. GC không phải reference counting đơn giản

Một trực giác sai:

> A trỏ B và B trỏ A, nên mỗi object có một người giữ; bộ nhớ của chúng không thể được thu hồi.

Đây là lập luận theo **đếm tham chiếu thuần túy**. Java garbage collection được mô tả theo **khả năng truy cập** (*reachability*) trong object graph; collector có thể thu gom cả nhóm objects tạo cycle nếu **không còn reachable từ GC roots**.

Đặt câu hỏi chính xác hơn:

> Có tồn tại một đường đi bằng các **strong references** từ một GC root thích hợp tới object này không?

Nếu có, object thuộc nhóm strongly reachable theo mô hình thông thường. Nếu toàn bộ một chu kỳ không còn đường đi như vậy, sự tồn tại của links bên trong chu kỳ **không tự khiến chúng sống mãi**.

### 3.1. GC roots là gì?

Ở mức khái niệm, các nguồn khả năng truy cập gồm:

- Những references được JVM xác định còn sống/được dùng trong các execution contexts, như một số local variables và stack frames của **threads đang hoạt động**.
- Static fields của các runtime classes còn liên quan đến tập root theo cơ chế JVM và class loaders.
- References do JNI/native/runtime quản lý theo quy tắc.
- Những runtime references khác do JVM coi là GC roots hoặc liên quan tới quá trình đánh dấu reachability.

Đây là mô hình để suy luận, **không phải danh sách bảo đảm mọi JVM luôn dùng thuật toán hoặc biểu diễn root giống hệt nhau**.

**Lưu ý tinh tế:** một local variable còn nằm trong scope ở mã nguồn không bảo đảm reference phải luôn được coi là còn live tới hết dấu `}`. JIT/VM có thể xác định object không còn được sử dụng sớm hơn. Ngược lại, không thể nhìn một dòng `x = null` rồi khẳng định collector đã chạy.

### 3.2. Ba đồ thị khác nhau

**Đồ thị I — có đường từ root:**

~~~text
GC root (ví dụ field của registry còn sống)
  |
  v
[A] --> [B]
 ^       |
 |-------|

Kết luận: A và B còn reachable qua root và strong references.
~~~

**Đồ thị II — vòng tách khỏi roots:**

~~~text
[A] --> [B]
 ^       |
 |-------|

Không còn đường strong-reference nào từ GC roots tới A/B.

Kết luận: cycle không tự ngăn A/B trở thành
những đối tượng đủ điều kiện được GC thu hồi.
~~~

**Đồ thị III — chỉ một đường giữ lại:**

~~~text
root --> [B] --> [A] --> [B]
~~~

Chỉ cần root còn trỏ B, thì cả B và A có thể còn strongly reachable. Ngắt `A.next` có thể chưa làm A đủ điều kiện thu gom vì B vẫn có thể trỏ A.

## 4. Reachable, unreachable, eligible và collected không đồng nghĩa

Các thuật ngữ dễ bị lẫn:

| Tình trạng | Ý nghĩa |
| --- | --- |
| **Strongly reachable** | Còn đường strong-reference từ root thích hợp đến object |
| **Không còn strongly reachable** | Không còn đường đó; có thể có ảnh hưởng từ soft/weak/phantom references tùy trường hợp |
| **Eligible for GC** | Có thể được hệ thống thu gom theo quy tắc reachability/reference processing |
| **Collected/reclaimed** | JVM/GC thực sự đã thực hiện xử lý và có thể thu hồi bộ nhớ |
| **Resource closed** | File/socket/connection... đã được đóng bằng hợp đồng API |
| **Đã hết scope của biến** | Một hiện tượng lexical; không phải sự kiện GC có timestamp được bảo đảm |

**Một object không còn được ứng dụng truy cập mạnh không có nghĩa “lập tức bị hủy”.** JVM có quyền chọn thời điểm hoạt động của GC và tối ưu hóa khác nhau. Thậm chí chương trình có thể kết thúc mà một số unreachable objects chưa được xử lý theo cách bạn có thể quan sát.

### 4.1. GC không phải destructor deterministic

Java không có ngữ nghĩa destructor được gọi chắc chắn ngay khi biến ra khỏi scope như một số mô hình RAII của C++.

~~~java
void process() {
    Object temp = new Object();
    // Dùng temp ...
}
~~~

Khi `process()` kết thúc, **không có callback nào được Java bảo đảm chạy ngay trên object** chỉ vì local variable biến mất khỏi phạm vi. Object có thể trở thành unreachable; thời điểm thu gom không xác định.

Vì thế không dựa vào GC để bảo đảm “cuối method thì file đã đóng”, “ngay khi gán null thì database connection trả về pool” hay “trước dòng kế tiếp memory phải được giải phóng”.

## 5. Chương trình về root giữ một chu kỳ — không đoán GC

Lưu **`RootedCycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RootedCycleDemo {
    static final class Node {
        final String name;
        Node next;

        Node(String name) {
            this.name = name;
        }

        String nextName() {
            return next == null ? "none" : next.name;
        }
    }

    private static final List<Node> REGISTRY = new ArrayList<>();

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        a.next = b;
        b.next = a;

        REGISTRY.add(a);

        System.out.println("registry size=" + REGISTRY.size());
        System.out.println("A -> " + REGISTRY.get(0).nextName());
        System.out.println("B -> " + b.nextName());

        REGISTRY.clear();
        System.out.println("registry after clear=" + REGISTRY.size());

        // Từ đây không đưa ra kết luận về thời điểm GC.
    }
}
~~~

Chạy:

~~~bash
javac RootedCycleDemo.java
java RootedCycleDemo
~~~

Output:

~~~text
registry size=1
A -> B
B -> A
registry after clear=0
~~~

**Phân tích:**

- `REGISTRY` là static list được initialized cùng class. Khi list chứa `a`, nó cung cấp một **đường giữ mạnh** tới A, rồi từ A tới B.
- `REGISTRY.clear()` xóa references được giữ trong list, làm mất đường giữ **qua REGISTRY**.
- Các local variables `a`, `b` vẫn xuất hiện ở method; dù JVM có thể tối ưu liveness, ví dụ **không khẳng định** ngay sau `clear()` hai objects đã unreachable hoặc đã collected.
- Để xác định một graph thực sự không còn reachable cần xét **mọi đường giữ**, không chỉ một collection.
- Mục đích chương trình là chứng minh registry có giữ references theo ngữ nghĩa API và xóa entry làm registry không còn giữ chúng, **không phải phép thử thời điểm GC**.

### 5.1. Vì sao không thêm `System.gc()` và in “đã hủy”?

`System.gc()` chỉ là một **yêu cầu/gợi ý** tới VM, không phải lời hứa “thu gom toàn bộ object không reachable ngay bây giờ”. Java không bảo đảm chương trình sẽ in một sự kiện GC cụ thể sau lời gọi ấy. Dùng `Thread.sleep(...)` rồi đoán cũng không biến hành vi thành deterministic.

Trong bài học có stdout chính xác, ta in **trạng thái references/collections có thể quan sát**, không suy diễn timing của collector.

## 6. Tham chiếu vòng không tự là memory leak

**Memory leak trong ứng dụng Java** thường được hiểu là tình huống objects **không còn cần về mặt nghiệp vụ** nhưng vẫn **được giữ reachable** ngoài ý muốn, dẫn đến chiếm bộ nhớ kéo dài/tăng dần. Java GC có thể hoạt động đúng mà ứng dụng vẫn leak do retention.

Các trường hợp:

- Một `static List<Object> ALL_USERS` tích lũy references mãi, không xóa entries sau khi session kết thúc.
- Event bus/listener registry giữ callbacks từ những subscribers không còn cần dùng.
- Cache không có giới hạn/eviction.
- Thread pool giữ `ThreadLocal` values qua nhiều requests do code quên `remove()`.
- Một long-lived owner giữ một inner-class instance mà instance đó giữ enclosing object, kéo theo object graph lớn.
- Một queue/task registry giữ callbacks hoặc closures lâu hơn thời gian sử dụng dự tính.

**Vòng tham chiếu chỉ đáng lo về memory retention nếu tồn tại đường strong-reference từ root/owner sống lâu tới vòng đó.** Không phải mỗi cặp `A.next=B; B.next=A` đều leak.

### 6.1. Phân biệt leak với cache hữu ích

Một cache giữ object lâu chưa chắc là lỗi: có thể đó là hành vi có chủ đích. Nhưng nếu không có giới hạn kích thước, thời gian sống hoặc phương thức eviction, cache dễ giữ quá nhiều objects.

Đánh giá cần dựa trên **ownership và mục đích nghiệp vụ**, không chỉ số references hay việc memory chưa giảm ngay trong profiler.

## 7. Static registry: mô phỏng retained graph và cleanup

Lưu **`RegistryLifecycleDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RegistryLifecycleDemo {
    static final class Session {
        private final String id;

        Session(String id) {
            this.id = id;
        }

        String id() {
            return id;
        }
    }

    static final class Registry {
        private static final Map<String, Session> SESSIONS =
                new HashMap<>();

        static void register(Session session) {
            SESSIONS.put(session.id(), session);
        }

        static void unregister(String id) {
            SESSIONS.remove(id);
        }

        static int size() {
            return SESSIONS.size();
        }
    }

    public static void main(String[] args) {
        Session session = new Session("S-1");
        Registry.register(session);

        System.out.println("registered=" + Registry.size());

        session = null;
        System.out.println("still registered=" + Registry.size());

        Registry.unregister("S-1");
        System.out.println("after unregister=" + Registry.size());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac RegistryLifecycleDemo.java
java RegistryLifecycleDemo
~~~

Output:

~~~text
registered=1
still registered=1
after unregister=0
~~~

**Diễn giải:**

- `Registry.SESSIONS` là map cấp lớp, giữ strong references tới `Session` values.
- Gán `session = null` chỉ bỏ reference trong **một biến local**; map vẫn giữ session bằng entry `"S-1"`.
- `unregister("S-1")` bỏ entry; map không còn giữ session đó.
- Chương trình không xác minh session đã được collector thu hồi; nó xác minh một **đường giữ mạnh** đã được dọn.
- Với hệ thống session thật, policy có thể dựa trên timeout/TTL, logout, bounded size và cleanup khi failure.

## 8. Listener/callback: rò rỉ bộ nhớ do quên hủy đăng ký

Trong mô hình observer, một object sống lâu (event bus) giữ references tới listeners. Listener có thể là:

- Một object listener trực tiếp.
- Lambda/method reference.
- Inner-class instance giữ enclosing object.
- Callback closure tham chiếu tới state lớn.

Nếu một subscriber “đã không dùng nữa” nhưng event bus **vẫn giữ callback** tham chiếu tới subscriber, subscriber và các objects reachable qua nó có thể tiếp tục sống lâu.

### 8.1. Tự quản lý subscription bằng `AutoCloseable`

Lưu **`ListenerLifecycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class ListenerLifecycleDemo {
    static final class EventBus {
        private final List<Consumer<String>> listeners =
                new ArrayList<>();

        AutoCloseable subscribe(Consumer<String> listener) {
            listeners.add(listener);
            return () -> listeners.remove(listener);
        }

        void publish(String event) {
            for (Consumer<String> listener : listeners) {
                listener.accept(event);
            }
        }

        int listenerCount() {
            return listeners.size();
        }
    }

    static final class Subscriber {
        private final String name;

        Subscriber(String name) {
            this.name = name;
        }

        Consumer<String> callback() {
            return event -> System.out.println(name + " heard " + event);
        }
    }

    public static void main(String[] args) throws Exception {
        EventBus bus = new EventBus();
        Subscriber subscriber = new Subscriber("Lan");

        try (AutoCloseable subscription =
                     bus.subscribe(subscriber.callback())) {
            System.out.println("listeners=" + bus.listenerCount());
            bus.publish("hello");
        }

        System.out.println("after close=" + bus.listenerCount());
        bus.publish("again");
        System.out.println("finished");
    }
}
~~~

Lệnh:

~~~bash
javac ListenerLifecycleDemo.java
java ListenerLifecycleDemo
~~~

Output:

~~~text
listeners=1
Lan heard hello
after close=0
finished
~~~

**Đường tham chiếu trong khi đăng ký:**

~~~text
root/owner -> EventBus
                |
                v
              listeners
                |
                v
          callback lambda
                |
                v
             Subscriber
                |
                v
              state
~~~

Lambda sử dụng instance field `name` trong `Subscriber.callback()`, nên callback cần giữ truy cập tới instance Subscriber tương ứng. EventBus giữ listener mạnh trong list. Sau `subscription.close()`, lambda được xóa khỏi list, ngắt một đường giữ từ EventBus.

**Điểm giới hạn:** ví dụ xử lý trên một luồng, không đồng bộ hóa list với việc phát events từ nhiều threads. Nếu concurrent subscribe/unsubscribe/publish, hãy thiết kế thread safety riêng. Ngoài ra, một subscription object vẫn có thể tạm giữ callback trong lúc scope còn sống; cleanup ở bus không đồng nghĩa mọi references từ tất cả nơi đều biến mất ngay.

### 8.2. Vì sao `try-with-resources` ở đây hữu ích?

Một subscription cũng có **vòng đời cần đóng rõ**. `try-with-resources` gọi `close()` khi rời khối theo hợp đồng, kể cả khi code trong khối ném exception (theo cơ chế exception/suppression của Java).

Không có gì buộc listener phải chờ tới GC mới hủy; API trả handle `AutoCloseable` khiến code kiểm soát **thời điểm bỏ đăng ký**.

## 9. `ThreadLocal` và long-lived threads

`ThreadLocal<T>` cho mỗi thread một giá trị liên quan theo API. Trong môi trường dùng thread pools, thread có thể sống qua rất nhiều requests. Nếu code:

~~~java
THREAD_CONTEXT.set(largeRequestContext);
~~~

mà không có cleanup, dữ liệu từ request trước có thể được giữ quá lâu hoặc bị dùng sai về mặt logic trên chính thread đó.

Một `ThreadLocal` instance không phải lời hứa “giá trị sẽ tự biến mất khi request kết thúc”. Cần có cleanup ở mức vòng đời của request/job.

### 9.1. Chương trình cleanup rõ ràng

Lưu **`ThreadLocalCleanupDemo.java`**:

~~~java
public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> USER =
            new ThreadLocal<>();

    static void handle(String user) {
        USER.set(user);
        try {
            System.out.println("handling=" + USER.get());
        } finally {
            USER.remove();
        }
    }

    public static void main(String[] args) {
        handle("Lan");
        System.out.println("after first=" + USER.get());

        handle("Minh");
        System.out.println("after second=" + USER.get());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
~~~

Output:

~~~text
handling=Lan
after first=null
handling=Minh
after second=null
~~~

**Tại sao dùng `finally`?**

- Nếu công việc trong `try` hoàn tất bình thường hoặc ném exception, `finally` vẫn thực hiện cleanup theo quy tắc Java.
- `ThreadLocal.remove()` xóa giá trị của current thread đối với ThreadLocal đó, tránh vô tình dùng lại giá trị request trước trong thread reused.
- Demo chỉ sử dụng main thread để stdout ổn định; nguy cơ thực tế cao hơn trong thread pools sống lâu.
- Không suy ra rằng `remove()` lập tức thu hồi object `String` hay toàn bộ graph: những references khác vẫn có thể tồn tại; GC có thời điểm riêng.

### 9.2. Không nhầm ThreadLocal với thread safety tổng quát

ThreadLocal giữ giá trị riêng theo thread cho một key ThreadLocal, nhưng nếu các values trong các threads cùng trỏ tới một **shared mutable object**, chúng vẫn có thể race khi mutate object đó.

Ngoài ra, việc JVM quản lý weak references tới ThreadLocal keys không thay bạn thiết kế cleanup; stale values có thể còn sống trong một số tình huống. Quy tắc đơn giản cho request-scoped context là **set → try/finally → remove**.

## 10. Weak references: không giữ mạnh object

Trong `java.lang.ref`, **`WeakReference<T>`** là một cách giữ reference mà **bản thân weak reference không giữ mạnh referent** như một strong reference thông thường.

Một weakly reachable referent có thể bị clearing/collection khi collector xử lý theo quy tắc weak references. Nhưng:

- Nếu có **strong reference khác** tới referent, weak ref không “ép” object bị thu hồi.
- `weakRef.get()` có thể trả referent hoặc `null` tùy trạng thái và hoạt động GC.
- Không được giả định weak reference sẽ trở thành null **ngay tại một dòng cố định** sau khi bỏ local reference.
- Nếu cần sử dụng referent lấy ra, hãy giữ local strong reference trong đoạn dùng và xử lý `null`.

### 10.1. Demo deterministic không dựa vào thời điểm GC

Lưu **`WeakReferenceBasicsDemo.java`**:

~~~java
import java.lang.ref.WeakReference;

public class WeakReferenceBasicsDemo {
    static final class Item {
        private final String name;

        Item(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Item strong = new Item("A");
        WeakReference<Item> weak = new WeakReference<>(strong);

        Item observed = weak.get();
        System.out.println("same object=" + (observed == strong));
        System.out.println("name=" + observed.name());

        strong = null;
        System.out.println("strong variable cleared");
        System.out.println("demo finished");
    }
}
~~~

Chạy:

~~~bash
javac WeakReferenceBasicsDemo.java
java WeakReferenceBasicsDemo
~~~

Output:

~~~text
same object=true
name=A
strong variable cleared
demo finished
~~~

Ở thời điểm `observed = weak.get()`, local `strong` vẫn được dùng ngay sau trong phép so sánh, và referent còn mạnh. Về sau `strong = null` chỉ xóa một reference; local `observed` có thể vẫn đang giữ referent, tùy phân tích liveness.

**Cố ý không in `weak.get() == null` sau `System.gc()`**, vì không thể ghi một stdout duy nhất mà Java luôn bảo đảm cho lần dọn GC đó. Tránh bài test phụ thuộc “collector phải chạy trong 100 ms”.

### 10.2. Weak reference không thay thế ownership

Nếu ứng dụng **cần** object B tồn tại trong suốt nghiệp vụ đang chạy, chỉ giữ `WeakReference<B>` là một thiết kế dễ lỗi: referent có thể bị thu gom khi không còn strong reference nào khác. Weak references phù hợp cho thông tin **có thể bỏ được**, canonicalizing/maps đặc thù hoặc cache tùy chính sách, không thay thế một required dependency.

## 11. `WeakHashMap`: weak keys nhưng strong values

`WeakHashMap<K,V>` là map đặc biệt với **keys được giữ weakly** theo cơ chế của Java. Khi một key không còn strong reachable ngoài map theo các quy tắc thích hợp, entry có thể bị bỏ trong quá trình GC/housekeeping.

Tuy vậy:

- Giá trị `V` thường được giữ **strongly** bởi map.
- Nếu value **tham chiếu mạnh trở lại key**, có thể xuất hiện đường giữ key qua map → value → key. Khi đó weak-key map không tự giải quyết retention.
- Số entries giảm sau khi collector xử lý là điều **không có thời điểm deterministic**. Không dùng “gán key=null rồi kiểm tra `size()==0`” làm test bắt buộc.
- WeakHashMap không mặc định thread-safe; cần synchronization hoặc lựa chọn khác khi chia sẻ giữa threads.
- Map vẫn dùng các hợp đồng keys như `equals`/`hashCode`; GC references và logical key equality là hai vấn đề khác nhau.

### 11.1. Ví dụ không giả định đã GC

Lưu **`WeakHashMapBasicsDemo.java`**:

~~~java
import java.util.Map;
import java.util.WeakHashMap;

public class WeakHashMapBasicsDemo {
    static final class Key {
        final int id;

        Key(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Map<Key, String> map = new WeakHashMap<>();
        Key key = new Key(1);

        map.put(key, "cached");
        System.out.println("value=" + map.get(key));
        System.out.println("contains key=" + map.containsKey(key));

        map.remove(key);
        System.out.println("after explicit remove=" + map.size());
    }
}
~~~

Chạy:

~~~bash
javac WeakHashMapBasicsDemo.java
java WeakHashMapBasicsDemo
~~~

Output:

~~~text
value=cached
contains key=true
after explicit remove=0
~~~

Đây là demo về cú pháp, semantics map và **explicit remove**; không coi nó là bằng chứng GC đã dọn một weak key. Nếu muốn đánh giá cache thực tế, cần profile và kiểm tra chính sách retention thay vì khẳng định thời điểm thu gom.

## 12. Soft, weak, phantom và reference queues

Bảng nhìn tổng quan:

| Loại | Ý nghĩa chính | Ghi chú |
| --- | --- | --- |
| **Strong reference** | Quan hệ tham chiếu thông thường giữa local/field/array elements và object | Có thể giữ object strongly reachable |
| **`SoftReference<T>`** | Tham chiếu mềm, VM có chính sách thu hồi dựa vào pressure/quy tắc | Không bảo đảm cache eviction kịp thời hay đáp ứng giới hạn memory cụ thể |
| **`WeakReference<T>`** | Không ngăn GC xử lý referent chỉ còn weakly reachable | `get()` có thể trở thành null |
| **`PhantomReference<T>`** | Cơ chế theo dõi giai đoạn sau khả năng truy cập qua reference queue | `get()` luôn trả null; không dùng để “lấy lại object” |
| **`ReferenceQueue<T>`** | Nhận references đã được VM enqueue theo lifecycle tương ứng | Việc enqueue phụ thuộc processing của collector, không phải đồng hồ deterministic |

**Không khuyên dùng soft refs như cache manager tổng quát** khi ứng dụng cần TTL, bounded memory hoặc eviction chính xác. Một cache có giới hạn và đo lường rõ thường tốt hơn.

### 12.1. `PhantomReference.get()` không trả referent

`PhantomReference` không phải “weak reference mạnh hơn” để đọc object sắp mất. Nó phối hợp với `ReferenceQueue` để theo dõi lifecycle và thực hiện cleanup theo kiến trúc cẩn thận; `get()` luôn null theo API.

Chỉ dùng loại reference này khi đã hiểu object lifetime, reference queues và các điều kiện concurrency/cleanup. Với file/DB connections thông thường, **`AutoCloseable` + `try-with-resources`** dễ đúng và dễ kiểm thử hơn.

### 12.2. `Cleaner` không thay `close()`

Java cung cấp `java.lang.ref.Cleaner` cho một số tình huống fallback cleanup. Nhưng cleanup phụ thuộc reachability và scheduling; không có lời hứa chính xác khi nào/hoặc tác vụ cleanup được chạy trước khi JVM kết thúc. Một cleaning action nếu vô tình giữ **strong reference tới chính object đăng ký** còn có thể ngăn object đủ điều kiện được dọn.

Khi quản lý tài nguyên ngoài heap, ưu tiên **đóng rõ ràng**, dùng Cleaner chỉ khi thật sự cần fallback và hiểu ràng buộc API.

## 13. Vòng đời của object không phải vòng đời của tài nguyên

Một object Java có thể **giữ handle** tới file/socket/database resource:

~~~text
Java object: FileReader/Socket/Connection
       |
       v
Tài nguyên hệ điều hành / connection pool / native handle
~~~

Garbage collection quản lý **bộ nhớ JVM của objects**; nó **không là hợp đồng đóng tài nguyên đúng thời điểm**. Nếu chỉ bỏ mọi references tới một `Connection` và chờ GC, ứng dụng có thể làm cạn connection pool trước khi collector xử lý.

Khái niệm cần tách:

1. **Object still reachable:** còn reference giữ object.
2. **Object no longer needed:** nghiệp vụ đã xong.
3. **Resource closed/released:** đã gọi API cleanup đúng.
4. **Object reclaimed by GC:** JVM thực tế thu hồi vùng bộ nhớ object.

Các sự kiện này không diễn ra đồng thời theo một quy tắc đơn giản.

### 13.1. `try-with-resources` cho cleanup có thể dự đoán

Lưu **`ResourceLifecycleDemo.java`**:

~~~java
public class ResourceLifecycleDemo {
    static final class Resource implements AutoCloseable {
        private final String name;
        private boolean closed;

        Resource(String name) {
            this.name = name;
            System.out.println("open=" + name);
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("already closed");
            }
            System.out.println("use=" + name);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("close=" + name);
            }
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource("R1")) {
            resource.use();
            System.out.println("inside block");
        }

        System.out.println("after block");
    }
}
~~~

Chạy:

~~~bash
javac ResourceLifecycleDemo.java
java ResourceLifecycleDemo
~~~

Output:

~~~text
open=R1
use=R1
inside block
close=R1
after block
~~~

Thời điểm `close=R1` **không phụ thuộc GC**: `try-with-resources` tự gọi `close()` khi thoát block theo ngữ nghĩa Java. Ví dụ `Resource` tự mô phỏng tài nguyên; trong thực tế `close` có thể đóng file, trả connection, hủy subscription hoặc giải phóng native handle.

### 13.2. Reference cycle có làm `close()` tự chạy không?

Không. Một object A giữ Resource B, B giữ lại A, rồi hai objects thành unreachable **không tự tạo lời gọi `close()` đúng thời điểm nghiệp vụ**. Phải định nghĩa owner/callback/try-with-resources để đóng tài nguyên.

Nếu hai resources có phụ thuộc đóng theo thứ tự, xây dựng một lifecycle owner đóng theo thứ tự thích hợp và xử lý exceptions. GC reachability không giải quyết dependency ordering này.

## 14. Finalization là cơ chế cũ, không nên phụ thuộc

Trong Java 17, finalization đã được **deprecated for removal** (theo các tài liệu nền tảng Java). Không dùng `finalize()` để làm giải pháp quản lý resource mới.

Vấn đề cơ bản:

- Việc object trở thành unreachable không bảo đảm finalizer chạy ngay hoặc chắc chắn trước khi chương trình kết thúc.
- Finalization có rủi ro bảo mật, hiệu năng, object resurrection và hành vi khó tiên đoán.
- Thứ tự cleanup giữa các objects có references qua lại không thể được thay thế bằng giả định “finalizer của A chạy trước B”.
- Code nghiệp vụ cần close/cleanup theo hợp đồng rõ ràng chứ không chờ finalization.

`Cleaner` hay phantom references là công cụ chuyên sâu cho fallback/resource management, nhưng **không thay thế** explicit lifecycle khi yêu cầu đóng chắc chắn.

## 15. Object resurrection và phạm vi kiến thức

**Object resurrection** là tình huống lịch sử khi code finalizer hoặc cơ chế đặc biệt khiến một object từng có nguy cơ bị thu gom lại trở nên reachable. Điều này minh họa vì sao finalization gây khó suy luận lifecycle.

Đối với bài này, không nên tạo ví dụ dựa vào `finalize()` hay đồng hồ GC. Điều cần nhớ: **không thiết kế object graph theo giả định “GC sẽ gọi một callback để tôi tái gắn object”**. Hãy công bố lifecycle qua methods/factories/repositories và kiểm soát khi nào owner giữ hoặc bỏ reference.

## 16. Duyệt đồ thị có vòng: cần tránh recursion không dừng

Khi bạn viết code duyệt một object graph:

~~~java
void visit(Node node) {
    visit(node.next);
}
~~~

nếu `next` quay lại object đã duyệt, recursion có thể không bao giờ chạm điều kiện dừng và cuối cùng gây `StackOverflowError`. Đây là **lỗi thuật toán duyệt graph**, không phải lỗi garbage collection.

### 16.1. Vì sao so sánh identity thường phù hợp?

Nếu mục tiêu là “mỗi **object instance** chỉ được thăm một lần”, hãy lưu **identity** đã thấy. Dùng `IdentityHashMap` hoặc set dựa trên identity hữu ích, bởi hai object khác nhau có thể `equals() == true` nhưng vẫn là hai nodes riêng trong graph.

Một `HashSet<Node>` thường dùng `equals`/`hashCode`; nếu Node là record theo value hoặc methods equality đệ quy theo neighbors, việc “visited” có thể bỏ sót nodes khác identity hoặc gặp recursion khác.

### 16.2. Chương trình DFS an toàn với chu trình

Lưu **`CycleSafeTraversalDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public class CycleSafeTraversalDemo {
    static final class Node {
        final String name;
        final List<Node> links = new ArrayList<>();

        Node(String name) {
            this.name = name;
        }

        void connect(Node other) {
            links.add(other);
        }
    }

    static void walk(Node node, Set<Node> seen, List<String> names) {
        if (node == null || !seen.add(node)) {
            return;
        }

        names.add(node.name);
        for (Node next : node.links) {
            walk(next, seen, names);
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");

        a.connect(b);
        b.connect(c);
        c.connect(a);
        a.connect(c);

        Set<Node> seen = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        List<String> order = new ArrayList<>();

        walk(a, seen, order);

        System.out.println("visited=" + order);
        System.out.println("count=" + seen.size());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CycleSafeTraversalDemo.java
java CycleSafeTraversalDemo
~~~

Output:

~~~text
visited=[A, B, C]
count=3
~~~

Giải thích:

1. `seen.add(node)` trả false nếu cùng object identity đã được thêm.
2. Khi C trỏ lại A, A đã trong `seen` nên recursion dừng ở nhánh đó.
3. Liên kết bổ sung A → C cũng không khiến C được in hai lần.
4. `names` bảo toàn thứ tự thăm theo thứ tự các links được thêm trong ví dụ; dùng `IdentityHashMap` chỉ để membership chứ không dựa vào thứ tự iteration của map.

**Giới hạn:** DFS đệ quy với graph **rất sâu** vẫn có thể tràn call stack dù đã tránh cycle. Với dữ liệu rất lớn, cân nhắc iterative DFS/BFS bằng stack/queue và giới hạn tài nguyên.

## 17. `toString()`, `equals()` và `hashCode()` khi có liên kết hai chiều

Một lỗi thường gặp:

~~~java
class Person {
    Department department;

    public String toString() {
        return "Person{department=" + department + "}";
    }
}

class Department {
    Person leader;

    public String toString() {
        return "Department{leader=" + leader + "}";
    }
}
~~~

Nếu `person.department = department` và `department.leader = person`, việc in `person` có thể tạo chuỗi lời gọi:

~~~text
Person.toString()
 -> Department.toString()
 -> Person.toString()
 -> Department.toString()
 -> ...
~~~

Cuối cùng có thể `StackOverflowError`. Hai khai báo là mã **minh họa**, không đưa ra một lệnh chạy để chủ động gây stack overflow.

Tương tự, nếu tự viết `equals()` và `hashCode()` bằng cách đi sâu vô hạn qua references lẫn nhau, có thể gây recursion, performance tệ hoặc hợp đồng equality không đúng.

### 17.1. Cách in an toàn hơn

Thay vì in cả object:

~~~java
@Override
public String toString() {
    return "Person{name=" + name
            + ",departmentId=" + department.id() + "}";
}
~~~

Đây là mảnh minh họa cần fields/types đúng và xử lý nullable department. Ý tưởng là **in định danh/tóm tắt của object liên quan**, không tiếp tục in mọi nested object không giới hạn.

Với object graph phức tạp/serialization, có thể:

- Dùng tập visited theo object identity.
- Giới hạn độ sâu và số nodes được mô tả.
- Dùng DTOs không tạo vòng khi trả API.
- Dùng cơ chế object references/IDs của framework serialization phù hợp, sau khi kiểm tra contract.
- Xác định equality theo **stable identity/domain key** thay vì toàn bộ graph vòng.

**Không phải mọi class đều nên override `equals` theo tất cả reference fields**; entity identity và value equality là hai lựa chọn thiết kế khác nhau.

## 18. Quan hệ hai chiều: tính nhất quán của link khác với reachability của graph

Nếu `Employee.department` trỏ đến `QA` nhưng `Engineering.employees` vẫn chứa Employee, **hai phía của association đã lệch**. Java không tự sửa các fields/collections đó. Một operation chuyển phòng phải cập nhật hai đầu theo invariant nghiệp vụ; nếu có nhiều threads hoặc persistence, còn cần synchronization/transaction phù hợp.

~~~text
Đúng về liên kết (sau chuyển):
  Employee.department ───> QA
  QA.employees ──────────> Employee
  Engineering.employees: không còn Employee
~~~

**Vòng tham chiếu xuất hiện trở lại là bình thường:** Employee trỏ QA, QA lại trỏ Employee. Đây không phải memory leak **chỉ vì** có chu kỳ. Với mục tiêu của bài này, câu hỏi khác quan trọng hơn là: **khi nhân viên/ngữ cảnh sử dụng hết vòng đời, còn GC root hay static registry/listener/cache nào giữ đường tham chiếu tới một phía của chu kỳ không?** Nếu còn, cả graph có thể tiếp tục reachable. Nếu không, collector có thể thu hồi graph (không cam kết thời điểm).

Bài **Quan hệ hai chiều và bảo toàn tính nhất quán** cung cấp chương trình chuyển liên kết, kiểm tra hai chiều và rollback/atomicity; ở đây hãy dùng cùng cấu trúc ấy để phân biệt **domain consistency** với **memory reachability và retention**.

## 19. Composition, aggregation và ownership có khác reachability không?

Các khái niệm UML:

- **Association:** hai objects có một mối quan hệ.
- **Aggregation:** whole–part với ownership lỏng; part có thể tồn tại độc lập.
- **Composition:** whole–part với lifecycle/ownership chặt hơn theo domain.

Đây là những **cam kết mô hình hóa**, không phải lệnh Java khiến GC thu hồi part ngay khi whole không được dùng nữa.

Ví dụ:

~~~java
class Order {
    private final List<OrderLine> lines;
}
~~~

Nếu Order giữ các lines nhưng một nơi khác còn giữ `OrderLine` reference, các line objects vẫn có thể reachable sau khi Order không còn được sử dụng. Nếu logic database yêu cầu cascade delete, điều đó thuộc transaction/persistence, **không** tự phát sinh vì field thuộc Order.

### 19.1. Ownership có thể giúp tránh retention

Một owner rõ ràng thường chịu trách nhiệm:

- Đăng ký và hủy listener.
- Thêm và xóa children/parts khỏi collection.
- Đóng resources khi kết thúc use case.
- Giới hạn cache.
- Xóa `ThreadLocal` sau request.
- Ngắt references tới context/session không còn cần thiết.

Những actions đó **loại bỏ strong-reference paths** và giải phóng tài nguyên đúng lúc; GC vẫn tự quyết định khi nào thu hồi bộ nhớ.

## 20. Non-static inner class có thể giữ enclosing object

Trong Java, một **non-static member inner class** gắn với một enclosing instance. Một instance của inner class có thể truy cập state của enclosing object qua `Outer.this` trong ngữ cảnh phù hợp.

Nếu một long-lived registry giữ một inner-class instance, nó có thể **gián tiếp giữ enclosing object** và object graph mà outer object giữ.

### 20.1. Chương trình thấy quan hệ enclosing instance

Lưu **`InnerClassReferenceDemo.java`**:

~~~java
public class InnerClassReferenceDemo {
    static final class Outer {
        private final String label;

        Outer(String label) {
            this.label = label;
        }

        class Inner {
            String describe() {
                return Outer.this.label;
            }
        }

        static class Nested {
            String describe() {
                return "static nested";
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer("A");
        Outer.Inner inner = outer.new Inner();
        Outer.Nested nested = new Outer.Nested();

        System.out.println("inner=" + inner.describe());
        System.out.println("nested=" + nested.describe());
    }
}
~~~

Chạy:

~~~bash
javac InnerClassReferenceDemo.java
java InnerClassReferenceDemo
~~~

Output:

~~~text
inner=A
nested=static nested
~~~

**Vì sao điều này liên quan thời gian tồn tại?**

- `inner` gắn với `outer` cụ thể; `Outer.this.label` đọc field của enclosing instance.
- Nếu object giữ `inner` sống lâu, có thể còn đường giữ tới `outer`.
- `static nested class` không có enclosing instance reference tự động tương tự; muốn dùng outer object phải được truyền một reference rõ.
- Đừng suy luận class nào có chữ “nested” cũng tự tạo cycle; cycle chỉ xuất hiện nếu các đường reference thực sự quay lại nhau.
- Compiler/runtime có quyền tổ chức implementation details; ý nghĩa ngôn ngữ quan trọng là **mối liên hệ enclosing instance** của inner object.

### 20.2. Listener là inner class

Một non-static inner listener được đăng ký vào global event bus có thể giữ Outer lâu hơn dự kiến. Nếu listener chỉ cần một identifier nhỏ, cân nhắc static nested class/đối tượng độc lập nhận dependency tối thiểu và có unsubscribe handle.

## 21. `final` reference có ngăn memory leak không?

Không. Xem:

~~~java
class Owner {
    private final Node node;

    Owner(Node node) {
        this.node = node;
    }
}
~~~

`final` ngăn reassign field `node` sau khởi tạo đúng, nhưng **không giới hạn** bao lâu Owner còn reachable. Nếu Owner nằm trong một long-lived map, Node cũng có thể bị giữ reachable vì Owner trỏ nó.

Một immutable object graph vẫn có thể bị **giữ quá lâu**, chiếm bộ nhớ không cần thiết. Immutability giúp concurrency và reasoning, **không tự tạo eviction/lifecycle**.

Ngược lại, mutable reference field cho phép `owner.node = null` có thể giúp bỏ link, nhưng không bắt buộc mọi thiết kế phải mở field mutable chỉ để GC. Hãy quyết định ownership, lifecycle và data retention theo hợp đồng.

## 22. Class loaders, static state và vòng đời ứng dụng

Static fields thuộc **runtime class**, mà identity chịu ảnh hưởng bởi class loader. Trong application servers/plugin systems, một class loader được dự định unload có thể vẫn bị giữ bởi một thread, callback, global registry hoặc object graph có reference path tới nó.

Điều này có thể giữ cả **nhiều classes/static data** sống lâu ngoài ý muốn. Không phải cứ đặt `static` là lỗi; vấn đề là lifecycle boundary của **class loader và những gì tiếp tục giữ nó reachable**.

Các ứng dụng có hot reload/plugin unload cần đặc biệt tránh:

- Thread do plugin tạo nhưng không dừng.
- Listener trong registry thuộc loader sống lâu giữ object/plugin class.
- Strong cache keys/values trỏ types/instances từ loader cần được unload.
- ThreadLocals và executors không được cleanup.

Đây là nguyên nhân memory retention **do đường giữ từ roots**, không phải vì mỗi plugin có cyclic references.

## 23. GC roots và Reachability API nâng cao

Trong Java 17, `java.lang.ref.Reference.reachabilityFence(Object)` cung cấp một cách đảm bảo object còn **strongly reachable ít nhất đến sau lời gọi fence** trong những ngữ cảnh cần thiết, ví dụ interoperability với native resources khi JIT có thể suy ra object không còn được dùng sớm.

Đây là công cụ nâng cao. Đa số code nghiệp vụ không cần gọi `reachabilityFence`, và nó **không thay `close()`**. Dùng sai nó có thể khiến người đọc nghĩ rằng object sẽ sống mãi hoặc được collector xử lý đúng thời điểm — cả hai đều không phải hợp đồng của API.

### 23.1. Local scope chưa chắc là lifetime

~~~java
void run() {
    Resource resource = new Resource();
    resource.useNativeHandle();
    // resource vẫn còn nằm trong scope về mặt source code
}
~~~

Đây là **mảnh minh họa** cần class `Resource` phù hợp. Java compiler/JIT có thể xác định local reference không còn cần thiết sau lần dùng cuối, tùy trường hợp. Mô hình “local trong scope đến cuối dấu } nên luôn mạnh tới lúc đó” không phải một quy tắc tuyệt đối.

Với native object liveness chuyên sâu, hãy tham khảo API `reachabilityFence` và patterns an toàn; với tài nguyên đóng thông thường, vẫn ưu tiên `try-with-resources`.

## 24. Các bước phân tích một memory-retention problem

Khi heap usage tăng, đừng khởi đầu bằng việc xóa bừa mọi cycle.

1. **Quan sát triệu chứng:** heap sau các GC cycles tăng dần? Số live objects tăng? Có cache/queue dự kiến lớn không?
2. **Xác định types đang bị retained:** profiler, heap dump hoặc JVM tooling phù hợp.
3. **Tìm retained paths tới GC roots:** ai đang giữ object? Static map, listener registry, thread, context, loader?
4. **Phân biệt object thật sự còn cần** với object đã hết vòng đời nghiệp vụ.
5. **Đọc ownership code:** ai đăng ký, ai nên unregister? Ai đặt vào cache, ai evict? Ai tạo resource, ai close?
6. **Xem các cycles:** nếu cycle **không có root path** thì không mặc nhiên là vấn đề; nếu có root path cần kiểm tra lý do giữ.
7. **Thêm cleanup hợp đồng:** `remove`, `unsubscribe`, `close`, `finally`, bounded cache/TTL, cancel tasks, shutdown executors.
8. **Chạy lại workload và đo:** xác minh live retained set giảm theo kỳ vọng; tránh chỉ dựa vào free memory ngay sau một dòng code.
9. **Kiểm tra concurrency:** cleanup và cập nhật graph có race không?
10. **Kiểm tra test robustness:** không viết test bắt buộc `System.gc()` khiến weakRef null ở một thời điểm cố định.

Trong trường hợp high-stakes hay production, heap dump và profiler cần được thu thập/đọc theo chính sách bảo mật vì có thể chứa dữ liệu người dùng nhạy cảm.

## 25. Unit tests cho quan hệ vòng và vòng đời

Các bài test **deterministic** nên tập trung vào hợp đồng API:

| Điều cần kiểm tra | Cách kiểm tra |
| --- | --- |
| Hai nodes tạo cycle | `a.next()==b` và `b.next()==a` |
| Ngắt liên kết đúng | `b.next()==null` sau unlink |
| Registry cleanup | `size()` giảm, lookup không còn entry |
| Listener unsubscribe | Counter/listener count giảm; event sau close không được gửi |
| ThreadLocal cleanup | `get()==null` sau `remove()` |
| Resource close | Flag `closed`/mock verify được gọi khi thoát `try-with-resources` |
| Graph traversal không vòng lặp vô hạn | Mỗi identity được duyệt một lần, kết quả ổn định |
| Quan hệ hai chiều | Sau chuyển department, old list không còn employee và new list có employee |
| WeakReference | Logic xử lý **cả** `get()!=null` và `get()==null`, không ép GC timing |
| Cache | Định nghĩa eviction/size/TTL và test bằng clock hoặc operations kiểm soát |

Test kiểu:

~~~java
System.gc();
Thread.sleep(100);
assert weak.get() == null;
~~~

là **ví dụ không nên dùng** làm một assertion portable: JVM không hứa dọn object trong 100 ms, và vẫn có thể còn strong references. Nếu cần kiểm tra cơ chế memory dưới workload, dùng integration/performance testing với quan sát thống kê và giới hạn của môi trường, không gọi đó là unit test tuyệt đối.

### 25.1. Test nên chứng minh cleanup, không chứng minh collector chạy

Sau `subscription.close()`, bạn có thể kiểm tra event bus không còn listener và không gọi callback nữa — đó là hành vi API deterministic. Không cần (và thường không thể) chứng minh ngay sau đó subscriber đã được GC thu hồi.

Tương tự, sau `Registry.unregister(id)` có thể assert map không còn entry; đó là bước cần thiết để loại bỏ **một đường retention**, không phải đảm bảo mọi references đều biến mất.

## 26. Lỗi thường gặp và cách sửa

| Hiểu nhầm/lỗi | Thực tế và giải pháp |
| --- | --- |
| “A trỏ B, B trỏ A thì Java bị memory leak.” | Cycle không tự giữ objects reachable từ roots; kiểm tra retained root paths. |
| “GC chỉ thu hồi object khi reference count bằng 0.” | Suy luận theo reachability, không theo reference-count thuần. |
| “Xóa một link nghĩa là object bị xóa.” | Có thể còn links khác; GC timing không xác định. |
| “Gán `x = null` là giải phóng bộ nhớ tức thì.” | Chỉ bỏ một reference; còn GC và aliases khác. |
| “Object ra khỏi scope chắc bị collected ngay.” | Scope và reachability/liveness không có timestamp đồng nhất. |
| “`System.gc()` bắt JVM chạy GC hoàn chỉnh ngay.” | Chỉ là request/hint; không có bảo đảm thời điểm/đối tượng thu hồi. |
| “Static cache không cần giới hạn vì có GC.” | Strong references trong cache có thể giữ objects dài hạn; thêm eviction. |
| “Listener sẽ tự biến mất sau khi UI đóng.” | Registry có thể vẫn giữ callback; unsubscribe khi hết lifecycle. |
| “ThreadLocal tự xóa sau mỗi request.” | Thread pool reuse; dùng `try/finally remove`. |
| “WeakReference luôn null sau khi gán strong=null.” | Có thể có aliases khác; timing collector không được bảo đảm. |
| “WeakHashMap có weak values.” | Keys weak, values thường strong; value→key cycle có thể giữ key. |
| “SoftReference là cache eviction policy chính xác.” | GC policy không là TTL/size cap có thể dự đoán. |
| “PhantomReference.get() trả object đã sắp chết.” | `get()` luôn null. |
| “Cleaner là destructor chắc chắn.” | Fallback không deterministic; dùng explicit close. |
| “Java GC sẽ tự đóng database/file ngay khi object không còn dùng.” | Đóng tài nguyên theo `AutoCloseable` và lifecycle. |
| “Composition UML bảo đảm part bị GC khi whole biến mất.” | Ownership là contract; aliases và roots khác vẫn tồn tại. |
| “Mọi `toString()` có thể in toàn bộ graph.” | Cyclic graph có thể khiến recursion vô hạn. |
| “`HashSet` luôn phù hợp theo dõi mỗi object instance.” | `equals` có thể hợp nhất object khác identity; cân nhắc IdentityHashMap. |
| “`final` reference khiến object không leak.” | Immutable/final object vẫn có thể bị root giữ quá lâu. |
| “Inner object không thể giữ Outer.” | Non-static inner object gắn enclosing instance; cân nhắc static nested. |
| “Java có thể tự cập nhật hai bên liên kết.” | Cần operation bảo vệ invariant graph hai chiều. |
| “Hai threads cập nhật references riêng chắc an toàn.” | Invariant nhiều objects và visibility cần synchronization. |
| “Heap chưa giảm nghĩa là cleanup thất bại.” | GC/heap management có timing riêng; đo live objects/retained paths. |

## 27. Checklist thiết kế object graph có vòng đời rõ ràng

Khi một class A giữ reference tới B, hãy kiểm tra:

1. **Quan hệ là bắt buộc hay tùy chọn?** Có cho phép `null` không?
2. **Ai tạo B?** A, caller, container, repository?
3. **Ai chịu trách nhiệm bỏ liên kết?** Có `detach`, `remove`, `unsubscribe` không?
4. **A và B có thể trỏ ngược nhau không?** Nếu có, liệu graph invariant được duy trì khi đổi link?
5. **B có mutable không?** Có alias từ nơi khác không?
6. **A sống bao lâu?** Request, session, application, static singleton?
7. **Có root path sống lâu không?** ThreadLocal, static map, listener, cache, loader?
8. **Có tài nguyên ngoài heap không?** Ai `close` và khi nào?
9. **Có cần weak reference không?** Nếu B là optional cache entry, ai giữ strong reference khi đang dùng?
10. **Collection có bounded size/eviction không?**
11. **Graph traversal/toString/serialization có cycle detection không?**
12. **Equality dựa identity hay domain value?** Tập visited dùng tiêu chí nào?
13. **Có concurrency không?** Đồng bộ các thao tác chuyển link và cleanup?
14. **Có kiểm thử cleanup deterministic không?** Không phụ thuộc vào GC timing.
15. **Có tài liệu ownership contract rõ không?** Không dựa vào tên “composition” để suy diễn tự động.

## 28. Câu hỏi ôn tập kèm lời giải

**Câu 1.** A.next = B và B.next = A tạo bao nhiêu objects nếu chỉ có hai lần `new`?  
**Đáp án:** Hai objects; các phép gán reference chỉ tạo cycle trong graph, không tạo thêm objects.

**Câu 2.** Vòng `A → B → A` có tự ngăn Java GC thu gom hai objects không?  
**Đáp án:** Không. Nếu cả graph không còn reachable theo các quy tắc reference processing từ GC roots, vòng tự nó không ngăn thu gom.

**Câu 3.** Nếu một static list giữ reference tới A, còn A trỏ B và B trỏ A, vì sao cả hai có thể được giữ?  
**Đáp án:** Có đường strong-reference từ root/registry tới A rồi B.

**Câu 4.** Gán `a = null` có bảo đảm B và A bị collected ngay không?  
**Đáp án:** Không. Có thể còn aliases, và JVM không cam kết GC tức thì.

**Câu 5.** Vì sao “biến ra khỏi scope” không hoàn toàn tương đương “object bị thu hồi”?  
**Đáp án:** Scope là khái niệm lexical, còn reachability/collection phụ thuộc runtime/liveness và collector.

**Câu 6.** Lỗi giữ objects không còn cần trong một static map được gọi là gì?  
**Đáp án:** Có thể là memory retention/memory leak của ứng dụng vì references được giữ quá lâu.

**Câu 7.** Một listener còn trong event bus sau khi UI đóng có thể giữ những gì?  
**Đáp án:** Callback và objects nó tham chiếu/capture, có thể gồm subscriber và graph liên quan.

**Câu 8.** Vì sao nên có handle unsubscribe/`AutoCloseable` cho listener?  
**Đáp án:** Để kết thúc đường giữ reference vào đúng thời điểm nghiệp vụ, không chờ GC.

**Câu 9.** Tại sao dùng `ThreadLocal` trong thread pool phải chú ý `remove()`?  
**Đáp án:** Threads được tái sử dụng nên context values có thể còn gắn với thread sang request khác hoặc bị giữ lâu.

**Câu 10.** `WeakReference.get()` có luôn trả object cho tới khi gọi `System.gc()` không?  
**Đáp án:** Không. Collector có thể clear weak ref theo quy tắc khi referent không còn strongly reachable; `get()` có thể null.

**Câu 11.** Sau `strong = null`, tại sao không assert weakRef.get()==null ngay?  
**Đáp án:** Có thể có references khác và không có bảo đảm collector chạy vào thời điểm đó.

**Câu 12.** `WeakHashMap` giữ keys và values theo cách nào?  
**Đáp án:** Keys weakly; values thông thường strongly. Value có strong path quay về key có thể ảnh hưởng retention.

**Câu 13.** `PhantomReference.get()` trả gì?  
**Đáp án:** Luôn `null` theo API.

**Câu 14.** Vì sao `SoftReference` không tự là giải pháp cache có giới hạn bộ nhớ chính xác?  
**Đáp án:** GC/clearing policy không là TTL hoặc bounded-size contract do ứng dụng kiểm soát.

**Câu 15.** Vì sao file nên được đóng bằng `try-with-resources` thay vì chờ GC?  
**Đáp án:** `close()` được gọi theo cấu trúc chương trình, bảo vệ tài nguyên vào thời điểm xác định; GC không bảo đảm khi nào đóng.

**Câu 16.** Một `AutoCloseable` có thể dùng ngoài file/socket không?  
**Đáp án:** Có. Ví dụ subscription handle dùng `close()` để unsubscribe.

**Câu 17.** Chu kỳ A↔B có thể gây lỗi khác ngoài retention không?  
**Đáp án:** Có. `toString`, `equals`, `hashCode` hoặc graph traversal ngây thơ có thể recurse không dừng.

**Câu 18.** Vì sao DFS qua cyclic graph cần tập visited?  
**Đáp án:** Để không thăm lại cùng object vô hạn; dùng identity-based set khi ý nghĩa là instance identity.

**Câu 19.** Khi nào `HashSet` có thể khác identity-based visited set?  
**Đáp án:** Khi `equals/hashCode` định nghĩa hai instances khác nhau là equal, HashSet có thể coi chúng là một mục.

**Câu 20.** Một Employee giữ Department và Department giữ Employees có phải Java tự đồng bộ hai phía không?  
**Đáp án:** Không. API phải cập nhật cả hai links/lists theo invariant.

**Câu 21.** `final Node next` có bảo đảm Node không bị giữ lâu không?  
**Đáp án:** Không. Final không quyết định lifetime của object graph được giữ từ roots.

**Câu 22.** Một non-static inner class có thể khiến Outer sống lâu hơn dự kiến như thế nào?  
**Đáp án:** Inner gắn với enclosing instance; nếu một root giữ inner, Outer có thể còn reachable qua quan hệ đó.

**Câu 23.** Nếu composition UML nói Part thuộc Whole, Java GC có tự xóa Part khi Whole hết dùng không?  
**Đáp án:** Không theo một lịch deterministic; part vẫn có thể reachable từ nơi khác và DB lifecycle là chuyện riêng.

**Câu 24.** Heap usage cao sau khi `registry.clear()` có chứng minh vẫn leak không?  
**Đáp án:** Không. JVM có thể giữ heap committed hoặc chưa thu gom; cần phân tích live objects/retained paths.

**Câu 25.** Tại sao không viết test “`System.gc(); sleep(100); assert weak.get()==null`”?  
**Đáp án:** Không portable và không deterministic: GC không bảo đảm chạy/xử lý referent trong thời gian đó.

**Câu 26.** Khi một resource được đóng nhưng Java object vẫn reachable, có mâu thuẫn không?  
**Đáp án:** Không. Resource lifecycle và object reachability là hai khái niệm độc lập.

**Câu 27.** `Cleaner` có làm `close()` không cần thiết không?  
**Đáp án:** Không. Cleaner là fallback có timing không chắc chắn, và cleaning action có thể giữ nhầm referent nếu thiết kế sai.

**Câu 28.** Root path qua class loader/thread có ảnh hưởng gì?  
**Đáp án:** Có thể giữ objects/classes/plugin graph tồn tại lâu ngoài ý muốn; cần giải phóng registrations, tasks và thread-associated state.

**Câu 29.** Khi nào một cycle là đúng nghiệp vụ?  
**Đáp án:** Ví dụ graph hai chiều, parent–child backlinks, mạng xã hội, doubly linked list, nếu invariant và traversal được thiết kế rõ.

**Câu 30.** Ba câu hỏi đầu tiên khi thấy “memory leak do cycle” là gì?  
**Đáp án:** (1) Object graph có còn reachable từ GC roots không? (2) Ai giữ đường reference đó và vì sao? (3) Có thể cleanup/evict/unsubscribe/close theo lifecycle không?

## Tài liệu tham khảo

- Java Language Specification, [`4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): kiểu và giá trị tham chiếu.
- Java Language Specification, [`4.12.5 — Initial Values of Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.5): mặc định `null` cho reference fields.
- Java Language Specification, [`12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): tạo và khởi tạo objects.
- Java Language Specification, [`12.6 — Finalization of Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6): quan hệ với finalization/reachability trong mô tả ngôn ngữ.
- Java Platform API, [`java.lang.ref Package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html): strong, soft, weak, phantom references và reachability.
- Java Platform API, [`WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak references.
- Java Platform API, [`WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys và strong values.
- Java Platform API, [`Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): fallback cleanup.
- Java Platform API, [`AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): explicit resource closing.
- Java Platform API, [`ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): thread-associated values và `remove`.
- Java Platform API, [`Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): advanced liveness boundary.
- Java Language Specification, [`14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): trình tự gọi `close`.
- OpenJDK [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): lý do không phụ thuộc finalization.

## Kết luận

**Tham chiếu vòng không tự gây memory leak trong Java.** Điều quyết định khả năng tiếp tục tồn tại của object graph là **những đường tham chiếu còn đi từ GC roots**, cùng ngữ nghĩa các loại reference thích hợp. Một vòng không còn reachable có thể được GC thu gom; ngược lại, chỉ một static registry hay callback còn giữ reference tới một object có thể giữ **cả graph** sống lâu hơn dự kiến.

Vì vậy, khi thiết kế quan hệ giữa các lớp, đừng chỉ hỏi “A và B có trỏ nhau không?”. Hãy hỏi **ai sở hữu liên kết, ai được phép đổi/hủy liên kết, vòng đời nghiệp vụ kết thúc khi nào, có đường giữ từ long-lived owner không, và có tài nguyên phải đóng rõ ràng không?**

Dùng **`unsubscribe`/`remove`/eviction**, `try-with-resources`, `ThreadLocal.remove()`, immutable/snapshot contracts, và duyệt graph có `visited` đúng identity khi phù hợp. **Không phụ thuộc vào `System.gc()` hoặc finalizer để quyết định thời điểm cleanup.** Hãy kiểm thử những thay đổi reference/API có thể đo xác định, còn thời điểm JVM thu gom bộ nhớ là một quyết định riêng của runtime.
