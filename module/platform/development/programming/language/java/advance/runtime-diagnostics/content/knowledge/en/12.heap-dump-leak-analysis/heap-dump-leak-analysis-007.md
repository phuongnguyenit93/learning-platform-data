# 12.7 GC root, chuỗi tham chiếu và cách đối tượng bị giữ lại

## Mục tiêu của bài

Sau bài này, bạn có thể:

1. Giải thích **GC root** là gì và vì sao đường đi từ root tới một object khiến object đó chưa được thu hồi.
2. Đọc một **chuỗi tham chiếu (reference chain)** từ class/static field, thread, biến cục bộ, JNI handle hoặc một object trung gian đến object nghi bị giữ lại.
3. Phân biệt **reachable**, **strongly reachable**, các kiểu tham chiếu yếu và **eligible for GC**; hiểu vì sao object không còn hữu ích cho nghiệp vụ vẫn có thể đang sống.
4. Dùng **Paths to GC Roots**, **Dominator Tree** và **retained size** trong Eclipse Memory Analyzer (MAT) để tìm đối tượng giữ bộ nhớ, tránh kết luận sai từ một đường đi ngắn nhất.
5. Nhận diện các nguyên nhân phổ biến như cache không giới hạn, listener chưa hủy đăng ký, ThreadLocal không dọn, hàng đợi và class loader còn bị giữ.

Trọng tâm: **Java GC tự thu hồi object không còn reachable theo các quy tắc reachability; GC không thể tự biết một object tuy reachable nhưng đã hết giá trị nghiệp vụ.** Vì vậy memory leak trong Java thường là **logical leak**: vẫn có đường tham chiếu giữ object sống ngoài vòng đời mong muốn.

## 1. GC root là gì?

Trong quá trình xác định object sống, bộ thu gom rác của JVM bắt đầu từ tập **GC roots**: các điểm xuất phát được runtime coi là đang sử dụng hoặc bắt buộc duy trì. Từ đó GC đi theo các quan hệ tham chiếu phù hợp để tìm các object reachable. Một object có đường tham chiếu **mạnh** từ root thường được giữ lại. Nếu không còn đường giữ sống tương ứng thì object đủ điều kiện để được thu hồi theo cơ chế GC.

Các nguồn root thường gặp trong Java HotSpot và các công cụ heap-analysis:

| Nhóm root | Ngữ cảnh điển hình | Dấu vết có thể gặp khi phân tích |
| --- | --- | --- |
| Thread/stack | Reference đang sống trong local variable, parameter hoặc frame đang chạy; thông tin về thread đang hoạt động | Thread, Java local, stack frame |
| Class và static state | Lớp đang được giữ sống, các static field trỏ tới object; tính reachability chịu ảnh hưởng bởi vòng đời class/class loader | System Class, class object, static field |
| JNI | Native code đang giữ **JNI global reference** hoặc một local reference còn hiệu lực | JNI Global, JNI Local |
| Runtime-internal | Một số đối tượng đặc biệt JVM cần giữ trong lúc thực thi, ví dụ các tham chiếu gắn với thread hoặc cơ chế runtime | Root type phụ thuộc JVM, phiên bản và định dạng dump |

**Không có danh sách nhãn GC root cố định cho mọi JVM, mọi bộ gom rác và mọi heap dump.** Tên root trong MAT là cách diễn giải metadata của bản dump. Đừng coi mọi chi tiết trong một công cụ là quy tắc áp dụng cho mọi VM.

Một static field **không tự nó là câu trả lời đầy đủ** cho vòng đời object: hãy kiểm tra class có còn được giữ sống, class loader có thể unload không, và có root nào giữ class loader đó không. Với ứng dụng chạy lâu, static cache thường sống trong suốt đời class loader; trong ứng dụng plugin/redeploy, một class loader cũ cũng có thể bị giữ lại bởi thread, ThreadLocal hoặc callback.

## 2. Chuỗi tham chiếu: vì sao object vẫn reachable?

Hãy hình dung các đối tượng Java là **đỉnh** trong đồ thị và mỗi trường tham chiếu/mục trong array là **cạnh có hướng**.

~~~text
GC ROOT (class còn được giữ sống)
    |
    | static CACHE
    v
CacheRegistry
    |
    | entries
    v
HashMap
    |
    | table / entry / value  (đường thực tế tùy JDK)
    v
CachedResponse
    |
    | payload
    v
byte[] (dữ liệu lớn)
~~~

Đây là **đồ thị minh họa ý nghĩa**, không phải tên trường nội bộ bắt buộc của mọi bản JDK. Mỗi cạnh nói rằng object phía trước đang giữ tham chiếu đến object phía sau. Chỉ cần một đường giữ sống thích hợp từ GC root tới mảng byte, GC chưa thể thu hồi mảng như rác.

Đọc một đường từ dưới lên:

- **Đối tượng đích**: mảng byte đang chiếm heap.
- **Người giữ trực tiếp**: CachedResponse.payload.
- **Vật chứa**: entry/value trong cache Map.
- **Đầu mối sống lâu**: Registry được tham chiếu qua static field.
- **GC root**: trạng thái class/class loader hoặc một runtime root tương ứng.

Đường đi trả lời câu hỏi **“ai đang khiến object này còn reachable tại thời điểm chụp?”** Nó chưa trả lời được **“đây có phải memory leak không?”**. Một cache có giới hạn và chính sách hết hạn hợp lệ vẫn có thể là đường giữ sống hoàn toàn đúng thiết kế.

### Có tham chiếu không đồng nghĩa với giữ sống mạnh

Không phải mọi cạnh có cùng ý nghĩa. Java cung cấp **strong, soft, weak, phantom references**. Khi nói “có đường từ GC root” trong điều tra leak thông thường, điều cần tìm nhất là **đường tham chiếu mạnh**, hoặc ít nhất hiểu rõ mức reachability theo loại tham chiếu. Một đường chỉ đi qua referent của WeakReference không có tác dụng ngăn GC thu hồi referent giống như một strong reference.

## 3. Các mức reachability và thời điểm object có thể được thu hồi

### Strong reference

Phép gán thông thường, phần tử trong collection hoặc trường object thường tạo strong reference:

~~~java
byte[] payload = new byte[1024];
List<byte[]> list = new ArrayList<>();
list.add(payload);
payload = null;
~~~

*Đây là đoạn minh họa đặt trong một method có import java.util.List và java.util.ArrayList, không phải chương trình độc lập.* Sau khi biến payload được gán null, **list vẫn giữ strong reference** đến mảng. Vì vậy việc xóa **một biến** không có nghĩa object đã không còn reachable.

Cũng cần chú ý: **biến local không giữ object sống trong suốt phạm vi cú pháp một cách máy móc**. JVM/JIT có thể xác định lần sử dụng cuối và tối ưu liveness; compiler có thể giữ hoặc loại một tham chiếu khỏi vị trí stack tại điểm GC. Khi dựa vào thread-stack roots từ heap dump, hãy xem đó là trạng thái thực tế VM ghi nhận lúc chụp, không suy ra chính xác chỉ bằng dấu ngoặc nhọn trong source.

### SoftReference

Một object chỉ còn được tham chiếu qua **SoftReference** có thể được VM giữ tạm và thu hồi tùy chính sách/áp lực bộ nhớ. Soft reference có thể giúp tạo cache nhạy cảm với bộ nhớ, nhưng **không thay thế chính sách giới hạn dung lượng, TTL, eviction**. Thời điểm referent bị clear không mang tính tất định từ phía ứng dụng.

### WeakReference

Khi object chỉ còn weakly reachable, GC có thể clear WeakReference và thu hồi referent; bản thân WeakReference có thể vẫn đang được giữ sống như một object độc lập. **WeakReference không biến một strong reference ở nơi khác thành weak**.

~~~java
WeakReference<Object> weak = new WeakReference<>(new Object());
// Sau một lần GC phù hợp, weak.get() có thể là null.
// Không được dùng System.gc() rồi mặc định chắc chắn weak.get() == null.
~~~

*Đây là đoạn minh họa cần import java.lang.ref.WeakReference, không có bảo đảm về thời điểm GC.*

### PhantomReference

**PhantomReference** hỗ trợ cơ chế thông báo/hậu xử lý thông qua ReferenceQueue; phương thức get() luôn trả về null. Nó không được dùng như strong reference để đọc lại referent, và không bảo đảm thu hồi ngay. Với tài nguyên cần đóng đúng hạn, ưu tiên **try-with-resources/close** thay vì trông chờ GC.

### Bảng chẩn đoán

| Tình trạng từ góc nhìn phân tích | Kết luận đúng |
| --- | --- |
| Có ít nhất một đường **strong** từ root tới object | Object vẫn strongly reachable; GC chưa thể xem như rác |
| Chỉ còn đường qua WeakReference referent | Có thể trở thành weakly reachable và được GC xử lý; cạnh weak không giữ sống như strong |
| Chỉ còn tham chiếu soft | VM có thể giữ tạm hoặc clear tùy điều kiện; không được tự gán thời điểm thu hồi |
| Không còn đường reachability có ý nghĩa | Object có thể đủ điều kiện thu hồi, nhưng không có bảo đảm nó đã được reclaim ngay lập tức |
| Có nhiều đường strong độc lập | Bỏ một tham chiếu thường **chưa đủ** để thu hồi object |

Tùy loại và thứ tự xử lý reference, **“không có strong path”** chưa phải đồng nghĩa với **“đã được giải phóng”**. Trong heap dump lấy với chế độ bao gồm cả unreachable object, bạn còn có thể thấy object đáng lẽ sẽ bị GC dọn ở lần xử lý thích hợp.

## 4. Một object có thể bị nhiều đường giữ cùng lúc

Giả sử một Response được giữ bởi cả cache lẫn một tác vụ nền:

~~~text
        GC Root: class                   GC Root: worker thread
              |                                    |
              v                                    v
       static CACHE                         running task
              |                                    |
              v                                    v
            Map                               queue/item
              |                                    |
              +-------------> Response <------------+
                                   |
                                   v
                                byte[]
~~~

Nếu chỉ **CACHE.remove(key)** mà worker vẫn giữ Response, byte[] vẫn reachable. Ngược lại, tác vụ kết thúc nhưng cache chưa evict thì object vẫn sống. Kết luận “đã sửa leak” yêu cầu kiểm tra **mọi đường giữ quan trọng** và vòng đời nghiệp vụ.

### Vòng tham chiếu không tự tạo leak

~~~text
 A -> B
 ^    |
 |____|
~~~

Nếu **không có GC root nào đi tới A hoặc B**, chu trình này vẫn có thể được tracing GC thu hồi. Garbage collector hiện đại không chỉ đếm số reference như một bộ đếm đơn giản. Vì vậy “có cycle” **không đủ** chứng minh leak; điều quyết định là **tính reachable từ roots** theo mô hình GC.

### Reachable khác với còn cần thiết

Ví dụ một người dùng đã đăng xuất, nhưng HttpSession cũ vẫn bị giữ trong Map không có expiration; object vẫn strongly reachable dù nghiệp vụ không cần. Vấn đề nằm ở **chính sách ownership/lifecycle**, không phải GC “quên” thu hồi.

## 5. Paths to GC Roots và Dominator Tree là hai loại câu hỏi khác nhau

### Paths to GC Roots: ai đang giữ object?

Trong **Eclipse Memory Analyzer (MAT)**, chọn object nghi vấn rồi chạy **Path to GC Roots** hoặc **Path to GC Roots → exclude weak/soft references** tùy phiên bản giao diện. Công cụ đi **ngược** từ object lên các object chứa reference, cuối cùng tới root. Một đường cụ thể có thể giống:

~~~text
byte[] payload
 <- CachedResponse.payload
 <- Map entry.value
 <- CacheRegistry.responses
 <- GcRootDemo.REGISTRY (static)
 <- class / root liên quan
~~~

Tên các bước và số tầng thực tế có thể khác theo JVM, JDK, kiểu collection và đường đi được chọn.

- **Shortest path** là đường ngắn nhất theo số cạnh qua đồ thị đang phân tích; không có nghĩa đó là đường duy nhất hay nguyên nhân đáng sửa nhất.
- **All paths** có thể rất nhiều và tốn tài nguyên. Nên lọc/giới hạn khi cần; nếu chỉ mở một đường, đừng kết luận các đường khác không tồn tại.
- **Exclude weak/soft/phantom references** (tùy lựa chọn của MAT) giúp tập trung vào những quan hệ thường giữ sống mạnh. Cần hiểu cấu hình truy vấn, tránh diễn giải cạnh weak như vật giữ sống không thể GC.
- Cần đọc **tên trường** trên từng cạnh. Một đường tới root qua List hoặc Map có thể hợp lệ hoặc bất thường tùy ai sở hữu dữ liệu và khi nào cần xóa.

### Dominator Tree: object nào kiểm soát retained memory?

MAT dùng một **đồ thị dominator** được suy ra từ đồ thị tham chiếu. Object **X dominates Y** nếu **mọi đường** từ (siêu)root của đồ thị đến Y đều đi qua X. Nếu bỏ X khỏi đồ thị giữ sống, Y không còn reachable theo mô hình đó.

**Retained set** của X gồm các object X dominates; **retained size** là tổng shallow size của tập này (theo cách công cụ tính). Đây là chỉ số giúp tìm đầu mối giữ nhiều dữ liệu nhất.

Một tình huống minh họa:

~~~text
Root -> CacheHolder -> Object A -> byte[]  (20 MB)
                  \-> Object B -> byte[]  (30 MB)
~~~

Nếu **mọi đường** tới hai mảng đều đi qua CacheHolder, retained size của CacheHolder có thể gần 50 MB cộng overhead các object khác, dù **shallow size của CacheHolder rất nhỏ**.

Nếu một mảng còn đường khác từ root qua queue, CacheHolder có thể **không dominate mảng đó**, nên retained size của CacheHolder giảm, mặc dù cache **vẫn trực tiếp tham chiếu tới mảng**.

**Cạnh trong dominator tree không nhất thiết là cạnh reference thật trong Java.** Muốn biết field/collection nào tạo tham chiếu, quay lại **Paths to GC Roots** hoặc xem các incoming/outgoing references. Không nên diễn giải nhầm cạnh “immediate dominator” thành một field tồn tại trong source.

### So sánh hai thao tác

| Thao tác | Trả lời | Điểm dễ hiểu sai |
| --- | --- | --- |
| Paths to GC Roots | Object còn sống qua đường root → ... → object nào? | Một đường không đại diện tất cả đường |
| Merge Shortest Paths to GC Roots | Nhiều object nghi vấn cùng đi qua root/owner nào? | Đường ngắn nhất có thể bỏ sót đường khác |
| Dominator Tree | Object nào giữ độc quyền các tập object lớn? | Cạnh dominator không nhất thiết là reference trực tiếp |
| Histogram | Class nào có nhiều instance/shallow bytes? | Không chỉ ra owner/root và không đo retained size |
| Leak Suspects | Nhóm object đáng xem trước theo heuristic | Là giả thuyết, cần xác minh vòng đời nghiệp vụ |

## 6. Ví dụ chạy được: static listener registry giữ object sau khi biến local bị bỏ

Chương trình bên dưới giữ một listener trong **static List**. Listener sở hữu một mảng byte 1 MiB. Biến local **listener** được gán null, nhưng object chưa thể thu hồi vì registry vẫn chứa nó. Một **WeakReference** được dùng để quan sát tính reachable ở thời điểm có strong reference, không làm tăng khả năng giữ sống của object.

Lưu thành file **GcRootDemo.java**:

~~~java
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.List;

public final class GcRootDemo {
    private static final List<Listener> REGISTRY = new ArrayList<>();

    private static final class Listener {
        private final String id;
        private final byte[] payload;

        private Listener(String id) {
            this.id = id;
            this.payload = new byte[1024 * 1024];
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Listener listener = new Listener("payment-events");
        REGISTRY.add(listener);

        WeakReference<Listener> observation = new WeakReference<>(listener);
        listener = null;

        System.out.println("Registry size: " + REGISTRY.size());
        System.out.println("Weak referent present: " + (observation.get() != null));

        // Giữ tiến trình chạy để có thời gian chụp heap.
        Thread.sleep(180_000L);

        REGISTRY.clear();
        System.out.println("Registry after clear: " + REGISTRY.size());
    }
}
~~~

Lệnh chạy với JDK 17+:

~~~bash
javac GcRootDemo.java
java -Xmx128m GcRootDemo
~~~

Đầu ra được bảo đảm trước khi ngủ:

~~~text
Registry size: 1
Weak referent present: true
~~~

Sau khoảng ba phút (nếu không dừng tiến trình), in tiếp:

~~~text
Registry after clear: 0
~~~

Tại thời điểm in dòng thứ hai, **REGISTRY.get(0)** vẫn là strong reference, vì thế WeakReference.get() chắc chắn không null. Đừng diễn giải đoạn code này như lời hứa rằng WeakReference.get() **sẽ** bằng null ngay sau REGISTRY.clear(); GC không chạy đúng một thời điểm dự đoán được, và các local/JIT roots khác có thể còn tồn tại.

### Chụp heap và tìm đường root

Trong lúc chương trình đang ngủ, mở terminal thứ hai:

~~~bash
jcmd -l
jcmd <PID> GC.heap_dump heap-root-demo.hprof
~~~

Thay **PID** bằng process ID từ lệnh đầu tiên; không gõ dấu ngoặc nhọn ví dụ. Với HotSpot, lệnh **GC.heap_dump** thông thường yêu cầu Full GC trước khi tạo file, trừ khi chọn **-all**. Đây là thao tác có chi phí cao, nên ví dụ chỉ nên chạy trên JVM thử nghiệm.

Mở **heap-root-demo.hprof** bằng MAT:

1. Mở **Histogram** rồi lọc class **GcRootDemo$Listener** hoặc mảng byte liên quan.
2. Chọn instance Listener, mở **Path to GC Roots**, ưu tiên tùy chọn loại weak/soft references khi điều tra giữ sống mạnh.
3. Tìm một chuỗi tham chiếu đại ý: class **GcRootDemo** → static **REGISTRY** → ArrayList backing array → Listener → payload byte[]. Tên node thực tế có thể khác.
4. Mở **Dominator Tree** và xem retained size của listener/registry hoặc chủ sở hữu liên quan. Kiểm tra có các đường tới mảng qua owner khác không.
5. Đối chiếu với thiết kế: listener đáng lẽ phải đăng ký lâu dài hay phải **unregister** khi không dùng nữa?

**Bằng chứng có thể rút ra:** gán biến local bằng null **không loại bỏ** strong reference đang nằm trong collection. Khi ứng dụng xóa registry và không còn đường giữ mạnh nào khác, object trở thành ứng viên thu hồi; việc thu hồi thực tế phụ thuộc GC.

> Cẩn thận với tên field trong các snapshot: nhiều collection và tối ưu JVM có cấu trúc nội bộ thay đổi giữa các phiên bản. Luôn kiểm tra cạnh reference được công cụ trình bày, không dựa vào giả định từ source để viết ra một path “chính xác tuyệt đối”.

## 7. Năm kiểu giữ object ngoài ý muốn cần nhận diện

### 7.1 Static cache không có giới hạn

~~~text
GC root → class còn sống → static cache → Map entry → object đã hết hạn
~~~

Dấu hiệu: số entry và retained heap tăng theo lượng request, không giảm khi tải trở về bình thường. Cách xử lý: **bounded cache, TTL, eviction, invalidate theo lifecycle**; kiểm tra cả cached keys có giữ value hoặc context lớn không. Đừng chỉ gọi GC nhiều hơn.

### 7.2 Listener/callback không unregister

~~~text
Root → long-lived event bus → listeners → callback → captured service/context
~~~

Dấu hiệu: component đã đóng nhưng listener vẫn trong event bus. Fix: quản lý **subscription/registration token** và hủy đăng ký khi component kết thúc. Lambda có thể capture object theo biến, khiến vòng đời owner kéo dài hơn dự kiến.

### 7.3 ThreadLocal trên thread pool

~~~text
Root → worker thread sống lâu → ThreadLocalMap → value → request/session data
~~~

Thread pool tái sử dụng thread, vì vậy value có thể sống qua nhiều request. Nếu một ThreadLocal key bị GC, **value cũ vẫn có thể tồn tại trong map một thời gian** cho tới khi các mục stale được dọn; không nên xem đây là cơ chế cleanup có thời hạn.

Mẫu sử dụng an toàn khi mỗi tác vụ có quyền sở hữu dữ liệu:

~~~java
private static final ThreadLocal<byte[]> BUFFER = new ThreadLocal<>();

static void doWork() {
    try {
        BUFFER.set(new byte[64 * 1024]);
        // Xử lý tác vụ hiện tại.
    } finally {
        BUFFER.remove();
    }
}
~~~

*Đoạn minh họa là hai thành viên cần đặt trong một class; đây không phải chương trình Java độc lập.* Trong pool, **finally + remove** là điểm quan trọng. Việc xóa key từ biến của ứng dụng không bảo đảm value sẽ biến mất tức thì.

### 7.4 Queue/executor tích đọng

~~~text
Root → Executor / scheduler → queue → pending Runnable → captured payload
~~~

Dấu hiệu: lượng job chờ tăng, queue giữ request buffer lớn. Các object này vẫn hợp lệ theo reference graph, nhưng có thể là tình trạng **backlog** hoặc thiết kế queue không có giới hạn. Cần backpressure, bounded queue, timeout, hủy công việc và giám sát số job chờ.

### 7.5 Class loader và JNI global reference

- **Class loader cũ** có thể bị thread, context class loader, static registry, listener hoặc ThreadLocal ở tầng cha giữ sống; khi đó class và dữ liệu gắn với loader khó được giải phóng sau redeploy. Đừng nghĩ “đã bỏ biến module” là đủ nếu loader vẫn có đường strong tới root.
- **JNI global reference** từ native code là một cơ chế giữ Java object sống; native code cần **DeleteGlobalRef** đúng vòng đời. **JNI weak global reference** có ngữ nghĩa yếu hơn và không tương đương strong global reference.
- Heap dump có thể chỉ cho thấy root kiểu JNI hoặc class loader mà không giải thích toàn bộ trách nhiệm phía native; cần đối chiếu mã native/JNI và runtime để kết luận.

## 8. Quy trình điều tra từng bước, tránh kết luận vội

### Bước 1. Xác định đúng biểu hiện

Quan sát **used heap sau các GC có thể so sánh**, mức tải, allocation rate và số object theo thời gian. Heap tăng giữa các lần GC là bình thường. Rò rỉ đáng ngờ khi dữ liệu sau GC hoặc retained sets tăng kéo dài dù vòng đời của chúng đáng lẽ đã kết thúc.

### Bước 2. Chụp dữ liệu đủ điều kiện

Với JDK HotSpot hỗ trợ jcmd:

~~~bash
jcmd -l
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump /path/to/app.hprof
~~~

- **Histogram** khoanh vùng class tăng bất thường.
- **Heap dump HPROF** chứa đồ thị object tại một thời điểm để MAT phân tích root paths, dominators và retained size.
- Lệnh **GC.heap_dump -all** có thể bao gồm các object không còn reachable và **không yêu cầu Full GC trước dump**. Không trộn kết quả dump -all với dump mặc định rồi kết luận khác biệt là leak.
- Việc dump có thể gây pause, tốn tài nguyên, tốn đĩa và chứa dữ liệu nhạy cảm như token, payload hoặc chuỗi. Thu thập và chia sẻ theo quy định an toàn của môi trường thực tế.

### Bước 3. Chọn object nghi vấn đúng cách

Trong MAT, bắt đầu bằng **Overview → Histogram, Dominator Tree, Top Consumers hoặc Leak Suspects**. Chú ý class ứng dụng, retained size lớn, số lượng instance bất thường và owner sống lâu. Một object khổng lồ không nhất thiết là thủ phạm gốc nếu object đó đang được giữ hợp lệ.

### Bước 4. Lần chuỗi tham chiếu lên GC roots

Đi từ **object đích** lên các owner trong **Paths to GC Roots**. Ghi lại:
- Root type và vòng đời root (thread, class/static, JNI).
- Các trường hoặc collection đang tạo **cạnh tham chiếu**.
- Weak/soft/phantom edge có bị loại khi chạy truy vấn không.
- Có bao nhiêu đường giữ mạnh độc lập; nếu một đường bị cắt, các đường khác còn không.

Khi rất nhiều object cùng bị giữ, sử dụng **Merge Shortest Paths to GC Roots** để tìm owner/accumulation point chung, rồi xác thực qua incoming references. Không coi shortest path là tất cả đường có thể.

### Bước 5. Kiểm tra dominator và kích thước giữ lại

Nếu một owner dominates nhiều object, retained size sẽ cho biết lượng heap có thể trở thành unreachable nếu owner đó bị loại khỏi đồ thị giữ sống. Ngược lại, một owner có ít retained size vẫn có thể tham chiếu tới nhiều object **chia sẻ** với owner khác.

### Bước 6. Ghép với vòng đời nghiệp vụ

Hỏi cụ thể:

- Object được tạo khi nào, hợp đồng sử dụng bao lâu?
- Ai đăng ký/đưa object vào Map, List, queue hoặc ThreadLocal?
- Bước nào có trách nhiệm remove, evict, unregister hoặc close?
- Có key/value tồn tại vĩnh viễn do lỗi hủy tác vụ hoặc retry không?
- Một request/job đã kết thúc nhưng object còn được giữ vì hoạt động hợp lệ khác không?

Sau sửa, đo lại bằng tải đại diện và các lần chụp tương đương. **Không kết luận từ một snapshot đơn lẻ** hoặc chỉ từ System.gc(); phải xác nhận retained graph và xu hướng biến đổi phù hợp.

## 9. Những bẫy suy luận thường gặp

1. **“Bỏ biến local bằng null thì object được giải phóng.”** Không đúng khi List, static field, thread, callback hoặc JNI vẫn có strong reference.
2. **“Có reference cycle là có leak.”** Sai: cycle không reachable từ root vẫn có thể được tracing GC thu hồi.
3. **“Path ngắn nhất là root gây leak duy nhất.”** Sai: object có thể được giữ bởi nhiều root/owner độc lập.
4. **“Mọi cạnh xuất hiện trong dump đều là strong reference.”** Sai: weak, soft, phantom và một số liên kết đặc biệt cần diễn giải theo ngữ nghĩa reachability.
5. **“Retained size là tổng shallow size của mọi object có thể đi tới từ owner.”** Sai nếu có những object còn được giữ bởi đường khác và owner không dominates chúng.
6. **“Cạnh trên Dominator Tree là field tham chiếu trực tiếp.”** Sai: dominator tree là kết quả phân tích graph, không phải bản sao những trường object trong Java.
7. **“Một static field luôn gây leak và không bao giờ được giải phóng.”** Sai: phải xét vòng đời class/class loader và nhu cầu dữ liệu; static không mặc nhiên là lỗi.
8. **“Không thấy root path trong một dump nghĩa là object đã bị GC.”** Chưa chắc: bộ phân tích có thể có tùy chọn bỏ cạnh/giới hạn path, dump -all có unreachable object và thời điểm dump khác thời điểm reclaim.
9. **“Chỉ cần thêm WeakReference để sửa mọi leak.”** Sai: nếu vẫn có strong path, WeakReference không thay đổi việc object được giữ; thay đổi kiểu reference còn phải phù hợp hợp đồng ứng dụng.
10. **“Object reachable là object cần thiết.”** Sai: GC không biết TTL, nghiệp vụ hay việc listener đáng lẽ đã được unregister.

## 10. Tự kiểm tra

**Tình huống 1:** một service giữ 200 MB dữ liệu qua static Map, đã gọi method kết thúc phiên làm việc nhưng không xóa Map entry. Vì sao GC không dọn?  
**Đáp án:** class/static → Map → entry → dữ liệu vẫn là chuỗi tham chiếu mạnh từ root. Cần xóa/evict entry theo lifecycle rồi xác minh không có đường mạnh khác.

**Tình huống 2:** hai static Map độc lập cùng giữ một byte[] 30 MB. Xóa một Map có đủ không?  
**Đáp án:** không; đường từ Map còn lại vẫn khiến object reachable. Dominator/retained size của từng Map có thể không tính toàn bộ mảng vì nó được chia sẻ.

**Tình huống 3:** A trỏ B và B trỏ A, nhưng cả hai không còn reachable từ bất kỳ GC root nào. Chúng có leak chỉ vì cycle không?  
**Đáp án:** không. Tracing GC có thể thu hồi cả chu trình.

**Tình huống 4:** MAT chỉ hiển thị đường tới object thông qua WeakReference. Bạn có thể kết luận object sẽ mãi còn sống không?  
**Đáp án:** không. Phải kiểm tra có strong path khác và hiểu chế độ loại weak references trong truy vấn; weak edge không giữ referent như strong edge.

**Tình huống 5:** một owner có outgoing references tới 100 MB dữ liệu nhưng retained size chỉ 4 MB. Có mâu thuẫn không?  
**Đáp án:** không. Nhiều object được tham chiếu có thể vẫn được giữ sống qua các owner khác; retained size đo phần bị dominate.

## Tài liệu tham khảo

- [Oracle Java SE 21 — java.lang.ref package: cấp độ reachability và Reference Objects](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/package-summary.html)
- [Oracle JDK 21 — jcmd: GC.heap_dump, GC.class_histogram](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — Diagnostic Tools: thu thập heap dump và histogram](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [Eclipse MAT — Basic Tutorial: Dominator Tree và Path to GC Roots](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html)
- [Eclipse MAT — Path to GC Roots](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/path_to_gc_roots.html)
- [Eclipse MAT — Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html)
- [Eclipse MAT — Merge Shortest Paths](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/merge_shortest_paths.html)
