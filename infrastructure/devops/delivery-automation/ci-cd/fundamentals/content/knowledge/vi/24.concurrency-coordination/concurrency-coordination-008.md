# Giới hạn mức song song theo tài nguyên và dịch vụ phụ thuộc

## 1. Vì sao pipeline cần giới hạn mức song song?

CI/CD thường tăng tốc bằng cách chạy nhiều job cùng lúc: build nhiều module, kiểm thử trên nhiều phiên bản runtime, quét bảo mật, đóng gói nhiều image hoặc triển khai nhiều service. Song song hóa giúp giảm thời gian chờ, nhưng mỗi job đều tiêu thụ tài nguyên và có thể gọi tới những dịch vụ dùng chung như database, package registry, container registry, cloud API, test environment hoặc hệ thống quản lý bí mật.

Nếu số job đồng thời vượt quá năng lực của runner hoặc dependency, pipeline có thể chậm hơn thay vì nhanh hơn. Runner thiếu CPU/memory làm build kéo dài; nhiều job cùng tải dependency khiến registry bị throttling; hàng trăm integration test cùng tạo dữ liệu làm database quá tải; nhiều deployment cùng cập nhật một môi trường gây xung đột hoặc ghi đè trạng thái.

Giới hạn concurrency (mức thực thi đồng thời) là cách kiểm soát số tác vụ được phép chạy tại cùng thời điểm. Giới hạn cần dựa trên năng lực tài nguyên và khả năng chịu tải của dịch vụ phụ thuộc, đồng thời cân bằng giữa tốc độ, độ ổn định, tính công bằng và chi phí.

Mục tiêu không phải chạy ít job nhất. Mục tiêu là giữ mức song song đủ cao để sử dụng hiệu quả tài nguyên mà không đẩy runner hoặc dependency vào trạng thái quá tải.

## 2. Phân biệt các lớp concurrency

Một pipeline có thể có nhiều lớp chạy đồng thời. Nếu chỉ đặt một giới hạn ở cấp workflow, các job con hoặc pipeline khác vẫn có thể cùng tiêu thụ tài nguyên.

| Lớp | Phạm vi | Ví dụ |
|---|---|---|
| Organization/global | Toàn tổ chức hoặc nhóm runner | Tối đa 80 job CI đang chạy |
| Project/repository | Một dự án hoặc repository | Tối đa 12 pipeline trong repository |
| Pipeline/workflow | Các stage/job thuộc một lần chạy | Build và lint chạy song song |
| Job/step | Một job hoặc nhóm thao tác | Tối đa 4 test worker trong một job |
| Matrix/fan-out | Các biến thể được tạo từ một job | Test trên 5 JDK × 3 OS |
| Resource/dependency | Một tài nguyên hoặc dịch vụ dùng chung | Tối đa 6 integration test cùng dùng database |
| Environment/deployment | Một môi trường triển khai | Chỉ một release ghi vào production tại một thời điểm |

Các giới hạn này cần phối hợp. Ví dụ, giới hạn 20 job ở cấp repository không bảo đảm database test an toàn nếu mỗi job chạy 10 test worker. Concurrency thực tế tới database có thể lên tới 200.

## 3. Tính concurrency thực tế từ fan-out

Khi một pipeline tạo nhiều nhánh công việc, số tác vụ cuối cùng có thể lớn hơn nhiều so với số pipeline.

Ví dụ:

- 8 pipeline đang chạy.
- Mỗi pipeline có 3 job test song song.
- Mỗi job test khởi chạy 4 worker.

Số worker test đồng thời tối đa theo cấu hình có thể là:

\[
8 \times 3 \times 4 = 96
\]

Nếu mỗi worker mở 3 kết nối database, tải kết nối lý thuyết có thể đạt 288 kết nối, chưa tính ứng dụng test, migration job và các dịch vụ khác.

Khi tính mức song song, cần xét cả fan-out ở workflow, matrix, job, test framework và process con. Một giới hạn chỉ áp dụng cho số job runner có thể bỏ sót mức đồng thời thực tế bên trong job.

## 4. Xác định giới hạn từ năng lực runner

Runner có giới hạn CPU, memory, disk I/O, network bandwidth và số process/file descriptor. Số job phù hợp phụ thuộc mức tiêu thụ của từng loại workload.

| Tài nguyên | Dấu hiệu quá tải | Tác động lên pipeline |
|---|---|---|
| CPU | CPU liên tục cao, run queue dài, steal time tăng | Compile/test chậm, timeout |
| Memory | RAM gần đầy, swap hoặc OOM kill | Build bị kill, cache bị thu hồi, test chập chờn |
| Disk I/O | I/O wait cao, queue disk dài | Checkout, extract dependency và đóng gói chậm |
| Disk capacity | Workspace/cache đầy | Job lỗi khi ghi file hoặc upload artifact |
| Network | Băng thông bão hòa, packet loss | Tải dependency/image và gọi API chậm |
| Process/file descriptors | Đạt giới hạn hệ điều hành | Không tạo được process/socket/file |

Không nên dùng số CPU làm giới hạn duy nhất. Một job compile có thể chủ yếu tiêu thụ CPU; một job integration test có thể ít CPU nhưng giữ nhiều kết nối database; một job container build có thể tiêu thụ memory và disk I/O lớn.

## 5. Ước lượng số job đồng thời theo CPU và memory

Một ước lượng ban đầu có thể dùng tài nguyên khả dụng chia cho mức tiêu thụ trung bình hoặc mức tiêu thụ bảo thủ của một job:

\[
C_{cpu} = \left\lfloor \frac{CPU_{usable}}{CPU_{per\ job}} \right\rfloor
\]

\[
C_{memory} = \left\lfloor \frac{Memory_{usable}}{Memory_{per\ job}} \right\rfloor
\]

Giới hạn runner ban đầu nên không vượt quá tài nguyên chặt nhất:

\[
C_{runner} \leq \min(C_{cpu}, C_{memory}, C_{io}, C_{network})
\]

Ví dụ, runner có 16 vCPU và 32 GiB RAM. Sau khi dành tài nguyên cho OS, agent và daemon, còn khoảng 13 vCPU và 26 GiB. Nếu một build job cần khoảng 3 vCPU và 5 GiB RAM ở tải cao, ước lượng theo CPU là 4 job, theo memory là 5 job. CPU là giới hạn chặt hơn, nên có thể bắt đầu với 3 job để giữ headroom rồi đo thực tế.

Đây chỉ là điểm khởi đầu. Mức tiêu thụ thay đổi theo cache hit, kích thước project, test parallelism và tải nền. Hãy đo p50/p95 CPU, memory, I/O và thời gian chạy dưới tải thực trước khi nâng giới hạn.

## 6. Dành headroom cho hệ thống và biến động tải

Không nên phân bổ 100% tài nguyên lý thuyết cho job. Runner cần headroom cho OS, agent, container runtime, logging, antivirus/security agent và các đột biến ngắn.

Các nguyên tắc:

- Dành phần CPU/memory cố định cho hệ điều hành và agent.
- Không lập kế hoạch dựa duy nhất vào mức tiêu thụ trung bình nếu job có đỉnh cao lớn.
- Theo dõi OOM, swap, I/O wait và thời gian xếp hàng.
- Tách workload nặng như image build, browser test hoặc load test sang pool phù hợp.
- Giới hạn disk workspace và dọn dữ liệu tạm theo vòng đời job.
- Giữ một phần capacity cho job ưu tiên hoặc xử lý sự cố nếu tổ chức cần.

Nếu runner là máy dùng chung với developer hoặc dịch vụ khác, phải tính cả tải ngoài CI. Nếu runner ephemeral được tạo theo nhu cầu, giới hạn còn phụ thuộc quota cloud, tốc độ cấp máy, image startup và chi phí.

## 7. Giới hạn theo dịch vụ phụ thuộc

Runner khỏe không có nghĩa dependency chịu được mọi mức song song. Nhiều job có thể cùng gọi một dịch vụ có quota hoặc capacity thấp hơn runner.

| Dependency | Giới hạn cần xem xét | Hậu quả khi vượt |
|---|---|---|
| Package registry | Request rate, download bandwidth, số kết nối | HTTP 429, timeout, tải dependency chậm |
| Container registry | Pull/push quota, concurrent upload, storage | Throttling, lỗi push/pull |
| Database test | Connection limit, CPU, IOPS, lock contention | Connection refused, query chậm, test flaky |
| Cloud API | Request quota theo account/region/resource | Rate limit, API error |
| Secret manager | Request rate, token issuance quota | Job không lấy được credential |
| Kubernetes API | API Priority and Fairness, request rate, admission webhook | Apply chậm hoặc bị throttling |
| Shared test environment | Một trạng thái dùng chung, dữ liệu hoặc port | Test ghi đè dữ liệu, kết quả không xác định |
| External sandbox | Quota đối tác, số tài khoản thử nghiệm | Request bị từ chối hoặc khóa tài khoản |

Giới hạn dependency cần được quản lý riêng với giới hạn runner. Ví dụ, có thể cho phép 20 build job cùng chạy nhưng chỉ 5 job được truy cập database integration cùng lúc.

## 8. Tính mức song song theo quota dịch vụ

Với dependency có quota theo request mỗi giây, cần ước lượng tổng tốc độ request từ tất cả job.

Nếu mỗi job trung bình tạo R_job request/giây và dependency cho phép R_limit, mức song song lý thuyết tối đa là:

\[
C_{dependency} \leq \left\lfloor \frac{R_{limit}}{R_{job}} \right\rfloor
\]

Ví dụ, sandbox đối tác cho phép 40 request/giây. Một integration test worker tạo trung bình 5 request/giây khi hoạt động. Giới hạn lý thuyết là 8 worker. Nếu có traffic khác, burst limit hoặc retry, cần đặt thấp hơn, chẳng hạn 5 hoặc 6 worker rồi đo.

Quota có thể được áp dụng theo token, project, account, IP, region hoặc endpoint. Phải xác định đúng phạm vi quota. Nếu 3 repository dùng cùng một cloud account, giới hạn mỗi repository riêng lẻ có thể cộng lại vượt quota toàn account.

## 9. Dùng semaphore hoặc concurrency group cho tài nguyên dùng chung

Semaphore là cơ chế giới hạn số tác vụ được phép vào một vùng tài nguyên cùng lúc. Một semaphore có giá trị 1 tương đương khóa độc quyền; giá trị lớn hơn 1 cho phép một số lượng tác vụ đồng thời xác định.

Ví dụ, nhiều pipeline có thể build song song nhưng chỉ 3 job được chạy integration test trên database dùng chung:

~~~text
semaphore: shared-integration-db
capacity: 3

job:
  acquire: shared-integration-db
  run: integration-tests
  release: shared-integration-db
~~~

Đây là pseudocode mô tả ý tưởng. Hệ thống thực tế có thể dùng resource group, concurrency group, distributed lock, queue hoặc plugin điều phối. Cần bảo đảm khóa được giải phóng khi job cancel, runner chết hoặc timeout; lock có lease/TTL và cơ chế chống một job cũ tiếp tục ghi sau khi lease hết hạn.

Không nên dùng một khóa toàn cục cho mọi job nếu chỉ một dependency nhỏ cần giới hạn. Hãy khóa đúng tài nguyên và đặt capacity theo năng lực của nó để tránh giảm concurrency không cần thiết.

## 10. Khóa độc quyền cho môi trường triển khai

Một môi trường dùng chung có thể không hỗ trợ nhiều deployment cùng lúc. Ví dụ, hai pipeline cùng cập nhật staging, migration chạy đồng thời hoặc một job cleanup xóa tài nguyên của job khác.

Trong các trường hợp đó, dùng concurrency group hoặc environment lock:

- Chỉ một deployment thay đổi một môi trường tại một thời điểm.
- Xác định chính sách khi có release mới đến trong lúc release cũ đang chạy.
- Có thể hủy job cũ, xếp hàng hoặc từ chối job mới tùy loại môi trường.
- Lock cần bao phủ toàn bộ thao tác có xung đột, gồm deploy, migration, smoke test và cleanup nếu chúng dùng chung trạng thái.
- Sau khi giữ lock, xác minh release/commit vẫn là phiên bản được phép triển khai.

Ví dụ: production thường cần tuần tự hóa thao tác thay đổi workload và migration. Trong khi đó, các job kiểm tra read-only có thể chạy đồng thời nếu không ảnh hưởng tài nguyên hoặc dữ liệu dùng chung.

## 11. Queue và backpressure

Khi số job đến nhiều hơn số job có thể chạy, hệ thống cần một hàng đợi. Queue hấp thụ burst và giúp giới hạn concurrency, nhưng hàng đợi không thể tự giải quyết tình trạng thiếu capacity kéo dài.

Backpressure (điều tiết ngược) là cơ chế làm chậm hoặc hạn chế bên tạo tải khi phía nhận không còn khả năng xử lý an toàn. Trong CI/CD, backpressure có thể gồm:

- Giới hạn số pipeline được tạo hoặc đưa vào chạy.
- Giới hạn số job đang chờ cấp runner.
- Giảm matrix fan-out khi registry hoặc test environment bận.
- Tạm dừng job không ưu tiên khi dependency vượt ngưỡng.
- Trả trạng thái retryable khi quota bị throttling.
- Dùng queue có giới hạn và chính sách từ chối/expire rõ ràng.

Một queue không giới hạn có thể biến burst ngắn thành thời gian chờ rất dài, chiếm quota và khiến kết quả CI đã lỗi thời khi được chạy. Cần theo dõi queue depth, tuổi job cũ nhất, thời gian chờ và tỷ lệ job bị hủy do không còn cần thiết.

## 12. Fairness và ưu tiên giữa các pipeline

Nếu chỉ dùng một queue FIFO, job dài có thể chặn job ngắn; nếu luôn ưu tiên job mới, job cũ có thể bị starvation. Nếu một repository tạo nhiều job, nó có thể chiếm toàn bộ runner và làm dự án khác phải chờ.

Các cơ chế thường dùng:

| Cơ chế | Cách hoạt động | Khi phù hợp |
|---|---|---|
| FIFO | Job vào trước chạy trước | Hệ thống đơn giản, tải ổn định |
| Per-project quota | Mỗi dự án có giới hạn riêng | Tránh một dự án chiếm toàn bộ capacity |
| Weighted fair queue | Chia capacity theo trọng số | Nhóm có mức ưu tiên hoặc nhu cầu khác nhau |
| Priority class | Job quan trọng được ưu tiên | Hotfix, security patch, release production |
| Aging | Tăng ưu tiên theo thời gian chờ | Hạn chế starvation |
| Separate pools | Tách runner theo loại workload | Browser test, build image, trusted release |

Ưu tiên cần được định nghĩa rõ. Không nên để mọi job gắn nhãn urgent vì khi đó ưu tiên không còn ý nghĩa. Cũng cần giữ quota tối thiểu cho job thông thường để job ưu tiên không làm tắc toàn bộ luồng phát triển.

## 13. Matrix build và fan-out có kiểm soát

Matrix giúp kiểm thử nhiều tổ hợp runtime, hệ điều hành, database hoặc cấu hình. Tuy nhiên, một matrix lớn có thể tạo hàng chục hoặc hàng trăm job trong một lần chạy.

Ví dụ:

~~~yaml
strategy:
  matrix:
    java: [17, 21]
    os: [linux, windows, macos]
    database: [postgres, mysql]
  max-parallel: 4
~~~

Matrix này có 2 × 3 × 2 = 12 biến thể. max-parallel: 4 giới hạn số biến thể chạy đồng thời trong phạm vi matrix job theo semantics của nền tảng. Nó không giới hạn các pipeline khác hoặc worker con được khởi chạy bên trong từng job.

Các cách kiểm soát fan-out:

- Đặt max-parallel hoặc giới hạn tương đương.
- Chạy bộ test nhanh trên mọi commit, full matrix theo lịch hoặc trước release.
- Dùng matrix include/exclude để bỏ tổ hợp không có giá trị.
- Chạy smoke test trên một số tổ hợp đại diện trước khi mở rộng.
- Chia test theo shard nhưng đặt giới hạn tổng worker.
- Dừng các biến thể còn lại khi phát hiện lỗi chặn sớm nếu policy cho phép.

Không giảm ma trận tùy tiện đến mức bỏ sót nền tảng được hỗ trợ. Hãy dùng dữ liệu lỗi thực tế, mức độ phổ biến và rủi ro tương thích để chọn tổ hợp bắt buộc.

## 14. Điều phối song song giữa build và test

Không phải mọi bước đều cần chạy tuần tự. Các job độc lập có thể chạy song song, trong khi job phụ thuộc cần chờ kết quả đầu vào.

Ví dụ:

~~~mermaid
flowchart TD
    A[Checkout revision] --> B[Compile / build]
    B --> C[Unit tests]
    B --> D[Static analysis]
    B --> E[Dependency scan]
    C --> F[Quality gate]
    D --> F
    E --> F
    F --> G[Package and publish]
    G --> H[Integration test]
    G --> I[Image scan]
    H --> J[Release candidate gate]
    I --> J
~~~

Song song hóa các kiểm tra độc lập có thể giảm thời gian tổng. Nhưng nếu tất cả job cùng tải dependency, khởi động database hoặc gọi scanner vào một thời điểm, hệ thống phụ thuộc có thể bị burst. Có thể thêm cache, mirror, semaphore hoặc staggered start để phân tán tải.

Hãy phân biệt concurrency trong DAG với concurrency trên hạ tầng. Một DAG cho phép 10 job chạy song song không có nghĩa runner hoặc dependency đủ sức chạy cả 10.

## 15. Giới hạn kết nối và contention ở database

Integration test thường là nguồn gây quá tải database vì mỗi test worker có thể tạo pool kết nối riêng, transaction và dữ liệu dùng chung.

Khi thiết kế giới hạn:

- Ước lượng số connection mỗi process và tổng connection từ mọi job.
- Dành connection cho ứng dụng, migration, monitoring và quản trị.
- Dùng database/schema riêng cho job nếu khả thi.
- Giới hạn worker trong test framework.
- Tránh chạy migration đồng thời trên cùng schema.
- Dọn dữ liệu test theo namespace hoặc transaction rollback phù hợp.
- Theo dõi lock wait, deadlock, query latency, connection pool và IOPS.
- Đặt timeout để test không giữ lock vô hạn.

Ví dụ, database có giới hạn 200 connection. Nếu dành 80 cho ứng dụng và dịch vụ nền, 20 cho quản trị/monitoring và dự phòng 30, phần còn lại tối đa khoảng 70 connection cho CI. Nếu mỗi test worker giữ 5 connection, giới hạn lý thuyết là 14 worker; nên bắt đầu thấp hơn để dành headroom cho burst và connection phụ.

Không nên chỉ tăng max_connections để xử lý quá tải. Tăng giới hạn có thể làm database tiêu thụ thêm memory và khiến query contention nặng hơn. Hãy xác định bottleneck CPU, I/O, lock hay connection trước khi thay đổi.

## 16. Giới hạn request tới API và registry

Các dịch vụ bên ngoài thường trả 429 Too Many Requests, quota exceeded hoặc header cho biết thời gian chờ. Pipeline cần xử lý theo giao thức thay vì retry ngay lập tức.

Thực hành:

- Đọc và tôn trọng Retry-After nếu API cung cấp.
- Dùng exponential backoff có jitter để tránh mọi job retry cùng thời điểm.
- Giới hạn số lần retry và tổng thời gian chờ.
- Không retry lỗi xác thực hoặc request không idempotent như lỗi tạm thời.
- Cache dependency và dùng registry mirror nếu phù hợp.
- Giới hạn concurrency toàn cục tới quota account, không chỉ từng repository.
- Tách request read-only và write/publish nếu quota khác nhau.

Retry có thể làm tăng tải khi dịch vụ đang quá tải. Nếu 100 job cùng nhận 429 rồi retry sau đúng 1 giây, chúng có thể tạo một burst mới. Jitter phân tán thời điểm retry; semaphore/backpressure giảm số request được phát ra ngay từ đầu.

## 17. Timeout, cancellation và retry phối hợp với concurrency

Concurrency control cần đi cùng timeout và cancellation. Một job bị treo lâu vẫn giữ slot, connection hoặc lock và làm các job khác chờ.

Mỗi lớp nên có timeout phù hợp:

- Job timeout: giới hạn tổng thời gian thực thi.
- Step timeout: giới hạn một thao tác như download hoặc deploy.
- Network timeout: giới hạn kết nối và response.
- Lock wait timeout: không chờ vô hạn để lấy semaphore.
- Test timeout: phát hiện test treo hoặc deadlock.
- Shutdown grace period: cho process dọn dẹp trước khi bị dừng.

Khi hủy job, cần dừng process con và giải phóng tài nguyên. Không chỉ đánh dấu job canceled trong UI trong khi process trên runner vẫn tiếp tục chạy và gọi dependency.

Retry cần có giới hạn và phân biệt lỗi transient với lỗi deterministic. Build thất bại do compile error không nên retry; request bị throttling có thể retry với backoff; deploy timeout cần kiểm tra trạng thái thực tế trước khi gửi lại vì thao tác đầu tiên có thể đã áp dụng một phần.

## 18. Tránh retry storm và thundering herd

Retry storm xảy ra khi nhiều job cùng retry một dependency đang lỗi, làm tải tăng và khiến dịch vụ khó phục hồi. Thundering herd là nhiều client cùng thức dậy hoặc gọi một tài nguyên tại cùng thời điểm.

Biện pháp:

- Exponential backoff với full jitter hoặc equal jitter theo thư viện phù hợp.
- Giới hạn retry count và deadline tổng.
- Dùng circuit breaker để tạm ngừng gọi dependency khi lỗi liên tục.
- Đưa request vào queue thay vì giữ hàng loạt job chờ.
- Giảm concurrency khi tỷ lệ lỗi hoặc throttling tăng.
- Stagger lịch chạy nightly/full matrix.
- Cache kết quả hoặc artifact dùng chung khi tính đúng đắn cho phép.

Circuit breaker không thay thế retry policy. Nó ngăn gọi dependency liên tục khi đã có bằng chứng dịch vụ đang lỗi; sau thời gian cooldown, một số request thử có kiểm soát được dùng để xác định dependency đã phục hồi chưa.

## 19. Adaptive concurrency và điều chỉnh theo tín hiệu

Giới hạn cố định dễ vận hành nhưng có thể không tận dụng hết capacity vào giờ thấp điểm hoặc không đủ bảo vệ khi tải thay đổi. Adaptive concurrency điều chỉnh mức song song theo tín hiệu quan sát.

Các tín hiệu có thể dùng:

- CPU/memory và queue depth của runner pool.
- Job wait time và execution time.
- HTTP 429/5xx, timeout và latency của dependency.
- Database connection usage, lock wait và query latency.
- Registry throughput và error rate.
- Cloud quota hoặc capacity signal.

Một chính sách đơn giản:

1. Bắt đầu với concurrency bảo thủ đã đo.
2. Tăng từng bước nhỏ khi latency/error ổn định và còn headroom.
3. Giảm nhanh khi throttling, timeout hoặc saturation vượt ngưỡng.
4. Giữ thời gian ổn định trước lần điều chỉnh tiếp theo để tránh dao động.
5. Đặt min/max và giới hạn tốc độ thay đổi.

Không nên để từng repository tự điều chỉnh độc lập nếu tất cả dùng chung một quota. Bộ điều phối cần nhìn được tải toàn cục hoặc có quota phân bổ theo nhóm. Với hệ thống nhỏ, giới hạn tĩnh thường dễ dự đoán hơn và có thể đủ tốt.

## 20. Ước lượng queue và thời gian chờ

Khi job đến nhanh hơn tốc độ hoàn tất, queue depth tăng. Định luật Little thường được dùng để liên hệ số lượng công việc trung bình, throughput và thời gian ở trong hệ thống:

\[
L = \lambda W
\]

Trong đó:

- L: số job trung bình trong hệ thống (đang chạy và/hoặc chờ, tùy ranh giới đo).
- λ: throughput trung bình, số job hoàn tất hoặc đến mỗi đơn vị thời gian trong hệ ổn định.
- W: thời gian trung bình một job ở trong hệ thống.

Ví dụ, hệ thống hoàn tất trung bình 30 job mỗi giờ và có trung bình 15 job trong hệ thống, thời gian trung bình từ lúc vào đến lúc ra khoảng 0,5 giờ theo mô hình ổn định.

Đây là quan hệ trung bình, không dự báo chính xác p95 queue wait khi workload có thời gian chạy khác nhau hoặc tải đến theo burst. Hãy đo riêng queue wait, execution time, throughput và job age. Nếu queue tăng liên tục, chỉ tăng concurrency không phải lúc nào cũng giải quyết được: bottleneck có thể nằm ở dependency hoặc một loại job dài.

## 21. Tách pool theo loại workload

Một pool runner chung có thể bị workload nặng chiếm hết. Tách pool giúp giới hạn đúng loại tài nguyên và tránh ảnh hưởng chéo.

Ví dụ:

| Pool | Workload | Cách giới hạn |
|---|---|---|
| General CI | Lint, unit test, build nhỏ | Nhiều job, giới hạn CPU/memory vừa phải |
| Large build | Build monorepo, container image lớn | Ít job hơn, disk/memory cao |
| Browser test | E2E browser, nhiều browser process | Giới hạn theo RAM và số browser |
| Integration | Test dùng database/broker chung | Semaphore theo dependency |
| Release/deploy | Publish artifact và production deployment | Quyền riêng, environment lock |
| Untrusted PR | Mã từ fork hoặc contributor chưa tin cậy | Runner ephemeral, network/secret hạn chế |

Pool riêng giúp kiểm soát tài nguyên nhưng có thể tạo capacity nhàn rỗi ở pool này và queue ở pool khác. Nếu nền tảng hỗ trợ, có thể dùng quota động hoặc pool có thể mở rộng, nhưng vẫn giữ giới hạn toàn cục cho dependency dùng chung.

## 22. Ví dụ cấu hình concurrency theo nhiều lớp

Một pipeline khái niệm có thể đặt giới hạn ở workflow, matrix và tài nguyên dùng chung:

~~~yaml
workflow:
  maxConcurrentRuns: 6

jobs:
  unit-tests:
    matrix:
      java: [17, 21]
    maxParallel: 3

  integration-tests:
    resourceGroup: shared-test-database
    maxConcurrent: 2
    timeout: 30m

  deploy-staging:
    resourceGroup: staging-environment
    maxConcurrent: 1

  deploy-production:
    resourceGroup: production-environment
    maxConcurrent: 1
    approvalRequired: true
~~~

Đây là pseudocode tổng quát, không phải cú pháp trực tiếp của GitHub Actions, GitLab CI, Jenkins hay một engine cụ thể. Trong hệ thống thực, cần ánh xạ từng giới hạn vào concurrency group, resource group, lock, runner pool hoặc plugin phù hợp.

Điều cần đạt:

- Không quá 6 workflow run đồng thời trong phạm vi được quản lý.
- Matrix test chỉ fan-out tối đa 3 biến thể cùng lúc.
- Database integration chỉ có 2 job cùng truy cập.
- Staging và production chỉ có một deployment ghi môi trường tại một thời điểm.
- Quyền production chỉ cấp cho job đã qua gate và approval theo policy.

## 23. Quan sát và điều chỉnh concurrency

Không thể chọn giới hạn tốt nếu không đo. Nên theo dõi cả tài nguyên, queue và kết quả chất lượng.

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Active jobs | Có bao nhiêu job đang chạy theo pool/project? |
| Queue depth/age | Có bao nhiêu job chờ và job cũ nhất chờ bao lâu? |
| Queue wait p50/p95 | Người phát triển phải chờ runner bao lâu? |
| Job duration p50/p95 | Job có chậm đi khi concurrency tăng không? |
| Runner CPU/memory/I/O | Pool còn headroom hay đang saturation? |
| Dependency latency | Database/registry/API có chậm theo mức song song không? |
| 429/timeout/error rate | Có bị throttling hoặc lỗi do quá tải không? |
| Retry count | Retry có đang khuếch đại tải không? |
| Cancellation rate | Job bị hủy do commit mới hoặc timeout bao nhiêu? |
| Cost per successful pipeline | Tăng concurrency có cải thiện hiệu quả hay chỉ tăng chi phí? |

Thay đổi giới hạn theo từng bước và so sánh trước/sau trên workload tương đương. Nếu execution time giảm nhưng queue wait, lỗi dependency hoặc chi phí tăng mạnh, cần đánh giá tổng thể thay vì chỉ nhìn thời gian job.

## 24. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Không giới hạn matrix/fan-out | Một commit tạo hàng trăm job | Đặt max parallel và chọn tổ hợp theo rủi ro |
| Chỉ giới hạn runner, bỏ qua dependency | Database/registry vẫn bị quá tải | Có semaphore/quota riêng theo dependency |
| Mỗi repository đặt quota độc lập | Tổng tải vượt quota dùng chung | Phân bổ quota toàn cục hoặc theo nhóm |
| Dùng khóa toàn cục cho mọi job | Giảm throughput không cần thiết | Khóa đúng resource và capacity cần bảo vệ |
| Queue không giới hạn | Job cũ chờ quá lâu và chiếm tài nguyên quản lý | Queue bound, expiry, cancellation và backpressure |
| Retry ngay khi gặp 429/timeout | Retry storm và thundering herd | Backoff, jitter, retry budget và concurrency giảm |
| Không timeout job/lock | Slot bị giữ vô hạn | Timeout và cleanup khi cancel |
| Tăng max connection để che DB bottleneck | Tăng memory/contention và làm DB mất ổn định | Đo CPU, I/O, lock và pool usage |
| Chỉ dùng average utilization | Bỏ qua đỉnh tải và p95 | Dùng percentile, headroom và burst test |
| Ưu tiên mọi job là urgent | Job thường bị starvation | Priority policy, aging và quota tối thiểu |
| Chia runner pool quá cứng | Pool nhàn rỗi trong khi pool khác bị queue | Quota linh hoạt có giới hạn toàn cục |

## 25. Checklist thiết kế giới hạn song song

Trước khi tăng concurrency hoặc mở rộng matrix, hãy xác minh:

- [ ] Đã tính fan-out ở pipeline, matrix, job và worker/process con.
- [ ] Đã đo CPU, memory, disk I/O, network và process limit của runner.
- [ ] Có headroom cho OS, agent, daemon và biến động tải.
- [ ] Đã xác định dependency dùng chung và quota theo đúng phạm vi account/project/region.
- [ ] Có giới hạn riêng cho database, registry, API, secret manager và test environment khi cần.
- [ ] Job dùng tài nguyên độc quyền có semaphore, lock hoặc resource group.
- [ ] Lock có timeout/lease và được giải phóng khi cancel hoặc runner chết.
- [ ] Queue có giới hạn, chính sách fairness/priority và backpressure.
- [ ] Matrix có max parallel và tổ hợp test được chọn theo rủi ro.
- [ ] Retry có backoff/jitter, giới hạn số lần và phân biệt lỗi transient.
- [ ] Job, step, network và lock wait có timeout phù hợp.
- [ ] Cancellation dừng process con và giải phóng tài nguyên.
- [ ] Có metric queue, execution, runner, dependency, retry và chi phí.
- [ ] Thay đổi concurrency được đo và điều chỉnh từng bước.
- [ ] Production deployment được tuần tự hóa và kiểm soát quyền phù hợp.

## 26. Nguyên tắc thực hành cốt lõi

1. Tính mức song song ở mọi lớp, bao gồm pipeline, matrix, job và worker con.
2. Đặt giới hạn runner theo CPU, memory, I/O, network và headroom thực tế.
3. Đặt quota riêng cho dependency; runner còn capacity không có nghĩa database hoặc API còn capacity.
4. Dùng semaphore/resource group cho database, môi trường và tài nguyên dùng chung.
5. Điều tiết queue bằng backpressure, fairness, priority và giới hạn thời gian chờ.
6. Giới hạn matrix/fan-out theo giá trị kiểm thử và rủi ro cần bao phủ.
7. Kết hợp timeout, cancellation, retry budget, exponential backoff và jitter.
8. Tránh retry storm bằng circuit breaker hoặc giảm concurrency khi dependency suy giảm.
9. Tách runner pool theo loại workload và trust boundary khi cần.
10. Đo queue wait, execution time, saturation, throttling, lỗi và chi phí trước khi điều chỉnh giới hạn.

Giới hạn mức song song là một quyết định điều phối tài nguyên trên toàn bộ chuỗi CI/CD. Khi runner, dependency, queue và môi trường có giới hạn phù hợp, pipeline có thể tận dụng concurrency để rút ngắn feedback mà vẫn giữ được độ ổn định và khả năng dự đoán. Hãy bắt đầu từ số liệu thực tế, đặt headroom và điều chỉnh từng bước thay vì tăng số job đồng thời chỉ để làm pipeline trông nhanh hơn.
