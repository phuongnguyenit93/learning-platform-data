# Couchbase Cluster, bucket, scope và collection

## 1. Vì sao cần hiểu hệ phân cấp dữ liệu của Couchbase?

Trong một ứng dụng Spring Boot tích hợp nhiều hệ thống, Couchbase có thể lưu trạng thái đơn hàng, cấu hình tích hợp, dữ liệu tra cứu hoặc dấu vết xử lý sự kiện dưới dạng tài liệu JSON. Trước khi gọi API lưu/đọc, ứng dụng phải xác định **kết nối tới cluster nào, sử dụng bucket nào, scope nào và collection nào**. Chọn sai một cấp có thể khiến ứng dụng đọc nhầm tập dữ liệu, gặp lỗi phân quyền hoặc không tìm thấy tài liệu dù khóa có tồn tại ở nơi khác.

Ví dụ, dịch vụ xử lý đơn hàng lưu dữ liệu theo địa chỉ logic:

`commerce.sales.orders`

Trong đó `commerce` là bucket, `sales` là scope và `orders` là collection. Tài liệu có ID `order::tenant-42::ORD-10021`. Cluster là hệ thống Couchbase chứa toàn bộ cấu trúc đó và cung cấp các dịch vụ truy cập dữ liệu.

Sau bài này, người học cần phân biệt được vai trò của bốn cấp, tự thiết kế namespace phù hợp, định tuyến thao tác từ Spring Boot đến đúng collection và hiểu ảnh hưởng của chỉ mục, nhất quán, quyền truy cập và khả năng chịu lỗi.

## 2. Bốn cấp: cluster → bucket → scope → collection

~~~text
Couchbase Cluster
├── Node A: Data Service, Query Service
├── Node B: Data Service, Index Service
└── Node C: Data Service
    (các node cùng phục vụ dữ liệu và dịch vụ của cluster)

Bucket: commerce
├── Scope: sales
│   ├── Collection: orders
│   │   ├── ID: order::tenant-42::ORD-10021
│   │   └── ID: order::tenant-42::ORD-10022
│   └── Collection: payment_receipts
└── Scope: integration
    ├── Collection: webhook_inbox
    └── Collection: partner_settings
~~~

Sơ đồ phân biệt hai góc nhìn: **cluster/node** là hạ tầng và dịch vụ; **bucket/scope/collection** là tổ chức dữ liệu. Một node không “sở hữu” riêng một collection; Couchbase phân phối các phân vùng dữ liệu của bucket qua các node Data Service.

| Cấp | Chức năng chính | Quyết định cần thiết kế |
| --- | --- | --- |
| **Cluster** | Tập hợp node Couchbase, cấu hình dịch vụ và khả năng mở rộng/sẵn sàng | Số node, phân bố dịch vụ Data/Query/Index, kết nối TLS, HA, giám sát |
| **Bucket** | Không gian lưu trữ dữ liệu với cấu hình tài nguyên, độ bền và chính sách vận hành | Tách dữ liệu theo yêu cầu vận hành, dung lượng, sao lưu, thời hạn lưu trữ |
| **Scope** | Namespace logic chứa nhiều collection có liên quan | Nhóm theo miền nghiệp vụ hoặc ứng dụng; tổ chức quyền truy cập |
| **Collection** | Tập tài liệu có ID và JSON body, là đích đọc/ghi KV và đối tượng của chỉ mục truy vấn | Phân loại tài liệu theo mục đích, chỉ mục, quyền, TTL khi phù hợp |
| **Document** | Một bản ghi JSON định danh bằng document ID trong collection | Cấu trúc JSON, khóa, phiên bản, quy tắc cập nhật |

### Cluster và các dịch vụ

`Cluster` là đơn vị triển khai và quản trị. Ứng dụng dùng Couchbase SDK kết nối bằng `couchbase://...` hoặc `couchbases://...` (TLS), xác thực tài khoản và sau đó lấy bucket/scope/collection. Một đối tượng SDK `Cluster` có thể truy cập nhiều bucket nếu tài khoản được cấp quyền.

Couchbase cung cấp các dịch vụ riêng: **Data Service** xử lý truy cập khóa–giá trị (KV), **Query Service** thực thi SQL++, **Index Service** phục vụ secondary index, cùng các dịch vụ khác tùy hệ thống. Có thể phân bổ những dịch vụ này trên các node khác nhau. Không phải truy vấn nào cũng đi qua Query Service: `collection.get(id)` là truy cập KV trực tiếp qua Data Service.

Dữ liệu của bucket được chia thành các phân vùng ảo (vBucket) và đặt trên các node Data Service. Bản sao và cơ chế failover giúp tăng khả năng chịu lỗi tùy cấu hình, nhưng **replica trong cluster không đồng nghĩa sao lưu độc lập**. Phục hồi sau xóa nhầm, lỗi ứng dụng hoặc mất toàn bộ cluster vẫn cần chiến lược backup/restore.

### Bucket: ranh giới vận hành của dữ liệu

Bucket là nơi đặt các cấu hình lưu trữ quan trọng như loại bucket, phân bổ tài nguyên, số replica, chính sách hết hạn và sao lưu theo khả năng phiên bản/triển khai. Một bucket chứa nhiều scope; mỗi scope chứa nhiều collection.

Không nên tạo một bucket cho mỗi loại entity chỉ vì thói quen thiết kế bảng quan hệ. Nếu `orders` và `payment_receipts` chia sẻ cùng yêu cầu vận hành, chúng có thể ở hai collection trong cùng bucket `commerce`. Ngược lại, dữ liệu cache có TTL ngắn và dữ liệu nghiệp vụ cần bảo toàn lâu dài có thể cần bucket hoặc cấu hình lưu trữ khác nhau.

### Scope: namespace theo miền chức năng

Scope nhóm các collection liên quan. Ví dụ, `sales` chứa `orders` và `payment_receipts`, còn `integration` chứa `webhook_inbox` và `partner_settings`. Hai scope có thể cùng có collection tên `events` mà không trùng keyspace.

Scope hỗ trợ tổ chức quyền truy cập và quản trị namespace, nhưng **không phải một cluster độc lập**, không tự cấp dung lượng riêng và không thay thế kiểm soát tenant ở tầng ứng dụng. Khi thiết kế multi-tenant, cần xét cả giới hạn số lượng scope/collection và chi phí vận hành trước khi quyết định tạo một scope cho mỗi tenant.

### Collection: đích trực tiếp của tài liệu

Collection là nơi API KV thao tác. **Document ID chỉ cần duy nhất bên trong một collection**, do đó ID `order::42` có thể đồng thời xuất hiện trong hai collection khác nhau mà vẫn là hai tài liệu độc lập.

Chỉ mục SQL++ được định nghĩa trên keyspace collection; ACL có thể được cấp theo phạm vi bucket/scope/collection tùy vai trò. Có thể cấu hình thời gian hết hạn cho tài liệu hoặc collection theo nhu cầu và khả năng của phiên bản Couchbase. Việc có TTL phải được chủ động lựa chọn: để tài liệu đơn hàng tự hết hạn vì nhầm cấu hình cache có thể gây mất dữ liệu nghiệp vụ.

Trong Couchbase hỗ trợ collections, bucket mặc định có scope `_default` và collection `_default` để tương thích với mô hình truy cập cũ. Nếu ứng dụng không chọn scope/collection rõ ràng, rất dễ ghi vào `_default._default` và sau đó truy vấn nhầm `sales.orders`.

## 3. Thiết kế namespace cho tích hợp Spring Boot

Giả sử có ba nhu cầu: lưu đơn hàng, chống xử lý trùng webhook từ đối tác và quản lý cấu hình từng đối tác.

| Dữ liệu | Keyspace được đề xuất | ID ví dụ | Lý do |
| --- | --- | --- | --- |
| Đơn hàng | `commerce.sales.orders` | `order::tenant-42::ORD-10021` | Dữ liệu nghiệp vụ cần được giữ và truy vấn theo trạng thái |
| Sự kiện webhook đã tiếp nhận | `commerce.integration.webhook_inbox` | `webhook::partner-a::evt-853` | Khóa sự kiện dùng để phát hiện trùng lặp; TTL phụ thuộc cửa sổ replay |
| Cấu hình đối tác | `commerce.integration.partner_settings` | `partner::tenant-42::partner-a` | Tách quyền sửa cấu hình khỏi quyền cập nhật đơn |

Một tài liệu trong `orders`:

~~~json
{
  "tenantId": "tenant-42",
  "orderId": "ORD-10021",
  "status": "PAID",
  "createdAt": "2026-11-21T03:20:00Z"
}
~~~

ID lưu ở **metadata của document**, không bắt buộc có trường `id` trong JSON. Có thể lưu thêm trường ID nếu nhu cầu truy vấn/trao đổi dữ liệu yêu cầu, nhưng phải quy định rõ trường đó được đồng bộ với document ID. Chuỗi `tenantId` trong khóa hỗ trợ định danh, **không tự bảo đảm phân quyền**: mọi thao tác phải xác thực tenant từ ngữ cảnh người dùng, và khi tìm kiếm phải lọc đúng tenant.

Một số nguyên tắc thiết kế:

1. Chọn bucket theo yêu cầu vận hành; chọn scope theo ranh giới chức năng; chọn collection theo nhóm tài liệu và chính sách truy cập/chỉ mục.
2. Thiết kế document ID ổn định, có quy tắc chuẩn hóa và tránh nhập nhằng dấu phân cách. Không tạo ID ngẫu nhiên cho một sự kiện cần idempotency theo external event ID.
3. Tránh tạo scope/collection động theo mỗi request. Provision namespace và chỉ mục qua quy trình triển khai/migration đã kiểm soát.
4. Quy định quyền tối thiểu cho tài khoản ứng dụng; tài khoản dịch vụ ghi đơn hàng không nhất thiết được tạo bucket, scope, collection hay chỉ mục.

## 4. Tạo scope, collection và chỉ mục

Quản trị viên hoặc pipeline triển khai tạo bucket `commerce` trước bằng công cụ quản trị thích hợp. Sau đó, với quyền quản trị tương ứng, có thể chạy SQL++ DDL:

~~~sql
CREATE SCOPE `commerce`.`sales`;
CREATE SCOPE `commerce`.`integration`;

CREATE COLLECTION `commerce`.`sales`.`orders`;
CREATE COLLECTION `commerce`.`integration`.`webhook_inbox`;
CREATE COLLECTION `commerce`.`integration`.`partner_settings`;
~~~

Đây là thao tác **provisioning**, không nên đặt trong xử lý HTTP request của Spring Boot. Khi chạy nhiều lần, migration cần kiểm tra trạng thái tồn tại hoặc dùng cú pháp idempotent được phiên bản server hỗ trợ. Sau khi thay đổi cấu trúc, phải bảo đảm tài khoản ứng dụng có đúng quyền trên các keyspace mới.

KV lookup theo ID không cần secondary index. Nhưng truy vấn lọc đơn hàng theo tenant, trạng thái và thời điểm cần chỉ mục phù hợp:

~~~sql
CREATE INDEX `idx_orders_tenant_status_created`
ON `commerce`.`sales`.`orders`(tenantId, status, createdAt);

SELECT META(o).id AS documentId,
       o.orderId, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = $status
ORDER BY o.createdAt DESC
LIMIT 50;
~~~

Ở đây `$tenantId` và `$status` là tham số SQL++, **không nối chuỗi từ input** vào câu truy vấn. Query Service sử dụng chỉ mục từ Index Service; với hệ thống thật, cần xem query plan, thống kê và mức chọn lọc của chỉ mục. Tạo primary index để “cho mọi truy vấn chạy được” thường không phải chiến lược tối ưu cho production. Chỉ mục có thể cần thời gian xây dựng trước khi sẵn sàng phục vụ truy vấn.

## 5. Từ Spring Boot kết nối tới đúng collection

Ví dụ sử dụng Spring Boot 3.x, Java 17+ và Couchbase Java SDK 3.x thông qua starter:

~~~kotlin
// build.gradle.kts
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-couchbase")
}
~~~

Cấu hình kết nối trong `application.yml`:

~~~yaml
spring:
  couchbase:
    connection-string: ${COUCHBASE_CONNECTION_STRING}
    username: ${COUCHBASE_USERNAME}
    password: ${COUCHBASE_PASSWORD}
  data:
    couchbase:
      bucket-name: commerce
~~~

Các placeholder `${COUCHBASE_CONNECTION_STRING}`, `${COUCHBASE_USERNAME}` và `${COUCHBASE_PASSWORD}` khiến Spring lấy giá trị từ biến môi trường tương ứng. Trong thực tế, ứng dụng không lưu mật khẩu trực tiếp trong Git. Dùng `couchbases://...` và cấu hình tin cậy chứng chỉ phù hợp khi môi trường triển khai yêu cầu TLS.

Thuộc tính `spring.data.couchbase.bucket-name` chỉ chọn **bucket mặc định** cho Spring Data Couchbase. Nó không tự chọn scope `sales` hoặc collection `orders` cho mọi lần gọi SDK. Khi dùng API KV, ta phải chỉ rõ:

~~~java
// CouchbaseCollectionConfig.java
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CouchbaseCollectionConfig {

    @Bean("ordersCollection")
    public Collection ordersCollection(Cluster cluster) {
        Bucket bucket = cluster.bucket("commerce");
        bucket.waitUntilReady(Duration.ofSeconds(15));
        return bucket.scope("sales").collection("orders");
    }
}
~~~

`Cluster` do Spring Boot tạo từ cấu hình kết nối; `Bucket`, `Scope` và `Collection` là các handle của SDK. Chúng đại diện cho đích thao tác, **không có nghĩa toàn bộ tài liệu đã được tải vào bộ nhớ**. Việc đợi bucket sẵn sàng khi khởi động giúp phát hiện lỗi kết nối sớm, nhưng ứng dụng vẫn cần timeout, health check và xử lý lỗi tại thời điểm gọi.

Adapter ghi và đọc đơn hàng qua đúng collection:

~~~java
// CouchbaseOrderAdapter.java
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.InsertOptions;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Repository;

@Repository
public class CouchbaseOrderAdapter {
    private final Collection orders;

    public CouchbaseOrderAdapter(
            @Qualifier("ordersCollection") Collection orders) {
        this.orders = orders;
    }

    public void create(OrderDocument order) {
        String key = key(order.tenantId(), order.orderId());
        orders.insert(
                key,
                order,
                InsertOptions.insertOptions()
                        .durability(DurabilityLevel.MAJORITY));
    }

    public Optional<OrderDocument> findById(
            String tenantId, String orderId) {
        try {
            return Optional.of(
                    orders.get(key(tenantId, orderId))
                          .contentAs(OrderDocument.class));
        } catch (DocumentNotFoundException exception) {
            return Optional.empty();
        }
    }

    private String key(String tenantId, String orderId) {
        // Trong ứng dụng thật, chuẩn hóa/kiểm tra các thành phần ID.
        return "order::" + tenantId + "::" + orderId;
    }
}

record OrderDocument(
        String tenantId,
        String orderId,
        String status,
        String createdAt) {}
~~~

Đây là ví dụ cho **truy cập KV theo document ID**. `insert` chỉ tạo khi khóa chưa tồn tại; nếu khóa đã có thì SDK báo `DocumentExistsException`. Điều này phù hợp hơn `upsert` trong luồng tạo mới cần tránh âm thầm ghi đè. `DurabilityLevel.MAJORITY` yêu cầu mức xác nhận bền vững cao hơn mặc định theo cấu hình cluster; đổi lại có thể tăng độ trễ hoặc thất bại khi không đủ replica đáp ứng. Hãy chọn mức durability theo yêu cầu nghiệp vụ và khả năng triển khai.

Khi sử dụng `CouchbaseRepository` của Spring Data Couchbase thay vì SDK trực tiếp, ánh xạ `@Document` cùng cấu hình scope/collection của entity/repository theo phiên bản Spring Data đang dùng. Cần kiểm tra rằng repository thật sự thao tác trên `commerce.sales.orders`, tránh vô tình dùng `_default._default`. Không tự suy ra đường dẫn repository chỉ từ tên lớp Java.

## 6. KV, SQL++ và tính nhất quán

Hai cách đọc thường gặp có chi phí và hành vi khác nhau:

| Thao tác | Đường đi | Chỉ mục cần thiết | Lưu ý |
| --- | --- | --- | --- |
| `collection.get(documentId)` | KV / Data Service | Không cần secondary index | Tốt khi biết chính xác ID và collection |
| `collection.insert(id, json)` | KV / Data Service | Không cần secondary index | Lỗi nếu ID đã tồn tại; hữu ích cho tạo mới/chống trùng |
| `collection.replace(id, json, options)` | KV / Data Service | Không cần secondary index | Có thể dùng CAS để tránh ghi đè bản cập nhật mới hơn |
| `cluster.query("SELECT ...")` | Query Service, thường phối hợp Index Service | Thường cần secondary index phù hợp | Truy vấn nhiều tài liệu theo thuộc tính và điều kiện lọc |

Ví dụ Java SDK thực thi SQL++ với tham số:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.stereotype.Repository;

@Repository
public class OrderQueryReader {
    private final Cluster cluster;

    public OrderQueryReader(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult findPaidOrders(String tenantId) {
        String statement = """
            SELECT META(o).id AS documentId, o.orderId, o.status
            FROM `commerce`.`sales`.`orders` AS o
            WHERE o.tenantId = $tenantId AND o.status = $status
            """;

        return cluster.query(
                statement,
                QueryOptions.queryOptions()
                        .parameters(JsonObject.create()
                                .put("tenantId", tenantId)
                                .put("status", "PAID"))
                        .scanConsistency(QueryScanConsistency.REQUEST_PLUS));
    }
}
~~~

SQL++ dùng index được cập nhật bất đồng bộ. Vì vậy, ngay sau khi ghi một tài liệu bằng KV, một truy vấn dùng chỉ mục với mức scan consistency mặc định có thể chưa thấy thay đổi mới. `REQUEST_PLUS` yêu cầu Query Service đợi chỉ mục bắt kịp các mutation trước thời điểm truy vấn, đổi lại độ trễ cao hơn; nó không biến toàn bộ ứng dụng thành hệ thống giao dịch phân tán tuyến tính. Khi đã biết ID, KV get thường là đường đọc phù hợp hơn cho nhu cầu vừa ghi vừa đọc cùng tài liệu.

Với cập nhật cạnh tranh, SDK trả về **CAS** (compare-and-swap) khi đọc document. Có thể truyền CAS vào thao tác `replace` để yêu cầu “chỉ cập nhật nếu tài liệu chưa đổi kể từ lần đọc”. Nếu CAS không còn khớp, phải xử lý xung đột theo nghiệp vụ; `upsert` không tự giải quyết lost update.

## 7. Lỗi tích hợp, quyền truy cập và vận hành

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| KV báo document không tồn tại nhưng đã nhìn thấy trên UI | Sai bucket/scope/collection hoặc sai ID; tài liệu hết hạn | Log keyspace và ID ở dạng an toàn, kiểm tra TTL và quy tắc tạo khóa |
| Không mở được bucket/collection | Chưa provision, gõ sai tên, thiếu quyền | Kiểm tra namespace, tài khoản dịch vụ và quyền RBAC |
| SQL++ không chạy dù KV get hoạt động | Thiếu Query/Index Service, chỉ mục chưa tồn tại/chưa sẵn sàng, quyền truy vấn khác với KV | Kiểm tra dịch vụ, chỉ mục, query plan và quyền |
| Truy vấn không thấy dữ liệu vừa ghi | Độ trễ cập nhật secondary index | Dùng KV get nếu biết ID, hoặc chọn scan consistency phù hợp |
| Retry tạo ra tác dụng phụ trùng | Timeout khiến kết quả commit chưa rõ; luồng xử lý không idempotent | Dùng ID ổn định, `insert`/kiểm tra trùng, xử lý kết quả mơ hồ và retry có kiểm soát |
| Tranh chấp cập nhật cùng tài liệu | Nhiều luồng ghi đè bằng `upsert` | Cân nhắc CAS, mô hình cập nhật trạng thái và chính sách xử lý xung đột |
| Dữ liệu biến mất theo thời gian | TTL bucket/collection/document hoặc chính sách xóa | Kiểm tra cấu hình hết hạn theo đúng yêu cầu lưu giữ |

### Phân quyền

Tài khoản ứng dụng nên được cấp quyền đọc/ghi chính xác trên các collection cần dùng; tài khoản deployment riêng mới có quyền tạo namespace/chỉ mục. Chú ý rằng quyền **KV Data Reader/Writer** không mặc nhiên là quyền **Query**, và quyền trên một collection không tự mở rộng sang collection khác. Khi log lỗi, tránh lộ mật khẩu, dữ liệu cá nhân hoặc toàn bộ document chứa thông tin nhạy cảm.

### Retry, idempotency và giao dịch

Trong xử lý webhook hoặc sự kiện broker, document ID có thể là dấu vết chống trùng, chẳng hạn `webhook::partner-a::evt-853` trong `integration.webhook_inbox`. Dùng `insert` để phát hiện sự kiện đã nhận, nhưng **ghi dấu vết và cập nhật đơn hàng là hai thao tác**; nếu cần nguyên tử qua nhiều document thì phải xem xét giao dịch Couchbase hoặc thiết kế trạng thái/đền bù phù hợp. Giao dịch Couchbase không tự gộp được cả việc commit Kafka/RabbitMQ hoặc HTTP của hệ thống bên ngoài. Vì vậy, cần thiết kế retry, acknowledge, inbox/outbox và phục hồi lỗi ở ranh giới hệ thống.

Một `TimeoutException` hoặc lỗi mạng không nhất thiết chứng minh thao tác ghi chưa xảy ra. Trước khi retry thao tác có tác dụng phụ, xác định xem thao tác đó có idempotent không; với `insert`, gặp document đã tồn tại sau retry cần đối chiếu nội dung hoặc trạng thái nghiệp vụ thay vì luôn xem là lỗi hệ thống.

### Kiểm thử và quan sát

Kiểm thử tích hợp trên một cluster Couchbase tương thích phiên bản thực tế và đã tạo bucket/scope/collection/chỉ mục cần thiết. Các tình huống quan trọng gồm: đọc/ghi đúng keyspace; collection không tồn tại; thiếu quyền; ID trùng; đọc ngay sau ghi; query khi chưa có chỉ mục; cạnh tranh cập nhật; timeout và replay webhook. Test đơn vị có thể mock adapter, nhưng không thay thế kiểm thử query/index/ACL trên Couchbase thật.

Trong production cần theo dõi độ trễ KV và SQL++, timeout, số kết nối, trạng thái node/service, chỉ mục, độ trễ replica, sử dụng bộ nhớ/đĩa, lỗi quyền và tốc độ hết hạn document. Đặt timeout và retry theo đặc tính từng API; không retry vô hạn hoặc dùng một chính sách chung cho mọi lỗi.

## 8. Tình huống thiết kế và câu hỏi tự kiểm tra

**Tình huống:** Một ứng dụng Spring Boot ghi `order::tenant-42::ORD-10021` vào `commerce.sales.orders`, sau đó API liệt kê đơn hàng bằng SQL++ không thấy đơn mới. Truy vấn khác trên `commerce._default._default` cũng không thấy gì.

Cách phân tích:

1. Xác minh adapter dùng `bucket("commerce").scope("sales").collection("orders")` và document ID chính xác; kiểm tra tồn tại bằng KV get trước.
2. Nếu KV có dữ liệu, kiểm tra câu SQL++ có dùng keyspace `commerce.sales.orders` hay không, và chỉ mục trên collection đã sẵn sàng chưa.
3. Kiểm tra scan consistency của truy vấn và độ trễ Index Service. Chọn `REQUEST_PLUS` khi cần quan sát nhanh thay đổi mới nhất và chấp nhận chi phí độ trễ.
4. Nếu lỗi chỉ xảy ra với tenant khác, kiểm tra khóa ID, điều kiện `tenantId` và quyền truy cập; không gỡ điều kiện lọc tenant để “khắc phục”.

Tự kiểm tra: (a) Hai collection có thể chứa cùng document ID không? **Có**, vì ID duy nhất trong từng collection. (b) Scope có tự cấp tài nguyên vật lý như bucket không? **Không**. (c) KV get cần SQL++ index không? **Không**. (d) Vì sao `upsert` không luôn phù hợp để chống trùng webhook? **Vì nó có thể ghi đè ID đã tồn tại**, nên cần thao tác tạo có điều kiện và logic idempotency. (e) Vì sao cần tách tài khoản triển khai khỏi tài khoản ứng dụng? **Để ứng dụng chỉ có quyền tối thiểu cần cho vận hành**.

Khi triển khai Couchbase trong Spring Boot, luôn truy vết đầy đủ **cluster → bucket → scope → collection → document ID**, sau đó đối chiếu cách truy cập KV hay SQL++, quyền và yêu cầu nhất quán của luồng tích hợp. Cách xác định keyspace cụ thể giúp tránh lỗi định tuyến dữ liệu và thiết kế đúng cơ chế xử lý trùng, retry và giám sát.
