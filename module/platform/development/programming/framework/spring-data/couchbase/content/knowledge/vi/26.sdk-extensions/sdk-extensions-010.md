# Giữ nhất quán quy tắc mã hóa, TTL, CAS và ánh xạ khi kết hợp các API

Trong một ứng dụng **Spring Data Couchbase**, cùng một document có thể được tạo bởi `CouchbaseRepository`, đọc qua `CouchbaseTemplate`, cập nhật một trường bằng **Couchbase Java SDK KV**, lọc bằng SQL++, hoặc xử lý bởi một job reactive. Các API đều có thể trỏ tới **cùng bucket/scope/collection**, nhưng không có nghĩa chúng dùng chung mọi quy tắc chuyển đổi dữ liệu, thời hạn sống, kiểm soát cạnh tranh và callback của Spring.

Một thay đổi tưởng như đơn giản — chuyển từ `repository.save(session)` sang `collection.upsert(id, json)` để tối ưu — có thể gây ra bốn lỗi khó phát hiện:

- **Sai mã hóa/serialization:** JSON field `user_id` bị ghi thành `userId`, hoặc JSON bị lưu dưới **non-JSON common flag** nên truy vấn SQL++ không nhìn thấy như mong đợi.
- **Sai TTL:** một document phiên làm việc đang hết hạn sau 30 phút bị `replace`/`upsert` làm mất thời hạn và tồn tại lâu ngoài ý định.
- **Mất optimistic locking:** code raw SDK ghi đè document mà không gửi CAS, trong khi Spring entity có `@Version`.
- **Sai ánh xạ:** custom converters, type discriminator, auditing hoặc field-level encryption chỉ chạy trong đường Spring Data, không chạy tự động trong raw SDK.

Bài thuộc chương **Mở rộng bằng SDK** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase với document mapping, Repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, index, TTL, CAS, transaction và API reactive để bảo đảm hiệu năng, tính nhất quán và khả năng vận hành.

> **Nguyên tắc nền tảng:** Kết hợp API ở tầng persistence phải giữ **một hợp đồng document duy nhất**: *keyspace + document key + schema/encoding + TTL policy + CAS policy + security + lifecycle*. SDK direct cho phép thao tác thấp tầng, **không tự thừa hưởng toàn bộ metadata, converter, annotation và callback của Spring Data**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả ranh giới giữa `CouchbaseRepository`, `CouchbaseTemplate`, Java SDK KV, SQL++ và reactive APIs.
2. Phân biệt **encoding/serialization/transcoding** với **encryption**; hiểu Couchbase **JSON common flags**.
3. Kiểm tra sự tương thích giữa SDK `JsonSerializer`/`Transcoder` và Spring Data `CouchbaseConverter`, `@Field`, type key, custom conversions, auditing.
4. Giải thích vị trí lưu **document key, CAS và expiry**: metadata KV chứ không phải các JSON properties được SDK tự điền.
5. Dùng `GetResult.cas()` và `replaceOptions().cas(...)` để không bỏ optimistic locking khi qua SDK.
6. Dùng `getOptions().withExpiry(true)` và `replaceOptions().preserveExpiry(true)` để kiểm soát TTL có chủ đích.
7. Hiểu `@Expiry`/`@Document(expiry=...)`, bucket/collection `maxExpiry` và cách SDK direct có thể đi vòng qua quy tắc Spring.
8. Tránh ghi đè từ partial SQL++ projection hoặc raw SDK upsert thiếu field metadata/JSON.
9. Phân tích lỗi trong SQL++ DML, sub-document updates, Search/Analytics read paths và transaction context.
10. Thiết kế schema contract, compatibility adapter, migration và integration tests **hai chiều Spring ↔ SDK**.
11. Xác định ranh giới mã hóa bảo mật, key rotation và các trường không nên đưa vào Search index/log.
12. Xây checklist code review và observability cho mixed-API persistence.

## 2. Một document, nhiều đường đi

~~~text
Application service
    |
    +-- Repository.save / findById
    |       |
    |   Spring converter + entity lifecycle
    |       |
    +-- CouchbaseTemplate operations
    |       |
    |   Spring mapping/converters tùy operation
    |       |
    +-- SDK Collection.get / replace / mutateIn
    |       |
    |   SDK serializer/transcoder + KV options
    |       |
    +-- SDK Cluster.query (SQL++)
    |       |
    |   Query Service + GSI, SQL++ result shape
    |       |
    +-- SDK reactive().get / replace
            |
        Publisher orchestration
            |
            v
       Bucket / Scope / Collection
            |
            +-- JSON body / common flags
            +-- document key / CAS / expiry metadata
~~~

Sơ đồ nhấn mạnh **đường xử lý khác nhau**, không phải mỗi API kết nối tới một bản dữ liệu riêng. Thực tế SQL++ đi qua Query Service và index, có thể có độ trễ cập nhật GSI; KV GET theo key đọc active document. Reactive là mô hình client không chặn thread, **không tự thay đổi tính nhất quán** của mutation.

Các quy tắc định dạng và vòng đời phải được ghi thành hợp đồng để mỗi đường đi thực hiện tương đương ở những điểm bắt buộc.

## 3. Bài toán xuyên suốt: session có TTL và CAS

Giả sử hệ thống lưu phiên đăng nhập trong:

~~~text
Bucket:       shop
Scope:        auth
Collection:   sessions
Document ID:  session::tenant-01::s-123
~~~

Đây là dữ liệu nhạy cảm: một session phải hết hạn theo chính sách, chỉ thuộc một tenant, và thay đổi đồng thời không được ghi đè tùy tiện.

Entity Spring Data minh họa:

~~~java
import java.time.Instant;
import java.util.concurrent.TimeUnit;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Expiry;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("auth")
@Collection("sessions")
@Expiry(expiry = 30, expiryUnit = TimeUnit.MINUTES)
public class SessionEntity {

    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;

    @Field("user_id")
    private String userId;

    @Field("last_seen_at")
    private Instant lastSeenAt;

    private boolean revoked;

    // Constructor, getters/setters phù hợp Spring Data.
}
~~~

Ví dụ field JSON (chỉ để minh họa shape; biểu diễn `Instant` thực tế phụ thuộc converter/serializer đang dùng):

~~~json
{
  "_class": "com.example.auth.SessionEntity",
  "tenantId": "tenant-01",
  "user_id": "user::42",
  "last_seen_at": "2026-11-25T03:00:00Z",
  "revoked": false
}
~~~

Chú ý:

- `@Id` xác định key lưu trong KV; trường `id` không cần nằm trong body.
- `@Version` dùng CAS do server quản lý; không phải một field JSON `version` với số tăng độc lập.
- `@Field("user_id")` đổi tên field lưu; code SDK raw phải dùng tên JSON thực.
- Spring Data mặc định có thể lưu type discriminator `_class`; tên/giá trị phải đối chiếu cấu hình converter.
- `@Expiry` cấu hình expiry ở đường Spring Data; không tự áp cho raw SDK mutations.
- CAS và thời điểm hết hạn là **metadata ngoài JSON body**.
- Class Java và package nêu trong `_class` là ví dụ, không phải giá trị mặc định của mọi dự án.

## 4. Ma trận rủi ro khi trộn API

| Thuộc tính | Spring Repository/Template | SDK KV direct | Rủi ro khi trộn |
| --- | --- | --- | --- |
| Field mapping | `@Field`, custom conversions | JSON key/serializer đã cấu hình | Ghi sai tên/kiểu field |
| Type metadata | Converter/type key | Không tự thêm discriminator | Repository query/mapping lỗi |
| Auditing | Callback/auditor theo config | Không tự chạy Spring callback | Mất created/modified audit |
| TTL | `@Expiry`/`@Document` và operation policy | `expiry`/`preserveExpiry`/default behavior | Document sống lâu hơn hoặc hết hạn sớm |
| CAS | `@Version` qua converter | `GetResult.cas()` và KV options | Lost update nếu raw upsert |
| Document ID | `@Id`/ID generation | Key truyền tường minh | Đọc/ghi nhầm keyspace/key |
| Binary/JSON | Spring entity mapping | `Transcoder` + common flags | SQL++/Search không thấy JSON |
| Encryption | Có thể tích hợp custom converter/crypto | Phải cấu hình riêng | Ghi plaintext hoặc không giải mã được |
| Security | Service validation + data-access | Cũng cần service validation | Lộ tenant/cross-keyspace |
| Reactive | Spring reactive repository/template | `ReactiveCollection` | Khác mapping dù cùng nonblocking |

Đừng chọn một API chỉ dựa trên khả năng thực hiện `get`/`save`. Tính tương thích đòi **đọc-ghi hai chiều** và giữ nguyên các invariant khi bất kỳ đường nào thực hiện mutation.

## 5. “Mã hóa” có hai nghĩa cần phân biệt

Trong bài này:

1. **Encoding/serialization/transcoding**: biến Java object thành JSON/bytes và ngược lại, gồm UTF-8, field naming, Jackson, SDK common flags.
2. **Encryption (mã hóa bảo mật)**: biến dữ liệu thành ciphertext bằng thuật toán/mật khóa để bảo mật, gồm mã hóa field phía client, TLS hoặc encryption at rest.

Các thao tác hoàn toàn khác nhau:

~~~text
Java entity
    |
    | Spring mapping / SDK serializer
    v
JSON logical fields
    |
    | Optional field-level encryption
    v
JSON with encrypted field(s)
    |
    | SDK transcoder
    v
bytes + common flags
    |
    | TLS over network; server encryption-at-rest if configured
    v
Couchbase stored document
~~~

**JSON encoding không phải encryption**; một field được encode Base64 vẫn không bảo mật. Ngược lại, TLS/encryption-at-rest không làm các JSON field tự khớp `@Field`/converter của Spring.

Mỗi quy tắc phải có owner và test riêng.

## 6. JSON common flags: vì sao bytes không đủ?

Couchbase lưu document body cùng các metadata như CAS, expiry và **common flags**. Với Java SDK:

- `JsonTranscoder` mặc định dùng `DefaultJsonSerializer` để chuyển Java object thành JSON bytes và đánh dấu **JSON common flag**.
- `RawJsonTranscoder` nhận raw JSON `String`/`byte[]` và pass-through, **vẫn đánh dấu JSON**.
- `RawStringTranscoder` lưu chuỗi dạng non-JSON string.
- `RawBinaryTranscoder` lưu raw bytes dạng binary.
- Tùy flags, truy vấn SQL++/index có thể không xử lý document như JSON object.

Ví dụ nguy hiểm:

~~~java
// Đây là một JSON-looking String ở cấp ứng dụng.
String jsonText = "{\"tenantId\":\"tenant-01\"}";

// Không chọn RawStringTranscoder khi chủ đích lưu JSON document
// cần SQL++ query vào trường tenantId.
collection.upsert(
        id,
        jsonText,
        upsertOptions().transcoder(
                RawStringTranscoder.INSTANCE));
~~~

Raw string là **non-JSON data** về mặt flags, dù bytes có dấu ngoặc nhọn. Một JSON body với wrong flags làm các read/query/mapping không còn tương thích theo kỳ vọng.

Quy tắc: xác định **document type hợp lệ** (JSON object, JSON array, scalar hoặc binary) và dùng cùng convention cho mọi API.

## 7. Dùng `JsonTranscoder` và `RawJsonTranscoder` đúng mục đích

SDK mặc định phù hợp khi truyền `JsonObject` hoặc POJO:

~~~java
JsonObject body = JsonObject.create()
        .put("tenantId", "tenant-01")
        .put("user_id", "user::42")
        .put("revoked", false);

collection.upsert(id, body);
~~~

Nếu đã có JSON text hợp lệ từ một serializer riêng:

~~~java
import com.couchbase.client.java.codec.RawJsonTranscoder;
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

String rawJson = """
    {
      "tenantId": "tenant-01",
      "user_id": "user::42",
      "revoked": false
    }
    """;

collection.upsert(
        id,
        rawJson,
        upsertOptions()
                .transcoder(RawJsonTranscoder.INSTANCE));
~~~

Với `RawJsonTranscoder`, SDK **không tự parse/validate đầy đủ JSON theo domain**; người gọi chịu trách nhiệm chắc chắn content là JSON hợp lệ và đúng schema. Nếu dùng default `JsonTranscoder` với một Java `String`, serializer có thể lưu nó thành **JSON string scalar** thay vì JSON object mong muốn.

**Không lấy một payload từ nguồn không tin cậy rồi pass-through chỉ vì tên lớp có chữ “Json”.** Phải validate schema, độ dài và security trước khi ghi.

## 8. Custom Jackson ở SDK không thay converter của Spring Data

Couchbase SDK cho phép thay `JsonSerializer`, ví dụ để hỗ trợ Java Time hoặc naming strategy. Nhưng trong Spring Data Couchbase có **lớp mapping entity riêng**:

| Chi tiết | Owner chính |
| --- | --- |
| Java POJO ↔ JSON bytes từ raw SDK | SDK `JsonSerializer` |
| Lựa chọn JSON/string/binary flags | SDK `Transcoder` |
| `@Field`, type hints, `@Version` | Spring Data `CouchbaseConverter` |
| `@CreatedDate`/`@LastModifiedDate` | Spring auditing/callback được bật |
| Token hóa ID/tenant prefix | Ứng dụng/key generator |
| Kiểm tra bất biến domain | Application/domain service |
| Cryptographic field conversion | Đường crypto được dự án định nghĩa |

Nếu Spring entity có `@Field("user_id")` mà raw SDK serialize một POJO với property `userId`, payload có thể thành:

~~~json
{
  "tenantId": "tenant-01",
  "userId": "user::42",
  "revoked": false
}
~~~

Trong khi Repository mong đợi:

~~~json
{
  "tenantId": "tenant-01",
  "user_id": "user::42",
  "revoked": false
}
~~~

Hai JSON đều hợp lệ, nhưng **không tương đương**. SQL++ predicate theo `user_id` có thể bỏ sót document viết qua raw SDK.

## 9. Type discriminator `_class` và schema version

Spring Data Couchbase mặc định có thể dùng field `_class` làm type key. Tên này có thể được cấu hình khác; không nên hardcode vào mọi microservice khi chưa kiểm tra cấu hình mapping.

Ví dụ một document từ Repository:

~~~json
{
  "_class": "com.example.auth.SessionEntity",
  "tenantId": "tenant-01",
  "user_id": "user::42",
  "revoked": false
}
~~~

Một raw SDK insert chỉ ghi:

~~~json
{
  "tenantId": "tenant-01",
  "user_id": "user::42",
  "revoked": false
}
~~~

Có thể gây vấn đề nếu Spring Repository generated query dựa vào discriminator hoặc converter cần type hint để tái tạo subtype. Không kết luận raw JSON luôn bị từ chối khi thiếu `_class`: kết quả phụ thuộc repository/query mapping, polymorphism và version.

### Contract nên tách hai khái niệm

- **Spring type hint** (ví dụ `_class`): phục vụ mapping/converter.
- **Domain schemaVersion** (ví dụ `schemaVersion: 2`): phục vụ migration/compatibility quy tắc nghiệp vụ.

Hai field không thay thế nhau. Khi package/class Java đổi tên, type hint có thể cần migration. Khi schema đổi field, `schemaVersion` giúp xử lý V1/V2 mà không phụ thuộc FQN của lớp.

Không tự thêm một giá trị `_class` giả nếu converter của dự án không dùng giá trị đó.

## 10. Auditing và callback không tự chạy qua raw SDK

Nếu entity có:

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;
~~~

và Spring auditing đã bật, thao tác qua Repository/Template có thể kích hoạt các callback tương ứng theo cấu hình. Raw SDK:

~~~java
collection.upsert(id, rawJson);
~~~

**Không tự chạy** Spring auditing hoặc validation listener. Rủi ro:

- `createdAt` mất khi full replace body thiếu field.
- `updatedAt` không đổi khi `mutateIn` sửa một field.
- `createdBy`/`lastModifiedBy` không được điền.
- `schemaVersion` không được nâng cấp khi migration rule nằm ở callback.
- Business event/audit trail chỉ chạy qua service path cũ.

Giải pháp: xác định **owner của auditing**. Nếu cả Spring và raw SDK cùng ghi, có thể buộc mọi mutation đi qua application service/audit port dùng chung hoặc dùng riêng domain event/CDC pipeline có consistency rõ. Không chỉ thêm dòng `put("updatedAt", now)` ở vài callsites rồi coi tất cả đường viết đã đồng nhất.

## 11. Document key và keyspace cũng thuộc contract

Một key như `session::tenant-01::s-123` có ý nghĩa **trong một collection cụ thể**.

~~~text
shop.auth.sessions:
    session::tenant-01::s-123

shop.archive.sessions:
    session::tenant-01::s-123
~~~

Hai document khác nhau dù key string giống hệt.

Cần thống nhất:

1. Bucket/scope/collection giữa entity annotations, Template và SDK collection handle.
2. Quy tắc tạo key (tenant prefix, immutable identifier).
3. Field `tenantId` trong body có đồng bộ với key prefix không?
4. Type hints/schema version tương ứng collection.
5. RBAC và business authorization cho mỗi keyspace.
6. TTL/maxExpiry ở bucket/collection được triển khai như thế nào.
7. Index Query/Search có map đúng collection này không?

Đừng để client tự chọn bucket/scope/collection từ query param chưa allowlist. Nếu cần multitenancy theo scope/collection, định tuyến dựa vào trusted tenant context.

## 12. TTL nằm ngoài body JSON

**TTL / document expiry** là metadata của KV item, không phải field body `expiresAt` do SDK tự đọc/ghi.

~~~text
Document key: session::tenant-01::s-123
JSON body:    { "user_id": "...", "revoked": false }
Metadata:     CAS = opaque 64-bit token
              expiry = thời điểm hết hạn/không hết hạn
              common flags = JSON
~~~

Các điều cần phân biệt:

- `@Expiry`/`@Document(expiry=...)` cấu hình policy trên Spring entity khi dùng operations phù hợp.
- `InsertOptions.expiry(...)`, `UpsertOptions.expiry(...)` định nghĩa expiry cho SDK write.
- `replaceOptions().preserveExpiry(true)` giữ expiry hiện có khi đổi body.
- Bucket/collection có `maxExpiry`/quy tắc giới hạn expiry do Server áp dụng.
- `touch`/`getAndTouch` chủ động thay expiry.
- Xóa/hết hạn document có thể làm GSI/Search/Analytics phản ánh thay đổi sau một độ trễ index/ingestion.

**Có field `expiresAt` trong JSON không khiến Server tự hết hạn**. Muốn bảo đảm TTL phải kiểm tra metadata/Server policy, không chỉ so JSON.

## 13. Spring `@Expiry` không tự truyền qua raw SDK

Trong mô hình minh họa:

~~~java
@Expiry(expiry = 30, expiryUnit = TimeUnit.MINUTES)
public class SessionEntity { /* ... */ }
~~~

Repository write có thể áp quy tắc expiry theo mapping/config. Nhưng:

~~~java
JsonObject body = JsonObject.create()
        .put("tenantId", "tenant-01")
        .put("user_id", "user::42")
        .put("revoked", false);

collection.insert(id, body);
~~~

là raw SDK call; **không tự đọc `@Expiry`**.

Nếu nghiệp vụ quy định tạo session mới sống 30 phút, SDK adapter cần explicit policy:

~~~java
import java.time.Duration;
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

collection.insert(
        id,
        body,
        insertOptions().expiry(Duration.ofMinutes(30)));
~~~

Điều này áp thời hạn từ **lúc mutation** theo semantics SDK/Server (và maxExpiry), không nói gì về việc session có được phép *gia hạn* mỗi lần thay đổi hay phải hết hạn tuyệt đối.

Chính sách TTL nên đặt ở **application configuration/domain port** dùng chung, không sao chép magic number 1800 ở nhiều chỗ.

## 14. Bẫy lớn: `replace`/`upsert` có thể xóa expiry cũ

Một session đang có TTL còn 10 phút:

~~~text
T0: session được tạo, TTL 30 phút
T1: sau 20 phút, còn khoảng 10 phút
T2: job raw SDK replace session body
T3: nếu không giữ expiry, quy tắc mutation có thể reset expiry
    (thường thành "không expire" nếu không có maxExpiry ghi đè)
~~~

Couchbase Java SDK docs hướng dẫn dùng **`preserveExpiry(true)`** khi update document cần giữ thời điểm hết hạn:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

GetResult result = sessions.get(id);
JsonObject body = result.contentAsObject();
body.put("revoked", true);

sessions.replace(
        id,
        body,
        replaceOptions()
                .cas(result.cas())
                .preserveExpiry(true));
~~~

Hai bảo đảm riêng:

- `cas(...)`: chỉ mutate nếu document vẫn có CAS đã đọc.
- `preserveExpiry(true)`: giữ expiry cũ thay vì vô tình reset khi replace, trong phạm vi semantics SDK/Server.

Một không tự suy ra cái kia. **CAS không tự giữ TTL; preserveExpiry không tự chống lost update**.

### Không đặt đồng thời expiry mới và preserveExpiry tùy tiện

Hai mục tiêu khác nhau: *giữ expiry hiện có* hoặc *đặt thời hạn mới*. Một số option API không cho dùng cùng lúc hoặc có precedence riêng; chọn một chính sách nhất quán và kiểm thử.

## 15. “Sliding TTL” khác “Absolute expiry”

Hai chính sách cho session:

| Chính sách | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Absolute expiry | Session phải hết hạn lúc 11:00 dù có activity | Update body **phải giữ expiry** |
| Sliding TTL | Mỗi lần hoạt động hợp lệ gia hạn thêm 30 phút | Có thao tác gia hạn expiry chủ đích |
| Fixed retention | Audit record sống 90 ngày từ ngày tạo | Mọi update phải giữ mốc đã chốt |
| Cache TTL | Cache có thể refresh expiry khi recompute | Chọn expiry theo cache policy |

Không chuyển ngầm từ absolute sang sliding chỉ vì gọi `upsert(..., expiry(Duration.ofMinutes(30)))` mỗi lần save.

Nếu business cần sliding TTL, có thể dùng KV `touch` hoặc `getAndTouch`/mutation expiry options theo cách được phép; nhưng phải biết hoạt động nào được phép gia hạn session. Một request đọc session không nhất thiết phải gia hạn.

Khi có yêu cầu bảo mật “logout/revoke ngay”, **không phụ thuộc chỉ vào TTL**; cần thao tác/kiểm tra revoke phù hợp và consistency của đường đọc.

## 16. Đọc và kiểm tra expiry đúng cách

SDK không trả expiry mặc định trên mọi `get`. Khi cần kiểm tra:

~~~java
import java.time.Instant;
import java.util.Optional;
import com.couchbase.client.java.kv.GetResult;
import static com.couchbase.client.java.kv.GetOptions.getOptions;

GetResult current = sessions.get(
        id,
        getOptions().withExpiry(true));

long cas = current.cas();
Optional<Instant> expiry = current.expiryTime();

System.out.println("CAS=" +
        Long.toUnsignedString(cas));
System.out.println("Expiry=" + expiry);
~~~

Cần kiểm tra theo môi trường:

- `Optional.empty()` diễn đạt expiry không hiện diện/không thiết lập theo response SDK, **không tự gán timestamp giả**.
- TTL được lưu theo độ phân giải/phương pháp Server; đừng assert expiry timestamp chính xác từng nanosecond.
- Có thể bị maxExpiry cấp bucket/collection điều chỉnh.
- Nếu document đã hết hạn giữa hai lần kiểm tra, `DocumentNotFoundException` hợp lý.
- Nếu cần đặt expiration tuyệt đối, cân nhắc overload `expiry(Instant)` và phiên bản Server/SDK.
- Đừng dùng Java `System.currentTimeMillis()` làm nguồn duy nhất kết luận Server đã hết hạn khi đồng hồ client/server khác nhau; test với tolerance.

## 17. Bucket/collection `maxExpiry` là một phần chính sách

Ngay cả khi SDK gọi:

~~~java
insertOptions().expiry(Duration.ofHours(4));
~~~

kết quả expiry còn chịu **quy tắc maxExpiry ở bucket/collection**. Các phiên bản Server mới có cơ chế kế thừa từ bucket xuống collection và tùy chọn collection không expiry; chi tiết có thể khác theo version.

Đặt câu hỏi:

1. Bucket có cấu hình `maxExpiry` bao nhiêu?
2. Collection override hay kế thừa?
3. Document có truyền explicit expiry không?
4. Mutation có `preserveExpiry` không?
5. TTL của Repository/Template có tính lại khi save không?
6. Có `touch`/`getAndTouch` ở một service khác không?
7. Có workflow backup/restore/replay làm thay thời hạn không?

Không tự khẳng định `expiry(Duration.ZERO)` tạo “never expire” khi bucket/collection đã có maxExpiry. Phải kiểm chứng policy thật.

## 18. CAS: một token lạc quan theo document

CAS (**Compare And Swap**) thay đổi khi document bị mutate (bao gồm một số thay đổi metadata). Trong Spring Data:

~~~java
@Version
private Long version;
~~~

được mapping theo CAS ở Repository/Template, không phải một counter integer mà app tự tăng trong JSON body.

Ở raw SDK:

~~~java
GetResult existing = sessions.get(id);
long expectedCas = existing.cas();

JsonObject updated = existing.contentAsObject();
updated.put("revoked", true);

MutationResult mutation = sessions.replace(
        id,
        updated,
        replaceOptions().cas(expectedCas));
~~~

Nếu writer khác đã sửa document, replace có thể nhận `CasMismatchException`. **Không tự sửa bằng `upsert` không CAS** vì như vậy bypass optimistic locking.

CAS không phải:

- Timestamp có thể so sánh giữa các documents.
- Số lần thay đổi tuyệt đối.
- ID/version nghiệp vụ có thể đoán.
- Token để làm snapshot query nhiều documents.
- Bằng chứng TTL đã được giữ hoặc mã hóa đã đúng.

Hãy xem CAS như **opaque concurrency token**.

## 19. CAS và `@Version` khi hai writer dùng API khác nhau

Timeline:

~~~text
T0  Repository.findById(id) -> entity.version = CAS-A
T1  Raw SDK get(id)         -> cas() = CAS-A
T2  SDK replace CAS-A       -> thành công, CAS-B
T3  Repository.save(entity cũ với CAS-A)
    -> optimistic-lock conflict
~~~

Đây là hành vi **mong muốn**: Spring Data không được ghi đè trạng thái mới mà không đọc lại.

Tình huống sai:

~~~text
T0  Repository.findById(id) -> CAS-A
T1  Raw SDK upsert(id, body mới) không CAS -> thành công, CAS-B
T2  Repository.save(entity với CAS-A)      -> conflict
~~~

Spring phát hiện xung đột ở T2, nhưng raw SDK đã **ghi đè không điều kiện ở T1**, có thể đã làm mất sửa đổi trước đó. Vì vậy mọi **writer** có thể thay cùng document phải tuân thủ policy, không chỉ bên Repository.

## 20. Phối hợp CAS và TTL trong một read–modify–write

Mẫu SDK khi cần thay một field, giữ body và giữ expiry:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.MutationResult;

import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

public MutationResult revokeSession(
        Collection sessions,
        String id,
        String authenticatedTenant) {

    GetResult current = sessions.get(id);
    JsonObject body = current.contentAsObject();

    if (!authenticatedTenant.equals(
            body.getString("tenantId"))) {
        throw new SecurityException("Tenant mismatch");
    }

    body.put("revoked", true);

    return sessions.replace(
            id,
            body,
            replaceOptions()
                    .cas(current.cas())
                    .preserveExpiry(true));
}
~~~

Đặc tính:

1. Dùng **đúng collection**.
2. Đọc full body và CAS cùng một GET.
3. Check tenant dựa trên principal đã xác thực.
4. Chỉ thay trường cần thay trong full JSON.
5. Không làm mất các field không được mapper hiểu (nếu JsonObject giữ lại đầy đủ).
6. Gửi CAS để chặn concurrent overwrite.
7. Giữ expiry cũ thay vì tạo session không hết hạn.

**Giới hạn:** raw SDK không tự chạy Spring auditing/custom encryption/converter. Nếu entity dùng client-side field encryption hoặc callback bắt buộc, **không dùng mẫu raw full-body replace này nguyên trạng** mà phải đi qua adapter có khả năng tái thực thi đúng quy tắc hoặc dùng Repository/Template thích hợp.

## 21. Vì sao full-body replace cần bảo toàn type key và fields lạ?

Một document Spring Data lưu:

~~~json
{
  "_class": "com.example.auth.SessionEntity",
  "tenantId": "tenant-01",
  "user_id": "user::42",
  "last_seen_at": "2026-11-25T03:00:00Z",
  "revoked": false,
  "schemaVersion": 2,
  "internalFlags": {
    "legacyVerified": true
  }
}
~~~

Một SDK DTO chỉ có:

~~~java
public record SessionCard(
        String userId,
        boolean revoked) {}
~~~

Không được:

~~~java
sessions.replace(id, sessionCard);
~~~

vì serializer có thể tạo một body **chỉ hai field** và mất `_class`, `tenantId`, `last_seen_at`, `schemaVersion`, `internalFlags`. Đó là **partial projection**, không phải full document hợp lệ.

Đúng hướng:

- Dùng Repository để đọc entity đầy đủ, update, save theo `@Version` nếu converter/auditing cần thiết.
- Hoặc dùng SDK `mutateIn` để thay đúng JSON path với CAS/expiry policy.
- Hoặc đọc **full raw JsonObject** và replace CAS, nhưng chỉ khi đủ điều kiện mapping/crypto/lifecycle.

**Projection là read model**, không phải payload an toàn cho full replacement.

## 22. Sub-document `mutateIn`: tốt cho field update, vẫn cần quy tắc

SDK sub-document có thể thay một JSON path mà không gửi cả body:

~~~java
import com.couchbase.client.java.kv.MutateInSpec;
import java.util.List;

sessions.mutateIn(
        id,
        List.of(MutateInSpec.replace(
                "revoked", true)));
~~~

Một `mutateIn` atomically áp các specs trong **một document** theo semantics của subdoc operation. Nó giúp tránh việc tự deserialize/serialize toàn bộ body cho thay đổi nhỏ, nhưng phải xem:

- Path JSON thật (ví dụ `"last_seen_at"`, không phải Java property `lastSeenAt`).
- Field path có tồn tại không; `replace` khác `upsert`/`insert`.
- CAS tùy nhu cầu và chính sách tránh concurrent lost updates.
- TTL: thao tác này có làm thay đổi expiry hay cần preserve theo SDK/Server/version? **Kiểm chứng** thay vì suy diễn từ KV `replace`.
- Spring auditing/callback có cần chạy không?
- Subdoc field được mã hóa bảo mật có thể là ciphertext; sửa plaintext path không tự thực hiện encryption.
- Đây không phải transaction nhiều documents.

Khi một raw subdoc mutation và Repository cùng sửa fields liên quan, cần integration test về CAS, JSON path, auditing và TTL.

## 23. SQL++ query đọc JSON nhưng không chạy Spring entity converter

Một SDK query:

~~~java
QueryResult result = cluster.query(
        """
        SELECT META(s).id AS id,
               s.user_id AS userId,
               s.revoked AS revoked
        FROM `shop`.`auth`.`sessions` AS s
        WHERE s.tenantId = $tenantId
          AND s.revoked = FALSE
        LIMIT 20
        """,
        queryOptions().parameters(
                JsonObject.create()
                        .put("tenantId", tenantId)));
~~~

Trả **SQL++ rows**, không phải `SessionEntity` của Spring Data:

~~~json
{
  "id": "session::tenant-01::s-123",
  "userId": "user::42",
  "revoked": false
}
~~~

Một DTO phù hợp:

~~~java
public record SessionCard(
        String id,
        String userId,
        boolean revoked) {}
~~~

Cần hiểu:

- Alias `userId` do SQL++ định nghĩa, **không phải** `@Field` tự thực thi trên SDK result.
- Row không có đầy đủ `_class`, `last_seen_at` và mọi field nguồn.
- Row không mang CAS trừ khi query projection chọn metadata tương ứng.
- `QueryResult.rowsAs(SessionCard.class)` có thể deserialize sang DTO riêng nếu serializer/schema khớp; không tự chạy Spring callbacks.
- Query Service có mức consistency theo index, khác KV GET; response có thể chưa phản ánh mutation mới nhất.
- Một query trả dữ liệu đúng shape không chứng minh write qua SDK có TTL/CAS policy đúng.

**Không chuyển `SessionCard` thành `SessionEntity` rồi gọi `repository.save(...)`**. Partial entity có thể xóa fields, thay TTL hoặc làm mất optimistic locking.

## 24. Repository query có thể phụ thuộc type metadata

Một repository query method:

~~~java
List<SessionEntity> findByRevokedFalse();
~~~

có thể được Spring Data triển khai dựa trên entity mapping, type discriminator và query/index strategy của phiên bản.

Nếu raw SDK đã xóa `_class` hoặc đổi field `user_id` thành `userId`:

- KV `get(id)` có thể vẫn đọc body thành công.
- SQL++ custom query không lọc discriminator có thể thấy document.
- Derived Repository query có thể **không trả** document vì type/field predicate không khớp.
- Converter khi đọc subtype/polymorphic entity có thể thiếu type hint để tái tạo đúng loại.
- Một custom `SELECT RAW` thiếu metadata Spring cần cũng có thể làm entity mapping sai.

Không kết luận “SDK write thành công là tương thích” chỉ từ mutation ack. Test phải chứng minh **Repository, Template, KV và SQL++** tương tác đúng qua các đường.

## 25. SQL++ UPDATE và TTL/CAS: không suy từ KV options

Một SQL++ DML:

~~~sql
UPDATE `shop`.`auth`.`sessions` AS s
SET s.revoked = TRUE
WHERE s.tenantId = $tenantId
  AND s.revoked = FALSE;
~~~

chạy qua Query Service, không phải nhiều `repository.save(...)`.

Phải xác minh:

1. DML có giữ expiry theo cú pháp/options **của Server đang chạy** không?
2. Nó thay CAS của documents đã sửa như thế nào?
3. Có cần predicate về version/owner để tránh ghi ngoài ý định không?
4. Có đụng encrypted fields hoặc thay plaintext/ciphertext không?
5. Có bỏ qua Spring auditing, converter và type hints không?
6. Predicate có đủ tenant/collection restrictions không?
7. Timeout có thể gây outcome ambiguous ra sao?
8. Có cần transaction khi nhiều documents cùng invariant?

Không copy `preserveExpiry(true)` từ KV option vào một `QueryOptions` giả. Đọc **SQL++ UPDATE** docs và kiểm thử DML expiration behavior trên deployment thực.

Nếu chỉ thay một session theo key, `replace`/`mutateIn` kèm CAS/TTL policy thường dễ lý giải hơn DML rộng.

## 26. Index consistency và KV CAS là hai trục khác nhau

~~~text
T0  KV replace CAS-A -> CAS-B; Data Service xác nhận thành công
T1  KV get trên active document -> nhìn body mới
T2  SQL++ Query Service chưa bắt kịp GSI -> có thể chưa thấy
T3  Search index chưa ingest mutation -> FTS hit có thể stale
T4  Index pipelines hội tụ -> Query/Search bắt kịp
~~~

`QueryScanConsistency.REQUEST_PLUS` có thể khiến Query Service chờ index đạt freshness thích hợp trước query; Search dùng cơ chế consistency riêng, có thể dựa `MutationState`; Analytics có ingestion và scan consistency riêng. Không dùng option của dịch vụ này để cấu hình dịch vụ khác.

CAS giúp **một KV conditional mutation** đối chiếu version của document; **không** tạo snapshot cho SQL++/Search/Analytics.

Khi test cross-API, phải phân biệt:

- **Mapping bug:** field/discriminator sai.
- **TTL bug:** document thực sự hết hạn sớm/muộn.
- **CAS conflict:** writer dùng expected version cũ.
- **Index lag:** raw KV body đúng nhưng indexed query chưa thấy.
- **Authorization bug:** đọc từ sai tenant/keyspace.

Những tình huống này có cách sửa khác nhau.

## 27. Encryption at rest, TLS và field-level encryption

| Bảo vệ | Phạm vi | Có sửa JSON mapping không? | Trách nhiệm |
| --- | --- | --- | --- |
| TLS in transit | Bytes trên đường truyền | Không | Certificate/endpoint/TLS policy |
| Server encryption at rest | Dữ liệu trên lưu trữ khi deployment hỗ trợ | Không | Keys, backups, edition, config |
| Client-side field-level encryption | Một số JSON fields trước khi gửi | **Có thể đổi stored shape** | Crypto library, key IDs, serializer, queries |

Java SDK có **thư viện Field-Level Encryption tùy chọn** cho JSON fields trong edition/deployment phù hợp. Nó không tự bật vì Spring entity có `@Field` hay vì API gọi `Cluster.connect`.

Nếu Repository path encrypt `contact_email` mà raw SDK ghi plaintext vào cùng field, có thể gây:

- Mất confidentiality.
- Một số readers không decrypt được.
- Search/Index vô tình chứa plaintext.
- Key rotation/migration không nhất quán.
- Audit/compliance phân loại sai.

**Base64 là encoding, không phải encryption.** Không tự viết crypto algorithm, không để keys trong source code hay cùng document với ciphertext.

## 28. Một contract field-level encryption dùng chung

Dữ liệu logical:

~~~json
{
  "tenantId": "tenant-01",
  "user_id": "user::42",
  "contact_email": "user@example.com"
}
~~~

Representation lưu khi encrypt có thể là **encrypted field envelope** theo library/config:

~~~text
Logical plaintext:     user@example.com
Crypto component:      encrypt(keyId, associatedData, plaintext)
Stored document:       ciphertext + metadata theo thư viện
Crypto component:      decrypt(stored representation)
Domain read model:     user@example.com
~~~

Đây là mô tả kiến trúc, **không phải code mã hóa tự chế**.

Chính sách:

1. Xác định field nào được encrypt, khi nào decrypt, ai được quyền.
2. Cả Spring path và SDK path phải dùng cùng crypto adapter nếu được phép ghi field đó.
3. SDK raw update field không nhạy cảm không nên ghi lại POJO thiếu encrypted fields.
4. Update encrypted field phải đi qua component có keys/key IDs hợp lệ.
5. Quản lý rotation/migration, không ghi plaintext khi fallback.
6. Không log keys, ciphertext, plaintext không cần thiết.
7. Kiểm soát Search index, Analytics dataset và logs đối với field này.
8. Không kỳ vọng equality/FTS/range query trên ciphertext có cùng semantics với plaintext.
9. Kiểm thử mixed key versions và missing/invalid key.
10. Không cho phép lỗi decrypt bị biến thành `null`/empty DTO hợp lệ.

## 29. Schema version, crypto key ID và type hint khác nhau

Một document có thể có:

~~~json
{
  "_class": "com.example.auth.SessionEntity",
  "schemaVersion": 3,
  "encryptionKeyVersion": "k2026-11",
  "tenantId": "tenant-01"
}
~~~

- `_class`: Spring Data type hint nếu converter sử dụng.
- `schemaVersion`: phiên bản cấu trúc và quy tắc domain của ứng dụng.
- `encryptionKeyVersion`: **field ứng dụng minh họa**, nếu crypto library design cần metadata tìm key.

Không tự thêm `encryptionKeyVersion` như thể Couchbase SDK bắt buộc có nó. Nhiều FLE implementations dùng envelope/key metadata riêng.

Không dùng CAS làm schema version hoặc `_class` làm toàn bộ chiến lược migration: chúng biểu diễn những thứ khác nhau.

## 30. Encryption và idempotency: đừng so raw bytes bừa

Một job replay cần biết “logical command đã được áp dụng chưa?”. Hash serialized JSON tùy tiện dễ sai:

- Thứ tự JSON object fields có thể đổi.
- `Instant` có thể serialize khác.
- Ciphertext có thể khác mỗi lần do random nonce/IV dù plaintext giống.
- Auditing timestamp thay đổi theo mutation.
- Type hint thay khi rename class.
- CAS khác sau mutation.

Khi cần idempotency, dùng **event ID/domain version** hoặc canonical logical representation đã được kiểm chứng. Fingerprint chỉ dựa trên fields có ý nghĩa, canonicalization rõ; nếu chứa PII có thể dùng keyed hash/HMAC và retention policy.

Không retry cả batch vì ciphertext/bytes khác khi thực tế chỉ khác encryption nonce/metadata.

## 31. Document Contract cho mọi writer

| Thuộc tính | Quy tắc ứng dụng đề xuất |
| --- | --- |
| Keyspace | `shop.auth.sessions` |
| Key | `session::{tenantId}::{sessionId}`, immutable |
| Body | JSON object, JSON common flag |
| Type hint | Theo Spring converter config |
| Schema | `schemaVersion=3`, migration V2/V3 |
| Fields | `user_id`, `last_seen_at`, `tenantId`, `revoked` |
| Required | `tenantId`, `user_id`, `revoked` |
| Encryption | Fields nhạy cảm qua crypto policy, không raw plaintext |
| Creation TTL | 30 phút, xét maxExpiry |
| Update TTL | Giữ absolute expiry trừ explicit extend |
| Concurrency | CAS hoặc transaction/domain invariant phù hợp |
| Auditing | Chạy qua chung audit policy |
| Authorization | Tenant từ principal, xác minh khi mutation |
| Error handling | CAS conflict ≠ not-found/timeout/permission |
| Retry | Không retry non-idempotent writes mù |
| Cross-API | Repository/Template/SDK/SQL++ tương thích |
| Observability | CAS conflict, TTL violation, schema/crypto errors |

**Contract không chỉ là annotation**. Spring `@Expiry` giúp Spring path; raw SDK writer phải thực hiện tương đương trong adapter.

## 32. Đặt policy ở port/adapter thay vì controller

Một port:

~~~java
public interface SessionStore {
    SessionView findCurrent(
            String sessionId, String authenticatedTenant);

    SessionView revoke(
            String sessionId, String authenticatedTenant);

    SessionView extendExpiryIfAuthorized(
            String sessionId, String authenticatedTenant);
}
~~~

SDK adapter:

~~~java
public final class SdkSessionStore implements SessionStore {

    private final Collection sessions;
    private final SessionDocumentPolicy policy;

    public SdkSessionStore(
            Collection sessions,
            SessionDocumentPolicy policy) {
        this.sessions = sessions;
        this.policy = policy;
    }

    // Mọi thao tác qua policy:
    // keyspace, tenant, JSON, TTL, CAS, crypto, auditing.
}
~~~

`SessionDocumentPolicy` và `SessionView` là **thành phần ứng dụng minh họa**, không phải types SDK. Policy có thể chứa TTL duration, field names, schema version, rule gia hạn và validation.

Lợi ích: một nơi sở hữu quy tắc, dễ test hai chiều, không để controllers chọn `preserveExpiry`/bỏ CAS tùy request, không lộ raw `JsonObject` ra API.

## 33. Khi nào giữ Repository/Template thay vì chuyển SDK?

Hạ tầng qua SDK khi có nhu cầu rõ:

- `mutateIn` hoặc KV option chưa được abstraction đang dùng expose thuận tiện.
- Bounded concurrency cho nhiều keys độc lập.
- Replica reads, Search/Analytics hoặc metadata thấp tầng.
- Benchmark chứng minh bottleneck ở đường mapping/operation cụ thể.

Nếu tác vụ chỉ là load–modify–save entity đầy đủ có custom conversions, auditing, `@Version`, `@Expiry`, **Repository/Template có thể an toàn và đơn giản hơn**.

Không giả định SDK direct luôn nhanh hơn: reimplement mapping, crypto, validation, auditing, CAS retry có thể tốn công và tạo lỗi nghiêm trọng.

## 34. Reactive SDK không tự kế thừa Spring mapping

~~~java
public Mono<MutationResult> revokeReactive(
        Collection sessions,
        String id,
        String tenantId) {

    return sessions.reactive().get(id)
            .flatMap(current -> {
                JsonObject body = current.contentAsObject();

                if (!tenantId.equals(
                        body.getString("tenantId"))) {
                    return Mono.error(
                            new SecurityException("Tenant mismatch"));
                }

                body.put("revoked", true);

                return sessions.reactive().replace(
                        id,
                        body,
                        replaceOptions()
                                .cas(current.cas())
                                .preserveExpiry(true));
            });
}
~~~

Đây là code cấu trúc; imports Reactor/SDK và bean lifetime cần bổ sung theo project.

Dù dùng `Mono`:

- Field names/JSON vẫn do SDK xử lý.
- Spring `@Version`/`@Expiry` không tự chạy trên raw SDK call.
- CAS và preserve expiry vẫn cần explicit.
- Subscription có thể cancel/timeout, write outcome có thể ambiguous.
- Conflict retry cần read–merge–write lại đúng invariant.
- Không `block()` trong WebFlux event loop.
- Không `subscribe()` lén trong service rồi báo success.

**Reactive thay orchestration client, không thay document semantics.**

## 35. Retry phải giữ CAS và TTL invariants

Anti-pattern:

~~~java
try {
    sessions.replace(id, body,
            replaceOptions().cas(oldCas));
} catch (Exception ignored) {
    sessions.upsert(id, body);
}
~~~

Biến CAS conflict thành unconditional write, có thể reset TTL và mất dữ liệu writer khác.

Hướng đúng:

1. Phân loại `CasMismatchException`, not-found, timeout, RBAC.
2. Với conflict, đọc lại document và CAS hiện hành.
3. Kiểm tra lại tenant/authorization và invariant.
4. Áp lại **thay đổi domain**, không replay toàn stale body.
5. CAS replace mới, vẫn giữ đúng TTL/crypto/audit policy.
6. Retry bounded, có backoff nếu cần.
7. Ambiguous timeout yêu cầu reconciliation/idempotency, không giả định chưa ghi.
8. Không retry toàn bộ batch khi chỉ một item conflict.

Chỉ lấy CAS mới mà không kiểm tra lại business invariant vẫn có thể ghi sai.

## 36. Transaction context không tự lan vào raw SDK call

Nếu use case yêu cầu nhiều documents **all-or-nothing**, phải dùng transaction API và Spring integration đúng phiên bản.

Không giả định:

~~~java
@Transactional
public void updateSeveral() {
    repository.save(a);
    collection.upsert(idB, bodyB); // Có thể ngoài transaction context
}
~~~

là transaction nguyên tử cho cả hai thao tác. Một raw `Collection.upsert(...)` không tự enlist trong Spring-managed transaction **chỉ vì dùng cùng Cluster**. Việc một operation tham gia transaction phụ thuộc context/API integration và cách gọi.

Cần chọn:

- Tất cả operations đi qua cùng transaction context được hỗ trợ.
- Hoặc phân tách invariant bằng CAS/idempotency/saga khi phù hợp.
- Không chèn raw SDK call ngoài context chỉ vì method tiện hơn.

CAS chống lost update của **một document**. Durability xác nhận mutation theo policy, **không tự tạo atomicity nhiều documents**.

## 37. CAS, expiry và durability là các chiều độc lập

Ví dụ SDK:

~~~java
MutationResult result = sessions.replace(
        id,
        fullBody,
        replaceOptions()
                .cas(expectedCas)
                .preserveExpiry(true)
                .durability(DurabilityLevel.MAJORITY));
~~~

| Option | Giải quyết | Không giải quyết |
| --- | --- | --- |
| `cas(expectedCas)` | Chặn conditional write nếu version cũ | Không tự giữ TTL/mã hóa |
| `preserveExpiry(true)` | Giữ expiry khi update | Không chống lost update |
| `durability(MAJORITY)` | Chính sách xác nhận mutation | Không bảo đảm schema/transaction |
| `timeout(...)` | Giới hạn thời gian chờ ở client | Không chắc mutation chưa xảy ra khi timeout |
| `expiry(Duration)` | Đặt expiry mới | Không tạo lock/CAS |

Dùng options phối hợp khi SDK/Server phiên bản hỗ trợ và hợp đồng yêu cầu; benchmark vì durability có thể tăng latency. Không suy ra Spring Repository và raw SDK có options mặc định giống nhau chỉ vì kết nối cùng Cluster.

## 38. Quy trình migration từ Repository sang SDK có kiểm soát

**Pha 1 — Khám phá**

1. Tạo fixture qua Repository trên test cluster.
2. Đọc raw JSON, CAS, expiry, common flags qua SDK.
3. Ghi lại `@Field`, type key, custom conversions, auditing.
4. Kiểm tra encryption và maxExpiry bucket/collection.
5. Xác định key generator/tenant/authorization.
6. Viết Document Contract.

**Pha 2 — Adapter nhỏ**

1. Chỉ chọn operation nhỏ, ví dụ revoke một session.
2. Bắt đầu bằng full GET + CAS replace + preserve expiry.
3. Nếu cần, tối ưu sang `mutateIn` sau khi test semantics.
4. Không chạm encrypted fields nếu adapter chưa được cấp crypto policy.
5. Viết unit tests cho mapper; integration tests Spring ↔ SDK.
6. Đo CAS conflicts và TTL behavior.

**Pha 3 — Canary**

1. Bật feature flag cho một tập nhỏ.
2. Theo dõi missing fields, query hits, expiry, error rates.
3. So sánh behavior Spring-only và SDK path.
4. Có rollback về write path cũ có kiểm soát; tránh rollback schema tùy tiện.
5. Giữ một owner rõ khi hai writers cạnh tranh cùng key.

**Pha 4 — Mở rộng**

1. Version hóa schema/key rotation.
2. Backfill dữ liệu cũ theo pipeline có checkpoint.
3. Loại bỏ fallback V1 khi biết không còn dữ liệu cần nó.
4. Tái kiểm tra index/consumer compatibility, audit và SLO.

## 39. Integration test hai chiều: Repository → SDK → Repository

Kịch bản:

~~~text
Given  Repository.save(SessionEntity)
       tạo body bằng @Field/type key và CAS, TTL theo policy.

When   SDK get + replace(CAS, preserveExpiry)
       chỉ thay field revoked.

Then   Repository.findById vẫn map đúng SessionEntity.
And    user_id, _class, schemaVersion và fields khác không mất.
And    @Version phản ánh CAS mới.
And    expiry không vô tình reset/gia hạn.
And    tenant/authorization giữ nguyên.
~~~

Trong bước save sau:

- Repository phải load current entity/version nếu cần update.
- Entity cũ chứa CAS trước SDK mutation phải bị conflict.
- Không tự gán CAS mới vào một partial entity rồi save để vượt kiểm tra.

Bài test này trực tiếp bắt lỗi “SDK write thành công nhưng Spring không còn đọc/ghi đúng”.

## 40. Integration test ngược: SDK → Repository → SDK

~~~text
Given  SDK tạo document theo shared contract.
When   Repository.findById(id).
Then   converter dựng entity đúng type/fields.

When   Repository.save(entity đã thay đổi).
Then   SDK get thấy đúng raw JSON, CAS mới và TTL theo policy.
And    common JSON flag tương thích SQL++/index.
And    encrypted fields và auditing vẫn đúng.
~~~

Khi SDK tạo document, **không** tự gán `_class` bằng chuỗi class package tưởng tượng. Lấy contract/type alias thực từ project/test fixtures; nếu Repository derived query cần discriminator, phải test thêm query đó.

Tạo cùng ID trong hai collections để kiểm tra routing. Kiểm thử cả JSON body thiếu field, schema v1/v2 và custom converter.

## 41. TTL tests: đo metadata với tolerance

Các kịch bản:

1. Tạo document qua Repository với TTL ngắn trong môi trường cô lập.
2. SDK GET với `withExpiry(true)` ghi nhận expiry.
3. Raw replace không preserve trong **negative test**; quan sát semantics thật.
4. Raw replace có `preserveExpiry(true)` trong **positive test**.
5. So expiry trước/sau với tolerance theo Server độ phân giải.
6. Test maxExpiry bucket/collection và inheritance.
7. Test `touch`/`getAndTouch` cho sliding expiry riêng.
8. Test Repository save sau SDK mutation: expiry có reset/gia hạn theo annotation không?
9. Test document hết hạn, nhận not-found theo deadline.
10. Test reactive path có cùng contract.

Không chỉ `Thread.sleep(500)` rồi assert document đã biến mất: TTL resolution, scheduling, index lag và test cluster load có thể gây flaky tests. Dùng thời hạn/phạm vi đủ hợp lý, polling có timeout và đọc metadata khi cần.

## 42. CAS tests cho hai writers

**A — SDK thắng trước:**

~~~text
Repo read CAS-A
SDK read CAS-A
SDK replace(CAS-A) -> CAS-B
Repo save(entity CAS-A) -> OptimisticLockingFailureException
~~~

**B — Spring thắng trước:**

~~~text
Repo read CAS-A
SDK read CAS-A
Repo save(entity CAS-A) -> CAS-B
SDK replace(CAS-A) -> CasMismatchException
~~~

**C — Anti-pattern:**

~~~text
Repo read CAS-A
SDK upsert không CAS -> CAS-B
Repo save CAS-A -> conflict
~~~

C cho thấy raw SDK đã có thể ghi đè trước khi Repository phát hiện entity cũ.

Lưu ý:

- Không compare CAS bằng số lớn hơn/nhỏ hơn hay wall-clock order.
- Không dùng CAS của key khác.
- Không đưa raw 64-bit CAS qua JavaScript `Number` nếu có nguy cơ mất precision.
- Ánh xạ exception Spring/SDK thành một domain conflict nếu cần, nhưng giữ error diagnostics ở lớp hạ tầng.

## 43. Kiểm thử encoding và schema evolution

| Case | Điều cần xác nhận |
| --- | --- |
| Java property `userId` và JSON `user_id` | Repo/SDK đọc cùng field |
| `_class` mặc định/custom | Derived query và converter đúng |
| Schema V1 thiếu `revoked` | Default/migration policy rõ |
| Schema V2 đổi field name | Cả hai paths xử lý tương thích |
| Unknown fields | SDK update không xóa ngoài ý định |
| JSON common flag | SQL++ có thể query document |
| Raw string/binary document | Không decode như JSON object |
| `Instant`/timezone | Serializer/converter hiểu cùng mốc |
| PII field encryption | SDK path không ghi plaintext |
| Key rotation | Readers xử lý key version cũ/mới |
| Missing decryption key | Fail closed, không trả null giả |
| Number/enum sai kiểu | Không coercion tạo sai business |
| Tenant mismatch | Không đọc/ghi chéo dù key format hợp lệ |
| Search index | Không index plaintext/ciphertext ngoài policy |
| Auditing | Có dấu vết thay đổi ở mọi write paths |

Đừng chỉ kiểm thử POJO ↔ JSON round trip; cần cả **KV flags, Spring mapping, SQL++ predicate và quyền truy cập**.

## 44. Quan sát lỗi cross-API trong vận hành

| Tín hiệu | Giả thuyết cần xác minh |
| --- | --- |
| CAS conflicts tăng | Hai writers cạnh tranh/stale entity |
| Session hết hạn quá sớm/muộn | TTL reset/maxExpiry/policy |
| Repository query 0 hits nhưng KV thấy | Type key/field/index lag |
| JSON decode errors | Common flag/schema/serializer lệch |
| Missing `_class`/schemaVersion | Raw writer bypass mapping |
| Audit fields mất | SDK path không gọi callback |
| Search/Analytics stale | Index/ingestion lag |
| Crypto decrypt failures | Key ID/rotation/ciphertext không hợp lệ |
| Tenant authorization violation | Routing/IDOR/multi-tenant bug |
| Ambiguous write timeout | Cần reconciliation, không retry mù |
| Latency và resultSize tăng | Payload/serialization/IO bottleneck |

Không log plaintext, raw JWT, keys hoặc full document chứa PII để chẩn đoán. Ghi operation, allowlisted keyspace, error category, schemaVersion và correlation ID. Tránh dùng document key như metric label có cardinality cao.

Query Service trả ít hits sau write có thể do index lag chứ không phải schema drift; xác minh raw KV body và metadata trước khi kết luận.

## 45. Các lỗi thường gặp

| Anti-pattern | Hậu quả | Thay thế |
| --- | --- | --- |
| SDK upsert POJO bằng Java property | Sai `@Field`/converter | Document schema contract |
| Lưu JSON-looking text bằng RawString | Non-JSON common flag | `JsonTranscoder`/`RawJsonTranscoder` |
| Base64 gọi là encryption | Không có bảo mật | Crypto library chuẩn |
| SDK ghi plaintext vào encrypted field | Lộ dữ liệu/không decrypt | Crypto adapter thống nhất |
| Raw replace xóa `_class` | Derived query/mapping sai | Full JSON contract |
| `@Version` được map thành JSON counter tự tăng | Mất CAS | CAS của KV/Spring |
| CAS conflict thì upsert | Lost update | Read–merge–replace với CAS |
| Replace quên preserve expiry | Session còn sống ngoài ý định | TTL policy explicit |
| SDK insert dựa vào `@Expiry` | TTL không được cấu hình | SDK expiry options |
| Gia hạn TTL ở mọi read | Sliding policy ngoài ý định | Touch khi được phép |
| Đọc expiry không withExpiry | Metadata thiếu | Yêu cầu expiry rõ |
| Save partial projection thành entity | Mất fields | Read DTO ≠ write entity |
| DML tưởng chạy callback Spring | Auditing/TTL/encryption sai | DML tests riêng |
| `REQUEST_PLUS` làm CAS lock | Không chống lost update | CAS/transaction |
| Raw SDK call trong `@Transactional` | Có thể ngoài transaction | Đúng transaction context |
| Retry timeout mù | Double apply/ghi đè | Idempotency/reconciliation |
| Search bỏ tenant filter | Data leak | Tenant filter + KV auth |
| Chỉ unit-test một mapper | Không bắt drift TTL/CAS/flags | Integration tests hai chiều |

## 46. Ma trận chọn kỹ thuật

| Nhu cầu | Đường ưu tiên | Điều kiện |
| --- | --- | --- |
| CRUD entity có converter/auditing | Repository/Template | `@Version`/`@Expiry` theo config |
| Đổi một field session | SDK `mutateIn` hoặc Template | Path thật, CAS/TTL/audit |
| Full replace có version | SDK `replace` | CAS, preserve expiry, full JSON |
| Tạo session 30 phút | Repository hoặc SDK `insert(expiry)` | TTL/security đúng |
| Gia hạn session có điều kiện | `touch`/`getAndTouch`/mutation | Sliding TTL policy |
| Đọc current version để sửa | KV GET/Repository | CAS/current auth |
| Lọc nhiều docs | SQL++ Query/GSI | Index/consistency/DTO |
| Text search | Search Service | Index lag, auth, hydrate |
| Tổng hợp lịch sử | Analytics | Ingestion lag/aggregate DTO |
| Nhiều docs cùng commit | Transaction | Context tương thích |
| Copy/migrate data | Versioned mapper/pipeline | Schema, crypto, TTL |
| Raw non-JSON binary | `RawBinaryTranscoder` | Không dùng entity JSON query |
| Field bảo mật | Crypto library + policy | Key rotation, không plaintext |

## 47. Checklist code review

### Encoding và mapping

- [ ] Đúng bucket/scope/collection/key generator.
- [ ] JSON common flag đúng; không lẫn RawString và JSON object.
- [ ] Field names khớp `@Field`, nested paths, converters.
- [ ] Type hint `_class`/alias phù hợp Spring config.
- [ ] Schema version khác CAS/type hint, có migration policy.
- [ ] SDK serializer không bị coi là Spring `CouchbaseConverter`.
- [ ] Auditing/callback owner khi raw SDK mutation.
- [ ] Không dùng partial projection để full replace.
- [ ] Encryption đúng field, không log plaintext/keys.

### TTL, CAS và transaction

- [ ] TTL absolute hay sliding được viết rõ.
- [ ] Raw insert/replace/upsert có expiry/preserve policy.
- [ ] Đã kiểm tra bucket/collection maxExpiry.
- [ ] Expiry metadata dùng `withExpiry(true)` khi cần.
- [ ] Conditional writes dùng CAS đúng.
- [ ] Không giải conflict bằng unconditional upsert.
- [ ] Retry có idempotency/ambiguous policy.
- [ ] DML/subdoc TTL/auditing semantics có test riêng.
- [ ] Multi-doc invariant dùng transaction/saga phù hợp.

### Security, vận hành và QA

- [ ] Tenant từ authentication context, authorize từng key.
- [ ] Search/Analytics/Query không rò fields nhạy cảm.
- [ ] Index lag không bị chẩn đoán thành CAS/TTL bug.
- [ ] Cluster do Spring quản lý và tái sử dụng.
- [ ] Reactive path không block event loop.
- [ ] Có integration tests Spring ↔ SDK cả hai hướng.
- [ ] Có metrics cho CAS, expiry, decode, crypto errors.
- [ ] Có canary/rollback plan khi đổi write path.
- [ ] Đã kiểm chứng Server/SDK/Spring versions trước triển khai.

## 48. Bài tập thực hành

**Phần A — Khám phá schema thực**

1. Tạo `SessionEntity` với `@Field`, `@Version` và `@Expiry`.
2. Save bằng Repository.
3. SDK GET, quan sát JSON shape, type key, field names.
4. Dùng `getOptions().withExpiry(true)` đọc expiry, ghi CAS.
5. So sánh body với Java entity và KV metadata.
6. SQL++ query bằng `user_id` và tenant filter.

**Phần B — Ghi SDK mà không làm hỏng session**

1. Implement `revokeSession` full GET + CAS replace + preserve expiry.
2. Đọc lại Repository, kiểm tra mapped fields/`@Version`.
3. Thử bỏ preserve expiry trong negative test riêng.
4. Thử body partial và quan sát field bị mất trong fixture.
5. Sửa bằng full-body contract hoặc subdoc.
6. Gây CAS conflict giữa Repository/SDK.

**Phần C — Encoding và encryption**

1. So Java POJO từ SDK serializer và entity từ Spring converter.
2. Dùng `RawJsonTranscoder` lưu JSON đã validate.
3. Test `RawStringTranscoder` để quan sát khác biệt flags/query.
4. Với môi trường hỗ trợ, kiểm chứng field encryption cả hai paths.
5. Test key rotation và no-plaintext logs/Search index.
6. Viết mapper `schemaVersion` V1/V2.

**Phần D — Kiến trúc**

1. Lập Document Contract đầy đủ.
2. Viết ma trận Spring write/SDK read và SDK write/Spring read.
3. Test absolute vs sliding TTL.
4. So KV GET với SQL++ ngay sau mutation, giải thích index lag.
5. Mô phỏng ambiguous timeout và reconciliation.
6. Viết ADR chọn Repository/Template hay SDK cho một operation.
7. Nêu test/QA chuyên môn cần chạy trước production.

### Câu hỏi tự kiểm tra

1. Encoding có giống encryption bảo mật không?
2. JSON common flag có vai trò gì?
3. RawStringTranscoder có thể làm một JSON-looking string khó query thế nào?
4. SDK JsonSerializer có tự hiểu `@Field` không?
5. `_class` và `schemaVersion` khác nhau ra sao?
6. CAS/expiry/key nằm ở body hay KV metadata?
7. Vì sao Spring `@Expiry` không tự ảnh hưởng SDK insert?
8. `preserveExpiry(true)` và `cas(...)` giải quyết hai việc nào?
9. Absolute TTL và sliding TTL khác nhau thế nào?
10. Bucket/collection maxExpiry có thể ảnh hưởng explicit TTL ra sao?
11. Vì sao `@Version` không phải counter Java tăng thủ công?
12. SDK upsert không CAS có được Spring version bảo vệ không?
13. Vì sao partial SQL++ projection không làm full replacement?
14. `mutateIn` có tự chạy Spring auditing/encryption không?
15. SQL++ DML có kế thừa `@Expiry` không?
16. `REQUEST_PLUS` có tạo CAS lock không?
17. Spring transaction có tự enlist raw SDK writes tùy ý không?
18. Re-serialize encrypted field có nguy cơ gì?
19. Vì sao hash ciphertext không ổn định cho idempotency?
20. Các tests Spring ↔ SDK phải bao phủ gì?
21. Session hết hạn sai: phân biệt TTL reset với index lag ra sao?
22. Durability có thay CAS/transaction được không?
23. Tenant auth/audit nên nằm ở đâu khi nhiều write paths?
24. Khi nào giữ Repository thay vì “tối ưu” sang SDK direct?

## 49. Tài liệu chính thức và đối chiếu phiên bản

- [Couchbase Java SDK — Transcoders and Non-JSON Documents](https://docs.couchbase.com/java-sdk/current/howtos/transcoders-nonjson.html): `JsonTranscoder`, `JsonSerializer`, common flags, RawJson/String/Binary.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): CAS, expiry, `withExpiry`, `preserveExpiry`, mutation options.
- [Couchbase Java SDK — Data Durability and Expiration](https://docs.couchbase.com/java-sdk/current/concept-docs/data-durability-acid-transactions.html): maxExpiry, durability, transaction boundaries.
- [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): `lookupIn`/`mutateIn`.
- [Couchbase Java SDK — Field-Level Encryption](https://docs.couchbase.com/java-sdk/current/howtos/encrypting-using-sdk.html): optional library, encryption key management.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): Query Service và consistency.
- [Couchbase Java SDK — Transactions](https://docs.couchbase.com/java-sdk/current/howtos/distributed-acid-transactions-from-the-sdk.html): multi-document transactions.
- [Couchbase Java SDK — Async/Reactive APIs](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-async-apis.html): reactive KV và concurrency.
- [Spring Data Couchbase — Entity Modeling](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Field`, `@Version`, type hints, auditing, expiry.
- [Spring Data Couchbase — @Expiry API](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/core/mapping/Expiry.html): expiry unit/expression.
- [Spring Data Couchbase — Repository](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD/entity mapping và optimistic locking.
- [Spring Data Couchbase — Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): lower-level entity operations.
- [Couchbase Server — SQL++ UPDATE](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/update.html): DML và version-dependent expiry behavior.

**Lưu ý phiên bản:** Các code snippets minh họa **Couchbase Java SDK 3.x** và Spring Data Couchbase tương thích. Tên/chữ ký `@Expiry`/`@Document`, maxExpiry, preserve-expiry, common flags, SDK transcoders, custom conversion, transaction integration và field-level encryption phụ thuộc **Server/SDK/Spring Data/edition**. Trước khi dùng production cần khóa dependencies, compile, integration test và đánh giá TTL/CAS/crypto trên deployment thực. Nội dung viết ở STEP 4 không thay vòng Content QA chuyên môn/biên dịch ở STEP 6.

> **Ghi nhớ:** Cùng truy cập một key không có nghĩa Repository, Template và SDK direct **tự tương thích**. Hãy giữ một Document Contract về encoding/common flags, field names/type hints/schema, encryption, TTL và CAS. `cas(...)` chống ghi đè stale version, `preserveExpiry(...)` giữ thời điểm hết hạn, converter giữ mapping, crypto bảo vệ fields — **không cơ chế nào tự thay nhiệm vụ của cơ chế khác**.

