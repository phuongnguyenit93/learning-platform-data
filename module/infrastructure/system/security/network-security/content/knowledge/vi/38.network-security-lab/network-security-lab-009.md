# Lab: Thêm network policy cho container hoặc Kubernetes

## 1. Bài toán bảo mật: container chạy được chưa có nghĩa mạng đã được phân đoạn

Khi triển khai ứng dụng theo mô hình container, nhiều nhóm tập trung vào việc Pod chạy ổn, Service phân giải DNS thành công và lưu lượng giữa các thành phần thông suốt. Tuy nhiên, nếu không giới hạn các đường kết nối **east–west** giữa workload, một container bị xâm nhập có thể kết nối thử tới các dịch vụ nội bộ không thuộc nhu cầu nghiệp vụ. Phân đoạn ở ranh giới VPC hay firewall ngoài cụm chưa chắc đủ để ngăn việc này.

**Kubernetes NetworkPolicy** là tài nguyên API dùng để mô tả chính sách **được phép** đối với lưu lượng vào (*ingress*) và ra (*egress*) của một nhóm Pod. Việc thực thi phụ thuộc vào plugin mạng **CNI/network policy engine** đang được cài trên cụm. Đây là cách đưa nguyên tắc **least privilege**, **default deny** và **microsegmentation** vào môi trường container, giúp hỗ trợ nhiều lớp phòng thủ cùng firewall, VPN, IDS/IPS, DNS security và giám sát lưu lượng.

Bài thực hành thuộc chương **Dự án thực hành bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**. Chúng ta sẽ tạo một môi trường lab an toàn, mô phỏng ứng dụng **frontend → api** và một client không được cấp quyền, sau đó lần lượt triển khai:

1. Đo lưu lượng **trước** khi áp policy.
2. Đặt **default deny ingress** cho namespace thử nghiệm.
3. Chỉ cho phép Pod gắn nhãn `app=frontend` kết nối `api` qua TCP/80.
4. Hạn chế **egress của frontend** để chỉ tới API và dịch vụ DNS được phép.
5. Kiểm chứng luồng được phép/bị chặn, phân tích lỗi DNS/CNI và quan sát policy.
6. Thử một policy bổ sung cross-namespace, rồi thu hồi để chứng minh tính **cộng gộp** của NetworkPolicy.
7. Dọn toàn bộ tài nguyên lab và liên hệ mô hình với Docker Compose.

**Sản phẩm bàn giao của lab:** bộ manifest mẫu, ma trận connectivity trước/sau, kết quả kiểm tra, giải thích semantics của policy, checklist triển khai production và kế hoạch rollback.

> **Giới hạn:** Thực hiện trên **cluster lab hoặc namespace đã được cấp phép**, không áp default-deny lên namespace production/dịch vụ chia sẻ khi chưa khảo sát dependencies và có phương án khôi phục. Lệnh trong bài có thể làm mất kết nối Pod được chọn nếu áp vào sai phạm vi.

## 2. Mục tiêu học tập và tiêu chí hoàn thành

Sau lab, người học có thể:

- Giải thích sự khác nhau giữa **Kubernetes Service**, firewall ngoài cluster, CNI và NetworkPolicy.
- Hiểu khi nào Pod được coi là **isolated** theo chiều ingress/egress.
- Viết `podSelector`, `namespaceSelector`, `policyTypes`, `ingress`, `egress` và `ports` đúng ý định.
- Tạo một allowlist theo **nhãn workload** thay vì dựa vào Pod IP thay đổi liên tục.
- Hiểu cách NetworkPolicy có hiệu lực theo **hợp của các rule cho phép**, không có thứ tự “first match wins” và không có rule `deny` ưu tiên cao hơn.
- Xác minh DNS, TCP/80, lưu lượng bị chặn, và phân biệt **deny bởi policy** với lỗi ứng dụng/DNS/route.
- Phát hiện các điều kiện khó: CNI không hỗ trợ enforcement, NodeLocal DNSCache, Service NAT, hostNetwork, IPv6, phiên kết nối đã tồn tại, policy drift.
- Mô tả vai trò của GitOps, RBAC, admission guardrails và flow observability trong bảo vệ mạng container.

**Tiêu chí thành công:** từ `frontend` truy cập được `api`; từ `intruder` không truy cập được `api`; sau khi hạn chế egress, `frontend` vẫn phân giải tên và tới đúng API, nhưng không kết nối tới một dịch vụ thử nghiệm **ngoài allowlist**. Khi gỡ policy có điều kiện, hành vi trở về baseline. Kết quả phải được chứng minh bằng thực tế, không chỉ bằng `kubectl apply` thành công.

## 3. Điều kiện tiên quyết và an toàn lab

### 3.1. Yêu cầu kỹ thuật

| Thành phần | Yêu cầu |
|---|---|
| Kubernetes | Cluster lab có API `networking.k8s.io/v1` và namespace riêng được phép thao tác |
| CNI/policy engine | **Phải thực sự hỗ trợ và bật thực thi Kubernetes NetworkPolicy**; ví dụ cấu hình Calico, Cilium hoặc plugin hỗ trợ tương đương |
| Quyền | Có thể tạo namespace, Deployment, Pod, Service và NetworkPolicy trong phạm vi lab |
| Công cụ | `kubectl`, kết nối tới cluster đúng context, shell để lưu manifest |
| Workload lab | Image Nginx và BusyBox từ registry được phép, phù hợp kiến trúc CPU của cluster |
| DNS | CoreDNS hoặc DNS service tương đương; biết namespace và nhãn Pod DNS thực tế |
| Quan sát | Quyền đọc Pod/Service/Policy, sự kiện, log và thông tin policy engine phù hợp |

**Lưu ý quan trọng:** Kubernetes chấp nhận đối tượng `NetworkPolicy` qua API ngay cả khi plugin mạng không thực thi nó. Vì vậy `kubectl apply` thành công **không chứng minh** traffic đã bị chặn. Một cluster dùng cấu hình mạng mặc định không hỗ trợ policy (ví dụ nhiều cấu hình kindnet cơ bản) sẽ không cho kết quả đúng lab này. Hãy kiểm tra CNI và chọn cluster có enforcement trước.

Trong thực tế, `kubectl get pods -n kube-system` giúp xem các thành phần mạng, nhưng tên Pod **không tự chứng minh** enforcement. Tốt nhất dùng tài liệu của platform owner, một bài test allow/deny trong namespace thử nghiệm và telemetry của CNI.

### 3.2. Ranh giới thao tác

- Các tên `netpol-lab` và `netpol-external` dưới đây chỉ là namespace dành cho lab. Không được tự xóa hoặc sử dụng chúng nếu đã thuộc ứng dụng khác.
- Không áp `podSelector: {}` vào namespace production khi chưa đánh giá tác động; selector này chọn **mọi Pod trong namespace**.
- Không thử scan dải IP, truy cập dữ liệu hay workload không thuộc quyền kiểm thử. Chỉ thử các endpoint được tạo trong lab.
- Trước khi bắt đầu, xác minh `kubectl config current-context` và `kubectl cluster-info`, rồi xác nhận đó là cluster đúng.
- Nếu mạng đang bị lỗi, **ngừng thử và hỏi owner**; không tự mở policy rộng kiểu any-any để giải quyết cho nhanh.
- Trong tổ chức, các manifest nên được pin image theo digest đã rà soát và qua quy trình thay đổi có kiểm soát. Tag trong ví dụ chỉ giúp minh họa cách chạy.

## 4. Topology và luồng mong muốn

Chúng ta dùng hai namespace:

- `netpol-lab`: Pod `frontend` (client hợp lệ), Pod `intruder` (client không có quyền), Deployment/Service `api`.
- `netpol-external`: Deployment/Service `public-echo` để kiểm tra **egress không được cấp phép** sau khi áp policy. Tên “public” ở đây chỉ để phân biệt, **không mở ra Internet**.
- `kube-system`: DNS của cụm (nếu dùng CoreDNS với nhãn phù hợp). Cách DNS hoạt động có thể khác theo cluster, cần xác minh.

~~~mermaid
flowchart TD
  subgraph LAB["Namespace netpol-lab"]
    FE["frontend | app=frontend"]
    IN["intruder | app=intruder"]
    API["api Pod | app=api | TCP 80"]
    SVC["Service api | ClusterIP"]
    FE -->|"Allowed: TCP 80"| SVC
    IN -.->|"Denied ingress"| SVC
    SVC --> API
  end
  subgraph EXT["Namespace netpol-external"]
    PE["Service/Pod public-echo | TCP 80"]
  end
  subgraph SYS["kube-system / cluster DNS"]
    DNS["CoreDNS hoặc DNS implementation"]
  end
  FE -->|"Allowed: UDP/TCP 53"| DNS
  FE -.->|"Denied egress khi chưa có exception"| PE
~~~

### 4.1. Ma trận kiểm thử theo giai đoạn

| Luồng | Baseline chưa có policy | Sau default-deny ingress + allow frontend | Sau thêm giới hạn egress frontend |
|---|---|---|---|
| frontend → api:80 | Cho phép theo cấu hình lab mặc định | **Cho phép** | **Cho phép** |
| intruder → api:80 | Cho phép theo cấu hình lab mặc định | **Chặn** tại ingress API | **Chặn** |
| frontend → public-echo:80 | Cho phép nếu cluster không có policy khác | Cho phép | **Chặn** bởi egress frontend |
| frontend → DNS:53 | Cho phép theo cấu hình lab mặc định | Cho phép theo egress mặc định | **Cho phép nếu DNS rule khớp hạ tầng thực** |
| traffic khác vào Pod trong netpol-lab | Phụ thuộc chính sách sẵn có | Mặc định bị chặn, trừ allow policy | Giữ nguyên giới hạn ingress |

Bảng mô tả **kỳ vọng khi CNI thực thi NetworkPolicy** và cluster lab không có kiểm soát khác chồng lấn. Kubernetes Service, load balancer, DNS và các chính sách khác có thể ảnh hưởng kết quả, nên cần kiểm tra thực tế.

## 5. NetworkPolicy hoạt động như thế nào?

### 5.1. Policy chọn Pod, không chọn Service

Một NetworkPolicy sống trong **namespace** và dùng `spec.podSelector` để xác định nhóm **Pod đích của chính policy** trong namespace đó. Service có thể trỏ tới Pod đó, nhưng Kubernetes NetworkPolicy chuẩn **không có trường chọn Service theo tên**.

Ví dụ:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: example-select-api
  namespace: netpol-lab
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
  ingress: []
~~~

Đối tượng trên chọn các Pod `app=api` và **không cho phép ingress nào theo bản thân policy**. Vì policy chọn Pod cho ingress, Pod được coi là **isolated for ingress**; traffic ingress chỉ được cho phép nếu một NetworkPolicy khác áp dụng với rule phù hợp. Để kiểm tra semantics đúng, phải tính **tập hợp tất cả policy** cùng chọn Pod chứ không chỉ một file YAML.

### 5.2. Ingress và egress là hai chiều độc lập

- Một Pod được **isolated for ingress** nếu có ít nhất một policy chọn nó với `Ingress` trong `policyTypes`.
- Một Pod được **isolated for egress** nếu có ít nhất một policy chọn nó với `Egress` trong `policyTypes`.
- Nếu chưa bị isolate ở một chiều bởi policy, **NetworkPolicy không hạn chế chiều đó**, nhưng firewall/CNI khác vẫn có thể hạn chế.
- Với lưu lượng Pod→Pod, khi cả hai phía bị cô lập theo policy, kết nối được phép cần **egress ở nguồn và ingress ở đích đều chấp nhận**. Các policy không tạo rule deny ưu tiên.
- Các rule **cộng gộp theo phép hợp (additive union)**: nếu bất kỳ rule allow phù hợp trong các policy áp dụng cho một chiều thì chiều đó được phép.
- Policy là điều khiển chủ yếu ở **L3/L4** (địa chỉ/nhãn, giao thức, cổng); không phân biệt URL, method HTTP, identity ứng dụng hay nội dung gói theo API chuẩn.

### 5.3. Default deny phải được hiểu chính xác

~~~yaml
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress: []
~~~

`podSelector: {}` là **tất cả Pod trong namespace**, không phải toàn cluster. `ingress: []` là không có rule allow từ policy này. Nhưng nếu còn policy khác chọn cùng Pod và cho phép ingress, **vẫn có ingress được phép**. Vì vậy “default deny” không phải một rule deny bất khả xâm phạm.

Tương tự:

~~~yaml
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress: []
~~~

Khi áp chính sách mẫu cho egress, cần allow traffic cần thiết tới DNS/API/monitoring; áp vội có thể làm Pod mất phân giải tên hoặc liên lạc với dependency.

## 6. Chuẩn bị lab bằng kubectl

Các lệnh bên dưới minh họa trên terminal với `kubectl`. Nếu dùng Windows PowerShell, cách quote và chạy shell có thể khác; **các file YAML đều có thể lưu trực tiếp rồi chạy `kubectl apply -f`**.

### 6.1. Xác nhận context và namespace

~~~bash
kubectl config current-context
kubectl cluster-info

# Chỉ chạy khi đã xác nhận đúng cluster lab và có quyền.
kubectl create namespace netpol-lab
kubectl create namespace netpol-external

# Giúp theo dõi và làm ví dụ cho namespaceSelector.
kubectl label namespace netpol-lab purpose=networkpolicy-lab
kubectl label namespace netpol-external purpose=networkpolicy-external

kubectl get namespaces --show-labels
~~~

Nếu namespace đã tồn tại từ một lab trước hoặc thuộc nhóm khác, **không chạy cleanup xóa namespace**. Chọn namespace mới theo quy định tổ chức hoặc xin xác nhận owner.

### 6.2. Tạo API và client

~~~bash
# API demo là Nginx; Deployment tự gắn label app=api.
kubectl -n netpol-lab create deployment api --image=nginx:stable-alpine
kubectl -n netpol-lab expose deployment api --name=api \
  --port=80 --target-port=80

# Hai Pod BusyBox giúp tạo request từ hai danh tính mạng khác nhau.
kubectl -n netpol-lab run frontend --image=busybox:1.36 \
  --restart=Never --labels="app=frontend" \
  --command -- sleep 36000

kubectl -n netpol-lab run intruder --image=busybox:1.36 \
  --restart=Never --labels="app=intruder" \
  --command -- sleep 36000

# Endpoint thử chặn egress nằm ở namespace riêng, không phải Internet.
kubectl -n netpol-external create deployment public-echo \
  --image=nginx:stable-alpine
kubectl -n netpol-external expose deployment public-echo \
  --name=public-echo --port=80 --target-port=80

kubectl -n netpol-lab rollout status deployment/api --timeout=120s
kubectl -n netpol-external rollout status deployment/public-echo --timeout=120s
kubectl -n netpol-lab wait pod/frontend --for=condition=Ready --timeout=120s
kubectl -n netpol-lab wait pod/intruder --for=condition=Ready --timeout=120s
~~~

Một Pod có thể cần lâu hơn để kéo image, bị admission policy từ chối hoặc không được schedule; nếu lệnh fail thì kiểm tra trạng thái trước, **không quy kết thành NetworkPolicy**.

~~~bash
kubectl -n netpol-lab get pods -o wide --show-labels
kubectl -n netpol-lab get svc,endpoints
kubectl -n netpol-external get pods,svc -o wide
kubectl -n netpol-lab get networkpolicy
~~~

Nếu namespace đã có policy do một hệ thống quản trị cluster áp vào, baseline có thể khác. Không xóa policy của nền tảng để làm bài dễ hơn; chọn lab cô lập hoặc trao đổi với owner.

## 7. Kiểm tra baseline trước khi thêm policy

Trước khi thay đổi, phải xác minh ít nhất ba luồng:

~~~bash
# frontend được phép gọi API qua Kubernetes Service.
kubectl -n netpol-lab exec frontend -- \
  wget -q -T 3 -O /dev/null http://api

# intruder cũng có thể gọi API nếu chưa có policy nào hạn chế.
kubectl -n netpol-lab exec intruder -- \
  wget -q -T 3 -O /dev/null http://api

# frontend gọi endpoint cross-namespace.
kubectl -n netpol-lab exec frontend -- \
  wget -q -T 3 -O /dev/null \
  http://public-echo.netpol-external.svc.cluster.local

# Kiểm tra DNS độc lập với HTTP.
kubectl -n netpol-lab exec frontend -- nslookup api
~~~

Với `wget -O /dev/null`, exit code **0** thường thể hiện request trả thành công; lỗi có thể do DNS, route, app readiness hoặc NetworkPolicy. Không nên coi mọi timeout là một bằng chứng policy đang chặn.

### 7.1. Cần ghi lại điều gì?

| Trường | Ví dụ record |
|---|---|
| Test phase | `baseline` |
| Cluster/namespace | Lab context xác minh, `netpol-lab` |
| Source Pod/labels | `frontend`, `app=frontend` |
| Destination | `api.netpol-lab.svc.cluster.local:80/tcp` |
| Kết quả | Success, DNS error, connection refused, timeout |
| Mốc thời gian | UTC, thời điểm Pod/Service/Policy được tạo |
| Artifact | Lệnh, `kubectl get`, log ứng dụng, policy list |
| Giới hạn | CNI/Service NAT và các policy khác có thể ảnh hưởng |

Đối với bài học, ghi **trước/sau** rất quan trọng. Nếu baseline đã chặn intruder hoặc endpoint cross-namespace thì không thể khẳng định sự chặn sau đó do policy mới.

## 8. Bước 1 — Default deny ingress trong namespace lab

Tạo file `01-deny-ingress.yaml` trong máy chạy lab (tên file ví dụ, không phải file trong module bài học):

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: lab-default-deny-ingress
  namespace: netpol-lab
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress: []
~~~

Áp chính sách và xem kết quả:

~~~bash
kubectl apply -f 01-deny-ingress.yaml
kubectl -n netpol-lab get networkpolicy
kubectl -n netpol-lab describe networkpolicy lab-default-deny-ingress

# Kỳ vọng với CNI thực thi đúng: cả hai request tới API đều fail.
kubectl -n netpol-lab exec frontend -- \
  wget -q -T 3 -O /dev/null http://api

kubectl -n netpol-lab exec intruder -- \
  wget -q -T 3 -O /dev/null http://api
~~~

**Phân tích:** policy chọn tất cả Pod trong `netpol-lab` và isolate ingress; chưa có rule ingress nào cho API, vì thế HTTP đến API bị chặn. Nó **không chặn egress mặc định** của frontend/intruder. Ngoài ra policy cũng tác động ingress tới frontend/intruder và các Pod khác trong namespace: đây là một hệ quả quan trọng nếu áp nhầm vào production.

Nếu request vẫn thành công, kiểm tra: CNI có hỗ trợ policy không, policy có nằm đúng namespace không, Pod có phù hợp selector không, có policy khác cho phép ingress không, traffic có đi qua đường không được NetworkPolicy bao phủ không.

## 9. Bước 2 — Chỉ cho frontend được kết nối API

Tạo file `02-allow-frontend-api.yaml`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-api
  namespace: netpol-lab
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 80
~~~

~~~bash
kubectl apply -f 02-allow-frontend-api.yaml
kubectl -n netpol-lab get networkpolicy
kubectl -n netpol-lab describe networkpolicy allow-frontend-to-api

# Kỳ vọng: thành công.
kubectl -n netpol-lab exec frontend -- \
  wget -q -T 3 -O /dev/null http://api

# Kỳ vọng: không thành công.
kubectl -n netpol-lab exec intruder -- \
  wget -q -T 3 -O /dev/null http://api
~~~

### 9.1. Đọc manifest theo đúng vai trò

- `metadata.namespace: netpol-lab`: chính sách chỉ áp trong namespace này.
- `spec.podSelector.matchLabels.app: api`: Pod **nhận traffic** được policy chọn.
- `ingress[].from[].podSelector.matchLabels.app: frontend`: chỉ Pod nguồn có label phù hợp **trong cùng namespace**, do không có `namespaceSelector`.
- `ports[].port: 80`, `protocol: TCP`: giới hạn cổng được cho phép.
- Policy `lab-default-deny-ingress` vẫn tồn tại. Rule allow mới **mở đúng một ngoại lệ** cho API, không “ghi đè” hay vô hiệu toàn bộ default deny.

**Điểm quan trọng:** tên Pod `frontend` không được dùng làm danh tính bảo mật trong NetworkPolicy; **nhãn `app=frontend` mới là điều kiện chọn**. Nếu tài khoản không tin cậy có quyền tạo/sửa Pod hoặc label để tự nhận `app=frontend`, chính sách dựa vào nhãn có thể bị lợi dụng. Cần RBAC và admission policy bảo vệ quyền tạo/sửa workload/label, ngoài NetworkPolicy.

### 9.2. Khi nào rule chưa đủ?

Nếu `api` chuyển sang port 8080, policy chỉ cho port 80 không cho phép traffic 8080. Nếu frontend nằm ở namespace khác, `podSelector` đơn độc không chọn được nó. Nếu frontend có egress policy chặn TCP/80, ingress API allow vẫn chưa đủ. Phải xác định rõ **cả hai chiều** trong path.

## 10. Bước 3 — Giới hạn egress của frontend

Ở giai đoạn này, API ingress đã giới hạn; nhưng `frontend` vẫn có thể kết nối tới `public-echo` ở namespace khác khi egress chưa bị isolate. Chúng ta đặt default deny egress **chỉ cho frontend**, rồi thêm allowlist.

### 10.1. Quan sát tình trạng DNS của cluster

Trước khi viết DNS rule, kiểm tra:

~~~bash
kubectl -n netpol-lab exec frontend -- cat /etc/resolv.conf

# Xác minh tên, nhãn Pod DNS và service theo cluster thực tế.
kubectl -n kube-system get pods --show-labels
kubectl -n kube-system get services

# Kiểm tra nhãn namespace để dùng namespaceSelector.
kubectl get namespace kube-system --show-labels
~~~

Ví dụ nhiều cluster chạy CoreDNS trong namespace `kube-system` với Pod label `k8s-app=kube-dns` và namespace label `kubernetes.io/metadata.name=kube-system`. **Không phải cluster nào cũng như vậy**: có NodeLocal DNSCache, CNI đặc biệt, custom labels hoặc dịch vụ DNS khác. Cần thay rule dưới đây bằng **đích thật** đã được platform owner xác nhận, không để rule rộng kiểu “mọi UDP/53 ra toàn bộ cluster” vì tiện.

### 10.2. Đầu tiên: đặt egress deny cho frontend

Tạo file `03-deny-frontend-egress.yaml`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-frontend-egress
  namespace: netpol-lab
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes:
    - Egress
  egress: []
~~~

~~~bash
kubectl apply -f 03-deny-frontend-egress.yaml

# Với egress deny, HTTP tới API và DNS có thể thất bại.
kubectl -n netpol-lab exec frontend -- \
  wget -q -T 3 -O /dev/null http://api
~~~

**Không dừng lab ở đây trong production.** Phần này cố ý tạo mất kết nối **chỉ trong môi trường thử nghiệm** để quan sát tác động. Luồng đã thiết lập từ trước có thể chưa bị cắt ngay, tùy CNI; nên kiểm tra bằng **kết nối mới** và chờ policy hội tụ.

### 10.3. Thêm đúng các egress cần thiết

Tạo file `04-allow-frontend-egress.yaml`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-egress
  namespace: netpol-lab
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes:
    - Egress
  egress:
    # Cho phép frontend gọi các API pod trong cùng namespace.
    - to:
        - podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 80

    # DNS: CHỈ chính xác khi các nhãn này khớp CoreDNS của cluster.
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

Các ý quan trọng:

- `podSelector: app=frontend` trong `spec` chọn **Pod nguồn bị giới hạn egress**.
- Rule đầu cho phép egress TCP/80 tới **Pod API có label app=api** trong namespace.
- Rule thứ hai cho phép UDP/TCP 53 tới Pod DNS có **đồng thời namespace và pod label phù hợp**.
- Không có rule cho `public-echo`, nên egress tới Pod thử nghiệm ngoài allowlist sẽ bị chặn.
- Policy `deny-frontend-egress` vẫn tồn tại; `allow-frontend-egress` bổ sung **quyền allow** vì policy là additive. Không có cú pháp `deny` có mức ưu tiên cao hơn ở NetworkPolicy chuẩn.

~~~bash
kubectl apply -f 04-allow-frontend-egress.yaml
kubectl -n netpol-lab get networkpolicy
kubectl -n netpol-lab describe networkpolicy allow-frontend-egress

# Kỳ vọng nếu DNS rule đúng: DNS phân giải được.
kubectl -n netpol-lab exec frontend -- nslookup api

# Kỳ vọng: frontend gọi API thành công qua Service.
kubectl -n netpol-lab exec frontend -- \
  wget -q -T 3 -O /dev/null http://api

# Kỳ vọng: egress tới public-echo KHÔNG thành công.
kubectl -n netpol-lab exec frontend -- \
  wget -q -T 3 -O /dev/null \
  http://public-echo.netpol-external.svc.cluster.local
~~~

Nếu request cuối fail, cần kiểm tra DNS của `public-echo` trước khi kết luận do egress. Một phép thử sạch hơn là **xác minh DNS trước, rồi kiểm tra TCP tới Pod IP được phép thử** bằng công cụ/flow logs để tách lỗi tên miền khỏi lỗi policy.

### 10.4. Vì sao rule DNS đôi khi không hoạt động?

- Pod DNS thực tế dùng nhãn khác `k8s-app=kube-dns`.
- Pod dùng NodeLocal DNSCache với địa chỉ link-local/nút thay vì trực tiếp tới CoreDNS Pod.
- CNI áp policy ở điểm trước/sau Service DNAT khác kỳ vọng, hoặc DNS service chuyển đổi địa chỉ.
- Chỉ cho UDP/53 nhưng có truy vấn dùng TCP/53 (vì đáp ứng lớn, truncation, policy).
- HostNetwork, node-level resolver hoặc cloud DNS tạo đường đi không được chọn bằng hai selector trong ví dụ.
- Namespace `kube-system` không có/không thể dùng nhãn `kubernetes.io/metadata.name` như giả định hoặc có chính sách cấp cluster chồng lấn.

**Không chữa bằng cách allow toàn bộ egress.** Tìm đúng DNS endpoint và đường đi bằng `resolv.conf`, DNS service/pods, CNI flow logs và trao đổi với chủ cluster. Một số môi trường cần policy theo `ipBlock` tới IP DNS xác định hoặc tính năng CNI riêng; phải đánh giá Service NAT, ổn định IP và giới hạn trust trước.

## 11. Bước 4 — Thử cross-namespace allow rồi thu hồi

Mục tiêu: chứng minh selector trong namespace khác và NetworkPolicy additive.

Trước mắt, `frontend` đã bị egress isolation và không được truy cập `public-echo`. Giả sử một quy trình nghiệp vụ mới **được phê duyệt** cần frontend gọi dịch vụ đó. Tạo file `05-allow-external-demo.yaml`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-external-demo
  namespace: netpol-lab
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              purpose: networkpolicy-external
          podSelector:
            matchLabels:
              app: public-echo
      ports:
        - protocol: TCP
          port: 80
~~~

~~~bash
kubectl apply -f 05-allow-external-demo.yaml

# Kỳ vọng: frontend có thể gọi public-echo sau policy bổ sung.
kubectl -n netpol-lab exec frontend -- \
  wget -q -T 3 -O /dev/null \
  http://public-echo.netpol-external.svc.cluster.local

# Thu hồi ngoại lệ sau thử nghiệm:
kubectl -n netpol-lab delete networkpolicy allow-frontend-external-demo

# Kỳ vọng: kết nối mới tới public-echo lại bị chặn.
kubectl -n netpol-lab exec frontend -- \
  wget -q -T 3 -O /dev/null \
  http://public-echo.netpol-external.svc.cluster.local
~~~

**Phân tích:** quyền ingress tại đích `netpol-external` trong lab mặc định không bị giới hạn nếu không có NetworkPolicy chọn Pod ở namespace đó; chỉ cần egress từ frontend được phép cho kịch bản này. Nếu namespace đích có ingress policy khác, phải kiểm tra cả phía đích. Không áp dụng ngoại lệ cross-namespace chỉ vì DNS thấy service name.

### 11.1. Bẫy YAML: AND khác OR

Trong một phần tử `to` hoặc `from`, hai selector ở **cùng một peer** được hiểu là **AND**: Pod phải thuộc namespace khớp và có nhãn khớp.

~~~yaml
# AND: Pod app=public-echo thuộc namespace purpose=networkpolicy-external
to:
  - namespaceSelector:
      matchLabels:
        purpose: networkpolicy-external
    podSelector:
      matchLabels:
        app: public-echo
~~~

Nếu đặt chúng thành **hai phần tử** trong danh sách, ý nghĩa là **OR**, có thể vô tình mở rộng rất nhiều:

~~~yaml
# OR: MỌI pod trong namespace đã chọn,
# HOẶC pod app=public-echo trong cùng namespace với policy.
to:
  - namespaceSelector:
      matchLabels:
        purpose: networkpolicy-external
  - podSelector:
      matchLabels:
        app: public-echo
~~~

Hai dạng này khác nhau do **thụt lề và dấu gạch đầu dòng YAML**, dù nhìn rất giống. Luôn soát lại policy sau khi render/apply và thử một client/đích **không được phép** để phát hiện rule quá rộng.

## 12. Ma trận kiểm thử sau khi áp chính sách

Sau khi giữ bốn policy cơ bản (`lab-default-deny-ingress`, `allow-frontend-to-api`, `deny-frontend-egress`, `allow-frontend-egress`) và đã gỡ policy số 5:

| Test ID | Source | Destination | Kỳ vọng | Lý do |
|---|---|---|---|---|
| T01 | frontend | api:80 | **ALLOW** | Source egress và target ingress đều có rule phù hợp |
| T02 | intruder | api:80 | **DENY** | Target API isolated ingress, không có allow từ intruder |
| T03 | frontend | CoreDNS:53 | **ALLOW** nếu DNS labels/path khớp | Frontend có allow DNS cụ thể |
| T04 | frontend | public-echo:80 | **DENY** | Frontend isolated egress và không allow đích này |
| T05 | intruder | public-echo:80 | Thường **ALLOW** | Intruder chưa bị isolate egress; đích không có ingress policy |
| T06 | frontend | api:81 | **DENY** | Không có egress allow TCP/81 và API không allow ingress port 81 |
| T07 | frontend | api:80 sau gỡ allow-frontend-to-api | **DENY** | Default-deny ingress vẫn có hiệu lực |
| T08 | frontend | api:80 sau phục hồi policy allow | **ALLOW** | Đã áp lại allow đúng |
| T09 | guest/other namespace bất kỳ | api:80 | **DENY** trừ policy khác | Không có allow ingress cho nguồn ngoài frontend |

Các kết quả phụ thuộc CNI, source/destination thực, các policy khác và cách chọn Service/Pod. Nên kiểm tra T01–T06 trước khi làm T07–T08 vì việc gỡ allow là một thao tác cố ý gây gián đoạn trong lab.

### 12.1. Đo bằng exit code và thông điệp lỗi

~~~bash
# Không nên chỉ xem chữ "blocked" trong log của app.
# Exit code 0 thường là request thành công.
kubectl -n netpol-lab exec frontend -- \
  wget -q -T 3 -O /dev/null http://api

kubectl -n netpol-lab exec intruder -- \
  wget -q -T 3 -O /dev/null http://api

kubectl -n netpol-lab exec frontend -- nslookup api

# Liệt kê các policy đang áp theo namespace.
kubectl -n netpol-lab get networkpolicy -o wide
~~~

Có thể bổ sung quan sát **Pod IP trực tiếp** khi nghi lỗi DNS, nhưng Pod IP có thể thay đổi khi restart, và đường đi qua Service có thể bị NAT khác với Pod IP trực tiếp. Vì vậy ghi cả Service name và Pod IP lúc thử, không lẫn hai kết quả.

### 12.2. Tại sao cần negative tests?

Chỉ thử `frontend → api` thành công có thể che một policy vô tình mở rộng, chẳng hạn cho phép mọi Pod trong namespace hoặc mọi port. **Negative tests** xác minh những kết nối phải bị chặn: `intruder → api`, `frontend → public-echo`, `frontend → cổng API không được cấp`. Đây là bằng chứng tốt hơn nhiều so với chỉ nhìn vào phần YAML.

## 13. Phân tích semantics và các lỗi dễ gặp

### 13.1. Một NetworkPolicy không “deny” theo thứ tự rule

NetworkPolicy chuẩn có mô hình **allowlist**. Không có quy tắc ưu tiên kiểu firewall truyền thống để policy `default-deny` thắng một policy `allow-all`. Nếu một controller/IaC khác thêm policy cho phép quá rộng, kết nối có thể mở trở lại.

**Hệ quả vận hành:** cần RBAC/admission policy/GitOps để hạn chế ai được tạo policy rộng và giám sát drift, không coi `default-deny` là một rào chắn cuối cùng không thể vượt.

### 13.2. Selector label là điều kiện chọn, không phải danh tính mạnh

Một Pod gắn `app=frontend` chưa chứng minh nó thực sự được phát hành bởi ứng dụng frontend tin cậy. Người có quyền tạo Pod trong cùng namespace có thể tự gắn label. Vì vậy nên có:

- Namespace ownership và quyền `create/patch pod/deployment` chặt chẽ.
- Policy kiểm soát image provenance, service account và admission.
- Tách namespace giữa các nhóm tin cậy, hạn chế quyền thay namespace labels.
- Identity ở tầng ứng dụng (mTLS, token, RBAC) cho dịch vụ nhạy cảm.

NetworkPolicy làm giảm reachability; nó **không thay thế xác thực/ủy quyền API**.

### 13.3. Source/Destination namespace dễ nhầm

- `spec.podSelector` chỉ chọn Pod trong namespace chứa policy.
- `from[].podSelector` hoặc `to[].podSelector` đứng một mình thường chỉ chọn Pod trong **cùng namespace với policy**.
- `namespaceSelector` đứng một mình chọn Pod trong các namespace phù hợp.
- `namespaceSelector` + `podSelector` trong **cùng một phần tử** chọn Pod phù hợp ở namespace được chọn.
- Không thể dùng `Service name` trực tiếp làm đối tượng trong NetworkPolicy chuẩn. Cần chọn Pod/namespace, hoặc IP/CIDR khi thích hợp.

### 13.4. Policy ingress/egress không đồng nghĩa firewall toàn hệ thống

NetworkPolicy chuẩn không phải một bộ lọc packet tùy ý cho host, node management interface, Kubernetes API, service mesh L7, network appliance hoặc mọi đường egress ra Internet. Một số lưu lượng tới/chạy từ node, hostNetwork Pod, Service DNAT, overlay hoặc traffic từ endpoint ngoài cluster có semantics phụ thuộc CNI.

**Không khẳng định** rằng một policy vừa áp sẽ ngăn được truy cập host hoặc mọi external IP. Cần tham khảo CNI, kiểm tra thực tế, kết hợp node firewall, cloud SG/NACL, identity và control plane policies.

### 13.5. ipBlock cần được sử dụng thận trọng

`ipBlock.cidr` phù hợp khi cần diễn tả IP/CIDR được phép, chẳng hạn DNS endpoint ngoài cluster có IP ổn định và có ownership. Không nên mặc định dùng `ipBlock` để chọn Pod IP hoặc Service ClusterIP trong mọi CNI: hành vi trước/sau DNAT/SNAT, biến động IP và implementation có thể khiến policy sai ý định.

Ưu tiên selector Pod/namespace cho workload Kubernetes có nhãn đáng tin, dùng `ipBlock` cho đích IP thích hợp theo khả năng plugin và kết quả test thực tế.

## 14. Kiểm tra khả năng thực thi của CNI và DNS

Nếu `kubectl apply` không báo lỗi nhưng kết quả test trái kỳ vọng, đi theo trình tự thay vì liên tục thêm allow-all.

### 14.1. Quy trình chẩn đoán

~~~mermaid
flowchart TD
    A["Test không đúng kỳ vọng"] --> B{"Pod/Service sẵn sàng?"}
    B -->|"Không"| C["Sửa scheduling, image, endpoint, app readiness"]
    B -->|"Có"| D{"DNS phân giải đúng?"}
    D -->|"Không"| E["Kiểm tra resolv.conf, CoreDNS labels/path, NodeLocal DNS"]
    D -->|"Có"| F{"CNI thực thi NetworkPolicy?"}
    F -->|"Không hoặc chưa rõ"| G["Kiểm tra CNI/plugin & controlled deny test"]
    F -->|"Có"| H["Xem tất cả policy chọn source/destination"]
    H --> I["So selector, namespace, ports, ingress+egress"]
    I --> J["Kiểm tra Pod IP vs Service/NAT, logs/flow"]
    J --> K["Sửa đúng nguyên nhân, test allow+deny lại"]
~~~

### 14.2. Câu hỏi cụ thể

| Triệu chứng | Nguyên nhân có thể | Bước xác minh |
|---|---|---|
| Default deny ingress không chặn | CNI không enforce, selector sai, policy khác allow | Xem CNI, `get netpol -o yaml`, deny test từ đúng Pod |
| frontend bị chặn sau allow ingress | Egress frontend vẫn bị deny, DNS lỗi, API Pod port khác | Kiểm tra hai chiều, DNS, endpoint, nhãn |
| `nslookup api` fail | DNS Pod/namespace label không khớp, NodeLocal DNS, port 53 bị chặn | `resolv.conf`, CoreDNS labels, DNS flow |
| DNS resolve được nhưng HTTP fail | API service/endpoints sai, ingress/egress TCP 80 chặn | Dùng Pod IP trong lab và flow logs |
| intruder vẫn gọi API được | Có allow rộng khác, ingress không được enforce, traffic đi đường khác | List mọi policy, CNI telemetry, Pod labels |
| Egress tới public-echo vẫn thành công | Policy không chọn frontend, allow từ policy khác, CNI không enforce | Get Pod labels, policy union, test new connections |
| Request bị treo rồi mới timeout | Policy drop, firewall drop, route/CNI, app không trả lời | Phối hợp logs, metrics, capture có phạm vi |
| Request bị connection refused | Không có listener, proxy/app chủ động reject hoặc lớp mạng trả RST | Kiểm tra Pod/service readiness, direct Pod IP |
| Pod restart thì kết quả đổi | IP/labels/endpoint thay đổi, policy hội tụ, caching | Kiểm tra Pod UID, labels, IP và policy applied |

### 14.3. Observability hữu ích

Khi CNI hỗ trợ, xem flow records/metrics cho kết quả `FORWARDED`/`DROPPED` và policy verdict; tên lệnh/tính năng tùy Calico, Cilium hoặc nền tảng. Ngoài ra dùng:

~~~bash
kubectl -n netpol-lab get pods -o wide --show-labels
kubectl -n netpol-lab get svc,endpoints
kubectl -n netpol-lab get networkpolicy -o yaml
kubectl -n netpol-lab describe networkpolicy allow-frontend-to-api
kubectl -n netpol-lab logs deployment/api --tail=30
kubectl -n netpol-lab get events --sort-by=.lastTimestamp
~~~

**Hạn chế:** `kubectl describe networkpolicy` mô tả object Kubernetes, không đảm bảo data plane áp thành công. Log ứng dụng không thấy request có thể do DNS, policy, firewall, route hoặc workload lỗi. Cần đối chiếu nhiều nguồn và ghi chính xác thời điểm thay đổi.

## 15. Những điều NetworkPolicy chuẩn không tự giải quyết

NetworkPolicy là một thành phần của phòng vệ nhiều lớp, không thay thế:

- **Authentication/authorization:** ứng dụng cần xác thực người gọi, mTLS, RBAC, token scopes và audit.
- **L7 policy:** endpoint `/admin` và `/health` dùng cùng TCP/80 không được phân biệt bởi chính sách L3/L4 chuẩn.
- **Ingress từ Internet:** còn cloud security groups, LB, WAF, Ingress/Gateway và edge firewall.
- **Encryption in transit:** NetworkPolicy không tự mã hóa traffic; có thể dùng TLS/mTLS và cơ chế thích hợp.
- **Host security:** hostNetwork, kubelet, node firewall, runtime hardening và control plane API cần chính sách riêng.
- **DNS security:** cho phép TCP/UDP 53 chưa kiểm soát DNS tunneling, nội dung query, DoH/DoT hoặc resolver trust.
- **IDS/IPS/NDR:** chặn kết nối có lợi nhưng cần log, detection, alert triage và response.
- **Container security:** image scan, admission, runtime sandbox, pod security, secret management và least privilege.
- **Multi-cluster:** policy của một namespace/cluster không tự bảo vệ traffic ở các cluster khác.
- **NetworkPolicy hỗ trợ đặc biệt của CNI:** một số plugin có CRD L7/cluster-wide/deny; **không được coi chúng là API NetworkPolicy chuẩn** nếu chưa xác minh compatibility.

Tư duy “thêm NetworkPolicy là mạng đã an toàn” cũng sai như việc chỉ chặn cổng Internet nhưng bỏ đường lateral movement, API và credential.

## 16. Docker Compose: cách phân đoạn ở mức container khi không dùng Kubernetes

**Docker Compose không tự triển khai tài nguyên Kubernetes NetworkPolicy.** Tuy vậy, có thể giảm kết nối không cần thiết bằng cách dùng **các Docker bridge network riêng**, chỉ kết nối container vào network cần thiết và không publish cổng của service nhạy cảm lên host.

Mẫu `compose.yaml` minh họa:

~~~yaml
services:
  client:
    image: busybox:1.36
    command: ["sh", "-c", "sleep 36000"]
    networks:
      - frontnet

  api:
    image: nginx:stable-alpine
    networks:
      - frontnet
      - backnet
    # Không publish ports ra host nếu không có nhu cầu.

  database-sim:
    image: nginx:stable-alpine
    networks:
      - backnet

networks:
  frontnet: {}
  backnet:
    internal: true
~~~

Ở ví dụ này, `client` và `api` dùng chung `frontnet`; `api` và `database-sim` dùng chung `backnet`. Vì `client` không gắn `backnet`, nó không có đường DNS/bridge trực tiếp mặc định tới `database-sim` qua network đó.

Tuy nhiên, đây **không tương đương với bộ NetworkPolicy allowlist ingress/egress đầy đủ**:

- Container `api` gắn hai mạng có thể kết nối các dịch vụ ở cả hai; ứng dụng có thể làm proxy tới database-sim.
- `internal: true` trên backnet giới hạn kết nối external của **network đó**, nhưng một container đa-homed vẫn có thể có lối đi khác qua frontnet.
- Host networking, port publishing, Docker daemon access, routing/firewall của host và mạng overlay tạo khả năng truy cập khác.
- Không có mặc định logic điều khiển Pod label/namespace và additive union giống NetworkPolicy.
- Cần firewall host/nftables, chính sách orchestrator/SDN hoặc cơ chế phù hợp khi yêu cầu chặn L3/L4 chi tiết, áp dụng với thẩm quyền và kiểm thử rollback.

Một kiểm tra minh họa sau khi khởi chạy bằng `docker compose up -d`:

~~~bash
# client có thể gọi API trong cùng frontnet.
docker compose exec client wget -q -O /dev/null http://api

# client không có kết nối trực tiếp qua backnet tới database-sim.
# Lỗi có thể là không phân giải tên vì hai service không chung network.
docker compose exec client wget -q -T 3 -O /dev/null http://database-sim

# Gỡ môi trường lab Compose sau thử nghiệm.
docker compose down
~~~

Phải kiểm tra bằng cả network inspection và kết nối thật, không coi việc không phân giải tên là bằng chứng traffic chắc chắn bị firewall drop. Trong production, container/network còn phải có owner, image security, secret isolation, logging và quản trị quyền Docker daemon.

## 17. Áp dụng mô hình lab vào môi trường production

### 17.1. Quy trình rollout được khuyến nghị

1. **Inventory:** xác định các namespace, service owners, Deployments, labels, ports, các luồng tới DNS/API/DB/monitoring/identity, Pod→node và external dependencies.
2. **Đo baseline:** netflow/eBPF telemetry/app logs, Service endpoints và nguồn/đích thực; phân loại traffic hợp lệ và không hợp lệ.
3. **Thiết kế allowlist:** từ hành vi cần thiết, không copy mọi kết nối quan sát được vì có thể chứa traffic độc hại hoặc dư thừa.
4. **Chọn phạm vi nhỏ:** thử trên lab, namespace staging hoặc một nhóm Pod được quản lý; tính đến rollout và CNI enforcement.
5. **Bổ sung allow trước khi deny nếu có thể:** thử cả đường hợp lệ và không hợp lệ, đặc biệt DNS, metrics, sidecars, health probes và external API.
6. **Áp isolation có kiểm soát:** default-deny theo nhóm/namespace chỉ sau khi xác minh dependencies và có rollback.
7. **Theo dõi:** kết nối ứng dụng, DNS errors, retry storms, client latency, packet drop, CNI verdict và SIEM/IDS.
8. **Mở rộng theo đợt:** canary/waves theo app, namespace, team, failure domain; lưu applied policy version và rollback plan.
9. **Governance:** bảo vệ quyền sửa policy/labels, code review độc lập, policy-as-code, admission guardrail và drift monitoring.
10. **Vận hành liên tục:** cập nhật allowlist khi service thay đổi, kiểm tra ngoại lệ/TTL, kiểm tra coverage của workload mới.

**Tránh áp default-deny trong khi chưa biết flow DNS, metadata service, credential refresh hoặc telemetry.** Một ứng dụng có thể vẫn trả HTTP 200 trong vài phút rồi lỗi sau khi token hết hạn vì đường cấp mới bị policy chặn.

### 17.2. GitOps và phê duyệt có kiểm soát

Đưa policy vào repository được kiểm soát; mỗi PR nên ghi:

- Namespace, Pod selector, dependency/port, chủ sở hữu và business justification.
- Negative tests và baseline test đã chạy ở staging.
- Những rule mở rộng như `0.0.0.0/0`, `namespaceSelector: {}` hoặc `podSelector: {}` cần review đặc biệt.
- Version/hash của artifact được duyệt và deployment result.
- Thời hạn ngoại lệ, rollback reference và xác nhận của service owner.

Người tạo thay đổi không nên tự phê duyệt policy rủi ro của mình. Ngoài GitOps, vẫn cần theo dõi sửa đổi **trực tiếp qua kubectl hoặc cloud console** nếu quyền chưa được hạn chế.

## 18. Case study: ngăn truy cập ngang tới API nội bộ

### 18.1. Bối cảnh giả định

Một nhóm vận hành ứng dụng có namespace `payments` với frontend, API và các job xử lý. Một job container bị lỗi cấu hình, liên tục cố kết nối các dịch vụ khác trong namespace. Cloud security group chỉ bảo vệ đường vào VPC; không giới hạn đủ traffic Pod-to-Pod trong cùng cluster.

Nhóm quyết định áp NetworkPolicy theo mẫu lab:

- Default-deny ingress cho Pod API/những Pod nhạy cảm.
- Allow traffic frontend→API trên đúng cổng.
- Đối với frontend, egress chỉ tới API, DNS và dependency được chấp thuận.
- Mở policy riêng cho monitoring/probes theo đúng đường nguồn thực tế.
- Giám sát drift/policy verdict và thử từ Pod không thuộc frontend.

### 18.2. Vì sao không nên áp nguyên xi ví dụ lab lên production?

- Nhãn `app=frontend` có thể không phản ánh identity thật nếu workload khác được phép tự gán.
- API có thể cần ingress từ load balancer/mesh gateway, monitoring hoặc background workers.
- Frontend có thể cần egress tới IdP, secrets service, database proxy hoặc upstream API.
- Policy tới CoreDNS có thể khác nếu dùng NodeLocal DNS hoặc CNI khác.
- Việc rollout, health probes, phiên đang chạy và service NAT có thể gây sai khác.
- Namespace production có thể có policy khác với semantics additive, bao gồm các CRD bổ sung của CNI.

### 18.3. Tiêu chí kiểm chứng

| Yêu cầu | Phép thử |
|---|---|
| Frontend tới API | Request hợp lệ thành công trong SLO |
| Job/intruder tới API | Request bị từ chối theo policy tại data plane |
| DNS/API dependencies | Resolution và các flow quan trọng hoạt động ổn định |
| Không lộ cross-namespace ngoài kế hoạch | Negative tests từ Pod khác namespace |
| Logging đầy đủ | CNI flow verdict và app metrics tương quan thời gian UTC |
| Không vượt policy bằng label spoofing | RBAC/admission kiểm soát label/Pod creation |
| Rollback an toàn | Có cách khôi phục service không mở tất cả kết nối |
| Không ảnh hưởng các dịch vụ khác | Mức lỗi/latency/cảnh báo đáp ứng ngưỡng trước/sau |

Thành công không chỉ là “một yêu cầu bị timeout”, mà là **chặn đúng đường không cần thiết trong khi giữ lại các đường hợp lệ và có bằng chứng vận hành**.

## 19. Cleanup và rollback lab

Sau khi hoàn tất, phải dọn đúng tài nguyên đã tạo **trong namespace lab thuộc quyền mình**. Cách nhanh nhất khi hai namespace được tạo mới **chỉ dành cho bài này**:

~~~bash
kubectl delete namespace netpol-lab
kubectl delete namespace netpol-external
~~~

**Cảnh báo:** xóa namespace sẽ xóa **mọi tài nguyên namespaced** bên trong, không chỉ Pod/Policy của bài. Chỉ chạy nếu xác nhận hai namespace được tạo dành riêng cho lab và không có dữ liệu/tài nguyên của người khác.

Nếu namespace được chia sẻ, thay vào đó xóa theo **đúng resource name** sau khi xem lại:

~~~bash
# Chỉ xóa tài nguyên do lab tạo ra trong namespace netpol-lab.
kubectl -n netpol-lab delete networkpolicy \
  lab-default-deny-ingress \
  allow-frontend-to-api \
  deny-frontend-egress \
  allow-frontend-egress \
  --ignore-not-found

kubectl -n netpol-lab delete pod frontend intruder --ignore-not-found
kubectl -n netpol-lab delete deployment api --ignore-not-found
kubectl -n netpol-lab delete service api --ignore-not-found

# Namespace thứ hai:
kubectl -n netpol-external delete deployment public-echo --ignore-not-found
kubectl -n netpol-external delete service public-echo --ignore-not-found
~~~

Nếu đã thử policy `allow-frontend-external-demo`, bảo đảm đã gỡ nó hoặc thêm vào danh sách cleanup. Trong tình huống production **không gỡ default-deny bừa bãi** để phục hồi vì sẽ mở tất cả kết nối chưa được hạn chế; hãy rollback đúng change đã tạo lỗi theo phê duyệt.

### 19.1. Xác nhận sau cleanup

~~~bash
kubectl -n netpol-lab get all
kubectl -n netpol-lab get networkpolicy
kubectl -n netpol-external get all
~~~

Nếu namespace đã bị xóa, lệnh truy vấn có thể báo `NotFound` — đó là kỳ vọng. Nếu namespace còn, kiểm tra các resource cụ thể đã biến mất; các tài nguyên không thuộc lab không được xóa.

## 20. Checklist nghiệm thu bài lab

### Chuẩn bị

- [ ] Context và cluster được xác nhận là lab; thao tác trong scope cho phép.
- [ ] CNI thực sự enforce Kubernetes NetworkPolicy, không chỉ chấp nhận API.
- [ ] Namespace và Pod label/Service được tạo đúng; không ghi đè tài nguyên có sẵn.
- [ ] Baseline cho frontend→api, intruder→api, frontend→public-echo và DNS đã ghi nhận.

### Thực thi

- [ ] `lab-default-deny-ingress` chọn toàn namespace và chặn ingress chưa có allow.
- [ ] `allow-frontend-to-api` chỉ mở TCP/80 từ app=frontend.
- [ ] Intruder vẫn không gọi được API sau khi thêm allow.
- [ ] Frontend isolated egress và được allow chính xác API + DNS theo cấu hình cluster.
- [ ] Frontend không gọi được `public-echo` khi chưa cấp egress ngoại lệ.
- [ ] Policy cross-namespace dùng namespaceSelector và podSelector ở **cùng một phần tử**.
- [ ] Kết quả thử allow/deny không bị nhầm với lỗi DNS, app readiness hoặc CNI không hỗ trợ.

### Vận hành

- [ ] Đã ghi timestamp UTC, lệnh, image/tag, CNI type, namespace, labels, test outcome.
- [ ] Đã đối chiếu policy object và thực tế traffic/flow logs.
- [ ] Đã hiểu semantics union/additive, hướng ingress/egress và giới hạn L3/L4.
- [ ] Đã nhận diện rủi ro label spoofing/RBAC, NodeLocal DNS, Service NAT, hostNetwork và các policy ngoài phạm vi.
- [ ] Cleanup chỉ xóa tài nguyên lab; không chạm workload người khác.
- [ ] Có mô tả cách chuyển kết quả lab thành thay đổi production an toàn với phê duyệt, canary và rollback.

## 21. Câu hỏi tự kiểm tra

**1. Vì sao tạo NetworkPolicy rồi thấy `kubectl apply` thành công vẫn chưa chứng minh traffic bị chặn?**

Vì Kubernetes API lưu object nhưng **CNI/plugin phải thực thi** ở data plane. Cần controlled test từ Pod được phép/không được phép và kiểm tra policy engine.

**2. `podSelector: {}` trong policy của namespace `netpol-lab` chọn những Pod nào?**

Chọn **tất cả Pod trong namespace đó**, không chọn tất cả Pod toàn cluster.

**3. Có default-deny ingress và một allow ingress từ frontend tới API. Default deny có luôn thắng không?**

Không. NetworkPolicy chuẩn là **cộng gộp các rule cho phép**. API được phép nhận traffic phù hợp với allow policy; các nguồn khác không có allow vẫn bị chặn.

**4. Frontend chỉ có ingress allow tới API, nhưng bản thân frontend có egress deny. Có gọi API được không?**

Chưa chắc. Đường Pod→Pod cần **egress nguồn và ingress đích cùng được phép** nếu các chiều đó bị cô lập. Phải thêm egress allow tới API và có thể tới DNS để dùng Service name.

**5. Vì sao phải allow cả UDP và TCP 53 cho DNS khi phù hợp?**

DNS thường dùng UDP nhưng có thể cần TCP cho một số phản hồi/trường hợp. Phải kiểm tra DNS path và policy thực tế của cluster.

**6. Vì sao policy có `namespaceSelector` và `podSelector` ở hai item riêng có thể nguy hiểm?**

Hai item là **OR**, làm phạm vi cho phép rộng hơn nhiều so với khi đặt hai selector cùng một item (**AND**).

**7. Có thể dùng `metadata.name: api` của Kubernetes Service làm `podSelector` không?**

Không. NetworkPolicy chọn Pod theo labels; Service chỉ là abstraction định tuyến tới Pod, không được chọn trực tiếp bằng Kubernetes NetworkPolicy chuẩn.

**8. Vì sao cần negative tests?**

Vì một request hợp lệ thành công không chứng minh rule không quá rộng. Cần thử intruder→api, frontend→đích không được cấp và cổng không được phép để phát hiện lỗ hổng phân đoạn.

**9. Đặt `app=frontend` có đủ chứng minh nguồn là ứng dụng đáng tin không?**

Không. Nhãn có thể bị gán bởi người có quyền tạo/sửa Pod. Cần RBAC/admission để bảo vệ workload identity và xác thực ở tầng ứng dụng.

**10. Vì sao rule CoreDNS theo Pod selector có thể fail trên một cluster khác?**

Nhãn Pod DNS, namespace, NodeLocal DNSCache, đường NAT và CNI có thể khác. Cần xác minh `resolv.conf`, thực tế DNS endpoints và flow trước khi xây policy.

**11. Docker bridge network có tương đương NetworkPolicy không?**

Không. Nó tạo các miền kết nối/container network khác nhau, nhưng không cung cấp đầy đủ semantics allowlist Pod/namespace/port như Kubernetes NetworkPolicy. Cần xem thêm host firewall, port publishing, multi-homed containers và quyền Docker daemon.

**12. Có nên sửa lỗi production bằng cách xóa default-deny policy không?**

Không mặc định. Xóa default-deny có thể mở hàng loạt luồng không cần thiết. Cần xác định flow bị chặn sai, bổ sung allow hẹp hoặc rollback có kiểm soát theo change đã duyệt.

---

**Ghi nhớ:** Lab **thêm network policy cho container hoặc Kubernetes** minh họa một nguyên tắc kiến trúc mạng quan trọng: **mặc định giới hạn luồng không cần thiết, chỉ cấp phép từng kết nối có mục đích, kiểm tra cả trường hợp được phép và bị cấm, rồi quan sát trạng thái thực tế**. Kubernetes NetworkPolicy là một lớp microsegmentation hữu ích khi CNI thực thi đúng, nhưng phải phối hợp với IAM/RBAC, TLS/mTLS, DNS, cloud firewall, monitoring, GitOps và quy trình vận hành để bảo vệ container hiệu quả.
