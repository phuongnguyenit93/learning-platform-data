# Lọc quyền truy cập và điều kiện nghiệp vụ trong truy vấn vector

Vector search tìm các document có embedding gần với query vector. Tuy nhiên, document gần nhất về mặt ngữ nghĩa chưa chắc là document người dùng được phép xem hoặc document đáp ứng điều kiện nghiệp vụ. Một kết quả chỉ hợp lệ khi đồng thời thỏa quyền truy cập, phạm vi tenant và các điều kiện như trạng thái publish, category, thời hạn hoặc giá.

Trong Elasticsearch, các điều kiện này được biểu diễn bằng query filter. Với kNN search, vị trí đặt filter rất quan trọng: filter nằm bên trong kNN clause là pre-filter, được áp dụng trong quá trình tìm vector; filter đặt bên ngoài có thể trở thành post-filter, chỉ loại kết quả sau khi kNN đã chọn candidate. Post-filter có thể làm response ít hơn k kết quả dù vẫn còn document phù hợp trong index.

Bài học này trình bày cách thiết kế field phục vụ ACL và business filters, cách tạo truy vấn vector có pre-filter trong Spring Data Elasticsearch, cách xử lý public/user/group access, cách kết hợp hybrid search, cách dùng Document-Level Security (DLS) như một lớp bảo vệ ở Elasticsearch, và cách kiểm thử để tránh lộ dữ liệu giữa người dùng hoặc tenant.

## 1. Vector similarity không phải quyền truy cập

Giả sử kho tri thức có các tài liệu:

- Tài liệu A thuộc tenant alpha, được chia sẻ cho nhóm engineering.
- Tài liệu B thuộc tenant beta, được đánh dấu public trong phạm vi tenant beta.
- Tài liệu C thuộc tenant alpha, chỉ chủ sở hữu được xem.
- Tài liệu D thuộc tenant alpha, đã hết hạn.

Người dùng thuộc tenant alpha, là thành viên nhóm engineering, tìm câu hỏi về cách cấu hình TLS. Vector của tài liệu A có thể gần query nhất. Tài liệu C cũng có thể rất gần về ngữ nghĩa, nhưng người dùng không có quyền xem. Tài liệu D có thể phù hợp nội dung nhưng không còn hiệu lực.

Kết quả hợp lệ phải thỏa tất cả điều kiện:

~~~text
Eligible document
    = correct tenant
    AND user is allowed to read
    AND business status is valid
    AND document is within effective dates
    AND vector is sufficiently relevant
~~~

Thứ tự logic rất quan trọng:

- Authorization xác định document nào người dùng được phép tiếp cận.
- Business filters xác định document nào phù hợp điều kiện của use case.
- Vector similarity xếp hạng các document còn đủ điều kiện.

Không dùng điểm similarity, boost hoặc reranking để biểu diễn quyền truy cập. Một document không có quyền phải bị loại khỏi tập kết quả, bất kể vector score cao đến đâu.

## 2. Phân biệt authorization và business filtering

Hai nhóm filter có mục tiêu khác nhau:

| Nhóm | Ví dụ | Nguồn dữ liệu |
|---|---|---|
| Authorization | tenantId, ownerId, ACL principal, group membership, visibility | Security context và policy của hệ thống |
| Business filter | status, category, price range, language, effectiveAt, stock status | Tham số use case và dữ liệu nghiệp vụ |
| Retrieval constraint | similarity threshold, candidate count, vector field | Cấu hình tìm kiếm |

Authorization trả lời “người dùng có được xem document này không?”. Business filter trả lời “document này có phù hợp với điều kiện tìm kiếm hiện tại không?”.

Ví dụ người dùng có thể được phép đọc toàn bộ tài liệu của tenant, nhưng request hiện tại chỉ muốn tài liệu đã publish thuộc category security. Category và status làm tập kết quả hẹp hơn; chúng không cấp thêm quyền.

### 2.1. Authorization phải được tạo từ server-side identity

Không lấy các giá trị sau trực tiếp từ query parameter hoặc JSON body rồi tin tưởng:

- tenantId được phép truy cập.
- userId dùng để kiểm tra ownership.
- groupIds hoặc roleIds.
- principal IDs trong ACL.
- danh sách field/permission cần bỏ qua.

Các giá trị này phải đến từ authenticated principal, token đã được xác minh hoặc authorization service đáng tin cậy. Client có thể gửi query text, category hoặc khoảng giá theo hợp đồng API; server tự bổ sung tenant và ACL scope.

Ví dụ không an toàn:

~~~http
GET /knowledge/search?q=tls&tenantId=tenant-beta&userId=user-admin
~~~

Nếu backend dùng hai tham số này trực tiếp trong query, người gọi có thể đổi tenant hoặc giả danh người khác.

Ví dụ an toàn hơn:

~~~java
SearchContext context = searchContextFactory.from(authentication);
return searchService.search(request.query(), request.filters(), context);
~~~

SearchContext được tạo từ authentication đã xác thực. Client không được tự quyết định principal IDs của chính mình.

## 3. Thiết kế document fields cho access control

Một document cần lưu đủ metadata để query có thể xác định phạm vi truy cập. Mapping minh họa:

~~~json
{
  "mappings": {
    "properties": {
      "tenantId": { "type": "keyword" },
      "ownerId": { "type": "keyword" },
      "visibility": { "type": "keyword" },
      "acl": {
        "properties": {
          "principalIds": { "type": "keyword" }
        }
      },
      "status": { "type": "keyword" },
      "category": { "type": "keyword" },
      "language": { "type": "keyword" },
      "price": { "type": "scaled_float", "scaling_factor": 100 },
      "effectiveAt": { "type": "date" },
      "expiresAt": { "type": "date" },
      "deleted": { "type": "boolean" },
      "embedding": {
        "type": "dense_vector",
        "dims": 768,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
~~~

Ý nghĩa:

- tenantId xác định ranh giới dữ liệu của tenant.
- ownerId lưu người sở hữu document.
- visibility biểu diễn phạm vi như PRIVATE hoặc PUBLIC.
- acl.principalIds chứa user/group/role principal được cấp quyền.
- status và category phục vụ điều kiện nghiệp vụ.
- effectiveAt và expiresAt xác định thời gian có hiệu lực.
- deleted giúp loại document đã xóa mềm.
- embedding phục vụ vector similarity.

Field dùng trong term/terms/range filter cần mapping phù hợp. ID, status, category, tenant và principal thường dùng keyword; ngày dùng date; giá dùng numeric; trạng thái xóa dùng boolean. Không dùng full-text analyzer cho ACL identifiers.

### 3.1. Dùng canonical principal IDs

Tránh lưu chuỗi tên hiển thị như “Engineering Team” hoặc email có thể đổi. Dùng ID ổn định và có namespace:

~~~text
user:8f3a
group:engineering
role:knowledge-reader
service:catalog-indexer
~~~

Document có thể chứa:

~~~json
{
  "tenantId": "tenant-alpha",
  "ownerId": "user:42",
  "visibility": "PRIVATE",
  "acl": {
    "principalIds": [
      "user:42",
      "group:engineering",
      "role:knowledge-reader"
    ]
  }
}
~~~

Người dùng đăng nhập có thể được cấp tập principal:

~~~text
user:42
group:engineering
group:platform
role:knowledge-reader
~~~

Query terms trên acl.principalIds sẽ match nếu ít nhất một principal của người dùng nằm trong danh sách ACL. Việc mở rộng group membership phải được thực hiện từ identity provider hoặc authorization service đáng tin cậy.

### 3.2. Mảng keyword đơn giản hay nested ACL object?

Nếu quyền chỉ là “principal này được đọc document”, mảng keyword thường đủ:

~~~json
{
  "acl": {
    "principalIds": ["user:42", "group:engineering"]
  }
}
~~~

Nếu mỗi grant có nhiều thuộc tính phải cùng khớp, ví dụ principal, permission và thời hạn, nên cân nhắc nested mapping:

~~~json
{
  "acl": {
    "grants": [
      {
        "principalId": "group:engineering",
        "permission": "READ",
        "expiresAt": "2027-01-01T00:00:00Z"
      },
      {
        "principalId": "user:42",
        "permission": "WRITE",
        "expiresAt": null
      }
    ]
  }
}
~~~

Mapping:

~~~json
{
  "acl.grants": {
    "type": "nested",
    "properties": {
      "principalId": { "type": "keyword" },
      "permission": { "type": "keyword" },
      "expiresAt": { "type": "date" }
    }
  }
}
~~~

Nếu dùng object array thường, Elasticsearch có thể flatten field values và match principal của grant thứ nhất với permission của grant thứ hai. Nested query giữ các điều kiện trong cùng một grant object.

Ví dụ nested ACL query:

~~~json
{
  "nested": {
    "path": "acl.grants",
    "query": {
      "bool": {
        "filter": [
          { "terms": { "acl.grants.principalId": ["user:42", "group:engineering"] } },
          { "term": { "acl.grants.permission": "READ" } }
        ]
      }
    }
  }
}
~~~

Nested mapping tốn thêm chi phí lưu trữ và query. Chỉ dùng khi quan hệ giữa các field trong từng grant cần được giữ chính xác.

## 4. Quy tắc ACL thường gặp

Một policy đơn giản có thể cho phép đọc khi:

- Document thuộc đúng tenant.
- Document đang public trong tenant đó; hoặc
- Người dùng là owner; hoặc
- Ít nhất một user/group/role principal của người dùng có quyền READ.

Biểu thức:

~~~text
tenant matches
AND (
    visibility = PUBLIC
    OR ownerId = currentUser
    OR acl.principalIds intersects currentPrincipals
)
~~~

Các điều kiện trong ngoặc là OR. Tenant là điều kiện AND bắt buộc bên ngoài. Vì vậy một document public của tenant khác vẫn không được trả về.

### 4.1. Public không nhất thiết có nghĩa public toàn hệ thống

Trong hệ thống multi-tenant, PUBLIC thường nên hiểu là “mọi người trong tenant này được đọc”. Khi đó vẫn giữ tenantId filter:

~~~text
tenantId = tenant-alpha
AND visibility = PUBLIC
~~~

Nếu có tài liệu public toàn hệ thống, hãy mô hình hóa phạm vi global rõ ràng, ví dụ scope riêng hoặc index riêng. Không bỏ tenant filter chỉ vì document có visibility PUBLIC.

### 4.2. Owner và ACL có thể được gộp vào principal list

Có thể đưa owner principal vào acl.principalIds khi index:

~~~json
{
  "ownerId": "user:42",
  "acl": {
    "principalIds": ["user:42", "group:engineering"]
  }
}
~~~

Khi đó query chỉ cần kiểm tra visibility PUBLIC hoặc terms trên principalIds. Nếu owner có quyền đặc biệt khác với READ, giữ ownerId riêng để policy dễ hiểu và dễ kiểm thử.

### 4.3. Quyền READ khác quyền WRITE

Search query đọc document thường chỉ cần quyền READ. Không suy ra người có thể đọc cũng được update/delete. Các API ghi cần authorization riêng dựa trên action và source of truth.

## 5. Điều kiện nghiệp vụ trong vector search

Business filters thường gồm:

- status = PUBLISHED.
- category nằm trong danh sách được chọn.
- language = vi.
- price trong khoảng min/max.
- effectiveAt đã bắt đầu.
- expiresAt chưa đến.
- stockStatus = IN_STOCK.
- deleted = false.
- loại nội dung hoặc version phù hợp.

Ví dụ:

~~~json
{
  "bool": {
    "filter": [
      { "term": { "status": "PUBLISHED" } },
      { "terms": { "category": ["security", "platform"] } },
      { "term": { "language": "vi" } },
      { "range": { "price": { "gte": 100000, "lte": 500000 } } },
      { "range": { "effectiveAt": { "lte": "2026-11-13T00:00:00Z" } } },
      { "range": { "expiresAt": { "gt": "2026-11-13T00:00:00Z" } } },
      { "term": { "deleted": false } }
    ]
  }
}
~~~

Ngày hiện tại nên được tính ở application/service theo timezone và business calendar đã thống nhất, rồi truyền vào query. Điều này giúp test có thể cố định Clock và tránh semantics khác nhau giữa service với Elasticsearch.

### 5.1. Hard constraint và soft preference

Không phải mọi điều kiện đều cần filter:

| Loại điều kiện | Ví dụ | Cách áp dụng |
|---|---|---|
| Bắt buộc | Tenant, ACL, không deleted | Filter, không được bỏ qua |
| Đủ điều kiện nghiệp vụ | Đã publish, còn hiệu lực, trong ngân sách tối đa | Pre-filter |
| Ưu tiên mềm | Ưu tiên category yêu thích, mới cập nhật, cùng ngôn ngữ | Boost hoặc reranking |

Nếu người dùng nói “chỉ tài liệu tiếng Việt”, language là hard filter. Nếu nói “ưu tiên tiếng Việt”, language có thể là soft preference. ACL luôn là hard constraint.

Không biến quyền truy cập thành boost. Một tài liệu không được phép xem không thể trở nên hợp lệ chỉ vì score cao.

## 6. Pre-filter và post-filter trong kNN

Đây là điểm quan trọng nhất khi viết truy vấn vector có điều kiện.

### 6.1. Pre-filter

Pre-filter nằm trong chính kNN clause. Elasticsearch dùng điều kiện đó trong quá trình tìm candidate vector. Mục tiêu là tìm các neighbor gần nhất trong tập document thỏa filter.

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.31, 0.08],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "bool": {
        "filter": [
          { "term": { "tenantId": "tenant-alpha" } },
          { "term": { "status": "PUBLISHED" } },
          { "term": { "visibility": "PUBLIC" } }
        ]
      }
    }
  }
}
~~~

Nếu có đủ document thỏa filter, vector search tìm top k trong tập eligible documents. Đây là cách phù hợp cho tenant, ACL và business conditions khi dùng kNN.

### 6.2. Post-filter

Post-filter chạy sau khi kNN đã chọn candidate. Ví dụ:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "knn": {
            "field": "embedding",
            "query_vector": [0.12, -0.31, 0.08],
            "k": 10,
            "num_candidates": 100
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-alpha" } },
        { "term": { "status": "PUBLISHED" } }
      ]
    }
  }
}
~~~

Trong Query DSL, filter nằm ngoài knn query là post-filter. kNN có thể chọn 10 document gần nhất trên toàn index trước, rồi bool.filter loại document không thuộc tenant hoặc không publish. Response có thể chỉ còn 2 hit dù vẫn có nhiều document phù hợp trong tenant đó.

Post-filter không phải cách tốt để chọn top k trong tập đủ điều kiện. Với authorization, cũng không nên dựa vào một filter ngoài kNN nếu hệ thống cần bảo đảm tập candidate của vector retrieval đã bị giới hạn từ đầu.

### 6.3. So sánh

| Đặc điểm | Pre-filter trong kNN | Post-filter ngoài kNN |
|---|---|---|
| Thời điểm | Trong quá trình kNN tìm candidate | Sau khi kNN đã chọn candidate |
| Ý nghĩa | Tìm neighbor trong tập đủ điều kiện | Lọc lại top-k đã tìm trên tập rộng hơn |
| Số hit | Có thể đạt k nếu đủ document phù hợp và ngưỡng similarity cho phép | Có thể ít hơn k |
| Phù hợp cho ACL/tenant | Lựa chọn phù hợp trong truy vấn vector | Không nên dùng làm filter duy nhất |
| Ảnh hưởng hiệu năng | Filter chọn lọc có thể làm ANN phải duyệt nhiều hơn | Có thể ít công việc filter trong vector traversal nhưng dễ thiếu hit |

Elasticsearch có thể dùng chiến lược thực thi khác nhau tùy mức chọn lọc của filter và số vector trong shard. Tính chất pre-filter mô tả semantics của kết quả, không có nghĩa mọi filter luôn làm query nhanh hơn.

### 6.4. k và num_candidates

- k là số neighbor mục tiêu.
- num_candidates là số candidate được xem xét trên mỗi shard.
- Tăng num_candidates thường cải thiện recall của approximate search nhưng tăng chi phí.
- Filter rất chọn lọc có thể khiến HNSW phải khám phá nhiều node hơn để tìm đủ candidate hợp lệ.

Benchmark với phân bố tenant/ACL thực tế. Đừng đặt num_candidates quá thấp rồi kết luận filter làm mất dữ liệu, cũng đừng tăng vô hạn để bù cho mapping hoặc query sai.

### 6.5. similarity threshold

kNN có thể trả k neighbor gần nhất ngay cả khi tất cả đều không thật sự liên quan. Nếu nghiệp vụ cần ngưỡng tương đồng tối thiểu, dùng tham số similarity khi version và metric hỗ trợ, hoặc kiểm tra score theo quy tắc đã được hiệu chỉnh.

Ngưỡng similarity không thay thế ACL. Nó chỉ loại kết quả không đủ liên quan.

## 7. Tạo filter Query DSL từ SearchContext

Nên có một service chuyên tạo security scope từ authentication:

~~~java
public record SearchContext(
        String tenantId,
        String userId,
        Set<String> principalIds) {
}
~~~

Factory:

~~~java
public SearchContext from(Authentication authentication) {
    String tenantId = tenantResolver.requireTenant(authentication);
    String userId = userResolver.requireUserId(authentication);
    Set<String> principals = groupResolver.resolvePrincipals(authentication);

    principals = new HashSet<>(principals);
    principals.add("user:" + userId);

    return new SearchContext(tenantId, userId, Set.copyOf(principals));
}
~~~

Các resolver là thành phần nội bộ của ứng dụng. Không lấy Set principal từ request body.

### 7.1. Không có security context thì fail closed

Nếu không xác định được tenant hoặc identity, không chạy vector query rộng:

~~~java
if (context.tenantId() == null || context.tenantId().isBlank()) {
    throw new AccessDeniedException("A tenant context is required");
}
~~~

Nếu principalIds rỗng, policy có thể chỉ cho phép tài liệu PUBLIC trong tenant hoặc trả kết quả rỗng. Không bỏ toàn bộ ACL clause chỉ vì danh sách principal rỗng.

### 7.2. Principal list có thể gồm user và groups

Ví dụ:

~~~text
user:42
group:engineering
group:platform
role:knowledge-reader
~~~

Terms query match bất kỳ principal nào trong danh sách. Nếu policy yêu cầu đồng thời nhiều điều kiện như user thuộc tenant và có permission READ, hãy biểu diễn logic đó rõ ràng bằng bool filter hoặc nested query.

## 8. Vector query với Spring Data Elasticsearch NativeQuery

Spring Data Elasticsearch cung cấp NativeQuery để dùng builder của Elasticsearch Java API Client. Từ Spring Data Elasticsearch 5.4, API top-level kNN trong NativeQueryBuilder được cấu hình bằng withKnnSearches. Filter pre-filter được gắn vào chính KnnSearch builder.

Ví dụ kNN-only:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

List<Float> queryVector = embeddingService.embedQuery(text);
List<FieldValue> principalValues = context.principalIds().stream()
        .map(FieldValue::of)
        .toList();

NativeQuery query = NativeQuery.builder()
        .withKnnSearches(knn -> knn
                .field("embedding")
                .queryVector(queryVector)
                .k(20)
                .numCandidates(200)
                .filter(filter -> filter.bool(bool -> {
                    bool.filter(f -> f.term(t -> t
                            .field("tenantId")
                            .value(FieldValue.of(context.tenantId()))));
                    bool.filter(f -> f.term(t -> t
                            .field("status")
                            .value(FieldValue.of("PUBLISHED"))));
                    bool.filter(f -> f.term(t -> t
                            .field("deleted")
                            .value(FieldValue.of(false))));

                    bool.filter(f -> f.bool(access -> {
                        access.should(s -> s.term(t -> t
                                .field("visibility")
                                .value(FieldValue.of("PUBLIC"))));

                        if (!principalValues.isEmpty()) {
                            access.should(s -> s.terms(t -> t
                                    .field("acl.principalIds")
                                    .terms(values -> values.value(principalValues))));
                        }

                        return access.minimumShouldMatch("1");
                    }));

                    return bool;
                })))
        .build();

SearchHits<KnowledgeDocument> hits = operations.search(
        query,
        KnowledgeDocument.class,
        IndexCoordinates.of("knowledge-documents"));
~~~

Ví dụ dùng flattened ACL field acl.principalIds. Điều kiện access có nghĩa document public trong tenant hoặc chia sẻ cho ít nhất một principal của người dùng. Tenant, status và deleted luôn là filter bắt buộc.

Tên builder method được lấy từ API Spring Data Elasticsearch hiện hành và Elasticsearch Java API Client. Nếu dùng release khác, đối chiếu API version của dependency; không thay pre-filter bằng một filter ở vị trí khác chỉ để code biên dịch.

### 8.1. Dùng business filters động

Có thể xây thêm filter category, language hoặc date range từ request đã validate. Ví dụ ở Query DSL:

~~~json
{
  "bool": {
    "filter": [
      { "term": { "tenantId": "tenant-alpha" } },
      { "term": { "status": "PUBLISHED" } },
      { "terms": { "category": ["security", "platform"] } },
      { "term": { "language": "vi" } },
      { "range": { "effectiveAt": { "lte": "2026-11-13T00:00:00Z" } } },
      { "range": { "expiresAt": { "gt": "2026-11-13T00:00:00Z" } } }
    ]
  }
}
~~~

Các filter này có thể được thêm vào cùng bool filter bên trong KnnSearch.filter. Không cho client truyền raw Query DSL hoặc tên field tùy ý.

### 8.2. Không nhầm NativeQueryBuilder.withFilter với KnnSearch.filter

NativeQueryBuilder có nhiều điểm cấu hình như withQuery, withFilter và withKnnSearches. Đối với top-level kNN pre-filter, filter phải nằm trên KnnSearch được tạo trong withKnnSearches. Một filter đặt ở một vị trí khác trong SearchRequest không tự động trở thành pre-filter của kNN.

Hãy kiểm tra JSON request thực tế trong integration test hoặc logging an toàn khi nâng version. Không suy luận semantics chỉ từ tên method có chữ filter.

## 9. Dùng knn query bên trong Query DSL

Elasticsearch cũng hỗ trợ knn query bên trong query clause. Trong trường hợp này, đặt filter trực tiếp bên trong knn query:

~~~json
{
  "query": {
    "knn": {
      "field": "embedding",
      "query_vector": [0.12, -0.31, 0.08],
      "k": 20,
      "num_candidates": 200,
      "filter": {
        "bool": {
          "filter": [
            { "term": { "tenantId": "tenant-alpha" } },
            { "term": { "status": "PUBLISHED" } },
            { "terms": { "acl.principalIds": ["user:42", "group:engineering"] } }
          ]
        }
      }
    }
  }
}
~~~

Nếu cần OR giữa public và principal ACL, thêm bool.should và minimum_should_match = 1 trong filter object. Đừng đặt public/ACL thành một sibling filter bên ngoài knn.

Trong Spring Data, Query DSL knn query có thể được xây bằng withQuery trên NativeQueryBuilder nếu Java API Client version hỗ trợ builder tương ứng. Top-level KnnSearch và query-level KnnQuery là hai kiểu request khác nhau; Spring Data đã chuyển sang withKnnSearches cho top-level kNN từ 5.4.

## 10. Ví dụ kết hợp tenant, ACL và business filter

Giả sử người dùng tìm tài liệu trong tenant alpha, chỉ muốn tài liệu đã publish, chưa hết hạn, thuộc category security hoặc platform, và có quyền đọc.

Query REST minh họa:

~~~http
POST knowledge-documents/_search
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.31, 0.08],
    "k": 20,
    "num_candidates": 200,
    "filter": {
      "bool": {
        "filter": [
          { "term": { "tenantId": "tenant-alpha" } },
          { "term": { "status": "PUBLISHED" } },
          { "term": { "deleted": false } },
          { "terms": { "category": ["security", "platform"] } },
          { "range": { "effectiveAt": { "lte": "2026-11-13T00:00:00Z" } } },
          { "range": { "expiresAt": { "gt": "2026-11-13T00:00:00Z" } } },
          {
            "bool": {
              "should": [
                { "term": { "visibility": "PUBLIC" } },
                {
                  "terms": {
                    "acl.principalIds": [
                      "user:42",
                      "group:engineering",
                      "role:knowledge-reader"
                    ]
                  }
                }
              ],
              "minimum_should_match": 1
            }
          }
        ]
      }
    }
  }
}
~~~

Các điều kiện trong filter được AND. Hai nhánh trong ACL should được OR. minimum_should_match = 1 bảo đảm document phải public hoặc có grant cho một principal.

Nếu bỏ minimum_should_match, bool có filter/must khác có thể mặc định không yêu cầu should match; khi đó ACL OR có thể không còn là điều kiện bắt buộc như mong muốn.

## 11. ACL dạng nested grant

Nếu mỗi grant chứa principal, permission và thời hạn, query cần bảo đảm tất cả điều kiện cùng thuộc một grant:

~~~json
{
  "nested": {
    "path": "acl.grants",
    "query": {
      "bool": {
        "filter": [
          {
            "terms": {
              "acl.grants.principalId": [
                "user:42",
                "group:engineering"
              ]
            }
          },
          {
            "term": {
              "acl.grants.permission": "READ"
            }
          },
          {
            "bool": {
              "should": [
                { "bool": { "must_not": { "exists": { "field": "acl.grants.expiresAt" } } } },
                { "range": { "acl.grants.expiresAt": { "gt": "2026-11-13T00:00:00Z" } } }
              ],
              "minimum_should_match": 1
            }
          }
        ]
      }
    }
  }
}
~~~

Đặt nested query này bên trong KnnSearch.filter để nó là pre-filter. Elasticsearch hỗ trợ nested filters trong kNN filter theo các giới hạn của version đang chạy; kiểm tra tài liệu và integration test khi dùng nested vector/ACL.

Với nested ACL, hãy cẩn thận khi một document có nhiều grant cùng principal nhưng khác permission hoặc expiration. Mục tiêu là xác định một grant READ còn hiệu lực, không ghép field của các grant khác nhau.

## 12. Business filter nào nên chạy trước vector retrieval?

Điều kiện loại trừ document nên được áp dụng trước hoặc trong vector retrieval:

- Tenant và ACL.
- Status bắt buộc phải PUBLISHED.
- Document chưa xóa.
- Giá phải nằm trong ngân sách cứng.
- Ngày phải còn hiệu lực.
- Locale bắt buộc.
- Product phải còn hàng nếu use case chỉ tìm hàng có thể mua.

Điều kiện chỉ ảnh hưởng thứ tự có thể xử lý sau:

- Ưu tiên tài liệu mới cập nhật.
- Ưu tiên category yêu thích.
- Ưu tiên nguồn chính thức.
- Ưu tiên ngôn ngữ ưa thích nếu vẫn chấp nhận ngôn ngữ khác.

Một cách phân loại:

~~~text
Hard constraints
  -> filter candidate set
  -> vector retrieval

Soft preferences
  -> score boost / fusion / reranking
  -> final ordering
~~~

Không dùng boost thay cho hard filter. Không dùng post-filter cho ACL với mục tiêu lấy top k trong tập được phép.

## 13. Hybrid search phải lọc từng nhánh

Một hệ thống hybrid có thể chạy lexical retrieval và vector retrieval rồi hợp nhất kết quả. Cả hai nhánh phải dùng cùng tenant, ACL và business constraints.

Ví dụ Query DSL:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "bool": {
            "must": [
              {
                "multi_match": {
                  "query": "cấu hình xác minh TLS",
                  "fields": ["title^3", "content"]
                }
              }
            ],
            "filter": [
              { "term": { "tenantId": "tenant-alpha" } },
              { "term": { "status": "PUBLISHED" } },
              {
                "bool": {
                  "should": [
                    { "term": { "visibility": "PUBLIC" } },
                    {
                      "terms": {
                        "acl.principalIds": ["user:42", "group:engineering"]
                      }
                    }
                  ],
                  "minimum_should_match": 1
                }
              }
            ]
          }
        },
        {
          "knn": {
            "field": "embedding",
            "query_vector": [0.12, -0.31, 0.08],
            "k": 50,
            "num_candidates": 200,
            "filter": {
              "bool": {
                "filter": [
                  { "term": { "tenantId": "tenant-alpha" } },
                  { "term": { "status": "PUBLISHED" } },
                  {
                    "bool": {
                      "should": [
                        { "term": { "visibility": "PUBLIC" } },
                        {
                          "terms": {
                            "acl.principalIds": ["user:42", "group:engineering"]
                          }
                        }
                      ],
                      "minimum_should_match": 1
                    }
                  }
                ]
              }
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

Lexical branch có bool.filter riêng. Vector branch có filter bên trong knn. Không giả định filter ở bool cha sẽ tự động trở thành kNN pre-filter.

Nếu dùng retriever API/RRF, áp dụng cùng authorization/business policy cho mọi retriever con. Một nhánh không có ACL filter vẫn có thể đưa document không được phép vào candidate set.

### 13.1. Hợp nhất kết quả không phải bước authorization

RRF hoặc reranker chỉ sắp xếp candidate. Chúng không thay thế ACL. Không đợi tới sau fusion mới loại dữ liệu trái quyền nếu có thể áp dụng policy ngay trong retriever.

Nếu vẫn có một kiểm tra authorization cuối trước khi trả response, đó là lớp phòng vệ bổ sung để xử lý ACL projection stale; không nên dùng nó làm cách duy nhất giới hạn tập vector retrieval.

### 13.2. Candidate count và filter consistency

Mỗi nhánh có thể trả số lượng candidate khác nhau. Hãy chọn k/candidate size phù hợp, nhưng không nới quyền để bù thiếu kết quả. Nếu tenant nhỏ hoặc ACL rất chọn lọc, điều chỉnh num_candidates và đo recall trên tập hợp lệ.

## 14. Document-Level Security của Elasticsearch

Elasticsearch cung cấp Document-Level Security (DLS) để gắn query giới hạn document mà một role được đọc. DLS có thể là lớp bảo vệ bổ sung khi client kết nối bằng credential gắn với identity/role tương ứng.

Ví dụ role query giới hạn document theo username:

~~~json
{
  "indices": [
    {
      "names": ["knowledge-documents"],
      "privileges": ["read"],
      "query": {
        "template": {
          "source": {
            "terms": {
              "acl.principalIds": "{{#toJson}}_user.metadata.principal_ids{{/toJson}}"
            }
          }
        }
      }
    }
  ]
}
~~~

Trong ví dụ, metadata của Elasticsearch user chứa principal IDs đã chuẩn hóa, ví dụ user:42 và group:engineering. Role query có thể dùng Mustache template để lấy username, roles hoặc metadata của authenticated Elasticsearch user. Với metadata dạng array/object, template có thể dùng toJson theo hướng dẫn của Elasticsearch. Tên metadata và cách đồng bộ group membership phải khớp với identity model thực tế.

### 14.1. Application filter và DLS giải quyết hai lớp khác nhau

| Cách | Identity được dùng | Trách nhiệm |
|---|---|---|
| Application-level filter | Người dùng cuối từ application security context | Backend thêm tenant/ACL vào mọi truy vấn |
| Elasticsearch DLS | User/API key mà Elasticsearch xác thực | Elasticsearch giới hạn document theo role query |
| Kết hợp cả hai | Cả hai | Defense in depth, nhưng phải kiểm thử semantics của hai lớp |

Nếu mọi request từ backend dùng chung một Elasticsearch service account, DLS chỉ nhìn thấy service account đó. Nó không tự biết người dùng cuối đang gọi API là ai. Khi đó backend vẫn phải tạo ACL filter từ authenticated principal.

Nếu người dùng hoặc service có credential Elasticsearch riêng, DLS có thể dùng metadata của credential để giới hạn document. Phải bảo đảm role và API key được cấp đúng phạm vi.

### 14.2. DLS không phải thay thế mọi authorization logic

DLS được thiết kế chủ yếu cho read-only access. Tài liệu Elastic lưu ý không nên thực hiện write operations bằng user có DLS/FLS trên index tương ứng. Quyền ghi, update và delete vẫn cần policy riêng.

DLS cũng có giới hạn: global index statistics dùng cho relevance scoring không bị giới hạn theo role query; một số aggregation hoặc query có thể để lộ thông tin tổng hợp về document không được trả về. Nếu dữ liệu yêu cầu cô lập nghiêm ngặt, đánh giá kỹ aggregation, suggest, metadata và cân nhắc tách index theo ranh giới bảo mật.

### 14.3. Nhiều role được kết hợp theo OR

Khi một Elasticsearch user có nhiều role áp dụng DLS cho cùng index, document queries của các role được kết hợp bằng OR. Một role khác không có DLS có thể mở quyền đọc toàn bộ document trong index.

Kiểm tra tổ hợp role thực tế của user/API key. Đừng chỉ kiểm thử một role đơn lẻ.

### 14.4. Filtered alias không phải security boundary

Alias có filter có thể hữu ích cho convenience hoặc use case search, nhưng không nên dùng làm cơ chế bảo mật duy nhất để ngăn người dùng truy cập document khác. Elastic khuyến nghị dùng DLS để bảo vệ document-level access. Kiểm tra index privileges, alias privileges và các API có thể truy cập backing index.

## 15. Field-Level Security và dữ liệu nhạy cảm

Document-level ACL quyết định document nào có thể đọc. Field-Level Security (FLS) giới hạn field nào một role được đọc. Hai vấn đề khác nhau.

Ví dụ người dùng có thể xem tài liệu nhưng không được xem:

- internalNotes.
- customerEmail.
- costPrice.
- securityReview.

Không dựa vào source filtering trong application query như một cơ chế bảo mật. Source filtering chỉ yêu cầu Elasticsearch không trả một số field trong response; người dùng có quyền query trực tiếp vẫn có thể yêu cầu field khác nếu security role cho phép.

Nếu field thực sự nhạy cảm, dùng FLS, tách document/index hoặc loại field đó khỏi projection mà người dùng không được truy cập.

## 16. Cập nhật ACL và độ trễ đồng bộ

ACL thường được quản lý ở database hoặc authorization service rồi đồng bộ sang Elasticsearch. Khi quyền thay đổi, document projection cần cập nhật:

~~~text
Permission source changes
        |
        v
Outbox / CDC event
        |
        v
ACL projection consumer
        |
        v
Update tenant/ACL fields in Elasticsearch
        |
        v
Refresh makes new ACL searchable
~~~

Nếu hệ thống eventual consistency, có một khoảng thời gian giữa lúc source thu hồi quyền và lúc Elasticsearch cập nhật ACL. Với nội dung nhạy cảm, không được mặc định khoảng trễ này là chấp nhận được.

Các lựa chọn:

- Cập nhật ACL projection đồng bộ trước khi xác nhận thay đổi quyền.
- Dùng outbox và refresh policy phù hợp khi cần search visibility.
- Kiểm tra authorization cuối với source of truth trước khi trả nội dung nhạy cảm.
- Dùng DLS hoặc index separation để thêm ranh giới bảo vệ.
- Có cơ chế deny/revocation list ngắn hạn trong khi projection đang cập nhật.

Kiểm tra cuối trước khi trả response có thể làm kết quả ít hơn k; khi đó backend có thể tiếp tục lấy candidate tiếp theo, nhưng cần giới hạn số vòng và không để lộ nội dung chưa được phép qua log/cache.

### 16.1. ACL version

Có thể lưu aclVersion hoặc permissionUpdatedAt trong document để quan sát độ mới của projection:

~~~json
{
  "tenantId": "tenant-alpha",
  "acl": {
    "principalIds": ["user:42", "group:engineering"]
  },
  "aclVersion": 27
}
~~~

Version giúp đối soát source với projection và phát hiện consumer bị lag. Nó không tự ngăn truy cập nếu query không kiểm tra hoặc source policy chưa được áp dụng.

### 16.2. Xóa quyền khác với xóa document

Khi thu hồi group access, cập nhật ACL list để loại principal đó. Khi user bị vô hiệu hóa, cập nhật identity/group expansion hoặc kiểm tra principal status. Không nhất thiết xóa document.

Khi xóa document, cập nhật tombstone/deleted field và bảo đảm vector retrieval filter loại document đó.

## 17. Cache và authorization context

Kết quả search có thể được cache ở application, API gateway hoặc tầng query. Cache key phải bao gồm mọi yếu tố làm thay đổi tập document được phép:

- tenantId.
- userId hoặc tập principal IDs.
- role/group membership version.
- ACL policy version nếu có.
- business filters.
- query text hoặc query hash.
- embedding model version.
- index/projection version.

Không cache kết quả của user A rồi trả cho user B chỉ vì query text giống nhau. Không dùng tenantId làm cache key duy nhất nếu ACL khác nhau giữa người dùng trong cùng tenant.

Khi group membership hoặc ACL thay đổi, invalidate cache hoặc dùng TTL/policy phù hợp với mức độ nhạy cảm. Với yêu cầu revoke tức thời, cache cũ không được tiếp tục phục vụ kết quả đã mất quyền.

## 18. Aggregation, count và metadata cũng cần scope

Không chỉ hits mới có thể tiết lộ dữ liệu. Các thông tin sau cũng có thể nhạy cảm:

- Total hits.
- Aggregation theo category hoặc department.
- Facet counts.
- Highlight fragments.
- Suggestion.
- Inner hits.
- Error messages chứa index/document identifiers.

Nếu application filter là ranh giới bảo vệ, bảo đảm aggregation và count dùng cùng query scope. Không chạy một count toàn index rồi trả total cho người dùng bị giới hạn ACL.

Nếu dùng DLS, lưu ý Elastic nêu rõ một số global index statistics và aggregation/query patterns vẫn có thể tiết lộ thông tin tổng hợp về dữ liệu không được trả trực tiếp. Với dữ liệu có yêu cầu cô lập cao, cân nhắc index separation hoặc một lớp aggregate service được kiểm soát.

## 19. Multi-tenant: filter bắt buộc và index separation

Có nhiều chiến lược cô lập tenant:

| Chiến lược | Ưu điểm | Hạn chế |
|---|---|---|
| Shared index + tenantId filter | Ít index, dễ vận hành | Mọi query path phải giữ tenant filter |
| Index theo tenant | Cô lập index tốt hơn | Số index/shard tăng, quản lý lifecycle phức tạp |
| Cluster/deployment riêng | Ranh giới vận hành mạnh | Chi phí và độ phức tạp cao |

Với shared index, tenantId phải là filter bắt buộc bên trong vector pre-filter và lexical branch. Nếu tenant isolation là yêu cầu nghiêm ngặt, cân nhắc index hoặc deployment riêng kết hợp privilege ở Elasticsearch.

Không dùng tenantId từ request như nguồn duy nhất. Lấy tenant từ identity đã xác thực, sau đó kiểm tra người dùng có quyền chọn tenant đó hay không.

### 19.1. Tenant filter và routing

Custom routing theo tenant có thể đưa document của một tenant tới cùng shard và giúp một số query tenant-scoped hiệu quả hơn. Tuy nhiên, routing không phải authorization. Người dùng có quyền truy cập index vẫn có thể thử routing khác nếu security layer không chặn.

Nếu dùng routing, phải giữ routing nhất quán khi index/get/update/delete và vẫn áp dụng tenant/ACL filter.

## 20. Hiệu năng khi filter vector search

Filter trong kNN có thể ảnh hưởng cách ANN duyệt vector graph. Với filter chọn lọc, HNSW có thể phải khám phá thêm node để thu thập đủ candidate thỏa điều kiện. Elasticsearch có thể chuyển sang brute-force trên segment trong một số trường hợp.

Đo trên dữ liệu thực:

- Tỷ lệ document thuộc tenant.
- Tỷ lệ document public hoặc được share.
- Số principal trung bình trên document.
- Số group của user.
- Số shard và vector trên mỗi shard.
- k và num_candidates.
- p50/p95/p99 latency.
- Recall@k sau filter.

### 20.1. ACL list quá lớn

Nếu một document được share với hàng chục nghìn user riêng lẻ, mảng acl.principalIds có thể trở nên lớn và khó cập nhật. Cân nhắc:

- Share theo group/role thay vì từng user.
- Chuẩn hóa group membership trong identity service.
- Dùng nested grant khi cần permission tuple.
- Tách public/tenant/group scopes.
- Dùng index/partition theo ranh giới phù hợp.
- Cache principal expansion ở server với version/invalidation rõ ràng.

Không mở rộng toàn bộ group membership từ một nguồn không tin cậy ở mỗi request.

### 20.2. Tăng num_candidates có kiểm soát

Tăng num_candidates có thể cải thiện recall nhưng tăng CPU và latency. Khi filter rất chọn lọc, cần benchmark kết hợp filter selectivity và số candidate. Không thay num_candidates bằng cách bỏ ACL filter.

### 20.3. Filter exact field

Dùng term/terms trên keyword, range trên numeric/date và exists khi cần. Tránh wildcard hoặc script filter cho ACL nếu có thể mô hình hóa bằng field rõ ràng; query phức tạp có thể làm tăng chi phí.

## 21. Tổ chức code để không quên security filters

Không để mỗi controller tự ghép ACL Query DSL. Tạo một policy/query factory dùng chung:

~~~text
Controller
   |
   v
Authentication + SearchRequest
   |
   v
SearchContextFactory
   |
   v
AccessPolicy / FilterFactory
   |
   +---- tenant filter
   +---- owner/public/group ACL
   +---- status/date/tenant business filters
   |
   v
VectorSearchRepository
   |
   v
ElasticsearchOperations
~~~

Một contract:

~~~java
public interface SearchFilterFactory {
    Query buildMandatoryKnnFilter(
            SearchContext context,
            KnowledgeSearchFilters filters);
}
~~~

Repository nhận SearchContext hoặc một query đã được policy factory tạo. Không cho caller bỏ qua filter bằng cách truyền null hoặc một raw query tùy ý.

### 21.1. Phân biệt mandatory và optional filters

Có thể dùng hai kiểu object:

- MandatorySearchScope: tenant, ACL, status/deleted constraints.
- OptionalSearchFilters: category, date range, language, price.

Khi build query, mandatory scope luôn được thêm. Optional filters chỉ có thể thu hẹp tập kết quả.

Nếu API có chức năng “include archived” hoặc “search all statuses”, đó phải là một permission/capability được xác thực riêng, không chỉ là boolean client gửi lên.

### 21.2. Không expose raw Query DSL qua API

Không nhận một JSON Query DSL tùy ý từ frontend rồi gửi nguyên vào Elasticsearch. Client có thể cố bỏ ACL filter, truy vấn field nhạy cảm hoặc tạo query tốn tài nguyên.

Hãy nhận request DTO có field được cho phép, validate giá trị, rồi backend tự xây Query DSL.

## 22. Kiểm thử quyền truy cập trong vector search

Test cần xác nhận cả kết quả được phép và kết quả bị từ chối. Chỉ kiểm tra vector ranking là chưa đủ.

Một fixture:

| Document | Tenant | ACL | Status | Category |
|---|---|---|---|---|
| A | alpha | group:engineering | PUBLISHED | security |
| B | alpha | user:99 | PUBLISHED | security |
| C | alpha | PUBLIC | PUBLISHED | platform |
| D | beta | PUBLIC | PUBLISHED | security |
| E | alpha | group:engineering | DRAFT | security |
| F | alpha | group:engineering | PUBLISHED, expired | security |

User test:

~~~text
tenant = alpha
principals = [user:42, group:engineering]
~~~

Kết quả mong muốn:

- A được trả về.
- C được trả về nếu PUBLIC có nghĩa public trong tenant alpha.
- B không được trả về.
- D không được trả về dù PUBLIC vì khác tenant.
- E không được trả về vì DRAFT.
- F không được trả về vì hết hạn.

### 22.1. Test tenant isolation

Tạo document ở tenant khác có vector gần query hơn tất cả document trong tenant hiện tại. Search vẫn chỉ trả document thuộc tenant được xác thực.

Test này bắt được lỗi filter đặt ngoài kNN khiến candidate set bị lấy từ toàn index.

### 22.2. Test group membership

User thuộc group engineering được phép đọc document có principal group:engineering. Khi group membership bị thu hồi, query context mới không còn principal đó và document phải biến mất khỏi kết quả.

### 22.3. Test public scope

Document PUBLIC trong cùng tenant được đọc; document PUBLIC ở tenant khác vẫn bị loại. Test này xác nhận PUBLIC không vô tình bypass tenant boundary.

### 22.4. Test business filters

Kiểm tra status, deleted, date range, price và category được áp dụng cùng ACL. Đặc biệt test thời điểm effectiveAt/expiresAt ngay sát ranh giới.

### 22.5. Test pre-filter và post-filter

Tạo nhiều vector gần nhất nhưng phần lớn thuộc tenant khác. Với pre-filter, query vẫn tìm được top k trong tenant nếu đủ dữ liệu phù hợp. Với post-filter, response có thể ít hơn k. Test cần làm rõ semantics mà repository đảm bảo.

### 22.6. Test fail closed

Khi thiếu tenant, authentication hoặc principal context, backend không được chạy query không filter. Có thể trả AccessDenied/BadRequest theo hợp đồng API hoặc trả empty result theo policy.

### 22.7. Test hybrid branch

Đặt document trái quyền vào top lexical và top vector. Cả hai nhánh phải loại document đó trước khi merge. Kiểm tra RRF/reranker không đưa document trái quyền trở lại.

### 22.8. Test ACL revocation và cache

Thu hồi quyền, cập nhật projection/cache và xác nhận người dùng không còn nhận nội dung. Nếu có eventual consistency, test phải mô tả rõ giới hạn và cơ chế bảo vệ trong khoảng đồng bộ.

## 23. Chẩn đoán khi vector search trả quá ít hoặc không có hit

Nếu filter quá rộng hoặc quá chặt, phân loại vấn đề:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không có hit | tenantId sai hoặc principal list rỗng | Kiểm tra SearchContext, không log dữ liệu nhạy cảm |
| Chỉ trả public docs | ACL terms không match | Kiểm tra canonical principal IDs và mapping keyword |
| Kết quả thiếu dù có document hợp lệ | Filter đang là post-filter | Kiểm tra vị trí filter trong kNN clause |
| User cùng group thấy kết quả khác nhau | Group expansion không nhất quán | Kiểm tra identity provider và cache membership |
| User vừa bị revoke vẫn thấy tài liệu | ACL projection/cache chưa cập nhật | Kiểm tra event lag, refresh và cache invalidation |
| Query chậm khi filter chọn lọc | ANN graph phải duyệt nhiều candidate | Benchmark num_candidates, shard và filter selectivity |
| Hybrid trả kết quả trái quyền | Một retriever branch thiếu filter | Kiểm tra từng lexical/vector/retriever branch |
| Public document lộ sang tenant khác | PUBLIC bypass tenant filter | Giữ tenantId trong mandatory AND scope |

Không debug bằng cách bỏ ACL filter trên production. Dùng test index, query fixture hoặc môi trường staging với dữ liệu giả.

## 24. Các lỗi thường gặp

### Chỉ filter sau khi vector search

Kết quả có thể ít hơn k và candidate được tìm trên tập rộng. Đặt điều kiện bắt buộc trong kNN filter.

### Đặt ACL thành should tùy chọn

Nếu bool có filter/must khác, should có thể không bắt buộc. Dùng bool lồng và minimum_should_match = 1 cho nhánh public-or-principal.

### Lấy tenantId từ request

Người dùng có thể đổi tenant. Lấy tenant từ authentication đã xác thực và kiểm tra quyền chọn tenant.

### Lấy principalIds từ client

Client có thể giả group/role. Resolve group membership ở server.

### Dùng match trên ACL keyword

ACL identifiers là giá trị cấu trúc. Dùng term/terms trên keyword.

### Quên business filters trong vector branch

Lexical và vector branch có thể trả tập khác nhau. Lặp lại policy tương ứng trong từng retriever.

### Coi filter score là authorization

Boost chỉ thay đổi thứ hạng, không loại document trái quyền. ACL phải là hard filter hoặc DLS.

### Dùng filtered alias như security boundary

Alias filter không thay thế DLS. Dùng index privileges và document-level security phù hợp.

### Coi DLS tự biết end user khi backend dùng service account

Elasticsearch chỉ thấy identity của service credential. Backend vẫn phải áp dụng user ACL từ application context.

### Coi source filtering là FLS

Source filtering không phải quyền field-level. Dùng FLS hoặc tách projection nếu field nhạy cảm.

### Không cập nhật ACL projection khi quyền đổi

Document có thể tiếp tục được trả về theo ACL cũ. Theo dõi lag và thiết kế revocation path.

### Cache search result không theo user/tenant

Cache key thiếu security context có thể trả dữ liệu của người khác. Gắn tenant, principal/policy version vào key.

### Bỏ filter khi principal list rỗng

Điều đó có thể mở toàn bộ index. Fail closed hoặc chỉ cho phép nhánh PUBLIC trong tenant theo policy.

### Tăng num_candidates bằng cách bỏ filter

Điều này làm sai security scope. Tối ưu candidate count và mapping mà vẫn giữ filter.

### Quên aggregation/count scope

Hits có thể được giới hạn nhưng total/aggregation vẫn tiết lộ thông tin. Áp dụng scope và đánh giá DLS limitations.

## 25. Quy trình triển khai truy vấn vector có kiểm soát truy cập

Khi xây vector search trong Spring Data Elasticsearch:

1. Xác định source of truth cho tenant, user, group và ACL.
2. Định nghĩa document identity và metadata fields cho authorization.
3. Mapping tenantId, ownerId, visibility, principal IDs và business fields thành keyword/numeric/date/boolean phù hợp.
4. Chọn flattened keyword ACL hay nested grants theo semantics permission.
5. Tạo SearchContext từ authenticated principal ở server.
6. Fail closed nếu thiếu tenant hoặc identity.
7. Xây mandatory filter gồm tenant, ACL, deleted/status và các business constraints bắt buộc.
8. Đặt filter trong KnnSearch.filter hoặc KnnQuery.filter để pre-filter.
9. Không giả định NativeQueryBuilder.withFilter ở vị trí khác tự trở thành kNN pre-filter.
10. Áp dụng cùng authorization/business policy cho lexical và mọi hybrid retriever.
11. Dùng DLS/FLS hoặc index separation khi cần lớp bảo vệ ở Elasticsearch.
12. Thiết kế ACL update/revocation, refresh và cache invalidation.
13. Đo latency/recall với filter selectivity và principal cardinality thực tế.
14. Kiểm thử tenant boundary, group ACL, public scope, business filters, pre/post-filter và hybrid branch.
15. Kiểm thử aggregation, cache và permission revocation.
16. Theo dõi ACL projection lag, authorization denial và kết quả reconciliation.

## 26. Tổng kết

Vector similarity chỉ xếp hạng document theo độ gần embedding; nó không quyết định người dùng có quyền đọc document hay document có đáp ứng điều kiện nghiệp vụ. Một truy vấn hợp lệ phải áp dụng tenant và ACL như hard constraints, kết hợp các điều kiện như status, category, price và thời hạn, rồi mới chọn các vector phù hợp trong tập đó.

Trong Elasticsearch kNN, filter nằm bên trong kNN clause là pre-filter. Filter đặt ngoài knn query có thể trở thành post-filter và làm kết quả ít hơn k dù còn document phù hợp. Với Spring Data Elasticsearch, top-level kNN được cấu hình qua NativeQueryBuilder.withKnnSearches; đặt filter trên chính KnnSearch builder. Không suy luận rằng mọi method có tên withFilter đều tạo ra kNN pre-filter.

Authorization context phải được tạo từ identity đã xác thực. Tenant và principal IDs không được tin từ request body. Dùng keyword fields cho tenant, ACL và trạng thái; dùng nested grants khi principal, permission và expiry phải khớp trong cùng một object. Với hybrid search, mọi retriever branch đều phải áp dụng cùng policy.

Application-level filtering phù hợp khi backend dùng một Elasticsearch service account cho nhiều end user. Elasticsearch DLS có thể bổ sung ranh giới document-level theo authenticated Elasticsearch user, nhưng có giới hạn và không tự biết user cuối khi backend dùng chung credential. Filtered aliases và source filtering không thay thế security controls. Cuối cùng, cập nhật ACL, cache invalidation, aggregation scope và kiểm thử revocation quan trọng không kém việc viết đúng kNN query.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Elasticsearch Operations and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – NativeQueryBuilder API 6.1.2](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch – Migration guide 5.3 to 5.4: kNN API](https://docs.spring.io/spring-data/elasticsearch/reference/6.2/migration-guides/migration-guide-5.3-5.4.html)
- [Elasticsearch – kNN query and pre-filters/post-filters](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-knn-query)
- [Elasticsearch – Filter approximate kNN results](https://www.elastic.co/docs/solutions/search/vector/knn/filtered-knn-search)
- [Elasticsearch – kNN search](https://www.elastic.co/docs/solutions/search/vector/knn)
- [Elasticsearch – Document and field level security](https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/controlling-access-at-document-field-level)
- [Elasticsearch – Security limitations](https://www.elastic.co/docs/deploy-manage/security/limitations)
- [Elasticsearch – Filtered aliases](https://www.elastic.co/docs/manage-data/data-store/aliases)
