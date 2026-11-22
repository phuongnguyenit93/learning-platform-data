# Kiểm chứng giá trị thực tế trước và sau refresh

Một thao tác refresh chỉ có ý nghĩa khi ứng dụng thực sự sử dụng cấu hình mới. Trong Spring Cloud, việc thấy giá trị mới ở Config Server hoặc gọi thành công endpoint refresh chưa đủ để kết luận một request đang chạy đã dùng giá trị mới. Cần kiểm tra theo từng tầng: **nguồn cấu hình**, **Environment của tiến trình**, **bean đã bind hoặc được tạo**, và **hành vi thực tế của thành phần tiêu thụ cấu hình**.

Bài học này trình bày một quy trình kiểm chứng có thể lặp lại trước và sau refresh. Ví dụ xuyên suốt là `order-service` đổi endpoint của `catalog-service` từ revision cũ sang revision mới. Ta sẽ xác định mỗi tầng cần quan sát gì, dùng API/Actuator nào, kiểm thử ra sao và xử lý thế nào khi các tầng không đồng nhất.

## 1. Điều gì cần được chứng minh?

Giả sử ban đầu cấu hình có:

```yaml
catalog:
  api:
    base-url: https://catalog-v1.internal
    timeout: 2s
    revision: catalog-config-17
```

Sau khi thay đổi nguồn cấu hình:

```yaml
catalog:
  api:
    base-url: https://catalog-v2.internal
    timeout: 3s
    revision: catalog-config-18
```

Mục tiêu không chỉ là chứng minh revision 18 đã được lưu. Cần chứng minh tiến trình đã nạp revision đó, bean dùng giá trị tương ứng và request tiếp theo thực sự đi tới endpoint v2.

| Tầng | Câu hỏi cần trả lời | Bằng chứng phù hợp |
| --- | --- | --- |
| Nguồn cấu hình | Revision mới đã được lưu và nguồn đang phục vụ revision nào? | Commit ID, label/version, response từ Config Server hoặc metadata nguồn |
| Environment | Property hiệu lực trong JVM hiện tại là gì? | `Environment.getProperty`, PropertySource/origin hoặc Actuator `env` |
| Bean cấu hình | Object `@ConfigurationProperties` đang giữ giá trị nào? | Đọc bean qua getter hoặc Actuator `configprops` |
| Bean/resource tiêu thụ | Client/policy đã được rebind hoặc tạo lại chưa? | Giá trị an toàn từ bean, generation ID, lifecycle log |
| Hành vi thực tế | Request sau refresh dùng endpoint/revision nào? | Request log ở dịch vụ đích, mock server, trace hoặc metric có nhãn an toàn |

Không nên suy luận một tầng từ bằng chứng của tầng khác. Ví dụ, Config Server trả revision mới không chứng minh mọi replica đã nạp; Environment trả URL mới không chứng minh HTTP client đã được tạo lại.

## 2. Thiết lập một dấu mốc không nhạy cảm

Để quan sát refresh, nên đưa vào cấu hình một giá trị nhận diện revision không chứa bí mật. Ví dụ:

```yaml
catalog:
  api:
    base-url: https://catalog-v1.internal
    timeout: 2s
    revision: catalog-config-17
```

Property `catalog.api.revision` là nhãn kiểm thử/quan sát, giúp đối chiếu trạng thái các tầng. Nó không thay thế version của Git hay Config Server; chỉ là một dấu mốc được phát hành cùng bộ cấu hình.

Không dùng API key, mật khẩu, token hoặc secret làm dấu mốc. Các giá trị này không nên được ghi vào log, trace, metric label hay endpoint chẩn đoán.

Một bộ cấu hình tốt có thể có:
- `revision`: mã phát hành cấu hình không nhạy cảm.
- `base-url`: endpoint đích.
- `timeout`: giá trị vận hành có thể quan sát.
- Một số feature flag không nhạy cảm để kiểm tra binding.

## 3. Kiểm tra nguồn cấu hình trước khi refresh

Nếu dùng Spring Cloud Config, trước hết xác nhận Config Server đang phục vụ đúng application, profile và label/revision. Cần nhớ Config Server có thể đọc từ Git, filesystem hoặc backend khác; trạng thái commit và trạng thái response của server là hai bằng chứng riêng.

Quy trình kiểm tra nguồn:

1. Xác định application name, profile và label mà client yêu cầu.
2. Kiểm tra revision/commit được triển khai ở backend.
3. Truy vấn Config Server bằng cùng application/profile/label như client.
4. Đối chiếu `catalog.api.revision`, `base-url` và `timeout` trong response.
5. Ghi lại thời điểm, revision và môi trường đang kiểm tra.

Ví dụ, với Config Server có endpoint mặc định, request có dạng:

```text
GET http://config-server:8888/order-service/prod
```

Đường dẫn thực tế có thể thay đổi theo context path, profile, label và cách bảo vệ server. Khi gọi endpoint, không đưa credential vào lịch sử terminal hoặc log chia sẻ.

**Bằng chứng đạt:** nguồn trả về `catalog-config-18` cùng endpoint v2. Nếu Config Server vẫn trả revision 17, hãy xử lý backend, label, cache hoặc repository refresh trước khi kiểm tra client.

## 4. Kiểm tra Environment trong từng tiến trình

Sau khi client thực hiện cơ chế nạp/refresh, đọc giá trị hiệu lực từ `Environment` của chính instance cần kiểm chứng.

Ví dụ một component chẩn đoán chỉ trả về các property không nhạy cảm:

```java
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CatalogEnvironmentSnapshot {
    private final Environment environment;

    public CatalogEnvironmentSnapshot(Environment environment) {
        this.environment = environment;
    }

    public Snapshot current() {
        return new Snapshot(
                environment.getProperty("catalog.api.revision"),
                environment.getProperty("catalog.api.base-url"),
                environment.getProperty(
                        "catalog.api.timeout", Duration.class)
        );
    }

    public record Snapshot(
            String revision,
            String baseUrl,
            Duration timeout
    ) {}
}
```

Đây là ví dụ dùng Java hiện đại; nếu dự án chưa hỗ trợ record, thay bằng class DTO thông thường. Chỉ expose snapshot qua kênh quản trị được bảo vệ, hoặc dùng nó trong test/log nội bộ có kiểm soát.

Trước refresh, snapshot dự kiến là revision 17, URL v1, timeout 2 giây. Sau khi Environment được cập nhật, snapshot phải cho thấy revision 18, URL v2 và timeout 3 giây.

### 4.1. Giá trị hiệu lực phụ thuộc PropertySource precedence

Nếu Config Client đã nạp revision 18 nhưng một PropertySource có ưu tiên cao hơn vẫn khai báo URL v1, `Environment.getProperty` có thể tiếp tục trả URL v1. Khi đó không phải Config Server không cập nhật; có thể nguồn ghi đè local đang thắng.

Khi cần tìm nguyên nhân, kiểm tra:
- Profile đang active.
- Biến môi trường và JVM system properties.
- Command-line arguments.
- File cấu hình local/ngoài.
- PropertySource từ Config Client.
- Thứ tự các nguồn và origin của key.

Không chỉ nhìn nội dung file YAML. Hãy đọc giá trị **hiệu lực** từ Environment của instance.

## 5. Kiểm tra bean @ConfigurationProperties

Environment mới không đồng nghĩa bean cấu hình đã được cập nhật. Tạo một bean cấu hình có kiểu dữ liệu và đọc trực tiếp nó để xác nhận.

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.api")
public class CatalogApiProperties {
    private String baseUrl;
    private Duration timeout = Duration.ofSeconds(2);
    private String revision;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public String getRevision() {
        return revision;
    }

    public void setRevision(String revision) {
        this.revision = revision;
    }
}
```

Đăng ký bean bằng `@ConfigurationPropertiesScan` trên class ứng dụng hoặc `@EnableConfigurationProperties(CatalogApiProperties.class)` trên một class cấu hình.

Component kiểm tra bean:

```java
import org.springframework.stereotype.Component;

@Component
public class CatalogPropertiesSnapshot {
    private final CatalogApiProperties properties;

    public CatalogPropertiesSnapshot(CatalogApiProperties properties) {
        this.properties = properties;
    }

    public CatalogApiProperties getProperties() {
        return properties;
    }
}
```

Trong production, nên trả một DTO snapshot có trường được chọn thay vì expose trực tiếp object cấu hình, nhất là khi nhóm property có thể chứa credential hoặc secret.

### 5.1. Rebind bean cấu hình

Trong các ứng dụng tích hợp Spring Cloud Context, thay đổi Environment có thể phát `EnvironmentChangeEvent`; cơ chế rebinder có thể bind lại các bean `@ConfigurationProperties` được quản lý theo quy tắc của phiên bản. Hành vi cụ thể phụ thuộc release train, cách đăng ký bean và cấu hình đang dùng.

Đừng kết luận rebind đã thành công chỉ vì event được phát. Hãy đọc trực tiếp getter của bean sau refresh. Nếu Environment đã có giá trị mới nhưng bean vẫn có giá trị cũ, cần kiểm tra rebinder, registration, scope và loại bean.

### 5.2. Phân biệt bean mutable và immutable

Một class cấu hình JavaBean với setter có thể được bind lại theo cơ chế rebinder phù hợp. Constructor-bound object/record và các kiểu bean khác có thể có hành vi khác theo phiên bản Spring Boot/Spring Cloud. Khi cần thay đổi runtime, xác minh rõ integration có hỗ trợ rebind kiểu object đó hay không; nếu không, cân nhắc tạo lại bean qua refresh scope hoặc dùng cơ chế cập nhật riêng.

## 6. Kiểm tra bean/resource thực sự tiêu thụ cấu hình

Một HTTP client có thể được tạo một lần với URL và timeout ở thời điểm khởi tạo. Dù Environment và `CatalogApiProperties` đã mới, client vẫn có thể giữ endpoint cũ.

Ví dụ target được tạo từ properties:

```java
import java.time.Duration;

public class CatalogHttpClient {
    private final String baseUrl;
    private final Duration timeout;
    private final String configRevision;
    private final String generationId;

    public CatalogHttpClient(
            String baseUrl,
            Duration timeout,
            String configRevision,
            String generationId) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
        this.configRevision = configRevision;
        this.generationId = generationId;
    }

    public String baseUrl() {
        return baseUrl;
    }

    public Duration timeout() {
        return timeout;
    }

    public String configRevision() {
        return configRevision;
    }

    public String generationId() {
        return generationId;
    }

    public String fetchCatalog() {
        // Thực hiện HTTP request với baseUrl và timeout hiện tại.
        return "request via " + baseUrl + " at " + configRevision;
    }
}
```

Nếu bean này là singleton thông thường, factory method không chạy lại chỉ vì Environment thay đổi. Cần xác định client được:
- Reconfigure qua API runtime của chính thư viện.
- Rebind nếu bản thân bean có thể nhận cấu hình mới.
- Tạo lại qua `@RefreshScope`.
- Hoặc restart/redeploy nếu tài nguyên không hỗ trợ thay đổi an toàn.

### 6.1. Kiểm tra target qua proxy

Với bean refresh-scoped, consumer giữ scoped proxy. Có thể thêm một generation ID không nhạy cảm vào target để xác nhận target đã được tạo lại:

```java
import java.time.Duration;
import java.util.UUID;

import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    @RefreshScope
    CatalogHttpClient catalogHttpClient(CatalogApiProperties properties) {
        return new CatalogHttpClient(
                properties.getBaseUrl(),
                properties.getTimeout(),
                properties.getRevision(),
                UUID.randomUUID().toString()
        );
    }
}
```

Để xác minh target mới, có thể thêm một `generationId` được tạo trong factory method hoặc một bộ đếm riêng theo context. Khi gọi qua proxy trước refresh, ghi lại generation A. Sau refresh, lần gọi tiếp theo qua proxy phải cho generation B khác A và revision 18.

Generation ID chỉ phục vụ quan sát; không dùng nó làm khóa nghiệp vụ hay định danh request phân tán.

## 7. Kiểm tra hành vi thực tế của request

Giá trị Environment, bean properties và target đều có thể đúng mà request vẫn thất bại vì DNS, network, TLS, authentication hoặc dịch vụ đích. Bằng chứng cuối cùng phải đến từ hành vi thực tế.

Một số cách xác minh:

- Dùng mock HTTP server trong integration test và kiểm tra request được gửi đến base URL/route mới.
- Ghi log an toàn ở dịch vụ đích với request ID, instance ID và revision cấu hình không nhạy cảm.
- Dùng distributed trace để thấy host/service instance đích sau refresh.
- Đo metric về request success/error và latency trước/sau.
- Dùng endpoint kiểm tra không gây side effect, tránh thử bằng thao tác thanh toán hoặc ghi dữ liệu thật.

Không log full Authorization header, cookie, token hoặc payload nhạy cảm. Nếu cần ghi nhận endpoint, loại bỏ query parameter có thể chứa token hoặc dữ liệu cá nhân.

### 7.1. Một request đang chạy có thể vẫn dùng target cũ

Refresh scope không chuyển một invocation đang thực thi sang target mới giữa chừng. Request đã bắt đầu có thể hoàn tất với target cũ; request tiếp theo qua proxy mới phân giải target hiện tại.

Vì vậy, khi kiểm chứng cần phân biệt:
- Request được gửi trước thời điểm refresh.
- Request đang chạy tại thời điểm invalidation.
- Request bắt đầu sau khi target mới được tạo.

Dùng correlation ID và timestamp để tránh kết luận sai khi log từ nhiều request xen kẽ.

## 8. Quy trình trước refresh và sau refresh

Nên chụp snapshot trước refresh theo cùng một bộ tiêu chí sẽ dùng sau refresh.

| Kiểm tra | Trước refresh | Sau refresh kỳ vọng |
| --- | --- | --- |
| Config Server/source revision | `catalog-config-17` | `catalog-config-18` |
| Environment revision | `catalog-config-17` | `catalog-config-18` |
| Environment base URL | `catalog-v1.internal` | `catalog-v2.internal` |
| Environment timeout | 2s | 3s |
| Properties bean | v1 / 2s | v2 / 3s |
| Client target revision | v1 | v2 |
| Target generation | A | B, khác A |
| Request thực tế | tới endpoint v1 | request mới tới endpoint v2 |
| Health/metrics | baseline | không tăng lỗi bất thường |

Một trình tự kiểm chứng có thể thực hiện:

1. Chọn một instance cụ thể và ghi nhận instance ID.
2. Ghi revision từ nguồn cấu hình.
3. Gọi snapshot Environment và bean properties.
4. Gửi một request kiểm tra và ghi target generation/đích thực tế.
5. Cập nhật nguồn lên revision mới.
6. Yêu cầu Config Client/ContextRefresher nạp lại theo cơ chế đang dùng.
7. Đọc lại Environment.
8. Đọc lại bean `@ConfigurationProperties`.
9. Refresh target nếu client dùng refresh scope.
10. Gửi request mới qua proxy và kiểm tra đích/generation.
11. Lặp lại trên các replica còn lại.
12. Đối chiếu lỗi, latency và revision cuối cùng.

Nếu một bước không đạt, dừng kết luận “refresh hoàn tất” và xác định tầng chưa đồng bộ.

## 9. Quan sát bằng Spring Boot Actuator

Actuator có thể hỗ trợ kiểm tra Environment và configuration properties trong runtime. Endpoint thường được dùng gồm:

| Endpoint | Thông tin hữu ích | Giới hạn |
| --- | --- | --- |
| `/actuator/env` | Environment và PropertySource; có thể truy vấn một property cụ thể | Giá trị nhạy cảm được che theo cấu hình; không chứng minh bean đã rebind |
| `/actuator/configprops` | Các bean `@ConfigurationProperties` và giá trị đã bind | Không chứng minh client/resource cuối cùng đã dùng giá trị |
| `/actuator/refresh` | Trong các tích hợp Spring Cloud hỗ trợ, kích hoạt refresh | Endpoint không phải bằng chứng duy nhất cho hành vi request; phụ thuộc phiên bản/cấu hình |
| `/actuator/health` | Trạng thái health/readiness theo indicator đã cấu hình | Health UP không chứng minh revision mới đã được áp dụng |

Các endpoint phải được expose có chủ đích. Với Actuator, chỉ expose những gì cần thiết qua `management.endpoints.web.exposure.include` và giới hạn truy cập bằng Spring Security/network policy.

Giá trị Environment/configuration có thể chứa thông tin nhạy cảm. Giữ masking mặc định hoặc chính sách `show-values` phù hợp; không bật hiển thị mọi giá trị trên production chỉ để debug. Không công khai endpoint refresh vì nó có thể thay đổi hành vi runtime.

### 9.1. Đọc Environment và configprops đúng cách

Nếu `/actuator/env/catalog.api.base-url` cho thấy URL v2, đó là bằng chứng Environment của instance đang báo giá trị v2. Tiếp theo, kiểm tra `/actuator/configprops` hoặc getter của bean để xác nhận object cấu hình.

Nếu hai endpoint cho kết quả khác nhau, hãy kiểm tra:
- Property source precedence.
- Bean có được đăng ký như configuration properties không.
- Bean có được rebind theo cơ chế hiện tại không.
- Endpoint đang đọc cùng application context/instance hay không.

### 9.2. Endpoint refresh không phải phép thử end-to-end

Một response thành công từ endpoint refresh chỉ xác nhận endpoint đã xử lý yêu cầu theo implementation. Nó không tự chứng minh Config Server có revision mới, mọi bean đã cập nhật, target mới đã tạo hoặc request đã đi tới endpoint mới.

Hãy dùng nó như một bước kích hoạt, rồi thực hiện các phép đọc/kiểm tra ở từng tầng.

## 10. Kiểm thử tự động theo từng tầng

Kiểm thử tốt nên cô lập các trách nhiệm để biết lỗi nằm ở đâu.

| Test | Thiết lập | Assertion |
| --- | --- | --- |
| Source integration test | Config Server/backend test chứa revision 18 | Client nhận đúng revision/response |
| Environment test | Nạp PropertySource revision 17 rồi thay bằng revision 18 | `Environment.getProperty` trả revision 18 |
| Binding test | Bean `@ConfigurationProperties` được rebind | Getter trả URL/timeout mới |
| RefreshScope test | Tạo target A, invalidate, gọi lại qua proxy | Target B được tạo với generation khác |
| HTTP integration test | Dùng mock server v1/v2 | Request sau refresh tới mock server v2 |
| Multi-instance test | Hai hoặc nhiều app instance | Mỗi instance báo cùng revision sau khi nhận trigger |

### 10.1. Test Environment với MapPropertySource có thể thay đổi

Ví dụ này chỉ kiểm tra Environment, không thay thế integration test Config Client:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

class CatalogEnvironmentTest {

    @Test
    void readsNewValueAfterSourceChanges() {
        Map<String, Object> values = new ConcurrentHashMap<>();
        values.put("catalog.api.revision", "catalog-config-17");

        StandardEnvironment environment = new StandardEnvironment();
        environment.getPropertySources().addFirst(
                new MapPropertySource("testCatalog", values)
        );

        assertThat(environment.getProperty("catalog.api.revision"))
                .isEqualTo("catalog-config-17");

        values.put("catalog.api.revision", "catalog-config-18");

        assertThat(environment.getProperty("catalog.api.revision"))
                .isEqualTo("catalog-config-18");
    }
}
```

Map mutable giúp minh họa việc lần tra cứu sau nhìn thấy giá trị mới. Trong production, Config Client có thể thay PropertySource hoặc tạo lại cấu trúc Environment theo cơ chế riêng; không dùng việc sửa map chia sẻ như một giải pháp refresh thay thế.

### 10.2. Test bean target generation

Một test refresh scope nên:
1. Gọi bean qua proxy và ghi generation đầu.
2. Thay đổi cấu hình trong nguồn test.
3. Cập nhật/rebind dữ liệu cấu hình theo integration đang kiểm thử.
4. Gọi `refresh("catalogHttpClient")` hoặc cơ chế refresh tương ứng.
5. Gọi proxy lần nữa.
6. Xác nhận generation mới khác generation cũ và revision target là revision mới.

Nếu chỉ gọi refresh scope mà không cập nhật Environment/properties trước, test có thể tạo target mới nhưng vẫn dùng giá trị cũ. Đây là một test hữu ích để chứng minh hai thao tác độc lập.

### 10.3. Test HTTP để xác minh endpoint thực tế

Dùng mock server có thể xác nhận request sau refresh đi đến server v2. Một kịch bản:
- Mock server v1 trả marker `server-v1`.
- Mock server v2 trả marker `server-v2`.
- Khởi tạo target với URL v1 và gửi request.
- Cập nhật property sang URL v2.
- Chạy quy trình rebind/refresh.
- Gửi request mới qua proxy.
- Xác nhận response đến từ mock server v2.

Không chỉ assert bean field bằng v2; hãy assert request thực sự được nhận ở mock server v2. Đây là bằng chứng ở tầng tiêu thụ.

## 11. Kiểm chứng trên nhiều replica

Mỗi replica có Environment và bean riêng. Vì vậy, cần ghi nhận trạng thái theo instance ID, không gộp thành một kết quả duy nhất của service.

Ví dụ bảng theo dõi:

| Instance | Environment revision | Properties revision | Client target revision | Request smoke test |
| --- | --- | --- | --- | --- |
| order-7f8a | 18 | 18 | 18 | v2 PASS |
| order-91bc | 18 | 18 | 17 | v1 FAIL |
| order-a2de | 18 | 18 | 18 | v2 PASS |

Trong ví dụ, instance `order-91bc` đã cập nhật Environment và bean properties nhưng client target vẫn dùng revision 17. Đây là dấu hiệu target chưa được invalidated, consumer đang giữ reference cũ hoặc client được tạo ở nơi khác.

Có thể dùng Spring Cloud Bus hoặc orchestration để phát trigger tới nhiều instance, nhưng phải kiểm tra từng instance đã nhận và áp dụng revision mới. Event đã được publish không chứng minh mọi consumer đã xử lý thành công.

## 12. Rollback và phục hồi khi refresh không đồng nhất

Nếu revision mới gây lỗi, cần có đường quay về revision đã biết là hoạt động tốt. Quy trình rollback cũng phải kiểm tra đủ các tầng:
1. Đưa nguồn cấu hình về revision trước.
2. Xác nhận Config Server phục vụ revision rollback.
3. Yêu cầu client tải lại.
4. Xác nhận Environment của từng instance.
5. Rebind hoặc refresh target.
6. Gửi request kiểm tra và xác nhận endpoint cũ hoạt động.
7. Ghi lại instance chưa rollback thành công.

Không chỉ đổi lại file ở Git rồi coi như rollback hoàn tất. Một instance có thể vẫn giữ PropertySource hoặc target cũ của revision lỗi. Nếu không thể refresh an toàn, dùng rolling restart/redeploy theo kế hoạch.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Tầng có thể gặp lỗi | Hướng kiểm tra |
| --- | --- | --- |
| Config Server vẫn trả revision cũ | Nguồn/backend | Kiểm tra commit, label, cache và application/profile |
| Config Server trả revision mới nhưng Environment cũ | Nạp cấu hình/client | Kiểm tra refresh trigger, Config Client, kết nối và PropertySource |
| Environment mới nhưng properties bean cũ | Binding/rebinder | Kiểm tra đăng ký configuration properties và rebinding |
| Properties bean mới nhưng client target cũ | Bean/resource | Kiểm tra refresh scope, proxy và reference target |
| Target revision mới nhưng request vẫn tới host cũ | Hành vi tiêu thụ/network | Kiểm tra client khác, DNS, proxy, connection pool và request log |
| Một số replica cũ, một số replica mới | Phân phối trigger | Kiểm tra event/bus, từng instance ID và revision |
| Endpoint refresh trả thành công nhưng không đổi | Sai tầng kỳ vọng hoặc nguồn không đổi | Đọc lại source, Environment, bean và target theo thứ tự |
| Request đầu sau refresh lỗi | Lazy target creation | Kiểm tra lỗi tạo target, property bắt buộc và kết nối endpoint mới |
| Actuator hiển thị giá trị bị che | Chính sách bảo mật | Dùng snapshot không nhạy cảm hoặc test nội bộ; không mở secret trên production |

Một nguyên tắc hiệu quả là tìm **điểm đầu tiên mà giá trị khác với revision mong đợi**. Nếu source đúng nhưng Environment sai, không cần debug HTTP client trước. Nếu Environment và bean đúng nhưng target sai, tập trung vào lifecycle/rebind. Nếu mọi giá trị đúng nhưng request thất bại, chuyển sang network và dịch vụ đích.

## 14. Checklist kiểm chứng trước khi công bố refresh thành công

- [ ] Đã xác định đúng application, profile, label và instance.
- [ ] Nguồn cấu hình đang phục vụ revision mới.
- [ ] Environment của instance có giá trị hiệu lực mới.
- [ ] PropertySource precedence không ghi đè giá trị mong muốn.
- [ ] Bean `@ConfigurationProperties` đã được rebind hoặc tạo lại.
- [ ] Bean/resource tiêu thụ đã dùng revision mới.
- [ ] Request mới qua đường thực tế tới đúng endpoint/instance.
- [ ] Target cũ đã giải phóng tài nguyên nếu cần.
- [ ] Các replica đều báo revision mong muốn.
- [ ] Health, lỗi và latency sau refresh vẫn trong giới hạn.
- [ ] Có thể rollback nếu một bước không đạt.
- [ ] Không có secret trong log, trace, metric hoặc snapshot.

Checklist này dùng cho vận hành và review; không thay thế test tự động hoặc chính sách phê duyệt triển khai của tổ chức.

## Ghi nhớ

Muốn chứng minh refresh có hiệu lực, hãy kiểm tra từ nguồn đến hành vi tiêu thụ: **revision ở nguồn → giá trị hiệu lực trong Environment → object cấu hình → target/client → request thực tế**. Mỗi tầng cần một bằng chứng riêng. `ContextRefresher`, `EnvironmentChangeEvent`, rebinder và `RefreshScope` hỗ trợ các bước cập nhật, nhưng không thay thế việc đọc lại giá trị, kiểm tra từng replica và gửi request xác minh. Chỉ kết luận refresh thành công khi instance đã áp dụng đúng revision và thành phần thực sự xử lý request đang dùng cấu hình mới.
