# Quan sát bản sao nhận yêu cầu để kiểm chứng phân phối

## Mục tiêu của phép quan sát

Trong chương **Cân bằng tải** của module **SPRING_CLOUD_KUBERNETES**, điều cần chứng minh là yêu cầu thực sự tới những bản sao nào của ứng dụng Spring đang chạy trên Kubernetes. Ba Pod ở trạng thái Running và nhiều phản hồi HTTP 200 chưa đủ để kết luận cả ba Pod đều nhận tải.

Sau bài này, bạn có thể:

- Gắn định danh của Pod xử lý vào phản hồi và log ứng dụng.
- Gửi một tập yêu cầu có mã tương quan qua đúng client dùng Spring Cloud LoadBalancer.
- Đếm số phản hồi theo từng Pod, đồng thời ghi nhận lỗi và thiếu dữ liệu.
- Giải thích kết quả dựa trên đường đi của yêu cầu, trạng thái Ready, retry và thời điểm thay đổi tập bản sao.

Bài thực hành sử dụng DiscoveryClient và Spring Cloud LoadBalancer. ConfigMap, Secret và Configuration Watcher không phải điều kiện để quan sát bản sao; chỉ bật những tính năng Kubernetes mà ứng dụng thực sự cần. RBAC liên quan ở đây là quyền đọc thông tin phục vụ discovery của ứng dụng gọi.

## 1. Xác định tầng đang phân phối yêu cầu

Có hai đường đi cần phân biệt:

| Đường đi | Thành phần quyết định đích tiếp theo | Điều có thể kết luận từ phản hồi |
| --- | --- | --- |
| Client có `@LoadBalanced`, chế độ `POD` | Spring Cloud LoadBalancer chọn một instance do DiscoveryClient cung cấp | Pod nào thực sự trả lời sau lựa chọn ở phía ứng dụng gọi |
| Client đi qua Kubernetes Service, gồm chế độ `SERVICE` | Kubernetes Service và cơ chế mạng phía sau định tuyến đến endpoint | Pod nào thực sự trả lời trên đường qua Service |

Ở chế độ `POD`, Spring Cloud Kubernetes tra cứu instance theo service ID. Ở chế độ `SERVICE`, đích gọi được dựng theo Service và namespace. Hãy khai báo chế độ rõ ràng khi làm thí nghiệm. Xem [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Sơ đồ cho lượt thử chính của bài:

~~~mermaid
flowchart LR
    T[Trình gửi yêu cầu] --> C[probe-client: /probe]
    C --> L[WebClient có LoadBalancer - POD]
    D[DiscoveryClient] -. danh sách instance .-> L
    K[Kubernetes API] -. thông tin discovery .-> D
    L --> A[replica-echo - Pod A]
    L --> B[replica-echo - Pod B]
    L --> E[replica-echo - Pod C]
~~~

Mũi tên discovery biểu diễn luồng thông tin, không phải đường chuyển tiếp nội dung HTTP của từng yêu cầu.

Nếu gọi trực tiếp `http://replica-echo:8080/whoami` bằng một HTTP client thông thường trong cluster, bạn đang kiểm tra đường Service/DNS. Nếu gọi địa chỉ đó bằng WebClient đã gắn LoadBalancer ở chế độ `POD`, tên `replica-echo` được dùng làm service ID để chọn instance. Cùng một chuỗi URL có thể đi qua các cơ chế khác nhau tùy cấu hình client.

## 2. Chuẩn bị một lượt thử có thể giải thích

Giả sử có namespace thực hành `lb-lab`, ứng dụng đích `replica-echo` và ứng dụng gọi `probe-client`.

| Thành phần | Điều kiện của lượt thử ban đầu |
| --- | --- |
| Backend | Ba Pod cùng phiên bản ứng dụng, đều Ready, nhãn `app=replica-echo` |
| Caller | Một Pod `probe-client`, dùng một WebClient có LoadBalancer được tái sử dụng |
| Service | Tên `replica-echo`, cổng 8080, selector đúng các Pod backend |
| Discovery | Nhìn thấy đúng namespace và tập instance của backend |
| Lưu lượng | Gửi tuần tự, không có tải nền vào cùng endpoint |
| Retry | Tắt retry trong phép đo ban đầu |
| Hạ tầng | Không có rollout hoặc thay đổi replica trong cửa sổ đo; ghi nhận nếu có proxy hoặc service mesh |

Các đoạn Java dưới đây giả định dự án Spring Boot dùng Java 17 trở lên và một Spring Cloud release train tương thích với Spring Boot của dự án. Đây là các thành phần thêm vào hai ứng dụng Spring Boot đã có lớp khởi động; không cần đổi phiên bản thư viện chỉ để thực hiện phép quan sát.

Các lệnh trong bài dành cho môi trường thực hành đã triển khai ứng dụng. Image phải chứa đúng mã minh họa trước khi chạy phép đo. Thay tên namespace, Deployment hoặc nhãn nếu môi trường của bạn dùng tên khác.

## 3. Để backend tự khai báo Pod đã xử lý

### 3.1. Cấp định danh từ Downward API

Trong container của Deployment backend, thêm các biến môi trường sau:

~~~yaml
spec:
  replicas: 3
  template:
    metadata:
      labels:
        app: replica-echo
    spec:
      containers:
        - name: app
          # Giữ image ứng dụng đã được build và phát hành cho môi trường lab.
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: POD_UID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.uid
            - name: POD_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
~~~

Đây là phần cấu hình cần ghép vào Deployment hiện có, không phải manifest Deployment đầy đủ. Phải giữ các trường bắt buộc như image và selector của workload.

Downward API có thể đưa tên, UID và namespace của chính Pod vào container mà backend không phải gọi Kubernetes API để đọc các giá trị này. Xem [Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/).

Pod name dễ đọc trong bảng kết quả. Pod UID phân biệt chính xác đối tượng Pod, kể cả khi một tên được tái sử dụng sau khi Pod cũ bị thay thế. Container khởi động lại trong cùng Pod vẫn giữ Pod UID; muốn phân biệt từng lần khởi động tiến trình thì cần thêm một định danh khởi động riêng.

### 3.2. Trả định danh trong JSON, header và log

Trong ứng dụng backend có Web starter hoặc WebFlux starter, đặt controller sau trong package được Spring Boot quét:

~~~java
package example.echo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    private static final Logger log =
            LoggerFactory.getLogger(WhoAmIController.class);

    private final String podName;
    private final String podUid;
    private final String namespace;

    public WhoAmIController(
            @Value("${POD_NAME:local}") String podName,
            @Value("${POD_UID:local}") String podUid,
            @Value("${POD_NAMESPACE:local}") String namespace) {
        this.podName = podName;
        this.podUid = podUid;
        this.namespace = namespace;
    }

    @GetMapping("/whoami")
    public ResponseEntity<ReplicaReply> whoami(
            @RequestHeader("X-Request-Id") String requestId) {
        log.info("replica_probe requestId={} pod={} uid={}",
                requestId, podName, podUid);

        return ResponseEntity.ok()
                .header("X-Served-By", podName)
                .header("X-Request-Id", requestId)
                .body(new ReplicaReply(requestId, podName,
                        podUid, namespace));
    }

    public record ReplicaReply(
            String requestId,
            String podName,
            String podUid,
            String namespace) {
    }
}
~~~

Một phản hồi minh họa:

~~~json
{
  "requestId": "lb-run01-001",
  "podName": "replica-echo-7b96c76c5c-q2m8v",
  "podUid": "80484e89-1bc5-4e5b-b602-31a66ab9eb74",
  "namespace": "lb-lab"
}
~~~

Các giá trị tên và UID trên chỉ minh họa. Trong cluster, nếu nhận `local`, hãy kiểm tra việc truyền biến môi trường và image đang chạy trước khi thống kê.

Request ID gắn một lần gọi từ trình gửi với phản hồi và log backend. Nó không phải định danh Pod. Bài thực hành tự sinh ID an toàn, không trùng trong một lượt; khi đưa cơ chế này vào ứng dụng thực tế, cần kiểm tra định dạng ID đầu vào và tránh ghi dữ liệu nhạy cảm vào log.

Endpoint quan sát không nên dùng làm readiness probe vì sẽ làm lẫn lưu lượng kiểm tra sức khỏe vào phép đếm log. Giữ endpoint sức khỏe riêng của ứng dụng.

### 3.3. Service chọn đúng backend

Service tương ứng trong namespace thực hành:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: replica-echo
  namespace: lb-lab
spec:
  selector:
    app: replica-echo
  sessionAffinity: None
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

`sessionAffinity: None` phù hợp cho phép thử đường qua Service không cố ý ghim theo IP client. Thiết lập này không điều khiển việc chọn Pod trực tiếp của Spring Cloud LoadBalancer ở chế độ `POD`.

## 4. Gửi qua đúng WebClient có LoadBalancer

### 4.1. Dependency và cấu hình phía caller

Trong dự án caller, sử dụng các dependency sau với BOM Spring Cloud tương thích của dự án. Ví dụ chọn Kubernetes Java Client; không thêm song song Fabric8 để làm cùng nhiệm vụ.

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-client</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-client-loadbalancer</artifactId>
</dependency>
~~~

Starter Kubernetes Client phục vụ discovery; starter LoadBalancer tích hợp việc chọn đích với Spring Cloud LoadBalancer. Các lựa chọn client được mô tả tại [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Cấu hình cho caller chạy trong cluster:

~~~properties
spring.application.name=probe-client
spring.cloud.kubernetes.discovery.all-namespaces=false
spring.cloud.kubernetes.discovery.namespaces[0]=lb-lab
spring.cloud.kubernetes.loadbalancer.mode=POD
spring.cloud.loadbalancer.retry.enabled=false
~~~

Không thêm retry ở WebClient, gateway hoặc service mesh trong lượt thử ban đầu. Nếu có các tầng retry đang hoạt động, phải ghi nhận chúng khi đọc kết quả.

Khai báo builder trong ứng dụng caller:

~~~java
package example.probe;

import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableDiscoveryClient
public class ClientConfiguration {
    @Bean
    @LoadBalanced
    public WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Endpoint caller nhận yêu cầu, chuyển request ID và trả kết quả backend:

~~~java
package example.probe;

import java.time.Duration;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
public class ProbeController {
    private final WebClient client;

    public ProbeController(@LoadBalanced WebClient.Builder builder) {
        this.client = builder.build();
    }

    @GetMapping("/probe")
    public Mono<ResponseEntity<String>> probe(
            @RequestHeader("X-Request-Id") String requestId) {
        return client.get()
                .uri("http://replica-echo:8080/whoami")
                .header("X-Request-Id", requestId)
                .exchangeToMono(response -> response.toEntity(String.class))
                .timeout(Duration.ofSeconds(3));
    }
}
~~~

Mỗi lần gọi `/probe` tạo một lần gọi HTTP xuống backend trong điều kiện không có retry. Builder có qualifier `@LoadBalanced`; một WebClient được tạo riêng bằng `WebClient.create()` sẽ không tự nhận cấu hình LoadBalancer của bean trên.

Spring Cloud LoadBalancer hỗ trợ chọn instance và mặc định dùng `RoundRobinLoadBalancer` khi không có cấu hình thay thế. Retry và cache cũng là các yếu tố phải ghi nhận khi đọc kết quả. Xem [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).

### 4.2. Kiểm tra quyền và đường mạng

Caller phải sử dụng ServiceAccount có Role/RoleBinding trong namespace discovery. Quyền cụ thể phụ thuộc implementation và cấu hình discovery; thường cần đọc Service, Pod và tài nguyên endpoint mà client thực sự sử dụng. Nếu dùng EndpointSlice, quyền nằm ở API group `discovery.k8s.io`.

Ví dụ kiểm tra quyền bằng tài khoản vận hành có quyền impersonation:

~~~powershell
kubectl auth can-i list services -n lb-lab --as=system:serviceaccount:lb-lab:probe-client
kubectl auth can-i watch endpoints -n lb-lab --as=system:serviceaccount:lb-lab:probe-client
kubectl auth can-i list endpointslices.discovery.k8s.io -n lb-lab --as=system:serviceaccount:lb-lab:probe-client
~~~

Các lệnh này chỉ minh họa kiểm tra từng quyền; một kết quả `yes` không chứng minh toàn bộ quyền cần thiết đã đủ. Nếu chính lệnh bị từ chối impersonation, đó chưa phải kết luận về quyền của caller. Đối chiếu tài nguyên và động từ bị báo `Forbidden` trong log ứng dụng rồi cấp quyền đúng phạm vi. Không cần cấp quyền đọc Secret hoặc quyền quản trị cluster để trả định danh bản sao.

Ở chế độ `POD`, NetworkPolicy phải cho phép caller đến cổng backend tại IP Pod. Chỉ phân giải được tên Service chưa chứng minh đường gọi trực tiếp tới Pod đã thông.

## 5. Chốt tập Pod trước khi đo

Thực hiện trong terminal dành cho lab:

~~~powershell
kubectl -n lb-lab rollout status deployment/replica-echo
kubectl -n lb-lab rollout status deployment/probe-client
kubectl -n lb-lab get pods -l app=replica-echo -o wide
kubectl -n lb-lab get pods -l app=replica-echo -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,IP:.status.podIP'
kubectl -n lb-lab get service replica-echo -o yaml
kubectl -n lb-lab get endpointslices -l kubernetes.io/service-name=replica-echo -o yaml
~~~

Ghi lại ba Pod name và UID, thời điểm bắt đầu, chế độ LoadBalancer, số caller và phiên bản ứng dụng. Kiểm tra Service selector, địa chỉ endpoint và trạng thái Ready của endpoint. Tập Pod của Deployment, tập endpoint của Service và tập instance caller nhìn thấy cần được đối chiếu, không chỉ đếm giá trị `replicas` mong muốn. Cách kiểm tra selector và endpoint nằm trong hướng dẫn [Debug Services](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/).

Nếu caller dùng cơ chế endpoint khác, đối chiếu thêm tài nguyên tương ứng mà phiên bản client đó theo dõi. Việc có EndpointSlice đúng trong Kubernetes chưa tự chứng minh cache discovery của caller đã cập nhật.

Để gửi từ máy cá nhân, mở một terminal riêng:

~~~powershell
kubectl -n lb-lab port-forward deployment/probe-client 18080:8080
~~~

Port-forward này cố định điểm vào là caller để quan sát các lựa chọn backend của caller. **Không port-forward vào Deployment hoặc Service backend rồi dùng kết quả đó để kết luận backend được phân phối qua LoadBalancer.** Port-forward tới Service cuối cùng cũng chọn một Pod để chuyển tiếp, không phải phép thử đường Service ClusterIP thông thường.

## 6. Gửi 300 yêu cầu và giữ cả bản ghi lỗi

Chạy PowerShell sau trong terminal thứ hai. Đổi `$probeRun` ở mỗi lượt thử. Đoạn mã chỉ giữ kết quả trong bộ nhớ; không cần tạo file thống kê.

~~~powershell
$probeRun = 'lb-run01'
$probeTotal = 300
$probeUrl = 'http://localhost:18080/probe'

# Làm nóng riêng, không gộp vào mẫu đo.
1..6 | ForEach-Object {
    $warmId = '{0}-warm-{1:D3}' -f $probeRun, $_
    try {
        $null = Invoke-RestMethod -Method Get -Uri $probeUrl `
            -Headers @{ 'X-Request-Id' = $warmId } -TimeoutSec 5
    } catch {
        Write-Warning ('Warm-up chưa thành công: {0}' -f $warmId)
    }
}

$probeRows = @(foreach ($index in 1..$probeTotal) {
    $requestId = '{0}-{1:D3}' -f $probeRun, $index
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $reply = Invoke-RestMethod -Method Get -Uri $probeUrl `
            -Headers @{ 'X-Request-Id' = $requestId } -TimeoutSec 5

        if ($reply.requestId -ne $requestId) {
            throw 'Request ID trong phản hồi không khớp.'
        }
        if ([string]::IsNullOrWhiteSpace([string]$reply.podName) -or
            [string]::IsNullOrWhiteSpace([string]$reply.podUid) -or
            $reply.podName -eq 'local' -or $reply.podUid -eq 'local') {
            throw 'Phản hồi thiếu định danh Pod hợp lệ cho cluster.'
        }
        if ($reply.namespace -ne 'lb-lab') {
            throw 'Phản hồi thuộc namespace ngoài phép thử.'
        }

        $watch.Stop()
        [pscustomobject]@{
            RequestId = $requestId
            PodName = [string]$reply.podName
            PodUid = [string]$reply.podUid
            Success = $true
            LatencyMs = $watch.ElapsedMilliseconds
            Error = ''
        }
    } catch {
        $watch.Stop()
        [pscustomobject]@{
            RequestId = $requestId
            PodName = ''
            PodUid = ''
            Success = $false
            LatencyMs = $watch.ElapsedMilliseconds
            Error = $_.Exception.Message
        }
    }
})

$probeGood = @($probeRows | Where-Object { $_.Success })
$probeBad = @($probeRows | Where-Object { -not $_.Success })

$probeRows | Select-Object -First 12 | Format-Table

$probeDistribution = @($probeGood |
    Group-Object -Property PodUid |
    ForEach-Object {
        [pscustomobject]@{
            PodName = $_.Group[0].PodName
            PodUid = $_.Name
            Responses = $_.Count
            PercentOfSuccess = [math]::Round(
                100.0 * $_.Count / $probeGood.Count, 2)
        }
    } |
    Sort-Object -Property PodName)

$probeDistribution | Format-Table -AutoSize
[pscustomobject]@{
    Sent = $probeTotal
    SuccessfulResponses = $probeGood.Count
    FailedOrInvalid = $probeBad.Count
    ObservedPods = $probeDistribution.Count
} | Format-List

$probeBad | Select-Object -First 10 | Format-Table -AutoSize
~~~

`Invoke-RestMethod` đưa lỗi HTTP hoặc lỗi gọi vào nhánh `catch`. Các phản hồi thiếu định danh hoặc không khớp request ID cũng bị ghi nhận là mẫu lỗi, không bị bỏ qua. Lượt warm-up có ID riêng nên không lẫn vào 300 yêu cầu chính.

Nếu toàn bộ yêu cầu thất bại, bảng phân phối rỗng; không có phép chia cho không vì không có nhóm thành công nào để tính. Hãy xử lý lỗi trước khi bàn về cân bằng tải.

Mẫu đo trên đếm **phản hồi hợp lệ mà trình gửi nhận được**. Nó không đếm đầy đủ mọi lần backend đã thực thi: một backend có thể xử lý xong nhưng phản hồi bị mất hoặc caller bị timeout. Bởi vậy vẫn cần log để đối chiếu khi có lỗi.

## 7. Đọc kết quả theo giả thiết của lượt thử

Ví dụ minh họa một lượt ổn định:

| Pod | Phản hồi hợp lệ | Tỷ lệ trên 300 phản hồi |
| --- | ---: | ---: |
| replica-echo-…-q2m8v | 100 | 33,33% |
| replica-echo-…-r6n4b | 100 | 33,33% |
| replica-echo-…-t9k7p | 100 | 33,33% |

Đây là số liệu minh họa, không phải kết quả đo sẵn của cluster. Luôn so sánh các UID quan sát được với ảnh chụp tập Pod trước và sau phép đo; chỉ thấy ba tên bất kỳ chưa đủ để xác nhận đó là đúng ba bản sao dự kiến.

Gọi `N_ok` là số phản hồi hợp lệ và `n_i` là số phản hồi của Pod thứ i:

~~~text
Tỷ lệ phản hồi của Pod i = n_i / N_ok × 100%
Tổng phản hồi hợp lệ + tổng mẫu lỗi = số yêu cầu đã gửi
~~~

Nếu ba instance cố định, một caller, không có tải nền, retry, lọc instance hoặc tùy biến thuật toán, kết quả round-robin phải thể hiện việc luân phiên lựa chọn; với đúng 300 lựa chọn thành công, bạn kỳ vọng khoảng 100 cho mỗi instance. Không cần giả định Pod nào được chọn đầu tiên.

Không lấy bảng minh họa làm cam kết chung cho mọi đường gọi. Thuật toán ngẫu nhiên có sai lệch thống kê; nhiều caller có trạng thái lựa chọn độc lập; proxy, chính sách định tuyến, lỗi và thay đổi membership có thể làm số phản hồi khác số lần được chọn. Nếu đang dùng round-robin trong điều kiện kiểm soát mà lệch lớn, cần tìm nguyên nhân thay vì tự coi đó là ngẫu nhiên.

Ba mức kết luận cần tách rõ:

1. **Có phân phối:** nhiều UID thuộc tập backend dự kiến đã trả lời.
2. **Đủ độ bao phủ:** mọi UID dự kiến trong cửa sổ ổn định đều có phản hồi; Pod không xuất hiện phải tính là 0 khi đối chiếu.
3. **Phù hợp chính sách:** tỷ lệ, chuỗi lựa chọn và lỗi phù hợp với thuật toán cùng điều kiện thực tế đã ghi nhận.

Ba Pod nhận số yêu cầu bằng nhau chưa chứng minh CPU, thời gian xử lý hay số tác vụ đang chạy bằng nhau. Muốn đánh giá tải tài nguyên, cần đo thêm thời gian phản hồi, số yêu cầu đang xử lý và tài nguyên từng Pod.

## 8. Đối chiếu request ID với log backend

Sau lượt đo, đọc log của tất cả Pod backend:

~~~powershell
kubectl -n lb-lab logs -l app=replica-echo --all-containers=true --prefix=true --tail=-1 --max-log-requests=10 --since=15m
~~~

Chọn một request ID cụ thể để kiểm tra đường đi:

~~~powershell
kubectl -n lb-lab logs -l app=replica-echo --all-containers=true --prefix=true --tail=-1 --max-log-requests=10 --since=15m |
    Select-String -SimpleMatch 'requestId=lb-run01-001 '
~~~

Một dòng log minh họa:

~~~text
replica_probe requestId=lb-run01-001 pod=replica-echo-7b96c76c5c-q2m8v uid=80484e89-1bc5-4e5b-b602-31a66ab9eb74
~~~

Dòng log đặt trước khi trả phản hồi chứng minh handler đã được gọi tới điểm ghi log; nó không chứng minh trình gửi nhận thành công. Đối chiếu cùng request ID, Pod UID và kết quả phía trình gửi.

Nếu cùng ID xuất hiện nhiều lần, xem xét retry hoặc client gửi lại trước khi kết luận một yêu cầu được nhân bản. Khi thống kê log, lọc đúng các ID thuộc lượt đo và loại ID `warm`; endpoint health, tải nền và lượt thử khác không nằm trong mẫu 300 yêu cầu này.

`--since` chỉ bao phủ cửa sổ đã chọn. Pod bị xóa hoặc container khởi động lại có thể khiến log hiện tại thiếu dữ liệu; với điều tra dài hơn, cần hệ thống tập trung log và metadata Pod. Không suy ra backend chưa xử lý chỉ vì một lệnh đọc log không tìm thấy ID.

## 9. Khi chỉ thấy một bản sao trả lời

| Hiện tượng | Kiểm tra tiếp theo | Hướng giải thích |
| --- | --- | --- |
| Chỉ một UID, nhưng đã port-forward tới backend | Xem đích của lệnh port-forward | Lượt đo bị cố định vào một backend |
| Ba Pod Running nhưng chỉ một endpoint Ready | Readiness, selector, EndpointSlice | Số Pod tồn tại khác số đích đủ điều kiện nhận tải |
| Ba endpoint đúng nhưng caller báo không có instance | Namespace, filter discovery, RBAC, log đồng bộ | Caller chưa có cùng góc nhìn với API Kubernetes |
| HTTP thành công nhưng luôn trả `local` | Biến môi trường và image backend | Thiếu dữ liệu định danh để đo |
| Dùng WebClient tạo thủ công và thấy lệch | Bean được inject, qualifier, chế độ đang chạy | Chưa chứng minh lời gọi đi qua Spring Cloud LoadBalancer |
| Lệch khi đi qua Service | Session affinity, kết nối được tái sử dụng, proxy hoặc mesh | Hành vi thuộc đường mạng Service và chuỗi proxy |
| Một UID biến mất giữa lượt | Rollout, scale, readiness, lỗi mạng, cache discovery | Cửa sổ đo không còn tập backend cố định |
| Log có nhiều dòng cùng ID | Retry từng tầng, thao tác gửi lại | Số lần thực thi có thể lớn hơn số yêu cầu logic |

Kubernetes Service có thể duy trì session affinity theo IP client khi cấu hình `ClientIP`. Ngoài ra, trên đường Service, nhiều yêu cầu HTTP có thể dùng lại một kết nối đã được ánh xạ tới một endpoint. Vì vậy, không thể đòi hỏi mỗi yêu cầu HTTP trong cùng kết nối đều được chọn lại Pod. Chi tiết phụ thuộc cơ chế mạng và proxy đang dùng. Xem [Virtual IPs and Service Proxies](https://kubernetes.io/docs/reference/networking/virtual-ips/).

Trong chế độ `POD`, LoadBalancer phía ứng dụng chọn instance cho lời gọi trước khi kết nối đến địa chỉ đích. Connection pool không tự biến ba địa chỉ Pod đã được chọn thành một địa chỉ Pod duy nhất. Hãy kiểm tra tập instance thực tế và bean client trước khi quy mọi sự lệch cho keep-alive.

## 10. Mở rộng có kiểm soát sau lượt thử ổn định

Chỉ thay một yếu tố mỗi lượt và dùng request ID với tiền tố mới:

- **Tăng backend từ ba lên bốn bản sao:** đợi Pod mới Ready, đối chiếu endpoint và để discovery đồng bộ, rồi chạy một cửa sổ đo mới. UID mới cần xuất hiện trong mẫu mới; không gộp cửa sổ trước và sau scale để đòi tỷ lệ 25% cho toàn bộ dữ liệu.
- **Thử chế độ `SERVICE`:** triển khai lại caller với cấu hình tương ứng rồi đo lại, ghi nhận chính sách Service và kết nối. Không dùng tính luân phiên của lượt `POD` làm chuẩn bắt buộc cho lượt này.
- **Tăng caller lên nhiều bản sao:** bỏ giả định một caller cố định và bổ sung định danh caller vào log hoặc dữ liệu quan sát. Một phiên port-forward vẫn chỉ vào một Pod caller được chọn, nên không tự tạo phép thử nhiều caller.
- **Quan sát backend rời tập Ready:** chỉ thực hiện trong lab có kiểm soát; theo dõi thời điểm endpoint, discovery và phản hồi thay đổi. Các lỗi trong giai đoạn chuyển tiếp phải được giữ lại để đánh giá, không bị xóa khỏi kết quả.

ConfigMap hoặc Configuration Watcher có thể phục vụ các bài cập nhật cấu hình khác trong module. Với phép đo hiện tại, phải biết cấu hình nào thực sự đang có hiệu lực tại caller; sửa nguồn cấu hình chưa đồng nghĩa giá trị chế độ LoadBalancer đã đổi trong tiến trình đang chạy.

## 11. Tiêu chí hoàn tất thực hành

Một bản ghi kết quả đủ để người khác kiểm chứng cần có:

- Namespace, service ID, mode `POD` hoặc `SERVICE`, thuật toán nếu có tùy biến, số caller và thời gian đo.
- Tập Pod name/UID dự kiến cùng trạng thái Ready ở đầu và cuối cửa sổ đo.
- Tổng yêu cầu gửi, tổng phản hồi hợp lệ, tổng lỗi và số phản hồi theo từng UID, bao gồm UID dự kiến có số đếm bằng 0.
- Ít nhất một request ID được đối chiếu giữa dữ liệu trình gửi và log đúng backend.
- Giải thích mức kết luận: có phân phối, đủ độ bao phủ và có phù hợp chính sách trong điều kiện đã thử hay không.

Kết quả quan sát có giá trị khi bạn chỉ ra được **yêu cầu nào đã tới Pod nào, qua cơ chế chọn đích nào và trong cửa sổ điều kiện nào**. Đó là cơ sở để quyết định Spring Cloud LoadBalancer có cần thiết cho đường gọi của ứng dụng hay cơ chế Service của Kubernetes đã đáp ứng yêu cầu triển khai.