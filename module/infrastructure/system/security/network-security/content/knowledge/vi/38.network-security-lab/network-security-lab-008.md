# Tạo chính sách egress cho workload

## 1. Bối cảnh bài lab và mục tiêu

**Egress** là lưu lượng đi **ra khỏi một workload** tới một workload khác, dịch vụ nội bộ, DNS resolver, Internet hoặc hạ tầng quản trị. Một ứng dụng chỉ cần gọi Payment API có thể không cần quyền kết nối tùy ý tới mọi máy trong mạng hoặc mọi địa chỉ ngoài Internet. **Chính sách egress** giới hạn các đích, giao thức và cổng mà workload được phép kết nối; khi được kết hợp với danh tính, phân đoạn mạng, firewall, VPN, IDS/IPS và logging, nó giảm phạm vi hoạt động nếu một workload bị cấu hình sai hoặc bị xâm nhập.

Trong chương **Dự án thực hành bảo mật mạng** thuộc mô-đun **SECURITY_NETWORK_SECURITY**, bài lab này hướng dẫn thiết kế, triển khai và xác minh một egress policy theo nguyên tắc **default deny + explicit allow**. Môi trường chính là **Kubernetes NetworkPolicy**, một cách thực hành rõ ràng để phân tách workload động. Cuối bài cũng trình bày cách ánh xạ yêu cầu sang VM, cloud security group, egress firewall và proxy khi cần kiểm soát theo hostname.

**Tình huống giả định:** Pod **lab-client** là workload xử lý đơn hàng, chỉ được phép gọi **approved-api** qua TCP/8080 và thực hiện phân giải DNS cần thiết. Một ứng dụng khác là **unapproved-api** tồn tại trong cùng cụm nhưng **không được phép nhận kết nối từ lab-client**. Hai dịch vụ đều là endpoint mô phỏng trong lab, không chứa dữ liệu thực.

Sau khi hoàn thành, người học có thể:

1. Xác định **luồng egress được phép**, luồng bị cấm và những dịch vụ nền thường bị bỏ quên.
2. Tạo NetworkPolicy chỉ chọn đúng Pod nguồn, thay vì chặn nhầm toàn bộ namespace.
3. Thiết lập **default deny egress**, sau đó mở riêng DNS và một API đã phê duyệt.
4. Giải thích ngữ nghĩa **namespaceSelector + podSelector**, cổng TCP/UDP và tính cộng dồn của nhiều NetworkPolicy.
5. Thực hiện **positive test, negative test, kiểm tra DNS, quan sát log và kiểm tra drift**.
6. Nhận biết giới hạn của NetworkPolicy: CNI phải hỗ trợ, DNS có thể đi qua NodeLocal DNS, policy chuẩn không match FQDN, và L3/L4 không thay thế authorization ứng dụng.
7. Chuẩn bị kế hoạch triển khai production an toàn, rollback, bằng chứng nghiệm thu và báo cáo.

**Giới hạn an toàn:** chỉ triển khai trên cluster lab hoặc namespace/tài sản được chủ sở hữu cấp quyền. Không áp default deny egress trực tiếp cho namespace production đang chạy khi chưa kiểm kê đầy đủ phụ thuộc và có phương án khôi phục.

## 2. Egress policy bảo vệ điều gì và không bảo vệ điều gì?

| Năng lực | Egress NetworkPolicy chuẩn có thể làm | Không tự giải quyết |
| --- | --- | --- |
| Hạn chế Pod nguồn | Chọn Pod theo nhãn trong namespace áp policy | Xác thực người dùng cuối đang gọi API |
| Giới hạn điểm đến | Pod/namespace selector, CIDR/IP block theo khả năng CNI | Danh sách tên miền động bằng FQDN trong API NetworkPolicy chuẩn |
| Giới hạn giao thức/cổng | TCP, UDP, SCTP và port nếu nền tảng/CNI hỗ trợ | Phân quyền theo HTTP method, URI, object hoặc dữ liệu |
| Giảm lateral movement | Ngăn những kết nối không được khai báo từ Pod được chọn | Ngăn mọi kỹ thuật di chuyển ngang nếu các đường khác còn mở |
| Hỗ trợ kiểm toán | Có thể đối chiếu policy và telemetry CNI/flow | NetworkPolicy API không tự tạo log allow/deny chuẩn thống nhất |
| Phòng thủ nhiều lớp | Phối hợp ingress policy, IAM, mTLS, DB role, egress proxy | Thay thế hoàn toàn firewall biên, cloud IAM, WAF hay EDR |

**L3/L4 reachability khác L7 authorization.** Nếu Pod được phép kết nối TCP/8080 tới approved-api, điều đó chưa chứng minh Pod được quyền đọc một đơn hàng hoặc thay đổi giao dịch cụ thể. Approved-api vẫn cần xác thực, ủy quyền nghiệp vụ, kiểm tra đầu vào và logging phù hợp.

### 2.1. Egress là khái niệm phụ thuộc điểm quan sát

Từ lab-client, traffic tới DNS hoặc approved-api là **egress**. Đối với approved-api, cùng kết nối đó là **ingress**. Trong Kubernetes, các policy chọn Pod nguồn/đích được đánh giá theo chiều tương ứng. Nếu cả hai đầu đều bị cô lập bởi policy, phải có điều kiện **egress ở nguồn** và **ingress ở đích** cho phép luồng.

Kết quả packet capture trên node, flow log ở VPC, service-mesh access log và firewall biên có thể thấy các địa chỉ/port khác nhau do NAT, Service VIP, proxy hoặc overlay. Bản thiết kế phải ghi rõ **đang kiểm soát đường nào**.

## 3. Kiến trúc lab và ma trận quyền truy cập

~~~mermaid
flowchart LR
    subgraph LE["Namespace lab-egress"]
        C["Pod lab-client\nrole=restricted-client"]
        NP["Default-deny + allow-egress\nNetworkPolicy"]
    end
    subgraph LS["Namespace lab-services"]
        A["Pod approved-api\napp=approved-api\nTCP/8080"]
        B["Pod unapproved-api\napp=unapproved-api\nTCP/8080"]
    end
    subgraph SYS["Namespace kube-system"]
        DNS["Cluster DNS\nUDP/TCP 53"]
    end
    C -. "Policy chọn Pod nguồn" .-> NP
    C -->|"Cho phép TCP/8080"| A
    C -. "Từ chối theo egress policy" .-> B
    C -->|"Cho phép UDP/TCP 53"| DNS
~~~

Đây là sơ đồ **logic của các Pod**, chưa phải sơ đồ Service NAT, đường vật lý hoặc những thành phần nằm trong CNI dataplane. Dấu mũi tên tới unapproved-api chỉ một **luồng kiểm thử cần bị ngăn**, không phải một kết nối thành công.

### 3.1. Ma trận yêu cầu trước khi viết YAML

| Mã | Nguồn | Đích | Giao thức/cổng | Yêu cầu | Lý do |
| --- | --- | --- | --- | --- | --- |
| E01 | lab-client | Cluster DNS phù hợp cấu hình thực tế | UDP/53, TCP/53 | **Allow** | Phân giải tên Service |
| E02 | lab-client | approved-api trong lab-services | TCP/8080 | **Allow** | Gọi API được phê duyệt |
| E03 | lab-client | unapproved-api trong lab-services | TCP/8080 | **Deny** | Không nằm trong danh mục phụ thuộc |
| E04 | lab-client | Pod khác không có rule cho phép | TCP/8080 và cổng khác | **Deny** | Giảm quyền theo mặc định |
| E05 | lab-client | Đích ngoài cluster chưa được phê duyệt | TCP/443 hoặc giao thức khác | **Deny** | Không có nhu cầu Internet trong lab |
| E06 | lab-client | approved-api nhưng sai cổng | TCP/9090 | **Deny** | Chỉ mở cổng cần thiết |

**Giả định của lab:** các Pod đích không có ingress policy chặn traffic và CNI hỗ trợ Kubernetes NetworkPolicy. Nếu đã tồn tại policy khác chọn cùng Pod, kết quả phải được phân tích trên **hợp các rule cho phép**, không dựa vào một YAML đơn lẻ.

### 3.2. Tại sao dùng hai namespace?

Hai namespace tạo bối cảnh thực hành phân biệt rõ **nguồn** và **đích**. Việc chọn endpoint theo **namespace label kết hợp Pod label** cho thấy cách cấp quyền chính xác hơn một rule cho toàn bộ namespace.

Namespace không tự là ranh giới an ninh tuyệt đối: có thể cùng node, cùng cluster DNS, cùng control plane và phụ thuộc CNI. Kỹ thuật này minh họa **network segmentation theo workload**, không phải cô lập multi-tenant hoàn chỉnh.

## 4. Điều kiện tiên quyết và preflight an toàn

Chuẩn bị một Kubernetes cluster **thử nghiệm**, quyền tạo namespace, Pod, Service và NetworkPolicy; có client **kubectl** kết nối đúng context. Cluster phải dùng **CNI có thực thi NetworkPolicy**. Không phải mọi cluster lab tạo từ công cụ phổ biến đều tự cung cấp engine NetworkPolicy; nếu CNI không hỗ trợ, Kubernetes vẫn có thể nhận YAML nhưng lưu lượng **không bị lọc**.

### 4.1. Kiểm tra đúng cluster trước khi thay đổi

~~~bash
# Các lệnh đọc thông tin, không tạo resource.
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
kubectl get namespaces
kubectl get networkpolicies --all-namespaces
~~~

Nếu context trỏ tới production hoặc cluster không thuộc quyền thử nghiệm, **dừng**. Không tự đổi context sang môi trường khác nếu chưa kiểm chứng. Đánh giá nhà cung cấp CNI bằng inventory/documentation của cluster và xác nhận bằng **negative test thực tế**, không chỉ bằng việc API nhận tài nguyên NetworkPolicy.

### 4.2. Kiểm tra tên namespace và quyền

Hai namespace dùng trong lab là **lab-egress** và **lab-services**. Trước khi tạo, xác minh chúng chưa thuộc workload khác:

~~~bash
kubectl get namespace lab-egress
kubectl get namespace lab-services
~~~

Nếu namespace tồn tại và có tài nguyên của người khác, **không áp manifest hoặc xóa namespace**. Dùng một cluster lab riêng hoặc phối hợp đổi tên có phê duyệt, và phải điều chỉnh toàn bộ nhãn/selector tương ứng.

### 4.3. Kiểm tra DNS và nhãn của CoreDNS

Ví dụ allow DNS trong bài giả định DNS Pod có nhãn **k8s-app=kube-dns** trong namespace **kube-system**, như nhiều cluster sử dụng. Cần xác minh **trước khi áp policy**:

~~~bash
kubectl -n kube-system get pods -l k8s-app=kube-dns --show-labels
kubectl -n kube-system get services -o wide
~~~

Nếu cluster dùng nhãn khác, **NodeLocal DNSCache**, DNS resolver bên ngoài Pod hoặc một cơ chế tùy biến, YAML allow DNS ở phần sau cần sửa theo **đích DNS thật và cách CNI xử lý traffic tới Service IP**. Không giả định nhãn, IP hay tên dịch vụ DNS giống nhau trên mọi cluster.

## 5. Tạo các workload mô phỏng

Tạo một tệp lab có tên **lab-resources.yaml** từ đoạn YAML sau. Nó chỉ tạo namespace, một Pod client, hai Pod HTTP test và hai Kubernetes Service **trong namespace lab**. Không chứa credential, token, kết nối Internet hoặc endpoint dữ liệu thật.

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: lab-egress
  labels:
    lab-purpose: egress-training
---
apiVersion: v1
kind: Namespace
metadata:
  name: lab-services
  labels:
    lab: egress-demo-services
    lab-purpose: egress-training
---
apiVersion: v1
kind: Pod
metadata:
  name: lab-client
  namespace: lab-egress
  labels:
    role: restricted-client
spec:
  containers:
    - name: shell
      image: busybox:1.36
      command: ["sh", "-c", "sleep 36000"]
      resources:
        requests:
          cpu: 10m
          memory: 16Mi
        limits:
          cpu: 100m
          memory: 64Mi
---
apiVersion: v1
kind: Pod
metadata:
  name: approved-api
  namespace: lab-services
  labels:
    app: approved-api
spec:
  containers:
    - name: web
      image: busybox:1.36
      command: ["sh", "-c"]
      args:
        - |
          mkdir -p /www
          echo APPROVED > /www/index.html
          exec httpd -f -p 8080 -h /www
      ports:
        - containerPort: 8080
      resources:
        requests:
          cpu: 10m
          memory: 16Mi
        limits:
          cpu: 100m
          memory: 64Mi
---
apiVersion: v1
kind: Service
metadata:
  name: approved-api
  namespace: lab-services
spec:
  selector:
    app: approved-api
  ports:
    - name: http
      port: 8080
      targetPort: 8080
      protocol: TCP
---
apiVersion: v1
kind: Pod
metadata:
  name: unapproved-api
  namespace: lab-services
  labels:
    app: unapproved-api
spec:
  containers:
    - name: web
      image: busybox:1.36
      command: ["sh", "-c"]
      args:
        - |
          mkdir -p /www
          echo UNAPPROVED > /www/index.html
          exec httpd -f -p 8080 -h /www
      ports:
        - containerPort: 8080
      resources:
        requests:
          cpu: 10m
          memory: 16Mi
        limits:
          cpu: 100m
          memory: 64Mi
---
apiVersion: v1
kind: Service
metadata:
  name: unapproved-api
  namespace: lab-services
spec:
  selector:
    app: unapproved-api
  ports:
    - name: http
      port: 8080
      targetPort: 8080
      protocol: TCP
~~~

**Lưu ý môi trường:** các Pod ví dụ dùng BusyBox và HTTP plaintext **chỉ để chứng minh kết nối trong lab cô lập**. Trong production phải áp dụng image digest được phê duyệt, image scanning, non-root, read-only root filesystem nếu phù hợp, TLS/mTLS, authentication và chính sách Pod Security. Nếu cluster chặn image hoặc không hỗ trợ applet **httpd** của image đã chọn, phải sửa môi trường lab hoặc dùng một HTTP test image đã được quản trị; không tự mở quyền production để làm chạy ví dụ.

### 5.1. Triển khai và kiểm tra readiness

~~~bash
kubectl apply -f lab-resources.yaml

kubectl -n lab-egress wait \
  --for=condition=Ready pod/lab-client --timeout=180s

kubectl -n lab-services wait \
  --for=condition=Ready \
  pod/approved-api pod/unapproved-api --timeout=180s

kubectl -n lab-egress get pods -o wide --show-labels
kubectl -n lab-services get pods,services -o wide --show-labels
~~~

Các câu lệnh có thể cần điều chỉnh đối với hệ thống triển khai bằng GitOps hoặc có admission policy riêng. Nếu Pod chưa Ready, điều tra image pull, scheduler, container logs và resource quota trước khi thử chính sách.

## 6. Đo baseline trước khi bật egress deny

**Không đặt policy trước khi chứng minh lab hoạt động bình thường.** Trước khi thêm NetworkPolicy, kiểm tra DNS và hai HTTP Service:

~~~bash
# Phân giải tên service qua cluster DNS.
kubectl -n lab-egress exec lab-client -- \
  nslookup approved-api.lab-services.svc.cluster.local

# Hai đích đều truy cập được trong baseline lab không có policy chặn.
kubectl -n lab-egress exec lab-client -- \
  wget -q -T 3 -O - \
  http://approved-api.lab-services.svc.cluster.local:8080/

kubectl -n lab-egress exec lab-client -- \
  wget -q -T 3 -O - \
  http://unapproved-api.lab-services.svc.cluster.local:8080/
~~~

**Kỳ vọng khi chưa có policy liên quan:** lần lượt có phản hồi DNS, nội dung **APPROVED** và **UNAPPROVED**. Nếu cluster đã có network policies, mesh policy hoặc firewall can thiệp, baseline có thể khác. **Không tiếp tục tới bước default deny khi chưa hiểu nguyên nhân baseline không đạt.**

Ghi lại thời gian UTC, cluster context, CNI, nhãn Pod/namespace và kết quả lệnh. Các kết quả này là **control observations** để phân biệt lỗi của policy mới với lỗi sẵn có.

### 6.1. Kiểm tra service thực sự trỏ tới Pod đúng

~~~bash
kubectl -n lab-services get endpointslices \
  -l kubernetes.io/service-name=approved-api
kubectl -n lab-services get endpointslices \
  -l kubernetes.io/service-name=unapproved-api
~~~

Khi service không có endpoint hợp lệ, lỗi kết nối không chứng minh NetworkPolicy chặn; phải xử lý lại selector, readiness và listener trước.

## 7. Bước 1: thiết lập default deny egress

Tạo tệp **egress-default-deny.yaml**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress-for-client
  namespace: lab-egress
spec:
  podSelector:
    matchLabels:
      role: restricted-client
  policyTypes:
    - Egress
  egress: []
~~~

### 7.1. Đọc chính xác từng trường

- **metadata.namespace:** policy tồn tại trong **lab-egress** và chỉ có thể chọn Pod nguồn thuộc namespace đó.
- **podSelector.matchLabels.role:** chỉ Pod có nhãn **role=restricted-client** bị chọn, không phải mọi Pod trong namespace.
- **policyTypes: Egress:** yêu cầu cô lập egress của Pod được chọn; **không tự thay đổi ingress isolation** của những Pod này.
- **egress: []:** policy này không định nghĩa bất kỳ luồng egress nào được phép.

Điểm rất quan trọng: các Kubernetes NetworkPolicy **có tính cộng dồn ở các quy tắc allow**. Một policy default deny làm Pod được chọn trở thành egress-isolated, nhưng nếu **một NetworkPolicy khác cũng chọn Pod** và cho phép một đích, luồng đó vẫn có thể được phép. Trong NetworkPolicy chuẩn, không có thứ tự đánh giá rule kiểu "deny luôn ưu tiên hơn allow". Vì vậy, muốn chứng minh default deny có hiệu lực, phải biết tất cả các policy đang chọn Pod.

### 7.2. Áp vào Pod thử nghiệm

~~~bash
kubectl apply -f egress-default-deny.yaml
kubectl -n lab-egress get networkpolicies
kubectl -n lab-egress describe networkpolicy \
  default-deny-egress-for-client
~~~

Đợi CNI reconcile rồi thử lại kết nối ở bước baseline. Nếu hiện tượng nhất thời không ổn định, đọc log/health của CNI và kiểm tra trạng thái thực thi; **API server chấp nhận YAML không chứng minh dataplane đã chặn**.

### 7.3. Kỳ vọng sau default deny

| Phép thử | Kỳ vọng |
| --- | --- |
| DNS query của lab-client tới cluster DNS | Không thành công qua egress path bị cô lập |
| HTTP tới approved-api | Không thành công |
| HTTP tới unapproved-api | Không thành công |
| Ingress tới lab-client | Không bị thay đổi bởi **chính policy Egress** này |

DNS có thể thất bại trước khi ứng dụng thử mở TCP, nên **không thể dùng một lỗi phân giải tên duy nhất để kết luận đã chặn đúng HTTP**. Nếu cần tách nguyên nhân, dùng IP Pod được xác minh trong lab hoặc xem telemetry CNI. Một số ngoại lệ Node/host-network/DNS đặc thù có thể khiến kết quả khác; phải ghi rõ thay vì suy đoán.

## 8. Bước 2: chỉ cho phép DNS và approved-api

Tạo tệp **egress-allow.yaml**. Policy thứ hai chọn **cùng nhóm Pod nguồn**, cho phép DNS theo nhãn Pod cụ thể và TCP/8080 tới **approved-api** trong namespace **lab-services**.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-and-approved-api
  namespace: lab-egress
spec:
  podSelector:
    matchLabels:
      role: restricted-client
  policyTypes:
    - Egress
  egress:
    # Ngoại lệ DNS: nhãn DNS Pod phải được xác minh trong cluster.
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53

    # Chỉ kết nối các Pod approved-api ở namespace lab-services.
    - to:
        - namespaceSelector:
            matchLabels:
              lab: egress-demo-services
          podSelector:
            matchLabels:
              app: approved-api
      ports:
        - protocol: TCP
          port: 8080
~~~

### 8.1. Vì sao selector phải viết đúng cấp thụt lề?

Trong rule egress thứ hai, **namespaceSelector và podSelector cùng nằm trong một phần tử danh sách to**, vì vậy đích phải thỏa **cả hai điều kiện**:

~~~text
namespace có label lab=egress-demo-services
          AND
pod trong namespace đó có label app=approved-api
          AND
traffic dùng TCP destination port 8080
~~~

Nếu vô tình đặt **namespaceSelector** và **podSelector** thành **hai phần tử khác nhau** trong danh sách **to**, NetworkPolicy sẽ cho phép lưu lượng khớp **bất kỳ phần tử nào**, khiến phạm vi rộng hơn dự kiến.

Ví dụ **không đúng với yêu cầu lab**:

~~~yaml
# CHỈ ĐỂ NHẬN BIẾT SAI LẦM, KHÔNG ÁP DỤNG!
to:
  - namespaceSelector:
      matchLabels:
        lab: egress-demo-services
  - podSelector:
      matchLabels:
        app: approved-api
~~~

Cách viết sai này cho phép traffic đến **tất cả Pod trong namespace được chọn**, **hoặc** các Pod có nhãn **app=approved-api trong cùng namespace với NetworkPolicy**; hai điều kiện không còn được kết hợp thành một tập đích duy nhất.

### 8.2. DNS cần điều chỉnh theo thực tế

Rule DNS dựa trên **namespace kube-system** và Pod có nhãn **k8s-app=kube-dns**. Trước khi áp, phải kiểm tra:

- Có đúng Pod DNS được chọn không?
- Pod dùng resolver nào trong **/etc/resolv.conf**?
- Có NodeLocal DNSCache ở địa chỉ link-local, DNS proxy của service mesh hoặc resolver ngoài cluster không?
- CNI áp rule theo địa chỉ Pod, Service ClusterIP trước/sau DNAT hay đường host-network như thế nào?

Các chi tiết này ảnh hưởng khả năng egress tới DNS. **Nếu lab sử dụng một topology khác, phải sửa rule theo chính nguồn DNS thực được phép**. Không mở toàn bộ **kube-system** hoặc mọi IP/UDP chỉ để xử lý DNS thất bại nếu chưa đánh giá phạm vi quyền.

### 8.3. Áp và xác minh policy

~~~bash
kubectl apply -f egress-allow.yaml
kubectl -n lab-egress get networkpolicies -o wide
kubectl -n lab-egress describe networkpolicy \
  allow-dns-and-approved-api
~~~

Vì policy allow có tính cộng dồn, kết hợp **default-deny-egress-for-client** và **allow-dns-and-approved-api** sẽ đưa Pod lab-client tới trạng thái: cô lập egress và chỉ có **hai nhóm ngoại lệ** được mô tả trong cấu hình, giả sử không có policy khác cấp thêm quyền.

## 9. Kiểm thử positive và negative

### 9.1. Positive test: DNS hoạt động

~~~bash
kubectl -n lab-egress exec lab-client -- \
  cat /etc/resolv.conf

kubectl -n lab-egress exec lab-client -- \
  nslookup approved-api.lab-services.svc.cluster.local
~~~

**Kỳ vọng:** tên service phân giải thành ClusterIP phù hợp. Nếu thất bại, điều tra DNS resolver và selector trước; không vội kết luận API bị NetworkPolicy chặn.

### 9.2. Positive test: approved-api truy cập được

~~~bash
kubectl -n lab-egress exec lab-client -- \
  wget -q -T 3 -O - \
  http://approved-api.lab-services.svc.cluster.local:8080/
~~~

**Kỳ vọng:** có phản hồi **APPROVED**. Đây là bằng chứng client kết nối và ứng dụng thử nghiệm phản hồi trong thời điểm kiểm tra, không phải chứng nhận mọi API được ủy quyền hay toàn bộ kết nối tương lai đều an toàn.

### 9.3. Negative test: unapproved-api bị ngăn

~~~bash
# Trường hợp này được kỳ vọng thất bại, không sửa policy để "làm xanh" test.
kubectl -n lab-egress exec lab-client -- \
  wget -q -T 3 -O - \
  http://unapproved-api.lab-services.svc.cluster.local:8080/
~~~

**Kỳ vọng:** không thiết lập được giao tiếp ứng dụng với unapproved-api. Một lệnh **wget** thất bại có thể do DNS, server chưa Ready hoặc mạng nền; muốn chứng minh nguyên nhân đúng là egress policy, phải đối chiếu **baseline thành công trước khi áp policy**, trạng thái server, EndpointSlice và, nếu CNI hỗ trợ, log quyết định deny.

### 9.4. Negative test: truy cập approved-api qua cổng khác

~~~bash
kubectl -n lab-egress exec lab-client -- \
  wget -q -T 3 -O - \
  http://approved-api.lab-services.svc.cluster.local:9090/
~~~

**Kỳ vọng:** không được phép kết nối tới cổng 9090 theo policy. Tuy nhiên, server trong lab cũng không lắng nghe cổng này, vì vậy **test thất bại không chứng minh riêng NetworkPolicy đã chặn cổng 9090**. Để kiểm chứng cổng bị chặn một cách độc lập, dùng một listener thử nghiệm có chủ đích trên cổng 9090 và một nguồn đối chứng không bị cô lập, hoặc xem flow-deny telemetry của CNI.

### 9.5. Ghi bảng kết quả

| Test | Trước policy | Sau default deny | Sau allow policy | Ghi chú |
| --- | --- | --- | --- | --- |
| DNS cho service lab | Thành công | Dự kiến thất bại | Thành công nếu DNS selector hợp lệ | Phụ thuộc topology DNS |
| HTTP tới approved-api:8080 | Thành công | Thất bại | **Thành công** | Positive egress |
| HTTP tới unapproved-api:8080 | Thành công | Thất bại | **Thất bại** | Negative egress |
| HTTP tới approved-api:9090 | Thất bại vì không có listener | Thất bại | Thất bại | Không đủ để quy nguyên nhân cho policy |

Kết quả thực tế phải ghi **UTC timestamp, cluster, CNI/version, policy YAML/UID, Pod IP, Service IP, exit code và logs**, không chỉ ghi PASS/FAIL chung chung.

## 10. Diễn giải đúng cơ chế Kubernetes NetworkPolicy

### 10.1. Các policy cộng dồn, không có thứ tự ưu tiên deny/allow

Khi một Pod bị chọn bởi một hay nhiều policy có **policyTypes: Egress**, nó được egress-isolated. Các kết nối được phép là **hợp của các egress rule cho phép** từ mọi NetworkPolicy chọn Pod đó. Một default-deny policy không có quyền phủ quyết một allow policy khác.

Vì vậy, nếu một nhóm khác bổ sung:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: broad-allow-example
  namespace: lab-egress
spec:
  podSelector:
    matchLabels:
      role: restricted-client
  policyTypes:
    - Egress
  egress:
    - {}
~~~

thì **đây là ví dụ PHẢI TRÁNH**, bởi **egress: - {}** cho phép mọi đích, port/protocol được biểu đạt bởi rule rỗng, làm mất tác dụng giới hạn của hai policy trước. **Không áp manifest minh họa sai này** vào lab hoặc production. Khi review, luôn liệt kê **mọi policy chọn Pod nguồn**.

### 10.2. Ingress và egress là hai chiều độc lập

Một policy egress trên lab-client không ngăn các Pod khác mở kết nối **tới lab-client**. Nếu approved-api có ingress policy chọn nó, cần thêm rule ingress cho nguồn lab-client. Khi cả hai phía được cô lập, phải được phép từ **cả hai chiều policy**. Stateful behavior và response traffic do CNI thực thi theo network policy semantics; không cần viết một rule egress riêng cho từng gói phản hồi của cùng kết nối thông thường.

### 10.3. Selector không phải danh tính mật mã

Nhãn **role=restricted-client** và **app=approved-api** là metadata của Kubernetes. Người hoặc controller có quyền sửa Pod labels hoặc tạo Pod trong namespace có thể tác động cách policy chọn workload. Vì vậy **RBAC, admission control, namespace ownership và audit** phải hạn chế ai có quyền tạo/sửa nhãn hoặc policy. NetworkPolicy không thay thế workload identity, mTLS hay authorization ứng dụng.

### 10.4. Các ngoại lệ theo nền tảng

NetworkPolicy chuẩn tập trung vào traffic Pod và không phải giải pháp đầy đủ cho mọi traffic **hostNetwork**, node-local, host-to-pod, overlay, service-mesh hoặc control plane. Tính năng bổ sung của CNI có thể khác nhau. Kiểm thử phải diễn ra trên **đúng cluster/CNI/version** cần bảo vệ; không khái quát từ một lab khác.

## 11. DNS là phụ thuộc dễ làm đứt ứng dụng nhất

Nhiều nhóm áp default deny egress rồi chỉ mở TCP/443 tới API, khiến ứng dụng **không phân giải được hostname**. Trong Kubernetes, Pod thường được cấu hình dùng một cluster DNS Service, nhưng đường đi thật có thể khác vì cache, node-local DNS, custom DNS hoặc service mesh.

### 11.1. Những câu hỏi cần trả lời

1. Resolver trong Pod là IP nào, từ đâu được inject?
2. CNI nhìn thấy DNS Service IP hay Pod IP sau DNAT?
3. DNS Pod có ở namespace và nhãn mà policy đang chọn không?
4. Có dùng **UDP/53 và TCP/53** không?
5. Có DNS-over-HTTPS hoặc DNS-over-TLS do workload chủ động sử dụng không?
6. Có nhiều view/split DNS, search suffix hoặc resolver failover không?

Allow UDP/TCP 53 tới cluster DNS **không tự bảo đảm mọi hostname bên ngoài được phép truy cập**. DNS resolution và kết nối tới địa chỉ trả về là hai hành động khác nhau, chịu các policy khác nhau.

### 11.2. Tại sao không nên allow 0.0.0.0/0:53?

Rule đó có thể cho workload gửi DNS query tới **bất kỳ resolver IPv4 nào**, kể cả resolver không được quản trị, làm mất khả năng giám sát và chính sách DNS nội bộ. Một workload có thể dùng giao thức DNS hoặc kênh mã hóa để truyền metadata; phạm vi đích cần được giới hạn ở resolver phù hợp, kết hợp DNS security logging và kiểm soát truy cập.

Đừng dùng wildcard DNS/network allowance như một bản vá tạm không có thời hạn. Nếu bắt buộc có exception, phải ghi owner, mục đích, expiry, rủi ro và kế hoạch thay bằng rule cụ thể.

## 12. Egress tới Internet: vì sao không thể chỉ dựa vào FQDN trong NetworkPolicy chuẩn?

Một yêu cầu production thường là "workload chỉ được gọi **api.partner.example** qua HTTPS". Tuy nhiên, **Kubernetes NetworkPolicy API chuẩn** không có trường cho phép biểu đạt policy theo FQDN, HTTP Host, URL path hoặc TLS SNI. Các quy tắc kiểu **ipBlock** làm việc với CIDR; địa chỉ của SaaS/CDN có thể thay đổi, dùng chung cho nhiều tenant và không đồng nhất với danh tính dịch vụ.

### 12.1. Các phương án kiến trúc

| Phương án | Ưu điểm | Giới hạn/rủi ro |
| --- | --- | --- |
| **CIDR allowlist qua ipBlock** | Đơn giản khi IP cố định và thuộc quyền quản trị | CDN/địa chỉ động, NAT và shared IP có thể làm sai phạm vi |
| **Egress proxy/gateway có authz** | Tập trung policy theo danh tính và hostname/HTTP khi hỗ trợ | Cần chặn direct egress, quản lý TLS, HA và log |
| **Cloud firewall/egress service** | Tích hợp VPC/VNet và telemetry của nhà cung cấp | Các feature match FQDN khác nhau theo sản phẩm |
| **CNI có FQDN policy extension** | Có thể gắn domain policy vào workload | Không thuộc API NetworkPolicy chuẩn; cần hiểu DNS cache, TTL và semantics |
| **Application authorization + network isolation** | Phân quyền nghiệp vụ ngay tại đích | Không thay thế toàn bộ giới hạn đường mạng |

**Không chọn chỉ dựa trên việc một sản phẩm có trường hostname.** Kiểm chứng cách giải quyết DNS answer thay đổi, IP CDN dùng chung, TLS inspection, QUIC, DoH/DoT, bypass qua direct IP, IPv6, cách ghi audit và xử lý outage.

### 12.2. Mẫu kiến trúc với egress gateway

~~~mermaid
flowchart LR
    W["Workload\nrestricted egress"] -->|"Chỉ cho phép tới gateway"| G["Egress proxy/gateway\nidentity + destination policy"]
    G -->|"Kiểm soát theo dịch vụ được phép"| E["External partner API"]
    W -. "Direct Internet egress bị chặn" .-> X["Internet khác"]
    G -. Audit .-> SOC["Telemetry / SIEM"]
    ID["Workload identity / IAM"] -. Xác minh principal .-> G
~~~

Ở kiến trúc này, NetworkPolicy/segmentation cho workload chỉ đến **gateway được kiểm soát**, còn gateway áp chính sách đích. Quan trọng nhất là **không có đường trực tiếp ra Internet bỏ qua gateway**, và gateway không dựa vào header identity có thể bị caller tự khai. Thiết kế phải xét khả năng gateway bị lỗi và xử lý fail-open/fail-closed theo mức rủi ro dịch vụ.

### 12.3. Ví dụ ipBlock chỉ nên dùng trong tình huống phù hợp

Trong một mạng thử nghiệm có đích IPv4 cố định và thuộc quyền tổ chức:

~~~yaml
# Ví dụ cấu trúc ipBlock, KHÔNG ghép trực tiếp vào policy lab
# nếu chưa được owner phê duyệt địa chỉ và routing.
egress:
  - to:
      - ipBlock:
          cidr: 198.51.100.10/32
    ports:
      - protocol: TCP
        port: 443
~~~

**198.51.100.0/24 là dải dành cho tài liệu**, không phải endpoint Internet để thử. Trong hạ tầng thật, cần xác minh IP thuộc chủ sở hữu, NAT, IPv6, cách CNI thực thi ipBlock với Service IP và các đường failover. Không dùng ipBlock để thay cho workload/pod selectors khi thực sự đang nói tới Pod endpoints.

## 13. Ánh xạ bài lab sang VM, firewall và cloud

Cùng một yêu cầu "chỉ workload A được liên hệ service B" có cách thực thi khác nhau:

| Nền tảng | Enforcement có thể dùng | Identity/đối tượng policy | Bằng chứng |
| --- | --- | --- | --- |
| Kubernetes | NetworkPolicy qua CNI | Namespace, Pod selector, protocol/port, CIDR | Policy + CNI flow logs + Pod test |
| VM trên VPC/VNet | Security group/NSG, subnet ACL, cloud firewall | NIC/instance/group, CIDR/port, tag tùy nền tảng | Cloud flow logs + rule evaluation |
| VM on-prem | Firewall giữa VLAN/VRF, host firewall | IP/subnet, host identity, zone | Session logs + host socket/network test |
| Service mesh | Workload identity, mTLS + auth policy | Service principal, request context tùy mesh | Proxy/mesh access logs + certificate identity |
| SaaS egress qua proxy | Egress gateway/proxy + network segmentation | Authenticated workload, destination, action | Gateway logs, identity, flow audit |

Trên firewall truyền thống, policy có thể áp theo **source zone, destination zone, address objects, NAT và rule order**. Trên cloud, security group thường có tính stateful, nhưng network ACL hoặc routing có thể có semantics khác. Đừng chuyển nguyên YAML giữa các nền tảng mà không xác định **policy evaluation, precedence, statefulness, response traffic và logging**.

## 14. Quan sát bằng chứng: chính sách đã thực thi thật chưa?

Kubernetes **kubectl describe networkpolicy** cho biết cấu hình đối tượng, không phải chứng cứ chắc chắn rằng CNI đã chặn từng packet. Khi đánh giá:

1. Ghi lại **policy manifest và resource version/UID** tại thời điểm thử.
2. Xác minh nhãn Pod nguồn, Pod đích và namespace.
3. Đối chiếu **Pod IP, Service IP, EndpointSlice, resolver** và đường NAT.
4. Dùng **flow logs hoặc policy verdicts của CNI** nếu nền tảng hỗ trợ, xác định chiều traffic và rule match.
5. Đọc application logs của approved-api và unapproved-api để biết request có tới listener không.
6. Ghi kết quả **negative test** cùng nguồn thử, không chỉ dựa vào timeout.
7. Kiểm tra có policy khác đang chọn Pod và mở rộng quyền ngoài ý định không.

### 14.1. Các lệnh read-only hữu ích

~~~bash
kubectl -n lab-egress get networkpolicies -o yaml
kubectl -n lab-egress get pod lab-client -o wide --show-labels
kubectl -n lab-services get pods -o wide --show-labels
kubectl -n lab-services get services,endpointslices

# Đọc log thử nghiệm ở dịch vụ đích nếu cần.
kubectl -n lab-services logs pod/approved-api
kubectl -n lab-services logs pod/unapproved-api
~~~

Nền tảng CNI có thể cung cấp CLI/flow telemetry riêng; chỉ dùng các công cụ đã được quản trị và quyền cho phép. **Không tự tắt IDS/IPS, proxy hoặc policy khác** để khiến bài test đạt kết quả mong muốn.

### 14.2. Quan sát nhiều lớp khi policy có proxy hoặc mesh

Một request có thể đi từ Pod tới sidecar, ra egress gateway rồi đến backend. Trong trường hợp này:

- Egress policy có thể quan sát **kết nối từ Pod tới gateway**, không thấy final destination ở cùng 5-tuple.
- Gateway có thể tạo TCP/TLS connection mới; flow log ở phía gateway thuộc principal khác.
- Access log và trace ID giúp nối request logic; firewall log giải thích quyết định L3/L4.
- Muốn phân tích nghi exfiltration, số byte trong flow không tự chứng minh loại dữ liệu đã rời hệ thống.

## 15. Debug khi kết quả khác kỳ vọng

| Triệu chứng | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| Sau default deny vẫn tới được unapproved-api | CNI không thực thi policy, có allow policy khác, source label sai | Xem CNI, tất cả policy, Pod labels, flow verdicts |
| Sau allow policy approved-api vẫn lỗi DNS | Selector DNS sai, NodeLocal DNS, DNAT/Service IP khác | /etc/resolv.conf, CoreDNS labels, CNI/service routing |
| DNS thành công nhưng HTTP tới approved-api lỗi | Destination selector sai, ingress policy ở đích, listener lỗi | Pod/service labels, EndpointSlice, logs, ingress policies |
| HTTP tới unapproved-api thất bại cả trước policy | Server/lab nền lỗi | Sửa baseline, không ghi nhận policy PASS |
| Kết nối qua Service khác kết nối Pod IP | CNI/NAT/load-balancer path hoặc EndpointSlice | So Pod IP, Service VIP và policy verdict |
| Policy trỏ nhầm mọi Pod trong namespace | namespaceSelector và podSelector là hai mục **to** riêng | Sửa selector về một mục AND và review diff |
| Quy tắc allow chưa đủ cho response | Có chính sách khác ở destination/source hoặc thiết bị trung gian | Kiểm tra ingress/egress, CNI và forwarding state |
| Chính sách hoạt động ở IPv4 nhưng IPv6 có đường khác | Address family coverage thiếu | Xem cluster dual-stack và policy semantics |
| Pod đổi IP sau restart, traffic bất thường | Rule dựa vào IP tĩnh, label/identity không nhất quán | Kiểm tra selector và lịch sử Pod/namespace |
| Log không thấy deny | CNI không xuất verdict, log collector thiếu hoặc sai interface | Kiểm tra capability/coverage, không suy “không deny” |

### 15.1. Trình tự debug ít gây nhiễu

1. **DNS trước:** có phân giải đúng endpoint không?
2. **Dịch vụ:** Pod đích Ready, listener đúng cổng, Service trỏ đúng Pod?
3. **Selector:** label nguồn/đích và namespace có khớp không?
4. **Policy union:** có NetworkPolicy khác cho phép ngoài ý định?
5. **Ingress ở đích:** có deny do đích đang được cô lập?
6. **CNI/route/NAT:** flow đi qua dataplane nào, verdict có sẵn không?
7. **Ứng dụng:** nếu TCP kết nối được mà HTTP lỗi, xác định auth, TLS, backend và timeout.

Đừng sửa bằng cách cho phép toàn bộ egress để thử nhanh nếu điều này phá nguyên tắc bài lab. Tại production, mọi thay đổi tạm phải được owner phê duyệt, ghi thời hạn và có rollback.

## 16. Thiết kế policy production an toàn hơn

Mục tiêu của lab là một Pod minh họa. Đối với production, nên xây **dependency inventory**:

| Nhóm phụ thuộc | Câu hỏi và ràng buộc |
| --- | --- |
| DNS | Resolver nào, UDP/TCP 53, NodeLocal hay DoH/DoT? |
| Service nội bộ | Danh tính workload, namespace, port, authorization? |
| External APIs | DNS/CDN/IP động, egress gateway, proxy và vendor change? |
| Identity/PKI | IdP, token issuer, certificate renewal, KMS/secret access? |
| Telemetry | Logs, traces, metrics exporters, SIEM/collector? |
| Time sync | Có dependency NTP trực tiếp từ Pod hay chỉ node? |
| Cloud metadata | Workload có cần metadata API không, token scope ra sao? |
| Data storage/queue | DB, cache, broker, backup và replication flow? |
| Management/recovery | Có đường break-glass và rollback nếu policy chặn chính CD system? |

Không phải tất cả dependency đều cần mở từ tất cả workload. Ví dụ một Pod không nhất thiết cần gọi NTP trực tiếp nếu node đã đồng bộ giờ; đừng đưa một rule UDP/123 chung vào policy chỉ vì NTP là giao thức mạng cơ bản.

### 16.1. Triển khai theo giai đoạn

1. **Discover:** lấy flow telemetry lịch sử trong cửa sổ đủ đại diện và xác minh owner của từng đích.
2. **Specify:** lập ma trận allow/deny theo service identity, giao thức, port, thời điểm và mức nhạy cảm.
3. **Validate:** chạy schema, selector review, policy unit tests và lab traffic checks.
4. **Canary:** chọn một workload không trọng yếu hoặc replica có kiểm soát, áp policy trong maintenance window.
5. **Observe:** so error rate, latency, DNS failures, CNI denies, business transactions.
6. **Expand:** mở rộng từng nhóm nhỏ khi test đạt, có stop conditions và người trực.
7. **Maintain:** cập nhật khi API/service dependencies thay đổi, theo dõi drift và exception expiry.

**Không triển khai default deny hàng loạt rồi mở dần khi người dùng báo lỗi**. Cách đó biến production thành môi trường thử nghiệm và có thể cắt khả năng quan sát hoặc khôi phục.

### 16.2. Fail mode, availability và monitoring

Chặn đúng traffic trái phép nhưng đồng thời chặn API cập nhật chứng chỉ hoặc dịch vụ định danh có thể làm hệ thống dừng sau một thời gian. Kiểm tra **long-running operations, certificate rotation, restart, failover, autoscaling và deploy mới**, không chỉ một request ở thời điểm đang khỏe.

Theo dõi những chỉ số như request failure, DNS timeout, policy verdicts, CNI health, traffic đến đích chưa được phê duyệt và độ trễ cập nhật rule. Tăng log đầy đủ có thể phát sinh chi phí, thông tin nhạy cảm và cardinality cao; quản trị retention và quyền truy cập.

## 17. Quản lý bằng Git và kiểm soát thay đổi

Đưa YAML policy đã duyệt vào **version control**, gắn owner, mục tiêu, môi trường và test case. Cần có:

- **Pull request review** cho NetworkPolicy, nhãn namespace, RBAC và thay đổi CNI có ảnh hưởng.
- **CI validation:** YAML/schema, các selector phải có Pod đích, không có broad allow vô ý, kiểm tra policy union khi có thể.
- **Security check:** không có credential hoặc token trong YAML; image và runner CI đáng tin.
- **Deployment gate:** chỉ áp vào cluster/namespace đã duyệt, có backup của policy hiệu lực và plan rollback.
- **Post-deploy readback:** so manifest Git với trạng thái Kubernetes API và telemetry thực tế.
- **Exception có thời hạn:** owner, lý do, expiry và negative test sau khi đóng exception.

Một policy rất chặt trên Git **không bảo đảm production đang chạy đúng policy** nếu GitOps controller lỗi hoặc có người thay đổi trực tiếp. Drift detection và bằng chứng kiểm thử traffic là cần thiết.

### 17.1. Quy trình rollback trong lab

Nếu policy mới vô tình làm hỏng luồng hợp lệ, với môi trường thử nghiệm do mình quản lý:

1. Lưu YAML và logs trước khi sửa.
2. Xác định policy gây thay đổi theo namespace, Pod labels và mốc UTC.
3. Chỉ gỡ **policy allow hoặc deny liên quan**, không xóa toàn bộ policy trong cluster.
4. Kiểm tra các luồng positive và negative sau rollback.
5. Ghi phiên bản sửa và cập nhật test matrix trước khi thử triển khai lại.

Trong production, rollback phải đi theo change/incident procedure vì việc gỡ default deny có thể mở quyền quá rộng. Nếu cần duy trì an toàn, có thể sửa rule hẹp sau khi xác minh thay vì xóa toàn bộ lớp bảo vệ.

## 18. Cleanup lab có kiểm soát

**Chỉ chạy trên cluster và namespace lab do bạn tạo**, sau khi đã kiểm chứng không có tài nguyên của người khác:

~~~bash
# Xóa chính sách allow và default deny do bài lab tạo.
kubectl delete -f egress-allow.yaml
kubectl delete -f egress-default-deny.yaml

# Xóa Pod, Service và namespace lab đã tạo từ manifest.
# Chỉ thực hiện khi hai namespace thực sự thuộc lab riêng này.
kubectl delete -f lab-resources.yaml

# Xác minh sau cleanup.
kubectl get namespace lab-egress
kubectl get namespace lab-services
~~~

Việc xóa namespace có thể xóa **mọi tài nguyên bên trong**. Vì vậy phải thực sự xác nhận chúng được dành riêng cho lab. Nếu dùng namespace chung theo chỉ đạo của tổ chức, **không dùng xóa namespace hàng loạt**; chỉ xóa những resource đã tạo có owner rõ.

Không xóa CNI components, cluster DNS hoặc network policies toàn cluster. Các tài nguyên đó không thuộc quyền sở hữu bài lab.

## 19. Tình huống mở rộng: workload có dấu hiệu kết nối đích lạ

Một hệ thống NDR phát hiện Pod order-worker tạo kết nối định kỳ tới địa chỉ ngoài danh mục sau deployment. Không nên coi đó là exfiltration đã xác nhận. Nhóm điều tra đặt những câu hỏi:

1. Pod UID, namespace và service account nào đã tạo flow trong đúng thời gian?
2. Flow đi qua gateway/proxy hay kết nối trực tiếp? Có NAT, IPv6 hoặc đường service mesh khác không?
3. DNS log xác định hostname nào, IP answer tại thời điểm đó là gì?
4. Workload có dependency được phê duyệt để truy cập dịch vụ đó không?
5. Egress policy nào có hiệu lực tại thời điểm sự kiện, có rule broad allow khác không?
6. EDR/container audit, deployment diff và application logs có giải thích việc mở kết nối không?
7. Có dữ liệu thực sự được tải đi không, hay chỉ là TCP/TLS connection bị từ chối hoặc retry?

### 19.1. Hành động theo phân loại

| Kết quả điều tra | Bước phù hợp |
| --- | --- |
| Đích thuộc dependency hợp lệ nhưng thiếu inventory | Cập nhật owner, risk review và policy có kiểm soát |
| Đích không được cấp quyền và bị chặn | Giữ log, phân tích tiến trình và xác định có cần incident response không |
| Đích không được cấp quyền nhưng kết nối thành công | Kiểm tra CNI, policy union, đường bypass và phạm vi ảnh hưởng |
| Telemetry chưa đủ để kết luận | Giữ trạng thái unknown, thu thêm log có quyền từ nguồn độc lập |
| Có dấu hiệu xâm nhập khác cùng hỗ trợ | Kích hoạt quy trình incident response và containment có phê duyệt |

Mục tiêu của egress policy không phải biến mọi kết nối lạ thành bằng chứng mã độc, mà là **giảm quyền kết nối không cần thiết và tạo điểm kiểm soát rõ ràng** cho phòng thủ và điều tra số.

## 20. Bảng tiêu chí nghiệm thu bài thực hành

| Tiêu chí | Đạt khi | Chưa đạt khi |
| --- | --- | --- |
| Phạm vi lab | Đúng cluster, namespace và Pod đã được cấp quyền | Triển khai nhầm production hoặc namespace chung |
| Baseline | DNS và hai API test hoạt động trước policy | Test nền đã lỗi nhưng vẫn kết luận |
| Default deny | lab-client không còn truy cập được luồng chưa cấp | CNI không chặn hoặc có allow policy rộng |
| DNS allow | Resolver được chọn đúng, DNS query hoạt động | Mở rộng quá mức hoặc DNS vẫn hỏng |
| API allow | approved-api:8080 truy cập được | Endpoint/selector/ingress khiến request lỗi |
| API deny | unapproved-api:8080 không được phép dù baseline từng thành công | Request tới unapproved-api vẫn thành công |
| Least privilege | Selector ghép đúng namespace và Pod, đúng TCP port | Allow cả namespace hoặc mọi destination |
| Evidence | Có YAML, resource IDs, log và UTC timestamp | Chỉ có một ảnh chụp màn hình chung |
| Rollback/cleanup | Chỉ gỡ tài nguyên lab do mình tạo | Xóa tài nguyên ngoài phạm vi |
| Phân tích giới hạn | Nêu DNS, CNI, service NAT, identity và L7 authz | Kết luận policy bảo vệ mọi giao thức và dữ liệu |

**Mẫu kết luận nghiệm thu phù hợp:** “Trong cluster lab có CNI thực thi NetworkPolicy, sau khi default deny và allow rule được áp dụng, lab-client phân giải được DNS và truy cập được approved-api:8080, trong khi không truy cập được unapproved-api:8080; kết quả được đối chiếu với baseline, nhãn selector và dữ liệu quan sát tại thời điểm kiểm tra. Kết luận giới hạn ở các Pod, cổng, giao thức và đường đi đã thử.”

## 21. Checklist trước khi đưa chính sách egress vào vận hành thật

- [ ] Đã được chủ sở hữu cluster và service phê duyệt phạm vi và thời gian áp dụng.
- [ ] Đã phân loại workload, dữ liệu nhạy cảm, nguồn/đích, namespace, identity và trust boundaries.
- [ ] Đã kiểm kê chính xác DNS, API, database, identity, telemetry, certificate, secret và backup dependencies.
- [ ] Đã xác nhận CNI thực sự thực thi NetworkPolicy, bao gồm các trường và protocol đang dùng.
- [ ] Đã xem tất cả NetworkPolicy cùng chọn Pod và hiểu tính cộng dồn của allow rules.
- [ ] Đã kiểm tra namespaceSelector và podSelector kết hợp đúng; không dùng allow rộng ngoài ý định.
- [ ] Đã xác minh DNS resolver path, labels, NodeLocal DNS/Service NAT và UDP/TCP 53.
- [ ] Đã xử lý các đích FQDN/CDN bằng kiến trúc có kiểm soát, không coi DNS allow là đủ giới hạn Internet.
- [ ] Đã xem IPv4/IPv6, UDP/QUIC, direct-to-origin, hostNetwork và các đường bypass có liên quan.
- [ ] Đã tách network reachability khỏi workload identity, mTLS và application authorization.
- [ ] Có positive và negative tests từ đúng Pod/source, cùng baseline trước thay đổi.
- [ ] Có CNI/flow/app logs, UTC timestamp, policy version và owner để truy vết.
- [ ] Có canary, health metrics, stop conditions, kế hoạch rollback và recovery access.
- [ ] Policy được review trong Git/CI, có kiểm tra secret, broad allow, drift và exception expiry.
- [ ] Đã kiểm tra trạng thái sau restart, autoscaling, DNS failover và certificate rotation.
- [ ] Đã xác nhận tác động vận hành và duy trì quy trình cập nhật policy theo thay đổi ứng dụng.

**Kết luận:** một egress policy hiệu quả không chỉ là tệp YAML chứa **default deny**. Nó bắt đầu từ việc hiểu **workload cần giao tiếp với ai và vì sao**, giới hạn đường đi bằng cơ chế được CNI thực thi, mở các phụ thuộc tối thiểu như DNS, xác minh cả **luồng được phép lẫn luồng phải chặn**, và duy trì telemetry cùng phương án phục hồi. Khi triển khai đúng, egress segmentation trở thành một lớp giảm thiểu rủi ro và hỗ trợ điều tra an ninh mạng, thay vì một tập luật chặn kết nối khó giải thích.
