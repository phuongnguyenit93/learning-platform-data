# G1 Full GC song song: Đánh dấu đối tượng sống và dồn bộ nhớ trong Full GC (Java 10+)

## 1. Mục tiêu và kết luận quan trọng

Khi ứng dụng Java sử dụng **Garbage-First Garbage Collector (G1)**, phần lớn các lần thu gom bình thường là **young GC** hoặc **mixed GC** theo từng nhóm vùng (*regions*), có kết hợp với một chu kỳ **concurrent marking** để theo dõi các đối tượng đang sống. Tuy nhiên, khi G1 không thể thu hồi bộ nhớ đủ nhanh hoặc gặp tình huống nghiêm trọng, nó có thể phải thực hiện **Full GC**: một phép thu gom toàn bộ heap, thường gây ra **stop-the-world (STW)** đáng kể.

Từ **Java 10**, **JEP 307 — Parallel Full GC for G1** đã cho G1 thực hiện công việc Full GC theo hướng **mark–sweep–compact song song**, cải thiện tình huống trước đây khi nhiều công đoạn Full GC phải thực hiện bởi một luồng.

**Hai khái niệm không được nhầm:**

- **Song song (*parallel*)**: nhiều **GC worker threads** cùng làm việc, trong khi **application threads đang bị tạm dừng** ở Full GC.
- **Đồng thời với ứng dụng (*concurrent*)**: GC làm một phần công việc **trong lúc application threads vẫn chạy** — mô tả một số giai đoạn khác của G1, **không có nghĩa Full GC ngừng là STW**.

**Nhớ:** Full GC của G1 trên HotSpot hiện hành vẫn là cơ chế **dự phòng tốn kém**, dù đã được song song hóa. Mục tiêu vận hành tốt là **tránh Full GC lặp lại thường xuyên**, không phải buộc Full GC chạy liên tục để “dọn sạch heap”.

### Bốn pha cốt lõi cần hiểu

~~~text
[1] Mark live objects
    Tìm những object còn reachable từ GC roots
          |
          v
[2] Prepare for compaction
    Xác định vùng/địa chỉ đích, kế hoạch dồn đối tượng còn sống
          |
          v
[3] Adjust pointers
    Sửa các tham chiếu đến địa chỉ mới theo kế hoạch
          |
          v
[4] Compact heap
    Di chuyển/cô đặc dữ liệu còn sống, giải phóng khoảng trống
          |
          v
    Phục hồi/cập nhật cấu trúc VM và tiếp tục ứng dụng
~~~

Đây là **bốn pha chính** của thuật toán G1 Full GC mà người học cần hiểu. Trên JDK hiện đại, log còn có thể in thêm pha nội bộ như **`Phase 5: Reset Metadata`**; **không nên gắn cứng rằng mọi phiên bản JDK chỉ có đúng bốn dòng log**.

## 2. Bối cảnh: G1 chia heap thành các region

G1 quản lý Java heap bằng những vùng liên tục gọi là **heap regions**. Các vùng có thể thuộc nhóm:

- **Eden**: nơi thường bắt đầu cấp phát đối tượng thông thường.
- **Survivor**: nơi lưu đối tượng sống sót qua một số lần young GC.
- **Old**: lưu đối tượng sống lâu hơn.
- **Humongous**: các đối tượng rất lớn chiếm một hoặc nhiều region theo quy tắc của G1.
- **Free**: các region chưa được sử dụng hoặc đã thu hồi.

G1 chủ yếu dọn **theo region**, thay vì phải quét/dồn cả heap mỗi lần. Trong young/mixed GC, G1 chọn một **collection set** và thường **evacuate** đối tượng còn sống từ các vùng nguồn sang vùng đích mới. Khi một vùng đã evacuate thành công, vùng nguồn có thể được giải phóng.

**Full GC khác ở phạm vi và chi phí**: đây là đường thu gom dự phòng trên **toàn heap**, thực hiện đánh dấu và compaction để thu hồi vùng trống khi quy trình incremental thông thường không giải quyết được áp lực bộ nhớ.

### Vì sao Full GC xảy ra?

Một số nhóm nguyên nhân thường gặp:

1. **Allocation pressure**: ứng dụng tạo đối tượng hoặc chuyển đối tượng sang old generation nhanh hơn G1 kịp thu hồi.
2. **Evacuation failure**: thiếu không gian đích phù hợp để sao chép các object còn sống khi một collection set được xử lý.
3. **Concurrent marking hoàn thành quá muộn**: chưa kịp xác định/thu hồi đủ old regions trước khi ứng dụng cần thêm bộ nhớ.
4. **Humongous allocation và fragmentation**: đối tượng lớn cần các vùng liên tục, khiến heap còn tổng byte trống nhưng không còn bố cục thích hợp.
5. **Yêu cầu Full GC rõ ràng từ ứng dụng hoặc công cụ**, ví dụ `System.gc()` trong một cấu hình HotSpot cho phép yêu cầu đó.

Trong thực tế, cần **đọc GC log để xác nhận nguyên nhân**. Không phải mọi Full GC đều đến từ `OutOfMemoryError`; và `OutOfMemoryError` cũng không nhất thiết đồng nghĩa một Full GC hữu ích vừa hoàn tất.

### G1 có luôn là collector mặc định?

Trên các JDK hiện đại, G1 thường là lựa chọn mặc định, nhưng **đừng phụ thuộc ngầm** vào điều đó khi học một tính năng của G1. Có thể chọn rõ ràng:

~~~bash
java -XX:+UseG1GC -version
~~~

Điều này cũng hữu ích trong môi trường container hoặc các máy cấu hình khác nhau. Hãy kiểm tra log `Using G1` hoặc thông tin JVM khi muốn xác nhận collector thực sự được chọn.

## 3. “Đối tượng sống” có nghĩa là gì?

**Live object** trong ngữ cảnh GC là một đối tượng được xem là **còn reachable** theo các quy tắc reachability và xử lý reference của JVM, hoặc cần được giữ theo những quy tắc collector áp dụng.

Một cách hình dung thường gặp:

~~~text
GC roots
  |
  +--> A --> B --> C
  |          |
  |          +--> D
  |
  +--> E

X --> Y    (không có đường đi từ GC roots)
~~~

- `A`, `B`, `C`, `D`, `E`: reachable từ tập GC roots trong sơ đồ, là những đối tượng cần giữ.
- `X`, `Y`: không reachable từ roots qua các **strong references** trong ví dụ; chúng là ứng viên để thu hồi sau khi GC xét các quy tắc liên quan.
- Một **chu kỳ tham chiếu** giữa các object, chẳng hạn `X → Y → X`, **không tự giúp chúng sống** nếu không có đường đi phù hợp từ roots.

Java GC không đơn thuần sử dụng “reference count”. Một đồ thị object có vòng lặp nhưng không còn reachable vẫn có thể bị thu gom.

### GC roots đến từ đâu?

Tùy HotSpot và điều kiện thực thi, các loại roots bao gồm hoặc liên quan đến:

- Tham chiếu trong **stack frames / local variables** của các Java threads khi còn được xem là đang sử dụng.
- Các **static references** thuộc những lớp còn thích hợp trong bộ nạp lớp.
- **JNI/global handles**, một số VM handles và cấu trúc root khác do JVM quản lý.
- Những tham chiếu cần giữ từ các thread hoặc nội bộ VM.

Không nên coi **mọi biến local đã viết trong mã nguồn** đều nhất thiết là root đến cuối lexical scope: JIT có thể phân tích **liveness** và nhận ra một object không còn cần thiết trước khi biến thoát phạm vi. Khi cần bảo đảm một object còn strongly reachable đến một điểm cụ thể trong chương trình, Java có `Reference.reachabilityFence(object)`.

### `static` và reachability

~~~java
static final java.util.Map<String, Object> CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
~~~

Nếu ứng dụng giữ hàng triệu object qua một static cache, các object đó có thể tiếp tục reachable; Full GC **không tự xóa** chúng chỉ vì “đã chạy xong một lần Full GC”.

**GC không hiểu giá trị nghiệp vụ:** một object trong cache có thể đã “hết hạn” theo ứng dụng nhưng nếu vẫn bị giữ bởi strong references thì JVM không có lý do tự suy ra nó có thể bị thu hồi. Ứng dụng phải quản lý eviction, TTL hoặc loại bỏ reference theo chính sách của cache.

## 4. Pha 1 — `Mark live objects`

**Marking** xác định những object còn được xem là sống bằng cách duyệt các **đường tham chiếu** bắt đầu từ GC roots.

Ở mức khái niệm:

1. Thu thập/tổ chức các root cần quét trong một pha Full GC.
2. Theo các tham chiếu từ root đến object.
3. Ghi nhận object đã gặp là reachable, tránh lặp vô hạn với những đồ thị có chu kỳ.
4. Duyệt tiếp các tham chiếu bên trong object được đánh dấu.
5. Hợp tác với cơ chế xử lý `SoftReference`, `WeakReference`, `PhantomReference` và những cấu trúc VM liên quan theo quy tắc phù hợp.
6. Tạo thông tin **liveness** để các pha sau quyết định object nào còn phải giữ và có thể di chuyển.

**Không được hiểu “mark” là gọi Java method `mark()` trên từng business object.** Đây là công việc bên trong collector; chương trình Java không được tự sắp xếp hay đặt vị trí bộ nhớ vật lý cho object.

### Vì sao có thể chạy song song?

JEP 307 cho phép nhiều GC worker hợp tác quét roots/đồ thị object và đánh dấu những phần phù hợp. Công việc có thể chia theo đối tượng, region, tasks hoặc các cơ chế phân phối tải nội bộ của HotSpot.

Điểm lợi là có thể khai thác nhiều CPU để xử lý một heap với nhiều object sống nhanh hơn so với chỉ một worker, tùy mức độ song song thực tế và khả năng cân bằng công việc.

**Nhưng song song không có nghĩa mọi công việc được chia đều hoàn hảo.** Các giai đoạn đồng bộ, tranh chấp, áp lực băng thông bộ nhớ và các phần việc tuần tự vẫn ảnh hưởng tổng thời gian dừng ứng dụng.

### Mark của Full GC khác `concurrent marking` thông thường

| Nội dung | G1 concurrent marking | Pha 1 của G1 Full GC |
| --- | --- | --- |
| Bối cảnh | Chu kỳ thu gom bình thường, chuẩn bị old-region candidates | Đường Full GC dự phòng |
| Application threads | Có thời đoạn tiếp tục chạy đồng thời với GC | Bị dừng trong Full GC STW |
| Phạm vi | Theo dõi liveness cho chu kỳ G1, nhiều bước | Xác định live set cho Full GC |
| Sau marking | Remark/Cleanup, rồi thường có young/mixed collections | Chuẩn bị compaction, sửa tham chiếu, compact |
| Tính chất cần nhớ | **Mostly concurrent** | **Parallel stop-the-world** |

**Không gộp hai thuật toán** chỉ vì cả hai đều có từ “marking”. Pha marking của Full GC chạy theo chuỗi thao tác khác với các bước Concurrent Start → Concurrent Mark → Remark → Cleanup trong chu kỳ bình thường của G1.

## 5. Pha 2 — `Prepare compaction`

Sau khi biết những object nào còn sống, G1 chuẩn bị **kế hoạch dồn bộ nhớ**.

Giả sử một vùng heap được biểu diễn đơn giản:

~~~text
Trước Full GC (mô hình minh họa):

| sống A | rác X | sống B | rác Y | sống C | khoảng trống |

Sau khi dồn (ý tưởng):

| sống A | sống B | sống C |      khoảng trống lớn hơn     |
~~~

Đây là **sơ đồ khái niệm**, không phải mô tả chính xác từng byte hoặc việc G1 bắt buộc phải dồn mọi region theo một thứ tự cố định.

Pha chuẩn bị thường cần:

- Xác định **region và đối tượng sống** nào thuộc phạm vi cần dồn.
- Xác định **điểm bắt đầu và vùng đích (*compaction points/destinations*)**.
- Tính **địa chỉ đích dự kiến** cho object đủ điều kiện di chuyển.
- Chuẩn bị **forwarding information** để các pha cập nhật tham chiếu biết đích đến mới.
- Phân phối công việc chuẩn bị giữa các GC workers theo khả năng triển khai.
- Xử lý riêng những tình huống cần thiết để tránh thiếu bộ nhớ hoặc đảm bảo an toàn khi di chuyển.

### Dồn bộ nhớ có phải cấp phát heap mới không?

**Không nhất thiết.** Tài liệu Oracle gọi Full GC của G1 là **in-place full heap compaction**: collector có thể dồn trong cấu trúc heap hiện có theo quy tắc của nó. Điều này khác đường **evacuation** thông thường khi G1 sao chép các live objects giữa các regions được chọn.

Không phải “Full GC tạo thêm RAM” theo nghĩa cấp phát vô hạn: nó chủ yếu **thu hồi không gian bị object chết chiếm giữ và/hoặc giảm phân mảnh**, tạo điều kiện cho những allocation tiếp theo.

### Có cần mọi object đều di chuyển không?

Không. Một object có thể **đã ở vị trí phù hợp**, một region có thể không được chọn cho compaction trong một điều kiện nhất định, và các ràng buộc như **pinned objects/humongous objects** có thể yêu cầu xử lý đặc biệt. Trên các bản HotSpot mới, có thể có đường tối ưu bỏ qua các bước adjust/compact khi không có mục tiêu compaction.

Không nên ghi “Full GC bắt buộc di chuyển tất cả live objects” như một luật Java.

## 6. Pha 3 — `Adjust pointers`

Nếu các đối tượng được dồn sang **địa chỉ mới**, những tham chiếu trỏ tới chúng phải được cập nhật để **giữ nguyên quan hệ đồ thị** của chương trình.

Ví dụ:

~~~text
Trước:
root --> A @1000
          |
          +--> B @5000

Dự kiến sau compaction:
A @1000 hoặc vị trí mới
B @2000

Tham chiếu A.next phải cập nhật
để vẫn chỉ đúng B.
~~~

Ở đây các số `1000`, `5000`, `2000` **chỉ là số minh họa**, không phải địa chỉ bạn có thể lấy trực tiếp bằng Java chuẩn.

Pha `Adjust pointers` dùng thông tin vị trí mới đã tính để sửa các **reference fields**, roots, handles và các cấu trúc tham chiếu khác mà thuật toán yêu cầu.

**Điều quan trọng nhất:** ứng dụng vẫn thấy cùng **đồ thị object về mặt ngữ nghĩa**, ngay cả khi collector di chuyển dữ liệu vật lý:

~~~java
Node tail = head.next.next;

System.gc();

System.out.println(head.next.next == tail); // true trong demo
~~~

Dòng trên minh họa một tình huống với các đối tượng còn strongly reachable. Đừng suy rằng `==` giữa hai tham chiếu trong cùng JVM nói lên object **không bị di chuyển**: collector đảm bảo tham chiếu Java theo logic vẫn trỏ đúng object tương ứng.

### Vì sao không chỉ dời object rồi sửa reference sau?

Nếu di chuyển một object mà không điều chỉnh các tham chiếu liên quan, một tham chiếu có thể chỉ tới vị trí cũ — đó là **không hợp lệ**. Pha tính đích/điều chỉnh tham chiếu phối hợp với compaction theo các cơ chế HotSpot nhằm duy trì tính đúng đắn.

**Không viết code Java tự thay địa chỉ tham chiếu**. JVM chịu trách nhiệm việc cập nhật ở mức GC; chương trình chỉ làm việc qua object references hợp lệ.

## 7. Pha 4 — `Compact heap`

Sau khi có thông tin live objects và chuẩn bị tham chiếu, G1 thực hiện **dồn các object phù hợp** để gom lại các khoảng bộ nhớ trống.

~~~text
Ban đầu (đơn giản hóa):
[Live][Dead][Live][Dead][Live][Dead]

Sau compaction:
[Live][Live][Live][          Free          ]
~~~

Những khoảng bị object chết chiếm dụng có thể được thu hồi, còn các live objects giữ được **trạng thái logic** của chúng.

### Compaction giúp gì?

- **Giảm phân mảnh nội bộ/giữa các vùng** trong những trường hợp áp lực bộ nhớ.
- **Thu hồi không gian** mà unreachable objects đã chiếm.
- **Tạo những đoạn/vùng trống phù hợp hơn** cho cấp phát tiếp theo.
- **Làm ổn định khả năng cấp phát** nếu heap còn đủ chỗ sau dọn.

**Không bảo đảm** Full GC luôn tạo ra đủ bộ nhớ. Nếu phần lớn heap vẫn chứa live objects hoặc còn ràng buộc về humongous allocations, Full GC có thể rất tốn thời gian nhưng thu hồi ít. Khi không thể cấp phát dù đã thử GC, ứng dụng vẫn có thể gặp `OutOfMemoryError`.

### Dồn bộ nhớ không làm mất identity Java

Trong một JVM, object có **identity** của nó. GC có thể di chuyển byte vật lý nhưng Java reference vẫn giữ cùng ngữ nghĩa:

~~~java
int stableHash = System.identityHashCode(head);

// Có thể xảy ra GC và di chuyển đối tượng.
System.gc();

boolean same = stableHash == System.identityHashCode(head);
~~~

**Điểm rất quan trọng:** `System.identityHashCode` **không phải địa chỉ bộ nhớ**. Việc nó không đổi **không chứng minh object không bị di chuyển**. Nó chỉ kiểm tra một đặc tính identity hash được JVM duy trì cho đối tượng đang sống.

Nếu muốn quan sát di chuyển vật lý, phải dùng công cụ/chẩn đoán VM thích hợp và hiểu rủi ro; không sử dụng `identityHashCode` như một bộ đo địa chỉ heap.

## 8. Các pha nội bộ sau compaction trong HotSpot mới

Tài liệu JEP 307 và nhiều giải thích nền tảng mô tả **bốn bước chính**:

1. Mark live objects.
2. Prepare for compaction.
3. Adjust pointers.
4. Compact heap.

Tuy nhiên, **một log JDK 24 được kiểm thử** còn cho:

~~~text
Phase 5: Reset Metadata
~~~

Một số nhánh mã nguồn HotSpot hiện hành có thể điều kiện hóa các công đoạn như adjust/compact khi không có region cần dồn, và thực hiện thêm cleanup/reset metadata. Đây là **chi tiết triển khai có thể thay đổi**.

Do đó:

- Học **bốn pha cốt lõi** để hiểu cơ chế của JEP 307.
- Khi vận hành, **đọc pha thực tế từ GC log** của JDK đang chạy.
- Không viết parser log chỉ chấp nhận đúng bốn pha và xem pha thứ năm là lỗi.
- Không dùng tên pha của một thuật toán GC khác, như Serial GC hoặc Parallel GC, để gán vô điều kiện cho G1 Full GC.

## 9. Parallel Full GC có phải concurrent với ứng dụng không?

**Không.** Đây là phân biệt quan trọng nhất của “G1 Full GC song song”.

~~~text
Thời gian -->

Application threads: [RUN] [STW--------------------] [RUN]
GC workers       :          [MARK][PLAN][FIX][MOVE]
                                  cùng làm song song
~~~

Trong phần **STW**, các Java application threads phải tạm dừng, dù nhiều GC workers đang cùng hoạt động. Tăng số GC workers có thể rút ngắn thời gian xử lý song song khi CPU và băng thông bộ nhớ cho phép, nhưng **không biến pause thành 0 ms**.

### `-XX:ParallelGCThreads`

Số worker được G1 sử dụng cho các công việc parallel GC được **giới hạn/điều khiển** bởi lựa chọn:

~~~bash
-XX:ParallelGCThreads=2
~~~

Tùy chọn này **không chỉ ảnh hưởng Full GC**, mà còn có thể ảnh hưởng những GC pauses khác. Số workers thực tế được sử dụng có thể được HotSpot điều chỉnh theo quy mô heap, số CPU và tình huống.

**Khuyến nghị hiện hành:** bắt đầu bằng **default G1 ergonomics**. Chỉ sửa `ParallelGCThreads` nếu đo đạc cho thấy có lý do rõ ràng; đặt worker quá cao có thể gây contention hoặc làm chậm ứng dụng trong những hệ thống giới hạn CPU.

### `-XX:ConcGCThreads` khác gì?

- `ParallelGCThreads` liên quan các giai đoạn GC **parallel**, đặc biệt ở STW.
- `ConcGCThreads` liên quan số luồng làm việc **concurrent** với ứng dụng, chẳng hạn chu kỳ concurrent marking.
- Điều chỉnh `ConcGCThreads` không phải cơ chế trực tiếp để biến **Pha 1 của Full GC** thành concurrent hay “bật Full GC đa luồng”.

Hãy dựa vào GC logs và tài liệu của collector đang dùng, không suy từ tên một flag sang một pha hoàn toàn khác.

## 10. Ví dụ Java hoàn chỉnh: đồ thị sống sót và Full GC thật

Tệp **`G1FullGcMarkCompactDemo.java`** dưới đây cố tình tạo ra **một đồ thị đối tượng còn reachable** và **một tập byte arrays tạm thời**. Sau khi loại bỏ reference tới tập tạm, chương trình **yêu cầu** GC để quan sát log. Đây là **bài lab**, không phải mẫu code nên dùng để gọi `System.gc()` liên tục trong dịch vụ production.

~~~java
import java.lang.ref.Reference;
import java.util.ArrayList;
import java.util.List;

public final class G1FullGcMarkCompactDemo {

    static final class Node {
        final int value;
        Node next;
        final byte[] payload = new byte[1024];

        Node(int value) {
            this.value = value;
        }
    }

    private static int total(Node n) {
        int sum = 0;

        while (n != null) {
            sum += n.value;
            n = n.next;
        }
        return sum;
    }

    public static void main(String[] args) {
        // Đồ thị được giữ strong reference qua head/tail.
        Node head = new Node(10);
        head.next = new Node(20);
        head.next.next = new Node(30);
        Node tail = head.next.next;

        int identityBefore = System.identityHashCode(head);

        // Tạo dữ liệu tạm có thể bị thu gom khi không còn dùng.
        List<byte[]> temporary = new ArrayList<>();

        for (int i = 0; i < 12000; i++) {
            temporary.add(new byte[1024]);
        }

        System.out.println(
                "temporaryAllocated=" + temporary.size());

        // Không còn giữ strong reference tới tập temporary.
        temporary = null;

        System.out.println(
                "graphSumBefore=" + total(head));

        // Chỉ là yêu cầu GC: lựa chọn JVM có thể ảnh hưởng.
        System.gc();

        System.out.println(
                "graphSumAfter=" + total(head));

        System.out.println(
                "tailStillReachable=" + (head.next.next == tail));

        System.out.println(
                "identityPreserved="
                + (identityBefore == System.identityHashCode(head)));

        // Giữ các references cần thiết đến cuối phép thử.
        Reference.reachabilityFence(head);
        Reference.reachabilityFence(tail);
    }
}
~~~

### Chạy bằng JDK 17+

Biên dịch:

~~~bash
javac G1FullGcMarkCompactDemo.java
~~~

Để yêu cầu Full GC và in các pha trên HotSpot G1, chạy:

~~~bash
java -XX:+UseG1GC -XX:-ExplicitGCInvokesConcurrent \
  -Xms64m -Xmx64m -XX:ParallelGCThreads=2 \
  -Xlog:gc=info,gc+phases=info \
  G1FullGcMarkCompactDemo
~~~

Dấu `\` ở cuối dòng là cách nối lệnh trong **bash/zsh**. Với **PowerShell**, dùng một dòng:

~~~text
java -XX:+UseG1GC -XX:-ExplicitGCInvokesConcurrent -Xms64m -Xmx64m -XX:ParallelGCThreads=2 -Xlog:gc=info,gc+phases=info G1FullGcMarkCompactDemo
~~~

**Các tùy chọn này chỉ dành cho bài kiểm thử**:

- `-XX:+UseG1GC`: chọn G1 rõ ràng.
- `-XX:-ExplicitGCInvokesConcurrent`: không chuyển yêu cầu explicit GC thành một concurrent collection.
- `-Xms64m -Xmx64m`: chọn heap nhỏ và cố định cho lab.
- `-XX:ParallelGCThreads=2`: giới hạn mức parallelism cho mục đích quan sát.
- `-Xlog:gc=info,gc+phases=info`: in sự kiện GC và thời gian các pha.

**Không phải Java SE bắt buộc `System.gc()` phải thực hiện Full GC.** Có thể có các cấu hình như `-XX:+DisableExplicitGC` khiến yêu cầu bị bỏ qua, hoặc các collector khác giải quyết theo cách khác. Trong bài lab đã kiểm thử bằng **HotSpot JDK 24**, lệnh trên thực sự tạo một **G1 Full GC**.

### `stdout` của chương trình (không tính GC logs)

~~~text
temporaryAllocated=12000
graphSumBefore=60
graphSumAfter=60
tailStillReachable=true
identityPreserved=true
~~~

**Đã xác minh trực tiếp trên JDK 24**: năm dòng từ chương trình đúng như trên. Những dòng log GC xuất hiện xen giữa theo thời gian và **không phải một phần stdout cố định** cần copy từng ký tự.

### Mẫu log G1 Full GC đã quan sát

~~~text
[info][gc] Using G1
GC(0) Phase 1: Mark live objects ...
GC(0) Phase 2: Prepare compaction ...
GC(0) Phase 3: Adjust pointers ...
GC(0) Phase 4: Compact heap ...
GC(0) Phase 5: Reset Metadata ...
GC(0) Pause Full (System.gc()) 14M->1M(64M) ...
~~~

Các dấu `...` thay thế **timestamp, mức log, thời gian từng pha và tổng pause**, không phải một stdout nguyên văn. Trong lần thử cụ thể, các pha đã xuất hiện theo thứ tự và heap báo `14M->1M(64M)`. **Số MB và thời gian có thể khác theo JDK/GC ergonomics/lần chạy**, vì vậy không được đưa vào assertion bắt buộc.

### Bài test này chứng minh điều gì?

- Đồ thị `head → next → next` còn reachable: tổng các giá trị vẫn là `60`.
- `tailStillReachable=true`: các tham chiếu Java vẫn nhất quán sau khi GC.
- `identityPreserved=true`: identity hash của `head` được giữ; **không nói địa chỉ vật lý không đổi**.
- `temporary` không còn được ứng dụng giữ strong reference sau khi gán `null`, trở thành ứng viên thu gom theo liveness thực tế.
- Log chứng minh **GC Full** và **các pha marking/compaction** đã xảy ra trong cấu hình kiểm thử.

**Bài test không chứng minh một địa chỉ cụ thể trước/sau**, không bảo đảm mọi array tạm đều được thu hồi tức thì, và không chứng minh mức tăng tốc parallel so với serial. Muốn đánh giá lợi ích song song cần benchmark có kiểm soát.

## 11. “Đánh dấu” không phải “xóa ngay”

Một đối tượng unreachable theo strong references không có nghĩa **ngay tại dòng gán null** nó bị xóa tức thời. JVM có thể thu gom **khi GC thực sự thực hiện** theo chính sách và điều kiện bộ nhớ.

~~~java
Object temporary = new Object();
temporary = null;
~~~

Dòng `temporary = null` **không trực tiếp gọi GC**, không yêu cầu dồn heap, và không làm cho một object được di chuyển ngay lúc đó. Nó chỉ thay tham chiếu trong chương trình.

### Weak/Soft/Phantom References

`WeakReference` và các loại reference đặc biệt có quy tắc thu gom/nhận thông báo riêng. Không được đơn giản mô tả:

~~~text
Object không còn strong reference => chắc chắn weak.get() là null ngay
~~~

Thực tế còn phụ thuộc GC có chạy hay chưa, thời điểm xử lý reference và các bảo đảm của loại reference đó.

Đối với demo có `WeakReference`, nếu in kết quả `weak.get() == null` sau một lời gọi `System.gc()` thì giá trị không phải lúc nào cũng là một **stdout có thể cam kết trên mọi JDK và cấu hình**. Vì vậy chương trình chính của bài chỉ in các tính chất ổn định của đồ thị còn reachable và để GC log làm bằng chứng thu gom.

### Có phải rác là “object không còn được dùng về mặt nghiệp vụ”?

Không nhất thiết. GC chỉ biết **reachability và các quy tắc reference**. Nếu một object đã hết hạn theo nghiệp vụ nhưng vẫn được giữ bởi `static Map` hoặc một listener chưa hủy đăng ký, nó có thể tiếp tục sống. Đây là một dạng **memory retention/leak theo ứng dụng** mà Full GC không thể tự sửa.

## 12. Một đồ thị có chu kỳ vẫn được thu gom

Xét:

~~~java
final class Node {
    Node next;
}

Node a = new Node();
Node b = new Node();

a.next = b;
b.next = a;

a = null;
b = null;
~~~

Sau khi không còn đường từ GC roots đến cặp object ở ví dụ, cả chu kỳ có thể được xem là unreachable. Thuật toán mark theo reachability **không phải reference counting**; nó có thể xác định cả hai không còn thuộc tập live.

**Không được suy:** “hai object trỏ qua lại nên GC không thể thu gom”. Các GC truy vết hiện đại được thiết kế để xử lý chu kỳ tham chiếu.

Đây là **mảnh mã minh họa** đặt trong phương thức, không có `main`; không nên mong nó tạo stdout khi chạy độc lập.

## 13. Không nhầm compact với evacuation trong young/mixed GC

G1 thực hiện hai kiểu di chuyển đối tượng mà người học dễ trộn lẫn.

### Young/mixed collection

- G1 chọn **collection set** gồm young regions và đôi khi old regions.
- Trong **evacuation**, live objects thường được **sao chép sang region đích**.
- Sau khi thành công, vùng nguồn được giải phóng.
- Collection thường xử lý **một phần heap**, với mục tiêu phân phối công việc qua nhiều pauses ngắn hơn.

### Full GC

- **Đường toàn heap**, hoạt động khi không thể thu hồi đủ theo con đường thông thường hoặc có yêu cầu Full GC.
- Thực hiện các pha **mark → prepare → adjust → compact**.
- Theo mô tả Oracle, đây là **in-place stop-the-world full heap compaction**.
- Dù parallel, nó có thể kéo dài và vi phạm pause-time target của G1.

| Tiêu chí | Young/Mixed GC | G1 Full GC |
| --- | --- | --- |
| Mức độ thường gặp | Đường xử lý bình thường của G1 | Dự phòng, nên hạn chế |
| Phạm vi | Collection set chọn từ heap regions | Toàn heap |
| Phương pháp thu hồi chính | Evacuate live objects khỏi vùng nguồn | Mark live objects và compaction |
| Mục tiêu pause | Phân phối công việc để gần mục tiêu | Có thể là pause dài |
| Song song | Có | Có từ Java 10 |
| Đồng thời với application threads trong collection pause? | Không ở phần STW | Không trong Full GC STW |

**Lưu ý:** G1 là một bộ thu gom “mostly concurrent”, không có nghĩa **mỗi thao tác của nó luôn chạy concurrent**. Đây là lý do cần dùng **tên phase trong log** thay vì suy từ tên bộ GC.

## 14. Khi nào compaction không thể giải quyết vấn đề?

### Live set quá lớn

Nếu heap 1 GB nhưng ứng dụng còn giữ hơn 950 MB dữ liệu thực sự sống, Full GC không thể biến phần dữ liệu sống đó thành rác. Nó có thể tiêu tốn nhiều CPU/latency mà chỉ lấy lại rất ít.

### Humongous allocations và fragmentation

G1 có cách xử lý riêng cho những object rất lớn, có thể chiếm nhiều regions. Một đối tượng humongous còn reachable có thể hạn chế cách tổ chức vùng và gây áp lực tìm không gian liên tục. Trường hợp này có thể dẫn tới **Full GC hoặc `OutOfMemoryError`** dù số byte “trống” nhìn tổng quan chưa về 0.

### Đối tượng bị giữ ngoài ý muốn

Ví dụ cache không giới hạn, listener leak hoặc queue không được rút phần tử sẽ giữ objects reachable. Full GC không biết những entries này đã “không còn hữu ích” đối với nghiệp vụ.

### Cấu hình heap quá nhỏ

Khi `-Xmx` không đủ so với peak live set, GC phải chạy quá thường xuyên. Thêm parallelism có thể giảm một phần pause của từng Full GC, nhưng **không bù đắp được việc không có đủ bộ nhớ để lưu dữ liệu sống**.

## 15. Đọc GC log để phát hiện Full GC và các pha

Với HotSpot hiện hành, cơ chế thống nhất logging **`-Xlog`** là lựa chọn phù hợp để quan sát.

### Log cơ bản

~~~bash
java -XX:+UseG1GC -Xlog:gc=info -jar app.jar
~~~

Nếu có Full GC, có thể thấy một dòng kiểu:

~~~text
GC(123) Pause Full (G1 Compaction Pause) ...
~~~

Hoặc khi được kích hoạt theo cách khác, log có thể nói:

~~~text
GC(0) Pause Full (System.gc()) ...
~~~

**Tên nguyên nhân phụ thuộc sự kiện thực tế**. Đừng viết parser chỉ dò `G1 Compaction Pause` rồi bỏ sót những Full GC có nguyên nhân khác.

### Log các pha

~~~bash
java -XX:+UseG1GC -Xlog:gc=info,gc+phases=info -jar app.jar
~~~

Hoặc chi tiết hơn để tìm bottleneck:

~~~bash
java -XX:+UseG1GC '-Xlog:gc*=debug' -jar app.jar
~~~

Dấu quote ở ví dụ thứ hai nhằm tránh shell mở rộng ký tự `*` trong một số môi trường. Nếu ghi `-Xlog` ra file, hãy dùng cơ chế rotation để log không tăng vô hạn.

**Những dòng đáng tìm:**

- `Pause Full`: sự kiện Full GC.
- `Phase 1: Mark live objects`: công việc marking.
- `Phase 2: Prepare compaction` hoặc cách ghi gần tương đương: tính công việc dồn.
- `Phase 3: Adjust pointers`: điều chỉnh tham chiếu.
- `Phase 4: Compact heap`: thực hiện dồn.
- Các pha VM bổ sung, ví dụ `Phase 5: Reset Metadata` ở JDK 24 kiểm thử.
- `usedBefore->usedAfter(capacity)`: số heap used trước/sau cùng capacity trong log, **không đồng nghĩa bộ nhớ hệ điều hành RSS giảm ngay**.

### Đánh giá áp lực GC

Một log:

~~~text
Pause Full ... 510M->500M(512M) ...
~~~

minh họa tình huống **thu hồi rất ít** dù heap gần đầy. Cần xét live set, cache, allocation rate, humongous regions và cấu hình heap. **Không** chỉ tăng `ParallelGCThreads` rồi mong mọi vấn đề hết.

Đây là **số liệu giả lập** dùng để đọc định dạng log, không phải kết quả benchmark hoặc một số đo thực tế của bài.

## 16. Điều chỉnh hiệu năng: ưu tiên tránh Full GC

Theo **Oracle Java SE 26 G1 GC Tuning**, mặc định G1 đã được cân bằng cho nhiều ứng dụng. Khi gặp Full GC dài hoặc nhiều, nên điều tra có bằng chứng, theo thứ tự hợp lý:

1. **Xem tần suất và nguyên nhân Full GC** qua GC log.
2. **Quan sát heap occupancy và lượng memory được thu hồi** trước/sau từng pause.
3. **Xem allocation rate**, promotion lên old generation và số lượng humongous objects.
4. **Kiểm tra memory retention của ứng dụng**: caches, collections không giới hạn, session leak, queues...
5. **Kiểm tra heap sizing**: `-Xmx` có đủ cho live set và allocation burst không?
6. **Kiểm tra tiến độ concurrent marking**: có hoàn tất đủ sớm để G1 chọn old regions thu hồi không?
7. **Xem nguyên nhân evacuation failure** và khả năng tìm các destination regions.
8. **Đo trên môi trường đại diện**, trước/sau mỗi thay đổi.

### Tối ưu phù hợp với nguyên nhân, không chạy theo flag

| Dấu hiệu | Hướng điều tra |
| --- | --- |
| Full GC sau evacuation failure | Heap headroom, allocation pressure, promotion, fragmentation |
| Full GC sau concurrent marking chậm | Tiến độ marking, old occupancy, cấu hình IHOP và concurrent workers khi có số liệu |
| Nhiều humongous objects | Kích thước object, vùng G1, cơ chế allocation/đời sống đối tượng |
| Full GC thu hồi rất ít | Live-set lớn, object retention, heap dump theo quy trình chẩn đoán |
| Full GC do `System.gc()` | Tìm code/thư viện/công cụ gọi explicit GC; đánh giá có nên loại bỏ hoặc cấu hình khác |
| Pause quá dài nhưng ít lần Full GC | Xem phase timing, CPU quota, heap lớn và số worker thực dùng |

**Đừng dùng `System.gc()` như “tối ưu bộ nhớ định kỳ”** trong môi trường production. Cơ chế này chỉ yêu cầu GC; lịch, chiến lược và hiệu quả còn phụ thuộc JVM/config, có thể tạo STW không cần thiết.

### `-XX:MaxGCPauseMillis` có khống chế Full GC không?

Không như một hard deadline. G1 có **pause-time goal** để điều chỉnh hoạt động bình thường, nhưng **không phải collector thời gian thực** và **Full GC có thể vượt xa mục tiêu**. Một Full GC bị áp lực live set lớn vẫn có thể rất dài dù bạn đặt pause goal thấp.

## 17. Lỗi hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Parallel Full GC nghĩa là ứng dụng chạy đồng thời với GC.” | Các **GC workers** chạy song song, ứng dụng vẫn **STW** trong Full GC. |
| “Full GC là chu kỳ concurrent marking thông thường.” | Không. Marking của Full GC là pha của đường thu gom toàn heap. |
| “Object chết thì được xóa đúng lúc gán reference thành null.” | Gán null chỉ làm thay đổi reference; GC thu hồi theo thời điểm thực thi. |
| “GC dùng reference count nên không xử lý vòng tròn.” | GC tracing xác định reachability; chu kỳ unreachable có thể thu hồi. |
| “Full GC luôn di chuyển tất cả object sống.” | Có những object/vùng không cần hoặc không thể di chuyển trong điều kiện nhất định. |
| “`identityHashCode` thay đổi nếu object bị compact.” | Identity hash được duy trì; nó không phải địa chỉ vật lý. |
| “Full GC tăng tốc Java vì heap càng sạch càng tốt.” | Full GC là STW đắt đỏ; cần tránh nếu không cần thiết. |
| “Thêm nhiều GC workers làm mọi pause ngắn theo tỷ lệ tuyến tính.” | Còn phần việc tuần tự, CPU quota, contention, bandwidth và heap size. |
| “`ParallelGCThreads` là số thread concurrent marking.” | Nó điều khiển công việc parallel; concurrent marking liên quan `ConcGCThreads`. |
| “G1 chỉ có Full GC từ Java 10.” | G1 đã có Full GC trước đó; Java 10 **song song hóa** đường Full GC. |
| “JDK mới luôn ghi đúng 4 pha.” | Log có thể có thêm pha nội bộ, như Reset Metadata. |
| “Full GC luôn giải phóng phần lớn heap.” | Nếu live set lớn, có thể giải phóng rất ít rồi gặp OOME. |
| “Giảm RSS ngay khi thấy heap used giảm.” | Java heap used không đồng nghĩa RSS/committed memory trả ngay cho OS. |
| “Log `Pause Full` chỉ do memory leak.” | Có thể do thiếu headroom, humongous fragmentation, explicit GC hay nguyên nhân khác. |
| “Đặt `-XX:MaxGCPauseMillis` nhỏ sẽ chặn Full GC dài.” | Đây là mục tiêu, không có deadline cứng cho Full GC. |
| “Thấy log Full GC là có thể xác nhận một object cụ thể đã chuyển địa chỉ.” | Log pha chứng minh hoạt động collector, không cho địa chỉ object theo Java chuẩn. |

## 18. Bài tập tự kiểm tra

### Câu 1 — Phân biệt loại thu gom

**Hỏi:** G1 chạy concurrent marking rồi young/mixed GC. Đây có tự động là một Full GC không?

**Đáp án:** Không. Đó là một phần chu kỳ bình thường của G1. Full GC là đường dự phòng toàn heap với STW compaction.

### Câu 2 — Parallel và concurrent

**Hỏi:** Từ Java 10, G1 Full GC “parallel” nghĩa là gì?

**Đáp án:** Nhiều GC worker threads có thể thực hiện các công việc Full GC song song để giảm worst-case pause, nhưng các Java application threads vẫn bị tạm dừng trong Full GC STW.

### Câu 3 — Marking

**Hỏi:** Hai đối tượng trỏ qua lại nhưng không reachable từ GC roots có được xem là sống chỉ vì có chu kỳ không?

**Đáp án:** Không. Thuật toán tracing xét reachability, không phải chỉ đếm reference.

### Câu 4 — Prepare compaction

**Hỏi:** Pha chuẩn bị cần thông tin gì sau marking?

**Đáp án:** Tập live objects/vùng liên quan, các vị trí đích và thông tin forwarding/compaction để các pha cập nhật tham chiếu và dời object thực hiện an toàn.

### Câu 5 — Adjust pointers

**Hỏi:** Vì sao JVM cần sửa reference khi object bị di chuyển?

**Đáp án:** Để các roots và các trường tham chiếu trong object vẫn chỉ đúng đối tượng logic sau khi nó có vị trí bộ nhớ mới.

### Câu 6 — Compact heap

**Hỏi:** Compaction có đảm bảo xóa mọi đối tượng ứng dụng không còn muốn dùng không?

**Đáp án:** Không. Đối tượng vẫn được giữ qua strong references là live theo reachability, ngay cả khi nghiệp vụ không còn dùng; cần bỏ retention ngoài ý muốn.

### Câu 7 — `identityHashCode`

**Hỏi:** Sau GC, identityHashCode giữ nguyên có chứng minh object không di chuyển vật lý?

**Đáp án:** Không. `System.identityHashCode` không phải địa chỉ bộ nhớ; JVM giữ identity dù object có thể di chuyển.

### Câu 8 — GC log

**Hỏi:** Dòng `Pause Full (System.gc())` khác `Pause Full (G1 Compaction Pause)` thế nào?

**Đáp án:** Đều có thể thuộc một G1 Full GC, nhưng **nguyên nhân được ghi khác nhau**. Để điều tra cần đối chiếu log, không chỉ tìm một chuỗi nguyên nhân.

### Câu 9 — Số pha

**Hỏi:** Nếu log JDK 24 có `Phase 5: Reset Metadata`, điều đó có phủ nhận mô hình 4 pha đánh dấu–dồn không?

**Đáp án:** Không. Bốn pha là các bước cốt lõi; runtime hiện đại còn có thể ghi công việc dọn metadata bổ sung.

### Câu 10 — Thu hồi ít

**Hỏi:** Heap `510M->500M(512M)` sau Full GC có nói điều gì?

**Đáp án:** Heap rất đầy và thu hồi ít; có thể live set lớn hoặc retention. Phải điều tra allocation, roots, cache và heap sizing; tăng GC workers không tự làm object trở thành rác.

### Câu 11 — Mã demo

**Hỏi:** Trong ví dụ `G1FullGcMarkCompactDemo`, vì sao `graphSumAfter=60` dù Full GC có thể dồn object?

**Đáp án:** `head` và `tail` được giữ reachable; GC có thể thay vị trí vật lý mà vẫn duy trì reference và dữ liệu logic.

### Câu 12 — Điều chỉnh production

**Hỏi:** Có nên gọi `System.gc()` mỗi vài giây để đảm bảo service “sạch rác” không?

**Đáp án:** Không. Nó có thể gây STW không cần thiết và làm giảm hiệu năng. Nên để GC tự vận hành, đo bằng log, và xử lý nguyên nhân memory pressure.

## 19. Checklist khi phân tích một G1 Full GC thật

1. **Xác nhận collector**: log hiển thị `Using G1` hay cấu hình `-XX:+UseG1GC`?
2. **Xác nhận sự kiện**: có `Pause Full` hay chỉ là Young/Mixed GC?
3. **Xác định nguyên nhân**: `System.gc()`, allocation pressure, evacuation failure, humongous allocation...
4. **Đọc pha 1**: thời gian mark live objects là bao nhiêu?
5. **Đọc pha 2**: công việc chuẩn bị compaction chiếm bao lâu?
6. **Đọc pha 3 và 4**: pointer adjustment và actual compaction mất bao nhiêu?
7. **Đọc các pha nội bộ bổ sung**: đừng bỏ qua reset/cleanup trên JDK mới.
8. **Đọc heap trước/sau**: Full GC thu hồi đáng kể hay chỉ rất ít?
9. **Xem tần suất**: Full GC có lặp lại sát nhau không?
10. **Tìm nguyên nhân ứng dụng**: cache, live set, tốc độ cấp phát, allocation burst, humongous objects.
11. **So sánh với pause goal**: tổng STW có vi phạm SLO/độ trễ không?
12. **Đánh giá giải pháp**: giảm retention, tăng heap/headroom khi hợp lý, giảm fragmentation hoặc tune GC có số liệu.
13. **Đo lại** bằng cùng workload và môi trường, tránh kết luận chỉ từ một lần chạy.

## 20. Tổng kết và tài liệu chính thức

- **JEP 307 (Java 10)** cải tiến **G1 Full GC** bằng cách **song song hóa mark–sweep–compact**; cơ chế vẫn còn áp dụng trong HotSpot mới.
- **Đánh dấu (*marking*)** là xác định object reachable/live từ roots theo quy tắc GC, không phải kiểm tra “đã dùng xong theo nghiệp vụ”.
- **Chuẩn bị dồn (*prepare compaction*)** xác định kế hoạch/vị trí đích; **điều chỉnh tham chiếu (*adjust pointers*)** duy trì đồ thị object; **compact heap** thu hồi khoảng trống, giảm fragmentation.
- **Full GC vẫn là STW** dù các GC worker hoạt động song song. Đừng nhầm Full GC mark với G1 concurrent marking của chu kỳ thông thường.
- **Không phải mọi live object đều phải di chuyển**; việc giữ identity/reference đúng không chứng minh địa chỉ vật lý giữ nguyên.
- **JDK mới có thể log thêm pha như `Reset Metadata`**, nên theo dõi GC log thực tế thay vì cố định bốn pha trong parser.
- **Ưu tiên tránh Full GC thường xuyên** bằng cách kiểm tra allocation rate, live-set retention, humongous objects, heap sizing và thời gian hoàn thành concurrent marking.
- **Chỉ dùng `System.gc()` trong bài lab có kiểm soát**; trong production hãy dựa vào GC ergonomics, logging và đo đạc.

### Tài liệu chính thức và hiện hành

1. [OpenJDK — JEP 307: Parallel Full GC for G1](https://openjdk.org/jeps/307) — lý do và phạm vi song song hóa Full GC từ Java 10.
2. [Oracle Java SE 26 — Garbage-First Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html) — G1 generations/regions, marking, evacuation, Full GC và đặc tính STW.
3. [Oracle Java SE 26 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html) — log `Pause Full`, nguyên nhân Full GC và hướng chẩn đoán thực tế.
4. [Oracle Java SE 26 — java launcher / `-Xlog` options](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — unified logging, GC tuning flags và câu lệnh chẩn đoán.
5. [OpenJDK — JEP 423: Region Pinning for G1](https://openjdk.org/jeps/423) — một ví dụ về giới hạn đặc biệt khi di chuyển object/region.
6. [Inside Java — Garbage Collection updates in JDK 26](https://inside.java/2026/02/28/jdk26-gc-changes/) — thay đổi GC hiện đại, tránh phụ thuộc các tùy chọn đã lỗi thời.
