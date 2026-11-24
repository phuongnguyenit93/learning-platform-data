# Networking, cổng dịch vụ và service discovery cho container

Khi chạy ứng dụng bằng container, mỗi thành phần có thể được tạo, thay thế hoặc chuyển sang máy khác trong quá trình triển khai và mở rộng. Vì vậy, địa chỉ IP của một container thường chỉ có giá trị tạm thời. Các thành phần cần một cách kết nối ổn định, biết cổng nào đang nhận yêu cầu và tìm được dịch vụ đích mà không phải cấu hình thủ công từng địa chỉ IP.

Bài học này thuộc chương **Dịch vụ chạy container** trong module **CLOUD_CORE_SERVICES_COMPUTE**. Nội dung tập trung vào cách container tham gia mạng, cách ánh xạ cổng từ ứng dụng ra ngoài, và cách các dịch vụ tìm thấy nhau trong môi trường container trên nền tảng đám mây. Đây là những kiến thức cần thiết khi triển khai ứng dụng, mở rộng tải, duy trì tính sẵn sàng và kiểm soát chi phí vận hành.

Sau bài học, người học có thể:

- Phân biệt cổng ứng dụng, cổng container, cổng máy chủ và cổng dịch vụ.
- Chọn kiểu kết nối phù hợp giữa các container và giữa container với người dùng.
- Giải thích vai trò của DNS, service registry, health check và load balancer trong service discovery.
- Cấu hình và kiểm tra kết nối bằng Docker Compose hoặc Kubernetes.
- Khoanh vùng các lỗi thường gặp về cổng, DNS, endpoint, firewall và trạng thái sẵn sàng.

## 1. Đường đi của một yêu cầu mạng

Container thường chạy trong một môi trường mạng được cô lập. Runtime hoặc nền tảng điều phối cấp cho container một giao diện mạng, địa chỉ IP, route và quy tắc kết nối. Các container cùng mạng có thể trao đổi dữ liệu qua địa chỉ hoặc tên dịch vụ; lưu lượng từ bên ngoài thường đi qua cổng được công bố, load balancer hoặc ingress.

Một luồng HTTP điển hình trong môi trường cloud có thể là:

```mermaid
flowchart LR
    U[Người dùng] --> DNS[DNS công khai]
    DNS --> LB[Load balancer]
    LB --> IN[Ingress hoặc gateway]
    IN --> SVC[Container service]
    SVC --> APP[Container ứng dụng]
    APP --> DB[Container cơ sở dữ liệu]
```

Mỗi lớp có một trách nhiệm riêng:

- **DNS công khai** phân giải tên miền của ứng dụng thành địa chỉ của điểm vào.
- **Load balancer** nhận lưu lượng, kiểm tra trạng thái đích và phân phối yêu cầu đến các instance khỏe mạnh.
- **Ingress hoặc gateway** áp dụng quy tắc định tuyến HTTP/HTTPS theo host, path hoặc các điều kiện khác.
- **Service** cung cấp một điểm truy cập ổn định cho nhóm container thay đổi theo thời gian.
- **Container ứng dụng** xử lý yêu cầu và gọi các dịch vụ phụ thuộc, chẳng hạn cơ sở dữ liệu hoặc hàng đợi.

Không phải triển khai nào cũng cần đủ các lớp trên. Ứng dụng nhỏ có thể dùng một load balancer trước dịch vụ; hệ thống nhiều API có thể dùng ingress hoặc gateway để gom các quy tắc định tuyến. Cần xác định rõ lớp nào chịu trách nhiệm kết thúc TLS, kiểm tra sức khỏe và kiểm soát truy cập để tránh cấu hình trùng hoặc bỏ sót.

## 2. Hiểu đúng về cổng dịch vụ

Một tiến trình trong container phải mở socket trên một địa chỉ và cổng để nhận kết nối. Với dịch vụ web, ứng dụng thường lắng nghe TCP trên cổng như `8080` hoặc `3000`. Trong container, ứng dụng thường cần bind vào `0.0.0.0` để nhận kết nối từ giao diện mạng của container. Nếu chỉ bind vào `127.0.0.1`, tiến trình có thể chỉ nhận kết nối nội bộ từ chính container đó, khiến container khác hoặc cổng được publish không truy cập được.

Các khái niệm cổng cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Cổng ứng dụng | Cổng mà tiến trình bên trong container đang lắng nghe | API nghe TCP `8080` |
| `containerPort` | Khai báo cổng container trong cấu hình nền tảng; thường giúp tài liệu hóa hoặc làm đích cho cấu hình khác tham chiếu | Pod khai báo `containerPort: 8080` |
| `targetPort` | Cổng đích bên trong Pod/container mà Service chuyển tiếp đến | Service nhận ở `80`, chuyển đến `8080` |
| `port` của Service | Cổng ổn định mà client trong mạng cluster dùng để gọi Service | `orders:80` |
| `hostPort` | Cổng được gắn trực tiếp trên máy chạy workload | Máy chủ nhận ở `18080`, chuyển đến container `8080` |
| Cổng publish/map | Ánh xạ cổng máy chủ sang cổng container, thường gặp ở Docker | `8080:8080` |

Trong Docker, `EXPOSE 8080` trong Dockerfile chỉ mô tả cổng dự kiến của ứng dụng; nó không tự mở cổng trên máy chủ. Muốn truy cập từ máy chủ hoặc bên ngoài, cần cấu hình publish, chẳng hạn `-p 8080:8080`. Các container cùng một Docker network có thể kết nối trực tiếp tới cổng ứng dụng của nhau bằng tên dịch vụ mà không cần publish cổng đó ra máy chủ.

Trong Kubernetes, `containerPort` cũng không tự tạo firewall rule hay công khai ứng dụng ra Internet. Service mới là đối tượng cung cấp địa chỉ và cổng ổn định cho các Pod. Service kiểu `LoadBalancer` có thể yêu cầu cloud provider tạo load balancer; Ingress cần một ingress controller đang hoạt động để nhận và định tuyến HTTP/HTTPS.

**Nguyên tắc cấu hình:** chỉ công bố các cổng cần thiết cho từng nhóm client. API công khai có thể nhận HTTPS qua load balancer; cơ sở dữ liệu thường chỉ nhận kết nối từ backend trong mạng riêng. Không mở cổng quản trị hoặc cổng dữ liệu ra Internet nếu không có yêu cầu rõ ràng và biện pháp bảo vệ tương ứng.

## 3. Các kiểu mạng container thường gặp

### Bridge network trên một máy

Docker tạo một mạng bridge để các container trên cùng máy chủ trao đổi qua mạng ảo. Docker Compose thường tạo một mạng riêng cho project; các service trong cùng mạng có thể tìm nhau bằng tên service.

Ưu điểm là dễ thiết lập, phù hợp phát triển và thử nghiệm trên một máy. Giới hạn chính là phạm vi mạng thường gắn với máy chủ đó. Khi ứng dụng chạy trên nhiều node, cần cơ chế mạng và điều phối ở cấp cluster.

### Host network

Container dùng trực tiếp network namespace của máy chủ. Cách này có thể giảm một lớp chuyển tiếp mạng và hữu ích trong một số workload đặc thù, nhưng làm giảm mức cô lập. Các tiến trình có thể tranh chấp cùng cổng trên host; việc di chuyển workload giữa node cũng khó dự đoán hơn. Chỉ chọn khi có lý do kỹ thuật cụ thể và đã đánh giá tác động bảo mật.

### Overlay hoặc mạng Pod trong cluster

Mạng overlay tạo kết nối logic giữa các node, cho phép workload ở các máy khác nhau giao tiếp như đang ở cùng một mạng. Kubernetes dùng mô hình mạng Pod do CNI plugin cung cấp; tùy plugin, lưu lượng có thể được định tuyến trực tiếp hoặc đi qua lớp overlay. Không nên giả định mọi cluster Kubernetes đều triển khai mạng theo cùng một cách.

Mô hình này phù hợp với ứng dụng phân tán và khả năng mở rộng nhiều node. Đổi lại, đội vận hành cần hiểu chính sách mạng, MTU, route, DNS và cách quan sát lưu lượng giữa các node. Cấu hình sai có thể tạo lỗi chỉ xuất hiện khi workload nằm ở các node khác nhau.

### Mạng riêng trên cloud

Trong các dịch vụ container được quản lý, workload thường kết nối vào VPC hoặc mạng riêng tương đương. Subnet, route table, security group hoặc firewall policy quyết định luồng lưu lượng nào được phép đi vào và đi ra. Một số nền tảng gán địa chỉ mạng trực tiếp cho Pod/task; nền tảng khác dùng địa chỉ hoặc cổng trên node và một lớp chuyển tiếp.

Khi thiết kế, hãy xác định rõ:

1. Client nào cần gọi dịch vụ và từ vùng mạng nào.
2. Giao thức và cổng đích cần cho phép.
3. Dịch vụ có cần địa chỉ công khai hay chỉ cần truy cập nội bộ.
4. Lưu lượng phản hồi, DNS và kết nối đến dịch vụ phụ thuộc đi qua route nào.
5. Quy tắc mạng có còn đúng khi số lượng replica hoặc node tăng lên hay không.

## 4. Service discovery: tìm dịch vụ bằng tên ổn định

Địa chỉ IP của container có thể thay đổi khi container khởi động lại, được thay thế sau khi triển khai phiên bản mới hoặc được lập lịch sang node khác. Nếu cấu hình ứng dụng lưu cứng IP của từng container, hệ thống dễ phát sinh lỗi sau các sự kiện vận hành bình thường.

**Service discovery** giải quyết vấn đề này bằng cách cung cấp tên hoặc điểm truy cập ổn định. Client gọi dịch vụ theo tên; DNS, service registry hoặc lớp điều phối tìm các endpoint hiện đang phục vụ tên đó. Endpoint có thể được thêm, loại bỏ hoặc thay thế mà client không cần biết từng IP cụ thể.

Một hệ thống service discovery thường có các thành phần:

- **Tên dịch vụ:** tên logic mà client sử dụng, ví dụ `orders` hoặc `payments`.
- **Registry hoặc DNS:** lưu và phân giải thông tin về các endpoint.
- **Health check/readiness:** xác định instance nào đủ điều kiện nhận yêu cầu.
- **Cơ chế phân phối:** chọn endpoint hoặc chuyển yêu cầu qua load balancer/service proxy.
- **Client:** sử dụng tên dịch vụ và xử lý timeout, retry, lỗi kết nối theo chính sách phù hợp.

DNS giúp giảm phụ thuộc vào IP, nhưng không thay thế hoàn toàn health check hoặc xử lý lỗi. Client có thể giữ cache DNS trong một khoảng thời gian; một endpoint vừa bị loại khỏi registry vẫn có thể còn xuất hiện trong cache của client. Ứng dụng cần timeout hợp lý và khả năng kết nối lại khi endpoint thay đổi.

### Service discovery trong Docker Compose

Trong một project Compose, tên service được dùng làm hostname trên mạng Compose. Ví dụ, service `api` có thể kết nối đến cơ sở dữ liệu qua hostname `db` và cổng PostgreSQL `5432`. Không nên dùng IP nội bộ của container vì IP có thể đổi khi container được tạo lại.

Ví dụ cấu hình rút gọn:

```yaml
services:
  api:
    build: .
    environment:
      PORT: "8080"
      DATABASE_URL: postgresql://app_user:${DB_PASSWORD}@db:5432/orders
    ports:
      - "8080:8080"
    depends_on:
      db:
        condition: service_healthy
    networks:
      - backend

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: orders
      POSTGRES_USER: app_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \"$${POSTGRES_USER}\" -d \"$${POSTGRES_DB}\""]
      interval: 5s
      timeout: 3s
      retries: 10
    networks:
      - backend

volumes:
  db_data:

networks:
  backend:
    driver: bridge
```

Trong ví dụ, `api` gọi `db:5432` qua mạng nội bộ. Chỉ API publish cổng `8080` ra máy chủ; PostgreSQL không publish cổng nên không có điểm truy cập trực tiếp từ host thông qua cấu hình này. `depends_on` với điều kiện `service_healthy` giúp Compose chờ health check của database trước khi khởi động API, nhưng ứng dụng vẫn cần xử lý trường hợp database mất kết nối sau khi hệ thống đã chạy. Giá trị `DB_PASSWORD` nên được cấp từ secret store hoặc cơ chế quản lý bí mật phù hợp khi triển khai thực tế; không commit mật khẩu thật vào repository.

### Service discovery trong Kubernetes

Kubernetes Service cung cấp một địa chỉ ổn định trước một nhóm Pod được chọn bằng label. DNS trong cluster phân giải tên Service, còn control plane cập nhật các endpoint tương ứng khi Pod được tạo, thay thế hoặc không còn sẵn sàng.

Ví dụ Service nội bộ cho ứng dụng `orders`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: production
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: 8080
```

Các Pod trong namespace `production` có thể gọi `http://orders:80`; client ở namespace khác có thể dùng tên đầy đủ `orders.production.svc.cluster.local`. Service chuyển tiếp lưu lượng đến cổng `8080` của những Pod có label `app: orders` và đủ điều kiện nhận traffic. Nếu selector không khớp label Pod, Service có thể tồn tại nhưng không có endpoint để chuyển tiếp.

`ClusterIP` chỉ phục vụ truy cập trong cluster. Nếu cần nhận traffic từ bên ngoài, có thể dùng `LoadBalancer` hoặc cấu hình Ingress/Gateway tùy yêu cầu. Load balancer thường dễ hiểu và tích hợp trực tiếp với cloud provider nhưng có thể tạo chi phí cho từng điểm vào. Ingress/Gateway có thể gom nhiều route HTTP vào một điểm vào, song cần vận hành controller, chứng chỉ TLS và quy tắc định tuyến.

Trên các nền tảng container cloud khác, ý tưởng tương tự được triển khai qua service registry, DNS riêng, service connect hoặc load balancer do nhà cung cấp quản lý. Ví dụ, một dịch vụ container có thể đăng ký task vào registry để service khác tìm theo tên; nền tảng sẽ cập nhật endpoint khi task thay đổi. Cần đọc đúng mô hình mạng của dịch vụ đang dùng vì cách cấp IP, ánh xạ cổng và phạm vi DNS có thể khác nhau giữa các nhà cung cấp.

## 5. Chọn điểm vào và phân đoạn lưu lượng

Một thiết kế phổ biến là chia lưu lượng thành hai nhóm:

- **North-south:** lưu lượng từ người dùng hoặc hệ thống bên ngoài đi vào ứng dụng, thường qua DNS, load balancer, ingress hoặc gateway.
- **East-west:** lưu lượng giữa các service bên trong hệ thống, chẳng hạn API gọi database hoặc service thanh toán. Nhóm này thường được giữ trong mạng riêng và giới hạn theo nhu cầu thực tế.

Ví dụ, người dùng truy cập `https://shop.example.com`. DNS trỏ tên miền đến load balancer công khai. Load balancer kết thúc TLS hoặc chuyển TLS đến ingress theo thiết kế; ingress định tuyến `/orders` đến Service `orders`. Service chọn các Pod sẵn sàng. Khi API cần đọc dữ liệu, nó gọi hostname nội bộ của database hoặc dịch vụ dữ liệu thông qua cổng được cho phép trong mạng riêng.

Thiết kế này giúp tách điểm vào công khai khỏi các dịch vụ nội bộ. Tuy nhiên, mỗi lớp trung gian đều có cấu hình, giới hạn kết nối, log và chi phí riêng. Với hệ thống nhỏ, một load balancer có thể đủ. Khi có nhiều ứng dụng hoặc route, ingress/gateway có thể giảm số điểm vào cần quản lý. Hãy cân nhắc số lượng dịch vụ, yêu cầu TLS, lưu lượng đỉnh, khả năng chịu lỗi và chi phí cố định trước khi chọn.

## 6. Kiểm tra kết nối theo từng lớp

Khi một client không gọi được dịch vụ, kiểm tra từ gần ứng dụng ra ngoài giúp khoanh vùng nhanh hơn. Trước tiên xác nhận tiến trình đang lắng nghe đúng cổng; sau đó kiểm tra mạng nội bộ, DNS/service, endpoint, cuối cùng mới kiểm tra load balancer và firewall.

### Kiểm tra với Docker

```bash
# Xem container và trạng thái
docker ps

# Xem ánh xạ cổng từ host vào container
docker port <container-name>

# Xem các container đang tham gia mạng
docker network inspect <network-name>

# Kiểm tra DNS từ container ứng dụng
docker exec <api-container> getent hosts db

# Kiểm tra ứng dụng đang lắng nghe trong container
docker exec <api-container> sh -c 'ss -lnt || netstat -lnt'

# Kiểm tra endpoint từ host nếu cổng đã publish
curl -v http://localhost:8080/health
```

Nếu image tối giản không có `getent`, `ss`, `netstat` hoặc `curl`, hãy dùng một container công cụ tạm thời cùng network để kiểm tra DNS và kết nối. Khi kiểm tra từ container ngang hàng, gọi hostname service và cổng container, ví dụ `http://api:8080/health`; không dùng cổng host trừ khi đang kiểm tra đường truy cập qua host.

### Kiểm tra với Kubernetes

```bash
# Xem Service và địa chỉ cluster
kubectl get svc -n production

# Xem endpoint mà Service đang chọn
kubectl get endpointslices -n production \
  -l kubernetes.io/service-name=orders

# Kiểm tra Pod, label và trạng thái sẵn sàng
kubectl get pods -n production --show-labels

# Xem cấu hình selector và port của Service
kubectl describe svc orders -n production

# Thử phân giải DNS từ một Pod có công cụ phù hợp
kubectl exec -n production <debug-pod> -- \
  nslookup orders.production.svc.cluster.local

# Gọi Service từ bên trong cluster
kubectl exec -n production <debug-pod> -- \
  curl -v http://orders:80/health
```

Nếu không có EndpointSlice hoặc danh sách endpoint rỗng, kiểm tra selector của Service, label Pod và readiness probe. Nếu DNS phân giải được nhưng kết nối timeout, kiểm tra cổng ứng dụng, NetworkPolicy, route và firewall. Nếu Service nội bộ hoạt động nhưng người dùng bên ngoài không truy cập được, kiểm tra Ingress/Gateway, địa chỉ load balancer, listener, chứng chỉ và quy tắc mạng ở lớp cloud.

### Kiểm tra trên nền tảng cloud

Với dịch vụ container được quản lý, kiểm tra cả cấu hình trong nền tảng lẫn cấu hình ứng dụng:

1. Task, replica hoặc Pod có trạng thái running và healthy hay không.
2. Cổng container, cổng service và cổng target group có khớp nhau không.
3. Health check dùng đúng giao thức, cổng và đường dẫn; ứng dụng có trả mã thành công trong thời gian cho phép không.
4. Security group/firewall cho phép đúng nguồn, đích và cổng cần thiết.
5. Subnet và route table có đường đi đến đích; DNS có phân giải đúng tên trong đúng phạm vi mạng không.
6. Log của ứng dụng, ingress và load balancer có chỉ ra lỗi từ chối kết nối, timeout hoặc không có endpoint không.

Health check của load balancer và readiness check của ứng dụng có mục đích liên quan nhưng không hoàn toàn giống nhau. Readiness xác định instance có nên nhận traffic hay chưa; liveness thường giúp phát hiện tiến trình bị kẹt để nền tảng khởi động lại. Health check của load balancer quyết định đích có được nhận lưu lượng từ load balancer hay không. Cấu hình sai có thể khiến instance tốt bị loại khỏi traffic hoặc instance chưa sẵn sàng vẫn nhận yêu cầu.

## 7. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xác minh hoặc khắc phục |
|---|---|---|
| Kết nối bị từ chối ngay | Ứng dụng chưa chạy, sai cổng hoặc chỉ bind vào `127.0.0.1` | Kiểm tra log và socket lắng nghe; bind vào `0.0.0.0` khi cần nhận kết nối qua interface container |
| Kết nối timeout | Firewall, NetworkPolicy, route hoặc security group chặn lưu lượng | Kiểm tra nguồn/đích, giao thức, cổng và route ở từng lớp |
| Gọi bằng IP được nhưng bằng tên thất bại | DNS hoặc service discovery chưa đúng phạm vi | Kiểm tra hostname, namespace, DNS resolver và registry |
| Service có nhưng không có endpoint | Selector không khớp label hoặc Pod chưa Ready | So sánh selector với label; kiểm tra readiness probe và EndpointSlice |
| Host truy cập được nhưng container khác không truy cập được | Client dùng sai hostname/cổng hoặc các container ở khác network | Kiểm tra network chung và gọi bằng tên service cùng cổng container |
| Container gọi được nhau nhưng Internet không truy cập được | Chưa publish cổng hoặc chưa cấu hình load balancer/Ingress | Kiểm tra điểm vào công khai, listener, DNS và firewall |
| Deploy mới làm một số request lỗi | Endpoint cũ còn trong cache, rollout hoặc health check chưa đồng bộ | Kiểm tra readiness, thời gian drain, DNS TTL, retry và khả năng kết nối lại của client |

Retry không nên được bật vô hạn. Với lỗi tạm thời, dùng timeout rõ ràng, số lần retry giới hạn và backoff có jitter; với thao tác không idempotent, phải có cơ chế tránh thực hiện lặp ngoài ý muốn. Những biện pháp này giúp service discovery và load balancing hoạt động ổn định khi endpoint thay đổi hoặc một node gặp sự cố.

## 8. Đánh đổi vận hành và chi phí

- **Publish cổng trực tiếp:** đơn giản cho môi trường thử nghiệm hoặc một dịch vụ nhỏ, nhưng cần quản lý cổng host, firewall và xung đột cổng. Không nên publish mọi cổng của mọi container.
- **Host network/hostPort:** có thể giảm một số bước chuyển tiếp, nhưng giảm cô lập và ràng buộc workload vào cổng của node. Điều này có thể hạn chế khả năng xếp lịch và mở rộng.
- **Service nội bộ:** giữ backend trong mạng riêng và giảm bề mặt tấn công. Cần quản lý DNS, policy và quan sát lưu lượng giữa các service.
- **Load balancer:** cung cấp điểm vào ổn định, health check và phân phối tải. Đổi lại, có thể phát sinh chi phí theo giờ, số rule hoặc lưu lượng; nhiều load balancer riêng lẻ cũng tăng số cấu hình phải vận hành.
- **Ingress/Gateway dùng chung:** gom nhiều route và chứng chỉ vào một điểm vào, có thể tiết kiệm tài nguyên. Cần thiết kế dự phòng, giới hạn tài nguyên, quyền thay đổi route và phạm vi ảnh hưởng khi controller lỗi.
- **Service registry/DNS:** giảm phụ thuộc vào IP tĩnh. Cần tính đến cache, TTL, thời gian cập nhật endpoint và khả năng chịu lỗi của thành phần DNS/registry.
- **Phân đoạn mạng:** giới hạn service nào được gọi service nào, giảm tác động khi một workload bị xâm nhập. Policy quá chặt hoặc thiếu kiểm thử có thể làm gián đoạn luồng hợp lệ.

Với hệ thống có nhiều service, nên chuẩn hóa tên service, cổng, giao thức, health endpoint và quy tắc truy cập. Ghi nhận các chỉ số như tỷ lệ kết nối lỗi, độ trễ, số kết nối đang mở, trạng thái endpoint và lỗi phân giải DNS. Khi sự cố xảy ra, các tín hiệu này giúp phân biệt lỗi ứng dụng với lỗi mạng hoặc discovery.

## 9. Bài tập thực hành

Triển khai một API và một database bằng Docker Compose, sau đó mô phỏng việc database được tạo lại:

1. Đặt API và database trong cùng một mạng riêng; chỉ publish cổng API.
2. Cấu hình API kết nối database bằng hostname `db` và cổng `5432`.
3. Xác nhận API phân giải được `db`, kết nối thành công và endpoint `/health` trả kết quả mong đợi.
4. Tạo lại container database, quan sát IP có thể thay đổi và xác nhận API vẫn kết nối bằng tên service.
5. Tạm thời đổi cổng database hoặc tên service để tạo lỗi; dùng log và lệnh kiểm tra ở phần trên để xác định nguyên nhân.
6. Khôi phục cấu hình, xác nhận kết nối và kiểm tra database không bị publish ra host.

Nếu có cluster Kubernetes, thực hiện thêm: tạo Service `ClusterIP` cho một Deployment, gọi Service bằng DNS trong cluster, tăng số replica và quan sát EndpointSlice thay đổi. Thử thay label của Pod để thấy Service mất endpoint, sau đó khôi phục label và xác nhận traffic hoạt động trở lại.

## 10. Checklist trước khi đưa lên môi trường cloud

- [ ] Ứng dụng lắng nghe đúng giao thức và cổng; bind vào interface phù hợp.
- [ ] Phân biệt rõ cổng container, cổng Service, cổng host và cổng load balancer.
- [ ] Chỉ publish điểm vào cần thiết; backend và database ở mạng riêng.
- [ ] Các service gọi nhau bằng tên ổn định thay vì IP container cố định.
- [ ] DNS/service registry hoạt động trong đúng namespace hoặc phạm vi mạng.
- [ ] Selector, endpoint và readiness health check khớp với cấu hình ứng dụng.
- [ ] Security group, firewall, NetworkPolicy và route chỉ cho phép lưu lượng cần thiết.
- [ ] Đã kiểm tra từ client nội bộ và từ điểm vào bên ngoài theo đúng đường đi thực tế.
- [ ] Ứng dụng có timeout, retry giới hạn và xử lý được khi endpoint thay đổi.
- [ ] Đã xem xét chi phí load balancer, lưu lượng mạng và mức độ phức tạp vận hành.

Một cấu hình mạng container tốt giúp dịch vụ có điểm truy cập ổn định dù container và địa chỉ IP thay đổi. Khi thiết kế đúng cổng, discovery, health check và ranh giới mạng, đội vận hành có thể triển khai phiên bản mới, mở rộng replica và xử lý lỗi node với ít thao tác thủ công hơn, đồng thời giữ lưu lượng ở đúng phạm vi cần thiết.
