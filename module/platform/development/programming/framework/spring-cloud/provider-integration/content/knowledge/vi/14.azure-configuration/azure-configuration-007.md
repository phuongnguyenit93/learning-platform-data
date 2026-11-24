# Làm mới cấu hình, bộ nhớ đệm và xoay vòng bí mật

Trong một ứng dụng Spring Boot chạy trên Azure, cấu hình và bí mật thường được tải lúc khởi động rồi giữ trong bộ nhớ để phục vụ request. Cách này giảm độ trễ và số lần gọi dịch vụ, nhưng đặt ra ba câu hỏi vận hành: **làm thế nào để nhận cấu hình mới**, **cache nằm ở đâu và được cập nhật ra sao**, và **làm sao thay secret để các client đang chạy không tiếp tục dùng credential cũ**.

Spring Cloud Azure kết hợp với **Azure App Configuration** và **Azure Key Vault** cung cấp các cơ chế khác nhau cho từng loại dữ liệu. App Configuration hỗ trợ refresh theo polling, theo request hoặc chủ động; Key Vault PropertySource có chu kỳ refresh riêng; Key Vault reference cần được resolve lại vì App Configuration không biết secret phía Key Vault đã đổi. Sau cùng, các bean, HTTP client và connection pool trong ứng dụng vẫn cần lifecycle phù hợp để dùng giá trị mới.

Bài học thuộc chương **Cấu hình Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud, bao gồm danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và so sánh cloud provider. Mục tiêu ở đây là thiết kế được **một quy trình refresh và secret rotation có thể quan sát, kiểm thử và rollback**.

## 1. Mục tiêu học tập và tình huống xuyên suốt

Sau bài này, bạn cần làm được:

1. Phân biệt refresh cấu hình App Configuration với refresh trực tiếp Key Vault PropertySource.
2. Cấu hình polling, sentinel trigger, manual refresh và request-based refresh trong Spring.
3. Xác định cache nằm ở provider, Spring bean hay client nghiệp vụ.
4. Giải thích vì sao thay secret trong Key Vault không tự động làm App Configuration phát hiện thay đổi.
5. Thiết kế URI có version/không version, cache TTL và chu trình rotation.
6. Triển khai rotation có overlap credential, xác minh mọi instance và thu hồi credential cũ đúng thời điểm.
7. Kiểm thử refresh và rotation trong môi trường dev mà không làm thay đổi vault production.

Giả sử `checkout-service` có:

- `payments.timeout` trong Azure App Configuration, có thể thay đổi theo môi trường.
- `payments.api-token` là Key Vault reference trỏ tới secret `payments-api-token`.
- `PaymentGatewayClient` được tạo lúc Spring khởi động và giữ token trong bộ nhớ để gọi đối tác.
- 4 instance của ứng dụng chạy sau load balancer.

Khi timeout đổi, ta muốn ứng dụng nhận giá trị mới mà không cần restart. Khi token được rotate, ta muốn các instance lần lượt dùng token mới, xác minh giao dịch thành công rồi mới thu hồi token cũ.

~~~mermaid
flowchart TD
    A["Azure App Configuration"] --> B["Spring Cloud Azure provider"]
    K["Azure Key Vault"] -->|Secret value| B
    B --> C["Spring Environment / PropertySource"]
    C --> D["ConfigurationProperties / RefreshScope"]
    D --> E["HTTP client / DataSource / service"]
    F["Refresh trigger / interval"] --> B
    G["Rotation workflow"] --> K
    G --> F
~~~

**Nguyên tắc cốt lõi:** tải lại giá trị từ Azure và thay giá trị mà client đang dùng là **hai bước riêng**. Hoàn tất bước đầu chưa chứng minh bước thứ hai đã xảy ra.

## 2. Phân biệt dữ liệu và vòng đời

| Loại dữ liệu | Nguồn | Cách refresh chính | Ví dụ |
| --- | --- | --- | --- |
| Cấu hình thông thường | App Configuration key-value | Monitoring/polling, manual refresh, request-based refresh | Timeout, retry, endpoint công khai |
| Feature flag | App Configuration Feature Manager | Monitoring và feature-flag refresh interval | Bật checkout v2 |
| Bí mật trực tiếp | Key Vault Secrets PropertySource | `refresh-interval` của từng vault property source | Password, API token |
| Bí mật được tham chiếu | App Configuration Key Vault reference | Resolve lại reference qua App Configuration forced refresh hoặc khi reference thay đổi | `payments.api-token` |

Mỗi dịch vụ có cơ chế cache và thông báo thay đổi riêng:

- **App Configuration** biết khi key-value hoặc reference của nó đổi ETag.
- **Key Vault** biết khi secret có version mới, nhưng App Configuration không tự nhận sự kiện đó chỉ vì URI reference vẫn giữ nguyên.
- **Spring** có thể làm mới property và tái tạo một số bean.
- **HTTP client, pool kết nối hoặc biến `String` được giữ trong field** có thể vẫn giữ credential cũ.

Đừng dùng một chu kỳ refresh duy nhất cho tất cả loại dữ liệu mà không hiểu cơ chế nào đang theo dõi thay đổi.

## 3. Làm mới key-value từ Azure App Configuration

### 3.1. Polling và monitoring

App Configuration provider hỗ trợ **pull-based refresh**. Ứng dụng kiểm tra xem các key được theo dõi có thay đổi không; nếu phát hiện thay đổi, provider tải lại cấu hình và phát sự kiện refresh của Spring.

Ví dụ cấu hình:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            monitoring:
              enabled: true
              refresh-interval: 30s
              triggers:
                - key: /application/config.refresh-sentinel
                  label: prod
~~~

Trong App Configuration, tạo key `/application/config.refresh-sentinel` với label `prod`. Đây là **sentinel key**. Khi cập nhật một nhóm cấu hình, hãy cập nhật các key cần thay đổi trước, rồi đổi sentinel sau cùng. Provider theo dõi ETag của sentinel; khi phát hiện thay đổi, nó refresh các cấu hình đã chọn trong store.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `monitoring.enabled` | Bật cơ chế theo dõi thay đổi |
| `monitoring.refresh-interval` | Khoảng thời gian tối thiểu giữa các lần kiểm tra |
| `monitoring.triggers[].key` | Key được theo dõi qua ETag |
| `monitoring.triggers[].label` | Label của sentinel; phải khớp bản ghi được tạo trong store |

Theo tài liệu Spring Cloud Azure, khoảng refresh mặc định là **30 giây** và có thể cấu hình lớn hơn 1 giây. Đây là khoảng tối thiểu trước khi một lần kiểm tra tiếp theo được phép diễn ra, không phải cam kết rằng mọi instance đều cập nhật đúng sau 30 giây.

Nếu không khai báo trigger, một số phiên bản provider hỗ trợ theo dõi collection đã chọn; để quy trình phát hành rõ ràng và tránh refresh khi key không liên quan thay đổi, nên khai báo sentinel cụ thể và kiểm tra hành vi theo phiên bản thư viện đang dùng.

### 3.2. Tại sao dùng sentinel?

Giả sử một lần phát hành cập nhật 6 key: timeout, retry, endpoint, giới hạn giao dịch và hai tham số khác. Nếu provider theo dõi mọi key, mỗi lần cập nhật có thể tạo nhiều lần refresh trong khi dữ liệu mới chưa được ghi đủ.

Sentinel tạo ra **một điểm xác nhận**:

1. Cập nhật toàn bộ key cấu hình.
2. Xác minh các key đã lưu đúng.
3. Cập nhật sentinel.
4. Các instance phát hiện ETag mới và tải lại cấu hình.

Sentinel không tạo giao dịch nguyên tử cho nhiều key. Nó chỉ giúp ứng dụng biết **thời điểm nhóm cấu hình được công bố hoàn tất**. Nếu cần snapshot bất biến cho release, hãy đánh giá App Configuration snapshots.

### 3.3. Request-based refresh với thư viện Web

Khi dùng thư viện `spring-cloud-azure-appconfiguration-config-web` (hoặc biến thể Web được BOM của dự án hỗ trợ), ứng dụng Spring MVC có thể tự kiểm tra refresh khi nhận sự kiện `ServletRequestHandledEvent`.

Cấu hình monitoring vẫn cần bật:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled=true
spring.cloud.azure.appconfiguration.stores[0].monitoring.triggers[0].key=/application/config.refresh-sentinel
spring.cloud.azure.appconfiguration.stores[0].monitoring.triggers[0].label=prod
~~~

Cơ chế này **gắn với hoạt động request**. Nếu ứng dụng không nhận servlet request thì cache hết hạn cũng không tự bảo đảm refresh được thực thi. Trong hướng dẫn thực hành, sau khi chờ interval, request đầu tiên có thể kích hoạt kiểm tra; request tiếp theo mới quan sát giá trị đã refresh tùy bean scope.

Không dùng request của người dùng cuối làm cơ chế bảo đảm một thay đổi bảo mật phải áp dụng tức thì. Với tình huống nhạy cảm, cần quy trình refresh/restart có kiểm soát và kiểm tra trạng thái từng instance.

### 3.4. Manual refresh

Cả thư viện core và Web đều hỗ trợ gọi chủ động qua bean `AppConfigurationRefresh`. Ví dụ trong một Spring MVC controller nội bộ:

~~~java
package com.example.checkout;

import com.azure.spring.cloud.appconfiguration.config.AppConfigurationRefresh;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InternalConfigurationRefreshController {
    private final AppConfigurationRefresh refresh;

    InternalConfigurationRefreshController(AppConfigurationRefresh refresh) {
        this.refresh = refresh;
    }

    @PostMapping("/internal/configuration/refresh")
    boolean refreshConfiguration() {
        // Ví dụ imperative MVC: gọi trên request thread, không phải WebFlux event loop.
        return Boolean.TRUE.equals(refresh.refreshConfigurations().block());
    }
}
~~~

`refreshConfigurations()` trả về một reactive result cho biết có refresh được kích hoạt hay không. Giá trị `false` không nhất thiết là lỗi: có thể interval chưa hết, không phát hiện thay đổi, hoặc một thread khác đang kiểm tra.

Endpoint minh họa phải được **bảo vệ bằng authorization quản trị**, giới hạn mạng và audit. Không mở endpoint refresh công khai. Với ứng dụng WebFlux/reactive, không gọi `.block()` trên event loop; dùng reactive composition hoặc cơ chế thực thi thích hợp.

### 3.5. Manual và automated khác nhau ở đâu?

| Cơ chế | Ai kích hoạt kiểm tra? | Khi phù hợp |
| --- | --- | --- |
| Poll + sentinel | Request/worker/manual gọi refresh sau interval | Muốn kiểm soát nhóm key cần theo dõi |
| Web automatic | Sự kiện servlet request sau interval | Ứng dụng Spring MVC có request đều |
| Manual `AppConfigurationRefresh` | Code hoặc tác vụ nội bộ | Console app, job, thao tác điều phối |
| Push/Event Grid webhook | Sự kiện Azure gọi endpoint | Chỉ cân nhắc khi cần và đã hiểu lifecycle; tài liệu hiện hành không còn khuyến nghị đây là phương án mặc định |

Tài liệu Microsoft đánh dấu push-based refresh là **không còn được khuyến nghị**, dù vẫn được hỗ trợ. Ưu tiên pull/monitoring hoặc manual refresh trước, trừ khi kiến trúc có lý do rõ ràng.

## 4. Spring cập nhật bean như thế nào sau refresh?

Khi provider nhận cấu hình mới, nó cập nhật Spring configuration system và phát sự kiện refresh. Tuy nhiên, **không phải mọi object Java tự thay đổi trạng thái**.

### 4.1. `@ConfigurationProperties`

Các bean được tạo từ `@ConfigurationProperties` được Spring Cloud Azure tích hợp vào refresh scope theo mặc định của thư viện. Khi refresh thành công, bean được tạo lại và bind với giá trị mới.

Ví dụ:

~~~java
package com.example.checkout;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payments")
public record PaymentSettings(Duration timeout, int maxRetries) {
}
~~~

Sau refresh, consumer truy cập proxy/bean theo cơ chế refresh scope sẽ nhận cấu hình mới. Nếu code sao chép `settings.timeout()` vào một field khác ở startup, field đó vẫn có thể giữ giá trị cũ.

### 4.2. `@RefreshScope` cho bean tạo client

Với bean tự tạo client từ token hoặc endpoint, đánh dấu bean cần tái tạo:

~~~java
package com.example.checkout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PaymentClientConfiguration {

    @Bean
    @RefreshScope
    PaymentGatewayClient paymentGatewayClient(
            @Value("${payments.api-token}") String token,
            @Value("${payments.base-url}") String baseUrl) {
        return new PaymentGatewayClient(baseUrl, token);
    }
}
~~~

Khi refresh scope được làm mới, bean `PaymentGatewayClient` được tạo lại với giá trị property mới. Ví dụ giả định class client là adapter của ứng dụng; trong dự án thật, hãy xác minh client/SDK hỗ trợ tạo mới và đóng tài nguyên cũ đúng cách.

**Đừng chỉ đánh dấu bean cấu hình mà quên client giữ secret.** Nếu một singleton tạo HTTP client ở constructor rồi giữ token trong interceptor, refresh một `PaymentSettings` bean không tự cập nhật interceptor đó. Có thể đặt client trong refresh scope, hoặc thiết kế credential provider có thể thay thế giá trị an toàn.

### 4.3. Bean scope không thay thế lifecycle của tài nguyên

| Thành phần | Sau khi property đổi | Việc cần làm |
| --- | --- | --- |
| `@ConfigurationProperties` bean | Có thể được refresh/rebind theo tích hợp | Consumer phải đọc bean/proxy mới |
| Bean `@RefreshScope` | Được đánh dấu stale và tạo lại khi truy cập | Đảm bảo khởi tạo client mới và đóng client cũ phù hợp |
| HTTP client giữ token | Có thể vẫn dùng token cũ nếu không được tái tạo | Rebuild client hoặc cập nhật credential provider |
| JDBC connection pool | Connection hiện hữu có thể tiếp tục dùng session cũ | Điều phối pool/reconnect; thử nghiệm với driver và DB |
| `String` được copy vào field singleton | Không tự đổi | Tránh cache thủ công hoặc thiết kế cập nhật rõ |
| Cache nghiệp vụ | Không tự biết cấu hình đã đổi | Evict/refresh theo phiên bản hoặc TTL |

## 5. Các lớp cache trong kiến trúc

Hãy hình dung một secret đi từ Key Vault tới request:

~~~text
Key Vault secret/version
        |
        v
Provider cache / Spring PropertySource
        |
        v
Spring Environment + RefreshScope
        |
        v
PaymentGatewayClient / connection pool
        |
        v
Cache riêng của nghiệp vụ (nếu có)
        |
        v
Request đang chạy
~~~

Mỗi lớp có lifecycle riêng. Nếu chỉ nhìn thấy property trong `Environment` đã đổi, bạn chưa biết client có đổi token hay không.

### 5.1. Cache ở provider

App Configuration client lưu cấu hình đã tải để không gọi Azure trên mỗi lần đọc property. Monitoring/refresh kiểm tra theo interval và tải lại khi có thay đổi.

Key Vault PropertySource trực tiếp cũng có cache riêng. Theo tài liệu Spring Cloud Azure, `refresh-interval` của từng property source mặc định là **30 phút**. Có thể cấu hình:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
              refresh-interval: 15m
~~~

Thuộc tính này chỉ dành cho **Key Vault PropertySource trực tiếp**. Nếu ứng dụng lấy secret qua **App Configuration Key Vault reference**, phải hiểu cơ chế forced refresh của App Configuration ở mục 6; không áp dụng `keyvault.secret.property-sources[].refresh-interval` cho reference mà ứng dụng không hề tải qua property source đó.

### 5.2. Cache trong client ứng dụng

HTTP client thường giữ token trong cấu hình interceptor hoặc connection object để giảm chi phí xử lý. Điều này tốt cho hiệu năng nhưng có nghĩa client có thể tiếp tục dùng token cũ sau khi provider cache đã thay đổi.

Không nên gọi Key Vault trên từng request chỉ để luôn lấy giá trị mới nhất. Cách đó làm tăng latency, phụ thuộc mạng và có nguy cơ throttling. Thay vào đó:

- Cache credential trong bộ nhớ ở phạm vi cần thiết.
- Refresh theo sự kiện/interval hoặc theo workflow rotation.
- Cập nhật client một cách nguyên tử hoặc thay instance có kiểm soát.
- Dùng retry/backoff cho lỗi tạm thời.
- Theo dõi tuổi của credential đang dùng và version đã nạp, nhưng **không ghi giá trị secret** vào log.

Microsoft khuyến nghị cache secret trong bộ nhớ và refresh khi secret rotate để giảm số lần gọi Key Vault và tránh throttling.

## 6. Làm mới Key Vault reference khi secret thay đổi

Đây là điểm đặc biệt cần nhớ khi kết hợp App Configuration và Key Vault.

### 6.1. Vì sao monitoring App Configuration không thấy secret đổi?

Giả sử App Configuration chứa:

| Key | Value |
| --- | --- |
| `/application/payments.api-token` | URI không version tới `payments-api-token` |

Secret trong Key Vault đổi từ version A sang version B, nhưng URI trong App Configuration **không đổi**. App Configuration không biết dữ liệu đằng sau URI đã đổi, vì vậy ETag của key reference vẫn có thể giữ nguyên. Một monitoring trigger chỉ kiểm tra ETag của App Configuration sẽ không phát hiện việc rotate secret.

**Giải pháp của Spring Cloud Azure:** cấu hình thuộc tính forced refresh toàn cục:

~~~properties
spring.cloud.azure.appconfiguration.refresh-interval=5m
~~~

Thuộc tính `spring.cloud.azure.appconfiguration.refresh-interval` đặt chu kỳ refresh toàn bộ cấu hình App Configuration. Khác với `stores[0].monitoring.refresh-interval`, nó **không kiểm tra watch keys**; mục đích của nó bao gồm làm mới Key Vault references vì App Configuration không thể biết secret ở Key Vault đã thay đổi.

| Thuộc tính | Phạm vi | Cơ chế |
| --- | --- | --- |
| `stores[0].monitoring.refresh-interval` | Monitoring của store | Sau interval, kiểm tra trigger/collection; nếu có thay đổi thì refresh |
| `spring.cloud.azure.appconfiguration.refresh-interval` | Forced client refresh toàn cục | Refresh cấu hình theo interval, không kiểm tra watch key |
| `keyvault.secret.property-sources[0].refresh-interval` | Key Vault PropertySource trực tiếp | Làm mới các secret mà PropertySource tải |

Không nhầm ba thuộc tính trên. Chúng quản lý **ba đường nạp dữ liệu khác nhau**.

### 6.2. Cấu hình đầy đủ cho Key Vault reference

Ví dụ `application.yml`:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        refresh-interval: 5m
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            monitoring:
              enabled: true
              refresh-interval: 30s
              triggers:
                - key: /application/config.refresh-sentinel
                  label: prod
~~~

- `monitoring.refresh-interval` phát hiện các thay đổi ở key-value/sentinel App Configuration.
- `appconfiguration.refresh-interval` định kỳ nạp lại toàn bộ cấu hình, bao gồm resolve Key Vault reference để lấy secret hiện hành.
- `5m` và `30s` chỉ là **giá trị minh họa**. Chọn chu kỳ theo mức độ nhạy cảm, tải, quota, số instance và khả năng refresh client.

Mỗi Key Vault reference được resolve sẽ tạo một lần pull secret tới Key Vault; Key Vault trả secret theo từng lần đọc. Nếu có nhiều reference, refresh quá ngắn có thể tăng số request và gặp throttling. Hãy chỉ tham chiếu secret thật sự cần thiết.

### 6.3. Nếu URI reference ghim version

Có hai tình huống:

| Reference URI | Khi secret tạo version mới |
| --- | --- |
| Không chứa version | Khi resolve lại, Key Vault có thể trả phiên bản hiện hành của secret theo URI |
| Có version cụ thể | Vẫn trả version đã ghim; muốn đổi phải cập nhật reference URI trong App Configuration |

Với URI ghim version, cập nhật reference ở App Configuration làm ETag thay đổi; monitoring trigger hoặc collection monitoring có thể phát hiện và nạp URI mới. Với URI không version, key App Configuration không đổi khi chỉ có secret đổi; forced refresh là cơ chế cần xem xét.

Dù dùng cách nào, sau khi provider resolve giá trị mới, cần bảo đảm bean/client được cập nhật và xác minh mọi instance đã dùng credential mới.

## 7. Chiến lược secret rotation

Rotation là thay credential cũ bằng credential mới và bảo đảm workload chuyển sang giá trị mới trước khi thu hồi credential cũ. **Tạo version mới trong Key Vault chỉ là một bước của rotation.**

### 7.1. Rotation một credential và hai credential

| Kiểu hệ thống đích | Mô hình rotation | Đặc điểm |
| --- | --- | --- |
| Chỉ chấp nhận một credential tại một thời điểm | Cần phối hợp thời gian thay đổi phía dịch vụ và ứng dụng | Có thể cần maintenance window hoặc chấp nhận một khoảng gián đoạn ngắn |
| Hỗ trợ đồng thời hai credential (primary/secondary) | Tạo credential mới ở slot chưa dùng, chuyển workload, rồi xoay slot còn lại | Có thể đạt gần zero downtime nếu các bước và client được điều phối đúng |

Ví dụ nhà cung cấp thanh toán hỗ trợ hai API key:

- Key A đang hoạt động; Key B là slot dự phòng.
- Tạo Key B mới và lưu vào Key Vault.
- Cập nhật reference/config để ứng dụng nạp Key B.
- Xác minh các instance và giao dịch thành công.
- Thu hồi Key A rồi mới dùng slot A cho lần rotation tiếp theo.

Không phải mọi dịch vụ đều hỗ trợ dual credential. Nếu chỉ có một password, hãy lập lịch đổi ở cả phía database và ứng dụng, chuẩn bị rollback và kiểm soát thời gian chuyển tiếp.

### 7.2. Quy trình rotation đề xuất

~~~mermaid
flowchart TD
    A["Tạo credential mới ở dịch vụ đích"] --> B["Lưu version mới vào Key Vault"]
    B --> C["Cập nhật reference nếu URI ghim version"]
    C --> D["Kích hoạt refresh / rolling restart"]
    D --> E["Tái tạo client và kiểm tra mọi instance"]
    E --> F{"Giao dịch và health check đạt?"}
    F -->|Chưa| G["Rollback về credential cũ"]
    G --> E
    F -->|Đạt| H["Thu hồi credential cũ"]
    H --> I["Ghi nhận version và hoàn tất rotation"]
~~~

Trình tự chi tiết:

1. **Chuẩn bị:** xác định owner, thời hạn credential, version đang sử dụng, số instance và khả năng dual credential.
2. **Tạo credential mới:** tạo ở dịch vụ đích trước (nếu dịch vụ yêu cầu), bảo đảm credential mới hợp lệ.
3. **Lưu vào Key Vault:** tạo version mới của secret; không đưa value vào pipeline log.
4. **Cập nhật reference:** nếu URI ghim version, thay URI ở App Configuration. Nếu URI không version, lên kế hoạch forced refresh hoặc trigger phù hợp.
5. **Làm mới ứng dụng:** gọi refresh/đợi interval hoặc rolling restart; tái tạo bean/client giữ token.
6. **Xác minh:** kiểm tra version/metadata không nhạy cảm, health, giao dịch thử và số lỗi xác thực ở tất cả instance.
7. **Thu hồi credential cũ:** chỉ sau khi xác nhận không còn workload dùng nó.
8. **Audit:** ghi lại thời gian, người thực hiện, version mới, kết quả và thời điểm thu hồi; không lưu plaintext secret.

### 7.3. Event Grid và tự động hóa

Key Vault có thể phát sự kiện vòng đời secret, ví dụ tạo version mới hoặc gần hết hạn. Có thể dùng **Event Grid** để chuyển sự kiện tới Azure Function, Logic App hoặc workflow vận hành.

Sự kiện **không tự cập nhật biến trong JVM**. Automation phải thực hiện hành động tiếp theo: cập nhật reference/sentinel, gọi một cơ chế refresh đã bảo vệ, hoặc điều phối rolling restart. Nếu sự kiện chỉ đến một instance, cần fan-out tới các instance khác hoặc để mỗi instance tự refresh theo lịch.

Đối với quy trình quan trọng, dùng Event Grid để **khởi động workflow**, còn việc chuyển client và xác minh vẫn phải có bước rõ ràng.

## 8. Refresh nhiều instance và tính nhất quán

Giả sử có 4 instance sau load balancer. Mỗi instance có cache riêng, timer/trigger riêng và các client riêng. Khi cấu hình thay đổi:

- Instance A có thể refresh trước; instance B chỉ refresh ở request tiếp theo.
- Một số request có thể được xử lý bằng client cũ trong giai đoạn chuyển.
- Nếu credential cũ đã bị thu hồi quá sớm, instance chưa cập nhật có thể nhận 401/403.
- Nếu request được retry sang instance khác, kết quả có thể khác nhau trong cửa sổ chuyển tiếp.

### 8.1. Thiết kế tương thích trong cửa sổ chuyển đổi

Với credential có thể overlap, duy trì credential cũ và mới cùng hợp lệ trong khoảng chuyển. Chỉ thu hồi cũ khi:

- Mọi instance đã nạp version mới.
- Các HTTP client/connection pool đã được tạo lại hoặc cập nhật.
- Không còn lỗi xác thực do credential cũ.
- Các request đang chạy đã hoàn tất hoặc hết thời gian tối đa cho phép.

Nếu không thể overlap, cần **rolling restart hoặc maintenance window** được điều phối với dịch vụ đích. Đừng thu hồi credential chỉ dựa vào việc một instance báo refresh thành công.

### 8.2. Tránh refresh đồng loạt

Nếu mọi instance refresh cùng thời điểm, số request Key Vault/App Configuration tăng đột biến. Cân nhắc:

- Dùng interval hợp lý và jitter nếu thư viện/cơ chế hỗ trợ.
- Hạn chế số Key Vault references và danh sách secret được tải.
- Retry với exponential backoff cho lỗi 429/5xx và timeout.
- Không đặt refresh interval cực ngắn chỉ để giảm thời gian rotation.
- Theo dõi request count, latency, lỗi xác thực và tuổi cache trên từng instance.

## 9. Lựa chọn TTL và chính sách cache

Không có một TTL phù hợp cho mọi loại dữ liệu. Chọn theo **tốc độ thay đổi, hậu quả khi dùng giá trị cũ, tải dịch vụ và khả năng rollback**.

| Dữ liệu | Hướng chọn TTL/refresh | Lý do |
| --- | --- | --- |
| Timeout/retry không nhạy cảm | Monitoring 30s hoặc dài hơn theo nhu cầu | Thay đổi thường không cần áp dụng tức thì |
| Feature flags | Feature flag refresh interval riêng | Quyết định rollout cần nhanh nhưng vẫn phải kiểm soát tải |
| Key Vault reference có URI không version | Forced refresh App Configuration theo chính sách rotation | App Configuration không tự nhận biết secret đổi |
| Key Vault PropertySource trực tiếp | Mặc định 30m hoặc cấu hình `refresh-interval` | Provider cache và làm mới các secret được chọn |
| Credential trong HTTP client | Cache theo lifecycle client; cập nhật khi rotation | Tránh truy cập Key Vault mỗi request |
| Credential trong connection pool | Phối hợp với pool/driver và thời gian sống connection | Property mới không thay session đã mở |

Một TTL ngắn làm secret cũ tồn tại trong cache ít lâu hơn, nhưng tăng số lần gọi dịch vụ. Một TTL dài giảm tải nhưng mở rộng cửa sổ dùng credential cũ. Đối với secret bị lộ hoặc cần thu hồi khẩn cấp, **không chờ TTL thông thường**; cần quy trình incident response để thu hồi credential và điều phối cập nhật ngay.

## 10. Kiểm thử refresh và rotation

### 10.1. Unit test không phụ thuộc Azure

Unit test cho logic đọc cấu hình nên dùng giá trị giả và không gọi App Configuration/Key Vault. Ví dụ dùng `MockEnvironment` và Spring Binder:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

class PaymentSettingsTest {
    @Test
    void bindsConfigurationValues() {
        var environment = new MockEnvironment()
                .withProperty("payments.timeout", "PT3S")
                .withProperty("payments.api-token", "test-token");

        PaymentSettings settings = Binder.get(environment)
                .bind("payments", Bindable.of(PaymentSettings.class))
                .orElseThrow();

        assertThat(settings.timeout()).isEqualTo(Duration.ofSeconds(3));
        assertThat(settings.toString()).doesNotContain("test-token");
    }
}
~~~

Test này kiểm tra binding và cách object tránh lộ secret; không chứng minh Azure refresh hoặc RBAC.

### 10.2. Kiểm thử App Configuration refresh trong môi trường dev

Với store và identity thử nghiệm:

1. Tạo `/application/payments.timeout` và sentinel `/application/config.refresh-sentinel` cùng label.
2. Khởi động ứng dụng với monitoring bật, ghi nhận timeout ban đầu.
3. Thay timeout ở portal, sau khi interval hết hãy gửi request hoặc gọi `AppConfigurationRefresh`.
4. Quan sát log refresh và kiểm tra `@ConfigurationProperties` nhận giá trị mới.
5. Kiểm tra bean `@RefreshScope` được tạo lại; xác minh client mới đang sử dụng giá trị mới.
6. Chạy với nhiều instance và quan sát độ trễ từng instance.

Không dùng secret thật trong log. Chỉ quan sát giá trị không nhạy cảm như timeout hoặc một version label do test thiết kế.

### 10.3. Kiểm thử Key Vault reference rotation

Trong vault dev:

1. Tạo secret `payments-api-token` version A với token giả.
2. Tạo reference App Configuration tới URI **không version**.
3. Khởi động ứng dụng, xác nhận client sandbox dùng token A.
4. Tạo version B và giữ A còn hiệu lực.
5. Chờ/cưỡng bức forced refresh App Configuration; kiểm tra property được resolve lại.
6. Tạo lại `PaymentGatewayClient` hoặc cập nhật credential provider.
7. Gửi giao dịch sandbox và xác minh tất cả instance dùng B.
8. Thu hồi A trong môi trường thử nghiệm và kiểm tra không có request nào còn phụ thuộc A.

Lặp lại với URI ghim version để xác minh rằng URI phải được cập nhật khi muốn chuyển version.

### 10.4. Ma trận tình huống cần có

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Sentinel không đổi | Không refresh dữ liệu do trigger |
| Sentinel đổi sau interval | Provider tải lại cấu hình được chọn |
| Manual refresh trước interval | Không bắt buộc tạo request kiểm tra mới |
| Secret đổi nhưng reference URI không đổi | Cần forced refresh/resolve lại theo chính sách |
| URI ghim version, secret có version mới | Vẫn dùng version cũ đến khi reference đổi |
| Property mới, client cũ chưa được tạo lại | Client có thể tiếp tục dùng credential cũ |
| Identity thiếu quyền Key Vault | Resolve reference thất bại; không fallback sang token production hard-code |
| Một instance chưa refresh | Credential cũ phải còn hiệu lực trong cửa sổ chuyển nếu hệ thống yêu cầu zero downtime |

## 11. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Thay key trong portal nhưng app không đổi | Monitoring chưa bật, interval chưa hết hoặc không có request/manual trigger | Kiểm tra `monitoring.enabled`, trigger và cách kích hoạt refresh |
| Chờ quá 30 giây nhưng Web app vẫn dùng config cũ | Không có servlet request để kích hoạt automatic refresh | Gửi request sau interval hoặc dùng manual refresh |
| `refreshConfigurations()` trả false | Chưa tới interval, không có thay đổi hoặc thread khác đang kiểm tra | Xem đây là trạng thái không refresh; không mặc định là lỗi |
| `@ConfigurationProperties` đổi nhưng HTTP client vẫn dùng config cũ | Client giữ bản sao token/timeout ở field | Dùng `@RefreshScope`, tái tạo client hoặc credential provider |
| Secret Key Vault mới nhưng Spring reference vẫn cũ | App Configuration không biết secret phía sau URI đã đổi | Cấu hình `spring.cloud.azure.appconfiguration.refresh-interval` |
| URI có version vẫn trả secret cũ | Reference ghim version | Cập nhật URI trong App Configuration |
| Key Vault trả 403 khi resolve | Identity thiếu `Key Vault Secrets User` hoặc access policy `Get` | Kiểm tra principal runtime và scope vault |
| App Configuration trả 403 | Thiếu `App Configuration Data Reader` | Kiểm tra role trên đúng store |
| 429 khi refresh | Quá nhiều reference/request hoặc refresh đồng loạt | Giảm số lần gọi, dùng cache, jitter/backoff và giới hạn secret |
| Restart app mới nhận secret | Bean/client giữ giá trị cũ hoặc provider không refresh | Thiết kế lifecycle và test refresh trước khi dựa vào rotation tự động |
| Một số instance dùng token cũ | Cache/refresh độc lập theo instance | Theo dõi từng instance, overlap credential, rolling refresh/restart |
| Log chứa secret | Log toàn bộ config object, exception hoặc HTTP header | Redact dữ liệu, giảm logging và kiểm tra telemetry |

## 12. Quy trình vận hành production

Một quy trình chuẩn có thể chia thành bốn giai đoạn:

**Trước rotation**

- Xác định owner, thời hạn credential, version đang sử dụng, số instance và khả năng dual credential.
- Xác nhận dịch vụ đích có hỗ trợ dual credential không.
- Xác định refresh interval, cơ chế manual/automatic và cách tái tạo client.
- Kiểm tra quyền đọc và giám sát trên Key Vault/App Configuration.

**Trong rotation**

- Tạo credential mới ở dịch vụ đích.
- Lưu version mới trong Key Vault.
- Cập nhật reference nếu URI ghim version, hoặc kích hoạt forced refresh nếu URI không version.
- Refresh từng instance hoặc rolling restart; kiểm tra client mới.

**Sau rotation**

- Xác minh mọi instance và giao dịch thử.
- Thu hồi credential cũ sau khi hết cửa sổ overlap.
- Kiểm tra log/audit và cập nhật hồ sơ rotation.

**Khi có sự cố hoặc nghi lộ secret**

- Thu hồi credential bị lộ ở dịch vụ đích theo quy trình incident.
- Không chờ cache TTL thông thường.
- Kích hoạt cập nhật khẩn cấp cho tất cả instance, restart nếu cần.
- Kiểm tra quyền, access log và dấu hiệu sử dụng bất thường.
- Ghi nhận nguyên nhân và bổ sung biện pháp phòng ngừa.

## 13. Bài tập áp dụng

Một `order-service` chạy 5 instance cần:

- `orders.timeout` trong App Configuration, thay đổi không cần restart.
- `orders.partner-token` là Key Vault reference tới secret versionless URI.
- HTTP client giữ token trong bộ nhớ.
- Nhà cung cấp hỗ trợ primary/secondary token.

**Nhiệm vụ:**

1. Bật monitoring và sentinel cho `orders.timeout`.
2. Chọn chu kỳ forced refresh để cập nhật Key Vault reference khi secret đổi.
3. Đánh dấu bean tạo HTTP client với `@RefreshScope` hoặc thiết kế credential provider có thể cập nhật.
4. Viết kế hoạch rotation primary/secondary, giữ hai token cùng hợp lệ trong cửa sổ chuyển.
5. Xác minh version mới được nạp và cả 5 instance dùng token mới trước khi thu hồi token cũ.

Câu hỏi tự đánh giá:

- Vì sao `monitoring.refresh-interval` không đủ để phát hiện một secret đổi phía sau URI không version?
- Khác nhau giữa `spring.cloud.azure.appconfiguration.refresh-interval` và `stores[0].monitoring.refresh-interval` là gì?
- Vì sao request đầu tiên sau interval có thể kích hoạt refresh nhưng vẫn đọc giá trị cũ?
- Khi nào `@RefreshScope` cần được đặt ở bean tạo client thay vì chỉ ở bean chứa properties?
- Vì sao cache secret trong bộ nhớ thường tốt hơn gọi Key Vault trên từng request?
- Khi nào phải dùng rolling restart hoặc maintenance window thay cho refresh tự động?

**Đáp án định hướng:** App Configuration không biết Key Vault secret đổi nếu reference/ETag không đổi; forced refresh toàn cục resolve lại reference, monitoring kiểm tra trigger; request kích hoạt refresh trước khi scope bean được tạo lại/đọc lần tiếp theo; client giữ secret cần được tái tạo; cache giảm latency và throttling; single-credential service có thể cần cửa sổ chuyển đổi có điều phối.

## 14. Nguồn tham khảo chính thức

- [Microsoft Learn – Use dynamic configuration in a Java Spring app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): polling, manual refresh, Web request-based refresh và `AppConfigurationRefresh`.
- [Microsoft Learn – Spring Cloud Azure App Configuration support](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/app-configuration-support): monitoring, sentinel, forced refresh, Key Vault references, feature flags và health.
- [Microsoft Learn – Spring Cloud Azure App Configuration Java API reference](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-cloud-starter-appconfiguration-config-readme?view=azure-java-stable): thuộc tính refresh interval, trigger và feature flag interval.
- [Microsoft Learn – Secure your Azure Key Vault secrets](https://learn.microsoft.com/en-us/azure/key-vault/secrets/secure-secrets): cache secret, refresh khi rotation, retry/backoff, Event Grid và giám sát.
- [Microsoft Learn – Azure Key Vault as Event Grid source](https://learn.microsoft.com/en-us/azure/event-grid/event-schema-key-vault): sự kiện vòng đời secret/key/certificate.
- [Microsoft Learn – Automate secret rotation for resources with two sets of authentication credentials](https://learn.microsoft.com/en-us/azure/key-vault/secrets/tutorial-rotation-dual): quy trình rotation có hai credential để giảm downtime.
- [Microsoft Learn – Automate secret rotation for resources with one set of authentication credentials](https://learn.microsoft.com/en-us/azure/key-vault/secrets/tutorial-rotation): điều phối rotation khi dịch vụ chỉ hỗ trợ một credential.
- [Microsoft Learn – Azure Key Vault throttling guidance](https://learn.microsoft.com/en-us/azure/key-vault/general/overview-throttling): giới hạn dịch vụ và cách xử lý tải.

**Ghi nhớ:** refresh provider làm mới **giá trị cấu hình**; refresh scope làm mới **bean**; rotation hoàn tất khi **client đang chạy thực sự dùng credential mới** và credential cũ đã được thu hồi an toàn. Hãy thiết kế và kiểm thử cả ba tầng, đặc biệt khi ứng dụng chạy nhiều instance.
