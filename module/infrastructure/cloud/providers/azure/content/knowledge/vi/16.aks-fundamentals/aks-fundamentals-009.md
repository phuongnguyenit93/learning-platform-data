# Triển khai ứng dụng Java bằng Deployment và Service

Một ứng dụng Java có thể chạy tốt bằng lệnh **java -jar** trên laptop nhưng chưa thể phục vụ người dùng chỉ bằng cách đưa file JAR lên Azure Kubernetes Service (AKS). Kubernetes cần biết **chạy image nào, cần bao nhiêu bản sao, tiến trình lắng nghe ở cổng nào, khi nào ứng dụng sẵn sàng và traffic phải được chuyển tới Pod ra sao**. Hai tài nguyên nền tảng giải quyết phần lớn bài toán này là **Deployment** và **Service**.

Trong bài học, chúng ta xây dựng một API Spring Boot đơn giản, đóng gói thành container image, lưu image trong Azure Container Registry (ACR), triển khai bằng Kubernetes Deployment và tạo Service **ClusterIP** để truy cập ổn định. Sau đó, ta kiểm thử ứng dụng, thực hiện rolling update/rollback và xử lý những lỗi thường gặp như ImagePullBackOff, CrashLoopBackOff và Pod không Ready. Những thao tác có thể tạo chi phí hoặc mở đường public đều được phân tách rõ khỏi phần thực hành cơ bản.

Bài thuộc chương **Nền tảng Azure Kubernetes Service** của module **CLOUD_PROVIDERS_AZURE**. Module khám phá Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ, dữ liệu, triển khai, giám sát, bảo vệ và kiểm soát chi phí. Ở đây, AKS cung cấp nền tảng orchestration; ACR quản lý artifact; Deployment điều hành vòng đời Pod; Service tạo điểm truy cập ổn định; các chính sách danh tính, mạng và quan sát giúp triển khai Java an toàn.

Sau khi học, bạn có thể:

- Giải thích quan hệ **Java app → image → registry → Pod → Deployment → Service**.
- Viết một ứng dụng Spring Boot tối giản và Dockerfile đóng gói thành image.
- Phân biệt Deployment, ReplicaSet, Pod, Service và EndpointSlice.
- Tạo manifest Deployment/Service có labels, selectors, ports, requests/limits và health probes đúng.
- Cấu hình quyền image pull từ ACR bằng danh tính thích hợp, không hard-code registry password.
- Triển khai và xác minh ứng dụng bằng **az**, **kubectl**, **curl**, rolling update và rollback.
- Phân biệt Service ClusterIP với LoadBalancer/Ingress, tránh vô tình mở ứng dụng ra Internet.
- Chẩn đoán lỗi scheduling, image pull, ứng dụng Java khởi động và đường kết nối.

## 1. Tổng quan kiến trúc triển khai Java trên AKS

AKS là dịch vụ Kubernetes được Azure quản lý. Azure quản lý các thành phần control plane theo mô hình dịch vụ; người vận hành vẫn chịu trách nhiệm cấu hình node pools, quyền truy cập, network, image, workload và nhiều thành phần bảo mật/giám sát.

~~~text
Developer / CI pipeline
      |
      | Build + test + package
      v
Java application (JAR)
      |
      | Docker build
      v
Container image: java-api:1.0.0
      |
      | Push
      v
Azure Container Registry (ACR)
      |
      | Kubelet/image pull identity
      v
AKS cluster
  |
  +-- Deployment/java-api
  |     |
  |     +-- ReplicaSet
  |           +-- Pod A --> Java container :8080
  |           +-- Pod B --> Java container :8080
  |
  +-- Service/java-api (ClusterIP :80)
        |
        +-- Chọn các Pod có label app=java-api
        +-- Chuyển traffic tới targetPort 8080
~~~

Đường **pull image** khác đường **HTTP request**. ACR là nơi cung cấp image khi tạo/recreate Pod; Service nhận request của các client trong cluster và chuyển tới Pod đã sẵn sàng. **ACR không phải load balancer HTTP** và Service không dùng để lưu trữ JAR.

### Một số thuật ngữ cần phân biệt

| Khái niệm | Vai trò | Điều không nên nhầm |
|---|---|---|
| **AKS cluster** | Môi trường Kubernetes do Azure hỗ trợ quản lý | Không phải một VM duy nhất |
| **Node** | Máy chạy các Pod, thường thuộc node pool | Không phải container |
| **Pod** | Đơn vị triển khai/scheduling nhỏ nhất, chứa một hoặc nhiều container | IP/định danh Pod có thể thay đổi |
| **Deployment** | Khai báo trạng thái mong muốn cho nhóm Pod có thể thay thế, hỗ trợ rollout | Không tự tạo endpoint cố định cho client |
| **ReplicaSet** | Duy trì số Pod theo template, thường do Deployment quản lý | Thường không chỉnh trực tiếp khi đã có Deployment |
| **Service** | Địa chỉ/điểm kết nối ổn định tới một tập Pod theo selector | Không build image và không bảo đảm ứng dụng healthy |
| **EndpointSlice** | Thông tin endpoint backend được controller duy trì | Không phải nơi triển khai code |
| **Namespace** | Nhóm tài nguyên Kubernetes để tổ chức/quản lý | Không phải ranh giới cách ly bảo mật tuyệt đối |

## 2. Deployment và Service giải quyết hai vấn đề khác nhau

### Deployment: duy trì ứng dụng theo desired state

Khi khai báo **replicas: 2**, Deployment cố gắng duy trì hai Pod phù hợp với template. Nếu một Pod bị xóa hoặc node gặp sự cố, controller sẽ tìm cách tạo Pod thay thế dựa trên tài nguyên còn khả dụng và điều kiện scheduling.

~~~text
Deployment replicas=2
   |
   +-- Pod 1 Ready
   +-- Pod 2 Ready

Pod 1 bị mất
   |
   v
Controller cố tạo Pod 3 thay thế
   |
   +-- Pod 2 Ready
   +-- Pod 3 Pending/Starting -> Ready
~~~

Deployment không cam kết luôn có đủ hai Pod nếu cluster hết CPU/RAM, image không kéo được, không đủ quota hoặc lỗi node. Nó cung cấp cơ chế **reconciliation**, còn khả năng phục vụ thực tế phụ thuộc capacity và các thành phần khác.

### Service: endpoint ổn định cho client

Pod có thể được tạo lại với IP khác. Nếu client ghi cứng địa chỉ Pod, mỗi lần rolling update hoặc reschedule đều có thể làm đứt kết nối. Service có một **DNS name ổn định trong namespace**, định tuyến tới các Pod khớp selector và ở trạng thái sẵn sàng theo cơ chế Kubernetes.

Ví dụ:

~~~text
java-api.java-demo.svc.cluster.local:80
            |
            v
       Service/java-api
        /           \
       v             v
  Pod A:8080     Pod B:8080
~~~

Trong cùng namespace, một client thường dùng tên ngắn **java-api:80**. Từ namespace khác, có thể dùng **java-api.java-demo:80** hoặc FQDN đầy đủ.

**Service không nhất thiết public.** Trong bài này dùng **ClusterIP** nên mặc định chỉ định tuyến trong phạm vi mạng cluster/các đường kết nối được thiết kế; để truy cập từ máy học viên, ta dùng **kubectl port-forward** thay vì tạo public load balancer.

## 3. Luồng request, label và selector

Một Service **không liên kết Deployment bằng tên tài nguyên**. Nó tìm Pod theo **labels** đã khai báo.

~~~yaml
template:
  metadata:
    labels:
      app: java-api
~~~

Service có:

~~~yaml
spec:
  selector:
    app: java-api
~~~

Khi các Pod mang label tương ứng, Service mới có backend phù hợp. Nếu Deployment đặt **app: order-api** còn Service chọn **app: java-api**, Service có thể tồn tại và có ClusterIP nhưng **không có endpoint**, khiến request thất bại.

### Ba loại cổng thường gặp

| Trường | Nằm ở đâu? | Ý nghĩa |
|---|---|---|
| **containerPort: 8080** | Pod/Container spec | Mô tả cổng ứng dụng dự kiến mở trong container; tự khai báo không tạo tiến trình lắng nghe |
| **port: 80** | Service spec | Cổng client sử dụng khi kết nối tới Service |
| **targetPort: http** | Service spec | Cổng container đích; có thể là số hoặc **tên cổng** đã khai báo trong Pod |

Ví dụ: **Service port 80 → targetPort http → containerPort 8080**. Ứng dụng Java thật sự phải lắng nghe trên **0.0.0.0:8080** hoặc interface phù hợp; chỉ viết containerPort trong YAML không khiến Java tự mở cổng.

## 4. Chuẩn bị môi trường an toàn

Để thực hành với tài nguyên Azure thật, cần:

- Một **subscription lab** được phép sử dụng, có quy tắc budget/cost.
- Một **AKS cluster đã tồn tại** và có node pool đủ công suất cho ít nhất hai Pod mẫu.
- Một **ACR đã tồn tại**, có repository cho image demo; hoặc registry lab được phép tạo riêng.
- Quyền thích hợp để xem AKS, lấy kubeconfig, tạo Deployment/Service trong namespace lab và đẩy image vào ACR.
- Azure CLI (**az**), **kubectl**, Java/Maven và Docker hoặc công cụ build OCI tương thích nếu build local.
- Mạng có thể kết nối AKS control plane, ACR login/data endpoints và đường tới namespace lab.

**Không bắt buộc tạo AKS mới để học Deployment và Service.** Cluster, node pools, public IP, storage, ACR và Azure Monitor có thể phát sinh phí. Nếu chưa có sandbox, vẫn có thể đọc mã Java/YAML và hoàn thành phần phân tích mà không tác động tới tài nguyên cloud.

### Phân biệt ba nhóm quyền

1. **Azure management plane:** quyền xem/sửa cluster, registry và tài nguyên Azure.
2. **Kubernetes authorization:** quyền tạo/xem/sửa Deployment, Service và Pod trong namespace; thường dùng Kubernetes RBAC, tùy AKS có tích hợp Azure RBAC.
3. **ACR data plane:** quyền push/pull image; không đồng nghĩa tự có chỉ vì người dùng quản trị AKS.

Một tài khoản có quyền **Reader** với cluster chưa chắc được tạo Deployment. Một người có quyền push image chưa chắc được thay đổi Kubernetes Service.

## 5. Dựng ứng dụng Java Spring Boot mẫu

Để bài học tự chứa, ta dùng API Spring Boot có endpoint **/api/hello**, còn **Spring Boot Actuator** cung cấp health endpoints cho Kubernetes probes. Ví dụ dùng Java 21 và Maven; ứng dụng thực tế có thể dùng phiên bản Java/Spring Boot khác đã được tổ chức phê duyệt.

### Cấu trúc dự án

~~~text
aks-java-demo/
├── pom.xml
├── Dockerfile
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/aksdemo/
│       │       └── AksDemoApplication.java
│       └── resources/
│           └── application.properties
└── k8s/
    └── java-api.yaml
~~~

Các file trong cấu trúc trên là **ví dụ để học viên tạo ở môi trường thực hành**, không phải những file được tạo bởi bài Markdown này.

### Cấu hình Maven (pom.xml)

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>aks-java-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phiên bản Spring Boot **3.5.7** chỉ là phiên bản cố định cho ví dụ tái lập tại thời điểm biên soạn; khi triển khai thực tế, phải kiểm tra phiên bản **còn được hỗ trợ và đã vá bảo mật** rồi cập nhật toàn bộ pipeline cho tương thích. Không sao chép các tag image hay dependency từ bài học thành chính sách cập nhật production lâu dài.

### Mã Java

Đặt file **src/main/java/com/example/aksdemo/AksDemoApplication.java**:

~~~java
package com.example.aksdemo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AksDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AksDemoApplication.class, args);
    }
}

@RestController
class HelloController {
    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        String message = System.getenv()
            .getOrDefault("APP_MESSAGE", "Hello from AKS");
        return Map.of("message", message);
    }
}
~~~

Đây là API đọc một biến môi trường không nhạy cảm **APP_MESSAGE**, giúp minh họa cách cấu hình theo môi trường mà không cần build một image mới cho mỗi thông điệp.

### Cấu hình Spring Boot

Đặt file **src/main/resources/application.properties**:

~~~properties
server.port=8080
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info
~~~

Khi có **spring-boot-starter-actuator** và cấu hình probes phù hợp, Spring Boot cung cấp các endpoint:

- **GET /actuator/health/liveness**: tiến trình có còn sống ở mức ứng dụng không?
- **GET /actuator/health/readiness**: ứng dụng đã sẵn sàng xử lý request theo trạng thái Spring Boot chưa?
- **GET /api/hello**: endpoint nghiệp vụ mẫu.

Health endpoint được hỗ trợ và đường dẫn thật phụ thuộc phiên bản Spring Boot và cấu hình Actuator. Đừng dùng đường dẫn trên trong manifest nếu ứng dụng của bạn chưa có Actuator hoặc đã đổi base path.

### Chạy thử Java trước khi container hóa

Trong thư mục dự án:

~~~bash
mvn -B test
mvn -B package
java -jar target/aks-java-demo-1.0.0.jar
~~~

Ở terminal khác:

~~~bash
curl -fsS http://localhost:8080/api/hello
curl -fsS http://localhost:8080/actuator/health/liveness
curl -fsS http://localhost:8080/actuator/health/readiness
~~~

Kỳ vọng API trả JSON chứa **message**, còn hai health endpoint phản hồi trạng thái thành công sau khi app khởi động. Trên hệ thống thật, hãy thêm unit tests và integration tests cho các yêu cầu nghiệp vụ thay vì chỉ kiểm tra hello.

## 6. Tạo Dockerfile cho ứng dụng Java

Kubernetes không triển khai trực tiếp file JAR: nó chạy container theo image được khai báo. Dockerfile multi-stage giúp tách môi trường build có Maven khỏi image runtime chỉ cần JRE.

~~~dockerfile
# Stage 1: build JAR
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml ./
COPY src ./src
RUN mvn -B -DskipTests package

# Stage 2: lean runtime
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build --chown=10001:10001 /build/target/*.jar /app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

### Những điểm cần hiểu

1. **Build image:** dùng JDK/Maven để compile và đóng gói JAR. Trong ví dụ Docker build bỏ chạy test để tránh lặp bước sau khi CI đã chạy **mvn test**; pipeline production vẫn phải chặn build nếu tests thất bại.
2. **Runtime image:** dùng Java 21 JRE, không mang nguyên Maven/build tools vào image cuối.
3. **Non-root user:** chạy dưới UID/GID **10001** để giảm rủi ro khi container bị xâm nhập.
4. **EXPOSE 8080:** mô tả cổng dự kiến, **không tự tạo listener**. Spring Boot đã được cấu hình để lắng nghe trên 8080.
5. **ENTRYPOINT:** khởi động tiến trình Java làm process chính; Kubernetes theo dõi vòng đời container qua process này.
6. **Pin base image:** production nên sử dụng image base từ nguồn tin cậy, được quét lỗ hổng và pin bằng digest/chính sách nội bộ; tag ví dụ không bảo đảm luôn mới hoặc an toàn.
7. **File permission:** nếu ứng dụng cần ghi file tạm, hãy thiết kế thư mục writable/volume phù hợp với non-root user, không tự chạy lại dưới root để vượt lỗi quyền.

Maven parent tạo executable Spring Boot JAR qua plugin cấu hình trong pom.xml. Nếu dự án của bạn xuất nhiều file **.jar** hoặc dùng Gradle/quy trình khác, phải sửa **COPY** để chỉ chọn đúng artifact; tránh wildcard vô tình copy nhầm.

### Kiểm thử container trước AKS

~~~bash
docker build -t aks-java-demo:1.0.0 .
docker run --rm -p 8080:8080 \
  -e APP_MESSAGE="Xin chao tu container local" \
  aks-java-demo:1.0.0
~~~

Ở terminal khác:

~~~bash
curl -fsS http://localhost:8080/api/hello
curl -fsS http://localhost:8080/actuator/health/readiness
~~~

Nếu container chưa hoạt động local, **chưa đưa lên AKS để thử may rủi**. Kiểm tra Java version, main class, artifact path, port và container logs trước.

## 7. Đưa image lên Azure Container Registry

ACR cung cấp registry private để AKS kéo image bằng danh tính được cấp quyền. Giả sử registry lab tên **acrjavalab** (chỉ minh họa), image đầy đủ có dạng:

~~~text
acrjavalab.azurecr.io/java-api:1.0.0
~~~

**Registry name phải tồn tại và hợp lệ**; không dùng nguyên tên minh họa khi tạo tài nguyên. Một registry có **repository java-api**, tag **1.0.0** và manifest digest tương ứng.

### Đăng nhập Azure và kiểm tra registry

Các lệnh sau dùng Bash trong Azure Cloud Shell hoặc terminal có Azure CLI/Docker:

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"
az account show --output table

ACR="<EXISTING_ACR_NAME>"
LOGIN_SERVER=$(az acr show \
  --name "$ACR" \
  --query loginServer \
  --output tsv)

echo "$LOGIN_SERVER"
~~~

Chỉ định đúng registry đã được cấp phép và xác minh login server. **Không tạo registry hoặc bật admin account** nếu không cần và chưa có phê duyệt.

### Build, tag và push

~~~bash
az acr login --name "$ACR"

docker build \
  -t "$LOGIN_SERVER/java-api:1.0.0" \
  .

docker push "$LOGIN_SERVER/java-api:1.0.0"
~~~

Lệnh này cần Docker daemon, quyền push phù hợp và đường mạng tới ACR. Nếu máy không có Docker, có thể nghiên cứu **az acr build** trong môi trường cho phép; ACR Tasks có các điều kiện riêng khi registry bị khóa private networking.

Kiểm tra repository:

~~~bash
az acr repository show-tags \
  --name "$ACR" \
  --repository java-api \
  --output table
~~~

### Tag và digest

**Tag** dễ đọc nhưng có thể trỏ tới nội dung khác nếu bị ghi đè. **Digest** là định danh manifest có giá trị cho việc phát hành nhất quán:

~~~text
<ACR_LOGIN_SERVER>/java-api:1.0.0
<ACR_LOGIN_SERVER>/java-api@sha256:<MANIFEST_DIGEST>
~~~

Trong production, nên dùng tag bất biến theo release và/hoặc pin digest. Ghi lại digest cùng commit nguồn, SBOM và kết quả kiểm tra bảo mật. Một image đã xuất hiện trong registry không tự chứng minh nó an toàn hoặc chạy được trên CPU architecture của node pool.

## 8. AKS kéo image từ ACR bằng quyền gì?

Đây là điểm dễ nhầm: **người dùng chạy kubectl apply không nhất thiết là danh tính dùng để pull image**.

Ở AKS, việc kéo image cho Pod thường do **kubelet/node identity** thực hiện theo cấu hình cluster. Identity ứng dụng dùng để gọi Azure Key Vault, Storage hoặc database là một mối quan tâm **khác** với identity lấy image từ ACR.

### Với ACR sử dụng registry-level RBAC thông thường

Trong mô hình **RBAC Registry Permissions**, kubelet identity hoặc service principal tương ứng cần role **AcrPull** trong phạm vi registry thích hợp. Một số cấu hình AKS có thể tích hợp ACR bằng:

~~~bash
az aks update \
  --resource-group "<AKS_RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER_NAME>" \
  --attach-acr "<ACR_NAME_OR_RESOURCE_ID>"
~~~

**Không chạy lệnh này mặc định**: nó thay đổi tích hợp/quyền trên cluster, cần đủ quyền Azure và phê duyệt của chủ AKS/ACR. Ngoài ra, nếu ACR đã bật **RBAC Registry + ABAC Repository Permissions**, cơ chế **--attach-acr** kiểu registry-wide có hạn chế và không được dùng thay việc gán đúng repository role theo mode mới.

### Với ACR repository-level permissions

Registry dùng **ABAC Repository Permissions** cần role và điều kiện repository phù hợp, ví dụ **Container Registry Repository Reader** cho repository **java-api** khi tính năng/mode hỗ trợ. Quyền catalog/list cũng có thể cần được xét cho một số thao tác. Không tự gán **AcrPull** rồi giả định có quyền trong mọi mode.

### Không nên dùng registry admin password

Không bật ACR admin user chỉ vì gặp **ImagePullBackOff**. Một credential registry quá rộng có thể bị lộ qua manifest, log hoặc secret, và khó audit theo workload. Nếu bắt buộc dùng imagePullSecret cho một trường hợp không hỗ trợ managed identity, giới hạn phạm vi/thời hạn, lưu credential an toàn và lên kế hoạch thu hồi.

### Mạng cũng phải đúng

Quyền pull hợp lệ chưa đủ nếu node AKS không kết nối được registry:

- ACR có public endpoint và firewall network rules? Node egress IP có được phép không?
- ACR sử dụng **Private Endpoint**? DNS login và data endpoints có phân giải đúng từ VNet/node không?
- NSG, route, proxy và firewall egress có cho phép luồng tới registry không?
- Image đã tồn tại, có đúng tag/digest và kiến trúc CPU?

Nếu ACR đang dùng geo-replication, cần kiểm thử truy cập từ các vùng workload, không chỉ quan sát trạng thái replica.

## 9. Tạo kết nối kubectl tới AKS hiện có

Trên môi trường lab, dùng:

~~~bash
RG="<AKS_RESOURCE_GROUP>"
AKS="<EXISTING_AKS_CLUSTER>"

az aks get-credentials \
  --resource-group "$RG" \
  --name "$AKS"

kubectl config current-context
kubectl cluster-info
kubectl get nodes
~~~

**az aks get-credentials** cập nhật kubeconfig/context trên máy và có thể ảnh hưởng context mặc định. **Luôn xem current-context trước khi kubectl apply/delete**, tránh nhầm cluster production.

Nếu cluster sử dụng private API server, máy chạy kubectl phải có đường kết nối phù hợp (VPN, bastion, jump host hoặc runner trong VNet). Nếu gặp lỗi authorization, phải kiểm tra **Azure auth/Kubernetes RBAC** thay vì tự yêu cầu quyền cluster-admin trong mọi tình huống.

### Dùng namespace lab riêng

~~~bash
kubectl create namespace java-demo
kubectl get namespace java-demo
~~~

Nếu namespace đã tồn tại, không tạo lại; kiểm tra namespace thuộc ai trước khi triển khai. Namespace giúp tổ chức tài nguyên và quota, nhưng **không mặc nhiên cô lập mạng hoặc quyền** nếu chưa có NetworkPolicy/RBAC tương ứng.

## 10. Viết ConfigMap cho cấu hình không nhạy cảm

Ứng dụng Java đọc **APP_MESSAGE** từ environment variable. Kubernetes **ConfigMap** phù hợp với giá trị không nhạy cảm:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: java-api-config
  namespace: java-demo
data:
  APP_MESSAGE: "Xin chao tu AKS Deployment"
~~~

ConfigMap được mount hoặc truyền qua environment variables theo khai báo Pod. Trong ví dụ ở phần tiếp theo, ta dùng **envFrom.configMapRef** để ánh xạ các key.

**Không lưu database password, API key, certificate private key hoặc token trong ConfigMap.** Kubernetes Secret không mặc nhiên được mã hóa đầu-cuối ngoài mọi nguy cơ; cần quản trị encryption at rest, RBAC và tích hợp Azure Key Vault/Workload Identity khi phù hợp.

Khi ConfigMap được đưa vào container dưới dạng **environment variables**, sửa ConfigMap sau đó **không tự thay đổi biến môi trường của các Pod đang chạy**. Cần thực hiện rollout/restart có kiểm soát để tạo Pod mới nhận giá trị.

## 11. Viết Deployment hoàn chỉnh

Deployment sau chạy **hai bản sao** của API, dùng image ACR, health probes và tài nguyên CPU/RAM minh họa.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: java-api
  namespace: java-demo
  labels:
    app: java-api
spec:
  replicas: 2
  revisionHistoryLimit: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: java-api
  template:
    metadata:
      labels:
        app: java-api
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: java-api
          image: <ACR_LOGIN_SERVER>/java-api:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          envFrom:
            - configMapRef:
                name: java-api-config
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            runAsUser: 10001
            capabilities:
              drop:
                - ALL
~~~

**Trước khi chạy:** phải thay **<ACR_LOGIN_SERVER>** bằng login server chính xác, ví dụ **myregistry.azurecr.io**. Kubernetes không hiểu placeholder. Không sao chép nguyên manifest lên production khi chưa điều chỉnh image digest, requests/limits, probes, security policy và requirements thực tế.

### Giải thích các trường quan trọng

| Trường | Ý nghĩa |
|---|---|
| **apiVersion: apps/v1** | API Kubernetes cho Deployment |
| **replicas: 2** | Mong muốn hai Pod; không phải cam kết luôn có hai Pod Ready |
| **selector.matchLabels** | Quy tắc xác định Pod thuộc Deployment; cần khớp template labels |
| **template.spec.containers.image** | Image mà kubelet kéo về node |
| **imagePullPolicy: IfNotPresent** | Nếu có image phù hợp trong node cache, kubelet có thể sử dụng cache |
| **ports.name: http** | Tên cổng để Service/probes tham chiếu |
| **envFrom.configMapRef** | Đưa các key ConfigMap vào môi trường container |
| **requests** | Mức CPU/RAM scheduler dùng để xếp Pod lên node |
| **limits** | Giới hạn runtime; thiếu RAM có thể dẫn tới OOMKilled |
| **startupProbe** | Cho ứng dụng thời gian khởi động trước khi liveness/readiness bắt đầu áp dụng |
| **readinessProbe** | Quyết định Pod có được tính là ready endpoint cho Service không |
| **livenessProbe** | Giúp kubelet phát hiện process kẹt theo tiêu chí, có thể restart container |
| **securityContext** | Giảm quyền tiến trình container |

### Requests, limits và Java memory

**cpu: 250m** là yêu cầu **0,25 vCPU** cho scheduler. **memory: 512Mi** là mức memory request. **memory limit: 1Gi** là giới hạn bộ nhớ container, **không phải chỉ heap Java**.

Một ứng dụng JVM dùng thêm memory cho metaspace, code cache, thread stacks, direct buffers và native libraries ngoài heap. Nếu đặt **-Xmx** sát bằng limit container, Pod có thể bị **OOMKilled** dù chỉ số heap nhìn có vẻ phù hợp.

Hãy sizing theo heap/native memory thực tế, thử tải, xác định GC phù hợp và đo các metric liên quan. Java hiện đại có nhận biết môi trường container, nhưng **không thay thế việc đo memory và chọn requests/limits**.

### Vì sao có startupProbe riêng?

Spring Boot có thể cần thời gian khởi động JVM, load classes và khởi tạo bean. Một liveness probe quá nghiêm có thể khiến Kubernetes restart ứng dụng liên tục trước khi nó sẵn sàng.

Trong manifest mẫu, startupProbe kiểm tra mỗi 10 giây, có **failureThreshold: 30**. Tổng cửa sổ thử ban đầu có thể xấp xỉ vài phút theo cadence/timeout và hành vi kubelet; **không phải bảo đảm thời gian chính xác 300 giây trong mọi trường hợp**. Khi startupProbe chưa thành công, Kubernetes chưa chạy các liveness/readiness probes theo cơ chế startup probe.

Không dùng ngưỡng rất lớn chỉ để che startup error vĩnh viễn; hãy tối ưu application startup và điều tra dependency không sẵn sàng.

## 12. Viết Service ClusterIP

Service dưới đây có **port 80**, chuyển tới cổng đặt tên **http** của Pod (8080):

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: java-api
  namespace: java-demo
spec:
  type: ClusterIP
  selector:
    app: java-api
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: http
~~~

Kubernetes thường gán ClusterIP từ dải Service CIDR. DNS nội bộ có dạng:

~~~text
java-api.java-demo.svc.cluster.local
~~~

Một Pod khác cùng namespace có thể gọi:

~~~text
http://java-api/api/hello
~~~

**Service chỉ chọn Pod theo label.** Nếu selectors đúng nhưng không có Pod **Ready**, Service có thể không có endpoint sẵn sàng để phục vụ. Không sửa targetPort ngẫu nhiên nếu API chưa khởi động; phải kiểm tra Java log, container port và endpoints cùng nhau.

### ClusterIP không tự tạo public endpoint

Với **ClusterIP**, không có public IP của Azure Load Balancer được tạo bởi Service này. Muốn cho người dùng Internet truy cập có thể dùng **Ingress** với ingress controller/Gateway API phù hợp, Application Gateway hoặc Service **LoadBalancer** theo kiến trúc. Những lựa chọn đó cần TLS, domain, xác thực, WAF và chính sách bảo mật riêng.

Trong bài tập, **không cần public LoadBalancer**: dùng **kubectl port-forward** là đủ để kiểm thử.

## 13. Manifest kết hợp và thứ tự apply

Trong thực tế, có thể lưu ba tài nguyên trong file **k8s/java-api.yaml**, tách bởi dấu **---** theo thứ tự:

~~~text
1. ConfigMap/java-api-config
---
2. Deployment/java-api
---
3. Service/java-api
~~~

Khi áp dụng, Kubernetes API xử lý từng resource. Để tránh lỗi config missing và dễ đọc, nên đặt ConfigMap trước Deployment trong tài liệu học. Controller sẽ tiếp tục reconciliation khi các đối tượng xuất hiện; không xem apply thành công là bằng chứng ứng dụng đã Ready.

### Validate manifest trước khi triển khai

Sau khi đã tạo namespace và lưu manifest:

~~~bash
kubectl apply \
  --dry-run=client \
  --validate=true \
  -f k8s/java-api.yaml
~~~

Lệnh trên kiểm tra nhiều lỗi cú pháp/schema ở mức client/server discovery tùy phiên bản kubectl và cách validate. Nó **không** đảm bảo image pull, node capacity, Probe URL, registry permission hoặc service connectivity sẽ hoạt động.

Với pipeline production, bổ sung kiểm tra schema/chính sách, image scanning, IaC review và chạy thử staging.

## 14. Apply Deployment và Service lên AKS

Giả sử namespace **java-demo** đã tồn tại, file manifest đã thay login server, image đã push và AKS có quyền pull:

~~~bash
kubectl apply -f k8s/java-api.yaml

kubectl get deployment -n java-demo
kubectl get pods -n java-demo -l app=java-api -o wide
kubectl get service -n java-demo java-api
~~~

Theo dõi quá trình rollout:

~~~bash
kubectl rollout status \
  deployment/java-api \
  -n java-demo \
  --timeout=180s
~~~

Nếu rollout chưa hoàn tất, **đừng lập tức tăng timeout hoặc số replicas**. Cần xem các Pod Pending, ImagePullBackOff, CrashLoopBackOff, NotReady và Kubernetes events để biết nguyên nhân.

### Kiểm tra đường Service → Pod

~~~bash
kubectl get endpointslice \
  -n java-demo \
  -l kubernetes.io/service-name=java-api
~~~

Các EndpointSlices được controller tạo để mô tả backend. Để xem chi tiết địa chỉ/điều kiện ready:

~~~bash
kubectl describe service java-api -n java-demo
kubectl get pods -n java-demo -l app=java-api --show-labels
~~~

Nếu Service không có backend, kiểm tra **selector**, labels, readiness và targetPort. Việc Deployment có replicas đang Running **không đủ** để chứng minh endpoint nhận request.

## 15. Truy cập ứng dụng qua kubectl port-forward

Thay vì public service, sử dụng:

~~~bash
kubectl port-forward \
  -n java-demo \
  service/java-api \
  8080:80
~~~

Giữ terminal này mở, rồi ở terminal khác:

~~~bash
curl -fsS http://localhost:8080/api/hello
curl -fsS http://localhost:8080/actuator/health/liveness
curl -fsS http://localhost:8080/actuator/health/readiness
~~~

Kết quả hello dự kiến tương tự:

~~~json
{"message":"Xin chao tu AKS Deployment"}
~~~

**port-forward** là kênh debug/thực hành, không phải giải pháp production ingress. Phiên kết nối có thể ngắt khi Pod được chọn bị thay thế; nó cũng không tạo kiểm chứng cân bằng tải tới cả hai Pod. Nếu cổng 8080 local đã được dùng, chọn một cổng local khác phù hợp.

### Kiểm tra nội bộ trong cluster

Với quyền và quy trình bảo mật phù hợp, một Pod client cùng namespace có thể gọi Service bằng DNS nội bộ. Không cần cấp public IP để các microservices cùng cluster gọi nhau.

Nếu muốn dùng một ephemeral debug Pod, phải chọn image đã được phê duyệt và phù hợp với network/policy. **Không chạy các image chẩn đoán không rõ nguồn gốc trên AKS production** chỉ vì tiện có lệnh curl.

## 16. Health probes: liveness, readiness và startup

Ba probe kiểm tra ba mục tiêu khác nhau:

| Probe | Khi trả lỗi nhiều lần | Cách thiết kế |
|---|---|---|
| **Startup** | Container có thể bị restart nếu vượt ngưỡng thất bại | Cho startup JVM/framework thời gian hợp lý |
| **Readiness** | Pod bị coi là chưa sẵn sàng nhận traffic qua Service | Phản ánh khả năng phục vụ request theo vai trò |
| **Liveness** | Kubelet có thể restart container | Chỉ kiểm tra tiến trình mắc lỗi cần restart, tránh phụ thuộc dễ chập chờn |

Với Spring Boot Actuator, cần hiểu rằng **readinessState** cơ bản không tự động bao gồm mọi database/queue bên ngoài trong mọi cấu hình. Nếu ứng dụng không thể phục vụ khi DB mất kết nối, hãy xác định tiêu chí readiness phù hợp, nhưng tránh liveness phụ thuộc toàn bộ dịch vụ ngoài gây **restart storm**.

### Ví dụ về sai lầm

Một API phụ thuộc database. Liveness probe gọi endpoint chạy truy vấn SQL; database chập chờn 30 giây, khiến mọi Pod bị restart và tăng thời gian hồi phục. Cách tốt hơn:

- **Liveness:** xác nhận ứng dụng không bị deadlock/trạng thái không thể phục hồi.
- **Readiness:** ngừng nhận traffic khi không thể phục vụ nghiệp vụ bắt buộc.
- **Monitoring:** theo dõi tình trạng DB riêng và cảnh báo.

Probe endpoints cần nhẹ, không ghi dữ liệu và không để lộ stack traces, credentials hay nội dung hệ thống nhạy cảm.

## 17. Rolling update bằng Deployment

Deployment với **RollingUpdate** có thể thay dần Pod phiên bản cũ bằng Pod mới.

~~~text
Trước cập nhật:
  Pod A: v1.0.0 Ready
  Pod B: v1.0.0 Ready

Rollout:
  Pod C: v1.0.1 Starting -> Ready
  Pod A: v1.0.0 Terminating
  Pod D: v1.0.1 Starting -> Ready
  Pod B: v1.0.0 Terminating

Sau cập nhật:
  Pod C: v1.0.1 Ready
  Pod D: v1.0.1 Ready
~~~

Đây là mô hình minh họa, thứ tự Pod thực tế có thể khác.

### maxSurge và maxUnavailable

Trong manifest:

~~~yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
~~~

Với **replicas: 2**, controller có thể tạo thêm tối đa một Pod vượt số bản sao mong muốn trong quá trình cập nhật, và cố tránh để số Pod available giảm dưới mức yêu cầu theo quy tắc strategy. Nhưng **không cam kết zero downtime** nếu node thất bại, readiness thiết kế sai, client giữ kết nối lâu hoặc ứng dụng không xử lý shutdown đúng.

**maxSurge=1 cần thêm tài nguyên node.** Nếu node pool đã đầy, Pod mới có thể Pending và rollout đứng yên. Có thể dùng cluster autoscaler hoặc chuẩn bị capacity, nhưng autoscaling có thời gian và giới hạn quota.

### Đổi image để rollout

Sau khi build/push **java-api:1.0.1**:

~~~bash
kubectl set image \
  deployment/java-api \
  java-api="<ACR_LOGIN_SERVER>/java-api:1.0.1" \
  -n java-demo

kubectl rollout status \
  deployment/java-api \
  -n java-demo \
  --timeout=180s
~~~

**Cảnh báo drift:** lệnh **kubectl set image** thay live Deployment; nếu manifest Git vẫn khai báo image cũ, lần **kubectl apply/GitOps sync** tiếp theo có thể đổi nó về. Trong môi trường khai báo (declarative), nên cập nhật **source manifest/Helm values** và để pipeline triển khai đồng bộ.

### Rollback

Kiểm tra lịch sử:

~~~bash
kubectl rollout history deployment/java-api -n java-demo
~~~

Nếu phiên bản mới lỗi và Deployment còn revision phù hợp:

~~~bash
kubectl rollout undo deployment/java-api -n java-demo
kubectl rollout status deployment/java-api -n java-demo
~~~

Rollback Deployment thường giúp khôi phục **Pod template** trước đó; nó **không tự rollback database schema, dữ liệu đã ghi hoặc các secret/config ngoài Deployment**. Vì vậy các thay đổi có migration dữ liệu cần kế hoạch tương thích ngược và khôi phục riêng.

## 18. Scale và khả năng phục vụ

Scale thủ công:

~~~bash
kubectl scale deployment/java-api \
  -n java-demo \
  --replicas=3

kubectl get deployment java-api -n java-demo
~~~

Thao tác này thay desired replicas, nhưng số Pod Running/Ready phụ thuộc node capacity, quota, networking, image pull và probes. Có thêm Pod không tự động làm database nhanh hơn hoặc tăng số connection mà downstream chịu được.

### Horizontal Pod Autoscaler (HPA)

Trong production, có thể sử dụng **HPA** theo CPU/memory hoặc custom/external metrics khi hệ thống cung cấp metrics phù hợp. HPA **không tự xuất hiện** chỉ vì Deployment có requests/limits.

Nếu dùng HPA, tránh đồng thời sửa replicas thủ công/GitOps mà không hiểu controller nào đang sở hữu trường **spec.replicas**. Scale tới nhiều Pod cũng có thể làm tăng database connections, request concurrency và chi phí.

### PodDisruptionBudget và phân bố node

Một Deployment có hai Pod chưa chắc đặt ở hai node/zones khác nhau. Để tăng khả năng chịu lỗi, cân nhắc:

- Node pool đủ node và nhiều Availability Zones khi được AKS hỗ trợ.
- **topologySpreadConstraints** hoặc affinity/anti-affinity để phân bố Pod.
- **PodDisruptionBudget (PDB)** khi cần giới hạn voluntary disruptions.
- Readiness/terminationGracePeriodSeconds và graceful shutdown.

PDB giúp kiểm soát một số **voluntary evictions**, không ngăn mọi lỗi node/zone và không tạo thêm capacity.

## 19. Service types: khi nào dùng loại nào?

| Loại Service | Điểm truy cập | Trường hợp thường dùng |
|---|---|---|
| **ClusterIP** | IP/DNS nội bộ Kubernetes | Microservice nội bộ, API sau ingress |
| **NodePort** | Cổng trên node theo mô hình Kubernetes | Kết nối tích hợp/kiểm thử được thiết kế; thường không là ingress Internet cuối cùng |
| **LoadBalancer** | Tích hợp cloud load balancer theo cấu hình AKS | Dịch vụ TCP/UDP cần endpoint ngoài hoặc nội bộ |
| **ExternalName** | DNS alias theo CNAME | Chuyển tên dịch vụ đến tên DNS khác; không proxy hay tạo Pod backend |

### Có nên dùng LoadBalancer cho Java API?

Với một lab muốn kiểm tra từ Internet, có thể tạo **Service type LoadBalancer**, nhưng thao tác có thể tạo Azure Load Balancer/public IP và phát sinh chi phí/bề mặt tấn công. Trong production, nên đánh giá **ingress controller/Gateway API**, **Azure Application Gateway/Application Gateway for Containers** hoặc kiến trúc Front Door trước, nhất là khi cần nhiều host/path, TLS/WAF và policy tập trung.

**Ví dụ khái niệm** cho LoadBalancer:

~~~yaml
spec:
  type: LoadBalancer
  selector:
    app: java-api
  ports:
    - port: 80
      targetPort: http
~~~

Đoạn trên **không phải manifest đầy đủ** và không yêu cầu bạn triển khai. Đừng đổi Service từ ClusterIP thành LoadBalancer trên production khi chưa xác định public/private annotation, IP SKU, TLS, firewall, ingress và ngân sách.

### ClusterIP có thể bị truy cập trái phép từ mọi Pod không?

ClusterIP không phơi public IP mặc định, nhưng **không có nghĩa mọi Pod trong cluster đều bị chặn khỏi nó**. Muốn phân quyền east-west traffic, hãy dùng network policies hỗ trợ bởi AKS/network plugin, service authentication và authorization trong Java API.

Service chỉ thực hiện network forwarding; nó không xác thực token của người dùng hay áp dụng business authorization cho API.

## 20. Cấu hình: ConfigMap, Secret và Azure Key Vault

### Cấu hình không nhạy cảm qua ConfigMap

Bạn đã thấy **APP_MESSAGE** trong ConfigMap. Với giá trị configuration như LOG_LEVEL hoặc FEATURE_X_ENABLED, ConfigMap cho phép tách code/image khỏi môi trường triển khai.

Ví dụ một Java API cần endpoint phụ thuộc:

~~~text
ORDER_SERVICE_URL=http://order-service.internal
LOG_LEVEL=INFO
APP_MESSAGE=Hello from AKS
~~~

**Không dựa vào env var chứa tên host bất kỳ để tự tạo quyền truy cập**. Network, DNS và identity vẫn phải được thiết kế.

### Secret và quản lý dữ liệu nhạy cảm

Không đưa password hoặc token vào ConfigMap, Dockerfile, manifest trong repo hoặc lệnh CLI có thể lưu shell history. Kubernetes Secret cũng cần kiểm soát RBAC, encryption at rest và cách inject an toàn.

Với Azure, có thể cân nhắc **Azure Key Vault Secrets Store CSI Driver** cùng **Microsoft Entra Workload ID** khi AKS và ứng dụng hỗ trợ. Luồng khái niệm:

~~~text
Java Pod (Kubernetes service account)
     |
     | Workload identity federation / workload ID
     v
Microsoft Entra ID
     |
     v
Azure Key Vault
     |
     v
Secrets được ứng dụng sử dụng theo tích hợp được thiết kế
~~~

**Workload identity đọc Key Vault không nhất thiết là identity của kubelet dùng để pull image từ ACR.** Đừng cấp quyền registry push cho Java Pod chỉ vì nó cần đọc secret trong Key Vault.

### ConfigMap thay đổi có hiệu lực lúc nào?

Trong ví dụ dùng **envFrom**, Pod nhận environment variables tại lúc container khởi động. Sau khi cập nhật ConfigMap, cần rollout/restart có kiểm soát:

~~~bash
kubectl rollout restart deployment/java-api -n java-demo
kubectl rollout status deployment/java-api -n java-demo
~~~

Trên production, restart nhiều Pod phải có capacity và readiness phù hợp. Với ConfigMap được mount qua volume, hành vi refresh khác env var và cần kiểm tra cách ứng dụng reload cấu hình.

## 21. Quan sát ứng dụng Java trên AKS

Các bước đọc thông tin nên tiến hành từ trên xuống:

~~~bash
kubectl get deployment java-api -n java-demo
kubectl get replicaset -n java-demo -l app=java-api
kubectl get pods -n java-demo -l app=java-api -o wide
kubectl get service java-api -n java-demo
kubectl get endpointslice -n java-demo \
  -l kubernetes.io/service-name=java-api
~~~

### Xem logs

~~~bash
kubectl logs -n java-demo \
  -l app=java-api \
  --all-containers=true \
  --tail=100 \
  --prefix=true
~~~

Log dùng để xem Spring Boot startup, exception, port listener và trace nghiệp vụ. Tránh ghi access token, mật khẩu và thông tin người dùng vào log.

### Describe và events

Khi một Pod Pending/NotReady:

~~~bash
kubectl describe deployment java-api -n java-demo
kubectl get pods -n java-demo -l app=java-api
kubectl get events -n java-demo \
  --sort-by=.metadata.creationTimestamp
~~~

Muốn xem một Pod cụ thể:

~~~bash
kubectl describe pod <POD_NAME> -n java-demo
kubectl logs <POD_NAME> -n java-demo --previous
~~~

**--previous** chỉ có dữ liệu khi tồn tại container instance trước đó trong Pod theo điều kiện Kubernetes; nó có ích với CrashLoopBackOff nhưng không bảo đảm có log nếu Pod mới chưa từng restart.

### Azure Monitor và Application Insights

Trong production, cân nhắc **Azure Monitor managed service for Prometheus**, Container Insights và **Application Insights/OpenTelemetry** theo nhu cầu để thu metrics, logs/traces và correlation giữa Pod, Service và backend.

Những công cụ này phải được cấu hình, cấp quyền và ngân sách riêng; **AKS không tự thu mọi JVM metric hoặc business trace** chỉ vì cluster đã được tạo.

## 22. Bảng lỗi thường gặp khi triển khai Java

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| **ImagePullBackOff / ErrImagePull** | Sai registry/image/tag, thiếu quyền pull, ACR firewall/DNS, CPU architecture không khớp | Pod events, kubelet identity, ACR permissions, mạng và tag/digest |
| **CrashLoopBackOff** | Java process thoát vì thiếu config, lỗi classpath, JAR sai, OOM hoặc startup lỗi | Logs hiện tại/--previous, exit code, runtime config |
| **OOMKilled** | Container vượt memory limit, heap/native memory quá cao | kubectl describe pod, limits, JVM metrics |
| **Pending** | Thiếu CPU/RAM/node, quota, taints/tolerations, zone/affinity | Scheduler events, node capacity, requests |
| **Running nhưng NotReady** | Readiness URL 404/503, app chưa start, dependency bắt buộc lỗi | Probe settings, logs, status, endpoint URL |
| **Service có ClusterIP nhưng không truy cập được** | Selector sai, không có ready endpoints, targetPort sai, network policy | Labels, EndpointSlice, Service describe |
| **Port-forward connect rồi lỗi** | Không có Ready Pod phù hợp, app chưa listen, local port bị chiếm | Port-forward output, Pods, target port |
| **HTTP 404 cho /actuator/health/readiness** | Thiếu Actuator, sai base path hoặc probes chưa bật | POM, Spring Boot config và startup logs |
| **HTTP 500** | Exception ứng dụng, lỗi database, dependency hoặc logic | App logs, trace, request correlation |
| **Rollout bị treo** | Pod mới không Ready hoặc maxSurge thiếu capacity | Rollout status, describe, Pod events |
| **Có 2 replicas nhưng vẫn mất dịch vụ khi node lỗi** | Cả hai Pod ở một node/zone, không đủ capacity thay thế | Pod placement, topology spread, node pools |
| **Sai cấu hình sau sửa ConfigMap** | envFrom không cập nhật vào Pod hiện có | Rollout restart và verify environment qua kênh an toàn |
| **Ứng dụng chạy local nhưng fail ở AKS** | Khác Java version/CPU, filesystem permissions, env/secrets hoặc port | Image metadata, non-root user, logs |
| **Rollout undo không sửa được lỗi database** | Migration/schema hoặc dữ liệu không được rollback cùng Deployment | Database recovery plan và compatibility |

**Đừng sửa nhiều lớp cùng lúc**. Chọn một giả thuyết dựa trên events/logs, thực hiện một thay đổi có thể rollback, rồi kiểm tra lại.

## 23. Tình huống A: ImagePullBackOff từ ACR private

**Bối cảnh:** pipeline đẩy image thành công, Deployment đã apply, nhưng Pod hiện:

~~~text
STATUS: ImagePullBackOff
Failed to pull image ".../java-api:1.0.0"
~~~

### Cách xử lý theo thứ tự

1. Kiểm tra image reference trong Deployment có đúng registry login server, repository và tag/digest không.
2. Xem **kubectl describe pod** để tìm thông điệp cụ thể: **unauthorized**, **manifest unknown**, **DNS timeout** hay lỗi registry khác.
3. Xác minh kubelet identity và **ACR role assignment permissions mode**.
4. Với registry RBAC thông thường, kiểm tra quyền **AcrPull** cho principal thích hợp. Với ABAC, kiểm tra role reader/condition repository được hỗ trợ.
5. Nếu registry private, kiểm tra ACR login/data endpoint, Private DNS, egress/firewall và đường mạng từ AKS nodes.
6. Kiểm tra manifest đã có và image hỗ trợ CPU architecture của node pool.
7. Retry rollout sau khi sửa nguyên nhân, ghi nhận thay đổi.

**Không bật public access hoặc admin password trên ACR production** chỉ vì Pod chưa pull được image. Cần phân biệt lỗi identity, network và artifact.

## 24. Tình huống B: Spring Boot chạy nhưng Service không có backend

**Bối cảnh:** hai Pod Running, Service/java-api tồn tại với ClusterIP, nhưng curl qua Service không thành công.

### Những câu hỏi cần kiểm tra

- Pod có **READY 1/1** hay chỉ **STATUS Running**?
- **kubectl get endpointslice** có endpoint ready không?
- Service selector **app=java-api** có khớp Pod labels không?
- Spring Boot thật sự listen trên **8080**?
- Service **targetPort: http** có khớp tên container port **http**?
- Probe **/actuator/health/readiness** có tồn tại và trả HTTP 200 không?
- Có NetworkPolicy chặn client → Pod không?

Nếu endpoint không ready vì Actuator thiếu, hãy sửa dependency/config/probes đúng cách. **Không xóa readinessProbe để làm Deployment “xanh”** khi app vẫn chưa sẵn sàng nhận request.

## 25. Tình huống C: Java bị OOMKilled sau khi scale

**Bối cảnh:** app chạy local, trên AKS mỗi Pod có memory limit **512Mi**, nhưng JVM dùng heap và native memory lớn. Kubelet ghi OOMKilled.

### Hướng xử lý

1. Xem **kubectl describe pod**, container lastState/exit reason, metrics và logs.
2. Xác định memory limit, heap options, số threads, direct buffers và class loading.
3. Chạy benchmark workload tương tự production, đo peak/percentiles.
4. Giảm footprint Java hoặc tăng memory request/limit có lý do, đồng thời kiểm tra node capacity.
5. Kiểm tra Java 21 container awareness/JVM ergonomics, không đặt **-Xmx** bằng toàn bộ container limit.
6. Tối ưu concurrency/connection pool và điều tra memory leak nếu cần.

**Scale thêm số Pod không tự chữa memory leak** trong mỗi Pod. Nếu mỗi Pod còn bị OOM, việc tăng replicas có thể gây lặp lại lỗi và tăng chi phí.

## 26. Bài thực hành hoàn chỉnh trên AKS lab

### Mục tiêu và giới hạn

Bài tập yêu cầu tạo một ứng dụng Java, build image, push vào ACR, triển khai hai Pod qua Deployment và kiểm tra bằng Service ClusterIP. Chỉ sử dụng **cluster/registry lab đã có hoặc được phép tạo**. Không chạy lệnh xóa cluster, thay ACR role toàn subscription hoặc mở LoadBalancer public ngoài phạm vi được phê duyệt.

### Các bước

1. Tạo dự án Maven theo mục 5 và Dockerfile theo mục 6.
2. Chạy local **mvn test**, **mvn package**, **docker build/run** và kiểm tra **/api/hello**, hai health endpoints.
3. Đăng nhập Azure, chọn subscription lab, lấy ACR login server, build/push **java-api:1.0.0**.
4. Kiểm tra AKS kubeconfig context; chắc chắn đang ở **lab cluster**.
5. Tạo namespace **java-demo** nếu chưa tồn tại và được phép dùng.
6. Lưu **k8s/java-api.yaml** chứa lần lượt **ConfigMap**, **Deployment**, **Service** ở mục 10–12; giữa các document YAML có dấu **---**.
7. Thay **<ACR_LOGIN_SERVER>** bằng hostname registry hợp lệ.
8. Kiểm tra image pull identity của AKS được cấp quyền đúng mode và network tới ACR hoạt động.
9. Chạy **kubectl apply --dry-run=client --validate=true -f k8s/java-api.yaml** rồi **kubectl apply -f k8s/java-api.yaml**.
10. Theo dõi **kubectl rollout status**, kiểm tra **2/2** replicas available khi cluster đủ capacity.
11. Xem **Service**, **EndpointSlice** và **Pod labels/readiness**.
12. Dùng **kubectl port-forward -n java-demo service/java-api 8080:80** và **curl /api/hello**.
13. Thay ConfigMap APP_MESSAGE và thực hiện **kubectl rollout restart** nếu được phép; kiểm tra giá trị mới.
14. Build/push phiên bản **1.0.1**, cập nhật manifest image, rollout rồi kiểm tra; diễn tập rollback trong lab nếu có vấn đề.
15. Ghi nhận mọi lỗi và chi phí phát sinh, dọn **chỉ các tài nguyên do bài lab tạo**.

### Bảng bằng chứng

| Hạng mục | Kết quả phải kiểm tra |
|---|---|
| Artifact | JAR chạy được; Docker image có tag/digest |
| Registry | Repository java-api chứa release đã push |
| Identity | AKS kubelet có quyền pull tối thiểu |
| Deployment | Có 2 desired replicas, image/port/probes đúng |
| Pods | 2 Pod Running **và Ready** (khi cluster đủ capacity) |
| Service | ClusterIP :80; selector app=java-api |
| EndpointSlice | Có ready endpoints tương ứng |
| HTTP | /api/hello trả JSON và /actuator/health/readiness trả thành công |
| Rollout | Phiên bản mới được triển khai; biết cách undo khi cần |
| Security | Không public LB, không hard-code secret, container non-root |
| Cost | Ghi nhận tài nguyên đã dùng và kế hoạch cleanup |

### Dọn dẹp an toàn

Nếu manifest chứa **chỉ ba tài nguyên của bài thực hành**:

~~~bash
kubectl delete -f k8s/java-api.yaml

kubectl get all -n java-demo
kubectl get configmap -n java-demo
~~~

Lệnh delete theo manifest chỉ xóa các tài nguyên khai báo trong manifest tương ứng, nhưng có thể ảnh hưởng workload nếu bạn đã tái sử dụng tên. **Kiểm tra current-context và namespace trước khi xóa**.

Nếu namespace **java-demo** được tạo riêng và không còn tài nguyên người khác:

~~~bash
kubectl delete namespace java-demo
~~~

Xóa namespace sẽ xóa **mọi tài nguyên namespaced** bên trong, không chỉ app mẫu. Không xóa nếu namespace dùng chung. **Không xóa AKS cluster, node pool hoặc ACR** của tổ chức để kết thúc bài tập. Image demo trong ACR có thể cần dọn theo retention/quy trình của chủ registry.

## 27. Triển khai production: những lớp cần bổ sung

Deployment và Service trong bài là nền tảng kỹ thuật, chưa phải kiến trúc production hoàn chỉnh. Với Java API có người dùng thật, cần bổ sung các yếu tố:

| Nhóm | Câu hỏi trước khi mở production |
|---|---|
| **Ingress/TLS** | API đi qua ingress/Gateway/Application Gateway nào? HTTPS, domain, WAF và authentication được cấu hình ra sao? |
| **Network policy** | Service nào/namespace nào được gọi Java API? Egress đi database/Key Vault qua đâu? |
| **Identity** | App dùng Workload ID cho Azure dependencies? Kubelet chỉ có quyền ACR pull? |
| **Secrets** | Key Vault, CSI Driver hoặc secret manager phù hợp đã có RBAC/audit chưa? |
| **Availability** | Node pools đủ headroom, Pod phân bố nhiều node/zone, PDB và autoscaling? |
| **Data** | Ứng dụng stateless chưa? Nếu cần state, dùng database/storage có backup/DR? |
| **Health** | Liveness/readiness/startup probe có phản ánh trạng thái thật và tránh restart storm? |
| **Resource limits** | CPU/memory/JVM sizing dựa trên load test chưa? |
| **Security** | Non-root, image scanning, SBOM, signed images, admission policy, RBAC? |
| **Rollout** | Canaries/rolling updates, schema compatibility, rollback và change approval? |
| **Observability** | Logs/metrics/traces, Alert rules, SLOs và chi phí lưu log? |
| **DR** | Cluster/registry/data/ingress ở region khác có runbook và đã diễn tập? |

### Tránh lưu dữ liệu bền vững trong container filesystem

Deployment thường dùng Pod có vòng đời thay thế được. Dữ liệu viết vào filesystem tạm của container có thể mất khi Pod bị thay. Với đơn hàng, tài liệu, session hoặc file upload, dùng dịch vụ dữ liệu bền vững như Azure SQL, Blob Storage, Azure Files hoặc PersistentVolume theo kiến trúc.

**Deployment với 2 replicas không tạo database replication.** Nếu ứng dụng cần giao dịch và nhất quán dữ liệu, phải thiết kế storage/database độc lập với vòng đời Pod.

### Lưu ý chi phí

AKS và ACR có các khoản phí theo mô hình/tier thực tế: node compute, disk, load balancer, public IP, log ingestion/retention, registry storage, egress và các tính năng thêm. Tạo Deployment 2 replicas có thể tăng mức sử dụng node hoặc kích hoạt scale-out. **Budget alerts không tự giới hạn tài nguyên hoặc ngừng hóa đơn**.

## 28. Checklist trước khi kết thúc bài

- [ ] Đã hiểu Deployment quản lý Pods/ReplicaSets còn Service tạo endpoint ổn định.
- [ ] Java API build thành JAR, chạy local và chạy trong container đúng port 8080.
- [ ] Image được push lên ACR dưới tag duy nhất/digest đã xác nhận.
- [ ] AKS kubelet được cấp quyền image pull phù hợp với registry mode, không dùng admin password.
- [ ] Kubeconfig context và namespace đúng môi trường được phép.
- [ ] Deployment selector khớp template labels; Service selector khớp Pod labels.
- [ ] Service port/targetPort khớp cổng container và Java thực sự lắng nghe.
- [ ] Probes kiểm tra đúng endpoints đang được Spring Boot cung cấp.
- [ ] CPU/memory requests và limits phù hợp cho JVM, không OOMKilled.
- [ ] Cluster đủ node capacity cho rolling update với maxSurge.
- [ ] Service là ClusterIP cho bài lab; không vô tình tạo public LoadBalancer.
- [ ] Đã xem ReplicaSets, Pods, EndpointSlices, events và logs để hiểu trạng thái.
- [ ] Đã kiểm tra /api/hello qua port-forward và readiness.
- [ ] Đã thử rollback/rollout có kiểm soát, không thay image bằng tag latest mutable.
- [ ] Đã tách ConfigMap không nhạy cảm khỏi secrets và workload identity.
- [ ] Có phương án cleanup an toàn và ghi lại chi phí.

## 29. Câu hỏi tự kiểm tra

1. Deployment khác Service như thế nào? Vì sao thường cần cả hai?
2. Tại sao Service không định tuyến thẳng bằng tên Deployment?
3. Điều gì xảy ra nếu Service selector không khớp Pod labels?
4. **containerPort**, **port** và **targetPort** khác nhau ra sao?
5. Tại sao Pod Running chưa chắc được Service đưa vào danh sách endpoints?
6. Khi nào dùng **ClusterIP**, khi nào cần **LoadBalancer/Ingress**?
7. Với Spring Boot, readiness và liveness probe phục vụ hai quyết định gì?
8. Vì sao dùng startupProbe giúp một Java app khởi động chậm?
9. **maxSurge=1** có ảnh hưởng gì khi node pool đã đầy?
10. Vì sao quay về bản Deployment cũ không tự rollback database?
11. Khi gặp ImagePullBackOff, cần kiểm tra identity, network và image reference theo thứ tự nào?
12. AKS kubelet identity khác workload identity của Java Pod ở đâu?
13. Vì sao không đặt password database trong ConfigMap hoặc Dockerfile?
14. Với memory limit 1Gi, có nên đặt JVM max heap đúng 1Gi không?
15. Nếu cập nhật ConfigMap dùng envFrom, Pod đang chạy có tự nhận giá trị mới không?
16. Nếu API chỉ cần gọi trong cluster, có cần cấp public IP không?
17. Cluster HPA và Deployment replicas được điều phối như thế nào để tránh ghi đè cấu hình?
18. Vì sao cần pin digest khi triển khai cùng phiên bản ở nhiều region?

## 30. Tài liệu tham khảo

- [What is Azure Kubernetes Service (AKS)?](https://learn.microsoft.com/azure/aks/what-is-aks) — mô hình AKS và trách nhiệm quản trị.
- [Deploy an application to AKS](https://learn.microsoft.com/azure/aks/learn/quick-kubernetes-deploy-cli) — thao tác kubectl và ứng dụng demo trên AKS.
- [Integrate Azure Container Registry with AKS](https://learn.microsoft.com/azure/aks/cluster-container-registry-integration) — kubelet identity, quyền image pull và những hạn chế theo registry mode.
- [Azure Container Registry authentication](https://learn.microsoft.com/azure/container-registry/container-registry-authentication) — identity/permissions cho pull và push.
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — desired state, ReplicaSet, rolling updates.
- [Kubernetes Services](https://kubernetes.io/docs/concepts/services-networking/service/) — ClusterIP, selectors, ports và endpoint routing.
- [Configure liveness, readiness and startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) — cách Kubernetes kiểm tra Pod.
- [Kubernetes resource management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/) — requests, limits và scheduler.
- [Configure ConfigMaps in Pods](https://kubernetes.io/docs/concepts/configuration/configmap/) — tách cấu hình khỏi image.
- [Spring Boot Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — health và probes ở phía ứng dụng.
- [Azure Workload ID for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview) — workload identity liên kết Microsoft Entra ID.
- [Azure CLI: az aks](https://learn.microsoft.com/cli/azure/aks) — quyền cluster và kết nối AKS.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — ước tính chi phí compute, networking và ACR.

**Kết luận:** Triển khai Java trên AKS không dừng ở **docker push** hay **kubectl apply**. Deployment phải khai báo đúng image, resource, probes và chính sách cập nhật; Service phải chọn đúng các Pod sẵn sàng và ánh xạ đúng cổng. Khi kết hợp ACR permissions, Kubernetes RBAC, network, quan sát và rollout/rollback có kiểm soát, bạn có thể chuyển một ứng dụng Java từ JAR chạy local thành dịch vụ trên AKS có thể mở rộng, vận hành và phục hồi theo mục tiêu của hệ thống.
