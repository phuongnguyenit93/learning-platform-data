# Đo độ trễ, throughput và số lần sao chép với workload đại diện

Muốn biết Unix-domain socket có phù hợp với một ứng dụng hay không, cần đo bằng workload gần với cách ứng dụng thực sự gửi và nhận dữ liệu. Một con số throughput duy nhất hoặc một lần đo thời gian cho một message không đủ để kết luận. Hãy đo ít nhất độ trễ theo percentile, số operation hoàn tất mỗi giây, số byte truyền mỗi giây và chi phí sao chép/ cấp phát trong đường đi dữ liệu.

Java 16 bổ sung Unix-domain socket cho NIO qua `StandardProtocolFamily.UNIX`, `SocketChannel` và `ServerSocketChannel`. API này cho phép dùng cùng mô hình channel, `ByteBuffer` và `Selector` để xây dựng IPC trên cùng máy. Tuy nhiên, hiệu năng thực tế phụ thuộc kích thước payload, số client, cách framing, chế độ blocking/non-blocking, buffer, scheduling của hệ điều hành và cách ứng dụng xử lý dữ liệu.

## 1. Định nghĩa đúng các chỉ số cần đo

Trước khi chạy benchmark, hãy xác định chính xác ý nghĩa từng số liệu:

| Chỉ số | Cách hiểu | Cách báo cáo |
| --- | --- | --- |
| Latency | Thời gian từ lúc client bắt đầu một operation đến khi nhận đủ response tương ứng. | p50, p95, p99, có thể thêm p99.9 và max. |
| Throughput | Số request/response hoàn tất trong một đơn vị thời gian. | operations/second hoặc requests/second. |
| Byte throughput | Tổng byte payload được xử lý trong một đơn vị thời gian. | MiB/s hoặc GiB/s; ghi rõ tính một chiều hay cả request và response. |
| Copy count | Số lần sao chép tường minh trong code ứng dụng. | Số copy/operation và số byte ứng dụng yêu cầu copy/operation. |
| Allocation rate | Lượng object hoặc byte được cấp phát trong đường đi dữ liệu. | bytes/operation, MB/s và GC activity. |

Độ trễ round-trip (RTT) của request/response gồm thời gian ghi request, chuyển qua IPC, xử lý ở server, ghi response và đọc đủ response ở client. Nó không phải latency một chiều. Muốn đo một chiều cần đồng hồ và phương pháp đồng bộ phù hợp; không lấy timestamp của hai tiến trình rồi trừ trực tiếp nếu chưa kiểm soát sai lệch clock.

Throughput nên đếm operation đã hoàn tất, không chỉ đếm số lần gọi `write()`. `SocketChannel.write()` và `read()` có thể xử lý ít byte hơn buffer yêu cầu, vì vậy benchmark phải xử lý partial write/read và xác định ranh giới message rõ ràng.

## 2. Chọn workload đại diện cho ứng dụng

Benchmark phải phản ánh cả hình dạng dữ liệu và cách client/server tương tác. Một ma trận khởi đầu có thể gồm:

| Nhóm workload | Payload gợi ý | Mẫu tương tác | Điều cần quan sát |
| --- | --- | --- | --- |
| Message nhỏ | 32–256 byte | Request/response tuần tự | RTT, syscall và chi phí mỗi message. |
| Message vừa | 1–8 KiB | Request/response hoặc batch nhỏ | Cân bằng giữa latency và throughput. |
| Payload lớn | 64 KiB–1 MiB | Streaming hoặc truyền theo frame | Throughput, allocation và chi phí copy. |
| Nhiều client | Kích thước payload thực tế | Nhiều client đồng thời | Contention, scheduling và fairness. |
| Burst | Một nhóm request đến liên tiếp | Burst rồi idle | Queueing, backpressure và p99. |

Các kích thước trên chỉ là điểm bắt đầu để khảo sát. Hãy thay bằng phân phối payload lấy từ production hoặc từ hợp đồng API. Nếu ứng dụng gửi phần lớn message 100 byte và thỉnh thoảng gửi 2 MiB, benchmark chỉ dùng payload 64 KiB cố định sẽ không phản ánh đúng workload.

Ngoài kích thước payload, cần mô phỏng:

- Số client đồng thời và số connection được tái sử dụng.
- Tỷ lệ request/response, one-way message hoặc streaming.
- Mức độ xử lý của server sau khi nhận message.
- Kích thước batch và tần suất flush nếu protocol có buffering ở tầng ứng dụng.
- Tốc độ producer nhanh hơn consumer để quan sát backpressure.
- Kết nối mới liên tục hay giữ connection lâu dài.

Với Unix-domain socket kiểu stream, ranh giới message không được bảo toàn tự động. Protocol phải tự định nghĩa framing, ví dụ fixed-size frame hoặc length prefix. Cả server và client trong benchmark phải dùng cùng framing và cùng quy tắc đọc đủ frame.

## 3. Tách warm-up, measurement và setup

JVM cần thời gian khởi động và tối ưu code. Đo ngay những operation đầu tiên có thể trộn chi phí class loading, JIT compilation, cấp phát ban đầu và khởi tạo channel vào kết quả steady-state.

Một quy trình thực tế:

1. Khởi chạy server và chờ server bind thành công.
2. Tạo client channel và thực hiện warm-up bằng cùng protocol, payload và đường code với phép đo.
3. Bỏ dữ liệu warm-up khỏi thống kê.
4. Đo trong khoảng đủ dài để tránh kết luận từ một burst ngắn.
5. Lặp lại nhiều lần hoặc dùng nhiều fork JVM độc lập.
6. Báo cáo cấu hình máy, JDK, hệ điều hành và kết quả từng lần chạy.

Với microbenchmark CPU, dùng JMH để có warm-up, measurement iteration và fork được kiểm soát. Với end-to-end IPC, nên chạy client và server ở hai process riêng để bao gồm chi phí scheduling và kernel IPC thực tế; có thể điều khiển chúng bằng một harness riêng. Không nên xem một vòng lặp JMH trong cùng process là phép đo đầy đủ cho giao tiếp giữa hai process.

Giữ các phần setup ngoài vùng đo nếu mục tiêu là latency/throughput steady-state: không tạo `SocketChannel`, mở `Selector`, bind socket file hoặc cấp phát buffer mới trong mỗi operation nếu production tái sử dụng chúng. Nếu startup/connect latency là mục tiêu cần đo, tạo một benchmark riêng cho connection setup.

## 4. Đo RTT bằng đồng hồ monotonic

`System.nanoTime()` phù hợp để đo khoảng thời gian trong cùng JVM vì nó là đồng hồ monotonic. Không dùng `System.currentTimeMillis()` để đo latency ngắn vì thời gian hệ thống có thể bị điều chỉnh và độ phân giải không phù hợp.

Ví dụ sau đo RTT của request/response có kích thước cố định trên một `SocketChannel` blocking đã kết nối. Server echo phải đọc đủ đúng số byte của frame rồi gửi lại đủ số byte đó. Buffer được tái sử dụng để tránh cấp phát trong mỗi operation:

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;
import java.util.Arrays;

class RoundTripBenchmark {
    static long[] measure(
            SocketChannel channel,
            byte[] payload,
            int warmupOperations,
            int measuredOperations) throws IOException {

        ByteBuffer request = ByteBuffer.allocate(payload.length);
        ByteBuffer response = ByteBuffer.allocate(payload.length);

        for (int i = 0; i < warmupOperations; i++) {
            exchange(channel, request, response, payload);
        }

        long[] samples = new long[measuredOperations];
        for (int i = 0; i < measuredOperations; i++) {
            request.clear();
            request.put(payload).flip();
            response.clear();

            long start = System.nanoTime();
            writeFully(channel, request);
            readFully(channel, response);
            samples[i] = System.nanoTime() - start;
        }

        Arrays.sort(samples);
        return samples;
    }

    private static void exchange(
            SocketChannel channel,
            ByteBuffer request,
            ByteBuffer response,
            byte[] payload) throws IOException {

        request.clear();
        request.put(payload).flip();
        response.clear();
        writeFully(channel, request);
        readFully(channel, response);
    }

    private static void writeFully(SocketChannel channel, ByteBuffer buffer)
            throws IOException {
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    private static void readFully(SocketChannel channel, ByteBuffer buffer)
            throws IOException {
        while (buffer.hasRemaining()) {
            if (channel.read(buffer) < 0) {
                throw new EOFException("Peer đóng kết nối giữa frame");
            }
        }
    }

    static long percentile(long[] sortedSamples, double percentile) {
        if (sortedSamples.length == 0 || percentile <= 0 || percentile > 1) {
            throw new IllegalArgumentException("percentile hoặc samples không hợp lệ");
        }
        int index = (int) Math.ceil(percentile * sortedSamples.length) - 1;
        return sortedSamples[index];
    }
}
```

Sau khi `measure()` trả về mảng đã sắp xếp, có thể báo cáo:

```java
long p50 = RoundTripBenchmark.percentile(samples, 0.50);
long p95 = RoundTripBenchmark.percentile(samples, 0.95);
long p99 = RoundTripBenchmark.percentile(samples, 0.99);
```

Các giá trị trên có đơn vị nanosecond. Khi trình bày cho người đọc, chuyển sang microsecond hoặc millisecond và ghi rõ đơn vị. Với số lượng sample rất lớn, dùng histogram có giới hạn bộ nhớ như HdrHistogram thay vì giữ toàn bộ latency trong một mảng.

Đoạn mã là ví dụ cho một client tuần tự và frame có kích thước cố định. Server phải gửi response tương ứng cho mỗi request; không dùng code này cho protocol có frame biến độ dài nếu chưa thêm length prefix và logic đọc đủ frame. Đối với non-blocking channel, `read()` hoặc `write()` có thể trả `0`; khi đó cần tích hợp với `Selector` thay vì vòng lặp blocking này.

## 5. Đo throughput riêng với phép đo latency

Trong benchmark throughput, đo số operation hoàn tất trong một khoảng thời gian. Nếu mỗi request có `payloadBytes` và mỗi response có cùng kích thước, tổng byte payload hai chiều là `2 * payloadBytes * completedOperations`. Cần báo cáo rõ nếu chỉ tính byte request hoặc tính cả response.

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;

class ThroughputBenchmark {
    static void measure(
            SocketChannel channel,
            byte[] payload,
            int warmupOperations,
            long measurementNanos)
            throws IOException {
        if (payload.length == 0 || warmupOperations < 0 || measurementNanos <= 0) {
            throw new IllegalArgumentException("Payload, warm-up hoặc thời gian đo không hợp lệ");
        }

        ByteBuffer request = ByteBuffer.allocate(payload.length);
        ByteBuffer response = ByteBuffer.allocate(payload.length);

        for (int i = 0; i < warmupOperations; i++) {
            exchange(channel, request, response, payload);
        }

        long start = System.nanoTime();
        long completedOperations = 0;

        while (System.nanoTime() - start < measurementNanos) {
            exchange(channel, request, response, payload);
            completedOperations++;
        }

        long elapsedNanos = System.nanoTime() - start;
        double seconds = elapsedNanos / 1_000_000_000.0;
        double operationsPerSecond = completedOperations / seconds;
        double payloadMiBPerSecond =
            (completedOperations * 2.0 * payload.length)
                / (1024.0 * 1024.0 * seconds);

        System.out.printf("ops/s=%.2f, payload MiB/s=%.2f%n",
            operationsPerSecond, payloadMiBPerSecond);
    }

    private static void exchange(
            SocketChannel channel,
            ByteBuffer request,
            ByteBuffer response,
            byte[] payload) throws IOException {
        request.clear();
        request.put(payload).flip();
        response.clear();
        writeFully(channel, request);
        readFully(channel, response);
    }

    private static void writeFully(SocketChannel channel, ByteBuffer buffer)
            throws IOException {
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    private static void readFully(SocketChannel channel, ByteBuffer buffer)
            throws IOException {
        while (buffer.hasRemaining()) {
            if (channel.read(buffer) < 0) {
                throw new EOFException("Peer đóng kết nối giữa frame");
            }
        }
    }
}
```

Đoạn mã trên giả định `exchange()` dùng buffer đã tạo trước và server echo một response có cùng độ dài. Nếu protocol có header, serialization hoặc compression, hãy báo cáo riêng payload bytes và wire/application bytes để không đánh đồng chúng.

Latency và throughput nên có các lượt đo riêng hoặc ít nhất các cấu hình riêng. Ghi timestamp cho từng operation và lưu sample có chi phí CPU, cache và memory; overhead đó có thể làm giảm throughput. Nếu cần quan sát cả hai, dùng histogram sampling có kiểm soát và so sánh với một lượt throughput không ghi từng sample.

## 6. Đọc percentile thay vì chỉ xem average

Average có thể che giấu các request chậm. Ví dụ, phần lớn request có latency thấp nhưng một số request bị trì hoãn do GC, CPU contention hoặc server queue có thể làm p99 tăng mạnh.

- **p50:** latency của request ở giữa phân phối; thường gần trải nghiệm điển hình.
- **p95:** 95% request hoàn tất không chậm hơn giá trị này.
- **p99:** phản ánh tail latency; hữu ích cho service có SLO.
- **p99.9:** hữu ích khi số sample đủ lớn và cần quan sát tail sâu.
- **Max:** cho biết trường hợp chậm nhất trong sample, nhưng nhạy với outlier và thời lượng chạy.

Không so sánh p99 của hai benchmark nếu số sample hoặc thời lượng đo chênh lệch lớn. Hãy chạy đủ request để percentile có ý nghĩa, lưu histogram và ghi số lượng sample. Nếu ứng dụng có deadline, báo cáo tỷ lệ request vượt deadline cùng percentile.

## 7. Closed-loop và open-loop tạo ra góc nhìn khác nhau

Trong closed-loop benchmark, client gửi một request, chờ response rồi mới gửi request tiếp theo. Cách này dễ triển khai và đo RTT, nhưng tốc độ request tự giảm khi server chậm. Nó mô tả workload có concurrency giới hạn, không mô tả tốt hệ thống nhận request liên tục ở tốc độ cố định.

Trong open-loop benchmark, load generator phát request theo tốc độ mục tiêu độc lập với thời gian response. Cách này hữu ích để kiểm tra queueing và tail latency khi tải tăng. Tuy nhiên, phải giới hạn queue và theo dõi request bị drop hoặc chờ trong client; nếu load generator không theo kịp tốc độ phát, kết quả sẽ sai lệch.

Khi server gần bão hòa, cần ghi cả:

- Tốc độ request được phát.
- Tốc độ request hoàn tất.
- Số request đang chờ và số request bị drop/reject.
- Thời gian chờ trong client queue và thời gian RTT sau khi gửi.
- CPU, GC và context switching trong cùng khoảng đo.

Nếu chỉ đo closed-loop, latency có thể trông tốt hơn vì client tự giảm tốc khi server bị chậm. Nếu chỉ đo open-loop mà không đo queue delay, bạn có thể bỏ qua phần lớn thời gian người dùng thực sự phải chờ.

## 8. Đếm số lần copy ở tầng ứng dụng

Không có API Java chuẩn cho biết chính xác tổng số lần byte đã bị copy bên trong JVM, native socket provider và kernel. Có thể đếm các lần copy tường minh trong code ứng dụng nếu mọi thao tác copy đi qua một abstraction được kiểm soát.

Ví dụ, với overload absolute bulk put của `ByteBuffer` có từ Java 16:

```java
import java.nio.ByteBuffer;
import java.util.concurrent.atomic.LongAdder;

class CopyMetrics {
    private final LongAdder copyCalls = new LongAdder();
    private final LongAdder copiedBytes = new LongAdder();

    void copy(
            ByteBuffer destination,
            int destinationIndex,
            ByteBuffer source,
            int sourceOffset,
            int length) {

        destination.put(destinationIndex, source, sourceOffset, length);
        copyCalls.increment();
        copiedBytes.add(length);
    }

    long copyCalls() {
        return copyCalls.sum();
    }

    long copiedBytes() {
        return copiedBytes.sum();
    }
}
```

Các counter này chỉ đếm những lần copy được gọi qua `CopyMetrics`; chúng không nhìn thấy copy nội bộ trong `SocketChannel.read()`/`write()`, provider native hoặc kernel socket buffer. Hãy báo cáo đây là *application-visible copy count*, không gọi đó là tổng số memory copy của hệ thống.

Instrumentation làm tăng chi phí operation, đặc biệt khi mỗi message rất nhỏ. Chạy một lượt diagnostic có counter để tìm đường copy, sau đó chạy lượt performance riêng không có counter để đo latency/throughput. Không lấy số liệu của lượt instrumented làm kết quả hiệu năng cuối.

## 9. Direct ByteBuffer không đồng nghĩa zero-copy

`ByteBuffer.allocate()` tạo heap buffer; `ByteBuffer.allocateDirect()` yêu cầu vùng nhớ direct phù hợp hơn cho một số thao tác I/O native. Direct buffer có thể giúp giảm một số bản sao trung gian trong một số provider và workload, nhưng Java API không bảo đảm mọi lần `SocketChannel.read()` hoặc `write()` đều zero-copy.

Khi so sánh heap và direct buffer:

1. Tái sử dụng buffer trong vòng đo; không tính chi phí allocate direct buffer vào mỗi message nếu production không làm vậy.
2. Dùng cùng kích thước, framing, số client và protocol.
3. Đo cả throughput lẫn latency; lợi ích với payload lớn có thể khác payload nhỏ.
4. Theo dõi allocation và GC của heap buffer.
5. Theo dõi chi phí quản lý vùng nhớ direct và giới hạn direct memory.
6. Kiểm tra trên từng OS/JDK mục tiêu vì provider và native path có thể khác nhau.

Direct buffer thường tốn chi phí tạo và thu hồi cao hơn heap buffer. Không tạo một direct buffer mới cho từng request; hãy cân nhắc pool hoặc buffer tái sử dụng nếu benchmark và mô hình sở hữu bộ nhớ cho thấy có lợi. Pool phải có giới hạn và quy tắc trả buffer rõ ràng để tránh giữ direct memory vô thời hạn.

## 10. Dùng profiler để tìm allocation và chi phí ẩn

Số lần copy tường minh không phản ánh toàn bộ chi phí. Hãy kết hợp nhiều nguồn quan sát:

| Công cụ/quan sát | Câu hỏi cần trả lời |
| --- | --- |
| Java Flight Recorder (JFR) | Có allocation spike, GC pause, thread park hoặc lock contention không? |
| JMH với GC profiler | Một phép encode/decode hoặc copy tạo bao nhiêu byte allocation mỗi operation? |
| CPU profiler | Thời gian CPU nằm ở serialization, buffer copy, syscall wrapper hay xử lý nghiệp vụ? |
| OS profiler | Thread bị context switch, block hoặc tiêu tốn CPU kernel ở đâu? |
| Application counters | Có bao nhiêu copy tường minh và bao nhiêu byte ứng dụng yêu cầu copy? |

JMH phù hợp để cô lập các đoạn như encode/decode, copy heap buffer, copy direct buffer hoặc biến đổi `ByteBuffer`. Với benchmark micro, hãy dùng `@State`, warm-up, measurement iteration và nhiều fork; tránh benchmark một method mà compiler có thể loại bỏ kết quả vì không được sử dụng.

JFR và profiler cũng có overhead. Hãy dùng chúng trong lượt chẩn đoán riêng, hoặc xác minh overhead trước khi bật trong lượt benchmark cuối. Không suy ra số kernel copy chính xác chỉ từ số object allocation của JVM.

## 11. So sánh Unix-domain socket với TCP loopback công bằng

Nếu mục tiêu là quyết định giữa Unix-domain socket và TCP loopback, hãy chạy cả hai trên cùng máy với cùng ứng dụng, payload, framing, serialization và concurrency. Thay đổi duy nhất nên là transport và phần cấu hình bắt buộc của nó.

| Yếu tố | Unix-domain socket | TCP loopback |
| --- | --- | --- |
| Địa chỉ | Pathname/Unix-domain address | IP loopback và port |
| Phạm vi | IPC trên cùng host | TCP qua loopback interface trên cùng host |
| Framing | Ứng dụng tự định nghĩa với stream channel | Ứng dụng tự định nghĩa với stream channel |
| Chi phí cần đo | Path native, permission, IPC và scheduling | TCP stack, loopback và scheduling |
| Phạm vi kết luận | Chỉ workload và OS/JDK đã đo | Chỉ workload và OS/JDK đã đo |

Giữ nguyên:

- Cùng server/client code path và cùng lượng công việc xử lý request.
- Cùng payload distribution, framing, số client và thời gian chạy.
- Cùng chế độ blocking/non-blocking và cách tái sử dụng buffer.
- Cùng JVM flags, heap, GC, CPU placement và môi trường máy.
- Cùng chính sách timeout, queue, batch và backpressure.

Không so sánh Unix-domain socket trên một máy với TCP tới máy khác rồi kết luận chênh lệch là do transport. Cũng không so sánh UDS dùng direct buffer với TCP dùng heap buffer nếu mục tiêu là cô lập riêng ảnh hưởng của transport.

## 12. Kiểm soát môi trường và khả năng lặp lại

Kết quả IPC nhạy với hệ điều hành, kernel, filesystem namespace, JDK build, CPU governor, tải nền và container. Ghi lại ít nhất:

- Phiên bản JDK vendor/build và JVM flags.
- OS, kernel version, kiến trúc CPU và số core được cấp cho process.
- Chạy native hay trong container; pathname socket nằm trên filesystem nào.
- Heap size, GC, direct memory configuration và số thread.
- Kích thước payload, số client, số operation, warm-up và measurement duration.
- Blocking hay non-blocking, Selector hay thread-per-connection.
- Buffer heap/direct, reuse hay allocate theo operation.
- Số lần lặp, p50/p95/p99, throughput và số lỗi/drop.

Chạy nhiều lần trong điều kiện tải nền ổn định. Nếu kết quả dao động, báo cáo phân phối giữa các lần chạy thay vì chỉ chọn lần tốt nhất. Không chạy benchmark đồng thời với build, test nặng hoặc tác vụ CPU khác trên cùng host nếu mục tiêu là so sánh tinh tế.

## 13. Đọc kết quả và tìm bottleneck

Một số dấu hiệu thường gặp:

| Quan sát | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Payload nhỏ có RTT cao | Chi phí mỗi message, syscall, scheduling hoặc protocol overhead. | Giảm số round-trip, batch hợp lý, kiểm tra thread wakeup. |
| Throughput tăng rồi bão hòa khi tăng client | CPU, server worker, lock hoặc memory bandwidth đã thành bottleneck. | Profile CPU, queue, context switch và lock. |
| p99 tăng nhanh trong khi average ổn định | Queueing, GC pause, contention hoặc client/server bị scheduler trì hoãn. | Xem histogram, JFR, queue depth và GC. |
| Direct buffer chỉ tốt với payload lớn | Chi phí setup/copy chiếm tỷ lệ khác nhau theo kích thước. | Đo theo payload distribution thực tế. |
| Copy counter thấp nhưng CPU vẫn cao | Copy nội bộ, encode/decode, syscall hoặc xử lý nghiệp vụ. | Dùng CPU profiler và OS profiler. |
| Throughput cao nhưng nhiều request timeout | Benchmark không phản ánh SLO hoặc queue không được kiểm soát. | Đo open-loop, queue delay, drop và deadline miss. |

Đừng tối ưu số lần copy chỉ vì con số đó lớn. Một lần copy lớn tuần tự có thể rẻ hơn nhiều lần copy nhỏ rời rạc; chi phí còn phụ thuộc cache, kích thước dữ liệu, allocation và đường native. Dùng profiler và phép đo end-to-end để xác định copy nào thực sự nằm trên critical path.

## 14. Checklist benchmark có thể tái lập

- [ ] Workload có payload distribution và concurrency gần thực tế.
- [ ] Protocol framing giống production và xử lý partial read/write.
- [ ] Server/client chạy trong hai process riêng khi đo end-to-end IPC.
- [ ] Warm-up được tách khỏi measurement.
- [ ] Latency dùng `System.nanoTime()` và báo p50/p95/p99.
- [ ] Throughput đếm operation hoàn tất và ghi rõ cách tính bytes/s.
- [ ] Closed-loop/open-loop được chọn theo mục tiêu tải.
- [ ] Copy counter chỉ đo copy ở tầng ứng dụng và chạy riêng để tránh overhead.
- [ ] Heap/direct buffer được so sánh với cùng điều kiện.
- [ ] JFR/profiler được dùng để tìm allocation và bottleneck ẩn.
- [ ] TCP loopback baseline dùng cùng protocol và cùng workload nếu cần so sánh.
- [ ] Ghi JDK, OS, kernel, CPU, JVM flags và kết quả của nhiều lần chạy.

## 15. Những điểm cần nhớ

- Đo latency, throughput, byte throughput, copy count và allocation rate như các chỉ số riêng.
- Dùng workload đại diện về payload, concurrency, request pattern và backpressure.
- Warm-up trước khi đo; tách setup/connect khỏi steady-state nếu đó không phải mục tiêu.
- Dùng `System.nanoTime()` cho elapsed time và báo percentile thay vì chỉ average.
- Xử lý partial read/write và framing; đếm operation hoàn tất chứ không đếm lời gọi `write()`.
- Đếm copy tường minh ở ứng dụng không cho biết toàn bộ copy trong JVM/kernel.
- Direct `ByteBuffer` không bảo đảm zero-copy; cần benchmark trên JDK và OS thực tế.
- Dùng JMH cho microbenchmark, harness process riêng cho end-to-end IPC.
- So sánh TCP loopback công bằng bằng cách giữ nguyên workload và mọi điều kiện khác.

Hãy xem benchmark là phép đo một workload cụ thể trên một môi trường cụ thể. Kết quả chỉ có giá trị khi protocol, payload, concurrency, warm-up, cách thống kê và môi trường được ghi lại đầy đủ. Đo end-to-end để hiểu trải nghiệm của ứng dụng, rồi dùng profiler và microbenchmark để xác định phần nào đáng tối ưu.

## Tài liệu tham khảo

- [SocketChannel – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [ByteBuffer – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java Flight Recorder – Java SE 16 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/16/troubleshoot/diagnostic-tools.html)
- [JMH: Java Microbenchmark Harness](https://github.com/openjdk/jmh)
- [JEP 380: Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
