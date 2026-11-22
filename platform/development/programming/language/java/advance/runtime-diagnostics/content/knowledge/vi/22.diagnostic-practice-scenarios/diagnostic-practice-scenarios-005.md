# 22.5. Tái hiện giữ tham chiếu trong collection và lần theo GC root trong heap dump

Một chương trình Java có thể tiếp tục dùng nhiều heap dù các request đã hoàn tất, không phải vì Garbage Collector (GC) “không chạy”, mà vì **một collection vẫn giữ strong reference** đến những object không còn cần cho nghiệp vụ. Khi các object còn **reachable** từ GC root, GC không được phép thu hồi chúng. Muốn điều tra đúng, cần đi từ hiện tượng bộ nhớ tăng đến **chuỗi tham chiếu cụ thể** nối object đang chiếm bộ nhớ với một GC root.

Bài thực hành này tái hiện có kiểm soát một `static HashMap` giữ 64 object, mỗi object sở hữu mảng `byte[]` dung lượng 256 KiB. Ta sẽ tạo **hai heap dump HPROF** ở các trạng thái khác nhau của **cùng một JVM**:

1. **RETAINED:** các object nằm trong `HashMap` và còn được giữ bởi static field.
2. **RELEASED:** gọi `HashMap.clear()`, loại strong reference của map đến những object đó; tiếp tục chụp heap dump chỉ gồm object còn sống.

Sau đó dùng **Eclipse Memory Analyzer (MAT)**: Histogram → Dominator Tree → Path To GC Roots để tìm chính xác **ai giữ object sống**, rồi so sánh ảnh chụp trước/sau. Ví dụ dùng Java 17+ và công cụ JDK; lệnh heap dump chỉ chạy trên JVM lab riêng. Không thực hiện heap dump nặng trên dịch vụ thật khi chưa đánh giá chi phí và quyền truy cập.

## 1. Tư duy căn bản: object được cấp phát khác object được giữ lại

Các khái niệm cần tách rõ:

- **Allocation:** chương trình tạo object mới trên heap, chẳng hạn `new byte[262144]`. Allocation cao chưa đồng nghĩa memory leak, vì object ngắn hạn có thể được thu hồi.
- **Reachability:** một object còn được coi là sống nếu có **đường strong reference** từ GC root đến nó. Các đường chỉ qua weak/soft/phantom references có ngữ nghĩa thu gom khác và cần phân tích riêng.
- **GC root:** điểm xuất phát mà JVM coi là gốc của đồ thị object sống, chẳng hạn các static fields của class reachable, Java thread, local variables còn sống trong stack, JNI global references và một số cấu trúc JVM.
- **Retention:** object vẫn được giữ qua một hoặc nhiều chu kỳ GC vì có đường tham chiếu tồn tại.
- **Memory leak ở Java:** logic ứng dụng giữ reference đến dữ liệu **không còn cần nữa**, khiến bộ nhớ không được thu hồi; không nhất thiết là mất khả năng quản lý bộ nhớ như trong native code.
- **Heap dump HPROF:** snapshot của object graph, class, field, references và thông tin root tại một thời điểm. Nó giải thích **ai đang giữ gì**, không tự cho biết tất cả object đã sống bao lâu hoặc khi nào được cấp phát.

Một object chỉ có thể được GC thu hồi sau khi không còn reachable theo ngữ nghĩa reference/GC tương ứng. Vì vậy, **gọi `System.gc()` không sửa được việc collection còn giữ strong references**. JVM cũng không bảo đảm yêu cầu `System.gc()` sẽ thực hiện một GC ngay lập tức trong mọi cấu hình.

### Strong reference từ collection thường xuất hiện thế nào?

~~~text
GC Root (class được JVM giữ sống)
    |
    v
static field CollectionRootLab.CACHE
    |
    v
java.util.HashMap
    |
    v
HashMap.table (mảng HashMap$Node[])
    |
    +-- HashMap$Node(key=0, value=RetainedValue@...)
    |                                 |
    |                                 +-- RetainedValue.payload
    |                                              |
    |                                              v
    |                                          byte[262144]
    |
    +-- HashMap$Node(key=1, value=RetainedValue@...)
    |                                 |
    |                                 +-- byte[262144]
    |
    +-- ... còn 62 entry nữa
~~~

Đây là **mô hình tham chiếu logic**, không phải văn bản MAT bảo đảm hiển thị đúng từng dòng. Tên field nội bộ, kiểu node và hình thức hiển thị GC root phụ thuộc JDK và parser. Điểm quan trọng là: **static field → map → internal node → value → byte[]**. Chỉ một strong reference tới map có thể làm toàn bộ tập value và payload của nó tiếp tục sống.

Với 64 mảng × 256 KiB, tổng dữ liệu **phần tử mảng** là `64 × 262144 = 16.777.216 byte = 16 MiB`. Đây chưa phải tổng retained heap: object headers, references, map table, nodes, keys và alignment cũng chiếm bộ nhớ.

## 2. Phân biệt shallow size và retained size trước khi đọc MAT

**Shallow heap** của object là kích thước bản thân object đó. Ví dụ:

- Một `HashMap` object thường có shallow size tương đối nhỏ vì nó chủ yếu chứa các field như size/table reference.
- Một `byte[262144]` có shallow size lớn hơn 256 KiB một chút khi cộng header/alignment.
- Một `RetainedValue` chỉ chứa `int id` và `byte[] payload` reference nên shallow size nhỏ hơn rất nhiều so với toàn bộ payload.

**Retained heap** của object X là tổng shallow sizes của các object sẽ trở nên không còn reachable nếu **mọi đường giữ tới X** bị loại, theo mô hình dominator/retained set. Một map nhỏ về shallow size có thể **gián tiếp** giữ hàng chục MiB thông qua các values.

| Câu hỏi | Xem trong MAT | Không nên kết luận |
| --- | --- | --- |
| Object này tự chiếm mấy byte? | **Shallow Heap** | Nhầm với toàn bộ bộ nhớ nó khiến JVM giữ lại |
| Bao nhiêu bộ nhớ phụ thuộc riêng vào object này? | **Retained Heap / Retained Set** | Cộng retained size của các node chồng lấn |
| Class nào có nhiều instance? | **Histogram** | Class có số instance lớn chắc chắn là thủ phạm |
| Ai ngăn instance bị GC? | **Path To GC Roots** | Đường ngắn nhất duy nhất là toàn bộ nguyên nhân |
| Object nào thống trị nhiều object khác? | **Dominator Tree** | Mỗi cạnh của dominator tree là một Java field reference thật |

Theo định nghĩa, X **dominates** Y khi mọi đường từ GC roots đến Y phải đi qua X. Cây dominator được suy ra từ toàn bộ object graph; cạnh của cây này **không nhất thiết trùng một reference trực tiếp** trong code. Để nhìn chuỗi field reference thực, dùng **Path To GC Roots**.

Một snapshot với 16 MiB giữ trong cache có thể hoàn toàn đúng thiết kế nếu cache bị giới hạn và còn phục vụ request. Chỉ khi dữ liệu đã hết vòng đời nhưng vẫn được giữ không có cách giải phóng hợp lý, đó mới là **leak** theo nhu cầu ứng dụng.

## 3. Chương trình Java 17+ tái hiện tình huống một cách kiểm soát

Tạo file **`CollectionRootLab.java`** với toàn bộ nội dung:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

public final class CollectionRootLab {
    private static final int ENTRY_COUNT = 64;
    private static final int PAYLOAD_BYTES = 256 * 1024;

    // GC root sẽ dẫn đến class đang sống và static field này.
    private static final Map<Integer, RetainedValue> CACHE = new HashMap<>();

    private static final class RetainedValue {
        private final int id;
        private final byte[] payload;

        private RetainedValue(int id) {
            this.id = id;
            this.payload = new byte[PAYLOAD_BYTES];
            this.payload[0] = (byte) id;
        }
    }

    private static void populate() {
        for (int i = 0; i < ENTRY_COUNT; i++) {
            CACHE.put(i, new RetainedValue(i));
        }
    }

    private static void releaseReferences() {
        // Xóa các entry. Các RetainedValue và byte[] không còn
        // được CACHE trỏ đến sau khi phương thức này trả về.
        CACHE.clear();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 0) {
            throw new IllegalArgumentException("Run without arguments");
        }

        populate();

        BufferedReader input = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Stage=RETAINED");
        System.out.println("Cache entries=" + CACHE.size());
        System.out.println("Capture first dump, then press Enter");

        // Chờ lệnh jcmd ở terminal thứ hai chụp trạng thái RETAINED.
        if (input.readLine() == null) {
            return;
        }

        releaseReferences();
        System.out.println("Stage=RELEASED");
        System.out.println("Cache entries=" + CACHE.size());
        System.out.println("Capture second dump, then press Enter");

        // Chờ lệnh jcmd thứ hai, không tạo tham chiếu tới RetainedValue.
        input.readLine();
        System.out.println("Done");
    }
}
~~~

### Vì sao ví dụ tạo được chuỗi GC root rõ ràng?

- `CACHE` là **static field** trong class `CollectionRootLab`. Khi JVM đang chạy class này, map còn reachable qua class/static state.
- `CACHE.put(i, new RetainedValue(i))` tạo 64 value, mỗi value giữ 1 mảng `byte[]`. Tập mảng payload tổng cộng 16 MiB.
- Phương thức `populate()` kết thúc trước khi main chờ. Object được giữ **không cần** local variables của method này; đường đáng điều tra đi qua `CACHE`.
- `BufferedReader.readLine()` chỉ giữ main thread chờ lệnh từ người dùng. Đây là cơ chế điều phối thực hành, không phải một root trực tiếp của các `RetainedValue`.
- `releaseReferences()` gọi `CACHE.clear()` để xóa các mapping; nó **không** cần sửa dữ liệu trong payload và không cần gọi `System.gc()` để loại bỏ reference.
- Map object và một phần **bộ nhớ capacity** của bảng băm vẫn có thể tồn tại sau `clear()`, vì chính static field `CACHE` vẫn trỏ đến map. Điều sẽ biến mất khỏi *live-object dump* là các `RetainedValue`/payload không còn strong reference.
- Không có vòng lặp cấp phát vô hạn; mục tiêu là tạo hiện tượng retention nhỏ, an toàn cho máy thử nghiệm, không kích hoạt OOM một cách cố ý.

### 3.1. Biên dịch và chạy

Dùng JDK 17+ có `javac`, `java` và `jcmd`, trên máy **không phục vụ production**:

~~~bash
javac CollectionRootLab.java
java -Xms32m -Xmx128m CollectionRootLab
~~~

Khi main đang dừng ở giai đoạn thứ nhất, stdout do chương trình in:

~~~text
PID=<PID thực tế do hệ điều hành cấp>
Stage=RETAINED
Cache entries=64
Capture first dump, then press Enter
~~~

`PID` là một số nguyên động; các dòng khác cố định nếu chương trình khởi động bình thường. JVM hiện đang chờ **Enter** tại terminal A, nên đủ thời gian chụp heap dump lần một. Không bấm Enter trước khi lần chụp thứ nhất hoàn tất.

**Lưu ý quan trọng:** output tên PID ở đây không phải nội dung để copy nguyên dạng vào shell. Lệnh `jcmd` phải dùng PID thật của **tiến trình lab đang sống**.

## 4. Chụp HPROF lần một khi collection vẫn giữ references

Mở **terminal B** trên cùng host và trong process namespace phù hợp. Với JDK 21, `GC.heap_dump` nhận **filename là positional argument**, nên cú pháp thường là:

~~~bash
jcmd -l
jcmd 12345 help GC.heap_dump
jcmd 12345 GC.heap_dump /var/tmp/collection-retained-12345.hprof
~~~

Trong đó **12345 chỉ là PID minh họa**. Trước khi chạy, thay bằng PID được chương trình in và bảo đảm file output mới, đường dẫn `/var/tmp` tồn tại/có quyền ghi cho tiến trình JVM trên Linux/macOS tương ứng. Trên Windows thay bằng đường dẫn thư mục có sẵn như `C:/jfr-lab/collection-retained.hprof`.

Nếu `jcmd -l` không thấy process vì container namespace, kiểm tra PID qua `ps`/công cụ container đúng ngữ cảnh. `jcmd` attach thường cần cùng user/group hiệu lực với JVM. Đường dẫn HPROF được JVM đích mở **trên filesystem nơi JVM chạy**, không phải nơi một terminal từ xa đang mở.

Trên HotSpot JDK 21, `GC.heap_dump` tạo **HPROF Java heap** và được xếp **High impact**. Nếu không dùng `-all`, lệnh yêu cầu **Full GC** trước khi dump để tập trung vào object còn sống. Trong lab này **không dùng `-all`**, vì ta muốn quan sát retention sau khi GC có cơ hội loại những object không reachable.

Chờ command kết thúc thành công. Kiểm tra file ở đúng host/volume:

~~~bash
ls -lh /var/tmp/collection-retained-12345.hprof
~~~

Kích thước file không phải phép đo chính xác retained heap: định dạng HPROF chứa metadata, references, class records và các object khác trong JVM. Không nên dự đoán trước file phải lớn đúng 16 MiB.

### Rủi ro của heap dump thật

Dù ít rủi ro hơn `jhsdb` live SA attach trong nhiều tình huống, heap dump vẫn có thể dừng JVM đáng kể, chạy GC, dùng CPU/I/O, tạo file rất lớn, gây disk full và chứa secrets/PII. **Chỉ thực hành trên JVM disposable/lab.** Khi vận hành thật, cần ước lượng heap, quota, thời gian pause, quyền attach, vùng chứa file và kế hoạch bảo vệ dữ liệu.

## 5. Chụp HPROF lần hai sau khi loại reference

Quay lại terminal A và **nhấn Enter đúng một lần**. Chương trình chạy `releaseReferences()`, in:

~~~text
Stage=RELEASED
Cache entries=0
Capture second dump, then press Enter
~~~

Trong terminal B, dùng chính PID lúc trước nhưng **tên file khác**:

~~~bash
jcmd 12345 GC.heap_dump /var/tmp/collection-released-12345.hprof
ls -lh /var/tmp/collection-released-12345.hprof
~~~

Lúc này `CACHE.size() == 0`. Với cơ chế mặc định chỉ dump live objects, các `CollectionRootLab$RetainedValue` và mảng payload do chúng sở hữu **thường không còn xuất hiện như object reachable** trong HPROF thứ hai, vì không còn đường giữ chúng từ static map. Các mảng `byte[]` của JVM/JDK khác vẫn tồn tại, nên **không** kỳ vọng toàn bộ `byte[]` biến mất khỏi histogram.

Sau khi lệnh thứ hai hoàn tất, nhấn Enter ở terminal A để chương trình in:

~~~text
Done
~~~

**Không dùng cùng tên file cho hai snapshot.** JDK 21 mặc định không ghi đè heap dump đã có (trừ khi dùng tùy chọn override tương ứng), nên tên file duy nhất giúp tránh mất bằng chứng. Giữ cả hai file trước/sau để so sánh.

### Trường hợp `clear()` không giải phóng object

`clear()` chỉ bỏ các reference bên trong collection đó. Nếu ở nơi khác còn có:

~~~java
// Mảnh minh họa, KHÔNG thuộc CollectionRootLab.java ở trên.
static RetainedValue LAST_VALUE;
LAST_VALUE = someValueFromCache;
CACHE.clear();
~~~

thì `LAST_VALUE` vẫn có thể giữ `RetainedValue` và `byte[]`. Tương tự với `ThreadLocal`, listener registry, callback/closure, task queue, cache thứ hai, static list khác hoặc local variable còn sống. **Không kết luận object chết chỉ vì map đã rỗng**; phải đọc GC roots từ heap dump và kiểm tra mọi strong path còn lại.

## 6. Mở HPROF và tìm nghi phạm trong Eclipse Memory Analyzer

**Eclipse Memory Analyzer (MAT)** là công cụ phân tích heap dump, gồm Histogram, Dominator Tree, Path To GC Roots, Leak Suspects, OQL và so sánh snapshots. Trên máy đủ RAM/CPU, mở:

1. `collection-retained-12345.hprof` — trạng thái RETAINED.
2. `collection-released-12345.hprof` — trạng thái RELEASED.

MAT có thể cần dựng index/parser, tiêu thụ thêm RAM và tạo các file chỉ mục bên cạnh HPROF. Với heap dump lớn, dùng máy phân tích riêng; đừng mở ngay trên máy production đang thiếu bộ nhớ.

### 6.1. Bắt đầu bằng Histogram

Trong snapshot thứ nhất, mở **Histogram** (tên menu/vị trí tùy version MAT). Tìm class:

~~~text
CollectionRootLab$RetainedValue
byte[]
java.util.HashMap
java.util.HashMap$Node
~~~

Kỳ vọng logic khi dump ở trạng thái RETAINED: có **64 instance** `CollectionRootLab$RetainedValue` được map giữ; các instance đó dẫn đến 64 payload arrays mỗi mảng 256 KiB. Histogram `byte[]` tổng sẽ lớn hơn và có nhiều mảng khác từ JVM/JDK.

**Cảnh báo về con số:** MAT có thể hiện class qua package, class loader, tên lồng nhau hoặc grouping khác. Không nên lấy toàn bộ byte-array histogram làm “chính xác 16 MiB bị leak”, vì chỉ một phần `byte[]` thuộc lab. Số class instance, nếu đúng giai đoạn và heap dump hợp lệ, là một dấu hiệu để kiểm tra tiếp.

Trong snapshot thứ hai, tìm lại `CollectionRootLab$RetainedValue`. Nếu không còn instance live của class này hoặc số lượng giảm đúng kỳ vọng, đó là bằng chứng thao tác bỏ reference đã có hiệu quả. Có thể còn class metadata hoặc table của `HashMap`; điều đó **không đồng nghĩa 64 payload vẫn bị giữ**.

### 6.2. Dùng Dominator Tree để thấy “bộ nhớ giữ gián tiếp”

Mở **Dominator Tree**, sắp xếp theo **Retained Heap**. Tìm `CollectionRootLab`, `HashMap`, vùng array `byte[]` hoặc sử dụng **Top Consumers / Big Drops** nếu dữ liệu có nhiều class.

Mục tiêu: nhận diện một **accumulation point** — object/cấu trúc làm nhiều values/payload tiếp tục reachable. `HashMap` có shallow size nhỏ, nhưng retained set của nó có thể chứa các `HashMap$Node`, `RetainedValue` và `byte[]` nếu không có đường strong reference khác đến các object đó.

**Chú ý:** dominator tree phản ánh quan hệ thống trị trong object graph. Có thể thấy retained heap lớn ở class object hoặc collection root, không nhất thiết xuất hiện `HashMap` ngay ở đầu cây do cách sắp xếp. Đừng bỏ cuộc nếu nhìn bảng ban đầu không thấy “16 MiB”.

## 7. Path To GC Roots: lần theo đường giữ object cụ thể

Đây là bước quan trọng nhất để trả lời câu hỏi **“Tại sao GC chưa thu object này?”**.

1. Trong Histogram của snapshot RETAINED, mở nhóm `CollectionRootLab$RetainedValue`.
2. Chọn **một instance** bất kỳ, chẳng hạn instance id=0. Không chọn class definition; phải chọn **object instance**.
3. Nhấp chuột phải, chọn **Path To GC Roots** hoặc **Shortest Paths To GC Roots** (tên lệnh/menu khác nhau tùy phiên bản MAT).
4. Khi có lựa chọn, dùng **Exclude Weak/Soft/Phantom References** để tập trung vào đường giữ mạnh. Trong ví dụ này các liên kết qua `HashMap` là strong, nên không bị loại.
5. Mở rộng cây reference từ root tới instance; nhìn **tên field** hoặc reference label tại từng bước.
6. Lần tiếp từ `RetainedValue.payload` tới một `byte[]` 256 KiB để đối chiếu lượng dữ liệu thực sự được giữ.

Một chuỗi logic kỳ vọng:

~~~text
GC Root: class / system class (CollectionRootLab)
   |
   +-- static CollectionRootLab.CACHE
         |
         +-- java.util.HashMap
               |
               +-- table: HashMap$Node[]
                     |
                     +-- HashMap$Node
                           |
                           +-- value: CollectionRootLab$RetainedValue
                                 |
                                 +-- payload: byte[262144]
~~~

**Đây là cách diễn giải, không phải output MAT cố định.** Đường thực tế có thể đi qua class mirror, class loader, node/table field khác, hoặc hiện nhiều GC roots. MAT chọn một số đường ngắn nhất theo truy vấn; **một đường ngắn không chứng minh đó là đường duy nhất**.

### 7.1. “Path to GC Roots” và “incoming references” khác nhau

- **Incoming references** cho biết object nào **trỏ trực tiếp** tới instance đang chọn. Ví dụ một `HashMap$Node` có field `value` trỏ tới `RetainedValue`.
- **Path To GC Roots** truy ngược *nhiều bước* để xác định reference chain nối object tới GC root. Đây mới là lời giải “vì sao còn sống”.
- **Dominator Tree** giúp đánh giá lượng bộ nhớ phụ thuộc vào một cấu trúc; không yêu cầu mọi cạnh trong cây là field reference trực tiếp.

Một object có thể có nhiều incoming paths. Nếu chỉ gỡ một map nhưng object vẫn nằm trong `ThreadLocal` hoặc static collection khác, MAT sẽ cho thấy **đường root còn lại**. Đây là lý do nên kiểm tra nhiều paths (hoặc merged shortest paths cho một nhóm instances) khi nghi ngờ nhiều owner.

### 7.2. Vì sao loại weak/soft/phantom paths?

Java có các loại reference đặc biệt:

| Reference | Ảnh hưởng cơ bản | Cách đọc trong MAT |
| --- | --- | --- |
| **Strong** | Giữ object reachable bình thường | Phải tìm mọi strong path khiến object còn sống |
| **WeakReference** | Không tự ngăn object bị GC khi chỉ còn weak reachability | Thường loại `referent` yếu khi tìm nguyên nhân leak |
| **SoftReference** | GC có quyền dọn theo chính sách memory pressure | Có thể bỏ qua khi ưu tiên chuỗi strong reference, nhưng vẫn xem nếu cache soft gây áp lực |
| **PhantomReference** | Không cung cấp strong reachability tới referent; chủ yếu hỗ trợ cleanup tracking | Không coi đường phantom là strong owner |
| **Finalizer-related references** | Có thể ảnh hưởng thời gian chết/khả năng cleanup của object | Phân tích riêng, đặc biệt trong chương trình cũ |

Tùy MAT và loại heap dump, truy vấn “exclude weak/soft/phantom/finalizer references” giúp giảm nhiễu. **Không loại tất cả các reference type một cách mù quáng**: nếu vấn đề nằm ở cache dùng `SoftReference` hoặc cleanup queue, chính loại reference đó có thể là nội dung cần điều tra.

## 8. So sánh trước/sau để xác nhận phép sửa

Đặt hai heap dump cạnh nhau và kiểm tra:

| Hạng mục | Snapshot RETAINED | Snapshot RELEASED | Diễn giải |
| --- | --- | --- | --- |
| `CACHE.size()` | 64 | 0 | Code đã xóa mapping |
| `CollectionRootLab$RetainedValue` live instances | Kỳ vọng có 64 | Kỳ vọng không còn instance được map giữ | Kiểm tra retention sau bỏ references |
| `byte[262144]` do lab sở hữu | 64 payload arrays | Không còn bị giữ qua `CACHE` | Đối chiếu qua incoming/paths, không chỉ class `byte[]` |
| `HashMap` object | Có | Vẫn có | Static field vẫn giữ map object |
| `HashMap.table` | Có table chứa nodes | Có thể vẫn có table capacity nhưng entries rỗng | `clear()` không bắt buộc thu nhỏ nội bộ table |
| Retained heap của chủ sở hữu | Có thể chứa ≈16 MiB payload và overhead | Giảm đáng kể | Không đòi dung lượng chính xác bằng 16 MiB |
| Tổng kích thước HPROF | Phụ thuộc toàn JVM | Cũng phụ thuộc toàn JVM | **Không** dùng chênh file size làm retained-size chính xác |

Có hai cách so sánh:

- Mở **Histogram** của cả hai, lọc class `CollectionRootLab$RetainedValue`, so **object count** và shallow heap.
- Dùng tính năng **Compare Snapshots** hoặc so các **Dominator Tree/Leak Suspects** nếu MAT phiên bản đó hỗ trợ. Đảm bảo hai ảnh chụp cùng JVM, cùng cấu hình và đúng thứ tự thời gian.

Quan trọng: HPROF **không lưu thời gian cấp phát của mọi object** và bản thân nó là snapshot. Một lần chụp có 64 object không chứng minh “rò rỉ liên tục”. Thực hành tạo retention có chủ đích; sự giảm sau `clear()` xác nhận nguyên lý reachability, chứ không phải bằng chứng tự động về một lỗi production cụ thể.

## 9. Vì sao gọi GC nhiều lần vẫn không giải quyết retention?

Giả sử chương trình tạo một object và đặt nó trong map:

~~~java
// Minh họa nguyên lý, không phải một file chạy độc lập.
byte[] payload = new byte[1024 * 1024];
sessionCache.put("user-42", payload);
payload = null;
System.gc();
~~~

Việc gán `payload = null` chỉ làm mất **local reference**. `sessionCache` vẫn chứa reference tới cùng mảng. GC không thể thu nó nếu map vẫn reachable từ GC root. Cách giải quyết logic là bỏ entry khi hết vòng đời:

~~~java
// Minh họa nguyên lý, không phải một file chạy độc lập.
sessionCache.remove("user-42");
// Hoặc sessionCache.clear() khi toàn bộ cache được phép xóa.
~~~

Sau khi bỏ reference, object **đủ điều kiện** để được GC thu hồi; không có nghĩa JVM lập tức giảm RSS hoặc trả committed heap về OS. Heap used và memory resident ở OS là hai phép đo khác nhau.

### Khi nào `clear()` vẫn không đủ?

1. **Một collection khác** cũng giữ object; ví dụ `HISTORY.add(value)`.
2. **ThreadLocal** giữ object trong thread pool lâu sống.
3. **Listener/event bus registry** không unsubscribe callback.
4. **Scheduled task hoặc executor queue** giữ closure có capture object.
5. **Static field khác** hoặc class loader bị giữ vì registry/plugin không gỡ.
6. **Local variables trên stack** còn sống tại thời điểm chụp, đặc biệt khi cố chụp ngay trong một method đang giữ tham chiếu.
7. **JNI global references** hoặc native agent giữ object thông qua cơ chế JVM.

Từng trường hợp cần **Path To GC Roots** để xác định owner thật, không suy đoán theo tên class. Một lần gỡ `CACHE` nhưng vẫn thấy object trong snapshot sau có thể là dữ kiện cần điều tra, không phải lý do kết luận GC “không hoạt động”.

## 10. Mở rộng thực hành: tái hiện leak thực tế trong code service

Ứng dụng thật hiếm khi có một dòng `CACHE.put(...)` đơn độc dễ nhận ra. Thường là các nguyên nhân nghiệp vụ:

- **Session cache không có TTL/eviction**: người dùng logout nhưng object vẫn được giữ trong map theo ID.
- **Map key có cardinality không giới hạn**: cache theo request ID hoặc random UUID; mỗi request đều tạo key mới nên cache không reuse được.
- **ConcurrentHashMap** được dùng đúng về thread safety nhưng chưa có chính sách loại entry; concurrent container **không tự giải quyết memory lifecycle**.
- **Listener registry**: mỗi request đăng ký một object callback vào list tĩnh nhưng không unregister.
- **ThreadLocal trong thread pool**: request kết thúc nhưng thread sống lâu; nếu không gọi `remove()` ở `finally`, payload có thể còn được giữ.
- **Queue tồn đọng**: producer nhanh hơn consumer; object giữ trong queue hợp lệ về reachability nhưng vượt khả năng xử lý.

Đặc biệt với `WeakHashMap`: chỉ **key** là weak; value có thể tham chiếu ngược trở lại key, làm key không được thu. Không thay mọi strong map bằng `WeakHashMap` như một “mẹo sửa leak” nếu vòng đời dữ liệu cần được định nghĩa rõ ràng.

### 10.1. Chọn sửa code theo đường root

| Path To GC Roots chỉ ra | Giả thuyết đáng kiểm chứng | Sửa phù hợp |
| --- | --- | --- |
| Static cache → map → old request values | Cache không có eviction/TTL | Giới hạn entry count, TTL/size, cleanup sau lifecycle |
| Thread → ThreadLocalMap → value | Thread pool tái sử dụng thread, quên cleanup | `try/finally` + `ThreadLocal.remove()` |
| EventBus/listener list → callback → owner | Không unregister listener | Token/unsubscribe ở `close()`/`destroy()` |
| Executor queue → Runnable → captured payload | Downstream nghẽn hoặc retry vô hạn | Bounded queue, backpressure, timeout, hủy task |
| Static registry → class loader → classes | Hot redeploy/plugin classloader leak | Gỡ registry, thread, timer, listener thuộc classloader cũ |
| Local stack variable → payload | Snapshot chụp khi method vẫn chạy | Chờ ra khỏi frame, xét lại thời điểm chụp trước khi gọi leak |

Mỗi cách sửa phải được xác minh bằng **tải tương đương** và snapshot/metrics mới: object count/retained set giảm theo nhu cầu, sau GC heap trở về mức ổn định, latency/throughput không xấu đi vì logic eviction.

## 11. Một quy trình điều tra leak có thể áp dụng thực tế

### Bước A — xác định triệu chứng theo thời gian

Quan sát heap used **sau GC**, GC log/JFR, `-Xmx`, container RSS, throughput và loại request. Một cache warm-up hợp lệ có thể làm memory tăng một lần rồi ổn định; đây khác với đường đáy heap tiếp tục tăng trong điều kiện tải ổn định.

### Bước B — lấy snapshot đúng thời điểm, trong ngân sách an toàn

Ưu tiên staging/canary có thể tái hiện. Nếu cần production dump, `GC.heap_dump` có **High impact** và thường làm Full GC; tính trước pause, file size, I/O, quyền và bảo vệ PII. Đừng gọi nhiều lần mỗi phút không có kế hoạch. Không dùng `-all` nếu đang cần kiểm tra *live reachable objects* trong một phép so sánh retention.

### Bước C — bắt đầu từ vùng nhớ lớn

Trong MAT xem **Overview, Histogram, Top Consumers và Dominator Tree**. Đừng chỉ nhìn class `byte[]`: nó thường xuất hiện rất nhiều ở Java application; cần xem ai **owns** các mảng và phần lớn retained size.

### Bước D — truy path đến GC root

Chọn instance hoặc accumulation point; mở **Path To GC Roots**, thường loại weak/soft/phantom để giảm nhiễu; đọc từng reference field trong chain. Ghi lại root type, class, field, số lượng object và retained size. Nếu có nhiều owners, xem merged paths, không chỉ một shortest path.

### Bước E — đối chiếu logic ứng dụng

Reference hợp lệ hay bất thường? Session còn hoạt động không? Request đã kết thúc chưa? TTL/eviction có chạy không? Lifecycle có unregister? Root chain cho biết **vì sao object sống**, nhưng chỉ kiến thức nghiệp vụ mới cho biết **có nên tiếp tục sống không**.

### Bước F — xác minh bản sửa

Thử workload đủ lâu sau warm-up, so hai hoặc nhiều dumps cùng điều kiện và heap used sau GC. Một bộ nhớ lớn không được thu vì yêu cầu cache hợp lệ khác với memory leak. Nếu release đúng mà RSS không giảm ngay, có thể do JVM giữ committed heap và native allocator; không vội quy chụp leak.

## 12. Các lỗi thường gặp khi làm lab và phân tích MAT

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `jcmd 12345` không kết nối được | Chưa thay PID ví dụ, process đã thoát, khác host/user/namespace, attach bị tắt | Dùng PID thực đang in ở terminal A, kiểm tra quyền và môi trường |
| File HPROF không xuất hiện ở terminal B | Đường dẫn được mở trên filesystem JVM đích, container mount khác hoặc thiếu quyền | Kiểm tra target machine/volume, folder, disk quota |
| Báo file đã tồn tại | `GC.heap_dump` không ghi đè theo mặc định | Dùng tên file mới; không xóa bằng chứng quan trọng |
| Ảnh đầu không có 64 `RetainedValue` | Chụp sau khi nhấn Enter, nhầm PID/file, dùng `-all`/settings lạ | Thực hiện đúng thứ tự, xác minh “Stage=RETAINED” |
| Ảnh sau vẫn có nhiều `byte[]` | JVM/JDK có rất nhiều byte arrays khác | Lọc class `RetainedValue` và đường payload, không cộng tất cả `byte[]` |
| `CACHE.size()=0` nhưng heap chưa giảm hoàn toàn | Map table capacity, JVM baseline, committed heap hoặc reference khác | Xem retained set/paths; so after-GC used thay vì chỉ RSS |
| `RetainedValue` vẫn reachable sau clear | Object còn được giữ bởi local/ThreadLocal/listener/static owner khác | Path To GC Roots của chính instance và phân tích từng owner |
| Retained Heap của map không như 16 MiB | Header/alignment/other paths, GC roots và cách tính dominator | Xem từng payload, references, shared ownership; không ép bằng 16 MiB |
| MAT báo OutOfMemoryError | Parser/index cần memory, dump quá lớn | Tăng heap cho MAT hoặc chạy trên máy phân tích đủ RAM; tránh production host |
| MAT hiển thị nhiều shortest paths | Một instance có nhiều owners hoặc đường tương đương | Đọc nhiều paths, tách strong và weak references |
| MAT không hiện đúng path như hình | Phiên bản JDK, class loader, parser và internal HashMap implementation khác | Theo field `CACHE`/`value`/`payload`, không so text từng dòng |
| Heap dump khác size dự kiến | HPROF chứa runtime metadata, class records, object layout khác | Không suy file size là retained heap chính xác |
| Tạo dump làm dịch vụ ngừng đáp ứng | Dump high impact, Full GC và disk I/O | Chỉ dùng lab; production cần change/incident approval |
| Lần phân tích sau chồng lên lần trước | Đọc nhầm file, cùng PID nhưng đã run lại JVM, thiếu timestamp | Đặt tên file riêng, lưu PID/time/JDK build và hash artifact |

### Đặt tên và bảo vệ artifact

HPROF có thể chứa passwords, API tokens, session data, URLs và nội dung object nghiệp vụ. Nên dùng tên gồm **environment, JVM/PID, timestamp, state**, hạn chế người đọc, mã hóa khi chuyển/lưu và xóa theo retention policy. Không đưa heap dump thật lên nơi công khai để xin hỗ trợ nếu chưa rà soát dữ liệu nhạy cảm.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Chương trình đã gọi `System.gc()` nhưng `CACHE` vẫn chứa 64 value. Tại sao các mảng chưa biến mất?

*Đáp án:* `CACHE` là static collection còn reachable từ class/JVM roots; map giữ các nodes, mỗi node giữ value, value giữ mảng. Khi còn strong path từ GC root, GC không được thu các mảng đó.

**Câu 2.** Trong MAT, `HashMap` chỉ có shallow heap vài chục byte, nhưng retained heap có thể lớn. Có mâu thuẫn không?

*Đáp án:* Không. Shallow size đo chính object `HashMap`; retained size xét những object chỉ còn sống nhờ đường qua map, như nodes, values và payload arrays.

**Câu 3.** Vì sao phải xem Path To GC Roots thay vì chỉ Histogram `byte[]`?

*Đáp án:* Histogram cho biết lượng object theo class, nhưng không cho biết **ai giữ** từng object. Path To GC Roots chỉ ra chủ sở hữu qua chuỗi reference, ví dụ static `CACHE` của class.

**Câu 4.** Sau `CACHE.clear()`, ảnh HPROF thứ hai vẫn có rất nhiều `byte[]`. Bài thực hành thất bại?

*Đáp án:* Không nhất thiết. JVM và ứng dụng vẫn có nhiều byte arrays phục vụ runtime. Hãy xem instance `CollectionRootLab$RetainedValue` và payload của chúng, không lấy toàn bộ class `byte[]` làm kết quả lab.

**Câu 5.** Một GC root path từ static cache tới session có đủ chứng minh memory leak không?

*Đáp án:* Chưa. Nó chứng minh object **đang được giữ**. Cần đối chiếu vòng đời session, giới hạn cache, tốc độ tăng retained set và việc cleanup có xảy ra khi cần.

**Câu 6.** Dùng `jcmd GC.heap_dump -all` để “bắt hết object” có hợp lý trong phép thử retention trước/sau?

*Đáp án:* Không nên. `-all` bao gồm object unreachable và không yêu cầu Full GC như mặc định. Điều đó có thể làm xuất hiện object đã đủ điều kiện thu hồi, gây nhiễu khi mục tiêu là tìm những object vẫn được giữ sống.

## Tài liệu tham khảo

- Oracle JDK 21 — **The jcmd Command**, `GC.heap_dump`, `-all`, ảnh hưởng High, tham số filename: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — **Troubleshoot Memory Leaks**, giải thích live set, strong reference không được loại khỏi collection và phân tích leak: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html
- Eclipse Memory Analyzer — **Basic Tutorial**, Histogram, Dominator Tree, Path To GC Roots: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html
- Eclipse Memory Analyzer — **Path to GC Roots**, các exclude filters và reference paths: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/path_to_gc_roots.html
- Eclipse Memory Analyzer — **Shallow vs. Retained Heap**, định nghĩa retained set: https://help.eclipse.org/latest/ntopic/org.eclipse.mat.ui.help/concepts/shallowretainedheap.html
- Eclipse Memory Analyzer — **Dominator Tree**, quan hệ thống trị so với reference graph: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html
- Eclipse Memory Analyzer — **Leak Suspects Report**, công cụ gợi ý nghi phạm, không tự chứng minh bug: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/runningleaksuspectreport.html
