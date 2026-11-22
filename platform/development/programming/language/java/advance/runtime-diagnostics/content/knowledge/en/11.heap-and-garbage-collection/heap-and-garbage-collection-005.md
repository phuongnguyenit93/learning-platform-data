# 11.5. Phân biệt tần suất GC, tổng thời gian GC, pause time và thời gian tới safepoint

## Mục tiêu

Khi điều tra hiệu năng Java, câu “GC nhiều nên ứng dụng chậm” chưa đủ để kết luận nguyên nhân. Cần phân biệt **GC diễn ra bao nhiêu lần**, **thời gian được hạch toán cho GC**, **mỗi lần ứng dụng thực sự bị dừng bao lâu**, và **JVM mất bao lâu để đưa các luồng đến safepoint**. Bốn đại lượng có đơn vị, phạm vi đo và tác động khác nhau; nhầm chúng có thể dẫn tới chỉnh heap/GC sai hướng.

Bài này tập trung vào HotSpot/JDK 17+; tên log, bộ đếm và chi tiết hạch toán có thể khác theo JDK và garbage collector.

## 1. Bốn đại lượng là gì?

| Đại lượng | Câu hỏi trả lời | Đơn vị thường gặp | Không được hiểu nhầm |
| --- | --- | --- | --- |
| **Tần suất GC (GC frequency/rate)** | Trong một khoảng thời gian có bao nhiêu sự kiện GC thuộc loại đang xét? | lần/phút, lần/giây | Số lần cao không tự chứng minh mỗi lần dừng lâu hay GC tốn nhiều CPU. |
| **Tổng thời gian GC (total GC time)** | Tổng thời gian mà nguồn đo hạch toán cho hoạt động thu gom trong một cửa sổ hoặc từ khi JVM chạy? | ms, s, đôi khi % của cửa sổ | Tùy nguồn đo/collector, có thể không tương đương tổng thời gian dừng ứng dụng. |
| **Pause time (GC pause duration)** | Một lần JVM tạm dừng các luồng Java để làm công việc GC mất bao lâu? | ms, p50/p95/p99/max theo từng pause | Không phải độ dài toàn bộ chu kỳ GC khi có pha chạy đồng thời. |
| **Time to safepoint (TTSP)** | Sau khi JVM yêu cầu safepoint, mất bao lâu để đạt trạng thái safepoint? | µs, ms, đôi khi ns trong log | Không phải thời gian thực hiện GC sau khi đã đạt safepoint. |

**Phân loại sự kiện trước khi tính tần suất:** young evacuation, mixed, full GC và các pha/chu kỳ concurrent không có cùng tác động. Một chu kỳ concurrent có thể chứa nhiều pha và nhiều lần dừng ngắn. Không đếm mỗi dòng log `gc`, `gc,phases` hay mỗi pha nội bộ thành “một GC” độc lập. Ưu tiên đối chiếu GC ID, tên sự kiện và cách collector trình bày chu kỳ.

**Đặt tên đúng cho “total GC time”:** ví dụ `GarbageCollectorMXBean.getCollectionTime()`, `jstat GCT`, tổng độ dài các sự kiện GC trong log và tổng `jdk.GCPhasePause` trong JFR là những phép đo có ngữ nghĩa khác nhau. Khi báo cáo, phải ghi rõ *đang cộng cái gì*, *trong cửa sổ nào* và *dùng collector/JDK nào*.

## 2. Trục thời gian: GC, safepoint và ứng dụng

Một hoạt động cần safepoint toàn cục có thể được nhìn theo trục thời gian khái niệm:

```text
JVM yêu cầu safepoint
       |
       v
[ Reaching safepoint ] -> [ At safepoint / thực hiện VM operation ] -> [ Luồng Java tiếp tục ]
  TTSP (thời gian đạt)        thường chứa phần STW liên quan
```

- **Safepoint** là cơ chế phối hợp để JVM thực hiện một số tác vụ cần trạng thái nhất quán của các luồng. Không phải safepoint nào cũng do GC; một số VM operation khác cũng có thể yêu cầu safepoint.
- **Reaching safepoint** là khoảng JVM chờ phối hợp để đến safepoint. Một số luồng có thể đã dừng trong lúc các luồng khác chưa đến điểm an toàn; vì thế TTSP có thể góp vào độ trễ mà yêu cầu ứng dụng quan sát được.
- **At safepoint** là phần thời gian sau khi đã đạt safepoint để thực hiện công việc được yêu cầu, có thể gồm công việc GC hoặc hoạt động JVM khác. Không mặc định toàn bộ `At safepoint` là GC.
- **Pause GC** ghi trong GC log/JFR là thời gian của một pha GC có dừng ứng dụng theo phạm vi mà công cụ ghi nhận. Ranh giới đo của nó không nhất thiết trùng hoàn toàn với `At safepoint`; không lấy tổng safepoint trừ GC pause để suy ra TTSP nếu chưa xác nhận cùng sự kiện và ranh giới.
- **Concurrent GC** (ví dụ một số pha marking/relocation của G1, ZGC hoặc Shenandoah) có thể làm việc khi luồng ứng dụng vẫn chạy. Vì vậy thời gian chu kỳ GC tính theo đồng hồ thực có thể dài hơn nhiều so với từng pause STW.

Với HotSpot JDK 17, log `safepoint` thường có các trường `Reaching safepoint`, `At safepoint` và `Total` tính bằng nanosecond; `Total` bao gồm thời gian tới safepoint và thời gian ở safepoint theo ranh giới log của phiên bản đó. Với JDK mới hơn có thể xuất hiện thêm thành phần như `Leaving safepoint`. Đọc tên trường thực tế của chính phiên bản đang chạy.

## 3. Công thức đo theo cửa sổ và phép so sánh đúng

Giả sử quan sát cửa sổ thời gian dài `T` giây, bộ đếm GC tăng từ `N0` lên `N1`:

- **GC rate** = `(N1 − N0) / T` lần/giây; nhân 60 để ra lần/phút. Đếm riêng loại GC nếu muốn so sánh hành vi.
- **GC-time delta** = `GC_time_end − GC_time_start`. Khi nguồn là bộ đếm tích lũy (như JMX/jstat), phải lấy hiệu giữa hai mẫu; giá trị từ lúc JVM khởi động không phải thời gian GC của cửa sổ hiện tại.
- **GC time ratio** = `GC-time delta / (T × 1000 ms)`, nếu đại lượng ở tử số là ms. Chỉ gọi là “tỷ lệ thời gian GC theo nguồn đo X”; không tự đổi tên thành tỷ lệ STW khi X bao gồm hoặc hạch toán thời gian khác.
- **STW pause fraction** = `sum(pause_duration_ms) / (T × 1000)` khi đã thu thập đầy đủ các pause trong cửa sổ. Đây mới là phần thời gian dừng theo tập pause được đo; không suy từ số lần GC.
- **Pause mean** = tổng các pause / số pause; **p95/p99/max** cần danh sách thời gian *từng pause*. Trung bình thấp vẫn có thể che một pause rất dài.
- **TTSP** cần phân phối riêng (max/p95/p99) và đối chiếu theo timestamp với pause, request latency và các VM operation. Không gộp TTSP vào trung bình GC pause một cách tùy ý.

**Lưu ý về số liệu:** Dùng cùng cửa sổ thời gian, clock và workload; loại bỏ thời gian warm-up nếu đang so sánh steady state. Bộ đếm có thể reset khi JVM khởi động lại. Kết quả của các collector, phiên bản và công cụ khác nhau không nhất thiết cộng gộp được. Khi ít mẫu, không nên xem p99 của vài pause là chỉ số ổn định về mặt thống kê.

### Ví dụ tính tay

Trong một cửa sổ **60 giây**, giả sử có **4 GC pause STW** lần lượt **8 ms, 12 ms, 20 ms, 160 ms**:

- Tần suất của *bốn sự kiện đang xét*: `4 / 60 = 0,0667` lần/giây, hay **4 lần/phút**.
- Tổng **STW GC pause**: `8 + 12 + 20 + 160 = 200 ms`, trung bình **50 ms/pause**.
- Tỷ lệ dừng đo được: `200 / 60.000 × 100% ≈ 0,333%` thời gian cửa sổ.
- Pause lớn nhất: **160 ms**. Một đuôi độ trễ 160 ms vẫn đáng chú ý cho hệ thống nhạy p99, mặc dù tổng phần trăm dừng chỉ khoảng 0,33%.

Nếu đúng sự kiện có pause 160 ms cũng có **Reaching safepoint = 70 ms**, một luồng đã bị giữ lại sớm có thể quan sát ảnh hưởng gần **230 ms** (70 + 160 ms, bỏ qua sai khác ranh giới và tác vụ khác). Đây là ví dụ để hiểu hai pha; không được cộng mọi TTSP với mọi GC pause mà không ghép đúng sự kiện. **200 ms ở trên là tổng pause, không tự khẳng định đó là `jstat GCT` hay tổng collection time của JMX.**

## 4. Thu thập log GC và safepoint trong JDK 17+

Với một tiến trình Java khởi động mới, bật Unified Logging ngay ở command line:

```bash
java -Xms64m -Xmx64m -XX:+UseG1GC \
  -Xlog:gc*=info,safepoint=info:file=gc-safepoint.log:time,uptime,level,tags \
  GcCountersDemo
```

Dấu `\` nối dòng dùng trong shell kiểu Unix; trên PowerShell hãy đặt lệnh trên một dòng hoặc dùng cú pháp nối dòng phù hợp. Tùy tải, `gc*` có thể tạo nhiều dòng; khi chạy lâu, cân nhắc cấu hình log rotation và dung lượng lưu trữ.

Một đoạn **minh họa cấu trúc** (không phải output cố định của chương trình):

```text
[2026-01-01T10:00:00.000+0000][12.000s][info][gc] GC(18) Pause Young (Normal) (G1 Evacuation Pause) 40M->9M(64M) 160.000ms
[2026-01-01T10:00:00.001+0000][12.001s][info][safepoint] Safepoint "G1CollectForAllocation", Time since last: 3000000000 ns, Reaching safepoint: 70000000 ns, At safepoint: 160000000 ns, Total: 230000000 ns
```

Cách đọc:

1. Dòng `gc` mô tả một **G1 young evacuation pause**. `160.000ms` là thời lượng pause được GC log báo cho sự kiện đó; `40M->9M(64M)` lần lượt gợi ý mức heap trước/sau và tổng dung lượng heap trong log minh họa, không biểu thị thời gian.
2. Dòng `safepoint` báo JVM mất **70 ms để đạt safepoint**, **160 ms tại safepoint** và **230 ms tổng cộng** cho VM operation tương ứng. `Time since last` là khoảng thời gian kể từ safepoint trước, **không phải TTSP**.
3. Để ghép hai dòng trong log thật, so sánh timestamp, loại VM operation, GC ID và các pha liên quan. Không giả định mỗi dòng safepoint đều thuộc GC, hoặc mọi pause luôn có đúng một dòng safepoint tương ứng.

**Mẹo chuyển đơn vị:** `1 ms = 1.000.000 ns`. Vì thế `Reaching safepoint: 70000000 ns` = **70 ms**, không phải 70.000 ms.

## 5. Dùng jstat, JMX và Java code: bộ đếm, không phải phân phối pause

### 5.1 jstat để so hai mẫu theo thời gian

Trên HotSpot, khi tiến trình còn sống:

```bash
jstat -gcutil 12345 1000 10
```

`12345` là PID ví dụ; lệnh lấy 10 mẫu cách nhau khoảng 1.000 ms. Các cột thường gặp:

- `YGC` và `YGCT`: số sự kiện GC young và tổng thời gian được hạch toán cho chúng.
- `FGC` và `FGCT`: số sự kiện full GC và tổng thời gian liên quan.
- `GCT`: tổng thời gian GC theo số liệu jstat của JVM; đơn vị của các cột thời gian là **giây**, trong khi duration từ GC log thường là **ms**.
- Tùy phiên bản/collector, còn có các cột liên quan concurrent GC (như `CGC`, `CGCT`). Bộ đếm, loại sự kiện và mức hỗ trợ khác nhau; đọc header thực tế, không suy đoán từ tên cột của một JVM khác.

Ví dụ nếu trong khoảng 10 giây, `YGC` tăng từ 40 lên 45 và `YGCT` tăng từ 1,20 lên 1,32 giây, đó là **5 lần young GC/10 giây** và **0,12 giây thời gian young GC được jstat hạch toán**. Không đủ dữ liệu để biết pause lớn nhất hay p99; cần GC log/JFR chi tiết.

### 5.2 Đo qua `GarbageCollectorMXBean` bằng Java 17

Chương trình sau chụp bộ đếm trước/sau một đợt cấp phát. Nó minh họa rõ việc lấy **hiệu số đếm** và **hiệu thời gian**, thay vì nhầm các giá trị tích lũy từ lúc JVM khởi động với một cửa sổ ngắn.

Lưu thành **`GcCountersDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.LinkedHashMap;
import java.util.Map;

public class GcCountersDemo {
    private static Map<String, long[]> snapshot() {
        Map<String, long[]> result = new LinkedHashMap<>();
        for (GarbageCollectorMXBean gc : ManagementFactory.getGarbageCollectorMXBeans()) {
            result.put(gc.getName(),
                    new long[] {gc.getCollectionCount(), gc.getCollectionTime()});
        }
        return result;
    }

    public static void main(String[] args) {
        Map<String, long[]> before = snapshot();
        long started = System.nanoTime();

        byte[][] ring = new byte[128][];
        for (int i = 0; i < 30_000; i++) {
            ring[i % ring.length] = new byte[8 * 1024];
        }

        long elapsedNs = System.nanoTime() - started;
        Map<String, long[]> after = snapshot();

        long retainedBytes = 0;
        for (byte[] block : ring) {
            retainedBytes += block.length;
        }
        System.out.printf("Window: %.3f s; retained: %d bytes%n",
                elapsedNs / 1_000_000_000.0, retainedBytes);

        for (Map.Entry<String, long[]> entry : before.entrySet()) {
            String name = entry.getKey();
            long[] start = entry.getValue();
            long[] end = after.get(name);
            if (end == null) {
                continue;
            }
            long events = (start[0] >= 0 && end[0] >= 0) ? end[0] - start[0] : -1;
            long millis = (start[1] >= 0 && end[1] >= 0) ? end[1] - start[1] : -1;
            System.out.printf("%s: eventsDelta=%d, collectionTimeDeltaMs=%d%n",
                    name, events, millis);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GcCountersDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC \
  -Xlog:gc*=info,safepoint=info:file=gc-safepoint.log:time,uptime,level,tags \
  GcCountersDemo
```

`retainedBytes` luôn là **1.048.576 bytes** vì vòng đệm cuối cùng chứa 128 mảng, mỗi mảng 8.192 bytes. Các dòng số đếm/thời gian GC và thời lượng thực thi **không có stdout cố định**: phụ thuộc JDK, collector, kiến trúc máy, tối ưu hóa và điều kiện chạy. `-1` cho biết bộ đếm tương ứng không được JVM hỗ trợ. Một giá trị `eventsDelta=0` cũng hợp lệ nếu không xảy ra GC trong cửa sổ.

**Giới hạn quan trọng:** `getCollectionTime()` trả về thời gian collection tính theo mili giây mà implementation cung cấp, có thể là xấp xỉ; nó **không trả về danh sách từng pause, p99, TTSP**, và đối với collector concurrent không nên tự coi nó bằng tổng thời gian dừng ứng dụng. Tách metrics theo tên từng bean rồi đối chiếu log của collector.

## 6. Lấy phân phối pause bằng JFR

Để nhìn từng khoảng dừng, có thể ghi Java Flight Recorder (JFR) cho tiến trình đang chạy, ví dụ:

```bash
jcmd 12345 JFR.start name=gcdiag settings=profile duration=60s filename=gcdiag.jfr
jfr print --events jdk.GCPhasePause gcdiag.jfr
```

Lệnh `jfr print` cần chạy sau khi recording đã kết thúc và file tồn tại. Event `jdk.GCPhasePause` có `duration` và `gcId`, cho phép tổng hợp **tổng số ms dừng**, **max**, **p95/p99** trên các pause ghi nhận được. Một GC có thể có nhiều pause; muốn tính “tổng pause theo GC” thì nhóm theo `gcId` trước khi cộng. Event có thể không được ghi nếu cấu hình JFR không bật loại event tương ứng; kiểm tra settings và recording thực tế.

Hãy tách riêng **safepoint timing** từ `-Xlog:safepoint=info`. JFR có thể chứa các sự kiện safepoint/GC liên quan, nhưng loại event, mức bật và trường có thể khác theo phiên bản; không giả định TTSP luôn có trong `jdk.GCPhasePause`.

## 7. Chẩn đoán theo tổ hợp, không nhìn một số đơn lẻ

| Quan sát | Điều cần kiểm tra tiếp | Nhận định an toàn |
| --- | --- | --- |
| GC xảy ra thường xuyên, pause ngắn, tổng pause thấp | Allocation rate, kích thước young generation, CPU, throughput, heap sau GC | Tần suất cao có thể chấp nhận được; chưa đủ kết luận ảnh hưởng latency. |
| GC ít nhưng có một pause cực dài | Max/p99 pause, Full GC/mixed GC, promotion, heap occupancy, SLA | Rủi ro tail latency dù tổng thời gian dừng nhỏ. |
| Tổng thời gian GC hạch toán tăng nhanh, nhiều pause ngắn | So tổng với danh sách STW pause; collector concurrent và CPU load | Có thể mất throughput/CPU dù từng pause nhỏ; xác định định nghĩa counter. |
| GC log ghi pause ngắn nhưng `Reaching safepoint` lớn | Tên VM operation, thread state, JNI/native, thời điểm và luồng chậm phối hợp | Cần điều tra **TTSP** riêng; không vội tăng heap hay đổi GC. |
| `At safepoint` dài nhưng không ghép được GC event | VM operation nào kích hoạt, thread dump/JFR/log liên quan | Safepoint có thể phục vụ công việc JVM ngoài GC. |
| Latency của request cao, GC và TTSP đều bình thường | CPU throttling, lock contention, I/O, scheduler, mạng, application traces | Không quy mọi độ trễ của ứng dụng cho GC. |

### Quy trình điều tra thực tế

1. **Ghi rõ triệu chứng:** throughput giảm, request p99 tăng, thời gian đáp ứng đứng hình hay CPU tăng. Đánh dấu mốc thời gian và PID/JDK/collector.
2. **Chọn cửa sổ đo đồng nhất:** ví dụ một phút có tải cao; xác nhận thời điểm khởi động lại hoặc deploy.
3. **Đo tần suất theo loại GC** và **delta thời gian tích lũy** bằng counter, sau đó xem **độ dài từng pause** bằng GC log/JFR.
4. **Đối chiếu safepoint log**, đặc biệt `Reaching safepoint` lớn; xác định VM operation và chỗ trùng với request latency spike.
5. **Xem áp lực bộ nhớ và CPU:** heap trước/sau GC, allocation rate, live set, promotion, system CPU/throttling. Phân biệt pause STW với CPU của các pha concurrent.
6. **Chỉ sau khi có bằng chứng** mới thử thay đổi heap/GC, cường độ cấp phát hoặc đoạn mã gây chậm tới safepoint; đo lại trên cùng workload để so sánh p95/p99, throughput và mức CPU.

## 8. Những lỗi diễn giải dễ gặp

- **“100 GC/phút chắc chắn tệ hơn 2 GC/phút.”** Sai: phải xem loại GC, tổng chi phí và phân phối pause.
- **“GCT = 2 giây nghĩa là ứng dụng đứng hình 2 giây liên tục.”** Sai: đó có thể là giá trị cộng dồn qua nhiều collection; ngữ nghĩa của nguồn đo cần được xác nhận.
- **“Một chu kỳ concurrent kéo dài 800 ms là một pause 800 ms.”** Sai: các pha chạy đồng thời với Java threads không đồng nghĩa STW.
- **“GC pause 20 ms thì thời gian đạt safepoint cũng 20 ms.”** Sai: TTSP được đo riêng; có trường hợp cao hoặc thấp hơn nhiều.
- **“Time since last là TTSP.”** Sai: trường đó là khoảng cách thời gian từ safepoint trước, không phải thời gian chờ đạt safepoint hiện tại.
- **“Có safepoint là có GC.”** Sai: safepoint còn phục vụ các tác vụ khác của VM.
- **“Lấy GCT/T là tỷ lệ CPU mà GC đã dùng.”** Sai: wall/elapsed collection time và CPU time của các GC worker là các phép đo khác nhau.
- **“Lấy tổng pause chia số GC là p99.”** Sai: đó là trung bình nếu mẫu ghép phù hợp. p99 đòi phân phối của từng pause và đủ mẫu.
- **“Dòng nào có chữ GC trong log cũng là một lần GC.”** Sai: dòng pha, thống kê và thông điệp phụ có thể cùng thuộc một GC ID.
- **“Tối ưu GC bằng cách đếm pause mà không nhìn workload.”** Sai: thay đổi tải, cấu hình heap, collector hoặc thời gian warm-up đều làm số liệu mất tính so sánh.

## 9. Câu hỏi tự kiểm tra

1. Trong 60 giây có 30 young GC, mỗi pause 2 ms. Tần suất là bao nhiêu? Tổng STW pause là bao nhiêu? **Đáp án:** 0,5 lần/giây, 60 ms (0,1% của 60 giây); chỉ từ dữ liệu này chưa suy được tổng collection time của JMX.
2. Có một Full GC pause 400 ms nhưng GC rate thấp. Với API yêu cầu p99 dưới 100 ms, chỉ nhìn rate có đủ không? **Đáp án:** Không; cần phân phối pause và đối chiếu latency/timestamp của request.
3. Log ghi `Reaching safepoint: 80000000 ns` và `At safepoint: 15000000 ns`. Giá trị nào là TTSP? **Đáp án:** 80 ms là TTSP; 15 ms là thời gian tại safepoint; trong log JDK 17 kiểu này tổng tương ứng khoảng 95 ms.
4. Vì sao `GarbageCollectorMXBean.getCollectionTime()` không thể tự cung cấp p99 pause? **Đáp án:** Nó là bộ đếm thời gian tích lũy theo bean, không phải chuỗi duration từng lần dừng.
5. Thấy một safepoint mất 200 ms nhưng không có GC event tương ứng. Cần làm gì? **Đáp án:** Kiểm tra tên VM operation và nguồn safepoint/JFR khác trước khi kết luận đó là GC.

## Tài liệu tra cứu

- [Oracle JDK 17 — `java` / Unified Logging và `-Xlog`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle — Troubleshoot Performance Issues Using JFR, phần GC và `jdk.GCPhasePause`](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle — `jstat` command, ý nghĩa các bộ đếm GC](https://docs.oracle.com/en/java/javase/11/tools/jstat.html)
- [OpenJDK — cách HotSpot ghi `Reaching safepoint`, `At safepoint` và `Total`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/safepoint.cpp)
