# Nhận diện cấu hình Ribbon, Hystrix và Zuul còn sót trong dự án

Trong quá trình nâng cấp ứng dụng Spring Cloud, việc xóa một dependency rồi thấy project biên dịch thành công **chưa chứng minh** công nghệ cũ đã được loại bỏ. Ribbon có thể còn được kéo vào gián tiếp và vẫn tham gia chọn instance; Hystrix có thể còn được gọi qua annotation, Feign builder hoặc fallback; Zuul 1 có thể vẫn khởi tạo reverse proxy và giữ route cũ. Ngược lại, một dòng cấu hình `zuul` hoặc một class có chữ `Hystrix` trong tên chưa đủ để kết luận runtime đang dùng thư viện legacy.

Bài thuộc chương **Tương thích và nâng cấp** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Ta sẽ nhận diện dấu vết của **Netflix Ribbon, Hystrix và Zuul 1** theo bốn nguồn bằng chứng: dependency graph, source code, cấu hình có hiệu lực và hành vi runtime. Sau đó, ta ánh xạ đúng chức năng sang **Spring Cloud LoadBalancer**, **Spring Cloud CircuitBreaker** (ví dụ Resilience4j) và **Spring Cloud Gateway**, rồi lập quy trình loại bỏ an toàn và kiểm thử hồi quy.

> **Phạm vi:** “Ribbon” là Netflix Ribbon được tích hợp qua Spring Cloud Netflix; “Hystrix” là Netflix Hystrix và tích hợp Spring Cloud cũ; “Zuul” là Zuul 1/Spring Cloud Netflix Zuul. Bài không yêu cầu gỡ Eureka: Spring Cloud Netflix hiện vẫn có tài liệu và starter cho Eureka Client/Server. Cũng không xem `@LoadBalanced`, Spring Cloud OpenFeign hoặc mọi circuit breaker là công nghệ legacy.

## 1. Vì sao cần tìm dấu vết trước khi nâng cấp?

Các hệ thống lâu năm thường chứa một hoặc nhiều tình huống:

- Ứng dụng đã chuyển từ Ribbon sang Spring Cloud LoadBalancer nhưng starter Ribbon vẫn còn do một module nội bộ kéo vào.
- Code đã bỏ `@HystrixCommand`, nhưng `spring-cloud-starter-netflix-hystrix` vẫn nằm trong dependency graph và auto-configuration vẫn có thể được nạp.
- Một gateway đã có Spring Cloud Gateway nhưng vẫn khởi tạo Zuul 1 với route cũ.
- File `application.yml` chứa nhiều thuộc tính `ribbon.*`, `hystrix.*`, `zuul.*`; không rõ thuộc tính nào còn được bind.
- Một số profile, biến môi trường hoặc Config Server vẫn ghi đè cấu hình cũ.
- Build local chạy qua, nhưng image production dùng profile hoặc dependency graph khác.
- Dashboard/alert cũ vẫn mang tên “Hystrix” dù runtime đã chuyển sang Resilience4j.

Tác động không chỉ là dependency thừa:

| Dấu vết còn sót | Rủi ro |
|---|---|
| Ribbon starter/artifact | Hai implementation load balancing cùng tồn tại; ở một số release train cũ Ribbon có thể được ưu tiên khi cả hai cùng có mặt |
| Hystrix starter/code | Timeout, thread isolation, fallback và metrics không còn khớp với cấu hình mới |
| Zuul 1 starter/routes | Proxy cũ tiếp tục nhận traffic, filter và routing behavior khác gateway mới |
| Properties legacy | Cấu hình tưởng đã migrate nhưng thực tế bị bỏ qua; đội vận hành hiểu sai timeout/retry |
| Transitive dependency | Gỡ direct dependency nhưng thư viện legacy vẫn nằm trên runtime classpath |
| Dashboard/metrics cũ | Quan sát sai trạng thái, cảnh báo không phản ánh implementation hiện tại |

Spring Cloud từng công bố Ribbon, Hystrix và Zuul 1 đi vào **maintenance mode** từ Spring Cloud Greenwich; khuyến nghị thay thế lần lượt là Spring Cloud LoadBalancer, Resilience4j và Spring Cloud Gateway. Maintenance mode trong thông báo lịch sử có nghĩa ngừng phát triển tính năng mới và chỉ xem xét blocker/security fixes theo giai đoạn hỗ trợ được nêu ở thời điểm đó. Với release train hiện hành, hãy đối chiếu tài liệu và compatibility matrix hiện tại thay vì giả định mọi module còn hỗ trợ như nhau.

## 2. Nhận diện bốn lớp bằng chứng

Không kết luận chỉ từ một kết quả tìm kiếm. Một dự án có thể chứa tài liệu migration cũ, ví dụ trong test hoặc dependency chỉ dùng cho module khác.

| Lớp | Câu hỏi | Bằng chứng cần lưu |
|---|---|---|
| **Dependency graph** | Artifact legacy có nằm trong compile/runtime/test classpath không? | Maven/Gradle tree, đường dẫn dependency kéo vào |
| **Source code** | Có class, annotation, API legacy đang được gọi không? | Import, annotation, bean, filter, command, builder |
| **Configuration** | Có thuộc tính legacy được load và bind ở profile thực tế không? | `application*.yml`, env vars, Config Server, Helm |
| **Runtime behavior** | Implementation nào đang xử lý request? | Condition evaluation, startup logs, routes, metrics, traces, integration tests |

Một dependency ở `testRuntimeClasspath` không đồng nghĩa ứng dụng production đang chạy nó. Một property nằm trong YAML không đồng nghĩa Spring Boot có component nào đọc nó. Ngược lại, dependency đến gián tiếp vẫn có thể hoạt động dù `pom.xml` không khai báo trực tiếp.

Phân loại kết quả theo từng module/service:

- **ACTIVE:** dependency/runtime bean/source path đang được sử dụng.
- **TRANSITIVE:** không khai báo trực tiếp nhưng được artifact khác kéo vào.
- **CONFIG-ONLY:** chỉ còn cấu hình legacy, chưa thấy component đọc hoặc bind.
- **CODE-ONLY:** còn class/import/annotation, cần xác minh có được gọi hay không.
- **HISTORICAL:** chỉ xuất hiện trong tài liệu, changelog, migration note hoặc test fixture không chạy production.
- **UNKNOWN:** chưa đủ bằng chứng; cần kiểm tra runtime profile hoặc dependency path.

## 3. Nhận diện dependency Maven và Gradle

### 3.1. Artifact cần tìm

| Công nghệ | Starter/artifact Spring Cloud thường gặp | Artifact nền tảng thường gặp |
|---|---|---|
| Ribbon | `spring-cloud-starter-netflix-ribbon`, `spring-cloud-netflix-ribbon` | `com.netflix.ribbon:ribbon-*`, `ribbon-loadbalancer` |
| Hystrix | `spring-cloud-starter-netflix-hystrix`, `spring-cloud-netflix-hystrix` | `com.netflix.hystrix:hystrix-core`, `hystrix-javanica`, `hystrix-metrics-event-stream` |
| Hystrix Dashboard/Turbine | `spring-cloud-starter-netflix-hystrix-dashboard`, `spring-cloud-starter-netflix-turbine` | `hystrix-dashboard`, `turbine-*` |
| Zuul 1 | `spring-cloud-starter-netflix-zuul`, `spring-cloud-netflix-zuul` | `com.netflix.zuul:zuul-core` |
| Thành phần mới cần phân biệt | `spring-cloud-starter-loadbalancer`, `spring-cloud-starter-circuitbreaker-*`, Spring Cloud Gateway starter | Resilience4j, Micrometer |

Tên artifact có thể khác theo thế hệ Spring Cloud hoặc được chia module. Dùng dependency tree của **đúng module và đúng configuration** làm bằng chứng cuối cùng; bảng trên là danh sách điểm bắt đầu để tìm.

### 3.2. Maven: xem dependency tree

Từ thư mục có `pom.xml`:

~~~powershell
.\mvnw.cmd dependency:tree -Dverbose
~~~

Lọc từng nhóm artifact:

~~~powershell
.\mvnw.cmd dependency:tree -Dverbose "-Dincludes=org.springframework.cloud:spring-cloud-starter-netflix-ribbon,org.springframework.cloud:spring-cloud-netflix-ribbon,com.netflix.ribbon:*"
.\mvnw.cmd dependency:tree -Dverbose "-Dincludes=org.springframework.cloud:spring-cloud-starter-netflix-hystrix,org.springframework.cloud:spring-cloud-netflix-hystrix,com.netflix.hystrix:*"
.\mvnw.cmd dependency:tree -Dverbose "-Dincludes=org.springframework.cloud:spring-cloud-starter-netflix-zuul,org.springframework.cloud:spring-cloud-netflix-zuul,com.netflix.zuul:*"
~~~

Nếu không dùng Maven Wrapper, thay `.\mvnw.cmd` bằng `mvn`. Một số Maven Dependency Plugin versions có cách diễn giải wildcard/includes khác nhau; nếu filter không trả kết quả như mong đợi, chạy `dependency:tree` không filter và tìm trực tiếp trong output.

Ví dụ dependency kéo vào gián tiếp:

~~~text
order-service
\- com.example:legacy-http-adapter:1.4.0
   \- org.springframework.cloud:spring-cloud-starter-netflix-ribbon:...
      \- com.netflix.ribbon:ribbon-loadbalancer:...
~~~

Trong trường hợp này, xóa dòng Ribbon khỏi `order-service` không đủ vì nguồn kéo vào là `legacy-http-adapter`. Cần nâng cấp, thay thế hoặc exclude đúng dependency tại edge đó sau khi xác nhận adapter không cần API legacy.

Để xem POM sau khi kế thừa parent/BOM/profiles:

~~~powershell
.\mvnw.cmd help:effective-pom -Doutput=target/effective-pom.xml
~~~

Effective POM giúp phát hiện dependency được thêm từ parent/profile và version được quản lý bởi BOM. Nó không thay thế `dependency:tree`: artifact được khai báo trong POM chưa chắc xuất hiện trong runtime graph sau khi exclusions/profiles được áp dụng.

### 3.3. Gradle: kiểm tra runtimeClasspath và đường kéo vào

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-starter-netflix-ribbon --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-netflix-ribbon --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-starter-netflix-hystrix --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-netflix-hystrix --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-starter-netflix-zuul --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-netflix-zuul --configuration runtimeClasspath
~~~

Nếu artifact chỉ xuất hiện ở `testRuntimeClasspath`, ghi nhận đúng scope. Với multi-project Gradle, chạy trên đúng project path, ví dụ:

~~~powershell
.\gradlew.bat :services:order-service:dependencyInsight --dependency spring-cloud-netflix-ribbon --configuration runtimeClasspath
~~~

Nếu dùng version catalog, platform/BOM, convention plugin hoặc dependency constraints, lần theo nơi khai báo; không sửa trực tiếp version đã được quản lý tập trung khi chưa hiểu nguồn.

### 3.4. Kiểm tra dependency graph sau khi loại bỏ

Sau khi migrate, chạy lại cùng các lệnh với **cùng module và configuration**. Mục tiêu là xác nhận:

- Starter/artifact legacy không còn trên runtime classpath.
- Không có adapter nội bộ kéo lại artifact đó.
- Dependency thay thế vẫn hiện diện ở đúng module cần dùng.
- Test scope chỉ còn nếu có lý do rõ ràng, không bị đóng gói vào artifact production.
- Không loại nhầm Eureka Client/Server chỉ vì chúng thuộc Spring Cloud Netflix.

## 4. Tìm dấu vết trong source code

Tìm cả import, annotation, class name và API sử dụng. Không chỉ tìm starter artifact vì code có thể dùng thư viện nền tảng trực tiếp.

### 4.1. Ribbon

Các dấu hiệu đáng kiểm tra:

~~~java
import com.netflix.loadbalancer.ILoadBalancer;
import com.netflix.loadbalancer.IRule;
import com.netflix.loadbalancer.Server;
import com.netflix.loadbalancer.ServerList;
import com.netflix.loadbalancer.ServerListFilter;
import org.springframework.cloud.netflix.ribbon.RibbonClient;
import org.springframework.cloud.netflix.ribbon.RibbonClients;
import org.springframework.cloud.netflix.ribbon.RibbonLoadBalancedRetryFactory;
~~~

Từ khóa thường gặp:

- `@RibbonClient`, `@RibbonClients`
- `ILoadBalancer`, `IRule`, `ServerList`, `ServerListFilter`, `IPing`
- `RibbonClientConfiguration`, `RibbonLoadBalancerClient`
- `ZoneAvoidanceRule`, `WeightedResponseTimeRule`, `BestAvailableRule`, `AvailabilityFilteringRule`
- `RibbonLoadBalancedRetryFactory`
- `com.netflix.loadbalancer.*`

Các tên rule hoặc class có thể xuất hiện trong tài liệu/test cũ. Hãy xem chúng có được import, tạo bean hoặc khai báo bằng properties trong runtime không.

### 4.2. Hystrix

~~~java
import com.netflix.hystrix.HystrixObservableCommand;
import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;
import com.netflix.hystrix.contrib.javanica.annotation.HystrixProperty;
import org.springframework.cloud.netflix.hystrix.EnableHystrix;
~~~

Dấu hiệu thường gặp:

- `@EnableHystrix`, `@HystrixCommand`, `@DefaultProperties`
- `HystrixCommand`, `HystrixObservableCommand`, `HystrixCollapser`
- `HystrixFeign`, `HystrixFeign.Builder`
- `HystrixCircuitBreaker`, `HystrixCommandProperties`
- `HystrixMetricsStreamServlet`, `/hystrix.stream`
- `com.netflix.hystrix.*`, `org.springframework.cloud.netflix.hystrix.*`

**Không kết luận từ `@EnableCircuitBreaker` một mình.** Annotation này từng là abstraction/entry point trong các thế hệ Spring Cloud; cần xem implementation cụ thể và dependency graph. Tương tự, một class tên `CircuitBreaker` có thể là code domain tự viết.

### 4.3. Zuul 1

~~~java
import org.springframework.cloud.netflix.zuul.EnableZuulProxy;
import org.springframework.cloud.netflix.zuul.EnableZuulServer;
import org.springframework.cloud.netflix.zuul.filters.ProxyRequestHelper;
import com.netflix.zuul.ZuulFilter;
~~~

Dấu hiệu thường gặp:

- `@EnableZuulProxy`, `@EnableZuulServer`
- `ZuulFilter`, `ZuulFilterFactory`, `ZuulProperties`
- `RibbonRoutingFilter`, `SimpleHostRoutingFilter`, `PreDecorationFilter`
- `com.netflix.zuul.*`, `org.springframework.cloud.netflix.zuul.*`
- `/zuul` servlet mapping hoặc `/hystrix.stream` đi qua proxy cũ
- Custom pre/route/post/error filters kế thừa `ZuulFilter`

Nếu code có class `ZuulFilter` tự định nghĩa trong package khác, không tự động coi là Netflix Zuul. Kiểm tra fully qualified name và dependency.

### 4.4. Lệnh tìm nhanh bằng ripgrep

Chạy từ root repo:

~~~powershell
rg -n -i --hidden -g '!**/.git/**' -g '!**/target/**' -g '!**/build/**' -g '!**/.gradle/**' -g '!**/.idea/**' 'spring-cloud-(starter-)?netflix-(ribbon|hystrix|zuul)|com\.netflix\.(loadbalancer|hystrix|zuul)|@Ribbon(Client|Clients)|@Enable(Hystrix|ZuulProxy|ZuulServer)|@HystrixCommand|HystrixFeign|RibbonLoadBalancerClient|ZuulFilter' .
~~~

Lệnh trên tìm source, POM, Gradle, YAML và XML ở repo; exclusions tránh kết quả build/generated phổ biến. Nếu repository dùng folder khác để sinh source hoặc config, điều chỉnh glob thay vì mặc định coi “không có kết quả” là đã sạch.

Tìm riêng các prefix cấu hình:

~~~powershell
rg -n -i --hidden -g '!**/.git/**' -g '!**/target/**' -g '!**/build/**' '(^|[[:space:]])(ribbon|hystrix|zuul):|\.ribbon\.|hystrix\.command|hystrix\.threadpool|zuul\.routes|zuul\.prefix|zuul\.retryable' .
~~~

Nếu PowerShell không có `rg`, dùng `Get-ChildItem -Recurse -File` kết hợp `Select-String`, nhưng cần loại `target`, `build`, `.git` và generated files để giảm noise.


## 5. Nhận diện cấu hình legacy còn sót

Tìm property prefix rộng trước, rồi đối chiếu key cụ thể với phiên bản Spring Cloud cũ mà dự án đang dùng.

### 5.1. Ribbon properties

~~~yaml
ribbon:
  ConnectTimeout: 1000
  ReadTimeout: 3000
  MaxAutoRetries: 1
  MaxAutoRetriesNextServer: 1

inventory-service:
  ribbon:
    NFLoadBalancerRuleClassName: com.netflix.loadbalancer.ZoneAvoidanceRule
~~~

Dấu hiệu khác:

- `ribbon.*` và `<service-id>.ribbon.*`
- `ribbon.eureka.enabled`
- `NFLoadBalancerRuleClassName`, `NIWSServerListClassName`, `NIWSServerListFilterClassName`
- `ConnectTimeout`, `ReadTimeout`, `MaxAutoRetries`, `MaxAutoRetriesNextServer`

Đây là ví dụ cấu hình Ribbon cũ. Đừng copy các key sang Spring Cloud LoadBalancer và mong chúng tự hoạt động; API cấu hình, supplier và retry policy là khác nhau.

### 5.2. Hystrix properties

~~~yaml
hystrix:
  command:
    default:
      execution:
        isolation:
          thread:
            timeoutInMilliseconds: 2500
  threadpool:
    default:
      coreSize: 20
~~~

Dấu hiệu khác:

- `hystrix.command.*`
- `hystrix.threadpool.*`
- `hystrix.collapser.*`
- `hystrix.shareSecurityContext`
- `feign.hystrix.enabled` trong các thế hệ Spring Cloud OpenFeign cũ
- `hystrix.stream`, `hystrix.dashboard`, `turbine.*`

Không nhầm timeout của Hystrix với timeout của HTTP client. Một lệnh Hystrix có thể bao quanh nhiều thao tác, còn connect/read timeout được áp dụng ở transport; khi migrate phải xác định deadline và vị trí mỗi timeout.

### 5.3. Zuul properties

~~~yaml
zuul:
  prefix: /api
  ignored-services: "*"
  routes:
    inventory:
      path: /inventory/**
      serviceId: inventory-service
      stripPrefix: true
  retryable: false
  host:
    connect-timeout-millis: 1000
    socket-timeout-millis: 3000
~~~

Dấu hiệu khác:

- `zuul.routes.*`, `zuul.prefix`, `zuul.ignored-services`
- `zuul.retryable`, `zuul.sensitive-headers`
- `zuul.host.*`
- `zuul.ribbon-isolation-strategy`
- `zuul.servlet-path`
- Route IDs và path rewrite được khai báo trong application config hoặc Config Server.

Đừng coi mọi key có chữ `route` là Zuul. `spring.cloud.gateway.routes` thuộc Spring Cloud Gateway; một property `app.zuul.routeName` do ứng dụng tự định nghĩa cũng không chứng minh Zuul 1 đang chạy.

### 5.4. Cấu hình có thể đến từ đâu?

Tìm không chỉ application.yml:

- `application-{profile}.yml` và `application-{profile}.properties`.
- `bootstrap.yml`/`bootstrap.properties` ở các thế hệ Spring Cloud Config cũ.
- Config Server repository, profile và label caller đang sử dụng.
- Biến môi trường như `RIBBON_READ_TIMEOUT`, `HYSTRIX_COMMAND_DEFAULT_EXECUTION_ISOLATION_THREAD_TIMEOUT_IN_MILLISECONDS`, `ZUUL_ROUTES_*`.
- `SPRING_APPLICATION_JSON`, JVM system properties và command-line arguments.
- Helm values, Kubernetes ConfigMap/Secret, Docker Compose, manifest và pipeline deploy.
- Test resources có profile riêng; không nhầm test config với production config.

Spring Boot có quy tắc property source và precedence. Một key trong file mặc định có thể bị ghi đè ở environment hoặc Config Server; hãy xem **effective runtime configuration** trong đúng profile.

### 5.5. Kiểm tra cấu hình đang được bind ở runtime

Trong môi trường local/staging được bảo vệ, Spring Boot Actuator có thể giúp:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions,beans,configprops,env
~~~

Các endpoint có ích:

| Endpoint | Dùng để |
|---|---|
| `/actuator/conditions` | Xem auto-configuration nào match hoặc bị loại và lý do |
| `/actuator/beans` | Kiểm tra bean LoadBalancer, Feign, Gateway hoặc legacy có được tạo |
| `/actuator/configprops` | Xem properties được `@ConfigurationProperties` bind |
| `/actuator/env` | Xem property sources và giá trị hiệu lực khi endpoint/configuration cho phép |

**Không public các endpoint `env`, `configprops`, `beans`, `conditions` ra Internet.** Chúng có thể lộ cấu hình, classpath và thông tin hạ tầng; chỉ bật tạm ở môi trường được kiểm soát và áp dụng authentication/network restrictions. Một property legacy không xuất hiện trong `configprops` chưa đủ chứng minh không ai đọc nó bằng `@Value` hoặc `Environment.getProperty`.

## 6. Phân biệt dấu vết thật với false positives

Không gỡ thành phần hiện hành chỉ vì tên package có chữ Netflix hoặc có từ khóa tương tự.

| Kết quả tìm kiếm | Kết luận ban đầu |
|---|---|
| `spring-cloud-starter-netflix-ribbon` trên runtimeClasspath | Bằng chứng mạnh Ribbon integration còn ở classpath; tìm nguồn kéo vào và kiểm tra implementation được dùng |
| `com.netflix.ribbon:ribbon-loadbalancer` chỉ trong test fixture | Chưa chứng minh production dùng Ribbon |
| `spring-cloud-starter-netflix-hystrix` trên runtimeClasspath | Hystrix integration còn trên classpath; kiểm tra source/config/auto-configuration |
| `@EnableCircuitBreaker` nhưng không có Hystrix dependency | Không đủ bằng chứng Hystrix; có thể là abstraction hoặc code cũ chưa được xóa |
| `spring-cloud-starter-netflix-zuul` + `@EnableZuulProxy` | Bằng chứng mạnh Zuul 1 đang được cấu hình |
| `zuul` trong URL nghiệp vụ, tên biến hoặc tài liệu | False positive có thể xảy ra |
| `spring-cloud-starter-netflix-eureka-client` | Eureka Client, **không phải** Ribbon/Hystrix/Zuul |
| `spring-cloud-starter-openfeign` | OpenFeign; không đồng nghĩa Hystrix hay Ribbon |
| `@LoadBalanced` | Annotation tích hợp client-side LoadBalancer; không phải dấu hiệu Ribbon |
| `spring-cloud-starter-loadbalancer` | Thành phần thay thế hiện hành cần giữ nếu module đang sử dụng |
| `resilience4j-*` hoặc Spring Cloud CircuitBreaker | Không phải Hystrix; kiểm tra đúng implementation và cấu hình mới |

### Ba tình huống dễ nhầm

**Eureka vẫn có thể được giữ lại.** Spring Cloud Netflix hiện tiếp tục cung cấp Eureka Client/Server. Việc module từng được phân phối trong cùng Spring Cloud Netflix không có nghĩa tất cả các module Netflix đều legacy hoặc phải gỡ cùng lúc.

**OpenFeign không đồng nghĩa Ribbon.** Feign có thể tích hợp với Spring Cloud LoadBalancer thông qua dependency/integration phù hợp. Hãy xem `@FeignClient(name = "inventory-service")`, starter OpenFeign và LoadBalancer trên classpath; đừng xóa Feign chỉ vì ứng dụng từng dùng Feign + Ribbon.

**`@EnableCircuitBreaker` không đồng nghĩa Hystrix.** Xem import package, starter và implementation thực sự được tạo. Nếu dự án dùng Spring Cloud CircuitBreaker + Resilience4j thì không thay bằng một migration Hystrix không liên quan.


## 7. Lập inventory trước khi chỉnh sửa

Không bắt đầu bằng việc xóa tất cả từ khóa trong repo. Hãy lập bảng theo **module, profile và runtime scope** để biết thứ gì thực sự còn hoạt động.

| Module | Dấu vết | Dependency scope | Profile/runtime | Phân loại | Owner |
|---|---|---|---|---|---|
| order-service | `spring-cloud-starter-netflix-ribbon` | runtime, transitive từ legacy adapter | prod | TRANSITIVE/ACTIVE cần xác minh | Order team |
| inventory-client | `@RibbonClient` và `IRule` | compile | prod | CODE-ONLY/ACTIVE | Platform |
| payment-service | `hystrix.command.default.*` | config | prod | CONFIG-ONLY cần truy nguồn bind | Payment team |
| edge-gateway | `@EnableZuulProxy` | runtime | prod | ACTIVE | Edge team |
| catalog-service | tài liệu nhắc `HystrixCommand` | không có | docs | HISTORICAL | Catalog team |

Đây là dữ liệu minh họa; thay bằng bằng chứng thật của từng repository. Với mỗi dòng, ghi rõ đường dependency, file/line, profile, service ID/route, hành vi runtime và người chịu trách nhiệm.

### 7.1. Tìm tên biến môi trường và deployment config

Trong PowerShell, quét các thư mục triển khai cùng repository:

~~~powershell
rg -n -i --hidden -g '!**/.git/**' -g '!**/target/**' -g '!**/build/**' 'RIBBON_|HYSTRIX_|ZUUL_|spring\.cloud\.loadbalancer\.ribbon\.enabled|feign\.hystrix\.enabled' .
~~~

Nếu Config Server nằm ở repository khác, cần chạy cùng quy trình trên **đúng repo cấu hình** và đúng branch/label mà ứng dụng đang sử dụng. Không coi việc source repo không có property là bằng chứng Config Server không cung cấp property đó.

### 7.2. Kiểm tra effective runtime configuration

Có thể bật startup condition report tạm thời:

~~~powershell
java -jar app.jar --debug
~~~

Hoặc xem `/actuator/conditions` và `/actuator/configprops` trong môi trường local/staging được bảo vệ. Đối chiếu:

- Auto-configuration legacy nào được import/match.
- Bean nào được tạo theo service ID hoặc gateway context.
- Property source nào cung cấp key cũ.
- Profile nào được kích hoạt và thứ tự override.
- Có classpath condition nào khiến Ribbon/Hystrix/Zuul vẫn bật dù source code chính không còn annotation.

Condition report có thể không liệt kê mọi thao tác đọc property bằng `Environment` hoặc mọi bean được tạo thủ công. Kết hợp report với source search và dependency tree.

## 8. Quy trình migration an toàn theo từng lớp

### Bước 1 — Chốt version nền trước khi đổi thư viện

Ghi lại:

- Spring Boot version.
- Spring Cloud release train/BOM version.
- Java version.
- Maven/Gradle và plugin version.
- Các module cùng dùng dependency management chung.
- Runtime profile và cách nạp cấu hình ngoài.

Dùng Spring Cloud compatibility table để chọn release train tương thích với Spring Boot. Đừng nâng Boot, Spring Cloud, Java, HTTP client và cả ba công nghệ legacy trong cùng một thay đổi lớn nếu không có test coverage đủ tốt.

### Bước 2 — Xác định chức năng đang được dùng

Với mỗi dấu vết, trả lời:

- Ribbon đang thực hiện rule nào: Round Robin, zone, weighted, retry hay custom filtering?
- Hystrix đang bảo vệ operation nào; timeout, isolation, fallback và dashboard có ý nghĩa gì?
- Zuul đang phục vụ route nào; filter nào sửa header/path/authentication/rate limit?
- Những behavior đó có nằm ở API Gateway, service client, service adapter hay shared library?

Không migrate tên class; migrate **hành vi quan sát được và hợp đồng**.

### Bước 3 — Thay Ribbon trước ở một client/service ID

- Thêm Spring Cloud LoadBalancer starter tương thích BOM.
- Chuyển HTTP client sang URI logic bằng service ID.
- Dùng `@LoadBalanced RestClient.Builder`, `@LoadBalanced WebClient.Builder` hoặc OpenFeign integration phù hợp.
- Chuyển các rule cần thiết sang `ServiceInstanceListSupplier`, built-in supplier hoặc custom `ReactorServiceInstanceLoadBalancer`.
- Kiểm thử discovery, empty list, zone/hint/weight, retry, timeout và no-instance.
- Nếu có Ribbon per-client config, migrate riêng từng service ID; không tạo một policy global ngoài ý muốn.

Không giữ cả Ribbon và LoadBalancer chỉ để “fallback” nếu chưa hiểu implementation nào đang được chọn. Với một số release train cũ, tài liệu từng mô tả Ribbon có thể được ưu tiên khi cả hai starter cùng có mặt.

### Bước 4 — Thay Hystrix theo từng operation

- Xác định boundary của command: một HTTP call, một operation nghiệp vụ hay toàn workflow.
- Chọn Spring Cloud CircuitBreaker implementation và starter blocking/reactive phù hợp.
- Chuyển circuit breaker ID, failure classification, slow-call threshold, TimeLimiter và fallback.
- Thiết kế bulkhead/executor nếu trước đây dùng thread isolation.
- Tách connect/read timeout, deadline tổng và retry policy.
- Kiểm tra SecurityContext/MDC/trace propagation khi thay đổi executor.
- Chuyển metrics/dashboard sang Micrometer và monitoring backend.

Không biến fallback Hystrix thành fallback Resilience4j chỉ bằng cách giữ nguyên code response: cần xác nhận lỗi nào được record, ignore, retry hoặc trả về cho caller.

### Bước 5 — Thay Zuul 1 bằng Gateway

- Liệt kê toàn bộ routes, predicates, prefix, strip-prefix, rewrite, retry, sensitive headers và custom filters.
- Tạo route Spring Cloud Gateway với route ID ổn định.
- Chuyển từng pre/post/route/error filter thành GatewayFilter/GlobalFilter tương ứng.
- Thiết kế lại filter order, reactive execution và error handling.
- Nếu route đến service discovery, dùng URI `lb://service-id` và xác nhận LoadBalancer integration.
- Kiểm tra CORS, authentication, forwarded headers, cookie, request body, WebSocket và timeout theo route.
- Chuyển traffic từng nhóm route/canary; giữ rollback plan cho gateway.

Không chuyển code `ZuulFilter` thành `GlobalFilter` bằng cách đổi tên class. Vòng đời, ordering, request exchange, reactive execution và xử lý lỗi khác nhau. Filter blocking nặng có thể làm nghẽn event loop trong Gateway WebFlux; phải thiết kế lại và kiểm thử concurrency.

### Bước 6 — Gỡ dependency và config cũ sau khi behavior mới đã được xác nhận

- Xóa starter/direct dependencies legacy.
- Nếu dependency là transitive, xử lý ở dependency kéo vào hoặc nâng cấp module adapter.
- Xóa `@RibbonClient`, `@HystrixCommand`, `@EnableZuulProxy` và custom legacy classes sau khi call sites đã chuyển.
- Xóa key `ribbon.*`, `hystrix.*`, `zuul.*` trong mọi profile/deployment source sau khi đã thay semantics.
- Gỡ dashboard/alerts cũ sau khi metrics mới có coverage tương đương.
- Không xóa Eureka hoặc OpenFeign nếu chúng vẫn được sử dụng và tương thích.

### Bước 7 — Kiểm tra classpath và runtime lần cuối

Chạy lại dependency tree/insight, source scan, config scan và condition report. Sau đó kiểm thử bằng artifact/image được đóng gói giống production, không chỉ bằng test classpath của IDE.

## 9. Kiểm thử hồi quy sau migration

### 9.1. Ribbon → LoadBalancer

| Scenario | Kỳ vọng |
|---|---|
| Có 2+ instances cùng service ID | Client chọn một instance hợp lệ |
| Discovery list rỗng | Lỗi no-instance có thể quan sát, không gọi host giả |
| Instance unhealthy | Behavior theo health/discovery policy được xác định |
| Zone preference | Chọn đúng tập ưu tiên và hiểu rõ fallback |
| Weighted policy | Tỷ lệ chọn phù hợp metadata/weight |
| Retry | Attempts giới hạn, tránh instance đã lỗi nếu policy yêu cầu |
| RestClient/WebClient/OpenFeign | Tất cả gọi đúng service ID và dùng LoadBalancer integration |
| Nhiều service IDs | Custom config không leak sang client khác |

### 9.2. Hystrix → CircuitBreaker

| Scenario | Kỳ vọng |
|---|---|
| Backend success | Response bình thường, breaker CLOSED |
| Nhiều failures | Breaker chuyển OPEN theo threshold |
| OPEN | Call bị chặn nhanh, fallback/error đúng contract |
| HALF_OPEN | Probe có giới hạn và recovery đúng |
| 4xx nghiệp vụ | Không bị tính thành dependency outage nếu policy đã ignore |
| Slow response | TimeLimiter/timeout hoạt động theo deadline |
| Concurrency cao | Bulkhead/concurrency limit giữ tài nguyên trong giới hạn |
| Fallback | Không giả dữ liệu thành công hoặc gây side effect lặp |
| Metrics | State, failures, not-permitted, fallback và latency quan sát được |

### 9.3. Zuul → Gateway

| Scenario | Kỳ vọng |
|---|---|
| Route predicate match | Request tới đúng backend |
| Path prefix/rewrite | Backend nhận đúng request path |
| Header/cookie | Chính sách forward/remove đúng |
| Authentication | Security filters thực thi đúng thứ tự |
| Retry/timeout | Không tạo retry storm hoặc vượt deadline |
| Backend unavailable | Error/fallback có cấu trúc |
| High concurrency | Không block event loop; p95/p99 theo SLO |
| Multiple routes | Không route nhầm service ID hoặc public endpoint |
| Rollback | Có thể chuyển traffic về gateway version cũ theo kế hoạch |

### 9.4. Kiểm tra không còn legacy ở runtime

Acceptance criteria nên có:

- Không có Ribbon/Hystrix/Zuul 1 artifacts trên production runtimeClasspath, trừ trường hợp ngoại lệ đã được chấp thuận và ghi rõ.
- Không có bean/auto-configuration legacy đang active.
- Không còn call sites legacy trên production code path.
- Không còn properties legacy được nạp từ config repo, env vars hoặc deployment manifests.
- Các chức năng tương đương đã được kiểm thử ở LoadBalancer/CircuitBreaker/Gateway.
- Eureka Client/Server và OpenFeign còn hoạt động nếu vẫn thuộc kiến trúc.
- Metrics, logs, dashboards, alerts và runbooks đã chuyển sang tên/semantics mới.
- Đã chạy smoke/integration tests trên image gần production và có rollback plan.

## 10. Các lỗi migration thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Gỡ Ribbon nhưng Feign không gọi được service ID | Thiếu LoadBalancer integration hoặc Feign cấu hình URL sai | Starter, `@FeignClient(name=...)`, runtime dependency |
| Cả Ribbon và LoadBalancer còn trong graph | Adapter cũ kéo Ribbon transitive | `dependency:tree`/`dependencyInsight` và đường dependency |
| Đặt `spring.cloud.loadbalancer.ribbon.enabled=false` nhưng không có tác dụng | Dùng release train không còn property chuyển tiếp này | Kiểm tra docs đúng version, loại Ribbon khỏi classpath |
| `ribbon.ReadTimeout` thay đổi nhưng timeout không đổi | HTTP client mới không bind property Ribbon | Cấu hình timeout của transport mới |
| Hystrix annotation không còn chạy | Hystrix starter/code đã gỡ nhưng call site chưa chuyển | Search `@HystrixCommand`, compile/test từng module |
| Resilience4j mở breaker quá sớm | Failure classification hoặc minimum calls khác Hystrix | Metrics, exception predicates, sliding window |
| Fallback trả 200 nhưng dữ liệu sai | Copy fallback cũ mà không kiểm tra semantics | Test UNKNOWN/degraded, business contract |
| Gateway route trả 404 | Path predicate/StripPrefix/RewritePath chuyển sai | So request path trước/sau filter |
| Gateway bị treo dưới tải | Blocking code chạy trên reactive event loop | Thread dump, Reactor/Netty metrics, chuyển blocking work |
| Dashboard cũ trống | Runtime đã bỏ Hystrix stream | Chuyển metrics và dashboard sang Micrometer |
| Eureka bị gỡ nhầm | Nhầm toàn bộ Spring Cloud Netflix là legacy | Giữ discovery implementation vẫn đang dùng |
| `zuul.*` vẫn xuất hiện sau migration | Config Server/profile/Helm còn property cũ | Quét mọi config source và effective runtime env |



## 11. Lập bản đồ chức năng cũ sang thành phần mới

Spring Cloud công bố các hướng thay thế ở cấp **chức năng**, nhưng không có nghĩa mọi property, class và semantics được chuyển nguyên xi.

| Công nghệ cũ | Chức năng | Hướng thay thế | Điểm phải thiết kế lại |
|---|---|---|---|
| Ribbon | Client-side load balancing | Spring Cloud LoadBalancer | `IRule`/`ServerListFilter` chuyển thành supplier, chooser, request context và policy |
| Hystrix | Circuit breaker, timeout, isolation, fallback | Spring Cloud CircuitBreaker với Resilience4j hoặc implementation phù hợp | Thread isolation, bulkhead, timeout, retry và fallback không phải cùng một property |
| Hystrix Dashboard/Turbine | Dashboard và tổng hợp stream | Micrometer + monitoring backend | Metrics names, labels, scrape/push, dashboards và alert rules |
| Zuul 1 | Edge reverse proxy, route, filter | Spring Cloud Gateway | Route predicates, filters, order, request/response mutation và reactive model |
| Archaius (nếu có) | External/dynamic configuration | Spring Boot external config + Spring Cloud Config | Property source, refresh semantics, secret management |

### 11.1. Ribbon → Spring Cloud LoadBalancer

Dependency thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

RestClient:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}
~~~

WebClient:

~~~java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
~~~

Feign dùng service ID:

~~~java
@FeignClient(name = "inventory-service")
public interface InventoryClient {
    @GetMapping("/stock/{sku}")
    StockView getStock(@PathVariable("sku") String sku);
}
~~~

Các chức năng thường cần ánh xạ:

| Ribbon cũ | Spring Cloud LoadBalancer |
|---|---|
| `IRule` | `ReactorServiceInstanceLoadBalancer` hoặc implementation built-in phù hợp |
| `ServerList` | `ServiceInstanceListSupplier` kết hợp DiscoveryClient |
| `ServerListFilter` | Supplier decorators như zone, hint, health, subset hoặc custom filter |
| Zone-aware rule | Zone preference supplier và metadata `zone` |
| Weighted rule | `WeightedServiceInstanceListSupplier`/`WeightFunction` |
| Retry theo server | LoadBalancer retry + retry-aware supplier và HTTP client retry policy |
| Ribbon per-client configuration | `@LoadBalancerClient`/`@LoadBalancerClients` theo service ID |

Spring Cloud LoadBalancer có Round Robin và Random implementation, supplier dựa trên discovery và custom configuration. Không phải mọi Ribbon rule đều có một class thay thế tương đương. Trước hết hãy mô tả **business intent** (zone, weight, affinity, retry, capacity) rồi chọn supplier/chooser phù hợp; chỉ viết custom LoadBalancer khi policy hiện có không đáp ứng.

Một ghi chú lịch sử: ở một số Hoxton-era configurations, nếu cả `spring-cloud-starter-loadbalancer` và Ribbon cùng có mặt, Ribbon có thể được chọn mặc định; tài liệu cũ hướng dẫn `spring.cloud.loadbalancer.ribbon.enabled=false` để chuyển sang Spring Cloud LoadBalancer. Đây là chi tiết của release train cũ, **không phải property migration chung cho mọi phiên bản hiện tại**. Với dự án đang ở train cũ, kiểm tra đúng reference version và runtime conditions; với dự án mới, loại bỏ Ribbon thay vì dựa vào công tắc chuyển tiếp cũ.

### 11.2. Hystrix → Spring Cloud CircuitBreaker + Resilience4j

Dependency blocking:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

Dependency reactive:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

API blocking:

~~~java
@Service
class InventoryGateway {

    private final RestClient client;
    private final CircuitBreaker breaker;

    InventoryGateway(
            RestClient client,
            CircuitBreakerFactory<?, ?> factory) {
        this.client = client;
        this.breaker = factory.create("inventoryRead");
    }

    StockView getStock(String sku) {
        return breaker.run(
                () -> client.get()
                        .uri("http://inventory-service/stock/{sku}", sku)
                        .retrieve()
                        .body(StockView.class),
                cause -> new StockView(sku, null, true)
        );
    }
}
~~~

Đây là skeleton minh họa: production phải phân loại exception và chỉ fallback khi semantics nghiệp vụ cho phép. Không chuyển mọi 4xx hoặc lỗi validation thành dữ liệu giả.

Cấu hình Resilience4j theo breaker ID:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s

  timelimiter:
    instances:
      inventoryRead:
        timeoutDuration: 900ms
~~~

Bảng chuyển đổi ý nghĩa:

| Hystrix cũ | Thiết kế mới cần xem xét |
|---|---|
| Command key / group key | Breaker ID và group ID có chủ đích |
| Circuit breaker state | Resilience4j CircuitBreaker state |
| Execution timeout | HTTP connect/read timeout, deadline và TimeLimiter; xác định mỗi tầng giới hạn điều gì |
| Thread isolation | Bulkhead/executor hoặc semaphore; không giả định mặc định giống Hystrix |
| Semaphore isolation | Resilience4j semaphore bulkhead/concurrency limit khi phù hợp |
| Fallback method | Fallback function, `onErrorResume` hoặc xử lý lỗi tại adapter |
| Request cache/collapser | Thiết kế cache/batching riêng; không có chuyển đổi 1:1 tự động |
| Hystrix Dashboard/Turbine | Actuator/Micrometer metrics + Prometheus/monitoring backend |

Không đổi tên `hystrix.command.default.execution.isolation.thread.timeoutInMilliseconds` thành một key Resilience4j tương tự rồi coi migration hoàn tất. Phải quyết định timeout của HTTP transport, TimeLimiter, bulkhead và retry budget riêng biệt. Đặc biệt, TimeLimiter không đảm bảo một transaction backend đã rollback khi caller hết thời gian chờ.

### 11.3. Zuul 1 → Spring Cloud Gateway

Zuul 1 là reverse proxy/gateway ở phía server/edge. Spring Cloud Gateway là lựa chọn thay thế để định tuyến HTTP request, áp dụng predicates và filters. Nó không phải cùng một thứ với **client-side load balancer**: gateway xử lý request đến ở edge, còn LoadBalancer chọn instance cho các HTTP client trong ứng dụng. Gateway có thể dùng LoadBalancer khi route có URI dạng `lb://inventory-service` và dependency/integration tương ứng được cấu hình.

Route minh họa của Spring Cloud Gateway:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory-route
          uri: lb://inventory-service
          predicates:
            - Path=/api/inventory/**
          filters:
            - StripPrefix=2
~~~

Ví dụ trên giả định ứng dụng Gateway có LoadBalancer integration và discovery/service ID `inventory-service`. Kiểm tra số segment bị loại bởi `StripPrefix` với path contract thực tế trước khi chuyển traffic.

| Zuul 1 cũ | Spring Cloud Gateway cần thiết kế lại |
|---|---|
| `zuul.routes.inventory.path` | Route predicate như `Path=/api/inventory/**` |
| `serviceId`/Ribbon route | `uri: lb://inventory-service` nếu route qua LoadBalancer |
| Zuul pre/post/route/error filters | `GlobalFilter`, `GatewayFilter` và filter factories |
| `zuul.prefix` | Path predicate/rewrite/strip-prefix theo contract |
| Zuul sensitive headers | Header filtering và security policy tại gateway |
| Zuul retry | Retry filter hoặc retry layer được cấu hình có giới hạn |
| Hystrix Zuul filter | CircuitBreaker GatewayFilter tích hợp implementation được hỗ trợ |

Không chuyển code `ZuulFilter` thành `GlobalFilter` bằng cách đổi tên class. Vòng đời, ordering, request exchange, reactive execution và xử lý lỗi khác nhau. Filter blocking nặng có thể làm nghẽn event loop trong Gateway WebFlux; phải thiết kế lại và kiểm thử concurrency.

### 11.4. Hystrix Dashboard/Turbine → observability hiện đại

Hystrix Dashboard/Turbine thường hiển thị command metrics và stream theo cách riêng. Khi chuyển sang Resilience4j/Spring Cloud CircuitBreaker, bật Actuator và Micrometer integration thích hợp, sau đó export đến monitoring backend (Prometheus, Grafana hoặc nền tảng tổ chức đang dùng).

Ví dụ dependency metrics bổ sung khi dùng Resilience4j:

~~~xml
<dependency>
    <groupId>io.github.resilience4j</groupId>
    <artifactId>resilience4j-micrometer</artifactId>
</dependency>
~~~

Kết hợp `spring-boot-starter-actuator` và metrics registry/exporter. Dashboard mới cần được thiết kế theo metric names, tags và SLO mới; không giả định Hystrix command keys sẽ tự chuyển thành Resilience4j breaker IDs hoặc các metric series cũ vẫn có ý nghĩa.


## 12. Đối chiếu release train trước khi quyết định xóa hay thay thế

Tài liệu Spring Cloud có nhiều thế hệ và các trang legacy vẫn có thể xuất hiện trên kết quả tìm kiếm. Ví dụ, tài liệu Spring Cloud Netflix 2.2.x còn mô tả Ribbon, Hystrix và Zuul; tài liệu Spring Cloud Netflix hiện hành tập trung vào Eureka. Đừng lấy ví dụ từ reference 2.2.x để cấu hình ứng dụng Boot/Cloud mới nếu chưa kiểm tra compatibility.

Quy trình xác nhận phiên bản:

1. Lấy Spring Boot version hiệu lực từ parent/plugin/dependency management.
2. Lấy Spring Cloud BOM/release train version hiệu lực từ effective POM hoặc Gradle platform.
3. Mở compatibility table của Spring Cloud để xác nhận cặp Boot/Cloud được hỗ trợ.
4. Dùng reference docs đúng release train khi xác minh property, starter và class.
5. Dùng tài liệu hiện hành để hiểu hướng phát triển/thay thế, nhưng không áp ngược property của bản mới vào ứng dụng cũ.
6. Kiểm tra deprecation/removal notes trong release notes của các train mà dự án sẽ đi qua.

Một property có thể tồn tại ở Hoxton nhưng không còn được đọc ở release train hiện tại. Ngược lại, một starter có tên gần giống có thể đã được chia module. **Tên property trong YAML không phải hợp đồng tương thích**; classpath, binder và runtime behavior mới là bằng chứng.

### Bảng quyết định theo version scope

| Bối cảnh | Hướng xử lý |
|---|---|
| Ứng dụng ở train cũ, Ribbon vẫn là implementation đang chạy | Lập kế hoạch migrate sang LoadBalancer; không chỉ xóa dependency khi call sites còn phụ thuộc API Ribbon |
| Ứng dụng đã dùng LoadBalancer nhưng Ribbon transitive còn sót | Xác định dependency kéo vào, thay adapter hoặc exclude sau khi test |
| Ứng dụng dùng Hystrix trực tiếp | Migrate command/fallback/isolation theo operation; chọn Spring Cloud CircuitBreaker và implementation tương thích |
| Gateway còn `@EnableZuulProxy` | Chuyển route/filter sang Spring Cloud Gateway, test behavior và rollout |
| Chỉ còn Eureka Client/Server | Giữ nếu discovery architecture vẫn dùng; không gỡ chỉ vì cùng thuộc Spring Cloud Netflix |
| Chỉ còn tài liệu/config legacy không được bind | Xác nhận nguồn cấu hình, sau đó dọn config/comment/docs để tránh vận hành nhầm |

## 13. Bài thực hành: kiểm kê một service trước và sau migration

Giả sử module `order-service` có POM, Java source và nhiều profile YAML. Thực hiện trên branch làm việc riêng và lưu kết quả vào issue/PR; không cần chạy thay đổi production để hoàn thành bài kiểm kê.

### 13.1. Quét dependency

~~~powershell
.\mvnw.cmd dependency:tree -Dverbose
.\mvnw.cmd help:effective-pom -Doutput=target/effective-pom.xml
~~~

Lọc output để tìm:

- Ribbon starter/core và dependency nào kéo vào.
- Hystrix starter/core/javanica/metrics.
- Zuul starter/core.
- Spring Cloud LoadBalancer, CircuitBreaker, Gateway và Eureka đang dùng.
- Version conflict/omitted nodes do dependency mediation.

### 13.2. Quét source và config

~~~powershell
rg -n -i --hidden -g '!**/.git/**' -g '!**/target/**' -g '!**/build/**' 'RibbonClient|IRule|ILoadBalancer|HystrixCommand|EnableHystrix|HystrixFeign|EnableZuulProxy|ZuulFilter|ribbon\.|hystrix\.|zuul\.' .
~~~

Phân loại từng kết quả thành active, transitive, config-only, code-only hoặc historical. Với mỗi kết quả, ghi:

- File/line và module.
- Profile/môi trường có load file đó.
- Dependency path và runtime scope.
- Bean/auto-configuration có được tạo không.
- Request/route/operation nào bị ảnh hưởng.
- Thay thế dự kiến và test cần bổ sung.

### 13.3. Lập migration record

Mẫu báo cáo trước khi sửa:

~~~text
Module: order-service
Spring Boot / Cloud train: <versions đã xác nhận>
Ribbon:
  dependency path: legacy-http-adapter -> spring-cloud-starter-netflix-ribbon
  source: InventoryRibbonConfiguration / IRule
  runtime: active trên inventory-service
  replacement: ServiceInstanceListSupplier + LoadBalancer
Hystrix:
  dependency path: spring-cloud-starter-netflix-hystrix
  source: @HystrixCommand trên InventoryGateway
  runtime: active
  replacement: Spring Cloud CircuitBreaker + Resilience4j
Zuul:
  dependency path: none
  source/config: chỉ có tài liệu migration cũ
  classification: historical
Eureka:
  dependency path: spring-cloud-starter-netflix-eureka-client
  usage: discovery registration
  decision: keep
~~~

Đây là **mẫu minh họa**, không phải kết quả quét repository hiện tại. Ghi rõ những mục UNKNOWN và yêu cầu owner xác nhận thay vì tự đánh dấu đã migrate.

### 13.4. Nghiệm thu sau migration

Chạy lại đúng các lệnh dependency/source/config scan. Đối chiếu báo cáo trước/sau:

- Dependency graph: không còn legacy artifacts trên production runtime path.
- Source: không còn call sites/annotations/classes được kích hoạt.
- Configuration: không còn property legacy được nạp từ file, environment hoặc Config Server.
- Runtime: không còn bean/route/command legacy hoạt động.
- Replacement: LoadBalancer/CircuitBreaker/Gateway có tests và metrics.
- Discovery: Eureka (nếu còn sử dụng) vẫn đăng ký và tra cứu đúng service ID.
- Rollout: canary/smoke test và rollback path được kiểm chứng.

## 14. Checklist hoàn tất nhận diện và migration

### Nhận diện

- [ ] Đã xác định module/service, Spring Boot version và Spring Cloud release train.
- [ ] Đã chạy Maven dependency tree hoặc Gradle dependency insight cho runtime configuration.
- [ ] Đã lần theo transitive dependency về module kéo vào.
- [ ] Đã tìm Ribbon imports, annotations, rules và `*.ribbon.*` properties.
- [ ] Đã tìm Hystrix commands, Feign integration, dashboard/stream và `hystrix.*` properties.
- [ ] Đã tìm Zuul annotations, filters, route config và `zuul.*` properties.
- [ ] Đã quét profile, Config Server, environment variables, Helm/Kubernetes và pipeline config.
- [ ] Đã phân biệt code/config active với historical/test-only/false positives.
- [ ] Đã giữ lại Eureka/OpenFeign/LoadBalancer/Resilience4j/Gateway khi chúng là thành phần hiện hành.

### Migration

- [ ] Đã ghi behavior cũ theo service ID, operation, route và policy.
- [ ] Ribbon được chuyển theo intent sang Spring Cloud LoadBalancer.
- [ ] Hystrix được chuyển theo operation sang CircuitBreaker/Resilience4j hoặc implementation phù hợp.
- [ ] Zuul routes/filters được thiết kế lại trên Spring Cloud Gateway.
- [ ] Timeout, retry, bulkhead, fallback và idempotency được đánh giá riêng.
- [ ] Metrics/dashboard/alerts/runbooks được chuyển theo semantics mới.
- [ ] Dependency và properties legacy được gỡ khỏi mọi nguồn cấu hình.
- [ ] Dependency graph/runtime conditions được kiểm tra lại sau khi gỡ.
- [ ] Integration tests chạy qua discovery, HTTP clients và gateway.
- [ ] Có canary/rollback plan và owner xác nhận kết quả.

## Tài liệu tham khảo

- [Spring Cloud Greenwich RC1 — Modules entering maintenance mode and replacements](https://spring.io/blog/2018/12/12/spring-cloud-greenwich-rc1-available-now/): thông báo lịch sử về maintenance mode và hướng thay thế Ribbon, Hystrix, Zuul 1.
- [Spring Cloud Netflix 2.2.x Reference](https://docs.spring.io/spring-cloud-netflix/docs/2.2.x/reference/html/): tài liệu legacy để nhận diện API, starter, property và behavior của Ribbon/Hystrix/Zuul trong các dự án cũ.
- [Spring Cloud Netflix — Current Reference](https://docs.spring.io/spring-cloud-netflix/reference/): phạm vi hiện hành của Spring Cloud Netflix, bao gồm Eureka.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ReactiveLoadBalancer`, `ServiceInstanceListSupplier`, Round Robin/Random, custom client configuration và HTTP client integrations.
- [Spring Cloud CircuitBreaker](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): API `CircuitBreakerFactory`, implementation abstraction và customizers.
- [Spring Cloud CircuitBreaker — Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): blocking/reactive starters, configuration, TimeLimiter, bulkhead và metrics.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/): route, predicate, filter và gateway runtime.
- [Spring Cloud Project](https://spring.io/projects/spring-cloud/): release trains và compatibility information.

**Kết luận:** nhận diện Ribbon, Hystrix và Zuul còn sót phải dựa trên **dependency graph + source code + cấu hình hiệu lực + runtime behavior**. Sau khi xác định được chức năng đang hoạt động, migrate theo intent sang Spring Cloud LoadBalancer, Spring Cloud CircuitBreaker/Resilience4j và Spring Cloud Gateway. Cuối cùng, kiểm tra lại classpath, bean, route, profile và metrics để chắc chắn hệ thống đã chuyển hẳn sang implementation mới mà vẫn giữ những thành phần hiện hành như Eureka hoặc OpenFeign khi kiến trúc còn cần chúng.



