# Network endpoint groups cho VM, GKE và serverless

Một doanh nghiệp triển khai dịch vụ đặt hàng trên **Cloud Run**, API danh mục sản phẩm trên **Google Kubernetes Engine (GKE)** và một ứng dụng cũ trên **Compute Engine VM**. Đội vận hành muốn dùng một tên miền HTTPS thống nhất, chuyển tiếp yêu cầu `/orders` tới Cloud Run, `/catalog` tới GKE và `/legacy` tới VM. Ngoài việc chọn loại load balancer và cấu hình TLS, cần xác định **backend thực sự nhận lưu lượng là gì** và cách Google Cloud biết endpoint nào đang phục vụ.

**Network endpoint group (NEG)** là tài nguyên mô tả một nhóm endpoint mạng hoặc dịch vụ có thể được load balancer sử dụng làm backend. Tùy loại NEG, endpoint có thể là **IP:port của VM**, **IP:port của Pod GKE** hoặc **tham chiếu tới dịch vụ serverless**. NEG giúp cấu hình backend ở mức cụ thể hơn so với việc chỉ quản lý danh sách VM theo instance group.

Bài học thuộc chương **Cân bằng tải và phân phối nội dung** của mô-đun **CLOUD_PROVIDERS_GCP**. Kiến thức về NEG nối liền tổ chức project, IAM, VPC và cách triển khai Compute Engine, GKE, Cloud Run với bảo vệ tài nguyên, tự động hóa phát hành, giám sát độ tin cậy và quản lý chi phí. Trọng tâm là **chọn và vận hành đúng NEG cho VM, GKE và serverless**; các loại NEG khác được giới thiệu để tránh nhầm lẫn.

## 1. Hiểu NEG trong kiến trúc load balancing

### 1.1. NEG nằm ở đâu?

Với một **Application Load Balancer** (cân bằng tải HTTP/HTTPS), luồng logic thường gồm:

~~~mermaid
flowchart LR
    U["Người dùng / client"] --> F["Frontend: IP, port, TLS"]
    F --> P["Target HTTP(S) proxy"]
    P --> M["URL map: host/path"]
    M --> B1["Backend service: orders"]
    M --> B2["Backend service: catalog"]
    M --> B3["Backend service: legacy"]
    B1 --> N1["Serverless NEG"]
    B2 --> N2["GKE zonal NEGs"]
    B3 --> N3["VM zonal NEGs"]
    N1 --> R["Cloud Run service"]
    N2 --> K["GKE Pods: IP:port"]
    N3 --> V["VM ứng dụng: IP:port"]
~~~

Đây là mô hình của một load balancer lớp ứng dụng. Thành phần và quy tắc của **proxy Network Load Balancer** hoặc **passthrough Network Load Balancer** có thể khác. Khi sử dụng ví dụ này, cần phân biệt năm vai trò:

| Thành phần | Trách nhiệm |
| --- | --- |
| **Frontend / forwarding rule** | Địa chỉ IP, cổng và phương án nhận traffic từ client. |
| **Target proxy và URL map** | Xử lý phiên HTTP(S), TLS và chọn backend service theo host/path đối với loại Application Load Balancer tương ứng. |
| **Backend service** | Tập hợp một hoặc nhiều backend, cấu hình phân phối traffic và những chính sách được loại load balancer hỗ trợ. |
| **NEG** | Xác định các endpoint hoặc dịch vụ mà backend service có thể gửi traffic đến. |
| **Endpoint/backend thực tế** | VM process, Pod container hoặc dịch vụ serverless nhận và xử lý yêu cầu. |

**NEG không phải một load balancer hoàn chỉnh.** Tạo NEG không tự cung cấp public IP, HTTPS certificate, URL map hoặc tuyến traffic từ Internet. Ngược lại, một backend service phải tham chiếu đến một NEG thích hợp và tương thích với loại load balancer đang dùng.

### 1.2. Vì sao không dùng instance group cho tất cả workload?

**Instance group** tập hợp VM để quản lý/cân bằng tải ở mức instance. **NEG** cho phép mô tả endpoint cụ thể hơn:

- Một VM có thể phục vụ nhiều process ở những cổng khác nhau; NEG kiểu `GCE_VM_IP_PORT` có thể nhắm tới IP:port cần dùng.
- Một node GKE có thể chạy nhiều Pod; với container-native load balancing, backend được biểu diễn bằng **địa chỉ IP và cổng của Pod**, thay vì buộc traffic đi qua cổng của node chỉ để tiếp cận Pod.
- Cloud Run không cung cấp cho người dùng một VM hoặc Pod IP cố định để tự đăng ký làm backend. **Serverless NEG** tham chiếu dịch vụ Cloud Run theo cơ chế được hỗ trợ.

Instance groups vẫn rất phù hợp cho nhiều mô hình Compute Engine, nhất là workload cần autohealing/autoscaling ở mức VM. NEG không tự thay thế **Managed Instance Group**, scheduler của Kubernetes hay autoscaling của Cloud Run; mỗi thành phần giải quyết một trách nhiệm khác nhau.

### 1.3. Các loại NEG thường gặp

| Loại NEG | Loại endpoint API tiêu biểu | Phạm vi | Trường hợp sử dụng |
| --- | --- | --- | --- |
| **Zonal NEG cho IP và port** | `GCE_VM_IP_PORT` | Zone | VM có ứng dụng ở cổng cụ thể; Pod GKE theo mô hình container-native. |
| **Zonal NEG chỉ có IP** | `GCE_VM_IP` | Zone | VM hoặc node GKE với các loại **passthrough Network Load Balancer** hỗ trợ. |
| **Serverless NEG** | `SERVERLESS` | Region | Cloud Run, Cloud Run functions, App Engine và một số nền tảng serverless khác theo loại Application Load Balancer được hỗ trợ. |
| **Hybrid connectivity NEG** | `NON_GCP_PRIVATE_IP_PORT` | Zone | Endpoint riêng ngoài Google Cloud, tiếp cận qua kết nối hybrid phù hợp. |
| **Internet NEG** | `INTERNET_IP_PORT`, `INTERNET_FQDN_PORT` | Global hoặc regional | Backend có IP/FQDN truy cập qua Internet. |
| **Private Service Connect NEG** | `PRIVATE_SERVICE_CONNECT` | Theo khả năng dịch vụ/loại LB | Backend đại diện cho dịch vụ được xuất bản qua Private Service Connect. |

**Không thể tùy ý dùng mọi loại NEG với mọi load balancer.** Chẳng hạn, serverless NEG dành cho những **Application Load Balancer** được hỗ trợ, không phải backend chung cho mọi Network Load Balancer. `GCE_VM_IP` và `GCE_VM_IP_PORT` cũng tương ứng với các loại load balancer và endpoint khác nhau. Khi thiết kế thực tế, luôn đối chiếu **bảng tương thích NEG–load balancer** của Google Cloud.

## 2. Zonal NEG cho Compute Engine VM

### 2.1. Endpoint IP:port là gì?

Giả sử một VM có địa chỉ IPv4 nội bộ `10.10.1.12` và ứng dụng lắng nghe trên cổng `8080`. Một endpoint kiểu `GCE_VM_IP_PORT` có thể được biểu diễn:

~~~text
NEG:       neg-legacy-a
Zone:      asia-southeast1-a
VPC:       retail-vpc
Subnet:    app-subnet
Instance:  legacy-vm-1
Endpoint:  10.10.1.12:8080
~~~

Một NEG kiểu này có thể chứa nhiều endpoint đủ điều kiện trong **cùng zone**, gắn với network/subnet phù hợp. Địa chỉ IP phải thuộc các địa chỉ được hỗ trợ trên interface của VM, chẳng hạn primary internal IPv4 hoặc alias IP theo quy định. Với cấu hình IPv6/dual stack, khả năng hỗ trợ còn phụ thuộc loại NEG, kiểu interface và giai đoạn phát hành; bài này minh họa bằng IPv4 để dễ kiểm tra.

**Cổng endpoint có ý nghĩa thực tế:** nếu process đang chạy ở `8080` nhưng NEG đăng ký `9090`, load balancer không thể phục vụ đúng ứng dụng chỉ nhờ VM đang `RUNNING`.

### 2.2. Zonal NEG `GCE_VM_IP` khác gì?

`GCE_VM_IP` biểu diễn VM qua địa chỉ IP mà **không có cổng endpoint**. Nó được sử dụng với những loại **passthrough Network Load Balancer** hỗ trợ và có cách xử lý gói tin khác với proxy/Application Load Balancer.

| Điểm so sánh | `GCE_VM_IP_PORT` | `GCE_VM_IP` |
| --- | --- | --- |
| Định danh endpoint | IP:port gắn với VM/interface phù hợp. | IP gắn với VM/interface phù hợp. |
| Tình huống điển hình | Application/proxy load balancing, VM apps và Pod GKE. | Passthrough network load balancing; một số dịch vụ GKE LoadBalancer sử dụng node IP. |
| Phân phối tới cổng ứng dụng | Cổng là một phần định nghĩa endpoint. | Cổng không nằm trong endpoint; phụ thuộc forwarding rule và mô hình passthrough. |
| Health checks | Backend service dùng cơ chế health check phù hợp. | Backend service dùng cơ chế health check phù hợp loại LB. |

Chọn loại NEG theo **kiến trúc traffic** cần dùng, không chỉ theo việc backend “có phải VM hay không”.

### 2.3. Ví dụ tạo NEG cho VM bằng gcloud

Giả sử project, VPC, subnet và VM đã tồn tại. Các lệnh có `create`/`update` dưới đây **thay đổi tài nguyên thật**, nên chỉ dùng trong môi trường được phép và sau khi kiểm tra thông số.

~~~bash
# Ví dụ cho Bash; thay tên và project bằng tài nguyên thực tế.
PROJECT_ID="retail-prod"
ZONE="asia-southeast1-a"
NETWORK="retail-vpc"
SUBNET="app-subnet"
NEG="neg-legacy-a"

# Tạo zonal NEG kiểu GCE_VM_IP_PORT; default-port là tùy chọn.
gcloud compute network-endpoint-groups create "$NEG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --network="$NETWORK" \
  --subnet="$SUBNET" \
  --default-port=8080

# Đăng ký endpoint của VM đã tồn tại trong cùng zone.
gcloud compute network-endpoint-groups update "$NEG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --add-endpoint="instance=legacy-vm-1,ip=10.10.1.12,port=8080"
~~~

Nếu cùng dịch vụ chạy ở nhiều zone, cần các **zonal NEGs tương ứng**. Việc chỉ tạo một NEG trong zone A không khiến load balancer tự phát hiện VM ở zone B. Với VM do Managed Instance Group quản lý, cần thiết kế cơ chế cập nhật membership khi VM được tạo/xóa; thao tác đăng ký thủ công không tự bảo đảm NEG luôn đồng bộ với mọi lần autoscale.

### 2.4. Xem NEG và endpoint

Các lệnh dưới đây là thao tác **đọc**:

~~~bash
gcloud compute network-endpoint-groups list \
  --project="$PROJECT_ID"

gcloud compute network-endpoint-groups describe "$NEG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

gcloud compute network-endpoint-groups list-network-endpoints "$NEG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"
~~~

Danh sách endpoint chỉ xác nhận sự hiện diện của cấu hình. Để kết luận endpoint **đang nhận được traffic**, cần xem backend service liên kết, health check, firewall, logs và kiểm thử HTTP/TCP thực tế.

### 2.5. Gắn NEG vào backend service

Ví dụ backend service dành cho **global external Application Load Balancer** đã tồn tại:

~~~bash
# Lệnh ghi: cập nhật backend service đã tồn tại.
gcloud compute backend-services add-backend legacy-backend \
  --project="$PROJECT_ID" \
  --global \
  --network-endpoint-group="$NEG" \
  --network-endpoint-group-zone="$ZONE"
~~~

Tùy loại Application Load Balancer, backend service có thể là **global hoặc regional** và có các cờ khác nhau. Phải chọn đúng loại load balancer, scope, health check và backend service. Không gắn `--global` cho backend service regional chỉ vì muốn cân bằng tải tới nhiều zone.

## 3. NEG cho GKE: container-native load balancing

### 3.1. Vì sao định tuyến trực tiếp tới Pod?

Trong Kubernetes, ứng dụng thường được truy cập qua **Service**, còn Pod có thể được tạo/xóa hoặc chuyển node khi rollout, scaling, rescheduling. Một mô hình cũ là load balancer hướng traffic tới **node**, rồi `NodePort`/kube-proxy chuyển tiếp tới Pod. Mô hình **container-native load balancing** cho phép những load balancer được hỗ trợ sử dụng **GCE_VM_IP_PORT zonal NEGs** với endpoint **Pod IP:container port**.

~~~mermaid
flowchart LR
    C["HTTPS client"] --> LB["Application Load Balancer"]
    LB --> BS["Backend service"]
    BS --> NEG1["Zonal NEG - zone A"]
    BS --> NEG2["Zonal NEG - zone B"]
    NEG1 --> P1["Pod A: 10.50.1.20:8080"]
    NEG1 --> P2["Pod B: 10.50.1.21:8080"]
    NEG2 --> P3["Pod C: 10.50.2.20:8080"]
    K["GKE NEG controller"] -. "Đồng bộ Pod endpoints" .-> NEG1
    K -.-> NEG2
~~~

Kết quả: load balancer có thể kiểm tra sức khỏe và gửi traffic tới backend ở **mức Pod**, thay vì chỉ thấy node đang sống. Điều này hữu ích khi một node có nhiều ứng dụng hoặc khi cần phản ánh tình trạng từng Pod trong quá trình phát hành.

GKE cũng có mô hình **`LoadBalancer` Service** dùng zonal `GCE_VM_IP` NEGs với **node VM** làm endpoint trong các trường hợp passthrough được hỗ trợ. Vì vậy, nói “mọi NEG của GKE đều trỏ thẳng tới Pod” là không chính xác. Cần xác định controller, loại Service, loại load balancer và kiểu NEG được sử dụng.

### 3.2. Ai quản lý danh sách Pod endpoints?

Khi sử dụng **GKE Ingress**, **GKE Gateway controller** hoặc **standalone NEGs** theo cấu hình hỗ trợ, **GKE NEG controller** tạo/sửa các NEG và cập nhật endpoint khi Pod thay đổi. Người vận hành cần quản lý:

- `Deployment` hoặc workload resource, labels, selectors và cổng thực tế của Pod.
- `Service` cùng chú thích (annotation) hoặc cấu hình mà controller yêu cầu.
- `Ingress`, `Gateway`, HTTPRoute hoặc backend service được quản lý tương ứng.
- Probe, readiness, kết nối VPC, firewall và quyền của controller.

**Không chỉnh membership của NEG do GKE controller sở hữu bằng tay** nếu muốn GKE tiếp tục đồng bộ đúng. Thay đổi thủ công có thể bị ghi đè hoặc gây sai lệch khi controller reconcile.

### 3.3. Ví dụ standalone NEG qua Kubernetes Service

Ví dụ dưới đây tạo **manifest mô tả** một Service có annotation yêu cầu GKE tạo zonal NEGs cho cổng `80`. Các Pod được chọn bởi `app: catalog-api` phải lắng nghe tại cổng `8080`. Manifest này chỉ áp dụng trong một GKE cluster đủ điều kiện, đã có workload phù hợp.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: retail
  annotations:
    cloud.google.com/neg: '{"exposed_ports":{"80":{}}}'
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: 8080
~~~

Với **standalone NEGs**, bạn tự quản lý phần cấu hình load balancer hoặc công cụ tích hợp tham chiếu NEG, tùy mô hình triển khai. Nếu cluster sử dụng **GKE Ingress** và annotation tương ứng, controller có thể tự tạo/quản lý các thành phần load balancer. Không kết hợp hai controller quản lý cùng một backend mà chưa xác định rõ **bên nào là chủ cấu hình**.

Trong một số mô hình Ingress, annotation:

~~~yaml
metadata:
  annotations:
    cloud.google.com/neg: '{"ingress":true}'
~~~

cho biết các NEGs sẽ được dùng cho backend Ingress theo điều kiện của GKE. Với **Gateway API**, controller GKE cũng có thể tạo NEGs cho Service được tham chiếu. Cấu hình cụ thể thay đổi theo cluster, version và loại load balancer; ví dụ trên không phải thay thế cho tài liệu tương thích của từng controller.

### 3.4. Kiểm tra trạng thái NEG do GKE quản lý

~~~bash
# Các lệnh đọc: trong kubeconfig/context của đúng GKE cluster.
kubectl -n retail get service catalog-api -o yaml
kubectl -n retail describe service catalog-api
kubectl -n retail get endpointslices -l kubernetes.io/service-name=catalog-api

# Khi cluster/controller có tài nguyên ServiceNetworkEndpointGroup:
kubectl -n retail get svcneg

# Từ môi trường có quyền đọc Compute API:
gcloud compute network-endpoint-groups list --project=retail-prod
~~~

Trong metadata của Service, hãy kiểm tra annotation **`cloud.google.com/neg-status`**: nó cho biết tên các NEGs được controller tạo và những zone tương ứng. Tên NEG tự sinh có thể dài và không giống tên Service; không tự đoán để xóa hoặc sửa nhầm NEG.

Kiểm tra thêm số Pod `Ready`, selector, port mapping và các sự kiện controller. **Kubernetes endpoints tồn tại** không tự bảo đảm load balancer coi chúng `HEALTHY`: cơ chế kiểm tra sức khỏe của LB và readiness của Pod là hai khía cạnh cần đối chiếu.

### 3.5. Health check, readiness và rolling deployment

Để ứng dụng nhận traffic chính xác:

1. Cấu hình `readinessProbe` của Pod phản ánh khi ứng dụng thực sự có thể phục vụ.
2. Chọn health check đúng **protocol, path, port** trên backend service của load balancer.
3. Đảm bảo chính sách firewall cho phép nguồn traffic/health check của **đúng loại load balancer** tới Pod IP:port trong mạng VPC.
4. Theo dõi cơ chế **NEG readiness gates** khi controller sử dụng để đồng bộ trạng thái sẵn sàng của Pod với tình trạng LB; không giả định mọi mô hình standalone đều có cùng hành vi.
5. Kiểm thử rolling update, scale-up/down, Pod termination và connection draining.

Trong một số mô hình global external Application Load Balancer, các dải health check thường gặp là `35.191.0.0/16` và `130.211.0.0/22`; tuy nhiên **không sao chép các dải này cho mọi load balancer**. Với load balancer dùng Envoy proxy trong region, đường đến backend còn liên quan tới **proxy-only subnet**. Luôn kiểm tra tài liệu firewall/health check của loại LB đã chọn.

## 4. Serverless NEG cho Cloud Run và các dịch vụ được hỗ trợ

### 4.1. Serverless NEG không chứa IP:port

Khác với VM và Pod, Cloud Run có hạ tầng tự quản lý, có thể scale thay đổi theo lưu lượng. Một **serverless NEG** có kiểu endpoint `SERVERLESS`, tham chiếu tới một tài nguyên serverless hoặc **URL mask** được hỗ trợ. Nó **không có danh sách IP:port** để quản trị viên tự thêm hay xóa.

~~~mermaid
flowchart LR
    C["Client"] --> LB["Application Load Balancer HTTPS"]
    LB --> BS["Backend service: orders"]
    BS --> SN["Serverless NEG (regional)"]
    SN --> RUN["Cloud Run service: orders-api"]
    RUN --> REV["Revision / instances do Cloud Run quản lý"]
~~~

Những điểm thiết kế bắt buộc:

- **Serverless NEG có phạm vi regional**, và tài nguyên Cloud Run/App Engine/functions/API Gateway được trỏ tới phải thuộc vùng phù hợp theo quy định loại dịch vụ.
- Tài nguyên serverless backend và NEG thông thường phải ở **cùng project** theo giới hạn của serverless NEG.
- Một serverless NEG biểu diễn **một endpoint logic** (tài nguyên hoặc URL mask), không phải nhiều VM hoặc Pod.
- Backend service có thể dùng nhiều serverless NEGs thuộc những region khác nhau trong những topology load balancer được hỗ trợ; việc phân phối và failover phụ thuộc loại LB và cấu hình thực tế.
- Serverless NEG dùng với **Application Load Balancer** được hỗ trợ, không dùng làm backend cho passthrough/proxy Network Load Balancer.

Ngoài Cloud Run còn có các biến thể dùng cho **Cloud Run functions, App Engine** và **API Gateway**, nhưng phạm vi hỗ trợ theo từng loại Application Load Balancer không hoàn toàn giống nhau. Khi xây hệ thống mới, xác định chính xác sản phẩm, thế hệ runtime, khu vực và loại LB trước khi chọn.

### 4.2. Tạo serverless NEG tham chiếu Cloud Run

Giả sử Cloud Run service `orders-api` đã được triển khai tại `asia-southeast1` trong project `retail-prod`:

~~~bash
PROJECT_ID="retail-prod"
REGION="asia-southeast1"

# Đọc service đã tồn tại.
gcloud run services describe orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml"

# Lệnh ghi: tạo regional serverless NEG tham chiếu service.
gcloud compute network-endpoint-groups create orders-run-neg \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --network-endpoint-type=serverless \
  --cloud-run-service=orders-api

# Đọc lại cấu hình NEG.
gcloud compute network-endpoint-groups describe orders-run-neg \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml"
~~~

Lệnh tạo NEG **không triển khai Cloud Run service** và không tự tạo HTTPS frontend. Nếu service chưa tồn tại, đặt sai region/project hoặc không thuộc nhóm tài nguyên được hỗ trợ, cấu hình sẽ không đạt mục đích.

### 4.3. Gắn vào backend service tương thích

Ví dụ xây một **global external Application Load Balancer** với chế độ `EXTERNAL_MANAGED`, trong đó backend service `orders-run-backend` sử dụng một serverless NEG:

~~~bash
# Lệnh ghi: tạo global backend service kiểu phù hợp.
gcloud compute backend-services create orders-run-backend \
  --project="$PROJECT_ID" \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --protocol=HTTP

# Lệnh ghi: gắn regional serverless NEG vào backend service.
gcloud compute backend-services add-backend orders-run-backend \
  --project="$PROJECT_ID" \
  --global \
  --network-endpoint-group=orders-run-neg \
  --network-endpoint-group-region="$REGION"

# Lệnh đọc: xác nhận backend service.
gcloud compute backend-services describe orders-run-backend \
  --project="$PROJECT_ID" \
  --global
~~~

Để người dùng truy cập qua domain thực, đội hạ tầng **còn phải** cấu hình URL map, target HTTPS proxy, certificate, forwarding rule, DNS và chính sách liên quan. Ví dụ chỉ minh họa phần backend. Với **regional external** hoặc **internal Application Load Balancer**, cấu hình backend service và phạm vi `--region` phải theo hướng dẫn riêng.

### 4.4. Health check của serverless NEG khác VM/GKE

Điểm dễ nhầm: backend service với **serverless NEG không hỗ trợ health check truyền thống như zonal NEG** và không có `port` endpoint để gửi probe. Các tham số balancing mode kiểu `RATE`, `UTILIZATION` hoặc `CONNECTION` cũng không có ý nghĩa như với backend VM.

Tuy nhiên, một số loại load balancer có khả năng **outlier detection** theo phản hồi HTTP hoặc **Cloud Run service health** để hỗ trợ phát hiện và tránh serverless backend đang lỗi. Tính năng này có điều kiện về loại LB, region và cấu hình; **không đồng nghĩa có health check thông thường gắn vào serverless backend service**.

Khi backend serverless trả `5xx`, cần kiểm tra **Cloud Run request logs**, revision, concurrency, timeout, quota, cold starts và phụ thuộc dữ liệu, không chỉ xem NEG có tồn tại hay không.

### 4.5. Ingress và xác thực

Đặt load balancer trước Cloud Run mang lại khả năng dùng domain chung, TLS, URL routing và những tính năng như **Cloud Armor** hoặc **Cloud CDN** khi loại LB/backend cho phép. Nhưng **load balancer không tự hoàn tất xác thực người dùng cuối**. Nếu Cloud Run yêu cầu xác thực, phải thiết kế cách client được ủy quyền, ví dụ **Identity-Aware Proxy (IAP)** ở topology được hỗ trợ hoặc cơ chế xác thực ứng dụng thích hợp.

Với Cloud Run có frontend qua external Application Load Balancer, nên xem xét ingress mode **`internal-and-cloud-load-balancing`** nếu phù hợp, để giới hạn đường truy cập trực tiếp vượt qua load balancer. Cấu hình ingress, IAM Invoker, domain mapping và giải pháp IAP phải tương thích; không chỉ bật một tùy chọn rồi cho rằng toàn bộ yêu cầu đã được bảo vệ.

Nếu dự kiến dùng **Cloud CDN và IAP trên cùng backend service**, cần kiểm tra giới hạn tương thích hiện hành; với cấu hình phổ biến chúng không thể bật đồng thời trên cùng backend service.

## 5. Đặt ba loại workload sau một tên miền

### 5.1. Thiết kế theo route

Giả sử người dùng truy cập `https://shop.example.com`:

| Host/path | Backend service | NEG và đích | Chủ sở hữu |
| --- | --- | --- | --- |
| `/orders/*` | `orders-run-backend` | Regional serverless NEG → Cloud Run `orders-api`. | Nhóm backend đơn hàng. |
| `/catalog/*` | `catalog-gke-backend` | Zonal NEGs → Pod GKE `catalog-api`. | Nhóm danh mục sản phẩm. |
| `/legacy/*` | `legacy-vm-backend` | Zonal NEG → VM IP:port. | Nhóm bảo trì ứng dụng cũ. |

URL map của Application Load Balancer phân loại yêu cầu tới **ba backend services riêng**. Mỗi backend service sử dụng NEG hợp lệ theo chính sách của chính loại backend đó.

**Không gộp Cloud Run serverless NEG và GKE zonal NEG trong cùng một backend service** để mong load balancer tự trộn traffic theo tỷ lệ: sự kết hợp này không được hỗ trợ. Có thể phân luồng bằng URL map tới những backend services tương ứng và sử dụng các tính năng traffic management được loại load balancer hỗ trợ nếu có nhu cầu triển khai đặc biệt.

### 5.2. Giới hạn khác nhau giữa “routing” và “capacity”

Khi client gửi `/orders/123`, URL map chọn `orders-run-backend`; sau đó backend service/NEG chuyển yêu cầu tới Cloud Run theo cơ chế serverless. Cách Cloud Run mở rộng instances là trách nhiệm của nền tảng Cloud Run, chịu giới hạn quota, concurrency và cấu hình runtime.

Với `/catalog/123`, URL map chọn `catalog-gke-backend`, backend service sử dụng các zonal NEGs chứa Pod IP:port; trạng thái health check và endpoint membership ảnh hưởng tới lựa chọn Pod nhận yêu cầu. Khi số replica thay đổi, GKE controller cập nhật NEGs.

Với `/legacy/report`, URL map chọn backend VM; nếu VM hoặc application process không đáp ứng health check, backend tương ứng có thể bị coi là không khỏe theo quy tắc LB. **NEG không tự khởi động lại VM**; autohealing của Managed Instance Group hoặc cơ chế vận hành riêng mới đảm nhiệm việc đó.

### 5.3. Các câu hỏi cần trả lời trước khi triển khai

1. Client ở Internet, VPC nội bộ hay cả hai? Chọn **external/internal Application Load Balancer**, **global/regional/cross-region** và network tier phù hợp.
2. Có cần HTTP routing theo path/host hay cân bằng tải TCP/UDP? Nếu chỉ cần passthrough L4, tập loại NEG tương thích sẽ khác.
3. Workload nằm ở zone/region nào? Có cần đa vùng, DR hoặc chuyển traffic giữa nhiều region không?
4. Backend do ai quản lý: VM team, GKE controller, Cloud Run hay IaC? Tránh hai công cụ đồng thời sửa cùng một tài nguyên.
5. Các route có cần header/path rewrite, TLS end-to-end, session affinity, caching, WAF hoặc IAP không? Kiểm tra hỗ trợ với đúng backend.
6. Quy trình rollback có xử lý thay đổi route và endpoint membership hay chỉ rollback image/revision?

## 6. Health checks và vòng đời endpoint

### 6.1. Kiểm tra tình trạng backend

| Backend | Cơ chế theo dõi phù hợp | Rủi ro thường gặp |
| --- | --- | --- |
| **VM zonal NEG `GCE_VM_IP_PORT`** | Health check của backend service tới IP:port, route và firewall. | VM chạy nhưng process không nghe cổng, health check path sai. |
| **GKE Pod zonal NEG** | Health check LB + readiness/lifecycle của Kubernetes + đồng bộ NEG controller. | Pod đổi IP, readiness chưa đạt, endpoint cũ còn trong NEG. |
| **Serverless NEG** | Quan sát Cloud Run/app logs và khả năng service health/outlier detection khi có hỗ trợ. | Không có health check NEG truyền thống; revision trả lỗi vẫn có thể nhận traffic. |

Ví dụ một **HTTP health check** cho zonal NEG sử dụng **serving port** được endpoint khai báo:

~~~bash
# Lệnh ghi: tạo health check; chỉ dùng cho backend tương thích.
gcloud compute health-checks create http hc-catalog \
  --project=retail-prod \
  --request-path=/healthz \
  --use-serving-port
~~~

Health check còn phải được gắn vào **backend service** phù hợp. Endpoint phải trả mã phản hồi và nội dung theo quy định của health check; route và firewall phải cho phép nguồn kiểm tra đi tới endpoint. Không áp dụng ví dụ này cho backend service serverless NEG.

### 6.2. Connection draining và thay đổi phiên bản

Với zonal NEGs, khi endpoint bị xóa khỏi backend, kết nối đang mở có thể chịu ảnh hưởng của **connection draining** và các giới hạn của backend service. Điều này đặc biệt quan trọng khi:

- GKE rolling deployment thay Pod IP:port.
- VM được loại khỏi pool để cập nhật phần mềm.
- Cấu hình port hoặc network interface thay đổi.
- Người vận hành di chuyển traffic giữa zone hoặc backend.

Thiết kế ứng dụng cần timeout và retry phù hợp, xử lý idempotency cho yêu cầu ghi dữ liệu và thực hiện graceful shutdown. Một backend được đánh dấu khỏe không bảo đảm mọi giao dịch dài đều có thể kết thúc nếu endpoint đang bị chấm dứt.

### 6.3. Tách autoscaling khỏi NEG

**NEG là biểu diễn backend**, không phải bộ điều khiển capacity:

- **Compute Engine:** Managed Instance Group có thể tự mở rộng/quản lý VM; membership NEG do công cụ và kiến trúc tương ứng quản lý.
- **GKE:** Horizontal Pod Autoscaler hoặc các cơ chế autoscaling khác thay đổi số Pod; controller đồng bộ NEG.
- **Cloud Run:** nền tảng tự mở rộng theo cấu hình và nhu cầu; serverless NEG chỉ trỏ tới service.

Nếu tất cả endpoints của một zonal NEG mất health hoặc không còn backend đủ điều kiện, traffic có thể thất bại dù load balancer vẫn có frontend. Tương tự, một serverless NEG hợp lệ không ngăn Cloud Run hết quota hoặc backend database quá tải.

## 7. Bảo mật và giới hạn truy cập

### 7.1. Mạng và firewall

Đối với **VM/GKE zonal NEGs**, hãy xác định loại load balancer sử dụng Google Front Ends hay Envoy proxy, rồi áp dụng đúng firewall rules và vùng mạng:

- Cho phép traffic tới endpoint theo protocol/port cần thiết.
- Cho phép các dải health checker hoặc proxy-only subnet đúng với loại LB và phạm vi triển khai.
- Hạn chế nguồn truy cập trực tiếp tới VM/backend nếu kiến trúc yêu cầu chỉ nhận traffic qua load balancer.
- Với GKE, đối chiếu thêm Kubernetes NetworkPolicy (nếu áp dụng), Pod IP range, VPC routes và cấu hình cluster.

Chỉ tạo NEG không tự mở firewall. Ngược lại, mở quá rộng cổng NodePort/Pod/VM có thể tạo đường truy cập ngoài chính sách load balancer.

### 7.2. IAM và danh tính ứng dụng

**IAM cho quản trị load balancer/NEG** khác **IAM của workload**:

- Pipeline cần đủ quyền tạo/sửa backend service, URL map và NEG ở đúng project/tài nguyên, nhưng không cần role Owner rộng cho toàn organization.
- GKE controller phải được phép quản lý NEGs và backend resources theo kiến trúc triển khai; người dùng không tự sửa NEG do controller sở hữu.
- Cloud Run runtime service account có quyền gọi Cloud SQL, Cloud Storage hoặc Secret Manager theo nhu cầu nghiệp vụ; role quản lý serverless NEG không tự cấp quyền dữ liệu này.
- Người gọi endpoint Cloud Run cần cơ chế xác thực, ingress và chính sách ứng dụng thích hợp; load balancer không mặc nhiên thay thế mọi kiểm tra quyền.

Nếu dùng **Shared VPC** hoặc **cross-project service referencing** ở một số Application Load Balancer, cần kiểm tra các giới hạn và IAM cụ thể. Việc backend ở project khác không đồng nghĩa được tự động phép sử dụng chỉ vì cả hai project thuộc cùng organization.

### 7.3. Cloud Armor, IAP và CDN

Một số Application Load Balancer với NEG backend có thể kết hợp:

| Thành phần | Vai trò | Điều cần kiểm tra |
| --- | --- | --- |
| **Cloud Armor** | Chính sách bảo vệ tại lớp HTTP/HTTPS hoặc hỗ trợ chặn traffic không mong muốn. | Loại LB/backend, điểm gắn policy và khả năng client bypass trực tiếp vào backend. |
| **IAP** | Kiểm soát người dùng truy cập ứng dụng theo danh tính trong topology được hỗ trợ. | Khả năng hỗ trợ backend, OAuth client và tương thích với Cloud CDN. |
| **Cloud CDN** | Cache nội dung phù hợp gần người dùng khi backend/LB hỗ trợ. | Header cache, dữ liệu cá nhân, thời hạn cache, purge và chi phí cache/egress. |

Không cache nhầm các phản hồi chứa thông tin đơn hàng riêng của người dùng. **Không gắn CDN là mặc nhiên an toàn**, cũng không coi Cloud Armor là thay thế cho IAM, session handling và kiểm tra authorization của ứng dụng.

## 8. Giám sát, xử lý lỗi và chi phí

### 8.1. Chẩn đoán theo từng lớp

Khi người dùng gặp `502`, `503` hoặc độ trễ cao, hãy kiểm tra từ ngoài vào trong:

1. **Frontend:** IP/DNS, certificate/TLS, forwarding rule, listener.
2. **Routing:** host/path rules và URL map có chọn đúng backend service không?
3. **Backend service:** có gắn NEG đúng loại, đúng scope, đúng region/zone không?
4. **NEG:** VM/GKE endpoints có được đăng ký/sync chính xác? Với serverless, NEG có trỏ đúng Cloud Run service?
5. **Health/availability:** VM/GKE có khỏe không? Cloud Run có lỗi revision/concurrency/quota không?
6. **Networking và quyền:** route, firewall, ingress, IAM, IAP hoặc Cloud Armor có chặn request không?
7. **Ứng dụng:** code, database, dependency, timeout, exception và logs cụ thể.

**HTTP 403** thường gợi ý vấn đề authorization, ingress, IAP hoặc security policy; **HTTP 404** có thể đến từ URL map/path hoặc ứng dụng; **HTTP 502/503** có thể liên quan backend không khỏe, timeout hoặc lỗi kết nối. Không dùng mã HTTP đơn lẻ để khẳng định chính xác nguyên nhân.

### 8.2. Lệnh kiểm tra read-only

~~~bash
PROJECT_ID="retail-prod"

# Kiểm kê các NEGs và kiểu/scope.
gcloud compute network-endpoint-groups list \
  --project="$PROJECT_ID"

# Xem zonal NEG dành cho VM hoặc GKE.
gcloud compute network-endpoint-groups describe neg-legacy-a \
  --project="$PROJECT_ID" \
  --zone=asia-southeast1-a

# Với zonal NEG, xem các IP:port hiện đã đăng ký.
gcloud compute network-endpoint-groups list-network-endpoints neg-legacy-a \
  --project="$PROJECT_ID" \
  --zone=asia-southeast1-a

# Xem serverless NEG theo region.
gcloud compute network-endpoint-groups describe orders-run-neg \
  --project="$PROJECT_ID" \
  --region=asia-southeast1

# Xem global backend service và NEG đã gắn.
gcloud compute backend-services describe orders-run-backend \
  --project="$PROJECT_ID" \
  --global
~~~

Để xem health của các backend tương thích, có thể dùng:

~~~bash
# Ví dụ: backend service cho zonal NEGs đã được tạo với scope global.
gcloud compute backend-services get-health legacy-backend \
  --project=retail-prod \
  --global
~~~

Lệnh này phải được gọi với **backend service đã tồn tại**, loại load balancer tương thích và quyền đọc phù hợp. Với serverless NEG, không dựa vào `get-health` như cách kiểm tra health của VM/Pod; xem Cloud Run metrics, logs và tính năng service health/outlier detection được hỗ trợ.

### 8.3. Dữ liệu cần quan sát

| Tầng | Tín hiệu nên theo dõi | Câu hỏi vận hành |
| --- | --- | --- |
| Load balancer | Requests, lỗi 4xx/5xx, latency, backend response status. | Lỗi xảy ra ở frontend, proxy hay backend? |
| Zonal NEG/backend | Số endpoints, trạng thái health, thay đổi membership. | Có đủ endpoint khỏe ở các zone không? |
| GKE | Pod readiness, restart, events, NEG sync status, rollout. | Có lệch giữa Pods và endpoints trong NEG không? |
| Cloud Run | Requests, latency, 5xx, concurrency, instances, revision logs. | Dịch vụ có đủ capacity, timeout hay phụ thuộc gây lỗi? |
| Ứng dụng | SLI đầu cuối như tỷ lệ tạo đơn hàng thành công. | Người dùng có đang hoàn thành hành trình nghiệp vụ không? |

Chỉ số `load balancer up` chưa đủ để kết luận hệ thống đáp ứng SLO. Một frontend vẫn phục vụ TLS trong khi database không ghi được đơn hàng vẫn là sự cố nghiệp vụ. Hãy kết hợp Cloud Monitoring, Cloud Logging, Cloud Trace và log ứng dụng theo nhu cầu và phạm vi hỗ trợ.

### 8.4. Chi phí và năng lực mở rộng

Không nên xem “NEG” là một cách loại bỏ chi phí load balancing. Các chi phí có thể liên quan:

- Quy tắc/giờ sử dụng load balancer và lượng dữ liệu xử lý theo bảng giá hiện hành.
- Compute Engine VM, GKE nodes/Pods và cấu hình autoscaling.
- Cloud Run requests, CPU/memory, concurrency và thời gian thực thi.
- Cloud CDN cache/egress, Cloud Armor hoặc IAP khi được sử dụng.
- Lưu lượng liên zone/region, outbound data transfer, logging và monitoring.

Theo tài liệu của GKE standalone NEGs, việc sử dụng NEGs riêng **không tự tạo một khoản phí NEG bổ sung** trong mô hình được mô tả, nhưng backend, network và load balancer vẫn có chi phí. Khi ước tính cho sản xuất, hãy dùng bảng giá Google Cloud đang hiệu lực, Billing reports và dữ liệu request/traffic thực tế.

## 9. Bảng lựa chọn nhanh

| Tình huống | NEG nên khảo sát | Cấu hình cần đi cùng |
| --- | --- | --- |
| HTTP ứng dụng trên VM, port `8080`, cần HTTPS và path routing. | Zonal `GCE_VM_IP_PORT`. | Application LB, backend service, health check, firewall, membership cập nhật. |
| Passthrough TCP/UDP tới VM/node ở mô hình được hỗ trợ. | Zonal `GCE_VM_IP`. | Đúng passthrough Network LB và các giới hạn tương thích. |
| API chạy trên Pod GKE, muốn LB tới từng Pod. | GKE-managed `GCE_VM_IP_PORT` zonal NEGs. | GKE Ingress/Gateway/standalone controller, Service, health/readiness, backend service. |
| Cloud Run cần domain chung, HTTPS và routing. | Regional `SERVERLESS`. | Application LB hỗ trợ, backend service, ingress/IAP/WAF khi cần. |
| Ứng dụng ở on-premises qua VPN/Interconnect. | Hybrid `NON_GCP_PRIVATE_IP_PORT`. | Hybrid connectivity, DNS, route, health check và firewall phù hợp. |
| Public backend ngoài Google Cloud theo IP/FQDN. | Internet NEG phù hợp. | Loại LB hỗ trợ, bảo mật outbound và rủi ro phụ thuộc bên ngoài. |

Chọn NEG là **một bước trong quyết định kiến trúc**, không phải lựa chọn độc lập. Backend protocol, phạm vi global/regional, VPC, security policy, health check và đội sở hữu workload quyết định giải pháp có vận hành được hay không.

## 10. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| NEG tồn tại nhưng không có endpoints. | VM chưa được thêm; GKE selector sai; Pod chưa được controller đồng bộ. | `list-network-endpoints`, Service labels/annotations và GKE events. |
| NEG GKE không được tạo. | Annotation JSON sai, cổng Service không khớp, cluster/controller không hỗ trợ hoặc lỗi quyền. | `kubectl describe svc`, `neg-status`, `svcneg` và events. |
| VM zonal NEG trả backend unhealthy. | Sai IP/port, process không nghe, health path sai, firewall chặn check. | Xem endpoint, health check, firewall và log VM. |
| GKE Pods Ready nhưng LB trả 502/503. | LB health khác readiness, NEG chưa sync, backend service thiếu/cấu hình sai. | Health từ backend service, Pod readiness gate, NEG status. |
| Cloud Run NEG không hoạt động. | Sai project/region, service không tồn tại, backend type/LB không tương thích. | `describe` serverless NEG, Cloud Run service và backend service. |
| Cloud Run trả nhiều 5xx nhưng NEG không báo unhealthy. | Serverless NEG không dùng health check truyền thống; app/revision đang lỗi. | Cloud Run logs, metrics; đánh giá service health/outlier detection nếu được hỗ trợ. |
| `/catalog` đi vào `/orders`. | URL map có host/path rule hoặc priority sai. | Xem URL map và cấu hình backend dịch vụ tương ứng. |
| 403 từ domain LB hoặc URL Cloud Run. | IAM, ingress, IAP, Cloud Armor hoặc application authorization. | Đối chiếu quyền, ingress, logs và security policy. |
| Lỗi xuất hiện sau rolling update GKE. | Pod termination/draining, health transition, thiếu capacity. | Theo dõi rollout, NEG sync, request logs và graceful shutdown. |
| Chi phí tăng sau khi dùng LB. | Lưu lượng xử lý/egress, vùng, cache, logging hoặc backend autoscaling. | Cloud Billing, traffic metrics và cấu hình networking. |

## 11. Bài tập thực hành

### Bài 1 — Chọn NEG đúng loại

Một ứng dụng có ba thành phần:

1. VM Compute Engine chạy HTTP trên `10.10.1.12:8080`.
2. GKE Service với ba Pod `10.50.1.20:8080`, `10.50.1.21:8080`, `10.50.2.20:8080`.
3. Cloud Run service `orders-api` ở `asia-southeast1`.

**Câu hỏi:** chọn loại NEG, phạm vi zone/region và phương án quản lý endpoint cho từng thành phần.

**Gợi ý:** VM dùng zonal `GCE_VM_IP_PORT` với membership theo quy trình quản lý; GKE container-native dùng GKE-managed zonal `GCE_VM_IP_PORT` và controller đồng bộ Pods; Cloud Run dùng regional `SERVERLESS` tham chiếu service, không có danh sách Pod/VM IP.

### Bài 2 — Phân tích luồng request

Người dùng truy cập `https://shop.example.com/catalog/42`. Hãy mô tả thứ tự **frontend → HTTPS proxy → URL map → backend service → zonal NEG → Pod**. Một lỗi ở URL map gây ra hậu quả gì dù Pod vẫn khỏe?

**Gợi ý:** request có thể bị đưa sang backend service sai, trả 404/403 hoặc nội dung không mong đợi. Vì vậy cần kiểm thử từng path/host sau mỗi lần thay cấu hình.

### Bài 3 — Chẩn đoán 502

GKE Deployment có 4 Pods `Ready`, Service có annotation NEG hợp lệ, nhưng load balancer trả `502`.

**Hãy kiểm tra theo thứ tự:** controller có tạo NEGs không; danh sách endpoint có khớp Pod IP:port không; backend service có gắn đúng NEGs không; health check path/port và firewall có đúng không; ứng dụng có trả HTTP thành công khi gọi trực tiếp ở mạng nội bộ không.

### Bài 4 — Phân quyền

Pipeline của nhóm giao diện cần thay URL map của load balancer nhưng không cần đọc dữ liệu đơn hàng trong Cloud SQL. Hãy giải thích vì sao role quản trị LB và role truy cập dữ liệu phải tách riêng; xác định người phê duyệt thay đổi định tuyến production.

### Bài 5 — Thiết kế rollback

Nhóm sản phẩm triển khai revision Cloud Run mới và đồng thời rollout Pods GKE. Khi SLI `order_success_rate` giảm, hãy đề xuất phương án rollback riêng cho **Cloud Run revision**, **GKE Deployment** và **URL map/backend routing**. Cần đo metric nào để xác nhận người dùng thực sự phục hồi?

## 12. Checklist trước production

| Hạng mục | Tiêu chí kiểm tra |
| --- | --- |
| **Loại LB** | Chọn đúng Application/Network, external/internal, global/regional theo nhu cầu. |
| **NEG type** | Endpoint `GCE_VM_IP`, `GCE_VM_IP_PORT` hay `SERVERLESS` phù hợp loại LB. |
| **Ownership** | Xác định ai tạo/sửa NEG: người vận hành, GKE controller hay IaC. |
| **Định danh endpoint** | VM IP:port đúng zone/subnet; Pod IP:port đúng Service; Cloud Run đúng project/region. |
| **Backend service** | Gắn NEG đúng scope, không trộn kiểu backend không hỗ trợ. |
| **Health/availability** | VM/GKE health checks và readiness; serverless metrics/service health theo hỗ trợ. |
| **Network security** | Firewall, proxy/health-check traffic, ingress và khả năng truy cập trực tiếp backend. |
| **IAM** | Danh tính triển khai, controller và runtime có quyền tối thiểu. |
| **TLS và routing** | Certificate, DNS, host/path rules, URL map và backend mapping đúng. |
| **Deployment** | Có kịch bản rollout, draining, canary/rollback hoặc điều phối traffic tương thích. |
| **Observability** | Request logs, 4xx/5xx, backend health, GKE events, Cloud Run logs và SLO đầu cuối. |
| **Cost & scale** | Có ước tính LB/egress/backend capacity, quota và cảnh báo ngân sách. |

## 13. Tài liệu chính thức và điều cần ghi nhớ

Các loại NEG, phạm vi hỗ trợ từng Application/Network Load Balancer và tính năng như outlier detection hoặc service health có thể thay đổi. Khi triển khai môi trường thật, đối chiếu tài liệu hiện hành:

- [Network endpoint groups overview](https://cloud.google.com/load-balancing/docs/negs)
- [Zonal network endpoint groups overview](https://cloud.google.com/load-balancing/docs/negs/zonal-neg-concepts)
- [Set up zonal NEGs](https://cloud.google.com/load-balancing/docs/negs/setting-up-zonal-negs)
- [Container-native load balancing with standalone NEGs on GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/standalone-neg)
- [GKE container-native load balancing](https://cloud.google.com/kubernetes-engine/docs/concepts/container-native-load-balancing)
- [Serverless NEGs overview](https://cloud.google.com/load-balancing/docs/negs/serverless-neg-concepts)
- [Set up external Application Load Balancer with serverless backend](https://cloud.google.com/load-balancing/docs/https/setting-up-https-serverless)
- [Load balancing health checks](https://cloud.google.com/load-balancing/docs/health-check-concepts)
- [Google Cloud CLI: network-endpoint-groups](https://cloud.google.com/sdk/gcloud/reference/compute/network-endpoint-groups)

**NEG mô tả nơi load balancer gửi traffic, nhưng không tự bảo đảm backend hoạt động tốt.** Với VM, hãy chú ý IP:port và health check; với GKE, hãy chú ý controller, Pod readiness và sự đồng bộ endpoint; với Cloud Run, hãy chú ý tham chiếu serverless, ingress, identity và giới hạn health checking. Khi kết hợp đúng các lớp đó, một hệ thống có thể phục vụ nhiều loại workload sau cùng một frontend, vận hành được các lần phát hành và theo dõi chất lượng dịch vụ từ góc nhìn người dùng.
