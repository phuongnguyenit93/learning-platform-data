# Phân biệt Datastore và Firestore khi chọn mô hình lưu trữ

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot tích hợp các dịch vụ managed của AWS, Azure và Google Cloud để truy cập dữ liệu, storage, messaging và quản lý danh tính/quyền. Trên Google Cloud, Datastore và Firestore thường được nhắc cùng nhau vì Firestore là thế hệ kế tiếp của Cloud Datastore và vẫn cung cấp một chế độ tương thích API Datastore.

Bài học giúp bạn phân biệt đúng **Firestore in Datastore mode** và **Firestore in Native mode**, sau đó chọn Spring integration phù hợp:

1. Hiểu tên gọi Cloud Datastore, Firestore và hai database mode hiện nay.
2. So sánh data model: kind/entity/key với collection/document/field.
3. Chọn cách biểu diễn quan hệ parent-child, embedded data và reference.
4. Đánh giá query, index, transaction, consistency và realtime capability.
5. Chọn Spring Data Cloud Datastore hoặc Spring Data Cloud Firestore.
6. Cấu hình starter, ADC, IAM và emulator trong Spring Boot.
7. Thiết kế schema evolution, kiểm thử và kế hoạch chuyển đổi dữ liệu.
8. Nhận biết khi nào NoSQL phù hợp và khi nào nên chọn Cloud SQL hoặc Spanner.

> **Phạm vi:** Ví dụ dùng Java và Spring Boot. Phiên bản Spring Framework on Google Cloud, Spring Boot và Java phải tương thích theo BOM của dự án. Tên property, repository API và tính năng có thể khác giữa các major version; hãy đối chiếu reference documentation của đúng BOM đang sử dụng. Theo compatibility matrix của Spring Framework on Google Cloud 8.2.1, nhánh 8.x tương thích Spring Boot 4.0/4.1, 7.x với Boot 3.5 và 6.x với Boot 3.4.

## 1. Cloud Datastore và Firestore: hiểu đúng tên gọi

### 1.1. Datastore không còn là sản phẩm database độc lập

Cloud Datastore là tên gọi lịch sử của một dịch vụ NoSQL document/entity database. Firestore kế thừa Datastore và cung cấp một API tương thích để ứng dụng Datastore hiện hữu tiếp tục hoạt động. Vì vậy, khi nói "Datastore" trong kiến trúc Google Cloud hiện nay, thường cần xác định đang nói đến:

- **Firestore in Datastore mode:** database sử dụng Datastore API, tương thích với mô hình kind/entity/key và các ứng dụng Cloud Datastore cũ.
- **Firestore in Native mode:** database sử dụng Firestore API, mô hình collection/document, hỗ trợ các khả năng Firestore dành cho ứng dụng backend, web và mobile.

Firestore là tên dịch vụ hiện tại; Datastore mode là một chế độ truy cập/API tương thích. Hai tên gọi không đại diện cho hai database engine hoàn toàn tách biệt.

### 1.2. Database mode là lựa chọn ở cấp database

Khi tạo Firestore database, cần chọn data access mode phù hợp với edition. Standard edition hỗ trợ Native mode hoặc Datastore mode; Enterprise edition hỗ trợ Native mode hoặc MongoDB compatibility mode. Một database có một mode tại một thời điểm; ứng dụng phải dùng API và client library tương ứng. Mode change chỉ được phép khi database còn rỗng theo quy định quản lý database. Với dữ liệu đang chạy, không thể xem việc đổi mode như thay một property trong application.yml.

Một Google Cloud project có thể quản lý nhiều database, vì vậy đừng suy rằng mọi database trong project phải dùng cùng mode. Hãy kiểm tra database ID và mode của đúng tài nguyên mà ứng dụng sẽ kết nối.

### 1.3. So sánh nhanh

| Tiêu chí | Firestore in Datastore mode | Firestore in Native mode |
| --- | --- | --- |
| API chính | Datastore API | Firestore API |
| Mô hình dữ liệu | Kind, entity, property, key | Collection, document, field |
| Định danh | Entity key; có namespace, kind, ID và ancestor path | Document path và document ID |
| Query | GQL/Datastore query | Firestore query API |
| Quan hệ phân cấp | Ancestor/descendant qua key path | Subcollection và document reference |
| Index | Built-in index và composite index qua cấu hình Datastore | Single-field và composite index theo Firestore |
| Realtime listener cho web/mobile | Không có các tính năng realtime của Native API | Có realtime listeners và client SDK tương ứng |
| Offline cache trên SDK mobile/web | Không có bộ SDK Datastore tương đương | Có offline persistence trên client SDK hỗ trợ |
| Spring Data | Spring Data Cloud Datastore | Spring Data Cloud Firestore với reactive repositories |
| Tương thích ứng dụng Datastore cũ | Có | Không dùng Datastore API trực tiếp |

Cả hai mode đều là NoSQL document database managed, hỗ trợ transaction và strong consistency. Điểm khác biệt quan trọng nằm ở API, data model, query features, client ecosystem và cách ứng dụng được xây dựng. [Google Cloud mô tả hai mode và các giới hạn tương thích tại đây](https://docs.cloud.google.com/datastore/docs/firestore-or-datastore).

### 1.4. Sơ đồ hai đường tích hợp Spring

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> CHOICE{"Database mode?"}
    CHOICE -->|"Datastore mode"| DS["Spring Data Cloud Datastore"]
    CHOICE -->|"Native mode"| FS["Spring Data Cloud Firestore"]
    DS --> DAPI["Datastore API / GQL"]
    FS --> FAPI["Firestore API / query builder"]
    DAPI --> DB["Firestore database"]
    FAPI --> DB
    ADC["ADC + workload service account"] --> DAPI
    ADC --> FAPI
~~~

Hai starter có repository abstraction riêng. Không dùng DatastoreRepository để truy cập Native mode, và không dùng FirestoreReactiveRepository để truy cập Datastore mode.

## 2. Data model của Datastore mode

### 2.1. Kind, entity và property

Datastore mode tổ chức dữ liệu thành entity. Mỗi entity thuộc một **kind** và chứa các **property**:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Kind | Order | Phân loại entity |
| Entity | Một đơn hàng có ID cụ thể | Đơn vị dữ liệu |
| Property | customerId, status, createdAt | Thuộc tính của entity |
| Key | Order / 10001 | Định danh duy nhất |
| Namespace | tenant-a | Phân vùng logic tên dữ liệu |
| Ancestor path | Customer/42/Order/10001 | Quan hệ phân cấp trong key |

Các entity cùng kind không bắt buộc có cùng tập property hoặc cùng kiểu dữ liệu cho một property. Đây là mô hình schemaless. Tuy vậy, ứng dụng nên chủ động chuẩn hóa field và kiểu dữ liệu để query, validation và mapping ổn định.

Ví dụ hai entity cùng kind Order có thể có field khác nhau:

~~~json
{
  "customerId": "customer-42",
  "status": "PAID",
  "total": 125000
}
~~~

~~~json
{
  "customerId": "customer-77",
  "status": "PENDING",
  "currency": "VND"
}
~~~

Sự linh hoạt này giúp mở rộng field mà không cần migration DDL như relational database. Đổi lại, ứng dụng phải kiểm soát schema contract, null/missing field, kiểu dữ liệu và backward compatibility.

### 2.2. Entity key

Một key Datastore mode bao gồm kind, identifier và có thể có ancestor path. Identifier có thể là:

- Chuỗi do ứng dụng cấp, ví dụ order-2026-001.
- Numeric ID do Datastore tự cấp.

Namespace cho phép tách dữ liệu theo không gian tên trong cùng database. Namespace hữu ích cho multitenancy hoặc phân vùng logic, nhưng **không phải ranh giới bảo mật**. Nếu tenant không được phép truy cập dữ liệu tenant khác, ứng dụng vẫn phải kiểm tra tenant identity và giới hạn quyền IAM phù hợp.

Ví dụ key có ancestor:

~~~text
Customer("customer-42")
  └── Order(10001)
       └── OrderItem("item-1")
~~~

Key con chứa đường dẫn ancestor. Điều này cho phép xác định các entity thuộc cùng cây dữ liệu và truy vấn theo ancestor.

### 2.3. Quan hệ trong Datastore mode

Spring Data Cloud Datastore hỗ trợ một số cách biểu diễn quan hệ:

- **Embedded entity:** object con được lưu trực tiếp trong property của entity cha.
- **@Descendants:** entity con tồn tại độc lập trong kind riêng, nhưng key chứa ancestor path.
- **@Reference:** lưu key tham chiếu đến entity độc lập ở kind khác.
- **@LazyReference:** tương tự reference nhưng trì hoãn việc tải entity được tham chiếu đến khi truy cập property.

Chọn embedded khi object nhỏ, luôn được đọc cùng parent và không cần định danh độc lập. Chọn descendants khi child có vòng đời gắn với parent và cần ancestor query. Chọn reference khi hai entity có vòng đời riêng.

Với @Descendants, entity con có kind riêng và ID property dùng kiểu Key để chứa ancestor path; Spring Data có thể đọc/lưu descendants theo parent. Với @Reference, property lưu key của entity khác kind và Spring Data chuyển key thành object Java tương ứng. Reference được resolve khi đọc/ghi entity; dùng @LazyReference nếu muốn trì hoãn tải entity được tham chiếu. Collection descendants/references không bảo đảm giữ nguyên thứ tự ban đầu sau khi đọc.

### 2.4. Không có schema DDL như relational database

Datastore mode không tạo bảng bằng CREATE TABLE. Kind và property được hình thành khi ứng dụng ghi entity. Bạn vẫn cần tài liệu hóa schema nghiệp vụ và kiểm soát migration bằng code/configuration, nhưng không có DDL cố định như PostgreSQL.

Đặc biệt, entity ID/key không phải một cột có thể đổi tùy ý. Key là định danh của entity; thay đổi key về bản chất là tạo entity mới và xử lý entity cũ.

## 3. Data model của Firestore Native mode

### 3.1. Collection, document và field

Firestore Native mode tổ chức dữ liệu theo cây collection/document:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Collection | orders | Nhóm document |
| Document | orders/order-10001 | Đơn vị dữ liệu |
| Field | status, customerId, total | Dữ liệu trong document |
| Subcollection | orders/order-10001/items | Collection con của document |
| Document reference | Reference đến customers/customer-42 | Liên kết document khác |

Document chứa các cặp key-value. Field có thể là string, number, boolean, timestamp, geopoint, array, map hoặc reference. Document có thể chứa object lồng nhau, nhưng cần cân nhắc giới hạn kích thước và tần suất cập nhật.

Ví dụ document:

~~~json
{
  "customerId": "customer-42",
  "status": "PAID",
  "total": 125000,
  "createdAt": "2026-11-24T09:30:00Z",
  "shippingAddress": {
    "city": "Ho Chi Minh City",
    "country": "VN"
  },
  "tags": ["priority", "online"]
}
~~~

Các document trong cùng collection có thể có field khác nhau. Trong ứng dụng production, nên giữ field contract tương đối nhất quán để query và mapping không phụ thuộc vào các kiểu dữ liệu tùy ý.

### 3.2. Subcollection và document reference

Nếu một đơn hàng có số lượng item tăng theo thời gian, không nên nhồi toàn bộ item vào một array lớn trong document cha. Có thể dùng subcollection:

~~~text
orders/
  order-10001/
    status: "PAID"
    customerId: "customer-42"
    items/
      item-1/
      item-2/
  order-10002/
    status: "PENDING"
    customerId: "customer-77"
    items/
      item-1/
~~~

Subcollection phù hợp với danh sách tăng trưởng, cần query độc lập hoặc collection group query. Document reference phù hợp khi cần liên kết các document độc lập như orders và customers.

Lưu ý: xóa document cha không tự động xóa các subcollection bên dưới. Nếu nghiệp vụ yêu cầu cascade delete, cần triển khai quy trình xóa đệ quy hoặc background job có kiểm soát.

### 3.3. Embedded data hay subcollection?

| Tiêu chí | Embedded map/array | Subcollection |
| --- | --- | --- |
| Số lượng phần tử | Nhỏ, giới hạn và ít thay đổi | Có thể tăng theo thời gian |
| Đọc dữ liệu | Đọc cùng parent | Có thể query riêng |
| Cập nhật | Có thể ghi lại document cha | Ghi từng document con |
| Query | Query field trong document | Query collection hoặc collection group |
| Xóa parent | Field embedded biến mất cùng document | Subcollection vẫn còn nếu không xóa riêng |

Ví dụ địa chỉ giao hàng có cấu trúc cố định có thể nhúng vào document order. Danh sách lịch sử trạng thái hoặc dòng hàng có thể đặt ở subcollection nếu cần truy vấn độc lập.

### 3.4. Giới hạn kích thước document

Firestore Native mode có giới hạn kích thước document và giới hạn về số lượng field/path. Không thiết kế document như một bảng chứa vô hạn dòng. Với Standard edition, giới hạn document thường được công bố là 1 MiB; hãy kiểm tra quota/limits theo edition và thời điểm triển khai.

## 4. Query và index: khác biệt quan trọng

### 4.1. Datastore mode dùng GQL và index

Datastore mode cung cấp GQL, một ngôn ngữ truy vấn dạng SQL-like. Ví dụ:

~~~sql
SELECT * FROM orders
WHERE customer_id = @customerId
  AND status = @status
ORDER BY createdAt DESC
~~~

GQL giúp diễn đạt query quen thuộc, nhưng không phải SQL đầy đủ. Datastore mode không có JOIN như relational database. Query engine dựa vào index; built-in indexes hỗ trợ nhiều truy vấn đơn giản, còn query phức tạp cần composite index.

Một số điểm cần nhớ:

- Datastore API/GQL hiện hỗ trợ composite filter AND và OR; tuy nhiên query methods theo convention của Spring Data Cloud Datastore chỉ hỗ trợ tập filter hẹp hơn và kết hợp các filter bằng AND.
- Các phép so sánh và sort bị giới hạn theo quy tắc query/index.
- Không có join hoặc subquery như SQL relational.
- Query cần index tương ứng; index thiếu sẽ khiến query thất bại và cung cấp gợi ý tạo index.
- Có thể loại property khỏi index nếu không cần query trên property đó.

### 4.2. Composite index và index.yaml

Khi query lọc nhiều property hoặc có nhiều sort order, Datastore mode có thể cần composite index. Index được mô tả trong cấu hình index.yaml và triển khai cùng ứng dụng/pipeline.

Ví dụ minh họa:

~~~yaml
indexes:
  - kind: orders
    properties:
      - name: customer_id
      - name: status
      - name: createdAt
        direction: desc
~~~

Đây là cấu trúc minh họa; cú pháp chính xác phải khớp công cụ triển khai index và định nghĩa query thực tế. Không copy index này vào production nếu query pattern không sử dụng.

### 4.3. Native mode query API

Firestore Native mode dùng query builder của Firestore API, không dùng GQL. Query theo collection hoặc collection group. Các khả năng bao gồm equality, range filters, array filters, in, not-in và logical OR trong các điều kiện được hỗ trợ.

Ví dụ Java client:

~~~java
CollectionReference orders = firestore.collection("orders");

ApiFuture<QuerySnapshot> future = orders
        .whereEqualTo("customerId", "customer-42")
        .whereEqualTo("status", "PAID")
        .orderBy("createdAt", Query.Direction.DESCENDING)
        .limit(20)
        .get();

QuerySnapshot snapshot = future.get();
for (QueryDocumentSnapshot document : snapshot.getDocuments()) {
    System.out.println(document.getId() + " " + document.getString("status"));
}
~~~

Firestore Native mode không hỗ trợ SQL JOIN. Nếu cần dữ liệu từ nhiều collection, ứng dụng thường dùng document references, denormalization hoặc nhiều query riêng. Collection group query cho phép truy vấn các subcollection có cùng collection ID ở nhiều cấp trong cây document.

### 4.4. Index trong Native mode

Firestore tự tạo một số single-field indexes và yêu cầu composite indexes cho một số query. Khi query cần composite index mà chưa có, lỗi trả về thường kèm liên kết tạo index.

Không tạo index cho mọi field một cách máy móc. Index giúp query nhanh nhưng làm tăng chi phí lưu trữ và công việc ghi. Các field không cần query có thể được cấu hình miễn index theo nhu cầu.

### 4.5. Spring repository query có giới hạn theo từng mode

Đây là khác biệt cần lưu ý khi chuyển code:

- Spring Data Cloud Datastore hỗ trợ query methods theo quy ước Spring Data và custom GQL qua @Query.
- Spring Data Cloud Firestore cung cấp reactive query methods theo tên method; @Query GQL không dùng cho Native mode vì Firestore không có GQL.
- Query method của cả hai integration chỉ hỗ trợ tập toán tử tương ứng với database API. Không mặc định mọi predicate của Spring Data JPA đều dùng được.

Với query phức tạp hoặc cần tính năng đặc thù, dùng DatastoreTemplate/FirestoreOperations hoặc native client API.

## 5. Consistency và transaction

### 5.1. Strong consistency ở cả hai mode

Firestore in Datastore mode hiện cung cấp strong consistency cho key lookup và query. Không nên sao chép nhận định từ tài liệu Cloud Datastore rất cũ rằng mọi non-ancestor query đều eventual consistent.

Firestore Native mode cũng cung cấp strong consistency cho reads và queries theo semantics của Firestore. Vì vậy, chọn Native hay Datastore mode không nên dựa trên giả định rằng một mode có consistency mạnh còn mode kia chỉ eventual.

### 5.2. Transaction trong Datastore mode

Datastore mode hỗ trợ read-write transaction và read-only transaction. Một transaction có tính atomic: tất cả thao tác commit cùng nhau hoặc không thao tác nào được áp dụng.

Các transaction có thể gặp contention khi nhiều request cùng sửa một entity hoặc vùng dữ liệu liên quan. Database có các concurrency mode:

- **Pessimistic:** transaction dùng cơ chế khóa để bảo đảm isolation.
- **Optimistic:** các transaction có thể chạy đồng thời; xung đột được phát hiện khi commit.
- **Optimistic with entity groups:** chế độ tương thích legacy với một số giới hạn entity group.

Không thiết kế ứng dụng mới dựa trên các giới hạn entity group của hệ thống Datastore cũ nếu không có yêu cầu tương thích cụ thể. Hãy kiểm tra concurrency mode của database hiện hữu và kiểm thử workload trước khi thay đổi.

### 5.3. Transaction trong Native mode

Firestore Native mode hỗ trợ:
- **Read-write transaction:** đọc dữ liệu rồi ghi nhiều document một cách nguyên tử.
- **Batched write:** nhóm nhiều thao tác ghi không cần đọc trước vào một commit nguyên tử.

Trong transaction, thực hiện các thao tác đọc trước rồi mới ghi. Nếu dữ liệu được đọc thay đổi đồng thời, Firestore có thể chạy lại transaction callback. Vì vậy callback phải an toàn khi thực thi nhiều lần.

### 5.4. Retry và idempotency

Dù database trả lỗi ở bước commit, ứng dụng không phải lúc nào cũng biết chắc request đã được áp dụng hay chưa. Đối với các thao tác nghiệp vụ như tạo đơn, trừ tiền hoặc xác nhận thanh toán:

1. Dùng idempotency key hoặc business key duy nhất.
2. Giữ transaction ngắn.
3. Không gửi email, gọi payment gateway hoặc publish message trực tiếp bên trong transaction callback.
4. Ghi event/outbox cùng transaction nếu cần phát sự kiện.
5. Dùng worker riêng để gửi sự kiện và xử lý trùng lặp an toàn.

Không retry vô hạn mọi exception. Phân loại lỗi transient, conflict, permission và validation trước khi quyết định retry.

## 6. Chọn Spring integration phù hợp

### 6.1. Spring Data Cloud Datastore cho Datastore mode

Spring Framework on Google Cloud cung cấp starter:

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

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-data-datastore</artifactId>
    </dependency>
</dependencies>
~~~

spring-cloud-gcp.version là property do dự án chọn theo compatibility matrix. BOM quản lý phiên bản các module Spring Cloud GCP tương thích với nhau; tránh gán phiên bản starter riêng lẻ.

Starter tự cấu hình DatastoreTemplate, Datastore client và các repository được phát hiện trong package. Spring Data Cloud Datastore tương thích với Firestore in Datastore mode, không tương thích với Native mode.

### 6.2. Cấu hình Datastore mode

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-platform-dev
      datastore:
        project-id: rental-platform-dev
        database-id: "(default)"
        namespace: orders
~~~

Một số property thường dùng:

| Property | Ý nghĩa |
| --- | --- |
| spring.cloud.gcp.datastore.enabled | Bật/tắt Datastore client autoconfiguration |
| spring.cloud.gcp.datastore.project-id | Project chứa Datastore database |
| spring.cloud.gcp.datastore.database-id | Database ID; mặc định thường là (default) |
| spring.cloud.gcp.datastore.namespace | Namespace mặc định |
| spring.cloud.gcp.datastore.host | Host/port của service hoặc emulator |
| spring.cloud.gcp.datastore.emulator.enabled | Bật Datastore Emulator autoconfiguration |
| spring.cloud.gcp.datastore.emulator.port | Port emulator khi starter tự khởi chạy |

Nếu dùng database ID khác (default), hãy bảo đảm property và IAM/database resource cùng trỏ tới đúng database.

### 6.3. Ánh xạ POJO Datastore mode

Ví dụ entity đơn hàng:

~~~java
import com.google.cloud.spring.data.datastore.core.mapping.Entity;
import com.google.cloud.spring.data.datastore.core.mapping.Field;
import com.google.cloud.Timestamp;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;

@Entity(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    @Field(name = "customer_id")
    private String customerId;

    private String status;

    private Long totalAmount;

    private Timestamp createdAt;

    @Transient
    private String displayLabel;

    public OrderEntity() {
    }

    // Getters and setters omitted for brevity.
}
~~~

Ý nghĩa:

- @Entity xác định kind.
- @Id đánh dấu ID/key của entity.
- @Field ánh xạ property Java sang tên property trong Datastore.
- @Transient đánh dấu field không lưu xuống database.

Nếu ID là Long và giá trị null, Datastore có thể cấp numeric ID tự động. Không dùng primitive long nếu cần phân biệt trạng thái chưa có ID với ID bằng 0.

### 6.4. Repository Datastore mode

~~~java
import com.google.cloud.spring.data.datastore.repository.DatastoreRepository;
import java.util.List;
import java.util.Optional;

public interface OrderRepository
        extends DatastoreRepository<OrderEntity, Long> {

    List<OrderEntity> findByCustomerId(String customerId);

    List<OrderEntity> findByCustomerIdAndStatus(
            String customerId, String status);

    Optional<OrderEntity> findFirstByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

Spring Data tạo implementation cho repository. Tập filter của Datastore mode hạn chế hơn JPA: query methods không có toàn bộ toán tử, JOIN hoặc biểu thức SQL tùy ý. Hãy kiểm tra reference theo phiên bản thư viện.

Theo reference hiện hành, query methods của Spring Data Cloud Datastore kết hợp filter bằng AND và hỗ trợ equality, not-equal, greater/greater-or-equal, less/less-or-equal và is-null. GQL/Datastore API có thêm khả năng query riêng, bao gồm composite AND/OR; không đồng nhất giới hạn của repository method với toàn bộ Datastore API.

### 6.5. Custom GQL bằng @Query

~~~java
import com.google.cloud.spring.data.datastore.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface OrderGqlRepository
        extends DatastoreRepository<OrderEntity, Long> {

    @Query("SELECT * FROM orders WHERE customer_id = @customer")
    List<OrderEntity> findOrdersByCustomer(
            @Param("customer") String customerId);
}
~~~

Tên placeholder GQL sau ký tự @ phải khớp tên @Param. Luôn bind parameter, không nối chuỗi dữ liệu người dùng vào GQL.

### 6.6. DatastoreTemplate và save semantics

DatastoreTemplate phù hợp khi cần thao tác trực tiếp với key, query, transaction hoặc tính năng không biểu đạt gọn bằng repository.

~~~java
import com.google.cloud.spring.data.datastore.core.DatastoreTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderWriteService {

    private final DatastoreTemplate datastoreTemplate;

    public OrderWriteService(DatastoreTemplate datastoreTemplate) {
        this.datastoreTemplate = datastoreTemplate;
    }

    public OrderEntity save(OrderEntity order) {
        return datastoreTemplate.save(order);
    }
}
~~~

save có semantics update-or-insert (upsert). insert thất bại nếu entity đã tồn tại. Khi cần bảo đảm entity chưa tồn tại, dùng insert hoặc business key/transaction phù hợp thay vì giả định save là INSERT thuần.

### 6.7. Transaction với DatastoreTransactionManager

Starter Datastore cung cấp DatastoreTransactionManager; repository và template có thể tham gia @Transactional:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;

    public OrderApplicationService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "datastoreTransactionManager")
    public void markPaid(Long orderId) {
        OrderEntity order = orderRepository.findById(orderId)
                .orElseThrow();
        order.setStatus("PAID");
        orderRepository.save(order);
    }
}
~~~

Không gọi performTransaction lồng bên trong method đã có @Transactional trên cùng Datastore transaction. Spring Data Cloud Datastore không hỗ trợ nested transaction theo cách tùy ý.

## 7. Spring Data Cloud Firestore cho Native mode

### 7.1. Starter Firestore Native

Spring Framework on Google Cloud cung cấp starter cho Firestore Native mode:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-firestore</artifactId>
</dependency>
~~~

Module này cung cấp Spring Data Reactive Repositories, FirestoreTemplate và Firestore client. Đây là integration riêng với Datastore mode.

Nếu chỉ muốn dùng Firestore Java client mà không cần Spring Data repository, có thể dùng spring-cloud-gcp-starter-firestore; starter này tự cấu hình bean Firestore.

### 7.2. Cấu hình Firestore Native

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

Các property thường dùng:

| Property | Ý nghĩa |
| --- | --- |
| spring.cloud.gcp.firestore.enabled | Bật/tắt Firestore autoconfiguration |
| spring.cloud.gcp.firestore.project-id | Project chứa Firestore database |
| spring.cloud.gcp.firestore.database-id | Database ID; thường là (default) |
| spring.cloud.gcp.firestore.emulator.enabled | Kết nối emulator |
| spring.cloud.gcp.firestore.host-port | Host/port Firestore service hoặc emulator |
| spring.cloud.gcp.firestore.credentials.location | Credentials riêng nếu không dùng ADC mặc định |

Dùng ADC trong local development và workload identity/service account gắn với Cloud Run, GKE hoặc Compute Engine trong production. Không đóng gói service account key JSON trong image hoặc Git.

### 7.3. Ánh xạ POJO Firestore Native

~~~java
import com.google.cloud.firestore.annotation.DocumentId;
import com.google.cloud.firestore.annotation.PropertyName;
import com.google.cloud.spring.data.firestore.Document;
import com.google.cloud.Timestamp;

import java.util.List;

@Document(collectionName = "orders")
public class OrderDocument {

    @DocumentId
    private String id;

    private String customerId;

    private String status;

    private Long totalAmount;

    private Timestamp createdAt;

    private List<String> tags;

    public OrderDocument() {
    }

    @PropertyName("customer_id")
    public String getCustomerId() {
        return customerId;
    }

    @PropertyName("customer_id")
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    // Getters and setters omitted for brevity.
}
~~~

- @Document xác định collection.
- @DocumentId đánh dấu document ID; khi ID là null, Firestore có thể sinh ID khi save.
- @PropertyName ánh xạ tên field lưu trữ.
- List/map và object con có thể được lưu thành array/map embedded trong document.

Không nhầm @DocumentId của Firestore với @Id của Datastore. Đây là hai mapping model riêng.

### 7.4. Reactive repository

Firestore Spring Data cung cấp FirestoreReactiveRepository:

~~~java
import com.google.cloud.spring.data.firestore.FirestoreReactiveRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderDocumentRepository
        extends FirestoreReactiveRepository<OrderDocument> {

    Flux<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);

    Flux<OrderDocument> findByStatusOrderByCreatedAtDesc(String status);

    Mono<OrderDocument> findFirstByCustomerId(String customerId);
}
~~~

Repository sử dụng Reactor Mono và Flux. Không gọi block() trong WebFlux request path nếu muốn giữ non-blocking flow. Nếu ứng dụng Spring MVC đồng bộ, cân nhắc dùng Firestore Java client/FirestoreTemplate hoặc chuyển đổi ở boundary có chủ đích.

### 7.5. FirestoreOperations và FirestoreTemplate

FirestoreOperations và FirestoreTemplate cung cấp API reactive cho save, read, query, delete, transaction và subcollection. Dùng template khi query method theo tên không đủ diễn đạt hoặc cần truy cập chức năng Firestore cụ thể.

Native Firestore không dùng GQL. Spring Data Cloud Firestore không hỗ trợ custom @Query theo kiểu GQL; dùng query builder hoặc native Firestore client API.

Query methods của reactive repository hỗ trợ một tập toán tử được Spring Data ánh xạ sang Firestore, ví dụ equality, not-equal, range, null, contains, in và not-in theo giới hạn của API. Các filter trong method convention được kết hợp theo AND. Nếu cần biểu thức OR hoặc tính năng query chưa được repository biểu diễn, dùng Firestore query builder/native client. Đừng suy rằng mọi method name hợp lệ trong Spring Data JPA đều chạy được ở Firestore.

Trong reference hiện hành, Spring Data Cloud Firestore chưa hỗ trợ query by example, projection và auditing. Nếu use case cần các tính năng này, dùng native client/template hoặc triển khai mapping/auditing ở tầng ứng dụng.

### 7.6. Transaction và optimistic locking

Spring Data Cloud Firestore hỗ trợ transaction qua @Transactional và ReactiveFirestoreTransactionManager của starter. Nếu ứng dụng có nhiều transaction manager, chỉ định đúng manager cho reactive transaction boundary. Firestore transaction có thể được thực thi lại khi có xung đột; callback phải tránh side effect ngoài database. Các thao tác đọc trong transaction phải diễn ra trước các thao tác ghi.

Firestore cũng có update timestamp và optimistic locking. Có thể dùng field @UpdateTime(version = true) để kiểm tra document chưa bị thay đổi kể từ lần đọc trước. Đây là cơ chế hữu ích khi nhiều request cùng cập nhật một document.

## 8. IAM, Security Rules và workload identity

### 8.1. Datastore mode: IAM cho server workload

Ứng dụng Spring Boot chạy trên server dùng ADC để xác thực với Google Cloud. Các role thường gặp:

- roles/datastore.user: quyền đọc/ghi dữ liệu cho workload.
- roles/datastore.viewer: quyền đọc dữ liệu.
- roles/datastore.owner: quyền quản trị rộng, không nên cấp cho runtime API nếu không cần.

Tách service account runtime khỏi principal migration/index administration. Không cấp Owner chỉ để ứng dụng chạy CRUD.

### 8.2. Native mode: server SDK và mobile/web SDK có mô hình bảo mật khác nhau

Firestore Native có hai kiểu truy cập thường gặp:

- **Mobile/web client SDK:** request được đánh giá bằng Firebase Authentication và Firestore Security Rules.
- **Server client SDK trong Spring Boot:** request dùng ADC và IAM. Server client libraries bỏ qua Firestore Security Rules.

Điều này rất quan trọng: viết Security Rules không tự bảo vệ request mà Spring Boot server SDK gửi. Backend phải có IAM đúng và tự kiểm tra authorization nghiệp vụ theo user/tenant đã xác thực.

### 8.3. IAM không thay thế business authorization

Service account có quyền đọc dữ liệu trong database không có nghĩa mọi người dùng API được phép xem mọi document. Backend cần kiểm tra:

- User identity từ access token/session.
- Tenant/customer ID thuộc về user.
- Quyền xem/sửa theo nghiệp vụ.
- Field nào được phép trả về.
- Không tin tenant ID do client tự gửi mà chưa xác thực.

Namespace trong Datastore mode và document path trong Firestore Native chỉ là cách tổ chức dữ liệu; chúng không tự tạo ranh giới bảo mật.

### 8.4. Bảo vệ dữ liệu và log

- Không log access token, service account key hoặc dữ liệu cá nhân đầy đủ.
- Chỉ cấp role tối thiểu cho từng service.
- Bật audit logging và monitoring theo yêu cầu tổ chức.
- Xác định retention, backup/export và deletion policy.
- Kiểm thử IAM với đúng service account của runtime, không chỉ tài khoản developer local.

## 9. Index, schema evolution và hiệu năng

### 9.1. Datastore mode

Mọi query Datastore mode dựa trên index. Cần:

1. Ghi lại query patterns của repository.
2. Tạo composite indexes cần thiết.
3. Triển khai index.yaml qua pipeline.
4. Đánh dấu property không cần query là unindexed khi phù hợp.
5. Theo dõi query latency và index build status.

Không xem việc entity schemaless là lý do bỏ qua schema contract. Hãy version hóa field và migration logic trong ứng dụng.

### 9.2. Firestore Native mode

Firestore tự tạo single-field indexes và yêu cầu composite indexes cho một số query. Quản lý index bằng cấu hình/console hoặc công cụ triển khai. Kiểm tra link tạo index từ lỗi query trong môi trường dev, review định nghĩa rồi mới đưa vào production.

Không nhúng list tăng vô hạn trong một document. Dùng subcollection khi dữ liệu con phát triển độc lập; nhớ rằng xóa parent không cascade xóa subcollection.

### 9.3. Denormalization và cập nhật nhiều document

Cả hai mode là NoSQL nên thường cần denormalize dữ liệu cho read pattern. Ví dụ order có thể lưu customerName tại thời điểm mua để render nhanh mà không cần join customer document.

Đổi lại, nếu tên customer thay đổi, các bản sao denormalized không tự đồng bộ. Cần quyết định:
- Chấp nhận snapshot tên tại thời điểm đặt hàng.
- Cập nhật fan-out bằng event/background job.
- Đọc dữ liệu customer riêng khi cần tên mới nhất.

Chọn cách lưu theo consistency requirement, không sao chép dữ liệu mà không có chiến lược đồng bộ.

## 10. Emulator và kiểm thử tích hợp

### 10.1. Datastore Emulator

Spring Data Cloud Datastore có thể tự khởi chạy Datastore Emulator:

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

Emulator phù hợp để test mapping, repository, GQL, CRUD và transaction cơ bản. Có thể dùng host/port của emulator tự chạy nếu không bật autoconfiguration.

### 10.2. Firestore Emulator

Firestore Native dùng Firebase Emulator Suite/Firestore Emulator. Ví dụ:

~~~yaml
spring:
  cloud:
    gcp:
      firestore:
        emulator:
          enabled: true
        host-port: localhost:8080
~~~

Port ở trên là ví dụ; kiểm tra port thực tế của emulator trong test environment. Starter Firestore có thể kết nối tới emulator khi cấu hình host-port tương ứng.

### 10.3. Các test cần có

| Nhóm test | Datastore mode | Firestore Native |
| --- | --- | --- |
| Mapping | @Entity, @Id, @Field, @Descendants | @Document, @DocumentId, @PropertyName |
| CRUD | DatastoreRepository/Template | FirestoreReactiveRepository/Template |
| Query | Query methods và GQL @Query | Query methods và Firestore query builder |
| Index | Built-in và composite index.yaml | Single-field/composite index |
| Relationship | Embedded, ancestor, reference | Embedded, subcollection, document reference |
| Transaction | DatastoreTransactionManager | Firestore transaction support |
| Security | IAM service account | IAM cho server SDK; Security Rules cho mobile/web |
| Integration | Datastore Emulator và sandbox thật | Firestore Emulator và sandbox thật |

Emulator không thay thế hoàn toàn kiểm thử trên project sandbox. Cần kiểm tra IAM, index provisioning, quota, concurrency và hành vi mạng với đúng runtime identity.

## 11. Migration giữa Datastore mode và Firestore Native

### 11.1. Không thể chỉ đổi starter

Hai mode có API, data model, query language, key/document ID và Spring mapping khác nhau. Việc đổi từ DatastoreRepository sang FirestoreReactiveRepository đòi hỏi thiết kế lại:

- Entity key và document ID.
- Ancestor path/descendant relationship và subcollection/document reference.
- GQL query và Firestore query builder.
- index.yaml và Firestore composite indexes.
- Transaction boundaries và concurrency assumptions.
- Namespace và tenant isolation.
- Spring synchronous repository và reactive repository.

### 11.2. Kiểm tra mode change và dữ liệu hiện hữu

Mode của database là thuộc tính cấp database. API quản lý chỉ cho phép đổi database type khi database còn rỗng. Nếu database đã có dữ liệu, hãy tạo database đích với mode phù hợp rồi lập kế hoạch export/transform/import hoặc pipeline migration riêng.

Không xóa database cũ hoặc đổi mode trên production chỉ để thử nghiệm. Trước khi migration, kiểm tra dữ liệu, index, key format, reference, query behavior và downtime/cutover requirement.

### 11.3. Các bước migration đề xuất

1. Kiểm kê kind/entity, property, namespace, key và ancestor path hiện tại.
2. Liệt kê toàn bộ query GQL, index và transaction.
3. Thiết kế collection/document/subcollection và document ID đích.
4. Xây dựng mapping và transformation có thể chạy lại.
5. Tạo database Native mode sandbox và index cần thiết.
6. Chạy export/import thử, đối chiếu số lượng và checksum/business invariants.
7. Chạy shadow read hoặc dual-write có kiểm soát nếu yêu cầu giảm downtime.
8. Kiểm thử IAM, Security Rules phía client, business authorization phía server.
9. Chuyển traffic theo kế hoạch, theo dõi error/latency và giữ phương án rollback.
10. Chỉ dừng database cũ sau khi đối chiếu và phê duyệt cutover.

Nếu ứng dụng đang dùng Datastore API vì phụ thuộc App Engine hoặc code legacy, tiếp tục Datastore mode có thể là lựa chọn hợp lý. Không cần migration chỉ vì tên sản phẩm mới là Firestore.

## 12. Chọn database theo yêu cầu

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Ứng dụng App Engine/Datastore API hiện hữu | Firestore in Datastore mode |
| Backend Spring Boot đã dùng kind/entity/key/GQL | Datastore mode + Spring Data Cloud Datastore |
| Ứng dụng mobile/web cần realtime listener và offline cache | Firestore Native mode |
| Spring Boot backend mới cần document model và reactive repository | Firestore Native + Spring Data Cloud Firestore |
| Query cần JOIN, foreign key, SQL relational phức tạp | Cloud SQL |
| Workload relational phân tán quy mô lớn, transaction liên vùng | Cloud Spanner |
| Dữ liệu document với quan hệ lỏng và query/index phù hợp | Firestore Native hoặc Datastore mode theo API/feature cần dùng |

Firestore là document database, không phải relational database thay thế cho mọi workload. Nếu use case cần join, ràng buộc quan hệ phức tạp, báo cáo SQL hoặc transaction nhiều bảng, hãy đánh giá Cloud SQL/Spanner.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| PERMISSION_DENIED | ADC sai principal hoặc thiếu IAM role | Kiểm service account runtime và roles/datastore.user/role Firestore phù hợp |
| Spring repository không được tạo | Thiếu starter hoặc scan sai package | Kiểm dependency, package và repository interface |
| Datastore mode báo không tìm thấy kind | Sai @Entity(name=...) hoặc database ID | Đối chiếu kind, project và database |
| Firestore báo không tìm thấy document | Sai collection/document path hoặc database ID | Kiểm @Document, @DocumentId và cấu hình |
| Query Datastore không chạy | Thiếu composite index hoặc filter không hỗ trợ | Kiểm GQL, index.yaml và index đã deploy |
| Firestore query yêu cầu index | Thiếu composite index | Tạo index được gợi ý, review và triển khai |
| Native Firestore không có GQL | Đang dùng @Query Datastore cho Native mode | Dùng query method hoặc Firestore query builder |
| Xóa parent nhưng còn child | Subcollection không cascade delete | Viết recursive delete hoặc background cleanup |
| Transaction conflict | Nhiều request ghi cùng entity/document | Rút ngắn transaction, retry có giới hạn và idempotency |
| Local chạy nhưng Cloud Run lỗi | Emulator không dùng IAM/network thật | Test trên sandbox bằng workload identity |
| Đổi mode thất bại | Database đã có dữ liệu | Tạo database đích và migration dữ liệu |
| Backend nghĩ Security Rules đang bảo vệ | Server client SDK bỏ qua Security Rules | Cấu hình IAM và business authorization ở backend |

## 14. Bài tập thực hành

### Bài A — Nhận diện mode

Tạo một Firestore database sandbox. Ghi lại database type, database ID và location. Xác minh API/client library nào được dùng cho mode đã chọn.

### Bài B — Spring Data Datastore

Thêm spring-cloud-gcp-starter-data-datastore. Tạo OrderEntity với @Entity, @Id, @Field. Xây dựng repository tìm đơn theo customer và status; thêm GQL @Query có parameter.

### Bài C — Spring Data Firestore Native

Tạo database Native mode. Thêm spring-cloud-gcp-starter-data-firestore, ánh xạ OrderDocument bằng @Document và @DocumentId. Viết reactive repository trả về Flux<OrderDocument> và thử query theo status.

### Bài D — So sánh quan hệ

Mô hình hóa Order và OrderItem theo ba cách: embedded, Datastore ancestor/descendant và Firestore subcollection. Đo số lần đọc, cách xóa parent và khả năng query child độc lập.

### Bài E — Index và query

Tạo query lọc theo customer, status và sort theo thời gian. Xác định composite index cần thiết ở mỗi mode. Kiểm thử lỗi khi thiếu index và triển khai index qua pipeline.

### Bài F — Transaction và idempotency

Viết thao tác xác nhận đơn và cập nhật audit/event trong transaction. Giả lập conflict và retry; xác minh callback không gửi message trùng. Đề xuất outbox pattern nếu cần publish event.

### Bài G — Security

Chạy backend bằng service account riêng có role tối thiểu. Với Native mode, kiểm tra server SDK dùng IAM thay vì Security Rules. Viết business authorization theo customer/tenant ID.

### Bài H — Migration plan

Lập bảng mapping từ Kind/Entity/Key/Namespace/Ancestor sang Collection/Document/Document ID/Subcollection/Reference. Xây dựng một batch migration thử và kiểm tra số lượng, key mapping, field types và query results.

### Câu hỏi tự kiểm tra

1. Cloud Datastore và Firestore liên hệ với nhau như thế nào?
2. Firestore in Datastore mode khác Native mode ở API nào?
3. Database mode được chọn ở cấp nào?
4. Kind, entity, property và key tương ứng với khái niệm nào trong mô hình Native?
5. Namespace có phải ranh giới bảo mật tenant không?
6. Khi nào nên dùng ancestor/descendant trong Datastore mode?
7. Subcollection khác embedded array như thế nào?
8. Vì sao xóa document cha không tự xóa subcollection?
9. GQL khác Firestore query builder ở điểm nào?
10. Vì sao Datastore mode cần composite index?
11. Spring Data Cloud Datastore có tương thích Firestore Native không?
12. Spring Data Cloud Firestore dùng repository kiểu nào?
13. Vì sao @Query GQL không dùng được cho Native mode?
14. Strong consistency có phải lý do để chọn một mode thay mode kia không?
15. Server Firestore client library có áp dụng Security Rules không?
16. Khi nào cần roles/datastore.user?
17. Vì sao transaction callback phải idempotent?
18. Vì sao không thể đổi mode của database đang có dữ liệu chỉ bằng cấu hình?
19. Khi nào nên chọn Cloud SQL hoặc Spanner thay Firestore?
20. Những phần nào của ứng dụng phải thay đổi khi migration Datastore mode sang Native mode?

**Kết quả mong đợi:** người học phân biệt chính xác Firestore in Datastore mode và Native mode, chọn đúng Spring starter/repository, thiết kế data model và index theo query pattern, cấu hình IAM/ADC an toàn, kiểm thử bằng emulator và lập được kế hoạch migration có kiểm soát.

## Tài liệu tham khảo

- [Choose between Firestore APIs](https://docs.cloud.google.com/datastore/docs/firestore-or-datastore)
- [Create and manage Firestore databases](https://docs.cloud.google.com/firestore/native/docs/manage-databases)
- [Datastore overview](https://docs.cloud.google.com/datastore/docs/concepts/overview)
- [Datastore entities, properties and keys](https://docs.cloud.google.com/datastore/docs/concepts/entities)
- [Datastore indexes](https://docs.cloud.google.com/datastore/docs/concepts/indexes)
- [Datastore transactions](https://docs.cloud.google.com/datastore/docs/concepts/transactions)
- [Datastore queries and filters](https://docs.cloud.google.com/datastore/docs/concepts/queries)
- [Firestore Native data model](https://docs.cloud.google.com/firestore/native/docs/data-model)
- [Firestore transactions and batched writes](https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions)
- [Firestore IAM for server client libraries](https://docs.cloud.google.com/firestore/native/docs/security/iam)
- [Spring Data Cloud Datastore reference](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.1/reference/html/datastore.html)
- [Spring Data Cloud Firestore reference](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.1/reference/html/index.html)

