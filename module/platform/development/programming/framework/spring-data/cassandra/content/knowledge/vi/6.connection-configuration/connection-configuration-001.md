# Spring Boot starter cho truy cập Cassandra đồng bộ và phản ứng

Khi phát triển ứng dụng **Spring Data Cassandra**, lựa chọn đầu tiên là cách kết nối và truy cập **Apache Cassandra**: gọi theo kiểu **đồng bộ (synchronous/blocking)** hay **phản ứng (reactive/nonblocking)**. Spring Boot cung cấp starter để quản lý thư viện, tạo bean kết nối, cấu hình Spring Data và tích hợp repository/template. Chọn starter đúng giúp tập trung vào entity mapping, thiết kế bảng theo truy vấn, CQL, partition key, consistency, paging và hiệu năng của hệ thống phân tán thay vì tự ghép toàn bộ hạ tầng kết nối.

Bài thuộc chương **Cấu hình kết nối**. Nội dung sử dụng cách đặt cấu hình và tên starter phổ biến của **Spring Boot 3.x / Spring Data Cassandra tương thích**. Phiên bản Spring Boot khác có thể đổi namespace thuộc tính, dependency hoặc API; cần đối chiếu tài liệu đúng version thực tế trước khi áp dụng nguyên văn.

## 1. Starter làm được gì, không làm được gì?

Một **Spring Boot starter** là tập phụ thuộc đã được lựa chọn để dùng cùng nhau, cộng với cơ chế auto-configuration của Spring Boot. Sau khi thêm starter và cung cấp cấu hình Cassandra, ứng dụng thường có thể nhận các bean của tầng truy cập dữ liệu qua dependency injection.

| Vai trò | Trách nhiệm |
| --- | --- |
| Spring Boot starter | Kéo các thư viện tương thích vào classpath và kích hoạt auto-configuration theo điều kiện |
| Java Driver for Apache Cassandra | Kết nối cluster, xác thực, gửi CQL, định tuyến tới replica, quản lý connection pool, timeout và retry |
| Spring Data Cassandra | Mapping đối tượng Java với bảng, repository và template |
| Ứng dụng | Xác định schema, partition key, truy vấn CQL, giới hạn paging và chính sách nhất quán phù hợp |

Starter **không tự tạo cluster Cassandra**, không bảo đảm keyspace đã tồn tại và không biến một truy vấn thiếu partition key thành truy vấn hiệu quả. Nó cũng không biến Cassandra thành cơ sở dữ liệu quan hệ: thiết kế bảng thường bắt đầu từ **những truy vấn ứng dụng cần thực hiện**, không từ mô hình JOIN.

## 2. Hai starter: synchronous và reactive

Trong các bản Spring Boot 3.x, hai starter thường dùng là:

| Nhu cầu | Maven artifact | API chính | Kiểu kết quả |
| --- | --- | --- | --- |
| Truy cập **đồng bộ** | `spring-boot-starter-data-cassandra` | `CassandraRepository`, `CassandraTemplate`, `CassandraOperations` | Đối tượng, `List<T>`, `Optional<T>`… |
| Truy cập **phản ứng** | `spring-boot-starter-data-cassandra-reactive` | `ReactiveCassandraRepository`, `ReactiveCassandraTemplate`, `ReactiveCassandraOperations` | `Mono<T>`, `Flux<T>` |

**Đồng bộ (blocking):** khi gọi repository hoặc `CassandraTemplate`, luồng gọi thường chờ thao tác I/O hoàn tất rồi mới tiếp tục. Mô hình này phù hợp ứng dụng Spring MVC, batch jobs hoặc code nghiệp vụ tuần tự, đơn giản.

**Phản ứng (reactive):** API trả `Mono` hoặc `Flux`, xây dựng luồng xử lý bất đồng bộ dựa trên các khả năng nonblocking của driver và Reactor. Phù hợp hệ thống đã dùng WebFlux hoặc cần phối hợp nhiều I/O không chặn luồng với mức đồng thời cao.

**Không có kết luận “reactive luôn nhanh hơn”.** Với truy vấn đơn lẻ, độ trễ chủ yếu còn phụ thuộc thiết kế partition, kết nối mạng, replica, consistency level và kích thước kết quả. Reactive có thể cải thiện khả năng sử dụng luồng khi có nhiều yêu cầu đồng thời, nhưng làm tăng yêu cầu quản lý backpressure và chuỗi xử lý bất đồng bộ.

Hai starter đều làm việc với **cùng dữ liệu Cassandra**, không phải hai giao thức lưu trữ khác nhau. Nếu dự án thực sự cần cả hai API, có thể cấu hình chúng cùng tồn tại theo khả năng của phiên bản; tuy nhiên nên chọn một mô hình chủ đạo, tránh vô tình gọi repository blocking trên luồng xử lý reactive.

## 3. Thêm dependency bằng Maven hoặc Gradle

Ví dụ Maven cho ứng dụng **synchronous** có Spring Boot quản lý phiên bản dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
</dependency>
~~~

Nếu ứng dụng sử dụng **reactive**, chọn starter tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
~~~

Ví dụ Gradle Groovy DSL:

~~~groovy
// Chọn một trong hai theo cách truy cập dữ liệu chính.
implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
// Hoặc:
// implementation 'org.springframework.boot:spring-boot-starter-data-cassandra-reactive'
~~~

Nếu tạo REST API, `spring-boot-starter-web` thường đi cùng mô hình MVC đồng bộ; `spring-boot-starter-webflux` thường đi cùng mô hình reactive. WebFlux không bắt buộc chỉ để dùng một `ReactiveCassandraRepository` trong tầng service; ngược lại, chỉ thêm WebFlux cũng **không làm** `CassandraRepository` trở thành nonblocking.

Trong dự án do Spring Boot quản lý dependency, tránh tự gắn phiên bản không tương thích cho Spring Data, Cassandra driver hoặc Reactor nếu chưa có lý do rõ ràng. Nếu gặp `ClassNotFoundException` hoặc `NoSuchMethodError` sau khi thêm starter, hãy kiểm tra xung đột phiên bản trong dependency tree trước khi sửa logic truy vấn.

## 4. Chuẩn bị Cassandra và keyspace

Trước khi chạy ứng dụng, cần có Cassandra cluster hoạt động, port CQL có thể truy cập, **datacenter name** đúng và keyspace mà ứng dụng được phép sử dụng.

Ví dụ dùng Cassandra một datacenter cho **môi trường học tập**: giả sử datacenter thực tế tên `datacenter1`. Tạo keyspace và bảng bằng `cqlsh` hoặc công cụ quản trị tương đương:

~~~sql
CREATE KEYSPACE IF NOT EXISTS training_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 1
};

CREATE TABLE IF NOT EXISTS training_ks.events_by_tenant_day (
    tenant_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    description text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
~~~

Ví dụ chọn **RF = 1 chỉ cho cụm học tập**; hệ thống production phải chọn replication phù hợp với số node, datacenter, khả năng chịu lỗi và yêu cầu vận hành. Không mặc định tên datacenter là `datacenter1`: phải kiểm tra cấu hình thực tế của cluster rồi thay ở cả CQL và Spring Boot.

Trong bảng trên, `(tenant_id, event_day)` là **composite partition key**; `occurred_at` và `event_id` là clustering columns. Một tenant trong một ngày là một partition; ngày khác đi vào partition khác. Đây là ví dụ có thể dùng chung để so sánh đồng bộ và reactive.

Nếu keyspace chưa tồn tại, ứng dụng không nhất thiết tự tạo nó khi startup. Ở production, quản lý schema bằng quy trình triển khai/migration được kiểm soát, với quyền ứng dụng giới hạn theo chức năng.

## 5. Cấu hình kết nối Spring Boot

Ví dụ `application.yml` cho **Spring Boot 3.x** và cluster CQL nội bộ:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: training_ks
    schema-action: none
~~~

Giải thích từng thuộc tính:

| Thuộc tính | Ý nghĩa và kiểm tra |
| --- | --- |
| `spring.cassandra.contact-points` | Địa chỉ các node seed/contact point mà driver có thể kết nối khi khởi tạo |
| `spring.cassandra.port` | Port CQL của contact point, thường là `9042` nếu cluster dùng cấu hình mặc định |
| `spring.cassandra.local-datacenter` | Datacenter của ứng dụng; phải khớp **tên datacenter thực** mà driver nhìn thấy |
| `spring.cassandra.keyspace-name` | Keyspace mặc định cho mapping và các CQL không ghi đủ keyspace |
| `spring.cassandra.schema-action` | Chọn cách Spring Data quản lý schema; `none` giúp ứng dụng không tự sửa schema khi khởi động |

**Lưu ý tương thích phiên bản:** ví dụ trên dùng namespace `spring.cassandra.*` của Spring Boot 3.x. Một số dự án cũ dùng `spring.data.cassandra.*`; không sao chép xen lẫn cấu hình giữa các phiên bản. Hãy kiểm tra phiên bản Spring Boot đang chạy và configuration metadata tương ứng.

Trong môi trường mạng/container, `127.0.0.1` là địa chỉ bên trong **process/container của ứng dụng**. Nếu Cassandra chạy ở container hoặc host khác, cần dùng tên host/IP có thể phân giải từ **nơi ứng dụng thực sự chạy**; `localhost` trong container ứng dụng không tự trỏ tới container Cassandra.

### Xác thực bằng secrets và kết nối mã hóa

Nếu cluster yêu cầu username/password, có thể cung cấp qua biến môi trường hoặc secret manager thay vì ghi thông tin nhạy cảm vào mã nguồn:

~~~yaml
spring:
  cassandra:
    username: ${CASSANDRA_USERNAME}
    password: ${CASSANDRA_PASSWORD}
~~~

Trong ví dụ, `CASSANDRA_USERNAME` và `CASSANDRA_PASSWORD` là tên các biến môi trường phải được cấp khi chạy ứng dụng. Không commit giá trị thật vào Git, log hoặc tài liệu.

Với Cassandra cloud hoặc cluster yêu cầu TLS/mTLS, certificate trust, secure connect bundle, proxy hay cách xác thực riêng, dùng **hướng dẫn của nhà cung cấp và driver phiên bản đang chạy**. Chỉ cấu hình `contact-points` và `port` không đủ cho mọi dịch vụ Cassandra được quản lý. Không tắt xác minh chứng chỉ để xử lý lỗi kết nối ở production.

## 6. Auto-configuration tạo những gì?

Khi Spring Boot thấy starter, cấu hình hợp lệ và các điều kiện classpath phù hợp, quá trình tự động cấu hình có thể cung cấp:

~~~text
application.yml / environment / secrets
                 |
                 v
         Spring Boot auto-config
                 |
                 v
            CqlSession (driver)
                 |
          +------+------+
          |             |
          v             v
   CassandraTemplate   ReactiveCassandraTemplate
   CassandraRepository ReactiveCassandraRepository
          |             |
          +------+------+
                 v
       Cassandra cluster / replicas
~~~

Đây là sơ đồ **khái niệm**, không có nghĩa cả hai template và hai repository luôn cùng được tạo trong mọi ứng dụng. Những bean thực tế phụ thuộc starter, cấu hình repository scan, phiên bản Spring Data và các bean tùy biến do dự án cung cấp.

**Driver session:** `CqlSession` của Java Driver quản lý giao tiếp với cluster và có khả năng gửi truy vấn đồng bộ hoặc bất đồng bộ. Tái sử dụng session do Spring quản lý; đừng tạo một session mới ở mỗi HTTP request.

**Template:** `CassandraTemplate` và `ReactiveCassandraTemplate` cung cấp tầng thao tác dữ liệu theo Spring Data, có thể hỗ trợ query tùy chỉnh. Chúng dùng cho những tình huống repository method không tiện thể hiện logic CQL.

**Repository:** Spring Data tạo implementation từ interface khai báo phù hợp, cho phép viết CRUD và các query có cấu trúc rõ ràng. Dù dùng repository, điều kiện truy vấn vẫn phải tuân thủ **quy tắc partition/clustering key** của Cassandra.

Trong đa số dự án có cấu trúc package chuẩn dưới `@SpringBootApplication`, Boot có thể tự tìm component và repository. Nếu entity/repository ở package ngoài phạm vi quét mặc định, cần cấu hình quét rõ ràng phù hợp với phiên bản; tránh thêm annotation bật repository một cách máy móc khi auto-configuration đã làm việc đúng.

## 7. Entity mapping dùng chung cho hai cách truy cập

Để minh họa hai starter, ta dùng một entity duy nhất khớp với bảng `training_ks.events_by_tenant_day` đã tạo.

~~~java
@PrimaryKeyClass
public class EventKey implements Serializable {

    @PrimaryKeyColumn(
        name = "tenant_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "event_day",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(
        name = "occurred_at",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(
        name = "event_id",
        ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private UUID eventId;

    // Constructor, getter/setter, equals/hashCode phù hợp với mapping.
}

@Table("events_by_tenant_day")
public class EventRow {

    @PrimaryKey
    private EventKey key;

    @Column("description")
    private String description;

    // Constructor và accessor phù hợp với mapping.
}
~~~

Các import được lược bỏ để tập trung vào cấu trúc: `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@PrimaryKey`, `@Table`, `@Column` thuộc Spring Data Cassandra; `PrimaryKeyType` và `Ordering` thuộc hỗ trợ CQL. Entity thực tế cần constructor/accessor và giá trị khóa phù hợp với cơ chế mapping của phiên bản đang dùng.

Điểm quan trọng nhất: **hai cột `tenant_id` và `event_day` cùng là partition key**. Nếu truy vấn chỉ theo `event_day` hoặc chỉ theo `description`, dù repository method có vẻ hợp lệ trong Java, Cassandra có thể từ chối truy vấn hoặc yêu cầu lọc rất tốn kém.

## 8. Truy cập đồng bộ với CassandraRepository và CassandraTemplate

Nếu chọn `spring-boot-starter-data-cassandra`, repository trả kết quả kiểu Java đồng bộ.

~~~java
public interface SyncEventRepository
        extends CassandraRepository<EventRow, EventKey> {

    @Query("SELECT * FROM events_by_tenant_day " +
           "WHERE tenant_id = ?0 AND event_day = ?1 LIMIT 50")
    List<EventRow> recentForDay(UUID tenantId, LocalDate day);
}
~~~

Ví dụ service:

~~~java
@Service
public class SyncEventService {
    private final SyncEventRepository repository;

    public SyncEventService(SyncEventRepository repository) {
        this.repository = repository;
    }

    public List<EventRow> recent(UUID tenantId, LocalDate day) {
        return repository.recentForDay(tenantId, day);
    }
}
~~~

Khi `recent(...)` được gọi, luồng hiện tại chờ kết quả truy vấn được hoàn thành. Điều này dễ hiểu trong ứng dụng MVC nhưng cần giới hạn số request đồng thời, connection pool và timeout khi triển khai tải lớn.

Với thao tác theo khóa đầy đủ, có thể dùng `CassandraTemplate`:

~~~java
@Service
public class SyncEventLookup {
    private final CassandraTemplate template;

    public SyncEventLookup(CassandraTemplate template) {
        this.template = template;
    }

    public EventRow find(EventKey key) {
        return template.selectOneById(key, EventRow.class);
    }
}
~~~

Ví dụ template minh họa cách đọc theo toàn bộ primary key. Nếu cần logic truy vấn CQL phức tạp hơn, nên tạo query có **điều kiện partition key đầy đủ** và dùng API query/template phù hợp; đừng giả định Spring sẽ tự phân phối truy vấn lọc tùy ý tới đúng partition.

## 9. Truy cập phản ứng với ReactiveCassandraRepository và ReactiveCassandraTemplate

Nếu chọn `spring-boot-starter-data-cassandra-reactive`, repository trả `Mono` hoặc `Flux` để chuỗi xử lý tiếp tục theo mô hình Reactor:

~~~java
public interface ReactiveEventRepository
        extends ReactiveCassandraRepository<EventRow, EventKey> {

    @Query("SELECT * FROM events_by_tenant_day " +
           "WHERE tenant_id = ?0 AND event_day = ?1 LIMIT 50")
    Flux<EventRow> recentForDay(UUID tenantId, LocalDate day);
}
~~~

Service có thể biến đổi dữ liệu mà không chặn luồng chờ truy vấn:

~~~java
@Service
public class ReactiveEventService {
    private final ReactiveEventRepository repository;

    public ReactiveEventService(ReactiveEventRepository repository) {
        this.repository = repository;
    }

    public Flux<EventRow> recent(UUID tenantId, LocalDate day) {
        return repository.recentForDay(tenantId, day)
                .filter(row -> row.getDescription() != null);
    }
}
~~~

Ví dụ giả định entity có getter `getDescription()`. `Flux` mô tả luồng kết quả, còn `Mono` mô tả tối đa một phần tử. Khi được subscribe theo cách phù hợp (ví dụ qua pipeline WebFlux), truy vấn và xử lý tiếp tục theo semantics phản ứng.

Ví dụ tương đương với template:

~~~java
@Service
public class ReactiveEventLookup {
    private final ReactiveCassandraTemplate template;

    public ReactiveEventLookup(ReactiveCassandraTemplate template) {
        this.template = template;
    }

    public Mono<EventRow> find(EventKey key) {
        return template.selectOneById(key, EventRow.class);
    }
}
~~~

Trong một handler WebFlux, nên **trả Publisher cho framework** thay vì gọi `subscribe()` thủ công rồi quên quản lý lifecycle, lỗi và kết quả. Tránh gọi `block()`/`blockFirst()` trên event-loop; tương tự, bọc repository đồng bộ bằng `Mono.just(repository.find...)` **không làm I/O trở thành nonblocking**. Việc chuyển một call blocking qua scheduler có thể là biện pháp tương thích trong một số trường hợp, nhưng không tương đương driver reactive thực sự.

Reactive stream có thể truyền tín hiệu backpressure, nhưng backpressure **không loại bỏ** chi phí đọc partition lớn, tombstone, CQL thiếu khóa hoặc quá nhiều trang dữ liệu. Giới hạn tổng lượng công việc, concurrency và kích thước response vẫn cần được thiết kế.

## 10. So sánh luồng xử lý một HTTP request

~~~text
Đồng bộ:
HTTP request -> MVC thread -> CassandraRepository
             -> driver gửi CQL -> đợi kết quả
             -> trả List/EventRow -> HTTP response

Phản ứng:
HTTP request -> WebFlux handler -> ReactiveCassandraRepository
             -> Mono/Flux -> driver gửi CQL nonblocking
             -> dữ liệu phát qua pipeline -> HTTP response
~~~

| Tiêu chí | Đồng bộ | Reactive |
| --- | --- | --- |
| Cách viết service | Phương thức trả giá trị trực tiếp | Phương thức trả `Mono`/`Flux` |
| Thread khi chờ I/O | Thường bị chiếm để chờ | Có thể phục vụ công việc khác khi I/O đang chờ |
| Độ khó debug | Dễ lần stack lời gọi tuần tự | Cần hiểu chuỗi Publisher và signal lỗi |
| Paging | Điều hướng từng trang/kết quả qua driver hoặc API Spring Data | Điều hướng dòng kết quả và paging qua API reactive phù hợp |
| Hạn chế dữ liệu | Vẫn cần partition key và giới hạn kết quả | Vẫn cần partition key và giới hạn kết quả |
| Hợp với | Spring MVC, batch hoặc nghiệp vụ tuần tự | WebFlux, nhiều I/O bất đồng bộ, concurrency cao |

Chọn mô hình dựa trên **toàn bộ call chain**. Nếu controller và service đang xử lý nhiều lời gọi JPA/JDBC blocking, đổi riêng Cassandra repository sang reactive không tự biến hệ thống thành nonblocking. Ngược lại, nếu API đã đi theo WebFlux, nên tránh để thao tác Cassandra đồng bộ chặn event-loop.

## 11. Connection pool, timeout, retry và consistency

Cấu hình `contact-points` đủ cho bản demo, nhưng không đủ để đánh giá vận hành. Cassandra driver quản lý phiên kết nối đến node, discovery/topology, request timeout, retry và các option khác. Các tùy chọn nâng cao thường được cung cấp qua cấu hình driver và/hoặc customizer của Spring Boot, tùy phiên bản.

Các quyết định cần được xác định theo workload:

| Nhóm cấu hình | Vấn đề giải quyết | Lưu ý |
| --- | --- | --- |
| Contact points và local datacenter | Khởi tạo kết nối, định tuyến | Sai `local-datacenter` có thể khiến session không tạo được |
| Authentication và TLS | Truy cập cluster an toàn | Tài khoản/secret/certificate phải khớp môi trường |
| Request timeout | Thời gian chờ thao tác CQL | Timeout quá ngắn gây thất bại giả; quá dài giữ request quá lâu |
| Pool/concurrency | Kiểm soát kết nối, yêu cầu đồng thời | Không tăng vô hạn; đo p95/p99 và sức chịu tải của node |
| Retry policy | Xử lý một số lỗi tạm thời | Chỉ retry khi hiểu tính idempotent, mức tải và tác động duplicate |
| Consistency level | Số replica cần phản hồi đọc/ghi | Phụ thuộc RF, datacenter và SLA |

**Replication factor (RF)** là số replica mục tiêu của partition trong datacenter; **consistency level (CL)** là yêu cầu phản hồi của thao tác. Ví dụ production RF = 3 trong một datacenter, `LOCAL_QUORUM` đòi hỏi phản hồi từ đa số replica cục bộ (2 trong 3); `ONE` yêu cầu ít phản hồi hơn. Không đặt `ALL` chỉ vì “an toàn” mà bỏ qua bài toán tính sẵn sàng. Các lựa chọn CL cụ thể phải dựa trên yêu cầu đọc/ghi, khả năng chịu lỗi và mô hình nhất quán Cassandra.

Đối với thao tác ghi có thể bị retry, hãy thiết kế **primary key ổn định** để tránh tạo hàng logic mới ngoài ý muốn. Tuy nhiên Cassandra dùng timestamp và last-write-wins ở các trường hợp thông thường; retry không thể được đánh đồng với giao dịch ACID tuyến tính hóa.

Các ví dụ trong bài không cố định property tùy biến timeout/pool vì **tên thuộc tính ở tầng Java Driver và cách tích hợp vào Spring Boot thay đổi theo version**. Khi triển khai, hãy lấy đúng tài liệu Java Driver đang sử dụng và xác nhận các setting thực sự được nạp; tránh đưa các khóa YAML chưa được Spring/driver nhận diện vào production.

## 12. Paging và thiết kế truy vấn có ảnh hưởng gì tới kết nối?

Cả repository đồng bộ lẫn reactive đều không sửa được một CQL thiếu partition key. Với bảng ví dụ, truy vấn hiệu quả thường có dạng:

~~~sql
SELECT occurred_at, event_id, description
FROM training_ks.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT 50;
~~~

Nó xác định rõ một partition của một tenant/ngày. Ngược lại, tìm mọi sự kiện có cùng `description` nhưng không biết tenant/ngày không phù hợp bảng này. Dùng `ALLOW FILTERING` để “cho chạy được” có thể khiến hệ thống phải đọc và lọc quá nhiều dữ liệu, tạo request chậm bất kể đã bật reactive.

**Phân trang Cassandra** chủ yếu dựa trên trạng thái trang (paging state) của driver, không phải random-access offset rẻ như một số hệ cơ sở dữ liệu quan hệ. Có ba điểm cần nhớ:

1. `LIMIT 50` giới hạn tổng số hàng trả về cho câu truy vấn minh họa; còn fetch/page size điều chỉnh cách driver nhận dữ liệu theo từng đợt.
2. Paging state cần gắn với truy vấn và tham số đã dùng; không thể thay keyspace, điều kiện hoặc sort rồi tái sử dụng tùy ý.
3. Kết quả đang được ghi/xóa song song không nhất thiết là snapshot bất biến qua nhiều lần lấy trang; reactive `Flux` cũng không bảo đảm điều đó.

Đối với lịch sử nhiều ngày, mỗi `event_day` là một partition riêng. Ứng dụng phải xác định các bucket cần đọc, giới hạn số partition, hợp nhất thứ tự và quản lý continuation state; không nên giả định một `PageRequest` offset sẽ tự thực hiện việc này an toàn và nhanh.

## 13. Các lỗi cấu hình thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Ứng dụng báo không kết nối được contact point | Cassandra chưa chạy, DNS/port sai hoặc network không thông | Kiểm tra endpoint CQL từ **máy/container chạy ứng dụng** |
| `local-datacenter` không khớp hoặc không nhận node | Datacenter trong cấu hình khác tên cluster | Kiểm tra tên datacenter do driver/cluster báo |
| `Unauthorized`/authentication error | Sai tài khoản, thiếu quyền keyspace/bảng | Kiểm tra secret, policy, quyền CQL |
| Lỗi TLS/handshake | Truststore/certificate/hostname mismatch | Kiểm tra certificate và cấu hình kết nối mã hóa |
| `Keyspace ... does not exist` | Chưa tạo keyspace hoặc sai tên | Kiểm tra keyspace tồn tại và cấu hình `keyspace-name` |
| Mapping lỗi tên cột/kiểu dữ liệu | Entity không khớp CQL schema | Kiểm tra tên bảng, tên cột, primary key và kiểu Java/CQL |
| Repository không được tạo | Package không nằm trong vùng scan, thiếu starter/điều kiện auto-config | Xem dependency, component scan và auto-configuration |
| `NoSuchMethodError` ở driver/Spring Data | Phụ thuộc phiên bản không tương thích | Kiểm tra dependency tree/BOM và starter |
| Truy vấn chạy nhưng chậm | Partition lớn, tombstone, nhiều bucket, CL hoặc tải node cao | Kiểm tra CQL, partition size, metrics, p95/p99 |
| Reactive endpoint không cải thiện concurrency | Có `block()` hoặc thư viện blocking trong chain | Kiểm tra luồng xử lý end-to-end, thread và operator Reactor |

Để phân biệt **lỗi kết nối** với **lỗi thiết kế query**, hãy kiểm tra theo trình tự: cluster có thể truy cập từ nơi chạy ứng dụng → xác thực/TLS → local DC và keyspace → startup/mapping → CQL theo partition key → độ trễ, timeout và metrics. Không tăng timeout liên tục để che giấu truy vấn quét dữ liệu.

## 14. Tình huống lựa chọn starter

**Tình huống A — Spring MVC quản lý lịch sử đơn hàng.** Ứng dụng phục vụ lưu lượng vừa phải, service chủ yếu tuần tự, các thư viện khác cũng blocking. Chọn `spring-boot-starter-data-cassandra`, `CassandraRepository` và `CassandraTemplate` thường đơn giản hơn để phát triển và vận hành.

**Tình huống B — WebFlux cung cấp luồng sự kiện cho nhiều client.** API đã dùng Reactor/WebFlux, truy vấn theo tenant và ngày, muốn không chiếm thread trong lúc chờ I/O Cassandra. Chọn `spring-boot-starter-data-cassandra-reactive`, `ReactiveCassandraRepository` và `ReactiveCassandraTemplate`; giới hạn mức đồng thời, số hàng, paging và chuỗi xử lý.

**Tình huống C — Đội ngũ chỉ muốn đổi starter để hết lỗi timeout.** Nếu cùng CQL đang đọc partition khổng lồ hoặc quét nhiều partition, đổi sang reactive không xử lý nguyên nhân. Trước hết đánh giá lại partition key, phạm vi truy vấn, dữ liệu/tombstone, paging, CL và trạng thái replica.

### Tự kiểm tra

**Câu 1.** Ứng dụng dùng Spring MVC, muốn gọi repository và nhận `List<EventRow>` trực tiếp. Starter nào phù hợp?

**Đáp án:** `spring-boot-starter-data-cassandra` với `CassandraRepository` đồng bộ.

**Câu 2.** Service WebFlux cần trả luồng sự kiện mà không chặn I/O chờ Cassandra. API nào phù hợp?

**Đáp án:** `ReactiveCassandraRepository`/`ReactiveCassandraTemplate` với `Flux` hoặc `Mono` trong một pipeline reactive.

**Câu 3.** Vì sao khai báo `spring.cassandra.local-datacenter: datacenter1` có thể thất bại dù port 9042 đang mở?

**Đáp án:** Cluster thực tế có thể dùng tên datacenter khác; driver cần cấu hình datacenter phù hợp với topology.

**Câu 4.** Nếu đã dùng reactive repository, có thể truy vấn mọi event theo `description` trên bảng `events_by_tenant_day` mà bỏ qua `tenant_id` và `event_day` không?

**Đáp án:** Không mặc định. Khả năng định tuyến theo partition key và chi phí CQL không thay đổi vì API Java trở thành reactive.

**Câu 5.** Thêm `schema-action: none` mang ý nghĩa gì?

**Đáp án:** Không yêu cầu Spring Data tự tạo/chỉnh sửa schema khi khởi động; người vận hành phải chuẩn bị keyspace và bảng đúng phiên bản schema.

---

**Ghi nhớ:** dùng starter đồng bộ khi cần cách viết tuần tự và kết quả trực tiếp; dùng starter reactive khi luồng ứng dụng và nhu cầu concurrency phù hợp với `Mono`/`Flux`. Cả hai cần cùng những điều kiện nền: Cassandra cluster sẵn sàng, `local-datacenter`/keyspace chính xác, credential và TLS đúng môi trường, entity mapping khớp CQL, truy vấn theo partition key, paging có giới hạn và consistency/timeout được đo theo workload thực tế.
