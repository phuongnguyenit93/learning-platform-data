# Kiểm thử truy cập trái phép và rò rỉ dữ liệu chéo

Một ứng dụng dùng Spring Data Elasticsearch có thể trả đúng kết quả tìm kiếm nhưng vẫn mắc lỗi bảo mật nếu người dùng xem được dữ liệu thuộc tenant khác, truy cập tài liệu bằng ID đoán được hoặc suy ra thông tin qua aggregation và metadata. Những lỗi này thường xuất hiện khi backend chỉ kiểm tra đăng nhập mà quên giới hạn phạm vi dữ liệu theo người dùng, tổ chức hoặc quyền nghiệp vụ.

**Kiểm thử truy cập trái phép** xác nhận người dùng không có quyền không thể đọc, sửa, xóa hoặc suy ra dữ liệu ngoài phạm vi được cấp. **Kiểm thử rò rỉ dữ liệu chéo** xác nhận mọi đường truy cập đều giữ đúng ranh giới tenant, kể cả những đường ít được chú ý như get-by-ID, count, aggregation, autocomplete, export, bulk update và cache.

Bài này đặt trong ngữ cảnh Spring Data Elasticsearch, Spring Security và hệ thống nhiều tenant. Ví dụ sử dụng index products với trường tenantId. Mục tiêu là xây dựng bộ kiểm thử có thể phát hiện lỗi phân quyền ở tầng HTTP, service, query và Elasticsearch, đồng thời bảo đảm test chứng minh được cả trường hợp được phép lẫn trường hợp bị từ chối.

## 1. Xác định ranh giới bảo mật trước khi viết test

Trước khi kiểm thử, cần mô tả rõ ai được phép làm gì và trên dữ liệu nào. Một hệ thống nhiều tenant thường có các khái niệm:

- **Authentication:** xác định người gọi là ai.
- **Authorization:** xác định người đó được phép thực hiện hành động nào.
- **Tenant isolation:** giới hạn dữ liệu mà người gọi được phép nhìn thấy hoặc thay đổi.
- **Object-level authorization:** kiểm tra quyền trên một tài liệu cụ thể.
- **Field-level authorization:** giới hạn các trường có thể đọc hoặc sửa.
- **Function-level authorization:** giới hạn thao tác như search, export, delete hoặc quản trị index.

Một người dùng đã đăng nhập vẫn có thể không được xem một sản phẩm cụ thể. Một người dùng có quyền đọc sản phẩm trong tenant A vẫn không được đọc sản phẩm thuộc tenant B.

Ví dụ ma trận quyền:

| Principal | Tenant | Search sản phẩm | Xem chi tiết | Sửa | Xóa |
|---|---|---:|---:|---:|---:|
| Alice | tenant-a | Có | Trong tenant A | Có theo role | Có theo role |
| Bob | tenant-b | Có | Trong tenant B | Có theo role | Có theo role |
| Guest | Không có | Không | Không | Không | Không |
| Support | Theo quyền hỗ trợ | Theo chính sách | Theo chính sách | Có thể bị giới hạn | Không mặc định |

Ma trận này là hợp đồng để viết test. Không nên suy ra quyền chỉ từ tên role hoặc từ việc endpoint trả HTTP 200 trong một test happy path.

## 2. Phân biệt 401, 403 và 404

Các trạng thái HTTP thường có ý nghĩa:

- **401 Unauthorized:** request chưa được xác thực hoặc credential không hợp lệ.
- **403 Forbidden:** người gọi đã được xác thực nhưng không có quyền thực hiện hành động.
- **404 Not Found:** tài nguyên không tồn tại hoặc ứng dụng cố ý không tiết lộ tài nguyên có tồn tại ngoài phạm vi người gọi.

Với endpoint truy cập theo ID, một ứng dụng có thể trả 404 cho cả hai trường hợp: ID không tồn tại và ID thuộc tenant khác. Cách này giảm khả năng dò ID của tenant khác. Một ứng dụng khác có thể trả 403 khi muốn biểu đạt rõ quyền bị từ chối. Cả hai chính sách đều có thể hợp lệ nếu được áp dụng nhất quán và không làm lộ dữ liệu.

Test cần khẳng định chính sách đã chọn. Không nên viết test chấp nhận tùy tiện cả 403 lẫn 404 nếu yêu cầu sản phẩm đã quy định một hành vi cụ thể.

| Tình huống | Kết quả thường mong đợi |
|---|---|
| Không gửi token | 401 |
| Token hết hạn hoặc sai chữ ký | 401 |
| Đã đăng nhập nhưng thiếu authority | 403 |
| ID không tồn tại | 404 |
| ID thuộc tenant khác | 404 hoặc 403 theo chính sách |
| Tenant hợp lệ và có quyền | 200 |

## 3. Xây dựng dữ liệu test có thể phát hiện rò rỉ chéo

Một bộ test chỉ tạo một tenant sẽ không thể phát hiện lỗi cross-tenant. Hãy chuẩn bị ít nhất hai tenant với dữ liệu có dấu hiệu phân biệt rõ ràng.

| ID | tenantId | name | category | status |
|---|---|---|---|---|
| p-a-001 | tenant-a | Alpha Keyboard | keyboard | ACTIVE |
| p-a-002 | tenant-a | Alpha Mouse | mouse | ACTIVE |
| p-b-001 | tenant-b | Beta Keyboard | keyboard | ACTIVE |
| p-b-002 | tenant-b | Beta Monitor | monitor | ACTIVE |

Dữ liệu nên có ID khác nhau giữa hai tenant, tên và SKU dễ nhận biết, một số trường nhạy cảm chỉ dành cho role nhất định, trạng thái ACTIVE và INACTIVE, category trùng nhau ở nhiều tenant để phát hiện aggregation bị cộng chéo, và từ khóa trùng nhau để phát hiện suggest hoặc autocomplete rò rỉ.

Dùng dữ liệu mồi có giá trị đặc trưng như BETA-SECRET-9281 giúp phát hiện chuỗi rò rỉ trong response, log test hoặc thông báo lỗi.

## 4. Không tin tenantId do client tự gửi

Một lỗi phổ biến là API nhận tenantId từ query parameter:

~~~http
GET /products?tenantId=tenant-a
~~~

Nếu backend dùng trực tiếp giá trị này làm filter, người dùng tenant A có thể đổi thành tenant B để truy cập dữ liệu ngoài quyền.

Tenant context phải được suy ra từ principal đã xác thực hoặc một cơ chế ủy quyền đáng tin cậy. Ví dụ JWT có claim tenant_id đã được xác minh chữ ký:

~~~java
String tenantId = jwt.getClaimAsString("tenant_id");
~~~

Controller có thể nhận JWT principal và chuyển tenant context vào service:

~~~java
@GetMapping
public Flux<ProductView> search(
        @AuthenticationPrincipal Jwt jwt,
        @RequestParam String q) {

    String tenantId = jwt.getClaimAsString("tenant_id");
    return productService.searchForTenant(tenantId, q);
}
~~~

Không dùng tenantId do client gửi để thay thế claim. Nếu API có tham số tenant để người dùng quản trị chuyển tenant, phải kiểm tra authority cho phép thao tác đó và xác minh tenant đích thuộc phạm vi được cấp.

Test cần gửi tenantId giả mạo trong query/body/header và chứng minh backend vẫn chỉ dùng tenant từ principal.

## 5. Bảo vệ query bằng filter bắt buộc

Với tìm kiếm Elasticsearch, tenant filter phải được thêm vào mọi query có thể trả dữ liệu nhiều tenant.

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-a"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ],
      "must": [
        {
          "match": {
            "name": "keyboard"
          }
        }
      ]
    }
  }
}
~~~

TenantId giới hạn phạm vi dữ liệu, status áp dụng điều kiện nghiệp vụ, match tìm nội dung trong phạm vi đã lọc, và filter context không làm thay đổi relevance score.

Tenant filter phải được áp dụng ở backend, không dựa vào frontend gửi thêm một clause. Không cho client truyền một Query DSL tùy ý rồi ghép tenant filter bằng logic không chắc chắn; một query do client kiểm soát có thể tạo bool.should hoặc nhánh truy vấn làm thay đổi semantics dự kiến.

Tốt nhất là xây dựng query từ các tham số nghiệp vụ đã validate và luôn thêm tenant clause ở một service/helper dùng chung.

## 6. Tạo một thành phần xây query theo tenant

Có thể tập trung logic tenant filter để các service không quên thêm điều kiện. Ví dụ với NativeQuery và Elasticsearch Java API Client builder của Spring Data Elasticsearch:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public final class TenantQueries {

    private TenantQueries() {
    }

    public static Query activeProducts(String tenantId, String text) {
        return NativeQuery.builder()
                .withQuery(q -> q.bool(b -> b
                        .filter(f -> f.term(t -> t
                                .field("tenantId")
                                .value(tenantId)
                        ))
                        .filter(f -> f.term(t -> t
                                .field("status")
                                .value("ACTIVE")
                        ))
                        .must(m -> m.match(match -> match
                                .field("name")
                                .query(text)
                        ))
                ))
                .build();
    }
}
~~~

Service nhận tenantId đã được xác thực:

~~~java
public Flux<Product> searchForTenant(
        String tenantId,
        String text) {

    Query query = TenantQueries.activeProducts(tenantId, text);

    return operations.search(query, Product.class)
            .map(SearchHit::getContent);
}
~~~

Cú pháp builder có thể khác theo phiên bản Spring Data Elasticsearch và Java API Client. Điều quan trọng là tenant filter được tạo từ principal ở server và không thể bị client ghi đè.

Nếu hệ thống có nhiều index hoặc nhiều loại tài liệu, hãy tạo các query helper tương ứng. Một helper chung không có nghĩa mọi query đều giống nhau; nó cần bảo đảm điều kiện tenant bắt buộc được gắn vào đúng query tree.

## 7. Không dùng findById một cách mù quáng trong hệ thống nhiều tenant

Repository method:

~~~java
repository.findById(id)
~~~

thường tìm theo document ID trong index. Nó không tự biết tenant hiện tại và không tự thêm điều kiện tenantId trừ khi ứng dụng có cơ chế riêng.

Đây là một nguồn IDOR (Insecure Direct Object Reference): người dùng có thể thay ID trên URL để thử đọc tài liệu thuộc tenant khác.

Ví dụ endpoint dễ mắc lỗi:

~~~java
@GetMapping("/{id}")
public Mono<Product> findById(@PathVariable String id) {
    return repository.findById(id);
}
~~~

Cách xử lý an toàn hơn là truy vấn theo cả tenant và ID, hoặc dùng một cơ chế object-level authorization đã được kiểm tra.

Ví dụ query theo tenant và productId:

~~~java
public Mono<Product> findForTenant(String tenantId, String productId) {
    Query query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                    .filter(f -> f.term(t -> t
                            .field("tenantId")
                            .value(tenantId)
                    ))
                    .filter(f -> f.term(t -> t
                            .field("productId")
                            .value(productId)
                    ))
            ))
            .withMaxResults(1)
            .build();

    return operations.search(query, Product.class)
            .next()
            .map(SearchHit::getContent);
}
~~~

Nếu productId chính là Elasticsearch _id, có thể dùng ids query kết hợp tenant filter thay vì lưu thêm productId. Hãy kiểm tra API query builder của phiên bản dự án.

Một lựa chọn khác là dùng ID có cấu trúc chứa tenant, nhưng không xem ID khó đoán là cơ chế phân quyền. ID ngẫu nhiên làm giảm khả năng dò tìm, song backend vẫn phải xác thực quyền.

## 8. Kiểm thử IDOR bằng cách thay ID

Một test IDOR cần tạo hai principal thuộc hai tenant khác nhau và truy cập chéo ID.

Kịch bản:

1. Tạo p-a-001 thuộc tenant-a.
2. Tạo p-b-001 thuộc tenant-b.
3. Gọi endpoint chi tiết với JWT tenant-a và ID p-a-001: phải thành công.
4. Gọi endpoint chi tiết với JWT tenant-a và ID p-b-001: phải bị từ chối theo chính sách.
5. Gọi endpoint với một ID không tồn tại: phải trả kết quả tương ứng với chính sách 404.
6. Kiểm tra response không chứa bất kỳ trường nào của p-b-001.

Test không nên chỉ xác nhận status 403/404. Cần kiểm tra body không chứa tên, SKU, tenantId, giá, địa chỉ hoặc metadata của tài liệu ngoài phạm vi.

Ví dụ kiểm thử bằng WebTestClient:

~~~java
webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
                .subject("alice")
                .claim("tenant_id", "tenant-a")
                .claim("scope", "products.read")
        ))
        .get()
        .uri("/products/p-b-001")
        .exchange()
        .expectStatus().isNotFound()
        .expectBody()
        .jsonPath("$").doesNotExist();
~~~

Ví dụ này minh họa cách thiết lập JWT test; cấu hình authority mapping và response body thực tế phụ thuộc ứng dụng. Nếu endpoint trả ProblemDetail, hãy kiểm tra body chỉ có mã lỗi chung, không có source hoặc thông tin nội bộ.

## 9. Kiểm thử search không trả dữ liệu tenant khác

Test tìm kiếm cần xác nhận cả tập ID lẫn metadata tổng hợp.

~~~java
@Test
void searchReturnsOnlyProductsFromAuthenticatedTenant() {
    StepVerifier.create(
            service.searchForTenant("tenant-a", "keyboard")
    )
    .expectNextMatches(product ->
            "p-a-001".equals(product.getId())
    )
    .verifyComplete();
}
~~~

Test này nên chạy với dữ liệu test đã được index và refresh phù hợp. Nếu search có thể trả nhiều kết quả, hãy thu thập danh sách test ở phạm vi nhỏ rồi assert tập ID chính xác, không chỉ assert rằng có ít nhất một kết quả.

Bổ sung các test:

- Tenant A không nhận sản phẩm tenant B dù cùng từ khóa.
- Tenant A không nhận sản phẩm tenant B dù cùng category.
- Tenant A không nhận sản phẩm INACTIVE nếu role hoặc API chỉ cho ACTIVE.
- Kết quả không chứa tenantId khác.
- Total hits chỉ đếm tài liệu thuộc tenant hiện tại.
- Sort và pagination không làm mất tenant filter.

## 10. Không để count và aggregation tiết lộ dữ liệu chéo

Một endpoint có thể không trả document nhưng vẫn làm lộ số lượng tài liệu của tenant khác.

Ví dụ query trả hit đã lọc tenant nhưng aggregation lại được dựng ở một nhánh khác không có tenant filter. Người dùng tenant A có thể nhìn thấy số sản phẩm hoặc phân bố category của toàn hệ thống.

Các dữ liệu cần kiểm thử:

- totalHits và total relation.
- Count API.
- Terms aggregation theo category/status/brand.
- Min/max/avg giá.
- Cardinality theo customer hoặc SKU.
- Date histogram theo ngày.
- Geo aggregation và centroid.
- Suggestion hoặc facet count.
- Thống kê trong response dashboard.

Ví dụ aggregation đúng phải nằm trong cùng query đã lọc tenant:

~~~http
POST /products/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-a"
          }
        }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Test cần tạo category chỉ tồn tại ở tenant B và xác nhận bucket đó không xuất hiện trong response của tenant A. Cũng kiểm tra số lượng bucket và doc_count, vì chỉ ẩn tên bucket vẫn có thể để lộ tổng số.

## 11. Kiểm thử autocomplete, suggest và highlight

Các tính năng tìm kiếm phụ trợ thường bị bỏ quên khi kiểm thử phân quyền. Một suggest request có thể tạo đề xuất từ term dictionary của toàn index, không tự động kế thừa tenant filter của query chính theo cách ứng dụng mong muốn.

Các trường hợp cần thử:

- Autocomplete trả tên sản phẩm thuộc tenant khác.
- Term/phrase suggester đề xuất SKU hoặc tên bí mật của tenant khác.
- Highlight trả đoạn văn bản chứa dữ liệu ngoài phạm vi.
- Search-as-you-type trả suggestion count hoặc score có thể suy ra dữ liệu chéo.
- Completion suggester dùng field tổng hợp toàn index mà không phân vùng tenant.

Nếu suggester không hỗ trợ tenant filter như mong muốn hoặc dùng chung từ điển, cần thiết kế index/field hoặc tầng kiểm tra phù hợp. Không giả định thêm query filter ở search request chính là đủ để giới hạn mọi loại suggestion.

Test nên dùng một chuỗi bí mật chỉ xuất hiện trong tenant B, gọi endpoint autocomplete bằng tenant A và xác nhận chuỗi đó không xuất hiện ở bất kỳ option, highlight hoặc metadata nào.

## 12. Kiểm thử get, multi-get, exists và count

Ngoài search, cần kiểm tra mọi API đọc theo ID hoặc đếm tài liệu:

- Repository findById.
- ElasticsearchOperations get.
- Java API Client get.
- MultiGet.
- Exists.
- Count.
- Delete-by-query hoặc update-by-query nếu endpoint có quyền gọi.
- Search theo IDs.
- Scroll, search_after và Point in Time.

Một endpoint có thể bảo vệ search nhưng quên bảo vệ multi-get hoặc exists. Ví dụ, trả true cho exists khi ID thuộc tenant khác cũng tiết lộ sự tồn tại của tài liệu.

Với multi-get, mỗi ID cần được kiểm tra quyền hoặc truy vấn theo tenant. Không nhận danh sách ID do client gửi rồi gọi mget trực tiếp trên index dùng chung mà không giới hạn phạm vi.

Test nên gồm danh sách ID hỗn hợp: một ID thuộc tenant hiện tại, một ID thuộc tenant khác và một ID không tồn tại. Xác nhận kết quả không làm lộ nội dung hoặc phân biệt ngoài chính sách giữa hai loại ID không thuộc quyền.

## 13. Kiểm thử phân quyền khi ghi, cập nhật và xóa

Rò rỉ chéo không chỉ là đọc dữ liệu. Người dùng có thể thay đổi tài liệu của tenant khác nếu backend chỉ dùng ID mà không thêm tenant constraint.

Các thao tác cần thử:

- Tạo tài liệu với tenantId giả mạo.
- Cập nhật tài liệu ngoài tenant.
- Xóa tài liệu ngoài tenant.
- Update bằng script.
- Upsert với ID thuộc tenant khác.
- Bulk index/create/update/delete.
- Update-by-query và delete-by-query.
- Reindex hoặc export nếu endpoint cho phép.
- Thay đổi owner/tenantId của một tài liệu.

Khi tạo mới, tenantId phải do server xác định từ principal hoặc quyền quản trị đã xác minh. Không cho client tự tạo tài liệu trong tenant khác chỉ bằng cách gửi tenantId trong JSON.

Khi cập nhật, query phải chứa cả ID và tenant. Không gọi update theo ID đơn thuần sau khi chỉ kiểm tra quyền ở frontend.

Khi xóa, cùng nguyên tắc: thao tác chỉ được áp dụng trong phạm vi tenant được phép.

## 14. Ngăn client chuyển tài liệu sang tenant khác

Một payload nguy hiểm:

~~~json
{
  "name": "Updated Product",
  "tenantId": "tenant-b"
}
~~~

Nếu entity được bind trực tiếp từ request rồi save, client có thể thay tenantId. Điều này tạo ra một lỗ hổng cross-tenant hoặc chuyển quyền sở hữu trái phép.

Nên dùng request DTO không có tenantId:

~~~java
public record UpdateProductRequest(
        String name,
        BigDecimal price,
        String status
) {
}
~~~

Service lấy tài liệu trong tenant hiện tại, áp dụng các trường được phép cập nhật và giữ nguyên tenantId:

~~~java
public Mono<Product> update(
        String tenantId,
        String productId,
        UpdateProductRequest request) {

    return findForTenant(tenantId, productId)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(productId)
            ))
            .map(product -> {
                product.setName(request.name());
                product.setPrice(request.price());
                product.setStatus(request.status());
                return product;
            })
            .flatMap(repository::save);
}
~~~

Ví dụ chỉ minh họa luồng. Cần áp dụng validation, kiểm tra quyền cập nhật từng trường và bảo vệ các thuộc tính hệ thống. Nếu dùng partial update, tenantId cũng phải được loại khỏi danh sách field mà client có thể ghi.

Test gửi tenantId khác trong body và xác nhận giá trị tenant trong Elasticsearch không thay đổi.

## 15. Bulk API phải có kiểm soát tenant ở từng item

Bulk request có thể chứa nhiều action. Nếu backend chỉ kiểm tra quyền một lần ở endpoint mà không xác thực từng item, một request có thể ghi vào nhiều tenant.

~~~text
Bulk request:
  item 1 -> tenant-a / product A
  item 2 -> tenant-b / product B
  item 3 -> tenant-a / product C
~~~

Nếu principal thuộc tenant-a, item 2 phải bị từ chối hoặc loại khỏi batch theo hợp đồng API. Không được ghi item 2 chỉ vì hai item còn lại hợp lệ.

Một cách xử lý là gán tenant từ principal vào từng document trước khi dựng bulk action và từ chối payload có tenantId xung đột. Với update/delete, query/action phải được giới hạn tenant. Với bulk import quản trị nhiều tenant, phải xác thực quyền trên từng tenant đích.

Test bulk nên kiểm tra partial success: item thuộc tenant hiện tại có thể thành công, item ngoài tenant bị từ chối, và response không làm lộ source của tài liệu không được phép.

## 16. Field-level security và dữ liệu nhạy cảm

Một người dùng có thể được phép đọc Product nhưng không được phép xem giá vốn, thông tin nhà cung cấp hoặc dữ liệu khách hàng.

~~~json
{
  "tenantId": "tenant-a",
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "sellingPrice": 120,
  "costPrice": 72,
  "supplierContract": "SUPPLIER-SECRET",
  "customerNotes": "Confidential"
}
~~~

API công khai có thể chỉ trả sku, name và sellingPrice. Endpoint nội bộ dành cho role tài chính mới được xem costPrice. Không nên trả toàn bộ entity rồi hy vọng frontend ẩn field nhạy cảm.

Các lớp bảo vệ:

- DTO response chỉ chứa field được phép.
- Source filtering trong query để giảm lượng dữ liệu nhạy cảm được tải về.
- Kiểm tra quyền ở service trước khi tạo response.
- Elasticsearch field-level security (nếu edition và cấu hình hỗ trợ) như một lớp phòng thủ bổ sung.
- Không ghi field nhạy cảm vào log hoặc error response.

Source filtering không thay thế authorization. Nếu một endpoint khác hoặc code khác vẫn trả toàn bộ entity, dữ liệu vẫn có thể rò rỉ.

Test cần kiểm tra role thấp không thấy field nhạy cảm trong JSON, kể cả khi field tồn tại trong source và mapping. Cũng kiểm tra các endpoint export, detail, search, aggregation và cache.

## 17. Document-level security ở Elasticsearch

Elasticsearch có thể hỗ trợ **document-level security (DLS)** và **field-level security (FLS)** trong những cấu hình/edition nhất định. DLS giới hạn document mà một user hoặc API key có thể truy cập; FLS giới hạn field được phép đọc.

Đây là lớp bảo vệ phía cluster, hữu ích khi nhiều ứng dụng hoặc người dùng truy cập Elasticsearch trực tiếp qua credential riêng. Tuy nhiên:

- Phải xác nhận tính năng có trong license/edition đang triển khai.
- Phải kiểm tra role và API key thực tế.
- DLS query cần được kiểm thử với nhiều tenant.
- FLS cần được kiểm tra trên search, get và các API liên quan.
- Không nên giả định credential dùng chung của backend tự áp dụng DLS theo người dùng cuối.

Nếu backend dùng một service credential có quyền đọc mọi tenant, Elasticsearch sẽ nhìn thấy danh tính service. Khi đó ứng dụng phải áp dụng tenant authorization ở tầng backend cho mọi request. DLS chỉ tạo ranh giới theo principal/role mà Elasticsearch thực sự nhận được.

## 18. Không để alias hoặc index routing phá vỡ tenant isolation

Một số hệ thống tách dữ liệu bằng index riêng cho tenant; hệ thống khác dùng chung index và trường tenantId. Cả hai đều cần test.

Với index riêng:

- Xác nhận tenant A không thể chọn alias/index của tenant B.
- Kiểm tra alias trỏ đúng backing index.
- Kiểm tra rollover và migration không đưa dữ liệu vào sai tenant.
- Không nhận tên index tùy ý từ client.
- Kiểm tra quyền truy cập index của credential.

Với index dùng chung:

- Mọi query phải có tenant filter.
- Mọi thao tác get/update/delete phải giới hạn tenant.
- Aggregation, suggest và export cũng phải theo tenant.
- Mapping và template phải nhất quán.
- Bulk phải xác thực từng item.

Routing theo tenant có thể cải thiện phân bố dữ liệu hoặc hiệu năng, nhưng **routing không phải cơ chế authorization**. Client có thể gửi routing khác nếu backend cho phép; server vẫn phải kiểm tra tenant và quyền.

## 19. Kiểm thử cache để tránh trả nhầm dữ liệu tenant

Một query có tenant filter đúng vẫn có thể rò rỉ dữ liệu nếu cache key không chứa tenant hoặc phạm vi quyền.

~~~text
product-search:keyboard
~~~

Tenant A tìm keyboard, response được cache. Tenant B tìm keyboard và nhận lại response của A nếu key chỉ dựa vào query.

Cache key cần bao gồm tenant và các yếu tố ảnh hưởng đến quyền:

~~~text
product-search:tenant-a:keyboard:role-catalog-reader
~~~

Không chỉ cache response search. Cần xem xét cache theo ID, count và aggregation, autocomplete/suggest, export, object trong application layer, CDN hoặc reverse proxy cache, và cache key có role/permission version khi quyền thay đổi.

Test nên gọi cùng một URL và query với hai JWT tenant khác nhau. Xác nhận response của tenant B không chứa dữ liệu đã được cache từ tenant A. Kiểm tra cả cache hit và cache miss.

## 20. Pagination, cursor và Point in Time

Phân trang có thể gây rò rỉ nếu cursor hoặc token tìm kiếm có thể được tái sử dụng giữa các tenant.

Nếu dùng search_after hoặc Point in Time:

- Cursor phải gắn với tenant và query context.
- Không chấp nhận cursor do client sửa tùy ý nếu nó chứa thông tin nội bộ.
- Kiểm tra tenant filter được áp dụng ở mọi trang.
- Kiểm tra cursor của tenant A không thể dùng với JWT tenant B.
- Giới hạn thời gian sống của PIT.
- Hủy hoặc đóng PIT khi không còn dùng.
- Không đưa dữ liệu nhạy cảm vào token dạng plaintext nếu token được gửi qua URL.

Có thể ký cursor hoặc lưu state phía server. Dù chọn cách nào, backend vẫn phải xác thực tenant của request hiện tại và đối chiếu với tenant đã tạo cursor.

Test quan trọng: lấy cursor từ tenant A, sau đó gửi cursor đó với principal tenant B. Kết quả phải bị từ chối hoặc được tạo lại trong phạm vi tenant B theo chính sách; tuyệt đối không tiếp tục trang dữ liệu tenant A.

## 21. Export, scroll và tác vụ nền

Endpoint export thường trả lượng dữ liệu lớn và có thể sử dụng scroll hoặc search_after. Nếu chỉ endpoint search được bảo vệ, export vẫn có thể là đường rò rỉ dữ liệu.

Cần kiểm tra:

- Quyền export riêng.
- Tenant filter trên mọi batch.
- Giới hạn số bản ghi và thời gian chạy.
- File được tạo có tenant scope rõ ràng.
- Link tải file không thể dùng bởi tenant khác.
- Object storage key và quyền đọc file.
- Job nền giữ đúng tenant context.
- Retry job không dùng nhầm credential hoặc tenant.
- File tạm và bản export cũ được xóa theo retention.

Một background job không còn HTTP principal. Hãy lưu tenant ID đã được xác thực cùng job request và kiểm tra quyền tại thời điểm tạo job. Không lấy tenant từ một field tự do trong message nếu producer không đáng tin cậy.

Test tải file bằng principal tenant khác, đoán ID job và thử truy cập file bằng URL của tenant khác.

## 22. Kiểm tra lỗi và log không làm lộ dữ liệu

Ngay cả khi API trả 403, nội dung lỗi có thể làm lộ source hoặc thông tin index:

~~~json
{
  "error": "Access denied for product Beta Monitor, supplier SUPPLIER-SECRET, tenant tenant-b"
}
~~~

Thông báo này đã tiết lộ tên và nhà cung cấp của tài liệu không được phép xem.

Response công khai nên dùng thông báo chung:

~~~json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Resource not found"
}
~~~

Log nội bộ cũng cần kiểm soát. Không ghi toàn bộ request body, source document, token, query chứa dữ liệu nhạy cảm hoặc error reason có source fragment nếu không cần thiết.

Test nên kiểm tra:

- Response không chứa tên hoặc field của tenant khác.
- Error body không trả Elasticsearch stack trace.
- Log không chứa access token.
- Log không chứa source document nhạy cảm.
- Metric label không đưa tenant ID hoặc user ID có cardinality rất cao nếu không cần.
- Trace không ghi query parameter nhạy cảm dưới dạng plaintext.

## 23. Kiểm thử quyền ở Spring Security

Phân quyền ở endpoint có thể dùng authority hoặc method security. Ví dụ:

~~~java
@PreAuthorize("hasAuthority('products:read')")
public Flux<Product> searchForTenant(String tenantId, String text) {
    // Tenant filter vẫn phải được áp dụng trong query.
}
~~~

Method security kiểm tra quyền thực hiện chức năng. Nó không tự giới hạn tài liệu theo tenant. Hai lớp cần có mặt:

1. Authority check: principal có được phép search sản phẩm không?
2. Tenant filter/object authorization: principal được search trong tenant nào?

Một người có products:read không mặc nhiên được đọc mọi tenant.

Test nên bao gồm:

- Anonymous không gọi được endpoint.
- User authenticated nhưng thiếu authority bị từ chối.
- User có authority và tenant-a chỉ nhận dữ liệu tenant-a.
- User có authority nhưng gửi tenant-b trong query vẫn không thể đọc tenant-b.
- Admin có quyền cross-tenant chỉ hoạt động qua endpoint/chức năng quản trị được thiết kế riêng.

## 24. Ví dụ test WebFlux với JWT

Với WebFlux và Spring Security Test, có thể dùng mock JWT để kiểm tra controller:

~~~java
@Test
void tenantASeesOnlyItsOwnProducts() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("tenant_id", "tenant-a")
            ))
            .get()
            .uri("/products?q=keyboard")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(ProductView.class)
            .value(products -> {
                assertThat(products)
                        .extracting(ProductView::getId)
                        .containsExactly("p-a-001");
            });
}
~~~

Test giả định fixture có một sản phẩm keyboard thuộc tenant A và một sản phẩm tương tự thuộc tenant B. Cần import cấu hình mock JWT phù hợp với phiên bản Spring Security Test.

Kiểm tra giả mạo tenant:

~~~java
@Test
void queryParameterCannotSwitchTenant() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("tenant_id", "tenant-a")
            ))
            .get()
            .uri("/products?tenantId=tenant-b")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(ProductView.class)
            .value(products -> assertThat(products)
                    .allSatisfy(product ->
                            assertThat(product.getTenantId())
                                    .isEqualTo("tenant-a")
                    ));
}
~~~

Nếu response DTO không chứa tenantId, hãy assert danh sách ID hoặc một field nhận diện dữ liệu. Test phải chứng minh tenant từ token là nguồn quyết định.

## 25. Ví dụ test không cho sửa tài liệu tenant khác

Một test cập nhật cần kiểm tra cả response và trạng thái dữ liệu sau thao tác:

~~~java
@Test
void tenantACannotUpdateTenantBProduct() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("tenant_id", "tenant-a")
                    .claim("scope", "products.write")
            ))
            .put()
            .uri("/products/p-b-001")
            .bodyValue(new UpdateProductRequest(
                    "Compromised Name",
                    new BigDecimal("1.00"),
                    "ACTIVE"
            ))
            .exchange()
            .expectStatus().isNotFound();

    StepVerifier.create(
            productService.findForTenant("tenant-b", "p-b-001")
    )
    .expectNextMatches(product ->
            "Beta Keyboard".equals(product.getName())
    )
    .verifyComplete();
}
~~~

Test này xác nhận người dùng tenant A không sửa được tài liệu tenant B và source gốc vẫn giữ nguyên. Nếu chính sách trả 403, thay expectation theo hợp đồng API.

Không chỉ kiểm tra status. Một bug có thể cập nhật document rồi mới trả lỗi do bước kiểm tra được đặt sau thao tác ghi.

## 26. Kiểm thử tích hợp với Elasticsearch thật

Mock repository có thể kiểm tra service composition nhưng không xác nhận Query DSL cuối cùng có tenant filter đúng. Để kiểm thử ranh giới dữ liệu, cần integration test với Elasticsearch tương thích phiên bản dự án.

Một bộ test tích hợp nên:

1. Tạo index và mapping tương ứng.
2. Index dữ liệu tenant A và tenant B.
3. Refresh index hoặc chờ cơ chế refresh phù hợp.
4. Gọi service qua các API đọc và ghi.
5. Kiểm tra kết quả search và total hits.
6. Kiểm tra aggregation và suggest.
7. Kiểm tra get-by-ID và multi-get.
8. Thử update/delete chéo tenant.
9. Kiểm tra source sau thao tác bị từ chối.
10. Xóa index hoặc dữ liệu test sau khi hoàn tất.

Testcontainers có thể cung cấp Elasticsearch cho integration test nếu image và phiên bản được cấu hình tương thích. Không dùng mock để giả định hành vi mapping, alias, aggregation hoặc security plugin của cluster.

## 27. Test ma trận theo từng bề mặt truy cập

Một checklist hữu ích là lập bảng endpoint/API và loại tenant boundary phải kiểm tra:

| Bề mặt | Test đọc chéo tenant | Test ghi chéo tenant |
|---|---:|---:|
| Search/list | Có | — |
| Get-by-ID | Có | — |
| Multi-get | Có | — |
| Exists/count | Có | — |
| Aggregation/facets | Có | — |
| Suggest/autocomplete | Có | — |
| Highlight/inner hits | Có | — |
| Scroll/search_after/PIT | Có | — |
| Export/download | Có | — |
| Cache | Có | — |
| Create | — | Có |
| Update/partial update | — | Có |
| Upsert | — | Có |
| Delete | — | Có |
| Bulk operations | Có thể | Có |
| Update-by-query/delete-by-query | Có thể | Có |
| Reindex/admin job | Có thể | Có |

Không phải ứng dụng nào cũng cung cấp mọi API trên. Chỉ cần đánh dấu các bề mặt thực sự tồn tại, nhưng đừng bỏ qua một API chỉ vì nó không nằm trên giao diện chính.

## 28. Kiểm tra query và test ở nhiều tầng

Bộ kiểm thử bảo mật nên có nhiều tầng:

- **Unit test cho tenant resolver:** xác nhận tenant được lấy từ principal đã xác thực và không lấy từ request tùy ý.
- **Unit test cho query builder:** xác nhận mọi query nghiệp vụ đều có tenant filter bắt buộc.
- **Service test:** xác nhận ID, tenant, role và field permissions được áp dụng đúng.
- **Controller/security test:** xác nhận 401/403/404 và response không lộ dữ liệu.
- **Elasticsearch integration test:** xác nhận query DSL, mapping, aggregation và bulk semantics thực tế.
- **End-to-end test:** xác nhận toàn bộ luồng từ token tới response, cache và export.

Không nên chỉ kiểm tra chuỗi JSON của query builder. Query có thể đúng nhưng một service khác lại dùng repository.findById bỏ qua helper. Cần kiểm tra các đường gọi thực tế và có thể dùng code review/static analysis để phát hiện API truy cập Elasticsearch trực tiếp ngoài lớp được kiểm soát.

## 29. Các lỗi thường gặp trong kiểm thử bảo mật

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test chỉ xác nhận người dùng đăng nhập | Nhầm authentication với authorization | Test authority và tenant scope riêng |
| Search an toàn nhưng detail bị lộ | findById không giới hạn tenant | Query theo tenant và ID |
| Hit đúng nhưng totalHits sai | Count/aggregation không cùng filter | Áp dụng tenant filter cho toàn request |
| Response không có document nhưng suggest lộ tên | Suggest dùng từ điển toàn index | Thiết kế suggest theo tenant và test riêng |
| User sửa tenantId trong body | Bind entity trực tiếp từ request | Dùng DTO và gán tenant phía server |
| Bulk ghi lẫn tenant | Không xác thực từng item | Gán tenant server-side và kiểm tra từng action |
| Update bị từ chối nhưng dữ liệu đã đổi | Kiểm tra quyền sau khi ghi | Authorize trước và giới hạn query |
| Cache trả dữ liệu của tenant khác | Cache key thiếu tenant/role | Đưa tenant và quyền vào cache key |
| Cursor dùng được ở tenant khác | Cursor không gắn query context | Ký hoặc lưu cursor và xác thực tenant |
| Export chứa dữ liệu chéo | Export path thiếu filter | Áp dụng authorization cho từng batch |
| Error response lộ source | Trả raw Elasticsearch exception | Chuẩn hóa error response |
| Test pass với mock nhưng production lộ dữ liệu | Mock không kiểm tra DSL thật | Thêm Elasticsearch integration test |

## 30. Quy trình điều tra khi phát hiện rò rỉ

Khi test phát hiện dữ liệu tenant khác xuất hiện, xử lý theo thứ tự:

1. Lưu lại request, principal test, tenant claim và response đã được masking.
2. Xác định endpoint hoặc operation tạo ra response.
3. Kiểm tra query DSL thực tế được gửi tới Elasticsearch.
4. Xác nhận tenant filter được tạo từ principal hay từ input client.
5. Kiểm tra repository, Operations, Java API Client và bulk path có bypass service không.
6. Kiểm tra aggregation, suggest, highlight, cache, export và pagination.
7. Xác nhận dữ liệu đã bị đọc hay ghi nhầm bằng integration test.
8. Sửa điểm kiểm soát chung để các đường gọi không bỏ qua tenant scope.
9. Thêm regression test tái hiện chính xác lỗ hổng.
10. Kiểm tra log, cache, file export và các bản sao dữ liệu có thể đã chứa thông tin chéo.
11. Đánh giá phạm vi ảnh hưởng và quy trình xử lý sự cố theo chính sách tổ chức.

Trong quá trình debug, dùng fixture và dữ liệu test. Không sao chép dữ liệu nhạy cảm production vào log hoặc test artifact nếu không có cơ chế xử lý phù hợp.

## 31. Nguyên tắc thiết kế để ngăn rò rỉ dữ liệu chéo

- Lấy tenant từ principal đã xác thực hoặc context được ủy quyền.
- Không tin tenantId trong query parameter, path hoặc body nếu chưa kiểm tra quyền.
- Áp dụng tenant filter ở backend cho mọi query dùng index chung.
- Không dùng findById/get/mget/exists mà thiếu object-level authorization.
- Bảo vệ count, aggregation, suggest, highlight, export và pagination.
- Gán tenantId phía server khi tạo tài liệu.
- Không cho client tự thay tenantId khi cập nhật.
- Giới hạn update/delete/upsert/bulk theo tenant.
- Tách quyền function-level và tenant-level.
- Dùng DTO và field-level authorization cho dữ liệu nhạy cảm.
- Xem DLS/FLS như lớp bảo vệ bổ sung khi có hỗ trợ và cấu hình phù hợp.
- Không xem ID khó đoán hoặc routing là cơ chế phân quyền.
- Đưa tenant và quyền vào cache key.
- Gắn cursor/PIT với tenant và query context.
- Không trả raw Elasticsearch errors hoặc source trong response.
- Kiểm thử bằng ít nhất hai tenant và dữ liệu mồi phân biệt.
- Kết hợp unit, service, security, integration và end-to-end test.
- Kiểm tra cả trường hợp được phép lẫn trường hợp bị từ chối.
- Xác nhận trạng thái dữ liệu không đổi sau thao tác ghi trái phép.

Kiểm thử bảo mật cho Spring Data Elasticsearch phải chứng minh người dùng chỉ truy cập đúng dữ liệu và thao tác trong phạm vi được cấp. Authentication và role check ở endpoint chưa đủ: tenant scope phải được áp dụng ở query, get-by-ID, count, aggregation, suggest, cache, export và mọi đường ghi. Bộ test nhiều tenant cần thử IDOR, tenant giả mạo, bulk item chéo tenant, field nhạy cảm và side channel qua metadata; đồng thời xác nhận dữ liệu không thay đổi sau thao tác trái phép. Khi kết hợp kiểm thử ở tầng Spring Security, service/query builder và Elasticsearch integration, ứng dụng có thể phát hiện những lỗ hổng rò rỉ chéo trước khi chúng xuất hiện trong production.
