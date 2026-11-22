# Kiểm soát chỉ mục hoặc schema và tránh thay đổi ngầm khi khởi động

## 1. Vì sao schema/index của NoSQL cũng cần quản lý phiên bản?

Trong module **Spring Boot Integration**, dữ liệu không chỉ nằm ở SQL database. Ứng dụng còn có thể lưu tài liệu vào MongoDB, ghi sự kiện vào Cassandra, tạo read model tìm kiếm trên Elasticsearch/OpenSearch, truy cập DynamoDB hoặc dùng Couchbase. Những datastore này linh hoạt hơn mô hình bảng SQL truyền thống ở một số khía cạnh, nhưng **linh hoạt không đồng nghĩa với không có schema, chỉ mục hoặc hợp đồng dữ liệu**.

Ví dụ dịch vụ Catalog lưu thông tin sản phẩm trong MongoDB. Một phiên bản mới bổ sung truy vấn `findByTenantIdAndExternalId` và đánh dấu cặp `(tenantId, externalId)` là duy nhất. Developer đặt annotation `@Indexed` hoặc `@CompoundIndex` rồi triển khai đồng thời 12 pod. Nếu framework được cấu hình tự tạo index lúc khởi động, nhiều pod có thể cùng cố tạo index trên collection đang có hàng triệu tài liệu. Một số tình huống có thể xảy ra:

- Index build làm tăng I/O, bộ nhớ và thời gian xử lý ở cụm database đúng lúc lượng truy cập tăng.
- **Unique index** không thể tạo vì dữ liệu hiện có đã trùng; một số pod không khởi động được.
- Pod phiên bản cũ và mới có **định nghĩa index khác nhau**; thứ tự triển khai trở thành nguồn gây lỗi.
- Một process có quyền DDL quá rộng tự sửa cấu trúc mà không qua phê duyệt.
- Hệ thống tìm kiếm tự tạo index qua request ghi với **dynamic mapping không mong muốn**, khiến type của trường bị suy đoán sai.

Vấn đề không chỉ nằm ở annotation hay framework. Đây là bài toán **quyền sở hữu thay đổi schema**, **khả năng tương thích giữa các phiên bản**, **chi phí migration** và **thứ tự rollout trên nhiều replica**.

Mục tiêu của bài học:

1. Phân biệt model trong Java, schema thực tế, chỉ mục phục vụ truy vấn và ràng buộc dữ liệu.
2. Biết nơi nào Spring Data hoặc datastore có thể tạo/sửa cấu trúc khi khởi động hoặc khi ghi.
3. Tách **migrations có kiểm soát** khỏi vòng đời startup của ứng dụng phục vụ traffic.
4. Triển khai an toàn khi có nhiều pod, dữ liệu lịch sử và sự kiện bất đồng bộ.
5. Kiểm chứng thay đổi qua test, monitoring, rollback và runbook.

~~~mermaid
flowchart LR
    A["Spring Boot app replicas"] --> B["Repository / HTTP adapter"]
    B --> C[("NoSQL datastore")]
    D["Pipeline migration riêng"] -->|"Có phê duyệt, quyền DDL"| C
    E["Schema/index manifest"] --> D
    A -. "Startup: chỉ kiểm tra tương thích" .-> C
~~~

Nguyên tắc triển khai: **ứng dụng bình thường đọc/ghi dữ liệu theo quyền tối thiểu; thay đổi schema/index được quản lý bằng một quy trình riêng, theo phiên bản và có quan sát**.

## 2. “Schema” khác nhau giữa các NoSQL datastore

Không nên sao chép cách nghĩ về migration của PostgreSQL sang mọi NoSQL. Mỗi hệ thống có ranh giới cấu trúc khác nhau:

| Datastore | Cấu trúc quan trọng | Ví dụ thay đổi rủi ro | Điểm cần quản lý |
| --- | --- | --- | --- |
| **MongoDB** | Collections, JSON/BSON document, index (compound, unique, TTL, partial), validator. | Thêm unique index trên dữ liệu có trùng; đổi TTL làm dữ liệu lịch sử bị xóa. | Index definitions, collection validation, backfill và tương thích tài liệu cũ. |
| **Apache Cassandra** | Keyspace, table, partition/clustering keys, columns, secondary index/materialized view. | Chọn lại partition key, thay cấu trúc truy vấn hoặc schema agreement chưa hoàn tất. | CQL migrations, chiến lược tạo bảng mới/backfill cho thay đổi khóa và năng lực cluster. |
| **Elasticsearch/OpenSearch** | Index, mappings, analyzers, settings, templates, aliases. | Thay field type/analyzer không tương thích trong index đã có dữ liệu; dynamic mapping sai. | Versioned indices, reindex, alias switch và đồng bộ dữ liệu khi chuyển. |
| **DynamoDB** | Table key schema, GSI/LSI, capacity, TTL setting và attribute shape. | Thêm GSI trên bảng lớn, thiết kế khóa truy cập sai hoặc dựa vào GSI như đọc nhất quán mạnh. | IaC, online GSI backfill, capacity, giới hạn và hợp đồng truy vấn. |
| **Couchbase** | Buckets, scopes, collections, primary/secondary indexes, query plan. | Tạo index lớn khi nhiều node cùng startup, query fail do index chưa online. | Tạo index riêng, trạng thái index và rollout query phụ thuộc. |

Document database có thể cho phép tài liệu mang các trường khác nhau, nhưng **ứng dụng vẫn có schema logic**: dữ liệu bắt buộc, kiểu trường, version, quy ước ID, validation và cách truy vấn. Không có DDL cưỡng chế ở mọi nơi không có nghĩa consumer chịu được mọi thay đổi payload.

### 2.1. Bốn lớp schema cần tách

1. **Application model:** Java `record`, `@Document`, `@Table`, mapping JSON/BSON, repository query.
2. **Persisted data contract:** bản ghi thực tế, schema version, field tùy chọn, quy tắc biến đổi dữ liệu cũ.
3. **Physical query structures:** index, partition key, mapping/analyzer, materialized view, GSI.
4. **Operational configuration:** TTL, retention, capacity, replica/consistency settings và quyền DDL.

Một annotation trong Java có thể mô tả **ý định** của lập trình viên nhưng không nhất thiết thay đổi ngay cấu trúc đã có trên server. Ngược lại, một API ghi dữ liệu ở server có thể kích hoạt cấu trúc mới **không qua annotation Java** nếu datastore cho phép. Cần kiểm soát cả hai phía.

## 3. Vì sao không nên mặc định chạy DDL trong startup?

Startup của ứng dụng thường được thực thi đồng thời và có thể lặp lại vì:

- Rolling update, HPA scale-out, node replacement, crash loop.
- Canary/blue-green deployment, hai phiên bản cùng tồn tại.
- Health check, readiness retry, khởi động nhiều tenant hoặc nhiều context.
- Spring Batch worker hay scheduled job tạo thêm process cùng truy cập một datastore.

Nếu startup tự tạo hoặc sửa index, **một thao tác có chi phí lớn bị biến thành side effect ngầm**, với đặc tính rủi ro sau:

| Rủi ro | Ví dụ | Kết quả |
| --- | --- | --- |
| Nhiều người cùng thay đổi | 10 pod cùng yêu cầu tạo một unique index. | Tranh chấp, cảnh báo khó đọc, fail không nhất quán. |
| Không có kiểm tra dữ liệu lịch sử | Đã tồn tại duplicate key. | Migration thất bại giữa rollout. |
| Phá vỡ tương thích | App mới đổi mapping, app cũ vẫn ghi kiểu cũ. | Error hoặc dữ liệu không đọc được. |
| Không quản lý resource | Index build cạnh tranh I/O với workload. | Latency tăng, timeout ở consumer/API. |
| Quyền triển khai quá rộng | App service account có quyền CREATE/ALTER/DROP. | Lỗi code hoặc cấu hình gây thay đổi cấu trúc ngoài ý muốn. |
| Không có kiểm toán | Không biết ai tạo index hay khi nào sửa TTL. | Khó rollback, khó truy nguyên sự cố. |

**Idempotent migration** là điều kiện cần nhưng chưa đủ. Ví dụ `CREATE INDEX IF NOT EXISTS` có thể không kiểm tra rằng định nghĩa index đã tồn tại **thực sự giống** định nghĩa mới. Một index cùng tên nhưng sai thứ tự cột, unique flag hoặc TTL vẫn gây sai truy vấn/hợp đồng.

Đích đến không phải “không bao giờ thay đổi schema”, mà là **mỗi thay đổi phải có chủ sở hữu, điều kiện trước khi chạy, đánh giá tác động, bước kiểm chứng và kế hoạch khôi phục**.

## 4. MongoDB: tắt tự tạo index và quản lý index riêng

Spring Data MongoDB có annotation như `@Indexed`, `@CompoundIndex`, `@TextIndexed`, `@GeoSpatialIndexed` và hỗ trợ index từ metadata entity. Tuy nhiên, **annotation là mô tả mapping**; việc tự tạo index phụ thuộc cấu hình `autoIndexCreation` của Spring Data MongoDB.

Trong Spring Boot 3.x, hãy **khai báo rõ ý định** thay vì dựa vào giá trị mặc định của phiên bản:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
      auto-index-creation: false
~~~

Khi không bật automatic index creation, ứng dụng không nên dùng startup listener hay `ApplicationRunner` tự gọi `createIndex`/`ensureIndex` để “bù” lại. Nếu dự án tự định nghĩa `MongoMappingContext`/`MongoTemplate`, kiểm tra xem custom configuration có ghi đè chính sách trên hay không.

### 4.1. Annotation phục vụ mô tả, không thay thế migration

~~~java
package com.example.integration.catalog;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customer_profiles")
@CompoundIndex(
        name = "uq_tenant_external",
        def = "{ 'tenantId': 1, 'externalId': 1 }",
        unique = true)
public class CustomerProfile {
    @Id
    private String id;
    private String tenantId;
    private String externalId;
    private String displayName;

    // Constructors, getters và logic domain lược bỏ.
}
~~~

`@CompoundIndex` mô tả ý định index, nhưng trong cấu hình production trên **không yêu cầu app tự build index khi startup**. Nhóm sở hữu migration phải tạo, kiểm tra và công bố index tương ứng **trước khi** deploy code phụ thuộc vào điều kiện unique hay hiệu năng query.

Chú ý với dữ liệu cũ: nếu `tenantId` hoặc `externalId` thiếu/null, unique compound index có thể có hành vi khác mong đợi. Đặt quy tắc dữ liệu bắt buộc, làm sạch duplicate/null và cân nhắc **partial index** chỉ khi hợp đồng thực sự cho phép những tài liệu không nằm trong phạm vi unique.

### 4.2. Tạo index qua một migration có chủ đích

Ví dụ một migration MongoDB được thực hiện bằng tài khoản riêng, **sau khi xác nhận không có duplicate**:

~~~javascript
// Chạy trong phiên migration đã được kiểm soát, không chạy ở startup app.
db.customer_profiles.createIndex(
  { tenantId: 1, externalId: 1 },
  {
    name: "uq_tenant_external",
    unique: true
  }
);

db.customer_profiles.getIndexes();
~~~

Kiểm tra duplicate trước khi thêm unique index:

~~~javascript
db.customer_profiles.aggregate([
  {
    $group: {
      _id: { tenantId: "$tenantId", externalId: "$externalId" },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 100 }
]);
~~~

Truy vấn này là **điểm bắt đầu kiểm tra**, không phải toàn bộ kế hoạch dữ liệu: cần xét key thiếu/null, collation, normalization (chữ hoa/thường, khoảng trắng), tenant scope và dung lượng dữ liệu. Dùng index hỗ trợ kế hoạch query hoặc chạy audit vào khung giờ phù hợp để tránh scan tài liệu lớn gây áp lực lên cluster.

**Khi index đã có:** việc gọi `createIndex` với tên trùng nhưng định nghĩa khác có thể trả lỗi; không coi lỗi là “đã có, bỏ qua”. Migration phải **so đúng keys/options, quyết định rebuild theo kế hoạch** và không tự drop index đang dùng.

### 4.3. TTL index có thể xóa dữ liệu thật

Ví dụ collection lưu sự kiện tạm thời:

~~~javascript
db.integration_events.createIndex(
  { expiresAt: 1 },
  { name: "ttl_integration_events", expireAfterSeconds: 0 }
);
~~~

Trong MongoDB, TTL index dựa trên field thời gian phù hợp (ví dụ BSON Date). `expireAfterSeconds: 0` nghĩa là tài liệu đủ điều kiện hết hạn theo thời điểm ghi ở `expiresAt`; **TTL monitor xóa bất đồng bộ**, không bảo đảm xóa đúng một mili giây hay thay thế cơ chế tuân thủ retention bắt buộc.

Đổi TTL từ nhiều ngày xuống vài phút có thể khiến lượng lớn dữ liệu lịch sử đủ điều kiện bị xóa; cần dry-run, thống kê số tài liệu ảnh hưởng, backup, cân nhắc tải delete và phê duyệt riêng. TTL index không nên được tự thay đổi trong startup.

## 5. Cassandra: schema CQL và khả năng tương thích của partition key

Với Spring Data Cassandra trên Spring Boot 3.x, có thể cấu hình không cho hạ tầng tự tạo/chỉnh schema từ mapping entity:

~~~yaml
spring:
  cassandra:
    keyspace-name: integration_app
    contact-points: cassandra.internal
    local-datacenter: dc1
    schema-action: none
~~~

`schema-action: none` biểu thị ứng dụng **không thực hiện các hành động schema management** khi thiết lập mapping; tài nguyên keyspace/table vẫn phải được tạo trước theo kế hoạch. Nếu project có config riêng tạo `SessionFactory` hoặc `CqlSession`, cần kiểm tra nơi nó thực hiện DDL.

### 5.1. Migration CQL được thực thi một lần

~~~sql
-- Ví dụ CQL do quy trình migration vận hành thực hiện.
CREATE TABLE IF NOT EXISTS integration_app.order_events (
    tenant_id text,
    event_id text,
    occurred_at timestamp,
    payload text,
    schema_version int,
    PRIMARY KEY ((tenant_id), event_id)
);
~~~

Khóa `((tenant_id), event_id)` chọn **tenant_id là partition key**, `event_id` là clustering key. Đây là mô hình minh họa cho truy vấn theo tenant và event ID; chưa chắc phù hợp nếu một tenant có hàng triệu event trong một partition. Thiết kế thực tế nên dựa trên **access patterns**, kích thước partition, hot partitions, time buckets, consistency và retention.

Trong Cassandra, thay đổi **partition/clustering key** của bảng hiện có thường không thể xử lý như một `ALTER TABLE ADD column` thông thường. Cách tiếp cận thường là:

1. Tạo bảng mới với khóa/phân vùng phù hợp truy vấn mới.
2. Backfill có giới hạn tốc độ và theo dõi độ đầy đủ dữ liệu.
3. Chuyển đường ghi/đọc hoặc duy trì dual-write theo chiến lược có kiểm chứng.
4. Đối soát dữ liệu, theo dõi consistency/latency và chỉ xóa bảng cũ sau khi hết nhu cầu rollback.

### 5.2. Không nhầm schema agreement với việc dữ liệu đã sẵn sàng

Thay đổi CQL có thể cần thời gian để các node thống nhất schema (**schema agreement**). DDL “được chấp nhận” không có nghĩa dữ liệu backfill, index build hoặc materialized view đã sẵn sàng phục vụ workload. Migration phải đợi trạng thái phù hợp, kiểm tra query plan/latency và chỉ sau đó cho app mới dùng cấu trúc.

Không tự bổ sung secondary index vào mọi field vì thấy truy vấn mới cần filter. Secondary index, materialized view hay SAI (nếu cluster hỗ trợ) có chi phí và giới hạn khác nhau theo phiên bản Cassandra, phân bố dữ liệu và cách truy vấn. Hãy thiết kế **bảng theo query**, đo tải thật và chọn giải pháp index một cách có chủ đích.

## 6. Elasticsearch/OpenSearch: tách index, mapping và alias khỏi startup

Trong hệ thống tìm kiếm, mapping quy định field type, analyzer và cách index tài liệu. Nhiều thay đổi như chuyển field từ `text` sang `keyword` hay đổi analyzer **không thể áp trực tiếp để diễn giải lại toàn bộ dữ liệu cũ**.

Khi dùng Spring Data Elasticsearch, có thể tắt việc repository tự tạo index cho entity bằng `createIndex = false`:

~~~java
package com.example.integration.search;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders-search", createIndex = false)
public class OrderSearchDocument {
    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Keyword)
    private String orderId;

    @Field(type = FieldType.Text)
    private String description;

    // Constructors/getters lược bỏ.
}
~~~

Giả định `orders-search` là **alias**, trỏ tới physical index có version. Annotation này **chỉ kiểm soát hành vi của Spring Data khi tạo index**; nó **không tự vô hiệu hóa** khả năng server tự tạo index nếu cluster cho phép auto-create khi có lệnh ghi tới tên chưa tồn tại. Phía Elasticsearch/OpenSearch cần có quyền/setting và chiến lược provisioning phù hợp để ghi sai tên không vô tình tạo physical index với dynamic mapping.

### 6.1. Tạo index version mới rồi chuyển alias

Quy trình tổng quát:

~~~text
orders-search (alias) -> orders-search-v1

Migration:
  1. Tạo orders-search-v2 với mapping, analyzer và settings mới.
  2. Backfill/reindex dữ liệu từ nguồn authoritative hoặc v1 nếu phù hợp.
  3. Đồng bộ các thay đổi phát sinh trong lúc backfill.
  4. Kiểm tra số liệu, query correctness, lag và quyền truy cập.
  5. Chuyển alias orders-search từ v1 sang v2 có kiểm soát.

orders-search (alias) -> orders-search-v2
~~~

Ví dụ yêu cầu REST mô tả mapping mong muốn:

~~~http
PUT /orders-search-v2
Content-Type: application/json

{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "tenantId": { "type": "keyword" },
      "orderId": { "type": "keyword" },
      "description": { "type": "text" }
    }
  }
}
~~~

Sau khi index v2 đã đầy đủ và ổn định, thao tác alias có thể làm trong một yêu cầu cập nhật:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    { "remove": { "index": "orders-search-v1", "alias": "orders-search" } },
    { "add": { "index": "orders-search-v2", "alias": "orders-search" } }
  ]
}
~~~

Các API ở trên là **ví dụ định hướng** cho hệ sinh thái Elasticsearch; phải xác minh phiên bản và khác biệt OpenSearch trước khi chạy. Nếu alias vừa dùng để đọc vừa dùng để ghi, cần xác định `is_write_index` và cách xử lý ghi phát sinh trong lúc chuyển. Chuyển alias **không tự đồng bộ** những update đã xảy ra sau lúc bắt đầu reindex. Dùng CDC/outbox, dual-write có đối soát hoặc nguồn authoritative để đóng khoảng hở dữ liệu.

**Dynamic mapping** là một nguồn thay đổi ngầm thứ hai: dù application code không tạo index khi startup, việc ghi một document chứa field lạ có thể tự làm mapping thay đổi nếu server cho phép. Với dữ liệu có hợp đồng nghiêm ngặt, cân nhắc `dynamic: strict`, index template versioned và CI contract tests. Không bật strict một cách mù quáng nếu hệ thống có legitimate dynamic fields; thiết kế nơi chứa metadata mở rộng riêng.

## 7. DynamoDB và Couchbase: application startup không phải migration pipeline

### 7.1. DynamoDB

Với DynamoDB, **table partition/sort key**, GSI/LSI, TTL và capacity mode là cấu hình hạ tầng; nên quản lý bằng **IaC** (CloudFormation/CDK/Terraform hoặc cơ chế được tổ chức phê duyệt). Một Java entity/DTO có field mới không có nghĩa hệ thống đã tự tạo **GSI** cần thiết cho truy vấn.

Các điều cần quan sát:

- GSI mới có thể cần **backfill** và đi qua các trạng thái trước khi sử dụng; ứng dụng không nên bắt đầu query index trước khi index sẵn sàng.
- GSI thường có đặc tính **eventual consistency**; đừng đòi read-after-write mạnh từ GSI chỉ vì transaction trên table đã thành công.
- TTL expiration được xử lý bất đồng bộ; không lấy TTL làm phép xóa đúng thời hạn tuyệt đối hoặc quy tắc kiểm toán duy nhất.
- Thay đổi key design không phải chỉ đổi annotation: thường cần bảng mới, migration dữ liệu, dual-read/write và cutover.

SDK trong Spring Boot nên được cấp quyền đọc/ghi bảng theo nhu cầu, **không mang quyền quản trị table/index** trong process thông thường. Job migration có danh tính/quyền riêng và được theo dõi để không đánh đổi availability khi tạo GSI trên bảng lớn.

### 7.2. Couchbase

Trong Couchbase, bucket/scope/collection và primary/secondary indexes cần được cấu hình theo workload truy vấn. Việc thêm một repository query không bảo đảm index tương ứng đã online. Tạo index lớn hay sửa bố cục collection có thể tiêu tốn tài nguyên và gây lệch behavior giữa môi trường.

Nên dùng provisioning/migration tách biệt, kiểm tra `index state` và kế hoạch query, chỉ cho code mới chạy khi index sẵn sàng. Với nhiều replica, không để mỗi pod tự chạy `CREATE INDEX` khi ứng dụng nhận traffic. Schema JSON linh hoạt vẫn cần version, validation và chuyển đổi tài liệu lịch sử.

## 8. Thiết kế pipeline migration tách khỏi vòng đời khởi động

Một pipeline tốt có **artifact được version hóa**, chạy một lần theo phạm vi datastore và ghi lại kết quả:

~~~mermaid
flowchart TD
    A["Pull request thay đổi model/query"] --> B["Thiết kế contract + access pattern"]
    B --> C["Migration có version + review"]
    C --> D["Preflight: duplicate, capacity, schema hiện tại"]
    D --> E["Tạo index/schema trong rollout riêng"]
    E --> F["Đợi index/schema sẵn sàng"]
    F --> G["Backfill + đối soát + metrics"]
    G --> H["Deploy app dùng cấu trúc mới"]
    H --> I["Theo dõi + cleanup phiên bản cũ"]
~~~

Nên có các nguyên tắc cụ thể:

1. **Version hóa migration** theo datastore và collection/table/index, nêu ID, mục tiêu, rủi ro và trạng thái đã thực hiện.
2. **Chạy migration dưới một chủ sở hữu** (CI/CD job, release task hoặc công cụ migration chuyên biệt); ngăn chạy cạnh tranh trên cùng namespace.
3. **Tài khoản migration tách biệt** tài khoản ứng dụng, có quyền DDL đúng phạm vi.
4. **Preflight kiểm tra drift**: cấu trúc thực tế giống phiên bản đã công bố hay không, có duplicate/null, đủ dung lượng và năng lực để build index không.
5. **Idempotency có kiểm chứng**: chạy lại không làm tạo thêm side effect, nhưng phải fail khi định nghĩa đã tồn tại **khác** định nghĩa yêu cầu.
6. **Quan sát được tiến độ**: duration, index build status, backfill lag, số bản ghi sai, latency p95/p99, replication lag, quota/capacity.
7. **Rollout có điều kiện**: app mới chỉ dùng query/index khi migration đã đạt trạng thái sẵn sàng và code cũ vẫn tương thích trong cửa sổ chuyển tiếp.

Một manifest/nhật ký thay đổi có thể trông như sau:

~~~yaml
# Ví dụ metadata migration do pipeline quản lý, không phải Spring Boot config.
id: catalog-2026-11-21-04
store: mongodb
target: customer_profiles
operation: create-compound-unique-index
indexName: uq_tenant_external
preconditions:
  - no-duplicate-tenant-external-key
  - enough-disk-and-io-headroom
postconditions:
  - index-spec-matches-approved-definition
  - index-visible-to-application
rollbackPolicy: reviewed-manual-plan
~~~

Các key trên là quy ước ví dụ; không có nghĩa một thư viện Spring mặc định sẽ tự hiểu hoặc chạy YAML này. Quan trọng là **change request và bằng chứng execution** phải được lưu lại để truy nguyên.

### 8.1. Không dùng startup hook để thay migration pipeline

Mẫu code nên tránh trong ứng dụng phục vụ traffic:

~~~java
// Không áp dụng trong production service.
@Bean
ApplicationRunner createIndexesOnEveryStartup(MongoTemplate template) {
    return args -> template.indexOps("customer_profiles")
            .ensureIndex(new Index()
                    .on("tenantId", Sort.Direction.ASC)
                    .on("externalId", Sort.Direction.ASC)
                    .unique());
}
~~~

Dù `ensureIndex` có khả năng dùng lại index trong một số tình huống, code này vẫn biến startup thành một migration không có phê duyệt, chi phí khó dự báo và chạy lặp trên các replica. **Tốt hơn:** migration riêng thực hiện DDL; startup chỉ kiểm tra hệ thống đã đáp ứng contract.

## 9. Kiểm tra tương thích read-only lúc startup

Tắt DDL tự động không có nghĩa ứng dụng nên khởi động “mù”. Nếu một chức năng phụ thuộc vào index/mapping mới, startup có thể **đọc metadata theo quyền read-only** và từ chối readiness khi datastore chưa đạt phiên bản phù hợp.

Ví dụ lưu một tài liệu migration marker trong MongoDB:

~~~json
{
  "_id": "catalog",
  "schemaVersion": 4,
  "lastMigration": "catalog-2026-11-21-04"
}
~~~

Một preflight chỉ đọc có thể được thực hiện bằng Spring Boot:

~~~java
package com.example.integration.catalog;

import static com.mongodb.client.model.Filters.eq;

import org.bson.Document;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration(proxyBeanMethods = false)
class CatalogSchemaCompatibilityConfiguration {

    @Bean
    ApplicationRunner verifyCatalogSchema(MongoTemplate mongoTemplate) {
        return args -> {
            Document marker = mongoTemplate
                    .getCollection("integration_schema_metadata")
                    .find(eq("_id", "catalog"))
                    .first();

            if (marker == null) {
                throw new IllegalStateException(
                        "Catalog schema marker is missing");
            }

            Integer version = marker.getInteger("schemaVersion");
            if (version == null || version < 4 || version > 5) {
                throw new IllegalStateException(
                        "Unsupported catalog schema version: " + version);
            }
        };
    }
}
~~~

Đây là **kiểm tra điều kiện tối thiểu**, không phải bằng chứng mọi index đúng. Marker chỉ đáng tin khi **migration pipeline cập nhật nó sau khi đã kiểm tra đầy đủ hậu điều kiện**. Nếu cần khẳng định index quan trọng sẵn sàng, startup hoặc health preflight có thể **đọc và so định nghĩa index** (keys, uniqueness, partial/TTL options) bằng quyền phù hợp mà không tự sửa chúng.

Quy tắc quan trọng khi rolling deployment:

- App phiên bản N và N+1 có thể cùng chạy. Chọn một **cửa sổ version/feature compatibility**, không nhất thiết ép mọi replica kiểm tra `schemaVersion == currentVersion`.
- Version marker cần thống nhất theo **datastore/database/tenant phạm vi thực tế**; tránh một marker global báo thành công khi một namespace vẫn chưa migrate.
- Khi datastore tạm không truy cập được, hành vi fail startup/readiness phải theo SLO và khả năng phục hồi của ứng dụng; không để cơ chế kiểm tra gọi DDL hoặc reset schema khi lỗi.
- Kiểm tra metadata quá nặng mỗi startup cũng có thể tạo load spike; nên dùng bước nhanh, cache trạng thái phù hợp và kiểm soát retry/backoff.

**Quyền read-only của application startup** là lớp bảo vệ bổ sung: ngay cả khi một đoạn code vô tình gọi API tạo collection/index, quyền bị từ chối thay vì thay đổi cấu trúc âm thầm.

## 10. Expand–migrate–contract khi nhiều phiên bản chạy cùng lúc

Quy trình nâng cấp không nên dựa vào việc “tất cả pod đổi version tức thì”. Ví dụ muốn đổi `customerFullName` thành hai field `givenName` và `familyName` trong document:

| Giai đoạn | Thay đổi | Điều kiện hoàn tất |
| --- | --- | --- |
| **Expand** | Reader có thể đọc cả định dạng cũ và mới; writer chuẩn bị phát field mới khi phù hợp. | Code cũ vẫn hoạt động; schema/index cần thiết được tạo trước. |
| **Migrate** | Backfill dữ liệu lịch sử với checkpoint và kiểm tra lỗi; có thể dual-write có giới hạn. | Tỷ lệ dữ liệu mới đạt mục tiêu; backlog và sai lệch được đối soát. |
| **Cutover** | Chuyển consumer, query hoặc search alias sang cấu trúc mới. | Metrics/latency và tính đúng đắn đạt SLO. |
| **Contract** | Dừng ghi/đọc field cũ, xóa index/bảng cũ nếu an toàn. | Không còn process cũ phụ thuộc; hết thời hạn rollback và retention. |

~~~mermaid
sequenceDiagram
    participant Old as App N
    participant New as App N+1
    participant DB as NoSQL
    participant Migrator as Migration pipeline
    Migrator->>DB: Expand schema/index tương thích ngược
    Old->>DB: Đọc/ghi contract cũ
    New->>DB: Đọc được cả hai contract
    Migrator->>DB: Backfill dữ liệu
    New->>DB: Chuyển sang contract mới
    Note over Old,New: Chờ tất cả replica cũ rời cluster
    Migrator->>DB: Cleanup cấu trúc cũ theo phê duyệt
~~~

Với Elasticsearch/OpenSearch, expand thường có nghĩa **tạo physical index v2 rồi reindex và chuyển alias**; với Cassandra thay partition key thường là **bảng mới + chuyển luồng**, còn MongoDB có thể thêm field/index trong collection hiện tại nếu bảo đảm tương thích.

Backfill phải có **checkpoint, idempotency, giới hạn tốc độ và khả năng tiếp tục sau lỗi**. Có thể dùng Spring Batch hoặc job riêng; không khởi chạy backfill dài mỗi lần pod API restart. Nếu phát event qua Kafka/RabbitMQ hoặc ghi read model NoSQL, giữ event ID/schema version để consumer dedupe và xử lý reordering đúng cách.

## 11. Kiểm soát rủi ro với unique index, TTL và index build

### 11.1. Unique index: không chỉ là thao tác hiệu năng

Unique index có thể thay đổi **luật nghiệp vụ**. Nếu dữ liệu lịch sử chứa duplicate, index creation sẽ thất bại. Nếu app đang nhận ghi, duplicate mới có thể tiếp tục xuất hiện **sau preflight nhưng trước khi index bắt đầu enforce**.

Một kế hoạch tốt:

1. Thống nhất định nghĩa uniqueness (tenant, case normalization, null/blank, collation, soft delete).
2. Audit và giải quyết dữ liệu đã trùng, ghi biên bản và cơ chế đối soát.
3. Bảo đảm đường ghi mới không tạo duplicate (idempotency/validation/constraint staging).
4. Tạo unique index khi cluster đủ capacity và kiểm tra trạng thái cuối.
5. Chạy kiểm thử concurrent insert/update để xác minh ràng buộc có hiệu lực.

Một hệ thống ghi đa nguồn không nên chỉ trông cậy vào validation tại một endpoint HTTP: job Batch, consumer broker và lệnh vận hành cũng có thể ghi trùng. Unique index ở datastore hỗ trợ bảo vệ cuối, nhưng cần kiểm tra đúng cấu trúc và phương án xử lý duplicate.

### 11.2. TTL/retention là thay đổi dữ liệu có thể không đảo ngược

TTL index hoặc TTL setting thay đổi **thời gian xóa dữ liệu thực tế**, không chỉ bộ nhớ cache. Khi hạ TTL, dữ liệu cũ có thể bị xóa vĩnh viễn. Trong NoSQL, tiến trình xóa thường bất đồng bộ và có thể tạo I/O tăng đột biến. Với dữ liệu phục vụ audit, thanh toán hoặc compliance, phải phân biệt retention bắt buộc với dữ liệu tạm có thể loại bỏ.

### 11.3. Index build làm ảnh hưởng query hiện hữu

Tạo chỉ mục trên bộ dữ liệu lớn có thể gây CPU/I/O/network pressure, lag replica hoặc tăng dung lượng lưu trữ. DDL “online” không đồng nghĩa không có tác động. Trước khi triển khai cần:

- Ước tính kích thước index, disk free space, thời gian build và latency budget.
- Kiểm tra rate limit/quota của managed service và ảnh hưởng tới workload khác.
- Đặt giám sát tiến độ; có tiêu chí dừng/rollback khi p95/p99 vượt ngưỡng.
- Không đồng thời chạy nhiều build/backfill nặng trong rolling deployment.
- Chỉ chuyển app sang query mới sau khi index đã phục vụ được và contract test đạt.

## 12. Bảo mật và tách quyền application với migration

Phân tách quyền là cách phòng ngừa lỗi cấu hình tốt hơn chỉ dựa vào quy ước code:

| Danh tính | Quyền cần thiết | Không nên có |
| --- | --- | --- |
| **Application runtime** | Đọc/ghi tài liệu, record, index đã có theo collection/table được cấp; các lệnh query cần thiết. | Quyền rộng để drop collection, sửa schema, tạo index tự do. |
| **Migration runner** | DDL/index/schema có giới hạn phạm vi, ghi marker/migration history, đọc metric kiểm chứng. | Secret của ứng dụng không liên quan hoặc quyền admin toàn bộ cluster khi không cần. |
| **Read-only preflight/monitor** | Kiểm tra phiên bản, trạng thái index/schema và các chỉ số được phép. | Quyền mutate hoặc xóa dữ liệu. |

Ở từng datastore, cú pháp phân quyền khác nhau. Ví dụ MongoDB role tùy chỉnh, Cassandra `GRANT` theo keyspace/table, Elasticsearch/OpenSearch role quản lý index/alias, IAM cho DynamoDB table/index. Không giả định vai trò tên `readWrite` ở một datastore tự loại trừ mọi khả năng tạo index; phải rà **quyền cụ thể**.

Lưu secret trong secret manager, dùng credential riêng theo môi trường và tránh in URI/credential vào log. Migration có audit trail gồm operator, phiên bản, thời gian, target, cấu trúc trước/sau và kết quả. Nếu dùng CI/CD job chạy DDL, giới hạn concurrency cho cùng target và không để nhiều cluster tự thực thi cùng thay đổi.

## 13. Kiểm thử đúng: chứng minh startup không đổi schema

Một application context khởi động thành công **chưa đủ chứng minh không có DDL ngầm**. Nên có test chuyên biệt:

| Kiểm thử | Điều cần khẳng định |
| --- | --- |
| MongoDB với `auto-index-creation: false` | Tạo context/repository không tự tạo collection/index còn thiếu; index chỉ được tạo bởi migration. |
| MongoDB index specification drift | Startup không tự drop/rebuild; preflight phát hiện định nghĩa sai và trả lỗi rõ. |
| MongoDB unique index với dữ liệu trùng | Migration từ chối có kiểm soát; không chạy vòng lặp tạo index trên mỗi pod. |
| MongoDB TTL thay đổi | Có báo cáo lượng bản ghi đủ điều kiện xóa; không thay retention âm thầm. |
| Cassandra `schema-action: none` | Startup không CREATE/ALTER keyspace/table; thiếu schema được báo thay vì tự sửa. |
| Elasticsearch `createIndex=false` | Repository startup không tạo index; server-side auto-create và dynamic mapping được quản lý riêng. |
| Elasticsearch reindex + alias | Index v2 đủ dữ liệu, consumer lag đã đóng và alias cutover không làm mất update. |
| Nhiều replica chạy song song | Một migration runner sở hữu thao tác; runtime chỉ thực hiện preflight read-only. |
| Rolling deploy N và N+1 | Cả hai bản tương thích với schema trong giai đoạn expand và migrate. |
| Backfill bị dừng giữa chừng | Restart từ checkpoint, không tạo bản ghi trùng hoặc ghi đè version mới. |
| Application account thiếu DDL permission | Các lời gọi DDL ngoài ý muốn bị từ chối; đường đọc/ghi hợp lệ vẫn hoạt động. |
| Downgrade/rollback app | Không giả định có thể đảo lại index/key schema ngay; contract còn tương thích hoặc có phương án phục hồi. |

Dùng Testcontainers hoặc test cluster phù hợp cho MongoDB/Cassandra/Elasticsearch/OpenSearch và môi trường thử nghiệm được phép cho DynamoDB/Couchbase. Với bài test startup, **chụp snapshot metadata trước và sau**, so index/collection/schema/mapping/alias; đừng chỉ assert HTTP health trả 200.

Một phương pháp test tích hợp:

1. Tạo datastore trống hoặc snapshot có **phiên bản schema cũ** bằng migration fixture.
2. Khởi động ứng dụng **với danh tính runtime không có quyền DDL**.
3. Xác minh rằng app chỉ đọc metadata và phản ứng đúng khi schema chưa tương thích.
4. Chạy migration **riêng**; kiểm tra index schema/options và version marker sau migration.
5. Khởi động app N và N+1; chạy CRUD/query theo contract, mô phỏng ghi đồng thời và crash backfill.
6. So sánh metadata sau test; bảo đảm không có thay đổi lạ do startup, repository hoặc lệnh ghi tự động.

Không nên dùng cùng một tài khoản admin cho tất cả bài kiểm thử rồi kết luận không có rủi ro DDL: cấu hình sai có thể bị che vì test account có quyền quá rộng.

## 14. Quan sát và xử lý sự cố schema/index

### 14.1. Các tín hiệu cần thu thập

- **Migration status:** ID thay đổi, start/end time, người thực thi, target, preflight/result, lỗi và thời điểm hoàn tất.
- **Index health:** index build progress, trạng thái online/ready, kích thước, memory/disk, error hoặc trường hợp drift.
- **Query performance:** read/write latency p50/p95/p99, slow queries, full scan, query plan và workload saturation.
- **Cluster capacity:** CPU, I/O, disk, replication lag, schema agreement, indexing throughput và throttling.
- **Backfill/reindex:** hàng đợi chưa xử lý, số record nguồn/đích, checksum/đếm sai, duplicate/rejection count.
- **Contract compatibility:** lỗi deserialize, unknown fields, mapper failures, lỗi mapping/type và query bị từ chối.

Tách metric label theo datastore, collection/index type và migration ID có cardinality được kiểm soát. Đừng đưa document ID, email, token hoặc tenant key có số lượng lớn vào label/alert công khai.

### 14.2. Runbook: ứng dụng mới lỗi ngay sau rollout

Ví dụ code mới truy vấn theo index `uq_tenant_external` nhưng một môi trường chưa chạy migration:

1. **Khoanh vùng phiên bản:** pod nào lỗi, repository nào, datastore nào, connection credentials và namespace nào.
2. **Kiểm tra cấu trúc thực tế bằng quyền read-only:** index list/schema, options, version marker, alias, trạng thái index build.
3. **Đánh giá tác động:** query không có index có thể chậm nhưng vẫn trả đúng kết quả, hoặc schema/mapping thiếu khiến operation thất bại; không đánh đồng hai trường hợp.
4. **Không bật lại auto-create ở production như hotfix** nếu chưa đánh giá dữ liệu và chi phí build.
5. **Khôi phục an toàn:** dừng rollout/giảm traffic phiên bản mới, chạy migration đã được kiểm chứng hoặc chuyển lại app tương thích với schema hiện tại.
6. **Theo dõi:** độ trễ truy vấn, lag, lock/IO, kết quả backfill, duplicate và trạng thái tất cả replica.
7. **Đối soát và cập nhật pipeline:** bổ sung preflight, release gate và test để môi trường không còn thiếu migration.

### 14.3. Runbook: unique index không tạo được

1. Thu thập lỗi gốc, index name/spec và số lượng tài liệu trùng theo định nghĩa uniqueness thật.
2. Giới hạn các đường ghi có thể tạo duplicate mới trong thời gian xử lý.
3. Đối soát và sửa dữ liệu **theo quyền nghiệp vụ**; không tự xóa một tài liệu chỉ vì nó trùng key.
4. Chạy lại migration sau khi chứng minh preconditions, kiểm tra index tạo thành công và unique constraint hoạt động.
5. Tiếp tục rollout, đối chiếu tất cả writer (HTTP, Batch, broker) có cùng idempotency/normalization.

**Không xử lý bằng cách xóa collection hoặc drop toàn bộ index** để ứng dụng “chạy được”. Sự cố schema là sự cố về **hợp đồng và dữ liệu**, không chỉ là lỗi của một thao tác DDL.

## 15. Checklist trước khi phát hành ứng dụng NoSQL

- [ ] Xác định **schema/index owner** và nơi lưu migration version của mỗi datastore.
- [ ] Đã tắt hoặc kiểm soát các cơ chế framework tự tạo/sửa index/schema khi startup; phân biệt với **server-side auto-create/dynamic mapping**.
- [ ] Runtime service account không có quyền DDL ngoài nhu cầu; migration có credential riêng, được phê duyệt/audit.
- [ ] Các thay đổi unique index, TTL, partition key, analyzer, GSI và retention có preflight + kế hoạch dữ liệu lịch sử.
- [ ] Migration idempotent có so **đúng định nghĩa**; index cùng tên nhưng khác spec là drift cần xử lý.
- [ ] Pipeline tạo và xác nhận index/schema trước khi app N+1 phụ thuộc vào nó; có gate cho index build/backfill.
- [ ] App N/N+1 tương thích trong rolling/canary/blue-green rollout; chỉ cleanup khi không còn consumer cũ.
- [ ] Backfill/reindex có checkpoint, throttling, dedupe và đối soát; sự kiện bất đồng bộ có schema version và ordering strategy.
- [ ] Startup chỉ làm **preflight read-only nhẹ**; không khởi chạy DDL, backfill hoặc sửa dữ liệu ngoài dự kiến.
- [ ] Có test metadata trước/sau startup, nhiều replica, drift, schema cũ, rollback và khả năng phục hồi khi migration thất bại.
- [ ] Có dashboard query/index latency, migration history, lag và runbook cho lỗi schema/index.

**Kết luận:** Dù dùng MongoDB, Cassandra, Elasticsearch/OpenSearch, DynamoDB hay Couchbase, **chỉ mục và schema là tài sản vận hành cần quản lý như một hợp đồng**, không phải side effect được phép phát sinh mỗi lần Spring Boot khởi động. Tách migration khỏi runtime, kiểm soát quyền, đặt phiên bản và điều kiện triển khai, rồi kiểm thử tình huống nhiều replica/rollback sẽ giúp các luồng tích hợp NoSQL vừa có hiệu năng, vừa giữ được tính nhất quán và khả năng phục hồi khi hệ thống thay đổi.
