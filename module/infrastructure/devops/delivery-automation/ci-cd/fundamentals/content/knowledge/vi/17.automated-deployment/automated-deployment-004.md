# Phân biệt chạy lệnh thành công với ứng dụng thực sự sẵn sàng

Một pipeline có thể chạy lệnh triển khai và nhận exit code bằng 0, nhưng người dùng vẫn không truy cập được ứng dụng. Lệnh có thể chỉ xác nhận rằng cấu hình đã được gửi đến nền tảng, container đã được tạo hoặc yêu cầu rollout đã được chấp nhận. Sau đó ứng dụng còn phải tải cấu hình, khởi tạo kết nối, chạy migration, nạp dữ liệu, đăng ký với service discovery và vượt qua các kiểm tra trước khi nhận traffic.

Vì vậy, **lệnh triển khai thành công không đồng nghĩa ứng dụng đã sẵn sàng phục vụ**. Pipeline cần xác minh ít nhất ba lớp: lệnh hoặc API triển khai hoàn tất, nền tảng đã đưa phiên bản mới vào trạng thái mong muốn, và ứng dụng thực sự đáp ứng được yêu cầu phục vụ. Với hệ thống quan trọng, cần quan sát thêm lỗi, độ trễ và hành vi nghiệp vụ sau khi traffic bắt đầu đi vào phiên bản mới.

## 1. Phân biệt các trạng thái sau triển khai

Các trạng thái thường bị gộp thành một khái niệm “deploy thành công”, nhưng chúng mô tả những điều khác nhau:

| Trạng thái | Điều gì đã xảy ra? | Điều chưa được chứng minh |
|---|---|---|
| Command completed | Tiến trình chạy lệnh kết thúc và trả exit code 0 | Nền tảng đã triển khai xong hay ứng dụng phục vụ được |
| Deployment accepted | API hoặc control plane chấp nhận yêu cầu thay đổi | Replica mới đã chạy hoặc đã nhận traffic |
| Rollout completed | Controller đã đạt điều kiện rollout theo cấu hình | Các luồng nghiệp vụ thực tế đều hoạt động |
| Process started | Tiến trình ứng dụng đã khởi động | Cổng mạng đã lắng nghe và dependency đã sẵn sàng |
| Readiness passed | Instance được đánh giá có thể nhận traffic | Mọi chức năng hoặc mọi request đều thành công |
| Smoke test passed | Một tập request đại diện đã chạy thành công | Tất cả tình huống tải, lỗi và nghiệp vụ đều đúng |
| Operationally healthy | Telemetry và các chỉ số vận hành nằm trong ngưỡng chấp nhận | Không còn rủi ro nào trong mọi điều kiện |

### Command completion

Một lệnh shell thường trả về mã thoát. Mã 0 thường biểu thị chương trình cho rằng thao tác của nó đã hoàn tất thành công; mã khác 0 biểu thị lỗi theo quy ước của chương trình. Exit code không tự mô tả trạng thái của ứng dụng ở phía sau.

Ví dụ:

- kubectl apply trả về thành công khi Kubernetes API chấp nhận các đối tượng được gửi.
- Một lệnh upload có thể trả về thành công khi file đã được tải lên registry.
- docker compose up -d có thể kết thúc sau khi yêu cầu khởi chạy container được thực hiện.
- systemctl restart có thể trả về thành công khi systemd chấp nhận hoặc hoàn tất yêu cầu restart, nhưng ứng dụng vẫn có thể chưa nhận request được.

Ý nghĩa chính xác phụ thuộc từng lệnh và tùy chọn được sử dụng. Cần đọc tài liệu công cụ và không suy luận rằng exit code 0 luôn có nghĩa toàn bộ dịch vụ đã sẵn sàng.

### Rollout completion

Rollout là quá trình đưa phiên bản mới vào hệ thống theo chiến lược triển khai. Trong Kubernetes, Deployment controller theo dõi ReplicaSet và Pod để đưa số replica về trạng thái mong muốn. Khi rollout được báo hoàn tất, điều đó cho biết các điều kiện rollout của controller đã đạt.

Kết quả rollout có giá trị hơn việc chỉ gửi cấu hình, nhưng vẫn không đảm bảo mọi endpoint, quyền truy cập, luồng dữ liệu hoặc nghiệp vụ đều hoạt động. Một Pod có thể Ready nhưng endpoint nghiệp vụ vẫn trả lỗi do cấu hình sai hoặc dependency ở một vùng khác.

### Application readiness

Readiness là khả năng một instance nhận và xử lý traffic tại thời điểm kiểm tra. Một instance có thể đang chạy nhưng chưa sẵn sàng vì:

- Đang nạp cấu hình hoặc dữ liệu ban đầu.
- Đang khởi tạo connection pool.
- Chưa hoàn tất migration hoặc đồng bộ cache.
- Chưa kết nối được dependency bắt buộc.
- Chưa đăng ký thành công với service discovery.
- Đang quá tải hoặc không đủ tài nguyên để phục vụ.

Readiness cần được kiểm tra ở đúng tầng có thể phản ánh khả năng phục vụ. Một TCP port mở chỉ cho biết có tiến trình lắng nghe; nó không chứng minh endpoint hoặc nghiệp vụ hoạt động đúng.

## 2. Vì sao lệnh triển khai có thể thành công nhưng ứng dụng vẫn lỗi?

### Triển khai là thao tác bất đồng bộ

Nhiều nền tảng tiếp nhận yêu cầu rồi thực hiện triển khai ở background. Lệnh gửi yêu cầu kết thúc nhanh, trong khi việc kéo image, tạo container, gắn volume, cấp IP và khởi động ứng dụng có thể mất vài phút.

Nếu pipeline kết thúc ngay sau lệnh gửi yêu cầu, nó có thể báo thành công trước khi phiên bản mới thực sự chạy. Cần có bước chờ trạng thái rollout hoặc một cơ chế theo dõi tiến trình triển khai.

### Tiến trình khởi động chậm

Ứng dụng Java có thể cần thời gian nạp class, khởi tạo framework, kết nối database, tạo pool và nạp cache. Container có thể ở trạng thái Running trong khi ứng dụng vẫn trả 503 hoặc chưa mở endpoint.

Nếu health check bắt đầu quá sớm với ngưỡng quá ngắn, hệ thống có thể đánh dấu ứng dụng không khỏe hoặc restart liên tục. Nếu ngưỡng quá rộng, lỗi khởi động có thể bị phát hiện muộn.

### Cấu hình hoặc secret không hợp lệ

Image có thể được kéo và container tạo thành công nhưng ứng dụng không thể khởi tạo do thiếu biến môi trường, sai secret, sai endpoint hoặc thiếu quyền truy cập. Lệnh triển khai không nhất thiết kiểm tra mọi cấu hình runtime.

### Dependency chưa sẵn sàng

Ứng dụng có thể khởi động nhưng không kết nối được database, message broker, cache hoặc dịch vụ định danh. Tùy thiết kế, ứng dụng có thể:

- Không khởi động nếu dependency là bắt buộc.
- Khởi động ở trạng thái chưa sẵn sàng và chờ dependency.
- Phục vụ một phần chức năng trong chế độ degraded.
- Khởi động thành công nhưng request cụ thể thất bại khi gọi dependency.

Pipeline cần biết dependency nào thực sự bắt buộc cho readiness và chức năng nào có thể hoạt động độc lập.

### Phiên bản mới chạy nhưng không nhận traffic

Load balancer, ingress, service discovery hoặc routing rule có thể chưa cập nhật đúng. Pod hoặc process có thể Ready nhưng không được route tới; ngược lại, traffic có thể đến instance chưa sẵn sàng nếu health check được cấu hình sai.

### Ứng dụng sẵn sàng nhưng nghiệp vụ vẫn sai

Health endpoint trả 200 chỉ chứng minh điều kiện mà endpoint đó kiểm tra đã đạt. Nó không tự chứng minh đăng nhập, thanh toán, tạo đơn, gửi message hoặc truy vấn dữ liệu đều đúng. Cần thêm smoke test đại diện cho luồng quan trọng.

## 3. Thiết kế health endpoint có ý nghĩa

Ứng dụng nên cung cấp các endpoint hoặc cơ chế health riêng cho mục đích khác nhau. Một cách đặt tên thường dùng:

- /health/live: tiến trình còn hoạt động và không ở trạng thái cần restart.
- /health/ready: instance có thể nhận request thông thường.
- /health/startup: quá trình khởi tạo đã hoàn tất.

Không bắt buộc phải dùng đúng ba URL này. Điều quan trọng là hợp đồng của từng endpoint phải rõ ràng và được nền tảng triển khai hiểu đúng.

### Liveness: có cần khởi động lại tiến trình không?

Liveness trả lời liệu tiến trình còn có khả năng tiếp tục hoạt động hay đã rơi vào trạng thái không thể phục hồi nếu không restart. Ví dụ, ứng dụng bị deadlock, event loop không phản hồi hoặc thành phần cốt lõi bị kẹt vĩnh viễn.

Liveness không nên phụ thuộc trực tiếp vào mọi dịch vụ bên ngoài. Nếu database tạm thời mất kết nối, liveness của tất cả instance cùng thất bại có thể khiến hệ thống restart hàng loạt. Restart không khắc phục được sự cố database và có thể tạo thêm tải trong lúc hệ thống đang phục hồi.

### Readiness: có nên gửi traffic đến instance này?

Readiness trả lời liệu instance có thể xử lý request tại thời điểm hiện tại. Nó có thể kiểm tra:

- Ứng dụng đã hoàn tất startup.
- Cấu hình bắt buộc đã được nạp.
- Connection pool hoặc client quan trọng đã sẵn sàng.
- Các dependency bắt buộc cho luồng phục vụ chính có thể truy cập.
- Instance không ở trạng thái shutdown hoặc draining.

Nếu một dependency chỉ ảnh hưởng một tính năng phụ, không nhất thiết phải làm toàn bộ instance NotReady. Có thể để ứng dụng phục vụ phần chức năng còn lại và trả lỗi có kiểm soát cho tính năng bị ảnh hưởng. Quyết định này cần dựa trên hợp đồng dịch vụ và yêu cầu người dùng.

### Startup: ứng dụng đã khởi tạo xong chưa?

Startup probe dành cho ứng dụng có thời gian khởi động dài hoặc không ổn định. Nó cho hệ thống biết cần chờ bao lâu trước khi áp dụng các kiểm tra liveness và readiness thông thường. Khi startup probe chưa thành công, Kubernetes không chạy liveness và readiness probe của container đó.

Startup probe giúp tránh việc liveness kiểm tra một ứng dụng hợp lệ nhưng chưa hoàn tất khởi tạo. Tuy nhiên, nếu startup probe không bao giờ thành công, container vẫn có thể bị restart khi vượt quá giới hạn failure threshold.

### Bảng so sánh ba loại probe

| Loại probe | Câu hỏi | Khi thất bại | Mục tiêu |
|---|---|---|---|
| Startup | Ứng dụng đã khởi động xong chưa? | Container có thể bị restart khi vượt ngưỡng | Cho phép startup kéo dài |
| Readiness | Instance có thể nhận traffic không? | Pod bị loại khỏi endpoint phục vụ | Điều khiển traffic |
| Liveness | Tiến trình còn hoạt động có thể phục hồi không? | Container bị restart | Phục hồi tiến trình bị kẹt |

Không dùng một endpoint duy nhất cho cả ba mục đích nếu chúng có ngữ nghĩa khác nhau. Một dependency tạm thời lỗi có thể khiến readiness thất bại nhưng không nên làm liveness thất bại.

## 4. Quy tắc xây dựng health check đáng tin cậy

Một health check tốt cần nhanh, ổn định, có giới hạn thời gian và phản ánh đúng trạng thái cần đo.

### Phản hồi nhanh và có timeout

Probe thường được gọi lặp lại. Không để endpoint thực hiện truy vấn nặng, quét toàn bộ dữ liệu hoặc chờ dependency vô thời hạn. Đặt timeout cho thao tác kiểm tra và chọn interval phù hợp.

Nếu mỗi lần health check tạo một truy vấn database nặng, số lượng instance lớn có thể tạo thêm tải lên database. Dùng connection đã quản lý hoặc phép kiểm tra nhẹ, có giới hạn và có cache trạng thái nếu phù hợp.

### Không trả thông tin nhạy cảm

Endpoint health không nên trả stack trace, connection string, token, tên người dùng, nội dung secret hoặc chi tiết hạ tầng không cần thiết. Thường chỉ cần trạng thái tổng quát và mã thành phần.

Nếu endpoint chi tiết phục vụ vận hành cần xác thực, hãy tách nó khỏi endpoint mà load balancer hoặc kubelet cần truy cập. Không mở một trang diagnostics đầy đủ ra Internet chỉ để health check hoạt động.

### Phân biệt lỗi ứng dụng và lỗi kiểm tra

Health check có thể thất bại vì:

- Ứng dụng thật sự không sẵn sàng.
- Probe gọi sai path hoặc port.
- Network policy chặn đường kiểm tra.
- Timeout quá ngắn.
- TLS hoặc authentication cấu hình sai.
- Probe chạy từ môi trường khác với request thật.

Khi điều tra, kiểm tra cả log ứng dụng và log của probe. Không tự động tăng timeout hoặc bỏ kiểm tra khi chưa xác định nguyên nhân.

### Kiểm tra từ đúng góc nhìn

Một health endpoint nội bộ có thể trả 200 trong khi ingress hoặc DNS bên ngoài không hoạt động. Do đó, có thể cần nhiều lớp:

1. Process/container health bên trong instance.
2. Readiness của instance trong orchestrator.
3. Health của load balancer hoặc ingress.
4. Synthetic check từ bên ngoài theo đường truy cập người dùng.
5. Smoke test một số API hoặc luồng nghiệp vụ.

Không phải hệ thống nào cũng cần mọi lớp. Chọn điểm kiểm tra dựa trên các ranh giới có thể hỏng độc lập.

## 5. Ví dụ cấu hình health endpoint trong ứng dụng Java

Với Spring Boot Actuator, ứng dụng có thể cung cấp health endpoint và các trạng thái readiness/liveness. Ví dụ cấu hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health
~~~

Tùy phiên bản Spring Boot và cách triển khai, các nhóm health có thể được cung cấp tại các đường dẫn như /actuator/health/liveness và /actuator/health/readiness. Cần kiểm tra phiên bản framework, cấu hình management port và đường dẫn thực tế trước khi cấu hình probe.

Một health endpoint có thể trả trạng thái tổng quát:

~~~json
{
  "status": "UP"
}
~~~

Kết quả này chỉ có ý nghĩa theo những health indicator đã được bật và cách framework tổng hợp chúng. Nếu readiness không bao gồm dependency cần thiết, trạng thái UP không chứng minh dependency đó đang hoạt động. Nếu mọi dependency đều được gộp vào liveness, sự cố tạm thời bên ngoài có thể gây restart không cần thiết.

### Tách readiness và liveness theo hợp đồng

Một ứng dụng có thể coi:

- Liveness UP khi process và các thành phần nội bộ cốt lõi vẫn tiến triển.
- Readiness UP khi startup hoàn tất, cấu hình bắt buộc hợp lệ và các dependency tối thiểu để phục vụ request chính đã sẵn sàng.
- Startup UP khi quá trình khởi tạo đã hoàn tất.

Đây là cách phân loại khái niệm. Cách triển khai cụ thể có thể dùng Spring Boot availability state, health group, custom indicator hoặc endpoint riêng. Tránh thêm một truy vấn database nặng vào mỗi liveness request.

## 6. Kubernetes: triển khai, rollout và readiness

Kubernetes cung cấp các probe cho container và controller quản lý rollout. Ví dụ Deployment:

~~~yaml
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
    spec:
      containers:
        - name: app
          image: registry.example.com/order-service:2.4.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Đây là ví dụ minh họa; các path phải khớp endpoint thực tế của ứng dụng. Startup probe ở ví dụ dùng liveness group để xác định ứng dụng đã khởi tạo đủ để bắt đầu kiểm tra; có thể tạo một startup health group riêng nếu ứng dụng có quy trình khởi tạo riêng. Không dùng một health endpoint tổng hợp mọi dependency làm startup probe nếu dependency đó có thể tạm thời chưa sẵn sàng. Startup probe ở ví dụ cho phép thời gian khởi động tối đa xấp xỉ 180 giây theo số lần kiểm tra và chu kỳ đã cấu hình, chưa tính mọi yếu tố lập lịch và thời gian phản hồi. Hãy chọn ngưỡng dựa trên thời gian khởi động đo được ở điều kiện tải thực tế.

Khi readiness probe thất bại, Pod không được coi là Ready và sẽ bị loại khỏi các endpoint phục vụ tương ứng. Khi liveness probe thất bại đủ số lần, kubelet sẽ restart container theo chính sách restart. Khi startup probe chưa thành công, các probe liveness/readiness khác chưa được thực hiện.

### Lệnh apply và rollout status

Lệnh gửi manifest:

~~~bash
kubectl apply -f deployment.yaml
~~~

Lệnh này thường trả về sau khi Kubernetes API chấp nhận cập nhật. Để chờ Deployment rollout:

~~~bash
kubectl rollout status deployment/order-service --timeout=180s
~~~

Nếu rollout status trả thành công, controller đã báo rollout hoàn tất theo trạng thái Deployment. Tuy vậy, pipeline vẫn nên thực hiện smoke test qua đường truy cập mà người dùng sẽ dùng và quan sát lỗi sau khi traffic được chuyển.

Có thể kiểm tra trạng thái Pod và endpoint:

~~~bash
kubectl get pods -l app=order-service
kubectl get endpointslices -l kubernetes.io/service-name=order-service
kubectl describe deployment order-service
~~~

Các lệnh này giúp điều tra trạng thái workload và endpoint được publish. Tên resource, selector và API có thể khác tùy cấu hình cluster.

### Readiness không thay thế rollout policy

Một Deployment có thể không hoàn tất rollout vì Pod mới không Ready, image pull lỗi, quota thiếu hoặc scheduling thất bại. Readiness probe giúp điều khiển việc đưa Pod vào phục vụ; rollout controller dùng trạng thái replica để quyết định tiến trình cập nhật.

Nếu maxUnavailable, maxSurge hoặc chiến lược cập nhật được cấu hình không phù hợp, rollout có thể làm giảm capacity hoặc bị kẹt. Cần thiết kế số replica, tài nguyên và chiến lược cập nhật phù hợp với tải.

## 7. Chờ readiness và chạy smoke test trong CI

Pipeline nên có bước chờ sau khi gửi yêu cầu triển khai. Chỉ chờ một khoảng sleep cố định không đáng tin cậy: máy nhanh sẽ phải chờ thừa, máy chậm có thể vẫn chưa sẵn sàng khi thời gian chờ kết thúc.

Một cách tốt hơn là polling health endpoint với deadline và timeout:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

HEALTH_URL="https://staging.example.com/actuator/health/readiness"
DEADLINE=$((SECONDS + 180))

until curl --fail --silent --show-error --max-time 5 "$HEALTH_URL"; do
  if (( SECONDS >= DEADLINE )); then
    echo "Application did not become ready before the deadline."
    exit 1
  fi
  sleep 5
done

echo "Readiness check passed."
~~~

Ví dụ giả định endpoint staging có thể truy cập từ runner. Trong môi trường thật, dùng URL, chứng thư TLS và cơ chế xác thực phù hợp. Nếu health endpoint trả JSON, có thể kiểm tra cả trường status thay vì chỉ dựa trên HTTP 2xx.

### Smoke test sau readiness

Sau khi endpoint readiness đạt, chạy một tập request nhỏ đại diện cho các luồng quan trọng:

~~~bash
curl --fail --silent --show-error \
  --max-time 10 \
  https://staging.example.com/api/version

curl --fail --silent --show-error \
  --max-time 10 \
  https://staging.example.com/api/orders/health-check
~~~

Đường dẫn trong ví dụ chỉ mang tính minh họa. Smoke test thực tế cần kiểm tra response body, status, header hoặc dữ liệu trả về theo hợp đồng API. Nếu request có side effect, dùng dữ liệu test, idempotency key hoặc môi trường được cô lập để tránh tạo giao dịch thật.

Một smoke test tốt nên:

- Chạy nhanh và ổn định.
- Bao phủ một vài luồng quan trọng có thể đại diện.
- Không tạo tác động không thể đảo ngược.
- Có timeout và thông báo lỗi rõ.
- Chạy qua cùng ingress, DNS và authentication path mà client sử dụng khi phù hợp.
- Xác định đúng phiên bản vừa triển khai.

Smoke test không phải bộ regression test đầy đủ. Nó là phép xác minh nhanh sau deploy để phát hiện lỗi lớn trước khi rollout rộng hơn.

## 8. Xác minh đúng phiên bản vừa triển khai

Một endpoint trả 200 có thể đang trả lời từ phiên bản cũ, cache hoặc instance khác. Vì vậy, cần xác nhận phiên bản thực tế đang phục vụ:

- API version endpoint hoặc response header có commit/build ID.
- Image digest hoặc artifact digest được triển khai.
- Deployment revision và Pod template image.
- Deployment record từ hệ thống phát hành.

Ví dụ API có thể trả:

~~~json
{
  "service": "order-service",
  "version": "2.4.0",
  "commit": "a1b2c3d4e5f6",
  "buildId": "18452"
}
~~~

Không nên công khai mọi thông tin nội bộ ra endpoint Internet. Có thể dùng endpoint nội bộ hoặc header chỉ dành cho kiểm tra vận hành. Dữ liệu phiên bản phải được tạo từ build metadata đáng tin cậy, không lấy từ một biến runtime tùy ý mà không có kiểm soát.

Với container, triển khai bằng image digest giúp xác định chính xác nội dung. Tag có thể bị ghi đè hoặc trỏ sang image mới; digest bất biến theo nội dung là cách xác nhận tốt hơn.

## 9. Xác minh dependency và luồng nghiệp vụ

Health endpoint thường kiểm tra một số thành phần kỹ thuật. Nó có thể không kiểm tra đầy đủ các luồng nghiệp vụ. Sau deploy, hãy chọn smoke test phản ánh rủi ro quan trọng:

| Loại ứng dụng | Smoke test gợi ý |
|---|---|
| REST API | Gọi endpoint đọc dữ liệu và xác minh schema/response |
| Dịch vụ xử lý đơn hàng | Tạo đơn test, đọc trạng thái và xác minh chuyển trạng thái |
| Worker/message consumer | Gửi message thử và xác nhận xử lý hoặc ack |
| Dịch vụ thanh toán | Dùng sandbox để xác minh luồng giả lập, không phát sinh giao dịch thật |
| Web frontend | Tải trang, kiểm tra asset và thực hiện thao tác chính |
| Dịch vụ có database | Thực hiện truy vấn hoặc thao tác an toàn với dữ liệu test |

Không cần kiểm tra mọi dependency bằng một request health duy nhất. Nếu một dịch vụ phụ trợ có thể lỗi độc lập, cần quyết định ứng dụng sẽ degraded, từ chối một chức năng hay ngừng nhận toàn bộ traffic.

### Readiness và dependency

Một câu hỏi quan trọng là dependency nào cần có để instance được coi là Ready. Nếu ứng dụng có thể phục vụ request đọc dù message broker tạm thời không hoạt động, readiness không nhất thiết phải chuyển sang NotReady cho toàn bộ dịch vụ. Nếu database là nền tảng của mọi request, database không sẵn sàng có thể là điều kiện readiness bắt buộc.

Hãy thiết kế theo khả năng phục vụ thực tế và hợp đồng dịch vụ, tránh đưa mọi dependency vào một danh sách cứng nhắc. Một dependency không bắt buộc nhưng bị đưa vào readiness có thể làm giảm capacity toàn hệ thống khi nó gặp sự cố.

## 10. Theo dõi sau deploy bằng telemetry

Readiness và smoke test là tín hiệu tức thời. Sau khi phiên bản mới nhận traffic, cần quan sát telemetry để phát hiện lỗi chỉ xuất hiện dưới tải hoặc trong tương tác thật.

Các chỉ số thường theo dõi:

- Tỷ lệ request thành công và lỗi theo mã HTTP.
- Latency p50, p95 và p99.
- Tỷ lệ timeout và retry.
- Số lượng request, throughput và queue depth.
- CPU, memory, garbage collection và restart count.
- Kết nối database, pool saturation và lỗi truy vấn.
- Message lag, dead-letter queue và lỗi consumer.
- Business metric như tỷ lệ hoàn tất giao dịch hoặc đơn hàng.

Nên so sánh với baseline trước triển khai và đặt cửa sổ quan sát đủ để có traffic đại diện. Một service ít traffic có thể không tạo đủ dữ liệu trong vài giây đầu; khi đó cần synthetic test hoặc kéo dài thời gian xác minh theo chính sách.

### Không chỉ nhìn trạng thái Pod

Pod Ready không có nghĩa người dùng không gặp lỗi. Có thể tất cả Pod Ready nhưng:

- Ingress trỏ sai service.
- DNS hoặc TLS certificate lỗi.
- Một route API trả 500.
- Database migration làm truy vấn chậm.
- Phiên bản mới có memory leak chỉ xuất hiện khi tải tăng.
- Message consumer nhận message nhưng xử lý sai dữ liệu.

Do đó, cần kết hợp trạng thái nền tảng, health check, smoke test và telemetry từ request thật.

## 11. Progressive delivery: tăng traffic theo từng bước

Với dịch vụ quan trọng, không nhất thiết chuyển toàn bộ traffic sang phiên bản mới ngay lập tức. Có thể dùng:

- **Rolling update:** thay thế instance từng phần, giữ một phần capacity cũ trong lúc rollout.
- **Canary:** gửi một tỷ lệ nhỏ traffic đến phiên bản mới rồi tăng dần nếu chỉ số đạt.
- **Blue-green:** duy trì hai môi trường và chuyển traffic sau khi môi trường mới được xác minh.
- **Feature flag:** triển khai mã nhưng bật hành vi mới theo nhóm người dùng hoặc điều kiện.

Một luồng canary khái quát:

~~~text
Deploy version N+1
       |
       v
Wait for startup and readiness
       |
       v
Send small traffic share
       |
       v
Run smoke tests + observe SLI
       |
       +---- Within thresholds? ---- No ----> Stop rollout / rollback
       |
      Yes
       |
       v
Increase traffic gradually
       |
       v
Verify full rollout and observe
~~~

Ngưỡng quyết định cần dựa trên baseline, SLO và mức rủi ro. Không tăng traffic chỉ vì một endpoint trả 200 nếu tỷ lệ lỗi hoặc latency đang xấu đi.

## 12. Timeout, retry và xử lý khi không sẵn sàng

Pipeline phải có deadline cho từng bước:

| Bước | Giới hạn cần xác định | Khi hết thời gian |
|---|---|---|
| Gửi yêu cầu deploy | Timeout API hoặc CLI | Xác định request đã được chấp nhận chưa trước khi gửi lại |
| Rollout | Thời gian tối đa theo chiến lược | Thu thập trạng thái, event và log |
| Readiness | Deadline chờ instance sẵn sàng | Không chuyển traffic hoặc không tiếp tục release |
| Smoke test | Timeout từng request và tổng suite | Ghi request lỗi và dừng gate |
| Observation window | Thời gian theo dõi telemetry | Tiếp tục, dừng rollout hoặc rollback theo chính sách |

### Retry có giới hạn

Retry hữu ích với lỗi mạng tạm thời hoặc endpoint đang khởi động. Tuy nhiên, retry không được biến một lỗi kéo dài thành thành công giả. Dùng số lần thử hoặc deadline hữu hạn, khoảng nghỉ hợp lý và log mỗi lần thất bại.

Nếu lệnh deploy có thể tạo tài nguyên hoặc kích hoạt thao tác không idempotent, không gửi lại mù quáng sau timeout. Trước tiên xác minh trạng thái yêu cầu trước đã được xử lý hay chưa. Điều này tránh tạo hai lần triển khai hoặc hai tác vụ migration.

### Không xóa dấu vết khi deploy thất bại

Khi readiness không đạt, lưu lại:

- Deployment run ID và commit/artifact digest.
- Lệnh và tham số triển khai.
- Trạng thái rollout, Pod event và log ứng dụng.
- Kết quả health check và smoke test.
- Thời điểm từng bước.
- Quyết định retry, dừng hoặc rollback.

Thông tin này giúp phân biệt lỗi do artifact, cấu hình, hạ tầng hay dependency.

## 13. Rollback sau khi readiness hoặc smoke test thất bại

Nếu phiên bản mới không sẵn sàng hoặc vượt ngưỡng lỗi, hệ thống có thể dừng rollout và quay lại phiên bản trước. Nhưng rollback chỉ an toàn khi dữ liệu và hợp đồng giữa các phiên bản tương thích.

### Quy trình rollback khái quát

1. Dừng tăng traffic hoặc dừng rollout.
2. Xác định phiên bản và artifact digest đang hoạt động trước thay đổi.
3. Triển khai lại artifact đã biết là tốt hoặc chuyển traffic về blue environment.
4. Chờ rollout/endpoint readiness của phiên bản cũ.
5. Chạy smoke test và quan sát telemetry.
6. Ghi lại nguyên nhân, thời điểm và kết quả rollback.

Trong Kubernetes, có thể dùng rollout history và undo nếu chính sách release cho phép:

~~~bash
kubectl rollout history deployment/order-service
kubectl rollout undo deployment/order-service
kubectl rollout status deployment/order-service --timeout=180s
~~~

Undo thay đổi workload revision theo lịch sử Deployment. Nó không tự rollback database migration, message schema, secret rotation hoặc thay đổi ở dịch vụ ngoài cluster.

### Database migration cần tương thích ngược

Một phiên bản mới có thể thêm cột hoặc đổi schema. Nếu migration xóa cột cũ ngay lập tức, phiên bản trước có thể không chạy được khi rollback. Dùng chiến lược expand-and-contract:

1. Thêm cấu trúc mới mà mã cũ vẫn hoạt động.
2. Triển khai ứng dụng có thể đọc/ghi tương thích.
3. Chuyển dữ liệu hoặc traffic theo giai đoạn.
4. Xác minh không còn thành phần dùng cấu trúc cũ.
5. Chỉ xóa cấu trúc cũ trong một thay đổi riêng sau khi rollback window kết thúc.

Rollback ứng dụng không phải lúc nào cũng đồng nghĩa rollback dữ liệu. Với thay đổi dữ liệu không thể đảo ngược, có thể cần forward fix hoặc phục hồi từ backup theo kế hoạch đã thử nghiệm.

## 14. Các lỗi thiết kế thường gặp

### Chỉ kiểm tra exit code của deploy command

Pipeline dừng sau lệnh triển khai và báo xanh dù ứng dụng chưa khởi động. Thêm bước chờ rollout và kiểm tra readiness.

### Dùng sleep cố định thay cho polling

Sleep không phản ánh trạng thái thực. Dùng polling có deadline, timeout và thông báo lỗi.

### Dùng TCP port mở làm readiness

Port mở không chứng minh ứng dụng có thể xử lý request. Dùng HTTP health endpoint hoặc cơ chế kiểm tra phù hợp với giao thức.

### Dùng liveness để kiểm tra mọi dependency

Dependency tạm thời lỗi có thể khiến toàn bộ instance restart, làm sự cố nặng hơn. Chỉ dùng liveness cho trạng thái tiến trình không thể phục hồi; dùng readiness để điều khiển traffic.

### Health endpoint luôn trả 200

Endpoint không kiểm tra trạng thái cần thiết sẽ tạo tín hiệu xanh giả. Định nghĩa hợp đồng readiness và cập nhật cùng thay đổi kiến trúc.

### Chỉ chạy smoke test trên localhost

Localhost có thể hoạt động trong khi ingress, DNS, TLS, authentication hoặc routing bên ngoài bị lỗi. Kiểm tra qua đường truy cập đại diện cho người dùng khi phù hợp.

### Không xác minh đúng phiên bản

Health endpoint có thể trả lời từ instance cũ hoặc cache. Đối chiếu commit/build ID hoặc artifact digest đang phục vụ.

### Rollback mà không xem xét dữ liệu

Phiên bản cũ có thể không tương thích schema mới. Thiết kế migration có khả năng tương thích và thử rollback trước khi phát hành.

## 15. Checklist xác minh ứng dụng sau triển khai

- [ ] Lệnh triển khai kết thúc với exit code được mong đợi.
- [ ] Nền tảng đã chấp nhận và ghi nhận đúng phiên bản mong muốn.
- [ ] Rollout đạt trạng thái hoàn tất trong deadline.
- [ ] Instance mới vượt qua startup và readiness check.
- [ ] Liveness probe phản ánh khả năng phục hồi của process, không phụ thuộc mọi dịch vụ bên ngoài.
- [ ] Readiness chỉ bao gồm điều kiện thực sự cần để nhận traffic.
- [ ] Load balancer, ingress hoặc service discovery đưa traffic đến instance mới.
- [ ] Smoke test qua đường truy cập phù hợp đã đạt.
- [ ] Commit/build ID hoặc artifact digest khớp phiên bản dự kiến.
- [ ] Telemetry không vượt ngưỡng lỗi, latency hoặc tài nguyên.
- [ ] Có kế hoạch dừng rollout và rollback đã được xác định.
- [ ] Database migration và thay đổi dữ liệu tương thích với phương án phục hồi.
- [ ] Deployment record lưu trạng thái, log, thời gian và quyết định cuối.

Triển khai tự động chỉ hoàn tất khi pipeline có bằng chứng rằng phiên bản mới đã được đưa vào trạng thái phục vụ theo chính sách. Exit code 0 cho biết lệnh đã báo thành công; rollout status cho biết nền tảng đã đạt điều kiện cập nhật; readiness và smoke test kiểm tra ứng dụng từ góc nhìn phục vụ; telemetry cho biết phiên bản có tiếp tục hoạt động ổn định khi nhận traffic hay không. Kết hợp các lớp xác minh này giúp pipeline tránh báo thành công quá sớm và có cơ sở để dừng hoặc quay lui khi ứng dụng chưa thực sự sẵn sàng.
