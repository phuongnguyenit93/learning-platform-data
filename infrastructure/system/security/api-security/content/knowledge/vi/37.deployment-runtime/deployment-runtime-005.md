# Autoscaling không bỏ qua quota

Autoscaling giúp dịch vụ tăng hoặc giảm số instance theo tải. Khi traffic tăng, hệ thống có thể tạo thêm pod, VM hoặc worker để tăng năng lực xử lý. Nhưng số instance tăng không có nghĩa quota của tenant, API key, database, message broker hay nhà cung cấp bên ngoài cũng tăng theo.

Một lỗi thiết kế phổ biến là đặt bộ đếm quota riêng trong từng process. Nếu mỗi pod cho phép một client gửi 100 request/phút, một deployment có 5 pod có thể vô tình cho phép khoảng 500 request/phút khi traffic được phân phối đều. Scale-out đã làm tăng giới hạn thực tế mà không có quyết định cấp quota. Ở chiều ngược lại, nếu nhiều pod cùng gọi một API bên thứ ba có giới hạn 100 request/giây cho toàn bộ tài khoản, tăng worker có thể làm vượt quota provider, nhận 429 hàng loạt và khuếch đại retry.

**Quota phải được xác định theo phạm vi nghiệp vụ và tài nguyên cần bảo vệ, độc lập với số replica.** Autoscaling thay đổi capacity của hệ thống; quota quyết định actor/tenant/service được tiêu thụ bao nhiêu tài nguyên. Hai cơ chế phải phối hợp để hệ thống tăng năng lực mà vẫn giữ giới hạn, công bằng, chi phí và chính sách bảo mật.

## 1. Phân biệt capacity, rate limit, quota và concurrency

Các khái niệm liên quan nhưng không thể thay thế nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Capacity | Hệ thống có thể xử lý bao nhiêu tải ở thời điểm hiện tại? | Một pod xử lý ổn định 300 request/giây |
| Autoscaling | Khi nào và tăng/giảm bao nhiêu instance? | HPA tăng từ 3 lên 8 pod khi CPU cao |
| Rate limit | Tốc độ request được phép trong một cửa sổ hoặc theo token bucket là bao nhiêu? | Một tenant tối đa 60 request/giây |
| Usage quota | Tổng lượng sử dụng trong kỳ là bao nhiêu? | 100.000 report/tháng |
| Concurrency limit | Có bao nhiêu tác vụ đồng thời được chạy? | Tối đa 20 export đang xử lý |
| Resource budget | Một thao tác được phép tiêu tốn bao nhiêu tài nguyên? | Tối đa 500 MB hoặc 30 giây xử lý |
| Provider quota | Dịch vụ bên ngoài cho phép tiêu thụ bao nhiêu? | Tài khoản gửi email tối đa 50 message/giây |

Autoscaling chỉ điều chỉnh capacity. Nó không tự tăng plan của tenant, quota API key, giới hạn database, quota cloud account hay giới hạn của nhà cung cấp.

Một endpoint có thể cần đồng thời nhiều kiểm soát: rate limit theo user, usage quota theo tenant, concurrency limit theo loại job và global limit theo provider. Nếu chỉ có một con số request/giây, hệ thống có thể vẫn bị lạm dụng bằng các request rất tốn tài nguyên.

## 2. Vì sao quota per-instance bị nhân lên khi scale-out?

Giả sử mỗi instance giữ một bộ đếm độc lập:

~~~text
Limit mỗi pod: 100 request/phút
Số pod hiện tại: 2
Tổng mức có thể được chấp nhận: khoảng 200 request/phút

Scale-out lên 6 pod:
Tổng mức có thể được chấp nhận: khoảng 600 request/phút
~~~

Nếu load balancer phân phối request giữa các pod, cùng một caller có thể chạm nhiều bộ đếm khác nhau. Sticky session không giải quyết triệt để vì pod có thể thay đổi, client có thể mở nhiều connection và autoscaler có thể tạo replica mới.

Với quota theo kỳ, vấn đề còn rõ hơn:

~~~text
Mỗi pod cho phép 1.000 tác vụ/ngày
3 pod có thể chấp nhận khoảng 3.000 tác vụ/ngày
8 pod có thể chấp nhận khoảng 8.000 tác vụ/ngày
~~~

Giới hạn được cấu hình là 1.000 nhưng giới hạn thực tế phụ thuộc số pod. Đây là quota không ổn định và có thể bị lợi dụng bằng cách tăng traffic để kích hoạt scale-out.

Local limiter vẫn hữu ích cho bảo vệ từng process khỏi burst hoặc quá tải cục bộ. Tuy nhiên, nó chỉ nên là một lớp bảo vệ bổ sung. Quota cần áp dụng cho toàn bộ tenant/client/service phải có state dùng chung hoặc cơ chế phân bổ budget có kiểm soát.

## 3. Xác định quota theo đúng phạm vi

Trước khi triển khai, hãy xác định ai hoặc tài nguyên nào đang bị giới hạn:

| Phạm vi | Key định danh gợi ý | Mục đích |
|---|---|---|
| Global service | service + environment + operation | Bảo vệ tổng capacity và downstream |
| Tenant | tenant ID đã xác minh + operation | Giữ công bằng giữa khách hàng |
| User | subject đã xác thực + operation | Ngăn một user chiếm hết quota tenant |
| API client/key | client ID hoặc key reference | Giới hạn tích hợp cụ thể |
| Endpoint | route template + method | Bảo vệ endpoint nhạy cảm/tốn tài nguyên |
| Resource/object | tenant + object + action | Giới hạn thao tác trên một tài nguyên |
| Provider credential | provider account/key reference | Không vượt quota nhà cung cấp |
| Queue/worker pool | queue + job type | Giới hạn backlog và số job đang chạy |

Không dùng raw API key hoặc access token làm Redis key, metric label hay log field. Dùng principal ID/client ID đã xác minh hoặc fingerprint có kiểm soát. Tenant ID phải đến từ tenant context server-side, không lấy trực tiếp từ header/body rồi tin tưởng.

Một request có thể cần nhiều bucket cùng lúc: user bucket, tenant bucket, endpoint bucket và global provider bucket. Chỉ cho phép request nếu tất cả bucket bắt buộc đều còn budget. Việc consume nhiều bucket cần được thực hiện nguyên tử hoặc có cơ chế reservation/compensation để tránh trừ một bucket nhưng không trừ bucket còn lại.

## 4. Rate limit toàn hệ thống phải độc lập với số pod

Một cách triển khai phổ biến là dùng bộ đếm phân tán hoặc quota service dùng chung:

~~~mermaid
flowchart TD
    C[Client] --> G[API Gateway / Application]
    G --> I[Resolve authenticated identity and tenant]
    I --> L[Shared quota / rate-limit service]
    L -->|Allowed| A[Application handler]
    L -->|Exceeded| R[429 response]
    A --> D[Downstream services]
    H[Autoscaler] --> P[More or fewer application pods]
    P --> G
    L --> S[(Shared atomic quota state)]
~~~

Khi pod tăng từ 2 lên 10, tất cả vẫn tham chiếu cùng quota state. Mỗi request tiêu thụ budget theo tenant/client/global key đã xác định. Số replica không làm thay đổi quota đã cấp.

Các lựa chọn thường gặp:

- Redis hoặc datastore hỗ trợ atomic operation/script.
- Dedicated rate-limit/quota service.
- API gateway có global/distributed rate-limit backend.
- Distributed lease/token allocation với budget được chia trước cho từng instance.
- Database transaction cho quota dài hạn hoặc usage cần đối soát.

Chọn giải pháp theo yêu cầu latency, throughput, consistency, availability và độ chính xác. Local memory counter đơn giản và nhanh nhưng không đủ làm nguồn sự thật cho quota toàn hệ thống khi có nhiều replica.

## 5. Distributed limiter và thao tác atomic

Nếu nhiều pod cùng đọc rồi ghi một counter theo kiểu read-modify-write, chúng có thể cùng thấy còn budget và cùng chấp nhận request vượt giới hạn. Việc kiểm tra và tiêu thụ quota cần atomic.

Ví dụ logic token bucket:

~~~text
atomic consume(key, now, cost):
    state = load(key)
    elapsed = max(0, now - state.updatedAt)
    tokens = min(capacity, state.tokens + elapsed * refillRate)

    if tokens < cost:
        save(key, tokens, now)
        return DENY with retryAfter

    save(key, tokens - cost, now)
    return ALLOW
~~~

Trong Redis, có thể thực hiện toàn bộ logic trong Lua script hoặc primitive atomic phù hợp. Không tách thành nhiều lệnh GET rồi SET nếu các request có thể chạy đồng thời. Key cần TTL phù hợp để state không tồn tại vô hạn; TTL không được làm mất quota đang còn hiệu lực.

Với nhiều bucket, hãy kiểm tra và consume theo một transaction/script nguyên tử nếu tất cả state nằm trong cùng hệ thống hỗ trợ. Nếu bucket nằm ở nhiều hệ thống, cần reservation có ID, timeout và compensation; tránh báo ALLOW trước khi các giới hạn bắt buộc đã được giữ thành công.

Đồng hồ giữa node có thể lệch. Ưu tiên dùng thời gian do quota store quyết định hoặc thiết kế thuật toán chịu được clock skew; không để clock lùi làm token được refill quá mức.

## 6. Chọn thuật toán theo loại quota

| Thuật toán | Hành vi | Phù hợp |
|---|---|---|
| Fixed window | Đếm số request trong cửa sổ cố định | Quota đơn giản theo phút/giờ/ngày; có thể burst ở ranh giới cửa sổ |
| Sliding log | Lưu timestamp từng request trong cửa sổ trượt | Chính xác cao nhưng tốn storage/operation |
| Sliding window counter | Kết hợp cửa sổ hiện tại và trước đó | Xấp xỉ mượt hơn với chi phí vừa phải |
| Token bucket | Có burst capacity và refill đều | API rate limit phổ biến |
| Leaky bucket | Xử lý theo tốc độ thoát ổn định | Làm mượt tải tới dependency |
| Semaphore/concurrency counter | Giới hạn tác vụ đang chạy | Export, report, payment hoặc provider call |
| Usage ledger | Tích lũy usage trong kỳ và đối soát | Quota tháng, credit, số job hoặc dung lượng |

Không dùng token bucket cho mọi loại quota. Một quota 100.000 tác vụ/tháng cần usage ledger theo kỳ; một giới hạn 10 export đang chạy cần semaphore; provider 50 request/giây có thể cần token bucket hoặc leaky bucket ở egress.

## 7. Kết hợp per-tenant, per-user và global quota

Tenant quota bảo vệ công bằng giữa khách hàng, nhưng một user hoặc API key trong tenant có thể chiếm toàn bộ budget. Ngược lại, chỉ giới hạn theo user có thể để nhiều user cùng tenant cộng lại vượt mức plan.

Một policy ví dụ:

~~~text
POST /reports
  global service: 2.000 requests/min
  tenant: 120 requests/min
  user: 20 requests/min
  endpoint: 500 requests/min
  active report jobs per tenant: 5
  provider export concurrency: 30
~~~

Request chỉ được nhận nếu các giới hạn bắt buộc còn budget. Các giá trị trên chỉ minh họa; cần đo tải và thỏa thuận plan thực tế.

Để tránh một tenant dùng hết global capacity, có thể dùng fair scheduling, per-tenant reservation, weighted fair queueing hoặc giới hạn đồng thời theo tenant. Global quota vẫn cần giữ trần để bảo vệ dịch vụ, nhưng không nên để một tenant tiêu thụ toàn bộ chỉ vì request của họ đến trước.

## 8. Autoscaling có thể khuếch đại tải xuống downstream

Scale-out làm tăng số consumer có thể gọi database, payment provider, email API, search service hoặc một API nội bộ. Nếu mỗi pod có pool/worker riêng, tổng concurrency sẽ tăng theo replica.

Ví dụ:

~~~text
Mỗi pod có 20 worker gọi provider
Số pod: 3
Tổng concurrency: tối đa 60

Scale-out lên 10 pod
Tổng concurrency: tối đa 200

Provider chỉ cho phép 50 request đồng thời
~~~

Hệ thống có thể tự làm quá tải dependency dù CPU ứng dụng đã được giải phóng. Khi provider trả 429/503, retry không kiểm soát có thể tạo retry storm.

Đặt giới hạn tại egress/downstream boundary:

- Global request rate theo provider account/credential.
- Global concurrency theo provider hoặc endpoint.
- Per-tenant sub-limit nếu một tenant có thể gây tải provider.
- Timeout, circuit breaker và retry có backoff/jitter.
- Retry budget để retry không chiếm phần lớn traffic.
- Queue để làm mượt tải và điều phối fairness.

Không đặt quota provider riêng theo pod nếu nhà cung cấp tính quota trên toàn account. Các replica phải phối hợp qua shared limiter hoặc lease budget được phân bổ rõ ràng.

## 9. Quota cho worker và message queue

Autoscaling worker theo queue depth có thể khiến hàng trăm consumer được tạo cùng lúc. Nếu mỗi worker tự gọi downstream mà không có global cap, backlog giảm nhanh nhưng database/provider có thể bị quá tải.

Một mô hình an toàn:

1. API validate và ghi nhận job theo tenant quota.
2. Queue lưu job có tenant, job type, cost estimate và idempotency reference.
3. Scheduler chọn job theo fair queue/weighted policy.
4. Worker chỉ nhận job khi còn global và per-tenant concurrency slot.
5. Trước khi gọi provider, worker tiêu thụ downstream rate budget.
6. Nếu quota provider hết, job được trì hoãn với backoff thay vì retry liên tục.
7. Khi hoàn tất/hủy, concurrency slot được giải phóng.

Không chỉ giới hạn số message trong queue. Một queue có 10.000 job nhỏ và một queue có 10.000 job tạo báo cáo nặng có cost khác nhau. Có thể dùng weighted cost, job class, estimated duration hoặc resource budget.

Nếu worker crash khi đang giữ semaphore, lease cần TTL/heartbeat để slot được thu hồi. Nếu TTL quá ngắn, một job đang chạy lâu có thể bị cấp slot trùng; nếu quá dài, slot bị kẹt sau crash. Chọn lease theo timeout, heartbeat và fencing token phù hợp.

## 10. Usage quota dài hạn và reservation

Quota theo tháng hoặc theo kỳ thường không thể quản lý chỉ bằng rate limiter. Ví dụ tenant được tạo 10.000 report/tháng hoặc lưu 500 GB.

Một usage ledger có thể ghi:

| Field | Ý nghĩa |
|---|---|
| Tenant/plan | Chủ thể và gói quota |
| Meter | Loại usage: report, storage, export, API credits |
| Period | Kỳ tính quota và timezone/rule reset |
| Limit | Mức được cấp |
| Consumed | Lượng đã hoàn tất |
| Reserved | Lượng đang giữ cho job chưa hoàn tất |
| Adjustment | Điều chỉnh/hoàn trả có audit |
| Version | Phiên bản policy/quota |

Khi tạo job tốn tài nguyên, có thể reserve budget trước:

~~~text
reserve(tenant, meter, estimatedCost, idempotencyKey)
  -> reservationId

process job

on success:
  settle(reservationId, actualCost)

on cancel/failure:
  release(reservationId)
~~~

Reservation ngăn nhiều request đồng thời cùng nhìn thấy usage còn đủ rồi vượt quota khi commit. Reservation phải idempotent, có trạng thái và expiry; không được release hai lần hoặc settle nhiều lần. Nếu actual cost lớn hơn estimate, cần policy cho phần vượt.

Định nghĩa rõ quota tính theo lúc nhận request, lúc job hoàn tất hay theo actual resource consumed. Với công việc kéo dài, cần xử lý thay đổi plan, reset kỳ và job chạy qua thời điểm reset.

## 11. Không để autoscaling tạo đường vòng quota

Một số anti-pattern:

| Anti-pattern | Vì sao sai | Cách xử lý |
|---|---|---|
| Counter trong memory mỗi pod | Tổng quota tăng theo replica | Shared atomic state hoặc lease budget |
| Chia quota cố định theo số pod hiện tại | Scale-out/in làm đổi tổng hoặc bỏ phí quota | Cấp lease có tổng budget được kiểm soát và thu hồi |
| Reset counter khi pod restart | Restart/rollout xóa usage | State bền vững ngoài process |
| Sticky session để giữ quota | Có thể đổi pod, mở connection hoặc bypass qua node khác | Identity-based shared limiter |
| HPA maxReplicas được coi là quota | Chỉ giới hạn số pod, không giới hạn tenant usage | Application quota độc lập |
| Kubernetes ResourceQuota được coi là API quota | Giới hạn tài nguyên namespace, không giới hạn request của tenant | Tách infrastructure quota và business quota |
| Một limit cho mọi endpoint | Request rẻ và đắt tiêu thụ như nhau | Weighted cost/endpoint policy |
| Retry khi provider trả 429 không giới hạn | Khuếch đại tải và kéo dài outage | Backoff, Retry-After, retry budget và shared limiter |

Local limiter có thể bảo vệ CPU/connection của từng pod, nhưng không được xem là nguồn quota toàn cục. Nếu dùng local prefilter, global limiter vẫn phải quyết định quota cuối cùng.

## 12. Kubernetes HPA không quản lý business quota

Horizontal Pod Autoscaler điều chỉnh số replica dựa trên metric như CPU, memory hoặc custom/external metric. HPA không biết tenant nào đã dùng bao nhiêu API call, gói khách hàng có bao nhiêu credit hay provider account còn bao nhiêu request.

Các khái niệm Kubernetes cần tách biệt:

| Cơ chế | Giới hạn/điều chỉnh | Không thay thế |
|---|---|---|
| HPA | Số replica theo metric | Tenant/API-key quota |
| Resource requests/limits | CPU/memory mỗi container | Giới hạn usage nghiệp vụ |
| ResourceQuota | Tổng tài nguyên/object trong namespace | Rate limit API |
| LimitRange | Default/min/max resource request/limit cho object | Quota của user/tenant |
| PodDisruptionBudget | Số pod tối thiểu khả dụng khi voluntary disruption | Concurrency hoặc request quota |
| NetworkPolicy | Luồng mạng được phép | Quota và authorization ở API |

Ví dụ, namespace ResourceQuota có thể ngăn một team tạo quá nhiều CPU/memory request. Nhưng một tenant gọi API 1 triệu lần vẫn cần được application/gateway limiter xử lý.

## 13. Ví dụ HPA có giới hạn scale

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 3
  maxReplicas: 12
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      selectPolicy: Max
      policies:
        - type: Pods
          value: 4
          periodSeconds: 60
        - type: Percent
          value: 100
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      selectPolicy: Max
      policies:
        - type: Percent
          value: 25
          periodSeconds: 60
~~~

Đây là ví dụ minh họa cho HPA autoscaling/v2. maxReplicas và behavior giới hạn tốc độ/mức thay đổi replica theo policy, nhưng không phải tenant quota và không đảm bảo downstream chịu được tải. Cần cấu hình resource request để CPU utilization có ý nghĩa; nếu dùng custom metric, phải có adapter/metrics pipeline phù hợp.

Giá trị min/max và scale policy phải dựa trên capacity test, ngân sách và giới hạn dependency. HPA có thể không scale đúng nếu metric thiếu hoặc scheduler không còn capacity; quota phải hoạt động độc lập trong các tình huống đó.

## 14. Kubernetes ResourceQuota và LimitRange cho capacity

Ví dụ ResourceQuota:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: production-budget
  namespace: production
spec:
  hard:
    requests.cpu: "40"
    requests.memory: 80Gi
    limits.cpu: "80"
    limits.memory: 160Gi
    pods: "50"
~~~

Ví dụ LimitRange:

~~~yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: container-defaults
  namespace: production
spec:
  limits:
    - type: Container
      defaultRequest:
        cpu: 100m
        memory: 128Mi
      default:
        cpu: "1"
        memory: 512Mi
      max:
        cpu: "4"
        memory: 4Gi
~~~

Các cấu hình này giới hạn tài nguyên Kubernetes trong namespace. Chúng giúp tránh autoscaler tạo quá nhiều pod hoặc pod khai báo tài nguyên quá lớn, nhưng không thay thế limiter ở API, service hoặc provider egress.

Khi HPA muốn tăng replica vượt ResourceQuota hoặc cluster capacity, pod có thể ở trạng thái Pending. Hãy giám sát unschedulable pod, quota usage và scaling events; đừng dựa vào việc cluster từ chối pod như một cơ chế bảo vệ API quota.

## 15. Connection pool và giới hạn database khi scale

Mỗi pod thường có connection pool riêng. Nếu pool size cố định, tổng connection tối đa tăng theo số pod:

~~~text
Tổng connection tối đa
  = số pod tối đa × pool size mỗi pod
    + connection của worker/admin/migration
~~~

Ví dụ 12 pod × 20 connection = 240 connection, chưa tính background worker và công cụ vận hành. Nếu database chỉ cho phép 200 connection, autoscaling có thể làm database từ chối connection dù mỗi pod vẫn khỏe.

Hãy đặt pool budget theo maxReplicas và reserve cho:

- Migration, monitoring và backup.
- Admin/incident response.
- Background worker và scheduled job.
- Replica/read pool nếu dùng database cluster.
- Connection của service khác cùng database.

Có thể dùng connection pooler/proxy, giới hạn pool mỗi pod, bulkhead và admission control. Không tăng pool size chỉ vì số pod tăng. Đối với query tốn tài nguyên, cần giới hạn concurrency và statement timeout; quota request/giây không bảo đảm database không bị quá tải.

## 16. Global concurrency và provider quota

Rate limit và concurrency limit bảo vệ hai khía cạnh khác nhau. Provider có thể cho phép 100 request/giây nhưng chỉ chịu 20 request đồng thời; request kéo dài 10 giây có thể vượt concurrency dù rate không cao.

Một egress controller có thể áp dụng:

~~~text
Provider account: mail-service-prod
  global rate: 40 calls/second
  global concurrency: 20
  per-tenant rate: 5 calls/second
  timeout: 3 seconds
  retry: max 2 attempts with exponential backoff + jitter
~~~

Mỗi worker phải xin slot/concurrency lease và rate token từ shared limiter trước khi gọi provider. Slot được giải phóng khi request kết thúc hoặc lease được thu hồi theo heartbeat. Khi provider trả 429 và có Retry-After, tôn trọng thời điểm retry; không để từng pod tự retry ngay lập tức.

Provider quota thường gắn với account, project, region, endpoint hoặc credential. Hãy đọc quota contract và phân loại đúng scope. Một API key khác nhau có thể vẫn dùng chung account quota; chia key không nhất thiết tăng giới hạn thực tế.

## 17. Quota theo cost thay vì chỉ đếm request

Một request GET metadata có thể rẻ hơn một request tạo báo cáo, export file hoặc gọi nhiều downstream service. Đếm mọi request như nhau khiến quota không phản ánh chi phí.

Có thể gán cost weight:

| Operation | Cost minh họa |
|---|---:|
| GET summary | 1 |
| GET detail với quan hệ | 2 |
| Search trên tập dữ liệu lớn | 5 |
| Tạo report nền | 10 |
| Export nhiều bản ghi | 20 |

Limiter consume token theo cost thay vì số request. Cost nên dựa trên độ phức tạp thực tế, số record, kích thước, fan-out và tài nguyên dùng. Với cost chỉ biết sau khi chạy, dùng estimate/reservation rồi settle theo actual usage.

Không để client tự gửi cost weight. Server xác định cost theo route, plan, request shape đã validate và resource estimate.

## 18. Scale-to-zero và quota state

Khi dịch vụ scale-to-zero hoặc pod bị thay thế, local memory state biến mất. Nếu quota counter nằm trong process, client có thể nhận lại budget sau cold start hoặc rollout.

Quota state cần tồn tại ngoài vòng đời pod:

- Redis/shared datastore với persistence và replication phù hợp.
- Database usage ledger cho quota dài hạn.
- Dedicated service có state durable.
- Lease/token allocation có expiry và tổng budget được quản lý.

Không reset quota theo startup time của pod. Reset theo kỳ phải dựa vào period boundary đã định nghĩa, timezone và idempotent scheduler. Nếu nhiều pod cùng chạy reset job, cần distributed lock/transaction hoặc thao tác idempotent.

Với quota ngày/tháng, lưu kỳ rõ ràng (ví dụ UTC calendar period hoặc billing period của tenant). Không suy ra reset từ local clock của pod.

## 19. Autoscaling và cost-based denial of service

Autoscaling có thể biến request độc hại thành chi phí trực tiếp:

- Attacker gửi request tốn CPU để kích hoạt scale-out.
- Tạo nhiều job nền làm queue backlog tăng.
- Kích hoạt nhiều pod, connection và log volume.
- Gọi dependency trả phí hoặc tiêu thụ provider quota.
- Tạo burst khiến cluster phải tải image, warm cache và mở connection.

Rate limit là một lớp; cần thêm:

- MaxReplicas, scale-up rate và budget theo namespace/service.
- Per-tenant request/job/compute quota.
- Endpoint cost limit và concurrency cap.
- Queue admission control và backlog cap.
- Circuit breaker và downstream global quota.
- Alert khi replica, cost, queue depth hoặc provider usage tăng bất thường.
- Authentication sớm trước các thao tác đắt tiền; giới hạn pre-auth endpoint riêng.

Không dựa vào autoscaler để tự xử lý abuse. Autoscaler phản ứng với tải, không phân biệt traffic hợp lệ với attacker. Nếu không có admission control, hệ thống có thể tự mở rộng để phục vụ traffic gây hại.

## 20. Fail-open hay fail-closed khi quota store gặp sự cố?

Nếu Redis/quota service không truy cập được, hệ thống cần policy rõ cho từng loại thao tác:

| Trường hợp | Hành vi có thể phù hợp |
|---|---|
| Public read ít rủi ro, có global capacity guard | Có thể dùng local emergency limit đã định nghĩa |
| Tạo job tốn tài nguyên/chi phí | Fail closed hoặc queue admission hạn chế |
| Thanh toán, chuyển tiền, usage billing | Không chấp nhận nếu không thể bảo đảm idempotency/quota policy cần thiết |
| Authentication/pre-auth endpoint | Dùng giới hạn fallback chặt và bảo vệ chống abuse |
| Provider egress | Dừng hoặc giảm tốc khi không xác định được global budget |

Fail-open có thể giữ availability nhưng mở đường vượt quota. Fail-closed bảo vệ quota nhưng có thể giảm availability. Không dùng một lựa chọn cho mọi endpoint; phân loại theo tác động bảo mật, chi phí và khả năng chấp nhận rủi ro.

Nếu dùng local fallback, tổng budget fallback phải có trần độc lập với số pod hoặc được chia lease trước. Nếu mỗi pod tự mở một fallback limit khi Redis lỗi, sự cố quota store lại làm quota tổng tăng theo replica.

## 21. Tránh double charge khi retry và scale

Request có thể được gửi lại do timeout, gateway retry, client retry hoặc worker redelivery. Nếu mỗi lần thử đều trừ quota, usage có thể bị tính nhiều lần dù chỉ một nghiệp vụ được tạo.

Thiết kế nên:

- Dùng idempotency key theo principal/tenant và operation.
- Gắn reservation ID/usage event ID duy nhất.
- Tách request attempt count khỏi completed business usage.
- Không consume lại quota khi replay cùng idempotency key và cùng request fingerprint.
- Với retry nội bộ, giữ cùng operation ID và retry budget.
- Ghi audit cho adjustment/refund thay vì sửa counter không dấu vết.
- Consumer deduplicate message/job theo ID.

Định nghĩa rõ điều gì được tính quota: request được nhận, job được tạo, job hoàn tất hay actual resource consumed. Nếu quota là billing meter, cần usage ledger có thể đối soát; counter rate limit ngắn hạn không đủ làm bằng chứng tính phí.

## 22. Triển khai trong Spring/API gateway

Một request flow nên resolve identity trước khi chọn quota key:

~~~java
public RateLimitDecision checkRequest(
        AuthenticatedPrincipal principal,
        TenantContext tenant,
        String routeId,
        int cost) {

    List<QuotaBucket> buckets = List.of(
        QuotaBucket.global(routeId),
        QuotaBucket.tenant(tenant.id(), routeId),
        QuotaBucket.user(principal.subject(), routeId)
    );

    return quotaService.consumeAtomically(buckets, cost);
}
~~~

Ví dụ này là pseudocode; QuotaBucket và consumeAtomically là abstraction cần triển khai bằng shared atomic store hoặc quota service. Không dùng header X-Tenant-ID thô để tạo tenant bucket. TenantContext phải được tạo sau authentication và membership check.

Ở Spring, có thể đặt limiter tại gateway/filter/interceptor để từ chối sớm, nhưng service vẫn cần kiểm soát cho các luồng nội bộ không đi qua gateway. Business usage quota nên được kiểm tra ở application service/transaction boundary để gắn với thao tác nghiệp vụ.

Response khi vượt rate limit có thể là:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 10
Content-Type: application/problem+json

{
  "status": 429,
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "The request rate limit has been reached."
}
~~~

Không tiết lộ quota nội bộ hoặc key của tenant khác. Nếu API công bố quota còn lại, chỉ trả thông tin thuộc principal hiện tại và bảo đảm semantics rõ ràng. Với quota đã hết trong kỳ billing, có thể dùng error code riêng như QUOTA_EXCEEDED thay vì mô tả nhầm là rate limit ngắn hạn.

## 23. Metrics và alert cho autoscaling cùng quota

Theo dõi cả trạng thái scale và quota:

**Autoscaling/capacity**

- Replica desired/current/ready/pending.
- Scale-up/down event và thời gian từ trigger tới pod ready.
- CPU, memory, request concurrency và saturation.
- Pod restart, OOM, unschedulable và rollout overlap.

**Quota/rate limiting**

- ALLOW/DENY theo bucket scope, route và reason code.
- Usage/limit/reserved theo tenant và meter.
- Số lần quota store timeout/error và local fallback.
- Reservation hết hạn, duplicate consume và adjustment.
- Top tenant theo usage/cost nhưng tránh lộ raw ID trong dashboard chung.

**Downstream**

- Provider 429/5xx, Retry-After và retry count.
- Active concurrency, queue wait và circuit breaker state.
- Database connection usage, pool wait và rejected connection.
- Queue depth, oldest message age và worker throughput.

Alert khi scale-out tăng nhanh đồng thời provider 429, database connection saturation hoặc quota-store error tăng. Alert khi một tenant tạo nhiều job tốn tài nguyên hoặc usage tăng bất thường dù request rate không cao.

Không dùng raw user ID/API key làm metric label cardinality cao. Dùng label giới hạn như service, route template, operation, bucket type, decision và reason; chi tiết định danh để trong audit/log có quyền truy cập.

## 24. Kiểm thử quota khi autoscaling

Test đơn pod không đủ chứng minh quota đúng trong môi trường nhiều replica. Cần kiểm tra scale, race condition, restart và dependency:

| Nhóm test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Replica multiplication | Gửi cùng tenant qua nhiều pod | Tổng usage không vượt global/tenant quota |
| Scale-out | Tăng từ 2 lên nhiều replica trong lúc traffic cao | Quota không thay đổi theo số pod |
| Scale-in | Pod bị terminate khi đang giữ lease | Budget được giải phóng/thu hồi đúng, không cấp trùng |
| Restart | Restart pod sau khi đã consume quota | Usage vẫn được giữ |
| Concurrent race | Nhiều request consume bucket cùng lúc | Atomic limit không bị vượt ngoài burst policy |
| Multi-bucket | Tenant/user/global bucket cùng áp dụng | Không có partial consume gây sai usage |
| Redis outage | Shared limiter unavailable | Fallback theo policy, không nhân quota theo pod |
| Provider quota | Worker scale-out và gọi provider | Egress rate/concurrency vẫn nằm trong quota |
| Queue backlog | Tăng job backlog đột biến | Worker scale có trần và scheduler giữ fairness |
| DB connections | Tăng replica tới maxReplicas | Tổng pool không vượt budget database |
| Idempotency | Retry cùng request/message | Không double charge hoặc tạo job trùng |
| Period reset | Nhiều pod chạy qua thời điểm reset | Quota reset đúng một lần theo period |
| Tenant fairness | Một tenant tạo burst lớn | Tenant khác vẫn có phần capacity theo policy |
| Cost abuse | Request/job có cost cao | Cost budget và concurrency được áp dụng |
| HPA limit | HPA chạm maxReplicas hoặc cluster quota | API quota vẫn hoạt động độc lập |
| Metrics/alert | Scale và provider throttle cùng tăng | Dashboard/alert chỉ ra quan hệ giữa hai hiện tượng |

Nên chạy load test với nhiều client/tenant, nhiều pod và shared quota backend thật hoặc test environment tương đương. Kiểm tra cả p95/p99 latency của limiter vì một global service quá chậm có thể trở thành bottleneck mới.

## 25. Checklist autoscaling không bỏ qua quota

- [ ] Phân biệt capacity, rate limit, usage quota, concurrency và provider quota.
- [ ] Xác định quota scope: global, tenant, user, client, endpoint, resource và provider.
- [ ] Không dùng in-memory counter per pod làm nguồn quota toàn hệ thống.
- [ ] Shared limiter thực hiện consume atomically và chịu được concurrent requests.
- [ ] Nhiều bucket được kiểm tra/consume nhất quán; reservation có timeout và compensation.
- [ ] Quota state tồn tại ngoài vòng đời pod và không reset khi restart/scale-to-zero.
- [ ] Autoscaling không làm tăng quota tenant/client hoặc provider.
- [ ] Có global egress rate/concurrency limit cho dependency và provider account.
- [ ] Worker autoscaling có queue admission, fairness, concurrency cap và retry budget.
- [ ] Database connection pool được tính theo maxReplicas và reserve vận hành.
- [ ] HPA maxReplicas/scale behavior và Kubernetes ResourceQuota được cấu hình theo capacity/cost.
- [ ] Không nhầm HPA, ResourceQuota hoặc LimitRange với business quota.
- [ ] Có cost-based limit cho endpoint/job tốn tài nguyên.
- [ ] Có policy fail-open/fail-closed và emergency fallback không nhân theo số pod.
- [ ] Idempotency/reservation ngăn double charge khi retry hoặc redelivery.
- [ ] Metrics liên kết replica, quota denial, provider 429, DB saturation và queue backlog.
- [ ] Test nhiều replica, scale-out/in, restart, race, backend outage và provider throttle.
- [ ] Exception hoặc quota override có owner, scope, thời hạn và audit.

## Kết luận

Autoscaling tăng số instance để đáp ứng tải, nhưng không cấp thêm quota cho tenant, user, API key, database hoặc provider. Quota toàn hệ thống phải dựa trên identity và resource scope đã xác minh, được tiêu thụ bằng shared atomic state, usage ledger hoặc lease có tổng budget kiểm soát. Đồng thời, scale-out phải tính đến downstream rate/concurrency, queue worker, database connection pool và chi phí vận hành. HPA và Kubernetes ResourceQuota giới hạn capacity hạ tầng; application quota vẫn phải hoạt động độc lập. Khi kiểm thử nhiều replica, restart, retry và backend outage, hệ thống có thể mở rộng mà không tạo đường vòng quota hoặc biến autoscaling thành bộ khuếch đại tấn công từ chối dịch vụ.
