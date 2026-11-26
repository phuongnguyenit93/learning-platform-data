# Kiểm tra điều kiện tự cấu hình và các bean được tạo

## 1. Vì sao cần kiểm tra auto-configuration?

Spring Boot có thể tạo nhiều bean từ dependency và property mà mã ứng dụng không gọi trực tiếp. Với Spring Cloud Kubernetes, một starter có thể kích hoạt discovery, nguồn cấu hình, client Kubernetes, Spring Cloud LoadBalancer hoặc cơ chế refresh. Nếu chỉ nhìn vào `pom.xml` hay `build.gradle`, ta chưa biết:

- Auto-configuration nào đã được nạp?
- Điều kiện nào làm configuration được bật hoặc bỏ qua?
- Bean DiscoveryClient đang đến từ implementation nào?
- Ứng dụng đang dùng Fabric8 hay Kubernetes Java Client?
- ConfigMap và Secret được đọc qua API hay qua file mount?
- LoadBalancer có nguồn ServiceInstance hay chưa?
- Bean nào bị thay thế bởi bean tự định nghĩa?
- Vì sao một bean mong đợi không tồn tại hoặc có nhiều candidate?

Kiểm tra tự cấu hình giúp biến quá trình khởi động từ “đoán dependency” thành bằng chứng quan sát được.

Luồng khái quát:

```text
Starter trên classpath
    -> auto-configuration được phát hiện
    -> điều kiện class/property/bean/resource được đánh giá
    -> bean được tạo hoặc bị bỏ qua
    -> ứng dụng sử dụng discovery/config/load balancer
```

Điều kiện đạt không có nghĩa chức năng nghiệp vụ đã hoạt động. Bean có thể được tạo nhưng gọi API bị `403`, discovery có thể khởi động nhưng danh sách instance rỗng, hoặc ConfigMap có thể được đọc nhưng bean không refresh. Cần kiểm tra từng lớp.

Bài học này thuộc phần **Thiết lập dự án** của module **Spring Cloud Kubernetes**. Mục tiêu là biết cách xác nhận starter và auto-configuration trước khi điều tra sâu hơn về RBAC, namespace, API server hoặc dữ liệu Kubernetes.

## 2. Auto-configuration hoạt động theo điều kiện

Một auto-configuration thường chỉ tạo bean khi các điều kiện phù hợp. Những loại điều kiện hay gặp:

| Loại điều kiện | Câu hỏi được kiểm tra |
|---|---|
| Classpath | Class hoặc dependency cần thiết có tồn tại không? |
| Bean | Đã có bean cùng vai trò chưa? Có cho phép tạo bean mặc định không? |
| Property | Property bật, tắt hoặc chọn implementation nào? |
| Resource | File, classpath resource hoặc metadata có tồn tại không? |
| Web application | Ứng dụng có loại context phù hợp không? |
| Missing bean | Có thể tạo bean thay thế vì người dùng chưa tự định nghĩa không? |

Ví dụ khái quát:

```text
Có discovery starter?
    |
    +-- Không -> không tạo DiscoveryClient của integration
    |
    '-- Có
         |
         +-- Có class client phù hợp? -> tiếp tục
         +-- Discovery được bật? -> tiếp tục
         +-- Chưa có DiscoveryClient khác? -> tạo bean
         '-- Không đạt -> auto-configuration bị bỏ qua
```

Điều kiện có thể phụ thuộc lẫn nhau. Một starter discovery có thể thấy class Kubernetes client nhưng vẫn không tạo bean vì property tắt discovery, context không phù hợp hoặc một bean khác đã chiếm cùng vai trò.

Khi điều tra, phải phân biệt:

- **Matched:** điều kiện đạt, configuration hoặc bean có thể được áp dụng.
- **Did not match:** điều kiện không đạt, nên bean không được tạo theo nhánh đó.
- **Unconditional:** configuration không phụ thuộc vào một điều kiện cụ thể trong report.
- **Excluded:** auto-configuration bị loại khỏi danh sách hoặc bị người dùng loại trừ.

## 3. Bật thông tin chẩn đoán khi khởi động

Spring Boot có thể in thông tin điều kiện khi bật debug:

```properties
debug=true
```

Hoặc chạy ứng dụng với tham số:

```text
java -jar app.jar --debug
```

Log debug thường chứa Condition Evaluation Report. Tên format và mức chi tiết có thể khác giữa các phiên bản, nhưng mục tiêu đọc vẫn giống nhau: tìm configuration liên quan, xem điều kiện nào khớp và lý do nhánh khác bị bỏ qua.

Không nên bật debug vĩnh viễn trong production chỉ để theo dõi một lần kiểm tra. Log khởi động có thể dài và có thể chứa tên class, property hoặc thông tin môi trường không cần công khai. Dùng profile hoặc môi trường kiểm thử phù hợp, rồi tắt sau khi thu thập bằng chứng.

Khi xem report, tìm theo các từ khóa capability thay vì chỉ tìm tên module:

```text
Discovery
Kubernetes
Config
LoadBalancer
Client
Watcher
Refresh
Actuator
```

Report cho biết quyết định auto-configuration, nhưng không thay thế log lỗi kết nối hoặc kiểm tra RBAC.

## 4. Condition Evaluation Report: đọc từ ngoài vào trong

Một quy trình đọc report:

1. Xác định capability đang kiểm tra: discovery, config hay load balancing.
2. Tìm tên auto-configuration liên quan.
3. Xem nhánh matched để biết điều kiện đã đạt.
4. Xem nhánh did not match nếu bean không xuất hiện.
5. Đọc lý do cụ thể: thiếu class, property không đúng, bean đã tồn tại hay context không phù hợp.
6. Đối chiếu với dependency và property thực tế.
7. Kiểm tra bean cuối cùng trong ApplicationContext.

Ví dụ suy luận:

| Quan sát | Diễn giải có thể có |
|---|---|
| Discovery auto-configuration không xuất hiện | Starter chưa có, tên module sai hoặc không thuộc release train |
| Configuration xuất hiện nhưng không match | Property bật/tắt, class client hoặc điều kiện context chưa phù hợp |
| Auto-configuration match nhưng gọi API lỗi | Bean đã tạo; vấn đề có thể là URL, TLS, token, RBAC hoặc mạng |
| Bean bị bỏ qua vì missing bean condition không đạt | Ứng dụng hoặc thư viện khác đã cung cấp bean cùng vai trò |
| Có nhiều bean cùng type | Nhiều implementation hoặc cấu hình thủ công gây ambiguity |
| LoadBalancer có bean nhưng không có instance | Nguồn DiscoveryClient, service ID hoặc dữ liệu endpoint có vấn đề |

Không kết luận “starter hỏng” chỉ vì một nhánh không match. Auto-configuration thường có nhiều nhánh thay thế; cần đọc đúng configuration và điều kiện liên quan.

## 5. Actuator hỗ trợ quan sát runtime

### 5.1. Điều kiện tự cấu hình

Actuator có thể cung cấp endpoint `conditions` để xem Condition Evaluation Report trong lúc chạy nếu endpoint này được expose:

```properties
management.endpoints.web.exposure.include=health,info,conditions,beans
```

URL thường có dạng:

```text
/actuator/conditions
/actuator/beans
```

Đường dẫn context, port quản trị và base path có thể thay đổi. Không expose endpoint chẩn đoán rộng ra mạng công khai. Cần bảo vệ bằng network policy, authentication và giới hạn exposure.

Một số phiên bản Spring Boot có thể hiển thị cấu trúc report khác nhau. Điều cần lấy là tên configuration, outcome và message của condition, không nên phụ thuộc vào một vị trí JSON cố định.

### 5.2. Danh sách bean

Endpoint `beans` cho biết bean trong ApplicationContext, scope, type, resource và quan hệ một số dependency. Khi điều tra Spring Cloud Kubernetes, tìm các bean liên quan tới:

- `DiscoveryClient`
- `ReactiveDiscoveryClient` nếu ứng dụng reactive
- `ServiceInstanceListSupplier`
- `LoadBalancerClient` hoặc thành phần load balancer tương ứng
- `EnvironmentRepository`, property source hoặc config data integration
- Kubernetes client hoặc adapter của client
- Health indicator
- Application event listener cho refresh hoặc watcher

Tên bean cụ thể có thể khác theo phiên bản. Type và implementation thường có giá trị hơn việc đoán một tên bean cố định.

Ví dụ một phần quan hệ khái quát:

```text
DiscoveryClient implementation
    -> Kubernetes client adapter
    -> API server / cache
    -> ServiceInstance

LoadBalancer
    -> ServiceInstanceListSupplier
    -> DiscoveryClient
    -> HTTP client
```

Bean tồn tại chỉ chứng minh context đã tạo object. Cần kiểm tra hành vi bằng một lời gọi an toàn, health signal hoặc log phù hợp.

### 5.3. Health và readiness

Actuator health giúp tách trạng thái ứng dụng khỏi trạng thái auto-configuration:

```properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info,conditions,beans
```

Có thể cấu hình các group startup, liveness và readiness tùy cách ứng dụng chạy trên Kubernetes. Không đưa mọi lỗi API server vào liveness nếu điều đó làm Pod khởi động lại liên tục. Discovery hoặc Config integration có thể cần API trong lúc khởi động, nhưng chính sách khi API tạm thời không sẵn sàng phải được quyết định riêng.

## 6. Kiểm tra bean bằng mã ứng dụng

Có thể in các bean phù hợp trong môi trường local hoặc kiểm thử:

```java
@Component
class SpringCloudKubernetesBeanReport implements ApplicationRunner {

    private final ApplicationContext context;

    SpringCloudKubernetesBeanReport(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] names = context.getBeanNamesForType(
                org.springframework.cloud.client.discovery.DiscoveryClient.class);

        for (String name : names) {
            Object bean = context.getBean(name);
            System.out.printf("%s -> %s%n",
                    name, bean.getClass().getName());
        }
    }
}
```

Đoạn mã này chỉ nên dùng cho môi trường chẩn đoán hoặc test. Không log toàn bộ ApplicationContext trong production vì output lớn, có thể lộ implementation và làm nhiễu log. Với ứng dụng reactive, kiểm tra thêm loại DiscoveryClient tương ứng nếu capability sử dụng reactive path.

Có thể kiểm tra một bean bắt buộc bằng điều kiện rõ ràng:

```java
@Component
class DiscoveryStartupCheck implements ApplicationRunner {

    private final ApplicationContext context;

    DiscoveryStartupCheck(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        boolean present = context.getBeansOfType(
                org.springframework.cloud.client.discovery.DiscoveryClient.class)
                .values()
                .stream()
                .anyMatch(bean -> bean.getClass().getName()
                        .toLowerCase()
                        .contains("kubernetes"));

        if (!present) {
            throw new IllegalStateException(
                    "Expected a Kubernetes-backed DiscoveryClient");
        }
    }
}
```

Đây là kiểm tra phù hợp khi ứng dụng thực sự bắt buộc discovery Kubernetes. Nếu discovery chỉ là capability tùy chọn, không nên làm toàn bộ ứng dụng fail startup chỉ vì bean đó vắng mặt.

## 7. Kiểm tra client đang được dùng

Auto-configuration có thể tạo adapter quanh một Kubernetes client. Khi cần xác định implementation:

1. Xem class của bean adapter hoặc client trong `beans`.
2. Đọc dependency graph của build để tìm artifact Fabric8 hoặc Kubernetes Java Client.
3. Kiểm tra log khởi động của integration.
4. Đối chiếu tên starter với release train.
5. Xem property được dùng để chọn hoặc cấu hình client.
6. Tách test cho startup, API call, watch và lỗi quyền.

Có thể đặt một kiểm tra dependency ở mức dự án:

```text
Kỳ vọng: một họ client chính
    |
    +-- Fabric8 artifacts xuất hiện theo starter đã chọn
    '-- Kubernetes Java Client xuất hiện theo starter đã chọn

Cảnh báo:
    cả hai họ cùng xuất hiện vì dependency transitively
    -> kiểm tra auto-configuration và bean candidate
```

Việc cả hai thư viện có mặt không nhất thiết luôn là lỗi. Một dependency khác có thể cần chúng cho mục đích riêng. Rủi ro nằm ở việc không biết integration Spring đang dùng client nào hoặc có hai bean cùng vai trò.

Không viết code dựa vào API Fabric8 rồi đổi sang Kubernetes Java Client chỉ bằng một dòng dependency. Hai client có model, lifecycle, exception và cơ chế watch khác nhau. Nếu application chỉ dùng abstraction Spring, đổi client có thể ít sửa mã hơn nhưng vẫn phải kiểm tra hành vi runtime.

## 8. Kiểm tra theo từng capability

### 8.1. Discovery

Câu hỏi và bằng chứng cần thu thập:

- Có bean DiscoveryClient phù hợp không?
- Condition report nói starter và client class đã match chưa?
- Service ID được gọi có đúng tên và namespace không?
- Có ServiceInstance nào được trả về không?
- Endpoint ready có được lọc đúng không?
- Lỗi API là `401`, `403`, timeout hay dữ liệu rỗng?
- Cache hoặc watch đã đồng bộ chưa?

Một bean DiscoveryClient tồn tại nhưng trả danh sách rỗng có thể do selector, namespace, Service không có endpoint, filter hoặc RBAC. Đừng dừng ở bước `beans`.

### 8.2. ConfigMap và Secret

Kiểm tra:

- Property source hoặc config data location có xuất hiện trong Environment không?
- Condition report có nói integration config đã match không?
- ConfigMap/Secret được đọc qua API hay file mount?
- ServiceAccount có quyền trên tài nguyên và namespace không?
- Property nào đã được nạp, nhưng không log giá trị Secret?
- Bean sử dụng property có hỗ trợ refresh không?

Có thể kiểm tra tên property hoặc nguồn, nhưng không in toàn bộ Environment vì Secret có thể đã được resolve thành giá trị nhạy cảm. Hãy che giá trị hoặc chỉ log boolean “đã có property”.

### 8.3. LoadBalancer

Kiểm tra:

- Có LoadBalancer bean hoặc ServiceInstanceListSupplier không?
- Nguồn instance có liên kết với DiscoveryClient không?
- Service ID trong URL hoặc annotation có đúng không?
- LoadBalancer chọn ClusterIP hay instance address?
- HTTP client có được tích hợp với load balancer không?
- Retry, timeout và connection pool có tạo hành vi ngoài ý muốn không?

LoadBalancer bean có thể được tạo dù discovery backend không có dữ liệu. Vì vậy cần một test gọi service ID bằng endpoint an toàn hoặc kiểm tra supplier trả danh sách phù hợp.

### 8.4. Configuration Watcher

Kiểm tra:

- Watcher có phải workload riêng hay bean trong ứng dụng?
- ServiceAccount của watcher có quyền `watch` nguồn cấu hình không?
- Ứng dụng có endpoint hoặc listener nhận thông báo không?
- Bean được refresh có thực sự đọc giá trị mới không?
- Khi thông báo thất bại, cơ chế retry hoặc hội tụ lại là gì?
- Readiness/liveness có phản ứng sai với lỗi watcher không?

Đừng đánh đồng “watcher bean tồn tại” với “cấu hình động đã hoạt động”. Cần kiểm tra một thay đổi thử nghiệm không nhạy cảm từ nguồn đến hành vi.

## 9. Tạo bảng kiểm tra startup có chủ đích

Một bảng kiểm tra giúp tránh sửa nhiều thứ cùng lúc:

| Bước | Bằng chứng | Kết luận |
|---|---|---|
| Dependency | Starter và BOM đúng dòng | Có nền tảng phiên bản phù hợp |
| Condition report | Auto-configuration match | Biết vì sao configuration được áp dụng |
| Beans | Bean type/implementation | Biết context đã tạo gì |
| Properties | Property source và flag | Biết tính năng được bật bằng cấu hình nào |
| Connectivity | Log/API timeout/TLS | Biết có tới được API server không |
| RBAC | Quyền ServiceAccount | Biết request có được phép không |
| Data | Service, endpoint, ConfigMap hoặc Secret | Biết backend có dữ liệu hợp lệ không |
| Behavior | Gọi an toàn/refresh thử nghiệm | Biết chức năng thật sự hoạt động không |

Mỗi bước trả lời một câu hỏi khác nhau. Không dùng kết quả bước trước để kết luận thay cho bước sau.

## 10. Những lỗi chẩn đoán thường gặp

### “Có dependency là chắc chắn có bean”

Auto-configuration còn phụ thuộc classpath, property, bean khác, resource và context. Hãy đọc condition report và danh sách bean.

### “Bean có nghĩa API đã dùng được”

Bean có thể chưa thực hiện request nào. Token, TLS, URL, RBAC, namespace và dữ liệu tài nguyên vẫn cần kiểm tra.

### “Không có bean nghĩa là starter không tải”

Bean có thể bị thay thế bởi bean tự định nghĩa, bị tắt bởi property hoặc bị loại bởi điều kiện. Tìm nhánh did not match trước khi đổi dependency.

### “Bật debug là đủ để điều tra production”

Debug tạo nhiều log và có thể lộ cấu trúc ứng dụng. Dùng có kiểm soát, Actuator bảo vệ, metric và log chọn lọc.

### “Endpoint beans có thể mở công khai”

`/actuator/beans` và `/actuator/conditions` tiết lộ nhiều thông tin nội bộ. Chỉ expose trong phạm vi quản trị được xác thực.

### “Có LoadBalancer là tự có discovery”

LoadBalancer cần nguồn ServiceInstance. DiscoveryClient hoặc supplier phải cung cấp dữ liệu phù hợp.

### “Refresh event thành công nghĩa mọi bean đã đổi”

Event chỉ là một bước trong chuỗi. Bean, cache, connection pool hoặc client có thể không hỗ trợ cập nhật trực tiếp.

## 11. Quy trình thực hành đề xuất

Giả sử tạo `order-service` với discovery và ConfigMap:

1. Chốt release train, BOM và một họ Kubernetes client.
2. Chỉ thêm discovery/config starter tương ứng nhu cầu.
3. Khởi động trong môi trường local hoặc cluster kiểm thử.
4. Bật `debug=true` trong lần kiểm tra có kiểm soát.
5. Đọc Condition Evaluation Report cho discovery và config.
6. Mở Actuator `conditions` và `beans` trong phạm vi bảo vệ.
7. Xác định implementation của DiscoveryClient và Kubernetes client.
8. Kiểm tra property source mà không in giá trị Secret.
9. Dùng ServiceAccount có Role tối thiểu trong cluster.
10. Gọi một Service không gây tác dụng phụ hoặc kiểm tra danh sách instance.
11. Thử ConfigMap không nhạy cảm và quan sát quá trình refresh nếu có.
12. Ghi lại bằng chứng, tắt debug/exposure không cần thiết và cố định cấu hình.

Sơ đồ quyết định:

```text
Bean mong đợi không có?
    |
    v
Condition report có configuration tương ứng không?
    |
    +-- Không -> kiểm tra starter, version, exclude, property
    |
    '-- Có
          |
          v
      Vì sao did not match?
          |
          +-- Thiếu class -> kiểm tra client/starter
          +-- Property -> kiểm tra cấu hình
          +-- Bean đã có -> kiểm tra override/nhầm implementation
          '-- Context/resource -> kiểm tra kiểu ứng dụng và môi trường

Bean có nhưng chức năng lỗi?
    -> kiểm tra connectivity -> RBAC -> namespace/data -> cache -> behavior
```

## 12. Checklist trước khi coi dự án đã sẵn sàng

- Starter đã chọn theo capability, không phải theo thói quen thêm “all”?
- Spring Boot, Spring Cloud và Spring Cloud Kubernetes tương thích?
- Chỉ một họ Kubernetes client làm nền cho integration chính?
- Condition Evaluation Report đã xác nhận configuration quan trọng?
- Bean type và implementation thực tế đã được ghi nhận?
- DiscoveryClient có nguồn ServiceInstance hợp lệ?
- ConfigMap/Secret source có xuất hiện mà không lộ giá trị nhạy cảm?
- LoadBalancer có supplier và HTTP integration phù hợp?
- Watcher có quyền, thông báo và cơ chế hội tụ đầy đủ?
- ServiceAccount, Role và RoleBinding khớp với request API thật?
- Actuator diagnostic endpoints được bảo vệ và giới hạn exposure?
- Có test phân biệt bean creation với runtime behavior?
- Khi API server hoặc resource tạm thời không sẵn sàng, ứng dụng phản ứng an toàn?

Tự cấu hình giúp Spring Boot nối các starter thành một ApplicationContext, nhưng tính đúng đắn của hệ thống chỉ được xác nhận khi đi tiếp từ condition, bean, kết nối, quyền, dữ liệu đến hành vi. Với Spring Cloud Kubernetes, thói quen kiểm tra này giúp phát hiện sớm việc chọn sai starter, trộn sai client hoặc bật một tính năng vượt quá nhu cầu triển khai.
