# Khi nào chỉ cần Kubernetes Service và DNS

## 1. Bắt đầu từ nhu cầu gọi một dịch vụ

Một ứng dụng Spring chạy trong Kubernetes không nhất thiết phải cài Spring Cloud Kubernetes để gọi một ứng dụng khác trong cùng cụm. Với một nhu cầu phổ biến như `checkout` gọi API của `orders`, Kubernetes đã có hai khả năng nền tảng:

- **Service** cung cấp một điểm truy cập ổn định tới nhóm Pod cung cấp cùng một dịch vụ.
- **DNS nội bộ** cho phép ứng dụng dùng tên Service thay vì lưu địa chỉ IP của từng Pod.

Nếu ứng dụng chỉ cần gửi HTTP đến một dịch vụ có tên ổn định, không cần biết từng instance và không cần tự chọn Pod, một URL như `http://orders:8080` thường đã đáp ứng yêu cầu.

Trong module Spring Cloud Kubernetes, cần phân biệt nhu cầu này với các nhu cầu khác: liệt kê instance qua `DiscoveryClient`, chọn instance bằng Spring Cloud LoadBalancer, đọc ConfigMap hoặc Secret qua cơ chế tích hợp, hay nhận thông báo thay đổi cấu hình từ Configuration Watcher. Mỗi khả năng giải quyết một bài toán riêng; việc triển khai lên Kubernetes chưa đủ để kết luận ứng dụng cần tất cả chúng.

Mục tiêu của bài là xác định ranh giới đó, thực hành một đường gọi bằng Service và DNS, rồi nhận diện những tình huống cần bổ sung cơ chế khác.

## 2. Service và DNS làm gì trong đường gọi?

### 2.1. Tên ổn định, Pod có thể thay đổi

Pod thường có vòng đời ngắn. Khi triển khai phiên bản mới, mở rộng số replica hoặc thay thế một Pod lỗi, địa chỉ IP của các Pod có thể đổi. Nếu ghi trực tiếp các địa chỉ này vào cấu hình ứng dụng, bạn phải tự xử lý việc cập nhật và loại bỏ địa chỉ cũ.

Một Service kiểu `ClusterIP` tạo ra điểm truy cập có tên và địa chỉ IP ảo ổn định trong vòng đời của chính đối tượng Service. Với Service có `selector`, Kubernetes theo dõi các Pod khớp nhãn và biểu diễn các endpoint qua EndpointSlice. Đường dữ liệu của cụm dùng thông tin endpoint để chuyển lưu lượng đến backend phù hợp.

Khi Pod thay đổi, tên và ClusterIP của Service vẫn có thể giữ nguyên. Nếu xóa rồi tạo lại Service, không nên giả định ClusterIP cũ được giữ lại; tên DNS là điểm cấu hình thuận tiện hơn cho ứng dụng.

```text
Ứng dụng checkout
    |
    | tra cứu DNS tên orders
    v
DNS nội bộ trả về ClusterIP của Service orders
    |
    | kết nối đến ClusterIP:8080
    v
Đường dữ liệu Service của cụm
    |
    +----> Pod orders A:8080
    +----> Pod orders B:8080
    +----> Pod orders C:8080
```

Đây là sơ đồ logic. Sau khi có kết quả phân giải tên, dữ liệu HTTP không đi xuyên qua máy chủ DNS. Cách triển khai đường dữ liệu có thể khác giữa các cụm; ứng dụng không cần dựa vào một chế độ proxy cụ thể.

### 2.2. DNS và cân bằng tải là hai vai trò khác nhau

Với Service `ClusterIP` thông thường, bản ghi địa chỉ của tên Service trả về ClusterIP, không phải danh sách IP của từng Pod. Việc phân phối lưu lượng tới backend thuộc đường dữ liệu Service của Kubernetes.

Do đó, không nên diễn giải rằng mỗi HTTP request đều được DNS chọn một Pod mới. DNS có thể được cache, còn một kết nối HTTP có thể được tái sử dụng cho nhiều request.

### 2.3. Tên ngắn và tên theo namespace

Giả sử Service tên `orders`, nằm trong namespace `shop` và công bố cổng `8080`:

| Vị trí của client | URL có thể dùng | Ý nghĩa |
| --- | --- | --- |
| Pod trong namespace `shop` | `http://orders:8080` | Tên ngắn được phân giải theo namespace của client |
| Pod trong namespace khác | `http://orders.shop:8080` | Chỉ rõ namespace của Service |
| Cần tên đầy đủ | `http://orders.shop.svc.<cluster-domain>:8080` | Chỉ rõ toàn bộ tên DNS trong cụm |

`<cluster-domain>` là chỗ giữ chỗ, cần thay bằng miền thực tế của cụm. Nhiều cụm dùng `cluster.local`, nhưng không nên coi đây là hằng số của mọi môi trường.

Các ví dụ trên giả định Pod dùng cấu hình DNS phù hợp với Kubernetes, thường là `dnsPolicy: ClusterFirst`, và mạng cho phép client truy cập DNS cùng Service đích. Một máy tính cá nhân hoặc một tiến trình chạy ngoài cụm thường không phân giải và truy cập trực tiếp được các tên này.

## 3. Khi nào Service và DNS đã đủ?

Có thể chọn giải pháp này làm điểm bắt đầu khi các điều kiện chính sau đúng:

1. Dịch vụ đích được công bố bằng Kubernetes Service và client có đường mạng đến nó.
2. Client chỉ cần biết tên dịch vụ, cổng và hợp đồng API.
3. Các replica phía sau Service tương đương về khả năng xử lý request theo hợp đồng đó.
4. Client không cần liệt kê Pod, đọc metadata từng instance hoặc chọn đích theo quy tắc riêng.
5. Cách phân phối kết nối của Service đáp ứng yêu cầu hiện tại của hệ thống.

Ví dụ điển hình là các API HTTP nội bộ không lưu trạng thái phiên trong bộ nhớ của một Pod cụ thể. `checkout` gửi yêu cầu tra cứu đơn hàng đến `orders`; replica nào nhận được cũng có thể xử lý từ cùng nguồn dữ liệu.

Trong tình huống này, ứng dụng có thể dùng một HTTP client thông thường của Spring hoặc Java. Client nhận URL từ cấu hình và gọi `http://orders:8080`. Không cần bật discovery hay thêm `@LoadBalanced` chỉ để tên `orders` hoạt động.

Tên dịch vụ là một phần của hợp đồng vận hành: phía triển khai đảm bảo Service tồn tại, selector đúng và backend sẵn sàng; phía ứng dụng đảm bảo gọi đúng API, xử lý lỗi và giới hạn thời gian chờ.

## 4. Ví dụ thực hành: checkout gọi orders

### 4.1. Giả định của ví dụ

Namespace `shop` đã tồn tại. Ứng dụng `orders` lắng nghe HTTP trên cổng `8080`, có endpoint `GET /orders/{id}` và một endpoint `GET /ready` phục vụ readiness probe. Các image minh họa cần được thay bằng image thực tế có những hành vi này trước khi áp dụng manifest.

Ví dụ dùng HTTP nội bộ để làm rõ đường gọi. Nếu môi trường yêu cầu TLS hoặc xác thực giữa các dịch vụ, cần cấu hình các khả năng đó riêng; DNS và Service không tự cung cấp chúng.

### 4.2. Deployment và Service cho orders

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: shop
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: orders
          image: registry.example.com/orders:1.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      port: 8080
      targetPort: http
```

Các quan hệ cần đọc đúng:

- `Service.spec.selector.app: orders` khớp `Deployment.spec.template.metadata.labels.app: orders`.
- `Service.spec.ports[].port: 8080` là cổng client gọi.
- `targetPort: http` trỏ đến cổng container có tên `http`, ở đây là `8080`.
- `containerPort` mô tả cổng của container; nó không tự làm ứng dụng lắng nghe và không tự công bố một Service.
- `readinessProbe` kiểm tra backend có sẵn sàng nhận lưu lượng hay chưa. Endpoint `/ready` trong ví dụ là giả định của ứng dụng, không phải endpoint mặc định mà mọi ứng dụng Spring đều có.

Trong cấu hình Service thông thường, Pod chưa sẵn sàng không được chọn làm backend sẵn sàng để phục vụ lưu lượng thông thường. Không bật `publishNotReadyAddresses` cho một API thông thường nếu chưa hiểu rõ lý do và hệ quả của lựa chọn đó.

### 4.3. Truyền URL vào checkout

Trong Pod template của Deployment `checkout`, có thể khai báo:

```yaml
spec:
  template:
    spec:
      containers:
        - name: checkout
          image: registry.example.com/checkout:1.0.0
          env:
            - name: ORDERS_BASE_URL
              value: "http://orders:8080"
```

Đây là phần trích của Deployment `checkout`, không phải một manifest độc lập. Pod này cũng nằm trong namespace `shop`. Nếu chuyển client sang namespace khác, có thể dùng `http://orders.shop:8080` hoặc tên DNS đầy đủ theo cấu hình cụm.

Khai báo thuộc tính trong cấu hình Spring:

```yaml
orders:
  base-url: ${ORDERS_BASE_URL:http://localhost:8081}
```

Cấu hình này dùng URL từ biến môi trường khi chạy trong cụm và dùng địa chỉ local khi phát triển. Nhờ vậy, mã nghiệp vụ không chứa địa chỉ IP của Pod hay tên namespace cố định.

### 4.4. Gọi bằng HTTP client thông thường

Ví dụ Java sau giả định dự án Spring đang dùng hỗ trợ `RestClient` và đã cung cấp bean `RestClient.Builder`, như trong một ứng dụng Spring Boot có auto-configuration phù hợp:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersClientConfiguration {

    @Bean
    RestClient ordersRestClient(
            RestClient.Builder builder,
            @Value("${orders.base-url}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }
}
```

Một lớp sử dụng client:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class OrdersGateway {

    private final RestClient client;

    public OrdersGateway(
            @Qualifier("ordersRestClient") RestClient client) {
        this.client = client;
    }

    public String findOrder(String orderId) {
        return client.get()
                .uri("/orders/{id}", orderId)
                .retrieve()
                .body(String.class);
    }
}
```

Ở đây không gắn `@LoadBalanced` lên builder. `orders` là tên máy chủ trong URL và được phân giải bởi cơ chế DNS mà tiến trình Java sử dụng trong Pod. Nó không cần được chuyển thành một service ID để hỏi `DiscoveryClient`.

Ví dụ trả về chuỗi để tập trung vào cơ chế định địa chỉ. Khi áp dụng vào nghiệp vụ, cần ánh xạ DTO, xử lý mã trạng thái và đặt timeout trên HTTP client thực tế mà dự án sử dụng. Các đoạn mã này chưa thể hiện cấu hình timeout, retry hay xác thực.

Có thể thay `RestClient` bằng `WebClient` hoặc một HTTP client phù hợp khác. Quyết định dùng Service và DNS không buộc ứng dụng sử dụng một thư viện HTTP duy nhất.

## 5. Readiness, kết nối và phân phối lưu lượng

### 5.1. Readiness giúp chọn backend; DNS không kiểm tra sức khỏe API

Tên `orders` vẫn có thể phân giải ra ClusterIP dù hiện tại Service không có backend sẵn sàng. Phân giải thành công vì thế không đồng nghĩa API đang hoạt động.

Readiness cần phản ánh khả năng phục vụ request của chính ứng dụng. Một HTTP server đã mở cổng nhưng chưa khởi tạo xong dữ liệu có thể chưa sẵn sàng. Ngược lại, probe phụ thuộc quá sâu vào mọi dịch vụ bên ngoài có thể khiến cả nhóm Pod bị loại cùng lúc khi một dependency gặp sự cố.

Liveness có vai trò khác: giúp phát hiện tình trạng cần khởi động lại container. Không dùng liveness như một tên gọi thay thế cho readiness.

Khi readiness thay đổi, việc cập nhật endpoint và đường dữ liệu có độ trễ. Các kết nối đang tồn tại cũng cần được xem xét. Cần kết hợp readiness với cơ chế tắt ứng dụng có kiểm soát, thời gian chờ kết thúc Pod và hành vi của HTTP client; không giả định mọi request đang chạy đều được bảo vệ chỉ nhờ có probe.

### 5.2. Nhiều replica không bảo đảm chia đều từng request

Với TCP, đường dữ liệu Service thường chọn backend khi hình thành luồng hoặc kết nối. HTTP keep-alive có thể gửi nhiều request trên cùng một kết nối. HTTP/2 và gRPC còn có thể ghép nhiều luồng ứng dụng trên một kết nối TCP lâu dài.

Ví dụ, một client chỉ duy trì một kết nối đến Service có ba replica. Nhiều request liên tiếp có thể cùng đến một Pod; tăng thêm replica không bắt buộc làm kết nối đang có chuyển sang Pod mới.

Nếu quan sát thấy phân phối lệch, cần kiểm tra số lượng kết nối, connection pool, giao thức và tuổi thọ kết nối trước khi kết luận DNS hoặc Service bị lỗi. Với gRPC có tải cao, có thể cần một cơ chế cân bằng tải hiểu giao thức hoặc cơ chế chọn backend của client gRPC. Spring Cloud LoadBalancer cho HTTP không tự động giải quyết mọi đường gọi gRPC.

### 5.3. Service không thay thế xử lý lỗi phía client

Ứng dụng vẫn cần những chính sách thích hợp:

- Giới hạn thời gian thiết lập kết nối và thời gian chờ phản hồi.
- Giới hạn tổng thời gian cho một thao tác nghiệp vụ.
- Xử lý lỗi có ý nghĩa với người gọi, thay vì chờ vô hạn.
- Retry có giới hạn khi thao tác và loại lỗi cho phép.
- Quan sát độ trễ, lỗi và số lượng kết nối để phát hiện vấn đề vận hành.

Với thao tác tạo đơn hàng, request có thể đã được xử lý dù client không nhận được phản hồi. Retry mù có thể tạo dữ liệu trùng; cần thiết kế idempotency hoặc cơ chế chống trùng phù hợp trước khi tự động thử lại.

Service và DNS cung cấp đường định địa chỉ và chuyển lưu lượng. Chúng không xác định hộ ứng dụng rằng một thao tác nghiệp vụ đã thành công hay có thể thực hiện lại an toàn.

## 6. Phân biệt với DiscoveryClient và Spring Cloud LoadBalancer

| Nhu cầu | Service và DNS thông thường | Khả năng cần cân nhắc thêm |
| --- | --- | --- |
| Gọi một API nội bộ qua tên ổn định | Thường đủ | HTTP client có timeout và xử lý lỗi |
| Pod đổi IP hoặc tăng giảm replica | Service cập nhật tập endpoint | Readiness và vận hành triển khai đúng |
| Gọi Service ở namespace khác | Dùng tên có namespace nếu mạng cho phép | NetworkPolicy, quy ước namespace |
| Liệt kê từng instance cùng metadata | Không cung cấp qua một URL ClusterIP | `DiscoveryClient` hoặc cơ chế discovery phù hợp |
| Chọn instance theo quy tắc của client | Không cho client trực tiếp điều khiển qua URL Service | Spring Cloud LoadBalancer với nguồn instance thích hợp |
| Cần định tuyến theo HTTP header, người dùng hoặc trọng số nghiệp vụ | Service lớp vận chuyển không tự hiểu các quy tắc này | Gateway, mesh, proxy hoặc logic ứng dụng theo yêu cầu |
| Theo dõi thay đổi cấu hình | DNS không giải quyết | Cơ chế cập nhật cấu hình và, khi phù hợp, Configuration Watcher |

`DiscoveryClient` hữu ích khi mã ứng dụng thật sự cần mô hình dịch vụ và instance. Nó không phải điều kiện để tên DNS của Kubernetes hoạt động.

Spring Cloud LoadBalancer hữu ích khi ứng dụng cần chọn một instance từ danh sách mà nó nhận được. Muốn đánh giá hiệu quả, cần biết danh sách đó chứa **địa chỉ Pod** hay chỉ chứa **địa chỉ Service**. Nếu client chọn một địa chỉ Service rồi Kubernetes tiếp tục chọn Pod phía sau, quy tắc chọn ở client không mặc nhiên kiểm soát được Pod cuối cùng.

Vì vậy, trước khi thêm một tầng chọn đích, hãy chỉ ra quyết định cụ thể mà tầng đó phải thực hiện: chọn instance theo metadata nào, loại instance theo tín hiệu gì, hay giải quyết yêu cầu nào mà đường gọi qua Service chưa đáp ứng. Nếu chưa có quyết định đó, URL DNS thường dễ cấu hình và vận hành hơn.

## 7. Headless Service không giống ClusterIP thông thường

Một Service khai báo `clusterIP: None` là headless Service. Với headless Service có selector và backend tương ứng, DNS có thể công bố địa chỉ endpoint trực tiếp thay vì trả về một ClusterIP chung. Đây là một mô hình khác với ví dụ phía trên.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-headless
  namespace: shop
spec:
  clusterIP: None
  selector:
    app: orders
  ports:
    - name: http
      port: 8080
      targetPort: http
```

Headless Service có ích khi một hệ thống cần tìm hoặc định danh các thành viên riêng lẻ. Tuy nhiên, nó không tự biến mọi HTTP client thành bộ cân bằng tải theo từng request. Việc client sử dụng địa chỉ nào, cache DNS bao lâu và giữ kết nối thế nào còn phụ thuộc thư viện và cấu hình của client.

Nếu nhu cầu chỉ là gọi một API với các replica tương đương, `ClusterIP` thường là điểm bắt đầu phù hợp hơn. Chọn headless khi mô hình hệ thống cần thấy endpoint trực tiếp và đã có cách xử lý tập endpoint đó.

## 8. RBAC và mạng: gọi Service không đồng nghĩa đọc Kubernetes API

Với đường gọi thông thường `checkout -> DNS -> orders Service`, ứng dụng `checkout` không phải gọi Kubernetes API để liệt kê Pod hay Service. Vì vậy, không cần cấp quyền `list` hoặc `watch` các tài nguyên đó chỉ để gửi HTTP đến tên `orders`.

Cần tách hai lớp quyền:

| Lớp | Kiểm soát điều gì? | Ví dụ |
| --- | --- | --- |
| Kubernetes RBAC | Truy cập tài nguyên qua Kubernetes API | Quyền đọc Service, EndpointSlice hoặc Secret |
| Chính sách và bảo mật đường gọi | Lưu lượng mạng và quyền sử dụng API ứng dụng | NetworkPolicy, TLS, token ứng dụng |

Một Pod có thể không được phép liệt kê Service qua Kubernetes API nhưng vẫn gọi được một Service nếu mạng và API đích cho phép. Ngược lại, quyền đọc Service không bảo đảm kết nối mạng đến backend sẽ thành công.

Nếu dùng NetworkPolicy được thực thi bởi giải pháp mạng của cụm, cần cho phép lưu lượng cần thiết, gồm cả tra cứu DNS và kết nối đến workload đích. Việc xác định rule cụ thể cần dựa trên namespace, nhãn Pod và cách cụm triển khai DNS.

Khi bật một cơ chế discovery hoặc watcher dựa trên Kubernetes API, hãy xác định đúng tài nguyên, namespace và động từ mà cơ chế đó cần. Không cấp quyền quản trị cụm chỉ để khắc phục một lỗi gọi HTTP chưa được chẩn đoán.

## 9. ConfigMap, Secret và Configuration Watcher là quyết định riêng

Việc chỉ dùng Service và DNS cho đường gọi không ngăn ứng dụng dùng ConfigMap hoặc Secret. Kubernetes có thể đưa dữ liệu cấu hình vào Pod qua biến môi trường hoặc volume mà mã ứng dụng không trực tiếp gọi Kubernetes API.

Tuy nhiên, cần phân biệt các mốc:

1. Đối tượng ConfigMap hoặc Secret được thay đổi trong Kubernetes.
2. Dữ liệu mới được đưa tới môi trường chạy theo cách đã chọn.
3. Ứng dụng đọc lại dữ liệu và áp dụng hành vi mới.

Ba mốc này không tự đồng thời xảy ra. Biến môi trường của một tiến trình đang chạy không tự đổi khi ConfigMap thay đổi. File mount có thể được cập nhật theo cơ chế của Kubernetes, nhưng ứng dụng vẫn cần cách đọc lại; mount bằng `subPath` cũng không có hành vi cập nhật tự động giống volume ConfigMap thông thường.

Configuration Watcher phục vụ bài toán phát hiện và thông báo thay đổi cấu hình trong một kiến trúc được thiết lập phù hợp. Nó không phải thành phần bắt buộc của việc gọi `http://orders:8080`, và chỉ có watcher cũng chưa đủ để kết luận mọi bean hoặc cấu hình trong ứng dụng đều được nạp lại.

Câu hỏi lựa chọn nên là: ứng dụng có cần cấu hình thay đổi khi đang chạy, hay một lần triển khai lại có kiểm soát đã đáp ứng? Quyết định này độc lập với việc có cần liệt kê instance hay không.

## 10. Kiểm tra đường gọi theo từng lớp

Các lệnh dưới đây là ví dụ để người học thực hành trong môi trường có quyền phù hợp. Chúng không phải kết quả đã được chạy cho bài viết. Thay `<checkout-pod>` bằng tên Pod thực tế; shell trong container phải có các công cụ được sử dụng.

### 10.1. Kiểm tra đúng đối tượng và endpoint

```bash
kubectl -n shop get service orders
kubectl -n shop get pods -l app=orders -o wide
kubectl -n shop get endpointslices -l kubernetes.io/service-name=orders
```

Đọc kết quả theo quan hệ:

- Service có tên, cổng và selector như mong đợi không?
- Nhãn Pod có khớp selector không?
- Có Pod sẵn sàng không?
- EndpointSlice có địa chỉ, cổng và trạng thái readiness phù hợp không?

Nếu cần xem chi tiết để chẩn đoán:

```bash
kubectl -n shop describe service orders
kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=orders -o yaml
```

Các lệnh `kubectl` là thao tác của người vận hành có quyền đọc tài nguyên. Quyền đó không phải yêu cầu RBAC bổ sung cho HTTP client bên trong ứng dụng.

### 10.2. Kiểm tra DNS từ vị trí của client

Nếu container có `nslookup`:

```bash
kubectl -n shop exec <checkout-pod> -- nslookup orders
```

Kiểm tra từ chính môi trường của client giúp phát hiện sai namespace hoặc cấu hình DNS. Không dùng kết quả tra cứu trên laptop để kết luận DNS bên trong Pod bị lỗi.

Nếu image ứng dụng tối giản không có công cụ chẩn đoán, có thể dùng công cụ debug phù hợp với chính sách cụm. Không cần thêm các công cụ đó vào image sản xuất chỉ để hoàn thành bài thực hành.

### 10.3. Kiểm tra HTTP từ client

Nếu container có `curl`:

```bash
kubectl -n shop exec <checkout-pod> -- \
  curl --connect-timeout 2 --max-time 5 \
  http://orders:8080/orders/123
```

Ví dụ giả định API cho phép request này trong môi trường thực hành và đơn hàng `123` tồn tại nếu mong đợi phản hồi thành công. Một phản hồi HTTP `404` do không có đơn hàng có ý nghĩa khác hoàn toàn với lỗi không phân giải được tên.

| Hiện tượng | Hướng kiểm tra đầu tiên |
| --- | --- |
| Không phân giải được tên | Tên Service, namespace, DNS của Pod, đường truy cập DNS |
| Có DNS nhưng kết nối timeout | NetworkPolicy, đường mạng, endpoint và trạng thái backend |
| Kết nối bị từ chối | Cổng Service/targetPort, ứng dụng có lắng nghe, backend thực tế |
| Trả về HTTP `404` | Đường dẫn API, dữ liệu yêu cầu, ứng dụng thực sự nhận request |
| Trả về HTTP `401` hoặc `403` | Cơ chế xác thực và phân quyền của API hoặc proxy |
| Request phân bố lệch giữa các Pod | Connection pool, keep-alive, HTTP/2, lượng client và số kết nối |

Bảng này gợi ý điểm bắt đầu, không khẳng định mỗi hiện tượng chỉ có một nguyên nhân. Đặc biệt, cùng một lỗi endpoint có thể biểu hiện khác nhau tùy đường dữ liệu của cụm.

## 11. Những ngộ nhận thường gặp

### “Chạy Spring trong Kubernetes thì phải có DiscoveryClient”

Không. Nếu ứng dụng chỉ cần URL của một Service, DNS nội bộ đã cung cấp cách định địa chỉ. Chỉ thêm discovery khi cần khả năng liên quan đến dịch vụ hoặc instance mà đường gọi đó chưa đáp ứng.

### “Gọi được DNS nghĩa là Service khỏe”

Không. DNS của Service `ClusterIP` và khả năng phục vụ của backend là hai lớp khác nhau. Cần kiểm tra readiness, endpoint và phản hồi HTTP.

### “Ba replica sẽ nhận đúng một phần ba số request”

Không có bảo đảm như vậy. Kết nối lâu dài, số lượng client ít và đặc tính giao thức đều có thể tạo phân phối lệch. Cần đo hành vi thực tế theo loại tải.

### “Không dùng Spring Cloud Kubernetes thì không dùng được ConfigMap hoặc Secret”

Không. Kubernetes có cơ chế cấp dữ liệu vào Pod. Cơ chế đọc, cập nhật và áp dụng cấu hình của ứng dụng mới là phần cần thiết kế thêm.

### “Service là một ranh giới bảo mật hoặc URL công khai”

Service `ClusterIP` chủ yếu phục vụ truy cập nội bộ theo thiết kế mạng của cụm. Nó không tự tạo một địa chỉ Internet công khai và không tự xác thực người gọi. Công bố dịch vụ ra ngoài là một bài toán riêng, có thể cần Ingress, Gateway hoặc Service kiểu phù hợp.

## 12. Bài tập tự kiểm chứng

Với môi trường thực hành của ví dụ, thực hiện lần lượt:

1. Cho `checkout` gọi `orders` bằng `http://orders:8080` trong namespace `shop`.
2. Đổi số replica của `orders` từ ba lên bốn; giữ nguyên URL phía client.
3. Thay thế một Pod `orders` và quan sát địa chỉ endpoint thay đổi trong khi tên Service giữ nguyên.
4. Làm một Pod chưa sẵn sàng và quan sát readiness trong EndpointSlice cùng hành vi đường gọi. Không suy luận rằng mọi kết nối cũ sẽ chuyển đích ngay lập tức.
5. Chuyển client sang namespace khác, sửa URL thành tên có namespace và kiểm tra lại chính sách mạng.
6. So sánh lỗi DNS, lỗi kết nối và phản hồi HTTP lỗi; xác định mỗi loại thuộc lớp nào.

Kết quả cần giải thích được là vì sao client không phải cập nhật danh sách IP của Pod, đồng thời vẫn cần timeout và xử lý lỗi dù đã có Service.

## 13. Ra quyết định cho một ứng dụng Spring

Có thể dùng chuỗi câu hỏi sau khi thiết kế đường gọi:

1. **Chỉ cần một địa chỉ ổn định cho API?** Bắt đầu với Service `ClusterIP`, DNS và HTTP client thông thường.
2. **Ứng dụng cần biết từng instance?** Xác định metadata và thao tác cụ thể rồi đánh giá discovery phù hợp.
3. **Ứng dụng cần trực tiếp chọn instance?** Kiểm tra nguồn instance, giao thức và chính sách chọn trước khi bổ sung cân bằng tải phía client.
4. **Cần định tuyến ở lớp HTTP hoặc gRPC?** Đánh giá thành phần hiểu giao thức và yêu cầu vận hành tương ứng.
5. **Cần cập nhật cấu hình khi ứng dụng đang chạy?** Thiết kế đường cập nhật riêng cho ConfigMap, Secret và cơ chế nạp lại; cân nhắc watcher nếu cần.

Với phần lớn đường gọi API nội bộ đơn giản, Service và DNS đã giải quyết việc tìm một điểm truy cập ổn định khi Pod thay đổi. Giá trị của Spring Cloud Kubernetes xuất hiện khi có nhu cầu tích hợp cụ thể vượt ra ngoài đường gọi đó. Lựa chọn tính năng theo nhu cầu giúp giữ mã ứng dụng, quyền RBAC và số thành phần vận hành ở mức có thể giải thích và kiểm chứng được.