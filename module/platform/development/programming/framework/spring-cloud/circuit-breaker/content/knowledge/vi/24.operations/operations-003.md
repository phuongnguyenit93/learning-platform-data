# Phát hành thử ngưỡng mới trên một nhóm replica

Khi thay đổi ngưỡng circuit breaker trong hệ thống Spring Cloud, không nên áp dụng ngay cho toàn bộ replica nếu chưa biết cấu hình mới sẽ tác động thế nào dưới tải thực tế. Có thể phát hành thử cấu hình trên một nhóm replica riêng, chuyển một phần traffic có kiểm soát đến nhóm đó, rồi so sánh hành vi với nhóm đang chạy cấu hình ổn định.

Cách làm này thường được gọi là canary rollout. Với Resilience4j, mỗi tiến trình thường giữ instance circuit breaker và sliding window cục bộ. Vì vậy, một nhóm replica canary có thể chạy ngưỡng mới trong khi nhóm stable tiếp tục dùng ngưỡng cũ. Nhóm vận hành quan sát tỷ lệ lỗi, lời gọi chậm, số lần mở mạch, fallback và độ trễ trước khi quyết định mở rộng hoặc rollback.

## Vì sao phát hành thử ngưỡng circuit breaker?

Các ngưỡng như `failureRateThreshold`, `slowCallDurationThreshold`, `slowCallRateThreshold` và `minimumNumberOfCalls` ảnh hưởng trực tiếp đến thời điểm circuit breaker chuyển từ CLOSED sang OPEN. Thay đổi ngưỡng có thể cải thiện khả năng bảo vệ, nhưng cũng có thể làm mạch mở quá sớm hoặc quá muộn.

Ví dụ, giảm `slowCallDurationThreshold` từ 2 giây xuống 800 ms làm nhiều lời gọi bị phân loại là chậm hơn. Nếu dịch vụ vốn thường phản hồi trong khoảng 900 ms ở giờ cao điểm, cấu hình mới có thể làm slow call rate tăng và mạch mở thường xuyên. Ngược lại, tăng `failureRateThreshold` quá cao có thể khiến ứng dụng tiếp tục gửi nhiều lời gọi đến phụ thuộc đang lỗi.

Phát hành thử giúp trả lời các câu hỏi:

- Cấu hình mới có phát hiện sự suy giảm sớm hơn không?
- Mạch có mở quá thường xuyên trong điều kiện tải bình thường không?
- Tỷ lệ fallback và từ chối nhanh có tăng ngoài dự kiến không?
- Người dùng có nhận nhiều lỗi hoặc dữ liệu suy giảm hơn không?
- Cấu hình mới có hoạt động ổn định khi lưu lượng tăng và khi phụ thuộc phục hồi không?

Thay đổi ngưỡng cần được đánh giá cùng hành vi nghiệp vụ. Một circuit breaker mở nhiều hơn có thể giảm áp lực lên phụ thuộc, nhưng cũng có thể làm nhiều request chuyển sang fallback. Mục tiêu là tìm điểm cân bằng giữa bảo vệ hệ thống và khả năng phục vụ.

## Tách nhóm canary và stable

Để so sánh có ý nghĩa, cần phân biệt rõ replica dùng cấu hình cũ và replica dùng cấu hình mới. Có thể triển khai hai nhóm Deployment:

- **Stable:** tiếp tục chạy phiên bản và cấu hình đã được xác nhận.
- **Canary:** chạy cùng ứng dụng hoặc cùng phiên bản tương thích, nhưng nạp bộ ngưỡng circuit breaker mới.

Mỗi nhóm nên có nhãn hoặc thuộc tính nhận diện rõ ràng, ví dụ `track=stable` và `track=canary`. Tên circuit breaker có thể giống nhau trong hai nhóm, chẳng hạn `inventory-read`, vì mỗi tiến trình có registry và trạng thái riêng. Tuy nhiên, metrics cần có nhãn triển khai hoặc nhóm phát hành để phân biệt số liệu stable với canary.

~~~mermaid
flowchart TD
    A[Gateway hoặc bộ định tuyến traffic] -->|Phần lớn traffic| B[Nhóm stable]
    A -->|Một tỷ lệ nhỏ| C[Nhóm canary]
    B --> D[Cấu hình circuit breaker cũ]
    C --> E[Cấu hình circuit breaker mới]
    D --> F[Metrics và log stable]
    E --> G[Metrics và log canary]
    F --> H[So sánh cùng cửa sổ thời gian]
    G --> H
    H --> I{Đạt điều kiện phát hành?}
    I -->|Có| J[Tăng dần tỷ lệ canary]
    I -->|Không| K[Rollback nhóm canary]
~~~

Không nên chỉ thay ConfigMap đang được cả stable và canary dùng chung, vì như vậy hai nhóm có thể cùng nhận cấu hình mới và mất khả năng so sánh. Hãy cấp cấu hình riêng theo Deployment, profile hoặc nguồn cấu hình có nhãn riêng.

## Quản lý cấu hình theo profile

Spring Boot có thể nạp cấu hình riêng theo profile. Ví dụ, cấu hình mặc định của nhóm stable được giữ trong `application.yml`, còn nhóm canary nạp thêm `application-canary.yml`.

Cấu hình stable minh họa:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 40
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 5
~~~

Cấu hình canary minh họa thay đổi ngưỡng thời gian và tỷ lệ lời gọi chậm:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 40
        failureRateThreshold: 50
        slowCallDurationThreshold: 1200ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 5
~~~

Trong ví dụ, canary nhạy hơn với lời gọi chậm: thời lượng phân loại chậm giảm từ 2 giây xuống 1,2 giây và tỷ lệ chậm cho phép giảm từ 60% xuống 50%. Các giá trị này chỉ minh họa cách tách cấu hình; cần chọn ngưỡng dựa trên SLO, độ trễ nền và lưu lượng thật.

Có thể bật profile canary bằng biến môi trường trong Deployment:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: canary
~~~

Nếu stable không bật profile canary, nó tiếp tục nạp cấu hình mặc định. Trong môi trường thực tế, có thể dùng ConfigMap riêng cho từng Deployment hoặc Spring Cloud Config với label/profile tách biệt. Điều quan trọng là xác minh mỗi nhóm thực sự nạp đúng bộ giá trị.

Không nên giả định thay đổi file ConfigMap sẽ tự động cập nhật instance circuit breaker đang chạy. Việc file được mount cập nhật không đồng nghĩa Spring Boot và Resilience4j đã tái tạo hoặc cập nhật instance. Nếu cơ chế refresh của phiên bản và ứng dụng không bảo đảm cập nhật cấu hình circuit breaker, hãy triển khai rollout để tiến trình mới nạp cấu hình mới. Sau rollout, kiểm tra cấu hình hiệu lực qua endpoint hoặc log cấu hình đã được bảo vệ, không công khai dữ liệu nhạy cảm.

## Giữ điều kiện so sánh công bằng

Canary chỉ có giá trị khi nhóm stable và canary nhận workload tương đương. Nếu canary chỉ nhận request đọc cache còn stable nhận cả thao tác ghi, tỷ lệ lỗi và độ trễ sẽ không thể so sánh trực tiếp.

Trước khi chuyển traffic, hãy xác định:

- Cùng loại endpoint và thao tác nghiệp vụ được gửi đến hai nhóm.
- Tỷ lệ request, kích thước payload và phân bố tenant tương đương.
- Cùng phiên bản ứng dụng hoặc chỉ khác đúng cấu hình đang thử nghiệm.
- Cùng dependency, timeout HTTP client, retry và bulkhead, trừ khi đó cũng là thay đổi được chủ ý kiểm thử.
- Cùng cách thu thập metrics và cùng khoảng thời gian quan sát.

Nếu thay đổi nhiều chính sách cùng lúc, sẽ khó xác định nguyên nhân khi kết quả khác nhau. Trong một đợt canary ngưỡng circuit breaker, nên thay đổi một nhóm tham số có quan hệ trực tiếp và ghi lại chính xác giá trị cũ/mới.

## Chọn tỷ lệ traffic và kích thước nhóm canary

Có thể bắt đầu với một replica canary hoặc một tỷ lệ traffic nhỏ, sau đó tăng dần khi số liệu ổn định. Tỷ lệ cụ thể phụ thuộc vào lưu lượng, mức độ rủi ro và khả năng cô lập traffic.

Một tiến trình circuit breaker thường giữ sliding window riêng. Nếu có một canary replica nhưng chỉ nhận vài request mỗi phút, nó có thể không đạt `minimumNumberOfCalls` trong thời gian quan sát. Khi đó, circuit breaker chưa có đủ mẫu để đánh giá failure rate hoặc slow call rate. Việc dashboard tổng hợp nhiều replica có đủ mẫu không làm cho sliding window cục bộ của một replica tự động có đủ mẫu.

Hãy tính sơ bộ số mẫu canary nhận được:

`Số mẫu trong thời gian quan sát ≈ lưu lượng mỗi giây × tỷ lệ traffic canary × số giây quan sát`

Ví dụ, dịch vụ nhận 100 request/giây, canary nhận 5% traffic trong 60 giây. Tổng số request vào nhóm canary khoảng 300. Nếu có ba replica canary chia tải tương đối đều, mỗi replica nhận khoảng 100 request trong phút đó. Với `minimumNumberOfCalls=40`, từng replica có khả năng đủ mẫu để bắt đầu đánh giá. Đây chỉ là ước lượng; cần kiểm tra phân phối thực tế và số lời gọi thực sự đi qua circuit breaker.

Nếu traffic thấp, có thể tăng thời gian quan sát hoặc dùng nhóm canary nhỏ hơn để tăng số mẫu trên mỗi instance. Không nên hạ `minimumNumberOfCalls` chỉ để canary mở mạch nhanh hơn mà không đánh giá ảnh hưởng đến độ tin cậy thống kê.

## Điều hướng traffic đến canary

Cần dùng cơ chế định tuyến có thể tách nhóm stable và canary, chẳng hạn Gateway, ingress controller, service mesh hoặc rollout controller hỗ trợ weighted traffic. Kubernetes Service thông thường chọn endpoint theo selector; nó không tự chia tỷ lệ 95/5 giữa hai Deployment chỉ vì cả hai có cùng nhãn ứng dụng.

Một cách triển khai là tạo hai Service riêng:

- `inventory-api-stable` chọn pod có `track: stable`.
- `inventory-api-canary` chọn pod có `track: canary`.

Sau đó, Gateway hoặc service mesh định tuyến một tỷ lệ nhỏ request đến Service canary. Cần bảo đảm session affinity hoặc phân phối tenant không làm canary nhận một tập request khác biệt quá nhiều so với stable. Nếu dùng sticky routing, hãy theo dõi phân bố traffic thực tế thay vì chỉ tin vào trọng số cấu hình.

Ví dụ cấu trúc nhãn Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-api-canary
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory-api
      track: canary
  template:
    metadata:
      labels:
        app: inventory-api
        track: canary
    spec:
      containers:
        - name: inventory-api
          image: example/inventory-api:1.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: canary
~~~

Đây là phần minh họa Deployment; cần khai báo Service và cấu hình weighted routing tương ứng trong nền tảng triển khai đang dùng. Không đưa pod canary vào cùng một backend không phân biệt với stable nếu mục tiêu là kiểm soát tỷ lệ traffic rõ ràng.

## Theo dõi circuit breaker riêng theo nhóm

Cần gắn nhãn triển khai vào metrics hoặc log để tách stable và canary. Các chỉ số quan trọng gồm:

- Failure rate và số lời gọi thất bại.
- Slow call rate và số lời gọi chậm.
- Độ trễ p50, p95 và p99.
- Số lần chuyển CLOSED → OPEN và OPEN → HALF_OPEN.
- Số lời gọi bị từ chối do mạch OPEN.
- Số lần fallback và loại kết quả fallback.
- Tỷ lệ HTTP 5xx, timeout và lỗi kết nối.
- Tỷ lệ request thành công ở cấp nghiệp vụ.

Ví dụ các chiều phân tích metrics:

| Nhãn | Giá trị minh họa | Mục đích |
|---|---|---|
| `deployment_track` | stable / canary | So sánh nhóm phát hành. |
| `service` | inventory-api | Xác định dịch vụ. |
| `circuit_breaker` | inventory-read | Xác định luồng được bảo vệ. |
| `config_revision` | cb-threshold-2026-11 | Gắn kết quả với phiên bản cấu hình. |
| `outcome` | success / failure / slow / rejected | Phân loại kết quả. |

Các nhãn phải có miền giá trị giới hạn. Không thêm SKU, user ID, order ID hoặc request ID vào metrics. Có thể ghi các giá trị đó trong trace hoặc log theo chính sách dữ liệu của ứng dụng.

Nên so sánh tỷ lệ và phân vị, không chỉ số đếm tuyệt đối. Nếu canary nhận 5% traffic, số lỗi tuyệt đối có thể thấp hơn stable ngay cả khi tỷ lệ lỗi cao hơn. Hãy so sánh trên cùng endpoint, cùng khoảng thời gian và cùng nhóm request.

## Đặt tiêu chí promotion và rollback trước khi bắt đầu

Trước khi chuyển traffic, hãy ghi lại baseline của stable và xác định điều kiện để tăng traffic hoặc rollback. Không nên chờ đến khi có sự cố mới quyết định ngưỡng chấp nhận.

Ví dụ các tiêu chí có thể dùng:

| Chỉ số | Điều kiện promotion minh họa | Dấu hiệu rollback |
|---|---|---|
| Tỷ lệ lỗi nghiệp vụ | Không tăng đáng kể so với stable. | Tăng vượt biên độ cho phép hoặc ảnh hưởng giao dịch cốt lõi. |
| p95/p99 latency | Không vượt SLO và không xấu đi đáng kể. | Độ trễ tăng kéo dài hoặc request timeout tăng. |
| Fallback rate | Tăng trong giới hạn dự kiến của thay đổi. | Fallback tăng đột biến hoặc trả dữ liệu suy giảm quá nhiều. |
| Circuit breaker open rate | Phù hợp với tín hiệu lỗi/chậm thực tế. | Mạch mở liên tục trong điều kiện tải bình thường. |
| Dependency load | Không vượt năng lực phụ thuộc. | Tải hoặc connection pool tăng tới mức nguy hiểm. |
| Số mẫu | Đủ minimumNumberOfCalls trên các replica canary. | Không đủ mẫu để đưa ra kết luận; kéo dài quan sát hoặc điều chỉnh kế hoạch. |

Các điều kiện phải được lượng hóa theo SLO và đặc tính nghiệp vụ. Không có một tỷ lệ promotion chung phù hợp cho mọi hệ thống. Nếu canary thiếu mẫu hoặc traffic không đại diện, kết quả nên được xem là chưa đủ bằng chứng, không phải mặc nhiên đạt.

## Quy trình phát hành tăng dần

Một trình tự triển khai có kiểm soát có thể gồm:

1. **Ghi baseline:** lưu cấu hình hiện tại, metrics stable và tình trạng phụ thuộc trước thay đổi.
2. **Chuẩn bị canary:** tạo nhóm replica riêng, nạp profile hoặc ConfigMap chứa ngưỡng mới.
3. **Xác minh cấu hình:** kiểm tra tên instance, giá trị threshold, timeout và phiên bản config trên từng pod canary.
4. **Smoke test:** gửi một số request có kiểm soát để xác nhận canary hoạt động và metrics mang đúng nhãn.
5. **Chuyển traffic nhỏ:** định tuyến một tỷ lệ thấp đến canary, giữ stable phục vụ phần còn lại.
6. **Quan sát đủ mẫu:** đợi mỗi instance canary có đủ số lời gọi tối thiểu và theo dõi trong điều kiện tải đại diện.
7. **Đánh giá:** so sánh failure rate, slow call rate, latency, fallback, trạng thái mạch và chỉ số nghiệp vụ.
8. **Tăng dần:** nếu đạt tiêu chí, tăng tỷ lệ traffic theo từng bước, ví dụ 5%, 10%, 25%, 50% rồi 100%.
9. **Hoàn tất:** sau khi toàn bộ traffic dùng cấu hình mới và ổn định, cập nhật cấu hình stable theo cùng giá trị đã xác nhận.
10. **Dọn canary:** loại bỏ cấu hình và tài nguyên canary khi không còn cần thiết, đồng thời giữ lại lịch sử thay đổi và metrics.

Các mức traffic trên chỉ là ví dụ. Có thể dùng bước nhỏ hơn nếu dịch vụ quan trọng hoặc lưu lượng lớn. Sau mỗi lần tăng tỷ lệ, cần quan sát lại vì hành vi ở 5% traffic có thể khác khi 50% traffic cùng dùng cấu hình mới.

## Rollback khi canary không đạt

Rollback cần khôi phục đường traffic và cấu hình stable một cách nhanh chóng:

- Dừng chuyển thêm traffic đến canary.
- Đưa tỷ lệ canary về 0% hoặc chuyển request về stable.
- Giữ lại log, metrics và revision cấu hình để điều tra.
- Nếu cần, scale down hoặc loại nhóm canary khỏi Service.
- Xác minh stable tiếp tục nhận traffic và các chỉ số trở về baseline.
- Không xóa bằng chứng về trạng thái circuit breaker, fallback và lỗi đã xảy ra.

Nếu thay đổi chỉ nằm trong cấu hình canary, rollback thường là chuyển traffic về stable và dừng nhóm canary. Nếu cấu hình mới đã được áp dụng trên toàn bộ replica, cần phát hành lại cấu hình cũ bằng rollout có kiểm soát. Không nên chỉ sửa file cấu hình mà không xác nhận tiến trình đang chạy đã nạp lại giá trị cũ.

Cũng cần lưu ý trạng thái circuit breaker không nhất thiết được giữ lại khi pod restart. Replica mới có thể bắt đầu với trạng thái CLOSED và sliding window rỗng. Sau rollback, theo dõi cẩn thận giai đoạn warm-up để tránh nhầm việc chưa đủ mẫu với việc phụ thuộc đã khỏe hoàn toàn.

## Những rủi ro cần tránh

| Rủi ro | Hệ quả | Cách giảm thiểu |
|---|---|---|
| Stable và canary dùng chung ConfigMap có thể thay đổi đồng thời | Mất nhóm đối chứng và không biết cấu hình nào đang chạy. | Tách cấu hình theo Deployment/profile hoặc revision. |
| Canary nhận traffic không đại diện | Metrics không thể so sánh công bằng. | Giữ cùng loại request và kiểm tra phân bố traffic. |
| Mỗi replica canary không đủ mẫu | Circuit breaker không đánh giá được threshold. | Tính sample rate theo từng instance và kéo dài thời gian quan sát. |
| Chỉ so sánh số lỗi tuyệt đối | Nhóm nhận nhiều traffic có số lỗi cao hơn dù tỷ lệ thấp hơn. | So sánh tỷ lệ và phân vị trên cùng workload. |
| Thay nhiều policy cùng lúc | Khó xác định nguyên nhân kết quả thay đổi. | Thay đổi có phạm vi rõ và ghi lại revision. |
| Giả định cấu hình tự refresh | Pod vẫn chạy giá trị cũ dù ConfigMap đã đổi. | Xác minh cơ chế refresh hoặc rollout pod mới. |
| Chỉ theo dõi trạng thái OPEN | Bỏ lỡ latency và fallback tăng trước khi mạch mở. | Theo dõi failure rate, slow call rate, latency và outcome nghiệp vụ. |
| Canary bị restart liên tục | Sliding window bị reset, số mẫu không ổn định. | Theo dõi restart và readiness; dừng rollout khi có bất thường. |

## Kiểm tra sau khi phát hành

Sau khi hoàn tất rollout, cần xác nhận:

- Tất cả replica đang chạy đúng revision cấu hình dự kiến.
- Tên circuit breaker khớp với cấu hình Resilience4j.
- Mỗi nhóm có metrics phân biệt được stable/canary trong giai đoạn so sánh.
- Traffic không còn đi vào nhóm canary cũ nếu đã rollback hoặc kết thúc thử nghiệm.
- Không có fallback hoặc từ chối nhanh tăng bất thường sau khi promotion.
- Các replica có đủ mẫu và trạng thái circuit breaker ổn định sau warm-up.
- Dashboard, cảnh báo và tài liệu vận hành tham chiếu đúng revision đã phát hành.

Đừng chỉ kiểm tra cấu hình trong repository. Hãy xác minh giá trị hiệu lực ở tiến trình đang chạy bằng log khởi tạo có kiểm soát, endpoint nội bộ được bảo vệ hoặc thông tin deployment. Nếu có nhiều nguồn cấu hình, cần biết giá trị cuối cùng được Spring Boot nạp từ nguồn nào.

## Checklist vận hành

1. Lưu baseline và revision cấu hình hiện tại.
2. Tách nhóm stable và canary bằng Deployment, profile hoặc cấu hình độc lập.
3. Chọn tỷ lệ traffic nhỏ nhưng đủ để từng circuit breaker có số mẫu cần thiết.
4. Giữ workload canary tương đương stable.
5. Xác minh threshold mới thực sự được nạp trên từng replica.
6. Theo dõi failure rate, slow call rate, latency, fallback, open transitions và lỗi nghiệp vụ.
7. Chỉ tăng traffic khi đủ mẫu và đạt tiêu chí promotion đã định.
8. Rollback ngay khi chạm điều kiện rủi ro đã xác định.
9. Sau promotion, cập nhật stable bằng cùng revision và kiểm tra lại toàn bộ replica.
10. Lưu lại kết quả thử nghiệm để lần điều chỉnh sau có baseline đáng tin cậy.

Phát hành thử ngưỡng mới trên một nhóm replica giúp kiểm chứng tác động của circuit breaker dưới traffic thực tế trong phạm vi có thể kiểm soát. Khi tách cấu hình và traffic, tính đến sliding window cục bộ của từng replica, so sánh bằng tỷ lệ và đặt trước điều kiện promotion/rollback, nhóm vận hành có thể điều chỉnh khả năng bảo vệ mà giảm rủi ro làm gián đoạn toàn bộ dịch vụ.

