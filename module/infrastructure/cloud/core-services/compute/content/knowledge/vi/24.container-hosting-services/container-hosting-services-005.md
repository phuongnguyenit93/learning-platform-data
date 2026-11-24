# Health probe và vòng đời triển khai của container service

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Phân biệt health probe khởi động, sẵn sàng và hoạt động của container.
- Thiết kế endpoint kiểm tra sức khỏe phù hợp với vai trò của từng probe.
- Cấu hình probe cho một dịch vụ container chạy trên Kubernetes.
- Giải thích cách health probe tham gia vào quá trình đưa phiên bản mới vào phục vụ, rút phiên bản cũ khỏi lưu lượng và khôi phục khi triển khai lỗi.
- Kiểm tra trạng thái triển khai và nhận diện các lỗi cấu hình probe thường gặp.

## 1. Vì sao container service cần health probe?

Một container ở trạng thái `Running` chỉ cho biết tiến trình chính đã được khởi chạy. Điều đó chưa chứng minh ứng dụng đã tải cấu hình, mở kết nối đến dịch vụ phụ thuộc, hoàn tất khởi tạo hoặc có thể nhận yêu cầu. Ngược lại, một tiến trình có thể vẫn chạy nhưng đã bị treo, hết tài nguyên hoặc không còn xử lý được yêu cầu.

Health probe là phép kiểm tra định kỳ để nền tảng điều phối biết container đang ở giai đoạn nào và có thể phục vụ hay không. Kết quả probe có thể khiến nền tảng chờ khởi động, đưa instance ra khỏi danh sách nhận lưu lượng, khởi động lại container hoặc đánh dấu một lần triển khai chưa đạt điều kiện.

Trong dịch vụ chạy nhiều bản sao, probe giúp bộ cân bằng tải gửi yêu cầu đến các instance sẵn sàng. Trong quá trình cập nhật phiên bản, probe giúp hệ thống chỉ chuyển lưu lượng sang instance mới sau khi ứng dụng thực sự sẵn sàng, đồng thời phát hiện phiên bản mới bị lỗi để dừng hoặc rollback.

## 2. Ba loại probe và trách nhiệm của chúng

Ba loại probe phổ biến trong Kubernetes có mục đích khác nhau. Không nên dùng một phép kiểm tra duy nhất cho cả ba mục đích.

| Loại probe | Câu hỏi cần trả lời | Khi thất bại | Ví dụ tình huống |
|---|---|---|---|
| Startup probe | Ứng dụng đã khởi tạo xong chưa? | Container bị xem là khởi động thất bại và có thể được khởi động lại theo `restartPolicy`. | Ứng dụng cần 50 giây để nạp mô hình hoặc chạy migration khởi tạo. |
| Readiness probe | Instance có thể nhận yêu cầu ngay lúc này không? | Instance bị đánh dấu chưa sẵn sàng và không được chọn làm endpoint phục vụ thông thường. Container không bị khởi động lại chỉ vì readiness thất bại. | Ứng dụng đang nạp cache hoặc mất kết nối đến cơ sở dữ liệu bắt buộc. |
| Liveness probe | Tiến trình còn hoạt động đúng mức tối thiểu để tiếp tục chạy không? | Kubelet kết thúc container; chính sách khởi động lại của Pod quyết định việc khởi chạy lại. | Event loop bị treo, deadlock hoặc tiến trình không còn phản hồi. |

**Startup probe** dành cho ứng dụng có thời gian khởi động dài hoặc không ổn định. Khi đã cấu hình startup probe, Kubernetes chưa chạy readiness và liveness probe cho container đó cho đến khi startup probe thành công. Điều này ngăn liveness probe kết luận ứng dụng bị treo trong lúc ứng dụng vẫn đang khởi tạo hợp lệ.

**Readiness probe** quyết định instance có nên nhận lưu lượng hay không. Readiness có thể chuyển từ thành công sang thất bại nhiều lần trong suốt vòng đời container, chẳng hạn khi ứng dụng đang quá tải hoặc một phụ thuộc thiết yếu tạm thời không khả dụng. Probe thất bại không đồng nghĩa container cần restart.

**Liveness probe** phát hiện tình trạng tiến trình không thể tự phục hồi. Phép kiểm tra nên tập trung vào khả năng sống của ứng dụng, chẳng hạn máy chủ HTTP nội bộ còn phản hồi hay event loop còn tiến triển. Nếu liveness phụ thuộc trực tiếp vào mọi dịch vụ bên ngoài, một sự cố cơ sở dữ liệu có thể làm tất cả container restart cùng lúc dù bản thân tiến trình vẫn khỏe.

## 3. Thiết kế endpoint health check

Một ứng dụng HTTP có thể cung cấp ba endpoint riêng:

- `/health/startup`: trả thành công khi các bước khởi tạo bắt buộc đã hoàn tất.
- `/health/ready`: trả thành công khi instance có thể nhận và xử lý yêu cầu thực tế.
- `/health/live`: trả thành công khi tiến trình còn phản hồi và không rơi vào trạng thái không thể phục hồi.

Với HTTP probe, mã phản hồi trong khoảng 200–399 được Kubernetes xem là thành công. Có thể quy ước endpoint trả `200 OK` khi đạt yêu cầu và `503 Service Unavailable` khi chưa đạt. Endpoint nên phản hồi nhanh, có timeout rõ ràng và không thực hiện truy vấn nặng.

Khi thiết kế, hãy phân định trách nhiệm như sau:

1. Startup kiểm tra các bước cần thiết để bắt đầu phục vụ: nạp cấu hình, mở listener, khởi tạo thành phần nội bộ và hoàn tất công việc khởi động bắt buộc.
2. Readiness kiểm tra khả năng nhận loại yêu cầu mà service cam kết xử lý. Chỉ đưa một phụ thuộc vào phép kiểm tra nếu thiếu phụ thuộc đó thực sự khiến instance không thể phục vụ an toàn.
3. Liveness kiểm tra sức khỏe nội bộ của tiến trình. Không gọi API của nhà cung cấp bên ngoài hoặc chạy truy vấn cơ sở dữ liệu nặng ở mỗi lần kiểm tra liveness.

Ví dụ, một dịch vụ đơn hàng cần cơ sở dữ liệu để ghi đơn mới. Readiness có thể kiểm tra pool kết nối còn khả năng cấp kết nối và trạng thái ứng dụng cho phép ghi đơn. Nếu cơ sở dữ liệu mất kết nối, instance có thể tạm thời ngừng nhận yêu cầu ghi. Liveness vẫn có thể thành công nếu tiến trình HTTP hoạt động bình thường. Khi cơ sở dữ liệu phục hồi, readiness thành công trở lại và instance được đưa vào phục vụ mà không cần restart.

Không phải mọi lỗi phụ thuộc đều cần làm readiness thất bại. Nếu ứng dụng vẫn có thể phục vụ một phần chức năng bằng cache hoặc chế độ suy giảm đã được thiết kế, hãy biểu diễn trạng thái đó theo đúng cam kết dịch vụ. Nếu readiness kiểm tra quá nhiều phụ thuộc không thiết yếu, một lỗi ở hệ thống phụ có thể khiến toàn bộ bản sao rời khỏi load balancer và tạo ra gián đoạn lớn hơn.

## 4. Cấu hình probe cho dịch vụ container trên Kubernetes

Ví dụ dưới đây triển khai ba bản sao của API đơn hàng. Ứng dụng lắng nghe cổng `8080`; startup probe cho phép tối đa khoảng hai phút để khởi tạo; readiness kiểm tra khả năng nhận lưu lượng; liveness phát hiện tiến trình ngừng phản hồi.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  minReadySeconds: 10
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: api
          image: registry.example.com/orders-api:1.8.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
```

Các thông số trong ví dụ là điểm khởi đầu, cần điều chỉnh theo thời gian khởi động và độ trễ thực tế:

- `periodSeconds` là khoảng thời gian giữa các lần probe.
- `timeoutSeconds` là thời gian tối đa chờ một lần probe phản hồi.
- `failureThreshold` là số lần thất bại liên tiếp trước khi probe bị xem là thất bại.
- `successThreshold` là số lần thành công liên tiếp cần có để readiness chuyển lại sang sẵn sàng. Với liveness và startup, giá trị này phải là `1`.
- `minReadySeconds` yêu cầu Pod duy trì trạng thái Ready trong một khoảng thời gian trước khi Deployment xem là đã sẵn sàng ổn định cho rollout.
- `maxSurge: 1` cho phép tạo thêm tối đa một Pod trong lúc cập nhật; `maxUnavailable: 0` yêu cầu giữ đủ số bản sao khả dụng theo mong muốn trong rollout. Cụm phải có đủ tài nguyên để tạo Pod bổ sung.

Startup probe trong ví dụ có chu kỳ 5 giây và ngưỡng 24 lần thất bại, tạo khoảng thời gian kiểm tra xấp xỉ 120 giây. Hãy đặt ngưỡng dựa trên thời gian khởi động ở điều kiện tải và tài nguyên thực tế, có thêm khoảng đệm hợp lý. Nếu ứng dụng thường xuyên khởi động lâu hơn ngưỡng, cần tìm nguyên nhân hoặc điều chỉnh ngưỡng thay vì tăng vô hạn.

Kubernetes cũng hỗ trợ probe TCP, exec và gRPC. TCP chỉ xác nhận cổng có thể mở kết nối, không chứng minh ứng dụng xử lý yêu cầu đúng. Exec chạy lệnh trong container nên phụ thuộc vào công cụ có sẵn trong image và tạo thêm chi phí tiến trình. HTTP phù hợp khi ứng dụng có endpoint health chuyên dụng; gRPC phù hợp với service đã triển khai health checking theo giao thức gRPC.

## 5. Health probe trong dịch vụ container được quản lý

Các nền tảng cloud có thể có nhiều lớp kiểm tra sức khỏe. Cần xác định lớp nào kiểm tra container, lớp nào kiểm tra task hoặc instance và lớp nào quyết định định tuyến lưu lượng.

**Ví dụ với Amazon ECS và Application Load Balancer (ALB):** task definition có thể khai báo container health check bằng lệnh chạy trong container. ALB đồng thời kiểm tra target thông qua health check của target group. Container health check phản ánh sức khỏe của tiến trình trong container; ALB health check phản ánh khả năng tiếp cận ứng dụng từ góc nhìn của bộ cân bằng tải. Hai kết quả bổ sung cho nhau nhưng không thay thế nhau. Cấu hình grace period cho service cần đủ dài để task mới khởi động trước khi nền tảng đánh giá trạng thái chưa khỏe.

**Ví dụ với Kubernetes trên EKS, GKE hoặc AKS:** Deployment quản lý số bản sao và rollout; kubelet thực thi startup, readiness và liveness probe; Service và EndpointSlice phản ánh các Pod đủ điều kiện nhận lưu lượng. Load balancer hoặc ingress có thể thực hiện thêm health check ở lớp mạng vào ứng dụng. Khi nhiều lớp cùng kiểm tra, đường dẫn, cổng, timeout và kỳ vọng phản hồi cần nhất quán.

Một probe ở lớp ngoài có thể thất bại dù probe bên trong container thành công, ví dụ ứng dụng lắng nghe `127.0.0.1` thay vì địa chỉ có thể truy cập từ mạng Pod hoặc security rule chặn đường đến target. Khi điều tra, hãy kiểm tra từng chặng từ container, Pod, Service đến load balancer.

## 6. Vòng đời triển khai của container service

Một lần triển khai an toàn thường đi qua các giai đoạn sau:

1. **Build và đóng gói:** tạo image từ mã nguồn, chạy kiểm tra cần thiết và gắn tag phiên bản bất biến. Với môi trường quan trọng, ghi nhận image digest để xác định chính xác nội dung đã triển khai.
2. **Đẩy image và tạo revision:** đẩy image lên registry, cập nhật cấu hình service hoặc Deployment để nền tảng tạo revision hay ReplicaSet mới.
3. **Lập lịch và khởi động:** nền tảng cấp tài nguyên, tải image, tạo container và khởi chạy tiến trình. Startup probe cho ứng dụng thời gian hoàn tất khởi tạo.
4. **Kiểm tra readiness:** khi startup thành công, readiness probe bắt đầu xác định instance có thể nhận lưu lượng hay chưa. Instance chưa Ready không được đưa vào endpoint phục vụ thông thường.
5. **Chuyển lưu lượng:** khi số bản sao mới đạt điều kiện sẵn sàng, cơ chế rollout tăng dần lưu lượng hoặc thay thế bản sao cũ. Cần theo dõi lỗi, độ trễ và tỷ lệ yêu cầu thành công trong giai đoạn này.
6. **Rút bản cũ và dừng có kiểm soát:** instance cũ ngừng nhận yêu cầu mới, hoàn tất các yêu cầu đang xử lý trong thời gian cho phép, rồi kết thúc tiến trình. Ứng dụng cần xử lý `SIGTERM`, đóng kết nối và giải phóng tài nguyên trước khi hết thời gian grace period.
7. **Hoàn tất hoặc rollback:** nếu revision mới ổn định, kết thúc rollout. Nếu probe thất bại kéo dài, Pod liên tục restart, hoặc chỉ số dịch vụ xấu đi, dừng rollout và khôi phục revision trước đó.

Readiness là một phần quan trọng của quá trình rút instance khỏi lưu lượng. Khi bắt đầu shutdown, ứng dụng có thể chuyển readiness sang thất bại trước, đợi một khoảng ngắn để cập nhật endpoint và load balancer lan truyền, sau đó xử lý các yêu cầu đang chạy và thoát khi nhận `SIGTERM`. Có thể dùng lifecycle hook như `preStop` để kích hoạt chế độ drain, nhưng thời gian hook và thời gian shutdown đều nằm trong giới hạn `terminationGracePeriodSeconds`. Hãy bảo đảm ứng dụng có thời gian thực tế để hoàn tất yêu cầu; nếu grace period quá ngắn, yêu cầu đang xử lý có thể bị ngắt.

Với rolling update, `maxUnavailable: 0` giúp giữ đủ bản sao sẵn sàng trong khi thay phiên bản, nhưng cần tài nguyên cho Pod mới và có thể khiến rollout chờ nếu probe readiness cấu hình sai. Một chính sách chuyển lưu lượng theo tỷ lệ hoặc theo revision ở nền tảng quản lý có thể giảm phạm vi ảnh hưởng, nhưng cần có tiêu chí dừng và rollback rõ ràng.

## 7. Trade-off và lỗi cấu hình thường gặp

| Quyết định | Lợi ích | Rủi ro cần kiểm soát |
|---|---|---|
| Readiness kiểm tra nhiều phụ thuộc | Tránh nhận yêu cầu khi service không thể hoàn thành nghiệp vụ. | Sự cố phụ thuộc có thể làm tất cả replica rời khỏi lưu lượng cùng lúc. |
| Liveness kiểm tra cả database hoặc API bên ngoài | Có vẻ bao quát nhiều thành phần. | Lỗi mạng hoặc sự cố bên ngoài gây restart hàng loạt và làm tình hình nặng hơn. |
| Timeout quá ngắn | Phát hiện nhanh instance không phản hồi. | Tải cao hoặc GC pause ngắn gây probe thất bại giả. |
| Failure threshold quá thấp | Phát hiện lỗi nhanh. | Một đợt chậm ngắn có thể gây restart hoặc loại instance khỏi lưu lượng. |
| Startup window quá ngắn | Rút ngắn thời gian phát hiện khởi động lỗi. | Ứng dụng khởi động hợp lệ nhưng chậm bị restart lặp lại. |
| Startup window quá dài | Chấp nhận ứng dụng có thời gian khởi động biến động. | Lỗi khởi động thật bị phát hiện muộn, kéo dài rollout. |
| Readiness chỉ kiểm tra cổng TCP | Cấu hình đơn giản, ít phụ thuộc. | Cổng mở nhưng ứng dụng chưa xử lý được nghiệp vụ. |

Các dấu hiệu cần chú ý:

- `CrashLoopBackOff`: xem log trước lần thoát, sự kiện Pod và kết quả startup/liveness; kiểm tra cấu hình, tài nguyên và thời gian khởi động.
- Pod `Running` nhưng `NotReady`: kiểm tra endpoint readiness, dependency, cổng, đường dẫn và phản hồi HTTP.
- Rollout đứng lâu: kiểm tra Pod mới có Ready không, `minReadySeconds`, tài nguyên, image pull và giới hạn surge.
- Tất cả replica cùng mất Ready: xem xét phụ thuộc dùng chung, network policy, DNS, chứng thư, secret hoặc readiness quá chặt.
- Instance bị restart khi tải tăng: xem timeout, CPU throttling, memory limit, thời gian dừng GC và việc endpoint health có tranh chấp tài nguyên với request thật hay không.

## 8. Quy trình xác minh sau cấu hình hoặc triển khai

Thực hiện trên môi trường thử nghiệm trước khi áp dụng cho service đang nhận lưu lượng.

1. Gọi trực tiếp ba endpoint từ bên trong Pod hoặc container. Xác nhận startup chỉ thành công sau khi khởi tạo xong; readiness phản ánh khả năng nhận yêu cầu; liveness tiếp tục thành công khi một phụ thuộc ngoài tạm thời lỗi nhưng tiến trình vẫn hoạt động.
2. Áp dụng manifest và theo dõi rollout:

   ```bash
   kubectl apply -f orders-api.yaml
   kubectl rollout status deployment/orders-api
   kubectl get pods -l app=orders-api -w
   ```

3. Nếu Pod chưa Ready, xem trạng thái, sự kiện và log:

   ```bash
   kubectl describe pod <pod-name>
   kubectl logs <pod-name> -c api
   kubectl get endpointslices -l kubernetes.io/service-name=orders-api
   ```

   Kiểm tra `Events` để biết probe nào thất bại, số lần thất bại và thông báo như timeout, connection refused hoặc HTTP status không hợp lệ. EndpointSlice giúp xác nhận Pod nào đang được Service đưa vào danh sách endpoint.

4. Kiểm thử các tình huống có chủ đích trong môi trường thử nghiệm: kéo dài thời gian khởi động, làm endpoint readiness trả lỗi, tạm ngắt một phụ thuộc thiết yếu và mô phỏng tiến trình không còn phản hồi. Quan sát đúng hành vi mong đợi: startup chờ trong giới hạn, readiness loại instance khỏi lưu lượng mà không restart, liveness kích hoạt restart khi tiến trình thực sự không khỏe.
5. Kiểm tra shutdown có kiểm soát: gửi tín hiệu dừng hoặc xóa một Pod, xác nhận instance ngừng nhận request mới, request đang chạy được hoàn tất trong grace period và các Pod còn lại tiếp tục phục vụ.
6. Sau rollout, kiểm tra tỷ lệ lỗi, độ trễ, số lần restart, thời gian Ready và trạng thái revision. Nếu cần khôi phục Deployment về revision trước:

   ```bash
   kubectl rollout history deployment/orders-api
   kubectl rollout undo deployment/orders-api
   ```

Với dịch vụ trên nền tảng khác, dùng trang trạng thái task/revision, sự kiện triển khai, log container và trạng thái target health tương ứng. Xác minh cả health check nội bộ lẫn health check của load balancer nếu nền tảng sử dụng cả hai.

## 9. Checklist vận hành

- [ ] Startup, readiness và liveness có mục đích riêng, phù hợp với vòng đời ứng dụng.
- [ ] Endpoint health phản hồi nhanh, không yêu cầu xác thực người dùng và không thực hiện truy vấn nặng.
- [ ] Liveness không phụ thuộc vào dịch vụ bên ngoài có thể gây restart hàng loạt.
- [ ] Readiness chỉ kiểm tra những điều kiện thực sự cần để nhận yêu cầu.
- [ ] Timeout, chu kỳ và ngưỡng thất bại dựa trên số liệu khởi động và tải thực tế.
- [ ] Rollout có đủ tài nguyên, số bản sao tối thiểu và thời gian chờ khởi động phù hợp.
- [ ] Ứng dụng xử lý `SIGTERM`, drain request và thoát trong grace period.
- [ ] Đã thử tình huống startup chậm, readiness thất bại, liveness thất bại và rollback trong môi trường thử nghiệm.
- [ ] Có theo dõi probe failure, restart, thời gian rollout, tỷ lệ lỗi và độ trễ sau triển khai.

## Kết luận

Health probe giúp nền tảng hiểu khi nào container đã khởi động, khi nào instance có thể nhận lưu lượng và khi nào tiến trình cần được khởi động lại. Kết hợp probe được thiết kế đúng với rolling update, shutdown có kiểm soát, theo dõi chỉ số và rollback giúp container service triển khai phiên bản mới ổn định hơn, giảm gián đoạn và rút ngắn thời gian xử lý sự cố.