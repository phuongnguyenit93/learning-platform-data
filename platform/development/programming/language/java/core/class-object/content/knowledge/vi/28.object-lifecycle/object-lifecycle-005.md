# Vì sao tham chiếu vòng không tự nó ngăn thu gom rác trong Java 17+

**Một vòng các tham chiếu mạnh giữa những đối tượng Java không tự làm chúng “bất tử”.** Trong mô hình *tracing garbage collection* của các JVM phổ biến, đối tượng được giữ sống vì **có đường đi tham chiếu mạnh từ tập GC roots**, không phải đơn thuần vì một đối tượng khác vẫn trỏ tới nó.

Hãy xem hai nhóm đối tượng:

~~~text
GC root ───► A ───► B
              ▲      │
              └──────┘

C ───► D
▲      │
└──────┘
~~~

- A và B trỏ nhau, đồng thời **A được GC root trỏ tới**: A/B còn reachable.
- C và D cũng trỏ nhau, **nhưng không có đường đi từ bất kỳ GC root nào**: C/D có thể trở thành garbage và được thu hồi.
- Những cạnh C→D, D→C không phải GC roots; chúng không tạo đường đi từ root.

Đó là lý do **thu gom rác theo reachability khác với bộ đếm tham chiếu đơn giản**. Trong reference counting thuần túy, mỗi object còn ít nhất một reference từ object kia nên count không về 0; tracing GC lại có thể nhận diện cả vòng không được roots đi tới.

README độc lập này thuộc **Java Core — Class & Object / Vòng đời đối tượng**, đúng trọng tâm **“Vì sao tham chiếu vòng không tự nó ngăn thu gom rác”**, áp dụng cho **Java 17+**. Chương trình chạy được có tên file, lệnh biên dịch và stdout dự kiến. Các ví dụ về đồ thị là **mô hình reachability**; chúng không giả vờ đo chính xác một lần thu gom của JVM.

## 1. Kết quả học tập

Sau bài này bạn có thể:

1. Phân biệt “có một reference trỏ tới” với “có đường tham chiếu từ GC root”.
2. Vẽ đồ thị đối tượng và xác định reachable/unreachable nodes.
3. Giải thích vì sao A→B→A không ngăn hai object trở thành garbage.
4. Hiểu khái niệm GC roots, strong references và hướng của các cạnh.
5. Biết thuật toán marking đi từ roots và dùng visited set để xử lý cycles.
6. So sánh tracing GC với reference counting thuần túy.
7. Phân biệt **eligible for GC** với **actually reclaimed**.
8. Không dự đoán chính xác kết quả `System.gc()` hoặc `WeakReference.get()`.
9. Nhận diện vòng bị giữ bởi static field, cache, listener, ThreadLocal hoặc thread.
10. Hiểu tại sao gán null cho một variable không nhất thiết cắt mọi root paths.
11. Phân tích weak references và giới hạn của WeakHashMap.
12. Phân biệt quản lý heap memory với cleanup tài nguyên ngoài heap.
13. Sử dụng try-with-resources và AutoCloseable để quản lý resource lifecycle.
14. Biết cách dùng paths-to-GC-roots khi điều tra memory retention.
15. Tránh viết finalizers làm “thí nghiệm xác nhận GC”.
16. Giải đúng các tình huống nhiều roots, self-loop, parent-child cycles và listeners.

## 2. “Reachable” mới là từ khóa quan trọng

Trong mô hình tracing GC cơ bản, tập reachable được xác định như sau:

- Bắt đầu từ tập **GC roots** mà runtime xác định.
- Lần theo các cạnh **strong reference** tới objects.
- Lặp cho tới khi không còn object mới.
- Những objects không được tìm thấy không còn strongly reachable từ root set trong mô hình.

Ví dụ:

~~~text
ROOT ─► A ─► B ─► C
               ▲    │
               └────┘

D ─► E
▲    │
└────┘
~~~

Từ ROOT có thể đi tới A, B, C. Không thể đi tới D, E, dù D/E tạo một vòng. Vòng chỉ biểu diễn quan hệ giữa objects **bên trong nhóm**; nó không phải một con đường từ GC root **vào** nhóm.

**Kết luận chính:** Không phải “mọi reference đều làm object sống mãi”; chỉ những đường giữ sống phù hợp với quy tắc của runtime/collector mới quyết định reachability.

## 3. Tham chiếu mạnh (*strong reference*) là gì?

Những tham chiếu Java thông thường như fields, local variables, array elements thường là strong references:

~~~java
final class Node {
    Node next;
}

Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;
~~~

Nếu local `a` còn được JVM xem là một live root reference, A reachable và từ A cũng tới được B. Nếu `a` và mọi reference khác từ roots tới vòng không còn, các reference A.next/B.next **không tự kéo vòng trở lại reachable set**.

Tuy vậy, JVM/JIT có thể tối ưu liveness của local references. Không nên đồng nhất dấu ngoặc nhọn, tên biến hay phép gán null trong source với thời điểm collector chính xác coi object là dead.

## 4. GC root là gì?

GC roots là những điểm bắt đầu giúp collector tìm các object cần giữ. Các nguồn thường gặp trong JVM gồm:

- References còn live trên call stacks/registers của threads.
- References từ các static fields/classes đang sống.
- Native/JNI references mà runtime quản lý như roots.
- Một số references do JVM/runtime subsystems nắm giữ.

Chi tiết roots phụ thuộc implementation và collector; không nên coi một bảng liệt kê đơn giản là mô tả nội bộ đầy đủ của mọi JVM.

Một static root minh họa:

~~~java
class Registry {
    static Node retained;
}
~~~

Khi `Registry.retained` trỏ vào A thuộc vòng A↔B, cả vòng có thể đi tới từ root liên quan tới static field. Nếu field không còn giữ reference và **không có đường root khác**, vòng trở thành ứng viên thu gom.

## 5. Vòng có hai nút: khi nào sống, khi nào không?

Tình huống 1:

~~~text
ROOT ─► A ─► B
         ▲    │
         └────┘

Reachable: A, B
~~~

Tình huống 2:

~~~text
ROOT ─► null

A ─► B
▲    │
└────┘

Reachable từ ROOT: không có A/B
~~~

Trong tình huống 2, A/B vẫn trỏ nhau. Nhưng collector không “bắt đầu từ A” hay “bắt đầu từ B” chỉ vì chúng có reference fields.

Nếu còn ROOT2→B, cả A và B lại reachable. Vì thế điều quan trọng là **tập hợp tất cả các root paths**, không chỉ một biến local.

## 6. Tracing GC hoạt động như thế nào ở mức mô hình?

Một mô tả đơn giản:

1. Nhận tập roots.
2. Đánh dấu các objects trực tiếp có thể đi tới từ roots.
3. Theo các reference edges của objects đã đánh dấu.
4. Chỉ mở rộng các cạnh của một object **lần đầu tiên** gặp.
5. Những objects không được đánh dấu có thể được thu hồi theo cơ chế của collector.
6. Collector có thể sweep, compact, copy hoặc thực hiện các phases khác tùy thuật toán.

**Visited set** ngăn duyệt mãi vòng A→B→A. Khi quay lại A, A đã được mark nên không cần mở rộng lại.

Đây là **mô hình lý thuyết**: Java có nhiều collectors với thế hệ vùng nhớ, marking đồng thời, barriers và phases riêng. Không phải mọi collector đơn giản chỉ “dừng toàn thế giới, mark toàn heap rồi sweep”.

## 7. Chương trình chạy: mô phỏng reachability bằng đồ thị

Tạo **`ReachabilityModelDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public class ReachabilityModelDemo {
    static final class Node {
        final String name;
        Node next;

        Node(String name) {
            this.name = name;
        }
    }

    static Set<Node> mark(List<Node> roots) {
        Set<Node> visited = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        Deque<Node> pending = new ArrayDeque<>(roots);

        while (!pending.isEmpty()) {
            Node node = pending.pop();
            if (!visited.add(node)) {
                continue;
            }
            if (node.next != null) {
                pending.push(node.next);
            }
        }
        return visited;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");
        Node d = new Node("D");

        a.next = b;
        b.next = a;
        c.next = d;
        d.next = c;

        Set<Node> seen = mark(List.of(a));
        System.out.println("A=" + seen.contains(a));
        System.out.println("B=" + seen.contains(b));
        System.out.println("C=" + seen.contains(c));
        System.out.println("D=" + seen.contains(d));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ReachabilityModelDemo.java
java ReachabilityModelDemo
~~~

Stdout:

~~~text
A=true
B=true
C=false
D=false
~~~

**Ranh giới của ví dụ:** Đây là kết quả từ **root set giả lập `List.of(a)`**, không phải GC root set thực của JVM. Trong chính chương trình này còn có local variables và Set references trỏ tới các nodes; việc `C=false` chỉ nói C không được thuật toán mô phỏng tìm thấy từ A, **không** nói object C thực sự đã bị Java GC reclaim.

`IdentityHashMap` tạo identity-based visited set, tránh việc custom `equals` làm nhầm hai objects khác nhau thành cùng node.

## 8. Vì sao reference counting đơn giản gặp khó với vòng?

Thuật toán **reference counting thuần túy** đếm các references tới mỗi object. Khi count về 0, object được giải phóng và refs mà nó giữ được giảm count.

Giả sử:

~~~text
A ─► B
▲    │
└────┘

Không có chủ sở hữu bên ngoài.
~~~

Theo bộ đếm đơn giản:
- A vẫn được B trỏ tới → count của A không bằng 0.
- B vẫn được A trỏ tới → count của B không bằng 0.
- Nếu chỉ thu hồi khi count=0, cả nhóm có thể bị giữ mãi.

Tracing GC thì khác: **không root nào đến A/B**, nên chúng không được mark và có thể bị reclaim.

Không nên suy rộng rằng **mọi** hệ thống dùng reference counting đều không giải quyết được cycles: có thể kết hợp cycle detection/collection. Vấn đề nêu ở đây là **pure reference counting với quy tắc count=0**.

## 9. So sánh theo tình huống

| Tình huống | Reference counting thuần túy | Tracing reachability |
| --- | --- | --- |
| Object không có references tới | Count=0 | Unreachable |
| A↔B không còn owner | Counts có thể vẫn 1 | Cả vòng unreachable |
| ROOT→A↔B | Counts dương | A/B reachable |
| A tự trỏ tới chính nó, không owner | Count của A có thể vẫn 1 | A unreachable |
| Có nhiều đường từ roots vào vòng | Counts phản ánh edges | Chỉ cần một path là giữ cả vòng |

Đừng hiểu Java 17 GC là bộ đếm reference đơn giản. Tracing reachability chính là ý tưởng quan trọng để giải thích vì sao cycles không khiến heap objects bất tử.

## 10. Chương trình chạy: vòng tham chiếu rời khỏi method

Tạo **`CycleScopeDemo.java`**:

~~~java
public class CycleScopeDemo {
    static final class Node {
        Node next;
    }

    static void buildCycle() {
        Node first = new Node();
        Node second = new Node();
        first.next = second;
        second.next = first;

        System.out.println("cycle created");
    }

    public static void main(String[] args) {
        buildCycle();
        System.out.println("method returned");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CycleScopeDemo.java
java CycleScopeDemo
~~~

Stdout:

~~~text
cycle created
method returned
~~~

Method không lưu A/B vào static field, không trả chúng ra caller, cũng không đặt chúng trong long-lived collection. Sau khi method kết thúc, nếu không có root path nào khác, A/B có thể trở thành unreachable **dù vẫn trỏ nhau**.

Stdout **không chứng minh GC đã chạy**. Chương trình có thể kết thúc trước khi collector có lý do hoạt động thêm một lần.

## 11. “Đủ điều kiện thu gom” khác “đã thu gom”

Ba trạng thái cần phân biệt:

**Reachable:** vẫn có đường giữ sống phù hợp từ GC roots; không được coi là ordinary garbage chỉ vì user không còn dùng về mặt logic.

**Unreachable / eligible:** không còn strongly reachable theo điều kiện tương ứng; collector có thể thu hồi.

**Actually reclaimed:** JVM đã thật sự reclaim memory trong một lần GC sau đó.

Vì thế, câu **“không còn reference từ roots thì GC có thể thu”** chính xác hơn câu **“khi method return thì JVM giải phóng ngay”**.

Thời điểm reclaim phụ thuộc memory pressure, collector, JVM options, JIT và những hoạt động khác. Không nên tạo bài test dựa vào thời gian cụ thể mà JVM không cam kết.

## 12. Chương trình chạy: static reference còn giữ vòng

Tạo **`StaticOwnerDemo.java`**:

~~~java
public class StaticOwnerDemo {
    static final class Node {
        Node next;
    }

    private static Node head;

    static void registerCycle() {
        Node a = new Node();
        Node b = new Node();

        a.next = b;
        b.next = a;
        head = a;
    }

    public static void main(String[] args) {
        registerCycle();
        System.out.println("still linked=" +
                (head.next.next == head));

        head = null;
        System.out.println("owner removed");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 StaticOwnerDemo.java
java StaticOwnerDemo
~~~

Stdout:

~~~text
still linked=true
owner removed
~~~

Trước `head=null`, đường root→static head→A→B giúp cả hai reachable. Sau khi bỏ static reference, cả vòng **có thể** không còn root path. **Không dựa vào dòng “owner removed” để suy rằng GC ngay lúc đó đã xóa A/B**.

## 13. Gán `null` không nhất thiết phá chu trình

Ví dụ:

~~~java
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;

a = null;
b = null;
~~~

Hai phép gán cuối bỏ references trong hai biến a/b; chúng **không** thay đổi fields A.next/B.next trong heap. Nhưng điều đó không gây vấn đề cho tracing GC nếu không root nào khác còn tới A/B.

Không cần bắt buộc viết:

~~~java
// a.next = null;
// b.next = null;
~~~

để “phá vòng trước khi GC”, và sau `a=null` thì thậm chí không thể truy cập A qua biến a ấy nữa.

Điều cần giải quyết trong ứng dụng là **loại các đường root→graph không còn được dùng**, không phải phá mọi cạnh giữa objects đã unreachable.

## 14. Nhiều roots: loại một reference chưa chắc đủ

~~~text
ROOT1 ─► A ─► B
          ▲    │
          └────┘
ROOT2 ────────► B
~~~

Sau khi ROOT1→A biến mất, ROOT2→B vẫn giữ cả B và A. Việc thấy memory còn cao không chứng minh GC không xử lý cycles; có thể **một owner khác vẫn giữ đường sống**.

Hãy phân tích toàn bộ:
- static fields/cache entries;
- active threads hoặc tasks;
- closures/lambda captures;
- callback/listener registries;
- ThreadLocal values;
- JNI/native references;
- parent objects hoặc collections vẫn reachable.

## 15. Chương trình chạy: mô hình thêm/bỏ roots

Tạo **`RootSetDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public class RootSetDemo {
    static final class Node {
        Node next;
    }

    static int count(List<Node> roots) {
        Set<Node> marked = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        Deque<Node> todo = new ArrayDeque<>(roots);

        while (!todo.isEmpty()) {
            Node node = todo.pop();
            if (marked.add(node) && node.next != null) {
                todo.push(node.next);
            }
        }
        return marked.size();
    }

    public static void main(String[] args) {
        Node a = new Node();
        Node b = new Node();
        a.next = b;
        b.next = a;

        System.out.println("with root=" + count(List.of(a)));
        System.out.println("without roots=" + count(List.of()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RootSetDemo.java
java RootSetDemo
~~~

Stdout:

~~~text
with root=2
without roots=0
~~~

Dù đoạn Java thực có a/b locals, root list do ta **chủ động mô phỏng** có thể rỗng. Đây là thí nghiệm logic, không phải công cụ buộc JVM reclaim.

## 16. Memory leak trong Java thường là object **vẫn reachable**

Một “memory leak” ở mức ứng dụng Java thường là **đối tượng không còn cần về mặt nghiệp vụ nhưng vẫn có đường mạnh từ root**, do application giữ nó quá lâu.

Ví dụ:
- static List/Map không bao giờ clear/evict;
- event listeners không unregister;
- queued tasks lưu closures giữ toàn bộ màn hình/model;
- ThreadLocal values sống lâu trong pooled threads;
- cache keys/values liên kết với nhau;
- threads không dừng đúng lifecycle;
- native handles còn sở hữu reference graph.

GC **không thể tùy tiện xóa reachable objects** vì application vẫn có cách truy cập chúng; vấn đề là **ownership**, không phải “Java bị kẹt trước vòng tham chiếu”.

Ngược lại, một vòng không còn owner là **ordinary garbage** có thể được collector xử lý.

## 17. Chương trình chạy: static cache giữ cả vòng

Tạo **`CacheCycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CacheCycleDemo {
    static final class Node {
        Node next;
    }

    static final List<Node> CACHE = new ArrayList<>();

    static void install() {
        Node a = new Node();
        Node b = new Node();
        a.next = b;
        b.next = a;
        CACHE.add(a);
    }

    public static void main(String[] args) {
        install();

        System.out.println("cache=" + CACHE.size());
        System.out.println("cycle=" +
                (CACHE.get(0).next.next == CACHE.get(0)));

        CACHE.clear();
        System.out.println("cache cleared=" + CACHE.size());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CacheCycleDemo.java
java CacheCycleDemo
~~~

Stdout:

~~~text
cache=1
cycle=true
cache cleared=0
~~~

Khi CACHE chứa A, đường static cache→A→B giữ vòng. Khi clear, đường ấy biến mất. Nếu không có root khác, A/B đủ điều kiện GC. Số phần tử cache 0 không có nghĩa JVM phải giảm committed heap bytes tức thì.

## 18. Event listener giữ sống object qua lambda capture

Một common pattern:

~~~text
GC root
   │
   ▼
Static listener registry ─► Callback ─► Screen
                               ▲          │
                               └──────────┘
~~~

Ở đây vòng Callback↔Screen có thể tồn tại, nhưng điều quan trọng là **registry vẫn giữ Callback** và Callback giữ Screen.

Khi UI/screen/component kết thúc lifecycle:
- unsubscribe listener;
- remove callback khỏi registry;
- clear/detach subscriptions theo contract;
- tránh capture object graph lớn không cần thiết.

## 19. Chương trình chạy: callback capture Screen

Tạo **`ListenerOwnerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerOwnerDemo {
    static final List<Runnable> LISTENERS =
            new ArrayList<>();

    static final class Screen {
        final String title;

        Screen(String title) {
            this.title = title;
        }
    }

    static void open() {
        Screen screen = new Screen("Home");
        LISTENERS.add(() ->
                System.out.println("event=" + screen.title));
    }

    public static void main(String[] args) {
        open();

        System.out.println("listeners=" + LISTENERS.size());
        LISTENERS.get(0).run();

        LISTENERS.clear();
        System.out.println("after clear=" + LISTENERS.size());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ListenerOwnerDemo.java
java ListenerOwnerDemo
~~~

Stdout:

~~~text
listeners=1
event=Home
after clear=0
~~~

Listener còn trong static registry giữ Screen reachable qua captured reference. Sau clear, đường owner này bị bỏ. Không có claim về thời điểm JVM GC thực sự reclaim Screen.

## 20. ThreadLocal trong thread pool cũng là một owner path

Một long-lived thread giữ ThreadLocalMap, value có thể giữ A↔B. Một request đã hoàn thành nhưng ThreadLocal không được remove có thể làm object graph sống quá request.

Thực hành:

~~~java
try {
    CONTEXT.set(context);
    // Xử lý trong request.
} finally {
    CONTEXT.remove();
}
~~~

Đặc biệt quan trọng khi threads được tái sử dụng trong executor/thread pool.

### Chương trình chạy

Tạo **`ThreadLocalOwnerDemo.java`**:

~~~java
public class ThreadLocalOwnerDemo {
    static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    static void process() {
        CONTEXT.set("request-7");
        try {
            System.out.println("inside=" + CONTEXT.get());
        } finally {
            CONTEXT.remove();
        }
    }

    public static void main(String[] args) {
        process();
        System.out.println("outside=" + CONTEXT.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ThreadLocalOwnerDemo.java
java ThreadLocalOwnerDemo
~~~

Stdout:

~~~text
inside=request-7
outside=null
~~~

Đây là deterministic cleanup của owner relationship. Nó không gọi System.gc và không cần phá các cycles mà value có thể tham chiếu.

## 21. Self-reference không khác về nguyên lý

Object có thể tự trỏ tới chính nó:

~~~java
Node node = new Node();
node.next = node;
~~~

Đồ thị:

~~~text
A ───► A
~~~

Nếu không còn strong path từ GC roots vào A, self-edge không giữ A sống.

### Chương trình chạy

Tạo **`SelfCycleDemo.java`**:

~~~java
public class SelfCycleDemo {
    static final class Node {
        Node next;
    }

    static void create() {
        Node node = new Node();
        node.next = node;

        System.out.println("self=" + (node.next == node));
    }

    public static void main(String[] args) {
        create();
        System.out.println("returned");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SelfCycleDemo.java
java SelfCycleDemo
~~~

Stdout:

~~~text
self=true
returned
~~~

Self-loop tồn tại trong method, nhưng không làm object tự trở thành root sau method exit.

## 22. Hướng của tham chiếu rất quan trọng

Giả sử chỉ có A→B, không có B→A:

~~~text
A ─► B
~~~

Nếu root→A, cả A/B reachable. Nếu root→B nhưng không root→A, thì A **không** tự reachable chỉ vì A đã trỏ tới B.

GC traversal đi **theo chiều reference từ owner đến target**, không coi mọi cạnh như đường hai chiều.

### Chương trình chạy

Tạo **`DirectedEdgesDemo.java`**:

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class DirectedEdgesDemo {
    static final class Node {
        Node next;
    }

    static Set<Node> follow(Node root) {
        Set<Node> visited = Collections.newSetFromMap(
                new IdentityHashMap<Node, Boolean>());
        Node current = root;

        while (current != null && visited.add(current)) {
            current = current.next;
        }
        return visited;
    }

    public static void main(String[] args) {
        Node a = new Node();
        Node b = new Node();
        a.next = b;

        System.out.println("A to B=" + follow(a).contains(b));
        System.out.println("B to A=" + follow(b).contains(a));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DirectedEdgesDemo.java
java DirectedEdgesDemo
~~~

Stdout:

~~~text
A to B=true
B to A=false
~~~

Ví dụ duyệt đồ thị có output chắc chắn; không đo roots của Java runtime.

## 23. Cấu trúc parent/child có back references là bình thường

Doubly linked lists, trees có parent pointers, graphs và domain relationships thường chứa vòng:

~~~java
final class TreeNode {
    TreeNode parent;
    java.util.List<TreeNode> children =
            new java.util.ArrayList<>();
}
~~~

Khi parent giữ child và child giữ parent, có cycle. Điều đó **không phải lỗi memory management**. Nếu cả cây không còn root owner, collector có thể reclaim cả graph.

Nếu parent vẫn sống và muốn detach một subtree, hãy cập nhật `children` và `parent` đúng domain invariant để subtree không còn bị giữ. Lý do làm vậy là **logical ownership và graph integrity**, không phải vì Java không biết thu gom cycles.

## 24. Chương trình chạy: cây với quan hệ hai chiều

Tạo **`ParentChildCycleDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ParentChildCycleDemo {
    static final class Node {
        final String name;
        Node parent;
        final List<Node> children = new ArrayList<>();

        Node(String name) {
            this.name = name;
        }

        void add(Node child) {
            child.parent = this;
            children.add(child);
        }
    }

    public static void main(String[] args) {
        Node root = new Node("root");
        Node leaf = new Node("leaf");
        root.add(leaf);

        System.out.println("root has leaf=" +
                root.children.contains(leaf));
        System.out.println("leaf has root=" +
                (leaf.parent == root));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ParentChildCycleDemo.java
java ParentChildCycleDemo
~~~

Stdout:

~~~text
root has leaf=true
leaf has root=true
~~~

Vòng parent↔child là mô hình bình thường. Liveness phụ thuộc liệu còn root paths vào cây hay không.

## 25. WeakReference: một cách biểu đạt quan hệ không sở hữu

`java.lang.ref.WeakReference<T>` không giữ target mạnh như một reference field thông thường.

Ví dụ:

~~~java
Node strong = new Node();
WeakReference<Node> weak = new WeakReference<>(strong);
~~~

Khi `strong` (và các strong/soft paths phù hợp khác) không còn:
- referent có thể trở thành weakly reachable;
- collector có thể clear weak references tới referent;
- `weak.get()` **có thể** trả object trước khi được clear, hoặc null sau khi được clear;
- việc khi nào clear không là một guarantee dựa trên số dòng Java hoặc thời gian cố định.

Cách phát biểu đúng là **weak reference không tự ngăn GC của target chỉ còn weakly reachable**, không phải “weak.get() ngay lập tức null sau strong=null”.

## 26. Chương trình chạy: WeakReference nhưng stdout ổn định

Tạo **`WeakReferenceDemo.java`**:

~~~java
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    static final class Node {
        final String name;

        Node(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        Node strong = new Node("A");
        WeakReference<Node> weak = new WeakReference<>(strong);

        System.out.println("same while held=" +
                (weak.get() == strong));

        strong = null;
        System.out.println("strong variable cleared");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 WeakReferenceDemo.java
java WeakReferenceDemo
~~~

Stdout:

~~~text
same while held=true
strong variable cleared
~~~

Sau `strong=null` chương trình **cố ý không in `weak.get()==null`**, bởi kết quả không được bảo đảm. JVM/JIT còn có thể tối ưu liveness của local variables; assignment ở source không phải lệnh giải phóng memory lập tức.

## 27. Weak edge và strong cycle có thể tồn tại cùng nhau

~~~text
ROOT ─► WeakReference ──weak──► A ──strong──► B
                               ▲             │
                               └─────────────┘
~~~

Nếu không root nào có **strong path** tới A/B, weak edge từ root tới A không bắt đầu một strong tracing path giữ cả cycle. Vòng A↔B có thể thu gom.

Nếu ROOT2→B bằng strong reference, B và A lại reachable.

**Lưu ý:** Java Reference API còn có SoftReference, PhantomReference, ReferenceQueue và các quy tắc đặc biệt; với câu hỏi cơ bản về vòng strong references, không nên trộn chúng với strong GC roots rồi kết luận sai.

## 28. WeakHashMap không chữa mọi memory retention

`WeakHashMap<K,V>` lưu **weak keys**. Nếu key không còn được giữ mạnh ở nơi khác và collector xử lý, entry có thể mất khỏi map.

Nhưng hãy xem graph:

~~~text
WeakHashMap ──strong──► Value ──strong──► Key
       │                                  ▲
       └────────────weak──────────────────┘
~~~

Value có đường mạnh từ map, và value lại trỏ mạnh tới Key. Điều đó có thể khiến Key vẫn strongly reachable dù map dùng weak key. Vì vậy **WeakHashMap không bảo đảm tự xóa mọi entry khi application “không còn dùng key” theo ý nghĩ logic**.

Cũng không được suy ra rằng entries phải biến mất vào đúng một thời điểm hay WeakHashMap thay được bounded cache/eviction policy.

## 29. Chương trình chạy: WeakHashMap khi key còn mạnh

Tạo **`WeakMapDemo.java`**:

~~~java
import java.util.Map;
import java.util.WeakHashMap;

public class WeakMapDemo {
    static final class Key {
        final String id;

        Key(String id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Map<Key, String> map = new WeakHashMap<>();
        Key key = new Key("A");
        map.put(key, "value");

        System.out.println("contains=" + map.containsKey(key));
        System.out.println("value=" + map.get(key));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 WeakMapDemo.java
java WeakMapDemo
~~~

Stdout:

~~~text
contains=true
value=value
~~~

Key vẫn được local reference `key` giữ mạnh trong lúc sử dụng; ví dụ không đoán lúc JVM sẽ thu gom WeakHashMap entries sau khi bỏ root.

## 30. ReferenceQueue không bảo đảm GC chạy theo lịch test

`ReferenceQueue<T>` giúp một số reference objects được enqueue theo Java Reference processing rules. Nó hữu ích cho certain cleanup/cache mechanisms, nhưng không cho phép application bảo đảm:

- collector phải chạy sau X mili-giây;
- `WeakReference.get()` phải null ngay sau `System.gc()`;
- mọi reference phải được enqueue trước khi main kết thúc;
- external resources sẽ được close theo thời điểm mong muốn.

Ngoài ra, gọi `Reference.clear()` chủ động không phải bằng chứng JVM vừa reclaim target.

Nếu chỉ muốn minh họa vì sao vòng được GC xử lý, đồ thị reachability và thuật toán mark là cách chắc chắn hơn một ReferenceQueue test không xác định.

## 31. `System.gc()` chỉ là yêu cầu, không phải lệnh ép kết quả

Không viết test như sau rồi kết luận “JVM chắc chắn sai” nếu weak.get() vẫn khác null:

~~~java
a = null;
b = null;
System.gc();
// Không được đảm bảo weak.get() == null ngay.
~~~

`System.gc()` là một yêu cầu cố gắng thu gom; không có language guarantee rằng mọi unreachable object sẽ được reclaim, cleared/enqueued hay reflected trong heap metrics ở thời điểm kế tiếp. JVM có thể có flags/chính sách ảnh hưởng tới yêu cầu này.

Vì vậy:
- **Đừng assert một mốc thời gian GC** trong unit tests.
- **Đừng dùng GC print logs để khẳng định một object cụ thể chắc chắn đã chết**, nếu không có evidence phù hợp.
- **Đừng dùng System.gc() thường xuyên như phương án chữa leak**.
- Nếu muốn đo retention, dùng heap analysis, allocation profiling và paths-to-roots có phương pháp.

## 32. Tránh dùng `finalize()` để chứng minh vòng đã chết

Finalization đã bị deprecated và Java hướng tới loại bỏ dần cơ chế này. Overriding `finalize()` để in “object reclaimed” có nhiều vấn đề:
- thời điểm chạy không được bảo đảm;
- có thể không chạy trước khi program kết thúc;
- có thể làm object resurrection;
- gây overhead và rủi ro bảo mật/độ tin cậy;
- không mô tả thuần túy actual reclaim timing.

Với Java 17+, **không viết finalizer-based GC demonstrations** chỉ để chứng minh object cycles có thu gom. Hãy diễn đạt eligibility bằng root reachability.

## 33. Garbage collection không thay thế đóng tài nguyên

Một object có thể giữ file handle, socket, JDBC resource hoặc native memory. GC-managed heap memory và external resource lifecycle **khác nhau**.

Nếu một Session giữ vòng references với callback, việc vòng đó trở nên unreachable **không phải đảm bảo** file/socket được close đúng lúc.

Giải pháp:
- implement `AutoCloseable` khi phù hợp;
- dùng try-with-resources;
- xác định clear/close/unregister theo lifecycle;
- không dựa vào finalization hoặc collector schedule để làm business-critical cleanup.

### Chương trình chạy

Tạo **`ExplicitCloseDemo.java`**:

~~~java
public class ExplicitCloseDemo {
    static final class Session implements AutoCloseable {
        private boolean closed;

        Session() {
            System.out.println("open");
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            System.out.println("use");
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("close");
        }
    }

    public static void main(String[] args) {
        try (Session session = new Session()) {
            session.use();
        }
        System.out.println("done");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ExplicitCloseDemo.java
java ExplicitCloseDemo
~~~

Stdout:

~~~text
open
use
close
done
~~~

`close()` được gọi do try-with-resources, không phải vì JVM GC quyết định reclaim Session.

## 34. RAM của tiến trình không giảm ngay chưa chứng minh leak

Sau khi objects unreachable và GC thực sự reclaim chúng, JVM vẫn có thể:
- giữ heap memory đã committed để dùng lại;
- không trả phần lớn committed heap về OS ngay;
- phân bổ native/metaspace/off-heap memory khác;
- tiếp tục allocate objects liên tục trong workload.

Vì vậy Task Manager hoặc RSS không giảm ngay sau `CACHE.clear()` **không chứng minh** “circular references ngăn thu gom”.

Khi điều tra memory:
1. đo used heap với công cụ phù hợp;
2. phân tích retained objects;
3. kiểm tra root paths;
4. phân biệt committed heap, used heap và RSS;
5. quan sát xu hướng qua nhiều GC cycles/workload ổn định.

## 35. Điều tra heap dump: tìm đường đến GC roots

Khi nghi ngờ object graph sống quá lâu:
- tạo heap dump với quyền truy cập phù hợp;
- dùng công cụ phân tích heap hỗ trợ Java 17;
- chọn object/subgraph;
- xem **path to GC roots** hoặc **dominator tree/retained size**;
- xác định owner có đường mạnh tới subgraph;
- sửa lifecycle như clear cache, unregister listeners, remove ThreadLocal;
- đo lại sau thay đổi.

Ví dụ:

~~~text
GC root
  └── static EventBus.listeners
       └── Callback
            └── Screen
                 └── Model A
                      └── Model B
                           └── Model A
~~~

Vấn đề thường là **EventBus.listeners giữ Callback**, không phải Model A/B có cycle.

Heap dumps có thể chứa dữ liệu nhạy cảm như passwords/tokens. Giữ an toàn, hạn chế chia sẻ và không lưu bừa vào logs hoặc artifacts công khai.

## 36. Phân biệt đúng đối tượng nào nên được root giữ

Không phải every retained object là leak:
- Một session active cần giữ state.
- Một graph model được người dùng mở cần tồn tại.
- Một static immutable constant có thể được giữ suốt process.
- Một cache có eviction và size budget rõ có thể đúng thiết kế.

Memory leak logic xảy ra khi **retention kéo dài ngoài nhu cầu**. Đánh giá bằng ownership và lifecycle contract, không chỉ nhìn thấy references hay cycles.

Một object graph A↔B được root giữ là bình thường nếu application còn dùng; bất thường khi root owner đã hết nhiệm vụ nhưng chưa release.

## 37. Có nên chủ động phá các cạnh A.next/B.next?

Đối với một vòng **đã không còn reachable từ roots**, không cần đi vào vòng để đặt next=null cho mục đích GC.

Đối với graph **còn một owner sống** nhưng muốn detach một nhánh:
- bỏ edge từ owner tới nhánh, hoặc
- update bidirectional links để domain invariant đúng,
- clear collection entries không còn cần.

Ví dụ một doubly linked list còn root→head, khi remove một node giữa list bạn phải sửa prev/next links để cấu trúc logic đúng; đây không phải “chữa GC không biết cycle”.

Nguyên tắc: **tìm cạnh giữ sống từ owner vào object graph** thay vì phá toàn bộ vòng mà không hiểu ownership.

## 38. Bảng phân tích tình huống

| Trường hợp | Kết luận reachability |
| --- | --- |
| A↔B, không GC root path | Có thể thành garbage |
| static root→A↔B | A/B reachable |
| root→B và B→A | A/B reachable |
| Root1→A, Root2→B, bỏ Root1 | Vẫn reachable từ Root2 |
| A→A không root | Self-loop không ngăn GC |
| global List giữ A, A↔B | List giữ cả vòng |
| listener registry giữ lambda capture Screen | Screen retained qua registry |
| long-lived ThreadLocal giữ cycle | Cycle retained qua ThreadLocal path |
| WeakReference là đường duy nhất tới cycle | Không tạo strong root path |
| WeakHashMap value giữ mạnh key | Key có thể vẫn strongly reachable |
| Method trả về sau khi tạo cycle, không escape | Cycle có thể thành unreachable |
| Resource object unreachable | Không đảm bảo external resource đóng đúng lúc |

## 39. Lỗi hiểu sai phổ biến

**“Vẫn có reference nên không bao giờ GC.”** Sai: references từ các objects unreachable không tự thành GC roots.

**“Vòng 2 objects cần gán cả hai next=null.”** Không cần nếu toàn bộ vòng đã unreachable.

**“Có cycle là memory leak.”** Không đúng; các cấu trúc hai chiều là bình thường.

**“Java chỉ dùng reference counting.”** Không đúng cho tracing collectors phổ biến của JVM.

**“Gán null rồi System.gc() bảo đảm weak.get()==null.”** Không được Java đảm bảo.

**“Ra khỏi scope thì heap phải giảm ngay.”** Không có timing guarantee; liveness và collection khác nhau.

**“Chỉ nhìn một biến null là đủ biết graph không còn root.”** Có thể còn cache, listener, thread, JNI hoặc static owner khác.

**“WeakHashMap tự xóa mọi leak.”** Weak keys không đủ nếu values/reference graph còn giữ keys hoặc owner vẫn cần logic eviction.

**“GC xử lý xong thì socket/file tự close.”** Dùng explicit close.

**“RSS không giảm nghĩa là collector không giải phóng cycles.”** Used heap/committed heap/RSS khác nhau; điều tra retention đúng công cụ.

## 40. Bài tập 1 — A↔B không root

Hai objects A/B trỏ nhau, không có bất kỳ root path nào tới chúng.

**Đáp án:** Cả A/B unreachable theo mô hình tracing; internal references không ngăn chúng đủ điều kiện thu gom.

## 41. Bài tập 2 — Root giữ một node

ROOT→A, A→B, B→A.

**Đáp án:** A và B đều reachable. Chỉ cần một root path vào cycle.

## 42. Bài tập 3 — Hai roots

ROOT1→A và ROOT2→B trong vòng A↔B. Xóa ROOT1→A.

**Đáp án:** Chưa đủ; ROOT2→B→A vẫn giữ cả vòng.

## 43. Bài tập 4 — Self-loop

Object A.next=A; biến local duy nhất rời scope, không object nào khác giữ A.

**Đáp án:** Self-loop không phải root. A có thể trở thành garbage; không có yêu cầu phải phá self-reference bằng tay.

## 44. Bài tập 5 — Reference counting

Vì sao một bộ đếm tham chiếu thuần túy có thể không giải phóng A↔B?

**Đáp án:** Sau khi mất external refs, A/B vẫn mỗi object có incoming edge từ object kia; counts chưa về 0. Tracing GC giải quyết qua root reachability.

## 45. Bài tập 6 — Static cache

Static Map giữ A; A↔B. Sau khi application không còn cần A/B, dùng gì?

**Đáp án:** Xóa/evict entry giữ A theo cache policy; nếu không còn root khác, cả vòng có thể thu gom. Không phải bẻ gãy mọi cạnh A/B.

## 46. Bài tập 7 — Listener

Static List<Runnable> giữ callback capture một Screen; Screen giữ model có vòng.

**Đáp án:** Registry là root owner giữ Screen/model. Unregister callback theo lifecycle.

## 47. Bài tập 8 — ThreadLocal

Một pooled thread còn giữ ThreadLocal value của request đã hoàn tất.

**Đáp án:** Dùng `try/finally` với `ThreadLocal.remove()`; không đợi GC thu hồi data còn reachable từ thread.

## 48. Bài tập 9 — WeakReference

Strong path tới A đã mất, WeakReference<A> vẫn tồn tại. Có cần weak.get() lập tức null?

**Đáp án:** Không. Nó không là strong root path, nhưng việc clear/reclaim xảy ra tùy thời điểm collector.

## 49. Bài tập 10 — WeakHashMap

Value của entry giữ strong reference tới chính key.

**Đáp án:** Weak key không tự thoát; đường map→value→key có thể giữ key reachable.

## 50. Bài tập 11 — Directed edge

ROOT→B; A→B; không B→A, không root khác→A.

**Đáp án:** B reachable; A không được suy ra reachable từ B vì edges có hướng.

## 51. Bài tập 12 — Parent-child cycle

Root của một cây không còn referenced, nhưng mọi child.parent trỏ lại parent.

**Đáp án:** Nếu không còn GC root path, toàn cây có thể thu gom. Back-references không ngăn tracing GC.

## 52. Bài tập 13 — System.gc

Một chương trình gọi System.gc() sau khi tạo A↔B và thấy WeakReference chưa cleared.

**Đáp án:** Không chứng minh cycle leak; System.gc() không hứa GC hoàn tất theo thời điểm test yêu cầu.

## 53. Bài tập 14 — Resource cleanup

Một object sở hữu socket nằm trong vòng, sau đó trở thành unreachable. Có nên đợi GC để socket đóng?

**Đáp án:** Không. Dùng explicit `close()` hoặc try-with-resources theo lifecycle.

## 54. Bài tập 15 — Task Manager

Sau khi clear listener registry, RSS của process không giảm ngay.

**Đáp án:** Không đủ bằng chứng leak. JVM có thể giữ committed heap; kiểm tra retained references và heap metrics đúng cách.

## 55. Bài tập 16 — Đọc heap paths

Heap dump cho thấy static cache→EventListener→Screen→A↔B.

**Đáp án:** Điều tra cache/listener ownership path và thời điểm cleanup. A/B cycle chỉ là phần graph được giữ, không phải nguyên nhân tự sinh root.

## 56. Bài tập 17 — Mô hình mark

Roots là {A}; A→B→C→A; D→E→D. Mark set gồm gì?

**Đáp án:** A, B, C. Vòng D/E unreachable từ A dù hai node trỏ nhau.

## 57. Bài tập 18 — Vòng và một strong path yếu?

ROOT→WeakReference→A↔B và không có strong/soft paths khác tới A/B.

**Đáp án:** Weak edge không trở thành strong path vào vòng. A/B có thể được collector xử lý theo weak reachability rules.

## 58. Bài tập 19 — Phân biệt GC và business lifecycle

A↔B đang được service active sử dụng; muốn đóng service và giải phóng các resources.

**Đáp án:** Thực hiện close/cancel/unsubscribe và release owner references theo API; GC sau đó có thể reclaim unreachable heap objects. Không dựa vào collector để thực hiện business shutdown.

## 59. Quy trình phân tích một chu trình nghi ngờ gây leak

1. **Vẽ graph.** Liệt kê object nodes và hướng references.
2. **Đánh dấu roots.** Static field? Active thread? Cache/listener? JNI?
3. **Duyệt strong edges từ roots.** Không duyệt ngược theo sở thích.
4. **Xác định object set reachable.** Có path vào cycle không?
5. **Phân biệt cần giữ hay không cần giữ.** Object reachable chưa chắc leak.
6. **Tìm owner path kéo dài quá lifecycle.** Cache entries, listeners, ThreadLocal, queues.
7. **Cắt owner path phù hợp.** Remove/unregister/clear/detach.
8. **Không bắt buộc phá toàn bộ cycle.** Nếu unreachable, collector xử lý được.
9. **Đóng external resources tường minh.** Không đợi GC.
10. **Đo bằng profiler nếu cần.** Retained heap/paths to roots, không chỉ RSS.
11. **Không assert GC timing.** Tránh nondeterministic weak-reference tests.
12. **Kiểm thử ownership cleanup.** Chứng minh cache/registry không còn giữ entries theo application contract.

## 60. Checklist cuối bài

- [ ] Tôi biết reference cycle không tự sinh GC root.
- [ ] Tôi phân biệt “has reference” và “root reachable”.
- [ ] Tôi hiểu strong-reference paths quyết định vòng có còn được giữ sống hay không.
- [ ] Tôi có thể vẽ A↔B và tìm đường root tới A/B.
- [ ] Tôi biết nhiều root paths cần được xét cùng lúc.
- [ ] Tôi biết khi root path vào vòng bị bỏ, cả vòng có thể trở thành garbage.
- [ ] Tôi hiểu tracing GC dùng visited/marked set để tránh lặp vô hạn.
- [ ] Tôi biết reference counting thuần túy có thể mắc kẹt ở cycles.
- [ ] Tôi không suy rộng điều đó cho mọi thuật toán reference counting.
- [ ] Tôi phân biệt eligible for GC và actual reclamation.
- [ ] Tôi không dự đoán GC chạy ngay khi method return.
- [ ] Tôi không nhầm phép gán null với free/destroy.
- [ ] Tôi biết fields/static collections/listeners/ThreadLocal có thể giữ owner path.
- [ ] Tôi biết GC không xóa objects còn reachable dù business không cần nữa.
- [ ] Tôi biết weak reference không giữ target mạnh.
- [ ] Tôi không phụ thuộc thời điểm weak.get() trả null.
- [ ] Tôi biết WeakHashMap có thể không loại entry nếu value giữ ngược key.
- [ ] Tôi không dùng finalize để kiểm chứng GC.
- [ ] Tôi không coi System.gc() là lệnh bảo đảm kết quả.
- [ ] Tôi biết try-with-resources dành cho tài nguyên cần close.
- [ ] Tôi phân biệt heap used, committed memory và RSS.
- [ ] Tôi biết tìm path to GC roots trong heap analyzer.
- [ ] Tôi phân biệt graph model runnable với việc đo actual JVM GC.
- [ ] Tôi biết chiều cạnh quyết định reachability.
- [ ] Tôi hiểu các cấu trúc parent-child/doubly linked có cycles là bình thường.
- [ ] Tôi có thể giải thích memory retention mà không đổ lỗi sai cho vòng references.

**Kết luận:** **Tham chiếu vòng A↔B không tự ngăn Java GC thu hồi A/B**, vì tracing collection tìm đối tượng sống bằng cách đi **từ GC roots theo các cạnh giữ sống**. Nếu không còn đường mạnh vào vòng, nội bộ vòng không giúp object tự được đánh dấu reachable. Nếu vòng vẫn ở trong retained heap, hãy tìm đường owner từ static caches, threads, listeners, ThreadLocal hoặc các roots khác. Đúng hướng xử lý là **quản lý ownership và lifecycle**, không phải phá các reference cycles chỉ để “ép Java thu gom rác”.
