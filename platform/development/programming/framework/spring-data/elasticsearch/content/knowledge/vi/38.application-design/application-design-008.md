# Xóa mềm, thời hạn dữ liệu và chiến lược lọc nhất quán

Trong nhiều ứng dụng, xóa một bản ghi không có nghĩa là phải loại bỏ document khỏi Elasticsearch ngay lập tức. Người dùng có thể cần khôi phục dữ liệu đã xóa, hệ thống cần giữ lại dấu vết cho kiểm toán, hoặc dữ liệu phải được giữ trong một khoảng thời gian trước khi xóa vật lý. Những yêu cầu này dẫn tới ba khái niệm cần thiết kế cùng nhau: **xóa mềm (soft delete), thời hạn lưu trữ (retention) và lọc nhất quán (consistent filtering)**.

Xóa mềm thường đánh dấu document là đã xóa bằng một field như `deleted=true` hoặc `deletedAt`. Các truy vấn thông thường phải loại document này khỏi kết quả. Sau thời hạn cho phép khôi phục, một job có thể xóa vật lý document hoặc xử lý theo chính sách lưu trữ. Nếu chỉ thêm field `deleted` nhưng quên lọc ở một endpoint, dữ liệu đã xóa vẫn có thể xuất hiện trong search, aggregation, autocomplete, export hoặc API đọc theo ID.

Với Spring Data Elasticsearch, Elasticsearch không tự cung cấp một global soft-delete filter giống một số ORM. Ứng dụng phải tổ chức query và API truy cập dữ liệu sao cho điều kiện `deleted=false` được áp dụng nhất quán trên mọi đường đọc. Cũng cần xác định rõ nguồn dữ liệu chuẩn, cơ chế đồng bộ projection, xử lý event đến trễ và thời điểm dữ liệu thực sự biến mất khỏi search.

## 1. Phân biệt xóa mềm và xóa vật lý

**Xóa mềm** là cập nhật trạng thái document để biểu thị rằng dữ liệu không còn được sử dụng trong hoạt động bình thường. Document vẫn tồn tại trong index và có thể được truy xuất bởi quy trình khôi phục, kiểm toán hoặc dọn dẹp.

**Xóa vật lý** là loại bỏ document khỏi index bằng Delete API, Bulk API hoặc Delete By Query. Sau khi xóa và các cơ chế lưu trữ liên quan được xử lý, document không còn là một phần của dữ liệu đang được phục vụ bởi index đó.

| Tiêu chí | Xóa mềm | Xóa vật lý |
|---|---|---|
| Document còn trong index | Có | Không sau khi delete được áp dụng |
| Có thể khôi phục trực tiếp | Có thể, nếu còn dữ liệu và quyền cho phép | Thường cần nguồn backup/nguồn chuẩn để dựng lại |
| Search thông thường | Phải filter document đã xóa | Document không còn được trả về |
| Dung lượng index | Vẫn chiếm dung lượng | Có thể được giải phóng sau merge/segment cleanup |
| Audit | Có thể giữ actor/time/reason | Cần audit event riêng nếu cần lịch sử |
| Phù hợp | Undo, retention window, workflow archive | Hết hạn lưu trữ, xóa theo yêu cầu, dữ liệu không cần giữ |

Xóa mềm không làm dữ liệu biến mất khỏi Elasticsearch. Nó chỉ thay đổi trạng thái logic. Vì vậy, không được coi `deleted=true` là bằng chứng đã xóa dữ liệu theo nghĩa pháp lý hoặc bảo mật nếu dữ liệu vẫn còn trong `_source`, snapshot, log hoặc bản sao khác.

## 2. Khi nào nên dùng xóa mềm?

Xóa mềm phù hợp khi có yêu cầu rõ ràng về khả năng khôi phục hoặc lưu giữ:

- Người dùng có thể undo thao tác xóa trong một khoảng thời gian.
- Quản trị viên cần xem hoặc khôi phục bản ghi đã xóa.
- Hệ thống cần giữ trạng thái xóa để đồng bộ giữa các service.
- Nghiệp vụ cần audit ai đã xóa và khi nào.
- Bản ghi phải được ẩn khỏi hoạt động thông thường trước khi purge.
- Dữ liệu được giữ trong thời gian retention đã định nghĩa.

Không nên thêm soft delete chỉ vì nó có vẻ an toàn hơn. Nó làm tăng độ phức tạp cho mọi query, aggregation, update, reindex và cleanup. Nếu dữ liệu không cần khôi phục, không có yêu cầu audit và chính sách cho phép xóa ngay, xóa vật lý có thể đơn giản hơn.

### Soft delete không thay thế phân quyền

Field `deleted` không phải cơ chế authorization. Người dùng không được phép đọc dữ liệu của tenant khác dù document đó chưa bị xóa. Ngược lại, tài khoản quản trị có thể được phép xem bản ghi đã xóa trong một màn hình riêng. Phân quyền và trạng thái xóa phải là hai điều kiện độc lập.

## 3. Thiết kế field cho soft delete

Một mô hình cơ bản có thể dùng:

```json
{
  "id": "p-100",
  "tenantId": "tenant-42",
  "name": "Wireless Mouse",
  "deleted": true,
  "deletedAt": "2026-11-13T10:30:00Z",
  "deletedBy": "user-123",
  "deleteReason": "USER_REQUEST"
}
```

Các field thường gặp:

| Field | Kiểu | Mục đích |
|---|---|---|
| `deleted` | boolean | Trạng thái đã xóa hay chưa; thuận tiện cho filter exact |
| `deletedAt` | date | Thời điểm đánh dấu xóa, dùng cho retention và audit |
| `deletedBy` | keyword | Actor thực hiện thao tác, nếu nghiệp vụ cần |
| `deleteReason` | keyword | Mã lý do xóa có tập giá trị kiểm soát |
| `retentionUntil` | date | Mốc được phép purge sau thời gian lưu giữ |
| `legalHold` | boolean | Ngăn purge khi có yêu cầu giữ lại hợp lệ |
| `sourceVersion` | long | Version nguồn đã được áp dụng vào projection |

Không nhất thiết cần tất cả field. Chọn theo chính sách nghiệp vụ và tránh lưu thông tin cá nhân không cần thiết. `deletedBy` nên là ID hoặc actor code đã được kiểm soát; không lưu token hay bí mật vào document.

### Dùng boolean hay chỉ `deletedAt`?

Có thể dùng `deletedAt=null` để biểu thị chưa xóa và có timestamp để biểu thị đã xóa. Tuy nhiên, một field boolean `deleted` giúp filter đơn giản, rõ ràng và dễ kiểm tra. Nếu dùng cả hai, cần invariant:

- `deleted=false` thì `deletedAt` phải null.
- `deleted=true` thì `deletedAt` phải có giá trị.

Không để trạng thái hai field mâu thuẫn. Nếu chỉ dùng `deletedAt`, query cần kết hợp `must_not exists` hoặc `exists` đúng cách và phải thống nhất ở mọi nơi.

### Mapping tường minh

Ví dụ entity:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-read")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Boolean)
    private boolean deleted = false;

    @Field(type = FieldType.Date)
    private Instant deletedAt;

    @Field(type = FieldType.Keyword)
    private String deletedBy;

    @Field(type = FieldType.Keyword)
    private String deleteReason;

    @Field(type = FieldType.Date)
    private Instant retentionUntil;

    @Field(type = FieldType.Boolean)
    private boolean legalHold;

    @Version
    private Long version;

    // Constructors, getters and setters
}
```

Mapping field type tường minh giúp tránh việc một field trạng thái quan trọng bị dynamic mapping thành kiểu không phù hợp. `deleted` nên là boolean; `deletedAt` và `retentionUntil` nên là date; các mã trạng thái/actor nên là keyword nếu cần exact filter.

Giá trị mặc định `deleted=false` cần được áp dụng khi tạo document mới. Tuy nhiên, không dựa duy nhất vào default Java nếu document được tạo bởi bulk import, ingest pipeline hoặc service khác. Mapper/projector phải bảo đảm field được ghi đúng.

## 4. Mọi read path phải áp dụng cùng quy tắc

Lỗi thường gặp nhất của soft delete là chỉ filter ở màn hình search chính. Một hệ thống có thể có nhiều cách đọc document:

- Tìm kiếm theo text.
- Tìm theo ID.
- Repository derived query.
- Query DSL tự xây.
- `count` và aggregation.
- Autocomplete/suggestion.
- Export, scroll, PIT và batch processing.
- Related-document lookup hoặc enrichment.
- API nội bộ và job nền.
- Cache chứa kết quả trước khi xóa.

Nếu một đường đọc bỏ qua filter, document đã xóa có thể lộ lại. Vì vậy, cần xác định một quy tắc thống nhất: **mọi truy vấn nghiệp vụ thông thường đều phải thêm điều kiện `deleted=false` và các filter quyền truy cập cần thiết**. Chỉ endpoint quản trị hoặc quy trình retention được phép truy cập bản ghi đã xóa, với authorization riêng.

### Quy tắc filter cơ bản

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "deleted": false } },
        { "term": { "tenantId": "tenant-42" } }
      ],
      "must": [
        { "match": { "name": "wireless mouse" } }
      ]
    }
  }
}
```

`deleted=false` và `tenantId` nằm trong filter context vì chúng là điều kiện bắt buộc, không ảnh hưởng relevance score. Query text vẫn nằm trong query context để tính điểm.

## 5. Vì sao phải filter ở cả search và get-by-ID?

Một search query có thể thêm `deleted=false`, nhưng repository `findById(id)` thường thực hiện truy xuất theo ID và không tự biết quy tắc soft delete của ứng dụng. Nếu service trả trực tiếp kết quả từ `findById`, document đã xóa vẫn có thể được đọc.

Không nên giả định Spring Data Elasticsearch tự áp dụng global filter. Hãy tạo method hoặc service API có ngữ nghĩa rõ ràng:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findByIdAndTenantIdAndDeletedFalse(
        String id,
        String tenantId
    );

    List<ProductDocument> findByTenantIdAndDeletedFalse(String tenantId);

    long countByTenantIdAndDeletedFalse(String tenantId);
}
```

Derived query method làm rõ filter ở cấp repository. Cần xác nhận tên property đúng với model và mapping. Các method mặc định như `findById`, `findAll`, `existsById` hoặc `count` vẫn có semantics riêng; không dùng chúng trong service thông thường nếu chúng có thể trả dữ liệu đã xóa hoặc bỏ qua tenant scope.

### Bọc repository bằng service/facade

Một cách tổ chức là chỉ expose service nghiệp vụ cho controller:

```java
public Optional<ProductDocument> findActiveProduct(String id, String tenantId) {
    return repository.findByIdAndTenantIdAndDeletedFalse(id, tenantId);
}
```

Controller không inject repository trực tiếp. Các job và service khác cũng gọi qua facade có cùng quy tắc. Điều này giảm nguy cơ một caller vô tình dùng method không filter.

## 6. Tập trung hóa query filter trong Spring Data Elasticsearch

Với query phức tạp, có thể tạo một component chuyên xây dựng các điều kiện bắt buộc. Ví dụ:

```java
public class ProductQueryFactory {

    public NativeQuery activeProducts(String tenantId, String text, int page, int size) {
        return NativeQuery.builder()
            .withQuery(q -> q.bool(b -> {
                b.filter(f -> f.term(t -> t
                    .field("deleted")
                    .value(false)
                ));
                b.filter(f -> f.term(t -> t
                    .field("tenantId")
                    .value(tenantId)
                ));

                if (text != null && !text.isBlank()) {
                    b.must(m -> m.multiMatch(mm -> mm
                        .query(text)
                        .fields("name^3", "description")
                    ));
                }
                return b;
            }))
            .withPageable(PageRequest.of(page, size))
            .build();
    }
}
```

Đây là ví dụ dùng Java API Client builder được Spring Data Elasticsearch tích hợp; cú pháp lambda cụ thể phụ thuộc version. Ý tưởng quan trọng là filter soft delete và tenant được tạo ở server, không lấy từ raw query của client.

### Không nối filter vào chuỗi do người dùng nhập

Không làm:

```java
String query = userQuery + " AND deleted:false";
```

Nếu user query có cú pháp boolean, dấu ngoặc hoặc field expression, việc nối chuỗi có thể thay đổi ý nghĩa query. Đặt query người dùng trong một nhánh con của `bool.must`, còn `deleted=false` nằm trong `bool.filter` do server quản lý.

## 7. Không có global soft-delete filter tự động

Spring Data Elasticsearch cung cấp repository abstraction và Query API, nhưng không tự áp dụng một điều kiện `deleted=false` cho tất cả method của repository. Khác với một số ORM có filter toàn cục ở session/entity level, query Elasticsearch được gửi theo cấu trúc cụ thể do repository hoặc ứng dụng tạo.

Do đó, cần chọn một cách tổ chức rõ ràng:

- Repository method riêng có hậu tố `AndDeletedFalse` cho các truy vấn đơn giản.
- Custom repository fragment để tập trung query phức tạp.
- Query factory dùng chung cho filter bắt buộc.
- Application service/facade giới hạn quyền truy cập trực tiếp vào repository.
- Test contract cho mọi endpoint/query type để xác nhận filter luôn có mặt.

Không chỉ dựa vào code review hoặc quy ước tên method. Một test integration với document đã xóa có thể phát hiện endpoint nào quên filter.

## 8. Search, count và aggregation phải nhất quán

Nếu search loại document đã xóa nhưng count hoặc aggregation không loại, giao diện có thể hiển thị số tổng không khớp với danh sách.

Ví dụ query aggregation:

```json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "deleted": false } },
        { "term": { "tenantId": "tenant-42" } }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "categoryId"
      }
    }
  }
}
```

Filter đặt ở query cấp ngoài áp dụng cho cả hits và aggregations trong request. Nếu dùng `global` aggregation hoặc filter aggregation riêng, phải kiểm tra semantics vì `global` có thể bỏ qua query filter ở cấp ngoài. Không dùng aggregation đặc biệt mà quên thêm điều kiện soft delete và tenant vào bucket scope.

Các endpoint `count`, thống kê dashboard, facet, suggestion và export phải dùng cùng chính sách. Nếu có một endpoint quản trị muốn tính cả bản ghi đã xóa, hãy đặt tên và quyền riêng thay vì vô tình bỏ filter.

## 9. Autocomplete, suggestion và các đường đọc phụ

Autocomplete thường được triển khai bằng completion suggester, prefix query hoặc một index phụ. Nếu dữ liệu nguồn bị xóa mềm nhưng suggestion index không được cập nhật, tên bản ghi đã xóa vẫn có thể xuất hiện trong gợi ý.

Khi soft delete xảy ra, cần:

- Cập nhật document projection chứa suggestion.
- Loại document đã xóa khỏi truy vấn suggestion nếu index lưu trạng thái.
- Cập nhật index phụ hoặc cache chứa từ khóa.
- Xử lý event đồng bộ tới mọi read model có liên quan.
- Kiểm tra autocomplete và search trong cùng test case.

Không chỉ kiểm thử endpoint `/search`; hãy kiểm tra tất cả chức năng có thể tiết lộ tên, ID hoặc metadata của document.

## 10. Xóa mềm qua Spring Data service

Một service đơn giản có thể tìm document đang active, cập nhật trạng thái và lưu lại:

```java
import java.time.Clock;
import java.time.Instant;

public class ProductLifecycleService {

    private final ProductRepository repository;
    private final Clock clock;

    public ProductLifecycleService(ProductRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public ProductDocument softDelete(
            String id,
            String tenantId,
            String actor) {

        ProductDocument product = repository
            .findByIdAndTenantIdAndDeletedFalse(id, tenantId)
            .orElseThrow(() -> new ProductNotFoundException(id));

        product.setDeleted(true);
        product.setDeletedAt(Instant.now(clock));
        product.setDeletedBy(actor);
        product.setDeleteReason("USER_REQUEST");

        return repository.save(product);
    }
}
```

Đoạn code minh họa luồng đồng bộ. Trong hệ thống có cập nhật đồng thời, cần bảo vệ thao tác bằng version/optimistic concurrency hoặc conditional update để tránh ghi đè thay đổi khác giữa lúc đọc và lưu. Nếu Elasticsearch là projection từ database, thao tác xóa phải bắt đầu ở nguồn chuẩn; projector nhận event rồi cập nhật document tìm kiếm.

### Xóa mềm nên idempotent

Nếu cùng một yêu cầu xóa được gửi lại, hệ thống nên có semantics rõ ràng. Có thể:

- Trả kết quả hiện trạng nếu document đã được xóa.
- Trả not-found cho API chỉ thao tác trên active document.
- Ghi nhận một event xóa duy nhất theo command/event ID.

Không cập nhật lại `deletedAt` mỗi lần retry nếu thời điểm xóa đầu tiên cần được giữ để tính retention. Lưu thời điểm ban đầu và tránh tạo audit event trùng.

## 11. Restore document đã xóa

Nếu nghiệp vụ cho phép khôi phục, restore cần là một thao tác riêng có authorization. Không nên cho client gửi trực tiếp `deleted=false` qua generic update endpoint.

Ví dụ:

```java
public ProductDocument restore(String id, String tenantId, String actor) {
    ProductDocument product = repository
        .findByIdAndTenantIdAndDeletedTrue(id, tenantId)
        .orElseThrow(() -> new ProductNotFoundException(id));

    if (product.getRetentionUntil() != null
            && Instant.now(clock).isAfter(product.getRetentionUntil())) {
        throw new RestoreWindowExpiredException(id);
    }

    product.setDeleted(false);
    product.setDeletedAt(null);
    product.setDeletedBy(null);
    product.setDeleteReason(null);

    return repository.save(product);
}
```

Ví dụ này giả định policy lưu `retentionUntil` và chỉ restore trong cửa sổ cho phép. Trong thực tế, có thể cần giữ lịch sử deletion trong audit event riêng thay vì xóa metadata khỏi document. Nếu giữ `deletedAt` sau restore để làm lịch sử, hãy dùng field khác như `lastDeletedAt` hoặc event log để tránh mâu thuẫn với invariant trạng thái hiện tại.

### Restore có thể xung đột với ID mới

Trong thời gian document đã xóa, có thể một document khác được tạo lại với cùng ID nghiệp vụ. Cần định nghĩa rõ restore có được phép ghi đè hay phải từ chối. Version, unique key và quy tắc nguồn chuẩn phải quyết định hành vi; không tự động restore bằng `save()` nếu có nguy cơ thay thế một bản ghi mới.

## 12. Optimistic concurrency khi xóa và restore

Hai thao tác có thể xảy ra đồng thời:

1. Người dùng A cập nhật tên sản phẩm.
2. Người dùng B soft delete sản phẩm.
3. Cả hai đọc cùng một version.
4. Một thao tác ghi trước; thao tác còn lại có thể ghi đè trạng thái hoặc dữ liệu nếu không có concurrency control.

Spring Data Elasticsearch hỗ trợ versioning qua `@Version` ở các phiên bản phù hợp. Khi version conflict, service cần đọc lại trạng thái và quyết định theo nghiệp vụ; không retry mù quáng bằng object cũ.

Với API Elasticsearch trực tiếp, có thể dùng `if_seq_no` và `if_primary_term` cho optimistic concurrency. Các token này thuộc Elasticsearch document concurrency, khác với `sourceVersion` do domain service quản lý.

Đối với xóa từ nguồn chuẩn, transaction nguồn cần cập nhật trạng thái và phát event qua outbox/CDC. Projector phải chống event cũ ghi đè trạng thái mới.

## 13. Filter nhất quán cho repository và custom query

Với query builder, có thể định nghĩa helper tạo filter dùng chung:

```java
private Query filterActiveTenant(String tenantId) {
    return NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
            .filter(f -> f.term(t -> t.field("deleted").value(false)))
            .filter(f -> f.term(t -> t.field("tenantId").value(tenantId)))
        ))
        .build();
}
```

Đây chỉ là query fragment minh họa; tùy cách xây query phức tạp, nên tạo hàm nhận builder hoặc một query factory trả về phần điều kiện thay vì cố ghép hai `Query` object độc lập.

Với custom repository fragment, có thể gom mọi thao tác search theo tenant vào một nơi:

```java
public interface ProductSearchRepository {
    SearchPage<ProductDocument> searchActive(
        String tenantId,
        ProductSearchCriteria criteria);
}
```

Implementation chịu trách nhiệm tạo `bool.filter` gồm `deleted=false`, tenant scope và filter nghiệp vụ. Controller và service không tự tạo raw query ở nhiều nơi.

### Không tạo nhiều cách diễn giải trạng thái

Tránh một endpoint dùng `deleted=false`, endpoint khác dùng `deletedAt` không tồn tại, endpoint khác lại dùng `status != DELETED`. Nếu có nhiều field biểu thị cùng trạng thái, cần một invariant và một mapper duy nhất để chúng không lệch nhau.

## 14. Query quản trị để xem bản ghi đã xóa

Một số chức năng cần xem dữ liệu đã xóa, ví dụ thùng rác hoặc trang audit. Không nên bỏ filter trong endpoint chung rồi để client quyết định có muốn xem deleted hay không.

Thiết kế API tách biệt:

- `searchActive`: chỉ trả document `deleted=false`.
- `searchDeleted`: chỉ trả document `deleted=true`, yêu cầu role quản trị phù hợp.
- `searchAllForAudit`: có thể trả cả hai trạng thái, quyền rất hạn chế và có log audit.

Ví dụ filter cho thùng rác:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "deleted": true } },
        { "term": { "tenantId": "tenant-42" } }
      ]
    }
  }
}
```

Quyền xem dữ liệu đã xóa phải được kiểm tra ở server. Không dựa vào việc endpoint có tên `/deleted` để coi nó đã được bảo vệ.

## 15. Retention policy là gì?

Retention policy xác định dữ liệu được giữ trong bao lâu, khi nào được ẩn, khi nào được archive và khi nào phải xóa. Policy có thể khác nhau theo loại dữ liệu, tenant, khu vực pháp lý, hợp đồng hoặc mục đích xử lý.

Một chính sách nên trả lời:

- Dữ liệu nào thuộc phạm vi retention?
- Mốc bắt đầu tính thời hạn là created time, closed time hay deleted time?
- Thời gian giữ tối thiểu/tối đa là bao lâu?
- Có legal hold hoặc ngoại lệ không?
- Sau thời hạn, dữ liệu bị archive, anonymize hay hard delete?
- Dữ liệu liên quan ở index phụ, cache, snapshot và log được xử lý thế nào?
- Ai được phép thay đổi policy và ai được phép purge?
- Làm sao chứng minh job đã xử lý đủ dữ liệu?

Không nên dùng một TTL chung cho mọi document nếu dữ liệu có nghĩa vụ lưu trữ khác nhau.

## 16. Tách retention window khỏi thời điểm soft delete

Thời điểm xóa và thời điểm được purge có thể khác nhau. Ví dụ document được đánh dấu xóa hôm nay nhưng được giữ 30 ngày để người dùng khôi phục.

Có thể tính:

\[
\text{retentionUntil} = \text{deletedAt} + \text{recoveryWindow}
\]

Hoặc policy dựa trên ngày đóng hồ sơ, ngày hết hợp đồng hay timestamp nguồn khác. Hãy ghi rõ mốc tính retention trong model/policy.

Ví dụ:

```java
Instant deletedAt = Instant.now(clock);
Instant retentionUntil = deletedAt.plus(Duration.ofDays(30));

document.setDeleted(true);
document.setDeletedAt(deletedAt);
document.setRetentionUntil(retentionUntil);
```

Đây là ví dụ cửa sổ khôi phục 30 ngày, không phải khuyến nghị mặc định. Policy thực tế phải được xác định bởi yêu cầu nghiệp vụ và quy định áp dụng.

### Dùng UTC và kiểu date nhất quán

Lưu timestamp dưới dạng UTC (`Instant`) và mapping Elasticsearch `date` phù hợp. Không tính retention bằng chuỗi ngày locale hoặc giờ địa phương không có timezone. Khi hiển thị cho người dùng, chuyển sang timezone phù hợp ở tầng presentation.

## 17. Elasticsearch không tự xóa document theo field date

Việc mapping một field `expiresAt` hoặc `retentionUntil` thành `date` không khiến Elasticsearch tự động xóa document khi đến thời điểm đó. Field date chỉ được lưu và có thể dùng trong query.

Để purge document hết hạn, cần một cơ chế chủ động:

- Scheduled job chạy query theo `retentionUntil` rồi delete.
- Worker nhận retention event và xóa theo ID.
- Delete By Query cho tập document thỏa điều kiện.
- Index Lifecycle Management (ILM) hoặc data stream lifecycle cho dữ liệu được tổ chức theo index/time-based backing index phù hợp.

Không nhầm với TTL tự động của một số database khác. Không dựa vào mapping date để cho rằng dữ liệu đã được xóa khi hết hạn.

## 18. Hard purge theo thời hạn với Delete By Query

Nếu cần xóa vật lý các document đã soft delete và hết thời hạn khôi phục, có thể dùng `_delete_by_query`:

```http
POST /products-write/_delete_by_query?conflicts=proceed&wait_for_completion=false
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        { "term": { "deleted": true } },
        { "term": { "legalHold": false } },
        {
          "range": {
            "retentionUntil": {
              "lt": "2026-10-14T00:00:00Z"
            }
          }
        }
      ]
    }
  }
}
```

Ví dụ dùng mốc cutoff cố định để minh họa. Trong job thực tế, tính cutoff từ policy bằng `Clock` và truyền timestamp đã chuẩn hóa. Nếu `legalHold` có thể thiếu trên document cũ, query phải xử lý trạng thái thiếu theo policy thay vì mặc định mọi document đều có `false`.

`wait_for_completion=false` yêu cầu Elasticsearch chạy tác vụ bất đồng bộ và trả task ID. Job cần poll task, ghi nhận số document đã xóa, version conflict, failure và trạng thái cuối. `conflicts=proceed` cho phép tiếp tục khi gặp version conflict; nó không có nghĩa mọi document đủ điều kiện đều chắc chắn đã xóa.

### Delete By Query không phải thao tác nguyên tử

Delete By Query tìm document rồi phát các delete operation theo batch. Document có thể thay đổi trong lúc job chạy; version conflict và failure cần được xử lý. Kết quả có thể có một phần thành công. Job phải kiểm tra response/task result và có quy trình retry/đối soát.

### Giới hạn tải của purge job

Với index lớn, dùng throttle (`requests_per_second`) và slices phù hợp để tránh purge chiếm hết tài nguyên search/index. Chạy theo batch hoặc partition, theo dõi task progress và tránh chạy nhiều purge job chồng lấn không kiểm soát.

## 19. Legal hold và ngoại lệ retention

Một số hồ sơ không được purge dù đã đến ngày hết hạn thông thường, ví dụ đang có tranh chấp hoặc nghĩa vụ lưu trữ đặc biệt. Có thể biểu diễn `legalHold=true` hoặc quản lý hold ở hệ thống policy riêng.

Điều quan trọng:

- Hold phải có owner và lý do.
- Có thời điểm bắt đầu/kết thúc hoặc cơ chế review.
- Chỉ role có thẩm quyền được bật/tắt hold.
- Purge query phải loại document đang hold.
- Thay đổi hold cần audit.
- Job purge phải đọc trạng thái hold mới nhất và xử lý concurrency.

Nếu hold được quản lý ở database nguồn, không chỉ dựa vào một field projection có thể bị trễ. Với purge quan trọng, xác nhận policy tại nguồn chuẩn hoặc đồng bộ trạng thái hold đủ chặt trước khi xóa.

## 20. Retention theo document và ILM theo index

Elasticsearch ILM (Index Lifecycle Management) quản lý vòng đời **index** dựa trên phase/action như rollover, shrink, force merge, migrate, searchable snapshot và delete. Nó không phải cơ chế mặc định để xóa từng document riêng lẻ theo `deletedAt`.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Xóa một document đã hết retention | Delete API hoặc Delete By Query |
| Xóa nhiều document theo field `retentionUntil` | Scheduled purge job / Delete By Query |
| Xóa toàn bộ index dữ liệu cũ theo tuổi index | ILM |
| Dữ liệu append-only theo thời gian trong data stream | Data stream lifecycle/ILM theo backing index |
| Giữ dữ liệu nóng rồi chuyển sang cold/frozen | ILM phase phù hợp |

Nếu index chứa document của nhiều tenant và nhiều thời điểm, ILM delete index có thể xóa cả document còn hạn. Chỉ dùng index-level retention khi cách partition dữ liệu bảo đảm toàn bộ index có cùng policy và có thể xóa cùng lúc.

### Ví dụ index theo tháng

```text
events-2026.09
events-2026.10
events-2026.11
```

Nếu mọi event trong một backing index có retention 90 ngày tính từ thời điểm tạo và không có legal hold riêng, index-level lifecycle có thể phù hợp. Nếu mỗi event có thời hạn khác nhau hoặc có hold, cần cơ chế document-level hoặc tách index theo policy.

## 21. Xóa dữ liệu liên quan và nhiều index

Một sản phẩm có thể xuất hiện trong:

- Index tìm kiếm chính.
- Index autocomplete.
- Index analytics/rollup.
- Index lịch sử hoặc audit.
- Cache của application.
- Search projection theo tenant/locale.

Soft delete hoặc purge chỉ ở index chính không đảm bảo dữ liệu đã biến mất khỏi các read model khác. Cần xác định danh sách projection liên quan và phát event có thể được từng projector xử lý.

Ví dụ event:

```json
{
  "eventId": "evt-9010",
  "aggregateId": "p-100",
  "aggregateVersion": 13,
  "eventType": "ProductSoftDeleted",
  "deletedAt": "2026-11-13T10:30:00Z"
}
```

Projector cập nhật trạng thái ở index chính, projector suggestion loại gợi ý, application cache evict key liên quan và analytics projection xử lý theo policy riêng. Với hard purge, event cần chỉ rõ phạm vi dữ liệu phải xóa và theo dõi hoàn tất ở từng hệ thống.

## 22. Đồng bộ soft delete qua Outbox/CDC

Nếu database là nguồn chuẩn và Elasticsearch là read model, thao tác xóa nên bắt đầu ở database:

```text
Delete command
    |
    v
Source DB transaction
    +--> set deleted=true, deleted_at=...
    +--> insert ProductSoftDeleted outbox event
    |
    v
Commit
    |
    v
Outbox publisher / CDC
    |
    v
Projection consumer
    |
    v
Update Elasticsearch document
```

Ghi trạng thái và outbox event trong cùng transaction giúp tránh trường hợp DB commit nhưng event không được ghi nhận. Projector cần idempotent vì event có thể được giao lại.

### Event ordering và version

Giả sử ProductUpdated version 12 đến sau ProductSoftDeleted version 13. Nếu projector áp dụng event 12 sau, nó có thể làm document sống lại. Hãy lưu `sourceVersion` và từ chối event cũ hơn version đã áp dụng; khi cần, dùng conditional update/serialization theo aggregate ID để kiểm tra và ghi nguyên tử.

### Soft delete và tombstone

Nếu hard delete document ngay, version marker có thể biến mất. Một event cũ đến trễ có thể tạo lại document. Tombstone giữ lại ID, version và trạng thái deleted trong một khoảng thời gian đủ dài để projector nhận biết event cũ và không hồi sinh dữ liệu.

Sau khi hết thời gian replay/retention và không còn event cũ có thể đến, tombstone có thể được purge theo policy.

## 23. Độ nhất quán và thời điểm dữ liệu bị ẩn

Trong kiến trúc eventual consistency, database có thể đánh dấu deleted ngay nhưng Elasticsearch chỉ cập nhật sau khi event được xử lý. Trong khoảng thời gian đó, search có thể vẫn trả document.

Hãy xác định yêu cầu:

- **Ẩn eventual:** chấp nhận một khoảng trễ ngắn; search projection cập nhật qua outbox/CDC.
- **Ẩn gần đồng bộ:** command chờ projector cập nhật và xác nhận search visibility, nếu SLA cho phép.
- **Thu hồi quyền ngay:** API kiểm tra trạng thái ở nguồn chuẩn hoặc authorization layer trước khi trả dữ liệu, không chỉ dựa vào projection.

Với dữ liệu nhạy cảm hoặc thao tác thu hồi quyền, không nên chỉ chờ eventual filter trong Elasticsearch. Một search result cũ có thể xuất hiện trong khoảng đồng bộ; API cần xác nhận quyền/trạng thái ở nguồn có thẩm quyền hoặc dùng cơ chế đồng bộ được thiết kế cho yêu cầu đó.

### Write acknowledgement không đồng nghĩa search visibility

Sau khi cập nhật document, Elasticsearch có thể chưa refresh nên query search chưa thấy thay đổi ngay. Nếu cần đo/đợi visibility, dùng refresh policy phù hợp (`wait_for` trong use case cần thiết) hoặc một cơ chế xác nhận canary. Không ép refresh cho mọi thao tác nếu không cần.

## 24. Bulk soft delete

Khi cần đánh dấu nhiều document, có thể dùng Bulk Update hoặc Update By Query. Bulk Update phù hợp khi đã biết ID và cần cập nhật field cho từng document:

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "update": { "_id": "p-100" } }
{ "doc": { "deleted": true, "deletedAt": "2026-11-13T10:30:00Z" } }
{ "update": { "_id": "p-101" } }
{ "doc": { "deleted": true, "deletedAt": "2026-11-13T10:30:00Z" } }
```

Bulk Update vẫn có partial failures; kiểm tra từng item. Dùng timestamp nhất quán cho cùng một command nếu muốn audit biểu thị một lần thao tác.

### Update By Query

Nếu cần đánh dấu tất cả document thỏa điều kiện:

```http
POST /products/_update_by_query?conflicts=proceed&wait_for_completion=false
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "ARCHIVED" } },
        { "term": { "deleted": false } }
      ]
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.deleted = true; ctx._source.deletedAt = params.deletedAt;",
    "params": {
      "deletedAt": "2026-11-13T10:30:00Z"
    }
  }
}
```

Đây là thao tác cập nhật hàng loạt có thể chạy bất đồng bộ, phát sinh version conflict và partial failure. Query phải giới hạn đúng tenant/status; script phải được ứng dụng kiểm soát. Theo dõi task và xác nhận số document đã cập nhật.

Không dùng Update By Query để thay thế transaction nguồn chuẩn nếu Elasticsearch chỉ là projection. Trong kiến trúc đó, hãy cập nhật nguồn chuẩn và để projector đồng bộ trạng thái.

## 25. Cache và soft delete

Application cache có thể tiếp tục trả document cũ sau khi Elasticsearch đã đánh dấu deleted. Khi soft delete thành công, cần xem xét:

- Evict cache chi tiết theo ID.
- Evict hoặc version hóa search page cache.
- Evict autocomplete/suggestion cache.
- Xóa cache theo tenant/namespace nếu không thể xác định mọi key bị ảnh hưởng.
- Không cache response chứa deleted record quá TTL cho phép.

Cache key phải chứa tenant và authorization scope phù hợp. Nếu cache một response trước khi filter soft delete, không được tái sử dụng nó cho endpoint hoặc user có policy khác.

Với event-driven architecture, có thể phát event `ProductSoftDeleted` để các cache consumer evict. Tuy nhiên, event eviction cũng eventual; endpoint nhạy cảm cần xác nhận trạng thái ở nguồn chuẩn.

## 26. Retention và dữ liệu nhạy cảm

Soft delete giữ document trong index, nên không phù hợp làm biện pháp duy nhất khi yêu cầu là xóa dữ liệu cá nhân hoặc bí mật. Nếu cần xóa theo yêu cầu, phải xác định phạm vi gồm:

- Source database.
- Elasticsearch index và mọi projection phụ.
- Cache trong JVM/Redis.
- Broker/retry queue/DLQ nếu payload chứa dữ liệu.
- Log và trace nếu đã ghi payload/PII.
- Snapshot/backup theo chính sách retention tương ứng.
- Export hoặc bản sao do downstream service lưu.

Elasticsearch snapshot có thể chứa dữ liệu ở thời điểm snapshot. Xóa document khỏi index hiện tại không tự động sửa snapshot cũ. Quy trình backup retention, expiry và restore phải được thiết kế cùng chính sách xóa.

Nếu cần giữ audit về việc đã xóa mà không giữ nội dung nhạy cảm, lưu audit event tối thiểu như ID nội bộ đã được bảo vệ, thời điểm, actor code và action, theo retention riêng. Không sao chép nguyên payload đã xóa vào audit log.

## 27. Phân quyền với document đã xóa và purge

Các quyền nên được tách rõ:

- Người dùng thường: chỉ đọc document active trong tenant được phép.
- Người dùng có quyền khôi phục: đọc thùng rác và restore trong cửa sổ cho phép.
- Quản trị viên: có thể xem trạng thái xóa theo phạm vi được cấp.
- Retention worker: chỉ được truy vấn và purge dữ liệu thỏa policy.
- Audit reader: đọc audit metadata, không nhất thiết đọc payload đã xóa.

Không cấp quyền `delete_by_query` rộng cho mọi application user. Credential của retention worker nên có quyền tối thiểu trên alias/index đích và được quản lý riêng. Log purge cần ghi task ID, policy version, cutoff, số document và kết quả, nhưng không log nội dung document.

## 28. Tenant isolation trong mọi filter

Trong multi-tenant index, filter soft delete và tenant phải luôn được kết hợp:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "deleted": false } }
      ]
    }
  }
}
```

Tenant ID nên được lấy từ principal/security context phía server. Không tin `tenantId` do client gửi nếu không kiểm tra membership/permission.

Với purge job, tenant filter cũng cần được thêm nếu job chạy theo tenant. Nếu policy purge toàn index, phải xác nhận index/alias chỉ chứa đúng phạm vi dữ liệu. Một query thiếu tenant filter có thể xóa dữ liệu của nhiều tenant.

## 29. Xử lý document cũ thiếu field `deleted`

Khi bổ sung soft delete vào index đã có dữ liệu, document cũ có thể không chứa field `deleted`. Trong Elasticsearch, `term deleted=false` không match document thiếu field đó.

Có ba hướng xử lý:

1. Reindex/backfill để mọi document cũ có `deleted=false`.
2. Trong giai đoạn chuyển tiếp, query dùng `should` để chấp nhận field thiếu hoặc false.
3. Tạo index version mới, dựng document theo schema mới rồi chuyển alias.

Ví dụ query chuyển tiếp:

```json
{
  "query": {
    "bool": {
      "filter": [
        {
          "bool": {
            "should": [
              { "term": { "deleted": false } },
              { "bool": { "must_not": { "exists": { "field": "deleted" } } } }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  }
}
```

Đây là query tương thích dữ liệu cũ trong giai đoạn migration. Sau khi backfill hoàn tất và xác nhận mọi document có field, nên chuyển về quy tắc rõ ràng `deleted=false` để giảm độ phức tạp.

Không để mỗi endpoint tự chọn cách xử lý document thiếu field. Quy tắc tương thích phải nằm trong query factory dùng chung và có ngày kết thúc migration.

## 30. Reindex và thay đổi mapping cho soft delete

Nếu mapping cũ chưa có field trạng thái hoặc cần đổi cấu trúc, có thể tạo index version mới:

```text
products-v1  <- dữ liệu cũ
products-v2  <- mapping mới + deleted/deletedAt
products-read -> products-v1 (đang phục vụ)
```

Quy trình tổng quát:

1. Tạo `products-v2` với mapping tường minh.
2. Backfill document từ nguồn chuẩn, đặt `deleted=false` cho bản ghi active.
3. Đồng bộ event mới trong lúc backfill bằng watermark/CDC/outbox.
4. Xác nhận số lượng, version và filter behavior.
5. Chuyển alias `products-read` sang index mới.
6. Giữ index cũ trong thời gian rollback phù hợp rồi mới xóa theo policy.

Không sửa mapping và query production một cách nửa chừng khiến một số document có field, một số document thiếu field mà không có migration plan.

## 31. Retention job phải có checkpoint và khả năng tiếp tục

Purge job có thể xử lý hàng triệu document và bị dừng giữa chừng. Thiết kế job nên có:

- Policy ID/version.
- Cutoff timestamp cố định cho một lần chạy.
- Index/alias scope.
- Query filter đầy đủ gồm deleted, retention, legal hold và tenant nếu cần.
- Task ID hoặc batch checkpoint.
- Số document dự kiến, đã xử lý, thất bại và còn lại.
- Retry policy cho lỗi tạm thời.
- Audit record cho lần chạy.
- Cơ chế dry-run/count trước purge nếu nghiệp vụ yêu cầu.
- Giới hạn tốc độ để bảo vệ cluster.

Không tính lại cutoff thành `now` ở mỗi batch nếu muốn một job có phạm vi ổn định. Lưu cutoff lúc job bắt đầu để retry/restart không làm thay đổi tập dữ liệu mục tiêu.

### Dry-run và kiểm tra phạm vi

Trước một purge lớn, có thể chạy count query với cùng filter để ước lượng số document đủ điều kiện. Count không thay thế kết quả thực thi vì dữ liệu có thể thay đổi giữa hai bước, nhưng giúp phát hiện nhầm index/tenant hoặc cutoff sai trước khi xóa.

Với thao tác không thể đảo ngược, nên yêu cầu phê duyệt theo quy trình vận hành của hệ thống nếu policy của tổ chức quy định. Job tự động vẫn phải ghi lại chính xác policy và phạm vi đã áp dụng.

## 32. Đo và giám sát retention

Các chỉ số hữu ích:

- Số document `deleted=true`.
- Số document đã quá `retentionUntil` nhưng chưa purge.
- Tuổi của document quá hạn cũ nhất.
- Số document đang legal hold.
- Purge throughput (documents/second).
- Purge task duration và failure count.
- Version conflict và retry count.
- Số document còn lại sau job.
- Số cache/projection consumer đã xác nhận xóa.

Không chỉ đo số document đã purge. Nếu job liên tục xóa 10.000 document nhưng mỗi ngày có 100.000 document hết hạn, backlog vẫn tăng. Theo dõi cả arrival rate của document đến hạn và processing rate của purge worker.

## 33. Kiểm thử soft delete và filter consistency

Test nên bao phủ mọi đường đọc quan trọng:

1. Document mới được tạo với `deleted=false`.
2. Soft delete đặt `deleted=true`, `deletedAt`, actor và reason đúng.
3. Search thông thường không trả document đã xóa.
4. Search theo ID không trả document đã xóa.
5. Count và aggregation loại document đã xóa.
6. Autocomplete/suggestion không trả dữ liệu đã xóa.
7. Export, pagination và batch scan áp dụng filter.
8. Endpoint quản trị chỉ trả deleted record cho role được phép.
9. Tenant A không đọc/xóa/restore document của tenant B.
10. Restore chỉ hoạt động trong policy window và không ghi đè bản ghi mới.
11. Event trùng không thay đổi `deletedAt` hoặc tạo audit event trùng ngoài ý muốn.
12. Event cũ không hồi sinh document đã xóa.
13. Purge chỉ xóa document đủ điều kiện và không xóa legal hold.
14. Document cũ thiếu field được xử lý theo migration policy.
15. Cache và index suggestion được invalidation.
16. Search visibility được xác nhận theo refresh semantics.

### Integration test với Elasticsearch

Tạo một document active và một document deleted trong index test. Gọi repository/query service thật rồi dùng search API để xác nhận chỉ document active xuất hiện. Test riêng count/aggregation và query theo ID. Với search sau khi ghi, dùng refresh policy hoặc refresh index rõ ràng; không dùng `Thread.sleep()` để chờ.

Unit test query factory có thể xác nhận cấu trúc filter, nhưng integration test mới chứng minh query thực tế loại document đã xóa theo mapping hiện tại.

## 34. Các lỗi thiết kế thường gặp

### Chỉ thêm field `deleted` mà không filter ở mọi nơi

Document vẫn xuất hiện qua endpoint hoặc aggregation quên filter. Tạo query factory/facade và test mọi read path.

### Nghĩ Spring Data tự có global soft-delete filter

Repository không tự thêm `deleted=false` cho mọi method. Dùng derived query/custom fragment và giới hạn quyền truy cập repository.

### Chỉ filter search, quên `findById`

Read-by-ID có thể trả document đã xóa. Tạo method `findByIdAndTenantIdAndDeletedFalse` hoặc service lookup tương đương.

### Quên count, aggregation và autocomplete

Danh sách có thể đúng nhưng số tổng, facet hoặc suggestion vẫn chứa document đã xóa. Áp dụng cùng policy cho mọi read model.

### Coi soft delete là xóa dữ liệu thật

Payload vẫn còn trong index và snapshot. Nếu cần xóa theo yêu cầu, phải có hard purge và phạm vi xóa rộng hơn.

### Coi field date là TTL tự động

Elasticsearch không tự xóa document chỉ vì `retentionUntil` đã qua. Cần purge job hoặc lifecycle theo index phù hợp.

### Dùng ILM để xóa document riêng lẻ

ILM quản lý index. Nếu index trộn dữ liệu còn hạn và hết hạn, xóa cả index có thể làm mất dữ liệu hợp lệ.

### Purge không loại legal hold

Query purge phải kiểm tra hold theo nguồn policy có thẩm quyền và xử lý race khi hold thay đổi.

### Event cũ làm document sống lại

Dùng source version, ordering và tombstone để chặn event cũ sau delete.

### Cache vẫn trả dữ liệu đã xóa

Evict cache liên quan, version hóa key hoặc đặt TTL theo freshness; endpoint nhạy cảm kiểm tra nguồn chuẩn.

### Dùng save toàn document cho soft delete mà không kiểm soát concurrency

Một lần save có thể ghi đè thay đổi đồng thời. Dùng version/conditional update và xử lý conflict.

## 35. Quy trình thiết kế end-to-end

Khi triển khai soft delete và retention cho một loại document:

1. Xác định nguồn dữ liệu chuẩn và service sở hữu trạng thái xóa.
2. Xác định lý do cần soft delete: restore, audit, workflow hay retention.
3. Thiết kế field `deleted`, `deletedAt`, actor/reason và retention metadata tối thiểu.
4. Định nghĩa invariant cho trạng thái và giá trị mặc định của document mới.
5. Tạo repository/service API chỉ đọc active document cho luồng thông thường.
6. Tập trung query filter để search, get-by-ID, count, aggregation, suggestion và export cùng tuân thủ.
7. Tách endpoint quản trị xem/restore dữ liệu đã xóa và kiểm tra authorization.
8. Dùng outbox/CDC để cập nhật search projection và cache nếu Elasticsearch là read model.
9. Dùng version/order/tombstone để event cũ không ghi đè hoặc hồi sinh document.
10. Định nghĩa retention window, legal hold và thời điểm purge theo từng loại dữ liệu.
11. Chọn document-level purge hay index-level ILM dựa trên cách partition dữ liệu.
12. Chạy purge có checkpoint, throttle, task monitoring và audit.
13. Kiểm thử filter consistency và search visibility với Elasticsearch thật.
14. Theo dõi số deleted, quá hạn, backlog purge, sync lag và cache invalidation.

## 36. Kết luận

Xóa mềm là một trạng thái nghiệp vụ, không phải xóa dữ liệu khỏi Elasticsearch. Một document thường có thể dùng `deleted`, `deletedAt`, actor/reason và retention metadata; các truy vấn thông thường phải áp dụng `deleted=false` cùng tenant/security filters. Spring Data Elasticsearch không tự thêm global soft-delete filter, nên cần repository method, custom query factory và service facade để bảo đảm search, get-by-ID, count, aggregation, autocomplete, export và cache đều tuân thủ cùng quy tắc.

Retention policy phải xác định mốc tính thời hạn, cửa sổ khôi phục, legal hold và hành động sau khi hết hạn. Elasticsearch không tự xóa document theo field date; dùng purge job/Delete By Query cho document-level retention, còn ILM/data stream lifecycle phù hợp với dữ liệu được tổ chức theo index có cùng vòng đời. Nếu Elasticsearch là projection, cập nhật trạng thái ở nguồn chuẩn qua outbox/CDC, xử lý event trùng/sai thứ tự bằng version và tombstone, rồi theo dõi search visibility. Với dữ liệu nhạy cảm cần xóa thật, phải xem xét index phụ, cache, queue, log và snapshot theo chính sách tương ứng.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Spring Data Elasticsearch – ElasticsearchOperations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Elasticsearch – Delete API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete)
- [Elasticsearch – Delete By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query)
- [Elasticsearch – Update By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query)
- [Elasticsearch – Index Lifecycle Management](https://www.elastic.co/docs/manage-data/lifecycle/index-lifecycle-management)
- [Elasticsearch – Data stream lifecycle](https://www.elastic.co/docs/manage-data/lifecycle/data-stream)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Elasticsearch – Refresh API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-refresh)
