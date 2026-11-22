# 2.8 Kiểm chứng một thay đổi dưới cùng tải và ghi rõ giới hạn của kết luận

## Mục tiêu học tập

Khi sửa một truy vấn, đổi cấu hình GC, tăng connection pool hay tối ưu một đoạn Java, câu hỏi quan trọng không chỉ là **“sau thay đổi hệ thống có nhanh hơn không?”** mà là: **“Dưới cùng một tải và những điều kiện so sánh được, thay đổi này có cải thiện đúng hiện tượng cần xử lý, có gây hồi quy khác và bằng chứng cho phép kết luận đến đâu?”**

Sau bài học, bạn sẽ có thể:

- Xây dựng phép so sánh **trước (baseline/A)** và **sau (candidate/B)** cho một thay đổi cụ thể, với tiêu chí đo, điều kiện tải và quy tắc PASS/FAIL định nghĩa từ trước.
- Xác định yếu tố nào phải giữ ổn định, yếu tố nào được phép khác và cách phát hiện những khác biệt khiến phép so sánh mất giá trị.
- Đọc đồng thời **tải phát ra**, **tải thực đến**, **thông lượng hoàn thành**, **độ trễ**, **lỗi** và **chi phí tài nguyên** khi đánh giá hiệu quả.
- Kiểm chứng **cơ chế giả thuyết** bằng logs, metrics, traces, JFR/GC/thread evidence khi cần, thay vì suy ra nguyên nhân chỉ từ một số đo.
- Viết một kết luận có phạm vi, độ tin cậy, hạn chế và đề xuất tiếp theo rõ ràng; phân biệt cải thiện quan sát được với bằng chứng nhân quả và xác minh trên production.

## 1. “Dưới cùng tải” nghĩa là gì?

**Kiểm chứng thay đổi** là so sánh hành vi hệ thống tại hai trạng thái, trong đó ta cố gắng chỉ thay đổi đúng yếu tố cần kiểm tra. Trong ứng dụng Java, yếu tố đó có thể là:

- Mã nguồn hoặc thuật toán: giảm allocation, sửa vòng lặp, loại bỏ khóa thừa, thay truy vấn.
- Cấu hình runtime: heap size, GC, thread pool, connection pool, retry, timeout, cache.
- Hệ thống phụ thuộc: index database, API downstream, cách kết nối hoặc giới hạn tài nguyên.
- Cấu trúc triển khai: số instance, CPU/memory limit, container image hoặc phiên bản JDK.

**Cùng tải** không chỉ là hai lần chạy đều hiển thị “100 RPS” hoặc “100 virtual users”. Cần xác định *công việc được đưa vào hệ thống* có tương đương về đặc tính và lịch phát sinh hay không:

| Yếu tố | Điều cần so khớp hoặc ghi rõ |
| --- | --- |
| Tốc độ gửi | Arrival rate theo thời gian, ramp-up, spike, think time, open/closed workload |
| Mức đồng thời | Số request in-flight, client workers, giới hạn concurrency và queue |
| Cơ cấu thao tác | Tỷ trọng endpoint/operation, tỉ lệ đọc/ghi, nhánh cache hit/miss |
| Đầu vào | Payload size, phân phối khóa, số record, seed, dataset/snapshot ban đầu |
| Thời gian | Warm-up, thời lượng đo, thời điểm thu mẫu, cách xử lý cold start |
| Hệ thống | Build, JDK, JVM flags, OS/container, CPU/memory, số replica, topology |
| Phụ thuộc | Trạng thái DB, pool, cache, network, external service, giới hạn rate |
| Công cụ đo | Phiên bản load generator, vị trí đo latency, profiler/logging/sampling |
| Kết quả tải | RPS **đã gửi**, **đã đến**, **đã hoàn thành**; timeout/error, backlog |

Một so sánh chỉ có giá trị khi các điều kiện **liên quan đến giả thuyết** đủ tương đương, hoặc khi sự khác biệt đã được ghi nhận và được tính tới trong cách diễn giải. Trong môi trường thật hiếm khi mọi yếu tố giống hệt nhau; điều quan trọng là biết khác biệt nào có thể làm sai kết luận.

**Lưu ý về “cùng môi trường”:** nếu đang kiểm tra chính thay đổi tăng CPU limit, tăng heap hay số instance, yếu tố đó *phải* khác theo thiết kế. Khi ấy giữ ổn định các yếu tố còn lại và mô tả phép so sánh là **hiệu quả của cả thay đổi tài nguyên** cùng chi phí tăng thêm. Không gọi đây là “cải thiện thuật toán” nếu chưa có bằng chứng về thuật toán.

## 2. Vì sao nhìn một phép đo trước và một phép đo sau thường không đủ?

Giả sử p95 latency giảm từ 400 ms xuống 290 ms sau khi sửa code. Mức giảm quan sát được là:

```text
reduction (%) = (before - after) / before × 100
              = (400 - 290) / 400 × 100 = 27.5%
```

**Quan sát:** p95 thấp hơn 110 ms, tương đương 27,5% so với mốc trước, *trong hai phép đo đó*. Chưa thể kết luận toàn bộ cải thiện do bản sửa vì còn các khả năng:

1. Bản sau vô tình chạy với **tải nhẹ hơn**, dù cùng cấu hình của bộ phát.
2. Cache, JIT hoặc connection pool đã **ấm hơn** sau các lần chạy trước.
3. Database xử lý nhanh hơn vào thời điểm B, hoặc một batch/cron cạnh tranh tài nguyên đã kết thúc.
4. Bản sau loại bỏ những request chậm khỏi histogram vì chúng **timeout**, làm p95 của response thành công trông tốt hơn.
5. Công cụ đo hoặc số instance/giới hạn CPU/JVM flags khác.
6. Tập mẫu quá nhỏ hoặc p95 thay đổi mạnh giữa các lần đo ngay cả khi không có thay đổi code.

Bởi vậy, một kết quả “B nhanh hơn A” là **mô tả số liệu**. Một nhận định “thay đổi X làm B nhanh hơn” cần **thiết kế đối chứng, lặp lại, loại trừ yếu tố gây nhiễu và bằng chứng về cơ chế**.

Trong kiểm chứng runtime, hãy ghi rõ ba tầng kết luận:

- **Quan sát được:** số liệu trước/sau thay đổi thế nào, ở thời gian và môi trường nào.
- **Có bằng chứng ủng hộ:** so sánh được dưới tải, lặp lại và các dấu hiệu runtime phù hợp giả thuyết.
- **Chưa xác nhận hoặc chỉ áp dụng có điều kiện:** những khác biệt môi trường, workload chưa thử, sai số mẫu hoặc khả năng giải thích thay thế.

## 3. Đặt giả thuyết và tiêu chí từ trước

Trước khi thử một thay đổi, viết giả thuyết có thể bị bác bỏ:

> “Trong workload `checkout-open-100rps-v1`, tối ưu câu truy vấn X sẽ giảm p95 latency của `POST /checkout` ít nhất 20%, trong khi error rate không tăng, throughput hoàn tất đạt mục tiêu và CPU trung vị không tăng quá 8 điểm phần trăm. Nếu giảm độ trễ nhưng tăng timeout hoặc không đạt tải, thay đổi chưa đạt cổng chấp nhận.”

Ví dụ trên là tiêu chí **minh họa**, không phải ngưỡng SLO mặc định cho mọi hệ thống.

Một giả thuyết tốt xác định đủ năm phần:

1. **Thay đổi duy nhất:** commit/config/feature flag nào khác so với baseline; nếu nhiều thay đổi bắt buộc đi chung, coi chúng là **một gói can thiệp** và không gán tác dụng riêng cho từng thành phần.
2. **Cơ chế dự đoán:** vì sao thay đổi giúp (ít allocation hơn, giảm thời gian chờ lock, query thực thi nhanh, giảm GC pause, ...).
3. **Tải và điều kiện:** operation mix, RPS/concurrency, trạng thái cache/data, số instance, JVM, giai đoạn đo.
4. **Metric chính và guardrails:** p95/p99, số lỗi, correctness, throughput, CPU, heap/GC, DB pressure, queue.
5. **Tiêu chí thất bại:** nếu cải thiện chưa đủ, xảy ra hồi quy, điều kiện so sánh không đạt hoặc evidence không đủ thì kết quả là FAIL hoặc INCONCLUSIVE.

Không nên lựa chọn metric chính hay ngưỡng **sau khi đã xem số liệu**, vì sẽ có xu hướng chọn chỉ số thuận lợi nhất để tuyên bố thành công. Đặt mục tiêu hiệu quả kỹ thuật theo SLO, mức chậm gây ảnh hưởng hoặc yêu cầu nghiệp vụ; đồng thời định nghĩa phạm vi sai số và các trade-off chấp nhận được.

### 3.1 Phân biệt mục tiêu và hàng rào kiểm soát

Ví dụ một bản sửa làm p95 giảm 25% nhưng tiêu thụ CPU tăng 80%, gây timeout ở database hoặc trả kết quả sai. Khi đó tốc độ tốt hơn **không** đồng nghĩa thay đổi có thể chấp nhận.

| Nhóm | Metric | Câu hỏi |
| --- | --- | --- |
| Mục tiêu chính | p95/p99 latency hoặc throughput đúng nghiệp vụ | Thay đổi có giải quyết vấn đề đặt ra không? |
| Correctness | Assertion, trạng thái DB, kết quả tính toán, lỗi nghiệp vụ | Có làm sai dữ liệu hoặc hành vi không? |
| Reliability | 5xx, timeout, retry, dropped request, crash | Có đánh đổi bằng lỗi không? |
| Khả năng chịu tải | Offered/received/completed RPS, queue, in-flight | Có thực sự xử lý cùng lượng việc không? |
| Chi phí | CPU, RSS/heap, GC pause, I/O, DB connections | Có đẩy nghẽn hoặc chi phí sang chỗ khác không? |
| Điều kiện | Workload mix, dataset, JDK, resource limit | Kết quả trước và sau có đủ so sánh không? |

Với một thay đổi về memory leak, metric chính có thể là **xu thế retained heap sau GC dưới cùng workload trong khoảng thời gian đủ dài**; dùng p95 làm metric chính sẽ không đo đúng giả thuyết. Với thay đổi deadlock, metric chính là **tác vụ hoàn tất/có hoặc không có chu trình chờ khóa** theo điều kiện kích hoạt. Không áp một bộ tiêu chí hiệu năng cho mọi loại sự cố.

## 4. Thiết kế thử nghiệm A/B có kiểm soát

### 4.1 Khóa hồ sơ thử nghiệm (run manifest)

Lập một bản mô tả bất biến trước khi chạy:

```yaml
experiment_id: checkout-query-v2
hypothesis: "query optimization reduces p95 without error regression"
version_A: "image-digest-A"
version_B: "image-digest-B"
jdk: "17 (record actual vendor and patch version)"
jvm_flags: "record exact startup flags"
environment: "staging-cluster-profile-1"
instance_count: 3
cpu_memory_limits: "record exact requested/limit values"
workload_id: "checkout-open-100rps-mix-v1"
model: "open (scheduled arrivals)"
offered_rate: "100 req/s"
operation_mix: "70% read, 30% checkout"
dataset_snapshot: "synthetic-dataset-v7"
warmup: "3 min"
measurement_window: "10 min"
repetitions_per_variant: 3
metric_source: "client metrics + server metrics + traces"
primary_metric: "client-side p95 end-to-end latency"
guardrails: "errors, achieved throughput, CPU, correctness"
stop_condition: "abort on agreed resource/error/safety threshold"
```

Đây là **mẫu minh họa**, không phải tệp cấu hình bắt buộc của JDK hoặc benchmark. Giá trị “jdk: 17” chưa thay thế cho việc ghi đúng bản patch/vendor thực tế. Một hệ thống kiểm chứng tốt lưu thêm command của load generator, sampling, bộ dữ liệu/seed, thời gian UTC, phiên bản profiler, trạng thái cache và link tới artifact của mỗi run.

Với test liên quan JIT, class loading, GC hoặc cache, cần ghi rõ liệu **warm-up nằm ngoài cửa sổ đo** và các lần chạy có reset JVM/cache hay không. Nếu lỗi chỉ xảy ra ở cold start hoặc sau thời gian tích lũy dài, **không** được bỏ giai đoạn gây lỗi đi chỉ để số liệu đẹp hơn.

### 4.2 Chọn cách so sánh phù hợp

**Chạy nối tiếp A rồi B trên cùng môi trường:** dễ thực hiện và ít cần thêm tài nguyên, nhưng dễ bị ảnh hưởng bởi khác biệt theo thời gian (cache, mạng, batch, tải hệ thống). Chạy A nhiều lần rồi B nhiều lần có thể khiến thời gian là yếu tố gây nhiễu.

**Đan xen A–B–A–B hoặc B–A–B–A** khi có thể reset điều kiện: giúp nhận ra drift theo thời gian. Cần khởi tạo lại dataset/cache đúng quy tắc, tránh trạng thái từ một run lan sang run sau; nếu không reset được, phải ghi hạn chế.

**Hai nhóm chạy song song:** giảm biến thiên do thời gian, nhưng phải kiểm tra tính tương đương của node, network, data và load routing. Nếu A và B cùng dùng một DB bão hòa, chúng có thể **can thiệp lẫn nhau**, nên song song không tự động là đối chứng tốt.

**Canary/A-B production:** phản ánh tải thực hơn, nhưng hai nhóm phải được chia traffic tương đồng và có guardrails/rollback. Khác biệt tenant, loại request, vị trí máy, cache, phiên bản dependency có thể làm lệch kết luận. Không tổ chức thí nghiệm tác động người dùng chỉ để có số benchmark nếu chưa có quy trình vận hành phù hợp.

Không có một thứ tự chạy “chuẩn” áp dụng mọi trường hợp. Chọn thiết kế theo khả năng reset, độ nhạy thời gian, trạng thái dữ liệu và rủi ro vận hành; ghi rõ lý do chọn.

### 4.3 Lặp lại và theo dõi biến thiên

Một lần A và một lần B chỉ cho hai điểm đo. Nên có **nhiều run độc lập** ở điều kiện tương đương, lưu từng run thay vì chỉ lưu một trung bình. Ba run là một ví dụ dễ học, **không phải chuẩn đủ mẫu thống kê**.

Với metric có phân phối lệch như p99 latency, số lượng mẫu, thời lượng và độ độc lập của mẫu rất quan trọng. Các request trong cùng run thường có tương quan do GC, burst, dependency hoặc queue; không được coi từng request là một phép đo hoàn toàn độc lập để tạo độ tin cậy giả.

Ghi kết quả từng run (A1/A2/A3, B1/B2/B3), cả thành công lẫn thất bại. Có thể dùng median giữa các run để mô tả mức điển hình của **run-level p95**; hãy nêu đây là **median của p95 từng run**, không phải p95 gộp của toàn bộ request. Muốn tính percentile gộp phải có phân phối/quan sát hoặc histogram tương thích và phương pháp ghép hợp lệ; **không lấy trung bình các p95/p99 rồi gọi là p95/p99 tổng**.

## 5. Kiểm tra tải thực tế trước khi nhìn biểu đồ kết quả

Một bản sửa chỉ được xem là “nhanh hơn dưới cùng tải” khi workload **được thực thi đúng như thiết kế** ở cả hai phiên bản.

### 5.1 Offered load, achieved load, completed load

- **Offered load:** lịch và lượng request mà bộ phát *dự định* gửi, ví dụ 100 request mới mỗi giây.
- **Sent/received:** request được phát và đến hệ thống thực tế; cần quan sát lỗi của load generator, proxy và kết nối.
- **Completed throughput:** request đã hoàn tất mỗi giây, thành công hay thất bại cần phân biệt rõ.
- **In-flight/queue/backlog:** lượng công việc còn đang xử lý/chờ tại thời điểm đo; nếu tăng liên tục, hệ thống chưa ở trạng thái ổn định.

Ví dụ:

| Chỉ số | Trước A | Sau B |
| --- | ---: | ---: |
| Offered RPS | 100 | 100 |
| Received RPS | 99 | 98 |
| Completed RPS | 98 | 97 |
| p95 latency | 400 ms | 290 ms |
| Timeout rate | 0,3% | 0,3% |

Các số liệu **chỉ mang tính minh họa**. Nếu cả hai nhận/hoàn tất gần mức tải mục tiêu, không có backlog tăng mãi và request mix/data tương đương, phép so sánh có cơ sở tốt hơn.

Ngược lại, nếu B chỉ xử lý 55 RPS vì bộ phát bị nghẽn hoặc client dừng gửi khi server chậm, p95 của B không thể được gọi là cải thiện “ở cùng 100 RPS” chỉ vì cả hai được cấu hình 100 RPS.

### 5.2 Open workload và closed workload

**Open model:** request đến theo lịch tốc độ cố định độc lập tương đối với thời gian hoàn tất trước đó. Thích hợp cho nhiều bài toán mô phỏng traffic ngoại sinh; phải đo độ chính xác của lịch gửi và queue khi server chậm.

**Closed model:** có số client/tác vụ đồng thời cố định; một client thường chờ phản hồi rồi mới gửi tiếp (có thể thêm think time). Khi hệ thống chậm, tổng throughput có thể giảm. Bằng nhau về số virtual users không đủ để khẳng định bằng nhau về RPS.

**Coordinated omission:** khi hệ thống chậm, công cụ đo kiểu closed hoặc tự giảm phát tải có thể bỏ qua các request lẽ ra đến trong khoảng nghẽn, khiến histogram latency đánh giá thấp trải nghiệm dưới traffic thực. Đọc kỹ mô hình phát tải và cách công cụ ghi các request bị trì hoãn/mất trước khi diễn giải p95/p99.

Trong cả hai mô hình, hãy tính lỗi và timeout đầy đủ. Một histogram chỉ chứa response thành công có thể giảm p99 khi số timeout tăng; đó không phải thành công.

### 5.3 Cùng load không đồng nghĩa chỉ số khác đều phải giống

Nếu chính thay đổi làm giảm CPU hoặc GC, CPU/GC **được mong đợi khác** và là kết quả cần đo. Điều cần giữ tương đương là yếu tố đầu vào/đối chứng như điều kiện CPU limit, tải gửi, dataset và JVM khác ngoài can thiệp. Với throughput test tìm **khả năng chịu tải tối đa**, có thể tăng offered load theo cùng quy trình ramp ở cả A và B để so đường cong capacity; khi đó không nên chỉ so một mốc RPS đơn lẻ.

## 6. Đọc kết quả với ngưỡng chấp nhận và hiệu ứng phụ

Một mẫu cổng kiểm chứng, chỉ áp dụng khi workload và điều kiện có thể so sánh:

```text
Precondition:
- A và B có cùng workload plan/dataset/build-context ngoài thay đổi X;
- load generator không nghẽn; received/completed đạt mức cho phép;
- warm-up và cửa sổ đo tương đương; không có backlog tăng vô hạn.

Primary:
- median của p95 theo từng run giảm ít nhất 20%
  (tính cả mức cải thiện tuyệt đối bằng ms).

Guardrails:
- error/timeout rate không tăng vượt ngưỡng đặt trước;
- correctness assertions PASS;
- throughput thực đạt mục tiêu;
- CPU, heap/GC, DB wait, queue không vi phạm ngân sách;
- không phát sinh lỗi mới ở workload khác trong phạm vi kiểm thử.

Outcome:
PASS nếu toàn bộ điều kiện định trước đạt.
FAIL nếu can thiệp không đạt hoặc có hồi quy.
INCONCLUSIVE nếu workload/điều kiện/quan sát không so sánh được.
```

Đừng sửa tiêu chí PASS giữa chừng chỉ vì bản B đạt số đẹp ở một metric. Nếu tăng CPU để giảm latency là đánh đổi có chủ đích, ghi chi phí tài nguyên và điều kiện có thể chấp nhận từ trước.

**Các số cần báo cùng nhau:**

- Giá trị trước/sau và **chênh lệch tuyệt đối**, ví dụ giảm 110 ms.
- **Chênh lệch tương đối** với baseline, ví dụ giảm 27,5%.
- Phân bố từng run hoặc khoảng biến thiên, số run và số request quan sát.
- Error/timeout, achieved throughput, tài nguyên và trạng thái queue.
- Định nghĩa metric: latency ở client hay server, percentile per-run hay pooled, request lỗi được xử lý thế nào.

Một mức tăng 10 ms có thể rất đáng kể với endpoint vốn chạy 20 ms, nhưng ít quan trọng với batch vài phút. “Có ý nghĩa thống kê” (nếu được ước lượng đúng) và “đáng triển khai” là hai câu hỏi khác nhau; SLO, correctness, chi phí và tác động nghiệp vụ quyết định giá trị thực tế.

## 7. Ví dụ Java 17+: kiểm tra một bộ kết quả trước/sau được ghi sẵn

Ví dụ dưới đây dùng các **bản ghi giả định** của ba run A và ba run B. Chương trình không tạo load, không đo JFR/GC, không giả vờ tạo benchmark thực. Mục tiêu là mô tả cách **kiểm tra metadata tải trước khi so sánh**, tính hiệu quả trên run-level p95 và áp guardrails với dữ liệu đã có. Trong công việc thật, dữ liệu này phải đến từ load generator, hệ thống metric và bằng chứng runtime.

Tạo tệp `ChangeVerificationDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.ToIntFunction;

public class ChangeVerificationDemo {
    record Plan(String workloadId, String datasetId,
                int targetRps, int durationSeconds, String jdk) { }

    // errorBp: 1 basis point = 0.01 percentage point;
    // 30 means 0.30% error rate.
    record Trial(String variant, Plan plan, int achievedRps,
                 int p95Ms, int errorBp, int cpuPct) { }

    static int median(List<Trial> runs, ToIntFunction<Trial> metric) {
        if (runs.isEmpty() || runs.size() % 2 == 0) {
            throw new IllegalArgumentException("use an odd run count");
        }
        int[] values = runs.stream()
                .mapToInt(metric)
                .sorted()
                .toArray();
        return values[values.length / 2];
    }

    static void validate(List<Trial> before, List<Trial> after) {
        if (before.size() != 3 || after.size() != 3) {
            throw new IllegalArgumentException("expected three runs each");
        }
        Plan expected = before.get(0).plan();
        List<Trial> all = new ArrayList<>(before);
        all.addAll(after);

        for (Trial run : all) {
            boolean samePlan = run.plan().equals(expected);
            boolean meetsLoad = run.achievedRps() * 100
                    >= expected.targetRps() * 95;
            if (!samePlan || !meetsLoad) {
                throw new IllegalArgumentException("not comparable");
            }
        }
    }

    public static void main(String[] args) {
        Plan plan = new Plan("checkout-open-100rps-mix-v1",
                "synthetic-dataset-v7", 100, 600, "17");

        List<Trial> a = List.of(
                new Trial("A", plan, 99, 390, 30, 56),
                new Trial("A", plan, 98, 400, 20, 57),
                new Trial("A", plan, 99, 420, 40, 58));

        List<Trial> b = List.of(
                new Trial("B", plan, 98, 280, 20, 61),
                new Trial("B", plan, 99, 290, 30, 62),
                new Trial("B", plan, 98, 300, 30, 63));

        validate(a, b);
        System.out.println("metadata=matched; achieved>=95 RPS");

        int p95a = median(a, Trial::p95Ms);
        int p95b = median(b, Trial::p95Ms);
        int errA = median(a, Trial::errorBp);
        int errB = median(b, Trial::errorBp);
        int cpuA = median(a, Trial::cpuPct);
        int cpuB = median(b, Trial::cpuPct);

        double reduction = 100.0 * (p95a - p95b) / p95a;
        System.out.printf(Locale.ROOT,
                "p95 median: %d -> %d ms (reduction=%.1f%%)%n",
                p95a, p95b, reduction);
        System.out.printf(Locale.ROOT,
                "error median: %.2f%% -> %.2f%%%n",
                errA / 100.0, errB / 100.0);
        System.out.printf(Locale.ROOT,
                "cpu median: %d%% -> %d%%%n", cpuA, cpuB);

        boolean pass = reduction >= 20.0
                && errB <= errA
                && cpuB <= cpuA + 8;
        System.out.println("gate=" + (pass ? "PASS" : "FAIL"));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ChangeVerificationDemo.java
java ChangeVerificationDemo
```

Stdout chính xác:

```text
metadata=matched; achieved>=95 RPS
p95 median: 400 -> 290 ms (reduction=27.5%)
error median: 0.30% -> 0.30%
cpu median: 57% -> 62%
gate=PASS
```

**Giải thích phép tính:**

- Có ba p95 theo run của A: 390, 400, 420 ms; median = 400 ms.
- Có ba p95 theo run của B: 280, 290, 300 ms; median = 290 ms.
- Mức giảm = `(400 - 290) / 400 × 100 = 27.5%`.
- Error median: 30 basis points = 0,30% ở cả A và B.
- CPU median tăng từ 57% lên 62%, tức **5 điểm phần trăm**, nằm trong ngân sách minh họa không quá 8 điểm phần trăm.
- Mọi run ghi cùng `Plan` và `achievedRps >= 95`, nên **metadata validation** của ví dụ qua cổng; các rule đặt trước dẫn tới PASS.

**Giới hạn của ví dụ:** `Plan.equals(...)` chỉ xác nhận *metadata khai báo giống nhau*. Nó không chứng minh các request thực đến cùng lịch, cùng query plan, cùng cache, cùng phiên bản driver/JVM patch hoặc máy phát tải không nghẽn; các điều đó cần đối chiếu artifact thật. `achievedRps >= 95` là một điều kiện đơn giản, **không** kiểm tra queue, sai lệch lịch arrival hay correctness. Median p95 của ba run không phải p95 gộp của mọi request. Tập dữ liệu nhỏ và được dựng sẵn **không** chứng minh thay đổi là nguyên nhân, cũng không cung cấp confidence interval.

Nếu thay `B` bằng số liệu mới, luôn đọc metadata/tải và định nghĩa metric trước khi chạy cổng số học. Chương trình minh họa giúp kiểm tra tính nhất quán của quyết định, **không thay thế chẩn đoán JVM và thiết kế benchmark**.

## 8. Kiểm chứng cơ chế: đo đúng điều thay đổi đáng lẽ tác động

Ngay cả khi B đạt ngưỡng p95, cần xem **dấu hiệu dẫn đến cải thiện có phù hợp với giả thuyết**:

| Thay đổi đang thử | Cơ chế dự đoán | Bằng chứng nên đối chiếu |
| --- | --- | --- |
| Giảm allocation Java | Ít byte cấp phát hơn trên mỗi request, giảm áp lực GC | Allocation profiling/JFR, allocation rate, GC events, CPU và latency |
| Giảm contention | Luồng chờ lock ít hơn, thời gian blocked/wait giảm | JFR lock events, thread dump nhiều thời điểm, throughput và p95 |
| Tối ưu query | Query latency/rows read/cost giảm | DB execution plan/metrics, trace span, pool wait, query correctness |
| Đổi connection pool | Ít request chờ connection hơn | Pool in-use/pending/wait time, DB connections, DB CPU/latency và timeout |
| Đổi GC/heap | Phân phối pause/throughput/footprint phù hợp mục tiêu | GC logs/JFR, heap after GC, CPU, RSS, p99 và OOM behavior |
| Thêm cache | Cache hit tăng, dependency call giảm | Hit/miss, stale data/correctness, memory footprint, cache warm/cold behavior |

Cần tránh một vòng suy luận: “B có p95 thấp hơn, nên GC đã tốt hơn; GC tốt hơn, nên B có p95 thấp hơn”. Chỉ kết luận về GC khi **thật sự đo GC** và evidence nhất quán với thời gian request bị ảnh hưởng.

**Cơ chế có thể là trade-off.** Tăng thread pool đôi khi giúp xử lý đồng thời nhiều request hơn, nhưng cũng có thể tăng context switching, áp lực DB hoặc tail latency. Việc tăng/giảm một metric không xác nhận toàn hệ thống tối ưu nếu không xem tài nguyên và các dependency liên quan.

Khi thay đổi là **bug fix về tính đúng đắn**, điều kiện quan trọng nhất là test tái hiện lỗi và regression tests PASS. Chạy performance benchmark chỉ hữu ích nếu bản sửa có rủi ro hiệu năng hoặc tác động dưới tải; không dùng một p95 đẹp để biện hộ cho kết quả nghiệp vụ sai.

## 9. Xử lý biến thiên và độ tin cậy của kết luận

Dữ liệu runtime thường nhiễu. Một số nguồn biến thiên điển hình:

- JIT compilation/deoptimization, class loading, cache, GC, CPU scheduling, container throttling.
- Network jitter, database plan/cache, index/update, queue, downstream workload và batch jobs.
- Sai khác giữa các máy/instance, load generator quá tải, clock/metric sampling và instrumentation overhead.
- Workload mix, payload distribution, dữ liệu nóng/lạnh, retries và request timeout.

Để giảm nhầm lẫn:

1. **Lặp lại theo thiết kế**, lưu toàn bộ từng run và điều kiện. Không vứt run xấu chỉ vì không hợp giả thuyết; nếu loại bỏ run do lỗi công cụ, ghi lý do trước hoặc độc lập với kết quả mong muốn.
2. **Dùng baseline đối chứng** gần thời điểm đo và, nếu phù hợp, đan xen thứ tự chạy. Kiểm tra việc revert B về A có đưa hành vi quay gần baseline không; đây có thể là bằng chứng mạnh thêm về tác động nhưng cũng bị ảnh hưởng bởi trạng thái/tải.
3. **Xem phân phối**, không chỉ mean. Đối với tail latency, cần đủ request ở cửa sổ đo và lưu p95/p99 cùng error/timeout; các mẫu cực đoan quan trọng với người dùng.
4. **Phân biệt đơn vị mẫu**. Request trong một run có thể tương quan; các run thực sự độc lập có giá trị khác với hàng triệu request cùng một đợt nghẽn.
5. **Ước lượng bất định khi cần**. Có thể tính khoảng tin cậy cho chênh lệch run-level với phương pháp phù hợp hoặc bootstrap trên các đơn vị độc lập; không tự tuyên bố “95% chắc chắn” từ một phép đo hoặc từ ba run giả định.
6. **Đánh giá tính thực tiễn**. Chênh lệch nhỏ hơn dao động baseline hoặc không có tác động SLO/người dùng có thể chưa đủ để triển khai, kể cả khi tìm được một p-value nhỏ trong tập dữ liệu lớn.

Nếu dữ liệu mâu thuẫn, ví dụ p95 cải thiện ở một mức tải nhưng xấu đi ở mức cao, hãy báo **đường cong theo tải** và kết luận có điều kiện. Đừng ép các trường hợp trái chiều vào một nhãn “nhanh hơn 20%”.

### 9.1 Các trạng thái kết luận nên phân biệt

- **PASS (theo cổng định trước):** điều kiện so sánh thỏa và mọi metric/guardrail của phạm vi đã đo đạt ngưỡng. Không đồng nghĩa chứng minh hiệu quả trong mọi tải/môi trường.
- **FAIL:** thay đổi không đạt mục tiêu, có hồi quy hoặc vi phạm guardrail trong điều kiện hợp lệ.
- **INCONCLUSIVE:** không đủ bằng chứng đáng tin để PASS/FAIL: tải không tương đương, mất dữ liệu, không đủ mẫu, run lỗi công cụ, biến gây nhiễu lớn.
- **NOT TESTED:** một workload/môi trường/tác động nằm ngoài kế hoạch, không được suy ra từ PASS của workload khác.

Các nhãn này thuộc **thí nghiệm đo**, không đồng nhất với trạng thái **sửa lỗi đã triển khai/đóng incident**.

## 10. Những giới hạn phải viết ra trong báo cáo

Một kết luận có trách nhiệm luôn đặt số liệu vào phạm vi thực tế. Các dạng giới hạn thường gặp:

### 10.1 Giới hạn về môi trường

- Benchmark chạy trên staging, chưa kiểm chứng traffic production và topology thực.
- JDK 17, heap 2 GiB, 2 CPU và ba replica là điều kiện của thí nghiệm; không mặc định kết quả giữ nguyên ở cấu hình khác.
- Database synthetic nhỏ hơn dữ liệu production, khác phân phối khóa/query plan/cache hoặc không có contention thật.

### 10.2 Giới hạn về workload

- Chỉ đo 100 RPS và mix 70:30, chưa kiểm chứng 300 RPS, spike, tải nền hoặc payload lớn.
- Chỉ đo steady state 10 phút sau warm-up; chưa đánh giá cold start, leak dài hạn, rollover và trạng thái sau giờ cao điểm.
- Chỉ đo hai endpoint; không kết luận các job batch, scheduled tasks hay API khác đều cải thiện.

### 10.3 Giới hạn về đo lường và thống kê

- Chỉ có ba run/phiên bản, độ biến thiên lớn; chưa đủ chứng minh cải thiện ổn định ở mức thống kê mong muốn.
- Chưa xác minh load generator phát đúng lịch hoặc chưa ghi đủ timeout; p99 có thể bị thiên lệch.
- Dùng median của p95 từng run, không phải p95 gộp, và không kèm khoảng tin cậy.
- Chưa đo CPU throttling, DB wait, GC hay ảnh hưởng lâu dài; các nguyên nhân khác vẫn có thể giải thích chênh lệch.

### 10.4 Giới hạn của suy luận nguyên nhân

- Nếu cùng lúc đổi code và cấu hình, phép thử chỉ cho biết hiệu ứng **gộp**; không thể tách tác động của từng thay đổi.
- Nếu A đo sáng, B đo chiều và dependency thay đổi, kết luận nhân quả bị giới hạn bởi time-of-day và external load.
- Nếu không có đối chứng độc lập hoặc không thử revert, có thể nói “phù hợp giả thuyết”, chưa nên nói “đã chứng minh nguyên nhân gốc”.
- Nếu sample chỉ là ba run thuận lợi được chọn từ nhiều run, kết luận dễ bị selection bias.

Giới hạn không làm báo cáo “yếu”; nó giúp người đọc biết phải áp dụng kết quả vào quyết định nào và cần thí nghiệm bổ sung ở đâu.

## 11. Ví dụ viết kết luận đúng mức bằng chứng

Giả sử nhóm đo ba lần A và ba lần B trong staging theo cùng plan khai báo, thu được median run-level p95 là 400 ms và 290 ms, error median bằng nhau ở 0,30%, CPU median tăng 5 điểm phần trăm và achieved throughput mỗi run >=95% của 100 RPS mục tiêu.

**Kết luận quá mạnh:**

> “Bản B đã được chứng minh nhanh hơn 27,5% trong production và loại bỏ hoàn toàn vấn đề hiệu năng.”

Câu này vượt quá bằng chứng vì phép đo staging không chứng minh production, không bao quát mọi workload và không nói rõ tính bất định.

**Kết luận phù hợp:**

> “Trong ba run/biến thể của workload synthetic 100 RPS trên môi trường staging đã khai báo, median của p95 theo run giảm từ 400 xuống 290 ms (giảm 110 ms, tương đương 27,5%). Error median giữ ở 0,30%; CPU median tăng từ 57% lên 62%; các run đạt ngưỡng achieved throughput tối thiểu. Bộ số liệu đáp ứng cổng chấp nhận minh họa của thử nghiệm. Giới hạn: ít run, chưa có khoảng tin cậy và chưa xác nhận trạng thái dependency/cache thực giống nhau hoặc hiệu quả ở traffic production; cần thêm đối chứng và theo dõi canary trước khi khẳng định hiệu quả triển khai rộng.”

Nếu đã có metric/JFR/trace chứng minh query X giảm thời gian xử lý đúng như giả thuyết, có thể bổ sung: “Các trace/DB metrics liên kết theo run ID ủng hộ việc giảm latency ở query X là cơ chế đóng góp chính”, kèm link bằng chứng. Không tự thêm một kết luận này nếu chưa thật sự đo.

## 12. Quy trình thực hành theo từng bước

1. **Định nghĩa thay đổi và giả thuyết.** Ghi commit/config diff, cơ chế dự đoán, metric chính, guardrails và tiêu chí PASS/FAIL/INCONCLUSIVE.
2. **Khóa hợp đồng so sánh.** Workload model, offered rate và lịch gửi, concurrency, operation mix, dataset, warm-up, thời lượng, JDK/JVM, resource, dependency và nguồn metric.
3. **Chuẩn hóa các run.** Lưu run ID, timestamp có múi giờ, build digest, command load generator, seed, metrics và nơi lưu artifact. Kiểm tra công cụ đo hoạt động trước khi đo.
4. **Chạy baseline và candidate nhiều lần.** Giữ điều kiện tương đương, có chiến lược giảm drift, không trộn warm-up với steady-state nếu đang kiểm tra steady-state.
5. **Kiểm tra tính hợp lệ của phép so sánh.** Đối chiếu offered/sent/received/completed RPS, in-flight/queue, lỗi load generator, mix, data, instance, dependency; nếu không hợp lệ, đánh dấu INCONCLUSIVE trước khi diễn giải cải thiện.
6. **Phân tích hiệu quả và guardrails.** Công bố từng run, chênh lệch tuyệt đối/tương đối, biến thiên, correctness, errors/timeouts, CPU/heap/GC, DB; không chỉ báo con số có lợi.
7. **Kiểm tra cơ chế và các cách giải thích khác.** Nối logs, metrics, traces, JFR hoặc GC/thread evidence theo cùng cửa sổ; thử lại khi cần, kiểm tra tác động phụ và trường hợp workload khác.
8. **Ra quyết định có điều kiện.** PASS/FAIL/INCONCLUSIVE theo tiêu chí đặt trước; ghi giới hạn, độ tin cậy, tài nguyên/chi phí, hướng hành động, owner và cổng canary/rollback nếu triển khai.
9. **Theo dõi sau thay đổi.** Với production, kiểm tra SLO, error/timeout, user impact, CPU/DB, load mix và thời gian dài hơn; lưu kết quả để đối chiếu với dự báo của thí nghiệm.

### Mẫu báo cáo so sánh

```text
CHANGE / HYPOTHESIS
- Experiment ID:
- Incident or performance problem:
- Change A -> B (commit/config/package/image):
- Expected mechanism:
- Primary metric and predeclared acceptance threshold:
- Correctness/reliability/cost guardrails:

COMPARABILITY
- Workload model, target and measured arrival/throughput:
- Operation mix, payload distribution, dataset snapshot:
- Warm-up, run duration, time zone and run order:
- JDK/JVM flags, CPU/memory, replicas, dependency state:
- Instrumentation/load generator versions:
- Deviations and sources of confounding:

RESULTS
- A runs (run IDs, values, artifacts):
- B runs (run IDs, values, artifacts):
- Absolute and relative change:
- Per-run spread / uncertainty:
- Errors, timeouts, throughput, queue, CPU/GC/DB:
- Mechanism evidence and alternative explanations:

DECISION
- PASS / FAIL / INCONCLUSIVE:
- Exact scope supported by evidence:
- Limits: environment, load, duration, sample, measurement:
- Untested cases and remaining risks:
- Next test or rollout/canary/rollback gate:
- Owner and date:
```

## 13. Lỗi thường gặp khi kiểm chứng thay đổi

- **“Cùng 100 virtual users” được gọi là “cùng 100 RPS”.** Mô hình closed không bảo đảm throughput giống nhau; phải đo arrival và completed RPS.
- **Benchmark chỉ chạy một lần.** Kết quả có thể phụ thuộc JIT, cache, GC hoặc tải dependency; cần lặp và ghi độ biến thiên.
- **Chỉ so p95 response 200.** Timeout/retry bị bỏ qua khiến cải thiện giả; phải báo lỗi và policy tính latency.
- **Warm-up khác nhau giữa A/B.** Một bản cache nóng, bản kia lạnh; so sánh sai đối tượng.
- **Không giữ dữ liệu đầu vào tương đương.** Dataset, khóa nóng, schema/index hoặc state thay đổi có thể chi phối metric.
- **Chạy nhiều thay đổi trong cùng một B rồi gán công cho một dòng code.** Chỉ có bằng chứng về gói thay đổi; muốn tách riêng cần thiết kế thử nghiệm khác.
- **Dùng trung bình của p99 và gọi đó là p99 toàn bộ request.** Percentile không cộng gộp theo cách đó.
- **Bỏ guardrails khi thấy p95 tốt.** CPU, heap, database, correctness hay error rate có thể hồi quy.
- **Không kiểm tra công cụ phát tải.** Generator nghẽn hoặc coordinated omission có thể làm B trông nhanh hơn.
- **Gọi tương quan là nhân quả.** Không xem mechanism, drift, canary split và yếu tố gây nhiễu.
- **Kết luận “fix production” từ staging.** Chỉ nên nói kết quả áp dụng trong workload/môi trường đã đo và nêu điều kiện xác minh rollout.
- **Không ghi điều chưa biết.** Người đọc dễ áp dụng một kết luận có điều kiện thành khẳng định tuyệt đối.

## 14. Tự kiểm tra kiến thức

1. Hai phiên bản đều có `targetRps=100`, nhưng A hoàn thành 99 RPS, B hoàn thành 60 RPS và B có p95 thấp hơn. Vì sao chưa thể gọi B nhanh hơn “ở cùng tải”?
2. B có p95 thấp hơn 30% nhưng timeout tăng từ 0,2% lên 5%. Kết quả có vượt cổng reliability nếu tiêu chí định trước là lỗi không tăng không?
3. Vì sao không thể lấy trung bình ba giá trị p99 theo run rồi gọi là p99 của toàn bộ request A hoặc B?
4. Nếu đổi JVM flags, `-Xmx` và code cùng lúc, kết luận nhân quả tối đa có thể nói về điều gì?
5. Bạn có ba run A/B ở staging và kết quả ổn định; những giới hạn nào phải nêu trước khi quyết định production rollout?
6. Một thay đổi giảm median p95 nhưng làm CPU tăng 20 điểm phần trăm, trong khi ngân sách định trước chỉ cho phép tăng 8. Trạng thái PASS/FAIL/INCONCLUSIVE nên là gì khi dữ liệu hoàn chỉnh và workload tương đương?
7. Làm sao sử dụng trace, GC log hoặc JFR để tăng bằng chứng cho **cơ chế** của thay đổi, thay vì chỉ thấy “trước/sau khác nhau”?
8. Trong benchmark của dịch vụ có queue, vì sao phải quan sát backlog theo thời gian chứ không chỉ throughput và p95 tại một thời điểm?

**Ghi nhớ:** kiểm chứng một thay đổi yêu cầu **tải và điều kiện có thể so sánh**, **tiêu chí định trước**, **đủ số run/bằng chứng**, **đánh giá cả guardrails** và **một kết luận được giới hạn bởi những gì thực sự đã đo**. “B đạt cổng ở 100 RPS trên staging” là một kết luận hữu ích; từ đó không tự suy ra “B tốt hơn ở mọi tải và mọi production environment”.