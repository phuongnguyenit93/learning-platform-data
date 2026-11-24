# Lặp phép đo, ghi điều kiện và phân biệt sai số với thay đổi có ý nghĩa

## 1. Vì sao một lần đo không đủ?

Đo hiệu năng của Spring Boot trên JVM và GraalVM Native Image thường nhằm so sánh thời gian khởi động, mức dùng bộ nhớ, throughput hoặc latency. Những số liệu này dao động theo tải máy, trạng thái cache, JIT warm-up, garbage collection, scheduler của hệ điều hành, network và database. Vì vậy, một lần chạy nhanh hoặc chậm chưa đủ để kết luận bản build mới tốt hơn hay kém hơn.

Một phép đo có giá trị cần có ba phần: **lặp lại có kiểm soát**, **ghi đầy đủ điều kiện**, và **đánh giá độ lớn của khác biệt**. Phải phân biệt biến thiên tự nhiên giữa các lần chạy với thay đổi ổn định do code, cấu hình hoặc loại binary.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, các phép đo thường so sánh JVM và native executable. Hai loại runtime có đặc điểm khác nhau: JVM có JIT warm-up và heap/GC riêng; native executable thường không có JIT theo cách JVM HotSpot dùng. Vì vậy, cần xác định rõ giai đoạn đo, workload và môi trường để phép so sánh có ý nghĩa.

## 2. Xác định câu hỏi và metric trước khi chạy

Không bắt đầu bằng việc chạy benchmark rồi chọn số đẹp. Viết rõ câu hỏi cần trả lời, ví dụ:

- Native executable có giảm thời gian từ process start tới readiness không?
- Mức RSS sau 60 giây idle thay đổi bao nhiêu?
- Throughput khi xử lý cùng workload có giữ được không?
- p95/p99 latency có cải thiện trong tải đồng thời mục tiêu không?
- Thời gian build native có chấp nhận được so với lợi ích runtime không?

Chọn metric phù hợp với câu hỏi:

| Metric | Đơn vị | Cách hiểu |
|---|---:|---|
| Startup-to-ready | ms hoặc s | Từ lúc khởi chạy process đến khi ứng dụng sẵn sàng nhận traffic |
| RSS | MiB | Physical memory resident của process tại thời điểm đo |
| Heap used | MiB | Bộ nhớ heap đang dùng; cách đo khác RSS |
| Throughput | requests/s | Số request hoàn tất mỗi giây |
| Latency | ms | Thời gian xử lý request; nên báo p50/p95/p99 |
| CPU | % hoặc CPU-seconds | Mức sử dụng CPU trong workload |
| Error rate | % | Tỷ lệ request thất bại |
| Build duration | s hoặc min | Thời gian tạo executable native |

Đừng dùng một metric làm đại diện cho mọi khía cạnh. RSS thấp hơn không tự chứng minh throughput cao hơn; startup nhanh hơn không chứng minh latency dưới tải thấp hơn.

## 3. Định nghĩa chính xác điểm bắt đầu và kết thúc

Startup time cần một mốc bắt đầu và một điều kiện readiness có thể quan sát. Ví dụ:

- **Start**: thời điểm supervisor/process launcher bắt đầu tạo process.
- **Ready**: health/readiness endpoint trả trạng thái sẵn sàng và các dependency bắt buộc đã được kết nối.

Không dùng thời điểm log “Started Application” nếu ứng dụng còn phải warm up cache, chạy migration hoặc chờ dependency trước khi nhận traffic. Nếu mục tiêu là thời gian process tới socket listen, hãy ghi rõ đó là startup-to-listen chứ không phải startup-to-ready.

Latency request cũng cần định nghĩa điểm đo: client-side end-to-end hay server-side handler duration. Client-side bao gồm network, connection setup và serialization; server-side thường không bao gồm toàn bộ các thành phần đó.

## 4. Lặp lại phép đo có kế hoạch

Lặp lại giúp ước lượng biến thiên. Số lần lặp phụ thuộc độ nhiễu và chi phí benchmark; không có con số duy nhất đúng cho mọi workload.

Một quy trình khởi đầu thực tế:

1. Chạy một vài lần pilot để phát hiện lỗi setup và ước lượng độ biến thiên.
2. Chạy warm-up theo protocol đã định nghĩa nếu runtime/workload cần.
3. Thu ít nhất 10-20 lần đo độc lập cho metric ổn định khi chi phí cho phép.
4. Với benchmark rất nhiễu hoặc p99, cần nhiều mẫu hơn và thời gian chạy đủ dài.
5. Báo toàn bộ phân bố và số mẫu, không chỉ lấy lần nhanh nhất.

Với startup, mỗi lần đo nên là một process mới vì trạng thái khởi động thuộc vòng đời process. Với throughput/latency, mỗi sample nên là một cửa sổ đo có workload và thời lượng xác định; không coi từng request trong cùng một đợt tải là các lần chạy benchmark độc lập hoàn toàn.

Có thể dùng nhiều block chạy xen kẽ JVM và native để giảm ảnh hưởng nhiệt độ, tải nền hoặc thay đổi trạng thái máy theo thời gian.

## 5. Warm-up và cold start phải được phân biệt

JVM HotSpot cần thời gian để JIT compile và tối ưu code. Nếu đo JVM ngay sau khi process khởi động, kết quả có thể phản ánh interpreter/compilation phase. Nếu đo sau warm-up, kết quả phản ánh trạng thái steady-state hơn.

Native Image thường không có JIT warm-up tương đương, nhưng vẫn có thể chịu ảnh hưởng từ page cache, class/resource loading, connection pool, DNS, TLS session, database cache và application cache.

Do đó, thiết kế hai loại câu hỏi riêng:

- **Cold-start behavior**: đo process mới, cache ở trạng thái xác định, không bỏ qua startup work.
- **Steady-state behavior**: sau thời gian warm-up/workload ổn định, đo latency/throughput và resource usage.

Không warm-up JVM 5 phút nhưng đo native ngay sau startup rồi gọi đó là so sánh throughput công bằng. Cũng không bỏ qua cold-start nếu mục tiêu sản phẩm chính là scale-to-zero hoặc serverless.

## 6. Ghi điều kiện máy và môi trường

Mỗi lần benchmark cần lưu tối thiểu:

| Nhóm | Thông tin cần ghi |
|---|---|
| Hardware | CPU model, số core, RAM, kiến trúc |
| OS | Distribution/version, kernel, Windows/macOS version |
| Runtime | JDK vendor/version, GraalVM version, Native Image version |
| Build | Commit SHA, compiler flags, optimization, debug/strip settings |
| Application | Spring Boot version, profile, configuration, feature flags |
| Dependencies | Driver/library versions và resolved dependency graph |
| Container | Image digest, base image, CPU/memory limits, runtime user |
| Workload | Request mix, concurrency, duration, payload và dataset |
| External systems | Database version, topology, cache state, network path |
| Host state | Power mode, background load, CPU throttling, thermal state |

Ghi cả những yếu tố tưởng như phụ: container CPU quota, memory limit, JVM flags, GC, heap sizing, native memory settings và số replica. Nếu môi trường khác nhau, không nên gộp số đo thành một phép so sánh duy nhất mà không giải thích.

## 7. Kiểm soát biến gây nhiễu

Một benchmark tốt cố định hoặc ghi lại các biến có thể làm kết quả thay đổi:

- Chạy trên cùng máy hoặc cùng loại instance.
- Dùng cùng OS, kernel, architecture và container limits.
- Giữ cùng database dataset, index và cache policy.
- Dùng cùng request mix, payload và concurrency.
- Tắt workload nền không cần thiết hoặc ghi lại mức tải.
- Giữ cùng network path và vị trí client.
- Tránh chạy build native đồng thời với benchmark.
- Theo dõi CPU throttling, thermal throttling và memory pressure.
- Dùng cùng cấu hình logging/metrics/tracing.

Nếu phải chạy trên CI shared runner, lưu thông tin host và tải nền. Các kết quả CI nhiều nhiễu phù hợp phát hiện regression lớn; với khác biệt nhỏ, cần benchmark trên máy/runner được kiểm soát hơn.

## 8. Báo cáo phân bố, không chỉ trung bình

Latency thường lệch phải: phần lớn request nhanh, một số request chậm đáng kể. Mean có thể bị kéo lên bởi outlier; p50/p95/p99 giúp mô tả các phần khác nhau của phân bố.

Báo cáo nên gồm:

- Số lần chạy/số request và thời lượng mỗi run.
- Mean và standard deviation khi phân bố phù hợp.
- Median và interquartile range (IQR) để mô tả trung tâm/độ phân tán bền vững hơn.
- p50, p95, p99 cho latency.
- Min/max chỉ như thông tin phụ, không dùng min làm kết luận.
- Error rate và số mẫu bị loại cùng lý do.

Ví dụ bảng tổng hợp:

| Runtime | Runs | Startup median | Startup IQR | RSS median sau 60s |
|---|---:|---:|---:|---:|
| JVM | 15 | 1,850 ms | 120 ms | 310 MiB |
| Native | 15 | 420 ms | 35 ms | 105 MiB |

Các con số chỉ minh họa cách trình bày, không phải kết quả thực nghiệm của module. Trong báo cáo thật, kèm dữ liệu thô và điều kiện đo.

## 9. Độ biến thiên và sai số đo

Giả sử cùng một cấu hình chạy nhiều lần cho kết quả khác nhau. Phần chênh lệch có thể đến từ:

- Nhiễu hệ thống và scheduler.
- Cache nóng/lạnh.
- JIT/GC hoặc background compilation.
- Connection pool chưa ổn định.
- Network jitter và database load.
- Độ phân giải/overhead của công cụ đo.
- Thay đổi nhiệt độ và CPU frequency.

Standard deviation mô tả mức phân tán quanh mean khi phù hợp. IQR mô tả khoảng giữa Q1 và Q3, ít nhạy với outlier. Confidence interval mô tả độ bất định của ước lượng theo phương pháp và giả định đã chọn.

Không gọi mọi khác biệt nhỏ hơn một standard deviation là “không có ý nghĩa” theo quy tắc máy móc. Cần xem thiết kế mẫu, phân phối, cỡ mẫu và mức thay đổi tối thiểu có giá trị với sản phẩm.

## 10. Phân biệt ý nghĩa thống kê và ý nghĩa thực tế

Hai câu hỏi khác nhau:

- **Ý nghĩa thống kê**: dữ liệu có đủ bằng chứng cho thấy khác biệt không chỉ do biến thiên ngẫu nhiên theo mô hình phân tích đã chọn?
- **Ý nghĩa thực tế**: mức khác biệt có đủ lớn để ảnh hưởng tới SLA, chi phí, trải nghiệm hoặc quyết định kiến trúc không?

Với mẫu rất lớn, chênh lệch 1 ms có thể có ý nghĩa thống kê nhưng không quan trọng với SLA 500 ms. Ngược lại, với ít lần chạy, cải thiện 20% có thể đáng quan tâm nhưng cần thêm dữ liệu để ước lượng chắc chắn.

Trước benchmark, xác định **minimum practically important difference** (mức thay đổi tối thiểu có giá trị thực tế). Ví dụ nhóm đặt mục tiêu startup giảm ít nhất 200 ms hoặc RSS giảm ít nhất 50 MiB để đáng thay đổi pipeline; các ngưỡng này phải dựa vào nhu cầu hệ thống, không lấy từ ví dụ chung.

## 11. Tính phần trăm thay đổi đúng chiều

Với metric càng thấp càng tốt như startup hoặc latency:

`improvement(%) = (baseline - candidate) / baseline × 100`

Với metric càng cao càng tốt như throughput:

`improvement(%) = (candidate - baseline) / baseline × 100`

Ví dụ startup median giảm từ 1,800 ms xuống 450 ms:

`(1800 - 450) / 1800 × 100 = 75%`

Với RSS giảm từ 300 MiB xuống 120 MiB:

`(300 - 120) / 300 × 100 = 60%`

Luôn ghi đơn vị và baseline. Nếu baseline bằng 0 hoặc metric không có ý nghĩa theo tỷ lệ, không dùng công thức phần trăm máy móc.

## 12. Dùng confidence interval và so sánh cặp khi phù hợp

Khi so sánh JVM và native, có thể chạy các block trên cùng host và xen kẽ thứ tự để giảm drift. Nếu hai phép đo được ghép cặp theo block (ví dụ JVM run rồi native run trong cùng điều kiện), phân tích chênh lệch theo từng cặp thường hữu ích hơn so sánh hai tập không liên quan.

Với metric gần chuẩn và giả định phù hợp, confidence interval của mean có thể dùng để mô tả độ bất định. Với phân phối lệch hoặc outlier, cân nhắc median, bootstrap confidence interval hoặc phương pháp phi tham số. Không chọn kiểm định sau khi xem kết quả chỉ để đạt p-value mong muốn.

Báo rõ phương pháp, mức confidence, số mẫu và giả định. Với quyết định vận hành, hãy ưu tiên cả độ lớn hiệu ứng và khoảng bất định, không chỉ một con số p-value.

## 13. Outlier: không tự ý xóa lần đo xấu

Outlier có thể là lỗi đo thật, nhưng cũng có thể là biểu hiện của vấn đề sản phẩm: GC pause, throttling, connection retry hoặc tail latency. Không xóa mẫu chỉ vì nó làm kết quả xấu.

Quy trình xử lý:

1. Đánh dấu mẫu bất thường.
2. Kiểm tra log/metrics/host telemetry để tìm nguyên nhân.
3. Xác định tiêu chí loại mẫu trước hoặc theo quy tắc đã ghi.
4. Nếu là lỗi hạ tầng ngoài phạm vi benchmark, loại có lý do và báo số mẫu bị loại.
5. Nếu là hành vi ứng dụng có thể xảy ra production, giữ trong phân tích.
6. Báo kết quả có và không có mẫu bị loại nếu quyết định phụ thuộc vào nó.

Không trim top/bottom tùy ý mà không nêu phương pháp. Một tail latency xấu có thể chính là điều benchmark cần phát hiện.

## 14. Đo startup, memory và throughput theo protocol riêng

**Startup**: mỗi lần chạy process mới, dùng readiness probe, ghi thời gian process start và ready, cố định dependency readiness và migration policy. Báo median/IQR cùng số lần chạy.

**Memory**: chọn RSS, heap hoặc native memory rõ ràng; lấy mẫu tại các mốc như sau startup, sau 60 giây idle và sau workload. Không so sánh JVM heap used với native RSS như cùng một metric.

**Throughput/latency**: dùng load generator riêng, warm-up theo protocol, giữ concurrency/request mix, chạy đủ lâu để ổn định và báo p50/p95/p99 cùng error rate. Đảm bảo load generator không trở thành bottleneck.

## 15. Ví dụ protocol benchmark có thể tái lập

Một protocol so sánh JVM và Native Image có thể ghi:

```text
Question: Compare startup-to-ready and steady-state HTTP latency
Host: Linux x86_64, 8 vCPU, 16 GiB RAM
Container: same CPU quota and memory limit
Database: same test dataset and endpoint
Application: same commit, Spring profile and request behavior
JVM: recorded JDK, heap and GC flags
Native: recorded GraalVM and Native Image build arguments

Startup:
- 15 fresh process launches per runtime
- Same readiness endpoint
- Record process start and readiness timestamp

Steady state:
- 2-minute warm-up
- 10-minute measurement window
- Fixed request mix and concurrency
- 5 independent runs per runtime
- Report throughput, p50/p95/p99 and error rate

Memory:
- Record RSS at ready, 60 seconds idle and after load
- Record JVM heap separately where applicable
```

Protocol là ví dụ; điều chỉnh số lần chạy/thời lượng theo độ nhiễu và SLA. Lưu script, dataset, request fixtures và raw results cùng benchmark report để người khác có thể lặp lại.

## 16. Tránh benchmark không công bằng giữa JVM và native

Các lỗi thường gặp:

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Đo JVM ngay lúc start, native sau warm-up | Giai đoạn runtime khác nhau | Định nghĩa cold-start và steady-state riêng |
| Dùng heap JVM so với RSS native | Metric khác nhau | So RSS với RSS; báo heap riêng |
| Khác CPU/memory limit | Tài nguyên không tương đương | Dùng cùng quota/host class |
| Khác profile hoặc feature | Workload thực thi khác | Cùng commit/configuration/behavior |
| Chỉ chạy một lần | Không ước lượng biến thiên | Lặp độc lập và báo phân bố |
| Chỉ báo best run | Che giấu tail và noise | Báo median, spread, percentiles |
| Xóa outlier tùy ý | Thiên lệch kết quả | Quy tắc loại mẫu rõ ràng |
| Chỉ đo health endpoint | Không đại diện workload | Dùng request mix production-like |
| Load generator quá yếu | Throughput bị giới hạn bởi client | Kiểm tra CPU/network phía client |

## 17. Ghi nhận kết quả và so sánh qua thời gian

Mỗi report nên chứa:

- Câu hỏi benchmark và metric chính.
- Baseline/candidate commit và artifact digest.
- Protocol, script và dataset version.
- Host/container/runtime conditions.
- Raw samples, summary statistics và plots nếu có.
- Outlier/exclusion notes.
- Practical threshold và kết luận.
- Hạn chế và scenario chưa được đo.

Khi so sánh qua nhiều lần release, giữ benchmark harness ổn định. Nếu thay load generator, dataset hoặc readiness definition, đánh dấu đây là thay đổi protocol; không nối trực tiếp hai chuỗi số liệu như thể cùng phép đo.

Có thể chạy benchmark định kỳ để phát hiện drift, nhưng chỉ đưa regression gate cứng vào CI khi môi trường đủ ổn định và ngưỡng được hiệu chỉnh theo biến thiên nền. Nếu runner nhiều nhiễu, dùng kết quả làm tín hiệu điều tra thay vì fail build theo chênh lệch nhỏ.

## 18. Checklist trước khi kết luận

- Câu hỏi benchmark và metric được xác định trước.
- Điểm bắt đầu/kết thúc và warm-up được định nghĩa.
- Có đủ số lần chạy độc lập và cửa sổ đo phù hợp.
- JVM và native dùng cùng workload, dataset và giới hạn tài nguyên.
- Hardware, OS, toolchain, profile và dependency versions được ghi lại.
- Báo median/percentiles và độ phân tán, không chỉ best run.
- Outlier được điều tra và xử lý theo quy tắc có ghi nhận.
- Phân biệt statistical significance với practical significance.
- Có ngưỡng thay đổi tối thiểu có giá trị cho sản phẩm.
- Raw data, script, artifact digest và report được lưu.
- Kết luận chỉ áp dụng cho metric, workload và môi trường đã đo.

## 19. Câu hỏi tự kiểm tra

1. Vì sao một lần đo startup không đủ để so sánh JVM và Native Image?
2. Khác nhau giữa cold-start và steady-state benchmark là gì?
3. Vì sao phải định nghĩa rõ startup-to-ready?
4. Khi nào median/IQR phù hợp hơn chỉ báo mean?
5. Standard deviation và confidence interval mô tả điều gì?
6. Ý nghĩa thống kê khác ý nghĩa thực tế ra sao?
7. Vì sao không nên tự ý loại outlier?
8. Làm thế nào để so sánh RSS và heap một cách đúng đắn?
9. Những điều kiện môi trường nào cần ghi để benchmark có thể tái lập?
10. Khi nào nên dùng benchmark làm CI gate và khi nào chỉ dùng làm tín hiệu điều tra?

**Ghi nhớ:** một kết luận hiệu năng đáng tin cậy phải dựa trên phép đo lặp lại, protocol và điều kiện được ghi rõ, phân bố cùng độ bất định, và ngưỡng ý nghĩa thực tế. So sánh JVM với Native Image trên cùng workload, phân biệt cold-start với steady-state, rồi lưu dữ liệu thô để người khác có thể tái lập.
