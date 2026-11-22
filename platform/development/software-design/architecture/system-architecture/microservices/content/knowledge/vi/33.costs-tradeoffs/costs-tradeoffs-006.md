# Cân bằng đa dạng công nghệ với khả năng bảo trì trong Microservices

Microservices cho phép mỗi dịch vụ chọn công nghệ phù hợp với đặc tính công việc. Một dịch vụ xử lý dữ liệu thời gian thực có thể cần nền tảng khác với một dịch vụ phân tích batch; một workload cần latency thấp có thể có lựa chọn khác với một API CRUD thông thường. Sự linh hoạt này tạo ra **đa dạng công nghệ (technology diversity)** hoặc **polyglot architecture**.

Tuy nhiên, nếu mỗi team tự chọn ngôn ngữ, framework, database, message broker, build tool và cách triển khai mà không có giới hạn, tổ chức sẽ phải duy trì quá nhiều runtime, pipeline, thư viện, kỹ năng và quy trình vận hành. Chi phí không chỉ nằm ở giấy phép hay máy chủ mà còn ở thời gian tuyển dụng, onboarding, xử lý sự cố, vá bảo mật, nâng cấp và chuyển giao người phụ trách.

Bài toán kiến trúc là tìm điểm cân bằng: **cho phép khác biệt khi nó tạo ra giá trị đo được, đồng thời chuẩn hóa những phần không cần khác biệt**. Không nên ép mọi dịch vụ dùng một stack duy nhất nếu workload có nhu cầu đặc biệt; cũng không nên coi quyền tự do công nghệ là lý do để tạo thêm một nền tảng phải bảo trì.

Bài học thuộc nhóm **Chi phí và đánh đổi** trong kiến trúc hệ thống Microservices.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích polyglot architecture và lý do Microservices thường có nhiều công nghệ.
- Phân biệt đa dạng có chủ đích với technology sprawl.
- Đánh giá trade-off giữa hiệu năng, năng suất, khả năng tuyển dụng, vận hành, bảo mật và chi phí vòng đời.
- Chọn một bộ công nghệ mặc định được hỗ trợ và quy trình phê duyệt ngoại lệ.
- Dùng tiêu chí kỹ thuật và nghiệp vụ để quyết định có nên thêm một ngôn ngữ, framework hoặc datastore.
- Hiểu ảnh hưởng của nhiều runtime lên CI/CD, observability, on-call, dependency management và disaster recovery.
- Thiết kế paved road, service template, platform capability và guardrail để giảm chi phí lặp lại.
- Quản lý vòng đời công nghệ: lựa chọn, áp dụng, nâng cấp, deprecate và loại bỏ.
- Lập kế hoạch giảm đa dạng không còn giá trị mà không tạo big-bang migration.
- Đo lợi ích và chi phí bằng dữ liệu thay vì chỉ dựa trên sở thích của team.

## 2. Đa dạng công nghệ trong Microservices là gì?

**Technology diversity** là việc hệ thống sử dụng nhiều lựa chọn kỹ thuật khác nhau cho các phần khác nhau. Phạm vi có thể bao gồm:

- Ngôn ngữ: Java, Kotlin, Go, C#, Python, TypeScript, Rust.
- Runtime: JVM, .NET, Node.js, CPython hoặc runtime chuyên dụng.
- Framework: Spring Boot, ASP.NET Core, FastAPI, NestJS.
- Database: PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, columnar warehouse.
- Messaging: Kafka, RabbitMQ, cloud queues, streaming platforms.
- Giao thức: REST/JSON, gRPC/Protobuf, event schemas.
- Build/dependency: Maven, Gradle, npm, Poetry, Go modules.
- Deployment: container, serverless, managed runtimes, Kubernetes.
- Observability/security tooling: agent, SDK, scanner và cách cấu hình khác nhau.

**Polyglot architecture** là cách chọn nhiều ngôn ngữ hoặc công nghệ trong cùng hệ thống để đáp ứng nhu cầu khác nhau. Ví dụ, một service Java xử lý nghiệp vụ giao dịch, một worker Python chạy mô hình machine learning và một gateway Go xử lý kết nối nhẹ.

Đa dạng không đồng nghĩa với việc mỗi service phải khác nhau. Một tổ chức có thể dùng Java cho phần lớn backend, PostgreSQL làm transactional store và Kafka cho event streaming, nhưng vẫn dùng Python ở một subsystem có nhu cầu khoa học dữ liệu rõ ràng.

### 2.1. Ba dạng đa dạng thường gặp

| Dạng | Ví dụ | Lợi ích tiềm năng | Chi phí cần quản lý |
|---|---|---|---|
| Đa dạng theo workload | Python cho ML, Java cho transaction | Dùng công cụ phù hợp công việc | Nhiều runtime và kỹ năng |
| Đa dạng theo domain | Một số domain dùng document store, domain khác dùng relational DB | Mô hình dữ liệu sát nhu cầu | Backup, consistency và vận hành khác nhau |
| Đa dạng do lịch sử | Service cũ dùng framework cũ, service mới dùng framework mới | Tránh rewrite ngay lập tức | Nhiều phiên bản, dependency và kiến thức legacy |

Dạng đầu có thể là lựa chọn có chủ đích. Dạng thứ hai có thể phù hợp khi mô hình dữ liệu khác biệt thực sự. Dạng thứ ba thường cần kế hoạch quản lý vòng đời, vì công nghệ tồn tại do lịch sử không nhất thiết còn tạo giá trị.

## 3. Vì sao Microservices dễ dẫn đến đa dạng công nghệ?

Microservices tách trách nhiệm thành nhiều service có vòng đời tương đối độc lập. Mỗi team có thể lựa chọn:

- Ngôn ngữ phù hợp kỹ năng và bài toán.
- Framework phù hợp giao thức và yêu cầu vận hành.
- Database phù hợp access pattern.
- Cách scale phù hợp CPU, memory hoặc I/O.
- Thư viện và công cụ phù hợp domain.

Sự tự chủ có thể cải thiện tốc độ quyết định. Nhưng mỗi lựa chọn thêm vào hệ sinh thái đều tạo một phần chi phí phải trả trong nhiều năm.

Ví dụ một service mới dùng ngôn ngữ X có thể nhanh hơn 15% trong một benchmark. Để đưa nó vào production, tổ chức còn phải có build image, dependency scanning, tracing, metrics, secrets, runtime patching, deployment, rollback, backup, on-call và người có khả năng xử lý sự cố. Nếu chỉ một service nhỏ sử dụng X, phần chi phí nền này có thể lớn hơn lợi ích hiệu năng.

**Quyết định công nghệ cần được đánh giá ở cấp toàn hệ thống và vòng đời**, không chỉ ở cấp source code của một service.

## 4. Technology diversity và technology sprawl

Đa dạng có chủ đích khác với đa dạng phát sinh không kiểm soát.

| Đa dạng có chủ đích | Technology sprawl |
|---|---|
| Có lý do gắn với workload/domain | Chọn theo sở thích hoặc xu hướng |
| Có owner và người hỗ trợ | Không rõ ai duy trì |
| Có template, pipeline và observability | Mỗi service tự cấu hình |
| Có version/support policy | Nhiều version không kiểm kê |
| Có phương án tuyển dụng và on-call | Chỉ một người hiểu stack |
| Có tiêu chí tiếp tục hoặc loại bỏ | Công nghệ tồn tại vô thời hạn |
| Có security patch cadence | Không biết ai chịu trách nhiệm vá |
| Có contract liên dịch vụ ổn định | Tích hợp riêng theo từng stack |

Một hệ thống có mười ngôn ngữ không nhất thiết tệ nếu mỗi ngôn ngữ phục vụ một nhu cầu quan trọng, có đội ngũ và platform hỗ trợ. Ngược lại, ba ngôn ngữ cũng có thể là quá nhiều nếu tổ chức nhỏ và không đủ người vận hành.

**Số lượng công nghệ không phải chỉ số chất lượng độc lập.** Cần đo độ phức tạp và lợi ích mà mỗi công nghệ mang lại.

## 5. Lợi ích của đa dạng công nghệ

### 5.1. Dùng đúng công cụ cho workload

Một tác vụ có thể phù hợp với runtime khác nhau:

- CPU-bound computation cần tối ưu concurrency hoặc native performance.
- Data science/ML cần hệ sinh thái thư viện phân tích và model.
- API CRUD có thể ưu tiên hệ sinh thái framework, validation và persistence ổn định.
- Worker xử lý stream có thể cần throughput, backpressure và memory footprint đặc thù.
- Frontend/server-side rendering cần runtime và tooling phù hợp web.

Việc chọn công nghệ đúng có thể giảm code tùy biến và tăng hiệu quả phát triển.

### 5.2. Tối ưu hiệu năng hoặc tài nguyên

Một runtime nhẹ có thể giảm memory footprint cho hàng nghìn worker ngắn hạn; một thư viện native có thể tăng tốc phép tính; một database chuyên biệt có thể cải thiện truy vấn phân tích. Nhưng phải đo bằng workload đại diện, không chỉ dựa vào quảng cáo hoặc microbenchmark.

### 5.3. Khai thác năng lực chuyên môn

Team có chuyên môn sâu về Python ML hoặc .NET có thể tạo giá trị nhanh hơn khi dùng công cụ họ hiểu. Bắt buộc chuyển toàn bộ team sang một stack mới có thể làm tăng rủi ro và chi phí đào tạo.

### 5.4. Giảm phụ thuộc vào một công nghệ

Đa dạng có thể giảm rủi ro khi một công nghệ không còn phù hợp, bị giới hạn license hoặc không đáp ứng yêu cầu. Tuy nhiên, thêm một stack không tự động giảm vendor lock-in; nó cũng có thể tạo một dependency mới.

### 5.5. Cho phép tiến hóa theo domain

Một số domain có data model và workload khác biệt đáng kể. Polyglot persistence cho phép chọn relational database cho giao dịch, search engine cho tìm kiếm và object storage cho blob. Mỗi datastore vẫn cần owner, backup, access policy và đường khôi phục.

## 6. Chi phí ẩn của mỗi công nghệ mới

Chi phí thường không xuất hiện đầy đủ trong estimate của feature ban đầu.

### 6.1. Chi phí xây dựng nền tảng

- Service template và build image.
- Pipeline compile/test/package/deploy.
- Dependency cache và artifact repository.
- Secret management và configuration.
- Health checks, readiness, graceful shutdown.
- Metrics, logs, tracing và alert.
- Security scanner, SBOM và vulnerability policy.
- Backup, restore và disaster recovery.

### 6.2. Chi phí vận hành

- Cài đặt và vá runtime.
- Nâng version framework và thư viện.
- Theo dõi CVE và dependency lifecycle.
- Xử lý memory leak, thread starvation, GC hoặc event loop.
- Debug production với tool và profiler khác nhau.
- Quản lý certificate, TLS và connection pool.
- Tương thích base image, architecture và operating system.

### 6.3. Chi phí nhân sự

- Tuyển người có kỹ năng phù hợp.
- Đào tạo và onboarding.
- Phân ca on-call.
- Hỗ trợ khi chuyên gia nghỉ việc.
- Duy trì kiến thức qua tài liệu, pairing và runbook.
- Phân bổ thời gian của platform/security team cho stack mới.

### 6.4. Chi phí phối hợp

Nhiều stack có thể khiến team khó chia sẻ thư viện, convention, test harness và cách quan sát. Một incident xuyên service đòi hỏi người hiểu nhiều runtime và protocol. Nếu mỗi team có cách đặt metric hoặc log khác nhau, thời gian điều tra tăng.

## 7. Đánh giá theo Total Cost of Ownership

Không nên so sánh công nghệ chỉ bằng chi phí license hoặc hiệu năng request. **Total Cost of Ownership (TCO)** cần xét toàn bộ vòng đời.

Một mô hình khái niệm:

~~~text
TCO trong một khoảng thời gian
= Chi phí xây dựng ban đầu
+ Chi phí runtime/hạ tầng
+ Chi phí platform integration
+ Chi phí bảo trì và nâng cấp
+ Chi phí bảo mật/compliance
+ Chi phí tuyển dụng và đào tạo
+ Chi phí on-call/incident
+ Chi phí chuyển đổi hoặc loại bỏ
~~~

Đây là khung để lập estimate, không phải công thức kế toán bắt buộc. Một số chi phí khó quy đổi tiền trực tiếp; có thể ghi riêng effort, risk và opportunity cost.

### 7.1. Ví dụ so sánh giả định

Một nhóm muốn dùng Runtime B cho một worker có thể xử lý 20.000 message/giây thay vì Runtime A xử lý 15.000 message/giây trong benchmark.

| Thành phần | Runtime A | Runtime B |
|---|---:|---:|
| Năng lực benchmark | 15.000 msg/s | 20.000 msg/s |
| Hạ tầng hàng tháng | 1.000 đơn vị | 800 đơn vị |
| Platform integration ban đầu | Đã có | 30 ngày công |
| On-call support | Nhiều người biết | 1-2 người |
| Dependency/security tooling | Đã chuẩn hóa | Cần tích hợp |
| Khả năng tuyển dụng | Rộng | Hẹp hơn trong tổ chức |
| Nâng cấp/patch | Quy trình sẵn | Chưa có quy trình |

Các số liệu là minh họa. Runtime B có thể tiết kiệm compute nhưng chi phí platform và rủi ro vận hành ban đầu lớn. Nếu worker tạo 60% chi phí compute của nền tảng, lợi ích có thể đáng để đầu tư. Nếu nó chỉ chiếm 1% workload, có thể không đáng thêm stack.

### 7.2. Chi phí cơ hội

Một kỹ sư xây integration cho stack mới có thể không dành thời gian cải thiện nền tảng chung, xử lý lỗi người dùng hoặc nâng cấp dependency cũ. TCO cần tính cả công việc bị trì hoãn, không chỉ hóa đơn cloud.

## 8. Ma trận lựa chọn công nghệ

Trước khi thêm một stack, xác định tiêu chí và trọng số phù hợp với sản phẩm.

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| Functional fit | Công nghệ giải quyết nhu cầu nào mà stack hiện tại khó đáp ứng? |
| Performance | Có benchmark trên workload thực không? |
| Reliability | Runtime có hành vi failure/recovery dễ kiểm soát không? |
| Security | Có patch cadence, scanner, SBOM và support policy không? |
| Maintainability | Team có đủ kỹ năng và khả năng nâng cấp không? |
| Operability | Có logs, metrics, traces, profiling và runbook không? |
| Interoperability | Có contract/API/event tiêu chuẩn không? |
| Ecosystem | Thư viện, community, documentation và vendor support ra sao? |
| Hiring | Có thể tuyển hoặc đào tạo người thay thế không? |
| Cost | TCO trong 2-3 năm và chi phí loại bỏ là gì? |
| Lifecycle | Công nghệ có roadmap và thời hạn support phù hợp không? |
| Portability | Có bị phụ thuộc vào API/runtime độc quyền không? |

Có thể chấm điểm từ 1 đến 5, nhưng không nên cộng điểm một cách máy móc. Một rủi ro bảo mật hoặc thiếu owner có thể là điều kiện loại trừ, dù tổng điểm cao.

### 8.1. Ví dụ ma trận có trọng số

| Tiêu chí | Trọng số | Stack A | Stack B |
|---|---:|---:|---:|
| Functional fit | 20% | 4 | 5 |
| Performance | 15% | 4 | 5 |
| Operability | 20% | 5 | 2 |
| Security support | 15% | 5 | 3 |
| Hiring/skills | 10% | 5 | 2 |
| TCO | 20% | 4 | 3 |

Điểm giả định:

~~~text
Score(A) = 0.20×4 + 0.15×4 + 0.20×5
         + 0.15×5 + 0.10×5 + 0.20×4
         = 4.40

Score(B) = 0.20×5 + 0.15×5 + 0.20×2
         + 0.15×3 + 0.10×2 + 0.20×3
         = 3.35
~~~

Stack B có functional fit/performance tốt hơn nhưng chưa có khả năng vận hành và kỹ năng đủ mạnh. Kết quả không có nghĩa B bị cấm; có thể đầu tư platform support trước rồi đánh giá lại.

## 9. Xây dựng supported technology portfolio

Một tổ chức có thể công bố **technology portfolio** hoặc tech radar để cho biết công nghệ nào được khuyến nghị và ở trạng thái nào.

| Trạng thái | Ý nghĩa | Chính sách gợi ý |
|---|---|---|
| Adopt | Đã được hỗ trợ và khuyến nghị cho use case rõ | Có template, pipeline, owner và support |
| Trial | Đang thử nghiệm có giới hạn | Chỉ áp dụng trong dự án thử, có thời hạn |
| Assess | Đang nghiên cứu giá trị và rủi ro | Chưa dùng cho workload production trọng yếu |
| Hold | Không khuyến khích cho dự án mới | Chỉ duy trì hệ thống hiện có hoặc có ngoại lệ |
| Retire | Đang trong lộ trình loại bỏ | Không tạo service mới, có kế hoạch migration |

Các trạng thái này là một cách tổ chức thông tin, không phải chuẩn bắt buộc. Cần gắn mỗi lựa chọn với version, runtime support, owner và ngày xem xét.

### 9.1. Default stack

Một default stack có thể gồm:

- Ngôn ngữ/runtime phổ biến nhất của backend.
- Một framework API được hỗ trợ.
- Một relational database mặc định.
- Một message broker/event platform mặc định.
- Một bộ logging/metrics/tracing.
- Một build/deploy template.
- Một policy dependency/security.

Default stack giúp giảm quyết định lặp lại và chi phí platform. Nó không cấm công nghệ khác khi có lý do thuyết phục.

### 9.2. Ngoại lệ phải có thời hạn

Một request ngoại lệ nên nêu:

1. Vấn đề cụ thể mà default stack không giải quyết tốt.
2. Lợi ích đo được hoặc yêu cầu bắt buộc.
3. Owner chịu trách nhiệm runtime và security.
4. Cách tích hợp CI/CD, observability và secrets.
5. Kế hoạch đào tạo/on-call.
6. TCO và dependency lifecycle.
7. Phạm vi thử nghiệm và tiêu chí thành công.
8. Ngày review lại hoặc điều kiện loại bỏ.

Ngoại lệ không nên là một cuộc họp phê duyệt chung cho mọi thư viện. Chỉ yêu cầu review sâu khi có tác động hệ thống, security, dữ liệu hoặc chi phí vận hành đáng kể.

## 10. Polyglot persistence: đa dạng database có chủ đích

Microservices có thể dùng nhiều loại datastore vì mỗi domain có access pattern khác nhau.

| Loại lưu trữ | Use case thường gặp | Rủi ro/chi phí |
|---|---|---|
| Relational DB | Transaction, constraint, query quan hệ | Schema migration, lock, connection capacity |
| Document DB | Aggregate document, schema linh hoạt | Index, consistency và query cross-document |
| Key-value/cache | Lookup nhanh, ephemeral state | TTL, eviction, invalidation, hot key |
| Search engine | Full-text search, relevance | Index lag, storage và cluster operations |
| Columnar warehouse | Analytics, aggregation lớn | Không phù hợp transaction latency thấp |
| Object storage | Blob, file, export/import | Quyền truy cập, lifecycle, metadata consistency |
| Graph DB | Quan hệ nhiều bước đặc thù | Query model và vận hành chuyên biệt |

### 10.1. Không chọn database chỉ theo xu hướng

Ví dụ một service CRUD đơn giản dùng PostgreSQL đã đáp ứng latency, transaction và scale. Chuyển sang document database chỉ vì team muốn schema linh hoạt có thể tạo thêm chi phí backup, query, consistency và kỹ năng mà không đem lại lợi ích đáng kể.

Ngược lại, search engine có thể hợp lý cho full-text search thay vì tự xây inverted index trong relational DB. Tuy nhiên, search index thường là projection có thể rebuild từ nguồn dữ liệu chính; không nên mặc nhiên coi nó là nguồn sự thật cho giao dịch.

### 10.2. Data ownership và integration

Mỗi service nên có owner cho dữ liệu chính của nó. Service khác truy cập qua API/event hoặc read model phù hợp, thay vì kết nối trực tiếp database của nhau. Đa dạng database làm quy tắc này càng quan trọng vì cross-database transaction và migration có thể phức tạp.

## 11. Chuẩn hóa những gì, cho phép khác biệt những gì?

Một chiến lược thực tế thường chuẩn hóa **cách vận hành và giao tiếp**, còn cho phép **implementation khác nhau** khi có lý do.

| Lĩnh vực | Mức chuẩn hóa gợi ý | Lý do |
|---|---|---|
| API conventions | Cao | Dễ tích hợp, auth và debug |
| Logging/metrics/tracing | Cao | Quan sát nhất quán |
| CI/CD artifact and provenance | Cao | Bảo mật và triển khai |
| Secrets/configuration | Cao | Giảm rủi ro vận hành |
| Health checks/graceful shutdown | Cao | Platform cần hiểu hành vi service |
| Language | Mặc định có giới hạn, có ngoại lệ | Giảm runtime sprawl |
| Framework | Một vài lựa chọn được hỗ trợ | Cân bằng năng suất và diversity |
| Database | Theo domain/access pattern | Có thể cần nhiều mô hình dữ liệu |
| Internal libraries | Chọn lọc | Tránh shared model coupling |
| Deployment topology | Theo SLO/workload, có mẫu | Giảm khác biệt vận hành không cần thiết |

Chuẩn hóa không nhất thiết là dùng một thư viện duy nhất cho mọi ngôn ngữ. Có thể định nghĩa contract và telemetry schema chung, sau đó cung cấp SDK chính thức cho từng runtime được hỗ trợ.

## 12. Golden path và paved road

**Golden path** là cách làm mặc định được platform hỗ trợ tốt, giúp team tạo service an toàn và vận hành được mà không phải tự phát minh mọi thứ.

Một service template có thể tạo sẵn:

- Cấu trúc repository và module convention.
- Build/test/package pipeline.
- Container image có base image được quản lý.
- SBOM và dependency/vulnerability scan.
- Structured logs, metrics, distributed tracing.
- Liveness/readiness/startup checks.
- Secret/config integration.
- Deployment manifests, resource requests/limits.
- Alert/runbook template.
- Contract test và versioning conventions.
- Quy trình rollback và ownership metadata.

### 12.1. Vì sao golden path giúp cân bằng diversity?

Nếu một team dùng ngôn ngữ khác nhưng vẫn tích hợp được vào pipeline, logs, tracing, policy và deploy workflow chuẩn, chi phí khác biệt giảm. Platform có thể hỗ trợ một số runtime có chọn lọc thay vì mọi công nghệ tùy ý.

### 12.2. Đừng biến golden path thành rào cản

Golden path cần có đường thoát có kiểm soát. Nếu một workload cần streaming hoặc native library đặc biệt, team có thể đề xuất extension. Platform nên cho phép cấu hình và plugin ở những điểm đã thiết kế, thay vì buộc mọi service giống nhau đến mức không giải quyết được use case.

## 13. Chuẩn hóa observability xuyên nhiều runtime

Khi service viết bằng nhiều ngôn ngữ, cách log và metric khác nhau làm incident khó điều tra. Nên thống nhất:

- Trace context propagation, ví dụ W3C Trace Context khi hệ sinh thái hỗ trợ.
- Correlation ID và request ID.
- Structured logging với timestamp, severity, service name, environment và version.
- Metric naming, unit và label cardinality.
- Error classification và status mapping.
- Redaction dữ liệu nhạy cảm.
- Sampling và retention.
- Health/readiness semantics.

Ví dụ log có cấu trúc:

~~~json
{
  "timestamp": "2026-11-12T02:00:00Z",
  "level": "ERROR",
  "service": "order-service",
  "runtime": "jvm",
  "version": "2.4.1",
  "traceId": "trace-123",
  "errorCode": "PAYMENT_TIMEOUT"
}
~~~

Ví dụ là dữ liệu minh họa. Các trường chung giúp truy vấn xuyên service, nhưng không nên thêm mọi thuộc tính có cardinality vô hạn thành metric label. Platform có thể cung cấp SDK hoặc agent phù hợp cho từng runtime.

## 14. Security và compliance trong môi trường đa công nghệ

Mỗi runtime/framework có vòng đời và cách quản lý dependency riêng. Đa dạng công nghệ mở rộng bề mặt cần bảo vệ:

- Base image và runtime patching.
- Package manager, lockfile và transitive dependencies.
- CVE detection, exploitability và thời gian xử lý.
- SBOM, artifact signing và provenance.
- Secret storage, TLS, certificate rotation.
- Authentication/authorization SDK.
- Data encryption, audit và retention.
- Quy trình xử lý lỗ hổng nghiêm trọng.
- Hỗ trợ version và end-of-life.

Một runtime không còn security support có thể buộc tổ chức phải nâng cấp hoặc thay thế dù service vẫn chạy tốt. Vì vậy, lifecycle policy phải là một phần của quyết định lựa chọn ban đầu.

### 14.1. Security baseline xuyên ngôn ngữ

Không cần mọi service dùng cùng framework để có chính sách bảo mật nhất quán. Có thể đặt yêu cầu:

1. Dependency phải được kiểm kê và scan.
2. Artifact có thể truy vết đến source commit và pipeline.
3. Secret không được hardcode trong repository/image.
4. TLS và authentication theo chuẩn tổ chức.
5. Image/runtime có patch cadence.
6. Log không lộ dữ liệu nhạy cảm.
7. Có owner và SLA xử lý lỗ hổng.
8. Production version phải nằm trong supported lifecycle.

## 15. Version sprawl và dependency management

Đa dạng ngôn ngữ chỉ là một phần. Một tổ chức có thể dùng Java ở mọi nơi nhưng vẫn có hàng chục phiên bản JDK, Spring Boot, logging framework và database driver khác nhau.

Version sprawl gây:

- Lỗ hổng nằm trong dependency cũ.
- Build reproducibility thấp.
- Khó chia sẻ base image và pipeline.
- Một service không thể nâng cấp vì library không còn tương thích.
- Người on-call phải nhớ hành vi nhiều version.
- Các tool scanning không còn hỗ trợ một số phiên bản.

### 15.1. Supported version matrix

Có thể công bố bảng:

| Thành phần | Supported | Maintenance | End-of-life |
|---|---|---|---|
| JDK/runtime | Phiên bản được khuyến nghị | Chỉ security fixes | Không nhận production workload mới |
| Framework | Phiên bản tương thích runtime | Kế hoạch nâng cấp | Có deadline migration |
| Base image | Image đã scan | Security patch | Không được deploy |
| Database driver | Được kiểm thử | Giới hạn cập nhật | Phải nâng cấp |

Các giá trị cụ thể phải được cập nhật theo vendor và policy của tổ chức; không nên cố định một version trong tài liệu lâu dài nếu support window đã thay đổi.

### 15.2. Nâng cấp theo nhịp

- Theo dõi release/security advisory.
- Có owner cho mỗi service và dependency.
- Dùng automated PR hoặc dependency update bot.
- Chạy unit, integration và contract tests.
- Nâng cấp theo wave, canary khi rủi ro cao.
- Đặt thời hạn xử lý CVE theo severity.
- Loại bỏ dependency không dùng.
- Ghi lại compatibility constraints và lý do pin version.

Nâng cấp thường xuyên, nhỏ và có kiểm thử thường dễ quản lý hơn một lần nâng cấp lớn sau nhiều năm.

## 16. Tuyển dụng, onboarding và bus factor

Một công nghệ mới có thể giảm chi phí compute nhưng tăng rủi ro nếu chỉ một người hiểu nó. **Bus factor** là cách nói về mức độ tập trung tri thức; nếu một cá nhân rời nhóm và không ai có thể vận hành service, rủi ro duy trì rất cao.

Trước khi chấp nhận stack mới, hỏi:

- Có ít nhất hai người có thể review và xử lý production không?
- Team khác có thể hỗ trợ khi on-call không?
- Có tài liệu setup, deploy, debug và rollback không?
- Có thể tuyển người trên thị trường hoặc đào tạo nội bộ không?
- Có test và automated checks giảm phụ thuộc kiến thức cá nhân không?
- Platform có thể cung cấp phần runtime chung không?

### 16.1. Onboarding time là một chi phí

Nếu mỗi stack mới cần 6 tuần để kỹ sư hiểu toolchain, deploy và debug, việc luân chuyển người giữa team trở nên khó. Một số chuẩn chung như repository conventions, tracing, pipeline và API contracts giúp người mới chuyển domain dễ hơn dù ngôn ngữ khác nhau.

### 16.2. Không dùng “ai cũng biết Java” làm tiêu chí duy nhất

Năng lực hiện tại quan trọng, nhưng không phải lý do vĩnh viễn để giữ một công nghệ không phù hợp. Nếu một workload có lợi ích rõ rệt từ stack khác, có thể đào tạo và xây platform support. Quyết định cần tính thời gian chuyển tiếp và khả năng duy trì sau khi chuyên gia đầu tiên rời dự án.

## 17. Khả năng bảo trì: những thành phần cần nhất quán

Một hệ thống đa ngôn ngữ vẫn có thể dễ bảo trì nếu các điểm giao tiếp và quy trình vận hành được thống nhất.

### 17.1. Contract-first

API/event contract phải độc lập với language-specific object model. Dùng OpenAPI, Protobuf, AsyncAPI hoặc schema phù hợp; không chia sẻ class Java làm hợp đồng xuyên ngôn ngữ.

### 17.2. Domain ownership

Mỗi service sở hữu dữ liệu và quy tắc nghiệp vụ của nó. Tránh các service đa ngôn ngữ cùng ghi vào một database schema mà không có owner.

### 17.3. Runtime contract

Service phải tuân thủ cách nhận cấu hình, secret, health checks, shutdown, logs, metrics và tracing đã thống nhất. Đây là hợp đồng giữa service và platform.

### 17.4. Release contract

Artifact phải versioned, có digest, có thể deploy/rollback và được kiểm tra trong pipeline. Một service dùng runtime khác vẫn cần quy trình release có thể dự đoán.

### 17.5. Error semantics

Các service nên thống nhất cách phân loại lỗi, timeout, retryable/non-retryable và idempotency. Nếu mỗi stack trả một loại lỗi riêng, gateway và consumer khó xử lý thống nhất.

## 18. Chọn ngôn ngữ theo bài toán, không theo phong trào

Một ma trận cân nhắc có thể là:

| Nhu cầu | Tiêu chí lựa chọn |
|---|---|
| API nghiệp vụ | Ecosystem, maintainability, framework support, team skill |
| CPU-intensive processing | Benchmark, concurrency model, native optimization |
| Data science/ML | Library ecosystem, model lifecycle, deployment constraints |
| Worker nhẹ, số lượng lớn | Memory footprint, startup time, concurrency, operability |
| Frontend/BFF | Tooling, client ecosystem, rendering needs |
| Streaming | Backpressure, throughput, memory, client/broker support |
| Security-critical service | Runtime support, library quality, audit, team expertise |

Không có ngôn ngữ tốt nhất chung cho mọi tiêu chí. Benchmark cần sử dụng cùng input, cùng business semantics, cùng resource budget và đo end-to-end.

### 18.1. Ví dụ polyglot hợp lý

~~~text
Checkout Service (Java)
  - Transaction orchestration
  - Relational persistence
  - Business rules

Fraud Scoring Worker (Python)
  - Model inference
  - Feature processing
  - Async result event

Media Processing Service (Go)
  - Concurrent file processing
  - Bounded memory workers

All services:
  - Versioned API/event contracts
  - Common tracing/logging conventions
  - Standard CI/CD and security checks
~~~

Ví dụ chỉ thể hiện phân chia theo workload. Không nên thêm ba runtime nếu tất cả service có thể chạy tốt trên một stack mà không có lợi ích khác biệt.

## 19. Quy trình đưa một công nghệ mới vào production

Một quyết định có thể đi qua các giai đoạn:

### Giai đoạn 1 — Nêu vấn đề

Mô tả workload hoặc constraint mà công nghệ hiện tại không giải quyết tốt: latency, memory, throughput, ecosystem hoặc compliance. Đưa baseline và mục tiêu định lượng.

### Giai đoạn 2 — So sánh phương án

Đánh giá tối ưu stack hiện có, dùng managed service, thêm library hoặc thay một component trước khi thêm runtime mới.

### Giai đoạn 3 — Proof of concept

Dựng POC giới hạn, dùng dữ liệu và workload đại diện. Đo performance, startup, memory, developer productivity và integration effort.

### Giai đoạn 4 — Đánh giá operability

Chứng minh build/deploy, observability, secrets, security scan, backup/restore, autoscaling, rollback và on-call.

### Giai đoạn 5 — Xác định owner và support model

Có team chịu trách nhiệm, người backup, tài liệu, runtime support matrix và lịch nâng cấp.

### Giai đoạn 6 — Pilot có thời hạn

Đưa vào một workload nhỏ, có tiêu chí thành công và điều kiện dừng. Không mở rộng đồng loạt khi chưa có dữ liệu production.

### Giai đoạn 7 — Quyết định portfolio

Chuyển sang Adopt/Trial/Hold hoặc loại bỏ. Ghi quyết định, lý do, scope và ngày review.

### Giai đoạn 8 — Mở rộng có kiểm soát

Chỉ mở rộng khi platform support và năng lực con người đã sẵn sàng; không để mỗi team tự copy POC thành production service.

## 20. Architecture Decision Record cho lựa chọn công nghệ

ADR giúp lưu quyết định và hệ quả để team sau hiểu vì sao một stack tồn tại.

~~~markdown
# ADR-024: Dùng Python cho Fraud Scoring Worker

## Context
Fraud scoring phụ thuộc thư viện ML hiện có.
Workload bất đồng bộ, không nằm trong checkout request latency path.

## Decision
Dùng Python worker cho inference.
Giao tiếp qua versioned event contract.
Không cho worker truy cập trực tiếp Order database.

## Consequences
Cần Python runtime template, scanner và observability.
Fraud team sở hữu model/runtime và on-call.
Review lại chi phí sau hai quý.
~~~

Đây là ví dụ minh họa. Một ADR tốt ghi cả phương án đã cân nhắc, lý do không chọn, giả định, rủi ro và điều kiện xem xét lại.

## 21. Chuẩn hóa thông qua platform thay vì áp đặt từng service

Platform team có thể hỗ trợ một số runtime được chọn:

- Base images được vá và kiểm kê.
- Build templates cho các ngôn ngữ được hỗ trợ.
- Dependency scanning và SBOM.
- Logging/metrics/tracing SDK hoặc agent.
- Secrets và configuration integration.
- Health checks và graceful shutdown examples.
- Deployment manifests và autoscaling defaults.
- Runbook/alert templates.
- Runtime version policy.
- Self-service service catalog.

Nếu mỗi runtime đều cần platform viết lại toàn bộ tooling, số runtime được hỗ trợ nên giới hạn theo khả năng. Có thể mở rộng dần khi nhu cầu đủ lớn.

### 21.1. Supported tier

Một cách phân loại:

- **Tier 1:** runtime được hỗ trợ đầy đủ, có golden path, on-call guidance và upgrade automation.
- **Tier 2:** được phép dùng với owner riêng; platform hỗ trợ integration ở mức giới hạn.
- **Experimental:** chỉ POC hoặc workload không trọng yếu; không được dùng cho dữ liệu/luồng production quan trọng nếu chưa có phê duyệt phù hợp.
- **Retiring:** không nhận workload mới; có migration plan và deadline.

Tên tier là quy ước nội bộ có thể thay đổi. Quan trọng là team biết rõ mức hỗ trợ và trách nhiệm khi xảy ra lỗi.

## 22. Quản lý ngoại lệ

Một exception không nên được duyệt chỉ vì “team thích ngôn ngữ này”. Request cần có:

| Thành phần | Bằng chứng cần có |
|---|---|
| Vấn đề | Baseline hiện tại và constraint |
| Lợi ích | Throughput, latency, cost hoặc capability được cải thiện |
| Phương án khác | Tối ưu stack hiện có, managed service, library |
| Operability | Pipeline, metrics, logs, tracing, rollback |
| Security | Patch support, scanner, dependency policy |
| People | Owner, backup, training và hiring |
| Lifecycle | Upgrade path, EOL plan, decommission |
| TCO | Chi phí đầu tư và vận hành theo thời gian |
| Scope | Phạm vi pilot, workload và thời hạn |
| Review trigger | Điều kiện mở rộng, dừng hoặc loại bỏ |

Có thể phê duyệt ngoại lệ theo rủi ro và phạm vi. Một library thuần không làm thay đổi runtime thường cần review nhẹ hơn một database engine hoặc một runtime mới xử lý dữ liệu nhạy cảm.

## 23. Chiến lược giảm đa dạng công nghệ không còn giá trị

Không nên bắt đầu bằng rewrite toàn hệ thống. Ưu tiên những nơi có chi phí duy trì cao và lợi ích hội tụ rõ.

### 23.1. Inventory

Liệt kê service, language/runtime version, framework, datastore, owner, traffic, SLO, dependency, support status và mức độ criticality.

### 23.2. Xác định duplicate capability

Nhiều service có thể dùng ba logging library, bốn cách deploy hoặc nhiều phiên bản HTTP client. Một số khác biệt chỉ là convention chứ không tạo giá trị nghiệp vụ.

### 23.3. Ưu tiên theo rủi ro và chi phí

Ưu tiên công nghệ EOL, thiếu owner, có lỗ hổng nghiêm trọng hoặc tốn nhiều effort để duy trì. Không nhất thiết loại bỏ công nghệ hiếm nếu nó có vai trò quan trọng và ổn định.

### 23.4. Chuẩn hóa ở boundary trước

Có thể chuẩn hóa:

- API/event contracts.
- Logging/tracing fields.
- Artifact metadata.
- Security scanning.
- Deployment/health checks.
- Runtime support policy.

Các bước này thường giảm chi phí phối hợp mà chưa cần đổi ngôn ngữ.

### 23.5. Migration có điều kiện

Nếu cần chuyển service sang stack chuẩn:

1. So sánh behavior và contract hiện tại.
2. Tạo implementation mới với cùng API/event.
3. Chạy contract/integration tests.
4. Shadow traffic hoặc canary nếu an toàn.
5. Chuyển consumer/traffic theo wave.
6. Theo dõi SLO, cost và data integrity.
7. Giữ rollback path cho đến khi đủ bằng chứng.
8. Loại bỏ runtime cũ và cập nhật inventory.

Không nên giữ hai implementation lâu vô hạn. Đặt deadline và owner cho phần legacy sau cutover.

## 24. Polyglot architecture và khả năng quan sát

Nhiều runtime có thể dùng các agent/SDK khác nhau, nhưng nên phát ra telemetry theo quy ước chung.

Một trace cần cho phép theo dõi:

~~~text
API Gateway
   |
   v
Order Service (JVM)
   |
   v
Kafka Producer
   |
   v
Fraud Worker (Python)
   |
   v
Fraud Result Event
   |
   v
Checkout Workflow
~~~

Các nguyên tắc:

- Propagate trace context qua HTTP/gRPC và message headers.
- Dùng service name, version, environment và deployment metadata nhất quán.
- Chuẩn hóa error category và retry outcome.
- Định nghĩa unit của metric rõ ràng.
- Giữ label cardinality trong giới hạn.
- Không log secret, token, PII hoặc toàn bộ payload không cần thiết.
- Có cách tương quan logs/metrics/traces giữa nhiều runtime.

Một SDK chung có thể không phù hợp mọi ngôn ngữ; platform có thể cung cấp wrapper hoặc instrumentation theo từng runtime nhưng giữ cùng semantics.

## 25. Testing trong hệ sinh thái nhiều công nghệ

Mỗi service có thể có unit/integration tests khác nhau, nhưng contract và workflow cross-service phải nhất quán.

### 25.1. Test theo từng lớp

- Unit tests kiểm tra logic nội bộ.
- Component/integration tests kiểm tra framework, DB và broker adapter.
- Contract tests kiểm tra provider/consumer tương thích.
- End-to-end tests kiểm tra workflow quan trọng.
- Performance tests kiểm tra workload và resource budget.
- Security tests kiểm tra dependency, image và runtime configuration.
- Resilience tests kiểm tra timeout, retry, shutdown và dependency failure.

### 25.2. Contract không phụ thuộc language

Ví dụ Payment API được định nghĩa bằng OpenAPI. Consumer Java và consumer Python đều có thể tạo client hoặc test contract từ cùng schema. Điều này giảm coupling theo object model của một ngôn ngữ.

### 25.3. Test matrix cần có giới hạn

Không cần kiểm thử mọi tổ hợp của mọi runtime/version. Tập trung vào:

- Những cặp service thực sự giao tiếp.
- Phiên bản provider/consumer còn được hỗ trợ.
- Breaking/behavior changes.
- Data/schema migration.
- Workflow nghiệp vụ có rủi ro cao.
- Các runtime hoặc broker version thay đổi trong release.

## 26. Database diversity và chi phí vận hành

Thêm datastore không chỉ là thêm một connection string. Mỗi hệ thống lưu trữ cần:

- Backup/restore và kiểm thử phục hồi.
- Encryption, access policy và audit.
- Schema/index migration.
- Capacity planning và scaling.
- Replication/consistency monitoring.
- Query profiling và performance troubleshooting.
- Data retention và deletion.
- Disaster recovery.
- On-call skill và support contract.

Nếu một service chọn database mới, cần chỉ ra capability nào không thể đạt hợp lý bằng datastore hiện tại. Đôi khi managed database hoặc một read model chuyên biệt là đủ, không cần tự vận hành cluster mới.

### 26.1. Polyglot persistence không phải database-per-table

Mỗi bounded context có quyền sở hữu dữ liệu của mình, nhưng không có nghĩa mỗi bảng phải nằm trong một database engine riêng. Cần cân bằng ownership, transaction, operational capacity và query patterns.

### 26.2. Eventual consistency và nhiều datastore

Khi một nghiệp vụ cập nhật nhiều hệ thống lưu trữ, transaction phân tán trở nên khó. Cần outbox, saga, idempotency, reconciliation hoặc workflow phù hợp. Thêm datastore làm tăng khả năng xảy ra trạng thái lệch; phải có cách phát hiện và sửa.

## 27. Technology lifecycle: từ Adopt đến Retire

Mỗi công nghệ được hỗ trợ nên có lifecycle rõ:

~~~text
Assess
  |
  v
Trial / POC
  |
  v
Adopt
  |
  v
Maintain + Upgrade
  |
  v
Deprecate
  |
  v
Migrate / Retire
~~~

Các câu hỏi theo giai đoạn:

- **Assess:** vấn đề gì cần giải quyết, có phương án khác không?
- **Trial:** kết quả benchmark và integration ra sao?
- **Adopt:** ai hỗ trợ, version nào được phép, có template chưa?
- **Maintain:** patch, upgrade, on-call và capacity được quản lý thế nào?
- **Deprecate:** vì sao ngừng khuyến nghị, ngày nào không nhận service mới?
- **Retire:** service còn lại được migrate hoặc tắt ra sao, dữ liệu được xử lý thế nào?

Không nên giữ một công nghệ trong trạng thái “tạm thời” nhiều năm mà không có owner và review date.

## 28. Chi phí của đa dạng công nghệ trong incident

Khi một request lỗi xuyên qua nhiều service, người điều tra có thể cần:

- Hiểu thread dump/JVM GC.
- Hiểu Python worker/event loop.
- Đọc metrics và heap của Go process.
- Kiểm tra serializer, broker client và retry semantics.
- Biết cách trace context được truyền qua từng SDK.

Nếu không có tiêu chuẩn telemetry và runbook, thời gian xác định nguyên nhân tăng. Một công nghệ mới cần được xem xét cả **khả năng phục hồi sau sự cố**, không chỉ khả năng xử lý happy path.

### 28.1. On-call readiness

Trước khi đưa runtime mới vào production, xác nhận:

- Có dashboard chuẩn và alert phù hợp.
- Có runbook startup/shutdown, memory, CPU và dependency errors.
- Có cách lấy diagnostic data an toàn.
- Có owner chính và backup.
- Có support/escalation nếu gặp lỗi runtime hoặc framework.
- Có quy trình vá lỗ hổng và nâng cấp khẩn cấp.
- Có diễn tập incident hoặc game day phù hợp mức rủi ro.

Nếu không có ai nhận trách nhiệm on-call, service chưa sẵn sàng production dù POC hoạt động tốt.

## 29. Ví dụ quyết định: có nên thêm Rust cho một worker?

**Bối cảnh giả định:** một worker hiện dùng Java xử lý ảnh, CPU cao và có chi phí compute đáng kể. Một nhóm đề xuất viết lại bằng Rust.

Đánh giá:

1. Đo profile xác định thời gian nằm ở thuật toán, I/O hay encode/decode.
2. Thử tối ưu thuật toán, batch, concurrency và thư viện native trong Java.
3. Xây benchmark Rust dùng cùng input, output và resource limits.
4. Đo throughput, p95 latency, memory, CPU và failure behavior.
5. Ước lượng effort viết, review, CI, security scanning, deploy và observability.
6. Kiểm tra năng lực on-call, hiring và backup owner.
7. Xác định interface giữa worker và các service khác để giữ contract ổn định.
8. Tính TCO trong ít nhất một chu kỳ vận hành đủ dài.
9. Nếu lợi ích rõ, pilot một workload nhỏ và có rollback.
10. Nếu không có lợi ích vượt chi phí, giữ stack hiện tại và lưu kết quả đánh giá.

Không chọn Rust chỉ vì benchmark một hàm nhanh hơn. Cần chứng minh cải thiện ở **end-to-end workload** và chi phí toàn vòng đời.

## 30. Anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Mỗi team tự chọn mọi công nghệ | Runtime/tool sprawl | Default stack + exception process |
| Chọn theo sở thích cá nhân | Không có business/technical evidence | ADR, benchmark, TCO |
| Chỉ so sánh compute cost | Bỏ qua platform/on-call/hiring | Lifecycle cost model |
| POC trở thành production không review | Thiếu security và vận hành | Production readiness gate |
| Một người duy nhất hiểu runtime | Bus factor thấp | Backup owner, training, runbook |
| Mỗi service tự viết logging/tracing | Khó điều tra cross-service | Shared telemetry conventions |
| Nhiều version framework không kiểm kê | CVE và support risk | Supported version matrix |
| Thêm database vì schema linh hoạt | Backup/consistency/ops tăng | Chứng minh access pattern cần thiết |
| Chuẩn hóa mọi thứ bằng một stack duy nhất | Không phù hợp workload đặc biệt | Có ngoại lệ dựa trên bằng chứng |
| Giữ legacy runtime vô thời hạn | Cost và security debt | Deprecation/retirement plan |
| Shared library domain xuyên service | Coupled releases | Contract-first, model riêng |
| Platform phải làm hộ mọi stack | Platform thành bottleneck | Paved road và self-service |
| Dùng benchmark micro đơn lẻ | Quyết định sai workload | End-to-end representative test |
| Không có deadline cho Trial | POC tồn tại mãi | Review date và success criteria |

## 31. Bài thực hành A: đánh giá một công nghệ mới

**Tình huống:** nhóm đề xuất dùng một framework mới cho API catalog vì framework đó có startup nhanh và memory thấp. Hệ thống hiện đã có framework mặc định được platform hỗ trợ.

Hãy:

1. Ghi baseline startup time, memory, p95 latency và throughput của service hiện tại.
2. Tạo prototype dùng cùng contract và workload.
3. Đo build time, container size, dependency scanning và observability integration.
4. Xác định ai có thể trực production và xử lý CVE.
5. Ước lượng TCO ba năm, gồm platform và đào tạo.
6. Định nghĩa phạm vi pilot và ngày review.
7. Quyết định Adopt, Trial hoặc không tiếp tục dựa trên kết quả.

## 32. Bài thực hành B: giảm technology sprawl

**Tình huống:** một tổ chức có 25 service với 5 ngôn ngữ, 4 cách deploy, 3 hệ thống logging và 8 phiên bản framework đang được sử dụng.

Nhiệm vụ:

1. Tạo inventory theo service, owner, runtime/version, criticality và support status.
2. Xác định công nghệ EOL, thiếu owner hoặc gây incident.
3. Phân biệt khác biệt tạo giá trị với khác biệt chỉ do lịch sử.
4. Chọn một số chuẩn chung: CI/CD, telemetry, security và API contracts.
5. Chọn các stack mặc định và tier hỗ trợ.
6. Xây lộ trình migration theo rủi ro, không big-bang.
7. Đặt chỉ số trước/sau: time-to-patch, onboarding time, build/deploy effort và incident MTTR.

## 33. Bài thực hành C: thiết kế exception request

Viết một ADR ngắn để xin dùng Python cho một worker ML trong hệ thống Java:

- Vấn đề hiện tại và baseline.
- Lợi ích của Python so với tối ưu Java hoặc gọi managed ML service.
- Contract giữa producer và worker.
- Security/dependency policy.
- Runtime template, logs, traces và deployment.
- Owner chính, backup và on-call.
- TCO, upgrade cadence và điều kiện retire.
- Tiêu chí thành công của pilot.

## 34. Checklist trước khi thêm một stack

### Giá trị kỹ thuật và nghiệp vụ

- [ ] Có vấn đề cụ thể mà stack hiện tại chưa giải quyết hợp lý.
- [ ] Đã cân nhắc tối ưu implementation hiện tại hoặc dùng managed capability.
- [ ] Có benchmark/POC dùng workload đại diện.
- [ ] Lợi ích end-to-end đủ lớn để biện minh khác biệt.

### Maintainability và nhân sự

- [ ] Có owner và người backup.
- [ ] Có kỹ năng on-call hoặc kế hoạch đào tạo.
- [ ] Có thể tuyển/đào tạo người thay thế.
- [ ] Có tài liệu setup, debug, deploy, rollback và incident.
- [ ] Cognitive load của team vẫn nằm trong khả năng.

### Platform và vận hành

- [ ] Có CI/CD, artifact, base image và dependency scanning.
- [ ] Có logs, metrics, tracing và health checks chuẩn.
- [ ] Có secrets/config, access control và deployment policy.
- [ ] Có backup/restore nếu công nghệ lưu trữ dữ liệu.
- [ ] Có cách kiểm thử compatibility với các service khác.

### Lifecycle và chi phí

- [ ] Runtime/framework còn được hỗ trợ.
- [ ] Có security patch cadence và EOL plan.
- [ ] Có TCO gồm hạ tầng, platform, đào tạo, on-call và chuyển đổi.
- [ ] Ngoại lệ có scope, owner, thời hạn và review date.
- [ ] Có điều kiện Adopt, tiếp tục Trial hoặc Retire.

## 35. Kết luận

Đa dạng công nghệ cho phép Microservices dùng công cụ phù hợp với từng workload và domain. Nhưng mỗi runtime, framework hay datastore mới cũng tạo thêm chi phí build, deploy, bảo mật, quan sát, tuyển dụng, nâng cấp và xử lý sự cố. **Đa dạng chỉ có giá trị khi lợi ích của khác biệt lớn hơn chi phí duy trì nó.**

Một chiến lược bền vững là duy trì **default supported stack**, cho phép ngoại lệ dựa trên bằng chứng, chuẩn hóa những điểm vận hành và giao tiếp chung, cung cấp golden path và quản lý lifecycle từ Trial đến Retire. Các team vẫn có thể chọn công nghệ riêng khi workload thực sự cần, nhưng phải có owner, support model, security posture và TCO rõ ràng.

Quyết định tốt không phải “mọi service dùng cùng công nghệ” hay “mọi team tự do chọn bất cứ thứ gì”. Đó là **chọn ít khác biệt tùy tiện, giữ những khác biệt tạo giá trị, và làm cho các khác biệt còn lại có thể vận hành, nâng cấp và chuyển giao an toàn**.