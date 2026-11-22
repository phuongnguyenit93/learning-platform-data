# Phân biệt thay đổi Environment với thay đổi bean đã khởi tạo

Bài học thuộc chương **Environment** của module **SPRING_CLOUD_CORE**. Trong ứng dụng Spring, giá trị cấu hình được đọc từ `Environment` và các `PropertySource`, sau đó được đưa vào bean khi bean được tạo hoặc binding. Khi cấu hình thay đổi trong lúc ứng dụng đang chạy, hai việc này **không đồng nghĩa**:

- **Environment thay đổi:** giá trị mà hệ thống phân giải từ các nguồn cấu hình có thể đã khác.
- **Bean đã khởi tạo thay đổi:** đối tượng đang được ứng dụng sử dụng thực sự nhận giá trị mới hoặc được tạo lại với giá trị mới.

Một lần cập nhật `Environment` không tự động làm mọi field trong mọi singleton bean thay đổi. Spring Cloud Context cung cấp các cơ chế như `EnvironmentChangeEvent`, rebinding cho `@ConfigurationProperties` và `@RefreshScope` để xử lý một số trường hợp. Người học cần hiểu chính xác cơ chế nào áp dụng cho loại bean nào, giới hạn của chúng và cách kiểm chứng sau refresh.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Mô tả vai trò của `Environment`, `PropertySource` và thứ tự ưu tiên khi đọc property.
2. Phân biệt giá trị được tra cứu động từ Environment với giá trị đã được inject vào bean lúc khởi tạo.
3. Giải thích vì sao `@Value` trong singleton thông thường không tự đổi sau khi property source thay đổi.
4. Phân biệt khởi tạo ban đầu, rebinding của `@ConfigurationProperties` và tái tạo target của `@RefreshScope`.
5. Giải thích vai trò của `EnvironmentChangeEvent`, quy trình refresh và các endpoint Actuator liên quan.
6. Nhận diện giới hạn của mutable/immutable configuration bean, bean giữ state và các dependency phụ thuộc.
7. Thiết kế test xác minh Environment, bean và từng instance sau khi cấu hình thay đổi.
8. Vận hành refresh an toàn trong hệ thống có nhiều instance, tránh trạng thái cấu hình không đồng nhất.

## 2. Ba lớp cần phân biệt

Có thể nhìn luồng cấu hình theo ba lớp:

~~~mermaid
flowchart TD
    SRC["Nguồn cấu hình: YAML, env, system property, Config Server..."] --> PS["PropertySource collection"]
    PS --> ENV["Environment: tra cứu giá trị hiện tại"]
    ENV --> CREATE["Tạo bean / bind cấu hình ban đầu"]
    CREATE --> BEAN["Bean singleton đã khởi tạo"]
    ENV --> EVENT["EnvironmentChangeEvent / refresh workflow"]
    EVENT --> REBIND["@ConfigurationProperties rebind"]
    EVENT --> SCOPE["@RefreshScope target cache invalidation"]
    REBIND --> BOUND["Bean cấu hình được cập nhật"]
    SCOPE --> NEXT["Lần gọi sau tạo target mới"]
~~~

Ba lớp không nên bị gộp làm một:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Nguồn cấu hình** | Dữ liệu gốc đang nằm ở đâu? | File YAML, biến môi trường, system property, Config Server. |
| **Environment** | Khi tra cứu khóa này, giá trị hiệu lực là gì? | `environment.getProperty("app.banner")`. |
| **Bean đang chạy** | Đối tượng nào đang giữ hoặc sử dụng giá trị? | Singleton có field `banner`, bean `@ConfigurationProperties`, proxy `@RefreshScope`. |

Giả sử `app.banner=Welcome` khi ứng dụng khởi động. Một bean singleton nhận giá trị này qua constructor. Sau đó một nguồn cấu hình được cập nhật thành `Hello again`.

- Environment có thể trả về `Hello again` khi tra cứu lại.
- Field đã gán trong singleton thông thường vẫn có thể là `Welcome`.
- Bean `@ConfigurationProperties` có thể được rebinding khi Spring Cloud xử lý `EnvironmentChangeEvent`.
- Bean `@RefreshScope` có thể được tạo lại target ở lần gọi tiếp theo sau khi cache target bị xóa.

Vì vậy, câu “đã refresh cấu hình” cần được làm rõ: đã cập nhật source, đã cập nhật Environment, đã phát event, đã rebinding bean, hay đã tái tạo target?

## 3. Environment và PropertySource hoạt động thế nào?

### 3.1. Environment là lớp tra cứu

Trong Spring, `Environment` cung cấp khả năng truy vấn property và profile đang hoạt động. Nó tổng hợp nhiều nguồn `PropertySource`, mỗi nguồn có tên và dữ liệu riêng. Một khóa có thể xuất hiện ở nhiều nguồn; giá trị được chọn theo thứ tự ưu tiên của các nguồn trong môi trường đó.

Ví dụ:

~~~java
@Component
class EnvironmentInspector {
    private final Environment environment;

    EnvironmentInspector(Environment environment) {
        this.environment = environment;
    }

    String currentBanner() {
        return environment.getProperty("app.banner", "default");
    }
}
~~~

Mỗi lần gọi `currentBanner()`, phương thức tra cứu property từ Environment tại thời điểm gọi. Nếu một PropertySource đang được quản lý đã thay đổi giá trị, lần tra cứu tiếp theo có thể thấy giá trị mới.

Điều đó khác với việc lấy property một lần rồi lưu vào field:

~~~java
@Component
class BannerSnapshot {
    private final String banner;

    BannerSnapshot(@Value("${app.banner:default}") String banner) {
        this.banner = banner;
    }

    String currentBanner() {
        return banner;
    }
}
~~~

Constructor của `BannerSnapshot` chạy khi bean được tạo. Giá trị được inject lúc đó được lưu trong field `banner`; Spring không tự gọi lại constructor chỉ vì Environment thay đổi. Đây là ví dụ về **snapshot tại thời điểm khởi tạo**.

### 3.2. PropertySource và thứ tự ưu tiên

Các nguồn thường gặp:

- File cấu hình packaged như `application.yml`.
- File cấu hình bên ngoài và file theo profile.
- Environment variables.
- JVM system properties.
- Command-line arguments.
- Nguồn cấu hình tích hợp, ví dụ Config Server hoặc nguồn tùy chỉnh.

Thứ tự chính xác phụ thuộc phiên bản Spring Boot, cách khởi động và cơ chế tích hợp. Không nên đoán precedence từ tên nguồn; khi có nhiều nguồn cùng khai báo một khóa, hãy kiểm tra tài liệu của phiên bản đang dùng và đo giá trị thực tế.

Có thể hình dung một số nguồn được ưu tiên cao hơn nguồn khác. Nếu `app.banner` xuất hiện ở cả file mặc định và command line, giá trị hiệu lực có thể đến từ command line. Khi nguồn có ưu tiên cao bị gỡ bỏ, giá trị tra cứu có thể quay về nguồn thấp hơn vẫn còn.

### 3.3. Thay nội dung source khác với thay tập PropertySource

Có hai thao tác khác nhau:

1. **Cập nhật dữ liệu trong một PropertySource có thể thay đổi:** ví dụ map đang được quản lý được cập nhật.
2. **Thay thế/thêm/gỡ một PropertySource:** ví dụ thêm một nguồn override ở đầu danh sách.

Việc thay đổi một file trên đĩa không mặc nhiên khiến Spring Boot theo dõi file và cập nhật Environment đang chạy. Cần một cơ chế reload/config refresh thực sự để đọc dữ liệu mới và cập nhật các nguồn trong ứng dụng.

Khi nguồn thay đổi, kết quả tra cứu còn phụ thuộc vị trí của nguồn trong danh sách ưu tiên. Thêm nguồn mới ở vị trí không phù hợp có thể khiến giá trị cũ tiếp tục thắng.

## 4. Vì sao bean singleton thông thường không tự đổi?

### 4.1. Dependency injection diễn ra khi tạo bean

Với bean singleton, Spring thường tạo đối tượng một lần trong vòng đời ApplicationContext. Các giá trị `@Value`, constructor arguments hoặc cấu hình được bind vào bean tại thời điểm tạo.

Ví dụ:

~~~java
@Component
class GreetingService {
    private final String greeting;

    GreetingService(@Value("${app.greeting:Hello}") String greeting) {
        this.greeting = greeting;
    }

    String greet() {
        return greeting;
    }
}
~~~

Sau khi khởi tạo, field `greeting` giữ giá trị đã nhận. Nếu Environment đổi từ `Hello` thành `Xin chào`, việc gọi `greet()` trên singleton này vẫn có thể trả về `Hello`.

Đây không phải lỗi của Environment. Đối tượng đã nhận một giá trị và không có cơ chế nào tự thay field đó.

### 4.2. Những cách đọc có hành vi khác nhau

| Cách dùng | Giá trị được lấy khi nào? | Tự thấy Environment mới? |
| --- | --- | --- |
| `environment.getProperty(key)` trong mỗi lần gọi | Mỗi lần phương thức tra cứu chạy. | Có thể, nếu Environment/PropertySource thực sự đã được cập nhật. |
| `@Value` vào field/constructor của singleton | Khi bean được tạo. | Không tự động. |
| `@ConfigurationProperties` bean thông thường | Khi bean được binding ban đầu. | Chỉ được cập nhật lại nếu có cơ chế rebinding phù hợp. |
| `@RefreshScope` bean | Khi target được khởi tạo; target được cache. | Sau khi refresh scope invalidate target, lần gọi tiếp theo tạo target mới. |

Có thể inject `Environment` vào một bean và tra cứu mỗi lần gọi, nhưng cách này không phải lúc nào cũng là lựa chọn tốt. Nó làm phụ thuộc cấu hình xuất hiện trực tiếp trong logic, khó kiểm soát tính nhất quán giữa nhiều lần đọc và khó kiểm thử hơn so với một configuration object có kiểu rõ ràng.

### 4.3. Khi nào nên dùng snapshot?

Snapshot có ích khi giá trị được xem là bất biến trong vòng đời process, ví dụ một hằng số vận hành chỉ thay khi deploy/restart. Nó cũng tránh việc một thao tác nghiệp vụ đọc hai giá trị cấu hình khác nhau giữa chừng.

Nếu yêu cầu thực sự là cập nhật runtime, hãy chọn cơ chế cập nhật rõ ràng và xác định thời điểm hiệu lực, thay vì kỳ vọng singleton tự đọc lại.

## 5. @ConfigurationProperties và rebinding

### 5.1. Binding ban đầu

`@ConfigurationProperties` gom nhóm các khóa liên quan thành một object có kiểu. Ví dụ:

~~~yaml
app:
  routing:
    primary-region: ap-southeast
    fallback-enabled: true
~~~

Bean mutable:

~~~java
@ConfigurationProperties(prefix = "app.routing")
public class RoutingProperties {
    private String primaryRegion;
    private boolean fallbackEnabled;

    public String getPrimaryRegion() {
        return primaryRegion;
    }

    public void setPrimaryRegion(String primaryRegion) {
        this.primaryRegion = primaryRegion;
    }

    public boolean isFallbackEnabled() {
        return fallbackEnabled;
    }

    public void setFallbackEnabled(boolean fallbackEnabled) {
        this.fallbackEnabled = fallbackEnabled;
    }
}
~~~

Đăng ký bean bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(RoutingProperties.class)`, tùy cấu trúc ứng dụng. Spring Boot Binder lấy giá trị từ Environment để gán vào bean khi binding.

### 5.2. EnvironmentChangeEvent

Spring Cloud Context lắng nghe `EnvironmentChangeEvent`. Khi event được phát với danh sách các khóa thay đổi, các hành vi tiêu chuẩn gồm:

- Rebind các bean `@ConfigurationProperties` trong context.
- Cập nhật mức log cho các khóa thuộc nhóm `logging.level.*`.

Do đó, với mutable `@ConfigurationProperties`, việc thay đổi Environment và phát event thích hợp có thể làm bean nhận giá trị mới mà không cần khởi động lại toàn bộ ApplicationContext.

Tuy nhiên, rebinding không có nghĩa mọi bean trong ứng dụng đều được cập nhật. Bean singleton chỉ nhận `@Value` không tự động được rebinding theo cơ chế này. Các object tùy chỉnh cần xử lý event riêng nếu có yêu cầu.

### 5.3. Rebinding có giới hạn

Một số đặc điểm cần nhớ:

- Rebinding mutable configuration bean có thể cập nhật các field trên **cùng một instance** thay vì tạo object mới.
- Trong quá trình cập nhật, một thread khác có thể đọc object khi một số field đã đổi nhưng field khác chưa được cập nhật xong. Cần cân nhắc tính nhất quán và thread safety.
- Các giá trị bị gỡ khỏi Environment có thể được reset về mặc định cấp lớp khi rebinding theo cơ chế Spring Cloud; cần kiểm tra phiên bản và cấu trúc object.
- Constructor-bound immutable configuration, bao gồm Java Record dùng constructor binding, không thể được refresh theo cơ chế rebinding này trong tài liệu Spring Cloud hiện hành.
- Các nested object, collection và kiểu dữ liệu phức tạp có thể có hành vi binding riêng; không giả định cập nhật luôn là một thao tác atomic với mọi reader.

Nếu ứng dụng cần một cấu hình nhất quán như một snapshot duy nhất, cân nhắc `@RefreshScope` hoặc thiết kế immutable snapshot được thay thế có kiểm soát. Đừng dựa vào mutable bean để thực hiện cập nhật nhiều thuộc tính liên quan mà không có cơ chế đồng bộ.

### 5.4. Xác minh rebinding

Với ứng dụng đã cài Actuator và expose endpoint phù hợp, có thể dùng `/actuator/configprops` để kiểm tra giá trị đã bind vào configuration properties. Endpoint có thể hiển thị thông tin nhạy cảm nếu không cấu hình sanitization/bảo vệ phù hợp; chỉ bật trong môi trường và phạm vi truy cập được kiểm soát.

Việc Environment trả về giá trị mới nhưng `@ConfigurationProperties` vẫn cũ có thể chỉ ra rằng event/rebinding chưa chạy, bean chưa được đăng ký đúng, hoặc loại bean không hỗ trợ rebinding.

## 6. @RefreshScope: tạo lại target bean khi cần

### 6.1. Cách hoạt động

`@RefreshScope` cung cấp một scoped proxy và một cache các target bean đã khởi tạo. Khi bean được sử dụng lần đầu, target được tạo và lưu trong scope. Khi scope được refresh, cache target tương ứng bị invalidate. Lần gọi sau qua proxy sẽ tạo target mới, lúc đó dependency/configuration được inject từ trạng thái Environment hiện hành.

Ví dụ:

~~~java
@Component
@RefreshScope
class DynamicGreetingService {
    private final String greeting;

    DynamicGreetingService(@Value("${app.greeting:Hello}") String greeting) {
        this.greeting = greeting;
    }

    String greet() {
        return greeting;
    }
}
~~~

Caller thường inject proxy của `DynamicGreetingService`. Sau khi target cache bị xóa, caller tiếp tục gọi qua proxy; target mới được khởi tạo với giá trị cấu hình hiện hành.

### 6.2. Refresh không đồng nghĩa restart toàn bộ ứng dụng

Khi refresh scope:

1. Scoped target cache được xóa.
2. Proxy vẫn là đối tượng mà caller giữ.
3. Lần gọi phương thức tiếp theo tạo target mới.
4. Target mới đọc dependency và property ở thời điểm khởi tạo.

Không phải mọi bean singleton đều bị tạo lại. Không phải mọi resource đều tự đóng/mở lại đúng cách. Các dependency giữ connection, thread, scheduler hoặc state bên ngoài cần lifecycle rõ ràng để tránh rò rỉ tài nguyên hoặc dùng lẫn cấu hình cũ/mới.

### 6.3. Đặt annotation đúng chỗ

`@RefreshScope` trên một bean không tự biến tất cả bean mà nó phụ thuộc thành refresh scoped. Nếu một bean khác đã sao chép giá trị từ dependency vào field của nó khi khởi tạo, field đó không tự đổi chỉ vì dependency phía dưới được refresh.

Ví dụ:

- `DynamicGreetingService` thuộc refresh scope.
- `NotificationFacade` là singleton và lưu sẵn chuỗi greeting trong constructor.
- Refresh target của `DynamicGreetingService` không tự cập nhật field snapshot trong `NotificationFacade`.

Nếu facade gọi method qua proxy mỗi lần cần giá trị, nó có thể nhận kết quả từ target mới. Nếu facade cần tái tạo state nội bộ, nó cũng cần cơ chế lifecycle phù hợp hoặc được thiết kế lại để không lưu snapshot.

### 6.4. Bean không phải lúc nào cũng refresh được

Một số bean có state nội bộ phức tạp hoặc được đánh dấu không refreshable. Tài liệu Spring Cloud có danh sách `spring.cloud.refresh.never-refreshable` và `spring.cloud.refresh.extra-refreshable` để kiểm soát các trường hợp đặc biệt. Ví dụ, `HikariDataSource` là một trường hợp mặc định không refreshable trong tài liệu hiện hành; cần xem đúng release train trước khi thay đổi cấu hình này.

Không thêm `@RefreshScope` vào mọi bean. Hãy đánh giá:
- Bean có thực sự cần đổi cấu hình khi process đang chạy không?
- Có thể restart/rollout instance an toàn hơn không?
- Target mới có thể tạo trong khi request cũ còn sử dụng target cũ không?
- Resource cũ được đóng và resource mới được khởi tạo như thế nào?
- Có dependency downstream nào giữ lại state cũ không?

## 7. Quy trình cập nhật cấu hình và refresh

Một quy trình khái niệm:

~~~mermaid
sequenceDiagram
    participant Source as Config Source
    participant Env as Environment
    participant Refresher as Context Refresher
    participant Event as EnvironmentChangeEvent
    participant Props as ConfigurationProperties
    participant Scope as RefreshScope
    participant Caller as Application Caller

    Source->>Refresher: Có cấu hình mới
    Refresher->>Env: Cập nhật property sources
    Refresher->>Event: Publish changed keys
    Event->>Props: Rebind mutable properties
    Refresher->>Scope: Invalidate refresh targets
    Caller->>Scope: Gọi method qua proxy
    Scope-->>Caller: Tạo / dùng target mới
~~~

Các bước quan trọng:

1. **Cấu hình nguồn:** file, Config Server hoặc nguồn quản lý cấu hình được cập nhật.
2. **Nạp vào Environment:** cơ chế reload/refresh thực sự đọc lại hoặc thay đổi property source.
3. **Xác định khóa thay đổi:** hệ thống biết các property nào có giá trị khác.
4. **Phát event/rebind:** các bean `@ConfigurationProperties` và logger được cập nhật theo cơ chế Spring Cloud.
5. **Invalidate refresh scope:** target cache của bean thuộc `@RefreshScope` bị xóa.
6. **Tái tạo khi dùng:** target mới được khởi tạo khi proxy nhận lần gọi tiếp theo.
7. **Kiểm chứng:** đọc lại giá trị và kiểm tra hành vi nghiệp vụ.

Nếu chỉ thay file trên đĩa mà không có cơ chế nạp lại, bước 2 chưa xảy ra. Nếu chỉ thêm một PropertySource mới mà không chạy quy trình refresh/rebind, các bean đã khởi tạo vẫn có thể giữ giá trị cũ.

## 8. Kích hoạt refresh bằng Spring Cloud Context và Actuator

Spring Cloud Context cung cấp các API và endpoint hỗ trợ refresh. Cách kích hoạt cụ thể phụ thuộc dependency và phiên bản ứng dụng.

### 8.1. Actuator refresh endpoint

Trong ứng dụng có Spring Boot Actuator và Spring Cloud Context phù hợp, endpoint refresh có thể được expose:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Sau đó, nếu endpoint được bật, expose và bảo vệ đúng cách:

~~~bash
curl -X POST http://localhost:8080/actuator/refresh
~~~

Endpoint này thực hiện quy trình refresh của Spring Cloud cho instance nhận request, gồm cập nhật cấu hình theo context refresher và refresh các target trong refresh scope. Nó không phải một lệnh restart toàn bộ JVM.

Không mặc định endpoint này tồn tại hoặc được expose. Kiểm tra dependency, cấu hình management, security và tài liệu release train. Không public endpoint refresh ra Internet; đây là thao tác thay đổi runtime configuration.

### 8.2. Environment endpoint khác refresh endpoint

Một số phiên bản Spring Boot Actuator hỗ trợ endpoint `/actuator/env` để xem Environment; thao tác POST cập nhật Environment có thể yêu cầu cấu hình riêng và giới hạn key được phép. Khi endpoint này được bật, Spring Cloud có thể xử lý EnvironmentChangeEvent và rebinding các configuration properties.

Phân biệt:

| Endpoint | Vai trò chính | Điều cần xác minh |
| --- | --- | --- |
| `/actuator/env` | Xem Environment; POST cập nhật property nếu được bật/cấu hình. | Key được phép, property source, event/rebind và quyền truy cập. |
| `/actuator/refresh` | Chạy quy trình refresh của Spring Cloud Context. | Config source có được nạp lại và refresh scope có được invalidate? |
| `/actuator/restart` | Đóng và khởi động lại ApplicationContext khi endpoint/capability được bật. | Đây là lifecycle khác refresh target; không mặc định được bật. |

Endpoint `env` POST không phải cách thay thế an toàn cho một hệ thống quản lý cấu hình tập trung. Nếu sử dụng, cần allowlist property được cập nhật, authentication/authorization, audit log và giới hạn network.

### 8.3. Refresh qua API trong ứng dụng

Trong mã Java, Spring Cloud Context có abstraction `ContextRefresher` cho quy trình refresh. Một ví dụ minh họa về lời gọi:

~~~java
@Component
class RefreshCoordinator {
    private final ContextRefresher contextRefresher;

    RefreshCoordinator(ContextRefresher contextRefresher) {
        this.contextRefresher = contextRefresher;
    }

    Set<String> refreshConfiguration() {
        return contextRefresher.refresh();
    }
}
~~~

API cụ thể và bean availability phụ thuộc module Spring Cloud Context và phiên bản đang dùng. Không gọi refresh tùy tiện từ mỗi request người dùng; cần kiểm soát quyền, tần suất, nguồn cấu hình và hành vi đồng thời.

## 9. Một instance refresh không có nghĩa toàn bộ cluster đã refresh

Mỗi instance có ApplicationContext, Environment, bean và refresh scope riêng. Nếu có 5 instance và chỉ gọi `POST /actuator/refresh` đến một instance, chỉ instance đó được refresh qua endpoint đó.

Spring Cloud Config Client không mặc định polling liên tục để phát hiện mọi thay đổi trong Environment. Với ứng dụng scale-out, một cách phổ biến là dùng cơ chế broadcast như **Spring Cloud Bus** để gửi sự kiện refresh đến nhiều instance. Cách truyền event và phạm vi broadcast phải được cấu hình, bảo vệ và kiểm chứng.

### 9.1. Ví dụ trạng thái không đồng nhất

Giả sử cấu hình `app.routing.mode` đổi từ `legacy` sang `safe`:

| Instance | Environment | Bean thông thường đã snapshot | Refresh target sau lần gọi tiếp |
| --- | --- | --- | --- |
| `order-1` | `safe` | Có thể vẫn `legacy` | Target mới có thể nhận `safe` |
| `order-2` | `legacy` | `legacy` | Vẫn nhận `legacy` |
| `order-3` | `safe` | Có thể vẫn `legacy` | Target mới có thể nhận `safe` |

Bảng là tình huống minh họa. Nó cho thấy cần kiểm tra **theo từng instance**:
- Revision/giá trị Environment.
- Thời điểm event được nhận.
- Trạng thái rebinding.
- Refresh target đã được invalidate và tạo lại chưa.
- Request đang được xử lý bởi instance nào.

Nếu cấu hình thay đổi ảnh hưởng đến contract giữa các dịch vụ, trạng thái cluster không đồng nhất có thể gây lỗi. Cần rollout có kiểm soát, backward-compatible configuration hoặc một quy trình phối hợp đồng bộ.

### 9.2. Không polling mỗi instance một cách thiếu kiểm soát

Nếu mọi instance cùng polling Config Server với tần suất cao, hệ thống có thể tạo tải không cần thiết và thời điểm cập nhật vẫn không đồng nhất. Với quy mô nhiều instance, broadcast event hoặc triển khai thay đổi theo release/rollout có kiểm soát thường dễ quản lý hơn. Cần lựa chọn theo độ trễ chấp nhận được, độ tin cậy messaging và khả năng quan sát.

## 10. Kiểm thử sự khác biệt giữa Environment và bean

Một bài test tốt phải kiểm tra riêng:
- Giá trị mà Environment trả về.
- Giá trị đang nằm trong singleton snapshot.
- Giá trị trong mutable `@ConfigurationProperties`.
- Giá trị mà proxy `@RefreshScope` trả về sau khi target được tạo lại.

### 10.1. Bảng tình huống

| Tình huống | Environment | Singleton `@Value` | Mutable `@ConfigurationProperties` | `@RefreshScope` |
| --- | --- | --- | --- | --- |
| Khởi động lần đầu | Giá trị A | A | A | Target lần đầu nhận A |
| Thêm override B nhưng chưa refresh/rebind | Lần tra cứu có thể thấy B | Vẫn A | Vẫn A | Target cache hiện tại vẫn A |
| Phát event/rebind theo cơ chế phù hợp | B | Vẫn A | Có thể được rebind thành B | Chưa nhất thiết target cache được clear nếu chỉ phát event không đầy đủ quy trình refresh |
| Chạy quy trình refresh đầy đủ | B | Vẫn A | Được xử lý theo event/rebind | Target cache được invalidate; lần gọi sau tạo target B |

Bảng mô tả hành vi điển hình của các cơ chế Spring Cloud Context, không phải cam kết cho mọi loại bean hay mọi phiên bản. Khi viết test, hãy xác định rõ thao tác nào chỉ cập nhật Environment, thao tác nào phát event và thao tác nào gọi quy trình refresh đầy đủ.

### 10.2. Ví dụ test tư duy

Giả sử `app.greeting` ban đầu là `Hello`, sau đó được cập nhật thành `Xin chào`.

| Bước | Thao tác | Kết quả cần quan sát |
| --- | --- | --- |
| 1 | Khởi động context với `app.greeting=Hello`. | Environment, singleton snapshot và refresh bean đều thấy Hello ở lần đầu. |
| 2 | Thêm PropertySource override có `app.greeting=Xin chào`. | Tra cứu Environment thấy giá trị mới; singleton vẫn giữ Hello. |
| 3 | Rebind mutable `@ConfigurationProperties` qua event. | Object properties phản ánh giá trị mới theo cơ chế rebinder. |
| 4 | Chạy refresh scope. | Target cũ bị invalidate; gọi proxy lần tiếp theo tạo target mới với giá trị mới. |
| 5 | Gọi lại singleton snapshot. | Vẫn Hello nếu không có cơ chế cập nhật riêng. |
| 6 | Gọi lại EnvironmentInspector. | Trả Xin chào nếu PropertySource mới vẫn đang có ưu tiên cao. |

Có thể dùng `MapPropertySource` trong test để tạo nguồn override, nhưng cần đảm bảo source được thêm vào đúng `MutablePropertySources` và đúng thứ tự ưu tiên. Để kiểm thử end-to-end quy trình Spring Cloud, ưu tiên API refresh hoặc endpoint phù hợp thay vì tự mô phỏng một phần event rồi kết luận toàn bộ refresh hoạt động.

### 10.3. Những assertion cần có

- `Environment.getProperty(key)` trả giá trị mới sau khi source được cập nhật.
- Singleton dùng `@Value` không tự đổi nếu không có cơ chế đặc biệt.
- Mutable `@ConfigurationProperties` được rebind khi event và rebinder thực sự chạy.
- Constructor-bound/record config không được coi là refreshable.
- Scoped proxy tiếp tục được caller sử dụng, nhưng target được tạo lại sau khi scope refresh.
- Bean phụ thuộc vào target refresh không tự cập nhật state snapshot của chính nó.
- Sau refresh, các giá trị mới thực sự được dùng trong hành vi nghiệp vụ.
- Với nhiều instance, mỗi instance đều được xác minh độc lập.

## 11. Thiết kế cập nhật cấu hình an toàn

Refresh có thể tác động trực tiếp đến tài nguyên và hành vi nghiệp vụ. Cần quản lý như một thao tác vận hành.

### 11.1. Phân loại cấu hình

| Nhóm | Ví dụ | Chiến lược thường phù hợp |
| --- | --- | --- |
| **Cấu hình khởi động** | Port, SSL keystore, một số thành phần tạo lúc startup. | Restart/rollout có kiểm soát. |
| **Cấu hình runtime đơn giản** | Feature flag, ngưỡng giới hạn, thông điệp hiển thị. | Environment update + rebind hoặc refresh scope tùy cách dùng. |
| **Cấu hình tài nguyên** | Database URL, pool, connection factory. | Đánh giá lifecycle, đóng/mở tài nguyên, drain request và khả năng refresh của implementation. |
| **Cấu hình nhạy cảm** | Credential, signing key, token. | Secret management, rotate có kế hoạch, giới hạn log và quyền đọc. |
| **Cấu hình liên dịch vụ** | Tên service, endpoint, routing mode, protocol. | Tương thích ngược, rollout/broadcast, xác minh trên toàn cluster. |

Không phải mọi property đều nên thay đổi runtime. Với port, listener, security material hoặc cấu hình được đọc trong quá trình khởi tạo hạ tầng, restart có thể an toàn và dễ dự đoán hơn.

### 11.2. Tránh trạng thái nửa cũ nửa mới

Nếu một nghiệp vụ phụ thuộc ba giá trị có quan hệ với nhau, rebinding từng field trên mutable bean có thể khiến reader đồng thời quan sát trạng thái trung gian. Một số cách giảm rủi ro:

- Dùng một cấu hình snapshot bất biến và thay cả snapshot qua cơ chế đồng bộ.
- Dùng refresh-scoped target để thay target đã cache khi cần tạo lại object.
- Thiết kế config thay đổi theo version/revision và kiểm tra revision trước khi xử lý nghiệp vụ.
- Chia rollout thành các bước backward-compatible.
- Không thực hiện refresh trong lúc thao tác tài nguyên chưa có lifecycle rõ ràng.

`@RefreshScope` giúp quản lý target cache cho bean được đánh dấu, nhưng không tự biến mọi thay đổi trên toàn hệ thống thành một giao dịch atomic. Các instance khác nhau vẫn có thể refresh ở thời điểm khác nhau.

### 11.3. Bảo vệ thao tác refresh

- Chỉ expose endpoint refresh trong network quản trị cần thiết.
- Bắt buộc authentication và authorization.
- Ghi audit event: ai yêu cầu, thời điểm, instance, revision cấu hình và kết quả.
- Giới hạn tần suất, tránh refresh liên tục làm tạo lại tài nguyên.
- Kiểm tra cấu hình mới trước khi phát tán.
- Có kế hoạch rollback nếu target mới không khởi tạo được.
- Không log giá trị secret khi ghi nhận thay đổi.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Environment thấy giá trị mới nhưng method bean vẫn trả giá trị cũ. | Bean đã lưu snapshot qua `@Value` hoặc constructor. | Kiểm tra thời điểm bean được tạo; dùng rebinding/refresh scope nếu phù hợp. |
| File cấu hình đã đổi nhưng Environment vẫn cũ. | Source chưa được reload hoặc Config Client chưa lấy cấu hình mới. | Kiểm tra Config Server/source, cơ chế reload, profile và property precedence. |
| `@ConfigurationProperties` không cập nhật. | Bean chưa được đăng ký/bind, event không được phát hoặc kiểu binding không hỗ trợ refresh. | Kiểm tra scan/enable, event, Actuator configprops và kiểu constructor binding. |
| Record configuration không thay đổi sau refresh. | Constructor-bound immutable bean không hỗ trợ rebinding theo cơ chế này. | Dùng mutable bean phù hợp hoặc tạo lại bean/context theo thiết kế. |
| Bean `@RefreshScope` vẫn trả giá trị cũ. | Refresh endpoint chưa được gọi, endpoint không expose, target không nằm trong scope hoặc source chưa đổi. | Kiểm tra dependency, proxy, scope cache và Environment trước/sau refresh. |
| Một dependency vẫn giữ cấu hình cũ. | Dependency/facade đã snapshot giá trị từ bean khác. | Xác định bean nào cần proxy hoặc cần được tạo lại. |
| Một số instance dùng config mới, số khác dùng config cũ. | Refresh chỉ tới một instance hoặc broadcast không hoàn tất. | Ghi revision và thời điểm refresh trên từng instance. |
| Refresh làm request lỗi tạm thời. | Target mới khởi tạo thất bại hoặc resource cũ/mới có lifecycle xung đột. | Kiểm tra refresh scope health, exception, pool và trạng thái dependency. |
| Rebind gây giá trị trung gian không mong muốn. | Mutable bean được cập nhật field trong khi thread khác đang đọc. | Kiểm tra concurrency; cân nhắc immutable snapshot hoặc refresh-scoped bean. |
| Gọi `/actuator/refresh` trả 404/401/403. | Thiếu dependency, chưa expose endpoint hoặc security từ chối. | Kiểm tra Actuator, Spring Cloud Context, endpoint exposure và quyền truy cập. |

## 13. Bài thực hành: Environment, singleton và refresh scope

### 13.1. Chuẩn bị

Tạo ứng dụng Spring Boot có Spring Cloud Context tương thích với release train đã chọn. Cài Actuator nếu muốn dùng endpoint quản trị trong lab. Cấu hình ban đầu:

~~~yaml
app:
  greeting: "Hello"
  routing:
    mode: "legacy"

management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Cấu hình expose ở trên chỉ dành cho lab; production phải giới hạn endpoint và bảo vệ truy cập.

Tạo ba bean:

1. `EnvironmentInspector`: gọi `environment.getProperty("app.greeting")` mỗi lần request.
2. `GreetingSnapshot`: nhận `@Value` trong constructor và lưu field.
3. `DynamicGreetingService`: `@RefreshScope`, nhận cùng property trong constructor.

Một controller lab có thể gọi ba bean và trả kết quả để so sánh. Chỉ expose endpoint này trong môi trường test, không dùng để hiển thị cấu hình nhạy cảm.

### 13.2. Thử nghiệm

1. Khởi động ứng dụng với `app.greeting=Hello`.
2. Gọi endpoint lab và ghi lại ba giá trị.
3. Cập nhật property source thông qua cơ chế quản lý cấu hình đang dùng, ví dụ Config Server hoặc thao tác test có kiểm soát.
4. Xác nhận Environment tra cứu giá trị mới.
5. Trước refresh, gọi lại endpoint và ghi nhận singleton snapshot cùng refresh target đang cache.
6. Gọi quy trình refresh được hỗ trợ cho instance lab.
7. Gọi lại endpoint; quan sát singleton snapshot, Environment và refresh target.
8. Nếu dùng nhiều instance, lặp lại kiểm tra từng instance và ghi nhận revision.
9. Thử giá trị cấu hình không hợp lệ để quan sát lỗi binding/khởi tạo target.
10. Khôi phục cấu hình ban đầu và xác nhận ứng dụng hoạt động ổn định.

### 13.3. Bảng kết quả

| Mốc | Environment | Singleton snapshot | Refresh target | Kết quả |
| --- | --- | --- | --- | --- |
| Khởi động | Hello | Hello | Hello | Tự ghi |
| Source đổi, chưa refresh | Xin chào | Hello | Có thể vẫn Hello | Tự ghi |
| Sau refresh đầy đủ | Xin chào | Hello | Xin chào khi target mới được gọi | Tự ghi |
| Instance chưa nhận event | Giá trị cũ | Giá trị cũ | Target cũ | Tự ghi |

Bảng là kỳ vọng cho cấu trúc bean được mô tả. Kết quả thực tế cần được xác minh theo phiên bản và cách cập nhật source. Nếu singleton được thiết kế để tra cứu Environment mỗi lần gọi, kết quả của singleton đó sẽ khác ví dụ snapshot.

## 14. Checklist hoàn thành

- [ ] Phân biệt nguồn cấu hình, Environment và bean đã khởi tạo.
- [ ] Giải thích được thứ tự ưu tiên của PropertySource và cách kiểm chứng giá trị hiệu lực.
- [ ] Giải thích vì sao `@Value` trong singleton không tự cập nhật khi Environment đổi.
- [ ] Phân biệt tra cứu Environment mỗi lần gọi với snapshot trong field.
- [ ] Dùng được `@ConfigurationProperties` và biết điều kiện rebinding.
- [ ] Hiểu vai trò `EnvironmentChangeEvent` với configuration properties và logging.
- [ ] Biết giới hạn của mutable rebind và constructor-bound/Record.
- [ ] Giải thích scoped proxy, target cache và thời điểm target `@RefreshScope` được tạo lại.
- [ ] Phân biệt refresh bean với restart toàn bộ ApplicationContext.
- [ ] Kiểm tra được endpoint/ContextRefresher và bảo vệ thao tác refresh.
- [ ] Xác minh được trạng thái Environment/bean trên từng instance trong cluster.
- [ ] Có test chứng minh giá trị trước/sau source update, event và refresh.
- [ ] Có chiến lược rollback, audit và xử lý cấu hình nhạy cảm.

**Tài liệu cần đối chiếu khi triển khai:** Spring Cloud Commons Reference về Application Context Services, Environment Changes, Refresh Scope và configuration properties; Spring Boot Reference về Environment, PropertySource, Actuator và externalized configuration. API, endpoint, loại bean refreshable và hành vi rebinding có thể khác theo release train, vì vậy hãy kiểm tra tài liệu đúng phiên bản của ứng dụng.
