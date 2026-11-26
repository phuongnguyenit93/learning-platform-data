# Pagination cache trong Spring HATEOAS

API phân trang thường được gọi lặp lại với cùng bộ lọc, thứ tự sắp xếp và số trang. Nếu mỗi request đều truy vấn database, dựng DTO, tạo link hypermedia và serialize HAL từ đầu, collection lớn có thể tạo tải đáng kể. Cache giúp giảm chi phí này, nhưng cache response phân trang cần được thiết kế cẩn thận vì mỗi trang là một phần của cùng collection và có thể thay đổi khi bản ghi được thêm, sửa hoặc xóa.

Trong Spring HATEOAS, một page response không chỉ chứa item. Nó còn có page metadata, self/next/prev links, filter và sort context, có thể có link tùy quyền người dùng. Vì vậy, cache cần phân biệt chính xác từng truy vấn và không được tái sử dụng representation có link hoặc dữ liệu của người dùng khác. Bài này trình bày cách cache dữ liệu phân trang ở tầng ứng dụng, dùng HTTP caching với ETag và Cache-Control, quản lý invalidation, xử lý link bị cũ và kiểm thử các trường hợp quan trọng.

## 1. Vì sao cần cache pagination?

Giả sử endpoint GET /orders hỗ trợ page, size, sort và filter status. Một màn hình quản trị có thể tải trang đầu nhiều lần khi người dùng quay lại, refresh hoặc mở cùng danh sách ở nhiều tab. Các request giống nhau có thể tạo ra cùng kết quả trong một khoảng thời gian ngắn.

Không cache, mỗi request có thể thực hiện:

1. Kiểm tra quyền truy cập và phạm vi tenant.
2. Chạy truy vấn lọc và sắp xếp.
3. Đếm tổng số bản ghi để tạo page metadata.
4. Chuyển entity thành DTO.
5. Tạo link cho collection và từng item.
6. Serialize PagedModel thành HAL JSON.

Cache đúng vị trí giúp giảm truy vấn lặp, giảm CPU serialize và cải thiện độ trễ. Tuy nhiên, dữ liệu phân trang nhạy với thay đổi collection: thêm một đơn mới có thể đẩy item cuối trang 0 sang trang 1, làm thay đổi cả hai trang và các metadata liên quan.

## 2. Phân biệt application cache và HTTP cache

Có hai lớp cache thường gặp:

| Lớp cache | Cache gì? | Nằm ở đâu? | Ví dụ |
| --- | --- | --- | --- |
| Application cache | Kết quả truy vấn hoặc DTO của một trang | Trong service, Caffeine, Redis hoặc cache provider khác | Page<OrderSummary> cho tenant A, status PENDING, page 0. |
| HTTP cache | HTTP representation cùng validator và freshness metadata | Browser, reverse proxy hoặc CDN theo chính sách | HAL response cho URI /orders?page=0&size=20. |

Application cache giảm công việc ở server trước khi tạo response. HTTP cache có thể tránh request tới origin trong thời gian response còn fresh; conditional request có thể giúp client nhận 304 Not Modified khi nội dung chưa đổi.

Hai lớp có thể dùng đồng thời. Ví dụ application cache giữ Page<OrderSummary>, controller dựng PagedModel và link theo request hiện tại, sau đó HTTP layer trả ETag và Cache-Control. Không nên mặc định cache một PagedModel hoàn chỉnh là lựa chọn tốt nhất; representation có thể chứa absolute URI, link phụ thuộc người dùng hoặc metadata theo request.

## 3. Cache key phải nhận diện đầy đủ một trang

Cache key là điều kiện quan trọng nhất. Hai request chỉ được dùng chung cache entry nếu chúng có cùng phạm vi dữ liệu và cùng cách trình bày kết quả.

Với endpoint phân trang, key thường cần bao gồm:

- Page number.
- Page size.
- Sort fields, directions và thứ tự ưu tiên.
- Tất cả filter ảnh hưởng tới kết quả.
- Tenant hoặc phạm vi dữ liệu của principal nếu dữ liệu bị phân vùng.
- Locale nếu nội dung trả về phụ thuộc ngôn ngữ.
- Version/profile nếu representation khác nhau theo version.

Ví dụ hai request sau không được dùng chung cache entry:

~~~http
GET /orders?status=PENDING&page=0&size=20&sort=createdAt,desc
GET /orders?status=SHIPPED&page=0&size=20&sort=createdAt,desc
~~~

Chúng có cùng page và size nhưng tập dữ liệu khác nhau. Tương tự, page 0 và page 1, size 20 và size 50, hoặc sort ASC và DESC đều cần key riêng.

Với HTTP cache, URI đầy đủ bao gồm query string thường là một phần của cache key. Với application cache, bạn phải tự xây key hoặc dùng KeyGenerator để tránh bỏ sót filter hay tenant.

## 4. Chuẩn hóa sort và filter trước khi tạo key

Hai request có thể mang cùng semantics nhưng query parameter được sắp xếp theo thứ tự khác nhau. Ví dụ:

~~~http
GET /orders?status=PENDING&customerId=c-7&page=0
GET /orders?customerId=c-7&page=0&status=PENDING
~~~

HTTP cache có thể xem hai URI khác nhau là hai cache key khác nhau. Đây không phải lỗi correctness, nhưng có thể làm giảm cache hit rate. Application cache có thể chuẩn hóa filter thành một key object với field cố định.

Sort cũng cần được canonicalize theo đúng thứ tự sort thực tế. Không được sắp xếp lại danh sách sort order tùy tiện vì:

~~~text
sort=createdAt,desc&sort=id,asc
~~~

không tương đương với thứ tự ưu tiên ngược lại.

Hãy chuẩn hóa giá trị mặc định trước khi tạo key. Ví dụ request không truyền size và request truyền size bằng default có thể được xem là cùng truy vấn nếu resolver thực sự áp dụng cùng page size. Đừng chuẩn hóa trước khi áp dụng chính sách pageable vì default và maximum size có thể thay đổi kết quả.

## 5. Cache kết quả trang ở tầng service

Một cách phổ biến là cache Page<DTO> hoặc một cấu trúc dữ liệu bất biến ở tầng service. Controller tiếp tục tạo PagedModel cho mỗi request.

Ví dụ:

~~~java
@Service
class OrderQueryService {

    private final OrderRepository repository;

    OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
            cacheNames = "orderPages",
            key = "#tenantId + ':' + #status + ':' + #pageable.pageNumber + ':' + #pageable.pageSize + ':' + #pageable.sort"
    )
    Page<OrderSummary> findPage(
            UUID tenantId,
            OrderStatus status,
            Pageable pageable) {

        return repository.findSummaries(tenantId, status, pageable);
    }
}
~~~

Ví dụ dùng key dạng chuỗi để làm rõ các thành phần. Với nhiều filter, nên tạo một key object hoặc KeyGenerator riêng để tránh SpEL dài và bảo đảm canonicalization nhất quán. Sort phải được biểu diễn theo thứ tự ưu tiên, không chỉ lấy một thuộc tính sort đầu tiên.

Bật cache annotation:

~~~java
@Configuration
@EnableCaching
class CacheConfiguration {
}
~~~

Ứng dụng cũng cần cấu hình cache provider như Caffeine hoặc Redis. Không dùng cache mặc định trong production mà không xác định giới hạn dung lượng, TTL, serialization và chiến lược eviction.

## 6. Không bỏ tenant và authorization scope khỏi cache key

Nếu cùng một URI có thể trả dữ liệu khác nhau theo tenant hoặc người dùng, cache key phải tách các phạm vi đó. Ví dụ tenant A và tenant B cùng gọi page 0, status PENDING; kết quả của họ không được chia sẻ.

Không lấy tenantId trực tiếp từ query parameter do client tự gửi rồi tin tưởng nó. Server cần xác định tenant từ principal hoặc authorization context, sau đó đưa tenant đã được xác thực vào truy vấn và cache key.

Nếu trong cùng một tenant, dữ liệu truy vấn còn bị giới hạn theo người dùng hoặc nhóm quyền, key cần thêm user ID/security scope tương ứng. Ví dụ có thể mở rộng key thành tenantId + principalId + filter + pageable. Không cần thêm principalId nếu mọi người trong tenant thực sự nhận cùng một tập dữ liệu; chỉ đưa vào key những yếu tố làm kết quả cache khác nhau.

Với representation chứa link theo quyền, cần cẩn thận hơn nữa. Hai người dùng có thể đọc cùng dữ liệu nhưng có quyền thao tác khác nhau, dẫn tới một người có link cancel còn người kia không có. Cache chung PagedModel có thể làm lộ link thao tác hoặc ẩn nhầm link.

Các lựa chọn an toàn:

- Cache dữ liệu trang đã được giới hạn theo tenant và quyền đọc.
- Tạo link/affordance theo principal của request sau khi lấy dữ liệu cache.
- Cache riêng representation theo security scope nếu thực sự cần.
- Dùng Cache-Control private hoặc no-store cho response cá nhân hóa.

Không bao giờ dùng cache shared/public cho response chứa dữ liệu riêng tư hoặc action link khác nhau theo người dùng.

## 7. Tạo PagedModel sau khi lấy page từ cache

Spring HATEOAS có thể dùng PagedResourcesAssembler để chuyển Spring Data Page thành PagedModel. Cách này giúp giữ page metadata và pagination links nhất quán.

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderQueryService queryService;
    private final OrderSummaryAssembler assembler;
    private final PagedResourcesAssembler<OrderSummary> pagedAssembler;
    private final TenantProvider tenantProvider;

    @GetMapping
    PagedModel<EntityModel<OrderSummary>> all(
            @RequestParam(required = false) OrderStatus status,
            Pageable pageable) {

        UUID tenantId = tenantProvider.currentTenantId();
        Page<OrderSummary> page =
                queryService.findPage(tenantId, status, pageable);

        return pagedAssembler.toModel(page, assembler);
    }
}
~~~

Ví dụ dùng TenantProvider để lấy tenant từ security context hoặc một TenantContext đã được xác thực. Không nhận tenantId tùy ý từ query parameter rồi dùng nó làm phạm vi truy vấn hoặc cache key.

Assembler tạo item model và link dựa trên request hiện tại. Nhờ vậy, cache giữ phần dữ liệu ổn định, còn self/next/prev links được tạo lại theo mapping và request context hiện tại.

## 8. Khi nào nên cache toàn bộ HAL representation?

Cache nguyên response HAL có thể hữu ích khi representation công khai, giống nhau cho mọi client và có chi phí serialize lớn. Tuy nhiên, nó mang theo nhiều yếu tố cần xem xét:

- Self link có thể chứa host, scheme hoặc context path theo request.
- Pagination links có thể mang filter, sort và query parameter.
- Affordance có thể thay đổi theo role hoặc trạng thái nghiệp vụ.
- Link association có thể phụ thuộc cấu hình hoặc quyền.
- Content negotiation có thể tạo representation HAL và JSON khác nhau.
- Locale hoặc profile có thể làm payload khác nhau.

Nếu cache cả PagedModel, cache key phải nhận diện mọi yếu tố làm response thay đổi. Nếu không, response được tạo cho request trước có thể chứa link sai host, sai query, sai quyền hoặc sai media type.

Với API cá nhân hóa, ưu tiên cache page data rồi tạo hypermedia controls theo request. Nếu vẫn cache toàn bộ representation, hãy giới hạn cache theo security scope và kiểm thử response của các principal khác nhau.

## 9. HTTP Cache-Control cho response phân trang

Cache-Control xác định response có thể được lưu ở đâu và khi nào cần revalidate.

| Directive | Ý nghĩa | Trường hợp dùng |
| --- | --- | --- |
| public | Shared cache có thể lưu response nếu các điều kiện khác cho phép. | Collection công khai, giống nhau cho mọi người. |
| private | Chỉ private cache như browser được lưu response. | Dữ liệu theo người dùng đã đăng nhập. |
| max-age=N | Response được xem là fresh trong N giây. | Dữ liệu có thể chấp nhận độ trễ cập nhật ngắn. |
| s-maxage=N | Freshness lifetime cho shared cache. | CDN/reverse proxy có chính sách riêng. |
| no-cache | Có thể lưu nhưng phải revalidate trước khi dùng lại. | Dữ liệu cần kiểm tra validator mỗi lần. |
| no-store | Không được lưu response. | Dữ liệu nhạy cảm hoặc không muốn lưu trên cache. |
| must-revalidate | Khi hết hạn, cache phải revalidate trước khi dùng lại. | Không được dùng response stale tùy tiện. |

no-cache không có nghĩa là không lưu; directive đó yêu cầu kiểm tra lại trước khi tái sử dụng. no-store mới yêu cầu không lưu response.

Ví dụ response public:

~~~http
Cache-Control: public, max-age=30, s-maxage=60
~~~

Ví dụ response riêng tư cần revalidate:

~~~http
Cache-Control: private, no-cache
~~~

Ví dụ response nhạy cảm:

~~~http
Cache-Control: no-store
~~~

Chọn freshness theo mức độ thay đổi dữ liệu và yêu cầu nghiệp vụ. Trang báo cáo công khai có thể cache lâu hơn danh sách đơn hàng đang được cập nhật liên tục.

## 10. Vary và content negotiation

Nếu cùng URI có thể trả HAL hoặc representation khác tùy Accept header, cache cần phân biệt các biến thể. Response nên có:

~~~http
Vary: Accept
~~~

Nếu payload phụ thuộc ngôn ngữ, có thể cần Vary: Accept-Language. Nếu representation phụ thuộc header version như X-API-Version, cache phải phân biệt header đó, thường qua Vary tương ứng hoặc cấu hình cache key riêng.

Không thêm Vary cho mọi header một cách máy móc vì có thể làm giảm cache hit rate. Chỉ khai báo những request header thực sự ảnh hưởng representation.

Với response cá nhân hóa theo Authorization, ưu tiên Cache-Control private hoặc no-store. Không cho rằng chỉ thêm Vary: Authorization đã đủ để bảo vệ mọi shared cache; phải tuân theo semantics HTTP caching và cấu hình proxy/CDN.

## 11. ETag cho từng trang

ETag là validator nhận diện một phiên bản representation. Client lưu ETag nhận được và gửi lại trong If-None-Match khi request cùng resource. Nếu representation chưa thay đổi, server có thể trả 304 Not Modified mà không gửi lại body.

Với pagination, mỗi URI truy vấn là một representation riêng. ETag của:

~~~text
/orders?page=0&size=20&sort=createdAt,desc
~~~

không nên được dùng lại cho:

~~~text
/orders?page=1&size=20&sort=createdAt,desc
~~~

ETag cần phản ánh nội dung và metadata của trang tương ứng. Nếu response có absolute links, embedded data, page totals hoặc affordance theo quyền, các yếu tố đó có thể làm representation thay đổi và cần được tính vào validator.

Một ETag mạnh thường nhận diện chính xác representation bytes; weak ETag có thể dùng khi chỉ cần so sánh tương đương về ngữ nghĩa. Đừng tạo ETag từ Object.hashCode() không ổn định hoặc chỉ từ page number. Có thể dùng digest của serialized representation hoặc một collection revision/version đáng tin cậy.

## 12. Conditional GET và 304 Not Modified

Luồng conditional GET:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring MVC API
    participant D as Data source/cache
    C->>S: GET /orders?page=0
    S->>D: Lấy dữ liệu trang và revision
    D-->>S: Page + revision
    S-->>C: 200 HAL + ETag
    Note over C: Lưu response và ETag
    C->>S: GET /orders?page=0 + If-None-Match
    S->>D: Kiểm tra revision hiện tại
    D-->>S: Revision không đổi
    S-->>C: 304 Not Modified
    Note over C: Dùng lại body đã cache
~~~

Khi ETag còn hợp lệ, server trả 304 và client dùng body đã lưu. Response 304 không gửi lại PagedModel. Nếu dữ liệu trang thay đổi, server trả 200 với representation và ETag mới.

Để conditional GET tiết kiệm được chi phí database, server cần xác định validator trước khi tải toàn bộ page. Nếu ETag chỉ được tính sau khi truy vấn và serialize toàn bộ response, client vẫn tiết kiệm băng thông nhưng server chưa tiết kiệm được toàn bộ công việc.

## 13. Dùng ShallowEtagHeaderFilter

Spring Framework cung cấp ShallowEtagHeaderFilter để tính ETag từ nội dung response và hỗ trợ conditional GET. Đây là cách nhanh để thêm validator cho response MVC mà không tự xây thuật toán hash.

Filter đọc nội dung response được render rồi tính ETag. Vì vậy, nó có thể giảm băng thông khi client nhận 304, nhưng controller, service và serialization vẫn có thể đã chạy trước khi filter xác định response không đổi. Với endpoint phân trang truy vấn đắt, validator dựa trên revision/version trước khi dựng body có thể hiệu quả hơn.

Ví dụ đăng ký filter:

~~~java
@Bean
FilterRegistrationBean<ShallowEtagHeaderFilter> shallowEtagFilter() {
    FilterRegistrationBean<ShallowEtagHeaderFilter> registration =
            new FilterRegistrationBean<>(new ShallowEtagHeaderFilter());
    registration.addUrlPatterns("/orders/*");
    return registration;
}
~~~

Kiểm tra cấu hình thực tế để bảo đảm filter được đăng ký đúng một lần và không xung đột với filter khác. Nếu dùng filter cho response có nội dung lớn, hãy cân nhắc chi phí buffering response body.

## 14. Last-Modified và collection revision

Last-Modified là validator dựa trên thời điểm sửa đổi. Với item resource, trường updatedAt có thể phù hợp. Với một trang collection, chỉ lấy updatedAt lớn nhất của các item hiện đang ở trang có thể sai:

- Một item bị xóa sẽ không còn để tính thời điểm sửa đổi.
- Một item mới được thêm có thể đẩy item khác sang trang.
- Một thay đổi filter hoặc association có thể làm kết quả thay đổi.
- Page total có thể thay đổi dù item trong trang không đổi.

Vì vậy, trang phân trang thường cần collection revision hoặc một timestamp phản ánh mọi thay đổi có thể ảnh hưởng truy vấn. Ví dụ tenant có một orderCatalogVersion tăng sau mỗi thao tác create/update/delete liên quan.

Khi tính Last-Modified, phải bảo đảm độ phân giải thời gian phù hợp. HTTP date thường có độ phân giải giây; nhiều thay đổi trong cùng một giây có thể khiến validator không phân biệt được. ETag thường phù hợp hơn khi cần nhận diện chính xác nhiều phiên bản liên tiếp.

## 15. Invalidation khi collection thay đổi

Cache pagination dễ bị stale sau các thao tác ghi:

| Thay đổi | Cache entry có thể bị ảnh hưởng |
| --- | --- |
| Tạo đơn hàng | Trang đầu, các trang sau do item bị dịch chuyển, totalElements và totalPages. |
| Xóa đơn hàng | Các trang tại và sau vị trí item bị xóa, page totals. |
| Đổi trạng thái | Các trang của filter trạng thái cũ và mới. |
| Đổi khách hàng/tenant association | Các trang lọc theo customer hoặc tenant liên quan. |
| Đổi trường sort | Thứ tự và ranh giới trang có thể thay đổi. |
| Thay đổi quyền | Representation có link/affordance phụ thuộc quyền. |

Chiến lược đơn giản là evict toàn bộ cache orderPages sau mutation thành công:

~~~java
@CacheEvict(cacheNames = "orderPages", allEntries = true)
public void updateOrder(UUID orderId, UpdateOrderCommand command) {
    // Thực hiện cập nhật.
}
~~~

Cách này dễ đúng nhưng có thể làm mất nhiều cache entry. Với hệ thống lớn, có thể dùng cache key theo tenant, tag invalidation, generation version hoặc cache region riêng cho từng nhóm truy vấn.

Với method không có transaction bao ngoài, @CacheEvict mặc định chạy sau khi method kết thúc thành công. Nếu method được bọc trong transaction và cần đồng bộ chặt với commit, hãy phối hợp invalidation ở giai đoạn after-commit bằng transaction synchronization hoặc domain event:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderChanged(OrderChanged event) {
    cacheManager.getCache("orderPages").clear();
}
~~~

Nếu cache bị evict trước commit rồi transaction rollback, cache hit rate giảm nhưng dữ liệu vẫn đúng; nếu cache được cập nhật bằng dữ liệu chưa commit, có nguy cơ công bố trạng thái chưa được xác nhận. Với distributed cache, event after-commit cần được chuyển tới cache provider một cách tin cậy.

## 16. Dùng generation version để tránh quét mọi page key

Một chiến lược khác là gắn collection generation vào cache key. Mỗi lần dữ liệu liên quan thay đổi, tăng generation của collection/tenant. Key của trang bao gồm generation hiện tại:

~~~text
orders:tenant-A:generation-42:status-PENDING:page-0:size-20:sort-createdAt-desc
~~~

Sau mutation, generation tăng lên 43. Các request mới dùng key mới nên không đọc entry thuộc generation 42 nữa. Entry cũ sẽ được dọn khi TTL hết hạn hoặc cache eviction xảy ra.

Ưu điểm là không cần tìm mọi tổ hợp page/filter/sort để xóa. Đổi lại, generation phải được cập nhật nhất quán và không được cache quá lâu theo cách khiến client dùng generation cũ. Với nhiều node, generation cần lưu ở nơi chia sẻ như database hoặc Redis.

## 17. Offset pagination và rủi ro stale page

Offset pagination chia collection thành các lát theo vị trí. Khi một item mới được thêm ở đầu danh sách, các item ở mọi trang sau có thể dịch chuyển. Cache page 1 trước khi insert có thể chứa một item đã chuyển sang page 2 sau insert.

Đây là lý do TTL dài không phù hợp với collection thay đổi thường xuyên. Hãy chọn TTL theo tốc độ cập nhật và mức độ chấp nhận dữ liệu cũ. Với collection cần nhất quán mạnh, invalidate ngay khi mutation commit hoặc dùng version/revision để phát hiện thay đổi.

Keyset/cursor pagination giảm một số vấn đề dịch chuyển vị trí bằng cách tiếp tục từ khóa sắp xếp cuối cùng, nhưng cache key vẫn cần chứa cursor, sort và filter. Cursor cũng có thể hết hạn hoặc không còn hợp lệ khi dữ liệu thay đổi tùy semantics của API.

## 18. Pagination links cũng có thể trở nên cũ

PagedModel chứa links self, first, prev, next và last. Nếu cache nguyên PagedModel trong thời gian dài, các link có thể không còn phản ánh collection hiện tại:

- Trang cuối có thể đã thay đổi sau khi thêm/xóa item.
- next link có thể dẫn tới trang không còn tồn tại.
- Filter/sort context có thể đã lỗi thời.
- Absolute host hoặc context path có thể thuộc request trước.
- Link thao tác có thể không còn hợp lệ do trạng thái hoặc quyền đã thay đổi.

Cache dữ liệu trang và tạo PagedModel theo request giúp giảm rủi ro link theo host/request. Tuy vậy, page content vẫn có thể stale và metadata pagination vẫn có thể cũ. Khi cần tính nhất quán cao, hãy gắn page result với collection revision và kiểm tra revision trước khi sử dụng cache entry.

Không cache affordance hoặc action link theo quyền người dùng chung giữa nhiều principal. Nếu link được tạo từ policy, hãy tính lại theo request hoặc phân vùng cache theo security scope đã xác thực.

## 19. Cache error response và trang rỗng

Không phải mọi response đều nên cache giống nhau:

- Collection rỗng có thể cache ngắn nếu kết quả ít thay đổi.
- Page index vượt quá trang cuối có thể trả page rỗng hoặc lỗi theo hợp đồng; cần thống nhất và test.
- 401/403 không nên bị cache chung như response thành công.
- 404 có thể cache theo HTTP semantics nhưng phải cân nhắc khi resource được tạo ngay sau đó.
- 5xx và timeout thường không nên lưu lâu trong application cache.

Với page rỗng do filter không có kết quả, key vẫn phải chứa filter. Không dùng một cache entry rỗng cho mọi truy vấn. Khi một bản ghi mới được tạo và thỏa filter, cache rỗng cũ cần được invalidate hoặc hết TTL.

## 20. Kiểm thử cache key ở tầng service

Kiểm thử application cache nên xác nhận request giống nhau dùng lại cache, còn thay đổi một thành phần quan trọng sẽ tạo entry khác.

Ví dụ ý tưởng test:

~~~java
@Test
void cachesSamePageButSeparatesDifferentFilters() {
    service.findPage(tenantA, PENDING, page0);
    service.findPage(tenantA, PENDING, page0);
    service.findPage(tenantA, SHIPPED, page0);

    verify(repository, times(2))
            .findSummaries(any(), any(), any());
}
~~~

Test giả định cache đã được bật trong test context và repository là mock. Hai lần gọi cùng tenant/filter/page chỉ truy vấn một lần; filter khác phải truy vấn lần nữa. Bổ sung test riêng cho page number, size, sort, tenant và các filter khác.

Nếu dùng KeyGenerator, kiểm thử key cho hai Pageable có cùng semantics và hai Pageable khác sort order. Không chỉ test rằng cache hit; cần chứng minh không có cache collision giữa hai phạm vi dữ liệu khác nhau.

## 21. Kiểm thử Cache-Control, ETag và conditional GET

MockMvc có thể xác nhận header caching:

~~~java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(header().string(
            HttpHeaders.CACHE_CONTROL,
            containsString("private")))
    .andExpect(header().exists(HttpHeaders.ETAG))
    .andExpect(header().string(
            HttpHeaders.VARY,
            containsString("Accept")));
~~~

Sau khi lấy ETag từ response đầu tiên, gửi conditional request:

~~~java
MvcResult first = mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

String etag = first.getResponse().getHeader(HttpHeaders.ETAG);

mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "20")
        .header(HttpHeaders.IF_NONE_MATCH, etag)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isNotModified());
~~~

Test giả định controller hoặc filter hỗ trợ ETag và response chưa thay đổi giữa hai request. Nếu ETag được tính từ revision, hãy test thêm mutation làm revision thay đổi và request tiếp theo trả 200 với ETag mới.

## 22. Kiểm thử cache isolation và authorization

Cache isolation cần được test như một yêu cầu bảo mật:

1. Principal A gọi trang dữ liệu thuộc tenant A.
2. Principal B gọi cùng URI nhưng thuộc tenant B.
3. Xác nhận B không nhận content của A.
4. Nếu link thao tác phụ thuộc role, xác nhận mỗi principal nhận links đúng policy.
5. Gửi lại request dưới principal khác sau khi cache đã warm.

Nếu response cá nhân hóa, test header Cache-Control phải xác nhận private hoặc no-store theo policy. Không chỉ kiểm tra body vì shared cache có thể tái sử dụng response cho người khác dù lần request đầu trả đúng.

## 23. Các lỗi thường gặp

**Cache key chỉ chứa page number.** Thêm size, sort, filter và phạm vi tenant/security vào key.

**Bỏ tenant hoặc principal khỏi cache key.** Có thể làm lộ dữ liệu giữa tenant hoặc tạo link theo quyền của người khác.

**Cache nguyên PagedModel quá lâu.** Page metadata và pagination links có thể cũ; cân nhắc cache page data rồi tạo links theo request.

**Dùng ETag chỉ từ page number.** ETag phải phản ánh nội dung/metadata của representation hoặc collection revision đáng tin cậy.

**Dùng Last-Modified từ item mới nhất trên page.** Delete hoặc insert có thể làm page thay đổi mà timestamp tính từ item hiện tại không phát hiện được.

**Hiểu no-cache là không lưu.** no-cache yêu cầu revalidate; no-store mới cấm lưu response.

**Không có Vary khi representation phụ thuộc Accept.** Cache có thể trả nhầm HAL hoặc representation khác.

**Chỉ invalidate trang đầu.** Insert/delete có thể dịch chuyển item và thay đổi tổng số trang ở nhiều page.

**Evict cache trước khi transaction commit.** Có thể tạo trạng thái cache không đồng bộ với dữ liệu đã commit; chọn thời điểm invalidation phù hợp.

**Dùng TTL dài để thay thế invalidation.** TTL chỉ giới hạn thời gian stale; nó không bảo đảm dữ liệu luôn mới trong thời hạn đó.

**Cache 401/403 hoặc 5xx như dữ liệu thành công.** Chọn policy cache riêng cho lỗi và response rỗng.

## 24. Bài tập thực hành và tiêu chí hoàn thành

Hãy triển khai cache cho endpoint GET /orders:

1. Tạo service trả Page<OrderSummary> và bật Spring Cache.
2. Thiết kế cache key có tenant, filter, page, size và sort.
3. Viết test chứng minh request giống nhau cache hit, request khác filter/page/tenant cache miss.
4. Dùng PagedResourcesAssembler tạo PagedModel từ page đã cache.
5. Chỉ tạo security-sensitive links theo principal hiện tại.
6. Cấu hình Cache-Control private hoặc no-store cho response cá nhân hóa.
7. Thêm ETag hoặc ShallowEtagHeaderFilter và kiểm thử conditional GET.
8. Thêm Vary: Accept nếu cùng URI trả nhiều media type.
9. Tạo mutation test xác nhận create/update/delete làm cache invalidation hoặc generation thay đổi.
10. Kiểm tra insert/delete làm thay đổi item, totalElements, totalPages và next/prev links.
11. Kiểm thử cache isolation giữa hai tenant và hai role.
12. Đánh giá TTL, cache size, eviction và cách xử lý khi cache provider mất kết nối.

Bạn đã nắm được pagination cache khi có thể nhận diện đầy đủ một trang bằng cache key, tách dữ liệu trang khỏi hypermedia controls phụ thuộc request, chọn đúng HTTP caching directive, dùng validator để revalidate, invalidate khi collection thay đổi và kiểm thử không rò rỉ dữ liệu giữa tenant hoặc người dùng. Cache hiệu quả phải giữ đúng semantics của page content, metadata và các link mà client dùng để điều hướng.

## Tài liệu tham khảo chính thức

- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework – HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html)
- [Spring HATEOAS Reference Documentation – Paged resources](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.paged-resources)
- [Spring Data Commons – Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
