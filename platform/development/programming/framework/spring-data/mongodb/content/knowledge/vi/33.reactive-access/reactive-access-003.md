# AbstractReactiveMongoConfiguration và @EnableReactiveMongoRepositories

## 1. Bài toán: khởi tạo đường truy cập MongoDB theo reactive

Trong chương **Truy cập reactive** của **Spring Data MongoDB**, ứng dụng có thể truy vấn và ghi document bằng `ReactiveMongoTemplate` hoặc repository trả về `Mono<T>`/`Flux<T>`. Những API này khác về cách tổ chức luồng thực thi so với `MongoTemplate` và `MongoRepository` đồng bộ: thay vì chờ kết quả trong thread gọi, reactive driver cung cấp publisher để xử lý dữ liệu bất đồng bộ theo mô hình Reactive Streams.

Ví dụ một API danh mục cần:

- Lấy một sản phẩm theo SKU **trong tenant đã xác thực**;
- Liệt kê các sản phẩm còn hoạt động, có thứ tự rõ ràng;
- Cập nhật tồn kho bằng một conditional update;
- Phát hiện kết quả rỗng, lỗi truy vấn và đóng kết nối đúng vòng đời.

Để repository reactive hoạt động, Spring phải biết **reactive MongoDB client**, **database**, **mapping/converter**, **ReactiveMongoTemplate** và **nơi tìm repository interfaces**. Hai thành phần trọng tâm của bài là:

1. `AbstractReactiveMongoConfiguration`: lớp cấu hình cơ sở của Spring Data MongoDB để khai báo hạ tầng truy cập MongoDB reactive **theo cách thủ công, có chủ đích**.
2. `@EnableReactiveMongoRepositories`: kích hoạt phát hiện các **reactive repository interfaces** và tạo repository proxies, thường chỉ định package/loại template cần dùng.

Trong dự án **Spring Boot** đã sử dụng `spring-boot-starter-data-mongodb-reactive`, nhiều bean và repository scanning **có thể được auto-configure**. Vì vậy không phải ứng dụng nào cũng cần kế thừa `AbstractReactiveMongoConfiguration` hoặc thêm `@EnableReactiveMongoRepositories`. Bài sẽ trình bày hai con đường **thay thế/cân nhắc**, không khuyên khai báo mọi cấu hình chồng lên nhau.

### Kết quả cần đạt

1. Nắm vai trò từng bean từ reactive driver đến `ReactiveMongoRepository`.
2. Viết cấu hình kế thừa `AbstractReactiveMongoConfiguration` với `reactiveMongoClient()`, `getDatabaseName()`.
3. Dùng `@EnableReactiveMongoRepositories(basePackageClasses = ...)` để chỉ định đúng repository cần quét.
4. Phân biệt cấu hình thủ công với auto-configuration của Spring Boot.
5. Thực hành `Mono`, `Flux`, `ReactiveMongoTemplate`, ánh xạ `@Document`/`@Field`, filter tenant và lỗi rỗng.
6. Hiểu subscription, không dùng `block()` tùy tiện trong WebFlux, kiểm soát backpressure và vòng đời client.
7. Kiểm thử trên MongoDB thực bằng Reactor `StepVerifier`; nhận diện lỗi startup và transaction/reactive context.

> Ví dụ hướng tới Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x và MongoDB tương thích. Chữ ký hoặc hành vi của một số API có thể khác ở phiên bản khác. Dùng cùng bộ phiên bản do Spring Boot quản lý; không pha các driver MongoDB đồng bộ và reactive rồi kỳ vọng chúng hoán đổi được.

## 2. Kiến trúc reactive MongoDB trong Spring

Sơ đồ từ ứng dụng đến MongoDB:

~~~mermaid
flowchart TD
    A["HTTP request / reactive job"] --> B["Reactive service trả Mono / Flux"]
    B --> C["ReactiveMongoRepository proxy"]
    B --> D["ReactiveMongoTemplate"]
    C --> D
    D --> E["ReactiveMongoDatabaseFactory"]
    E --> F["Reactive Streams MongoClient"]
    F --> G["MongoDB server"]
    H["Mapping context + MongoConverter"] --> D
    I["@EnableReactiveMongoRepositories"] --> C
    J["AbstractReactiveMongoConfiguration hoặc Boot auto-config"] --> E
    J --> H
~~~

| Thành phần | Trách nhiệm chính |
|---|---|
| `com.mongodb.reactivestreams.client.MongoClient` | Kết nối MongoDB dùng Reactive Streams driver; không phải sync `MongoClient` |
| `ReactiveMongoDatabaseFactory` | Cung cấp quyền truy cập reactive tới database, hỗ trợ context/session phù hợp |
| `ReactiveMongoTemplate` | API reactive cho query, update, aggregation, index, conversion |
| Mapping context/converter | Mapping class Java/record với BSON, `@Id`/`@MongoId`, `@Field`, nested types |
| `ReactiveMongoRepository<T, ID>` | Repository abstraction, được Spring tạo proxy |
| `@EnableReactiveMongoRepositories` | Chỉ định repository scan và template reference |
| `AbstractReactiveMongoConfiguration` | Cấu hình nền tảng cho reactive infrastructure |
| Spring Boot auto-configuration | Có thể cung cấp những bean trên khi starter và conditions phù hợp |

Một repository không tự mở connection bằng cách `new`. Nó là **Spring bean proxy** và cần hạ tầng reactive hợp lệ trong application context.

### 2.1. Reactive không đồng nghĩa “MongoDB xử lý vô hạn request”

I/O bất đồng bộ giúp tránh việc giữ một thread ứng dụng bị block cho mỗi thao tác chờ database. Tuy nhiên:

- MongoDB server vẫn cần CPU, RAM, index, connection pool và I/O.
- Query chậm vẫn chậm nếu filter không có index, scan quá rộng hoặc aggregation dùng nhiều tài nguyên.
- Gọi code blocking trong event-loop có thể làm ứng dụng WebFlux chậm.
- Đọc hàng triệu dòng vào một `List` vẫn tốn bộ nhớ dù nguồn là `Flux`.
- Reactive programming không tự tạo transaction, tenant security hay cơ chế retry an toàn.

## 3. Chọn giữa Spring Boot auto-configuration và cấu hình thủ công

Hai cách khởi tạo phổ biến:

| Tình huống | Cách ưu tiên |
|---|---|
Spring Boot, một MongoDB database, schema thông dụng | Starter reactive và Boot auto-configuration |
Muốn kiểm soát rõ bean factory/template/repository scan | Cấu hình tường minh, có thể dùng `AbstractReactiveMongoConfiguration` |
Không dùng Spring Boot | Cấu hình Spring Data thủ công |
Nhiều MongoDB databases/templates | Cấu hình có tên, explicit template references, kiểm tra phạm vi repository |
Mới chuyển từ sync sang reactive | Kiểm tra rõ driver/starter và API; không chỉ đổi return type sang `Mono` |

**Quy tắc vận hành:** chọn **một nơi chịu trách nhiệm chính** cho việc tạo client/factory/template và repository scanning. Nếu vừa để Boot auto-configure, vừa khai báo nhiều bean thủ công cùng tên, có thể có bean conflict, repository scan trùng hoặc kết nối không dùng như dự định.

### 3.1. Cách A: Spring Boot auto-configuration

Dependencies Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

`spring-boot-starter-webflux` chỉ cần khi xây HTTP API theo WebFlux; một batch/job reactive không nhất thiết phải có WebFlux. `reactor-test` được dùng cho `StepVerifier`.

Ví dụ cấu hình:

~~~yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI:mongodb://localhost:27017/catalogdb}"
~~~

Trong cách này, Spring Boot có thể tạo reactive client, database factory, template và reactive repositories **nếu các điều kiện auto-configuration/repository scanning phù hợp**. Một ứng dụng chuẩn có `@SpringBootApplication` đặt ở package cha của repository thường không cần tự viết `@EnableReactiveMongoRepositories`.

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Đặt repository trong `com.example.catalog` hoặc package con. Nếu repository nằm ngoài vùng scan, cần điều chỉnh cấu hình scan thay vì đoán rằng framework sẽ tự tìm khắp classpath.

### 3.2. Cách B: AbstractReactiveMongoConfiguration

Khi cần kiểm soát tường minh, viết `@Configuration` kế thừa lớp Spring Data này. Bản cấu hình đầy đủ sẽ có ở mục 6; điểm khác biệt là bạn chủ động cung cấp **reactive MongoClient** và **database name**, còn lớp cơ sở hỗ trợ tạo infrastructure bean liên quan.

Trong Spring Boot, cách B phù hợp khi dự án đã chủ động quản lý hạ tầng thay vì phụ thuộc toàn bộ vào Boot auto-configuration. Không nhập cả hai bộ cấu hình một cách vô thức.

## 4. Dependency và đúng loại MongoClient

Đối với reactive access, type cần dùng là:

~~~java
import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
~~~

Không nhầm với:

~~~java
// Driver đồng bộ, KHÔNG phải type ở cấu hình reactive bên dưới:
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
~~~

Hai loại cùng tên đơn giản `MongoClient` nhưng thuộc package khác nhau. Driver reactive thực hiện publisher-based operations; driver sync thực hiện blocking calls. `MongoTemplate` và `ReactiveMongoTemplate` cũng khác nhau.

### 4.1. Vì sao không nên trộn driver version?

Spring Boot quản lý dependency versions qua BOM. Nếu tự ép một MongoDB Reactive Streams Driver mới/cũ không tương thích với Spring Data MongoDB trong cùng runtime, ứng dụng có thể gặp lỗi class/method không tồn tại hoặc runtime behavior khác.

Quy trình:

1. Chọn một dòng Spring Boot phù hợp.
2. Dùng `spring-boot-starter-data-mongodb-reactive` cùng BOM.
3. Chỉ override dependency version sau khi đọc bảng tương thích và test.
4. Khi project đã có sync starter, kiểm tra Boot đang tạo **cả hai client/template** hay chỉ một phần.

### 4.2. Một client là tài nguyên dài hạn

`MongoClient` giữ connection pool/tài nguyên. Không tạo client mới trong **mỗi request**:

~~~java
// Tránh:
public Mono<?> everyRequest() {
    MongoClient client = MongoClients.create(uri);
    // Tạo client mới liên tục, khó đóng/tái sử dụng pool.
    throw new UnsupportedOperationException("Minh họa anti-pattern");
}
~~~

Đây chỉ là đoạn minh họa lỗi thiết kế, không phải service cần chạy. Trong ứng dụng, dùng **Spring-managed singleton MongoClient** có vòng đời/cleanup thích hợp.

## 5. Entity mẫu: cấu trúc BSON và tên field Java

Ta dùng collection `catalog_products`:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": "BOTTLE-500",
  "name": "Bình nước giữ nhiệt",
  "status": "ACTIVE",
  "stock_qty": 12,
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public record CatalogProduct(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String sku,
        String name,
        String status,
        @Field("stock_qty") long stockQty,
        Instant createdAt) {
}
~~~

Ý nghĩa:

- `@Document` ánh xạ entity sang collection `catalog_products`.
- `@MongoId(FieldType.STRING)` giữ `_id` là BSON String theo schema ví dụ.
- Property Java `stockQty` được lưu là BSON `stock_qty` nhờ `@Field`.
- `createdAt` là thời điểm được dùng khi sắp xếp danh sách.
- `tenantId` dùng để giới hạn dữ liệu theo tenant, **không tự được Spring thêm vào mọi query**.

Repository có thể dùng **Java property names** cho query derived. Khi dùng raw BSON trong driver/aggregation stage tùy chỉnh, cần tham chiếu **BSON field names** đúng thực tế.

### 5.1. Reactive entity mapping không biến Java record thành bất biến nghiệp vụ

Java record là cấu trúc dữ liệu immutable ở mức các component references, thích hợp cho kết quả đọc/ghi. Nhưng nó không tự áp dụng invariant “stock không âm”, “mỗi tenant chỉ một SKU” hay “chỉ ACTIVE mới được bán”. Các invariant đó cần conditional updates, unique indexes, validation, quyền tenant và tests tương ứng.

## 6. Cấu hình thủ công với AbstractReactiveMongoConfiguration

Đây là cấu hình **tự chứa** cho đường truy cập reactive, khi dự án chọn kiểm soát thủ công thay vì dựa hoàn toàn vào Boot auto-configuration.

**ReactiveMongoConfig.java**

~~~java
package com.example.catalog;

import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.AbstractReactiveMongoConfiguration;
import org.springframework.data.mongodb.repository.config.EnableReactiveMongoRepositories;

@Configuration
@EnableReactiveMongoRepositories(
        basePackageClasses = CatalogProductRepository.class)
public class ReactiveMongoConfig
        extends AbstractReactiveMongoConfiguration {

    private final String connectionString;
    private final String databaseName;

    public ReactiveMongoConfig(
            @Value("${app.mongodb.uri}") String connectionString,
            @Value("${app.mongodb.database}") String databaseName) {
        this.connectionString = connectionString;
        this.databaseName = databaseName;
    }

    @Override
    protected String getDatabaseName() {
        return databaseName;
    }

    @Bean(destroyMethod = "close")
    @Override
    public MongoClient reactiveMongoClient() {
        return MongoClients.create(connectionString);
    }
}
~~~

Ví dụ properties dành cho cấu hình này:

~~~yaml
app:
  mongodb:
    uri: "${MONGODB_URI:mongodb://localhost:27017}"
    database: "catalogdb"
~~~

Đây là **properties riêng** của `ReactiveMongoConfig`, không phải alias tự động của `spring.data.mongodb.uri`. Khi chọn cách manual, bạn cần định nghĩa rõ cách truyền cấu hình và secret. Trên production, không hard-code mật khẩu MongoDB trong source.

**Quan trọng:** đặt `ReactiveMongoConfig`, repository và entity trong package được cấu hình scan. Ở ví dụ, `basePackageClasses = CatalogProductRepository.class` chỉ định package chứa repository; service vẫn cần component scan hoặc được import riêng.

### 6.1. Vai trò từng override

| Thành phần | Vai trò |
|---|---|
`getDatabaseName()` | Xác định tên database sử dụng cho reactive MongoDB infrastructure |
`reactiveMongoClient()` | Cung cấp `com.mongodb.reactivestreams.client.MongoClient` |
`@Bean(destroyMethod = "close")` | Đặt vòng đời client dưới Spring; đóng khi context shutdown |
`@EnableReactiveMongoRepositories(...)` | Quét và đăng ký repository proxies |
`AbstractReactiveMongoConfiguration` | Cung cấp cấu hình nền cho mapping, converter, database factory, template theo phiên bản Spring Data |

Lớp cơ sở không giải quyết bài toán xác thực tenant hoặc thiết kế truy vấn; nó chỉ là một **điểm tổ chức hạ tầng**.

### 6.2. Vì sao khai báo @Bean khi override client?

Việc cung cấp MongoClient như một Spring bean giúp reuse connection pool, injection, lifecycle và kiểm tra context. Một số ví dụ API của Spring Data override `reactiveMongoClient()` mà không thể hiện rõ toàn bộ annotation tùy version; ở đây khai báo `@Bean` tường minh để người học thấy vòng đời tài nguyên.

Không tạo hai bean client thủ công cho cùng database trừ khi có thiết kế rõ: một template dùng client A còn repository lại dùng client B có thể gây lỗi cấu hình khó chẩn đoán.

### 6.3. Sự khác nhau giữa getDatabaseName và URI

`MongoClients.create(connectionString)` cấu hình cách driver kết nối/authenticate. `getDatabaseName()` chọn database do Spring Data sử dụng. Khi URI đã chứa database mặc định hoặc thông tin xác thực gắn với authSource, cần cấu hình cho nhất quán:

- Không suy tên DB từ đường dẫn URI nếu config thủ công đã trả một tên khác.
- Không tự tạo collection vào DB kiểm thử trong khi repository đọc DB production do sai `getDatabaseName()`.
- Với URI có credentials, kiểm tra `authSource` và quyền của tài khoản theo database thực tế.

## 7. @EnableReactiveMongoRepositories quét và tạo proxy như thế nào?

Annotation:

~~~java
@EnableReactiveMongoRepositories(
        basePackageClasses = CatalogProductRepository.class)
~~~

khai báo vị trí repository interfaces. Spring Data quét package có `CatalogProductRepository`, tìm interface repository reactive phù hợp và tạo proxy kết nối tới `ReactiveMongoTemplate` được chọn.

### 7.1. Base package có ý nghĩa chính xác

| Cách khai báo | Khi nào phù hợp |
|---|---|
`@EnableReactiveMongoRepositories` không có tham số | Scan theo package của class cấu hình và package con theo quy tắc framework |
`basePackages = "com.example.catalog"` | Khi muốn chỉ rõ package dạng String |
`basePackageClasses = CatalogProductRepository.class` | Refactor-safe hơn String package |
`reactiveMongoTemplateRef = "reactiveMongoTemplate"` | Khi cần chọn tên template bean, nhất là nhiều template |

Không quét cả package gốc của công ty chỉ để “cho chắc”; phạm vi scan rộng có thể nạp repositories không liên quan hoặc trùng definition. Cũng không dùng `@EnableMongoRepositories` (imperative) để kỳ vọng nó sinh reactive repository proxies.

### 7.2. @EnableReactiveMongoRepositories không tạo database server

Nó **không** chạy `mongod`, tạo một MongoDB replica set hay cấu hình network. Repository proxy có thể được tạo trong Spring context nhưng thao tác thật sẽ lỗi khi URI/credentials/server không hoạt động.

### 7.3. Repository scanning khác entity mapping

`basePackageClasses` ở đây xác định **vùng quét repository**. Entity mapping thường được phát hiện/đăng ký theo cơ chế mapping context, metadata và quy tắc package của configuration. Nếu entity ở package khác và gặp lỗi mapping, cần kiểm tra getMappingBasePackages/config entity scan tương ứng; không mặc định rằng repository scan package sẽ đổi tất cả entity mapping packages.

## 8. ReactiveMongoRepository: khai báo method tìm kiếm

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CatalogProductRepository
        extends ReactiveMongoRepository<CatalogProduct, String> {

    Mono<CatalogProduct> findByTenantIdAndSku(
            String tenantId, String sku);

    Flux<CatalogProduct> findByTenantIdAndStatusOrderByCreatedAtDesc(
            String tenantId, String status);

    Mono<Boolean> existsByTenantIdAndSku(
            String tenantId, String sku);

    Mono<Long> countByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

Với convention ở trên:

- `findByTenantIdAndSku` dùng equality trên `tenantId` và `sku`.
- `findByTenantIdAndStatusOrderByCreatedAtDesc` chọn tập ACTIVE của tenant và sắp thời gian giảm dần.
- `existsBy...` trả `Mono<Boolean>`, không trả boolean trực tiếp khi gọi method.
- `countBy...` trả `Mono<Long>`.

**Repository derived query dùng tên property Java**, không cần khai báo tên BSON trong method. Với field `@Field("stock_qty")`, nếu thêm `findByStockQtyGreaterThanEqual` thì phần property name vẫn là `StockQty`, còn converter xử lý tên lưu trữ.

### 8.1. Mono và Flux khác nhau

| Type | Ý nghĩa dự kiến | Ví dụ |
|---|---|---|
`Mono<CatalogProduct>` | 0 hoặc 1 document | Tìm SKU của một tenant |
`Flux<CatalogProduct>` | 0..N document | Liệt kê sản phẩm ACTIVE |
`Mono<Boolean>` | Một kết quả kiểm tra tồn tại | `existsByTenantIdAndSku` |
`Mono<Long>` | Một kết quả đếm | `countByTenantIdAndStatus` |
`Mono<Void>` | Chỉ biểu diễn hoàn tất/lỗi | `deleteAll` hoặc một pipeline command |

Một `Mono<CatalogProduct>` **rỗng** không phải là document null. Reactor không phát `null` làm phần tử thông thường. Khi entity không tồn tại, dùng `switchIfEmpty`/`defaultIfEmpty`/`hasElement` theo đúng contract.

### 8.2. Derived query không tự kiểm tra tenant

Repository thừa hưởng các method như `findAll()`. Trong ứng dụng đa tenant, gọi `findAll()` ở HTTP endpoint có thể đọc sản phẩm của **mọi tenant**, dù một method khác có `findByTenantId...`.

Phải thiết kế service/API áp dụng tenant từ **auth context đáng tin**; không nhận bất kỳ tenant ID do client tự chọn rồi mặc định được phép truy cập. Index tốt không thay phân quyền.

## 9. Viết reactive service từ repository: không block, không tự subscribe

**CatalogQueryService.java**

~~~java
package com.example.catalog;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CatalogQueryService {
    private final CatalogProductRepository repository;

    public CatalogQueryService(CatalogProductRepository repository) {
        this.repository = repository;
    }

    public Mono<CatalogProduct> findBySku(
            String authenticatedTenantId, String sku) {
        requireTenant(authenticatedTenantId);
        if (sku == null || sku.isBlank()) {
            return Mono.error(new IllegalArgumentException("SKU rỗng"));
        }

        return repository.findByTenantIdAndSku(authenticatedTenantId, sku)
                .switchIfEmpty(Mono.error(
                        new CatalogProductNotFoundException(sku)));
    }

    public Flux<CatalogProduct> activeProducts(
            String authenticatedTenantId) {
        requireTenant(authenticatedTenantId);

        return repository
                .findByTenantIdAndStatusOrderByCreatedAtDesc(
                        authenticatedTenantId, "ACTIVE");
    }

    public Mono<Boolean> existsBySku(
            String authenticatedTenantId, String sku) {
        requireTenant(authenticatedTenantId);
        if (sku == null || sku.isBlank()) {
            return Mono.error(new IllegalArgumentException("SKU rỗng"));
        }
        return repository.existsByTenantIdAndSku(
                authenticatedTenantId, sku);
    }

    private static void requireTenant(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant không hợp lệ");
        }
    }
}
~~~

**CatalogProductNotFoundException.java**

~~~java
package com.example.catalog;

public class CatalogProductNotFoundException
        extends RuntimeException {
    public CatalogProductNotFoundException(String sku) {
        super("Không tìm thấy sản phẩm với SKU: " + sku);
    }
}
~~~

`CatalogQueryService` trả Publisher để caller — HTTP WebFlux runtime, batch pipeline hoặc test — quyết định subscription. Không gọi `subscribe()` trong service chỉ để “kích hoạt truy vấn”; làm vậy tách truy vấn khỏi kết quả, lỗi, cancellation và lifecycle của caller.

### 9.1. Mono.empty khác exception

Một repository method tìm theo SKU thường trả `Mono.empty()` khi không có document. Service chọn hợp đồng “không có sản phẩm thì lỗi domain” bằng:

~~~java
return repository.findByTenantIdAndSku(tenantId, sku)
        .switchIfEmpty(
                Mono.error(new CatalogProductNotFoundException(sku)));
~~~

Khi muốn API trả 404, tầng WebFlux có thể map domain exception đó thành HTTP 404. Khi muốn trả tùy chọn “không tìm thấy là hợp lệ”, có thể giữ `Mono.empty()` hoặc dùng một response DTO phù hợp. Không dùng `null` để thay một Publisher rỗng.

### 9.2. Phải lấy tenant từ nguồn tin cậy

Tham số `authenticatedTenantId` nhấn mạnh tenant được xác định bởi cơ chế authentication/authorization phía server. Controller không nên truyền trực tiếp tenantId tùy ý từ query string rồi bỏ qua quyền của principal.

Trong ứng dụng WebFlux, có thể tạo một component lấy tenant từ security context/principal và sau đó:

~~~java
return authenticatedTenantProvider.currentTenantId()
        .flatMap(tenantId -> catalogQueryService.findBySku(
                tenantId, sku));
~~~

Fragment trên giả định `currentTenantId()` trả `Mono<String>` và chỉ cung cấp tenant đã được authorize. Nó minh họa điểm kết hợp security context với reactive flow, không phải một bản triển khai security provider. **Đừng đưa tenantId do client tự chọn vào như nguồn tin cậy**.

## 10. Mono, Flux và subscription: khi nào lệnh được thực thi?

Trong Reactor, hầu hết các publisher từ repository/template là **cold**: chỉ mô tả công việc trước khi có subscriber, và truy vấn thực sự được kích hoạt khi có subscription theo semantics publisher.

~~~java
Mono<CatalogProduct> pending =
        repository.findByTenantIdAndSku("tenant-a", "BOTTLE-500");

// Chưa block, chưa subscribe và chưa có kết quả ở đây.
~~~

Trong WebFlux, framework subscribe vào Publisher do handler trả về. Trong test, `StepVerifier` subscribe giúp kiểm chứng signals. Trong một ứng dụng batch, một pipeline được nối vào orchestrator có lifecycle rõ ràng.

### 10.1. Không return entity bằng block()

Tránh:

~~~java
public CatalogProduct unsafe(String tenantId, String sku) {
    return repository.findByTenantIdAndSku(tenantId, sku)
            .block();
}
~~~

`block()` chuyển chờ kết quả về hành vi blocking, có thể gây tắc event-loop hoặc lỗi trong thread non-blocking. Không dùng nó như cách mặc định để biến API reactive về imperative.

Tốt hơn:

~~~java
public Mono<CatalogProduct> correct(String tenantId, String sku) {
    return repository.findByTenantIdAndSku(tenantId, sku);
}
~~~

Nếu ứng dụng thuần synchronous, cân nhắc `MongoTemplate`/repository imperative từ đầu, thay vì viết reactive xong block tại mọi tầng.

### 10.2. map và flatMap

`map` dùng cho phép biến đổi **đồng bộ**:

~~~java
Mono<String> name =
        repository.findByTenantIdAndSku("tenant-a", "BOTTLE-500")
                .map(CatalogProduct::name);
~~~

`flatMap` dùng khi một bước trả **Publisher**:

~~~java
Mono<Boolean> active =
        repository.findByTenantIdAndSku("tenant-a", "BOTTLE-500")
                .flatMap(product ->
                        repository.existsByTenantIdAndSku(
                                product.tenantId(), product.sku()));
~~~

Đây là minh họa composition; điều kiện `exists` vừa nêu không cần thiết trong nghiệp vụ thật vì document đã được tìm thấy. Trọng tâm là `flatMap` nối một bước bất đồng bộ khác mà **không gọi `block()`**.

### 10.3. subscribe() trong service không phải cách “fire and forget” an toàn

Sai:

~~~java
public Mono<Void> unsafeWrite(CatalogProduct product) {
    repository.save(product).subscribe();
    return Mono.empty();
}
~~~

Caller nhận `Mono.empty()` hoàn thành ngay, trong khi write nằm ở subscription độc lập. Lỗi database có thể không được caller xử lý; cancellation, transaction context, backpressure và kết quả cũng bị tách rời.

Đúng hơn:

~~~java
public Mono<Void> saveThenComplete(CatalogProduct product) {
    return repository.save(product).then();
}
~~~

Caller subscribe vào một Publisher thể hiện **chính kết quả công việc**. Để viết batch/worker có trách nhiệm riêng, cần một subscriber có lifecycle, logging/retry/termination rõ ràng, không chỉ gọi `subscribe()` rồi bỏ mặc.

### 10.4. Nhiều subscription có thể lặp lại thao tác

Với cold Publisher, mỗi lần subscribe có thể kích hoạt một lần query/write. Không viết:

~~~java
Mono<CatalogProduct> saved = repository.save(product);
saved.subscribe();
saved.subscribe(); // Có thể thực hiện thêm một write.
~~~

`save` với cùng ID có thể tạo kết quả không như mong muốn khi nhiều subscribers hoặc nhiều request đồng thời. Với `$inc` hay external side effect, tác hại rõ hơn. Composition cần nhất quán idempotency, retry và subscriber ownership.

## 11. ReactiveMongoTemplate để kiểm soát Query và Sort

Repository derived queries rất tiện cho tìm kiếm đơn giản. Khi filter, sort, projection hoặc limit phức tạp, `ReactiveMongoTemplate` giúp diễn đạt truy vấn tường minh.

**CatalogTemplateQueryService.java**

~~~java
package com.example.catalog;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CatalogTemplateQueryService {
    private final ReactiveMongoTemplate template;

    public CatalogTemplateQueryService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<CatalogProduct> newestActive(
            String authenticatedTenantId, int limit) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || limit < 1 || limit > 100) {
            return Flux.error(
                    new IllegalArgumentException("Filter/limit sai"));
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE"));

        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")));
        query.limit(limit);
        return template.find(query, CatalogProduct.class);
    }

    public Mono<CatalogProduct> findByIdInTenant(
            String authenticatedTenantId, String productId) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || productId == null || productId.isBlank()) {
            return Mono.error(
                    new IllegalArgumentException("Input sai"));
        }

        Query query = Query.query(
                Criteria.where("id").is(productId)
                        .and("tenantId").is(authenticatedTenantId));
        return template.findOne(query, CatalogProduct.class);
    }
}
~~~

Query này dùng tên property Java, nên `Sort.Order.asc("id")` được map sang BSON `_id`. Khi dùng `Criteria.where("stockQty")` sau này, Spring Data sẽ map sang `stock_qty` nhờ `@Field`. Query `findByIdInTenant` cố ý không dùng `findById(productId)` rồi kiểm tra tenant sau: filter tenant ngay tại database giảm nguy cơ truy cập nhầm tài nguyên.

### 11.1. Limit phải nằm trong query khi cần giới hạn server

`Flux.take(20)` có thể ngắt stream phía client sau 20 phần tử, nhưng nếu MongoDB phải sort quá nhiều document trước đó, chi phí server chưa chắc nhỏ. Đối với endpoint paging, nên đặt `query.limit(20)`, sort và index phù hợp để server hiểu giới hạn từ đầu.

### 11.2. Sort có tie-breaker

`createdAt DESC` một mình không bảo đảm thứ tự duy nhất nếu nhiều document có timestamp giống nhau. Thêm `id ASC` giúp thứ tự ổn định khi tập dữ liệu không đổi. Nếu cần keyset paging, cursor phải mang đủ tuple `(createdAt, id)`, không chỉ timestamp.

### 11.3. Không thu toàn bộ Flux vào List bừa bãi

~~~java
Mono<java.util.List<CatalogProduct>> all =
        template.find(new Query(), CatalogProduct.class)
                .collectList();
~~~

Truy vấn `new Query()` không lọc tenant và `collectList()` tích lũy toàn bộ document trong bộ nhớ; đây là **anti-pattern** nếu collection lớn/đa tenant. Hãy lọc và giới hạn tại database, stream/paginate hoặc thiết kế pipeline batch có kiểm soát.

## 12. Reactive conditional update: atomicity vẫn do MongoDB bảo vệ

Reactive không tự tạo atomicity lớn hơn imperative. Với tồn kho, chỉ cập nhật khi status ACTIVE và còn đủ:

**CatalogStockService.java**

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CatalogStockService {
    private final ReactiveMongoTemplate template;

    public CatalogStockService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Boolean> reserve(
            String authenticatedTenantId,
            String productId,
            long quantity) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || productId == null || productId.isBlank()
                || quantity <= 0) {
            return Mono.error(
                    new IllegalArgumentException("Request không hợp lệ"));
        }

        Query query = Query.query(
                Criteria.where("id").is(productId)
                        .and("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE")
                        .and("stockQty").gte(quantity));

        Update update = new Update()
                .inc("stockQty", -quantity);

        return template.updateFirst(
                query, update, CatalogProduct.class)
                .map(result -> result.getMatchedCount() == 1);
    }
}
~~~

MongoDB nhận một lệnh tương đương:

~~~javascript
db.catalog_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    status: "ACTIVE",
    stock_qty: { $gte: 3 }
  },
  { $inc: { stock_qty: -3 } }
);
~~~

Đây là một **single-document conditional update**. Hai request cùng trừ 3 khi stock ban đầu là 5 không thể cùng khớp nếu mọi writer dùng điều kiện phù hợp. `Mono<Boolean>` chỉ có giá trị khi Publisher được subscribe và lệnh có kết quả đã xác nhận.

### 12.1. Không tách read → check → write để “dễ hiểu”

Sai:

~~~java
return repository.findById(productId)
        .flatMap(product -> {
            if (product.stockQty() < quantity) {
                return Mono.just(false);
            }
            // Save một entity dựa trên giá trị đã đọc cũ:
            return repository.save(new CatalogProduct(
                    product.id(), product.tenantId(),
                    product.sku(), product.name(), product.status(),
                    product.stockQty() - quantity,
                    product.createdAt())).thenReturn(true);
        });
~~~

Hai streams cùng đọc stock cũ có thể ghi đè nhau khi entity không có version guard. `flatMap` chỉ giải quyết composition bất đồng bộ, **không tạo transaction** và không bảo vệ invariant nếu check nằm trước write.

### 12.2. Không retry $inc mù quáng

Nếu client mất kết nối sau khi server đã giảm tồn kho nhưng trước khi client nhận kết quả, application-level retry của toàn bộ `reserve` như một request mới có thể giảm lần hai. Reactive `retryWhen(...)` cũng không tự làm một business command idempotent.

Cần command ID và thiết kế idempotency phù hợp với phạm vi document/workflow. Đây là vấn đề **đúng đắn nghiệp vụ**, không phải lỗi riêng của API reactive.

### 12.3. @Version không tự bảo vệ mọi đường ghi

Nếu dùng entity có `@Version`, repository `save` có thể thực hiện optimistic locking theo cơ chế framework. Với raw/custom update hoặc update template tường minh, cần kiểm tra semantics version và đối chiếu BSON/`matchedCount`; không cho rằng mọi đường reactive update tự có cùng CAS version.

## 13. Lifecycle của ReactiveMongoClient và resource cleanup

MongoDB client không nên được tạo/hủy theo từng HTTP request. Mẫu `@Bean(destroyMethod = "close")` trong `ReactiveMongoConfig` đặt client vào vòng đời Spring context.

Khi ứng dụng shutdown:

1. Spring đóng application context.
2. Các bean dùng client ngừng nhận công việc mới và publishers đang chạy cần có chiến lược graceful shutdown.
3. `MongoClient.close()` giải phóng tài nguyên/kết nối.

**Lưu ý:** close client không phải một cơ chế transaction rollback nghiệp vụ cho mọi task đang pending. Nếu ứng dụng dừng giữa một workflow nhiều bước không transaction, phải có idempotency/reconciliation.

### 13.1. Connection pool cần được quản lý chung

Không mở một `MongoClient` cho từng repository/service. Dùng cùng Spring-managed reactive Mongo client, trừ khi dự án thật sự phân tách database/credential và có lý do vận hành rõ.

Khi pool quá nhỏ, request có thể đợi connection; khi pool quá lớn, server có thể chịu áp lực tài nguyên. Các options như max pool size, timeout, TLS, authentication cần được cấu hình/đo theo workload thay vì đoán một con số chung.

### 13.2. Reactive driver không phải HTTP client

Reactive MongoDB driver không có trách nhiệm quản lý security token HTTP, tenant context, API rate limits hoặc downstream services. Một service reactive phải giữ đúng authorization/filter và lifecycle ở tầng ứng dụng.

## 14. Chọn repository hay template?

| Yêu cầu | Reactive repository | ReactiveMongoTemplate |
|---|---|---|
CRUD/entity access đơn giản | Rất phù hợp | Cũng hỗ trợ |
Derived query theo property | `findByTenantIdAndSku` | Xây `Query` tường minh |
Query động nhiều điều kiện | Có thể cần custom implementation | Linh hoạt với `Criteria`/`Query` |
Aggregation | Có hỗ trợ một số annotation/query mechanisms | Thường linh hoạt hơn |
Atomic conditional update | Tùy repository method/custom update hỗ trợ | `updateFirst`/`findAndModify` rõ |
Index operations | Thường qua hạ tầng khác | `indexOps(...)` trả reactive publisher |
Một pipeline nghiệp vụ cần cả hai | Có thể phối hợp nếu cùng factory/session | Có thể phối hợp nếu cùng factory/session |

Không chọn `ReactiveMongoTemplate` chỉ vì “nhanh hơn repository”: cả hai cùng gọi driver/server và index/query shape mới là yếu tố lớn của hiệu năng. Repository giúp biểu đạt miền truy cập, template linh hoạt cho operations tùy chỉnh.

### 14.1. Cùng database không đồng nghĩa cùng transaction

Reactive repository và `ReactiveMongoTemplate` có thể dùng chung hạ tầng. Nhưng khi cần transaction nhiều document, phải đăng ký `ReactiveMongoTransactionManager`/`TransactionalOperator` và đảm bảo reactive flow cùng Reactor context. Chỉ vì hai method cùng được gọi trong một service không tự tạo transaction.

## 15. Spring Boot auto-config: khi nào không nên tự extends lớp cấu hình?

Trường hợp điển hình với Spring Boot:

~~~text
spring-boot-starter-data-mongodb-reactive
  + spring.data.mongodb.uri
  + @SpringBootApplication scan package
  + interface extends ReactiveMongoRepository

=> Boot thường có thể cấp reactive MongoClient,
   ReactiveMongoTemplate và repository proxies.
~~~

Trong trường hợp này, tự tạo thêm `ReactiveMongoConfig extends AbstractReactiveMongoConfiguration` đôi khi chỉ tăng độ phức tạp. Lợi ích của manual config rõ hơn khi:

- Không dùng Spring Boot.
- Phải tùy biến rất sâu về mapping/converter/template.
- Có nhiều template hoặc các repository nằm ở các database tách biệt.
- Cần kiểm soát tường minh base packages và bean references.
- Đang di chuyển kiến trúc từ client cũ sang reactive driver và cần migration có từng bước.

### 15.1. Một bảng phân biệt thuộc tính cấu hình

| Cấu hình | Ai đọc nó? |
|---|---|
`spring.data.mongodb.uri` | Spring Boot auto-configuration |
`app.mongodb.uri` | `ReactiveMongoConfig` trong bài, thông qua `@Value` |
`app.mongodb.database` | `getDatabaseName()` trong cấu hình thủ công |
`@EnableReactiveMongoRepositories` | Spring Data repository infrastructure |
`@Document(collection = "...")` | Spring Data mapping |
`@Field("stock_qty")` | MongoDB mapping converter |

Nếu sử dụng **cách B/manual** nhưng chỉ đặt `spring.data.mongodb.uri` trong YAML mà không cung cấp `app.mongodb.uri`, constructor của ví dụ có thể báo thiếu property. Đừng kết luận MongoDB server hỏng khi lỗi thực tế là **mismatch tên cấu hình**.

### 15.2. Không tạo trùng client/template beans

Khi có custom config trong ứng dụng Boot:

1. Kiểm tra các auto-configuration conditions đang match hay back off.
2. Liệt kê `MongoClient` reactive beans, `ReactiveMongoDatabaseFactory` và `ReactiveMongoTemplate`.
3. Nếu có bean tên giống nhau, kiểm tra bean override policy (Boot thường không khuyến khích override âm thầm).
4. Chọn một cấu hình và kiểm tra repository được inject đúng template.
5. Kiểm thử truy vấn thật vào **đúng database**, không chỉ thấy Spring context startup thành công.

Không dùng `@Primary` như một cách chữa tất cả bean conflict: nó chỉ ảnh hưởng injection preference, không giải quyết repository quét trùng hoặc resources dùng nhầm database.

### 15.3. Auto index creation không mặc định giải quyết lifecycle index

`@Indexed`/`@CompoundIndex` trên entity không chứng minh index tồn tại trên MongoDB. Với Spring Data MongoDB hiện đại, auto-index-creation thường không bật mặc định; application nên có quy trình migration/index provisioning rõ ràng.

Đặc biệt, một repository reactive không trở nên “nhanh” chỉ vì nó reactive. Query vẫn cần index phù hợp với equality, range, sort và tenant filters.

## 16. Nhiều database, nhiều ReactiveMongoTemplate và repository scanning

Trong hệ thống lớn, có thể có:

~~~text
Catalog repositories  -> catalogReactiveMongoTemplate  -> catalogdb
Reporting repositories -> reportReactiveMongoTemplate   -> reportdb
~~~

Nếu cả hai cùng là reactive repositories, phải cấu hình vùng scan và template reference riêng. `@EnableReactiveMongoRepositories` có tham số `reactiveMongoTemplateRef` để xác định template bean cụ thể.

Ví dụ ý tưởng dành cho một cấu hình report riêng:

~~~java
@Configuration
@EnableReactiveMongoRepositories(
        basePackageClasses = ReportingRepository.class,
        reactiveMongoTemplateRef = "reportReactiveMongoTemplate")
public class ReportRepositoryConfig {
    // Đăng ký reportReactiveMongoTemplate cùng
    // ReactiveMongoDatabaseFactory tương ứng ở config riêng.
}
~~~

Đây là **fragment kiến trúc**, yêu cầu project có `ReportingRepository` và bean `reportReactiveMongoTemplate` được định nghĩa. Không copy nó nguyên dạng để compile khi chưa có report domain.

### 16.1. Hai lỗi phổ biến

- Cả hai `@EnableReactiveMongoRepositories` quét cùng package → repository bean có thể bị tạo trùng hoặc dùng template không định trước.
- Repository A được nối tới template của database B → query trả rỗng/dữ liệu sai database; ứng dụng có thể khởi động bình thường nên lỗi khó phát hiện.

Nên đặt các repository theo package ổn định, ví dụ `com.example.catalog.repository` và `com.example.reporting.repository`, rồi dùng `basePackageClasses` tương ứng để refactor-safe.

### 16.2. Không tự coi hai database có chung reactive transaction

`ReactiveMongoTransactionManager` quản lý tài nguyên/session của factory được cung cấp. Hai client/factory thuộc hai MongoDB deployments không tự trở thành một distributed transaction chỉ vì cả hai được Spring quản lý.

Nếu business operation trải qua nhiều database/services, cần thiết kế transaction boundary, outbox, saga hoặc compensation phù hợp; đừng chỉ gắn `@Transactional` lên method rồi tin mọi thứ cùng rollback.

## 17. ReactiveMongoTransactionManager: liên hệ nhưng không trộn phạm vi

`AbstractReactiveMongoConfiguration` và `@EnableReactiveMongoRepositories` **chỉ cấu hình truy cập dữ liệu reactive**, không mặc định biến mọi thao tác repository thành transaction nhiều document.

Khi nghiệp vụ thực sự cần transaction nhiều document, có thể đăng ký:

**ReactiveMongoTransactionConfig.java**

~~~java
package com.example.catalog;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTransactionConfig {

    @Bean("reactiveMongoTransactionManager")
    public ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

MongoDB cần **replica set hoặc topology khác hỗ trợ transaction**, session/driver cùng database factory, đúng MongoDB version và quyền kết nối. Một MongoDB standalone không hỗ trợ đầy đủ multi-document transactions không trở thành transaction-capable chỉ bằng bean này.

### 17.1. TransactionalOperator dùng Reactor Context

Đối với reactive flow, Spring dùng **Reactor Context** thay vì chỉ thread-local context của imperative transaction manager. Ví dụ:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;

TransactionalOperator tx =
        TransactionalOperator.create(reactiveMongoTransactionManager);

Mono<Void> businessFlow = debitReactive()
        .then(creditReactive())
        .as(tx::transactional);
~~~

Ở fragment này, các method `debitReactive()`/`creditReactive()` trả Publisher thực sự dùng cùng reactive MongoDB factory và có xử lý lỗi đúng. Biến `reactiveMongoTransactionManager` là manager được inject. Đây không phải implementation chuyển tiền sẵn sàng production.

### 17.2. Mono tạo xong mà không subscribe: transaction cũng không chạy

~~~java
Mono<Void> flow = performReactiveWrites()
        .as(tx::transactional);

// Chưa có subscriber: không mặc định có write/commit.
~~~

Trong WebFlux, framework subscribe vào Publisher được handler trả về. Trong test, `StepVerifier` subscribe. Nếu code gọi một method trả `Mono<Void>` rồi bỏ kết quả, không nên cho rằng database writes đã hoàn tất.

### 17.3. @Transactional imperative khác reactive

| Đường truy cập | Manager phù hợp | Context |
|---|---|---|
`MongoTemplate` + `MongoRepository` | `MongoTransactionManager` | Imperative/thread-bound |
`ReactiveMongoTemplate` + `ReactiveMongoRepository` | `ReactiveMongoTransactionManager` | Reactive/Reactor Context |

Không dùng `MongoTransactionManager` để bao một `Mono` và mong driver reactive tự chia sẻ session với transaction imperative. Nếu ứng dụng dùng cả hai, chỉ định manager đúng loại và test rollback.

## 18. Index, giới hạn kết quả và backpressure

Reactive Streams cho phép subscriber yêu cầu số lượng phần tử theo **demand**. MongoDB reactive driver có thể fetch kết quả theo batch/cursor khi nhận demand, thay vì ứng dụng chủ động đọc tất cả một lượt. Nhưng điều này **không thay thế index, pagination hoặc giới hạn dữ liệu tại server**.

### 18.1. Index cho query tenant + SKU

Nếu mỗi tenant có một SKU duy nhất:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, sku: 1 },
  {
    name: "uq_product_tenant_sku",
    unique: true
  }
);
~~~

Unique compound index bảo vệ business key dưới concurrent inserts. `existsByTenantIdAndSku` rồi `save` **không thay unique index**.

### 18.2. Index cho sort newest ACTIVE

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: 1 },
  { name: "idx_product_tenant_status_created_id" }
);
~~~

Đây là ứng viên cho query tenant/status với sort `createdAt DESC, _id ASC`. Không tạo index theo mọi field chỉ vì có entity; cần `explain("executionStats")`/metrics theo workload thật.

### 18.3. Reactive index operations cũng là publisher

Trong Spring Data reactive:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;
import reactor.core.publisher.Mono;

Index index = new Index()
        .on("tenantId", Sort.Direction.ASC)
        .on("sku", Sort.Direction.ASC)
        .unique()
        .named("uq_product_tenant_sku");

Mono<String> indexCreation =
        template.indexOps(CatalogProduct.class)
                .ensureIndex(index);
~~~

`indexCreation` là publisher cần được **thực thi trong một migration/provisioning lifecycle có chủ đích**. Chỉ tạo `Mono<String>` mà không subscribe/await ở orchestrator **không đảm bảo index đã được tạo**.

Không block tùy tiện trên event-loop để tạo index mỗi request. Việc provisioning index nên thuộc quy trình deployment/test được quản lý, có xác minh unique conflict và permissions.

### 18.4. Backpressure không cứu một truy vấn không có index

Nếu server phải scan toàn bộ collection để tìm một vài document, reactive consumer yêu cầu 20 phần tử không làm chi phí server tự biến mất. Nếu code dùng `collectList()` trên hàng triệu document, vẫn có thể hết bộ nhớ. Các bước kiểm soát:

1. Có filter tenant và business predicates ở MongoDB.
2. Index phù hợp với filter/sort.
3. `limit`, paging/cursor hoặc batch processing tại server.
4. Chỉ lấy field cần thiết qua projection.
5. Đặt timeout, metrics và giới hạn lượng công việc theo API contract.

### 18.5. flatMap concurrency không phải transaction

~~~java
return Flux.fromIterable(commands)
        .flatMap(command -> applyOneCommand(command), 8);
~~~

Fragment này xử lý tối đa một mức concurrency theo operator, nhưng **không tạo atomicity cho 8 commands**. Nếu mỗi command tác động cùng một document, cần CAS/unique/idempotency; nếu muốn xử lý theo thứ tự, `concatMap` hoặc thiết kế queue có thể cần thiết. Không dùng `parallel()` chỉ để “tăng tốc mọi update” mà chưa đo contention/database capacity.

## 19. Giám sát và chẩn đoán reactive access

Một vấn đề reactive thường cần quan sát theo nhiều tầng:

| Triệu chứng | Điều cần kiểm tra |
|---|---|
Spring context không tạo repository | Package scan, `@EnableReactiveMongoRepositories`, repository interface |
Không inject được `ReactiveMongoTemplate` | Client/factory/template bean, auto-config conditions |
Publisher trả empty | Query filter, tenant, collection/database, mapping BSON |
Publisher báo lỗi khi subscribe | URI, authentication, network, schema, server timeout |
HTTP request treo | Thiếu subscription ở custom flow, blocking event-loop, DB latency |
CPU tăng | Query thiếu index, aggregation nặng, xử lý Java đắt |
Connection pool cạn | Client tạo nhiều, concurrency quá cao, tài nguyên đóng không đúng |
Timeout chỉ ở dữ liệu lớn | Cursor/batch size, index, sort, memory, read concern |
Write bị lặp sau retry | Cold Publisher resubscribed, idempotency, driver/application retries |
Reactive transaction không rollback | Manager sai loại, không cùng Reactor Context/session, topology |

### 19.1. Quan sát trên MongoDB

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20)
.explain("executionStats");
~~~

Theo dõi `totalKeysExamined`, `totalDocsExamined`, blocking `SORT`, `nReturned` và latency. Một Publisher reactive với query `COLLSCAN` tốn nhiều I/O vẫn có thể là bottleneck.

### 19.2. Logging phải tôn trọng privacy

MongoDB Driver `CommandListener` có thể giúp quan sát lệnh thực tế, nhưng BSON query có thể chứa tenant, SKU, tọa độ hoặc dữ liệu nhạy cảm. Trong integration test, ghi log có kiểm soát và không đưa raw query data lên production log theo mặc định.

### 19.3. Không che lỗi database bằng onErrorResume chung

Sai:

~~~java
return repository.findByTenantIdAndSku(tenantId, sku)
        .onErrorResume(anyError -> Mono.empty());
~~~

Cách này biến timeout/auth failure thành “không tìm thấy sản phẩm”. Caller không thể phân biệt lỗi hạ tầng với kết quả rỗng hợp lệ. Hãy xử lý theo **loại lỗi cụ thể**, đảm bảo logging/metrics và giữ semantics của API.

## 20. Kiểm thử cấu hình: context phải tạo đúng bean

Với cấu hình manual, nên có integration test kiểm chứng:

- Spring context tạo được `com.mongodb.reactivestreams.client.MongoClient`.
- Bean `ReactiveMongoTemplate` có thể inject.
- `@EnableReactiveMongoRepositories` tìm thấy `CatalogProductRepository`.
- Repository proxy dùng đúng database/collection và converter.
- Một Publisher thực sự thực hiện đọc/ghi khi được subscribe.

**Đừng chỉ kiểm tra rằng `@Configuration` có mặt trong source.** Annotation tồn tại không chứng minh URI đúng, bean được chọn đúng, repository đã scan hay MongoDB server hoạt động.

### 20.1. Môi trường test

Đối với ví dụ, cần một MongoDB test riêng. Có thể dùng Testcontainers hoặc một MongoDB local chuyên biệt cho test:

~~~yaml
# Cấu hình chỉ dành cho test, không dùng dữ liệu thật.
app:
  mongodb:
    uri: "mongodb://localhost:27017"
    database: "catalog_reactive_test"
~~~

Không giả định `@SpringJUnitConfig` hoặc `@DataMongoTest` tự khởi động `mongod`. Bài dùng `@SpringJUnitConfig` để rõ hạ tầng manual, với `@TestPropertySource` ghi đè properties; MongoDB test phải được chạy độc lập hoặc cung cấp qua Testcontainers.

**Lưu ý:** các test xóa collection data của `catalog_reactive_test` để seed. Không trỏ URI này vào database dùng chung/production.

### 20.2. Test context + reactive bean wiring

**ReactiveMongoWiringIntegrationTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.reactivestreams.client.MongoClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        ReactiveMongoConfig.class,
        CatalogQueryService.class,
        CatalogTemplateQueryService.class,
        CatalogStockService.class
})
@TestPropertySource(properties = {
        "app.mongodb.uri=mongodb://localhost:27017",
        "app.mongodb.database=catalog_reactive_test"
})
class ReactiveMongoWiringIntegrationTest {

    @Autowired MongoClient reactiveClient;
    @Autowired ReactiveMongoTemplate template;
    @Autowired CatalogProductRepository repository;
    @Autowired CatalogQueryService queryService;
    @Autowired CatalogStockService stockService;

    @Test
    void allReactiveBeansAreAvailable() {
        assertThat(reactiveClient).isNotNull();
        assertThat(template).isNotNull();
        assertThat(repository).isNotNull();
        assertThat(queryService).isNotNull();
        assertThat(stockService).isNotNull();
    }
}
~~~

Test này chỉ chứng minh **Spring bean wiring**; vì chưa subscribe vào MongoDB operation, nó **chưa chứng minh server thực sự truy vấn được**. Bước tiếp theo dùng `StepVerifier` và MongoDB test thực.

## 21. Kiểm thử repository, template và concurrency bằng StepVerifier

`StepVerifier` thuộc `reactor-test` và subscribe vào Publisher, quan sát `onNext`, `onComplete` và `onError`. Đây là cách kiểm thử reactive flow mà không lồng `block()` trong application service.

### 21.1. Test suite trên MongoDB thật

**CatalogReactiveIntegrationTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.reactivestreams.client.MongoClient;
import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringJUnitConfig(classes = {
        ReactiveMongoConfig.class,
        CatalogQueryService.class,
        CatalogTemplateQueryService.class,
        CatalogStockService.class
})
@TestPropertySource(properties = {
        "app.mongodb.uri=mongodb://localhost:27017",
        "app.mongodb.database=catalog_reactive_test"
})
class CatalogReactiveIntegrationTest {

    @Autowired CatalogProductRepository repository;
    @Autowired CatalogQueryService queryService;
    @Autowired CatalogTemplateQueryService templateService;
    @Autowired CatalogStockService stockService;
    @Autowired ReactiveMongoTemplate template;
    @Autowired MongoClient reactiveClient;

    private CatalogProduct product(
            String id,
            String tenant,
            String sku,
            String status,
            long stock,
            String createdAt) {
        return new CatalogProduct(
                id,
                tenant,
                sku,
                "Product " + id,
                status,
                stock,
                Instant.parse(createdAt));
    }

    @BeforeEach
    void cleanCollection() {
        // Chỉ dành cho database test cô lập.
        StepVerifier.create(repository.deleteAll())
                .verifyComplete();
    }

    @Test
    void reactiveRepositoryWasScannedAndCanQuery() {
        CatalogProduct source = product(
                "p-101", "tenant-a", "BOTTLE-500", "ACTIVE", 12,
                "2026-11-20T08:00:00Z");

        StepVerifier.create(
                repository.save(source)
                        .then(queryService.findBySku(
                                "tenant-a", "BOTTLE-500")))
                .assertNext(saved -> {
                    assertThat(saved.id()).isEqualTo("p-101");
                    assertThat(saved.stockQty()).isEqualTo(12L);
                    assertThat(saved.tenantId()).isEqualTo("tenant-a");
                })
                .verifyComplete();
    }

    @Test
    void notFoundIsReportedAsDomainError() {
        StepVerifier.create(
                queryService.findBySku("tenant-a", "MISSING"))
                .expectError(CatalogProductNotFoundException.class)
                .verify();
    }

    @Test
    void querySortAndTenantIsolationAreCorrect() {
        List<CatalogProduct> fixtures = List.of(
                product("p-101", "tenant-a", "SKU-1", "ACTIVE", 12,
                        "2026-11-20T08:00:00Z"),
                product("p-102", "tenant-a", "SKU-2", "ACTIVE", 9,
                        "2026-11-20T09:00:00Z"),
                product("p-103", "tenant-a", "SKU-3", "DRAFT", 1,
                        "2026-11-20T10:00:00Z"),
                product("p-201", "tenant-b", "SKU-4", "ACTIVE", 7,
                        "2026-11-20T11:00:00Z")
        );

        StepVerifier.create(
                repository.saveAll(fixtures)
                        .thenMany(templateService.newestActive(
                                "tenant-a", 10))
                        .map(CatalogProduct::id))
                .expectNext("p-102", "p-101")
                .verifyComplete();
    }

    @Test
    void concurrentConditionalUpdatesDoNotOversell() {
        CatalogProduct source = product(
                "p-101", "tenant-a", "BOTTLE-500", "ACTIVE", 5,
                "2026-11-20T08:00:00Z");

        StepVerifier.create(
                repository.save(source)
                        .then(Mono.zip(
                                stockService.reserve(
                                        "tenant-a", "p-101", 3),
                                stockService.reserve(
                                        "tenant-a", "p-101", 3)))
                        .flatMap(pair -> repository.findById("p-101")
                                .map(saved -> new ReservationOutcome(
                                        pair.getT1(),
                                        pair.getT2(),
                                        saved.stockQty()))))
                .assertNext(result -> {
                    // Thứ tự request thắng không được giả định.
                    assertThat(result.first() ^ result.second()).isTrue();
                    assertThat(result.stock()).isEqualTo(2L);
                })
                .verifyComplete();
    }

    @Test
    void fieldAnnotationIsAppliedToBson() {
        CatalogProduct source = product(
                "p-101", "tenant-a", "BOTTLE-500", "ACTIVE", 12,
                "2026-11-20T08:00:00Z");

        Mono<Document> rawById = Mono.from(
                reactiveClient.getDatabase("catalog_reactive_test")
                        .getCollection("catalog_products")
                        .find(new Document("_id", "p-101"))
                        .first());

        StepVerifier.create(
                repository.save(source).then(rawById))
                .assertNext(raw -> {
                    assertThat(raw.containsKey("stock_qty")).isTrue();
                    assertThat(raw.containsKey("stockQty")).isFalse();
                    assertThat(raw.get("stock_qty"))
                            .isInstanceOf(Number.class);
                    assertThat(((Number) raw.get("stock_qty"))
                            .longValue()).isEqualTo(12L);
                })
                .verifyComplete();
    }

    private record ReservationOutcome(
            boolean first, boolean second, long stock) {
    }
}
~~~

### 21.2. Test StepVerifier chứng minh gì?

- `repository.save(...)`/`findBy...` thực sự truy cập MongoDB khi được subscribe.
- `@EnableReactiveMongoRepositories` đã đăng ký proxy đúng interface.
- `ReactiveMongoTemplate` áp dụng filter tenant và sort đúng.
- Hai conditional updates cạnh tranh cùng stock=5, mỗi update trừ 3: **chỉ một match** và tồn kho cuối là 2.
- `@Field("stock_qty")` tạo tên BSON vật lý đúng; raw driver read xác minh.
- `Mono.empty` được xử lý thành domain exception theo contract.

### 21.3. Test chưa chứng minh những gì?

Vài document trên một MongoDB local không đủ kết luận:

- Query được tối ưu bằng index; server có thể chọn collection scan trên tập nhỏ.
- Bảo đảm idempotency cho retry sau timeout.
- Throughput dưới tải lớn hoặc backpressure/cursor behavior ở hàng triệu document.
- Reactive transaction rollback đa document; cần replica set và `ReactiveMongoTransactionManager`.
- Tính đúng đắn của authorization ở HTTP layer: service test chỉ dùng giá trị tenant truyền vào.

Với API đa tenant, cần thêm security integration test chứng minh principal chỉ lấy được tenant có quyền, không phải tenant do client tự khai báo.

### 21.4. Không chạy test này trên database dùng chung

`repository.deleteAll()` trong `@BeforeEach` xóa toàn bộ document của collection test. Nếu nhiều test song song dùng cùng database, có thể xảy ra race và test flaky. Dùng database riêng, tên collection riêng hoặc cơ chế cô lập phù hợp; không trỏ test vào production.

### 21.5. Khi dùng Testcontainers

Với một Testcontainers MongoDB:

1. Chạy container MongoDB phiên bản phù hợp.
2. Lấy connection string mà container thực sự cung cấp.
3. Đăng ký property `app.mongodb.uri` trước khi Spring tạo `ReactiveMongoConfig`, ví dụ qua `@DynamicPropertySource`.
4. Giữ database test được cô lập.
5. Để Testcontainers quản lý vòng đời server và dọn resource sau test.

Đừng hard-code `localhost:27017` nếu MongoDB test thực tế được expose ra port ngẫu nhiên. Bài hiển thị URI cố định để đơn giản khi test với MongoDB local đã chạy sẵn.

## 22. Những lỗi cấu hình và sử dụng thường gặp

| Sai lầm/triệu chứng | Vì sao xảy ra | Cách xử lý |
|---|---|---|
Kế thừa `AbstractReactiveMongoConfiguration` nhưng trả sync `MongoClient` | Type driver không khớp reactive infrastructure | Import `com.mongodb.reactivestreams.client.MongoClient` |
Chỉ thêm `@EnableReactiveMongoRepositories` và mong nó tự chạy MongoDB | Annotation chỉ kích hoạt repository scanning | Cấu hình client/factory/template và MongoDB server |
Không thấy repository bean | Package không nằm trong vùng scan | Dùng `basePackageClasses` đúng package |
Dùng `@EnableMongoRepositories` cho reactive interface | Imperative vs reactive repository infrastructure | Dùng `@EnableReactiveMongoRepositories` |
Service không được inject | Repository được scan nhưng `@Service` nằm ngoài component scan | Điều chỉnh component scan/import bean |
Không có `ReactiveMongoTemplate` | Thiếu starter, factory/client hoặc auto-config bị vô hiệu | Kiểm tra context và cấu hình |
Thiếu `app.mongodb.uri` khi dùng config manual | Nhầm property của Boot với property custom | Cung cấp đúng property cho `@Value` |
Tạo trùng client/template/repository beans | Kết hợp manual config và Boot scan vô tội vạ | Chọn một strategy, xem auto-config conditions |
Lấy MongoClient bằng cách `new` mỗi request | Pool và tài nguyên bị nhân lên | Spring-managed singleton bean |
Ứng dụng gọi `Mono` rồi bỏ kết quả | Không có subscriber nên operation chưa chạy | Return Publisher hoặc subscribe ở boundary rõ |
Gọi `subscribe()` bên trong service | Lỗi/transaction/cancellation bị tách khỏi caller | Compose `Mono`/`Flux` và trả về |
Gọi `block()` trong WebFlux handler | Block event-loop, tăng latency hoặc lỗi runtime | Dùng `flatMap`/`map`/`then` |
Tưởng `Mono.empty` là null | Logic lỗi/404 không chạy như mong muốn | Dùng `switchIfEmpty` theo contract |
`onErrorResume` tất cả lỗi thành empty | Che lỗi mạng/auth như “không có dữ liệu” | Phân loại exception và giữ semantics |
Gọi inherited `findAll()` trong tenant API | Rò dữ liệu của tenant khác | Chỉ truy vấn tenant đã được authorize |
Truy vấn typed dùng tên BSON trong derived method | Sai property resolution | Derived method dùng tên Java property |
Raw BSON tự dùng tên property Java | Không tự được map đúng trong mọi raw stage | Dùng tên BSON thực, kiểm tra command |
Lấy kết quả từ DB khác dự kiến | URI, `getDatabaseName()` hoặc template reference sai | Assert database/collection ở integration test |
Đọc toàn bộ `Flux` bằng `collectList()` | Tích lũy quá nhiều document | Filter/limit/project/paginate tại server |
Sort theo createdAt không có tie-breaker | Paging thiếu ổn định | Thêm `id`, cursor đủ khóa |
Cho rằng reactive tự bảo vệ concurrent updates | Lost update hoặc oversell | CAS/filter và atomic update |
Retry `$inc` mà không có command ID | Ghi lặp khi request/commit outcome không rõ | Idempotency/reconciliation |
Nhầm `MongoTransactionManager` với reactive manager | Không chia sẻ đúng session context | `ReactiveMongoTransactionManager` |
Reactive transaction trên standalone | Server không hỗ trợ multi-document transactions | Dùng replica set test/topology tương thích |
Chỉ unit test mock Mongo client | Không chứng minh mapping/server behavior | Integration test + `StepVerifier` |
Test `deleteAll()` trên database dùng chung | Xóa dữ liệu ngoài ý muốn | Database test cô lập |
Thấy bean tạo được rồi tin query sẽ chạy | Publisher chưa subscribe, URI có thể sai | Test subscribe và assert kết quả MongoDB |

### 22.1. Checklist chẩn đoán startup

Khi ứng dụng báo `NoSuchBeanDefinitionException` hoặc `BeanCreationException` liên quan MongoDB reactive:

1. Có `spring-boot-starter-data-mongodb-reactive` hoặc dependencies tương thích chưa?
2. `MongoClient` import có đúng reactive streams package?
3. `ReactiveMongoConfig` có được Spring import/scan không?
4. `getDatabaseName()` có tên DB thực tế và đủ quyền?
5. `@EnableReactiveMongoRepositories` có quét đúng repository package?
6. Repository interface có extends `ReactiveMongoRepository` không?
7. Có nhiều template beans, template reference có chọn đúng bean không?
8. Boot auto-configuration có bị custom config thay thế hoặc tạo trùng không?
9. Khi subscribe, lỗi là lỗi MongoDB network/auth/schema hay lỗi bean wiring?
10. Một integration test trên DB cô lập có đọc/ghi thành công không?

Phân biệt **lỗi khởi động context** với **lỗi runtime khi subscribe**. Một số Publisher được tạo thành công nhưng lỗi kết nối/auth chỉ xuất hiện khi operation thực sự được thực thi.

## 23. Bài tập thực hành

**Bài 1 — Boot tự động.** Tạo ứng dụng Spring Boot có `spring-boot-starter-data-mongodb-reactive`, `spring.data.mongodb.uri` và `@SpringBootApplication`. Tạo `ReactiveMongoRepository` rồi viết test xác minh truy vấn chạy khi subscribe. Ghi lại những bean auto-configuration đã tạo.

**Bài 2 — Manual config.** Thay con đường auto-config bằng `ReactiveMongoConfig extends AbstractReactiveMongoConfiguration` nhận URI và database name từ properties. Xác minh `reactiveMongoClient()` dùng reactive driver đúng package.

**Bài 3 — Quét repository.** Đặt repository ở một package khác class cấu hình. Thử thiếu scan rồi dùng `@EnableReactiveMongoRepositories(basePackageClasses = ...)` để đăng ký đúng proxy.

**Bài 4 — Base packages vs templateRef.** Tạo hai nhóm repository/reporting có template riêng trên hai database test. Chỉ định `reactiveMongoTemplateRef` và chứng minh dữ liệu không bị truy vấn nhầm database.

**Bài 5 — Mono và empty.** Viết `findByTenantIdAndSku` trả `Mono<CatalogProduct>`; với SKU không tồn tại, dùng `switchIfEmpty` tạo domain exception. Kiểm tra bằng `StepVerifier.expectError`.

**Bài 6 — Flux và sort.** Liệt kê sản phẩm ACTIVE của tenant, sắp `createdAt DESC, id ASC`. Dùng `ReactiveMongoTemplate` với `limit=20` và kiểm tra index ứng viên bằng `explain`.

**Bài 7 — Mapping Java → BSON.** Đặt `@Field("stock_qty")` lên `stockQty`. Ghi entity bằng repository reactive, đọc lại bằng native reactive driver và xác minh BSON chỉ chứa `stock_qty`.

**Bài 8 — Không block.** Chuyển một service đang gọi `.block()` thành chuỗi `map`/`flatMap`/`then`. Giải thích tại sao subscription nên thuộc WebFlux framework hoặc boundary điều phối rõ ràng.

**Bài 9 — Không subscribe fire-and-forget.** Viết một ví dụ sai gọi `repository.save(...).subscribe()` trong service rồi trả `Mono.empty()`. Sửa thành một Publisher caller có thể await, cancel và nhận lỗi.

**Bài 10 — Conditional update.** Seed stock=5, gọi hai `reserve(..., 3)` reactive đồng thời. Assert đúng một kết quả true và stock cuối là 2. Giải thích vì sao `flatMap` sau một lần đọc stock không thay được update có điều kiện.

**Bài 11 — Error handling.** Mô phỏng MongoDB không kết nối được. So sánh `switchIfEmpty` với `onErrorResume`; không được biến timeout/auth failure thành 404.

**Bài 12 — Bounded result.** Seed hàng chục nghìn sản phẩm. So sánh query có index và `Query.limit(20)` với `collectList()` không limit. Đo memory, latency và số docs examined.

**Bài 13 — Reactive transaction.** Trên MongoDB replica set test, cấu hình `ReactiveMongoTransactionManager` rồi dùng `TransactionalOperator` bao hai write. Chủ động gây lỗi ở write thứ hai và xác minh rollback của write đầu.

**Bài 14 — Security tenant.** Cho principal tenant-a cố ý gọi SKU của tenant-b. Xác minh service không trả dữ liệu và mọi query có filter tenant từ auth context.

**Bài 15 — Testcontainers.** Thay MongoDB local `localhost:27017` trong test bằng Testcontainers và `@DynamicPropertySource`. Kiểm tra vòng đời client và database test được cô lập giữa các suite.

**Bài 16 — Hiệu năng.** Viết load test với `Flux.flatMap` concurrency 1, 8 và 32 cho các query độc lập. Đo throughput, p95, connection usage và DB CPU; giải thích tại sao tăng concurrency vô hạn có thể gây chậm.

## 24. Ghi nhớ

**`AbstractReactiveMongoConfiguration`** giúp cấu hình **MongoDB Reactive Streams client**, database factory, converter và `ReactiveMongoTemplate` một cách tường minh khi ứng dụng cần manual configuration. Hai điểm override then chốt là `reactiveMongoClient()` và `getDatabaseName()`; client phải thuộc package `com.mongodb.reactivestreams.client`, là Spring-managed bean có vòng đời phù hợp và kết nối vào đúng database.

**`@EnableReactiveMongoRepositories`** kích hoạt **repository scanning/proxies** cho những interface kế thừa `ReactiveMongoRepository`. Dùng `basePackageClasses`/`basePackages` để quét đúng vùng repository; dùng `reactiveMongoTemplateRef` khi có nhiều template. Annotation này **không tự chạy MongoDB server, không tự cấp quyền tenant và không mở transaction**.

Trong **Spring Boot**, nên kiểm tra khả năng **auto-configuration** trước khi tạo hạ tầng thủ công: một starter và `spring.data.mongodb.uri` có thể đã cung cấp đầy đủ các bean cần thiết. Không trộn manual config với Boot config một cách vô tình.

Cuối cùng, **`Mono`/`Flux` là các publisher cần subscription**: hãy return/compose reactive pipelines thay vì `block()` hoặc `subscribe()` tùy tiện. Tối ưu bằng filter/index/limit tại server, bảo vệ concurrent writes bằng conditional updates/idempotency, chọn `ReactiveMongoTransactionManager` cho transaction reactive, và **xác minh bean wiring lẫn hành vi thực tế bằng `StepVerifier` trên MongoDB test được cô lập**.
