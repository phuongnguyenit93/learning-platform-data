# Thư viện dùng chung và nguy cơ ghép chặt phiên bản

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Nền tảng và quản trị.  
> **Mục tiêu:** nhận biết lợi ích và rủi ro của shared libraries trong hệ microservices, đặc biệt là **coupling tại thời điểm build, dependency và release**; thiết kế cách chia sẻ các năng lực dùng chung mà vẫn bảo toàn quyền sở hữu domain, khả năng triển khai độc lập, tương thích ngược, bảo mật chuỗi cung ứng và quy trình quản trị phiên bản.

## 1. Bài toán: chia sẻ code giúp nhanh lúc đầu nhưng gây phát hành đồng loạt

Một tổ chức có 25 microservice viết bằng Java/Spring Boot: Order, Payment, Inventory, Catalog, Shipping, Notification và các dịch vụ hỗ trợ. Để tránh lặp code, nhóm nền tảng tạo thư viện **company-common** chứa:

- HTTP client, timeout, retry và tracing.
- Authentication/authorization helpers.
- Java classes cho Order, Payment, Inventory và các DTO dùng giữa service.
- Exception handling và cấu trúc error response.
- Database entities, JPA repositories và các migration tiện dụng.
- Feature flag client, JSON configuration, logging và validation.
- Các dependency version được đưa vào cùng một BOM.

Ban đầu, mọi nhóm chỉ import một JAR và tiến nhanh. Vài tháng sau:

1. Payment cần sửa một lỗi serialization và nâng **company-common v4.2**.
2. Bản mới thay một method công khai và nâng Jackson, Spring Security.
3. Order cần nâng để nhận bản vá bảo mật, nhưng v4.2 kéo theo thay đổi JPA model không tương thích Order.
4. Inventory vẫn ở runtime framework cũ; shared JAR mới không tải được một số class.
5. CI yêu cầu tất cả 25 dịch vụ lên cùng version trước khi một thay đổi được phát hành.
6. Một chức năng mới của Payment bị giữ lại vì những service không liên quan chưa nâng xong.

Hệ thống vẫn có 25 deployment, nhưng **khả năng phát hành độc lập đã giảm**. Đây là một dạng **distributed monolith do ghép chặt mã nguồn và dependency**.

**Bài học trung tâm:** tái sử dụng code là mục tiêu tốt, nhưng trong microservices không nên đổi quyền phát triển và triển khai độc lập lấy một JAR chung chứa quá nhiều kiến thức domain.

## 2. Shared library là gì và những thứ nào thường được chia sẻ?

**Shared library** là artifact code được nhiều chương trình sử dụng, chẳng hạn Maven JAR, npm package hoặc thư viện Python. Với Java, một service khai báo dependency tới tọa độ artifact gồm **groupId, artifactId, version**; build tool tìm bản phát hành cụ thể và đưa vào classpath/module path theo cấu hình.

Các kiểu chia sẻ:

| Loại | Ví dụ | Có phù hợp dùng chung? | Rủi ro chính |
| --- | --- | --- | --- |
| **Pure utility** | Xử lý ngày/giờ, encoding, kiểm tra định dạng không gắn domain | Thường có | API/behavior breaking change |
| **Cross-cutting infrastructure** | Logging, tracing, metrics, HTTP policy | Thường có, nếu modular | Kéo theo framework/transitive dependencies |
| **Client SDK** | InventoryClient, PaymentClient | Có điều kiện | Coupling với provider protocol/version |
| **Contract/schema** | OpenAPI, Protobuf, Avro, JSON Schema | Có, nếu version hóa | Breaking schema và generated-code changes |
| **Domain entities** | OrderEntity, PaymentStatus, InventoryRecord | Thường nên tránh dùng chung trực tiếp giữa bounded contexts | Shared domain ownership và lockstep releases |
| **Database repositories** | Shared JPA Repository hoặc chung migration | Nên tránh xuyên service | Coupling schema/storage, phá data ownership |
| **Security policy** | Tenant authorization rules hoặc quyền domain | Không nên áp một policy chung tùy tiện | Thay đổi bảo mật ảnh hưởng diện rộng |
| **Framework starter** | Auto-config cho telemetry, HTTP client | Có ích nếu opt-in và pin được | Ẩn cấu hình, version collisions |
| **Build conventions** | Compiler settings, test plugins, code quality | Nên chia theo tool/version | Buộc tất cả service nâng đồng loạt |
| **Infrastructure chart/template** | Helm chart base, deployment policy | Có thể, nhưng version riêng | Configuration rollout lockstep |

Không phải mọi sự chia sẻ đều xấu. Câu hỏi là: **chúng ta đang chia sẻ một khả năng ổn định hay đang chia sẻ quyết định nghiệp vụ, lifecycle và công nghệ nội bộ của một service?**

## 3. Các chiều coupling cần phân biệt

Trong microservices, coupling không chỉ nằm ở lời gọi HTTP.

1. **Compile-time coupling:** service phải dùng public API và kiểu dữ liệu do library định nghĩa.
2. **Binary coupling:** JVM bytecode mong đợi method, class hoặc ABI cụ thể khi chạy.
3. **Transitive dependency coupling:** library kéo nhiều dependencies và version vào classpath.
4. **Framework coupling:** phụ thuộc cấu hình, annotations hoặc lifecycle của Spring, Jakarta, Hibernate.
5. **Domain/semantic coupling:** dùng chung một khái niệm nghiệp vụ có nghĩa khác nhau ở các bounded contexts.
6. **Release coupling:** một thay đổi library buộc nhiều service build, test hoặc deploy cùng lúc.
7. **Operational coupling:** lỗi mặc định timeout, retry hoặc tracing của library ảnh hưởng toàn hệ thống.
8. **Organizational coupling:** đội sửa library bị lệ thuộc phê duyệt của nhiều đội khác.
9. **Security coupling:** một CVE hoặc secret-handling bug ảnh hưởng mọi consumer của JAR.
10. **Data coupling:** nhiều service cùng import entity/repository và thao tác chung schema.

**Tách microservice thành nhiều repository và nhiều container không tự xóa coupling.** Nếu mọi nhóm phải phát hành cùng nhau để một type dùng chung thay đổi, ranh giới triển khai chưa thực sự độc lập.

## 4. Ghép chặt phiên bản là gì?

**Version coupling** xảy ra khi một service không thể tự chọn nhịp nâng cấp dependency hoặc khi sự thay đổi của một package buộc nhiều service tiến theo một chuỗi version cố định.

Ví dụ:

~~~text
Order 1.7 ----\
Payment 3.2 ---+--> company-common 4.2
Inventory 2.1 /
~~~

Nếu version 4.2 chứa toàn bộ logging, auth, domain DTO và persistence, Order chỉ muốn nâng phần logging cũng bị kéo theo API Payment và JPA changes.

Một thiết kế modular hơn:

~~~text
Order --> company-observability 2.x
      --> company-http-client 3.x
      --> order-domain (internal)

Payment --> company-observability 2.x
        --> company-security-base 4.x
        --> payment-domain (internal)

Inventory --> company-http-client 2.x
          --> company-observability 2.x
          --> inventory-domain (internal)
~~~

Ở đây mỗi module có version/lifecycle riêng và các phần domain được sở hữu nội bộ. Tuy nhiên **nhiều artifact nhỏ không tự bảo đảm ít coupling** nếu tất cả luôn release dưới một version tập trung, có rất nhiều dependency chéo hoặc cần nâng cùng lúc.

### 4.1. Cảnh báo lockstep

Các dấu hiệu:

- Service A nâng một library nhưng phải chờ Service B merge pull request.
- Parent POM bắt buộc mọi module sản xuất dùng cùng version của mọi thứ.
- Một bug ở package logging làm tất cả service phải migrate schema trong cùng release.
- Library cung cấp một enum chung và khi thêm giá trị phải deploy đồng thời mọi consumer.
- Một nhóm thay API công khai mà không có migration guide hoặc compatibility window.
- CI của một service xanh nhưng release bị chặn vì dịch vụ không liên quan chưa deploy.
- Nâng shared library kéo theo thay đổi Java/Spring runtime mà đội app chưa sẵn sàng.

Đó là tín hiệu xem lại **granularity, ownership, API boundaries và release governance**.

## 5. Lợi ích thật sự của shared libraries

Không nên phản ứng bằng cách cấm chia sẻ code. Thư viện phù hợp giúp:

- Giảm duplication của logic kỹ thuật ổn định.
- Chuẩn hóa telemetry, context propagation và error handling cơ sở.
- Phát hành bản vá bảo mật cho nhiều dịch vụ qua đường dependency rõ ràng.
- Cung cấp client API có timeout/serialization conventions đáng tin.
- Giảm lỗi do mỗi nhóm tự triển khai lại cryptography hoặc protocol details.
- Tăng năng suất onboarding và discoverability.
- Cung cấp API tốt hơn cho những thành phần nền tảng phức tạp.

Tuy nhiên lợi ích chỉ bền vững khi thư viện có **hợp đồng rõ, ít dependency, tương thích, tài liệu, test và vòng đời riêng**.

Một nguyên tắc: **chia sẻ cái ổn định và lặp lại nhiều; giữ logic thay đổi theo nghiệp vụ tại service sở hữu domain.**

## 6. DDD: bounded context và nguy cơ shared domain model

Order, Payment và Inventory cùng dùng khái niệm “trạng thái” nhưng không nhất thiết có cùng mô hình.

- Order có **CREATED, CONFIRMED, CANCELLED**.
- Payment có **PENDING, AUTHORIZED, CAPTURED, REFUNDED**.
- Inventory có **AVAILABLE, RESERVED, SHIPPED**.

Nếu đặt các enum này trong một package **common-domain**, mọi nhóm phụ thuộc vào cách mô hình của nhóm khác phát triển. Một service có thể phải cập nhật vì một giá trị enum mà nó không sử dụng.

### 6.1. Shared kernel không phải default

Trong Domain-Driven Design, **Shared Kernel** là một kiểu quan hệ khi hai bounded contexts chủ động chia sẻ một phần mô hình, nhưng cần governance và phối hợp chặt. Nó hữu ích trong phạm vi nhỏ, ổn định và các đội chấp nhận ownership chung.

Đừng dùng tên “Shared Kernel” để hợp lý hóa một thư viện domain chứa tất cả entity/DTO và gọi đó là kiến trúc microservices.

### 6.2. Giữ domain model nội bộ

Mỗi service sở hữu:

- Entities, aggregates, repositories.
- Validation nghiệp vụ và state machine.
- Database schema/migrations.
- Ý nghĩa của trạng thái và bất biến.
- Quyết định phân quyền theo domain.

Những thứ trao đổi qua ranh giới service là **public contract**, không phải object model nội bộ.

Ví dụ Order có thể nhận response:

~~~json
{
  "paymentId": "PAY-123",
  "status": "CAPTURED",
  "amountMinor": 150000,
  "currency": "VND"
}
~~~

Order dùng thông tin này để cập nhật saga trạng thái đơn hàng, nhưng không cần import **PaymentJpaEntity**, repository hoặc internal domain aggregate của Payment.

## 7. Chia sẻ hợp đồng API khác chia sẻ class triển khai

Một sai lầm phổ biến: vì hai service giao tiếp bằng JSON nên cả hai import cùng một class Java để serialization/deserialization. Điều này đơn giản lúc đầu nhưng tạo build-time coupling tới chi tiết của provider.

### 7.1. Không nên chia sẻ internal entity

Ví dụ không phù hợp:

~~~java
// Trong JAR common-domain
@Entity
public class PaymentEntity {
    @Id
    private UUID id;
    private BigDecimal amount;
    private String internalRiskFlag;
    private PaymentStatus status;
}
~~~

Nếu cả Order và Payment import class này, một thay đổi database hoặc ORM của Payment có thể bắt Order nâng dependency dù HTTP contract không đổi.

Đồng thời một **JPA entity không phải DTO public**; chú thích persistence, lazy relations và internal fields có thể vô tình rò sang network.

### 7.2. Sử dụng boundary DTO cục bộ

Trong Order:

~~~java
public record PaymentReceipt(
    String paymentId,
    String status,
    long amountMinor,
    String currency
) {}

public interface PaymentGateway {
    PaymentReceipt capture(
        String orderId,
        long amountMinor,
        String currency,
        String idempotencyKey
    );
}
~~~

Đây là port của Order. Adapter outbound chịu trách nhiệm mapping dữ liệu HTTP/gRPC từ Payment sang model mà Order cần.

Khi Payment mở rộng response thêm trường **riskScore**, Order thường không phải đổi code nếu hợp đồng và deserializer cho phép bỏ qua trường không dùng.

### 7.3. Anti-Corruption Layer

Một **Anti-Corruption Layer (ACL)** có thể chuyển đổi:

~~~text
Payment public contract
        |
        v
Payment API adapter (Order)
        |
        v
Order domain concept
~~~

ACL giúp chống việc domain của Payment chi phối naming/state machine của Order. Việc mapping có chút duplication nhưng mang lại quyền thay đổi độc lập; không phải mọi dòng mã giống nhau đều cần gom vào shared library.

## 8. Contract/schema là nguồn sự thật, không phải shared runtime internals

Một lựa chọn tốt hơn cho giao tiếp service:

- **REST:** OpenAPI mô tả endpoint, headers, request/response schemas và errors.
- **gRPC:** Protobuf schema cho service/method và messages.
- **Events:** Avro/Protobuf/JSON Schema và versioning policy.
- **GraphQL:** schema/operations và compatibility policy.
- **Consumer-driven contracts:** Pact hoặc công cụ tương đương kiểm tra interaction thực tế.

Generated client có thể được phát hành riêng. Nhưng **client generator cũng có version** và code sinh ra vẫn có dependency; không được nhầm rằng codegen loại bỏ mọi coupling.

### 8.1. Ví dụ thay đổi an toàn

Payment thêm một trường optional:

~~~json
{
  "paymentId": "PAY-123",
  "status": "CAPTURED",
  "amountMinor": 150000,
  "currency": "VND",
  "riskReviewRequired": false
}
~~~

Nếu Order chỉ cần bốn trường đầu, response mới thường tương thích với Order cũ khi parser chấp nhận unknown fields. Cần test behavior thật chứ không chỉ dựa trên giả định “thêm trường luôn an toàn”.

### 8.2. Ví dụ thay đổi không tương thích

Payment đổi:

~~~text
Old: amountMinor (long)
New: amount (string, major unit)
~~~

Order có thể đọc sai tiền hoặc không deserialize được. Đây là API/semantic breaking change dù hai đội có cùng library Java mới. Giải pháp thường là **expand–migrate–contract**: thêm trường mới, tiếp tục hỗ trợ cũ, chuyển consumer, sau đó deprecate và gỡ.

## 9. Phân biệt source compatibility, binary compatibility và behavioral compatibility

**Source compatibility:** code consumer có thể compile khi nâng library hay không.

**Binary compatibility:** bytecode đã biên dịch với version cũ có thể link/chạy với version mới hay không.

**Behavioral/semantic compatibility:** chương trình có giữ hành vi mà consumer phụ thuộc hay không.

Ví dụ:

~~~java
// V1
public interface MoneyFormatter {
    String format(long minorUnits, String currency);
}

// V2 - thay method cũ bằng signature khác
public interface MoneyFormatter {
    String format(BigDecimal majorUnits, Currency currency);
}
~~~

Consumer cũ sẽ không compile nếu build lại với V2. Nếu một service chạy binary cũ nhưng classpath có V2, có thể gặp **NoSuchMethodError** khi gọi method không còn tồn tại.

Một thay đổi khác giữ nguyên signature nhưng đổi behavior:

~~~java
public long toMinorUnits(BigDecimal value) {
    // V1 giả định nhân với 100;
    // V2 bất ngờ tự suy diễn scale từ currency chưa truyền vào.
    ...
}
~~~

Code có thể compile và link bình thường nhưng nghiệp vụ sai khi xử lý JPY/VND hoặc làm tròn tiền. Compatibility phải được đánh giá ở **cả API và semantics**.

## 10. Lỗi JVM thường gặp khi phụ thuộc không tương thích

| Triệu chứng | Nguyên nhân khả dĩ | Hướng điều tra |
| --- | --- | --- |
| **NoSuchMethodError** | Runtime class khác binary mà consumer compile against | Xem dependency tree, jar versions, API change |
| **NoClassDefFoundError** | Class bị thiếu hoặc không tải được lúc runtime | Packaging, scope, classloader, transitive dependency |
| **ClassNotFoundException** | Runtime tìm class không thấy | Dependency inclusion, reflection/classpath |
| **IncompatibleClassChangeError** | Binary API thay đổi không phù hợp | API diff, jar signature, compile/runtime versions |
| **UnsupportedClassVersionError** | Bytecode compile cho Java mới hơn JVM chạy | Java toolchain, target/release, runtime image |
| **NoSuchFieldError** | Field binary không còn đúng | Mixed versions và API changes |
| **LinkageError** | Class loading/linking không tương thích | Jar conflicts, shaded classes, classloaders |
| **Serialization errors** | DTO/schema hoặc Jackson configuration thay đổi | JSON contracts, naming, nullability, enum |
| **Unexpected method behavior** | Semantics thay đổi nhưng signature không đổi | Behavior tests và migration notes |

Khi lỗi xuất hiện chỉ ở production, không vội sửa bằng cách thêm JAR ngẫu nhiên. Cần so sánh **resolved dependency graph** giữa build và artifact đã triển khai.

## 11. Transitive dependencies: thay library có thể đổi cả dependency graph

Giả sử:

~~~text
order-service
  -> company-http-client:3.1
       -> httpcomponents-core:5.x
       -> jackson-databind:2.x
  -> spring-boot-starter-web
       -> jackson-databind:2.y
~~~

Tùy Maven dependency mediation/dependencyManagement, version Jackson thực dùng có thể không đúng bản người viết library kỳ vọng. Một dependency mới có thể thay classpath mà không cần sửa source của Order.

Những rủi ro:

- Conflict phiên bản với Spring Boot managed dependencies.
- Transitive vulnerability không ai để ý.
- Library tải logging provider thứ hai và gây duplicate bindings.
- Một starter tự kích hoạt auto-configuration ngoài dự kiến.
- License hoặc artifact repository policy khác nhau.
- Dependency graph thay đổi trong khi source code hầu như không đổi.

### 11.1. Cách xem Maven dependency tree

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core
mvn help:effective-pom
~~~

Các lệnh là ví dụ: chạy tại module thực, dùng Maven/plugin version mà dự án hỗ trợ. Cần kiểm tra packaging thực tế và scope của dependencies. Báo cáo resolved tree từ chính build release quan trọng hơn việc nhìn POM một cách thủ công.

### 11.2. Không khai báo mọi dependency là api

Với thư viện Java, phân biệt API surface và implementation details. Một library HTTP client không nên làm các class transport cụ thể thành kiểu trả về công khai nếu consumer không cần biết.

Thiết kế dependency nhỏ giúp giảm conflict và tạo sự linh hoạt đổi implementation; việc gói một class lớn với hàng loạt dependencies vì “tiện dùng” có chi phí lâu dài.

## 12. Maven: mỗi service phải pin version được chọn

Ví dụ Order Service khai báo dependency rõ:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>company-observability</artifactId>
    <version>2.4.1</version>
  </dependency>
</dependencies>
~~~

Service có thể quyết định khi nào nâng từ 2.4.1 lên 2.4.2 sau kiểm thử và canary. Không thay đổi artifact đã publish tại cùng version.

### 12.1. Maven BOM

**Bill of Materials (BOM)** giúp quản lý version phối hợp của các dependencies:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.example.platform</groupId>
      <artifactId>platform-bom</artifactId>
      <version>3.2.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Sau đó service chọn module thực sự cần:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>company-observability</artifactId>
  </dependency>
</dependencies>
~~~

**BOM quản lý version, không tự thêm dependency**, và không chứng minh các version tương thích ở runtime. Thứ tự/chiến lược hòa giải với Spring Boot BOM và parent POM cần được kiểm tra qua effective POM/dependency tree.

BOM là công cụ tốt khi một **nhóm module có compatibility policy chung**, nhưng không được dùng nó để ép mọi service nâng cùng lúc.

### 12.2. Immutable artifacts

Đừng overwrite **company-common:4.2.0** bằng bytes mới rồi để các build cùng version nhận artifact khác nhau. Dùng immutable repository, checksum, provenance và version mới.

Nếu cần sửa bản 4.2.0, phát hành 4.2.1 hoặc version phù hợp và cập nhật consumers theo pipeline. Reproducible builds và artifact retention giúp điều tra incident.

## 13. Gradle và version catalogs

Gradle version catalogs có thể cung cấp aliases và version conventions cho dependency:

~~~toml
[versions]
observability = "2.4.1"
httpClient = "3.1.0"

[libraries]
company-observability = {
  module = "com.example.platform:company-observability",
  version.ref = "observability"
}
company-http-client = {
  module = "com.example.platform:company-http-client",
  version.ref = "httpClient"
}
~~~

Đoạn TOML là ví dụ cấu trúc. Một version catalog quản lý nơi định nghĩa version cho build, **không tự bảo đảm một version duy nhất được dùng trong toàn dependency graph** và không thay compatibility testing.

Nếu tất cả 25 service import một catalog version chung bắt buộc và chỉ cập nhật đồng loạt, catalog có thể trở thành coupling mechanism. Cân nhắc policy **baseline được khuyến nghị** và quyền pin/nâng theo lịch của service.

## 14. Semantic Versioning giúp gì, giới hạn ở đâu?

Trong **SemVer**, version dạng MAJOR.MINOR.PATCH thường có ý nghĩa:

- **MAJOR:** thay đổi public API không tương thích.
- **MINOR:** bổ sung API tương thích ngược.
- **PATCH:** sửa lỗi tương thích ngược.

Đây là một **cam kết của maintainer** về public API được định nghĩa, không phải bộ máy tự động chứng minh an toàn.

Một patch có thể làm behavior khác đi nếu sửa bug mà consumer đang vô tình phụ thuộc; một minor có thể thêm enum constant khiến consumer switch exhaustive hoặc serializer strict bị lỗi.

Nên định nghĩa:

1. Public API gồm những package/class nào.
2. Những behavior nào được bảo đảm.
3. Thay đổi binary/source compatibility được test ra sao.
4. Deprecation window và migration path.
5. Runtime/framework/Java minimum versions.
6. Những config mặc định là compatibility surface.
7. Các version nào đã hết hỗ trợ.

Với pre-1.0 libraries, cần một policy riêng nếu API thay đổi thường xuyên. Đừng dựa vào số version một mình để quyết định deploy.

## 15. Phá vỡ tương thích do đổi framework

Một tình huống thực tế trong Java ecosystem là chuyển từ thư viện dùng **javax.*** sang các API **jakarta.*** ở thế hệ framework mới. Thay đổi package namespace có thể ảnh hưởng source code, annotations, reflection, serializers, validation và dependency tree.

Các rủi ro thường gặp:

- Library compile bằng Java 21 nhưng service runtime Java 17.
- Library dùng Spring/Spring Security major version không tương thích với stack service.
- Auto-configuration chỉ tương thích phiên bản Boot mới.
- Thay đổi Jackson modules ảnh hưởng record/enum/date handling.
- Nâng Hibernate/JPA làm thay behavior lazy loading hoặc persistence.
- Một starter kéo servlet/reactive dependencies không mong đợi.

Không để một thư viện nhỏ như **company-error-model** buộc hàng loạt services nâng major runtime nếu tính năng của nó không cần framework mới. Tách **pure core** khỏi adapter framework-specific.

Ví dụ:

~~~text
company-error-core           (Java, không phụ thuộc Spring)
company-error-spring-boot-3  (adapter Boot 3)
company-error-spring-boot-4  (adapter riêng nếu được hỗ trợ)
~~~

Tên version/module chỉ minh họa. Chỉ phát hành adapter khi có kiểm thử tương thích với runtime thật.

## 16. Thiết kế thư viện nhỏ, cohesion cao

Một package tốt nên có **lý do thay đổi thống nhất**. Ví dụ:

- **company-observability:** trace context, metric conventions, log correlation.
- **company-http-client:** timeout/retry helpers với chính sách có thể tùy chỉnh.
- **company-security-base:** thành phần xác thực/token parsing dùng chung.
- **company-event-envelope:** schema envelope tối thiểu nếu thật sự chia sẻ.
- **company-build-conventions:** compiler/lint/testing plugins riêng với runtime JAR.

Một package kém thường gồm:

~~~text
common.jar
  AuthUtils
  OrderEntity
  PaymentRequest
  EmailTemplate
  InventoryRepository
  JPAConfig
  KafkaConfig
  RedisConfig
  FeatureFlagClient
  GlobalExceptionHandler
  JwtVerifier
  PriceCalculator
  UserAuthorizationRules
~~~

Với mọi lần sửa một trong các thành phần trên, tất cả consumers được thúc ép nâng một artifact. Thư viện lớn cũng che ranh giới ownership và làm transitive graph phức tạp.

**Tách module có chi phí** như release automation và versioning, nên không cần một JAR cho mỗi method. Mục tiêu là những **cụm thay đổi có vòng đời và dependency hợp lý**.

## 17. API surface tối thiểu: nguyên tắc dùng cái cần thiết

Một thư viện nên:

- Công khai càng ít class/type càng tốt.
- Giữ internal package không bị consumer phụ thuộc.
- Tránh trả thẳng class của vendor nếu không cần.
- Tránh static global state và cấu hình ẩn.
- Dùng interfaces/abstractions ổn định ở boundary.
- Có behavioral contract, compatibility tests và documentation.
- Cho consumer cấu hình timeout, policy, retry trong phạm vi cho phép.
- Không tự ý truy cập database, network hoặc secret trong class initialization.
- Có dependency tree nhỏ và exclusions được giải thích.

Java có thể dùng package access, module system (JPMS) hoặc quy tắc API bằng tooling. Tên package **internal** chỉ là quy ước nếu class vẫn public và compiler vẫn cho phép import; có thể cần API compatibility checker hoặc architecture tests để quản lý thật.

### 17.1. Ví dụ thư viện utility thuần

~~~java
public final class CorrelationIds {
    private CorrelationIds() {}

    public static boolean isValid(String id) {
        return id != null
            && id.length() >= 8
            && id.length() <= 128
            && id.chars().allMatch(ch ->
                Character.isLetterOrDigit(ch) || ch == '-' || ch == '_');
    }
}
~~~

Đoạn code chỉ minh họa utility kỹ thuật và giới hạn đầu vào; không giải quyết đầy đủ trace context security. Nếu cần chuẩn trace ID, nên dùng SDK/standard phù hợp, không tự tạo nhiều format bất nhất giữa services.

## 18. Shared security library: dùng chung nền tảng, không dùng chung mọi quyền

Các nhóm thường muốn dùng chung JWT validation, OAuth/OIDC resource-server setup, authentication filters và audit context.

Phần có thể chuẩn hóa:

- Kiểm tra chữ ký, issuer, audience, expiry bằng library uy tín.
- Mapping identity context vào request.
- Cấu hình TLS/mTLS và secure defaults.
- Bảo vệ secret, correlation và structured audit logging.
- Error format ở mức protocol.

Nhưng **domain authorization** thường thuộc service sở hữu nghiệp vụ:

- Order quyết định ai xem/sửa đơn hàng.
- Payment xác minh merchant/transaction ownership.
- Inventory xác minh warehouse và tenant permissions.

Không nên tạo một **GlobalAuthorizationHelper.canAccessAnyResource()** rồi suy luận mọi service có cùng quy tắc.

Nếu shared-security library có CVE, ảnh hưởng có thể lan rất rộng. Cần inventory consumers, SBOM, patch release, migration path và rollout theo mức độ rủi ro. Không update tất cả ở production đồng thời chỉ vì version mới đã có trên Maven registry.

## 19. Default behavior của shared library là API ngầm

Một số thay đổi không đổi method signature nhưng vẫn phá production:

- HTTP client mặc định retry POST ba lần.
- Timeout tăng từ 500 ms lên 30 giây, giữ thread lâu.
- Circuit breaker đổi threshold và mở trên toàn hệ thống.
- JSON mapper chuyển unknown-enum handling từ tolerant sang fail.
- Logger vô tình ghi authorization header.
- Trace instrumentation làm tăng cardinality/PII.
- Date parser đổi timezone default.
- Money formatter đổi quy tắc rounding.

Đó là **behavioral coupling**. Hợp đồng library phải mô tả những defaults quan trọng và cơ chế **opt-in/opt-out**.

Ví dụ:

~~~java
public record HttpCallPolicy(
    Duration connectTimeout,
    Duration responseTimeout,
    int maxAttempts
) {
    public HttpCallPolicy {
        if (connectTimeout.isNegative() || connectTimeout.isZero()) {
            throw new IllegalArgumentException("connectTimeout");
        }
        if (responseTimeout.isNegative() || responseTimeout.isZero()) {
            throw new IllegalArgumentException("responseTimeout");
        }
        if (maxAttempts < 1 || maxAttempts > 3) {
            throw new IllegalArgumentException("maxAttempts");
        }
    }
}
~~~

**HttpCallPolicy** là kiểu minh họa. Một production policy cần thêm retryable errors, jitter, deadline propagation, idempotency, queue timeout và limits. Mục tiêu ví dụ là biến các lựa chọn dễ gây hậu quả thành cấu hình tường minh thay vì default ẩn.

## 20. Client SDK: hữu ích nhưng phải giữ quyền tự chủ của consumer

Một SDK có thể giúp Order gọi Payment với endpoint, token handling, serialization và error mapping nhất quán. Tuy nhiên nếu SDK chứa toàn bộ Payment domain model hoặc bắt buộc bản provider mới nhất, consumer có thể bị ghép chặt.

Thiết kế tốt:

- SDK chỉ mô tả **public contract**.
- Có version độc lập.
- Hỗ trợ server versions được công bố.
- Có test compatibility với provider.
- Dependency footprint nhỏ.
- Tránh yêu cầu Spring context nếu chỉ cần một HTTP client.
- Hỗ trợ timeout, cancellation, idempotency và tracing.
- Không biến DTO public thành internal JPA entities.
- Có changelog và deprecation policy.

Một service có thể dùng OpenAPI-generated client nhưng vẫn đặt **adapter riêng** để domain code không phụ thuộc generated classes ở mọi nơi.

### 20.1. Port–adapter trong Order

~~~java
// Port nội bộ của Order.
public interface PaymentPort {
    PaymentOutcome capture(OrderPaymentIntent intent);
}

// Adapter triển khai port qua SDK HTTP đã pin version.
public final class PaymentApiAdapter implements PaymentPort {
    private final PaymentSdkClient client;

    public PaymentApiAdapter(PaymentSdkClient client) {
        this.client = client;
    }

    @Override
    public PaymentOutcome capture(OrderPaymentIntent intent) {
        PaymentApiResponse response = client.capture(
            intent.orderId(),
            intent.amountMinor(),
            intent.currency(),
            intent.idempotencyKey()
        );
        return PaymentOutcomeMapper.fromResponse(response);
    }
}
~~~

Các class **PaymentSdkClient**, **OrderPaymentIntent**, **PaymentApiResponse**, **PaymentOutcome**, **PaymentOutcomeMapper** là abstractions minh họa. Domain service chỉ thấy PaymentPort/PaymentOutcome của mình; nếu SDK thay format, sửa adapter thay vì lan thay đổi khắp codebase.

## 21. Compatibility matrix giữa library và service

Không đủ biết version mới nhất của library pass test của chính nó. Cần biết service đang chạy có tương thích không.

Ví dụ:

| Service | Java | Framework | company-http-client | company-observability |
| --- | --- | --- | --- | --- |
| Order v12 | 17 | Boot 3.x | 2.8 | 2.4 |
| Payment v9 | 21 | Boot 3.x | 3.1 | 2.4 |
| Inventory v7 | 17 | Boot 3.x | 2.8 | 2.3 |
| Notification v4 | 21 | Framework adapter riêng | 3.0 | 2.4 |

**Ví dụ giả định** để thấy mỗi service có nhịp nâng khác nhau. Không cần ép tất cả dùng một version vào cùng thời điểm nếu các version trong support window vẫn an toàn.

Một thư viện có thể công bố hỗ trợ:

~~~text
company-http-client 3.x:
  Java minimum: 17
  Tested with: Spring Boot 3.x adapters
  Public API compatibility: theo SemVer policy
  Server protocol: Payment API v1/v2 theo contract tests
  Runtime dependency constraints: mô tả trong BOM/POM
~~~

Đây là mẫu documentation, không phải tuyên bố về sản phẩm đang tồn tại. Support matrix cần được tạo từ CI thật và điều kiện đã test, không ghi “mọi version đều supported” thiếu bằng chứng.

## 22. Quy trình nâng dependency an toàn

Một nâng cấp library nên đi qua các bước:

1. **Đọc release notes và API diff:** có breaking source/binary/behavior change không?
2. **Kiểm tra dependency tree:** version conflict, exclusions, scope, platform BOM.
3. **Xác định security impact:** CVE, license, secret handling, cryptography changes.
4. **Nâng trong branch của service** chứ không sửa version của mọi service một lượt.
5. **Compile + unit tests:** bắt source errors và behavior tests.
6. **Component/integration tests:** khởi động Spring context, DB, serialization, HTTP clients.
7. **Contract tests:** kiểm tra API consumed/provided.
8. **Performance/resilience tests:** khi library ảnh hưởng timeout, retry, thread, cache, tracing.
9. **Build immutable artifact:** lưu dependency graph, checksum và version.
10. **Canary hoặc progressive rollout:** quan sát lỗi theo service/version.
11. **Ghi nhận dependency inventory:** service đã nâng lên version nào.
12. **Rollback/roll forward:** biết đường khôi phục khi behavior mới gây lỗi.

Đừng thay tất cả version trong 25 service chỉ vì có một PR Dependabot chung và coi CI compile xanh là đủ. Ngược lại, nếu có lỗ hổng critical đang bị khai thác, policy cần ưu tiên thời gian vá và giảm blast radius, không dùng “triển khai độc lập” làm lý do trì hoãn vô thời hạn.

## 23. Phát hành thư viện nội bộ thế nào?

Một thư viện nên có pipeline riêng:

~~~text
Source commit
  -> Unit tests + API/ABI compatibility tests
  -> Dependency/security/license checks
  -> Build artifact + checksum/provenance
  -> Publish candidate/prerelease nếu cần
  -> Compatibility tests trên consumer mẫu
  -> Publish immutable version
  -> Changelog + migration guide
  -> Dependency update PRs cho consumer
  -> Monitor adoption / end-of-support
~~~

Nếu thay đổi behavior mặc định nguy hiểm, cần thử với một số consumer đại diện trước khi khuyến nghị toàn tổ chức. Không được cho library pipeline tự deploy mọi service mà không qua kiểm soát release của từng service.

### 23.1. Artifact version policy

- Dùng version bất biến.
- Có changelog cho API và behavior changes.
- Công bố Java minimum/framework compatibility.
- Tránh **SNAPSHOT** trong production releases nếu tổ chức cần reproducibility.
- Có policy về prerelease và stable channels.
- Giữ artifact version cũ đủ lâu để rollback.
- Dùng registry nội bộ với access control, audit và checksum.

### 23.2. Ownership

Mỗi library nên có owner và maintainer được xác định. Chỉ đặt thư viện “common” mà không ai chịu trách nhiệm security, API lifecycle hoặc support sẽ tích lũy nợ kỹ thuật.

## 24. API/ABI compatibility testing

Thư viện Java có thể dùng:

- Unit tests cho behavior contract.
- API difference tooling như **japicmp** hoặc **Revapi**.
- Consumer fixture tests biên dịch với version mới.
- Contract tests nếu library chứa SDK network.
- Integration tests với các JVM/framework versions được tuyên bố hỗ trợ.
- Serialization compatibility tests.
- Load/regression tests cho thư viện liên quan hiệu năng.

API diff test có thể phát hiện method bị xóa hoặc signature đổi. Nhưng nó không chứng minh behavior mới đúng; ví dụ **same method signature** nhưng timeout default khác hoặc làm tròn tiền sai vẫn cần behavioral tests.

### 24.1. Ví dụ thử tương thích

Nếu V1 cung cấp:

~~~java
public final class ResultParser {
    public PaymentResult parse(String payload) {
        // ...
        return null;
    }
}
~~~

V2 muốn đổi parse để nhận byte array, nên giữ API cũ và thêm overload trong support window nếu có thể:

~~~java
public final class ResultParser {
    @Deprecated(since = "2.0", forRemoval = false)
    public PaymentResult parse(String payload) {
        return parse(payload.getBytes(StandardCharsets.UTF_8));
    }

    public PaymentResult parse(byte[] payload) {
        // Implementation thực cần validate và parse an toàn.
        return null;
    }
}
~~~

**Đây là skeleton minh họa**, không phải parser sử dụng được: return null không phải implementation production. Mục đích là trình bày pattern mở rộng API trước khi loại bỏ API cũ. Thư viện thực cần contract, test và error behavior rõ.

## 25. Hạn chế major upgrade đồng loạt

Nếu library lớn kết hợp security, JSON, logging, client SDK và domain model, mỗi major upgrade gây áp lực toàn hệ thống. Các cách giảm:

1. Tách library thành các module có cohesion cao.
2. Giữ public API tối thiểu, giảm breaking changes.
3. Cung cấp adapter tương thích giữa các framework generations.
4. Sử dụng deprecation window có thời hạn.
5. Có automated migration/codemod cho thay đổi lặp lại.
6. Viết dual-compatible APIs trong giai đoạn chuyển tiếp khi hợp lý.
7. Không gắn migration database vào version bump utility.
8. Pin dependency và nâng từng service qua PR riêng.
9. Duy trì support policy cho 1–2 major versions khi năng lực cho phép.
10. Theo dõi adoption để dọn version cũ theo bằng chứng, không chỉ theo cảm tính.

**Independent deployment không có nghĩa bỏ qua sự tương thích.** Nó có nghĩa mỗi service có thể chọn thời điểm nâng trong một cửa sổ compatibility được thiết kế.

## 26. Strategy: expand–migrate–contract cho shared API

Giả sử company-money V1 có:

~~~java
public static long toMinorUnits(BigDecimal majorValue);
~~~

Nhóm phát hiện hàm thiếu currency nên không thể xử lý mọi đồng tiền đúng.

Không nên bất ngờ thay signature trong cùng version hoặc đổi semantics của method cũ mà không thông báo.

Một lộ trình:

1. **Expand:** phát hành V2 thêm API mới nhận currency, giữ method cũ với behavior được document.
2. **Migrate:** các consumer nâng version và chuyển sang API mới theo test case currency của mình.
3. **Measure:** theo dõi consumers chưa migrate; cung cấp migration guide.
4. **Contract:** chỉ gỡ API cũ ở major version tiếp theo và sau support window.

Ví dụ API mới:

~~~java
public interface MoneyScale {
    long toMinorUnits(BigDecimal major, Currency currency);
}
~~~

Implementation cần xác định rounding, scale, overflow và zero-decimal currencies, không mặc định nhân 100. Nếu thư viện chứa logic tài chính domain quan trọng, cần owner nghiệp vụ và test sâu; có trường hợp nên giữ logic tính tiền tại Payment thay vì chia sẻ bừa.

## 27. Consumer-driven contracts khi dùng shared SDK

Một SDK có thể compile tốt nhưng API provider đã thay đổi. Ngược lại provider có thể tuân OpenAPI mới nhưng consumer cũ không được hỗ trợ nữa.

Với Order gọi Payment:

- **Consumer tests:** Order kiểm tra nó gửi request và xử lý response theo contract thực.
- **Provider verification:** Payment chứng minh implementation đáp ứng các interaction consumer cần.
- **Deployment compatibility:** xét version Order/Payment đang chạy ở environment thật.
- **SDK compatibility:** test adapter với version SDK đã pin.

Nếu shared SDK sinh từ một schema mới, **không được ép tất cả consumer nâng ngay** nếu provider vẫn có thể hỗ trợ contract cũ. Cần versioning và compatibility strategy ở network boundary.

Đừng thay contract testing bằng “cả hai dùng chung class Java nên chắc chắn tương thích”. Shared DTO có thể giống nhau tại compile time nhưng khác serializer, HTTP status, business semantics hoặc runtime versions.

## 28. Event schema và nguy cơ shared model

Trong event-driven systems, các service có thể trao đổi sự kiện:

~~~json
{
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "eventId": "9eea2673-bd7b-4d91-91f7-7a60e8b07f57",
  "orderId": "ORD-101",
  "occurredAt": "2026-11-12T02:00:00Z"
}
~~~

Một JAR chứa toàn bộ **OrderEntity** không nên được coi là schema event. Event contract là giao diện public có version, ownership và compatibility policy.

Lợi ích của schema registry hoặc source schema versioned:

- Producer/consumer có cùng định nghĩa dữ liệu ở boundary.
- Kiểm tra backward/forward compatibility theo khả năng công cụ.
- Generated serializers có thể dùng types rõ ràng.
- Có khả năng tìm consumer đang sử dụng version nào.

Giới hạn:

- Schema compatible chưa chứng minh semantics đúng.
- Consumer vẫn cần xử lý duplicate events, ordering và idempotency.
- Một event mới có thể đến queue cũ; consumer rollback phải hiểu dữ liệu còn tồn.
- Registry không thay domain ownership.

## 29. Build-time coupling so với runtime coupling

Một service dù không import shared JAR vẫn có runtime coupling qua HTTP API, database hoặc broker. Ngược lại dùng JAR không nhất thiết làm runtime coupling nếu thư viện là pure function.

So sánh:

| Tình huống | Build-time coupling | Runtime coupling | Quyết định thiết kế |
| --- | --- | --- | --- |
| Dùng common date utility | Có | Không đáng kể | Thường chấp nhận |
| Dùng PaymentClient SDK | Có | Có, qua Payment API | Cần version/contract tests |
| Import Payment JPA entity | Cao | Gián tiếp tới schema | Nên tránh xuyên bounded context |
| Dùng OpenAPI schema và codegen | Có ở build | Có qua API | Thường rõ ranh giới hơn |
| Dùng common logging adapter | Có | Có thể qua backend telemetry | Pin version và fallback |
| Shared database repository | Cao | Cao, qua DB | Vi phạm data ownership nếu xuyên service |
| Dùng event schema versioned | Có hoặc contract-level | Có qua broker | Quản lý schema và consumer lag |

Mục tiêu không phải loại bỏ coupling bằng mọi giá, mà là **chọn coupling có mục đích, ít bị ảnh hưởng bởi thay đổi không liên quan và có chi phí nâng cấp kiểm soát được**.

## 30. Dependency governance trong tổ chức

Nền tảng nên tạo **paved road**, không phải một con đường duy nhất bắt mọi người chờ nhau.

Ví dụ governance hợp lý:

- Baseline version security/observability được khuyến nghị.
- Danh sách versions hiện còn hỗ trợ.
- Trợ giúp nâng cấp tự động qua pull requests.
- BOM cho những module cần phối hợp version.
- Compatibility matrix với Java/Spring versions.
- SBOM và vulnerability scanning theo từng service artifact.
- Policy về deprecation và ngày EOL.
- Chủ sở hữu, contact và SLA phản hồi của mỗi library.
- Cơ chế exception rõ, có giới hạn thời gian và lý do.

Một policy kém: “mọi service phải dùng company-common latest cùng ngày, kể cả khi chưa test”. Một policy khác cũng kém: “mỗi service dùng library version tùy ý mãi mãi, không ai biết lỗ hổng”.

**Sự cân bằng:** cho phép service phát hành độc lập trong giới hạn bảo mật, khả năng hỗ trợ và contract đã được kiểm chứng.

## 31. Dependency inventory, SBOM và supply-chain risk

Một lỗi trong shared library có thể lan ra nhiều service, hoặc một dependency transitive có CVE mà app developer không nhìn thấy trong source.

Cần:

1. Biết service nào dùng version library nào.
2. Biết dependency graph cuối cùng của mỗi artifact build.
3. Tạo **Software Bill of Materials (SBOM)** theo chuẩn phù hợp.
4. Scan vulnerabilities và licenses, phân biệt direct/transitive.
5. Xác minh provenance, checksum, chữ ký nếu quy trình dùng.
6. Dùng registry/permissions hạn chế dependency confusion hoặc tampered artifacts.
7. Có cách phát hành patch và nâng nhiều service có điều phối.
8. Không để artifact snapshot mutable trong release production.
9. Ghi lại runtime version thực, không chỉ POM ở main branch.
10. Thu hồi phiên bản có lỗi nghiêm trọng theo policy, không bỏ qua consumers chưa nâng.

Một hệ thống có 25 service cùng import library bị lỗi không thể được vá chỉ bằng việc publish JAR mới. **Mỗi service phải build/deploy artifact chứa bản đã cập nhật**, hoặc có cơ chế runtime update được thiết kế riêng. Cần kiểm tra đã triển khai version nào ở production.

## 32. Maven Enforcer và dependency convergence

Các plugin như Maven Enforcer có thể giúp phát hiện điều kiện build không mong muốn, ví dụ Java version không hỗ trợ hoặc một số dependency conflicts.

Ví dụ cấu hình khái niệm:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-enforcer-plugin</artifactId>
  <version>3.5.0</version>
  <executions>
    <execution>
      <id>enforce-dependencies</id>
      <goals>
        <goal>enforce</goal>
      </goals>
      <configuration>
        <rules>
          <dependencyConvergence/>
          <requireJavaVersion>
            <version>[17,)</version>
          </requireJavaVersion>
        </rules>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

**Đây là cấu hình minh họa**, không phải file POM hoàn chỉnh. Rule dependencyConvergence có thể đánh dấu các graph không hội tụ theo cách tổ chức cần cân nhắc; hãy giải quyết/xem xét có chủ đích thay vì thêm exclusions bừa. Kết hợp với Maven Dependency Plugin, effective POM và integration tests.

Enforcer không chứng minh logic của library đúng, không thay API compatibility checker và không ngăn mọi runtime classloader conflict.

## 33. Anti-pattern: common utility kết nối database từ class initializer

Một thư viện có thể gây side effect ẩn:

~~~java
public final class CommonConfig {
    static {
        // Phản ví dụ: tự kết nối DB hoặc đọc secret toàn cục
        // ngay khi class được load.
        // GlobalDatabase.connect();
    }
}
~~~

Các vấn đề:

- Khởi tạo service thất bại nếu DB không sẵn sàng.
- Unit tests khó cô lập.
- Version bump có thể đổi network behavior của mọi service.
- Không kiểm soát tốt timeout, retries, credentials hoặc dependency lifecycle.
- Library bị gắn chặt với deployment config.

Thiết kế tốt hơn: thư viện cung cấp factory/configuration rõ ràng, constructor injection và lifecycle do application kiểm soát. Network client nên là dependency có owner, giới hạn tài nguyên và observability.

## 34. Anti-pattern: dùng chung một schema database

Nếu Order và Payment cùng import **company-db-model** chứa entity và repository, cả hai có thể đọc/ghi vào cùng bảng. Khi Payment đổi schema, Order phải đổi theo; ai chịu trách nhiệm migration cũng không rõ.

Hệ quả:

- Database migration lockstep.
- Không rõ source of truth.
- Hai service có thể cùng ghi vi phạm invariant.
- Rollback một service nguy hiểm vì schema đã thay.
- Thay ORM hoặc database engine khó.
- Security/tenant ownership bị loãng.

Hướng thay thế: mỗi service sở hữu storage và public interface. Dùng API/events hoặc data products/projections rõ ownership để chia sẻ thông tin; tránh truy cập trực tiếp bảng nội bộ service khác.

Một số hệ có data warehouse/read-only integration riêng; cần data contracts và governance khác, không coi đó là lý do để mọi application service cùng thao tác transactional tables.

## 35. Anti-pattern: common JAR luôn lấy latest

Nếu build được cấu hình tự nhận một version thay đổi bất định, hai build cùng commit có thể lấy dependency graph khác nhau. Điều đó gây khó tái hiện incident và kiểm chứng tương thích.

Nên:

- Pin artifact version trong POM/catalog/lock.
- Dùng release repository immutable.
- Có checksum/provenance theo policy.
- Ghi dependency inventory của artifact đã deploy.
- Tạo PR nâng version có test và review.
- Không dùng version range tùy tiện cho production nếu thiếu kiểm soát.
- Giữ lại artifact cũ để rollback.

**Tính tái lập của build là điều kiện vận hành**, không chỉ chuyện developer convenience.

## 36. Trường hợp thư viện chung làm giảm độ tin cậy

Một shared HTTP client đổi retry mặc định từ 1 sang 3 attempt. Mỗi Order request gọi Payment, Inventory và Promotion. Khi Inventory chậm, thêm retry làm tăng traffic đúng thời điểm queue bão hòa, có thể tạo cascading failure.

Mặc dù Java API không đổi, library có **behavior breaking change** ảnh hưởng SLO.

Quy trình khắc phục:

1. Phát hiện bằng metrics retries/attempts, queue wait, p99 và downstream QPS.
2. Dừng rollout library mới trong service bị ảnh hưởng.
3. Revert library version hoặc tắt tính năng nếu đường cũ an toàn.
4. Phát hành patch với mặc định cũ, hoặc chuyển retry policy thành opt-in.
5. Viết load/fault tests để tránh lặp lại.
6. Xác định consumers đã nâng và giám sát ở từng service.
7. Ghi release note/changelog và sửa tài liệu defaults.

Đừng giải quyết bằng cách tăng timeout vô hạn hoặc retry mọi lỗi ở nhiều tầng.

## 37. Ví dụ thực hành: tách common.jar thành module ổn định

### Trước

~~~text
company-common:4.0
  -> Logging
  -> JwtVerifier
  -> OrderEntity
  -> PaymentDto
  -> HttpClient
  -> KafkaConfig
  -> FeatureFlagClient
  -> JPARepositories
~~~

Mọi service dùng một artifact dù nhu cầu khác nhau.

### Sau

~~~text
company-telemetry-core:1.0
company-telemetry-spring:1.0
company-http-core:1.0
company-http-spring:1.0
company-authentication:1.0
company-event-envelope:1.0

Order Service:
  internal order-domain
  company-http-core
  company-telemetry-spring

Payment Service:
  internal payment-domain
  company-authentication
  company-telemetry-spring

Inventory Service:
  internal inventory-domain
  company-http-core
~~~

Các version chỉ minh họa. Để chuyển đổi an toàn:

1. Kiểm kê usage thật của từng class trong common.jar.
2. Xác định các public APIs cần giữ trong support window.
3. Tách module theo cohesion, dependency direction và ownership.
4. Giữ bridge/adapter tạm thời nếu consumer chưa migrate.
5. Migrate lần lượt theo service, không buộc big-bang.
6. Test API/ABI và runtime behavior.
7. Deprecate old common.jar có lộ trình.
8. Chỉ xóa sau khi không còn consumer được hỗ trợ.

Đừng thay thư viện lớn bằng vài chục library luôn phải cùng version, vì coupling sẽ chuyển hình thức mà không biến mất.

## 38. Mẫu đánh giá trước khi tạo shared library mới

Trước khi publish một package, trả lời:

1. Có ít nhất hai consumer thật hay mới chỉ dự đoán sẽ được dùng?
2. Logic có **ổn định** và cùng semantics giữa consumer?
3. Có một owner và release lifecycle rõ?
4. Public API nhỏ, dễ test và version hóa?
5. Có transitive/framework dependencies nặng không?
6. Consumer có thể pin version khác nhau?
7. Chúng có thể nâng độc lập mà không deploy cùng nhau?
8. Có migration/deprecation policy?
9. Có yêu cầu security/SBOM/license?
10. Có lựa chọn **copy small utility** hoặc **schema/contract** phù hợp hơn?
11. Dùng chung có vô tình chia sẻ DB/entity/domain ownership không?
12. Nếu library lỗi, blast radius ảnh hưởng bao nhiêu service?
13. Library có tự động bật behavior khi được import không?
14. Có test phản ánh cả binary và semantic compatibility?
15. Dùng platform starter có là lựa chọn opt-in hay ép buộc?

**Không có số lượng dòng code tối thiểu để buộc tạo library.** Một utility 10 dòng ổn định được nhiều nơi dùng có thể xứng đáng chia sẻ; một model 5.000 dòng biến đổi theo nhiều domain có thể không.

## 39. Quy trình nâng cấp minh họa: vá CVE trong shared JSON dependency

Giả định một lỗ hổng trong dependency transitive của **company-http-client 3.1** ảnh hưởng Order, Payment và Inventory.

### Bước 1 — Xác định phạm vi

Lấy inventory/SBOM để biết:

- Service nào đang chạy version bị ảnh hưởng.
- Artifact nào đã deploy ở production, không chỉ source main branch.
- Exploitability theo cách từng service sử dụng dependency.
- Có phiên bản fixed, mitigation hoặc vendor advisory không.

### Bước 2 — Phát hành patch thư viện

Nhóm platform:

- Nâng dependency tới version được hỗ trợ.
- Kiểm tra API/ABI, unit và integration tests.
- Xác minh Jackson serialization/deserialization contract.
- Phát hành **company-http-client 3.1.1** bất biến với release notes.
- Cập nhật BOM khuyến nghị, nếu cần.

### Bước 3 — Nâng từng service

Tạo PR cho từng service. CI chạy compile, dependency convergence, contract tests, boot/integration tests, security checks. Service có thể nâng và deploy theo lịch ưu tiên rủi ro; không cần chờ mọi service cùng build xong nếu contract tương thích.

### Bước 4 — Quan sát kết quả

Canary/rollout theo service, theo dõi 5xx, serialization errors, p95/p99, retries và authorization outcomes. Cập nhật inventory để biết service nào còn version bị ảnh hưởng.

### Bước 5 — Đóng remediation

Khi không còn artifact chạy bản yếu trong phạm vi yêu cầu, ghi lại bằng chứng. Nếu consumer cần exception, phải có owner, hạn xử lý và mitigation — không coi là đã vá.

**Lưu ý:** version 3.1.1 ở đây là ví dụ; một advisory thật phải được xử lý theo phiên bản và hướng dẫn chính thức.

## 40. Checklist triển khai và vận hành

### Thiết kế thư viện

- [ ] Chỉ chia sẻ logic có semantics ổn định, dùng được ở nhiều consumer.
- [ ] Không công khai internal entity/repository giữa bounded contexts.
- [ ] Public API nhỏ, dependencies nhẹ, không có initialization side effects.
- [ ] Tách pure core khỏi framework-specific adapter.
- [ ] Có module owner, changelog, migration guide và support window.
- [ ] Có behavioral/ABI compatibility policy.
- [ ] Không ép mọi service cùng nâng một version.

### Dependency và build

- [ ] Pin version immutable; tránh mutable/latest trong production.
- [ ] Kiểm tra Maven dependency tree/effective POM hoặc Gradle resolved dependencies.
- [ ] BOM/catalog dùng để quản lý baseline, không thay kiểm thử.
- [ ] Có dependency convergence/security/license checks.
- [ ] Có SBOM, provenance và inventory theo artifact production.
- [ ] Có Java/framework version compatibility matrix.
- [ ] Giữ artifact cũ đủ lâu để rollback.

### Release và kiến trúc microservices

- [ ] Consumer/provider contracts được test độc lập.
- [ ] SDK và generated client không tràn vào domain logic.
- [ ] Changes additive trước breaking changes; có deprecation window.
- [ ] CI của library không tự yêu cầu mọi service deploy đồng thời.
- [ ] Nâng qua PR riêng, canary từng service.
- [ ] Có metric theo version, trace, error rate và downstream behavior.
- [ ] Có rollback/roll-forward policy khi shared default gây sự cố.
- [ ] Định kỳ rà soát các package common ngày càng phình to.

## 41. Câu hỏi tự kiểm tra

**1. Shared library có phải anti-pattern trong microservices?**  
Không. Library nhỏ, ổn định và quản lý tốt giúp giảm duplication. Anti-pattern là một library chung tạo coupling domain/framework/release không cần thiết.

**2. Vì sao dùng chung PaymentEntity giữa Order và Payment là nguy hiểm?**  
Vì entity là internal persistence/domain model. Order bị buộc đổi theo schema/ORM và business decisions của Payment.

**3. Shared DTO có bảo đảm hai service tương thích HTTP không?**  
Không. Cần kiểm tra status, headers, serializer, runtime versions, schema/semantics và tương tác thực bằng contract/integration tests.

**4. BOM có tự thêm dependencies không?**  
Không. BOM chỉ quản lý các version dependency được chọn theo cấu hình build.

**5. Có thể dùng SemVer như bằng chứng patch hoàn toàn an toàn?**  
Không. Version là cam kết; behavior, transitives và runtime compatibility vẫn cần kiểm thử.

**6. NoSuchMethodError gợi ý điều gì?**  
Có thể compiled consumer mong đợi method không có trong runtime class được nạp, thường do binary incompatibility/version conflict.

**7. Vì sao thư viện logging có thể gây lỗi ở Payment dù Payment không sửa code?**  
Version mới có thể đổi transitive dependencies, classpath, auto-config hoặc behavior mặc định.

**8. Cách nào giúp Order không phụ thuộc generated Payment SDK ở toàn domain?**  
Đặt PaymentPort nội bộ và adapter mapping từ SDK response sang Order domain model.

**9. Cùng một library có thể chạy trên Java 17 và Java 21 không?**  
Tùy bytecode target, API được sử dụng và test runtime; không suy ra từ source code một mình.

**10. Tại sao cần support window cho thư viện?**  
Để services nâng độc lập nhưng vẫn có giới hạn bảo mật/maintenance và đường migration.

**11. Khi library có CVE, chỉ publish patch JAR đã sửa là đủ chưa?**  
Chưa. Cần biết các consumer đã build/deploy bản mới ở production và kiểm tra remediation.

**12. Tại sao không nên dùng lastest dependency tự động trong mọi build?**  
Làm mất tính tái lập và có thể lấy artifact/graph khác nhau ở cùng một commit.

**13. Thay default retry từ 1 sang 3 có thể là breaking change không?**  
Có. Behavior thay đổi gây traffic amplification và cascading failure dù method signatures không đổi.

**14. Khi nào Shared Kernel của DDD phù hợp?**  
Khi nhiều bounded contexts thực sự đồng sở hữu một phần model nhỏ và có governance chấp nhận phối hợp, không phải mặc định cho toàn doanh nghiệp.

**15. Đo dấu hiệu ghép chặt version bằng gì?**  
Nâng version cần bao nhiêu service đổi theo, số breaking migrations, thời gian adoption, lỗi dependency, CI coordination và khả năng release từng service độc lập.

## 42. Tài liệu tham khảo

- Semantic Versioning 2.0.0: https://semver.org/
- Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven Dependency Plugin: https://maven.apache.org/plugins/maven-dependency-plugin/
- Maven Enforcer Plugin: https://maven.apache.org/enforcer/maven-enforcer-plugin/
- Gradle — Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html
- Gradle — Dependency Management: https://docs.gradle.org/current/userguide/dependency_management.html
- Spring Boot — Dependency Versions: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Martin Fowler — Microservices: https://martinfowler.com/articles/microservices.html
- Martin Fowler — Consumer-Driven Contracts: https://martinfowler.com/articles/consumerDrivenContracts.html
- Pact — Consumer-driven contract testing: https://docs.pact.io/
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
- OWASP — Software Component Verification Standard: https://owasp.org/www-project-software-component-verification-standard/
- CycloneDX — Software Bill of Materials: https://cyclonedx.org/
- SPDX Specification: https://spdx.dev/
- Revapi — API Analysis: https://revapi.org/
- japicmp — Java API comparison: https://github.com/siom79/japicmp

**Ghi nhớ:** Thư viện dùng chung là công cụ tái sử dụng, không phải cách trộn các bounded contexts vào một mô hình chung. **Chia sẻ contract ổn định, thu nhỏ API và dependency footprint, pin version, kiểm thử compatibility, phát hành artifact bất biến và cho từng service nâng cấp độc lập** là cách giảm nguy cơ ghép chặt phiên bản mà vẫn tận dụng được năng lực nền tảng.
