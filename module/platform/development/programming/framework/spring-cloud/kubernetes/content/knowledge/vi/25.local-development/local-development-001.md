# Chọn kind, minikube hoặc môi trường Kubernetes tương đương

## 1. Mục tiêu của việc chọn môi trường

Trong chương **Phát triển cục bộ** của module **SPRING_CLOUD_KUBERNETES**, môi trường Kubernetes là nơi kiểm chứng cách ứng dụng Spring sử dụng Service, ConfigMap, Secret và danh tính ServiceAccount. Một ứng dụng chạy được bằng IDE chưa chứng minh rằng nó đọc được Kubernetes API, tìm đúng instance hoặc nhận cấu hình trong Pod.

Sau bài này, bạn cần:

- Chọn được kind, minikube hoặc một môi trường tương đương dựa trên mục tiêu kiểm thử.
- Tạo cụm riêng, xác nhận context và đưa image ứng dụng vào đúng cụm.
- Triển khai một ứng dụng Spring, truy cập từ máy phát triển và từ bên trong cụm.
- Phân biệt kiểm thử nền tảng Kubernetes với kiểm thử các tính năng Spring Cloud Kubernetes.
- Biết bằng chứng nào còn thiếu trước khi kết luận DiscoveryClient, cấu hình hoặc cơ chế refresh hoạt động.

Nếu bắt đầu học và đã có Docker chạy Linux containers, **kind là lựa chọn mặc định hợp lý cho bài thực hành này**. Chọn **minikube** khi cần quy trình quản lý cụm qua profile, lựa chọn driver hoặc các tiện ích hỗ trợ thao tác cục bộ. Một cụm khác vẫn phù hợp nếu vượt qua các kiểm tra chức năng ở cuối bài; tên công cụ không phải tiêu chí quyết định duy nhất.

Đây là khuyến nghị cho tình huống học tập cụ thể. Máy ít tài nguyên, chính sách công ty, kiến trúc CPU và nhu cầu kiểm thử mạng có thể dẫn đến lựa chọn khác.

## 2. Hiểu đúng những thành phần đang lựa chọn

### 2.1. Công cụ tạo cụm không phải thư viện Spring

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Công cụ tạo và quản lý cụm | Tạo node, control plane và cấu hình truy cập | kind, minikube |
| Nền tảng chạy node cục bộ | Cung cấp container hoặc máy ảo cho node | Docker, driver máy ảo của minikube |
| Container runtime trong node | Chạy container của Pod | containerd hoặc runtime được cấu hình |
| Kubernetes | Điều phối Pod, Service, cấu hình và phân quyền API | Deployment, ServiceAccount, Role |
| Spring Cloud Kubernetes | Tích hợp ứng dụng Spring với tài nguyên Kubernetes | DiscoveryClient, PropertySource, LoadBalancer, Configuration Watcher |
| kubectl | Gửi yêu cầu quản trị tới API server | apply, logs, describe, auth can-i |

Ví dụ, minikube dùng Docker driver không có nghĩa mọi image build bằng Docker trên máy phát triển đã xuất hiện trong kho image của node. Tương tự, kind dùng container làm node không biến mỗi Pod thành một container có thể quản lý trực tiếp bằng Docker trên host.

Tài liệu [kiến trúc sử dụng kind](https://kind.sigs.k8s.io/docs/user/quick-start/) và [các driver của minikube](https://minikube.sigs.k8s.io/docs/drivers/) mô tả hai cách tổ chức môi trường này.

### 2.2. Hai vị trí chạy ứng dụng tạo ra hai bài toán khác nhau

~~~mermaid
flowchart LR
    IDE["Ứng dụng Spring trong IDE"] -->|"kubectl / kubeconfig"| API["Kubernetes API server"]
    IDE -->|"localhost:18080 qua port-forward"| PF["Một Pod được chọn"]
    subgraph Cluster["Cụm Kubernetes"]
        API
        PF
        APP["Ứng dụng Spring trong Pod"] -->|"ServiceAccount và RBAC"| API
        APP -->|"DNS Service và mạng nội bộ"| SVC["Service của ứng dụng khác"]
    end
~~~

Trong sơ đồ, ứng dụng chạy trong IDE chỉ gọi API khi bạn chủ động cấu hình Kubernetes client; kubectl là một client khác cũng sử dụng kubeconfig. Chúng không tự chia sẻ danh tính với ứng dụng trong Pod.

**Chạy trong IDE** thuận tiện cho debug và vòng lặp sửa mã. Bạn phải tự giải quyết quyền truy cập API và đường mạng tới dịch vụ đích.

**Chạy trong Pod** phù hợp để kiểm chứng namespace, ServiceAccount, RBAC, DNS nội bộ, probe và đường gọi giữa các dịch vụ. Đây là chế độ chuẩn của bài thực hành.

Một lỗi thường gặp là DiscoveryClient chạy trên laptop trả về địa chỉ Pod rồi ứng dụng gọi địa chỉ đó thất bại. Truy vấn API thành công chỉ chứng minh đường tới API server; nó chưa chứng minh laptop có route tới Pod CIDR. Đổi công cụ tạo cụm có thể không giải quyết được nguyên nhân này.

## 3. So sánh theo công việc cần hoàn thành

| Tiêu chí | kind | minikube | Môi trường tương đương |
| --- | --- | --- | --- |
| Tình huống phù hợp | Cụm dùng cho lab, tạo lại thường xuyên, kịch bản CI | Học tương tác, quản lý profile, cần driver và tiện ích cục bộ | Tận dụng cụm đã có hoặc cần gần môi trường của nhóm |
| Cách chạy node | Container trên nền tảng container được hỗ trợ | Container hoặc VM tùy driver | Phụ thuộc sản phẩm và cấu hình |
| Đưa image vào cụm | Load image vào cụm có tên hoặc dùng registry | image load, image build hoặc registry | Xác nhận rõ registry và image store của node |
| Truy cập HTTP từ host | Bắt đầu bằng port-forward; ánh xạ cổng khi cần | Bắt đầu bằng port-forward; có service URL hoặc tunnel theo nhu cầu | Xác minh cơ chế được cung cấp |
| Multi-node | Khai báo các node trong cấu hình | Có thể tạo nhiều node | Kiểm tra hỗ trợ thực tế |
| Khả năng tái tạo | Tốt khi lưu cấu hình và khóa phiên bản | Tốt khi ghi rõ profile, driver và phiên bản | Phải ghi lại cấu hình nền tảng |
| Điểm cần lưu ý | Image trên host và trong node là hai nơi; LoadBalancer cần thành phần phù hợp | Hành vi mạng thay đổi theo driver và hệ điều hành | Tiện ích cài sẵn có thể che khuất phụ thuộc của bài lab |

Các lựa chọn thường gặp khác gồm Kubernetes tích hợp trong Docker Desktop hoặc Rancher Desktop, k3d và một namespace riêng trên cụm phát triển từ xa. Hãy kiểm tra các khả năng trên bản đang dùng thay vì suy rằng mọi sản phẩm đều có hành vi giống nhau.

Đối với cụm dùng chung, bạn có thể chỉ được thao tác trong một namespace và không được tạo Role hoặc dùng impersonation. Hãy ghi rõ giới hạn này khi đánh giá môi trường; một quyền quản trị đã được cấp sẵn trên laptop không thay thế được yêu cầu vận hành của nhóm.

### 3.1. Cây quyết định thực dụng

1. **Cần tạo lại cụm bằng kịch bản, dùng cùng cấu hình trên máy cá nhân và CI?** Bắt đầu với kind.
2. **Cần lựa chọn driver, profile và tiện ích hỗ trợ học Kubernetes?** Bắt đầu với minikube.
3. **Đã có một cụm cục bộ đáp ứng toàn bộ tiêu chí kiểm chứng?** Dùng cụm đó để tránh duy trì thêm control plane.
4. **Cần kiểm chứng một hành vi riêng của môi trường triển khai?** Dùng môi trường có thành phần tương ứng, có thể là namespace phát triển từ xa.
5. **Chỉ đang sửa logic nghiệp vụ?** Chạy kiểm thử hoặc ứng dụng trong IDE trước; đưa vào cụm khi thay đổi liên quan đến tích hợp Kubernetes.

Không bật cả kind và minikube chỉ để “so sánh cho đủ”. Chọn một nhánh, chạy cùng bài lab và ghi lại lý do lựa chọn.

## 4. Chuẩn bị trước khi tạo cụm

### 4.1. Công cụ và tài nguyên

Bài thực hành sử dụng:

- kubectl, Docker CLI và Docker engine chạy Linux containers.
- kind **hoặc** minikube; nhánh minikube bên dưới dùng Docker driver.
- JDK 21 để build ứng dụng mẫu.
- Maven Wrapper của dự án Spring Boot.
- Quyền tải dependency và image, hoặc các bản cache tương ứng.
- Một thư mục lab riêng để lưu những tệp ví dụ trong bài.

Ví dụ khởi đầu có thể dành khoảng 4 CPU và 6–8 GiB RAM cho nền tảng container/VM nếu máy cho phép. Đây là ngân sách thử nghiệm, không phải cấu hình tối thiểu chung. IDE, JVM, số replica và các thành phần bổ sung cùng tiêu thụ tài nguyên; hãy quan sát mức dùng thực tế.

Kiểm tra từ terminal:

~~~powershell
docker version
kubectl version --client
java -version
~~~

Chạy thêm đúng công cụ đã chọn:

~~~powershell
kind version
~~~

Hoặc:

~~~powershell
minikube version
~~~

Nếu Docker CLI hiện thông tin client nhưng báo không kết nối được daemon, hãy xử lý nền tảng container trước. Tạo cụm Kubernetes lúc này thường chỉ tạo thêm lỗi thứ cấp.

### 4.2. Ghi lại những gì cần tái tạo

Trước khi chia sẻ bài lab cho người khác, ghi lại:

| Thông tin | Mục đích |
| --- | --- |
| Hệ điều hành, kiến trúc amd64/arm64 | Phát hiện image hoặc công cụ không phù hợp kiến trúc |
| Phiên bản kind/minikube và driver | Tái hiện quá trình tạo node |
| Phiên bản Kubernetes và node image | Tái hiện API, mặc định và lỗi tương thích |
| Phiên bản Spring Boot và Spring Cloud BOM nếu có | Tránh ghép các dependency không tương thích |
| Cluster context và namespace | Giảm nhầm đích của kubectl |
| Tag hoặc digest image ứng dụng | Biết chính xác mã nào đang được chạy |
| Thành phần mạng được cài thêm | Biết điều kiện để Service, Ingress hoặc NetworkPolicy hoạt động |

Các lệnh tạo cụm bên dưới dùng mặc định của công cụ để bắt đầu nhanh. Khi đưa vào kịch bản tái lập, chọn phiên bản Kubernetes được công cụ hỗ trợ và khóa cấu hình đó. Với kind, chọn node image từ release tương ứng, ưu tiên ghi cả digest; với minikube, ghi rõ giá trị `--kubernetes-version` đã kiểm chứng.

Không thay toàn bộ dependency Spring chỉ vì đổi từ kind sang minikube. Nếu thêm Spring Cloud Kubernetes, đối chiếu Spring Boot với release train ở [trang Spring Cloud](https://spring.io/projects/spring-cloud/), rồi để BOM quản lý các phiên bản liên quan.

### 4.3. Lưu ý cho Windows và WSL

Bạn có thể chạy bài lab từ PowerShell trên Windows hoặc từ một shell trong WSL, nhưng cần thống nhất nơi đặt Docker CLI, kubeconfig và mã nguồn. Một kubeconfig dùng được trong PowerShell không tự chứng minh rằng đường dẫn chứng chỉ hoặc địa chỉ API server cũng dùng được trong WSL.

Các lệnh kubectl trong bài được viết trên một dòng để dễ dùng ở nhiều shell. Các biến `$KubeContext` và `$LabNamespace` là cú pháp PowerShell; nếu dùng Bash, đặt chúng theo phần hướng dẫn tương ứng.

## 5. Tạo cụm: chọn đúng một nhánh

### 5.1. Nhánh A — kind

Trong thư mục lab, tạo `kind-local.yaml`:

~~~yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
~~~

Tạo cụm riêng:

~~~powershell
kind create cluster --name sck-local --config kind-local.yaml --wait 120s
kubectl --context kind-sck-local cluster-info
kubectl --context kind-sck-local get nodes -o wide
~~~

Một node đủ cho bước kiểm chứng đầu tiên. Khi cần kiểm thử scheduling giữa các node, có thể tạo lại cụm bằng cấu hình thêm worker:

~~~yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
  - role: worker
~~~

Nhiều node cùng chạy trên một laptop không mô phỏng được độc lập phần cứng hay vùng sẵn sàng của hệ thống thật. Nó vẫn hữu ích để làm rõ image có trên node nào và Pod được schedule ở đâu.

### 5.2. Nhánh B — minikube

Tạo profile riêng bằng Docker driver:

~~~powershell
minikube start -p sck-local --driver=docker --cpus=4 --memory=6144
minikube status -p sck-local
kubectl --context sck-local cluster-info
kubectl --context sck-local get nodes -o wide
~~~

Giá trị bộ nhớ ở đây tính theo MiB. Điều chỉnh theo ngân sách máy và giới hạn mà Docker Desktop hoặc VM được cấp.

Nếu chọn driver khác, xác minh driver đó được hỗ trợ trên hệ điều hành hiện tại và ghi lại quyết định. Không dùng kết quả mạng của một driver để suy ra kết quả của driver khác.

### 5.3. Chốt context cho mọi thao tác phía sau

Nếu chọn kind, đặt:

~~~powershell
$KubeContext = 'kind-sck-local'
$LabNamespace = 'sck-lab'
~~~

Nếu chọn minikube, đặt:

~~~powershell
$KubeContext = 'sck-local'
$LabNamespace = 'sck-lab'
~~~

Với Bash, dùng một trong hai context:

~~~bash
KubeContext=kind-sck-local
LabNamespace=sck-lab
~~~

Với minikube trong Bash, thay dòng đầu bằng `KubeContext=sck-local`.

Kiểm tra trước khi apply:

~~~powershell
kubectl config get-contexts
kubectl --context $KubeContext get nodes
kubectl --context $KubeContext -n kube-system get pods
~~~

Tiếp tục khi node đã `Ready` và các thành phần hệ thống đã ổn định. Bài lab truyền context trực tiếp vào từng lệnh kubectl thay vì phụ thuộc context đang được chọn toàn cục. Nếu mở terminal mới, đặt lại hai biến trước khi chạy tiếp.

## 6. Chuẩn bị ứng dụng Spring tối thiểu

Mục đích của ứng dụng đầu tiên là kiểm chứng đường build → image → Pod → Service. Nó chưa cần DiscoveryClient hoặc quyền đọc Kubernetes API. Khi nền tảng này hoạt động, bạn mới có cơ sở chẩn đoán phần tích hợp Spring Cloud Kubernetes.

### 6.1. Tạo dự án và endpoint quan sát

Tạo dự án Maven tại [Spring Initializr](https://start.spring.io/) với Java 21, một bản Spring Boot ổn định được công cụ hỗ trợ, package `com.example.sckdemo`, artifact `sck-demo` và hai dependency **Spring Web**, **Spring Boot Actuator**. Giải nén vào thư mục `sck-demo`.

Trong tệp main class được tạo, dùng nội dung:

~~~java
package com.example.sckdemo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SckDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SckDemoApplication.class, args);
    }

    @RestController
    static class DemoController {

        private final Environment environment;

        DemoController(Environment environment) {
            this.environment = environment;
        }

        @GetMapping("/hello")
        Map<String, String> hello() {
            return Map.of(
                "message", environment.getProperty("demo.message", "Xin chào từ local"),
                "pod", environment.getProperty("HOSTNAME", "ide"),
                "namespace", environment.getProperty("POD_NAMESPACE", "local"),
                "secretConfigured",
                    Boolean.toString(environment.containsProperty("demo.api-key"))
            );
        }
    }
}
~~~

Endpoint chỉ cho biết cấu hình nhạy cảm có tồn tại hay không; nó không trả về giá trị Secret.

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=sck-demo
server.port=8080
management.endpoints.web.exposure.include=health,info
management.endpoint.health.probes.enabled=true
~~~

Actuator cung cấp các nhóm health phù hợp cho Kubernetes tại `/actuator/health/liveness` và `/actuator/health/readiness`. Trong ví dụ, HTTP nghiệp vụ và Actuator cùng dùng cổng 8080. Xem [cấu hình endpoint và health của Spring Boot](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

### 6.2. Build image có định danh rõ ràng

Trong phần `<build>` hiện có của `pom.xml`, thêm:

~~~xml
<finalName>sck-demo</finalName>
~~~

Giữ Spring Boot Maven Plugin do Initializr sinh ra. Chạy từ thư mục gốc của ứng dụng trên PowerShell:

~~~powershell
./mvnw.cmd package
~~~

Nếu dùng Bash:

~~~bash
./mvnw package
~~~

Tạo `Dockerfile`:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/sck-demo.jar app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=65.0", "-jar", "/app/app.jar"]
~~~

Build:

~~~powershell
docker build -t sck-demo:dev-001 .
~~~

Dùng tag mới khi mã thay đổi, chẳng hạn `dev-002`. Trong lab, tên này giúp nhận biết vòng build; trong nhóm, có thể dùng mã commit hoặc digest. Nếu cần tái tạo chính xác cả lớp nền, khóa digest của base image trong Dockerfile.

## 7. Đưa image vào đúng node

Chạy đúng một lệnh tương ứng với cụm đã tạo.

Với kind:

~~~powershell
kind load docker-image sck-demo:dev-001 --name sck-local
~~~

Với minikube:

~~~powershell
minikube image load sck-demo:dev-001 -p sck-local
~~~

Đối với cụm từ xa, load image của laptop không phải cơ chế phân phối image tới node từ xa. Bạn cần push lên registry mà node truy cập được, rồi dùng địa chỉ registry trong manifest và cấu hình quyền pull nếu cần.

Quy trình load được hướng dẫn tại [kind: loading an image](https://kind.sigs.k8s.io/docs/user/quick-start/) và [minikube: pushing images](https://minikube.sigs.k8s.io/docs/handbook/pushing/).

Trong manifest tiếp theo, `imagePullPolicy: Never` được dùng có chủ đích: lab phải sử dụng đúng image đã load. Nếu thiếu image, lỗi sẽ xuất hiện thay vì âm thầm pull một image khác. Khi chuyển sang registry, thay bằng chính sách pull phù hợp với quy trình phát hành.

Không dùng `latest` cho vòng lặp này. Build lại cùng tag, load lại và restart Pod vẫn dễ để lại sự mơ hồ về phiên bản đang chạy; đổi tag làm quá trình quan sát rõ hơn.

## 8. Triển khai cùng một manifest trên hai môi trường

Tạo `k8s-local.yaml` trong thư mục lab:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sck-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: sck-demo
  namespace: sck-lab
automountServiceAccountToken: false
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: sck-demo
  namespace: sck-lab
data:
  DEMO_MESSAGE: "Xin chào từ ConfigMap"
---
apiVersion: v1
kind: Secret
metadata:
  name: sck-demo
  namespace: sck-lab
type: Opaque
stringData:
  DEMO_APIKEY: "local-demo-only"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sck-demo
  namespace: sck-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: sck-demo
  template:
    metadata:
      labels:
        app: sck-demo
    spec:
      serviceAccountName: sck-demo
      automountServiceAccountToken: false
      containers:
        - name: app
          image: sck-demo:dev-001
          imagePullPolicy: Never
          ports:
            - name: http
              containerPort: 8080
          envFrom:
            - configMapRef:
                name: sck-demo
            - secretRef:
                name: sck-demo
          env:
            - name: POD_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
---
apiVersion: v1
kind: Service
metadata:
  name: sck-demo
  namespace: sck-lab
spec:
  type: ClusterIP
  selector:
    app: sck-demo
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Ở đây, `DEMO_MESSAGE` ánh xạ thành `demo.message` và `DEMO_APIKEY` ánh xạ thành `demo.api-key` trong môi trường Spring. Giá trị `local-demo-only` là dữ liệu giả phục vụ lab.

Ứng dụng nhận cấu hình từ biến môi trường do Kubernetes thiết lập khi tạo container. **Đây chưa phải ConfigMap PropertySource của Spring Cloud Kubernetes.** Ứng dụng không gọi API để đọc ConfigMap hoặc Secret, nên chưa cần Role cho các tài nguyên đó.

Tài liệu [ConfigMap của Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/) phân biệt các cách sử dụng qua environment, volume và API; mỗi cách có vòng đời cập nhật khác nhau.

Áp dụng và chờ rollout:

~~~powershell
kubectl --context $KubeContext apply -f k8s-local.yaml
kubectl --context $KubeContext -n $LabNamespace rollout status deployment/sck-demo --timeout=180s
kubectl --context $KubeContext -n $LabNamespace get pods -l app=sck-demo -o wide
kubectl --context $KubeContext -n $LabNamespace get service sck-demo
kubectl --context $KubeContext -n $LabNamespace get endpointslices -l kubernetes.io/service-name=sck-demo
~~~

Kết quả mong đợi: có Pod `Running` và `1/1 Ready`, Service có cổng 80 và EndpointSlice có backend phù hợp. Giá trị IP, tên Pod và tên node thay đổi giữa các lần tạo cụm.

**Startup probe** cho JVM thời gian khởi động; **readiness probe** quyết định Pod có sẵn sàng nhận traffic qua Service hay không; **liveness probe** hỗ trợ phát hiện container cần khởi động lại. Không kết luận Pod phục vụ được chỉ từ trạng thái `Running`. Xem [ngữ nghĩa các probe của Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

## 9. Kiểm tra hai đường truy cập riêng biệt

### 9.1. Từ máy phát triển: port-forward

Trong một terminal giữ mở:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace port-forward service/sck-demo 18080:80 --address 127.0.0.1
~~~

Trong terminal khác, gọi bằng trình duyệt hoặc PowerShell:

~~~powershell
Invoke-RestMethod http://127.0.0.1:18080/hello
Invoke-RestMethod http://127.0.0.1:18080/actuator/health/readiness
~~~

Có thể dùng `curl` trên Bash hoặc `curl.exe` nếu đã cài trên Windows:

~~~bash
curl http://127.0.0.1:18080/hello
~~~

Phản hồi nghiệp vụ có dạng:

~~~json
{
  "message": "Xin chào từ ConfigMap",
  "pod": "sck-demo-<pod-suffix>",
  "namespace": "sck-lab",
  "secretConfigured": "true"
}
~~~

Port-forward tới Service chọn một Pod phù hợp để chuyển tiếp; nó không phải phép thử cơ chế phân phối traffic qua ClusterIP. Khi Pod được chọn bị thay thế, có thể cần chạy lại lệnh. Xem [hướng dẫn port-forward của Kubernetes](https://kubernetes.io/docs/tasks/access-application-cluster/port-forward-access-application-cluster/).

Vì vậy, gọi thành công `localhost:18080` chưa xác nhận DNS nội bộ, Ingress hoặc DiscoveryClient hoạt động.

### 9.2. Từ trong cụm: DNS Service

Tạo một Pod tạm dùng curl:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace run sck-curl --rm -i --restart=Never --image=curlimages/curl:8.12.1 -- http://sck-demo.sck-lab.svc/hello
~~~

Lệnh này cần node pull được image kiểm tra. Nếu đang làm lab offline, chuẩn bị trước image và chính sách pull tương ứng. Nếu Pod tạm không khởi động, xem Events của nó trước khi kết luận Service lỗi.

Đường này kiểm chứng tên Service, cổng Service và đường mạng từ một Pod tới backend. Tên `sck-demo` dùng trong cùng namespace; `sck-demo.sck-lab.svc` nêu rõ namespace và dựa vào cấu hình tìm kiếm DNS trong Pod. Không giả định mọi cụm có cluster domain là `cluster.local`. Tham khảo [DNS cho Service và Pod](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/).

### 9.3. Khi nào cần NodePort, Ingress hoặc LoadBalancer?

| Nhu cầu | Cơ chế nên kiểm chứng |
| --- | --- |
| Xem một endpoint từ laptop | Port-forward |
| Dịch vụ trong cụm gọi nhau | ClusterIP và DNS Service |
| Truy cập qua hostname, định tuyến HTTP hoặc TLS | Ingress controller/Gateway tương ứng với thiết kế |
| Kiểm thử Service type LoadBalancer | Bộ cung cấp LoadBalancer hoạt động trên môi trường đã chọn |

Với kind, nếu cần NodePort từ host, có thể tạo cụm với `extraPortMappings` và dùng giá trị `containerPort` khớp `nodePort` của Service. Đây là cấu hình node cần chuẩn bị khi tạo cụm, không phải thuộc tính của ứng dụng. Xem [cấu hình cổng của kind](https://kind.sigs.k8s.io/docs/user/configuration/).

Với minikube, `minikube service <tên-service> --url -p sck-local -n sck-lab` hỗ trợ truy cập Service phù hợp, còn `minikube tunnel -p sck-local` phục vụ trường hợp LoadBalancer. Khả năng truy cập trực tiếp IP node và việc phải giữ tiến trình tunnel chạy phụ thuộc driver/hệ điều hành; xem [minikube: accessing apps](https://minikube.sigs.k8s.io/docs/handbook/accessing/).

Với kind, có thể bổ sung Cloud Provider KIND khi thực sự cần hành vi Service type LoadBalancer; xem [hướng dẫn LoadBalancer của kind](https://kind.sigs.k8s.io/docs/user/loadbalancer/).

**Spring Cloud LoadBalancer** là thành phần trong ứng dụng Spring; **Service type LoadBalancer** là loại tài nguyên Kubernetes. Chọn minikube để có tunnel không tự cấu hình Spring Cloud LoadBalancer, và thêm thư viện Spring cũng không tạo bộ cân bằng tải bên ngoài cụm.

## 10. Từ nền tảng hoạt động đến tích hợp Spring Cloud Kubernetes

### 10.1. Bật tính năng theo bằng chứng cần thu thập

| Mục tiêu ứng dụng | Khởi đầu phù hợp | Khi nào cần thêm Spring Cloud Kubernetes |
| --- | --- | --- |
| Gọi một dịch vụ qua tên ổn định | Kubernetes Service và DNS | Cần API DiscoveryClient, thông tin instance hoặc tích hợp client cụ thể |
| Nhận cấu hình lúc khởi động | Environment hoặc tệp được mount | Cần PropertySource lấy ConfigMap/Secret qua Kubernetes client |
| Phân phối lời gọi ở phía client | Làm rõ Service đã đảm nhiệm phần nào | Cần chiến lược chọn instance trong ứng dụng qua Spring Cloud LoadBalancer |
| Áp dụng thay đổi cấu hình | Restart/rollout có kiểm soát | Cần refresh phù hợp và triển khai Configuration Watcher |
| Kiểm tra khả năng phục vụ của Pod | Actuator cùng Kubernetes probes | Chỉ thêm thành phần khác khi có nhu cầu quan sát cụ thể |

Sử dụng tên Service là một cách discovery tự nhiên của Kubernetes; không bắt buộc thêm DiscoveryClient chỉ để gọi một URL nội bộ. Tài liệu [Kubernetes native service discovery của Spring](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-kubernetes-native.html) mô tả cách gọi qua tên dịch vụ.

### 10.2. Kiểm chứng RBAC cho một ứng dụng có DiscoveryClient

Khi bài thực hành tiếp theo thực sự dùng DiscoveryClient, chọn một implementation Kubernetes client và BOM tương thích. Không ghép tùy tiện starter Fabric8 với starter Kubernetes Java Client.

Ví dụ dưới đây là **cấu hình môi trường cho nhánh DiscoveryClient dùng EndpointSlice**, không phải thao tác bắt buộc của ứng dụng tối thiểu ở trên. Nó giả định ứng dụng đã được bổ sung starter DiscoveryClient phù hợp, cấu hình chỉ khám phá namespace `sck-lab` và bật:

~~~properties
spring.cloud.kubernetes.discovery.use-endpoint-slices=true
~~~

Tùy chọn EndpointSlice và yêu cầu quyền tương ứng được mô tả trong [DiscoveryClient của Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html). Xác nhận chúng tồn tại ở phiên bản bạn sử dụng.

Tạo `discovery-rbac.yaml`:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: sck-discovery-reader
  namespace: sck-lab
rules:
  - apiGroups: [""]
    resources: ["services", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: sck-discovery-reader
  namespace: sck-lab
subjects:
  - kind: ServiceAccount
    name: sck-demo
    namespace: sck-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: sck-discovery-reader
~~~

Chỉ áp dụng khi làm nhánh này:

~~~powershell
kubectl --context $KubeContext apply -f discovery-rbac.yaml
~~~

Đồng thời sửa `spec.template.spec.automountServiceAccountToken` của Deployment thành `true` và apply lại manifest ứng dụng. Giá trị tường minh trên Pod template cho phép Pod mới nhận token dù ServiceAccount ban đầu đặt mặc định `false`. Xác nhận Pod mới vẫn dùng `serviceAccountName: sck-demo`.

Nếu implementation dùng API `Endpoints` thay vì EndpointSlice, Role phải có quyền trên `endpoints` trong API group rỗng. Chọn quyền theo client và cấu hình thực tế, không thêm tất cả tài nguyên chỉ để hết lỗi. Hướng dẫn [ServiceAccount và quyền của Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/security-service-accounts.html) giúp xác định các nhóm tài nguyên cần xem xét.

Có thể kiểm tra quyền bằng danh tính ServiceAccount:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace auth can-i list services --as=system:serviceaccount:sck-lab:sck-demo
kubectl --context $KubeContext -n $LabNamespace auth can-i watch endpointslices.discovery.k8s.io --as=system:serviceaccount:sck-lab:sck-demo
kubectl --context $KubeContext -n $LabNamespace auth can-i get secrets --as=system:serviceaccount:sck-lab:sck-demo
~~~

Với Role minh họa, kỳ vọng hai kiểm tra đầu là `yes` và kiểm tra Secret là `no`, nếu không có binding khác cấp quyền bổ sung. Người chạy lệnh cần có quyền impersonate danh tính đó. Nếu bị từ chối impersonation, hãy kiểm tra qua cơ chế được quản trị viên cho phép; không diễn giải lỗi ấy thành kết luận về quyền của Pod. Xem [kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Sau cùng, quan sát kết quả truy vấn DiscoveryClient từ **chính ứng dụng trong Pod** và thử gọi backend được phát hiện. Kết quả `can-i` chỉ kiểm tra quyết định phân quyền, chưa chứng minh token, namespace và kết nối runtime đều đúng.

### 10.3. Đọc ConfigMap/Secret qua API là một nhánh riêng

Khi chọn ConfigMap PropertySource, cần xác định tên nguồn, namespace, chế độ đọc và những verb mà phiên bản client sử dụng. Cấp quyền đúng cho ServiceAccount thay vì trông cậy quyền của kubectl trên laptop.

ConfigMap trong lab hiện chứa khóa biến môi trường `DEMO_MESSAGE`. Khi chuyển sang đọc bằng PropertySource, hãy thiết kế lại nguồn theo cú pháp của cơ chế đó, chẳng hạn khóa thuộc tính `demo.message` hoặc nội dung `application.yaml`. Không mặc định rằng mọi cơ chế xử lý cùng tên khóa theo cùng cách.

Tên ConfigMap có thể gắn với `spring.application.name` hoặc cấu hình nguồn tường minh. Tham khảo [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html) của đúng phiên bản.

Việc Kubernetes đưa Secret vào container không yêu cầu cấp quyền đọc Secret qua API cho ứng dụng. Nếu chọn API, hãy đánh giá riêng phạm vi quyền và tuyệt đối không in giá trị Secret khi kiểm chứng.

## 11. Thử thay đổi cấu hình mà không nhầm với refresh

Đầu tiên quay lại nhánh ứng dụng tối thiểu dùng `envFrom`. Sửa `DEMO_MESSAGE` trong `k8s-local.yaml` thành:

~~~yaml
DEMO_MESSAGE: "Cấu hình phiên bản hai"
~~~

Áp dụng:

~~~powershell
kubectl --context $KubeContext apply -f k8s-local.yaml
~~~

Gọi lại `/hello`. Pod đang chạy vẫn giữ giá trị môi trường lúc container được tạo; thay đổi ConfigMap không tự thay environment của tiến trình hiện tại.

Tạo đợt rollout mới:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace rollout restart deployment/sck-demo
kubectl --context $KubeContext -n $LabNamespace rollout status deployment/sck-demo --timeout=180s
~~~

Nếu port-forward cũ mất kết nối, mở lại rồi gọi `/hello`. Kỳ vọng message mới xuất hiện và tên Pod đã thay đổi.

Thử nghiệm này kiểm chứng cấu hình mới được nhận khi khởi động container. Nó không chứng minh hot refresh.

Nếu mục tiêu là Configuration Watcher, cần kiểm tra riêng:

- Watcher quan sát đúng namespace và đúng nguồn cấu hình được chọn.
- Danh tính của watcher có quyền cần thiết.
- Watcher truy cập được các instance ứng dụng cần refresh.
- Cơ chế refresh và bean được thiết kế để nhận lại cấu hình.
- Thay đổi đã tới nguồn mà ứng dụng thực sự đọc, thay vì bị một nguồn có độ ưu tiên cao hơn che mất.

Configuration Watcher là thành phần triển khai riêng; thay đổi tệp mount không tự buộc Spring cập nhật mọi bean. Với nhánh HTTP, watcher gọi endpoint refresh của các instance phù hợp. Việc refresh không thể thay một biến môi trường đã được container thiết lập lúc tạo. Xem [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Không mở công khai endpoint quản trị chỉ để làm thử nghiệm refresh. Trong môi trường nhóm, áp dụng cơ chế xác thực và đường truy cập quản trị phù hợp với thiết kế.

## 12. Vòng lặp sửa mã và kiểm tra sức khỏe

### 12.1. Sửa mã, tạo image mới, đổi Deployment

Sau khi sửa Java và build lại JAR, tạo image mới:

~~~powershell
docker build -t sck-demo:dev-002 .
~~~

Load theo công cụ đã chọn:

~~~powershell
kind load docker-image sck-demo:dev-002 --name sck-local
~~~

Hoặc:

~~~powershell
minikube image load sck-demo:dev-002 -p sck-local
~~~

Đổi `image` trong `k8s-local.yaml` thành `sck-demo:dev-002`, apply lại rồi chờ rollout. Đổi cả manifest giúp lần apply sau giữ đúng image, thay vì chỉ sửa trạng thái sống trên cụm.

Quan sát:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace get deployment sck-demo -o wide
kubectl --context $KubeContext -n $LabNamespace get pods -l app=sck-demo -o wide
kubectl --context $KubeContext -n $LabNamespace get pods -l app=sck-demo -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.containers[0].image}{" "}{.status.containerStatuses[0].imageID}{"\n"}{end}'
~~~

Tag cho biết cấu hình mong muốn; `imageID` giúp xác định image đã được runtime sử dụng. Với cụm nhiều node, lỗi xuất hiện ngắt quãng sau rollout có thể do image chưa có trên node nhận Pod.

### 12.2. Đọc bằng chứng theo lớp

~~~powershell
kubectl --context $KubeContext -n $LabNamespace get pods -l app=sck-demo
kubectl --context $KubeContext -n $LabNamespace describe pods -l app=sck-demo
kubectl --context $KubeContext -n $LabNamespace logs deployment/sck-demo --tail=100
kubectl --context $KubeContext -n $LabNamespace get events --sort-by=.metadata.creationTimestamp
~~~

Nếu container đã restart, lấy tên Pod từ `get pods` và đọc log lần chạy trước bằng `kubectl logs <tên-pod> --previous` cùng context và namespace tương ứng.

| Triệu chứng | Câu hỏi cần trả lời trước | Bằng chứng nên xem |
| --- | --- | --- |
| Pod `Pending` | Node còn tài nguyên để schedule không? | Events, requests và trạng thái node |
| `ErrImageNeverPull` | Đã load đúng image/tag vào đúng cụm chưa? | Tên cụm, image trong manifest, node nhận Pod |
| `ImagePullBackOff` | Node có truy cập registry và xác thực đúng không? | Events của Pod, địa chỉ image, quyền pull |
| `CrashLoopBackOff` | JVM thoát do lỗi gì? | Logs hiện tại và previous, exit code |
| `OOMKilled` | Bộ nhớ container có đủ không? | Last State, giới hạn memory và nhu cầu JVM |
| `Running` nhưng chưa `Ready` | Probe sai URL/cổng hay ứng dụng chưa sẵn sàng? | Describe, log và phản hồi health |
| API trả `403 Forbidden` | Ứng dụng dùng danh tính và verb nào? | ServiceAccount, RoleBinding, namespace và auth can-i |
| IDE không gọi được Pod IP | Host có route đến mạng Pod không? | Vị trí caller và đường mạng thực tế |
| DNS Service không phân giải | Lệnh được chạy từ đâu và namespace nào? | Pod thử, CoreDNS và tên Service |
| Gọi qua Service thất bại | Selector, cổng và backend đã đúng chưa? | Service, EndpointSlice và readiness |

Nếu cần đo CPU/memory bằng `kubectl top`, trước hết xác nhận cụm có metrics API hoạt động. Việc thiếu metrics-server không đồng nghĩa ứng dụng hoặc cụm bị hỏng.

## 13. Thế nào là một môi trường “tương đương”?

Một môi trường tương đương cho bài này phải cung cấp được các hành vi cần kiểm chứng, không chỉ có một API server trả lời lệnh `get nodes`.

| Phạm vi | Bằng chứng tối thiểu |
| --- | --- |
| Quản lý workload | Deployment rollout được và Pod chạy đúng image |
| Discovery tự nhiên của Kubernetes | Pod gọi được backend qua DNS Service |
| Tích hợp client qua API nếu sử dụng | Client dùng đúng ServiceAccount, quyền và namespace |
| Cấu hình | Xác định được nguồn, giá trị đang hiệu lực và cách cập nhật |
| Sức khỏe | Phân biệt được startup, readiness và liveness |
| Mạng host → cụm | Có đường truy cập phục vụ debug, được mô tả rõ |
| Tái tạo | Có thể dựng lại với phiên bản và cấu hình đã ghi nhận |

Các giới hạn phải được kiểm thử ở môi trường phù hợp hơn:

- Cụm nhiều node trên cùng laptop không đại diện cho lỗi mạng hay mất máy vật lý độc lập.
- Khả năng tạo đối tượng NetworkPolicy không chứng minh CNI đang thực thi chính sách đó.
- Ingress controller, Gateway, CSI, cloud identity hoặc load balancer của nhà cung cấp có thể khác hẳn môi trường cục bộ.
- Chạy bằng quyền quản trị trên cụm cá nhân không chứng minh ứng dụng hoạt động với quyền tối thiểu ở cụm nhóm.
- Kiểm thử một replica không xác nhận refresh, discovery hoặc phân phối lời gọi trên tất cả replica.

Ví dụ, nếu yêu cầu chỉ là đọc ConfigMap trong namespace và gọi Service nội bộ, kind và minikube đều có thể đáp ứng sau khi cấu hình đúng. Nếu lỗi liên quan chính sách mạng của cụm triển khai, hãy chọn môi trường có thành phần thực thi tương ứng và kiểm tra bằng traffic được phép/bị chặn.

## 14. Bài tập quyết định và tiêu chí hoàn thành

### 14.1. Ba tình huống để tự chọn

**Tình huống A — Laptop có Docker, cần lab có thể tạo lại trên CI.** Chọn kind, lưu cấu hình cụm, ghi node image và dùng tag image riêng cho từng build. Bắt đầu một node; chỉ thêm node khi tình huống kiểm thử cần.

**Tình huống B — Muốn học Kubernetes bằng thao tác tương tác và cần lựa chọn driver.** Chọn minikube, ghi profile cùng driver, dùng image load cho vòng lặp đầu và bổ sung service URL/tunnel khi bài toán mạng yêu cầu.

**Tình huống C — Máy ít tài nguyên, nhóm đã có cụm phát triển.** Dùng namespace riêng trên cụm đó nếu có quyền và registry phù hợp. Tách rõ kubeconfig của người phát triển với ServiceAccount của workload; không giả định có thể dùng kind load cho cụm từ xa.

Với mỗi lựa chọn, hãy viết được bốn câu: cần kiểm chứng điều gì, công cụ đáp ứng bằng cách nào, giới hạn nào còn lại và bằng chứng nào sẽ thu thập.

### 14.2. Danh sách hoàn thành bài thực hành

- [ ] Chọn một môi trường và ghi lý do cùng giới hạn.
- [ ] Xác nhận context, namespace, phiên bản Kubernetes và kiến trúc node.
- [ ] Build image có tag rõ ràng và đưa image vào đúng cụm.
- [ ] Deployment chạy được, Pod sẵn sàng và EndpointSlice có backend.
- [ ] Gọi `/hello` qua port-forward từ host.
- [ ] Gọi `/hello` qua DNS Service từ một Pod trong cụm.
- [ ] Thay ConfigMap, quan sát environment cũ rồi rollout để nhận giá trị mới.
- [ ] Không trả hoặc ghi log giá trị Secret.
- [ ] Phân biệt được các kết quả trên với bằng chứng cần có cho DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher.
- [ ] Ghi được cách tái tạo và dọn đúng tài nguyên của lab.

Đạt danh sách này chứng minh môi trường sẵn sàng cho những bài tích hợp tiếp theo. Muốn kết luận một tính năng Spring Cloud Kubernetes đã hoạt động, cần có phép thử riêng cho tính năng đó.

## 15. Dọn môi trường đúng phạm vi

Đóng tiến trình port-forward bằng `Ctrl+C`.

Nếu chỉ muốn xóa tài nguyên của bài và giữ cụm:

~~~powershell
kubectl --context $KubeContext delete namespace sck-lab
~~~

Nếu đã xong hoàn toàn, xóa đúng cụm được tạo trong bài, chọn đúng một lệnh:

~~~powershell
kind delete cluster --name sck-local
~~~

Hoặc:

~~~powershell
minikube delete -p sck-local
~~~

Lệnh xóa cụm sẽ xóa workload và dữ liệu nằm trong cụm lab đó. Đối với cụm của nhóm, chỉ dọn tài nguyên thuộc namespace được giao theo quy trình của nhóm; không thực hiện lệnh quản lý cụm cục bộ như một bước dọn cụm dùng chung.
