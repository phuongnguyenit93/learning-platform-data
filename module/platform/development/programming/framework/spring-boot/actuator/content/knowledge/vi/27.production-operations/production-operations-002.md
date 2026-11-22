# Thiết kế nhãn service, instance, môi trường và phiên bản nhất quán

> Phạm vi: vận hành Spring Boot Actuator 3.3.x với Micrometer; Prometheus được dùng để minh họa quá trình thu thập số liệu. Ví dụ Java dùng các API có trong Java 21. Các quy ước giá trị trong bài là một thiết kế cụ thể để tham khảo, không phải tên nhãn bắt buộc của mọi hệ thống.

## 1. Bốn câu hỏi phải trả lời từ một tín hiệu vận hành

Khi thấy tỷ lệ lỗi tăng, người vận hành cần xác định: dịch vụ nào đang gặp vấn đề, bản chạy nào phát sinh tín hiệu, dữ liệu thuộc môi trường nào và phần mềm đang chạy phiên bản nào. Một số đo có giá trị nhưng thiếu danh tính có thể khiến bạn điều tra nhầm bản phát hành hoặc trộn số liệu thử nghiệm vào số liệu thực tế.

Bốn khái niệm cần tách rõ:

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| service | Thành phần chức năng nào? | orders-api |
| instance | Bản chạy hoặc đích thu thập cụ thể nào? | runtime-a hoặc 10.0.12.21:8080, tùy mô hình |
| environment | Đang chạy trong môi trường nào? | production |
| version | Đang chạy bản phần mềm nào? | 2.4.1 |

Giả sử hai bản chạy cùng phục vụ đơn hàng. Chúng cần cùng tên service, có thể cùng environment và version, nhưng phải phân biệt được khi truy tìm lỗi theo từng bản chạy. Ngược lại, trong lúc triển khai cuốn chiếu, hai version có thể cùng tồn tại dưới một service.

Đừng gộp tất cả vào tên như orders-api-production-v2-pod-a. Làm vậy buộc mọi truy vấn phải bóc tách một chuỗi và khiến việc đổi phiên bản giống như xuất hiện một dịch vụ mới. Tách các chiều thông tin giúp lựa chọn đúng mức tổng hợp.

## 2. Xác định hợp đồng nhãn trước khi viết cấu hình

Hợp đồng nhãn là thỏa thuận về ý nghĩa, tên khóa, miền giá trị, nơi cấp giá trị và thời điểm được phép thay đổi. Chỉ thống nhất tên khóa là chưa đủ: production, prod và Production vẫn tạo ba giá trị khác nhau nếu chúng được gửi nguyên trạng.

Một hợp đồng tham khảo:

| Chiều thông tin | Quy ước giá trị | Nguồn cấp | Quy tắc thay đổi |
| --- | --- | --- | --- |
| service | Tên chức năng ổn định, chữ thường, ví dụ orders-api | Danh mục ứng dụng/cấu hình triển khai | Không đổi khi tăng số bản chạy hoặc phát hành phiên bản mới |
| environment | Một trong development, test, staging, production | Cấu hình môi trường triển khai | Cố định trong vòng đời tiến trình |
| version | Định danh bản phát hành, ví dụ 2.4.1 hoặc mã bản dựng bất biến | Pipeline tạo và phát hành artifact | Đổi khi artifact được thay thế; khôi phục bản cũ phải mang lại version cũ |
| instance | Phân biệt đúng đơn vị cần điều tra | Nền tảng chạy hoặc hệ thống thu thập | Ổn định trong đơn vị/vòng đời đã định nghĩa, không sinh lại theo từng yêu cầu |

Nếu nhiều hệ thống có thể có cùng tên service, bổ sung một chiều không gian tên như service_namespace hoặc ánh xạ sang service.namespace khi dùng OpenTelemetry. Cần thống nhất phạm vi duy nhất của tên, thay vì mặc định tên ngắn là duy nhất trong toàn tổ chức.

Với version, latest chỉ là một nhãn tham chiếu có thể thay đổi. Nó không giúp trả lời chính xác bộ mã nào đang chạy. Hãy gắn version với artifact thực tế và lưu quan hệ đến mã commit hoặc mã băm artifact trong hồ sơ phát hành.

Với instance, phải định nghĩa đó là **đích được thu thập** hay **một lần sống của tiến trình**. Địa chỉ host:port có thể được tái sử dụng sau khi tiến trình khởi động lại; nó không tự chứng minh hai mẫu thuộc cùng một lần chạy JVM.

## 3. Mỗi khóa có một nơi chịu trách nhiệm cấp giá trị

Trong thiết kế minh họa xuyên suốt bài này:

- Ứng dụng gắn service, environment và version vào số liệu do nó phát ra.
- Prometheus cấp job và instance cho đích mà nó thu thập.
- Nền tảng chạy có thể cấp thêm INSTANCE_ID cho nhật ký hoặc truy vết khi cần danh tính từng tiến trình.

Không thêm lại service/environment/version vào cấu hình đích Prometheus trong chính mô hình này. Nếu tổ chức muốn nền tảng thu thập sở hữu các khóa đó, hãy chuyển trách nhiệm sang nền tảng và bỏ bản khai báo tương ứng trong ứng dụng.

Việc có hai nơi cùng ghi một khóa dễ tạo xung đột: ứng dụng nói environment=staging còn bộ thu gắn environment=production. Một trong hai bị đổi tên hoặc bị bỏ qua không có nghĩa là dữ liệu đã đúng.

Giá trị dùng trong production nên được kiểm tra sớm: bắt buộc có, không chỉ chứa khoảng trắng, environment thuộc danh sách được chấp nhận và version khớp artifact sẽ chạy. Đừng dùng unknown như một giá trị mặc định để triển khai có vẻ thành công.

## 4. Áp dụng nhãn chung trong Spring Boot Actuator

Nhãn chung (common tags) trong Micrometer được áp dụng ở mức registry. Trong Spring Boot 3.3, management.metrics.tags là cách cấu hình các nhãn này. Nếu cần xử lý bằng Java, MeterRegistryCustomizer là điểm mở rộng được áp dụng trước khi các bộ đo được đăng ký. [Common tags của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.common-tags), [API MeterRegistryCustomizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/metrics/MeterRegistryCustomizer.html).

Đoạn application.yml sau dành cho ứng dụng đã có Actuator và registry Prometheus:

```yaml
spring:
  application:
    name: orders-api

management:
  metrics:
    tags:
      service: "${spring.application.name}"
      environment: "${DEPLOYMENT_ENVIRONMENT}"
      version: "${APP_VERSION}"
  endpoints:
    web:
      exposure:
        include: health,prometheus,metrics
```

Đây là phần cấu hình ghép vào một ứng dụng Spring Boot, không phải toàn bộ dự án độc lập. Các dependency tương ứng, dưới sự quản lý phiên bản của Spring Boot, gồm:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
implementation 'org.springframework.boot:spring-boot-starter-actuator'
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

Giá trị do môi trường triển khai cung cấp có thể được chuẩn bị như sau trên PowerShell:

```powershell
$env:DEPLOYMENT_ENVIRONMENT = 'production'
$env:APP_VERSION = '2.4.1'
```

Cấu hình tham chiếu spring.application.name làm nguồn cho service. Không nên suy ra rằng chỉ khai báo tên ứng dụng thì mọi registry tự có nhãn service đúng hợp đồng này. Tương tự, profile đang bật không nhất thiết là tên môi trường: một ứng dụng có thể đồng thời bật profile production và postgres.

Biến môi trường và các nguồn cấu hình khác có thứ tự ưu tiên. Khi giá trị thực tế khác tệp YAML, hãy kiểm tra nguồn ghi đè có hiệu lực, nhất là cấu hình triển khai và tham số dòng lệnh. [Cấu hình bên ngoài của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### Kiểm tra tại ứng dụng

Trong môi trường thực hành cho phép truy cập các endpoint này:

```powershell
curl.exe -fsS 'http://localhost:8080/actuator/metrics/jvm.memory.used'
curl.exe -fsS 'http://localhost:8080/actuator/prometheus'
```

Ở endpoint metrics, xem availableTags để xác nhận service/environment/version. Ở dữ liệu Prometheus, tìm một mẫu thuộc bộ đo JVM và kiểm tra các nhãn ứng dụng. Giá trị số và thứ tự nhãn có thể thay đổi; không dùng toàn bộ phản hồi làm kết quả cố định.

Endpoint metrics có vai trò chẩn đoán; dữ liệu tại đó chưa phải các chuỗi sau khi Prometheus gắn nhãn đích. Việc bật endpoint và việc cho phép truy cập HTTP cũng là các phần cấu hình riêng. Chỉ đưa những endpoint cần thiết vào đường truy cập vận hành đã được kiểm soát. [Endpoint của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### Khi cần cấu hình bằng Java

Nếu cần tính toán hoặc xác thực nhãn trong mã, dùng callback trước khi đăng ký bộ đo. Đừng đợi đến khi ứng dụng đã chạy một lúc rồi mới đổi nhãn chung: các bộ đo đã có không được coi là sẽ tự biến đổi đồng loạt theo cấu hình mới. Chọn một cách cấp nhãn có chủ đích thay vì khai báo cùng khóa ở cả YAML và nhiều callback. [Thời điểm cấu hình common tags của Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html#_common_tags).

## 5. Hiểu đúng instance khi dùng Prometheus

Prometheus mặc định gắn job theo cấu hình thu thập và instance theo địa chỉ host:port của đích. Vì vậy, một ứng dụng không cần tự xuất nhãn instance chỉ để Prometheus phân biệt hai đích khác nhau. [Jobs và instances](https://prometheus.io/docs/concepts/jobs_instances/).

Ví dụ dưới đây dùng hai địa chỉ minh họa. Phải thay chúng bằng địa chỉ mà máy chạy Prometheus thực sự truy cập được:

```yaml
scrape_configs:
  - job_name: orders-api-production
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - '10.0.12.21:8080'
          - '10.0.12.22:8080'
```

Giả sử cả hai ứng dụng đang chạy version 2.4.1. Sau khi thu thập, các chuỗi có thể cùng mang service=orders-api, environment=production, version=2.4.1 nhưng khác instance. Đây là khác biệt được thêm ở phía Prometheus.

Nếu trực tiếp gọi /actuator/prometheus mà không thấy instance trong phản hồi, điều đó phù hợp với thiết kế này: Prometheus chưa thực hiện bước gắn nhãn đích vào dữ liệu bạn đang xem.

### Tránh hai nghĩa cho cùng khóa instance

Nếu ứng dụng cũng tự xuất instance=runtime-a, khóa này xung đột với nhãn đích. Với honor_labels=false, mặc định của Prometheus, nhãn xung đột trong dữ liệu thu thập được đổi sang exported_instance và nhãn phía Prometheus được giữ dưới instance. Với honor_labels=true, nhãn từ dữ liệu được giữ và nhãn đích xung đột bị bỏ qua. [Cơ chế honor_labels](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config).

Đừng đổi honor_labels chỉ để che một hợp đồng nhãn chưa rõ. Nếu cần phân biệt thêm từng lần chạy tiến trình, cân nhắc khóa app_instance và định nghĩa nguồn, phạm vi duy nhất cùng vòng đời của nó. Một ID được tạo một lần lúc khởi động khác hẳn UUID được tạo lại cho từng yêu cầu.

Trong mô hình đẩy số liệu không có bước gắn instance của Prometheus, cần thiết kế định danh ở registry, thuộc tính tài nguyên hoặc bộ thu tương ứng. Không sao chép nguyên quyết định bỏ instance trong ví dụ này sang mọi hệ thống thu thập.

### Nhãn của up không tự kế thừa nhãn trong dữ liệu ứng dụng

up được Prometheus tạo cho đích thu thập. Các nhãn service/environment/version nằm trong dữ liệu ứng dụng không tự chuyển thành nhãn của up. Với cấu hình trên, có thể kiểm tra đích bằng:

```promql
up{job="orders-api-production"}
```

Nếu cần lọc up theo service hoặc environment, nền tảng phải cấp các nhãn đích tương ứng. Khi đó hãy điều chỉnh lại quyền sở hữu và quy tắc xung đột cho dữ liệu ứng dụng, thay vì lặp cùng khóa ở hai nơi mà không kiểm chứng.

## 6. Giữ danh tính hữu ích mà không làm số chuỗi tăng mất kiểm soát

Trong số liệu dạng chuỗi thời gian, mỗi tổ hợp nhãn khác nhau tạo ra một chuỗi riêng. Số giá trị phân biệt của nhãn thường được gọi là cardinality. Một nhãn được gắn chung sẽ đi theo rất nhiều bộ đo, nên chi phí của nó không chỉ nằm ở một phép đo nghiệp vụ. [Quy tắc nhãn của Prometheus](https://prometheus.io/docs/practices/naming/#labels).

Ví dụ tính toán để hiểu quy mô: giả sử một bản chạy đã phát ra 2.000 chuỗi sau khi tính các nhãn hiện có. Nếu triển khai 20 bản chạy và phân biệt từng bản, tổng có thể khoảng 40.000 chuỗi tương ứng, chưa tính các tín hiệu khác của nền tảng.

Không nhân thêm mọi chiều một cách máy móc. Trong ví dụ này, mỗi bản chạy có một version và một environment tại một thời điểm; các chiều có quan hệ với nhau. Cần ước lượng theo các tổ hợp thực sự xuất hiện.

Các lựa chọn nên tránh:

- Đưa requestId, traceId, userId, email hoặc URL đầy đủ có tham số vào nhãn chung.
- Dùng thời gian hiện tại làm version cho mỗi lần ghi số đo.
- Đổi instance cho mỗi lần thu thập hoặc mỗi yêu cầu.
- Phát cùng một ý nghĩa dưới nhiều khóa như env, environment và deployment_env mà không có lý do chuyển đổi rõ ràng.

Nhãn instance và version vẫn có ích dù tạo thêm chuỗi. Mục tiêu là kiểm soát theo số bản chạy và số bản phát hành, đồng thời theo dõi lượng chuỗi mới sinh ra theo thời gian. Khi version thay đổi, dữ liệu lịch sử của bản cũ vẫn còn trong thời hạn lưu trữ.

Nếu cần chặn một miền nhãn nghiệp vụ tăng ngoài dự kiến, Micrometer có MeterFilter để lọc hoặc biến đổi định danh bộ đo. Đây là lớp bảo vệ bổ sung; nó không thay việc sửa nguồn nhãn sai. [Meter filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

## 7. Dùng cùng ý nghĩa trên số liệu, nhật ký và truy vết

Nhất quán không bắt buộc mọi giao thức dùng cùng cách viết khóa. Điều cần giữ là ý nghĩa và giá trị có cùng nguồn chuẩn. Bảng ánh xạ tham khảo:

| Ý nghĩa | Nhãn metrics trong bài | Trường nhật ký do đội dự án quy định | Thuộc tính tài nguyên OpenTelemetry |
| --- | --- | --- | --- |
| Dịch vụ | service | service | service.name |
| Phiên bản | version | version | service.version |
| Môi trường | environment | environment | deployment.environment.name |
| Bản chạy | instance do Prometheus cấp; app_instance nếu có nhu cầu riêng | instance | service.instance.id |

service.name giữ ổn định giữa các bản chạy cùng dịch vụ; service.version mô tả phiên bản. service.instance.id phải phân biệt các instance trong phạm vi service.namespace và service.name. Địa chỉ thu thập không nhất thiết bằng giá trị service.instance.id, nên nếu cần đối chiếu chúng phải lưu được ánh xạ. [Quy ước service của OpenTelemetry](https://opentelemetry.io/docs/specs/semconv/resource/service/).

deployment.environment.name mô tả tầng môi trường, chẳng hạn production hoặc staging. Đây là một chiều thông tin riêng; không nhét nó vào tên dịch vụ chỉ để việc lọc môi trường dễ hơn. [Quy ước môi trường triển khai](https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/).

Trong đường tích hợp OpenTelemetry do Spring Boot 3.3 tự cấu hình, có thể cấu hình thuộc tính cho Resource bằng management.opentelemetry.resource-attributes. Đoạn dưới minh họa ánh xạ; bản thân nó chưa thiết lập đầy đủ truy vết hoặc bộ xuất:

```yaml
management:
  opentelemetry:
    resource-attributes:
      service.name: "${spring.application.name}"
      service.version: "${APP_VERSION}"
      service.instance.id: "${INSTANCE_ID}"
      deployment.environment.name: "${DEPLOYMENT_ENVIRONMENT}"
```

Nếu đã tự khai báo Resource hoặc dùng agent/starter theo một đường tích hợp khác, phải kiểm tra cơ chế cấu hình của chính đường đó. Các mục management.metrics.tags, management.observations.key-values và thuộc tính Resource có phạm vi khác nhau; một mục không tự cấu hình toàn bộ các mục còn lại. Việc thêm trường vào nhật ký cũng cần cấu hình logging tương ứng. [Observability và Resource trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 8. Giữ khả năng so sánh khi triển khai cuốn chiếu

Trong lúc thay phiên bản, trạng thái hợp lệ có thể là:

| service | environment | instance của Prometheus | version |
| --- | --- | --- | --- |
| orders-api | production | 10.0.12.21:8080 | 2.4.1 |
| orders-api | production | 10.0.12.22:8080 | 2.5.0 |

Để xem tổng bộ nhớ heap theo phiên bản:

```promql
sum by (service, environment, version) (
  jvm_memory_used_bytes{
    service="orders-api",
    environment="production",
    area="heap"
  }
)
```

Để xem tốc độ yêu cầu theo phiên bản khi ứng dụng đã có dữ liệu bộ đo HTTP tương ứng:

```promql
sum by (service, environment, version) (
  rate(http_server_requests_seconds_count{
    service="orders-api",
    environment="production"
  }[5m])
)
```

Trong truy vấn tốc độ, tính rate trên từng chuỗi trước rồi mới sum để việc xử lý bộ đếm bị đặt lại vẫn có đủ thông tin. [Hàm rate của Prometheus](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate).

Các truy vấn này chủ động bỏ instance khỏi kết quả tổng hợp nhưng giữ version. Khi cần tìm bản chạy lỗi, thêm instance vào nhóm hoặc bộ lọc. Khi cần sức khỏe chung của dịch vụ, có thể bỏ version khỏi nhóm.

Cửa sổ 5 phút có thể còn chứa dữ liệu của bản cũ sau khi nó đã ngừng chạy. Một đường trên biểu đồ tốc độ không tự chứng minh instance đó vẫn tồn tại ở thời điểm hiện tại.

Giữ nguyên định nghĩa môi trường và tên dịch vụ trong suốt triển khai. Khi khôi phục artifact 2.4.1, version phải phản ánh 2.4.1; không đổi thành thời điểm thực hiện thao tác khôi phục.

## 9. Ví dụ Java: kiểm tra hợp đồng giá trị

Chương trình dưới đây chỉ minh họa hợp đồng danh tính bằng Java thuần. Nó không tự gắn nhãn vào Spring Boot. Phương thức metricTags cố ý trả ba nhãn ứng dụng trong mô hình Prometheus đã chọn; instance vẫn được lưu để minh họa hai bản chạy khác nhau.

Tệp IdentityLabelsDemo.java:

```java
import java.util.Map;
import java.util.Set;

public class IdentityLabelsDemo {
    record Identity(String service, String environment,
                    String version, String instance) {
        Identity {
            service = required("service", service);
            environment = required("environment", environment);
            version = required("version", version);
            instance = required("instance", instance);

            if (!service.matches("[a-z][a-z0-9]*(?:-[a-z0-9]+)*")) {
                throw new IllegalArgumentException("Invalid service");
            }
            if (!Set.of("development", "test", "staging", "production")
                    .contains(environment)) {
                throw new IllegalArgumentException("Invalid environment");
            }
            if (Set.of("latest", "unknown", "unspecified").contains(version)) {
                throw new IllegalArgumentException("Ambiguous version");
            }
        }

        Map<String, String> metricTags() {
            return Map.of(
                "service", service,
                "environment", environment,
                "version", version
            );
        }

        private static String required(String key, String value) {
            if (value == null || value.isBlank()
                    || !value.equals(value.strip())) {
                throw new IllegalArgumentException("Invalid " + key);
            }
            return value;
        }
    }

    public static void main(String[] args) {
        Identity first = new Identity(
            "orders-api", "production", "2.4.1", "runtime-a"
        );
        Identity second = new Identity(
            "orders-api", "production", "2.4.1", "runtime-b"
        );

        System.out.println("service=" + first.service());
        System.out.println("environment=" + first.environment());
        System.out.println("version=" + first.version());
        System.out.println("sameMetricTags="
            + first.metricTags().equals(second.metricTags()));
        System.out.println("sameInstance="
            + first.instance().equals(second.instance()));

        try {
            new Identity("orders-api", "Prod", "2.4.1", "runtime-c");
            throw new AssertionError("Invalid environment was accepted");
        }
        catch (IllegalArgumentException expected) {
            System.out.println("invalidEnvironment=rejected");
        }
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```powershell
javac --release 21 -encoding UTF-8 IdentityLabelsDemo.java
java IdentityLabelsDemo
```

Stdout:

```text
service=orders-api
environment=production
version=2.4.1
sameMetricTags=true
sameInstance=false
invalidEnvironment=rejected
```

sameMetricTags=true cho biết hai bản chạy có cùng ba chiều thông tin do ứng dụng cấp. Chúng vẫn được phân biệt sau khi Prometheus gắn nhãn đích khác nhau. sameInstance=false cho biết mã bản chạy riêng trong ví dụ cũng khác.

Giá trị Prod bị từ chối vì hợp đồng này yêu cầu production. Đây là quyết định kiểm tra dữ liệu minh họa, không phải Spring tự chuẩn hóa Prod. Kiểm tra thực tế còn cần đối chiếu version với artifact và xác minh tính duy nhất của instance trên nền tảng triển khai; một hàm Java cục bộ không đủ để chứng minh các điều đó.

## 10. Kiểm chứng từ nguồn cấu hình đến hệ thống lưu trữ

Một lần kiểm tra đầy đủ nên đi qua các tầng:

1. **Hồ sơ phát hành:** version và mã artifact có khớp bản sẽ chạy không?
2. **Cấu hình có hiệu lực:** service/environment/version có đúng, thiếu hay bị ghi đè không?
3. **Tại ứng dụng:** endpoint chẩn đoán và dữ liệu xuất có các nhãn ứng dụng đã thỏa thuận không?
4. **Tại bộ thu:** đích có đúng job/instance và có xuất hiện exported_service, exported_environment hoặc exported_instance ngoài dự kiến không?
5. **Trong truy vấn:** có tách được hai môi trường, hai instance và hai phiên bản theo đúng mục đích không?
6. **Khi thay phiên bản:** dữ liệu bản cũ và mới có được nhận diện đúng mà không đổi tên service không?

Kiểm tra thêm cả trường hợp thiếu metadata, environment viết sai, triển khai đồng thời hai phiên bản và khôi phục phiên bản cũ. Không chỉ xác nhận một cấu hình đúng trên máy cá nhân.

Những dấu hiệu cần xem lại hợp đồng là: production lẫn prod, mọi bản chạy có cùng instance do cấu hình cứng, version luôn là latest, hoặc nhãn thay đổi theo từng yêu cầu. Khi phát hiện, sửa tại nguồn cấp và đánh giá ảnh hưởng đến dashboard/cảnh báo; dữ liệu lịch sử không tự được đổi tên theo cấu hình mới.

## 11. Tự thực hành

1. Cho hai bản chạy cùng service và version nhưng ở staging và production. Chỉ ra nhãn nào cần khác và viết bộ lọc để không trộn hai môi trường.
2. Cho một ứng dụng tự xuất instance trong khi Prometheus dùng honor_labels=false. Dự đoán hai khóa sẽ xuất hiện sau thu thập và giải thích nguồn của từng khóa.
3. Triển khai hai version cùng lúc. Viết một truy vấn tổng theo dịch vụ và một truy vấn tách theo version; nêu khác biệt về câu hỏi vận hành mà chúng trả lời.
4. Thử truyền giá trị version=latest vào ví dụ Java để quan sát việc từ chối, rồi bổ sung một kiểm tra theo chính sách phát hành thực tế của bạn. Giải thích vì sao kiểm tra định dạng vẫn chưa chứng minh artifact là đúng.
5. Thiết kế ánh xạ giữa instance của Prometheus và service.instance.id trong truy vết nếu yêu cầu điều tra cần đi từ số liệu của một đích sang vết của một lần chạy cụ thể.

Thiết kế đạt mục tiêu khi mỗi tín hiệu trả lời được bốn câu hỏi danh tính, các nguồn cấp giá trị không tranh quyền và việc tăng số bản chạy hay đổi phiên bản vẫn giữ được khả năng so sánh.
