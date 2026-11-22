# Đánh giá chi phí của nhiều đối tượng nhỏ và cấu trúc dữ liệu giữ tham chiếu trong HotSpot

## Mục tiêu

Một triệu giá trị `int` có thể được lưu trong một mảng primitive hoặc trong một triệu object riêng lẻ. Hai cấu trúc mang cùng dữ liệu logic nhưng có chi phí bộ nhớ và thực thi rất khác nhau. Với HotSpot, mỗi object nhỏ có thể cần **header**, **padding/alignment** và các **reference fields**; container còn có thể giữ **mảng tham chiếu**, **node** hoặc **entry**. Số object lớn cũng có thể tăng công việc cấp phát, GC tracing, pointer chasing và cache misses.

Sau bài học, bạn có thể:

- Phân biệt **shallow size**, **object graph footprint**, **retained size**, **live heap**, **allocated bytes** và **allocation rate**.
- Ước lượng các phần memory của object, reference array, primitive array và cấu trúc có N entries bằng **mô hình có giả định**, không gán số byte cố định cho mọi bản HotSpot.
- Nhận diện boxing, object caches, aliasing và việc một reference slot không tự đồng nghĩa thêm một object.
- So sánh `int[]`, `Integer[]`, `ArrayList<Integer>`, `LinkedList<Integer>`, `HashMap<K,V>` và cấu trúc node tự xây dựng.
- Hiểu ảnh hưởng của capacity, load factor, object lifetime, GC, CPU cache locality, escape analysis/JIT.
- Thực hành Java 17+, khảo sát dữ liệu bằng JOL, JFR, `jcmd`/heap dump và benchmark bằng JMH.
- Đưa ra quyết định tối ưu dựa trên phép đo và yêu cầu API, không chỉ dựa vào số lượng object.

## 1. Đếm phần tử logic không đủ để biết số object

Xét đoạn Java minh họa:

~~~java
int[] primitive = new int[1_000_000];
Integer[] boxed = new Integer[1_000_000];
~~~

Hai biểu thức tạo ra **mỗi bên một array object**, nhưng:

- `int[]` lưu trực tiếp 1.000.000 giá trị primitive int mặc định 0, không cần 1.000.000 Integer objects.
- `Integer[]` là **reference array** chứa 1.000.000 slots mặc định `null`. Lệnh tạo array **không tạo một triệu Integer objects**.
- Nếu điền boxed array bằng một triệu **references tới cùng một Integer**, vẫn chỉ có **một referent object** được chia sẻ (ngoài array).
- Nếu điền các giá trị Integer riêng biệt, số wrapper instances có thể tăng rất lớn; nhưng autoboxing/`Integer.valueOf` có **cache**, JIT có thể tối ưu trong các trường hợp hợp lệ.
- Hai arrays có cùng `length` không đồng nghĩa cùng lượng memory khi các phần tử của reference array đang trỏ tới object graphs khác nhau.

~~~text
int[N]
  [header][int0][int1][int2] ... [intN-1]

Integer[N] sau khi điền các referents riêng:
  [header][ref0][ref1][ref2] ... [refN-1]
             |     |     |
             v     v     v
         [Integer][Integer][Integer]

Integer[N] khi chia sẻ một referent:
  [header][ref0][ref1][ref2] ...
             \     |     /
              \    |    /
                [Integer]
~~~

**Phân biệt ngay từ đầu:** một **reference value** là giá trị cho biết object được tham chiếu, không phải toàn bộ object. Gán `target[i] = shared;` chỉ đặt một reference value vào slot; không clone object.

## 2. Object header, fields, padding và alignment

Theo mô hình JVM, các class instances và arrays nằm trên **heap**. HotSpot có quyền lựa chọn object layout vật lý, miễn giữ đúng Java/JVM semantics.

Một class instance điển hình có cấu trúc khái niệm:

~~~text
[ Object header / metadata runtime ]
[ Các instance fields của class và superclasses ]
[ Internal padding / alignment nếu cần ]
~~~

Khi có nhiều object nhỏ, chi phí lặp lại của **object header và alignment** có thể lớn so với dữ liệu hữu ích. Một class có một `byte` field không thể suy ra shallow instance size bằng một byte.

Đối với một cấu hình HotSpot 64-bit có **compressed oops**, **compressed class pointers** và **8-byte object alignment**, một layout thông dụng có thể có:
- Object header khoảng **12 bytes**.
- Compressed reference field khoảng **4 bytes**.
- `int` field có payload 4 bytes.
- Instance có một `int` có thể có shallow size **16 bytes** trong cấu hình này.

**Đây là ví dụ có điều kiện, không phải định lý cho mọi JDK.** HotSpot có thể hỗ trợ compact object headers hoặc options khác; architecture, JDK version, flags và alignment làm thay đổi các con số. Compressed oops cũng không bắt buộc bật trên mọi VM 64-bit.

Công thức tư duy:

~~~text
shallow_size(object)
  ~ align(header_bytes + field_bytes + padding_internal,
          alignment_bytes)
~~~

Đây là **ước lượng cấu trúc**, không thay thế việc đo; thứ tự fields, inheritance, packing và alignment do VM kiểm soát. Với `N` objects, tổng shallow bytes thường xấp xỉ `N × shallow_size` nếu thực sự có N instances cùng layout.

### Ví dụ class có reference link

~~~java
final class Link {
    int id;
    Link next;
}
~~~

Đây là class minh họa. Trong cấu hình giả định 12-byte header + 4-byte int + 4-byte compressed ref + alignment 8 byte:

~~~text
Unaligned: 12 + 4 + 4 = 20 bytes
Aligned:   24 bytes cho một Link instance
1_000_000 Link instances: khoảng 24_000_000 bytes
~~~

Con số **24 MB hệ thập phân** chỉ cho chính Link instances trong giả định ấy; chưa tính structures giữ chúng, các referents khác, metadata/GC overhead và heap capacity. `int[1_000_000]` có payload primitive 4_000_000 bytes, cộng header/alignment của **một array**. Tuy nhiên, một linked structure cung cấp chức năng và identity khác primitive array.

## 3. Primitive arrays, reference arrays và boxing

Các phần tử trong `int[]` được lưu trực tiếp bên trong array object. Các phần tử trong `Object[]` hoặc `Integer[]` là reference values; object referents nằm tách biệt theo mô hình runtime.

Mô hình size gần đúng, với `N` là length và `R` là reference width của JVM hiện tại:

~~~text
int[N]:
  array_overhead + 4*N + tail_padding

long[N]:
  array_overhead + 8*N + tail_padding

Object[N]:
  array_overhead + R*N + tail_padding
  + memory của referents nếu cần tính graph

Integer[N] đã được điền:
  array_overhead + R*N + tail_padding
  + M * shallow_size(Integer)
  (M là số Integer instances khác nhau thực sự được giữ)
~~~

`array_overhead` gồm metadata/header/length theo layout JVM thực tế, và **không có một giá trị bắt buộc chung** cho mọi platform.

### Autoboxing tạo thêm sự phức tạp

~~~java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);
System.out.println(a == b); // true
~~~

Đây là code snippet bên trong một phương thức. `Integer.valueOf` có cache bắt buộc cho vùng **-128..127**, nên hai reference ở đây cùng chỉ một Integer. Ngoài vùng đó, **không** dựa vào identity hoặc số allocations không được API hứa. Để so giá trị wrappers, dùng `equals` hoặc unbox phù hợp thay vì `==`.

Nếu một cấu trúc chứa một triệu số nguyên lớn khác nhau và giữ chúng như các Integer objects, chi phí box có thể cao. Ngược lại, nếu toàn bộ collection tham chiếu một object cache dùng chung, số wrapper objects không tương đương size của collection.

**Ví dụ ước lượng có điều kiện:** giả sử 1.000.000 phần tử, R=4, mỗi wrapper Integer shallow size 16 bytes, mọi wrapper là object riêng, backing array có capacity 1.000.000. Reference slots cần khoảng 4 MB và wrappers khoảng 16 MB, tổng khoảng 20 MB **chưa kể header/padding của array và container**. Với int[] cùng N, payload là khoảng 4 MB cộng một header. Đây **không phải số đo ứng dụng thực tế**.

## 4. Shallow size, reachable footprint, retained size và allocation rate

| Chỉ số | Câu hỏi | Lưu ý |
| --- | --- | --- |
| **Object count** | Có bao nhiêu instances/arrays? | Không bằng số phần tử logic hoặc số lần dùng `new` trong source. |
| **Shallow size** | Riêng object hiện tại chiếm bao nhiêu bytes? | Không cộng object được reference fields trỏ tới. |
| **Reachable graph footprint** | Từ một root có thể tới những object nào và tổng size chúng? | Có thể có chia sẻ với root khác. |
| **Retained size** | Nếu bỏ owner theo quan hệ dominator thì bao nhiêu bytes có thể trở nên unreachable? | Không phải tổng mọi referents reachable nếu có sharing. |
| **Allocated bytes** | Tổng bytes được cấp phát trong khoảng đo? | Có thể lớn dù phần lớn object đã chết. |
| **Live heap** | Bao nhiêu dữ liệu còn live ở thời điểm/tiêu chí đo? | Không bằng committed heap hoặc RSS tiến trình. |

Ví dụ:

~~~text
Root A ------> [List] ------> [LargePayload]
                                  ^
Root B ---------------------------+
~~~

Loại bỏ Root A/List không khiến `LargePayload` chết nếu Root B vẫn giữ reference. Vì vậy không thể tính retained size bằng cách cộng tất cả objects mà List reachable. Khi phân tích heap dump, *dominator tree* giúp tìm object owners thực sự giữ phần bộ nhớ quan trọng.

**Reachability là vấn đề của graph**, không phải của scope một biến duy nhất. `x = null` có thể cắt một edge, nhưng referent vẫn còn live nếu root/field/array khác giữ nó. GC cũng không bảo đảm trả ngay committed heap về OS.

## 5. ArrayList: backing array + references + elements

Trong triển khai JDK phổ biến, `ArrayList<E>` giữ elements bằng backing array of references. Capacity của array có thể lớn hơn size của list.

~~~java
ArrayList<String> names = new ArrayList<>(100);
names.add("A");
names.add("B");
System.out.println(names.size()); // 2
~~~

Đây là snippet cần `import java.util.ArrayList;`. `size()==2` không có nghĩa backing array chỉ có hai slots. Với capacity 100, vẫn có chi phí dự trữ reference slots.

Các phần trong memory:
1. **ArrayList instance** (metadata như size/reference tới backing array).
2. **Backing array object** với capacity `C ≥ size`.
3. **Element objects** nếu elements là references đến object do ứng dụng giữ.
4. Có thể có array tạm thời khi grow/copy.

Một biểu thức tư duy:

~~~text
ArrayList<E> graph footprint
  ~= shallow(ArrayList)
      + shallow(backing Reference[])
      + phần E referents thuộc graph (không đếm trùng sharing)
~~~

Đối với `ArrayList<Integer>`, cần xét **Integer wrappers**. Đối với `ArrayList<byte[]>`, cần xét từng **byte[] payload** nếu chúng thực sự tồn tại riêng, không chỉ reference slots.

Theo Java API, `ArrayList.add` có amortized constant-time behavior; `get(index)` thường nhanh, còn chèn/xóa ở giữa có thể dịch chuyển references. **Không hardcode một hệ số tăng capacity cụ thể cho mọi version JDK**, vì growth policy chi tiết là implementation detail.

### Dự trữ và thu gọn

- `new ArrayList<>(expectedSize)` hoặc `ensureCapacity(expectedSize)` có thể giảm số lần phải grow/copy nếu biết trước số phần tử sẽ thêm.
- Reserve quá lớn cho **nhiều** lists nhỏ có thể lãng phí memory đáng kể.
- `trimToSize()` giảm capacity theo size; nó không hủy các element objects đang được list giữ.
- Nếu có rất nhiều lists thường rỗng hoặc chỉ chứa 1–2 phần tử, **fixed overhead của chính list và backing array** có thể chiếm ưu thế.

**Không dùng reflection vào các private fields của ArrayList làm API**, vì module encapsulation, JVM update và implementation details có thể thay đổi.

## 6. LinkedList: nhiều node objects và pointer chasing

Một doubly linked list thường có mỗi phần tử trong một node lưu references `prev`, `next` và `item`. Trong các JDK thông dụng, `LinkedList<E>` có cơ chế node-based tương tự.

~~~text
LinkedList instance
      |
      v
[Node item,prev,next] -> [Node] -> [Node] -> ...
      |                   |        |
      v                   v        v
   [Element]           [Element] [Element]
~~~

Footprint gần đúng:

~~~text
shallow(LinkedList)
+ N * shallow(Node)
+ referent elements (trừ các phần được chia sẻ)
~~~

Mỗi node có **header, nhiều reference fields và alignment**, nên tổng overhead theo N thường cao hơn backing reference array tương ứng. Nếu element type là Integer, có thể vừa trả chi phí node **vừa** trả chi phí wrapper.

Không thể từ đó kết luận LinkedList luôn chậm/tệ:
- Thêm/xóa khi đã có iterator/node ở vị trí có thể tránh dịch chuyển cả mảng.
- Nếu cần random positional access, LinkedList thường phải traverse các nodes, tốn O(N) thời gian tìm vị trí.
- ArrayList có thể copy references theo block hiệu quả và có locality tốt hơn.
- Workload xử lý queues/deques có thể phù hợp hơn với `ArrayDeque`, tùy API và thread-safety.

**Quan trọng:** Big-O mô tả xu hướng thuật toán, **không bao gồm** mọi object allocation, CPU cache miss và GC overhead. Chọn theo workload, không theo một khẩu hiệu “LinkedList chèn nhanh”.

## 7. HashMap, HashSet và entry structures

Trong triển khai HotSpot/JDK phổ biến, `HashMap<K,V>` có một **bucket table** là reference array cùng các **entry/node objects** cho mappings. Khi collisions cao, một số buckets có thể có representation khác (ví dụ tree nodes).

~~~text
HashMap
  |
  v
table[capacity]
  |
  +--> bucket0: Node(keyRef, valueRef, nextRef)
  |
  +--> bucket1: null
  |
  +--> bucket2: Node --> Node ...
~~~

Thành phần chi phí:
- Bản thân **HashMap object**.
- **Backing table** với capacity buckets, kể cả buckets chưa dùng.
- **Entry objects** hoặc representation tương đương tùy JDK.
- **Key objects**, **value objects** và graphs phía sau chúng.
- Resize/re-hash, load factor, collision handling và capacity dư.

Một triệu mappings không đồng nghĩa một triệu key objects mới và một triệu value objects mới: keys/values có thể tạo ngoài map và được chia sẻ; `put` cùng key có thể thay value mà không tăng size. Với boxed keys như Integer/Long, cần tính thêm wrappers nếu chúng là instances riêng.

### Load factor và capacity

Load factor ảnh hưởng đến quan hệ giữa số entries và backing table capacity. Capacity lớn có thể tạo nhiều reference slots chưa dùng; capacity nhỏ có thể khiến resize/collision tốn kém. Phải đánh giá trên phân phối keys/operations thực, không chọn theo một con số duy nhất.

`HashSet<E>` trong JDK thông dụng sử dụng hash-based storage tương tự ở mức cơ chế, nên không “miễn phí” node/table chỉ vì API chỉ thể hiện một tập phần tử.

**Không gắn số bytes cố định cho `HashMap$Node` hay `LinkedList$Node`** như chuẩn Java SE. Layout của các inner classes là chi tiết của bản JDK, và VM headers/field packing ảnh hưởng thêm.

## 8. Cấu trúc lưu tham chiếu có sharing hoặc deep object graph

Một cấu trúc chứa 2 references có thể trỏ:
- **Cùng một object** → hai edges, một referent.
- **Hai object khác nhau** → hai edges, hai referents.
- **Hai object khác nhau cùng giữ một payload** → nhiều objects ở tầng ngoài, một payload chung.
- **Hai payload độc lập** → nhiều referents và nhiều mảng dữ liệu.

Mô hình:

~~~text
Owner A ---+
           +---> [SharedPayload byte[]]
Owner B ---+

Owner C ------> [SeparatePayload C]
Owner D ------> [SeparatePayload D]
~~~

### Ví dụ Java 17+ chạy độc lập: sharing

Tạo file **`ReferenceSharingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ReferenceSharingDemo {
    public static void main(String[] args) {
        byte[] shared = new byte[4];

        List<byte[]> reused = new ArrayList<>();
        reused.add(shared);
        reused.add(shared);

        List<byte[]> independent = new ArrayList<>();
        independent.add(new byte[4]);
        independent.add(new byte[4]);

        System.out.println("reusedSame=" +
                (reused.get(0) == reused.get(1)));
        System.out.println("independentSame=" +
                (independent.get(0) == independent.get(1)));

        reused.get(0)[0] = 9;
        System.out.println("aliasValue=" + reused.get(1)[0]);
        System.out.println("independentValue=" + independent.get(1)[0]);
        System.out.println("reusedSlots=" + reused.size());
        System.out.println("independentSlots=" + independent.size());
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac --release 17 ReferenceSharingDemo.java
java ReferenceSharingDemo
~~~

**Stdout chính xác:**

~~~text
reusedSame=true
independentSame=false
aliasValue=9
independentValue=0
reusedSlots=2
independentSlots=2
~~~

Các lists đều giữ hai entries về mặt logic; `reused` giữ **một byte[] referent dùng chung**, trong khi `independent` giữ hai byte[] objects riêng. Việc aliasing làm thay đổi footprint của graph nhưng cũng có ảnh hưởng tới **mutation semantics**: sửa shared payload qua một reference sẽ hiển thị qua reference khác.

**Chia sẻ object không phải lúc nào cũng phù hợp.** Nếu các owners cần mutate độc lập, sharing gây side effects không mong muốn. Quyết định tiết kiệm memory phải bảo toàn correctness và ownership.

## 9. Ví dụ Java 17+: cùng năm số, nhiều representation

Tạo file **`ContainerShapeDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedList;
import java.util.List;

public class ContainerShapeDemo {
    static final class Node {
        int value;
        Node next;

        Node(int value, Node next) {
            this.value = value;
            this.next = next;
        }
    }

    static int sumNodes(Node head) {
        int sum = 0;
        for (Node n = head; n != null; n = n.next) {
            sum += n.value;
        }
        return sum;
    }

    static int sumList(List<Integer> values) {
        int sum = 0;
        for (int v : values) {
            sum += v;
        }
        return sum;
    }

    public static void main(String[] args) {
        int[] values = {10, 20, 30, 40, 50};

        Integer[] boxed = new Integer[values.length];
        ArrayList<Integer> arrayList =
                new ArrayList<>(values.length);
        LinkedList<Integer> linkedList = new LinkedList<>();

        Node head = null;
        for (int i = values.length - 1; i >= 0; i--) {
            head = new Node(values[i], head);
        }

        int primitiveSum = Arrays.stream(values).sum();

        for (int i = 0; i < values.length; i++) {
            boxed[i] = Integer.valueOf(values[i]);
            arrayList.add(boxed[i]);
            linkedList.add(boxed[i]);
        }

        int boxedSum = 0;
        for (Integer v : boxed) {
            boxedSum += v;
        }

        System.out.println("primitiveSum=" + primitiveSum);
        System.out.println("boxedSum=" + boxedSum);
        System.out.println("arrayListSum=" + sumList(arrayList));
        System.out.println("linkedListSum=" + sumList(linkedList));
        System.out.println("nodeSum=" + sumNodes(head));
        System.out.println("arrayLength=" + values.length);
        System.out.println("listSize=" + arrayList.size());
        System.out.println("sameFirstRef=" +
                (arrayList.get(0) == boxed[0]));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 ContainerShapeDemo.java
java ContainerShapeDemo
~~~

**Stdout chính xác:**

~~~text
primitiveSum=150
boxedSum=150
arrayListSum=150
linkedListSum=150
nodeSum=150
arrayLength=5
listSize=5
sameFirstRef=true
~~~

Ý nghĩa:
1. `int[]` chứa 5 primitive values trong một array object.
2. `Integer[]` chứa 5 reference slots. Các giá trị 10,20,30,40,50 nằm trong vùng Integer cache bắt buộc, nên không dùng chương trình này để đếm 5 wrapper allocations.
3. `ArrayList<Integer>` và `LinkedList<Integer>` cùng giữ **những reference values đã cung cấp** từ boxed array; không tự deep-copy element objects.
4. LinkedList có thể thêm node instances, còn ArrayList dùng backing array.
5. Chuỗi Node được tự xây gồm **5 Node instances riêng**, mỗi node có int field và một link reference.
6. Các tổng số bằng nhau, nhưng footprint và memory-access shape khác nhau.

Ví dụ minh họa semantics, **không** phải benchmark throughput hoặc công cụ đo bytes.

## 10. Object locality, pointer chasing và CPU cache

Dữ liệu nằm trong một primitive array có xu hướng hỗ trợ duyệt tuần tự tốt nhờ contiguous layout. Trong một reference array, **reference slots** liên tiếp nhưng **referents** không bắt buộc liên tiếp. Linked nodes cần đọc `next` trước khi biết node tiếp theo nằm đâu.

~~~text
int[]:
  read element0 -> element1 -> element2 -> ...

ArrayList<E>:
  read ref0 -> dereference E0
  read ref1 -> dereference E1
  ...

LinkedList<E>:
  read node0.next -> node1.next -> node2.next ...
~~~

Tác động có thể gồm:
- CPU cache misses, TLB pressure.
- Kém khả năng hardware prefetch đối với dependent pointer chasing.
- Nhiều object header/metadata hơn cần GC quản lý.
- Allocation churn nếu liên tục tạo/hủy nodes.
- Thời gian tìm vị trí khi truy cập bằng index.

Tuy nhiên, tính locality không phải guarantee bất biến. Collector có thể di chuyển objects, HotSpot có thể cấp phát gần nhau vào một lúc nhưng không đảm bảo chúng luôn sát nhau. Nếu workload chủ yếu lookup hash key, thuật toán tốt có thể quan trọng hơn locality thuần; nếu chỉ duyệt rất ít entries, chi phí cấu trúc có thể khác.

## 11. Allocation rate khác retained heap

Hai ứng dụng đều còn 100 MB live objects nhưng có thể có allocation rate rất khác:
- A tạo dữ liệu một lần, giữ lâu.
- B tạo hàng triệu temporary wrappers mỗi giây rồi bỏ.

B có thể gây GC/CPU load lớn hơn dù cuối khoảng đo live heap bằng A. Ngược lại, nhiều objects nhỏ sống lâu có thể tăng GC tracing/live-set footprint ngay cả khi allocation rate thấp.

| Metric | Dùng để |
| --- | --- |
| **Bytes allocated per operation** | Biết mỗi request/công việc cấp phát nhiều không. |
| **Allocation rate bytes/s** | Xem pressure tổng ở steady state. |
| **Live heap sau GC phù hợp** | Ước lượng tập dữ liệu cần tồn tại. |
| **Retained heap/dominator** | Tìm owner đang giữ objects không còn cần. |
| **GC pauses, frequency, CPU** | Đánh giá ảnh hưởng đến latency/throughput. |
| **Process RSS / committed heap** | Khảo sát footprint hệ thống, không đồng nhất chúng với live objects. |

Vấn đề memory leak ở Java thường là **reference retention**: cache không eviction, listener không unregister, static collection phình to, thread-local giữ dữ liệu quá lâu, hoặc key/value lifecycle sai. GC không tự thu objects vẫn reachable từ roots.

## 12. JIT và escape analysis: số `new` không bằng số allocations vật lý

Ví dụ:

~~~java
static int calculate(int a, int b) {
    Pair p = new Pair(a, b);
    return p.first + p.second;
}
~~~

Đây là snippet cần class `Pair` phù hợp. Nếu JVM JIT chứng minh object không escape và loại bỏ allocation không thay đổi hành vi quan sát, nó **có thể** sử dụng **scalar replacement** thay vì tạo object vật lý.

Những điều **không thể** kết luận chỉ từ source:
- Mọi `new` chắc chắn tiêu tốn một heap object vật lý trên mọi JIT run.
- Mọi object nhỏ chắc chắn được stack-allocate.
- JIT chắc chắn loại bỏ riêng allocation trong ví dụ này ở mọi Java version/tier.
- Bytecode vẫn có opcode `new` thì bắt buộc profiler phải đếm một allocation trong optimized execution.

Để đánh giá object churn, cần quan sát trong context thực tế: warmup, compiler tier, escape, inlining, garbage collector và profiler overhead. Một phép thử không tiêu thụ kết quả có thể bị dead-code elimination, làm số đo gần như vô nghĩa.

## 13. Đo object layout bằng JOL

**Java Object Layout (JOL)** là công cụ OpenJDK nghiên cứu object layout/footprint thực tế và mô phỏng các VM modes. JOL giúp xác nhận header, alignment, field offsets và cách references đóng góp vào graph.

Các ví dụ lệnh (giả sử đã tải đúng JAR JOL CLI và đặt tên là `jol-cli.jar`):

~~~bash
java -jar jol-cli.jar internals java.lang.Integer
java -jar jol-cli.jar internals-estimates java.lang.Integer
java -jar jol-cli.jar footprint java.util.HashMap
~~~

Đây là hướng dẫn công cụ **ngoài Java SE**, không đảm bảo một output cố định. Phiên bản JOL CLI, VM mode, flags, class structure và quyền truy cập có thể ảnh hưởng lệnh khả dụng/kết quả.

- **internals**: cho biết header/field/padding và layout object.
- **internals-estimates**: ước lượng một số bố cục trong những VM modes hỗ trợ.
- **footprint**: khảo sát object graph, cần phân biệt reachable graph với retained dominator ownership.
- Một số chế độ heapdump của JOL giúp thống kê objects/wrappers/duplicates ở mức heap.

Trang dự án: https://openjdk.org/projects/code-tools/jol/ và tài liệu: https://github.com/openjdk/jol.

### Ghi rõ giả định khi báo kết quả

Một báo cáo đo memory cần có:
- JDK exact version/build, HotSpot architecture, VM flags/compressed references/alignment.
- GC collector và heap flags liên quan.
- Kích thước N, array capacity, load factor, dữ liệu key/value và mức object sharing.
- Đo **shallow** hay **graph/retained**.
- Kết quả bao gồm hay không bao gồm object wrappers, backing arrays, secondary indexes.
- Số lần chạy, mức độ nhiễu và cách kiểm chứng.

Nếu chỉ nói “Integer nặng 16 bytes” mà không cho biết giả định VM, phép tính không đủ đáng tin cho quyết định triển khai.

## 14. Dùng JFR, jcmd và heap dump để điều tra thực tế

**JFR (Java Flight Recorder)** có thể cung cấp thông tin allocation hotspots, event samples và hoạt động VM; **jcmd** có thể lấy heap info, histogram, heap dump hoặc điều khiển JFR trên HotSpot có hỗ trợ.

Một số mẫu lệnh cho một **tiến trình Java đang chạy** (thay `PID` bằng số PID thật):

~~~bash
jcmd PID GC.heap_info
jcmd PID GC.class_histogram
jcmd PID JFR.start name=MemStudy settings=profile duration=60s filename=memory.jfr
jcmd PID JFR.check
~~~

`PID` là **ký hiệu placeholder trong hướng dẫn dòng lệnh**, không phải chuỗi cần giữ nguyên khi chạy. Các diagnostic commands có thể có tác động đáng kể, đặc biệt class histogram trên heap lớn; không bật tùy tiện trên production.

Khi cần dump:

~~~bash
jcmd PID GC.heap_dump filename=memory.hprof
~~~

**Cảnh báo bảo mật:** heap dump có thể chứa mật khẩu, token, session data, PII hoặc nhiều dữ liệu nhạy cảm. Chỉ thu thập, lưu/chia sẻ với quyền phù hợp, bảo vệ file và quy định retention. Dump có thể rất lớn và ảnh hưởng throughput/GC khi chạy.

### Histogram nói gì và không nói gì?

Class histogram nhóm objects theo runtime class, hiển thị số instances và shallow bytes được ghi nhận. Nó hữu ích khi thấy quá nhiều `Integer`, `HashMap$Node`, `byte[]` hoặc domain records.

Nhưng histogram **không xác định đầy đủ**:
- Ai đang giữ những objects ấy reachable?
- Retained heap của một cache/owner?
- Các temporary allocations đã chết trước thời điểm chụp?
- CPU cache misses hoặc latency của traversal?

Để tìm nguyên nhân **retention**, dùng heap dump với **dominator tree và paths to GC roots**. Để tìm nguyên nhân **churn**, dùng JFR/allocation profiler. Nếu cần performance, phải đo thời gian và throughput riêng.

## 15. Benchmark bằng JMH

Không thể kết luận hiệu năng chỉ từ vòng lặp đo bằng `System.nanoTime()` một lần. HotSpot JIT có thể:
- Warm up và inline khác qua các iteration.
- Dùng scalar replacement làm biến mất object allocations.
- Loại bỏ code mà kết quả không được sử dụng.
- Dùng CPU caches khác tùy dữ liệu có được reuse.
- Có nhiễu GC, scheduling, CPU frequency, contention và profiler.

**JMH (Java Microbenchmark Harness)** là dự án OpenJDK cho microbenchmarks, hỗ trợ warmup, measurement iterations, forks, state và tiêu thụ kết quả để giảm sai lệch.

Một kế hoạch test công bằng:

| Phép đo | Cần giữ cố định |
| --- | --- |
| Duyệt `int[]` vs `ArrayList<Integer>` | Cùng N và values; tiêu thụ tổng; record boxing/cache setup |
| Duyệt `ArrayList<E>` vs `LinkedList<E>` | Cùng referents, setup dữ liệu ngoài vùng đo nếu muốn chỉ đo iteration |
| Insert/remove middle | Tính cả cách xác định vị trí hoặc tách chi phí search đúng intent |
| Lookup `HashMap` vs array scan | Cùng keys, query distribution, load factor và cardinality |
| Tạo N objects mỗi request | Đo throughput, bytes/op và GC cùng nhau |
| Structure-of-arrays vs object-per-entry | Đảm bảo cùng semantics và access pattern |

**Không coi JMH score là điểm số end-to-end** của một ứng dụng web/service: network, DB, serialization, locks và latency tail có thể quan trọng hơn micro-operation.

Trang dự án JMH: https://openjdk.org/projects/code-tools/jmh/.

## 16. Chọn cấu trúc nào?

| Workload | Lựa chọn thường nên xem xét đầu tiên | Trade-off |
| --- | --- | --- |
| Nhiều số nguyên và duyệt theo thứ tự | `int[]`, `long[]` hoặc primitive-specialized collections | Packing tốt, nhưng API/resize khác generic List |
| Danh sách objects truy cập theo index | `ArrayList<E>` | Backing array/capacity + referents |
| FIFO/LIFO | `ArrayDeque<E>` hoặc queue phù hợp | Dữ liệu lưu qua references, đồng bộ tùy API |
| Lookup bằng key | `HashMap<K,V>` | Table, nodes, load factor, key/value graphs |
| Sorted/range queries | `TreeMap<K,V>` hoặc sorted array theo workload | Tree-node overhead vs chi phí cập nhật array |
| Xóa/chèn với iterator đã ở vị trí | `LinkedList<E>` khi thực sự phù hợp | Node overhead/pointer chasing, random get đắt |
| Rất nhiều records nhỏ đồng nhất | Object array vs **structure-of-arrays** | Packing và locality vs identity/API complexity |
| Cache có khả năng tăng vô hạn | Bounded cache/eviction policy | Cần giới hạn owner retention rõ ràng |

### Khi nào dùng structure-of-arrays?

Thay vì N instances như:

~~~java
class Entry {
    int id;
    long timestamp;
}
~~~

có thể giữ hai primitive arrays:

~~~java
int[] ids = new int[n];
long[] timestamps = new long[n];
~~~

Các đoạn trên là **minh họa cần context khai báo biến n và class hợp lệ**. Representation thứ hai giúp loại bỏ nhiều object headers, có thể tăng cache locality cho scan. Nhưng nó thay đổi semantics:
- Không còn identity object per entry theo cách ban đầu.
- Dễ phát sinh sai lệch index khi delete/reorder.
- Cần kiểm soát concurrent updates, growth và invariant giữa hai arrays.
- Không tốt mặc định cho mọi access pattern.

Dùng dữ liệu đo thật và maintainability để quyết định, không ép tất cả domain model về arrays.

## 17. Checklist tối ưu có kiểm chứng

1. Nêu rõ vấn đề: memory budget, GC pauses, throughput, tail latency hay allocation CPU?
2. Định lượng số phần tử **N**, size distribution, lifetime, access pattern, null/sharing ratio.
3. Vẽ object graph: container, backing arrays, nodes/entries, keys/values, wrappers, payload arrays.
4. Tách **chi phí dữ liệu** khỏi **chi phí cấu trúc giữ references**.
5. Chọn metric phù hợp: shallow, graph, retained, bytes/op hoặc latency.
6. Ghi JDK/VM flags/alignment/compressed-oops/collector trước khi so bytes.
7. Đo baseline bằng JOL/JFR/heap dump/profiler/JMH tùy câu hỏi.
8. Đổi một yếu tố: reserve capacity, primitive storage, node count, cache policy, reuse.
9. Kiểm tra **correctness** sau đổi: aliasing, identity, equals/hashCode, null, concurrency.
10. Đo lại trên workload thực, ghi ưu/nhược điểm và rollback nếu trade-off không phù hợp.

**Tối ưu đúng** không phải luôn có ít objects nhất mà là đạt SLA và memory budget **trong khi duy trì đúng tính năng, tính đúng đắn và độ dễ bảo trì**.

## 18. Ngộ nhận thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “Một object có int field thì chiếm 4 byte.” | Header, alignment và fields khác cũng góp vào shallow size. |
| “JVM 64-bit thì mọi reference phải 8 byte.” | Compressed oops có thể dùng độ rộng nhỏ hơn. |
| “Object array có N slots tức là đã tạo N element objects.” | Slots chỉ chứa references, ban đầu null. |
| “Mỗi autoboxing chắc chắn new một object.” | Caches/optimizer có thể ảnh hưởng object identity/allocation. |
| “ArrayList size chính là capacity.” | Capacity có thể dư, làm tăng backing array footprint. |
| “LinkedList tiết kiệm vì không có backing array.” | Có nhiều node objects và refs prev/next/item. |
| “HashMap chỉ tốn key + value.” | Còn table, entries/nodes, capacity và collision handling. |
| “Reachable footprint luôn bằng retained size.” | Nếu graphs share objects, các số có thể khác nhau. |
| “Live heap ít thì allocation rate cũng ít.” | Objects ngắn hạn có thể được tạo rồi bỏ rất nhanh. |
| “Heap committed không giảm nghĩa là leak.” | VM có thể giữ committed memory để tái sử dụng. |
| “GC thấy object lớn là sẽ tự xóa nếu nghiệp vụ không dùng.” | Nếu vẫn reachable từ roots, GC không biết logic nghiệp vụ. |
| “Số bytes JOL trên máy tôi là chuẩn cho mọi JVM.” | Layout phụ thuộc JDK/HotSpot options/architecture. |
| “TLAB thuộc stack.” | TLAB là một cơ chế cấp phát trong heap. |
| “Mọi `new` chắc chắn tạo allocation vật lý.” | JIT có thể loại bỏ allocation khi giữ nguyên semantics. |
| “ArrayList luôn nhanh hơn LinkedList trong mọi hoạt động.” | Cần xét thuật toán, search, mutation và workload. |
| “Heap dump có thể chia sẻ thoải mái.” | Có nguy cơ chứa secrets/PII, phải kiểm soát truy cập. |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không lấy `4 × N` bytes để tính N instances có một field int?

**Đáp án:** Vì mỗi instance còn có header, alignment/padding và có thể inherited fields; cần đo shallow size thực tế.

**Câu 2.** `new Integer[1000]` tạo bao nhiêu Integer objects?

**Đáp án:** Không tạo Integer referent nào, chỉ tạo một Integer[] array có 1000 null reference slots.

**Câu 3.** Nhiều reference slots cùng trỏ một object sẽ ảnh hưởng graph như thế nào?

**Đáp án:** Có nhiều references nhưng một referent, tránh nhân object footprint theo số slots; sharing lại có mutation semantics riêng.

**Câu 4.** Tại sao `ArrayList<Integer>` có thể tốn hơn `int[]`?

**Đáp án:** ArrayList object + backing reference array + Integer wrappers (nếu nhiều objects riêng), trong khi int[] lưu primitive values trong một array.

**Câu 5.** Những values của Integer ở vùng cache có chắc mỗi lần boxing đều cấp phát mới không?

**Đáp án:** Không. `Integer.valueOf` có cache bắt buộc cho -128..127.

**Câu 6.** LinkedList thường có overhead per element gì?

**Đáp án:** Node object với header, các references và padding, cộng elements được tham chiếu.

**Câu 7.** HashMap thêm overhead gì ngoài keys và values?

**Đáp án:** Table, entry nodes, capacity dư, collision/tree structures tùy implementation.

**Câu 8.** Retained size có bằng sum mọi object reachable từ owner không?

**Đáp án:** Không khi có object sharing từ GC roots khác. Retained liên quan quan hệ dominator.

**Câu 9.** Allocation rate cao nhưng live heap nhỏ có thể xảy ra không?

**Đáp án:** Có. Những temporary objects có lifetime rất ngắn vẫn tạo GC/allocation churn.

**Câu 10.** Đo object layout bằng gì? Đo allocation hotspots bằng gì?

**Đáp án:** JOL để xem layout/footprint; JFR/profiler để khảo sát allocation; heap dump/dominator cho retention.

**Câu 11.** Có thể dùng một vòng lặp `System.nanoTime()` không tiêu thụ kết quả để chứng minh data structure nhanh hơn không?

**Đáp án:** Không; JIT có thể loại bỏ code/allocations, warmup và GC gây nhiễu; dùng JMH và benchmark hợp lệ.

**Câu 12.** Khi nào struct-of-arrays có thể phù hợp?

**Đáp án:** Với nhiều records có schema đồng nhất, truy cập tuần tự/analytical và memory/locality là bottleneck, sau khi cân nhắc identity, API và đo đạc.

## 20. Bản đồ ghi nhớ

~~~text
                   N PHẦN TỬ LOGIC
                         |
         +---------------+----------------+
         |                                |
    PRIMITIVE                         REFERENCE
      int[N]                         Object[N] / List<E>
         |                                |
    1 array header                    array slots R*N
    + 4*N payload                         |
                                    element referents
                                         |
                               +---------+----------+
                               |         |          |
                             wrappers   nodes      key/value
                               |         |          |
                               +---------+----------+
                                         |
                               OBJECT GRAPH FOOTPRINT
                                         |
                    +--------------------+------------------+
                    |                    |                  |
                SHALLOW SIZE        RETAINED SIZE     ALLOCATION RATE
                layout/headers      dominator graph   churn/GC impact
                    |                    |                  |
                    +--------------------+------------------+
                                         |
                             latency / throughput / cache
                                         |
                                ĐO TRÊN HOTSPOT THẬT

JOL = layout       JFR = allocation       Heap dump = retainers
JMH = performance  jcmd = VM diagnostics
~~~

**Kết luận:** chi phí của nhiều object nhỏ có thể tích lũy từ **header, alignment, nodes/entries và references**, không chỉ bytes của fields. Cần tính **cấu trúc giữ reference** cùng với **referent graph**, và tách **retained/live heap** khỏi **allocation churn**. Mô hình ước lượng có ích để định hướng, nhưng quyết định kỹ thuật phải dựa trên phép đo **đúng JDK/HotSpot, đúng cấu hình và đúng workload**.

## Tài liệu tham khảo

- [JVMS Java SE 21 — §2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.3).
- [JLS Java SE 21 — Types, Values and Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html).
- [OpenJDK — Java Object Layout (JOL)](https://openjdk.org/projects/code-tools/jol/).
- [OpenJDK — JOL README (layout/footprint)](https://github.com/openjdk/jol).
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/).
- [Java SE 21 — ArrayList API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).
- [Java SE 21 — LinkedList API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedList.html).
- [Java SE 21 — HashMap API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).
- [JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
