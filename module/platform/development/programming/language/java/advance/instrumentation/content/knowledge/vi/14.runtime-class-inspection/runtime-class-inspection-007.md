# Kích thước của một đối tượng khác với tổng đồ thị hoặc retained size

## 1. Một đối tượng, ba câu hỏi về bộ nhớ khác nhau

Java agent có thể gọi `Instrumentation.getObjectSize(object)` để lấy một giá trị `long`. Giá trị này **không phải** “tổng dung lượng của toàn bộ dữ liệu mà object trỏ tới” và **không phải** retained size của object trong JVM.

Cần phân biệt chính xác:

- **Shallow size (shallow heap):** ước lượng dung lượng của **chính object**: header, fields, array elements lưu trực tiếp, alignment/padding theo JVM. Nó không tự đi qua những references đến object khác.
- **Reachable graph size (tổng dung lượng đồ thị reachable):** tổng shallow sizes của những object instances **phân biệt** mà một thuật toán đi tới từ một starting object/root set theo **các loại cạnh đã được xác định**. Nếu không chống trùng/cycle, kết quả không đúng.
- **Retained size (retained heap):** tổng shallow sizes của objects bị object đang xét **dominate** trong object graph có GC roots. Nó cho thấy phần heap mà sự tồn tại phụ thuộc vào owner trong một root graph/snapshot, **không** chỉ là những gì owner có thể reach.

**Luận điểm chính của bài:** `getObjectSize(x)` chỉ cho ước lượng shallow size của `x`. API này không duyệt graph, không có thông tin GC roots, không xây dominator tree và **không trả retained size**. Một object có thể shallow rất nhỏ nhưng retained rất lớn, hoặc reachable graph lớn nhưng retained nhỏ vì các descendants được nhiều chủ sở hữu dùng chung.

### Chọn phép đo theo câu hỏi

| Câu hỏi | Đại lượng phù hợp |
|---|---|
| Một `Node` chiếm bao nhiêu bộ nhớ riêng? | Shallow size |
| Một `byte[]` dài một triệu phần tử chiếm xấp xỉ bao nhiêu byte? | Shallow size của primitive array |
| Duyệt từ object A có bao nhiêu object nodes, tổng kích thước là bao nhiêu? | Reachable graph count/sum có khử trùng |
| A và B cùng tham chiếu payload S, tổng unique heap của graph là bao nhiêu? | Sum trên `R(A) UNION R(B)` |
| Nếu không còn owner A, những objects nào mất mọi GC-root paths? | Retained size / dominator analysis |
| Object còn sống vì đường tham chiếu nào? | Paths to GC Roots |
| ByteBuffer direct dùng bao nhiêu native RAM? | Native/direct memory metrics, không phải shallow wrapper |
| JVM cấp phát object nhanh tại đâu? | Allocation profiler/JFR, không phải retained heap |

## 2. `Instrumentation.getObjectSize(Object)` thực sự làm gì?

### 2.1. Hợp đồng Java SE 17

Chữ ký:

~~~java
long getObjectSize(Object objectToSize);
~~~

Theo Java SE 17 Javadoc, giá trị là **implementation-specific approximation of the amount of storage consumed by the specified object**. Nó có thể tính một phần hoặc toàn bộ object overhead; thích hợp cho so sánh **trong một implementation**, không được bảo đảm so sánh giữa nhiều JVM implementations. Ước lượng còn có thể thay đổi **ngay trong một lần chạy JVM**.

Một số điều phải ghi rõ:

1. Không có tham số `depth`, `includeChildren`, `retained` hoặc traversal policy.
2. Không trả ra tập reference/object children.
3. Không đo tổng heap, total allocated bytes, RSS hay native memory.
4. `getObjectSize(null)` ném `NullPointerException`, không trả 0.
5. Không thể dùng số byte của một JVM 64-bit cụ thể làm chuẩn cho mọi VM: object headers, compressed pointers, alignment, representation và vendor khác nhau.

### 2.2. Object fields vs referenced objects

~~~java
final class Holder {
    int count;
    Object child;
}
~~~

Shallow size của `Holder holder` gồm phần lưu trữ của **bản thân Holder instance**: object overhead, ô nguyên thủy `count`, ô reference `child` và padding theo JVM. Nó **không cộng** dung lượng của object mà `holder.child` đang trỏ tới.

Nếu gán `holder.child` từ `null` sang một object có một triệu phần tử, shallow size của Holder thường không thay đổi trong cùng layout VM; dung lượng của object thứ hai là chuyện riêng. Một reference cũng **không** chứng minh owner duy nhất: child có thể được giữ sống từ các roots khác.

### 2.3. Trường hợp arrays rất dễ nhầm

| Java object | Shallow của chính object | Chưa được cộng |
|---|---|---|
| `new Object()` | Header/padding | Không có child objects |
| `new byte[1_000_000]` | Header/length + **một triệu byte elements inline** | Objects ngoài array |
| `new Object[1_000_000]` | Header/length + **một triệu reference slots** | Object instances mà slots trỏ tới |
| `new String("abc")` | Instance String | Backing array/objects tùy JDK representation |
| `new ArrayList<>()` | Instance ArrayList | Backing `Object[]` và elements |
| `new HashMap<>()` | Instance HashMap | Table, nodes, keys, values |
| `new Node("A")` | Instance Node | Các Node/String được field của nó trỏ tới |
| `ByteBuffer.allocateDirect(...)` | Java wrapper | Native/off-heap region |

**Không nói “shallow không tính phần tử array”** mà không phân biệt: primitive array chứa primitive elements **ngay trong chính array object**; `Object[]` chứa reference slots inline, nhưng **không chứa chính referenced objects**.

Ví dụ:

~~~java
byte[] payload = new byte[1_000_000];
Object[] wrapper = {payload};
~~~

`getObjectSize(wrapper)` chỉ đo object array một slot; `getObjectSize(payload)` đo byte array riêng. Một JVM thực tế có thể trả các số khác nhau phụ thuộc configuration; bài này không đặt con số layout byte làm tiêu chuẩn bắt buộc.

### 2.4. Shallow không phải toàn bộ footprint ứng dụng

Một `DirectByteBuffer` Java có thể có shallow nhỏ nhưng trỏ tới vùng native lớn. Thread stacks, metaspace, JIT code cache, memory mappings, JNI allocations và các vùng khác cũng không được cộng qua một lời gọi `getObjectSize` trên wrapper Java.

Phân biệt các nhãn:

- **Object shallow bytes**: estimate cho một Java object.
- **Live Java heap**: objects đang sống mà GC/JVM xác định.
- **Heap committed/reserved**: vùng quản lý bộ nhớ của JVM, không đồng nhất live objects.
- **RSS/process memory**: một đại lượng ở mức OS bao gồm nhiều phần ngoài Java heap.

Khi chẩn đoán RAM process tăng, chỉ gọi `getObjectSize` là thiếu thông tin.

## 3. Reachable graph cần có traversal và identity

### 3.1. Định nghĩa đồ thị

Gọi:

- `V`: các object instances trong phạm vi graph khảo sát.
- `E`: các cạnh reference mà thuật toán quyết định đi theo.
- `R(x)`: tập các objects **phân biệt** reachable từ x (bao gồm x).
- `s(v)`: shallow size do `getObjectSize(v)` trả về.

Nếu có tập `R(x)` chính xác cho **graph đã định nghĩa**, ta có thể tính:

~~~text
ReachableShallowSum(x) =
    SUM( getObjectSize(v) for each distinct v in R(x) )
~~~

Công thức **không** phải method tích hợp của Instrumentation. Bạn phải biết edges, duyệt và khử trùng lặp. Nếu chỉ biết `getObjectSize(x)` thì không thể suy ra `R(x)`.

### 3.2. Tại sao phải dùng object identity?

Hai instances có thể được coi bằng nhau bằng `equals()` nhưng vẫn là **hai allocations riêng** trên heap. Ngược lại, hai fields có thể cùng giữ reference tới **một object instance**.

Một visited set phù hợp:

~~~java
// Đoạn code minh họa trong class đã import các kiểu tương ứng.
Set<Node> seen = Collections.newSetFromMap(
        new IdentityHashMap<Node, Boolean>());
~~~

`IdentityHashMap` dùng identity (`==`) chứ không dùng value equality; do đó không đếm trùng một instance và không gộp hai instances khác nhau do override `equals`. Một `HashSet` thông thường không tự bảo đảm điều này cho object accounting.

### 3.3. Cycles và shared references

~~~text
ROOT A -> A -> S <- B <- ROOT B
           |
           v
           U -> A     (cycle A -> U -> A)
~~~

Các cạnh:

~~~text
A -> S
A -> U
U -> A
B -> S
~~~

Với graph này:

- `R(A) = {A, S, U}`.
- `R(B) = {B, S}`.
- Hợp hai tập `R(A) UNION R(B) = {A, B, S, U}`.
- Cộng riêng `sum(R(A)) + sum(R(B))` khiến S bị cộng **hai lần**.
- Nếu DFS/BFS không có visited set, cycle A→U→A có thể khiến thuật toán quay vòng vô hạn.

Do đó nếu hỏi tổng unique của A và B, phải hợp sets **theo identity trước khi cộng**. Một property như `left` trỏ tới child không chứng minh child thuộc sở hữu riêng của object mẹ.

### 3.4. “Graph total” phụ thuộc scope

Nếu code tự viết chỉ đi qua `Node.left` và `Node.right`, nó **không** đi tới `Node.id` (String), backing array của một collection hay các references từ JDK internals. Đó là total của **Node-only graph**, không phải toàn bộ graph heap JVM.

Một generic Java reflective walker còn gặp private fields, superclasses, object arrays, JPMS access, special references, concurrency và GC roots. Không có quyền khẳng định phép cộng shallow của một tập tự khám phá là retained heap toàn JVM.

## 4. Retained size đòi biết mọi đường đi từ GC roots

### 4.1. GC roots và object sống

Garbage collector xem xét reachability từ **GC roots**, tùy runtime/snapshot có thể bao gồm active stack references, static fields thông qua runtime class structures, JNI handles và các nguồn khác.

Một object S được A trỏ tới **không** có nghĩa A là lý do duy nhất khiến S sống. Nếu B cũng được root khác giữ sống và B trỏ tới S thì việc bỏ A không khiến S unreachable.

### 4.2. Dominator: điều kiện “mọi đường đều phải qua x”

Một object `x` **dominates** object `y` nếu **mọi đường từ virtual super-root** nối tới các GC roots liên quan tới y đều phải đi qua x. Nếu tồn tại một root path bỏ qua x, x **không** dominate y.

Retained set của x gồm chính x và mọi objects bị x dominate; retained size trong mô hình heap snapshot là:

~~~text
RetainedSet(x) = { v | x dominates v }
RetainedSize(x) = SUM( shallowSize(v) for v in RetainedSet(x) )
~~~

Dominator tree là một cách biểu diễn quan hệ này. **Cạnh trong dominator tree không nhất thiết là cạnh Java reference trực tiếp**. Một object có thể dominate cả subgraph dù không có field trực tiếp trỏ đến mọi object trong subgraph.

### 4.3. Graph A/B/S/U có retained khác reachable

Giả sử một **mô hình** chỉ có hai roots và bốn object nodes:

~~~text
ROOT_A -> A
ROOT_B -> B
A -> S
A -> U
U -> A
B -> S
~~~

Khi đó:

- A dominates U, vì mọi root path tới U đi qua A.
- A **không** dominate S: có đường `ROOT_B -> B -> S`.
- B **không** dominate S: có đường `ROOT_A -> A -> S`.
- Retained set của A theo mô hình = `{A,U}`.
- Retained set của B = `{B}`.
- Reachable từ A vẫn là `{A,S,U}`, **nhiều hơn** retained set A.

Đây là minh họa quan trọng: **không thể đổi tên ReachableShallowSum(A) thành RetainedSize(A)** nếu S được dùng chung.

### 4.4. Ví dụ số chỉ để làm toán

Giả sử shallow sizes giả định:

| Node | Bytes giả định |
|---|---:|
| A | 24 |
| B | 24 |
| S | 40 |
| U | 24 |

Kết quả trong **mô hình**:

~~~text
Shallow(A) = 24

ReachableSum(A) = 24(A) + 40(S) + 24(U) = 88
ReachableSum(B) = 24(B) + 40(S) = 64

Sum riêng = 88 + 64 = 152    (S bị đếm 2 lần)
Union unique = 24 + 24 + 40 + 24 = 112

Retained(A) = 24(A) + 24(U) = 48
Retained(B) = 24(B)
~~~

**24 và 40 là số minh họa**, không phải kích thước object thực của Java 17. Cùng A cho shallow=24, reachable=88 và retained=48 (trong mô hình GC-root paths đã định). Một JVM thực có thể có object layout và root paths khác hoàn toàn.

### 4.5. Phép trừ reachable sets không phải thuật toán retained tổng quát

Trong model trên, `R(A) - R(B) = {A,U}` trùng retained set A vì **đã giả định tất cả root paths** chỉ qua A và B. Nhưng trong JVM thật:

- Local variables, thread stacks, static fields hoặc JNI có thể giữ A/U/S bằng đường khác.
- Object fields không được graph Node-only duyệt, ví dụ `String id`, cũng là references.
- Nhiều roots có thể tới descendants của A mà không đi qua A.
- Weak/soft/phantom references không có cùng ý nghĩa giữ sống như strong references.

Vì vậy không tổng quát hóa `retained(A)=R(A)-R(B)`. Muốn retained heap thực cần **GC-root graph và dominator analysis**, không phải hai tập của demo.

## 5. Ví dụ Java 17+ hoàn chỉnh: shallow và graph theo identity

Bài thực hành có hai Java source files và một manifest. Java agent nhận `Instrumentation` ở `premain`, ứng dụng dùng `getObjectSize` và duyệt một graph có cycle/shared node.

**Mục đích:** minh họa shallow **khác** reachable sum, và phép cộng hai reachable sets có thể đếm trùng. Demo **không** giả vờ tính retained JVM.

### 5.1. Cấu trúc

~~~text
size-graph-demo/
├── AGENT.MF
├── src/
│   ├── agent/demo/SizeAgent.java
│   └── app/demo/GraphDemo.java
└── out/
    ├── agent/
    ├── app/
    └── size-agent.jar
~~~

### 5.2. `src/agent/demo/SizeAgent.java`

~~~java
package demo;

import java.lang.instrument.Instrumentation;

public final class SizeAgent {
    private static volatile Instrumentation inst;

    private SizeAgent() {}

    public static void premain(String arguments, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static long shallow(Object object) {
        Instrumentation i = inst;
        if (i == null) {
            throw new IllegalStateException("Use -javaagent:size-agent.jar");
        }
        return i.getObjectSize(object);
    }
}
~~~

Agent không đăng ký `ClassFileTransformer` vì không có yêu cầu đổi classfile. Nó chỉ dùng `Instrumentation` để ước lượng shallow size của những instances đã tồn tại. Nếu thiếu `-javaagent`, wrapper ném lỗi rõ ràng thay vì trả một số giả.

### 5.3. `src/app/demo/GraphDemo.java`

~~~java
package demo;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public final class GraphDemo {
    private GraphDemo() {}

    private static final class Node {
        final String id;
        Node left;
        Node right;
        Node(String id) { this.id = id; }
    }

    private static Set<Node> identitySet() {
        return Collections.newSetFromMap(new IdentityHashMap<>());
    }

    private static Set<Node> reachable(Node start) {
        Set<Node> seen = identitySet();
        ArrayDeque<Node> pending = new ArrayDeque<>();
        pending.add(start);
        while (!pending.isEmpty()) {
            Node current = pending.removeLast();
            if (!seen.add(current)) continue;
            if (current.left != null) pending.add(current.left);
            if (current.right != null) pending.add(current.right);
        }
        return seen;
    }

    private static Set<Node> difference(Set<Node> first, Set<Node> second) {
        Set<Node> result = identitySet();
        result.addAll(first);
        result.removeAll(second);
        return result;
    }

    private static Set<Node> union(Set<Node> first, Set<Node> second) {
        Set<Node> result = identitySet();
        result.addAll(first);
        result.addAll(second);
        return result;
    }

    private static String names(Set<Node> nodes) {
        List<String> ids = new ArrayList<>();
        for (Node node : nodes) ids.add(node.id);
        Collections.sort(ids);
        return String.join(",", ids);
    }

    private static long shallowSum(Set<Node> nodes) {
        long result = 0L;
        for (Node node : nodes) {
            result = Math.addExact(result, SizeAgent.shallow(node));
        }
        return result;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node shared = new Node("S");
        Node unique = new Node("U");

        a.left = shared;
        a.right = unique;
        unique.left = a; // Cycle: A -> U -> A
        b.left = shared; // Shared S: A -> S <- B

        Set<Node> fromA = reachable(a);
        Set<Node> fromB = reachable(b);
        Set<Node> all = union(fromA, fromB);
        Set<Node> onlyA = difference(fromA, fromB);

        long aBytes = SizeAgent.shallow(a);
        long separateSums = Math.addExact(shallowSum(fromA), shallowSum(fromB));
        long unionSum = shallowSum(all);
        long duplicateShared = SizeAgent.shallow(shared);

        System.out.println("shallow(A) positive=" + (aBytes > 0));
        System.out.println("reachable(A)=" + names(fromA));
        System.out.println("reachable(B)=" + names(fromB));
        System.out.println("union(A,B)=" + names(all));
        System.out.println("onlyA(model)=" + names(onlyA));
        System.out.println("duplicate S counted twice="
                + (separateSums == unionSum + duplicateShared));
        System.out.println("reachableSum(A) >= shallow(A)="
                + (shallowSum(fromA) >= aBytes));
        System.out.println("JVM retained size measured=no");
    }
}
~~~

### 5.4. Điều gì khiến ví dụ hoạt động?

- `reachable` chỉ đi qua **Node.left/right**, không duyệt Strings trong `Node.id`, các runtime objects khác hoặc GC roots.
- `IdentityHashMap` không nhầm hai instances có `equals` bằng nhau.
- `seen.add(current)` tránh duyệt vô hạn vòng A→U→A.
- `union` hợp hai starting sets trước khi cộng, nên shared object S chỉ có một lần.
- `difference` chỉ là phép so các sets trong model Node-only, không hứa retained.
- `names` sắp xếp labels để output không phụ thuộc thứ tự hash-map iteration.
- `Math.addExact` tránh âm thầm overflow phép cộng; graph demo rất nhỏ.
- `shallowSum` vẫn phải gọi `getObjectSize` **trên từng node**, trong khi `getObjectSize(a)` chỉ xử lý riêng A.

Khi chạy, các locals `a`, `b`, `shared`, `unique` trong chính `main` còn tạo đường giữ sống riêng. **Vì vậy dòng cuối nói thẳng rằng JVM retained size chưa được đo.**

### 5.5. `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.SizeAgent

~~~

Manifest kết thúc bằng newline, `Premain-Class` nằm trong main section. Không cần `Can-Retransform-Classes` hoặc `Can-Redefine-Classes` vì agent không sửa class.

### 5.6. Build và chạy với JDK 17+

Tạo output directories:

Bash/macOS/Linux:

~~~bash
mkdir -p out/agent out/app
~~~

PowerShell/Windows:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

Biên dịch agent, đóng gói JAR, biên dịch ứng dụng:

~~~bash
javac --release 17 -d out/agent src/agent/demo/SizeAgent.java
jar cfm out/size-agent.jar AGENT.MF -C out/agent .
javac --release 17 -cp out/size-agent.jar -d out/app src/app/demo/GraphDemo.java
~~~

Chạy trên Unix:

~~~bash
java -javaagent:out/size-agent.jar -cp "out/app:out/size-agent.jar" demo.GraphDemo
~~~

Chạy trên Windows:

~~~powershell
java -javaagent:out/size-agent.jar -cp "out/app;out/size-agent.jar" demo.GraphDemo
~~~

### 5.7. Stdout đã được biên dịch và kiểm thử

Chương trình lõi đã được **biên dịch với `javac --release 17` và chạy trên JDK 24**; đầu ra đúng:

~~~text
shallow(A) positive=true
reachable(A)=A,S,U
reachable(B)=B,S
union(A,B)=A,B,S,U
onlyA(model)=A,U
duplicate S counted twice=true
reachableSum(A) >= shallow(A)=true
JVM retained size measured=no
~~~

Không in số byte shallow cố định: Javadoc không cam kết cùng object layout/estimate trên mọi JVM.

Muốn in các giá trị **ước lượng thực tế** của JVM hiện tại, thêm mảnh mã sau vào `main` sau khi tạo `fromA`:

~~~java
System.out.println("approxShallowA=" + SizeAgent.shallow(a));
System.out.println("approxNodeSumA=" + shallowSum(fromA));
~~~

Kết quả sẽ thay đổi theo JVM, và phép `approxNodeSumA` vẫn là **tổng của Node-only graph**, không phải retained heap.

### 5.8. Giải thích ý nghĩa từng dòng

| Output | Kết luận hợp lệ |
|---|---|
| `shallow(A) positive=true` | API trả một estimate dương trong JVM chạy demo |
| `reachable(A)=A,S,U` | Từ A tới ba Node instances qua left/right |
| `reachable(B)=B,S` | Từ B tới hai Node instances |
| `union(A,B)=A,B,S,U` | Bốn nodes unique, S chỉ một lần |
| `onlyA(model)=A,U` | A và U không nằm trong reachable set B của model |
| `duplicate S counted twice=true` | Tổng hai sums riêng cộng s(S) lặp |
| `reachableSum(A) >= shallow(A)=true` | Tập reachable A chứa cả A |
| `JVM retained size measured=no` | Không có GC-root/dominator analysis |

## 6. Một thay đổi edge có thể đổi toàn bộ kết luận

Trong `main`, trước khi tính `reachable(a)` và `reachable(b)`, thử:

~~~java
b.right = unique;
~~~

Vì B giờ có đường `B -> U -> A`, nó có thể reach cả A, S và U. Kết quả ở **model** sẽ gồm:

~~~text
reachable(A)=A,S,U
reachable(B)=A,B,S,U
onlyA(model)=
~~~

Phép hiệu rỗng vì tất cả Node của A đều reachable từ B. Điều này cho thấy một **edge duy nhất** có thể làm thay đổi kết quả ownership inference. Nhưng nó không biến phép trừ sets thành retained heap của JVM: các GC roots ngoài model vẫn cần được biết.

## 7. Retained heap thực: sử dụng heap dump và dominator tree

### 7.1. Eclipse Memory Analyzer (MAT)

Eclipse MAT phân tích heap dump và cung cấp những góc nhìn bổ trợ:

| Góc nhìn | Trả lời |
|---|---|
| **Histogram** | Có bao nhiêu instances từng class, tổng shallow heap theo class? |
| **Dominator Tree** | Object/owner nào dominate và retain graph lớn? |
| **Paths to GC Roots** | Vì sao object này tiếp tục reachable từ một root? |
| **Leak Suspects Report** | Những nhóm objects/retainers nào đáng điều tra thêm? |

Dominator tree là **quan hệ giữ sống** chứ không phải cây fields. Một owner nhỏ có thể dominate một cấu trúc lớn ở nhiều cấp reference và có retained heap lớn.

### 7.2. Quy trình chẩn đoán

1. Đọc triệu chứng: Java heap used tăng sau GC, allocation rate cao hay process RSS tăng?
2. Xác định đúng JVM/process, phiên bản JDK, workload và thời điểm cần snapshot.
3. Lấy heap dump bằng công cụ có quyền, kiểm soát chi phí pause/disk.
4. Xem Histogram để biết class nào có shallow heap tổng lớn hoặc instance count bất thường.
5. Xem Dominator Tree để tìm owner có retained heap đáng kể.
6. Xem Paths to GC Roots của owners/children nghi vấn.
7. Đối chiếu với lifecycle: request/session, cache, listeners, ThreadLocal, plugin ClassLoader.
8. So nhiều snapshots hoặc trends khi cần; không kết luận leak chỉ từ một graph lớn tại một thời điểm.

Ví dụ lệnh HotSpot/JDK:

~~~bash
jcmd <pid> GC.heap_dump /secure/path/snapshot.hprof
~~~

**Lệnh mang tính minh họa:** thay `<pid>` và đường dẫn cho môi trường thật. Kiểm tra options khả dụng với `jcmd <pid> help GC.heap_dump` của JVM đang chạy. Heap dump có thể gây tạm dừng, tiêu tốn RAM/disk và chứa thông tin nhạy cảm như token, dữ liệu người dùng hoặc payloads; cần quyền và chính sách bảo mật thích hợp.

### 7.3. Allocation và native memory không phải retained heap

- `Instrumentation.getObjectSize`: shallow estimate một Java object.
- Heap dump/MAT: live heap object graph và retained/dominators.
- JFR/allocation profiler: cấp phát nhiều ở code path nào/tốc độ ra sao.
- Native Memory Tracking/direct-buffer/native profiler: bộ nhớ ngoài Java heap và JVM native allocations.

Allocation rate lớn không nhất thiết là leak nếu objects nhanh trở nên unreachable. Retained heap tăng không nhất thiết đi kèm allocation rate lớn ở hiện tại nếu một cache giữ data tích lũy từ trước.

## 8. Vì sao generic object walker thường đo sai?

Một traversal của graph `Node.left/right` dễ viết vì biết trước schema. Nhưng với arbitrary Java heap:

1. **Nhiều loại references:** instance fields, superclass fields, arrays, collection internals, synthetic fields.
2. **Module boundaries:** JPMS có thể chặn reflective access vào JDK private fields bằng `InaccessibleObjectException`.
3. **Cycles và shared references:** cần visited set theo identity, không phải `equals`.
4. **Weak/soft/phantom refs:** không phải mọi Java field giữ object sống theo strong semantics giống nhau.
5. **GC roots:** một traversal bắt đầu ở một object không biết tất cả incoming root paths.
6. **Concurrency:** graph có thể được sửa trong lúc duyệt, kết quả không nhất quán.
7. **Native memory:** không nằm trọn trong heap graph Java.
8. **Observer effect:** giữ references trong visited set có thể vô tình kéo dài lifetime của objects; traversal tốn CPU/memory.
9. **Custom classloaders:** classes có cùng tên từ loaders khác nhau có identity khác nhau.
10. **Implementation-specific sizes:** ngay tổng shallow của nhiều objects vẫn là tổng các estimates, không phải một phép đo RSS chính xác.

Do đó, một hàm `sumReachable` cần ghi **loại graph nó thực sự duyệt**. Chỉ khi có root information, các loại edges phù hợp và dominator analysis mới có thể dùng nhãn “retained heap”.

## 9. Tình huống thực tế

### 9.1. List chứa nhiều mảng byte

~~~java
List<byte[]> chunks = new ArrayList<>();
for (int i = 0; i < 100; i++) {
    chunks.add(new byte[1024 * 1024]);
}
~~~

Đây là code fragment minh họa (cần imports trong một chương trình riêng). `getObjectSize(chunks)` **không** trả tổng 100 MiB; nó đo chính `ArrayList` object. Backing array và 100 `byte[]` là các objects khác. Retained size của list/owner còn phụ thuộc đường giữ sống khác tới các arrays.

### 9.2. Cache `HashMap`

Shallow size của `HashMap` bỏ qua table array, entry nodes và objects được keys/values trỏ tới. Một cache root có thể retain một graph rất lớn, nhưng nếu values còn được tham chiếu từ caches khác thì reachable sum không bằng retained.

Retained size lớn **không tự động là memory leak**. Một cache hợp lệ được thiết kế lớn vẫn có retained cao; cần kiểm tra TTL, eviction và lifecycle.

### 9.3. ThreadLocal và listeners

Một ThreadLocal value hoặc listener registry có thể giữ graph sống sau khi request hoàn tất. Hãy xem Paths to GC Roots; shallow size của ThreadLocal/listener owner không mô tả toàn bộ retention.

### 9.4. ClassLoader sau redeploy

ClassLoader cũ có thể bị thread context loader, static registry hoặc JNI giữ sống sau redeploy. Retained heap của owner có thể liên quan nhiều class instances và static graphs, dù shallow của ClassLoader nhỏ. Phân biệt Java heap với metaspace/native class metadata.

### 9.5. Shared immutable objects và interned strings

Hai caches cùng dùng một String/payload có cùng **object identity** sẽ khiến reachable sums cộng trùng nếu tính riêng. Xóa một cache không thu hồi object khi cache còn lại vẫn tham chiếu.

### 9.6. Native-backed direct buffer

Một wrapper `DirectByteBuffer` shallow nhỏ có thể sở hữu native region lớn. Muốn giải thích process RSS, cần native/direct metrics; heap retained của wrapper không tự bao gồm toàn bộ off-heap allocation.

## 10. Lỗi phổ biến và cách sửa

| Sai lầm | Vấn đề | Giải pháp |
|---|---|---|
| Gọi `getObjectSize(list)` rồi đặt tên “list total” | Chỉ đo instance list | Phân tích backing/children graph riêng |
| Cho rằng shallow của `Object[]` cộng tất cả element objects | Reference slots khác referents | Đo referents riêng và khử trùng |
| Cho rằng shallow của `byte[]` không cộng phần tử | Primitive elements nằm inline | Hiểu array object layout |
| Cộng mỗi reference gặp được | Cycles/shared gây lặp hoặc đếm hai lần | Identity visited set |
| Dùng `HashSet` theo `equals` | Gộp hai allocations khác identity | Dùng identity set |
| Gán reachable sum bằng retained | Shared GC-root paths phá domination | Dùng dominator tree |
| Coi một outgoing field là ownership duy nhất | Nhiều roots có thể giữ object | Xem Paths to GC Roots |
| Coi size estimate là số byte chuẩn mọi JVM | Javadoc không cam kết | So sánh trong đúng JVM/config |
| Dùng reflection để đi mọi fields JDK | JPMS/các objects nội bộ có giới hạn | Tool heap snapshot được hỗ trợ |
| Quên weak/soft/phantom refs | Reachability không giống strong GC references | Nêu rõ edge semantics |
| Gắn retained heap với RSS | Native/other memory ngoài Java heap | Tách heap và native metrics |
| Retained lớn = leak | Có thể là cache chủ đích | Kiểm chứng lifecycle và trend |

### Retained size không hứa GC thu hồi RAM ngay

Retained trong heap snapshot thường diễn giải “phần memory không còn được giữ sống nếu bỏ owner đúng cách trong root graph”; điều đó **không** bảo đảm GC chạy tức thì hoặc RSS giảm tương ứng. Garbage collector, heap commitment và OS page management là các tầng độc lập.

## 11. Checklist dùng khi khảo sát JVM

**Trước khi đo:**

- [ ] Đã xác định cần shallow, reachable graph sum, retained heap, allocation hay RSS?
- [ ] Java agent nhận `Instrumentation` từ `premain/agentmain` chưa?
- [ ] Không gọi `getObjectSize(null)` hoặc kỳ vọng API tự duyệt graph?
- [ ] Môi trường JVM/vendor, compressed pointers và alignment có được ghi nhận nếu so size?
- [ ] Nếu tự duyệt graph, đã định nghĩa chính xác starting roots và edges chưa?

**Khi tính graph:**

- [ ] Có khử trùng theo identity?
- [ ] Có xử lý cycles/shared objects?
- [ ] Có ghi rõ bỏ qua field/arrays/JDK private internals nào không?
- [ ] Weak/soft/phantom references và concurrent mutation có ảnh hưởng?
- [ ] Có tránh gọi phép sum Node-only là JVM retained size?
- [ ] Nếu cần retained thật, đã dùng heap-root/dominator analyzer chưa?

**Khi kết luận:**

- [ ] Xem cả Histogram, Dominator Tree và Paths to GC Roots?
- [ ] So số liệu qua lifecycle/GC trước khi kết luận leak?
- [ ] Phân biệt off-heap memory và heap?
- [ ] Heap dump và dữ liệu nhạy cảm được bảo vệ đúng cách?
- [ ] Tên chỉ số trong dashboard/report phản ánh đúng phép đo thực hiện?

## 12. Tự kiểm tra kiến thức

**1.** `getObjectSize(new Object[1000])` có cộng shallow sizes của objects được mảng trỏ tới?

> Không. Array có reference slots, không chứa các referenced instances inline.

**2.** `getObjectSize(new byte[1_000_000])` có phản ánh primitive bytes inline không?

> Có. Primitive array là object gồm các phần tử lưu inline, dù số byte layout cụ thể phụ thuộc JVM.

**3.** Vì sao `HashSet` theo `equals` không an toàn để khử trùng heap objects?

> Hai objects khác identity có thể bằng nhau theo value; heap accounting phải giữ mỗi allocation riêng.

**4.** A reachable tới S, B cũng reachable tới S từ root khác. A có dominate S không?

> Không. Có đường qua B tới S bỏ qua A.

**5.** `onlyA(model)=A,U` trong ví dụ có phải retained JVM của A?

> Không. Nó là phép hiệu hai reachable sets theo cạnh Node.left/right; JVM còn local variables/roots và objects khác.

**6.** Một object shallow nhỏ có thể retained lớn không?

> Có, khi nó dominate một graph lớn chỉ được giữ sống thông qua nó.

**7.** Muốn biết ai đang giữ object còn sống nên xem gì?

> Heap dump, Paths to GC Roots và Dominator Tree; sau đó đối chiếu lifecycle.

**8.** Vì sao `getObjectSize(directBuffer)` không phản ánh toàn bộ native memory của buffer?

> API chỉ đo shallow Java wrapper, không tính toàn bộ native backing region.

**9.** Retained lớn có chứng minh leak không?

> Chưa. Phải so với lifecycle, cache policy, roots và trend.

**10.** Allocation rate tăng có bắt buộc retained heap tăng không?

> Không. Objects có thể được cấp phát nhanh nhưng chết nhanh.

**11.** `getObjectSize(x)` có cố định số byte trên mọi JVM/vendor không?

> Không. Javadoc định nghĩa implementation-specific approximation, có thể thay đổi trong cùng một phiên chạy.

**12.** Muốn tổng unique từ roots A, B với node dùng chung thì làm gì?

> Hợp reachable sets theo identity trước khi cộng shallow sizes, không cộng trực tiếp hai sums nếu có shared nodes.

## 13. Tài liệu chính thức và công cụ

- Java SE 17, `Instrumentation.getObjectSize(Object)` — implementation-specific approximation, overhead và NullPointerException: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `java.lang.instrument` — agent `premain` và manifest: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Eclipse MAT, **Dominator Tree** — dominates, immediate dominator, retained set: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html
- Eclipse MAT, **Basic Tutorial** — Histogram, Dominator Tree, Paths to GC Roots: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html
- Eclipse MAT, **Finding Memory Leak** — leak suspects, root paths và retained ownership: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html
- Java SE 17, `jcmd` — công cụ thu heap dump và kiểm tra options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
