# Tham chiếu ngầm tới đối tượng bao ngoài và nguy cơ giữ bộ nhớ trong Java

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **enclosing instance** của một non-static member inner class và cách `outer.new Inner()` gắn một Inner object với một Outer object cụ thể.
- Phân biệt **inner class**, **static nested class**, anonymous/local class và lambda về nhu cầu tham chiếu outer/captured state.
- Hiểu **reachability** của Java GC: object chỉ có thể được thu gom khi không còn reachable từ GC roots theo các quy tắc JVM; một listener/callback/task sống lâu có thể làm outer object sống lâu ngoài dự kiến.
- Đọc sơ đồ reference path: `GC root → registry → callback/inner → enclosing Outer → fields/payload` và xác định **ai đang giữ reference**, không chỉ tìm nơi đã viết `new`.
- Biết khi nào `Outer.this` hoặc truy cập instance field của Outer thực sự đòi giữ outer reference; không nhầm với việc truy cập static fields.
- Nắm chi tiết phiên bản: `javac` JDK 17 có thể sinh synthetic `this$0`, nhưng từ JDK 18 compiler có tối ưu bỏ field này khi inner class **không dùng** enclosing instance; bytecode layout không phải API guarantee.
- Phân biệt **memory leak theo nghĩa ứng dụng** với GC không hoạt động: objects vẫn reachable nên GC giữ chúng là hành vi đúng, dù ứng dụng không còn muốn sử dụng.
- Thiết kế listener lifecycle với `register`/`unregister`, `AutoCloseable` subscription, task cancellation/queue cleanup, giới hạn cache và listener ownership.
- Dùng **static nested class**/top-level class với immutable snapshot dữ liệu cần thiết để giảm khả năng kéo dài lifetime Outer; hiểu static nested vẫn có thể giữ Outer nếu bạn chủ động đặt field Outer.
- Thảo luận `WeakReference`/weak listeners/`WeakHashMap` đúng giới hạn, không đoán chắc GC từ `System.gc()` hay thời điểm object được thu gom.
- Kiểm tra nguy cơ retention bằng deterministic behavioral tests và heap snapshots/dominator/reference chains; không giả lập kết quả GC không được JVM bảo đảm.
- Viết và chạy các ví dụ Java 17+ độc lập, kết quả stdout xác định.

## 1. Enclosing instance là gì?

Hai khai báo thường gặp trong một lớp bao ngoài:

~~~java
class Outer {
    static class Nested {
    }

    class Inner {
    }
}
~~~

- `Nested` là **static nested member class**: object Nested không có enclosing Outer instance ngầm.
- `Inner` là **non-static member inner class**: việc tạo Inner từ một Outer instance gắn Inner với một **immediately enclosing instance** theo Java language semantics.

Từ bên ngoài Outer:

~~~java
Outer.Nested nested = new Outer.Nested();

Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

`Outer.Inner` là **tên kiểu**. `outer.new Inner()` là **biểu thức tạo instance với qualifier**. Qualifier `outer` cung cấp enclosing instance, không phải constructor argument tường minh do bạn khai báo trong danh sách tham số của Inner.

### 1.1. Liên kết đó có ích gì?

Bên trong Inner method, `this` chỉ chính Inner; `Outer.this` chỉ Outer instance đã gắn với Inner:

~~~java
class Outer {
    private final String id = "A";

    class Inner {
        String ownerId() {
            return Outer.this.id;
        }
    }
}
~~~

Inner có thể đọc private outer field `id` theo quy tắc Java nested-class access. Nếu outer state mutable, Inner có thể nhìn thấy state mới, không nhận bản copy mặc định của field Outer.

### 1.2. Một Inner khác một Outer

Một Outer có thể tạo nhiều Inner objects. Hai Outer objects có thể tạo Inner objects của **cùng kiểu `Outer.Inner`** nhưng liên kết với hai enclosing instances khác nhau. Outer không tự clone mỗi khi tạo Inner.

~~~text
Inner A --------------------+
                            |
                            v
                         Outer 1
                            ^
                            |
Inner B --------------------+

Inner C --------------------> Outer 2
~~~

Khi thiết kế memory ownership, hãy xem rõ Inner đang trỏ tới Outer nào và ai đang trỏ tới Inner.

## 2. Chương trình: kiểm chứng enclosing instance bằng hành vi

Lưu **`EnclosingLinkDemo.java`**:

~~~java
public class EnclosingLinkDemo {
    static final class Outer {
        private final String id;

        Outer(String id) {
            this.id = id;
        }

        class Inner {
            String ownerId() {
                return Outer.this.id;
            }

            boolean belongsTo(Outer candidate) {
                return Outer.this == candidate;
            }
        }
    }

    public static void main(String[] args) {
        Outer first = new Outer("A");
        Outer second = new Outer("B");

        Outer.Inner a = first.new Inner();
        Outer.Inner b = second.new Inner();

        System.out.println("a owner=" + a.ownerId());
        System.out.println("b owner=" + b.ownerId());
        System.out.println("a with first=" + a.belongsTo(first));
        System.out.println("a with second=" + a.belongsTo(second));
        System.out.println("b with second=" + b.belongsTo(second));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac EnclosingLinkDemo.java
java EnclosingLinkDemo
~~~

**Stdout:**

~~~text
a owner=A
b owner=B
a with first=true
a with second=false
b with second=true
~~~

Đây là kiểm chứng **ngữ nghĩa** chứ không đoán tên synthetic field trong bytecode. `Outer.this == candidate` so **reference identity** của enclosing Outer instance.

Một biến outer ở phía caller có thể được gán lại reference khác sau khi đã tạo Inner; Inner cũ vẫn gắn với object Outer **đã dùng khi tạo nó**.

## 3. Java GC dựa vào reachability, không dựa vào “biến còn tên hay không”

Garbage collector không quyết định object nào “hết giá trị nghiệp vụ”. Nó tìm các objects còn reachable từ **GC roots** (chẳng hạn live thread stacks, static roots, JVM runtime references, tùy loại root/implementation) theo một mô hình thu gom nhất định.

Ví dụ:

~~~text
GC root
   |
   v
static listener registry
   |
   v
inner listener object
   |
   v
enclosing Outer object
   |
   v
large byte[] / tree / cache / other fields
~~~

Nếu đường tham chiếu mạnh (**strong reference path**) còn tồn tại, outer có thể không được thu gom, và các object mà outer tham chiếu cũng có thể được giữ theo.

### 3.1. Khái niệm “memory leak” của ứng dụng

Trong Java, một **memory leak theo nghĩa ứng dụng** thường là tình trạng object không còn được business logic cần đến nhưng vẫn **reachable** do collection, listener, static cache, pending task hoặc owner khác giữ tham chiếu.

GC không “sai” khi giữ object đó: từ quan điểm reference graph, nó vẫn reachable.

### 3.2. Reference path quan trọng hơn số vòng tham chiếu

Nếu:

~~~text
Outer -> Inner -> Outer
~~~

nhưng **không còn đường nào từ GC roots đi tới cả hai**, một collector hỗ trợ GC thông thường vẫn có thể thu gom cả chu trình. Java GC không phải reference-counting thuần túy khiến mọi cycle tự động rò rỉ.

Đường đáng lo là:

~~~text
static registry (root) -> Inner -> Outer
~~~

Lúc đó **có root bên ngoài chu trình**, và cleanup registry có thể là bước cần thiết để cắt reference path.

### 3.3. Không thể chứng minh GC bằng một lần chạy ngắn

`System.gc()` chỉ là một lời yêu cầu/gợi ý đến JVM. Không được suy ra “gọi xong chắc chắn object đã thu gom”; thời điểm thu gom, collector và tối ưu JVM là những yếu tố ngoài output deterministic của ví dụ Java.

Các chương trình trong bài sẽ **kiểm tra đường tham chiếu, số callback còn đăng ký và behavior**, không in kết luận “GC đã chạy” không đáng tin.

## 4. Inner listener có thể kéo dài lifetime của Outer

Một tình huống điển hình:

1. Màn hình/view/controller Outer tạo một inner listener.
2. Listener được đăng ký vào EventBus tồn tại lâu hơn màn hình.
3. Người dùng đóng màn hình, code không còn lưu biến Outer local.
4. EventBus vẫn giữ strong reference tới listener.
5. Listener sử dụng `Outer.this`/instance state, nên đường reference tới Outer còn tồn tại.
6. Outer và các fields mà nó giữ có thể sống lâu ngoài ý định.

Điều này xảy ra **không cần thread hay lỗi GC**.

### 4.1. Demo registry làm Outer còn có thể truy cập

Lưu **`ListenerRetentionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerRetentionDemo {
    static final class EventBus {
        private final List<Runnable> callbacks = new ArrayList<>();

        void add(Runnable callback) {
            callbacks.add(callback);
        }

        void remove(Runnable callback) {
            callbacks.remove(callback);
        }

        int size() {
            return callbacks.size();
        }

        void fire() {
            for (Runnable callback : callbacks) {
                callback.run();
            }
        }
    }

    static final class Screen {
        private final String name;
        private final byte[] data = new byte[1024];

        Screen(String name) {
            this.name = name;
        }

        class ClickHandler implements Runnable {
            @Override
            public void run() {
                System.out.println("click " + Screen.this.name
                        + ",bytes=" + Screen.this.data.length);
            }
        }

        ClickHandler attach(EventBus bus) {
            ClickHandler listener = new ClickHandler();
            bus.add(listener);
            return listener;
        }
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();

        Screen screen = new Screen("Home");
        Runnable registered = screen.attach(bus);

        screen = null; // Chỉ bỏ reference local.
        System.out.println("registered=" + bus.size());
        bus.fire();

        bus.remove(registered);
        registered = null;
        System.out.println("after remove=" + bus.size());
    }
}
~~~

Chạy:

~~~bash
javac ListenerRetentionDemo.java
java ListenerRetentionDemo
~~~

Stdout:

~~~text
registered=1
click Home,bytes=1024
after remove=0
~~~

**Phân tích:**

- `screen = null` chỉ bỏ **một** reference local, không buộc Screen được thu gom.
- `bus` còn giữ listener, listener phải truy cập `Screen.this.name` và `Screen.this.data`, vì vậy Screen vẫn có thể được truy cập qua đường này.
- `bus.fire()` chứng minh callback còn hoạt động sau khi bỏ local screen reference; không cần kích hoạt GC.
- `bus.remove(registered)` loại callback khỏi bus trong ví dụ. Sau đó còn phải xem toàn bộ reference paths khác: không được khẳng định Screen **chắc chắn** được GC ngay.
- `data` chỉ là payload nhỏ minh họa. Nếu screen còn giữ graph lớn, một listener có thể giữ cả graph ấy reachable.

**Thông điệp:** Inner listener không phải bản sao chỉ chứa String name; nó có thể cần liên kết với chính Screen object.

## 5. Tại sao lưu một Inner ở nơi “sống lâu” nguy hiểm hơn?

`Inner` không tự động gây leak. Cùng logic có thể được dùng an toàn khi lifetime của callback **ngắn hơn hoặc bằng** lifetime cần thiết của Outer.

Nguy cơ tăng khi Inner được lưu trong:

- Static `List`/`Map`/registry không được dọn.
- EventBus singleton.
- Scheduled tasks, timer callbacks hoặc executor queues.
- Long-lived Swing/JavaFX/web listener registries.
- Observer/callback lists do service sống lâu quản lý.
- Global cache, retained diagnostics hooks hoặc debug registries.
- Reactive subscriptions không được dispose.
- Thread-local data của thread sống lâu, nếu chứa inner/owner reference.

Đừng chỉ hỏi “Inner được tạo ở method nào?”. Hãy hỏi **nơi nào còn đang giữ reference tới Inner, và bao lâu**.

## 6. Chương trình: static field registry là một GC root path

Lưu **`StaticRegistryPathDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StaticRegistryPathDemo {
    private static final List<Runnable> TASKS = new ArrayList<>();

    static final class Owner {
        private final String id;

        Owner(String id) {
            this.id = id;
        }

        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println("task for " + Owner.this.id);
            }
        }

        void register() {
            TASKS.add(new Task());
        }
    }

    public static void main(String[] args) {
        Owner owner = new Owner("A");
        owner.register();
        owner = null;

        System.out.println("queued=" + TASKS.size());
        TASKS.get(0).run();

        TASKS.clear();
        System.out.println("after clear=" + TASKS.size());
    }
}
~~~

Chạy:

~~~bash
javac StaticRegistryPathDemo.java
java StaticRegistryPathDemo
~~~

Output:

~~~text
queued=1
task for A
after clear=0
~~~

Đường đáng chú ý:

~~~text
StaticRegistryPathDemo.TASKS
            |
            v
         Owner.Task
            |
            v
         Owner("A")
~~~

`TASKS.clear()` cắt **đường từ list này** tới Task. Nếu một nơi khác còn giữ Task hoặc Owner, các objects vẫn reachable. Vì vậy chương trình **không** in “owner collected”.

### 6.1. Liên quan class unloading và static fields

Nói giản lược “static field luôn sống vĩnh viễn” cũng không chính xác: classloader/classes có lifecycle riêng. Nhưng trong một ứng dụng mà class và registry vẫn sống lâu, static collection thường là nguồn retention quan trọng.

## 7. Cách giảm coupling: static nested class với dữ liệu cần thiết

Nếu callback chỉ cần một immutable ID hoặc một vài thông tin nhỏ, có thể tạo một **static nested listener** thay vì non-static Inner.

~~~java
class Screen {
    private final String id;

    static class Callback implements Runnable {
        private final String idSnapshot;

        Callback(String idSnapshot) {
            this.idSnapshot = idSnapshot;
        }

        @Override
        public void run() {
            System.out.println(idSnapshot);
        }
    }
}
~~~

`Callback` không tự có `Screen.this`. Nếu constructor nhận chỉ String immutable, callback lưu ID snapshot, không cần giữ Screen.

**Nhưng:** static nested class **vẫn có thể giữ Screen** nếu bạn tự khai báo `private final Screen owner;` hoặc closure/field khác chứa owner. Từ khóa static chỉ loại bỏ **enclosing instance tự động**, không phải một “công cụ chống leak tuyệt đối”.

## 8. Chương trình: static nested callback không cần Outer object

Lưu **`StaticNestedCallbackDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StaticNestedCallbackDemo {
    static final class Registry {
        private final List<Runnable> actions = new ArrayList<>();

        void register(Runnable action) {
            actions.add(action);
        }

        void fire() {
            for (Runnable action : actions) {
                action.run();
            }
        }
    }

    static final class Screen {
        private final String id;

        Screen(String id) {
            this.id = id;
        }

        static final class Callback implements Runnable {
            private final String id;

            Callback(String id) {
                this.id = id;
            }

            @Override
            public void run() {
                System.out.println("screen id=" + id);
            }
        }

        Runnable createCallback() {
            return new Callback(id);
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();
        Screen screen = new Screen("Home");

        registry.register(screen.createCallback());
        screen = null;

        registry.fire();
    }
}
~~~

Chạy:

~~~bash
javac StaticNestedCallbackDemo.java
java StaticNestedCallbackDemo
~~~

Output:

~~~text
screen id=Home
~~~

Callback có đúng một field `String id` để thực hiện behavior, không chứa một field Screen explicit và không có `Screen.this` implicit theo ngữ nghĩa static nested class.

**Không đưa ra kết luận về thời điểm GC:** kết quả chỉ chứng minh callback **không cần Screen instance** để chạy. Memory retention thực tế phải xem toàn bộ reference paths.

### 8.1. Khi nào giữ Outer reference explicit vẫn hợp lý?

Nếu callback cần thao tác live state của Screen, việc truyền/giữ Screen explicit có thể đúng. Khi đó hãy **giới hạn lifetime** và cung cấp cơ chế unregister/dispose. Static nested không thể thay thế domain relationship nếu callback thực sự cần một owner đang sống.

## 9. Thay Inner bằng static nested chưa đủ khi field vẫn giữ owner

Một sửa chữa chưa triệt để:

~~~java
class Screen {
    static class Callback implements Runnable {
        private final Screen owner;

        Callback(Screen owner) {
            this.owner = owner;
        }

        @Override
        public void run() {
            owner.refresh();
        }
    }

    void refresh() {
    }
}
~~~

Đây là mảnh minh họa có thể compile nếu đặt trong một file đầy đủ phù hợp. Vì Callback lưu `owner` mạnh, registry giữ Callback vẫn có thể kéo dài lifetime Screen.

Phân biệt hai đường:

~~~text
Inner handler:  registry -> inner -> enclosing Screen
Nested handler: registry -> nested -> explicit owner Screen
~~~

**Chọn static nested class vì helper không cần outer**; nếu cần outer, giải quyết chủ yếu bằng **lifecycle/registration ownership**, không phải chỉ sửa modifier.

## 10. Giải pháp nền tảng: đối xứng register và unregister

Một listener API cần có quy tắc:

1. Register ở thời điểm component bắt đầu cần sự kiện.
2. Giữ đúng **cùng listener instance** hoặc registration token để unregister.
3. Unregister khi component ngừng cần sự kiện (close/dispose/unmount/stop).
4. Nếu sự kiện có thể chạy đồng thời, xác định race giữa remove và callback đang thực thi.
5. Test rằng registry không còn subscription sau cleanup.
6. Không giả định `remove(new Listener())` loại được listener cũ nếu equality/identity không phù hợp.

Nhiều frameworks cung cấp `Subscription`, `Disposable`, `Registration` hoặc `AutoCloseable` token. Chúng giúp ownership rõ hơn là đưa nguyên callback vào static list rồi không lưu phương tiện loại bỏ.

### 10.1. Vì sao callback identity quan trọng?

Nếu registry lưu `Runnable listener = owner.new Handler();`, nên lưu reference đó đến khi unsubscribe. Gọi `owner.new Handler()` lần nữa tạo instance khác; nó **không tự equal** callback ban đầu theo `Object.equals`, nên thường không remove được entry gốc.

Một registration token rõ ràng giảm rủi ro này.

## 11. Chương trình: đăng ký với `AutoCloseable` subscription

Lưu **`SubscriptionLifecycleDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class SubscriptionLifecycleDemo {
    static final class Bus {
        private final Map<Integer, Runnable> listeners =
                new LinkedHashMap<>();
        private int nextId;

        Subscription subscribe(Runnable listener) {
            int id = ++nextId;
            listeners.put(id, listener);
            return new Subscription(this, id);
        }

        private void remove(int id) {
            listeners.remove(id);
        }

        int size() {
            return listeners.size();
        }

        void fire() {
            for (Runnable listener : listeners.values()) {
                listener.run();
            }
        }
    }

    static final class Subscription implements AutoCloseable {
        private final Bus bus;
        private final int id;
        private boolean closed;

        Subscription(Bus bus, int id) {
            this.bus = bus;
            this.id = id;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                bus.remove(id);
            }
        }
    }

    static final class View {
        private final String name;

        View(String name) {
            this.name = name;
        }

        class Listener implements Runnable {
            @Override
            public void run() {
                System.out.println("event for " + View.this.name);
            }
        }

        Subscription attach(Bus bus) {
            return bus.subscribe(new Listener());
        }
    }

    public static void main(String[] args) {
        Bus bus = new Bus();
        View view = new View("Settings");

        try (Subscription ignored = view.attach(bus)) {
            System.out.println("inside size=" + bus.size());
            bus.fire();
        }

        System.out.println("outside size=" + bus.size());
        bus.fire();
    }
}
~~~

Chạy:

~~~bash
javac SubscriptionLifecycleDemo.java
java SubscriptionLifecycleDemo
~~~

Output:

~~~text
inside size=1
event for Settings
outside size=0
~~~

**Phân tích:**

- Bus giữ listener trong map, listener truy cập `View.this.name` nên View nằm trên đường tham chiếu.
- `try-with-resources` gọi `close()` khi rời block; close remove đúng subscription ID, không cần tạo listener mới.
- Sau `close`, `bus.size()` bằng 0; `bus.fire()` không gọi listener nữa.
- `close()` idempotent trong ví dụ: gọi lặp không gây side effect mới.
- Đây là ví dụ **đơn luồng**. Trong production, Bus có thể phải đồng bộ register/remove/fire, xử lý callback đang chạy và exception safety.

**Lưu ý thực tế:** đôi khi lifetime của component không trùng lexical scope của `try-with-resources`. Có thể giữ `Subscription` trong field và gọi `close` ở `dispose()/onStop()` theo framework lifecycle.

## 12. Anonymous inner class cũng có thể giữ Outer

Một anonymous class được tạo bên trong instance method có thể dùng members của enclosing object. Ví dụ:

~~~java
class Screen {
    private final String id = "A";

    Runnable create() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(Screen.this.id);
            }
        };
    }
}
~~~

Callback ở đây truy cập `Screen.this.id`, nên có quan hệ tham chiếu ngữ nghĩa tới Screen. Nếu đưa callback vào long-lived registry mà không unregister, Screen có thể tiếp tục reachable.

Không nên tuyên bố **mọi anonymous class ở mọi context đều giữ Outer**. Anonymous class trong static context không có enclosing instance của class đang gọi, và compiler implementation cũng có thể tối ưu những references không dùng.

### 12.1. Local class tương tự khi truy cập Outer

~~~java
class Screen {
    private final String name = "Home";

    Runnable createLocal() {
        class LocalHandler implements Runnable {
            public void run() {
                System.out.println(Screen.this.name);
            }
        }
        return new LocalHandler();
    }
}
~~~

Local class không phải member type được tạo bằng `outer.new LocalHandler()` từ ngoài method. Nhưng nó vẫn có thể capture enclosing context/local values theo Java rules, dẫn tới retention nếu object được giữ lâu.

### 12.2. Giữ biến local qua closure

Local/anonymous classes chỉ dùng local variables nếu đáp ứng **final/effectively final** constraints. Nếu captured local reference trỏ một mutable, lớn object graph, callback giữ reference ấy có thể làm graph còn reachable, dù không cần Outer.

## 13. Chương trình: member inner, anonymous và local class

Lưu **`InnerVariantsCaptureDemo.java`**:

~~~java
public class InnerVariantsCaptureDemo {
    static final class Screen {
        private final String id;

        Screen(String id) {
            this.id = id;
        }

        class MemberHandler implements Runnable {
            @Override
            public void run() {
                System.out.println("member " + Screen.this.id);
            }
        }

        Runnable anonymous() {
            return new Runnable() {
                @Override
                public void run() {
                    System.out.println("anonymous "
                            + Screen.this.id);
                }
            };
        }

        Runnable local() {
            class LocalHandler implements Runnable {
                @Override
                public void run() {
                    System.out.println("local " + Screen.this.id);
                }
            }
            return new LocalHandler();
        }
    }

    public static void main(String[] args) {
        Screen owner = new Screen("A");

        Runnable member = owner.new MemberHandler();
        Runnable anonymous = owner.anonymous();
        Runnable local = owner.local();

        member.run();
        anonymous.run();
        local.run();
    }
}
~~~

Chạy:

~~~bash
javac InnerVariantsCaptureDemo.java
java InnerVariantsCaptureDemo
~~~

Output:

~~~text
member A
anonymous A
local A
~~~

Cả ba callbacks **thực sự đọc** `Screen.this.id`; nếu một long-lived object giữ callbacks, Screen có thể nằm trong retained reference graph. Ví dụ không dựa vào việc lớp nội bộ có field compiler sinh tên gì.

## 14. Lambda có “implicit outer reference” giống member inner không?

Lambda `() -> ...` không tạo một *named member inner class* với enclosing instance theo cùng cú pháp `outer.new Inner()`. Tuy nhiên, lambda **có thể capture `this`** hoặc reference khác nếu body dùng instance state.

Ví dụ:

~~~java
class Screen {
    private String status = "open";

    Runnable capturingOwner() {
        return () -> System.out.println(status);
    }
}
~~~

Lambda cần đọc `status` của Screen instance, nên retained lambda có thể giữ một path tới Screen.

Trái lại:

~~~java
Runnable withSnapshot() {
    String snapshot = status;
    return () -> System.out.println(snapshot);
}
~~~

Lambda thứ hai chỉ cần String snapshot được capture. Nếu String immutable và không có captured Screen reference nào khác, callback có thể chạy mà không cần Screen object. Cụ thể closure representation là chi tiết compiler/runtime; hãy reasoning từ **những references body cần sử dụng**, không dựa vào tên field tổng hợp.

### 14.1. Lambda `this` khác anonymous class `this`

- Bên trong lambda viết trong Screen instance context, `this` theo lexical meaning trỏ **Screen**.
- Bên trong anonymous class `new Runnable() { ... }`, `this` trỏ **anonymous Runnable object**; muốn Screen dùng `Screen.this`.

Đây là khác biệt ngữ nghĩa, không phải mẹo chống memory leak. Cả hai đều có thể giữ owner nếu sử dụng owner.

## 15. Chương trình: lambda giữ owner so với lambda chụp giá trị

Lưu **`LambdaCaptureRetentionDemo.java`**:

~~~java
public class LambdaCaptureRetentionDemo {
    static final class Screen {
        private String title;

        Screen(String title) {
            this.title = title;
        }

        Runnable live() {
            return () -> System.out.println("live=" + title);
        }

        Runnable snapshot() {
            String captured = title;
            return () -> System.out.println("snapshot=" + captured);
        }

        void rename(String next) {
            title = next;
        }
    }

    public static void main(String[] args) {
        Screen screen = new Screen("Before");

        Runnable live = screen.live();
        Runnable snapshot = screen.snapshot();

        screen.rename("After");

        live.run();
        snapshot.run();
    }
}
~~~

Chạy:

~~~bash
javac LambdaCaptureRetentionDemo.java
java LambdaCaptureRetentionDemo
~~~

Output:

~~~text
live=After
snapshot=Before
~~~

**Giải thích:**

- `live` đọc instance field qua Screen đang sống: vì thế thấy After.
- `snapshot` capture một String value/reference tương ứng thời điểm tạo callback và thấy Before.
- Cả hai đều có thể được lưu như `Runnable`; lựa chọn giữa live state và snapshot state ảnh hưởng mạnh tới retention/lifecycle.
- Không nên chụp mutable object thành local rồi gọi đó là immutable snapshot: reference tới mutable object vẫn shared.

### 15.1. Trường hợp callback chỉ dùng static member

Lambda/method dùng duy nhất static data có thể không cần giữ owner; không kết luận từ việc lambda được tạo **trong instance method** rằng nó chắc chắn capture `this`. Xem code thực sự tham chiếu đối tượng nào.

## 16. Method reference cũng có thể capture receiver

Biểu thức `this::onEvent` tạo callback gắn với receiver `this` hiện tại. Registry giữ callback có thể giữ receiver reachable. Tương tự `someObject::method` giữ object receiver cần để gọi method.

Ngược lại, static method reference `Logger::log` không cần một receiver instance, dù nó có thể cần tham số dữ liệu.

### 16.1. Chương trình runnable

Lưu **`MethodReferenceRetentionDemo.java`**:

~~~java
public class MethodReferenceRetentionDemo {
    static final class Screen {
        private final String id;

        Screen(String id) {
            this.id = id;
        }

        void onEvent() {
            System.out.println("event " + id);
        }

        Runnable boundCallback() {
            return this::onEvent;
        }
    }

    public static void main(String[] args) {
        Screen screen = new Screen("A");
        Runnable callback = screen.boundCallback();

        callback.run();
        screen = null;
        callback.run();
    }
}
~~~

Chạy:

~~~bash
javac MethodReferenceRetentionDemo.java
java MethodReferenceRetentionDemo
~~~

Output:

~~~text
event A
event A
~~~

`screen = null` không khiến callback mất receiver mà nó cần để gọi `onEvent`. Đây là một ví dụ rõ về retention **mà không cần viết class Inner thủ công**.

## 17. Tasks đang chờ có thể giữ owner, không chỉ listeners

Một task trong queue/executor/scheduler có thể giữ:

- Một inner Runnable cần `Outer.this`.
- Một lambda cần `this` hoặc object fields.
- Captured local references tới payload/object graph.
- Một method reference có receiver.

Khi task nằm trong long-lived queue, các objects được tham chiếu có thể tiếp tục reachable **cho đến khi task được chạy và được bỏ khỏi queue, hoặc cancellation/cleanup cắt path theo API**.

Đừng cho rằng chỉ “đã ngừng hiển thị UI” là mọi tasks liên quan đều bị hủy.

### 17.1. Ví dụ deterministic với queue tự quản

Lưu **`PendingTaskRetentionDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Queue;

public class PendingTaskRetentionDemo {
    static final class WorkQueue {
        private final Queue<Runnable> pending = new ArrayDeque<>();

        void enqueue(Runnable action) {
            pending.add(action);
        }

        void runOne() {
            pending.remove().run();
        }

        void clear() {
            pending.clear();
        }

        int size() {
            return pending.size();
        }
    }

    static final class Page {
        private final String id;

        Page(String id) {
            this.id = id;
        }

        Runnable action() {
            return () -> System.out.println("work for " + id);
        }
    }

    public static void main(String[] args) {
        WorkQueue queue = new WorkQueue();
        Page page = new Page("P1");

        queue.enqueue(page.action());
        page = null;

        System.out.println("pending=" + queue.size());
        queue.runOne();
        System.out.println("after run=" + queue.size());

        queue.enqueue(() -> System.out.println("never printed"));
        queue.clear();
        System.out.println("after clear=" + queue.size());
    }
}
~~~

Chạy:

~~~bash
javac PendingTaskRetentionDemo.java
java PendingTaskRetentionDemo
~~~

Output:

~~~text
pending=1
work for P1
after run=0
after clear=0
~~~

`runOne()` bỏ task khỏi queue trước khi gọi `run`, nên queue size trở về 0. `clear()` loại một task chưa chạy mà không gọi body của nó.

Trong scheduler thực, **cancelled task có bị loại khỏi queue ngay không** và callback đang chạy được xử lý ra sao phụ thuộc library/implementation; đọc hợp đồng API và dùng cleanup cần thiết. Đừng suy từ queue demo đơn giản ra một chính sách chung cho mọi executor.

## 18. Cắt đường tham chiếu: giải pháp theo từng điểm giữ

Một chiến lược sửa leak cần tìm **chủ thể giữ reference quá lâu**:

| Chủ thể giữ | Đường tham chiếu phổ biến | Hành động phù hợp |
| --- | --- | --- |
| EventBus singleton | bus → listener → owner | Unsubscribe khi owner dừng hoạt động |
| Static List/Map | static field → inner callback → outer | Remove/clear theo scope và eviction policy |
| Scheduler | scheduler queue → Runnable → screen | Cancel task đúng cách, bỏ pending references khi API hỗ trợ |
| Timer/Observer | timer → handler → owner | Stop/dispose observer/timer khi đóng owner |
| Cache | cache → key/value → owner | Giới hạn cache, remove/eviction, dùng keys/values vừa đủ |
| ThreadLocal | long-lived thread → ThreadLocal value → owner | Remove đúng lúc theo thread lifecycle |
| GUI component | parent registry → listener → owner | Gỡ listener khi component unmount/close |
| Explicit nested owner field | static nested → owner | Chỉ giữ field khi cần; clear/unregister khi xong |
| Lambda capturing this | registry → closure → this | Capture immutable snapshot nếu chỉ cần giá trị; hoặc unsubscribe |
| Method reference `this::handler` | registry → bound receiver | Unsubscribe và xét receiver lifetime |

**Không “sửa” chỉ bằng cách gán local variable bằng null** nếu registry còn giữ object. Cần cắt reference path ở **bên sở hữu lâu dài** hoặc thay data representation.

## 19. `WeakReference` có phải lời giải tự động?

`WeakReference<T>` cho phép tham chiếu **không duy trì strong reachability** của referent chỉ bằng weak reference. Nếu referent không còn strongly reachable, GC có thể clear reference; sau đó `get()` có thể trả null.

Nhưng:

- Không có bảo đảm **khi nào** GC chạy/clear weak reference.
- Nếu còn **một** strong reference path tới Outer từ registry/lambda/field khác, weak reference không làm object biến mất.
- Một weak listener có thể bị thu gom **quá sớm** nếu chẳng nơi nào giữ strong reference tới listener mà bạn vẫn muốn hoạt động.
- Dùng weak references không thay thế ownership/lifecycle documentation.
- Weak references không tự ngăn một callback chạy sau khi owner đã logic-dispose nếu race chưa được kiểm soát.
- Weak references có thể khiến debugging/phỏng đoán thứ tự sự kiện khó hơn.

Ưu tiên **unsubscribe/close đúng lifecycle** khi framework hỗ trợ. Dùng weak listener khi framework/library có semantics phù hợp và bạn thật sự muốn callback tự biến mất khi owner không còn được giữ mạnh.

### 19.1. Ví dụ thiết kế weak callback (snippet)

~~~java
final class WeakCallback implements Runnable {
    private final java.lang.ref.WeakReference<Screen> owner;

    WeakCallback(Screen screen) {
        owner = new java.lang.ref.WeakReference<>(screen);
    }

    @Override
    public void run() {
        Screen current = owner.get();
        if (current != null) {
            current.refresh();
        }
    }
}
~~~

Đây là **mảnh minh họa** yêu cầu một `Screen` class có `refresh()`. Nếu `owner.get()` trả Screen non-null, local `current` là một strong reference trong lúc callback sử dụng nó. Nếu trả null, callback bỏ qua tác vụ.

Không viết stdout “sau `System.gc` chắc chắn in null” vì GC thời điểm và khả năng thu gom không được đảm bảo.

## 20. `WeakHashMap` không giải quyết mọi retention path

`WeakHashMap<K,V>` giữ keys qua weak references, nhưng values thông thường được giữ mạnh. Nếu value lại tham chiếu mạnh tới key, bạn có thể tạo đường:

~~~text
WeakHashMap (root)
      |
      +-- strong value --> Value --> Key
      |
      +-- weak key ------> Key
~~~

Mặc dù map dùng weak keys, đường **value → key** có thể giữ key strongly reachable và entry không biến mất như kỳ vọng. Đây là lỗi thiết kế cache thường gặp.

Với inner callback làm value, nếu callback giữ reference tới outer key, tình huống này đặc biệt đáng chú ý. Phải xem toàn bộ reference graph, không chỉ kiểu của map.

### 20.1. Đừng dùng `System.gc()` làm acceptance test

Một test như:

~~~java
System.gc();
// assert weak.get() == null;
~~~

không đáng tin. GC invocation không bắt buộc loại referent ngay. Thay vì test thu gom trong unit tests thông thường, kiểm tra **unregister, clear, owner references không còn trong registry**, và dùng heap analysis khi nghi leak trên ứng dụng thực.

## 21. Quan sát bytecode: `this$0` là chi tiết compiler, không phải hợp đồng

Với `javac` JDK 17, member inner class thường có một **synthetic field** với tên như `this$0` để lưu enclosing Outer reference. Đây là chi tiết implementation của compiler, không phải field bạn nên đọc/ghi trực tiếp từ Java source.

**Chi tiết quan trọng theo phiên bản:**

- Theo Oracle JDK 18 release notes, **trước JDK 18**, `javac` thường phát sinh synthetic `this$...` field cho inner class ngay cả khi không dùng enclosing instance.
- **Từ JDK 18**, `javac` có thể **bỏ field không được sử dụng** khi inner không tham chiếu enclosing instance; constructor form vẫn tuân quy tắc inner creation.
- Khi inner **thực sự dùng** `Outer.this` hoặc instance state, cần giữ semantics liên kết ấy; không lấy tối ưu trường hợp “không dùng” để kết luận một callback thật sự đọc Outer cũng không giữ Outer.
- Các compiler/JVM khác có thể sinh bytecode khác. Không phụ thuộc reflection field name `this$0` cho business logic.

Điều này có nghĩa câu “**mọi** non-static inner object trên **mọi** JDK luôn giữ toàn bộ Outer đến khi GC” là **quá tuyệt đối**. Rủi ro giữ bộ nhớ là có thật, nhưng phải kiểm tra **đường tham chiếu thực tế và compiler/version**.

### 21.1. Cách tự quan sát mà không viết test mong một field cố định

Lưu **`BytecodeOuterLink.java`**:

~~~java
public class BytecodeOuterLink {
    private final String name = "Outer";

    class Used {
        String read() {
            return BytecodeOuterLink.this.name;
        }
    }

    class Unused {
        int value() {
            return 7;
        }
    }

    public static void main(String[] args) {
        BytecodeOuterLink owner = new BytecodeOuterLink();

        System.out.println(owner.new Used().read());
        System.out.println(owner.new Unused().value());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BytecodeOuterLink.java
java BytecodeOuterLink
~~~

Output:

~~~text
Outer
7
~~~

Sau đó có thể xem các fields/methods compiler phát sinh bằng JDK tool `javap`:

~~~bash
javap -p "BytecodeOuterLink$Used"
javap -p "BytecodeOuterLink$Unused"
~~~

Dấu ngoặc kép trong ví dụ phù hợp với nhiều command shells, nhưng trong shell có mở rộng ký tự `$` (như một số Bash contexts) bạn nên dùng **single quotes**:

~~~bash
javap -p 'BytecodeOuterLink$Used'
javap -p 'BytecodeOuterLink$Unused'
~~~

**Không có stdout cố định cho `javap` trong bài này**, vì bytecode layout tùy phiên bản/compiler. Hãy quan sát việc Used cần outer state và Unused không cần, rồi so với release notes của JDK đang chạy.

### 21.2. Cần xem source-level semantics trước field synthetic

Việc một field compiler-generated được tối ưu bỏ không làm cú pháp `owner.new Unused()` biến thành `new Outer.Unused()`. Member Inner vẫn là non-static class và creation expression vẫn cần đúng qualifier. Chỉ **representation/runtime retention** có thể khác khi enclosing reference thực sự không cần tới.

## 22. Method/field chỉ dùng static data không cần giữ Outer trong logic

Xét:

~~~java
class Outer {
    private static final int VERSION = 17;

    class Inner {
        int version() {
            return VERSION;
        }
    }
}
~~~

Inner source chỉ đọc static member; về mặt tính toán method không cần state của một Outer object cụ thể. Đây là một trường hợp mà tối ưu compiler có thể bỏ reference tới enclosing instance trên JVM/JDK phù hợp, như đã nêu.

Tuy vậy để diễn đạt ý định thiết kế **không cần outer**, khai báo **static nested class** thường rõ ràng hơn:

~~~java
class Outer {
    private static final int VERSION = 17;

    static class Nested {
        int version() {
            return VERSION;
        }
    }
}
~~~

Client có thể tạo `new Outer.Nested()` mà không cần tạo Outer trước. Điều này giảm coupling và tránh phụ thuộc tối ưu compiler.

## 23. Tác động của reference tới mảng lớn và object graph

Một Inner có thể chỉ đọc `Outer.this.id` nhỏ, nhưng khi Outer còn reachable, **những fields khác của Outer** vẫn có thể reachable, ví dụ:

- `byte[]` cho ảnh/cache/buffer.
- `List` chứa hàng nghìn objects.
- Graph của view models/DOM-like trees.
- Connections/handlers được lưu trong fields.
- Các object listeners khác và state của một screen/session.

Vì vậy giữ một reference tới **một Outer** có thể có *retained size* lớn hơn nhiều so với shallow size của Outer.

**Phân biệt hai đại lượng khi dùng heap analyzer:**

- *Shallow size*: bộ nhớ thuộc chính object.
- *Retained size*: tổng bộ nhớ sẽ có thể được giải phóng nếu object/dominator path được loại bỏ theo cách analyzer định nghĩa, tùy graph.

Không cộng máy móc sizes của fields rồi xem đó là retained size; shared objects có nhiều đường reference và dominator relationships cần phân tích.

## 24. Ví dụ: thay vì giữ cả Screen, chỉ giữ ID snapshot

Nếu callback chỉ cần đăng log ID khi sự kiện xảy ra:

**Dễ giữ owner không cần thiết:**

~~~java
class Screen {
    private final String id;

    Screen(String id) {
        this.id = id;
    }

    class LoggerHandler implements Runnable {
        public void run() {
            System.out.println(Screen.this.id);
        }
    }
}
~~~

**Rõ lifetime hơn:**

~~~java
class Screen {
    private final String id;

    Screen(String id) {
        this.id = id;
    }

    static final class LoggerHandler implements Runnable {
        private final String idSnapshot;

        LoggerHandler(String idSnapshot) {
            this.idSnapshot = idSnapshot;
        }

        public void run() {
            System.out.println(idSnapshot);
        }
    }

    Runnable newLogger() {
        return new LoggerHandler(id);
    }
}
~~~

Cả hai mảnh là **class snippets**, được trình bày riêng và không dùng chung một file. Trong phiên bản static nested, callback chỉ chứa String ID immutable, không có path tới Screen nếu không có reference khác được truyền/giữ.

**Không áp dụng mẹo này** khi callback cần cập nhật Screen live. Lúc đó cần giữ owner hợp lệ và quản lý lifecycle đăng ký.

## 25. Weak-reference versus explicit cancellation: chọn theo hợp đồng

| Mục tiêu | Thường phù hợp | Nhược điểm/cẩn trọng |
| --- | --- | --- |
| Callback chỉ sống cùng UI component | Unsubscribe/dispose khi đóng UI | Phải triển khai lifecycle mọi đường thoát |
| Async task phải hủy khi owner dừng | Cancel/queue cleanup và lifecycle token | Callback đã chạy có thể vẫn cần phối hợp |
| Callback chỉ cần immutable data nhỏ | Static nested hoặc lambda capture snapshot | Không dùng nếu thực sự cần live owner |
| Owner sống lâu chủ đích và callback sử dụng live owner | Giữ strong owner, lifecycle rõ | Đây không phải leak nếu intended |
| Muốn owner được GC khi không nơi nào giữ mạnh | Weak owner reference có kiểm tra null | Không xác định thời điểm thu gom |
| Framework có weak listener API | Sử dụng framework convention đúng | Listener có thể biến mất nếu không được giữ mạnh đủ lâu |
| Cache với keys không còn cần giữ | Bounded cache/weak keys tùy domain | Values có thể refer back keys; weak refs không chữa mọi graph |
| Dữ liệu được dùng từ nhiều threads | Immutable snapshot hoặc synchronization | Publication/cancellation races vẫn tồn tại |

Không chỉ hỏi “dùng weak hay strong?”. Hãy trả lời **ai là owner của subscription, khi nào được dừng, callback có cần chạy sau khi owner biến mất hay không**.

## 26. Thread safety và callback cleanup

Bản thân việc có reference tới Outer không phải data race. Nhưng nếu callback chạy trên thread khác và truy cập mutable Outer fields, phải có Java Memory Model rules phù hợp.

Ví dụ:
- Shared mutable fields cần synchronization/volatile/locks/atomic operations tùy contract.
- `close()` subscription đang diễn ra cùng lúc với event dispatch có thể vẫn cho một callback đang chạy hoàn tất; định nghĩa ranh giới “đã unsubscribe” rõ.
- EventBus dựa trên `ArrayList` đơn giản không phù hợp cho concurrent register/fire/remove nếu không bảo vệ.
- Dữ liệu snapshot immutable giúp ít race hơn, nhưng holder reference/publication vẫn cần đúng.
- Một callback đọc String snapshot không có nghĩa một loạt updates external đã atomic.

### 26.1. Ví dụ concurrent registry dùng library phù hợp (snippet)

~~~java
private final java.util.concurrent.CopyOnWriteArrayList<Runnable>
        listeners = new java.util.concurrent.CopyOnWriteArrayList<>();
~~~

Cấu trúc này cung cấp thread-safe collection operations theo hợp đồng `CopyOnWriteArrayList`, nhưng:

- Listener object có thể vẫn giữ Outer qua captured reference.
- `remove` vẫn cần được gọi khi lifecycle kết thúc.
- Snapshot iteration semantics có thể cho callback đã tồn tại lúc bắt đầu duyệt tiếp tục được gọi ngay cả khi bị remove giữa đợt dispatch.
- Shared mutable state trong callback vẫn cần concurrency controls riêng.

**Thread-safe collection không tự chống memory retention.**

## 27. Heap inspection: kiểm chứng leak bằng đường GC root

Khi ứng dụng tăng heap sau nhiều lần mở/đóng màn hình, đừng kết luận leak chỉ từ một snapshot.

Quy trình điều tra thực tế:

1. **Tái hiện workflow** tạo/hủy owner (mở/đóng màn hình, subscribe/unsubscribe) nhiều lần có kiểm soát.
2. Theo dõi heap usage sau những GC thực sự diễn ra; phân biệt warm-up, caches đúng chủ đích, allocation rate và live set.
3. Lấy heap dump hoặc live-object histogram phù hợp, lưu ý heap dump có thể chứa dữ liệu nhạy cảm.
4. Dùng Memory Analyzer/VisualVM/JDK tooling để tìm instances của Screen/View/Outer sau khi lifecycle lẽ ra đã kết thúc.
5. Xem **path to GC roots**, **incoming references**, **dominator tree** và retained size; nhận diện registry/listener/task/cache owner.
6. Kiểm tra một Inner/lambda/anonymous instance có reference/captured receiver tới Outer không, không phụ thuộc duy nhất vào tên field `this$0`.
7. Sửa **gốc sở hữu reference**: unregister, cancel, clear cache/queue hoặc đổi static nested/snapshot nếu đúng contract.
8. Tái chạy workflow, so sánh các live counts/retained paths. Đừng cam kết GC tức thì trong unit test.

### 27.1. Công cụ thường dùng

- **VisualVM**: profiler, heap dump browsing, xem instances/references.
- **Eclipse Memory Analyzer (MAT)**: dominators, retained heap, paths to GC roots.
- **JDK Mission Control / JFR**: allocation/GC telemetry và chẩn đoán application runtime.
- **`jcmd`** và các JDK diagnostic commands: có thể lấy histogram/heap info/dump theo options của JDK đang dùng.
- **`javap -p`**: xem chi tiết generated fields/methods của class file cụ thể, không thay thế heap analysis.

Không chạy heap dump trên dữ liệu production nhạy cảm mà thiếu chính sách truy cập/lưu trữ/xóa phù hợp.

## 28. Tránh sửa leak bằng cách ép `null` mọi field

Đặt một local reference thành null đôi khi giúp code không giữ local lâu hơn cần, nhưng **không xóa reference trong registry**. Ví dụ:

~~~java
Screen screen = new Screen();
bus.add(screen.new Handler());

screen = null;
~~~

Nội dung này là snippet minh họa yêu cầu `Screen`/`bus` phù hợp. Registry vẫn giữ handler. **Giải pháp đúng** thường là remove registration hoặc thay cách callback giữ owner.

Tương tự, `System.gc()` không cắt bất kỳ reference path nào. Nó không thay việc fix lifecycle.

## 29. Đừng tự suy luận mọi nested class đều giữ outer

Cần phân biệt:

| Loại nested/callback | Enclosing Outer instance ngầm? | Rủi ro giữ Outer |
| --- | --- | --- |
| Non-static member `Outer.Inner` | Có theo ngữ nghĩa inner class; field vật lý tùy compiler/usage | Khi thật sự cần/có reference tới Outer và callback được giữ |
| Static member `Outer.Nested` | Không | Chỉ khi explicit/captured references khác giữ Outer |
| Member record trong Outer | Implicitly static | Không có enclosing Outer ngầm |
| Member interface/enum | Implicitly static | Không có enclosing Outer ngầm |
| Local class trong instance context | Có thể gắn/capture enclosing context theo quy tắc | Khi dùng state/refs dẫn tới Outer |
| Local class trong static context | Không có enclosing Outer instance của static method | Có thể giữ captured local objects |
| Anonymous class trong instance context | Có thể capture/use enclosing instance | Khi dùng owner/captured references |
| Lambda dùng instance field/`this` | Capture receiver cần dùng | Có thể giữ Outer |
| Lambda chỉ dùng immutable captured local | Không cần owner vì lý do đó | Có thể giữ captured object khác |
| Bound method reference `owner::method` | Giữ receiver cần gọi | Có thể giữ owner |
| Unbound/static method reference | Không buộc giữ một owner instance cụ thể | Tùy các captured values khác |

**Đọc semantics thực tế và reference graph**, không phân loại bằng tên file `Outer$1.class` hay việc code nằm trong cặp ngoặc của Outer.

## 30. Các lỗi thiết kế phổ biến

| Sai lầm | Cách sửa/hiểu đúng |
| --- | --- |
| “Inner được tạo trong method local nên chết khi method return.” | Nếu bị registry giữ, inner vẫn reachable sau method. |
| “`owner = null` chắc chắn giải phóng owner.” | Còn reference paths khác từ callbacks/listeners/queues. |
| “Java GC không thu gom cycles nên Outer↔Inner leak.” | GC có thể thu gom unreachable cycles; xem roots. |
| “Mọi Inner object trên mọi JDK luôn có field `this$0`.” | JDK 18 javac có thể bỏ unused outer field; implementation-dependent. |
| “Static nested class luôn không giữ Outer.” | Nó vẫn có thể giữ explicit Outer field hoặc references khác. |
| “Dùng `WeakReference` là không cần cleanup.” | Weak refs không thay lifecycle, callback có thể mất quá sớm. |
| “`WeakHashMap` luôn làm key được GC.” | Value có strong reference quay lại key có thể giữ key. |
| “Một lần `System.gc()` chứng minh không leak.” | Không có GC timing guarantee. |
| “EventBus thread-safe thì không leak.” | Thread safety và retention là hai concerns khác nhau. |
| “Copy Outer để listener không giữ object cũ.” | Copy có thể sai semantics và còn shared components; fix ownership. |
| “Tạo listener mới để gọi remove listener cũ.” | Registry có thể dùng identity/equality; cần đúng reference/token. |
| “Anonymous class và lambda luôn capture outer giống nhau.” | Lambda chỉ giữ receiver nếu body/reference đòi; `this` semantics khác. |
| “Cần luôn chuyển mọi Inner thành static.” | Nếu inner cần live Outer hợp pháp, quản lý lifecycle mới là trọng tâm. |
| “Weak listener tốt hơn strong listener trong mọi case.” | Có thể bị thu gom khi còn cần callback. |
| “Hết màn hình UI thì timer tự hủy.” | Phụ thuộc framework/lifecycle; cần stop/cancel khi cần. |
| “Callback đã unregister không thể đang thực thi.” | Concurrent dispatch có thể có callback đang chạy; cần hợp đồng race rõ. |
| “Retained size bằng shallow size của Inner.” | Inner có thể giữ Outer graph lớn qua một reference. |
| “Heap dump một lần đủ chứng minh leak.” | Cần reproduction, lifecycle expectations và roots/retained paths. |

## 31. Checklist code review cho inner callbacks

1. Inner có thật sự cần gọi instance state/method của Outer không?
2. Nếu không cần, có thể dùng **static nested class** hay top-level helper không?
3. Nếu chỉ cần ID/config nhỏ, có thể capture immutable snapshot thay cả Outer không?
4. Callback/Inner sẽ được đăng ký vào service nào? Lifetime service dài hơn owner không?
5. Ai lưu registration token/reference? Ai có trách nhiệm unsubscribe?
6. Có đủ nhánh cleanup: success, exception, close, cancellation, timeout, unmount không?
7. Callback có thể còn chạy trong lúc unsubscribe không? API có yêu cầu atomicity không?
8. Có pending executor/scheduler tasks khi owner dừng không?
9. Có static cache/registry/listener list nào giữ callback lâu dài không?
10. Có lambda `this::method` hoặc `() -> instanceField` đang capture receiver không?
11. Có anonymous/local class đọc `Outer.this` hoặc captured mutable references không?
12. Có weak listener được giữ strong đủ lâu theo nhu cầu không?
13. Có dùng `WeakHashMap` mà values tham chiếu quay lại weak keys không?
14. Outer có giữ large payload/graphs khiến retained size lớn không?
15. Có benchmark/test tái hiện nhiều vòng open-close để quan sát registry size không?
16. Có heap dump path to GC roots xác nhận đúng retention chain không?
17. Có vô tình viết test `System.gc()` và assert object cleared ngay không?
18. Có đang suy từ synthetic field name trên một JDK sang mọi JDK khác không?
19. Nếu đổi Inner sang static nested, hành vi business/lifetime có còn đúng không?
20. Đã giải thích ownership contract cho người gọi API chưa?

## 32. Chương trình tự kiểm tra vòng đời, không phụ thuộc GC

Lưu **`ListenerLifecycleContractTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerLifecycleContractTest {
    static final class Bus {
        final List<Runnable> handlers = new ArrayList<>();

        void add(Runnable callback) {
            handlers.add(callback);
        }

        void remove(Runnable callback) {
            handlers.remove(callback);
        }
    }

    static final class Owner {
        private final String id;

        Owner(String id) {
            this.id = id;
        }

        class Handler implements Runnable {
            @Override
            public void run() {
                if (Owner.this.id.isBlank()) {
                    throw new IllegalStateException();
                }
            }
        }

        Handler subscribe(Bus bus) {
            Handler handler = new Handler();
            bus.add(handler);
            return handler;
        }
    }

    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Bus bus = new Bus();
        Owner owner = new Owner("A");

        Owner.Handler handler = owner.subscribe(bus);

        check(bus.handlers.size() == 1, "registered");
        check(bus.handlers.contains(handler), "same handler");

        bus.handlers.get(0).run();
        bus.remove(handler);

        check(bus.handlers.isEmpty(), "cleanup");
        System.out.println("listener lifecycle checks passed");
    }
}
~~~

Chạy:

~~~bash
javac ListenerLifecycleContractTest.java
java ListenerLifecycleContractTest
~~~

Output:

~~~text
listener lifecycle checks passed
~~~

Test kiểm tra **contract register/unregister** bằng behavior xác định. Nó không kết luận thời điểm GC của Owner. Nếu bug ở production là retention, thêm integration test lifecycle và heap analysis phù hợp.

## 33. Bài tập ôn luyện và lời giải

**Câu 1.** `Outer.Inner x = outer.new Inner()` cung cấp điều gì?  
**Đáp án:** Tạo Inner gắn với enclosing Outer instance hiện tại của `outer`.

**Câu 2.** Inner dùng `Outer.this.id` đang tham chiếu tới object nào?  
**Đáp án:** Enclosing Outer object gắn với Inner.

**Câu 3.** `new Outer.Nested()` có cần một enclosing Outer instance không?  
**Đáp án:** Không, nếu Nested là static member class accessible.

**Câu 4.** Registry giữ một Inner listener mà Inner đọc Outer fields, gán `outer=null` có đủ để Outer được GC không?  
**Đáp án:** Không; registry → listener → Outer có thể còn là strong path.

**Câu 5.** Registry remove listener xong Outer có chắc chắn bị thu gom ngay không?  
**Đáp án:** Không. Có thể còn refs khác, và GC timing không được bảo đảm.

**Câu 6.** Nếu Outer ↔ Inner tạo cycle nhưng không GC root nào tới chúng, có mặc định leak không?  
**Đáp án:** Không; garbage collector có thể thu gom unreachable cycles.

**Câu 7.** JDK 18 có thay đổi nào về `this$0`?  
**Đáp án:** `javac` có thể bỏ synthetic enclosing-instance field khi inner class không sử dụng outer instance.

**Câu 8.** Tối ưu JDK 18 có bỏ yêu cầu `outer.new Inner()` của member Inner không static không?  
**Đáp án:** Không. Source-level creation syntax/enclosing rules vẫn áp dụng.

**Câu 9.** Inner thật sự đọc `Outer.this.id` có thể dùng dữ liệu đó sau khi caller bỏ local Outer reference không?  
**Đáp án:** Có nếu Inner vẫn được giữ; nó cần liên kết semantic với Outer.

**Câu 10.** Static nested callback giữ `private final Outer owner` có thể giữ Outer reachable không?  
**Đáp án:** Có. Explicit strong owner reference vẫn là reference path.

**Câu 11.** Khi callback chỉ cần immutable String ID, hướng thiết kế nào thường giảm coupling?  
**Đáp án:** Static nested callback hoặc lambda chỉ capture ID snapshot, không capture cả owner.

**Câu 12.** Lambda `() -> println(this.status)` có thể giữ owner không?  
**Đáp án:** Có vì body sử dụng receiver `this`/instance state.

**Câu 13.** Lambda chỉ capture local String snapshot có luôn giữ Outer không?  
**Đáp án:** Không vì lý do capture String snapshot; nhưng cần xem toàn bộ captured references/implementation.

**Câu 14.** `this` trong anonymous Runnable trỏ tới ai?  
**Đáp án:** Anonymous Runnable object; enclosing Outer dùng `Outer.this` nếu có.

**Câu 15.** `this` trong lambda đặt trong Outer instance method trỏ tới ai?  
**Đáp án:** Theo lexical scope, Outer instance.

**Câu 16.** `owner::onEvent` có giữ owner receiver cần gọi method không?  
**Đáp án:** Có thể tạo strong reference tới receiver; xem lifecycle của callback.

**Câu 17.** Callback trong queue chưa chạy có thể giữ Outer không?  
**Đáp án:** Có nếu callback giữ Outer/captured reference và queue còn giữ callback.

**Câu 18.** Có phải mọi cancelled scheduled task đều bị loại ngay khỏi queue không?  
**Đáp án:** Không có bảo đảm chung; tùy scheduler implementation/configuration.

**Câu 19.** Cơ chế cleanup rõ nhất của EventBus listener là gì?  
**Đáp án:** Giữ registration token/reference, unregister/close khi owner dừng.

**Câu 20.** Vì sao tạo một new Handler rồi remove có thể không xóa Handler cũ?  
**Đáp án:** Handler mới là object khác, Object.equals mặc định identity nếu không override.

**Câu 21.** `WeakReference` có bảo đảm `get()==null` ngay sau `System.gc()` không?  
**Đáp án:** Không. GC có timing/behavior không được bảo đảm.

**Câu 22.** Vì sao weak listener có thể mất quá sớm?  
**Đáp án:** Không còn strong root giữ listener khi nghiệp vụ vẫn cần callback.

**Câu 23.** `WeakHashMap` với value trỏ ngược key có thể giữ key không?  
**Đáp án:** Có; strong path từ value tới key có thể ngăn key được thu gom.

**Câu 24.** Một Outer chứa byte[] lớn bị giữ bởi Inner có thể ảnh hưởng retained size thế nào?  
**Đáp án:** Có thể giữ cả payload graph reachable, lớn hơn shallow size của Inner.

**Câu 25.** Có nên phụ thuộc reflection field name `this$0` để tìm owner?  
**Đáp án:** Không; field synthetic/name/compiler layout không phải public API contract.

**Câu 26.** Tại sao thread-safe listener list không tự sửa memory leak?  
**Đáp án:** Thread safety của operations khác với lifetime của stored listener references.

**Câu 27.** Có phải tất cả inner classes là sai thiết kế không?  
**Đáp án:** Không. Khi business cần gắn với Outer và lifecycle được quản lý, Inner rất phù hợp.

**Câu 28.** Nếu callback đọc outer state sống, có thể thay bằng ID snapshot mà giữ behavior không?  
**Đáp án:** Không nhất thiết; snapshot có thể làm thay đổi semantics. Cần làm rõ nhu cầu live hay snapshot.

**Câu 29.** Trong heap dump, cần tìm gì để giải thích Outer không được thu gom?  
**Đáp án:** Path to GC roots và incoming strong reference chains, dominators/retained size.

**Câu 30.** Unit test retention nên assert điều gì thay vì GC ngay?  
**Đáp án:** Số subscriptions/tasks còn lại, unregister/cancel đúng identity, registry cleanup và behavior sau close.

**Câu 31.** Nếu callback có receiver `this::handler` và được lưu trong global map, ai có thể bị giữ?  
**Đáp án:** Receiver object và graph reachable từ receiver nếu không có cleanup.

**Câu 32.** Static nested class không giữ outer ngầm thì còn cách nào làm leak?  
**Đáp án:** Giữ Outer hoặc graph lớn qua explicit fields, callbacks hay các references khác.

## 34. Tài liệu tham khảo

- Java Language Specification Java SE 17, [`8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing-instance semantics.
- Java Language Specification, [`15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): qualified inner class creation.
- Java Language Specification, [`15.8.4 — Qualified this](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): `Outer.this`.
- Java Language Specification, [`15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): lambda lexical scoping/capture.
- Java Platform API Java 17, [`WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability.
- Java Platform API, [`WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys và value references.
- Java Platform API, [`AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): lifecycle/close.
- Java Platform API, [`CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): thread-safe listener registry pattern, lưu ý lifecycle.
- Java Platform API, [`System.gc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()): yêu cầu GC không phải xác nhận thu gom ngay.
- Oracle JDK 18 Release Notes, [Enclosing Instance Fields Omitted from Inner Classes That Don't Use Them](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html): thay đổi compiler `javac` liên quan unused `this$` synthetic fields.
- Java Platform Tools, [`javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspect class file fields/methods.
- Java Platform Tools, [`jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): JDK diagnostics/heap inspection.

## Tổng kết

Một **non-static member Inner** được tạo bằng `outer.new Inner()` có enclosing instance theo Java source-level semantics, cho phép dùng `Outer.this` và truy cập outer instance fields. Nếu callback Inner được giữ trong một registry/task/cache sống lâu và thực sự cần enclosing Outer, nó có thể **giữ Outer cùng nhiều thành phần của Outer còn reachable**, dù caller không còn biến local trỏ tới Outer. Đây là memory retention do ownership/lifecycle, không phải GC “không biết dọn cycle”.

Không khẳng định mù quáng mọi Inner trên mọi compiler luôn có field `this$0`: từ JDK 18, `javac` có thể bỏ synthetic field này nếu enclosing instance **không được sử dụng**. Để giảm rủi ro, hãy dùng **static nested class hoặc callback chụp immutable values** khi không cần owner; khi cần live owner thì **register/unregister/cancel/close rõ ràng** theo lifecycle. Static nested có explicit owner field cũng có thể giữ Outer, nên chỉ đổi từ khóa `static` không thay việc quản lý references.

Cuối cùng, không đo “thành công” bằng `System.gc()`. Hãy kiểm tra subscription counts, callback identity, task cleanup và dùng **heap snapshots + paths to GC roots** khi nghi retention trong ứng dụng thực. Chọn nơi giữ callback và thời điểm giải phóng nó quan trọng hơn bất kỳ mẹo ép GC nào.
