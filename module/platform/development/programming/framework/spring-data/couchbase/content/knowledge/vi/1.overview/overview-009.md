# Phạm vi kiến thức, điều kiện đầu vào và thứ tự học Spring Data Couchbase

## 1. Bài học này giúp bạn định hướng điều gì?

**Spring Data Couchbase** là một phần trong hệ sinh thái Spring Data, giúp ứng dụng Java/Spring truy cập Couchbase thông qua **document mapping**, **Repository**, **CouchbaseTemplate** và truy vấn **SQL++**. Để dùng thành thạo, người học không chỉ cần biết gọi `save()` hay `findById()` mà còn phải hiểu **bucket, scope, collection, document ID, index, TTL, CAS, giao dịch, reactive API, consistency và vận hành**.

Bài học thuộc chương **Tổng quan**, trả lời ba câu hỏi định hướng:

1. **Phạm vi nào cần học?** Những khả năng và giới hạn nào của Spring Data Couchbase thuộc mục tiêu của module?
2. **Cần biết gì trước khi bắt đầu?** Nền tảng Java, Spring, JSON, NoSQL, mạng và môi trường chạy nào là điều kiện tiên quyết?
3. **Nên học theo thứ tự nào?** Vì sao cần hiểu document key trước Repository, index trước tối ưu SQL++ và consistency trước khi xử lý giao dịch?

Kết quả mong đợi là một **bản đồ học tập có thể kiểm chứng**. Bạn có thể dựa vào nó để tự đánh giá mức sẵn sàng, chọn bài tiếp theo và biết mình đã đạt năng lực triển khai một tầng truy cập Couchbase hay chưa.

> **Nguyên tắc xuyên suốt:** Học theo *đường dữ liệu và yêu cầu nghiệp vụ*, không chỉ theo tên API. API càng thuận tiện thì càng cần hiểu những gì vẫn xảy ra ở Couchbase Server.

## 2. Mục tiêu năng lực cuối module

Sau khi hoàn thành lộ trình, người học cần có thể làm những việc sau ở một dự án Spring Boot:

| Năng lực | Bằng chứng có thể kiểm tra |
| --- | --- |
| **Mô hình hóa document** | Giải thích vì sao một đơn hàng embed các dòng hàng, nhưng lịch sử đơn được lưu thành nhiều document |
| **Định vị dữ liệu** | Chọn đúng bucket/scope/collection và tạo document ID ổn định |
| **Ánh xạ Java ↔ JSON** | Dùng `@Document`, `@Id`, `@Field` và kiểm tra JSON được lưu đúng như mong đợi |
| **CRUD bằng Repository** | Tạo, đọc, sửa, xóa document theo key với lỗi rõ ràng |
| **Truy vấn SQL++** | Viết điều kiện lọc/sắp xếp có tham số và thiết kế secondary index phù hợp |
| **Dùng Template/SDK** | Nêu được trường hợp nào nên dùng `CouchbaseTemplate` hay Couchbase Java SDK thay Repository |
| **Bảo vệ cập nhật đồng thời** | Giải thích CAS/`@Version`, tái hiện và xử lý optimistic-locking conflict |
| **Điều khiển vòng đời dữ liệu** | Áp dụng TTL cho session, không xóa nhầm dữ liệu nghiệp vụ lâu dài |
| **Nhất quán và giao dịch** | Phân biệt KV read, độ mới của SQL++ index, durability và transaction đa document |
| **Lựa chọn sync/reactive** | Giữ pipeline WebFlux non-blocking khi cần, nhưng không lạm dụng reactive cho mọi bài toán |
| **Vận hành an toàn** | Cấu hình xác thực, quyền truy cập, timeout, quan sát latency, retry và kiểm thử tích hợp |

**Hoàn thành mục tiêu** không đồng nghĩa chỉ chạy được một ứng dụng CRUD. Bạn cần giải thích **vì sao** chọn một API hay index và dự đoán điều gì có thể hỏng khi tăng tải hoặc có hai request cập nhật cùng document.

## 3. Phạm vi học: từ mô hình dữ liệu đến vận hành

Có thể xem nội dung thành sáu nhóm kiến thức phụ thuộc lẫn nhau.

~~~mermaid
flowchart TD
    A["Nền tảng: Java, Spring, JSON, Couchbase"] --> B["Document model: bucket/scope/collection/ID"]
    B --> C["Mapping và CRUD: Repository/Template"]
    C --> D["SQL++ + secondary index"]
    C --> E["CAS + TTL + transaction"]
    D --> F["Consistency + đo hiệu năng"]
    E --> F
    F --> G["Reactive, kiểm thử và vận hành"]
~~~

### 3.1. Nhóm A — Couchbase và JSON document

Cần hiểu:

- Couchbase lưu và truy cập document theo **document ID** trong một **collection** thuộc **scope** và **bucket**.
- **Document ID là metadata**, không nhất thiết là field `id` trong JSON body.
- JSON hỗ trợ object lồng nhau và array; khi thiết kế phải chọn dữ liệu **embed** hay **tham chiếu ID**.
- Document có vòng đời riêng: có thể tạo, thay thế, xóa hoặc hết hạn qua expiry.
- Khả năng tìm theo key khác với tìm theo field hay toàn văn.

Đây là nhóm bắt buộc học trước Repository; nếu không, bạn có thể dùng `findById` nhưng vẫn đặt ID sai, nhầm collection hoặc thiết kế một document khổng lồ.

### 3.2. Nhóm B — Spring Data Couchbase mapping và APIs

Nội dung cốt lõi:

- Cấu hình Spring Boot, connection, bucket, scope/collection và bean cần thiết.
- `@Document`, `@Id`, `@Field`, `@Version`; custom conversion/schema evolution ở mức phù hợp.
- `CouchbaseRepository` cho CRUD entity và các phương thức truy vấn.
- `CouchbaseTemplate` cho những thao tác hoặc truy vấn lập trình linh hoạt.
- Couchbase Java SDK cho KV/SQL++/Search và các option ở mức thấp hơn.
- Cách dịch lỗi database sang lỗi nghiệp vụ/HTTP phù hợp.

**Giới hạn cần nhớ:** Spring Data Couchbase thực hiện object–document mapping, **không có persistence context và dirty checking kiểu JPA**. Sửa object Java đã đọc không tự ghi xuống Couchbase nếu không gọi một thao tác lưu/cập nhật thích hợp.

### 3.3. Nhóm C — Truy vấn và chỉ mục

Người học cần phân biệt:

| Đường truy cập | Câu hỏi giải quyết | Điều kiện |
| --- | --- | --- |
| **KV** | “Đọc document có ID này” | Biết key và collection chính xác |
| **SQL++** | “Lọc/sắp xếp/tổng hợp document theo field JSON” | Truy vấn và index phù hợp |
| **Search/FTS** | “Tìm văn bản gần đúng, xếp hạng liên quan” | Search index và analyzer phù hợp |

Trọng tâm chính của module là **KV và SQL++ thông qua Spring Data**, trong đó có thiết kế secondary index, xem `EXPLAIN`, phân trang và query consistency. Search/FTS là nội dung liên quan để nhận biết khi **SQL++ không phải công cụ tốt nhất cho tìm kiếm ngôn ngữ tự nhiên**; không cần chuyên sâu xây một search engine hoàn chỉnh trong giai đoạn nền tảng.

### 3.4. Nhóm D — Đúng đắn dữ liệu

- **CAS/optimistic locking:** tránh một request ghi đè thay đổi mới hơn trên cùng document.
- **TTL/expiry:** quản lý vòng đời session/token/cache mà không nhầm với field JSON tùy ý.
- **Durability:** yêu cầu mức xác nhận ghi phù hợp.
- **Transaction:** hỗ trợ workflow nhiều document cần cùng thành công/thất bại theo API/phiên bản đang dùng.
- **Consistency:** hiểu khác biệt giữa KV theo ID và query qua index vừa cập nhật.

Đây là nhóm quan trọng ngang với CRUD; thiếu nó, ứng dụng có thể hoạt động tốt khi thử một người nhưng sai khi hai người cùng thao tác.

### 3.5. Nhóm E — Chọn mô hình đồng bộ hoặc phản ứng

- API đồng bộ: `CouchbaseRepository`, `CouchbaseTemplate`, SDK sync.
- API reactive: `ReactiveCouchbaseRepository`, `ReactiveCouchbaseTemplate`, SDK reactive/async.
- `Mono`, `Flux`, `map`, `flatMap`, `zip`, backpressure và giới hạn mức đồng thời.
- Không dùng `block()` trong pipeline non-blocking hoặc `Mono.just(blockingCall())` để giả lập reactive.

**Reactive không làm thiếu index biến mất.** Mục đích của nó chủ yếu là điều phối I/O và tài nguyên thread dưới tải đồng thời.

### 3.6. Nhóm F — Kiểm thử và vận hành

- Test mapping thực, không chỉ mock Repository.
- Test generated SQL++ và index với dữ liệu đại diện.
- Thử CAS conflict, expiry, timeout, lỗi kết nối và sự khác nhau về query consistency.
- Theo dõi latency p95/p99, lỗi, retry, hot key, document size và tài nguyên Couchbase Data/Query/Index Service.
- Bảo vệ credential, phân quyền theo ứng dụng/tenant và kiểm soát dữ liệu nhạy cảm trong log.

## 4. Những chủ đề liên quan nhưng nằm ngoài trọng tâm ban đầu

Một lộ trình hiệu quả cần xác định cả những gì **chưa cần học sâu ngay**.

| Chủ đề | Mức cần biết ở module này | Khi nào học sâu hơn? |
| --- | --- | --- |
| Quản trị cluster nhiều vùng, topology phức tạp | Biết dịch vụ, network, scaling và failover ảnh hưởng client | Khi phụ trách platform/SRE |
| Thiết kế tìm kiếm toàn văn nâng cao | Biết phân biệt SQL++ và FTS | Khi xây sản phẩm search với ranking/analyzer phức tạp |
| Eventing/Analytics/Vector Search | Biết đây là các khả năng riêng của hệ sinh thái Couchbase khi phù hợp phiên bản | Khi use case cụ thể yêu cầu |
| Định tuyến cross-region, XDCR | Nhận diện liên quan vận hành/khôi phục dữ liệu | Khi triển khai đa vùng |
| Xây một framework repository riêng | Không cần | Khi abstraction hiện tại không đáp ứng yêu cầu lặp lại |
| Tối ưu JVM ở mức rất thấp | Chỉ theo dõi GC, heap, thread và pool | Khi profiling cho thấy bottleneck |
| Transaction phân tán qua nhiều hệ thống thanh toán | Hiểu idempotency và giới hạn database transaction | Khi thiết kế workflow production đa dịch vụ |

Phần ngoài phạm vi **không phải không quan trọng**. Đây là cách giữ thứ tự học hợp lý: làm chủ các thao tác phổ biến, bảo đảm tính đúng đắn rồi mới đầu tư các nhánh chuyên sâu theo nhu cầu.

## 5. Điều kiện đầu vào về Java và Spring

### 5.1. Java bắt buộc

Người học nên sử dụng được:

1. Class, interface, constructor, getter/setter, access modifier.
2. Generic types như `Optional<Customer>`, `List<Order>` và `CouchbaseRepository<Customer, String>`.
3. Annotation và cách annotation metadata được framework sử dụng.
4. Exception, `try/catch`, xử lý validation và luồng lỗi.
5. `java.time`, thời gian UTC, đối tượng bất biến, kiểu số cho tiền.
6. `Maven` hoặc `Gradle` để quản lý dependency/build.
7. Khái niệm thread, blocking, timeout và race condition ở mức căn bản.

Bạn **không cần biết sâu cơ chế nội bộ JVM** trước khi học, nhưng phải hiểu tại sao hai thread sửa cùng một giá trị có thể gây lost update.

### 5.2. Spring và Spring Boot bắt buộc

Cần hiểu:

- Dependency injection qua constructor.
- `@Component`, `@Service`, `@Repository` và quản lý bean.
- Cách Spring Boot cấu hình datasource hoặc client qua properties/environment.
- Controller/service/repository và trách nhiệm mỗi tầng.
- HTTP status, request validation và exception handling.
- Kiểm thử cơ bản với JUnit và Spring Boot Test.
- Sự khác biệt mức khái niệm giữa Spring MVC và Spring WebFlux.

Nếu đã biết Spring Data JPA, bạn sẽ nhận ra giao diện Repository và annotation `@Id`, nhưng **đừng suy rằng Couchbase có dirty checking hoặc `EntityManager` giống JPA**.

### 5.3. Checklist tự kiểm tra nền Java/Spring

| Câu hỏi | Nếu chưa trả lời được |
| --- | --- |
| Làm thế nào inject một Repository vào service bằng constructor? | Ôn Spring DI |
| Vì sao không nên tạo một connection/client mới cho mỗi HTTP request? | Ôn bean lifecycle và tài nguyên mạng |
| `Optional.empty()` khác exception kết nối như thế nào? | Ôn kiểu kết quả và xử lý lỗi |
| `@Transactional` liên quan gì đến phạm vi giao dịch? | Ôn nguyên lý transaction, không mặc định JPA semantics |
| Khi nào dùng `long`/decimal thay `double` cho tiền? | Ôn mô hình kiểu số |
| Nếu hai request cùng đọc rồi ghi, điều gì có thể xảy ra? | Ôn race condition, optimistic locking |

Nếu còn yếu 2–3 ý, vẫn có thể học song song, nhưng nên làm bài tập nền ngắn trước khi viết thao tác mutation có concurrency.

## 6. Điều kiện đầu vào về dữ liệu và Couchbase

Nên có các khái niệm sau:

| Kiến thức | Mức độ cần thiết |
| --- | --- |
| **JSON** | Biết object, array, kiểu string/number/boolean/null; phân biệt field không tồn tại với field có giá trị null |
| **Key–value** | Hiểu một key chính xác định vị một giá trị; biết sự khác nhau với tìm theo field |
| **SQL căn bản** | `SELECT`, `WHERE`, `ORDER BY`, `LIMIT`, `JOIN` và parameter binding |
| **Index** | Hiểu index giúp tìm kiếm có điều kiện, đổi lại chi phí cập nhật/lưu trữ |
| **Transaction** | Hiểu atomicity, lost update, retry và isolation ở mức ý tưởng |
| **Mạng và security** | Host, port, TLS, timeout, username/password, quyền tối thiểu |
| **Document database** | Hiểu embed vs reference và vì sao không dịch nguyên sơ đồ bảng thành JSON |

SQL++ có cú pháp quen thuộc với SQL nhưng làm việc trên dữ liệu JSON; không cần thành thạo toàn bộ ngôn ngữ từ đầu. Chỉ cần biết query theo field, tạo index và đọc kết quả `EXPLAIN` ở các bước sau.

**Phân biệt hay bị nhầm:**

~~~text
Document metadata:
  bucket: shop
  scope: crm
  collection: customers
  document ID: customer::c-1001

JSON body:
  {
    "fullName": "Nguyen An",
    "email": "an@example.com",
    "status": "ACTIVE"
  }
~~~

Ở đây `customer::c-1001` không phải field JSON tên `id`. `findById("customer::c-1001")` có key để đi KV; `findByEmail("an@example.com")` phải tìm theo field nên thường sử dụng SQL++/index.

## 7. Điều kiện môi trường trước khi chạy mã

Hãy chuẩn bị môi trường học tập **tách biệt production**:

- **JDK** đúng với phiên bản Spring Boot và Spring Data Couchbase đã chọn.
- **Maven hoặc Gradle**; IDE có hỗ trợ Java và xem log/test.
- **Couchbase Server hoặc môi trường Couchbase tương thích** có Data/Query/Index Service theo bài thực hành; Search Service chỉ cần nếu tập tìm kiếm toàn văn.
- **Bucket, scope và collection** dùng cho bài tập, tài khoản có quyền truy cập phù hợp; dùng tài khoản ít quyền nhất đủ cho các bài cần chạy.
- **Kết nối mạng/TLS** và credential có thể được cấp qua environment/secret, không commit password thật.
- Công cụ thực hiện truy vấn SQL++ và kiểm tra query plan, chẳng hạn giao diện quản trị/Query Workbench hoặc API tương đương.
- Dữ liệu mẫu dễ tái tạo và có thể xóa an toàn; phân biệt dữ liệu dev/test với dữ liệu nghiệp vụ thật.

### 7.1. Kiểm tra tương thích phiên bản

Đừng sao chép nguyên dependency của một hướng dẫn cũ rồi mặc định chạy được. Hãy xác nhận **bộ phiên bản**:

~~~text
Java Runtime
   -> Spring Boot
      -> Spring Data Couchbase
         -> Couchbase Java SDK
            -> Couchbase Server
~~~

Sử dụng dependency management/BOM của Spring Boot phù hợp để tránh xung đột version thủ công. Kiểm tra tài liệu tương ứng về annotation collection mapping, transaction integration, reactive support, SSL/TLS và option expiry/CAS. Nhiều đoạn mã trong tài liệu học là **minh họa nguyên lý**; API cụ thể phải khớp stack đang chạy.

### 7.2. Ví dụ cấu hình Spring Boot

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
}
~~~

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: YOUR_COUCHBASE_USERNAME
    password: YOUR_COUCHBASE_PASSWORD
  data:
    couchbase:
      bucket-name: shop
~~~

Thay placeholder bằng cơ chế secret/environment phù hợp. Chọn scope/collection bằng annotation/configuration của phiên bản đang dùng; `bucket-name` không tự xác định mọi collection mong muốn.

**Tiêu chí môi trường sẵn sàng:** ứng dụng khởi động được, xác thực thành công, thực hiện ít nhất một KV get/insert trong collection thử nghiệm và có thể chạy một truy vấn SQL++ đơn giản. Nếu các bước này chưa xong, không nên kết luận một query Repository “không hoạt động” do logic Java.

## 8. Thứ tự học đề xuất: từ KV tới vận hành

Thứ tự dưới đây ưu tiên **quan hệ phụ thuộc kiến thức**, không phải số ngày cố định. Có thể dành nhiều hay ít thời gian tùy nền tảng người học.

| Chặng | Chủ đề | Vì sao học ở đây? | Đầu ra thực hành |
| --- | --- | --- | --- |
| **0** | Môi trường, JSON, Couchbase services | Chưa kết nối được thì không thể kiểm chứng mã | Cluster dev + collection test hoạt động |
| **1** | Bucket, scope, collection, document ID; embed/reference | Phải biết document ở đâu và mang cấu trúc gì | Sơ đồ dữ liệu khách hàng–đơn hàng |
| **2** | Mapping, Repository, KV CRUD | Cách đơn giản nhất để đi từ Java đến JSON | CRUD theo ID, đọc lại chính document |
| **3** | SQL++, secondary index, phân trang | CRUD theo key không giải quyết lọc danh sách | Query lịch sử đơn + `EXPLAIN` |
| **4** | `CouchbaseTemplate` và SDK | So sánh abstraction khi đã hiểu đường KV/query | Một thao tác bằng Repository và một thao tác qua Template/SDK |
| **5** | CAS, TTL, durability, consistency | Cần xử lý đúng đắn khi dữ liệu biến động | Test lost-update; session expiry; query sau ghi |
| **6** | Transaction và idempotency | Mở rộng từ một document sang workflow nhiều document | Thiết kế tạo đơn/trừ tồn kho và retry an toàn |
| **7** | Sync vs reactive | Chỉ có ý nghĩa khi đã hiểu thao tác I/O cần compose | Reactive read/write pipeline đơn giản |
| **8** | Kiểm thử tích hợp và vận hành | Xác nhận tính đúng đắn lẫn hiệu năng thực tế | Bộ test, metric, runbook lỗi phổ biến |

### 8.1. Vì sao không bắt đầu bằng Reactive?

Nếu người học chưa phân biệt KV với SQL++, sẽ khó biết một `Flux<Order>` đang thực hiện index query hay thao tác KV nào. Reactive là mô hình **điều phối I/O**, không thay logic truy cập Couchbase. Học đọc/ghi đồng bộ trước giúp nhìn rõ document ID, index, CAS và lỗi; sau đó chuyển các luồng tương tự sang `Mono`/`Flux`.

Ngoại lệ hợp lý: nếu đang làm một dự án WebFlux đã vận hành, có thể học song song hai API ngay từ đầu, nhưng vẫn phải hiểu các tiền đề ở chặng 1–5.

### 8.2. Vì sao CAS phải học trước transaction?

CAS giải quyết **xung đột trên một document** và giúp nhận thức về ghi đồng thời. Transaction giải quyết các bất biến cần phối hợp **nhiều document**. Nếu chưa hiểu hai request cùng đọc một trạng thái cũ rồi ghi, người học dễ hiểu nhầm rằng một loạt lệnh `save` tự an toàn chỉ vì chạy trong service Spring.

## 9. Sơ đồ phụ thuộc kỹ năng

~~~mermaid
flowchart TD
    J["Java + Spring DI"] --> MAP["Document mapping"]
    JSON["JSON + Couchbase keyspace"] --> MAP
    JSON --> KV["KV theo ID"]
    MAP --> REPO["Repository CRUD"]
    KV --> REPO
    SQL["SQL căn bản"] --> SQLPP["SQL++ + index"]
    REPO --> SQLPP
    REPO --> CAS["CAS / optimistic locking"]
    REPO --> TTL["TTL / expiry"]
    SQLPP --> CONS["Query consistency"]
    CAS --> TX["Transaction và idempotency"]
    CONS --> TX
    REPO --> R["Reactive Repository/Template"]
    R --> OPS["Load test / observability"]
    TX --> OPS
    TTL --> OPS
~~~

Đây là thứ tự kỹ năng đề xuất; không phải dependency kỹ thuật bắt buộc giữa mọi API. Ví dụ, Couchbase Java SDK có thể dùng ngay từ đầu, nhưng học nó **sau** khi hiểu KV giúp phân biệt vấn đề do model với vấn đề do lớp trừu tượng.

## 10. Mốc thực hành 1 — Thiết kế document và CRUD

### 10.1. Bài toán mẫu

Xây một ứng dụng nhỏ quản lý khách hàng và đơn hàng:

- `Customer`: ID, tên, email, trạng thái.
- `Order`: ID, customer ID, trạng thái, thời điểm tạo, danh sách `OrderLine`.
- Dữ liệu khách hàng nằm trong `shop.crm.customers`; đơn hàng nằm trong `shop.sales.orders`.
- ID theo quy ước `customer::c-001` và `order::o-001`.

Hãy trả lời trước khi viết code:

1. Vì sao Order chứa `customerId` thay vì embed toàn bộ lịch sử Order trong Customer?
2. Vì sao Order nên chứa snapshot `unitPrice` tại thời điểm mua?
3. ID nào cho phép đọc thẳng qua KV mà không cần secondary index?

### 10.2. Mapping tối thiểu

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Customer {
    @Id
    private String id;

    @Field
    private String fullName;

    @Field
    private String email;

    @Version
    private Long version;

    public Customer() {}

    // Bổ sung constructor, getters/setters trong dự án thực.
}
~~~

Ví dụ chỉ thể hiện annotation cốt lõi. Nếu cần scope/collection riêng, thêm mapping theo cách được phiên bản Spring Data hỗ trợ. Spring Data có thể ghi metadata type/discriminator trong JSON; hãy **xem document thực tế** thay vì giả định body luôn giống mọi ví dụ.

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {
}
~~~

Tự kiểm tra:

- `save(customer)` tạo/lưu document đúng collection.
- `findById("customer::c-001")` đọc lại đúng ID.
- `deleteById` và `existsById` phản ánh đúng kết quả; phân biệt not-found với lỗi network.
- Sửa object Java sau `findById` **không tự ghi** nếu không gọi `save`/operation cập nhật.
- `@Version` phải được dùng/kiểm thử phù hợp khi cập nhật cạnh tranh.

**Mốc đạt:** giải thích và chứng minh được ánh xạ key ↔ Java entity ↔ JSON body.

## 11. Mốc thực hành 2 — SQL++ và index

Giả sử bảng lịch sử cần liệt kê 20 đơn mới nhất của một khách hàng. Mỗi đơn có:

~~~json
{
  "customerId": "c-001",
  "createdAt": "2026-11-25T03:00:00Z",
  "status": "PAID",
  "totalVnd": 320000
}
~~~

Metadata document ID ví dụ `order::o-001`.

Truy vấn SQL++ minh họa:

~~~sql
SELECT META(o).id AS documentId, o.customerId,
       o.createdAt, o.status, o.totalVnd
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Một chỉ mục khởi đầu:

~~~sql
CREATE INDEX ix_orders_customer_date
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Các điều kiện để **thực sự đạt mốc**:

- Truyền `$customerId` như tham số, không nối chuỗi input trực tiếp thành SQL++.
- `EXPLAIN` cho thấy một kế hoạch thực thi phù hợp, không scan rộng không cần thiết.
- Không tải toàn bộ Order vào Java rồi mới lọc/phân trang.
- Biết index tạo thêm chi phí cập nhật/lưu trữ.
- Phân biệt derived query do Spring Data sinh (có thể kèm metadata type) với SQL++ minh họa.
- Phân biệt read theo ID qua KV với query theo field qua Query/Index Service.

**Mốc đạt:** tự giải thích được index nào phục vụ query nào và lý do `findById` không cần secondary index.

## 12. Mốc thực hành 3 — CAS, TTL và consistency

### 12.1. Test mất cập nhật

Tạo một Order ở trạng thái `CREATED`, dùng hai request đọc cùng document:

~~~text
A đọc Order, CAS = C1
B đọc Order, CAS = C1
A sửa status, save thành công -> CAS = C2
B save object cũ với C1 -> conflict khi dùng optimistic locking
~~~

Học viên cần thấy **một lỗi ghi có chủ đích** là điều tốt: CAS giúp ngăn mất thay đổi của A. Sau đó chọn cách ứng dụng xử lý conflict:

- Trả 409 Conflict để người dùng làm mới.
- Hoặc đọc lại, áp dụng lại thao tác và retry có giới hạn khi nghiệp vụ an toàn.

Không retry cùng một object với CAS cũ vô hạn. Không lặp gửi email/thu tiền trong callback retry.

### 12.2. Test session expiry

Tạo session document có TTL ngắn ở collection session riêng. Xác nhận tài liệu bị hết hạn theo policy và phân biệt:

~~~json
{ "expiresAt": "2026-11-25T04:00:00Z" }
~~~

với **expiry metadata** thực sự. Một field `expiresAt` do ứng dụng ghi vào body **không tự khiến Couchbase xóa document**. Sau khi sửa session, kiểm tra policy giữ hoặc thay expiry bằng API/phiên bản đang dùng.

### 12.3. Test read-after-write

Ghi Order mới và so sánh:

1. `findById(orderKey)` — KV theo key.
2. `findByCustomerId(customerId)` — SQL++ qua index.

Query index có thể chưa bắt kịp mutation nếu dùng consistency mặc định. Hãy thử cơ chế scan consistency thích hợp (chẳng hạn `request_plus` hoặc theo mutation token nếu phiên bản hỗ trợ) và đo thời gian chờ. **CAS, TTL, query consistency và durability trả lời các câu hỏi khác nhau**, không thay thế nhau.

**Mốc đạt:** mô tả được ít nhất ba lỗi có thể xảy ra ở concurrency/vòng đời/độ mới dữ liệu và cách phát hiện chúng bằng test.

## 13. Mốc thực hành 4 — Template, SDK và reactive

### 13.1. Repository so với Template

Repository giúp khai báo `findById`, `save` và các derived query. `CouchbaseTemplate` hữu ích khi cần lập trình các thao tác/truy vấn linh hoạt trên entity mà vẫn tận dụng mapper/converter của Spring Data. Couchbase Java SDK phù hợp khi cần API KV chuyên sâu, Search, option đặc thù hoặc dữ liệu thô.

**Bài tập:** Viết một hàm tìm Customer theo key bằng Repository và một hàm tương đương bằng Template. So sánh:

- Keyspace mà mỗi hàm sử dụng.
- Cách JSON được mapping thành Customer.
- Kiểu lỗi/giá trị trả về khi không có document.
- Độ trễ thực tế khi cùng truy cập theo KV (không mặc định API nào nhanh hơn).

### 13.2. Chuyển một luồng sang reactive

~~~java
import reactor.core.publisher.Mono;
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {
}

public class CustomerReadService {
    private final ReactiveCustomerRepository repository;

    public CustomerReadService(ReactiveCustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> find(String id) {
        return repository.findById("customer::" + id);
    }
}
~~~

Kết quả `Mono<Customer>` biểu diễn 0–1 customer bất đồng bộ. Trong WebFlux, trả Publisher về handler; tránh `block()` và không tự `subscribe()` rồi bỏ qua lỗi. Khi cần hai truy vấn độc lập, có thể phối hợp `Mono.zip`; khi gọi thao tác lưu tiếp theo, dùng `flatMap`.

**Mốc đạt:** giải thích được vì sao `Mono.just(syncRepository.findById(id))` **vẫn blocking**, và đưa ra phương án reactive thực sự khi stack hỗ trợ.

## 14. Mốc thực hành 5 — Giao dịch, idempotency và lỗi production

Giả sử thao tác đặt hàng mở rộng thành:

~~~text
1. Xác minh Customer ACTIVE
2. Kiểm tra tồn kho
3. Giảm tồn kho trong Inventory document
4. Tạo Order document
5. Gọi payment provider bên ngoài
~~~

Không thể mặc định một loạt lời gọi `repository.save(...)` tự có **atomicity đa document**. Cần chọn transaction Couchbase được hỗ trợ bởi phiên bản stack hoặc workflow có bước bù trừ khi thiết kế yêu cầu. Lệnh gọi payment provider nằm **ngoài** transaction dữ liệu Couchbase thông thường: cần idempotency, cơ chế ghi nhận trạng thái và xử lý retry an toàn.

Một bộ câu hỏi bắt buộc:

- Nếu bước 4 lỗi sau khi bước 3 thành công, tồn kho còn đúng không?
- Nếu network timeout sau khi ghi thành công nhưng client không biết, retry tạo đơn có tạo trùng không?
- Nếu một khách click “Đặt hàng” hai lần, request có idempotency key không?
- Nếu Order đã `CONFIRMED`, thao tác xác nhận lặp sẽ trả gì?
- Nếu SQL++ chưa thấy đơn mới ngay, có được phép coi đơn chưa được tạo không?

**Mốc đạt:** trình bày được một sơ đồ trạng thái của đặt hàng, các điểm commit, cách kiểm tra kết quả khi timeout và phương án ngăn thao tác bị lặp.

## 15. Lộ trình khác nhau theo nền tảng người học

### 15.1. Người mới với Spring Data

**Đề xuất:** Ôn Java/Spring DI → JSON/keyspace → CRUD Repository → SQL++/index → Template/SDK → CAS/TTL/consistency → transaction → reactive → vận hành.

Đừng bắt đầu bằng việc copy một service reactive phức tạp khi chưa biết `save` đi tới collection nào.

### 15.2. Người đã biết Spring Data JPA

**Có thể đi nhanh hơn** ở phần DI, Repository và validation, nhưng phải dành thời gian cho:

- **Document ID** thay vì column primary key.
- **Embed vs reference** thay vì `@OneToMany` / khóa ngoại theo mặc định.
- **Không có JPA persistence context/dirty checking** cho document đã đọc.
- **`@Version`/CAS** và semantics ghi của Couchbase.
- **KV vs SQL++/index**, không suy luận từ JPQL/Hibernate.
- **Transaction** và query consistency khác những giả định JPA thông thường.

Bài tập chuyển đổi nên là một domain nhỏ (customer/order), không dịch nguyên mọi bảng/association vào một JSON document.

### 15.3. Người đang vận hành ứng dụng Spring WebFlux

Bạn có thể học Repository reactive song song với CRUD, nhưng phải:

1. Giữ mọi thành phần pipeline có thể non-blocking.
2. Hiểu Publisher subscription/lifecycle và các operator ghép I/O.
3. Đo concurrency, backpressure, timeout và memory.
4. Không bỏ qua index, CAS hay transaction vì đã dùng Reactor.

### 15.4. Người phụ trách hệ thống/DevOps

Tập trung sớm vào credential/RBAC, cluster services, sizing, network/TLS, index build, observability, timeout/retry và backup/khôi phục theo yêu cầu. Tuy nhiên vẫn cần hiểu ID và query plan để giải thích vì sao một API gây tải cho Data Service hay Query Service.

## 16. Các ngộ nhận phải sửa trước khi học phần nâng cao

| Ngộ nhận | Kiến thức cần sửa |
| --- | --- |
| “Couchbase chỉ là một JSON database nên không cần thiết kế schema” | JSON linh hoạt nhưng vẫn cần hợp đồng dữ liệu, định danh và schema evolution |
| “`@Id` là trường JSON bình thường” | `@Id` của Spring Data Couchbase thường ánh xạ document key metadata |
| “Repository nào cũng truy vấn bằng SQL++” | `findById` thường đi KV; derived query theo field thường là SQL++ |
| “Có secondary index thì mọi query nhanh” | Index phải phù hợp điều kiện, sắp xếp, projection và dữ liệu; cần `EXPLAIN` |
| “`save` xong thì danh sách query chắc chắn thấy ngay” | KV và secondary index có cơ chế cập nhật/consistency khác nhau |
| “`@Version` hoặc CAS làm nhiều document thành transaction” | CAS chủ yếu bảo vệ cập nhật cùng một document |
| “`@Transactional` khiến mọi POJO đã sửa tự flush như JPA” | Spring Data Couchbase không có JPA dirty checking |
| “TTL là một field `expiresAt` trong JSON” | TTL là expiry metadata/cấu hình của document |
| “Dùng reactive sẽ luôn nhanh hơn synchronous” | Lợi ích phụ thuộc tải I/O; index, server và logic vẫn là nút thắt |
| “Bất kỳ lỗi timeout nào cũng có thể retry lệnh tạo đơn” | Có thể đã commit; cần idempotency và kiểm tra trạng thái |

Bạn nên giải thích được bảng này **bằng ví dụ cụ thể**, không chỉ ghi nhớ định nghĩa.

## 17. Cách tự đánh giá tiến độ

Chấm từng năng lực theo thang 0–3:

- **0 — Chưa biết:** chưa giải thích đúng khái niệm.
- **1 — Nhận biết:** giải thích được nhưng chưa tự thực hiện.
- **2 — Thực hành:** tự triển khai và test trên môi trường học tập.
- **3 — Vận dụng:** giải thích được đánh đổi và xử lý được lỗi/tải đại diện.

| Năng lực | Điểm tự chấm |
| --- | --- |
| JSON document, embed/reference | 0 / 1 / 2 / 3 |
| Bucket/scope/collection/document ID | 0 / 1 / 2 / 3 |
| Mapping Java ↔ Couchbase | 0 / 1 / 2 / 3 |
| Repository CRUD, lỗi not-found | 0 / 1 / 2 / 3 |
| SQL++/secondary index/`EXPLAIN` | 0 / 1 / 2 / 3 |
| Template/SDK selection | 0 / 1 / 2 / 3 |
| CAS/optimistic locking | 0 / 1 / 2 / 3 |
| TTL/durability/consistency | 0 / 1 / 2 / 3 |
| Transaction/idempotency | 0 / 1 / 2 / 3 |
| Sync vs reactive | 0 / 1 / 2 / 3 |
| Integration testing/observability | 0 / 1 / 2 / 3 |

**Quy tắc gợi ý:** Ở các năng lực cốt lõi *document ID, Repository CRUD, SQL++/index, CAS*, cố gắng đạt ít nhất **mức 2** trước khi coi đã hoàn thành phần nền tảng. Năng lực reactive có thể ở mức 1 nếu dự án hiện tại chỉ dùng Spring MVC, nhưng phải hiểu khi nào chọn nó.

Thang điểm này là **khung tự học đề xuất**, không phải chứng chỉ hay chuẩn đánh giá chính thức.

## 18. Kế hoạch capstone nhỏ cuối module

Một sản phẩm luyện tập có thể đặt tên **Customer & Order API**, với hai collection `customers` và `orders`:

~~~mermaid
flowchart TD
    UI["REST API"] --> S["Application Services"]
    S --> CR["CustomerRepository"]
    S --> OR["OrderRepository"]
    S --> Q["OrderQueryDao: Template khi cần"]
    S --> GW["KV Gateway: SDK khi cần"]
    CR --> CB[("Couchbase cluster")]
    OR --> CB
    Q --> CB
    GW --> CB
~~~

### 18.1. Chức năng tối thiểu

1. Tạo customer, đọc customer theo ID, cập nhật email.
2. Tạo order với item snapshot và total được tính ở server.
3. Xem order theo ID.
4. Liệt kê order của customer với `LIMIT`/pagination và index phù hợp.
5. Đổi trạng thái order bằng optimistic locking.
6. Tạo session tạm có TTL ở collection riêng.
7. Tạo integration test cho mapping, query, CAS, lỗi và expiry.
8. Ghi một trang “quyết định kỹ thuật” giải thích các lựa chọn API/index/consistency.

### 18.2. Tiêu chí nghiệm thu

| Tiêu chí | Cách xác minh |
| --- | --- |
| CRUD đúng keyspace | Document xuất hiện ở collection mong đợi, ID rõ ràng |
| Mapping đúng | Đọc lại JSON/entity khớp trường và kiểu |
| Lịch sử đơn có giới hạn | Query có `LIMIT`/pagination; không lọc toàn bộ bằng Java |
| Index hiệu quả | Có `EXPLAIN`/quan sát query sử dụng index thích hợp |
| Chống lost update | Test hai request cho thấy một xung đột được xử lý |
| TTL có hiệu lực | Session hết hạn theo policy; Order không có TTL ngắn tùy tiện |
| Idempotency | Request tạo đơn lặp không vô ý tạo giao dịch trùng |
| Query sau ghi | Có policy rõ khi index chưa bắt kịp mutation |
| Security | Không lưu secret trong repo, có kiểm soát quyền trên document |
| Observability | Có log/metric cho latency, timeout, conflict, query lỗi |

**Không cần làm một hệ thống thương mại điện tử hoàn chỉnh**. Giá trị của capstone nằm ở việc chứng minh đúng lựa chọn kỹ thuật, nhất quán dữ liệu và khả năng kiểm thử.

## 19. Bộ câu hỏi kiểm tra trước khi bước vào module

**Câu 1.** Sự khác nhau giữa document ID và trường `email` trong JSON là gì?

*Document ID là khóa metadata để truy cập KV theo key; email là field nghiệp vụ cần query/index nếu chỉ biết email.*

**Câu 2.** Nếu `findById` hoạt động nhưng `findByEmail` chậm/lỗi, nên kiểm tra gì?

*Xác nhận collection, generated SQL++, secondary index, query plan và quyền dịch vụ Query/Index.*

**Câu 3.** Vì sao không nên nhét toàn bộ lịch sử Order vào Customer document?

*Lịch sử tăng liên tục, làm phình document, tăng chi phí cập nhật và contention; các Order có vòng đời độc lập.*

**Câu 4.** `@Version` giúp gì và không giúp gì?

*Giúp optimistic locking/CAS khi sửa cùng document; không tự biến nhiều document hoặc external API thành transaction nguyên tử.*

**Câu 5.** Chỉ thêm `expiresAt` trong JSON có đủ để document tự hết hạn không?

*Không; phải cấu hình expiry/TTL metadata bằng API tương ứng.*

**Câu 6.** `Mono<Customer>` có tự làm một truy vấn thiếu index nhanh hơn không?

*Không. Reactive chủ yếu thay đổi cách điều phối I/O; query plan/index vẫn phải tối ưu.*

**Câu 7.** Khi hai request cùng tạo Order và gặp timeout, làm sao tránh đơn trùng?

*Dùng idempotency key, quy tắc định danh/ghi có điều kiện và kiểm tra trạng thái cuối trước khi retry.*

**Câu 8.** Vì sao phải xem bộ phiên bản Spring Boot–Spring Data Couchbase–SDK–Server?

*Annotation, cấu hình, API transaction/reactive và các option KV/consistency có thể thay đổi giữa phiên bản; cần dùng stack tương thích.*

## 20. Kết luận: học theo tính đúng đắn và đường truy cập

Lộ trình **Spring Data Couchbase** nên bắt đầu từ Java/Spring và JSON, tiếp đến **bucket/scope/collection, document ID và access pattern**; sau đó học **mapping, Repository, SQL++/index, Template/SDK**, rồi **CAS, TTL, consistency, transaction và reactive**, cuối cùng là **kiểm thử tích hợp và vận hành**.

Chìa khóa không phải thuộc thật nhiều annotation mà là thiết kế được **một luồng dữ liệu đúng**: biết document nào phải đọc/ghi, dùng KV hay SQL++, khi nào cần index, dữ liệu có thể bị cập nhật cạnh tranh hay hết hạn không, lỗi nào cần retry và lúc nào cần transaction. Khi chứng minh được những quyết định này bằng một ứng dụng nhỏ, người học có đủ nền tảng để mở rộng Spring Data Couchbase thành tầng truy cập dữ liệu hiệu quả, nhất quán và có khả năng vận hành trong dự án thực tế.
