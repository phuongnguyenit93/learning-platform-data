# Cờ tính năng và ranh giới với cấu hình thông thường

Một ứng dụng Spring Boot có thể cần thay đổi **giá trị vận hành** (ví dụ tăng timeout từ 3 giây lên 5 giây) hoặc thay đổi **tính năng nào được phép thực thi** (ví dụ chỉ 5% người dùng được thử luồng thanh toán mới). Hai quyết định này thường bị gom vào cùng một nhóm “config”, nhưng có mục đích, cách đánh giá và vòng đời khác nhau.

**Azure App Configuration** hỗ trợ cả **key-value thông thường** và **feature flags**. Với **Spring Cloud Azure**, các key-value được tải vào Spring `Environment` để bind bằng `@ConfigurationProperties` hoặc `@Value`; còn feature flags được thư viện **Feature Management** đánh giá qua `FeatureManager`. Một feature flag không đơn thuần là biến boolean: nó có thể chứa điều kiện theo người dùng, nhóm, tỉ lệ triển khai hoặc khoảng thời gian.

Bài học thuộc chương **Cấu hình Azure** trong mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun hướng tới thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud, bao gồm danh tính/quyền, dữ liệu, storage, messaging, bảo vệ secret, kiểm thử và so sánh cloud provider. Ở đây, trọng tâm là **biết khi nào dùng feature flag, khi nào dùng cấu hình thông thường**, cấu hình Spring Cloud Azure đúng cách và vận hành cờ tính năng an toàn.

## 1. Một tình huống, hai loại quyết định

Giả sử `checkout-service` có hai luồng thanh toán:

- **Luồng cũ (v1)** đang phục vụ toàn bộ người dùng.
- **Luồng mới (v2)** đã được triển khai trong mã nguồn nhưng chỉ muốn mở dần cho nhóm thử nghiệm.

Đồng thời, cả hai luồng đều gọi API đối tác và cần timeout, retry, endpoint.

| Câu hỏi | Biểu diễn phù hợp | Ví dụ |
| --- | --- | --- |
| Có cho phép chạy checkout v2 không? | **Feature flag** | `NewCheckout` bật/tắt |
| Chỉ mở checkout v2 cho nhóm canary? | **Feature flag có targeting filter** | Người dùng thuộc nhóm `pilot` |
| Mở từ 5% lên 25% người dùng? | **Feature flag có rollout/targeting** | Thay đổi tỉ lệ tiếp cận |
| Bao lâu thì timeout khi gọi gateway? | **Key-value thông thường** | `checkout.timeout=PT3S` |
| Retry tối đa bao nhiêu lần? | **Key-value thông thường** | `checkout.max-retries=3` |
| Địa chỉ API không nhạy cảm ở `prod`? | **Key-value theo label** | `checkout.endpoint=https://pay.example.com` |
| API key/mật khẩu của đối tác? | **Azure Key Vault** | Secret `payment-provider-token` |

**Nguyên tắc chọn:** nếu muốn *điều chỉnh một tham số* mà hệ thống đang sử dụng, hãy bắt đầu bằng cấu hình thông thường. Nếu muốn *quyết định một hành vi mới có được thực thi hay không và cho ai*, hãy cân nhắc feature flag. Nếu là bí mật, đưa vào Key Vault, kể cả khi bí mật đó được dùng bởi một tính năng đang bật cờ.

## 2. So sánh feature flag và cấu hình thông thường

| Khía cạnh | Cấu hình thông thường | Feature flag |
| --- | --- | --- |
| Câu hỏi chính | “Giá trị nào đang được sử dụng?” | “Tính năng này có được bật ở ngữ cảnh hiện tại?” |
| Dữ liệu thường gặp | Chuỗi, số, thời lượng, URL, collection | Trạng thái bật/tắt, điều kiện, bộ lọc, biến thể |
| Ví dụ | `checkout.timeout`, `checkout.max-retries` | `NewCheckout`, `UseNewRiskEngine` |
| Cách gọi trong Spring | `@ConfigurationProperties`, `@Value`, `Environment` | `FeatureManager.isEnabled("...")` |
| Quy mô quyết định | Cấu hình ứng dụng/môi trường | Có thể theo request, người dùng, nhóm hoặc thời điểm |
| Công cụ Azure | **Configuration Explorer** | **Feature Manager** |
| Chọn dữ liệu | `stores[].selects` theo key/label | `stores[].feature-flags.selects` theo tên flag/label |
| Vòng đời | Thay đổi khi cần tối ưu vận hành | Thường gắn với phát hành, canary, thử nghiệm hoặc kill switch |
| Rủi ro dễ gặp | Sai kiểu, override nhầm nguồn, config drift | Rẽ nhánh logic phức tạp, trải nghiệm không nhất quán, flag tồn đọng |

Hai loại dữ liệu **cùng được phân phối qua App Configuration**, nhưng thư viện và API sử dụng khác nhau. Đừng tạo một key `new-checkout=true` trong Configuration Explorer rồi kỳ vọng `FeatureManager.isEnabled("NewCheckout")` tự nhận đó là feature flag.

### 2.1. Vậy một boolean property có bao giờ đủ?

Có. Nếu một ứng dụng nội bộ chỉ cần cấu hình cố định theo môi trường như `reports.include-archive=false`, không cần rollout, targeting, quản lý vòng đời tính năng hay thay đổi thường xuyên, boolean property có thể là cách đơn giản nhất.

Khi cần bật/tắt tính năng **mà không redeploy**, điều phối thử nghiệm, ghi nhận người dùng nào thấy tính năng hoặc khôi phục nhanh về luồng cũ, feature flag mang lại cơ chế rõ ràng hơn. Tất nhiên, thay đổi runtime vẫn phụ thuộc vào cơ chế refresh và cách ứng dụng đánh giá cờ; không nên hiểu “bật ở portal” là “mọi instance đều cập nhật ngay tức thì”.

### 2.2. Feature flag không phải cơ chế phân quyền

Flag trả lời “có nên bật chức năng?”; xác thực và phân quyền trả lời “người gọi có **được phép** truy cập tài nguyên này?”. Vì vậy:

- Không thay `Spring Security`, `@PreAuthorize`, RBAC hoặc kiểm tra quyền miền nghiệp vụ bằng feature flag.
- Không dùng feature flag như biện pháp duy nhất để bảo vệ dữ liệu cá nhân hoặc tài khoản quản trị.
- Người dùng có thể thấy một chức năng mới được bật nhưng vẫn phải qua các bước authorization bình thường.
- Nếu flag thiếu, lỗi, hoặc bị tắt, ứng dụng phải có hành vi dự phòng hợp lý và an toàn.

## 3. Feature flag lưu trong Azure gồm những gì?

Khi tạo cờ trong **Feature Manager** của App Configuration, bạn sẽ gặp các trường:

| Thuộc tính | Mục đích |
| --- | --- |
| **Name / ID** | Định danh được mã Java dùng để kiểm tra, ví dụ `NewCheckout` |
| **Enabled** | Công tắc cấp cao: đang bật hay tắt |
| **Label** | Phiên bản theo môi trường hoặc phạm vi, ví dụ `dev`, `staging`, `prod` |
| **Description** | Giải thích ý nghĩa và trách nhiệm của flag |
| **Client filters / conditions** | Quy tắc xác định khi nào một flag bật, ví dụ tỉ lệ hoặc đối tượng |
| **Variants** | Khi sử dụng loại flag có biến thể, trả các phương án trải nghiệm hoặc giá trị khác nhau |

Trong kho dữ liệu App Configuration, feature flag có **dạng bản ghi chuyên biệt** (tên key nội bộ theo quy ước như `.appconfig.featureflag/NewCheckout` cùng content type dành cho feature flag). Không nên tự tạo thủ công một key-value thông thường có tên giống flag; hãy dùng **Feature Manager**, Azure CLI hoặc SDK/API quản lý feature flags để bảo đảm định dạng chính xác.

Ba nhóm kịch bản trên Azure thường được trình bày là:

1. **Switch:** bật/tắt chức năng đơn giản.
2. **Rollout:** mở dần tính năng theo tỉ lệ hoặc đối tượng xác định.
3. **Experiment:** phân phối phiên bản trải nghiệm và theo dõi số liệu để đánh giá.

Khả năng cụ thể như variant assignment, telemetry và targeting phụ thuộc dòng phiên bản của client Feature Management. Trong bài thực hành đầu tiên, ta dùng **Switch** để làm rõ ranh giới với property thông thường; phần nâng cao giải thích rollout và filter.

## 4. Kiến trúc tích hợp với Spring Cloud Azure

~~~mermaid
flowchart TD
    Portal["Azure App Configuration store"] -->|Key-value| Provider["Spring Cloud Azure App Configuration provider"]
    Portal -->|Feature flags| Provider
    Provider -->|"PropertySource: checkout.timeout"| Env["Spring Environment"]
    Provider -->|"feature-management"| Flags["Feature Management configuration"]
    Env --> Settings["@ConfigurationProperties / @Value"]
    Flags --> Manager["FeatureManager"]
    Manager --> Decision["isEnabled(NewCheckout)"]
    Settings --> Business["Checkout service"]
    Decision --> Business
    Vault["Azure Key Vault: secret nếu cần"] -.-> Business
~~~

Để hoàn thành luồng này, ứng dụng có hai dependency có trách nhiệm riêng:

- **App Configuration provider** tải dữ liệu từ Azure.
- **Feature Management library** đọc cấu hình feature và đánh giá flag tại thời điểm gọi.

Điểm quan trọng: **Feature Management không bắt buộc phải có Azure**. Có thể khai báo feature flags trong `application.yml` và vẫn dùng `FeatureManager`. Việc thêm App Configuration giúp quản trị cờ tập trung và hỗ trợ tải/làm mới dữ liệu từ Azure.

## 5. Thực hành: bật/tắt checkout v2 từ Azure

### 5.1. Chuẩn bị App Configuration store

Giả sử đã có store `demo-checkout-config` với endpoint:

~~~text
https://demo-checkout-config.azconfig.io
~~~

Tạo hai loại dữ liệu khác nhau trên Azure portal:

**Trong Configuration Explorer**, tạo key-value thông thường:

| Key | Label | Value |
| --- | --- | --- |
| `/application/checkout.timeout` | (No Label) | `PT3S` |
| `/application/checkout.max-retries` | (No Label) | `3` |

**Trong Feature Manager**, tạo **feature flag**:

| Tên | Label | Trạng thái ban đầu |
| --- | --- | --- |
| `NewCheckout` | (No Label) | Off |

Chọn loại Switch và để trống điều kiện/filter ở bước đầu. Thêm mô tả, ví dụ “Điều khiển luồng checkout v2; owner: team payments”.

Lúc này Azure có hai **loại cấu hình cùng tồn tại**. `checkout.timeout` không phải flag, còn `NewCheckout` phải được tạo trong giao diện feature flag.

### 5.2. Chọn phiên bản Spring Cloud Azure tương thích

Dự án ví dụ dùng **Spring Boot** và **Maven**. Chọn BOM Spring Cloud Azure theo ma trận hỗ trợ của phiên bản Spring Boot đang dùng (ví dụ Spring Boot 4.0.x với dòng Spring Cloud Azure 7.x). Một cấu hình Maven minh họa:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud-azure.version>7.2.0</spring-cloud-azure.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- Tải key-value và feature flags từ App Configuration -->
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-appconfiguration-config</artifactId>
    </dependency>

    <!-- Đánh giá feature flags qua FeatureManager -->
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-feature-management</artifactId>
    </dependency>
</dependencies>
~~~

`7.2.0` là phiên bản BOM minh họa theo quickstart Microsoft; kiểm tra version mapping khi thực hiện trong dự án thật. Nếu cần `@FeatureGate` tích hợp Spring MVC, có thể chọn `spring-cloud-azure-feature-management-web` thay cho thư viện feature management core. Chỉ thêm `spring-cloud-azure-appconfiguration-config-web` khi muốn tận dụng cơ chế tự kiểm tra refresh gắn với Spring Web; một ứng dụng dùng Spring Web không tự yêu cầu phải dùng cả hai biến thể `-web`.

### 5.3. Cấu hình Spring import và bật feature flags

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: checkout-service
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            feature-flags:
              enabled: true
~~~

Khai báo biến môi trường:

~~~bash
export AZURE_APPCONFIG_ENDPOINT="https://demo-checkout-config.azconfig.io"
~~~

Trong PowerShell:

~~~powershell
$Env:AZURE_APPCONFIG_ENDPOINT = "https://demo-checkout-config.azconfig.io"
~~~

**Giải thích ba dòng quyết định:**

- `spring.config.import=azureAppConfiguration`: yêu cầu Spring Boot dùng App Configuration provider ở giai đoạn nạp Config Data.
- `stores[0].endpoint`: xác định store để đọc cấu hình; đây là URL endpoint, không phải secret.
- `stores[0].feature-flags.enabled=true`: yêu cầu provider **nạp cả feature flags**, ngoài các key-value thông thường.

Nếu quên `feature-flags.enabled`, `checkout.timeout` vẫn có thể xuất hiện trong Spring `Environment`, nhưng `FeatureManager` không nhận flag `NewCheckout` từ store và có thể trả false vì thiếu định nghĩa.

### 5.4. Danh tính và quyền đọc

Khi dùng Microsoft Entra ID, định danh mà ứng dụng đang dùng cần role **App Configuration Data Reader** trên store. Với workload chạy trên Azure, nên sử dụng **Managed Identity** và gán role cho đúng principal. Máy local có thể dùng credential chain phù hợp và tài khoản phát triển đã được cấp quyền.

Một tài khoản có quyền quản lý resource trên Azure portal chưa chắc có quyền **đọc dữ liệu**. Không khắc phục lỗi 403 bằng cách chép connection string chứa access key vào repository. Nếu sử dụng Key Vault reference cho secret ở kịch bản mở rộng, workload còn cần quyền đọc secret bên Key Vault riêng.

## 6. Cách mã Spring sử dụng hai loại cấu hình

### 6.1. Bind key-value bằng `@ConfigurationProperties`

~~~java
package com.example.checkout;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutSettings(Duration timeout, int maxRetries) {
}
~~~

Tạo lớp ứng dụng:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Khi import hoạt động, `/application/checkout.timeout=PT3S` được provider ánh xạ thành `checkout.timeout`, rồi Spring Binder tạo `Duration.ofSeconds(3)`. Cấu hình này được sử dụng như một **tham số**, không phải điều kiện bật/tắt tính năng.

### 6.2. Kiểm tra flag bằng `FeatureManager`

~~~java
package com.example.checkout;

import com.azure.spring.cloud.feature.management.FeatureManager;
import org.springframework.stereotype.Service;

@Service
public class CheckoutFlowSelector {
    private final FeatureManager featureManager;
    private final CheckoutSettings settings;

    public CheckoutFlowSelector(
            FeatureManager featureManager,
            CheckoutSettings settings) {
        this.featureManager = featureManager;
        this.settings = settings;
    }

    public String selectFlow() {
        // Đánh giá cờ tại điểm quyết định; không chụp kết quả cố định khi khởi tạo bean
        return featureManager.isEnabled("NewCheckout") ? "checkout-v2" : "checkout-v1";
    }

    public long gatewayTimeoutMillis() {
        // Đây vẫn là cấu hình thông thường
        return settings.timeout().toMillis();
    }
}
~~~

Ví dụ REST controller chỉ đưa ra thông tin không nhạy cảm:

~~~java
package com.example.checkout;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutPreviewController {
    private final CheckoutFlowSelector selector;

    public CheckoutPreviewController(CheckoutFlowSelector selector) {
        this.selector = selector;
    }

    @GetMapping("/checkout/preview")
    public Map<String, Object> preview() {
        return Map.of(
                "flow", selector.selectFlow(),
                "timeoutMillis", selector.gatewayTimeoutMillis());
    }
}
~~~

Chạy ứng dụng, gọi:

~~~bash
curl http://localhost:8080/checkout/preview
~~~

Nếu `NewCheckout` đang Off và timeout là `PT3S`:

~~~json
{"flow":"checkout-v1","timeoutMillis":3000}
~~~

Sau khi bật flag trong Azure Feature Manager và **khởi động lại ứng dụng** (bài cơ bản chưa bật refresh), kết quả kỳ vọng:

~~~json
{"flow":"checkout-v2","timeoutMillis":3000}
~~~

Giá trị timeout không đổi chỉ vì flag được bật. Hai dữ liệu phục vụ hai quyết định độc lập.

### 6.3. Đặt điểm kiểm tra flag hợp lý

Thường nên kiểm tra tại **ranh giới quyết định hành vi**, như chọn service implementation, chọn template hiển thị hoặc định tuyến luồng nghiệp vụ:

~~~java
if (featureManager.isEnabled("NewCheckout")) {
    // Thực thi luồng mới với các quy tắc của v2
} else {
    // Thực thi luồng hiện hành
}
~~~

Đừng chia nhánh ở mọi lớp từ controller, service đến repository, vì việc đổi flag trong một request có thể dẫn tới trạng thái nửa v1 nửa v2. Đối với request phức tạp, **chốt quyết định một lần trong request hoặc workflow** rồi truyền lựa chọn nhất quán xuống các thành phần liên quan.

Với Spring Web, thư viện `spring-cloud-azure-feature-management-web` có `FeatureManagerSnapshot` ở phạm vi request để giữ kết quả đánh giá nhất quán trong một request; cũng có `@FeatureGate` để chặn endpoint khi flag Off. `@FeatureGate` mặc định có thể trả **HTTP 404** qua disabled handler. Đây là một **cổng tính năng** và vẫn cần authorization phù hợp nếu endpoint truy cập dữ liệu/hoạt động có bảo vệ.

## 7. Cấu hình flag theo môi trường và bộ lọc

App Configuration hỗ trợ **label** cho cả key-value và feature flags. Tuy nhiên, hai nhóm sử dụng **hai bộ chọn khác nhau**.

Ví dụ ứng dụng có key-value timeout theo profile `prod` và flag chỉ cho `dev`:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/*"
                label-filter: ',${spring.profiles.active}'
            feature-flags:
              enabled: true
              selects:
                - key-filter: "*"
                  label-filter: "dev"
~~~

- `stores[].selects` lọc **key-value thông thường**.
- `stores[].feature-flags.selects` lọc **feature flags**.
- Trong ví dụ, flag luôn lấy label `dev`, kể cả khi profile đang là `prod`. Đây chỉ là ví dụ để thấy hai filter độc lập, **không phải cấu hình production nên dùng**.

Để flag đi theo môi trường đang chạy, thay bộ chọn flag bằng:

~~~yaml
feature-flags:
  enabled: true
  selects:
    - key-filter: "*"
      label-filter: "${spring.profiles.active}"
~~~

Giả định có đúng một active profile môi trường (`dev`, `staging`, `prod`). Nếu chỉ có flag với **(No Label)** như ở bước 5, hãy bỏ `feature-flags.selects` để dùng selector mặc định, hoặc cấu hình selector No Label rõ ràng theo hướng dẫn phiên bản provider. **Không tự giả định** rằng cách fallback No Label của key-value luôn áp dụng giống hệt cho feature flags.

### 7.1. Một feature có thể bật ở dev nhưng tắt ở prod

| Flag | Label | Enabled | Hành vi |
| --- | --- | --- | --- |
| `NewCheckout` | `dev` | On | Cho đội phát triển thử nghiệm |
| `NewCheckout` | `staging` | On | Cho nhóm QA kiểm thử |
| `NewCheckout` | `prod` | Off | Người dùng production vẫn đi v1 |

Khi muốn canary ở prod, bạn không nhất thiết chuyển On cho tất cả: có thể tạo điều kiện rollout/targeting trên **bản ghi prod**, rồi chuyển theo từng giai đoạn. Cần gắn role/tài khoản cấu hình đúng người được phép thay đổi flag và kiểm soát quy trình phát hành.

### 7.2. Ranh giới giữa label và phân quyền

Label không mặc định là **biên bảo mật**. Người có quyền đọc App Configuration store thường có thể đọc các bản ghi ở nhiều label theo quyền được cấp. Nếu production yêu cầu phân vùng quyền hoặc mạng riêng, hãy cân nhắc store riêng cho production thay vì dựa vào tên label để ngăn lộ thông tin.

## 8. Feature filter: khác biệt lớn nhất so với boolean thông thường

Một key-value `new-checkout.enabled=true` thường chỉ có hai trạng thái. Feature Management có thể bổ sung điều kiện để trạng thái cuối cùng thay đổi theo bối cảnh đánh giá.

| Bộ lọc | Trường hợp sử dụng | Cẩn trọng |
| --- | --- | --- |
| **TimeWindowFilter** | Bật tính năng trong khoảng thời gian hoặc lịch định kỳ | Múi giờ, thời điểm bắt đầu/kết thúc, đồng bộ thời gian |
| **PercentageFilter** | Thử bật ngẫu nhiên theo một tỉ lệ khi đánh giá | Kết quả có thể khác giữa các lượt đánh giá |
| **TargetingFilter** | Nhắm tới người dùng, nhóm hoặc phần trăm đối tượng | Phải có danh tính/ngữ cảnh đúng; kiểm thử tính ổn định |
| **Custom FeatureFilter** | Điều kiện đặc thù, ví dụ tenant hoặc loại tài khoản | Quy tắc cần xác định, kiểm thử và có đường fallback |
| **Variants** | Đưa người dùng vào một trong nhiều biến thể trải nghiệm | Không dùng biến thể để thay thế xác thực/authorization |

### 8.1. Tỉ lệ ngẫu nhiên khác rollout ổn định theo người dùng

Giả sử dùng `PercentageFilter` với tham số 10%. Theo tài liệu Spring Cloud Azure, bộ lọc này có thể cho **kết quả khác nhau ở mỗi lần đánh giá**. Nếu một request được đánh giá nhiều lần, người dùng có nguy cơ gặp trạng thái không nhất quán trừ khi dùng cơ chế snapshot theo request.

Nếu mục tiêu là **một người dùng đã được chọn sẽ tiếp tục nhìn thấy cùng phiên bản** qua các request, cần chiến lược targeting/assignment dựa trên danh tính ổn định hoặc cơ chế phân phối phù hợp, không nên dùng random percentage check như lời hứa về nhóm người dùng cố định.

### 8.2. Ví dụ cấu hình flag trong YAML local

Thư viện Feature Management cũng hiểu cấu trúc cờ định nghĩa **ngay trong Spring configuration**; điều này hữu ích cho local development hoặc kiểm thử không có Azure:

~~~yaml
feature-management:
  feature_flags:
    - id: NewCheckout
      enabled: true
    - id: NewRecommendation
      enabled: false
    - id: PartialCheckout
      enabled: true
      conditions:
        client_filters:
          - name: PercentageFilter
            parameters:
              Value: 10
~~~

Đây là **cấu trúc feature-management chuyên dụng**, khác với:

~~~yaml
checkout:
  timeout: PT3S
  max-retries: 3
~~~

Dữ liệu flag nằm dưới `feature-management` và được `FeatureManager` đánh giá. Dữ liệu checkout thường nằm dưới `checkout` và được Spring Binder chuyển kiểu.

Cú pháp, bộ lọc hỗ trợ và cách truyền ngữ cảnh targeting có thể thay đổi giữa các dòng Feature Management; khi triển khai targeting/variants, đối chiếu tài liệu đúng phiên bản dependency.

### 8.3. Custom feature filter phải có quy tắc rõ

Một custom filter cần ánh xạ **tên filter trên Azure** với bean implement `FeatureFilter` trong Spring. Ví dụ khung cơ bản:

~~~java
import com.azure.spring.cloud.feature.management.filters.FeatureFilter;
import com.azure.spring.cloud.feature.management.models.FeatureFilterEvaluationContext;
import org.springframework.stereotype.Component;

@Component("MaintenanceWindow")
public class MaintenanceWindowFilter implements FeatureFilter {
    @Override
    public boolean evaluate(FeatureFilterEvaluationContext context) {
        // Chỉ ví dụ: logic thật phải xét giờ, múi giờ và chính sách vận hành
        return false;
    }
}
~~~

Khi flag tham chiếu một filter tên `MaintenanceWindow`, thư viện tìm bean tương ứng. Nếu filter bị thiếu hoặc ném lỗi, hành vi phụ thuộc `spring.cloud.azure.feature.management.fail-fast`. Nên thiết kế nhánh off/dự phòng rõ ràng để hệ thống vẫn có hành vi dự đoán được trong sự cố.

## 9. Làm mới flag trong lúc ứng dụng đang chạy

Trong ví dụ cơ bản, ta **khởi động lại ứng dụng** sau khi thay đổi flag trên portal. Điều này giúp phân biệt đúng/không đúng của dữ liệu đã tải lúc startup trước khi đưa refresh vào.

Để bật cơ chế kiểm tra refresh của Spring Cloud Azure App Configuration:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].feature-flags.enabled=true
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled=true
spring.cloud.azure.appconfiguration.stores[0].monitoring.feature-flag-refresh-interval=30s
~~~

Theo tài liệu provider, khi **feature flags và monitoring** cùng được bật, provider có thể kiểm tra thay đổi flag theo chu kỳ; thời gian mặc định là khoảng **30 giây**. Đó là **khoảng kiểm tra tối thiểu**, không phải cam kết độ trễ cập nhật từ portal tới mọi người dùng.

Chỉ dùng `spring-cloud-azure-appconfiguration-config` thì cần cơ chế chủ động kích hoạt kiểm tra refresh theo API/endpoint phù hợp. Nếu dùng `spring-cloud-azure-appconfiguration-config-web`, việc kiểm tra tự động gắn với **hoạt động request của Spring Web**. Một instance không nhận request có thể chưa kiểm tra khi đã qua 30 giây.

Phân biệt các lớp cache:

1. **Provider App Configuration** giữ bản dữ liệu đã tải và theo dõi refresh.
2. **FeatureManager/FeatureManagerSnapshot** đánh giá và có thể giữ kết quả theo phạm vi (ví dụ request).
3. **Mã nghiệp vụ** có thể tự cache quyết định nếu lập trình viên lưu vào field/bean.

Vì vậy, ngay cả khi provider đã làm mới cấu hình, một **đối tượng tự chụp giá trị `isEnabled` khi khởi tạo** sẽ không tự thay đổi. Luôn xác định **điểm đánh giá và phạm vi nhất quán** của feature flag.

### 9.1. Nhiều instance và rollback

Giả sử có ba instance `checkout-service` đằng sau load balancer. Khi thay đổi `NewCheckout` từ Off thành On:

- Các instance có thể thực hiện kiểm tra refresh ở những thời điểm khác nhau.
- Trong giai đoạn chuyển tiếp, cùng một người dùng có thể lần lượt gặp v1 và v2 ở các request khác nhau.
- Quy trình phát hành nên chịu được tính **nhất quán cuối cùng**, có quan sát riêng theo phiên bản/nhánh xử lý và rollback rõ ràng.

Đối với chức năng ghi dữ liệu hoặc giao dịch, cần bảo đảm cấu trúc dữ liệu và giao thức tương thích trong thời gian cả hai luồng đang cùng hoạt động. Không dùng flag để che một thay đổi schema **không tương thích ngược** đã được áp dụng.

## 10. Fail-fast và an toàn khi cờ không tồn tại

Có hai loại lỗi dễ nhầm:

| Lỗi | Nơi xảy ra | Cần xem |
| --- | --- | --- |
| Không đọc được App Configuration store (401/403, mạng, endpoint sai) | **Config provider** ở startup/refresh | Cấu hình `spring.cloud.azure.appconfiguration.stores[0].fail-fast`, danh tính, role, network |
| Flag đã tải nhưng có filter không tồn tại/ném lỗi | **Feature Management evaluator** | `spring.cloud.azure.feature.management.fail-fast`, tên bean filter, tham số |

Khi một flag **không có định nghĩa**, `FeatureManager.isEnabled("...")` theo tài liệu trả `false`. Điều này hữu ích khi muốn an toàn mặc định cho tính năng mới. Tuy nhiên, nếu đó là **kill switch để tắt một hành vi nguy hiểm**, cần xác định rõ ý nghĩa của trạng thái missing và dự phòng: thiết kế “missing = off” có thể khiến nhánh cũ được thực thi, và nhánh cũ chưa chắc là lựa chọn an toàn trong mọi tình huống.

Nếu flag có filter không nhận diện được, `FeatureManager` thường ném lỗi khi `spring.cloud.azure.feature.management.fail-fast=true` (mặc định theo tài liệu); có thể cấu hình `false` để evaluator trả false thay vì ném lỗi. Không nên tắt fail-fast chỉ để che sai tên bộ lọc trong production: điều đó có thể làm tính năng lặng lẽ chuyển sang Off mà không ai nhận ra.

## 11. Kiểm thử: ba cấp độ không nên gộp lại

### 11.1. Unit test logic chọn nhánh

Không cần gọi Azure để kiểm tra logic nghiệp vụ. Có thể mock `FeatureManager` và cung cấp `CheckoutSettings` giả:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.azure.spring.cloud.feature.management.FeatureManager;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class CheckoutFlowSelectorTest {
    @Test
    void offUsesOldFlow() {
        FeatureManager flags = mock(FeatureManager.class);
        when(flags.isEnabled("NewCheckout")).thenReturn(false);

        CheckoutSettings settings =
                new CheckoutSettings(Duration.ofSeconds(3), 3);
        CheckoutFlowSelector selector =
                new CheckoutFlowSelector(flags, settings);

        assertThat(selector.selectFlow()).isEqualTo("checkout-v1");
        assertThat(selector.gatewayTimeoutMillis()).isEqualTo(3000);
    }

    @Test
    void onUsesNewFlow() {
        FeatureManager flags = mock(FeatureManager.class);
        when(flags.isEnabled("NewCheckout")).thenReturn(true);

        CheckoutFlowSelector selector = new CheckoutFlowSelector(
                flags, new CheckoutSettings(Duration.ofSeconds(3), 3));

        assertThat(selector.selectFlow()).isEqualTo("checkout-v2");
    }
}
~~~

Các test này xác minh **logic rẽ nhánh**, không chứng minh Azure đã tải flag hoặc evaluator thực hiện targeting đúng. Không cần startup `SpringApplication` trong test đơn vị kiểu này.

### 11.2. Test feature-management không cần Azure

Trong `src/test/resources/application-test.yml`, tắt App Configuration và khai báo flag local:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        enabled: false

feature-management:
  feature_flags:
    - id: NewCheckout
      enabled: true
~~~

Với `@SpringBootTest` và `@ActiveProfiles("test")`, có thể inject `FeatureManager` rồi xác minh `isEnabled("NewCheckout")` trả true. Cách này kiểm tra **mapping cờ vào Feature Management** nhưng chưa kiểm tra tải flag từ Azure, RBAC hoặc refresh.

Lưu ý: nếu `application.yml` production có `spring.config.import=azureAppConfiguration`, cần xác nhận cờ `enabled=false` thực sự vô hiệu hóa provider trước khi test; không đưa endpoint/credential thật vào tài nguyên test.

### 11.3. Integration test với App Configuration

Một luồng kiểm thử tích hợp có thể dùng store dev và identity có quyền đọc hạn chế:

1. Tạo flag `NewCheckout` với (No Label), trạng thái Off; tạo key-value timeout.
2. Khởi động app với `feature-flags.enabled=true`, xác minh `isEnabled` trả false.
3. Bật flag và **khởi động lại app**, xác minh true; đảm bảo timeout vẫn giữ nguyên.
4. Tạo một flag `prod`/`dev` có trạng thái khác nhau và xác minh `feature-flags.selects`.
5. Bật monitoring/refresh; thay flag, quan sát thời gian và số instance cập nhật.
6. Thử filter lỗi/missing và kiểm tra hành vi fail-fast; không dùng production secret trong test.
7. Nếu triển khai rollout theo đối tượng, kiểm tra cùng một người dùng luôn được xử lý nhất quán trong một workflow.

Không log token, connection string, toàn bộ `Environment` hoặc định danh người dùng không cần thiết vào kết quả kiểm thử.

## 12. Vòng đời vận hành: tạo, mở dần, dọn dẹp

Feature flag tạo ra **nợ kỹ thuật** nếu không được quản trị. Mỗi flag nên có thông tin tối thiểu:

| Trường quản trị | Ví dụ |
| --- | --- |
| Tên ổn định | `NewCheckout` |
| Owner | Nhóm Payments |
| Lý do | Canary checkout v2 |
| Trạng thái mục tiêu | Sau phát hành, v2 trở thành mặc định |
| Hạn xử lý | Khi đạt ngưỡng quan sát vận hành đã thống nhất |
| Cách rollback | Chuyển Off để quay về v1 trong giai đoạn còn hỗ trợ |
| Chỉ số kiểm tra | Tỉ lệ lỗi, latency, doanh thu/hoàn tất checkout |
| Kế hoạch cleanup | Xóa nhánh v1 và flag sau khi không còn cần thiết |

Một chu trình gợi ý:

~~~mermaid
flowchart LR
    A["Tạo flag Off"] --> B["Bật ở dev"]
    B --> C["Kiểm thử staging"]
    C --> D["Canary trên prod"]
    D --> E{"Số liệu ổn?"}
    E -->|Có| F["Mở rộng rollout"]
    E -->|Không| G["Chuyển Off, điều tra"]
    G --> C
    F --> H["Chọn nhánh cố định"]
    H --> I["Xóa code cũ và flag"]
~~~

**Chọn loại flag theo mục đích:**

- **Release flag:** phục vụ ra mắt tính năng; thường nên xóa khi rollout hoàn tất.
- **Experiment flag:** xác định nhóm thử nghiệm và đo kết quả; cần quy trình phân phối nhóm nhất quán và thống kê phù hợp.
- **Operational kill switch:** dùng để giảm tải hoặc tắt nhanh chức năng rủi ro; cần theo dõi tình trạng chính xác và có đường dự phòng.
- **Permission/entitlement:** không nên chỉ là feature flag; phải có kiểm tra authorization/entitlement ở phía server và nguồn quyền tin cậy.

Không nên lạm dụng feature flag cho hầu hết mọi giá trị cấu hình: tăng số nhánh xử lý, gây khó kiểm thử toàn bộ tổ hợp và để lại đường code chết sau phát hành.

## 13. Lỗi thường gặp khi tích hợp Spring Cloud Azure

| Biểu hiện | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Timeout từ Azure đọc được, flag luôn false | Chưa bật `feature-flags.enabled` hoặc flag chưa được tạo đúng kiểu | Kiểm tra cấu hình store và **Feature Manager**, không chỉ Configuration Explorer |
| Flag có trên portal nhưng Spring không thấy | Sai label/`feature-flags.selects` hoặc endpoint | Kiểm tra tên flag, label, selectors, store đang kết nối |
| `FeatureManager` không inject được | Thiếu thư viện `spring-cloud-azure-feature-management` | Kiểm tra dependency và BOM |
| Key `new.checkout=true` không ảnh hưởng `isEnabled("NewCheckout")` | Key-value thường không phải định nghĩa feature flag | Tạo flag trong Feature Manager hoặc dùng schema `feature-management` local |
| Bật flag xong chỉ một số instance thấy | Refresh/check cache khác thời điểm | Xác minh monitoring, interval, lưu lượng request và trạng thái từng instance |
| Tỉ lệ rollout thay đổi giữa hai lần gọi | Dùng filter ngẫu nhiên cho mục đích cần sticky assignment | Dùng targeting/assignment ổn định và kết quả nhất quán theo request |
| `@FeatureGate` trả 404 khi Off | Đây là hành vi chặn endpoint mặc định | Thiết kế fallback/status phù hợp; vẫn giữ authorization |
| Lỗi 403 khi đọc store | Identity thiếu `App Configuration Data Reader` | Kiểm tra principal, scope RBAC, token và network |
| Feature filter báo không tìm thấy | Tên filter trong flag không khớp bean đã đăng ký | Kiểm tra `@Component` và `fail-fast` evaluator |
| Có thể mở tính năng nhưng người dùng không được phép thao tác | Flag kiểm soát rollout, không kiểm soát quyền | Thêm Spring Security/kiểm tra quyền nghiệp vụ |

## 14. Bài tập áp dụng

Bạn triển khai một dịch vụ `recommendation-service` có tính năng thuật toán gợi ý mới. Yêu cầu:

- Tham số `recommendation.timeout=PT2S` áp dụng cho cả thuật toán cũ và mới.
- Tính năng `NewRanker` ở `dev` bật cho tất cả; ở `prod` ban đầu Off.
- Sau khi ổn định, chỉ mở cho nhóm người dùng thử nghiệm ở `prod`.
- Khi phát hiện tăng lỗi, có thể chuyển về thuật toán cũ nhanh chóng.
- Chỉ người có quyền mới được xem dữ liệu gợi ý cá nhân; rollout không được bỏ qua authorization.

**Hãy quyết định:**

1. Dữ liệu nào tạo trong Configuration Explorer và dữ liệu nào tạo trong Feature Manager?
2. Bộ lọc label nào được dùng cho cờ `NewRanker` khi chuyển giữa `dev` và `prod`?
3. Trong code, kiểm tra `NewRanker` tại điểm nào để một request không trộn thuật toán cũ và mới?
4. Nếu dùng `PercentageFilter` ngẫu nhiên, có thể bảo đảm người dùng luôn ở cùng nhóm trong nhiều request không?
5. Cần loại test nào để khẳng định provider thực sự tải flag từ Azure, không chỉ mock logic?
6. Khi hoàn thành rollout, nên xử lý nhánh code cũ và flag như thế nào?

**Đáp án định hướng:** (1) timeout là key-value, `NewRanker` là feature flag; (2) `feature-flags.selects[].label-filter` theo môi trường; (3) tại ranh giới chọn thuật toán và giữ quyết định nhất quán trong workflow; (4) không, cần targeting/assignment ổn định; (5) integration test với store dev và identity thực; (6) chốt nhánh chính rồi xóa flag và nhánh lỗi thời sau khi đánh giá rủi ro.

## 15. Tài liệu tham khảo chính thức

- [Microsoft Learn – Quickstart: Add feature flags to a Spring Boot app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/quickstart-feature-flag-spring-boot): dependency, `feature-flags.enabled`, cách tạo flag và sử dụng `FeatureManager`.
- [Microsoft Learn – Tutorial: Use feature flags in a Spring Boot app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/use-feature-flags-spring-boot): kiểm tra flag, filters, controller actions và `@FeatureGate`.
- [Microsoft Learn – Spring Cloud Azure App Configuration support](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/app-configuration-support): key-value, feature flags, label filters, refresh và fail-fast.
- [Microsoft Learn – Feature management overview](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-feature-management): feature release, switch, rollout và experiment.
- [Microsoft Learn – Manage feature flags](https://learn.microsoft.com/en-us/azure/azure-app-configuration/manage-feature-flags): tạo/biên tập cờ trên Azure portal.
- [Microsoft Learn – Feature management library capabilities](https://learn.microsoft.com/en-us/azure/azure-app-configuration/feature-management-overview): so sánh targeting, variants và feature gates giữa các nền tảng.
- [Microsoft Learn – Dynamic configuration for Spring Boot](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): refresh, hoạt động request và cache.

**Ghi nhớ:** key-value thông thường cung cấp **tham số cho hành vi**, feature flag cung cấp **quyết định có thực thi hành vi hay không**, còn quyền truy cập và bí mật cần cơ chế bảo vệ riêng. Khi tích hợp Spring Cloud Azure, chọn đúng API (`@ConfigurationProperties` hoặc `FeatureManager`), bộ lọc, cách refresh và chính sách vận hành để phát hành tính năng có kiểm soát.
