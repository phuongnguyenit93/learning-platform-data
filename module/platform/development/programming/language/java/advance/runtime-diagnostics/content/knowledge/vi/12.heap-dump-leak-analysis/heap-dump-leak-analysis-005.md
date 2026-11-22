# 12.5. Phân biệt đối tượng còn sống với toàn bộ đối tượng được ghi và khả năng kích hoạt GC

## Mục tiêu và phạm vi

Trong chẩn đoán **heap dump và rò rỉ bộ nhớ Java**, việc chọn “chỉ đối tượng còn sống” (*live objects*) hay “mọi đối tượng hiện có trong heap” (*all objects*) thay đổi cả **dữ liệu được thu thập**, **ngữ nghĩa của kết luận** và **khả năng lệnh thu thập kích hoạt garbage collection (GC)**. Nếu không ghi lại chế độ dump, một heap dump có nhiều đối tượng “rác” rất dễ bị hiểu nhầm thành memory leak; ngược lại, một dump chỉ gồm đối tượng còn sống có thể đã bỏ mất dấu vết của đợt cấp phát tạm thời ngay trước khi thu thập.

Bài sử dụng chủ yếu **HotSpot trên JDK 17+**, các lệnh `jcmd`/`jmap` và Eclipse Memory Analyzer (MAT). Hành vi cụ thể phải đối chiếu với phiên bản JDK, garbage collector và cấu hình đang chạy; không mặc định mọi JVM có cùng tùy chọn.

## 1. “Đối tượng còn sống” là gì?

Java heap lưu trữ các instance và array. Bộ thu gom rác xác định khả năng tiếp cận chúng từ **GC roots**, chẳng hạn tham chiếu trong luồng Java, trường `static`, JNI global reference và những root do JVM quản lý. Có thể hình dung:

```text
GC roots
   ├──> singleton/static cache ──> Object A ──> Object B    (reachable)
   └──> thread/local variable ──> Object C                 (reachable)

Object D ──> Object E                                     (không còn đường từ GC root)
```

- **Reachable/live (theo cách JVM/GC xác định tại thời điểm đo):** object còn được giữ bởi một chuỗi tham chiếu có hiệu lực từ các root và thuộc tập mà GC phải duy trì. Ví dụ A, B, C. Thực tế có thêm quy tắc xử lý weak/soft/phantom references, finalization và loại collector; không đồng nhất “live” với “mọi biến từng trỏ tới object”.
- **Unreachable nhưng chưa được thu hồi:** object đã không còn đường tham chiếu hợp lệ từ GC roots, song GC chưa thu gom vùng nhớ của nó. Ví dụ D, E có thể vẫn tồn tại trong heap trước lần thu gom tiếp theo. Chúng **đủ điều kiện để được thu gom**, không đồng nghĩa sẽ biến mất tức khắc khi biến bị gán `null`.
- **Đã được GC thu hồi:** object không còn tồn tại trong vùng heap đang sử dụng; một heap dump tạo về sau **không thể khôi phục** object đã thu hồi.
- **“All objects” trong heap dump:** mọi object mà cơ chế dump ghi nhận **đang còn hiện diện trong Java heap ở thời điểm snapshot**, bao gồm reachable và, nếu còn tồn tại, unreachable. Không có nghĩa “mọi object từng được ứng dụng tạo ra kể từ khi khởi động”.

Một object **còn sống không tự động là memory leak**: nó có thể là cache hợp lệ, dữ liệu phiên làm việc hoặc trạng thái phục vụ request. Ngược lại, một object không còn reachable nhưng vẫn nằm trong heap chỉ phản ánh rác **chưa được thu gom**, chưa phải leak.

## 2. Live dump và all-objects dump khác nhau ở đâu?

| Khía cạnh | Live-only heap dump | All-objects heap dump |
| --- | --- | --- |
| Tập object được chọn | Chỉ object JVM xác định là live/reachable trong quy trình thu thập | Object còn trong heap, kể cả object hiện unreachable |
| Object đã bị GC thu hồi trước snapshot | Không có | Cũng không có |
| Dữ liệu về rác chưa thu gom | Thường không còn sau GC để chọn live set | Có thể có nếu GC chưa thu hồi trước snapshot |
| Ưu tiên sử dụng | Truy vết object được giữ lại, GC roots, retained heap, nghi ngờ leak | Điều tra các đợt cấp phát tạm thời, rác đang chờ thu gom, chênh lệch trước/sau GC |
| Nguy cơ diễn giải | Mất bằng chứng transient/unreachable do GC trước dump | Dễ đánh đồng “được ghi” với “đang bị giữ lại” |
| Kích thước HPROF | Thường nhỏ hơn khi rác được dọn trước | Có thể lớn hơn do chứa unreachable object |
| Có tự chứng minh leak? | Không; cần đường giữ tham chiếu và quan sát xu hướng | Không; unreachable object không phải leak |

**Lưu ý:** Không thể đảm bảo `all dump` luôn lớn hơn `live dump` nếu chụp ở những thời điểm khác nhau. GC có thể đã chạy, ứng dụng tiếp tục cấp phát, và bản thân thao tác đo làm trạng thái thay đổi. Muốn so sánh phải ghi rõ thời gian, tải, cấu hình và loại dump.

### Tình huống minh họa

Giả sử tại thời điểm `t0`: cache còn giữ 12 MB object reachable; một batch vừa giải phóng toàn bộ tham chiếu tới 35 MB temporary arrays; GC chưa thu hồi chúng.

- **All dump chụp ngay lúc đó** có thể chứa cả 12 MB cache và 35 MB temporary arrays. Sự hiện diện của 35 MB không nói rằng chúng đang bị giữ bởi GC root.
- **Live dump có GC trước snapshot** có thể chỉ còn cache và các object reachable khác. Temporary arrays đã được thu hồi nên không xuất hiện.
- **Nếu cache tăng liên tục** qua nhiều thời điểm sau GC, và MAT chỉ ra đường tham chiếu giữ cache từ một static root, khi ấy mới có bằng chứng mạnh hơn về retention bất thường.

Các số trên nhằm giải thích phạm vi quan sát; file HPROF thật còn bao gồm đối tượng JVM, object graph và metadata, nên không suy kích thước file bằng cách cộng đúng các số minh họa.

## 3. Tùy chọn `jcmd GC.heap_dump` và khả năng kích hoạt Full GC

Trên **HotSpot JDK 17**, tài liệu lệnh `jcmd` quy định rõ: **`GC.heap_dump` mặc định yêu cầu một Full GC, trừ khi có tùy chọn `-all`**. Đây là điểm cần ghi trong biên bản điều tra. “Yêu cầu Full GC” mô tả hành vi từ công cụ; cách collector triển khai và ảnh hưởng thực tế phụ thuộc JVM, không nên hứa một thời lượng pause cố định.

### 3.1. Dump mặc định: ưu tiên live objects, có yêu cầu Full GC

```bash
jcmd 12345 GC.heap_dump /tmp/heap-live.hprof
```

- `12345` là PID ví dụ của tiến trình Java cần đo; thay bằng PID thật.
- JVM **yêu cầu Full GC** trước khi tạo HPROF theo mặc định của lệnh. Điều này có thể thu hồi object đã unreachable, làm thay đổi lượng heap sử dụng và nội dung snapshot.
- Phù hợp khi trọng tâm là **object còn được giữ lại sau GC**, đường tới GC roots và retained heap.
- Không dùng cách này nếu mục tiêu là giữ bằng chứng rác chưa được thu gom tại chính thời điểm đang gặp triệu chứng; GC do công cụ yêu cầu có thể làm bằng chứng đó biến mất.
- Lệnh có **impact cao**; GC được yêu cầu, tiến trình ghi dump và I/O có thể gây độ trễ đáng kể.

### 3.2. Dump `-all`: có thể ghi unreachable objects, không yêu cầu Full GC từ lệnh

```bash
jcmd 12345 GC.heap_dump -all /tmp/heap-all.hprof
```

- Tùy chọn `-all` yêu cầu ghi **all objects, including unreachable objects** đang hiện diện trong heap theo cơ chế chụp của JVM.
- Với JDK 17, chọn `-all` nghĩa là **lệnh này không yêu cầu Full GC** trước khi dump. Đây **không phải bảo đảm “không có GC nào xảy ra”**: ứng dụng hoặc JVM vẫn có thể có GC do tải và những nguyên nhân khác trong thời gian quan sát.
- `-all` cũng **không có nghĩa thao tác không dừng ứng dụng**. Heap inspection/dumping có thể gây safepoint, pause và chi phí CPU/đĩa dù bỏ yêu cầu Full GC.
- Chọn khi cần khảo sát object unreachable **chưa kịp thu gom**, hoặc cần tránh việc Full GC do lệnh mặc định dọn mất trạng thái đang điều tra.

File `/tmp/heap-*.hprof` là ví dụ đường dẫn Linux/macOS. Trên Windows có thể dùng đường dẫn tuyệt đối như `C:/dumps/heap-all.hprof`. Đường dẫn được xử lý trong **môi trường của JVM đích**, nên cần quyền ghi và dung lượng đĩa ở máy/container/namespace phù hợp.

### Bảng quyết định nhanh cho `jcmd`

| Lệnh | Phạm vi snapshot | Có yêu cầu Full GC trước dump? |
| --- | --- | --- |
| `jcmd PID GC.heap_dump FILE` | Live objects theo mặc định | **Có**, theo tài liệu HotSpot JDK 17 |
| `jcmd PID GC.heap_dump -all FILE` | Gồm cả unreachable object nếu còn trong heap | **Không** do tùy chọn `-all` |
| `jcmd PID GC.class_histogram` | Thống kê số instance/bytes theo class ở chế độ mặc định | Không suy luận riêng hành vi GC chỉ từ tên; kiểm tra log/JDK |
| `jcmd PID GC.class_histogram -all` | Histogram bao gồm cả unreachable object | `-all` ở đây thay đổi phạm vi đếm; histogram **không** chứa object graph |
| `jcmd PID GC.run` | **Không tạo heap dump**; gọi `System.gc()` | Là lời yêu cầu GC riêng; không dùng để “kiểm tra” khi muốn giữ nguyên hiện trường |

Chữ `PID` và `FILE` trong bảng là **ký hiệu**; cú pháp chạy thực tế cần PID số và đường dẫn cụ thể như hai ví dụ trên. Trên JVM đang dùng, kiểm tra cú pháp được hỗ trợ bằng `jcmd 12345 help GC.heap_dump`.

## 4. `jmap`, dump khi OutOfMemoryError và giới hạn của từng nguồn

### `jmap`

JDK 17 cũng có các lệnh:

```bash
jmap -dump:live,format=b,file=/tmp/jmap-live.hprof 12345
jmap -dump:format=b,file=/tmp/jmap-all.hprof 12345
```

Trong tài liệu `jmap`, `live` chọn chỉ live objects; **không khai báo `live` thì ghi all objects**. Đây là phạm vi dữ liệu, **không tự thay thế** kết luận về việc GC thực sự đã chạy trong thời gian lệnh. Để xác định GC trên tiến trình thật, cần đối chiếu GC log; với hai lựa chọn `jcmd GC.heap_dump` phía trên, JDK 17 có quy định minh bạch về Full GC request. `jmap` được ghi là công cụ experimental/unsupported nên ưu tiên `jcmd` cho HotSpot thường dùng.

### Dump tự động khi `OutOfMemoryError`

Có thể cấu hình JVM lưu HPROF khi có OOME:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/oom.hprof -jar app.jar
```

Đây là **dump tại thời điểm sự cố**, không phải một lần tự chọn `jcmd -all` hay `jcmd` mặc định. Khi OOME xảy ra vì Java heap không cấp phát được, JVM **thường đã thử GC để giải phóng vùng nhớ**, nên dump tại sự cố có thể không còn nhiều unreachable objects. Cũng có trường hợp GC không xảy ra trước OOME; không suy đoán nếu chưa có log. Một OOME cũng có thể liên quan native memory/metaspace, khi ấy HPROF của Java heap không phản ánh toàn bộ nguyên nhân.

**Không gọi `System.gc()` hoặc `jcmd GC.run` trước khi thu thập chỉ để “làm số liệu đẹp hơn”.** Việc này có thể làm thay đổi chính đối tượng và dấu vết cần điều tra. Nếu cần live set sau GC, hãy nêu mục đích rồi dùng chế độ dump phù hợp.

## 5. Bài thực hành Java 17+: object được giữ và object đã bỏ tham chiếu

Tạo file **`HeapDumpScopeDemo.java`**:

```java
public class HeapDumpScopeDemo {
    // volatile để giữ đường tham chiếu quan sát được từ static field.
    private static volatile byte[][] retained;
    private static volatile byte[][] temporary;

    private static byte[][] allocate(int count, int bytesPerArray) {
        byte[][] result = new byte[count][];
        for (int i = 0; i < count; i++) {
            result[i] = new byte[bytesPerArray];
        }
        return result;
    }

    public static void main(String[] args) throws InterruptedException {
        retained = allocate(8, 256 * 1024);      // ~2 MiB còn reachable
        temporary = allocate(160, 256 * 1024);   // ~40 MiB có tham chiếu tạm
        temporary = null;                       // bỏ đường tham chiếu tạm

        System.out.println("Retained arrays: " + retained.length);
        System.out.println("PID: " + ProcessHandle.current().pid());
        Thread.sleep(120_000);                  // cho phép lấy dump từ terminal khác
    }
}
```

Biên dịch và chạy từ terminal thứ nhất:

```bash
javac -encoding UTF-8 HeapDumpScopeDemo.java
java -Xms128m -Xmx128m -XX:+UseSerialGC \
  -Xlog:gc=info \
  HeapDumpScopeDemo
```

Trên Unix shell, dấu `\` cuối dòng nối lệnh; trên PowerShell có thể nhập toàn bộ lệnh `java` trên một dòng. Chương trình in chính xác dòng `Retained arrays: 8`; PID là số phụ thuộc tiến trình. Sau đó chương trình giữ JVM chạy khoảng 120 giây.

Ở terminal thứ hai, thay `12345` bằng PID in ra:

```bash
jcmd 12345 GC.heap_dump -all /tmp/demo-all.hprof
jcmd 12345 GC.heap_dump /tmp/demo-live.hprof
```

**Điều cần hiểu khi quan sát:**

1. `retained` là một `static` field chứa mảng 8 phần tử, mỗi phần tử trỏ tới một `byte[]`; các mảng này vẫn reachable.
2. Sau khi `temporary = null` và phương thức đã tiếp tục, cụm 160 mảng có thể **không còn reachable** và đủ điều kiện để GC thu hồi. Việc gán `null` **không tự chạy GC**.
3. Nếu GC chưa thu gom chúng, dump `-all` **có thể** ghi cả các mảng không còn reachable. Dump mặc định có yêu cầu Full GC nên có thể không còn chúng.
4. **Không dự đoán số lượng object, kích thước file, số lần GC hay stdout của `jcmd` một cách cố định**: JVM có thể tự chạy GC trong lúc cấp phát hoặc trước snapshot. Kết quả thay đổi theo môi trường.
5. Hai dump chạy tuần tự **không phải một thí nghiệm A/B độc lập**: dump thứ nhất, GC tự nhiên hoặc dump thứ hai có thể làm thay đổi heap. Muốn so sánh chắc hơn, khởi động lại ở điều kiện tương đương và đo GC log song song.

Ví dụ có mục đích minh họa **reachability và sự khác nhau của hai lệnh**. Nó không cố tình tạo leak: khi tham chiếu `temporary` đã mất, vùng nhớ của các mảng có thể được tái sử dụng sau GC.

## 6. Khi mở HPROF bằng Eclipse MAT: vì sao “all” có thể nhìn như “live”?

Đây là một lớp khác hoàn toàn: **chế độ parser của công cụ phân tích**, không phải chế độ thu thập của JVM.

Theo tài liệu Eclipse Memory Analyzer, khi mở dump, MAT **mặc định loại các object unreachable khỏi object graph lúc parse** vì chúng thường không cần thiết cho phân tích memory leak. MAT vẫn có mục **Unreachable Objects** ở dạng histogram, nhưng object graph của phần bị loại không còn để lần theo trong phiên parse mặc định.

Hệ quả:

- File `-all` thực sự có thể chứa object unreachable, nhưng **Histogram/Dominator Tree mặc định trong MAT không hiện toàn bộ những object ấy** vì MAT đã lọc khi xây chỉ mục.
- **Unreachable Objects histogram** cho thấy các class và lượng object unreachable MAT ghi nhận; trong chế độ parse mặc định, không thể từ histogram này lần theo đầy đủ từng object bị loại.
- Muốn phân tích chi tiết các object unreachable trong all dump, bật **Keep unreachable objects** trong **Window → Preferences → Memory Analyzer**, xóa index cũ của snapshot nếu cần và mở lại dump để **parse lại**. Hãy xác nhận file gốc được lấy ở chế độ cho phép ghi unreachable; tùy chọn MAT không thể tái tạo object đã bị GC dọn trước khi dump.
- **Keep unreachable objects** là lựa chọn của công cụ phân tích trên file đã tồn tại; **nó không kích hoạt GC trên ứng dụng đích**. Ngược lại, `jcmd -all` tác động đến cách JVM thu thập dữ liệu, không tự buộc MAT giữ unreachable trong graph.

Khi điều tra leak, MAT có các góc nhìn hữu ích:

- **Histogram:** số lượng/`shallow heap` theo class; kích thước shallow của từng object không bao gồm toàn bộ các object mà nó giữ tham chiếu.
- **Dominator Tree / Retained Heap:** giúp tìm những nhóm object bị giữ lại bởi một owner/root có ảnh hưởng lớn. Retained heap là ước lượng bộ nhớ sẽ trở nên có thể thu hồi nếu một object/nhóm chủ đạo được giải phóng, theo graph mà MAT đang phân tích.
- **Path to GC Roots:** truy ngược vì sao object còn được giữ (ví dụ `static Map`, `ThreadLocal` hoặc một listener chưa được tháo đăng ký).

**Không suy “Leak!” chỉ từ class có nhiều instance trong all dump.** Trước tiên phải phân biệt unreachable objects với object được giữ lại bởi đường tham chiếu hợp lệ, rồi xem sự tăng trưởng qua thời gian.

## 7. Kiểm tra chính xác GC có diễn ra khi dump hay không

Với ứng dụng tự khởi động để điều tra, bật GC/safepoint log (ví dụ):

```bash
java -Xms128m -Xmx128m \
  -Xlog:gc*=info,safepoint=info:file=gc-events.log:time,uptime,level,tags \
  HeapDumpScopeDemo
```

Sau khi dùng `jcmd`, đối chiếu timestamp giữa thời gian chạy lệnh, nội dung GC log và thời điểm ghi HPROF.

**Cách đọc an toàn:**

- Nếu chạy **`GC.heap_dump` mặc định**, theo tài liệu JDK 17 lệnh **yêu cầu Full GC**. Xác nhận log có sự kiện GC nào tương ứng, loại GC, pause và thay đổi heap thực tế; không kết luận thời gian dừng chỉ từ sự hiện diện của file.
- Nếu chạy **`GC.heap_dump -all`**, lệnh **không yêu cầu Full GC**. Tuy nhiên nếu log vẫn có GC quanh thời điểm đó, phải xét liệu GC tự nhiên, ngưỡng cấp phát hoặc một thao tác khác kích hoạt nó.
- `-all` **không phải chế độ non-stop**: việc chụp heap vẫn có thể gây pause và chi phí tài nguyên. Kiểm tra độ trễ ứng dụng, GC/safepoint log và thời gian dump.
- Dùng `jcmd 12345 help GC.heap_dump` để biết tùy chọn trên JVM cụ thể. Không gán cùng hành vi cho những collector, phiên bản và vendor khác nhau mà không kiểm chứng.

Ví dụ log **minh họa**, không phải output cố định:

```text
[10.000s][info][gc] GC(3) Pause Full (Diagnostic Command) 45M->6M(128M) 87.123ms
```

Thông điệp thực có thể khác; điều cần học là nhận ra **GC cause**, **heap before/after** và **pause duration** thay vì suy luận từ tên file. Một collector có thể báo nhiều pha hoặc khác câu chữ.

## 8. Chọn chiến lược theo mục đích chẩn đoán

| Câu hỏi thực tế | Cách thu thập ưu tiên | Cách diễn giải |
| --- | --- | --- |
| Vì sao heap sau GC vẫn cao hoặc tăng qua các chu kỳ? | Live dump, GC logs, nhiều điểm đo cùng tải | Xem retained heap, Dominator Tree, GC roots; phân biệt cache hợp lệ và retention bất thường. |
| Có phải ứng dụng tạo nhiều object tạm rồi chờ GC? | All dump nếu cần xem unreachable trước GC; đồng thời đo allocation/GC bằng JFR, GC logs | Unreachable hiện trong dump không đủ để chứng minh leak; dùng lượng cấp phát và collection để hiểu churn. |
| Có cần giữ hiện trường ngay trước lúc GC dọn rác? | `jcmd GC.heap_dump -all` với ghi nhận thời điểm, tải và GC log | Không yêu cầu Full GC từ lệnh, nhưng vẫn có GC tự nhiên và pause đo đạc. |
| HPROF được tạo sau OutOfMemoryError | Dump OOME + GC logs + thông báo chi tiết của OOME | Thường đã có nỗ lực GC trước lỗi; bản dump không đảm bảo chứa rác từng tồn tại. |
| Histogram class rất lớn, không có đường tới GC roots | Kiểm tra MAT parser và mục Unreachable Objects | Có thể là unreachable đã bị MAT lọc; bật Keep unreachable trước khi parse lại nếu cần. |
| Heap dump bình thường nhưng RSS của process cao | Native Memory Tracking, thread stacks, direct memory/metaspace và OS metrics | HPROF của Java heap không bao trùm mọi loại native memory. |

Để điều tra leak một cách có cơ sở, nên ghi lại **JDK/collector, PID, heap flags, thời điểm, tải hệ thống, câu lệnh dump chính xác, trạng thái GC log**. Trong MAT, tìm **đường tham chiếu giữ object** và sự thay đổi *sau GC* qua những lần quan sát có điều kiện tương đương.

### Quy trình tối thiểu khi nghi memory leak

1. Kiểm tra **triệu chứng**: heap sau GC tăng đều, GC ngày càng nhiều, OOME, hoặc chỉ có burst cấp phát tạm thời.
2. Lựa chọn phạm vi: muốn khảo sát *object vẫn bị giữ* thì live; muốn giữ dấu vết *unreachable chưa thu gom* thì `-all`.
3. Chuẩn bị **đĩa và thời điểm lấy dump**; tránh tạo nhiều dump lớn trên production trong giờ cao tải khi chưa đánh giá ảnh hưởng.
4. Chạy lệnh đã chọn; đồng thời lưu log GC/safepoint và ghi nhận **lệnh dump có/không yêu cầu Full GC**.
5. Mở HPROF trong MAT, xác nhận tùy chọn **Keep unreachable objects** phù hợp mục đích; đối chiếu Histogram, Dominator Tree, Path to GC Roots.
6. Nếu nhận định leak, xác nhận **object graph bị giữ lại** và **xu hướng theo thời gian**; đối chiếu code tạo, cache eviction, listener, `ThreadLocal`, lifecycle hoặc nguồn giữ tham chiếu cụ thể.

## 9. Những sai lầm phổ biến

1. **“All dump là tất cả object từng được tạo.”** Không đúng: object đã bị GC thu hồi trước snapshot không quay lại trong HPROF.
2. **“Object unreachable xuất hiện tức là leak.”** Không đúng: đó thường là garbage đang chờ thu gom.
3. **“Object live xuất hiện tức là leak.”** Không đúng: object có thể đang được sử dụng hợp lệ.
4. **“`-all` sẽ không có bất kỳ GC/pause nào.”** Không đúng: `-all` chỉ bỏ yêu cầu Full GC do lệnh `jcmd GC.heap_dump` theo JDK 17; JVM vẫn có thể GC vì nguyên nhân khác và thao tác dump vẫn tốn tài nguyên.
5. **“Heap dump mặc định không thay đổi chương trình.”** Không đúng: mặc định `jcmd GC.heap_dump` yêu cầu Full GC; heap và GC log có thể thay đổi trước snapshot.
6. **“MAT không hiện unreachable thì file không chứa chúng.”** Không đúng: MAT thường lọc unreachable khi parse; cần xét cách tạo dump và tùy chọn Keep unreachable.
7. **“So kích thước hai file liên tiếp chứng minh có rò rỉ.”** Không đúng: thời điểm, workload, tự động GC, Full GC do công cụ và đối tượng runtime đều khác nhau.
8. **“Cứ dùng `System.gc()` trước dump cho sạch.”** Làm vậy có thể phá hủy bằng chứng transient và thêm pause, cần mục đích rõ ràng.
9. **“HPROF phản ánh toàn bộ RAM process.”** Không đúng: direct/native memory, metaspace và các vùng khác cần công cụ tương ứng.
10. **“Khi đã có histogram là đủ tìm root gây leak.”** Không đúng: histogram cung cấp thống kê theo class, còn muốn hiểu retention phải phân tích object graph và GC roots.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một `List<byte[]>` tạm vừa bị bỏ tham chiếu, GC chưa chạy. Có thể thấy các mảng trong `jcmd PID GC.heap_dump -all FILE` không?  
**Đáp án:** Có thể, nếu chúng còn hiện diện trong heap khi snapshot được tạo. Đó không tự chứng minh rò rỉ.

**Câu 2.** `jcmd PID GC.heap_dump FILE` trên HotSpot JDK 17 có yêu cầu Full GC không?  
**Đáp án:** Có, theo mặc định; `-all` là tùy chọn để **không yêu cầu Full GC từ lệnh dump**.

**Câu 3.** Có `-all` thì bảo đảm không pause?  
**Đáp án:** Không. GC tự nhiên vẫn có thể xảy ra; heap inspection và ghi HPROF vẫn có chi phí, có thể dừng ứng dụng.

**Câu 4.** File HPROF tạo bằng `-all` nhưng MAT chỉ hiện object reachable. Vì sao?  
**Đáp án:** MAT thường loại unreachable trong quá trình parse; cần xem Unreachable Objects và tùy chọn Keep unreachable objects khi muốn giữ graph của chúng.

**Câu 5.** Thấy 500 MB unreachable object trong một snapshot là bằng chứng leak?  
**Đáp án:** Chưa. Cần xem vì sao tồn tại trước GC và xu hướng. Leak Java heap thường được chứng minh bằng những đối tượng vẫn bị giữ từ GC roots và tập live tăng bất thường.

**Câu 6.** JVM vừa OOME, tại sao dump không có đợt temporary allocation trước lỗi?  
**Đáp án:** Một hoặc nhiều GC có thể đã thu hồi những object không còn reachable trước lúc dump; HPROF không lưu lịch sử toàn bộ allocations.

## Tài liệu chính thức

- [Oracle JDK 17 — `jcmd`, mục `GC.heap_dump` và `-all`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle JDK 17 — `jmap`, mục `-dump:live` và all objects](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jmap.html)
- [Oracle JDK 17 — `java`, `HeapDumpOnOutOfMemoryError` và `HeapDumpPath`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle JDK 17 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html)
- [Eclipse Memory Analyzer — Unreachable Objects](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/unreachable_objects.html)
- [Eclipse Memory Analyzer — Keep unreachable objects](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/configure_mat.html)
