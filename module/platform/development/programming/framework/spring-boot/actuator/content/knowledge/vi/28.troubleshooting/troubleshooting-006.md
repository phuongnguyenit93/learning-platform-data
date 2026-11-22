# Phân tích probe thành công trong khi ứng dụng không nhận được yêu cầu

## 1. Probe thành công chứng minh điều gì?

Một probe thành công chỉ chứng minh **phép kiểm tra được cấu hình đã thành công tại thời điểm kiểm tra**. Nó không tự chứng minh rằng mọi yêu cầu của người dùng đi qua được toàn bộ hệ thống.

Trong một triển khai Spring Boot trên Kubernetes, hai đường đi thường khác nhau:

```text
Đường kiểm tra:
kubelet -> địa chỉ Pod -> cổng và đường dẫn của probe

Đường phục vụ:
người dùng -> DNS / bộ cân bằng tải -> Ingress hoặc Gateway
           -> Service -> endpoint của Pod -> cổng ứng dụng
           -> bộ lọc -> controller -> xử lý nghiệp vụ
```

Theo cấu hình HTTP probe thông thường, kubelet gọi IP của Pod với cổng và đường dẫn đã khai báo. Nó không mặc nhiên đi qua Service hay Ingress. Trường `httpGet.host` có thể thay đổi đích kết nối; mặc định của trường này là IP Pod. Xem [HTTPGetAction trong API Kubernetes](https://kubernetes.io/docs/reference/kubernetes-api/core/pod-v1/#HTTPGetAction).

Vì vậy, câu “probe xanh nhưng không có yêu cầu” chưa phải một nguyên nhân. Cần xác định:

- Probe nào thành công: liveness, readiness hay startup?
- Nó gọi đúng tiến trình, cổng, đường dẫn và giao thức nào?
- “Không nhận được yêu cầu” nghĩa là không có kết nối, không vào controller, hay đã nhận nhưng không xử lý xong?
- Thành công được quan sát ở Pod nào, thời điểm nào, phiên bản triển khai nào?

Bài này dùng thuộc tính của **Spring Boot 3.3.x** và mô hình Kubernetes có Service chọn Pod bằng nhãn. Các ví dụ cấu hình là mảnh ghép cho một ứng dụng đã tồn tại, không phải một dự án Java hoặc bộ manifest triển khai hoàn chỉnh.

## 2. Đừng đồng nhất ba loại probe

| Probe | Câu hỏi chính | Tác động cần phân biệt |
| --- | --- | --- |
| Liveness | Tiến trình có ở trạng thái cần khởi động lại để phục hồi không? | Khi thất bại đủ ngưỡng, kubelet có thể khởi động lại container |
| Readiness | Container đã sẵn sàng tham gia phục vụ lưu lượng chưa? | Góp phần quyết định trạng thái sẵn sàng của Pod và việc định tuyến tới Pod |
| Startup | Ứng dụng đã vượt qua giai đoạn khởi động chưa? | Khi được cấu hình, trì hoãn liveness/readiness cho đến khi startup thành công |

Các vai trò này được mô tả trong [tài liệu probe của Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/probes/). Liveness thành công không thay thế readiness; startup thành công cũng không kiểm tra toàn bộ đường đi của yêu cầu người dùng.

HTTP probe đánh giá thành công theo mã phản hồi trong khoảng 200 đến dưới 400, đồng thời có quy tắc xử lý chuyển hướng. Nó không tự diễn giải JSON nghiệp vụ. Với Actuator, cần bảo đảm trạng thái không sẵn sàng được ánh xạ sang mã lỗi phù hợp, thay vì chỉ nhìn thấy trường JSON có vẻ đúng. Xem [cấu hình HTTP probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Một số ví dụ suy luận:

- `/actuator/health/liveness` trả 200: tiến trình vượt qua kiểm tra sống; chưa xác nhận Pod đang được Service chọn.
- `/actuator/health/readiness` trả 200: nhóm readiness vượt qua kiểm tra; chưa xác nhận Ingress có route đúng.
- TCP probe mở được kết nối: chưa xác nhận HTTP trả lời đúng đường dẫn hay nghiệp vụ hoạt động.
- Exec probe gọi `localhost` thành công: chưa xác nhận một nguồn bên ngoài Pod truy cập được cùng tài nguyên.

Nếu thấy chuyển hướng hoặc `ProbeWarning`, kiểm tra đích chuyển hướng và sự kiện. Đừng lấy kết quả của một lần `curl` với tùy chọn theo chuyển hướng khác nhau làm bằng chứng rằng kubelet đã kiểm tra cùng một tài nguyên.

## 3. Nguyên nhân điển hình: probe chỉ kiểm tra cổng quản trị

Xét cấu hình `application.yml`:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
```

Ứng dụng phục vụ API trên 8080, còn Actuator dùng 8081. Mảnh cấu hình container sau là một cấu hình probe có phạm vi kiểm tra hẹp:

```yaml
ports:
  - name: http
    containerPort: 8080
  - name: management
    containerPort: 8081

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: management
    scheme: HTTP
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
```

Kubelet đang kiểm tra 8081. Nếu cổng 8080 không nhận thêm kết nối hoặc hạ tầng xử lý yêu cầu trên cổng đó gặp vấn đề, 8081 vẫn có thể trả lời probe.

Spring Boot lưu ý rằng management context riêng có thể sử dụng hạ tầng web khác cổng chính, gồm cổng, các nhóm kết nối và thành phần framework. Vì vậy, kết quả probe ở đó có thể không phản ánh khả năng phục vụ của máy chủ chính. Xem [Kubernetes Probes trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Đây là một **giả thuyết cần kiểm chứng**, không phải kết luận mặc định cho mọi sự cố. Bằng chứng hữu ích là so sánh đồng thời:

| Điểm gọi | Câu hỏi được kiểm tra |
| --- | --- |
| Cổng 8081, readiness | Hạ tầng quản trị và nhóm readiness có phản hồi không? |
| Cổng 8080, probe trên cổng chính | Máy chủ phục vụ có xử lý được yêu cầu kiểm tra không? |
| Cổng 8080, API đang lỗi | Tuyến API và các bước xử lý liên quan có hoạt động không? |

Không cần làm cổng quản trị hỏng để chứng minh cổng chính đang gặp vấn đề. Chỉ cần chỉ ra hai yêu cầu đi qua hạ tầng khác nhau và quan sát được kết quả khác nhau.

## 4. Đưa probe lên cổng phục vụ chính

Với Spring Boot 3.3, có thể thêm các đường dẫn probe trên máy chủ chính bằng `management.endpoint.health.probes.add-additional-paths`.

Thay cấu hình ứng dụng ở mục 3 bằng:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Trong ví dụ dùng đường dẫn ngữ cảnh gốc và không có ánh xạ tùy chỉnh, cổng 8080 có thêm `/livez` và `/readyz`. Cổng 8081 vẫn có các đường dẫn health tương ứng của Actuator.

Sau đó **phải đổi chính cấu hình probe** sang cổng chính. Chỉ bật thuộc tính rồi vẫn để probe gọi 8081 thì chưa thay đổi đường đi kiểm tra.

Mảnh cấu hình đặt bên trong container của Pod template:

```yaml
ports:
  - name: http
    containerPort: 8080
  - name: management
    containerPort: 8081

readinessProbe:
  httpGet:
    path: /readyz
    port: http
    scheme: HTTP
  periodSeconds: 5
  timeoutSeconds: 2
  successThreshold: 1
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /livez
    port: http
    scheme: HTTP
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
```

Các ngưỡng trên là giá trị minh họa, cần chọn theo thời gian phản hồi và đặc điểm khởi động thực tế. Nếu ứng dụng khởi động lâu, đánh giá thêm startup probe; không tăng liveness tùy tiện để che một vấn đề sau khởi động.

Ba điểm cần kiểm tra khi áp dụng:

1. **Cổng được khai báo không tự làm Java lắng nghe.** `containerPort: 8080` là khai báo trong manifest; tiến trình vẫn phải thực sự bind và phục vụ ở cổng đó.
2. **Đường dẫn phải đúng với ứng dụng đang chạy.** Nếu có context path, đường dẫn bổ sung tùy chỉnh, TLS hoặc lớp bảo mật, kiểm tra URL thực tế thay vì sao chép nguyên ví dụ. Quy tắc cổng và base path được trình bày tại [Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).
3. **Probe trên cổng chính vẫn chưa phải kiểm tra toàn bộ hệ thống.** Nó tăng độ gắn kết với máy chủ phục vụ, nhưng không tự kiểm tra DNS công khai, Service, Ingress và mọi phụ thuộc nghiệp vụ.

Giữ endpoint kiểm tra nhanh, có thời gian chờ hữu hạn và ý nghĩa rõ. Một endpoint luôn trả 200 bất kể trạng thái thực tế không cung cấp bằng chứng sẵn sàng hữu ích.

## 5. Probe đúng nhưng Service gửi sai nơi

Giả sử Pod template của Deployment `orders` có nhãn:

```yaml
metadata:
  labels:
    app: orders
```

Đây là nhãn của **Pod template**, không chỉ nhãn trên đối tượng Deployment bên ngoài.

Service tương ứng trong namespace `learning`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: learning
spec:
  selector:
    app: orders
  ports:
    - name: http
      port: 80
      targetPort: http
```

Ở đây:

- `port: 80` là cổng Service nhận.
- `targetPort: http` tham chiếu tên cổng `http` của Pod, tức 8080 trong ví dụ.
- Selector phải khớp Pod cần phục vụ.

Kubernetes cho phép Service ánh xạ cổng nhận sang cổng đích khác hoặc dùng tên cổng. Xem [định nghĩa cổng Service](https://kubernetes.io/docs/concepts/services-networking/service/#port-definitions).

Một lỗi có thể xảy ra là Service dùng:

```yaml
ports:
  - name: http
    port: 80
    targetPort: management
```

Khi ấy, probe trên 8081 có thể thành công và Service cũng gửi lưu lượng vào 8081, trong khi API cần cổng 8080. Tên cổng Service là `http` không thay đổi ý nghĩa của `targetPort`.

Một lỗi khác là selector chọn nhầm phiên bản hoặc không chọn Pod nào. Probe được thực hiện trên một Pod không chứng minh rằng Service của người dùng đang trỏ tới Pod đó.

Đừng chỉ nhìn cột `Running`: đó không phải bằng chứng đã có endpoint phục vụ đúng Service.

## 6. Readiness của một container chưa phải mọi điều kiện định tuyến

Ngay cả khi readiness của container ứng dụng thành công, Pod vẫn có thể chưa `Ready` vì container khác hoặc readiness gate chưa đạt. Các readiness gate tùy chỉnh cũng tham gia quyết định; xem [Pod readiness](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-readiness).

Tiếp theo, cần kiểm tra EndpointSlice của đúng Service:

- Có địa chỉ của Pod đang phân tích không?
- Cổng endpoint có đúng cổng API không?
- Các điều kiện `ready`, `serving`, `terminating` đang là gì?
- Pod có đang bị xóa hoặc chuyển phiên bản trong lúc quan sát không?

Không áp dụng quy tắc “không ready thì tuyệt đối không bao giờ có lưu lượng” cho mọi cấu hình. Chẳng hạn, `publishNotReadyAddresses` ảnh hưởng cách công bố endpoint; điều kiện `ready` trong EndpointSlice có ngoại lệ khi thuộc tính đó được bật. Các điều kiện này được mô tả tại [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/#conditions).

Cũng cần tính đến thời gian. Một lần probe thành công, cập nhật trạng thái Pod và cập nhật đường định tuyến không phải cùng một thao tác tức thời. So sánh dữ liệu gần nhau về thời điểm và đúng Pod; tránh ghép ảnh chụp từ các thời điểm khác nhau thành một kết luận.

## 7. Quy trình khoanh vùng bằng bằng chứng

### 7.1. Đặt bối cảnh cho các lệnh

Các lệnh dưới đây dùng tình huống minh họa:

- Namespace: `learning`.
- Deployment và Service: `orders`.
- Nhãn Pod: `app=orders`.
- Cổng ứng dụng: 8080; cổng quản trị: 8081.
- Ứng dụng đã có API `GET /api/orders`.

Chúng là lệnh chẩn đoán cho môi trường có các tài nguyên trên; không tạo tài nguyên và không giả định rằng đầu ra của cluster nào cũng giống nhau. Dùng các giá trị của triển khai cần kiểm tra khi áp dụng.

### 7.2. Kiểm tra cấu hình và trạng thái thực tế

```shell
kubectl -n learning get deployment orders -o yaml
kubectl -n learning get pods -l app=orders -o wide
kubectl -n learning describe pods -l app=orders
kubectl -n learning get service orders -o yaml
kubectl -n learning get endpointslices -l kubernetes.io/service-name=orders -o yaml
```

Đọc cấu hình probe của Pod đang chạy, không chỉ file manifest trong mã nguồn. Kiểm tra:

- `httpGet.path`, `port`, `scheme`, các header và `host` nếu được đặt.
- Readiness của từng container, điều kiện Pod và sự kiện probe.
- Nhãn Pod có khớp selector Service không.
- EndpointSlice có đúng địa chỉ/cổng của các Pod cần phục vụ không.
- Có nhiều replica hoặc phiên bản cùng được chọn không.

Nếu workload có nhiều replica, không coi một Pod khỏe là đại diện cho tất cả. Lỗi chỉ xuất hiện với một phần yêu cầu có thể liên quan đến tập backend không đồng nhất.

### 7.3. So sánh cổng quản trị với cổng ứng dụng

Một phép thử tiện dụng là port-forward tới Deployment:

```shell
kubectl -n learning port-forward deployment/orders 18080:8080 18081:8081
```

Giữ terminal này mở và gọi từ terminal khác:

```shell
curl -i --max-time 3 http://127.0.0.1:18081/actuator/health/readiness
curl -i --max-time 3 http://127.0.0.1:18080/readyz
curl -i --max-time 3 http://127.0.0.1:18080/api/orders
```

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` là alias. `-i` hiển thị mã/header cùng phần thân; `--max-time` giới hạn thời gian cho phép thử.

Đọc kết quả theo điều kiện:

| Nếu quan sát được | Suy luận ban đầu |
| --- | --- |
| Readiness 18081 thành công, `/readyz` trên 18080 timeout | Cần kiểm tra hạ tầng cổng chính và cấu hình đường dẫn bổ sung |
| `/readyz` thành công, API trả lỗi | Cổng chính trả lời được probe; kiểm tra tuyến API và các bước nghiệp vụ |
| Cả ba thành công, người dùng vẫn lỗi | Tiếp tục kiểm tra Service, Ingress/Gateway và đường đi bên ngoài |
| Probe nhận 404 | Kiểm tra đường dẫn, cổng, phiên bản và cấu hình công bố; chưa kết luận tiến trình bị treo |

Port-forward tới Deployment chọn một Pod. Ghi nhận Pod đã được chọn và lặp lại khi cần kiểm tra các replica khác. Đặc biệt, **port-forward bỏ qua đường đi thông thường qua Service và Ingress**; thành công ở đây không xác nhận đường mạng thông thường từ kubelet hay client khác đã hoạt động.

Nếu `/readyz` chưa được bật, một 404 tại đó không thể dùng để đánh giá khả năng phục vụ của cổng chính. Trước hết xác minh cấu hình bổ sung đã có hiệu lực.

### 7.4. Kiểm tra từng chặng của đường phục vụ

Từ một vị trí chẩn đoán phù hợp trong cluster và có công cụ cần thiết, so sánh lần lượt:

```text
Pod IP + cổng ứng dụng + đường dẫn API
Service DNS + cổng Service + cùng đường dẫn API
Địa chỉ Ingress/Gateway + Host/path đúng của người dùng
```

Phải giữ các yếu tố liên quan tương đương: phương thức, đường dẫn, header `Host`, thông tin xác thực được cấp và giao thức. Đừng so sánh một GET công khai với một POST cần xác thực rồi cho rằng đường mạng khác nhau là nguyên nhân duy nhất.

Nếu Pod trực tiếp hoạt động nhưng Service không hoạt động, ưu tiên selector, EndpointSlice, targetPort và hạ tầng mạng Service. Nếu Service hoạt động nhưng Ingress không, kiểm tra backend Service/port, host/path, quy tắc viết lại đường dẫn và TLS.

Đây là cách thu hẹp phạm vi, không phải khẳng định mỗi mã lỗi chỉ có một nguyên nhân. Có thể tham khảo quy trình chính thức [Debug Services](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/).

### 7.5. Xác định yêu cầu dừng trước hay sau controller

“Không thấy log trong controller” chưa chứng minh rằng tiến trình không nhận yêu cầu. Yêu cầu có thể bị bộ lọc bảo mật, router hoặc xử lý lỗi chặn trước khi vào controller; cũng có thể ứng dụng chưa bật loại log mà bạn đang tìm.

Có thể đọc log gần thời điểm phép thử:

```shell
kubectl -n learning logs -l app=orders --all-containers=true --prefix=true --since=10m --tail=2000 --max-log-requests=10
```

Đối chiếu thêm access log, log proxy/gateway và mã định danh yêu cầu nếu hệ thống đã hỗ trợ. Với nhiều Pod hoặc hơn 10 luồng log, chia phạm vi truy vấn cho phù hợp; một lệnh không bảo đảm thu được mọi dữ kiện.

Phân biệt ít nhất ba tình huống:

1. Yêu cầu chưa tới cổng ứng dụng.
2. Yêu cầu đã tới hạ tầng HTTP nhưng chưa vào controller.
3. Controller đã chạy nhưng đang chờ luồng, kết nối cơ sở dữ liệu hoặc dịch vụ khác.

Chúng cần những cách sửa khác nhau. Tăng timeout probe không sửa selector sai; sửa Ingress không giải phóng một nhóm kết nối cơ sở dữ liệu đã cạn.

## 8. Probe trên cổng chính thành công nhưng nghiệp vụ vẫn không chạy được

Một endpoint readiness nhẹ có thể trả lời dù một thao tác nghiệp vụ đang lỗi vì:

- Nhóm kết nối cơ sở dữ liệu cạn hoặc truy vấn chờ lâu.
- Dịch vụ phụ thuộc không truy cập được.
- Một nhóm luồng thực thi nghiệp vụ riêng bị đầy.
- Đường dẫn API bị cấu hình sai hoặc bị từ chối quyền.
- API cần dữ liệu/khả năng mà nhóm readiness chưa kiểm tra.

Không suy ngược rằng mọi sự cố đó chắc chắn tồn tại chỉ từ kết quả probe. Hãy kiểm tra số yêu cầu đang xử lý, thời gian chờ, trạng thái nhóm luồng/kết nối và log của đúng thao tác.

Trong Spring Boot, readiness dựa trên trạng thái sẵn sàng của ứng dụng và có thể được mở rộng. Trạng thái `ACCEPTING_TRAFFIC` là thông tin availability của ứng dụng, không phải một giao dịch nghiệp vụ tổng hợp được chạy lại cho mọi lần probe. Xem [Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

Nếu một phụ thuộc thực sự là điều kiện để phục vụ, có thể cân nhắc đưa kiểm tra tương ứng vào readiness. Ví dụ cấu hình sau chỉ phù hợp khi contributor `db` thực sự tồn tại:

```properties
management.endpoint.health.group.readiness.include=readinessState,db
```

Giữ `readinessState` nếu vẫn muốn nhóm phản ánh trạng thái sẵn sàng do Spring quản lý. Đồng thời kiểm tra mã HTTP, chi phí và thời gian chờ của indicator. Không thêm mọi hệ thống bên ngoài vào liveness: khởi động lại ứng dụng không nhất thiết khôi phục được một cơ sở dữ liệu dùng chung đang lỗi.

Việc bỏ toàn bộ replica khỏi phục vụ khi một phụ thuộc dùng chung hỏng cũng là quyết định kiến trúc, không phải công thức áp dụng cho mọi hệ thống. Cần xét khả năng phục vụ một phần và các cơ chế dự phòng hiện có.

Một phép kiểm tra từ bên ngoài đi qua đúng DNS/Ingress/API có thể bổ sung bằng chứng về trải nghiệm thật. Nó phục vụ mục tiêu khác với probe của kubelet; không cần biến mọi liveness probe thành một giao dịch nghiệp vụ nặng.

## 9. Chọn cách sửa theo bằng chứng

| Bằng chứng chính | Hướng sửa phù hợp |
| --- | --- |
| Probe chỉ gọi management port, cổng chính đang không đáp ứng | Bổ sung probe trên cổng chính và xử lý nguyên nhân máy chủ chính bị nghẽn |
| Readiness tốt, Service chọn sai nhãn | Sửa selector/nhãn của đúng tài nguyên |
| EndpointSlice trỏ sai cổng | Sửa targetPort hoặc tên cổng tương ứng |
| Container ứng dụng ready, Pod chưa Ready | Kiểm tra container còn lại và readiness gate |
| Service nội bộ tốt, đường Ingress lỗi | Sửa route, backend, Host/path, rewrite hoặc TLS theo log |
| Request đã vào controller nhưng bị chờ | Xử lý giới hạn tài nguyên hoặc phụ thuộc trong đường nghiệp vụ |
| Probe nhận 200 từ một tài nguyên không đúng | Sửa đích kiểm tra và xác minh phản hồi đúng ý nghĩa |

Đừng chuyển mọi probe sang `/actuator/health`, mở toàn bộ endpoint, bỏ bảo mật hoặc tăng mọi ngưỡng chỉ để màu trạng thái thay đổi. Thay đổi probe cần giúp nó kiểm tra đúng điều kiện phục vụ và dẫn tới hành động phục hồi phù hợp.

## 10. Tự kiểm tra khả năng suy luận

**A. Liveness trả 200 nhưng Service không có endpoint sẵn sàng. Có mâu thuẫn không?**

Không. Liveness không thay readiness, không sửa selector và không bảo đảm trạng thái Pod đã đủ điều kiện phục vụ.

**B. Actuator 8081 trả lời tốt, API 8080 timeout. Probe đã chứng minh cổng 8080 khỏe chưa?**

Chưa. Kiểm tra hai cổng riêng và cân nhắc đường dẫn probe bổ sung trên cổng chính.

**C. `/readyz` trên 8080 tốt nhưng người dùng vẫn nhận lỗi từ Ingress.**

Tiếp tục kiểm tra Service/EndpointSlice và Ingress/Gateway. Probe trên cổng chính vẫn không đi qua toàn bộ tuyến bên ngoài.

**D. Không có log controller nhưng gateway có phản hồi 401/403 hoặc 404.**

Kiểm tra yêu cầu đã dừng ở gateway, bộ lọc hay ánh xạ nào. Thiếu log controller không đồng nghĩa không có yêu cầu tới hệ thống.

**E. Sau khi bật `add-additional-paths`, manifest vẫn probe cổng `management`. Đã tăng phạm vi kiểm tra chưa?**

Chưa. Phải cập nhật đích probe sang đường dẫn bổ sung và cổng chính, rồi xác minh cấu hình của Pod đang chạy.

**F. Port-forward tới một Pod thành công. Có thể khẳng định mọi replica và đường Service đều hoạt động không?**

Không. Phép thử chỉ xác nhận phạm vi Pod/đường chuyển tiếp đã dùng. Cần kiểm tra các replica liên quan và đường mạng thực tế của lưu lượng.
