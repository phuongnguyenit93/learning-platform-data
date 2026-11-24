# Alert theo latency percentile trong Spring Boot

Latency percentile cho biết thời gian phản hồi mà một tỷ lệ request đã hoàn tất trong một khoảng thời gian. p95 = 800 ms có nghĩa khoảng 95% requests được quan sát hoàn tất trong 800 ms hoặc nhanh hơn; khoảng 5% còn lại chậm hơn. p99 tập trung vào phần đuôi chậm hơn nữa. Các percentile giúp phát hiện trải nghiệm của nhóm request chậm mà average latency có thể che khuất.

Bài **Alert theo latency percentile** thuộc chương **Dashboard và alert** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể phân biệt histogram và summary, cấu hình histogram phù hợp với Micrometer/Prometheus, tính p95/p99 bằng PromQL, thiết kế alert theo latency SLO và traffic volume, tránh cảnh báo sai ở traffic thấp, và điều tra alert bằng route metrics, logs và traces.

## 1. Percentile nói lên điều gì?

Average latency có thể che giấu tail latency. Nếu 99 requests mất 100 ms và một request mất 10 giây, average khoảng 199 ms; con số này không thể hiện rõ request chậm nhất đã ảnh hưởng tới một người dùng.

Percentile sắp xếp thời gian request và lấy một điểm trong phân phối:

- **p50:** median; một nửa requests nhanh hơn hoặc bằng giá trị này.
- **p90:** 90% requests nhanh hơn hoặc bằng giá trị này.
- **p95:** 95% requests nhanh hơn hoặc bằng giá trị này.
- **p99:** 99% requests nhanh hơn hoặc bằng giá trị này.
- **p99.9:** tập trung vào phần đuôi rất nhỏ, thường cần lượng traffic lớn để ước lượng ổn định.

Ví dụ p95 = 750 ms và p99 = 2,4 s cho thấy phần lớn requests phản hồi nhanh nhưng một nhóm nhỏ có tail latency cao. Không diễn giải p99 là “request tệ nhất”; nó là một quantile của phân phối.

## 2. Chọn percentile theo mục tiêu vận hành

Percentile cần gắn với trải nghiệm và SLO, không chọn chỉ vì dashboard phổ biến có p99.

| Percentile | Cách sử dụng thường gặp | Hạn chế |
| --- | --- | --- |
| p50 | Theo dõi baseline và thay đổi latency phổ biến | Không thể hiện tail |
| p90/p95 | Cảnh báo trải nghiệm phần lớn người dùng | Có thể bỏ qua tail rất chậm |
| p99 | Theo dõi tail latency cho endpoint quan trọng | Dao động ở traffic thấp |
| p99.9 | Điều tra tail cực đoan ở hệ thống traffic lớn | Cần nhiều observations và histogram đủ chi tiết |

Đặt mục tiêu theo route/operation nếu chúng có latency budget khác nhau. Một endpoint đọc cache không nhất thiết dùng cùng ngưỡng với endpoint tạo báo cáo hoặc xử lý thanh toán.

## 3. Histogram và summary

Để tính percentile trong Prometheus, cần hiểu metric representation:

| Loại metric | Cách hoạt động | Percentile ở đâu? |
| --- | --- | --- |
| Histogram | Đếm observations theo các bucket tích lũy | Backend có thể tính quantile từ bucket counts |
| Summary | Client tính quantiles và export các quantile đã cấu hình | Quantile được tính ở process; không thể tổng hợp chính xác qua nhiều instances như histogram buckets |

Với Prometheus, histogram thường phù hợp hơn khi cần percentile tổng hợp toàn service hoặc theo route qua nhiều pods. Summary quantiles từ nhiều instances không thể cộng/trung bình để tạo quantile toàn cụm chính xác.

Histogram quantile là ước lượng dựa trên bucket boundaries; độ chính xác phụ thuộc bucket layout và phân phối dữ liệu. Bucket cần bao phủ vùng latency mục tiêu và tail cần theo dõi.

## 4. Bật histogram cho HTTP server requests

Spring Boot/Micrometer có thể bật percentile histogram cho HTTP server request Timer qua distribution configuration. Ví dụ minh họa:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Tên meter filter và property binding cần kiểm tra theo Spring Boot/Micrometer version. Một số dự án dùng tên meter `http.server.requests`; Prometheus export thường chuẩn hóa thành `http_server_requests_seconds`. Xác minh scrape output trước khi viết query.

Nếu cần bucket boundaries cụ thể, cấu hình service-level SLO boundaries hoặc explicit buckets theo hỗ trợ của registry/version. Không bật histogram cho mọi meter một cách rộng rãi khi chưa đánh giá cardinality và storage cost.

## 5. Histogram buckets và Prometheus series

Prometheus histogram thường xuất các series:

```text
http_server_requests_seconds_bucket{le="0.1",...}
http_server_requests_seconds_bucket{le="0.25",...}
http_server_requests_seconds_bucket{le="0.5",...}
http_server_requests_seconds_bucket{le="1.0",...}
http_server_requests_seconds_bucket{le="+Inf",...}
http_server_requests_seconds_count{...}
http_server_requests_seconds_sum{...}
```

Label `le` biểu thị upper bound của bucket. Bucket counts là cumulative: bucket `le="1.0"` bao gồm observations nhỏ hơn hoặc bằng 1 giây, kể cả observations đã được đếm ở bucket nhỏ hơn.

Histogram thêm nhiều series cho mỗi tổ hợp label. Nếu có nhiều routes, methods, status, exception, instance và custom tags, chi phí series có thể tăng nhanh. Dùng route template và labels hữu hạn; chỉ bật histogram cho các meter cần percentile.

## 6. Tính p95 bằng histogram_quantile

PromQL tính p95 toàn service:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Để tính p99, thay `0.95` bằng `0.99`. Dùng `rate()` trên bucket counters trước khi aggregate để xử lý counter resets theo từng instance.

Không bỏ label `le` khỏi aggregation trước khi gọi `histogram_quantile`; hàm cần bucket boundaries để nội suy quantile.

## 7. Percentile theo service, route và method

Theo service nếu label `service` tồn tại:

```promql
histogram_quantile(
  0.95,
  sum by (service, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Theo route:

```promql
histogram_quantile(
  0.95,
  sum by (uri, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Theo method và route:

```promql
histogram_quantile(
  0.99,
  sum by (method, uri, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Các label trong ví dụ chỉ mang tính minh họa. Chỉ group theo labels thực sự có trong series và cần cho quyết định vận hành. Dùng URI route template, không dùng raw URL chứa IDs hoặc query parameters.

## 8. Chọn cửa sổ thời gian

Percentile được tính trên observations trong cửa sổ query. Cửa sổ ngắn phản ứng nhanh nhưng dễ nhiễu; cửa sổ dài ổn định hơn nhưng có thể làm chậm phát hiện sự cố.

| Window | Đặc điểm | Dùng khi |
| --- | --- | --- |
| 1m | Phản ứng nhanh, nhạy với burst | Dashboard điều tra hoặc traffic lớn |
| 5m | Cân bằng tốc độ và độ ổn định | Alert phổ biến cho service có traffic đều |
| 15m | Mượt hơn, phản ứng chậm hơn | Xu hướng và cảnh báo suy giảm kéo dài |
| 1h | Xu hướng dài hạn | Capacity planning, không phù hợp phát hiện sự cố nhanh |

Không có window đúng cho mọi service. Kiểm tra scrape interval, evaluation interval, request volume và tốc độ thay đổi của workload. Với scrape interval 30 giây, cửa sổ 1 phút chỉ có rất ít samples.

## 9. Alert p95 vượt latency objective

Ví dụ Prometheus alert rule khi p95 lớn hơn 800 ms liên tục:

```yaml
groups:
  - name: spring-boot-latency
    rules:
      - alert: HttpP95LatencyHigh
        expr: |
          histogram_quantile(
            0.95,
            sum by (service, le) (
              rate(http_server_requests_seconds_bucket[5m])
            )
          ) > 0.8
        for: 10m
        labels:
          severity: page
        annotations:
          summary: HTTP p95 latency is above objective
          description: Inspect route latency, errors and dependency traces.
```

Ngưỡng 0,8 là giây, không phải millisecond. Giá trị và `for` chỉ là ví dụ; đặt theo SLO, route criticality và baseline. Thêm `service`/`environment` labels theo schema của Prometheus.

Một alert theo p95 không đủ nếu traffic thấp. Nên kết hợp với minimum request volume để tránh cảnh báo từ vài observations:

```promql
histogram_quantile(
  0.95,
  sum by (service, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
) > 0.8
and
sum by (service) (
  rate(http_server_requests_seconds_count[5m])
) > 1
```

Ngưỡng 1 request/giây chỉ là ví dụ. Với endpoint ít traffic nhưng critical, dùng synthetic monitoring hoặc alert theo transaction-specific SLI.

## 10. Tail latency và SLO

Latency SLO thường định nghĩa tỷ lệ requests hoàn tất dưới một threshold, ví dụ 99% requests dưới 500 ms. Điều này gần với một good-event ratio hơn là chỉ theo dõi p99 line trên dashboard.

Nếu histogram có bucket boundary tại 0,5 giây, có thể tính tỷ lệ requests dưới ngưỡng:

```promql
sum(rate(http_server_requests_seconds_bucket{le="0.5"}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

Đây là tỷ lệ request có duration không vượt quá 500 ms theo bucket. Bucket boundary phải tồn tại đúng như label value; nếu không có bucket `le="0.5"`, cần cấu hình boundary hoặc dùng bucket gần nhất với hiểu biết về sai số.

Với SLO latency, alert theo tỷ lệ good events có thể dễ diễn giải và phù hợp error budget hơn một p99 threshold đơn lẻ. Percentile vẫn hữu ích để debug tail và hiển thị trải nghiệm phân phối.

## 11. Multi-window và burn-rate alerts

Một spike p95 ngắn có thể tự hết, còn một mức suy giảm vừa phải kéo dài có thể tiêu thụ error budget đáng kể. Alert nhiều cửa sổ kết hợp:

- Window ngắn để phát hiện sự cố ảnh hưởng lớn ngay lập tức.
- Window dài để xác nhận suy giảm có kéo dài.
- Traffic volume để tránh kết luận từ ít samples.
- SLO burn rate để gắn alert với budget.

Không dùng cùng một threshold percentile cho tất cả routes. Endpoint có latency objective khác nhau cần rule riêng hoặc labels/policies được quản lý. Với hệ thống SLO, ưu tiên multi-window burn rate trên latency good-event ratio đã được thống nhất.

## 12. Loại trừ traffic không đại diện người dùng

Health probes, synthetic checks và internal calls có thể ảnh hưởng percentile. Trước khi loại traffic, xác định dashboard đang đo user experience hay toàn bộ server workload.

Nếu probe có route riêng, filter cùng một cách ở mọi bucket và count series:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri!~"/actuator/health.*"
    }[5m])
  )
)
```

Không loại traffic chỉ vì nó nội bộ nếu chính traffic đó là dependency quan trọng. Ghi rõ scope và filter của panel/rule để người xem hiểu percentile đang đại diện cho nhóm request nào.

## 13. Cardinality và bucket design

Histogram series count tăng theo số bucket nhân với số tổ hợp labels. Giữ cardinality trong budget:

- Dùng route template thay vì raw URI.
- Không thêm request ID, trace ID, user ID hoặc exception message làm label.
- Chỉ bật percentile histogram cho meter cần thiết.
- Chọn bucket tập trung quanh latency objective và tail cần theo dõi.
- Review series count sau khi thêm route hoặc custom tags.

Bucket quá rộng làm percentile ít chính xác ở vùng quan trọng. Bucket quá dày làm tăng series/storage cost. Nếu SLO là 500 ms, nên có boundary gần 500 ms thay vì chỉ có bucket 0,1 và 1 giây.

## 14. Kiểm thử alert rules

Kiểm thử cần xác minh cả metric data và alert semantics:

| Test | Điều cần chứng minh |
| --- | --- |
| Histogram enabled | Bucket series xuất hiện trên scrape endpoint |
| p95 query | Quantile tính đúng với fixture buckets đã biết |
| p99 query | Tail query dùng đúng quantile và aggregation labels |
| Instance aggregation | Counter reset không làm hỏng rate/aggregate |
| Low traffic | Minimum-volume guard ngăn false page |
| No traffic | Rule xử lý no data theo policy |
| Route filter | Probe/route exclusions áp dụng nhất quán |
| SLO bucket | Boundary cần thiết tồn tại và good-event ratio đúng |
| Alert duration | `for` và evaluation windows hoạt động như dự kiến |

Prometheus `promtool test rules` có thể chạy alert rule tests với series fixtures. Dùng fixture có nhiều instances và bucket boundaries để phát hiện lỗi thiếu `le` trong aggregation hoặc chia sai denominator.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| p95 query không có dữ liệu | Histogram chưa bật hoặc metric name sai | Kiểm tra scrape output và meter configuration |
| p95 bằng 0 hoặc không hợp lý | Bucket aggregation thiếu `le` hoặc sai labels | Kiểm tra raw bucket series và PromQL grouping |
| p99 dao động mạnh | Traffic thấp hoặc bucket quá thưa | Tăng volume window, xem p95 và good-event ratio |
| Alert luôn firing | Ngưỡng thấp hơn baseline hoặc đơn vị ms/seconds nhầm | Xác minh unit và SLO threshold |
| Alert không firing | Thiếu histogram buckets, label mismatch hoặc no data | Query trực tiếp và kiểm tra rule evaluation |
| Percentile theo pod khác service-level | Quantile được tính riêng rồi aggregate sai | Sum bucket rates trước histogram_quantile |
| Series tăng mạnh sau bật histogram | Nhiều labels kết hợp với nhiều buckets | Giảm labels và chỉ bật histogram cần thiết |
| Probe làm p95 tốt giả tạo | Probe request rất nhanh chiếm denominator | Xác định scope và lọc probe đồng nhất |
| SLO latency query trả no data | Bucket boundary không tồn tại chính xác | Cấu hình explicit bucket tại threshold |
| Summary quantile không tổng hợp được | Summary quantiles không merge chính xác giữa instances | Dùng histogram buckets cho aggregate quantiles |

## 16. Tình huống thực tế: p99 tăng sau khi nâng database pool load

**Bối cảnh giả định:** Sau một đợt traffic tăng, p50 của orders-service vẫn khoảng 90 ms nhưng p99 tăng từ 700 ms lên 3,2 giây. Error rate chưa tăng đáng kể. Alert p99 kích hoạt liên tục.

Quy trình điều tra:

1. **Xác minh query:** kiểm tra histogram đã bật, bucket boundaries, đơn vị giây và aggregation qua mọi instances.
2. **Kiểm tra traffic:** xem request rate để xác nhận quantile có đủ observations và không bị probe traffic chi phối.
3. **Khoanh vùng route:** group p95/p99 theo route template và method để tìm endpoint tail latency.
4. **Đối chiếu saturation:** xem Hikari pending/acquire time, database query latency, CPU throttling và thread pools.
5. **Mở traces:** chọn exemplar/trace đại diện request chậm, xác định span downstream kéo dài.
6. **So sánh deployment/config:** kiểm tra pool size, concurrency và thay đổi query/index gần thời điểm alert.
7. **Xác minh:** theo dõi p99, tỷ lệ requests dưới latency objective, request volume và error rate sau remediation.

p50 ổn định không chứng minh hệ thống khỏe; tail latency có thể ảnh hưởng nhóm người dùng nhỏ nhưng quan trọng. Dùng percentile cùng good-event ratio và traces để đánh giá tác động.

## 17. Bài tập tự kiểm tra

**Bài 1.** p95 = 800 ms có nghĩa gì?

*Gợi ý:* Khoảng 95% observations có duration không vượt quá 800 ms trong cửa sổ đo.

**Bài 2.** Vì sao không thể lấy trung bình p99 của từng pod để ra p99 toàn service?

*Gợi ý:* Quantiles không cộng/trung bình được; tổng hợp histogram buckets trước rồi tính quantile.

**Bài 3.** Histogram khác summary ở điểm nào khi aggregate nhiều instances?

*Gợi ý:* Histogram buckets có thể aggregate; summary quantiles được tính cục bộ và không merge chính xác.

**Bài 4.** Vì sao p99 alert cần minimum traffic guard?

*Gợi ý:* Một vài observations có thể làm quantile dao động lớn và tạo false alert.

**Bài 5.** `histogram_quantile` cần giữ label nào khi aggregate?

*Gợi ý:* Giữ `le` để hàm biết bucket boundaries; thêm service/route nếu cần group theo chiều đó.

**Bài 6.** Nếu latency SLO là 500 ms, vì sao cần bucket tại hoặc gần 0,5 giây?

*Gợi ý:* Good-event ratio theo threshold cần bucket boundary tương ứng; bucket gần nhất ảnh hưởng độ chính xác.

**Bài 7.** p50 ổn định nhưng p99 tăng gợi ý điều gì?

*Gợi ý:* Một nhóm nhỏ request đang chậm; điều tra route, DB pool, downstream và saturation.

**Bài 8.** Khi nào nên alert theo good-event ratio thay vì chỉ p99?

*Gợi ý:* Khi SLO định nghĩa tỷ lệ requests hoàn tất dưới latency threshold và cần gắn alert với error budget.

## 18. Ghi nhớ

- Percentile mô tả phân phối latency; p95/p99 giúp nhìn tail mà average có thể che khuất.
- Histogram phù hợp để aggregate quantiles qua nhiều instances; summary quantiles không thể merge chính xác theo cách cộng/trung bình.
- Bật Micrometer percentile histogram có chủ đích và xác minh Prometheus bucket series/labels thực tế.
- Dùng `histogram_quantile` trên `rate()` của bucket counters; aggregate trước quantile và giữ label `le`.
- Chọn percentile, threshold và window theo SLO, route criticality, scrape interval và request volume.
- Kết hợp minimum traffic guard, xử lý no-data và phân biệt seconds với milliseconds để giảm false alerts.
- Thiết kế bucket quanh latency objective; quản lý label cardinality và không dùng raw IDs/URLs.
- Với latency SLO, good-event ratio/burn-rate alerts bổ sung cho p95/p99; drilldown qua route, saturation, logs và traces.
