# Tách quyền đọc tìm kiếm, ghi dữ liệu và quản lý index

Trong một ứng dụng Spring Data Elasticsearch, không phải thành phần nào cũng cần toàn quyền trên Elasticsearch. API tìm kiếm chỉ cần đọc document; service nhập liệu cần ghi document; tiến trình triển khai có thể cần tạo index, cập nhật mapping và chuyển alias. Nếu tất cả cùng dùng một tài khoản có quyền quản trị, một lỗi trong endpoint hoặc một credential bị lộ có thể ảnh hưởng đến toàn bộ dữ liệu.

Cách thiết kế an toàn là **tách quyền theo nhiệm vụ và cấp quyền tối thiểu**:

- **Search/read**: tìm kiếm và đọc document trong các index được phép.
- **Document write**: tạo hoặc cập nhật document theo nghiệp vụ.
- **Index administration**: tạo/xóa index, thay đổi mapping/settings và quản lý alias khi triển khai.

Cần phân biệt quyền ở hai lớp. Spring Security quyết định người dùng ứng dụng được gọi endpoint nào; Elasticsearch Security quyết định credential mà ứng dụng dùng được phép thực hiện hành động gì trên cluster và index. Hai lớp bổ sung cho nhau, không thay thế nhau.

## 1. Vì sao phải tách quyền?

Giả sử một hệ thống catalog có:

- Search API phục vụ website và mobile app.
- Product service cập nhật document khi sản phẩm thay đổi.
- Import worker nhận dữ liệu từ nguồn ngoài.
- Deployment job tạo index version mới và chuyển alias.
- Nhóm vận hành kiểm tra cluster và mapping.

Nếu tất cả dùng cùng một tài khoản Elasticsearch có quyền all, mỗi thành phần đều có thể xóa index hoặc thay đổi mapping dù không cần chức năng đó.

Một thiết kế phân quyền theo nhiệm vụ:

~~~mermaid
flowchart TD
    A["Website / Mobile"] --> B["Spring Search API"]
    B -->|credential read-only| C["Elasticsearch: products-*"]
    D["Product Service"] -->|credential document-write| C
    E["Import Worker"] -->|credential create/write| C
    F["Deployment Pipeline"] -->|credential index-admin| G["Create index / mapping / alias"]
    G --> C
~~~

| Thành phần | Nhu cầu | Quyền nên có |
|---|---|---|
| Search API | Search, get document | Read |
| Product service | Index/update document | Write trên index cần thiết |
| Event consumer chỉ tạo event document | Create document, không sửa/xóa | Create-only nếu phù hợp |
| Import worker | Bulk create/index | Quyền ghi tương ứng với operation |
| Migration job | Tạo index, mapping, alias | Index administration có giới hạn |
| Monitoring agent | Đọc health/metrics | Quyền monitor phù hợp |
| Người vận hành | Quản trị cluster | Quyền quản trị riêng, có kiểm soát |

Một credential chỉ nên có quyền cần thiết cho công việc của chính nó. Search API không cần quyền ghi; service ghi document không cần quyền xóa index; runtime application thông thường không cần quyền quản trị cluster.

## 2. Phân biệt quyền ở Spring Security và Elasticsearch Security

Hai hệ thống bảo mật có mục tiêu khác nhau:

| Lớp | Kiểm soát điều gì? | Ví dụ |
|---|---|---|
| Spring Security | Ai được gọi API của ứng dụng | User có authority products.read được gọi GET |
| Elasticsearch Security | Credential nào được gọi Elasticsearch API nào | API key chỉ có read trên products-* |
| Authorization nghiệp vụ | Người dùng được xem/sửa dữ liệu thuộc phạm vi nào | User chỉ xem sản phẩm của tenant mình |

Một request search có thể đi qua hai lần kiểm tra:

1. Spring Security xác thực user và cho phép gọi Search API.
2. Search service dùng credential riêng để gọi Elasticsearch.
3. Elasticsearch kiểm tra role/API key của credential đó có quyền đọc index đích hay không.
4. Ứng dụng áp dụng thêm filter theo tenant, ownership hoặc phạm vi dữ liệu.

Elasticsearch thường nhìn thấy service account hoặc API key của ứng dụng, không tự biết end-user đang đăng nhập vào website là ai. Vì vậy, nếu ứng dụng dùng chung một API key cho nhiều người dùng, không thể dựa vào role Elasticsearch đó để thay thế kiểm tra quyền theo từng user.

## 3. Các nhóm quyền Elasticsearch cần biết

Elasticsearch Security có quyền ở cấp cluster và cấp index. Cần chọn đúng phạm vi khi tạo role.

### Quyền cấp index

Một số index privilege thường gặp:

| Privilege | Mục đích |
|---|---|
| read | Search và đọc document |
| view_index_metadata | Đọc metadata như mapping/settings/alias ở các API được hỗ trợ |
| create_doc | Tạo document theo create semantics, không cho update/delete document |
| write | Ghi document, bao gồm các thao tác index/update/delete được privilege này cho phép |
| create_index | Tạo index |
| delete_index | Xóa index |
| manage | Quản lý index ở phạm vi rộng: mapping, settings và các thao tác quản trị index |
| manage_aliases | Quản lý alias |

Tên privilege là hợp đồng authorization của Elasticsearch. Một API có thể yêu cầu nhiều quyền tùy hành động và phiên bản. Hãy kiểm tra privilege requirement của API cụ thể khi thu hẹp role.

### Quyền cấp cluster

Cluster privilege áp dụng cho API quản lý hoặc quan sát toàn cluster, ví dụ:

- monitor: đọc thông tin giám sát cluster.
- manage_index_templates: quản lý index templates.
- manage_ilm: quản lý Index Lifecycle Management policies.
- manage: quản trị cluster ở phạm vi rộng.
- manage_security: quản lý users, roles, API keys và security configuration.

Không nhầm index privilege manage với cluster privilege manage. Cùng tên nhưng phạm vi khác nhau. Một service cần quản lý mapping của một nhóm index không vì thế mà cần quyền quản trị users hoặc toàn cluster.

## 4. Tạo role chỉ đọc để phục vụ tìm kiếm

Search API thường cần quyền đọc document trên các index sản phẩm. Ví dụ tạo role:

~~~http
POST /_security/role/products_search
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-*"],
      "privileges": [
        "read",
        "view_index_metadata"
      ],
      "allow_restricted_indices": false
    }
  ],
  "applications": [],
  "run_as": [],
  "metadata": {
    "description": "Read-only access for product search API"
  }
}
~~~

Giải thích:

- cluster rỗng vì search service không cần cluster administration.
- names giới hạn role vào index có tên khớp products-*.
- read cho phép các thao tác đọc/search.
- view_index_metadata chỉ thêm khi client hoặc endpoint cần metadata index.
- allow_restricted_indices để false nhằm tránh vô tình cấp quyền lên restricted indices.

Nếu ứng dụng chỉ gọi search/get và không cần đọc mapping, hãy kiểm tra xem có thể bỏ view_index_metadata hay không. Cấp privilege bổ sung chỉ vì "có thể cần" sẽ làm role rộng hơn mức cần thiết.

### Gắn role cho user hoặc API key

Role không tự xác thực request. Cần gắn role vào user hoặc tạo API key với role descriptor tương ứng.

Ví dụ tạo user dành riêng cho Search API:

~~~http
POST /_security/user/products-search-service
Content-Type: application/json

{
  "password": "<secret-from-secure-provisioning>",
  "roles": ["products_search"],
  "full_name": "Product search service"
}
~~~

Password trong ví dụ là placeholder. Không commit password thật vào source control, file cấu hình công khai hoặc log. Trong production, dùng secret manager hoặc cơ chế provisioning bảo mật của nền tảng.

API key cũng có thể được tạo với role descriptor giới hạn:

~~~http
POST /_security/api_key
Content-Type: application/json

{
  "name": "products-search-api",
  "role_descriptors": {
    "products_search": {
      "cluster": [],
      "indices": [
        {
          "names": ["products-*"],
          "privileges": ["read", "view_index_metadata"]
        }
      ]
    }
  }
}
~~~

Khi dùng API key, cần quản lý vòng đời, thời hạn, thu hồi và xoay vòng key. Không gửi API key về browser/mobile client nếu key được thiết kế cho service backend.

## 5. Role chỉ ghi document

Một service cập nhật document không cần quyền đọc tìm kiếm toàn bộ index nếu logic không yêu cầu. Tuy nhiên, cần chọn privilege phù hợp với loại thao tác.

### Trường hợp chỉ tạo document mới

Nếu worker chỉ dùng create operation và không cập nhật hoặc xóa document đã có, có thể cân nhắc create_doc:

~~~http
POST /_security/role/products_ingest_create
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-*"],
      "privileges": ["create_doc"]
    }
  ],
  "metadata": {
    "description": "Create-only ingestion for product documents"
  }
}
~~~

Quyền này phù hợp với pipeline append-only dùng ID ổn định và create semantics. Khi ID đã tồn tại, request create sẽ conflict; credential không được mở rộng thành quyền cập nhật hoặc xóa document.

### Trường hợp cần index/update/delete

Product service có thể cần thay thế document theo ID, cập nhật một phần source hoặc xóa document. Khi đó cần privilege ghi rộng hơn, thường là write:

~~~http
POST /_security/role/products_document_writer
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-*"],
      "privileges": ["write"]
    }
  ],
  "metadata": {
    "description": "Write product documents without index administration"
  }
}
~~~

Role này không có quyền quản trị index như tạo/xóa index hoặc thay đổi mapping. Nếu code gọi thêm search/get để kiểm tra trước khi update, cần cấp thêm quyền đọc phù hợp thay vì mặc định giả định write bao gồm read.

### Không cấp quyền ghi cho index không liên quan

Một service sản phẩm không nên có quyền write trên * nếu chỉ cần products-*. Hãy giới hạn cả loại operation lẫn tên index.

## 6. Phân biệt create_doc, write và read

Không nên gom tất cả thao tác thành một role "application" có read/write/manage.

| Nhu cầu | Privilege gợi ý | Lưu ý |
|---|---|---|
| Search và get | read | Không cho sửa document |
| Đọc metadata mapping khi cần | view_index_metadata | Chỉ thêm khi API/client yêu cầu |
| Chỉ tạo document | create_doc | Không phù hợp cho update/delete |
| Index/update/delete document | write | Không đồng nghĩa với index administration |
| Tạo index | create_index hoặc privilege quản lý phù hợp | Áp dụng cho tên index đích |
| Xóa index | delete_index hoặc privilege quản lý phù hợp | Rủi ro mất dữ liệu |
| Quản lý mapping/settings/alias | manage hoặc privilege chuyên biệt | Dành cho deployment/admin workflow |

Một số API có thể yêu cầu thêm metadata privilege hoặc cluster privilege. Ví dụ bulk request chứa nhiều loại action sẽ cần quyền tương ứng với từng item; quyền của cả request không tự biến mọi action thành hợp lệ.

## 7. Role quản lý index

Index administration là nhóm quyền nhạy cảm hơn quyền ghi document. Một migration job có thể cần:

- Tạo index version mới.
- Đặt mapping và settings.
- Tạo hoặc cập nhật alias.
- Kiểm tra index trước khi chuyển alias.
- Xóa index cũ theo chính sách retention.

Ví dụ role quản trị index sản phẩm:

~~~http
POST /_security/role/products_index_admin
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-*"],
      "privileges": ["manage"],
      "allow_restricted_indices": false
    }
  ],
  "metadata": {
    "description": "Manage product index lifecycle and mappings"
  }
}
~~~

manage là quyền quản lý index rộng. Chỉ cấp cho deployment/migration identity hoặc nhóm vận hành có nhu cầu thực sự. Nếu tác vụ chỉ cần một hành động cụ thể, hãy cân nhắc privilege chuyên biệt như create_index, delete_index hoặc manage_aliases thay vì cấp quyền rộng.

Nếu migration cần đọc document để xác nhận dữ liệu sau reindex, có thể bổ sung read. Không thêm quyền đọc nếu job chỉ thao tác mapping/settings và alias.

### Index template và ILM là quyền cấp cluster

Quản lý index template hoặc ILM policy không giống thay đổi mapping của một index hiện có. Các API này thường yêu cầu cluster privilege chuyên biệt, ví dụ manage_index_templates hoặc manage_ilm.

Không cấp cluster privilege này cho runtime Search API hoặc Document Writer. Chỉ deployment pipeline hoặc service quản trị tương ứng mới cần.

## 8. Tách tài khoản runtime và tài khoản deployment

Một mô hình triển khai an toàn thường dùng các danh tính khác nhau:

~~~text
Runtime application
  ├── search credential
  │     └── read products-*
  ├── document writer credential
  │     └── write products-*
  └── ingestion credential
        └── create_doc products-*

Deployment pipeline
  └── index admin credential
        ├── create index
        ├── update mapping/settings
        └── manage aliases
~~~

Deployment credential không nên nằm trong container runtime nếu ứng dụng không cần quản lý index. Nếu một runtime service bị xâm nhập, phạm vi thiệt hại của credential document writer sẽ nhỏ hơn nhiều so với credential có manage hoặc cluster-wide all.

Nếu một service thực sự cần đọc và ghi, có thể gắn hai role vào một service identity hoặc dùng một role tổng hợp chỉ gồm read và write trên đúng index. Tách credential riêng cho read và write hữu ích khi muốn giới hạn từng luồng hoặc audit theo workload, nhưng làm tăng số secret cần quản lý. Chọn theo ranh giới tin cậy thực tế.

## 9. Spring Security bảo vệ endpoint của ứng dụng

Elasticsearch role chỉ kiểm soát credential gọi cluster. Search API vẫn cần Spring Security để kiểm soát end-user.

Ví dụ với OAuth2 Resource Server và JWT scopes:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                HttpMethod.GET,
                                "/api/products/**"
                        ).hasAuthority("SCOPE_products.read")
                        .requestMatchers(
                                HttpMethod.POST,
                                "/api/products/**"
                        ).hasAuthority("SCOPE_products.write")
                        .requestMatchers(
                                HttpMethod.PUT,
                                "/api/products/**"
                        ).hasAuthority("SCOPE_products.write")
                        .requestMatchers(
                                HttpMethod.DELETE,
                                "/api/products/**"
                        ).hasAuthority("SCOPE_products.delete")
                        .anyRequest().authenticated()
                )
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt()
                )
                .build();
    }
}
~~~

Scopes là quyền của API ứng dụng. Chúng không tự động trở thành Elasticsearch privileges. Một user có SCOPE_products.read chỉ được gọi endpoint GET; backend vẫn sử dụng search credential được cấu hình riêng.

Nếu endpoint có thao tác nhạy cảm, có thể dùng method security:

~~~java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfiguration {
}
~~~

~~~java
@Service
public class ProductCommandService {

    @PreAuthorize("hasAuthority('SCOPE_products.write')")
    public void updateProduct(ProductCommand command) {
        // Validate command and update source data.
    }
}
~~~

Hãy xác định rõ authority mapping từ JWT hoặc authentication provider. Không tin một header tùy ý do client gửi như X-Role: admin nếu header đó không được gateway tin cậy xác thực và ghi đè.

## 10. Authorization theo tenant và quyền trên từng document

Role Elasticsearch thường cấp quyền theo index hoặc pattern index. Nhiều ứng dụng lại cần giới hạn user theo tenant, organization hoặc owner.

Ví dụ hai tenant cùng dùng index products:

~~~json
{
  "productId": "P-1001",
  "tenantId": "tenant-42",
  "name": "Wireless Keyboard"
}
~~~

~~~json
{
  "productId": "P-1001",
  "tenantId": "tenant-77",
  "name": "Wireless Mouse"
}
~~~

Một search credential có read trên products có thể đọc cả hai tenant. Ứng dụng phải thêm filter tenant được suy ra từ authentication:

~~~java
Query tenantQuery = Query.of(q -> q
        .term(t -> t
                .field("tenantId")
                .value(authenticatedTenantId)
        )
);

NativeQuery searchQuery = NativeQuery.builder()
        .withQuery(tenantQuery)
        .withPageable(PageRequest.of(0, 25))
        .build();
~~~

authenticatedTenantId phải lấy từ principal/claims đã được xác thực và kiểm tra, không lấy trực tiếp từ query parameter hoặc body mà không authorization.

Với update/delete, cũng phải xác minh document thuộc tenant trước khi thực hiện. Không cho phép client gửi ID của tenant khác rồi dùng service credential có quyền ghi toàn index để thay đổi document đó.

Có thể dùng index-per-tenant trong một số hệ thống, nhưng cần quản lý số index, lifecycle và role patterns. Không nên tạo hàng chục nghìn index chỉ để thay thế authorization theo tenant nếu mô hình dữ liệu không yêu cầu.

## 11. Quyền của Bulk API

Bulk API chứa nhiều action trong một request. Mỗi action có privilege riêng:

- create hoặc index: cần quyền tạo/ghi tương ứng.
- update: cần quyền update/write tương ứng.
- delete: cần quyền delete/write tương ứng.

Một API key chỉ có create_doc có thể phù hợp cho bulk create-only. Nếu bulk có update hoặc delete action, item tương ứng có thể bị từ chối.

Ví dụ create-only bulk:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"create":{"_index":"products-v2","_id":"P-1001"}}
{"productId":"P-1001","name":"Wireless Keyboard"}
{"create":{"_index":"products-v2","_id":"P-1002"}}
{"productId":"P-1002","name":"Wireless Mouse"}
~~~

Nếu một item conflict hoặc lỗi authorization, các item khác vẫn có thể thành công. Bulk không phải transaction. Consumer phải đọc từng item trong response và phân loại lỗi; không suy luận tất cả action thất bại chỉ vì response có errors: true.

## 12. Quyền khi dùng alias và versioned index

Một cách triển khai phổ biến là tạo index theo version rồi dùng alias cho ứng dụng:

~~~text
products-v1
products-v2
products (read/write alias)
~~~

Deployment pipeline có thể cần quyền quản lý alias để chuyển alias từ index cũ sang index mới. Runtime search và writer chỉ cần quyền trên alias hoặc index pattern phù hợp với hoạt động thực tế.

Ví dụ alias switch:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Thao tác alias cần privilege quản lý alias trên index liên quan. Chỉ deployment identity nên có quyền này nếu runtime không cần tự chuyển alias.

Cẩn thận với quyền trên alias và backing index. Role phải khớp tên index thực tế mà API authorization kiểm tra. Hãy kiểm thử qua alias trong môi trường staging thay vì chỉ kiểm tra quyền trên một tên index cố định.

## 13. Cấu hình credential trong Spring Data Elasticsearch

Spring Data Elasticsearch sử dụng Elasticsearch client được cấu hình trong application context. Authentication được cấu hình ở client/transport layer; Spring Data repository hoặc operations dùng client đó khi gửi request.

Có thể lưu endpoint và API key bằng biến môi trường hoặc secret manager:

~~~yaml
spring:
  elasticsearch:
    uris: $ELASTICSEARCH_URIS
    api-key: $ELASTICSEARCH_API_KEY
~~~

Tên property có thể khác theo Spring Boot/Spring Data Elasticsearch version và cách client được cấu hình. Nếu phiên bản ứng dụng không hỗ trợ property api-key trực tiếp, cấu hình Elasticsearch Java API Client/transport với HTTP Authorization header theo hướng dẫn tương ứng.

Không đặt API key thật trong YAML được commit. Dùng secret injection của nền tảng triển khai và giới hạn quyền đọc secret theo service account.

### Khi cần nhiều Elasticsearch credential

Nếu Search API và Writer cần role khác nhau, có thể tạo hai client/operations bean riêng, mỗi bean sử dụng credential tương ứng. Service inject đúng bean theo nhiệm vụ.

Sơ đồ:

~~~text
SearchService
   |
   +--> searchOperations
           |
           +--> Elasticsearch client (read API key)

ProductCommandService
   |
   +--> writeOperations
           |
           +--> Elasticsearch client (write API key)
~~~

Cấu hình nhiều client cần đặt tên bean rõ ràng và dùng @Qualifier khi inject để tránh nhầm. Không dùng cùng một client admin làm default cho mọi repository chỉ vì cấu hình thuận tiện.

Trong một số ứng dụng, một service account read/write giới hạn trên đúng index là đủ. Tách client riêng chỉ khi ranh giới quyền hoặc vận hành cần thiết và nhóm có thể quản lý secret/connection pool tương ứng.

## 14. Không dùng quyền admin cho health check

Health check và readiness probe thường không cần quyền quản trị index. Hãy xác định probe cần kiểm tra điều gì:

- Ứng dụng còn kết nối được Elasticsearch không?
- Cluster có đủ điều kiện phục vụ request không?
- Alias/index mục tiêu có tồn tại không?
- Search API có thể thực hiện truy vấn mẫu không?

Một probe chỉ kiểm tra kết nối có thể dùng endpoint health/cluster phù hợp với quyền monitor, hoặc thực hiện một thao tác đọc rất nhỏ trên index đã biết. Không cấp manage chỉ để endpoint health có thể đọc cluster metadata.

Nếu probe cần đọc cluster health, dùng credential monitor riêng hoặc quyền monitor tối thiểu theo API đang gọi. Không đưa credential quản trị vào actuator endpoint.

## 15. Kiểm thử role và quyền thực tế

Role JSON hợp lệ chưa chứng minh ứng dụng hoạt động đúng. Cần kiểm thử bằng đúng user/API key mà service sẽ dùng.

### Kiểm tra danh tính hiện tại

~~~http
GET /_security/_authenticate
~~~

Response cho biết user/API key identity và role hiệu lực theo security configuration.

### Kiểm tra quyền cụ thể

Elasticsearch cung cấp API kiểm tra quyền:

~~~http
POST /_security/user/_has_privileges
Content-Type: application/json

{
  "cluster": [],
  "index": [
    {
      "names": ["products-v2"],
      "privileges": ["read"]
    }
  ]
}
~~~

Dùng credential cần kiểm tra để xác nhận quyền đọc. Có thể kiểm tra thêm write, create_doc hoặc manage tùy role.

### Kiểm tra hành vi thực tế

| Test | Search role | Writer role | Index admin role |
|---|---|---|---|
| Search products | Cho phép | Chỉ nếu được cấp read | Theo quyền được cấp |
| Create document | Từ chối | Cho phép nếu có create/write | Có thể được phép theo manage |
| Update document | Từ chối | Cho phép nếu có write | Có thể được phép theo manage |
| Delete document | Từ chối | Chỉ nếu có write/delete | Có thể được phép theo manage |
| Create index | Từ chối | Từ chối | Cho phép |
| Update mapping | Từ chối | Từ chối | Cho phép |
| Delete index | Từ chối | Từ chối | Cho phép |
| Manage alias | Từ chối | Từ chối | Cho phép nếu role có privilege tương ứng |

Test cần xác nhận cả hành động được phép và hành động bị từ chối. Chỉ kiểm tra happy path sẽ không phát hiện role bị cấp quá rộng.

## 16. Xoay vòng và thu hồi credential

API key và service account credential cần có vòng đời:

1. Tạo key mới với role tối thiểu.
2. Cập nhật secret trong môi trường triển khai.
3. Khởi động/reload service để dùng key mới.
4. Xác nhận authentication và hành vi API.
5. Thu hồi key cũ sau khi không còn workload sử dụng.
6. Theo dõi lỗi authentication sau rotation.

Không chia sẻ một API key duy nhất cho nhiều service không liên quan nếu cần khả năng audit và thu hồi độc lập. Nếu key bị lộ, việc thu hồi key dùng chung có thể làm nhiều workload dừng cùng lúc.

Không log Authorization header, API key, password hoặc full connection URI có chứa credential. Giới hạn quyền xem secret và quyền tạo API key.

## 17. Nguyên tắc thiết kế role an toàn

Một bộ nguyên tắc thực tế:

- Cấp quyền theo nhiệm vụ, không theo chức danh chung chung.
- Giới hạn index names bằng pattern hẹp.
- Không cấp all cho runtime application.
- Search role chỉ đọc.
- Writer role chỉ có thao tác document cần thiết.
- Create-only ingestion dùng create_doc khi phù hợp.
- Index admin dùng identity riêng cho deployment/migration.
- Cluster privileges chỉ cấp khi API quản trị thực sự cần.
- Không đưa credential admin vào browser/mobile hoặc API response.
- Kiểm thử cả allow và deny.
- Dùng TLS và secret manager.
- Xoay vòng, thu hồi và audit credential.
- Áp dụng tenant/ownership authorization trong ứng dụng.
- Revalidate role khi thêm API hoặc đổi thao tác bulk/update.

## 18. Các lỗi thường gặp

### Dùng một superuser cho mọi service

Search API có thể xóa index nếu credential có toàn quyền. Tạo role riêng cho read, write và index administration.

### Nghĩ Spring Security thay thế Elasticsearch Security

Spring Security bảo vệ endpoint ứng dụng. Elasticsearch vẫn kiểm tra credential backend khi nhận request. Cần cả hai lớp.

### Cấp read/write trên mọi index

Pattern * có thể mở quyền lên index không liên quan. Giới hạn vào products-* hoặc đúng tên index cần dùng.

### Nghĩ write bao gồm quyền quản trị index

Quyền ghi document khác quyền tạo/xóa index hoặc thay đổi mapping/settings. Cấp quyền quản trị riêng.

### Dùng create_doc cho update

Create-only không đáp ứng update/delete. Nếu operation cần thay thế hoặc cập nhật document, chọn privilege phù hợp và kiểm thử.

### Quên metadata privilege

Một số client hoặc API đọc mapping/alias cần view_index_metadata. Chỉ thêm sau khi xác định request thực tế bị thiếu quyền đó.

### Gán role Elasticsearch cho end-user như thể nó tự giới hạn tenant

Nếu mọi request đi qua một service account, Elasticsearch thấy cùng identity. Ứng dụng vẫn phải áp dụng filter tenant và ownership.

### Đưa admin credential vào runtime container

Một lỗi trong service có thể xóa index hoặc sửa mapping. Giữ credential quản trị ở deployment/operations workflow.

### Không kiểm tra từng bulk item

Một bulk request có thể có item thành công và item bị từ chối. Đọc items và xử lý partial failure.

### Không xoay vòng API key

Key tồn tại lâu và được chia sẻ rộng làm tăng phạm vi rủi ro. Dùng key riêng, thời hạn phù hợp và quy trình rotation.

## 19. Quy trình triển khai phân quyền

Khi tách quyền đọc, ghi và quản lý index:

1. Liệt kê các service và Elasticsearch API mà từng service thực sự gọi.
2. Phân loại thao tác thành search/read, document create/write/delete, index administration và cluster administration.
3. Chọn index pattern hẹp cho từng role.
4. Tạo role read với read và metadata privilege chỉ khi cần.
5. Tạo create-only role với create_doc nếu ingestion không update/delete.
6. Tạo writer role với write cho service cần update document.
7. Tạo index admin role riêng cho migration/deployment.
8. Cấp cluster privilege chuyên biệt cho template/ILM chỉ khi workflow cần.
9. Tạo user/API key riêng và đưa secret vào secret manager.
10. Cấu hình Spring Data client/operations dùng credential đúng nhiệm vụ.
11. Bảo vệ endpoint bằng Spring Security và kiểm tra tenant/ownership trong service.
12. Kiểm thử request được phép và bị từ chối bằng credential thật.
13. Theo dõi authorization failure, key usage và credential rotation.
14. Khi thêm thao tác mới, cập nhật role tối thiểu và test lại cả allow/deny.

## Tài liệu tham khảo

- [Elasticsearch — Security privileges](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-privileges.html)
- [Elasticsearch — Defining roles](https://www.elastic.co/guide/en/elasticsearch/reference/current/defining-roles.html)
- [Elasticsearch — Create or update roles API](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-put-role.html)
- [Elasticsearch — Create API key API](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-create-api-key.html)
- [Elasticsearch — Has privileges API](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-has-privileges.html)
- [Elasticsearch — Authentication API](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-authenticate.html)
- [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Data Elasticsearch — Configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)

## Kết luận

Tách quyền đọc tìm kiếm, ghi document và quản lý index giúp giảm phạm vi ảnh hưởng khi credential bị lộ hoặc service gặp lỗi. Dùng Elasticsearch index privilege như read, create_doc, write và manage theo đúng nhiệm vụ; giới hạn index pattern và giữ cluster administration ở deployment/operations identity riêng. Spring Security tiếp tục kiểm soát end-user ở API, còn Elasticsearch Security bảo vệ cluster bằng credential backend. Với multi-tenant, ứng dụng vẫn phải kiểm tra tenant/ownership vì một service credential có thể đọc nhiều document trong cùng index. Kiểm thử cả quyền được phép lẫn bị từ chối, quản lý secret và xoay vòng API key theo vòng đời rõ ràng.
