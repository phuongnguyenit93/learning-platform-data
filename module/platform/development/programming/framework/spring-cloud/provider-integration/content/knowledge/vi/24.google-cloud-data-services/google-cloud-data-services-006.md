# Repository Firestore reactive và truy cập Datastore theo thư viện tương ứng

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot kết nối các dịch vụ managed của AWS, Azure và Google Cloud thông qua các thư viện Spring Cloud tương ứng. Với dữ liệu document trên Google Cloud, ứng dụng có thể dùng Firestore Native mode hoặc Firestore in Datastore mode. Hai mode có API và data model khác nhau nên Spring cung cấp hai hướng tích hợp riêng.

Bài học tập trung vào cách viết code và tổ chức tầng truy cập dữ liệu:

1. Chọn đúng starter theo database mode.
2. Ánh xạ POJO Firestore bằng `@Document`, `@DocumentId` và `@PropertyName`.
3. Xây dựng `FirestoreReactiveRepository` với `Mono`, `Flux`, query methods và paging.
4. Kết hợp reactive pipeline trong service/WebFlux mà không chặn event loop.
5. Dùng `FirestoreTemplate`/`FirestoreReactiveOperations` cho query và subcollection.
6. Dùng `ReactiveFirestoreTransactionManager` và `TransactionalOperator` cho reactive transaction.
7. Ánh xạ Datastore mode bằng `@Entity`, `@Id`, `@Field` và `@Unindexed`.
8. Xây dựng `DatastoreRepository`, custom GQL, `DatastoreTemplate` và transaction.
9. Hiểu giới hạn query, index, delete và transaction của từng integration.
10. Kiểm thử bằng emulator và xác minh quyền truy cập bằng runtime identity.

> **Phạm vi:** Ví dụ tham chiếu Spring Framework on Google Cloud 8.2.1. Nhánh 8.x tương thích Spring Boot 4.0/4.1; hãy chọn BOM phù hợp với phiên bản Spring Boot thực tế. Firestore reactive repository dành cho Native mode. Spring Data Cloud Datastore dành cho Datastore mode và không tương thích Native mode.

## 1. Hai API, hai repository abstraction

### 1.1. Kiến trúc tích hợp

~~~mermaid
flowchart TD
    SERVICE["Spring service layer"] --> NATIVE{"Database mode"}
    NATIVE -->|"Firestore Native"| F_REPO["FirestoreReactiveRepository"]
    NATIVE -->|"Datastore mode"| D_REPO["DatastoreRepository"]
    F_REPO --> F_TEMPLATE["FirestoreTemplate / FirestoreReactiveOperations"]
    D_REPO --> D_TEMPLATE["DatastoreTemplate"]
    F_TEMPLATE --> F_CLIENT["Firestore Java client"]
    D_TEMPLATE --> D_CLIENT["Datastore Java client"]
    F_CLIENT --> F_DB["Firestore Native database"]
    D_CLIENT --> D_DB["Firestore Datastore mode database"]
    ADC["ADC + runtime service account"] --> F_CLIENT
    ADC --> D_CLIENT
~~~

| Thành phần | Firestore Native | Datastore mode |
| --- | --- | --- |
| Starter repository | spring-cloud-gcp-starter-data-firestore | spring-cloud-gcp-starter-data-datastore |
| Repository | FirestoreReactiveRepository<T> | DatastoreRepository<T, ID> |
| Return type chính | Reactor Mono<T>, Flux<T> | Java object, Iterable, List, Optional, Page, Slice |
| Template | FirestoreTemplate, FirestoreReactiveOperations | DatastoreTemplate, DatastoreOperations |
| Query | Firestore query API; query methods theo convention | Datastore query/GQL; query methods theo convention |
| Transaction | Reactive transaction manager/operator | DatastoreTransactionManager hoặc performTransaction |
| Client bean | Firestore | Datastore |

Không dùng repository của mode này để truy cập mode kia. Khi project có nhiều database hoặc nhiều integration, cấu hình database ID và transaction manager tường minh để tránh kết nối nhầm.

### 1.2. Chọn starter theo nhu cầu

- Cần Firestore Native và Spring Data reactive repository/template: dùng spring-cloud-gcp-starter-data-firestore.
- Chỉ cần Firestore Java client và không cần Spring Data: dùng spring-cloud-gcp-starter-firestore.
- Cần Datastore mode và Spring Data repository/template: dùng spring-cloud-gcp-starter-data-datastore.
- Cần Datastore Java client trực tiếp: starter Datastore vẫn tự cấu hình bean Datastore; có thể dùng client này trong service chuyên biệt.

Không thêm đồng thời nhiều starter chỉ để có nhiều cách gọi. Mỗi starter có thể tạo client và transaction infrastructure riêng; chỉ thêm module thực sự được ứng dụng sử dụng.

## 2. Dependency và cấu hình chung

### 2.1. Quản lý version bằng BOM

Với Maven, import BOM một lần ở dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Chọn giá trị spring-cloud-gcp.version theo compatibility matrix của Spring Boot và Spring Framework on Google Cloud. Ví dụ dưới đây không khai báo version riêng vì BOM quản lý các module tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-data-firestore</artifactId>
    </dependency>
</dependencies>
~~~

Để dùng Datastore mode, thay dependency Firestore bằng:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-datastore</artifactId>
</dependency>
~~~

Nếu một ứng dụng thực sự cần cả hai mode, có thể khai báo cả hai starter. Tuy nhiên, hãy tách package repository/entity, database ID, cấu hình và transaction boundary để tránh trộn domain type hoặc chọn sai transaction manager.

### 2.2. ADC và project ID

Cả hai starter sử dụng Google Cloud core auto-configuration để tìm project ID và credentials. Trong local development, dùng Application Default Credentials. Trên Cloud Run, GKE hoặc Compute Engine, gắn service account/workload identity vào workload.

Ví dụ cấu hình project:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-platform-dev
~~~

Không commit service account key JSON vào source, image hoặc file cấu hình. Ưu tiên runtime identity; chỉ dùng credentials riêng theo property khi có yêu cầu rõ ràng và được quản lý an toàn.

## 3. Firestore Native: cấu hình và ánh xạ document

### 3.1. Cấu hình Firestore

Các property thường dùng:

| Property | Ý nghĩa |
| --- | --- |
| spring.cloud.gcp.firestore.enabled | Bật/tắt Firestore auto-configuration |
| spring.cloud.gcp.firestore.project-id | Project chứa Firestore database |
| spring.cloud.gcp.firestore.database-id | Database ID; mặc định là (default) |
| spring.cloud.gcp.firestore.emulator.enabled | Bật kết nối emulator |
| spring.cloud.gcp.firestore.host-port | Host/port của Firestore hoặc emulator |
| spring.cloud.gcp.firestore.credentials.location | Credentials riêng nếu khác cấu hình core |
| spring.cloud.gcp.firestore.credentials.encoded-key | Credentials JSON đã base64 nếu có lý do phải cấu hình riêng |

Ví dụ production/local profile:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-platform-dev
      firestore:
        project-id: rental-platform-dev
        database-id: "(default)"
        emulator:
          enabled: false
        host-port: firestore.googleapis.com:443
~~~

Khi dùng emulator đang chạy sẵn, bật emulator.enabled và trỏ host-port tới host/port emulator. Không bật emulator trong production.

### 3.2. POJO document

Spring Data Cloud Firestore ánh xạ POJO vào collection/document. Annotation quan trọng:

- @Document(collectionName = "..."): chỉ định collection.
- @DocumentId: đánh dấu document ID; field này phải có kiểu String.
- @PropertyName: ánh xạ tên property lưu trữ.
- @UpdateTime: nhận update timestamp do Firestore quản lý.

Ví dụ:

~~~java
import com.google.cloud.Timestamp;
import com.google.cloud.firestore.annotation.PropertyName;
import com.google.cloud.firestore.annotation.DocumentId;
import com.google.cloud.spring.data.firestore.Document;
import com.google.cloud.spring.data.firestore.mapping.UpdateTime;

import java.util.List;

@Document(collectionName = "orders")
public class OrderDocument {

    @DocumentId
    private String id;

    private String customerId;

    private String status;

    private Long totalAmount;

    private Timestamp createdAt;

    @UpdateTime(version = true)
    private Timestamp updateTime;

    private List<String> tags;

    public OrderDocument() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    @PropertyName("customer_id")
    public String getCustomerId() {
        return customerId;
    }

    @PropertyName("customer_id")
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Long getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(Long totalAmount) {
        this.totalAmount = totalAmount;
    }
}
~~~

Nếu id là null, Firestore tạo document ID khi entity được lưu. Sau khi save thành công, giữ ID được trả về trong entity để các thao tác sau truy cập đúng document. Không dùng kiểu Long cho @DocumentId; Firestore mapping yêu cầu String.

@PropertyName có thể đặt trên field public hoặc getter/setter. Khi đặt trên accessor, áp dụng nhất quán cho cả getter và setter để serialize/deserialize cùng tên field.

### 3.3. Kiểu dữ liệu và embedded object

Các kiểu thường được hỗ trợ gồm String, Long, Integer, Double, Float, Boolean, Character, Date, Map, List, Enum, com.google.cloud.Timestamp, GeoPoint và Blob.

Custom POJO và list của custom POJO được lưu thành embedded map/array. Ví dụ:

~~~java
public class ShippingAddress {

    private String street;
    private String city;
    private String country;

    public ShippingAddress() {
    }

    // Getters and setters.
}

@Document(collectionName = "orders")
public class OrderDocument {

    @DocumentId
    private String id;

    private ShippingAddress shippingAddress;

    private List<ShippingAddress> previousAddresses;

    public OrderDocument() {
    }
}
~~~

Embedded object phù hợp với dữ liệu nhỏ, thường đọc cùng document cha. Với danh sách tăng không giới hạn, cần query độc lập hoặc vòng đời riêng, hãy dùng subcollection thay vì một array ngày càng lớn.

### 3.4. Kiểm soát update timestamp

Firestore tự quản lý update time cho document. Field @UpdateTime nhận timestamp đó sau thao tác ghi. Khi dùng @UpdateTime(version = true), Spring Data thêm precondition để bảo đảm document chưa bị thay đổi kể từ lần đọc trước.

Đây là optimistic locking ở mức document. Nếu hai request cùng đọc một version rồi cùng ghi, request thứ hai có thể bị từ chối do version không còn khớp. Hãy xử lý conflict bằng cách đọc lại và quyết định nghiệp vụ; không retry mù quáng một giá trị đã tính trên snapshot cũ.

## 4. FirestoreReactiveRepository

### 4.1. Khai báo repository

Spring Data Cloud Firestore cung cấp FirestoreReactiveRepository<T>, mở rộng reactive CRUD repository:

~~~java
import com.google.cloud.spring.data.firestore.FirestoreReactiveRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderDocumentRepository
        extends FirestoreReactiveRepository<OrderDocument> {

    Flux<OrderDocument> findByCustomerId(String customerId);

    Flux<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);

    Flux<OrderDocument> findByStatusOrderByCreatedAtDesc(String status);

    Flux<OrderDocument> findByTotalAmountGreaterThan(Long minimum);

    Mono<OrderDocument> findFirstByCustomerIdAndStatus(
            String customerId, String status);

    Mono<Long> countByStatus(String status);
}
~~~

Repository không cần viết implementation. Spring Boot starter tự bật reactive repository scanning. Nếu cần tùy chỉnh package scan, dùng @EnableReactiveFirestoreRepositories.

### 4.2. Mono và Flux biểu đạt điều gì?

| Return type | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Mono<OrderDocument> | Không hoặc một document | findById, findFirstBy... |
| Flux<OrderDocument> | Không hoặc nhiều document | findByStatus, findAll |
| Mono<Long> | Một giá trị đếm | countByStatus |
| Mono<Void> | Hoàn tất mà không trả payload | deleteById, service command |

Reactive repository trả về publisher. Database call thường được thực thi khi publisher được subscribe, vì vậy việc gọi method chỉ tạo pipeline; nó chưa nhất thiết đã chạy query.

Trong WebFlux, controller/service nên trả tiếp Mono/Flux để runtime điều phối. Không gọi block() trong request path vì thao tác này chặn thread đang xử lý reactive pipeline.

### 4.3. CRUD trong service

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderDocumentService {

    private final OrderDocumentRepository repository;

    public OrderDocumentService(OrderDocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<OrderDocument> create(OrderDocument order) {
        return repository.save(order);
    }

    public Mono<OrderDocument> findById(String id) {
        return repository.findById(id);
    }

    public Mono<Void> delete(String id) {
        return repository.deleteById(id);
    }
}
~~~

Lưu ý semantics ghi: API FirestoreTemplate.save hiện hành có hành vi insert-only; saveAll ghi theo semantics insert/update và không atomic trên toàn publisher. Khi gọi qua repository, hãy kiểm tra implementation của đúng BOM và không mặc định ReactiveCrudRepository.save có upsert semantics như JPA. Nếu cần update một document đã tồn tại, dùng saveAll cho thao tác đơn lẻ có optimistic locking hoặc native client update/set merge; kiểm thử precondition trước khi triển khai. Không mặc định save tương đương upsert của DatastoreTemplate.

### 4.4. Kết hợp nhiều thao tác reactive

Ví dụ tạo order rồi đọc lại:

~~~java
public Mono<OrderDocument> createAndReload(OrderDocument order) {
    return repository.save(order)
            .flatMap(saved -> repository.findById(saved.getId()));
}
~~~

Ví dụ tìm order, kiểm tra trạng thái và upsert document qua saveAll:

~~~java
public Mono<Void> markPacked(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Order not found")))
            .flatMap(order -> {
                if (!"PAID".equals(order.getStatus())) {
                    return Mono.error(
                            new IllegalStateException("Order is not paid"));
                }

                order.setStatus("PACKED");
                return repository.saveAll(Mono.just(order)).then();
            });
}
~~~

Ví dụ này minh họa cách ghép publisher; saveAll không atomic khi phát nhiều document. Field @UpdateTime(version = true) trong entity có thể giúp phát hiện document đã bị request khác cập nhật. Nếu yêu cầu nhiều thay đổi cùng commit, dùng transaction API và chỉ dùng các thao tác đã xác minh tham gia transaction context. Chỉ kiểm tra status trong một query độc lập rồi ghi ở request sau có thể tạo race condition.

### 4.5. Error handling

Dùng operator Reactor để chuyển lỗi ở boundary phù hợp:

~~~java
public Mono<OrderDocument> findOrCreate(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.defer(() -> {
                OrderDocument order = new OrderDocument();
                order.setId(id);
                order.setStatus("PENDING");
                return repository.save(order);
            }));
}
~~~

switchIfEmpty xử lý trường hợp không có document; nó không xử lý permission denied, timeout hoặc lỗi network. Dùng onErrorMap để chuyển exception thành domain exception và onErrorResume khi có fallback an toàn.

Không biến mọi lỗi database thành empty result. Điều đó có thể khiến API trả 404 cho một lỗi IAM hoặc outage.

## 5. Query methods của Firestore

### 5.1. Tạo query từ tên method

Spring Data ánh xạ tên method sang Firestore query. Ví dụ:

~~~java
Flux<OrderDocument> findByStatus(String status);

Flux<OrderDocument> findByCustomerIdAndStatus(
        String customerId, String status);

Flux<OrderDocument> findByCreatedAtGreaterThan(Timestamp timestamp);

Flux<OrderDocument> findByTagsContains(String tag);

Flux<OrderDocument> findByStatusOrderByCreatedAtDesc(String status);

Mono<OrderDocument> findTopByCustomerIdOrderByCreatedAtDesc(
        String customerId);
~~~

Có thể dùng nested property expressions để lọc field trong embedded object, ví dụ findByShippingAddressCity(String city), nếu kiểu mapping và query tương ứng được Firestore hỗ trợ.

### 5.2. Giới hạn filter trong repository method

Theo reference Spring Framework on Google Cloud 8.2.1, query methods của Firestore hỗ trợ các filter kết hợp bằng AND:

- Equality và not-equal.
- Greater than/greater than or equal.
- Less than/less than or equal.
- Is null.
- Contains.
- In và not-in.

contains nhận một giá trị đơn hoặc danh sách tối đa 10 phần tử. in và not-in nhận danh sách tối đa 10 phần tử. Nếu kết hợp in với contains, đối số của contains phải là giá trị đơn.

Đây là giới hạn của Spring Data query method. Firestore API có những biểu thức query khác, nhưng không có nghĩa mọi biểu thức đó được sinh ra từ tên method repository.

Trong reference 8.2.1, Spring Data Cloud Firestore chưa hỗ trợ query by example, projection và auditing. Nếu cần các khả năng này, dùng query builder/native client hoặc tự triển khai mapping/auditing ở tầng ứng dụng.

### 5.3. Không có @Query GQL cho Native mode

Firestore Native không có GQL/SQL query language tương đương Datastore. Vì vậy custom @Query theo GQL không được hỗ trợ. Nếu query method không đủ diễn đạt, dùng FirestoreTemplate hoặc Firestore Java client query builder.

Đừng cố dùng @Query("SELECT ...") như Datastore repository; nó không phải cú pháp Firestore Native.

### 5.4. Index và query failure

Query kết hợp filter/sort có thể yêu cầu composite index. Khi index chưa có, Firestore thường trả lỗi kèm link tạo index. Quy trình đúng:

1. Tái hiện query ở môi trường dev/emulator hoặc sandbox.
2. Đọc index definition được gợi ý.
3. Review field order, sort direction và collection scope.
4. Đưa index vào cấu hình triển khai.
5. Theo dõi trạng thái build trước khi phát hành query.

Không thêm index cho mọi field. Index tăng chi phí ghi và lưu trữ; chỉ tạo theo query pattern thực tế.

### 5.5. Paging và giới hạn kết quả

Repository có thể nhận Pageable để áp dụng giới hạn và phân trang, ví dụ:

~~~java
Flux<OrderDocument> findByStatus(
        String status, Pageable pageable);
~~~

Pageable là tham số yêu cầu offset/page size và sort; kết quả vẫn là Flux, không phải Page có tổng số trang. Nếu cần tổng số lượng, gọi count riêng và cân nhắc chi phí.

Với collection lớn, ưu tiên giới hạn page size và cursor/keyset strategy. Offset sâu có thể tốn kém và kết quả có thể dịch chuyển khi document được thêm/xóa giữa các request trang.

## 6. FirestoreTemplate và FirestoreReactiveOperations

### 6.1. Khi nào dùng template?

Repository phù hợp với CRUD và query method ổn định. Dùng template khi cần:
- Tạo query động từ nhiều điều kiện.
- Thao tác với subcollection.
- Dùng API Firestore chưa được repository biểu diễn.
- Chuyển đổi DTO hoặc xử lý một tập document theo logic riêng.
- Tổ chức thao tác đọc/ghi trong transaction.

Spring Boot starter tự cấu hình FirestoreTemplate, FirestoreReactiveOperations và bean Firestore để truy cập Java client cấp thấp.

### 6.2. Lưu và đọc bằng template

Ví dụ dùng reactive operations:

~~~java
import com.google.cloud.spring.data.firestore.FirestoreReactiveOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class OrderTemplateService {

    private final FirestoreReactiveOperations firestore;

    public OrderTemplateService(FirestoreReactiveOperations firestore) {
        this.firestore = firestore;
    }

    public Mono<OrderDocument> save(OrderDocument order) {
        return firestore.save(order);
    }

    public Flux<OrderDocument> findAll() {
        return firestore.findAll(OrderDocument.class);
    }

    public Mono<Long> deleteAll() {
        return firestore.deleteAll(OrderDocument.class);
    }
}
~~~

FirestoreTemplate là implementation template được starter cấu hình. Dùng interface FirestoreReactiveOperations ở service để giữ code phụ thuộc abstraction.

Với FirestoreOperations, save(entity) là insert-only; saveAll(publisher) hỗ trợ insert/update nhưng dùng buffer và không atomic trên toàn publisher. Vì vậy, đừng dùng saveAll như một batch transaction.

Lưu ý chi phí: reference API 8.0.4 mô tả count của FirestoreTemplate là đọc các document ID rồi đếm, không phải count aggregation tối ưu. Trước khi gọi count trên collection lớn, kiểm tra implementation của BOM đang dùng và cân nhắc Firestore aggregation query hoặc lưu counter theo nghiệp vụ.

### 6.3. Subcollection với withParent

Để làm việc với subcollection gắn với parent, tạo operations object bằng withParent:

~~~java
FirestoreReactiveOperations itemOperations =
        firestore.withParent(orderDocument);

return itemOperations.save(orderItem);
~~~

Parent cần có ID không rỗng; document cha không nhất thiết phải tồn tại trước khi thao tác child. Sau đó có thể save, query và delete child thông qua operations object này.

Xóa document cha không tự động xóa subcollection. Nếu nghiệp vụ yêu cầu cascade delete, phải triển khai quy trình xóa child documents rõ ràng, có giới hạn batch, retry và khả năng resume.

### 6.4. Native Firestore Java client

Starter data Firestore cũng cấu hình bean Firestore. Khi cần API đặc thù, có thể dùng trực tiếp:

~~~java
import com.google.cloud.firestore.Firestore;
import com.google.api.core.ApiFuture;
import com.google.cloud.firestore.DocumentSnapshot;

public class NativeOrderReader {

    private final Firestore firestore;

    public NativeOrderReader(Firestore firestore) {
        this.firestore = firestore;
    }

    public ApiFuture<DocumentSnapshot> get(String orderId) {
        return firestore.collection("orders")
                .document(orderId)
                .get();
    }
}
~~~

Native client trả ApiFuture, không phải Mono/Flux. Nếu gọi get() trên future trong WebFlux event-loop, thread sẽ bị block. Chỉ chờ future trong ứng dụng đồng bộ hoặc chuyển sang scheduler phù hợp; tốt hơn là dùng reactive template khi request path cần non-blocking I/O.

## 7. Transaction reactive trong Firestore

### 7.1. ReactiveFirestoreTransactionManager

Spring Framework on Google Cloud cung cấp ReactiveFirestoreTransactionManager. Có thể tạo TransactionalOperator để bọc một chuỗi reactive operation:

~~~java
import com.google.cloud.spring.data.firestore.transaction.ReactiveFirestoreTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.reactive.TransactionalOperator;

public class FirestoreTransactionConfig {

    public TransactionalOperator firestoreTransactionOperator(
            ReactiveFirestoreTransactionManager transactionManager) {

        DefaultTransactionDefinition definition =
                new DefaultTransactionDefinition();

        definition.setReadOnly(false);

        return TransactionalOperator.create(
                transactionManager, definition);
    }
}
~~~

Spring Boot starter tự cấu hình reactive transaction manager. Có thể inject manager và tạo operator tại service/configuration; không cần tự tạo Firestore gRPC stub.

### 7.2. Bọc chuỗi repository operation

~~~java
public Mono<Void> createOrderAndAudit(
        OrderDocument order,
        OrderAuditDocument audit,
        TransactionalOperator transactionOperator) {

    return orderRepository.save(order)
            .then(auditRepository.save(audit))
            .then()
            .as(transactionOperator::transactional);
}
~~~

Các thao tác ghi trong transaction commit nguyên tử. Nếu một thao tác lỗi, transaction rollback. Trong read-write transaction, thực hiện các thao tác đọc trước khi bắt đầu ghi; không xen kẽ read sau write.

### 7.3. Đọc trước, ghi sau

Một transaction có thể đọc trạng thái hiện tại rồi ghi các document liên quan:

~~~java
public Mono<Void> recordConfirmationRequest(
        String orderId,
        TransactionalOperator transactionOperator) {

    Mono<Void> work = orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Order not found")))
            .flatMap(order -> {
                if (!"PENDING".equals(order.getStatus())) {
                    return Mono.error(
                            new IllegalStateException("Invalid order state"));
                }

                OrderAuditDocument audit = new OrderAuditDocument();
                audit.setOrderId(orderId);
                audit.setAction("CONFIRM_REQUESTED");
                return auditRepository.save(audit).then();
            });

    return work.as(transactionOperator::transactional);
}
~~~

Ví dụ minh họa đọc order rồi insert audit document trong cùng reactive transaction. Audit có ID mới nên thao tác save insert-only phù hợp. Nếu cần cập nhật order và audit atomically, hãy dùng Firestore transaction API với write operation đã xác minh tham gia cùng transaction; không giả định saveAll theo batch là atomic. Không gọi payment gateway, gửi email hoặc publish message bên trong transaction; transaction có thể retry hoặc rollback.

### 7.4. @Transactional và reactive transaction

Spring Framework on Google Cloud 8.2.1 mô tả cả TransactionalOperator với ReactiveFirestoreTransactionManager và declarative @Transactional cho Firestore repository/template. Phần declarative transaction trong reference nêu bean SpannerTransactionManager, trong khi phần reactive transaction dùng ReactiveFirestoreTransactionManager.

Với reactive pipeline nên dùng ReactiveFirestoreTransactionManager cùng TransactionalOperator như ví dụ trên để transaction boundary tường minh. Nếu chọn @Transactional, kiểm tra bean transaction manager thực tế và compatibility của BOM trước khi áp dụng; không tự giả định manager của Spanner hoặc Datastore có thể quản lý Firestore.

## 8. Datastore mode: cấu hình và ánh xạ entity

### 8.1. Starter và property

Dùng starter:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-datastore</artifactId>
</dependency>
~~~

Property thường dùng:

| Property | Ý nghĩa |
| --- | --- |
| spring.cloud.gcp.datastore.enabled | Bật/tắt Datastore client |
| spring.cloud.gcp.datastore.project-id | Project chứa database |
| spring.cloud.gcp.datastore.database-id | Database ID; mặc định (default) |
| spring.cloud.gcp.datastore.namespace | Namespace mặc định |
| spring.cloud.gcp.datastore.host | Host/port service hoặc emulator chạy sẵn |
| spring.cloud.gcp.datastore.emulator.enabled | Tự khởi chạy Datastore Emulator |
| spring.cloud.gcp.datastore.emulator.port | Port emulator; mặc định 8081 |
| spring.cloud.gcp.datastore.emulator.consistency | Consistency setting của emulator |
| spring.cloud.gcp.datastore.skip-null-value | Bỏ qua property có giá trị null khi ghi |

Ví dụ:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-platform-dev
      datastore:
        project-id: rental-platform-dev
        database-id: "(default)"
        namespace: orders
        emulator:
          enabled: false
~~~

Nếu bật autoconfigured emulator, property spring.cloud.gcp.datastore.host bị bỏ qua và starter kết nối emulator local do nó quản lý. Nếu emulator do bạn tự khởi chạy, đặt host tới đúng địa chỉ.

### 8.2. Entity Datastore

Annotation mapping chính:

- @Entity(name = "..."): tên kind.
- @Id: property ID/key; mỗi entity phải có một ID.
- @Field(name = "..."): tên property trong Datastore.
- @Transient: bỏ qua field khi đọc/ghi.
- @Unindexed: không tạo index cho property không cần query.

Ví dụ:

~~~java
import com.google.cloud.spring.data.datastore.core.mapping.Entity;
import com.google.cloud.spring.data.datastore.core.mapping.Field;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;

@Entity(name = "orders")
public class DatastoreOrder {

    @Id
    private Long id;

    @Field(name = "customer_id")
    private String customerId;

    private String status;

    private Long totalAmount;

    @Transient
    private String displayLabel;

    public DatastoreOrder() {
    }

    // Getters and setters.
}
~~~

Nếu Long id là null khi lưu, Datastore có thể cấp numeric ID và Spring Data gán lại vào entity. Không dùng primitive long nếu muốn ID tự sinh vì giá trị mặc định 0 không phải null.

### 8.3. Key và quan hệ

Datastore mode dùng Key làm định danh. ID property có thể là String, Long hoặc Key tùy mô hình. Với ancestor path, dùng kiểu Key để giữ đầy đủ kind, identifier và ancestor.

Các quan hệ Spring Data Datastore:

- Embedded entity: object con nằm trong entity cha.
- @Descendants: entity con thuộc ancestor path của entity cha.
- @Reference: lưu key tới entity ở kind khác.
- @LazyReference: trì hoãn resolve entity được tham chiếu.

Ví dụ child entity có ancestor key:

~~~java
import com.google.cloud.datastore.Key;
import com.google.cloud.spring.data.datastore.core.mapping.Entity;
import org.springframework.data.annotation.Id;

@Entity(name = "orderItems")
public class DatastoreOrderItem {

    @Id
    private Key id;

    private String productId;

    private Long quantity;

    public DatastoreOrderItem() {
    }
}
~~~

Đừng dùng namespace như security boundary. Nếu namespace đại diện tenant, service vẫn phải kiểm tra tenant identity và giới hạn quyền ở tầng ứng dụng.

## 9. DatastoreRepository

### 9.1. Khai báo repository

DatastoreRepository<T, ID> mở rộng PagingAndSortingRepository và bổ sung thao tác riêng của Datastore:

~~~java
import com.google.cloud.spring.data.datastore.repository.DatastoreRepository;
import java.util.List;
import java.util.Optional;

public interface DatastoreOrderRepository
        extends DatastoreRepository<DatastoreOrder, Long> {

    List<DatastoreOrder> findByCustomerId(String customerId);

    List<DatastoreOrder> findByCustomerIdAndStatus(
            String customerId, String status);

    Optional<DatastoreOrder> findFirstByCustomerIdAndStatus(
            String customerId, String status);

    int countByStatus(String status);

    boolean existsByCustomerId(String customerId);
}
~~~

Spring Boot starter tự cấu hình repository scanning. Nếu cần tùy chỉnh package hoặc repository behavior, dùng @EnableDatastoreRepositories.

### 9.2. Query methods theo convention

Spring Data Cloud Datastore hỗ trợ các filter method theo convention, gồm:
- Equality.
- Not equal.
- Greater than/greater than or equal.
- Less than/less than or equal.
- Is null.

Các filter trong query method được kết hợp bằng AND. Không giả định có đầy đủ phép toán của Spring Data JPA, OR, JOIN hoặc SQL expression tùy ý.

Nếu cần các query khác, sử dụng custom GQL hoặc Datastore Java client. Kiểm tra composite index trước khi triển khai query mới.

### 9.3. Kết quả rỗng và kiểu trả về

Dùng Optional<T> cho kết quả có thể không tồn tại. Method trả collection không trả null; khi không có entity, collection rỗng.

Ví dụ:

~~~java
Optional<DatastoreOrder> findFirstByCustomerIdAndStatus(
        String customerId, String status);
~~~

Tránh method trả object đơn mà không định nghĩa rõ behavior khi không tìm thấy. Nếu API nghiệp vụ cần 404, chuyển Optional.empty() thành domain exception ở service/controller boundary.

### 9.4. Paging, Slice và Page

Datastore repository hỗ trợ Pageable, Sort, Page và Slice.

~~~java
Page<DatastoreOrder> findByStatus(
        String status, Pageable pageable);

Slice<DatastoreOrder> findByCustomerId(
        String customerId, Pageable pageable);
~~~

Page cần query bổ sung để tính tổng số kết quả/trang. Slice không cần count query và thường hiệu quả hơn khi chỉ cần biết còn trang tiếp theo hay không.

Datastore query hỗ trợ offset/limit, nhưng offset sâu có thể tốn kém. Với dataset lớn, thiết kế cursor/keyset theo key/index và giới hạn page size.

### 9.5. Delete query có một giới hạn quan trọng

Method như deleteByStatus hoặc removeByCustomerId được thực hiện bằng hai bước: query entity rồi xóa các entity tìm được. Nó không chạy như một câu delete nguyên tử trong transaction. Do giới hạn query trong Datastore transaction, các delete query theo convention này không dùng được bên trong @Transactional hoặc performTransaction.

Nếu cần đọc/kiểm tra rồi xóa nguyên tử, hãy thiết kế transaction theo ancestor/query constraints được Datastore hỗ trợ hoặc thao tác trực tiếp bằng key trong transaction. Không dựa vào deleteBy... để thực hiện một nghiệp vụ multi-step atomic.

## 10. Custom GQL với @Query

### 10.1. Khi nào dùng custom GQL?

Query method theo tên phù hợp với filter đơn giản. Dùng @Query khi cần kiểm soát GQL, chọn key hoặc projection.

Ví dụ:

~~~java
import com.google.cloud.spring.data.datastore.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface DatastoreOrderGqlRepository
        extends DatastoreRepository<DatastoreOrder, Long> {

    @Query("SELECT * FROM orders WHERE customer_id = @customer")
    List<DatastoreOrder> findByCustomer(
            @Param("customer") String customerId);
}
~~~

Tên placeholder sau @ phải khớp với @Param. Luôn bind parameter, không nối input người dùng vào GQL.

### 10.2. Truy vấn key

Datastore GQL có special column __key__ để lấy key:

~~~java
import com.google.cloud.datastore.Key;

@Query("SELECT __key__ FROM orders WHERE status = @status")
List<Key> findKeysByStatus(@Param("status") String status);
~~~

Khi so sánh ID trong custom query, dùng __key__ và parameter kiểu Key nếu query yêu cầu key đầy đủ. Có thể tạo key qua DatastoreTemplate.createKey(...).

### 10.3. Count và exists

Với custom GQL, annotation @Query có tùy chọn count = true hoặc exists = true cho các trường hợp cần số lượng hoặc boolean. Chọn return type phù hợp:

~~~java
@Query(value = "SELECT __key__ FROM orders WHERE status = @status",
       count = true)
int countOrdersByStatus(@Param("status") String status);
~~~

~~~java
@Query(value = "SELECT __key__ FROM orders WHERE customer_id = @customer",
       exists = true)
boolean hasOrders(@Param("customer") String customerId);
~~~

Dùng __key__ khi chỉ cần biết key/count để tránh đọc toàn bộ entity. Kiểm tra cú pháp và index trong test trước khi triển khai.

### 10.4. Projection

Spring Data Cloud Datastore hỗ trợ interface projection:

~~~java
public interface OrderSummary {
    String getCustomerId();
    String getStatus();
}

public interface DatastoreOrderSummaryRepository
        extends DatastoreRepository<DatastoreOrder, Long> {

    List<OrderSummary> findByStatus(String status);
}
~~~

Projection giúp giảm dữ liệu mapping khi chỉ cần một số field. Với custom GQL select các property cụ thể, Datastore yêu cầu composite index chứa các field được select theo quy tắc của dịch vụ; cần xác minh index trước khi phát hành.

## 11. DatastoreTemplate và DatastoreOperations

### 11.1. Khi nào dùng template?

Dùng DatastoreTemplate khi cần:
- Đọc theo ID/key hoặc nhiều ID.
- Lấy toàn bộ entity theo kind.
- GQL query trả entity hoặc key.
- Tạo key.
- Ghi map trực tiếp.
- Thực hiện transaction qua performTransaction.

Spring Boot starter tự cấu hình bean DatastoreTemplate, interface DatastoreOperations và client Datastore.

### 11.2. Đọc theo ID và ghi entity

~~~java
import com.google.cloud.spring.data.datastore.core.DatastoreTemplate;
import org.springframework.stereotype.Service;

@Service
public class DatastoreOrderService {

    private final DatastoreTemplate datastore;

    public DatastoreOrderService(DatastoreTemplate datastore) {
        this.datastore = datastore;
    }

    public DatastoreOrder find(Long id) {
        return datastore.findById(id, DatastoreOrder.class);
    }

    public DatastoreOrder save(DatastoreOrder order) {
        return datastore.save(order);
    }
}
~~~

Các thao tác phổ biến khác:

~~~java
DatastoreOrder one =
        datastore.findById(orderId, DatastoreOrder.class);

List<DatastoreOrder> many =
        datastore.findAllById(orderIds, DatastoreOrder.class);

List<DatastoreOrder> all =
        datastore.findAll(DatastoreOrder.class);
~~~

save có semantics update-or-insert. insert thất bại nếu entity đã tồn tại. API hiện không hỗ trợ partial update theo kiểu chỉ ghi một vài property; write operation ghi các property của POJO. Nếu chỉ muốn thay một field, hãy thiết kế entity/update flow cẩn thận hoặc dùng lower-level client phù hợp.

### 11.3. Query bằng DatastoreTemplate

DatastoreTemplate hỗ trợ GQL/query object và mapping entity. Ví dụ query builder của Datastore client:

~~~java
import com.google.cloud.datastore.Entity;
import com.google.cloud.datastore.Query;
import com.google.cloud.datastore.StructuredQuery;

Query<Entity> query = Query.newEntityQueryBuilder()
        .setKind("orders")
        .setFilter(StructuredQuery.PropertyFilter.eq(
                "status", "PAID"))
        .build();

Iterable<DatastoreOrder> orders =
        datastore.query(query, DatastoreOrder.class);
~~~

Đây là ví dụ minh họa builder của Datastore client; tên import và generic query phải khớp phiên bản client do BOM quản lý. Nếu chỉ dùng GQL, có thể dùng @Query ở repository. Với truy vấn động, lower-level Datastore client cho phép kiểm soát query object trực tiếp.

### 11.4. Transaction với DatastoreTemplate

DatastoreOperations.performTransaction cung cấp một DatastoreOperations instance gắn với transaction:

~~~java
public void markPaid(Long orderId) {
    datastore.performTransaction(transactionDatastore -> {
        DatastoreOrder order = transactionDatastore.findById(
                orderId, DatastoreOrder.class);

        if (order == null) {
            throw new IllegalArgumentException("Order not found");
        }

        order.setStatus("PAID");
        transactionDatastore.save(order);
        return null;
    });
}
~~~

Không mở transaction con bên trong callback transaction. Datastore có giới hạn consistency/ancestor cho query trong transaction; hãy thiết kế thao tác transaction theo key/ancestor mà dịch vụ hỗ trợ.

### 11.5. @Transactional và transaction manager

Starter Datastore cung cấp DatastoreTransactionManager. Repository và template có thể tham gia declarative transaction:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Service
public class DatastoreOrderApplicationService {

    private final DatastoreOrderRepository repository;

    public DatastoreOrderApplicationService(
            DatastoreOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "datastoreTransactionManager")
    public void updateOrder(Long id) {
        DatastoreOrder order = repository.findById(id).orElseThrow();
        order.setStatus("PAID");
        repository.save(order);
    }
}
~~~

Nếu ứng dụng có thêm Firestore hoặc Spanner, chỉ định transaction manager để Spring không chọn nhầm bean. Không gọi performTransaction bên trong method đã có @Transactional trên cùng Datastore database.

## 12. So sánh lựa chọn Repository, Template và Client

| Tình huống | Firestore Native | Datastore mode |
| --- | --- | --- |
| CRUD phổ biến | FirestoreReactiveRepository | DatastoreRepository |
| Query method đơn giản | Reactive query methods | Query methods đồng bộ |
| Query tùy chỉnh | FirestoreTemplate hoặc native query builder | GQL @Query hoặc DatastoreTemplate |
| Subcollection | FirestoreReactiveOperations.withParent | Ancestor/descendant hoặc reference |
| Transaction reactive | ReactiveFirestoreTransactionManager + TransactionalOperator | Không dùng reactive API; dùng Datastore transaction |
| Client API trực tiếp | Firestore + ApiFuture | Datastore client |
| Paging | Pageable parameter và Flux | Page, Slice, Pageable, Sort |
| Query annotation | Không hỗ trợ custom @Query | Hỗ trợ @Query GQL |

Nguyên tắc chọn:

- Dùng repository khi query ổn định, đơn giản và phù hợp giới hạn method convention.
- Dùng template khi cần query động, subcollection, transaction hoặc API Spring abstraction chuyên biệt.
- Dùng native client khi cần tính năng không được template/repository bộc lộ.
- Giữ API đồng bộ của Datastore ở service boundary đồng bộ; giữ Firestore reactive xuyên suốt WebFlux pipeline.

## 13. Bảo mật và vận hành

### 13.1. IAM theo runtime identity

Spring Boot server dùng ADC và IAM. Cấp role tối thiểu cho service account:
- Datastore/Firestore user role cho workload đọc/ghi.
- Viewer/read-only role cho workload chỉ đọc.
- Tách principal migration/index administration khỏi runtime API.

Với Firestore Native server SDK, request dùng IAM và server client libraries bỏ qua Firestore Security Rules. Security Rules bảo vệ mobile/web client SDK; backend vẫn phải kiểm tra authorization theo user/tenant.

### 13.2. Không chặn reactive event loop

Trong Firestore reactive path:
- Không gọi block() trong controller/service.
- Không gọi ApiFuture.get() trên event-loop.
- Dùng Mono/Flux xuyên suốt pipeline.
- Chỉ chuyển sang scheduler blocking khi bắt buộc gọi thư viện đồng bộ.
- Giới hạn concurrency và page size.

Trong Datastore mode, repository/template là API đồng bộ. Nếu ứng dụng là WebFlux, đẩy thao tác blocking sang scheduler phù hợp hoặc cân nhắc thiết kế endpoint/service đồng bộ theo stack của ứng dụng. Không giả định DatastoreRepository tự trở thành non-blocking chỉ vì controller trả Mono.

### 13.3. Index và latency

Theo dõi:
- Query latency p50/p95/p99.
- Số document/entity đọc so với số trả về.
- Composite index missing/building.
- Error rate theo operation.
- Transaction conflict/abort.
- Session/thread usage và blocking time.
- Emulator/production behavior khác nhau.

Dùng projection/field selection khi có thể. Tránh findAll() trên collection/kind lớn nếu không có giới hạn; dùng page/cursor, filter và sort theo index.

### 13.4. Xóa dữ liệu và retention

Firestore subcollection không tự cascade khi xóa parent. Datastore descendants/reference có semantics khác và có thể phát sinh đọc/ghi đệ quy qua mapping. Hãy định nghĩa rõ retention, soft delete, cascade cleanup và khả năng resume.

Không triển khai thao tác xóa hàng loạt bằng cách gọi deleteAll() không giới hạn trên production. Chia batch, giới hạn tốc độ và audit kết quả.

## 14. Kiểm thử bằng emulator

### 14.1. Firestore Emulator

Firestore Native dùng Firebase Emulator. Khi emulator chạy mặc định port 8080, cấu hình:

~~~yaml
spring:
  cloud:
    gcp:
      firestore:
        emulator:
          enabled: true
        host-port: localhost:8080
~~~

Có thể dùng Testcontainers FirestoreEmulatorContainer trong CI. Kiểm thử repository CRUD, query, embedded mapping, transaction, subcollection và optimistic locking.

### 14.2. Datastore Emulator

Starter Datastore có thể tự khởi chạy emulator:

~~~yaml
spring:
  cloud:
    gcp:
      datastore:
        emulator:
          enabled: true
          port: 8081
          consistency: 0.9
~~~

Emulator hữu ích cho mapping, GQL, repository, CRUD và transaction cơ bản. Có thể dùng emulator tự chạy bằng cách đặt spring.cloud.gcp.datastore.host.

### 14.3. Test reactive bằng StepVerifier

Không dùng block() để kiểm tra mọi pipeline nếu có thể dùng Reactor Test:

~~~java
StepVerifier.create(orderRepository.findByStatus("PAID"))
        .expectNextMatches(order -> "PAID".equals(order.getStatus()))
        .thenCancel()
        .verify();
~~~

Nếu cần kiểm tra toàn bộ collection, dùng expectNextCount, expectNextMatches hoặc collectList trong pipeline test. Luôn kiểm tra lỗi và completion signal, không chỉ kiểm tra một giá trị trả về.

### 14.4. Test Datastore repository

Kiểm tra:
- Entity mapping và ID tự sinh.
- save upsert và insert duplicate behavior.
- Query methods với filter AND.
- Custom GQL parameter binding.
- Page và Slice.
- Transaction commit/rollback.
- Delete query boundary.
- Index cần thiết.

Emulator không thay thế sandbox thật để xác minh IAM, index provisioning, quota, concurrency và network path.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không tạo được repository Firestore | Thiếu starter hoặc scan sai package | Kiểm dependency và @EnableReactiveFirestoreRepositories |
| @DocumentId mapping error | ID không phải String hoặc thiếu annotation | Dùng String và một field @DocumentId |
| Reactive endpoint bị treo | Có block() hoặc ApiFuture.get() trên event-loop | Giữ publisher reactive hoặc chuyển blocking sang scheduler |
| Firestore query yêu cầu index | Thiếu composite index | Tạo và deploy index tương ứng |
| Firestore repository query không chạy | Dùng filter không hỗ trợ hoặc OR | Chuyển sang native Firestore query builder |
| @Query không chạy trên Native | Firestore Native không có GQL | Dùng query methods/template/client |
| Subcollection còn dữ liệu sau delete | Xóa document cha không cascade | Triển khai recursive/background cleanup |
| Transaction conflict | Nhiều request sửa cùng document | Dùng optimistic locking hoặc retry có giới hạn |
| Không tìm thấy Datastore entity | Sai kind, ID type hoặc namespace | Đối chiếu @Entity, @Id, database và namespace |
| Datastore query thiếu index | Chưa tạo composite index | Kiểm GQL/query pattern và triển khai index |
| deleteBy... lỗi trong transaction | Query-delete chạy ngoài transaction | Dùng key/ancestor operation phù hợp hoặc tách transaction |
| @Transactional chạy nhầm database | Nhiều transaction manager trong context | Chỉ định manager đúng |
| Local pass nhưng cloud fail | Emulator không xác minh IAM/runtime network | Test trên sandbox với workload identity |

## 16. Bài tập thực hành

### Bài A — Firestore reactive CRUD

Tạo OrderDocument và OrderDocumentRepository. Viết API tạo, đọc, cập nhật và xóa đơn hàng bằng Mono/Flux. Xác minh controller không gọi block().

### Bài B — Query method và index

Viết method tìm order theo customer, status và createdAt. Tạo composite index cần thiết. Thử truy vấn thiếu index và đọc lỗi để hiểu cách xử lý.

### Bài C — FirestoreTemplate và subcollection

Dùng FirestoreReactiveOperations.withParent để lưu OrderItem vào subcollection. Viết cleanup job xóa child trước khi xóa parent và đảm bảo job có thể resume.

### Bài D — Firestore transaction

Dùng ReactiveFirestoreTransactionManager và TransactionalOperator để cập nhật order và insert audit document trong một transaction. Đảm bảo toàn bộ read diễn ra trước write.

### Bài E — Datastore repository

Tạo DatastoreOrder và DatastoreOrderRepository. Viết CRUD, query method theo customer/status, count, exists và Slice pagination.

### Bài F — GQL và projection

Viết custom @Query với named parameter, truy vấn __key__, và một interface projection. Tạo composite index nếu query yêu cầu.

### Bài G — DatastoreTemplate transaction

Viết performTransaction đọc order, kiểm tra trạng thái rồi cập nhật. So sánh với @Transactional(transactionManager = "datastoreTransactionManager").

### Bài H — Emulator và security

Chạy hai test suite với Firestore Emulator và Datastore Emulator. Triển khai một integration test lên sandbox thật bằng service account tối thiểu; kiểm tra IAM và query/index behavior.

### Câu hỏi tự kiểm tra

1. Vì sao Firestore Native và Datastore mode cần hai repository abstraction?
2. FirestoreReactiveRepository mở rộng loại repository nào?
3. Khi nào một method nên trả Mono, khi nào trả Flux?
4. Vì sao không gọi block() trong WebFlux request path?
5. @DocumentId có yêu cầu kiểu dữ liệu gì?
6. @PropertyName giúp xử lý naming mismatch như thế nào?
7. Firestore query methods hỗ trợ các filter nào và kết hợp ra sao?
8. Vì sao custom @Query GQL không dùng cho Native mode?
9. Khi nào dùng FirestoreTemplate thay repository?
10. withParent dùng để làm gì?
11. Xóa document cha có tự xóa subcollection không?
12. ReactiveFirestoreTransactionManager kết hợp với operator nào?
13. Vì sao transaction cần đọc trước rồi mới ghi?
14. @UpdateTime(version = true) bảo vệ update cạnh tranh ra sao?
15. DatastoreRepository<T, ID> dùng generic thứ hai cho mục đích gì?
16. Query method Datastore hỗ trợ filter nào?
17. Vì sao Page tốn query hơn Slice?
18. Vì sao deleteBy... convention không dùng trong Datastore transaction?
19. Khi nào dùng custom GQL và DatastoreTemplate?
20. Làm thế nào phân biệt lỗi IAM, index và lỗi reactive pipeline?

**Kết quả mong đợi:** người học triển khai được repository Firestore reactive cho Native mode và repository Datastore cho Datastore mode, viết query đúng giới hạn API, dùng template/client cho trường hợp nâng cao, quản lý transaction và index phù hợp, giữ reactive pipeline không blocking, và kiểm thử được tích hợp bằng emulator cùng runtime identity.

## Tài liệu tham khảo

- [Spring Framework on Google Cloud 8.2.1 — Spring Data Cloud Firestore](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.1/reference/html/index.html#spring-data-cloud-firestore)
- [Spring Framework on Google Cloud 8.2.1 — Spring Data Cloud Datastore](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.1/reference/html/datastore.html)
- [Firestore query and data model](https://docs.cloud.google.com/firestore/native/docs/query-data/queries)
- [Firestore transactions](https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions)
- [Datastore queries](https://docs.cloud.google.com/datastore/docs/concepts/queries)
- [Datastore transactions](https://docs.cloud.google.com/datastore/docs/concepts/transactions)
- [Firestore Emulator](https://firebase.google.com/docs/emulator-suite/connect_firestore)

