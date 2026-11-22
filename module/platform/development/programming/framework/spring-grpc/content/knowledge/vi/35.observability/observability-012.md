# Alert theo error rate và saturation

## 1. Alert phải phản ánh lỗi người dùng và nguy cơ cạn tài nguyên

Trong **Spring gRPC**, một service có thể vẫn sống và nhận kết nối trong khi RPC liên tục thất bại, latency tăng hoặc executor không còn capacity. Health check chỉ cho biết process có đáp ứng một phép kiểm tra đơn giản; nó không chứng minh service đang phục vụ request đúng SLO.

Hai nhóm tín hiệu quan trọng:

- **Error rate:** tỷ lệ RPC không đạt kết quả mà API cam kết, ví dụ lỗi server, timeout hoặc dependency failure ảnh hưởng người gọi.
- **Saturation:** mức sử dụng tài nguyên có giới hạn như executor threads, queue, database connections, outbound connection pool hoặc CPU.

Alert tốt cần trả lời ba câu hỏi: điều gì đang hỏng, mức độ ảnh hưởng tới người dùng ra sao, và người trực cần làm gì tiếp theo. Một metric vượt ngưỡng trong vài giây chưa chắc cần đánh thức on-call; cần xét thời lượng, traffic, SLO và tín hiệu liên quan.

## 2. Xác định error rate trước khi viết rule

Không phải mọi gRPC status khác OK đều có nghĩa service đang vi phạm availability SLO. Ví dụ:

| Status | Cách diễn giải thường gặp | Đưa vào availability error? |
| --- | --- | --- |
| INTERNAL, UNKNOWN | Lỗi xử lý không mong đợi | Thường có |
| UNAVAILABLE | Service hoặc dependency tạm thời không phục vụ | Thường có |
| DEADLINE_EXCEEDED | Không hoàn thành trong ngân sách thời gian | Có nếu timeout thuộc trách nhiệm service/SLO |
| RESOURCE_EXHAUSTED | Hết quota hoặc capacity | Thường có nếu caller không chủ động vượt quota |
| INVALID_ARGUMENT | Request sai contract | Thường không |
| UNAUTHENTICATED, PERMISSION_DENIED | Caller thiếu credential/quyền | Thường không với availability SLI |
| CANCELLED | Caller hoặc upstream hủy | Phụ thuộc nguyên nhân và SLO |
| NOT_FOUND | Resource không tồn tại | Thường là kết quả nghiệp vụ hợp lệ |

Phải định nghĩa **eligible request** và **bad event** theo SLO của từng RPC. Nếu dùng biểu thức đơn giản grpc_status khác OK, các lỗi caller dự kiến như INVALID_ARGUMENT hoặc PERMISSION_DENIED có thể làm error rate tăng giả.

Một metric contract ứng dụng có thể gắn slo_result="good" hoặc slo_result="bad" vào mỗi logical server call đã kết thúc:

| Metric | Loại | Ý nghĩa |
| --- | --- | --- |
| app_grpc_server_calls_completed_total | Counter | Eligible RPC kết thúc cho SLI, có label service, method, grpc_status và slo_result |
| app_grpc_server_call_duration_seconds | Histogram | Thời gian server xử lý RPC |
| app_grpc_server_inflight | Gauge | RPC đang hoạt động |
| app_grpc_executor_active_threads | Gauge | Worker đang chạy theo pool |
| app_grpc_executor_max_threads | Gauge | Số worker tối đa theo pool |
| app_grpc_executor_queue_size | Gauge | Task đang chờ theo pool |
| app_grpc_executor_queue_capacity | Gauge | Capacity queue theo pool |
| app_grpc_executor_rejected_total | Counter | Task bị executor từ chối |
| app_grpc_dependency_calls_completed_total | Counter | Outbound dependency call đã kết thúc, có outcome |
| app_grpc_db_pool_active | Gauge | Database connections đang được sử dụng |
| app_grpc_db_pool_max | Gauge | Giới hạn database connections |
| app_grpc_db_pool_pending | Gauge | Request đang chờ connection |

Các tên trên là metric contract minh họa, không phải tên mặc định bắt buộc của gRPC hoặc OpenTelemetry. Nếu instrumentation hiện có đã xuất metric tương đương, dùng metric đó và ánh xạ label/semantics rõ ràng.

Counter dùng trong công thức SLI chỉ chứa eligible requests theo contract. RPC bị loại khỏi SLO như INVALID_ARGUMENT hoặc một số CANCELLED vẫn cần metric vận hành riêng để điều tra, nhưng không được cộng vào mẫu số SLI nếu SLO không tính chúng.

## 3. Tính error ratio đúng cách

Error ratio trong một cửa sổ thời gian được tính bằng bad eligible requests chia cho all eligible requests.

Với Prometheus counter, dùng rate() để lấy tốc độ tăng trong cửa sổ. Luôn cộng numerator và denominator theo cùng tập label trước khi chia:

~~~promql
sum by (service, method) (
  rate(app_grpc_server_calls_completed_total{slo_result="bad"}[5m])
)
/
clamp_min(
  sum by (service, method) (
    rate(app_grpc_server_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Không lấy trung bình các error ratio riêng của từng instance. Instance có 2 request và 1 lỗi không nên có trọng số ngang instance có 20.000 request và 10 lỗi. Cộng số bad events và eligible events trước rồi mới chia sẽ cho tỷ lệ có trọng số theo traffic.

Nếu chỉ có gRPC status, có thể tạo một tập status lỗi theo SLO:

~~~promql
sum by (service, method) (
  rate(app_grpc_server_calls_completed_total{
    grpc_status=~"INTERNAL|UNKNOWN|UNAVAILABLE|DEADLINE_EXCEEDED|RESOURCE_EXHAUSTED"
  }[5m])
)
/
clamp_min(
  sum by (service, method) (
    rate(app_grpc_server_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Danh sách status chỉ là ví dụ. Hãy quyết định riêng với product/SLO owner xem RESOURCE_EXHAUSTED, DEADLINE_EXCEEDED và CANCELLED có phải bad event hay không; không copy regex này cho mọi RPC.

## 4. Tránh alert sai khi traffic thấp

Một lỗi trong một request có thể tạo error ratio 100% khi traffic rất thấp. Alert ratio cần đi cùng traffic floor hoặc số lượng request tối thiểu:

~~~promql
(
  sum by (service) (
    rate(app_grpc_server_calls_completed_total{slo_result="bad"}[5m])
  )
  /
  clamp_min(
    sum by (service) (
      rate(app_grpc_server_calls_completed_total[5m])
    ),
    1e-9
  )
) > 0.02
and on (service)
sum by (service) (
  increase(app_grpc_server_calls_completed_total[5m])
) >= 100
~~~

Ví dụ trên chỉ kích hoạt khi error ratio vượt 2% và có ít nhất 100 call trong 5 phút. Với API ít traffic, ngưỡng 100 có thể không phù hợp; dùng cửa sổ dài hơn, absolute error count, synthetic probe hoặc alert riêng cho mất khả năng phục vụ.

Không coi “không có time series” là zero error. Cần alert riêng cho telemetry target down, scrape failure hoặc metric bị mất. Nếu service không có traffic theo thiết kế, không cảnh báo availability dựa trên ratio chia cho zero.

## 5. Alert theo SLO và error budget burn rate

Nếu service có availability SLO 99,9%, error budget ratio là 1 - 0.999 = 0.001.

Burn rate cho biết tốc độ tiêu thụ error budget so với tốc độ được phép:

~~~text
burn rate = observed error ratio / allowed error ratio
~~~

Ví dụ error ratio 1,44% với SLO 99,9% tương đương burn rate 14,4 lần. Nếu kéo dài, budget sẽ cạn nhanh hơn kế hoạch.

Multi-window alert dùng hai cửa sổ dài/ngắn để tránh đánh thức on-call vì một spike ngắn:

- Cửa sổ dài xác nhận vấn đề tồn tại đủ lâu.
- Cửa sổ ngắn xác nhận vấn đề vẫn đang diễn ra.
- Cùng một burn threshold phải vượt ở cả hai cửa sổ.

Ví dụ rule dưới đây minh họa burn rate 14,4 với cửa sổ 1 giờ và 5 phút. Với error budget 30 ngày, mức burn này tương ứng tiêu thụ khoảng 2% budget trong một giờ nếu duy trì liên tục.

~~~promql
(
  sum by (service) (
    rate(app_grpc_server_calls_completed_total{slo_result="bad"}[1h])
  )
  /
  clamp_min(
    sum by (service) (
      rate(app_grpc_server_calls_completed_total[1h])
    ),
    1e-9
  )
) / 0.001 > 14.4
and on (service)
(
  sum by (service) (
    rate(app_grpc_server_calls_completed_total{slo_result="bad"}[5m])
  )
  /
  clamp_min(
    sum by (service) (
      rate(app_grpc_server_calls_completed_total[5m])
    ),
    1e-9
  )
) / 0.001 > 14.4
~~~

Thay 0.001 bằng error budget thực tế của SLO. Trong production nên dùng recording rule cho error ratio/burn rate để tránh lặp biểu thức dài, và chọn các cặp cửa sổ theo quy mô budget, mức độ nghiêm trọng và chính sách on-call.

## 6. Saturation: đo giới hạn đang bị chạm

Saturation là tình trạng một tài nguyên gần hoặc đã chạm giới hạn. Với Spring gRPC, cần quan sát ít nhất:

| Tài nguyên | Metric/tín hiệu | Dấu hiệu saturation |
| --- | --- | --- |
| Callback executor | Active threads / max threads | Worker liên tục chạm max |
| Executor queue | Queue size / capacity | Queue tăng và gần đầy |
| Executor rejection | Rejected task rate | Request công việc mới bị từ chối |
| Database pool | Active / max, pending | Không lấy được connection đúng hạn |
| Outbound connection pool | Active / max, pending acquire | Handler chờ connection downstream |
| CPU | Utilization, throttling | CPU gần quota hoặc bị throttling |
| Memory/GC | Heap, allocation, pause | GC pause tăng, heap gần giới hạn |
| In-flight RPC | Active calls và duration | Call tồn đọng, stream không kết thúc |

Một gauge cao riêng lẻ chưa đủ kết luận sự cố. Ví dụ CPU 90% có thể bình thường nếu throughput cao và latency ổn định. Saturation alert nên kết hợp utilization, queue/wait, rejection hoặc latency để phát hiện ảnh hưởng thực.

## 7. Alert cho executor queue và worker

Tỷ lệ queue occupancy theo pool:

~~~promql
app_grpc_executor_queue_size
/
clamp_min(app_grpc_executor_queue_capacity, 1)
~~~

Alert queue gần đầy:

~~~promql
(
  app_grpc_executor_queue_size
  /
  clamp_min(app_grpc_executor_queue_capacity, 1)
) > 0.80
and on (service, pool)
(
  app_grpc_executor_active_threads
  /
  clamp_min(app_grpc_executor_max_threads, 1)
) > 0.90
~~~

Alert rejection:

~~~promql
sum by (service, pool) (
  rate(app_grpc_executor_rejected_total[5m])
) > 0
~~~

Queue trên 80% và worker trên 90% trong một khoảng duy trì cho thấy pool sắp hết capacity. Rejection rate lớn hơn zero là tín hiệu rõ hơn rằng pool đã từ chối task; mức độ cần page hay warning tùy traffic và RPC quan trọng.

Nếu executor có queue capacity bằng zero hoặc dùng SynchronousQueue, queue occupancy không có ý nghĩa như queue thông thường. Khi đó theo dõi active/max, rejection, task wait và latency.

## 8. Alert cho database và downstream dependency

Database pool utilization:

~~~promql
app_grpc_db_pool_active
/
clamp_min(app_grpc_db_pool_max, 1)
~~~

Pending connection acquisition:

~~~promql
app_grpc_db_pool_pending > 0
~~~

Kết hợp pending với thời gian chờ connection hoặc query latency. Một vài request pending trong thời gian ngắn có thể là burst bình thường; pending kéo dài cùng p95 acquisition wait và RPC latency tăng là tín hiệu mạnh hơn.

Với dependency call, dùng error ratio và p95 latency theo dependency:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, dependency) (
    rate(app_grpc_dependency_call_duration_seconds_bucket[5m])
  )
)
~~~

~~~promql
sum by (dependency) (
  rate(app_grpc_dependency_calls_completed_total{outcome="failure"}[5m])
)
/
clamp_min(
  sum by (dependency) (
    rate(app_grpc_dependency_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Không áp một ngưỡng latency cho tất cả dependency. Database query, cache lookup và downstream gRPC call có baseline khác nhau. Đặt threshold theo dependency SLO và kiểm tra liệu độ trễ đó có truyền tới RPC người dùng hay được cache/fallback hấp thụ.

## 9. Định nghĩa alert rule có thể vận hành

Một Prometheus alert rule thường có:

- expr: điều kiện tính từ metric.
- for: thời gian điều kiện phải duy trì trước khi firing.
- labels: severity, team hoặc service để route.
- annotations: summary, mô tả tác động và runbook link.

Ví dụ file rule:

~~~yaml
groups:
  - name: spring-grpc-availability
    rules:
      - alert: GrpcServerHighErrorRate
        expr: |
          (
            sum by (service) (
              rate(app_grpc_server_calls_completed_total{slo_result="bad"}[5m])
            )
            /
            clamp_min(
              sum by (service) (
                rate(app_grpc_server_calls_completed_total[5m])
              ),
              1e-9
            )
          ) > 0.02
          and on (service)
          sum by (service) (
            increase(app_grpc_server_calls_completed_total[5m])
          ) >= 100
        for: 5m
        labels:
          severity: page
          team: platform
        annotations:
          summary: "gRPC error rate cao ở {{ $labels.service }}"
          description: "Error ratio vượt 2% với traffic đủ lớn trong ít nhất 5 phút."
          runbook_url: "https://runbooks.example/grpc/high-error-rate"

      - alert: GrpcExecutorSaturated
        expr: |
          (
            app_grpc_executor_queue_size
            /
            clamp_min(app_grpc_executor_queue_capacity, 1)
          ) > 0.80
          and on (service, pool)
          (
            app_grpc_executor_active_threads
            /
            clamp_min(app_grpc_executor_max_threads, 1)
          ) > 0.90
        for: 10m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Executor gần cạn capacity: {{ $labels.service }}/{{ $labels.pool }}"
          description: "Queue trên 80% và active workers trên 90% trong 10 phút."
          runbook_url: "https://runbooks.example/grpc/executor-saturation"
~~~

Đây là rule minh họa theo metric contract của bài. Cần kiểm tra tên label thực tế, rule syntax và URL runbook trước khi triển khai. Không để ví dụ domain hoặc threshold chưa được phê duyệt đi thẳng vào production.

## 10. Chọn severity và thời gian duy trì

Một cách phân loại:

| Severity | Điều kiện điển hình | Hành động |
| --- | --- | --- |
| Page | SLO burn nhanh, error rate cao có traffic đáng kể, service không phục vụ | Đánh thức on-call |
| Warning | Queue/pool gần đầy hoặc dependency latency tăng nhưng chưa ảnh hưởng rõ SLO | Tạo ticket/điều tra trong giờ làm việc |
| Info | Spike ngắn hoặc metric bất thường chưa có user impact | Dashboard/event, không page |

Chọn for theo đặc tính metric:

- Error rate có thể dùng cửa sổ rate 5 phút và for vài phút để loại spike ngắn.
- Queue saturation nên tồn tại liên tục trước khi cảnh báo, trừ khi rejection đã gây user impact.
- Hard exhaustion như queue rejection liên tục hoặc database pool timeout có thể cần alert nhanh hơn.
- SLO burn multi-window thường hữu ích hơn một threshold cố định cho mọi method.

Không kéo for quá dài để che giấu noise; alert có thể phát hiện quá muộn. Cũng không đặt for bằng 0 cho metric dao động mạnh nếu chưa đánh giá false positive.

## 11. Alertmanager: grouping, routing và inhibition

Alertmanager giúp tránh gửi hàng trăm thông báo cho cùng một sự cố:

- **Grouping:** gom alert theo service, cluster hoặc team để on-call nhận một thông báo có ngữ cảnh.
- **Routing:** page cho severity cao, warning vào kênh vận hành, info vào dashboard.
- **Deduplication:** gộp các alert giống nhau trong cùng group.
- **Inhibition:** khi service hoàn toàn down, tạm ngăn các alert thứ cấp như queue hoặc dependency latency tạo noise.
- **Silence:** tạm ngừng thông báo trong maintenance window đã được phê duyệt.

Không dùng inhibition để che alert gốc hoặc che lỗi kéo dài. Silence cần owner, lý do và thời điểm hết hạn.

## 12. Runbook phải chỉ ra bước điều tra tiếp theo

Một alert không có runbook thường chỉ tạo thêm thông báo. Runbook cho gRPC high error rate nên hướng dẫn:

1. Xác nhận alert có traffic đủ lớn và SLO classification đúng.
2. Chia theo method và gRPC status để tìm RPC gây lỗi.
3. So sánh client latency với server latency.
4. Mở trace mẫu để tìm span chậm/lỗi.
5. Kiểm tra dependency error/latency, executor queue, rejection và database pool.
6. Kiểm tra rollout/config change gần thời điểm bắt đầu.
7. Áp dụng hành động an toàn: rollback, giảm traffic, scale hoặc disable retry storm theo quy trình.

Runbook saturation nên nêu rõ giới hạn pool, queue capacity, database connection cap và các bước scale. Tăng thread pool không phải lúc nào cũng đúng: có thể làm database/downstream bị quá tải hơn.

## 13. Kiểm thử alert trước khi bật page

Kiểm thử ba phần riêng:

| Loại test | Điều cần xác minh |
| --- | --- |
| Query test | PromQL trả kết quả đúng với dữ liệu mẫu và label thực tế |
| Rule test | for, threshold, traffic floor và multi-window logic firing/resolved đúng |
| Notification test | Alertmanager route đúng team/severity, group/dedup/inhibition đúng |

Tình huống cần mô phỏng:

- Error ratio cao trong traffic lớn.
- Một lỗi trên traffic rất thấp.
- Một status caller error như INVALID_ARGUMENT tăng đột biến nhưng không thuộc availability SLI.
- Queue tăng thoáng qua rồi tự giảm.
- Queue và active workers duy trì gần max.
- Executor bắt đầu reject task.
- Database pool pending tăng và acquisition timeout xuất hiện.
- Dependency latency tăng nhưng server fallback vẫn giữ SLO.
- Telemetry target mất scrape hoặc metric biến mất.
- Sự cố kéo dài qua nhiều cửa sổ burn rate.

Dùng promtool test rules hoặc test framework tương đương để kiểm tra Prometheus rules trong CI. Kiểm tra alert resolved khi dữ liệu trở lại bình thường; alert không nên bị kẹt firing do label hoặc absent series.

## 14. Sai lầm thường gặp

1. **Coi mọi status khác OK là availability failure.** Caller error và lỗi nghiệp vụ có thể là kết quả dự kiến.
2. **Lấy trung bình error ratio của từng instance.** Phải cộng numerator/denominator trước khi chia.
3. **Không có traffic floor.** Một lỗi duy nhất có thể tạo ratio 100% và page sai.
4. **Chỉ dùng một cửa sổ ngắn.** Spike thoáng qua gây alert noise.
5. **Chỉ alert CPU.** Queue, connection pool và rejection có thể cạn trước CPU.
6. **Chỉ alert queue occupancy.** Queue nhỏ hoặc pool không queue cần tín hiệu active/max và rejection.
7. **Tăng pool vô điều kiện.** Có thể chuyển saturation từ executor sang database hoặc downstream.
8. **Không phân biệt warning và page.** On-call bị đánh thức bởi tín hiệu chưa có user impact.
9. **Không có runbook hoặc owner.** Alert không giúp người nhận biết bước xử lý.
10. **Không test alert khi metric mất.** No data có thể bị hiểu nhầm thành zero errors.

## 15. Bài tập vận dụng

Với CatalogService gọi InventoryService và database:

1. Định nghĩa availability SLI và danh sách gRPC status được tính là bad event.
2. Viết PromQL error ratio có traffic floor, tổng hợp theo service/method trước khi chia.
3. Thiết kế burn-rate alert nhiều cửa sổ dựa trên error budget của SLO.
4. Tạo alert executor queue/active worker, rejected task và database pool pending.
5. Phân loại page/warning và chọn for phù hợp với từng tín hiệu.
6. Viết Prometheus rule kèm summary, description và runbook URL.
7. Kiểm thử traffic thấp, spike ngắn, saturation kéo dài, dependency degradation và missing telemetry.
8. Cấu hình Alertmanager grouping, routing, deduplication và inhibition.
9. Diễn tập runbook từ alert tới trace, server method và dependency gây lỗi.

**Tiêu chí hoàn thành:** người học định nghĩa được error SLI theo contract, viết alert error rate không bị sai lệch bởi traffic thấp, phát hiện saturation ở executor và dependency, dùng multi-window SLO burn rate, route alert đúng severity và cung cấp runbook có bước điều tra cụ thể.

### Tài liệu tham khảo

- [Prometheus Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): biểu thức, for, labels và annotations.
- [Prometheus Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/): rate, increase và aggregation trong PromQL.
- [Prometheus Alerting Practices](https://prometheus.io/docs/practices/alerting/): thiết kế alert hướng tới người dùng và giảm noise.
- [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/): routing, grouping, inhibition và silence.
- [Google SRE Workbook](https://sre.google/workbook/alerting-on-slos/): alert theo SLO và error budget burn rate.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): semantics của status trong gRPC.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
