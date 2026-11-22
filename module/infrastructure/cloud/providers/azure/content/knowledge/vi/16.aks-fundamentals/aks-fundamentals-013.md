# Network policy và kiểm soát giao tiếp giữa pod

Một ứng dụng thương mại điện tử chạy trên Azure Kubernetes Service (AKS) thường có nhiều thành phần: frontend nhận yêu cầu từ người dùng, API xử lý đơn hàng, database lưu dữ liệu và worker chạy công việc nền. Dù các pod nằm ở những namespace khác nhau, **việc tách namespace không tự động chặn mạng giữa chúng**. Nếu cluster chưa áp chính sách mạng và không có lớp kiểm soát tương ứng, một pod bị xâm nhập có thể thử kết nối tới nhiều dịch vụ mà nó không cần dùng.

**Kubernetes NetworkPolicy** cho phép khai báo những kết nối mạng **Layer 3/Layer 4** được phép tới hoặc đi từ các pod theo nhãn, namespace, dải IP và cổng/giao thức. Trên AKS, chính sách phải được một **network policy engine/dataplane được hỗ trợ** thực thi. Việc tạo tài nguyên YAML thành công chưa đủ để kết luận lưu lượng đã bị chặn.

Bài học thuộc chương **Nền tảng Azure Kubernetes Service** trong lộ trình Microsoft Azure: từ subscription, resource group, Microsoft Entra ID, mạng ảo tới dịch vụ tính toán, lưu trữ và dữ liệu; sau đó triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Trọng tâm là biến nguyên tắc **least privilege trong mạng pod-to-pod** thành quy tắc kiểm tra được.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao namespace, Service và Azure NSG không tự thay thế Kubernetes NetworkPolicy.
2. Hiểu mô hình **default allow**, **default deny**, danh sách cho phép theo **Ingress/Egress** và cách nhiều policy kết hợp.
3. Sử dụng **podSelector**, **namespaceSelector**, **ipBlock**, **ports** và **policyTypes** đúng ngữ nghĩa.
4. Thiết kế luồng ba tầng: frontend → API → database, chặn những kết nối không cần thiết.
5. Mở egress DNS và các kết nối hạ tầng cần thiết có kiểm soát.
6. Nhận diện sự khác nhau giữa Azure CNI, dataplane Cilium và network policy engine ở AKS.
7. Áp policy trong môi trường thử nghiệm và kiểm chứng cả trường hợp được phép lẫn bị từ chối.
8. Chẩn đoán lỗi sau khi bật policy, tránh làm mất kết nối DNS, telemetry hoặc ingress.

## 1. Vì sao cần bảo vệ giao tiếp giữa các pod?

Trong Kubernetes, ứng dụng có thể triển khai nhiều namespace để phân chia nhóm, quyền và vòng đời:

~~~text
AKS cluster
  |
  +-- Namespace: shop-web
  |     +-- frontend pods
  |
  +-- Namespace: shop-api
  |     +-- orders-api pods
  |
  +-- Namespace: shop-data
        +-- database pods
~~~

Một frontend hợp lệ cần gọi API trên cổng 8080 nhưng **không cần truy cập trực tiếp database** trên cổng 5432. API cần database nhưng một pod công cụ bất kỳ trong namespace khác không nên có cùng quyền truy cập. Nếu tất cả các luồng đều được phép, khi frontend bị khai thác, kẻ tấn công có thể thử truy cập database theo đường mạng nội bộ.

**NetworkPolicy giảm phạm vi kết nối**, giúp hạn chế di chuyển ngang (*lateral movement*) trong cluster. Nó không phải tường lửa ứng dụng hoàn chỉnh và không thay thế xác thực, phân quyền, TLS, quản lý bí mật hay biện pháp bảo vệ dữ liệu.

### Ba câu hỏi khi thiết kế

1. **Ai được gọi?** Pod/namespace nguồn nào có thể mở kết nối?
2. **Được gọi tới đâu?** Pod/namespace đích nào cần nhận?
3. **Theo giao thức và cổng nào?** TCP 8080, TCP 5432, UDP/TCP 53 hay một cổng khác?

Với quy tắc tốt, chỉ các luồng cần thiết mới được cho phép. Việc ứng dụng cùng nằm trên một VNet hoặc cùng được truy cập qua ClusterIP Service không tự tạo ra ranh giới bảo mật.

## 2. NetworkPolicy thực thi ở đâu trong AKS?

Kubernetes định nghĩa API **networking.k8s.io/v1**, kind **NetworkPolicy**. API này mô tả ý định nhưng việc cho phép/chặn gói tin do **network plugin/dataplane hoặc policy engine tương thích** thực hiện.

AKS có nhiều mô hình mạng và thành phần theo phiên bản/khu vực/cấu hình cluster. Những tên quan trọng có thể gặp:

- **Azure CNI** và các chế độ kết nối pod với mạng Azure, ví dụ Azure CNI Overlay trong cấu hình được hỗ trợ.
- **Azure CNI Powered by Cilium**: dataplane dựa trên Cilium, có khả năng thực thi Kubernetes NetworkPolicy chuẩn trong những mô hình hỗ trợ.
- Các giải pháp **network policy engine** như Azure Network Policy Manager hoặc Calico ở những môi trường/cấu hình được AKS hỗ trợ.

**Không đồng nhất Azure CNI với Azure Network Policy Manager**, và cũng không coi “có Azure CNI” đồng nghĩa “có Cilium”. Network plugin, kiểu cấp IP cho pod, dataplane và thành phần thực thi policy là các khái niệm có liên quan nhưng không thay thế nhau.

### Những điều cần xác nhận trước khi áp policy

| Điều cần biết | Vì sao quan trọng |
|---|---|
| Phiên bản Kubernetes/AKS | Ảnh hưởng hỗ trợ tính năng và nâng cấp |
| Network plugin và plugin mode | Quyết định mô hình IP và routing của pod |
| Network dataplane/policy engine | Xác nhận Kubernetes NetworkPolicy có được thực thi không |
| Linux/Windows node pools | Mức hỗ trợ policy và tính năng có thể khác nhau |
| CNI/Overlay/Pod CIDR/VNet CIDR | Giúp phân biệt đường đi gói tin và routing |
| Ingress controller và service mesh | Có thể có luồng đặc biệt phải kiểm tra |
| DNS/observability agents | Các kết nối hạ tầng cần tiếp tục hoạt động |
| Quyền quản trị cluster | Bảo vệ thay đổi policy và quy trình rollback |

Nếu một cluster **không có engine thực thi NetworkPolicy được hỗ trợ**, bạn có thể tạo policy nhưng không quan sát thấy hành vi chặn như mong đợi. Khi bổ sung hoặc đổi networking cho cluster, hãy kiểm tra tài liệu AKS về khả năng chuyển đổi; không giả định có thể bật mọi tùy chọn trên cluster đang vận hành mà không gây gián đoạn.

## 3. NetworkPolicy là mô hình allow-list

Trong Kubernetes NetworkPolicy chuẩn, mặc định một pod **không bị cô lập bởi NetworkPolicy**: nếu không có policy liên quan, NetworkPolicy không giới hạn ingress/egress của pod đó.

Khi có một policy chọn pod theo một hướng:

- **Ingress isolation:** những kết nối đi **vào** pod chỉ được phép nếu khớp ít nhất một ingress rule của các policy áp dụng.
- **Egress isolation:** những kết nối đi **ra** từ pod chỉ được phép nếu khớp ít nhất một egress rule của các policy áp dụng.

Kubernetes NetworkPolicy chuẩn có các **quy tắc cho phép**, không có danh sách deny rule và không đặt priority để policy sau ghi đè policy trước.

### Hai chiều phải phù hợp

Muốn pod frontend mở kết nối tới pod API, khi cả hai được cô lập:

1. **Egress của frontend** phải cho phép đi tới API.
2. **Ingress của API** phải cho phép nhận từ frontend.

Nếu thiếu một trong hai, kết nối sẽ không thành công theo các điều kiện thực thi của dataplane.

~~~text
frontend pod                  api pod
shop-web                      shop-api
    |                            ^
    |  Egress frontend: allow    |
    +------ TCP/8080 ------------+
           Ingress API: allow

Thiếu một phía -> không có kết nối như mong đợi
~~~

### Policy kết hợp theo phép hợp

Nếu hai policy cùng chọn pod API và một policy cho phép frontend, policy kia cho phép monitoring, thì **cả hai nguồn** được phép. Một policy default-deny không thể “phủ quyết” một allow rule từ policy khác.

Vì vậy:

- Không dựa vào **thứ tự áp dụng YAML** để giải quyết xung đột.
- Không dùng suy luận “policy mới chặt hơn sẽ tự chặn policy cũ”.
- Khi xuất hiện luồng không mong muốn, hãy kiểm tra **tất cả policy chọn pod**, đặc biệt những rule rộng dùng selector rỗng.

## 4. Cấu trúc của một NetworkPolicy

Ví dụ đơn giản:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-from-web
  namespace: shop-api
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              security-zone: web
          podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
~~~

Ý nghĩa:

| Field | Vai trò |
|---|---|
| **metadata.namespace** | Namespace chứa policy; policy chọn pod đích ở chính namespace này |
| **spec.podSelector** | Chọn pod được policy áp dụng |
| **policyTypes** | Những hướng Ingress/Egress mà policy cô lập pod |
| **ingress.from** | Nguồn được phép gọi tới pod được chọn |
| **egress.to** | Đích được phép nhận kết nối từ pod được chọn |
| **ports** | Cổng/giao thức được cho phép theo hướng rule |
| **namespaceSelector** | Chọn namespace theo nhãn |
| **ipBlock** | Chọn CIDR và ngoại lệ theo khả năng/ý nghĩa của Kubernetes NetworkPolicy |

Policy ở **shop-api** không thể trực tiếp chọn một pod thuộc namespace **shop-web** làm đối tượng áp dụng qua spec.podSelector. Nếu muốn hạn chế egress của frontend, hãy tạo policy trong **shop-web**.

### Tầm quan trọng của labels

Policy dựa vào label, không dựa vào việc tên pod ngẫu nhiên là **api-6f7b...**. Một Deployment có thể tạo lại pod với tên mới nhưng vẫn giữ label **app: api**, nên policy tiếp tục phù hợp.

Ngược lại, nếu ứng dụng được triển khai với nhãn khác, ví dụ **app.kubernetes.io/name: orders-api** nhưng policy chọn **app: api**, rule có thể không chọn pod cần bảo vệ. Trước khi áp dụng, luôn đối chiếu labels thực tế.

## 5. Mặc định từ chối mọi ingress

Một NetworkPolicy tạo cách ly ingress cho mọi pod trong namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: shop-api
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

**podSelector: {}** chọn tất cả pod trong namespace của policy. Vì **policyTypes** có Ingress nhưng không có ingress rules, không có luồng ingress nào được chính policy này cho phép.

**Điểm quan trọng:** nếu có policy khác cùng chọn những pod đó và cho phép một nguồn, nguồn ấy vẫn được phép theo cơ chế cộng gộp. Tên policy là “default-deny” không có quyền ưu tiên đặc biệt.

### Default-deny toàn bộ egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: shop-api
spec:
  podSelector: {}
  policyTypes:
    - Egress
~~~

Sau khi áp, pod trong namespace **shop-api** không được gửi kết nối tới nơi khác **theo những quy tắc NetworkPolicy chuẩn**, trừ khi một egress policy bổ sung cho phép. DNS, database, telemetry, Key Vault hoặc endpoint identity có thể ngừng truy cập nếu chưa được mở đúng phạm vi.

### Default-deny cả hai hướng

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: shop-data
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Đây là cách thường dùng để xây dựng **least privilege từ nền tảng**. Tuy nhiên, nếu đưa default-deny ingress+egress lên namespace có ứng dụng đang hoạt động mà chưa biết các dependency, có thể gây gián đoạn nghiêm trọng.

## 6. Selector: phân biệt AND và OR

Kubernetes NetworkPolicy có một chi tiết cú pháp rất dễ gây sai lệch quyền.

### namespaceSelector và podSelector cùng một phần tử

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        security-zone: web
    podSelector:
      matchLabels:
        app: frontend
~~~

Ý nghĩa là **AND**: chỉ các pod có label **app=frontend** nằm **trong những namespace** mang label **security-zone=web**.

### Hai phần tử khác nhau trong danh sách

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        security-zone: web
  - podSelector:
      matchLabels:
        app: frontend
~~~

Ý nghĩa là **OR**: cho phép **tất cả pod trong namespace có security-zone=web**, **hoặc** cho phép các pod **app=frontend trong namespace của policy**. Đây là quyền rộng hơn rất nhiều so với ý định “frontend thuộc web namespace”.

**Đặt đúng độ thụt YAML là vấn đề bảo mật, không chỉ vấn đề định dạng.**

### Selector rỗng

- **podSelector: {}** tại spec chọn tất cả pod trong namespace hiện tại.
- Một peer chỉ chứa **podSelector: {}** chọn các pod trong namespace của NetworkPolicy.
- Một peer với **namespaceSelector: {}** có thể chọn pod thuộc tất cả namespace.
- Một rule có **from/to không chỉ rõ** có thể cho phép rộng hơn dự định đối với hướng được xét.

Đừng dùng selector rỗng như một cách “test cho nhanh” trong production; chỉ thêm rule cụ thể và có kiểm chứng.

### namespace labels có thể thay đổi

Nếu quyền truy cập phụ thuộc nhãn namespace, người có quyền chỉnh nhãn namespace có thể làm một nhóm pod phù hợp với selector vốn chỉ dành cho nhóm khác. Vì vậy, **quyền sửa namespace labels** là một phần của mô hình bảo mật, không chỉ là tiện ích tổ chức.

## 7. Ingress và egress qua Service

Một ứng dụng thường không gọi pod IP trực tiếp mà dùng **ClusterIP Service**, ví dụ:

~~~text
api.shop-api.svc.cluster.local:8080
db.shop-data.svc.cluster.local:5432
~~~

NetworkPolicy chuẩn lựa chọn **pod**, namespace, dải IP và cổng, không cho phép theo tên Kubernetes Service. Khi request đi qua Service, dataplane phân phối tới backend pod; chính sách cần chọn đúng **nguồn, đích và cổng mà dataplane thực thi**.

Ví dụ:

- Frontend gọi Service **api** ở cổng 8080.
- Service chọn backend pods có **app=api**.
- Ingress policy của các pod API cho phép nguồn frontend trên cổng backend tương ứng.

Nếu Service **port=80** nhưng **targetPort=8080**, cần phân biệt cổng mà policy áp vào kết nối tới pod backend. Không giả định mọi triển khai DNAT/NAT giữ nguyên địa chỉ/cổng ở tất cả các điểm xử lý; hãy kiểm thử trên dataplane AKS thực tế.

### Named ports

NetworkPolicy có thể chỉ định tên cổng (ví dụ **http-api**) khi pod đích khai báo containerPort name phù hợp. Cách này giúp tránh phụ thuộc số cổng trong YAML policy, nhưng vẫn yêu cầu nhất quán giữa Deployment, Service và policy.

### Headless Service và truy cập trực tiếp

Policy vẫn cần bảo vệ pod ngay cả khi ứng dụng truy cập **headless Service** hoặc pod IP trực tiếp. Không nên cho rằng chỉ vì không có Service public thì pod đã không thể bị các workload nội bộ tiếp cận.

## 8. Mô hình ba tầng web → API → database

Thiết kế một ứng dụng mẫu:

| Namespace | Nhãn namespace | Pod | Cổng |
|---|---|---|---|
| **shop-web** | security-zone=web | frontend | TCP 8080 khi cần nhận ingress |
| **shop-api** | security-zone=api | api | TCP 8080 |
| **shop-data** | security-zone=data | db | TCP 5432 |
| **kube-system** | Nhãn hệ thống của Kubernetes | CoreDNS | UDP/TCP 53 |

Mục tiêu kết nối:

~~~text
Ingress controller
       |
       | (nếu được cho phép)
       v
frontend (shop-web)
       |
       | TCP/8080
       v
api (shop-api)
       |
       | TCP/5432
       v
db (shop-data)

Không cho phép:
  frontend ----X----> db:5432
  pod không liên quan ----X----> api:8080
  api ----X----> Internet tùy ý
~~~

Đây là **mô hình logic**, không phải chứng minh mọi luồng hệ thống (DNS, telemetry, identity, private endpoints...) đã được mở. Mỗi dependency phải được đưa vào bảng kết nối trước khi triển khai production.

## 9. Lab có kiểm soát: chuẩn bị namespaces và labels

Các manifest dưới đây dành cho **cluster thử nghiệm có network policy engine đang hoạt động**. Việc tạo namespace/pod và áp NetworkPolicy là thao tác thay đổi cluster thật. Không áp lên production hoặc namespace hệ thống nếu chưa có phê duyệt, kế hoạch rollback và danh sách dependency.

Tạo file **namespaces.yaml**:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: shop-web
  labels:
    security-zone: web
---
apiVersion: v1
kind: Namespace
metadata:
  name: shop-api
  labels:
    security-zone: api
---
apiVersion: v1
kind: Namespace
metadata:
  name: shop-data
  labels:
    security-zone: data
~~~

Áp trên cluster lab:

~~~bash
kubectl apply -f namespaces.yaml
kubectl get namespaces --show-labels
~~~

Trong production, namespace labels nên được quản lý bằng GitOps/IaC, Azure RBAC/Kubernetes RBAC và policy phê duyệt. Không cấp cho mọi developer quyền sửa nhãn phân quyền mạng của namespace khác.

## 10. Lab: tạo workload mô phỏng để kiểm thử

Không cần triển khai PostgreSQL thật chỉ để kiểm tra NetworkPolicy. Ta dùng một HTTP server giả lập ở **cổng 5432** của db pod để chứng minh đường TCP qua chính sách. **Cổng mô phỏng không biến HTTP server thành PostgreSQL.**

File **workloads.yaml**:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: frontend
  namespace: shop-web
  labels:
    app: frontend
spec:
  containers:
    - name: client
      image: busybox:1.36
      command: ["/bin/sh", "-c", "sleep 360000"]
---
apiVersion: v1
kind: Pod
metadata:
  name: api
  namespace: shop-api
  labels:
    app: api
spec:
  containers:
    - name: server
      image: python:3.12-alpine
      command: ["python", "-m", "http.server", "8080", "--bind", "0.0.0.0"]
      ports:
        - containerPort: 8080
---
apiVersion: v1
kind: Pod
metadata:
  name: db
  namespace: shop-data
  labels:
    app: db
spec:
  containers:
    - name: simulator
      image: python:3.12-alpine
      command: ["python", "-m", "http.server", "5432", "--bind", "0.0.0.0"]
      ports:
        - containerPort: 5432
---
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: shop-api
spec:
  selector:
    app: api
  ports:
    - name: http-api
      port: 8080
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: db
  namespace: shop-data
spec:
  selector:
    app: db
  ports:
    - name: tcp-demo-db
      port: 5432
      targetPort: 5432
~~~

Áp và kiểm tra:

~~~bash
kubectl apply -f workloads.yaml
kubectl get pods -A -o wide
kubectl get services -n shop-api
kubectl get services -n shop-data
~~~

Chờ pod chạy và image được pull từ registry mà môi trường cho phép. Hai image công cộng chỉ mang tính minh họa; production phải dùng image có quản lý phiên bản/nguồn, quét lỗ hổng và chính sách image pull phù hợp.

### Đường đi trước khi áp NetworkPolicy

Ở một cluster có NetworkPolicy hỗ trợ và chưa có quy tắc cách ly trong các namespace lab, truy cập thông thường tới các pod có thể được phép:

~~~bash
kubectl exec -n shop-web frontend -- \
  wget -T 3 -O - http://api.shop-api.svc.cluster.local:8080/

kubectl exec -n shop-web frontend -- \
  wget -T 3 -O - http://db.shop-data.svc.cluster.local:5432/
~~~

Trong môi trường này, yêu cầu đầu nên đi tới API; yêu cầu thứ hai **được thực hiện chỉ để làm baseline** và chứng minh nguy cơ frontend có thể kết nối database nếu không có policy. Có thể có các kiểm soát khác đã tồn tại nên kết quả thực tế cần được ghi lại chứ không mặc định đều thành công.

## 11. Lab: áp mặc định từ chối ingress và egress

Tạo file **default-deny.yaml**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: shop-web
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: shop-api
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: shop-data
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
~~~

Áp trên cluster **thử nghiệm**:

~~~bash
kubectl apply -f default-deny.yaml
kubectl get networkpolicy -A
~~~

Sau đó frontend có thể không phân giải được tên Service vì egress DNS cũng bị cô lập. **Không kết luận ngay rằng API policy chặn đúng** nếu phép thử lỗi chỉ vì DNS. Bước tiếp theo phải mở DNS có kiểm soát.

## 12. Lab: mở egress DNS

Pod cần truy vấn DNS để phân giải tên Service. Trên nhiều cluster AKS dùng CoreDNS, các pod DNS thuộc **kube-system** và thường có label như **k8s-app=kube-dns**. **Hãy kiểm tra labels thực tế** trước khi dùng ví dụ:

~~~bash
kubectl get pods -n kube-system --show-labels
kubectl get namespaces --show-labels
kubectl get services -n kube-system
~~~

Nếu DNS đang dùng NodeLocal DNSCache, custom DNS resolver hoặc dataplane có đường đi đặc biệt, rule chọn CoreDNS pod có thể chưa đủ. Cần kiểm tra địa chỉ đích và hướng dẫn của AKS/CNI đang sử dụng.

Ví dụ **allow-dns.yaml** mở UDP/TCP 53 cho web và API tới pod CoreDNS:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: shop-web
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
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
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: shop-api
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
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
~~~

Tại sao cần cả UDP/TCP 53? Truy vấn DNS thường sử dụng UDP nhưng có các trường hợp cần TCP. Luồng DNS phải được điều chỉnh theo triển khai thực tế, không mở **to: [{}]** cho toàn Internet chỉ vì không tìm thấy CoreDNS pod labels.

## 13. Lab: chỉ cho frontend gọi API

### Egress từ frontend tới API

File **allow-web-to-api.yaml**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-web-egress-api
  namespace: shop-web
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              security-zone: api
          podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 8080
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-ingress-web
  namespace: shop-api
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              security-zone: web
          podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
~~~

Hai policy này bổ sung nhau: phía frontend cho phép **egress** và phía API cho phép **ingress**. Policy default-deny đã áp dụng trước đó vẫn có hiệu lực, nhưng các rule mới bổ sung những luồng hợp lệ.

### Xác minh

~~~bash
kubectl apply -f allow-dns.yaml
kubectl apply -f allow-web-to-api.yaml

kubectl exec -n shop-web frontend -- \
  wget -T 3 -O - http://api.shop-api.svc.cluster.local:8080/
~~~

Nếu truy cập vẫn lỗi, kiểm tra DNS, label của Pod/Namespace, port thực, trạng thái pod và engine thực thi. Đừng xóa default-deny ngay khi thấy lỗi; làm như vậy mất bằng chứng về rule còn thiếu.

## 14. Lab: chỉ cho API gọi database

API được phép gọi database simulator trên TCP 5432. Mở **egress API** và **ingress database**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-egress-db
  namespace: shop-api
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              security-zone: data
          podSelector:
            matchLabels:
              app: db
      ports:
        - protocol: TCP
          port: 5432
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-db-ingress-api
  namespace: shop-data
spec:
  podSelector:
    matchLabels:
      app: db
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              security-zone: api
          podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 5432
~~~

Lưu thành **allow-api-to-db.yaml**, sau đó:

~~~bash
kubectl apply -f allow-api-to-db.yaml

kubectl exec -n shop-api api -- \
  python -c "import urllib.request; print(urllib.request.urlopen('http://db.shop-data.svc.cluster.local:5432/', timeout=3).status)"
~~~

Đây là HTTP server giả lập có cổng 5432, vì vậy phản hồi HTTP chỉ chứng minh kết nối TCP được mở; không kiểm tra quyền PostgreSQL hoặc TLS của database thật.

### Phép thử bị từ chối

Frontend **không** được gọi database:

~~~bash
kubectl exec -n shop-web frontend -- \
  wget -T 3 -O - http://db.shop-data.svc.cluster.local:5432/
~~~

Nếu DNS đã được mở, yêu cầu vẫn nên **thất bại ở kết nối dữ liệu** vì frontend không có egress tới db và db không cho ingress từ frontend. Một trường hợp thất bại vì DNS hoặc ứng dụng down chưa đủ làm bằng chứng policy hoạt động.

## 15. Bảng nghiệm thu luồng mạng

Sau khi áp đầy đủ các policy đã mô tả:

| Nguồn | Đích | Giao thức | Kỳ vọng |
|---|---|---|---|
| frontend / shop-web | api / shop-api | TCP 8080 | Cho phép |
| api / shop-api | db / shop-data | TCP 5432 | Cho phép |
| frontend / shop-web | db / shop-data | TCP 5432 | Từ chối |
| pod khác không có label nguồn cần thiết | api / shop-api | TCP 8080 | Từ chối |
| frontend, api | CoreDNS được chọn | UDP/TCP 53 | Cho phép |
| api | Internet tùy ý | TCP 443 | Từ chối theo mẫu egress đã áp, trừ luồng khác được policy cho phép |
| db | API | TCP 8080 | Từ chối kết nối mới theo policy mẫu |

**Kết nối phản hồi** cho một phiên đã được phép thường được dataplane xử lý theo cơ chế stateful/tracking của network policy implementation. Điều này không có nghĩa pod database tự được quyền mở một phiên **mới** về API.

### Phân biệt lỗi được chặn với lỗi ứng dụng

Với phép thử được phép, cần xác nhận mã phản hồi hoặc dữ liệu từ đúng backend. Với phép thử bị từ chối, kiểm tra DNS đã đúng, pod đích khỏe mạnh và kết quả không phải **HTTP 403/404 do ứng dụng** tự trả.

Một NetworkPolicy chặn L3/L4 thường biểu hiện bằng timeout hoặc kết nối không thành công, tùy dataplane, không nhất thiết trả mã HTTP. Khi cùng một phép thử được phép ở baseline nhưng bị chặn sau policy, bằng chứng mạnh hơn so với chỉ một lần chạy thất bại.

## 16. Ingress controller và luồng vào frontend

Trong ví dụ lab, frontend chỉ là pod client, không có HTTP server để nhận ingress. Trong ứng dụng thật, frontend có thể được Service/Ingress hoặc Azure Application Gateway for Containers chuyển lưu lượng vào.

Nếu đã dùng default-deny ingress trong **shop-web**, phải mở chính xác luồng từ **ingress controller hoặc thành phần nhận traffic** đến frontend. Ví dụ ingress controller chạy như pod thuộc namespace có label **security-zone=ingress** và label **app=ingress-controller**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-from-ingress
  namespace: shop-web
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              security-zone: ingress
          podSelector:
            matchLabels:
              app: ingress-controller
      ports:
        - protocol: TCP
          port: 8080
~~~

Đây là **ví dụ điều kiện**, không nên áp nguyên xi trước khi xác định ingress thực tế. Nếu traffic đến qua node, load balancer, gateway ngoài cluster hoặc có SNAT/DNAT, source IP mà dataplane quan sát có thể khác. Cần kiểm tra đường đi của ingress controller/AKS networking đang sử dụng.

**Kubernetes Ingress resource không tự áp một NetworkPolicy vào pod backend.** Ingress/Service định tuyến traffic; NetworkPolicy kiểm soát điều kiện kết nối giữa các endpoint theo dataplane.

## 17. Kết nối DNS, Azure services và egress Internet

Egress default-deny có thể ngắt những dependency ít được nhìn thấy:

- CoreDNS hoặc DNS resolver tùy biến.
- Azure Key Vault, Azure Storage, Service Bus, Container Registry hoặc endpoint identity.
- Azure Monitor, OpenTelemetry collector, log/metrics agent.
- Service mesh control plane, certificate authority hoặc dịch vụ mTLS.
- Update check, telemetry hoặc webhook của ứng dụng.
- Endpoint ngoài Internet mà ứng dụng thực sự cần.

Hãy lập **bảng egress inventory** trước khi bật deny:

| Nguồn | Đích | Cổng | Vì sao cần | Cách giới hạn |
|---|---|---|---|---|
| frontend | API pods | TCP 8080 | Gọi API | namespaceSelector + podSelector |
| API | DB pods | TCP 5432 | Đọc/ghi nghiệp vụ | namespaceSelector + podSelector |
| frontend/API | CoreDNS | UDP/TCP 53 | Phân giải tên | Labels DNS đã kiểm tra |
| API | Azure Storage private endpoint | TCP 443 | Đọc/ghi dữ liệu | Thiết kế IP/egress theo dataplane và routing |
| API | Key Vault endpoint | TCP 443 | Đọc secret bằng identity | Thiết kế FQDN/egress nâng cao hoặc outbound firewall |
| Workload | Telemetry collector pods | TCP theo agent | Gửi logs/traces | Namespace/pod selectors |

### NetworkPolicy chuẩn không lọc theo FQDN

Trường **to.ipBlock** của NetworkPolicy chuẩn sử dụng CIDR, không cho phép khai báo trực tiếp **storageaccount.blob.core.windows.net** như một điều kiện FQDN. Azure service public IP có thể thay đổi; mở whitelist IP tĩnh thủ công có thể không bền vững.

Nếu yêu cầu “chỉ được kết nối tới một domain cụ thể”, cần đánh giá **Azure Firewall/FQDN filtering, proxy, Cilium-specific policies hoặc biện pháp egress nâng cao được hỗ trợ**, không giả định Kubernetes NetworkPolicy chuẩn tự kiểm tra hostname/TLS SNI.

### Private Endpoint

Khi pod gọi dịch vụ Azure qua Private Endpoint, DNS nên phân giải về private IP và route phải hợp lệ. NetworkPolicy egress có thể cần cho phép lưu lượng tới địa chỉ đích/cổng thích hợp theo behavior của dataplane. Đồng thời phải kiểm tra NSG, UDR và Azure Firewall trên đường mạng.

**Private Endpoint không tự cấp quyền truy cập dữ liệu**: workload vẫn cần managed identity/Workload Identity và role data plane phù hợp.

## 18. ipBlock, CIDR và các giới hạn cần biết

NetworkPolicy hỗ trợ chọn dải IP:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-outbound-to-approved-range
  namespace: shop-api
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes: [Egress]
  egress:
    - to:
        - ipBlock:
            cidr: 10.90.20.0/24
            except:
              - 10.90.20.128/25
      ports:
        - protocol: TCP
          port: 443
~~~

Ví dụ cho phép API đi TCP 443 tới một phần dải **10.90.20.0/24**, loại trừ nửa sau **10.90.20.128/25**. Các địa chỉ chỉ là minh họa; không có bằng chứng chúng thuộc hệ thống Azure nào của người học.

### Hạn chế quan trọng

- **ipBlock phù hợp hơn với endpoint IP ổn định bên ngoài tập pod**; dùng pod/namespace selectors cho lưu lượng pod-to-pod.
- Khi gói tin đi qua Service, NAT hoặc thành phần proxy, địa chỉ mà policy nhìn thấy có thể phụ thuộc vào CNI/dataplane. Không suy đoán việc khớp CIDR dựa duy nhất trên tên Service.
- Kubernetes NetworkPolicy chuẩn không mặc định điều khiển mọi traffic từ node, hostNetwork pod hoặc thành phần host networking theo cùng cách với pod thường.
- Không dùng **0.0.0.0/0** chỉ để sửa lỗi DNS hoặc cho toàn bộ egress Internet nếu chính sách least privilege đang là mục tiêu.
- Cấu hình IP block không thay thế policy của Azure Firewall/NSG hoặc quy tắc truy cập dữ liệu ở dịch vụ đích.

## 19. AKS NetworkPolicy, NSG và Azure Firewall khác nhau thế nào?

| Cơ chế | Vị trí/vấn đề | Đơn vị kiểm soát điển hình |
|---|---|---|
| **Kubernetes NetworkPolicy** | Giao tiếp giữa pod/namespace ở L3/L4 | Pod selectors, namespace selectors, IP/CIDR, cổng |
| **Azure Network Security Group (NSG)** | Lưu lượng mạng Azure ở phạm vi subnet/NIC theo khả năng áp dụng | IP, protocol, port, service tags theo Azure |
| **Azure Firewall/NVA** | Kiểm soát north-south/egress hoặc tuyến tập trung | IP/network rules, một số FQDN/application rules và logging |
| **Ingress controller/Application Gateway** | Nhận và định tuyến HTTP(S) vào workload | Host, path, listener, backend |
| **Service mesh authorization** | Một số chính sách Layer 7/mTLS giữa service | Workload identity, HTTP method/path tùy mesh |
| **Kubernetes RBAC/Entra ID** | Ai được thao tác API Kubernetes/Azure | Danh tính, resource, verb, scope |

Không dùng NSG như cơ chế tương đương NetworkPolicy để phân biệt **app=frontend** và **app=db**. Trong AKS dùng Overlay hoặc CNI khác, IP pod, định tuyến và NAT có thể khiến NSG không có ngữ nghĩa pod label. Cần hiểu lớp nào thực thi luật nào.

### L3/L4 không thay thế L7

NetworkPolicy có thể cho phép frontend gọi API trên TCP 8080 nhưng không biết request đó là **GET /orders** hay **DELETE /admin/users**. Ứng dụng vẫn phải kiểm tra token, vai trò, quyền đối tượng và giới hạn API; mTLS/service mesh có thể bổ sung xác thực kết nối khi kiến trúc hỗ trợ.

## 20. Kiểm tra AKS networking trước khi áp dụng

### Lệnh đọc thông tin AKS

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az aks show \
  --resource-group "<AKS_RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER_NAME>" \
  --query "{name:name,kubernetesVersion:kubernetesVersion,networkPlugin:networkProfile.networkPlugin,pluginMode:networkProfile.networkPluginMode,networkPolicy:networkProfile.networkPolicy,networkDataplane:networkProfile.networkDataplane}" \
  --output json
~~~

Kết quả giúp xác nhận kiểu plugin, mode, policy và dataplane mà API công bố. Một trường có thể vắng hoặc có giá trị khác tùy version/tính năng; không tự kết luận “không có bảo mật” chỉ vì một field là null. Cần đối chiếu cấu hình cluster thực tế với hướng dẫn AKS đang áp dụng.

### Lệnh đọc Kubernetes policies và labels

~~~bash
kubectl get networkpolicies --all-namespaces
kubectl describe networkpolicy -n shop-api allow-api-ingress-web
kubectl get pods -n shop-api --show-labels
kubectl get namespaces --show-labels
kubectl get services -n shop-api
kubectl get endpointslices -n shop-api
~~~

Các lệnh trên chủ yếu chỉ đọc thông tin Kubernetes; quyền cần thiết phụ thuộc RBAC. **kubectl get networkpolicy** chứng minh Kubernetes API lưu policy chứ **chưa chứng minh dataplane đang thực thi**. Bằng chứng thực thi đến từ kiểm tra kết nối và telemetry của engine.

### Kiểm tra policy selector

~~~bash
kubectl get networkpolicy -n shop-api -o yaml
kubectl describe pods -n shop-api
~~~

Đối chiếu:

1. Policy nằm đúng namespace.
2. Pod selector khớp labels của pod.
3. Namespace selector khớp labels hiện tại của namespace nguồn/đích.
4. Hướng **Ingress/Egress** đúng.
5. Cổng backend thực tế đúng.
6. Không có policy khác mở rộng quyền một cách ngoài ý muốn.

## 21. Quy trình áp chính sách trong production

Không áp default-deny trên toàn cluster chỉ trong một bước. Một trình tự giảm rủi ro:

1. **Khảo sát:** lập sơ đồ namespace, pod labels, Service, ingress controller, DNS, Azure dependencies và network policy engine.
2. **Chọn phạm vi nhỏ:** bắt đầu một namespace thử nghiệm hoặc workload không quan trọng.
3. **Đo baseline:** ghi lại các kết nối thành công/không thành công, IP/cổng thực và log ứng dụng.
4. **Viết allow rules:** liệt kê tất cả luồng hợp lệ trước khi bật deny.
5. **Kiểm tra với manifests:** review selector, quy tắc AND/OR, cổng và host/network exceptions.
6. **Áp dần:** bật default-deny với cửa sổ thay đổi phù hợp; giám sát ngay.
7. **Kiểm thử tích cực:** frontend→API, API→DB, DNS, ingress, telemetry, identity thành công.
8. **Kiểm thử tiêu cực:** frontend→DB hoặc pod không được phép→API bị từ chối.
9. **Giám sát:** đo lỗi kết nối, DNS, timeout, ứng dụng, các thay đổi trong policy.
10. **Tự động hóa:** đưa chính sách vào GitOps/IaC, review và tạo bộ kiểm thử regression.

### Rollback

Nên có manifest phiên bản trước và cách khôi phục chính sách đã được kiểm tra, ví dụ thay đổi allow rules hoặc hoàn tác một policy thử nghiệm. Không xem **xóa tất cả NetworkPolicy** là rollback an toàn trong production vì nó có thể mở toàn bộ mạng nội bộ.

Trong lab riêng, có thể dọn tài nguyên đã tạo khi chắc chắn namespace chỉ chứa workload thử nghiệm:

~~~bash
# Chỉ chạy trên cluster lab; ba namespace phải thực sự dành riêng cho bài học.
kubectl delete namespace shop-web shop-api shop-data
~~~

Lệnh delete là thao tác phá hủy tài nguyên; **không** sử dụng nếu những namespace này chứa workload cần giữ. Khi việc kiểm tra policy có ảnh hưởng đến cụm dùng chung, liên hệ người chịu trách nhiệm cluster và tuân thủ change management.

## 22. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| NetworkPolicy đã tạo nhưng lưu lượng vẫn thông | Chưa có engine thực thi; selector không khớp; policy khác cho phép | Xem AKS networking, pod labels, toàn bộ policy và thử kết nối |
| DNS hỏng sau default-deny | Egress UDP/TCP 53 chưa mở hoặc selector CoreDNS sai | Xem CoreDNS labels, NodeLocal DNS, NS service và test DNS |
| Frontend không gọi được API | Chỉ mở một phía; thiếu egress web hoặc ingress API | Kiểm tra cả hai policy và cổng backend |
| API không gọi được database | Sai namespace labels/pod labels, cổng hoặc egress | Kiểm tra Service endpoints, selector, ingress DB và egress API |
| Ingress controller báo 502/504 | Pod backend không nhận được từ nguồn controller thực | Kiểm tra datapath, nguồn thực, policy ingress và trạng thái app |
| Pod không truy cập được Azure Storage/Key Vault | Egress deny, private DNS, UDR/firewall, identity | Kiểm tra DNS/IP/port trước rồi xác minh RBAC |
| Policy mở rộng quá nhiều | namespaceSelector và podSelector nằm ở hai danh sách khác nhau | Xem AND/OR, review YAML indentation |
| Một policy chặn nhưng kết nối vẫn được | Policy khác cùng chọn pod và cho phép | Tổng hợp toàn bộ allow rules trên pod |
| Service ClusterIP có vẻ lỗi | Service endpoints rỗng, port/targetPort sai hoặc policy chặn | Xem Endpoints/EndpointSlice, test pod IP và Service |
| Một số node/pod không nhất quán | Dataplane hoặc policy agent lỗi, rollout/cấu hình khác nhau | Xem trạng thái node, agent, logs và version hỗ trợ |
| Pod mới deploy bị ngắt kết nối | Labels/template khác, namespace không mang nhãn mong đợi | So sánh manifest, labels pod thực và rollout |
| App lỗi HTTPS nhưng TCP vẫn thông | TLS, DNS SNI, quyền hoặc ứng dụng chứ không phải L3/L4 | Xem HTTP/TLS error, chứng chỉ và app logs |

### Chẩn đoán theo tầng

1. **Tầng ứng dụng:** pod có Ready không, có process đang nghe cổng đúng không?
2. **Service discovery:** DNS có trả đúng Service/IP không, Service có backend endpoints không?
3. **NetworkPolicy:** policy nào chọn nguồn và đích, hai hướng có allow rule không?
4. **Dataplane/CNI:** AKS có engine thực thi không, tình trạng network agent thế nào?
5. **Azure networking:** NSG/UDR/Azure Firewall/Private Endpoint có ảnh hưởng không?
6. **Identity/TLS:** khi TCP kết nối được nhưng trả 401/403/5xx, kiểm tra RBAC/tokens/TLS/app.

Đừng khắc phục lỗi 403 của ứng dụng bằng cách mở egress toàn Internet. Ngược lại, nếu DNS timeout, đừng tăng quyền Azure RBAC khi nguyên nhân nằm ở NetworkPolicy.

## 23. Trường hợp đặc biệt và giới hạn của NetworkPolicy chuẩn

### Pod dùng hostNetwork hoặc lưu lượng node

NetworkPolicy chuẩn chủ yếu nhắm vào pod network. Traffic liên quan **hostNetwork**, node-local services, kubelet, host endpoint và một số luồng hệ thống có đặc điểm phụ thuộc dataplane/CNI. Không giả định default-deny của một namespace đã bảo vệ toàn bộ giao tiếp với node hoặc host.

### Các giao thức và chức năng ngoài chuẩn

NetworkPolicy chuẩn tập trung vào TCP, UDP và SCTP theo khả năng mạng. Nó không mô tả toàn bộ luật Layer 7 như URL path, HTTP method, gRPC method, database user hoặc FQDN. Một số engine như Cilium có chính sách mở rộng, nhưng đó là **CRD/chức năng riêng**, không phải nội dung của Kubernetes NetworkPolicy API chuẩn.

### Egress ra Internet, SNAT và chính sách CIDR

Lưu lượng egress có thể đi qua NAT Gateway, load balancer outbound, Azure Firewall hoặc routing riêng. NetworkPolicy ở pod và Azure Firewall trên đường egress phải được xem xét kết hợp. IP mà dịch vụ đích nhìn thấy có thể là địa chỉ sau NAT, khác với địa chỉ pod nguồn.

### Cluster upgrades

Nâng cấp phiên bản AKS/CNI có thể thay đổi thành phần dataplane hoặc cách xử lý những corner cases, vì vậy cần kiểm tra chính sách trong môi trường staging sau nâng cấp. Không dựa vào quy tắc NAT/service routing không được chuẩn Kubernetes bảo đảm.

## 24. Bảo mật và quản trị chính sách

### RBAC

Người có quyền **create/update/delete NetworkPolicy** có thể mở rộng hoặc thay đổi khả năng giao tiếp giữa các pod. Cần hạn chế quyền theo namespace và phân tách nhóm phát triển với nhóm quản trị cluster khi phù hợp.

Quyền sửa **namespace labels**, pod labels trong Deployment và admission policies cũng ảnh hưởng an ninh của selector. Một policy được viết rất chặt có thể mất ý nghĩa nếu bất kỳ workload nào cũng tự thêm label thuộc nhóm được phép.

### Policy-as-code

- Lưu NetworkPolicy trong Git cùng ứng dụng hoặc kho chính sách được kiểm soát.
- Có code review cho thay đổi selectors, CIDR và cổng.
- Dùng CI kiểm tra schema YAML và áp dụng test policy trong cluster lab.
- Áp dụng admission control/Azure Policy hoặc công cụ tương thích để giữ baseline khi tổ chức cần.
- Theo dõi drift giữa Git và cluster.
- Tránh cấp quyền bypass policy cho các ứng dụng chỉ vì “khẩn cấp” khi chưa có quy trình.

### Bảo vệ nhiều lớp

NetworkPolicy là một lớp trong kiến trúc:

~~~text
Microsoft Entra ID + Kubernetes RBAC
             |
             v
Admission / policy-as-code
             |
             v
NetworkPolicy (pod L3/L4)
             |
             v
Azure NSG / Firewall / Private networking
             |
             v
TLS / workload identity / app authorization
             |
             v
Audit logs / incident response
~~~

Một pod được phép gọi DB qua TCP 5432 vẫn phải có **tài khoản database được cấp quyền**, TLS phù hợp và kiểm soát dữ liệu ở tầng ứng dụng.

## 25. Chi phí và tác động vận hành

Tài nguyên NetworkPolicy chuẩn không có nghĩa mỗi file YAML phát sinh một đơn giá dịch vụ riêng, nhưng triển khai bảo mật mạng có thể làm tăng **độ phức tạp vận hành** và ảnh hưởng tài nguyên:

- Dataplane/policy engine cần được hỗ trợ và vận hành ổn định.
- Logging, flow visibility và truy vết có thể tăng chi phí giám sát.
- Egress qua Azure Firewall/NAT hoặc proxy có chi phí riêng.
- Kiểm thử và CI/GitOps cần môi trường staging.
- Workload có thể phải điều chỉnh DNS, readiness, startup và timeout.

Không tối ưu chi phí bằng cách tắt NetworkPolicy mà không có phương án bù đắp. Nên đo metrics về tỷ lệ kết nối lỗi, hiệu năng và chi phí các thành phần mạng bổ sung, sau đó chọn phạm vi policies và observability hợp lý.

## 26. Bài tập tình huống: cô lập ứng dụng đặt hàng

Một doanh nghiệp có AKS chạy:

- **store-web**: frontend nhận HTTP thông qua ingress controller.
- **store-api**: API đơn hàng, chỉ frontend được gọi trên TCP 8080.
- **store-payments**: xử lý thanh toán, chỉ API được gọi trên TCP 8443.
- **store-db**: database, chỉ API và payments được gọi TCP 5432 theo danh sách quyền riêng.
- **kube-system/CoreDNS**: phục vụ DNS.
- API gọi một Storage Account bằng Private Endpoint trên TCP 443.

### Nhiệm vụ

1. Phân biệt vai trò của namespace, Service, NSG và NetworkPolicy.
2. Đặt nhãn namespace/pod để chọn nguồn và đích rõ ràng.
3. Đề xuất default-deny ingress/egress theo namespace và kế hoạch triển khai theo giai đoạn.
4. Thiết kế ingress allow rules cho API, payments và DB.
5. Thiết kế egress allow rules tương ứng từ frontend, API và payments.
6. Mở DNS có kiểm soát, xử lý trường hợp dùng NodeLocal DNS.
7. Giải thích quyền cần có để API đi tới Storage Private Endpoint và đọc dữ liệu.
8. Nêu vì sao cần kiểm tra cả đường từ ingress controller đến web.
9. Chỉ ra rủi ro nếu tách namespaceSelector và podSelector thành hai phần tử OR.
10. Thiết kế bộ test một kết nối hợp lệ và một kết nối bị chặn cho mỗi tầng.
11. Nêu cách rollback khi chính sách chặn ứng dụng production.
12. Xác định log, alert, quyền thay namespace labels và quy trình review policy.

### Gợi ý hướng giải

Áp namespace labels có ý nghĩa bảo mật, đặt default-deny theo từng namespace rồi mở luồng **ingress controller → web → API → payments/DB** theo nhu cầu thực. Mỗi kết nối khi cả nguồn/đích bị cô lập phải có egress ở nguồn và ingress ở đích. DNS được mở riêng, Storage qua Private Endpoint cần thiết kế cả IP/route, DNS và quyền dữ liệu. Không mở database trực tiếp từ frontend.

Nếu ứng dụng gọi payments ở TCP 8443, NetworkPolicy cho phép cổng này **không tự bảo đảm** thanh toán an toàn: vẫn cần mTLS/TLS, authentication, authorization và bảo vệ bí mật.

## 27. Checklist production

| Hạng mục | Cần xác minh |
|---|---|
| AKS networking | Network plugin/dataplane/policy engine hỗ trợ NetworkPolicy |
| Namespace | Nhãn phân quyền và người có quyền sửa nhãn được quản lý |
| Pod labels | Selector khớp Deployment/Pods thực tế |
| Baseline | Có bản đồ kết nối trước khi áp deny |
| Default-deny | Có phạm vi đúng, không cắt đồng loạt namespace hệ thống |
| Ingress | API/DB chỉ nhận từ đúng nguồn và đúng port |
| Egress | Workload chỉ gọi đúng backend/hạ tầng cần thiết |
| DNS | UDP/TCP 53 và thực tế CoreDNS/NodeLocal được kiểm tra |
| Ingress controller | Luồng tới frontend qua dataplane thực có phép |
| Azure dependencies | Private Endpoint, DNS, identity và mạng outbound đúng |
| Test positive | Luồng hợp lệ kết nối thành công |
| Test negative | Luồng ngoài danh sách bị chặn vì policy, không phải do app down |
| GitOps | YAML được review, có trạng thái mong muốn và rollback |
| RBAC | Hạn chế chỉnh NetworkPolicy/namespace labels |
| Monitoring | Có log, metrics, alert và quy trình điều tra |
| Upgrades | Policies được thử lại sau nâng cấp AKS/CNI |

## 28. Câu hỏi tự kiểm tra

1. Tại sao tạo hai namespace khác nhau không tự cô lập mạng giữa các pod?
2. Khi nào Kubernetes NetworkPolicy bắt đầu cô lập ingress hoặc egress của một pod?
3. NetworkPolicy chuẩn có deny rule và priority không?
4. Hai policy cùng chọn một pod được kết hợp như thế nào?
5. Vì sao một kết nối frontend → API có thể cần cả egress frontend lẫn ingress API?
6. **podSelector: {}** ở spec có ý nghĩa gì?
7. Tại sao namespaceSelector và podSelector cùng một mục trong from khác với hai mục riêng?
8. Một policy có namespace **shop-api** có thể trực tiếp cô lập egress của pod ở **shop-web** không?
9. Sau default-deny egress, vì sao tên Service có thể không phân giải được?
10. Vì sao mở UDP 53 đôi khi chưa đủ cho DNS?
11. Vì sao NetworkPolicy không đơn giản chọn backend theo tên Kubernetes Service?
12. Vì sao Kubernetes NetworkPolicy chuẩn không lọc được URL path và HTTP method?
13. Khi dùng ipBlock, NAT và Service có thể làm phép thử CIDR phức tạp hơn như thế nào?
14. Vai trò khác nhau của AKS NetworkPolicy và Azure NSG/Firewall là gì?
15. Vì sao kết quả kubectl get networkpolicy chưa chứng minh dataplane đang chặn?
16. Vì sao traffic từ hostNetwork hoặc node cần được xem xét riêng?
17. Khi app lỗi sau áp default-deny, cần kiểm tra gì trước khi mở rộng egress?
18. Làm thế nào chứng minh một luồng bị chặn vì policy chứ không phải DNS hoặc backend lỗi?
19. Tại sao người có quyền sửa namespace labels có thể ảnh hưởng chính sách mạng?
20. Bạn sẽ triển khai NetworkPolicy trên AKS production theo những bước nào để giảm nguy cơ downtime?

## Tài liệu tham khảo

- Kubernetes — *Network Policies*: https://kubernetes.io/docs/concepts/services-networking/network-policies/
- Kubernetes — *Declare Network Policy*: https://kubernetes.io/docs/tasks/administer-cluster/declare-network-policy/
- Microsoft Learn — *Secure traffic between pods using network policies in AKS*: https://learn.microsoft.com/azure/aks/use-network-policies
- Microsoft Learn — *Azure CNI Powered by Cilium*: https://learn.microsoft.com/azure/aks/azure-cni-powered-by-cilium
- Microsoft Learn — *AKS networking concepts*: https://learn.microsoft.com/azure/aks/concepts-network
- Microsoft Learn — *Azure CNI overview*: https://learn.microsoft.com/azure/aks/azure-cni-overview
- Microsoft Learn — *Control egress traffic for AKS clusters*: https://learn.microsoft.com/azure/aks/limit-egress-traffic
- Microsoft Learn — *Azure Network Security Groups*: https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview
