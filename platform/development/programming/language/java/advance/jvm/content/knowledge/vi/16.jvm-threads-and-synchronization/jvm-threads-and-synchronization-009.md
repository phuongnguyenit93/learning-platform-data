# Quy tắc trường final, hoàn thành khởi tạo và công bố đối tượng an toàn trong Java Memory Model

## Mục tiêu bài học

Một luồng tạo object, gán các fields trong constructor rồi đưa reference của object đó cho luồng khác. Có phải luồng đọc **chắc chắn thấy mọi field đã được gán**? Không thể trả lời chỉ bằng câu “constructor đã chạy xong”. Trong Java Memory Model (JMM), việc luồng đọc có được bảo đảm nhìn thấy các writes của luồng tạo phụ thuộc **happens-before**, hình thức **publication**, và **quy tắc đặc biệt dành cho final fields**. Nếu reference `this` lọt ra ngoài trước khi constructor kết thúc, ngay cả bảo đảm đặc biệt của `final` cũng có thể bị phá vỡ.

Bài học này tập trung vào ba câu hỏi khác nhau:

1. **Hoàn thành khởi tạo:** constructor đã thiết lập invariants và hoàn tất đúng cách trước khi object được quan sát từ thread khác hay chưa?
2. **Công bố reference:** thread khác nhận được reference bằng cơ chế nào: racy ordinary field, `volatile`, synchronized, class initialization, thread start, concurrent collection hay Future?
3. **Sử dụng sau công bố:** object có thực sự bất biến không? Nếu vẫn mutable, các writes/reads diễn ra về sau được đồng bộ hóa bằng gì?

Sau bài này, bạn có thể:

- Diễn giải chính xác §17.4 và §17.5 của **Java Language Specification**, đặc biệt `happens-before`, `synchronizes-with`, `freeze action` và khái niệm **properly constructed**.
- Phân biệt `final`, `volatile` và `synchronized`; nhận ra **final-field initialization safety khác full safe publication**.
- Tránh `this`-escape qua static field, registry, listener, callback, thread được start trong constructor hoặc overridable method.
- Hiểu vì sao `final List<T>` hoặc `final byte[]` không khiến các elements trở thành bất biến; biết dùng defensive copy và snapshot.
- Công bố một object an toàn bằng `volatile`, monitor lock, `AtomicReference`, class initialization, `Thread.start()`, `BlockingQueue`, `Future.get()` hoặc công cụ concurrent phù hợp.
- Viết đúng **double-checked locking** với `volatile`, hoặc chọn initialization-on-demand holder khi phù hợp.
- Kiểm tra code Java 17+ chạy được, phân biệt **stdout xác định** của ví dụ đã đồng bộ với **kết quả không xác định** của chương trình cố ý chứa data race.
- Sử dụng code review, stress testing và OpenJDK **jcstress** để nghiên cứu memory ordering, không dựa vào `Thread.sleep()` làm phép thử correctness.

## 1. Một object được tạo như thế nào?

Khi chạy:

~~~java
Profile p = new Profile("Lan", 20);
~~~

đây là **snippet minh họa** yêu cầu class `Profile` thích hợp. HotSpot/JVM phải thực hiện đúng Java semantics, thường liên quan:

1. Cấp phát hoặc biểu diễn object với các instance fields ban đầu có **default values** theo JLS, ví dụ `0`, `false`, `null`.
2. Thực thi các phần khởi tạo instance fields/instance initializers và constructor chain theo thứ tự Java quy định.
3. Thực thi statements trong constructor để gán các fields và thiết lập invariants.
4. Constructor hoàn thành bình thường, sau đó biểu thức `new Profile(...)` trả reference cho caller.

Ở mức implementation, JIT có thể tối ưu mạnh, chẳng hạn **escape analysis/scalar replacement** loại physical allocation trong trường hợp hợp lệ. Tuy nhiên việc tối ưu phải bảo toàn behavior JMM, kể cả bảo đảm đặc biệt của `final`.

**Hai việc không được gộp làm một:**
- Constructor **hoàn tất** trong thread A.
- Thread B **được bảo đảm thấy các writes** mà thread A đã thực hiện.

Nếu A viết reference vào ordinary shared field rồi B đọc mà không có synchronization, có thể có **data race**. Dù code trên A chạy đúng thứ tự source, Java không mặc định cung cấp một edge happens-before từ writes ở A tới reads ở B chỉ vì thời gian đồng hồ ở B đến sau.

## 2. Happens-before, program order và synchronizes-with

Theo JLS §17.4.5, nếu action X **happens-before** action Y, X được ordered/visible với Y theo JMM. Đây là quan hệ được xây dựng từ program order trong một thread và các edges **synchronizes-with**, cùng tính bắc cầu phù hợp.

Các edges thường dùng:

| Sự kiện | Bảo đảm trong JMM |
| --- | --- |
| Program order trong một thread | Action trước happens-before action sau trong cùng thread |
| Monitor `unlock` rồi `lock` kế tiếp cùng monitor | Unlock synchronizes-with subsequent lock |
| `volatile write` rồi subsequent `volatile read` cùng variable | Write synchronizes-with read theo volatile synchronization order |
| `Thread.start()` | Những actions trước start happens-before actions trong started thread |
| Thread termination được phát hiện bằng `join()` thành công | Actions trong worker happens-before actions sau join ở thread chờ |
| `java.util.concurrent` APIs | Có thêm memory consistency effects tùy class/method contract |
| Class initialization | JVM thực hiện synchronization cần thiết cho initialization safety khi class được sử dụng |

Ví dụ về volatile publication:

~~~text
THREAD A (writer)                       THREAD B (reader)

obj = new Config(...);
  constructor writes
shared = obj;                 <---      Config c = shared;
  volatile write                         volatile read
                                            |
                                            v
                                        reads c.fields

                 happens-before chain
          constructor writes -> volatile write
            -> volatile read -> field reads
~~~

Sơ đồ đòi hỏi `shared` được khai báo **volatile**, reader thực sự đọc variable đó và quan sát reference đã công bố theo đúng sequence. Không phải chỉ có keyword volatile ở một field không liên quan là mọi object/field trong chương trình đều an toàn.

### Happens-before không chỉ là “đến trước theo thời gian”

Nếu hai threads cùng truy cập một ordinary field không có ordering phù hợp, việc luồng A chạy trước theo wall-clock không tạo happens-before. OS cache coherence, CPU scheduling và những lần test in đúng giá trị **không phải bằng chứng** rằng publication đã có guarantee JMM.

Ngược lại, nếu được đồng bộ đúng, JVM/JIT và hardware có thể reorder tối ưu bên dưới nhưng **không được phá** Java-level observable guarantees.

### Data race và visibility

Ví dụ:

~~~java
final class Data {
    int a;
    int b;
}

static Data shared; // ordinary, không volatile
~~~

Đây là class/field snippets. Writer có thể chạy `shared = new Data(); shared.a=1; shared.b=2;` và reader chạy `Data d=shared; if(d!=null) print(d.a,d.b);` mà không có HB. Reader có thể nhìn thấy reference cùng các field values không như mong đợi, hoặc gặp lỗi do timing. Hơn nữa fields được ghi **sau khi published** càng không được bảo vệ bởi bất kỳ final-constructor guarantee nào.

**Không viết benchmark tự đoán một output cố định cho data race.** Một lần chạy luôn in 1,2 không chứng minh nó được bảo đảm.

## 3. final field: bảo đảm đặc biệt từ JLS §17.5

Ví dụ class:

~~~java
final class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

Nếu `Point` được **properly constructed** — đặc biệt reference tới object **không được làm visible cho thread khác trước khi constructor hoàn tất** — JMM có những bảo đảm đặc biệt cho reads của `final` fields, **ngay cả khi object reference được truyền qua một racy ordinary field**.

JLS mô tả `final` fields:
- Khởi tạo một lần theo cách thông thường, compiler được phép tối ưu reads mạnh hơn một ordinary mutable field.
- Có một **freeze action** liên quan tới final field khi constructor ghi field đó **kết thúc**.
- Thread đọc một reference tới object đã hoàn tất khởi tạo được đảm bảo nhìn thấy **giá trị đúng của final fields** theo final-field semantics.
- Với object/array được tham chiếu bởi final field, các writes được thực hiện thích hợp trước freeze có một bảo đảm nhìn thấy đặc biệt **qua đường dereference đó**.

**Đây không phải full happens-before edge tổng quát từ constructor tới mọi arbitrary field read.** JLS quy định cơ chế **dereference chain** và **memory chain** dành cho final fields; HB đặc biệt được dùng trong một phép xác định giá trị nhất định, không được áp tính bắc cầu tùy tiện như một synchronization edge toàn cục.

### Minh họa mẫu trong JLS

~~~java
final class Example {
    final int finalized;
    int ordinary;

    Example() {
        finalized = 42;
        ordinary = 17;
    }
}
~~~

Nếu hoàn tất constructor, rồi reference được công bố **racy**:

~~~java
static Example shared; // ordinary field, ví dụ minh họa
// writer:
shared = new Example();
// reader ở thread khác:
Example e = shared;
if (e != null) {
    int a = e.finalized;
    int b = e.ordinary;
}
~~~

**Diễn giải thận trọng:**
- Nếu reader đã thấy reference tới instance được khởi tạo đúng cách, final-field semantics bảo đảm `a == 42`.
- Không có một ordinary HB từ writer sang reader, nên **không có bảo đảm tương đương cho `b`**; có thể quan sát default `0` hoặc `17` trong những execution phù hợp JMM.
- Không có guarantee reader sẽ **sớm hoặc luôn thấy `shared != null`**, vì reference truyền qua data race.
- Nếu constructor có `this`-escape trước khi gán `finalized`, không được sử dụng kết luận trên.

**Khuyến nghị kỹ thuật:** dù `final` có initialization safety đặc biệt, **hãy dùng safe publication cho toàn bộ object** để readers có happens-before rõ ràng, thay vì cố tình dựa vào racy publication.

## 4. Freeze action là gì? Không phải đóng băng toàn bộ heap

Một mô hình:

~~~text
Thread A tạo Object O

ALLOCATE O (default fields)
        |
        v
constructor:
    write final x = 42
    write ordinary y = 17
        |
        v
constructor exit  ---> FREEZE of final x
        |
        v
O được đưa tới nơi thread khác có thể thấy
        |
        v
Thread B đọc O.x qua reference phù hợp
    -> final field được bảo vệ bởi JMM 17.5
~~~

**Freeze là khái niệm của Java Memory Model**, không phải gọi một public API hoặc buộc HotSpot khóa mọi CPU cache lines. JLS 17.5.1 quy định freeze khi constructor có write tới final field kết thúc (kể cả các chi tiết constructor delegation; specification còn xét trường hợp abrupt completion). Đừng tự khái quát freeze thành “mọi fields trở thành volatile”.

### Nếu constructor gọi constructor khác

~~~java
final class Pair {
    final int a;
    final int b;

    Pair(int a) {
        this(a, 0);
    }

    Pair(int a, int b) {
        this.a = a;
        this.b = b;
    }
}
~~~

Constructor delegation với `this(...)` có quy tắc freeze gắn với constructor thực hiện writes. Khi thiết kế class, vẫn cần **không để `this` escape trong toàn bộ construction path**, bởi một thread khác có thể thấy object trước khi initialization toàn bộ hierarchy hoàn tất.

### final field được gán ở declaration có khác không?

~~~java
final class Status {
    final int code = 200;

    Status() {
        // Có thể thực hiện thêm khởi tạo.
    }
}
~~~

Đây là **instance final constant-variable-like expression** nhưng điều quan trọng của bài là final field initialization semantics khi object được constructed properly. Compiler có thể inline literal rất sớm; không dùng `Status.code==200` trong mọi test để kết luận publication an toàn cho những mutable fields khác.

### final fields bị sửa qua reflection/Unsafe

JLS §17.5.3 có các tình huống đặc biệt của deserialization/reflection, nhưng code ứng dụng bình thường **không được dựa vào việc thay đổi final field sau construction**. Những thay đổi đó có thể có visibility/optimization surprises; strong encapsulation, records và các JDK mới tiếp tục hạn chế deep reflection hoặc unsafe mutation.

Tư duy an toàn: coi final fields như **chỉ được thiết lập trong constructor/instance initializer**; không dùng reflection để đổi chúng sau publication.

## 5. Properly constructed: vì sao `this` không được escape?

Một object có thể lọt ra khỏi constructor thông qua:
- Gán `this` vào static/shared field.
- Đăng ký `this` làm listener/callback ở registry bên ngoài, nơi thread khác có thể chạy callback tức thì.
- Start một thread trong constructor rồi Runnable capture `this`.
- Submit task cho executor trong constructor, task tham chiếu tới fields của object đang tạo.
- Đưa `this` vào một concurrent collection trước khi constructor hoàn tất.
- Gọi overridable instance method từ constructor, subclass override publish object hoặc đọc fields chưa khởi tạo.
- Gọi method của bên thứ ba và truyền `this` khi không kiểm soát việc method ấy làm gì.

### Anti-pattern: đăng ký sớm

~~~java
final class UnsafeListener {
    final int id;

    UnsafeListener(Registry registry) {
        registry.register(this); // this có thể bị thread khác thấy
        id = 42;
    }
}
~~~

Đây là **snippet minh họa**, cần định nghĩa `Registry` phù hợp. Nếu registry làm object visible trước khi `id=42`, thread khác có thể đọc `id=0` (default value) trong một lịch chạy, và final-field initialization guarantee cho instance này **không còn được áp dụng như properly constructed object**.

Một registry dùng `volatile`, `ConcurrentHashMap` hoặc `synchronized` **không cứu được** việc object được công bố **trước khi fields được gán**. Safe publication có thể công bố một object **chưa hoàn tất construction** một cách rõ ràng và hợp lệ về ordering, nhưng kết quả vẫn thiếu dữ liệu nếu publish quá sớm.

### Anti-pattern: gọi overridable method trong constructor

~~~java
class Base {
    Base() {
        initialize(); // dynamic dispatch có thể gọi subclass
    }

    void initialize() { }
}

class Child extends Base {
    final int value = 42;

    @Override
    void initialize() {
        // value có thể chưa được khởi tạo khi Base() gọi.
        System.out.println(value);
    }
}
~~~

Đây là **hai class fragments**. Điểm quan trọng: trong Java, dynamic dispatch xảy ra ngay cả khi đang thực thi base constructor, khi subclass field initializers chưa hoàn tất. Ngoài nguy cơ publish `this`, đây còn là nguồn quan sát **partially initialized subclass state**.

Với final constant initialized bằng compile-time literal, compiler có thể inline giá trị, làm ví dụ in ra không phản ánh rõ vấn đề. Để chứng minh tình huống thực tế, dùng subclass instance field không phải compile-time constant và tổ chức code cẩn thận; đừng hứa output của fragment trên.

### Cách sửa: factory đăng ký sau khi constructor hoàn tất

~~~java
final class Listener {
    final int id;

    private Listener(int id) {
        this.id = id;
    }

    static Listener createAndRegister(Registry registry, int id) {
        Listener listener = new Listener(id);
        registry.register(listener);
        return listener;
    }
}
~~~

Đây là code snippet cần `Registry`. Khi `new Listener(id)` trả về, constructor hoàn tất trước khi gọi `register`. Vẫn cần registry có **publication semantics phù hợp** cho các readers khác, và không sửa mutable state thiếu đồng bộ sau đó.

## 6. final reference khác deep immutability

Xét:

~~~java
final class Bag {
    final int[] values;

    Bag() {
        values = new int[] {4, 5};
    }
}
~~~

Điều `final` ngăn cấm theo Java language bình thường là **gán lại reference field**:

~~~java
// bag.values = new int[] {1, 2};  // compile-time error
bag.values[0] = 99;               // hợp lệ
~~~

Đây là snippets, cần biến `bag` phù hợp.

Sơ đồ:

~~~text
[Bag object]
    final values -------+
                        |
                        v
                    [int array]
                    [4][5]
                        |
                    element 0 mutable

FINAL: reference field không gán lại theo Java source
NOT FINAL: các array elements là dữ liệu mutable
~~~

### Bảo đảm khi arrays được khởi tạo trước freeze

JLS §17.5 giải thích rằng với một array/object được tham chiếu qua final field, những writes phù hợp đã xảy ra **trước freeze** có visibility guarantee đặc biệt khi thread khác dereference qua final field đó. Vì vậy nếu constructor tạo array, điền element trước khi kết thúc, reader đọc qua final reference có thể được bảo vệ cho trạng thái khởi tạo ban đầu.

Nhưng **sau khi object đã published**, nếu một thread sửa `values[0]` mà thread khác đọc không synchronization, đó vẫn có thể là **data race trên array element**. Bảo đảm của final reference không biến mọi lần mutate tương lai thành volatile writes.

Cũng không thể tùy tiện suy “mọi object reachable nhiều cấp đều tự động immutable” từ một final reference. Với nested mutable graphs và aliases bên ngoài, cần xem chính xác các writes/read paths và ownership.

### Defensive copying

Nếu class cần immutable snapshot của một mảng do caller cung cấp:

~~~java
final class ByteMessage {
    private final byte[] payload;

    ByteMessage(byte[] incoming) {
        this.payload = incoming.clone();
    }

    byte[] payload() {
        return payload.clone();
    }
}
~~~

Nếu không clone ở constructor, caller còn giữ `incoming` và có thể sửa array sau khi gửi vào object. Nếu trả raw `payload` trong getter, caller có thể sửa state nội bộ. **Clone cả vào và ra** giúp tránh aliasing ở cấp một mảng primitive. Với nested arrays hoặc mutable element objects, cần deep copy hoặc thiết kế ownership/immutability phù hợp.

**`List.copyOf`, `Map.copyOf` và `Collections.unmodifiableList` không tự deep-copy các objects mutable bên trong.** Immutable container không đồng nghĩa immutable element graph.

## 7. Ví dụ Java 17+ chạy độc lập: immutable snapshot và defensive copy

Tạo file **`ImmutableSnapshotDemo.java`**:

~~~java
import java.util.Arrays;

public class ImmutableSnapshotDemo {
    static final class Message {
        private final String id;
        private final byte[] payload;

        Message(String id, byte[] source) {
            this.id = id;
            this.payload = source.clone();
        }

        String id() {
            return id;
        }

        byte[] payload() {
            return payload.clone();
        }

        int firstByte() {
            return Byte.toUnsignedInt(payload[0]);
        }
    }

    public static void main(String[] args) {
        byte[] input = {1, 2, 3};
        Message message = new Message("m1", input);

        input[0] = 9;
        byte[] externalCopy = message.payload();
        externalCopy[1] = 8;

        System.out.println("id=" + message.id());
        System.out.println("first=" + message.firstByte());
        System.out.println("snapshot=" +
                Arrays.toString(message.payload()));
        System.out.println("input=" + Arrays.toString(input));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 ImmutableSnapshotDemo.java
java ImmutableSnapshotDemo
~~~

**Stdout chính xác:**

~~~text
id=m1
first=1
snapshot=[1, 2, 3]
input=[9, 2, 3]
~~~

Giải thích:
1. `Message` có final reference fields và không để `this` escape.
2. `payload` được clone trong constructor, nên caller sửa `input[0]` không tác động snapshot.
3. Getter trả clone mới, nên caller sửa `externalCopy[1]` không tác động internal array.
4. Không có writes tới internal array sau construction, nên đây là một object có **effective immutability** ở biên API nêu trên.
5. Code chỉ chứng minh copy/encapsulation semantics; nó **không kích hoạt hoặc quan sát một freeze event** trực tiếp. Freeze là mô hình JMM do JVM triển khai.

Nếu dữ liệu là `List<MutableUser>`, sao chép danh sách references không tự snapshot từng mutable user. Cần thiết kế immutable element type hoặc deep-copy theo nhu cầu.

## 8. final field visibility không bằng safe publication

Bảng so sánh:

| Tình huống | final fields của object properly constructed | ordinary fields khởi tạo trước công bố | updates sau công bố |
| --- | --- | --- | --- |
| Reference qua **ordinary field, data race** | Có **final-field guarantee** khi reader thấy object đúng | Không có full happens-before guarantee chỉ nhờ final | Không có guarantee nếu tiếp tục racy |
| Reference qua **volatile field** | Được bảo đảm nếu properly constructed | Writes trước volatile publish được ordered tới subsequent volatile read | Cần synchronization cho những updates sau publish |
| Reference dưới **cùng monitor lock** | Được bảo đảm | Writes trước unlock được ordered tới lock/read sau | Phải bảo vệ mutable access đúng lock/discipline |
| Reference trong **class initialized safely** | Được bảo đảm | Initialization visibility theo class init | Mutable fields sau đó vẫn cần đồng bộ |
| Reference qua **BlockingQueue/Future** đúng contract | Được bảo đảm | Handoff memory consistency theo API | Hậu công bố vẫn có thể có races nếu mutate |
| Reference qua **Thread.start()** trước worker actions | Được bảo đảm | Actions trước start HB worker actions | Những concurrent writes sau start không tự HB |
| Reference thoát **trước constructor exit** | Không có normally constructed guarantee | Có nguy cơ thấy partial state | Tiếp tục cần đồng bộ |

**Quan trọng:** bên ngoài mệnh đề “reader thấy object/reference”, racy publication có thể còn gặp visibility/liveness issues trên **chính reference**. Final-field semantics không khiến publisher phải công bố reference kịp thời hoặc cho mọi reader eventually thấy non-null.

### Các câu hỏi review hữu ích

1. Constructor hoàn tất lúc nào? Object có bị registry/callback nhìn thấy trước đó không?
2. Reference nằm ở ordinary field, volatile field hay concurrent container?
3. Reader đọc reference qua đường nào, có cùng synchronization protocol?
4. Fields nào final; fields nào mutable; elements/referents nào mutable?
5. Có writes sau khi publish không? Cơ chế bảo vệ từng write/read là gì?
6. Getter có trả alias tới internal mutable graph không?
7. Có subclass override/callback từ constructor không?
8. Có dependency là native/reflection/serialization framework sửa final fields không?

## 9. Safe publication bằng volatile

Ví dụ một snapshot object gồm cả final và ordinary fields, với một biến reference **volatile**:

~~~java
final class Settings {
    final String region;
    int timeoutMs;

    Settings(String region, int timeoutMs) {
        this.region = region;
        this.timeoutMs = timeoutMs;
    }
}

static volatile Settings current;
~~~

Đây là class/field snippets, `current` cần được khai báo trong một class hợp lệ.

Writer:

~~~java
current = new Settings("ap-southeast", 300);
~~~

Reader:

~~~java
Settings snapshot = current;
if (snapshot != null) {
    use(snapshot.region, snapshot.timeoutMs);
}
~~~

Các đoạn trên là snippets; method `use` chỉ minh họa. Nếu reader quan sát reference đã được published qua **volatile read**, toàn bộ constructor writes trước volatile write có HB tới những reads sau đó. Do đó `timeoutMs` ordinary field cũng có visibility guarantee **cho giá trị được ghi trước publication**.

**Nhưng:** nếu sau đó thread writer chạy `current.timeoutMs = 500;` mà reader tiếp tục đọc `timeoutMs` không synchronization, volatile nature của **reference field `current`** không tự làm `timeoutMs` trở thành volatile. Thay vì mutate snapshot, có thể publish **một immutable object mới** qua cùng volatile reference.

### Read volatile đúng lần khi cần nhất quán snapshot

~~~java
Settings snapshot = current;
if (snapshot != null) {
    // dùng tất cả fields từ cùng snapshot
}
~~~

Dùng local `snapshot` để đảm bảo cùng một instance xuyên các reads logic. Nếu đọc `current` nhiều lần giữa chừng và thread khác thay reference, code có thể lấy region từ instance A và timeout từ instance B, gây một “mixed configuration”, dù từng volatile read riêng lẻ hợp lệ.

## 10. Ví dụ Java 17+ chạy độc lập: publish immutable snapshot bằng volatile

Tạo file **`VolatilePublicationDemo.java`**:

~~~java
public class VolatilePublicationDemo {
    static final class Config {
        final String label;
        final int port;

        Config(String label, int port) {
            this.label = label;
            this.port = port;
        }
    }

    private static volatile Config published;

    public static void main(String[] args)
            throws InterruptedException {
        Thread writer = new Thread(() -> {
            Config next = new Config("READY", 8080);
            published = next; // volatile publication
        });

        writer.start();
        writer.join();

        Thread reader = new Thread(() -> {
            Config snapshot = published; // volatile read
            System.out.println("label=" + snapshot.label);
            System.out.println("port=" + snapshot.port);
        });

        reader.start();
        reader.join();
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac --release 17 VolatilePublicationDemo.java
java VolatilePublicationDemo
~~~

**Stdout chính xác:**

~~~text
label=READY
port=8080
~~~

Trong ví dụ này:
- Writer tạo và hoàn tất `Config` trước khi gán volatile `published`.
- `writer.join()` cũng tạo một HB path tới main, làm ví dụ **deterministic**; reader được start sau join nên đảm bảo sẽ thấy object. **Đây không phải benchmark chỉ riêng cơ chế volatile** vì có thêm HB từ join/start.
- Volatile ở `published` cung cấp một cơ chế publication rõ ràng nếu mở rộng sang thiết kế writer/reader chạy đồng thời và đọc đúng volatile variable.
- `Config` có final fields; trong code này cả final guarantee lẫn safe publication đều được duy trì.

Đừng xóa `join()` rồi viết một reader có một phép đọc duy nhất và đoán nó chắc chắn thấy non-null ngay. Một reader có thể chạy trước khi writer publish. **Ordering/visibility** không tự đồng nghĩa **scheduling/arrival time**.

## 11. Safe publication bằng synchronized monitor

Writer:

~~~java
synchronized (lock) {
    shared = new Settings("ap-southeast", 300);
}
~~~

Reader:

~~~java
Settings copy;
synchronized (lock) {
    copy = shared;
}
~~~

Đây là snippets, cần `lock` và `shared` trong class hợp lệ. Nếu writer **unlock monitor** sau assignment và reader **subsequently lock chính monitor đó**, JMM thiết lập synchronizes-with edge. Các writes trong constructor trước publication có thể được quan sát qua HB tại reader.

Hai lỗi thường gặp:
- Writer lock object A, reader lock object B: **không có cùng monitor** nên không nhận được edge mong muốn.
- Writer dùng synchronized, reader đọc `shared` trực tiếp ngoài lock: reader có thể **không** hưởng visibility guarantee từ monitor protocol.

### synchronized không chỉ là mutual exclusion

Nó cung cấp **atomicity** cho critical section theo mutual exclusion và **visibility/ordering** khi lock/unlock đúng cặp monitor. Tuy nhiên nó không tự giải quyết object escaping từ constructor hoặc việc trả raw aliases tới mutable array sau khi lock được thả.

## 12. Safe publication qua class initialization

Initialization-on-demand holder là một idiom đơn giản:

~~~java
final class Service {
    final int id;

    private Service(int id) {
        this.id = id;
    }

    private static final class Holder {
        static final Service INSTANCE = new Service(42);
    }

    static Service instance() {
        return Holder.INSTANCE;
    }
}
~~~

JVM phối hợp class initialization theo JLS §12.4.2, do đó instance được tạo trong static initializer và công bố thông qua Holder có initialization visibility đúng cho những threads sử dụng class. Không cần tự viết `volatile` hoặc `synchronized` trong accessor mỗi lần.

### Eager static final

~~~java
final class Constants {
    static final Service INSTANCE = new Service(42);
}
~~~

Tạo object từ static field initializer cũng hưởng cơ chế class initialization tương ứng. Phải phân biệt **static final reference** với **JLS constant variable**: `Service` là reference type, không thể trở thành compile-time constant variable như một `static final int ANSWER=42`.

### Enum singleton

~~~java
enum GlobalService {
    INSTANCE;
}
~~~

Enum initialization cũng được JVM quản lý và thường hữu ích để tạo singleton an toàn với built-in serialization semantics. Nhưng nếu enum singleton giữ mutable fields, các operations trên fields vẫn phải thread-safe.

## 13. Ví dụ Java 17+ chạy độc lập: holder singleton và thread join

Tạo file **`HolderPublicationDemo.java`**:

~~~java
public class HolderPublicationDemo {
    static final class Service {
        final int id;
        final String name;

        private Service() {
            id = 42;
            name = "single";
        }
    }

    static final class Holder {
        static final Service INSTANCE = new Service();
    }

    public static void main(String[] args)
            throws InterruptedException {
        Service[] observed = new Service[4];
        Thread[] workers = new Thread[observed.length];

        for (int i = 0; i < observed.length; i++) {
            final int index = i;
            workers[i] = new Thread(
                    () -> observed[index] = Holder.INSTANCE);
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        boolean same = true;
        for (Service service : observed) {
            same &= service == observed[0];
        }

        System.out.println("same=" + same);
        System.out.println("id=" + observed[0].id);
        System.out.println("name=" + observed[0].name);
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 HolderPublicationDemo.java
java HolderPublicationDemo
~~~

**Stdout chính xác:**

~~~text
same=true
id=42
name=single
~~~

Các threads có thể đụng `Holder.INSTANCE` cùng lúc, nhưng JVM chỉ thực hiện class initialization phù hợp **một lần** cho một class loader/class instance. `join()` làm main chờ và cung cấp HB để đọc các phần tử của array `observed`. Code này không đo thô chi phí synchronization; nó minh họa một cách publication **không cần tự viết double-checked locking**.

## 14. Double-checked locking: vì sao cần volatile?

**Double-checked locking (DCL)** nhằm giảm overhead synchronized sau khi singleton đã được tạo:

~~~java
final class LazyService {
    private static volatile LazyService instance;

    static LazyService get() {
        LazyService result = instance;
        if (result == null) {
            synchronized (LazyService.class) {
                result = instance;
                if (result == null) {
                    result = new LazyService();
                    instance = result;
                }
            }
        }
        return result;
    }
}
~~~

Đây là class snippet. Cần khai báo constructor phù hợp.

**Vì sao có hai checks?**
- Check ngoài giảm việc vào monitor khi instance đã có.
- Check trong bảo đảm sau khi acquire lock, nếu thread khác đã tạo singleton thì không tạo lần hai.

**Vì sao `volatile` quan trọng?**
- Một thread có thể quan sát reference ngoài synchronized block.
- Without volatile hoặc một publication mechanism tương đương, reference read/write ở ngoài lock có data race và không bảo đảm visibility thích hợp cho toàn bộ constructor writes.
- Volatile publication tạo ordering/visibility: readers nhìn thấy reference sau publication sẽ nhìn thấy trạng thái khởi tạo trước đó.
- Một `final` field trong singleton **không tự biến ordinary fields hay mutable graph của singleton thành safely published**, và không biến toàn bộ DCL không volatile thành một idiom nên dùng.

### Cách đọc tránh race giữa hai volatile reads

Dùng local `result` để đọc volatile một lần trên mỗi check level; cũng phù hợp khi value được thay đổi trong những patterns khác. Với singleton chỉ khởi tạo một lần, mục tiêu chính là correct publication và avoiding unnecessary reads.

### Không cần DCL mọi nơi

Nếu singleton không cần lazy creation, dùng static final field. Nếu muốn lazy nhưng ít phức tạp, dùng **initialization-on-demand holder**. DCL hữu ích khi cần lazy initialization với lifecycle/constructor args hoặc logic đặc biệt nhưng tăng chi phí review.

## 15. Ví dụ Java 17+ chạy độc lập: DCL singleton đúng

Tạo file **`DclSingletonDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class DclSingletonDemo {
    static final class Service {
        private static final AtomicInteger CREATED =
                new AtomicInteger();
        private static volatile Service instance;

        final int value;
        final String label;

        private Service() {
            value = 42;
            label = "ready";
            CREATED.incrementAndGet();
        }

        static Service get() {
            Service result = instance;
            if (result == null) {
                synchronized (Service.class) {
                    result = instance;
                    if (result == null) {
                        result = new Service();
                        instance = result;
                    }
                }
            }
            return result;
        }

        static int creationCount() {
            return CREATED.get();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Service[] results = new Service[8];
        Thread[] threads = new Thread[results.length];

        for (int i = 0; i < threads.length; i++) {
            final int index = i;
            threads[i] = new Thread(
                    () -> results[index] = Service.get());
            threads[i].start();
        }

        for (Thread thread : threads) {
            thread.join();
        }

        boolean allSame = true;
        for (Service result : results) {
            allSame &= result == results[0];
        }

        System.out.println("same=" + allSame);
        System.out.println("created=" + Service.creationCount());
        System.out.println("value=" + results[0].value);
        System.out.println("label=" + results[0].label);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 DclSingletonDemo.java
java DclSingletonDemo
~~~

**Stdout chính xác:**

~~~text
same=true
created=1
value=42
label=ready
~~~

Lý do đúng:
- Chỉ một thread có thể tạo instance trong critical section nếu result vẫn null.
- `volatile instance` cung cấp release/acquire semantics cho publication và lock-free read path.
- Các fields final được thiết lập trước khi constructor trả về.
- `AtomicInteger` đếm một lần constructor invocation trong ví dụ hợp lệ, nhưng **không phải điều kiện cần** cho DCL; nó chỉ phục vụ trình diễn.
- `join()` giúp main đọc các phần tử results đã được threads gán.

**Không được bỏ `volatile` rồi lấy output trên một máy làm chứng minh DCL vẫn đúng.** Failure có thể hiếm trên phần cứng/test cụ thể mà JMM vẫn không hứa correctness.

## 16. Safe handoff qua Thread.start và Thread.join

Khởi tạo object trên main rồi start worker là một handoff JMM hợp lệ:

~~~java
final class WorkData {
    int ordinary;
    final int fixed;

    WorkData() {
        ordinary = 17;
        fixed = 42;
    }
}
~~~

Trong main:

~~~java
WorkData data = new WorkData();
Thread worker = new Thread(() -> {
    System.out.println(data.ordinary);
    System.out.println(data.fixed);
});
worker.start();
worker.join();
~~~

Đây là **hai snippets minh họa**, cần bọc trong class/method, checked exception `InterruptedException`. Actions trước `start()` happen-before actions của worker. Vì vậy trong tình huống này **cả ordinary và final fields** được initialized visible tới worker; không cần thêm volatile chỉ để pass reference trước start.

Nhưng nếu main mutate `data.ordinary` **sau khi start** đồng thời với worker read, thread-start HB không tự order write mới đó. Cần synchronization thích hợp.

### Thread.join trả kết quả theo hướng ngược

Worker writes trước termination happen-before main actions sau `join()` thành công. Đây là lý do các ví dụ multi-thread có thể thu kết quả vào các slots khác nhau và chỉ print từ main sau khi joins.

**Cả platform threads và virtual threads** (JDK 21+) đều tuân những Java Memory Model rules tương ứng; carrier mapping không thay đổi final-field semantics.

## 17. Handoff qua BlockingQueue, Future và concurrent collections

Một số Java concurrency APIs quy định memory consistency effects rõ ràng.

### BlockingQueue

Writer tạo và hoàn tất immutable message rồi `put(message)` vào `BlockingQueue<Message>`. Reader `take()` cùng queue để nhận message. Các actions trước việc đặt object vào queue happen-before actions sau khi thread khác truy cập/loại nó qua queue theo API memory consistency properties.

~~~text
Producer                        Consumer
  new Message(...)
  fields initialized
        |
  queue.put(message) ----------> queue.take()
                                     |
                               message fields read
~~~

Đây là mô hình **safe handoff**, miễn rằng producer không mutate shared mutable payload thiếu đồng bộ sau khi put.

### ConcurrentHashMap

Dùng `ConcurrentHashMap` để đưa **fully initialized objects** vào map, và reader dùng retrieval tương ứng theo API. Memory visibility guarantee của map không khiến object đã publish ở constructor trước khi init hoàn tất “hoàn chỉnh trở lại”.

### Future / ExecutorService

Các actions trước task submission happen-before task execution theo `ExecutorService` contract; task actions happen-before **result được lấy qua `Future.get()`** theo package/API memory consistency rules.

**Đừng nhầm** “nộp task vào executor” với “task đã hoàn tất”. Reader cần `Future.get()`, join, latch hoặc cơ chế tương ứng để chờ kết quả và ordering phù hợp.

### AtomicReference

Một `AtomicReference<T>` dùng `set`/`get` cung cấp visibility semantics tương tự volatile reference cho thao tác tương ứng. Nhưng tham chiếu atomic không biến toàn bộ state của T thành immutable hoặc mọi field access thành atomic transaction.

## 18. Ví dụ Java 17+ chạy độc lập: safe publication bằng BlockingQueue

Tạo file **`QueuePublicationDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueuePublicationDemo {
    static final class Payload {
        final String name;
        final int code;

        Payload(String name, int code) {
            this.name = name;
            this.code = code;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        BlockingQueue<Payload> queue =
                new ArrayBlockingQueue<>(1);

        Thread producer = new Thread(() -> {
            Payload payload = new Payload("TASK", 27);
            try {
                queue.put(payload);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        producer.start();

        Payload received = queue.take();
        producer.join();

        System.out.println("name=" + received.name);
        System.out.println("code=" + received.code);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 QueuePublicationDemo.java
java QueuePublicationDemo
~~~

**Stdout chính xác khi chương trình hoàn tất bình thường:**

~~~text
name=TASK
code=27
~~~

Constructor kết thúc trước khi producer enqueue. Queue đảm bảo safe handoff tới consumer. `producer.join()` chỉ chờ thread kết thúc để lifecycle rõ ràng; visibility giữa put/take đã được API đảm bảo. Nếu producer bị interrupt trước khi put, ví dụ sẽ chờ trên `take()`; chương trình đơn giản này không có timeout/cancellation policy riêng, vì vậy production code nên thiết kế timeout hoặc một result/error channel phù hợp.

## 19. final reference không làm mutable data thread-safe

Ví dụ:

~~~java
final class Stats {
    final int[] counts = new int[1];

    void increment() {
        counts[0]++;
    }

    int read() {
        return counts[0];
    }
}
~~~

`counts` luôn tham chiếu cùng array, nhưng `counts[0]++` là một read-modify-write không atomic. Hai threads cùng gọi `increment()` có thể mất cập nhật. `final` **không** bảo đảm các element reads/writes có visibility/happens-before mới sau initialization.

Có thể sửa bằng:

~~~java
final class StatsSafe {
    private final java.util.concurrent.atomic.AtomicInteger count =
            new java.util.concurrent.atomic.AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int read() {
        return count.get();
    }
}
~~~

Đây là snippet class hoàn chỉnh với fully qualified class name. AtomicInteger có operations thread-safe theo contract. Field reference `count` là final để reference không bị gán lại sau constructor, còn **atomic state** của chính AtomicInteger được đồng bộ theo API.

Một alternative là `synchronized` ở cả `increment()` và `read()`; hoặc thiết kế immutable snapshots publish lại mỗi update qua `volatile`/AtomicReference.

### AtomicReference không làm nhiều field updates thành atomic snapshot

Nếu một object có `name` và `timeout` mutable, viết hai fields rồi để readers đọc qua một AtomicReference không tự tạo atomicity xuyên hai field assignments. Tốt hơn tạo **một immutable Config mới** chứa cả hai giá trị rồi đổi reference bằng một atomic/volatile store. Reader lấy **một snapshot** rồi sử dụng cả hai fields của nó.

## 20. Records và immutable classes

JDK 17 hỗ trợ records ổn định. Record components tương ứng private final fields, đem lại cú pháp ngắn cho những value aggregates.

~~~java
record Endpoint(String host, int port) { }
~~~

Nếu `host` là immutable String và `port` là primitive, record này là một value carrier dễ dùng theo style immutable. Nhưng một record có component `byte[]` **không deep immutable**:

~~~java
record Packet(byte[] bytes) { }
~~~

Caller có thể sửa array được đưa vào canonical constructor hoặc array getter trả về. Record compiler tạo final reference field, **không tự clone** array.

### Record với defensive copy

~~~java
record Packet(byte[] bytes) {
    Packet {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Đây là **đoạn record snippet**, có thể biên dịch trên Java 17+ khi đặt đúng file/package. Compact canonical constructor cho phép chuẩn hóa parameter trước khi tự động gán component field; clone ở accessor ngăn trả alias. Đối với nested mutable graphs, phải thiết kế deep copying hoặc immutable elements.

### Immutable là một contract thiết kế

Một class có `final int x` nhưng getter tùy tiện trao raw references tới mutable internal state không tự thành immutable class. An toàn với nhiều threads đòi hỏi **không có mutation quan sát được sau khi constructed** hoặc phải đồng bộ mutation. Java final-field rules giúp xây **thread-safe immutable objects**, không thay thế thiết kế API.

## 21. Mutable singleton và giới hạn của class initialization

Holder singleton tạo object an toàn một lần, nhưng nếu singleton chứa mutable state:

~~~java
final class CounterService {
    static final CounterService INSTANCE =
            new CounterService();

    int count;

    void increment() {
        count++;
    }
}
~~~

Việc `INSTANCE` được published an toàn **không** khiến `count++` atomic hoặc thread-safe. Class initialization chỉ bảo đảm initialization visibility theo quy tắc, không biến mọi subsequent method calls thành synchronized.

Cần kết hợp:
- AtomicInteger/LongAdder cho counters theo workload.
- Synchronized/locks cho compound invariants.
- Immutable snapshots qua AtomicReference nếu state có nhiều fields cần nhất quán.
- Concurrent collections phù hợp.
- Thread confinement hoặc message passing nếu không muốn shared mutable state.

**Câu ghi nhớ:** *safe initialization + safe publication ≠ automatic safe mutation forever.*

## 22. Constructor escape qua Thread.start: vì sao nguy hiểm?

Anti-pattern:

~~~java
final class EarlyWorker {
    final int port;

    EarlyWorker() {
        new Thread(() -> System.out.println(port)).start();
        port = 8080;
    }
}
~~~

Đây là **class minh họa**; Java source có thể biên dịch khi blank final được gán đúng. Runnable capture `this`; start xảy ra **trước** `port=8080`. Thread có thể đọc `0` nếu nó chạy sớm hoặc `8080` theo scheduling và memory effects thực tế; không có guarantee properly constructed publication cho final field ở thời điểm start.

**Không làm demo tự động in `0` với `Thread.sleep()` để “chứng minh JMM”**: scheduler và JIT khác nhau, timing không quyết định legality của memory model.

Cách sửa:

~~~java
final class ReadyWorker {
    final int port;

    ReadyWorker(int port) {
        this.port = port;
    }

    Thread startWorker() {
        Thread t = new Thread(() ->
                System.out.println(port));
        t.start();
        return t;
    }
}
~~~

Caller chỉ gọi `startWorker()` **sau khi `new ReadyWorker(...)` hoàn tất**, tránh escape trong constructor. Nếu có superclass/subclass inheritance, cách bố trí constructors/callbacks vẫn cần kiểm tra. Có thể dùng static factory để đảm bảo lifecycle.

### Gọi start ở cuối constructor liệu đủ?

Không nên làm vậy. Ngay cả khi `start()` nằm ở dòng cuối source, constructor chưa thực sự hoàn tất; object có thể escape trước constructor exit/freeze. Với subclassing, superclass constructor có thể start thread khi subclass fields chưa được gán. Giải pháp đơn giản nhất là **không publish `this` từ constructor**, mà tách start/register ra sau factory/construction.

## 23. Publication sai: không thể sửa bằng sleep, yield hay join sai hướng

Một pattern sai:

~~~java
static Example shared;

static void writer() {
    shared = new Example();
}

static void reader() {
    while (shared == null) {
        Thread.yield();
    }
    use(shared);
}
~~~

Đây là snippets cần Example/use thích hợp. `Thread.yield()` chỉ là scheduling hint, **không** hình thành volatile/monitor HB và không hứa một thread sẽ thấy reference thay đổi. Compiler/JMM có thể không cung cấp tiến triển/visibility như code mong đợi.

Tương tự:
- `Thread.sleep(10)` không tạo memory barrier đúng nghĩa mà bạn được quyền dùng để publish fields.
- Nhiều lần chạy đúng không chứng minh data race không có.
- `Thread.join()` chỉ có memory effect khi **thread chờ thực sự phát hiện termination** theo contract; không thể rải một `join` vô nghĩa vào đường thực thi khác rồi cho rằng mọi writes từ mọi threads đã visible.
- Ghi console đôi khi thay đổi timing/internal synchronization khiến race khó tái hiện, nhưng **không sửa correctness**.
- `synchronized` ở writer mà reader không đồng bộ cùng lock không phải safe publication protocol.

**Giải pháp:** tạo một HB path rõ ràng giữa những writes trước publication và reads sau publication, hoặc dùng đúng final-field semantics của immutable constructed object kết hợp thiết kế publication phù hợp.

## 24. Stress test JMM: đừng dùng số lần chạy bình thường làm chứng minh

Một concurrency bug có thể chỉ xuất hiện khi:
- JIT tối ưu đủ lâu, reorder/hoist reads.
- CPU architecture cho phép memory behavior khác máy dev.
- Thread scheduling thay đổi ở tải cao.
- Class initialization/safepoint/GC timings khác.
- Test trên nhiều CPU cores và compiler tiers.
- Publication diễn ra sát lúc constructor chưa hoàn tất.

Một bài thử cố gắng “đo số lần field bằng 0” với một vòng loop ngắn có thể trả về 0 lần lỗi **ngay cả khi code có data race**. Đó không phải bằng chứng an toàn.

### jcstress

OpenJDK **jcstress** là framework dành cho nghiên cứu các kết quả có thể quan sát trong chương trình concurrent theo memory-model litmus tests. Nó thực thi actors đồng thời qua nhiều iterations, thu outcomes và phân biệt expected/acceptable/interesting/forbidden states theo test định nghĩa.

**Điều nó giúp:** tăng cơ hội phát hiện outcome hiếm, thử nhiều JVM modes/hardware, học về visibility/ordering.

**Điều nó không hứa:** một race hợp lệ sẽ luôn xảy ra trên máy của bạn; không quan sát kết quả X không chứng minh X bị JMM cấm; stress testing không thay thế lập luận happens-before/JLS.

Trang dự án: https://openjdk.org/projects/code-tools/jcstress/ và https://github.com/openjdk/jcstress.

### Không dùng JMH thay jcstress

**JMH** đo hiệu năng microbenchmarks và kiểm soát JIT warmup/forks; **jcstress** kiểm thử outcomes concurrency. Chúng phục vụ câu hỏi khác nhau. Dùng JMH để kiểm tra correctness JMM hoặc jcstress để so p99 REST latency đều không đúng mục đích.

## 25. Chẩn đoán production: nhìn vào ownership, publication và API contract

Các công cụ như JFR, thread dumps, `jcmd` hoặc profiler hữu ích để thấy locks, thread states, CPU, GC và class loading, nhưng chúng **không tự chứng minh** chương trình không có data races. Một JMM bug phải được đánh giá qua code review và happens-before graph.

Một checklist điều tra:
1. Tìm fields có thể được nhiều threads cùng đọc/ghi. Phân biệt immutable snapshots và mutable shared state.
2. Tìm mọi nơi object reference được lưu vào shared static/instance fields, registries, maps hoặc queues.
3. Xác định thời điểm constructor hoàn tất so với những nơi publish reference.
4. Kiểm tra callbacks/listeners/overridable methods khiến `this` escape sớm.
5. Với reader, xác định acquire operation tương ứng với writer's release.
6. Vẽ happens-before chain cụ thể; không dừng ở “đã dùng synchronized somewhere”.
7. Với final reference chứa array/collection, kiểm tra defensive copy và mutations sau công bố.
8. Kiểm tra DCL `volatile`, lock monitor identity và class-init holder.
9. Khi nghi race, thiết kế jcstress test để xem outcomes mà JMM cho phép.
10. Sửa cách ownership/synchronization, rồi kiểm tra regression cả trên Java 17 và JDK triển khai thực.

### Khả năng quan sát và giới hạn

`jcmd PID Thread.print` hoặc JFR có thể giúp thấy thread stacks và lock contention; race trên ordinary field không bắt buộc có lock contention hoặc event rõ ràng. Thread dumps thường chỉ là ảnh chụp thời điểm; code có race không nhất thiết xuất hiện trong ảnh chụp.

Các lệnh diagnostics lấy PID từ process thật, không đưa dữ liệu nhạy cảm của production cho bên ngoài khi chưa được phép.

## 26. Các ngộ nhận phổ biến

| Ngộ nhận | Sự thật |
| --- | --- |
| “Constructor kết thúc nghĩa thread khác chắc chắn thấy mọi field.” | Chỉ khi có safe publication/HB hoặc những bảo đảm đặc biệt như final-field semantics. |
| “final và volatile giống nhau.” | final có initialization safety/immutability của field; volatile có ordering/visibility cho accesses tới variable. |
| “final ref khiến array/list bất biến.” | Chỉ field reference không được gán lại; referent và elements có thể mutable. |
| “final-field rules publish reference tới mọi thread.” | Không; ordinary racy publication vẫn có visibility/liveness issues trên reference. |
| “Constructor freeze tạo HB tổng quát cho mọi fields.” | §17.5 có điều kiện và dereference semantics đặc biệt; không tương đương volatile publish. |
| “Nếu dùng ConcurrentHashMap thì publish giữa constructor cũng ổn.” | Có thể safely publish **partial object**; phải construct đầy đủ trước put. |
| “Chạy new Thread trong constructor là cách khởi động tiện và luôn an toàn.” | Runnable capture this có thể observe object chưa initialized. |
| “final field gán ở cuối constructor là đủ dù this đã escape trước đó.” | Proper construction đã bị vi phạm, không dựa được guarantee đặc biệt. |
| “static final singleton không cần đồng bộ mọi method.” | Khởi tạo an toàn không làm mutations về sau tự thread-safe. |
| “volatile ref làm object fields thành volatile.” | Chỉ publication trước write được bảo đảm; post-publication mutable writes cần synchronization. |
| “Một thread thấy volatile ref là mọi object reachable đều immutable.” | Visibility của pre-publication writes khác với bất biến của graphs có aliases/mutations. |
| “DCL không volatile vẫn đúng vì constructor có final fields.” | DCL không volatile thiếu safe publication phù hợp cho ordinary state và reader path. |
| “Cùng chạy trên x86 không tái hiện lỗi thì JMM guarantee.” | Một execution không chứng minh portable correctness. |
| “Thread.sleep tạo memory barrier.” | Sleep không phải safe-publication protocol. |
| “volatile write đồng nghĩa compound action atomic.” | Volatile riêng field không làm nhiều bước read-modify-write thành transaction. |
| “Record luôn deep immutable.” | Record component có thể là mutable array/collection object. |
| “Immutable list luôn deep copy phần tử.” | CopyOf/unmodifiable wrappers có thể giữ mutable element references. |
| “jcstress không thấy lỗi tức chương trình chắc chắn an toàn.” | Stress outcomes không thay thế lập luận theo JLS. |
| “GC/JIT tự sửa race thiếu synchronization.” | JVM giữ đúng memory-model semantics, không tự cung cấp guarantees mà program thiếu. |

## 27. Câu hỏi tự kiểm tra kèm đáp án

**1. final-field freeze xảy ra khi nào?**

Theo JLS 17.5.1, có freeze action khi constructor ghi final field kết thúc. Cần hiểu chi tiết constructor delegation, không để reference escape sớm.

**2. Một object được constructed đúng, published qua ordinary racy field; reader nhìn thấy reference. Field `final int x=42` được đảm bảo thế nào?**

Properly constructed final-field guarantee cho phép reader thấy giá trị khởi tạo đúng của x. Nhưng publication qua ordinary field vẫn không cung cấp full HB cho arbitrary non-final fields và không bảo đảm reader sớm thấy reference.

**3. Tại sao `int y=17` ordinary field của cùng object không nhận bảo đảm giống final x khi racy publish?**

Vì final-field semantics đặc biệt không tự trở thành một synchronization HB edge tổng quát cho mọi ordinary fields.

**4. Nếu `this` được đưa vào registry trước khi gán final x, reader có chắc x=42 không?**

Không. Object không được properly constructed trước publication; có thể bị quan sát partial state.

**5. final `byte[] payload` có làm `payload[0]++` atomic không?**

Không. Final áp dụng cho reference field; array elements mutable và increments không atomic.

**6. clone trong constructor nhưng getter trả raw internal byte[] có immutable không?**

Không. Caller có thể mutate internal array qua getter. Cần defensive copy ở cả boundaries phù hợp.

**7. Writer lưu object fully initialized vào volatile field; reader đọc field đó. Điều gì được bảo đảm?**

Writes trước volatile publication HB những reads sau volatile acquire, nên readers thấy initial state theo HB. Updates mutable về sau vẫn cần đồng bộ.

**8. Writer khóa monitor A, reader khóa B, có safe publication không?**

Không chỉ từ hai locks khác nhau. Phải có đúng matching synchronization protocol.

**9. Holder singleton có cần synchronized trên mỗi accessor call?**

Không; class initialization cung cấp initialization safety cho static final INSTANCE. Mutable state trong instance vẫn phải thread-safe riêng.

**10. DCL cần volatile vì sao?**

Fast path đọc reference ngoài monitor; volatile cung cấp ordering/visibility cho publication và tránh data race trên reference.

**11. Nếu main tạo data rồi Thread.start(worker), worker được bảo đảm thấy writes trước start không?**

Có; start happens-before actions trong worker.

**12. Nếu worker ghi output rồi main join(worker), main thấy writes không?**

Có sau khi join thành công, theo termination/join HB.

**13. Volatile `current` thay reference mới, reader đọc current hai lần có thể thấy hai snapshots khác nhau không?**

Có, nếu publisher thay reference giữa hai reads; capture một local snapshot nếu cần coherence trên một object version.

**14. Một ConcurrentHashMap chứa fully initialized object có cần final cho mọi field để visibility đúng không?**

Không phải điều kiện của publication; map API cung cấp memory consistency cho insert/retrieval. Nhưng final vẫn có ích cho immutable design và fields mutate sau đó cần synchronization.

**15. Tại sao sleep không chứng minh không có data race?**

Sleep thay timing nhưng không tự tạo volatile/monitor/thread handoff edge cần thiết.

**16. JMH có thể chứng minh JMM cấm một outcome không?**

Không. JMH đo performance; cần JLS reasoning, code review và công cụ như jcstress cho stress outcomes.

**17. final field trong object mà constructor đã throw exception có ý nghĩa giống object hợp lệ được published không?**

Đừng thiết kế publication từ failed constructors. JLS mô tả freeze details cả abrupt exit, nhưng một object không xây dựng invariants hoàn chỉnh không nên được đưa cho application threads sử dụng.

**18. Record có component int[] và accessor trả original array có deep immutable không?**

Không. Record final field chỉ cố định reference, không ngăn mutations của array.

**19. final `AtomicInteger` có phải giá trị counter cố định không?**

Không. Reference tới AtomicInteger cố định, nhưng internal atomic value có thể cập nhật thread-safe.

**20. Cần hỏi gì đầu tiên nếu một thread đôi khi đọc config timeout=0?**

Kiểm tra constructor, publication timing, đường volatile/lock/queue/handoff ở writer-reader, và xem timeout được gán trước hay sau publish. Không kết luận “compiler reorder bug” khi thiếu HB.

## 28. Bản đồ ghi nhớ

~~~text
                CREATE OBJECT O
                       |
              DEFAULT FIELD VALUES
                       |
                 CONSTRUCTOR
                       |
            +----------+----------+
            |                     |
        NO this ESCAPE       this ESCAPES EARLY
            |                     |
       fields initialized      possible partial view
            |                     |
      CONSTRUCTOR EXIT         final guarantee may fail
            |
      FINAL FIELD FREEZE
            |
            v
          PUBLICATION
            |
       +----+---------------------------+
       |                                |
  RACY ORDINARY FIELD              SAFE PUBLICATION
       |                                |
  final-field special              volatile/lock/start/
  guarantee only                   class init/queue/Future
       |                                |
  non-final not fully              constructor writes
  ordered; ref liveness            happen-before reads
  not guaranteed                        |
       +----------------+---------------+
                        |
                   AFTER PUBLISH
                        |
                IS OBJECT MUTABLE?
                     /      \
                    NO       YES
                    |         |
             final + deep   locks/atomic/
             immutability   volatile/snapshot/
                    |       ownership discipline
                    +---------+
                              |
                    THREAD-SAFE DESIGN
                              |
                  Verify with JLS HB graph
                  and targeted jcstress tests
~~~

**Kết luận:** `final` fields có **initialization safety** đặc biệt nhờ **constructor freeze**, với điều kiện object được **properly constructed** và reference không escape sớm. Tuy nhiên final field **không tự tạo full safe publication cho mọi non-final fields**, cũng không làm một referent graph mutable trở thành deep immutable. Để code concurrent đáng tin, hãy **hoàn tất construction trước publication**, tạo một **happens-before path rõ ràng** bằng volatile/locks/class initialization/Thread.start/concurrent handoff phù hợp, và bảo vệ **mọi mutations về sau** theo ownership/synchronization protocol riêng.

## Tài liệu tham khảo chính thức

- [Java Language Specification SE 17 — §17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4).
- [Java Language Specification SE 17 — §17.4.5 Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5).
- [Java Language Specification SE 17 — §17.5 final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5).
- [Java Language Specification SE 17 — §17.5.1 Semantics of final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5.1).
- [Java Language Specification SE 17 — §12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2).
- [Java Language Specification SE 17 — §15.29 Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29).
- [Java SE 17 API — Thread.start, join, and interrupt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html).
- [Java SE 17 API — BlockingQueue memory consistency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).
- [Java SE 17 API — ExecutorService memory consistency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
- [Java SE 17 API — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html).
- [Java SE 17 API — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).
- [OpenJDK jcstress — Java Concurrency Stress tests](https://openjdk.org/projects/code-tools/jcstress/).
- [OpenJDK jcstress source repository](https://github.com/openjdk/jcstress).
