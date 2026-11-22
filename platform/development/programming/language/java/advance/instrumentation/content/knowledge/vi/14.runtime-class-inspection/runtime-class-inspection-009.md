# Chi phí và vòng đời tham chiếu khi lặp lại việc khảo sát lớp bằng Java Instrumentation

## 1. Vấn đề: một lần khảo sát rẻ không có nghĩa lặp lại mãi là rẻ

Trong một Java agent, việc gọi `Instrumentation.getAllLoadedClasses()` để xem JVM đang có những lớp nào là thao tác rất hữu ích khi điều tra class loading, kiểm tra phạm vi instrumentation, thống kê các class loaders hoặc quyết định liệu một class đã được nạp có đủ điều kiện retransform hay không.

Tuy nhiên, **khảo sát lớp không phải một thao tác miễn phí**. Mỗi lần gọi có thể tạo một mảng mới chứa rất nhiều tham chiếu `Class<?>`. Nếu tiếp tục duyệt mảng, truy vấn module, loader, modifiability, reflection hoặc lưu lại các kết quả, chi phí có thể tăng đáng kể. Và nếu agent giữ tham chiếu `Class<?>` hoặc `ClassLoader` quá lâu, nó có thể vô tình **ngăn class loader và các class do loader đó định nghĩa được thu hồi**, ngay cả khi plugin hoặc ứng dụng đã dỡ bỏ chúng.

Có hai câu hỏi độc lập cần giải quyết:

1. **Chi phí thực thi:** mỗi lần khảo sát mất bao lâu, tạo bao nhiêu dữ liệu tạm, có ảnh hưởng đến latency và hoạt động của JVM không?
2. **Vòng đời tham chiếu:** sau khảo sát, agent còn giữ những đối tượng nào; có làm các class loaders vốn có thể được GC giữ sống lâu hơn không?

Bài học thuộc mục **Khảo sát khi chạy**. Trọng tâm là `getAllLoadedClasses()`, `getInitiatedClasses(ClassLoader)`, `isModifiableClass(Class<?>)` và thiết kế vòng đời dữ liệu trong agent. Các ví dụ dùng **Java 17+** và API chính thức của `java.lang.instrument`.

**Thông điệp chính:** hãy coi một đợt khảo sát là **snapshot tạm**, trích xuất số liệu cần thiết rồi thả các tham chiếu; không biến mỗi snapshot thành một danh sách `Class<?>` tồn tại suốt vòng đời JVM.

## 2. Ba API thường được sử dụng khi khảo sát lớp

### 2.1. `getAllLoadedClasses()`: chụp danh sách toàn JVM

```java
Class<?>[] classes = instrumentation.getAllLoadedClasses();
```

Theo Javadoc Java 17, API trả một mảng các lớp/interface **đang được nạp trong JVM**. Kết quả bao gồm cả:

- Classes và interfaces thông thường;
- **Hidden classes/interfaces**;
- **Array classes** của nhiều loại phần tử.

Mảng này **không phải live view** cập nhật tự động. Sau khi lời gọi kết thúc, JVM có thể tiếp tục tải hoặc unload classes; mảng cũ không tự phản ánh những thay đổi đó.

Những điểm cần hiểu chính xác:

- Kết quả là **một `Class<?>[]`**, không phải tên lớp hoặc record thống kê.
- Trên Java 17, **hidden classes** có thể xuất hiện trong danh sách, dù không thể tra cứu bằng tên nhờ class loader như class thông thường.
- Các phần tử có thể bao gồm array types; array class không đồng nghĩa có một class file độc lập để transform.
- Không giả định thứ tự các phần tử ổn định giữa các lượt, các JVM hoặc các lần khởi động.
- API không cam kết làm “đứng yên” mọi class load/unload của ứng dụng sau thời điểm snapshot.
- Không suy rằng mỗi `Class<?>` là một class có thể redefine/retransform; cần kiểm tra điều kiện riêng.

Ví dụ chỉ đếm:

```java
Class<?>[] snapshot = inst.getAllLoadedClasses();
int total = snapshot.length;
// Dùng snapshot trong phạm vi ngắn, sau đó không lưu giữ.
```

Đây là **đoạn minh họa**, biến `inst` được truyền vào agent; chưa phải chương trình độc lập.

### 2.2. `getInitiatedClasses(loader)`: khảo sát theo initiating loader

```java
Class<?>[] initiated =
        instrumentation.getInitiatedClasses(targetLoader);
```

Hàm này trả những class mà `targetLoader` có thể tìm bằng tên theo quy tắc `ClassLoader.loadClass`, `Class.forName` và liên kết bytecode — nghĩa là những class mà loader đã được ghi nhận là **initiating loader**.

**Initiating loader không nhất thiết là defining loader.**

Ví dụ system loader có thể khởi tạo yêu cầu tìm `java.lang.String` và ủy quyền tới bootstrap loader. Class `String` được **bootstrap định nghĩa** dù system loader có thể là initiating loader trong một đường phân giải.

Những điểm khác biệt so với `getAllLoadedClasses()`:

- Truy vấn **theo một loader cụ thể**, không phải toàn JVM.
- Nếu tham số `loader == null`, truy vấn danh sách class mà **bootstrap loader** có thể tìm bằng tên.
- Kết quả **không chứa hidden classes/interfaces** hoặc array classes có element type là hidden class/interface, vì chúng không thể được tìm bằng tên thông thường.
- Nếu gọi với nhiều loader rồi cộng tất cả độ dài, **không chắc ra số class duy nhất của JVM**: cùng một class do parent định nghĩa có thể xuất hiện trong tập initiated của nhiều loader.
- Không coi đây là một API “chỉ liệt kê những class mà loader này trực tiếp define”.

**Khi nào nên dùng?** Khi chỉ quan tâm một initiating loader đã biết và định nghĩa bài toán đúng với initiating semantics, ví dụ quan sát các class đã được resolve qua một plugin loader. Đừng dùng nó làm bản thay thế có cùng ngữ nghĩa với `getAllLoadedClasses()`.

### 2.3. `isModifiableClass(type)`: kiểm tra từng class, không phải mọi class đều có thể sửa

```java
boolean candidate = instrumentation.isModifiableClass(type);
```

Hàm trả khả năng JVM cho phép sửa class đó bằng redefinition hoặc retransformation **về mặt loại class**. Nó **không** tự xác nhận agent đã được cấp capability retransform/redefine; các API `isRetransformClassesSupported()` và `isRedefineClassesSupported()` là điều kiện riêng.

Lưu ý:

- Primitive và array classes **không bao giờ modifiable**.
- `isModifiableClass(type) == true` **không bảo đảm mọi classfile replacement đều hợp lệ**.
- Thử kiểm tra modifiability cho **hàng chục nghìn class mỗi lần khảo sát** là một công việc bổ sung; không miễn phí và thường không cần nếu mục tiêu chỉ là đếm class.
- Nên **lọc class quan tâm trước**, rồi mới gọi `isModifiableClass` cho những class mà agent thực sự có ý định xử lý.

Không gọi `retransformClasses` hoặc `redefineClasses` chỉ để biết một class có tồn tại: đó là thao tác **thay đổi runtime**, không phải một phép liệt kê thuần túy.

## 3. Chi phí đến từ đâu?

Một đợt khảo sát toàn JVM thường có các loại chi phí sau:

| Hạng mục | Nguyên nhân | Điều cần đo |
| --- | --- | --- |
| Lấy snapshot | JVM phải cung cấp mảng chứa tham chiếu tới các class đang nạp | Duration của `getAllLoadedClasses()`, độ dài mảng |
| Allocation | Mỗi mảng `Class<?>[]` chiếm heap và giữ tham chiếu trong thời gian tồn tại | Kích thước *shallow* của mảng, allocation rate |
| Duyệt/filter | Mỗi phần tử cần xét tên, loader, module, kiểu array/hidden | Thời gian xử lý trên mỗi lượt, số phần tử duyệt |
| Truy vấn bổ sung | `isModifiableClass`, reflection, annotation inspection, resource lookup | Số lời gọi và thời gian tăng thêm |
| Chuyển dữ liệu/log | Ghi mọi tên class, serialize JSON, đẩy telemetry/network | Số bytes/log records, blocking time, backpressure |
| Lưu kết quả | Cache hoặc giữ snapshots trên heap | Retained heap, classloader retention/unloading |
| Đồng thời | Nhiều lần scan trùng nhau hoặc scan chạy cạnh tranh với class loading | Contention, latency tail, queue backlog |

### 3.1. Chi phí tăng theo số lớp

Giả sử tại một thời điểm JVM có `N` đối tượng `Class<?>` trong phạm vi khảo sát. Chỉ riêng việc trả một mảng chứa `N` phần tử đã cần tài nguyên tương ứng với số phần tử; nếu agent duyệt từng phần tử, công việc của **vòng lặp trong agent** là `O(N)`.

Đừng biến mô tả này thành cam kết chính xác rằng implementation nội bộ `getAllLoadedClasses()` có độ phức tạp hay pause time cố định trên mọi JVM. Đặc tả không cam kết tốc độ; con số phụ thuộc runtime, số class, GC, class loaders và cấu hình.

Nếu chạy **một lần mỗi giây** trong hệ thống có rất nhiều lớp, ngay cả vài millisecond mỗi lượt cũng tích lũy thành CPU/heap pressure đáng kể. Nếu mỗi lượt lại log toàn bộ class names hoặc kiểm tra modifiability, overhead có thể lớn hơn chính snapshot.

### 3.2. Snapshot array nằm trên heap, nhưng không đo được cả Metaspace

Một `Class<?>[]` giữ **các references** tới đối tượng `Class<?>`. Nếu nó có `N` phần tử, kích thước mảng gồm header và không gian lưu `N` references; số bytes mỗi reference phụ thuộc JVM và tùy chọn compressed references.

`Instrumentation.getObjectSize(snapshot)` trả một **ước lượng implementation-specific của kích thước *shallow* object**, hữu ích để so sánh trong cùng môi trường. Nó **không** là:

- Tổng heap của mọi `Class<?>` trong array;
- Tổng metadata/Metaspace của các class;
- Tổng retained heap của classloader/object graph;
- Công cụ đo chính xác GC pause hoặc memory leak;
- Số bytes portable giữa hai JVM khác nhau.

Không nhân kết quả `getObjectSize(Class<?>[])` lên rồi tuyên bố “tốn chừng ấy Metaspace”. Nếu cần đánh giá tác động đến Metaspace/class unloading, kết hợp JFR, GC logs hoặc công cụ heap/classloader diagnostics trên JVM mục tiêu.

### 3.3. Chi phí sau snapshot thường do agent tự tạo

Đoạn này tương đối nhẹ:

```java
Class<?>[] classes = inst.getAllLoadedClasses();
int count = classes.length;
```

Nhưng logic sau có thể rất tốn kém:

```java
for (Class<?> c : classes) {
    System.out.println(c.getName());
    // Reflection sâu, đọc annotation, gọi API khác cho từng class...
}
```

In từng dòng đồng bộ có thể chiếm phần lớn thời gian. Phân tích annotation hoặc reflective members có thể kéo theo nhiều công việc phụ, truy cập module/security hoặc nạp thêm class phụ thuộc tùy cách dùng. Nếu cần metadata sâu, hãy giới hạn vào **class thực sự liên quan** thay vì cả JVM.

## 4. Vòng đời tham chiếu `Class<?>` và nguy cơ giữ loader sống

### 4.1. Đường tham chiếu quan trọng

Theo `ClassLoader` Javadoc Java 17, một đối tượng `Class` chứa tham chiếu tới **defining class loader** của nó.

```text
GC root của agent
      |
      v
static Map<Class<?>, Metadata>
      |
      +---- key: Class<?> của plugin
                  |
                  v
           defining ClassLoader
                  |
                  v
            classes/resources
            của plugin
```

Nếu agent giữ `Class<?>` trong một collection tĩnh, nó có thể giữ defining loader reachable. Với một plugin loader vốn đã không còn được ứng dụng sử dụng, **tham chiếu mạnh từ agent có thể ngăn loader được reclaim**. Hậu quả là class metadata/Metaspace liên quan có thể không được giải phóng khi hệ thống mong đợi.

Điều tương tự có thể xảy ra nếu lưu:

- `Class<?>[]` snapshot trong một static field;
- `List<Class<?>>`, `Set<Class<?>>`, `Map<Class<?>, ...>` không có eviction;
- `ClassLoader` trực tiếp như map key hoặc value;
- `Method`, `Field`, `Constructor` hoặc metadata reflective giữ references đến declaring class;
- Object instance do plugin class tạo ra, hoặc lambda/task/thread context giữ plugin loader;
- `Throwable`/stack trace hoặc các đối tượng hạ tầng chứa references không được giải phóng.

**Không phải mọi chuỗi `String` chứa class name đều giữ ClassLoader.** Lưu số đếm/tên thuần có thể tránh giữ `Class<?>`, nhưng vẫn có nguy cơ **tăng heap không giới hạn** nếu tạo một key cho mỗi loader/class/lần khảo sát. Tránh memory leak cần cả **loại tham chiếu đúng** lẫn **giới hạn kích thước dữ liệu**.

### 4.2. Class unloading không được bảo đảm chỉ nhờ bỏ một tham chiếu

Theo JLS `12.7, một class/interface có thể được unload **chỉ khi defining class loader có thể được reclaim**; các class do bootstrap loader định nghĩa không thể unload theo quy tắc này.

Nhưng “có thể” **không có nghĩa sẽ**:

- GC có thể chưa chạy hoặc chưa quyết định unload ngay;
- Plugin có thể còn thread, instance, thread-local, callback, cache hoặc executor đang giữ loader;
- Agent khác cũng có thể giữ class/loader;
- Runtime tùy chính sách GC/class unloading và trạng thái reachability.

Vì vậy sau khi xóa cache, **không được khẳng định class chắc chắn đã unload**. Cần đo bằng sự kiện class unload/JFR, log JVM hoặc công cụ heap/classloader nếu muốn kết luận. `System.gc()` không phải một bảo đảm portable về thời điểm reclaim/unload.

### 4.3. Snapshot ngắn hạn vẫn là tham chiếu mạnh trong lúc được dùng

Một `Class<?>[]` trả về từ `getAllLoadedClasses()` là mảng tham chiếu mạnh trong lúc agent còn giữ. Nó có thể kéo dài vòng đời class/loaders **cho đến khi mảng và các references không còn reachable**.

Điều đó bình thường với một scan ngắn:

```java
static int countLoaded(Instrumentation inst) {
    Class<?>[] snapshot = inst.getAllLoadedClasses();
    return snapshot.length;
}
```

Sau khi hàm kết thúc, nếu không lưu snapshot ở đâu khác, mảng không còn được giữ bởi hàm này. **Không cần gọi `System.gc()` hoặc tự xóa từng phần tử** để “giải phóng”; GC quyết định thời điểm thực tế.

Ngược lại:

```java
static final java.util.List<Class<?>> ALL_EVER_SEEN =
        new java.util.ArrayList<>();

static void badPoll(Instrumentation inst) {
    java.util.Collections.addAll(
            ALL_EVER_SEEN, inst.getAllLoadedClasses());
}
```

Đây là **mã minh họa anti-pattern**, không phải chương trình độc lập. Mỗi lượt thêm vào hàng loạt tham chiếu (nhiều phần tử lặp lại). Danh sách tăng theo số lượt, giữ lớp/loader lâu dài và khó phân biệt classes đã unload với classes hiện tại.

Một biến thể `static Class<?>[] lastSnapshot` tuy không nhân đôi dữ liệu vô hạn như list trên, **vẫn** giữ mọi lớp thuộc snapshot gần nhất; sau khi ghi đè mảng cũ, snapshot mới tiếp tục giữ references tới nhiều lớp. “Chỉ lưu một snapshot” không đồng nghĩa không ảnh hưởng class unloading.

## 5. Bản ghi khảo sát có tuổi thọ khác snapshot

Một quy tắc thiết kế đơn giản:

```text
getAllLoadedClasses()
        |
        v
Class<?>[] snapshot — PHẠM VI NGẮN
        |
        +--> Duyệt/phân loại
        |      |
        |      +--> count (int)
        |      +--> durationNanos (long)
        |      +--> histogram kích thước có giới hạn
        |      +--> tên module/loader đã chuẩn hóa nếu thật cần
        |
        v
Kết thúc lượt scan
        |
        +--> Không giữ snapshot/Class<?>/ClassLoader
        |
        v
Chỉ lưu các scalar hoặc DTO không chứa class references
```

Một **`record ScanStats(int total, int arrays, long durationNanos)`** chỉ chứa số nguyên và không làm reference tới class loaders qua trường dữ liệu của nó. Đó là thiết kế tốt cho thống kê lâu dài.

Nếu cần theo dõi một class cụ thể lâu dài, hãy xác định điều đó là yêu cầu chức năng chủ động. Có thể dùng weak references, `ClassValue`, epoch-scoped caches hoặc lifecycle hook của plugin — nhưng không giả định một loại cache “magic” tự giải quyết mọi retention.

## 6. Ví dụ Java 17 hoàn chỉnh: khảo sát lặp lại nhưng chỉ giữ số liệu tổng hợp

Ví dụ này sử dụng Java agent bắt đầu bằng `-javaagent` để lấy `Instrumentation`, sau đó ứng dụng chủ động gọi **ba lượt scan tuần tự**:

1. Một scan chỉ đếm các nhóm class.
2. Một scan tương tự để quan sát chi phí và thay đổi runtime.
3. Một scan sâu hơn, chỉ kiểm tra `isModifiableClass` đối với **các class do system loader định nghĩa**.

Điểm học tập là **snapshot có phạm vi local**, còn giá trị trả về chỉ là record chứa primitive. Bài không cố chứng minh JVM sẽ có số class cố định hoặc thời gian cố định; các con số đó biến thiên theo môi trường.

### 6.1. Cấu trúc thư mục

```text
class-survey-demo/
├── SurveyAgent.java
├── SurveyTarget.java
├── SurveyApp.java
└── agent.mf
```

Các source ở default package để lệnh biên dịch dễ theo dõi. Dùng JDK 17+.

### 6.2. Tệp `SurveyAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class SurveyAgent {
    private static volatile Instrumentation instrumentation;

    private SurveyAgent() {
    }

    public static void premain(
            String agentArgs, Instrumentation inst) {
        instrumentation = inst;
    }

    // Chỉ chứa primitive, không giữ Class<?> hoặc ClassLoader.
    public record Stats(
            int total,
            int arrayClasses,
            int hiddenClasses,
            int systemDefined,
            int modifiableSystemDefined,
            long snapshotShallowBytes,
            long elapsedNanos) {
    }

    public static Stats scan(boolean deep) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Agent not installed");
        }

        long started = System.nanoTime();

        // Chỉ giữ mảng trong method này.
        Class<?>[] snapshot = inst.getAllLoadedClasses();

        int arrays = 0;
        int hidden = 0;
        int system = 0;
        int modifiable = 0;

        ClassLoader systemLoader =
                ClassLoader.getSystemClassLoader();

        for (Class<?> type : snapshot) {
            if (type.isArray()) {
                arrays++;
            }
            if (type.isHidden()) {
                hidden++;
            }

            // Lọc trước khi thử isModifiableClass.
            // Phân loại này chọn defining loader, không phải initiating.
            if (!type.isArray()
                    && !type.isPrimitive()
                    && type.getClassLoader() == systemLoader) {
                system++;

                if (deep && inst.isModifiableClass(type)) {
                    modifiable++;
                }
            }
        }

        // Ước lượng shallow size của MẢNG, không phải Metaspace.
        long arrayBytes = inst.getObjectSize(snapshot);
        long elapsed = System.nanoTime() - started;

        // Không trả snapshot, Class<?> hoặc loader.
        return new Stats(
                snapshot.length,
                arrays,
                hidden,
                system,
                deep ? modifiable : -1,
                arrayBytes,
                elapsed);
    }
}
```

**Giải thích code:**

- `premain` lưu `Instrumentation` để ứng dụng demo gọi `scan` sau khi JVM khởi động. Trong production, hãy giới hạn API này cho thành phần agent có quyền sử dụng, không phơi lộ đối tượng Instrumentation cho code không đáng tin.
- `Class<?>[] snapshot` là biến **local**; chỉ sống trong phạm vi cần duyệt.
- `Stats` chứa toàn bộ số liệu dạng primitive; không chứa `Class<?>`, `ClassLoader` hoặc mảng snapshot.
- `isArray()` và `isHidden()` phục vụ phân loại nhanh. Hidden classes được Javadoc `getAllLoadedClasses` bao gồm; array types cũng có thể có mặt.
- `systemDefined` ở đây là các class có **defining loader đúng bằng system loader** (so sánh reference identity), không phải tất cả class system loader có thể initiate.
- Chế độ `deep=false` **không** gọi `isModifiableClass` cho từng class, và `modifiableSystemDefined=-1` nghĩa “không đo”, không phải có -1 class.
- Chế độ `deep=true` chỉ kiểm tra modifiability trong **tập đã lọc**; nếu muốn đo mọi class, phải chấp nhận chi phí cao hơn và tách loại class không modifiable.
- `getObjectSize(snapshot)` là kích thước **shallow của mảng** và implementation-specific.
- Thời gian `elapsedNanos` bao gồm lấy mảng, duyệt, lọc, kiểm tra tùy chế độ và lấy shallow size; **không** đo riêng chi phí `getAllLoadedClasses`. Muốn bóc tách, đặt timer độc lập ngay quanh lời gọi.
- Không có thao tác load class bằng tên trong vòng lặp; chương trình chỉ dùng các `Class<?>` được JVM cung cấp.

### 6.3. Tệp `SurveyTarget.java`

```java
public final class SurveyTarget {
    private SurveyTarget() {
    }

    public static int value() {
        return 42;
    }
}
```

Class này cho ứng dụng thực hiện một công việc xác định trước khi bắt đầu scan.

### 6.4. Tệp `SurveyApp.java`

```java
public final class SurveyApp {
    private SurveyApp() {
    }

    private static void print(String label, SurveyAgent.Stats s) {
        System.out.println("[scan] " + label
                + " total=" + s.total()
                + " arrays=" + s.arrayClasses()
                + " hidden=" + s.hiddenClasses()
                + " system=" + s.systemDefined()
                + " modifiable=" + s.modifiableSystemDefined()
                + " arrayBytes=" + s.snapshotShallowBytes()
                + " elapsedNanos=" + s.elapsedNanos());
    }

    public static void main(String[] args) {
        System.out.println("[app] target=" + SurveyTarget.value());

        // Không lưu danh sách Class<?> giữa các lượt.
        SurveyAgent.Stats first = SurveyAgent.scan(false);
        SurveyAgent.Stats second = SurveyAgent.scan(false);
        SurveyAgent.Stats deep = SurveyAgent.scan(true);

        System.out.println("[app] completedScans=3");
        System.out.println("[app] allNonEmpty="
                + (first.total() > 0
                && second.total() > 0
                && deep.total() > 0));

        print("first", first);
        print("second", second);
        print("deep", deep);
    }
}
```

Không thể lấy `first.total()` hoặc `deep.elapsedNanos()` làm con số hằng cho mọi JVM. Ngay cả lúc agent chạy, runtime có thể nạp thêm helper classes hoặc dỡ class của plugin khác.

### 6.5. Tệp `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: SurveyAgent

```

Chỉ cần `Premain-Class`. Ví dụ **không** gọi retransform/redefine nên không cần `Can-Retransform-Classes` hoặc `Can-Redefine-Classes`.

### 6.6. Biên dịch, đóng gói, chạy trên Linux/macOS/WSL

Đứng tại thư mục `class-survey-demo/`:

```bash
mkdir -p out

javac --release 17 -d out \
  SurveyAgent.java SurveyTarget.java SurveyApp.java

# Agent JAR chứa agent và nested record Stats.
jar --create --file survey-agent.jar --manifest agent.mf \
  -C out SurveyAgent.class -C out 'SurveyAgent$Stats.class'

# App JAR chứa hai class ứng dụng.
jar --create --file survey-app.jar \
  -C out SurveyApp.class -C out SurveyTarget.class

java -javaagent:survey-agent.jar \
  -cp "survey-agent.jar:survey-app.jar" SurveyApp
```

`SurveyAgent$Stats.class` là file compiler tạo cho nested record. Dấu nháy đơn bảo vệ ký tự `$` trước POSIX shell. Đừng bỏ file nested record khi đóng agent JAR.

### 6.7. Windows PowerShell

```powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -d out SurveyAgent.java SurveyTarget.java SurveyApp.java

jar --create --file survey-agent.jar --manifest agent.mf -C out SurveyAgent.class -C out 'SurveyAgent$Stats.class'
jar --create --file survey-app.jar -C out SurveyApp.class -C out SurveyTarget.class

java -javaagent:survey-agent.jar -cp "survey-agent.jar;survey-app.jar" SurveyApp
```

Chạy lệnh tại cùng thư mục chứa ba source và `agent.mf`.

### 6.8. Output: điều gì cố định, điều gì biến thiên?

Hai dòng đầu là **kết quả xác định trong điều kiện demo thành công**:

```text
[app] target=42
[app] completedScans=3
[app] allNonEmpty=true
```

Sau đó là **ba dòng bắt đầu bằng** `[scan] first`, `[scan] second` và `[scan] deep`. Mỗi dòng chứa các trường `total`, `arrays`, `hidden`, `system`, `modifiable`, `arrayBytes` và `elapsedNanos` với **giá trị thực đo được**, không có số cố định portable.

Chú ý thứ tự: chương trình in `[app] completedScans=3` và `[app] allNonEmpty=true` **trước** ba dòng dữ liệu `[scan]`, dù các phép khảo sát đã được thực hiện trước đó.

Trong hai lượt `first` và `second`, trường `modifiable=-1` (chưa đo). Ở lượt `deep`, giá trị này là số không âm, vì chương trình kiểm tra một tập class đã lọc. Không khẳng định `second.total >= first.total`: JVM có thể nạp **và unload** classes giữa hai snapshot.

### 6.9. Cách đánh giá kết quả

- Nếu `elapsedNanos` của lượt `deep` lớn hơn hai lượt cơ bản, có thể do nhiều lời gọi `isModifiableClass`; nhưng **một lần thử không đủ kết luận overhead trung bình**.
- Nếu `total` tăng theo lượt, cần kiểm tra runtime có tải class mới hay không, không lập tức kết luận agent có leak.
- Nếu `arrayBytes` tăng, mảng snapshot lớn hơn; con số đó **không đo trực tiếp retained Metaspace**.
- Nếu ba lần scan hoàn thành, ứng dụng vẫn không giữ `Class<?>[]` nào **sau khi `scan` trả về**. Điều này làm giảm một nguồn retention do chính ví dụ tạo ra, **không chứng minh toàn JVM không có cache giữ class loaders**.

## 7. Anti-pattern: duy trì lịch sử snapshot và các class đã từng thấy

### 7.1. Lưu toàn bộ snapshot theo thời gian

```java
static final java.util.List<Class<?>[]> HISTORY =
        new java.util.ArrayList<>();

static void retainEveryScan(Instrumentation inst) {
    HISTORY.add(inst.getAllLoadedClasses());
}
```

Đây là **anti-pattern minh họa**, không phải chương trình độc lập. Sau `K` lượt, agent đã giữ `K` mảng — mỗi mảng có thể chứa rất nhiều tham chiếu trùng nhau. Các class loaders đã ngừng được ứng dụng dùng có thể vẫn reachable qua snapshots cũ.

Nếu cần lịch sử để biểu đồ, hãy lưu:

```text
timestamp, totalLoadedCount, arrayCount, hiddenCount, scanDuration
```

dưới dạng dữ liệu scalar/time-series có giới hạn, không lưu từng mảng `Class<?>[]`.

### 7.2. Cache `Class<?>` không có eviction

```java
static final java.util.Map<Class<?>, String> NAMES =
        new java.util.concurrent.ConcurrentHashMap<>();

static void remember(Class<?> type) {
    NAMES.putIfAbsent(type, type.getName());
}
```

Mặc dù value chỉ là `String`, **key `Class<?>` là strong reference**. Map tĩnh có thể giữ class và defining loader sống mãi.

Nếu cache là bắt buộc, cần hợp đồng rõ về lifetime, giới hạn số entry, sự kiện unload/stop plugin và cách giải phóng. Đừng đặt cache không giới hạn ở agent chỉ để tối ưu một lookup rẻ như `Class.getName()`.

### 7.3. Lưu `ClassLoader` từ mỗi class

```java
static final java.util.Set<ClassLoader> LOADERS =
        java.util.concurrent.ConcurrentHashMap.newKeySet();

static void record(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    if (loader != null) {
        LOADERS.add(loader);
    }
}
```

Đây cũng là **anti-pattern nếu không bao giờ xóa key**. Với hệ thống hot-deploy có hàng nghìn loaders, Set tăng dần và trực tiếp ngăn GC reclaim những loader đã bị ứng dụng dỡ.

Nếu chỉ cần **đếm loaders trong một snapshot**, hãy dùng cấu trúc cục bộ (trong thời gian scan), không lưu tập đối tượng loader ra ngoài. Nếu cần phân biệt ID cho telemetry dài hạn, phải thiết kế ID/lifecycle có giới hạn, tránh chỉ dựa vào `System.identityHashCode(loader)` vì có thể va chạm và không định danh vĩnh viễn.

## 8. Biện pháp quản lý vòng đời dữ liệu

### 8.1. Ưu tiên trả DTO chỉ chứa primitives hoặc immutable strings có giới hạn

Ví dụ thiết kế tốt:

```java
public record Summary(
        long timestampMillis,
        int classes,
        int hiddenClasses,
        long durationNanos) {
}
```

Đoạn này là một `record` Java 17 minh họa. Không có `Class<?>` hoặc `ClassLoader` nào trong cấu trúc. Nếu thêm histogram theo package/module, nên giới hạn số buckets, số entries và thời hạn giữ dữ liệu.

**String không phải là class identity.** Hai class do hai loaders định nghĩa có thể cùng tên; nếu dùng name làm key, metadata sẽ bị gộp. Đừng giải quyết bằng cách giữ mạnh mọi loader trong một map không bao giờ hết hạn.

### 8.2. `WeakReference<ClassLoader>`: hữu ích để quan sát, không phải bảo đảm unload

```java
java.lang.ref.WeakReference<ClassLoader> ref =
        new java.lang.ref.WeakReference<>(pluginLoader);
```

Đây là snippet minh họa: `pluginLoader` là loader do application/plugin lifecycle cung cấp. Weak reference **không tự giữ referent sống**, nên có thể phục vụ quan sát “loader còn reachable hay đã được GC clear?”. Nhưng:

- Nếu có tham chiếu mạnh ở nơi khác, `ref.get()` vẫn có thể khác `null`.
- Sau khi bỏ các strong references, GC **có thể chưa chạy**; `ref.get() != null` không chứng minh leak.
- Khi `ref.get() == null`, loader đã không còn weakly reachable theo semantics của reference; nhưng không suy từ đó mọi resource bên ngoài đã được giải phóng.
- Nếu code lấy `ClassLoader active = ref.get()`, biến `active` tạm thời là một **strong reference** trong thời gian sử dụng.
- Không lưu thêm `Class<?>`/`Method`/instances trong value của cache theo weak loader; điều đó có thể phá ý định weak-key cache.

Một `WeakHashMap<ClassLoader, Metadata>` dùng weak keys có thể hữu ích, **nhưng không tự thread-safe** và value có thể gián tiếp giữ lại key/loader. Nếu value trỏ tới một `Class<?>` do loader định nghĩa, vòng tham chiếu từ value tới loader có thể làm key không còn được thu hồi theo cách mong đợi.

### 8.3. `ClassValue<T>`: gắn metadata theo từng `Class<?>`

Java có `java.lang.ClassValue<T>` để liên kết giá trị tính toán theo class. Đây là lựa chọn đáng cân nhắc khi thực sự cần cache metadata **cho từng class** mà không duy trì `static Map<Class<?>, T>` với strong keys:

```java
private static final ClassValue<String> CLASS_LABEL =
        new ClassValue<>() {
            @Override
            protected String computeValue(Class<?> type) {
                return type.getName();
            }
        };
```

Đây là đoạn **minh họa** trong một class Java; không có entry point độc lập. `CLASS_LABEL.get(type)` lấy giá trị gắn với type; `remove(type)` xóa value liên kết để tính lại khi cần.

`ClassValue` không nên được hiểu là lời hứa mọi data/reference luôn tự giải phóng đúng thời điểm; value được tính có thể giữ external resources, thread, class loaders khác hoặc mảng lớn. Phải kiểm soát **nội dung value**, **vòng đời của chính ClassValue** và tính phù hợp của cache.

### 8.4. Bounded cache và lifecycle hooks

Nếu mục đích là đưa ra quyết định instrumentation cho class đã được kiểm tra:

- Giới hạn cache theo số entries/bytes hoặc thời gian;
- Có TTL/epoch/invalidation theo plugin/module lifecycle;
- Không dùng tên class đơn lẻ làm identity trong môi trường nhiều loader;
- Xóa cache khi module/plugin dừng hoặc phiên bản policy thay đổi;
- Tránh giữ strong reference tới class loader chỉ để nhớ việc đã khảo sát;
- Kiểm soát thread safety, race giữa scan và unload;
- Nếu cần giữ class identity để thực sự gọi `retransformClasses`, chỉ giữ trong **batch ngắn hạn** và giải phóng ngay khi hoàn thành.

Không nên cố “đo đúng loader” bằng cách chụp toàn bộ graph của class loaders trong một static field không bao giờ reset.

## 9. Dùng event-driven thay vì polling toàn JVM khi phù hợp

Nếu mục tiêu là biết **class mới vừa được định nghĩa** để quyết định có chèn instrumentation, `ClassFileTransformer` thường phù hợp hơn việc gọi `getAllLoadedClasses()` liên tục:

```java
inst.addTransformer(new ClassFileTransformer() {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if ("demo/Target".equals(className)) {
            // Ghi nhận một sự kiện ngắn hoặc áp policy.
        }
        return null;
    }
}, false);
```

Đây là **đoạn minh họa trong `premain`/`agentmain`**, cần import `ClassFileTransformer`, `ProtectionDomain`, có `Instrumentation inst`. Transformer quan sát các class **được load trong tương lai** (và có thể redefine theo hợp đồng). Nó không tự replay toàn bộ lịch sử các class đã được nạp **trước khi đăng ký**.

Cần cẩn thận: callback chạy trên đường class loading, vì vậy thao tác trong callback phải **rất ngắn, không blocking I/O và không gây class loading đệ quy**. Event-driven cũng có chi phí; đó không phải giải pháp “zero overhead”.

Khi cần bức tranh tổng thể ngay tại thời điểm agent attach:

1. Chụp **một snapshot** ban đầu bằng `getAllLoadedClasses()`;
2. Lọc class quan tâm và chỉ giữ metadata cần thiết;
3. Theo dõi class mới bằng transformer hoặc JVM events;
4. Định kỳ **reconcile** với snapshot toàn JVM ở tần suất thấp để phát hiện lệch;
5. Không coi biến đổi giữa hai snapshot là một event log đầy đủ.

### Class unload không được thể hiện đầy đủ bởi load-time transformer

`ClassFileTransformer` không phải callback thông báo class unloading. Nếu cần xác định loader/class có thực sự unload, dùng JFR events hoặc cơ chế JVMTI/JVM class-unload diagnostics tùy runtime. Không tính “class có ở snapshot A nhưng vắng snapshot B” thành một bằng chứng unload tuyệt đối khi snapshot không lưu đủ identity hoặc khi class loading/unloading xảy ra đồng thời.

## 10. Lịch khảo sát: tần suất, giới hạn và backpressure

### 10.1. Chọn tần suất theo mục tiêu

Đối với chẩn đoán một lần, một snapshot có thể đủ. Đối với telemetry dài hạn, polling mỗi vài giây/phút chỉ nên bắt đầu sau khi đo được overhead ở workload thật.

Một mô hình vận hành:

```text
Tác vụ được lên lịch
        |
        v
Kiểm tra scan trước đã hoàn thành?
        |
   +----+----+
   |         |
  Có       Chưa
   |         |
   v         v
 Scan      Bỏ lượt/đánh dấu skipped
   |
   v
Đếm / tổng hợp
   |
   v
Xuất metrics có giới hạn
   |
   v
Thả Class<?>[] và các references cục bộ
```

Đừng để scheduler tạo thêm một đợt scan khi đợt trước còn chạy và tích lũy queue vô hạn. Nếu một scan mất lâu hơn interval, có thể **bỏ lượt** thay vì mở nhiều vòng đồng thời.

### 10.2. Đặt budget

Các chỉ số nên ghi:

- `scan_duration_ms`: tổng thời gian;
- `loaded_class_count`: kích thước snapshot;
- `array_class_count`, `hidden_class_count`;
- `survey_failures_total` và `survey_skipped_total`;
- `scan_frequency`, `scan_overlap_count`;
- `approx_array_shallow_bytes` nếu có nhu cầu;
- JFR/GC: heap allocation, pause, Metaspace và class-unload trend.

Các chi tiết bổ sung có thể hữu ích theo use case: số loaders có active class, số class nằm trong named modules, số classes modifiable sau bộ lọc. Đừng đưa mọi metric vào pipeline production khi chưa biết giá trị sử dụng và overhead của nó.

### 10.3. Phân biệt thời gian API với thời gian phân tích

Thường cần đo hai khoảng:

```java
long t0 = System.nanoTime();
Class<?>[] classes = inst.getAllLoadedClasses();
long t1 = System.nanoTime();

// Duyệt, filter, lấy module, isModifiableClass...
long t2 = System.nanoTime();

long snapshotNanos = t1 - t0;
long processingNanos = t2 - t1;
```

Đây là **khung mã minh họa**: đoạn không có vòng xử lý ở giữa nên `processingNanos` chưa đại diện cho pipeline thực. Hãy bổ sung logic thật, chạy warm-up, đo nhiều lượt và khảo sát percentile thay vì chỉ một mẫu. Timer cũng có overhead nhỏ; environment nên giữ ổn định khi so sánh.

Đặc biệt, nếu đo `System.nanoTime` trong JIT-warmed JVM nhưng một số module/plugin vẫn tiếp tục class loading, các lượt không có điều kiện giống hệt nhau. Không suy ra “API tự động chậm dần” chỉ vì workload ngày càng chứa nhiều class.

## 11. Snapshot không phải danh sách class cố định qua thời gian

### 11.1. Diff hai snapshot có những cạm bẫy

Giả sử:

```java
Class<?>[] previous = inst.getAllLoadedClasses();
// ... một thời gian ...
Class<?>[] current = inst.getAllLoadedClasses();
```

Nếu giữ `previous` lâu để diff, chính việc giữ nó có thể làm một số class loaders không unload. Vì vậy phương pháp đo **đã tác động đến đối tượng đang được đo**.

Có thể tính một diff **trong một khoảng ngắn**, trả các số liệu tổng hợp rồi giải phóng cả hai mảng. Nhưng nếu bạn muốn so sánh mọi class identity qua nhiều giờ, một tập `Class<?>` lưu dài hạn không phù hợp với yêu cầu class unloading không bị ảnh hưởng.

### 11.2. Key theo tên không xác định class duy nhất

Hai plugin loaders có thể cùng định nghĩa `com.example.Plugin`. Khi đó:

```text
Plugin loader A -> Class<?> com.example.Plugin (A)
Plugin loader B -> Class<?> com.example.Plugin (B)
```

Hai `Class<?>` có cùng tên từ `getName()`, nhưng **khác class identity**. Nếu chỉ lưu tên để so sánh snapshots, bạn không thể kết luận có bao nhiêu class identities được thêm/bỏ chính xác.

Các lựa chọn:

- Nếu chỉ muốn **đếm tổng**, chấp nhận thống kê không mang danh tính;
- Nếu cần nhóm theo name/module, nói rõ đây là **aggregation** chứ không phải tracking từng class;
- Nếu cần class identity thật, thiết kế epoch ngắn hạn hoặc tracking bằng weak keys, lường trước race và garbage collection;
- Nếu cần sự kiện unload chuẩn, dùng cơ chế JVM chuyên biệt thay vì suy từ tên và kích thước snapshot.

### 11.3. Không nhầm loader hiện tại với lịch sử

`getAllLoadedClasses()` chụp những class đang loaded tại thời điểm lấy mảng. Nó không phải log “tất cả class đã từng được JVM tải từ lúc khởi động”. Một class có thể xuất hiện trong snapshot trước, sau đó loader unload và class không còn trong snapshot sau. Nếu agent giữ tham chiếu từ snapshot trước, chính điều đó có thể làm class đó tiếp tục reachable.

## 12. Chẩn đoán classloader retention và Metaspace growth

Nếu một dịch vụ hot deploy ngày càng dùng nhiều Metaspace sau mỗi lần reload plugin, hãy kiểm tra hai loại nguyên nhân:

**Ứng dụng:** thread, scheduler, thread-local, static listener, cache hay callback vẫn giữ plugin loader/instances.

**Agent:** snapshot đã giữ, `Map<Class<?>, ...>`, `Set<ClassLoader>`, transformer state, callback/handler hoặc metadata reflective giữ class/loader.

Quy trình gợi ý:

1. Ghi mốc trước/giữa/sau mỗi chu kỳ plugin deployment.
2. Quan sát classloader counts, class loading/unloading và Metaspace qua JFR/GC logs hoặc công cụ JVM.
3. Kiểm tra heap dump/retained paths nếu số loader tăng bất thường; tìm các GC roots dẫn từ agent tới `Class<?>`/`ClassLoader`.
4. Tạm thời tắt/bỏ **tính năng khảo sát do agent sở hữu** trong môi trường kiểm soát để so sánh.
5. Sửa theo vòng đời: bỏ static snapshot, thay strong-key cache, đóng lifecycle listeners và giới hạn bảng theo dõi.
6. Kiểm tra nhiều chu kỳ warm-up, GC, unload; không dựa vào một lần gọi `System.gc()`.
7. Không vội kết luận mọi tăng trưởng Metaspace là leak: JIT, class loading hợp lệ và chính sách GC có thể làm đường biểu diễn tăng mà không phải retention vô hạn.

### Dùng `WeakReference` để làm phép thử có điều kiện

Có thể tạo `WeakReference<ClassLoader>` tới plugin loader **mà ứng dụng vừa quyết định dỡ**, bỏ strong references rồi chờ GC có cơ hội hoạt động. Nếu một lúc sau `ref.get() == null`, đó là bằng chứng loader không còn weakly reachable ở thời điểm GC xử lý. Nếu `ref.get() != null`, **chưa đủ để kết luận leak**: GC có thể chưa thu gom hoặc loader vẫn được sử dụng hợp lệ.

Khi chẩn đoán, đừng để phép thử tự tạo `Class<?>`/ClassLoader strong reference trong một collection tĩnh; nếu không kết quả sẽ bị nhiễu bởi chính mã đo.

## 13. So sánh ba cách tiếp cận

| Phương pháp | Chi phí chính | Vòng đời tham chiếu | Phù hợp khi |
| --- | --- | --- | --- |
| `getAllLoadedClasses()` mỗi lần theo yêu cầu | Snapshot toàn JVM + xử lý mỗi class | Mảng local nếu giữ ngắn; rủi ro nếu cache | Điều tra tức thời, reconcile ít lần |
| `getInitiatedClasses(loader)` | Snapshot theo initiating loader | Giữ loader trong thời gian truy vấn; kết quả local | Chỉ quan tâm tập class loader **có thể tìm bằng tên** |
| Transformer event-driven | Callback trên đường class load/redefine | Chỉ giữ dữ liệu event tổng hợp | Cần theo dõi các definition tương lai, áp policy |
| JFR/JVMTI class events | Phụ thuộc cấu hình runtime và loại sự kiện | Có buffer/event retention riêng cần quản lý | Cần lịch sử class load/unload hoặc profiling |
| Lưu toàn bộ `Class<?>[]` mỗi phút | Allocation + tăng retained refs | Có thể ngăn unload, tăng heap theo thời gian | **Không nên dùng làm lịch sử dài hạn** |
| Lưu primitive summary mỗi phút | Allocation/CPU scan + dữ liệu nhỏ | Không giữ class loader qua kết quả summary | Telemetry định kỳ cần biểu đồ xu hướng |

Không có phương pháp nào là “zero cost”. Chọn theo câu hỏi cần trả lời, mức độ chính xác và budget được chấp nhận.

## 14. Lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Mỗi phút CPU tăng vọt khi agent scan | Quét toàn JVM và truy vấn sâu cho từng class | Giảm tần suất, lọc sớm, đo từng giai đoạn |
| GC/heap allocation tăng | Mỗi lần tạo snapshot lớn và log/serialize nhiều metadata | Lưu số liệu tổng hợp, giảm/giới hạn export |
| Plugin unload rồi nhưng loader vẫn nằm trong heap | Agent giữ `Class<?>[]`, map keys hoặc loader references | Kiểm tra GC roots, xóa strong retention theo lifecycle |
| `System.gc()` xong loader vẫn chưa biến mất | GC/unload không được bảo đảm ngay hoặc còn references khác | Không kết luận leak từ một lần; đo retained paths |
| `getAllLoadedClasses` trả nhiều hơn số class có thể retransform | Kết quả gồm arrays/hidden/unmodifiable classes | Dùng `isModifiableClass` và capability checks trên tập cần xử lý |
| `getInitiatedClasses` cộng nhiều loader tạo số lớp quá lớn | Cùng class do parent define có thể được initiate qua nhiều loader | Không cộng trực tiếp thành tổng unique classes |
| Không thấy hidden classes trong `getInitiatedClasses` | Hidden classes không discoverable bằng tên | Dùng API phù hợp với câu hỏi, đọc đúng Javadoc |
| `getAllLoadedClasses` có hidden/array classes | API được đặc tả bao gồm chúng | Phân loại/loại trừ có chủ đích |
| Snapshot A và B khác độ dài | Class load/unload xảy ra, agent/JVM có thể tự load thêm classes | Không suy từ một diff rằng đã leak/unload |
| Cache theo `getName()` bị sai | Class cùng tên ở hai loaders khác nhau | Phân biệt namespace/identity khi thật sự cần |
| `getObjectSize(snapshot)` bị hiểu là Metaspace | Chỉ shallow size của một object | Dùng classloader/JFR/GC/Metaspace metrics khác |
| `WeakHashMap` vẫn giữ plugin loader | Value tham chiếu ngược về class/loader, hoặc cache có strong refs khác | Kiểm tra object graph, không tin weak key một cách máy móc |
| `ClassValue` chứa dữ liệu lớn | Giá trị liên kết có resources hoặc refs không giới hạn | Dọn data/lifecycle và chọn giới hạn cache |
| Quét lặp trùng giờ | Scheduler không chống overlap/backpressure | Dùng một worker, skip/delay lượt khi trước chưa xong |
| Muốn liệt kê lớp đã từng unload bằng `getAllLoadedClasses` | Snapshot không phải event history | Dùng JFR/JVMTI events hoặc tracking phù hợp |
| Transformer gây deadlock trong khảo sát | Callback làm I/O/lock/load class đệ quy | Giảm việc trong callback, tách xử lý, kiểm soát concurrency |

## 15. Checklist vận hành

1. **Xác định câu hỏi:** cần tổng số class hiện tại, tập initiated của một loader, hay sự kiện class load/unload theo thời gian?
2. **Đúng API:** `getAllLoadedClasses()` là toàn JVM; `getInitiatedClasses(loader)` là initiating loader; hai tập không thay thế nhau.
3. **Snapshot ngắn hạn:** mảng `Class<?>[]` chỉ nằm trong phạm vi scan; không giữ vào static history.
4. **Lọc sớm:** tránh gọi `isModifiableClass`/reflection sâu cho mọi class khi không cần.
5. **Không giữ loader lâu:** kiểm tra mọi cache `Class<?>`, `ClassLoader`, reflection metadata, plugin instances.
6. **Summary nhẹ:** chỉ lưu số liệu scalar, bounded string labels hoặc aggregation có giới hạn.
7. **Cache có lifecycle:** cân nhắc `ClassValue`/weak references/TTL nhưng kiểm tra value references và thread safety.
8. **Tần suất vừa đủ:** đo overhead trên workload thật, dùng backpressure và không chồng scans.
9. **Đo đúng chi phí:** tách thời gian snapshot/processing/export; `getObjectSize` chỉ đo shallow object approximation.
10. **Không suy GC tuyệt đối:** bỏ strong refs mở khả năng unload, **không ép JVM unload ngay**.
11. **Theo dõi unload thật:** dùng JFR/GC logs/classloader diagnostics, không suy từ tên class.
12. **Tôn trọng class identity:** loader + binary name là cơ sở định nghĩa class; aggregation theo name chỉ là thống kê.
13. **Không sửa runtime để khảo sát:** tránh `retransformClasses` hoặc classloading chủ động khi mục tiêu chỉ là liệt kê.
14. **Thử nghiệm Java 17 thực tế:** so sánh hoạt động trên app bình thường và app có nhiều plugin/custom loaders.
15. **Bảo toàn an toàn vận hành:** mọi metric và callback phải nhỏ gọn, không tạo queue không giới hạn hoặc deadlock.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `getAllLoadedClasses()` không phù hợp làm một “history” giữ mãi trong static list?

**Đáp án:** Mỗi lời gọi trả mảng chứa tham chiếu mạnh `Class<?>`. Giữ history có thể tăng heap và giữ class/defining class loaders reachable, ngăn một số class loaders có cơ hội GC/unload.

**Câu 2.** `getInitiatedClasses(loader)` có chỉ trả các class do chính loader đó define không?

**Đáp án:** Không. Nó theo **initiating loader**; các class do parent/bootstrap define có thể vẫn nằm trong tập initiated của loader khác.

**Câu 3.** `getAllLoadedClasses()` có bỏ hidden classes hoặc array classes không?

**Đáp án:** Không. Javadoc Java 17 quy định bao gồm cả hidden classes/interfaces và array classes. Ngược lại, `getInitiatedClasses` không liệt kê hidden classes hoặc array classes của hidden element type vì không discoverable bằng tên.

**Câu 4.** Tại sao một `Map<Class<?>, Metadata>` tĩnh có thể gây classloader leak?

**Đáp án:** Strong key tham chiếu tới đối tượng `Class<?>`; đối tượng này liên kết với defining ClassLoader. Nếu map giữ key lâu dài, loader có thể còn reachable dù ứng dụng đã ngừng sử dụng plugin.

**Câu 5.** Xóa mọi snapshot của agent có chắc class loader được GC ngay không?

**Đáp án:** Không. Còn có thể có references ở nơi khác và GC/unload là hành vi do JVM quyết định. Xóa snapshot chỉ loại bỏ một nguồn retention.

**Câu 6.** `getObjectSize(snapshot)` có đo tổng Metaspace của mọi class trong mảng không?

**Đáp án:** Không. Đây là ước lượng kích thước shallow của object mảng theo implementation.

**Câu 7.** Hai scan trả `total` lần lượt là 10.000 và 9.900. Có thể kết luận đúng 100 class unload không?

**Đáp án:** Không. Giữa hai snapshot có thể đồng thời load và unload, kết quả còn gồm arrays/hidden classes, và bản thân phép đo không mang đầy đủ lịch sử.

**Câu 8.** Khi cần chỉ instrument class mới được load, có cần polling `getAllLoadedClasses()` mỗi giây không?

**Đáp án:** Thường không. Có thể dùng `ClassFileTransformer` event-driven cho những class được định nghĩa sau khi đăng ký, kết hợp một scan ban đầu nếu cần xử lý class đã nạp.

## 17. Tài liệu chính thức

- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `getInitiatedClasses`, `getObjectSize`, `isModifiableClass` và transform/retransform.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining vs initiating loader; `Class` giữ reference tới defining loader.
- [Java Language Specification SE 17 — `12.7 Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): điều kiện class unloading, không có bảo đảm unload khi loader còn reachable.
- [Java SE 17 — `WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability và referent collection.
- [Java SE 17 — `ClassValue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html): liên kết metadata theo class mà không thiết kế static map strong keys.
- [Java SE 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName`, `getClassLoader`, `isArray`, `isHidden` và class identity.
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback khi định nghĩa/redefine/retransform, giới hạn công việc trên đường class loading.

**Ghi nhớ:** **Khảo sát lớp là thao tác tạo snapshot và tham chiếu mạnh tạm thời.** Khi lặp lại `getAllLoadedClasses()`, hãy đo chi phí, lọc công việc, giữ snapshot sống càng ngắn càng tốt và chỉ lưu dữ liệu tổng hợp. Một `Class<?>` bị giữ trong agent có thể giữ defining class loader sống, còn việc bỏ tham chiếu chỉ cho phép — chứ không bảo đảm ngay lập tức — class unloading.
