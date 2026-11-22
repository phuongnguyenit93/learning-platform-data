# Đặt tiêu chí chấp nhận và kiểm tra hồi quy hiệu năng trong CI

Kiểm tra hiệu năng trong CI cần trả lời hai câu hỏi: phiên bản mới có đáp ứng mục tiêu hiệu năng của sản phẩm hay không, và nó có làm chậm đáng kể so với phiên bản chuẩn đã được chấp nhận hay không. Để trả lời đáng tin cậy, nhóm phát triển phải xác định workload đại diện, chỉ số cần đo, môi trường đo, baseline và ngưỡng chấp nhận trước khi biến kết quả benchmark thành điều kiện pass/fail.

Với ứng dụng Java 21, có thể kết hợp JMH cho microbenchmark, bài kiểm thử tải cho hành vi đầu cuối, JFR và GC log để điều tra nguyên nhân. Không nên dùng một phép đo thời gian đơn lẻ trên runner CI dùng chung làm cổng duy nhất: nhiễu từ CPU, scheduling, JIT, GC và môi trường có thể lớn hơn mức hồi quy cần phát hiện.

## 1. Phân biệt tiêu chí hiệu năng và kiểm tra hồi quy

Hai mục tiêu có liên quan nhưng khác nhau:

- **Tiêu chí chấp nhận (acceptance criteria):** hiệu năng phải đạt mức nào để đáp ứng yêu cầu sản phẩm hoặc SLA/SLO.
- **Kiểm tra hồi quy (regression check):** hiệu năng của phiên bản hiện tại có giảm đáng kể so với baseline đã chấp nhận hay không.

Ví dụ, một API có thể vẫn đáp ứng p99 dưới 200 ms nhưng chậm hơn 25% so với phiên bản trước. Nó đạt SLO hiện tại nhưng có hồi quy cần điều tra. Ngược lại, một thay đổi có thể nhanh hơn baseline 10% nhưng p99 vẫn vượt giới hạn 200 ms; nó cải thiện tương đối nhưng chưa đạt tiêu chí sản phẩm.

Vì vậy, CI nên đánh giá cả hai:

1. Kiểm tra giới hạn tuyệt đối theo yêu cầu sản phẩm.
2. So sánh tương đối với baseline ổn định.
3. Kiểm tra độ tin cậy của phép đo trước khi kết luận.

## 2. Chọn chỉ số đúng với workload

Không có một chỉ số duy nhất đại diện cho hiệu năng. Chọn metric theo loại ứng dụng và mục tiêu người dùng.

| Nhóm chỉ số | Ví dụ | Khi hữu ích |
|---|---|---|
| Latency | p50, p95, p99, p999, thời gian xử lý mỗi operation | API, tương tác người dùng, tác vụ có deadline |
| Throughput | requests/s, operations/s, records/s | Batch, service xử lý nhiều request |
| Error rate | lỗi, timeout, request bị từ chối | Đảm bảo tốc độ không đạt được bằng cách bỏ request |
| CPU | CPU time, utilization, throttling | Phát hiện chi phí tính toán hoặc GC tăng |
| Memory | heap, RSS, allocation rate, live set | Kiểm soát bộ nhớ và allocation pressure |
| GC | pause, allocation stall, GC CPU | Xác định GC ảnh hưởng tới latency hoặc throughput |
| Concurrency | số request đồng thời, queue depth, active threads | Kiểm tra khả năng chịu tải và điểm bão hòa |
| I/O | connection pool wait, disk/network throughput | Phân biệt giới hạn ứng dụng với giới hạn phụ thuộc bên ngoài |

Với API, thường cần ít nhất throughput, p95/p99 latency và error rate. Chỉ đo latency trung bình có thể che giấu một nhóm request rất chậm. Với batch, records/second và tổng thời gian hoàn thành có thể quan trọng hơn p99 của từng record.

Luôn ghi nhận cả tải đầu vào và lượng công việc thực sự hoàn tất. Một hệ thống có thể biểu diễn latency thấp giả tạo nếu request bị từ chối hoặc timeout trước khi được tính vào mẫu thành công.

## 3. Xác định workload đại diện trước khi đặt ngưỡng

Benchmark chỉ có ý nghĩa nếu phản ánh công việc thật. Trước khi viết benchmark hoặc pipeline, mô tả workload bằng các thuộc tính cụ thể:

- Kích thước và phân bố dữ liệu: nhỏ, trung bình, lớn; dữ liệu thường gặp và trường hợp biên.
- Tỷ lệ thao tác: đọc/ghi, cache hit/miss, parse/serialize, truy vấn.
- Mức đồng thời: số worker, số request đồng thời và tốc độ gửi request.
- Thời lượng: warm-up, steady-state, burst và soak nếu cần.
- Phụ thuộc: database, HTTP service, filesystem, message broker.
- Kết quả cần giữ đúng: output, side effect, số record xử lý và error rate.

Không nên tạo workload chỉ có dữ liệu nhỏ hoặc cache luôn nóng nếu production thường xử lý dữ liệu lớn và cache miss. Cũng không nên benchmark với dữ liệu hoàn toàn ngẫu nhiên nếu phân bố production có đặc điểm khác, chẳng hạn key lặp lại hoặc độ dài chuỗi lệch mạnh.

Giữ bộ dữ liệu và cách tạo dữ liệu ổn định giữa baseline và candidate. Nếu workload thay đổi, cần tạo baseline mới có phiên bản và ghi rõ lý do thay đổi.

## 4. Phân biệt microbenchmark và load test

**Microbenchmark** đo một đoạn code hoặc một operation nhỏ trong điều kiện kiểm soát, ví dụ thuật toán parse, cấu trúc dữ liệu, chuyển đổi object hoặc hàm tính toán. JMH là công cụ phù hợp cho JVM vì nó hỗ trợ warm-up, measurement iteration, fork JVM và các chế độ đo.

**Load test hoặc end-to-end performance test** đo ứng dụng trong điều kiện gần với vận hành: request đi qua routing, serialization, database, cache và network. Nó phản ánh latency và throughput của toàn hệ thống, nhưng khó cô lập nguyên nhân.

| Loại kiểm thử | Câu hỏi trả lời | Công cụ/cách làm |
|---|---|---|
| Microbenchmark | Hàm hoặc thuật toán này nhanh/chậm bao nhiêu? | JMH |
| Component benchmark | Một thành phần có đáp ứng tải và latency mục tiêu không? | Harness riêng, dependency giả lập hoặc môi trường kiểm soát |
| Load test | Service xử lý được bao nhiêu request với p99 và error rate nào? | Load generator và môi trường gần production |
| Soak test | Hiệu năng và bộ nhớ có suy giảm theo thời gian không? | Tải ổn định trong thời gian dài, theo dõi memory/GC |
| Stress test | Điểm bão hòa và hành vi khi quá tải là gì? | Tăng tải có kiểm soát tới khi đạt giới hạn |

Không dùng kết quả JMH để khẳng định p99 của API production. Ngược lại, load test toàn hệ thống thường không đủ nhạy để kết luận một thay đổi nhỏ trong một method đã nhanh hơn bao nhiêu.

## 5. Thiết kế microbenchmark bằng JMH

JMH (Java Microbenchmark Harness) là công cụ benchmark JVM được duy trì riêng, không phải API tích hợp sẵn trong JDK. Dùng JMH thay vì tự đo bằng `System.nanoTime()` quanh một vòng lặp đơn giản, vì JIT compiler, dead-code elimination, constant folding, warm-up và GC có thể làm phép đo tự viết sai lệch.

Ví dụ so sánh hai cách đếm token trong một chuỗi:

```java
package com.example.bench;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class TokenizeBenchmark {
    @Param({"128", "4096"})
    public int tokenCount;

    private String input;

    @Setup(Level.Trial)
    public void setUp() {
        StringBuilder builder = new StringBuilder();

        for (int i = 0; i < tokenCount; i++) {
            if (i > 0) {
                builder.append(',');
            }
            builder.append("token").append(i);
        }

        input = builder.toString();
    }

    @Benchmark
    public int regexSplit() {
        return input.split(",").length;
    }

    @Benchmark
    public int scanCharacters() {
        int count = 1;

        for (int i = 0; i < input.length(); i++) {
            if (input.charAt(i) == ',') {
                count++;
            }
        }

        return count;
    }
}
```

Các điểm cần hiểu:

- `@State(Scope.Thread)` tạo state riêng cho mỗi benchmark thread.
- `@Param` chạy benchmark với nhiều kích thước dữ liệu.
- `@Setup(Level.Trial)` chuẩn bị dữ liệu ngoài phần được đo.
- `@Warmup` cho JVM thời gian biên dịch JIT và ổn định hành vi.
- `@Measurement` định nghĩa các iteration dùng để lấy kết quả.
- `@Fork(3)` chạy nhiều JVM process độc lập để giảm ảnh hưởng trạng thái của một JVM duy nhất.
- Giá trị trả về từ benchmark được JMH tiêu thụ để tránh một số dạng dead-code elimination.

Ví dụ chỉ minh họa cấu trúc JMH. Trong benchmark thực tế, cần bảo đảm hai phương thức tạo ra kết quả tương đương về mặt nghiệp vụ và dữ liệu có phân bố đại diện. Nếu muốn đo cấu trúc chia sẻ giữa nhiều thread, hãy chọn scope và số benchmark thread phù hợp thay vì mặc định dùng state riêng từng thread.

## 6. Warm-up, measurement và fork

Một benchmark JVM cần phân biệt thời gian warm-up với thời gian measurement.

- **Warm-up:** chạy code để JIT compiler có cơ hội biên dịch các đường chạy nóng và runtime đạt trạng thái ổn định.
- **Measurement:** thu kết quả sau warm-up.
- **Fork:** chạy benchmark trong JVM process mới, giúp tách các lần đo khỏi trạng thái JIT/heap của lần trước.

Lệnh chạy JMH có thể chỉ định rõ cấu hình và xuất JSON:

```bash
java -jar target/benchmarks.jar '.*TokenizeBenchmark.*' \
  -f 3 -wi 5 -i 8 -w 1s -r 1s -t 1 \
  -rf json -rff target/tokenize-results.json
```

Trong đó:

- `-f 3`: ba fork JVM.
- `-wi 5`: năm warm-up iterations.
- `-i 8`: tám measurement iterations.
- `-w 1s`: mỗi warm-up iteration kéo dài một giây.
- `-r 1s`: mỗi measurement iteration kéo dài một giây.
- `-t 1`: một benchmark thread.
- `-rf json` và `-rff`: xuất kết quả dạng JSON vào file.

Các con số trên là cấu hình minh họa, không phải cấu hình tối ưu cho mọi benchmark. Benchmark ngắn có thể cần warm-up lâu hơn nếu code có nhiều nhánh nóng hoặc allocation phức tạp. Benchmark concurrency cần chọn số thread phù hợp với tình huống sử dụng.

JMH hỗ trợ nhiều mode:

| Mode | Ý nghĩa | Ví dụ đơn vị |
|---|---|---|
| `Throughput` | Số operation trong một đơn vị thời gian | ops/s |
| `AverageTime` | Thời gian trung bình cho một operation | ns/op, us/op |
| `SampleTime` | Lấy mẫu thời gian từng operation để xem phân bố | ns/op, percentiles |
| `SingleShotTime` | Đo một lần thực thi operation hoặc batch | ms/op |

Chọn mode theo câu hỏi cần trả lời. Không dùng average time để suy ra tail latency của một service nhiều tầng; mode và workload của microbenchmark không mô phỏng đầy đủ queueing, network và dependency.

## 7. Tránh các lỗi phổ biến khi viết JMH benchmark

Một benchmark có thể cho số đẹp nhưng không đo đúng công việc cần tối ưu. Hãy kiểm tra các lỗi sau:

- **Đo cả setup ngoài ý muốn:** tạo dữ liệu hoặc khởi tạo object trong method benchmark dù production không làm vậy, hoặc ngược lại bỏ qua chi phí mà production thực sự phải trả.
- **Dead-code elimination:** tính kết quả nhưng không sử dụng; JMH hỗ trợ tiêu thụ giá trị trả về hoặc dùng `Blackhole` khi cần.
- **Constant folding:** benchmark chỉ dùng một hằng số khiến JIT tối ưu bỏ phần lớn công việc.
- **Dữ liệu không đại diện:** chỉ thử một kích thước hoặc một trường hợp thuận lợi.
- **Không có warm-up/fork:** kết quả bị ảnh hưởng bởi trạng thái JIT và heap.
- **Benchmark quá nhỏ:** chi phí harness, timer hoặc scheduling lớn hơn công việc được đo.
- **Trộn nhiều mục tiêu:** một method vừa parse, vừa đọc file, vừa gọi network khiến không xác định được phần nào thay đổi.

Nếu dùng `Blackhole`, đặt nó ở vị trí cần tiêu thụ kết quả; không thêm thao tác phụ không có trong production vào phần được đo. Nếu dùng `@Setup(Level.Invocation)`, lưu ý chi phí gọi setup và cách JMH tách nó khỏi phần benchmark; chỉ dùng khi mỗi invocation thật sự cần trạng thái mới.

## 8. Đặt tiêu chí chấp nhận bằng bảng rõ ràng

Mỗi tiêu chí nên chỉ rõ metric, điều kiện workload, ngưỡng, cách tổng hợp và hành động khi vượt ngưỡng.

Ví dụ mẫu cho một API (các số chỉ minh họa, phải được thay bằng SLO và baseline thực tế):

| Metric | Tiêu chí sản phẩm | Regression tolerance | Khi không đạt |
|---|---:|---:|---|
| p95 latency | ≤ 120 ms | Tăng tối đa 5% so baseline | Fail nếu vượt SLO hoặc hồi quy có ý nghĩa |
| p99 latency | ≤ 200 ms | Tăng tối đa 5% so baseline | Fail khi vượt giới hạn đã thống nhất |
| Throughput | ≥ 2.000 req/s | Giảm tối đa 3% so baseline | Điều tra CPU, GC, lock và dependency |
| Error/timeout rate | ≤ 0,1% | Không tăng vượt biên thống kê đã đặt | Fail nếu vượt SLO |
| Process memory | ≤ memory budget | Không tăng quá ngân sách cho phép | Điều tra heap, native memory và retention |

Không có ngưỡng 3% hay 5% phù hợp với mọi dự án. Nếu độ nhiễu của runner là 4%, ngưỡng 2% sẽ tạo nhiều false positive. Nếu ứng dụng có SLA rất chặt, mức tăng 5% có thể quá rộng. Hãy đo noise floor trước, rồi chọn tolerance dựa trên tác động sản phẩm và khả năng phát hiện ổn định.

Mỗi tiêu chí cần có chủ sở hữu và lý do: SLA khách hàng, ngân sách hạ tầng, chi phí vận hành hay yêu cầu thời gian xử lý. Tránh tạo threshold chỉ vì một lần benchmark trước đó đạt được một con số đẹp.

## 9. Thiết lập baseline đáng tin cậy

Baseline là kết quả của phiên bản đã được chấp nhận trong môi trường đo được kiểm soát. Nó phải có đủ metadata để có thể so sánh về sau:

- Commit hoặc version ứng dụng.
- JDK vendor, version và build.
- Phiên bản JMH và cấu hình benchmark.
- CPU model, số core, memory, OS và container quota.
- JVM flags, heap size và GC được sử dụng.
- Dataset, workload, concurrency và thời gian chạy.
- Kết quả thô, score, error/uncertainty và timestamp.

Không nên cập nhật baseline tự động bằng kết quả của mọi build. Nếu candidate đã chậm hơn, việc tự động lấy nó làm baseline sẽ làm mất dấu hồi quy. Chỉ cập nhật baseline sau khi kết quả được review, nguyên nhân thay đổi được hiểu và phiên bản mới được chấp nhận.

Khi so sánh pull request, tốt nhất chạy base commit và candidate trên cùng loại runner, cùng cấu hình và cùng dataset. Có thể chạy nhiều lần hoặc xen kẽ thứ tự base/candidate để giảm ảnh hưởng của nhiệt độ CPU, background load và thay đổi trạng thái máy.

## 10. Kiểm soát nhiễu của môi trường CI

Hiệu năng JVM nhạy với môi trường. Trước khi dùng kết quả làm cổng merge, hãy kiểm soát:

- **Runner:** ưu tiên máy chuyên dụng hoặc runner có đặc tính ổn định; tránh nhiều job tranh CPU/RAM.
- **CPU:** giữ cùng model, số core khả dụng, quota và chính sách frequency nếu có thể.
- **Container:** dùng cùng CPU/memory limit; ghi nhận throttling.
- **JDK:** giữ cùng vendor, version, build và JVM flags.
- **GC/heap:** giữ cùng collector và heap settings khi so sánh một thay đổi code.
- **OS/dependency:** giữ phiên bản hệ điều hành, thư viện và dịch vụ phụ thuộc tương đương.
- **Dataset:** dùng cùng dữ liệu, seed và phân bố request.
- **Warm-up:** chạy đủ để JIT và cache đạt trạng thái có thể so sánh.
- **Background activity:** tránh backup, scan, build khác hoặc tác vụ gây tải cạnh tranh trên runner.

Không nên so sánh benchmark từ laptop của developer với runner CI khác CPU rồi dùng tỷ lệ đó làm regression gate. So sánh tương đối chỉ có ý nghĩa khi môi trường và workload đủ tương đồng.

Nếu bắt buộc dùng runner dùng chung, hãy xem kết quả như tín hiệu cảnh báo hoặc chạy lại trên runner ổn định trước khi chặn merge. Không lặp lại benchmark cho đến khi có lần pass rồi bỏ qua các lần fail; cần lưu toàn bộ kết quả để nhìn thấy mức độ biến động.

## 11. So sánh candidate với baseline

Với metric càng thấp càng tốt như latency hoặc thời gian xử lý:

`Regression (%) = (candidate / baseline - 1) × 100`

Với metric càng cao càng tốt như throughput:

`Regression (%) = (1 - candidate / baseline) × 100`

Ví dụ:

| Metric | Baseline | Candidate | Thay đổi |
|---|---:|---:|---:|
| p99 latency | 100 ms | 112 ms | Chậm hơn 12% |
| Throughput | 10.000 req/s | 9.500 req/s | Giảm 5% |
| Average operation time | 20 us | 19 us | Nhanh hơn 5% |

Đừng so sánh hai score nếu chúng dùng đơn vị, mode, input hoặc cấu hình khác nhau. Với JMH, giữ nguyên benchmark parameters, forks, warm-up, measurement và JVM flags khi so sánh.

JMH cung cấp score và thông tin sai số/độ không chắc chắn. CI nên dùng phương pháp thống kê nhất quán để đánh giá mức thay đổi, chẳng hạn tổng hợp nhiều fork và so sánh khoảng biến thiên cùng ngưỡng tác động thực tế. Nếu kết quả nằm sát ngưỡng hoặc nhiễu lớn, đánh dấu inconclusive và chạy lại có kiểm soát thay vì tự động kết luận hồi quy.

## 12. Xác định pass, warning và fail

Có thể chia kết quả CI thành ba mức:

| Trạng thái | Điều kiện ví dụ | Hành động |
|---|---|---|
| Pass | Đạt SLO và không có hồi quy vượt tolerance | Cho phép tiếp tục pipeline |
| Warning | Kết quả gần ngưỡng, độ nhiễu cao hoặc có thay đổi nhỏ cần theo dõi | Lưu artifact, thông báo nhóm phụ trách |
| Fail | Vượt SLO hoặc hồi quy có ý nghĩa, được xác nhận trong môi trường ổn định | Chặn merge/release theo policy |

Một lần đo bất thường do runner bị throttling hoặc có job khác chiếm CPU nên được đánh dấu là lỗi môi trường/inconclusive, không phải tự động gán cho code. Tuy nhiên, phải giữ lại log và metadata để xác minh; không được âm thầm bỏ kết quả fail.

Nên có quy tắc rõ về số lần xác nhận và người có quyền chấp nhận ngoại lệ. Nếu cho phép override, lưu lý do, phạm vi và thời hạn; tránh biến warning thành cơ chế bỏ qua vĩnh viễn.

## 13. Tổ chức performance checks trong CI

Không nhất thiết chạy toàn bộ benchmark nặng trên mọi pull request. Có thể phân tầng:

| Giai đoạn | Nội dung | Mục tiêu |
|---|---|---|
| Mỗi pull request | Bộ microbenchmark nhỏ, ổn định; component smoke test | Phát hiện thay đổi lớn, rẻ và nhanh |
| Merge vào nhánh chính | Benchmark đại diện với nhiều fork và runner ổn định | Xác nhận candidate trước khi phát hành |
| Nightly hoặc định kỳ | Load test, soak test, nhiều dataset/concurrency | Phát hiện xu hướng, memory growth và saturation |
| Trước release | Benchmark đầy đủ trên môi trường gần production | Xác nhận SLO và capacity |

Một pipeline tổng quát:

```text
Build
  |
Unit / integration tests
  |
Correctness checks
  |
Performance smoke
  |-- không đủ mẫu hoặc runner nhiễu --> Inconclusive
  |-- regression vượt ngưỡng ----------> Fail
  |-- trong giới hạn ------------------> Pass
  |
Artifact + report
  |
Merge / release policy
```

Performance smoke nên tập trung vào các benchmark có tín hiệu ổn định và thời gian chạy hợp lý. Những bài load/soak dài nên chạy ở runner và môi trường có kiểm soát hơn, có thể theo lịch hoặc trước release.

## 14. Ví dụ cấu trúc một job CI

Tên bước và cú pháp YAML cụ thể phụ thuộc nền tảng CI. Về logic, job cần checkout candidate, lấy baseline đã duyệt, xác nhận môi trường, chạy cùng benchmark, lưu kết quả và gọi bộ so sánh.

Ví dụ lệnh chạy benchmark:

```bash
java -jar target/benchmarks.jar '.*CriticalPathBenchmark.*' \
  -f 3 -wi 5 -i 8 -w 1s -r 1s \
  -rf json -rff artifacts/candidate.json
```

Job so sánh cần:

1. Tải baseline đúng version và metadata.
2. Kiểm tra JDK, CPU class, JVM flags và benchmark parameters tương thích.
3. Chạy candidate trên runner cùng loại.
4. Phân tích JSON theo metric và tolerance đã cấu hình.
5. Lưu JSON, GC log, JFR và report làm CI artifact.
6. Trả exit code theo pass/warning/fail policy.

Không nên hard-code một kết quả score kỳ vọng trực tiếp vào test unit. Tách benchmark, baseline và comparator giúp cập nhật ngưỡng có kiểm soát mà không làm thay đổi logic kiểm thử chức năng.

## 15. Kết hợp JFR và GC log khi có hồi quy

Khi benchmark phát hiện regression, bước tiếp theo là tìm nguyên nhân. JFR và unified GC logging giúp giải thích sự thay đổi:

- Allocation rate tăng có thể do tạo thêm object tạm hoặc copy dữ liệu.
- GC CPU/pause tăng có thể do allocation pressure hoặc live set lớn hơn.
- CPU tăng nhưng allocation ổn định có thể do thuật toán, contention hoặc JIT khác.
- p99 tăng nhưng CPU thấp có thể do I/O, queueing, lock contention hoặc dependency chậm.
- RSS tăng trong khi heap ổn định có thể liên quan native memory, direct buffer hoặc thread stack.

Có thể chạy candidate với JFR trong một lần profiling riêng:

```bash
jcmd <pid> JFR.start name=PerformanceInvestigation \
  settings=profile duration=60s filename=performance.jfr
```

Và bật GC log trong lần chạy benchmark:

```bash
-Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags
```

Profiling có thể tạo overhead; không nhất thiết bật mọi event chi tiết trong lần benchmark dùng để so score. Tách lần đo chuẩn để xác nhận regression và lần profiling để tìm nguyên nhân. Giữ workload đủ giống nhau để kết quả điều tra còn liên quan.

## 16. Cập nhật baseline và xử lý ngoại lệ

Baseline cần thay đổi khi có lý do được chấp nhận, chẳng hạn:

- Thay đổi có chủ đích về thuật toán hoặc kiến trúc.
- Nâng JDK, đổi vendor/build hoặc thay đổi JVM flags.
- Thay đổi dataset hoặc workload theo hành vi sản phẩm mới.
- Thay đổi phần cứng runner hoặc quota CI.

Khi thay đổi, hãy chạy cả baseline cũ và mới trong môi trường tương thích nếu có thể, lưu kết quả trước/sau và ghi lại nguyên nhân. Không gộp thay đổi baseline với thay đổi code tối ưu nếu muốn biết tác động của từng yếu tố.

Ngoại lệ hiệu năng nên có chủ sở hữu, lý do và thời hạn xem xét lại. Nếu một regression được chấp nhận để đổi lấy tính năng, ghi rõ mức ảnh hưởng, metric liên quan và kế hoạch xử lý; tránh để ngoại lệ không thời hạn.

## 17. Checklist trước khi bật performance gate

- [ ] Workload phản ánh dữ liệu và mức đồng thời thực tế.
- [ ] Metric và hướng tốt/xấu được xác định rõ.
- [ ] Có SLO hoặc acceptance threshold theo nhu cầu sản phẩm.
- [ ] Baseline được tạo từ phiên bản đã chấp nhận và có metadata.
- [ ] Candidate và baseline chạy trên cùng loại runner/JDK/configuration.
- [ ] JMH có warm-up, measurement và forks phù hợp.
- [ ] Kết quả có độ không chắc chắn và được so sánh theo quy tắc thống kê nhất quán.
- [ ] Nhiễu runner được đo và có trạng thái inconclusive.
- [ ] Artifact thô, log và report được lưu lại.
- [ ] Quy tắc pass/warning/fail và ngoại lệ được thống nhất.
- [ ] Load/soak test dài được chạy ở giai đoạn phù hợp.
- [ ] Baseline chỉ được cập nhật sau review.

## 18. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng thời gian của một lần chạy làm gate | False positive do JIT, scheduling và CPU noise | Warm-up, forks, lặp lại và runner ổn định |
| Chỉ đo average latency | Che giấu tail latency | Theo dõi p95/p99 và error rate |
| So sánh kết quả từ hai máy khác cấu hình | Không tách được ảnh hưởng phần cứng | Dùng cùng runner class và metadata |
| Dùng JMH để đại diện cho API end-to-end | Bỏ qua network, queue, DB và serialization | Bổ sung load test gần production |
| Dùng load test để đo một method rất nhỏ | Nhiễu hệ thống che mất thay đổi nhỏ | Dùng JMH cho microbenchmark |
| Cập nhật baseline tự động từ mọi build | Hồi quy dần trở thành baseline mới | Chỉ cập nhật sau review và chấp nhận |
| Chọn threshold thấp hơn noise floor | CI thường xuyên báo sai | Đo biến động trước và chọn tolerance thực tế |
| Retry benchmark đến khi pass | Che giấu kết quả xấu và làm sai lịch sử | Lưu mọi lần chạy, phân loại lỗi môi trường rõ ràng |
| Chỉ nhìn throughput mà bỏ error rate | Hệ thống có thể bỏ request để đạt tốc độ | Đo throughput thành công cùng lỗi/timeout |
| Bật profiling nặng trong mọi lần đo | Công cụ quan sát làm thay đổi kết quả | Tách run đo chuẩn và run điều tra |

## 19. Quy trình áp dụng cho dự án Java 21

1. Chọn workload quan trọng và xác định metric gắn với trải nghiệm hoặc SLA.
2. Dùng JMH cho các operation nhỏ và load test cho hành vi service đầu cuối.
3. Xây dựng baseline có metadata về commit, JDK, phần cứng, flags và dữ liệu.
4. Chạy candidate và baseline trên runner cùng loại với cấu hình tương đương.
5. Thu nhiều mẫu, tổng hợp kết quả và xét cả sai số lẫn regression tolerance.
6. Áp dụng pass/warning/fail; không biến kết quả nhiễu thành kết luận chắc chắn.
7. Khi có regression, dùng JFR, GC log và application metrics để tìm nguyên nhân.
8. Chỉ cập nhật baseline sau khi kết quả được review và phiên bản mới được chấp nhận.
9. Chạy load/soak test định kỳ để kiểm tra hành vi dài hạn và điểm bão hòa.

Với Java 21, JMH là lựa chọn phù hợp cho microbenchmark JVM; JFR và unified logging hỗ trợ điều tra runtime; load test phản ánh hiệu năng đầu cuối. Một performance gate đáng tin cậy cần kết hợp SLO, baseline, workload đại diện, môi trường ổn định và cách xử lý độ không chắc chắn. Mục tiêu là phát hiện hồi quy có ý nghĩa mà không chặn phát triển vì nhiễu đo lường.

## Tài liệu tham khảo

- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)
- [JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples)
- [Oracle Java SE 21 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle Java SE 21 — Unified Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework)
- [Oracle Java SE 21 API — Management and Monitoring](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/module-summary.html)
