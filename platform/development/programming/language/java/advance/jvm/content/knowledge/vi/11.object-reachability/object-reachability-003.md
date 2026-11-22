# Vì sao gán null hoặc ra khỏi phạm vi biến không bảo đảm thu gom ngay?

## 1. Ý chính cần nắm

Trong Java, bạn có thể viết:

~~~java
Object object = new Object();
object = null;
~~~

Hoặc để một biến cục bộ ra khỏi block:

~~~java
{
    Object object = new Object();
}
// object không còn nằm trong phạm vi tên biến ở đây
~~~

Nhưng **không thao tác nào bảo đảm object vừa tạo sẽ được GC thu hồi ngay tại thời điểm đó**. Lý do gồm ba lớp khác nhau:

1. **Một biến không phải một object.** Gán `null` chỉ đổi giá trị của **một reference variable**; object có thể còn được tham chiếu từ nơi khác.
2. **Hết lexical scope không phải “sự kiện thu hồi”.** Java compiler/JIT và garbage collector phân tích **khả năng truy cập (reachability)**, không thực hiện lệnh `free` khi gặp dấu `}`.
3. **Ngay cả khi object không còn reachable, GC vẫn không bị buộc thu hồi tại một thời điểm cụ thể.** Bộ quản lý bộ nhớ tự động quyết định khi nào làm việc; trong nhiều trường hợp, chương trình có thể kết thúc trước khi object được thu gom.

Phân biệt cẩn thận:

~~~text
Gán null cho một biến / biến ra khỏi scope
                 |
                 v
Một đường tham chiếu có thể không còn sử dụng được
                 |
                 v
Có còn đường truy cập khác từ các live roots không?
        +-----------------------+
        |                       |
       CÓ                      KHÔNG
        |                       |
        v                       v
Object vẫn có thể        Object có thể trở thành
strongly reachable       không còn strongly reachable
        |                       |
        v                       v
Không đủ điều kiện        Có thể đủ điều kiện cho
thu gom theo cách         các bước xử lý reference/GC
thông thường                     |
                                 v
                         GC có thực sự chạy,
                         xử lý và thu hồi chưa?
                                 |
                        KHÔNG CÓ LỊCH CỐ ĐỊNH
~~~

Từ **“có thể đủ điều kiện” (eligible for reclamation)** tới **“đã được thu gom” (collected/reclaimed)** là một khoảng cách quan trọng. **Điều kiện được thu hồi không đồng nghĩa thao tác thu hồi đã diễn ra.**

## 2. Biến tham chiếu không phải bản thân object

Xét đoạn Java:

~~~java
final class Box {
    final int id;

    Box(int id) {
        this.id = id;
    }
}
~~~

Đây là class minh họa, chưa có `main`. Một object được tạo với:

~~~java
Box first = new Box(7);
Box second = first;
first = null;
~~~

Có thể vẽ:

~~~text
Trước khi first = null:

first  ----+
           |
           v
        Box(id=7)
           ^
           |
second ----+

Sau khi first = null:

first  ----> null

        Box(id=7)
           ^
           |
second ----+
~~~

**Object không bị xóa** chỉ vì `first` bị gán `null`. `second` vẫn giữ reference tới chính object đó, nên chương trình có thể đọc `second.id`.

Về mặt loại dữ liệu:

- `first` và `second` là các **reference variables** trong chương trình.
- `new Box(7)` tạo object theo ngữ nghĩa Java.
- Cả hai có thể mang **cùng reference value**, nên `first == second` đã từng là `true` trước khi `first` bị gán null.
- Gán `first = null` **không biến object thành null**, cũng không làm `second` tự đổi thành null.

**Lưu ý JIT:** nếu compiler thấy reference `second` không còn được sử dụng trong tương lai, liveness thực tế có thể sớm khác hình vẽ source. Nhưng khi chương trình còn thao tác quan sát được qua `second`, object phải tồn tại đúng theo ngữ nghĩa Java. Đừng dùng hình vẽ alias để dự đoán chính xác thời điểm GC sẽ chạy.

## 3. Ví dụ Java 17+: null một alias không xóa object

Tạo file **`AliasReachability.java`**:

~~~java
public class AliasReachability {
    static final class Box {
        final int id;

        Box(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Box first = new Box(7);
        Box second = first;

        System.out.println("same-before-null=" + (first == second));

        first = null;

        System.out.println("first-is-null=" + (first == null));
        System.out.println("still-readable=" + second.id);

        second = null;
        System.out.println("references-cleared");
        System.out.println("collection-is-not-guaranteed");
    }
}
~~~

Chạy bằng **JDK 17+**:

~~~bash
javac -g AliasReachability.java
java AliasReachability
~~~

**Stdout chính xác:**

~~~text
same-before-null=true
first-is-null=true
still-readable=7
references-cleared
collection-is-not-guaranteed
~~~

Điều mà chương trình **chứng minh**: sau khi `first` thành null, alias `second` vẫn truy cập `Box.id`. Hai dòng cuối là **thông điệp cố định của chương trình**, **không phải tín hiệu GC xác nhận đã hoặc chưa thu gom**.

Điều chương trình **không chứng minh**: ngay sau dòng `second = null`, garbage collector đã xử lý object. Không có phép đo GC trong ví dụ, và đặc tả không cho phép biến giả thiết “có lẽ không còn reference” thành kết luận “đã giải phóng heap”.

### Nếu một object có nhiều đường tham chiếu khác

Một reference khác có thể nằm trong:

- Trường của một object khác đang còn reachable.
- `static` field của runtime class còn được giữ theo các quy tắc reachability.
- Phần tử của array hoặc `List`/`Map`/cache.
- Biến cục bộ/cấu trúc runtime mà các thread đang thực thi còn sử dụng.
- Giá trị được closure/lambda hoặc callback giữ lại.
- Các JNI references/native-runtime handles hoặc hệ thống quản lý references khác.

Các mục trên là **những nguồn/thành phần đường truy cập thường gặp**, không phải danh sách GC roots cố định áp dụng y hệt mọi collector/JVM. Khi điều tra leak phải tìm **đường từ GC roots tới object**, thay vì chỉ thấy một biến cục bộ đã nhận `null`.

## 4. Reachability là thuộc tính của object graph, không phải số lần gọi null

Một mô hình học tập phổ biến là **object graph**:

- **Nodes**: runtime objects.
- **Edges**: references từ object tới object; cũng có references từ roots/runtime state.
- **Roots**: những điểm bắt đầu mà VM coi là sống khi xác định object nào phải giữ, tùy runtime và GC.
- **Reachable**: có đường truy cập phù hợp từ phần computation của những threads còn sống tới object.

~~~text
Sơ đồ mô hình root/heap:

GC root: active state của thread
   |
   v
CustomerService
   |
   +--> Repository ---------> Cache Map
   |                             |
   |                             +--> Customer #42
   |
   +--> Listener ---------> Customer #99

Local "temp" -------> Customer #42

temp = null:
  đường temp -> Customer #42 mất đi,
  nhưng Cache Map -> Customer #42 vẫn còn.
~~~

Object `Customer #42` **không được coi là unreachable chỉ vì reference `temp` không còn**, bởi vì cache map vẫn có thể giữ nó thông qua đường khác.

### Strong reachability và các mức khác

Tài liệu `java.lang.ref` của JDK định nghĩa những cấp độ reachability, từ mạnh đến yếu:

| Trạng thái khái niệm | Ý nghĩa |
| --- | --- |
| **Strongly reachable** | Có thể truy cập mà không phải đi qua referent của đối tượng `Reference` đặc biệt |
| **Softly reachable** | Không strongly reachable, nhưng có thể đi qua `SoftReference` |
| **Weakly reachable** | Không strongly/softly reachable, nhưng có thể đi qua `WeakReference` |
| **Phantom reachable** | Trường hợp đặc biệt dành cho `PhantomReference` và post-mortem cleanup theo API semantics |
| **Unreachable** | Không reachable qua các đường được hệ thống reference processing nhận diện; là đối tượng có thể được reclamation theo quy tắc liên quan |

**Đừng đồng nhất “không còn strong reference” với “memory đã được giải phóng”.** Khi dùng `SoftReference`/`WeakReference`/`PhantomReference`, garbage collector có thể thực hiện xử lý reference theo các quy tắc API; kết quả clearing/enqueueing và reclamation vẫn không có thời điểm do ứng dụng tùy ý đặt ra.

Một điểm tinh tế: **`PhantomReference.get()` luôn trả null**, dù referent chưa bị GC xử lý đến mức thông báo; nó không phải cách kiểm tra “object có còn sống không” bằng một phép `get()` như WeakReference.

## 5. Lexical scope: đóng dấu ngoặc không phải chạy garbage collector

Java có phạm vi tên biến theo cú pháp. Ví dụ:

~~~java
static void example() {
    {
        byte[] buffer = new byte[1024];
        System.out.println("bytes=" + buffer.length);
    }

    System.out.println("after-block");
}
~~~

Đây là **method minh họa phải nằm trong một class** để chạy. Sau block, tên `buffer` **không còn được source code truy cập hợp lệ**. Nhưng JVM không có opcode “closing brace; free the array now” tương ứng.

### Ba loại “lifetime” cần tách riêng

| Khái niệm | Bản chất | Có bảo đảm GC ngay không? |
| --- | --- | --- |
| **Lexical scope** | Phạm vi mà tên biến được dùng hợp lệ theo JLS | **Không** |
| **Runtime/JIT liveness** | VM/compiler đánh giá reference còn cần cho các phép tính tương lai hay không | **Không** |
| **Object reachability + GC decision** | Object còn đủ đường truy cập theo quy tắc hay không, rồi GC chọn lúc xử lý/reclaim | **Không** |

Lexical scope có thể kết thúc trước khi method return. Ngược lại, một biến có tên vẫn nằm trong scope nhưng **không còn được dùng tiếp**, nên compiler/JIT có thể coi giá trị reference là dead sớm hơn bạn tưởng.

### Method đã return thì object có chắc được GC?

Nếu object chỉ từng được tham chiếu bởi locals của frame đã kết thúc, các references ấy không còn là đường truy cập từ frame cũ. Nhưng vẫn có hai khả năng:

1. Object đã escape ra field/array/return value/callback/thread khác, nên còn reachable.
2. Object thực sự không còn reachable, nhưng **GC có thể chưa thực hiện reclamation**.

Vì vậy “method return rồi” **không đủ** để kết luận memory ngay lập tức được thu hồi. Thời điểm GC và quản lý heap thuộc runtime.

### `LocalVariableTable` không phải bản đồ cuối cùng của GC

Trong class file, debug `LocalVariableTable` có thể mô tả tên `buffer`, local slot, `Start` và `Length` tính theo bytecode indexes. Nó phục vụ debugger, **không phải lệnh bắt GC thu gom**.

- Compiler có thể tái sử dụng cùng một local slot cho nhiều biến không chồng phạm vi.
- JIT có thể giữ references trong registers, loại bỏ biến trung gian hoặc tối ưu code.
- GC sử dụng thông tin liveness/roots theo runtime state, không lấy dấu `}` làm tín hiệu “object chắc chắn đã chết và có thể thu ngay”.

Dùng `javap -c -l -p ClassName` để **quan sát bytecode và debug ranges**, nhưng **không suy trực tiếp từ output `-l` ra thời điểm thu gom thực tế**.

## 6. Liveness có thể kết thúc sớm hơn lexical scope

Ví dụ:

~~~java
static void process() {
    byte[] data = new byte[1024];
    int length = data.length;

    // Sau đây không sử dụng lại data.
    performOtherWork();

    System.out.println(length);
}
~~~

Đây là **minh họa**; `performOtherWork` cần được khai báo trong class chứa method. Bạn có thể nhìn source và nghĩ `data` còn sống tới hết method. Tuy nhiên nếu compiler/JIT chứng minh object không cần cho bất kỳ hành vi quan sát tiếp theo, reachability có thể chấm dứt sớm hơn “cuối method”. Đặc tả JLS `12.6.1` thừa nhận optimizing transformations có thể khiến tập reachable objects nhỏ hơn cách đọc ngây thơ từ source.

**Hướng ngược lại:** nếu `performOtherWork()` ghi `data` vào field của object khác hoặc tạo một asynchronous task giữ reference, object có thể **sống lâu hơn method**. Scope và reachability liên quan nhưng không đồng nhất.

### Escape analysis và scalar replacement

HotSpot JIT có thể nhận thấy một object không cần materialize thành một heap allocation riêng và tối ưu:

~~~java
static int sum() {
    Pair pair = new Pair(2, 3);
    return pair.left + pair.right;
}
~~~

`Pair` ở đây là **class minh họa** phải được định nghĩa trong chương trình. JIT có thể scalar-replace object thành các giá trị fields, **không cần tạo object heap vật lý** ở optimized code. Khi đó hỏi “object được GC lúc nào?” có thể không có ý nghĩa đối với một allocation đã bị tối ưu loại bỏ.

**Không khẳng định** mọi `new` đều bị loại bỏ hoặc HotSpot chuyển tất cả non-escaping objects sang stack. Đây là khả năng tối ưu, phụ thuộc code, profile, flags và compiler tier.

## 7. Eligible for GC khác GC đã chạy và khác memory đã được tái sử dụng

Ngay cả khi object không còn các đường truy cập khiến nó phải được giữ, các sự kiện sau là riêng biệt:

~~~text
T0: Ứng dụng không còn cần object
T1: Object thực tế không còn reachable theo trạng thái runtime
T2: GC thực hiện reachability/reference processing phù hợp
T3: GC reclaim/đánh dấu memory tái sử dụng, có thể compact/di chuyển
T4: Runtime cấp phát object khác và tái sử dụng vùng memory tương ứng

Không có điều kiện bắt buộc T1 == T2 == T3 == T4.
Không có deadline do source Java đặt ra từ câu lệnh = null.
~~~

Đây là sơ đồ logic. Trong garbage collectors khác nhau, các bước có thể diễn ra đồng thời/chồng lấp hoặc được tổ chức khác, không nhất thiết có đúng bốn pha vật lý tuần tự.

### Vì sao collector không thu ngay từng object?

GC là trade-off giữa throughput, latency, memory usage và overhead. Những thực tế thường gặp:

- Khi heap còn đủ dung lượng, thu gom ngay một object nhỏ có thể **không mang lại lợi ích đủ lớn**.
- GC thường thực hiện công việc theo vùng/chu kỳ, có thể concurrent hoặc stop-the-world tùy collector và giai đoạn.
- Cần xem xét những objects đang được threads sử dụng, reference graph và các yêu cầu memory barriers.
- Việc memory trở nên reusable **trong heap** không có nghĩa hệ điều hành lập tức thấy RSS/process memory giảm.
- GC có thể giữ heap committed/regions để cấp phát sau, thay vì trả ngay mọi trang memory cho OS.

Do đó “memory usage không giảm khi vừa `obj = null`” **không đủ** chứng minh Java memory leak. Cần quan sát nhiều chu kỳ GC, live-set và reference retention.

## 8. `System.gc()` không phải lời hứa thu hồi một object

Java có:

~~~java
System.gc();
Runtime.getRuntime().gc();
~~~

Đây là **các yêu cầu gợi ý VM nên dành nỗ lực để thu hồi objects không còn sử dụng**, không phải những thao tác với hậu điều kiện “mọi object unreachable lập tức biến mất”.

API `Runtime.gc()` của JDK 25 nói rõ VM **không bảo đảm** thu hồi số lượng object, dung lượng memory hoặc hoàn tất tại một thời điểm cụ thể, kể cả việc clearing/enqueueing reference objects. Ngoài ra, runtime có thể chịu ảnh hưởng của VM settings (chẳng hạn HotSpot `-XX:+DisableExplicitGC`).

**Không dùng** `System.gc()` trong vòng lặp để “bảo đảm giải phóng memory đúng từng bước” hoặc để sửa memory leak. Nó có thể làm xấu latency/throughput và không giải quyết việc các strong references vẫn giữ object reachable.

Đừng kiểm tra hành vi GC bằng:

~~~java
object = null;
System.gc();
// khẳng định: object đã bị thu gom
~~~

Kết luận cuối **không được bảo đảm**. Nếu object còn một reference khác thì vẫn không đủ điều kiện tương ứng; nếu đã unreachable thì GC vẫn không bị buộc thực hiện theo giả định thời gian của bạn.

## 9. Java 17+ runnable: ra khỏi scope không sinh “sự kiện GC”

Tạo file **`ScopeDemo.java`**:

~~~java
public class ScopeDemo {
    static final class ResourceHolder {
        final String name;

        ResourceHolder(String name) {
            this.name = name;
        }
    }

    static void work() {
        {
            ResourceHolder scoped = new ResourceHolder("temporary");
            System.out.println("inside=" + scoped.name);
        }
        System.out.println("scope-ended");
    }

    public static void main(String[] args) {
        work();
        System.out.println("method-returned");
        System.out.println("collection-timing-unspecified");
    }
}
~~~

Chạy:

~~~bash
javac -g ScopeDemo.java
java ScopeDemo
~~~

**Stdout chính xác:**

~~~text
inside=temporary
scope-ended
method-returned
collection-timing-unspecified
~~~

**Ý nghĩa:** tên `scoped` không thể được truy cập sau dấu `}` của block, `work()` rồi hoàn tất, và `main` tiếp tục. Dòng `collection-timing-unspecified` do programmer **in chủ động** để nhấn mạnh không có sự kiện GC được đo trong chương trình.

**Không suy từ output** rằng object đã được hoặc chưa được thu gom. Nếu JIT tối ưu đi, thậm chí một allocation vật lý riêng có thể không tồn tại. Mục tiêu duy nhất là phân biệt control flow, lexical scope và GC.

### Dùng `javap`

~~~bash
javap -c -l -p ScopeDemo
~~~

Bạn có thể xem:

- Bytecode tạo `ResourceHolder` và gọi constructor.
- `LineNumberTable` nếu compiler giữ thông tin line.
- `LocalVariableTable` cho `scoped` vì biên dịch bằng `-g`.

**Đừng biến `LocalVariableTable.Length` thành “số instruction rồi object chết”**. Debug scope không nhất thiết phản ánh JIT liveness hoặc thời điểm GC.

## 10. Ví dụ quan trọng: field/static/cache giữ object sau method return

Xét chương trình Java 17+ **`RetainedObjectDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RetainedObjectDemo {
    private static final List<byte[]> CACHE = new ArrayList<>();

    static void populateCache() {
        byte[] data = new byte[1024];
        CACHE.add(data);
        data = null;
    }

    public static void main(String[] args) {
        populateCache();

        System.out.println("retained=" + CACHE.size());
        System.out.println("length=" + CACHE.get(0).length);

        CACHE.clear();
        System.out.println("after-clear=" + CACHE.size());
        System.out.println("collection-still-not-guaranteed");
    }
}
~~~

Biên dịch:

~~~bash
javac -g RetainedObjectDemo.java
java RetainedObjectDemo
~~~

**Stdout chính xác:**

~~~text
retained=1
length=1024
after-clear=0
collection-still-not-guaranteed
~~~

Giải thích chi tiết:

1. `populateCache` tạo một `byte[]` trên heap theo mô hình, rồi lưu reference vào `CACHE` (một `static` field trỏ tới `ArrayList`).
2. `data = null` chỉ bỏ reference local, **không xóa phần tử trong list**.
3. Khi method kết thúc, `CACHE` vẫn giữ reference tới array, vì vậy `CACHE.get(0).length` vẫn là 1024.
4. `CACHE.clear()` bỏ phần tử; theo API `ArrayList`, list không còn giữ phần tử ấy sau thao tác thành công. Nhưng object array có được GC ngay không vẫn **không có bảo đảm**.
5. `CACHE.size() == 0` chứng minh collection không giữ phần tử ở logic API, **không phải** xác nhận object array memory đã được reclaimed.

Nếu có một alias khác tới array, dù đã `CACHE.clear()`, array vẫn có thể reachable. Cần tìm **mọi relevant roots/path** khi debug giữ bộ nhớ.

### Các chỗ giữ references lâu hơn dự kiến

Trong ứng dụng lớn, những đường giữ object thường là:

- `static Map/List` hoặc cache không có eviction policy.
- Listener/callback được đăng ký mà không unregister.
- Thread pool task/queue giữ object, `CompletableFuture` callback hoặc lambda captures.
- Một `ThreadLocal` còn giữ reference trên platform thread sống lâu.
- Session map, HTTP request context hoặc registry tồn tại lâu.
- ClassLoader/plugin framework vẫn giữ object/Class/Method hoặc context loader cũ.
- JNI global references, native handles trong tích hợp native.

Một object **không phải leak chỉ vì còn trong heap**. Leak thực dụng xảy ra khi ứng dụng giữ objects **lâu hơn ý định**, khiến live-set không ngừng tăng hoặc tài nguyên không được giải phóng. Muốn kết luận cần đối chiếu logic ownership và đo memory qua thời gian.

## 11. WeakReference: quan sát mà không giữ strong reference

`java.lang.ref.WeakReference<T>` có thể tham chiếu một object mà **bản thân weak reference không giữ object strongly reachable**. Khi GC xác định referent chỉ còn weakly reachable theo các rules, nó có thể clear weak references và enqueue chúng nếu được đăng ký với queue.

**Quan trọng:** `weak.get() == null` không phải một timer; và `weak.get() != null` tại thời điểm kiểm tra không chứng minh GC không bao giờ xảy ra. Không nên viết unit test yêu cầu weak reference phải clear trong vài mili giây.

### Ví dụ Java 17+ với output hoàn toàn xác định

Tạo file **`WeakReferenceDemo.java`**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    static final class Node {
        final int id;

        Node(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Node keeper = new Node(42);
        WeakReference<Node> weak = new WeakReference<>(keeper);

        System.out.println("id=" + keeper.id);
        System.out.println("same-while-strong="
                + (weak.get() == keeper));

        // Bảo đảm keeper còn strongly reachable tới điểm này.
        Reference.reachabilityFence(keeper);

        keeper = null;
        System.gc();

        // Không in weak.get() sau GC vì kết quả không được bảo đảm.
        System.out.println("gc-requested");
        System.out.println("weak-clear-time-unspecified");
    }
}
~~~

Chạy:

~~~bash
javac -g WeakReferenceDemo.java
java WeakReferenceDemo
~~~

**Stdout chính xác:**

~~~text
id=42
same-while-strong=true
gc-requested
weak-clear-time-unspecified
~~~

Vì `Reference.reachabilityFence(keeper)` bảo đảm referent strongly reachable ít nhất đến điểm đó, kết quả so sánh `weak.get() == keeper` trước fence là `true` trong chương trình hợp lệ. Sau `keeper = null` và `System.gc()`, code **cố ý không in kết quả `weak.get()`**: kết quả có thể thay đổi do GC/JIT/runtime và không phải contract thời gian.

### Đừng giữ strong reference vô tình

Nếu bạn kiểm tra:

~~~java
Node keeper = new Node(42);
WeakReference<Node> weak = new WeakReference<>(keeper);
List<Node> list = new ArrayList<>();
list.add(keeper);
keeper = null;
~~~

Đây là **đoạn minh họa**, thiếu imports/khung class. `list` vẫn giữ **strong reference** tới Node (nếu list còn reachable); vì thế đừng chờ `WeakReference` tự clear chỉ vì `keeper` bị gán null.

### ReferenceQueue không biến GC thành callback đồng bộ

`ReferenceQueue<T>` cho phép nhận thông báo **sau khi GC xử lý references** theo điều kiện API. Đây không phải hệ thống callback “ngay lập tức khi biến ra khỏi scope”. `queue.poll()` có thể trả `null` nếu chưa có notification, dù ứng dụng đã đặt các locals thành null.

Với `PhantomReference`, `get()` luôn trả null; cần kết hợp queue/cleanup design đúng thay vì dùng nó để đếm objects sống bằng cách thử `get()`.

## 12. `Reference.reachabilityFence` dùng khi nào?

Từ Java 9, phương thức:

~~~java
java.lang.ref.Reference.reachabilityFence(object);
~~~

**Bảo đảm object được truyền vào còn strongly reachable ít nhất tới sau lời gọi fence** bất chấp tối ưu mà JVM có thể thực hiện. Đây là cơ chế rất hữu ích cho trường hợp **đối tượng Java giữ quyền sở hữu native resource** hoặc Cleaner/finalization-like processing mà thời điểm object bị coi là unreachable có hậu quả quan sát được.

### Tình huống lý thuyết với native resource

~~~java
final class NativeHolder implements AutoCloseable {
    private final long handle;

    NativeHolder(long handle) {
        this.handle = handle;
    }

    void use() {
        nativeUse(handle);
        java.lang.ref.Reference.reachabilityFence(this);
    }

    private static native void nativeUse(long handle);

    @Override
    public void close() {
        nativeClose(handle);
    }

    private static native void nativeClose(long handle);
}
~~~

**Đây là thiết kế minh họa, không phải chương trình chạy độc lập:** hai native methods cần implementation JNI/FFM thích hợp, logic idempotent close và kiểm soát concurrency thực tế. Ý của `reachabilityFence(this)`: đừng để compiler coi wrapper Java object không còn strongly reachable **trước khi** hoàn tất native operation mà wrapper sở hữu, khi cleanup phụ thuộc reachability.

**Giới hạn rõ ràng:**

- `reachabilityFence` **không gọi GC**, **không cấp phát memory**, **không ép giữ object sống vĩnh viễn**.
- Nó không tự đồng bộ các thao tác `close`/`use` trên nhiều threads; phải thiết kế protocol về resource ownership riêng.
- Không dùng fence cho mọi object để “chữa GC lỗi”: bình thường GC đã bảo đảm các use hợp lệ của Java code.

## 13. Tài nguyên ngoài heap cần đóng theo vòng đời, không chờ GC

Có những thứ quan trọng hơn Java heap memory: file descriptors, sockets, streams, database connections, locks hoặc native handles. Việc object wrapper trở nên unreachable **không đồng nghĩa** những resource ấy đã đóng đúng lúc.

Cách Java khuyến nghị là **`try-with-resources`** với `AutoCloseable`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

public class CloseDemo {
    public static void main(String[] args) throws IOException {
        byte[] bytes = {1, 2, 3};

        try (InputStream input = new ByteArrayInputStream(bytes)) {
            System.out.println("first=" + input.read());
        }

        System.out.println("resource-scope-ended");
    }
}
~~~

Biên dịch:

~~~bash
javac CloseDemo.java
java CloseDemo
~~~

**Stdout:**

~~~text
first=1
resource-scope-ended
~~~

Ở ví dụ này, `try-with-resources` bảo đảm gọi `close()` theo ngữ nghĩa Java khi rời block, kể cả trên đường exception phù hợp. `ByteArrayInputStream` không đại diện cho một file descriptor thật, nhưng minh họa control flow mà không cần file ngoài.

**Không suy** `close()` = GC object. `close()` là resource-lifecycle operation ở Java API; object wrapper vẫn có thể còn trên heap, trong khi resource đã được đóng. Nếu cần minh họa resource OS, dùng `Files.newBufferedReader`/`FileInputStream` trong bài thực hành có file cụ thể và kiểm soát exception.

### Finalization và Cleaner có thay được try-with-resources không?

- Java finalization bị **deprecated for removal**, và theo Java SE 25 implementation có thể disable finalization. Không viết logic cần `finalize()` chắc chắn được gọi để giải phóng tài nguyên đúng lúc.
- `Cleaner` có thể hỗ trợ cleanup fallback khi object trở nên phantom reachable theo semantics, nhưng **không có deadline** đủ thay thế thao tác `close()` tường minh cho file/socket/database resources quan trọng.
- **Ưu tiên sở hữu tài nguyên rõ ràng**, đóng trong `finally`/`try-with-resources` hoặc giao thức vòng đời cụ thể.

## 14. Làm sao phân biệt memory leak với GC chưa chạy?

Nếu bạn thấy heap tăng sau một request, đừng vội gán null hàng loạt. Hãy đánh giá:

### Trình tự chẩn đoán

1. **Kiểm tra live-set:** memory sau các GC chu kỳ phù hợp có tiếp tục tăng theo tải tương đương không?
2. **Xem GC logs/metrics:** collector có chạy chưa; heap used trước/sau GC, allocation rate và pause/throughput ra sao?
3. **Dùng heap dump khi có bằng chứng retention:** tìm object dominators và reference paths từ GC roots.
4. **Tìm owner dài hạn:** static caches, maps, event listeners, task queues, ThreadLocal, long-lived services, classloader references.
5. **Chứng minh path cụ thể giữ object:** nếu bỏ một local alias mà vẫn có static map, GC không thể thu object do map còn giữ.
6. **Sửa ownership/eviction:** remove entries, unregister listeners, close resources, giới hạn cache size, bỏ references không cần thiết.
7. **Kiểm chứng sau sửa** bằng workload tái hiện, heap profiling và GC metrics tương đương.

### Ví dụ phân biệt

| Quan sát | Điều có thể kết luận | Điều chưa được phép kết luận |
| --- | --- | --- |
| `obj = null` vừa chạy | Một variable được gán null | Object đã reclaimed |
| Method chứa `obj` vừa return | Frame cũ kết thúc về mặt semantics | Không còn reference ở field/callback/other thread |
| `WeakReference.get() != null` | Tại thời điểm đó referent còn được weak.get trả về | GC chưa hề từng chạy, object sẽ luôn còn |
| `WeakReference.get() == null` | Weak ref đã bị clear hoặc do code chủ động clear | Memory chắc chắn đã trả về OS |
| Heap used không giảm ngay | Chưa quan sát giảm theo metric đó | Memory leak chắc chắn tồn tại |
| Sau nhiều GC live-set vẫn tăng | Có dấu hiệu retention cần điều tra | Chính xác class nào leak nếu chưa xem graph |
| `CACHE.clear()` | Collection không giữ entries theo API | Mọi aliases khác đã mất hoặc GC vừa chạy |
| `System.gc()` đã return | VM đã xử lý yêu cầu best-effort theo API | Mọi unreachable object đã được thu gom |

**Một heap dump lớn không tự động là memory leak**: có thể do workload/caches hợp lệ. Điều quyết định là objects không cần nữa nhưng vẫn được giữ reachable qua owners không mong muốn.

### Quan sát HotSpot

Một số tùy chọn/công cụ:

~~~bash
java -version
java -Xlog:gc* -jar app.jar
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

Đây là **mẫu** cho ứng dụng và PID thực, **không chạy nguyên xi nếu không có `app.jar`**. `jcmd` là công cụ JDK để hỏi thông tin JVM được hỗ trợ và có quyền truy cập; các commands/outputs cụ thể có thể thay đổi theo phiên bản VM, `GC.class_histogram` có thể tốn chi phí. Dùng công cụ quan sát ở môi trường test/staging trước khi tác động lên production.

Với **JFR**, bạn có thể quan sát allocation rate, GC, object count/old object sample theo cấu hình recording. **Đừng nhầm allocation rate cao** với memory leak: object có thể được tạo nhanh nhưng cũng nhanh chóng trở thành unreachable; leak nằm ở live retention.

## 15. Thời điểm ra khỏi scope và tối ưu compiler/JIT

Ví dụ:

~~~java
static void mainWork() {
    Object a = new Object();
    consume(a);

    // Trong source, a vẫn có thể được nhắc đến theo scope.
    doSomethingElse();
}
~~~

Đây là **đoạn minh họa cần khai báo `consume`, `doSomethingElse` trong class**. Nếu `consume` không giữ alias và `doSomethingElse` không còn dùng `a`, optimizer có thể kết luận `a` không cần cho tiếp tục thực thi. Ngược lại `consume` có thể giữ reference bằng cách lưu vào field, array hoặc callback, khiến object sống lâu hơn method.

**Độ sâu đặc biệt:** JLS `12.6.1` nhắc rằng reachability gắn với **potential continuing computation**. Cách xác định giá trị có còn reachable không phức tạp hơn việc “biến còn nằm trong source scope”. GC không bắt buộc đợi đến hết dấu ngoặc để xem một object đã không còn cần nữa.

### Đừng tự ép `null` để “tối ưu GC” ở mọi nơi

Với một local ngắn hạn:

~~~java
void handle() {
    byte[] data = computeData();
    process(data);
    data = null;
    continueWork();
}
~~~

Đoạn này là minh họa, cần có các methods `computeData`/`process`/`continueWork`. Assignment `data = null` có thể vô ích vì JIT đã biết reference dead sau `process`. Trên một số code và tình huống memory pressure đặc biệt, bỏ giữ reference lâu là có ý nghĩa; nhưng **bỏ tham chiếu không đồng nghĩa bắt GC chạy**, và viết null cho mọi local làm code khó đọc hơn.

Một ví dụ hiệu quả hơn thường là **xóa reference khỏi container sống lâu** ở thời điểm owner không cần nữa, hoặc chia method có phạm vi dữ liệu lớn thành những bước rõ ràng. Lợi ích thực tế cần được đo, không đoán theo source.

## 16. Phân biệt mạnh/weak/soft/phantom trong thực hành

| Cơ chế | Mục tiêu | Có giữ object strongly reachable không? | Có bảo đảm thu ngay không? |
| --- | --- | --- | --- |
| Local/field/array **strong reference** | Truy cập object thông thường | Có thể, khi đường đó còn reachable và cần thiết | Không |
| **`SoftReference<T>`** | Bộ nhớ đệm nhạy với memory pressure | Không phải strong reference | Không |
| **`WeakReference<T>`** | Mapping/cache không giữ referent bằng strong ref | Không phải strong reference | Không |
| **`PhantomReference<T>`** | Theo dõi hậu kỳ và cleanup patterns qua queue | Không phải strong reference | Không |
| **`ReferenceQueue<T>`** | Nhận notification sau reference processing | Queue không tự đảm bảo giữ mọi referent | Không |
| **`Cleaner`** | Quản lý cleanup action khi referent đạt điều kiện liên quan | Không dùng thay deadline đóng resource | Không |
| **`Reference.reachabilityFence`** | Giữ đối số strongly reachable ít nhất tới fence | Có, tới fence theo semantics | Không yêu cầu thu gom |

**Lưu ý với `WeakHashMap`:** keys là weakly referenced, nhưng nếu một **value giữ strong reference ngược tới key**, entry có thể vẫn giữ key alive gián tiếp. Thực tế thiết kế weak caching cần xem toàn bộ object graph.

Không tạo vòng chờ bận (`while (weak.get() != null) { System.gc(); }`) để đòi GC theo deadline; cách này có thể không kết thúc đúng kỳ vọng, tiêu tốn CPU và sai với semantics.

## 17. Các hiểu nhầm phổ biến

| Ngộ nhận | Điều đúng |
| --- | --- |
| “`x = null` xóa object ngay.” | Chỉ đổi **một reference variable**; các aliases khác có thể còn. |
| “Đóng dấu `}` gọi GC.” | Scope là luật tên biến, không phải instruction thu gom. |
| “Method return thì mọi objects đã tạo trong method đều chết.” | Objects có thể escape qua return, field, static collection, callback, thread khác. |
| “Một object unreachable nghĩa đã được reclaimed.” | **Eligibility khác actual reclamation**. |
| “GC là một hành động xảy ra ngay khi reference count về 0.” | Java GC không được định nghĩa là reference counting và không có deadline như vậy. |
| “Cứ gán null là heap used giảm ngay.” | GC có thể chưa chạy; heap memory có thể còn committed dù đã reusable. |
| “`System.gc()` buộc JVM thu gom mọi object không còn dùng.” | API chỉ best-effort/hint, không có bảo đảm số lượng/thời gian. |
| “Tên biến còn trong scope thì object chắc chắn sống tới cuối block.” | Optimizer có thể rút ngắn liveness nếu không còn observable use. |
| “Ra khỏi scope thì object chắc chắn unreachable.” | References khác có thể tồn tại trong graph. |
| “LocalVariableTable length cho biết GC thu lúc nào.” | Debug table không phải GC liveness timeline. |
| “Một WeakReference tồn tại sẽ giữ object mãi.” | Weak reference không giữ referent strongly reachable. |
| “WeakReference.clear ở đúng thời điểm chạy `System.gc()`.” | Reference processing không có lịch do source đặt ra. |
| “`PhantomReference.get() == null` chứng minh object đã GC.” | `get()` của PhantomReference trả null theo API. |
| “`reachabilityFence` buộc GC chạy.” | Nó chỉ đảm bảo strong reachability đến điểm fence. |
| “Cleaner/finalize luôn chạy đúng hạn để đóng file.” | Không; finalization còn bị deprecated for removal, và cleanup GC không có deadline. |
| “Memory leak chỉ xảy ra khi developer dùng native allocation.” | Java object graph có thể giữ references quá lâu qua static caches/listeners/ThreadLocal. |
| “Cứ heap tăng một lần là leak.” | Cần quan sát live-set sau GC, allocation load, owners. |
| “Đóng `AutoCloseable` đồng nghĩa wrapper object được GC.” | `close` quản lý resource lifecycle; object có thể vẫn còn reachable. |

## 18. Tự kiểm tra

**1.** `Box a = new Box(7); Box b = a; a = null;` — object có biến mất không?  
**Đáp án:** Không. `b` vẫn giữ reference tới object; `b.id` có thể đọc được.

**2.** Tại sao dấu `}` kết thúc block không đảm bảo GC?  
**Đáp án:** Nó kết thúc **lexical scope của tên biến**, không tự xóa aliases khác, không bắt GC chạy ngay.

**3.** “Eligible for GC” có bằng “GC đã reclaim memory” không?  
**Đáp án:** Không. Đủ điều kiện có thể bị thu hồi và thực sự được thu hồi là hai trạng thái/thời điểm khác nhau.

**4.** `static List<byte[]> CACHE` giữ array; local `data=null` trong method tạo array có tác dụng bỏ reference trong CACHE không?  
**Đáp án:** Không. Cần loại entry trong cache nếu owner thực sự không cần.

**5.** `System.gc()` đảm bảo mọi WeakReference được clear ngay khi return?  
**Đáp án:** Không. API không hứa rõ số reference được xử lý hoặc deadline.

**6.** Tại sao dùng `WeakReference.get()` trong một unit test rồi chờ nó thành null theo millisecond không đáng tin?  
**Đáp án:** GC timing và reference processing không được API bảo đảm theo thời gian.

**7.** Có trường hợp GC được phép coi object không còn reachable trước khi biến source ra khỏi scope không?  
**Đáp án:** Có. Optimizing compiler/JIT có thể rút ngắn liveness khi không còn use quan sát được.

**8.** `Reference.reachabilityFence(x)` cho bảo đảm nào?  
**Đáp án:** Giữ `x` strongly reachable ít nhất đến sau lời gọi, bất chấp một số tối ưu; không ép thu gom.

**9.** Đóng socket/database connection theo cách đáng tin hơn chờ GC?  
**Đáp án:** `close()` hoặc `try-with-resources` theo đúng API và vòng đời ứng dụng.

**10.** Heap memory không giảm sau một lần `null` là chứng cứ leak chắc chắn?  
**Đáp án:** Không. Cần kiểm tra GC cycles, live set và graph retention.

**11.** Tại sao `weak.get() == null` chưa cho biết heap space đã trả lại cho OS?  
**Đáp án:** Reference clearing, object reclamation, heap reuse và trả memory về OS là những cơ chế không đồng thời được bảo đảm.

**12.** Trong class dùng JIT, `new Pair()` luôn tạo heap object thật không?  
**Đáp án:** Không. Escape analysis/scalar replacement có thể loại allocation nếu vẫn giữ semantics chương trình.

## 19. Nguồn chính thức

- [JLS Java SE 25 — §12.6 Finalization of Class Instances](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.6): nền tảng về object reachability/finalization; đặc biệt **`12.6.1`** và tác động của optimizing transformations.
- [JDK 25 — `java.lang.ref` package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/package-summary.html): các loại strong/soft/weak/phantom reachability và ReferenceQueue.
- [JDK 25 — `java.lang.ref.Reference.reachabilityFence`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): giữ strong reachability tới một điểm xác định.
- [JDK 25 — `java.lang.ref.WeakReference`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/WeakReference.html): semantics clearing của weak references.
- [JDK 25 — `java.lang.ref.PhantomReference`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/PhantomReference.html): phantom reachability và `get()`.
- [JDK 25 — `Runtime.gc()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#gc()): best effort, không bảo đảm reclaim/count/timing.
- [JDK 25 — `System.gc()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#gc()): shorthand đến Runtime.gc.
- [JVMS Java SE 25 — §2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.3): class instances/arrays trong heap, GC do VM quản lý.
- [JLS Java SE 25 — §14.4 Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): biến cục bộ và phạm vi cú pháp.
- [JDK 25 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): đóng resources có quản lý vòng đời.
- [JDK 25 — `Cleaner`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/Cleaner.html): cleanup hỗ trợ khi reachability thay đổi; không có deadline bảo đảm.
- [JDK 25 — `jcmd`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): diagnostics liên quan heap/histogram và các lệnh VM được hỗ trợ.

**Kết luận:** **`= null` và hết scope chỉ tác động tới một cách giữ reference/địa chỉ tên biến; chúng không chứng minh toàn bộ đường truy cập tới object đã mất, và càng không buộc garbage collector thu hồi object ngay.** Hãy xác định object graph và ownership, phân biệt reachability với reclamation, sử dụng `AutoCloseable` để đóng tài nguyên có hạn định, và đánh giá GC bằng quan sát thực tế thay vì dựa vào dấu ngoặc hay phép gán null.