# Nạp image cục bộ vào cluster thử nghiệm

Trong chương **Phát triển cục bộ** của module **SPRING_CLOUD_KUBERNETES**, một vòng thử nghiệm thường gồm: sửa ứng dụng Spring, tạo container image, đưa image tới node, triển khai Pod rồi kiểm tra kết quả. Bài này hướng dẫn thực hiện vòng đó bằng **kind** hoặc **minikube**, với một ứng dụng Spring Boot nhỏ.

Kết quả cần đạt là biết image đang nằm ở đâu, nạp đúng image vào đúng cluster và chứng minh Pod đang chạy đúng bản build. Đây là nền tảng để thực hành DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher: nếu ứng dụng chưa khởi động được từ image mong muốn, các phép thử tích hợp phía sau chưa có cơ sở đáng tin cậy.

## 1. Mục tiêu và phạm vi thực hành

Sau bài học, bạn có thể:

- Giải thích vì sao `docker image ls` nhìn thấy image nhưng Pod vẫn báo thiếu image.
- Build image Spring Boot với tên và tag rõ ràng, rồi nạp vào kind hoặc minikube.
- Chọn `imagePullPolicy` phù hợp với image chỉ có trong máy thử nghiệm.
- Đọc trạng thái rollout, image reference, image ID và mã bản build của ứng dụng.
- Lặp lại quy trình với phiên bản mới, xử lý lỗi thường gặp và nhận ra khi nào nên chuyển sang registry.

Lab tập trung vào việc phân phối image. Ứng dụng mẫu chỉ dùng Web và Actuator; các tính năng gọi Kubernetes API sẽ được bổ sung khi thực hành tích hợp Spring Cloud Kubernetes. Nhờ vậy, mỗi dấu hiệu lỗi trong lab có thể được đối chiếu với một bước cụ thể: build, load, tạo container hoặc khởi động ứng dụng.

## 2. Image trên máy phát triển và image trên node

Container image gồm các lớp filesystem cùng metadata để chạy ứng dụng. Registry là nơi phân phối image; node dùng container runtime để tạo container từ image.

Với cluster cục bộ chạy trong container hoặc máy ảo, có nhiều nơi lưu image:

| Vị trí | Ví dụ | Cách quan sát |
| --- | --- | --- |
| Docker daemon mà CLI đang kết nối | Docker Desktop trên máy lập trình | `docker context show`, `docker image ls` |
| Runtime của một node Kubernetes | containerd bên trong node kind | Kiểm tra image bằng công cụ của runtime trên node |
| Registry | Registry của nhóm phát triển | Kiểm tra repository, tag và digest trên registry |

Một image xuất hiện ở vị trí đầu tiên chưa chứng minh rằng runtime trên node đã có image đó. Tên kubeconfig context cũng độc lập với Docker context.

~~~mermaid
flowchart LR
    S["Mã nguồn Spring Boot"] --> B["Build image trên máy phát triển"]
    B --> H["Kho image của Docker daemon"]
    H --> L["kind load / minikube image load"]
    L --> N1["Image trong runtime node 1"]
    L --> N2["Image trong runtime node 2, nếu có"]
    N1 --> P1["Pod được lập lịch lên node 1"]
    N2 --> P2["Pod được lập lịch lên node 2"]
~~~

Sơ đồ mô tả đích cần đạt khi dùng nhiều node: mọi node có thể nhận Pod đều cần truy cập được image. Image không thuộc namespace Kubernetes; namespace phân tách các tài nguyên như Deployment và Service, còn khả năng tạo container phụ thuộc runtime của node được chọn.

## 3. Chuẩn bị môi trường và quy ước

Cần có:

- JDK và Maven Wrapper phù hợp với dự án Spring Boot đang học.
- Một dự án Maven Spring Boot chạy được, có Spring Web, Actuator và `spring-boot-maven-plugin`.
- Docker daemon hoạt động với Linux containers.
- `kubectl` và một trong hai công cụ: `kind` hoặc `minikube`.
- Mạng để tải dependency, builder/run image hoặc node image nếu chúng chưa được cache.

Giữ bộ phiên bản Spring Boot, Spring Cloud và Spring Cloud Kubernetes tương thích mà dự án đã chọn. Việc nạp image không yêu cầu nâng các dependency.

Các lệnh dưới đây dùng **PowerShell**, chạy tại thư mục dự án ứng dụng. Trên Linux/macOS, đổi `.\mvnw.cmd` thành `./mvnw` và dùng cú pháp biến tương ứng của shell.

Đặt các biến dùng chung:

~~~powershell
$clusterName = "sck-dev"
$namespace = "sck-local"
$imageV1 = "docker.io/library/catalog-api:dev-001"
~~~

`docker.io/library/catalog-api:dev-001` là image reference dùng nhất quán trong lab. Tên này không có nghĩa image đã được push lên Docker Hub. Với quy trình load và pull policy phù hợp, ứng dụng được chạy từ image đã nạp trên node.

Kiểm tra Docker trước khi build:

~~~powershell
docker context show
docker info
~~~

Nếu Docker CLI trỏ tới daemon khác với daemon mà bạn định dùng để build và load, hãy xử lý sự khác biệt đó trước. Đặc biệt, một terminal từng chạy `minikube docker-env` có thể đang trỏ sang Docker bên trong minikube. Xem [hướng dẫn các cách đưa image vào minikube](https://minikube.sigs.k8s.io/docs/handbook/pushing/).

### Chọn một cluster

**Nhánh A — kind:**

~~~powershell
kind create cluster --name $clusterName
$kubeContext = "kind-$clusterName"
~~~

Nếu cluster đã tồn tại, giữ cluster đó và chỉ gán `$kubeContext`. Có thể xem các cluster hiện có bằng `kind get clusters`.

**Nhánh B — minikube:**

~~~powershell
minikube start -p $clusterName --driver=docker
$kubeContext = $clusterName
~~~

Nếu dùng driver khác đã được thiết lập, giữ driver của môi trường. Các ví dụ chính giả định cluster một node; phần nhiều node được đề cập ở cuối bài.

Sau khi chọn **một nhánh**, kiểm tra đúng đích:

~~~powershell
kubectl --context $kubeContext cluster-info
kubectl --context $kubeContext get nodes -o wide
kubectl --context $kubeContext get nodes -o "custom-columns=NAME:.metadata.name,OS:.status.nodeInfo.operatingSystem,ARCH:.status.nodeInfo.architecture"
~~~

Ghi nhận hệ điều hành và kiến trúc node. Image phải có biến thể chạy được trên nền tảng đó, chẳng hạn `linux/amd64` hoặc `linux/arm64`.

## 4. Tạo dấu hiệu nhận biết bản build trong ứng dụng

Một tag đẹp chưa đủ để nhận biết mã thực sự đang chạy. Dùng endpoint nhỏ trả về một giá trị **được biên dịch vào ứng dụng** và tên Pod.

Ví dụ lớp chính, đặt đúng package của dự án:

~~~java
package com.example.catalog;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CatalogApplication {

    private static final String BUILD_MARKER = "dev-001";

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @GetMapping("/build")
    public Map<String, String> build() {
        String pod = System.getenv().getOrDefault("POD_NAME", "local-process");
        return Map.of("build", BUILD_MARKER, "pod", pod);
    }
}
~~~

Nếu dự án đã có lớp `@SpringBootApplication`, giữ lớp đó và đưa endpoint vào một controller được component scan. Không tạo thêm lớp main gây mơ hồ cho quá trình đóng gói.

Cấu hình mẫu trong `application.yml` của ứng dụng:

~~~yaml
spring:
  application:
    name: catalog-api

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
~~~

Lab giả định ứng dụng phục vụ `/build` và các health endpoint trên cổng 8080, không yêu cầu xác thực. Nếu dự án có Spring Security hoặc management port riêng, cần điều chỉnh endpoint/probe theo cấu hình thực tế.

Actuator cung cấp các health group cho liveness và readiness; cấu hình trên bật probes một cách tường minh. Xem [tài liệu Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

## 5. Build image Spring Boot trên máy phát triển

Với Spring Boot Maven Plugin, có thể tạo OCI image bằng Cloud Native Buildpacks mà không cần Dockerfile cho lab này:

~~~powershell
.\mvnw.cmd clean spring-boot:build-image "-Dspring-boot.build-image.imageName=$imageV1" "-Dspring-boot.build-image.publish=false"
if ($LASTEXITCODE -ne 0) { throw "Build image thất bại; dừng trước bước load." }
~~~

Goal `build-image` thực hiện lifecycle cần thiết để đóng gói ứng dụng và cần truy cập Docker daemon. Tham số `publish=false` yêu cầu giữ kết quả ở Docker daemon thay vì publish image lên registry. Builder và run image vẫn có thể cần được tải từ mạng trong quá trình build. Tham khảo [Spring Boot: Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html).

Kiểm tra image đầu ra:

~~~powershell
docker image inspect $imageV1 --format '{{.Id}} {{.Os}}/{{.Architecture}}'
if ($LASTEXITCODE -ne 0) { throw "Không tìm thấy image trong Docker daemon hiện tại." }
~~~

Lưu lại tên, tag và nền tảng image. Trong lab, `dev-001` đại diện cho đúng một lần build; lần sửa tiếp theo sẽ dùng `dev-002`.

Nếu dự án đã có Dockerfile, có thể dùng quy trình build của dự án thay cho Buildpacks. Với Buildx và builder không tự đưa kết quả về Docker image store, dùng `--load` cho kết quả một nền tảng:

~~~powershell
docker buildx build --load --platform linux/amd64 -t $imageV1 .
~~~

Lệnh này giả định thư mục hiện tại đã có Dockerfile hợp lệ và node là `linux/amd64`; đổi platform theo kết quả kiểm tra node. `--load` đưa kết quả về Docker daemon, chưa đưa image vào node Kubernetes. Xem [Docker Buildx build](https://docs.docker.com/reference/cli/docker/buildx/build/).

## 6. Nạp image vào cluster đã chọn

Chỉ thực hiện nhánh tương ứng với cluster đang dùng.

### 6.1. Với kind

~~~powershell
kind load docker-image $imageV1 --name $clusterName
if ($LASTEXITCODE -ne 0) { throw "Load image vào kind thất bại." }
~~~

Tham số `--name` phải đúng cluster đã tạo. Việc `kubectl` trỏ tới context nào không thay thế tham số này.

Trong môi trường kind dùng Docker provider của lab, có thể xem image bên trong từng node:

~~~powershell
$kindNodes = kind get nodes --name $clusterName
foreach ($nodeName in $kindNodes) {
    Write-Output "Node: $nodeName"
    docker exec $nodeName crictl images
}
~~~

Tìm repository `catalog-api` với tag `dev-001`. Việc runtime chuẩn hóa tên có thể làm cách hiển thị khác đôi chút; vẫn phải đối chiếu đúng repository và tag.

Các thao tác load, load archive và kiểm tra bằng `crictl` được mô tả trong [kind Quick Start](https://kind.sigs.k8s.io/docs/user/quick-start/#loading-an-image-into-your-cluster).

### 6.2. Với minikube

~~~powershell
minikube -p $clusterName image load $imageV1 --daemon
if ($LASTEXITCODE -ne 0) { throw "Load image vào minikube thất bại." }

minikube -p $clusterName image ls
~~~

`-p` chọn đúng profile. `--daemon` chỉ rõ lấy image từ Docker daemon. Kiểm tra danh sách có `catalog-api:dev-001` trước khi triển khai.

Minikube cũng có `image build` để build trong môi trường cluster; lab chọn build ở máy phát triển rồi load để dùng cùng một quy trình cho cả hai loại cluster. Xem [tham chiếu minikube image](https://minikube.sigs.k8s.io/docs/commands/image/).

## 7. Chọn imagePullPolicy cho lab

Pull policy điều khiển việc lấy image khi container được khởi động:

| Policy | Khi image đã có trên node | Khi chưa có | Dùng trong lab |
| --- | --- | --- | --- |
| `Never` | Dùng image trên node | Tạo container thất bại | Phù hợp để kiểm chứng load |
| `IfNotPresent` | Dùng image trên node | Thử pull từ registry | Dùng khi chấp nhận cơ chế dự phòng |
| `Always` | Vẫn cần liên hệ registry để giải quyết image reference | Thử pull | Cần registry truy cập được |

`Always` có thể tái sử dụng layer đã cache sau khi xác định image; không đồng nghĩa tải lại mọi layer.

Lab đặt **`Never` tường minh** để việc quên load xuất hiện rõ. Kubernetes mặc định thường chọn `Always` với `:latest` hoặc không ghi tag, và `IfNotPresent` với tag khác. Policy đã được mặc định hóa không tự đổi chỉ vì sửa tag sau đó. Chi tiết ở [Kubernetes Images](https://kubernetes.io/docs/concepts/containers/images/#image-pull-policy).

## 8. Triển khai ứng dụng từ image đã nạp

Lưu manifest mẫu dưới tên `k8s-local.yml` trong dự án thực hành:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sck-local
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: sck-local
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      automountServiceAccountToken: false
      containers:
        - name: catalog-api
          image: docker.io/library/catalog-api:dev-001
          imagePullPolicy: Never
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 60
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
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 768Mi
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: sck-local
spec:
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Các lựa chọn của ví dụ:

- `image` khớp hoàn toàn với tên đã build và load.
- `POD_NAME` lấy từ metadata của Pod để giúp nhận biết instance trả lời.
- Startup probe cho ứng dụng khoảng thời gian khởi động trước khi liveness/readiness bắt đầu tác động.
- Readiness kiểm tra khả năng nhận lưu lượng; liveness kiểm tra tình trạng sống của tiến trình.
- Resource là mức khởi đầu cho ứng dụng nhỏ, cần điều chỉnh theo nhu cầu đo được.
- `automountServiceAccountToken: false` phù hợp với ứng dụng mẫu chưa gọi Kubernetes API. Khi thêm client tích hợp cần xác thực trong cluster, phải cấu hình ServiceAccount, token và RBAC tương ứng.

Áp dụng và chờ rollout:

~~~powershell
kubectl --context $kubeContext apply -f .\k8s-local.yml
if ($LASTEXITCODE -ne 0) { throw "Apply manifest thất bại." }

kubectl --context $kubeContext -n $namespace rollout status deployment/catalog-api --timeout=300s
kubectl --context $kubeContext -n $namespace get pods -l app=catalog-api -o wide
~~~

Một lần chạy thành công cần có Deployment rollout hoàn tất và Pod đạt `1/1 Ready`. `Running` đơn lẻ chưa chứng minh readiness đã đạt.

`rollout status` theo dõi quá trình triển khai; khi timeout, dùng thông tin Pod và Events để tìm nguyên nhân. Xem [kubectl rollout status](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_status/).

## 9. Kiểm chứng image và mã thực sự đang chạy

### 9.1. Quan sát từng Pod

Lấy thông tin container từ kết quả Kubernetes:

~~~powershell
$podList = kubectl --context $kubeContext -n $namespace get pods -l app=catalog-api -o json | ConvertFrom-Json

foreach ($pod in $podList.items) {
    $container = $pod.status.containerStatuses |
        Where-Object { $_.name -eq "catalog-api" }

    [pscustomobject]@{
        Pod = $pod.metadata.name
        Node = $pod.spec.nodeName
        RequestedImage = $pod.spec.containers[0].image
        RuntimeImageID = $container.imageID
        Ready = $container.ready
        Restarts = $container.restartCount
    }
}
~~~

Đọc các thông tin cùng nhau:

| Dấu hiệu | Điều nó giúp xác nhận |
| --- | --- |
| `RequestedImage` | PodSpec yêu cầu repository/tag nào |
| `Node` | Node nào cần có image |
| `RuntimeImageID` | Định danh image runtime báo cho container |
| `Ready` và `Restarts` | Container có sẵn sàng và có đang khởi động lại hay không |
| Endpoint `/build` | Mã ứng dụng đang chạy trả về dấu hiệu bản build nào |

`RuntimeImageID` có thể có định dạng khác nhau tùy runtime. Không mặc định nó phải bằng chuỗi `.Id` của `docker image inspect`: hai công cụ có thể đang hiển thị các loại định danh khác nhau. Lưu các giá trị để đối chiếu khi cần điều tra.

### 9.2. Gọi endpoint từ máy phát triển

Mở một terminal giữ lệnh sau hoạt động:

~~~powershell
kubectl --context $kubeContext -n $namespace port-forward service/catalog-api 8080:80
~~~

Ở terminal PowerShell thứ hai:

~~~powershell
Invoke-RestMethod http://localhost:8080/build
Invoke-RestMethod http://localhost:8080/actuator/health/readiness
~~~

Kết quả mong đợi của `/build` chứa `build = dev-001` và tên Pod. Health readiness trả trạng thái `UP`.

Port-forward qua Service chọn một Pod để chuyển tiếp. Nó giúp truy cập lab, nhưng phép thử này chưa xác nhận đường đi ClusterIP, DNS nội bộ hoặc thuật toán Spring Cloud LoadBalancer. Khi Pod được thay thế, có thể cần dừng và chạy lại port-forward. Tham khảo [kubectl port-forward](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/).

## 10. Lặp lại với bản build mới

Giả sử sửa `BUILD_MARKER` trong mã Java thành `dev-002`. Thực hiện theo đúng thứ tự: **build → load → đổi image của Deployment → chờ rollout → gọi lại ứng dụng**.

### Bước 1 — Build với tag mới

~~~powershell
$imageV2 = "docker.io/library/catalog-api:dev-002"

.\mvnw.cmd clean spring-boot:build-image "-Dspring-boot.build-image.imageName=$imageV2" "-Dspring-boot.build-image.publish=false"
if ($LASTEXITCODE -ne 0) { throw "Build dev-002 thất bại." }

docker image inspect $imageV2
~~~

### Bước 2 — Nạp vào cluster đang dùng

Với kind:

~~~powershell
kind load docker-image $imageV2 --name $clusterName
if ($LASTEXITCODE -ne 0) { throw "Load dev-002 vào kind thất bại." }
~~~

Hoặc với minikube:

~~~powershell
minikube -p $clusterName image load $imageV2 --daemon
if ($LASTEXITCODE -ne 0) { throw "Load dev-002 vào minikube thất bại." }
~~~

### Bước 3 — Yêu cầu Deployment dùng tag mới

~~~powershell
kubectl --context $kubeContext -n $namespace set image deployment/catalog-api "catalog-api=$imageV2"
kubectl --context $kubeContext -n $namespace rollout status deployment/catalog-api --timeout=300s
kubectl --context $kubeContext -n $namespace get pods -l app=catalog-api -o wide
~~~

Đồng thời cập nhật `image` trong `k8s-local.yml` thành `docker.io/library/catalog-api:dev-002` để file đang quản lý phản ánh đúng phiên bản mong muốn. Nếu giữ manifest cũ rồi apply lại, bạn sẽ yêu cầu quay về `dev-001`.

Đổi image trong Pod template làm Deployment tạo rollout. Build hoặc load image đơn thuần không thay Pod đang chạy. Nếu giữ nguyên tag, apply một manifest không đổi cũng không tạo rollout mới. Cơ chế cập nhật Pod template được mô tả trong [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#updating-a-deployment).

### Bước 4 — Xác nhận bản mới

Chạy lại port-forward khi cần rồi gọi `/build`. Kết quả phải là `dev-002`. Xem cả danh sách Pod và image ID sau rollout để tránh kết luận chỉ từ thông báo build thành công.

Trong lab nhiều replica, hãy xác nhận trạng thái của toàn bộ Pod thuộc Deployment. Một lần gọi HTTP chỉ cho biết phiên bản của instance đã trả lời lần gọi đó.

### Khi buộc phải tái sử dụng tag

Có thể build đè tag, load lại vào các node rồi dùng `rollout restart`. Tuy nhiên, cách này khiến việc xác định bản đang chạy khó hơn và có thể dùng image cũ nếu một node chưa được cập nhật. Nên dùng tag mới cho mỗi bản build thử nghiệm; quy ước tag chỉ có giá trị nếu bạn thực sự không ghi đè tag cũ.

Nếu cần quay lại bản trước:

~~~powershell
kubectl --context $kubeContext -n $namespace rollout undo deployment/catalog-api
kubectl --context $kubeContext -n $namespace rollout status deployment/catalog-api --timeout=300s
~~~

Với policy `Never`, rollback chỉ chạy được khi image của revision trước còn tồn tại trên các node cần dùng. Đồng bộ lại manifest sau khi chọn phiên bản sẽ giữ.

## 11. Nạp bằng archive khi cần chuyển image giữa môi trường

Nếu image được build ở daemon khác hoặc cần chuyển sang máy thử nghiệm, lưu image thành archive:

~~~powershell
docker image save --output .\catalog-api-dev-001.tar $imageV1
~~~

Sau đó chọn một cách load:

~~~powershell
kind load image-archive .\catalog-api-dev-001.tar --name $clusterName
~~~

Hoặc:

~~~powershell
minikube -p $clusterName image load .\catalog-api-dev-001.tar
~~~

`docker image save` lưu image để nạp lại, gồm các layer và thông tin image liên quan. `docker export` xuất filesystem của một container, không thay thế thao tác lưu image cho quy trình này. Xem [docker image save](https://docs.docker.com/reference/cli/docker/image/save/).

Dù dùng archive, vẫn phải chọn đúng platform, tag và pull policy. Nạp image ứng dụng không bảo đảm toàn bộ lab hoạt động offline: node image, dependency Maven, builder image, sidecar hoặc image của các thành phần khác vẫn có thể cần mạng.

## 12. Chẩn đoán lỗi theo đúng bước

Bắt đầu bằng trạng thái và Events:

~~~powershell
kubectl --context $kubeContext -n $namespace get pods -l app=catalog-api -o wide
kubectl --context $kubeContext -n $namespace describe pods -l app=catalog-api
kubectl --context $kubeContext -n $namespace get events --sort-by=.metadata.creationTimestamp
~~~

| Hiện tượng | Điểm cần kiểm tra | Hướng xử lý trong lab |
| --- | --- | --- |
| `ErrImageNeverPull` | Runtime trên node chưa có image đúng tên/tag | Load lại đúng cluster, kiểm tra node nhận Pod |
| `ErrImagePull` hoặc `ImagePullBackOff` | Manifest đang cho phép/yêu cầu pull nhưng image không lấy được | Đọc Events; kiểm tra reference, policy, registry và xác thực nếu thực sự dùng registry |
| Load báo không tìm thấy image | Docker daemon được loader dùng không có image | Kiểm tra Docker context, inspect image; có thể chuyển bằng archive |
| Image đã load nhưng Pod ở cluster khác | Context của `kubectl` không khớp cluster/profile của loader | Đối chiếu `$kubeContext`, `--name` và `-p` |
| `exec format error` | Image có thể sai kiến trúc hoặc executable không hợp lệ | Đối chiếu platform của image với node; xem entrypoint |
| `CrashLoopBackOff` | Container đã được tạo nhưng tiến trình liên tục thoát | Đọc log, kiểm tra cấu hình/JVM/dependency |
| Pod `Running` nhưng chưa Ready | Probe không nhận được phản hồi phù hợp | Kiểm tra path, port, xác thực và thời gian khởi động |
| Rollout giữ cả Pod cũ lẫn Pod mới lỗi | Bản mới chưa đạt điều kiện để thay hết bản cũ | Điều tra Pod mới; không coi việc Pod cũ còn phục vụ là rollout thành công |
| `/build` vẫn trả `dev-001` | Chưa đổi Pod template, gọi nhầm Pod hoặc bản build chưa chứa mã mới | Kiểm tra requested image, marker trong mã, rollout và port-forward |

Khi container đã khởi động, xem log:

~~~powershell
kubectl --context $kubeContext -n $namespace logs deployment/catalog-api --tail=100
~~~

Lệnh trên lấy log từ Pod được chọn cho Deployment. Khi điều tra nhiều replica, lấy tên Pod cụ thể từ `get pods` rồi chạy `logs` cho đúng Pod; thêm `--previous` nếu cần log của lần chạy container trước.

Nếu container còn đang chờ image, có thể chưa có log ứng dụng. Khi đó, Events và kho image trên node là các bằng chứng cần đọc trước.

Phân biệt lỗi phân phối image với lỗi tích hợp Spring Cloud Kubernetes: lỗi `403 Forbidden` khi ứng dụng gọi API cần kiểm tra ServiceAccount/RBAC; lỗi discovery rỗng cần kiểm tra namespace, nhãn và tài nguyên được khám phá. Nạp lại image không tự sửa các vấn đề cấu hình đó.

## 13. Nhiều node và giới hạn của cách load cục bộ

Với nhiều node, một lần chạy thành công chưa chứng minh image có mặt ở mọi nơi. Hãy kiểm tra image trên từng node có thể nhận Pod, sau đó đối chiếu cột `NODE` của các Pod thực tế.

Đối với kind, dùng danh sách node và vòng kiểm tra `crictl` đã trình bày. Với minikube, kiểm tra hành vi load của phiên bản và profile đang dùng; nếu build trực tiếp bằng `minikube image build`, chú ý tùy chọn `--all` khi cần build trên mọi node. Không dùng việc `docker image ls` ở máy phát triển để thay cho các kiểm tra này.

Nếu tạo lại cluster hoặc thêm node, hãy coi image ứng dụng cần được nạp và xác minh lại. Dữ liệu image cục bộ có thể mất khi node bị xóa hoặc được runtime dọn dẹp.

| Nhu cầu | Cách phân phối phù hợp |
| --- | --- |
| Một người thử nhanh trên cluster cá nhân | Build rồi load bằng công cụ cluster |
| Chuyển một bản thử giữa hai máy | Save/load archive, ghi rõ tag và platform |
| Nhóm phát triển chia sẻ image thường xuyên | Registry mà mọi node truy cập được |
| CI hoặc môi trường có node thay đổi | Publish image, quản lý định danh bản phát hành và thông tin xác thực |

Registry đặt tại `localhost` của máy phát triển cần cấu hình mạng phù hợp để node truy cập; `localhost` bên trong node chỉ chính node đó. Khi chuyển sang registry, phải thiết kế địa chỉ truy cập, bảo mật và pull policy theo môi trường mới.

## 14. Áp dụng vào bài thực hành Spring Cloud Kubernetes

Sau khi vòng image đã ổn định, giữ nguyên quy trình build–load–rollout cho ứng dụng có các tích hợp khác:

- **DiscoveryClient và Spring Cloud LoadBalancer:** kiểm chứng các Pod đã chạy đúng bản trước khi kiểm tra danh sách instance và định tuyến.
- **ConfigMap và Secret:** tách thay đổi mã cần build image khỏi thay đổi cấu hình ngoài image; cơ chế cập nhật cấu hình phụ thuộc cách ứng dụng nạp chúng.
- **Configuration Watcher:** xác định riêng image của ứng dụng và image của watcher nếu watcher được triển khai; mỗi workload có yêu cầu phân phối image riêng.
- **RBAC:** cấp quyền theo tính năng thực sự dùng. Việc tải image do hạ tầng node/runtime đảm nhiệm, còn quyền đọc tài nguyên Kubernetes của ứng dụng là phần cấu hình khác.
- **Sức khỏe Pod:** tiếp tục quan sát startup, readiness, liveness và log sau khi thêm tích hợp.

Không đưa kubeconfig hay Secret thật vào image để tiện chạy lab. Dùng cấu hình ngoài image và cơ chế xác thực phù hợp với bài thực hành. Với workload cần Kubernetes API, điều chỉnh cấu hình ServiceAccount và `automountServiceAccountToken` của manifest mẫu theo quyền đã thiết kế.

## 15. Thực hành tự kiểm chứng

Thực hiện tuần tự và ghi lại bằng chứng ngắn cho mỗi bước:

1. Build `dev-001`, load vào cluster đã chọn, rollout thành công và nhận `dev-001` từ `/build`.
2. Dùng một tag mới chưa được build/load cùng policy `Never`; quan sát Events để nhận biết lỗi thiếu image.
3. Build và load tag đó, chờ hoặc yêu cầu triển khai lại, rồi xác nhận Pod khởi động.
4. Sửa marker thành `dev-002`, build/load `dev-002`, đổi image Deployment và xác nhận phản hồi mới.
5. Giải thích vì sao chỉ build/load mà không đổi Pod template chưa cập nhật tiến trình đang chạy.
6. Nếu dùng nhiều node, ghi tên node của từng Pod và kiểm tra image trên các node liên quan.

Hoàn thành khi bạn có thể chỉ ra đủ: **image reference đã build, cluster nhận image, node chạy Pod, trạng thái Ready và marker mà ứng dụng trả về**.

Sau khi thực hành xong, có thể xóa các tài nguyên của lab bằng manifest, với điều kiện namespace `sck-local` chỉ chứa tài nguyên dành riêng cho bài:

~~~powershell
kubectl --context $kubeContext delete -f .\k8s-local.yml
~~~

Manifest có cả Namespace nên thao tác này cũng xóa các tài nguyên nằm trong namespace đó. Cluster và image trên node có vòng đời riêng; xóa workload không đồng nghĩa xóa image khỏi runtime.
