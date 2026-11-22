# Rà soát thay đổi endpoint, cấu hình và thư viện khi nâng cấp Spring Boot

> Phạm vi: rà soát khả năng vận hành của ứng dụng có Spring Boot Actuator. Hai ví dụ phiên bản cụ thể là thay đổi Prometheus khi đi từ Boot 3.2 sang 3.3 và thay đổi quyền endpoint khi đi từ Boot 3.3 sang 3.4. Chúng minh họa cách phân tích một lần nâng cấp, không phải đề xuất chọn một phiên bản đích cho mọi dự án.

## 1. Nâng cấp làm thay đổi những hợp đồng nào?

Một ứng dụng sau nâng cấp có thể biên dịch và khởi động thành công nhưng bộ thu số liệu không còn đọc được dữ liệu, health probe trỏ sai đường hoặc một endpoint chẩn đoán mở rộng quyền ngoài dự kiến.

Với Actuator, cần nhìn ba lớp cùng nhau:

| Lớp | Những gì có thể thay đổi | Ai bị ảnh hưởng? |
| --- | --- | --- |
| Endpoint | Tính khả dụng, đường dẫn, thao tác, quyền truy cập, kiểu nội dung, cấu trúc phản hồi | Bộ kiểm tra sức khỏe, người vận hành, công cụ tự động |
| Cấu hình | Khóa đổi tên, khóa deprecated, mặc định, cách binding và nguồn ghi đè | Ứng dụng, cấu hình triển khai, chính sách vận hành |
| Thư viện | Phiên bản thực tế, package/API, điều kiện tự cấu hình, giao thức xuất dữ liệu | Mã Java, registry, exporter, collector, dashboard và cảnh báo |

Đây là các hợp đồng vận hành: hệ thống khác đang phụ thuộc vào hành vi nào của ứng dụng. Mục tiêu rà soát là xác định thay đổi nào có chủ đích, thay đổi nào phá vỡ hợp đồng và bằng chứng nào đủ để chấp nhận bản mới.

Không dùng việc mọi endpoint đều trả 200 làm tiêu chí thành công. Endpoint cần được bảo vệ phải tiếp tục từ chối người không có quyền; endpoint không phục vụ nhu cầu vận hành không nên xuất hiện chỉ vì bản mới bổ sung nó.

## 2. Chốt bản nguồn, bản đích và dữ liệu làm chuẩn

Trước khi đổi phiên bản, ghi lại một bộ thông tin có thể tái lập:

- Phiên bản Spring Boot nguồn và đích đầy đủ đến bản vá.
- JDK dùng để biên dịch và chạy, Gradle Wrapper, loại ứng dụng Servlet hoặc Reactive.
- Artifact đang chạy và tập cấu hình triển khai có hiệu lực.
- Dependency graph đã resolve, các phiên bản ghi đè và thư viện tích hợp bên ngoài.
- Tập endpoint, chính sách người gọi, health groups và các dữ liệu quan sát thực sự được sử dụng.

Bản nguồn không chỉ là một số trong build.gradle. BOM, dependency constraint, plugin dùng chung hoặc resolution rule có thể làm phiên bản runtime khác điều bạn đọc ở một dòng khai báo.

Đo bản nguồn và bản đích với cùng dữ liệu thử, cấu hình tương đương và lưu lượng đủ tạo các bộ đo cần kiểm tra. Nếu đổi cả phiên bản, dữ liệu thử và cấu hình môi trường cùng lúc, rất khó kết luận nguyên nhân của một khác biệt.

### Đóng băng kỳ vọng, không đóng băng mọi byte

Lưu các phần phản hồi phục vụ hợp đồng, chẳng hạn trường status, tập nhãn cần có hoặc tên metric mà cảnh báo sử dụng. Loại các giá trị biến động khỏi phép so sánh nguyên văn: timestamp, uptime, số đo bộ nhớ, thứ tự nhãn và traceId của từng lần gọi.

Điều này không có nghĩa là bỏ qua số đo. Cấu trúc và tên cần được đối chiếu theo hợp đồng; độ trễ, mức sử dụng tài nguyên và số lỗi cần được đánh giá bằng phép đo riêng.

## 3. Đọc tài liệu theo đúng đường nâng cấp

Bắt đầu bằng mục nâng cấp trong release notes của bản đích, rồi kiểm tra những bản trung gian nếu bỏ qua nhiều lần phát hành. Spring Boot hướng dẫn đọc cả release notes của các phiên bản đã bỏ qua. [Hướng dẫn nâng cấp Spring Boot](https://docs.spring.io/spring-boot/3.3/upgrading.html).

Với từng thay đổi liên quan, ghi lại:

| Nội dung cần xác minh | Câu hỏi cụ thể |
| --- | --- |
| Mức tương thích | Yêu cầu JDK/build tool có thay đổi không? |
| Cấu hình | Khóa bị đổi tên, deprecated, bỏ hỗ trợ hay chỉ đổi mặc định? |
| Endpoint | Thao tác nào được tạo hoặc không còn được tạo? Phản hồi nào đổi? |
| Dependency | BOM thay đổi thư viện nào mà ứng dụng hoặc công cụ đang dùng trực tiếp? |
| Tích hợp | Collector, thư viện Spring liên quan hoặc exporter có hỗ trợ tổ hợp mới không? |

Đọc thêm configuration changelog và tài liệu Micrometer, Spring Security hoặc thư viện thực sự thay đổi. Không dùng trang của một phiên bản khác để suy ra rằng cùng thuộc tính hoặc cùng giá trị mặc định áp dụng cho bản đang chạy.

Patch, minor và major giúp định hướng quy mô rà soát, nhưng không thay bằng chứng. Một bản vá vẫn có thể thay đổi hành vi quan trọng do sửa lỗi; một bản minor có thể nâng cấp thư viện mà API trực tiếp của bạn đang phụ thuộc.

## 4. Kiểm tra thư viện thực tế trước khi sửa mã

Spring Boot quản lý một tập phiên bản phụ thuộc được thiết kế để làm việc cùng nhau. Khi dùng cơ chế quản lý dependency của Boot, nhiều dependency không cần ghi phiên bản riêng. Các override vẫn cần được kiểm kê và đánh giá lại khi nâng cấp. [Quản lý dependency với Gradle của Spring Boot](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html).

Trong một dự án ứng dụng Gradle độc lập có configuration runtimeClasspath, có thể dùng:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency opentelemetry-sdk --configuration runtimeClasspath
```

Trong multi-project, gọi task của đúng project ứng dụng đã xác minh thay vì mặc định configuration này tồn tại ở root. Các lệnh trên là ví dụ điều tra graph, không phải yêu cầu thay đổi phiên bản của các thư viện được nêu.

dependencies cho biết graph đã chọn; dependencyInsight giúp giải thích nguồn đưa thư viện vào và lý do chọn phiên bản. So sánh kết quả giữa hai bản, gồm cả các dependency bắc cầu. [Công cụ xem dependency của Gradle](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).

Những câu hỏi quan trọng:

1. Boot plugin và BOM có cùng ý định phiên bản không?
2. Có thư viện quan sát bị ép về bản cũ bởi một constraint hoặc plugin khác không?
3. Có nhiều bridge, registry hoặc exporter chồng lấn khiến dữ liệu được gửi hai lần không?
4. Mã tùy biến có dùng lớp cụ thể của một registry thay vì API chung không?
5. Thư viện tích hợp do đội dự án quản lý có phải được nâng cùng không?

Không chữa NoSuchMethodError hoặc NoClassDefFoundError bằng cách thêm ngẫu nhiên một JAR. Trước hết xác minh tổ hợp thư viện và API mà thành phần gọi thật sự được biên dịch để sử dụng.

### Ví dụ: Prometheus khi nâng từ Boot 3.2 sang 3.3

Boot 3.3 đưa hỗ trợ Prometheus Java client 1.x vào registry Prometheus. Release notes chỉ ra các thay đổi có thể ảnh hưởng dữ liệu xuất. Vì vậy, endpoint prometheus vẫn trả 200 chưa đủ để kết luận hệ thống quan sát giữ nguyên hành vi. [Release notes Spring Boot 3.3](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes#prometheus-client-1x).

Trong Micrometer 1.13, module micrometer-registry-prometheus chuyển package cơ sở từ io.micrometer.prometheus sang io.micrometer.prometheusmetrics. Mã dùng trực tiếp PrometheusMeterRegistry phải được kiểm tra import và API tương ứng:

```java
// Registry sử dụng client mới trong Micrometer 1.13
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
```

Đây là đoạn import minh họa, không phải chương trình Java độc lập. Nếu ứng dụng chỉ dùng MeterRegistry do Boot cung cấp, có thể không cần sửa dòng import nào nhưng vẫn phải kiểm tra đầu ra số liệu.

Các thay đổi scrape cũng có thể chỉ khác biểu diễn, như số đếm từ 1.0 thành 1, hoặc khác về tên/loại dữ liệu. Phải phân loại khác biệt theo ngữ nghĩa, thay vì coi mọi chênh lệch văn bản là lỗi hoặc bỏ qua tất cả vì vẫn parse được. [Hướng dẫn migration Micrometer 1.13](https://github.com/micrometer-metrics/micrometer/wiki/1.13-Migration-Guide).

Module simpleclient cũ từng được cung cấp như một đường chuyển tiếp đã deprecated. Nếu dùng một cầu nối tạm thời, phải ghi phạm vi và kế hoạch loại bỏ; không coi nó là hợp đồng được giữ mãi ở mọi phiên bản sau.

## 5. Rà soát cấu hình ở cả tệp và môi trường triển khai

Kiểm kê các khóa liên quan đến:

- Endpoint được bật, được expose qua HTTP/JMX và mức thao tác được phép.
- Management port, base path, path mapping và cấu hình reverse proxy.
- Health groups, probe, ánh xạ trạng thái HTTP và mức chi tiết công bố.
- Nhãn metrics, bộ đo bị lọc, histogram/bucket và xuất dữ liệu.
- Tracing, sampling, exporter và địa chỉ hệ thống thu thập.
- Mức log, nội dung nhạy cảm và cấu hình xoay vòng tệp.

Đọc cả biến môi trường, tham số dòng lệnh, profile và cấu hình bên ngoài. Đổi khóa trong application.yml không đủ nếu deployment vẫn ghi đè bằng tên cũ hoặc một nguồn khác.

Với mỗi khóa, phân biệt rõ:

| Trạng thái | Cách xử lý |
| --- | --- |
| Đổi tên nhưng ý nghĩa tương đương | Chuyển nguồn cấu hình và kiểm tra giá trị có hiệu lực |
| Deprecated nhưng còn được hỗ trợ | Lập kế hoạch chuyển; không tự khẳng định khóa đã bị xóa |
| Bỏ hỗ trợ | Thay bằng khả năng mới hoặc loại phần cấu hình không còn tác dụng |
| Không đổi tên nhưng đổi mặc định | Kiểm tra ý định vận hành và cấu hình rõ nếu cần |
| Thay đổi ý nghĩa | Thiết kế lại policy và kiểm thử hành vi, không chỉ thay chuỗi tên |

Configuration metadata giúp nhận diện các thuộc tính và thông tin cấu hình được công bố cho công cụ phát triển. Việc IDE gợi ý một khóa không thay cho kiểm tra runtime, profile và nguồn ghi đè. [Configuration metadata của Spring Boot](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html).

### Công cụ hỗ trợ migration chỉ là một phần của bằng chứng

Khi phiên bản đích hỗ trợ, có thể thêm tạm module properties migrator để hỗ trợ phát hiện và chuyển các thuộc tính mà công cụ biết:

```groovy
runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
```

Đoạn dependency giả định dự án đã quản lý phiên bản phù hợp bằng Boot. Đọc kết quả trong môi trường thử, sửa các nguồn cấu hình gốc rồi gỡ module khi hoàn tất. Nó không tự chứng minh mọi khóa tùy biến, cấu hình được nạp muộn hoặc thay đổi ngữ nghĩa đã được xử lý. [Properties migrator và giới hạn được công bố](https://docs.spring.io/spring-boot/3.3/upgrading.html#upgrading.from-2x).

### So sánh điều kiện tự cấu hình

Nếu một bean registry, exporter hoặc endpoint biến mất, kiểm tra điều kiện thay vì lập tức tự khai báo một bean để bù. Classpath, thuộc tính, bean tùy biến và điều kiện của bản mới có thể dẫn tới lựa chọn khác.

Trong môi trường kiểm thử được kiểm soát, có thể xem conditions report bằng tùy chọn debug. Với dự án Boot độc lập có task bootRun:

```powershell
.\gradlew.bat bootRun --args='--debug'
```

Tìm nguyên nhân cấu hình được áp dụng hay không được áp dụng cho thành phần đang điều tra. Báo cáo là công cụ chẩn đoán và cần được xử lý như dữ liệu vận hành, không phải lý do mở rộng quyền endpoint trên production. [Conditions report của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

## 6. Ví dụ thay đổi ngữ nghĩa: quyền endpoint từ Boot 3.3 sang 3.4

Trong Boot 3.3, mô hình bật/tắt dùng management.endpoints.enabled-by-default và management.endpoint.<id>.enabled. Ví dụ chỉ bật health và prometheus:

```yaml
# Ví dụ dành cho Spring Boot 3.3
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      enabled: true
    prometheus:
      enabled: true
```

Boot 3.4 giới thiệu access với các mức none, read-only và unrestricted; các khóa enabled cũ được đánh dấu deprecated. Mô hình mới còn có max-permitted để đặt trần thao tác cho toàn bộ endpoint. [Thay đổi endpoint trong release notes Boot 3.4](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes#controlling-access-to-actuator-endpoints).

Một policy chủ đích trên Boot 3.4 để chỉ cho phép đọc hai endpoint đã chọn:

```yaml
# Ví dụ dành cho Spring Boot 3.4
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      access: read-only
    prometheus:
      access: read-only
```

Không chép khối cấu hình của 3.4 vào ứng dụng 3.3 rồi cho rằng nó đã thực thi mô hình mới. Hai khối minh họa phải được đối chiếu theo đúng phiên bản chạy.

Những điểm cần kiểm tra khi chuyển:

- enabled=true trước đây không tự đồng nghĩa với ý định chỉ đọc. Endpoint như loggers có cả thao tác đọc và thay đổi cấu hình.
- max-permitted có thể giới hạn mức của từng endpoint dù endpoint đó được khai báo unrestricted.
- Access quyết định thao tác endpoint được cung cấp; exposure quyết định kênh công bố; Spring Security quyết định người gọi được truy cập.
- read-only không có nghĩa là dữ liệu công khai hoặc vô hại: một thao tác đọc dữ liệu chẩn đoán vẫn có thể trả nội dung nhạy cảm.

Với endpoint khai báo bằng @Endpoint, mức đọc gắn với @ReadOperation. Đây không phải tên vai trò người dùng hoặc scope JWT. [Mô hình access của Actuator 3.4](https://docs.spring.io/spring-boot/3.4/reference/actuator/endpoints.html#actuator.endpoints.access).

Chỉ sửa tên thuộc tính mà không kiểm thử thao tác đọc/ghi có thể khiến một công cụ vận hành mất chức năng, hoặc làm policy khác với ý định ban đầu.

## 7. Kiểm tra endpoint bằng một ma trận hợp đồng

Đối với mỗi endpoint đang sử dụng, xác nhận đồng thời:

| Chiều kiểm tra | Nội dung cần đối chiếu |
| --- | --- |
| Vị trí | ID, base path, management port, đường đi qua proxy |
| Tính khả dụng | Điều kiện tạo endpoint và thao tác được cung cấp |
| Người gọi | Ẩn danh, người chỉ đọc số liệu, người trực hoặc chủ thể được cấp quyền riêng |
| Giao thức | HTTP method, status, Content-Type và khả năng thương lượng nội dung |
| Phản hồi | Trường bắt buộc, ý nghĩa trạng thái và mức chi tiết được phép công bố |
| Kênh | HTTP/JMX thực sự được dùng, không chỉ một đường truy cập |

Với health, kiểm tra cả tình trạng khỏe và các tình huống suy giảm đã được xác định. Xác nhận membership của liveness/readiness, mapping trạng thái và hành vi trong thời gian khởi động hoặc dừng. Một probe trỏ đúng URL nhưng kiểm tra sai ý nghĩa vẫn có thể đưa ra quyết định vận hành sai.

Với endpoint nhạy cảm, kiểm tra cả việc từ chối. Không dùng một kết quả 404 để suy ra chắc chắn endpoint đã bị vô hiệu hóa: proxy, đường dẫn sai hoặc bộ lọc bảo mật cũng có thể làm kết quả trông giống nhau.

Nếu có SecurityFilterChain tùy biến, đối chiếu matcher, thứ tự và phạm vi của các chuỗi. Việc tự khai báo chuỗi bảo mật làm thay đổi trách nhiệm cấu hình so với mặc định Boot; không mặc định bản mới sẽ bổ sung những rule còn thiếu cho bạn. [Tính khả dụng và bảo vệ endpoint trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Với @Endpoint hoặc extension tự viết, kiểm tra các annotation thao tác, kiểu tham số/kết quả và cách chuyển đổi dữ liệu mà công cụ gọi đang phụ thuộc. Tránh dựa vào nội bộ của một auto-configuration thay cho điểm mở rộng được công bố.

## 8. Kiểm tra cả đường dữ liệu quan sát đến nơi sử dụng

Đối chiếu theo đường đi:

```text
Ứng dụng tạo phép đo/quan sát
    -> registry hoặc tracing bridge
    -> endpoint scrape hoặc exporter
    -> collector/hệ thống lưu trữ
    -> recording rule, dashboard và cảnh báo
```

Ở từng chặng, cần xác minh:

1. **Tại ứng dụng:** dữ liệu có được tạo dưới lưu lượng thử không; có phát sinh bản ghi trùng không?
2. **Tại đầu ra:** tên, loại metric, nhãn, đơn vị và bucket có còn đúng không?
3. **Tại bộ thu:** có parse được định dạng và nhận đủ dữ liệu từ mọi instance không?
4. **Tại truy vấn:** bộ lọc có còn khớp và mẫu số có còn đầy đủ không?
5. **Tại cảnh báo:** điều kiện có hoạt động với cả dữ liệu tốt, dữ liệu xấu và dữ liệu mất không?

Một dashboard không báo lỗi cú pháp vẫn có thể rỗng vì tên hoặc nhãn đã thay đổi. Một SLI có thể trông đẹp hơn chỉ vì một phần mẫu số không còn được thu thập.

Đối với histogram, kiểm tra các ranh giới mà truy vấn dùng trên mọi instance của bản mới. Đối với tracing, kiểm tra sự nối tiếp context, sampling đã chọn, thông tin liên kết log và phần dữ liệu được phép xuất.

So sánh giá trị động theo điều kiện thử phù hợp. Không yêu cầu số đếm trước và sau phải giống hệt nếu số lần gọi thử hoặc thời gian chạy khác nhau. Cũng không bỏ qua thay đổi đơn vị chỉ vì hai phản hồi đều chứa số.

### Kiểm thử Spring chưa thay cho kiểm thử bộ thu

Dùng test có ApplicationContext để kiểm tra bean, cấu hình và quyền HTTP. Dùng bài thử tích hợp với registry/exporter và bộ thu thực tế cho những hợp đồng phụ thuộc đường xuất dữ liệu.

Hãy xác nhận cấu hình observability trong test: Spring Boot có những hành vi riêng cho @SpringBootTest và kiểm thử lát cắt. Một test dùng registry trong bộ nhớ không tự chứng minh exporter production đã hoạt động. [Kiểm thử ứng dụng Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).

## 9. Ví dụ Java: đánh giá thay đổi bằng kỳ vọng cụ thể

Chương trình sau minh họa một phần của cách so sánh. Snapshot là dữ liệu giả định đã thu được; nó không gọi HTTP và không tự đọc phản hồi Prometheus. Hai vi phạm được cố ý đưa vào bản ứng viên: heapdump đọc được bởi người ẩn danh và thiếu một tên metric bắt buộc.

Không được hiểu dữ liệu giả định này là tuyên bố một phiên bản Boot thực tế tự mở heapdump hoặc xóa bộ đo HTTP.

Tệp UpgradeContractDemo.java:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class UpgradeContractDemo {
    record Probe(String name, Set<Integer> allowedStatuses) {
        Probe {
            allowedStatuses = Set.copyOf(allowedStatuses);
        }
    }

    record Snapshot(Map<String, Integer> statuses, Set<String> metricNames) {
        Snapshot {
            statuses = Map.copyOf(statuses);
            metricNames = Set.copyOf(metricNames);
        }
    }

    static List<String> violations(
            List<Probe> contract, Set<String> requiredMetrics,
            Snapshot snapshot) {
        List<String> problems = new ArrayList<>();
        for (Probe probe : contract) {
            Integer status = snapshot.statuses().get(probe.name());
            if (status == null) {
                problems.add(probe.name() + ": missing result");
            }
            else if (!probe.allowedStatuses().contains(status)) {
                problems.add(probe.name() + ": unexpected HTTP " + status);
            }
        }
        requiredMetrics.stream().sorted()
            .filter(name -> !snapshot.metricNames().contains(name))
            .forEach(name -> problems.add("missing metric: " + name));
        return List.copyOf(problems);
    }

    public static void main(String[] args) {
        List<Probe> contract = List.of(
            new Probe("health:anonymous", Set.of(200)),
            new Probe("prometheus:collector", Set.of(200)),
            new Probe("heapdump:anonymous", Set.of(401, 403, 404))
        );
        Set<String> requiredMetrics = Set.of(
            "http_server_requests_seconds_count",
            "jvm_memory_used_bytes"
        );
        Snapshot baseline = new Snapshot(
            Map.of("health:anonymous", 200,
                   "prometheus:collector", 200,
                   "heapdump:anonymous", 404),
            requiredMetrics
        );
        Snapshot candidate = new Snapshot(
            Map.of("health:anonymous", 200,
                   "prometheus:collector", 200,
                   "heapdump:anonymous", 200),
            Set.of("jvm_memory_used_bytes")
        );

        List<String> oldProblems = violations(contract, requiredMetrics, baseline);
        List<String> newProblems = violations(contract, requiredMetrics, candidate);
        System.out.println("baselineViolations=" + oldProblems.size());
        System.out.println("candidateViolations=" + newProblems.size());
        newProblems.forEach(System.out::println);
        System.out.println("candidateAcceptable=" + newProblems.isEmpty());
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```powershell
javac --release 21 -encoding UTF-8 UpgradeContractDemo.java
java UpgradeContractDemo
```

Stdout:

```text
baselineViolations=0
candidateViolations=2
heapdump:anonymous: unexpected HTTP 200
missing metric: http_server_requests_seconds_count
candidateAcceptable=false
```

Chương trình không so byte của phản hồi. Nó kiểm tra những điều đã viết thành hợp đồng: người gọi có đúng kết quả truy cập và dữ liệu bắt buộc có tồn tại không.

Tập 401/403/404 trong ví dụ chỉ mô tả các kết quả từ chối được chấp nhận cho một phép thử ẩn danh. Muốn chứng minh endpoint bị tắt, bảo vệ đúng vai trò hoặc trả đúng nội dung, cần thêm những phép kiểm tra tương ứng.

Trong công cụ thực tế, cần phân tích nội dung bằng parser phù hợp, kiểm tra schema/ngữ nghĩa và lấy tên metric từ dữ liệu đã parse. Không dùng việc tìm thấy một chuỗi trong comment hoặc phần HELP như bằng chứng mẫu số liệu thật đã tồn tại.

Ví dụ chưa kiểm tra Content-Type, payload health, nhãn, kiểu dữ liệu hay kết quả truy vấn. Những phần đó phải được đưa vào bộ kiểm thử của dự án theo hợp đồng đã xác định.

## 10. Phân loại khác biệt trước khi quyết định phát hành

| Khác biệt quan sát được | Cách đánh giá |
| --- | --- |
| Thứ tự trường JSON hoặc nhãn thay đổi | Nếu thứ tự không thuộc hợp đồng, chuẩn hóa khi so sánh |
| Số đếm được biểu diễn 1 thay vì 1.0 | Parse theo kiểu số; kiểm tra bên tiêu thụ chấp nhận đúng |
| Endpoint không còn cho thao tác ghi cần thiết | Đối chiếu policy access, exposure và quyền; không mở toàn bộ để chữa nhanh |
| Endpoint nhạy cảm trả dữ liệu cho người không có quyền | Vi phạm quyền; chưa chấp nhận bản ứng viên |
| Một metric hoặc nhãn đổi ngoài kế hoạch | Sửa điểm xuất hoặc các bên tiêu thụ theo kế hoạch được kiểm tra |
| Bean exporter mất do điều kiện mới | Điều tra graph/cấu hình/điều kiện; xác nhận lại end-to-end |
| Khóa deprecated vẫn xuất hiện trong deployment | Chuyển nguồn cấu hình và kiểm tra lại khi bỏ lớp tương thích |

Với một thay đổi có chủ đích, cập nhật hợp đồng và các bên tiêu thụ cùng bằng chứng. Không cập nhật toàn bộ snapshot chỉ để làm bộ kiểm thử chuyển xanh.

## 11. Triển khai và khôi phục phải bao gồm cả cấu hình

Trước production, hoàn thành build và các bài kiểm tra phù hợp trên artifact sẽ phát hành, với cấu hình tương đương môi trường đích. Ghi lại nguồn, phiên bản đã resolve và kết quả đối chiếu để tránh kiểm thử một tổ hợp rồi phát hành tổ hợp khác.

Trong một đợt triển khai giới hạn, quan sát cả hành vi phục vụ người dùng và đường giám sát của bản mới. Nếu bản cũ và mới cùng chạy, bảo đảm cách gắn version/instance giúp so sánh được mà không làm cảnh báo mất một phần dữ liệu.

Chuẩn bị khả năng khôi phục theo một bộ tương thích gồm artifact, cấu hình và phần tích hợp liên quan. Hạ JAR về bản cũ nhưng giữ riêng các khóa cấu hình chỉ có ở bản mới có thể làm việc khôi phục không đúng như dự kiến.

Đánh giá riêng những thay đổi khó đảo ngược, chẳng hạn dữ liệu ngoài ứng dụng hoặc giao thức bên tiêu thụ đã thay đổi. Không mặc định mọi lần đổi dependency đều có thể khôi phục bằng một thao tác đổi version.

Các bằng chứng nên giữ cho lần nâng cấp:

- Bản nguồn/bản đích, JDK, Wrapper và artifact đã thử.
- Graph runtime và danh sách override còn tồn tại.
- Ma trận cấu hình: nguồn cũ, nguồn mới, ý nghĩa và giá trị có hiệu lực.
- Kết quả kiểm thử endpoint theo người gọi và thao tác.
- Kết quả scrape/export, truy vấn, dashboard và cảnh báo quan trọng.
- Khác biệt đã chấp nhận, giới hạn kiểm chứng và cách khôi phục đã xác minh.

## 12. Tự thực hành

1. Endpoint prometheus trả 200 sau nâng cấp nhưng dashboard không còn dữ liệu. Liệt kê những chặng cần kiểm tra trước khi kết luận endpoint bị lỗi.
2. Một ứng dụng từ Boot 3.3 sang 3.4 dùng loggers để đọc và đổi mức log. Giải thích vì sao thay enabled=true bằng access=read-only không giữ nguyên cả hai khả năng.
3. Thêm phép thử prometheus:anonymous vào chương trình Java. Chọn tập kết quả theo policy của bạn và xác minh bản ứng viên mở ngoài dự kiến bị phát hiện.
4. Dependency trong build.gradle không ghi phiên bản nhưng runtime vẫn dùng một bản Micrometer cũ. Dùng dependencyInsight để xác định những loại nguyên nhân cần điều tra.
5. Kể một thay đổi cấu hình hoặc bên tiêu thụ phải được xét khi khôi phục artifact cũ; giải thích vì sao chỉ giữ JAR cũ chưa đủ.

Rà soát đạt mục tiêu khi bạn giải thích được mỗi thay đổi quan trọng đến từ đâu, tác động đến ai và đã được kiểm chứng bằng hợp đồng vận hành nào.
