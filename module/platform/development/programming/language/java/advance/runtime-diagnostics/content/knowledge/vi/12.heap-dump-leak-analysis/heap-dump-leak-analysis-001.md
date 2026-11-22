# 12.1 Heap dump lưu dữ liệu gì và khác gì với class histogram hoặc bản ghi cấp phát

## Mục tiêu

Sau bài này, bạn có thể trả lời ba câu hỏi khác nhau khi phân tích bộ nhớ Java: **đang còn những đối tượng nào trong heap, nhóm lớp nào đang chiếm nhiều dung lượng, và mã nguồn nào liên tục tạo ra đối tượng mới?** Bạn cũng sẽ biết vì sao một biểu đồ cấp phát cao chưa chứng minh có rò rỉ bộ nhớ, và vì sao histogram chưa đủ để xác định ai đang giữ đối tượng sống.

## 1. Phân biệt ba góc nhìn

- **Heap dump:** ảnh chụp cấu trúc bộ nhớ heap tại một thời điểm. Cho phép đi từ đối tượng sang trường dữ liệu, tham chiếu, chuỗi giữ sống và GC root; phù hợp để điều tra **retention** (đối tượng còn bị giữ lại).
- **Class histogram:** bảng tổng hợp tại một thời điểm, thường có **tên lớp, số instance, tổng shallow bytes**. Phù hợp để phát hiện nhóm đối tượng tăng bất thường và khoanh vùng nhanh; thiếu chi tiết đồ thị tham chiếu.
- **Bản ghi cấp phát (allocation recording/profile):** dữ liệu thu thập trong **một khoảng thời gian**, thường là sự kiện hoặc mẫu cấp phát từ JFR/profiler, có thể có lớp, thread, call stack và trọng số/số byte ước lượng. Phù hợp để tìm **allocation hot spot** (đường gọi tạo nhiều đối tượng), nhưng không mặc nhiên cho biết đối tượng nào còn sống.

Điểm mấu chốt: **allocation là lúc tạo ra đối tượng; retention là việc đối tượng tiếp tục có thể tới được và chưa được thu hồi.** Ứng dụng có thể cấp phát rất nhanh nhưng GC thu hồi tốt, hoặc cấp phát tương đối ít mà giữ lại lượng lớn dữ liệu không còn cần thiết.

| Câu hỏi cần trả lời | Công cụ ưu tiên | Vì sao |
| --- | --- | --- |
| Những đối tượng và tham chiếu nào đang nằm trong heap tại thời điểm chụp? | Heap dump | Có dữ liệu từng instance và liên kết giữa chúng |
| Class nào có nhiều instance/chiếm nhiều shallow bytes? | Class histogram | Tổng hợp nhanh theo class |
| Object nào giữ một tập object khác không được GC thu hồi? | Heap dump + dominator tree + path to GC roots | Truy vết quan hệ giữ sống |
| Hàm nào đang tạo ra phần lớn object hoặc byte cấp phát? | JFR/allocation profiler | Có mẫu sự kiện và stack cấp phát qua thời gian |
| Có rò rỉ bộ nhớ kéo dài không? | Theo dõi xu hướng + heap dump tại các thời điểm + thông tin GC | Một snapshot đơn lẻ chỉ cho thấy trạng thái; cần chứng minh việc giữ lại tăng dai dẳng |

## 2. Heap dump thực sự lưu gì?

Với HotSpot/OpenJDK, heap dump thường được tạo ở định dạng **HPROF**. Nó mô tả trạng thái Java heap trong thời điểm thu thập; đây là một tập đối tượng cùng quan hệ tham chiếu, không phải chỉ là báo cáo sử dụng RAM.

Các nhóm thông tin cốt lõi:

1. **Instance object và array:** kiểu/class của object, dữ liệu trường primitive được ghi nhận, các trường tham chiếu trỏ tới object khác; array có loại phần tử, độ dài và phần tử/giá trị tương ứng. Ví dụ một đối tượng danh sách có thể trỏ đến mảng backing array, rồi đến các phần tử.
2. **Thông tin lớp phục vụ giải mã heap:** tên class, quan hệ lớp, các trường instance/static, liên kết đến class loader; nhờ đó công cụ phân tích có thể quy object về đúng kiểu và nhận diện class loader đang giữ dữ liệu. Không đồng nghĩa với chụp toàn bộ bytecode, mọi metadata của Metaspace hay tất cả thông tin nội bộ JVM.
3. **Các tham chiếu và thông tin GC roots mà định dạng/VM xuất ra:** ví dụ liên quan đến biến cục bộ trên stack, static field, thread và JNI handle. Công cụ như Eclipse MAT dùng chúng để tính **Paths to GC Roots**, tức vì sao object vẫn có thể tới được.
4. **Kích thước và số lượng:** công cụ phân tích suy ra hoặc tính shallow size của từng object và các tập object liên quan; sau đó tính retained size dựa trên đồ thị tham chiếu. Đây là kết quả phân tích chứ không nên hiểu toàn bộ phép tính đã được lưu sẵn trong một cột của dump.

### Shallow size, retained size và GC root

- **Shallow size**: bộ nhớ của chính object, ví dụ phần vỏ của một đối tượng Map hoặc mảng (không cộng toàn bộ object mà nó tham chiếu).
- **Retained size**: tổng bộ nhớ của những object sẽ trở nên không thể tới được nếu loại bỏ object đang xét khỏi đồ thị giữ sống, theo mô hình dominator. Nó thể hiện tác động giữ bộ nhớ, không phải chỉ độ lớn của đối tượng mẹ.
- **GC root**: điểm xuất phát mà JVM coi là còn sống để truy vết các object có thể tới được; đi theo các cạnh tham chiếu từ root cho biết lý do một object chưa được thu hồi.

Ví dụ: một cache Map có thể chỉ có shallow size vài chục byte, nhưng đang giữ hàng trăm nghìn entry và các mảng byte. **Retained size** của đối tượng giữ cache có thể rất lớn. Class histogram có thể cho thấy nhiều mảng byte; **heap dump mới giúp lần ngược đường tham chiếu** từ các mảng đó đến cache hoặc trường static giữ chúng.

### Những điều heap dump không tự cung cấp

- Không phải lịch sử: một dump thông thường **không lưu đầy đủ thời điểm tạo, tần suất cấp phát, stack tạo ra từng object, hay danh sách object từng tồn tại rồi đã bị GC thu hồi**.
- Không phải bộ chụp toàn bộ tiến trình: không trực tiếp mô tả đầy đủ **native/off-heap memory** như direct buffer native payload, thread native stack, Code Cache, Metaspace, mmap, socket/file descriptor. Một object Java đại diện cho tài nguyên native có thể thấy được, nhưng phần native bên dưới không nhất thiết có trong heap dump.
- Không tự kết luận “leak”: object còn sống tại thời điểm chụp có thể hoàn toàn hợp lệ. Phải so sánh với vòng đời mong đợi, xu hướng theo thời gian, GC và đường giữ sống.
- Không phải ảnh chụp trung lập về trạng thái chưa GC: với lệnh HotSpot ở phần sau, mặc định JVM **yêu cầu Full GC trước khi xuất heap dump**; tùy chọn -all thay đổi tập object được đưa vào và bỏ yêu cầu Full GC đó. Vì thế hai cách chụp có thể cho kết quả khác nhau.

**Chú ý dữ liệu nhạy cảm:** heap dump có thể chứa chuỗi, token, nội dung request, dữ liệu khách hàng và thông tin ứng dụng ở dạng đọc được. Kiểm soát quyền truy cập, nơi lưu, thời gian lưu và việc chia sẻ file.

## 3. Class histogram ghi gì và không ghi gì?

Histogram thường có một dòng cho mỗi class hoặc kiểu array, gồm thứ hạng, **#instances**, **#bytes** và tên class. Ví dụ minh họa (số liệu giả định):

~~~text
 num     #instances       #bytes  class name
   1:         10000     11000000  [B
   2:          2000       480000  java.lang.String
   3:           100        12000  java.util.HashMap
~~~

Trong ký hiệu tên lớp của JVM, **[B** là mảng byte (byte[]). **#bytes** đại diện tổng shallow size của các instance trong hàng, không phải retained size của chúng. Cột tổng hợp **không nói 10.000 mảng byte đến từ request nào**, vì sao chúng còn sống, hay HashMap nào giữ những mảng đó.

Histogram hữu ích khi:
- So sánh nhanh hai thời điểm **sau khi áp dụng cùng điều kiện đo**: số instance/bytes của một class có đang tăng không?
- Xác định nghi phạm như byte[], char[], String, Map entry hoặc đối tượng thuộc package ứng dụng.
- Cần một bức tranh tổng quan ngắn gọn trước khi tạo và phân tích file dump lớn.

Giới hạn quan trọng:
- Không có tham chiếu giữa từng object và không có path to GC roots/dominator tree.
- Không có call stack hoặc tốc độ cấp phát theo giây.
- Một class tăng mạnh có thể là cache hợp lệ, tải tăng, ứng dụng đang warm-up hoặc lượng dữ liệu đầu vào lớn; **không đủ chứng minh rò rỉ**.
- Histogram lấy trực tiếp từ JVM ở thời điểm khác với histogram dựng từ một file dump có thể khác nhau, nhất là khi tập object và điều kiện GC không giống nhau.

## 4. Bản ghi cấp phát lưu gì và khác heap dump thế nào?

Một **allocation recording** quan sát *hoạt động tạo object* trong một khoảng đo. Với Java Flight Recorder (JFR), sự kiện/mẫu như **jdk.ObjectAllocationSample** có thể cung cấp kiểu object, thread, stack trace và **weight** (trọng số byte dùng để ước lượng áp lực cấp phát). Những kiểu sự kiện chi tiết khác, ví dụ **jdk.ObjectAllocationInNewTLAB** hoặc **jdk.ObjectAllocationOutsideTLAB**, phụ thuộc cấu hình thu thập và chi phí đo. Các profiler khác có thể dùng cơ chế sampling riêng.

Vì sao cần lấy mẫu? Ghi lại chính xác mọi lần cấp phát trong hệ thống bận rộn có thể tạo chi phí rất lớn. Do đó **kết quả sampling là ước lượng**, không phải nhật ký bắt buộc chứa mọi object. Không được đọc số event như tổng số lần cấp phát thực tế nếu công cụ đang sampling.

Allocation recording trả lời:
- Call stack/phương thức nào tạo nhiều byte[] hay đối tượng tạm thời?
- Trong khoảng đo, allocation rate và nhóm class cấp phát biến động thế nào?
- Những thread hoặc request path nào tạo áp lực cấp phát dẫn tới GC thường xuyên?

Nó **không tự trả lời** object đó hiện còn sống, đang được root nào giữ, hay sẽ được GC thu hồi ngay sau sự kiện. File JFR chứa nhiều loại sự kiện theo cấu hình; bản thân nó cũng không phải một heap dump HPROF. Một loại sự kiện khác là **OldObjectSample** có thể hỗ trợ điều tra object sống lâu và dữ liệu về đường đến GC root nếu bật tính năng phù hợp, nhưng chỉ là mẫu và không thay thế đồ thị đối tượng đầy đủ từ heap dump.

Ví dụ khác biệt thực tế:

- **Tình huống A — tạo nhiều object tạm:** mỗi request tạo hàng nghìn buffer rồi bỏ tham chiếu sau khi trả response. JFR có thể báo điểm cấp phát nóng; sau GC, heap dump/histogram có thể chứa rất ít buffer đó. Vấn đề là **allocation pressure/GC overhead**, chưa chắc có leak.
- **Tình huống B — cache giữ object vô hạn:** request chỉ thêm vài object vào một Map static nhưng không có cơ chế eviction. Theo thời gian, retained heap tăng; heap dump cho thấy Map giữ dữ liệu, histogram cho biết class nào tích lũy. JFR có thể giúp tìm nơi cấp phát ban đầu nhưng không tự chỉ ra quan hệ giữ sống hiện tại.

## 5. Bảng đối chiếu lựa chọn công cụ

| Tiêu chí | Heap dump (HPROF) | Class histogram | Allocation recording (ví dụ JFR) |
| --- | --- | --- | --- |
| Bản chất | Snapshot đồ thị object | Snapshot tổng hợp theo class | Sự kiện/mẫu phát sinh trong khoảng thời gian |
| Đơn vị quan sát | Từng instance và reference | Class, số instance, shallow bytes | Lần cấp phát/mẫu, class, stack/thread, trọng số |
| Tìm ai giữ object sống | **Có**, qua đồ thị, GC roots/dominator | **Không** | Không trực tiếp với mẫu cấp phát thông thường |
| Tìm call stack gây cấp phát | Thường **không** | **Không** | **Có thể**, nếu cấu hình thu thập stack |
| Thấy object đã cấp phát nhưng đã bị GC dọn | Không trong bản dump live thông thường | Không trong histogram live thông thường | **Có thể**, nếu sự kiện được thu khi object tạo |
| Theo dõi diễn biến qua thời gian | So sánh nhiều dump; bản dump riêng lẻ không có timeline | So sánh nhiều histogram | Phù hợp với timeline/tốc độ trong thời gian ghi |
| Chi phí thường gặp | Tác động lớn, có thể Full GC/pause và file rất lớn | Có thể tốn thời gian/pause khi quét heap | Tùy sự kiện và cấu hình, profile lấy mẫu thường nhẹ hơn |
| Phù hợp nhất | Tìm retention/leak và root giữ sống | Khoanh vùng class và biến động số lượng | Tìm allocation hot spot/GC pressure |

**Không đồng nhất heap usage với process RSS:** Java heap chỉ là một phần bộ nhớ tiến trình. Nếu RSS tăng mà Java heap sau GC ổn định, cần điều tra native memory/off-heap, không suy kết luận leak từ histogram.

## 6. Thực hành Java 17+: cùng lúc có nhiều allocation và ít object còn được giữ

Chương trình sau tạo 20.000 mảng byte được thay thế liên tục qua một trường volatile; sau đó giữ 500 mảng trong List. Các mảng bị thay thế có thể đủ điều kiện GC. JIT, GC, class của thư viện và thời điểm chụp sẽ làm số lượng object quan sát thực tế thay đổi.

Lưu file **HeapSnapshotDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapSnapshotDemo {
    private static volatile byte[] mostRecent;
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 20_000; i++) {
            mostRecent = new byte[1_024];
        }

        for (int i = 0; i < 500; i++) {
            RETAINED.add(new byte[1_024]);
        }

        System.out.println("Retained arrays: " + RETAINED.size());
        System.out.println("Ready for diagnostics");
        Thread.sleep(180_000L);
    }
}
~~~

Biên dịch và chạy (JDK 17+, ví dụ sử dụng HotSpot):

~~~bash
javac HeapSnapshotDemo.java
java -Xmx128m -XX:StartFlightRecording=filename=alloc.jfr,settings=profile,dumponexit=true HeapSnapshotDemo
~~~

Hai dòng stdout xác định của chương trình là:

~~~text
Retained arrays: 500
Ready for diagnostics
~~~

Tại terminal thứ hai, tìm PID Java đang chạy và lấy các phép đo khác nhau:

~~~bash
jcmd -l
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump heap.hprof
~~~

- **Histogram** giúp kiểm tra tổng byte[] đang có tại thời điểm đo, nhưng còn có byte[] do chính JDK hoặc các thư viện tạo nên đừng kỳ vọng đúng 500.
- **Heap dump** mở bằng Eclipse Memory Analyzer (MAT) cho phép đi sâu từ byte[] đến List hoặc các root khác. RETAINED là trường static giữ tham chiếu đến List; mostRecent giữ một mảng cuối cùng.
- **JFR** đã được bật từ lúc khởi động. Sau khi chương trình kết thúc, dùng lệnh dưới đây để xem các mẫu cấp phát nếu recording thực tế chứa sự kiện tương ứng:

~~~bash
jfr print --events jdk.ObjectAllocationSample alloc.jfr
~~~

Dữ liệu mẫu JFR có thể gợi ý nơi tạo các mảng; số event cụ thể **không cố định** và không phải “20.500 object” vì có sampling, các cấp phát khác và tối ưu của JVM. Đây là demo về **sự khác biệt thông tin**, không phải bài kiểm thử bắt buộc mọi công cụ phải trả một tổng số giống nhau.

Nếu cần lấy dump khi hết heap, có thể cấu hình JVM **-XX:+HeapDumpOnOutOfMemoryError** và **-XX:HeapDumpPath=/duong-dan/dump.hprof** từ trước. Đảm bảo dung lượng đĩa, quyền ghi và quy trình bảo vệ file.

## 7. Quy trình điều tra thực tế

### Khi heap sau GC tiếp tục tăng và nghi có leak

1. Xác minh triệu chứng bằng chỉ số heap/GC theo thời gian và trạng thái tải. Phân biệt peak sử dụng trước GC với dung lượng còn lại **sau các lần GC có ý nghĩa**.
2. Lấy histogram ở những thời điểm có thể so sánh; xem nhóm class nào tăng về instance hoặc shallow bytes. Đây chỉ là bước chọn nghi phạm.
3. Khi cần biết nguyên nhân giữ sống, tạo **heap dump** ở thời điểm phù hợp; nếu có thể, thu thêm dump khác dưới điều kiện tải và GC tương đương để so sánh.
4. Mở bằng **Eclipse MAT**: xem Histogram, Dominator Tree hoặc Top Consumers, rồi **Paths to GC Roots** đối với object đáng ngờ. Lần ngược đến trường static, cache, queue, listener, collection hoặc class loader đang giữ object.
5. So sánh với vòng đời thiết kế: object tồn tại vì cache hợp lệ, job chưa xong hay do thiếu remove/evict/close/unregister? Sửa cơ chế quản lý vòng đời và đo lại.

**Ví dụ lý luận:** histogram cho thấy số lượng byte[] tăng → dump xác định byte[] thuộc nhiều value của cache → Paths to GC Roots nối cache tới một static field → kiểm tra chính sách eviction. Kết luận leak chỉ được củng cố nếu dữ liệu đáng lẽ phải hết hạn mà vẫn bị giữ lâu dài.

### Khi GC chạy dày, throughput giảm nhưng heap sau GC ổn định

1. Thu **JFR allocation profile** trong khoảng thời gian có tải đại diện, xem nhóm class, allocation rate và call stack.
2. Tối ưu điểm nóng phù hợp: tránh tạo buffer lặp không cần thiết, tránh trung gian dư thừa hoặc xem xét batch/pooling trong điều kiện có lợi.
3. Đo lại allocation rate, latency và GC sau thay đổi. Không kết luận “không leak” chỉ bằng một vài phút recording; đánh giá retention riêng khi có dấu hiệu tích lũy.

### Lệnh chẩn đoán HotSpot và lưu ý vận hành

~~~bash
# Thay PID bằng tiến trình đích, đường dẫn bằng nơi có đủ dung lượng.
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump /safe-path/heap.hprof

# Với -all, bao gồm cả object không còn reachable; không yêu cầu Full GC trước dump.
jcmd <PID> GC.heap_dump -all /safe-path/all-objects.hprof

# Ghi JFR trong 2 phút; sự kiện thực tế phụ thuộc profile và JDK.
jcmd <PID> JFR.start name=alloc settings=profile duration=2m filename=/safe-path/alloc.jfr
~~~

Theo tài liệu lệnh **jcmd** của JDK 21, GC.heap_dump mặc định yêu cầu Full GC trừ khi dùng **-all**; GC.class_histogram và heap dump đều được xếp tác động cao. Thu dump có thể làm ứng dụng tạm dừng lâu và tạo file lớn. Cần thực hiện vào thời điểm phù hợp, kiểm tra dung lượng đĩa/quyền truy cập, và tránh nhiều tác vụ nặng đồng thời trên JVM production. Thông số và hỗ trợ lệnh phụ thuộc JDK/VM; ví dụ ở đây áp dụng cho HotSpot/OpenJDK.

**-all không có nghĩa là “dữ liệu chính xác hơn để kết luận leak”.** Nó bao gồm cả object không thể tới được và có thể bị GC thu hồi, nên tập object khác với dump live mặc định. Khi so sánh hai lần đo, ghi rõ cách chụp và điều kiện GC.

## 8. Lỗi suy luận thường gặp

1. **“Histogram có 2 GB byte[] nên chắc chắn byte[] bị leak.”** Sai: đó là tổng shallow bytes tại thời điểm đo, chưa nói ai giữ, vì sao giữ và có đang tăng bất thường hay không.
2. **“JFR ghi nhiều allocation nên heap sẽ luôn tăng.”** Sai: allocation rate cao có thể đi cùng heap sau GC ổn định vì object chỉ sống rất ngắn.
3. **“Object lớn nhất trong heap là nguyên nhân gốc.”** Chưa chắc: một object nhỏ như cache holder có thể giữ lại cả mạng object lớn. Cần xem dominator và retained size.
4. **“Heap dump có stack cấp phát của từng object.”** Thường sai đối với HPROF dump thông thường; dùng allocation profiler/JFR nếu cần đường gọi tạo object.
5. **“Chỉ cần một heap dump là chứng minh leak.”** Chưa đủ: cần so với vòng đời mong đợi, xu hướng và đường giữ sống.
6. **“Giải phóng Java heap chắc chắn giảm ngay RSS.”** Sai: JVM có thể giữ vùng heap đã commit và RSS còn bao gồm native memory; hai số liệu không đồng nhất.
7. **“Có cờ -all thì tất cả số liệu giữa các công cụ phải giống nhau.”** Sai: khác thời điểm, cách GC, phạm vi đối tượng, sampling và overhead nên không thể ép số lượng bằng nhau.

## 9. Tự kiểm tra cách chọn công cụ

- Cần biết **cache nào giữ 500.000 đối tượng cũ**: thu heap dump, xem dominator tree và paths to GC roots; histogram chỉ giúp định vị class.
- Cần biết **phương thức nào tạo 1 GB object tạm mỗi phút**: thu JFR/allocation profile có stack trace, phân tích thời gian và trọng số mẫu.
- Cần **xem class nào có số lượng tăng nhanh** trước khi quyết định dump: so sánh class histogram ở các thời điểm cùng điều kiện.
- Cần điều tra **RSS tăng trong khi Java heap sau GC không tăng**: bổ sung phân tích native memory/off-heap; ba công cụ tập trung vào Java object không giải thích đầy đủ mọi vùng nhớ tiến trình.

### Tài liệu tra cứu

- [Oracle JDK 21 — jcmd: GC.heap_dump, GC.class_histogram và JFR.start](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — jfr command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle — Troubleshoot Memory Leaks và OldObjectSample](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html)
- [Eclipse Memory Analyzer — Finding Memory Leak](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html)
