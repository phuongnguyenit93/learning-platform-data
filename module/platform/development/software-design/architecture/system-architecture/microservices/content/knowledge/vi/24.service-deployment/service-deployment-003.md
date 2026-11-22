# Rolling Update, Blue-Green và Canary Deployment

## 1. Mục tiêu

Một dịch vụ đang phục vụ người dùng cần được nâng cấp thường xuyên: sửa lỗi, vá bảo mật, thay đổi API, thêm tính năng hoặc tối ưu hiệu năng. Nếu dừng toàn bộ dịch vụ trước khi triển khai, người dùng sẽ gặp lỗi hoặc gián đoạn. Nếu đẩy phiên bản mới tới toàn bộ traffic ngay lập tức, một lỗi nhỏ trong bản phát hành có thể ảnh hưởng toàn hệ thống.

**Deployment strategy** là cách thay phiên bản đang chạy, điều phối instance và luồng request, kiểm chứng phiên bản mới và phản ứng khi phát hiện sự cố.

Bài này tập trung vào ba cách triển khai quan trọng trong kiến trúc Microservices:

1. **Rolling update:** thay các instance cũ bằng instance mới từng phần.
2. **Blue-green deployment:** duy trì hai môi trường/phân nhóm hoàn chỉnh, chuyển traffic từ nhóm đang hoạt động sang nhóm mới.
3. **Canary deployment:** đưa một tỷ lệ traffic hoặc một nhóm người dùng nhỏ sang phiên bản mới, giám sát rồi mở rộng dần.

Sau khi đọc, người học cần hiểu được cách hoạt động, sự khác nhau về rủi ro, tài nguyên, yêu cầu hạ tầng, giám sát và rollback; biết lựa chọn chiến lược cho từng dịch vụ và xây dựng một quy trình triển khai an toàn.

## 2. Các khái niệm nền tảng

### 2.1. Release và deployment

- **Build artifact:** file/binary/container image được tạo từ mã nguồn, thường có version, build ID, Git commit và image digest.
- **Release:** tập thay đổi phần mềm được công bố để có thể triển khai.
- **Deployment:** hành động đưa artifact vào một môi trường cụ thể, thay đổi workload và traffic đang phục vụ.
- **Rollout:** quá trình đưa version mới tới nhiều instance hoặc nhóm người dùng theo các giai đoạn.
- **Rollback:** chuyển hệ thống về artifact/cấu hình hoặc luồng traffic trước đó theo một phương án đã chuẩn bị.
- **Roll forward:** phát hành bản sửa mới thay vì đưa về bản cũ, phù hợp khi dữ liệu/schema không thể quay ngược.
- **Traffic shifting:** điều chỉnh request đi tới phiên bản cũ và mới theo một quy tắc.
- **Readiness:** khả năng của instance xử lý request mới ở thời điểm hiện tại.
- **Liveness:** tín hiệu cho biết tiến trình còn sống/không thể tự phục hồi và có thể cần restart.
- **Drain:** ngừng nhận request mới, cho các request/connection hiện tại kết thúc có kiểm soát.

Một version có thể được triển khai nhiều lần tới các môi trường và vùng khác nhau. Deployment thành công theo CI/CD không tự động đảm bảo rằng người dùng đang nhận hành vi đúng; kết quả runtime mới là điều cần quan sát.

### 2.2. Không đồng nhất "zero downtime" với "zero risk"

Triển khai không gián đoạn đòi hỏi nhiều điều kiện: đủ replica, load balancer chuyển hướng đúng, readiness chính xác, xử lý shutdown/long-lived connection và hợp đồng API/database có tương thích. Ngay cả khi request không bị đứt, phiên bản mới vẫn có thể tính sai dữ liệu hoặc tạo side effect không mong muốn.

**Zero downtime** là mục tiêu vận hành; **safe deployment** còn cần correctness, khả năng quan sát và rollback phù hợp.

### 2.3. Định danh phiên bản nhất quán

Nên gắn định danh phiên bản vào:

- Container image digest và build metadata.
- Kubernetes Deployment/Pod labels hoặc annotations.
- OpenTelemetry service.version trên spans.
- Structured logs và metrics ở mức cardinality kiểm soát.
- Deployment events và dashboard annotations.
- Feature flag, config revision và migration version nếu có.

Khi hai phiên bản chạy đồng thời, các dữ liệu này giúp xác định request lỗi đã thật sự đi qua instance nào.

## 3. So sánh tổng quan

| Tiêu chí | Rolling update | Blue-green | Canary |
|---|---|---|---|
| Cách thay bản | Thay dần instance | Giữ hai nhóm rồi chuyển traffic | Chuyển traffic từ ít tới nhiều |
| Bản cũ/mới cùng tồn tại | Có, trong rollout | Có, thường hai môi trường | Có, trong các giai đoạn |
| Traffic shift chính | Theo số pod/endpoint được thay | Chuyển selector/router/LB | Theo tỷ lệ, cohort hoặc rule |
| Tài nguyên thêm | Thường vừa phải | Có thể gần gấp đôi cho môi trường green | Tùy số replica và mức phân tích |
| Kiểm chứng với traffic thật | Trong rollout, nhưng khó tách chính xác | Có thể smoke test trước switch | Rất phù hợp cho thí nghiệm tăng dần |
| Rollback | Đưa image cũ trở lại, rolling ngược | Chuyển traffic về blue nếu còn khả dụng | Giảm tỷ lệ/đưa traffic về stable |
| Rủi ro phổ biến | Lỗi lan dần khi thay pod; mixed versions | Chuyển toàn bộ có blast radius lớn | Mẫu nhỏ nhiễu; routing và đo lường phức tạp |
| Điều kiện nền tảng | Scheduler, health checks, capacity | Hai nhóm đủ độc lập, switch chính xác | Controller/routing hỗ trợ tỷ lệ hoặc cohort |
| Trường hợp phù hợp | Thay đổi rủi ro thấp, dịch vụ stateless | Cần chuyển nhanh và rollback traffic | Thay đổi có rủi ro, cần kiểm chứng production |

Bảng phản ánh đặc điểm thông dụng; thực tế có thể kết hợp chiến lược, ví dụ dùng rolling update để thay replica trong chính nhóm canary, hoặc blue-green kết hợp canary traffic shift.

## 4. Rolling Update là gì?

**Rolling update** thay instance phiên bản cũ bằng instance mới theo từng đợt, trong khi dịch vụ vẫn phục vụ request.

Ví dụ đang có 6 replica A (bản v1) và muốn chuyển sang v2:

~~~text
Bước 0: A A A A A A
Bước 1: A A A A A B
Bước 2: A A A A B B
Bước 3: A A A B B B
Bước 4: A A B B B B
Bước 5: A B B B B B
Bước 6: B B B B B B
~~~

Trong quá trình này, load balancer có thể đưa các request khác nhau tới A và B. Nếu service là stateless và hợp đồng backward-compatible, người dùng thường không cảm nhận ngắt quãng. Nếu v2 đổi schema hoặc API theo cách không tương thích với v1, sự cùng tồn tại tạo rủi ro.

### 4.1. Cơ chế trong Kubernetes Deployment

Kubernetes Deployment hỗ trợ RollingUpdate. Hai tham số quan trọng:

- **maxSurge:** số pod được phép tạo thêm so với số replicas mong muốn trong quá trình rollout.
- **maxUnavailable:** số pod có thể không khả dụng so với số replicas mong muốn trong quá trình rollout.

Ví dụ 6 replica, maxSurge=2 và maxUnavailable=1: controller có thể tạo thêm tối đa 2 pod (thông thường không vượt quá 8 pod theo cấu hình ReplicaSet đang quản lý) và cho phép số available pod giảm tới 5 trong quá trình thay. Giá trị thực theo controller, readiness và trạng thái cluster; không suy rằng mỗi đợt luôn đúng 2 pod.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 6
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 1
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
        version: "2.1.0"
    spec:
      containers:
        - name: catalog-api
          image: registry.example.com/catalog-api:2.1.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
~~~

Manifest mang tính minh họa. Production nên pin image digest bất biến, cấu hình resources, security, startupProbe nếu khởi động lâu, timeout/probe thresholds phù hợp và quy trình shutdown. Tham số đúng phụ thuộc capacity và SLO của service.

### 4.2. maxSurge và maxUnavailable là bài toán capacity

Một Deployment với 10 replica mà maxUnavailable=3 có thể tạm mất 30% capacity nếu các pod mới chưa ready. Nếu hệ thống đang chạy gần saturation, việc mất capacity sẽ làm latency tăng hoặc phát sinh lỗi.

Cần đặt các tham số theo:

- Peak RPS và concurrency.
- Số request tối đa mỗi pod xử lý an toàn.
- CPU/memory requests và giới hạn node capacity.
- Startup/warm-up time.
- Số replica còn có thể nhận request khi pod bị drain.
- PDB, autoscaling, quota và sự sẵn sàng của cluster.

maxSurge lớn không có nghĩa capacity thực sự đủ: scheduler có thể không đặt được pod nếu thiếu CPU/memory/quota, hoặc pod mới chưa đủ kết nối tới dependency.

### 4.3. Readiness kiểm soát thời điểm nhận traffic

Readiness nên trả thành công khi service đã có khả năng nhận request với hợp đồng dự kiến. Ví dụ ứng dụng đã khởi động HTTP server nhưng chưa load config cần thiết, chưa tạo kết nối tối thiểu hoặc chưa warm cache quan trọng; nếu readiness trả thành công quá sớm, traffic sẽ tới instance chưa chuẩn bị xong.

Liveness dùng để quyết định restart tiến trình bị lỗi, không nên phụ thuộc mù vào mọi external dependency. Nếu một database chung có sự cố và tất cả pod cùng fail liveness, hệ thống có thể rơi vào restart storm. Readiness và liveness có mục tiêu khác nhau.

### 4.4. Drain và graceful shutdown

Khi thay pod, cần:

1. Dừng nhận request mới (readiness false hoặc rút endpoint khỏi router).
2. Cho load balancer/sidecar đủ thời gian cập nhật danh sách endpoint.
3. Hoàn tất hoặc hủy có kiểm soát các request in-flight.
4. Đóng consumer, scheduler, connection và tài nguyên.
5. Không làm mất job/message chưa được ack.
6. Chỉ dừng tiến trình khi trong thời gian grace period phù hợp.

Với gRPC streaming, WebSocket và long polling, cần chiến lược chuyển kết nối; không thể giả định tất cả kết thúc trong vài giây.

### 4.5. Rolling rollback

Nếu rollout v2 có lỗi, có thể dừng progression và trở về revision cũ. Trong Kubernetes, các lệnh như sau thường dùng để quan sát và rollback Deployment:

~~~bash
kubectl rollout status deployment/catalog-api
kubectl rollout history deployment/catalog-api
kubectl rollout undo deployment/catalog-api
~~~

Những lệnh này là ví dụ cho môi trường Kubernetes có đúng resource và quyền truy cập. Lịch sử revision phụ thuộc cấu hình và những revision còn lưu. Quá trình undo cũng cần thay pod, kiểm tra readiness và có thể mất thời gian. Nếu schema/dữ liệu đã bị thay đổi không tương thích, undo image không tự khôi phục hệ thống.

## 5. Blue-Green Deployment là gì?

**Blue-green** duy trì hai nhóm phục vụ độc lập ở mức đủ để vận hành:

- **Blue:** version đang nhận traffic production.
- **Green:** version mới đã được deploy và chuẩn bị để nhận traffic.

Sau kiểm tra, router/load balancer/service selector chuyển traffic từ Blue sang Green. Có thể giữ Blue trong khoảng quan sát để chuyển lại nhanh nếu Green có vấn đề.

~~~text
Trước switch:
Users --> Load Balancer --> BLUE (v1) [active]
                       \-> GREEN (v2) [standby/test]

Sau switch:
Users --> Load Balancer --> GREEN (v2) [active]
                       \-> BLUE (v1) [standby/rollback]
~~~

Blue/green chỉ là nhãn tương đối. Khi một release mới xuất hiện, vai trò có thể đảo lại; không nên xây quy trình cố định "Blue luôn cũ, Green luôn mới".

### 5.1. Cách chuyển traffic

Có nhiều cách:

- Đổi backend của load balancer.
- Đổi selector của một Kubernetes Service nếu các pod có label đúng.
- Đổi rule của API Gateway, ingress hoặc service mesh.
- Đổi DNS, nhưng cần chú ý DNS caching/TTL và kết nối lâu; DNS không thường đảm bảo switch đồng loạt tức thời.
- Dùng weighted routing để chuyển dần, khi đó blue-green trở thành biến thể kết hợp canary.

Ví dụ phân nhóm pod bằng labels và Service selector:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
spec:
  selector:
    app: catalog-api
    color: blue
  ports:
    - port: 80
      targetPort: 8080
~~~

Khi Green đã ready, hệ thống điều phối có thể cập nhật selector color sang green. Đây là ví dụ cơ chế, không phải quy trình đủ cho production: cần kiểm tra bộ điều khiển hiện tại, traffic từ ingress, kết nối đang tồn tại và việc cập nhật endpoint đã hoàn tất.

### 5.2. Kiểm thử Green trước khi switch

Có thể chạy:

- Smoke test HTTP và contract.
- Readiness/startup checks.
- Kết nối database/cache/broker.
- Kiểm thử cấu hình môi trường.
- Synthetic transactions có dữ liệu an toàn.
- Security checks cần thiết.
- Test nghiệp vụ với sandbox/mock hợp lệ.

**Lưu ý side effects:** nếu Green dùng chung production database và broker, một lệnh smoke test có thể tạo đơn, gửi mail hoặc thu tiền thật. Cần dùng test account, sandbox provider, dữ liệu được cô lập hoặc thao tác an toàn có thể dọn đúng cách. Không gửi request thử có nguy cơ gây giao dịch thật không thể hoàn tác.

### 5.3. Rollback bằng switch

Lợi thế lớn của blue-green là có thể chuyển traffic ngược về Blue khi Blue còn khỏe và tương thích dữ liệu. Tuy nhiên vẫn có giới hạn:

- Cache và session có thể không tương thích.
- Green có thể đã ghi dữ liệu mà Blue không đọc được.
- Persistent connection còn giữ kết nối Green.
- Queue consumers Green có thể tiếp tục xử lý message sau khi HTTP traffic đã được chuyển.
- Các bản ghi hoặc side effects tạo bởi Green không tự biến mất.
- Hạ tầng Blue có thể đã bị scale down quá sớm.

Blue-green rollback nhanh ở **lớp routing**, nhưng không có nghĩa rollback được tất cả side effects.

### 5.4. Chi phí và điểm cần bảo vệ

Nếu cả hai môi trường cần đủ replicas, tài nguyên compute/memory có thể tăng mạnh. Với stateful services, database đôi khi vẫn dùng chung; tạo bản sao database độc lập có thể tăng độ phức tạp và rủi ro nhất quán dữ liệu. Phải xác định thành phần nào được duplicate, thành phần nào shared.

Môi trường Green cần có routing riêng để test trước switch và phải được bảo vệ khỏi traffic không mong muốn. Không để cả Blue và Green cùng chạy scheduler hoặc consumer có side effects nếu chỉ một nhóm được phép giữ quyền xử lý.

## 6. Canary Deployment là gì?

**Canary** là chiến lược gửi một phần nhỏ traffic hoặc một nhóm user/tenant có kiểm soát tới version mới. Quan sát kết quả; nếu ổn thì tăng dần, nếu không thì giảm hoặc dừng traffic.

~~~text
Stage 0: v1 = 100%, v2 =   0%
Stage 1: v1 =  99%, v2 =   1%
Stage 2: v1 =  95%, v2 =   5%
Stage 3: v1 =  75%, v2 =  25%
Stage 4: v1 =  50%, v2 =  50%
Stage 5: v1 =   0%, v2 = 100%
~~~

Điểm khác rolling update: **canary tập trung vào kiểm soát nhóm traffic và quyết định dựa trên dữ liệu**, không chỉ số pod đã thay. Nếu chỉ có 1 pod mới trong tổng 10 pod mà load balancer phân phối đều, phiên bản mới có thể nhận khoảng 10% request, nhưng không chắc đúng 10% traffic có cùng tính chất; mức thực tế còn phụ thuộc connection/session và routing.

### 6.1. Các cách chọn canary cohort

- **Random weighted traffic:** chuyển 1%, 5% hoặc 25% request theo trọng số.
- **Sticky cohort:** user/tenant/session ổn định ở cùng version trong một khoảng.
- **Internal users:** nhân viên hoặc nhóm kiểm thử được chỉ định.
- **Tenant/region:** rollout tới một nhóm khách hàng, vùng hay cluster trước.
- **Feature exposure:** cùng binary nhưng bật đường code mới cho một phần người dùng.

Canary theo tenant hoặc region có thể tạo sai lệch mẫu vì hành vi user và tải khác stable. Khi so sánh phải ghi lại phương pháp phân nhóm; không mặc định canary và stable tương đương thống kê.

### 6.2. Weighted routing

Trong một số kiến trúc, ingress/service mesh/API Gateway có thể điều phối trọng số:

~~~text
            +----> Stable v1 (95%)
Client -> Router
            +----> Canary v2 (5%)
~~~

Yêu cầu:

- Định tuyến có thể kiểm soát và quan sát được.
- Bản mới có đủ replica/capacity cho traffic thực.
- Có metric request volume theo version.
- Có thể chuyển traffic về stable nhanh.
- Cơ chế sticky session nếu yêu cầu state compatibility.
- Logic routing không dựa vào thông tin do client tự khai mà chưa xác thực.

Không đồng nhất "5% pod" với "5% traffic": nếu pod có capacity khác nhau, session affinity hoặc request duration khác nhau, tỷ lệ thực có thể lệch đáng kể.

### 6.3. Các bước rollout

Một quy trình ví dụ:

1. Deploy canary v2 ở trạng thái không nhận hoặc nhận rất ít traffic.
2. Chạy readiness/smoke tests.
3. Chuyển 1% traffic, ghi mốc và bắt đầu cửa sổ phân tích.
4. Nếu đủ mẫu và guardrails ổn, chuyển 5%.
5. So sánh cùng route/cohort và tăng 25%.
6. Quan sát peak load, latency, retry, business metrics.
7. Tăng 50% rồi 100% theo ngân sách rủi ro.
8. Theo dõi sau hoàn tất và chỉ loại bỏ stable sau khi rollback window phù hợp.

Các tỷ lệ và thời gian dừng là ví dụ, không phải ngưỡng mặc định cho mọi hệ thống. Một service có 50 request/ngày cần cách lấy mẫu rất khác service có 50.000 request/phút.

### 6.4. Controller triển khai nâng cao

Các giải pháp progressive delivery như Argo Rollouts, Flagger hoặc khả năng tương tự của nền tảng có thể kết hợp traffic shifting, analysis, metric queries, pause/abort và rollback. Quy tắc cấu hình cụ thể phụ thuộc controller, ingress/service mesh và phiên bản đang dùng.

Ví dụ ý tưởng các bước:

~~~yaml
strategy:
  canary:
    steps:
      - setWeight: 5
      - pause:
          duration: 5m
      - setWeight: 25
      - pause:
          duration: 10m
      - setWeight: 50
      - pause: {}
      - setWeight: 100
~~~

Đoạn YAML là **mảnh cấu hình ý tưởng**, chưa phải manifest Kubernetes đầy đủ và không thể áp trực tiếp nếu cluster chưa cài/đấu nối controller phù hợp. Pause không tự bảo đảm hệ thống an toàn; cần các phân tích SLI và quy tắc ra quyết định.

## 7. Khi nào chọn chiến lược nào?

### 7.1. Dịch vụ stateless, thay đổi tương thích

Ví dụ API Catalog với 6 replica, không thay đổi schema và có smoke test tốt. **Rolling update** thường là lựa chọn gọn, tiết kiệm tài nguyên, dễ tích hợp với scheduler.

### 7.2. Cần khả năng chuyển traffic nhanh

Ví dụ một ứng dụng web với nhiều service đóng gói cùng một môi trường và có đủ tài nguyên duy trì hai bản. **Blue-green** thuận tiện nếu routing switch và kiểm thử Green được chuẩn hóa.

### 7.3. Thay đổi nghiệp vụ nhạy cảm

Ví dụ thay thuật toán đề xuất, đường thanh toán hoặc cách tính cước. **Canary** giúp giới hạn phạm vi tác động ban đầu, đo cả business correctness và tăng traffic có kiểm soát.

### 7.4. Dịch vụ có state hoặc kết nối dài

Không có chiến lược nào tự giải quyết tương thích state, WebSocket, gRPC streaming, database migration hoặc message processing. Phải bổ sung phiên bản contract, session migration, graceful shutdown và khả năng resume.

### 7.5. Lựa chọn không loại trừ nhau

Có thể dùng:

- Rolling update **bên trong** nhóm Green trước khi switch.
- Blue-green hai môi trường và weighted routing để canary từ Blue sang Green.
- Kubernetes rolling update cho các pod của bản canary.
- Feature flag để bật một tính năng sau khi deploy mã nguồn bằng rolling.
- Canary theo region cho thay đổi infrastructure, rồi rolling theo từng cluster.

Lựa chọn nên dựa trên blast radius, mức độ rủi ro, SLO, traffic, chi phí tài nguyên, tốc độ rollback và khả năng đo lường.

## 8. Readiness, liveness và startup probes

Trong container orchestration, health checks ảnh hưởng trực tiếp đến mức độ an toàn của rollout.

**Readiness probe:** quyết định pod có nên được đưa vào danh sách endpoint nhận request hay không. Nếu chưa ready, request mới không nên được gửi tới nó.

**Liveness probe:** nhận diện process bị kẹt nghiêm trọng và cần khởi động lại. Không nên đặt liveness phụ thuộc vào mọi dịch vụ ngoài để tránh vòng lặp restart hàng loạt khi dependency chung lỗi.

**Startup probe:** cho ứng dụng khởi động dài thời gian mà không bị liveness giết sớm. Sau khi startup probe thành công, liveness/readiness tiếp tục đánh giá.

Ví dụ:

~~~yaml
containers:
  - name: orders
    image: registry.example.com/orders:3.2.0
    ports:
      - containerPort: 8080
    startupProbe:
      httpGet:
        path: /startupz
        port: 8080
      periodSeconds: 5
      failureThreshold: 24
    readinessProbe:
      httpGet:
        path: /readyz
        port: 8080
      periodSeconds: 5
      failureThreshold: 3
    livenessProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 10
      failureThreshold: 3
~~~

Cấu hình thời gian cần phản ánh startup distribution thực tế. Nếu readiness phụ thuộc cache warm-up hoặc nguồn cấu hình quan trọng, hãy định nghĩa mức sẵn sàng đúng; tránh làm tất cả pod NotReady khi một optional dependency tạm hỏng nếu service vẫn có thể phục vụ an toàn ở chế độ suy giảm.

## 9. Graceful shutdown và in-flight requests

Một pod vừa bị rút khỏi endpoint vẫn có thể xử lý request cũ, hoặc router chưa đồng bộ việc thay endpoint. Nếu container thoát tức thì, request đang chạy có thể lỗi 502/503.

Mô hình mong muốn:

~~~text
Controller bắt đầu terminate
  -> pod/người quản lý traffic ngừng route request mới
  -> connection/request cũ hoàn tất hoặc bị hủy có chủ đích
  -> consumer ngừng nhận job mới, ack/nack đúng cách
  -> ứng dụng flush dữ liệu an toàn
  -> process kết thúc trước grace period
~~~

Cần kiểm tra:

- HTTP keep-alive/HTTP2/gRPC connections.
- WebSocket/streaming sessions dài.
- Batch jobs đang xử lý và message acknowledgement.
- External side effects đã commit hay chưa.
- Retry của client khi request đứt giữa chừng.
- Các hook shutdown của framework.
- terminationGracePeriodSeconds và preStop hooks khi phù hợp.

Đặt sleep cố định trước khi thoát không đủ giải quyết mọi race condition. Sử dụng readiness/draining, hooks và thời gian thực phù hợp, rồi kiểm thử với traffic tải cao.

## 10. Tính toán capacity trong rollout

Một ví dụ đơn giản: dịch vụ có 8 pod, mỗi pod xử lý an toàn 100 request/giây, tổng capacity danh nghĩa 800 RPS. Traffic bình thường 600 RPS.

Nếu rolling update tạm giảm còn 6 pod ready, capacity danh nghĩa còn 600 RPS, bằng đúng tải đang nhận, rất ít headroom cho burst. Nếu có pod bị cold start hoặc request duration tăng, tail latency dễ xấu đi.

Với canary 10% của 600 RPS, bản mới dự kiến nhận khoảng 60 RPS nếu weighted routing ổn định. Một pod canary có capacity 100 RPS có vẻ đủ trong ví dụ tĩnh, nhưng thực tế còn ảnh hưởng traffic skew, retry, connection reuse, long-tail request và CPU/memory overhead.

Với blue-green hai bộ đủ capacity, chi phí có thể gần gấp đôi trong cửa sổ chuyển đổi. Không nhất thiết phải giữ cả hai ở full capacity lâu dài; có thể scale Green trước switch và scale Blue sau khi hết rollback window, nhưng phải tính thời gian scale up nếu cần chuyển lại.

Các phép tính này là **capacity planning minh họa**, không phải cam kết throughput. Cần dùng load test và metrics thực tế để ước lượng.

## 11. Tương thích giữa các version đang cùng chạy

Rolling và canary đều tạo ra giai đoạn mixed-version. Blue-green thường cũng cần backward compatibility trong lúc chuyển traffic hoặc khi hai môi trường dùng chung dữ liệu.

### 11.1. Hợp đồng HTTP/gRPC

Thay đổi API an toàn thường theo hướng bổ sung có kiểm soát:

- Thêm field optional và thiết lập default phù hợp.
- Giữ endpoint/mã lỗi quan trọng ổn định trong thời gian chuyển tiếp.
- Consumer không phụ thuộc vào thứ tự field nếu protocol không bảo đảm.
- Có contract tests giữa version gọi và nhận.
- Chỉ xóa/đổi nghĩa field sau khi tất cả consumer đã nâng cấp.

Một consumer v1 có thể gọi provider v2, đồng thời provider v1 vẫn được gọi bởi consumer v2. Thiết kế compat phải xét cả hai chiều cần hỗ trợ.

### 11.2. Database schema

Một thay đổi phá vỡ schema, như xóa cột ngay khi ứng dụng mới được deploy, có thể làm phiên bản cũ lỗi trong rollout hoặc khiến rollback thất bại.

Mô hình **expand-and-contract**:

1. Thêm schema mới tương thích với ứng dụng cũ (expand).
2. Deploy mã biết ghi/đọc cả biểu diễn cũ và mới khi cần.
3. Backfill dữ liệu theo lô, kiểm tra tính đúng.
4. Chuyển traffic/feature flag sang code path mới.
5. Xác nhận không còn consumer cần schema cũ.
6. Loại bỏ schema cũ ở một lần triển khai riêng (contract).

Cần đánh giá online migration, lock, transaction và dữ liệu đã thay đổi. Rollback ứng dụng **không tự đảo ngược** dữ liệu/schema.

### 11.3. Message/event schema

Producer v2 có thể phát event mà consumer v1 chưa biết đọc. Với event-driven systems:

- Dùng schema version và quy tắc tương thích.
- Thêm field optional hoặc default phù hợp.
- Kiểm thử producer/consumer chéo version.
- Cân nhắc schema registry và contract testing.
- Đảm bảo consumer idempotent khi broker redeliver.
- Không đưa cả stable và canary cùng xử lý một job theo cách gây side effect trùng ngoài ý muốn.

### 11.4. Session và cache compatibility

Một server mới có thể thay format session hoặc cache key, khiến người dùng chuyển pod bị đăng xuất hoặc nhận dữ liệu sai. Nên dùng shared stateless token, versioned cache keys, backward-compatible session format hoặc sticky routing có kiểm soát khi cần.

Sticky session giúp ổn định trải nghiệm nhưng có thể làm phân phối traffic canary lệch và khiến rollback không tức thì với các session cũ. Phải đo exposure thực tế.

## 12. Health checks khác với kiểm tra tính đúng đắn nghiệp vụ

Một service có thể trả /healthz = 200, nhưng chức năng đặt hàng vẫn bị lỗi ở một nhánh hiếm. Vì vậy cần nhiều lớp xác minh:

| Loại kiểm tra | Mục tiêu |
|---|---|
| Liveness | Process còn đủ khỏe để tiếp tục chạy |
| Readiness | Có thể nhận request mới an toàn |
| Startup | Đã qua giai đoạn khởi động |
| Smoke test | Một số luồng cơ bản chạy được |
| Contract test | API/event đáp ứng consumer |
| Synthetic transaction | Luồng end-to-end an toàn hoạt động |
| Canary SLI analysis | Tác động trên traffic thật |
| Business invariant | Kết quả nghiệp vụ đúng, không trùng/mất |
| Post-deploy monitoring | Không có regression sau khi mở rộng |

Không đưa mọi synthetic operation vào readiness vì có thể gây tải, timeout hoặc side effects khi hàng trăm pod liên tục được probe. Dùng kiểm thử phù hợp ở tầng deployment pipeline.

## 13. Canary analysis: đo điều gì?

Một rollout có kiểm soát cần guardrails cho cả tính đúng đắn kỹ thuật và nghiệp vụ.

| Tín hiệu | Ví dụ câu hỏi |
|---|---|
| Request rate | Canary đã nhận đủ traffic để đánh giá chưa? |
| Error rate | 5xx, timeout, gRPC errors có tăng không? |
| Latency | p50/p95/p99 có xấu đi theo route không? |
| Saturation | CPU, memory, pool, queue có gần giới hạn? |
| Retry rate | Lỗi có bị che bằng retry làm tăng tải? |
| DB behavior | Query count, lock wait, connection wait có khác? |
| External calls | Payment/provider traffic, 429, quota có tăng? |
| Business success | Checkout hoàn tất, đơn tạo đúng, thanh toán thành công? |
| Correctness | Có dữ liệu sai, duplicate, missing event không? |
| Cost | Số lời gọi/chi phí trên một nghiệp vụ có tăng? |
| Feature exposure | Nhóm nào thực sự được bật logic mới? |

Cần định nghĩa baseline, threshold và action. Ví dụ một hệ thống giao dịch có thể dừng rollout ngay nếu phát hiện order/payment consistency violation, dù HTTP error rate chưa tăng.

Không có ngưỡng p95 hoặc error rate dùng chung cho mọi hệ thống. Chọn ngưỡng dựa trên SLO, lượng mẫu, mức độ rủi ro và chênh lệch chấp nhận được.

### 13.1. So sánh cùng thời điểm

Nếu stable và canary chạy đồng thời, so cùng route, region, traffic mix và load. Chỉ so "p95 hôm nay" với "p95 tuần trước" dễ bị ảnh hưởng thời điểm cao điểm, cache state hoặc dependency khác.

### 13.2. Chú ý lượng mẫu và bias

Canary nhận 1% traffic của dịch vụ ít người dùng có thể chỉ có vài chục request. Một lỗi duy nhất làm tỷ lệ lỗi tăng mạnh dù chưa đủ dữ liệu thống kê. Ngược lại, lỗi hiếm nhưng rất nghiêm trọng có thể cần dừng ngay mà không chờ đủ mẫu.

Canary theo một region hoặc khách hàng đặc biệt không phải nhóm ngẫu nhiên; nếu nhóm đó có hành vi khác stable, cần phân tầng hoặc thiết kế cohort phù hợp.

### 13.3. Tail latency và histogram

Khi so p95/p99, cần dùng metrics histogram thích hợp và biết rằng percentile từ sample ít có độ bất định lớn. Không cộng hoặc lấy trung bình các p95 của nhiều instance để có p95 toàn cục; hãy tổng hợp histogram/bucket hoặc dữ liệu phân phối theo cách hợp lệ.

## 14. Ví dụ phân tích canary bằng metrics

Giả sử 10 phút đầu:

| Chỉ số | Stable v1 | Canary v2 |
|---|---:|---:|
| Requests | 20.000 | 2.000 |
| HTTP 5xx | 40 | 12 |
| p95 latency | 320 ms | 580 ms |
| Checkout completed | 19.200 | 1.850 |
| Retry attempts / request | 0,04 | 0,22 |

Tính:

- Stable error rate = 40 / 20.000 = 0,20%.
- Canary error rate = 12 / 2.000 = 0,60%.
- Stable checkout completion = 19.200 / 20.000 = 96%.
- Canary checkout completion = 1.850 / 2.000 = 92,5%.

Canary có tín hiệu xấu ở cả error rate, p95, completion và retry. Đây là lý do để **tạm dừng tăng traffic** và điều tra; với hệ thống nhạy cảm có thể giảm canary về 0 tùy guardrail. Chưa thể kết luận v2 là nguyên nhân cuối cùng nếu traffic mix, region, dependency hoặc cờ tính năng khác nhau.

Cần xem trace của request chậm, mã lỗi, dependency và đường xử lý mới; đồng thời đối chiếu số lượng request và thời điểm đổi stage.

## 15. Ví dụ PromQL theo version

Các truy vấn dưới đây giả định hệ thống đã xuất HTTP request classic histogram với labels job, service_version, status và uri. Thay tên metric/label theo exporter thực tế.

### 15.1. Request rate

~~~promql
sum by (service_version) (
  rate(http_server_requests_seconds_count{
    job="checkout"
  }[5m])
)
~~~

Mục đích: xác nhận canary nhận traffic thực, không chỉ tồn tại pod mới.

### 15.2. Tỷ lệ HTTP 5xx

~~~promql
sum by (service_version) (
  rate(http_server_requests_seconds_count{
    job="checkout",
    status=~"5.."
  }[5m])
)
/
sum by (service_version) (
  rate(http_server_requests_seconds_count{
    job="checkout"
  }[5m])
)
~~~

Nếu mẫu số không có request hoặc series biến mất, không diễn giải như tỷ lệ lỗi 0; dashboard nên hiển thị request volume đồng thời.

### 15.3. p95 latency

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service_version) (
    rate(http_server_requests_seconds_bucket{
      job="checkout"
    }[5m])
  )
)
~~~

Ví dụ áp dụng cho classic histogram, không trực tiếp cho mọi native histogram. Percentile ước lượng phụ thuộc bucket và số request.

### 15.4. Phân tích theo route

~~~promql
sum by (service_version, uri) (
  rate(http_server_requests_seconds_count{
    job="checkout",
    uri="/checkout"
  }[5m])
)
~~~

Dùng route template chuẩn; không gắn raw userId/orderId vào metric labels vì cardinality tăng nhanh và có nguy cơ lộ dữ liệu.

## 16. Khi nào tăng, dừng hoặc hủy rollout?

Một mô hình ra quyết định có thể là:

~~~text
Deploy version mới
     |
     v
Readiness + smoke tests OK?
     |
     +-- Không --> dừng rollout, xử lý lỗi
     |
     v
Chuyển traffic canary nhỏ
     |
     v
Đủ traffic/đủ thời gian đo?
     |
     +-- Chưa --> tiếp tục quan sát theo ngân sách rủi ro
     |
     v
Guardrails pass?
     |
     +-- Không --> pause/abort/rollback/flag off
     |
     v
Tăng traffic stage tiếp theo
     |
     +-- Lặp lại cho tới khi đạt 100%
     |
     v
Theo dõi post-deploy và kết thúc
~~~

Điểm khác quan trọng:

- **Pause:** giữ nguyên stage để phân tích thêm; không mặc định có lỗi.
- **Abort:** hủy tiến trình rollout; tùy controller có thể scale down version mới hoặc chuyển traffic về stable.
- **Rollback:** phục hồi phiên bản/traffic trước đó theo kế hoạch.
- **Roll forward:** sửa lỗi bằng version mới khi rollback không an toàn.
- **Feature flag off:** tắt đường code mới nếu phiên bản hỗ trợ và điều này an toàn.

Automation chỉ đáng tin khi guardrail, dữ liệu đầu vào và quyền tác động được thiết kế kỹ. Không tự động rollback khi telemetry bị mất mà không phân biệt lỗi hệ thống quan sát với lỗi ứng dụng, trừ khi policy fail-safe đã được phê duyệt cho trường hợp đó.

## 17. Tổ chức pipeline CI/CD

Một pipeline an toàn có thể gồm:

~~~text
Commit / Pull request
   -> Build + unit tests
   -> Static analysis + dependency/security scan
   -> Package + immutable image digest
   -> Contract/integration tests
   -> Deploy staging + smoke test
   -> Chọn chiến lược production
   -> Apply manifests / start rollout
   -> Readiness + verify actual traffic
   -> Evaluate metrics, logs, traces, business guards
   -> Increase traffic or rollback
   -> Post-deploy observation
   -> Record final deployment outcome
~~~

Cần ghi deployment ID, source SHA, image digest, environment, region, config revision, migration status và các traffic stages để liên kết với sự cố sau này.

### 17.1. Immutable artifacts

Nên deploy cùng artifact đã qua kiểm thử, dùng digest bất biến nếu nền tảng hỗ trợ. Nếu một tag image được ghi đè giữa các lần deploy, quá trình rollback theo tag có thể lấy một binary khác dự kiến.

### 17.2. Idempotent pipeline

Chạy lại một bước deployment không được vô tình tạo tác vụ nghiệp vụ trùng hoặc phá hỏng trạng thái. Các lệnh kiểm tra trạng thái và apply manifest cần có cơ chế an toàn khi re-run. Cần lock/serialise các deployment cùng service và environment khi cần để tránh hai pipeline cùng thay traffic.

### 17.3. Migration trước, trong hay sau rollout?

Lập thứ tự dựa trên khả năng tương thích:

- Expand schema thường diễn ra trước rollout code mới.
- Backfill có thể chạy nền theo batch có giới hạn.
- Bật code path mới sau khi dữ liệu đủ.
- Contract schema cũ chỉ sau khi mọi consumer không còn phụ thuộc.

Không nên đưa một migration không đảo ngược vào cùng bước với traffic switch mà không có kế hoạch xử lý khi rollback.

## 18. Feature flags và tách deploy khỏi release

**Deploy code** là đưa binary mới vào hệ thống. **Release feature** là cho người dùng tiếp cận một hành vi mới. Feature flags cho phép hai việc này diễn ra ở thời điểm khác nhau.

Ví dụ:

~~~text
Ngày 1: Deploy Checkout v2.4.1 tới 100% pod
        new-checkout-flow = OFF cho mọi user
Ngày 2: Bật flag cho nhân viên nội bộ
Ngày 3: Bật 5% khách hàng
Ngày 4: Bật 25% khách hàng
Ngày 5: Bật 100% sau khi chỉ số ổn
~~~

Lợi ích: có thể tắt nhánh tính năng nhanh nếu phát hiện regression mà không rollback toàn bộ service. Tuy nhiên flag off cũng cần kiểm chứng; nếu bản mới đã thay dữ liệu hoặc có side effect, tắt flag không tự sửa hậu quả.

Cần lưu flag change events, variant exposure, nguồn quyết định và độ trễ cache của flag SDK. Feature flags có tuổi thọ dài nếu không được dọn dẹp; quy trình quản trị nên có owner, mục tiêu và thời điểm loại bỏ flag.

## 19. Observability theo version và rollout stage

Mỗi service nên cung cấp đủ thông tin để trả lời "request này đã chạy trên phiên bản nào?".

Ví dụ metadata:

~~~json
{
  "service": "checkout-service",
  "serviceVersion": "2.4.1",
  "deploymentId": "checkout-prod-20261112-1408",
  "region": "region-a",
  "rolloutStage": "canary-25",
  "traceId": "example-trace-id",
  "operation": "POST /checkout",
  "outcome": "success"
}
~~~

Mẫu trên minh họa structured log; không nên gắn mỗi traceId vào metric label. Trong OpenTelemetry, service.version có thể đặt ở resource; deployment IDs chi tiết có thể truy ngược qua release registry, tránh tạo quá nhiều time series.

**Deployment annotations** nên có start, pod ready, traffic shifted, paused, completed, rollback started/completed. Khi lỗi xuất hiện sau một mốc cụ thể, việc so canary/stable giúp kiểm tra giả thuyết.

Không nhầm correlation với causation: lỗi xuất hiện sau deploy chưa đủ chứng minh deploy gây lỗi; kiểm tra dependency, traffic mix, config/flag/migration và các nhóm không nhận thay đổi.

## 20. Bảo đảm rollback có thể thực hiện

Rollback phải được chuẩn bị **trước** khi triển khai, gồm:

- Artifact ổn định đã biết, có digest và cấu hình tương thích.
- Quy tắc chuyển traffic về stable/Blue.
- Kiểm tra khả năng rollback của schema và dữ liệu.
- Phiên bản API/event có thể tương thích khi hai bản cùng chạy.
- Số replica/capacity cần để nhận lại 100% traffic.
- Quy trình drain version mới và đóng consumer/job.
- Cách xử lý side effects đã xảy ra, đặc biệt thanh toán/đơn hàng.
- Quy trình quan sát tính đúng đắn sau rollback.

### 20.1. Rollback rolling update

Rolling ngược có thể tốn thời gian và tạo một đợt mixed-version mới. Cần quan sát readiness, unavailable pods và 5xx phát sinh trong quá trình phục hồi.

### 20.2. Rollback blue-green

Nếu Blue còn tồn tại và đủ capacity, có thể đổi routing tương đối nhanh. Nhưng các kết nối cũ, session và dữ liệu do Green ghi có thể khiến lỗi kéo dài. Phải kiểm tra việc switch thực sự hoàn tất và các job nền đã được kiểm soát.

### 20.3. Rollback canary

Đưa trọng số canary về 0 hoặc loại cohort exposure. Một số connection dài và user sticky có thể vẫn ở version mới; cần cơ chế drain hoặc chuyển session hợp lệ. Hành vi do version mới đã thực hiện không được đảo ngược chỉ bằng cách đổi routing.

### 20.4. Rollback không phải luôn là lựa chọn đúng

Nếu schema/data migration không thể đảo ngược an toàn, phát hành bản sửa mới có thể ít rủi ro hơn. Với hệ thống tài chính, cần đối soát giao dịch và trạng thái nguồn sự thật trước khi đổi hành vi lần nữa.

## 21. Statefulness và các vấn đề đặc biệt

### 21.1. Stateful services

Database, broker, stateful stream processor hoặc service giữ state trong bộ nhớ không thể coi như stateless HTTP API. Cần replication, leader election, partition assignment, checkpoint và quy trình rolling chuyên biệt. Không dùng cùng một manifest rolling của API stateless để thay cluster lưu trữ dữ liệu mà chưa hiểu cơ chế quorum và consistency.

### 21.2. Message consumers

Nếu stable và canary cùng subscribe một consumer group, broker có thể phân chia partitions giữa hai version; đó có thể là rollout hợp lệ, nhưng không tương đương tỷ lệ HTTP traffic. Nếu cả hai ở hai group khác nhau, mỗi group có thể xử lý cùng message và gây side effects lặp. Phải kiểm soát consumer group và idempotency.

### 21.3. Scheduled jobs

Trong blue-green, nếu cả Blue và Green đều chạy scheduler, cron có thể thực hiện hai lần. Dùng leader election, distributed locks hoặc tách scheduler thành dịch vụ độc lập; quy tắc thực thi phải rõ trong thời kỳ song song.

### 21.4. Long-lived connection

WebSocket, SSE, gRPC streaming và HTTP2 có thể giữ kết nối lâu. Traffic shift chỉ áp dụng request/kết nối mới nếu không có cơ chế chấm dứt hoặc migrate. Cần timeout, resumption, drain và client reconnect behavior phù hợp.

### 21.5. Sticky sessions

Session affinity giúp người dùng không nhảy giữa version nhưng làm phân phối canary lệch. Khi rollback, có thể cần xóa/đổi sticky mapping và bảo đảm session data tương thích.

## 22. Triển khai đa vùng và blast radius

Một thay đổi có thể phát hành tới từng region hoặc cluster:

~~~text
Region A: v2 canary 5%
Region B: v1 100%
Region C: v1 100%
        |
        v
Kiểm tra A ổn -> tăng A lên 100%
        |
        v
Canary B rồi C
~~~

Ưu điểm là giới hạn phạm vi ảnh hưởng theo địa lý/hạ tầng. Nhưng traffic của mỗi region có thể khác nhau; một lỗi chỉ xảy ra với phương thức thanh toán hoặc dữ liệu ở Region C sẽ không lộ ra khi thử ở A.

Cần theo dõi dependency chung: nếu các region cùng dùng một database hoặc provider, lỗi ở canary A có thể tác động tới vùng khác qua tải/tài nguyên. Blast radius thực tế không luôn bằng phần trăm request trực tiếp tới canary.

Đối với dịch vụ quan trọng, có thể triển khai theo thứ tự internal environment → một region ít rủi ro → nhiều region, với guardrails và mốc phê duyệt cụ thể.

## 23. Ví dụ hệ thống Order, Inventory và Payment

Một hệ thống thương mại điện tử có:

~~~text
API Gateway
  -> Checkout Service
       -> Inventory Service
       -> Payment Service
       -> Order Service
~~~

Cần phát hành Checkout v2 có thuật toán khuyến mãi mới và thay đổi cách gọi Payment.

### Phương án rolling

Nếu v2 backward-compatible với Payment/Order và chỉ thêm trường optional, có thể rolling 6 replica Checkout. Quan sát tổng tỷ lệ checkout success và request metrics theo version. Vẫn cần test logic giảm giá đúng cho cả request chạm v1 và v2.

### Phương án blue-green

Tạo môi trường Green với Checkout v2, kiểm thử API và synthetic checkout dùng sandbox hoặc transaction an toàn. Sau đó chuyển router từ Blue v1 sang Green v2. Nếu gặp lỗi, chuyển lại Blue. Phải đảm bảo cả hai dùng dữ liệu/schema tương thích.

### Phương án canary

Đưa 5% traffic phù hợp vào Checkout v2. Quan sát:

- HTTP 5xx và timeout.
- Checkout completed / checkout started.
- Payment authorization / duplicate attempts.
- Order amount so với kỳ vọng theo business rule.
- Latency p95/p99.
- Retry, queue backlog và DB connection pool.
- Cohort/region/payment method.

Nếu tỷ lệ checkout thành công giảm hoặc tính tiền sai, dừng rollout; nếu ổn theo guardrails và đủ mẫu, tăng traffic. Đây là ví dụ mà business correctness quan trọng hơn chỉ nhìn HTTP status.

## 24. Bài tập tính toán

### Bài 1: Rolling update và capacity

Dịch vụ có 10 replica, mỗi replica xử lý an toàn 80 RPS, traffic hiện tại 620 RPS. Nếu maxUnavailable=3 và không tính pod surge đang ready:

- Số pod ready tối thiểu trong kịch bản cho phép: 10 - 3 = 7.
- Capacity danh nghĩa còn: 7 × 80 = 560 RPS.
- 560 RPS thấp hơn 620 RPS; có nguy cơ quá tải.

Hỏi: nên cân nhắc thay đổi gì?

Gợi ý: giảm maxUnavailable, tăng maxSurge nếu cluster đủ capacity, tăng replicas/headroom hoặc giảm concurrency/traffic trong rollout; cần kiểm tra khả năng scale thực và startup time.

### Bài 2: Canary số lượng mẫu

Trong 10 phút stable nhận 30.000 request với 60 lỗi, canary nhận 300 request với 3 lỗi.

- Stable error rate = 60 / 30.000 = 0,20%.
- Canary error rate = 3 / 300 = 1,00%.

Canary có tín hiệu xấu hơn, nhưng chỉ có 300 request; cần xem loại lỗi và mức nghiêm trọng, độ lệch traffic mix, số mẫu cũng như các business guards. Không thể áp một kết luận thống kê chung mà bỏ qua định nghĩa của sự cố.

### Bài 3: Blue-green và schema

Green v2 ghi một JSON mới vào cột orders.metadata mà Blue v1 không biết đọc. Có nên switch về Blue ngay khi thấy lỗi?

Câu trả lời: chưa thể coi đó là rollback an toàn. Cần đánh giá tác động dữ liệu đã ghi, có thể dùng compatibility layer, hotfix hoặc roll forward trước khi chuyển lại. Rollback traffic không tự sửa dữ liệu cũ không hiểu.

### Bài 4: Async consumer

Stable v1 và canary v2 cùng tham gia một consumer group. Sau khi scale canary lên 25% số pod, số message canary xử lý có nhất thiết là 25% không?

Không. Phân phối message phụ thuộc partition assignment, tốc độ xử lý, rebalancing, key distribution và broker semantics, không chỉ tỷ lệ pod. Đo số message thực xử lý theo version và độ trễ/side effects.

### Bài 5: Phân tích metric

Canary v2 có HTTP 5xx tương đương v1 nhưng checkout completion giảm từ 97% xuống 92%. Có nên tiếp tục tăng traffic vì error rate ổn?

Không tự động. Đây là tín hiệu thay đổi hành vi có thể quan trọng. Kiểm tra logic nghiệp vụ, payment/order states, event pipeline và data correctness trước khi tiếp tục.

## 25. Runbook mẫu cho một rollout an toàn

### Trước triển khai

- [ ] Artifact đã build/test, có version và image digest bất biến.
- [ ] Đã xác định thay đổi API, event và database schema; các version chéo tương thích.
- [ ] Có baseline của technical SLI và business SLI.
- [ ] Có capacity headroom, resource requests/limits hợp lý.
- [ ] Có readiness/startup/liveness probes và graceful shutdown.
- [ ] Có smoke tests và rollback target.
- [ ] Đã biết xử lý data migration, session và in-flight requests.
- [ ] Dashboard có service_version, deployment markers và trace/log correlation.
- [ ] Có owner vận hành và các guardrails rõ ràng.

### Trong triển khai

- [ ] Xác nhận pod mới thực sự ready.
- [ ] Xác nhận tỷ lệ traffic/version thực tế, không chỉ trạng thái pipeline.
- [ ] Quan sát 5xx, p95/p99, retry, saturation, queue và correctness.
- [ ] Ghi các mốc tăng traffic và kết quả analysis.
- [ ] Pause khi dữ liệu chưa đủ hoặc metric bất thường.
- [ ] Dừng/rollback khi guardrails bị vi phạm.
- [ ] Giữ thông tin sự kiện thay đổi để điều tra.

### Sau triển khai

- [ ] Xác nhận tất cả request mới đã đi tới version mong muốn.
- [ ] Kiểm tra instance cũ được drain, consumer và scheduler đúng trạng thái.
- [ ] Kiểm tra business success, data consistency, logs/traces.
- [ ] Theo dõi backlog và lỗi xuất hiện muộn.
- [ ] Ghi deployment outcome và thời điểm hoàn tất.
- [ ] Giữ rollback window hoặc scale down tài nguyên theo chính sách.
- [ ] Dọn feature flags/tài nguyên tạm khi thích hợp.

## 26. Các lỗi thiết kế thường gặp

1. **Deploy một lần 100% mà không có guardrails:** blast radius lớn khi có lỗi.
2. **Nhầm rolling update với canary:** có pod mới chưa chắc kiểm soát được tỷ lệ traffic và nhóm người dùng.
3. **Readiness trả OK quá sớm:** pod chưa warm up đã nhận request.
4. **Liveness kiểm tra dependency không phù hợp:** outage chung gây restart storm.
5. **Không drain kết nối:** request đang xử lý bị 502/503 khi pod bị kill.
6. **maxUnavailable quá lớn so với tải:** capacity tụt trong rollout.
7. **Không đủ cluster capacity cho maxSurge/Green:** rollout treo hoặc degrade.
8. **Dùng tag image mutable:** rollback không chắc lấy đúng binary.
9. **API/database schema không tương thích:** v1 và v2 lỗi khi cùng chạy.
10. **Blue và Green cùng chạy scheduler/consumer có side effects:** xử lý trùng.
11. **Canary được route vào cohort khác stable:** kết luận sai từ metric.
12. **Canary quá ít request nhưng tự động promote:** thiếu dữ liệu để thấy lỗi.
13. **Chỉ giám sát CPU/HTTP 5xx:** bỏ qua sai giá, trùng đơn, mất event.
14. **Không gắn version vào metrics/traces/logs:** không biết bản nào gây triệu chứng.
15. **Tăng traffic quá nhanh trước khi metrics ổn định:** chưa nhìn thấy hậu quả delayed.
16. **Rollback code nhưng không xét data migration:** khôi phục không an toàn.
17. **Sticky sessions/long-lived connections bị quên:** traffic switch không có hiệu lực ngay.
18. **Không có quan sát sau deploy:** lỗi muộn từ queue, cache hoặc batch bị bỏ sót.

## 27. Checklist lựa chọn chiến lược

Trước khi chọn rolling, blue-green hay canary, cần trả lời:

- Dịch vụ có state không? Có long-lived connections hay queue consumers?
- Thời gian startup/warm-up là bao lâu?
- Tải đỉnh và headroom của mỗi pod/cluster?
- Có thể chạy song song v1/v2 và dùng chung database/schema không?
- Có routing theo tỷ lệ/cohort và đo exposure thực tế không?
- Cần chuyển traffic về bản cũ nhanh tới mức nào?
- Có business SLI để nhận diện sai dữ liệu, không chỉ lỗi HTTP không?
- Một lỗi ở 5% canary có thể ảnh hưởng dependency chung thế nào?
- Có feature flag phù hợp để tắt tính năng thay vì rollback toàn binary?
- Chi phí duy trì Blue và Green hoặc canary thêm có chấp nhận được không?
- Quy trình stop/abort/rollback có được kiểm thử với traffic thật không?
- Các service phụ thuộc có phù hợp với mixed-version window không?

Không nên áp một chiến lược duy nhất cho mọi service. Một API stateless ít rủi ro có thể dùng rolling; thay đổi thanh toán hoặc pricing nên cân nhắc canary với business metrics; môi trường cần chuyển traffic nhanh và có đủ tài nguyên có thể dùng blue-green.

## 28. Ghi nhớ

**Rolling update** thay pod theo từng bước, thường đơn giản và tiết kiệm tài nguyên. **Blue-green** giữ hai môi trường rồi chuyển traffic, hữu ích khi cần tách môi trường kiểm thử và chuyển lại nhanh. **Canary** tăng dần exposure dựa trên dữ liệu, phù hợp với thay đổi có rủi ro và cần đánh giá trên production.

Cả ba đều cần readiness đáng tin, graceful shutdown, đủ capacity, định danh version, observability, API/database/event compatibility, guardrails và phương án rollback. Không chiến lược nào tự bảo đảm zero downtime hoặc tính đúng đắn nghiệp vụ.

Trong thực tế, lựa chọn chiến lược chỉ là phần đầu. Điều quyết định độ an toàn là **biết phiên bản nào thực sự phục vụ người dùng, đo đúng tác động, dừng được khi xuất hiện tín hiệu xấu và phục hồi mà không làm hỏng dữ liệu hay giao dịch**.