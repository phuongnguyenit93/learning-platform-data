# Liên hệ Garbage Collection với latency của ứng dụng Java

## 1. Vì sao cần liên hệ GC với latency?

**Garbage Collection (GC)** thu hồi bộ nhớ của các object không còn được sử dụng. Quá trình này giúp ứng dụng không phải tự giải phóng object, nhưng có thể ảnh hưởng tới thời gian phản hồi.

**Latency** là thời gian một thao tác hoặc request cần để hoàn thành. Trong dịch vụ Java, người vận hành thường theo dõi p50, p95, p99 và giá trị cực đại thay vì chỉ nhìn thời gian trung bình.

GC có thể làm latency tăng khi JVM cần tạm dừng application thread để thực hiện một pha stop-the-world (STW). Nếu request đang được xử lý trong khoảng dừng đó, thời gian hoàn thành của request có thể tăng. Request đến trong lúc pause cũng có thể phải chờ trong queue, sau đó tiếp tục chịu ảnh hưởng bởi backlog.

Mục tiêu của phân tích không phải là mặc định đổ lỗi cho GC khi thấy latency spike. Cần ghép thời điểm request chậm với GC pause, safepoint, allocation rate, heap state và các yếu tố khác để xác định GC có đóng góp bao nhiêu vào độ trễ.

## 2. Các loại latency cần phân biệt

| Chỉ số | Ý nghĩa | Câu hỏi trả lời |
|---|---|---|
| p50 | 50% request hoàn thành trong hoặc dưới thời gian này. | Trải nghiệm điển hình ra sao? |
| p90 | 90% request hoàn thành trong hoặc dưới thời gian này. | Phần lớn request chậm hơn bình thường ở mức nào? |
| p95 | 95% request hoàn thành trong hoặc dưới thời gian này. | Tail latency đáng chú ý ra sao? |
| p99 | 99% request hoàn thành trong hoặc dưới thời gian này. | 1% request chậm nhất bị ảnh hưởng thế nào? |
| max | Request chậm nhất trong cửa sổ đo. | Có outlier cực lớn hay không? |
| mean | Thời gian trung bình. | Tổng thời gian xử lý trên mỗi request trung bình là bao nhiêu? |

Ví dụ:

| Chỉ số | Trước đợt GC bất thường | Trong cửa sổ có latency spike |
|---|---:|---:|
| p50 | 12 ms | 12 ms |
| p95 | 28 ms | 34 ms |
| p99 | 45 ms | 190 ms |
| max | 90 ms | 240 ms |

Bảng trên chỉ minh họa một tình huống: p50 gần như không đổi nhưng tail latency tăng mạnh. Đây là lý do cần xem phân phối thay vì chỉ xem average.

Percentile phải được tính từ histogram hoặc tập mẫu phù hợp. Không lấy trung bình các p99 của nhiều instance để tạo ra p99 toàn hệ thống; hãy tổng hợp histogram buckets hoặc dữ liệu request phù hợp rồi tính lại percentile.

## 3. GC pause ảnh hưởng tới request như thế nào?

Trong một pha STW, các application thread liên quan bị dừng tại safepoint để JVM thực hiện công việc cần thiết. Ví dụ, G1 Young GC thường có pha evacuation pause.

Giả sử một request bắt đầu lúc 10:00:00.100 và cần 8 ms CPU time. Nếu JVM dừng 15 ms trong lúc request đang chạy, thời gian wall-clock của request có thể tăng xấp xỉ thêm phần pause mà request đi qua.

Request đến trong lúc JVM đang pause có thể chưa được application thread xử lý. Khi JVM tiếp tục, request phải chờ thêm thời gian xử lý backlog. Vì vậy, độ trễ end-to-end có thể lớn hơn thời lượng GC pause đơn lẻ.

Để đo đúng, timer của request nên bắt đầu tại ingress hoặc điểm nhận request và kết thúc khi response hoàn tất. Nếu chỉ bắt đầu đo sau khi request đã được lấy khỏi queue, thời gian chờ trong lúc JVM pause có thể bị bỏ sót.

Một GC pause 10 ms không có nghĩa mọi request trong cùng phút đều tăng đúng 10 ms. Chỉ các request có khoảng thời gian chồng lấp với pause hoặc phải chờ backlog mới bị ảnh hưởng trực tiếp.

## 4. Phân biệt GC cycle, GC pause và concurrent phase

Không phải toàn bộ thời gian của một GC cycle đều là thời gian ứng dụng bị dừng.

| Khái niệm | Ý nghĩa | Ảnh hưởng latency |
|---|---|---|
| GC cycle | Một chu kỳ thu gom, có thể gồm nhiều pha. | Có thể kéo dài qua nhiều giây nhưng không nhất thiết dừng ứng dụng suốt thời gian đó. |
| STW pause | Khoảng thời gian application thread bị dừng. | Có thể trực tiếp kéo dài request đang chạy hoặc làm queue tăng. |
| Concurrent phase | GC làm việc đồng thời với application thread. | Có thể cạnh tranh CPU hoặc memory bandwidth, làm request chậm dù không có pause dài. |
| Safepoint | Trạng thái JVM đưa thread tới điểm an toàn để thực hiện VM operation. | Một số safepoint liên quan GC; một số khác không phải GC. |

Với collector concurrent, cần xem riêng các pha pause và concurrent. Không lấy duration của toàn bộ concurrent cycle rồi xem đó là thời gian STW.

Concurrent GC vẫn có thể làm giảm CPU dành cho ứng dụng. Khi CPU saturation xuất hiện, request latency có thể tăng dù pause rất ngắn.

## 5. Safepoint và GC pause liên quan thế nào?

GC pause thường được thực hiện tại safepoint. Khi đọc log, có thể thấy thời gian đưa thread tới safepoint, thời gian ở trong safepoint và thời gian rời safepoint.

Ví dụ thực tế trên JDK 24.0.2:

~~~text
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 35M->4M(64M) 2.200ms
Safepoint "G1CollectForAllocation", Reaching safepoint: 4800 ns, At safepoint: 2245200 ns, Leaving safepoint: 8300 ns, Total: 2258300 ns
~~~

Cách đọc:

- Heap thay đổi từ 35 MiB xuống 4 MiB trong heap capacity 64 MiB.
- GC pause được báo cáo là 2.200 ms.
- Thời gian application thread ở safepoint là khoảng 2.2452 ms.
- Tổng thời gian của safepoint, bao gồm reaching và leaving, là khoảng 2.2583 ms.

Các số liệu trên được lấy từ một lần chạy thử và chỉ dùng để minh họa. GC pause duration và safepoint total có thể khác nhau do cách đo và các giai đoạn phụ trợ.

Không phải safepoint nào cũng do GC. Các VM operation khác, deoptimization, class redefinition hoặc một số hoạt động runtime cũng có thể yêu cầu safepoint. Hãy đọc tên operation và ghép với GC log trước khi quy nguyên nhân cho GC.

## 6. Bật unified GC logging trên JDK 17+

Unified logging có từ JDK 9. Có thể bật GC và safepoint log bằng:

~~~bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Ý nghĩa:

- gc*: ghi các tag liên quan tới GC, gồm thông tin collection, heap và các pha.
- safepoint: ghi hoạt động safepoint.
- file=gc.log: ghi ra file thay vì chỉ in trên console.
- time: thời gian theo đồng hồ ngày giờ.
- uptime: thời gian từ khi JVM khởi động.
- level: mức log.
- tags: nhóm tag của từng log event.

Có thể thêm rotation để tránh file tăng không giới hạn:

~~~bash
java -Xlog:gc*,safepoint:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Trong ví dụ, JVM giữ tối đa năm file rotation, mỗi file mục tiêu 20 MiB. Tên file có PID để phân biệt process.

Đối với production, chọn mức log và rotation phù hợp với dung lượng đĩa, chính sách retention và nhu cầu điều tra. Không để log debug/trace quá chi tiết chạy vô thời hạn nếu chưa đánh giá chi phí I/O.

## 7. Đọc các trường quan trọng trong GC log

Một dòng GC thường cung cấp các thông tin:

~~~text
[2026-11-10T20:19:51.994+0700][0.308s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 35M->4M(64M) 2.200ms
~~~

| Thành phần | Ý nghĩa |
|---|---|
| 2026-11-10T20:19:51.994+0700 | Timestamp theo giờ địa phương và offset. |
| 0.308s | Uptime của JVM tại thời điểm log. |
| GC(0) | ID của GC event trong process. |
| Pause Young | Loại collection. |
| G1 Evacuation Pause | Nguyên nhân hoặc loại pause theo collector. |
| 35M->4M | Heap occupancy trước và sau collection. |
| (64M) | Heap capacity tại thời điểm đó. |
| 2.200ms | Thời lượng pause được log. |

Các dòng heap và phase tiếp theo có thể cho biết Eden, Survivor, Old regions, object promotion và công việc evacuation. Đọc toàn bộ block có cùng GC ID để hiểu collection đã làm gì.

Không suy ra memory leak chỉ từ một dòng occupancy. Hãy quan sát xu hướng sau nhiều chu kỳ GC tương đương, đặc biệt là mức sử dụng sau collection và tốc độ tăng live set.

## 8. Dùng Java Flight Recorder để xem GC và safepoint event

Java Flight Recorder (JFR) ghi event có timestamp và duration. Có thể bật recording khi khởi chạy JVM:

~~~bash
java -XX:StartFlightRecording=filename=gc-latency.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Hoặc bắt đầu recording trên JVM đang chạy:

~~~bash
jcmd 12345 JFR.start name=LatencyCapture settings=profile duration=5m filename=gc-latency.jfr
~~~

Sau khi recording hoàn tất, xem tổng quan:

~~~bash
jfr summary gc-latency.jfr
~~~

In các event GC và safepoint:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCPhaseConcurrent,jdk.SafepointBegin,jdk.SafepointEnd gc-latency.jfr
~~~

Các event hữu ích:

| JFR event | Dữ liệu cần xem |
|---|---|
| jdk.GarbageCollection | Tên collector, cause, duration, sumOfPauses và longestPause. |
| jdk.GCPhasePause | Thời gian từng pha pause. |
| jdk.GCPhaseConcurrent | Thời gian các pha GC concurrent. |
| jdk.SafepointBegin | Thời điểm và duration của safepoint. |
| jdk.GCHeapSummary | Heap usage trước/sau collection hoặc tại các thời điểm được ghi. |
| jdk.ObjectAllocationSample | Mẫu allocation để hiểu workload tạo object. |

Event có thể khác theo JDK và collector. Dùng metadata của chính JDK hoặc jfr summary để xác nhận event có mặt trong recording.

JFR settings profile thu thập nhiều chi tiết hơn default và có thể tăng overhead. Hãy chọn cửa sổ ghi đủ ngắn và đánh giá overhead nếu dùng trên production. JFR event ghi nhận thời gian và nguyên nhân GC, nhưng không tự chứng minh một request cụ thể bị chậm vì event đó.

## 9. Ghép request latency với GC timeline

Để liên hệ GC với latency, cần một timeline chung.

Một cách thực hiện:

1. Ghi latency histogram theo các cửa sổ thời gian ngắn, ví dụ 1 giây hoặc 10 giây.
2. Ghi timestamp của GC pause và safepoint.
3. Ghi timestamp request hoặc trace span khi cần điều tra một outlier.
4. Dùng cùng timezone hoặc cùng mốc thời gian để đối chiếu.
5. Đánh dấu các cửa sổ latency tăng trùng với pause.
6. Xác định request nào đang chạy hoặc đang chờ trong lúc pause.
7. So sánh với cửa sổ không có GC pause để có baseline.

GC log có cả wall-clock timestamp và JVM uptime. JFR có event start time và duration. Ứng dụng nên dùng System.nanoTime() để tính duration request vì đây là đồng hồ monotonic, không bị điều chỉnh bởi đồng hồ hệ thống.

Nếu cần ghép duration request với GC log, ghi thêm timestamp wall-clock tại điểm bắt đầu hoặc xuất trace span có start time. Không so sánh trực tiếp giá trị nanoTime với timestamp ngày giờ của GC log; hai đồng hồ có mốc gốc khác nhau.

Correlation là sự trùng khớp về thời điểm hoặc xu hướng giữa latency spike và GC event. Causation là quan hệ nhân quả, cần thêm bằng chứng như request thực sự chồng lấp pause, backlog tăng sau pause hoặc controlled experiment tái hiện được hiện tượng. Correlation đơn thuần không chứng minh causation.

Không cần log mọi request ở production nếu volume quá lớn. Có thể dùng histogram metrics để theo dõi phân phối và sampling/tracing có chọn lọc để điều tra request outlier.

## 10. Đọc latency histogram trong cùng cửa sổ với GC pause

Ví dụ trong cửa sổ 10 giây:

| Metric | Cửa sổ bình thường | Cửa sổ có GC pause |
|---|---:|---:|
| Request count | 12.000 | 12.500 |
| p50 | 14 ms | 14 ms |
| p95 | 32 ms | 41 ms |
| p99 | 58 ms | 180 ms |
| GC pause count | 0 | 3 |
| Longest GC pause | 0 ms | 24 ms |

Nếu p99 tăng trong cửa sổ có ba GC pause, đó là dấu hiệu cần điều tra thêm. Nó chưa chứng minh toàn bộ 122 ms chênh lệch p99 do GC gây ra.

Hãy kiểm tra:

- Các pause có trùng với thời điểm request chậm không?
- Có request nào đi qua nhiều pause hoặc phải chờ backlog sau pause không?
- Các request chậm có cùng endpoint, route hoặc dependency không?
- Có thay đổi CPU, lock, network hoặc database trong cùng cửa sổ không?
- p99 có tiếp tục cao trong các cửa sổ không có GC pause không?

Nếu latency tăng liên tục trong khi GC pause ngắn và hiếm, nguyên nhân có thể nằm ở concurrent GC CPU pressure, application CPU, queueing hoặc dependency khác.

## 11. Liên hệ độ dài pause với latency budget

Giả sử API có latency objective p99 dưới 200 ms. Một GC pause 25 ms có thể tiêu thụ một phần đáng kể budget nếu xảy ra trong lúc request đang chạy.

Tuy nhiên, so sánh trực tiếp pause duration với p99 chỉ là bước đầu. Ảnh hưởng phụ thuộc:

- Tỷ lệ request đang chạy khi pause bắt đầu.
- Arrival rate và queue depth.
- Thread pool size.
- Request timeout và retry behavior.
- Số pause trong một cửa sổ.
- Thời gian phục hồi throughput sau pause.

Một pause 20 ms trong lúc traffic thấp có thể không tạo ra tail latency đáng kể. Cùng pause đó trong giờ cao điểm có thể tạo backlog và khiến nhiều request hoàn thành muộn hơn 20 ms.

Đặt pause budget theo latency objective, nhưng không dùng một ngưỡng GC duration đơn lẻ làm tiêu chí duy nhất. Cần theo dõi cả pause frequency, longest pause, allocation rate, throughput và request histogram.

## 12. Tính tỷ lệ thời gian pause và GC pressure

Một số chỉ số hữu ích:

- Tổng pause time trong cửa sổ.
- Số pause trong cửa sổ.
- Pause dài nhất.
- Pause time / wall-clock time.
- Allocation rate.
- Promotion rate hoặc old-generation growth.
- Heap occupancy sau collection.
- Concurrent GC CPU time.

Ví dụ trong cửa sổ 60 giây có tổng STW pause 600 ms:

\[
\text{Pause ratio} = \frac{0.6}{60} \times 100\% = 1\%
\]

Pause ratio 1% không có nghĩa latency chỉ tăng 1%. Một pause tập trung đúng lúc peak traffic có thể tác động mạnh tới p99 dù tổng pause ratio thấp.

Đối với concurrent collector, không cộng toàn bộ duration concurrent phase vào STW pause ratio. Concurrent work có thể làm giảm CPU dành cho application thread nhưng không dừng tất cả thread.

Metric names của exporter khác nhau. Ví dụ Prometheus/JMX exporter có thể cung cấp counter hoặc histogram cho GC pause, collection count và duration; hãy xác nhận tên metric và đơn vị thực tế trong hệ thống.

## 13. Khác biệt giữa các garbage collector

| Collector | Đặc điểm cần xem khi phân tích latency |
|---|---|
| Serial GC | Collection chủ yếu stop-the-world; pause có thể lớn khi heap hoặc live set tăng. |
| Parallel GC | Ưu tiên throughput; pause có thể dài hơn khi cần thu gom nhiều object. |
| G1 GC | Có các evacuation pause STW và các pha concurrent; theo dõi từng pause và concurrent cycle. |
| ZGC | Thiết kế để pause ngắn, phần lớn công việc concurrent; vẫn cần đo pause và concurrent CPU impact. |
| Shenandoah | Thực hiện phần lớn công việc concurrent nhưng vẫn có một số pha pause; cần xem event cụ thể. |

Không nên áp dụng cùng một cách đọc Eden/Old hoặc cùng một ngưỡng pause cho mọi collector.

Collector concurrent không có nghĩa latency luôn thấp. Concurrent work cạnh tranh CPU, memory bandwidth và cache với ứng dụng. Nếu CPU gần bão hòa, latency có thể tăng dù STW pause nhỏ.

Đọc collector thực tế bằng:

~~~bash
jcmd 12345 VM.flags
~~~

Ghi lại JDK vendor, version, collector và flags khi so sánh kết quả giữa các môi trường.

## 14. Dấu hiệu GC có thể là một phần nguyên nhân

Các dấu hiệu sau giúp định hướng điều tra:

### p99 tăng đúng thời điểm có STW pause

Nếu timestamp request outlier chồng lấp với GC pause và request duration tăng gần tương ứng, có bằng chứng mạnh hơn về ảnh hưởng trực tiếp của pause.

### Nhiều pause liên tiếp và queue tăng

Một chuỗi Young GC dày có thể làm application thread mất nhiều thời gian chờ. Nếu throughput sau pause không đủ xử lý backlog, latency có thể tiếp tục cao sau khi GC kết thúc.

### Allocation rate tăng trước latency spike

Allocation pressure có thể khiến Young GC xảy ra thường xuyên hơn. Kiểm tra allocation profile và thay đổi workload trước khi giảm heap hoặc đổi collector.

### Concurrent GC trùng CPU saturation

Nếu concurrent phase kéo dài, CPU application có thể giảm. Theo dõi process CPU, GC CPU time, run queue và application throughput.

### Full GC hoặc pause dài hiếm gặp

Một Full GC dài có thể tạo outlier lớn. Kiểm tra cause, heap occupancy, live set, promotion failure, humongous allocation và memory pressure.

## 15. Những yếu tố khác có thể gây latency spike

Không phải latency spike nào cũng do GC. Các nguyên nhân khác gồm:

- CPU saturation hoặc thread bị scheduler trì hoãn.
- Lock contention, synchronized block hoặc deadlock một phần.
- Thread pool cạn hoặc queue backlog.
- Network latency, packet loss hoặc DNS.
- Database query chậm, connection pool cạn hoặc lock trong database.
- Disk I/O, page fault hoặc container throttling.
- JIT compilation, deoptimization hoặc class loading.
- Safepoint không liên quan GC.
- Retry storm, traffic burst hoặc downstream timeout.

Nếu GC pause chỉ 2 ms nhưng request tăng từ 20 ms lên 500 ms, cần tìm thêm thời gian bị tiêu tốn ở đâu. Không quy toàn bộ outlier cho GC chỉ vì GC event xuất hiện trong cùng phút.

## 16. Chạy controlled experiment để xác minh giả thuyết

Để kiểm tra GC có tác động tới latency hay không:

1. Chọn một workload cố định và dữ liệu đại diện.
2. Giữ JDK, collector, heap size và thread count cố định.
3. Ghi request latency histogram.
4. Ghi unified GC log.
5. Lặp lại workload trong cùng thời lượng.
6. Thay đổi một yếu tố mỗi lần, ví dụ allocation rate hoặc heap size.
7. So sánh pause count, longest pause, allocation rate và p95/p99.
8. Lặp lại đủ lần để đánh giá độ biến thiên.
9. Xác nhận trong workload gần production trước khi áp dụng.

Không gọi System.gc() trong benchmark để tạo pause nhân tạo rồi kết luận đó là hành vi của production. Lệnh này có thể tạo Full GC hoặc bị JVM xử lý khác theo cấu hình; nó không mô phỏng đầy đủ allocation pressure thực tế.

Không thay đổi đồng thời heap size, collector, thread count và workload vì sẽ khó xác định yếu tố nào tạo ra khác biệt.

## 17. Ví dụ thực hành: đo latency trong lúc tạo allocation

Tạo file **GcLatencyProbe.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicLongArray;

public class GcLatencyProbe {
    private static final int BUCKETS = 64;
    private static final AtomicLongArray HISTOGRAM = new AtomicLongArray(BUCKETS);
    private static final AtomicLong MAX_NANOS = new AtomicLong();
    private static final long[] CHECKSUMS = new long[4];

    private static final class Worker implements Runnable {
        private final int id;
        private final CountDownLatch ready;
        private final CountDownLatch start;

        Worker(int id, CountDownLatch ready, CountDownLatch start) {
            this.id = id;
            this.ready = ready;
            this.start = start;
        }

        @Override
        public void run() {
            ready.countDown();
            try {
                start.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            long checksum = 0;
            long operations = 0;
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(6);

            while (System.nanoTime() < deadline) {
                long requestStart = System.nanoTime();

                byte[] payload = new byte[16 * 1024];
                long value = 0;
                for (int i = 0; i < payload.length; i += 64) {
                    payload[i] = (byte) (i + operations);
                    value += payload[i];
                }

                checksum += value;
                long elapsed = System.nanoTime() - requestStart;
                int bucket = 63 - Long.numberOfLeadingZeros(Math.max(1L, elapsed));
                HISTOGRAM.incrementAndGet(bucket);
                MAX_NANOS.accumulateAndGet(elapsed, Math::max);
                operations++;
            }

            CHECKSUMS[id] = checksum;
        }
    }

    private static long percentileUpperBound(long total, double percentile) {
        long target = (long) Math.ceil(total * percentile);
        long cumulative = 0;
        for (int bucket = 0; bucket < BUCKETS; bucket++) {
            cumulative += HISTOGRAM.get(bucket);
            if (cumulative >= target) {
                return bucket == 63 ? Long.MAX_VALUE : 1L << (bucket + 1);
            }
        }
        return MAX_NANOS.get();
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(4);
        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(
                    new Worker(i, ready, start), "request-worker-" + i);
            workers[i].start();
        }

        ready.await();
        start.countDown();

        for (Thread worker : workers) {
            worker.join();
        }

        long total = 0;
        for (int i = 0; i < BUCKETS; i++) {
            total += HISTOGRAM.get(i);
        }

        long checksum = 0;
        for (long value : CHECKSUMS) {
            checksum += value;
        }

        System.out.printf("operations=%d%n", total);
        System.out.printf("p50_upper_us=%.3f%n",
                percentileUpperBound(total, 0.50) / 1000.0);
        System.out.printf("p95_upper_us=%.3f%n",
                percentileUpperBound(total, 0.95) / 1000.0);
        System.out.printf("p99_upper_us=%.3f%n",
                percentileUpperBound(total, 0.99) / 1000.0);
        System.out.printf("max_us=%.3f%n", MAX_NANOS.get() / 1000.0);
        System.out.printf("checksum=%d%n", checksum);
        System.out.println(
                "Note: percentiles are upper bounds from a base-2 histogram.");
    }
}
~~~

Probe có bốn worker thread. Mỗi operation tạo một mảng 16 KiB, ghi và đọc một số byte rồi ghi nhận thời gian bằng System.nanoTime(). Histogram dùng bucket log₂ nên percentile là cận trên của bucket, không phải percentile chính xác tới từng nanosecond.

Ví dụ này đo một thao tác allocation tổng hợp trong JVM. Nó không mô phỏng HTTP server, network, database hoặc queueing của một dịch vụ thực tế. Dùng nó để quan sát cách pause có thể xuất hiện trong thời gian xử lý operation.

## 18. Biên dịch và chạy với GC log và JFR

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 GcLatencyProbe.java
~~~

Chạy với G1, heap 64 MiB, unified GC/safepoint log và JFR:

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*,safepoint:file=gc-latency.log:time,uptime,level,tags -XX:StartFlightRecording=filename=gc-latency.jfr,settings=profile,dumponexit=true GcLatencyProbe
~~~

Sau khi chương trình kết thúc, kiểm tra GC log:

~~~bash
findstr /i "Pause Young Pause Full G1CollectForAllocation" gc-latency.log
~~~

Đọc tổng quan JFR:

~~~bash
jfr summary gc-latency.jfr
~~~

In event liên quan:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCPhaseConcurrent,jdk.SafepointBegin,jdk.SafepointEnd gc-latency.jfr
~~~

Các lệnh này đã được kiểm tra trên JDK 24.0.2 với source code tương thích Java 17. GC log ghi được Young pause và safepoint breakdown; jfr summary và jfr print đều đọc recording thành công.

Nếu dùng PowerShell, hãy để jfr summary chạy hoàn tất trước khi lọc output. Pipe trực tiếp sang Select-Object -First có thể đóng stdout sớm và khiến native command trả exit status khác 0 dù file recording vẫn hợp lệ.

## 19. Kết quả một lần chạy kiểm chứng

Một lần chạy probe trên JDK 24.0.2 với bốn worker, G1 và heap 64 MiB cho kết quả:

~~~text
operations=4985025
p50_upper_us=4.096
p95_upper_us=8.192
p99_upper_us=8.192
max_us=497116.200
checksum=-638435584
Note: percentiles are upper bounds from a base-2 histogram.
~~~

Trong cùng lần chạy, GC log ghi nhận một Young pause khoảng 2.200 ms và safepoint total khoảng 2.2583 ms.

Max latency khoảng 497 ms lớn hơn nhiều so với pause GC quan sát được. Đây là ví dụ hữu ích: một outlier lớn không thể tự động quy cho GC. Scheduling của hệ điều hành, thread bị trì hoãn, JFR overhead hoặc yếu tố môi trường có thể góp phần. Cần đối chiếu timestamp của từng request và event trước khi kết luận.

Các số liệu trên là output của một lần chạy cụ thể, không phải kết quả cố định. Khi chạy lại, số operation, histogram và max latency sẽ thay đổi theo CPU, OS, JDK, collector và tải nền.

## 20. Dùng metrics và tracing trong dịch vụ thật

Trong production, nên theo dõi latency và GC ở cùng độ phân giải thời gian.

Các nhóm metric hữu ích:

| Nhóm | Metric |
|---|---|
| Request | Request count, p50, p95, p99, timeout và error rate. |
| GC | Pause count, pause duration, longest pause và collection cause. |
| Heap | Heap used, heap after GC, old-generation occupancy. |
| Allocation | Allocation rate, promotion rate và object allocation profile. |
| CPU | Process CPU, container CPU throttling, GC CPU và run queue. |
| Thread/queue | Active threads, queue depth, rejected tasks và lock contention. |

Metric cụ thể tùy Micrometer, JMX exporter, OpenTelemetry hoặc monitoring agent. Kiểm tra đơn vị và semantics của metric trước khi ghép.

Distributed tracing giúp xác định request nào chậm ở application, database, network hoặc downstream service. Dùng trace ID và timestamp để liên hệ span với GC timeline. Tránh ghi quá nhiều log cho mọi request nếu volume lớn; histogram và sampling có thể giảm chi phí quan sát.

## 21. Cách giảm latency liên quan GC

Chọn biện pháp sau khi đã xác định nguyên nhân:

### Giảm allocation không cần thiết

- Tránh tạo object tạm trong hot path nếu có thể dùng cấu trúc phù hợp hơn.
- Giảm copy mảng hoặc buffer không cần thiết.
- Xem lại boxing/unboxing, string concatenation và collection churn.
- Tái sử dụng buffer chỉ khi ownership và concurrency được kiểm soát.

### Giảm live set và object retention

- Giới hạn cache và queue.
- Đặt TTL cho dữ liệu tạm.
- Tránh giữ tham chiếu lâu ngoài nhu cầu.
- Kiểm tra class loader, listener và collection giữ object không cần thiết.

### Chọn heap và collector phù hợp

- Đo allocation rate và live set trước khi thay đổi Xms/Xmx.
- Kiểm tra container memory limit và native memory.
- So sánh collector trên workload thực tế.
- Đặt pause goal hoặc collector flags theo tài liệu JDK đang dùng.

### Điều chỉnh concurrency và workload

- Kiểm tra thread pool và queue depth.
- Giới hạn burst allocation nếu workload có thể điều tiết.
- Tránh retry storm sau một pause dài.
- Theo dõi throughput sau GC để xem ứng dụng có xử lý kịp backlog hay không.

Tăng heap có thể giảm tần suất collection nhưng cũng có thể làm một số pause dài hơn hoặc tăng footprint. Đổi collector không tự động giải quyết allocation pressure hoặc CPU saturation. Mọi thay đổi cần được benchmark và xác nhận trong workload gần production.

## 22. Những lỗi phân tích thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| Thấy latency spike cùng phút có GC là kết luận GC gây ra | Cửa sổ thời gian quá rộng và có thể có nguyên nhân khác. | Ghép timestamp request với pause cụ thể. |
| Dùng GC cycle duration làm STW pause | Cycle có thể gồm nhiều pha concurrent. | Xem GCPhasePause và pause duration. |
| Chỉ xem average latency | Tail outlier bị che khuất. | Theo dõi p95/p99 và histogram. |
| Chỉ xem heap used | Không cho biết pause, allocation rate hoặc live set sau GC. | Ghép heap, allocation, GC và request metrics. |
| Coi mọi safepoint là GC | Nhiều VM operation không liên quan GC. | Đọc safepoint operation name và GC ID. |
| Cho rằng concurrent GC không ảnh hưởng latency | Concurrent work có thể tranh CPU và memory bandwidth. | Theo dõi GC CPU, process CPU và throughput. |
| Dùng một max latency để kết luận | Max nhạy với scheduler và noise. | Lặp lại, xem phân phối và trace outlier. |
| Gọi System.gc() để mô phỏng production | Không đại diện cho allocation và live-set thực tế. | Dùng workload tạo allocation giống ứng dụng. |
| So sánh collector với heap/traffic khác nhau | Không cô lập được nguyên nhân. | Giữ môi trường và workload cố định. |
| Không tính thời gian request chờ queue | Có thể bỏ sót tác động pause tới request chưa được xử lý. | Đo end-to-end từ ingress tới response. |

## 23. Quy trình điều tra GC và latency

Một quy trình có thể lặp lại:

1. Xác định latency objective và cửa sổ spike.
2. Kiểm tra p50/p95/p99, request count, error và timeout.
3. Xác định instance hoặc JVM bị ảnh hưởng.
4. Đọc GC log theo timestamp và uptime.
5. Tìm pause, duration, cause và heap before/after.
6. Kiểm tra safepoint breakdown để biết thời gian reaching/at/leaving.
7. Mở JFR và xem GarbageCollection, GCPhasePause, GCPhaseConcurrent và allocation event.
8. Ghép request trace hoặc histogram với timeline GC.
9. Kiểm tra CPU, thread pool, queue, lock, network và database.
10. Xác định request nào thật sự chồng lấp pause hoặc chịu backlog sau pause.
11. Đưa ra giả thuyết và thay đổi một yếu tố trong controlled experiment.
12. So sánh kết quả nhiều lần trên workload tương đương.
13. Kiểm tra lại p99, throughput, allocation và pause sau thay đổi.

Báo cáo điều tra nên ghi JDK version, collector, JVM flags, heap size, workload, thời gian, GC cause, pause duration và request percentile. Điều này giúp người khác kiểm tra lại kết luận.

## 24. Checklist trước khi kết luận GC làm tăng latency

- [ ] Đã đo request latency từ ingress tới response.
- [ ] Đã theo dõi p50, p95, p99 và request count.
- [ ] Đã bật GC log có timestamp và uptime.
- [ ] Đã bật safepoint logging khi cần phân tích STW.
- [ ] Đã xác định collector và JDK version.
- [ ] Đã phân biệt GC cycle, STW pause và concurrent phase.
- [ ] Đã ghép timestamp của request chậm với pause cụ thể.
- [ ] Đã kiểm tra GC cause và heap before/after.
- [ ] Đã xem JFR GC event và allocation event.
- [ ] Đã kiểm tra queue depth và request backlog.
- [ ] Đã kiểm tra CPU, scheduler, lock, network và database.
- [ ] Đã phân biệt tương quan với quan hệ nhân quả.
- [ ] Đã lặp lại controlled experiment.
- [ ] Đã xác nhận thay đổi bằng workload gần production.

## 25. Tài liệu tham khảo

- Oracle JDK 24 — Unified Logging: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — Diagnostic Tools và Java Flight Recorder: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Java Flight Recorder event reference: https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html
- Java SE 17 System.nanoTime(): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()

GC có thể ảnh hưởng trực tiếp tới request qua STW pause và gián tiếp qua concurrent CPU pressure hoặc backlog. Muốn chứng minh ảnh hưởng, hãy ghép request latency histogram và trace với timestamp GC/safepoint, phân biệt pause với concurrent phase, rồi kiểm tra các nguyên nhân cạnh tranh trước khi thay đổi heap hoặc collector.