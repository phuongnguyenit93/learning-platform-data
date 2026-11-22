# Generational ZGC: cơ chế và thay đổi chế độ, tùy chọn giữa các phiên bản JDK

## Mục tiêu bài học

**ZGC (Z Garbage Collector)** là một garbage collector của HotSpot hướng tới **độ trễ tạm dừng thấp** bằng cách thực hiện phần lớn công việc GC đồng thời với application threads. ZGC ban đầu dùng mô hình **non-generational**: xử lý heap mà không phân chia đối tượng thành hai thế hệ trẻ/già theo cách thu gom thế hệ. **Generational ZGC**, được giới thiệu trong **JDK 21 qua JEP 439**, bổ sung khả năng thu gom các đối tượng trẻ thường xuyên hơn mà không phải xử lý toàn bộ tập đối tượng già trong mọi chu kỳ. Sau đó chế độ mặc định và **chính các JVM flags để chọn chế độ** đã thay đổi qua JDK 23, 24 và 26.

Đây là nội dung dễ áp dụng sai nhất khi nâng JDK: lệnh có `-XX:+ZGenerational` là cần thiết trên **JDK 21** để chủ động chọn generational mode, nhưng không nên đưa nguyên nó vào cấu hình dùng chung cho **JDK 26**.

Sau bài học, bạn có thể:

- Phân biệt **ZGC** với **Generational ZGC**, generational GC với concurrent GC, và GC pause với end-to-end request latency.
- Giải thích **young/old generations, object survival, promotion/tenuring, remembered references và barriers** mà không hiểu sai rằng Java source có địa chỉ heap cố định.
- Kể đúng các mốc **JDK 11 → 15 → 17 → 21 → 22 → 23 → 24 → 25 → 26**, nhất là JEP 439, 474 và 490.
- Viết câu lệnh chọn ZGC đúng từng giai đoạn; phân biệt **enabled/disabled, deprecated, obsolete và removed/expired options**.
- Hiểu chi phí của **store barriers** và cách phân loại old-to-young references giúp collector tránh phải quét mọi old objects khi xử lý young.
- Tuning an toàn bằng **-Xmx, -Xms, SoftMaxHeapSize, ZUncommit/ZUncommitDelay và GC logging**, không dùng flags lỗi thời.
- Thiết kế kiểm chứng bằng `java -version`, `-Xlog:gc*`, `jcmd`, JFR và thử nghiệm A/B có SLA.
- Chạy ví dụ Java 17+ có output xác định, biết rõ các ví dụ không bảo đảm kích hoạt một loại GC cycle cụ thể.

## 1. ZGC là gì? Điều gì khiến nó khác GC khác?

Với những collector thiên về **Stop-The-World (STW)**, một số khối lượng công việc mark/copy/compact lớn diễn ra khi application threads bị dừng. ZGC cố chuyển phần lớn công việc đắt đỏ sang **concurrent phases** để giảm thời gian dừng mà người dùng cảm nhận.

Các ý quan trọng:

1. **Concurrent** không nghĩa là hoàn toàn không có pause. ZGC vẫn có những pha synchronization/safepoint ngắn theo thiết kế và thực tế từng bản HotSpot.
2. **Low pause** không phải **zero overhead**. Mark/relocation, GC worker threads và load/store barriers dùng CPU, cache, memory bandwidth và heap headroom.
3. ZGC **không phải collector mặc định của mọi JVM**. Với nhiều HotSpot server configurations, mặc định vẫn là G1; chỉ dùng `-XX:+UseZGC` khi muốn chọn ZGC.
4. Một collector xử lý tốt heap nhiều GiB không có nghĩa tự động phù hợp một microservice chỉ có 1 vCPU và memory limit chặt.
5. **Non-generational** và **generational** là hai chế độ thuật toán trong lịch sử ZGC; chúng không phải hai GC names công khai độc lập như `UseZGC` và `UseG1GC`.

ZGC xuất hiện dưới dạng thử nghiệm trong JDK 11 (JEP 333) và trở thành tính năng production trong JDK 15 (JEP 377). Trước JDK 21, chế độ ZGC của upstream OpenJDK/HotSpot **không generational**. Chế độ generational được bổ sung sau đó, rồi dần thay thế hoàn toàn đường thuật toán non-generational.

## 2. Vì sao thêm generations vào ZGC?

*Generational hypothesis* nói rằng trong nhiều workload thực tế **phần lớn object mới được tạo trở nên unreachable khá sớm**, còn một số object sống lâu. Nếu phải xử lý cùng một tập old objects trong mọi lần GC chỉ vì rất nhiều temporary young objects xuất hiện, collector có thể làm nhiều công việc không cần thiết.

Mô hình:

~~~text
     Application allocations
               |
               v
       YOUNG GENERATION
       objects mới / tuổi nhỏ
               |
          Young collection
          /           \
         v             v
    Dead: reclaim   Survivors
                       |
              có thể tiếp tục young
              hoặc được PROMOTE
                       |
                       v
              OLD GENERATION
              objects sống lâu
                       |
              Old/major collection
              theo policy của ZGC
~~~

Đây là **sơ đồ ngữ nghĩa**; không yêu cầu ZGC trên mọi release dùng layout y hệt G1/Eden/Survivor/Old regions. ZGC có tổ chức bộ nhớ và cách theo dõi generation riêng; **không** lấy tên vùng của G1 rồi suy ra byte layout của ZGC.

### Young collection

Một chu kỳ young collection tập trung vào vùng young và những references cần thiết để biết young objects nào còn reachable. Nhiều object ngắn hạn có thể được reclaim mà không cần xử lý toàn bộ old generation như một full-heap traversal.

### Old collection

Old generation vẫn cần thu gom. Object sống lâu trong cache, queues hoặc graphs lớn không tự trở thành rác; old collections được chạy theo heuristics/scheduling của collector. Việc có generations **không** giúp chữa một memory leak mà objects còn reachable từ static fields/GC roots.

### Promotion và adaptive heuristics

Các object sống qua collection có thể được giữ trong young hoặc chuyển sang old tùy policy, độ tuổi, không gian và áp lực cấp phát. Generational ZGC được thiết kế để **tự thích nghi** với tải, kích thước thế hệ và ngưỡng tenuring. Không suy ra một object “tồn tại đúng 3 young GCs sẽ luôn lên old” trên mọi JDK hoặc một ngưỡng cố định tương đương G1.

## 3. Thách thức lớn: references từ old sang young

Giả sử có object `SessionCache` sống lâu trong old generation:

~~~java
static final class SessionCache {
    byte[] currentPayload;
}
~~~

Đây là **class minh họa**, không phải chương trình độc lập. Khi chương trình chạy:

~~~java
cache.currentPayload = new byte[1024];
~~~

nếu `cache` đã ở old còn `new byte[1024]` là object trẻ, chúng ta tạo một **old-to-young edge**:

~~~text
OLD                         YOUNG
+------------------+        +----------------+
| SessionCache     |        | byte[1024]     |
| currentPayload --+------->| new payload    |
+------------------+        +----------------+
~~~

Nếu young collection chỉ quét trực tiếp các **young roots** mà bỏ qua reference từ old, nó có thể kết luận sai rằng payload không reachable. Đây là lý do một generational collector phải giữ đủ thông tin để **tìm/duy trì các references giữa generations**.

### Store/write barrier

Khi mutator ghi một reference vào field hoặc array element, một **store barrier** có thể thông báo cho collector/ghi nhận thông tin cần thiết về graph. Generational ZGC bổ sung cơ chế store barriers thích hợp để theo dõi liên hệ thế hệ, bên cạnh logic load barriers vốn quan trọng trong ZGC.

Các khái niệm:
- **Write/store barrier:** mã hoặc đường xử lý VM quanh một số phép ghi reference, giúp GC giữ metadata đúng.
- **Load barrier:** xử lý quanh một số phép đọc reference, hữu ích cho việc relocation/remapping và tính đúng đắn khi collector di chuyển object đồng thời.
- **Remembered-set-like metadata:** thông tin cho phép xác định các locations có thể chứa cross-generational references. Không nhất thiết là chính data structure như remembered set/card table của G1.
- **Forwarding/remapping:** đảm bảo reference hợp lệ vẫn trỏ đúng logical object sau khi object đổi vị trí vật lý.

**Không nói** rằng mọi Java assignment phải viết một card-table entry theo đúng byte layout cụ thể. Compiler/GC có quyền tối ưu/coalesce/filter barriers, và cách triển khai có thể đổi qua JDK.

### Cái giá của generations

Generational ZGC có thể:
- Giảm công việc marking/collection lặp lại trên old objects.
- Giảm nguy cơ allocation stalls và nhu cầu heap headroom trong nhiều workload.
- Tạo thêm một số **store-barrier bookkeeping**, metadata hoặc concurrent work để theo dõi old-to-young references.
- Có profile lợi ích khác nhau khi workload chủ yếu là long-lived objects, có nhiều reference mutations hoặc không biểu hiện generational hypothesis rõ.

Vì vậy Generational ZGC không phải tuyên bố rằng mọi chương trình sẽ nhanh hơn một tỷ lệ cố định. Benchmark trên workload thật mới xác định trade-off.

## 4. Timeline chính thức theo JDK version

Ba JEP cốt lõi:

- **JEP 439:** Generational ZGC, delivered JDK 21.
- **JEP 474:** ZGC: Generational Mode by Default, delivered JDK 23.
- **JEP 490:** ZGC: Remove the Non-Generational Mode, delivered JDK 24.

Bảng dưới tập trung **upstream OpenJDK/HotSpot**; với vendor custom builds hoặc backports, phải kiểm tra chính binary đang chạy.

| JDK | Tình trạng ZGC | Mặc định khi chọn `UseZGC` | Cách chỉ định generational mode |
| --- | --- | --- | --- |
| **11** | ZGC được giới thiệu dưới dạng experimental (JEP 333) | Non-generational | Chưa có Generational ZGC |
| **15** | ZGC production (JEP 377) | Non-generational | Chưa có Generational ZGC |
| **17 (LTS)** | ZGC production | Non-generational | **Không có** flag `ZGenerational` để bật mode của JDK 21 |
| **21 (LTS)** | JEP 439 bổ sung Generational ZGC | **Non-generational**, nếu chỉ dùng `-XX:+UseZGC` | `-XX:+UseZGC -XX:+ZGenerational` |
| **22** | Hai modes tiếp tục cùng tồn tại | **Non-generational** | `-XX:+UseZGC -XX:+ZGenerational` |
| **23** | JEP 474 đổi default và deprecate non-gen mode | **Generational** | `-XX:+UseZGC` là đủ; `-XX:-ZGenerational` chọn legacy non-gen trong release này |
| **24** | JEP 490 xóa non-generational implementation | **Generational duy nhất** | `-XX:+UseZGC`; `ZGenerational` **obsolete, được nhận nhưng bị bỏ qua/cảnh báo** theo HotSpot option life cycle |
| **25 (LTS)** | Tiếp tục generational-only | **Generational duy nhất** | `-XX:+UseZGC`; cờ `ZGenerational` legacy vẫn thuộc giai đoạn obsolete/cảnh báo |
| **26** | Generational-only; option legacy hết thời gian tương thích | **Generational duy nhất** | `-XX:+UseZGC`; **không truyền `ZGenerational`**, vì đã expire/remove và có thể làm JVM từ chối startup |

**Lưu ý quan trọng về thuật ngữ:** JEP 490 **loại bỏ non-generational mode trong JDK 24**; điều đó khác với thời điểm chính **cú pháp flag** `ZGenerational` hết thời gian obsolete. Thông thường HotSpot có một giai đoạn chấp nhận option cũ, in warning rồi **bỏ qua** để giảm đột ngột lỗi khi chuyển bản, trước khi option **expired** và trở thành lỗi. Thảo luận OpenJDK về JDK 26 xác nhận cờ `ZGenerational` được đưa khỏi danh sách obsolete ở release này. Hãy kiểm tra exact startup behavior trên bản JDK/vendor của bạn thay vì phụ thuộc warning/ignore.

### Những suy luận sai từ tên release

- JDK 21 là bản **đầu tiên có Generational ZGC**, **không phải** bản đầu tiên chọn generational làm mặc định.
- JDK 23 chuyển **default khi đã chọn ZGC** sang generational, **không phải** đổi default GC toàn JVM từ G1 thành ZGC.
- JDK 24 xóa đường **non-generational ZGC**, không xóa ZGC.
- JDK 26 không yêu cầu cờ `ZGenerational`; đưa cờ này vào cấu hình có thể làm ứng dụng **không khởi động**.

## 5. Ma trận câu lệnh đúng từng nhóm JDK

### JDK 17: ZGC vẫn non-generational

~~~bash
java -XX:+UseZGC -version
~~~

Lệnh chọn ZGC trên HotSpot build hỗ trợ. **Không** thêm `-XX:+ZGenerational` vào Java 17: đây chưa phải tùy chọn Generational ZGC của JDK 21.

Muốn kiểm tra JVM hỗ trợ ZGC trong môi trường thực tế, hãy đọc `java -version` và khởi động smoke test thực bằng `-XX:+UseZGC -Xlog:gc*=info`. Nếu cờ hoặc collector không được build hỗ trợ, JVM có thể báo lỗi; không suy luận chỉ từ tên file Java.

### JDK 21–22: cần chọn generational rõ ràng

~~~bash
java -XX:+UseZGC -XX:+ZGenerational -version
~~~

Nếu bỏ `-XX:+ZGenerational` trong JDK 21/22, **ZGC non-generational** là mode mặc định. Đây là điểm quan trọng khi chuyển từ Java 17 sang Java 21 và muốn đo sự cải thiện của JEP 439.

Muốn đối chứng non-gen trong JDK 21:

~~~bash
java -XX:+UseZGC -version
~~~

Đây là hai chế độ của **cùng collector ZGC**, không phải ZGC và G1.

### JDK 23: generational trở thành mặc định của ZGC

~~~bash
java -XX:+UseZGC -version
~~~

JDK 23 mặc định chọn generational **sau khi ZGC đã được chọn**. Trong giai đoạn quá độ, có thể chọn legacy mode bằng:

~~~bash
java -XX:+UseZGC -XX:-ZGenerational -version
~~~

**Chỉ dùng ví dụ legacy JDK 23 để hiểu lịch sử hoặc thực hiện migration test**, không đưa cờ trừ này vào cấu hình cho JDK 24+ vì non-generational mode đã bị loại bỏ.

### JDK 24–26: chỉ chọn ZGC

~~~bash
java -XX:+UseZGC -version
~~~

Đây là câu lệnh ổn định hơn khi vận hành generational-only ZGC. Không thêm `-XX:+ZGenerational` hoặc `-XX:-ZGenerational`. JDK 24/25 có thể cho warning/ignore cờ legacy; JDK 26 có thể lỗi do flag đã expired. Cấu hình multi-JDK nên **phát sinh args theo phiên bản**, không đơn giản cộng một flag ZGenerational cho mọi máy.

### Một lệnh GC đã được chọn có ý nghĩa gì?

Không nên đọc `java -XX:+UseZGC -version` như bằng chứng application có GC event: nó chỉ có thể khởi động VM và báo version. Để xem collector được chọn, thêm logging:

~~~bash
java -XX:+UseZGC -Xlog:gc*=info -version
~~~

Thông điệp và format của logs khác nhau theo bản HotSpot. Có thể thấy dòng mô tả collector, nhưng không hứa stdout hay số collection events cố định.

## 6. Khi nâng JDK: trạng thái JVM option có ý nghĩa thực tế

Những trạng thái thường gặp trong vòng đời options của HotSpot:

| Trạng thái | Ý nghĩa thường gặp | Tác động khi cấu hình cũ còn tồn tại |
| --- | --- | --- |
| **Supported/active** | Option tồn tại, có effect theo semantics và release | Có thể dùng theo documentation |
| **Deprecated** | Option vẫn có effect nhưng có warning, có thể bị loại bỏ sau | Cần lên kế hoạch migration |
| **Obsolete** | Option được nhận nhưng không còn tác dụng; VM có thể warning | Dễ tưởng option còn bật được tính năng |
| **Expired/removed** | Option không còn được chấp nhận trong startup parser | Có thể khiến JVM fail ngay khi khởi động |

Bản chuyển đổi của `ZGenerational` tạo một **bẫy vận hành**:

~~~text
JDK 21:  -XX:+ZGenerational
         thật sự BẬT generational mode

JDK 23:  -XX:+ZGenerational
         không còn cần để chọn default generational

JDK 24/25:
         option legacy bị obsolete/ignored
         không đổi mode nữa

JDK 26:
         option legacy expired
         không nên xuất hiện trong startup args
~~~

**Ví dụ lỗi CI/CD:** một Helm chart chứa biến môi trường `JAVA_TOOL_OPTIONS="-XX:+UseZGC -XX:+ZGenerational"` áp dụng đồng loạt cho image JDK 21 và JDK 26. Ở JDK 21, chart giúp chọn generational mode. Ở JDK 26, option cũ có thể khiến mọi pods không khởi động. Cần sửa template image/tag→options tương ứng, chạy smoke test với **chính image production** trước khi rollout.

**Không đoán từ `java --version` đơn độc nếu ứng dụng thực sự dùng JDK khác với shell**. Container image, embedded runtime, IDE, Maven/Gradle toolchains và launcher scripts có thể chạy các binary khác nhau. Kiểm tra process/runtime đang hoạt động bằng diagnostics.

## 7. Đọc cơ chế generations đúng: object trẻ có sống lâu hơn một chu kỳ

Độ tuổi object không được định nghĩa bằng số giây đơn giản ở Java source. VM theo dõi object survival và khả năng promotion dựa vào collector policy.

~~~text
Tạo Payload tại t0:
  Payload ở young

t1: Young GC
  Payload unreachable? -> reclaim
  Payload reachable?   -> sống tiếp theo policy

t2: Young GC khác
  Payload tiếp tục sống
  Collector có thể giữ ở young hoặc promote old

t3: Old generation có nhiều dead objects
  Old collection thực hiện theo scheduling của ZGC
~~~

Không phải mọi object đều “trẻ trong hai giây”, và không có public Java API phổ thông xác định chắc chắn thế hệ của một object tùy ý ở mọi thời điểm. Một JFR/GC log có thể cho thống kê generations/tenuring, **không** biến Java variable thành handle điều khiển tuổi.

### Young vs old không đồng nghĩa weak vs strong references

- **Young/old** nói về tổ chức quản lý lifetime/generation.
- **Strong/weak/soft/phantom reference** nói về semantics reachability/reference processing.
- Một object ở old generation vẫn có thể unreachable và cần được collect.
- Một object ở young vẫn có thể reachable từ static field hoặc old object và cần được giữ.

Đừng lấy thứ tự garbage collection của G1 áp vào ZGC một cách máy móc. Cùng là generational, chúng có cách barrier/region/evacuation/coordination khác nhau.

## 8. Generational ZGC còn là moving concurrent collector

Generational ZGC vẫn dựa trên cơ chế **concurrent marking và relocation** của ZGC. Khi GC di chuyển object từ địa chỉ vật lý cũ sang vị trí mới, Java program vẫn phải quan sát cùng logical object:

~~~java
Object a = new Object();
Object b = a;
System.out.println(a == b); // true
~~~

Đây là snippet trong một method. Sau một concurrent relocation, VM phải bảo đảm `a == b` vẫn đúng trừ khi code tự thay các references. Java reference **không phải một con trỏ thô có địa chỉ bất biến do code quản lý**.

Những việc collector phải đảm bảo:
1. Trace những references thích hợp để xác định objects sống.
2. Phối hợp relocation/forwarding với các mutator threads.
3. Giữ identity và tính đúng đắn của references/fields khi objects di chuyển.
4. Không reclaim object mà vẫn reachable từ roots hoặc old-to-young references.
5. Phục vụ allocation đồng thời trong giới hạn heap/CPU cho phép.

Các kỹ thuật load/store barriers khác nhau có thể có chi phí trên hot execution paths. Một ứng dụng mutate references rất thường xuyên có thể chịu store-barrier overhead khác ứng dụng chủ yếu đọc immutable graphs. **Không tự khẳng định** generational luôn tăng throughput theo một phần trăm hoặc luôn giảm pauses.

## 9. Tuning quan trọng nhất: -Xmx và headroom

Tài liệu tuning ZGC nhấn mạnh rằng **max heap size** là nút điều chỉnh quan trọng hàng đầu. Vì GC làm nhiều công việc concurrently với application, heap phải đủ chỗ cho:
- **live set** đang được giữ,
- các allocations mới trong lúc GC chạy,
- destination/headroom liên quan relocation và collector bookkeeping.

Ví dụ:

~~~bash
java -XX:+UseZGC -Xms2g -Xmx4g -jar app.jar
~~~

Đây là **mẫu chạy ứng dụng**, cần thay `app.jar` bằng JAR hợp lệ và dành memory limit lớn hơn footprint của toàn JVM. **Không phải khuyến nghị chung** đặt 4 GiB cho mọi service.

### Nếu heap quá nhỏ

Có thể xảy ra:
- GC phải làm việc rất thường xuyên.
- Concurrent cycle không kịp reclaim trước khi allocations tiêu thụ headroom.
- Allocation stalls, latency spikes và eventual OOME.
- CPU contention giữa GC workers và mutators.

Dù ZGC hướng low pauses, **không có guarantee request sẽ không bao giờ stall** khi heap budget không đủ. Thời gian ngắn của GC safepoints không tự giải quyết vấn đề throughput hoặc memory pressure.

### Nếu heap quá lớn

Có thể:
- Tăng RSS/memory cost và giảm density triển khai.
- Che một memory retention bug lâu hơn.
- Tăng committed/reserved memory theo cấu hình.
- Không cải thiện p99 nếu bottleneck là database, locks, JIT hoặc CPU throttling.

**Chọn -Xmx theo live set, allocation spikes và SLO**, đồng thời dự phòng native memory của JVM (metaspace, code cache, thread stacks, direct buffers). `-Xmx=4g` không có nghĩa container RAM limit 4 GiB luôn đủ.

## 10. SoftMaxHeapSize: soft limit không phải hard limit

Tùy chọn:

~~~bash
java -XX:+UseZGC -Xmx5g -XX:SoftMaxHeapSize=4g -jar app.jar
~~~

Ý nghĩa:
- `-Xmx5g` là hard maximum của Java heap.
- `-XX:SoftMaxHeapSize=4g` là **soft target** mà ZGC cố gắng sử dụng khi điều kiện cho phép.
- ZGC **được phép vượt soft limit** tới hard max để tránh tình huống application stall do thiếu memory.
- Đây không phải một guarantee RSS process sẽ dưới 4 GiB.

Khi test, đừng chỉ nhìn committed heap tại một thời điểm rồi kết luận soft limit bị vi phạm là bug. Collector có thể chủ động dùng thêm memory lúc allocation spike hoặc khi cần hoàn tất concurrent work.

Đặt soft limit nhỏ hơn heap budget hữu ích khi muốn giảm average committed memory nhưng vẫn giữ **burst headroom**. Giá trị tối ưu phụ thuộc workload; không có một tỷ lệ cố định được khuyến nghị cho mọi ứng dụng.

## 11. Uncommit: trả unused heap cho OS

ZGC hỗ trợ hoàn trả một phần **unused committed memory** cho hệ điều hành qua cơ chế **uncommit** trong điều kiện thích hợp.

Các flags thường gặp:

| Flag | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `-XX:+ZUncommit` | Cho phép trả lại unused committed heap memory; mặc định thường bật trong ZGC | Không đồng nghĩa mọi garbage được trả tức thì về OS |
| `-XX:-ZUncommit` | Tắt cơ chế uncommit | Có thể giữ memory đã commit để tái sử dụng |
| `-XX:ZUncommitDelay=300` | Thời gian memory phải unused trước khi có thể uncommit (mặc định 300 giây theo tài liệu) | Không phải timer bắt GC đúng giây đó |
| `-Xms` | Sàn heap size: ZGC sẽ không uncommit để heap nhỏ hơn min heap | Khi `-Xms=-Xmx`, uncommit trở nên vô hiệu về tác dụng thực tế |

Ví dụ:

~~~bash
java -XX:+UseZGC -Xms1g -Xmx4g -XX:ZUncommitDelay=300 -jar app.jar
~~~

Các options thuộc HotSpot release hỗ trợ; phải thử trên đúng JDK production. Việc commit/uncommit pages cũng tốn chi phí. Nếu ưu tiên cực thấp latency và đủ RAM, một cấu hình `-Xms=-Xmx` kèm `-XX:+AlwaysPreTouch` **có thể** phù hợp một số môi trường, nhưng tốn committed memory/startup time; không coi nó là recipe mặc định cho mọi container.

### Heap used, committed và RSS không phải một

~~~text
-Xmx     : maximum Java heap
-Xms     : minimum/initial Java heap
Used heap / live set : trạng thái đối tượng
Committed heap       : memory đã commit
RSS/container memory : bao gồm heap và native components
~~~

ZGC có thể làm giảm footprint bằng uncommit, nhưng system RSS chịu nhiều yếu tố OS/native khác. Memory metrics phải được lấy từ VM và container đồng thời.

## 12. Tuning concurrent work: thận trọng với nhiều flags

ZGC được thiết kế **self-tuning**. Ngoài max heap, các knobs có thể xuất hiện trong tài liệu/flags của từng JDK:

- `-XX:ConcGCThreads=N`: điều chỉnh số GC worker threads đồng thời, nhưng override tự động có thể khiến GC thiếu tài nguyên hoặc tranh chấp CPU.
- `-XX:ZCollectionInterval=...`: policy/interval trigger trong những phiên bản hỗ trợ, không phải lời hứa GC chạy đúng từng N giây.
- `-XX:ZAllocationSpikeTolerance=...`: hướng dẫn heuristic về tốc độ allocation spikes; không dùng khi chưa có dấu hiệu stall.
- `-XX:ZFragmentationLimit=...`: ảnh hưởng policy relocation/compaction theo bản ZGC cụ thể; có trade-off CPU và fragmentation.
- `-XX:SoftMaxHeapSize=...`: soft target footprint.
- `-XX:ZUncommitDelay=...`: độ trễ trả lại unused pages.

**Không bê nguyên danh sách tuning flag từ một bản JDK sang bản khác.** JDK 21/23/24/25/26 có thay đổi về mode, heuristic và diagnostic/product flags. Kiểm tra:

~~~bash
java -version
java -XX:+PrintFlagsFinal -version
~~~

Nếu chỉ muốn xem flags chứa chữ Z trong PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String "UseZGC|ZGenerational|SoftMaxHeapSize|ZUncommit"
~~~

Lệnh trên là **hướng dẫn shell**, không phải phần output ổn định: một flag có thể không xuất hiện ở release mới vì đã bị xóa, hoặc không được in khi thiếu unlock level. Với production, ghi exact command line từ launcher/systemd/Helm environment, không chỉ JVM flags in trong một shell ngẫu nhiên.

## 13. Phân biệt các nhóm GC flags và lifecycle của chúng

| Nhóm | Ví dụ | Điều cần biết |
| --- | --- | --- |
| **Collector selection** | `-XX:+UseZGC` | Chọn ZGC; hiện generational-only trên JDK 24+ |
| **Mode selection trong giai đoạn quá độ** | `-XX:+ZGenerational` hoặc `-XX:-ZGenerational` | Chỉ có tác dụng ở releases hỗ trợ hai modes |
| **Heap budget** | `-Xms`, `-Xmx`, `SoftMaxHeapSize` | Không quy về một heap value duy nhất |
| **Memory returning** | `ZUncommit`, `ZUncommitDelay` | Tùy policy/bản JDK, có chi phí commit/uncommit |
| **Concurrent GC work** | `ConcGCThreads` | Có trade-off CPU với application threads |
| **Diagnostics** | `-Xlog:gc*`, JFR, `jcmd` | Quan sát behavior, không chọn GC mode |
| **Deprecated/obsolete legacy** | `ZGenerational` trên bản không còn hai modes | Cần loại khỏi startup scripts |

### Cờ nào có thể dùng xuyên nhiều phiên bản?

Nếu ứng dụng phải chạy cả JDK 21 và JDK 26 mà **bắt buộc** dùng Generational ZGC, phải phân nhánh:

~~~text
if runtime JDK == 21 or 22:
    append "-XX:+UseZGC -XX:+ZGenerational"
else if runtime JDK >= 23:
    append "-XX:+UseZGC"
else:
    Generational ZGC unavailable; choose migration strategy
~~~

Đây là **mã giả cấu hình**, không phải syntax Bash/PowerShell. Với JDK 23, mode generational là mặc định khi `UseZGC`, còn với JDK 24+ là mode duy nhất. Không nên dựa vào `-XX:+ZGenerational` nếu muốn cùng một manifest hoạt động trên JDK 26.

Nếu vendor đã backport/sửa flags, hãy dùng chính binary production để kiểm tra, không suy theo bảng upstream một cách mù quáng.

## 14. Java 17+: mô hình tham chiếu old → young có output xác định

Để học lý do của store barrier mà **không tự bịa GC events**, một chương trình Java có thể dùng static owner giữ tham chiếu đến một payload được tạo sau đó. Chương trình không có API ép owner phải lên old, nên nó chỉ minh họa **quan hệ reference** — không chứng minh object thực tế đang thuộc generation nào.

Tạo tệp **`GenerationalReferenceDemo.java`**:

~~~java
public class GenerationalReferenceDemo {
    static final class Holder {
        byte[] payload;
    }

    static final Holder LONG_LIVED = new Holder();

    public static void main(String[] args) {
        byte[] first = new byte[] {1, 2, 3};
        LONG_LIVED.payload = first;

        System.out.println("sameFirst=" +
                (LONG_LIVED.payload == first));
        System.out.println("first0=" + LONG_LIVED.payload[0]);

        byte[] second = new byte[] {7, 8, 9};
        LONG_LIVED.payload = second;

        System.out.println("sameSecond=" +
                (LONG_LIVED.payload == second));
        System.out.println("second0=" + LONG_LIVED.payload[0]);
        System.out.println("firstStill=" + first[0]);
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac --release 17 GenerationalReferenceDemo.java
java GenerationalReferenceDemo
~~~

**Stdout chính xác:**

~~~text
sameFirst=true
first0=1
sameSecond=true
second0=7
firstStill=1
~~~

Giải thích:
- `LONG_LIVED` là static field giữ reference tới Holder, không có bảo đảm object đã được **promoted** ở bất kỳ lúc nào trong chương trình ngắn này.
- Việc gán `payload` thay đổi một **reference field**, không copy array.
- Nếu Holder thực sự thuộc old và second thực sự thuộc young trong một workload dài, đây là loại **old-to-young reference** mà collector generational cần xử lý đúng.
- Sau phép gán lại, `first` vẫn còn được local variable tham chiếu, nên không tự biến mất ngay.
- Generational ZGC có thể dùng store-barrier bookkeeping cho các trường hợp thực tế thích hợp, nhưng **stdout không chứng minh barrier đã được thực thi**.

## 15. Java 17+: một workload tạo object và một phần survivors

Đây là chương trình thực thi được trên nhiều bản JDK, để thử GC với **cùng logic dữ liệu**. Nó không yêu cầu API Java riêng của ZGC.

Tạo tệp **`ZgcWorkloadDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ZgcWorkloadDemo {
    static volatile byte[] latest;

    public static void main(String[] args) {
        List<byte[]> survivors = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 50_000; i++) {
            byte[] payload = new byte[1024];
            payload[0] = (byte) i;

            checksum += Byte.toUnsignedInt(payload[0]);

            if (i % 1000 == 0) {
                survivors.add(payload);
            } else {
                latest = payload;
            }
        }

        System.out.println("survivors=" + survivors.size());
        System.out.println("checksum=" + checksum);
        System.out.println("last=" +
                Byte.toUnsignedInt(latest[0]));
    }
}
~~~

Biên dịch bằng **JDK 17+**:

~~~bash
javac --release 17 ZgcWorkloadDemo.java
~~~

Chạy với ZGC **non-generational trong JDK 17**:

~~~bash
java -Xms32m -Xmx128m -XX:+UseZGC ZgcWorkloadDemo
~~~

Chạy với **Generational ZGC trong JDK 21/22**:

~~~bash
java -Xms32m -Xmx128m -XX:+UseZGC -XX:+ZGenerational ZgcWorkloadDemo
~~~

Chạy với ZGC **generational mặc định trong JDK 23+**:

~~~bash
java -Xms32m -Xmx128m -XX:+UseZGC ZgcWorkloadDemo
~~~

**Stdout nghiệp vụ chính xác** nếu VM khởi động và chạy thành công, không bật riêng logging trên stdout:

~~~text
survivors=50
checksum=6367960
last=79
~~~

Cách kiểm tra số:
- Có 50.000 vòng lặp.
- Các chỉ số chia hết cho 1000 là 0, 1000, …, 49000 → **50 survivor references trong list**.
- `Byte.toUnsignedInt((byte)i)` đi theo chu kỳ 0..255, nên tổng trên 50.000 phần tử là **6.367.960**.
- i cuối là 49999; 49999 modulo 256 = **79**, nên `last=79`.
- Mặc dù source chứa 50.000 lệnh `new byte[1024]` ở runtime, **đừng tự suy ra profiler phải ghi nhận đúng 50.000 physical allocations**: JIT có thể tối ưu, GC có thể làm việc khác nhau.
- Một JVM/container quá hạn chế resources hoặc thiếu ZGC support có thể không chạy được; lệnh là **smoke test**, không phải benchmark production.

### Tại sao không in GC-count cố định?

Tần suất young/old GC và cách phân phối generations phụ thuộc JDK, heap sizing, CPU, object liveness, heuristics, JIT và scheduling. Cùng code có thể tạo không có, một hoặc nhiều GC cycles trong khoảng chạy ngắn. **Không viết stdout dự đoán “Young GC 3 lần”** khi không thể bảo đảm.

## 16. Xác minh collector thật sự chạy trên môi trường

Bắt đầu với:

~~~bash
java -version
java -XX:+UseZGC -Xlog:gc*=info -version
~~~

Với Java 21 nếu muốn generational, thêm cờ:

~~~bash
java -XX:+UseZGC -XX:+ZGenerational -Xlog:gc*=info -version
~~~

Đọc startup logs để xác nhận ZGC và mode tương ứng. Các tags/log messages **thay đổi theo bản HotSpot**, nên không hardcode một chuỗi log duy nhất mà không xác nhận trên đúng release.

### Chạy thử có GC log vào file

Trên JDK 24+:

~~~bash
java -Xms256m -Xmx1g -XX:+UseZGC -Xlog:gc*:file=zgc.log:time,uptime,level,tags ZgcWorkloadDemo
~~~

Tệp `zgc.log` có thể cho GC init/heap statistics/young–old phases tùy mức log và VM build. Program quá ngắn **có thể không kích hoạt số GC như mong muốn**, nên đừng dùng một lần chạy để đánh giá policy của collector.

Nếu muốn xem thêm mà tránh quá nhiều log, bắt đầu mức `info` rồi mở rộng `debug/trace` khi thực sự cần. Log GC lớn có thể ảnh hưởng disk và performance; cần rotation/retention trên production.

### Xác định flags của JVM thực sự đang chạy

Với process ID hợp lệ (thay số PID thật):

~~~bash
jcmd PID VM.command_line
jcmd PID VM.flags
jcmd PID GC.heap_info
~~~

Đây là lệnh ví dụ của JDK hỗ trợ. Không dùng nguyên chuỗi `PID` nếu process có ID khác, và hãy kiểm tra quyền attach/cấu hình JVM thực tế. Một app launcher có thể thêm các flags từ `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, start script hoặc service manager.

### JFR và GC events

JFR có thể giúp quan sát:
- GC pauses, concurrent cycles, heap usage và hoạt động allocation theo event settings;
- total CPU/process behavior;
- large objects hoặc allocation hotspots khi bật events tương ứng;
- stalls/chậm trễ và sự tương quan với request latency.

Tuy nhiên JFR recording, event sampling và output phụ thuộc cấu hình. Không coi một recording ngắn là bằng chứng ZGC luôn có p99 nhỏ hơn collector khác trong production.

## 17. Migration checklist Java 17 → 21 → 23/24/25/26

### Bước 1: xác nhận yêu cầu

Đầu tiên xác định:
- Runtime cần **low GC pause**, throughput-first hay memory-constrained?
- End-to-end p99/p99.9 latency SLO là bao nhiêu?
- Heap live set, allocation rate, largest bursts và CPU quota?
- Có pinned/native interactions hay large arrays đặc biệt?
- Phải chạy song song nhiều JDK trong một fleet không?

Không tự quyết định chuyển sang ZGC chỉ vì nâng Java. GC mặc định (thường G1) có thể đang thỏa SLO và ít CPU/memory hơn.

### Bước 2: kiểm tra chính binary/flags

~~~bash
java -version
java -XX:+UseZGC -Xlog:gc*=info -version
~~~

Trên JDK 21/22, thử đối chứng hai modes nếu cần để hiểu Generational ZGC:

~~~bash
java -XX:+UseZGC -version
java -XX:+UseZGC -XX:+ZGenerational -version
~~~

Trên JDK 23, generational đã mặc định khi chọn ZGC. Trên JDK 24+, legacy non-gen không còn. Trên JDK 26, **xóa hẳn** cờ `ZGenerational` trong startup scripts/Helm charts.

### Bước 3: di chuyển cấu hình theo release

| Nguồn | Đích | Thay đổi tối thiểu khi chủ động chọn generational ZGC |
| --- | --- | --- |
| JDK 17 ZGC → JDK 21 | Thử generational | Thêm `-XX:+ZGenerational` vào `-XX:+UseZGC` |
| JDK 21 generational → JDK 23 | Generational mặc định | Có thể bỏ `-XX:+ZGenerational`; giữ `-XX:+UseZGC` |
| JDK 23 non-gen → JDK 24 | Không còn non-gen | Xóa `-XX:-ZGenerational`; chấp nhận việc chuyển thuật toán |
| JDK 24/25 → JDK 26 | Xóa obsolete flag | Bỏ `-XX:±ZGenerational` hoàn toàn; giữ `-XX:+UseZGC` |
| JDK 17/G1 → JDK 26/ZGC | Đổi collector và thuật toán | Bật `UseZGC`, đo latency/CPU/RSS, không tái sử dụng các tuning flags của G1 một cách mù quáng |

**Lưu ý:** “Bỏ cờ đi” là thay đổi config syntax; nhưng performance behavior có thể đổi do underlying generational collector. Phải test workload/heap sizing sau migration, không chỉ chứng minh VM startup thành công.

### Bước 4: so sánh có kiểm soát

Trên cùng benchmark/service:
1. Cố định workload, versions của ứng dụng và inputs.
2. Ghi exact JDK build, CPU quota, memory limit và GC flags.
3. Warmup tương đương; chạy đủ để thấy concurrent/old collection cycles.
4. Thu p50/p95/p99 request latency, throughput, errors, CPU, RSS, live heap, allocation stalls, GC pause distribution.
5. Lặp runs để giảm nhiễu, không kết luận từ một log đẹp.
6. Canary trên traffic thật và có rollback plan.

**Không so hai cấu hình với heap limit khác nhau rồi quy mọi khác biệt cho collector**. Nếu phải thay heap để ZGC chạy ổn, ghi đó là một phần của configuration cost.

## 18. ZGC có thể vẫn gây allocation stalls

ZGC tối ưu pause time không có nghĩa JVM không thể rơi vào **allocation stalls** nếu concurrent GC không thu hồi kịp memory.

Nguyên nhân có thể gồm:
- `-Xmx` quá nhỏ so với live set + allocation bursts.
- CPU quota khiến concurrent GC workers không có đủ chu kỳ CPU.
- Allocation rate tăng nhanh đột biến.
- Nhiều long-lived objects hoặc cache retention.
- Phần heap ngoài Java heap (direct/native) gây container memory pressure, làm ứng dụng bất ổn dù GC pause thấp.

Khi thấy p99 spikes, hãy xem đồng thời:
- GC log markers cho stalls và cycle progress.
- Heap used/committed, available headroom.
- Process/container CPU throttling.
- JFR event timeline và requests.
- Memory leak/retention ownership.

**Không mặc định sửa bằng `ConcGCThreads`**. Tăng concurrent workers có thể giúp collector nhưng cũng lấy CPU khỏi application, làm service latency tệ hơn trên vCPU ít. Đầu tiên đo, sau đó thử một thay đổi có kiểm soát.

## 19. JDK version-specific tuning và những cái bẫy nâng cấp

### Bẫy 1: hiểu “default Generational ZGC” thành “default GC là ZGC”

**Sai.** JEP 474 chỉ đổi chế độ mặc định **trong ZGC** khi ZGC được chọn. VM có thể vẫn chọn G1 theo defaults tùy platform/heap.

### Bẫy 2: tin rằng Java 21 tự dùng Generational ZGC khi chọn `UseZGC`

**Sai.** JDK 21 vẫn chọn non-gen khi chỉ `-XX:+UseZGC`. Thêm `-XX:+ZGenerational` nếu muốn generational.

### Bẫy 3: dùng `ZGenerational` xuyên toàn bộ Java 21–26

**Sai.** Cờ có meaning thật trên 21/22, không còn cần ở 23, obsolete ở 24/25 và expired ở 26 theo lifecycle upstream. Cần version-specific configuration.

### Bẫy 4: bật `-XX:-ZGenerational` trên JDK 24 để quay lại old mode

**Không thể.** JEP 490 đã loại bỏ non-generational implementation. Một flag obsolete nếu còn được nhận cũng bị bỏ qua, không khôi phục được thuật toán.

### Bẫy 5: nghĩ Generational ZGC thu gom old generation miễn phí

**Sai.** Nó vẫn phải mark/copy/relocate old objects theo cycles thích hợp. Generations giúp tránh một số công việc không cần thiết trong nhiều young collections, không loại bỏ chi phí tất cả old objects.

### Bẫy 6: nghĩ ZGC không có reference store barrier

**Không chính xác với Generational ZGC.** Việc theo dõi old-to-young references đòi barrier/metadata phù hợp; compiler/runtime có tối ưu cụ thể.

### Bẫy 7: lấy “sub-millisecond GC pause” làm SLA

**Sai.** Đó là định hướng thiết kế, không phải deadline cứng cho mọi pause và không phải p99 request. CPU contention, allocation stalls và application logic vẫn có thể tạo latency.

### Bẫy 8: giảm `-Xmx` vì generational efficient hơn

Có thể làm tăng stalls nếu headroom không đủ. Cần xác nhận live set, spikes, CPU quota và memory footprint trước khi hạ budget.

### Bẫy 9: đặt `-Xms=-Xmx` khi muốn ZUncommit giảm RSS

Khi minimum heap bằng maximum heap, ZGC không thể uncommit xuống dưới minimum. Cấu hình đó về thực tế vô hiệu hóa lợi ích uncommit của unused heap.

### Bẫy 10: so ZGC với G1 chỉ bằng GC logs

GC logs chưa đủ cho end-to-end latency. Phải đo throughput, p99 service latency, errors, process CPU, RSS và container throttling.

### Bẫy 11: cho rằng Java source có API đo generation của một object bất kỳ

Không có API Java SE chung cam kết cung cấp generation của mọi object. Diagnostics có thể cho thông tin nội bộ, nhưng thay đổi theo collector/build.

### Bẫy 12: biến `java -version` thành “benchmark”

Lệnh khởi động kiểm tra config, không chạy đủ workload/GC cycles để nói gì về throughput/latency.

## 20. Thực hành phân tích một sự cố cấu hình

**Tình huống:** Một service đã chạy JDK 21 với command:

~~~text
java -XX:+UseZGC -XX:+ZGenerational -Xmx4g -jar service.jar
~~~

Khi đổi container image sang JDK 26, process không khởi động do legacy `ZGenerational`.

### Chẩn đoán

1. Kiểm tra exact JVM từ startup logs hoặc `java -version` trong cùng container.
2. Xem toàn bộ JVM arguments: command line, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, Helm chart/start script.
3. Đối chiếu JEP 490: JDK 24 đã bỏ non-generational mode; cờ cũ không còn cần.
4. Đối chiếu expiration ở JDK 26: cờ obsolete quá thời gian tương thích.
5. **Xóa cờ `-XX:+ZGenerational`**, giữ `-XX:+UseZGC` nếu vẫn muốn chọn ZGC.
6. Chạy smoke test trên exact production image, bật `-Xlog:gc*=info` để xác nhận collector.
7. Đo production-like workload, CPU/RSS/GC events và SLO để kiểm tra upgrade hoàn chỉnh.

**Cấu hình được sửa cho JDK 26:**

~~~bash
java -XX:+UseZGC -Xmx4g -jar service.jar
~~~

File `service.jar` là tên ví dụ, cần thay đúng application artifact. Việc xóa legacy flag sửa startup, không tự đảm bảo throughput/latency của release mới bằng release cũ.

## 21. Bài tập và lời giải

**Câu 1.** Generational ZGC được thêm lần đầu vào JDK nào?

**Đáp án:** **JDK 21**, qua **JEP 439**. Trên release này vẫn cần chọn generational mode bằng `-XX:+UseZGC -XX:+ZGenerational`.

**Câu 2.** Có Generational ZGC trên JDK 17 upstream không?

**Đáp án:** Không. ZGC trên JDK 17 upstream là **non-generational**.

**Câu 3.** JDK nào chuyển default mode của ZGC sang generational?

**Đáp án:** **JDK 23** theo **JEP 474**. Điều này không có nghĩa default garbage collector của toàn JVM đổi sang ZGC.

**Câu 4.** JDK nào loại bỏ non-generational ZGC?

**Đáp án:** **JDK 24**, theo **JEP 490**.

**Câu 5.** Vì sao cờ `ZGenerational` vẫn có thể không gây startup error trên JDK 25 dù đã vô dụng?

**Đáp án:** HotSpot có giai đoạn **obsolete option** chấp nhận/cảnh báo/bỏ qua trước khi expire, nhằm hỗ trợ quá trình chuyển đổi.

**Câu 6.** Khi dùng JDK 26, lệnh nào chọn ZGC?

**Đáp án:** `java -XX:+UseZGC ...`, **không** thêm cờ `ZGenerational`.

**Câu 7.** Vì sao Generational ZGC cần theo dõi old-to-young references?

**Đáp án:** Young object có thể reachable qua field của một old object; nếu bỏ qua, collector có thể reclaim nhầm object đang sống.

**Câu 8.** Store barrier có liên quan `volatile` trong Java source không?

**Đáp án:** Là các khái niệm khác nhau. GC store barrier là instrumentation/runtime logic phục vụ GC; `volatile` là semantics visibility/order trong Java Memory Model.

**Câu 9.** Khi `Xmx=5g, SoftMaxHeapSize=4g`, ZGC có được vượt 4g không?

**Đáp án:** Có, đến hard max khi cần, ví dụ để tránh allocation stalls. Soft limit không phải hard limit.

**Câu 10.** Vì sao `-Xms=-Xmx` giảm hiệu quả ZUncommit?

**Đáp án:** ZGC không uncommit dưới minimum heap; minimum bằng maximum làm không còn khoảng để shrink.

**Câu 11.** ZGC có đảm bảo application không có pause >1 ms hoặc p99 <10 ms không?

**Đáp án:** Không. Low pause là mục tiêu thiết kế, application latency còn nhiều nguồn và collector có thể gặp allocation stalls khi resources thiếu.

**Câu 12.** Có thể dùng `java -XX:+UseZGC -version` để so throughput ZGC vs G1 không?

**Đáp án:** Không. Đó là startup smoke test, không phải benchmark.

**Câu 13.** Khi lên JDK 23, `-XX:-ZGenerational` có tác dụng gì?

**Đáp án:** Trong JDK 23, nó có thể chọn **legacy non-generational mode**; mode đã deprecate và bị xóa trên JDK 24.

**Câu 14.** Khi nào đổi ZGC mode có thể không giúp ứng dụng?

**Đáp án:** Khi workload không có nhiều young garbage, nhiều old-to-young mutations, CPU quota thấp, heap quá chật, hoặc bottleneck nằm ngoài GC. Phải đo.

**Câu 15.** Tại sao không lấy số trẻ/già từ stdout của ví dụ ReferenceDemo?

**Đáp án:** Java source không bảo đảm object `Holder` đã được promote. Ví dụ chỉ chứng minh reference semantics, không quan sát age/generation của heap.

## 22. Bản đồ ghi nhớ

~~~text
HISTORY OF ZGC MODE SELECTION

JDK 11: ZGC experimental (non-gen)
    |
JDK 15/17: ZGC production, non-gen
    |
JDK 21: JEP 439 -> Generational mode ADDED
        -XX:+UseZGC                 => non-gen default
        -XX:+UseZGC -XX:+ZGenerational => gen
    |
JDK 22: same transitional behavior
    |
JDK 23: JEP 474 -> Generational DEFAULT if UseZGC
        -XX:+UseZGC                 => gen
        -XX:-ZGenerational          => legacy non-gen
    |
JDK 24: JEP 490 -> non-gen IMPLEMENTATION REMOVED
        -XX:+UseZGC                 => gen only
        ZGenerational legacy option obsolete
    |
JDK 25: gen only; legacy option still obsolete
    |
JDK 26: gen only; ZGenerational legacy option expired
        -XX:+UseZGC                 => recommended syntax


WHY GENERATIONAL?

New objects -> YOUNG -> usually die early
Survivors -> may be promoted -> OLD
OLD --> YOUNG reference requires tracking
  store barrier + GC metadata
Concurrent mark/relocation + load-barrier logic

WHAT TO MEASURE?

SLO p99 + throughput + CPU + RSS + heap headroom
GC logs + JFR + jcmd + container metrics
NEVER infer exact GC cycles from Java stdout
~~~

**Tóm tắt:** **Generational ZGC bắt đầu ở JDK 21**, trở thành **mode mặc định của ZGC trên JDK 23** và là **mode duy nhất từ JDK 24**. Cờ `ZGenerational` vì thế có tác dụng trên JDK 21/22, không cần cho JDK 23, bị obsolete trên JDK 24/25 và không còn hợp lệ trên JDK 26. Về cơ chế, phân thế hệ giúp tập trung work vào đối tượng trẻ và dùng barrier/metadata để giữ đúng các reference old→young. Để vận hành an toàn, chọn flags theo đúng runtime version, cấp đủ heap headroom và đo **latency/CPU/throughput/RSS** bằng workload thật.

## Tài liệu tham khảo chính thức và nguồn đối chiếu phiên bản

- [JEP 333 — ZGC: A Scalable Low-Latency Garbage Collector (JDK 11)](https://openjdk.org/jeps/333).
- [JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector (Production) (JDK 15)](https://openjdk.org/jeps/377).
- [JEP 439 — Generational ZGC (JDK 21)](https://openjdk.org/jeps/439).
- [JEP 474 — ZGC: Generational Mode by Default (JDK 23)](https://openjdk.org/jeps/474).
- [JEP 490 — ZGC: Remove the Non-Generational Mode (JDK 24)](https://openjdk.org/jeps/490).
- [Oracle JDK 24 Migration Guide — ZGC non-generational removal](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html).
- [Inside Java — Introducing Generational ZGC](https://inside.java/2023/11/28/gen-zgc-explainer/).
- [Oracle Java SE 21 — Z Garbage Collector and heap tuning](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html).
- [Oracle Java SE 26 — java command and GC flags](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
- [OpenJDK HotSpot review — Remove expired ZGC flags for JDK 26](https://mail.openjdk.org/pipermail/hotspot-runtime-dev/2025-October/082324.html).
- [Oracle JDK 21 Release Notes — Generational ZGC](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html).
