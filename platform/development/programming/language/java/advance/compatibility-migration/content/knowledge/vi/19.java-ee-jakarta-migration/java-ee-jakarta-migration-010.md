# Lập kế hoạch chuyển đổi theo nhóm thành phần phụ thuộc nhau

Chuyển một hệ thống Java EE sang Jakarta EE hiếm khi chỉ là thao tác đổi `javax.*` thành `jakarta.*`. Ứng dụng thực tế thường gồm web container, API REST, CDI, JPA, Bean Validation, transaction, messaging, security, thư viện JSON/XML, client SDK, plugin và các mô-đun nghiệp vụ. Những thành phần này liên kết với nhau qua kiểu dữ liệu trong chữ ký phương thức, annotation, service provider, configuration, database, HTTP hoặc queue. Nếu nâng từng JAR theo thứ tự ngẫu nhiên, ứng dụng có thể biên dịch một phần nhưng thất bại khi triển khai.

Cách tiếp cận hiệu quả hơn là **chia migration thành các nhóm thành phần có quan hệ phụ thuộc chặt chẽ**, rồi chuyển từng nhóm theo thứ tự được xác định bởi đồ thị phụ thuộc. Phạm vi nhóm phải đủ rộng để giải quyết các liên kết API không tương thích, nhưng đủ nhỏ để kiểm thử và rollback được.

Bài học trình bày phương pháp lập inventory, phân tích đồ thị, xác định *migration unit*, chia *waves*, chọn ranh giới tương thích giữa các nhóm, lập ma trận kiểm thử và tổ chức rollout. Các ví dụ mô tả một hệ thống giả định; tên module và version trong ví dụ không phải cấu hình bắt buộc cho mọi dự án.

## 1. Vì sao không thể chuyển đổi từng thư viện riêng lẻ?

Một module web Java EE cũ có thể phụ thuộc trực tiếp vào:

- `javax.servlet.*` để nhận HTTP request.
- `javax.ws.rs.*` để cung cấp endpoint REST.
- `javax.enterprise.*` và `javax.inject.*` cho dependency injection.
- `javax.persistence.*` để ánh xạ entity.
- `javax.validation.*` cho validation.
- `javax.transaction.*` cho transaction API thuộc Java EE/Jakarta.
- Một implementation hoặc framework dùng reflection để đọc các annotation đó.

Ví dụ lớp cũ:

```java
import javax.inject.Inject;
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.persistence.EntityManager;

@Path("/orders")
public class OrderResource {
    @Inject
    EntityManager entityManager;

    @GET
    public String list() {
        return "orders";
    }
}
```

Nếu chỉ nâng Jakarta REST implementation nhưng giữ API resource `javax.ws.rs.Path`, runtime mới có thể không nhận lớp là REST resource. Nếu chỉ đổi annotation mà container vẫn cung cấp Jakarta EE 8 API thuộc namespace `javax`, class có thể không tìm được kiểu cần thiết hoặc CDI/JPA không hoạt động đúng.

**Namespace là một phần của type identity trong Java.** Hai interface tên gần giống:

```text
javax.servlet.Filter
jakarta.servlet.Filter
```

là hai kiểu khác nhau. Một lớp triển khai kiểu thứ nhất không tự động triển khai kiểu thứ hai. Việc trộn dependency cũ và mới trong cùng runtime có thể gây `ClassCastException`, `NoClassDefFoundError`, `NoSuchMethodError` hoặc lỗi bootstrap không rõ ngay ở compile time.

Vì vậy, một nhóm migration nên bao gồm **những thành phần phải cùng đổi hợp đồng Java hoặc runtime** để hoạt động như một đơn vị kiểm chứng được.

## 2. Nhận diện đúng phạm vi Java EE → Jakarta EE

Cần phân biệt các mốc:

| Giai đoạn | Đặc điểm API namespace | Ý nghĩa lập kế hoạch |
|---|---|---|
| Java EE truyền thống | API Java EE phổ biến ở `javax.*`. | Baseline nhiều ứng dụng legacy. |
| Jakarta EE 8 | Chủ yếu vẫn giữ namespace `javax.*` của Java EE tương ứng. | Thay thương hiệu/tổ chức tiêu chuẩn chưa có nghĩa mọi import đã đổi. |
| Jakarta EE 9 trở đi | Các Jakarta EE API liên quan chuyển sang `jakarta.*`. | Ranh giới không tương thích source/binary đáng chú ý. |
| Các release Jakarta EE sau đó | Tiếp tục tiến hóa API, runtime và yêu cầu nền tảng. | Cần đọc đúng compatibility matrix, release notes và migration guide từng chặng. |

**Không đổi mọi `javax.*`.** Nhiều package `javax` vẫn thuộc Java SE và không bị đổi bởi migration Jakarta EE, ví dụ `javax.sql`, `javax.naming`, `javax.crypto`, `javax.management`, `javax.net.ssl`, `javax.xml.parsers` và `javax.annotation.processing`.

Ngoài ra, có các trường hợp đặc biệt theo module, ví dụ API transaction của Jakarta và API XA thuộc Java SE. Quyết định đổi import phải dựa vào **API owner, artifact và tài liệu của spec cụ thể**, không dùng phép tìm-thay toàn bộ theo prefix.

## 3. Mô hình hệ thống ví dụ

Giả sử hệ thống quản lý đơn hàng gồm các thành phần:

```text
                              External Clients
                                    |
                                    v
                           +------------------+
                           | API Gateway      |
                           +------------------+
                                    |
                           HTTP/JSON (contract)
                                    |
                                    v
                         +----------------------+
                         | order-web.war        |
                         | Servlet + REST       |
                         +----------------------+
                            |                 |
                         CDI/DI          DTO + validation
                            |                 |
                            v                 v
                         +----------------------+
                         | order-service        |
                         | nghiệp vụ, giao dịch |
                         +----------------------+
                            |               |
                           JPA              JMS
                            |               |
                   +-------------+    +---------------+
                   | order-data  |    | order-events  |
                   | entities    |    | publisher     |
                   +-------------+    +---------------+
                         |                  |
                       Database           Queue
                         |
              +----------------------+
              | reporting-batch      |
              | đọc dữ liệu/ORM      |
              +----------------------+
```

Trong thực tế, nhóm này còn liên kết tới framework, application server, logging và các thư viện dùng chung. Một kế hoạch “migrate order-web trước rồi để service và JPA tính sau” có thể không khả thi nếu các module trao đổi trực tiếp `javax.persistence.EntityManager` hoặc annotation Jakarta giữa nhau.

Ngược lại, nếu `reporting-batch` chỉ gọi một HTTP API ổn định, nó có thể nâng độc lập với `order-web`. **Ranh giới dữ liệu/giao thức** là một công cụ quan trọng để tách các nhóm migration.

## 4. Chọn *đơn vị chuyển đổi* theo quan hệ phụ thuộc

Một *migration unit* là tập thành phần được nâng và xác minh cùng nhau vì không có ranh giới tương thích ổn định ở bên trong tập đó.

Ví dụ:

| Nhóm | Thành phần giả định | Vì sao gộp? |
|---|---|---|
| Web/API | Servlet, Jakarta REST runtime, filters, interceptors, authentication integration. | Cùng sử dụng Jakarta web API và phụ thuộc container. |
| CDI/Injection | CDI runtime, bean discovery, qualifiers, interceptors, extensions. | Annotation và lifecycle gắn với một dependency injection container. |
| Persistence | JPA API/provider, entities, converters, transaction integration, cache. | ORM/provider và entity annotations phải tương thích. |
| Validation | Jakarta Validation API/provider, DTO annotations, REST/JPA integration. | Validation bootstrap và annotation namespace phải khớp. |
| Messaging | Jakarta Messaging API/provider adapters, producers, consumers, MDB nếu có. | Messaging runtime, transaction và listener integration liên quan chặt. |
| Build/Runtime | JDK, framework/BOM, server, Maven/Gradle plugins, test containers. | Quyết định Java baseline và tổ hợp artifact được hỗ trợ. |
| Boundary contracts | JSON schemas, XML schemas, HTTP routes, message schemas, DB schema. | Là ranh giới cần giữ ổn định khi hai nhóm cùng tồn tại. |

Không nhất thiết mỗi hàng trong bảng là một nhóm triển khai độc lập. Ví dụ với một WAR trên application server, Web, CDI, JPA, Validation và phần server integration có thể tạo thành một **nhóm chuyển đổi bắt buộc cùng thời điểm**. Với microservices giao tiếp qua HTTP/queue, có thể phân nhóm theo service và dùng hợp đồng giao thức để chuyển tuần tự.

## 5. Xác lập trạng thái nguồn và trạng thái đích

Trước khi chia nhóm, cần một **inventory có version thực tế**. Nên ghi cho mỗi component:

- Tên module/service, vị trí source, artifact đầu ra và owner.
- JDK nguồn, JDK target, baseline Java runtime cam kết.
- Runtime: application server, servlet container, embedded framework hoặc batch launcher.
- Phiên bản Java EE/Jakarta EE spec API mà code sử dụng.
- Implementation/provider tương ứng: JPA, CDI, JAX-RS, validation, messaging.
- Direct và transitive dependencies thực tế đã resolve.
- Các contract giao tiếp với module/service khác.
- Nơi lưu dữ liệu và phiên bản schema/format hiện có.
- Classloader/module-path/classpath đặc biệt và plugin runtime.
- Tính quan trọng nghiệp vụ và khả năng rollback.

Ví dụ hồ sơ rút gọn:

```yaml
component: order-web
artifact: order-web.war
owner: order-team
sourceRuntime: legacy-app-server
targetRuntime: jakarta-compatible-server
sourceApiFamily: javaee-javax
targetApiFamily: jakarta
jdkBaseline: 17
integrationBoundaries:
  - http: /api/orders
  - module: order-service
  - event: OrderCreated
dependencies:
  - order-service
  - common-web-filters
  - json-codec
tests:
  - order-api-contract
  - authentication-integration
  - persistence-smoke
rollbackNeeds:
  - old-and-new-message-readers
status: planned
```

Tài liệu minh họa không khẳng định một server cụ thể hỗ trợ toàn bộ các mức trên. Trong migration thực tế, phải chọn **bộ JDK, framework và server có compatibility matrix được xác nhận**, tránh chỉ dựa vào số Java feature release.

## 6. Lấy dependency graph từ nhiều nguồn

Không có một công cụ duy nhất phát hiện đầy đủ mọi loại phụ thuộc. Nên kết hợp:

1. **Build dependency graph:** Maven, Gradle, BOM, transitive dependencies.
2. **Source dependency graph:** import, method signature, annotation và module references.
3. **Binary dependency graph:** `jdeps`, class file references, package/API usage.
4. **Runtime integration graph:** CDI, JPA, SPI, reflection, ServiceLoader và container-managed resources.
5. **Data-flow graph:** HTTP, events, JDBC tables, batch files, JSON/XML, database migrations.
6. **Operational graph:** startup order, deployment pipelines, secrets, ports, shared server.

### 6.1. Maven

```bash
mvn dependency:tree
```

Trong multi-module project, cần chạy ở module liên quan và ghi rõ scope (compile, runtime, test). Parent POM hoặc BOM có thể điều chỉnh version mà `pom.xml` của module không ghi trực tiếp.

Để xem cấu hình sau kế thừa:

```bash
mvn help:effective-pom
```

Lệnh này bổ sung góc nhìn cấu hình nhưng không thay cho dependency tree khi xác định transitive dependencies và artifact runtime thực tế.

### 6.2. Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
    --dependency jakarta.persistence \
    --configuration runtimeClasspath
```

Phải chọn configuration và subproject phù hợp, bởi test, build plugin, compile và runtime dependency có thể khác nhau.

### 6.3. jdeps

```bash
jdeps --recursive --multi-release 17 \
    --class-path "libs/*" \
    build/libs/order-service.jar
```

Lệnh minh họa phân tích static dependencies của artifact trên JDK hỗ trợ các tùy chọn đó. `--multi-release 17` dành cho trường hợp có multi-release JAR phù hợp, **không** phải cách ép `jdeps` đổi nội dung source sang Java 17. Trên Windows, cách phân tách path/wildcard phụ thuộc shell và công cụ.

`jdeps` có thể giúp thấy class references tới package `javax`/`jakarta`, nhưng không tự nhìn thấy những tham chiếu chỉ lưu trong XML, reflection strings, deployment descriptors hoặc message payload.

### 6.4. Tìm kiếm source/configuration

Các từ khóa cần rà soát theo ngữ cảnh:

```text
javax.servlet
javax.ws.rs
javax.persistence
javax.enterprise
javax.inject
javax.validation
javax.jms
javax.transaction
web.xml
persistence.xml
beans.xml
META-INF/services
Class.forName
ServiceLoader
```

Một số string `javax.*` là Java SE hợp lệ; không đánh dấu tất cả là đối tượng cần chuyển.

## 7. Biểu diễn dependency graph có hướng

Định nghĩa một cạnh `A -> B` nếu **A phụ thuộc B**. Ví dụ:

```text
order-web -----------> order-service -------> order-data
    |                       |                     |
    v                       v                     v
common-web             transaction-api        JPA provider
    |                       |
    v                       v
Servlet/JAX-RS          CDI integration
```

Nếu không có chu trình, thường cần chuyển **dependency nền** trước **consumer**, hoặc chuẩn bị sẵn bản tương thích của dependency nền trước khi consumer chuyển.

Đối với đồ thị lớn, việc vẽ theo module kỹ thuật có thể quá chi tiết. Nên dùng hai lớp:

- **Component graph:** module JAR/WAR/service, framework, server và artifact.
- **Contract graph:** giao diện Java, REST endpoints, queue schemas và database schemas mà các component trao đổi.

Component graph cho biết cái gì cần build/triển khai. Contract graph cho biết nhóm nào có thể cùng tồn tại khác phiên bản.

## 8. Phụ thuộc cứng và phụ thuộc mềm

Một cạnh không chỉ có “có” hoặc “không”; nên đánh nhãn khả năng tách:

| Loại quan hệ | Ví dụ | Khả năng chuyển độc lập |
|---|---|---|
| Java type signature | Một module nhận `javax.persistence.EntityManager`. | Rất thấp nếu signature buộc namespace cũ. |
| Container-managed integration | CDI bean inject vào JAX-RS resource. | Thấp nếu dùng một runtime Jakarta đồng bộ. |
| Shared framework internals | Module gọi API nội bộ của framework. | Thấp và rủi ro cao. |
| JPA entity annotations | Provider tìm entity dùng annotation namespace cụ thể. | Thường phải đồng bộ provider/metadata. |
| HTTP/JSON contract | Service A gọi service B qua DTO JSON ổn định. | Cao hơn nếu giữ backward/forward compatibility. |
| Queue event schema | Producer/consumer chia sẻ Avro/JSON/XML schema versioned. | Có thể tách nếu reader xử lý cả hai format. |
| Database schema | Hai service cùng sửa một table. | Rủi ro cao; cần migration tương thích, coordination. |
| CLI/file exchange | Batch đọc file được version hóa. | Có thể độc lập nếu format được bảo đảm. |

Đồ thị nên ghi rõ mức **cứng/mềm** cho từng cạnh và lý do. Không chia nhóm chỉ dựa trên cấu trúc thư mục hoặc tên package.

## 9. Chu trình phụ thuộc và strongly connected components

Trong monolith nhiều năm tuổi, có thể có chu trình:

```text
order-web -> order-service -> common-domain
    ^                             |
    |                             |
    +-----------------------------+
```

Nếu cả ba module gọi trực tiếp các interface chứa kiểu `javax.*` lẫn nhau, việc nâng một module riêng có thể không khả thi.

Theo lý thuyết đồ thị, một **strongly connected component (SCC)** là tập nút có thể đi tới nhau theo hướng cạnh. Có thể coi mỗi SCC là ứng viên cho một migration unit, rồi nén chúng lại để tạo đồ thị không chu trình (DAG).

Tuy nhiên, **SCC không đồng nghĩa bắt buộc deploy chung** trong mọi trường hợp. Nếu một cạnh trong chu trình được thay bằng REST/queue interface tương thích hoặc adapter ổn định, SCC có thể được tách. Vì thế, kế hoạch cần cân nhắc:

1. Chuyển cả SCC trong một wave nếu đủ kiểm soát và quy mô hợp lý.
2. Hoặc chủ động phá chu trình bằng interface tách biệt, adapter hoặc boundary rõ ràng.
3. Sau đó phân tích lại DAG và thứ tự chuyển đổi.

Tách nhóm bằng cách **thay ranh giới phụ thuộc** là việc thiết kế kiến trúc, không phải thao tác chỉ đổi import.

## 10. Ranh giới Java-level khác ranh giới giao thức

Đây là quyết định quan trọng nhất khi nhóm dùng hai namespace song song.

Một Java class như:

```java
public interface OrderHandler {
    void handle(javax.servlet.http.HttpServletRequest request);
}
```

không thể chỉ được dùng như một interface nhận `jakarta.servlet.http.HttpServletRequest`. Hai kiểu không assignable cho nhau.

Một ranh giới được định nghĩa độc lập hơn:

```java
public interface OrderHandler {
    OrderResult handle(OrderCommand command);
}
```

với DTO không chứa kiểu Servlet/JPA/CDI có thể giảm phụ thuộc vào namespace. Adapter web cũ và adapter web mới có thể chuyển request của môi trường mình sang cùng `OrderCommand`.

Cấu trúc:

```text
Legacy Servlet adapter (javax) ----+
                                    |
                                    v
                            Domain contract
                                    ^
                                    |
Jakarta Servlet adapter -----------+
```

**Điều kiện:** contract chung phải thật sự độc lập với container, không trả lại hoặc truyền qua các kiểu Java EE/Jakarta không tương thích. Với hai tiến trình, chuyển qua HTTP/queue còn giúp tránh classloader/type identity. Với cùng JVM, vẫn phải đảm bảo classpath và runtime không xung đột.

## 11. Chọn chiến lược chuyển: một lần, nhiều wave hoặc strangler

### 11.1. One-shot/coordinated migration

Nâng toàn bộ một application deployable và runtime liên quan trong một thay đổi lớn.

Phù hợp khi:

- Có một WAR/EAR với namespace API liên kết chặt.
- Runtime/container không cho phép trộn hai thế hệ API trong cùng deployment.
- Bộ test đủ mạnh và rollback cả deployment có thể thực hiện.
- Dữ liệu/schema bên ngoài không đổi hoặc đã sẵn sàng hai chiều.

Nhược điểm là phạm vi lỗi lớn, thời gian tích hợp dài và khó xác định nguyên nhân nếu đồng thời nâng framework, JDK và database schema.

### 11.2. Migration theo wave

Chia tập component thành các nhóm có thể kiểm thử/triển khai riêng, chuyển nhóm nền hoặc nhóm có boundary ổn định trước.

Ví dụ:

```text
Wave 0  -> Baseline + dependency inventory + contract tests
Wave 1  -> Tách domain API khỏi javax/Jakarta, chuẩn hóa DTO
Wave 2  -> Nâng runtime/framework/BOM cho một deployable thí điểm
Wave 3  -> Web + CDI + Validation + JPA cùng deployment
Wave 4  -> Messaging + batch + integrations và consumers phụ thuộc
Wave 5  -> Loại bỏ adapters, cấu hình cũ, regression hardening
```

Trình tự chỉ minh họa. Trong một hệ thống khác, messaging có thể phải chuyển trước hoặc nằm cùng wave với JPA vì cùng transaction boundary.

### 11.3. Strangler-style

Giữ một ứng dụng legacy hoạt động trong khi từng chức năng được chuyển sang ứng dụng/runtime Jakarta mới, giao tiếp qua API hoặc event.

Phù hợp khi hệ thống quá lớn để nâng một lần, cần triển khai liên tục và có thể định nghĩa boundary dữ liệu ổn định. Cần tính tới routing, phân quyền, duplicate processing, transaction distributed và trách nhiệm sở hữu dữ liệu.

**Không nên** xem việc chạy song song hai ứng dụng là miễn phí: chi phí vận hành, đồng bộ dữ liệu và logic nghiệp vụ có thể tăng trong giai đoạn chuyển tiếp.

## 12. Phân nhóm theo *runtime compatibility cohort*

Trong Java EE/Jakarta, runtime thường định hình ranh giới chuyển đổi:

| Thành phần | Câu hỏi tương thích cần kiểm chứng |
|---|---|
| Jakarta Servlet / web container | Container có nhận API namespace và spec version đích không? |
| Jakarta REST runtime | JAX-RS implementation/version có phù hợp container, CDI và JSON provider không? |
| Jakarta CDI | CDI API, bean discovery, interceptor và extension provider có cùng thế hệ? |
| Jakarta Persistence | JPA API, ORM provider, enhancement, mapping, cache và transaction có tương thích? |
| Jakarta Validation | Validation API, implementation, EL provider và REST integration có đồng bộ? |
| Jakarta Messaging | JMS API/provider/client, connection factories và transaction integration có phù hợp? |
| Jakarta Security | Authentication/authorization integration, filters và security constraints còn đúng? |
| JSON/XML Binding | JSON-B/Jackson/JAXB providers, namespaces và wire formats có ổn định? |
| Application server | Server BOM/spec profile, classloading rules và deploy descriptors phù hợp? |

Không có quy tắc “chỉ cần mọi artifact đều mang tiền tố jakarta là tương thích”. Ví dụ, một API có thể được cung cấp bởi container nhưng ứng dụng lại đóng gói một implementation khác vào WAR, dẫn tới duplicate classes/provider conflicts. Phải đọc support matrix chính thức của **tổ hợp**, không chỉ từng thư viện riêng.

## 13. Chọn runtime và framework trước khi khóa dependency BOM

Đổi riêng các Jakarta API JAR không biến application server cũ thành Jakarta runtime. Một application server hoặc embedded framework chịu trách nhiệm tạo servlet, quản lý CDI/JPA, transaction, messaging và nhiều lifecycle service.

Quy trình chọn target:

1. Xác định mục tiêu JDK và chu kỳ hỗ trợ.
2. Chọn application server hoặc framework hỗ trợ Jakarta spec version cần dùng.
3. Kiểm tra runtime có implement/spec profile thích hợp hay phải bổ sung provider.
4. Chọn BOM/dependency management của framework hoặc runtime tương ứng.
5. Xác định đâu là dependency **provided** bởi container và đâu là dependency cần đóng gói.
6. Kiểm tra plugin build/test/deploy và container image.
7. Khóa một combination đã được kiểm thử trước khi bắt đầu chuyển nhiều module.

Ví dụ Maven nếu runtime cung cấp Servlet API:

```xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>VERSION_COMPATIBLE_WITH_CONTAINER</version>
    <scope>provided</scope>
</dependency>
```

Version trong mẫu là placeholder, cần thay bằng version được runtime hỗ trợ. Không nên blindly đặt bản mới nhất rồi đóng gói một API JAR không phù hợp vào WAR. Với embedded server, cấu hình dependency khác: implementation/container có thể nằm trên application runtime classpath.

## 14. Ví dụ chuyển đổi Servlet Filter theo nhóm

Một filter cũ:

```java
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import java.io.IOException;

public final class LegacyRequestFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
```

Phiên bản Jakarta:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import java.io.IOException;

public final class JakartaRequestFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
```

Thay đổi ở source trông nhỏ, nhưng phạm vi nhóm còn gồm:

- Server/container đang khởi tạo filter.
- `web.xml` hoặc annotation `@WebFilter`.
- Framework/security filters chạy trước/sau.
- `FilterRegistration` nếu được tạo bằng code.
- Các thư viện nhận `ServletRequest`/`FilterChain` trong public signature.
- Servlet API version mà framework sử dụng.
- Session/cookie/authentication integration và test infrastructure.

Nếu một security filter library chưa hỗ trợ Jakarta Servlet, việc đổi import ở filter của ứng dụng không làm filter library tự tương thích. Cần nâng hoặc thay library đó trong **cùng nhóm web/security**.

## 15. Ví dụ chuyển CDI + JPA + Validation cùng nhau

Một service cũ có thể kết hợp:

```java
import javax.enterprise.context.ApplicationScoped;
import javax.inject.Inject;
import javax.persistence.EntityManager;
import javax.transaction.Transactional;
import javax.validation.Valid;

@ApplicationScoped
public class OrderService {
    @Inject
    EntityManager entityManager;

    @Transactional
    public void create(@Valid OrderInput input) {
        entityManager.persist(
                new OrderEntity(input.reference()));
    }
}
```

Bản Jakarta tương ứng:

```java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;
import jakarta.validation.Valid;

@ApplicationScoped
public class OrderService {
    @Inject
    EntityManager entityManager;

    @Transactional
    public void create(@Valid OrderInput input) {
        entityManager.persist(
                new OrderEntity(input.reference()));
    }
}
```

`OrderInput` và `OrderEntity` trong ví dụ là DTO/entity do ứng dụng định nghĩa. Để chạy được, phải kiểm tra thêm:

- Provider JPA hỗ trợ `jakarta.persistence.*`.
- Entity annotations, entity scanning, custom converters và named queries.
- CDI runtime và extension libraries.
- Transaction manager và propagation semantics.
- Bean Validation provider và annotation metadata.
- `persistence.xml`, `beans.xml`, datasource và transaction settings.
- Test runner và test container khởi tạo CDI/JPA/transaction đúng thế hệ.

Đây là ví dụ của **nhóm phụ thuộc chặt theo container lifecycle**. Việc biên dịch được một `OrderService` chưa chứng minh bootstrapping và transaction hoạt động.

## 16. Lập kế hoạch với Java EE API và Java SE API đan xen

Dự án có thể chứa hàng trăm import `javax`, nhưng một phần không thuộc phạm vi Jakarta.

Ví dụ:

```java
import javax.sql.DataSource;     // Java SE: giữ nguyên
import javax.naming.InitialContext; // Java SE: giữ nguyên
import javax.crypto.Cipher;     // Java SE: giữ nguyên

import javax.persistence.Entity; // Java EE/Jakarta: cần xem xét
import javax.ws.rs.Path;        // Java EE/Jakarta: cần xem xét
```

Chú thích này nói về **phân loại nguồn sở hữu API**, không phải khẳng định mọi class ở source luôn có sẵn trên mọi JDK. Khi nâng JDK, một số Java EE module từng được JDK phân phối đã bị loại bỏ; ví dụ JEP 320 loại bỏ các Java EE/CORBA modules liên quan từ JDK 11.

Để lập kế hoạch chính xác, tạo mapping:

| Old symbol/artifact | API owner | New symbol/artifact | Hành động |
|---|---|---|---|
| `javax.servlet.Filter` | Servlet / Jakarta Servlet | `jakarta.servlet.Filter` | Chuyển cùng web container/framework. |
| `javax.persistence.Entity` | JPA / Jakarta Persistence | `jakarta.persistence.Entity` | Chuyển cùng ORM/provider. |
| `javax.validation.Valid` | Bean Validation / Jakarta Validation | `jakarta.validation.Valid` | Chuyển cùng validator integration. |
| `javax.jms.Message` | JMS / Jakarta Messaging | `jakarta.jms.Message` | Chuyển cùng provider/client. |
| `javax.xml.bind.JAXBContext` | JAXB / Jakarta XML Binding | `jakarta.xml.bind.JAXBContext` theo target. | Kiểm tra API/runtime riêng và XML contracts. |
| `javax.sql.DataSource` | Java SE JDBC API | Giữ `javax.sql.DataSource`. | Không replace hàng loạt. |
| `javax.naming.InitialContext` | Java SE JNDI API | Giữ `javax.naming.InitialContext`. | Xác minh JNDI resources khi đổi server. |
| `javax.annotation.processing.Processor` | Java SE compiler API | Giữ `javax.annotation.processing.Processor`. | Không đổi do Jakarta namespace. |

Một mapping có owner và nguồn tài liệu rõ ràng hữu ích hơn script thay toàn bộ chuỗi `javax.`.

## 17. Những dependency ẩn cần đưa vào nhóm

Một ứng dụng có thể không import một thư viện trực tiếp nhưng vẫn phụ thuộc nó qua runtime.

### 17.1. Reflection và annotation scanning

Framework có thể tìm class theo tên string hoặc annotation:

```java
Class<?> type = Class.forName(configuredClassName);
```

Nếu `configuredClassName` còn trỏ tới provider package cũ, compile vẫn xanh nhưng runtime thất bại. Xem cả properties, XML descriptors, bean scanning rules và generated metadata.

### 17.2. Service Provider Interface

`META-INF/services` có thể chứa tên provider hoặc service interface thuộc namespace cũ. Nếu library chuyển sang `jakarta.*`, file service configuration, module descriptor và provider phải cùng đổi theo hợp đồng mới.

### 17.3. Generated code

OpenAPI clients, JAXB/XJC, JPA metamodel, QueryDSL, annotation processors hoặc code generator khác có thể sinh import `javax.*` dù source viết tay đã đổi.

Cần lập danh sách generator/version và xác định thứ tự: **nâng generator và template trước khi sinh lại code**. Không sửa hàng loạt generated output rồi để lần build tiếp theo ghi đè trở lại.

### 17.4. Container descriptors

Các file như `web.xml`, `persistence.xml`, `beans.xml`, descriptors giao dịch hoặc security có namespace/schema version. Không chỉ thay Java import; hãy đối chiếu descriptor schema và target runtime.

### 17.5. Plugins và third-party extensions

CDI extensions, Hibernate listeners, servlet filters, JAX-RS filters và test runners có thể liên kết với namespace cũ. Mỗi plugin cần version tương thích hoặc kế hoạch thay thế.

## 18. Chọn thứ tự wave theo dependency graph

Sau khi nén các nhóm không thể tách, ta có đồ thị:

```text
Core DTO/contract
       |
       +----> Persistence integration
       |             |
       |             v
       +----> Domain service ------> Web + API
       |                                 |
       +----> Event contract             +----> external clients
                     |
                     v
                Messaging adapters
                     |
                     v
                 Batch consumers
```

Nếu cạnh biểu thị “consumer phụ thuộc provider”, thường nên chuẩn bị một bản **provider tương thích** trước, rồi nâng consumer. Tuy nhiên, thứ tự triển khai phụ thuộc vào hợp đồng tại boundary.

Ví dụ:
- Nếu REST consumer V1 không hiểu field mới, cần nâng consumer trước khi producer phát field đó.
- Nếu database schema mới không tương thích với app cũ, cần mở rộng schema theo cách giữ app cũ chạy được trước.
- Nếu hai module trao đổi trực tiếp Jakarta Java types và deploy cùng WAR, có thể phải nâng cùng lúc.
- Nếu message format đã versioned và consumer tolerant, producer và consumer có thể chuyển ở hai wave khác nhau theo contract.

Tóm lại, **thứ tự build theo Java dependencies** và **thứ tự rollout theo dữ liệu/giao thức** có thể khác nhau. Kế hoạch phải diễn đạt cả hai, không chỉ có một danh sách module theo thứ tự.

## 19. Bảng kế hoạch wave có điều kiện vào/ra

Ví dụ cho hệ thống order:

| Wave | Mục tiêu | Thành phần | Điều kiện bắt đầu | Điều kiện kết thúc |
|---|---|---|---|---|
| 0 — Baseline | Xác lập trạng thái cũ. | Build, CI, dependency inventory, contract fixtures. | Có hệ thống đang chạy. | Reproduce build và test của bản cũ. |
| 1 — Tách boundary | Không để public domain API lộ `javax.*`. | DTO, domain API, adapters. | Đã hiểu dependency graph. | Contract độc lập với container và có tests. |
| 2 — Runtime pilot | Xác nhận tổ hợp Jakarta đích. | Server/framework/BOM + một feature nhỏ. | Target support matrix hợp lệ. | Bootstrap, auth, JPA, logging và deploy ổn. |
| 3 — Core app | Chuyển application deployable chính. | Servlet/REST/CDI/JPA/Validation. | Các plugin/provider tương thích sẵn. | Integration/contract tests xanh. |
| 4 — Integrations | Chuyển message, batch, client SDK liên quan. | JMS, REST clients, batch. | Wire contracts hỗ trợ chạy song song. | Không còn đường gọi namespace cũ không được hỗ trợ. |
| 5 — Cleanup | Loại bỏ legacy bridges. | Config, transformers, imports cũ. | Không còn traffic/data cần legacy behavior. | Đã có rollback plan và evidence. |

Một wave không được hoàn thành chỉ vì source compile. Cần các **exit criteria** có thể đo: test pass, artifact được deploy, contract tương thích, resource usage và khả năng rollback xác nhận.

## 20. Dùng *expand → migrate → contract* cho ranh giới dữ liệu

Khi hai nhóm được nâng ở hai thời điểm, data contract phải hỗ trợ giai đoạn cùng tồn tại.

### 20.1. Expand

Triển khai consumers có thể đọc cả dạng dữ liệu cũ và mới. Nếu đổi tên JSON field, reader có thể nhận alias cũ trong giai đoạn quá độ. Nếu đổi schema DB, thêm column mới mà chưa xóa column cũ khi ứng dụng cũ còn cần.

### 20.2. Migrate

Producer chuyển dần sang định dạng mới hoặc thực hiện dual-write/dual-read có kiểm soát. Theo dõi số messages/records còn ở format cũ và các client chưa nâng.

### 20.3. Contract

Chỉ xóa đường đọc cũ khi dữ liệu lưu trữ đã chuyển hoặc hết thời gian tồn tại và không còn consumer legacy. Quyết định xóa cần evidence, owner và điều kiện rollback.

Ví dụ JSON:

```json
{
  "eventVersion": 2,
  "orderId": "ORD-10",
  "status": "CREATED",
  "occurredAt": "2026-11-12T00:00:00Z"
}
```

Đây là ví dụ schema event, **không liên quan trực tiếp** đến package `javax` hay `jakarta`. Namespace Java là vấn đề source/binary; JSON wire format là hợp đồng độc lập. Tách hai loại thay đổi khi có thể sẽ giảm rủi ro migration.

## 21. Shared database và transaction boundary

Một nhóm JPA được chuyển thành công chưa chắc tương thích với database schema đang được nhiều ứng dụng dùng chung.

Cần xác định:

- Entity mapping cũ và mới cho cùng table/column.
- Cách tạo khóa, optimistic locking và transaction isolation.
- Schema migrations có backward-compatible không.
- Dữ liệu được serialize vào DB (JSON/XML/blob) có đổi representation không.
- Batch/reporting service dùng driver/ORM nào.
- Cache layer 2 và query cache có tương thích không.
- App cũ có thể chạy khi schema đã nâng không.

Ví dụ một thay đổi nguy hiểm là xóa column trong cùng đợt triển khai app Jakarta mới, trong khi batch Java EE cũ vẫn đọc column đó.

Một kế hoạch an toàn hơn là:
1. Thêm column hoặc view mới mà không phá read path cũ.
2. Chạy migration dữ liệu với kiểm tra tính đầy đủ.
3. Đưa code mới có thể đọc/ghi theo kế hoạch.
4. Chuyển consumers còn lại.
5. Xóa schema cũ sau khi có bằng chứng không còn phụ thuộc.

Với transaction trải qua nhiều service, không giả định rằng di chuyển chúng vào hai runtime độc lập vẫn giữ atomic transaction như trước. Có thể cần outbox, idempotency hoặc quy trình bù trừ; đây là thay đổi kiến trúc, cần được lên kế hoạch và kiểm thử riêng.

## 22. Khác biệt khi chuyển monolith và microservices

### 22.1. Monolith / EAR nhiều module

Trong EAR hoặc WAR truyền thống, các module có thể chia sẻ:

- Một application server.
- CDI/JPA transaction context.
- Classloader hierarchy.
- Entity objects và local Java interfaces.
- Security realm và JNDI resources.

Do đó, dù source chia thành nhiều Maven/Gradle modules, **deployable/runtime boundary** có thể buộc chúng chuyển cùng nhau. Các module chỉ có thể được nâng lệch namespace nếu có ranh giới adapter và classloading thật sự được runtime hỗ trợ.

### 22.2. Microservices giao tiếp qua HTTP/queue

Mỗi service có thể chọn runtime Jakarta riêng nếu giao thức tương thích:

```text
Legacy service (Java EE / javax)
              |
              | HTTP/JSON
              v
New service (Jakarta / jakarta)
```

Thành phần này không cần trao `javax.servlet.HttpServletRequest` hoặc `jakarta.servlet.HttpServletRequest` qua network; chúng trao JSON, HTTP status, headers hoặc event schema.

Điều kiện là contract phải rõ: authentication, correlation IDs, retry/idempotency, versioned payload, timezone, error semantics và deployment order. Không đơn giản nghĩ “tách process là hoàn tất migration”, vì shared DB và transaction có thể vẫn tạo phụ thuộc chặt.

## 23. Sử dụng adapter để giảm nhóm buộc nâng cùng lúc

Một adapter có thể giữ contract domain ổn định, còn lớp ngoài đổi theo runtime.

Ví dụ domain API:

```java
package com.example.order.domain;

public record CreateOrderCommand(
        String customerId,
        String productCode,
        int quantity) {
}

public interface CreateOrderUseCase {
    String create(CreateOrderCommand command);
}
```

Adapter Servlet phía Jakarta:

```java
package com.example.order.web;

import com.example.order.domain.CreateOrderCommand;
import com.example.order.domain.CreateOrderUseCase;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

public final class OrderServlet extends HttpServlet {
    private final CreateOrderUseCase useCase;

    public OrderServlet(CreateOrderUseCase useCase) {
        this.useCase = useCase;
    }

    @Override
    protected void doPost(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException {
        String id = useCase.create(new CreateOrderCommand(
                request.getParameter("customerId"),
                request.getParameter("productCode"),
                Integer.parseInt(request.getParameter("quantity"))));
        response.setContentType("text/plain");
        response.getWriter().write(id);
    }
}
```

Đây là ví dụ cho **ranh giới kiểu dữ liệu**. Cách khởi tạo/đăng ký servlet có constructor nhận dependency cần được tích hợp vào container hoặc framework đúng cách; container không mặc nhiên gọi constructor này khi chỉ scan servlet thông thường. Trong ứng dụng thật, có thể dùng CDI, DI framework hoặc đăng ký servlet bằng code.

Đừng dùng ví dụ minh họa này như implementation production: cần validation, authentication, xử lý lỗi HTTP và transaction semantics phù hợp.

Mục tiêu của adapter là ngăn domain layer nhận trực tiếp `HttpServletRequest` hoặc `EntityManager` trong public API. Khi đó thay runtime web không buộc toàn bộ business code biết Jakarta API.

## 24. Công cụ hỗ trợ rewrite source và bytecode

Có thể dùng các công cụ migration tự động để giảm lỗi thao tác:

- **OpenRewrite:** áp dụng recipes cho source/build configuration theo framework hoặc dependency.
- **Eclipse Transformer:** có thể chuyển đổi một số namespace của Java EE/Jakarta ở mức archive/class/resource theo rules.
- **IDE refactoring và build tools:** sửa import, annotation, cấu hình và generator.
- **Static API diff tools:** kiểm tra version và các API không tương thích.
- **jdeps:** giúp điều tra bytecode references.

### 24.1. Khi nào nên dùng công cụ?

Khi phạm vi import/annotation lớn, script tự động có thể tiết kiệm thời gian. Tuy nhiên, công cụ không quyết định thay bạn:
- Runtime/container target có hỗ trợ tổ hợp version hay không.
- Thành phần nào phải cùng nâng.
- Các `javax.*` nào thuộc Java SE không được đổi.
- Có thay đổi semantic, security hoặc dữ liệu hay không.
- Test coverage và rollback đã đủ chưa.

### 24.2. Kiểm soát kết quả biến đổi

Nếu dùng transformer cho third-party artifact trong giai đoạn chuyển tiếp, cần ghi version, checksum, nguồn và license của artifact đã biến đổi; không được coi artifact transformer-output tương đương bản vendor chính thức về support/security.

Tự động rewrite source cũng không giải quyết việc database schema, JMS providers hoặc runtime extensions chưa hỗ trợ Jakarta. Sau khi rewrite, vẫn cần xác nhận compile, bootstrap, integration, contract tests và packaging.

## 25. Lập ma trận compatibility cho nhóm

Ví dụ ma trận cần kiểm chứng:

| Nhóm | Java baseline | Runtime/framework | API namespace | Tình trạng |
|---|---|---|---|---|
| Web + CDI | Java mục tiêu | Jakarta-capable target | `jakarta.*` | Cần xác nhận plugin/security filters. |
| JPA + transaction | Java mục tiêu | ORM + transaction manager phù hợp | `jakarta.persistence.*` | Cần test entity scan, transaction. |
| Validation | Java mục tiêu | Validation provider phù hợp | `jakarta.validation.*` | Cần test DTO và integration. |
| Messaging | Java mục tiêu | Broker client + provider phù hợp | `jakarta.jms.*` | Cần test connection, redelivery. |
| Reporting legacy | Java nguồn/đích theo kế hoạch | Batch runner | Có thể giữ `javax.*` tạm | Chỉ được tách nếu boundary tương thích. |
| Domain contracts | Java baseline chung | Không phụ thuộc container | Không lộ các API container | Cần contract tests. |

Mỗi ô cuối cùng cần điền **version thật** và liên kết tới compatibility matrix chính thức. Mẫu không khẳng định phiên bản Java hoặc provider cụ thể nào là phù hợp.

## 26. Dependency contract để triển khai theo wave

Một nhóm phải có hợp đồng “tương thích với hàng xóm” trước khi được nâng riêng:

```yaml
migrationGroup: web-jakarta
target:
  runtime: "selected-jakarta-runtime"
  java: "supported-jdk"
  namespace: "jakarta"
dependsOn:
  - domain-contract-v2
  - persistence-jakarta
  - validation-jakarta
boundaries:
  http:
    read: [v1, v2]
    write: v1
  database:
    schema: expanded
entryCriteria:
  - target-dependencies-resolved
  - integration-env-ready
  - contract-tests-baselined
exitCriteria:
  - deploy-successful
  - auth-and-session-tests-pass
  - persistence-and-transaction-tests-pass
  - http-contracts-pass
rollback:
  old-runtime-readable-data: true
  rollback-procedure-tested: true
```

Các giá trị trong YAML là minh họa. Trong dự án thật, nhóm có thể ghi chép trong issue tracker, ADR hoặc bảng kế hoạch; điều quan trọng là **tiêu chí vào/ra đo được**, không phải công cụ quản lý nào được dùng.

## 27. Kiểm thử theo ranh giới phụ thuộc

Nếu chỉ chạy unit tests của từng module, rất dễ bỏ sót lỗi nằm ở chỗ nối.

| Ranh giới | Bài kiểm thử cần ưu tiên |
|---|---|
| Servlet / REST / security | Endpoint routing, filter chain, auth, session/cookie, error mapping. |
| CDI / injection | Bean discovery, qualifiers, lifecycle, interceptors, producer methods. |
| JPA / transaction | Entity scanning, schema mapping, rollback, lazy loading, locking. |
| Validation | Constraints, custom validators, message interpolation, REST/JPA hooks. |
| JMS / queue | Serialization, message listener, ack, redelivery, transaction, idempotency. |
| JSON / XML | Golden fixtures, backward/forward compatibility, namespace/schema. |
| JDBC / database | Driver, connection pool, migrations, transaction isolation. |
| Shared domain API | Binary/source compatibility, DTO round-trip, adapter tests. |
| Deployment / container | Startup, CDI/JPA bootstrap, JNDI, packaging, modules/classloader. |

### 27.1. Tách ba lớp test

- **Component test:** kiểm tra logic trong một module với dependency giả lập phù hợp.
- **Integration test:** khởi động provider/container thật để kiểm chứng CDI, JPA, JMS, REST runtime.
- **Contract/end-to-end test:** kiểm tra hành vi qua HTTP, event, DB hoặc external client, đặc biệt khi hai thế hệ cùng tồn tại.

Test suite compile được với Jakarta API chưa chứng minh runtime có đúng implementation provider. Cần chạy trên target runtime hoặc cấu hình test container đại diện.

### 27.2. So sánh kết quả chứ không chỉ trạng thái build

Một serializer hoặc JSON provider mới có thể thay thứ tự field, null inclusion hoặc date formatting. Nếu contract yêu cầu dữ liệu tương đương, dùng semantic assertions; nếu ký raw payload, kiểm tra byte-level canonicalization. Không làm test xanh bằng cách cập nhật golden output tùy tiện nếu output mới vi phạm hợp đồng cũ.

## 28. Kiểm thử migration trong CI

Một pipeline hợp lý có thể được chia:

```text
                 PR source/build
                       |
                       v
               Dependency resolution
                       |
                       v
             Compile + static analysis
                       |
              +--------+--------+
              |                 |
              v                 v
       Component tests    Contract fixtures
              |                 |
              +--------+--------+
                       |
                       v
       Deploy to representative Jakarta runtime
                       |
                       v
              Integration tests
                       |
                       v
          Mixed-version compatibility tests
                       |
                       v
          Security/performance checks
                       |
                       v
                Release candidate
```

Trong thời gian chuyển tiếp, có thể cần hai đường kiểm thử:
- **Legacy mode:** chạy bản hiện hành với các boundary mới được mở rộng.
- **Target mode:** chạy nhóm Jakarta trên runtime mới.

Nếu chỉ test target mode, có thể bỏ sót lỗi làm client/producer cũ không dùng được. Nếu chỉ test legacy mode, không chứng minh target deployment hoạt động.

## 29. Quản lý cấu hình và deployment descriptors

Java EE/Jakarta không chỉ gồm source code. Cần kiểm tra:

- Namespace và version trong `web.xml`, `beans.xml`, `persistence.xml` và các descriptors liên quan.
- Resource/JNDI names và datasource configuration.
- Servlet context path, HTTP headers, session persistence và cookie policy.
- Authentication providers, roles và security constraints.
- Transaction timeout, pool sizing và persistence unit name.
- Logging, metrics, tracing và health probes.
- Build plugin đóng gói WAR/EAR và cách container giải quyết thư viện.
- Chế độ embedded hay externally managed container.

Một thay đổi server có thể đưa ra default khác, dù API source đã sửa đúng. Các default liên quan bảo mật không nên được nới lỏng chỉ để tái tạo hành vi cũ mà không có đánh giá.

## 30. Lập kế hoạch rollback cùng với kế hoạch migrate

Nâng một nhóm xong có thể cần quay lại khi gặp lỗi production. Kế hoạch rollback phải trả lời:

1. Artifact cũ còn triển khai được trên runtime hiện tại không?
2. Có cần khôi phục application server cũ hay chỉ thay WAR?
3. Schema database đã đổi có còn tương thích với phiên bản cũ?
4. Event/message do bản mới đã phát có được consumer cũ đọc không?
5. Có in-flight transactions hoặc messages cần drain?
6. Có cache/session state không tương thích giữa hai version?
7. Nếu song song hai hệ thống, routing và ownership dữ liệu thay đổi ra sao?

Ví dụ:
- Nếu chuyển từ `javax.servlet.*` sang `jakarta.servlet.*` đồng thời đổi container, rollback có thể phải quay lại cả image/container.
- Nếu schema DB đã xóa column mà app cũ cần, rollback code không đủ.
- Nếu message mới chứa enum value chưa tồn tại ở consumer cũ, consumer đó có thể thất bại sau rollback.

Khi thiết kế waves, nên giảm mức thay đổi không thể đảo ngược ở những đợt đầu. Với các migration dữ liệu bắt buộc, phải có chiến lược backup/restore hoặc dual-read đã thử nghiệm.

## 31. Xử lý phụ thuộc bên thứ ba chưa có bản Jakarta

Không phải plugin/thư viện nào cũng cung cấp bản tương thích ở thời điểm dự án cần nâng. Có các lựa chọn:

| Phương án | Khi phù hợp | Đánh đổi |
|---|---|---|
| Chờ/đổi sang bản chính thức hỗ trợ Jakarta | Library còn được bảo trì và roadmap rõ. | Có thể trì hoãn lịch migration. |
| Thay thư viện tương đương | Chức năng có alternative với API/support phù hợp. | Cần sửa code và test behavior. |
| Viết adapter hoặc tách process | Thư viện chỉ tương thích `javax` nhưng có thể cô lập sau contract. | Thêm vận hành/serialization latency. |
| Dùng transformer có kiểm soát | Thư viện gần tương thích và luật transform được kiểm thử. | Rủi ro support, security, reflection, tài nguyên động. |
| Hoãn cả migration unit | Quan hệ chặt chưa thể cắt. | Tiếp tục gánh rủi ro JDK/runtime cũ. |

Không nên cố dùng một third-party filter triển khai `javax.servlet.Filter` trong container chỉ chấp nhận `jakarta.servlet.Filter` mà thiếu adapter/cơ chế hợp lệ. Chúng là hai kiểu Java khác nhau.

Đối với thư viện quan trọng và chưa có giải pháp, ghi thành **blocker có owner** và phương án quyết định, thay vì im lặng đánh dấu wave hoàn tất.

## 32. Lựa chọn giữa mã chung và bản chuyển đổi song song

Đôi khi một thư viện API nội bộ phải phục vụ cả ứng dụng legacy và Jakarta:

### 32.1. Tách core độc lập container

Ưu tiên khi có thể. Các contract domain như `OrderCommand` và `OrderResult` không import Servlet/JPA/CDI, nên một artifact có thể dùng chung.

### 32.2. Hai adapter khác namespace

Có thể phát hành:
- `order-web-javax` cho runtime cũ.
- `order-web-jakarta` cho runtime mới.

Cả hai gọi core API chung. Phải tránh để adapter cùng xuất hiện lẫn lộn trong một classloader/runtime không hỗ trợ. Cần quản lý dependency graph, artifact naming, CI matrix và release version rõ ràng.

### 32.3. Hai branch dài hạn

Chỉ dùng khi không có lựa chọn tốt hơn. Hai branch mang rủi ro drift, security patches không đồng bộ và double maintenance. Nếu bắt buộc, định nghĩa thời hạn kết thúc, quy tắc backport và chỉ số đo lưu lượng legacy.

## 33. Ma trận rủi ro và cách ưu tiên nhóm

Không nên ưu tiên chỉ theo “module nào ít file nhất”. Một nhóm nhỏ nhưng quản lý login hoặc transaction có thể rủi ro hơn nhóm lớn xử lý read-only báo cáo.

Có thể đánh giá theo các chiều:

| Chiều rủi ro | Câu hỏi |
|---|---|
| Độ kết dính | Có bao nhiêu dependency trực tiếp dùng kiểu `javax/jakarta`? |
| Runtime coupling | Có cần container, transaction manager hoặc cùng classloader? |
| Dữ liệu | Có ghi DB/queue hoặc làm thay đổi format lưu lâu dài? |
| Độ phủ kiểm thử | Có contract/integration tests đại diện không? |
| Tính quan trọng | Ảnh hưởng doanh thu, xác thực hoặc tuân thủ? |
| Khả năng rollback | Có thể quay lại mà không cần sửa dữ liệu phức tạp không? |
| Third-party blockers | Có plugin chưa hỗ trợ Jakarta không? |
| Tác động vận hành | Phải thay server, image, certificate hoặc networking không? |

Một cách đơn giản là dùng thang 1–5 cho mỗi chiều rồi tính điểm **định hướng**, không xem tổng điểm là công thức khách quan tuyệt đối. Dùng điểm để đặt câu hỏi và thống nhất thứ tự thí điểm, chứ không thay thế đánh giá chuyên môn.

Wave đầu thường nên có **giá trị học hỏi lớn nhưng tác động production được kiểm soát**, chẳng hạn một chức năng read-only có test và dữ liệu ít nhạy cảm.

## 34. Kế hoạch phối hợp đội ngũ và ownership

Migration theo nhóm cần trách nhiệm rõ ràng:

- **Platform/build team:** JDK, framework/BOM, container, CI, artifact provenance.
- **Web/API team:** Servlet/REST, routing, security filters, API contracts.
- **Domain team:** loại phụ thuộc container khỏi business API, giữ behavior.
- **Persistence team:** JPA, transaction, datasource, schema migration.
- **Integration team:** JMS, HTTP clients, event contracts, external dependencies.
- **QA/reliability:** contract fixtures, integration environments, nonfunctional tests.
- **Security:** auth, parser settings, dependencies, CVEs và cấu hình TLS.
- **Operations:** deploy/rollback, traffic routing, monitoring và incident process.

Đây là phân chia ví dụ; một tổ chức nhỏ có thể gộp nhiều vai trò. Điều quan trọng là mỗi nhóm dependency và mỗi ranh giới giao tiếp có một owner được xác định.

Một record có thể gồm:
- Owner của migration unit.
- Owner phụ thuộc bên ngoài.
- Tài liệu compatibility matrix được chọn.
- Phiên bản artifact đang/đã chuyển.
- Exit criteria và test evidence.
- Quyết định cho blocker.
- Người phê duyệt rollout và rollback.

## 35. Ví dụ kế hoạch tổng hợp

Giả sử cần chuyển một hệ thống `order-web` lớn. Sau inventory phát hiện:

- `common-domain` chứa cả DTO và `javax.persistence` annotations.
- `order-web` dùng Servlet và JAX-RS cũ.
- `order-service` dùng CDI và transaction cũ.
- `order-data` dùng JPA và Validation cũ.
- `order-events` phát JSON messages; phía nhận không dùng Java type trực tiếp.
- `reporting-batch` đọc DB và chạy độc lập.

### 35.1. Phân tích và quyết định

1. Tách `common-domain-api` thành DTO/contract không lệ thuộc container.
2. Chuyển JPA entity/mapping về `order-data` để tránh rò namespace qua API.
3. Gộp `order-web` + `order-service` + `order-data` + CDI/Validation vào một migration unit deployable vì cùng server/lifecycle.
4. Giữ `order-events` theo event contract ổn định để consumer cũ vẫn đọc.
5. Để `reporting-batch` ở wave riêng nếu DB schema vẫn tương thích.
6. Nâng target server/framework/BOM đã được hỗ trợ cùng lúc với deployable Jakarta.
7. Sau khi vận hành ổn, chuyển reporting batch và loại bỏ adapter cũ.

### 35.2. Đồ thị sau khi tách boundary

```text
          common-domain-api
             /    |     \
            v     v      v
       web-app   events  reporting
          |
          v
   [CDI + JPA + Validation]
          |
          v
    Shared database
```

Sơ đồ giản lược: `web-app` và nhóm CDI/JPA/Validation vẫn được nâng cùng wave; `events` và `reporting` có thể tách nếu hợp đồng dữ liệu và DB bảo đảm.

### 35.3. Thứ tự thực hiện

```text
Baseline & fixtures
       |
       v
Domain decoupling
       |
       v
Target runtime pilot
       |
       v
Coordinated Jakarta deployment
       |
       v
Integration + mixed-version verification
       |
       v
Reporting/batch migration
       |
       v
Cleanup & legacy removal
```

Mỗi bước cần có bản ghi pass/fail, artifact version và rollback condition; chỉ xem checklist làm việc là chưa đủ.

## 36. Những tình huống lỗi điển hình

### 36.1. `ClassCastException` giữa hai thế hệ API

**Hiện tượng:** mã cũ cố cast `jakarta.servlet.ServletRequest` thành `javax.servlet.ServletRequest` hoặc ngược lại.

**Nguyên nhân:** hai kiểu Java khác nhau; cùng tên method không làm chúng tương thích.

**Xử lý:** chuyển adapter và runtime cùng thế hệ, hoặc dùng contract độc lập giữa các nhóm.

### 36.2. `NoClassDefFoundError: javax/...`

**Hiện tượng:** một thư viện trong container Jakarta mới vẫn yêu cầu class `javax.servlet.*` hoặc `javax.persistence.*`.

**Nguyên nhân có thể:** artifact chưa nâng, transitive dependency cũ, plugin hoặc generated code.

**Xử lý:** xác định JAR/class đang tham chiếu, đối chiếu dependency graph và support matrix; không chỉ thêm một API cũ vào classpath rồi coi đã tương thích.

### 36.3. CDI không phát hiện bean

**Hiện tượng:** deploy thành công nhưng `@Inject` không được xử lý.

**Nguyên nhân có thể:** annotation cũ, descriptor không đúng, bean discovery settings, CDI extension hoặc provider không phù hợp.

**Xử lý:** kiểm tra runtime CDI, import/metadata và integration test khởi động container thực.

### 36.4. JPA không thấy entity

**Hiện tượng:** entity không được managed hoặc persistence unit bootstrap thất bại.

**Nguyên nhân có thể:** entity annotations thuộc namespace cũ, `persistence.xml` không phù hợp, JPA provider/version khác, class scanning hoặc module accessibility.

**Xử lý:** chuyển entity + ORM provider + config trong cùng nhóm, kiểm thử mapping và transaction.

### 36.5. REST endpoint trả 404 sau migration

**Hiện tượng:** lớp có `@Path` nhưng endpoint không được đăng ký.

**Nguyên nhân có thể:** `javax.ws.rs.Path` còn sót, JAX-RS bootstrap config/provider không đúng hoặc container không scan application.

**Xử lý:** kiểm tra annotation runtime, resource registration và deployment logs.

### 36.6. Unit test pass nhưng production thất bại

**Hiện tượng:** test mock `EntityManager` hoặc tự `new` resource thành công, nhưng server lỗi.

**Nguyên nhân:** unit test không kiểm chứng CDI/JPA/Servlet lifecycle.

**Xử lý:** bổ sung deployment/integration tests trên runtime đại diện.

### 36.7. Rollback không đọc được dữ liệu mới

**Hiện tượng:** app cũ sau rollback không parse message hoặc không dùng được DB schema.

**Nguyên nhân:** đã thay data contract cùng wave mà không giữ backward compatibility.

**Xử lý:** áp dụng expand/migrate/contract và lập kế hoạch rollback dữ liệu.

## 37. Checklist trước khi chốt kế hoạch chuyển đổi

- [ ] Đã xác định Java EE/Jakarta EE source và target, kể cả JDK/runtime.
- [ ] Đã kiểm kê artifact và **resolved dependency versions**, không chỉ khai báo trực tiếp.
- [ ] Đã phân loại `javax.*` thuộc Jakarta spec và `javax.*` thuộc Java SE.
- [ ] Đã biết server/framework/BOM target và compatibility matrix được hỗ trợ.
- [ ] Đã vẽ component graph và contract graph.
- [ ] Đã phân biệt Java type coupling với HTTP/queue/DB boundaries.
- [ ] Đã xác định các chu trình hoặc nhóm phụ thuộc chặt phải nâng cùng.
- [ ] Đã kiểm tra runtime extensions, plugins, generated code và descriptors.
- [ ] Đã có migration units với owner, blockers và entry/exit criteria.
- [ ] Đã xác định wave build order và wave rollout order, không nhầm hai thứ.
- [ ] Đã có contract tests cho các boundary cần tồn tại hai phiên bản.
- [ ] Đã có tests CDI/JPA/Validation/Servlet/JMS trên provider/container thật.
- [ ] Đã có dữ liệu mẫu JSON/XML/message và kiểm tra schema/compatibility.
- [ ] Đã kiểm tra DB schema, transaction và rollback conditions.
- [ ] Đã xác nhận classpath/module path, BOM và provided dependencies.
- [ ] Đã có chiến lược xử lý plugin chưa hỗ trợ Jakarta.
- [ ] Đã có kế hoạch bảo mật, deploy, observability và rollback.
- [ ] Đã quy định khi nào gỡ legacy adapters, transformer và branches.
- [ ] Đã ghi lại quyết định kiến trúc và chứng cứ tương thích cho từng nhóm.

## 38. Tài liệu tham khảo

- [Jakarta EE Specifications](https://jakarta.ee/specifications/): các đặc tả và phiên bản API Jakarta EE.
- [Jakarta EE Platform](https://jakarta.ee/specifications/platform/): các release platform và profile liên quan.
- [Jakarta EE 9 Release](https://jakarta.ee/release/9/): bối cảnh chuyển namespace Java EE sang Jakarta.
- [Jakarta EE Migration Guides](https://jakarta.ee/learn/): tài liệu học và hướng dẫn migration từ hệ sinh thái Jakarta.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): các module từng thuộc JDK và bị loại từ Java 11.
- [Eclipse Transformer](https://github.com/eclipse-transformer/transformer): công cụ chuyển đổi namespace/resource phù hợp một số trường hợp migration.
- [OpenRewrite](https://docs.openrewrite.org/): công cụ rewrite source/build theo recipes.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): phân tích resolved dependency tree.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): xem dependency graph và dependencyInsight.
- [Oracle jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): phân tích phụ thuộc static trong class/JAR.
- [Semantic Versioning](https://semver.org/): cách diễn giải version khi phù hợp với dự án; không thay thế compatibility matrix.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): hợp đồng API Servlet theo Jakarta.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): hợp đồng API persistence theo Jakarta.
- [Jakarta Contexts and Dependency Injection](https://jakarta.ee/specifications/cdi/): CDI spec và integration points.

## Kết luận

Lập kế hoạch chuyển Java EE sang Jakarta EE theo **nhóm thành phần phụ thuộc nhau** là cách kiểm soát rủi ro source, binary, runtime và dữ liệu hiệu quả hơn việc đổi import từng module. Hãy bắt đầu bằng inventory và dependency graph, phân biệt API Java SE với Jakarta, tìm các thành phần liên kết chặt bởi container và namespace rồi chọn migration units phù hợp. Sau đó sắp wave theo điều kiện tương thích của **cả Java dependencies lẫn các ranh giới HTTP, queue và database**, với entry/exit criteria, integration tests và rollback rõ ràng. Những module giao tiếp bằng contract ổn định có thể chuyển lệch thời điểm; những module chia sẻ trực tiếp kiểu `javax/jakarta` hoặc cùng lifecycle của container thường phải được nâng cùng. Mục tiêu cuối cùng không chỉ là deploy được bản Jakarta, mà là duy trì nghiệp vụ và dữ liệu xuyên suốt quá trình nhiều phiên bản cùng tồn tại.

