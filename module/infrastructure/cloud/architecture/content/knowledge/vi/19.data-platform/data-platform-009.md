# Đánh giá kiến trúc phục vụ mô hình máy học và suy luận

Một mô hình máy học có độ chính xác tốt trong môi trường thử nghiệm chưa chắc hoạt động tốt khi đưa vào production. Khi số request tăng, dữ liệu đầu vào thay đổi, GPU thiếu, feature không đồng bộ hoặc model mới được phát hành, hệ thống có thể tăng độ trễ, trả dự đoán không nhất quán, tiêu tốn chi phí hoặc không thể khôi phục. Vì vậy, đánh giá kiến trúc phục vụ mô hình máy học cần xem xét toàn bộ đường đi từ dữ liệu, feature và model artifact tới runtime inference, tích hợp ứng dụng, giám sát và quy trình phát hành.

**Model serving** là phần hạ tầng và phần mềm nhận yêu cầu suy luận, nạp model, chuẩn bị đầu vào, thực thi model và trả kết quả theo một hợp đồng đã công bố. **Inference** là quá trình dùng model đã huấn luyện để tạo dự đoán hoặc kết quả từ dữ liệu mới. Hai khái niệm này liên quan nhưng không đồng nhất: inference có thể chạy bên trong ứng dụng, trong batch job, trên stream processor hoặc trên thiết bị edge; model serving thường mô tả một dịch vụ hoặc runtime chuyên phục vụ inference.

Bài học này thuộc chương **Nền tảng dữ liệu** của module **CLOUD_ARCHITECTURE**. Mục tiêu là đánh giá xem một kiến trúc có đáp ứng yêu cầu nghiệp vụ và kỹ thuật khi triển khai model trong môi trường cloud hay không. Trọng tâm gồm workload inference, dữ liệu và feature, model artifact, compute CPU/GPU, độ trễ và throughput, mở rộng, độ tin cậy, bảo mật, observability, chi phí và các đánh đổi theo tư duy Well-Architected.

## 1. Bắt đầu từ yêu cầu nghiệp vụ và workload inference

Không nên chọn Kubernetes, GPU hoặc một model serving framework trước khi hiểu workload. Cùng một model có thể được phục vụ theo nhiều cách tùy mức độ tương tác và thời gian cần kết quả.

Ví dụ, nền tảng đặt chỗ dùng ML cho ba chức năng:
- Gợi ý phòng phù hợp khi người dùng tìm kiếm.
- Xếp hạng kết quả tìm kiếm theo hành vi và ngữ cảnh.
- Chấm điểm rủi ro đặt chỗ theo lô để đội vận hành phân tích.

Chức năng gợi ý trên trang web cần phản hồi nhanh trong lúc người dùng đang tương tác. Chấm điểm rủi ro theo lô có thể chạy mỗi giờ hoặc mỗi ngày. Nếu đưa cả hai vào cùng một deployment và cùng một chính sách scaling, hệ thống có thể lãng phí tài nguyên hoặc không đạt được SLO.

### 1.1. Những câu hỏi cần thu thập

| Nhóm yêu cầu | Câu hỏi đánh giá | Ảnh hưởng kiến trúc |
|---|---|---|
| Use case | Model giải quyết quyết định hoặc trải nghiệm nào? | Xác định output, mức độ quan trọng và fallback |
| Inference mode | Online, batch, streaming hay edge? | Chọn endpoint, queue, job hoặc runtime tại thiết bị |
| Traffic | Request trung bình, peak, burst và tính mùa vụ? | Capacity, autoscaling, queue và quota |
| Latency | p50/p95/p99 tối đa là bao nhiêu? | Runtime, network, feature lookup và batching |
| Throughput | Số request/giây hoặc bản ghi/giờ? | Số replica, worker, GPU và partition |
| Availability | Dịch vụ cần sẵn sàng bao nhiêu? | Multi-zone, failover và dependency design |
| Output quality | Ngưỡng precision/recall, ranking quality hoặc business KPI? | Model validation, monitoring và rollback |
| Freshness | Model và feature cần mới đến mức nào? | Retraining, feature pipeline và deployment cadence |
| Data sensitivity | Input/output chứa PII hoặc dữ liệu nhạy cảm? | Encryption, access control, retention và audit |
| Cost | Ngân sách theo request, prediction hoặc tháng? | Model size, accelerator, batching và scale-to-zero |
| Failure behavior | Khi model/feature service lỗi, nghiệp vụ tiếp tục ra sao? | Fallback, degradation và retry policy |

### 1.2. Xây dựng workload profile

Một workload profile nên ghi ít nhất:
- Request rate bình thường và đỉnh.
- Kích thước request/response.
- Số feature cần đọc và chi phí chuẩn bị input.
- Thời gian model compute trên từng loại instance.
- Mức concurrency và batch size.
- Tỷ lệ cache hit nếu có cache feature hoặc prediction.
- Tỷ lệ lỗi và timeout ở các dependency.
- Các khoảng thời gian traffic tăng/giảm.
- Model size, memory footprint và loại compute cần thiết.

Nếu chưa biết những con số này, hãy đo prototype hoặc load test. Không nên lấy một benchmark trên máy phát triển để suy ra năng lực production vì phần cứng, network, batching, preprocessing và concurrency có thể khác đáng kể.

## 2. Chọn mô hình suy luận phù hợp

### 2.1. Online synchronous inference

Client hoặc backend gọi inference endpoint và chờ kết quả trong cùng request-response flow.

~~~mermaid
sequenceDiagram
    actor U as User
    participant API as Booking API
    participant F as Feature service
    participant M as Model endpoint
    U->>API: Search request
    API->>F: Fetch required features
    F-->>API: Feature vector
    API->>M: Predict
    M-->>API: Score / ranking
    API-->>U: Search response
~~~

Phù hợp khi kết quả ảnh hưởng ngay tới trải nghiệm hoặc quyết định đang diễn ra. Ưu điểm là consumer nhận kết quả trực tiếp, dễ tích hợp với HTTP/gRPC. Đánh đổi là latency của model và mọi dependency nằm trên critical path. Nếu feature store, model endpoint hoặc network chậm, request nghiệp vụ cũng bị chậm.

Đánh giá:
- Tổng latency gồm gateway, auth, feature lookup, preprocessing, model compute và response serialization.
- Có timeout end-to-end và timeout riêng cho từng dependency.
- Có fallback khi model không đáp ứng.
- Kiểm tra concurrency, queueing và tail latency.
- Không retry vô hạn request có deadline ngắn.

### 2.2. Batch inference

Batch inference xử lý một tập dữ liệu theo lịch hoặc theo sự kiện, ghi kết quả vào storage hoặc data warehouse để ứng dụng khác đọc sau.

~~~mermaid
flowchart LR
    DATA[("Data lake / warehouse")] --> JOB["Scheduled inference job"]
    JOB --> MODEL["Load model artifact"]
    MODEL --> PRED["Batch predictions"]
    PRED --> OUT[("Prediction table / object store")]
    OUT --> REPORT["Dashboard / downstream system"]
~~~

Phù hợp cho scoring danh sách khách hàng, dự báo nhu cầu, phân khúc, tính điểm rủi ro theo ngày hoặc tạo đề xuất trước. Không cần endpoint phản hồi từng request.

Ưu điểm:
- Xử lý được khối lượng lớn với batching.
- Có thể dùng compute theo lịch và tắt sau khi hoàn thành.
- Dễ tái chạy một partition hoặc một khoảng dữ liệu nếu workflow có lineage.
- Có thể tách chi phí batch khỏi dịch vụ online.

Đánh đổi:
- Kết quả có độ trễ theo lịch chạy.
- Job lớn có thể kéo dài hoặc cần checkpoint.
- Cần bảo đảm output không bị ghi trùng khi retry.
- Cần xử lý dữ liệu đến muộn, schema thay đổi và backfill.

Đánh giá phải có deadline hoàn thành (data-to-result SLA), khả năng resume, idempotency và đối soát số bản ghi đầu vào/đầu ra.

### 2.3. Streaming inference

Streaming inference xử lý sự kiện liên tục từ event bus hoặc stream processor. Ví dụ, hệ thống cập nhật điểm rủi ro mỗi khi có sự kiện đặt chỗ, thanh toán hoặc hủy.

~~~mermaid
flowchart LR
    P["Producers"] --> E[("Event stream")]
    E --> S["Stream processor"]
    S --> F["Feature enrichment"]
    F --> M["Model inference"]
    M --> R[("Scored events / state store")]
    R --> D["Consumers"]
~~~

Phù hợp khi cần kết quả gần thời gian thực nhưng không nhất thiết trả về trong request gốc. Đánh đổi nằm ở ordering, duplicate, late events, checkpoint, state management, backpressure và khả năng replay. Phải xác định inference có idempotent không, feature window được tính theo event time hay processing time và kết quả cũ được cập nhật ra sao.

### 2.4. Edge inference

Model được đóng gói và chạy trên thiết bị, gateway hoặc máy chủ gần nơi sinh dữ liệu. Ví dụ camera phát hiện đối tượng hoặc ứng dụng di động phân loại nội dung offline.

Ưu điểm:
- Giảm round-trip tới cloud.
- Có thể hoạt động khi kết nối chập chờn.
- Dữ liệu thô có thể ở lại thiết bị, giảm truyền dữ liệu.

Đánh đổi:
- Phần cứng thiết bị đa dạng, tài nguyên hạn chế.
- Phải quản lý model rollout, version và rollback trên nhiều thiết bị.
- Model có thể bị trích xuất hoặc phân tích ngược nếu thiết bị không được bảo vệ.
- Khó quan sát đầy đủ và cập nhật ngay khi có sự cố.

Edge phù hợp khi latency, privacy, offline capability hoặc chi phí truyền dữ liệu quan trọng hơn việc tập trung toàn bộ inference trong cloud.

### 2.5. So sánh các kiểu inference

| Kiểu | Thời gian trả kết quả | Giao diện phổ biến | Điểm mạnh | Rủi ro chính |
|---|---|---|---|---|
| Online | Milliseconds tới vài giây tùy SLO | HTTP/gRPC | Tương tác tức thời | Tail latency và dependency trên critical path |
| Batch | Theo lịch/phút/giờ/ngày | Job, workflow, table/object output | Throughput và hiệu quả xử lý lô | Kết quả trễ, retry/backfill |
| Streaming | Gần thời gian thực | Event stream | Xử lý liên tục, tách producer-consumer | Ordering, duplicate, late event, backpressure |
| Edge | Ngay trên thiết bị hoặc gateway | SDK/runtime local | Latency thấp, offline, ít truyền dữ liệu | Fleet rollout, phần cứng và bảo vệ model |

Không nhất thiết chỉ chọn một kiểu. Một nền tảng có thể dùng online inference cho ranking, batch inference để tạo candidate và streaming để cập nhật feature.

## 3. Kiến trúc logic của model serving

Một dịch vụ inference production thường có nhiều bước hơn lời gọi hàm model:

~~~mermaid
flowchart TB
    CLIENT["Application / API client"] --> GW["API gateway / authentication"]
    GW --> VALID["Request validation"]
    VALID --> FEAT["Feature retrieval / preprocessing"]
    FEAT --> SERVE["Model serving runtime"]
    REG[("Model registry / artifact store")] --> SERVE
    SERVE --> POST["Postprocessing / policy rules"]
    POST --> RESP["Response"]
    SERVE -. "Metrics / traces / logs" .-> OBS["Observability"]
    FEAT -. "Feature freshness / errors" .-> OBS
    GW -. "Access / quota" .-> OBS
~~~

Các thành phần chính:

1. **Ingress/API layer:** nhận request, xác thực caller, quota, rate limit và routing.
2. **Input validation:** kiểm tra schema, kiểu dữ liệu, giới hạn kích thước, giá trị hợp lệ.
3. **Feature retrieval:** đọc feature online hoặc thực hiện preprocessing.
4. **Model runtime:** nạp artifact, thực thi model và quản lý concurrency.
5. **Postprocessing:** chuyển output thành contract nghiệp vụ, áp dụng threshold hoặc policy được phê duyệt.
6. **Response/output:** trả kết quả hoặc ghi prediction.
7. **Observability:** đo latency, throughput, lỗi, resource, feature/model version và chất lượng sau triển khai.
8. **Model registry/artifact store:** quản lý artifact, metadata, lineage và trạng thái được phép deploy.

Không phải mọi use case cần từng service riêng. Một model nhỏ với feature tĩnh có thể chạy trong cùng process với ứng dụng. Tách thành nhiều service giúp scale và ownership độc lập nhưng tăng network hop, chi phí và failure modes.

## 4. Dữ liệu, feature và tính nhất quán train-serving

Một nguyên nhân phổ biến khiến model production kém chất lượng là feature lúc inference khác với feature khi huấn luyện. Đây là vấn đề **training-serving skew**.

Ví dụ model xếp hạng phòng được huấn luyện với:
- Tỷ lệ hủy của người dùng trong 30 ngày.
- Giá trung bình của phòng trong 7 ngày.
- Số lượt tìm kiếm trong 24 giờ.
- Điểm đánh giá gần nhất.

Khi inference, nếu backend tính tỷ lệ hủy từ cửa sổ 7 ngày thay vì 30 ngày, model nhận dữ liệu khác phân phối huấn luyện dù schema không đổi.

### 4.1. Feature pipeline

~~~mermaid
flowchart LR
    SRC["Operational data / events"] --> ETL["Ingestion and transformation"]
    ETL --> OFF[("Offline feature store / lake")]
    ETL --> ON[("Online feature store")]
    OFF --> TRAIN["Training pipeline"]
    TRAIN --> MODEL["Model artifact"]
    ON --> SERVE["Online serving"]
    MODEL --> SERVE
~~~

Offline feature store thường hỗ trợ training và backfill trên dữ liệu lịch sử. Online feature store hỗ trợ đọc nhanh các feature cần cho request. Nếu dùng hai nơi, cần có định nghĩa feature, transformation logic và lineage thống nhất.

### 4.2. Câu hỏi đánh giá feature

- Feature được tính từ nguồn nào và ai sở hữu?
- Transformation có được version hóa không?
- Offline và online dùng chung logic hay có cách kiểm chứng equivalence?
- Timestamp và event-time window có cùng semantics?
- Feature thiếu/null được xử lý như thế nào?
- Feature stale tối đa bao lâu?
- Có thể lấy feature theo cùng thời điểm lịch sử để tránh data leakage không?
- Có phân biệt tenant hoặc quyền truy cập trong feature key không?

### 4.3. Feature freshness và fallback

Nếu online feature store không có feature mới, hệ thống cần policy:
- Dùng giá trị gần nhất nếu freshness budget cho phép.
- Dùng default đã được model validation chấp thuận.
- Gọi nguồn phụ nếu đáp ứng latency.
- Degrade sang model/logic đơn giản hơn.
- Từ chối một số use case nếu thiếu feature bắt buộc.

Không tự đặt giá trị 0 cho mọi feature bị thiếu. Số 0 có thể là giá trị thực và mang ý nghĩa khác với missing. Cần có missing indicator, default theo thiết kế model hoặc behavior fail rõ ràng.

## 5. Model artifact, registry và khả năng tái lập

Model được deploy cần được quản lý như một artifact có version, không phải một file tùy ý tải từ máy của nhà phát triển.

Một model package nên liên kết với:
- Model name và version.
- Framework/runtime và phiên bản dependency.
- Input/output schema.
- Feature definitions/version.
- Training dataset reference và data lineage.
- Code/commit, pipeline run và hyperparameters.
- Evaluation metrics và test reports.
- Model signature và checksum.
- License, provenance và nguồn pretrained model nếu có.
- Trạng thái approval: candidate, staging, production, deprecated hoặc revoked.

Model registry là nơi quản lý metadata và vòng đời model; artifact store giữ file thực tế, container hoặc package. Một registry không tự bảo đảm artifact an toàn hoặc reproducible nếu nguồn dữ liệu, code và dependency không được ghi lại.

### 5.1. Registry và promotion flow

~~~mermaid
flowchart LR
    TRAIN["Training pipeline"] --> EVAL["Evaluation / validation"]
    EVAL --> CAND["Candidate model"]
    CAND --> APPROVE["Review / approval"]
    APPROVE --> STAGE["Staging deployment"]
    STAGE --> PROD["Production promotion"]
    PROD --> MON["Monitor"]
    MON -->|"Drift / regression"| ROLLBACK["Rollback / disable"]
~~~

Chỉ model đã vượt quality, security, compatibility và operational checks mới được promotion. Model version và artifact digest cần bất biến sau khi được phê duyệt; nếu artifact bị thay mà version không đổi, rollback và audit sẽ không còn đáng tin.

### 5.2. Model signature và input contract

Model signature mô tả input/output names, shapes, types hoặc schema. Serving gateway/runtime nên validate request dựa trên contract đã công bố. Khi input schema thay đổi, cần đánh giá consumer, feature pipeline và model compatibility giống như quản lý API.

Không cho consumer gửi tùy ý tên model artifact hoặc đường dẫn file. Model routing nên do server policy/registry quyết định.

## 6. Chọn compute: CPU, GPU và accelerator

Không phải model nào cũng cần GPU. Quyết định cần dựa trên benchmark với model, batch size, input shape, concurrency và SLO thật.

| Loại compute | Trường hợp thường phù hợp | Đánh đổi |
|---|---|---|
| CPU | Model nhỏ, tree-based model, preprocessing, low-throughput inference | Có thể không đạt throughput cho model tensor lớn |
| GPU | Neural network/LLM, phép toán song song lớn, throughput cao | Giá, memory, cold start và utilization |
| Specialized accelerator | Workload được tối ưu cho NPU/TPU hoặc phần cứng chuyên dụng | Khả năng tương thích runtime, porting và phụ thuộc provider |
| Edge device | Inference local, offline hoặc cần giảm latency | Hạn chế tài nguyên, cập nhật fleet và bảo mật thiết bị |

### 6.1. Đo hiệu quả compute

Các chỉ số:
- Predictions/second hoặc requests/second.
- p50/p95/p99 inference latency.
- GPU/CPU utilization.
- Accelerator memory và peak memory.
- Batch size hiệu quả.
- Model load/cold-start time.
- Queueing time và thời gian chờ resource.
- Cost trên 1.000 hoặc 1 triệu prediction.

GPU utilization cao không luôn là tốt: có thể latency tăng do queue dài. Utilization thấp có thể do model nhỏ, batch thấp, input preprocessing là bottleneck hoặc GPU replica dư thừa.

### 6.2. Batching và dynamic batching

Batching gộp nhiều request vào một lần thực thi model, cải thiện throughput trên accelerator. Dynamic batching gom request trong một cửa sổ chờ ngắn.

Đánh đổi:
- Batch lớn tăng hiệu suất compute nhưng có thể tăng latency do chờ đủ batch.
- Batch nhỏ giảm thời gian chờ nhưng không tận dụng hết accelerator.
- Request có shape khác nhau có thể khó batch chung.
- Một request chậm hoặc lớn có thể ảnh hưởng các request khác nếu scheduling không phù hợp.

Chọn max batch size và max queue delay theo SLO. Không tăng batching chỉ để tối ưu throughput nếu p99 latency vượt ngưỡng nghiệp vụ.

## 7. Đo latency, throughput và SLO

Tổng latency online không chỉ là thời gian model predict:

\[
T_{total} = T_{gateway} + T_{auth} + T_{feature} + T_{preprocess} + T_{queue} + T_{model} + T_{postprocess}
\]

Ví dụ mục tiêu minh họa:
- p95 end-to-end dưới 150 ms.
- p99 dưới 300 ms.
- Error rate dưới ngưỡng được thống nhất.
- Throughput peak có headroom cho burst.
- Feature freshness dưới một giới hạn đã xác định.

Mỗi thành phần nên có latency budget. Nếu model compute chỉ chiếm 20 ms nhưng feature lookup mất 120 ms, đổi GPU nhanh hơn có thể không cải thiện trải nghiệm.

### 7.1. SLO và error budget

SLO nên mô tả kết quả người dùng cảm nhận, không chỉ trạng thái container:
- Tỷ lệ request hợp lệ có response trong deadline.
- Tỷ lệ dự đoán trả về schema đúng.
- Tỷ lệ request được phục vụ bởi phiên bản model được phê duyệt.
- Freshness của feature hoặc prediction output.
- Batch job hoàn thành trước deadline và đủ coverage.

Error budget giúp quyết định tốc độ phát hành model mới. Nếu dịch vụ tiêu hết budget do lỗi/latency, có thể tạm dừng rollout để tập trung độ tin cậy.

### 7.2. Tail latency

p50 tốt không đủ nếu p99 quá cao. Tail latency thường tăng do:
- Feature lookup chậm ở một partition.
- GPU contention/queueing.
- Cold start và model load.
- Autoscaling chưa kịp.
- GC, memory pressure hoặc noisy neighbor.
- Dependency ngoài bị throttling.

Đo phân vị trên toàn request path và theo model version, instance type, region và loại input.

## 8. Scaling và capacity planning

### 8.1. Horizontal scaling

Tăng số replica để xử lý nhiều request. Phù hợp khi request độc lập và model runtime có thể chạy song song. Cần xem:
- Thời gian khởi động và nạp model.
- Kích thước artifact và tốc độ tải từ registry.
- Thời gian cấp GPU/accelerator.
- Readiness: chỉ nhận traffic sau khi model/feature/runtime sẵn sàng.
- Session/state trong process có làm request không thể phân phối tự do không?
- Autoscaling signal là CPU, GPU, concurrency, queue depth hay request latency?

CPU-based autoscaling có thể không phản ánh bottleneck GPU. Queue depth/concurrency hoặc accelerator metrics có thể hữu ích hơn, tùy runtime.

### 8.2. Vertical scaling

Dùng instance lớn hơn, nhiều memory/CPU/GPU hơn. Có thể phù hợp model lớn không chia được hoặc giảm số replica. Đánh đổi là giới hạn size, giá mỗi node, blast radius và khả năng cấp phát.

### 8.3. Scale-to-zero

Với workload dev, batch hoặc endpoint ít dùng, scale-to-zero có thể tiết kiệm chi phí. Nhưng request đầu tiên phải chờ startup/model load. Không phù hợp endpoint có SLO latency nghiêm ngặt trừ khi có warm pool, min replica hoặc fallback.

### 8.4. Capacity planning

Ước lượng capacity dựa trên benchmark:
1. Đo throughput mỗi replica ở latency mục tiêu.
2. Xác định peak request rate và headroom.
3. Tính replica cần thiết theo peak cùng mức dự phòng.
4. Thử mất một replica/zone để xác định capacity sau failure.
5. Tính thời gian autoscale từ trigger tới ready.
6. Kiểm tra quota GPU/accelerator và thời gian cấp tài nguyên.
7. Load test cả model warm và cold.
8. Định kỳ đối chiếu demand thực tế và chi phí.

Không giả định autoscaling phản ứng tức thời. Nếu traffic có burst nhanh hơn thời gian tạo replica, cần baseline capacity, queue hoặc admission control.

## 9. Độ tin cậy và failure handling

Model serving phụ thuộc nhiều thành phần: gateway, identity, feature store, registry/artifact store, container registry, network, runtime và downstream. Thiết kế cần chỉ ra behavior khi từng thành phần lỗi.

| Lỗi | Ảnh hưởng | Phương án giảm tác động |
|---|---|---|
| Model process crash | Request thất bại | Health check, restart, nhiều replica và rollout an toàn |
| Artifact store không truy cập được | Replica mới không nạp model | Cache artifact đã kiểm duyệt, warm deployment, giữ phiên bản đang chạy |
| Feature store chậm | End-to-end latency tăng | Timeout, feature cache có policy, default/fallback |
| GPU quota hết | Không scale được | Capacity reservation, CPU fallback nếu đạt chất lượng/SLO, queue |
| Model trả NaN/invalid output | Kết quả sai | Output validation, circuit breaker theo model, fallback |
| Một model version regression | Business KPI giảm | Canary, traffic split, rollback nhanh |
| Network partition | Inference dependency unavailable | Multi-zone, timeout, retry giới hạn |
| Traffic burst | Queue dài và p99 tăng | Autoscaling, admission control, rate limit, graceful degradation |

### 9.1. Fallback strategy

Fallback phải được product owner và model owner duyệt. Ví dụ:
- Model ranking lỗi thì trả ranking theo popularity/rule-based.
- Recommendation lỗi thì hiển thị danh mục mặc định.
- Risk score lỗi thì đưa giao dịch vào quy trình review thay vì tự động cho phép.
- Model classification lỗi thì trả trạng thái “chưa xác định” để xử lý tiếp.

Không dùng fallback tự động cho mọi quyết định. Với lĩnh vực nhạy cảm, fallback “cho phép” có thể tăng rủi ro; fallback “từ chối” có thể gây thiệt hại người dùng. Cần phân biệt fail-open và fail-closed theo nghiệp vụ.

### 9.2. Timeout và retry

Đặt deadline end-to-end; mỗi dependency phải nhận timeout nhỏ hơn phần ngân sách còn lại. Retry chỉ cho lỗi transient, có giới hạn và exponential backoff/jitter. Không retry đồng thời ở gateway, application, feature client và model client mà không có retry budget, vì một request gốc có thể tạo nhiều lần gọi.

Inference thường là tác vụ đọc/compute, nhưng downstream side effect hoặc ghi prediction cần idempotency nếu client retry.

## 10. Triển khai model: canary, shadow và rollback

Model mới có thể khác behavior dù API contract không đổi. Vì vậy, phát hành model cần kiểm tra cả kỹ thuật lẫn chất lượng.

### 10.1. Shadow deployment

Request production được gửi tới model hiện tại để trả kết quả; đồng thời một bản sao request được gửi tới model mới nhưng kết quả mới không ảnh hưởng người dùng. So sánh output, latency, resource và phân phối dự đoán.

Cần loại bỏ/che dữ liệu nhạy cảm, tránh side effect và bảo đảm shadow traffic không làm quá tải nguồn.

### 10.2. Canary rollout

Chuyển một phần nhỏ traffic tới model mới, quan sát error, latency và business metrics; sau đó tăng dần nếu đạt tiêu chí. Traffic split nên có khả năng phân tầng theo tenant, request type hoặc cohort; tránh chỉ dựa vào một tỷ lệ tổng thể nếu các nhóm có phân phối khác nhau.

### 10.3. A/B test

A/B test so sánh tác động nghiệp vụ giữa các model/strategy qua nhóm người dùng được phân bổ. Cần thiết kế experiment để tránh leakage, sample ratio mismatch, bias, và đảm bảo metric có ý nghĩa. A/B test đo outcome trong bối cảnh sử dụng; nó không thay thế load test hoặc security test.

### 10.4. Rollback

Rollback cần:
- Model artifact trước đó còn tồn tại và đã kiểm tra.
- Runtime tương thích với artifact cũ.
- Feature schema vẫn hỗ trợ model cũ.
- Traffic routing có thể chuyển lại nhanh.
- Output/state đã ghi từ model mới được xử lý theo policy.
- Registry ghi lại model version được rollback và lý do.
- Có thể disable một model hoặc route mà không cần deploy lại toàn ứng dụng.

Không xóa artifact cũ ngay sau promotion nếu còn trong rollback window.

## 11. Bảo mật và quản trị model/data

Model serving có thể nhận PII, prompt, hình ảnh, văn bản, dữ liệu thanh toán hoặc feature nhạy cảm. Cần bảo vệ cả input, output, artifact và quyền thực thi.

### Identity và authorization

- Service caller dùng identity riêng; không dùng một credential admin chung.
- Model endpoint chỉ cho principal được phép gọi.
- Model registry/artifact store có quyền publish, approve, deploy và read tách biệt.
- Pipeline training không mặc nhiên có quyền deploy production.
- Runtime không nên có quyền sửa registry hoặc IAM nếu không cần.
- Quản lý secret theo workload identity/secret manager; tránh nhúng key trong image.

### Data protection

- Mã hóa data in transit và at rest.
- Tối thiểu hóa input gửi tới inference service.
- Redact dữ liệu nhạy cảm trong log/trace.
- Kiểm soát retention của request/response sample.
- Tách tenant và namespace cache/feature.
- Kiểm tra data residency và quy định xử lý dữ liệu phù hợp.

### Model artifact và supply chain

- Quét dependency và container image.
- Kiểm tra nguồn artifact và checksum/signature.
- Giới hạn ai được upload hoặc promote model.
- Ghim dependency/runtime version và tạo SBOM khi quy trình yêu cầu.
- Không nạp model artifact không tin cậy nếu framework hỗ trợ serialization có thể thực thi code.
- Quản lý license và provenance của pretrained model/dataset.

### Model abuse và output control

Tùy use case, cần bảo vệ endpoint khỏi prompt injection, adversarial input, model extraction, abuse hoặc inference data leakage. Áp dụng request size/rate limits, authorization, input validation, policy kiểm tra output và monitoring bất thường. Với mô hình sinh nội dung, cần thêm guardrails phù hợp use case, kiểm tra đầu ra và quy trình xử lý nội dung nguy hại.

## 12. Observability: hạ tầng, model và nghiệp vụ

Chỉ giám sát CPU, memory và HTTP status là chưa đủ. Một model có thể trả 200 OK nhưng dự đoán sai hoặc feature stale.

### 12.1. Ba lớp quan sát

**Hạ tầng/runtime**
- Replica ready, restart, CPU/GPU utilization và memory.
- Queue depth, concurrency và throttling.
- Artifact load time, cold start và network error.
- Autoscaling event, quota và node capacity.

**Serving/API**
- Request count, p50/p95/p99 latency.
- Timeout, 4xx/5xx và validation failure.
- Input size, batch size, model version.
- Feature lookup latency/miss/staleness.
- Inference compute time và postprocessing time.

**Model/business**
- Prediction distribution và score distribution.
- Tỷ lệ null/NaN/out-of-range.
- Feature drift và data drift.
- Model quality khi ground truth đến sau.
- Business KPI, conversion, false positive/negative hoặc ranking quality.
- Bias/fairness metric nếu phù hợp mục tiêu và quy định.

Không phải mọi use case đều có ground truth ngay. Với dự đoán rủi ro hoặc churn, nhãn thật có thể đến sau nhiều ngày/tháng. Khi đó cần theo dõi proxy metrics và ghi lineage để đánh giá offline khi label đã có.

### 12.2. Data drift và concept drift

- **Data drift:** phân phối input/feature thay đổi so với dữ liệu dùng để xây dựng/đánh giá model.
- **Concept drift:** mối quan hệ giữa feature và target thay đổi theo thời gian, làm model giảm chất lượng ngay cả khi input distribution chưa đổi mạnh.

Monitoring drift không tự chứng minh model đã suy giảm. Cần kết hợp ground truth, domain metrics và review. Một thay đổi mùa vụ có thể là drift hợp lệ; trigger retraining tự động không kiểm soát có thể làm chất lượng xấu hơn.

### 12.3. Trace correlation

Gắn correlation/trace ID giữa API nghiệp vụ, feature lookup và inference endpoint để thấy latency từng chặng. Không ghi raw request/response nhạy cảm. Ghi model version, feature schema version và deployment revision dạng metadata đã được kiểm soát.

## 13. Quản lý vòng đời model và MLOps

Model serving không đứng riêng khỏi quá trình phát triển model. Cần kết nối training, evaluation, registry, deployment và monitoring.

~~~mermaid
flowchart LR
    DATA["Data ingestion / quality"] --> FEAT["Feature engineering"]
    FEAT --> TRAIN["Training"]
    TRAIN --> EVAL["Evaluation / validation"]
    EVAL --> REG[("Model registry")]
    REG --> DEPLOY["Deploy pipeline"]
    DEPLOY --> SERVE["Model serving"]
    SERVE --> MON["Monitor predictions / drift"]
    MON --> REVIEW["Review / retrain decision"]
    REVIEW --> DATA
~~~

Một quy trình MLOps trưởng thành nên có:
1. Data validation và lineage.
2. Version code, dataset/feature definition và training config.
3. Reproducible training hoặc ghi rõ giới hạn tái lập.
4. Evaluation theo holdout/time split phù hợp.
5. Model approval và registry.
6. Image/artifact scan và deployment policy.
7. Canary/shadow/rollback.
8. Monitoring infrastructure, data drift và business quality.
9. Retraining schedule/trigger có review.
10. Xóa/deprecate model và artifact theo retention policy.

Không tự động retrain chỉ vì drift metric vượt ngưỡng. Cần xác định nguyên nhân, chất lượng label, data pipeline và tiêu chí promotion. Một model mới chỉ được đưa vào production sau khi qua cùng cổng kiểm tra.

## 14. Chi phí và hiệu quả sử dụng tài nguyên

Chi phí ML serving có thể gồm:
- CPU/GPU/accelerator uptime.
- RAM, storage và model artifact egress.
- Online feature store/cache và database.
- Network traffic giữa region/zone.
- Log, trace, metric và prediction archive.
- Batch job, training pipeline và data processing.
- Idle capacity để đáp ứng latency SLO.
- License hoặc dịch vụ model API bên ngoài.

### Chỉ số unit economics

Có thể theo dõi:
- Cost per 1.000 predictions.
- Cost per successful request.
- GPU-seconds per prediction.
- Cost per batch record.
- Cost of idle replica.
- Cost per tenant/use case.
- Tỷ lệ request phải fallback hoặc retry.

Tối ưu có thể gồm quantization, model distillation, pruning, compilation, dynamic batching, shared model instance, scale-to-zero cho batch, spot/preemptible compute cho tác vụ có thể retry, hoặc dùng CPU cho model nhỏ.

Mỗi kỹ thuật có thể làm thay đổi quality, latency hoặc complexity. Đo chất lượng sau tối ưu; không giảm precision/recall hoặc reliability chỉ để đạt chi phí thấp nếu nghiệp vụ không chấp nhận.

## 15. Đánh giá kiến trúc theo Well-Architected

| Khía cạnh | Câu hỏi đánh giá | Dấu hiệu/bằng chứng |
|---|---|---|
| **Vận hành xuất sắc** | Có model registry, runbook, ownership, promotion và rollback? | Model lineage, deployment log, release checklist |
| **Bảo mật** | Identity, data access, artifact provenance và PII có được kiểm soát? | IAM review, encryption, artifact scan, audit |
| **Độ tin cậy** | Model/feature/registry lỗi thì có fallback, multi-zone và recovery? | Failure injection, SLO, rollback drill |
| **Hiệu quả hiệu năng** | Latency budget, batching, compute và feature lookup có đạt? | p95/p99, throughput, GPU utilization |
| **Tối ưu chi phí** | Resource có được right-size và scale theo demand? | Cost per prediction, idle capacity, utilization |
| **Bền vững** | Có giảm compute không cần thiết, model/artifact cũ và telemetry thừa? | Lifecycle policy, scale-to-zero, retention review |

### Đánh đổi thường gặp

**GPU hay CPU:** GPU có thể tăng throughput cho neural network lớn nhưng chi phí và cold start cao. CPU phù hợp model nhỏ, tree-based hoặc preprocessing nhưng có thể cần nhiều replica cho workload lớn. Benchmark end-to-end quyết định.

**Online hay batch:** Online giảm thời gian chờ người dùng nhưng đòi availability và latency SLO cao. Batch rẻ và hiệu quả cho công việc không cần tức thời nhưng chấp nhận kết quả trễ.

**Feature lookup realtime hay precompute:** Realtime tăng freshness nhưng thêm network dependency; precompute giảm latency và tải nhưng feature stale hơn. Có thể kết hợp một nhóm feature realtime với phần còn lại precomputed.

**Một endpoint cho mọi model hay endpoint riêng:** Dùng chung giảm hạ tầng nhưng gây noisy neighbor và khó độc lập scaling; tách riêng tăng isolation nhưng tăng cost/ops.

**Scale-to-zero hay minimum replicas:** Scale-to-zero tiết kiệm khi idle nhưng cold start có thể vượt SLO. Minimum replicas tăng chi phí nhưng giữ latency ổn định.

**Canary hay full rollout:** Canary giảm blast radius nhưng cần telemetry đủ tốt và routing phức tạp hơn. Full rollout đơn giản hơn nhưng có thể tác động toàn bộ traffic trước khi phát hiện regression.

## 16. Quy trình review kiến trúc model serving

Một design review có thể đi theo các bước:

1. **Mô tả quyết định nghiệp vụ:** model tạo output gì, ai sử dụng, lỗi dự đoán gây hậu quả nào?
2. **Chọn inference mode:** online, batch, streaming, edge hoặc kết hợp.
3. **Định nghĩa SLO:** latency phân vị, throughput, availability, freshness và output correctness.
4. **Vẽ request/data flow:** gateway, identity, feature, model runtime, artifact, output và telemetry.
5. **Kiểm tra data/feature:** lineage, schema, train-serving consistency, missing value và drift.
6. **Kiểm tra model lifecycle:** registry, signature, version, approval, artifact provenance và rollback.
7. **Benchmark compute:** CPU/GPU, batch, concurrency, memory, cold start và cost.
8. **Kiểm tra scale:** autoscaling signal, quota, warm capacity, burst, zone failure và queue.
9. **Kiểm tra failure mode:** dependency outage, model invalid output, timeout, fallback và retry budget.
10. **Kiểm tra security:** identity, tenant isolation, encryption, data retention, model supply chain.
11. **Thiết kế observability:** infrastructure, serving, feature, model quality và business metrics.
12. **Tính unit economics:** cost per prediction/use case và chi phí idle/recovery.
13. **Kiểm chứng:** load test, failure injection, shadow/canary, contract test và rollback drill.
14. **Ghi ADR:** lựa chọn, phương án loại trừ, lý do, đánh đổi, owner và điều kiện xem xét lại.

### Checklist kiến trúc ngắn

| Hạng mục | PASS khi |
|---|---|
| Workload profile | Có traffic, payload, latency và freshness được đo/ước lượng có cơ sở |
| Inference mode | Online/batch/stream/edge phù hợp với thời gian nghiệp vụ cần |
| Feature consistency | Training-serving schema/transform được version và kiểm chứng |
| Model artifact | Registry, provenance, checksum và approval rõ |
| Runtime capacity | Benchmark trên phần cứng gần production và có headroom |
| SLO | Có latency/error/availability/freshness target và dashboard |
| Resilience | Có timeout, bounded retry, fallback, multi-zone hoặc recovery |
| Release | Có canary/shadow, model version và rollback |
| Security | Identity, least privilege, encryption và data handling rõ |
| Operations | Owner, runbook, alert và incident process |
| Cost | Unit cost và idle capacity được đo |
| Governance | Có lineage, retention, approval và review định kỳ |

## 17. ADR minh họa — Phục vụ model ranking cho Booking API

> **Bối cảnh:** Booking API cần xếp hạng kết quả tìm kiếm trong thời gian người dùng chờ trang. Traffic đạt đỉnh theo giờ, model cần feature hành vi và giá. Model mới phát hành vài tuần một lần.
>
> **Phương án A:** Nhúng model vào Booking API. Ít network hop và đơn giản khi deploy cùng ứng dụng, nhưng model scaling gắn với API, tăng kích thước image và khó rollback độc lập.
>
> **Phương án B:** Tách model serving thành endpoint riêng, backend lấy feature và gọi inference qua private network. Có thể scale/rollout model độc lập, nhưng thêm network hop, service dependency và chi phí runtime.
>
> **Quyết định minh họa:** Chọn B nếu benchmark xác nhận p95 end-to-end đạt SLO và traffic đủ lớn để quản lý model độc lập. Endpoint có ít nhất capacity nền để tránh cold start; feature lookup có timeout/fallback; model version được pin trong deployment metadata.
>
> **Resilience:** Nếu endpoint lỗi hoặc vượt deadline, trả ranking theo rule/popularity đã được product owner duyệt; không chặn toàn bộ tìm kiếm.
>
> **Release:** Shadow model mới, so sánh score/latency, canary theo cohort rồi tăng traffic; giữ model cũ để rollback.
>
> **Security:** Private endpoint, workload identity cho Booking API, giới hạn quyền đọc feature và model artifact; log không chứa PII raw.
>
> **Kiểm chứng:** Load test peak, p95/p99, GPU/CPU utilization, feature freshness, fallback rate, canary business KPI, tenant isolation và rollback drill.
>
> **Điều kiện xem xét lại:** Traffic giảm, model nhỏ và endpoint network trở thành bottleneck; khi đó cân nhắc in-process inference hoặc batch/precomputed ranking.

## 18. Bài tập thực hành: chọn kiến trúc suy luận cho nền tảng đặt chỗ

Nền tảng cần ba chức năng:
1. Ranking kết quả tìm kiếm cần phản hồi nhanh.
2. Dự báo nhu cầu theo khu vực mỗi ngày.
3. Chấm điểm rủi ro khi booking được tạo để chuyển một số giao dịch sang review.

Nhóm đề xuất dùng một GPU endpoint cho cả ba. Model và feature được lưu trong cùng một bucket; endpoint trả kết quả 200 khi runtime hoạt động. Chưa có fallback, model version, drift monitoring hoặc cost per prediction.

**Yêu cầu:**
1. Chọn inference mode riêng cho ranking, demand forecasting và risk scoring.
2. Xác định latency, throughput, availability và freshness SLO phù hợp từng use case.
3. Vẽ data/feature/model flow và xác định source of truth.
4. Đánh giá có nên dùng chung GPU endpoint hay tách deployment.
5. Thiết kế fallback khi ranking/risk model lỗi.
6. Đề xuất registry, artifact version, approval, canary và rollback.
7. Xác định metric hạ tầng, serving, feature và model quality.
8. Viết security controls cho input, output, model artifact và tenant.
9. Tính cost per prediction và đề xuất tối ưu compute.
10. Lập kế hoạch test cho burst traffic, feature outage, GPU quota và model regression.

### Hướng giải quyết

- Ranking là online inference vì kết quả nằm trên critical path của tìm kiếm; cần p95/p99 latency, warm capacity và fallback ranking.
- Demand forecasting phù hợp batch theo lịch; ghi output có version và timestamp để dashboard đọc, hỗ trợ retry/backfill theo partition.
- Risk scoring có thể online hoặc streaming tùy quyết định cần ngay trước khi xác nhận booking; nếu cần tức thời, đặt deadline rõ và fallback sang review/manual policy thay vì tự động chấp nhận khi model lỗi.
- Không mặc định dùng chung một GPU endpoint. Benchmark từng model; dùng CPU cho model nhẹ hoặc batch khi phù hợp, tách endpoint khi SLO, resource profile hoặc blast radius khác nhau.
- Model registry ghi artifact, schema, feature version, lineage và evaluation; deployment chỉ lấy model được phê duyệt.
- Shadow/canary trước full rollout; giữ model cũ và feature compatibility để rollback.
- Theo dõi p95/p99, throughput, errors, GPU/CPU/memory, queue depth, cold start, feature freshness, drift, prediction distribution và business KPI.
- Dùng workload identity, private endpoint, encryption, least privilege, input validation, log redaction và retention phù hợp.
- So sánh cost per 1.000 predictions, utilization, idle replicas, feature lookup và data egress; tối ưu batching/quantization chỉ sau khi đo quality và latency.
- Failure test phải xác minh fallback và quy trình nghiệp vụ thực tế, không chỉ kiểm tra endpoint trả status code.

### Câu hỏi tự kiểm tra

1. Vì sao model accuracy tốt trong offline evaluation chưa đủ chứng minh kiến trúc production tốt?
2. Online, batch, streaming và edge inference khác nhau ở đâu?
3. Latency end-to-end gồm những thành phần nào ngoài model compute?
4. Training-serving skew xảy ra khi nào và làm sao phát hiện?
5. Vì sao model artifact cần registry, digest và provenance?
6. Khi nào CPU hợp lý hơn GPU dù model là neural network?
7. Dynamic batching cải thiện throughput nhưng có thể làm xấu chỉ số nào?
8. Vì sao autoscaling GPU có thể không phản ứng đủ nhanh với traffic burst?
9. Shadow deployment khác canary và A/B testing như thế nào?
10. Vì sao HTTP 200 không chứng minh model đang tạo dự đoán có chất lượng?
11. Khi feature store lỗi, fallback nào có thể an toàn tùy use case?
12. Những chỉ số nào giúp chứng minh chi phí trên mỗi prediction đang giảm mà quality vẫn được giữ?

Một kiến trúc phục vụ máy học tốt không chỉ làm cho model chạy được. Nó phải **đáp ứng đúng kiểu workload, cung cấp feature nhất quán, nạp artifact có nguồn gốc rõ, đạt SLO trên phần cứng phù hợp, phục hồi khi dependency lỗi và đo được chất lượng lẫn chi phí trong production**. Đánh giá theo toàn bộ vòng đời giúp nhóm lựa chọn được mức độ tách service, compute và kiểm soát vận hành phù hợp với giá trị nghiệp vụ thực tế.
