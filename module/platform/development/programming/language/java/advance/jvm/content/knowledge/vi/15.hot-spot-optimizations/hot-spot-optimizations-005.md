# Phân tích đối tượng thoát (escape analysis) và thay thế bằng giá trị thành phần trong HotSpot

## 1. Một object xuất hiện trong Java source có bắt buộc được cấp phát trên heap?

Không nhất thiết. Java cho phép viết `new Point(...)` để tạo một đối tượng về mặt **ngữ nghĩa**, nhưng chương trình chỉ được quan sát những hành vi mà ngôn ngữ cam kết: giá trị fields, reference identity khi có thể quan sát, kết quả gọi method, exceptions, đồng bộ, v.v. JVM được quyền tối ưu implementation nếu vẫn bảo toàn các hành vi đó.

Trong **HotSpot/OpenJDK Java 17**, trình biên dịch tối ưu **C2** có thể dùng **escape analysis (EA)** để xác định một object được tạo ra có thể được quan sát ở ngoài phạm vi đang xét hay không. Nếu một object không thoát và thỏa điều kiện triển khai, **scalar replacement of aggregates (SRA)** có thể biến các thao tác trên object thành các thao tác trên **các giá trị thành phần**, chẳng hạn `x` và `y`. Khi đó allocation thực và một số load/store/lock có thể bị loại khỏi mã máy.

Ba khái niệm phải tách bạch:

1. **Escape analysis** là bước **phân tích** dòng dữ liệu và các đường tham chiếu để đánh giá object có thể thoát phạm vi nào.
2. **Scalar replacement** là một phép **biến đổi code**: thay object aggregate bằng những trường/giá trị vô hướng có thể theo dõi độc lập; khi thành công có thể **loại bỏ allocation**.
3. **Lock elimination** là phép bỏ đồng bộ không cần thiết khi compiler chứng minh monitor không tạo ra tác dụng quan sát được giữa threads; nó có liên hệ với EA nhưng **không đồng nghĩa SRA**.

Một lưu ý cực quan trọng: **HotSpot C2 Java 17 không nói chung biến những Java objects không thoát thành heap objects được cấp phát trên Java stack**. Khi scalar replacement thành công, object có thể **không được materialize** như một allocation ở execution path nóng; các giá trị field có thể nằm trong CPU registers, stack slots của compiled frame hoặc được tối ưu tiếp. Đây **khác** việc cấp một object hoàn chỉnh với header trên stack.

### Mục tiêu học tập

Sau bài này, có thể giải thích:

- Object thoát khỏi method, thread hoặc phạm vi compiled graph như thế nào.
- Vì sao `return new Point(...)` và `return p.x + p.y` dẫn tới cơ hội tối ưu khác nhau.
- C2 quan sát allocation/reference graph và dùng **inlining, alias/points-to analysis** làm cơ sở.
- Scalar replacement có thể xóa `new`, field loads/stores và giảm GC pressure như thế nào.
- Những gì compiler cần giữ khi có exceptions, side effects, identity, locks và deoptimization.
- Vì sao **không phải cứ không thoát là chắc chắn hết allocation**.
- Cách kiểm chứng bằng JMH, JFR, allocation counters và đúng HotSpot flags của JDK 17.

Mọi ví dụ Java bên dưới chạy được trên **Java 17+** nếu ghi đầy đủ file; chỉ các đoạn nói rõ là *fragment/pseudocode* mới không độc lập. Những kết quả nào phụ thuộc compiler/GC được ghi rõ **không có output duy nhất**.

## 2. Java heap, stack và các đối tượng “ảo” của optimizer

### Java-level semantics không phải memory layout

Ở Java:

```java
Point point = new Point(3, 4);
int sum = point.x + point.y;
```

Đây là *fragment* minh họa. Về ngữ nghĩa, chương trình khởi tạo một `Point` và đọc hai fields. Nhưng compiler có thể chứng minh không một phần code khác cần nhận diện `point` như một object độc lập.

Sơ đồ trước tối ưu:

```text
Bytecode / mô hình object:
  new Point
  dup
  iconst_3
  iconst_4
  invokespecial Point.<init>
  astore point
  aload point
  getfield x
  aload point
  getfield y
  iadd

  -> sum
```

Sơ đồ sau tối ưu **minh họa**:

```text
  point.x -> scalar x = 3
  point.y -> scalar y = 4

  sum = x + y = 7

  Object header/allocation không cần tồn tại trên hot path
  nếu compiler đã chứng minh toàn bộ điều kiện an toàn.
```

Đây **không phải machine-code disassembly** của một lần chạy đã được xác minh. C2 có thể còn constant-fold `3 + 4` thành `7`, hoặc inlining/escape analysis đã không chạy khi program còn cold.

### Cần phân biệt 4 thứ

| Thành phần | Giải thích |
| --- | --- |
| **Java heap object** | Thực thể runtime được GC quản lý khi object thật sự được cấp phát |
| **Java reference** | Giá trị chương trình dùng để tham chiếu object; không có raw address API chuẩn |
| **Compiled frame/register values** | Nơi CPU/JIT có thể lưu giá trị `x`, `y` hoặc intermediate data |
| **Virtual/scalar-replaced object** | Biểu diễn **logic** trong optimizer, có thể không có allocation vật lý tương ứng trên hot path |

Không thể đo “Java object đã nằm ở stack địa chỉ nào” chỉ bằng `new` trong source. Lập trình viên không kiểm soát được layout ấy và không nên tự đặt yêu cầu “mọi short-lived object phải stack allocate” trên HotSpot Java 17.

## 3. “Escape” là thoát khỏi đâu?

Có ít nhất hai ranh giới quan trọng:

- **Method escape:** reference tới object được tạo ra có thể tồn tại hoặc bị sử dụng ngoài activation/analysis scope của method.
- **Thread escape:** object có thể được quan sát/truy cập bởi thread khác, thường qua field của object được chia sẻ, static reference hoặc một cơ chế xuất bản tương đương.

Ví dụ:

```java
final class Pair {
    int a, b;
    Pair(int a, int b) {
        this.a = a;
        this.b = b;
    }
}
```

Đây là class minh họa không có `main`. Các tình huống:

```java
static int localOnly(int x) {
    Pair p = new Pair(x, 2);
    return p.a + p.b;
}

static Pair returnsObject(int x) {
    return new Pair(x, 2);
}
```

Hai methods là *fragments*, có thể đặt trong một class bao ngoài.

- Ở `localOnly`, nếu mọi sử dụng đã biết, `p` có cơ hội rất tốt để được scalar-replace.
- Ở `returnsObject`, caller nhận một **reference** tới Pair. Ở biên method độc lập, Pair có vẻ escape. Tuy nhiên nếu caller **được inline vào cùng compiled graph** và chỉ đọc fields thì compiler vẫn có thể loại bỏ allocation xuyên qua method boundary.
- Nếu caller lưu reference tới static field hoặc return ra môi trường không được inline/analyzed thì object thường cần materialize.

**Escape có tính phạm vi phân tích.** Một object thoát một method nhỏ không nhất thiết thoát toàn **inlined compilation graph**; và object không qua thread khác vẫn có thể phải heap-allocate để giữ reference identity hoặc do compiler không đủ khả năng chứng minh điều kiện tối ưu.

## 4. Các trạng thái escape thường dùng trong tài liệu HotSpot

Tài liệu HotSpot Server Compiler mô tả các trạng thái phân tích quen thuộc:

| State | Cách hiểu thực hành | Ví dụ mô hình |
| --- | --- | --- |
| **NoEscape** | Compiler chứng minh candidate không thoát và có thể là scalar-replaceable khi đáp ứng các điều kiện liên quan | Tạo `Point`, chỉ đọc fields rồi return `int` |
| **ArgEscape** | Object đi qua argument/callee boundary nhưng không bị kết luận globally escape trong phân tích tương ứng | Truyền vào helper có hành vi được compiler xác định |
| **GlobalEscape** | Object có thể đi ra ngoài phạm vi kiểm soát/thread hoặc tồn tại ở nơi external code truy cập | Lưu vào static field, returned reference khỏi graph, publish sang shared object |

**Không được suy “NoEscape = chắc chắn heap allocation bị xóa”.** Đây là **kết quả phân tích** và cần thỏa thêm điều kiện của scalar replacement pass. Kích thước object, shape của graph, merges, arrays, calls và compiler heuristics có thể ngăn phép biến đổi.

Cũng không nên xem tên `GlobalEscape` như cách mô tả đầy đủ mọi code path ở source: C2 dùng các tập dữ liệu/flow-insensitive analysis và có thể đưa ra kết luận **bảo thủ** khi có một nhánh đủ điều kiện thoát.

## 5. Đường tham chiếu nào làm object thoát?

Những cách thường gặp:

### Trả reference

```java
static Pair makePair(int a, int b) {
    return new Pair(a, b);
}
```

Caller có thể giữ Pair. Nếu optimizer không thấy caller hoặc caller thực sự dùng reference lâu dài, allocation thường phải tồn tại. Nhưng nếu caller inline, kết quả chỉ tính `pair.a + pair.b` thì tối ưu vẫn có thể xảy ra.

### Gán vào static field

```java
static volatile Object published;

static void publish(int a) {
    published = new Pair(a, 10);
}
```

Đây là **fragments**. Value trong `published` được publish tới code khác. Nếu lời gán có thể quan sát, compiler không thể chỉ giữ `a`/`b` ở registers của method rồi làm như object reference đã thực sự tồn tại ở static field.

### Lưu vào object khác đã thoát

```java
static final class Holder {
    Object value;
}
static void attach(Holder external, int x) {
    external.value = new Pair(x, 1);
}
```

Nếu `external` có thể được code khác truy cập sau call, Pair cũng trở nên accessible qua holder. Kết luận escape tùy phân tích receiver/holder và compilation graph.

### Chuyển tới thread khác / queue / callback

```java
static void submit(java.util.concurrent.Executor executor, int id) {
    Pair p = new Pair(id, id + 1);
    executor.execute(() -> System.out.println(p.a + p.b));
}
```

Đây là fragment. Executor có thể xử lý lambda khi method `submit` đã kết thúc; lambda capture `p`, nên compiler phải giữ ngữ nghĩa reference cùng dữ liệu xuyên lifecycle đó. Tuy nhiên compiler có thể tối ưu các phần nội bộ của lambda/Pairs trong những điều kiện hẹp; không khẳng định luôn có chính xác hai allocations (Pair và lambda) cho mọi compiler.

### Gọi method chưa được compiler phân tích đủ

```java
static int passUnknown(Pair p, java.util.function.ToIntFunction<Pair> f) {
    return f.applyAsInt(p);
}
```

Nếu callsite tới implementation cụ thể chưa được inline hoặc có thể publish Pair, optimizer có thể phải bảo thủ. **Không phải bất kỳ argument truyền method đều tự động GlobalEscape**; static/interprocedural analysis hoặc inlining có thể chứng minh callee chỉ đọc field.

## 6. C2 dựa vào points-to / connection graph

Trong HotSpot C2, Escape Analysis dùng cấu trúc phân tích **connection graph (points-to/alias relationships)** trên compiler IR để theo dõi allocations và các tham chiếu có thể trỏ tới object nào.

Mô hình:

```text
new Pair(3, 4)
     |
     v
  P: object allocation node
    / \
   v   v
 field a field b
   |     |
   3     4

Local reference p ----------> P
Static/reference escape? ---> không thấy trong compiled graph

=> P có thể NoEscape / scalar-replaceable
```

Nếu reference `p` được gán vào static/returned field, graph chứa thêm edge tới escape boundary:

```text
Local p -> P -> static published
                      |
                      v
                reachable beyond scope

=> Compiler phải tính đến khả năng P escape
```

Đây là sơ đồ **khái niệm**, không phải định dạng nội bộ chính xác của `escape.cpp`. C2 phải xử lý aliasing, phi nodes, field loads/stores, nested objects, method inlining và exception paths. Đôi lúc một path có vẻ local ở source nhưng compiler không chứng minh được do merge nhiều references.

### Flow-insensitive có ý nghĩa gì?

Một giới hạn đã được OpenJDK phân tích: thuật toán EA truyền thống của C2 là **flow-insensitive** ở những khía cạnh quan trọng. Nếu cùng một allocation có **một nhánh escape**, compiler có thể conservatively coi nó escape ngay cả trên đường đi thường xuyên không thoát.

```java
static volatile Object shared;
static int conditionalEscape(int x, boolean publish) {
    Pair p = new Pair(x, 2);
    if (publish) {
        shared = p;
    }
    return p.a + p.b;
}
```

Đây là fragment. Về mặt logic, khi `publish=false`, object không cần được lưu lại ngoài method. Nhưng **không tự kết luận** HotSpot Java 17 sẽ phát sinh fast path không allocation cho riêng nhánh false. Partial escape analysis cần phép biến đổi sâu hơn, và implementation C2 có các hạn chế; các update JDK 17u khác nhau có thể cải thiện một số trường hợp cụ thể.

Không lấy lời nói “EA phân tích tất cả possible paths” làm bảo đảm **path-sensitive partial allocation** đã có cho mọi hình dạng code.

## 7. Scalar replacement of aggregates (SRA): thao tác từng field

Giả sử:

```java
static final class Point {
    int x;
    int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}

static int compute(int input) {
    Point p = new Point(input, input + 1);
    p.x += 2;
    return p.x * p.y;
}
```

Đây là fragments, chưa có `main`. Các field operations có thể được biểu diễn:

```text
Original logical object:
  p = new Point(input, input+1)
  p.x = p.x + 2
  result = p.x * p.y

Scalar form:
  x = input
  y = input + 1
  x = x + 2
  result = x * y

Nếu không phải materialize p, loại bỏ allocation/header/field memory ops.
```

Chú ý compiler có thể đặt `x`, `y` trong registers hoặc stack slots tùy register allocator. Không có lời hứa rằng “mỗi field trở thành đúng một Java local variable trên stack”. Cũng không có lời hứa C2 sinh chính xác cùng số machine instructions như sơ đồ.

### Vì sao giảm allocation giúp GC?

Nếu mỗi request tạo hàng ngàn temporary wrappers/points nhỏ và optimizer loại bỏ nhiều allocations:

- Giảm bytes allocated trên Java heap.
- Giảm số object headers và các initialization/write operations liên quan.
- Giảm áp lực vào Eden/TLAB và có thể giảm young GC frequency.
- Giảm lượng data GC phải scan hoặc copy nếu object thật sự không tồn tại.
- Cho phép compiler tiếp tục constant propagation, dead-store elimination và strength reduction.

Nhưng **không phải mọi allocation giảm đều chuyển thành tốc độ tăng tương ứng**. HotSpot TLAB allocation vốn rất nhanh; bottleneck khác như I/O, CPU branch misprediction hoặc memory access có thể chiếm nhiều hơn.

## 8. Java 17 hoàn chỉnh: object tạm chỉ dùng để tính số

Tạo file **`ScalarPointDemo.java`**:

```java
public class ScalarPointDemo {
    static final class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }
    }

    static int score(int input) {
        Point p = new Point(input, input + 1);
        return p.x * 2 + p.y;
    }

    public static void main(String[] args) {
        System.out.println("score3=" + score(3));
        System.out.println("score10=" + score(10));
    }
}
```

Biên dịch/chạy Java 17:

```bash
javac --release 17 ScalarPointDemo.java
java ScalarPointDemo
```

**Stdout chính xác:**

```text
score3=10
score10=31
```

Công thức `2×input + (input+1) = 3×input+1`. Object `Point` không thoát khỏi `score` theo Java source; về nguyên tắc phù hợp cho EA/SRA sau khi JIT compile/inline. **Hai dòng output không chứng minh `new Point` đã bị loại bỏ.** Có thể JVM chưa kịp C2 compile, hoặc compiler đã thực hiện các optimization khác.

Nếu muốn học riêng tác động của EA, cần đo trong workload lặp lại đủ dài và so flags/metrics trên cùng JVM; không đưa bất kỳ con số “object allocations = 0” nào như sự thật mặc định.

## 9. Quan hệ giữa inlining và escape analysis

Inlining thay method call bằng logic callee trong **compiled graph**. Điều này có thể giúp EA nhìn thấy một object chỉ được dùng để đọc fields, dù đã được truyền qua ranh giới method source.

Ví dụ:

```java
static int consume(Pair p) {
    return p.a + p.b;
}

static int calculation(int x) {
    Pair temporary = new Pair(x, x + 1);
    return consume(temporary);
}
```

Đây là fragments. Nếu `consume` được inline, optimizer có thể thấy:

```text
new Pair(x, x+1)
    |
    +--> load a
    +--> load b
    |
    v
return a+b

=> Pair allocation có thể scalar-replace nếu không escape.
```

Nếu `consume` quá lớn, có lời gọi unknown/native hoặc **không được inline**, compiler có thể khó chứng minh properties cần thiết. C2 có một số khả năng interprocedural EA hạn chế, nhưng **không** được giả định optimizer nhìn xuyên mọi method/library boundary.

### Không phải inlining lúc nào cũng tốt

C2 có **inline budgets**, giới hạn method size/call depth và phải cân bằng compiled code size, compile time, CPU instruction cache và runtime throughput. Ép inline quá nhiều có thể làm compiled methods phình to, làm EA graph phức tạp và giảm hiệu quả ở vùng code khác.

Vì thế câu “cứ tách method nhỏ thì escape analysis thất bại” cũng sai: inlining có thể nối chúng lại; ngược lại, một method rất lớn với phức tạp control flow không có nghĩa EA sẽ thành công.

## 10. Object không thoát vẫn có thể không được scalar-replace

Những trở ngại thường gặp (không phải điều kiện đủ để **chắc chắn** thất bại trong mọi release):

- **Control-flow merges:** cùng một biến reference sau `if` có thể trỏ đến hai allocations khác nhau; compiler cần xử lý phi nodes/aliasing.
- **Conditional escape:** object chỉ thoát một nhánh, nhưng flow-insensitive EA có thể đánh giá bảo thủ.
- **Non-inlined calls:** object truyền tới method chưa được phân tích đủ hoặc native call.
- **Loop-carried object state:** một object được cập nhật/truyền qua nhiều iterations với references/merges phức tạp.
- **Identity-sensitive behavior:** object thật sự cần reference identity, monitor, identity hash hoặc tương tác native/reflection.
- **Arrays:** variable index access, unknown sizes, aliasing hoặc array-copy semantics có thể làm scalarization khó hơn.
- **Large/nested object graphs:** chi phí biểu diễn từng field/element có thể vượt compiler limits.
- **Deoptimization state:** JIT phải bảo đảm có đủ thông tin để phục hồi object với fields/identity đúng khi cần.
- **Escape through exceptions:** một exception object hoặc cause/stack trace được return/throw có thể có lifetime và observation khác temporary math objects.
- **JVMTI/agent/debug instrumentation:** một số runtime observations/flags có thể thay đổi những optimization có thể áp dụng.

**NoEscape không phải code-generation guarantee.** Một object nhỏ không thoát vẫn có thể được heap-allocated nếu C2 chưa chạy, compiler budget không cho phép hoặc analysis bảo thủ.

### Control-flow merge minh họa

```java
static int mergeExample(boolean chooseNew, int x) {
    Pair p = new Pair(1, 2);
    if (chooseNew) {
        p = new Pair(x, x + 1);
    }
    return p.a;
}
```

Đây là fragment. Tại `return`, `p` có thể là object cũ hoặc mới. Một optimizer lý tưởng có thể biến code thành `chooseNew ? x : 1`; nhưng **không thể khẳng định C2 Java 17 luôn scalar-replace cả hai allocations**. Bản cập nhật JDK 17 khác nhau có thể có những khả năng xử lý merge khác nhau; đọc đúng JDK build và test thay vì thuộc lòng một danh sách “C2 không bao giờ”.

## 11. Lock elimination: bỏ đồng bộ vô ích khi object không chia sẻ

Java `synchronized` có thể áp dụng với một object không bao giờ được chia sẻ sang thread khác:

```java
static int localLock(int x) {
    Object privateLock = new Object();
    synchronized (privateLock) {
        return x + 1;
    }
}
```

Đây là method fragment. Nếu compiler chứng minh không thread khác có thể quan sát `privateLock` và mọi semantics khác được bảo toàn, HotSpot C2 có thể **loại bỏ thao tác locking/unlocking** không có tác dụng cạnh tranh thực.

**Điểm cần phân biệt:**

- EA phát hiện mức độ object có thể escape.
- Lock elimination loại bỏ một số monitor-enter/exit của compiled code khi hợp lệ.
- Scalar replacement có thể đồng thời loại bỏ allocation của lock object, nhưng **hai phép tối ưu không đồng nghĩa**.
- Không có bảo đảm Java compiler sẽ bỏ `synchronized` trong mọi trường hợp.
- Khi lock monitor là object có thể chia sẻ/cần phối hợp threads, compiler **không** được bỏ tác dụng đồng bộ yêu cầu bởi Java Memory Model.

### Vì sao synchronized vẫn phải đúng về exceptions?

Java `synchronized` cần bảo đảm monitor được giải phóng khi block kết thúc hoặc ném exception. Nếu JIT chứng minh lock hoàn toàn thread-local và tối ưu, nó vẫn phải giữ mọi **Java-visible result và exception behavior**, kể cả khi code đã deoptimized hoặc chuyển execution representation.

Đừng “tối ưu thủ công” bằng cách xóa synchronized trên shared data chỉ vì từng thấy JIT lock elimination trong một microbenchmark. JMM vẫn áp dụng đầy đủ.

## 12. Java 17 hoàn chỉnh: đồng bộ qua object riêng tư

Tạo file **`PrivateLockDemo.java`**:

```java
public class PrivateLockDemo {
    static int guardedSum(int a, int b) {
        Object lock = new Object();
        synchronized (lock) {
            return a + b;
        }
    }

    public static void main(String[] args) {
        System.out.println("sum=" + guardedSum(10, 32));
        System.out.println("same=" + (guardedSum(1, 2) == 3));
    }
}
```

```bash
javac --release 17 PrivateLockDemo.java
java PrivateLockDemo
```

**Stdout chính xác:**

```text
sum=42
same=true
```

Lệnh `synchronized` là Java code hợp lệ; việc compiler có loại bỏ monitor runtime hay không **không quan sát trực tiếp từ stdout**. Dùng debug/compiler diagnostics hoặc benchmarking có kiểm soát nếu mục tiêu là xác nhận lock elision, không dựa vào thời gian của một lần gọi.

## 13. Identity, hash code và hành vi quan sát object

Một temporary object chỉ dùng để đọc hai fields có vẻ có thể scalar-replace. Nhưng có những operations làm **identity** thành một phần observable semantics:

```java
static boolean sameReference(Object x, Object y) {
    return x == y;
}
```

Đây là fragment. Khi identity được dùng, HotSpot vẫn có thể tối ưu một số tình huống bằng phân tích aliasing mà **không bắt buộc materialize object**, nhưng phải bảo toàn:

- `a == b` trả đúng nếu cả hai references biểu diễn cùng logical object.
- Hai objects khác biệt về identity không được biến thành một object do scalar replacement.
- `System.identityHashCode(obj)` có semantics ổn định với **cùng object** (không phải raw memory address), và có thể tác động tới khả năng eliminate allocation.
- `synchronized(obj)`, `wait`, `notify`, JNI handles, identity-sensitive reflection/agent observations cần đúng contract.

**Tránh khẳng định quá mức:** “gọi `identityHashCode` luôn ngăn EA” chưa chắc đúng với mọi optimizer, và “object không thoát thì mọi identity operation đều miễn phí” cũng sai. Chỉ khi đã hiểu compiler codegen và deoptimization obligations mới có kết luận cho JDK/build cụ thể.

### Java object không trở thành giá trị (value type) chỉ vì SRA

Một Java class bình thường vẫn có **reference identity semantics**. Scalar replacement là lựa chọn internal codegen của JIT cho **một execution context**, không làm class thành primitive type, record value type không identity, hay biến đổi API contract.

## 14. Deoptimization: khi object ảo phải có hình dạng Java trở lại

HotSpot C2 thường tối ưu dựa vào dynamic profile và giả định có guards. Nếu một assumption không còn đúng, JVM có thể thực hiện **deoptimization** để khôi phục execution state tương thích với interpreter/compiled tier khác.

Giả sử trong optimized code:

```text
Java source:
  Point p = new Point(3, 4);
  int total = p.x + p.y;

Optimized state:
  virtual Point {x=3, y=4}
  total = 7
  không có object heap ở đường hot
```

Nếu deoptimization cần local `p` tiếp tục tồn tại với Java semantics, VM có thể phải **materialize/reallocate** object tương ứng dựa trên metadata ghi lại các fields và references.

```text
Nmethod optimized execution
  |
  | uncommon trap / invalidated assumption
  v
Deopt metadata:
  virtual object Point(x=3,y=4)
  |
  v
materialization / reconstruction khi cần
  |
  v
Interpreter-compatible frame, đúng Java behavior
```

**Hai nhầm lẫn cần tránh:**

1. Không phải mọi scalar-replaced object “nằm trên stack” từ đầu, rồi deopt chỉ sao chép nguyên object ấy ra heap. Có khi **không tồn tại object vật lý trước deopt**.
2. Không phải bất cứ deoptimization nào cũng chắc chắn tạo lại một object. Compiler/runtime chỉ làm những thao tác cần thiết để bảo toàn semantics của **trạng thái sống** phải phục hồi.

Deoptimization cost có thể bao gồm reconstruct states, materialize virtual objects và chuyển tier. Vì vậy một optimization tốt trên hot path vẫn có thể gây spike nếu speculative assumptions đổi thường xuyên.

## 15. Ví dụ Java 17: escape khi trả object, không escape khi chỉ trả scalar

Tạo file **`EscapePathDemo.java`**:

```java
public class EscapePathDemo {
    static final class Pair {
        final int left;
        final int right;

        Pair(int left, int right) {
            this.left = left;
            this.right = right;
        }
    }

    static int computeScalar(int value) {
        Pair pair = new Pair(value, value + 2);
        return pair.left + pair.right;
    }

    static Pair createReference(int value) {
        return new Pair(value, value + 2);
    }

    public static void main(String[] args) {
        int a = computeScalar(5);
        Pair b = createReference(5);
        System.out.println("scalar=" + a);
        System.out.println("pair=" + (b.left + b.right));
        System.out.println("sameResult=" + (a == b.left + b.right));
    }
}
```

```bash
javac --release 17 EscapePathDemo.java
java EscapePathDemo
```

**Stdout chính xác:**

```text
scalar=12
pair=12
sameResult=true
```

Đây là cách minh họa **khác biệt API** giữa method trả `int` và method trả object. `createReference` trả object về caller nên về mặt method boundary có escape. Tuy nhiên, nếu JIT **inline cả createReference và các phép đọc fields trong main** thì nó vẫn có thể loại allocation trong compiled graph. Vì vậy chương trình **không chứng minh** chính xác method nào đã thật sự heap-allocate.

Không dùng `System.identityHashCode` để đọc địa chỉ object nhằm “chứng minh” object nằm trên stack hoặc heap.

## 16. Interprocedural EA và những giới hạn của call graph

C2 có thể phân tích một số callees để hiểu object arguments mà không nhất thiết phải inline toàn bộ, nhưng phạm vi vẫn có giới hạn về bytecode, call shape, virtual dispatch và compiler budget.

**Inlining đặc biệt quan trọng** vì nó mở rộng compiled graph, giúp optimizer thấy toàn bộ các uses của candidate object. Khi code có polymorphic dispatch, reflection, JNI hoặc native call, compiler khó chứng minh caller-owned temporary object không thoát.

Ví dụ:

```java
interface Consumer {
    int use(Pair pair);
}

static int callThroughInterface(Pair pair, Consumer consumer) {
    return consumer.use(pair);
}
```

Fragment này có khả năng receiver `consumer` thay đổi runtime type; C2 có thể devirtualize/inlining nhờ type profile/CHA trong một số cases nhưng không hứa luôn thành công.

Không viết rằng “object truyền vào phương thức khác chắc chắn thoát”, vì điều đó sai khi callee được inline hoặc compiler biết nó chỉ đọc fields. Cũng không viết “compiler luôn nhìn xuyên mọi call”, vì điều đó quá lạc quan.

## 17. Scalar replacement cho arrays có khác objects fields không?

Đối với một object có một số fields kích thước cố định, optimizer có thể dễ thay từng field bằng SSA values. Với arrays, compiler phải xử lý:

- **Array length:** có được biết hoặc giới hạn hợp lý?
- **Index:** là constant, small known range hay biến động khó chứng minh?
- **Aliasing:** nhiều references trỏ cùng array, array được truyền qua calls nào?
- **Bounds checks:** có thể loại mà vẫn giữ exception semantics?
- **Arraycopy/clone:** có semantics và lifetime phù hợp để scalarize không?
- **Object/reference elements:** liệu objects bên trong cũng escape hoặc cần giữ identity không?
- **Loop-carried state:** array bị cập nhật qua iterations có làm graph phức tạp không?

Một temporary `int[]` kích thước nhỏ với constant indexes có thể là candidate. Nhưng **không có bảo đảm HotSpot Java 17 tự xóa mọi `new int[3]`**; constraints/optimizations phụ thuộc build và compiled graph.

### Ví dụ chỉ minh họa cơ hội tối ưu

```java
static int fromSmallArray(int x) {
    int[] values = {x, x + 1, x + 2};
    return values[0] + values[2];
}
```

Đây là fragment. Nếu compiler có đủ thông tin, có thể đơn giản hóa thành `2*x + 2`. Không dùng code này để hứa `int[]` không tồn tại trong heap của mọi Java implementation.

## 18. C2 EA truyền thống có hạn chế về flow merges và vòng lặp

Theo báo cáo nghiên cứu OpenJDK về escape analysis:

- Một allocation chỉ escape ở **một nhánh** vẫn có thể bị xét bảo thủ.
- **Phi/merge** giữa hai references khác allocations có thể hạn chế scalar replacement.
- **Loop-carried allocations** và values đi qua iterations có thể khó optimize.
- **Non-inlined helpers**, bytecode size limits và call graphs phức tạp có thể ngăn candidate NoEscape.
- Những cải tiến như **allocation merge reductions** ở một số cập nhật JDK 17u có thể thay đổi kết quả cho pattern cụ thể; phải khóa **17.0.x vendor/build** để kết luận.

Điều này giải thích vì sao hai snippets nhìn “cùng không thoát” trên source lại có allocation rate rất khác trên JMH.

### Flow-insensitive không có nghĩa không phân tích control flow gì cả

Nó là cách mô tả **đặc tính thuật toán EA** và nơi compiler phải đưa ra kết luận bảo thủ, không có nghĩa C2 hoàn toàn không biết `if`, SSA, branches hoặc types. Compiler còn nhiều passes khác có thể tối ưu logic dù EA/SRA không xử lý hết pattern.

## 19. Flags liên quan trên HotSpot Java 17

Những flags hay dùng trong thí nghiệm về EA/SRA:

| Flag | Vai trò khái quát |
| --- | --- |
| `-XX:+DoEscapeAnalysis` | Cho phép EA; thường bật mặc định với C2 phù hợp |
| `-XX:-DoEscapeAnalysis` | Tắt EA để so sánh có kiểm soát |
| `-XX:+EliminateAllocations` | Cho phép allocation elimination/SRA khi điều kiện đạt |
| `-XX:-EliminateAllocations` | Tắt phần allocation elimination nhằm cô lập ảnh hưởng |
| `-XX:+EliminateLocks` | Cho phép một số lock elimination nếu hợp lệ |
| `-XX:-EliminateLocks` | Tắt lock elimination để đối chiếu |
| `-XX:+PrintCompilation` | Quan sát compilation events/tiers (không nói allocation đã bị xóa) |
| `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` | Quan sát inlining decisions trên build hỗ trợ |
| `-XX:-TieredCompilation` | Thay đổi chiến lược tiering; không phải công tắc đơn giản bật EA |

**Không giả định mọi HotSpot build chấp nhận đúng mọi flag ở mọi chế độ**. Kiểm tra flags ở runtime đang chạy:

```bash
java -XX:+PrintFlagsFinal -version
```

Lọc tên `DoEscapeAnalysis`, `EliminateAllocations` và `EliminateLocks` bằng công cụ phù hợp OS. Không hard-code một default qua mọi JDK distributions.

**Tránh hướng dẫn bật `-XX:+PrintEscapeAnalysis` hay `-XX:+PrintEliminateAllocations` như lệnh chắc chạy trên product HotSpot builds.** Những option này thường chỉ khả dụng trong **non-product/debug builds**; trên production VM có thể bị từ chối. Dùng JMH/allocation profiling/assembly diagnostics được hỗ trợ và ghi rõ build.

## 20. Vì sao không nên đo EA bằng một lần System.nanoTime?

Giả sử:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    new Point(i, i + 1);
}
System.out.println(System.nanoTime() - start);
```

Đây là fragment **không phải benchmark đáng tin**:

- **Dead-code elimination:** object không được dùng; compiler có thể loại toàn bộ logic rất dễ.
- **Constant folding**: input và tính toán có thể được tính trước.
- **Loop optimizations**: unrolling, elimination hoặc vectorization làm số operation khác source.
- **JIT warmup:** test ngắn đo interpreter/C1/C2 compilation lẫn nhau.
- **GC/OS scheduling** làm latency thay đổi theo hệ thống.
- **Object allocation** trên TLAB rất nhanh; chênh lệch một loop đơn có thể nhỏ và sai số lớn.
- **Disable EA flag** có thể ảnh hưởng nhiều optimization khác, không thể mặc định mọi delta CPU là “thời gian allocate Point” thuần.

Dùng **JMH** với forks/warmup/measurement/Blackhole hoặc return value có thể quan sát. Kết hợp **allocation rate per operation**, CPU time và latency, thay vì chỉ một con số nanoseconds.

## 21. Mô hình phép đo: so hai JVM configurations

Khi nghiên cứu EA, có thể thực hiện **hai lần chạy riêng biệt cùng workload**:

```bash
java -XX:+PrintCompilation ScalarPointDemo
java -XX:-DoEscapeAnalysis ScalarPointDemo
```

Các lệnh trên chạy ví dụ logic nhưng **không** cho benchmark được: chương trình kết thúc rất nhanh, chưa chắc có C2 compiled hot path. Dùng một JMH benchmark thích hợp và chạy nhiều forks để so:

- A: default EA on.
- B: `-XX:-DoEscapeAnalysis`.
- C nếu cần: `-XX:-EliminateAllocations` và giữ EA theo VM build.
- Các flags khác, heap, GC, threads, machine load tương đương.
- Có warmup đủ để cả hai chạy ở mức compilation so sánh được.

**Kết luận đúng:** nếu A có allocation bytes/op thấp hơn B trong benchmark đủ tin cậy thì EA/SRA có thể góp phần, nhưng cần xem effects khác, codegen và compiler diagnostics. Không coi mọi chênh lệch do duy nhất “Point trên stack”.

### Đơn vị bytes/op cần hiểu

- Allocation profiling của JFR có thể là sampled events, **không chắc** đếm mọi allocation chính xác từng byte.
- Per-thread allocated-bytes counters từ `com.sun.management.ThreadMXBean` (khi supported/enabled) có semantics theo thread, không giống process RSS/heap used.
- Heap used snapshots giảm do GC; **delta used heap không phải cumulative allocated bytes**.
- JMH `gc.alloc.rate.norm` có thể giúp định lượng bytes/op theo profiler phù hợp, nhưng vẫn là công cụ/implementation-specific measurement cần warmup và forks.
- Allocation “0 B/op” được quan sát **trong một benchmark cụ thể** không phải định luật rằng mọi call production đều không allocate.

## 22. Ví dụ đo allocated bytes bằng API HotSpot mở rộng (Java 17)

Trong JDK có module `jdk.management`, giao diện `com.sun.management.ThreadMXBean` cung cấp chức năng đo lượng heap memory đã allocated **theo thread** nếu VM hỗ trợ. Đo ví dụ này có **output động**, không in một giá trị bytes cố định.

Tạo file **`ThreadAllocationProbe.java`**:

```java
import java.lang.management.ManagementFactory;

public class ThreadAllocationProbe {
    static volatile int sink;

    static int calculation(int i) {
        int[] numbers = {i, i + 1, i + 2};
        return numbers[0] + numbers[2];
    }

    public static void main(String[] args) {
        java.lang.management.ThreadMXBean base =
                ManagementFactory.getThreadMXBean();

        if (!(base instanceof com.sun.management.ThreadMXBean bean)
                || !bean.isThreadAllocatedMemorySupported()) {
            System.out.println("thread-allocation=unsupported");
            return;
        }

        if (!bean.isThreadAllocatedMemoryEnabled()) {
            bean.setThreadAllocatedMemoryEnabled(true);
        }

        long tid = Thread.currentThread().getId();
        long before = bean.getThreadAllocatedBytes(tid);

        int local = 0;
        for (int i = 0; i < 100_000; i++) {
            local += calculation(i);
        }
        sink = local;

        long after = bean.getThreadAllocatedBytes(tid);
        System.out.println("supported=true");
        System.out.println("deltaNonnegative=" + (after >= before));
        System.out.println("checksum=" + sink);
    }
}
```

```bash
javac --release 17 ThreadAllocationProbe.java
java ThreadAllocationProbe
```

Với môi trường `ThreadMXBean` hỗ trợ/enabled và trả counters hợp lệ, chương trình in:

```text
supported=true
deltaNonnegative=true
checksum=1410165408
```

**Kiểm tra phép tính:** một lượt `calculation(i)` trả `i + (i+2) = 2i+2`. Tổng số học toán học từ `i=0` tới `99.999` là `10.000.100.000`; Java `int` có overflow modulo 2³² nên kết quả `(10.000.100.000 mod 2³²) = 1.410.165.408`. Ở một VM không hỗ trợ, chỉ in:

```text
thread-allocation=unsupported
```

**Cảnh báo:** `getThreadAllocatedBytes` có thể trả số âm như `-1` trong những tình huống disabled/unavailable; production code cần xử lý tình huống đó. Demo đơn giản chủ yếu minh họa API, **không in allocation delta** để tránh gán một số phụ thuộc JIT/GC. JVM cũng có thể không cho thay đổi trạng thái đo ở một số môi trường; chương trình khi đó có thể cần quyền/cấu hình phù hợp.

Nếu mục tiêu là so hai JIT configurations, API nên được dùng trong benchmark đủ warmup, trừ overhead đo, đo lặp nhiều lần và xác nhận method thực sự được C2 compiled.

## 23. Kiểm tra số học trên int overflow khi scalar replacement

EA/SRA **không được phép đổi các quy tắc số học của Java**. Trong các ví dụ:

- `int` arithmetic wrap-around modulo 2³² khi overflow (trong biểu diễn signed two's-complement), nếu không dùng các phương pháp kiểm tra overflow như `Math.addExact`.
- Scalar replacement chỉ biến cách lưu trữ/trao đổi fields, không đổi kết quả do phép toán integer.
- Object field initialization/default values vẫn phải bảo toàn: nếu một field không được gán trong constructor, Java có default value 0/false/null theo kiểu.
- Side effects trong constructor (ghi static, I/O, throw exception) không thể tự bị xóa tùy ý chỉ vì object local không escape; compiler phải giữ observable behavior.

### Ví dụ constructor có side effect

```java
static int constructed;

static final class LoggedPoint {
    final int x;
    LoggedPoint(int x) {
        constructed++;
        this.x = x;
    }
}
```

Đây là fragment. Compiler có thể không cần vật lý cấp phát `LoggedPoint` nếu phù hợp, nhưng **không được bỏ tác dụng tăng `constructed`** nếu trạng thái ấy có thể được quan sát theo Java semantics. Không dùng “scalar replacement = bỏ mọi câu lệnh trong constructor” làm quy tắc.

## 24. Liên hệ với Garbage Collection và live set

EA/SRA không phải GC algorithm. GC thu hồi các **objects đã allocated và không còn reachable**, còn scalar replacement có thể làm cho một số logical objects **chưa từng cần tồn tại như heap allocation trên hot path**.

Ví dụ giả định (đây không phải benchmark):

```text
Trước:
  1.000.000 operations/s
  mỗi operation tạo một temporary 24-byte object trên heap
  => khoảng 24 MB/s payload/object layout tùy runtime

Sau EA/SRA thành công:
  nhiều temporary object allocations được loại
  => tốc độ heap allocation có thể giảm đáng kể
  => young GC activity có thể giảm nếu workload tương ứng
```

Đừng dùng 24 byte làm “kích thước chính xác” cho một class Java: header, compressed oops, field alignment và JVM flags quyết định real object size.

**Nếu object không escape nhưng scalar replacement thất bại**, nó vẫn có thể được heap-allocated bình thường rồi được GC thu hồi khi không còn reachable. Vì vậy mô hình Java “objects được GC quản lý trên heap” và tối ưu EA/SRA không mâu thuẫn ở cấp hành vi người dùng.

## 25. Scalar replacement có làm cache, listener, ThreadLocal bớt leak không?

Không theo nghĩa xóa các object đang bị giữ bởi **strong reference paths**. Nếu một object được lưu vào static cache, được callback giữ hoặc nằm trong long-lived `ThreadLocal`, nó có đường giữ sống mà VM cần tôn trọng. EA không được “scalarize rồi biến mất” một object mà ứng dụng vẫn có thể truy cập qua reference ấy.

Trong những tình huống đó cần sửa lifecycle:

- Cache có capacity/weight bounds và eviction/invalidation.
- Listener/observer unsubscribe khi owner đóng.
- ThreadLocal remove/restore trong `finally` sau request/task.
- Queues/backpressure giới hạn số object giữ đồng thời.

EA hữu ích cho **temporary allocations trong hot methods**, không thay thế garbage collector và không sửa **logical memory leak** ở application.

## 26. Tình huống escape qua record, StringBuilder và wrappers

### Record không tự đồng nghĩa scalarized

Java 17 hỗ trợ **records**:

```java
record PointRecord(int x, int y) {}

static int calculate(int n) {
    PointRecord p = new PointRecord(n, n + 1);
    return p.x() + p.y();
}
```

Đây là fragment nằm trong class phù hợp. Record là class có references/object identity theo Java 17, không phải primitive/value object. C2 có thể inline accessor và scalar-replace instance nếu đủ điều kiện, nhưng **record syntax không bảo đảm allocation elimination**.

### StringBuilder trong nối chuỗi

Một số chuỗi nối trong Java hiện đại có thể được triển khai bằng `invokedynamic`/StringConcatFactory và tối ưu theo chiến lược riêng. Đừng kết luận chỉ vì source có `new StringBuilder` hay phép `+` mà có một allocation cho mỗi thao tác, cũng đừng gán mọi tối ưu string concatenation cho EA/SRA. Dùng allocation profiler theo đúng JDK version.

### Boxing

`Integer.valueOf` có thể dùng cache ở một số giá trị, hoặc JIT unbox/optimize. Giảm boxing allocations có nhiều nguyên nhân: primitive specialization, cache, inlining, EA/SRA. Không khẳng định mọi `Integer` wrapper nhìn thấy trong source chắc bị scalar-replace.

## 27. Khi nào nên viết code “EA-friendly”?

Tập trung vào cách viết **rõ ngữ nghĩa**:

1. Tạo temporary immutable-ish objects khi giúp code dễ hiểu; đừng tự pooling mọi Point/DTO.
2. Giữ lifetimes và ownership rõ ràng; tránh publish reference khi không cần.
3. Nếu helper chỉ đọc fields, design API có thể inline được; nhưng đừng phân mảnh/ép inline code theo cảm tính.
4. Tránh giữ các temporary graphs vào static caches/listeners/ThreadLocal chỉ để “tiện debug”.
5. Dùng primitive locals khi một giá trị thật sự là scalar và code đơn giản hơn, thay vì ép object model bất lợi.
6. Đừng thay API đúng bằng code thủ công phức tạp chỉ vì chưa đo được EA.
7. Không tự bỏ synchronization khi object được chia sẻ.
8. Đo **allocation bytes/op**, GC pressure và end-to-end latency trước/sau bằng benchmark hợp lệ.
9. Khi C2 không optimize, xem control flow merges, method inlining, unknown calls, array indexes và identity-sensitive operations.
10. Đối chiếu đúng **JDK 17 build**: C2 EA có những cải tiến qua các cập nhật 17u.

Lợi ích quan trọng của EA/SRA là **JVM có thể tự tối ưu code object-oriented bình thường**. Code rõ ràng, không escape và được inline thích hợp đôi khi vừa maintainable vừa nhanh.

## 28. Thực hành: thiết kế một microbenchmark có thể kiểm chứng

Trên Java 17, bạn có thể tạo JMH benchmark (JMH phải được thêm dependency/setup riêng; không phải một class Java SE độc lập):

```java
// Fragment ý tưởng cho một benchmark JMH; cần dependencies,
// JMH annotations và build configuration đầy đủ.
@Benchmark
public int localPoint(BenchmarkState state) {
    Point p = new Point(state.value, state.value + 1);
    return p.x + p.y;
}
```

**Đây là fragment JMH**, không compile chỉ với `javac --release 17` nếu không cung cấp JMH và các declarations. Cách đo đúng:

1. Chạy warmup đủ để C1/C2 có cơ hội tối ưu hot path.
2. Dùng nhiều forks độc lập, nhiều iterations measurement.
3. Data biến đổi phù hợp, tránh benchmark bị constant-fold toàn bộ.
4. Kiểm tra profiler `gc` cho bytes/op và allocation rate normalized.
5. So với `-XX:-DoEscapeAnalysis` trên **một fork/experiment riêng**.
6. Đo p50/p99/time/op/throughput tùy mục tiêu.
7. Lặp trên cùng host, JDK vendor/build, heap/GC settings.
8. Nếu delta đáng kể, phân tích inlining/C2 compilation để hỗ trợ nguyên nhân.

Đừng đo chỉ `System.nanoTime()` trên một lần chạy. Trong ứng dụng thật, giảm allocation bytes/op có thể chưa giảm end-to-end request latency nếu bottleneck thuộc I/O hoặc locks.

## 29. Bảng chẩn đoán nhanh

| Hiện tượng | Giả thuyết hợp lý | Việc cần kiểm tra |
| --- | --- | --- |
| Temporary Point nhiều nhưng GC allocation ít | C2 có thể eliminate allocations | Warmup/JMH bytes/op, flags, inlining |
| `new` hiện trong bytecode `javap` | Bytecode giữ ngữ nghĩa allocation | Không suy machine code chắc có allocation |
| Scalar replacement không xảy ra | Object escapes hoặc compiler conservatively bails | Inlining, merges, identity, arrays, runtime build |
| Object trả từ method | Escape ở method boundary | Có caller inlining/scalarization xuyên graph hay không |
| Static field giữ Pair | Reference có thể dùng ngoài method | Đây là escape, GC vẫn phải bảo toàn object |
| Local `synchronized` không còn overhead thấy rõ | Lock elimination có thể xảy ra | JMH/compiler diagnostics và JMM semantics |
| Disable EA tăng bytes/op | EA/SRA có thể giúp workload | So cùng JDK, tiers, profiler và forks |
| JFR không thấy allocation | Có thể được optimize hoặc không được sample | Event/sampling semantics, alternative counters |
| Heap used không giảm ngay sau fix | Heap commit/GC timing khác allocation | Post-GC occupancy và GC/cgroup metrics |
| `PrintEscapeAnalysis` bị báo lỗi option | Product VM có thể không hỗ trợ debug-only flag | Dùng supported diagnostics; không ép flag |
| Method được C2 compiled nhưng vẫn allocate | NoEscape không đủ; transformation có giới hạn | JMH allocation, generated code/JIT logs |
| Workload polymorphism đổi sau warmup | Inlining/call graph và EA opportunities đổi | JFR/PrintInlining, compilation history |

## 30. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Mọi object có `new` bắt buộc nằm trên heap vật lý” | Compiler có thể loại allocation nếu Java semantics giữ nguyên |
| “Escape analysis là GC” | EA là compiler analysis; GC thu hồi heap objects đã allocated |
| “Object không thoát luôn được stack allocate” | HotSpot C2 thường **scalar-replace**, không thực hiện stack allocation object như khẳng định ấy |
| “NoEscape chắc chắn zero allocation” | Còn SRA eligibility, inlining, graph/implementation limits |
| “Trả object từ helper luôn cấm EA” | Inlining caller/callee có thể làm allocation không escape compiled graph |
| “Object truyền argument là GlobalEscape” | Callee có thể không giữ nó; ArgEscape/inlining/interprocedural analysis |
| “Static publication không liên quan escape” | Nó đưa reference tới owner ngoài scope, rất quan trọng |
| “Scalar replacement biến class thành primitive” | Nó chỉ là optimizer transformation; class vẫn giữ Java identity semantics |
| “EA xóa toàn bộ constructor” | Side effects/exceptions/initialization semantics phải bảo toàn |
| “Scalar values phải nằm trên stack” | Có thể ở registers, compiled spills/stack slots hoặc tối ưu xa hơn |
| “Identity hash code là địa chỉ object” | Không; là identity-based hash, có thể trùng cho objects khác |
| “Lock elimination cho phép xóa mọi synchronized trong source” | Shared synchronization/JMM vẫn phải đúng |
| “Debug-only PrintEscapeAnalysis luôn chạy ở JDK production” | Nhiều product builds không có flag ấy |
| “JFR không có event nên chắc không allocate” | Sampling/event thresholds có thể che allocations |
| “C2 compile chắc loại hết temporary objects” | Tùy escape graph, size, merges, calls, compiler heuristics |
| “`-XX:-DoEscapeAnalysis` chỉ đổi một `new`” | Có thể tác động nhiều optimizations/CPU/GC, benchmark cần kiểm soát |
| “Tăng `-Xmx` kích hoạt SRA” | Heap sizing không đảm bảo JIT scalar replacement |
| “Giảm allocation luôn giảm latency tỉ lệ thuận” | Throughput/latency phụ thuộc toàn workload |
| “Heap dump thiếu object X nghĩa X chắc bị scalar-replace” | Object cũng có thể đã chết/GC reclaimed hoặc không nằm trong dump |
| “Java 17 record là value type không identity” | Java 17 records vẫn là reference classes có identity |

## 31. Câu hỏi tự kiểm tra

**Câu 1:** Trong `new Point(3,4)` rồi chỉ đọc `x+y`, điều gì khiến JIT có thể xóa allocation?

**Đáp:** EA xác định object không escape và SRA đủ điều kiện biến fields thành scalar values, trong khi Java-visible semantics không đổi.

**Câu 2:** NoEscape có bắt buộc đồng nghĩa zero heap allocations không?

**Không.** NoEscape là kết quả phân tích; SRA còn có constraints và compiler/JVM runtime có thể chưa optimize.

**Câu 3:** Một method trả `Pair` ra caller. Có thể vẫn scalar-replace không?

**Có thể**, nếu JIT inline method vào caller và toàn compiled graph không cần một reference object thực sự, nhưng không được bảo đảm.

**Câu 4:** Vì sao gọi helper chưa được inline có thể làm EA khó hơn?

Compiler có thể không thấy helper có publish object hay không, nên phải phân tích bảo thủ.

**Câu 5:** Scalar replacement có phải cấp phát Point object đầy đủ trên Java stack?

**Không.** Nó có thể xóa object allocation và thay fields bằng registers/scalars; đó là khác biệt quan trọng.

**Câu 6:** Một object được lưu trong static shared field thì có thể biến mất hoàn toàn bằng SRA không?

Nếu reference có thể quan sát sau đó, compiler phải giữ object semantics; không thể đơn giản xóa object và coi assignment chưa từng xảy ra.

**Câu 7:** SRA có thể loại bỏ đồng bộ nào?

Lock elimination có thể áp dụng với private/non-escaping monitor nếu đủ điều kiện; nhưng không được xóa synchronization giữa threads đang chia sẻ object.

**Câu 8:** Vì sao deoptimization có thể cần “materialize” object?

Interpreter-compatible state có thể phải chứa logical object với fields/identity đúng, trong khi optimized code trước đó chỉ giữ scalar values.

**Câu 9:** Một `new int[3]` chắc bị xóa không?

Không. Constant indexes/small arrays có thể giúp, nhưng array indexing, aliasing, compiler limits vẫn quan trọng.

**Câu 10:** Nếu JFR không ghi event cấp phát Point, có thể khẳng định SRA hoạt động?

**Không.** Event sampling/thresholds và GC timing có thể khiến ta không thấy; cần profile/counters phù hợp.

**Câu 11:** `javap -c` còn thấy `new`, vậy HotSpot có thể đã loại allocation chưa?

**Có thể.** `javap` đọc class-file bytecode, không phải compiled machine code của C2.

**Câu 12:** Lợi ích của scalar replacement với GC là gì?

Nếu heap allocation thật sự được loại, số object/bytes cần quản lý trên heap giảm, từ đó có thể giảm allocation/GC pressure.

## 32. Nguồn chuẩn và đọc sâu

- [Oracle Java SE 17 — Java HotSpot Virtual Machine Performance Enhancements, Escape Analysis](https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html): escape states, scalar replacement, lock elimination và việc HotSpot không áp dụng stack allocation tổng quát.
- [OpenJDK — Escape Analysis and Scalar Replacement Status](https://cr.openjdk.org/~cslucas/escape-analysis/EscapeAnalysis.html): flow-insensitivity, control-flow merges, loop-carried cases, inlining/interprocedural limitations.
- [OpenJDK JDK 17 update branch — C2 Escape Analysis](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/opto/escape.cpp): implementation/connection graph; khi nghiên cứu cần chốt commit và build 17.0.x.
- [OpenJDK JDK 17 update branch — MethodData](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/oops/methodData.hpp): profiling structures phục vụ dynamic compilation decisions; thay đổi theo JDK build.
- [Microsoft Java Engineering — Improving OpenJDK Scalar Replacement](https://devblogs.microsoft.com/java/improving-openjdk-scalar-replacement-part-1-3/): inlining, C2 EA/SRA và những điểm cần cải thiện.
- [Java SE 17 — `java` command reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn VM, diagnostics, classpath, GC/heap settings.
- [Java SE 17 — `javap` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): phân biệt bytecode `new` và thực thi mã máy đã tối ưu.
- [Java SE 17 — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html) và [`com.sun.management.ThreadMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): allocation counters per thread trên implementation hỗ trợ.
- [Java SE 17 — JFR API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html): sự kiện runtime/allocation diagnostics.
- [JVMS Java SE 17 — Run-Time Data Areas](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): heap allocation semantics ở cấp specification.
- [JMH — OpenJDK Java Microbenchmark Harness](https://github.com/openjdk/jmh): công cụ benchmark tránh nhiều lỗi warmup/DCE/loop optimization.

**Kết luận:** **Escape analysis** phân tích objects có thể thoát phạm vi compiled graph/thread hay không; **scalar replacement** có thể thay object tạm bằng các **giá trị fields** và từ đó bỏ allocation thực; **lock elimination** có thể bỏ những monitors vô ích khi chứng minh an toàn. Hiệu quả phụ thuộc **C2, inlining, aliasing, control flow, identity, exceptions, compiler budgets và runtime build**. Đừng diễn giải thành “mọi `new` thành stack object”; hãy đo bằng **benchmark có warmup, bytes/op, JIT diagnostics và cùng JDK 17 configuration**.
