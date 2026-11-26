# Tiêu chí dùng SDK trực tiếp khi Repository hoặc Template chưa đáp ứng

Trong module **SPRING_DATA_COUCHBASE**, Spring Data cung cấp hai lớp truy cập rất hữu ích: **Repository** cho thao tác hướng domain và **CouchbaseTemplate** cho các thao tác linh hoạt hơn nhưng vẫn dựa vào cơ chế mapping của Spring Data. Bên dưới, ứng dụng vẫn sử dụng **Couchbase Java SDK** để giao tiếp với Couchbase Server.

Câu hỏi thiết kế không phải “SDK có nhanh hơn Repository không?”, mà là:

> **Bài toán này có yêu cầu rõ ràng nào mà Repository và Template của phiên bản đang dùng chưa biểu đạt đúng, hoặc chỉ có thể thực hiện với chi phí/độ phức tạp không phù hợp?**

Nếu câu trả lời có bằng chứng, **dùng SDK trực tiếp trong một adapter được khoanh vùng** là lựa chọn hợp lý. Nếu không, đi thẳng xuống SDK có thể khiến dự án tự gánh những việc mà Spring Data đã làm giúp: mapping, định danh document, optimistic locking, auditing, type discriminator, lifecycle và quy ước truy cập.

Bài thuộc chương **Mở rộng bằng SDK**, trong bối cảnh xây dựng tầng truy cập Couchbase với document mapping, bucket/scope/collection, SQL++, TTL, CAS, chỉ mục, giao dịch và reactive API. Mục tiêu là hiểu **khi nào nên hạ tầng trừu tượng**, làm thế nào để hạ đúng phạm vi và không tạo hai cách ghi dữ liệu mâu thuẫn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt trách nhiệm và phạm vi của Repository, `CouchbaseTemplate`, `ReactiveCouchbaseTemplate` và Java SDK.
2. Đặt tiêu chí đo được để quyết định lúc nào một tính năng cần SDK trực tiếp.
3. Nhận diện những trường hợp SDK mang lại lợi ích rõ: **KV/sub-document**, thao tác CAS đặc biệt, tùy chọn truy vấn SQL++ hoặc điều khiển request chưa được abstraction hiện tại hỗ trợ tương đương.
4. Tránh kết luận sai rằng Repository/Template không hỗ trợ durability, scan consistency, projection hay truy vấn tùy chỉnh.
5. Viết một adapter SDK cho nghiệp vụ cụ thể, có input/output theo domain thay vì làm lộ `Cluster`/`Collection` khắp codebase.
6. Bảo toàn document key, type discriminator, JSON field mapping, TTL, CAS và quy tắc authorization khi trộn Spring Data với SDK.
7. Tách truy vấn KV theo key khỏi SQL++ qua Query Service và thiết kế index tương ứng.
8. Xử lý concurrency, timeout, retry, durability, reactive và transaction theo hợp đồng nghiệp vụ.
9. Lập test so sánh hai đường truy cập và thu thập bằng chứng hiệu năng trước/sau khi chuyển sang SDK.

## 2. Sơ đồ các lớp truy cập

~~~text
HTTP / Scheduler / Consumer
            |
      Application service
            |
     Domain port / contract
       /         |         \\
Repository   CouchbaseTemplate   SDK adapter
       \\        |             /
         Spring Data / SDK
                  |
         Couchbase Java SDK
             /           \\
           KV          Query
             \\           /
             Couchbase Server
~~~

Sơ đồ diễn tả **lựa chọn đường vào**. Repository và Template cuối cùng dựa vào hạ tầng SDK, nhưng có thêm quy tắc mapping và tổ chức code. SDK adapter là một lối đi có chủ đích khi yêu cầu vượt khả năng/độ linh hoạt của hai lớp trên.

| Đường truy cập | Mạnh ở điểm nào | Khi nào nên ưu tiên |
| --- | --- | --- |
| **Repository** | CRUD hướng domain, query derivation, phân trang/sort, tích hợp converter | Luồng đọc/ghi entity phổ biến |
| **`CouchbaseTemplate`** | Fluent operations, truy vấn và tùy chọn linh hoạt hơn, vẫn gắn mapping entity | Repository quá cao cấp nhưng vẫn muốn quy ước Spring Data |
| **`ReactiveCouchbaseTemplate`** | Tương tự Template trên đường reactive mà phiên bản hỗ trợ | WebFlux và domain mapping cần non-blocking |
| **Java SDK – KV API** | `get/insert/replace/remove`, CAS, expiry, sub-document, durability và tùy chọn request cụ thể | Truy cập theo document key hoặc thao tác đặc thù |
| **Java SDK – SQL++** | Toàn quyền văn bản query, tham số, query options và mapping result row | Query có shape/plan/tùy chọn không diễn đạt tốt trong abstraction |
| **Java SDK – transactions** | Kiểm soát transaction SDK theo phạm vi hỗ trợ | Cần ngữ nghĩa transaction cụ thể, đã kiểm tra khả năng Spring integration |

**Không coi bảng là danh sách tính năng độc quyền.** Nhiều tùy chọn SDK có thể đã được Template hoặc Repository cung cấp ở phiên bản đang dùng. Quy tắc chọn là **kiểm tra khả năng hiện có trước**, rồi mới hạ xuống một lớp thấp hơn.

## 3. Thang quyết định: bắt đầu từ yêu cầu, không từ tên API

Đối với mỗi use case, đi qua lần lượt các câu hỏi:

1. **Có đang thao tác một entity theo key hoặc filter đơn giản không?** Nếu có, thử Repository.
2. **Có cần query, consistency, durability hoặc lựa chọn scope/collection linh hoạt hơn không?** Kiểm tra Template và cấu hình Spring Data.
3. **Cần KV/sub-document hoặc một SDK operation/request option chưa có đường tương đương phù hợp?** Thử Java SDK cho đúng thao tác đó.
4. **Có yêu cầu hiệu năng cụ thể?** Đo trước và sau trên cùng workload, tránh đoán SDK luôn nhanh.
5. **Có làm bypass các ràng buộc domain/mapping không?** Nếu có, bổ sung adapter bảo vệ và integration test.
6. **Có thể thu hẹp SDK vào một method không?** Nếu có, tránh di chuyển cả module sang SDK chỉ vì một thao tác đặc biệt.

Quyết định dễ xem xét ở code review khi có ba thứ: **yêu cầu**, **bằng chứng abstraction chưa đáp ứng**, **cách kiểm chứng thay thế**.

### Bảng quyết định nhanh

| Tình huống | Bắt đầu từ đâu? | Khi nào SDK trực tiếp hợp lý? |
| --- | --- | --- |
| CRUD một entity theo `@Id` | Repository | Khi cần KV option cụ thể mà đường hiện tại không đủ |
| Chọn collection hoặc tùy chỉnh fluent query | Template | Khi API/return shape không bao quát được |
| Truy vấn SQL++ có projection/DTO riêng | Repository `@Query` hoặc Template | Nếu mapping, tùy chọn hoặc clause sinh tự động gây giới hạn thực sự |
| Chỉ đọc vài nested fields của một document đã biết key | Xem khả năng Template | `lookupIn` cần thiết và giúp tránh tải cả document |
| Cập nhật một path hoặc tăng counter nguyên tử | Xem khả năng Template | `mutateIn`/KV counter phù hợp hơn read–modify–replace |
| Conditional replace theo CAS | Repository `@Version` hoặc Template | Muốn xử lý CAS thô/tùy chọn ở mức SDK |
| Expiry/TTL/durability riêng theo request | Kiểm tra annotation/Template | Khi cần mức chi tiết đường hiện tại chưa hỗ trợ |
| Query SQL++ cần profile, scan consistency, params chuyên biệt | Template/`@Query` | Khi cần `QueryOptions` hoặc result shape khác biệt |
| Giao dịch nhiều document | Kiểm tra transaction integration/khả năng dự án | Khi cần SDK transaction API cụ thể đã xác minh |
| Reactive truy cập KV/query | Reactive Repository/Template | Khi cần reactive SDK operation riêng, không block |

## 4. Đặt “chưa đáp ứng” thành tiêu chí kiểm chứng được

Cụm “Repository chưa đáp ứng” quá mơ hồ. Một quyết định tốt nên có bằng chứng như:

- **Thiếu operation:** use case đòi `mutateIn` để thay một nested path mà abstraction đang sử dụng không có phương thức tương đương đáng tin cậy.
- **Sai shape:** một query thống kê trả scalar hoặc JSON lồng nhau, converter repository hiện tại không map được đúng hợp đồng.
- **Không kiểm soát được request option:** nghiệp vụ cần một lựa chọn SDK cụ thể trên từng request và Template/Repository của phiên bản khóa không expose đúng lựa chọn đó.
- **Không thể biểu đạt predicate/query plan:** query phải dùng biểu thức `META()`, hint hoặc câu SQL++ tùy chỉnh; đường repository sinh clause ngoài ý muốn.
- **Yêu cầu resource:** chỉ cần hai field trong JSON document lớn, đo được KV sub-document giảm payload/latency hơn so với đọc full entity.
- **Vòng đời bất đồng bộ:** ứng dụng cần tổ hợp operation/reactive stream nhất định mà adapter hiện tại không cung cấp, không thể chấp nhận gọi blocking.
- **Độ đúng:** hai thao tác đọc–sửa–ghi thông thường có thể làm lost update; SDK có lệnh atomic phù hợp.

Ngược lại, những lý do sau **chưa đủ**:

- “SDK trông thấp tầng nên chắc nhanh hơn.”
- “Dùng `Cluster.query(...)` sẽ không cần index.”
- “Template không hỗ trợ query phức tạp” khi chưa thử `@Query`/fluent query.
- “Repository không hỗ trợ CAS/TTL” khi chưa kiểm tra `@Version`, cấu hình entity và Template.
- “Chuyển sang reactive SDK là có transaction hoặc snapshot.”
- “SDK giúp bỏ hết trách nhiệm ánh xạ document.”

Một spike nhỏ có **test đúng/sai, query plan, latency và chi phí vận hành** thường thuyết phục hơn tranh luận về sở thích API.

## 5. Repository vẫn là mặc định tốt cho entity CRUD

Entity Couchbase minh họa:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String fullName;
    private boolean active;

    // Constructor/getter/setter theo quy tắc mapping.
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    Page<Customer> findByActiveTrue(Pageable pageable);
}
~~~

Service:

~~~java
public Customer findRequired(String id) {
    return customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
~~~

`CustomerNotFoundException` là exception của ứng dụng. Ở đây ta không cần truy cập trực tiếp `Collection.get(...)` chỉ để đọc một entity bằng key.

**Lưu ý:** `@Version` gắn với optimistic locking theo semantics Spring Data. Đừng tự đồng nhất field Java `version` với một field JSON số nguyên “version” do SDK tự ghi; converter có thể dùng metadata CAS và không lưu phiên bản theo cách bạn đoán. Cần kiểm tra cơ chế mapping trên phiên bản đang dùng.

## 6. Template là bước trung gian quan trọng

`CouchbaseTemplate` không phải một Repository tên khác. Nó cho phép sử dụng fluent operations và kiểm soát cụ thể hơn, trong khi vẫn giữ converter và các quy tắc của Spring Data.

Ví dụ minh họa theo API Template thông dụng:

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public Customer loadById(
        CouchbaseTemplate template,
        String documentId) {

    return template.findById(Customer.class)
            .one(documentId);
}
~~~

Lưu entity:

~~~java
Customer saved = template
        .upsertById(Customer.class)
        .one(customer);
~~~

Template ở những phiên bản Spring Data Couchbase nhất định có thể cấu hình **durability** và **scan consistency** trực tiếp qua fluent operation. Ví dụ, khi bản dùng hỗ trợ:

~~~java
Customer saved = template.upsertById(Customer.class)
        .withDurability(DurabilityLevel.MAJORITY)
        .one(customer);
~~~

Đừng coi durability là lý do tự động phải dùng SDK. Tương tự, query có scan consistency cụ thể có thể đã diễn đạt được bằng API Template.

**Điểm cần xác minh:** chữ ký của `withDurability(...)`, lựa chọn query, scope/collection resolution và mapping theo **version đã khóa**. Với một phiên bản khác, lựa chọn có thể khác hoặc nằm ở nơi khác.

### Vì sao Template có lợi so với SDK?

Khi dùng Template, ứng dụng vẫn tận dụng:

- Mapping `@Field` hoặc converter tùy chỉnh.
- Cách xác định `@Id` và document key.
- Cách xác định collection/scope từ entity/configuration.
- Type metadata khi nhiều entity chia sẻ collection.
- Chính sách optimistic locking/auditing tương ứng.
- Sự thống nhất giữa query path và write path.

Nếu chuyển sang SDK, hãy liệt kê những quy ước nào phải được **chủ động giữ lại**.

## 7. Trường hợp rõ ràng cho SDK: chỉ đọc một phần document bằng KV sub-document

Giả sử `customers` có document lớn:

~~~json
{
  "tenantId": "tenant-01",
  "fullName": "Trần Minh",
  "profile": {
    "displayName": "Minh",
    "city": "Hà Nội",
    "preferences": {
      "language": "vi",
      "notifications": true
    }
  },
  "orders": [
    {"id": "order::1"},
    {"id": "order::2"}
  ]
}
~~~

Endpoint chỉ cần `profile.displayName` của một **document đã biết key**. Đọc toàn entity bằng Repository là hợp lệ, nhưng có thể truyền thêm nhiều dữ liệu không cần thiết. SDK cung cấp `lookupIn`:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.LookupInResult;
import com.couchbase.client.java.kv.LookupInSpec;
import java.util.List;

public String findDisplayName(
        Collection collection,
        String documentId) {

    LookupInResult result = collection.lookupIn(
            documentId,
            List.of(LookupInSpec.get("profile.displayName")));

    return result.contentAs(0, String.class);
}
~~~

`lookupIn` là **KV sub-document operation**, không phải SQL++ `SELECT profile.displayName`. Nó có lợi khi biết key, chỉ cần một phần nhỏ JSON và đã đo được lợi ích của tải ít dữ liệu.

**Không dùng `lookupIn` để thay query tìm kiếm theo filter.** Nó cần document key. Nếu chưa biết key và phải lọc theo nhiều trường/index, dùng SQL++ hoặc phương án query phù hợp.

Khi đường SDK bỏ qua converter, đường JSON là **tên field đã lưu**. Nếu entity dùng `@Field("display_name")` cho property Java `displayName`, SDK không tự đổi chuỗi `"displayName"` thành `"display_name"`.

## 8. Sub-document mutation: một lệnh nguyên tử trong một document

Một use case khác là sửa riêng `profile.displayName`. Có thể dùng `mutateIn`:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.MutateInSpec;
import java.util.List;

public void renameDisplayName(
        Collection collection,
        String id,
        String newDisplayName) {

    collection.mutateIn(
            id,
            List.of(MutateInSpec.upsert(
                    "profile.displayName",
                    newDisplayName)));
}
~~~

`mutateIn` thực hiện thay đổi path mà không yêu cầu ứng dụng đọc và ghi lại toàn bộ body. Nhiều mutate specs trong **cùng một lệnh** được thực thi nguyên tử ở mức **một document**: nếu một mutation không thể thực hiện, cả lệnh không thực hiện thay đổi từng phần như một chuỗi replace độc lập.

Tuy nhiên:

- Tính nguyên tử **một document** không biến `mutateIn` thành transaction nhiều document.
- `upsert("profile.displayName", ...)` vẫn cần đường dẫn cha hợp lệ, trừ khi sử dụng tùy chọn tạo path theo SDK.
- Một path bị viết sai có thể tạo trường mới ngoài schema nghiệp vụ; validate đường dẫn và payload.
- Nếu use case đòi tránh ghi đè khi document đã được người khác sửa, cân nhắc CAS.
- Ghi trực tiếp bằng SDK không tự phát các lifecycle callbacks/auditing của Spring Data theo đúng cách `save(...)` có thể thực hiện.

### CAS với sub-document

~~~java
import com.couchbase.client.java.kv.GetResult;
import static com.couchbase.client.java.kv.MutateInOptions.mutateInOptions;

GetResult current = collection.get(id);

collection.mutateIn(
        id,
        List.of(MutateInSpec.upsert(
                "profile.displayName", newDisplayName)),
        mutateInOptions().cas(current.cas()));
~~~

Nếu CAS không còn khớp lúc mutation, server trả lỗi cạnh tranh thay vì ghi đè phiên bản mới. Cần map lỗi CAS mismatch sang exception/domain conflict phù hợp và chỉ retry khi quy tắc nghiệp vụ cho phép.

**Chú ý:** các thao tác sub-document như append/increment có thể tự bảo đảm tính nguyên tử mà không cần CAS vòng đọc trước; thêm CAS một cách máy móc có thể làm tăng xung đột. Chọn CAS theo yêu cầu “chỉ sửa nếu document vẫn như lần đọc”, không phải theo thói quen.

## 9. SDK KV và SQL++ là hai đường khác nhau

Nếu đã biết document key:

~~~java
GetResult result = collection.get("customer::42");
~~~

Đây là KV get. Không cần query qua index chỉ để tìm một document theo key. Repository `findById(...)` cũng thường giải quyết bài toán này ở mức abstraction cao.

Khi cần tìm “toàn bộ khách hàng active của tenant X”:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
ORDER BY c.fullName ASC, META(c).id ASC
LIMIT $limit;
~~~

Đây là query SQL++ phục vụ bộ lọc/thứ tự, thường phụ thuộc vào secondary index thích hợp. Viết nó bằng `Cluster.query(...)` trong SDK **không tránh được Query Service, index hoặc chi phí SQL++**.

### Khi nào dùng SDK query?

- Cần SQL++ tường minh với `META(c).id`, `LET`, `JOIN`, `UNNEST`, `GROUP BY` hoặc shape result tùy chỉnh mà repository mapping chưa phù hợp.
- Cần các query options/tùy chọn profiling, timeout, scan consistency, readonly hoặc context ID cụ thể theo phiên bản API.
- Repository `@Query` kết hợp `Pageable` sinh clause khiến query không còn đúng và cần tự kiểm soát toàn bộ `WHERE/ORDER BY/LIMIT`.
- Kết quả không phải entity, ví dụ scalar `COUNT` hoặc thống kê DTO, dễ map JSON trực tiếp hơn.

Tuy nhiên, **không mặc định** mọi query phức tạp cần SDK. `@Query` và Template có thể xử lý nhiều tình huống; cần xác minh với bản Spring Data đang dùng.

## 10. Ví dụ SDK SQL++ trả DTO, không ép sang entity

Bài toán: lấy khách hàng theo tenant, trả read model nhỏ với ID:

~~~java
public record CustomerCard(String id, String fullName) {}
~~~

Custom adapter:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import java.util.List;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public List<CustomerCard> listActiveCustomers(
        Cluster cluster,
        String tenantId,
        int limit) {

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("tenantId required");
    }
    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("Invalid limit");
    }

    String statement = """
        SELECT META(c).id AS id,
               c.fullName AS fullName
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.tenantId = $tenantId
          AND c.active = TRUE
        ORDER BY c.fullName ASC, META(c).id ASC
        LIMIT $limit
        """;

    JsonObject parameters = JsonObject.create()
            .put("tenantId", tenantId)
            .put("limit", limit);

    QueryResult result = cluster.query(
            statement,
            queryOptions().parameters(parameters));

    return result.rowsAsObject().stream()
            .map(row -> new CustomerCard(
                    row.getString("id"),
                    row.getString("fullName")))
            .toList();
}
~~~

Ở đây:

1. DTO không đại diện cho một entity có đầy đủ field và CAS.
2. `META(c).id AS id` là key của document; khác `c.id` trong body JSON.
3. Named parameters áp dụng cho **giá trị** tenant/limit. Định danh bucket/scope/collection hoặc cấu trúc `ORDER BY` phải đến từ cấu hình đáng tin cậy/allowlist, không nối trực tiếp input người dùng.
4. `ORDER BY` có khóa phân xử; nếu nhiều `fullName` trùng, thứ tự vẫn xác định trên một tập dữ liệu tĩnh.
5. Query phải dùng index và được đo bằng `EXPLAIN`/profiling, không giả định SDK tự tối ưu.
6. DTO là read model; **không** truyền nó cho Repository `save(...)` như thể là Customer đầy đủ.

## 11. Quy tắc ánh xạ không được tự biến mất khi dùng SDK

Một dự án thường có quy ước mapping:

~~~java
@Document
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    @Version
    private Long version;

    @Field("display_name")
    private String displayName;

    private String tenantId;
}
~~~

Khi Repository/Template lưu, converter có thể thêm hoặc xử lý:

- Metadata định danh và version/CAS.
- Tên field JSON theo `@Field`.
- Type discriminator hoặc trường metadata nhận diện loại entity.
- Custom conversions cho kiểu Java.
- Auditing/lifecycle callbacks theo cấu hình.
- Các quy tắc expiry/durability đã cấu hình.

Nếu code SDK tự ghi:

~~~java
JsonObject body = JsonObject.create()
        .put("displayName", "Minh")
        .put("tenantId", "tenant-01");

collection.upsert("customer::42", body);
~~~

thì có thể lưu field `displayName`, trong khi entity Spring Data kỳ vọng field JSON `display_name`. Hệ thống sẽ có **hai schema** cho cùng một collection.

Cần đặc biệt tránh:

- Ghi JSON thiếu type discriminator khi collection có nhiều loại document và Spring Data dựa vào discriminator để query/map.
- Ghi đè document đang có các field mà SDK adapter không đọc/không tạo.
- Bỏ qua logic auditing như `updatedAt` do Spring Data thường thiết lập.
- Bỏ mất TTL hoặc điều kiện CAS khi thay thế toàn body.
- Đọc một document bằng SDK rồi gọi Repository `save(...)` trên object chưa được converter khởi tạo đúng phiên bản.

**Hướng triển khai:** định nghĩa một **document contract** chung cho mọi writer, hoặc dùng converter chính thức của Spring Data nếu thật sự cần map entity qua đường SDK, với API converter đã được kiểm chứng. Đừng tự giả định Gson/Jackson/SDK JsonObject tương đương tất cả converter tùy chỉnh.

## 12. TTL, expiry và bảo tồn thời hạn document

Trong Couchbase, một document có thể có thời hạn sống. Với Spring Data, expiry có thể được cấu hình ở entity/operation tùy phiên bản; SDK cũng cung cấp các option trên KV mutation.

Ví dụ một document tạm được tạo bằng SDK:

~~~java
import java.time.Duration;
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

collection.insert(
        "token::123",
        JsonObject.create().put("purpose", "reset-password"),
        insertOptions().expiry(Duration.ofMinutes(15)));
~~~

Nếu ứng dụng có quy tắc “tự xóa sau 15 phút”, việc ghi bằng SDK phải **thực hiện chính sách expiry rõ ràng**, không nghĩ annotation từ một entity mà SDK không dùng sẽ tự áp dụng.

Khi thay thế/upsert document đã có TTL, cần kiểm tra:

- Mutation đó có giữ hay đặt lại expiry theo semantics server/SDK/operation không?
- Có tùy chọn bảo tồn expiry phù hợp không?
- Có `maxTTL` tại bucket/collection ảnh hưởng thời hạn hiệu lực không?
- Có yêu cầu không kéo dài tuổi thọ của token/session không?
- Có cần kiểm tra giá trị expiry sau mutation không?

**Đừng coi TTL là field JSON thông thường.** Nó là metadata/semantics lưu trữ. Chính sách “giữ nguyên expiry” và “đặt lại expiry” khác nhau về bảo mật và vận hành.

## 13. CAS: chọn optimistic locking đúng đường

Một luồng thao tác mức entity có thể dùng `@Version` và Repository save để phát hiện sửa cạnh tranh. Nếu cần SDK-level conditional mutation, SDK nhận CAS lấy từ kết quả KV.

~~~java
import com.couchbase.client.java.kv.GetResult;
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

GetResult current = collection.get("customer::42");

JsonObject body = current.contentAsObject();
body.put("fullName", "Tên đã sửa");

collection.replace(
        "customer::42",
        body,
        replaceOptions().cas(current.cas()));
~~~

Nếu document đã được writer khác thay đổi, thao tác `replace` sẽ thất bại do CAS mismatch. Mẫu này phòng tránh lost update của **một document**, với điều kiện ứng dụng xử lý lỗi đúng.

Cẩn trọng:

1. `replace(...)` là thay thế **toàn bộ body**, có thể ảnh hưởng schema/TTL/auditing nếu không bảo tồn đúng.
2. Không dùng CAS cũ sau một mutation thành công để cố ghi lần nữa.
3. Không tự retry CAS mismatch bằng cách đọc mới rồi ghi đè vô điều kiện; phải xem lại điều kiện nghiệp vụ.
4. CAS không phải timestamp sắp xếp toàn cục hay token snapshot của collection.
5. Nếu chỉ muốn thay một path, `mutateIn` có thể hợp lý hơn full-document replace.

### Idempotency khác CAS

CAS giúp tránh ghi lên phiên bản ngoài ý muốn; **idempotency** giúp xử lý an toàn khi request bị retry sau timeout hoặc kết quả bất định. Một mutation có thể đã được server commit nhưng ứng dụng không nhận response. Nếu tự gửi lại thao tác “tăng điểm 1” mà không có cơ chế idempotency, điểm có thể bị tăng hai lần.

Đặc biệt với counters, `arrayAppend`, thanh toán hoặc side effect, phải có chiến lược idempotency riêng khi nghiệp vụ yêu cầu.

## 14. Durability: không chỉ là “ghi thành công”

Java SDK hỗ trợ yêu cầu durability của KV mutation, ví dụ:

~~~java
import com.couchbase.client.java.durability.DurabilityLevel;
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

collection.upsert(
        "audit::abc",
        JsonObject.create().put("action", "CREATED"),
        upsertOptions().durability(DurabilityLevel.MAJORITY));
~~~

`DurabilityLevel.MAJORITY` yêu cầu mức xác nhận cao hơn mặc định theo ngữ nghĩa durable writes. Điều này **không** đồng nghĩa đã sao lưu offsite, giữ lịch sử bất biến hay không thể mất dữ liệu trong mọi kịch bản.

Trước khi hạ xuống SDK vì durability, hãy kiểm tra Template hoặc cấu hình Spring Data: các API Template trong những phiên bản có thể hỗ trợ `withDurability(...)`. Chỉ dùng SDK khi cần một tùy chọn/tổ hợp chưa được abstraction hiện hành thể hiện đúng.

Một số quyết định vận hành:

- Mức durability nào phù hợp từng loại dữ liệu?
- Latency/throughput bị ảnh hưởng đến đâu?
- Các replicas và cấu hình bucket có hỗ trợ mức yêu cầu không?
- Timeout sau mutation sẽ được phân loại và retry như thế nào?
- Có log/tracing để phân biệt mutation thành công, thất bại và trạng thái chưa chắc chắn không?

Không trả HTTP “thành công” trước khi biết mutation đã đạt **mức durability mà nghiệp vụ yêu cầu**, trừ khi API chủ đích có trạng thái accepted/processing riêng.

## 15. Scan consistency: KV read khác SQL++ query

Couchbase SQL++ thường dựa vào secondary index. Sau KV mutation, index có thể chưa cập nhật ngay, tùy scan consistency.

SDK cho phép cấu hình:

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

QueryResult result = cluster.query(
        statement,
        queryOptions()
            .parameters(parameters)
            .scanConsistency(QueryScanConsistency.REQUEST_PLUS));
~~~

- `NOT_BOUNDED`: có thể query thấy index state chưa bắt kịp mutation mới nhất.
- `REQUEST_PLUS`: query có thể chờ index phản ánh mutation đã hoàn tất tới thời điểm request theo semantics của Query Service, đổi lại latency có thể tăng.
- Một số đường query/API hỗ trợ yêu cầu nhất quán dựa trên mutation state/token cụ thể.

**Không kết luận rằng chỉ SDK có `REQUEST_PLUS`.** Template cũng có thể có cấu hình query consistency; kiểm tra API đúng phiên bản.

**Không kết luận `REQUEST_PLUS` là transaction hoặc snapshot qua nhiều request.** Nó không đảm bảo trang 1 và trang 2 đọc sau vài phút có cùng tập dữ liệu.

## 16. Batch, counter và các mutation đặc thù

SDK có những thao tác rất phù hợp khi đơn vị thay đổi là **một key** hoặc **một phần document**:

- KV counter tăng/giảm số đếm mà không thực hiện vòng read–modify–replace thủ công.
- `mutateIn` với `arrayAppend`, `arrayPrepend`, `insert`, `remove`, `upsert` và các thao tác path khác.
- Thực hiện nhiều sub-document mutations trong cùng một lệnh nguyên tử ở mức document.
- Các operation/option dành riêng cho expiry, durability, CAS hoặc replica reads khi thật sự cần.

Nhưng cần tránh hai giả định:

1. **Nhiều operation được gửi song song không thành một transaction đa document.** Atomic ở mức một `mutateIn` chỉ liên quan document của lệnh đó.
2. **Dùng arrayAppend cho một danh sách tăng mãi không giải quyết giới hạn kích thước document.** Cân nhắc mô hình một item/một document hoặc collection riêng nếu mảng có thể lớn vô hạn.

Nếu SDK cung cấp batch theo kiểu phát nhiều KV operations bất đồng bộ, đó thường là cách **tối ưu luồng gửi request**, không có nghĩa server sẽ commit mọi document cùng nhau. Cần giới hạn concurrency, xử lý lỗi từng item, checkpoint và retry/idempotency.

## 17. Giao dịch: SDK trực tiếp không phải “nâng cấp tự động”

Couchbase Java SDK có transaction API cho một số tổ hợp KV/SQL++ operations. Đây là lựa chọn khi nghiệp vụ cần nguyên tử nhiều thao tác theo semantics transaction được Couchbase hỗ trợ.

Tuy nhiên:

- Kiểm tra trước **Spring Data transaction integration** trên phiên bản thực tế; không giả định Repository/Template hoàn toàn không có transaction.
- SDK transaction context là **cơ chế riêng**, không được trộn một thao tác repository bên ngoài context vào giữa callback rồi tin rằng nó thuộc transaction.
- Không dùng DDL tùy ý như `CREATE INDEX` trong transaction nếu Server không hỗ trợ.
- Cần hiểu retry của transaction lambda: code có external side effect (gửi email, thanh toán, publish trực tiếp) không được mặc nhiên chạy đúng một lần.
- Không giữ transaction qua nhiều HTTP request để mô phỏng snapshot vô hạn.
- Kiểm tra lỗi ambiguous/expired transaction, timeout, durability và tính idempotent.

Nếu use case chỉ là “thay một field của một document”, một lệnh `mutateIn` nguyên tử hoặc `replace` kèm CAS có thể **đơn giản hơn transaction**.

### Gợi ý phân tích nghiệp vụ

Ví dụ “trừ tồn kho và tạo đơn hàng” liên quan nhiều document. Đừng chỉ thấy SDK có `transactions()` rồi triển khai ngay. Hãy xác định:

1. Đơn vị bất biến cần giữ là gì?
2. Các document ở đâu, có nằm trong phạm vi transaction hỗ trợ không?
3. Có side effect ngoài Couchbase không?
4. Retry/timeout sẽ ảnh hưởng idempotency ra sao?
5. Có giải pháp thiết kế domain khác giảm contention không?

Quyết định transaction phải gắn với **semantics**, không phải sở thích framework.

## 18. Reactive SDK: không block và không đánh đồng publisher với tối ưu query

Java SDK cung cấp đường reactive trên Cluster/Collection:

~~~java
import com.couchbase.client.java.ReactiveCluster;
import com.couchbase.client.java.json.JsonObject;
import reactor.core.publisher.Flux;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public Flux<CustomerCard> listActiveReactive(
        ReactiveCluster cluster,
        String tenantId,
        int limit) {

    String sql = """
        SELECT META(c).id AS id,
               c.fullName AS fullName
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.tenantId = $tenantId
          AND c.active = TRUE
        ORDER BY c.fullName ASC, META(c).id ASC
        LIMIT $limit
        """;

    JsonObject args = JsonObject.create()
            .put("tenantId", tenantId)
            .put("limit", limit);

    return cluster.query(sql, queryOptions().parameters(args))
            .flatMapMany(result -> result.rowsAsObject())
            .map(row -> new CustomerCard(
                    row.getString("id"),
                    row.getString("fullName")));
}
~~~

Dự án cần truyền `ReactiveCluster` từ kết nối SDK được quản lý, không tạo mới kết nối mỗi request.

Cần nhớ:

- `Flux` không tự tạo `Page` hoặc tổng số phần tử.
- `Flux.take(20)` ở Java không chắc đẩy `LIMIT 20` vào SQL++; giới hạn kết quả nên nằm ở query.
- `Flux.skip(100000)` không tương đương một kế hoạch phân trang server hiệu quả.
- `collectList()` trên query không giới hạn có nguy cơ giữ rất nhiều dữ liệu trong RAM.
- Không gọi `block()` trong event loop của WebFlux.
- Backpressure giúp luồng dữ liệu, không thay thế index, query plan hoặc giảm chi phí aggregation.

Nếu cần một SDK operation cụ thể nhưng vẫn muốn domain converter của Spring Data, thiết kế ranh giới adapter cẩn thận, tránh tự trộn blocking và reactive giữa các lớp.

## 19. Kiến trúc đề xuất: một SDK adapter nhỏ sau domain port

Không nên tiêm `Cluster` hoặc `Collection` vào mọi service nghiệp vụ. Tạo interface diễn đạt **ý định domain**:

~~~java
public interface CustomerProfilePort {
    String readDisplayName(String customerId);

    void changeDisplayName(
            String customerId,
            String newName,
            long expectedCas);
}
~~~

Adapter cho use case SDK:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.LookupInResult;
import com.couchbase.client.java.kv.LookupInSpec;
import com.couchbase.client.java.kv.MutateInSpec;
import java.util.List;

import static com.couchbase.client.java.kv.MutateInOptions.mutateInOptions;

public final class CouchbaseCustomerProfileAdapter
        implements CustomerProfilePort {

    private final Collection collection;

    public CouchbaseCustomerProfileAdapter(Cluster cluster) {
        this.collection = cluster.bucket("shop")
                .scope("crm")
                .collection("customers");
    }

    @Override
    public String readDisplayName(String customerId) {
        LookupInResult result = collection.lookupIn(
                customerId,
                List.of(LookupInSpec.get("profile.displayName")));

        return result.contentAs(0, String.class);
    }

    @Override
    public void changeDisplayName(
            String customerId,
            String newName,
            long expectedCas) {

        collection.mutateIn(
                customerId,
                List.of(MutateInSpec.upsert(
                        "profile.displayName", newName)),
                mutateInOptions().cas(expectedCas));
    }
}
~~~

Đây là **khung minh họa**: application layer cần xác thực tenant/quyền và chuyển `expectedCas` từ một lần đọc có CAS hợp lệ; `readDisplayName` hiện chỉ trả chuỗi nên **không cung cấp CAS**. Trong ứng dụng thật, nếu sửa theo optimistic locking, thay đổi hợp đồng đọc thành DTO chứa cả value và CAS.

Ưu điểm:

- Controller/service không biết API SDK.
- Đường truy cập đặc biệt được khoanh ở một adapter.
- Có thể thay implementation bằng Template khi phiên bản framework cải thiện.
- Unit test dễ mock port, integration test tập trung vào Couchbase.
- Error mapping, timeout, metrics, retry và security được triển khai thống nhất.

### Sửa hợp đồng để có CAS hợp lệ

~~~java
public record DisplayNameSnapshot(
        String value,
        long cas) {}

public interface CustomerProfilePort {
    DisplayNameSnapshot read(String customerId);

    void replaceName(
            String customerId,
            String name,
            long expectedCas);
}
~~~

Adapter có thể đọc CAS bằng KV `GetResult.cas()` hoặc metadata tương ứng của sub-document lookup theo SDK được sử dụng. **Không phát minh CAS ở phía client**, không suy ra CAS từ `updatedAt`, và không dùng token cũ sau mutation khác.

## 20. Spring configuration: sử dụng kết nối đã được quản lý

Spring Data Couchbase thường cấu hình một `Cluster`/hạ tầng kết nối SDK. Theo tài liệu Spring Data, có thể tiếp cận SDK trực tiếp qua các bean có sẵn trong cấu hình Couchbase.

Nguyên tắc lifecycle:

- Dùng `Cluster` được **dependency injection** từ cấu hình được quản lý.
- Không tạo `Cluster.connect(...)` trong mỗi repository method.
- Không đóng `Cluster` của ứng dụng sau mỗi request.
- Tái sử dụng `Bucket`/`Scope`/`Collection` handle phù hợp.
- Cấu hình timeout, TLS, credential, observability và connection management tập trung.
- Với multi-tenant nhiều bucket/collection, dùng registry/config được kiểm soát thay vì lấy tên collection trực tiếp từ URL người dùng.

Ví dụ constructor injection:

~~~java
import com.couchbase.client.java.Cluster;
import org.springframework.stereotype.Component;

@Component
public final class SdkCustomerGateway {
    private final Cluster cluster;

    public SdkCustomerGateway(Cluster cluster) {
        this.cluster = cluster;
    }

    // Các method dùng cluster/collection đã có.
}
~~~

Việc bean `Cluster` sẵn có, scope và cách expose phụ thuộc **Spring Boot/Spring Data Couchbase configuration** của dự án. Nếu cấu hình hiện tại không expose đúng bean, cần tạo integration configuration một cách nhất quán, không dựng kết nối thứ hai không kiểm soát chỉ để né DI.

## 21. Authorization và multi-tenancy: SDK không tự lọc hộ

Đây là rủi ro lớn nhất khi viết SDK SQL++ tường minh.

Một Repository có thể có query method thường xuyên gắn type filter hoặc logic service. Khi code chuyển thành SDK:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Nếu thiếu `tenantId`, SDK có thể trả khách hàng của tenant khác.

Cần đảm bảo:

1. Lấy tenant từ **context xác thực**, không tin `tenantId` do client tự nhập.
2. Mọi query, kể cả `COUNT`/`EXPLAIN` trong công cụ nội bộ, phải tuân thủ phạm vi tenant/quyền khi dùng dữ liệu thật.
3. Nếu collection lưu nhiều loại document, bổ sung type predicate đúng với dữ liệu lưu; không trông chờ `#{#n1ql.filter}` của Spring Data tự áp dụng cho raw SDK SQL++.
4. KV operation dựa trên key cũng cần kiểm tra quyền truy cập. Biết document key **không đồng nghĩa được phép đọc nó**.
5. Nếu key encode tenant, phải kiểm tra quy tắc key/tenant và quyền; không chỉ tin prefix do người dùng gửi.
6. Không cho phép client ghép trực tiếp tên bucket, scope, collection, field sort hay SQL++ expression tùy ý.
7. Audit ai thực hiện mutation, trên tenant nào, với tài nguyên nào và có thành công không.

Bind parameter giúp tránh việc biến **giá trị** thành cú pháp query, nhưng **không thay thế authorization** và không bind được mọi thành phần định danh/cấu trúc SQL++.

## 22. Lỗi, timeout và retry phải có chính sách

SDK đưa nhiều tình huống lỗi lên gần ứng dụng hơn:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Not found | `get`/`lookupIn` trên key không tồn tại | Map sang domain not-found, cân nhắc không tiết lộ existence |
| Path error | Sub-document path không hợp lệ/không tồn tại | Map sang validation hoặc data corruption theo ngữ cảnh |
| CAS mismatch | `replace/mutateIn` có expected CAS cũ | Trả conflict hoặc đọc lại/merge theo nghiệp vụ |
| Timeout | Server đã xử lý hay chưa có thể không chắc chắn | Không retry mù cho mutation không idempotent |
| Durability ambiguity | Mutation có thể đã đạt trạng thái nào đó | Có chính sách kiểm tra/đối soát |
| Mapping | Trường JSON thiếu hoặc sai kiểu | Validate/migrate, không lặng lẽ trả DTO sai |
| Query/index | Không có index/query lỗi | Quan sát `EXPLAIN`, deploy index và rollback phù hợp |
| Permission | Thiếu RBAC hay sai tenant | Chặn truy cập, audit, không fallback sang quyền rộng |

**Không dùng** `catch (Exception) { return null; }` cho mọi lỗi. Lỗi query, thiếu document hợp lệ và lỗi quyền cần phân biệt.

### Retry

- KV `get` là read, có thể retry có giới hạn theo SDK/chính sách.
- Conditional mutation có CAS phải xử lý xung đột theo quy tắc domain.
- Counter increment/append có side effect; retry sau timeout có thể lặp tác động.
- Transaction SDK có retry behavior riêng; callback không nên thực hiện side effect ngoài transaction mà không có outbox/idempotency.
- Đặt timeout có ý nghĩa và quan sát operation/client context IDs phục vụ tracing.

Thực tế vẫn cần kiểm chứng phiên bản SDK cụ thể để phân loại lỗi ambiguous/unambiguous và retryability, không tự thiết kế một vòng retry vô hạn bên ngoài SDK.

## 23. Hiệu năng: đo đúng trước khi kết luận SDK tốt hơn

Một câu so sánh công bằng cần cùng ngữ nghĩa:

| Phép so sánh | Cần giữ tương đương |
| --- | --- |
| Repository `findById` với SDK `get` | Cùng key, dữ liệu, serialization/mapping, consistency |
| Entity full-document với SDK `lookupIn` | Cùng nhu cầu trường cần đọc; phân biệt payload có chủ đích |
| Template SQL++ với SDK `query` | Cùng SQL++, index, scan consistency, params, projection |
| Entity replace với `mutateIn` | Cùng bất biến nghiệp vụ, CAS, TTL và auditing |
| Blocking với reactive | Cùng concurrency, thread pool, workload và server resource |

Đo:

- p50, p95, p99 latency tại client.
- Số request Couchbase và request per second.
- Payload bytes và kích thước document.
- CPU/heap/GC của ứng dụng.
- Index entries scanned, Fetch, Order và query duration của SQL++.
- Tỉ lệ CAS conflicts, timeouts, retries, ambiguous results.
- Chi phí converter/mapping nếu thực sự đáng kể.
- Độ đúng của dữ liệu và tính nhất quán sau mutation.

**Cùng API nhưng khác ngữ nghĩa không phải benchmark công bằng.** Ví dụ SDK `lookupIn` chỉ trả một field nhanh hơn Repository `findById` đọc full entity là lợi ích có thể có của **đọc ít dữ liệu hơn**, không chứng minh toàn bộ SDK luôn nhanh hơn.

## 24. Thiết kế index khi viết SQL++ trực tiếp

SDK query vẫn dùng SQL++ và yêu cầu index phù hợp:

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = "tenant-01"
  AND c.active = TRUE
ORDER BY c.fullName ASC, META(c).id ASC
LIMIT 20;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_customers_tenant_active_name
ON `shop`.`crm`.`customers` (
    tenantId,
    active,
    fullName
);
~~~

Index này cần được **kiểm chứng bằng `EXPLAIN`**; không mặc nhiên cover mọi field, hỗ trợ đầy đủ thứ tự `META(c).id` hay đạt pagination pushdown. Khi có `JOIN`, `UNNEST`, `GROUP BY`, các operator có thể phát sinh `Fetch`/`Order` và intermediate rows lớn.

Hỏi:

1. Predicate tenant/active có được scan/index hỗ trợ không?
2. Query có cần Fetch body cho projection không?
3. Sort có được index hỗ trợ hay Query Service phải sắp lại?
4. LIMIT/OFFSET có được pushdown khi phù hợp không?
5. Số index entries scanned là bao nhiêu so với row trả?
6. Query có yêu cầu consistency làm tăng latency không?
7. Chỉ mục mới có làm tăng write amplification ngoài dự kiến không?

Đừng dùng SDK chỉ để “né” một index cần thiết: SQL++ query path không mất yêu cầu đó.

## 25. Checklist trước khi phê duyệt SDK adapter

### Quyết định kỹ thuật

- [ ] Nêu rõ use case và đơn vị truy cập: document key, nested path, query result hay transaction.
- [ ] Có bằng chứng Repository chưa đủ: API/test/behavior hoặc giới hạn phiên bản.
- [ ] Đã thử Template hoặc giải pháp Spring Data phù hợp.
- [ ] Nếu lý do là hiệu năng, có benchmark trước/sau cùng semantics.
- [ ] Chỉ dùng SDK ở phạm vi nhỏ nhất, không lan `Cluster`/`Collection` vào domain.
- [ ] Có kế hoạch quay lại abstraction cao hơn khi hỗ trợ thay đổi.

### Độ đúng và dữ liệu

- [ ] Schema body, `@Field`, converter và discriminator khớp các writer khác.
- [ ] Document key, scope, collection và tenant được xác định an toàn.
- [ ] Không bỏ quy tắc CAS/`@Version` khi ghi cạnh tranh.
- [ ] TTL/expiry được đặt hoặc bảo tồn đúng theo nghiệp vụ.
- [ ] Durability và consistency được chọn có căn cứ.
- [ ] Các mutation có side effect có chính sách retry/idempotency.
- [ ] Không dùng result projection thiếu field để thay thế toàn body.

### Vận hành

- [ ] SDK `Cluster` được DI/quản lý lifecycle tập trung.
- [ ] Không block event loop trong đường reactive.
- [ ] Có timeout, error mapping, metrics, tracing, log không lộ PII.
- [ ] Có `EXPLAIN`/profiling cho SQL++ quan trọng.
- [ ] Có integration test trên phiên bản Couchbase Server/Java SDK/Spring Data được khóa.
- [ ] Có test cạnh tranh writer, quyền tenant, document hết hạn TTL và retry.
- [ ] Có tài liệu owner/đường nâng cấp để không tạo SDK wrapper vô hạn.

## 26. Các bài test bắt buộc khi trộn Repository và SDK

Một bộ integration test hữu ích cần chạy trên Couchbase thật, không chỉ mock SDK.

### Test A — Cùng một document qua hai đường

1. Repository lưu entity Customer có `@Id`, `@Version`, `@Field("display_name")`.
2. SDK `get` xác minh body thực tế có khóa `display_name` đúng.
3. SDK `lookupIn` đọc nested path cần thiết.
4. SDK `mutateIn` cập nhật một trường nghiệp vụ.
5. Repository đọc lại entity, xác minh converter hiểu đúng field mới.
6. Repository sửa document và SDK `get` lại xác minh body/metadata.

Nếu hai đường tạo schema khác nhau, adapter không được coi là hoàn thành chỉ vì mỗi đường hoạt động độc lập.

### Test B — CAS conflict

~~~text
Given  KV get đọc CAS=A
When   writer khác mutate document -> CAS=B
And    adapter replace/mutateIn với expected CAS=A
Then   nhận conflict, không âm thầm ghi đè
~~~

Thử thêm trường hợp retry sau conflict theo quy tắc domain; nếu merge không hợp lệ, service phải trả conflict thay vì “last write wins” ngoài ý muốn.

### Test C — TTL

~~~text
Given  document có expiry theo chính sách
When   SDK adapter cập nhật hoặc replace
Then   expiry vẫn đúng chính sách đã chọn
And    document hết hạn theo thời gian mong muốn
~~~

Không chỉ kiểm tra field body; TTL là thuộc tính vòng đời.

### Test D — Auth/multi-tenancy

- Một user tenant A không thể lấy KV document tenant B chỉ nhờ biết key.
- Raw SQL++ SDK áp dụng đúng `tenantId` và type discriminator.
- Count/aggregate query cũng không tính nhầm tenant khác.
- Tên collection/field từ request không được ghép thành cú pháp SQL++ tùy ý.

### Test E — Tải và khả năng phục hồi

- So sánh full entity read với sub-document read trên document lớn.
- Đo độ trễ request khi dùng durability khác nhau.
- Simulate timeout/retry, xác minh counter/append không bị lặp tác động ngoài chính sách.
- Với reactive SDK, test không `block()` và giới hạn concurrency.
- Với SQL++, so sánh `EXPLAIN` và số index entries trước/sau điều chỉnh query/index.

## 27. Bài tập thực hành

Thiết kế một module danh sách khách hàng và hồ sơ khách hàng với hai use case:

**Use case 1 — CRUD chuẩn**

~~~text
createCustomer(customer)
findCustomerById(id)
findActiveCustomers(pageable)
~~~

Yêu cầu: dùng Repository/Template, giữ entity mapping, validation và phân trang đúng. Không tự viết SDK adapter chỉ để lặp lại CRUD thông thường.

**Use case 2 — Sửa một trường hồ sơ lớn**

~~~text
changeDisplayName(customerId, expectedCas, newDisplayName)
~~~

Yêu cầu:

1. Đề xuất vì sao `mutateIn` có thể phù hợp hơn đọc–sửa–replace toàn document.
2. Xây domain port và SDK adapter riêng cho thao tác này.
3. Đọc CAS thật từ KV; dùng CAS condition khi yêu cầu optimistic locking.
4. Bảo đảm field path phù hợp schema và parent path tồn tại.
5. Xác minh tenant/quyền truy cập trước mutation.
6. Có kiểm thử writer cạnh tranh và lỗi path.
7. Kiểm tra TTL trước/sau mutation.
8. So sánh latency, network payload và semantics với phiên bản Template.
9. Chứng minh Repository có thể đọc lại document vừa sửa bằng SDK.
10. Viết ngắn **Architecture Decision Record (ADR)**: vấn đề, các lựa chọn, bằng chứng, tradeoff, kế hoạch rollback.

**Use case 3 — SQL++ báo cáo tùy chỉnh**

Tạo một query trả DTO `CustomerCard` hoặc thống kê theo tenant. Thử `@Query`/Template trước; chỉ viết SDK `Cluster.query(...)` khi chứng minh đường abstraction hiện có không đáp ứng shape hoặc options yêu cầu. Chọn scan consistency, bind parameters và đọc `EXPLAIN`.

### Câu hỏi tự kiểm tra

1. Vì sao không nên lấy “SDK thấp tầng hơn” làm bằng chứng hiệu năng?
2. Repository và Template khác nhau ở mức kiểm soát và mapping như thế nào?
3. Có phải durability và `REQUEST_PLUS` là tính năng chỉ SDK có? Vì sao?
4. `lookupIn` khác SQL++ projection khi đã biết document ID ở điểm nào?
5. Khi dùng `mutateIn` cho hai path cùng document, tính nguyên tử có phạm vi nào?
6. Khi nào nên truyền CAS vào `mutateIn`, khi nào lệnh atomic có thể đủ?
7. Nếu SDK ghi field `displayName` nhưng entity Spring Data dùng `@Field("display_name")`, chuyện gì xảy ra?
8. Vì sao `collection.upsert` bằng JSON thô không tự áp dụng annotation TTL/auditing từ entity?
9. Tại sao biết document key chưa đủ để có quyền KV get?
10. Có `Cluster.query(...)` thì có bỏ được secondary index không?
11. Vì sao retry counter increment sau timeout có thể nguy hiểm?
12. Trộn operation Repository ngoài SDK transaction callback sẽ có rủi ro gì?
13. Khi nào cần snapshot/export riêng thay vì chỉ tăng scan consistency?
14. Một SDK adapter tốt nên expose `Collection` hay domain method? Vì sao?
15. Những bằng chứng nào cần có trước khi merge một thay đổi chuyển từ Template sang SDK?

## 28. Tài liệu chính thức

- [Spring Data Couchbase — Template & direct operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): Template là lớp thấp hơn Repository, fluent operations, durability/consistency và khả năng tiếp cận SDK.
- [Spring Data Couchbase — Couchbase Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): repository methods, `@Query`, entity mapping và phân trang.
- [Spring Data Couchbase — Object Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Id`, field mapping, metadata và converter.
- [Couchbase Java SDK — KV Data Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `get`, `insert`, `replace`, `upsert`, CAS, expiry và durability.
- [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): `lookupIn`, `mutateIn`, CAS, nguyên tử một document và thao tác path.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): query parameters, `QueryOptions`, scan consistency và result rows.
- [Couchbase Java SDK — Transactions](https://docs.couchbase.com/java-sdk/current/concept-docs/transactions.html): SDK transaction semantics và giới hạn.
- [Couchbase Java SDK — Reactive APIs](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-async-apis.html): blocking/async/reactive và threading.
- [Couchbase Server — EXPLAIN](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/explain.html): phân tích query plan của SQL++.

**Đối chiếu phiên bản:** Spring Data Couchbase, Spring Boot, Couchbase Java SDK và Couchbase Server có thể thêm/bớt khả năng hoặc đổi API. Khi quyết định “Template chưa đáp ứng”, phải gắn nhận định với **phiên bản đã khóa, yêu cầu thực tế và một bài test chứng minh**. Bài viết không mặc định mọi chức năng SDK nêu trên đều thiếu ở Repository/Template.

> **Ghi nhớ:** Dùng **Repository** để diễn đạt thao tác entity phổ biến, dùng **Template** khi cần linh hoạt hơn mà vẫn giữ mapping Spring Data, và dùng **Java SDK trực tiếp có chủ đích** khi cần operation/option/query shape cụ thể mà hai lớp trên chưa đáp ứng phù hợp. SDK không miễn trách nhiệm mapping, TTL, CAS, quyền tenant, consistency, retry và vận hành; hãy đóng gói nó sau một domain port và kiểm chứng bằng integration test.
