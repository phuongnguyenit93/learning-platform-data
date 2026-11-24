# Chạy thử nhiều replica, dựng dashboard và viết báo cáo phục hồi

## Mục tiêu của bài thực hành

Một ứng dụng Spring Cloud CircuitBreaker thường chạy nhiều replica để phục vụ lưu lượng và tăng khả năng sẵn sàng. Mỗi replica là một tiến trình riêng, vì vậy Resilience4j CircuitBreaker mặc định giữ trạng thái và sliding window trong bộ nhớ của từng JVM. Pod A có thể đang OPEN trong khi pod B và C vẫn CLOSED. Nếu chỉ xem một dashboard tổng hợp mà không giữ nhãn pod, nhóm vận hành có thể hiểu sai phạm vi sự cố.

Bài thực hành này xây dựng một môi trường có nhiều replica của order-service, tạo lỗi có kiểm soát trên một replica, quan sát trạng thái breaker theo từng pod, dựng dashboard và ghi lại quá trình phục hồi. Mục tiêu là chứng minh được đường đi từ lỗi phụ thuộc đến quyết định OPEN, hành vi fallback, các lần thử HALF_OPEN và trạng thái ổn định sau phục hồi.

Sau khi hoàn thành, bạn có thể:

- Triển khai nhiều replica của một ứng dụng Spring Cloud có circuit breaker.
- Giải thích vì sao mỗi replica có trạng thái breaker và sliding window riêng.
- Tạo lỗi có kiểm soát trên một replica để so sánh với các replica còn lại.
- Thu thập metric từ từng pod bằng Actuator, Micrometer và Prometheus.
- Dựng dashboard thể hiện trạng thái, failure rate, slow call rate, lời gọi bị từ chối và fallback.
- Phân biệt trạng thái của từng pod với sức khỏe tổng thể của dịch vụ phụ thuộc.
- Theo dõi một chu kỳ CLOSED → OPEN → HALF_OPEN → CLOSED.
- Viết báo cáo phục hồi có dữ liệu, mốc thời gian và hành động tiếp theo.

## 1. Kiến trúc môi trường thực hành

Dùng hai ứng dụng:

- **order-service:** gọi inventory-service qua một gateway được bảo vệ bằng Spring Cloud CircuitBreaker và Resilience4j.
- **inventory-service:** cung cấp API tra cứu tồn kho và hỗ trợ chế độ fault injection chỉ bật trong môi trường thực hành.

Triển khai ba replica order-service và ít nhất hai replica inventory-service. Một Kubernetes Service định tuyến request đến các pod inventory. Mỗi pod order có một CircuitBreakerRegistry trong bộ nhớ tiến trình riêng.

    Client
      |
      v
    order-service (Kubernetes Service)
      |
      +----------------+----------------+
      |                |                |
      v                v                v
    order-0          order-1          order-2
    breaker-local    breaker-local    breaker-local
      |                |                |
      +----------------+----------------+
                       |
                       v
             inventory-service (Service)
                       |
                +------+------+
                |             |
                v             v
             inventory-0  inventory-1

Mỗi order pod có thể tạo ra một trạng thái khác nhau:

| Replica | Trạng thái breaker ví dụ | Ý nghĩa |
| --- | --- | --- |
| order-0 | OPEN | Các lời gọi từ replica này gặp lỗi đủ ngưỡng. |
| order-1 | CLOSED | Các lời gọi từ replica này vẫn thành công. |
| order-2 | CLOSED | Các lời gọi từ replica này vẫn thành công. |

Trạng thái OPEN của order-0 không tự động mở breaker trong order-1 hoặc order-2. Kubernetes Service cũng không tự loại order-0 khỏi danh sách nhận request chỉ vì breaker outbound của pod đó OPEN. Circuit breaker bảo vệ lời gọi đi từ order-service đến inventory-service; readiness của order-service là một quyết định khác.

## 2. Chuẩn bị cấu hình CircuitBreaker và metric

Dùng một breaker id ổn định, chẳng hạn inventory-read. Mỗi replica sẽ tạo breaker cùng tên nhưng giữ trạng thái riêng trong JVM của nó.

Ví dụ application.yml dành cho môi trường lab:

    resilience4j:
      circuitbreaker:
        instances:
          inventory-read:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 10
            minimumNumberOfCalls: 6
            failureRateThreshold: 50
            slowCallDurationThreshold: 800ms
            slowCallRateThreshold: 60
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 2
            automaticTransitionFromOpenToHalfOpenEnabled: true

Các giá trị nhỏ giúp quan sát chuyển trạng thái nhanh trong bài thực hành. Không sao chép nguyên cấu hình này sang production khi chưa đánh giá lưu lượng, SLO và đặc tính của inventory-service.

Cấu hình Actuator và Prometheus:

    management:
      endpoints:
        web:
          exposure:
            include: health,info,metrics,prometheus
      endpoint:
        health:
          show-details: never
      metrics:
        tags:
          application: order-service

Dependency cần có tùy phiên bản Spring Boot và cách tích hợp:

- Spring Boot Actuator.
- Micrometer registry cho Prometheus.
- Resilience4j Micrometer integration nếu starter hiện tại chưa tự cấu hình binder.
- Spring Cloud CircuitBreaker Resilience4j starter phù hợp với release train của dự án.

Xác nhận endpoint `/actuator/prometheus` thực sự trả metric circuit breaker. Tên metric và tag được chuẩn hóa theo phiên bản Resilience4j/Micrometer; hãy kiểm tra dữ liệu xuất ra trước khi viết truy vấn dashboard.

Metric thường cần quan sát gồm:

- Trạng thái breaker theo name và state.
- Số lời gọi theo kết quả successful, failed, ignored hoặc not permitted.
- Failure rate và slow call rate.
- Số lời gọi bị từ chối khi breaker OPEN.
- Thời lượng lời gọi và độ trễ của inventory-service.
- Số lần fallback theo nguyên nhân.
- Số lần chuyển trạng thái, nếu ứng dụng phát event thành custom counter.

## 3. Triển khai nhiều replica

Ví dụ Kubernetes Deployment cho order-service:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: order-service
    spec:
      replicas: 3
      selector:
        matchLabels:
          app: order-service
      template:
        metadata:
          labels:
            app: order-service
          annotations:
            prometheus.io/scrape: "true"
            prometheus.io/path: "/actuator/prometheus"
            prometheus.io/port: "8080"
        spec:
          containers:
            - name: order-service
              image: example/order-service:lab
              ports:
                - name: http
                  containerPort: 8080
              env:
                - name: SPRING_PROFILES_ACTIVE
                  value: lab
              readinessProbe:
                httpGet:
                  path: /actuator/health/readiness
                  port: http
                initialDelaySeconds: 10
                periodSeconds: 5

Service cho order-service:

    apiVersion: v1
    kind: Service
    metadata:
      name: order-service
    spec:
      selector:
        app: order-service
      ports:
        - name: http
          port: 8080
          targetPort: http

Inventory-service cũng cần được triển khai với nhiều replica và Service DNS ổn định:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: inventory-service
    spec:
      replicas: 2
      selector:
        matchLabels:
          app: inventory-service
      template:
        metadata:
          labels:
            app: inventory-service
        spec:
          containers:
            - name: inventory-service
              image: example/inventory-service:lab
              ports:
                - name: http
                  containerPort: 8080

    ---
    apiVersion: v1
    kind: Service
    metadata:
      name: inventory-service
    spec:
      selector:
        app: inventory-service
      ports:
        - name: http
          port: 8080
          targetPort: http

Các manifest là khung minh họa; thay image, namespace, resource limit, secret và probe theo môi trường thực tế. Không khai báo container name cố định hoặc cấu hình khiến không thể scale replica. Mỗi pod cần có nhãn nhận diện để Prometheus và log phân biệt được nguồn metric.

Triển khai và kiểm tra:

    kubectl apply -f inventory-deployment.yml
    kubectl apply -f order-deployment.yml
    kubectl get pods -l app=order-service -o wide
    kubectl get pods -l app=inventory-service -o wide
    kubectl get endpoints inventory-service

Kết quả cần có ba pod order ở trạng thái Ready và ít nhất hai endpoint inventory khả dụng. Nếu chưa đủ replica hoặc readiness chưa đạt, xử lý trước khi bắt đầu tạo tải lỗi.

## 4. Tạo lỗi có kiểm soát trên một replica

Để thấy trạng thái breaker khác nhau giữa các pod, cần làm cho một replica order nhận kết quả lỗi có chủ đích trong khi các replica còn lại gọi inventory bình thường.

Một cách thực hành là thêm fault injection chỉ trong profile lab:

- Request từ order-service có header `X-Lab-Fault: always-fail` sẽ được inventory-service lab trả HTTP 503.
- Request không có header đó được xử lý bình thường.
- Chỉ dùng header này trong namespace lab; không bật hoặc tin cậy nó trong production.
- Gateway chuyển header từ request thử nghiệm đến lời gọi inventory chỉ trong profile lab.

Ví dụ phía inventory-service:

    @GetMapping("/inventory/{sku}")
    public InventoryResponse find(
            @PathVariable String sku,
            @RequestHeader(
                value = "X-Lab-Fault",
                required = false
            ) String faultMode) {

        if ("always-fail".equals(faultMode)) {
            throw new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Lab fault injection"
            );
        }

        return inventoryRepository.find(sku);
    }

Ví dụ phía order-service có thể truyền header trong Feign request interceptor hoặc WebClient filter dành riêng cho profile lab. Không cho phép client bên ngoài tùy ý bật fault injection trên môi trường thật.

Để gửi request trực tiếp đến từng order pod, lấy tên pod:

    kubectl get pods -l app=order-service

Sau đó mở port-forward đến một pod cụ thể:

    kubectl port-forward pod/<order-pod-name> 18080:8080

Gửi request đến pod đang được forward. Với pod mục tiêu, thêm header fault injection; với pod còn lại, gửi request bình thường. Lặp lại port-forward theo từng pod để giữ rõ replica nào đang nhận request.

Ví dụ:

    curl -H "X-Lab-Fault: always-fail"       http://localhost:18080/api/inventory/SKU-42

    curl http://localhost:18080/api/inventory/SKU-42

Nếu gateway dùng header khác hoặc endpoint khác, điều chỉnh theo API của lab. Điểm quan trọng là request được gửi trực tiếp đến một pod order xác định và fault chỉ được áp dụng cho lời gọi downstream từ pod đó.

## 5. Kích hoạt OPEN trên một pod và so sánh các pod khác

Với cấu hình lab có minimumNumberOfCalls bằng 6 và failureRateThreshold bằng 50, gửi đủ lời gọi lỗi đến order-0 để vượt ngưỡng. Cần tính cả số mẫu thực tế mà breaker ghi nhận; không giả định một request lỗi luôn tương ứng đúng một sample nếu có retry hoặc wrapper khác.

Quy trình:

1. Port-forward đến order-0.
2. Gửi liên tiếp các request có header fault injection.
3. Đọc metric hoặc event của order-0 sau mỗi nhóm request.
4. Xác nhận failure rate đạt ngưỡng sau khi đủ mẫu và breaker chuyển OPEN.
5. Tiếp tục gửi request đến order-0; xác nhận breaker từ chối nhanh và fallback chạy.
6. Port-forward đến order-1 và order-2.
7. Gửi request không có fault header; xác nhận hai pod này vẫn gọi inventory và breaker của chúng vẫn CLOSED.

Kết quả mong đợi:

| Pod | Request gửi đến pod | Trạng thái breaker | Hành vi |
| --- | --- | --- | --- |
| order-0 | Có fault header, đủ số mẫu lỗi | OPEN | Các lời gọi tiếp theo bị từ chối trước khi gọi inventory. |
| order-1 | Không có fault header | CLOSED | Lời gọi inventory thành công. |
| order-2 | Không có fault header | CLOSED | Lời gọi inventory thành công. |

Nếu cả ba pod cùng OPEN, hãy kiểm tra fault injection có đang áp dụng cho toàn bộ request, request có thực sự được gửi trực tiếp đến từng pod hay đang đi qua Service chung, và metric có đang bị tổng hợp mất nhãn pod không.

Khi truy cập qua Service order-service bình thường, request có thể được phân phối đến bất kỳ replica nào. Nếu một pod đang OPEN, người dùng chỉ được route đến pod đó có thể nhận fallback trong khi request khác đi đến pod CLOSED vẫn thành công. Đây là một phần quan trọng của hành vi multi-replica cần được thể hiện trên dashboard.

## 6. Xác minh mỗi replica có sliding window riêng

Resilience4j CircuitBreaker mặc định giữ state machine và sliding window trong bộ nhớ tiến trình. Không có cơ chế tự đồng bộ trạng thái breaker giữa các JVM chỉ vì chúng cùng dùng một breaker name.

Điều đó có nghĩa:

- order-0 có thể ghi nhận sáu lỗi và mở breaker.
- order-1 có thể chỉ ghi nhận hai lần thành công và vẫn CLOSED.
- order-2 có thể chưa nhận request nào; breaker có thể chưa đủ mẫu để đánh giá.
- Restart order-0 tạo một tiến trình mới và breaker trong bộ nhớ bắt đầu với trạng thái mới theo cấu hình, thường là CLOSED.

Không kết luận rằng inventory-service đã phục hồi chỉ vì một pod order mới khởi động và breaker của nó CLOSED. Trạng thái CLOSED mới chỉ cho biết breaker mới chưa có đủ lịch sử lỗi để mở; hãy xác minh request thực tế và health của phụ thuộc.

Lưu lượng phân phối qua nhiều replica cũng làm thay đổi tốc độ tích lũy mẫu. Nếu mỗi pod chỉ nhận một phần traffic, một breaker có thể cần nhiều thời gian hơn để đạt minimumNumberOfCalls. Khi chọn minimumNumberOfCalls, hãy tính lưu lượng trên từng replica, không chỉ tổng lưu lượng toàn deployment.

Không cố chia sẻ breaker state qua Redis hoặc database như một cách mặc định. Resilience4j breaker là cơ chế trong tiến trình; nếu cần điều khiển tập trung, hãy thiết kế một control plane riêng và đánh giá kỹ tính nhất quán, độ trễ và khả năng lỗi của nó.

## 7. Thu thập metric riêng cho từng pod

Prometheus cần scrape từng pod order-service thay vì chỉ scrape một Kubernetes Service load-balance. Nếu scrape qua Service, mỗi lần scrape có thể đến một pod khác nhau và nhãn pod không còn phản ánh ổn định từng nguồn.

Có thể dùng pod annotations, ServiceMonitor hoặc cấu hình Kubernetes service discovery của Prometheus. Ví dụ ý tưởng scrape theo pod annotations:

    scrape_configs:
      - job_name: order-service-pods
        kubernetes_sd_configs:
          - role: pod
        relabel_configs:
          - source_labels: [__meta_kubernetes_pod_label_app]
            action: keep
            regex: order-service
          - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
            action: keep
            regex: "true"
          - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
            action: replace
            target_label: __metrics_path__
            regex: (.+)
          - source_labels: [__meta_kubernetes_pod_ip, __meta_kubernetes_pod_annotation_prometheus_io_port]
            separator: ";"
            action: replace
            target_label: __address__
            regex: (.+);(\d+)
            replacement: $1:$2
          - source_labels: [__meta_kubernetes_pod_name]
            target_label: pod
          - source_labels: [__meta_kubernetes_namespace]
            target_label: namespace

Đây là khung cấu hình; rule trên ghép pod IP với port annotation để tạo `__address__`. Trong cluster thực tế, bổ sung namespace, TLS, authentication và relabel rule chuẩn của nền tảng. Nếu dùng Prometheus Operator, ưu tiên ServiceMonitor/PodMonitor để cấu hình scrape và label rõ ràng.

Sau khi scrape, xác nhận mỗi series có nhãn pod hoặc instance ổn định. Kiểm tra metric từ từng pod bằng cách truy cập trực tiếp endpoint Actuator khi cần.

Không expose Actuator public chỉ để Prometheus scrape. Dùng mạng nội bộ, authentication hoặc management port riêng phù hợp với nền tảng.

## 8. Dựng dashboard theo từng replica

Dashboard nên có bộ lọc namespace, application, pod và breaker name. Các panel gợi ý:

| Panel | Dữ liệu | Câu hỏi |
| --- | --- | --- |
| State theo pod | Gauge state của từng breaker | Pod nào đang CLOSED, OPEN hoặc HALF_OPEN? |
| Failure rate | Failure rate theo pod và breaker | Pod nào ghi nhận lỗi nhiều? |
| Slow call rate | Tỷ lệ lời gọi chậm | Phụ thuộc đang chậm trước khi lỗi hoàn toàn không? |
| Calls theo outcome | Rate successful, failed, ignored | Lưu lượng và kết quả thay đổi ra sao? |
| Not permitted | Counter lời gọi bị breaker từ chối | Bao nhiêu request bị chặn nhanh? |
| Fallback | Counter theo nguyên nhân và pod | Người dùng nhận fallback ở replica nào? |
| State transitions | Counter from/to theo pod | Breaker mở và phục hồi bao nhiêu lần? |
| Latency | p50/p95/p99 của lời gọi phụ thuộc | Độ trễ có giảm sau khi breaker mở không? |

Ví dụ PromQL minh họa cho số pod đang OPEN:

    sum by (namespace, pod, name) (
      resilience4j_circuitbreaker_state{state="open"} == 1
    )

Tỷ lệ lời gọi theo outcome, nếu registry xuất timer count với tag kind:

    sum by (pod, name, kind) (
      rate(resilience4j_circuitbreaker_calls_seconds_count[5m])
    )

Số lời gọi bị từ chối trong 5 phút:

    sum by (pod, name) (
      increase(resilience4j_circuitbreaker_not_permitted_calls_total[5m])
    )

Tên metric và label cần xác minh trên endpoint Prometheus của phiên bản đang chạy. Prometheus có thể chuẩn hóa tên Micrometer bằng dấu chấm thành dấu gạch dưới và hậu tố counter/timer. Nếu metric thực tế khác, điều chỉnh query theo dữ liệu scrape; không tạo panel trống rồi suy luận breaker không phát metric.

Nếu ứng dụng chưa xuất transition counter, đăng ký listener `onStateTransition` và tăng custom counter theo `from`, `to`, `name`. Giữ tập tag hữu hạn; không dùng request ID hoặc SKU làm tag.

## 9. Phân biệt dashboard theo pod và dashboard toàn dịch vụ

Một dashboard chỉ có trạng thái tổng hợp có thể che mất tình huống một pod OPEN và hai pod CLOSED. Hãy giữ hai góc nhìn:

**Góc nhìn theo pod**

- Trạng thái từng breaker ở từng pod.
- Failure rate, slow call rate và not-permitted theo pod.
- Số lần chuyển trạng thái và tuổi OPEN của từng pod.
- Fallback và latency từ pod đó.

**Góc nhìn toàn dịch vụ**

- Có bao nhiêu pod đang OPEN.
- Tỷ lệ request thành công và fallback tổng thể.
- Tổng số lời gọi bị từ chối.
- Latency tổng hợp và tình trạng inventory-service.
- Số pod Ready và số endpoint inventory có thể chọn.

Khi tổng hợp state gauge, dùng phép tổng hợp phù hợp với câu hỏi. Ví dụ, tổng số pod OPEN là tổng các gauge OPEN có giá trị 1. Không cộng các giá trị state CLOSED/OPEN/HALF_OPEN như thể chúng là counter sự kiện.

Nếu một pod OPEN nhưng hai pod CLOSED, dịch vụ vẫn có thể phục vụ một phần request. Tuy nhiên, load balancer phía trước order-service có thể tiếp tục gửi traffic đến pod OPEN. Hãy đo tỷ lệ fallback và lỗi ở phía client để biết mức ảnh hưởng thực tế.

Không tự động đánh dấu order pod NotReady chỉ vì breaker outbound đang OPEN. Làm vậy có thể loại pod khỏi traffic và dồn tải lên các pod còn lại, tạo hiệu ứng dây chuyền. Chỉ đưa trạng thái phụ thuộc vào readiness khi có thiết kế availability rõ ràng và đã đánh giá hậu quả.

## 10. Theo dõi một chu kỳ phục hồi

Với `waitDurationInOpenState: 10s` và `automaticTransitionFromOpenToHalfOpenEnabled: true`, breaker có thể tự chuyển từ OPEN sang HALF_OPEN sau thời gian chờ. Trong HALF_OPEN, tối đa hai lời gọi thử được cho phép theo cấu hình lab.

Quy trình phục hồi:

1. Ghi lại thời điểm order-0 chuyển OPEN.
2. Xác nhận request tiếp theo bị từ chối nhanh; downstream inventory không nhận thêm attempt từ breaker đó.
3. Gỡ fault injection để inventory-service trả response thành công.
4. Chờ breaker chuyển HALF_OPEN.
5. Gửi đủ số lời gọi thử được phép và quan sát kết quả.
6. Nếu các lời gọi thử thành công theo policy, breaker chuyển CLOSED.
7. Nếu lời gọi thử thất bại hoặc chậm vượt ngưỡng, breaker có thể quay lại OPEN.
8. Ghi lại thời điểm rời OPEN, kết quả HALF_OPEN và thời điểm trở về CLOSED.

Nếu automatic transition bị tắt, breaker có thể chỉ chuyển sang HALF_OPEN khi có lời gọi đến sau khi wait duration đã qua. Khi đó, thời gian OPEN quan sát được có thể dài hơn thời gian cấu hình. Hãy ghi lại cấu hình thực tế trong báo cáo.

Một lần chuyển CLOSED không chứng minh mọi instance inventory đều khỏe. Các lời gọi thử vẫn đi qua service discovery/load balancing và có thể đến một instance khác. Nếu cần kiểm chứng từng inventory instance, quan sát instance ID hoặc metric phía inventory-service.

## 11. Phân tích trường hợp các replica có trạng thái khác nhau

Dùng bảng quan sát trong lúc thực hành:

| Pod order | State | Failure rate | Not permitted | Fallback | Giải thích |
| --- | --- | --- | --- | --- | --- |
| order-0 | OPEN | 80% | 25 | 25 | Fault injection làm các mẫu lỗi vượt ngưỡng. |
| order-1 | CLOSED | 0% | 0 | 0 | Chỉ nhận lời gọi thành công. |
| order-2 | CLOSED | 0% | 0 | 0 | Chỉ nhận lời gọi thành công. |

Các số chỉ minh họa. Khi thu thập dữ liệu thật, hãy ghi cả số mẫu và thời điểm scrape để tránh so sánh tỷ lệ của cửa sổ rất nhỏ với cửa sổ đã đủ mẫu.

Nếu order-1 hoặc order-2 cũng OPEN, kiểm tra:

- Request lỗi có bị gửi qua Service chung thay vì port-forward pod cụ thể không?
- Fault header có bị gateway thêm vào mọi request không?
- Backend inventory có đang trả lỗi cho tất cả client không?
- Breaker id có bị dùng chung trong cùng pod giữa nhiều thao tác không?
- Metric có bị scrape qua Service làm mất nhãn pod không?
- Retry có khiến nhiều attempt lỗi hơn dự kiến không?
- Có cấu hình exception khiến lỗi nghiệp vụ bị tính là failure không?

Nếu order-0 vẫn CLOSED dù đã gửi lỗi, kiểm tra minimumNumberOfCalls, số request thực sự đi qua breaker, exception có được record không và breaker name trong metric có đúng không. Đừng chỉ hạ threshold để ép trạng thái OPEN; trước hết xác nhận dữ liệu đầu vào của breaker.

## 12. Viết báo cáo phục hồi

Báo cáo cần mô tả điều đã xảy ra bằng mốc thời gian và số liệu, không chỉ ghi “đã phục hồi”. Dùng mẫu sau cho mỗi lần thực hành hoặc diễn tập:

    # Báo cáo phục hồi CircuitBreaker

    ## 1. Thông tin triển khai
    - Ngày/giờ:
    - Môi trường/namespace:
    - Build/version:
    - Số replica order-service:
    - Số replica inventory-service:
    - Breaker id:
    - Cấu hình sliding window:
    - Failure/slow-call threshold:
    - waitDurationInOpenState:

    ## 2. Tình huống lỗi
    - Fault injection:
    - Pod được tác động:
    - Thời điểm bắt đầu:
    - Số request/attempt:
    - HTTP status hoặc exception:
    - Phạm vi ảnh hưởng:

    ## 3. Diễn biến breaker
    | Pod | State trước lỗi | Thời điểm OPEN | Thời điểm HALF_OPEN | Thời điểm CLOSED |
    | --- | --- | --- | --- | --- |
    | order-0 | | | | |
    | order-1 | | | | |
    | order-2 | | | | |

    ## 4. Tác động và metric
    - Failure rate cao nhất:
    - Slow call rate cao nhất:
    - Số lời gọi bị từ chối:
    - Số lần fallback:
    - Latency p95/p99:
    - Số pod Ready:
    - Số endpoint inventory khả dụng:

    ## 5. Phục hồi
    - Nguyên nhân đã được xử lý:
    - Kết quả lời gọi thử HALF_OPEN:
    - Thời gian OPEN quan sát được:
    - Thời điểm tỷ lệ lỗi trở về mức bình thường:
    - Bằng chứng từ dashboard/log/trace:

    ## 6. Kết luận và hành động
    - Điều gì hoạt động đúng:
    - Điều gì chưa đạt:
    - Cấu hình cần điều chỉnh:
    - Người phụ trách:
    - Thời hạn:
    - Link dashboard hoặc truy vấn:

Trong báo cáo, phân biệt thời gian cấu hình chờ OPEN với thời gian OPEN quan sát được. Nếu breaker chỉ rời OPEN khi có request mới, hai giá trị có thể khác nhau. Ghi rõ liệu automatic transition có được bật hay không.

Không ghi token, thông tin xác thực, payload nhạy cảm hoặc dữ liệu cá nhân vào báo cáo. Dùng pod name, breaker name, request correlation ID đã được làm sạch và mốc thời gian UTC để các nhóm có thể đối chiếu log.

## 13. Tiêu chí hoàn thành bài thực hành

Bài thực hành đạt yêu cầu khi có đủ bằng chứng:

- Ba order replica chạy Ready và được scrape riêng.
- Có thể truy cập metric của từng pod.
- Một pod được tạo lỗi có kiểm soát và chuyển OPEN.
- Các pod không bị tác động vẫn giữ CLOSED và tiếp tục gọi inventory thành công.
- Request đến pod OPEN bị từ chối nhanh và fallback được quan sát.
- Dashboard thể hiện trạng thái theo pod, failure rate, not-permitted và fallback.
- Fault injection được gỡ bỏ và lời gọi thử HALF_OPEN thành công.
- Breaker trở về CLOSED sau khi đạt điều kiện phục hồi.
- Báo cáo ghi đủ thời điểm, số mẫu, trạng thái, metric, thời lượng OPEN và hành động tiếp theo.
- Sau khi kết thúc, fault injection được tắt và môi trường lab trở về trạng thái bình thường.

Nếu không đạt một tiêu chí, ghi rõ bằng chứng còn thiếu và nguyên nhân. Không đánh dấu phục hồi chỉ vì endpoint trả HTTP 200 một lần; cần xác nhận breaker đã CLOSED, fallback giảm về mức bình thường và các replica đang hoạt động như dự kiến.

## 14. Bài tập mở rộng

Sau khi hoàn thành kịch bản chính, thử các tình huống sau:

1. Tăng order-service từ ba lên năm replica và quan sát thời gian mỗi breaker tích lũy đủ minimumNumberOfCalls.
2. Đổi sang TIME_BASED sliding window và so sánh thời điểm mở khi lưu lượng thay đổi.
3. Cho một inventory instance phản hồi chậm nhưng instance khác khỏe; quan sát LoadBalancer, retry và breaker theo logical call.
4. Restart riêng order-0 khi breaker OPEN; xác nhận breaker mới bắt đầu với state trong bộ nhớ mới và giải thích vì sao điều này không chứng minh dependency đã phục hồi.
5. Tắt Prometheus scrape một pod trong vài phút; quan sát dashboard và cảnh báo dữ liệu mất.
6. Tạo fallback tăng đột biến trong khi tổng request vẫn thành công nhờ các pod khác; đánh giá tác động thực tế đến người dùng.
7. Thử bulkhead limit thấp trên một pod và phân biệt Bulkhead rejection với CallNotPermittedException.
8. Tắt automatic transition và xác nhận thời gian OPEN quan sát được có thể vượt waitDurationInOpenState.
9. So sánh dashboard theo pod với dashboard tổng hợp; xác định thông tin nào bị mất khi bỏ nhãn pod.

Các bài tập này giúp hiểu rằng trạng thái breaker trong môi trường nhiều replica là trạng thái cục bộ. Dashboard cần giữ dữ liệu theo pod, còn báo cáo phục hồi cần liên kết trạng thái đó với sức khỏe dependency, traffic, fallback và thời điểm triển khai.

## Tài liệu tham khảo

- Spring Cloud CircuitBreaker — Resilience4J: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
- Resilience4j — CircuitBreaker state machine and configuration: https://resilience4j.readme.io/docs/circuitbreaker
- Resilience4j — Micrometer metrics: https://resilience4j.readme.io/docs/micrometer
- Spring Boot Actuator — Metrics and Prometheus: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Prometheus — Kubernetes service discovery: https://prometheus.io/docs/prometheus/latest/configuration/configuration/#kubernetes_sd_config

