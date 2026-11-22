# Young collection trong Java Garbage Collection

## 1. Young collection là gì?

**Young collection** là lần thu gom rác tập trung vào vùng nhớ dành cho object mới tạo (young generation). Trong các garbage collector có phân thế hệ, phần lớn object có vòng đời ngắn: request, iterator, DTO, buffer tạm, chuỗi trung gian và object phục vụ một lần tính toán thường không còn được tham chiếu sau một khoảng thời gian ngắn.

HotSpot tận dụng đặc điểm này bằng giả thuyết thế hệ yếu (weak generational hypothesis): phần lớn object sẽ chết trẻ. Thay vì quét toàn bộ heap ở mỗi lần thu gom, collector có thể thu gom young generation thường xuyên hơn, xử lý các object còn sống và thu hồi vùng chứa object đã hết vòng đời.

Trong thuật ngữ truyền thống, một lần thu gom young generation thường được gọi là **minor GC**. G1 thường ghi log là `Pause Young`, còn Generational ZGC có thể ghi `Minor Collection`. Tên gọi và cơ chế cụ thể phụ thuộc collector và phiên bản JDK.

Young collection thường có chi phí thấp hơn full-heap collection vì số object còn sống trong vùng cần thu gom thường nhỏ. Tuy nhiên, một young collection vẫn có thể tốn thời gian nếu nhiều object sống sót, phải copy nhiều object, cần quét nhiều reference hoặc hệ thống đang thiếu CPU.

## 2. Vì sao JVM chia heap thành các thế hệ?

Một object Java được xem là có thể thu gom khi không còn đường tham chiếu mạnh nào từ các GC root tới object đó. Nếu mỗi lần GC đều phải xét toàn bộ object còn sống trong heap, ứng dụng có live set lớn sẽ tốn nhiều thời gian.

Generational GC phân loại object theo tuổi:

- **Young generation:** nơi phần lớn object mới được cấp phát. Object chết sớm thường được thu hồi ở đây.
- **Old generation:** nơi giữ object sống qua nhiều lần young collection hoặc được promote sớm theo chính sách của collector.

Mục tiêu là tập trung công việc vào vùng có tỷ lệ garbage cao. Young collection thường chỉ phải xử lý một phần heap, nên thời gian có quan hệ gần với lượng object còn sống cần giữ/copy hơn là tổng số byte đã được cấp phát từ trước.

Không phải mọi object đều có cùng vòng đời. Cache, session, queue, static collection hoặc object gắn với request dài có thể sống lâu và được promote. Nếu ứng dụng giữ lại quá nhiều object, young collection vẫn chạy đều nhưng old generation sẽ tăng dần.

## 3. Eden, Survivor và Old generation

Ở các collector thế hệ cổ điển như Serial và Parallel, young generation thường gồm:

- **Eden:** phần lớn object mới được cấp phát tại đây. JVM thường cấp phát nhanh qua Thread-Local Allocation Buffer (TLAB) để giảm tranh chấp giữa các thread.
- **Survivor From:** vùng chứa object đã sống sót qua lần thu gom young gần nhất.
- **Survivor To:** vùng đích để copy object còn sống từ Eden và Survivor From trong lần thu gom tiếp theo.
- **Old/Tenured:** vùng chứa object đã sống đủ lâu hoặc được promote.

Hai survivor space luân phiên vai trò From và To. Sau một young collection, Eden và survivor source được làm rỗng; object còn sống được copy sang survivor destination hoặc old generation.

G1 dùng heap region thay cho ba vùng liên tục cố định. Một region có thể được gán vai trò Eden, Survivor hoặc Old; các region cùng một thế hệ không nhất thiết nằm cạnh nhau trong địa chỉ heap. Vì vậy, khi đọc log G1, hãy xem số region và trạng thái region thay vì giả định heap có ba dải địa chỉ liên tiếp.

## 4. Một young collection diễn ra như thế nào?

Với collector sao chép (copying/evacuating collector), quy trình khái quát gồm các bước:

1. JVM dừng hoặc đồng bộ các thread ứng dụng theo cơ chế của collector.
2. Collector xác định object còn sống trong vùng cần thu gom bằng cách duyệt GC root và các reference liên quan.
3. Object không còn reachable được xem là garbage; vùng nhớ của chúng có thể được tái sử dụng.
4. Object còn sống được copy sang Survivor hoặc Old theo tuổi, sức chứa và chính sách tenuring.
5. Reference được cập nhật để trỏ tới vị trí mới của object.
6. Vùng Eden và Survivor source cũ được tái sử dụng cho các lần cấp phát tiếp theo.

Với Serial và Parallel young collection, ứng dụng thường dừng trong suốt pha thu gom; Parallel dùng nhiều GC worker để xử lý song song. G1 cũng có các pause young dạng stop-the-world evacuation. Generational ZGC thực hiện phần lớn công việc tốn thời gian đồng thời với ứng dụng và chỉ dừng thread trong các pause ngắn cần thiết.

Young collection không đồng nghĩa với việc mọi object trong heap đều được quét. Collector phải xử lý reference từ vùng ngoài collection set trỏ vào object trẻ; đây là lý do các collector thế hệ dùng card table, remembered set hoặc cơ chế tương đương.

## 5. Object aging và promotion

Object còn sống sau young collection sẽ tăng tuổi (age). Tùy collector, object có thể được copy qua Survivor nhiều lần trước khi được promote sang Old.

Các yếu tố ảnh hưởng tới promotion:

- Tuổi object đã đạt ngưỡng tenuring hiện tại.
- Survivor space không còn đủ chỗ cho các object sống sót.
- Collector chọn ngưỡng tuổi thấp hơn để giữ Survivor ở mức sử dụng mục tiêu.
- Chính sách riêng của collector đối với object lớn hoặc allocation đặc biệt.

Trong HotSpot, `MaxTenuringThreshold` là giới hạn tuổi tối đa được cấu hình, nhưng ngưỡng thực tế có thể thấp hơn do JVM điều chỉnh dựa trên dữ liệu sống sót và sức chứa Survivor. Vì thế không nên mặc định rằng mọi object đều phải sống đúng 15 lần GC mới được promote.

Một object đã được promote sẽ làm tăng lượng dữ liệu ở Old generation. Nếu nhiều object được giữ lại lâu hơn dự kiến, promotion rate tăng và old generation có thể đầy nhanh hơn.

### Ví dụ về vòng đời

| Lần thu gom | Object A | Object B |
|---|---|---|
| Cấp phát | A và B được tạo ở Eden | A và B được tạo ở Eden |
| Young collection 1 | A còn được tham chiếu nên sống sót | B đã hết tham chiếu nên bị thu gom |
| Young collection 2 | A tiếp tục sống và tăng tuổi | B không còn tồn tại |
| Young collection tiếp theo | A có thể tiếp tục ở Survivor hoặc được promote | — |

Bảng này mô tả ý tưởng chung. Tuổi chính xác, thời điểm promotion và cách lưu object phụ thuộc collector, cấu hình và tải thực tế.

## 6. Remembered set và reference từ Old tới Young

Một object cũ có thể giữ reference tới object trẻ. Nếu young collection chỉ xét reference từ thread stack và object trong young generation, object trẻ đang được một object Old giữ có thể bị thu gom nhầm.

Collector cần biết các vị trí bên ngoài vùng đang thu gom có reference trỏ vào vùng đó. Các cơ chế thường gặp là:

- **Card table:** chia heap thành các card nhỏ và đánh dấu card có thể chứa reference cần xem xét.
- **Remembered set:** lưu thông tin về các vị trí bên ngoài collection set có reference trỏ tới vùng được quản lý.
- **Write barrier:** code được JVM chèn vào thao tác ghi reference để duy trì thông tin phục vụ GC.

Trong G1, remembered set giúp xác định reference từ region bên ngoài collection set vào region đang được thu gom. G1 dùng card để biểu diễn vị trí reference; mặc định một card có kích thước 512 byte trong tài liệu JDK 24. Các thông tin này giúp collector tránh quét toàn bộ old generation ở mỗi young collection.

Xử lý remembered set và quét heap roots cũng tiêu tốn thời gian. Khi pause young dài, hãy xem breakdown phase thay vì chỉ nhìn tổng thời gian.

## 7. Phân biệt Young collection, Mixed collection và Full GC

Ba khái niệm này thường bị nhầm lẫn:

| Loại | Phạm vi chính | Ý nghĩa |
|---|---|---|
| Young collection | Young generation | Thu gom Eden/Survivor hoặc vùng young tương ứng |
| Mixed collection của G1 | Young regions và một số Old regions được chọn | Thu gom young đồng thời lấy lại một phần Old generation |
| Full GC | Toàn heap | Thu gom/compact phạm vi heap rộng hơn; thường là sự kiện cần điều tra khi pause dài |

Với G1, **Young-Only phase** gồm các lần young collection bình thường. Khi old occupancy đạt ngưỡng bắt đầu marking, G1 có thể chạy một **Concurrent Start young collection**: pause này vừa thực hiện young collection vừa khởi động concurrent marking cho Old generation.

Sau marking, G1 có thể bước vào **Space-Reclamation phase**. Trong giai đoạn này, các lần **Mixed collection** thu gom young regions và thêm một số Old regions được chọn vì hiệu quả thu hồi bộ nhớ tốt. Mixed collection vẫn có phần young collection; tên Mixed không có nghĩa là Full GC.

Thuật ngữ **major GC** được dùng khác nhau giữa các tài liệu và collector. Không nên tự động coi mọi major collection là Full GC hoặc suy ra phạm vi chỉ từ tên gọi. Hãy xem log của đúng collector và JDK đang chạy.

## 8. Young collection khác nhau giữa các collector

Young collection không có cùng tên log hoặc cùng cách triển khai trên mọi collector.

| Collector | Cách thể hiện young collection | Đặc điểm cần nhớ |
|---|---|---|
| Serial GC | Thường có `Pause Young (Allocation Failure)` và `DefNew` | Thu gom bằng một GC thread; các thread ứng dụng dừng trong pause |
| Parallel GC | Thường có `Pause Young (Allocation Failure)` và `PSYoungGen` | Dùng nhiều GC worker cho young generation |
| G1 GC | `Pause Young (Normal)` hoặc các loại young pause khác | Dùng region; có Young-Only và Mixed collection; pause evacuation là stop-the-world |
| Generational ZGC | Có thể thấy `Minor Collection` và `Young Generation` trong log | As of JDK 24, ZGC là generational; phần lớn công việc GC chạy concurrent và pause rất ngắn |

Trên JDK 24, G1 là collector mặc định của HotSpot. ZGC cũng là generational collector; tùy chọn `-XX:+ZGenerational` đã bị loại bỏ vì chế độ generational trở thành mặc định của ZGC.

Tên log như `DefNew`, `PSYoungGen`, `Pause Young` hoặc `Minor Collection` là dấu hiệu của collector cụ thể. Đừng viết script hoặc dashboard giả định mọi JVM đều dùng cùng một tên sự kiện.

## 9. Bật Unified GC logging để quan sát Young collection

Unified Logging là cách chuẩn trên JDK hiện đại để quan sát hoạt động GC.

Ghi GC log cơ bản:

~~~bash
java -Xlog:gc -jar application.jar
~~~

Ghi chi tiết các tag GC và age trace vào file có rotation:

~~~bash
java \
  -Xlog:gc*,gc+age=trace:file=gc.log:uptime,level,tags:filecount=5,filesize=20M \
  -jar application.jar
~~~

Ý nghĩa:

- `gc*` bật các log có tag bắt đầu bằng `gc`.
- `gc+age=trace` ghi chi tiết tuổi object và tenuring threshold.
- `file=gc.log` ghi log ra file.
- `uptime,level,tags` thêm thời gian kể từ khi JVM khởi động, log level và tag.
- `filecount=5,filesize=20M` giới hạn số file rotation và kích thước mục tiêu của mỗi file.

Có thể tăng chi tiết từng phase:

~~~bash
java \
  -Xlog:gc*=info,gc+age=trace,gc+phases=debug,gc+cpu=info:file=gc.log:uptime,level,tags \
  -jar application.jar
~~~

`gc+phases=debug` giúp phân tích thời gian từng phase. `gc+cpu=info` cho biết thời gian CPU user/system và thời gian thực (real) của pause. Log chi tiết có thể tăng I/O và dung lượng; trong production nên chọn tag, level và rotation phù hợp.

## 10. Đọc một dòng log Young collection của G1

Ví dụ từ workload kiểm thử với Azul JDK 24.0.2:

~~~text
[0.043s][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
[0.043s][info][gc,heap] GC(0) Eden regions: 17->0(9)
[0.043s][info][gc,heap] GC(0) Survivor regions: 0->3(3)
[0.043s][info][gc,heap] GC(0) Old regions: 2->4
[0.043s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->5M(32M) 1.777ms
~~~

Cách đọc:

- `0.043s`: thời gian kể từ lúc JVM khởi động.
- `GC(0)`: mã định danh sự kiện GC; các dòng có cùng mã thuộc cùng một lần thu gom.
- `Pause Young`: đây là một young collection pause.
- `Normal`: loại young pause của G1.
- `G1 Evacuation Pause`: G1 copy object còn sống ra khỏi collection set.
- `Eden regions: 17->0`: số Eden region trước và sau pause.
- `Survivor regions: 0->3`: số Survivor region trước và sau pause.
- `Old regions: 2->4`: số Old region trước và sau pause.
- `18M->5M(32M)`: heap đã sử dụng trước GC, heap đã sử dụng sau GC và dung lượng heap tại thời điểm log.
- `1.777ms`: thời lượng pause được ghi trong ví dụ.

Số region không phải số object. `18M->5M` cũng không phải lượng memory đã giải phóng riêng trong Eden; đó là số liệu heap tổng hợp của lần GC.

Thời gian và số region trong log thay đổi theo JDK, heap, CPU và workload. Hãy dùng ví dụ để hiểu cấu trúc, không dùng các con số minh họa làm ngưỡng production.

## 11. Đọc tuổi object và tenuring threshold

Khi bật `gc+age=trace`, G1 có thể ghi thông tin dạng:

~~~text
[0.042s][debug][gc,age] GC(0) Desired survivor size 1572864 bytes, new threshold 2 (max threshold 2)
[0.044s][debug][gc,age] GC(1) Desired survivor size 1048576 bytes, new threshold 1 (max threshold 2)
~~~

Các thông tin quan trọng:

- **Desired survivor size:** mức dung lượng Survivor mà JVM hướng tới.
- **new threshold:** ngưỡng tuổi thực tế được chọn cho các object sống sót.
- **max threshold:** giới hạn tuổi tối đa được cấu hình.

Trong ví dụ, threshold thay đổi giữa 2 và 1 dù max threshold là 2. Điều này minh họa rằng JVM có thể điều chỉnh ngưỡng tenuring theo dữ liệu sống sót và sức chứa Survivor.

Nếu nhiều object có tuổi cao hoặc Survivor gần đầy, promotion có thể xảy ra sớm. Khi old generation tăng nhanh, hãy đối chiếu age table, allocation profile và các reference giữ object.

## 12. Theo dõi Young collection bằng jstat

`jstat` có thể cung cấp snapshot về các memory pool và số lần GC. Ví dụ:

~~~bash
jstat -gc <pid> 1000 5
~~~

Các cột thường hữu ích với young generation:

| Cột | Ý nghĩa |
|---|---|
| `S0C`, `S1C` | Dung lượng Survivor space 0 và 1 |
| `S0U`, `S1U` | Dung lượng đang dùng của Survivor space 0 và 1 |
| `EC` | Dung lượng Eden |
| `EU` | Dung lượng Eden đang dùng |
| `YGC` | Số lần young GC đã xảy ra |
| `YGCT` | Tổng thời gian dành cho young GC |

Các cột có thể được biểu diễn khác nhau theo collector và JDK. Với G1, `jstat` báo số liệu pool tổng hợp; GC log thường cung cấp thêm ngữ cảnh region và phase. Với ZGC, không nên giả định các cột Survivor/Eden theo cách bố trí của Serial/Parallel.

`jstat` là công cụ experimental/unsupported và định dạng text có thể thay đổi. Dùng nó để quan sát nhanh, kết hợp GC log hoặc JFR để điều tra sâu hơn; không xây dựng parser phụ thuộc định dạng text chưa ổn định.

## 13. Đánh giá tần suất và thời lượng Young collection

Không có một con số young GC mỗi giây được xem là tốt cho mọi ứng dụng. Một service cấp phát nhiều object ngắn hạn có thể chạy young collection thường xuyên nhưng vẫn đạt throughput và latency tốt.

Theo dõi các chỉ số sau theo cùng một khoảng thời gian:

- Số young collection trên giây hoặc trên phút.
- Tổng thời gian pause và phân vị p95/p99 của pause.
- Allocation rate của ứng dụng.
- Lượng heap còn dùng sau mỗi young collection.
- Survivor occupancy và age distribution.
- Promotion rate và xu hướng Old generation.
- CPU dành cho GC so với CPU ứng dụng.
- Request latency, throughput và error rate.

### Dấu hiệu thường gặp

| Quan sát | Cách diễn giải và hướng kiểm tra |
|---|---|
| Young GC thường xuyên nhưng pause rất ngắn | Có thể là workload allocation cao bình thường; so sánh với throughput/latency |
| Young GC thường xuyên và tổng thời gian GC lớn | Kiểm tra allocation rate, kích thước young generation và CPU GC |
| Pause young dài, lượng object sống sót cao | Xem age trace, object copy, survivor pressure và heap roots |
| Old generation tăng sau nhiều young GC | Có nhiều object sống lâu hoặc bị giữ bởi cache, queue, session, static reference |
| Survivor thường xuyên đầy hoặc threshold thấp | Kiểm tra lifetime distribution và promotion rate |
| Xuất hiện `Pause Young (Mixed)` ở G1 | G1 đang thu gom young cùng một số old regions trong Space-Reclamation phase |
| Xuất hiện `Pause Full` | Điều tra nguyên nhân Full GC; kiểm tra evacuation failure, old occupancy, humongous allocation và `System.gc()` |

Một young GC đơn lẻ không đủ để kết luận có memory leak. Hãy quan sát xu hướng post-GC heap và old occupancy qua nhiều chu kỳ.

## 14. Những yếu tố làm Young collection chậm

### Nhiều object sống sót

Thời gian evacuation thường tăng khi collector phải copy nhiều object còn sống. Một đợt thay đổi workload khiến object tồn tại lâu hơn có thể làm pause tăng đột ngột.

### Promotion tăng

Object sống sót được promote sẽ làm Old generation tăng. Nếu promotion rate cao hơn khả năng thu hồi Old generation, heap có thể tiến gần ngưỡng Full GC.

### Survivor space thiếu chỗ

Survivor quá nhỏ có thể khiến object được promote sớm. Điều này làm tăng áp lực Old generation và có thể thay đổi tần suất các collection tiếp theo.

### Reference và remembered set

G1 phải quét reference từ bên ngoài collection set vào region cần thu gom. Nhiều reference liên vùng hoặc nhiều dirty card có thể làm phase merge/scan heap roots tốn thời gian.

### CPU hoặc môi trường bị quá tải

Pause real time có thể tăng khi GC worker không được cấp đủ CPU, container bị giới hạn CPU hoặc máy đang chạy nhiều workload. Đối chiếu `User`, `Sys` và `Real` trong log `gc+cpu`.

### Allocation burst hoặc object lớn

Một đợt allocation burst có thể làm young generation đầy nhanh. Với G1, humongous object có thể được cấp phát trực tiếp vào old regions và gây áp lực lên quá trình thu hồi old generation.

## 15. Tuning Young generation đúng cách

Bắt đầu bằng đo workload thực tế và dùng collector defaults. Thay đổi kích thước young generation chỉ sau khi log cho thấy vấn đề cụ thể.

### Với G1

G1 tự điều chỉnh young generation để cố gắng đáp ứng pause-time goal. Oracle khuyến nghị tránh cố định kích thước young generation bằng `-Xmn`, `-XX:NewRatio` hoặc các tùy chọn tương tự vì việc này có thể vô hiệu hóa khả năng điều chỉnh pause time của G1.

Một số nguyên tắc:

- Đặt `-Xmx` theo live set, allocation rate và headroom đã đo.
- `-XX:MaxGCPauseMillis` là mục tiêu tối ưu hóa, không phải giới hạn pause được đảm bảo.
- Chỉ xem xét `G1NewSizePercent` hoặc `G1MaxNewSizePercent` khi log chỉ ra vấn đề kích thước young generation hoặc object copy.
- Nếu `Evacuate Collection Set` và `Object Copy` chiếm phần lớn pause, xem lại số object sống sót, allocation pattern và giới hạn young generation.
- Nếu Mixed collection chậm, tách thời gian xử lý young regions và old regions bằng log `gc+ergo+cset=debug`.

### Với Serial và Parallel

Các collector cổ điển có thể chịu ảnh hưởng từ `-XX:NewRatio`, `-XX:NewSize`, `-XX:MaxNewSize` và `-XX:SurvivorRatio`. Các option này điều chỉnh tỷ lệ young/old hoặc Eden/Survivor. Tuy nhiên, tăng young generation làm giảm tần suất minor GC nhưng có thể tăng pause; giảm young generation có thể làm GC xảy ra thường xuyên hơn.

Không sao chép các giá trị tuning của collector này sang collector khác. Đo lại sau mỗi thay đổi bằng cùng workload và cùng bộ chỉ số.

## 16. Ví dụ Java 17 hoàn chỉnh tạo Young collection

Ví dụ sau cấp phát nhiều object tạm thời và giữ lại một object trong mỗi batch để tạo cả garbage lẫn một tập object sống sót.

Tạo file `src/demo/YoungCollectionDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

/** Creates short-lived allocations and a small retained set for GC practice. */
public final class YoungCollectionDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static long checksum;

    public static void main(String[] args) {
        for (int batch = 0; batch < 24; batch++) {
            byte[][] allocations = new byte[512][];

            for (int i = 0; i < allocations.length; i++) {
                byte[] value = new byte[8 * 1024];
                value[0] = (byte) (batch + i);
                checksum += value[0] & 0xff;
                allocations[i] = value;
            }

            RETAINED.add(allocations[0]);
        }

        System.out.println(
            "READY batches=" + 24
            + " retained=" + RETAINED.size()
            + " checksum=" + checksum
        );
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d out src/demo/YoungCollectionDemo.java
~~~

Chạy với G1, heap nhỏ để dễ quan sát và bật age trace:

~~~bash
java -Xms32m -Xmx32m -XX:+UseG1GC -XX:MaxTenuringThreshold=2 -Xlog:gc*,gc+age=trace:stdout:uptime,level,tags -cp out demo.YoungCollectionDemo
~~~

Stdout của chương trình:

~~~text
READY batches=24 retained=24 checksum=1566720
~~~

GC log sẽ xuất hiện trước dòng `READY`. Trong lần thử với Azul JDK 24.0.2, G1 thực hiện nhiều young collection. Lần đầu có log `Pause Young (Normal) (G1 Evacuation Pause)`, Eden regions `17->0`, Survivor regions `0->3`, Old regions `2->4` và heap `18M->5M(32M)`. Log age cũng cho thấy JVM điều chỉnh tenuring threshold. Thời gian pause và số region thay đổi theo máy, heap và JDK.

`-XX:MaxTenuringThreshold=2` chỉ giúp minh họa age/promotion trong bài lab. Không dùng giá trị này làm cấu hình production mặc định. Sau khi chạy xong, chương trình kết thúc và JVM tự giải phóng process.

## 17. So sánh log của các collector

Cùng workload trên JDK 24.0.2 cho thấy các collector có tên log khác nhau:

**G1:**

~~~text
Pause Young (Normal) (G1 Evacuation Pause)
Eden regions: 17->0(9)
Survivor regions: 0->3(3)
Old regions: 2->4
~~~

**Parallel GC:**

~~~text
Pause Young (Allocation Failure)
PSYoungGen: 8704K(9728K)->1008K(9728K)
Eden: 8704K(8704K)->0K(8704K)
From: 0K(1024K)->1008K(1024K)
~~~

**Serial GC:**

~~~text
Pause Young (Allocation Failure)
DefNew: 8704K(9792K)->1088K(9792K)
Tenured: 1136K(21888K)->4231K(21888K)
~~~

**Generational ZGC:**

~~~text
Minor Collection (High Usage)
Young Generation
Concurrent Mark
Pause Relocate Start
Concurrent Relocate
~~~

Đây là các đoạn log đã quan sát trong bài lab; không phải định dạng cố định cho mọi bản build. Với ZGC, các phase concurrent là phần quan trọng của chu kỳ; không cộng toàn bộ thời gian concurrent thành stop-the-world pause.

## 18. Lỗi thường gặp khi đọc Young collection

### Nghĩ rằng mỗi Young GC đều là dấu hiệu xấu

Tần suất GC phụ thuộc allocation rate và kích thước young generation. Hãy so sánh pause, throughput và latency trước khi kết luận.

### Nhầm `18M->5M(32M)` là lượng Eden được giải phóng

Đây là số liệu heap đã dùng trước/sau GC và dung lượng heap. Dùng các dòng `Eden regions`, `Survivor regions` và `Old regions` để xem từng vùng.

### Nhầm promotion với memory leak

Object sống lâu có thể là hành vi đúng, ví dụ cache hoặc session. Kiểm tra ownership và retention path trước khi kết luận leak.

### Coi mọi `Pause Young (Mixed)` là Full GC

Với G1, Mixed collection gồm young regions và một số old regions được chọn. Tìm đúng log type và collection set.

### Ép young generation quá nhỏ

Young collection có thể xảy ra thường xuyên hơn và tăng tổng CPU dành cho GC. Đặc biệt với G1, việc cố định kích thước young generation có thể làm mất hiệu quả pause-time control.

### Chỉ xem số lần GC mà bỏ qua pause

Một ứng dụng có nhiều young GC ngắn có thể tốt hơn ứng dụng có ít GC nhưng pause rất dài. Theo dõi tổng thời gian và p95/p99.

### Dùng `System.gc()` để kiểm tra young collection

`System.gc()` có thể yêu cầu một full-heap collection hoặc hành vi khác tùy collector và flags. Không dùng nó để giả lập young collection.

### So sánh log của hai collector như cùng một định dạng

Serial, Parallel, G1 và ZGC có tên phase, pool và semantics khác nhau. Ghi nhận collector, JDK version và flags trước khi so sánh.

## 19. Quy trình điều tra Young collection trong ứng dụng thật

1. Xác nhận JDK version, collector, heap size và các GC flags.
2. Bật GC logging với `-Xlog:gc*`; thêm `gc+age=trace` nếu cần hiểu promotion.
3. Thu thập log trong một khoảng workload đại diện, có timestamp và rotation.
4. Đếm số young collection, thời lượng pause, tổng thời gian GC và xu hướng post-GC heap.
5. Kiểm tra Eden/Survivor/Old regions hoặc các pool tương ứng với collector.
6. Nếu pause dài, xem phase breakdown để xác định thời gian nằm ở root scan, remembered set, object copy hay phase khác.
7. Nếu old generation tăng, kiểm tra age distribution, promotion rate và các cấu trúc giữ object lâu.
8. Nếu thấy Full GC hoặc evacuation failure, điều tra old occupancy, allocation burst, humongous objects và headroom.
9. Đối chiếu với request latency, throughput, CPU, container limits và allocation metrics.
10. Thay đổi một yếu tố tại một thời điểm, chạy lại cùng workload và so sánh cùng bộ chỉ số.

Đối với production, dùng log level đủ để trả lời câu hỏi cần điều tra và giới hạn dung lượng file. Không thay đổi young generation size hoặc tenuring threshold chỉ dựa trên một dòng log.

## 20. Checklist

- [ ] Hiểu weak generational hypothesis và lý do object thường chết trẻ.
- [ ] Phân biệt Young generation, Old generation và Full GC.
- [ ] Hiểu vai trò Eden, Survivor From/To và promotion.
- [ ] Hiểu object age và tenuring threshold có thể được JVM điều chỉnh.
- [ ] Biết remembered set/card table giúp tìm reference từ Old tới Young.
- [ ] Phân biệt young-only và mixed collection trong G1.
- [ ] Nhận biết `Pause Young`, `PSYoungGen`, `DefNew` và `Minor Collection`.
- [ ] Bật `-Xlog:gc*` và `gc+age=trace` khi cần.
- [ ] Đọc heap before/after, pause duration, region count và age trace.
- [ ] Theo dõi YGC/YGCT nếu dùng `jstat -gc`.
- [ ] Đánh giá tần suất GC cùng pause, throughput và request latency.
- [ ] Không nhầm promotion với memory leak.
- [ ] Tránh cố định young generation size trong G1 khi chưa có bằng chứng.
- [ ] Kiểm tra Full GC, evacuation failure và humongous allocation khi old generation tăng.
- [ ] So sánh cùng workload và cùng collector khi đo trước/sau.

## 21. Tài liệu tham khảo

- [Oracle JDK 24 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-collector-implementation.html): generational hypothesis, minor collection, Eden/Survivor, aging, throughput và latency.
- [Oracle JDK 24 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html): G1 region layout, Young-Only phase, Concurrent Start, Mixed collection, evacuation và remembered set.
- [Oracle JDK 24 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-garbage-collector-tuning.html): GC logging, young collection pause, object copy, pause-time target và giới hạn tuning young generation.
- [Oracle JDK 24 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html): Generational ZGC, young/old generations và hành vi concurrent.
- [Oracle JDK 24 — The java Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html): tùy chọn heap và young generation như `-Xmn`, `-XX:NewSize` và `-XX:NewRatio`.

Young collection là một phần bình thường của generational GC. Muốn đánh giá nó có ảnh hưởng tới ứng dụng hay không, hãy xem object sống sót, promotion, pause duration, allocation rate và latency cùng nhau. Dùng GC log theo đúng collector giúp xác định phần nào của chu kỳ đang tốn thời gian trước khi điều chỉnh cấu hình.
