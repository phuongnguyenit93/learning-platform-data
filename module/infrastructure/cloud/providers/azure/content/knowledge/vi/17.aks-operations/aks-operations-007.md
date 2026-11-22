# Phân phối ứng dụng AKS bằng Helm

## 1. Vì sao AKS cần một cơ chế đóng gói và phát hành ứng dụng?

Khi một ứng dụng Java chạy trên Azure Kubernetes Service (AKS), chỉ có container image là chưa đủ. Để chạy ổn định, Kubernetes còn cần Deployment, Service, ConfigMap, Secret, ServiceAccount, Ingress, HorizontalPodAutoscaler và có thể cả PodDisruptionBudget hoặc PersistentVolumeClaim.

Nếu triển khai các thành phần bằng nhiều tệp YAML rời rạc, nhóm phát triển dễ gặp những vấn đề:

- Mỗi môi trường phát triển, thử nghiệm và production dùng các thông số khác nhau.
- Một bản phát hành cần đồng bộ nhiều tài nguyên Kubernetes.
- Việc đổi image tag hoặc số replicas phải sửa ở nhiều nơi.
- Khó biết release nào đã được cài, nâng cấp hoặc cần quay về phiên bản trước.
- Các nhóm sao chép YAML, tạo nhiều bản gần giống nhau và khó cập nhật đồng loạt.
- CI/CD cần cách kiểm tra và triển khai có thể lặp lại thay vì chạy thủ công từng lệnh.

**Helm** là công cụ quản lý gói ứng dụng cho Kubernetes. Helm cho phép gom các tài nguyên cần thiết vào một **chart**, thay đổi cấu hình qua **values**, dựng Kubernetes manifests từ **templates**, rồi cài đặt/nâng cấp theo một **release**.

Trong module khám phá hệ sinh thái Microsoft Azure, Helm kết nối quy trình vận hành AKS với **Azure Container Registry (ACR)**, Microsoft Entra ID, managed identity, mạng, lưu trữ, giám sát, bảo mật và kiểm soát chi phí. Helm không thay thế Kubernetes hoặc AKS; nó hỗ trợ quản lý cách phát hành ứng dụng lên cluster.

### Mục tiêu bài học

Sau khi học, bạn có thể:

1. Phân biệt chart, template, values, repository và release.
2. Hiểu Helm tương tác với Kubernetes API trên AKS như thế nào.
3. Tạo chart đơn giản cho một API Java gồm Deployment, Service và HPA.
4. Dùng Helm lint, template và các bước kiểm tra trước triển khai.
5. Cài đặt, nâng cấp, xem lịch sử và rollback release đúng namespace.
6. Quản lý khác biệt giữa dev/staging/prod mà không nhân bản toàn bộ chart.
7. Kết nối container image trong ACR với AKS và xác thực đúng cách.
8. Sử dụng Helm chart theo OCI registry khi cần phân phối chart.
9. Kiểm soát secret, quyền Kubernetes, security context và rủi ro từ bên thứ ba.
10. Tích hợp Helm vào CI/CD, GitOps, monitoring và quy trình phát hành an toàn.

## 2. Helm là gì và không phải là gì?

Helm là **package manager cho Kubernetes**. Từ những template và values của chart, Helm dựng ra manifests, gửi chúng đến Kubernetes API và theo dõi lịch sử release theo cơ chế Helm.

Helm hỗ trợ:

- Dùng chung một bộ cấu hình tài nguyên Kubernetes cho nhiều môi trường.
- Định nghĩa những tham số ứng dụng có thể tùy chỉnh.
- Quản lý các lần install, upgrade và rollback.
- Chia sẻ chart dưới dạng package hoặc OCI artifact.
- Chạy một số kiểm tra chart và test hooks.
- Tự động hóa triển khai trong pipeline.

Helm **không**:

- Tự tạo AKS cluster nếu không có công cụ/thiết kế hạ tầng bên ngoài.
- Build Docker image hoặc đảm bảo image đã được push vào ACR.
- Tự cấp quyền ACR pull, workload identity hay Kubernetes RBAC khi chart chưa khai báo và hệ thống chưa cấu hình đúng.
- Đảm bảo ứng dụng không lỗi nghiệp vụ chỉ vì Helm báo deployed.
- Tự backup/rollback dữ liệu database.
- Tự cài ingress controller, certificate manager hoặc CRD nếu chart ứng dụng giả định chúng đã tồn tại.
- Biến việc cài chart không tin cậy thành an toàn.

Nên nhìn Helm như **lớp đóng gói và phát hành Kubernetes resources**, còn AKS quản lý cluster và Kubernetes controllers thực hiện việc tạo/điều phối Pods.

## 3. Mô hình hoạt động của Helm trên AKS

~~~mermaid
flowchart LR
    DEV[Source + Dockerfile] --> BUILD[CI build/test]
    BUILD --> ACR[Azure Container Registry - image]
    CHART[Helm chart + values] --> RENDER[Helm render templates]
    CI[Developer hoặc CI/CD] --> RENDER
    RENDER --> API[AKS Kubernetes API]
    API --> DEP[Deployment / Service / HPA]
    DEP --> PODS[Pods kéo image từ ACR]
    ACR --> PODS
    API --> HISTORY[Helm release metadata]
    HISTORY --> ROLLBACK[History / Rollback]
~~~

Luồng triển khai ví dụ:

1. CI build một image API Java và push vào ACR dưới tham chiếu có version/digest.
2. Nhóm phát triển có chart mô tả Deployment, Service, resources và probes.
3. Pipeline chọn values tương ứng với staging hoặc production.
4. Helm render ra manifests với tham số môi trường.
5. Helm gửi những manifests đó tới Kubernetes API bằng danh tính hiện có.
6. Kubernetes tạo hoặc cập nhật các tài nguyên, scheduler đặt Pod lên nodes.
7. Node/kubelet kéo image từ ACR bằng cơ chế identity/authorization được cấu hình.
8. Helm lưu thông tin release và các revision để hỗ trợ lịch sử/rollback.

**Điểm quan trọng:** quyền của người chạy Helm để sửa tài nguyên Kubernetes và quyền của node để pull image từ ACR là **hai đường xác thực khác nhau**.

## 4. Chart, release, repository, values và templates

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Chart** | Gói mô tả tài nguyên Kubernetes và metadata cần triển khai | orders-api chart version 0.1.0 |
| **Chart.yaml** | Khai báo tên, version, mô tả, dependencies và metadata của chart | name: orders-api |
| **values.yaml** | Các giá trị mặc định cho templates | replicaCount: 2 |
| **Templates** | Các tệp dùng Go template để sinh manifests | templates/deployment.yaml |
| **Release** | Một lần cài đặt chart, có tên và lịch sử revision | orders-api trong namespace orders-prod |
| **Chart repository** | Nơi phân phối chart, có thể là Helm repository HTTP hoặc OCI registry | oci://registry.example/helm |
| **Image repository** | Nơi chứa container images | acrdemo.azurecr.io/apps/orders-api |
| **Chart version** | Phiên bản của gói cấu hình Helm | 0.1.0 |
| **App version** | Phiên bản ứng dụng do chart công bố | 1.4.0 |
| **Release revision** | Số lần cài/nâng cấp/rollback được Helm ghi nhận | 1, 2, 3... |

### 4.1. Không nhầm ba loại phiên bản

Một hệ thống có thể đồng thời có:

~~~text
Helm chart version : 0.3.0
Application version: 1.4.2
Image digest       : sha256:<digest-thuc>
Release revision   : 7
~~~

Chúng phục vụ mục đích khác nhau:

- **Chart version** thay đổi khi cấu hình chart hoặc cách đóng gói thay đổi.
- **App version** mô tả phiên bản ứng dụng nhưng không tự buộc container chạy đúng image.
- **Image tag/digest** xác định image mà Kubernetes cần tải.
- **Release revision** tăng theo các sự kiện release trong lịch sử Helm.

Một release có thể nâng cấp chỉ vì đổi values, dù chart version không đổi. Ngược lại, chart version mới không đảm bảo mọi Pod đang chạy image mới nếu cấu hình image reference chưa thay đổi.

### 4.2. Một chart có thể được cài nhiều lần

Ví dụ:

~~~text
Chart: orders-api version 0.3.0

Release: orders-dev     namespace: orders-dev
Release: orders-staging namespace: orders-staging
Release: orders-prod    namespace: orders-prod
~~~

Các release có state và values riêng. **Tên release được định danh trong phạm vi namespace**, nhưng bạn vẫn cần tránh đặt tên Kubernetes resources cứng khiến các release đụng nhau.

## 5. Cấu trúc cơ bản của một Helm chart

Helm có thể tạo cấu trúc khởi đầu:

~~~bash
helm create orders-api
~~~

Một chart thường được tổ chức như sau:

~~~text
orders-api/
├── Chart.yaml
├── values.yaml
├── values.schema.json
├── .helmignore
├── charts/
└── templates/
    ├── _helpers.tpl
    ├── deployment.yaml
    ├── service.yaml
    ├── hpa.yaml
    ├── ingress.yaml
    ├── serviceaccount.yaml
    ├── NOTES.txt
    └── tests/
        └── test-connection.yaml
~~~

Không phải chart nào cũng cần tất cả tệp. Ví dụ API nội bộ có thể không cần Ingress; ứng dụng không dùng autoscale thì không cần HPA template.

- **Chart.yaml** xác định gói.
- **values.yaml** chứa defaults.
- **values.schema.json** giúp kiểm tra kiểu/ràng buộc của values nếu được khai báo.
- **templates/** dùng để dựng các tài nguyên.
- **_helpers.tpl** chứa named templates phục vụ tên/labels.
- **charts/** có thể chứa dependencies đã được đóng gói.
- **.helmignore** loại các tệp không cần thiết khỏi chart package.

Trong phần thực hành của bài, các snippets dưới đây mô tả **nội dung bạn sẽ tạo trong dự án riêng**, không phải những tệp cần ghi vào repository học liệu hiện tại.

## 6. Viết Chart.yaml

Ví dụ metadata cho chart **orders-api**:

~~~yaml
apiVersion: v2
name: orders-api
description: Helm chart cho API đơn hàng trên AKS
type: application
version: 0.1.0
appVersion: "1.4.0"
~~~

Ý nghĩa:

- **apiVersion: v2**: định dạng chart dùng trong hệ sinh thái Helm hiện đại.
- **name**: tên của chart.
- **type: application**: đây là chart ứng dụng; loại library phục vụ chia sẻ template functions.
- **version**: version của chart, thường theo Semantic Versioning.
- **appVersion**: thông tin về phiên bản ứng dụng, được Helm coi là metadata.

**Không mặc định appVersion sẽ cập nhật trường image trong Deployment.** Chỉ khi template tham chiếu đến .Chart.AppVersion hoặc values tương ứng thì nó mới ảnh hưởng manifest được sinh.

### 6.1. Khi nào cần tăng chart version?

Tăng chart version khi nội dung chart được phát hành thay đổi, ví dụ thêm Service, đổi probes, cập nhật security defaults hoặc sửa template. Nếu chỉ đổi values ở môi trường production mà chưa phát hành chart package mới, release revision có thể tăng mà chart version vẫn giữ nguyên.

Trong CI/CD, nên ghi lại cả chart package/version lẫn image digest đã dùng để audit.

## 7. Viết values.yaml có thể tái sử dụng

Ví dụ values mặc định cho một API Java nghe cổng 8080:

~~~yaml
replicaCount: 2

image:
  repository: acrdemoexample.azurecr.io/apps/orders-api
  tag: "1.4.0"
  digest: ""
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80
  targetPort: 8080

resources:
  requests:
    cpu: "100m"
    memory: "256Mi"
  limits:
    cpu: "500m"
    memory: "768Mi"

autoscaling:
  enabled: false
  minReplicas: 2
  maxReplicas: 5
  targetCPUUtilizationPercentage: 65

probes:
  readinessPath: /health/ready
  livenessPath: /health/live
  initialDelaySeconds: 10

fullnameOverride: ""
~~~

Đây là cấu hình học tập. **acrdemoexample.azurecr.io** chỉ là hostname minh họa; người học phải thay bằng registry có image thật và quyền pull thích hợp.

Lưu ý:

- **replicaCount** là số replicas khi chưa dùng HPA.
- **image.repository** phải là đường dẫn đầy đủ tới repository chứa image.
- **image.tag** dễ đọc nhưng có thể bị ghi đè nếu registry không khóa.
- **image.digest** giúp pin manifest cụ thể khi được cung cấp.
- **service.type: ClusterIP** giữ Service ở phạm vi nội bộ cluster.
- **resources.requests** giúp scheduler và HPA đưa ra quyết định đúng.
- **resources.limits** phải dựa trên đo đạc để tránh CPU throttling hoặc OOM.
- **probes** phải trùng endpoint thực tế của ứng dụng.
- **autoscaling.enabled** điều khiển việc chart có sinh HPA hay không.

**values.yaml không phải nơi lưu password, connection string hoặc private key production.** Values đi qua Helm rendering, lịch sử release và công cụ chẩn đoán, nên có thể bị lộ nếu dùng sai cách.

## 8. Named templates: đặt tên và labels nhất quán

Tệp **templates/_helpers.tpl** có thể chứa các named templates:

~~~gotemplate
{{- define "orders-api.name" -}}
{{ .Chart.Name }}
{{- end -}}

{{- define "orders-api.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else -}}
{{ printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end -}}
{{- end -}}

{{- define "orders-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "orders-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
~~~

Named templates giúp tạo tên tài nguyên và labels thống nhất. Hàm **include** trả nội dung một named template để dùng kèm **nindent** (xuống dòng và thụt lề).

**.Release.Name** là tên release tại thời điểm cài; **.Chart.Name** là tên chart. Kết hợp chúng giúp tránh việc hai release có cùng tên tài nguyên trong một namespace nếu chart được thiết kế phù hợp.

### 8.1. Tại sao cần labels ổn định?

Kubernetes Service chọn Pods bằng **selector**. Deployment cũng dùng selector để quản lý Pods của nó. Nếu một lần nâng cấp làm selector không tương thích với Pod labels, ứng dụng có thể mất backend hoặc Kubernetes từ chối thay đổi một trường bất biến.

Nên thiết kế selector labels thật ổn định, tránh đưa số version vào selector nếu mỗi upgrade sẽ thay version đó.

## 9. Template Deployment cho API Java

Tệp **templates/deployment.yaml**:

~~~gotemplate
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "orders-api.fullname" . }}
  labels:
    {{- include "orders-api.selectorLabels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "orders-api.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "orders-api.selectorLabels" . | nindent 8 }}
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: orders-api
          image: {{ if .Values.image.digest }}{{ printf "%s@%s" .Values.image.repository .Values.image.digest | quote }}{{ else }}{{ printf "%s:%s" .Values.image.repository (.Values.image.tag | default .Chart.AppVersion) | quote }}{{ end }}
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
          ports:
            - name: http
              containerPort: {{ .Values.service.targetPort }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          readinessProbe:
            httpGet:
              path: {{ .Values.probes.readinessPath | quote }}
              port: http
            initialDelaySeconds: {{ .Values.probes.initialDelaySeconds }}
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: {{ .Values.probes.livenessPath | quote }}
              port: http
            initialDelaySeconds: {{ .Values.probes.initialDelaySeconds }}
            periodSeconds: 20
~~~

### 9.1. Giải thích Helm template syntax

- **{{ ... }}**: biểu thức Go template được Helm xử lý trước khi gửi manifest sang Kubernetes.
- **.Values.image.repository**: đọc giá trị từ cấu hình values.
- **.Chart.AppVersion**: đọc appVersion trong Chart.yaml.
- **default**: dùng giá trị thay thế nếu đầu vào trống trong ngữ cảnh tương ứng.
- **quote**: bao giá trị trong chuỗi YAML thích hợp.
- **toYaml**: chuyển cấu trúc values thành YAML.
- **nindent**: đảm bảo thụt lề phù hợp.
- **if**: chỉ sinh cấu hình khi điều kiện được thỏa.
- **include**: chèn named template.

Trong ví dụ, nếu **image.digest** được cung cấp, Deployment dùng **repository@digest**; nếu không, dùng **repository:tag**. Đây là một cách để giữ đường triển khai production theo digest mà không phải sửa Deployment template.

### 9.2. Vì sao không luôn đặt replicas?

Khi HPA được bật, HPA là controller điều chỉnh số replicas. Nếu chart liên tục áp một con số cố định mỗi lần upgrade, có thể gây thay đổi replicas ngoài ý muốn. Vì vậy template **chỉ sinh replicas nếu autoscaling.enabled = false**.

Khi nâng cấp giữa chế độ có/không HPA, cần kiểm tra replicas thực tế và quy trình chuyển đổi để tránh co giãn ngoài dự kiến.

### 9.3. Quyền chạy container

Mẫu đặt UID không phải root và giảm capabilities. Nhưng chỉ làm như vậy khi image đã được build để chạy đúng UID/permission; nếu Java cần ghi vào một đường dẫn không có quyền, container có thể lỗi khởi động.

Ở production có thể bổ sung readOnlyRootFilesystem và writable volumes thích hợp, nhưng không nên đặt cờ đó nếu ứng dụng chưa được kiểm tra với thư mục tạm, log và cache.

## 10. Template Service

Tệp **templates/service.yaml**:

~~~gotemplate
apiVersion: v1
kind: Service
metadata:
  name: {{ include "orders-api.fullname" . }}
  labels:
    {{- include "orders-api.selectorLabels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  selector:
    {{- include "orders-api.selectorLabels" . | nindent 4 }}
  ports:
    - name: http
      port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
~~~

Service sử dụng selector trùng với Pod labels và chuyển traffic từ port 80 của Service đến container port đã đặt tên **http** (ở ví dụ là 8080).

**ClusterIP** không tạo public endpoint. Đây là lựa chọn phù hợp để bắt đầu, sau đó tích hợp ingress controller hoặc một giải pháp gateway được thiết kế riêng.

Nếu ứng dụng cần LoadBalancer hoặc Ingress, nên cấu hình rõ network/TLS/WAF và tránh mở cổng Internet chỉ vì values đổi từ ClusterIP sang LoadBalancer.

## 11. Template HPA có điều kiện

Tệp **templates/hpa.yaml**:

~~~gotemplate
{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "orders-api.fullname" . }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "orders-api.fullname" . }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}
{{- end }}
~~~

### 11.1. HPA cần điều kiện nào?

- Cluster phải cung cấp metrics API/nguồn metrics thích hợp.
- Pods cần CPU requests hợp lý để tính CPU utilization.
- Node pools cần đủ capacity hoặc có node autoscaling phù hợp.
- Workload phải thực sự có thể chạy thêm replicas.
- Database, queue và dịch vụ phụ thuộc không bị quá tải khi tăng số Pods.

**HPA thêm Pods; Cluster Autoscaler thêm Nodes** khi có điều kiện phù hợp. Helm chỉ tạo HPA resource, không bảo đảm autoscaling thực sự đáp ứng tải.

### 11.2. Nếu không muốn HPA?

Đặt **autoscaling.enabled: false**. Deployment template sẽ đặt replicas theo **replicaCount**. Khi bật HPA trở lại, kiểm tra hành vi thay đổi replicas và số lượng tối thiểu/tối đa.

## 12. Dùng values.schema.json để phát hiện cấu hình sai

Helm có thể dùng **values.schema.json** để kiểm tra một số ràng buộc của values.

Ví dụ:

~~~json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["image", "service", "resources"],
  "properties": {
    "replicaCount": {
      "type": "integer",
      "minimum": 1
    },
    "image": {
      "type": "object",
      "required": ["repository"],
      "properties": {
        "repository": {
          "type": "string",
          "minLength": 1
        },
        "tag": {
          "type": "string"
        },
        "digest": {
          "type": "string"
        }
      }
    },
    "service": {
      "type": "object",
      "properties": {
        "port": {
          "type": "integer",
          "minimum": 1,
          "maximum": 65535
        }
      }
    },
    "resources": {
      "type": "object"
    }
  }
}
~~~

Một schema tốt có thể ngăn lỗi như đặt **replicaCount** thành chuỗi, quên **image.repository** hoặc nhập port ngoài phạm vi.

Tuy nhiên, schema không thay thế Kubernetes API validation, policy checks, kiểm tra image hay integration tests. Các ràng buộc giữa nhiều trường hoặc điều kiện business phức tạp có thể cần kiểm thử bổ sung.

## 13. Quy tắc viết template an toàn và dễ bảo trì

### 13.1. Sử dụng hàm required khi cần

Ví dụ kiểm tra image repository:

~~~gotemplate
{{ required "image.repository phai duoc cung cap" .Values.image.repository }}
~~~

Nếu chart thiếu giá trị bắt buộc, quá trình render có thể dừng sớm với thông báo rõ hơn.

### 13.2. Cẩn thận với khoảng trắng

Các dấu **{{-** và **-}}** điều chỉnh whitespace. Lỗi indent hoặc loại bỏ newline quá mức có thể tạo YAML sai.

Hãy chạy **helm template** và kiểm tra output; đừng chỉ xem file template vì Kubernetes sẽ nhận manifest **sau render**, không nhận các biểu thức Helm gốc.

### 13.3. Không lạm dụng logic điều kiện

Chart có hàng trăm flags và nhiều nhánh rối có thể khó bảo trì hơn YAML thông thường. Hãy giữ các lựa chọn có ý nghĩa thực, tách chart hoặc dependency nếu sản phẩm có vòng đời riêng.

### 13.4. Giữ selectors ổn định

Những trường như **spec.selector** của Deployment có ràng buộc bất biến. Không thay selector theo chartVersion/appVersion tùy tiện rồi kỳ vọng helm upgrade luôn áp dụng được.

### 13.5. Hạn chế random/lookup không cần thiết

Template có giá trị sinh ngẫu nhiên hoặc **lookup** trạng thái cluster ở runtime có thể làm manifest khó tái lập và khiến hành vi giữa môi trường render local, CI và cluster khác nhau.

### 13.6. Không hardcode namespace

Nên dùng namespace đã chọn khi triển khai hoặc **.Release.Namespace** khi thật sự cần. Tránh hardcode **metadata.namespace: default** trong mỗi template, vì như vậy giá trị **--namespace orders-prod** có thể không có tác dụng như mong đợi.

## 14. Quản lý cấu hình theo dev, staging và production

Một chart duy nhất có thể dùng cho nhiều môi trường qua values files.

~~~text
charts/orders-api/
├── Chart.yaml
├── values.yaml
├── values-dev.yaml
├── values-staging.yaml
├── values-prod.yaml
└── templates/
~~~

Ví dụ **values-dev.yaml**:

~~~yaml
replicaCount: 1

image:
  repository: acrdemoexample.azurecr.io/apps/orders-api
  tag: "1.4.0-dev"

resources:
  requests:
    cpu: "50m"
    memory: "128Mi"
  limits:
    cpu: "250m"
    memory: "512Mi"
~~~

Ví dụ **values-prod.yaml**:

~~~yaml
replicaCount: 3

image:
  repository: acrdemoexample.azurecr.io/apps/orders-api
  tag: "1.4.0"
  digest: "sha256:<digest-thuc-cua-image>"

resources:
  requests:
    cpu: "300m"
    memory: "512Mi"
  limits:
    cpu: "1000m"
    memory: "1536Mi"

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 12
  targetCPUUtilizationPercentage: 65
~~~

Trong lab, nếu dùng placeholder **sha256:<...>** phải thay bằng digest thực hoặc đặt digest rỗng, vì Kubernetes không thể kéo image có digest giả.

### 14.1. Thứ tự ưu tiên values

Helm kết hợp:

1. Defaults của **values.yaml**.
2. Một hoặc nhiều file được truyền bằng **--values / -f** theo thứ tự.
3. Các giá trị chỉ định trực tiếp bằng **--set / --set-string** và những lựa chọn override tương ứng.

File values sau có thể ghi đè file trước theo quy tắc merge của Helm; các loại cấu trúc như list có thể có hành vi ghi đè, không phải luôn ghép phần tử.

Ví dụ:

~~~bash
helm template orders-api ./charts/orders-api \
  --namespace orders-prod \
  --values ./charts/orders-api/values.yaml \
  --values ./charts/orders-api/values-prod.yaml \
  --set-string image.tag=1.4.0
~~~

**Không truyền password bằng --set trên command line**: giá trị có thể đi vào shell history, logs hoặc Helm release metadata.

### 14.2. Không làm mỗi môi trường thành một chart khác nhau

Mỗi môi trường nên dùng **cùng logic template** và khác nhau ở tham số chính đáng. Nếu phải sửa Deployment template riêng bằng tay ở production, bạn đã mất tính lặp lại và khó audit.

## 15. Kiểm tra chart trước khi triển khai

Một chart hợp lệ về mặt template chưa chắc tạo được Pod chạy tốt. Nên có nhiều lớp kiểm tra.

### 15.1. Lint

~~~bash
helm lint ./charts/orders-api \
  --values ./charts/orders-api/values-dev.yaml
~~~

**helm lint** giúp phát hiện một số lỗi cấu trúc chart và templates. Nó không kiểm tra toàn bộ hành vi runtime.

### 15.2. Render manifests

~~~bash
helm template orders-api ./charts/orders-api \
  --namespace orders-dev \
  --values ./charts/orders-api/values-dev.yaml
~~~

Lệnh này sinh YAML gửi cho người đọc/CI để kiểm tra mà không cài tài nguyên vào cluster.

Cần đối chiếu:

- Tên Deployment và Service.
- Selector labels và Pod labels.
- Container image repository, tag/digest.
- Replicas hoặc HPA.
- Ports, resources và health probes.
- ServiceAccount và security context khi sử dụng.
- Các trường namespace và annotation.
- Các giá trị môi trường và nguồn secrets.

### 15.3. Kiểm tra bằng Kubernetes API hoặc schema

Có thể kiểm tra manifests với công cụ Kubernetes schema validation hoặc dùng một môi trường staging có phiên bản API phù hợp. Một chart render YAML hợp lệ vẫn có thể dùng Kubernetes API đã bị loại bỏ trên phiên bản AKS mục tiêu.

### 15.4. Kiểm thử policy/security

Nếu môi trường dùng Azure Policy, admission controller hoặc Kubernetes Pod Security Admission, cần chạy kiểm tra với cùng chính sách như production. Chart không nên chỉ thành công khi cluster tắt hết policy.

### 15.5. Không đưa secret vào output debug

**helm template**, **helm get values**, **helm get manifest**, CI artifact và debug logs có thể hiển thị giá trị nhạy cảm. Nếu hệ thống có secret, phải thiết kế đường phân phối an toàn, không coi output của Helm là tài liệu vô hại.

## 16. Cài release lần đầu trên AKS

Giả sử bạn đã có:

- AKS cluster hợp lệ, kubeconfig chọn đúng context.
- Namespace được phép sử dụng.
- Chart và values đã kiểm tra.
- ACR image tồn tại và node có quyền pull.
- Kubernetes RBAC đủ để tạo các tài nguyên chart khai báo.

Kiểm tra context:

~~~bash
kubectl config current-context
kubectl get nodes
~~~

Cài vào namespace **orders-dev**:

~~~bash
helm install orders-api ./charts/orders-api \
  --namespace orders-dev \
  --create-namespace \
  --values ./charts/orders-api/values-dev.yaml \
  --wait \
  --timeout 10m
~~~

Giải thích:

- **orders-api** đầu tiên là tên release.
- **./charts/orders-api** là đường dẫn chart.
- **--namespace orders-dev** chọn namespace của release.
- **--create-namespace** yêu cầu tạo namespace nếu cần và có quyền.
- **--values** cung cấp cấu hình môi trường.
- **--wait** chờ những resource phù hợp đạt trạng thái ready theo logic của Helm.
- **--timeout** giới hạn thời gian chờ cho tác vụ tương ứng.

**Helm trả thành công không chứng minh mọi luồng nghiệp vụ hoạt động.** Cần tiếp tục kiểm tra logs, readiness, kết nối database và endpoint nghiệp vụ.

### 16.1. Kiểm tra release

~~~bash
helm list --namespace orders-dev

helm status orders-api --namespace orders-dev

kubectl get deployments,services,pods \
  --namespace orders-dev

kubectl rollout status deployment/orders-api-orders-api \
  --namespace orders-dev
~~~

Tên Deployment ở ví dụ cuối dựa vào helper tạo tên **release-chart**. Nếu chart có **fullnameOverride** hoặc tên khác, dùng tên thực tế từ **kubectl get deployment**.

Nếu không thấy Pod khỏe, kiểm tra events và logs thay vì chạy cài lại liên tục.

## 17. Dùng helm upgrade --install cho pipeline

Trong automation, pipeline có thể không biết release đã tồn tại hay chưa. Cú pháp **upgrade --install** cho phép:

- Release chưa tồn tại: cài mới.
- Release đã tồn tại: nâng cấp.

Ví dụ:

~~~bash
helm upgrade --install orders-api ./charts/orders-api \
  --namespace orders-dev \
  --create-namespace \
  --values ./charts/orders-api/values-dev.yaml \
  --wait \
  --atomic \
  --timeout 10m
~~~

**--atomic** yêu cầu Helm cố gắng khôi phục trạng thái release theo cơ chế hỗ trợ nếu install/upgrade thất bại trong các điều kiện được theo dõi. Nó thường đi cùng hành vi chờ các resources phù hợp.

**Đây không phải giao dịch ACID bao trùm cả ứng dụng.** --atomic không rollback database migration, không hoàn nguyên những thay đổi bên ngoài Kubernetes, không xóa một file đã ghi vào Blob và không đảm bảo có thể khôi phục trạng thái thật của mọi controller.

### 17.1. Khi nào không nên retry tự động vô hạn?

Nếu install/upgrade thất bại do admission policy, quota, image pull hoặc manifest không hợp lệ, retry vô hạn chỉ tăng logs và che nguyên nhân. Pipeline nên dừng, lưu bằng chứng và yêu cầu người có quyền sửa cấu hình.

### 17.2. Thời gian chờ phải tính đến startup

Ứng dụng Java có thể cần nhiều thời gian để boot JVM, warm-up cache hoặc kết nối database. Timeout quá ngắn có thể khiến Helm đánh dấu thất bại dù ứng dụng sẽ sẵn sàng sau đó. Nhưng timeout quá dài lại khiến triển khai lỗi bị giữ lâu. Hãy đo thực tế và đặt phù hợp với SLO.

## 18. Nâng cấp image và cấu hình

Giả sử CI vừa push image **1.4.1** và cập nhật values. Thay vì sửa Deployment trực tiếp bằng kubectl rồi Helm không biết, hãy chạy upgrade qua release:

~~~bash
helm upgrade orders-api ./charts/orders-api \
  --namespace orders-dev \
  --values ./charts/orders-api/values-dev.yaml \
  --set-string image.tag=1.4.1 \
  --wait \
  --atomic \
  --timeout 10m
~~~

Với production, có thể dùng **image.digest** được pipeline ghi nhận:

~~~bash
helm upgrade orders-api ./charts/orders-api \
  --namespace orders-prod \
  --values ./charts/orders-api/values-prod.yaml \
  --set-string image.digest="sha256:<digest-thuc>" \
  --wait \
  --atomic \
  --timeout 10m
~~~

**Các chuỗi digest trong bài chỉ là placeholder**. Phải dùng digest hợp lệ từ ACR trước khi thực thi.

### 18.1. Vì sao nên triển khai theo digest?

Tag như **1.4.1** có thể bị trỏ lại sang image khác nếu registry hoặc pipeline không kiểm soát. Digest xác định manifest cụ thể, giúp staging và production dùng đúng artifact đã kiểm thử.

### 18.2. Không rebuild image giữa staging và production

Một bản build thứ hai từ cùng source có thể sử dụng base image hoặc dependency khác. Quy trình đáng tin cậy: **build một lần → push ACR → ghi digest → kiểm thử staging → dùng cùng digest cho production**.

### 18.3. Tương thích dữ liệu khi rolling update

Trong quá trình nâng cấp, version cũ và mới có thể cùng tồn tại. Database migration nên được thiết kế theo cách tương thích trong giai đoạn này. Helm rollback manifests không tự đảo ngược schema hoặc dữ liệu đã biến đổi.

## 19. Lịch sử release và rollback

Helm ghi nhận các revisions của release theo cơ chế lưu trữ đã cấu hình trên cluster. Bạn có thể xem:

~~~bash
helm history orders-api --namespace orders-dev
~~~

Xem trạng thái:

~~~bash
helm status orders-api --namespace orders-dev
~~~

Xem values đang được ghi nhận:

~~~bash
helm get values orders-api \
  --namespace orders-dev \
  --all
~~~

Xem manifest đã được Helm ghi nhận:

~~~bash
helm get manifest orders-api --namespace orders-dev
~~~

**Cảnh báo:** lệnh xem values/manifests có thể làm lộ nội dung nhạy cảm nếu chart đã dùng secret không an toàn. Chỉ chạy và lưu output trong môi trường được phép.

### 19.1. Rollback tới một revision cụ thể

Giả sử revision 3 là bản đã kiểm thử:

~~~bash
helm rollback orders-api 3 \
  --namespace orders-dev \
  --wait \
  --timeout 10m
~~~

Sau đó kiểm tra:

~~~bash
helm history orders-api --namespace orders-dev
kubectl get pods --namespace orders-dev
~~~

**Rollback tạo ra một sự kiện release mới**; nó không nhất thiết làm số revision giảm về 3. Đây là thao tác khôi phục cấu hình manifest dựa trên một bản trước, không phải quay ngược thời gian cho cluster, database hoặc hệ thống ngoài.

### 19.2. Điều gì rollback không xử lý?

- Database đã đổi schema không tương thích.
- Persistent volume đã bị sửa hoặc dữ liệu bị xóa.
- Secret external đã luân chuyển.
- API hoặc contract với hệ thống khác đã thay đổi.
- Image cũ đã bị xóa khỏi registry.
- Resource bị thay đổi thủ công ngoài Helm hoặc có controller khác đang tranh chấp.

Một kế hoạch phát hành tốt phải giữ image cũ trong ACR, có chiến lược migration và diễn tập rollback.

## 20. Các trạng thái release thường gặp

Khi điều tra Helm, bạn có thể gặp những trạng thái như:

| Trạng thái | Ý nghĩa tổng quát | Cần làm |
|---|---|---|
| **deployed** | Revision được cài/nâng cấp thành công theo Helm | Kiểm tra ứng dụng và health thực |
| **failed** | Một tác vụ release thất bại | Xem lỗi, events và resources |
| **pending-install** | Cài đặt đang trong quá trình xử lý | Kiểm tra tiến trình và timeout |
| **pending-upgrade** | Nâng cấp đang trong quá trình xử lý | Kiểm tra tác vụ có đang chạy hay bị kẹt |
| **pending-rollback** | Đang thực hiện rollback | Kiểm tra lịch sử và trạng thái |
| **superseded** | Revision cũ đã được thay thế | Dùng để đối chiếu lịch sử |
| **uninstalled** | Release đã được gỡ theo cơ chế lưu lịch sử | Kiểm tra tài nguyên còn tồn tại |

Đừng sửa trực tiếp Helm release Secret/metadata để “mở khóa” một trạng thái đang pending nếu chưa hiểu hệ quả. Trước hết kiểm tra có pipeline khác đang chạy cùng release hay không, timeout và sự kiện của Kubernetes.

**Mỗi release nên có một luồng phát hành được điều phối**, tránh hai pipeline upgrade đồng thời một tên release/namespace.

## 21. Helm release metadata và rủi ro lộ secrets

Theo cơ chế mặc định phổ biến, Helm lưu thông tin release trong Kubernetes Secrets thuộc namespace liên quan. Dữ liệu release có thể chứa chart, values và manifests cần cho lịch sử/rollback.

Vì vậy:

- Đừng đặt mật khẩu production ở values.yaml.
- Đừng chuyển secret bằng **--set** trong CI logs.
- Đừng giả định Kubernetes Secret được bảo vệ chỉ vì dữ liệu được mã hóa Base64; mã hóa at rest và quyền truy cập phải được cấu hình riêng.
- Giới hạn quyền xem Secrets và Helm release metadata theo namespace.
- Chú ý output **helm get values**, **helm get manifest**, **helm template** và các pipeline artifacts.
- Khi dùng Helm hooks hoặc Jobs, đảm bảo log không in secrets.

### 21.1. Giải pháp secrets an toàn hơn

Có thể dùng:

- **Microsoft Entra Workload ID** để Pod lấy token gọi dịch vụ Azure được phép.
- **Azure Key Vault** và phương án tích hợp hỗ trợ, ví dụ Secrets Store CSI Driver.
- External Secrets Operator nếu được tổ chức phê duyệt và đã quản lý CRDs/controller.
- Kubernetes Secret được tạo và quản lý bởi một hệ thống riêng có RBAC/encryption phù hợp.

Chart có thể tham chiếu **tên secret hiện hữu** thay vì đưa giá trị secret vào template hoặc values. Ví dụ deployment có thể dùng:

~~~yaml
env:
  - name: DATABASE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-db-credentials
        key: password
~~~

Đoạn trên chỉ là ví dụ nếu Secret đã tồn tại. Trong production nên ưu tiên phương án workload identity và không dùng password nếu dịch vụ dữ liệu hỗ trợ.

## 22. Helm chart và quyền Kubernetes RBAC

Helm sử dụng kubeconfig/context và danh tính có quyền Kubernetes API tương ứng. Nếu chart tạo Deployment, Service, Role, ServiceAccount, HPA hoặc CRDs, người triển khai phải được phép thao tác trên những loại resource và scope đó.

### 22.1. Phân quyền theo môi trường

Một CI service principal hoặc danh tính pipeline chỉ nên được phép thay đổi resources cần thiết trong namespace mục tiêu. Không mặc định cấp **cluster-admin** để mọi Helm install thành công.

### 22.2. Rủi ro từ chart bên thứ ba

Một chart không tin cậy có thể khai báo:

- ClusterRole/ClusterRoleBinding quyền rộng.
- Privileged containers và hostPath mounts.
- ServiceAccount có token/quyền lớn.
- Helm hooks với Jobs chạy lệnh nhạy cảm.
- CRDs/controllers có phạm vi cluster.
- Image từ registry không được kiểm chứng.

Trước khi cài chart của bên thứ ba, cần kiểm tra nguồn, version, licenses, manifests sau render, RBAC, security context, images và network requirements.

### 22.3. Namespace không phải ranh giới cô lập tuyệt đối

Một chart cài trong namespace **orders-prod** vẫn có thể tạo tài nguyên cluster-scoped nếu template khai báo và danh tính đủ quyền. Do đó, namespace chỉ là một lớp tổ chức/quyền, không bảo đảm an toàn tuyệt đối.

## 23. ACR image authentication và Helm là hai việc khác nhau

Có hai vấn đề riêng:

1. **Helm truy cập chart package**, có thể nằm trong Git, Helm repository hoặc OCI registry.
2. **AKS node kéo container image**, thường từ ACR bằng kubelet/identity được cấu hình.

Ngay cả khi Helm cài Deployment thành công, Pod vẫn có thể gặp **ImagePullBackOff** nếu node không đủ quyền ACR hoặc không có đường mạng.

### 23.1. Khi dùng ACR private cho image

Cần kiểm tra:

- Image reference có đúng registry/repository/tag/digest.
- AKS kubelet identity hoặc cơ chế authentication có quyền **pull** theo ACR authorization model.
- Private endpoint/firewall/DNS/egress có cho phép kéo image.
- Image architecture/OS phù hợp node pool.
- Image digest còn tồn tại và không bị xóa theo retention.

Một ví dụ image trong values:

~~~yaml
image:
  repository: acrdemoexample.azurecr.io/apps/orders-api
  tag: "1.4.0"
  digest: ""
~~~

Khi CI có digest thực, dùng digest thay tag theo thiết kế Deployment ở mục 9.

### 23.2. Workload identity không tự động là quyền image pull

Workload identity thường dùng cho ứng dụng **bên trong Pod** truy cập Azure Storage, Key Vault hoặc API khác. Việc pull image diễn ra trong quá trình tạo Pod và liên quan đến kubelet/node identity hoặc cơ chế registry authentication được hỗ trợ. Không nhầm hai lớp danh tính.

## 24. Phân phối Helm chart qua OCI registry và ACR

Chart cũng có thể được đóng gói thành artifact và phân phối qua OCI registry như Azure Container Registry. Điều này khác với việc chứa **container image** trong repository của ACR, dù cùng dựa trên công nghệ OCI.

### 24.1. Đóng gói chart

Sau khi đã kiểm tra chart:

~~~bash
helm lint ./charts/orders-api

helm package ./charts/orders-api \
  --destination ./dist
~~~

Kết quả có dạng:

~~~text
dist/orders-api-0.1.0.tgz
~~~

Tên gói và version được lấy từ Chart.yaml.

### 24.2. Đăng nhập OCI registry

Với ACR và Azure CLI, có thể dùng token từ danh tính Azure đã đăng nhập, theo tính năng và quyền đang được hỗ trợ. Ví dụ Bash:

~~~bash
ACR_NAME="acrdemoexample"

ACR_LOGIN_SERVER="$(az acr show \
  --name "$ACR_NAME" \
  --query loginServer \
  --output tsv)"

az acr login \
  --name "$ACR_NAME" \
  --expose-token \
  --query accessToken \
  --output tsv |
helm registry login "$ACR_LOGIN_SERVER" \
  --username 00000000-0000-0000-0000-000000000000 \
  --password-stdin
~~~

**Không in token ra logs**. Nếu dùng runner hoặc cách xác thực khác, áp dụng phương pháp đăng nhập được ACR và Helm hỗ trợ, với quyền push/pull phù hợp. Username trong ví dụ là giá trị đặc biệt dùng cho luồng token được Azure CLI trả về, không phải tài khoản quản trị cá nhân.

### 24.3. Push chart package

~~~bash
helm push ./dist/orders-api-0.1.0.tgz \
  oci://acrdemoexample.azurecr.io/helm
~~~

Với cú pháp OCI, đích push là **repository prefix**; Helm suy ra tên chart và version từ package. Chart sẽ có tham chiếu logic:

~~~text
oci://acrdemoexample.azurecr.io/helm/orders-api
version: 0.1.0
~~~

### 24.4. Pull hoặc cài chart OCI

~~~bash
helm pull \
  oci://acrdemoexample.azurecr.io/helm/orders-api \
  --version 0.1.0
~~~

Cài trực tiếp chart từ OCI registry nếu client có quyền:

~~~bash
helm upgrade --install orders-api \
  oci://acrdemoexample.azurecr.io/helm/orders-api \
  --version 0.1.0 \
  --namespace orders-dev \
  --create-namespace \
  --values ./values-dev.yaml \
  --wait \
  --atomic
~~~

Chú ý **--version 0.1.0** ở ví dụ này là **chart version**, không phải image tag. Values vẫn có thể chỉ định image 1.4.0 hoặc một digest riêng.

### 24.5. Không nhầm chart OCI với Docker image OCI

ACR có thể chứa cả:

~~~text
Helm chart:
  oci://acrdemoexample.azurecr.io/helm/orders-api --version 0.1.0

Container image:
  acrdemoexample.azurecr.io/apps/orders-api:1.4.0
~~~

**helm pull/helm push** làm việc với chart package; **docker pull/docker push** làm việc với container image. AKS nodes không chạy một chart như container.

## 25. Chart dependencies và thư viện dùng chung

Một chart có thể khai báo dependencies trong **Chart.yaml**, ví dụ:

~~~yaml
apiVersion: v2
name: orders-api
type: application
version: 0.1.0
dependencies:
  - name: redis
    version: "18.x.x"
    repository: "https://charts.example.invalid"
    condition: redis.enabled
~~~

**Đây là minh họa cú pháp**. URL **charts.example.invalid** không phải repository thật; phải thay bằng nguồn chart được tổ chức phê duyệt và version constraint hợp lệ theo yêu cầu sử dụng.

Các lệnh thường gặp:

~~~bash
helm dependency update ./charts/orders-api

helm dependency build ./charts/orders-api
~~~

Phân biệt:

- **dependency update** tìm version theo khai báo và cập nhật lock/dependencies theo hành vi Helm.
- **dependency build** tái tạo dependency từ lock file khi có, giúp tăng tính lặp lại.

Nên commit **Chart.lock** trong repository ứng dụng khi cần kiểm soát version dependencies, nhưng vẫn kiểm tra package source/digest và chuỗi cung ứng.

### 25.1. Có nên đóng gói database vào chart API?

Một chart “all-in-one” gồm API, database, cache và message broker có thể tiện trong demo nhưng tạo rủi ro cho production:

- Database có vòng đời nâng cấp/backup khác API.
- Xóa release có thể ảnh hưởng tài nguyên stateful.
- Dữ liệu có thể bị mất nếu storage/PVC policy không được hiểu rõ.
- Security và trách nhiệm vận hành bị trộn lẫn.

Với Azure production, thường đáng cân nhắc dùng **managed database/cache** và cấu hình kết nối từ API, thay vì tự dựng một database trong chart ứng dụng nếu không có yêu cầu Kubernetes cụ thể.

### 25.2. Library chart

Helm hỗ trợ **library chart** cho các template/helper dùng chung. Nó giúp tái sử dụng tên/labels/policies, nhưng không nên biến một library chart thành lớp trừu tượng phức tạp làm người vận hành không thể đọc manifest cuối cùng.

## 26. Helm hooks, Jobs và thứ tự triển khai

Helm hỗ trợ **hooks** để chạy tài nguyên tại một số thời điểm trong vòng đời release, ví dụ trước/sau install hoặc upgrade.

Ví dụ annotation của một Kubernetes Job:

~~~yaml
metadata:
  annotations:
    "helm.sh/hook": pre-upgrade
    "helm.sh/hook-weight": "0"
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
~~~

### 26.1. Khi nào hooks hữu ích?

- Một Job kiểm tra điều kiện trước khi nâng cấp.
- Một bước đồng bộ cấu hình có kiểm soát.
- Một migration Job có thiết kế idempotent và tương thích.
- Một test Job kiểm tra kết nối sau triển khai.

### 26.2. Rủi ro của hooks

- Hooks có thể tạo side effects ngoài khả năng rollback của Helm.
- Một migration database thất bại có thể để dữ liệu ở trạng thái trung gian.
- Hook resource và lịch sử xóa có cơ chế riêng, không nhất thiết được quản lý giống resource thông thường.
- Hooks có thể chạy lại khi pipeline retry.
- Một pre-upgrade hook treo có thể khiến release chờ hoặc thất bại.

**Không coi --atomic là phương án rollback an toàn cho database migration hook.** Cần thiết kế migration độc lập, có backup, tương thích ngược và runbook riêng.

## 27. Helm test: kiểm tra sau khi cài

Helm có cơ chế **test** thông qua các tài nguyên kiểm thử được đánh dấu bằng hook. Ví dụ **templates/tests/test-connection.yaml**:

~~~gotemplate
apiVersion: v1
kind: Pod
metadata:
  name: {{ include "orders-api.fullname" . }}-test
  annotations:
    "helm.sh/hook": test
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  restartPolicy: Never
  containers:
    - name: wget
      image: busybox:1.36
      command:
        - sh
        - -c
        - >-
          wget -qO- http://{{ include "orders-api.fullname" . }}:{{ .Values.service.port }}/health/ready
~~~

Sau khi cài:

~~~bash
helm test orders-api --namespace orders-dev --logs
~~~

Pod test thử gọi Service ở namespace release. Nó chỉ thành công khi ứng dụng cung cấp endpoint đúng và môi trường cho phép test image được pull.

**Một test HTTP 200 không chứng minh toàn bộ nghiệp vụ đúng.** Cần tích hợp test thật với database, queue, authorization và những luồng quan trọng, tốt nhất ở staging trước khi promote.

### 27.1. Không dùng test images thiếu kiểm soát

Ngay cả test hooks cũng chạy container trong cluster. Hãy pin image/version/digest, đặt requests/limits và bảo vệ quyền cho nó tương tự những workload khác khi chuyển từ lab lên production.

## 28. Helm và Kubernetes reconciliation: ai quản lý tài nguyên?

Helm gửi Kubernetes resources; sau đó **Kubernetes controllers** duy trì trạng thái của Pods, Services và các đối tượng tương ứng.

Ví dụ:

1. Helm cài Deployment với replicas 3.
2. Kubernetes tạo ReplicaSet và ba Pods.
3. Một Pod crash.
4. Kubernetes tạo hoặc restart Pod tương ứng.
5. Helm không cần chạy lại chỉ để sửa Pod lỗi.

Nhưng nếu ai đó dùng **kubectl edit deployment** sửa image ngoài quy trình Helm:

- Cluster state có thể khác với manifest được Helm ghi nhận.
- Lần helm upgrade tiếp theo có thể ghi đè hoặc gây thay đổi ngoài ý muốn.
- Git/chart values không còn mô tả đúng trạng thái hệ thống.

Đây gọi là **configuration drift**. Cần quy định hệ thống nguồn sự thật: chart + values trong Git, pipeline/GitOps và những công cụ quản trị được phép.

### 28.1. Tránh hai hệ thống cùng quản lý một resource

Nếu một resource vừa được chart A quản lý vừa được GitOps/Helm chart B chỉnh sửa, hai controllers có thể cạnh tranh. Cần rõ owner cho mỗi resource, scope và chính sách phát hành.

### 28.2. Tài nguyên được tạo bên ngoài chart

Có những tài nguyên nên được quản trị riêng, chẳng hạn:

- AKS cluster, VNet, node pools và ACR bằng IaC/AKS APIs.
- Ingress controller hoặc cert-manager theo platform chart.
- Database/Key Vault qua Azure resources.
- Namespace, RBAC nền tảng và policies theo platform team.
- Ứng dụng/API theo application chart.

Không nhất thiết gom tất cả hạ tầng vào một Helm chart.

## 29. Helm và GitOps

Helm CLI thường được dùng trong CI/CD theo hướng **push deployment**: pipeline được cấp quyền rồi gọi **helm upgrade**.

Một mô hình khác là **GitOps**, nơi controller như Flux hoặc Argo CD (khi được triển khai/được hỗ trợ) quan sát cấu hình trong Git/OCI rồi reconcile tài nguyên vào cluster.

~~~mermaid
flowchart TD
    COMMIT[Git commit / release approval] --> CONFIG[Chart version + values + image digest]
    CONFIG --> CONTROLLER[GitOps controller trên AKS]
    CONTROLLER --> API[Kubernetes API]
    API --> DEPLOY[Deployment / Service / HPA]
    DEPLOY --> OBS[Logs, metrics và health]
~~~

### 29.1. Giá trị của GitOps

- Git lưu lịch sử thay đổi và review.
- Có thể quản lý nhiều environments theo cấu trúc rõ ràng.
- Hạn chế việc CI runner phải có quyền trực tiếp trên mọi cluster nếu thiết kế theo pull.
- Phát hiện hoặc điều chỉnh configuration drift theo chính sách.

### 29.2. Những điểm phải làm rõ

- Controller nào được phép quản lý release/resource?
- Secrets được giải mã/cấp an toàn bằng cơ chế nào?
- Chart version và image digest được pin ra sao?
- Có approval trước production hay không?
- Khi rollback, nên revert Git commit, chỉnh version hay dùng lệnh Helm thủ công?
- Khi GitOps và Helm CLI cùng can thiệp, hệ thống nào là nguồn sự thật?

**Không trộn hai quy trình triển khai song song vào cùng release** nếu chưa có cơ chế ownership rõ ràng, vì thao tác rollback thủ công có thể bị GitOps controller đưa trở về trạng thái trong Git ngay sau đó.

## 30. Thiết kế phát hành production trên AKS

Một quy trình kiểm soát chất lượng:

~~~mermaid
flowchart TD
    CODE[Source code] --> BUILD[Build và test application]
    BUILD --> IMAGE[Push image lên ACR]
    IMAGE --> DIGEST[Đọc image digest]
    CHART[Helm chart + pinned dependencies] --> LINT[Lint / Render / Policy checks]
    DIGEST --> LINT
    LINT --> STAGE[Deploy staging]
    STAGE --> TEST[Smoke / Integration / E2E tests]
    TEST --> APPROVE{Được duyệt?}
    APPROVE -->|Có| PROD[Deploy production]
    APPROVE -->|Không| STOP[Dừng, sửa lỗi]
    PROD --> WATCH[Observe rollout / SLO]
    WATCH --> ROLLBACK[Rollback khi vượt ngưỡng]
~~~

### 30.1. Release manifest cần ghi những gì?

| Thông tin | Ví dụ |
|---|---|
| Git commit | commit của ứng dụng |
| Pipeline run | build ID |
| Registry/image repository | acrdemoexample.azurecr.io/apps/orders-api |
| Image digest | sha256:... |
| Helm chart version | 0.1.0 |
| Values revision | Git commit hoặc file hash |
| Target cluster/namespace | aks-prod / orders-prod |
| Release name/revision | orders-api / 7 |
| Approval | Mã thay đổi hoặc release reviewer |

Không nên coi **helm history** là hệ thống duy nhất chứa audit trail. Khi rollback, Helm release metadata có thể bị giới hạn lịch sử hoặc xóa khi uninstall, còn pipeline/Git cần giữ chứng cứ phát hành.

### 30.2. Release gates

Có thể yêu cầu:

- Unit/integration tests đạt.
- Container security scan/policy đạt.
- Chart lint/render/schema validation đạt.
- Staging E2E tests đạt.
- Người có quyền chấp thuận production.
- Rollout health, error rate và latency nằm trong ngưỡng.
- Image/chart phiên bản trước vẫn còn để rollback.

## 31. Monitoring sau một lần helm upgrade

Ngay khi Helm báo thành công, cần xem:

~~~bash
helm status orders-api -n orders-prod
kubectl get deployments,pods,services -n orders-prod
kubectl rollout status deployment/orders-api-orders-api -n orders-prod
kubectl get events -n orders-prod --sort-by=.metadata.creationTimestamp
~~~

Nếu một Pod lỗi:

~~~bash
kubectl describe pod <pod-name> -n orders-prod
kubectl logs <pod-name> -n orders-prod
~~~

Những dấu hiệu cần quan sát:

- **ImagePullBackOff:** image name/tag/digest, ACR auth/network.
- **CrashLoopBackOff:** app startup, secret/config, dependency, OOM.
- **Pending:** node capacity, resources requests, taints, volume.
- **Readiness probe failed:** endpoint/port sai hoặc ứng dụng chưa sẵn sàng.
- **Error rate tăng:** bản phát hành lỗi nghiệp vụ dù Pods Ready.
- **HPA bất thường:** CPU requests/metrics không hợp lý hoặc database nghẽn.

Kết hợp Azure Monitor Container Insights, logs, metrics, dashboard và cảnh báo theo công cụ/tính năng được tổ chức sử dụng. Tên thành phần giám sát và cách triển khai có thể thay đổi theo cấu hình AKS.

## 32. Helm rollback và xử lý tình huống lỗi thật

### Tình huống A — Image không tồn tại

**Triệu chứng:** Helm apply thành công nhưng Pods không Ready và có ImagePullBackOff.

Cách điều tra:

1. Xem image reference cuối cùng từ Deployment.
2. Đối chiếu tag/digest trong ACR.
3. Kiểm tra quyền pull và egress/DNS.
4. Nếu image sai, sửa values và upgrade lại bằng digest đúng.
5. Nếu cần, rollback revision trong khi vẫn giữ image cũ.

### Tình huống B — Service trả 503 sau upgrade

Có thể do readiness chưa đạt, selector sai, Pod crash hoặc ứng dụng không tương thích database. Xem EndpointSlices/Service selectors, Pod logs và metrics. Rollback code chỉ giúp khi dependency/schema còn tương thích.

### Tình huống C — Helm pending-upgrade

Kiểm tra có pipeline khác đang chạy, tác vụ trước còn thực hiện hay đã timeout. Không sửa dữ liệu release bằng tay khi chưa xác minh trạng thái và đường phục hồi được hỗ trợ.

### Tình huống D — Helm rollback thành công nhưng ứng dụng vẫn lỗi

Helm quay lại manifest trước, nhưng database đã thay schema, cache thay đổi hoặc file đã bị xóa ngoài cluster. Cần áp dụng runbook của ứng dụng, kiểm tra dữ liệu và các hệ thống phụ thuộc.

### Tình huống E — Resource không bị xóa khi uninstall

Một số tài nguyên có lifecycle đặc biệt như CRDs hoặc được bảo vệ bằng annotation/policy; những tài nguyên tạo bởi hook/controller cũng có thể có vòng đời riêng. **helm uninstall không bảo đảm xóa sạch mọi thứ liên quan**, đặc biệt persistent data hoặc external resources.

## 33. Uninstall và dọn tài nguyên an toàn

Với release chỉ dùng cho lab:

~~~bash
helm uninstall orders-api \
  --namespace orders-dev
~~~

Kiểm tra:

~~~bash
helm list --namespace orders-dev
kubectl get all --namespace orders-dev
~~~

**Chỉ thực hiện khi release thuộc bài lab và được phép xóa.** Nếu ứng dụng có PVC, database, CRD, secrets dùng chung hoặc tài nguyên do hooks/controllers tạo, cần xem xét retention và backup trước khi uninstall.

Không xóa namespace hoặc resource group vì nghĩ chúng chỉ chứa Helm release đó nếu chưa kiểm tra ownership.

### 33.1. Helm uninstall có xóa ACR image không?

Không. Helm quản lý Kubernetes resources của release, không tự xóa image đang lưu trên Azure Container Registry.

### 33.2. Helm uninstall có xóa database không?

Phụ thuộc database có phải tài nguyên Kubernetes được chart quản lý và chính sách storage của nó, hay một Azure managed database độc lập. Trong production, không nên dựa vào uninstall làm cơ chế quản trị vòng đời database.

### 33.3. Dọn chart cache và credential

Những tệp charts/cache/registry credentials trên máy developer hoặc CI runner cũng cần được quản lý theo chính sách tổ chức, nhất là nếu helm registry login đã lưu thông tin xác thực.

## 34. Những sai lầm phổ biến khi dùng Helm trên AKS

- **Xem chart như Docker image:** chart là bộ cấu hình Kubernetes; image là artifact để chạy container.
- **Không phân biệt chart version và app version:** làm release khó audit.
- **Dùng latest cho production:** cùng tag có thể tải image khác theo thời điểm.
- **Sửa Deployment thủ công sau khi install:** gây drift và bị upgrade ghi đè.
- **Hardcode namespace/resource name:** hai release dễ đụng nhau.
- **Đưa mật khẩu vào values.yaml:** rò rỉ qua Git, Helm metadata hoặc logs.
- **Chỉ chạy helm lint rồi deploy thẳng:** bỏ qua render, API compatibility và policy checks.
- **Dùng --atomic như backup database:** rollback chỉ giải quyết một phần tài nguyên do Helm quản lý.
- **Không kiểm tra readiness:** Helm có thể chờ sai hoặc không phát hiện lỗi nghiệp vụ.
- **Bật HPA nhưng vẫn cưỡng bức replicas trong mọi upgrade:** gây biến động capacity.
- **Cài chart bên thứ ba với cluster-admin:** mở rộng blast radius không cần thiết.
- **Không kiểm soát hooks:** side effects và Jobs có thể tồn tại hoặc chạy lại.
- **Quên ACR pull permissions:** Pods không thể tải image dù Helm install thành công.
- **Không pin chart dependencies:** môi trường mới có thể tải dependency khác.
- **GitOps và helm upgrade cùng quản lý release:** dẫn đến tranh chấp trạng thái.
- **Xóa chart/release/image cũ sớm:** không có artifact để rollback.
- **Bỏ qua chi phí logs/compute:** số replicas tăng nhưng không có cảnh báo ngân sách.

## 35. Bài thực hành: đóng gói và phát hành API lên AKS

**Bối cảnh:** đội phát triển có API Java tên orders-api, container image đã được push vào ACR. Nhiệm vụ là dùng Helm tạo chart, triển khai ở namespace thử nghiệm, nâng cấp và rollback có kiểm soát.

### Phần A — Chuẩn bị

1. Có AKS cluster được phép thực hành và kubeconfig chọn đúng context.
2. Có quyền Kubernetes để tạo namespace/Deployment/Service/HPA theo yêu cầu.
3. Có image API Java chạy được tại một registry được phép truy cập; nếu dùng ACR private, cấu hình quyền pull trước.
4. API cung cấp **/health/live** và **/health/ready** hoặc điều chỉnh values/templates cho phù hợp.
5. Chuẩn bị môi trường thực hành riêng và ngân sách cho pods/nodes cần thiết.
6. Cài Helm CLI và kubectl phiên bản tương thích với cluster.

### Phần B — Tạo chart

1. Chạy **helm create orders-api** trong thư mục dự án thực hành.
2. Giữ những tệp cần dùng; loại template không phục vụ kiến trúc.
3. Thay Chart.yaml và values.yaml theo mục 6 và 7.
4. Viết _helpers.tpl, deployment.yaml, service.yaml, hpa.yaml như mục 8–11.
5. Thêm values-dev.yaml và values-prod.yaml theo tiêu chí môi trường.
6. Nếu cần, thêm values.schema.json.

### Phần C — Kiểm tra trước cài đặt

1. Chạy **helm lint**.
2. Chạy **helm template** với values-dev.
3. Xác nhận Deployment selector trùng Pod labels và Service selector.
4. Kiểm tra image reference, replicas, requests/limits, probes và HPA.
5. Kiểm tra các Kubernetes API versions phù hợp AKS cluster.
6. Đảm bảo không có secret production trong manifest render.

### Phần D — Install

1. Xác nhận Kubernetes context.
2. Chạy **helm upgrade --install** vào namespace **orders-dev**.
3. Dùng **helm status**, **helm list** và **kubectl get pods** để kiểm tra.
4. Quan sát readiness và logs nếu ứng dụng chưa chạy.
5. Dùng kubectl port-forward đến Service hoặc kiểm tra ingress riêng của lab.
6. Ghi lại chart version, image version/digest và release revision.

### Phần E — Upgrade

1. Tạo image thử nghiệm 1.4.1 hoặc thay một giá trị config không nhạy cảm.
2. Chạy **helm template** để xem manifest thay đổi.
3. Thực hiện **helm upgrade**.
4. Quan sát rolling rollout và các Pod mới.
5. Kiểm tra health, error rate và nghiệp vụ.
6. Ghi lại release revision mới.

### Phần F — Rollback

1. Dùng **helm history** xem revision trước.
2. Thực hiện rollback về revision đã biết hoạt động.
3. Xác minh Deployment image/config quay lại đúng phiên bản.
4. Kiểm tra database và những side effects bên ngoài nếu bài lab có sử dụng.
5. Ghi kết quả và giới hạn của rollback.

### Phần G — Đóng gói chart và thử OCI

Nếu có ACR chart repository và quyền cho phép:

1. Dùng **helm package** tạo chart .tgz.
2. Đăng nhập registry bằng cơ chế token phù hợp.
3. Push chart vào OCI repository.
4. Pull/chart install qua đường dẫn OCI với **chart version cố định**.
5. Đối chiếu chart version và image digest đang chạy.

### Phần H — Cleanup

1. Kiểm tra release thuộc sở hữu bài lab.
2. Xem tài nguyên stateful, Secrets và hook Jobs nếu có.
3. Uninstall release thử nghiệm nếu được phép.
4. Chỉ xóa namespace/tài nguyên riêng sau khi xác minh không có phụ thuộc.
5. Kiểm tra chi phí nếu bài lab tạo mới node, Load Balancer hoặc các dịch vụ Azure khác.

**Nếu chưa có AKS cluster hoặc ACR image hợp lệ**, vẫn có thể hoàn thành phần chart, lint và template offline. Tuy nhiên, không tuyên bố đã kiểm thử install, image pull hoặc rollback thực tế nếu chưa chạy trên cluster.

## 36. Checklist triển khai Helm vào production

- [ ] Chart có version rõ ràng và metadata đúng.
- [ ] Image được build/test/scan, pin theo digest hoặc tag bất biến.
- [ ] Chart dependencies được khóa và nguồn được kiểm tra.
- [ ] Values theo môi trường có cấu trúc rõ, không nhân bản chart.
- [ ] Không đưa secret vào chart/values/CI logs/Helm history.
- [ ] Tài khoản deploy chỉ có quyền Kubernetes cần thiết.
- [ ] ACR pull identity và network được xác minh trên AKS nodes.
- [ ] Templates dùng tên/labels/selectors nhất quán và ổn định.
- [ ] Resources requests/limits, probes và replicas/HPA phù hợp SLO.
- [ ] Ingress, TLS, Network Policy và RBAC đã được platform team duyệt.
- [ ] helm lint, template, schema và policy checks đã đạt.
- [ ] Staging đã kiểm tra runtime, health và nghiệp vụ.
- [ ] Rolling update có đủ capacity, PDB và graceful shutdown.
- [ ] Database migration tương thích ngược và có backup.
- [ ] Có helm history, rollback plan, old image/chart còn lưu.
- [ ] Hooks/CRDs/resources dùng chung có owner và lifecycle rõ.
- [ ] CI/CD hoặc GitOps là nguồn sự thật duy nhất cho release.
- [ ] Có alert cho Pod failures, rollout, HPA, latency và error rate.
- [ ] Có ngân sách AKS node pools, network, storage, monitoring.
- [ ] Có runbook xử lý ImagePullBackOff, pending-upgrade và rollback thất bại.

## 37. Câu hỏi tự kiểm tra

1. Chart, release và repository có nghĩa gì trong Helm?
2. Chart version, appVersion, image tag/digest và release revision khác nhau như thế nào?
3. Vì sao một chart có thể được cài nhiều lần ở các namespaces khác nhau?
4. Mục đích của _helpers.tpl và selectorLabels là gì?
5. Nếu thay values.yaml nhưng không sửa Chart.yaml, Helm release có thể tăng revision không?
6. **helm template** khác **helm install** ở điểm nào?
7. Vì sao nên chạy helm lint và render trước khi deploy AKS?
8. Khi HPA đã bật, vì sao không nên ép replicas cố định trong mỗi lần upgrade?
9. **helm upgrade --install** giải quyết tình huống gì của pipeline?
10. **--wait** và **--atomic** giúp gì và những giới hạn nào?
11. Helm rollback có phục hồi được database migration hay file Blob đã xóa không?
12. Tại sao không nên lưu mật khẩu production trong Helm values?
13. Khi Pod gặp ImagePullBackOff sau khi Helm install thành công, cần kiểm tra những lớp nào?
14. Khi nào nên dùng Helm chart OCI trong ACR và nó khác container image như thế nào?
15. Vì sao pin image digest giúp môi trường staging và production dùng đúng artifact?
16. Helm hooks hữu ích nhưng có những rủi ro side effect nào?
17. Một chart bên thứ ba có thể tạo quyền cluster-wide bằng cách nào?
18. Tại sao không nên dùng Helm CLI và GitOps controller cùng sửa một release không có ownership rõ?
19. Khi uninstall chart, những tài nguyên nào có thể vẫn còn?
20. Nếu release status deployed nhưng API trả 503, bạn sẽ điều tra thế nào?

## 38. Tổng kết

**Helm giúp đóng gói, cấu hình, phân phối và quản lý vòng đời ứng dụng trên AKS**. Một **chart** chứa metadata, templates và values; một **release** là lần cài đặt chart có lịch sử revisions. Các lệnh cốt lõi gồm **helm lint**, **helm template**, **helm install**, **helm upgrade**, **helm history**, **helm rollback**, **helm test** và **helm uninstall**.

Trong hệ sinh thái Azure, hãy kết hợp Helm với **AKS**, **ACR**, **Microsoft Entra ID/managed identity**, **Key Vault**, **Azure Monitor** và quy trình **CI/CD hoặc GitOps** có kiểm soát. Chú trọng dựng manifest đúng, pin chart/image version, phân quyền tối thiểu, không đưa secrets vào release metadata, thiết kế health/rollout/rollback phù hợp và hiểu rằng Helm rollback **không thay thế backup hay phục hồi dữ liệu**.

Quy trình đáng tin cậy là **build một lần → push image lên ACR → ghi digest → lint/render/chart checks → deploy staging → kiểm thử → phát hành production → theo dõi → rollback có kế hoạch khi cần**. Helm làm quá trình này lặp lại được, nhưng chất lượng vận hành phụ thuộc vào kiến trúc ứng dụng, bảo mật, dữ liệu và các kiểm chứng trên AKS thực tế.
