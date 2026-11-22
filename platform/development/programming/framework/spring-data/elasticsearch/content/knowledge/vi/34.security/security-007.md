# Routing không thay thế kiểm soát quyền truy cập

Elasticsearch dùng routing để quyết định document được lưu trên shard nào và search request cần gửi đến những shard nào. Trong ứng dụng nhiều tenant, routing thường được dùng để đặt dữ liệu của cùng tenant gần nhau, giảm số shard cần tìm kiếm và cải thiện hiệu năng.

Tuy nhiên, **routing không phải cơ chế phân quyền**. Routing chỉ điều hướng request đến shard. Nó không xác minh người gọi có quyền đọc, cập nhật hoặc xóa document hay không; cũng không tự lọc mọi document trên shard theo tenant. Nếu ứng dụng dùng routing như bằng chứng người dùng được phép truy cập dữ liệu, một request có routing value do người dùng tự chọn có thể vượt qua ranh giới tenant.

Bài học này phân biệt routing với authorization, giải thích cách Elasticsearch định tuyến document, cách truyền routing trong Spring Data Elasticsearch, cách kết hợp routing với bộ lọc tenant và quyền truy cập, cùng những tình huống kiểm thử cần có cho hệ thống nhiều tenant.

## 1. Routing giải quyết vấn đề gì?

Elasticsearch chia index thành các primary shard. Mỗi document được lưu trên một shard. Khi không chỉ định custom routing, Elasticsearch dùng document ID làm routing value mặc định để xác định shard.

Với custom routing, ứng dụng cung cấp một giá trị như tenant ID, customer ID hoặc account ID. Elasticsearch dùng giá trị đó để chọn shard cho document.

Ví dụ hệ thống quản lý đơn hàng:

- Tenant A có hàng nghìn đơn hàng.
- Tenant B có hàng nghìn đơn hàng khác.
- Người dùng thường xuyên tìm đơn hàng trong tenant của mình.
- Ứng dụng muốn các document của cùng tenant được định tuyến nhất quán để truy vấn theo tenant có thể giới hạn phạm vi shard.

Routing có thể giúp giảm số shard được tìm kiếm nếu query cung cấp đúng routing value. Nó cũng giúp các thao tác get, update hoặc delete tìm document trên shard mà document đã được lưu.

Routing có ích cho phân phối và truy cập dữ liệu. Nó không quyết định ai được phép thực hiện thao tác.

## 2. Cách Elasticsearch chọn shard

Khi index một document, Elasticsearch tính shard từ routing value và số lượng primary shard của index. Có thể hình dung đơn giản:

~~~text
routing value
      |
      v
    hash
      |
      v
  số primary shard
      |
      v
  shard đích
~~~

Nếu không truyền routing, document ID được dùng làm giá trị mặc định. Nếu truyền custom routing, giá trị custom được dùng để xác định shard.

Ví dụ hai document cùng routing value tenant-42 sẽ được định tuyến nhất quán tới cùng shard trong cùng index:

~~~http
POST /orders/_doc/O-100?routing=tenant-42
{
  "orderId": "O-100",
  "tenantId": "tenant-42",
  "status": "OPEN"
}
~~~

~~~http
POST /orders/_doc/O-101?routing=tenant-42
{
  "orderId": "O-101",
  "tenantId": "tenant-42",
  "status": "PAID"
}
~~~

Nếu document được index với custom routing, những thao tác đọc hoặc cập nhật theo ID thường phải dùng lại đúng routing value để tìm đúng shard.

### Routing không tạo một shard riêng cho mỗi tenant

Hai routing value khác nhau có thể được hash tới cùng một shard. Một tenant cũng có thể có rất nhiều document trên cùng shard với tenant khác.

Ví dụ:

~~~text
Primary shard 0: tenant-A, tenant-B, tenant-C
Primary shard 1: tenant-D, tenant-E
Primary shard 2: tenant-F, tenant-G, tenant-H
~~~

Sơ đồ chỉ minh họa việc nhiều routing value có thể cùng chọn một shard. Nó không biểu diễn một ranh giới bảo mật.

Nếu search request chỉ định routing cho tenant-A và shard 0 được chọn, Elasticsearch vẫn có thể tìm thấy document của tenant-B hoặc tenant-C nằm trên shard 0 nếu query không lọc theo tenant. Routing giới hạn shard tham gia; nó không tự thêm điều kiện tenant vào Query DSL.

## 3. Routing và authorization là hai trách nhiệm khác nhau

Authorization trả lời câu hỏi: người dùng hoặc service hiện tại có được phép thực hiện hành động trên tài nguyên này hay không?

Routing trả lời câu hỏi: document nằm ở shard nào và search nên gửi request đến shard nào?

| Khía cạnh | Routing | Authorization |
|---|---|---|
| Mục tiêu | Điều hướng đến shard | Cho phép hoặc từ chối hành động |
| Đầu vào | Routing value | Identity, role, permission, resource |
| Xác minh danh tính | Không | Dựa trên authentication đã xác thực |
| Kiểm tra tenant membership | Không | Phải được thực hiện bởi lớp phân quyền |
| Lọc document theo tenant | Không tự động | Cần policy/filter phù hợp |
| Ngăn truy cập trái phép | Không | Có |
| Tác động chính | Phạm vi shard và hiệu năng | Bảo mật dữ liệu và thao tác |

Một request có routing value hợp lệ vẫn có thể đến từ người dùng không có quyền. Elasticsearch không suy ra quyền từ việc request có routing value.

Không được dùng các giả định sau:

- Người dùng biết tenant ID thì người dùng thuộc tenant đó.
- Request chỉ đến một shard thì document trên shard đó đều thuộc người dùng.
- Routing value khớp với document ID nghĩa là người gọi có quyền.
- Index có custom routing thì dữ liệu tự động được cô lập.
- Một repository method có tham số routing đã đủ bảo vệ tenant.

## 4. Vì sao search routing không phải bộ lọc tenant?

Giả sử tenant-A và tenant-B cùng có document trên shard 0. Ứng dụng gửi:

~~~http
GET /orders/_search?routing=tenant-A
{
  "query": {
    "match_all": {}
  }
}
~~~

Request giới hạn việc tìm kiếm vào shard được chọn bởi tenant-A. Nhưng shard đó vẫn chứa document của tenant-B nếu routing value của tenant-B cũng hash tới shard 0.

Do đó, search cần có điều kiện tenant rõ ràng:

~~~http
GET /orders/_search?routing=tenant-A
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-A"
          }
        }
      ]
    }
  }
}
~~~

Hai phần có vai trò riêng:

- routing giảm phạm vi shard cần tìm.
- tenantId filter giới hạn document được phép đưa vào kết quả theo tenant.

Giá trị routing và tenantId nên nhất quán, nhưng chúng vẫn là hai khái niệm khác nhau. Routing là metadata điều hướng của Elasticsearch; tenantId trong source là dữ liệu nghiệp vụ có thể được query và kiểm tra.

### Không bỏ tenant filter vì đã truyền routing

Ngay cả khi hiện tại dữ liệu thử nghiệm tình cờ đặt tenant-A và tenant-B trên hai shard khác nhau, điều đó không phải bảo đảm lâu dài. Số primary shard, routing strategy, dữ liệu mới và cấu hình index có thể làm các tenant cùng shard.

Một thay đổi số shard hoặc cách định tuyến cũng có thể làm giả định cũ không còn đúng. Điều kiện tenant cần có trong query theo chính sách ứng dụng, bất kể routing có được truyền hay không.

## 5. Thiết kế dữ liệu nhiều tenant

Một document nhiều tenant nên chứa tenant identifier rõ ràng trong source:

~~~json
{
  "orderId": "O-100",
  "tenantId": "tenant-A",
  "customerId": "C-200",
  "status": "OPEN",
  "total": 125.50
}
~~~

Khi index document:

- Ứng dụng xác định tenant từ identity đã xác thực.
- Ứng dụng gán tenantId vào document.
- Ứng dụng dùng cùng tenant identifier làm routing value nếu chiến lược routing chọn tenant.
- Không nhận tenantId hoặc routing value từ request body như một giá trị đã được tin cậy.

Tenant ID trong source hỗ trợ filter, audit và đối soát. Nó cũng giúp phát hiện lỗi khi routing value và dữ liệu source không khớp.

### Xác định document ID

Với custom routing, cùng một document ID có thể được lưu trên các shard khác nhau nếu các lần index dùng routing value khác nhau. Elasticsearch bảo đảm tính duy nhất của ID trong phạm vi shard, không phải một ràng buộc unique nghiệp vụ xuyên mọi routing value.

Vì vậy, hệ thống nhiều tenant cần chọn một quy tắc ID rõ ràng:

- Dùng ID toàn cục duy nhất trong toàn index; hoặc
- Kết hợp tenant ID và business ID để tạo document ID duy nhất theo tenant.

Dù dùng cách nào, routing value phải ổn định cho vòng đời document. Nếu cùng một record bị index với hai routing value khác nhau, có thể tạo hai bản document trên các shard khác nhau thay vì ghi đè bản cũ.

## 6. Xác thực người dùng và lấy tenant từ nguồn đáng tin cậy

Ứng dụng nên xác định tenant sau khi authentication thành công. Tenant context có thể đến từ:

- Claim đã được xác minh trong access token.
- Membership được tải từ hệ thống quản lý danh tính.
- Context được tạo sau bước kiểm tra quyền của user.
- Service-to-service identity đã được xác thực và giới hạn scope.

Không mặc định tin các giá trị từ:

- Query parameter tenantId.
- HTTP header X-Tenant-ID.
- Request body.
- Path variable do caller tự chọn.
- Routing value do frontend gửi lên.

Các giá trị này có thể được dùng làm thông tin yêu cầu, nhưng server phải xác minh người gọi có membership hoặc quyền tương ứng trước khi dùng chúng.

Luồng xử lý nên như sau:

~~~text
HTTP request
     |
     v
Authenticate identity
     |
     v
Resolve trusted principal / tenant membership
     |
     v
Authorize requested action
     |
     v
Derive tenantId on server
     |
     +-----------------------+
     |                       |
     v                       v
Add tenant query filter   Set routing value
     |                       |
     +-----------+-----------+
                 |
                 v
       Elasticsearch request
                 |
                 v
       Return authorized result
~~~

Routing value được lấy từ tenant context đã được xác minh, không phải bằng chứng để tạo tenant context.

## 7. Tích hợp với Spring Security

Trong ứng dụng Spring, service có thể nhận tenant ID từ một thành phần context dựa trên principal đã xác thực.

Ví dụ một abstraction nhỏ:

~~~java
public interface CurrentTenant {

    String requireTenantId();
}
~~~

Implementation có thể đọc claim hoặc principal đã được xác minh bởi Spring Security. Cách lấy dữ liệu phụ thuộc mô hình authentication của ứng dụng.

Service không nhận tenant ID tùy ý từ caller:

~~~java
@Service
public class OrderService {

    private final CurrentTenant currentTenant;
    private final OrderRepository repository;

    public OrderService(
            CurrentTenant currentTenant,
            OrderRepository repository) {
        this.currentTenant = currentTenant;
        this.repository = repository;
    }

    public List<Order> findMyOrders() {
        String tenantId = currentTenant.requireTenantId();
        return repository.findByTenantId(tenantId);
    }
}
~~~

Trong ví dụ này, tenant ID được lấy từ server-side context. Repository vẫn phải áp dụng tenant filter. Nếu cần kiểm tra quyền trên một order cụ thể, service cần xác minh order thuộc tenant của principal trước khi thực hiện hành động.

### Method security

Có thể dùng method security để giới hạn quyền gọi service:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

~~~java
@Service
public class OrderAdministrationService {

    @PreAuthorize("hasAuthority('orders:read')")
    public List<Order> listOrdersForCurrentTenant() {
        // Resolve tenant from authenticated context
        // and query only that tenant's documents.
        return List.of();
    }
}
~~~

Authority như orders:read chỉ là ví dụ. Quyền thực tế phải phản ánh policy của ứng dụng. Kiểm tra authority cho phép gọi chức năng vẫn chưa đủ để xác định tài nguyên thuộc tenant nào; cần kiểm tra tenant scope trong cùng luồng xử lý.

Không dùng một annotation quyền chung làm lý do bỏ tenant filter khỏi truy vấn.

## 8. Áp dụng tenant filter trong repository

Một repository method nên biểu đạt tenant scope rõ ràng. Với derived query, có thể viết:

~~~java
public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {

    List<Order> findByTenantIdAndStatus(
        String tenantId,
        String status
    );

    Optional<Order> findByIdAndTenantId(
        String id,
        String tenantId
    );
}
~~~

Service truyền tenant ID từ trusted context:

~~~java
public List<Order> findOpenOrders() {
    String tenantId = currentTenant.requireTenantId();

    return repository.findByTenantIdAndStatus(
        tenantId,
        "OPEN"
    );
}
~~~

Không cung cấp một endpoint công khai gọi repository.findAll() cho người dùng tenant nếu chưa có policy rõ ràng. Repository CRUD tổng quát thường không tự biết tenant hiện tại.

Với method tìm theo ID, dùng truy vấn kết hợp ID và tenant. Không giả định ID khó đoán là cơ chế phân quyền.

### @Query cũng phải chứa tenant condition

Ví dụ query JSON cố định:

~~~java
@Query("""
{
  "bool": {
    "filter": [
      { "term": { "tenantId": "?0" } },
      { "term": { "status": "?1" } }
    ]
  }
}
""")
List<Order> findByTenantAndStatus(
    String tenantId,
    String status
);
~~~

Caller vẫn phải truyền tenant ID lấy từ context đã xác thực. Không cho phép client gửi tenant ID tùy ý rồi gọi method này trực tiếp mà không authorization.

Nếu nhiều query cần tenant filter, cân nhắc custom repository fragment hoặc một query builder chung để giảm nguy cơ quên điều kiện. Tuy nhiên, helper không thể bảo vệ các đường truy cập khác như CRUD, direct client hoặc admin endpoint nếu chúng không dùng helper.

## 9. Kết hợp routing với NativeQuery

Khi dùng NativeQuery, tạo bool query với tenant filter. Đồng thời, nếu API phiên bản đang dùng hỗ trợ routing metadata cho search request, truyền routing value để giới hạn shard.

Ví dụ cấu trúc Query DSL:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-A"
          }
        },
        {
          "term": {
            "status": "OPEN"
          }
        }
      ]
    }
  }
}
~~~

Trong code Spring Data, phần query có thể được dựng bằng Java API Client builder:

~~~java
Query tenantQuery = Query.of(q -> q.bool(b -> b
    .filter(f -> f.term(t -> t
        .field("tenantId")
        .value(tenantId)
    ))
    .filter(f -> f.term(t -> t
        .field("status")
        .value("OPEN")
    ))
));
~~~

Query object trên thể hiện điều kiện lọc. Routing được truyền riêng qua request metadata hoặc query option tương ứng của phiên bản Spring Data Elasticsearch đang dùng. Tên method builder và overload thay đổi theo release train; hãy kiểm tra API thực tế thay vì giả định tenant filter tự tạo routing.

Nếu dùng Elasticsearch Java API Client trực tiếp, request search có thể nhận routing rõ ràng:

~~~java
SearchResponse<Order> response =
    elasticsearchClient.search(s -> s
        .index("orders")
        .routing(tenantId)
        .query(q -> q.bool(b -> b
            .filter(f -> f.term(t -> t
                .field("tenantId")
                .value(tenantId)
            ))
            .filter(f -> f.term(t -> t
                .field("status")
                .value("OPEN")
            ))
        )),
        Order.class
    );
~~~

Ở đây tenantId phải là giá trị do server lấy từ context đã xác thực. Không truyền nguyên routing value do caller điều khiển.

## 10. Routing khi index, get, update và delete

Routing phải nhất quán qua vòng đời document.

### Index

Khi ghi document, truyền routing value đã được server xác định:

~~~java
IndexResponse response = elasticsearchClient.index(i -> i
    .index("orders")
    .id(order.getId())
    .routing(tenantId)
    .document(order)
);
~~~

Entity source nên chứa tenantId cùng giá trị tương ứng. Trước khi index, kiểm tra entity không mang tenantId do caller giả mạo.

### Get

Khi lấy theo ID, routing phải là giá trị đã dùng lúc index:

~~~java
GetResponse<Order> response = elasticsearchClient.get(g -> g
    .index("orders")
    .id(orderId)
    .routing(tenantId),
    Order.class
);
~~~

Sau khi lấy document, service vẫn cần xác minh tenant ownership theo policy. Không dùng route làm phép kiểm tra quyền.

### Update

Update theo ID cần đúng routing:

~~~java
UpdateResponse<Order> response =
    elasticsearchClient.update(u -> u
        .index("orders")
        .id(orderId)
        .routing(tenantId)
        .doc(Map.of("status", "PAID")),
        Order.class
    );
~~~

Nếu nghiệp vụ yêu cầu điều kiện tenant, cần kiểm tra ownership trước khi update hoặc dùng một query/update flow có điều kiện tenant rõ ràng. Không cho caller chỉ định routing rồi cập nhật document trực tiếp.

### Delete

Delete cũng cần route đúng:

~~~java
DeleteResponse response = elasticsearchClient.delete(d -> d
    .index("orders")
    .id(orderId)
    .routing(tenantId)
);
~~~

Trước khi xóa, service cần xác minh caller có quyền xóa order thuộc tenant đó. Nếu route sai, Elasticsearch có thể trả not found dù document tồn tại trên shard khác. Không diễn giải not found thành bằng chứng user không có quyền; xử lý lỗi theo API contract và tránh làm lộ sự tồn tại của document tenant khác.

## 11. Routing trong Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ khai báo routing metadata cho entity bằng annotation routing trên property. Ví dụ:

~~~java
@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Routing
    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Keyword)
    private String status;
}
~~~

Trong thực tế, nên dùng một property tenant identifier duy nhất và xác nhận cách mapping/conversion của phiên bản đang dùng. Ví dụ trên tách tên để nhấn mạnh rằng routing metadata và field trong source có hai mục đích; không nhất thiết phải duy trì hai field tenant riêng biệt.

Một model thường có thể dùng cùng property tenant ID vừa làm giá trị routing vừa được lưu thành field keyword để query. Kiểm tra annotation và mapping được tạo ra trong release train của dự án.

### Gán routing trước khi lưu

Khi tạo entity mới, server cần gán tenant ID từ trusted context:

~~~java
public Order createOrder(CreateOrderRequest request) {
    String tenantId = currentTenant.requireTenantId();

    Order order = new Order();
    order.setTenantId(tenantId);
    order.setStatus("OPEN");
    order.setCustomerId(request.customerId());

    return repository.save(order);
}
~~~

Không sao chép tenant ID từ request body nếu chưa xác minh quyền. Nếu DTO có field tenantId, có thể bỏ qua hoặc từ chối khi nó không khớp tenant context.

### Routing cho các thao tác tùy biến

Khi dùng ElasticsearchOperations, NativeQuery hoặc bulk operations, routing có thể được truyền qua metadata của operation/query hoặc từng item bulk. API cụ thể thay đổi theo phiên bản Spring Data Elasticsearch.

Đối với bulk, routing phải được thiết lập cho từng operation tương ứng. Không giả định một routing value ở cấp batch tự động phù hợp với mọi document nếu batch có thể chứa nhiều tenant.

Khi cần bảo đảm tenant isolation, mỗi item phải có tenant ID được xác minh và query/filter tương ứng. Nếu một batch gồm nhiều tenant, không dùng một routing value chung cho cả batch.

## 12. _routing.required có tác dụng gì?

Elasticsearch cho phép mapping yêu cầu routing khi index document. Ví dụ:

~~~http
PUT /orders
{
  "mappings": {
    "_routing": {
      "required": true
    },
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Khi bật required, thao tác index document thiếu routing sẽ bị từ chối. Cấu hình này giúp phát hiện caller quên truyền routing value.

Nhưng nó không xác minh routing value đúng tenant:

- Routing tenant-A vẫn có thể được gửi khi document source chứa tenant-B.
- Người dùng không có quyền vẫn có thể gửi routing nếu API cho phép.
- Search routing vẫn không tự thêm tenant filter.
- Một routing value bất kỳ vẫn có thể chọn shard hợp lệ.

Vì vậy, required là kiểm tra tính đầy đủ của metadata routing, không phải authorization.

## 13. Elasticsearch roles, document-level security và field-level security

Elasticsearch có các cơ chế bảo mật ở tầng cluster/index, và trong các cấu hình/phiên bản phù hợp có thể có document-level security (DLS) và field-level security (FLS).

- **Index privileges** giới hạn user/API key được đọc, ghi, tạo hoặc xóa trên index nào.
- **Document-level security** giới hạn document nào user được phép truy cập theo query policy.
- **Field-level security** giới hạn field nào được đọc hoặc ghi tùy loại quyền và cấu hình hỗ trợ.
- **API key/service identity** cung cấp danh tính và quyền cho ứng dụng hoặc client gọi Elasticsearch.

Các tính năng và điều kiện license có thể khác nhau theo phiên bản và subscription. Hãy xác nhận tính năng DLS/FLS có trong môi trường triển khai thực tế.

DLS có thể là lớp bảo vệ bổ sung khi các user hoặc API key khác nhau kết nối trực tiếp tới Elasticsearch với role riêng. FLS có thể giảm khả năng lộ field nhạy cảm cho các principal không cần đọc chúng.

### DLS/FLS không tự hiểu end-user khi backend dùng chung credential

Một kiến trúc phổ biến là backend Spring dùng một service account hoặc API key chung để gọi Elasticsearch thay cho tất cả end-user. Khi đó Elasticsearch chỉ nhìn thấy danh tính của backend, không tự biết request hiện tại đến từ tenant-A hay tenant-B.

Nếu backend dùng chung một credential có quyền đọc toàn index, DLS policy gắn với credential đó sẽ áp dụng theo danh tính backend. Nó không tự thay đổi theo principal người dùng của từng HTTP request.

Trong kiến trúc này, backend vẫn phải:

- Authenticate người dùng.
- Resolve tenant membership.
- Authorize hành động.
- Tạo tenant filter bắt buộc.
- Tự lấy routing value từ context đáng tin cậy.
- Không để client gọi query tùy ý vượt qua service policy.

Nếu từng tenant hoặc user có Elasticsearch identity riêng, roles/DLS/FLS có thể bổ sung enforcement ở cluster. Dù vậy, vẫn cần thiết kế identity lifecycle, credential rotation và quyền tối thiểu cẩn thận.

## 14. Index riêng, alias và routing

Một số hệ thống dùng index riêng cho từng tenant. Cách này có thể tạo ranh giới vận hành rõ hơn, nhưng chỉ an toàn nếu Elasticsearch privileges giới hạn principal vào đúng index.

Alias có thể trỏ tới một index hoặc nhiều index, và có thể được cấu hình với search/index routing. Alias routing giúp điều hướng request qua alias theo routing value đã cấu hình.

Nhưng alias routing cũng chỉ điều hướng shard. Nó không tự chứng minh caller thuộc tenant được phép truy cập alias đó.

Nếu backend service account có quyền trên tất cả index tenant, endpoint ứng dụng vẫn phải kiểm tra tenant context trước khi chọn alias/index. Không để người dùng tự cung cấp tên index hoặc alias tùy ý.

| Mô hình | Lợi ích | Điều cần bảo vệ |
|---|---|---|
| Một index, tenant routing | Dễ gom dữ liệu, có thể giảm shard fan-out | Tenant filter bắt buộc và server-derived route |
| Một index, không custom routing | Mô hình đơn giản | Tenant filter vẫn bắt buộc |
| Index riêng từng tenant | Tách mapping/lifecycle và có thể giới hạn index privilege | Index selection và Elasticsearch role |
| Alias theo tenant | API truy cập ổn định, có thể gắn routing | Alias không thay thế authorization |
| DLS/FLS theo principal | Enforcement tại Elasticsearch cho principal tương ứng | Identity, role policy và license/version |

Không chọn mô hình chỉ dựa trên giả định rằng shard riêng hoặc alias riêng tự động tạo bảo mật.

## 15. Tránh truy vấn không có tenant scope

Một lỗi thường gặp là repository cung cấp cả method an toàn và method tổng quát:

~~~java
List<Order> findByTenantId(String tenantId);

Iterable<Order> findAll();
~~~

Nếu controller hoặc service bất kỳ có thể gọi findAll, dữ liệu nhiều tenant có thể bị trả về ngoài dự kiến.

Một số nguyên tắc thiết kế:

- Đặt repository phía sau service layer.
- Không expose repository CRUD trực tiếp ra controller.
- Ưu tiên method có tenant scope rõ ràng.
- Với admin operation toàn hệ thống, dùng service và authority riêng.
- Hạn chế quyền truy cập vào raw ElasticsearchOperations/client.
- Code review mọi query mới để xác nhận tenant filter.
- Có test đảm bảo endpoint không thể truy vấn cross-tenant.

Không nên dựa vào convention hoặc comment để bảo vệ dữ liệu. Tenant condition cần hiện diện trong query hoặc được enforce bởi một lớp bảo mật thực sự.

## 16. Kiểm tra tenant ownership khi thao tác theo ID

Một request như GET /orders/O-100 chỉ có order ID. Service phải xác định order có thuộc tenant hiện tại hay không.

Một cách là query theo cả ID và tenant ID:

~~~java
public Optional<Order> findOrder(String orderId) {
    String tenantId = currentTenant.requireTenantId();

    return repository.findByIdAndTenantId(
        orderId,
        tenantId
    );
}
~~~

Nếu kết quả rỗng, API có thể trả not found theo chính sách để không tiết lộ document của tenant khác. Nếu policy yêu cầu phân biệt forbidden và not found, chỉ làm vậy sau khi đã kiểm tra quyền một cách an toàn.

Không dùng việc ID khó đoán như biện pháp authorization. ID có thể xuất hiện trong log, URL, message hoặc dữ liệu được chia sẻ.

Với custom routing, get/update/delete cần đúng routing value. Việc route đúng chỉ giúp tìm document; service vẫn phải kiểm tra ownership và quyền hành động.

## 17. Bulk operations và tenant isolation

Bulk request có thể chứa nhiều operation, mỗi operation có routing value riêng. Đây là nơi lỗi tenant scope dễ bị che giấu nếu chỉ kiểm tra request tổng thể.

Trước khi tạo bulk request:

1. Xác định tenant cho từng record từ nguồn đáng tin cậy.
2. Kiểm tra caller hoặc job identity được phép xử lý tenant đó.
3. Đảm bảo tenantId trong source không mâu thuẫn với tenant context.
4. Gán routing value cho từng item.
5. Giữ metadata source ID, tenant ID và operation type để đối soát.
6. Đọc kết quả từng item và ghi nhận lỗi.

Không cho một client tenant gửi danh sách document với tenantId tùy ý rồi để backend bulk index tất cả. Một thao tác bulk thành công về mặt kỹ thuật có thể vẫn vi phạm ranh giới dữ liệu của ứng dụng.

Với import job có quyền toàn hệ thống, cần có service identity và job scope được xác định rõ. Quyền của job không nên được suy ra từ routing value của từng item.

## 18. Thay đổi routing value và migration

Routing value cần ổn định trong vòng đời document. Nếu thay đổi routing strategy, document có thể phải được chuyển sang shard khác.

Không chỉ sửa field tenantId trong source rồi giả định metadata routing thay đổi theo. Routing metadata quyết định shard đã lưu document; cập nhật source field không tự di chuyển document sang shard mới.

Một quy trình migration có thể gồm:

1. Đọc document từ vị trí cũ với routing cũ.
2. Kiểm tra tenant và version của document.
3. Index document vào đích với routing mới.
4. Xác nhận document mới đã được ghi đúng.
5. Xóa document cũ bằng ID và routing cũ.
6. Đối soát để không còn bản sao ngoài ý muốn.
7. Cập nhật code đọc/ghi theo routing strategy mới.

Nếu dùng reindex, cần cấu hình cách xác định routing đích và kiểm soát xung đột/ghi đồng thời. Kế hoạch migration phải xem xét cả document đang được cập nhật trong lúc chuyển đổi.

## 19. Những rủi ro thường gặp

| Triệu chứng hoặc giả định | Vấn đề | Cách xử lý |
|---|---|---|
| Search có routing nhưng trả document tenant khác | Nhiều tenant cùng shard và query thiếu tenant filter | Thêm tenantId filter bắt buộc |
| Client tự gửi routing value | Caller có thể chọn route của tenant khác | Derive route từ authenticated tenant context |
| Document source có tenantId khác route | Dữ liệu và routing không nhất quán | Gán/validate tenant ở server trước index |
| Get theo ID không tìm thấy document | Request thiếu hoặc sai routing | Dùng routing value đã lưu khi index |
| Update/delete thao tác sai tenant | Chỉ dựa vào ID hoặc route mà thiếu ownership check | Authorize tenant và kiểm tra resource scope |
| Cùng ID xuất hiện hai lần | Index cùng ID với routing khác nhau | Dùng ID toàn cục hoặc tenant-qualified ID |
| _routing.required bị xem là bảo mật | Required chỉ kiểm tra routing có mặt | Thêm authorization và tenant filter |
| Alias được coi là ranh giới bảo mật | Alias routing chỉ điều hướng request | Dùng index privileges và service authorization |
| DLS không cô lập từng end-user | Backend dùng một credential chung | Enforce tenant trong backend hoặc dùng identity riêng |
| Repository findAll bị gọi từ controller | Query không có tenant scope | Đóng repository sau service và giới hạn method |
| Bulk request trộn tenant sai route | Dùng routing chung cho cả batch | Routing và tenant validation theo từng item |
| Đổi tenant ID nhưng giữ document trên shard cũ | Source update không di chuyển routing metadata | Reindex/migrate theo route mới |

## 20. Kiểm thử bảo mật routing và tenant isolation

Kiểm thử phải chứng minh tenant A không đọc, cập nhật hoặc xóa được document tenant B, kể cả khi caller biết ID hoặc thử thay routing value.

Một bộ integration test nên có ít nhất hai tenant. Để chứng minh routing không phải filter, có thể tạo test index với một primary shard để các routing value cùng đi vào shard đó. Khi đó, search chỉ có routing nhưng không có tenant filter sẽ cho thấy document của nhiều tenant trên cùng shard.

Ví dụ dữ liệu:

~~~json
[
  {
    "orderId": "A-100",
    "tenantId": "tenant-A",
    "status": "OPEN"
  },
  {
    "orderId": "B-200",
    "tenantId": "tenant-B",
    "status": "OPEN"
  }
]
~~~

Các kiểm thử cần có:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Tenant A tìm đơn hàng của mình | Chỉ document tenant-A được trả về |
| Tenant A thử thay routing thành tenant-B | Authorization từ chối hoặc service vẫn dùng route tenant-A |
| Tenant A gọi get với ID của tenant-B | Không trả nội dung tenant-B |
| Tenant A update ID của tenant-B | Không thay đổi document tenant-B |
| Tenant A delete ID của tenant-B | Không xóa document tenant-B |
| Search route tenant-A nhưng thiếu tenant filter | Test chứng minh có thể nhìn thấy document khác trên cùng shard |
| Query có routing và tenant filter | Chỉ document tenant-A được trả về |
| Index request gửi tenantId không khớp principal | Bị từ chối hoặc tenantId được server gán lại theo policy |
| Bulk có item tenant không được phép | Item đó bị từ chối và được ghi nhận |
| Request không có authenticated tenant | Không truy cập dữ liệu tenant |
| ID giống nhau với routing khác | Hệ thống ngăn duplicate theo quy tắc ID đã chọn |
| DLS/FLS được bật | Principal chỉ thấy document/field theo role policy |

### Test không nên chỉ mock routing

Mock có thể xác nhận service truyền đúng tham số, nhưng không thể chứng minh shard routing và Query DSL thực tế có semantics mong muốn.

Dùng Elasticsearch integration test tương thích để xác nhận:

- Document được index với routing.
- Get/update/delete cần route tương ứng.
- Search routing chỉ giới hạn shard.
- Tenant filter thực sự loại document của tenant khác.
- Mapping và _routing.required hoạt động đúng.
- Role/DLS/FLS được áp dụng nếu môi trường sử dụng các tính năng đó.

Ngoài integration test, kiểm thử service authorization bằng principal khác nhau để bảo đảm client không thể thay tenant context.

## 21. Checklist triển khai an toàn

- [ ] Hiểu routing là shard selection, không phải access control.
- [ ] Lưu tenantId rõ ràng trong source để filter và audit.
- [ ] Xác định tenant từ principal hoặc membership đã được xác thực.
- [ ] Không tin tenant ID/routing value do client gửi nếu chưa authorize.
- [ ] Gán routing value ở server.
- [ ] Dùng cùng routing value nhất quán cho index và các thao tác theo ID.
- [ ] Thêm tenant filter trong mọi search theo tenant.
- [ ] Kiểm tra ownership cho get/update/delete theo ID.
- [ ] Không expose findAll hoặc raw client cho caller tenant.
- [ ] Đảm bảo ID không tạo duplicate ngoài ý muốn khi routing khác nhau.
- [ ] Dùng _routing.required để phát hiện thiếu routing, không coi đó là authorization.
- [ ] Cấu hình index privileges tối thiểu.
- [ ] Đánh giá DLS/FLS theo version, subscription và identity model.
- [ ] Hiểu backend shared credential không tự phân biệt end-user.
- [ ] Xử lý routing theo từng item trong bulk request.
- [ ] Có migration plan khi thay đổi routing strategy.
- [ ] Có integration test nhiều tenant trên cùng shard.
- [ ] Kiểm thử cả read, update, delete và index authorization.
- [ ] Ghi log đủ để audit nhưng không làm lộ payload nhạy cảm.

Routing có thể giúp Elasticsearch phân phối document và giảm số shard cần tìm kiếm. Nó không xác minh danh tính, không kiểm tra tenant membership và không tự lọc document trong shard. Một hệ thống Spring Data Elasticsearch an toàn cần lấy tenant từ identity đã xác thực, kiểm tra quyền ở service/security layer, thêm tenant filter bắt buộc vào query và dùng routing server-side như một tối ưu điều hướng. Roles, index privileges và DLS/FLS có thể bổ sung lớp bảo vệ tại Elasticsearch khi kiến trúc identity phù hợp, nhưng routing value tự nó không bao giờ là bằng chứng quyền truy cập.

