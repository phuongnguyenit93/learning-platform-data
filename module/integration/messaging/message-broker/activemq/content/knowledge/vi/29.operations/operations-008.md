# Triển khai một hoặc nhiều broker trên Kubernetes với danh tính và lưu trữ ổn định

> **Chương:** Vận hành  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue, topic, routing và JMS; thực hành producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi:** Triển khai broker stateful trên Kubernetes, giữ nguyên **network identity, broker identity và persistent store** khi Pod bị thay thế hoặc chuyển node. Ví dụ chính dùng image Apache ActiveMQ Artemis **2.40.0**, StatefulSet, headless Service và PersistentVolumeClaim; cuối bài đối chiếu ActiveMQ Classic.

## 1. Broker là workload có trạng thái

Broker giữ nhiều dữ liệu mà không thể xem như cache của một Pod:

- Message persistent chưa được consumer ACK.
- Queue references, durable topic subscriptions và backlog.
- Journal, paging và large-message files.
- Transaction/acknowledgment state và dữ liệu phục hồi.
- Cấu hình broker, security users/roles và thông tin nhận diện node.

Nếu chạy broker bằng `Deployment` với `emptyDir`, Pod bị thay thế có thể tạo instance mới không có journal cũ. Nếu mount cùng một volume cho nhiều broker active, hai process có thể cùng ghi vào một store và làm hỏng dữ liệu. Nếu tạo nhiều replica mà không cấu hình cluster/HA, Kubernetes chỉ tạo nhiều process broker độc lập; nó không tự đồng bộ queue.

StatefulSet cung cấp ordinal ổn định, hostname ổn định và PVC riêng gắn với ordinal. Ví dụ `artemis-0` khi bị reschedule có thể gắn lại claim `data-artemis-0` nếu storage provisioner và topology cho phép. Đây là nền tảng phù hợp cho broker stateful, nhưng **StatefulSet không tự cấu hình replication, cluster hoặc failover của ActiveMQ**.

~~~mermaid
flowchart TD
    S["StatefulSet: artemis"] --> P0["Pod artemis-0"]
    S --> P1["Pod artemis-1"]
    P0 --> V0["PVC data-artemis-0"]
    P1 --> V1["PVC data-artemis-1"]
    H["Headless Service: artemis-headless"] --> P0
    H --> P1
    C["Client Service / broker-aware client"] --> P0
    C --> P1
~~~

**Các lớp identity cần phân biệt:**

| Lớp | Ví dụ | Cơ chế giữ ổn định |
|---|---|---|
| Kubernetes Pod | `artemis-0` | StatefulSet ordinal |
| Network | `artemis-0.artemis-headless.messaging.svc.cluster.local` | Headless Service + DNS |
| Storage | `data-artemis-0` | PVC template + PV |
| Broker | Artemis node ID hoặc Classic `brokerName` | Broker config và persisted instance data |

Pod name ổn định không có nghĩa broker node ID được tạo lại tùy ý. Với Artemis, thông tin node/instance có thể nằm trong instance data. Không clone nguyên PVC của broker A để tạo broker B độc lập rồi cho cả hai cùng chạy: identity và journal có thể bị trùng.

## 2. Chọn mô hình trước khi viết YAML

### 2.1. Một broker độc lập

Một StatefulSet `replicas: 1`, một PVC và một Service phù hợp cho lab hoặc workload chấp nhận downtime khi broker restart. Pod có tên ổn định; volume chứa broker instance được mount lại sau khi Pod thay thế. Client kết nối qua Service ổn định. Đây **không phải HA**: khi Pod dừng, producer/consumer vẫn bị gián đoạn.

### 2.2. Nhiều broker độc lập

Nếu cần broker tách biệt theo ứng dụng, tenant hoặc failure domain, tạo **mỗi broker một StatefulSet/PVC/configuration**:

~~~text
namespace messaging
  artemis-orders-0   -> PVC data-artemis-orders-0
  artemis-billing-0  -> PVC data-artemis-billing-0
  artemis-audit-0    -> PVC data-artemis-audit-0
~~~

Các broker này không tự chia sẻ queue. Client chọn đúng endpoint hoặc dùng routing/bridge/federation được cấu hình ở tầng broker.

### 2.3. Cluster hoặc HA pair

- **Artemis cluster** cần cluster connection/discovery/connectors và node identity phù hợp. Mỗi broker active có store riêng; cluster routing không phải replication của mọi message trên mọi node.
- **Artemis HA** cần primary/backup với replication hoặc shared-store theo topology được hỗ trợ. Backup phải được đồng bộ và có activation/fencing đúng.
- **ActiveMQ Classic** có master/slave hoặc Network of Brokers với semantics riêng. Network connector chuyển message theo demand/policy; nó không tự biến hai broker thành một store HA.
- Một Service Kubernetes chọn ngẫu nhiên mọi Pod trong HA pair có thể gửi client tới backup chưa active. Cần client failover hiểu topology hoặc endpoint chỉ chọn broker active bằng readiness/role đã kiểm chứng.

**Không tăng `replicas` từ 1 lên 3 chỉ để có HA.** Trước khi scale, phải có per-node configuration, unique identity, discovery/connectors, persistence và client failover được kiểm thử.

## 3. StatefulSet tạo network identity và volume như thế nào?

Với StatefulSet `artemis`, headless Service `artemis-headless`, namespace `messaging`, Pod đầu tiên có hostname `artemis-0`. DNS mặc định:

~~~text
artemis-0.artemis-headless.messaging.svc.cluster.local
~~~

Tên `cluster.local` là cluster domain mặc định; cụm có thể cấu hình domain khác.

`volumeClaimTemplates` tên `data` tạo PVC:

~~~text
data-artemis-0
data-artemis-1
data-artemis-2
~~~

Khi `artemis-0` bị xóa và StatefulSet tạo Pod thay thế, controller dùng lại claim `data-artemis-0` nếu PVC vẫn tồn tại và mount thành công.

### 3.1. Headless Service

StatefulSet tham chiếu `spec.serviceName` tới headless Service đã tồn tại. Service có `clusterIP: None` và quản lý DNS riêng của từng Pod. Nó phục vụ nhận diện peer trong topology, không phải load balancer thông thường cho ứng dụng.

`publishNotReadyAddresses: true` hữu ích khi broker cần resolve peer trước khi Pod đạt readiness, nhưng DNS sẽ công bố cả endpoint chưa Ready. Với client traffic, dùng một Service riêng chỉ nhận Pod đủ điều kiện phục vụ.

### 3.2. PVC retention và access mode

- `ReadWriteOnce`: volume read-write trên một node; nhiều Pod cùng node vẫn có thể truy cập.
- `ReadWriteOncePod`: volume read-write chỉ cho một Pod trên cluster; cần CSI driver/sidecar tương thích.
- `ReadWriteMany`: nhiều node có thể mount read-write nếu backend hỗ trợ. Nó không làm journal broker an toàn khi nhiều broker cùng ghi.

Kubernetes giữ PVC khi Pod bị xóa; PVC do StatefulSet tạo mặc định không bị xóa chỉ vì StatefulSet bị xóa hoặc scale down. Tuy vậy, xóa PVC có thể làm PV bị reclaim theo `persistentVolumeReclaimPolicy`. Phải kiểm tra StorageClass/PV trước khi thao tác.

## 4. Chọn storage cho journal và paging

Broker nhạy với **latency ghi bền vững, fsync, IOPS, throughput và filesystem consistency**. Không chọn storage chỉ dựa trên dung lượng.

| Kiểu lưu trữ | Dùng khi | Điều cần kiểm tra |
|---|---|---|
| Block volume qua CSI | Phương án thường dùng cho journal | IOPS/latency, fsync, detach/attach khi Pod chuyển node |
| SSD-backed StorageClass | Persistent workload cao | Throughput ổn định, quota, burst credits |
| Local PV | Cần latency thấp trên node cụ thể | Node failure, rescheduling và DR phức tạp |
| Network filesystem/RWX | Chỉ khi broker/version/storage hỗ trợ rõ | Locking, cache consistency, shared-store semantics |
| `emptyDir` | Cache hoặc dữ liệu tạm | Không dùng cho journal cần giữ qua Pod replacement |
| `hostPath` | Lab node đơn | Không portable, phụ thuộc node, khó phục hồi |

Với Artemis replication HA, mỗi broker node thường có persistent storage riêng. Shared-store HA là mô hình khác; chỉ dùng shared filesystem khi storage đáp ứng locking/consistency mà broker hỗ trợ. **Không mount một PVC journal read-write cho hai broker active độc lập.**

### 4.1. Ước lượng dung lượng

\[
D_{\text{required}} =
D_{\text{journal}} +
D_{\text{paging}} +
D_{\text{large-message}} +
D_{\text{metadata}} +
D_{\text{headroom}}.
\]

Backlog trong thời gian downstream gián đoạn có thể ước lượng:

\[
D_{\text{backlog}} \approx
\lambda \times T_{\text{outage}} \times \bar{s},
\]

trong đó \(\lambda\) là message/giây, \(T_{\text{outage}}\) là giây và \(\bar{s}\) là byte/message. Đây mới là payload gần đúng; journal records, queue references, paging, replication và biên an toàn làm dung lượng thực lớn hơn.

Theo dõi disk free, page bytes, journal growth, oldest message age và dự báo thời gian đến watermark. Broker hết disk có thể từ chối producer hoặc mất khả năng vận hành tùy policy.

## 5. Chuẩn bị namespace, Secret và image

Ví dụ dùng image chính thức `apache/activemq-artemis:2.40.0`. Với release này, container sử dụng các biến `ARTEMIS_USER`, `ARTEMIS_PASSWORD`, `ANONYMOUS_LOGIN` và thư mục instance `/var/lib/artemis-instance`. Đây là ví dụ version-pinned; production nên pin **digest** đã quét và kiểm tra chữ ký/provenance, không dùng tag `latest`.

### 5.1. Namespace

~~~bash
kubectl create namespace messaging
~~~

### 5.2. Bootstrap administrator Secret

Tạo Secret qua secret manager/External Secrets hoặc pipeline bảo mật. Manifest sau chỉ minh họa cấu trúc; không commit password thật vào Git.

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: artemis-bootstrap-admin
  namespace: messaging
type: Opaque
stringData:
  ARTEMIS_USER: broker-admin
  ARTEMIS_PASSWORD: REPLACE_FROM_SECRET_MANAGER
~~~

Tài khoản này phục vụ bootstrap/admin, **không phải credential để mọi ứng dụng kết nối**. Tạo user/role riêng cho producer, consumer và operator, cấp quyền tối thiểu trên address/queue cần thiết.

**Secret rotation:** image dùng environment variables để tạo broker instance lần đầu. Khi PVC đã có instance/configuration, thay `ARTEMIS_PASSWORD` trong Secret không nhất thiết tự sửa password đã lưu trong broker security store. Rotation phải cập nhật identity trong broker theo quy trình hỗ trợ, đồng bộ Secret mới và restart/reconnect client có kiểm soát.

### 5.3. Credential ứng dụng

Ứng dụng Java dùng Secret riêng, ví dụ `orders-jms-client` chứa `JMS_USERNAME` và `JMS_PASSWORD`. Không truyền bootstrap administrator Secret sang Pod ứng dụng. Broker admin, application identity và cluster/bridge identity là các vai trò khác nhau.

## 6. Manifest Artemis: Headless Service, client Service và StatefulSet

Manifest triển khai **một broker độc lập** trong namespace `messaging`. Điều chỉnh StorageClass, dung lượng, resource limits, image digest, Secret và NetworkPolicy theo cluster thực tế.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: artemis-headless
  namespace: messaging
  labels:
    app.kubernetes.io/name: artemis
spec:
  clusterIP: None
  publishNotReadyAddresses: true
  selector:
    app.kubernetes.io/name: artemis
  ports:
    - name: core
      port: 61616
      targetPort: core
      protocol: TCP
---
apiVersion: v1
kind: Service
metadata:
  name: artemis-client
  namespace: messaging
  labels:
    app.kubernetes.io/name: artemis
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: artemis
  ports:
    - name: core
      port: 61616
      targetPort: core
      protocol: TCP
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: artemis
  namespace: messaging
spec:
  serviceName: artemis-headless
  replicas: 1
  podManagementPolicy: OrderedReady
  updateStrategy:
    type: OnDelete
  selector:
    matchLabels:
      app.kubernetes.io/name: artemis
  template:
    metadata:
      labels:
        app.kubernetes.io/name: artemis
    spec:
      terminationGracePeriodSeconds: 180
      securityContext:
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: broker
          image: apache/activemq-artemis:2.40.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: core
              containerPort: 61616
              protocol: TCP
            - name: console
              containerPort: 8161
              protocol: TCP
          env:
            - name: ARTEMIS_USER
              valueFrom:
                secretKeyRef:
                  name: artemis-bootstrap-admin
                  key: ARTEMIS_USER
            - name: ARTEMIS_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: artemis-bootstrap-admin
                  key: ARTEMIS_PASSWORD
            - name: ANONYMOUS_LOGIN
              value: "false"
          volumeMounts:
            - name: data
              mountPath: /var/lib/artemis-instance
          resources:
            requests:
              cpu: "1"
              memory: 2Gi
            limits:
              cpu: "2"
              memory: 4Gi
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
          startupProbe:
            tcpSocket:
              port: core
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 30
          readinessProbe:
            tcpSocket:
              port: core
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes:
          - ReadWriteOnce
        storageClassName: fast-rwo
        resources:
          requests:
            storage: 100Gi
~~~

### 6.1. Hai Service có nhiệm vụ khác nhau

- `artemis-headless` là governing service cho StatefulSet, cung cấp DNS riêng của Pod.
- `artemis-client` là ClusterIP cho ứng dụng. Vì manifest chỉ có một replica, Service trỏ tới đúng broker đó.
- Port 8161 được khai báo trong container để quản trị nội bộ, nhưng không expose qua `artemis-client`. Nếu cần console, tạo Service/Ingress riêng có authentication, TLS và network restriction.

Với cluster domain mặc định, endpoint client:

~~~text
artemis-client.messaging.svc.cluster.local:61616
~~~

DNS riêng của broker:

~~~text
artemis-0.artemis-headless.messaging.svc.cluster.local:61616
~~~

### 6.2. Vì sao mount toàn bộ instance directory?

Với image 2.40.0, `/var/lib/artemis-instance` chứa configuration và data của instance. Mount PVC vào đây giúp cấu hình, identity và store tiếp tục tồn tại khi container bị thay thế. Nếu chỉ mount một thư mục con mà broker lưu journal hoặc config ở nơi khác, dữ liệu vẫn có thể mất.

**Không áp dụng đường dẫn này cho mọi tag Artemis.** Image mới có thể thay layout filesystem; đối chiếu tài liệu đúng image digest. Không dùng image version mới với volume path cũ chỉ vì manifest trước đó chạy được.

### 6.3. Probe có giới hạn gì?

`startupProbe` cho broker thời gian khởi động và recover journal; ví dụ cho tối đa khoảng 300 giây. `readinessProbe` TCP chỉ xác nhận cổng Core đang accept TCP. Nó **không chứng minh** user authenticate được, queue đã provision, cluster/backup khỏe hoặc consumer xử lý message được.

Production có thể bổ sung broker-aware health check đã được xác minh theo release hoặc synthetic JMS probe bên ngoài. Không đặt liveness probe TCP quá nhạy: khi broker đang paging/recover dưới tải, restart liên tục có thể kéo dài recovery. Nếu tiến trình broker tự exit, Kubernetes đã restart container theo restart policy; chỉ thêm liveness khi có tín hiệu đáng tin để phát hiện deadlock không tự thoát.

### 6.4. JVM và container memory

Memory limit không phải toàn bộ heap Java. Broker còn cần direct memory, thread stacks, metaspace, native allocations và page cache. Đặt heap qua cơ chế image/version hỗ trợ, giữ headroom dưới container limit và benchmark với paging/large messages. Không copy một giá trị `-Xmx` cố định cho mọi tải.

## 7. StorageClass, access mode và dữ liệu sau Pod replacement

### 7.1. Kiểm tra PVC

Với StatefulSet `artemis` và claim template `data`, PVC của Pod ordinal 0 là `data-artemis-0`:

~~~bash
kubectl get statefulset artemis -n messaging
kubectl get pods -n messaging -o wide
kubectl get pvc data-artemis-0 -n messaging
kubectl describe pvc data-artemis-0 -n messaging
kubectl get pv
~~~

PVC `Pending` thường cho thấy StorageClass không tồn tại, provisioner không hoạt động, capacity/access mode không phù hợp hoặc topology không thể bind.

### 7.2. Chọn access mode

- `ReadWriteOnce`: read-write mount trên một node; nhiều Pod cùng node vẫn có thể truy cập.
- `ReadWriteOncePod`: read-write mount chỉ cho một Pod trên cluster; cần CSI driver/sidecar tương thích.
- `ReadWriteMany`: nhiều node có thể mount read-write nếu backend hỗ trợ. Điều đó không làm journal broker an toàn khi nhiều broker cùng ghi.

Với một broker process/claim, `ReadWriteOncePod` chặt hơn nếu CSI hỗ trợ. Manifest dùng `ReadWriteOnce` để tương thích rộng hơn; đổi sau khi xác minh storage driver.

### 7.3. PVC retention và xóa dữ liệu

StatefulSet giữ PVC khi Pod bị xóa; PVC do `volumeClaimTemplates` tạo mặc định không bị xóa chỉ vì StatefulSet bị xóa hoặc scale down. Nhưng nếu operator xóa PVC, PV có thể được reclaim theo policy `Delete` hoặc `Retain`.

1. Trước khi xóa StatefulSet, xác nhận PVC/PV và reclaim policy.
2. Backup broker store theo phương pháp nhất quán được hỗ trợ.
3. Xác minh restore trong môi trường riêng.
4. Chỉ xóa PVC khi có phê duyệt data-retirement và đã đối soát message/backlog.
5. Không dùng `kubectl delete pvc` để sửa Pod Pending hoặc lỗi mount.

### 7.4. Snapshot journal

Snapshot volume có thể là crash-consistent hoặc application-consistent tùy CSI/backend. Nếu broker đang ghi journal, snapshot không phối hợp với broker có thể không tương đương backup hợp lệ. Dùng broker-aware backup/quiesce hoặc quy trình snapshot được vendor/storage xác nhận; định kỳ restore test và đo RPO/RTO.

## 8. Graceful shutdown, rolling update và node drain

### 8.1. Pod termination

Khi Pod bị xóa hoặc node drain, kubelet gửi SIGTERM rồi chờ `terminationGracePeriodSeconds`. Ví dụ đặt 180 giây để broker có thời gian shutdown và đóng store. Giá trị thực dựa trên journal size và shutdown behavior của image.

Không đặt grace period quá ngắn rồi thường xuyên buộc container kill. Shutdown không sạch làm lần khởi động sau recover journal lâu hơn và có thể tăng redelivery.

### 8.2. `OnDelete` để nâng version có kiểm soát

Manifest dùng:

~~~yaml
updateStrategy:
  type: OnDelete
~~~

Khi cập nhật image/config template, StatefulSet không tự thay Pod đang chạy. Operator thực hiện:

1. Backup/kiểm tra restore và đọc release notes.
2. Cập nhật image digest/config revision.
3. Xác nhận Pod khỏe và queue backlog trong ngưỡng.
4. Xóa một Pod theo lịch bảo trì; StatefulSet tạo lại Pod cùng ordinal/PVC.
5. Chờ broker recover, readiness và messaging smoke test PASS.
6. Chỉ tiếp tục node tiếp theo nếu topology/HA cho phép.

Với một broker duy nhất, bước thay Pod tạo downtime; `OnDelete` không tạo HA. Với HA pair, cập nhật từng node theo thứ tự được hỗ trợ, giữ đủ backup state và không restart cả hai cùng lúc.

### 8.3. PodDisruptionBudget

PDB giới hạn voluntary disruption như eviction khi drain node; nó không ngăn node crash hoặc lỗi storage. Ví dụ cho cụm có **hai broker replica thực sự sẵn sàng phục vụ theo thiết kế**:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: artemis-pdb
  namespace: messaging
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: artemis
~~~

Không áp dụng PDB `minAvailable: 1` cho StatefulSet một Pod nếu cần drain node: eviction có thể bị chặn vì không thể giảm số Ready Pod xuống dưới một. Với primary/backup, PDB selector và readiness phải phản ánh trạng thái thực; nếu backup không được xem Ready, PDB có thể không cho drain như mong đợi.

### 8.4. Placement cho HA

Đặt primary và backup trên node/zone khác nhau bằng pod anti-affinity hoặc topology spread constraints. Nếu hai Pod cùng node/zone, một sự cố node/zone có thể làm mất cả hai. Spread rule phải phù hợp số node khả dụng; `requiredDuringScheduling` có thể khiến Pod Pending nếu cluster không đủ topology domains.

## 9. Triển khai nhiều broker: tránh load balancing ngẫu nhiên

| Mô hình | Kubernetes layout | Điều kiện broker |
|---|---|---|
| Nhiều broker độc lập | Mỗi broker một StatefulSet 1 replica, PVC/Service riêng | Config và identity riêng; app chọn broker theo domain |
| Artemis cluster | StatefulSet/Operator nhiều Pod với headless DNS | Cluster connection/discovery, connector URI, unique node identity, cluster credentials |
| Artemis HA primary/backup | Primary/backup workload và PVC theo HA design | Replication/shared store, activation/fencing, backup topology và client HA |

### 9.1. Nhiều StatefulSet độc lập

Ví dụ đặt tên:

~~~text
artemis-orders
artemis-billing
artemis-audit
~~~

Mỗi StatefulSet có `replicas: 1`, headless Service riêng, PVC riêng, broker config riêng và client Service riêng. Nếu cần bridge giữa chúng, cấu hình bridge/federation ở broker theo đúng routing/security design.

### 9.2. Artemis cluster

Mỗi Pod cần peer discovery/connectors có thể resolve qua stable DNS. Không mặc định UDP multicast/JGroups multicast hoạt động trong mọi CNI/cloud network.

Cấu hình cluster phải giải quyết:

- Mỗi broker có identity/node ID riêng và persist đúng qua restart.
- Connector tới peer dùng DNS/port truy cập được từ mọi Pod.
- Cluster user/password và security permissions được quản lý riêng.
- Address/queue routing type, redistribution và message load được hiểu đúng.
- Khi node rời cluster, client/consumer và message ownership phục hồi theo policy.
- Cluster connection không đồng nghĩa mọi message được replicate lên mọi node.

Nếu dùng một StatefulSet `replicas: 3`, Kubernetes tạo ba PVC riêng, nhưng broker config trong cùng Pod template cũng giống nhau. Phải có **per-ordinal configuration** hoặc operator tạo broker identity/connector đúng cho từng Pod. Nếu không, node ID/broker name có thể trùng hoặc broker độc lập bị Service phân phối ngẫu nhiên.

### 9.3. Artemis HA pair

Để có primary/backup, cấu hình HA mode trong broker và storage theo replication hoặc shared store được hỗ trợ. Kubernetes chỉ đảm bảo Pod identity/PVC; nó không tự promote backup, fence primary cũ hay đồng bộ journal.

Không đặt một Service ClusterIP round-robin lên cả primary và backup rồi cho mọi client kết nối qua đó. Dùng broker-aware HA client/topology hoặc Service chỉ chọn active endpoint bằng readiness/role được kiểm chứng.

## 10. Network, TLS và security boundary

### 10.1. NetworkPolicy

Service `ClusterIP` chỉ giới hạn exposure ở cấp Service; Pod vẫn có thể nhận traffic nội bộ theo NetworkPolicy/CNI. Mẫu sau cho phép Pod `orders-api` trong namespace `orders` kết nối Artemis port 61616:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-orders-to-artemis
  namespace: messaging
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: artemis
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: orders
          podSelector:
            matchLabels:
              app.kubernetes.io/name: orders-api
      ports:
        - protocol: TCP
          port: 61616
~~~

NetworkPolicy có tính additive. Muốn default-deny ingress, cần policy deny mặc định phù hợp namespace và CNI hỗ trợ NetworkPolicy. Kiểm tra label namespace thật trước khi triển khai.

### 10.2. TLS và management port

- Broker acceptor production dùng TLS với certificate/SAN đúng hostname client sử dụng.
- Nếu client kết nối qua Service DNS, certificate cần phù hợp tên Service hoặc client phải kết nối endpoint được certificate bao phủ.
- Port 8161 (console/management HTTP) chỉ mở cho admin network/gateway được kiểm soát; không thêm vào Service ứng dụng.
- Quản lý certificate bằng Secret/CSI/secret operator; rotation bao gồm trust chain, broker reload/restart và client reconnect.
- NetworkPolicy cần cho phép traffic cluster/HA/replication giữa broker peers ngoài port client, theo đúng topology.

### 10.3. Security context và filesystem permissions

Image Artemis 2.40.0 chạy bằng user không root `artemis`; PVC mount phải cho user đó quyền ghi. Nếu đặt `runAsUser`, `runAsGroup` hoặc `fsGroup`, xác minh UID/GID thật của image digest đang pin và hành vi CSI driver. Không sửa permission bằng `chmod -R 777` hoặc chạy broker root để né lỗi mount.

## 11. ActiveMQ Classic trên Kubernetes

Classic cũng là workload stateful và dùng StatefulSet/PVC/headless Service theo nguyên lý Kubernetes, nhưng container, protocol, cấu hình và storage path khác Artemis.

- Image Classic chính thức dùng repository `apache/activemq`; pin release tag/digest, không dùng `latest`.
- Port 61616 thường là OpenWire connector; 8161 là web console trong image phổ biến.
- Persistent data nằm ở đường dẫn broker resolve từ property `activemq.data`/`dataDirectory` trong `activemq.xml`. Kiểm tra image và cấu hình thật; **không mount đường dẫn `/var/lib/artemis-instance` của Artemis vào Classic**.
- Mỗi Classic broker độc lập có `brokerName` riêng, connector và KahaDB path riêng.
- Master/slave/shared storage hoặc Network of Brokers cần cấu hình storage/locking/network connector theo tài liệu Classic; StatefulSet không tự cung cấp semantics đó.
- Durable topic subscriptions và message store cần được giữ trên PVC đúng broker.

Mảnh cấu hình Classic minh họa, cần hợp nhất vào `activemq.xml` hiện hữu:

~~~xml
<broker brokerName="orders-classic-0"
        dataDirectory="ACTIVEMQ_DATA_DIR"
        persistent="true">
    <!-- persistenceAdapter, transportConnectors,
         plugins và destinationPolicy theo cấu hình broker -->
</broker>
~~~

`ACTIVEMQ_DATA_DIR` là placeholder cần thay bằng đường dẫn thực tế mà image mount trên PVC. Không để hai broker độc lập dùng chung KahaDB directory. Nếu dùng HA shared store, chỉ làm theo mô hình file locking/shared filesystem được Classic hỗ trợ; một PVC `ReadWriteMany` bất kỳ không tự trở thành shared store an toàn.

## 12. Triển khai và xác minh trên cluster

### 12.1. Apply tài nguyên

Lưu manifest thành `artemis-statefulset.yaml`, Secret được cấp riêng từ secret manager, rồi chạy:

~~~bash
kubectl apply -f artemis-statefulset.yaml
kubectl rollout status statefulset/artemis -n messaging --timeout=10m
~~~

Kiểm tra:

~~~bash
kubectl get statefulset,pods,services,pvc -n messaging
kubectl describe pod artemis-0 -n messaging
kubectl describe pvc data-artemis-0 -n messaging
kubectl get endpointslices -n messaging
kubectl logs artemis-0 -n messaging
~~~

Nếu Pod Pending, xem Events, PVC binding, StorageClass, node affinity và resource requests. Nếu Pod CrashLoopBackOff, kiểm tra log khởi động, Secret keys, volume permissions và cấu hình broker.

### 12.2. Xác minh identity

~~~bash
kubectl get pod artemis-0 -n messaging -o wide
kubectl exec artemis-0 -n messaging -- hostname
kubectl get pvc data-artemis-0 -n messaging -o wide
kubectl get service artemis-headless artemis-client -n messaging
~~~

Xác nhận hostname Pod là `artemis-0`, PVC `data-artemis-0` ở trạng thái Bound, DNS headless resolve đúng Pod IP, Client Service có endpoint Ready và broker startup log load đúng persistent path.

### 12.3. Test Pod replacement nhưng giữ storage

Trong môi trường test, ghi persistent event với event ID, xác nhận queue depth, sau đó xóa **Pod**:

~~~bash
kubectl delete pod artemis-0 -n messaging
kubectl rollout status statefulset/artemis -n messaging --timeout=10m
kubectl get pod artemis-0 -n messaging -o wide
kubectl get pvc data-artemis-0 -n messaging
~~~

StatefulSet tạo Pod `artemis-0` mới và mount lại PVC `data-artemis-0`. Kết nối client, consume event và đối chiếu event ID. Đây là test Pod replacement/storage reattachment, **không phải** HA failover giữa hai broker.

### 12.4. Kiểm tra sau restart

Kiểm tra broker load đúng config/node identity, journal recovery hoàn tất, queue/address và durable subscription còn, message chưa ACK redeliver đúng, consumer reconnect và disk/page/journal ổn định. Không chỉ dựa vào Pod `Ready`; probe TCP có thể thành công khi business destination/authorization vẫn sai.

## 13. Scale, upgrade và khôi phục dữ liệu

### 13.1. Scale StatefulSet

~~~bash
kubectl scale statefulset artemis -n messaging --replicas=2
~~~

Lệnh tạo `artemis-1` và PVC `data-artemis-1`. Nó **không** tự cấu hình cluster connection, tạo unique broker config, chuyển message, replicate journal/durable subscription hay tạo HA backup. Chỉ scale sau khi per-pod identity/config, discovery, storage và routing policy đã được test.

Nếu chỉ muốn tăng throughput consumer, có thể scale consumer application độc lập; không phải lúc nào cũng cần scale broker.

### 13.2. Upgrade image

Với `OnDelete`, sau khi thay image digest, cần chủ động restart từng Pod theo kế hoạch:

1. Đọc release notes và compatibility.
2. Backup/restore rehearsal.
3. Xác nhận PVC và storage health.
4. Drain/giảm producer traffic nếu cần maintenance.
5. Upgrade một node theo thứ tự HA được hỗ trợ.
6. Chạy smoke tests JMS, persistence, subscription, redelivery và failover.
7. Theo dõi disk, GC, journal recovery và queue age.

Không rollback binary mù quáng nếu version mới đã thay đổi store/config format. Restore từ backup nhất quán có thể an toàn hơn, nhưng phải tính RPO và message phát sinh sau backup.

### 13.3. Restore PVC hoặc snapshot

Khi restore, gắn snapshot/clone vào một Pod broker duy nhất trong môi trường cô lập. Xác minh node identity, broker config, queue counts, message IDs và subscription state trước khi cho phép client production kết nối.

Không chạy đồng thời broker gốc và broker clone từ cùng snapshot có cùng identity trên cùng mạng/cluster. Điều này có thể gây duplicate node identity, connector confusion, split-brain hoặc duplicate message delivery.

## 14. Những anti-pattern cần tránh

- **Deployment + emptyDir:** mất journal/store khi Pod bị thay thế.
- **Một PVC cho nhiều broker active:** có nguy cơ ghi đè/corrupt journal.
- **StatefulSet replicas tăng mà không cluster config:** tạo broker độc lập, không có message replication.
- **ClusterIP round-robin primary và backup:** client có thể bị gửi tới node không active.
- **Dùng cùng broker identity/config cho nhiều broker:** trùng node identity/connector hoặc security state.
- **Clone PVC để tạo broker mới:** sao chép persisted identity và store.
- **Dùng hostPath cho production:** dữ liệu gắn với node, khó reschedule và DR.
- **Xóa PVC để sửa Pending/CrashLoop:** có thể xóa message và subscription state.
- **Dùng liveness TCP quá nhạy:** restart loop khi broker đang recover/paging.
- **Expose 8161 ra Internet:** mở rộng bề mặt quản trị.
- **Đổi Secret nhưng nghĩ password trong broker tự đổi:** environment bootstrap không nhất thiết sửa instance đã tồn tại.
- **Snapshot journal khi đang ghi mà không có quy trình hỗ trợ:** backup có thể không nhất quán.
- **PDB một Pod với `minAvailable: 1`:** có thể chặn voluntary eviction và drain node.
- **Scale down StatefulSet tùy tiện:** PVC có thể còn nhưng Pod/cluster topology và service availability thay đổi.
- **Dùng chung storage Artemis và Classic:** khác store layout, broker process và locking semantics.

## 15. Ma trận nghiệm thu vận hành

| ID | Kịch bản | Bằng chứng PASS |
|---|---|---|
| K8S-01 | Pod được tạo từ StatefulSet | Pod ordinal/hostname ổn định |
| K8S-02 | DNS headless | FQDN trỏ đúng Pod IP |
| K8S-03 | PVC binding | Claim đúng ordinal Bound với StorageClass |
| K8S-04 | Xóa Pod rồi tạo lại | Cùng PVC được mount, message IDs còn |
| K8S-05 | Restart broker | Journal recovery, queue/subscription state đúng |
| K8S-06 | Storage unavailable | Pod không nhận traffic; có alert và runbook |
| K8S-07 | Disk gần đầy | Alert watermark/backpressure hoạt động |
| K8S-08 | Node drain | Graceful shutdown, PDB/maintenance policy đúng |
| K8S-09 | Upgrade image | Runtime version/digest mới, JMS regression PASS |
| K8S-10 | Restore snapshot | Store và identity được xác minh trong môi trường cách ly |
| HA-01 | Primary failover | Backup activation và client reconnect theo topology |
| HA-02 | Backup không reachable | Alert/RTO failure được ghi, không báo HA PASS giả |
| SEC-01 | App user kết nối | Chỉ có quyền cần thiết; admin secret không nằm ở app Pod |
| SEC-02 | NetworkPolicy | Chỉ workload được phép kết nối Core port |
| SEC-03 | Management console | 8161 chỉ accessible từ admin network được kiểm soát |
| MULTI-01 | Thêm broker thứ hai | Unique config/node identity/PVC và routing được xác minh |
| MULTI-02 | Broker Classic | `activemq.data` trên PVC riêng, OpenWire/ACL đúng |
| DATA-01 | Restore sau lỗi | Event ID, DLQ, durable subscription và DB inbox được đối soát |

Một test chỉ thấy Pod `Running` hoặc Service có endpoint chưa chứng minh broker đã phục hồi dữ liệu và xử lý message đúng.

## 16. Runbook khi broker Pod không khởi động hoặc mất dữ liệu

### Pod Pending

1. Kiểm tra `kubectl describe pod` và Events.
2. Kiểm tra PVC `Bound`, StorageClass và CSI provisioner.
3. Kiểm tra node affinity/zone của volume.
4. Xem resource requests, quota và scheduling constraints.
5. Không xóa PVC để “thử lại”.

### CrashLoopBackOff

1. Đọc `kubectl logs --previous`.
2. Kiểm tra Secret name/key và quyền đọc.
3. Kiểm tra volume ownership/UID/GID và filesystem permission.
4. Kiểm tra cấu hình broker và version image/path.
5. Xem broker đang recover journal hay gặp corruption; tránh lặp restart quá nhanh.

### Pod Running nhưng client không kết nối

1. Kiểm tra Service/EndpointSlice và port target.
2. Kiểm tra NetworkPolicy, DNS và TLS/SAN.
3. Kiểm tra acceptor protocol/port.
4. Kiểm tra user/role và credential rotation.
5. Kiểm tra readiness probe chỉ TCP hay đã có broker-aware health.
6. Không expose management console để thay thế việc chẩn đoán Core/OpenWire.

### Pod mới lên nhưng queue/subscription rỗng

1. Xác nhận Pod dùng đúng PVC claim name và volume ID.
2. Kiểm tra mount path đúng image version.
3. Kiểm tra startup log và broker instance path.
4. Xác minh node identity và config revision.
5. Đối chiếu message IDs, queue/address, durable subscription, expiry/DLQ.
6. Dừng traffic nếu nghi Pod đang chạy store rỗng; không tiếp tục ghi lên nhầm instance.
7. Khôi phục từ backup/snapshot đã kiểm chứng và reconciliation theo RPO.

## 17. Checklist trước khi đưa broker lên production

- [ ] Chọn rõ standalone, nhiều broker độc lập, Artemis cluster hay HA pair.
- [ ] Dùng StatefulSet cho broker stateful và headless Service cho Pod identity.
- [ ] Pod ordinal, DNS FQDN, PVC claim và broker node identity được ghi inventory.
- [ ] Mỗi broker có persistent store riêng, trừ shared-store HA được hỗ trợ rõ.
- [ ] StorageClass đáp ứng IOPS/latency/fsync và có capacity/headroom.
- [ ] PVC retention, PV reclaim policy, backup và restore test đã rõ.
- [ ] Image được pin release/digest; đường dẫn instance/data đúng version.
- [ ] Bootstrap admin Secret tách khỏi app user/role credentials.
- [ ] TLS/SAN, NetworkPolicy, security context và management access đã kiểm soát.
- [ ] Startup/readiness probe phản ánh mức health phù hợp; không dùng TCP liveness quá nhạy.
- [ ] Graceful termination đủ thời gian và rollout có thứ tự.
- [ ] PDB/anti-affinity/topology spread phù hợp số broker và HA mode.
- [ ] Không scale replicas nếu chưa có per-node config/discovery/unique identity.
- [ ] Client dùng endpoint/failover phù hợp, không dựa vào Service round-robin cho active/backup.
- [ ] Đã test Pod replacement, broker restart, node drain, failover, PVC reattach và restore.
- [ ] Có alert queue age/depth, journal/page/disk, consumer count, restart, reconnect và DLQ.
- [ ] Có runbook bảo toàn PVC/message store trước khi xử lý lỗi.

## 18. Kết luận

**Kubernetes giữ danh tính Pod và gắn storage ổn định; broker vẫn phải tự quản lý identity, persistence, replication và failover.** StatefulSet cùng headless Service tạo hostname theo ordinal; `volumeClaimTemplates` tạo PVC riêng cho mỗi Pod. Khi Pod được thay thế, cùng identity và PVC giúp broker phục hồi instance/store cũ.

Với một broker, một StatefulSet replica và một PVC là điểm bắt đầu rõ ràng. Với nhiều broker, phải thiết kế riêng cho broker độc lập, Artemis cluster hoặc HA pair; `replicas > 1`, ClusterIP và PVC không tự tạo replication hay exactly-once. Độ tin cậy đến từ **stable identity + durable storage + broker topology đúng + graceful operations + backup/restore đã thử + kiểm thử message end-to-end**.

## Tài liệu tham khảo

- Kubernetes StatefulSets: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/
- Kubernetes Persistent Volumes và access modes: https://kubernetes.io/docs/concepts/storage/persistent-volumes/
- Kubernetes startup/readiness/liveness probes: https://kubernetes.io/docs/concepts/workloads/pods/probes/
- Apache ActiveMQ Artemis 2.40.0 documentation: https://activemq.apache.org/components/artemis/documentation/2.40.0/
- Apache ActiveMQ Classic Docker image: https://activemq.apache.org/components/classic/documentation/docker-image
