# Triển khai Deployment, Service và ConfigMap trên GKE

> **Chương:** GKE cơ bản  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Một nhóm phát triển đã đóng gói ứng dụng thành container image và lưu trong Artifact Registry. Bước tiếp theo là chạy nhiều bản sao ứng dụng trên Google Kubernetes Engine (GKE), cấp một địa chỉ truy cập ổn định cho các Pod, và thay đổi cấu hình mà không phải đóng gói lại image mỗi lần chuyển môi trường. Ba tài nguyên Kubernetes giữ vai trò trọng tâm trong tình huống này là **Deployment**, **Service** và **ConfigMap**.

Bài học đi từ khái niệm tới một lab có thể triển khai: tạo namespace riêng, khai báo ConfigMap cho trang web mẫu, chạy hai Pod thông qua Deployment, đưa lưu lượng vào Pod bằng ClusterIP Service, kiểm thử, cập nhật, rollback và dọn tài nguyên. Các phần mở rộng giải thích **GKE Autopilot/Standard, Artifact Registry, IAM, network exposure, probes, Java applications và chi phí**.

**Giới hạn an toàn:** các lệnh tạo GKE cluster, LoadBalancer hoặc lưu trữ có thể phát sinh chi phí thật. Hãy dùng project/cluster học tập được phép, đọc kubeconfig context trước mọi lệnh thay đổi và không áp dụng manifest demo vào namespace production.

## Mục tiêu học tập

Sau bài, người học có thể:

1. Mô tả vai trò của **Pod, ReplicaSet, Deployment, Service, ConfigMap** và cách các đối tượng liên kết bằng labels/selectors.
2. Chọn giữa GKE **Autopilot** và **Standard** theo nhu cầu quản lý hạ tầng.
3. Chuẩn bị đúng **project, cluster, location, kubeconfig context, IAM và namespace**.
4. Viết YAML cho một **ConfigMap**, một **Deployment** có resource requests, health probes và RollingUpdate, và một **ClusterIP Service**.
5. Dùng **kubectl apply, get, describe, logs, rollout status/history/undo, port-forward** để kiểm chứng ứng dụng.
6. Phân biệt **Service port, targetPort, containerPort**, EndpointSlice và DNS của Service.
7. Hiểu ConfigMap **env vars không tự cập nhật trong Pod đang chạy**, còn mounted volume có thể cập nhật trễ; subPath không tự nhận thay đổi.
8. Biết khi nào dùng **LoadBalancer/Ingress/Gateway**, cách hạn chế public exposure và kiểm soát chi phí.
9. Phân tích sự cố **ImagePullBackOff, CrashLoopBackOff, Pending, readiness failing, selector sai và thiếu ConfigMap**.
10. Thiết kế thay đổi cấu hình có kiểm soát, rollback và bảo vệ workload Java trong môi trường GKE.

## 1. Ba tài nguyên trung tâm và những lớp liên quan

| Tài nguyên | Trách nhiệm | Nó không tự làm gì? |
|---|---|---|
| **ConfigMap** | Chứa cấu hình không nhạy cảm dạng key/value hoặc file | Không mã hóa bí mật, không chạy ứng dụng |
| **Deployment** | Khai báo số bản sao Pod và chiến lược cập nhật/khôi phục workload stateless | Không tự cấp DNS Service hoặc public IP |
| **ReplicaSet** | Đảm bảo số Pod mục tiêu theo Deployment | Không thay thế Deployment làm API rollout thông thường |
| **Pod** | Đơn vị triển khai nhỏ nhất; chứa một hoặc nhiều container | Không có IP/định danh bền vững qua mỗi lần tạo lại |
| **Service** | Tạo endpoint ổn định và tìm các Pod phù hợp qua selector | Không thay đổi số replicas, không tự sửa ứng dụng chưa ready |
| **EndpointSlice** | Ghi thông tin các endpoint Pod có thể phục vụ Service | Không phải nơi người mới nên sửa thủ công khi Service có selector |
| **Namespace** | Gom và cô lập logical names/permissions trong cluster | Không tự tạo ranh giới mạng an toàn hoặc IAM project |
| **Ingress/Gateway** | Điều khiển HTTP(S) routing, TLS và policy theo controller | Không đồng nghĩa Service type LoadBalancer Layer 4 |

~~~mermaid
flowchart TD
    USER["Client trong cluster"] --> DNS["Kubernetes DNS\nweb-demo.gke-lab.svc.cluster.local"]
    DNS --> SVC["Service: web-demo\nClusterIP, TCP 8080"]
    SVC --> ES["EndpointSlices\nPod IPs sẵn sàng"]
    ES --> P1["Pod A: nginx\nport 80"]
    ES --> P2["Pod B: nginx\nport 80"]
    DEP["Deployment: web-demo\nreplicas = 2"] --> RS["ReplicaSet"]
    RS --> P1
    RS --> P2
    CM["ConfigMap: web-demo-config"] -. "env / mounted file" .-> P1
    CM -. "env / mounted file" .-> P2
~~~

**Hướng điều khiển khác hướng dữ liệu:** Deployment controller tạo và duy trì Pod thông qua ReplicaSet; Service chọn endpoints để lưu lượng tới Pod. ConfigMap được kubelet đưa vào container theo cách đã khai báo. Kubernetes không buộc các tài nguyên phải được tạo đúng thứ tự, nhưng nếu Deployment tham chiếu ConfigMap chưa tồn tại thì Pod có thể không khởi động được.

### 1.1. GKE khác Kubernetes upstream ở đâu?

Kubernetes xác định API của Deployment, Service, ConfigMap và các controller cơ bản. **GKE** vận hành Kubernetes trên Google Cloud với control plane quản lý, tích hợp VPC networking, Compute Engine infrastructure, Artifact Registry, Cloud Logging/Monitoring, IAM và các cơ chế Load Balancing.

| Chế độ GKE | Quản lý hạ tầng | Phù hợp |
|---|---|---|
| **Autopilot** | GKE quản lý worker nodes và phần lớn thiết lập hạ tầng; điều chỉnh resource requests theo giới hạn compute class | Nhóm muốn tập trung vào ứng dụng, ít vận hành node |
| **Standard** | Nhóm quản lý node pools và các cấu hình hạ tầng nhiều hơn, dù GKE vẫn quản lý control plane | Yêu cầu node, hardware, daemon và vận hành chuyên biệt |

Cả hai đều hỗ trợ Kubernetes Deployment, Service và ConfigMap. Trong lab, dùng **cluster đã tồn tại** là lựa chọn tiết kiệm và ít rủi ro hơn tạo cluster mới. Nếu cần tạo, bài chọn Autopilot để tập trung vào ba đối tượng chính. Cluster mode, node pool behavior và giới hạn Autopilot thay đổi theo phiên bản; cần đọc trạng thái cluster hiện có trước khi tạo workload.

### 1.2. Stateless không đồng nghĩa “không có dữ liệu”

Deployment phù hợp web/API services có state quan trọng lưu **bền vững bên ngoài Pod** (Cloud SQL, Firestore, Cloud Storage, Pub/Sub...) hoặc được thiết kế cache/retry an toàn. Không dùng một Deployment với filesystem tạm của Pod làm bản lưu duy nhất của file upload, database hay transaction.

Khi Pod bị thay thế lúc rollout, local data như writable container layer hoặc emptyDir có thể biến mất. Nếu cần persistent per-Pod identity/storage, hãy học **StatefulSet** và PersistentVolumes thay vì cố biến Deployment thành database cluster.

## 2. Kịch bản lab, giả định và tiêu chí đạt

Ta triển khai một HTTP page rất nhỏ bằng **nginx** trên GKE. Nginx là lựa chọn minh họa vì có thể trả nội dung ngay từ một file được mount bằng ConfigMap, không đòi hỏi build image trước. Phần cuối mở rộng cách áp dụng nguyên tắc tương tự cho **Java/Spring Boot** và private images trong Artifact Registry.

| Thành phần | Giá trị minh họa |
|---|---|
| Google Cloud project | YOUR_PROJECT_ID |
| GKE cluster | gke-app-lab (hoặc cluster được cấp) |
| Location | asia-southeast1 (region, thay theo cluster thực tế) |
| Namespace | gke-lab |
| ConfigMap | web-demo-config |
| Deployment | web-demo |
| Replicas | 2 |
| Container image | nginx:stable-alpine (chỉ dùng cho lab) |
| Container listening port | 80/TCP |
| Service name/type | web-demo / ClusterIP |
| Service port | 8080/TCP |
| Service targetPort | http (tên container port = 80) |
| Local port-forward | localhost:8080 |
| Web page | Giá trị index.html từ ConfigMap |

**Kết quả cần quan sát:**

1. Namespace **gke-lab** tồn tại trong đúng cluster.
2. ConfigMap có khóa **APP_MESSAGE** và tệp **index.html**.
3. Deployment có **2/2 Ready** sau khi scheduler đủ capacity và probes thành công.
4. Service **web-demo** có ClusterIP và endpoints thuộc hai Pod đúng label.
5. **kubectl port-forward** cùng một thử nghiệm từ Pod trong cluster trả HTTP 200 và nội dung trang.
6. Thay ConfigMap làm thay đổi mounted file sau độ trễ đồng bộ, nhưng **APP_MESSAGE** là env var trong container đang chạy **không tự đổi**.
7. Rollout restart thay Pod, biến môi trường mới được nạp và số replicas trở lại 2/2.

**Chú ý:** nginx:stable-alpine là tag có thể thay đổi theo thời gian. Đối với môi trường production, build/kiểm tra image, lưu ở Artifact Registry và **pin theo immutable digest**. Lab công khai không chứng minh đầy đủ bài toán supply-chain security.

## 3. Preflight: project, API, quyền và kubeconfig

### 3.1. Chỉ đọc: kiểm tra GCP context

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"
CLUSTER="gke-app-lab"
NAMESPACE="gke-lab"

gcloud auth list
gcloud config list
gcloud projects describe "$PROJECT_ID"

# Xem API đã bật; không tự thay đổi production.
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="name:container.googleapis.com"

# Liệt kê cluster có quyền xem.
gcloud container clusters list --project="$PROJECT_ID"

# Đọc cluster mà bạn định kết nối.
gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format="yaml(name,location,status,autopilot,network,subnetwork)"
~~~

**Không đoán location.** GKE cluster có thể zonal hoặc regional; dùng **--location** đúng với giá trị tra được. Nếu muốn chỉ xem tài nguyên trong cluster, còn cần quyền truy cập Kubernetes API và network connectivity tới control plane.

### 3.2. Nếu chưa có cluster lab

~~~bash
# THAY ĐỔI + CÓ CHI PHÍ: chỉ chạy trong project lab được phép.
# API đã phải được bật; account cần quyền tạo GKE cluster,
# hạ tầng/network/quota và IAM theo yêu cầu GKE.
gcloud container clusters create-auto "$CLUSTER" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"
~~~

**Tạo cluster là một thao tác tốn thời gian và chi phí thực tế.** Các mặc định về mạng, release channel, node service account và security posture phải được kiểm tra với chính sách của tổ chức. Trong production nên chọn service account cho nodes có quyền tối thiểu, thay vì dựa vào mặc định thiếu kiểm soát. Việc bạn tạo được cluster không chứng minh đã đủ quyền tạo LoadBalancer, pull private image hoặc truy cập Cloud SQL.

### 3.3. Kết nối kubectl với cluster

~~~bash
# GHI CẤU HÌNH kubeconfig cục bộ, không tạo Deployment.
gcloud container clusters get-credentials "$CLUSTER" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# CHỈ ĐỌC — bắt buộc đối chiếu context trước khi apply/delete.
kubectl config current-context
kubectl config get-contexts
kubectl cluster-info
kubectl get namespaces
~~~

GKE có thể cần **gke-gcloud-auth-plugin** tương thích phiên bản gcloud/kubectl đang dùng. Lệnh get-credentials cập nhật kubeconfig trên máy bạn; nếu đang làm nhiều project, **kubectl có thể trỏ nhầm cluster**. Khi thao tác hạ tầng production, nên dùng context explicit hoặc xác minh trong change ticket.

**Quyền IAM và Kubernetes RBAC khác nhau:** IAM cho phép thao tác/đăng nhập GKE cluster theo cơ chế của Google Cloud; các quyền tạo Deployment/Service/ConfigMap trong namespace còn phải được Kubernetes RBAC hoặc cơ chế GKE phù hợp cho phép. Không cấp Cluster Admin cho mọi developer để sửa lỗi Forbidden.

### 3.4. Tạo namespace riêng (thay đổi cluster)

~~~bash
# THAY ĐỔI — chỉ trong cluster lab đúng context.
kubectl create namespace "$NAMESPACE"

# CHỈ ĐỌC — xác nhận.
kubectl get namespace "$NAMESPACE"
kubectl get all -n "$NAMESPACE"
~~~

Nếu namespace đã tồn tại, dùng **kubectl get namespace** thay vì tạo lại. Namespace hỗ trợ tách tên resource và RBAC, **không tự chặn network traffic giữa namespaces**; muốn cô lập đường mạng cần NetworkPolicy hoặc chính sách GKE khác.

## 4. YAML Kubernetes và nguyên tắc khai báo

Một object manifest thường có:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-demo
  namespace: gke-lab
spec:
  # Desired state mà controller sẽ duy trì
  replicas: 2
~~~

- **apiVersion**: nhóm/phiên bản API.
- **kind**: loại tài nguyên.
- **metadata**: name, namespace, labels, annotations.
- **spec**: desired state, ví dụ số Pod và Pod template.
- **status**: trạng thái thực tế do control plane cập nhật; **không tự điền vào manifest**.

**kubectl apply** đưa cấu hình khai báo tới Kubernetes API, sau đó các controllers cố gắng làm thực tế khớp spec. Một thông báo **configured/created** chỉ xác nhận object được lưu/nhận; chưa bảo đảm Pod Running, image pull thành công, Service có endpoints hoặc ứng dụng healthy.

### 4.1. Labels và selectors là hợp đồng giữa Deployment và Service

Ví dụ cả Deployment và Service thống nhất label:

~~~yaml
app.kubernetes.io/name: web-demo
app.kubernetes.io/part-of: gke-lab
~~~

Deployment **spec.selector.matchLabels** phải khớp **spec.template.metadata.labels**. Selector của Deployment gần như là phần định danh bất biến sau khi tạo; nếu cần đổi selector nên thiết kế migration/create mới chứ không sửa tùy tiện.

Service **spec.selector** phải khớp labels của Pod thực tế. Nếu selector sai, Service vẫn có ClusterIP và DNS nhưng **không có endpoint phù hợp**, khiến request timeout hoặc connection refused tùy đường đi.

### 4.2. Namespace phải khớp

ConfigMap và Pod tham chiếu nó thường phải cùng namespace. Một ConfigMap tên **web-demo-config** ở namespace **default** không tự có mặt trong **gke-lab**. Deployment và Service có thể trùng tên ở các namespaces khác nhau; vì vậy dùng **-n gke-lab** hoặc khai báo **metadata.namespace** rõ ràng.

## 5. Manifest 1 — ConfigMap cho cấu hình không bí mật

Tạo tệp lab tên **01-configmap.yaml** với nội dung:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: web-demo-config
  namespace: gke-lab
  labels:
    app.kubernetes.io/name: web-demo
data:
  APP_MESSAGE: "Xin chao tu GKE!"
  index.html: |
    <!doctype html>
    <html lang="vi">
      <head>
        <meta charset="utf-8">
        <title>GKE Deployment + Service + ConfigMap</title>
      </head>
      <body>
        <h1>GKE lab: phien ban cau hinh 1</h1>
        <p>Trang nay duoc lay tu ConfigMap mount vao Pod.</p>
      </body>
    </html>
~~~

Ý nghĩa:

- **data.APP_MESSAGE** là một chuỗi có thể đưa vào biến môi trường của container.
- **data.index.html** chứa nội dung nhiều dòng, được kubelet chiếu thành tệp trong ConfigMap volume.
- **ConfigMap không phải nơi lưu secret**. Không nhúng password, database URL chứa credential, access token hoặc private key vào đó.
- Tổng kích thước mỗi ConfigMap bị giới hạn khoảng **1 MiB**; nội dung lớn nên dùng nơi lưu khác như Cloud Storage hoặc volume phù hợp.

Kubernetes còn hỗ trợ **binaryData** cho nội dung binary base64-encoded. Với ví dụ HTML, dùng **data** dễ đọc và kiểm tra hơn. Một ConfigMap có thể có **immutable: true** khi chính sách cần ngăn sửa, nhưng sau đó không thể thay data/binaryData; phải tạo bản mới và cập nhật Pod reference.

### 5.1. Áp dụng và đọc lại

~~~bash
# THAY ĐỔI — tạo/cập nhật ConfigMap trong cluster lab.
kubectl apply -f 01-configmap.yaml

# CHỈ ĐỌC.
kubectl get configmap web-demo-config -n "$NAMESPACE"
kubectl describe configmap web-demo-config -n "$NAMESPACE"
kubectl get configmap web-demo-config -n "$NAMESPACE" -o yaml
~~~

Khi copy output vào ticket, xem xét dữ liệu cấu hình có thể tiết lộ thông tin nội bộ. ConfigMap values có thể được đọc bởi những người có quyền get/list configmaps trong namespace.

## 6. Manifest 2 — Deployment có hai Pod, health probes và ConfigMap

Tạo tệp **02-deployment.yaml**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-demo
  namespace: gke-lab
  labels:
    app.kubernetes.io/name: web-demo
    app.kubernetes.io/part-of: gke-lab
spec:
  replicas: 2
  revisionHistoryLimit: 5
  progressDeadlineSeconds: 300
  selector:
    matchLabels:
      app.kubernetes.io/name: web-demo
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app.kubernetes.io/name: web-demo
        app.kubernetes.io/part-of: gke-lab
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: web
          # Lab demo: mutable public tag, production nên dùng digest từ Artifact Registry.
          image: nginx:stable-alpine
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 80
              protocol: TCP
          env:
            - name: APP_MESSAGE
              valueFrom:
                configMapKeyRef:
                  name: web-demo-config
                  key: APP_MESSAGE
          volumeMounts:
            - name: web-content
              mountPath: /usr/share/nginx/html
              readOnly: true
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 3
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 15
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
      volumes:
        - name: web-content
          configMap:
            name: web-demo-config
            items:
              - key: index.html
                path: index.html
~~~

**Tự kiểm tra manifest trước khi apply:**

| Vị trí | Giá trị | Ý nghĩa |
|---|---|---|
| replicas | 2 | Duy trì hai Pod nếu có tài nguyên |
| selector.matchLabels | app.kubernetes.io/name=web-demo | Chọn Pod template tương ứng |
| template.metadata.labels | Cùng nhãn | Để Deployment quản lý đúng Pod |
| containerPort | 80, name=http | Nginx lắng nghe TCP 80 |
| resources.requests | 500m CPU, 512Mi memory | Cung cấp thông tin để scheduler/autoscaling đặt Pod |
| resources.limits | 1000m CPU, 1Gi memory | Giới hạn tài nguyên; vượt memory có thể OOMKilled |
| readinessProbe | HTTP GET / | Pod chưa ready thì không nhận traffic Service bình thường |
| livenessProbe | HTTP GET / | Nếu lỗi liên tiếp, kubelet có thể restart container |
| env.configMapKeyRef | APP_MESSAGE | Chỉ đọc giá trị lúc container được khởi tạo |
| configMap volume | index.html | Tệp được mount vào thư mục Nginx phục vụ |
| RollingUpdate | maxSurge=1, maxUnavailable=0 | Cố giữ đủ 2 Pod available trong rollout, cần capacity |
| revisionHistoryLimit | 5 | Giữ tối đa các ReplicaSet cũ theo policy/controller |
| progressDeadlineSeconds | 300 | Báo rollout không tiến triển sau ngưỡng, không tự rollback |

**Lưu ý Autopilot:** GKE có thể điều chỉnh resource requests/limits theo compute class, chính sách bursting và giới hạn hợp lệ. Giá trị YAML không tự là giá trị cuối cùng. Kiểm tra Pod spec được GKE chấp nhận sau apply và theo dõi billing. Autopilot có thể chưa cấp node ngay, nên Pod Pending tạm thời không nhất thiết là lỗi ứng dụng.

### 6.1. Tại sao phải có readiness lẫn liveness?

- **Readiness:** “Pod có thể phục vụ request lúc này không?”. Khi false, Pod thông thường bị loại khỏi tập endpoint sẵn sàng của Service.
- **Liveness:** “Container có cần khởi động lại không?”. Khi probe thất bại đủ lần, kubelet restart container.
- **Startup probe** (không dùng trong Nginx lab) phù hợp với ứng dụng Java khởi động chậm; trong thời gian startup probe chưa thành công, liveness/readiness được xử lý theo cơ chế startup probe để tránh restart JVM vô ích.

Không cho liveness phụ thuộc trực tiếp vào một downstream DB có thể lỗi tạm thời: nếu DB chậm, toàn bộ Pod có thể bị restart liên tục thay vì chờ reconnect. Readiness có thể phản ánh khả năng phục vụ request theo thiết kế ứng dụng.

### 6.2. Áp dụng và chờ rollout

~~~bash
# THAY ĐỔI.
kubectl apply -f 02-deployment.yaml

# CHỈ ĐỌC / CHỜ TRẠNG THÁI rollout.
kubectl rollout status deployment/web-demo \
  -n "$NAMESPACE" --timeout=300s

kubectl get deployment web-demo -n "$NAMESPACE" -o wide
kubectl get replicasets -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo -o wide
~~~

Nếu rollout status timeout, **không mặc nhiên delete Pod**. Kiểm tra events, image pull, scheduling và probes; Deployment controller có thể đang chờ tài nguyên hoặc Pod chưa ready. Với **maxUnavailable=0**, việc không có đủ headroom cho **maxSurge=1** có thể trì hoãn cập nhật; đó là đánh đổi giữa availability và capacity.

### 6.3. Kiểm tra config thật trong Pod

~~~bash
# CHỈ ĐỌC — xem các Pod sau khi đã Ready.
kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo

# Chọn POD_NAME từ kết quả trên, KHÔNG dùng placeholder nguyên văn.
POD_NAME="REPLACE_WITH_POD_NAME"

# Đọc biến môi trường đã nạp khi container được tạo.
kubectl exec -n "$NAMESPACE" "$POD_NAME" -c web -- \
  printenv APP_MESSAGE

# Đọc tệp index.html mount từ ConfigMap.
kubectl exec -n "$NAMESPACE" "$POD_NAME" -c web -- \
  cat /usr/share/nginx/html/index.html
~~~

**Không dùng kubectl exec để chạy lệnh phá hủy trên Pod production.** Pod có thể bị thay trong lúc thao tác; nếu tên Pod không còn, lấy lại từ selector và kiểm tra trạng thái.

## 7. Manifest 3 — Service ClusterIP và truy cập tới Pod

Tạo tệp **03-service.yaml**:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: web-demo
  namespace: gke-lab
  labels:
    app.kubernetes.io/name: web-demo
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: web-demo
  ports:
    - name: http
      protocol: TCP
      port: 8080
      targetPort: http
~~~

Service chọn các Pod có label **app.kubernetes.io/name=web-demo**. Vì container đã khai báo một port đặt tên là **http** và ánh xạ tới **80**, nên Service port **8080** chuyển tiếp tới container port **80**.

~~~mermaid
flowchart LR
    C["Pod client"] -->|"web-demo:8080"| S["Service ClusterIP\nport: 8080"]
    S --> E["EndpointSlice"]
    E -->|"targetPort: http = 80"| A["Pod A\nnginx :80"]
    E -->|"targetPort: http = 80"| B["Pod B\nnginx :80"]
~~~

### 7.1. Ba port dễ nhầm

| Trường | Bối cảnh | Ý nghĩa |
|---|---|---|
| **containerPort: 80** | Deployment Pod template | Khai báo cổng container lắng nghe; không tự tạo listener hoặc mở mạng |
| **Service port: 8080** | Service spec | Cổng mà các client gọi Service |
| **targetPort: http** | Service spec | Trỏ đến container port có tên http, tức TCP 80 trong lab |
| **nodePort** | Chỉ khi kiểu Service cần NodePort | Cổng node-level được sử dụng tùy Service type và cấu hình GKE |
| **Local port 8080** | kubectl port-forward | Cổng trên máy người thao tác, không phải một public endpoint |

**Service không trực tiếp tạo Pod.** Nếu Deployment chưa có Pod Ready, Service vẫn có thể có ClusterIP nhưng chưa định tuyến được request tới application endpoint.

### 7.2. Áp dụng và xem EndpointSlice

~~~bash
# THAY ĐỔI — tạo/cập nhật Service.
kubectl apply -f 03-service.yaml

# CHỈ ĐỌC — thông số IP/port/selector.
kubectl get service web-demo -n "$NAMESPACE" -o wide
kubectl describe service web-demo -n "$NAMESPACE"

# CHỈ ĐỌC — EndpointSlices thuộc Service.
kubectl get endpointslices -n "$NAMESPACE" \
  -l kubernetes.io/service-name=web-demo -o wide

# CHỈ ĐỌC — so selector với label của Pod.
kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo --show-labels
~~~

Nếu Service **không có endpoints**, kiểm tra selector, Pod readiness, namespace và cổng. Trong Kubernetes hiện hành, EndpointSlice là API được dùng để theo dõi endpoints; lệnh **kubectl get endpoints** có thể tồn tại nhưng không nên coi là nguồn duy nhất của thiết kế mới.

### 7.3. DNS tên Service

Kubernetes DNS thường cho phép client trong cùng namespace dùng **web-demo** hoặc **web-demo.gke-lab**. Fully qualified name thường là:

~~~text
web-demo.gke-lab.svc.cluster.local
~~~

Tuy nhiên, **cluster domain có thể được tùy biến**; đừng hardcode cluster.local nếu cluster của tổ chức dùng tên khác. Tên Service ổn định hơn Pod IP; Pod có thể bị thay và nhận IP mới khi Deployment scale, upgrade hoặc reschedule.

### 7.4. Kiểm thử qua port-forward

~~~bash
# THAO TÁC TẠM THỜI — mở tunnel local tới một Pod do Service chọn.
kubectl port-forward -n "$NAMESPACE" \
  service/web-demo 8080:8080
~~~

Mở terminal khác trên máy người vận hành:

~~~bash
curl -i http://127.0.0.1:8080/
~~~

Kết quả mong đợi: **HTTP 200**, nội dung HTML có dòng **GKE lab: phien ban cau hinh 1**.

**Giới hạn chứng cứ:** kubectl port-forward khi trỏ vào Service có thể chọn một Pod tương ứng để chuyển cổng, **không nhất thiết đi qua chính data plane của ClusterIP hoặc external load balancer**. Nó chứng minh Pod/app có thể được truy cập qua API-mediated tunnel, nhưng không thay thế bài kiểm tra Service networking từ một client Pod thật.

### 7.5. Kiểm thử từ một Pod trong cùng namespace

Một cách kiểm thử Service DNS, port và đường mạng ngay trong cluster:

~~~bash
# TẠO POD TẠM rồi xóa khi xong.
# Image curlimages/curl chỉ là client lab, cần khả năng pull từ registry.
kubectl run http-client \
  -n "$NAMESPACE" \
  --restart=Never \
  --image=curlimages/curl:8.12.1 \
  --rm -i -- \
  curl -fsS http://web-demo:8080/
~~~

Trường hợp **--rm** không dọn Pod vì terminal bị ngắt, đọc lại trạng thái và xóa riêng Pod **http-client** đã tạo trong namespace lab. Không xóa Pod cùng tên nếu không phải tài nguyên mình sở hữu.

Nếu request trả 200 từ trong cluster nhưng client ngoài VPC không truy cập được, đó có thể là hành vi **đúng theo thiết kế**: ClusterIP chỉ là endpoint nội bộ của Kubernetes, không cấp public IP.

## 8. Service types và lựa chọn mức độ phơi bày mạng

| Service type | Ý nghĩa | Dùng khi nào? |
|---|---|---|
| **ClusterIP** | IP Service nội bộ; loại mặc định | Giao tiếp giữa workloads trong cluster, service backend |
| **NodePort** | Mở một cổng trên nodes theo cấu hình hỗ trợ | Tích hợp đặc thù; không phải lựa chọn public phổ biến cho app mới |
| **LoadBalancer** | Yêu cầu cloud integration cấp load balancer L4 | Cần endpoint có thể truy cập từ VPC hoặc Internet |
| **ExternalName** | CNAME DNS tới một hostname bên ngoài | Alias tên DNS, không tạo reverse proxy hay HTTP route |
| **Headless (clusterIP: None)** | DNS công bố endpoints theo cơ chế headless | StatefulSet/service discovery chuyên biệt |

Đối với HTTP/HTTPS nhiều host/path hoặc TLS termination, **GKE Ingress** hoặc **Gateway API** (khi được cấu hình và hỗ trợ) thường phù hợp hơn một Service LoadBalancer đơn lẻ. Không đồng nhất Service LoadBalancer Layer 4 với HTTP(S) Application Load Balancer.

### 8.1. External LoadBalancer — chỉ tạo khi thực sự cần

Manifest minh họa cho Service khác tên để không ảnh hưởng ClusterIP lab:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: web-demo-public
  namespace: gke-lab
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: web-demo
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
  # Chỉ dùng CIDR public thật đã được phép truy cập nếu dịch vụ hỗ trợ.
  # Không sao chép giá trị minh họa khi deploy.
  loadBalancerSourceRanges:
    - "198.51.100.0/24"
~~~

**Không thực thi manifest này trên production theo mặc định.** Kiểu LoadBalancer yêu cầu GKE tạo tài nguyên load balancer Google Cloud, có thể cấp **external IP và phí vận hành**; một rule quá rộng có thể đưa ứng dụng ra Internet.

Dải **198.51.100.0/24** ở trên là **dải địa chỉ tài liệu**, không phải mạng của người học. Thay bằng CIDR truy cập thực đã duyệt. Việc sử dụng loadBalancerSourceRanges và các firewall/policy liên quan còn phụ thuộc loại Service load balancer. Với sản phẩm Internet-facing, cần bổ sung auth, TLS, WAF/Cloud Armor khi phù hợp và kiểm tra security posture.

**Lưu ý theo GKE version:** các cơ chế backend cho external passthrough Network Load Balancer đã được cải tiến trong những GKE releases mới. Không áp dụng một annotation kiểu legacy target pool từ tutorial cũ khi chưa xem tài liệu của đúng cluster version.

### 8.2. Internal LoadBalancer — chỉ dành VPC/hybrid consumers

Khi cần một LoadBalancer service **chỉ có địa chỉ nội bộ**, một cách được GKE hỗ trợ là annotation:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: web-demo-internal
  namespace: gke-lab
  annotations:
    networking.gke.io/load-balancer-type: "Internal"
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: web-demo
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
~~~

Tùy GKE version và GKE subsetting, Google Cloud còn khuyến nghị dùng **spec.loadBalancerClass: networking.gke.io/l4-regional-internal** cho internal passthrough NLB ở những cluster hỗ trợ. **loadBalancerClass là thuộc tính bất biến**, cần chọn trước khi tạo Service. Đừng áp cả hai phương pháp mà chưa kiểm tra tài liệu và cấu hình cluster.

Internal load balancer thường chỉ phục vụ clients có route/đường mạng thích hợp trong VPC hoặc mạng kết nối. **“Internal” không thay thế authentication**: ứng dụng vẫn cần xác thực/ủy quyền theo yêu cầu. External/Internal LoadBalancers đều có thể tính phí ngay khi chưa có nhiều request.

### 8.3. Nên dùng gì trong lab?

Bài này sử dụng **ClusterIP + port-forward** để tránh tạo load balancer và giảm bề mặt tấn công. Chỉ triển khai Service LoadBalancer khi mục tiêu bài học yêu cầu thật, project được cấp quyền và đã kiểm tra chi phí. Không cần có public IP để chứng minh ba đối tượng Deployment, Service, ConfigMap hoạt động.

## 9. ConfigMap: cách tiêu thụ và hành vi khi cập nhật

ConfigMap có thể đưa vào Pod bằng nhiều cách:

| Cách sử dụng | Cấu hình Pod | Thay đổi ConfigMap có đi vào container đang chạy? |
|---|---|---|
| **Một key thành env var** | env.valueFrom.configMapKeyRef | **Không**, env chỉ được đọc lúc container start |
| **Nhiều key thành env vars** | envFrom.configMapRef | **Không**, cần Pod mới/restart |
| **Mount thành files** | volumes.configMap + volumeMounts | **Có thể được kubelet cập nhật eventual**, ứng dụng phải đọc lại file |
| **Mount bằng subPath** | volumeMounts.subPath | **Không tự cập nhật** nội dung ConfigMap ở mount đó |
| **API read trực tiếp** | App có quyền truy cập Kubernetes API | Phải thiết kế auth/RBAC/watch riêng; thường không cần cho app cơ bản |

### 9.1. Thí nghiệm A: đổi trang HTML

Sửa **01-configmap.yaml**:

- Dòng **APP_MESSAGE** thành **Xin chao tu GKE - cau hinh 2!**
- Dòng **h1** thành **GKE lab: phien ban cau hinh 2**

Sau đó:

~~~bash
# THAY ĐỔI ConfigMap nhưng chưa thay Deployment template.
kubectl apply -f 01-configmap.yaml

# CHỈ ĐỌC metadata ConfigMap.
kubectl get configmap web-demo-config \
  -n "$NAMESPACE" -o yaml
~~~

Chờ kubelet đồng bộ volume, rồi thử lại:

~~~bash
# Terminal 1: port-forward như phần trên.
kubectl port-forward -n "$NAMESPACE" \
  service/web-demo 8080:8080

# Terminal 2:
curl -fsS http://127.0.0.1:8080/
~~~

Kết quả mong đợi sau khi volume được đồng bộ và nginx đọc file mới: trang chứa **phien ban cau hinh 2**. Đây là cập nhật **mounted file**, không phải đảm bảo ứng dụng khác luôn tự reload cấu hình. Với Java/Spring Boot, nếu ứng dụng đọc file chỉ khi startup, một file mới được mount vẫn **không làm bean/application config tự cập nhật**.

### 9.2. Thí nghiệm B: env var vẫn cũ trong Pod đang chạy

~~~bash
# Chọn một Pod hiện tại trong deployment.
kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo

POD_NAME="REPLACE_WITH_POD_NAME"
kubectl exec -n "$NAMESPACE" "$POD_NAME" -c web -- \
  printenv APP_MESSAGE
~~~

Nếu Pod chưa bị thay, **APP_MESSAGE** có thể vẫn là giá trị cũ dù ConfigMap đã đổi. Cơ chế env var của container không cập nhật theo API ConfigMap runtime.

### 9.3. Chủ động restart Deployment để nạp env mới

~~~bash
# THAY ĐỔI Pod template annotation để yêu cầu rollout mới.
kubectl rollout restart deployment/web-demo -n "$NAMESPACE"

# CHỈ ĐỌC/CHỜ.
kubectl rollout status deployment/web-demo \
  -n "$NAMESPACE" --timeout=300s

kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo -o wide
~~~

Lấy tên **Pod mới**, rồi đọc lại env:

~~~bash
POD_NAME="REPLACE_WITH_NEW_POD_NAME"
kubectl exec -n "$NAMESPACE" "$POD_NAME" -c web -- \
  printenv APP_MESSAGE
~~~

Lúc này giá trị phải là **Xin chao tu GKE - cau hinh 2!** nếu Pod mới được tạo từ đúng ConfigMap key.

**Rollout restart không đồng nghĩa “reload mà không ảnh hưởng request nào”**: nó tạo Pod mới và thay Pod cũ theo strategy/capacity/readiness. Cần kiểm tra lưu lượng và khả năng phục hồi tương ứng với SLO.

### 9.4. Có nên tự đổi ConfigMap trong production?

Với hệ thống có kiểm soát, thường nên lưu các manifests trong Git, cập nhật bằng pull request và GitOps/CI, rồi:

- Tạo **ConfigMap phiên bản mới** với tên mới, ví dụ **web-demo-config-v2**, hoặc
- Thay config trong manifest và **chủ động rollout restart**,
- Hoặc cho hệ thống quản lý triển khai tự thay annotation của Pod template theo **checksum/config revision**.

Bằng cách đó có thể đối chiếu **phiên bản image + phiên bản config** khi rollback. ConfigMap mutable được chỉnh trực tiếp ngoài Git có thể làm cùng một Deployment revision chạy với các nội dung khác nhau mà khó tái tạo.

### 9.5. Các giới hạn cần nhớ

- **ConfigMap không phải Secret**; secret phải dùng Secret Manager/Secret đúng mô hình và IAM/RBAC, không đặt password vào ConfigMap.
- Dữ liệu ConfigMap có giới hạn kích thước; không dùng để nhét nhiều MB file build/ML model.
- ConfigMap volume có thể có độ trễ cập nhật (kubelet sync/cache propagation).
- Mount bằng **subPath** sẽ **không** nhận cập nhật live.
- Ứng dụng có thể cần restart/reload riêng dù file mount đã đổi.
- ConfigMap **immutable** không thể update data; dùng tài nguyên mới có tên khác rồi cập nhật Pod reference.
- Khi xóa ConfigMap vẫn đang được Pod hoặc rollout mới tham chiếu, Pod mới có thể bị kẹt trong trạng thái lỗi cấu hình.
- ConfigMap tham chiếu **bằng key bị thiếu** có thể chặn container start nếu tham chiếu không optional.

## 10. Deployment update, rollout history và rollback

Deployment đảm bảo **desired replicas**, kiểm soát các Pod revisions thông qua ReplicaSet và cập nhật theo strategy. Khi thay container image hoặc Pod template, Kubernetes thường tạo một **ReplicaSet mới**.

### 10.1. RollingUpdate hoạt động thế nào?

~~~mermaid
sequenceDiagram
    participant OP as Operator / CI
    participant D as Deployment controller
    participant OLD as Old ReplicaSet
    participant NEW as New ReplicaSet
    participant S as Service
    OP->>D: Apply Pod template mới
    D->>NEW: Tạo Pod mới (maxSurge)
    NEW-->>D: Pod Ready
    D->>OLD: Giảm replica cũ
    D->>NEW: Tạo thêm Pod mới
    S->>NEW: Chọn endpoints Ready mới
    D-->>OP: Rollout hoàn tất khi đạt điều kiện
~~~

Với lab **replicas=2**, **maxSurge=1** cho phép tạm có tối đa 3 Pod, còn **maxUnavailable=0** cố duy trì 2 Pod available trong quá trình thay. Điều này đòi hỏi đủ cluster capacity và readiness probes đúng.

Khi không có Pod mới đủ điều kiện Ready, rollout có thể báo không tiến triển sau **progressDeadlineSeconds=300**. Kubernetes **không tự undo** Deployment chỉ vì deadline bị vượt; operator/CI phải đánh giá và rollback theo quy trình.

### 10.2. Kiểm tra rollout trước và sau thay đổi

~~~bash
kubectl rollout history deployment/web-demo -n "$NAMESPACE"

kubectl describe deployment web-demo -n "$NAMESPACE"

kubectl rollout status deployment/web-demo \
  -n "$NAMESPACE" --timeout=300s

kubectl get replicasets -n "$NAMESPACE"
~~~

Chỉ những thay đổi trong **Pod template** thường tạo Deployment revision mới. Sửa metadata ngoài Pod template hoặc sửa ConfigMap riêng **không nhất thiết** tạo revision của Deployment. Để đưa version config vào history, hãy quản lý config name/checksum/version ở Pod template.

### 10.3. Đổi image có kiểm soát

Trong bài, image public dùng tag mutable để demo. Với pipeline thực tế, giả sử image đã build, scan và push tới Artifact Registry. Khi đã biết **IMAGE_REF thực**:

~~~bash
# THAY ĐỔI — chỉ làm khi IMAGE_REF là image đã tồn tại và được duyệt.
# Ví dụ giá trị IMAGE_REF hợp lệ:
# asia-southeast1-docker.pkg.dev/PROJECT/REPO/web-demo@sha256:ACTUAL_DIGEST

kubectl set image deployment/web-demo \
  web="$IMAGE_REF" \
  -n "$NAMESPACE"

kubectl rollout status deployment/web-demo \
  -n "$NAMESPACE" --timeout=300s
~~~

Cẩn trọng: nếu thay image Nginx bằng ứng dụng Java chạy cổng **8080** mà giữ nguyên Service targetPort **80** và readiness path cũ, rollout có thể fail. **Image, port, probes, ConfigMap, securityContext và Service targetPort phải được thay như một thay đổi có kế hoạch**.

### 10.4. Rollback một Deployment

Nếu bản image mới lỗi, sử dụng:

~~~bash
# CHỈ ĐỌC — các revision Deployment còn lưu.
kubectl rollout history deployment/web-demo -n "$NAMESPACE"

# THAY ĐỔI — quay lại Pod template của revision trước còn tồn tại.
kubectl rollout undo deployment/web-demo -n "$NAMESPACE"

# CHỈ ĐỌC/CHỜ.
kubectl rollout status deployment/web-demo \
  -n "$NAMESPACE" --timeout=300s
~~~

**Giới hạn của rollback:** undo khôi phục **Pod template trước**, nhưng **không tự rollback ConfigMap nội dung, Secret, Service, external database schema hay IAM** nếu chúng được cập nhật ngoài Deployment. Nếu template tham chiếu mutable tag hoặc ConfigMap cùng tên đã bị sửa, bản rollback có thể **không tái tạo chính xác** bản chạy cũ.

Do đó bản phát hành production nên ghi rõ:

- Image digest và provenance.
- ConfigMap version/checksum.
- Service/port contract.
- Resource requests/limits và probes.
- Database migration compatibility.
- Rollback window và retention của Artifact Registry.

## 11. Scale Deployment và hiểu tính ổn định của Service

Một Deployment có thể scale nhanh trong lab:

~~~bash
# THAY ĐỔI — tăng số Pod mong muốn từ 2 lên 3.
kubectl scale deployment/web-demo \
  -n "$NAMESPACE" --replicas=3

# CHỈ ĐỌC.
kubectl get deployment web-demo -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo -o wide
kubectl get endpointslices -n "$NAMESPACE" \
  -l kubernetes.io/service-name=web-demo
~~~

Service **web-demo:8080** vẫn giữ cùng tên/endpoint khi các Pod phía sau thay đổi. Trong hệ thống Kubernetes, các Pod được thay có thể nhận IP mới; consumers nên sử dụng **Service DNS**, không hardcode Pod IP.

Khôi phục về 2 replicas:

~~~bash
kubectl scale deployment/web-demo \
  -n "$NAMESPACE" --replicas=2
~~~

**Lưu ý về GitOps và HPA:** nếu manifest Git khai báo replicas=2, một lần apply/reconcile tiếp theo có thể đưa scale về 2. Nếu có Horizontal Pod Autoscaler, nó có thể tiếp tục điều chỉnh replicas. Không điều chỉnh thủ công rồi giả định thay đổi sẽ tồn tại vĩnh viễn khi có controller khác đang quản lý desired state.

### 11.1. Scale không có nghĩa mọi Pod lập tức healthy

- Scheduler cần đủ CPU/memory, node/zone capacity.
- Container cần pull image và khởi động.
- Startup/readiness phải thành công.
- Service cần cập nhật tập endpoints theo readiness.
- Tăng số Pod có thể tăng DB connection count, load lên downstream, quota và chi phí.

Scale-to-zero với **replicas=0** sẽ khiến Service không còn Pod endpoints; đây có thể là trạng thái hợp lệ cho workload không có lưu lượng, nhưng ứng dụng online sẽ không trả request như bình thường. Nếu cần tự động scale theo request/traffic, nghiên cứu HPA/KEDA hoặc Cloud Run tùy kiến trúc.

## 12. Áp dụng vào ứng dụng Java và Artifact Registry

Trong module CLOUD_PROVIDERS_GCP, một đường đi thực tế thường là:

~~~mermaid
flowchart LR
    SRC["Java source / Git"] --> BUILD["Maven/Gradle + tests"]
    BUILD --> OCI["Docker/OCI build"]
    OCI --> AR["Artifact Registry\nimage@sha256:digest"]
    AR --> DEP["GKE Deployment"]
    CONF["ConfigMap\nnon-secret settings"] --> DEP
    SEC["Secret Manager / identity"] -. "Credentials riêng" .-> DEP
    DEP --> POD["Java app Pods"]
    SVC["Service ClusterIP"] --> POD
    CL["Client / Ingress / Gateway"] --> SVC
~~~

**Điểm khác giữa Nginx lab và Java app:** Nginx nghe cổng 80 và phục vụ file index.html ngay khi volume thay đổi. Một Java/Spring Boot service thường nghe cổng **8080** (hoặc cổng do app đặt), đọc config khi startup, quản lý DB pool/queue consumers và cần health endpoints riêng.

### 12.1. Ví dụ thay Container spec cho Java API

Giả sử CI đã publish image thật tới Artifact Registry và ứng dụng có endpoint **/actuator/health/liveness** và **/actuator/health/readiness** được cấu hình. Phần Container spec có thể như sau:

~~~yaml
containers:
  - name: checkout-api
    image: asia-southeast1-docker.pkg.dev/PROJECT_ID/APP_REPO/checkout-api@sha256:ACTUAL_DIGEST
    ports:
      - name: http
        containerPort: 8080
    env:
      - name: APP_GREETING
        valueFrom:
          configMapKeyRef:
            name: checkout-config
            key: APP_GREETING
    resources:
      requests:
        cpu: "500m"
        memory: "1Gi"
      limits:
        cpu: "1000m"
        memory: "2Gi"
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      failureThreshold: 30
      periodSeconds: 5
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http
      periodSeconds: 5
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 10
~~~

**Đây là trích đoạn, không phải manifest hoàn chỉnh.** Bạn cần tạo ConfigMap **checkout-config**, thay path image bằng digest thật, có Pod/Deployment metadata và labels tương ứng. Endpoints Actuator phải **được ứng dụng cấu hình và đã kiểm thử**: nếu Spring Boot không expose những endpoint đó hoặc app chạy cổng khác, readiness/liveness sẽ fail và Pod có thể liên tục restart. Lựa chọn CPU/memory phải dựa trên profiling JVM, GKE mode và policy; không copy con số ví dụ vào production không qua kiểm tra.

### 12.2. Service đi kèm Java app

Khi Java container thực sự nghe **8080**, Service có thể dùng:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: checkout-api
  namespace: gke-lab
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: checkout-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
~~~

Ở đây client trong cluster gọi **checkout-api:80**, Service chuyển tới container **8080**. Giá trị này **khác** lab Nginx **Service port 8080 → targetPort 80**. Khi đổi image, luôn kiểm tra Service mapping và probes; một Pod Ready nhưng Service targetPort sai vẫn khiến request lỗi.

### 12.3. Private image và imagePull principal

Nếu image nằm trong Artifact Registry private repository:

- Repository phải tồn tại và chứa **đúng image digest**.
- Identity dùng để kéo image, thường liên quan **node service account** hoặc **GKE service agent/cơ chế được loại cluster hỗ trợ**, phải có quyền **Artifact Registry Reader** phù hợp.
- Với repository khác project, cần cấp IAM ở **repository nguồn** cho principal thực sự kéo image.
- Nếu image pull failed, kiểm tra **ImagePullBackOff, 401/403** và quyền node trước khi cấp quyền Editor/Owner.
- **Workload Identity Federation for GKE** dùng cho Pod gọi Google APIs sau khi chạy, không tự giải quyết mọi lỗi image pull; đường image pulling có cơ chế danh tính riêng.
- Pin bằng **digest** để tránh tag bị push đè làm các Pod khác nhau chạy bản không đồng nhất.

### 12.4. Runtime credentials khác image registry credentials

Một Java app sau khi chạy có thể gọi Cloud SQL, Pub/Sub hoặc Cloud Storage. Nên dùng **Workload Identity Federation for GKE** và service account có quyền tối thiểu, không nhúng JSON key vào ConfigMap, image hoặc environment manifest. Đường kéo image có thể sử dụng identity khác; cần thiết kế IAM riêng cho **pull artifact** và **runtime API access**.

Không dùng một service account quyền Admin cho cả build, image pull, Pod runtime và dọn hạ tầng. Các quyền này thuộc những giai đoạn và ranh giới khác nhau.

## 13. Bảo mật Deployment, Service và ConfigMap

### 13.1. Giới hạn quyền Kubernetes API

Khi có quyền truy cập GKE cluster, không đồng nghĩa người dùng cần quyền quản trị mọi namespace:

- **Namespace + Role/RoleBinding** để giới hạn ai được get/list/create/update Deployments, Services và ConfigMaps.
- **Kubernetes ServiceAccount** để định danh Pod với API server khi cần.
- Với app không gọi Kubernetes API, có thể tắt việc tự gắn API token bằng **automountServiceAccountToken: false** trong Pod spec.
- **Google Cloud IAM** vẫn áp dụng ở project/cluster và Google APIs; Kubernetes RBAC không thay IAM cho Cloud Storage hoặc Cloud SQL.
- Không cho dev environment được sửa production namespaces qua một shared ClusterRoleBinding quá rộng.

Ví dụ xem quyền hiện tại (chỉ đọc):

~~~bash
kubectl auth can-i get deployments -n "$NAMESPACE"
kubectl auth can-i create configmaps -n "$NAMESPACE"
kubectl auth can-i patch deployments -n "$NAMESPACE"
kubectl auth can-i create services -n "$NAMESPACE"
~~~

Nếu trả **no**, cần người quản trị cấp quyền phù hợp theo vai trò công việc. Không tự thêm cluster-admin binding để bỏ qua bảo vệ.

### 13.2. ConfigMap không phải công cụ quản lý bí mật

| Loại dữ liệu | Nơi nên đặt | Lý do |
|---|---|---|
| Log level, feature flag không nhạy cảm | ConfigMap | App config versioned, dễ đọc |
| Hostname DB không kèm credential | ConfigMap hoặc application config | Không bí mật tự thân theo policy |
| DB password, API token, private key | Secret Manager hoặc Kubernetes Secret theo thiết kế | Yêu cầu hạn chế truy cập, mã hóa, rotation |
| Image digest và artifact version | Deployment/GitOps manifest | Truy xuất và rollback |
| Tệp lớn hoặc dataset | Cloud Storage / volume thích hợp | ConfigMap giới hạn dung lượng |
| Cấu hình chứa PII/secret | Không dùng ConfigMap | Bảo vệ dữ liệu và quyền đọc |

Kubernetes Secret không tự biến mọi hệ thống thành an toàn tuyệt đối: phải thiết kế RBAC, encryption at rest, audit, đường truy cập qua CSI/Secret Manager khi phù hợp và rotation. Không in giá trị Secret vào logs hoặc commit vào Git.

### 13.3. Image và container runtime

Các cải tiến production thường gồm:

- Dùng image được kiểm tra CVE/SBOM và **digest cụ thể**.
- Dùng user không phải root khi image hỗ trợ.
- Tắt privilege escalation và quyền Linux không cần thiết.
- Cân nhắc **readOnlyRootFilesystem** nếu ứng dụng/container có thể chạy với các mount tạm phù hợp.
- Dùng **seccomp/runtime default** và securityContext theo khả năng GKE.
- Cấu hình **resource requests/limits** dựa trên tải.
- Không dùng **privileged: true** hoặc hostPath tùy tiện để giải quyết lỗi access.
- Kiểm soát supply-chain bằng Artifact Registry và policy như Binary Authorization nếu tổ chức yêu cầu.

**Không áp dụng securityContext tùy tiện lên Nginx lab:** image mặc định có thể cần quyền ghi các tệp/cache runtime hoặc port đặc thù. Cần test image và điều chỉnh container trước khi bật non-root/read-only, không copy các giá trị mà app chưa hỗ trợ.

### 13.4. Network exposure và NetworkPolicy

Service **ClusterIP** chỉ tạo endpoint nội bộ theo khả năng cluster; nó **không phải một firewall rule** chặn mọi Pod khác. Mặc định các Pod có thể kết nối với nhau tùy mạng/policy, kể cả qua namespaces.

Nếu tổ chức cần cô lập, sử dụng **Kubernetes NetworkPolicy** trên GKE dataplane/network policy enforcement được hỗ trợ, hoặc chính sách mạng nâng cao khác. Kiểm tra:

- Ingress từ những namespace/workload nguồn nào.
- Egress tới Cloud SQL, DNS, Pub/Sub/Google APIs.
- Load balancer health checks/proxy IPs.
- Lưu lượng hệ thống/kube-dns.
- GKE Dataplane V2 và các khác biệt hỗ trợ theo cluster mode/version.

Một **default-deny NetworkPolicy** thiếu các rule cho DNS và health checks có thể làm cả ứng dụng mất kết nối. Triển khai theo từng giai đoạn và kiểm chứng cả allowed lẫn denied flows.

### 13.5. Kiểm soát kết nối tới database

Nếu Java app dùng Cloud SQL:

1. Xác định private connectivity/Cloud SQL connector hoặc Auth Proxy theo kiến trúc.
2. Kiểm tra Pod egress và đường mạng GKE → Cloud SQL.
3. Cấp IAM/DB permissions tối thiểu.
4. Quản lý secret/credentials có rotation.
5. Đặt readiness probe phản ánh khả năng phục vụ nghiệp vụ; tránh biến liveness thành phụ thuộc không ổn định vào DB.
6. Kiểm soát số kết nối DB khi scale replicas từ 2 lên 20.

Service **checkout-api** đang hoạt động chỉ chứng minh phía GKE có endpoint ứng dụng, không tự cấp quyền database hoặc mở mạng tới on-premises.

## 14. Troubleshooting theo từng trạng thái và lớp

### 14.1. Những lệnh kiểm tra quan trọng

~~~bash
# Tổng quan objects trong namespace.
kubectl get deployments,replicasets,pods,services,configmaps \
  -n "$NAMESPACE"

# Chi tiết Deployment, điều kiện rollout, events.
kubectl describe deployment web-demo -n "$NAMESPACE"

# Chi tiết Pod và events, chọn tên Pod thật.
POD_NAME="REPLACE_WITH_POD_NAME"
kubectl describe pod "$POD_NAME" -n "$NAMESPACE"

# Logs container đang chạy.
kubectl logs "$POD_NAME" -c web -n "$NAMESPACE" --tail=100

# Khi container restart và log trước vẫn còn.
kubectl logs "$POD_NAME" -c web -n "$NAMESPACE" \
  --previous --tail=100

# Sự kiện trong namespace.
kubectl get events -n "$NAMESPACE" \
  --sort-by=.metadata.creationTimestamp

# Service và endpoints.
kubectl describe service web-demo -n "$NAMESPACE"
kubectl get endpointslices -n "$NAMESPACE" \
  -l kubernetes.io/service-name=web-demo
~~~

**Không gửi toàn bộ output logs có chứa token, private URLs hoặc dữ liệu khách hàng vào ticket công khai.** Đặc biệt tránh dùng **kubectl get secrets -o yaml** để “kiểm tra config” nếu không có quyền và yêu cầu cụ thể.

### 14.2. Ma trận triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| **ImagePullBackOff / ErrImagePull** | Image không tồn tại, tag sai, private registry IAM, network/proxy | Pod events, image ref, Artifact Registry IAM |
| **CreateContainerConfigError** | ConfigMap hoặc key tham chiếu không tồn tại | kubectl describe pod, namespace và ConfigMap |
| **CrashLoopBackOff** | App crash, config sai, liveness restart, permissions | kubectl logs --previous, describe, probe |
| **Pending / Unschedulable** | Không đủ CPU/memory, quota, Autopilot restrictions, taints | Pod events, requests, node capacity |
| **Running nhưng 0/1 Ready** | Readiness path/port sai, app chưa sẵn sàng | Pod conditions, probe, application logs |
| **Deployment 0/2 Ready** | Pod chưa lên hoặc readiness false | Deployment/ReplicaSet/Pod describe |
| **Service có ClusterIP nhưng không kết nối được** | Selector sai, không có Ready endpoints, targetPort sai | EndpointSlice, labels, port mapping |
| **Port-forward được nhưng client Pod timeout** | Service data plane/DNS/NetworkPolicy khác đường port-forward | Test từ client Pod, policy, DNS |
| **Service DNS không resolve** | Sai namespace, CoreDNS/cấu hình DNS, network policy | nslookup/dig từ Pod, kiểm tra tên FQDN |
| **ConfigMap file chưa đổi** | Kubelet sync/cache trễ, mount subPath hoặc app cache | Thời gian cập nhật, volumeMounts, cat file |
| **Env var ConfigMap vẫn cũ** | Pod chưa restart | Kiểm tra Pod age, rollout restart |
| **Rollout stuck** | Image pull, probes, capacity, maxSurge hoặc invalid config | rollout status + events |
| **OOMKilled** | JVM memory/limits thấp, heap/native memory quá lớn | Container lastState, metrics, JVM memory |
| **CPU throttling/latency** | CPU limits quá thấp hoặc quá tải | CPU metrics, p95 latency, profiling |
| **LoadBalancer EXTERNAL-IP Pending** | Quota, provisioning, IAM, subnet/network hoặc controller | describe service, GKE/load balancer events |
| **HTTP 401/403** | IAM/app auth, không nhất thiết firewall | Request logs, JWT/audience/principal |
| **Load balancer backend unhealthy** | Firewall/health check/probe/service mismatch | Backend health, LB/GKE controller, logs |
| **ConfigMap update thành công nhưng app không đổi** | App chỉ đọc file lúc startup hoặc env frozen | App behavior, restart/reload policy |
| **Pod mới pull khác image cùng tag** | Mutable tag + pull policy/cache | Resolved imageID/digest và release pipeline |

### 14.3. Sơ đồ xử lý vấn đề Service không đáp ứng

~~~mermaid
flowchart TD
    REQ["Không gọi được web-demo:8080"] --> CONTEXT{"Đúng context + namespace?"}
    CONTEXT -- "Không" --> FIX1["Xác minh kubeconfig và -n"]
    CONTEXT -- "Có" --> SVC{"Service tồn tại và selector đúng?"}
    SVC -- "Không" --> FIX2["Sửa Service manifest/labels"]
    SVC -- "Có" --> EP{"Có EndpointSlices Ready?"}
    EP -- "Không" --> POD["Kiểm tra Pod status + readiness + image pull"]
    EP -- "Có" --> PORT{"port 8080 → targetPort 80 đúng?"}
    PORT -- "Không" --> FIX3["Sửa mapping/probe"]
    PORT -- "Có" --> NET["Kiểm tra DNS, NetworkPolicy, VPC/LB path"]
    NET --> APP["Kiểm tra HTTP response, app logs và auth"]
~~~

### 14.4. Đừng sửa một tầng bằng cách mở rộng quyền tầng khác

- Khi Pod **ImagePullBackOff**, không mặc nhiên mở firewall 0.0.0.0/0 ingress hoặc cấp roles/owner.
- Khi Service selector không khớp, không tăng replicas lên 20 để “thử”.
- Khi ConfigMap key thiếu, không xóa cluster để tạo lại.
- Khi Java API trả **HTTP 403**, kiểm tra auth/IAM trước khi thay đổi VPC network.
- Khi Pod Pending do tài nguyên, xem requests, quota và Autopilot compute class, không bỏ limits hoặc chuyển sang privileged mode bừa bãi.

## 15. Quan sát độ tin cậy và vận hành Deployment

### 15.1. Tín hiệu nên quan sát

| Tín hiệu | Ý nghĩa |
|---|---|
| Deployment desired/available/unavailable replicas | Sức khỏe rollout và khả năng phục vụ |
| Pod Ready/NotReady và restart count | Khởi động, probes, crash |
| CPU/memory/ephemeral storage usage | Sizing và lỗi OOM/eviction |
| Request rate, p50/p95/p99 latency, HTTP errors | Chất lượng thực tế của API |
| Service endpoints, DNS resolution | Service discovery và network readiness |
| Rollout duration và version/digest | Phát hành có kiểm soát |
| ConfigMap version/checksum | Truy xuất thay đổi cấu hình |
| Image pull errors | Registry IAM/network/artifact retention |
| GKE cluster/node status và maintenance | Nền tảng sẵn sàng |
| Cost theo namespace/workload/project khi có tagging/monitoring | Phân bổ chi phí và FinOps |

GKE tích hợp **Cloud Logging và Cloud Monitoring** theo cấu hình cluster. Metrics Pod có thể xem với **kubectl top pods** nếu metrics API được triển khai và sẵn có; không mặc định mọi cluster đã cung cấp toàn bộ metrics từ đầu.

~~~bash
# CHỈ ĐỌC — metrics khi cluster có Metrics API.
kubectl top pods -n "$NAMESPACE"
kubectl top nodes

# CHỈ ĐỌC — trạng thái rollout.
kubectl get deployment web-demo -n "$NAMESPACE" \
  -o jsonpath='{.status.readyReplicas}/{.spec.replicas}{"\n"}'

# CHỈ ĐỌC — nhật ký ứng dụng mẫu.
kubectl logs deployment/web-demo -n "$NAMESPACE" \
  --all-containers=true --tail=100
~~~

**Không dùng việc cả hai Pod Ready làm bằng chứng SLO cuối cùng.** Health probe chỉ đánh giá điều kiện đơn giản mà bạn cấu hình; cần synthetic checks, load tests và observability của request nghiệp vụ.

### 15.2. PodDisruptionBudget và zone distribution

Đối với ứng dụng cần availability cao, cân nhắc:

- **PodDisruptionBudget (PDB)** để giới hạn gián đoạn tự nguyện theo khả năng Kubernetes hỗ trợ.
- **Topology spread constraints** hoặc anti-affinity để tránh tất cả Pod tập trung vào một node/zone.
- Đủ replicas và tài nguyên, readiness/startup/termination handling.
- Cấu hình **terminationGracePeriodSeconds** và graceful shutdown trong Java.
- Backend DB chịu được các đợt kết nối lại khi rolling update.
- **Regional cluster** hoặc thiết kế đa vùng phù hợp SLO.

PDB **không ngăn mọi loại sự cố** (node chết, zone outage, OOMKilled, app crash), và không thay thế backup. Với maxUnavailable=0, capacity không đủ có thể làm rollout kéo dài; cần cân bằng SLO và chi phí.

### 15.3. Java shutdown và retry

Khi Deployment scale down hoặc rollout, Pod nhận tín hiệu termination. Java/Spring Boot nên:

1. Dừng nhận request mới và chuyển readiness false/cho phép draining phù hợp.
2. Hoàn tất request/queue message trong giới hạn thời gian.
3. Đóng DB pool, flush logs/metrics và giải phóng resources.
4. Xử lý retry/idempotency cho request đã timeout ở client.
5. Không coi **terminationGracePeriodSeconds** là bảo đảm ứng dụng luôn hoàn tất mọi tác vụ dài.

Không ghi trạng thái transaction chỉ trong RAM hoặc emptyDir của Pod rồi kỳ vọng Pod mới sẽ tiếp tục chính xác khi rollout.

## 16. Chi phí: Deployment/Service/ConfigMap không có cùng mô hình tính phí

Một số tài nguyên Kubernetes là object control plane, nhưng việc chúng yêu cầu hạ tầng Google Cloud có thể tạo chi phí.

| Thành phần | Chi phí hoặc hệ quả cần tính |
|---|---|
| **GKE cluster** | Phí quản lý cluster và điều kiện miễn/giảm phí theo bảng giá hiện hành |
| **Autopilot Pods** | Mô hình tính phí theo cấu hình/tier, resource requests và điều kiện Autopilot được áp dụng |
| **Standard nodes** | Compute Engine node VM, boot disks, GPUs/Local SSD nếu có |
| **Service ClusterIP** | Không tự tạo external L4 load balancer; Pod/cluster vẫn có chi phí |
| **Service LoadBalancer** | Google Cloud load balancer, forwarding rules/IP, network transfer và tài nguyên phụ trợ |
| **ConfigMap** | Không tính như một Cloud Storage bucket riêng; tiêu thụ tài nguyên API/control plane và giới hạn Kubernetes |
| **Container image** | Artifact Registry storage, image pull/transfer khi áp dụng |
| **Cloud Logging/Monitoring** | Dữ liệu log, metric, retention vượt điều kiện tính giá |
| **Network egress** | Cross-region/outbound traffic theo cấu hình VPC và dịch vụ |
| **Persistent storage** | PersistentVolume/disk, snapshots và backups |
| **Cloud NAT/Public IPv4** | Tùy network topology và địa chỉ sử dụng |

### 16.1. Vì sao resource requests ảnh hưởng chi phí?

Trong lab, mỗi Pod khai báo CPU request **500m** và memory **512Mi**. Với **2 replicas**, tổng requests của workload trước khi GKE điều chỉnh là **1 vCPU và 1 GiB memory**. Chưa kể resource limits, overhead, workload khác và cách tính phí cluster.

Autopilot có thể áp dụng **minimum/default và CPU:memory ratios** theo compute class, sửa request hoặc từ chối Pod khi vượt giới hạn. Với Standard, requests ảnh hưởng scheduling và quyết định node capacity; phí thực tế thường gắn với node resources được provision. Không được tính hóa đơn bằng công thức “số Pod x memory limit” nếu chưa xác minh billing mode và cấu hình.

Đo request và usage, cân đối:

- Requests quá thấp: OOM, throttling, eviction hoặc Pod không ổn định.
- Requests quá cao: chi phí tăng, khó schedule và lãng phí capacity.
- Limits quá chặt: Java/JVM gặp OOMKilled dù average usage có vẻ thấp.
- Replicas quá ít: lỗi node/rollout có thể gây ngừng dịch vụ.
- Replicas quá nhiều: DB connection count và downstream load tăng.

### 16.2. Một phép tính minh họa

Giả sử một môi trường lab cần **hai Pod** chạy 8 giờ, mỗi Pod request **0,5 vCPU và 0,5 GiB**. Mức tiêu thụ giả định, trước khi áp các quy tắc cụ thể của Autopilot, là:

~~~text
Tổng CPU-request-hours:
2 Pods × 0,5 vCPU × 8 h = 8 vCPU-hours

Tổng memory-request-hours:
2 Pods × 0,5 GiB × 8 h = 8 GiB-hours
~~~

Đây **không phải hóa đơn Google Cloud**. Giá hiện hành, minimums, hardware/compute class, cluster fee, vùng, network và mức điều chỉnh resources của Autopilot quyết định phí thật. Dùng **Cloud Billing Reports/Cost table** và metric usage để đối chiếu. Nếu đã tạo LoadBalancer, phí có thể tiếp tục dù workload ngừng nhận request.

### 16.3. Quy trình tối ưu

1. Chọn đúng **cluster/mode** và dùng cluster học tập sẵn có khi được phép.
2. Dùng **ClusterIP** khi không cần public/private L4 load balancer bên ngoài cluster.
3. Right-size resource requests/limits dựa trên usage và health.
4. Tắt/xóa tài nguyên lab đúng quyền sở hữu sau khi học xong.
5. Giảm log noise nhưng không vô hiệu hóa security/audit cần thiết.
6. Xem Artifact Registry images, unused disks và network egress.
7. Theo dõi costs theo project/workload/namespace bằng hệ thống phân bổ được tổ chức hỗ trợ.
8. Kiểm thử rollback và readiness để không “tiết kiệm” bằng cách hy sinh tính sẵn sàng.

## 17. Case study — Từ Java container đến dịch vụ checkout trên GKE

### 17.1. Bối cảnh

Một công ty vận hành **checkout-api** với bốn yêu cầu:

- Có hai bản sao ở trạng thái Ready để chịu lỗi một Pod.
- Các services trong cluster gọi qua **checkout-api.gke-prod.svc.cluster.local** (hoặc cluster domain thực tế).
- **Cấu hình không bí mật** như log level và feature flag được đưa vào ConfigMap.
- Database credentials được quản lý riêng, image đến từ Artifact Registry và có thể rollback theo digest.

Pipeline dự kiến:

~~~mermaid
flowchart LR
    C["Git commit"] --> TEST["Java tests"]
    TEST --> B["Build image"]
    B --> AR["Artifact Registry\nimage digest"]
    AR --> D["Deployment checkout-api"]
    CM["ConfigMap\nlog level, feature flags"] --> D
    D --> P["Replicas: checkout-api Pods"]
    SVC["ClusterIP Service\ncheckout-api:80"] --> P
    CL["Orders / frontend API"] --> SVC
    DB["Cloud SQL / durable database"] <--> P
~~~

### 17.2. Bước thiết kế

| Lớp | Quyết định | Lý do |
|---|---|---|
| Image | Digest bất biến đã kiểm tra | Truy vết và rollback chính xác |
| Deployment | 2+ replicas, RollingUpdate, probes | Duy trì dịch vụ khi Pod bị thay |
| Service | ClusterIP | Chỉ cần consumer nội bộ cluster |
| ConfigMap | APP_FEATURE_X, LOG_LEVEL | Không chứa secrets |
| Auth | Workload Identity Federation for GKE | Không cần service account key trong image |
| Data | Cloud SQL hoặc storage bền vững | Pod filesystem có thể mất |
| Security | Namespace RBAC, NetworkPolicy theo nhu cầu, least privilege | Giới hạn tác động |
| Observability | Readiness, error rate, latency, DB connections | Đo sức khỏe nghiệp vụ |
| Rollback | Manifest image digest + ConfigMap version | Khôi phục image và cấu hình nhất quán |

### 17.3. Sự cố A — Service không có endpoint

Nhóm deploy Deployment với Pod labels **app=checkout-api**, nhưng Service selector dùng **app=checkout**. Service vẫn được tạo và DNS vẫn phân giải, song EndpointSlice không chứa Pod Ready phù hợp.

**Điều tra:** đối chiếu **kubectl get pods --show-labels** với **kubectl describe service**, rồi sửa selector/labels thống nhất qua Git. Không tạo thêm LoadBalancer, không tăng replicas và không đổi VPC firewall để giải quyết lỗi label.

### 17.4. Sự cố B — Cập nhật ConfigMap nhưng feature flag không đổi

Nhóm đổi ConfigMap **FEATURE_CHECKOUT_V2=true**, nhưng Java app đọc giá trị qua environment variable ở startup. Các Pod cũ vẫn giữ giá trị cũ.

**Điều tra:** kiểm tra Pod age, env và ConfigMap version; dùng GitOps/rollout restart hoặc tạo ConfigMap version mới và thay Pod template. Nếu app được thiết kế hot reload từ file, vẫn phải xác minh ứng dụng thực sự theo dõi file. Không khẳng định “Kubernetes apply ConfigMap là mọi app tự nhận config mới”.

### 17.5. Sự cố C — Rollout 0/2 Ready sau đổi image

Bản image mới sử dụng Java server ở port **8080**, nhưng Deployment readiness probe vẫn gọi port **80**. Pods được tạo nhưng không Ready; Service không chuyển traffic sang Pods mới. Với **maxUnavailable=0**, các Pods cũ có thể được giữ trong khi rollout bị chặn nếu chưa bị ảnh hưởng bởi một thay đổi khác.

**Điều tra:** describe Pod và Deployment; kiểm tra resolved imageID, container ports, readiness path, application logs. Sửa manifest cổng/probe rồi rollout lại, hoặc rollback template nếu cần. Không xóa hàng loạt Pod cũ trước khi có bản mới healthy.

### 17.6. Sự cố D — Scale lên 10 replicas khiến DB quá tải

Deployment scale thành công, Service có 10 endpoint nhưng mỗi Java Pod mở pool tối đa 30 connections, tổng tải có thể tới 300 DB connections trước khi tính service khác.

**Điều tra:** xem metrics DB, pool settings, retry, timeout và HPA; điều chỉnh connection pools và capacity database, không coi tăng Pod luôn là tăng throughput tuyến tính.

### 17.7. Tiêu chí nghiệm thu production

Một phát hành chỉ được xem là đạt khi:

1. Image digest và metadata build xác minh được.
2. Deployment đạt available replicas dự kiến.
3. Service có endpoints Ready và DNS hoạt động đúng namespace.
4. ConfigMap/Secret version phù hợp với release.
5. Functional test đi qua đường Service/Ingress thực, không chỉ port-forward.
6. IAM/RBAC/network exposure giới hạn theo policy.
7. Latency/error rate/DB connections không vượt ngưỡng SLO.
8. Có bản rollback và dữ liệu bên ngoài Pod không bị ảnh hưởng.
9. Chi phí/khả năng scale đã được đánh giá.
10. Pipeline/GitOps lưu được manifest chính xác cho lần triển khai sau.

## 18. Dọn dẹp lab có kiểm soát

**Chỉ xóa tài nguyên mà bạn tạo và có quyền sở hữu.** Không xóa cả namespace hoặc GKE cluster dùng chung vì một bài học. Đặc biệt, Service type LoadBalancer có thể tạo tài nguyên hạ tầng Google Cloud: nên xóa Service trước, kiểm tra load balancer đã được thu hồi rồi mới xem các phụ thuộc khác.

### 18.1. Kiểm kê trước dọn

~~~bash
# CHỈ ĐỌC — xác minh kubeconfig context.
kubectl config current-context

# CHỈ ĐỌC — tất cả object chính trong namespace lab.
kubectl get deployments,services,configmaps,pods \
  -n "$NAMESPACE"

kubectl get endpointslices -n "$NAMESPACE" \
  -l kubernetes.io/service-name=web-demo
~~~

Nếu đã tạo thêm **web-demo-public** hoặc **web-demo-internal**, trước khi dọn cần xác nhận đó là Service của lab, không có client đang phụ thuộc:

~~~bash
# CHỈ ĐỌC — chỉ xem, không xóa.
kubectl get services -n "$NAMESPACE" -o wide
~~~

### 18.2. Xóa đúng ba manifest đã tạo

~~~bash
# THAY ĐỔI / XÓA TÀI NGUYÊN — chỉ dùng với lab đúng context.
# Xóa Service trước để không tiếp tục expose endpoint.
kubectl delete -f 03-service.yaml

# Xóa Deployment và các Pod được controller quản lý.
kubectl delete -f 02-deployment.yaml

# Sau khi không còn Pod tham chiếu, xóa ConfigMap lab.
kubectl delete -f 01-configmap.yaml

# CHỈ ĐỌC — xác minh không còn các object đã tạo.
kubectl get deployments,services,configmaps,pods \
  -n "$NAMESPACE"
~~~

Trong trường hợp có **public/internal LoadBalancer Service**, cần **xóa riêng Service đó bằng manifest/đúng tên** và xác minh tài nguyên load balancer được giải phóng. Không tự xóa forwarding rules/firewall resources ở Console nếu chúng đang được GKE controller quản lý hoặc chia sẻ với workload khác.

### 18.3. Namespace và cluster

Namespace **gke-lab** chỉ nên xóa nếu được tạo riêng cho bài học và không còn workload của người khác:

~~~bash
# THAY ĐỔI — chỉ khi namespace thật sự dành riêng cho lab.
kubectl delete namespace gke-lab
~~~

Nếu bạn đã **tạo một GKE cluster hoàn toàn riêng chỉ để thực hành**, việc xóa cluster có thể giúp dừng phí hạ tầng. Tuy nhiên, thao tác này **rất rủi ro** nếu cluster còn workload/disk/IP của các nhóm khác. Cần xác minh project, cluster ID, location, workload ownership và quyết định giữ dữ liệu trước khi triển khai lệnh xóa thông qua quy trình change approval.

Không đưa lệnh **delete cluster** hàng loạt vào tài liệu để tránh người học sao chép không kiểm soát. Dọn **project** hoặc billing account không nằm trong phạm vi ba đối tượng của bài này.

### 18.4. Hậu kiểm chi phí

- Xem namespace/Service/Deployment đã biến mất đúng dự kiến.
- Kiểm tra có LoadBalancer, external IP, PersistentVolume hay Compute Engine resources phát sinh thêm không.
- Nếu tạo cluster riêng, bảo đảm kế hoạch xóa/giữ đã được thực hiện có phê duyệt.
- Dùng Billing Reports theo Service/SKU sau khoảng trễ ghi nhận.
- Không xóa Artifact Registry repository/digest vì lab nếu đang dùng chung với pipeline khác.

## 19. Bài tập và câu hỏi tự kiểm tra

### 19.1. Bài tập A — Đọc một Service có port mapping

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: billing-api
  namespace: gke-lab
spec:
  type: ClusterIP
  selector:
    app: billing
  ports:
    - port: 9000
      targetPort: 8080
      protocol: TCP
~~~

**Câu hỏi:**

1. Client trong cùng namespace phải gọi Service ở port nào?
2. Container billing phải lắng nghe port nào?
3. Nếu Pod mang label **app=billing-v2** thì Service có endpoint không?
4. Nếu Deployment có 3 replicas nhưng chỉ 1 Pod Ready, Service bình thường đưa traffic tới mấy Pod?
5. Service này có public IP không?

**Đáp án:** (1) 9000. (2) 8080. (3) Không khớp selector nên không chọn được Pod đó. (4) Thường chỉ tới 1 endpoint Ready; còn tùy cấu hình publishNotReadyAddresses và các trường hợp đặc biệt. (5) Không, ClusterIP nội bộ.

### 19.2. Bài tập B — Cập nhật ConfigMap

Một Deployment dùng ConfigMap theo hai cách:

- **LOG_LEVEL** qua **env.valueFrom.configMapKeyRef**.
- **app.yaml** qua **volumeMounts** bình thường, không dùng subPath.

Bạn sửa ConfigMap và apply thành công. Hãy trả lời:

1. LOG_LEVEL trong container cũ có đổi ngay không?
2. app.yaml mount có thể đổi không? Có độ trễ không?
3. Nếu Java app chỉ đọc app.yaml lúc startup, tính năng sẽ thay đổi không?
4. Nếu file mount bằng subPath thì sao?
5. Làm gì để rollout có thể tái tạo đúng image + config sau một tháng?

**Đáp án định hướng:** (1) Không. (2) Có thể được kubelet cập nhật eventual. (3) Không nếu app không hot reload. (4) Không tự cập nhật qua subPath. (5) Dùng image digest và ConfigMap version/checksum trong Pod template/GitOps để tạo revision có thể kiểm chứng.

### 19.3. Bài tập C — Rollout stuck

Deployment có **replicas=2, maxSurge=1, maxUnavailable=0**. Khi cập nhật image, Pod mới bị **ImagePullBackOff**. Hãy:

- Nêu điều kiện khiến rollout không tiến triển.
- Chỉ ra ba lệnh kubectl read-only để xem lỗi.
- Cho biết có nên xóa hai Pod cũ để “ép cập nhật” không.
- Đề xuất cách phục hồi nhanh với điều kiện revision cũ còn tồn tại.

**Đáp án định hướng:** Pod mới không có image để chạy nên không Ready; kiểm tra **kubectl describe pod**, **kubectl describe deployment**, **kubectl rollout status** và events. Không tự xóa Pod cũ; sửa image path/IAM hoặc **kubectl rollout undo** và kiểm tra lại.

### 19.4. Bài tập D — GKE và Cloud Run

Ứng dụng Java cần scale theo HTTP requests, không có yêu cầu Kubernetes API, service discovery đặc thù hay controller tùy chỉnh. Hãy so sánh triển khai với **GKE Deployment/Service/ConfigMap** và **Cloud Run** theo vận hành, scale, network, CI/CD, IAM và chi phí.

**Định hướng:** GKE phù hợp khi cần hệ sinh thái Kubernetes, nhiều workloads/protocols, khả năng kiểm soát scheduling/networking và các đối tượng declarative. Cloud Run có thể giảm độ phức tạp quản lý cluster với workload HTTP/event phù hợp; không nên chọn GKE chỉ vì đã biết viết Deployment YAML.

### 19.5. Câu hỏi nhanh

1. Deployment có tự tạo Service không?
2. Service có tăng replicas không?
3. ConfigMap có phải Secret an toàn để lưu database password không?
4. Vì sao Pod IP không phải địa chỉ nên hardcode trong client?
5. LoadBalancer Service có thể phát sinh phí dù chưa có request không?
6. kubectl apply báo created có chứng minh Pod Ready không?
7. Chạy port-forward thành công có chứng minh external load balancer hoạt động không?
8. Kubernetes rollout undo có tự rollback dữ liệu database hoặc ConfigMap đã sửa ngoài Deployment không?
9. Tại sao nên pin image digest?
10. Tại sao Service selector và Pod labels phải thống nhất?

**Đáp án ngắn:** (1) Không. (2) Không. (3) Không. (4) Pod bị thay và IP thay đổi. (5) Có. (6) Không. (7) Không. (8) Không. (9) Định danh chính xác artifact được chạy. (10) Để Service chọn đúng endpoints.

### 19.6. Mẫu nghiệm thu lab

~~~text
PROJECT_ID:
CLUSTER:
LOCATION:
KUBECTL_CONTEXT:
NAMESPACE:
CONFIGMAP_NAME / KEYS:
DEPLOYMENT_NAME / DESIRED_REPLICAS:
PODS_READY:
IMAGE_REFERENCE / IMAGE_ID:
SERVICE_NAME / TYPE / PORT / TARGET_PORT:
ENDPOINTSLICES:
HTTP_STATUS / RESPONSE_BODY:
CONFIGMAP_VOLUME_UPDATE:
ENV_VAR_BEFORE_RESTART:
ENV_VAR_AFTER_RESTART:
ROLLOUT_REVISION / RESULT:
LOGS / EVENTS:
LOADBALANCER_CREATED?:
COST_RESOURCES_CREATED:
CLEANUP_RESULT:
OWNER / OBSERVATION_TIME:
OPEN_ISSUES:
~~~

Điền từ **kết quả đã thực sự quan sát**, không đánh dấu PASS chỉ vì manifest hợp lệ về cú pháp. Không ghi credentials, Kubernetes tokens hoặc secrets vào biên bản.

## 20. Tài liệu tham khảo chính thức

Các nguồn nên dùng để đối chiếu API, cú pháp và các thay đổi của GKE/Kubernetes:

- [GKE: Deploy an app to a GKE cluster](https://docs.cloud.google.com/kubernetes-engine/docs/deploy-app-cluster)
- [GKE: Create an Autopilot cluster](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster)
- [GKE: Autopilot overview](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview)
- [GKE: Resource requests in Autopilot](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-resource-requests)
- [GKE: Exposing applications using Services](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/exposing-apps)
- [GKE: About LoadBalancer Services](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/service-load-balancer)
- [Kubernetes: Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes: Services](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes: ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes: Configure a Pod to use a ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/)
- [Kubernetes: Update a Deployment](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/)
- [GKE: Workload Identity Federation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [GKE: Use Artifact Registry images](https://docs.cloud.google.com/artifact-registry/docs/integrate-gke)
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing)

GKE versions, Autopilot constraints, load balancer implementation, Kubernetes API behavior và chi phí có thể được cập nhật. Khi làm thực tế, hãy đối chiếu tài liệu với **cluster mode/version, Google Cloud project, region, image architecture, IAM và network configuration** của chính môi trường.

---

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** bài học này sử dụng kiến thức về **project/IAM, VPC networking, container images trong Artifact Registry và Compute Engine/GKE** để triển khai ứng dụng có nhiều bản sao. **Deployment** duy trì Pod và rollout, **Service** cung cấp endpoint ổn định, **ConfigMap** tách cấu hình không bí mật khỏi image. Khi mở rộng sang **Cloud SQL, Cloud Storage, Pub/Sub, CI/CD và Cloud Monitoring**, nguyên tắc vẫn là **đúng image và cấu hình → đúng Pod/labels → Service có endpoints Ready → kiểm tra đường request thực → bảo vệ danh tính và dữ liệu → quan sát SLO, chi phí và rollback**.








