# Tích hợp Cosmos DB với Spring Data

## 1. Bài toán: Spring Boot cần lưu tài liệu NoSQL trên Azure

Một dịch vụ Spring Boot quản lý đơn hàng cho nhiều cửa hàng. Mỗi đơn hàng có mã định danh, tenant, khách hàng, trạng thái, số tiền và thời điểm cập nhật. Hệ thống cần:

- Lưu JSON documents mà không phải thiết kế bảng quan hệ cho mọi trường bổ sung.
- Đọc và cập nhật đơn hàng theo tenant, bảo vệ dữ liệu giữa các khách hàng.
- Chạy ổn định khi số requests tăng và Azure Cosmos DB trả throttling.
- Truy cập bằng **Microsoft Entra ID/managed identity** khi triển khai trên App Service, Azure Functions hoặc AKS.
- Theo dõi **RU/s, HTTP 429, latency, request charge và chi phí**.
- Có thể kiểm thử, triển khai nhiều môi trường và khôi phục sau lỗi.

**Spring Data Cosmos** giúp dùng entity, repository và những convention quen thuộc của Spring Data để làm việc với **Azure Cosmos DB for NoSQL**. Tuy nhiên, việc có repository không làm biến mất giới hạn của hệ thống phân tán: **partition key, throughput, consistency, idempotency và authorization** vẫn phải được thiết kế cẩn thận.

Bài thuộc chương **Spring Boot trên Azure** trong module **CLOUD_PROVIDERS_AZURE**. Ngữ cảnh xuyên suốt là xây dựng ứng dụng Azure từ subscription/resource group, Microsoft Entra ID, mạng ảo, compute, lưu trữ đến giám sát, bảo mật và kiểm soát chi phí. Nội dung này tập trung vào *tích hợp Cosmos DB với Spring Data*, không thay thế bài riêng về tất cả các API của Cosmos DB.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Cosmos account, database, container, item, logical/physical partition và RU.
2. Phân biệt **Azure Cosmos DB for NoSQL** với MongoDB/Cassandra/Gremlin và các SDK khác.
3. Chọn dependency **Spring Cloud Azure Starter Data Cosmos** phù hợp phiên bản Spring Boot.
4. Cấu hình endpoint, database và credentials không hardcode.
5. Xây entity bằng **@Container**, **@Id**, **@PartitionKey** và repository bằng **CosmosRepository**.
6. Triển khai save, find, query và delete theo đúng access pattern.
7. Biết khi nào Spring Data repository không tương đương với point read hiệu quả.
8. Tích hợp async/reactive bằng **ReactiveCosmosRepository**, Mono/Flux và WebFlux khi thích hợp.
9. Dự tính RU/s, nhận biết throttling 429 và đặt retry/backpressure có giới hạn.
10. Hiểu optimistic concurrency, ETag và phạm vi transaction.
11. Đặt ranh giới tenant authorization và data-plane RBAC cho managed identity.
12. Thiết kế indexing, TTL, schema evolution và migration partition key.
13. Theo dõi latency, request charge, partition skew, errors và budget.
14. Kiểm thử bằng mocks/lab, xây API có error mapping và triển khai an toàn trên Azure.

## 3. Spring Data Cosmos nằm ở đâu trong kiến trúc?

Một kiến trúc điển hình:

~~~mermaid
flowchart LR
    USER[Web / Mobile] --> API[Spring Boot REST API]
    API --> AUTH[Authentication + Authorization]
    AUTH --> SVC[OrderService]
    SVC --> REPO[Spring Data Cosmos Repository]
    REPO --> SDK[Azure Cosmos Java SDK]
    SDK --> NET[HTTPS / Private Endpoint]
    NET --> DB[(Azure Cosmos DB for NoSQL)]
    ID[Microsoft Entra / Managed Identity] --> SDK
    API --> OBS[Application Insights]
    DB --> MON[Azure Monitor]
~~~

Trong đó:

- **Spring MVC/WebFlux** nhận và phản hồi HTTP requests.
- **Business service** thực thi quy tắc nghiệp vụ và authorization.
- **Spring Data Cosmos** ánh xạ Java documents thành items, tạo repository query methods.
- **Cosmos DB Java SDK v4** là tầng client phục vụ giao tiếp Cosmos DB for NoSQL.
- **Cosmos DB service** lưu dữ liệu, quản lý partitioning, indexing, replication và throughput.
- **Azure Monitor/Application Insights** dùng để giám sát cả phía database lẫn ứng dụng.

**Repository là một abstraction lập trình, không phải ranh giới bảo mật.** Việc ứng dụng có thể đọc container không có nghĩa mọi người dùng HTTP đều được đọc mọi item.

## 4. Phạm vi dịch vụ: Cosmos DB for NoSQL

Spring Data Cosmos được đề cập ở đây dùng **Azure Cosmos DB for NoSQL**, trong khi Azure Cosmos DB còn có những API/model khác.

| Thành phần | Vai trò |
|---|---|
| **Cosmos account** | Resource Azure với endpoint, regions, authentication và cấu hình dịch vụ |
| **Database** | Nhóm logic của containers |
| **Container** | Tập JSON items, partition key path, index/TTL/throughput |
| **Item** | JSON document có thuộc tính id và những field của nghiệp vụ |
| **Logical partition** | Items có cùng partition key value |
| **Physical partition** | Đơn vị hạ tầng phục vụ dữ liệu và capacity theo cách dịch vụ quản lý |
| **RU** | Request Unit, thước đo resource cost của một operation |
| **RU/s** | Năng lực request units mỗi giây theo capacity model |
| **429** | Request bị throttled khi thiếu capacity ở phạm vi liên quan |

### 4.1. Không nhầm Spring Data Cosmos với Spring Data MongoDB

Cosmos DB có API MongoDB riêng nhưng **Spring Data Cosmos** dùng mô hình SDK/query của Cosmos DB for NoSQL. Không trộn dependency/query annotations dành cho MongoDB vào ví dụ này.

### 4.2. Không nhầm JSON linh hoạt với không cần schema

Dữ liệu có thể có những thuộc tính khác nhau giữa documents, nhưng Java application vẫn cần validation, schema version và migration strategy. Một lỗi đổi kiểu từ số sang string vẫn có thể làm code thất bại.

### 4.3. Khi nào không nên chọn Cosmos DB?

Nếu workload chủ yếu là joins phức tạp, relational transactions xuyên nhiều aggregates hoặc báo cáo OLAP quét khối dữ liệu rất lớn, cần so sánh Azure SQL, PostgreSQL, analytics engine và Cosmos DB theo access patterns thực tế. Không chọn NoSQL chỉ vì entity mapping thuận tiện.

## 5. Thiết kế dữ liệu trước khi viết Repository

Một document ví dụ:

~~~json
{
  "id": "ORD-1001",
  "tenantId": "shop-42",
  "customerId": "C-20",
  "status": "CREATED",
  "amountMinor": 125000,
  "updatedAtUtc": "2026-11-20T10:00:00Z",
  "schemaVersion": 1
}
~~~

Container **orders** dùng partition key path **/tenantId**.

### 5.1. Partition key path và partition key value

- **/tenantId** là đường dẫn field được cấu hình ở container.
- **shop-42** là giá trị partition key của document.
- **id + tenantId** là cặp thông tin quan trọng khi cần point read/update/delete.
- Hai items ở những tenants khác nhau có thể cùng id theo định danh cục bộ của logical partition.

### 5.2. Vì sao tenantId hợp với một số ứng dụng?

Các thao tác thường tìm đơn hàng của một tenant. Query có tenantId giúp khoanh phạm vi truy vấn, đặc biệt trong multi-tenant application. Nhưng nếu một tenant chiếm phần lớn writes, khóa **/tenantId** có nguy cơ tạo hot logical partition.

### 5.3. Chọn partition key bằng access patterns

| Mô hình | Partition key có thể cân nhắc | Đánh đổi |
|---|---|---|
| Multi-tenant orders | /tenantId | Tenant rất lớn có thể thành hot key |
| User profile | /userId | Point read thuận tiện theo user |
| IoT telemetry | /deviceId | Thiết bị gửi cực nhiều có thể nóng |
| Cart của người dùng | /customerId | Hợp truy vấn theo khách, cần xem distribution |
| Tải cực lệch | Synthetic hoặc hierarchical partition key | Query routing và transaction boundaries phức tạp |

**Không có partition key tối ưu cho mọi hệ thống.** Phải xét dữ liệu, peak load, query và transaction boundaries trước khi tạo container.

## 6. RU, throughput và vì sao phải quan tâm ngay từ đầu

Cosmos DB tính request charge dưới dạng **Request Units**. Mức charge phụ thuộc operation, dữ liệu, indexing, query, kích thước payload và nhiều đặc tính khác.

Ví dụ giả định:

| Operation | RU đo được trong ví dụ |
|---|---:|
| Point read item nhỏ | 1 |
| Create item | 5 |
| Query trong logical partition | 12 |
| Cross-partition query | 80 |

**Đây chỉ là số minh họa**, không phải bảng giá/charge cố định của Cosmos DB. Cần đo trên workload thật.

Nếu container có 1.000 RU/s và request bình quân 5 RU thì giới hạn lý tưởng theo RU vào khoảng 200 requests/giây, chưa xét burst, hot partitions và các bottleneck khác:

\[
\text{requests/second} \approx \frac{\text{available RU/s}}{\text{average RU/request}}
\]

### 6.1. Các mô hình capacity

- **Manual provisioned throughput:** cấu hình lượng RU/s tương đối ổn định.
- **Autoscale provisioned throughput:** điều chỉnh trong giới hạn được thiết lập và điều kiện hỗ trợ.
- **Serverless:** tính theo usage trong phạm vi tính năng/giới hạn của mode.

Autoscale/serverless **không bảo đảm không bao giờ có HTTP 429**. Một logical partition nóng vẫn có thể gặp giới hạn khi tổng RU/s có vẻ còn dư.

### 6.2. Database-level và container-level throughput

Một số cấu hình cho phép nhiều containers chia sẻ throughput ở database scope; trường hợp khác provision riêng container. Nếu workload share RU budget, job batch của một container có thể ảnh hưởng ứng dụng khác.

### 6.3. Repository abstraction không xóa request charge

**findAll()**, derived queries hoặc paging vẫn tiêu thụ RU và có thể fan-out sang partitions. Chọn query phù hợp quan trọng hơn chuyện dòng Java ngắn.

## 7. Chuẩn bị môi trường thực hành

Điều kiện giả định:

- JDK 17+ theo Spring Boot/SDK version được chọn.
- Maven hoặc Gradle theo chuẩn của dự án.
- Spring Boot release và Spring Cloud Azure release **tương thích chính thức với nhau**.
- Azure subscription/resource group lab, quota và budget.
- Azure Cosmos DB **for NoSQL** account và database **shopdb**.
- Container **orders** với partition key path **/tenantId**.
- Azure identity/data-plane role hoặc key lab được phép.
- Network route từ Java runtime tới Cosmos endpoint.

### 7.1. Không tự tạo resource production trong startup

Database/container, indexing và throughput nên được quản lý bằng IaC/approval trong production. Không thiết kế một Java service tự tăng RU/s hoặc tạo lại containers khi được scale thêm Pod.

### 7.2. Giữ một đường đi được kiểm chứng

Ví dụ học tập sẽ dùng **Spring Cloud Azure Starter Data Cosmos**, không trộn ngẫu nhiên với một thư viện Cosmos Spring Data legacy đã ngừng phù hợp. Kiểm tra compatibility matrix giữa **Spring Boot**, **Spring Cloud Azure** và Azure SDK trước khi dùng.

### 7.3. Quyền và networking là hai việc riêng

Ứng dụng có data-plane role phù hợp nhưng private DNS sai vẫn không kết nối được. Ngược lại, resolve endpoint đúng chưa bảo đảm user/managed identity có quyền đọc container.

## 8. Dependencies Maven: Spring Cloud Azure Starter Data Cosmos

Một mẫu **pom.xml fragment**:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure.spring</groupId>
      <artifactId>spring-cloud-azure-dependencies</artifactId>
      <version>VERSION_COMPATIBLE_WITH_SPRING_BOOT</version>
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
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-data-cosmos</artifactId>
  </dependency>
</dependencies>
~~~

**VERSION_COMPATIBLE_WITH_SPRING_BOOT** là placeholder bắt buộc phải thay bằng BOM tương thích, được nhóm dự án phê duyệt. Version Spring Boot, Spring Data, Spring Cloud Azure và Cosmos SDK thay đổi theo thời gian; bài học không khẳng định một con số cố định phù hợp mọi dự án.

### 8.1. Vì sao dùng BOM?

BOM giúp quản lý những phiên bản Azure libraries tương thích với nhau, giảm nguy cơ trộn **azure-core**, **azure-cosmos** và starter khác thế hệ.

### 8.2. Có cần thêm azure-cosmos trực tiếp?

Starter thường kéo các thư viện nền cần thiết. Nếu bạn gọi **CosmosClient** trực tiếp hoặc sử dụng tính năng SDK bổ sung, kiểm tra dependency tree và thêm dependency tường minh chỉ khi cần, theo BOM. Không gắn một phiên bản azure-cosmos ngẫu nhiên làm hỏng compatibility.

### 8.3. Java/Spring Boot compatibility

Spring Boot 3.x thông thường yêu cầu Java 17+, nhưng Spring Boot phiên bản khác có requirements khác. Khi chọn release, xác minh Java baseline, migration notes và dependency security policy của dự án.

## 9. Cấu hình Spring Boot application

Cấu hình property thường dùng cho **Spring Cloud Azure Cosmos integration**:

~~~properties
spring.application.name=orders-api
spring.cloud.azure.cosmos.endpoint=https://YOUR_ACCOUNT.documents.azure.com:443/
spring.cloud.azure.cosmos.database=shopdb
~~~

Thay endpoint/account/database bằng resource lab thực. Trong cloud không nên đặt API key vào file properties được commit.

### 9.1. Cấu hình qua environment

Spring Boot hỗ trợ relaxed binding; các environment variables tương ứng thường có dạng:

~~~text
SPRING_CLOUD_AZURE_COSMOS_ENDPOINT
SPRING_CLOUD_AZURE_COSMOS_DATABASE
~~~

Với môi trường lab chỉ cho phép key-based auth, có thể inject secret vào property **spring.cloud.azure.cosmos.key** qua cấu hình bí mật hoặc environment variable tương ứng:

~~~text
SPRING_CLOUD_AZURE_COSMOS_KEY
~~~

**Không commit secret thật**, không đặt vào README, container image hoặc Dockerfile.

### 9.2. Identity-based auth

Trong môi trường Azure đã hỗ trợ Entra-based authentication, cần chọn cấu hình TokenCredential/managed identity phù hợp với phiên bản starter, và **không đưa key vào cấu hình production**. Với một số phiên bản có nhiều credential routes, cấu hình cụ thể có thể khác; xác minh hướng dẫn của phiên bản sử dụng.

### 9.3. Cấu hình sai thường bị hiểu nhầm thành lỗi database

- Endpoint của Cosmos DB phải là **account endpoint đúng**, không phải Azure Portal URL.
- Database name phải khớp resource đã tạo.
- Role data-plane cần đúng identity.
- Cần DNS/TLS/firewall kết nối từ runtime.
- Starter version phải hợp Spring Boot release.

### 9.4. Đừng trộn các API configuration families

Properties từ một Spring Cloud Azure generation hoặc SDK configuration legacy có thể không áp dụng cho starter hiện tại. Kiểm tra auto-configuration bindings thực thay vì copy hai bộ cấu hình chồng nhau.

## 10. Dữ liệu mẫu và ánh xạ Entity

Mô hình entity được lưu vào container **orders**:

~~~java
package example.orders.data;

import com.azure.spring.data.cosmos.core.mapping.Container;
import com.azure.spring.data.cosmos.core.mapping.PartitionKey;
import org.springframework.data.annotation.Id;

@Container(containerName = "orders")
public class OrderDocument {

    @Id
    private String id;

    @PartitionKey
    private String tenantId;

    private String customerId;
    private String status;
    private long amountMinor;
    private String updatedAtUtc;
    private int schemaVersion;

    public OrderDocument() { }

    public OrderDocument(
            String id, String tenantId, String customerId,
            String status, long amountMinor, String updatedAtUtc) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.status = status;
        this.amountMinor = amountMinor;
        this.updatedAtUtc = updatedAtUtc;
        this.schemaVersion = 1;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getStatus() { return status; }
    public void setStatus(String status) {
        this.status = status;
    }

    public long getAmountMinor() { return amountMinor; }
    public void setAmountMinor(long amountMinor) {
        this.amountMinor = amountMinor;
    }

    public String getUpdatedAtUtc() { return updatedAtUtc; }
    public void setUpdatedAtUtc(String updatedAtUtc) {
        this.updatedAtUtc = updatedAtUtc;
    }

    public int getSchemaVersion() { return schemaVersion; }
    public void setSchemaVersion(int schemaVersion) {
        this.schemaVersion = schemaVersion;
    }
}
~~~

### 10.1. @Container

**@Container(containerName = "orders")** liên kết entity với Cosmos container. Phải tạo container đúng tên và partition key theo thiết kế trước khi chạy production.

### 10.2. @Id

**@Id** ánh xạ identifier. Trong partitioned container, cặp **id + partition key value** mới là thông tin đầy đủ cho point operation; chỉ id có thể không đủ.

### 10.3. @PartitionKey

**@PartitionKey** trên **tenantId** phải phù hợp container partition key path **/tenantId**. Không nhầm giữa tên field, JSON serialization name và path của container.

### 10.4. Thời gian và tiền

Ví dụ dùng **amountMinor** là đơn vị tiền nhỏ nhất do ứng dụng quy định, tránh sai số floating-point. **updatedAtUtc** dùng string ISO-8601 để ví dụ dễ quan sát; production có thể dùng Instant/OffsetDateTime với serialization mapping đã kiểm chứng.

### 10.5. Constructors, getters và schema evolution

Spring Data mapping cần có cách khởi tạo/deserialization hợp lệ theo version/framework. No-args constructor và getters/setters giúp ví dụ rõ ràng; dữ liệu thật cần validation, schema version, migration và xử lý các field cũ có thể thiếu.

## 11. Định nghĩa CosmosRepository

Một repository đơn giản:

~~~java
package example.orders.data;

import com.azure.spring.data.cosmos.repository.CosmosRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface OrderRepository
        extends CosmosRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantId(String tenantId);

    List<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status);

    List<OrderDocument> findByCustomerIdAndTenantId(
        String customerId, String tenantId);
}
~~~

### 11.1. Điều Spring Data làm giúp

- Mapping Java entity và JSON item.
- Cung cấp CRUD/repository abstractions.
- Derived query methods theo conventions của Spring Data Cosmos.
- Dùng các client/configuration trong Spring context.
- Kết hợp dependency injection và unit testing.

### 11.2. Không biến findById thành phương pháp hoàn hảo cho mọi partition

Một repository method nhận **id** nhưng không nhận partition key có thể không tương đương với một **point read có id + tenantId** ở tất cả implementation/cấu hình. Muốn tối ưu RU và authorization, cần đo query plan/charge hoặc dùng Cosmos SDK trực tiếp khi cần point operation chính xác.

### 11.3. Repository method không làm nhiệm vụ authorization

**findByTenantId("shop-42")** chỉ là truy vấn dữ liệu. Backend phải xác minh caller được quyền với shop-42 trước khi gọi method.

### 11.4. Đừng dùng findAll() trong HTTP request thông thường

Với container hàng triệu items, **findAll()** có thể truy vấn rộng, tiêu tốn RU, mạng và heap; ứng dụng phải dùng filters/pagination và quotas phù hợp.

## 12. Derived queries và truy vấn có tham số

Một số trường hợp truy vấn phức tạp hơn có thể dùng annotation **@Query** của Spring Data Cosmos. Ví dụ theo contract SQL-style của Cosmos DB for NoSQL:

~~~java
package example.orders.data;

import com.azure.spring.data.cosmos.repository.CosmosRepository;
import com.azure.spring.data.cosmos.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface OrderQueryRepository
        extends CosmosRepository<OrderDocument, String> {

    @Query("SELECT * FROM c WHERE c.tenantId = @tenantId "
         + "AND c.status = @status")
    List<OrderDocument> findByTenantStatusQuery(
        @Param("tenantId") String tenantId,
        @Param("status") String status);
}
~~~

**Lưu ý:** cú pháp cụ thể của custom queries và parameter binding phụ thuộc version Spring Data Cosmos. Phải chạy integration test với starter mà dự án sử dụng trước production.

### 12.1. Derived query có thể ngầm tạo SQL query

Tên **findByTenantIdAndStatus** dễ đọc nhưng không bảo đảm mọi hình thức truy vấn đều là point read. Khi có nhiều records, method trả List có thể tải nhiều dữ liệu vào memory; nên giới hạn kết quả ở mức API.

### 12.2. Query partition-scoped khác cross-partition query

Nếu query biết tenantId, thiết kế có thể hạn chế phân vùng truy vấn. Nếu filter chỉ theo status và status xuất hiện ở nhiều tenants, query có thể fan-out, tốn RU hơn.

### 12.3. Custom query vẫn cần indexing policy

Tạo @Query không tạo indexes chính xác cho mọi access pattern. Cần xác định fields WHERE/ORDER BY, dự toán request charge và cấu hình index khi thích hợp.

### 12.4. SQL injection và identifiers

Không nối user input thẳng vào query string. Dùng parameter binding theo SDK/repository API. Nếu query động buộc phải chọn tên trường hoặc container, chỉ lấy identifiers từ allowlist backend.

## 13. Tách REST controller, service và repository

Một cấu trúc gợi ý:

~~~text
example.orders
  OrdersApplication.java
  api/
    OrderController.java
    CreateOrderRequest.java
    OrderResponse.java
  service/
    OrderService.java
    TenantAuthorization.java
  data/
    OrderDocument.java
    OrderRepository.java
  config/
    CosmosConfiguration.java
  monitoring/
    CosmosMetrics.java
~~~

### 13.1. Service chịu business rules

Repository chỉ thực hiện data operations. Service phải:

- Lấy **trusted tenant** từ authenticated principal/context.
- Validate fields của request.
- Đặt server-side idempotency/business operation ID.
- Chọn đúng cách lưu.
- Kiểm tra quyền trước query/update/delete.
- Chuyển Cosmos errors thành domain errors.

### 13.2. DTO khác entity

Đừng nhận raw **OrderDocument** từ user rồi lưu nguyên bản: user có thể tự gửi tenantId khác, trạng thái đã hoàn tất, schemaVersion hoặc id của người khác. DTO nên chỉ có các fields caller thực được phép nhập.

~~~java
package example.orders.api;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
    @NotBlank String customerId,
    @Min(1) long amountMinor
) {}
~~~

### 13.3. Lấy tenant từ identity, không từ body

Nếu một user gửi request body chứa "tenantId": "admin-tenant", controller không nên tin nó. Tenant must be derived from verified claims/session và authorization policy theo ứng dụng.

## 14. OrderService: ghi dữ liệu và truy vấn theo tenant

Ví dụ service cho yêu cầu tạo đơn hàng và xem danh sách theo tenant:

~~~java
package example.orders.service;

import example.orders.api.CreateOrderRequest;
import example.orders.data.OrderDocument;
import example.orders.data.OrderRepository;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
public final class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderDocument create(
            String authorizedTenant,
            CreateOrderRequest request) {

        if (authorizedTenant == null
                || authorizedTenant.isBlank()) {
            throw new IllegalArgumentException("Tenant required");
        }
        if (request.amountMinor() <= 0) {
            throw new IllegalArgumentException("Invalid amount");
        }

        OrderDocument item = new OrderDocument(
            UUID.randomUUID().toString(),
            authorizedTenant,
            request.customerId(),
            "CREATED",
            request.amountMinor(),
            Instant.now().toString()
        );

        return repository.save(item);
    }

    public List<OrderDocument> listByTenant(
            String authorizedTenant) {
        return repository.findByTenantId(authorizedTenant);
    }
}
~~~

**Chỉ minh họa data access.** Caller của service có trách nhiệm xác minh tenant và quyền; production còn cần số lượng items tối đa, pagination, idempotency và error mapping.

### 14.1. Cẩn thận với UUID.randomUUID() khi retry POST

Nếu request đầu đã ghi thành công nhưng response mất, caller retry và service sinh UUID mới sẽ tạo **hai đơn hàng**. Cần **idempotency key** từ request, bảng marker hoặc operation ID ổn định, và chính sách phát hiện duplicate.

### 14.2. save không phải giao dịch nghiệp vụ

Repository.save có thể tạo/cập nhật document theo semantics của thư viện. Nó không có nghĩa toàn workflow thanh toán, gửi email và publish Service Bus đã atomic.

### 14.3. Không dùng status do user tự chỉ định

Ứng dụng tự đặt trạng thái CREATED. Khi chuyển sang PAID/SHIPPED cần business validation và optimistic concurrency, không cho client upsert tùy ý.

### 14.4. List không nên trả vô hạn

Ví dụ trả List để giới thiệu code. HTTP API production phải dùng filter, paging/continuation, số lượng tối đa và request deadline; load tất cả orders của một tenant rất lớn dễ gây memory/RU exhaustion.

## 15. REST controller và HTTP error contract

Ví dụ controller skeleton:

~~~java
package example.orders.api;

import example.orders.data.OrderDocument;
import example.orders.service.OrderService;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService service;
    private final TenantAuthorization tenantAuth;

    public OrderController(
            OrderService service,
            TenantAuthorization tenantAuth) {
        this.service = service;
        this.tenantAuth = tenantAuth;
    }

    @PostMapping
    public ResponseEntity<OrderDocument> create(
            @Valid @RequestBody CreateOrderRequest request) {
        String tenant = tenantAuth.requireAuthorizedTenant();
        OrderDocument item = service.create(tenant, request);
        return ResponseEntity.status(201).body(item);
    }

    @GetMapping
    public ResponseEntity<List<OrderDocument>> list() {
        String tenant = tenantAuth.requireAuthorizedTenant();
        return ResponseEntity.ok(
            service.listByTenant(tenant));
    }
}
~~~

**TenantAuthorization là interface/service của ứng dụng, không phải class có sẵn trong Spring Cloud Azure.** Ví dụ chưa định nghĩa implementation; cần triển khai bằng Spring Security và chính sách tenant đã được xác minh. Sử dụng DTO response thay vì trả thẳng entity có fields nội bộ trong production.

### 15.1. HTTP mapping gợi ý

| Trường hợp | API response |
|---|---|
| Request không hợp lệ | 400 Bad Request |
| Chưa xác thực | 401 Unauthorized |
| Không có quyền tenant/document | 403 Forbidden hoặc 404 không tiết lộ tồn tại theo policy |
| Item không tồn tại | 404 Not Found |
| Duplicate business request | 409 Conflict hoặc trả kết quả idempotent |
| ETag/precondition conflict | 409/412 theo API contract |
| Cosmos DB throttling/timeout | 429/503 hoặc response quá tải có Retry-After theo contract |
| Lỗi dependency khác | 5xx có correlation ID và telemetry |

### 15.2. Không expose Cosmos exception nguyên bản

Raw exception có thể chứa endpoint, metadata, SQL query hoặc thông tin nhạy cảm. Dùng @RestControllerAdvice và logs được redact để chuyển lỗi sang response có mã rõ ràng.

### 15.3. Controller chưa có authentication là chưa đủ an toàn

Đoạn skeleton phụ thuộc TenantAuthorization để minh họa. Trong production, bắt buộc Spring Security kiểm tra JWT/OIDC, mapping principal tới tenant và object-level access controls.
## 16. Query repository và point read không phải một việc

Trong Cosmos DB for NoSQL, thao tác thường hiệu quả nhất để đọc một item đã biết là **point read** với:

- **id** chính xác;
- **partition key value** chính xác.

Ví dụ người dùng yêu cầu ORD-1001 của shop-42:

~~~text
id = ORD-1001
partitionKeyValue = shop-42
~~~

Một repository method như **findByTenantIdAndStatus** là **query** theo fields, có thể duyệt nhiều items. Một **findById(id)** không phải lúc nào cũng truyền được partition key value độc lập trong contract repository mà ứng dụng đang dùng; không tự suy rằng nó luôn hoạt động như point read.

### 16.1. Khi nào query là đúng?

- Tìm nhiều đơn hàng theo trạng thái.
- Xem lịch sử đơn hàng của khách.
- Lấy danh sách có phân trang.
- Tìm theo nhiều điều kiện được index.

### 16.2. Khi nào point read tốt hơn?

- Xem chi tiết một đơn hàng đã biết id và tenant.
- Đọc trạng thái của một workflow object.
- Kiểm tra idempotency marker.
- Cập nhật một document với ETag.

### 16.3. Dùng Spring Data Cosmos hay Cosmos SDK trực tiếp?

| Nhu cầu | Công cụ |
|---|---|
| CRUD và query methods thường gặp | CosmosRepository |
| Reactive query/service | ReactiveCosmosRepository |
| Point read chính xác kèm partition key | Cosmos DB Java SDK v4 hoặc template API đã xác minh |
| Diagnostics/RU/ETag/request options chi tiết | SDK v4 thường minh bạch hơn |
| Transactional batch trong cùng partition | Cosmos SDK transactional batch |
| Dựng aggregation/reporting phức tạp | Thiết kế query/sink phù hợp, không chỉ repository |

Không phải mọi ứng dụng đều cần dùng trực tiếp SDK, nhưng **hợp lý khi kết hợp repository với SDK adapter** cho những thao tác cần kiểm soát partition hoặc response metadata rõ.

## 17. Cosmos SDK v4: point read có tenantId và request charge

Một adapter dùng SDK v4 cho point read:

~~~java
package example.orders.data;

import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;
import com.azure.identity.DefaultAzureCredentialBuilder;

public final class OrderPointReader {
    private final CosmosContainer container;

    public OrderPointReader(CosmosClient client) {
        this.container = client
            .getDatabase("shopdb")
            .getContainer("orders");
    }

    public OrderDocument read(String orderId, String authorizedTenant) {
        CosmosItemResponse<OrderDocument> response =
            container.readItem(
                orderId,
                new PartitionKey(authorizedTenant),
                OrderDocument.class);

        double ru = response.getRequestCharge();
        System.out.println("Point read RU=" + ru);
        return response.getItem();
    }

    public static CosmosClient newClient(String endpoint) {
        return new CosmosClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }
}
~~~

### 17.1. Điều kiện của mẫu

- Java Cosmos SDK v4 và Azure Identity versions phù hợp.
- Cosmos account for NoSQL cho phép Microsoft Entra authentication theo cấu hình.
- Principal có **Cosmos DB data-plane role** cho thao tác đọc.
- Database **shopdb**, container **orders** đã tồn tại.
- Partition key path là **/tenantId**.
- Endpoint do cấu hình đáng tin cung cấp.

### 17.2. Không tạo CosmosClient mỗi HTTP request

**newClient** chỉ minh họa construction, phải được gọi một lần ở startup/DI bean và được **close khi ứng dụng tắt**. Tạo client cho mỗi request gây connection churn, tăng resources và latency.

### 17.3. Request charge đo RU của thao tác

**response.getRequestCharge()** giúp đo chi phí thật của point read. Hãy so sánh với repository/query trên cùng dữ liệu để xem access pattern nào phù hợp. Tránh in per-request logs quá nhiều trong production; dùng metrics/structured telemetry có sampling.

### 17.4. Bảo đảm tenant đã được xác thực

Tham số **authorizedTenant** phải đến từ authorization layer, không lấy trực tiếp từ query parameter HTTP. Biết partition key không tự cấp quyền cho người dùng cuối.

## 18. Reactive Spring Data Cosmos Repository

Nếu ứng dụng đang dùng Reactor và Spring WebFlux, Spring Data Cosmos có repository reactive theo phiên bản được hỗ trợ.

~~~java
package example.orders.data;

import com.azure.spring.data.cosmos.repository.ReactiveCosmosRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveCosmosRepository<OrderDocument, String> {

    Flux<OrderDocument> findByTenantId(String tenantId);

    Flux<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status);
}
~~~

### 18.1. Mono và Flux

- **Mono<T>**: 0 hoặc 1 kết quả, complete hoặc error.
- **Flux<T>**: 0 đến nhiều kết quả, complete hoặc error.
- **Publisher** thường chỉ được thực hiện khi subscribe, tùy semantics của reactive driver.

### 18.2. Không bật cả sync và reactive repositories một cách tình cờ

Bài đưa ra hai lựa chọn kiến trúc, **không yêu cầu chạy đồng thời hai repository interfaces trên cùng entity package** trong một app. Nếu dùng cả hai, phải cấu hình repository scanning/bean names và dependency lifecycle phù hợp với phiên bản framework.

### 18.3. Reactive không tự giảm RU

Một reactive query cùng dữ liệu/index vẫn tiêu thụ RU theo Cosmos DB. Nó thay đổi cách Java quản lý I/O và concurrency, không làm service có throughput vô hạn.

### 18.4. Lazy execution

Trong reactive pipeline, chỉ tạo Mono/Flux mà không subscribe hoặc không trả publisher cho framework thì operation có thể không chạy. Không gọi subscribe() rồi ngay lập tức trả HTTP success vì errors có thể thất lạc.

## 19. WebFlux controller: trả Flux cho framework

Giả sử application đã cấu hình WebFlux, authz và ReactiveOrderRepository:

~~~java
package example.orders.api;

import example.orders.data.OrderDocument;
import example.orders.data.ReactiveOrderRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/reactive/orders")
public class ReactiveOrderController {
    private final ReactiveOrderRepository repository;
    private final TenantAuthorization tenantAuth;

    public ReactiveOrderController(
            ReactiveOrderRepository repository,
            TenantAuthorization tenantAuth) {
        this.repository = repository;
        this.tenantAuth = tenantAuth;
    }

    @GetMapping
    public Flux<OrderDocument> list() {
        String tenant = tenantAuth.requireAuthorizedTenant();
        return repository.findByTenantId(tenant)
            .take(100);
    }
}
~~~

**TenantAuthorization** vẫn là service của ứng dụng, cần triển khai theo Spring Security. Trong reactive environment chuẩn, authentication context có thể được lưu trong Reactor Context, không chắc truy cập bằng ThreadLocal ở mọi scheduler; phiên bản production phải lấy principal theo cách reactive an toàn.

### 19.1. Vì sao không block()?

WebFlux event-loop phải phục vụ nhiều requests. **Mono.block()/Flux.blockLast()** trên event-loop có thể giữ thread trong lúc đợi network I/O, tạo starvation. Trả Publisher để framework subscribe.

### 19.2. take(100) không phải SQL LIMIT tuyệt đối

Operator **take(100)** dừng phát thêm kết quả downstream; tùy driver/query paging, backend có thể đã truy xuất pages lớn hơn. Với query có tải cao, dùng pagination/limit của repository/query API được hỗ trợ và đo request charge thực.

### 19.3. Backpressure không phải rate limit Cosmos DB

Reactor demand giúp điều phối dữ liệu trong pipeline, nhưng query paging, retries và request serialization phụ thuộc driver. Cần concurrency/rate limiting khi database RU/s là bottleneck.

### 19.4. Reactive error propagation

Nếu một subscription gặp CosmosException hoặc Spring DataAccessException, Flux có thể kết thúc bằng error. Controller/service cần mapping lỗi phù hợp, không tự onErrorResume thành Flux.empty rồi báo thành công khi thật ra database đang lỗi.

## 20. Spring MVC hay Spring WebFlux?

| Khía cạnh | MVC + CosmosRepository | WebFlux + ReactiveCosmosRepository |
|---|---|---|
| Lập trình | Imperative, blocking-style | Reactive Publisher |
| Thread | Worker thread chờ call | Nonblocking pipeline khi toàn bộ dependencies phù hợp |
| Query nhiều items | List/Iterable/Page tùy API | Flux |
| Debug | Stack trace truyền thống | Reactive chain/context phức tạp hơn |
| Backpressure | Executor/queue/rate limiter | Reactor operators + capacity control |
| Đồng thời | Bounded threads hoặc virtual threads | Bounded reactive concurrency |
| Truy cập JDBC sync cùng pipeline | Tương đối tự nhiên | Có thể block event-loop nếu dùng sai |
| RU/request | Do Cosmos DB tính | Không tự giảm nhờ async |

### 20.1. Khi MVC đủ tốt

Số requests vừa phải, vài database operations mỗi request, đội có kinh nghiệm imperative và latency đạt SLO. Không chuyển toàn ứng dụng sang reactive chỉ vì cơ sở dữ liệu là NoSQL.

### 20.2. Khi WebFlux đáng cân nhắc

Rất nhiều I/O-bound concurrent operations, pipeline hiện có đã reactive, muốn stream data và giảm platform threads. Cần có kỷ luật debugging, cancellation, context propagation và load testing.

### 20.3. Spring Boot và Java virtual threads

Với Java 21 và runtime hỗ trợ, virtual threads có thể giúp giữ code blocking-style nhưng giảm chi phí chờ I/O ở một số workloads. Virtual threads **không tạo RU/s mới** và không xóa rủi ro hot partition; benchmark trước khi chọn.

## 21. Pagination: không trả tất cả documents

Với tenant có 2 triệu orders, trả một **List<OrderDocument>** từ repository cho mỗi request là nguy hiểm:

- Quá nhiều RU/query.
- Nhiều pages/round trips.
- Java heap tăng.
- p99 latency cao.
- HTTP response có thể vượt giới hạn của client/proxy.
- Throttling khiến retries kéo dài.

### 21.1. Phân trang với Spring Data

Các repository có thể hỗ trợ **Pageable**, Page/Slice hoặc cơ chế paging khác theo version và API; Cosmos DB có **continuation token** ở tầng SDK. Hãy chọn kiểu API phù hợp và xác minh cách ánh xạ pages/tokens trong version Spring Data Cosmos.

Không giả định SQL OFFSET/LIMIT có hiệu năng giống relational database; với dữ liệu lớn cần cân nhắc **continuation token**, ordering/indexing và read consistency.

### 21.2. Limit ổn định và index phù hợp

Nếu dùng API hiển thị 20 orders mới nhất, xác định sort key/version, maximum page size, tenant partition và indexing/composite indexes hỗ trợ truy vấn.

### 21.3. Rủi ro paging trong dữ liệu đang thay đổi

Giữa hai pages, dữ liệu có thể được insert/update/delete. Cần contract về cursor/consistency và tránh coi việc cộng trang là một snapshot hoàn toàn bất biến nếu dịch vụ không bảo đảm như vậy.

### 21.4. Đếm RU của mọi pages

Một query trả nhiều pages sẽ có tổng request charge là tổng charge của các pages thực được đọc. Đừng chỉ nhìn trang đầu rồi kết luận query rẻ.

## 22. Indexing policy và query performance

Cosmos DB for NoSQL indexing hỗ trợ tìm dữ liệu nhanh nhưng cũng tạo resource overhead cho writes.

### 22.1. Mapping entity không tự tối ưu index

Một Java field **status** có thể được query thường xuyên, nhưng index policy của container phải phù hợp access pattern. Có trường hợp nên điều chỉnh included/excluded paths hoặc composite indexes cho ORDER BY/multiple filters.

### 22.2. Các yếu tố ảnh hưởng RU

- Document size.
- Query predicates, projections, aggregation.
- Cross-partition fan-out.
- Indexing policy và data distribution.
- Số items trả về.
- Write frequency và số fields được index.

### 22.3. Đừng SELECT * vô cớ

Nếu UI chỉ cần orderId/status/amount, cân nhắc projection/DTO thay vì tải toàn document với fields lớn. Các projections và mapping về DTO phải được xác minh với thư viện sử dụng.

### 22.4. Tối ưu có hệ thống

1. Đo RU/request và latency baseline.
2. Phân nhóm operations theo endpoint/query type.
3. Xem indexing và query patterns.
4. Thử point read/partition-scoped query.
5. Kiểm tra correctness và data validation.
6. Benchmark lại p95/p99, RU/operation và successful throughput.

## 23. Throttling HTTP 429 và RU/s trong Spring Boot

Khi workload đòi nhiều RU hơn capacity đang có ở phạm vi liên quan, Cosmos DB có thể trả **HTTP 429 Too Many Requests**.

~~~mermaid
sequenceDiagram
    participant U as HTTP Client
    participant S as Spring Boot
    participant R as Spring Data Cosmos / SDK
    participant C as Cosmos DB
    U->>S: GET /api/orders
    S->>R: Repository query
    R->>C: Query request
    C-->>R: HTTP 429 + retry-after
    Note over R: SDK may retry within budget
    R->>C: Retry after delay
    C-->>R: Success + RU charge
    R-->>S: Data
    S-->>U: HTTP 200
~~~

### 23.1. 429 có thể bị SDK retry nội bộ

Một lời gọi repository cuối cùng thành công vẫn có thể đã gặp 429 ở tầng SDK, làm tăng latency. Chỉ đo final API status 200 không đủ để phát hiện RU contention.

### 23.2. 429 không luôn có nghĩa tăng tổng RU/s là đủ

Một tenant có traffic quá lớn trên cùng partition key có thể tạo **hot logical partition**; tổng container RU/s có vẻ còn nhưng physical partition liên quan đạt giới hạn. Phải xem normalized RU utilization/partition metrics khi khả dụng.

### 23.3. Không retry 400/401/403/404/409/412 như lỗi throttling

- **400:** request/schema/query sai.
- **401/403:** authentication/authorization hoặc policy.
- **404:** item/resource không tìm thấy theo request.
- **409:** conflict/duplicate.
- **412:** ETag/precondition mismatch.
- **429:** capacity/throttling.
- **503/timeout:** service/network transient theo tình huống.

Phân loại đúng trước khi retry hoặc chuyển thành HTTP response.

## 24. Retry policy: SDK, Spring và API gateway

Có thể có nhiều tầng retry:

~~~text
HTTP client retry
    x
Spring service retry
    x
Cosmos SDK retry
    x
Background job replay
    =
Nhiều attempts hơn dự kiến
~~~

### 24.1. Tôn trọng Retry-After

Cosmos service có thể đưa gợi ý retry delay; SDK đã có retry policy cho throttling. Nếu cần thêm outer retry ở Spring layer, phải bảo đảm:

- Chỉ retry lỗi đúng loại và còn thời gian.
- **Max attempts** hữu hạn.
- **Total deadline** và backoff có jitter.
- Không tạo unbounded queue/thread.sleep hàng nghìn requests.
- Write có idempotency.
- Có metrics attempts và final errors.

### 24.2. Không bật @Retryable một cách vô thức

Spring Retry/Resilience4j có thể hữu ích khi được cấu hình đúng, nhưng một annotation retry chung trên repository operations có thể chồng với SDK retry. Thiết kế policy theo operation type và status, tránh retry conflict hoặc auth failure.

### 24.3. HTTP response cho caller

Nếu sau retry budget vẫn thiếu capacity, API có thể trả 429/503 theo contract và cung cấp hướng dẫn chờ phù hợp; không giữ HTTP request mãi. Với job nền, đưa sang queue/dead-letter hoặc status retryable thay vì mất dữ liệu.

### 24.4. Thời gian retry ảnh hưởng SLO

Một SDK call có thể thành công sau nhiều retries nhưng vượt p99 SLO của API. Đặt deadline end-to-end, theo dõi long-tail latency, không chỉ successful response count.

## 25. Kiểm soát concurrency và backpressure

Giả sử có 20 AKS Pods, mỗi Pod cho phép 50 repository operations cùng lúc:

\[
20 \times 50 = 1.000\text{ operations có thể in-flight}
\]

Nếu Cosmos DB có RU capacity thấp hơn nhu cầu của 1.000 operations, thêm concurrency chỉ tạo nhiều retries/latency, không tạo throughput tương ứng.

### 25.1. Ba cơ chế khác nhau

| Cơ chế | Bảo vệ |
|---|---|
| **Semaphore / max in-flight** | Threads, memory, connections |
| **Requests/RU rate limiter** | Capacity Cosmos DB theo thời gian |
| **Bounded queue** | Tránh quá nhiều pending work và OOM |

### 25.2. Rate limiting theo RU

Nếu đã đo một write ~8 RU và container có 1.600 RU/s dành riêng cho API, ngân sách lý tưởng có thể khoảng 200 writes/giây, chưa tính headroom và biến thiên request charge.

Các số chỉ minh họa. Khi nhiều workloads dùng cùng container, cần phân bổ ngân sách thực, tránh một job import dùng hết RU của API.

### 25.3. Reactor flatMap concurrency

Trong reactive ingest, dùng **flatMap(fn, concurrency)** có giới hạn để không subscribe vô hạn. Nhưng concurrency limit một Pod không tự giới hạn toàn cluster.

### 25.4. Bulk ingestion và batch jobs

Khi nhập dữ liệu, dùng các tính năng batch/bulk được SDK hỗ trợ và điều tiết tốc độ. Bulk không tự bảo đảm atomicity hay exactly-once cho tất cả items, cần per-item outcome và idempotent replay.

## 26. ETag và optimistic concurrency

Hai clients có thể cùng đọc một document rồi ghi đè nhau. **ETag** giúp triển khai conditional update: chỉ ghi nếu version đã đọc vẫn còn hiện hành.

~~~text
Client A đọc ORD-1001, ETag = V1
Client B đọc ORD-1001, ETag = V1
Client B ghi mới -> ETag V2
Client A ghi If-Match V1 -> HTTP 412
~~~

### 26.1. @Version trong Spring Data Cosmos

Một số phiên bản Spring Data Cosmos hỗ trợ optimistic locking qua annotation/version mapping liên quan ETag. **Cú pháp/behavior phải được xác minh theo version thực**, gồm cách serialize field và mapping ETag; không giả định một annotation chung sẽ hoạt động nếu thiếu mapping thích hợp.

### 26.2. Đường kiểm soát rõ bằng Cosmos SDK

Ví dụ conditional replace thông qua SDK:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

CosmosItemResponse<OrderDocument> current =
    container.readItem(
        "ORD-1001",
        new PartitionKey("shop-42"),
        OrderDocument.class);

OrderDocument order = current.getItem();
order.setStatus("PAID");

CosmosItemRequestOptions options =
    new CosmosItemRequestOptions();
options.setIfMatchETag(current.getETag());

container.replaceItem(
    order,
    order.getId(),
    new PartitionKey(order.getTenantId()),
    options);
~~~

Ở fragment này, **container** là CosmosContainer đã cấu hình. Khi ETag không khớp, cần đọc lại state rồi đánh giá business rule, không retry replace mù.

### 26.3. 412 khác 429

**412 Precondition Failed** là conflict do state đổi; tăng RU/s không giải quyết. **429** là capacity/throttling; phải điều tiết/retry.

### 26.4. Business idempotency vẫn cần thiết

ETag tránh lost updates, nhưng không tự ngăn workflow hoàn tiền hai lần nếu mỗi lần retry tạo một operation mới. Dùng operationId và quy tắc trạng thái nghiệp vụ.

## 27. Transaction trong Cosmos DB và @Transactional của Spring

Cosmos DB có transaction semantics trong những phạm vi được hỗ trợ, đặc biệt **transactional batch cho các items cùng logical partition**.

**Không được mặc định @Transactional của Spring biến nhiều repository.save() ở các partition khác nhau thành một transaction ACID xuyên Cosmos DB.**

### 27.1. Vì sao cùng logical partition quan trọng?

Các items cùng partition key có thể tham gia các cơ chế transaction được Cosmos DB hỗ trợ trong giới hạn service; items ở partitions khác nhau không tự nằm trong cùng transaction.

### 27.2. Transactional batch qua SDK

Một quy trình cần atomicity giữa Order và OutboxEvent có thể thiết kế cả hai documents cùng partition key, rồi dùng **CosmosBatch**/executeTransactionalBatch theo SDK v4 phù hợp. Cần kiểm tra API signature, giới hạn batch và item sizes theo version.

### 27.3. Khi có Service Bus side effect

Ghi Cosmos DB rồi publish Service Bus không tự thành một distributed transaction. Sử dụng outbox/change feed hoặc workflow có idempotency để xử lý khi DB đã commit nhưng message chưa gửi.

### 27.4. Distributed workflow cần Saga/compensation

Thanh toán liên quan Cosmos DB, Azure SQL và dịch vụ ngoài thường cần Saga, retries/idempotency và nghiệp vụ bù trừ thay vì cố kỳ vọng một @Transactional bao trùm toàn hệ thống.

## 28. Consistency levels và trải nghiệm đọc sau ghi

Cosmos DB for NoSQL có các mức consistency theo cấu hình/khả năng hỗ trợ như:

- Strong.
- Bounded Staleness.
- Session.
- Consistent Prefix.
- Eventual.

### 28.1. Session consistency và Spring Boot

Session consistency thường hợp với nhiều ứng dụng; tuy nhiên nhiều service instances hoặc requests qua clients khác nhau có thể không chia sẻ session token/context theo cách bạn mong đợi. Nếu nghiệp vụ cần read-your-writes xuyên các instances, phải kiểm tra semantics, token propagation và cách sử dụng SDK.

### 28.2. Consistency ảnh hưởng tới business behavior

Nếu đặt hàng đã thành công mà UI đọc ngay từ region/connection khác, business contract phải xác định khi nào trạng thái mới được nhìn thấy. Không thay consistency mà không kiểm thử correctness của workflow.

### 28.3. Consistency và RU/latency

Các consistency settings có đánh đổi về latency/availability/chi phí trong một số cấu hình. Benchmark production-like settings, không dùng local/staging consistency khác rồi suy ra chi phí.

## 29. Schema evolution, TTL và lifecycle

Không có relational schema cố định không có nghĩa documents không cần versioning.

### 29.1. Schema version

Dùng **schemaVersion** trong OrderDocument:

~~~json
{
  "id": "ORD-1001",
  "tenantId": "shop-42",
  "amountMinor": 125000,
  "schemaVersion": 2
}
~~~

Khi thêm field mới, controller/mapper cần xử lý những documents cũ không có field, đổi định dạng bằng migration hoặc lazy upgrade theo contract.

### 29.2. TTL

Cosmos DB có Time-to-Live cho container/items theo tính năng cấu hình. TTL phù hợp session/cache/temporary jobs, nhưng **không phải backup**. Không áp dụng TTL cho đơn hàng/tài chính khi chưa có policy về retention.

### 29.3. Thay partition key path không đơn giản

Nếu đã tạo container với **/tenantId**, việc đổi sang /customerId thường cần kế hoạch tạo container đích, copy dữ liệu, đồng bộ changes, cutover và validation. Spring Data @PartitionKey trên Java entity không tự thay partition key path của container đã tồn tại.

### 29.4. Container migrations khác Java deployment

Thay entity annotations không bảo đảm database containers, indexes hoặc throughput tự được migration an toàn. Cần IaC và migration runbook riêng.

## 30. Phát hiện và xử lý hot partition

Giả sử container có các tenants:

~~~text
shop-big   -> 75% write requests
shop-small -> 15% write requests
others     -> 10% write requests
~~~

Với **/tenantId**, shop-big có thể tạo hot logical partition dù tổng RU/s được provision khá lớn.

### 30.1. Dấu hiệu

- 429 tập trung vào một tenant/key.
- p99 của tenant lớn cao hơn những tenants khác.
- Normalized RU utilization theo physical partitions không đều khi metrics khả dụng.
- Tăng tổng throughput không cải thiện tương xứng.
- Query/write patterns của một tenant quá dày.

### 30.2. Khắc phục theo ưu tiên

1. Đo request charge, key distribution và latency.
2. Tối ưu point read, query, indexing, document size.
3. Giới hạn per-tenant rate.
4. Tách workloads/background jobs hoặc container nếu hợp lý.
5. Cân nhắc synthetic/hierarchical partition key khi mô hình/dịch vụ hỗ trợ.
6. Lập kế hoạch migration nếu thật sự cần đổi partition key.

### 30.3. Đánh đổi của synthetic key

Một tenant được chia ra nhiều buckets có thể giảm hotspot, nhưng query toàn tenant có thể trở thành fan-out; transaction trong cùng logical partition cũng khó hơn. Không sửa partition key chỉ để thấy charts phân phối đều mà quên business access patterns.
## 31. Microsoft Entra data-plane RBAC và managed identity

Trong production, **managed identity** giúp ứng dụng gọi Cosmos DB mà không cần lưu account key dài hạn trong ứng dụng, khi API/SDK và cấu hình resource hỗ trợ.

### 31.1. Phân biệt ba lớp quyền

| Lớp | Phạm vi | Thay thế nhau được không? |
|---|---|---|
| **Azure management RBAC** | Quản trị Cosmos account/resource | Không tự cho phép query dữ liệu |
| **Cosmos DB for NoSQL data-plane RBAC** | Query/read/write items ở scope cấp phép | Không kiểm soát user HTTP cụ thể |
| **Spring Security / business authorization** | User/tenant/document được phép sử dụng | Không thay data-plane role của workload |

Hai data roles tích hợp thường dùng là **Cosmos DB Built-in Data Reader** và **Cosmos DB Built-in Data Contributor**. Xác minh scope/action của role ở resource thực; không cấp account Owner chỉ để chữa lỗi 403.

### 31.2. Managed identity của service không phải quyền của mọi người dùng

Nếu Java app identity có thể đọc container, Cosmos DB xác thực service principal của app. Spring Security vẫn phải kiểm tra user HTTP có quyền với shop-42 trước khi truy vấn đơn hàng shop-42.

### 31.3. Môi trường chạy

- **App Service:** system-assigned/user-assigned managed identity, VNet integration khi cần.
- **AKS:** Microsoft Entra Workload ID hoặc identity mechanism được phê duyệt.
- **Azure Functions:** managed identity, plan/network settings phù hợp.
- **Local:** Azure CLI/IDE developer identity với test account và role scope riêng.

### 31.4. Debug HTTP 403

Kiểm tra principal ID, tenant, token audience, Cosmos data role, scope, thời gian role propagation và firewall/network policy. Endpoint resolve đúng không đồng nghĩa có quyền data-plane.

## 32. Key Vault, configuration và quản lý secrets

Với Cosmos DB hỗ trợ identity-based data access, **managed identity trực tiếp** thường giảm nhu cầu lưu account key. Nếu phải dùng key do ràng buộc môi trường, bảo vệ bằng secret store/Key Vault và rotation.

### 32.1. Các thực hành bắt buộc

- Không commit **spring.cloud.azure.cosmos.key** hoặc connection string có key.
- Không in key trong application logs, exceptions, actuator env hoặc metrics tags.
- Tách credentials và Cosmos resources giữa dev/test/prod.
- Chỉ cho identities cần thiết được lấy secrets.
- Có chính sách rotate/revoke secrets và kiểm thử sau rotation.

### 32.2. Spring Boot configuration

Sử dụng environment/secret injection/App Configuration/Key Vault integration được phê duyệt theo phiên bản. Kiểm tra actual property binding và identity được starter sử dụng; không trộn cấu hình legacy khi thấy 401/403.

### 32.3. Spring Actuator có thể lộ cấu hình

Giới hạn endpoints như env, configprops, beans, heapdump và mappings bằng authorization và network policy. Ngay cả khi giá trị được mask, các metadata vận hành vẫn cần bảo vệ.

### 32.4. Không log toàn body Cosmos error

Error body có thể chứa endpoint/query metadata; dùng sanitized error code, status, activity ID và correlation ID thay vì copy toàn bộ exception vào logs công khai.

## 33. Private Endpoint, VNet và kết nối

~~~mermaid
flowchart LR
    APP[Spring Boot on AKS / App Service] --> VNET[Azure VNet]
    VNET --> DNS[Private DNS]
    DNS --> PE[Private Endpoint]
    PE --> DB[(Cosmos DB Account)]
    ID[Managed Identity] --> APP
    APP --> MON[Application Insights]
~~~

### 33.1. Kiểm tra theo thứ tự

1. Endpoint/FQDN thuộc đúng Cosmos DB for NoSQL account?
2. Private DNS zone, VNet links và resolution đúng?
3. Firewall/route cho phép network egress từ Pod/App Service?
4. TLS certificate chain/truststore hợp lệ?
5. SDK connection mode và ports phù hợp topology?
6. Data-plane role của managed identity hợp lệ?

### 33.2. Direct và Gateway mode

Azure Cosmos DB Java SDK có Direct/Gateway connection modes theo cấu hình hỗ trợ. Network/port/proxy/private connectivity khác nhau; chọn bằng benchmark và security requirements thay vì mặc định một mode phù hợp mọi nơi.

### 33.3. Không tắt TLS để sửa DNS

Không dùng trust-all SSL hoặc mở public access toàn Internet để tránh lỗi 403/timeout. Tìm đúng lỗi DNS, route, TLS và quyền.

### 33.4. Scale Pods có thể tăng connection pressure

Nếu SDK client được khởi tạo ở mỗi Pod, tổng số connections, memory và SNAT requirements tăng theo Pod count. Theo dõi pool/GC/network và reuse client theo lifecycle ứng dụng.

## 34. Azure Monitor và Application Insights

Ứng dụng cần metrics ở cả **Spring Boot**, **Cosmos SDK** và **Cosmos DB service**.

| Phạm vi | Chỉ số | Câu hỏi |
|---|---|---|
| HTTP API | p50/p95/p99 latency | Người dùng có chậm không? |
| Business service | Query duration, result counts | Endpoint nào đắt? |
| SDK | Retry count, dependency latency, error/status | Có retry storm? |
| Cosmos DB | Consumed RU/s, 429 counts | Có quá công suất? |
| Partitions | Normalized RU utilization (nếu có) | Tenant/partition nào nóng? |
| Data | RU/query page, storage growth | Query/index có hiệu quả? |
| JVM | Heap, GC, CPU, threads | App có nghẽn? |
| Network | DNS/TLS failures, connections | Kết nối có vấn đề? |
| Cost | RU provision/usage, storage, logs | Ngân sách có phù hợp? |

### 34.1. Internal 429 có thể không hiện ở final API errors

SDK retry 429 thành công thì controller vẫn trả HTTP 200. p99 có thể tăng. Dùng Cosmos service-side metrics và SDK diagnostics, không chỉ final HTTP status.

### 34.2. Đo request charge bằng SDK khi cần

**CosmosItemResponse.getRequestCharge()** cho RU của point read/write cụ thể. Với Spring Data Repository, nếu abstraction không expose charge trực tiếp, cần instrumentation ở SDK/transport hoặc dùng adapter SDK cho các operations cần đo chi tiết.

### 34.3. Query nhiều pages phải cộng charge

Tổng RU query là tổng RU của các trang thực được đọc. Không lấy một page đầu làm đại diện cho cả truy vấn.

### 34.4. Metrics instrumentation tùy version

Không coi tên metrics hoặc logs tables luôn giống nhau giữa Azure Monitor, OpenTelemetry và Application Insights. Xác minh exporter/instrumentation đang bật trên runtime.

### 34.5. Không đưa PII vào metric dimensions

Dùng operation type, status, deployment/environment và tenant group/hash khi cần. Tránh raw user IDs, full blob paths hoặc customer data trong metric labels.

## 35. Spring Boot Actuator và health checks

Spring Boot Actuator có thể cung cấp endpoints/metrics cho liveness, readiness và application health theo cấu hình.

### 35.1. Liveness không được phụ thuộc một query Cosmos đắt

Nếu database tạm chậm, liveness probe gọi remote dependency có thể khiến AKS restart hàng loạt Pods vẫn khỏe, tạo retry storm.

### 35.2. Phân biệt ba mức

- **Liveness:** process có còn hoạt động đúng không?
- **Readiness:** instance có sẵn sàng nhận traffic không?
- **Business dependency health:** Cosmos DB có đáp ứng workflow hay không, cần monitor riêng theo SLO.

### 35.3. Không gọi findAll cho health probe

Một health check quét container lớn tiêu tốn RU và có thể tự tạo 429. Nếu cần dependency probe, dùng thao tác nhẹ, tần suất/timeout hạn chế và quan sát kết quả.

### 35.4. Bảo vệ Actuator

Không expose public env/configprops/heapdump/mappings; đặt security, private network và access logs theo chính sách.
## 36. Unit testing service và tenant boundary

Vì OrderRepository là interface, có thể mock nó để kiểm tra logic của OrderService mà không cần Azure account.

Ví dụ JUnit 5 và Mockito:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import example.orders.api.CreateOrderRequest;
import example.orders.data.OrderDocument;
import example.orders.data.OrderRepository;
import example.orders.service.OrderService;
import org.junit.jupiter.api.Test;

class OrderServiceTest {
    @Test
    void createUsesTrustedTenant() {
        OrderRepository repo = mock(OrderRepository.class);
        when(repo.save(any(OrderDocument.class)))
            .thenAnswer(call -> call.getArgument(0));

        OrderService service = new OrderService(repo);
        OrderDocument item = service.create(
            "shop-42", new CreateOrderRequest("C-20", 125000L));

        assertEquals("shop-42", item.getTenantId());
        assertEquals("CREATED", item.getStatus());
        verify(repo).save(any(OrderDocument.class));
    }

    @Test
    void invalidAmountDoesNotSave() {
        OrderRepository repo = mock(OrderRepository.class);
        OrderService service = new OrderService(repo);

        assertThrows(IllegalArgumentException.class,
            () -> service.create(
                "shop-42", new CreateOrderRequest("C-20", 0L)));

        verifyNoInteractions(repo);
    }
}
~~~

### 36.1. Mock không kiểm chứng Cosmos mapping

Unit test không thực thi @Container/@PartitionKey, SDK serialization, RBAC, network, throughput hoặc query translation; phải có integration test.

### 36.2. Kiểm thử tenant authorization

Dùng Spring Security test principal của shop-A thử đọc dữ liệu shop-B. Quyền cần được kiểm tra ở TenantAuthorization/service, không phải nhờ user tự gửi tenantId đúng.

### 36.3. Kiểm thử idempotency

Giả lập write đã commit nhưng client mất response rồi retry cùng operationId. Đảm bảo không tạo hai đơn hàng nếu business yêu cầu một outcome duy nhất.

## 37. Integration testing trên Cosmos DB lab

Chỉ dùng resource/dataset test riêng, không ghi dữ liệu thật.

### 37.1. Thiết lập

1. Cosmos DB for NoSQL test account.
2. Database shopdb và container orders với **/tenantId**.
3. Managed identity có data-plane role hoặc test secret trong secret store.
4. Network/DNS từ runner hoặc IDE tới endpoint.
5. Test RU budget và cleanup policy.
6. Test entities/tenants giả, không có PII.

### 37.2. Test cases

- Repository.save ghi đúng JSON.
- findByTenantId và @Query trả đúng tenant.
- Point read id + partition key đúng thì thành công.
- Sai partition key nhưng đúng id trả Not Found.
- ETag/412 khi concurrent writes nếu dùng conditional replace.
- Serialization fields và schemaVersion backward compatibility.
- Multi-page query, paging boundaries và data consistency.
- Unauthorized identity không đọc/ghi được.
- Throttle/timeout policy phân loại rõ ràng.

### 37.3. Cô lập test data

Mỗi test dùng tenantId/runId riêng, cleanup đúng items được tạo. Không dùng deleteAll trên container shared.

### 37.4. Emulator không tái hiện mọi thứ

Nếu dùng Cosmos DB emulator, kiểm tra version/platform/features được hỗ trợ. Không coi emulator thể hiện đầy đủ Entra RBAC, private endpoint, multi-region latency, RU/429 hoặc mọi API production.
## 38. Failure tests: không tạo tải độc hại lên account thật

Để kiểm thử resilience, ưu tiên fake adapter hoặc HTTP stubs, thay vì cố gây 429 trên shared/production Cosmos DB.

| Failure case | Kết quả mong đợi |
|---|---|
| 400 schema/query sai | Không retry mù |
| 401 token hết hạn/sai | Authentication failure |
| 403 thiếu role | Kiểm tra data-plane permission/network |
| 404 item không tồn tại | Domain Not Found |
| 409 duplicate | Idempotency/business conflict |
| 412 stale ETag | Đọc state mới và resolve conflict |
| 429 có retry-after | Bounded retry và giảm tải |
| 503/network timeout | Retry hữu hạn, cuối cùng fail rõ |
| Response với schema cũ | Mapping hoặc migration policy |

### 38.1. Test replay sau write timeout

Một write có thể commit rồi client mất response. Test một retry cùng operationId không tạo hai business orders.

### 38.2. Kiểm thử budget end-to-end

Giới hạn tổng thời gian từ HTTP caller qua service/SDK retries. Không cho API timeout 3 giây nhưng SDK chạy ngầm nhiều phút.

### 38.3. Load test trong lab

Chọn ngưỡng dừng, quota và ngân sách rõ; đo successful throughput, p95/p99, RU/request, hot partitions và final error rates. Không dùng dữ liệu production thật để thử.

## 39. Triển khai Spring Boot trên App Service, AKS hoặc Functions

| Hosting | Phù hợp | Lưu ý |
|---|---|---|
| **Azure App Service** | Java REST API kiểu PaaS | Managed identity, VNet, scaling |
| **AKS** | Kubernetes/microservices | Workload Identity, HPA, Pod limits, DNS |
| **Azure Container Apps** | Container API và background jobs | Identity, ingress, scale rules |
| **Azure Functions** | Event-driven hoặc scheduled jobs | Hosting plan, timeout, cold start |
| **Azure VM** | Yêu cầu cấu hình host đặc thù | OS security, maintenance |

### 39.1. IaC quản lý database resources

Tạo account/container, indexing, throughput và RBAC bằng cơ chế quản trị có approval. Không để mỗi Pod tự thay schema/index/throughput khi khởi động.

### 39.2. Managed identity phải đúng principal

App Service có thể dùng system-assigned hoặc user-assigned identity. AKS Workload Identity phụ thuộc service account và federation. Xác nhận principal thực sự dùng trong Java SDK và role đã cấp.

### 39.3. Scale Java không scale Cosmos RU/s

Tăng Pods khiến số concurrent repository calls nhiều hơn. Nếu bottleneck ở RU/s hoặc hot partition, 429 có thể tăng. Phải điều tiết load và định cỡ database phù hợp.

### 39.4. Secrets và private network

Không lưu Cosmos account key trong Dockerfile hoặc application artifacts. Đặt network/Key Vault/identity theo chính sách, không mở public access tùy tiện để chữa lỗi kết nối.

## 40. CI/CD, IaC và migration document schema

Một release có thể thay đổi đồng thời:

- Java/Spring Boot/Spring Cloud Azure dependencies.
- Entity annotations, DTO/API fields.
- Container indexing/TTL/throughput.
- Partition key strategy và query patterns.
- Managed identity/data-plane RBAC.
- Document schemaVersion.
- Alert thresholds/dashboards.

### 40.1. Thứ tự triển khai gợi ý

1. Review code và data migration.
2. Provision/update Cosmos resources qua IaC có kiểm soát.
3. Xác minh network, identity, data RBAC trong staging.
4. Chạy backfill/migration nếu cần.
5. Deploy Spring Boot staging.
6. Chạy integration/failure tests.
7. Canary/rollout production.
8. Theo dõi 429, RU cost, p99 và correctness.
9. Rollback hoặc forward-fix theo compatibility plan.

### 40.2. Git revert không rollback dữ liệu

Nếu app version mới đã ghi schemaVersion=2, app version cũ có thể không parse được. Thiết kế backward/forward compatibility và quy trình migrate dữ liệu.

### 40.3. Migrations không chạy đồng thời trong mọi Pod

Khi có 20 Pods khởi động, tránh mỗi Pod tự thực hiện destructive migration. Dùng job có ownership, locking/approval và audit.

### 40.4. Bảo vệ CI/CD logs

Không in account keys, token, connection string hoặc document PII trong build logs, pipeline output hoặc error traces.
## 41. Change Feed và xử lý bất đồng bộ

Spring Data Cosmos thường phù hợp cho CRUD và query. Khi muốn xử lý thay đổi dữ liệu liên tục, có thể kết hợp **Cosmos DB Change Feed** với Azure Functions hoặc Java worker.

~~~mermaid
flowchart LR
    APP[Spring Boot Orders API] --> COSMOS[(Cosmos DB)]
    COSMOS --> FEED[Change Feed]
    FEED --> WORKER[Azure Function / Java worker]
    WORKER --> BUS[Service Bus / Analytics]
~~~

### 41.1. Change Feed không phải repository.findAll

Repository.findAll đọc current items. Change Feed dùng để theo dõi thay đổi theo khả năng và semantics được hỗ trợ, tránh quét toàn container mỗi phút để tìm những records mới.

### 41.2. Checkpoint và leases

Processor cần quản lý tiến độ và điều phối workers (lease/checkpoint) theo SDK/runtime. Không dùng biến static trong từng Pod làm checkpoint của toàn hệ thống.

### 41.3. Idempotency downstream

Worker có thể gửi message rồi crash trước checkpoint. Khi replay, event có thể được xử lý lại; consumer cần idempotency key/dedup và dead-letter policy.

### 41.4. Không tự có exactly-once liên dịch vụ

Ghi Cosmos và gửi Service Bus là hai thao tác khác tài nguyên. Có thể dùng outbox/change feed hoặc Saga theo business contract, không coi hai bước là một distributed transaction.

## 42. Chi phí Cosmos DB và Spring Boot

| Nguồn chi phí | Các yếu tố |
|---|---|
| Cosmos throughput | Manual RU/s, autoscale hoặc serverless theo capacity mode |
| Storage/index | Data size, index size, retention |
| Multi-region | Replication/read-write topology |
| Java compute | App Service/AKS/Functions |
| Networking | Private Link, NAT, egress khi áp dụng |
| Monitoring | Application Insights/Log Analytics ingestion |
| Backup/DR | Backup settings, restore mechanisms |
| Workload nền | Import, change feed, migration, replay |
| Retries | Additional requests và latency overhead |

### 42.1. Giảm RU trên mỗi operation

Ưu tiên point reads theo id + partition key, query trong logical partition, projection, indexing phù hợp, giảm document size và duplicate writes. Đo actual request charge trước khi thay đổi capacity.

### 42.2. Tối ưu theo successful throughput và SLO

Chỉ giảm requests để loại bỏ 429 có thể khiến backlog không được xử lý. Đo cost per successful operation, p95/p99 latency, freshness và data correctness.

### 42.3. Khi cần tăng RU/s

Tăng manual/autoscale capacity khi đã đo workload và tối ưu queries/partitioning mà vẫn cần thêm sức xử lý. Hot partition có thể không được giải quyết chỉ bằng tăng tổng RU.

### 42.4. Giá thay đổi theo region và mode

Không hardcode đơn giá trong bài học; tính theo Azure Pricing Calculator và Cost Management tại thời điểm lập kế hoạch.

## 43. Runbook: 429 và p99 latency tăng

Ví dụ:

~~~text
10:00  API p95 = 150 ms
10:05  Batch import bắt đầu
10:07  Cosmos 429 tăng
10:08  SDK retries tăng
10:10  API p99 vượt SLO, một số request timeout
~~~

### Bước 1 — Khoanh vùng

Một tenant, endpoint, container hay toàn hệ thống? Có deploy hoặc job mới vừa chạy không?

### Bước 2 — Kiểm tra ảnh hưởng

Đo p95/p99, final errors, request charge, queue/backlog, SDK attempts và JVM memory.

### Bước 3 — Kiểm tra RU

Manual/autoscale/serverless? Có chạm configured max hoặc nhiều containers cùng share database RU budget không?

### Bước 4 — Kiểm tra hot partition

Tenant nào chiếm nhiều writes? Normalized RU utilization có lệch theo physical partition không? Tăng tổng throughput có cải thiện không?

### Bước 5 — Soát queries

Có code mới chạy findAll, filter thiếu partition key, lấy quá nhiều pages hoặc tạo documents lớn không?

### Bước 6 — Bảo vệ ứng dụng

Giảm background concurrency, đặt admission control, rate limit và bounded retries. Không giữ hàng nghìn HTTP requests chờ vô hạn.

### Bước 7 — Sửa và xác minh

Tối ưu query, indexing, key distribution hoặc tăng capacity có kiểm soát; đo lại successful operations/s, p99, RU/operation, 429 và cost.

### Bước 8 — Điều tra sau sự cố

Lưu correlation/activity IDs, timeline, root cause và phương án rollback. Không sao chép raw customer data/keys vào incident report.
## 44. Bài lab 1: Spring Boot kết nối Cosmos DB for NoSQL

Thực hành trên tài nguyên lab riêng, không có dữ liệu production.
### Phần A — Azure resources

1. Tạo resource group lab riêng và Cosmos DB **for NoSQL** account.
2. Tạo database **shopdb**, container **orders** với partition key **/tenantId**.
3. Chọn capacity mode/thông số RU theo ngân sách lab.
4. Cấp test identity data-plane role thích hợp hoặc dùng key test trong secret store.
5. Kiểm tra endpoint, DNS/TLS, firewall/private networking và Azure Monitor.
6. Ghi resource names để có thể cleanup sau buổi học.

### Phần B — Spring Boot

1. Chọn Spring Boot release và Spring Cloud Azure BOM tương thích.
2. Thêm starter-data-cosmos, Spring Web và Validation.
3. Cấu hình spring.cloud.azure.cosmos.endpoint/database qua môi trường.
4. Bật managed identity/Entra auth khi được hỗ trợ hoặc inject key lab an toàn.
5. Tạo entity OrderDocument, OrderRepository, OrderService.
6. Tạo controller với DTO và TenantAuthorization/Spring Security.
7. Khởi chạy app, thử lưu rồi query dữ liệu tenant giả.

### Phần C — Gỡ lỗi

| Triệu chứng | Kiểm tra |
|---|---|
| Bean creation failed | BOM, Boot compatibility, auto-configuration |
| DNS/TLS failure | Endpoint, private DNS, VNet, truststore |
| 401/403 | Credential, data-plane role, network policies |
| 404 resource | Database/container name và tồn tại |
| 400 partition mismatch | Entity mapping và /tenantId |
| 429 | RU/s capacity, throttling metrics, retries |

**Đừng tăng RU/s để chữa lỗi DNS, bean creation hoặc thiếu RBAC.**

### Phần D — Xác minh và cleanup

App tạo được repository bean, ghi/đọc đúng documents shop-42, logs không chứa key và metrics hiển thị thao tác. Dừng app/test jobs, xóa **chỉ đúng dữ liệu/tài nguyên lab được phép**, rồi kiểm tra chi phí.
## 45. Bài lab 2: CRUD, partition key và optimistic concurrency
### A. Seed documents

1. Tạo ba orders giả của **shop-42** và hai orders giả của **shop-17**.
2. Ghi id, tenantId, status và amountMinor.
3. Xác minh entity mapping trong Cosmos DB Data Explorer/SDK.

### B. Repository queries

1. Gọi findByTenantId("shop-42").
2. Gọi findByTenantIdAndStatus("shop-42", "CREATED").
3. Đảm bảo kết quả không có dữ liệu của shop-17.
4. Đo request charge và latency khi có telemetry.

### C. Point read bằng SDK

1. Chọn id ORD-1001 trong shop-42.
2. Đọc bằng CosmosContainer.readItem(id, new PartitionKey("shop-42"), OrderDocument.class).
3. Ghi RU charge và latency.
4. Đọc cùng id với pk shop-17 và xác nhận Not Found.
5. So sánh với repository query trên cùng item.

### D. Tenant authorization

1. User shop-42 truy cập tài liệu shop-42.
2. User shop-17 yêu cầu đọc order của shop-42.
3. Spring Security/TenantAuthorization phải chặn.
4. HTTP error/log không tiết lộ nội dung của tenant khác.

### E. ETag conflict

1. Hai clients cùng đọc ETag V1.
2. Client B update thành V2.
3. Client A replace với If-Match V1.
4. Xác nhận status 412, không ghi đè state mới.
5. Đọc state mới và xử lý business conflict.

### F. Idempotency

1. Gửi create với operationId ổn định.
2. Giả lập DB commit nhưng client mất response bằng fake adapter.
3. Retry cùng operationId.
4. Xác minh không có hai business orders.

| Thử nghiệm | Kỳ vọng |
|---|---|
| Query shop-42 | Chỉ items shop-42 |
| Point read đúng pk | Có item và RU charge |
| Point read sai pk | Not Found |
| Unauthorized tenant | Bị chặn |
| ETag stale replace | HTTP 412 |
| Replay operationId | Không duplicate |

**Tiêu chí:** tenant isolation, point read, concurrency và idempotency đều được kiểm chứng.
## 46. Bài lab 3: reactive, throttling và giám sát

### A. So sánh Spring MVC với WebFlux

1. Dùng CosmosRepository trong một API sync nhỏ.
2. Dùng ReactiveCosmosRepository trong một WebFlux API lab riêng.
3. Với cùng dataset/logic, đo p95/p99, JVM threads, CPU và success rate.
4. Không dùng Mono.block() trong WebFlux event-loop.
5. Giới hạn số operations đồng thời ở mỗi biến thể.

### B. Mock failures

Tạo fake gateway/stub để mô phỏng:

- 400 với payload/query không hợp lệ.
- 401/403 sai identity hoặc role.
- 404 item không tồn tại.
- 409 business duplicate.
- 412 stale ETag.
- 429 kèm retry-after.
- 503/timeout và retry hết budget.

Không cố tình tạo tải gây 429 trên shared/production Cosmos account.

### C. Đo kết quả

| Metric | Sync | Reactive |
|---|---|---|
| Successful operations/s | Đo | Đo |
| p95/p99 latency | Đo | Đo |
| Total Cosmos RU consumed | Đo | Đo |
| Final 429/5xx | Đo | Đo |
| Retry count | Đo | Đo |
| JVM heap/threads | Đo | Đo |
| Per-item correctness | Kiểm tra | Kiểm tra |

### D. Hot partition mô phỏng

1. Tạo workload nhẹ phân tán nhiều tenantIds.
2. So sánh với cùng số requests tập trung vào một tenant trong lab.
3. Quan sát RU usage/latency/429 nếu có.
4. Lặp với concurrency thấp, điều kiện tương tự.
5. Phân tích vì sao tăng Java threads/Pods không tạo thêm RU/s.

### E. Tiêu chí hoàn thành

Đề xuất mô hình sync/reactive cho workload đã đo, xác minh bounded retry/authorization/idempotency, và chứng minh không có regression về data correctness khi tối ưu hiệu năng.
## 47. Checklist production

- [ ] Dùng Azure Cosmos DB **for NoSQL**, không trộn API MongoDB.
- [ ] Spring Boot, Spring Cloud Azure và Cosmos SDK versions tương thích.
- [ ] Dependency BOM và vulnerability scan đã được kiểm tra.
- [ ] Container được tạo đúng tên, partition key path **/tenantId**.
- [ ] Partition key được chọn theo query pattern và phân phối tải.
- [ ] Đã kiểm tra hot partitions, tenant skew và peak workload.
- [ ] Có data contract, schemaVersion và migration strategy.
- [ ] Entity @Id và @PartitionKey mapping đúng dữ liệu JSON.
- [ ] Không tự tạo/sửa container/throughput từ mọi Pod startup.
- [ ] Managed identity/Entra credential dùng khi có thể.
- [ ] Cosmos data-plane RBAC có scope tối thiểu.
- [ ] Spring Security xác minh user/tenant/document authorization.
- [ ] Không dùng account key plaintext trong Git/image/logs.
- [ ] Network/private endpoint/DNS/TLS đã kiểm thử từ runtime thật.
- [ ] Reuse Cosmos client, credential, HTTP transport qua DI/lifecycle.
- [ ] Không dùng findAll() cho endpoint production.
- [ ] Có query tenant-scoped, pagination và giới hạn kết quả.
- [ ] Dùng point read id + partition key khi phù hợp.
- [ ] Đã đo RU/request/query và tổng RU trên nhiều pages.
- [ ] Indexing policy phù hợp reads/writes, không scan vô cớ.
- [ ] Có optimistic concurrency/ETag hoặc version control khi cần.
- [ ] Create/update APIs có idempotency key phù hợp.
- [ ] Không coi @Transactional là transaction xuyên partitions.
- [ ] Có retry budget/Retry-After/deadline và status classifier.
- [ ] Không retry 400/403/409/412 như lỗi 429.
- [ ] Có concurrency/rate limit, bounded queue và backpressure.
- [ ] Background jobs không tiêu hết RU budget của interactive APIs.
- [ ] Đã chọn manual/autoscale/serverless bằng số liệu.
- [ ] Có monitor 429, RU, p95/p99, retries và request failures.
- [ ] Có partition-level metrics và tenant isolation monitoring.
- [ ] Logs/metrics không chứa raw PII/secrets.
- [ ] Liveness/readiness probes được thiết kế an toàn.
- [ ] Unit tests, integration tests và fake failure tests đầy đủ.
- [ ] Có load test với data distribution gần production.
- [ ] CI/CD có staging, IaC, schema migration và rollback.
- [ ] Có backup/restore/DR policy theo yêu cầu.
- [ ] Có cost budgets/alerts cho compute, RU, storage và logs.
- [ ] Có runbook cho 401/403/404/412/429/503/timeout.
- [ ] Có quy trình cleanup test resources và thu hồi test roles.
## 48. Câu hỏi tự kiểm tra
1. Spring Data Cosmos được thiết kế cho API nào của Cosmos DB?
2. Cosmos account, database và container khác nhau thế nào?
3. Partition key path /tenantId khác giá trị shop-42 ra sao?
4. Vì sao id + partition key quan trọng cho point read?
5. CosmosRepository giúp gì và không giúp gì?
6. Derived query có luôn là point read không?
7. Vì sao findAll có thể tốn RU và memory?
8. Khi nào nên dùng Cosmos SDK v4 trực tiếp?
9. @Container, @Id và @PartitionKey có tác dụng gì?
10. Điều gì xảy ra nếu @PartitionKey không khớp container path?
11. Vì sao chọn BOM tương thích Spring Boot?
12. Key auth khác Entra/managed identity ở rủi ro nào?
13. Azure ARM Contributor có tự được đọc items không?
14. Vì sao Spring Security vẫn cần khi app identity đọc được container?
15. Vì sao không nhận tenantId từ request body làm quyền truy cập?
16. ReactiveCosmosRepository khác CosmosRepository ra sao?
17. Mono/Flux có tự giảm RU/request không?
18. Vì sao không gọi block trong WebFlux event-loop?
19. Pagination/continuation token giúp tránh vấn đề gì?
20. Vì sao query thiếu partition key thường đắt hơn?
21. Cosmos DB tính RU/request theo những yếu tố nào?
22. HTTP 429 cho biết điều gì?
23. Vì sao autoscale vẫn có thể trả 429?
24. Hot logical partition khác thiếu tổng RU/s ra sao?
25. SDK retry và Spring outer retry có thể gây vấn đề gì?
26. Retry-After và deadline giúp giảm rủi ro nào?
27. ETag giúp tránh lost update như thế nào?
28. Vì sao 412 không được retry giống 429?
29. @Transactional có mặc định atomic xuyên các Cosmos partitions không?
30. Vì sao ghi Cosmos rồi gửi Service Bus cần idempotency/outbox?
31. SchemaVersion có vai trò gì khi migration?
32. Vì sao sửa @PartitionKey không tự sửa partition key path?
33. Vì sao liveness probe không nên gọi findAll?
34. Đo những chỉ số gì để so sánh sync/reactive?
35. HTTP 200 có che SDK retry 429 nội bộ không?
36. Data-plane RBAC khác tenant authorization của Spring thế nào?
37. Những nội dung nào phải loại khỏi logs và metrics?
38. Khi Change Feed event được replay, consumer phải làm gì?
39. Những nguồn chi phí nào ngoài RU/s?
40. Khi production có 429, các bước đầu của runbook là gì?
## 49. Tổng kết

**Tích hợp Cosmos DB với Spring Data** giúp Spring Boot ứng dụng dùng entity, repository, derived query và dependency injection để truy cập **Azure Cosmos DB for NoSQL**. Các lớp **@Container, @Id, @PartitionKey, CosmosRepository** làm code ngắn gọn nhưng không thay thế việc thiết kế partition key, indexing, authorization và RU/s.

Với dữ liệu multi-tenant, đặt **tenantId** theo quyền đã xác minh, hạn chế cross-partition queries, dùng **point read có id + partition key** khi cần hiệu quả cao và thiết kế pagination/continuation. Chú ý **ETag, idempotency và transaction boundaries**, vì repository.save hoặc @Transactional không tự bảo đảm toàn bộ workflow nhiều dịch vụ là atomic.

Khi chạy production, ưu tiên **managed identity + Cosmos data-plane RBAC**, private networking, secrets management, bounded retries và backpressure. Đo **HTTP 429, request charge, normalized RU utilization, p95/p99, throughput thành công và chi phí** trên cả Cosmos DB và Spring Boot. Lựa chọn **CosmosRepository hay ReactiveCosmosRepository** dựa trên mô hình thực thi ứng dụng và benchmark, không dựa vào giả định async luôn tốt hơn.

Một triển khai hoàn chỉnh kết nối Spring Boot với **Microsoft Entra ID, App Service/AKS/Functions, Azure networking, Application Insights, CI/CD và Cost Management** để bảo đảm dữ liệu đúng, ứng dụng an toàn, có thể kiểm thử/khôi phục và chi phí dự báo được.














