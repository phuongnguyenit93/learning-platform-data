# Ingress, Gateway API và công bố ứng dụng trên AKS

> **Chương:** Nền tảng Azure Kubernetes Service  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Hoàn thành bài này, bạn có thể:

1. Giải thích cách request từ Internet hoặc mạng riêng đi qua **Azure Kubernetes Service (AKS)** tới Pod.
2. Phân biệt `ClusterIP`, `NodePort`, `LoadBalancer`, **Ingress** và **Gateway API**.
3. Nhận diện vai trò của **Ingress controller**, **Gateway API controller**, `IngressClass` và `GatewayClass`; hiểu rằng khai báo API đơn thuần không tạo đường vào.
4. Triển khai hai ứng dụng thử nghiệm, công bố bằng **Ingress** với host/path routing và chứng chỉ TLS.
5. Mô tả và viết manifest **Gateway**, **HTTPRoute**; đọc trạng thái gắn route và các điều kiện `Accepted`, `ResolvedRefs`, `Programmed`.
6. Lựa chọn giữa **AKS application routing**, controller Ingress thích hợp, **Azure Application Gateway** hoặc **Application Gateway for Containers** theo kiến trúc và khả năng hỗ trợ.
7. Chẩn đoán lỗi DNS, TLS, HTTP 404/502/503, Service endpoints, health probes, ingress controller và quyền cấu hình.
8. Thiết kế bảo mật, giám sát, rollout, autoscaling và kiểm soát chi phí khi công bố workload trên AKS.

## 1. Bài toán: đưa ứng dụng trong cluster ra cho người dùng

Giả sử một doanh nghiệp triển khai hai microservice trên AKS:

- `catalog`: API lấy danh sách sản phẩm, chạy trên cổng `5678`.
- `orders`: API xử lý đơn hàng, cũng chạy trên cổng `5678`.

Bên ngoài, người dùng chỉ muốn truy cập một tên miền:

~~~text
https://shop.example.com/catalog
https://shop.example.com/orders
~~~

Bên trong cluster, ứng dụng đang chạy dưới dạng **Pods**; Pods có thể bị thay thế, đổi IP hoặc tăng số replica. Không thể cấu hình DNS công cộng trỏ trực tiếp tới một Pod IP rồi kỳ vọng ổn định.

Một cách tổ chức:

~~~mermaid
flowchart LR
    U["Client Internet"]
    DNS["DNS shop.example.com"]
    LB["Public IP / Azure Load Balancer\nhoặc gateway L7"]
    IC["Ingress/Gateway controller\nđiểm xử lý HTTP routing"]
    S1["Service catalog-svc"]
    S2["Service orders-svc"]
    P1["catalog Pods"]
    P2["orders Pods"]
    U --> DNS --> LB --> IC
    IC -->|"/catalog"| S1 --> P1
    IC -->|"/orders"| S2 --> P2
~~~

Sơ đồ là **luồng logic**. Trong một số giải pháp L7 được Azure quản lý, controller bên trong Kubernetes chỉ **reconcile cấu hình** và dữ liệu đi qua gateway nằm ngoài node, thay vì thực sự qua một proxy pod trong cluster. Luôn kiểm tra data plane của sản phẩm đã chọn.

**Mục tiêu:** công bố tên miền ổn định, định tuyến theo HTTP host/path, quản lý TLS và giảm phụ thuộc vào IP của từng Pod.

## 2. Các đối tượng Kubernetes trong đường đi request

### 2.1. Pod và Deployment

- **Pod** là đơn vị chạy một hoặc nhiều container chia sẻ network namespace.
- **Deployment** quản lý số replicas và rollout của những Pods stateless.
- Một Pod có IP riêng trong mạng cluster; IP có thể thay đổi khi Pod bị tạo lại.

Ví dụ Deployment `catalog` có 2 replicas, mỗi Pod có thể mang địa chỉ khác nhau. Người dùng không nên biết các địa chỉ đó.

### 2.2. Service và các loại Service

**Service** tạo điểm truy cập ổn định tới những Pods được chọn qua `selector` và `ports`.

| `Service.type` | Phạm vi sử dụng | Khi nào nên dùng |
| --- | --- | --- |
| `ClusterIP` | Điểm vào nội bộ cluster | Backend của Ingress/Gateway hoặc giao tiếp microservice |
| `NodePort` | Mở một port trên từng node theo cấu hình Kubernetes | Một số đường kết nối hoặc nhu cầu đặc thù; không phải mặc định tốt nhất cho web public |
| `LoadBalancer` | Yêu cầu cloud integration tạo load balancer bên ngoài cluster | Công bố TCP/UDP hoặc một dịch vụ trực tiếp; tùy cấu hình là public hay internal |
| `ExternalName` | Ánh xạ tên service sang một DNS name khác | Service discovery tới dịch vụ ngoài theo trường hợp hỗ trợ, không tự tạo proxy |

Trên AKS, một `Service.type=LoadBalancer` thông thường có thể khiến nền tảng cấp tài nguyên Azure Load Balancer và địa chỉ frontend theo cấu hình. Nếu không khai báo chế độ internal, nó **có thể công bố ra Internet**; cần kiểm tra chính sách và resource thực tế.

**ClusterIP** không thể được truy cập trực tiếp từ Internet. Đây là loại phù hợp cho Service backend phía sau Ingress hoặc Gateway.

### 2.3. Ingress và Gateway API nằm ở lớp nào?

- **Ingress** là Kubernetes API dành cho **HTTP/HTTPS routing** ở lớp 7, hỗ trợ các quy tắc host/path và TLS theo khả năng controller.
- **Gateway API** là tập Kubernetes APIs diễn tả nhiều vai trò, listener, route và quan hệ gắn route vào gateway, với mô hình mở rộng tốt hơn.
- **Ingress controller/Gateway controller** là thành phần **hiện thực hóa cấu hình**: lập trình proxy/gateway, chọn backend, cấu hình data plane và phản ánh trạng thái.
- **Azure Load Balancer** phần lớn hoạt động lớp 4; không thể tự đọc manifest `Ingress` rồi định tuyến theo URL path nếu không có một controller L7 thích hợp.

Đừng nhầm **Kubernetes Gateway API** với một dịch vụ API gateway quản trị nghiệp vụ như Azure API Management. Hai sản phẩm có thể cùng xuất hiện trong kiến trúc, nhưng chức năng và đối tượng quản lý khác nhau.

### 2.4. Phân lớp kiến trúc

~~~mermaid
flowchart TD
    C["Client"]
    D["DNS + public/private endpoint"]
    T["TLS listener / HTTP routing"]
    R["Ingress hoặc Gateway + HTTPRoute"]
    S["Kubernetes Service"]
    E["EndpointSlices"]
    P["Ready Pods"]
    C --> D --> T
    R -.->|"Controller reconcile"| T
    T --> S --> E --> P
~~~

`EndpointSlice` chứa thông tin backend endpoints cho Service, được cập nhật theo Pods và trạng thái readiness. Nếu Service có selector sai hoặc Pods không Ready, controller có thể không có backend dùng được dù manifest Ingress/Gateway hoàn toàn hợp lệ.

## 3. Bốn cách phổ biến để công bố ứng dụng trên AKS

| Phương án | Đường vào chính | Định tuyến HTTP host/path | Phù hợp |
| --- | --- | --- | --- |
| `Service.type=LoadBalancer` | Azure load balancer L4 | Không tự cung cấp routing L7 | TCP/UDP service, một endpoint đơn giản |
| **Ingress + controller** | Ingress controller được cài/được Azure quản lý | Có, theo Ingress API/controller | Nhiều web APIs dùng chung một điểm vào |
| **Gateway API + controller** | Gateway data plane do controller quản lý | Có, với `HTTPRoute` và các loại routes hỗ trợ | Phân quyền platform/app, routing nâng cao, mô hình nhiều nhóm |
| **Edge service phía trước AKS** | Azure Front Door, Application Gateway, WAF hoặc dịch vụ tương ứng | Tùy sản phẩm và tầng kết nối | Toàn cầu, bảo vệ biên, CDN, WAF, yêu cầu doanh nghiệp |

**Điểm phân biệt lớn:** một `Service.type=LoadBalancer` cho mỗi ứng dụng có thể đơn giản nhưng thường tăng số public endpoints, chứng chỉ và chính sách phải quản lý. Ingress/Gateway có thể gom nhiều Service sau một hoặc một số điểm vào.

### 3.1. Chỉ dùng LoadBalancer khi nào?

Một ứng dụng TCP hoặc UDP không có HTTP path routing có thể dùng `LoadBalancer` trực tiếp. Ví dụ:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: tcp-service
  namespace: shop
spec:
  type: LoadBalancer
  selector:
    app: some-tcp-app
  ports:
    - name: tcp
      port: 443
      targetPort: 9443
      protocol: TCP
~~~

Đây là **manifest minh họa**, chưa có Deployment backend. Trên AKS, tạo Service loại này có thể cấp **public frontend IP** và phát sinh chi phí. Nó cũng **không tự thực hiện TLS termination hoặc HTTP path routing** chỉ vì lắng nghe port 443.

Để yêu cầu internal load balancer trong một mô hình AKS hỗ trợ:

~~~yaml
metadata:
  annotations:
    service.beta.kubernetes.io/azure-load-balancer-internal: "true"
~~~

Annotation trên là ví dụ dùng với Azure cloud provider; phải đặt vào **metadata của Service** tương ứng, xác minh network/subnet/permission và xem Service được cấp địa chỉ private thực tế. Không coi annotation là cách kiểm soát authentication.

### 3.2. Khi nào nên chọn Ingress/Gateway?

Một ứng dụng có nhiều API HTTP/HTTPS, cần routing theo host/path, redirect HTTPS và chứng chỉ TLS thường cần L7 routing. Hãy chọn controller sản xuất có hỗ trợ AKS/Kubernetes version/tính năng bạn cần, thay vì chỉ áp dụng YAML rồi kỳ vọng IP tự xuất hiện.

## 4. Chuẩn bị trước khi triển khai

### 4.1. Kiểm tra ngữ cảnh và quyền

Trong ví dụ, các lệnh chạy trên máy quản trị đã có `az` và `kubectl`, được cấp quyền với cluster.

~~~bash
az login
az account show \
  --query "{name:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Thay bằng đúng subscription đã được phân công.
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-aks-lab"
AKS="aks-web-lab"

# Cập nhật kubeconfig cho đúng cluster được phép dùng.
az aks get-credentials \
  --resource-group "$RG" \
  --name "$AKS"

kubectl config current-context
kubectl get nodes
kubectl get namespaces
~~~

**Lưu ý:** `az aks get-credentials` thay đổi kubeconfig trên máy thao tác. Nó không tự cài cluster, controller hay cấp quyền Kubernetes RBAC cho tài khoản thiếu quyền.

### 4.2. Xác nhận controller/CRDs trước

Trước khi dùng Ingress hoặc Gateway API, kiểm tra những đối tượng thực sự có:

~~~bash
kubectl get ingressclasses

kubectl get gatewayclasses.gateway.networking.k8s.io

kubectl api-resources | grep -E 'ingresses|gateways|httproutes'
~~~

Nếu `GatewayClass` hoặc `HTTPRoute` báo “resource type not found”, cluster có thể **chưa cài Gateway API CRDs**. Nếu có CRDs nhưng không có controller/GatewayClass hoạt động, tạo `Gateway` chưa làm dữ liệu đi qua.

Nếu `IngressClass` tồn tại, phải xem controller tương ứng đang hoạt động; tên class có trong API chưa chứng minh proxy đã chạy hoặc sẵn sàng.

### 4.3. Ràng buộc an toàn của bài thực hành

- Ví dụ sử dụng tên miền tài liệu `shop.example.com`, **không phải DNS bạn sở hữu**. Muốn HTTPS thật, thay bằng domain của tổ chức và chứng chỉ phù hợp.
- Hai ứng dụng ví dụ dùng image công khai đơn giản chỉ để trình bày routing, không chứa dữ liệu sản xuất.
- Không chạy `kubectl apply` trên cluster production ngoài quy trình thay đổi.
- Không tự cài một controller Ingress/Gateway trùng với giải pháp hiện có trên cluster; có thể sinh thêm public load balancer hoặc xung đột quyền quản trị.
- Không chỉnh sửa role assignment, network, DNS công cộng hay certificate production chỉ để thực hành.

## 5. Tạo hai backend Deployment và ClusterIP Service

### 5.1. Namespace riêng cho bài lab

~~~bash
kubectl create namespace shop
~~~

Nếu namespace đã tồn tại, không cần tạo lại. Ở môi trường production, tổ chức nên áp dụng RBAC, ResourceQuota, LimitRange và NetworkPolicy phù hợp trước khi cho nhóm triển khai workloads.

### 5.2. File `microservices.yaml`

Ví dụ sau dùng image `hashicorp/http-echo` để trả nội dung tĩnh. Ở production, pin image digest, quét image và quản lý registry riêng. Các API `/catalog` và `/orders` của bài lab đều trả text để quan sát routing, không phải ứng dụng đơn hàng thật.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: echo
          image: hashicorp/http-echo:1.0.0
          args:
            - "-listen=:5678"
            - "-text=CATALOG service response"
          ports:
            - name: http
              containerPort: 5678
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 250m
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 2
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-svc
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: catalog
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: echo
          image: hashicorp/http-echo:1.0.0
          args:
            - "-listen=:5678"
            - "-text=ORDERS service response"
          ports:
            - name: http
              containerPort: 5678
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 250m
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 2
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: orders-svc
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

**Giải thích đường port:** client của cluster gọi Service ở `port:80`. Service chuyển tới port `5678` trong Pod qua `targetPort:http`, dựa trên named container port `http`.

- `selector: app: catalog` phải khớp nhãn Pod của Deployment catalog.
- `readinessProbe` quyết định Pod có thể trở thành endpoint sẵn sàng hay không.
- `replicas:2` là số Pod mong muốn, không phải số load balancer công cộng.
- Hai Services `ClusterIP` **chưa được công bố ra Internet**.

### 5.3. Áp dụng và xác minh trước khi công bố

~~~bash
kubectl apply -f microservices.yaml

kubectl -n shop rollout status deployment/catalog
kubectl -n shop rollout status deployment/orders

kubectl -n shop get deployments,pods,services

kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=catalog-svc

kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=orders-svc
~~~

Nếu Service không có ready endpoints, dừng ở đây và kiểm tra Pod labels, container logs, readiness probe và image pull trước khi cấu hình Ingress/Gateway.

Để thử route nội bộ mà không cần public endpoint, có thể dùng port-forward trong môi trường lab được phép:

~~~bash
kubectl -n shop port-forward service/catalog-svc 8081:80

# Trong terminal khác:
curl http://127.0.0.1:8081/
~~~

**Port-forward chỉ là đường kiểm tra tạm tới Kubernetes Service**, không phải giải pháp công bố public cho production.

## 6. Công bố HTTP bằng Kubernetes Ingress

### 6.1. Ingress là khai báo, controller mới thực hiện routing

Manifest Ingress chứa:

- `ingressClassName`: chọn loại Ingress controller cần xử lý.
- `rules.host`: hostname HTTP.
- `http.paths`: rule định tuyến theo đường dẫn.
- `backend.service`: Kubernetes Service đích và port.
- `tls`: hostname HTTPS và tham chiếu tới TLS Secret trong namespace theo quy tắc.

Controller có thể là giải pháp quản lý từ AKS, controller do tổ chức vận hành hoặc giải pháp tích hợp với một gateway L7 Azure. Các controller có **annotations, khả năng TLS, rewrite, WAF, health check và lifecycle** khác nhau; tránh copy annotation của controller A sang controller B.

### 6.2. Xác định IngressClass thật

~~~bash
kubectl get ingressclass

kubectl describe ingressclass <INGRESS_CLASS_NAME>
~~~

**Thay** `<INGRESS_CLASS_NAME>` bằng class đang được quản trị trên cluster. Ví dụ manifest bên dưới dùng tên `replace-with-installed-class` để tránh giả định class của một sản phẩm cụ thể. Phải thay bằng class có thực **trước khi apply**.

### 6.3. File `ingress.yaml`

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop-ingress
  namespace: shop
spec:
  ingressClassName: replace-with-installed-class
  rules:
    - host: shop.example.com
      http:
        paths:
          - path: /catalog
            pathType: Prefix
            backend:
              service:
                name: catalog-svc
                port:
                  number: 80
          - path: /orders
            pathType: Prefix
            backend:
              service:
                name: orders-svc
                port:
                  number: 80
~~~

**Vì sao ví dụ không có path rewrite?** Hai backend `http-echo` trả text với bất kỳ path nào, nên có thể thấy định tuyến mà không cần rewrite. Với API thật chỉ chấp nhận `/` hoặc `/v1/*`, cần thiết kế path phía ứng dụng hoặc cấu hình rewrite **đúng theo controller**. Ingress API chuẩn không đưa mọi tính năng rewrite/advanced routing thành trường dùng chung.

Khi đã sửa class, áp dụng:

~~~bash
kubectl apply -f ingress.yaml

kubectl -n shop get ingress
kubectl -n shop describe ingress shop-ingress
~~~

Kiểm tra cột `ADDRESS` và các events. Có controller nhưng không có địa chỉ hoặc Ingress status chưa sẵn sàng thì chưa thể kỳ vọng DNS công cộng hoạt động.

### 6.4. Kiểm tra host routing trước khi cấu hình DNS

Nếu Ingress controller đã có một public IP **được phê duyệt dùng để thử**, có thể gửi request với Host header mà chưa tạo DNS:

~~~bash
# IP 203.0.113.10 chỉ để minh họa, thay bằng endpoint thực tế.
curl -i \
  -H "Host: shop.example.com" \
  http://203.0.113.10/catalog

curl -i \
  -H "Host: shop.example.com" \
  http://203.0.113.10/orders
~~~

Kết quả kỳ vọng: `CATALOG service response` và `ORDERS service response`. IP `203.0.113.10` là **địa chỉ dành cho tài liệu**, không phải địa chỉ đã được cấp cho cluster.

Nếu nhận 404 từ controller, xem hostname/path matching, IngressClass và rules. Nếu nhận 503/502, xem backend Service endpoints, Pod readiness và log controller.


## 7. HTTPS, DNS và quản lý chứng chỉ cho Ingress

### 7.1. Từ IP ingress tới hostname thực tế

Với tên miền do tổ chức quản lý, thường cần:

1. Controller/gateway có một **frontend endpoint** ổn định theo phương án triển khai.
2. Cấu hình DNS record như **A** trỏ `shop.example.com` tới public IP, hoặc CNAME theo yêu cầu của dịch vụ/kiến trúc.
3. Chuẩn bị chứng chỉ TLS có SAN bao phủ `shop.example.com`.
4. Gắn chứng chỉ đúng listener/Ingress của controller.
5. Kiểm tra handshake, HTTP path routing và request tới backend.

**DNS record không tạo ra ingress controller.** Ngược lại, tạo Ingress có thể không tự tạo DNS record. Một số hệ thống dùng ExternalDNS hoặc tích hợp quản lý DNS để tự cập nhật records, nhưng chúng cần quyền DNS và cấu hình riêng.

### 7.2. TLS Secret cho Ingress

Nếu controller hỗ trợ Ingress TLS theo mô hình Kubernetes Secret, chứng chỉ và private key có thể được lưu dưới dạng Secret kiểu `kubernetes.io/tls` **trong cùng namespace với Ingress**, ví dụ `shop`.

Lệnh minh họa với chứng chỉ do tổ chức đã cấp:

~~~bash
# Chỉ dùng certificate/key hợp lệ thuộc quyền quản lý của tổ chức.
# Không ghi private key vào source code hoặc commit vào git.
kubectl -n shop create secret tls shop-tls \
  --cert=/secure/certs/shop-fullchain.pem \
  --key=/secure/certs/shop-private.key
~~~

Lưu ý: **Kubernetes Secret không mặc định được mã hóa end-to-end chỉ vì tên “Secret”**. Cần kiểm soát RBAC, secret encryption tại rest theo khả năng cluster, đường phân phối chứng chỉ và quy trình rotation. Có thể dùng **cert-manager** hoặc tích hợp Azure Key Vault/CSI/certificate management thích hợp theo cơ chế và controller được hỗ trợ.

### 7.3. Bổ sung `tls` vào Ingress

Một phiên bản `ingress-https.yaml` của Ingress ở mục 6:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop-ingress
  namespace: shop
spec:
  ingressClassName: replace-with-installed-class
  tls:
    - hosts:
        - shop.example.com
      secretName: shop-tls
  rules:
    - host: shop.example.com
      http:
        paths:
          - path: /catalog
            pathType: Prefix
            backend:
              service:
                name: catalog-svc
                port:
                  number: 80
          - path: /orders
            pathType: Prefix
            backend:
              service:
                name: orders-svc
                port:
                  number: 80
~~~

Áp dụng khi đã thay IngressClass và chuẩn bị TLS Secret:

~~~bash
kubectl apply -f ingress-https.yaml
kubectl -n shop describe ingress shop-ingress
kubectl -n shop get secret shop-tls
~~~

Secret chứa thông tin nhạy cảm. **Không in hoặc gửi nội dung `data.tls.key` lên chat/logs** để “kiểm tra nhanh”; chỉ xem metadata của Secret, chain công khai hoặc kiểm tra handshake qua endpoint.

### 7.4. TLS termination và mã hóa tới backend

Một phương án thường gặp:

~~~text
Client --HTTPS--> Ingress controller --HTTP--> catalog-svc --> Pods
~~~

TLS được chấm dứt ở ingress controller. Điều này **không đồng nghĩa đường từ ingress tới Pod cũng đang dùng HTTPS**. Nếu yêu cầu mã hóa nội bộ, cần cấu hình backend protocol, service mesh/mTLS hoặc giải pháp gateway phù hợp theo khả năng controller; Ingress API chuẩn không đưa toàn bộ backend TLS behavior vào cùng một trường dùng chung.

### 7.5. Redirect HTTP sang HTTPS

Không phải mọi controller tự redirect HTTP sang HTTPS theo cùng cách. Một số dùng cấu hình mặc định, một số dùng annotations hoặc policy riêng. Trước khi khẳng định “HTTP đã bị chặn/redirect”, hãy kiểm tra:

~~~bash
curl -I http://shop.example.com/catalog
curl -I https://shop.example.com/catalog
~~~

Trong production, TLS certificate phải hợp lệ. **Đừng dùng `curl -k` làm bằng chứng TLS đạt chuẩn**: `-k` bỏ qua xác minh chứng chỉ của client.

Nếu DNS chưa cập nhật và muốn thử frontend HTTPS qua một IP thực đã được cấp:

~~~bash
# IP 203.0.113.10 là ví dụ; thay bằng IP frontend thật.
curl -v \
  --resolve shop.example.com:443:203.0.113.10 \
  https://shop.example.com/catalog
~~~

`--resolve` giữ hostname cho TLS SNI và HTTP Host nhưng ép TCP tới IP chỉ định; hữu ích khi kiểm tra certificate và routing trước khi chuyển DNS.

## 8. Gateway API: mô hình mới để quản trị kết nối L7

**Gateway API** là một tập Kubernetes APIs do cộng đồng Kubernetes phát triển, nhằm mô tả routing và các vai trò vận hành rõ ràng hơn. Nó không phải một proxy cụ thể; vẫn cần **implementation/controller** tương thích.

### 8.1. Bốn đối tượng quan trọng

| Đối tượng | Ai thường quản lý | Trách nhiệm |
| --- | --- | --- |
| `GatewayClass` | Platform/network team | Chọn implementation/controller và tham số nền tảng |
| `Gateway` | Infra/cluster operator | Định nghĩa listener, port, protocol, hostname, TLS và phạm vi cho phép routes |
| `HTTPRoute` | App/team owner | Quy tắc match theo host/path/headers và backendRefs |
| `ReferenceGrant` | Owner namespace chứa resource được tham chiếu | Cho phép một số reference xuyên namespace, ví dụ HTTPRoute backendRef tới Service khác namespace |

Một cách nhìn:

~~~mermaid
flowchart TD
    CLASS["GatewayClass\ncontroller của nền tảng"]
    G["Gateway\nlisteners :80/:443"]
    R1["HTTPRoute team-catalog\n/catalog"]
    R2["HTTPRoute team-orders\n/orders"]
    S1["catalog-svc"]
    S2["orders-svc"]
    CLASS --> G
    R1 -->|"parentRefs"| G
    R2 -->|"parentRefs"| G
    R1 -->|"backendRefs"| S1
    R2 -->|"backendRefs"| S2
~~~

Gateway/HTTPRoute tách quyền sở hữu **điểm vào** khỏi quyền sở hữu **đường dẫn ứng dụng**. Đây là ưu thế khi nhiều nhóm cùng dùng hạ tầng công bố chung.

### 8.2. GatewayClass do controller cung cấp

Kiểm tra các class đã cài:

~~~bash
kubectl get gatewayclass
kubectl describe gatewayclass <GATEWAY_CLASS_NAME>
~~~

GatewayClass chứa `controllerName` trỏ tới implementation. Tên class và controller **không được Kubernetes tự sinh cho tất cả cluster**. Chọn class phải dựa trên công nghệ được tổ chức cài đặt, ví dụ controller tích hợp một gateway Azure hoặc một triển khai khác đã được hỗ trợ.

Nếu không có Gateway API CRDs, đừng chỉ apply các YAML dưới đây; phải có quy trình cài CRDs/controller và kiểm soát phiên bản trước.

### 8.3. Gateway và HTTPRoute tối thiểu qua HTTP

Ví dụ `gateway-http.yaml`. **Thay** `replace-with-installed-class` bằng GatewayClass thật:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: shop-gateway
  namespace: shop
spec:
  gatewayClassName: replace-with-installed-class
  listeners:
    - name: web
      protocol: HTTP
      port: 80
      hostname: shop.example.com
      allowedRoutes:
        namespaces:
          from: Same
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: shop-routes
  namespace: shop
spec:
  parentRefs:
    - name: shop-gateway
      sectionName: web
  hostnames:
    - shop.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /catalog
      backendRefs:
        - name: catalog-svc
          port: 80
    - matches:
        - path:
            type: PathPrefix
            value: /orders
      backendRefs:
        - name: orders-svc
          port: 80
~~~

Đường đi:

~~~text
HTTPRoute(shop-routes)
  parentRefs  → Gateway(shop-gateway), listener web :80
  /catalog    → Service catalog-svc:80
  /orders     → Service orders-svc:80
~~~

**Điều kiện:** implementation/controller phải hỗ trợ Gateway API `v1` với Gateway + HTTPRoute, GatewayClass hợp lệ và listener được lập trình thành data plane. Chỉ có các YAML không tạo IP public.

### 8.4. Áp dụng và xác minh trạng thái

~~~bash
kubectl apply -f gateway-http.yaml

kubectl -n shop get gateways.gateway.networking.k8s.io
kubectl -n shop get httproutes.gateway.networking.k8s.io

kubectl -n shop describe gateway shop-gateway
kubectl -n shop describe httproute shop-routes

kubectl -n shop get gateway shop-gateway -o yaml
kubectl -n shop get httproute shop-routes -o yaml
~~~

Kiểm tra các nhóm thông tin:

- `Gateway.status.addresses`: endpoint được cấp theo mô hình controller.
- Listener và `status.conditions`: có được chấp nhận/lập trình hợp lệ không.
- `HTTPRoute.status.parents` và `conditions`: route đã được Gateway chấp nhận, các references đã được resolve hay chưa.
- `GatewayClass.status.conditions`: class đã được controller chấp nhận hay chưa.

Một số condition phổ biến:

| Condition | Ý nghĩa quan sát | Khi `False` cần xem |
| --- | --- | --- |
| `Accepted` | Gateway/route đã được implementation chấp nhận theo các ràng buộc | Listener, hostname, class, allowedRoutes |
| `ResolvedRefs` | Backend/Secret và reference liên quan được resolve hợp lệ | Tên Service, port, namespace, ReferenceGrant |
| `Programmed` | Gateway/listener đã được lập trình vào data plane theo controller | Endpoint/IP, cloud resource provisioning, quyền, controller logs |

Tên/ý nghĩa condition phải được đọc **theo resource và implementation cụ thể**. Đừng chỉ kiểm tra HTTPRoute đã tồn tại; route có thể hiện trong API server nhưng **không được controller chấp nhận**.

## 9. Gateway API với HTTPS và định tuyến nâng cao

### 9.1. HTTPS listener và chứng chỉ

Một phiên bản Gateway có listener HTTPS:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: shop-gateway
  namespace: shop
spec:
  gatewayClassName: replace-with-installed-class
  listeners:
    - name: https
      protocol: HTTPS
      port: 443
      hostname: shop.example.com
      tls:
        mode: Terminate
        certificateRefs:
          - kind: Secret
            name: shop-tls
      allowedRoutes:
        namespaces:
          from: Same
~~~

Tài nguyên `shop-tls` trong ví dụ nằm **cùng namespace `shop` với Gateway**. Chứng chỉ phải có SAN phù hợp hostname và private key hợp lệ. Một số implementations có cơ chế tích hợp certificate khác; cần kiểm tra feature support của GatewayClass/controller thay vì mặc định mọi backend đều dùng Secret theo cách giống nhau.

HTTPRoute dùng listener `https`:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: shop-routes
  namespace: shop
spec:
  parentRefs:
    - name: shop-gateway
      sectionName: https
  hostnames:
    - shop.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /catalog
      backendRefs:
        - name: catalog-svc
          port: 80
    - matches:
        - path:
            type: PathPrefix
            value: /orders
      backendRefs:
        - name: orders-svc
          port: 80
~~~

**Lưu ý khi áp dụng:** ví dụ HTTPS ở mục này là **phương án thay thế** cấu hình Gateway HTTP `shop-gateway` ở mục 8. Nếu dùng `kubectl apply` lên cùng tên Gateway, cấu hình listeners có thể được **thay đổi**. Muốn giữ cả HTTP và HTTPS, phải khai báo cả hai listeners trong **cùng manifest Gateway** và thêm rules/HTTPRoute phù hợp.

### 9.2. HTTP → HTTPS redirect

Gateway API `HTTPRoute` cung cấp các loại filters chuẩn, trong đó có `RequestRedirect` theo khả năng hỗ trợ. Với một HTTP listener tên `web` đã tồn tại, route redirect có thể viết:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: shop-redirect
  namespace: shop
spec:
  parentRefs:
    - name: shop-gateway
      sectionName: web
  hostnames:
    - shop.example.com
  rules:
    - filters:
        - type: RequestRedirect
          requestRedirect:
            scheme: https
            statusCode: 301
~~~

Để ví dụ này hoạt động, Gateway phải có **listener `web` HTTP :80** và **listener HTTPS :443**, và implementation hỗ trợ filter đó. Đừng áp dụng route redirect khi chưa có listener `web`. Kiểm tra kết quả HTTP 301 và header `Location` trong client.

### 9.3. Route đến nhiều Services theo trọng số

Một số implementation Gateway API hỗ trợ weighted routing để canary:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: catalog-canary
  namespace: shop
spec:
  parentRefs:
    - name: shop-gateway
      sectionName: https
  hostnames:
    - shop.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /catalog
      backendRefs:
        - name: catalog-stable-svc
          port: 80
          weight: 90
        - name: catalog-canary-svc
          port: 80
          weight: 10
~~~

**Chỉ là manifest minh họa cho canary**: hai Services `catalog-stable-svc` và `catalog-canary-svc` **phải được tạo riêng**; chúng không nằm trong bộ Deployment lab ở mục 5. Khi dùng canary, phải tránh để một HTTPRoute khác có cùng match gây xung đột hoặc thay đổi thứ tự ưu tiên theo chính sách controller.

Trọng số `90/10` là tỷ lệ phân phối logic, không đảm bảo cứ 10 request phải có đúng một request vào canary. Quan sát trên mẫu nhỏ hoặc với session/caching có thể chênh lệch.

### 9.4. Header matching, URL rewrite và filters

Gateway API có thể mô tả các điều kiện/filters như:

- Match theo hostname, path, một số headers và query parameters theo khả năng.
- Redirect HTTP sang HTTPS.
- Header modification.
- URL rewrite khi feature được implementation hỗ trợ.
- Weighted backendRefs.

**Không phải mọi controller hỗ trợ toàn bộ tính năng chuẩn và extension.** Khi định dùng một filter hay route kind, kiểm tra danh sách Gateway API conformance/features của implementation và version đang chạy, cùng trạng thái conditions sau triển khai.

## 10. Nhiều namespace: phân quyền route và backend

### 10.1. Mẫu platform team quản lý Gateway, app team quản lý HTTPRoute

Một tổ chức có thể đặt:

~~~text
namespace: network-system
  Gateway: shared-gateway

namespace: team-catalog
  HTTPRoute: catalog-route
  Service: catalog-svc

namespace: team-orders
  HTTPRoute: orders-route
  Service: orders-svc
~~~

Gateway do platform team vận hành có thể cho phép HTTPRoutes từ namespace được chọn qua `listeners[].allowedRoutes`. Team sở hữu HTTPRoute có thể quản trị các path được ủy quyền trong phạm vi tổ chức.

Ví dụ Gateway listener chỉ cho phép namespaces có nhãn `expose=approved` gắn routes:

~~~yaml
listeners:
  - name: https
    protocol: HTTPS
    port: 443
    hostname: shop.example.com
    tls:
      certificateRefs:
        - name: shop-tls
    allowedRoutes:
      namespaces:
        from: Selector
        selector:
          matchLabels:
            expose: approved
~~~

Đây là **đoạn YAML listener** để minh họa, không phải manifest Gateway hoàn chỉnh. Nhãn namespace là một dạng chính sách attach route; phải kiểm soát ai được phép gắn nhãn đó. Với default `from: Same`, các HTTPRoutes từ namespace khác thường **không được gắn**, dù route đã tạo thành công.

### 10.2. ReferenceGrant và cross-namespace backendRefs

Ví dụ HTTPRoute trong namespace `team-catalog` muốn trỏ tới Service trong namespace `shared-backend`. Theo Gateway API, một số cross-namespace references cần **ReferenceGrant** được owner **namespace chứa resource đích** cấp cho bên tham chiếu.

Điểm cần phân biệt:

- **HTTPRoute ở namespace khác gắn vào Gateway**: kiểm soát qua `allowedRoutes` của listener và parentRefs.
- **HTTPRoute tham chiếu tới Service khác namespace**: yêu cầu cơ chế cho phép cross-namespace reference phù hợp, thường là `ReferenceGrant` ở namespace chứa Service.
- Một Gateway listener dùng TLS Secret ở namespace khác cũng có thể có ràng buộc reference/permission riêng.

Không mặc định tạo một ReferenceGrant sẽ thay thế cấu hình allowedRoutes, hoặc allowedRoutes tự cho phép mọi backendRefs xuyên namespace.

### 10.3. RBAC và khả năng kiểm soát chung

- Platform team được phép quản lý `GatewayClass`, Gateways, external IP, TLS, network/WAF.
- Application team có quyền trên `HTTPRoute`/Ingress và Services trong namespace của mình.
- Việc sửa DNS và cấp chứng chỉ thuộc quy trình kiểm soát riêng.
- Nếu team có quyền tạo HTTPRoute với hostname/path nhạy cảm, cần thêm chính sách admission và reviews phù hợp.

Không để mọi namespace tự chiếm hostname `shop.example.com` trên Gateway dùng chung mà thiếu quy tắc sở hữu, tránh routing conflicts và rủi ro bảo mật.

## 11. Những lựa chọn ingress/gateway thường gặp trên AKS

### 11.1. AKS application routing

AKS có khả năng **application routing** giúp đơn giản hóa việc cấu hình Ingress controller theo các tính năng và vùng hỗ trợ. Với những cấu hình được hỗ trợ, đây có thể là lựa chọn thuận tiện để triển khai **Ingress API** cho workload HTTP/HTTPS mà không tự vận hành toàn bộ thành phần routing.

Điểm cần xác minh trong môi trường thực tế:

- AKS/Kubernetes version và hỗ trợ add-on tại thời điểm triển khai.
- IngressClass tên gì, controller đang healthy không.
- External/internal ingress và network/subnet được cấu hình ra sao.
- Cách quản lý DNS, certificate và HTTPS.
- Lifecycle, chính sách bảo trì và hỗ trợ bảo mật của controller nền tảng.

Ví dụ kiểm tra trạng thái AKS:

~~~bash
az aks show \
  --resource-group "$RG" \
  --name "$AKS" \
  --query "{name:name, ingressProfile:ingressProfile}" \
  --output json

kubectl get ingressclass
~~~

Nếu chưa bật tính năng, không tự chạy lệnh enable trong production mà chưa đánh giá impact, chi phí, IP allocation và tính tương thích với controller hiện hữu.

**Lưu ý:** controller NGINX hoặc tên implementation cụ thể có vòng đời và chính sách hỗ trợ thay đổi theo phiên bản. Không dùng hướng dẫn cài đặt controller cũ không còn được bảo trì chỉ vì nó phổ biến trong bài blog. Với hệ thống mới, hãy đánh giá phương án hiện đang được AKS và nhà cung cấp hỗ trợ.

### 11.2. Application Gateway Ingress Controller (AGIC)

**AGIC** là integration/controller dùng cấu hình **Kubernetes Ingress** để lập trình **Azure Application Gateway** theo mô hình và phiên bản được hỗ trợ.

Luồng khái quát:

~~~mermaid
flowchart LR
    I["Kubernetes Ingress"]
    AGIC["AGIC controller\nreconcile cấu hình"]
    AGW["Azure Application Gateway\ndata plane L7"]
    S["Kubernetes Service"]
    P["AKS Pods"]
    I -.-> AGIC -.-> AGW
    AGW --> S --> P
~~~

Trong mô hình này, Application Gateway là tài nguyên L7 phía trước cluster; controller không nhất thiết là proxy HTTP mà traffic người dùng đi qua.

Các nội dung cần kiểm tra: Application Gateway SKU/tier, AGIC integration, VNet/peering/routing, backend health probes, TLS, WAF, identity/permissions và khả năng phiên bản sản phẩm.

### 11.3. Application Gateway for Containers

**Azure Application Gateway for Containers** có kiến trúc data plane và ALB Controller riêng, hỗ trợ các khả năng Kubernetes Gateway API/Ingress theo tính năng và phiên bản cụ thể. Nó **không phải cùng tài nguyên** với Azure Application Gateway truyền thống chạy cùng AGIC.

Phương án này đáng đánh giá khi tổ chức cần gateway L7 được Azure quản lý tích hợp sâu với AKS, routing theo Gateway API hoặc những tính năng hiện đại của data plane theo khả năng đang hỗ trợ.

Cần xác minh:

- Controller/GatewayClass tương ứng thực sự có trong cluster.
- Gateway API features/CRD versions được implementation hỗ trợ.
- Resource/region và networking prerequisites.
- Model ownership cho ALB, frontend, TLS, traffic và permissions.
- Logging, health probes, security policy và billing riêng.

Không áp dụng manifest có `gatewayClassName` của controller A sang controller B mà chưa kiểm tra. Tên GatewayClass là **giá trị implementation-specific**.

### 11.4. Azure Front Door và API Management không thay thế controller trong cluster

- **Azure Front Door** cung cấp entrypoint toàn cầu, routing/caching và WAF theo tính năng/cấu hình. Nó có thể chuyển tiếp tới một origin được công bố của AKS, nhưng **không tự tạo Service endpoints trong cluster**.
- **Azure API Management** tập trung quản trị API, policies, subscriptions, authentication và developer experience. Nó có thể đứng trước AKS, nhưng không phải một Kubernetes `GatewayClass` mặc định.
- **Azure Load Balancer** có thể cung cấp public/private L4 frontend cho ingress controller hoặc một Service, nhưng nó không tự giải mã quy tắc `HTTPRoute`.
- **Application Gateway** và **Application Gateway for Containers** là các sản phẩm L7 riêng, có data plane và tích hợp controller khác nhau.

Một hệ thống có thể có **Front Door → WAF/gateway → AKS Service → Pods**; mỗi lớp phải được cấu hình và giám sát độc lập. Tránh mở trực tiếp backend ra Internet ngoài ý muốn để bypass WAF.


## 12. Công bố public hay private: chọn đúng ranh giới mạng

### 12.1. Public ingress

Nếu website phục vụ người dùng ngoài Internet, ingress/gateway có thể sử dụng public frontend IP hoặc endpoint public của dịch vụ L7. Những cấu hình cần đánh giá:

1. **DNS** trỏ tới đúng địa chỉ/hostname frontend.
2. **TLS** có certificate, hostname và chính sách redirect HTTP/HTTPS phù hợp.
3. **Ingress/Gateway controller** khỏe và thực sự đã lập trình routing.
4. **Data plane tới Service/Pod** được định tuyến và cho phép lưu lượng.
5. **NSG/firewall/network policy** đúng phạm vi.
6. **Authentication, WAF/rate limiting** khi ứng dụng cần bảo vệ lớp 7.
7. **Observability** cho errors, latency, certificate expiry và backend health.

Không nên tạo một public `Service.type=LoadBalancer` cho mọi backend chỉ vì cấu hình nhanh. Một gateway có thể gom nhiều APIs vào một ingress point, giảm số điểm truy cập công cộng và tập trung chính sách.

### 12.2. Private ingress

Ứng dụng dành cho nhân viên qua VPN/ExpressRoute hoặc workload trong VNet có thể dùng **private IP frontend/internal ingress**.

~~~text
Máy on-premises -- VPN/ExpressRoute -- VNet/private DNS
                                        |
                                        v
                                Internal gateway :443
                                        |
                                        v
                                Service → Ready Pods
~~~

Cần xác định:

- Private IP có thể được định tuyến từ client đích không?
- Private DNS Zone/forwarding có phân giải được hostname không?
- Network security rules có cho phép đúng port/source không?
- TLS certificate có SAN đúng tên nội bộ không?
- Gateway/controller có hỗ trợ private frontend như cấu hình chọn không?
- Người dùng có được authentication/authorization không?

**Private AKS cluster** nói về cách truy cập **Kubernetes API server/control plane**, **không tự biến mọi Service hoặc Ingress thành private**. Và một AKS cluster có API server public vẫn có thể phục vụ ứng dụng qua private ingress.

### 12.3. Bảng quyết định đường vào

| Câu hỏi | Ảnh hưởng thiết kế |
| --- | --- |
| Client Internet hay nội bộ? | Public/private endpoint, DNS và firewall |
| Cần HTTP host/path hay TCP/UDP? | Ingress/Gateway API hoặc Service LoadBalancer L4 |
| Có nhiều team cùng dùng một entrypoint? | Gateway API, `allowedRoutes` và RBAC |
| Có cần WAF, CDN, multi-region? | Azure Front Door hoặc gateway L7 phù hợp |
| Ai quản lý DNS và TLS? | Static IP/hostname, Certificate/Key Vault và rotation |
| TLS kết thúc ở đâu? | Frontend cert, backend TLS, mTLS khi cần |
| Backend được bảo vệ khỏi bypass? | Không mở public LB ngoài ý muốn |
| Dev/Prod cần cách ly? | Namespace, cluster, gateway, policy và identity |

### 12.4. Rủi ro có hai đường public tới cùng backend

Giả sử API ở sau Front Door/WAF nhưng cũng có một Service LoadBalancer public trực tiếp. Kẻ gọi có thể truy cập backend mà **bỏ qua WAF, rate limit hoặc authentication ở edge**.

Do đó, cần thường xuyên kiểm kê các public IP, `Service.type=LoadBalancer`, Ingress, Gateway, origin endpoints và chính sách routing. Mọi đường public phải có chủ sở hữu, lý do tồn tại và phương án giám sát.

## 13. Health check và Service endpoints

### 13.1. Readiness, liveness và gateway health khác nhau

- **Readiness probe:** đánh giá Pod có thể nhận traffic qua Service hay không.
- **Liveness probe:** xác định container cần được restart theo điều kiện.
- **Startup probe:** cho phép ứng dụng khởi động chậm trước khi áp dụng kiểm tra khác.
- **Gateway/backend health check:** cơ chế riêng của controller hoặc gateway L7 để đánh giá upstream.

Chúng không tự đồng bộ về ngữ nghĩa. Có thể Pod Ready nhưng Application Gateway vẫn đánh giá backend `Unhealthy` vì gateway probe gọi sai hostname, port, path hoặc backend TLS certificate không hợp lệ.

### 13.2. Từ Pod readiness đến EndpointSlice

Trong lab, readiness probe gọi `GET /` trên container ở named port `http`:

~~~yaml
readinessProbe:
  httpGet:
    path: /
    port: http
  initialDelaySeconds: 2
  periodSeconds: 5
~~~

Kubernetes cập nhật EndpointSlices/Service khi Pods đủ điều kiện. Nếu selector sai hoặc Pods không Ready, Ingress/Gateway sẽ không có backend để phục vụ dù URL routing được khai báo đúng.

~~~bash
kubectl -n shop get pods -o wide
kubectl -n shop describe pod <POD_NAME>

kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=catalog-svc \
  -o yaml
~~~

Với ứng dụng thật, nên có readiness endpoint như `/ready` trả nhanh khi process và những dependency **thiết yếu** đã sẵn sàng. Tránh yêu cầu health endpoint đăng nhập bằng phiên người dùng hoặc liên tục truy cập dependency không thiết yếu khiến toàn bộ Pods mất Ready vì một lỗi nhỏ.

### 13.3. Port mismatch thường gây lỗi

Trong ví dụ:

~~~text
Ingress/HTTPRoute backendRef → Service port 80
Service targetPort "http"    → containerPort 5678
Process listen               → 0.0.0.0:5678
~~~

Nếu container chỉ nghe 5678 mà Service gửi tới 8080, sẽ xảy ra lỗi dù DNS và TLS hoàn toàn đúng.

~~~bash
kubectl -n shop describe service catalog-svc
kubectl -n shop get deployment catalog -o yaml
kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=catalog-svc
~~~

### 13.4. Rollout phải giữ đủ healthy backends

Khi Deployment rolling update, Pod mới cần Ready trước khi nhận request. Có thể cần:

- Startup probe phù hợp thời gian khởi tạo.
- Readiness probe phản ánh khả năng phục vụ thực tế.
- Graceful SIGTERM và `terminationGracePeriodSeconds` phù hợp.
- PodDisruptionBudget, topology spread và replicas khi cần availability.
- Cấu hình connection draining của ingress/gateway tương thích.

Kiểm tra:

~~~bash
kubectl -n shop rollout status deployment/catalog
kubectl -n shop get pods -l app=catalog -o wide
~~~

Đừng bỏ probes chỉ để làm Pods hiển thị Ready; cần xử lý lỗi startup hoặc dependency thật.

## 14. Quan sát hoạt động từ client tới Pod

### 14.1. Các nguồn thông tin quan trọng

| Lớp | Nguồn dữ liệu | Câu hỏi cần trả lời |
| --- | --- | --- |
| Client/DNS | `nslookup`, `curl`, TLS details | Request có đến đúng frontend? |
| Azure LB/L7 Gateway | Backend health, access logs, metrics | Data plane có chuyển request? |
| Ingress/Gateway controller | Reconciliation events, route status, logs | Config đã được chấp nhận và lập trình? |
| Ingress/Gateway access log | Host, path, upstream status, latency | HTTP status sinh ra ở đâu? |
| Kubernetes Service | EndpointSlices, selector, port | Có ready backend? |
| Pod/Deployment | Restart, readiness, OOMKilled, image pull | App có chạy khỏe? |
| App/Dependencies | Request traces, DB latency, exceptions | Code hoặc downstream có lỗi? |
| Azure Monitor | Alert và bảng chỉ số chung | SLO có bị ảnh hưởng? |

**Chú ý:** controller của một gateway Azure có thể chỉ chạy logic **reconcile**, còn dữ liệu HTTP và access logs nằm ở tài nguyên gateway Azure, không nằm trong pod controller.

### 14.2. Các lệnh quan sát không sửa workload

~~~bash
kubectl -n shop get deployments,pods,services

kubectl -n shop get ingress -o wide
kubectl -n shop get gateways,httproutes

kubectl -n shop get events \
  --sort-by=.lastTimestamp

kubectl -n shop logs deployment/catalog \
  --tail=100

kubectl -n shop logs deployment/orders \
  --tail=100
~~~

`kubectl get all` không liệt kê tất cả Kubernetes API resources, nên phải xem Ingress/Gateway/HTTPRoute/NetworkPolicy và những đối tượng khác một cách tường minh.

### 14.3. Tìm đúng controller thay vì đoán namespace

~~~bash
kubectl get ingressclass
kubectl get gatewayclass
kubectl get pods -A
kubectl get services -A
~~~

Dựa trên `IngressClass.spec.controller` hoặc `GatewayClass.spec.controllerName` để xác định implementation. Namespace controller không bắt buộc là `ingress-nginx`; không nên tự chạy `kubectl logs -n ingress-nginx` trước khi biết cluster đang dùng gì.

Nếu có Azure Application Gateway/Front Door, xem diagnostic settings, backend health và WAF logs tại **đúng tài nguyên Azure**. Nếu dùng controller proxy trong AKS, đọc logs/metrics từ controller data plane tương ứng.

### 14.4. Distributed tracing

Một request có thể đi qua:

~~~text
Client → Gateway → catalog-svc → catalog Pod → Azure SQL
~~~

Dùng OpenTelemetry/Application Insights hoặc hệ thống tương đương để theo dõi cùng trace ID:

- Thời điểm UTC, hostname/path.
- HTTP status frontend/upstream.
- Gateway/route, Service, Pod name, namespace.
- Pod version và thời gian dependency.
- Retry/timeout reason.

Không log token, private key hoặc dữ liệu người dùng nhạy cảm không cần thiết. Một dòng “502” từ gateway chưa đủ để biết bị lỗi TLS, network hay app.

### 14.5. Gợi ý cảnh báo

- 5xx/502/503 và p95/p99 latency tăng trên gateway.
- EndpointSlices của critical Service không có ready addresses.
- Pod restart, OOMKilled hoặc CrashLoopBackOff tăng.
- Controller/Gateway không reconcile hoặc route `Accepted=False`.
- TLS certificate sắp hết hạn.
- External IP/DNS trỏ sai sau thay đổi.
- Gateway/Ingress data plane CPU hoặc capacity gần trần.
- WAF blocks bất thường hoặc traffic tăng khác baseline.

Cảnh báo phải có **scope, owner, SLO và runbook**. Nhiều 404 có thể là hành vi hợp lệ của API; không mặc định 404 nào cũng là sự cố.


## 15. Playbook chẩn đoán lỗi DNS, TLS, 404, 502 và 503

Người dùng báo: `https://shop.example.com/catalog` không chạy. Trước khi sửa, hãy ghi **timestamp, hostname, path, HTTP status, client location** và thay đổi gần nhất.

### 15.1. Bảng khoanh vùng nhanh

| Triệu chứng | Giả thuyết đầu tiên | Phép kiểm tra tiếp |
| --- | --- | --- |
| `NXDOMAIN` | Tên chưa có DNS record hoặc DNS scope sai | `nslookup`, public/private DNS zone |
| TCP timeout | Frontend/network/firewall/routing | IP, listener, NSG, Azure LB/gateway |
| `ERR_CERT_COMMON_NAME_INVALID` | TLS certificate SAN không khớp hostname | SNI, cert chain, Secret hoặc Azure cert binding |
| TLS handshake failure | TLS policy, listener, cert/chain | `curl -v`, controller/gateway logs |
| HTTP 404 chỉ với một path | Ingress/HTTPRoute match không đúng hoặc backend trả 404 | Host/path rules, app route, access logs |
| HTTP 502 | Gateway không kết nối backend hoặc upstream response lỗi | Gateway backend health, port, TLS/backend log |
| HTTP 503 | Không có backend khả dụng hoặc upstream quá tải | Service ready endpoints, Pod readiness, data plane health |
| HTTP 504 | Upstream không trả response trước timeout | Request latency, dependency, gateway timeout |
| HTTP 403 | Authz/WAF/ingress policy/backend | WAF/access/app logs, policy |
| Một namespace gọi được, namespace khác không | NetworkPolicy, DNS hoặc permission | Source/destination namespace, policies, routing |

**HTTP status có thể do gateway hoặc ứng dụng sinh ra**. Không được kết luận chỉ từ một mã status mà thiếu log và route context.

### 15.2. Bước 1 — DNS và frontend

~~~bash
nslookup shop.example.com

# Chỉ khi domain và cert đã được tổ chức cấu hình:
curl -v https://shop.example.com/catalog
~~~

Nếu DNS trỏ sai IP, kiểm tra DNS record/TTL và đích ingress thực tế; đừng vội sửa container. Nếu DNS đúng nhưng TCP timeout, kiểm tra frontend listener, routing, firewall và backend health.

Khi cần kiểm tra IP đã được cấp mà DNS chưa đổi:

~~~bash
# 203.0.113.10 là địa chỉ tài liệu, phải thay bằng frontend thật.
curl -v \
  --resolve shop.example.com:443:203.0.113.10 \
  https://shop.example.com/catalog
~~~

Phép thử này giữ TLS SNI/HTTP Host đúng hostname. Không dùng `curl -k` như giải pháp production.

### 15.3. Bước 2 — Controller và route status

Với Ingress:

~~~bash
kubectl -n shop describe ingress shop-ingress
kubectl get ingressclass
~~~

Với Gateway API:

~~~bash
kubectl -n shop describe gateway shop-gateway
kubectl -n shop describe httproute shop-routes
kubectl -n shop get gateway shop-gateway -o yaml
kubectl -n shop get httproute shop-routes -o yaml
~~~

Kiểm tra:

- Class có được controller quản lý và chấp nhận không?
- Listener host/port có khớp `shop.example.com:443`?
- Route có attach đúng listener qua `parentRefs` và `sectionName`?
- Có `Accepted=True` và `ResolvedRefs=True` ở parent status không?
- Controller có báo reconcile error hoặc thiếu network/identity permission không?
- Endpoint/address thực tế của gateway là gì?

Nếu Gateway/HTTPRoute API chưa được cài, lệnh kiểm tra Gateway có thể báo resource không tồn tại; đây là dấu hiệu về CRDs, không phải DNS lỗi.

### 15.4. Bước 3 — Kiểm tra Service và EndpointSlices

~~~bash
kubectl -n shop describe service catalog-svc

kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=catalog-svc \
  -o wide

kubectl -n shop get pods \
  -l app=catalog \
  -o wide

kubectl -n shop describe deployment catalog
~~~

Nếu Service không có ready endpoints, sửa Pod, label selector, readiness hoặc startup trước. Nếu có endpoints nhưng vẫn 502/503, kiểm tra port, network policy, backend HTTP/TLS và gateway data plane.

### 15.5. Bước 4 — Kiểm tra ứng dụng theo đường nội bộ

Dùng port-forward khi được phép:

~~~bash
kubectl -n shop port-forward svc/catalog-svc 8081:80
~~~

Terminal khác:

~~~bash
curl -i http://127.0.0.1:8081/
~~~

Nếu ứng dụng phục vụ thành công qua port-forward nhưng public ingress lỗi, cần điều tra tầng gateway/controller, Azure network hoặc đường đi backend. **Port-forward không đi cùng đường mạng như gateway**, nên kết quả thành công chưa chứng minh gateway có connectivity.

### 15.6. Bước 5 — Thu thập logs và thời điểm thay đổi

~~~bash
kubectl -n shop logs deployment/catalog \
  --tail=100

kubectl -n shop get events \
  --sort-by=.lastTimestamp
~~~

Đối chiếu access logs của ingress/gateway, Azure Monitor, network policies và deployment history. Tránh restart/xóa nhiều Pods trước khi thu thập bằng chứng, trừ khi đã có runbook được phê duyệt.

### 15.7. Bước 6 — Sửa theo bằng chứng

- DNS sai → sửa record khi đã xác minh frontend IP thật.
- TLS mismatch → cấp/gắn chứng chỉ có SAN đúng hostname.
- IngressClass/GatewayClass sai → chọn controller đã được hỗ trợ.
- HTTPRoute bị từ chối → sửa hostname/parentRefs/allowedRoutes/reference grant.
- Service selector không khớp → sửa labels hoặc selector có kiểm soát.
- Readiness sai → dùng endpoint sẵn sàng đúng; không xóa probe để che lỗi.
- Gateway health probe lỗi → kiểm tra host/path/port/TLS và network.
- HTTP 504 → kiểm tra backend/dependency latency trước khi nâng timeout.
- WAF false positive → đối chiếu policy logs, sửa theo phạm vi hẹp.

### 15.8. Bước 7 — Xác minh đã phục hồi

Chỉ đóng sự cố khi:

1. DNS và certificate đúng.
2. Ingress/Gateway route được controller chấp nhận và có endpoint.
3. Service có ready backends.
4. `/catalog` và `/orders` trả body/status mong đợi.
5. 5xx/latency trở về SLO.
6. Không tạo thêm public entrypoint hoặc nới firewall ngoài ý định.
7. Alert và logging vẫn hoạt động.

## 16. Scaling, rolling updates và gateway capacity

### 16.1. Ba tầng autoscale khác nhau

- **Application Pods:** HPA/KEDA điều chỉnh số replicas theo metric/event.
- **AKS nodes:** Cluster autoscaler hoặc cơ chế node provisioning khác mở rộng năng lực chạy Pods theo cấu hình.
- **Ingress/Gateway data plane:** proxy pods hoặc gateway L7 có cơ chế/công suất scale riêng, đôi khi là Azure-managed.

Ví dụ, HPA muốn tăng `catalog` từ 2 lên 8 Pods nhưng node pool thiếu capacity; một phần Pods sẽ ở `Pending`. Ngược lại, Pods đã tăng nhưng ingress proxy nghẽn CPU hoặc gateway backend pool giới hạn thì SLO vẫn kém.

### 16.2. Ví dụ HPA theo CPU

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: catalog-hpa
  namespace: shop
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: catalog
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
~~~

Đây là ví dụ minh họa. CPU HPA cần metrics pipeline và CPU requests được khai báo; phải đo ngưỡng theo workload. HPA **không** tạo DNS, TLS cert hoặc public IP.

### 16.3. Giữ request khi rolling update

Khi scale in hoặc thay Pods:

- Pod mới cần hoàn thành readiness trước khi nhận lưu lượng.
- Pod cũ cần nhận SIGTERM và kết thúc request đang xử lý.
- EndpointSlices cập nhật khi Pod chuyển trạng thái.
- Controller/gateway có thể cần thời gian cập nhật backend.
- Với request dài, cần chú ý `terminationGracePeriodSeconds`, preStop, timeout và connection draining của data plane.

Nếu API bị ngắt request khi rollout, kiểm tra tính phối hợp giữa readiness, liveness, shutdown và gateway draining; đừng đơn giản tăng mọi timeout lên vô hạn.

### 16.4. Canary traffic

Gateway API controller có hỗ trợ **weighted backendRefs** có thể cho một tỷ lệ request vào Service canary. Với Ingress API, phương án canary thường phụ thuộc implementation-specific annotations/features.

Quy trình an toàn:

1. Deploy stable và canary Services khác nhau.
2. Kiểm tra canary Pod readiness và API contract.
3. Chuyển tỷ lệ nhỏ traffic khi controller hỗ trợ.
4. Đo 5xx, latency và lỗi nghiệp vụ theo version.
5. Tăng trọng số dần nếu SLO đạt.
6. Rollback routing khi có lỗi, nhưng tiếp tục đánh giá tác động dữ liệu.

**Rollback traffic không tự rollback schema database, queues hoặc dữ liệu đã được canary ghi.** Thiết kế API và migration tương thích nhiều phiên bản là điều kiện quan trọng.

## 17. Bảo mật Ingress và Gateway trên AKS

### 17.1. Nguyên tắc giảm bề mặt tấn công

- Chỉ public đúng frontend cần thiết, tránh public Service LoadBalancer cho backend riêng.
- Bật HTTPS, quản lý certificate chain/SAN/rotation và redirect.
- Dùng WAF/rate limiting/authentication khi phù hợp; TLS không thay authorization.
- Áp dụng Kubernetes RBAC, NetworkPolicy, admission policies và namespace isolation.
- Không để team ứng dụng tự thay đổi GatewayClass/controller hoặc public networking ngoài quyền đã phê duyệt.
- Giữ ingress/gateway controller và CRDs ở phiên bản được **nhà cung cấp hỗ trợ**, theo quy trình nâng cấp.
- Quản lý secrets và chứng chỉ bằng cơ chế có quyền tối thiểu, không commit private key.
- Ghi logs hợp lý nhưng tránh đưa credentials/PII vào access logs.

### 17.2. NetworkPolicy và phạm vi truy cập

Một backend `catalog-svc` có thể chỉ cần được truy cập từ gateway data plane và một số workloads nội bộ. **NetworkPolicy** có thể giúp giới hạn lưu lượng giữa Pods theo cơ chế CNI/NetworkPolicy engine của cluster.

Tuy nhiên:

- Traffic của **Azure-managed external L7 gateway** có thể không xuất phát từ Pod labels như ingress controller chạy trong cluster.
- Network policies thường quản lý Pod traffic trong phạm vi được hỗ trợ; Azure NSG/firewall/UDR vẫn có vai trò riêng.
- `NetworkPolicy` tạo ra chỉ tác động mong muốn khi network policy implementation của AKS được cấu hình và hoạt động phù hợp.
- Không copy một NetworkPolicy deny-all vào production mà chưa kiểm tra probe, DNS và ingress connectivity; có thể gây outage.

### 17.3. Quyền quản trị Ingress/Gateway

| Vai trò | Có thể quản lý | Không nên mặc định có |
| --- | --- | --- |
| Cluster/platform owner | GatewayClass, controller, IP, network, TLS policy | Tự đọc mọi secret nghiệp vụ của các team |
| Namespace application owner | Deployments, Services, HTTPRoutes trong namespace | Toàn bộ cluster RBAC và GatewayClass |
| Security owner | WAF, certificate lifecycle, policy, audit | Thay đổi source code ứng dụng khi không cần |
| DNS owner | Public/private DNS records | Kubernetes admin của mọi cluster |
| SRE | Logs, metrics, alert, rollback theo quyền | Owner toàn subscription |
| CI/CD identity | Apply manifests trong namespace được cấp | Quyền quản lý unrelated Azure resources |

**Gateway API giúp tách vai trò**, nhưng chính sách thực tế vẫn cần Kubernetes RBAC và admission/organizational controls. `allowedRoutes` không thay toàn bộ authorization layer.

### 17.4. Backend TLS và mTLS

Nếu chính sách yêu cầu mã hóa tới Pod, không chỉ bật certificate ở frontend rồi coi hệ thống đã có **end-to-end TLS**. Phải lựa chọn:

- HTTPS tới backend theo khả năng gateway/controller.
- Service mesh hoặc mTLS nội bộ phù hợp.
- Kiểm soát chứng chỉ, SAN/SNI và trust chain.
- Health probes dùng đúng protocol/host/port.
- Giám sát certificate expiry ở các lớp.

Đừng vô hiệu hóa TLS validation chỉ để sửa 502; cần xác định root CA, hostname và certificate chain đúng.

## 18. Chi phí và vận hành vòng đời

### 18.1. Những yếu tố phát sinh chi phí

| Thành phần | Yếu tố giá |
| --- | --- |
| AKS node pools | VM instances, CPU/RAM và disk |
| Ingress controller trên AKS | Proxy/controller Pods tiêu tốn node resources |
| Azure Load Balancer và Public IP | Frontend, data processing và IP theo bảng giá |
| Application Gateway/Application Gateway for Containers | L7 gateway capacity, networking và dịch vụ theo SKU |
| Front Door/WAF | Requests, bandwidth, rules và tính năng theo gói |
| Log Analytics/Azure Monitor | Ingestion, retention, metric/alerts |
| TLS/PKI và DNS | Managed certificate/dịch vụ DNS theo cấu hình |
| Egress/data transfer | Truyền dữ liệu giữa vùng, mạng hoặc Internet |
| Autoscaling | HPA/cluster autoscaler/gateway capacity có thể tăng chi phí |

Không kết luận “một Ingress dùng chung luôn rẻ hơn” nếu workload cần gateway managed với giá cố định cao; hãy so sánh **tổng chi phí theo nhu cầu và SLO thực tế**.

### 18.2. Chi phí của nhiều public endpoints

Mỗi `LoadBalancer` public có thể kéo theo frontend resource, public IP, DNS, TLS và chính sách riêng. Tập trung nhiều APIs qua một gateway giúp giảm chi phí quản trị nhưng cũng tạo **shared failure domain** và cần đảm bảo gateway đủ năng lực, có bảo mật và phân quyền multi-tenant.

### 18.3. Lifecycle và kiểm soát thay đổi

Trước khi nâng cluster version hoặc controller:

1. Kiểm tra API versions/CRD compatibility.
2. Kiểm tra controller support lifecycle và Gateway API feature support.
3. Snapshot/export cấu hình infrastructure như IaC theo quy trình tổ chức.
4. Thử ở staging và kiểm tra TLS/route/backend health.
5. Nâng lần lượt theo cửa sổ bảo trì.
6. Có chiến lược rollback, tránh khai báo resources đã bị loại khỏi phiên bản mục tiêu.

Đối với **Ingress** và **Gateway API**, cùng một namespace có thể tồn tại cả hai loại resources. Không mặc định cả hai cùng quản lý một hostname theo thứ tự ưu tiên rõ; cần tránh **conflicting routes/controllers**.

## 19. Bài thực hành tổng hợp: chọn Ingress hay Gateway API?

### 19.1. Yêu cầu nghiệp vụ

Một nhóm muốn công bố:

~~~text
https://shop.example.com/catalog → catalog-svc:80
https://shop.example.com/orders  → orders-svc:80
~~~

Các yêu cầu:

- Hai backend chỉ có ClusterIP, không nhận public IP riêng.
- Có HTTPS và certificate hợp lệ.
- Về lâu dài, đội platform quản lý entrypoint, đội ứng dụng quản lý từng route.
- Có kế hoạch canary một phần traffic cho `catalog`.
- Cần giám sát 5xx, readiness và chi phí.

### 19.2. Phương án A: Ingress

Dùng Ingress khi controller đã được vận hành và hỗ trợ routing/TLS cần thiết. App teams khai báo các paths theo host; các tính năng canary/redirect có thể phải dùng annotation hoặc policy theo implementation.

**Ưu điểm:** triển khai mô hình HTTP host/path quen thuộc, cấu hình đơn giản cho số ít nhóm.  
**Đánh đổi:** Ingress API cốt lõi không diễn đạt toàn bộ routing policies/role boundaries bằng các đối tượng tiêu chuẩn như Gateway API; tính năng nâng cao phụ thuộc controller.

### 19.3. Phương án B: Gateway API

Platform team tạo `GatewayClass`/`Gateway`, định nghĩa HTTPS listener và `allowedRoutes`. App team tạo `HTTPRoute` với `parentRefs`, `hostnames`, path match và backendRefs.

**Ưu điểm:** tách trách nhiệm rõ, route objects mở rộng và có weighted backendRefs theo support.  
**Đánh đổi:** phải bảo đảm Gateway API CRDs/controller được hỗ trợ, giải quyết quyền cross-namespace và nắm lifecycle GatewayClass/data plane.

### 19.4. Bảng nghiệm thu

| Kiểm tra | Kết quả mong đợi | Công cụ |
| --- | --- | --- |
| Pods healthy | Hai Deployment có replicas Ready | `kubectl get pods`, rollout status |
| Service endpoints | Hai Services có ready endpoints | `kubectl get endpointslices` |
| Controller/class | IngressClass hoặc GatewayClass hợp lệ | `kubectl get/describe` |
| Route status | Ingress có ADDRESS hoặc HTTPRoute Accepted/ResolvedRefs phù hợp | `kubectl describe`, status |
| DNS | `shop.example.com` trỏ frontend đúng | `nslookup` |
| TLS | Chứng chỉ hợp lệ với hostname | `curl -v`, kiểm tra cert |
| Host/path | `/catalog` và `/orders` tới backend đúng | `curl` |
| Internal backends | Không có public LoadBalancer ngoài ý muốn cho các backend | `kubectl get svc -A` |
| Observability | Có HTTP/access logs và metric | Azure Monitor/controller logs |
| Failure test | Khi một Pod không Ready, còn backend khỏe phục vụ | Readiness/Endpoints, test có kiểm soát |
| Canary | Tỷ lệ thử nghiệm không tạo lỗi backend | HTTPRoute weight/controller capability |
| Cost | IP/gateway/node/log charges được dự toán | Azure Pricing Calculator/Cost Management |

### 19.5. Tình huống A: Route có nhưng không chạy

`kubectl get httproute` thấy `shop-routes`, nhưng `status.parents[].conditions` có `Accepted=False`.

**Hỏi:** có nên thay DNS ngay?

**Đáp án:** chưa. Kiểm tra Gateway listener, hostname matching, `parentRefs`, `allowedRoutes`, GatewayClass/controller và events. Resource tồn tại chưa có nghĩa route đã được chấp nhận.

### 19.6. Tình huống B: TLS đúng nhưng 503

Client bắt tay TLS thành công, nhưng `GET /catalog` trả 503. `catalog-svc` có 0 ready endpoints.

**Đáp án:** kiểm tra Deployment/Pod readiness, labels, `targetPort`, image và logs; không cần sửa certificate khi bằng chứng chỉ về backend.

### 19.7. Tình huống C: Cần hai namespaces

`HTTPRoute` trong namespace `team-catalog` muốn gắn vào Gateway ở `network-system` và trỏ tới Service trong `team-catalog`.

**Đáp án:** Gateway listener phải cho phép HTTPRoute từ namespace team (theo `allowedRoutes`), còn backendRef cùng namespace HTTPRoute không cần cross-namespace ReferenceGrant. Nếu backendRef trỏ sang Service của namespace thứ ba, có thể cần ReferenceGrant do owner namespace đích cấp.

### 19.8. Tình huống D: Gateway phía sau Front Door

Một Azure Front Door có WAF đứng trước gateway AKS, nhưng backend có public IP khác vẫn mở rộng.

**Đáp án:** phải hạn chế đường truy cập trực tiếp không được ủy quyền tới origin, kiểm tra firewall/authentication và cách Front Door kết nối backend; nếu không, attacker có thể bypass WAF.

### 19.9. Dọn dẹp lab có kiểm soát

Nếu namespace `shop` **chỉ được tạo cho bài thực hành** và không chứa tài nguyên dùng chung, có thể kiểm tra:

~~~bash
kubectl -n shop get deployments,services,ingresses
kubectl -n shop get gateways,httproutes
kubectl -n shop get secrets
~~~

Chỉ sau khi xác minh tất cả resources thuộc lab và được phép xóa:

~~~bash
# THAO TÁC PHÁ HỦY trong namespace lab, không chạy trên Prod.
kubectl delete namespace shop
~~~

Đừng xóa Ingress/Gateway controller, GatewayClass, Application Gateway, Azure Front Door hoặc public IP dùng chung của tổ chức. Một tài nguyên Azure gateway có thể còn tồn tại và tính phí sau khi xóa namespace, tùy integration/controller.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `Service.type=ClusterIP` có thể được Internet truy cập trực tiếp không?

**Đáp án:** Không theo mô hình service nội bộ thông thường. Muốn công bố, cần một đường vào được cấu hình như LoadBalancer, Ingress/Gateway hoặc gateway ngoài cluster.

**Câu 2.** Tạo một Ingress object có bảo đảm AKS tự sinh public IP và HTTPS không?

**Đáp án:** Không. Cần Ingress controller, IngressClass, frontend networking, DNS, certificate và routing phù hợp. Ingress là API khai báo.

**Câu 3.** Khác biệt chính giữa Ingress và Gateway API là gì?

**Đáp án:** Ingress cung cấp quy tắc HTTP/HTTPS host/path tương đối đơn giản; Gateway API có mô hình GatewayClass/Gateway/routes tách quyền sở hữu và nhiều khả năng route/filter theo implementation.

**Câu 4.** `GatewayClass` có nhiệm vụ chạy container ứng dụng không?

**Đáp án:** Không. Nó lựa chọn gateway controller/implementation; Deployment/Pods và Services mới chứa đường phục vụ ứng dụng.

**Câu 5.** `HTTPRoute` ở namespace khác muốn gắn vào Gateway có cần gì?

**Đáp án:** Gateway listener phải cho phép routes ở namespace đó qua `allowedRoutes`; tên/hostname/parentRefs cũng phải phù hợp.

**Câu 6.** `ReferenceGrant` giải quyết vấn đề nào?

**Đáp án:** Cho phép một số references xuyên namespace, ví dụ HTTPRoute trỏ Service ở namespace khác, theo quyền owner resource đích. Nó không thay `allowedRoutes` cho việc attach route.

**Câu 7.** Khi Gateway API `ResolvedRefs=False`, bạn kiểm tra gì?

**Đáp án:** Tên Service, port, namespace, Secret và các điều kiện ReferenceGrant/permission tương ứng.

**Câu 8.** Một Pod Ready nhưng gateway báo unhealthy; có mâu thuẫn không?

**Đáp án:** Không. Readiness của Kubernetes và health check của gateway là những phép kiểm tra khác nhau, có thể dùng host/path/protocol/network khác.

**Câu 9.** Vì sao Service có selector không khớp Pods sẽ gây lỗi dù Ingress đúng?

**Đáp án:** Service không có ready endpoints để chuyển request; controller/gateway không có backend thực sự.

**Câu 10.** HPA tăng số Pods thì ingress data plane có tự tăng capacity không?

**Đáp án:** Không mặc định. App Pods, AKS nodes và ingress/gateway data plane có cơ chế scaling/giới hạn độc lập.

**Câu 11.** Chứng chỉ TLS Secret của một Ingress thường thuộc namespace nào?

**Đáp án:** Cùng namespace với Ingress theo mô hình Kubernetes Ingress TLS. Với Gateway API, certificateRefs/namespace rules tuân theo Gateway implementation và reference permissions.

**Câu 12.** Vì sao `curl --resolve` hữu ích hơn gọi `https://<IP>` khi chẩn đoán HTTPS theo hostname?

**Đáp án:** `--resolve` ép kết nối đến IP cần thử nhưng vẫn giữ hostname ở URL để TLS SNI và HTTP Host được gửi đúng.

**Câu 13.** Azure Application Gateway với AGIC và Application Gateway for Containers có phải cùng một sản phẩm không?

**Đáp án:** Không. Chúng có data plane, controller/integration và phạm vi tính năng riêng; phải chọn công nghệ phù hợp phiên bản và nhu cầu thực.

**Câu 14.** Nếu mục tiêu là công bố API ở nhiều region, cần xem thêm gì ngoài Ingress/Gateway trong một AKS cluster?

**Đáp án:** Global routing như Azure Front Door, WAF, DNS, health failover, backend isolation, replication dữ liệu, SLO và chính sách vận hành đa vùng.

## Ghi nhớ

- **Pod** chạy ứng dụng; **Service ClusterIP** cung cấp backend ổn định; **Ingress/Gateway API** khai báo cách truy cập HTTP/HTTPS theo host/path.
- **Ingress/Gateway resource không tự tạo dataplane**: phải có controller implementation, networking và địa chỉ frontend phù hợp.
- **IngressClass** chọn Ingress controller; **GatewayClass/Gateway/HTTPRoute** tách việc quản lý gateway và routes.
- **Gateway API** cung cấp điều kiện `Accepted`, `ResolvedRefs` và các trạng thái khác để xác minh controller đã chấp nhận cấu hình.
- **DNS, TLS, ingress controller, Kubernetes Services, EndpointSlices và Pods** là các lớp độc lập cần kiểm tra khi gặp lỗi.
- **Public/private ingress khác private AKS API server**; công bố backend phải gắn với bảo mật mạng, authentication và WAF.
- Quyết định giữa AKS application routing, AGIC, Application Gateway for Containers và Gateway API phải dựa vào **khả năng hỗ trợ, mô hình vận hành, bảo mật và chi phí**.
- Khi xử lý sự cố, đi từ **client/DNS → frontend/TLS → Ingress/Gateway status → Service endpoints → Pod → dependency**, rồi kiểm chứng SLO sau khi sửa.
