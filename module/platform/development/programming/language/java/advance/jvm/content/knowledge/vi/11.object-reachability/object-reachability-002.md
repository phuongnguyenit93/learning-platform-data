# Đồ thị tham chiếu, đối tượng không còn truy cập được và tham chiếu vòng

## 1. Mục tiêu

Java tự động quản lý bộ nhớ của phần lớn đối tượng trên heap bằng **garbage collection (GC)**. Tuy vậy, muốn biết một đối tượng có thể được giải phóng không, ta phải xét **đường đi từ những gốc còn sống (GC roots)** đến đối tượng ấy, thay vì chỉ đếm bao nhiêu đối tượng đang trỏ tới nó.

Ba nhận định quan trọng:

1. **Có đường tham chiếu mạnh từ GC roots tới object:** object được coi là còn **strongly reachable** và không thể bị thu hồi như rác trong khi đường giữ sống đó còn hiệu lực.
2. **Không còn đường tham chiếu mạnh từ roots:** object có thể chỉ còn được truy cập qua soft/weak/phantom references hoặc đã unreachable; phải xét các quy tắc reference processing tương ứng.
3. **Hai object tham chiếu vòng nhau không tự tạo memory leak:** một cycle không còn được giữ từ roots có thể được tracing collector thu hồi, dù các object trong cycle vẫn trỏ tới nhau.

Sau bài học, bạn sẽ biết:

- Biểu diễn Java heap thành **đồ thị có hướng**: nodes là objects/arrays, edges là references, roots là tập điểm bắt đầu.
- Duyệt graph theo strong edges để xác định reachable và unreachable groups.
- Giải thích chính xác vì sao vòng **A → B → C → A** có thể hoặc không thể được GC thu hồi.
- Phân biệt **gán null**, **hết scope**, **eligible for GC**, **reference cleared** và **memory reclaimed**.
- Hiểu ý nghĩa của **strong**, **soft**, **weak**, **phantom references**, **ReferenceQueue** và **Reference.reachabilityFence** trong Java 17.
- Nhận diện **logical memory leaks**: graph vẫn reachable nhưng đã hết vòng đời nghiệp vụ.
- Phân tích **WeakHashMap**, static caches, listeners, ThreadLocal, thread pools, JNI references và class loaders bằng đường đi tới roots.
- Dùng Java 17+ để mô phỏng graph, quan sát weak references một cách không phụ thuộc GC timing, và dùng công cụ xem path to GC root/retained heap khi xử lý sự cố.

**Phạm vi:** bài giải thích ngữ nghĩa reachability và mô hình tracing GC. Chi tiết roots cụ thể, safepoints, marking barriers, thời điểm reclaim và class unloading có thể khác giữa các JVM/collectors.

## 2. Đồ thị tham chiếu của đối tượng

Định nghĩa mô hình:

- **Đỉnh (vertex/node):** một Java object hoặc array instance.
- **Cạnh (directed edge):** một tham chiếu từ object A tới object B, ví dụ A.child = B hoặc A.elements[0] = B.
- **GC root:** một tham chiếu điểm xuất phát được collector coi là live trong trạng thái hiện tại của VM.
- **Path:** chuỗi cạnh có hướng nối một root tới một object.
- **Strongly reachable:** object có thể được truy cập từ nguồn còn sống mà không cần đi qua referent của Reference object (SoftReference/WeakReference/PhantomReference).
- **Unreachable:** không còn reachable qua các cấp độ quy định của java.lang.ref; đủ điều kiện để memory được reclaim khi JVM quyết định.

Sơ đồ giả định tất cả cạnh thường là strong:

~~~text
 GC ROOTS
   local session             static Registry.sessions
        |                             |
        v                             v
   Session A                      Cache C
        |                             |
        v                             v
   Account B                      Entry D
        |                             |
        v                             v
   Profile E                      Buffer F

 Nhóm không có đường từ roots:
     X ------------> Y
     ^               |
     |               |
     +---------------+
~~~

Có đường mạnh từ roots tới **A,B,C,D,E,F**, vì vậy nhóm này còn reachable. **X và Y** trỏ vòng nhau nhưng không có root path, nên chúng không được giữ sống chỉ nhờ tham chiếu qua lại.

**Cảnh báo:** Sơ đồ chỉ minh họa. Nếu ngoài hình còn một live local, static field, JNI global reference hoặc đường từ object khác trỏ tới X/Y, kết luận về nhóm ấy phải đổi.

### 2.1. Tham chiếu là cạnh, không phải object được copy

~~~java
// Minh họa bên trong một method:
Object a = new Object();
Object b = a;
~~~

Đây là **một object**, hai variables cùng tham chiếu tới nó. Gán **a = null** xóa một cạnh từ biến a, nhưng **b** vẫn có thể giữ object nếu b còn live. Không phải lệnh gán null “hủy object”.

Trong heap, mỗi field reference và phần tử object array có thể tạo thêm cạnh:

~~~java
// Minh họa:
Node parent = new Node();
Node child = new Node();
parent.next = child;
~~~

Nếu parent reachable, child cũng reachable qua **parent.next** cho tới khi cạnh thay đổi hoặc parent không còn được giữ.

### 2.2. Đường có hướng: A → B không đồng nghĩa B → A

Nếu A.next = B, thì reachability từ A đến B có thể tồn tại, nhưng từ B về A **chưa chắc** tồn tại. Đối với GC graph, hướng cạnh quan trọng.

**Một cạnh weak** có ngữ nghĩa khác strong edge: bản thân WeakReference wrapper có thể strongly reachable từ root, nhưng điều đó không đồng nghĩa referent được giữ mạnh. Đừng vẽ root→WeakReference→referent như hai strong arrows rồi kết luận referent không được GC.

## 3. GC roots có thể đến từ đâu?

Ở HotSpot và nhiều VM thực tế, tập roots bao gồm các nhóm tham chiếu đang live như:

| Nguồn có thể là root | Ví dụ |
| --- | --- |
| Execution state của thread đang sống | Live local reference, operand/register values cần cho computation |
| Static state từ runtime classes còn live | Static cache, singleton, registry |
| JNI/native global references | Native code giữ Java object qua JNI GlobalRef |
| VM/internal runtime structures | Tham chiếu VM cần duy trì trong loading, synchronization và runtime subsystems |
| Các runtime-managed handles | Những handles được collector cụ thể tính đến |

**Không nên học thuộc một danh sách cố định cho mọi JVM.** Root discovery khác nhau giữa implementations/collectors; một số công cụ phân tích heap biểu diễn thêm synthetic roots để dựng đồ thị.

### 3.1. Local variable sống đến khi nào?

Một tên biến nằm trong cặp dấu ngoặc nhọn của Java source **không đảm bảo** object được giữ tới dấu ngoặc đóng. JIT/compiler có thể chứng minh một reference không còn cần thiết trước khi hết lexical scope, theo những ngữ nghĩa được phép.

Trong trường hợp cần giữ object strongly reachable đến một mốc liên quan cleanup/reference processing, Java 17 cung cấp:

~~~java
Reference.reachabilityFence(resource);
~~~

Lời gọi này giữ **strong reachability ít nhất tới sau invocation**, không tự gọi GC và không pin object tại một memory address nhất định.

### 3.2. Static state cũng có vòng đời

~~~java
class Registry {
    static final java.util.List<Object> ITEMS =
            new java.util.ArrayList<>();
}
~~~

Nếu runtime class Registry và static state của nó còn live, **ITEMS** có thể giữ mạnh các objects trong list. Nhưng **static** không phải một hợp đồng “vĩnh viễn tồn tại dù class loader đã có thể unload”; trong các plugin/application servers, class loader lifetime có vai trò quan trọng.

## 4. Marking: tìm tập reachable bằng duyệt graph

Một phép duyệt graph mang tính khái niệm:

~~~text
function markReachable(rootReferences):
    worklist = new Queue()
    visited  = new IdentitySet()

    for each rootReference:
        if rootReference != null:
            worklist.add(rootReference.target)

    while worklist not empty:
        object = worklist.remove()
        if object in visited:
            continue

        visited.add(object)
        for each strong reference field/array element of object:
            if referent != null:
                worklist.add(referent)

    return visited
~~~

Những objects trong visited là strong-reachable **theo snapshot và root set của mô hình**. Phần graph không được đánh dấu sẽ không được giữ mạnh từ các roots ấy.

Sử dụng **IdentitySet**, không dùng business equals(), bởi hai objects có thể bằng nhau về nội dung nhưng khác object identities; GC quyết định trên object identities.

### 4.1. Cycle không làm duyệt graph lặp vô hạn

Với:

~~~text
A ---> B ---> C
^             |
+-------------+
~~~

Khi gặp lại A, thuật toán kiểm tra **visited** và bỏ qua. Cycle không ngăn traversal kết thúc. Một tracing GC có thể đánh dấu và thu hồi nhóm không reachable từ roots mà không cần “tháo từng cạnh bên trong cycle”.

Duyệt BFS/DFS một graph có N nodes và E edges thường có độ phức tạp **O(N+E)** trong mô hình, với cấu trúc visited phù hợp. Đây là bài tập thuật toán, không phải khẳng định mọi collector HotSpot triển khai đúng queue và visited objects bằng Java collections.

## 5. Tham chiếu vòng: có root và không có root

Trường hợp có root:

~~~text
ROOT --> A --> B --> C
         ^           |
         +-----------+
~~~

Từ ROOT tới A, rồi B rồi C, tất cả strongly reachable. Lúc này cycle tồn tại và được giữ bởi **ROOT → A**, không phải do cycle tự duy trì khả năng truy cập từ JVM.

Trường hợp không root:

~~~text
      A --> B --> C
      ^           |
      +-----------+
  Không còn đường strong từ roots vào nhóm.
~~~

Nếu không có cơ chế khác giữ chúng, nhóm A/B/C đủ điều kiện để thu hồi bằng GC dựa trên reachability.

### 5.1. Ví dụ vòng hai node

~~~java
// Mã minh họa, Node có field Node next:
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;

a = null;
b = null;
~~~

Nếu không còn edges khác từ roots tới a/b, cycle không tự ngăn GC. Nhưng nếu trước đó chương trình đã ghi **CACHE.put("cycle", a)** thì CACHE có thể giữ a và cả b; chỉ gán các locals thành null không xóa cache entry.

### 5.2. Reference counting thuần túy khác tracing GC

Reference counting cơ bản có thể giữ lại cycle vì mỗi object vẫn có incoming reference từ object còn lại, khiến count không về 0. Tracing GC quyết định sống/chết bằng root paths, nên cycle không rooted có thể được thu hồi.

So sánh này chỉ đúng với **reference counting thuần túy không có cycle collection**. Một số runtime sử dụng ref counting nhưng bổ sung cơ chế phát hiện cycle; không nên tuyệt đối hóa thành “mọi ref-counting system đều leak cycles”.

### 5.3. Strongly connected components (SCC)

Một nhóm nodes **strongly connected** nếu mỗi node có đường có hướng tới mọi node khác trong nhóm. SCC là công cụ hữu ích để suy luận về cycles. Tuy nhiên GC không bắt buộc phân tích SCC rồi mới reclaim; chỉ cần quan hệ reachability đúng theo collector semantics.

## 6. Ví dụ Java 17+ số 1 — Tự duyệt một object graph

Tạo file **ReachabilityGraphDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ReachabilityGraphDemo {
    static final class Node {
        final String name;
        Node next;

        Node(String name) {
            this.name = name;
        }
    }

    static Set<Node> markFrom(Node... roots) {
        Set<Node> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());
        ArrayDeque<Node> queue = new ArrayDeque<>();

        for (Node root : roots) {
            if (root != null) {
                queue.addLast(root);
            }
        }

        while (!queue.isEmpty()) {
            Node node = queue.removeFirst();
            if (!visited.add(node)) {
                continue;
            }
            if (node.next != null) {
                queue.addLast(node.next);
            }
        }

        return visited;
    }

    static String sortedNames(Iterable<Node> nodes) {
        TreeSet<String> names = new TreeSet<>();
        for (Node node : nodes) {
            names.add(node.name);
        }
        return names.toString();
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");
        Node d = new Node("D");
        Node e = new Node("E");

        a.next = b;
        b.next = c;
        c.next = a;
        d.next = e;
        e.next = d;

        Set<Node> reachable = markFrom(a);
        List<Node> all = Arrays.asList(a, b, c, d, e);
        Set<Node> notReached =
                Collections.newSetFromMap(new IdentityHashMap<>());
        notReached.addAll(all);
        notReached.removeAll(reachable);

        System.out.println("reachable=" + sortedNames(reachable));
        System.out.println("notReached=" + sortedNames(notReached));
        System.out.println("cycleA=" + (c.next == a));
        System.out.println("cycleD=" + (e.next == d));
    }
}
~~~

Biên dịch/chạy bằng Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 ReachabilityGraphDemo.java
java ReachabilityGraphDemo
~~~

**Stdout chính xác:**

~~~text
reachable=[A, B, C]
notReached=[D, E]
cycleA=true
cycleD=true
~~~

Giải thích:

1. Root của **phép mô phỏng** là a.
2. Thuật toán đi a→b→c→a và dừng vì a đã visited.
3. d/e tạo một cycle riêng không có đường từ root a nên không được đánh dấu.
4. **Cả hai nhóm có cycles**, nhưng chỉ nhóm a/b/c reachable từ root lựa chọn.

**Giới hạn cực kỳ quan trọng:** Chương trình đang giữ references tới d và e trong locals và collection **all** để tính toán. Do đó **notReached=[D,E] là kết quả của mô hình duyệt**, không phải chứng cứ JVM GC coi d/e là unreachable thật! Muốn kiểm tra GC thật cần xét root set thật và reference processing, không dùng một biến Java **notReached** do mình dựng làm nguồn sự thật.

### 6.1. Vì sao không dùng HashSet thông thường?

Nếu Node override equals() dựa vào name, hai Node objects khác identity nhưng cùng name có thể bị HashSet nhập thành một. **IdentityHashMap** đảm bảo so sánh objects theo reference identity, phù hợp graph simulation cho heap.

## 7. Phân biệt bốn giai đoạn thường bị trộn

| Tình huống | Điều có thể kết luận |
| --- | --- |
| **Một local bị gán null** | Đã xóa một reference edge cụ thể; chưa biết object có còn root path khác không |
| **Không còn strong path từ roots** | Object có thể chỉ softly/weakly/phantom reachable hoặc unreachable hoàn toàn |
| **Eligible for collection** | JVM có thể thu hồi khi GC chạy/phù hợp; **không có deadline** |
| **Memory reclaimed** | Collector đã thực sự xử lý và thu hồi; không thể chỉ suy từ gán null |

### 7.1. System.gc() không bảo đảm thời điểm thu gom

~~~java
Object value = new Object();
value = null;
System.gc();
~~~

Không có contract đảm bảo collector đã reclaim đúng object sau lời gọi. Trong một số cấu hình, explicit GC có thể bị vô hiệu hóa/điều chỉnh; collector có thể không xử lý object theo đúng lịch thời gian của test.

**Đừng assert** WeakReference.get()==null ngay sau System.gc() rồi coi test là chuẩn Java.

### 7.2. Heap used, committed và RSS khác nhau

Nếu collector thu hồi nhiều objects, heap **used** có thể giảm, nhưng JVM vẫn giữ memory **committed/reserved** để cấp phát sau. RSS của process còn liên quan native memory, code cache, stacks, metaspace và page management. Không suy “một graph không còn reachable” thành “RSS giảm đúng số byte” vào cùng thời điểm.

## 8. Strong, soft, weak và phantom reachability

Java SE 17 cung cấp package **java.lang.ref**. Các reference objects cho phép chương trình quan sát một phần vòng đời của referent mà không nhất thiết giữ nó bằng một strong edge.

| Loại | Có giữ object như một reference field mạnh thông thường? | Dùng khi nào? |
| --- | --- | --- |
| **Strong reference** | Có | Ownership/reference thường |
| **SoftReference** | Không theo mức strong; collector có thể clear theo memory demand | Một số memory-sensitive caches |
| **WeakReference** | Không; GC có thể clear khi referent chỉ weakly reachable | Weak-key mappings, canonical registry |
| **PhantomReference** | Không dùng để đọc referent; get() luôn null | Lifecycle notification/cleanup bookkeeping |
| **ReferenceQueue** | Không phải một kiểu reachability của referent | Nhận các Reference objects sau khi collector enqueue |

Các mức trong tài liệu java.lang.ref đi theo chuỗi **strong → soft → weak → phantom → unreachable**. Việc object có một weak reference trỏ đến **không** ngăn nó bị reclaim mãi.

### 8.1. WeakReference không giữ referent sống

~~~java
// Minh họa trong một method:
Object o = new Object();
WeakReference<Object> weak = new WeakReference<>(o);
~~~

Bản thân **weak** là một Java object. Nếu một root trỏ mạnh đến wrapper **weak**, wrapper còn sống; nhưng **referent o** có thể bị clear/reclaimed khi không còn strong/soft paths phù hợp.

### 8.2. SoftReference không có TTL hoặc “sống tới khi hết RAM” contract

Soft reference được clear theo chính sách VM và điều kiện memory. Không được dùng như một cơ chế cache có eviction timing/size chính xác. Nếu cached value biến mất, code phải tạo lại được một cách an toàn.

### 8.3. PhantomReference.get() luôn trả null

Phantom references thường phối hợp **ReferenceQueue** để nhận notification, không phải phương thức lấy object đã “chết”. Dùng **Cleaner** hoặc PhantomReference khi thiết kế cleanup cần cơ chế hậu kiểm, nhưng không dựa vào GC để đóng socket/file/DB connection đúng hạn.

### 8.4. Finalization là giải pháp lịch sử không nên phụ thuộc

Java object finalization có các vấn đề về reliability, performance và security; trên JDK 17 nó đã bị deprecate. Không dùng **finalize()** để xây dựng logic giao dịch hoặc quản lý tài nguyên bắt buộc. **try-with-resources** và explicit close() phù hợp hơn cho tài nguyên có lifecycle rõ.

## 9. Ví dụ Java 17+ số 2 — WeakReference với stdout xác định

Tạo **WeakReferenceDemo.java**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak = new WeakReference<>(strong);

        System.out.println("whileStrong=" + (weak.get() != null));
        Reference.reachabilityFence(strong);

        strong = null;
        System.out.println("afterDrop=timing-not-guaranteed");
        System.out.println("wrapperAlive=" + (weak != null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 WeakReferenceDemo.java
java WeakReferenceDemo
~~~

**Stdout:**

~~~text
whileStrong=true
afterDrop=timing-not-guaranteed
wrapperAlive=true
~~~

- Khi in **whileStrong**, **strong** được bảo đảm giữ reachable tới sau **Reference.reachabilityFence(strong)** nên referent chưa bị reclaim tại bước đọc.
- Sau **strong=null**, chương trình cố ý không in weak.get() vì kết quả sau GC là bất định.
- **wrapperAlive=true** chỉ nói Java reference wrapper chưa null; không có nghĩa referent còn strong reachable.

Để quan sát GC, có thể thêm:

~~~java
// Đoạn thêm vào main, kết quả KHÔNG cố định:
System.gc();
System.out.println("stillPresent=" + (weak.get() != null));
~~~

**stillPresent** có thể true hoặc false tùy GC, references khác và timing. Không dùng output đó làm bài toán có một stdout chuẩn.

## 10. ReferenceQueue: nhận thông báo nhưng không điều khiển GC

Ví dụ minh họa (cần các imports của java.lang.ref):

~~~java
ReferenceQueue<Object> queue = new ReferenceQueue<>();
Object referent = new Object();
WeakReference<Object> watch = new WeakReference<>(referent, queue);
referent = null;
Reference<?> notice = queue.poll();
~~~

Không thể khẳng định **notice != null** ngay khi gán referent=null. Queue có thể nhận reference sau khi collector xác định thay đổi reachability tương ứng.

**Cần giữ chính Reference wrapper reachable** khi muốn nhận notification: việc đăng ký nó vào queue không có nghĩa queue luôn giữ nó sống từ lúc đăng ký. Nếu wrapper bị mất, ứng dụng có thể không thấy thông báo mà mình muốn xử lý.

### 10.1. Tránh tự ngăn referent bị GC

Một lớp kế thừa WeakReference có thêm field **strongReferent** trỏ lại referent sẽ tạo đường strong vô tình, làm referent không còn weakly reachable như mong muốn. Với cleanup metadata, lưu các thông tin độc lập như identifier/native handle thay vì giữ mạnh chính referent.

### 10.2. Dùng try-with-resources cho tài nguyên bên ngoài

~~~java
// Minh họa; path là java.nio.file.Path đã khai báo:
try (java.io.InputStream in =
             java.nio.file.Files.newInputStream(path)) {
    // Xử lý dữ liệu.
}
~~~

Đây không phải chương trình độc lập; cần biến path và xử lý IOException. **close()** được gọi khi rời try-with-resources theo ngữ nghĩa Java, không chờ GC.

## 11. WeakHashMap: weak key vẫn có thể bị value giữ mạnh

WeakHashMap sử dụng weak references cho **keys**, còn **values** thường được map giữ bằng strong references. Đây là bẫy rất phổ biến:

~~~text
GC Root ---> WeakHashMap
                |
                +-- weak key ------> Key K
                |
                +-- strong value --> Value V
                                       |
                                       +-- strong field --> Key K
~~~

Nếu Value tham chiếu mạnh ngược tới Key, đường **root → map → value → key** vẫn tồn tại, dù entry key bên trong map là weak. Key vì vậy có thể không bao giờ đủ điều kiện xóa theo ý định ban đầu.

### 11.1. Ví dụ Java 17+ số 3 — Key được giữ bởi value

Tạo file **WeakMapPitfallDemo.java**:

~~~java
import java.util.WeakHashMap;

public class WeakMapPitfallDemo {
    static final class Key {
        final int id;

        Key(int id) {
            this.id = id;
        }
    }

    static final class Value {
        final Key backReference;

        Value(Key key) {
            this.backReference = key;
        }
    }

    static final WeakHashMap<Key, Value> CACHE =
            new WeakHashMap<>();

    public static void main(String[] args) {
        Key key = new Key(7);
        Value value = new Value(key);
        CACHE.put(key, value);

        key = null;
        value = null;

        System.out.println("entries=" + CACHE.size());
        System.out.println("valueBackReference=true");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 WeakMapPitfallDemo.java
java WeakMapPitfallDemo
~~~

**Stdout:**

~~~text
entries=1
valueBackReference=true
~~~

**Giải thích:** CACHE là static collection được main sử dụng; nó mạnh tới Value, còn Value.backReference mạnh tới Key. Cả graph reachable dù hai locals được gán null. Dòng thứ hai mô tả đường back-reference trong cấu trúc class, không phụ thuộc việc GC có chạy.

Nếu Value không trỏ ngược Key, một key không còn strong path có thể được reclaim, nhưng thời điểm entry biến mất/size() đổi không được bảo đảm ngay sau local=null.

### 11.2. Dùng weak references đúng nhu cầu

WeakHashMap thích hợp khi map không muốn là owner sống lâu của keys. Tuy nhiên:

- Có thể tồn tại root paths khác tới keys.
- Values có thể giữ keys hoặc giữ objects tham chiếu keys.
- Clear/enqueue/expunge không nhất thiết đồng bộ với dòng code vừa set null.
- Nếu cần bounded cache/eviction chính xác, weak key một mình chưa đủ.

## 12. Logical memory leak trong Java

**Memory leak về mặt logic** thường không phải “GC không biết thu hồi một object unreachable”. Nó thường là một **object graph vẫn reachable** nhưng **đã hết thời hạn sử dụng theo thiết kế ứng dụng**.

Ví dụ:

~~~text
Static Registry (rooted)
      |
      v
Map<UserId, Session>
      |
      +--> Session1 --> Cart --> ProductGraph
      +--> Session2 --> Cart --> ProductGraph
      +--> Session3 --> Cart --> ProductGraph
      +--> ...
~~~

Nếu ứng dụng liên tục thêm sessions mà không remove/expire, các graphs vẫn reachable. GC **đúng khi không thu hồi** chúng. Phải sửa lifecycle collection thay vì gọi System.gc() nhiều hơn.

### 12.1. Các root paths điển hình tạo leak

| Nguồn | Đường giữ sống | Cách sửa |
| --- | --- | --- |
| **Static cache/map** | Root → static → map → values → graph | Max size, TTL, eviction, remove |
| **Event bus/listener registry** | Root → publisher → listener → captured object | Unsubscribe tại lifecycle stop |
| **ThreadLocal** | Live thread → ThreadLocalMap → value → graph | remove() trong finally |
| **Thread pool/executor** | Thread/queue → task → captured closure | Complete/cancel task, shutdown pool |
| **Class loader** | Root → TCCL/registry → loader → classes/metadata | Clear references, stop worker threads |
| **HTTP sessions** | Session manager → session → large graph | Expire/invalidate, giới hạn dữ liệu |
| **Object pool** | Root → pool → idle objects | Bound pool, release entries |
| **JNI GlobalRef** | VM/native root → object graph | Delete global reference theo lifecycle |

**ThreadLocal trong thread pool** cần chú ý: request kết thúc không đồng nghĩa pooled thread kết thúc. Nếu value không được remove, nó có thể giữ request graph qua nhiều lượt xử lý.

### 12.2. Event listener gây leak không phải do cycle

~~~text
Long-lived Publisher --> Listener --> View
                              ^         |
                              |         |
                              +---------+
~~~

Cycle Listener↔View không tự làm leak. Nhưng Publisher được root giữ và tham chiếu Listener, nên toàn bộ nhóm vẫn reachable. Unsubscribe Listener có thể cắt đường root, nếu không còn đường giữ khác.

### 12.3. ClassLoader và redeploy

Một web container nạp plugin bằng Loader-v1, sau đó redeploy Loader-v2. Nếu pooled thread còn **contextClassLoader = Loader-v1**, loader v1 và metadata/classes/objects liên quan có thể còn reachable. Class unloading sẽ không giải phóng chúng như mong muốn cho đến khi lifecycle/reference paths phù hợp được giải quyết.

Đó là memory retention qua **GC root path**, không phải việc “GC không xử lý reference cycle”.

## 13. Shallow size, retained size và dominators

Các heap analyzers thường dùng:

- **Shallow size:** số byte của chính object, không cộng tất cả descendants.
- **Retained size:** kích thước graph chỉ còn reachable nhờ object/dominator được xét, theo mô hình công cụ.
- **Dominator:** node D thống trị X nếu mọi đường từ super-root tới X đều đi qua D.
- **Path to GC Root:** một hoặc nhiều đường chỉ ra lý do object vẫn reachable.
- **Incoming references:** những objects/roots đang trỏ đến object bị nghi ngờ.

Ví dụ:

~~~text
Root --> Cache --> Entry --> byte[10_000_000]
~~~

Cache có thể shallow size nhỏ nhưng retained size rất lớn nếu không có root path khác tới byte array. Ngược lại:

~~~text
Root1 --> CacheA --> SharedObject
Root2 --> CacheB --> SharedObject
~~~

Xóa CacheA chưa chắc khiến SharedObject eligible; Root2→CacheB vẫn giữ. Một **shortest path to GC Root** hữu ích nhưng không nhất thiết là đường duy nhất. Không suy leak root cause từ một path duy nhất khi object có nhiều owners hợp lệ.

### 13.1. Tại sao nên xem dominator tree?

Thay vì chỉ sắp xếp object classes theo số instance, dominator tree chỉ ra object/collection nào đang giữ độc quyền nhiều memory nhất. Ví dụ một ArrayList shallow nhỏ nhưng quản lý hàng trăm nghìn listeners với capture graphs lớn mới là điểm cần điều tra.

Đừng cộng hai retained sizes một cách tùy tiện vì graphs có thể trùng hoặc có quan hệ chi phối khác nhau.

## 14. GC timing và concurrent collectors

HotSpot có thể dùng các collectors khác nhau: Serial, Parallel, G1, ZGC và các biến thể theo JDK. Một số tiến hành marking concurrently, dùng barriers và nhiều chu kỳ GC.

Điều bất biến ở mức ngữ nghĩa:

- Java code không có deadline rằng object unreachable sẽ reclaimed trong X mili-giây.
- JVM phải duy trì memory safety và reference semantics khi objects/fields được cập nhật.
- Object graph thay đổi theo hoạt động của threads; sơ đồ trên giấy là snapshot lý tưởng.
- GC có thể di chuyển objects và cập nhật references; reference identity/equals semantics của Java vẫn được giữ.
- Một object không còn cần ở tầng business nhưng vẫn strongly reachable thì collector không được tự ý bỏ nó như garbage chỉ để giảm heap.

### 14.1. GC là cơ chế bộ nhớ, không phải transaction cleanup

Nếu bạn cần đóng file, socket, cursor hoặc DB transaction theo thời hạn, dùng explicit close/try-with-resources. GC/ReferenceQueue/Cleaner được dùng cho những trường hợp cleanup bổ trợ có chấp nhận tính bất định, không phải cơ chế commit/rollback.

## 15. Dùng công cụ để xem đường tới GC roots

### 15.1. Quan sát trước khi thu thập heap dump

Hỏi:

1. Có loại object nào tăng sau mỗi request/task dù lifecycle đã kết thúc?
2. Cache size/listener count/thread count có tăng mà không đạt trạng thái ổn định?
3. Object count và live heap qua các mốc đo có tăng liên tục hay chỉ tăng do warm-up?
4. Có plugin class loaders cũ còn tồn tại sau redeploy?
5. GC log cho thấy heap usage khác sau collection so với trước không?

Một memory snapshot duy nhất thường **không đủ** chứng minh leak. Cần trend theo workload và hiểu ownership.

### 15.2. jcmd và GC logs của HotSpot Java 17

Ví dụ (lệnh thay **<PID>** bằng process ID thật):

~~~bash
java -Xlog:gc*=info YourMainClass
jcmd
jcmd <PID> help
jcmd <PID> GC.heap_info
jcmd <PID> GC.class_histogram
~~~

Các commands và chi tiết output phụ thuộc JDK/JVM, quyền attach và cấu hình. **YourMainClass** là placeholder cho main class thực. Với hệ production, cân nhắc chi phí chẩn đoán và chính sách dữ liệu.

### 15.3. Heap dump

Trong môi trường được phép, HotSpot có thể hỗ trợ:

~~~bash
jcmd <PID> GC.heap_dump /path/to/heap.hprof
~~~

Heap dump có thể rất lớn và chứa dữ liệu cá nhân/bí mật của ứng dụng. Chụp dump có thể tác động latency hoặc gây GC theo options. Không thực hiện trên production mà chưa xem chi phí, quyền và hướng dẫn vận hành phù hợp.

Một số công cụ phân tích:

- **Eclipse Memory Analyzer (MAT):** dominator tree, retained heap, paths to GC roots.
- **VisualVM:** heap dump và heap sampling.
- **Java Flight Recorder (JFR):** allocation/runtime profiling tùy event configuration.
- **jcmd GC.class_histogram:** phân bố instances tại một thời điểm.

Các công cụ có thể biểu diễn soft/weak/phantom reference edges khác strong paths. Khi tìm leak, chọn bộ lọc đúng và không vô tình coi weak referent như đường mạnh giữ object.

## 16. Quy trình debug memory leak theo đồ thị

**Bước 1.** Reproduce với input/workload tương đương; ghi số sessions/tasks/objects được tạo và hoàn thành.

**Bước 2.** Thu metrics và snapshot tại các mốc có thể so sánh được (sau warm-up, sau cleanup), tránh so một peak với một idle snapshot.

**Bước 3.** Xác định classes/arrays tăng số lượng và nơi allocation.

**Bước 4.** Xem dominators có retained size cao; đừng chỉ nhìn shallow size.

**Bước 5.** Mở **path to GC root** cho một object hết vòng đời. Xác định static cache, live thread, ThreadLocal, listener, JNI hay class loader nào giữ.

**Bước 6.** Nếu thấy cycle, hỏi “root path vào cycle ở đâu?”. Cycle không phải nguyên nhân tự thân.

**Bước 7.** Sửa đúng **ownership/lifetime**: remove/evict/cancel/unsubscribe/close, cleanup trong finally hoặc scope phù hợp.

**Bước 8.** Đo lại dưới cùng workload. Xác minh object counts/retained graph trở về baseline hoặc ổn định.

**Bước 9.** Kiểm tra concurrent access và race conditions của caches/registries.

**Bước 10.** Thiết lập giới hạn và monitoring dài hạn thay vì phụ thuộc thao tác GC thủ công.

## 17. Các sai lầm phổ biến

1. **“Java thu gom rác khi reference count về 0.”** Không đúng như một quy tắc chung của tracing GC.
2. **“A ↔ B luôn memory leak.”** Sai nếu cycle không còn root path.
3. **“Xóa một local bằng null bảo đảm object được reclaim.”** Sai nếu còn references khác hoặc GC chưa chạy.
4. **“System.gc() chắc chắn dọn mọi object chết.”** Sai về timing/guarantee.
5. **“Strongly reachable chỉ cần object có một incoming edge bất kỳ.”** Sai: cần đường giữ từ roots.
6. **“WeakReference wrapper còn sống tức referent còn sống.”** Sai: wrapper và referent là hai objects.
7. **“WeakReference.get() lập tức null sau value=null.”** Sai: reference processing không đồng bộ với gán null.
8. **“SoftReference là cache TTL cố định.”** Sai: collector policy quyết định clearing.
9. **“PhantomReference.get() trả object khi sắp GC.”** Sai: get luôn null.
10. **“WeakHashMap value không thể giữ key.”** Sai: value→key có thể tạo strong path.
11. **“Có GC nên Java không leak.”** Sai: graph còn reachable nhưng không còn cần là leak logic.
12. **“Mọi local trong source scope luôn là root đến cuối block.”** Sai: JIT liveness có thể ngắn hơn.
13. **“Static field chắc chắn là root tồn tại tới hết process.”** Không tuyệt đối; class-loader lifecycle có ảnh hưởng.
14. **“Một heap dump có nhiều objects đã chứng minh leak.”** Sai: cần trend và lý do ownership.
15. **“Shallow size và retained size giống nhau.”** Sai: retained graph có thể rất lớn.
16. **“Dominator chỉ là object có nhiều incoming references nhất.”** Sai: mọi đường từ super-root tới node mới là tiêu chí.
17. **“Cycles xuất hiện trong heap dump nghĩa là GC không xử lý.”** Sai: snapshot có thể chứa objects còn reachable hoặc chưa reclaimed theo lịch.
18. **“Class loader mới tự giải phóng loader cũ.”** Sai nếu old loader còn reachable.
19. **“ReferenceQueue.poll() khác null ngay sau System.gc().”** Không được bảo đảm.
20. **“Cleanup native resource phải đợi finalizer/Cleaner.”** Sai: ưu tiên explicit lifecycle.

## 18. Bài tập tự kiểm tra có lời giải

**Câu 1.** ROOT→A→B→A. Nếu xóa ROOT→A và không còn root path khác, A/B có eligible for collection không?

**Đáp án:** Có theo mô hình reachability. Cycle A/B tự nó không tạo root path.

**Câu 2.** ROOT→A→B→C→A. Có bao nhiêu node strongly reachable từ ROOT?

**Đáp án:** A, B, C (ba nodes).

**Câu 3.** Object X được tham chiếu bởi hai locals p và q. p=null. X có trở thành unreachable ngay không?

**Đáp án:** Không nếu q vẫn live; còn phải xét static/other paths.

**Câu 4.** Graph A→B, B→C, C→B; D→E, E→D. Root model là A. Reachable?

**Đáp án:** A,B,C; D,E không có path từ root model, mặc dù cả hai nhóm có cycles.

**Câu 5.** Vì sao tracing GC thu hồi cycle unreachable mà basic reference counting không tự thu hồi?

**Đáp án:** Tracing dựa vào root reachability; basic ref count không về 0 do incoming edges nội bộ cycle.

**Câu 6.** Trong mã x=null; System.gc(); weak.get()==null có phải luôn true không?

**Đáp án:** Không. GC có thể không chạy/thực hiện kịp, referent có thể còn references khác.

**Câu 7.** Static WeakHashMap<Key, Value> có Value.backReference tới Key. Gán local key=null có chắc key collect được không?

**Đáp án:** Không. Static map giữ value mạnh, value giữ key mạnh.

**Câu 8.** Live pooled thread giữ ThreadLocal value là request data. Request xong rồi nhưng value chưa remove. Vì sao graph còn reachable?

**Đáp án:** Thread→ThreadLocalMap→value vẫn là strong path, có thể giữ cả graph.

**Câu 9.** Root1→A→X, Root2→B→X. Xóa root1→A có làm X unreachable không?

**Đáp án:** Không; root2 vẫn giữ X.

**Câu 10.** PhantomReference.get() trả referent lúc nào?

**Đáp án:** Không bao giờ trả referent; luôn null.

**Câu 11.** Một object shallow 32 bytes nhưng giữ độc quyền 100 MB arrays. Retained size có thể lớn không?

**Đáp án:** Có; retained size phản ánh graph bị giữ độc quyền qua object/dominator.

**Câu 12.** Heap histogram cho thấy 500 session objects sau load test. Có đủ kết luận leak?

**Đáp án:** Chưa; cần biết lifecycle, pending sessions, GC trạng thái, trend và paths to root.

**Câu 13.** Khi thấy cycle trong DOM tree và màn hình đã đóng, nên hỏi câu gì?

**Đáp án:** Có root path nào như listener/static cache/thread còn giữ tree hay không? Cycle tự thân không đủ kết luận leak.

**Câu 14.** Java GC tự giải phóng file descriptor đúng lúc rời method không?

**Đáp án:** Không được bảo đảm; dùng try-with-resources hoặc explicit close.

**Câu 15.** Tại sao mô phỏng graph bằng List all chứa toàn bộ nodes không chứng minh nodes “notReached” là GC-unreachable?

**Đáp án:** Chính List all và locals đang giữ strong references tới nodes; root set của thuật toán chỉ là đầu vào giả định, không phải roots thật của VM.

## 19. Checklist ghi nhớ

- Reachability là **đường đi từ GC roots**, không phải reference count.
- Duyệt graph theo **strong edges**, có **visited** để xử lý cycles.
- Một cycle không rooted **có thể** thu hồi; không có deadline bắt buộc.
- Gán null chỉ cắt **một cạnh**, không xóa object theo lệnh.
- **Eligible** khác **reclaimed**, và System.gc không quyết định được thời điểm.
- Weak/soft/phantom references có ngữ nghĩa khác strong; queue notification bất định.
- WeakHashMap vẫn có thể leak nếu value tham chiếu key.
- Java memory leaks thường là **graph còn reachable quá lâu** qua cache/listener/ThreadLocal/thread/class loader.
- Đọc heap dump bằng **paths to GC roots**, **dominator tree**, **retained sizes** và các mốc đo tương đương.
- Giữ tài nguyên external qua **explicit close**, không dựa vào GC.
- Khi mô phỏng, dùng **object identity** thay cho equals business.
- Xem tài liệu JLS/java.lang.ref để phân biệt ngữ nghĩa chuẩn và implementation collector.

### Tài liệu tham khảo chuẩn

- **Java SE 17 — java.lang.ref package (Reachability):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html
- **Java SE 17 — Reference và reachabilityFence:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html
- **Java SE 17 — WeakReference:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- **Java SE 17 — PhantomReference:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html
- **Java SE 17 — ReferenceQueue:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html
- **Java SE 17 — WeakHashMap:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html
- **JLS SE 17, §12.6 — Finalization và reachability:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6
- **JVMS SE 17, §2.5.3 — Heap:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3
- **Oracle Java SE 17 Garbage Collection Tuning — Other Considerations:** https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html

**Kết luận:** Một đối tượng trong Java không bị giữ sống chỉ vì còn được một đối tượng khác trong cùng cycle trỏ tới. **Đường tham chiếu mạnh từ GC roots** mới là yếu tố quyết định trong mô hình tracing. Một nhóm cycle không root có thể được thu gom, còn một object graph mà ứng dụng không cần nữa nhưng vẫn reachable qua cache/listener/thread có thể gây memory leak. Hãy tìm **GC root paths và ranh giới vòng đời**, không cố phá mọi cycle hoặc lặp System.gc().
