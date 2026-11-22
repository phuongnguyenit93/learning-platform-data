# Phân biệt phạm vi biến với khả năng đối tượng còn được truy cập — Java 17+

## Mục tiêu

Bài học này nằm trong chủ đề **Vòng đời đối tượng** của Java core. Sau khi học, bạn có thể:

- Phân biệt **lexical scope của tên biến** với **reachability của object** ở runtime.
- Hiểu rằng `}` đóng block và method `return` không phải thời điểm Java tự động xóa mọi object được tạo bên trong.
- Phân biệt **reference variable**, **reference value** và **heap object**, bao gồm nhiều aliases trỏ cùng một object.
- Xác định các đường giữ object qua return values, instance/static fields, arrays, collections, lambdas, inner classes, event listeners, threads và task queues.
- Giải thích Java **pass-by-value**, kể cả khi truyền reference type: reassign parameter không thay caller reference nhưng mutate referent có thể tác động caller.
- Hiểu chiều ngược: local variable vẫn trong lexical scope không đảm bảo referent strongly reachable đến hết block; JVM/JIT có thể ngừng giữ reference sau *last use* theo quy tắc Java.
- Phân biệt **có thể được garbage collector thu gom** với **đã được GC thu gom**; `System.gc()` không hứa thời điểm reclaim một object.
- Phân biệt strong, weak và những mức reachability trong `java.lang.ref`; sử dụng `WeakReference` và `Reference.reachabilityFence` mà không dự đoán output GC không xác định.
- Hiểu vòng references A→B→A không ngăn tracing GC reclaim nếu toàn bộ graph không còn root path.
- Nhận diện logical memory leaks từ long-lived maps, static registries, listeners, lambdas hoặc ThreadLocals giữ object lâu hơn dự kiến.
- Phân biệt object reachability, Java *statement reachability*, access modifiers, `final` và lifecycle của resources cần `close()`.
- Viết và chạy các ví dụ Java 17+ độc lập, với stdout chính xác **không phụ thuộc việc GC chạy ở một thời điểm nào đó**.

> **Phạm vi:** Java 17+. Các ví dụ có tên file, lệnh `javac`/`java` và stdout là chương trình hoàn chỉnh. Snippets không có `main` chỉ minh họa. Bài chủ ý không sử dụng finalizer logs, `Thread.sleep` hoặc `System.gc()` để khẳng định GC xảy ra đúng một dòng source.

## 1. Hai vấn đề khác nhau

Đoạn mã:

~~~java
{
    StringBuilder text = new StringBuilder("hello");
    System.out.println(text);
}
// text không được gọi tên bên ngoài block.
~~~

Câu hỏi **“Biến text còn trong phạm vi không?”** có câu trả lời **không**: lexical scope của local name đã kết thúc.

Câu hỏi **“StringBuilder object đã bị xóa chưa?”** không có câu trả lời từ dấu `}`:

- Có thể object được reference bởi biến/field khác.
- Có thể có callback/collection giữ nó gián tiếp.
- Có thể không còn strongly reachable, nhưng GC chưa reclaim.
- JVM/JIT có thể tối ưu object liveness sớm hơn trực giác dựa trên source variables.

Nói ngắn gọn:

**Scope là chuyện *tên nào dùng được ở vị trí source nào*. Reachability là chuyện *đường reference nào còn giúp tiếp tục truy cập object* tại runtime.**

### 1.1. Mô hình dễ nhớ

~~~text
Trong block:
   local text ─────► StringBuilder("hello")

Sau block:
   tên "text" không còn hợp lệ trong source.

Đối tượng StringBuilder:
   có thể có đường reference khác;
   có thể không còn accessible;
   có thể chưa bị GC reclaimed.
~~~

Đừng đồng nhất “local variable mất” với “heap object bị delete”. Java không có một cơ chế gọi destructor heap object tự động tại mọi lexical scope boundary.

## 2. JLS định nghĩa phạm vi tên biến như thế nào?

Java Language Specification (JLS) `6.3 mô tả scope của một declaration là vùng trong source có thể tham chiếu declaration đó bằng tên theo name resolution rules.

~~~java
static void example() {
    {
        int count = 3;
        System.out.println(count);
    }
    // System.out.println(count); // Không compile: ngoài scope.
}
~~~

Đối với reference variables cũng tương tự:

~~~java
static void example() {
    {
        Object local = new Object();
        System.out.println(local != null);
    }
    // local không còn được dùng bằng tên ở đây.
}
~~~

**Phân biệt ba lớp khái niệm:**

| Khái niệm | Hỏi về điều gì? | Ai quyết định? |
| --- | --- | --- |
| Lexical scope | Tên local/parameter có được dùng ở vị trí source này? | Java compiler/JLS |
| Runtime execution frame/liveness | Giá trị nào cần được giữ khi method đang chạy? | JVM/JIT theo Java semantics |
| Object reachability | Object có đường để continuing computation truy cập? | Runtime reference graph, tối ưu hóa và GC |

Không nên giả định mỗi source variable chiếm một stack slot cố định đến cuối block. JVM/JIT có thể dùng registers, lược bỏ locals không cần, rút ngắn liveness hoặc loại bỏ allocation nếu bảo toàn behavior.

## 3. Chương trình 1 — block scope không tạo GC event

Lưu **`BlockScopeDemo.java`**:

~~~java
public class BlockScopeDemo {
    static class Note {
        final String text;

        Note(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        System.out.println("before");
        {
            Note local = new Note("inside");
            System.out.println(local.text);
        }
        System.out.println("after");

        // System.out.println(local); // Không hợp lệ.
    }
}
~~~

Chạy:

~~~bash
javac --release 17 BlockScopeDemo.java
java BlockScopeDemo
~~~

Stdout:

~~~text
before
inside
after
~~~

Ta đã chứng minh **không thể dùng tên `local`** sau block. Không có bằng chứng nào rằng JVM đã chạy GC ở giữa hai lần println.

## 4. Biến tham chiếu khác object

Ví dụ:

~~~java
Box first = new Box("A");
Box second = first;
~~~

Hai reference variables có thể cùng chỉ một object:

~~~text
first ─────┐
           ├────► Box("A")
second ────┘
~~~

`first = null` đổi **giá trị reference của first**, không sửa second và không xóa Box object. Toán tử `==` trên reference operands kiểm tra identity, còn `equals` có thể so value tùy class.

Một local không phải “kho chứa nguyên object” theo source semantics: local giữ một reference value, object có thể được truy cập qua nhiều đường.

### 4.1. Chương trình 2 — alias giữ object

Lưu **`ReferenceAliasDemo.java`**:

~~~java
public class ReferenceAliasDemo {
    static class Box {
        String label;

        Box(String label) {
            this.label = label;
        }
    }

    public static void main(String[] args) {
        Box first = new Box("A");
        Box second = first;

        System.out.println("same=" + (first == second));
        first = null;

        System.out.println("first null=" + (first == null));
        System.out.println("second label=" + second.label);
        second.label = "B";
        System.out.println("second updated=" + second.label);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ReferenceAliasDemo.java
java ReferenceAliasDemo
~~~

Stdout:

~~~text
same=true
first null=true
second label=A
second updated=B
~~~

### 4.2. `final` không làm object bất tử

`final Box reference = ...` ngăn reassign variable đó, không làm referent tự immutable, không cam kết sống mãi và không ngăn GC một khi không còn đường cần thiết. `final` là quy tắc gán biến/field, không phải kiểu weak/strong reference đặc biệt.

## 5. Trả reference từ method là một dạng object escape

Một object được tạo trong method có thể được **trả ra**:

~~~java
static Book createBook() {
    Book local = new Book("Java");
    return local;
}
~~~

Sau return, local hết scope nhưng caller nhận được reference value:

~~~java
Book received = createBook();
~~~

Object có thể tiếp tục được dùng. Không có clone tự động và cũng không có “mọi object tạo trong method đều chết khi method kết thúc”.

### 5.1. Chương trình 3 — local hết scope, object qua return vẫn truy cập được

Lưu **`ReturnReferenceDemo.java`**:

~~~java
public class ReturnReferenceDemo {
    static class Book {
        final String title;

        Book(String title) {
            this.title = title;
        }
    }

    static Book makeBook() {
        Book local = new Book("Effective Java");
        return local;
    }

    public static void main(String[] args) {
        Book received = makeBook();
        System.out.println("title=" + received.title);
        System.out.println("received null=" + (received == null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ReturnReferenceDemo.java
java ReturnReferenceDemo
~~~

Stdout:

~~~text
title=Effective Java
received null=false
~~~

## 6. Truyền reference vào method: Java là pass-by-value

Khi truyền reference type argument, Java truyền **bản sao giá trị tham chiếu** cho parameter.

~~~java
static void reassign(Box parameter) {
    parameter = new Box("other");
}
~~~

Reassign `parameter` không đổi caller variable. Ngược lại:

~~~java
static void mutate(Box parameter) {
    parameter.label = "changed";
}
~~~

method sửa object mà cả caller và callee có thể tham chiếu. Parameter hết scope khi method return nhưng caller có thể vẫn giữ object.

### 6.1. Chương trình 4 — reassign khác mutate

Lưu **`ParameterScopeDemo.java`**:

~~~java
public class ParameterScopeDemo {
    static class Box {
        String label;

        Box(String label) {
            this.label = label;
        }
    }

    static void reassign(Box parameter) {
        parameter = new Box("other");
        System.out.println("inside reassign=" + parameter.label);
    }

    static void mutate(Box parameter) {
        parameter.label = "changed";
        System.out.println("inside mutate=" + parameter.label);
    }

    public static void main(String[] args) {
        Box caller = new Box("original");
        reassign(caller);
        System.out.println("after reassign=" + caller.label);
        mutate(caller);
        System.out.println("after mutate=" + caller.label);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ParameterScopeDemo.java
java ParameterScopeDemo
~~~

Stdout:

~~~text
inside reassign=other
after reassign=original
inside mutate=changed
after mutate=changed
~~~

Scope của parameter là source-level. Caller reference còn usable sau method return.

## 7. Instance field có thể giữ object lâu hơn local tạo ra nó

~~~java
Holder holder = new Holder();
{
    Item local = new Item("A");
    holder.item = local;
}
// local ngoài scope; holder.item vẫn có thể được dùng.
~~~

Đồ thị:

~~~text
holder ──► Holder object ──item──► Item("A")
~~~

Nếu Holder còn reachable, có đường reference từ Holder tới Item. `private` chỉ ảnh hưởng khả năng gọi tên field từ code khác, không khiến GC bỏ qua field. `final` hạn chế reassign field, không làm target tự deep-immutable.

### 7.1. Chương trình 5 — field giữ referent

Lưu **`FieldRetainsObjectDemo.java`**:

~~~java
public class FieldRetainsObjectDemo {
    static class Item {
        final String name;

        Item(String name) {
            this.name = name;
        }
    }

    static class Holder {
        Item item;
    }

    public static void main(String[] args) {
        Holder holder = new Holder();

        {
            Item local = new Item("retained");
            holder.item = local;
        }

        System.out.println("through field=" + holder.item.name);
        holder.item = null;
        System.out.println("field cleared=" + (holder.item == null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 FieldRetainsObjectDemo.java
java FieldRetainsObjectDemo
~~~

Stdout:

~~~text
through field=retained
field cleared=true
~~~

Sau `holder.item=null` chỉ biết Holder không còn giữ reference qua field đó; GC chưa chắc chạy và có thể có aliases khác.

## 8. Collection giữ references, không giữ “tên biến local”

Một `ArrayList<Item>` giữ reference tới elements. Khi code gọi `items.add(local)`, list có một reference path đến object. Local creator ra khỏi scope không tự xóa list element.

Tương tự, array cell `slots[0]=local` cũng giữ reference. `items.clear()` hoặc `slots[0]=null` bỏ đường reference tương ứng, không xóa aliases khác hay ép GC.

### 8.1. Chương trình 6 — collection retention

Lưu **`CollectionReachabilityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CollectionReachabilityDemo {
    static class Item {
        final String code;

        Item(String code) {
            this.code = code;
        }
    }

    public static void main(String[] args) {
        List<Item> items = new ArrayList<>();

        {
            Item temporary = new Item("A");
            items.add(temporary);
        }

        System.out.println("size=" + items.size());
        System.out.println("first=" + items.get(0).code);

        items.clear();
        System.out.println("cleared size=" + items.size());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CollectionReachabilityDemo.java
java CollectionReachabilityDemo
~~~

Stdout:

~~~text
size=1
first=A
cleared size=0
~~~

### 8.2. Chương trình 7 — array cell retention

Lưu **`ArrayAliasDemo.java`**:

~~~java
public class ArrayAliasDemo {
    static class Counter {
        int value;
    }

    public static void main(String[] args) {
        Counter[] slots = new Counter[1];

        {
            Counter local = new Counter();
            local.value = 5;
            slots[0] = local;
        }

        slots[0].value++;
        System.out.println("through array=" + slots[0].value);

        slots[0] = null;
        System.out.println("slot cleared=" + (slots[0] == null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ArrayAliasDemo.java
java ArrayAliasDemo
~~~

Stdout:

~~~text
through array=6
slot cleared=true
~~~

## 9. Static fields và lifetime dài hơn method

Static field là class-level state:

~~~java
class Cache {
    static Object retained;
}
~~~

Một method có thể lưu reference vào static field; sau method return, reference qua Cache vẫn có thể giữ object.

Không nói tuyệt đối “mọi static field tồn tại đến JVM shutdown” vì classloader/class unloading/liveness có thể khác theo runtime. Nhưng static caches và registries trong application là một nguồn **long-lived retention** rất phổ biến.

### 9.1. Chương trình 8 — static reference sau method return

Lưu **`StaticReferenceDemo.java`**:

~~~java
public class StaticReferenceDemo {
    static class Store {
        static StringBuilder kept;
    }

    static void build() {
        StringBuilder local = new StringBuilder("stored");
        Store.kept = local;
    }

    public static void main(String[] args) {
        build();
        System.out.println("static value=" + Store.kept);

        Store.kept = null;
        System.out.println("static cleared=" + (Store.kept == null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 StaticReferenceDemo.java
java StaticReferenceDemo
~~~

Stdout:

~~~text
static value=stored
static cleared=true
~~~

Method build return không khiến StringBuilder mất đi ngay, bởi class-level field tiếp tục giữ reference.

## 10. Quan trọng: biến **còn trong scope** nhưng object có thể hết liveness trước dấu ngoặc đóng

Đây là chiều ngược thường bị bỏ qua:

~~~java
static void work() {
    byte[] data = new byte[1_000_000];
    System.out.println(data.length);

    doOtherWork();
    // Tên data vẫn nằm trong lexical scope.
}
~~~

Sau lần sử dụng cuối `data.length`, JVM/JIT có thể xác định reference không còn cần cho continuing computation nào nữa. JLS `12.6.1 cho phép optimizing transformations giảm tập objects reachable so với suy luận ngây thơ từ locals; ví dụ runtime có thể xử lý variable/parameter không còn dùng như đã không giữ reference.

Như vậy:

- **Tên vẫn trong scope** ≠ **referent bắt buộc strongly reachable đến hết block**.
- Optimizing runtime phải bảo toàn *observable Java behavior*. Nếu sau này source thực sự đọc data ở một phép đọc hợp lệ, tối ưu hóa không được làm kết quả sai.
- Last-use analysis và stack/register liveness là runtime/compiler concerns, không định nghĩa lại lexical scope của tên biến.
- Không dựa vào một output finalizer hoặc GC log để nói object được giải phóng chính xác ở dòng nào.

**Tóm lại:** phạm vi tên là khái niệm source/compile time; reachability có tính runtime và được JVM tối ưu hợp lệ.

## 11. `x = null` không phải `delete x`

~~~java
Object value = create();
use(value);
value = null;
~~~

Assignment cuối thay giá trị local reference. Nó đôi khi giúp rút ngắn retention trong long-running frame, nhưng JIT có thể tự nhận ra last use. Đừng thêm `=null` vào mọi method như nghi thức dọn bộ nhớ.

Đặc biệt, nếu `other=value` trước khi gán null, `other` vẫn giữ object. Nếu `value` đã được thêm vào cache/list/field, gán null local không xóa các references kia.

### 11.1. Chương trình 9 — reassignment không hủy object cũ

Lưu **`ReassignmentDemo.java`**:

~~~java
public class ReassignmentDemo {
    static class Data {
        final int value;

        Data(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Data first = new Data(1);
        Data alias = first;

        first = new Data(2);
        System.out.println("first=" + first.value);
        System.out.println("alias=" + alias.value);
        System.out.println("same=" + (first == alias));

        alias = null;
        System.out.println("alias null=" + (alias == null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ReassignmentDemo.java
java ReassignmentDemo
~~~

Stdout:

~~~text
first=2
alias=1
same=false
alias null=true
~~~

## 12. Lambda có thể capture reference rồi được giữ lâu hơn block

Một final/effectively final local có thể được lambda capture:

~~~java
Runnable action;
{
    StringBuilder builder = new StringBuilder("A");
    action = () -> System.out.println(builder);
}
action.run();
~~~

`builder` hết lexical scope nhưng lambda vẫn cần captured value. Cách JVM tạo/bố trí lambda object là implementation detail; semantics bảo đảm callback có thể dùng referent.

**Effectively final** nói biến reference không reassign, **không** nói StringBuilder object bất biến. Lambda có thể `append` nội dung.

### 12.1. Chương trình 10 — captured reference còn usable

Lưu **`LambdaCaptureDemo.java`**:

~~~java
public class LambdaCaptureDemo {
    public static void main(String[] args) {
        Runnable action;

        {
            StringBuilder builder = new StringBuilder("A");
            action = () -> {
                builder.append("!");
                System.out.println("captured=" + builder);
            };
        }

        action.run();
        action.run();
    }
}
~~~

Chạy:

~~~bash
javac --release 17 LambdaCaptureDemo.java
java LambdaCaptureDemo
~~~

Stdout:

~~~text
captured=A!
captured=A!!
~~~

Một callback được lưu trong registry/listener/timer có thể giữ cả graph các objects mà nó capture sau khi method đăng ký đã return.

## 13. Inner class, listener, event bus và closure retention

Một **non-static inner class** có enclosing instance theo semantics Java. Nếu giữ inner object, nó có thể giữ outer object, nhất là khi inner methods cần state outer.

Một listener được thêm vào long-lived EventBus có thể giữ references qua captured values:

~~~text
EventBus ──listeners──► Listener / lambda ──capture──► Session
~~~

Ngay cả khi local Session variable đã hết scope, graph có thể vẫn reachable. Đó là retention **có chủ đích** nếu session còn cần sự kiện, nhưng có thể là logical memory leak nếu session hết hạn mà listener không được unsubscribe.

**Cách tránh:**
- `subscribe` nên trả handle/token; dùng `removeListener`/`unsubscribe`.
- Không capture toàn bộ Controller lớn khi chỉ cần một small immutable ID.
- Static nested class không tự có enclosing instance, nên thích hợp khi không cần outer state.
- Nếu dùng weak listener strategy, vẫn phải hiểu lifecycle/reference paths; WeakReference không tự giải quyết mọi leak.

### 13.1. Chương trình 11 — listener còn sau khi local hết scope

Lưu **`ListenerRetentionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerRetentionDemo {
    interface Listener {
        String event();
    }

    static class EventBus {
        private final List<Listener> listeners = new ArrayList<>();

        void subscribe(Listener listener) {
            listeners.add(listener);
        }

        int size() {
            return listeners.size();
        }

        String firstEvent() {
            return listeners.get(0).event();
        }
    }

    static void register(EventBus bus) {
        StringBuilder state = new StringBuilder("session");
        bus.subscribe(() -> state.toString());
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();

        register(bus);
        System.out.println("listeners=" + bus.size());
        System.out.println("event=" + bus.firstEvent());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ListenerRetentionDemo.java
java ListenerRetentionDemo
~~~

Stdout:

~~~text
listeners=1
event=session
~~~

## 14. Task queue/executor cũng giữ object references

Nếu Runnable capture Payload rồi nằm trong queue của một executor:

~~~text
executor ──► queue ──► Runnable ──► captured payload
~~~

thì method tạo Runnable đã kết thúc cũng không khiến captured payload mất khả năng truy cập. Live threads có thể giữ objects đang được dùng qua stack frames/locals của chính chúng.

`Future.cancel`/executor shutdown không được diễn giải thành “mọi captured object lập tức được GC”: task có thể đang chạy, còn ở queue, hoặc ứng dụng giữ Future/result references. Cần hiểu lifecycle cụ thể.

### 14.1. Chương trình 12 — deferred action

Lưu **`DeferredTaskDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Queue;

public class DeferredTaskDemo {
    static final Queue<Runnable> TASKS = new ArrayDeque<>();

    static void schedule() {
        StringBuilder payload = new StringBuilder("job");
        TASKS.add(() -> System.out.println("task=" + payload));
    }

    public static void main(String[] args) {
        schedule();
        System.out.println("queued=" + TASKS.size());

        Runnable action = TASKS.remove();
        action.run();

        System.out.println("remaining=" + TASKS.size());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 DeferredTaskDemo.java
java DeferredTaskDemo
~~~

Stdout:

~~~text
queued=1
task=job
remaining=0
~~~

Queue remove bỏ một retaining path, nhưng `action` còn giữ Runnable tại lúc chạy. Không suy GC timing từ những operations ấy.

## 15. Reference graph, GC roots và “còn reachable qua đường nào?”

Một object có thể được giữ gián tiếp:

~~~text
Root / live service
       |
       v
   Cache Map
       |
       +──► UserSession
                  |
                  +──► Events List
                  |      |
                  |      +──► Event
                  |
                  +──► byte[] Buffer
~~~

Muốn biết Event hoặc Buffer còn accessible hay không, phải tìm đường từ live computation/GC roots qua Map/Session/List. Không chỉ xem một local variable từng tạo nó đã hết scope.

JVM collector định nghĩa những GC roots phù hợp từ thread/VM/class references và traverses references. Chi tiết enumeration có thể phụ thuộc implementation; không coi mọi local name trong scope là một root phải sống tới hết block.

### 15.1. Static field không nhất thiết “immortal” trong mọi JVM

Một class có thể được unload khi classloader/VM liveness cho phép. Nhưng trong một application server, static caches và classloader retention vẫn có thể giữ graph lâu ngoài ý muốn. Hãy thiết kế eviction/cleanup theo lifecycle, không dựa vào khẳng định tuyệt đối về static.

## 16. Reference cycle không bắt đối tượng sống mãi

Hai objects A và B có thể tham chiếu lẫn nhau:

~~~text
A ──next──► B
▲           |
└───────────┘
~~~

Nếu vẫn còn root path đến A hoặc B, cả cycle reachable. Nếu không còn path nào từ roots/live computations tới cycle, cả graph có thể được reclaimed.

Java tracing garbage collection không phải đơn giản “đếm incoming references”; nếu object chỉ được tham chiếu bởi nhau nhưng không còn reachable từ roots, chúng không tự bất tử.

### 16.1. Chương trình 13 — cycle và cleared locals

Lưu **`ReferenceCycleDemo.java`**:

~~~java
public class ReferenceCycleDemo {
    static class Node {
        final String label;
        Node next;

        Node(String label) {
            this.label = label;
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.next = b;
        b.next = a;

        System.out.println("cycle=" +
                a.next.next.label + "/" + b.next.next.label);

        a = null;
        b = null;

        System.out.println("locals cleared=" +
                (a == null && b == null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ReferenceCycleDemo.java
java ReferenceCycleDemo
~~~

Stdout:

~~~text
cycle=A/B
locals cleared=true
~~~

Kết quả chỉ chứng minh locals null. Không phải phép đo collector đã reclaim A/B. Nếu static field khác giữ A, cả cycle có thể vẫn reachable.

## 17. WeakReference và sự không xác định của GC timing

`java.lang.ref.WeakReference<T>` là một reference object không giữ referent **strongly reachable** chỉ vì WeakReference tồn tại.

~~~java
Object strong = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(strong);
~~~

Khi không còn đường strong reachability đến referent, GC có thể clear weak reference, khi ấy `weak.get()` trả null. **Không có guarantee thời điểm ấy**.

Đừng viết test:

~~~java
// strong = null;
// System.gc();
// System.out.println(weak.get() == null);
// Không thể hứa output true/false cố định.
~~~

`System.gc()` chỉ yêu cầu/gợi ý collector, không xác nhận object nào đã reclaimed. `WeakHashMap` cũng không làm mọi key/object bị collect nếu có strong paths khác, đặc biệt khi value lại giữ key.

### 17.1. Chương trình 14 — WeakReference nhưng stdout xác định

Lưu **`WeakReferenceBasicsDemo.java`**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceBasicsDemo {
    static class Payload {
        final String value;

        Payload(String value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Payload strong = new Payload("ready");
        WeakReference<Payload> weak = new WeakReference<>(strong);

        boolean same = weak.get() == strong;
        System.out.println("same while strong used=" + same);
        System.out.println("value=" + strong.value);

        Reference.reachabilityFence(strong);
        strong = null;

        System.out.println("strong cleared=" + (strong == null));
        System.out.println("GC outcome not asserted");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 WeakReferenceBasicsDemo.java
java WeakReferenceBasicsDemo
~~~

Stdout:

~~~text
same while strong used=true
value=ready
strong cleared=true
GC outcome not asserted
~~~

Lúc so `weak.get() == strong`, strong reference được dùng trong expression nên referent strongly reachable cho phép so identity đúng. `Reference.reachabilityFence` chỉ định một điểm mà strong reachability được bảo đảm. Ví dụ không đo thời điểm weak.get() sau khi strong=null.

## 18. `Reference.reachabilityFence` và `System.gc()` không có cùng mục đích

- `Reference.reachabilityFence(obj)`: bảo đảm object mạnh đến điểm gọi, hữu ích đặc biệt khi native/external resource operation cần owner Java object vẫn reachable.
- `System.gc()`: gợi ý JVM thực hiện garbage collection. Không bảo đảm đối tượng cụ thể được collect.
- `obj=null`: gán lại một variable/field reference.
- `close()`: release external resource theo API contract.
- Kết thúc `try-with-resources`: Java language bảo đảm close theo control flow, không thông qua GC.

Không dùng reachabilityFence để cố giữ objects lâu không cần thiết; cũng không dùng System.gc để thay evict/remove/close.

## 19. Resource lifetime khác object lifetime

Một Java object có thể quản lý file descriptor, socket, database connection hoặc native handle. Khi local reference hết scope, GC không buộc đóng resource ngay. Finalization đã deprecated và không nên dùng làm cleanup mechanism.

`AutoCloseable` và try-with-resources xác định khi nào `close()` được gọi theo program control flow.

### 19.1. Chương trình 15 — close deterministic, GC không liên quan

Lưu **`ResourceScopeDemo.java`**:

~~~java
public class ResourceScopeDemo {
    static class Resource implements AutoCloseable {
        final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("opened=" + name);
        }

        void use() {
            System.out.println("used=" + name);
        }

        @Override
        public void close() {
            System.out.println("closed=" + name);
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource("R")) {
            resource.use();
        }

        System.out.println("after try");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ResourceScopeDemo.java
java ResourceScopeDemo
~~~

Stdout:

~~~text
opened=R
used=R
closed=R
after try
~~~

`closed=R` là kết quả của try-with-resources. Resource Java object có thể còn reachable hoặc chưa reclaimed sau đó, nhưng logical resource được close đúng lúc.

## 20. Access modifiers và GC reachability độc lập

`private` là Java access-control modifier; không biến field reference thành weak. `final` giới hạn reassignment theo source rules; không làm object referenced sâu bất biến hoặc immortal.

~~~java
class Holder {
    private final Object payload;

    Holder(Object payload) {
        this.payload = payload;
    }
}
~~~

Một Holder reachable có field reference tới payload; path tồn tại dù caller không được phép viết `holder.payload` trực tiếp.

### 20.1. Chương trình 16 — private field giữ payload

Lưu **`PrivateFieldDemo.java`**:

~~~java
public class PrivateFieldDemo {
    static class Payload {
        final String name;

        Payload(String name) {
            this.name = name;
        }
    }

    static class Holder {
        private final Payload payload;

        Holder(Payload payload) {
            this.payload = payload;
        }

        Payload payload() {
            return payload;
        }
    }

    static Holder create() {
        Payload local = new Payload("kept");
        return new Holder(local);
    }

    public static void main(String[] args) {
        Holder holder = create();

        System.out.println("payload=" + holder.payload().name);
        System.out.println("present=" + (holder.payload() != null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PrivateFieldDemo.java
java PrivateFieldDemo
~~~

Stdout:

~~~text
payload=kept
present=true
~~~

`local` hết scope khi create() return, nhưng Holder giữ payload qua private field.

## 21. Logical memory leak trong ngôn ngữ có GC

Một object được GC giữ đúng cách khi còn strong paths, nhưng ứng dụng có thể giữ **quá lâu so với nhu cầu**. Ví dụ static Map giữ UserSession sau khi user logout; GC không thể reclaim graph vẫn được map giữ.

Các nguồn:
- Unbounded static Map/List cache không eviction.
- Listeners không unregister.
- ThreadLocal per-request values trong pooled threads không remove.
- Lambda giữ controller/context graph quá lớn.
- Queued tasks giữ payload và results.
- Cyclic graph vẫn có root path từ static registry.
- Strong values trong WeakHashMap giữ keys ngược lại.
- Long-lived application singleton chứa request-scoped fields.

Các giải pháp thường đúng:
- Remove/evict expired entries; bounded cache + TTL.
- Trả và đóng subscription handles.
- `ThreadLocal.remove()` trong `finally`.
- Shutdown/cancel executors đúng lifecycle.
- Không capture objects không cần.
- Sử dụng heap dump/retaining paths để xác định ai giữ object.
- Không “chữa leak” bằng `System.gc()` nếu graph vẫn strongly reachable.

### 21.1. Chương trình 17 — static registry giữ Session qua method return

Lưu **`RegistryRetentionDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RegistryRetentionDemo {
    static class Session {
        final String id;

        Session(String id) {
            this.id = id;
        }
    }

    static class Registry {
        private static final Map<String, Session> SESSIONS =
                new HashMap<>();

        static void keep(Session session) {
            SESSIONS.put(session.id, session);
        }

        static Session find(String id) {
            return SESSIONS.get(id);
        }

        static void remove(String id) {
            SESSIONS.remove(id);
        }

        static int size() {
            return SESSIONS.size();
        }
    }

    static void register() {
        Session local = new Session("S1");
        Registry.keep(local);
    }

    public static void main(String[] args) {
        register();

        System.out.println("size after add=" + Registry.size());
        System.out.println("found=" + Registry.find("S1").id);

        Registry.remove("S1");
        System.out.println("size after remove=" + Registry.size());
        System.out.println("lookup now=" +
                (Registry.find("S1") == null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RegistryRetentionDemo.java
java RegistryRetentionDemo
~~~

Stdout:

~~~text
size after add=1
found=S1
size after remove=0
lookup now=true
~~~

Session local trong register() đã hết scope trước println, nhưng static registry vẫn giữ reference. Sau remove, registry bỏ reference của nó, **không khẳng định GC đã reclaimed Session**.

## 22. Chương trình không dùng local cũng có object semantics

~~~java
System.out.println(new StringBuilder("hello").length());
~~~

Không có named local reference tới StringBuilder, nhưng expression có semantics của Java object. JIT có thể scalar-replace/escape-analyze và tránh allocation vật lý khi hợp lệ; cũng không có guarantee reclaimed ngay sau `;`.

**Quan trọng:** Java source abstraction và optimized runtime representation không nhất thiết ánh xạ một-một với từng heap allocation vật lý.

## 23. Statement reachability là khái niệm khác hoàn toàn

Java compile-time analysis cũng dùng chữ **unreachable statement** (JLS `14.22):

~~~java
static void f() {
    return;
    // System.out.println("never"); // Nếu bỏ comment: unreachable.
}
~~~

Đây là control-flow reachability của statement, **không phải** object reachability từ GC roots. Không dùng lỗi unreachable statement để suy object đã bị thu gom.

Tương tự, biến bị shadowing hoặc field private không nói về GC. Một String immutable cũng không tự làm object strongly reachable lâu hơn; string literals/interning có sharing behavior riêng và không đại diện tốt cho mọi object identities.

## 24. Đối chiếu tình huống

| Tình huống | Về biến/scope | Về object reachability | Có biết GC đã chạy? |
| --- | --- | --- | --- |
| Local trong block rồi `}` | Tên hết lexical scope | Có thể còn alias/field/return | **Không** |
| `b=a; a=null` | a đổi reference | b vẫn có thể giữ object | Không |
| Method `return local` | local không nằm trong caller scope | caller giữ reference | Không |
| `holder.field=local` | local có thể hết scope | reachable holder giữ object | Không |
| `list.add(local)` | local có thể hết scope | list element giữ reference | Không |
| `staticField=local` | local có thể hết scope | static path có thể giữ lâu | Không |
| Lambda capture local | tên hết scope | callback giữ captured value | Không |
| `local=null` | tên có thể vẫn thuộc scope | tùy aliases và future uses | Không |
| Cycle A→B→A, không root path | không quyết định | cycle có thể unreachable | Không |
| WeakReference only | không liên quan tên local | GC có thể clear | Không |
| Last use trước `}` | tên vẫn trong scope | JVM có thể giảm liveness | Không |
| `try-with-resources` hết block | local ra scope | wrapper có thể vẫn sống | **close()** theo control flow |

## 25. Bảng lỗi hay gặp

| Diễn giải sai | Điều đúng |
| --- | --- |
| “Ra khỏi scope ⇒ object bị hủy ngay.” | Lexical name hết scope; object có thể còn references hoặc chưa GC. |
| “Reference variable chính là object.” | Variable giữ reference value, object là entity khác. |
| “Gán null xóa toàn bộ objects.” | Chỉ đổi một reference; aliases khác vẫn còn. |
| “Method return ⇒ mọi object của method đều chết.” | Return/fields/collections/callbacks có thể giữ object. |
| “Có tên local trong scope ⇒ GC phải giữ referent đến dấu }.” | JIT có thể rút liveness theo last use. |
| “Mỗi static field tuyệt đối sống đến lúc JVM exit.” | Classloader/class unloading có thể ảnh hưởng. |
| “Private fields không giữ object vì caller không nhìn thấy.” | Java source accessibility không phải reachability. |
| “Reference cycles chắc chắn không được GC.” | Unreachable cycles vẫn collectible. |
| “System.gc() buộc weak reference null.” | Không có timing guarantee. |
| “Finalizer dùng để đo GC/đóng file đúng lúc.” | Finalization deprecated và không đáng tin. |
| “Listener tạo local sẽ tự mất sau registration.” | Registry có thể giữ callback/captured data. |
| “Close resource tương đương heap object bị reclaimed.” | Resource lifecycle khác GC. |
| “Unreachable statement là object unreachable.” | Compile-time control flow khác runtime GC. |
| “Final làm referent immutable và immortal.” | Final chỉ hạn chế reassign field/variable. |

## 26. Quy trình phân tích reachability

Với bất kỳ đoạn code có `new` và nhiều assignments:

1. Xác định **object** cụ thể được tạo.
2. Xác định các **variables** giữ references, không nhầm biến với object.
3. Theo dõi aliases và reassignments.
4. Kiểm tra values trả về từ methods và references của caller.
5. Kiểm tra owner fields, arrays, lists, maps và nested object graphs.
6. Kiểm tra static registries, caches và classloader/lifecycle.
7. Kiểm tra lambdas, inner classes, listeners, tasks, futures và live threads.
8. Tìm root path và các edges; đừng chỉ tìm local variable name.
9. Phân biệt references đã clear với các paths còn lại.
10. Cân nhắc *last use* / JVM optimization, không coi lexical end là GC event.
11. Với WeakReference, không dự đoán thời điểm clear.
12. Với external resources, dùng close/try-with-resources.
13. Nếu điều tra leak, dùng heap dump/retaining paths/dominator analysis có kiểm soát.
14. Viết tests kiểm tra deterministic alias/field/collection semantics thay vì GC timing.

## 27. Chương trình 18 — contract tests không phụ thuộc GC

Lưu **`ReachabilityContractTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ReachabilityContractTest {
    static class Item {
        final String id;

        Item(String id) {
            this.id = id;
        }
    }

    static class Holder {
        Item item;
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static Holder make() {
        Item local = new Item("A");
        Holder holder = new Holder();
        holder.item = local;
        return holder;
    }

    public static void main(String[] args) {
        Holder holder = make();

        check("A".equals(holder.item.id),
                "local object retained in field");

        List<Item> list = new ArrayList<>();
        list.add(holder.item);

        Item alias = holder.item;
        holder.item = null;

        check(list.get(0) == alias, "alias identity");

        list.clear();
        check(list.isEmpty(), "list cleared");
        check("A".equals(alias.id), "alias accessible");

        System.out.println("reachability semantics checks passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ReachabilityContractTest.java
java ReachabilityContractTest
~~~

Stdout:

~~~text
reachability semantics checks passed
~~~

Check helper tự chạy, không phụ thuộc `assert` bị tắt mặc định khi không có `-ea`. Test không cần GC và chỉ xác nhận Java alias/reference semantics.

## 28. Bài tập và đáp án

**Câu 1.** Khi local reference ra khỏi scope, điều gì chắc chắn?  
**Đáp án:** Tên local không được dùng ngoài scope. Không biết object đã GC chưa.

**Câu 2.** `Object b=a; a=null;` khiến referent cũ chết chưa?  
**Đáp án:** Chưa; b vẫn giữ reference.

**Câu 3.** Method `return local;` thì caller dùng object được không?  
**Đáp án:** Được qua reference được return.

**Câu 4.** `private Object payload` có làm payload không reachable với GC không?  
**Đáp án:** Không; access control độc lập với reference paths.

**Câu 5.** `list.clear()` có xóa objects khỏi heap ngay không?  
**Đáp án:** Không, chỉ bỏ elements khỏi List; còn aliases/GC timing.

**Câu 6.** `static Map` có thể giữ sessions quá lâu không?  
**Đáp án:** Có; cần eviction/removal theo lifecycle.

**Câu 7.** Java có bắt mọi cycles A↔B sống mãi không?  
**Đáp án:** Không; cycles unreachable từ roots có thể reclaimed.

**Câu 8.** `System.gc()` có bảo đảm WeakReference trả null?  
**Đáp án:** Không.

**Câu 9.** Local vẫn trong scope mà không còn future use thì liveness có thể kết thúc sớm không?  
**Đáp án:** Có, JVM/JIT có thể tối ưu theo JLS.

**Câu 10.** `Reference.reachabilityFence` dùng để làm gì?  
**Đáp án:** Giữ strong reachability tới program point cụ thể.

**Câu 11.** `try-with-resources` rời block có bắt GC chạy không?  
**Đáp án:** Không; Java gọi close theo control-flow rules.

**Câu 12.** Lambda được giữ sau block có thể truy cập captured object không?  
**Đáp án:** Có.

**Câu 13.** Gán parameter reference = null có làm caller variable null không?  
**Đáp án:** Không; Java pass-by-value.

**Câu 14.** `final StringBuilder b` có ngăn append không?  
**Đáp án:** Không, final giới hạn reassign reference.

**Câu 15.** Chương trình không khai local name cho `new Object()` thì object semantics có tồn tại không?  
**Đáp án:** Có; JVM có thể tối ưu physical allocation nhưng phải bảo toàn behavior.

**Câu 16.** “Unreachable statement” có nghĩa object đã GC?  
**Đáp án:** Không; statement reachability là compile-time analysis.

**Câu 17.** Có thể nêu dòng source chính xác mà object bị reclaimed không?  
**Đáp án:** Không có guarantee chung như vậy.

**Câu 18.** Khi memory leak do static registry, nên làm gì?  
**Đáp án:** Xác định retaining paths và giải phóng entries theo lifecycle; GC không thể thu object còn strong path.

## 29. Checklist kiến thức và code review

- [ ] Biết tách variable name scope và heap object reachability?
- [ ] Biết aliases sau `x=null` vẫn có thể giữ object?
- [ ] Có xét return value, owner field, list, array và static map?
- [ ] Có xét lambda, listener, inner class, queued task và live threads?
- [ ] Không coi lexical `}` là GC trigger?
- [ ] Không coi local vẫn trong scope là referent sống bắt buộc tới cuối block?
- [ ] Có hiểu JVM có thể rút liveness sau last use?
- [ ] Không dùng finalizer/System.gc cho deterministic tests?
- [ ] Có hiểu WeakReference clear timing không được bảo đảm?
- [ ] Có nhận diện unreachable cycles?
- [ ] Phân biệt private/final modifiers với strong reference retention?
- [ ] Phân biệt resource close với heap reclamation?
- [ ] Khi cache/listener hết lifecycle đã remove/unsubscribe chưa?
- [ ] Có kiểm tra ThreadLocal cleanup trong pooled threads?
- [ ] Có giới hạn kích thước/lifetime của static cache?
- [ ] Có dùng heap profiler khi cần đo retaining path?
- [ ] Các demos có compile đúng Java 17+ và stdout deterministic?
- [ ] Đã tránh đưa ra lời khẳng định về thời điểm GC không có trong Java spec?

## 30. Tài liệu tham khảo

- [Java Language Specification SE 17, `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): lexical scope của declarations/locals.
- [JLS SE 17, `14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4): local declarations và rules.
- [JLS SE 17, `12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): tạo object instances.
- [JLS SE 17, `12.6.1 — Implementing Finalization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6.1): object reachability và compiler optimizations có thể rút liveness của references.
- [JLS SE 17, `14.22 — Unreachable Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.22): statement reachability không phải GC reachability.
- [Java SE 17 java.lang.ref Package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html): weak/soft/phantom references.
- [Java SE 17 Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): explicit strong reachability to point.
- [Java SE 17 WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability và get().
- [Java SE 17 System.gc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()): explicit collection request limitations.
- [Java SE 17 AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): resource cleanup.
- [JLS SE 17, `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): resource lifecycle.
- [Oracle JDK 17 GC Tuning — Other Considerations](https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html): reachability/finalization/explicit GC concerns.

## Kết luận

**Phạm vi biến** là quy tắc về tên trong source code. **Reachability của object** là quan hệ runtime: những đường references nào từ continuing computations/roots còn cho phép truy cập object.

Một biến local ra khỏi scope **không** làm đối tượng bị hủy ngay: return values, fields, collections, callbacks, threads và static registries có thể giữ object. Ngược lại, một tên local còn trong scope **không** bắt JVM giữ referent đến cuối block nếu nó không còn cần cho future use và tối ưu hóa hợp lệ rút ngắn liveness.

Đừng kết luận object đã GC khi gán null, ra khỏi method hay gọi System.gc. Nếu object không còn strong paths, nó **có thể** được collector xử lý vào thời điểm không xác định. Với logical retention, hãy giải quyết bằng **reference ownership và lifecycle** (`remove`, `unsubscribe`, bounded cache, `close`); với kiểm thử, hãy kiểm tra **Java reference semantics deterministic**, không kiểm tra GC timing.
