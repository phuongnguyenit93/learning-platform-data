# Đọc thời gian dừng và phân biệt sự kiện đồng thời trong log JVM

Khi phân tích hiệu năng JVM, cần tách **thời gian dừng ứng dụng (pause time)** khỏi **thời gian của các công việc GC chạy đồng thời (concurrent phases)**. Pause là khoảng thời gian các Java application thread bị dừng tại safepoint để JVM thực hiện công việc cần dừng thế giới; concurrent phase chạy trong lúc application thread vẫn có thể tiếp tục thực thi.

Từ Java 9, Unified JVM Logging cung cấp tùy chọn `-Xlog` để ghi log GC và safepoint với timestamp, uptime, level và tags. Với log G1, các dòng `Pause Young`, `Pause Remark`, `Pause Full` thể hiện các khoảng dừng; `Concurrent Mark Cycle` và các phase `Concurrent ...` thể hiện công việc chạy đồng thời. Đọc đúng loại sự kiện và duration giúp xác định thời gian ứng dụng thực sự bị ngừng, thay vì nhầm toàn bộ chu kỳ GC thành một lần pause.

## 1. Bật log GC và safepoint bằng Unified Logging

Có thể bật log khi khởi chạy JVM:

```bash
java -Xlog:gc*=info,safepoint=info:stdout:time,uptime,level,tags -jar application.jar
```

Ý nghĩa selector:

- `gc*=info`: ghi các tag bắt đầu bằng `gc` ở level `info`, bao gồm summary GC và các nhóm tag con như `gc,heap`, `gc,phases`, `gc,marking`.
- `safepoint=info`: ghi các lần JVM đi vào safepoint và thời gian liên quan.
- `stdout`: gửi log ra standard output. Có thể thay bằng `file=gc.log` để ghi ra tệp.
- `time`: thêm thời gian lịch theo đồng hồ hệ thống.
- `uptime`: thêm thời gian đã trôi qua kể từ khi JVM khởi động.
- `level`: thêm mức log như `info` hoặc `debug`.
- `tags`: thêm nhóm tag xác định loại thông tin.

Để ghi ra tệp và tự xoay vòng log:

```bash
java -Xlog:gc*=info,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar application.jar
```

Trong cấu hình trên, JVM giữ tối đa năm tệp log trong chu kỳ xoay vòng; mỗi tệp được xoay khi đạt ngưỡng khoảng 20 MiB. Cách ghi này giúp log GC không tăng vô hạn trên đĩa.

### Chọn mức chi tiết

- Bắt đầu với `gc*=info,safepoint=info` để xem các summary, nguyên nhân và duration chính.
- Khi cần phân tích từng bước bên trong một pause, có thể bật thêm `gc+phases=debug` trong một khoảng thời gian ngắn.
- Các selector `debug` hoặc chi tiết hơn tạo nhiều dữ liệu; tránh bật rộng trong thời gian dài nếu chưa có nhu cầu.

Ví dụ:

```bash
java -Xlog:gc*=info,gc+phases=debug,safepoint=info:file=gc-detail.log:time,uptime,level,tags -jar application.jar
```

Unified Logging thay thế các cờ GC logging cũ trước Java 9. Với JDK hiện hành, dùng `-Xlog` thay cho các tùy chọn legacy như `-XX:+PrintGCDetails` hoặc `-XX:+PrintGCDateStamps`.

## 2. Đọc các phần của một dòng GC log

Một dòng summary G1 có thể có dạng:

```text
[2026-11-06T23:55:56.855+0700][0.035s][info][gc] GC(0) Pause Young (Concurrent Start) (G1 Humongous Allocation) 58M->57M(128M) 0.703ms
```

Đọc từ trái sang phải:

| Thành phần | Ý nghĩa |
| --- | --- |
| `2026-11-06T23:55:56.855+0700` | Thời gian lịch tại thời điểm ghi log, kèm offset múi giờ. |
| `0.035s` | Uptime của JVM tại thời điểm ghi dòng này. |
| `info` | Log level. |
| `gc` | Tag của nhóm thông tin. |
| `GC(0)` | Mã định danh GC event/cycle để liên kết các dòng liên quan. |
| `Pause Young` | Loại sự kiện: một lần young collection có pause. |
| `(Concurrent Start)` | Pause này khởi động một chu kỳ concurrent; bản thân nó vẫn là pause. |
| `(G1 Humongous Allocation)` | Nguyên nhân kích hoạt collection trong ví dụ. |
| `58M->57M(128M)` | Heap được dùng trước và sau collection, cùng dung lượng heap hiện tại. |
| `0.703ms` | Thời gian của pause được báo cáo cho sự kiện này. |

### Timestamp và uptime dùng cho mục đích khác nhau

- Dùng `time` khi cần đối chiếu với log ứng dụng, request, metric hoặc sự kiện ở hệ thống khác.
- Dùng `uptime` để sắp thứ tự và tính khoảng cách thời gian trong cùng một lần chạy JVM. Uptime không bị ảnh hưởng bởi việc đồng hồ hệ thống được chỉnh giờ.
- Không trừ hai timestamp khác định dạng hoặc khác múi giờ khi chưa chuẩn hóa.

## 3. Nhận diện pause và concurrent event

Trong log G1, từ khóa đầu tiên của event summary là tín hiệu quan trọng:

| Dòng log | Cách hiểu | Tính là application pause? |
| --- | --- |---|
| `Pause Young ... 0.703ms` | Young collection dừng application thread. | Có. |
| `Pause Full ... 1.452ms` | Full GC với thời gian dừng toàn ứng dụng. | Có. |
| `Pause Remark ...` | Một pause ngắn trong chu kỳ marking của G1. | Có. |
| `Pause Cleanup ...` | Một pause ngắn ở bước cleanup của G1. | Có. |
| `Concurrent Mark Cycle 2.883ms` | Tổng thời gian chu kỳ marking chạy concurrent, có thể chứa các pause con. | Không cộng toàn bộ duration này vào pause time. |
| `Concurrent Mark ...` | Pha marking chạy đồng thời với application thread. | Không. |
| `Concurrent Cleanup ...` | Pha cleanup concurrent. | Không. |

**Điểm dễ nhầm:** `Pause Young (Concurrent Start)` vẫn là một pause vì tên event bắt đầu bằng `Pause Young`. Cụm `Concurrent Start` chỉ nói rằng pause này kích hoạt chu kỳ concurrent tiếp theo.

### Concurrent không đồng nghĩa với parallel

- **Stop-the-world parallel work:** JVM dừng application thread, sau đó nhiều GC worker cùng làm việc. Log có thể ghi `Using N workers ...`; nhiều worker không có nghĩa là concurrent với ứng dụng.
- **Concurrent work:** GC worker chạy trong lúc application thread có thể tiếp tục hoạt động. Ví dụ G1 `Concurrent Mark`.

Đừng kết luận một phase là concurrent chỉ vì log nói có nhiều worker. Hãy đọc loại event `Pause` hay `Concurrent` và ngữ cảnh của collector.

## 4. Đọc duration của GC pause

Với các dòng summary, duration thường nằm ở cuối dòng:

```text
GC(0) Pause Young (Concurrent Start) (G1 Humongous Allocation) 58M->57M(128M) 0.703ms
GC(1) Pause Remark 74M->74M(128M) 0.211ms
GC(2) Pause Full (System.gc()) 90M->89M(128M) 1.452ms
```

Các giá trị trên là số đo minh họa từ một lần chạy thử; thời gian thực tế phụ thuộc JVM, collector, heap, CPU, workload và môi trường.

Khi phân tích:

1. Lấy duration từ dòng summary của pause, không lấy dòng `... start` vì đó là thông báo bắt đầu event.
2. Phân biệt từng loại pause: Young, Mixed, Remark, Cleanup, Full.
3. Đối chiếu heap trước/sau để biết GC thu hồi được bao nhiêu bộ nhớ; heap giảm ít không đồng nghĩa pause dài, và heap giảm nhiều không đồng nghĩa pause xấu.
4. So sánh pause với latency của ứng dụng ở cùng khoảng thời gian.
5. Xem nhiều lần pause, percentile và khoảng cách giữa chúng; một pause đơn lẻ không đủ mô tả trải nghiệm người dùng.

### Tính tổng thời gian pause trong một khoảng

Để ước lượng thời gian dừng do GC trong một khoảng quan sát:

1. Chọn khoảng uptime hoặc timestamp cần phân tích.
2. Lọc các dòng summary có loại `Pause` và duration hợp lệ.
3. Cộng duration của các pause thuộc khoảng đó.
4. Chia tổng pause cho độ dài khoảng quan sát nếu cần tỷ lệ pause time.

Không cộng duration của `Concurrent Mark Cycle` vào tổng pause. Chu kỳ đó có thể kéo dài trong khi application vẫn chạy phần lớn thời gian; chỉ các pause con bên trong mới được tính vào stop-the-world time.

## 5. Đọc safepoint log chi tiết hơn

GC pause thường diễn ra tại safepoint, nhưng JVM còn có các safepoint cho công việc khác. Bật `safepoint=info` để xem breakdown:

```text
[2026-11-06T23:55:56.857+0700][0.037s][info][safepoint] Safepoint "G1PauseRemark", Time since last: 1814400 ns, Reaching safepoint: 3900 ns, At safepoint: 237500 ns, Leaving safepoint: 900 ns, Total: 242300 ns
```

Ý nghĩa:

- `Time since last`: thời gian kể từ safepoint trước đó; không phải duration của pause hiện tại.
- `Reaching safepoint`: thời gian JVM cần để các thread đạt tới safepoint.
- `At safepoint`: thời gian JVM ở trạng thái safepoint.
- `Leaving safepoint`: thời gian rời safepoint và đưa các thread trở lại hoạt động.
- `Total`: tổng thời gian của các giai đoạn reaching, at và leaving.

`Total` có thể khác duration ở dòng GC pause summary vì hai dòng đo các phạm vi khác nhau. Nếu điều tra độ trễ mà ứng dụng cảm nhận, safepoint total giúp thấy chi phí rendezvous và rời safepoint; GC pause summary giúp thấy thời gian của collection.

Không phải mọi safepoint đều do GC. Khi thấy safepoint có tên khác, hãy xem reason trong log và tương quan timestamp với các nhóm log khác trước khi kết luận GC gây ra pause.

## 6. Phân biệt các sự kiện đồng thời bằng `GC(n)`

Unified GC log có thể xen kẽ nhiều dòng từ các phase và thread khác nhau. Dùng `GC(n)` để ghép các dòng thuộc cùng GC event hoặc cycle:

```text
GC(1) Concurrent Mark Cycle
GC(1) Concurrent Scan Root Regions
GC(1) Concurrent Mark
GC(1) Pause Remark ... 0.211ms
GC(1) Concurrent Mark 1.4ms
GC(1) Pause Cleanup ... 0.010ms
GC(1) Concurrent Cleanup for Next Mark
GC(1) Concurrent Mark Cycle 2.883ms
```

Các dòng cùng `GC(1)` thuộc cùng chu kỳ G1 marking trong ví dụ. Trong chu kỳ đó có cả công việc concurrent lẫn những pause ngắn. Vì vậy, một chu kỳ có thể bao gồm nhiều loại sự kiện và không nên xem nó là một khối pause duy nhất.

Khi nhiều event xuất hiện gần nhau:

- So sánh `GC(n)` trước khi ghép các dòng.
- Dùng uptime để xác định thứ tự trong cùng JVM.
- Dùng timestamp để đối chiếu với log ứng dụng hoặc metric bên ngoài.
- Đọc tag như `gc,start`, `gc,marking`, `gc,phases`, `safepoint` để nhận biết nguồn thông tin.
- Không giả định các dòng liền nhau luôn thuộc cùng một event; log từ các thread có thể xen kẽ.

`GC(n)` không phải thread ID. Nó là mã sự kiện GC; thông tin thread nếu được ghi sẽ nằm ở decorator/tag khác.

## 7. Hiểu đúng một chu kỳ G1 concurrent marking

Một chu kỳ marking G1 có thể gồm các bước sau:

1. Một collection pause có thể khởi động chu kỳ concurrent, ví dụ `Pause Young (Concurrent Start)`.
2. G1 thực hiện các phase concurrent như scan root regions và concurrent mark trong khi application thread vẫn có thể chạy.
3. G1 thực hiện `Pause Remark`, một pause cần dừng application thread để hoàn tất thông tin marking.
4. G1 tiếp tục một số phase concurrent như rebuild remembered sets hoặc cleanup.
5. G1 có thể thực hiện `Pause Cleanup` ngắn.
6. Dòng `Concurrent Mark Cycle ...` tổng kết thời gian của toàn chu kỳ.

Các phase cụ thể và thứ tự có thể khác theo JDK và cấu hình G1. Dùng log thực tế của collector đang chạy thay vì áp dụng một sơ đồ cố định cho mọi JVM.

## 8. Ví dụ hoàn chỉnh tạo GC pause và concurrent event

Chương trình sau giữ lại 44 mảng 1 MiB để tạo áp lực heap với G1. Các lần cấp phát humongous có thể kích hoạt concurrent marking; `System.gc()` được gọi để tạo một Full GC dễ nhận diện trong ví dụ. Đây là chương trình quan sát log, không phải mẫu tối ưu hóa GC cho production.

```java
import java.util.ArrayList;
import java.util.List;

public class GcLogProbe {
    public static void main(String[] args) throws Exception {
        List<byte[]> live = new ArrayList<>();
        for (int i = 0; i < 44; i++) {
            live.add(new byte[1024 * 1024]);
        }
        System.gc();
        Thread.sleep(50);
        System.out.println("live MiB: " + live.size());
    }
}
```

Lưu thành `GcLogProbe.java`, biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all GcLogProbe.java
```

Chạy G1 với unified logging ra file:

```bash
java -Xms128m -Xmx128m -XX:+UseG1GC -Xlog:gc*=info,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=2,filesize=1M GcLogProbe
```

Stdout của chương trình:

```text
live MiB: 44
```

Các dòng GC log thay đổi theo máy và lần chạy. Một lần chạy thử đã tạo các dòng dạng:

```text
GC(0) Pause Young (Concurrent Start) (G1 Humongous Allocation) 58M->57M(128M) 0.703ms
GC(1) Concurrent Mark Cycle
GC(1) Pause Remark 74M->74M(128M) 0.211ms
GC(1) Pause Cleanup 0.010ms
GC(1) Concurrent Mark Cycle 2.883ms
GC(2) Pause Full (System.gc()) 90M->89M(128M) 1.452ms
```

Khi đọc đoạn này:

- `GC(0)` là một young pause khởi động concurrent cycle.
- `GC(1)` là chu kỳ concurrent marking, chứa các pause Remark và Cleanup.
- `2.883ms` là duration toàn chu kỳ concurrent, không phải pause time.
- `GC(2)` là Full GC pause được kích hoạt bởi `System.gc()` trong chương trình thử nghiệm.

Không dùng `System.gc()` để điều khiển GC trong ứng dụng thật. GC có thể bị trì hoãn hoặc xử lý khác tùy JVM; ví dụ chỉ dùng nó để tạo một sự kiện Full GC dễ nhận biết.

## 9. Đọc log khi điều tra latency

Khi người dùng báo request chậm hoặc timeout, có thể phân tích theo quy trình:

1. Xác định timestamp hoặc uptime của request chậm trong log ứng dụng.
2. Tìm các GC pause và safepoint nằm trong cùng khoảng thời gian.
3. Ghi lại loại pause, duration, heap before/after, nguyên nhân và `GC(n)`.
4. Tách concurrent cycle khỏi pause con; không lấy duration concurrent làm thời gian request bị dừng.
5. So sánh safepoint total với GC pause summary để thấy chi phí vào/ra safepoint.
6. Đối chiếu với CPU, allocation rate, heap occupancy, thread activity và latency metric.
7. Xem nhiều cửa sổ thời gian và percentile thay vì kết luận từ một log line.

Ví dụ: nếu request mất 200 ms trong khi cùng khoảng chỉ có một GC pause 0.7 ms, pause đó không giải thích toàn bộ 200 ms. Cần xem CPU scheduling, lock contention, I/O, queueing, safepoint khác và các phase concurrent có thể làm tăng tranh chấp CPU.

Concurrent GC không dừng application thread toàn bộ thời gian, nhưng vẫn tiêu thụ CPU và băng thông bộ nhớ. Nó có thể làm request chậm gián tiếp do contention dù không tạo một pause tương ứng.

## 10. Khác biệt giữa các garbage collector

Không áp dụng tên phase G1 cho mọi collector:

- **G1:** log thường thể hiện `Pause Young`, `Pause Mixed`, `Pause Full`, `Concurrent Mark Cycle`, `Pause Remark` và các phase marking.
- **ZGC:** log và cấu trúc phase khác; nhiều công việc diễn ra concurrent và các pause thường rất ngắn. Đọc event summary và tài liệu của đúng phiên bản ZGC.
- **Shenandoah:** có các phase concurrent và pause riêng; tên và cách tổng kết khác G1.
- **Serial/Parallel GC:** đặc điểm pause và cách log khác với G1; Parallel GC có thể dùng nhiều worker trong một stop-the-world collection.

Luôn kiểm tra dòng khởi tạo GC để biết JVM đang dùng collector nào, ví dụ `Using G1`. Collector mặc định có thể thay đổi theo phiên bản JDK, nền tảng và cấu hình.

## 11. Những lỗi thường gặp

1. **Coi `Concurrent Mark Cycle` là một pause.** Đây là thời gian toàn chu kỳ concurrent, có thể chứa các pause con.
2. **Nhầm `Pause Young (Concurrent Start)` là concurrent.** Tên bắt đầu bằng `Pause`, nên vẫn là stop-the-world pause.
3. **Coi nhiều GC worker là concurrent.** Parallel worker có thể cùng làm việc trong khi application thread đã dừng.
4. **Cộng cả duration concurrent vào pause total.** Chỉ cộng các pause summary khi tính stop-the-world time.
5. **Nhầm `GC(n)` với thread ID.** Đây là mã GC event/cycle để ghép các dòng liên quan.
6. **Dùng timestamp lịch để tính mọi khoảng thời gian.** Đồng hồ hệ thống có thể được chỉnh; uptime phù hợp hơn cho elapsed time trong cùng JVM.
7. **Đọc `Time since last` như duration pause.** Đây là khoảng thời gian kể từ safepoint trước đó.
8. **Coi safepoint total bằng chính xác GC pause duration.** Hai dòng đo phạm vi khác nhau, gồm cả thời gian reaching/leaving safepoint.
9. **Bỏ qua pause Remark/Cleanup.** Một concurrent cycle vẫn có thể chứa các stop-the-world pause ngắn.
10. **So sánh log của hai collector như cùng một định dạng ngữ nghĩa.** Phase names và cách đo có thể khác.
11. **Bật debug logging quá lâu.** Log chi tiết có thể tăng dung lượng và overhead; bật theo thời gian điều tra.
12. **Dùng cờ GC logging legacy trên JDK hiện hành.** Dùng Unified Logging `-Xlog` từ Java 9 trở lên.
13. **Kết luận mọi latency spike là do GC.** Đối chiếu GC pause với CPU, I/O, lock, scheduling và application metrics.
14. **Dùng `System.gc()` trong production để tạo log.** Đây không phải cách điều khiển GC hoặc tối ưu latency.

## 12. Ghi nhớ

1. Unified JVM Logging `-Xlog` có từ Java 9; `gc*=info,safepoint=info` là điểm bắt đầu hữu ích để đọc GC và safepoint.
2. `time` là timestamp lịch; `uptime` là thời gian kể từ lúc JVM khởi động.
3. `Pause Young`, `Pause Full`, `Pause Remark` và `Pause Cleanup` là các pause; duration nằm ở dòng summary.
4. `Concurrent Mark Cycle` là thời gian toàn chu kỳ concurrent, không phải thời gian application bị dừng.
5. `Pause Young (Concurrent Start)` vẫn là pause dù nó khởi động một chu kỳ concurrent.
6. Dùng `GC(n)` để ghép các dòng cùng event/cycle; mã này không phải thread ID.
7. Safepoint log tách `Reaching`, `At`, `Leaving` và `Total`; không nhầm `Time since last` với duration.
8. Tính pause total bằng các pause summary, không cộng toàn bộ concurrent duration.
9. Concurrent GC vẫn tiêu thụ CPU và memory bandwidth, nên có thể ảnh hưởng latency gián tiếp.
10. Đọc đúng collector và phiên bản JVM; phase names không giống nhau giữa G1, ZGC, Shenandoah và Parallel GC.