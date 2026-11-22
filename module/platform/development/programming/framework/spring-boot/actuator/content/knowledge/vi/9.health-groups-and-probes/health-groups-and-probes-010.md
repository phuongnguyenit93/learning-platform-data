# Phối hợp chu kỳ kiểm tra, timeout và ngưỡng lỗi với thời gian khởi động

## 1. Bài toán: ứng dụng đang khởi động chậm hay đã hỏng?

Một ứng dụng Spring Boot có thể mất thời gian để tạo bean, mở máy chủ HTTP, chạy migration và nạp dữ liệu ban đầu. Trong khoảng đó, kết nối đến endpoint kiểm tra có thể bị từ chối hoặc chưa trả về trạng thái sẵn sàng. Nếu nền tảng coi mọi lần kiểm tra thất bại là lý do khởi động lại ngay, ứng dụng có thể bị dừng trước khi hoàn thành khởi tạo và lặp lại tình trạng này mãi.

Ngược lại, nếu kéo dài mọi ngưỡng chỉ để vượt qua lần khởi động chậm, một tiến trình bị treo sau khi đã phục vụ bình thường có thể tiếp tục tồn tại quá lâu. Vì vậy, cần thiết kế riêng ba quyết định:

| Loại kiểm tra (probe) | Câu hỏi cần trả lời | Hành động khi thất bại đủ ngưỡng |
| --- | --- | --- |
| `startupProbe` | Ứng dụng đã đạt mốc khởi động được chọn chưa? | Kubelet dừng container; việc chạy lại tuân theo chính sách khởi động lại |
| `livenessProbe` | Tiến trình còn ở trạng thái có thể tiếp tục hoạt động không? | Kubelet dừng container; với Deployment, container thường được khởi động lại |
| `readinessProbe` | Bản sao này có nên nhận yêu cầu qua Service lúc này không? | Container tiếp tục chạy, nhưng không được coi là sẵn sàng để nhận lưu lượng thông thường qua Service |

Khi có startup probe, kubelet chưa thực hiện liveness và readiness probe cho đến khi startup probe thành công. Startup probe kết thúc vai trò sau lần thành công đó; nó không tiếp tục giám sát suốt vòng đời container. Liveness và readiness sau đó vận hành độc lập: readiness thất bại không tự làm liveness ngừng kiểm tra.

Các vai trò này được mô tả trong [tài liệu Kubernetes về probe](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Trong bài này, **Actuator cung cấp tín hiệu sức khỏe; kubelet quyết định lịch kiểm tra và hành động**. Chỉnh YAML của Spring Boot không tự thay đổi chu kỳ probe trong Kubernetes.

## 2. Hiểu từng tham số trước khi ghép chúng

Các trường bên dưới thuộc từng cấu hình probe trong manifest Kubernetes. Đơn vị thời gian là giây.

| Trường | Ý nghĩa thực tế | Giá trị mặc định |
| --- | --- | --- |
| `initialDelaySeconds` | Khoảng trì hoãn trước khi bắt đầu kiểm tra | `0` |
| `periodSeconds` | Chu kỳ dự kiến giữa các lần kiểm tra | `10` |
| `timeoutSeconds` | Thời gian tối đa chờ một lần kiểm tra trước khi coi là hết hạn | `1` |
| `failureThreshold` | Số lần thất bại liên tiếp cần đạt để probe bị coi là thất bại | `3` |
| `successThreshold` | Số lần thành công liên tiếp cần đạt để probe được coi là thành công sau thất bại | `1` |

`periodSeconds`, `timeoutSeconds`, `failureThreshold` và `successThreshold` có giá trị tối thiểu là `1`; `initialDelaySeconds` có thể bằng `0`. Với liveness và startup, `successThreshold` bắt buộc là `1`. Readiness có thể dùng giá trị lớn hơn để yêu cầu phục hồi ổn định hơn. Xem [định nghĩa Probe trong Kubernetes API](https://kubernetes.io/docs/reference/kubernetes-api/core/pod-v1/#Probe).

### 2.1. Timeout là giới hạn cho một lần kiểm tra

Ví dụ `timeoutSeconds: 2` nghĩa là một yêu cầu probe không được chờ vô hạn. Nó không cấp cho toàn bộ quá trình khởi động hai giây và cũng không nói rằng cứ sau hai giây sẽ khởi động lại container.

Hai dạng thất bại có thời lượng khác nhau:

- Kết nối bị từ chối hoặc endpoint trả HTTP 503 ngay: lần kiểm tra có thể thất bại rất nhanh.
- Kết nối được mở nhưng endpoint không phản hồi: lần kiểm tra có thể phải chờ đến timeout.

Do đó, cùng một chu kỳ và ngưỡng lỗi nhưng thời điểm đạt ngưỡng có thể khác nhau.

HTTP probe xét kết quả HTTP, không phân tích trường `status` trong JSON để tự quyết định. Endpoint phải trả mã HTTP phù hợp với trạng thái sức khỏe; không được đổi mọi kết quả thành HTTP 200 rồi kỳ vọng kubelet hiểu phần nội dung.

### 2.2. Ngưỡng lỗi đếm một chuỗi liên tiếp

Với `failureThreshold: 3`, chuỗi dưới đây chỉ đạt ngưỡng ở lần cuối:

```text
Kết quả:       lỗi  lỗi  đạt  lỗi  lỗi  lỗi
Số lỗi liền:     1    2    0    1    2    3
```

Không cộng mọi lỗi kể từ khi ứng dụng bắt đầu. Một lần thành công ngắt chuỗi lỗi liên tiếp.

Với readiness, `successThreshold: 2` giúp tránh đưa bản sao trở lại phục vụ ngay sau một kết quả thành công đơn lẻ. Đổi lại, thời gian trở lại trạng thái sẵn sàng sẽ tăng. Cần cân nhắc giữa độ ổn định và khả năng bổ sung lại năng lực phục vụ nhanh chóng.

### 2.3. Chu kỳ nhỏ tạo nhiều mẫu hơn, không làm endpoint tự nhanh lên

Giảm `periodSeconds` có thể phát hiện thay đổi sớm hơn, nhưng làm tăng số yêu cầu kiểm tra. Nếu endpoint chạy truy vấn nặng, việc kiểm tra dày còn tạo thêm tải đúng lúc hệ thống đang thiếu tài nguyên.

Với 50 bản sao, mỗi bản có liveness chu kỳ 10 giây và readiness chu kỳ 5 giây, tốc độ kiểm tra ở trạng thái ổn định xấp xỉ:

```text
50 × (1/10 + 1/5) = 15 yêu cầu kiểm tra/giây
```

Đây là phép ước lượng tải của ví dụ. Khi chưa Ready, readiness có thể được gọi ngoài nhịp chu kỳ thông thường để phát hiện phục hồi sớm hơn. Không nên xem chu kỳ là một lịch thời gian tuyệt đối.

## 3. Chọn mốc khởi động đúng trong Spring Boot

Với ứng dụng web có Actuator và bật hỗ trợ probe, hai địa chỉ thường dùng là:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Có thể bật chúng rõ ràng bằng `management.endpoint.health.probes.enabled=true`. Nếu Actuator dùng cổng quản trị riêng, `management.endpoint.health.probes.add-additional-paths=true` còn đưa `/livez` và `/readyz` lên cổng ứng dụng chính. Điều này giúp phép kiểm tra đi qua hạ tầng HTTP phục vụ ứng dụng. Xem [Spring Boot 3.3 — Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Cần phân biệt hai mốc:

1. **Liveness có thể trả thành công**: ngữ cảnh ứng dụng đã khởi tạo và endpoint có thể được gọi.
2. **Readiness có thể trả thành công**: ứng dụng đã hoàn tất các công việc khởi động cần thiết trước khi nhận lưu lượng.

Trong vòng đời chuẩn, Spring Boot coi ứng dụng sẵn sàng sau khi các `ApplicationRunner` và `CommandLineRunner` được thực hiện. Vì vậy, một runner dài có thể tạo khoảng cách đáng kể giữa hai mốc. Nếu tự đẩy công việc bắt buộc sang luồng nền và để runner kết thúc sớm, cần tự quản lý tín hiệu sẵn sàng; nền tảng không tự biết công việc nền đó còn thiếu. Tham khảo [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

### 3.1. Startup probe dùng liveness bảo vệ đến đâu?

Nếu startup probe gọi `/livez`, nó bảo vệ đến lần đầu `/livez` thành công. Nó **không bảo đảm mọi bước nạp dữ liệu đã xong**. Sau mốc đó, readiness vẫn có thể thất bại và tiếp tục chặn lưu lượng.

Ví dụ tự xây dựng:

```text
Container bắt đầu                  t =   0 s
/livez bắt đầu trả thành công       t =  95 s
Runner hoàn tất; /readyz thành công t = 130 s
```

Startup probe dùng `/livez` có thể kết thúc khoảng giây 95, tùy lịch kiểm tra. Từ đó liveness hoạt động, còn readiness giữ bản sao chưa sẵn sàng đến khoảng giây 130 hoặc lâu hơn tùy thời điểm quan sát.

Nếu runner sau giây 95 làm nghẽn toàn bộ tài nguyên đến mức `/livez` liên tục timeout, startup probe đã kết thúc nên không còn bảo vệ. Cần giải quyết việc chiếm tài nguyên, điều chỉnh phép kiểm tra hoặc chọn một tín hiệu khởi động phù hợp hơn.

### 3.2. Có nên dùng readiness cho startup probe?

Có thể chọn endpoint readiness làm startup probe nếu muốn thời hạn khởi động bao gồm cả khởi tạo nghiệp vụ. Tuy nhiên, khi đó việc chưa sẵn sàng kéo dài sẽ trở thành lý do dừng container.

Trước khi chọn, hãy trả lời: “Khởi động lại bản sao có giúp hoàn thành điều kiện này không?”. Nếu readiness phụ thuộc một cơ sở dữ liệu dùng chung đang ngừng hoạt động, mọi bản sao có thể bị khởi động lại liên tục mà không giải quyết được nguyên nhân.

Một cách thiết kế rõ ràng là dùng tín hiệu startup cho phần khởi tạo cục bộ có thể hoàn tất, readiness cho khả năng nhận lưu lượng, và liveness cho khả năng tiếp tục hoạt động. Không thêm tùy tiện mọi kiểm tra phụ thuộc ngoài vào liveness hoặc dùng endpoint health tổng hợp thay cho tín hiệu đã chọn.

## 4. Tính khoảng thời gian: bắt đầu từ một mô hình có giả định

Ký hiệu:

- `P`: `periodSeconds`.
- `T`: `timeoutSeconds`.
- `F`: `failureThreshold`.
- `t0`: thời điểm bắt đầu lần kiểm tra đầu tiên trong một chuỗi lỗi.
- `d`: thời lượng của lần kiểm tra cuối cùng, từ gần 0 đến khoảng `T`.

Nếu các lần kiểm tra bắt đầu đều cách nhau `P`, không bị trễ lịch, và thời lượng mỗi lần nhỏ hơn chu kỳ, thời điểm phát hiện lỗi trong mô hình là:

```text
t_phát_hiện ≈ t0 + (F - 1) × P + d
```

Đây là suy luận từ lịch mẫu, không phải cam kết thời gian thực của Kubernetes. Tải node, thời gian thực thi probe, lịch kubelet và loại lỗi có thể làm kết quả khác đi.

### 4.1. Cùng cấu hình, lỗi nhanh và timeout cho thời điểm khác nhau

Giả sử `P = 10`, `T = 2`, `F = 3`; lần lỗi đầu tiên bắt đầu tại giây 100:

| Lần kiểm tra | Bắt đầu theo mô hình | Nếu trả 503 ngay | Nếu không phản hồi |
| --- | --- | --- | --- |
| 1 | 100 s | Lỗi gần 100 s | Hết hạn gần 102 s |
| 2 | 110 s | Lỗi gần 110 s | Hết hạn gần 112 s |
| 3 | 120 s | Đạt ngưỡng gần 120 s | Đạt ngưỡng gần 122 s |

Khoảng cách từ đầu lần lỗi thứ nhất đến khi đạt ngưỡng xấp xỉ 20 hoặc 22 giây trong hai tình huống này.

Nếu sự cố xuất hiện ngay sau một lần kiểm tra thành công, còn phải chờ gần một chu kỳ trước khi có mẫu lỗi đầu tiên. Với lỗi liên tục và lịch đều như trên, độ trễ phát hiện từ lúc sự cố xuất hiện có thể xấp xỉ:

```text
Lỗi phản hồi ngay: từ 20 đến 30 giây
Lỗi luôn timeout:  từ 22 đến 32 giây
```

Các khoảng trên thuộc mô hình lý tưởng. Không dùng chúng làm giới hạn cứng để cam kết thời gian phục hồi.

### 4.2. Vì sao thường dùng F × P để ước lượng?

`F × P` là một cách tính nhanh khoảng chịu lỗi danh nghĩa. Kubernetes cũng dùng tích này khi hướng dẫn chọn startup probe cho ứng dụng khởi động chậm. Xem [hướng dẫn bảo vệ container khởi động chậm](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#protect-slow-starting-containers-with-startup-probes).

Tuy nhiên, trong mô hình mẫu bắt đầu tại `t0`, chỉ có `F - 1` khoảng cách giữa `F` lần kiểm tra. Vì vậy:

- Không coi `F × P` là thời điểm chính xác mà container chắc chắn bị dừng.
- Không cộng thêm `T` vào từng chu kỳ thành `F × (P + T)` một cách máy móc.
- Không dùng `F × T` làm tổng thời gian chịu lỗi vì phép tính đó bỏ qua khoảng cách giữa các lần kiểm tra.
- Nếu `T` lớn hơn `P`, mô hình các lần bắt đầu đều nhau có thể không còn phù hợp; phải xem lịch thực tế.

Khi thiết kế, hãy chừa biên an toàn và kiểm chứng trên cụm thật, thay vì đặt thời gian khởi động mong đợi sát một kết quả nhân.

### 4.3. Phát hiện lỗi khác với phục hồi dịch vụ

Sau khi liveness đạt ngưỡng, hệ thống còn có thể mất thời gian dừng ứng dụng, chờ cơ chế giãn nhịp khởi động lại, chạy JVM mới, khởi tạo và đạt readiness.

```text
Thời gian bản sao phục hồi
≈ chờ phát hiện lỗi
+ dừng container
+ chờ khởi động lại
+ khởi động đến mức sẵn sàng
+ thời gian cập nhật định tuyến
```

`terminationGracePeriodSeconds` thuộc phần dừng, không phải phần chờ khởi động ban đầu. Với container tự thoát hoặc bị kết thúc vì hết bộ nhớ, việc xử lý có thể xảy ra trước khi probe kịp đạt ngưỡng.

Công thức trên mô tả một bản sao. Thời gian người dùng bị ảnh hưởng còn phụ thuộc số bản sao khỏe mạnh và năng lực còn lại của dịch vụ.

## 5. Chọn tham số từ số đo và yêu cầu vận hành

### Bước 1 — Đo đúng khoảng thời gian

Đo nhiều lần trong điều kiện gần môi trường triển khai:

- Từ lúc container bắt đầu chạy đến khi endpoint startup được chọn trả thành công.
- Từ lúc container bắt đầu đến khi readiness trả thành công.
- Độ trễ của chính endpoint probe khi tải bình thường và tải cao.

Ghi cả các lần khởi động lạnh, migration, giới hạn CPU, bộ nhớ và tình trạng node. Thời gian lập lịch Pod hoặc kéo image xảy ra trước khi container chạy không thuộc cùng đồng hồ đo startup probe; chúng vẫn ảnh hưởng thời gian triển khai tổng thể.

Dùng phân vị phù hợp và các tình huống chậm đã quan sát, kèm biên an toàn. Một lần chạy nhanh trên máy cá nhân không đủ làm cơ sở. Phân vị cao cũng không bảo đảm bao phủ mọi trường hợp tương lai.

### Bước 2 — Đặt khoảng cho startup

Giả sử nhóm vận hành đo được thời gian đến lần thành công đầu của `/livez` ở phân vị p99 là 95 giây. Nhóm chọn mục tiêu cho phép 120 giây sau khi cộng biên 25 giây.

Một cấu hình thử nghiệm là:

```text
Startup: P = 5 s, T = 2 s, F = 30
Khoảng danh nghĩa: 30 × 5 = 150 s
```

Trong mô hình lỗi nhanh với lần kiểm tra đầu tại giây 0, lần thứ 30 bắt đầu gần giây 145; khoảng này vẫn lớn hơn mục tiêu 120 giây. Việc chừa khoảng rộng hơn giúp tránh dựa vào thời điểm biên. Các con số ở đây phục vụ ví dụ, không phải bộ giá trị mặc định cho mọi ứng dụng.

Nếu số đo 95 giây là thời gian đến readiness nhưng startup probe lại gọi liveness, phép chọn tham số đang dùng sai mốc đo. Phải thống nhất endpoint đo và endpoint kiểm tra.

### Bước 3 — Chọn timeout từ độ trễ endpoint

Giả sử probe thường phản hồi dưới 100 ms và vẫn dưới 700 ms ở phân vị cao trong bài đo tải. Timeout 2 giây có thể là điểm bắt đầu để thử, miễn là mức chờ đó phù hợp yêu cầu phát hiện sự cố.

Nếu endpoint gọi hệ thống ngoài, timeout kết nối/đọc của lời gọi bên trong phải có giới hạn và phù hợp với tổng ngân sách của endpoint. Timeout ở kubelet không bảo đảm công việc phía máy chủ tự dừng tức thì.

Không tăng timeout lên hàng chục giây chỉ để che truy vấn sức khỏe quá nặng. Trước hết cần giảm công việc trong probe và tìm nguyên nhân như thiếu CPU, hàng đợi HTTP, GC hoặc tranh chấp tài nguyên.

### Bước 4 — Chọn liveness theo khả năng tự hồi phục

Giả sử một đợt chậm ngắn vẫn có thể tự hồi phục trong khoảng vài giây. Có thể bắt đầu thử với `P = 10`, `T = 2`, `F = 3`, rồi tiêm lỗi để xác minh:

- Một lần chậm có gây dừng container quá nhạy không?
- Treo kéo dài có được phát hiện trong khoảng chấp nhận được không?
- Khởi động lại có thực sự cải thiện tình trạng không?

Khoảng startup 150 giây không cần biến thành khoảng chịu lỗi liveness 150 giây. Hai giai đoạn có mục tiêu khác nhau.

### Bước 5 — Chọn readiness theo thời gian chịu đựng lưu lượng lỗi

Readiness thường cần loại bản sao khỏi định tuyến sớm hơn quyết định khởi động lại. Ví dụ dùng `P = 5`, `T = 2`, `F = 2`, `successThreshold = 2`.

Trong mô hình lịch đều, hai lỗi liên tiếp được nhận ra sau khoảng một chu kỳ tính từ lần lỗi đầu, cộng thời lượng lần cuối. Hai lần thành công liên tiếp giúp phục hồi ổn định hơn. Nhưng readiness có thể được gọi nhanh hơn khi chưa Ready, nên không khẳng định phục hồi luôn mất đúng 10 giây.

Trong khoảng chờ đạt ngưỡng lỗi và truyền trạng thái định tuyến, bản sao vẫn có thể nhận yêu cầu. Cần tính mức chịu đựng đó, đặc biệt với một bản sao duy nhất.

## 6. Ghép cấu hình Spring Boot và Kubernetes

Ví dụ sau dành cho ứng dụng Spring Boot 3.3 có `spring-boot-starter-actuator` và một web starter. Đây là các đoạn cấu hình tích hợp vào ứng dụng/Deployment hiện có, không phải một dự án hoặc manifest hoàn chỉnh.

### 6.1. application.yml

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
```

Ví dụ giả định không đặt context path hoặc base path bổ sung. Các probe bên dưới gọi cổng 8080 với `/livez` và `/readyz`. Các khóa cấu hình được liệt kê trong [thuộc tính Actuator của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

Nếu ứng dụng có quy tắc Spring Security tùy chỉnh, phải cho kubelet truy cập các địa chỉ probe đã chọn. Lỗi 401/403 do cấu hình truy cập không thể sửa bằng cách tăng ngưỡng lỗi. Không mở toàn bộ endpoint quản trị để giải quyết việc này.

### 6.2. Đoạn cấu hình của một container

Thêm các trường sau vào phần tử container tương ứng dưới `spec.template.spec.containers` của Deployment:

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /livez
    port: http
  initialDelaySeconds: 0
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 30
  successThreshold: 1

livenessProbe:
  httpGet:
    path: /livez
    port: http
  initialDelaySeconds: 0
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 1

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  initialDelaySeconds: 0
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
  successThreshold: 2
```

Ý nghĩa của bộ cấu hình:

- Trước khi `/livez` thành công, startup probe có khoảng danh nghĩa 150 giây; hai probe còn lại chưa chạy.
- Sau lần startup thành công, liveness dùng khoảng chịu lỗi ngắn hơn để phát hiện lỗi kéo dài.
- Readiness có thể tiếp tục thất bại trong khi runner còn chạy; việc này không tự gây khởi động lại.
- Không có một khoảng trì hoãn cố định dài sau mỗi lần khởi động nhanh chỉ để dự phòng trường hợp chậm.

Nếu chưa dùng startup probe, có thể phối hợp `initialDelaySeconds` của liveness với ngưỡng lỗi để tránh dừng sớm. Cách đó vẫn hợp lệ nhưng phải cân bằng khoảng chờ cố định với tốc độ phát hiện. Khi đã dùng startup probe, tránh giữ một initial delay rất dài ở liveness mà không có lý do rõ ràng. Cần đối chiếu cách áp dụng delay với phiên bản Kubernetes của cụm.

Chính sách thời gian triển khai cũng phải khớp: một deadline theo dõi rollout ngắn hơn thời gian cần để bản sao đạt readiness có thể báo triển khai không tiến triển, dù startup probe chưa đạt ngưỡng lỗi. Deadline triển khai và ngưỡng probe là hai cơ chế riêng; xem [Kubernetes Deployment — Progress Deadline Seconds](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#progress-deadline-seconds).

## 7. Kiểm chứng theo từng tình huống

Chạy trên môi trường thử nghiệm với image ứng dụng đã cấu hình, không sửa trực tiếp môi trường đang phục vụ người dùng.

Các lệnh dưới đây giả định Deployment tên `actuator-demo` và container tên `app` trong namespace hiện tại:

```bash
kubectl get pods -l app=actuator-demo -w
kubectl describe pods -l app=actuator-demo
kubectl logs deployment/actuator-demo -c app --timestamps
kubectl get endpointslices -l kubernetes.io/service-name=actuator-demo -o yaml
```

Selector `app=actuator-demo` phải khớp nhãn của Pod; tên Service dùng trong lệnh cuối phải đúng với môi trường thử nghiệm. Các lệnh trả thông tin thay đổi theo cụm; không có stdout cố định để so khớp nguyên văn.

| Tình huống kiểm thử | Điều cần quan sát | Cách hiểu |
| --- | --- | --- |
| Khởi động nhanh | Startup thành công sớm, readiness đạt, số lần restart không tăng do probe | Không phải chờ hết khoảng startup danh nghĩa |
| Khởi động chậm nhưng trong khoảng cho phép | Có lỗi startup tạm thời, sau đó thành công; không bị dừng trước mốc khởi động | Khoảng bảo vệ phù hợp với lần chạy này |
| Startup không bao giờ thành công | Probe đạt ngưỡng, xuất hiện sự kiện dừng/chạy lại | Có giới hạn cho khởi động bị kẹt |
| Runner dài nhưng liveness vẫn tốt | Startup kết thúc, Pod vẫn chưa Ready đến khi runner xong | Liveness và readiness thể hiện hai mốc khác nhau |
| Readiness thất bại sau khi đã phục vụ | Ready chuyển false, thay đổi trạng thái endpoint; restart không tăng chỉ vì readiness | Điều khiển lưu lượng hoạt động riêng |
| Liveness thất bại liên tục sau startup | Đạt ngưỡng rồi container được dừng/chạy lại | Cơ chế phục hồi tiến trình hoạt động |
| Lỗi một lần rồi phục hồi | Chuỗi lỗi bị ngắt, không đạt ngưỡng ba lỗi liveness | Không đếm dồn các lỗi rời rạc |

Đối chiếu timestamp của log ứng dụng, sự kiện kubelet, trạng thái Ready và `restartCount`. Sự kiện có thể được gộp hoặc hiển thị thời gian tương đối; không dùng riêng màn hình `describe` để khẳng định một mốc đến từng mili giây.

Có thể dùng port-forward để kiểm tra thủ công đường dẫn và mã HTTP:

```bash
kubectl port-forward deployment/actuator-demo 8080:8080
```

Trong một cửa sổ khác:

```bash
curl -i --max-time 2 http://localhost:8080/livez
curl -i --max-time 2 http://localhost:8080/readyz
```

Port-forward giúp kiểm tra endpoint nhưng không tái tạo đầy đủ đường mạng từ kubelet đến Pod. Khi kubelet vẫn thất bại, tiếp tục kiểm tra cổng, địa chỉ lắng nghe, đường dẫn, cấu hình mạng và quyền truy cập thực tế.

## 8. Những cách chỉnh dễ làm sai mục tiêu

| Cách chỉnh | Vấn đề | Hướng xử lý phù hợp |
| --- | --- | --- |
| Chỉ tăng timeout để chịu startup 120 giây | Mỗi lần kiểm tra có thể chờ quá lâu, làm chậm phát hiện lỗi | Dùng startup probe và chọn timeout theo độ trễ endpoint |
| Tăng ngưỡng liveness rất cao cho mọi giai đoạn | Lỗi sau khởi động được nhận ra chậm | Dành khoảng dài cho startup, đo riêng khoảng liveness |
| Trông chờ readiness bảo vệ khỏi liveness | Liveness vẫn có thể đạt ngưỡng khi readiness đang lỗi | Dùng startup probe hoặc thiết kế delay liveness phù hợp |
| Startup gọi liveness nhưng đo thời gian đến readiness | Hai mốc không tương đương | Đo đúng tín hiệu startup đã chọn |
| Đặt ngưỡng đúng sát thời gian khởi động trung bình | Khởi động lạnh hoặc thiếu CPU dễ vượt ngưỡng | Đo phân phối thời gian và chừa biên |
| Dùng health tổng hợp chứa DB cho liveness | Sự cố DB có thể gây dừng đồng loạt bản sao | Chọn chỉ báo đúng khả năng tự phục hồi |
| Coi mọi HTTP 503 là tiến trình phải chạy lại | 503 của readiness có thể chỉ biểu thị chưa nhận lưu lượng | Phân biệt endpoint, probe và hành động của nó |
| Tăng tần suất trong khi probe quá nặng | Tăng tải và làm tình trạng chậm nghiêm trọng hơn | Giảm chi phí phép kiểm tra trước khi tăng tần suất |

## 9. Bài tập vận dụng

Một ứng dụng có số đo như sau:

- Liveness HTTP thành công chậm nhất trong đợt thử hiện tại ở giây 80.
- Một runner hoàn thành ở giây 115.
- Nhóm muốn dành thêm ít nhất 20 giây cho mốc startup được chọn.
- Probe hoạt động bình thường dưới 300 ms và thỉnh thoảng gần 900 ms khi tải cao.

Hãy giải thích lựa chọn `startupProbe`, `livenessProbe`, `readinessProbe` và dự đoán tác động nếu runner bị kẹt nhưng `/livez` vẫn thành công.

Một hướng giải:

1. Nếu chọn `/livez` làm startup, mục tiêu đo là 80 + 20 = 100 giây. Có thể thử `P = 5`, `F = 25`, khoảng danh nghĩa 125 giây, rồi xác minh thực tế; đây không phải bộ tham số duy nhất.
2. Có thể thử timeout 2 giây dựa trên số đo độ trễ, sau đó đo lại khi thiếu CPU và tải cao. Không suy ra timeout 115 giây từ thời gian runner.
3. Chọn liveness cho khoảng phát hiện lỗi sau startup mà dịch vụ chấp nhận được, chẳng hạn bộ 10/2/3 đã phân tích, rồi kiểm chứng bằng lỗi kéo dài.
4. Readiness ngăn đưa bản sao vào phục vụ trước khi runner xong. Khi runner kẹt mà liveness vẫn thành công, Pod có thể tiếp tục chưa Ready mà không bị probe yêu cầu khởi động lại.
5. Nếu yêu cầu vận hành là phải giới hạn cả thời gian runner, thiết kế thêm giới hạn công việc khởi tạo hoặc tín hiệu startup phản ánh việc hoàn tất đó; đánh giá rõ khả năng khởi động lại có giải quyết nguyên nhân hay không.

Khi giải thích một cấu hình, hãy luôn nêu được: **đang kiểm tra tín hiệu nào, cho phép chờ bao lâu, thất bại sẽ đổi định tuyến hay dừng container, và số đo nào chứng minh lựa chọn đó phù hợp**.
