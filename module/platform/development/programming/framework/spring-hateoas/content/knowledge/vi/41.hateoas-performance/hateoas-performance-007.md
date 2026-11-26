# Cache assembler

Representation assembler trong Spring HATEOAS chuyển dữ liệu domain hoặc DTO thành representation có hypermedia: field dữ liệu, self link, collection link, action link và affordance. Khi endpoint được gọi nhiều lần, việc tải dữ liệu, mapping DTO và tạo link có thể trở thành một phần đáng kể của chi phí xử lý. Cache có thể giảm công việc lặp lại, nhưng cache trực tiếp kết quả assembler cần được thiết kế cẩn thận vì representation không chỉ phụ thuộc vào order hay customer.

Một assembler thường tạo link theo request hiện tại, quyền của người dùng, tenant, locale, API version và trạng thái nghiệp vụ. Hai request đến cùng một resource URI có thể cần nhận hai representation khác nhau. Nếu cache chỉ theo resource ID, server có thể trả link sai host, sai phiên bản, sai ngôn ngữ hoặc thậm chí công bố hành động mà người dùng hiện tại không được phép thực hiện.

## Assembler nằm ở đâu trong luồng request?

Một endpoint HATEOAS thường đi qua các bước:

~~~text
HTTP request
    |
    v
Controller
    |
    v
Query / application service
    |
    v
Domain model or read projection
    |
    v
Representation assembler
    |
    +--> DTO fields
    +--> self / collection links
    +--> action links and affordances
    |
    v
HAL serialization
    |
    v
HTTP response
~~~

Assembler thường không truy vấn database trực tiếp. Nó nhận dữ liệu đã được tải, chuyển thành representation và gắn link. Tuy nhiên, nếu mỗi lần gọi assembler lại cần thêm truy vấn để kiểm tra quyền, tải thông tin liên quan hoặc tính toán trạng thái, chi phí có thể tăng nhanh.

Trước khi cache, hãy đo thời gian và số lần gọi ở từng bước. Nếu chậm do query database, cache query result hoặc read projection. Nếu chậm do tính toán DTO thuần túy và kết quả không phụ thuộc request, có thể cân nhắc cache projection đã chuẩn hóa. Nếu phần tốn chi phí là link generation, hãy xem lại cách tạo link và cấu trúc assembler trước khi lưu cả representation.

## Phân biệt các lớp cache

Không phải mọi cache đều lưu cùng một loại dữ liệu:

| Lớp cache | Dữ liệu lưu | Ví dụ |
| --- | --- | --- |
| Domain/read-model cache | Dữ liệu hoặc projection đã tải từ service/repository | OrderSnapshot theo order ID và revision. |
| Assembler/representation cache | Model đã map hoặc representation đã có link | EntityModel<OrderDto> hoặc cấu trúc representation bất biến. |
| HTTP response cache | Body và metadata HTTP của response | HAL JSON cùng ETag và Cache-Control. |

Spring Cache với @Cacheable là application cache. Nó không tự thiết lập Cache-Control, ETag hoặc invalidation ở browser/CDN. Ngược lại, HTTP cache không tự làm giảm số lần assembler chạy nếu server vẫn phải tạo body trước khi xác định response có thể trả 304.

Trong nhiều ứng dụng, lựa chọn an toàn và dễ bảo trì là cache dữ liệu hoặc projection đầu vào, rồi chạy assembler trên mỗi request. Cách này giữ các link theo đúng request context mà vẫn tránh tải lại dữ liệu đắt tiền.

## Vì sao cache trực tiếp EntityModel có thể sai?

Giả sử assembler tạo model cho order:

~~~java
EntityModel<OrderDto> model = EntityModel.of(
        dto,
        linkTo(methodOn(OrderController.class).one(orderId)).withSelfRel());
~~~

Link được tạo từ mapping controller và request context. Tùy cách triển khai, URI có thể bị ảnh hưởng bởi scheme, host, port, context path và forwarded headers. Nếu representation đầu tiên được tạo qua host api-a.example.com rồi cache theo order ID, request tiếp theo qua api-b.example.com có thể nhận href của host đầu tiên.

Ngoài host, representation còn có thể thay đổi theo:

- **Principal và authorization:** người quản lý thấy approve link, người xem chỉ thấy self link.
- **Tenant:** collection hoặc link liên quan chỉ hợp lệ trong tenant hiện tại.
- **Trạng thái domain:** order PENDING có thể có approve/cancel; order APPROVED có thể có ship.
- **Locale:** title, label hoặc nội dung được nhúng có thể được dịch.
- **API version:** DTO, route và relation có thể khác giữa v1 và v2.
- **Media type:** HAL và HAL-FORMS có cấu trúc hoặc affordance khác nhau.
- **Query context:** page, filter, sort và projection có thể làm thay đổi collection links.

Nếu key không phân biệt những yếu tố ảnh hưởng body, cache có thể trả một representation hợp lệ về mặt JSON nhưng sai về ngữ nghĩa hoặc quyền truy cập.

## Chiến lược khuyến nghị: cache projection, assemble theo request

Tách dữ liệu ổn định khỏi hypermedia metadata. Query service trả một projection bất biến có thể cache; assembler nhận projection đó và tạo link mới theo request hiện tại.

Projection:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderSnapshot(
        UUID id,
        String status,
        BigDecimal total,
        long revision) {
}
~~~

Query service cache projection theo ID:

~~~java
import java.util.UUID;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
class OrderSnapshotQueryService {

    private final OrderRepository orderRepository;

    OrderSnapshotQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Cacheable(cacheNames = "orderSnapshots", key = "#p0")
    public OrderSnapshot findSnapshot(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        return new OrderSnapshot(
                order.getId(),
                order.getStatus().name(),
                order.getTotal(),
                order.getVersion());
    }
}
~~~

Assembler tạo representation mỗi lần:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderSnapshot, EntityModel<OrderSnapshot>> {

    @Override
    public EntityModel<OrderSnapshot> toModel(OrderSnapshot order) {
        return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel());
    }
}
~~~

Facade phối hợp query và assembler:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Service;

@Service
class OrderRepresentationService {

    private final OrderSnapshotQueryService queryService;
    private final OrderModelAssembler assembler;

    OrderRepresentationService(
            OrderSnapshotQueryService queryService,
            OrderModelAssembler assembler) {
        this.queryService = queryService;
        this.assembler = assembler;
    }

    EntityModel<OrderSnapshot> findById(UUID orderId) {
        OrderSnapshot snapshot = queryService.findSnapshot(orderId);
        return assembler.toModel(snapshot);
    }
}
~~~

Controller chỉ gọi facade:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderRepresentationService representationService;

    OrderController(OrderRepresentationService representationService) {
        this.representationService = representationService;
    }

    @GetMapping("/api/orders/{id}")
    EntityModel<OrderSnapshot> one(@PathVariable UUID id) {
        return representationService.findById(id);
    }
}
~~~

Trong thiết kế này, cache chỉ chứa OrderSnapshot. Assembler chạy trên từng request, vì vậy self link được dựng từ mapping hiện hành và các link có điều kiện có thể được quyết định theo Authentication hoặc policy hiện tại. Ví dụ rút gọn chỉ thêm self link; khi tạo collection representation, hãy thêm collection link trong phương thức collection tương ứng. Nếu có link approve theo quyền, hãy đánh giá policy trong assembler hoặc một component chuyên trách ở mỗi request.

Order, OrderRepository, OrderNotFoundException và các method query trong ví dụ là kiểu domain/ứng dụng do dự án định nghĩa. Cần bảo đảm revision tăng mỗi khi dữ liệu projection thay đổi; nếu không, revision không thể giúp phát hiện stale snapshot. Cache không thay thế authorization: mỗi request vẫn phải kiểm tra quyền đọc resource. Nếu truy vấn hoặc dữ liệu phụ thuộc tenant, hãy đưa tenant ID vào cache key và không để cache theo ID toàn cục vượt qua phạm vi dữ liệu của tenant.

## Khi nào nên cache kết quả assembler?

Cache trực tiếp representation chỉ phù hợp khi kết quả thực sự giống nhau cho mọi request nằm trong cùng cache key. Trước khi bật cache, hãy trả lời được tất cả câu hỏi sau:

1. Dữ liệu và mọi dependency dùng để tạo representation có thay đổi theo thời gian không?
2. Link có phụ thuộc host, scheme, context path hoặc forwarded headers không?
3. Link/affordance có phụ thuộc principal, role, tenant hoặc ownership không?
4. Representation có phụ thuộc locale, API version, media type, filter hoặc page không?
5. Cache key có bao phủ toàn bộ các chiều ảnh hưởng response không?
6. Có cơ chế eviction khi aggregate hoặc dependency thay đổi không?
7. Cache provider có lưu được kiểu representation và phục hồi đúng link metadata không?
8. Có nguy cơ nhiều request cùng nhận một object mutable rồi sửa nó không?

Nếu chưa chứng minh được các điều kiện này, đừng cache EntityModel hoặc CollectionModel đã gắn link. Hãy cache projection hoặc DTO bất biến rồi assemble theo request.

Một trường hợp có thể cache representation là API công khai, cùng một canonical origin, không cá nhân hóa, một media type và một version cố định, với link chỉ phụ thuộc dữ liệu có revision rõ ràng. Ngay cả khi đó, cần có TTL/eviction và kiểm thử link sau thay đổi.

## Cache key phải phản ánh representation variant

Nếu thực sự cần cache representation theo ngữ cảnh, key phải bao gồm mọi đầu vào làm thay đổi representation. Có thể mô hình hóa key thành một record:

~~~java
import java.util.Locale;
import java.util.UUID;

public record OrderRepresentationKey(
        UUID orderId,
        long orderRevision,
        String tenantId,
        String permissionProfile,
        Locale locale,
        String apiVersion,
        String mediaType,
        String publicOrigin) {
}
~~~

Các trường là ví dụ, không phải danh sách bắt buộc cho mọi API. Chỉ đưa vào key các yếu tố thực sự ảnh hưởng representation; nhưng không được bỏ sót yếu tố nào đang ảnh hưởng body.

- **orderId/orderRevision:** nhận diện resource và revision dữ liệu.
- **tenantId:** ngăn dùng chung representation giữa tenant.
- **permissionProfile:** phân biệt tập link/field theo quyền. Giá trị này phải được tạo từ policy server-side, không lấy nguyên access token.
- **locale:** phân biệt label hoặc nội dung bản địa hóa.
- **apiVersion:** phân biệt DTO, route và relation theo hợp đồng.
- **mediaType:** phân biệt HAL, HAL-FORMS hoặc representation khác.
- **publicOrigin:** chỉ cần khi absolute href được tạo theo origin của request.

Không dùng username hoặc raw JWT làm cache key nếu có thể dùng một permission scope ổn định và không nhạy cảm. Cần có invalidation khi quyền thay đổi; nếu permission profile được tính sai hoặc không được cập nhật, cache vẫn có thể phát link không phù hợp.

Với application cache, một record Java có equals/hashCode ổn định là lựa chọn rõ ràng cho composite key. Với HTTP cache, dùng Vary cho request headers ảnh hưởng response và thiết lập Cache-Control đúng; hai cơ chế key này không tự thay thế nhau.

## Tránh cache absolute link theo request

WebMvcLinkBuilder tạo link dựa trên mapping controller và servlet request context. Khi cache output đã có absolute href, request sau có thể nhận origin từ request trước. Có ba hướng xử lý:

1. **Assemble theo request:** cache projection, gọi assembler trong request hiện tại. Đây thường là cách đơn giản nhất.
2. **Dùng canonical public origin:** cấu hình một origin chính thức để link không phụ thuộc Host header đến từng request. Cần xử lý forwarded headers ở gateway một cách tin cậy.
3. **Cache relative link descriptor:** lưu path/relation ổn định rồi dựng URI cuối cùng ở response boundary theo request context.

Không nên tin mọi Host hoặc X-Forwarded-Host từ client. Chỉ chấp nhận forwarded headers do reverse proxy tin cậy ghi vào; nếu không, có thể tạo link độc hại hoặc cache href sai origin.

Background job hoặc cache warmer thường chạy ngoài servlet request. Nó không có request context để WebMvcLinkBuilder suy ra host hiện tại. Hãy cache dữ liệu/descriptor trong background và chỉ tạo absolute links khi có origin rõ ràng hoặc khi xử lý HTTP request.

## EntityModel và CollectionModel có thể bị thay đổi

EntityModel và CollectionModel là các kiểu representation có thể được bổ sung link. Ví dụ assembler thêm link sau khi tạo model:

~~~java
EntityModel<OrderSnapshot> model = EntityModel.of(snapshot);
model.add(linkTo(methodOn(OrderController.class)
        .one(snapshot.id())).withSelfRel());
~~~

Nếu cùng một instance được lấy từ cache và tái sử dụng, một tầng xử lý khác có thể thêm hoặc xóa link trên object đó. Request sau có thể nhận metadata do request trước để lại. Với cache object in-memory, việc trả cùng reference là điều cần tính đến; với cache phân tán, serializer còn phải biết cách lưu và phục hồi kiểu model, link và metadata.

Không giả định EntityModel luôn có thể serialize an toàn với mọi cache provider. Redis hoặc provider khác cần serializer được cấu hình rõ và tương thích với kiểu Spring HATEOAS. Thay đổi class/DTO giữa các lần deploy có thể làm dữ liệu cache cũ không deserialize được.

Các lựa chọn an toàn:

- Cache record/DTO bất biến và tạo EntityModel mới cho mỗi request.
- Nếu cache representation, lưu một cấu trúc bất biến riêng gồm content snapshot và link descriptors, rồi dựng model mới khi trả response.
- Chỉ cache serialized bytes khi media type, serializer version, locale, API version và các biến thể đã nằm trong key.
- Không để code consumer mutate object được chia sẻ từ cache.

## Cấu hình Spring Cache

Để dùng các annotation cache, bật caching trong cấu hình:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
class CacheConfiguration {
}
~~~

Ví dụ trên dùng cache name orderSnapshots. Cache manager cần được cấu hình bằng provider phù hợp với yêu cầu TTL, eviction, phân tán và serialization. ConcurrentMapCacheManager có thể dùng cho ví dụ hoặc test đơn giản; ứng dụng production thường cần giới hạn kích thước và TTL bằng provider như Caffeine hoặc Redis.

SpEL key #p0 tham chiếu tham số đầu tiên mà không phụ thuộc tên tham số có được giữ trong bytecode hay không. Nếu method nhận nhiều tham số, hãy tạo key rõ ràng hoặc dùng record composite key thay vì nối chuỗi dễ va chạm.

## Proxy và self-invocation

Spring Cache annotation hoạt động qua Spring AOP proxy. Lời gọi từ bean khác đi qua proxy sẽ kích hoạt cache; lời gọi một method cacheable từ method khác trong cùng instance thường không đi qua proxy.

Ví dụ dễ gây nhầm:

~~~java
import java.util.UUID;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderSnapshot loadForScreen(UUID id) {
        return findSnapshot(id); // self-invocation: không đi qua cache proxy.
    }

    @Cacheable(cacheNames = "orderSnapshots", key = "#p0")
    public OrderSnapshot findSnapshot(UUID id) {
        return repository.loadSnapshot(id);
    }
}
~~~

Tách method cacheable sang một bean riêng như OrderSnapshotQueryService ở ví dụ trước. Khi controller hoặc facade inject bean đó, lời gọi sẽ đi qua proxy. Không tự gọi method nội bộ rồi kết luận cache đang hoạt động chỉ vì annotation đã được khai báo.

## Invalidation khi dữ liệu hoặc quyền thay đổi

Cache representation phải được invalidation khi bất kỳ dependency nào ảnh hưởng output thay đổi:

- Order thay đổi status, total hoặc revision.
- Customer name/address được nhúng vào order representation thay đổi.
- Permission hoặc tenant membership thay đổi làm tập link khác đi.
- API route/version hoặc relation metadata được triển khai mới.
- Locale message catalog thay đổi nếu cache nội dung đã dịch.

Với snapshot cache theo ID, command có thể evict key sau khi transaction commit:

~~~java
import java.util.UUID;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderCommandService {

    private final OrderRepository repository;

    OrderCommandService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    @CacheEvict(cacheNames = "orderSnapshots", key = "#p0")
    public void approve(UUID orderId) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));
        order.approve();
    }
}
~~~

Ví dụ minh họa eviction theo ID. Với yêu cầu nghiêm ngặt về thứ tự commit, hãy gắn invalidation vào event AFTER_COMMIT hoặc transactional outbox; không giả định thứ tự cache advisor luôn tương đương transaction commit. Nếu representation cache phụ thuộc customer, tenant hoặc permission, evict thêm những key/region liên quan.

Versioned key theo revision có thể khiến request mới không đọc entry cũ, nhưng entry cũ vẫn chiếm bộ nhớ đến khi hết TTL hoặc bị evict. Nó cũng không tự xử lý link phụ thuộc permission, route hoặc locale. Version key là một phần của chiến lược, không thay thế dependency invalidation.

## Cache collection assembler

Collection representation thường khó cache hơn item representation vì nội dung phụ thuộc membership, filter, sort, page và link phân trang. Một thay đổi order có thể khiến item:

- Biến mất khỏi collection filter PENDING.
- Xuất hiện trong collection filter APPROVED.
- Chuyển vị trí do sort theo updatedAt.
- Làm thay đổi totalElements, totalPages và link first/prev/next/last.

Nếu cache CollectionModel đã assemble, key phải tính đến filter, sort, page, tenant, authorization scope, locale, version và media type nếu các yếu tố đó ảnh hưởng response. Khi membership thay đổi, phải invalidation mọi trang có thể bị ảnh hưởng; việc chỉ evict key của order detail là chưa đủ.

Với collection lớn hoặc nhiều filter, thường nên cache query result theo key có cấu trúc và tạo PagedModel/CollectionModel cùng links trong request. Có thể dùng TTL ngắn cho search result, nhưng endpoint nhạy cảm không nên dựa vào TTL dài để quyết định quyền hoặc trạng thái workflow.

## Cache assembler và HTTP response cache

Hai chiến lược có mục tiêu khác nhau:

| Chiến lược | Điểm tiết kiệm | Điều cần quản lý |
| --- | --- | --- |
| Cache projection trước assembler | Giảm query và mapping dữ liệu | Data freshness, cache key và invalidation domain. |
| Cache assembled representation | Giảm mapping và tạo hypermedia | Mọi biến thể link, quyền, tenant, locale, version, media type và object mutability. |
| HTTP response cache | Có thể tránh cả việc gọi ứng dụng khi response còn fresh | Cache-Control, ETag, Vary, shared cache policy và purge. |

Nếu representation công khai, ổn định và cacheable, HTTP cache với ETag có thể giảm request xử lý ở server. Nếu representation cá nhân hóa theo principal, dùng private hoặc no-store theo yêu cầu bảo mật; không đưa link theo quyền vào shared cache công khai.

Không dùng Spring Cache để thay thế HTTP caching và không dùng ETag để thay thế application cache. Chọn đúng lớp cho phần chi phí muốn giảm.

## Kiểm thử cache và assembler

Nên kiểm thử riêng hai hành vi: query cache giảm số lần tải dữ liệu, và assembler vẫn tạo representation phù hợp request hiện tại.

Ví dụ kiểm tra query cache với Spring Cache:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

@TestConfiguration
class OrderCacheTestConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("orderSnapshots");
    }
}

@SpringBootTest
@Import(OrderCacheTestConfiguration.class)
class OrderSnapshotQueryCacheTest {

    @Autowired
    OrderSnapshotQueryService queryService;

    @MockBean
    OrderRepository orderRepository;

    @Test
    void reusesSnapshotForSameKey() {
        UUID id = UUID.fromString("00000000-0000-0000-0000-000000000042");
        Order order = OrderFixtures.pendingOrder(id);
        when(orderRepository.findById(id)).thenReturn(Optional.of(order));

        OrderSnapshot first = queryService.findSnapshot(id);
        OrderSnapshot second = queryService.findSnapshot(id);

        assertThat(first).isEqualTo(second);
        verify(orderRepository, times(1)).findById(id);
    }
}
~~~

OrderFixtures và Order là fixture/domain type của ứng dụng. Test phải gọi queryService từ bean được inject để lời gọi đi qua Spring proxy; gọi method trực tiếp trên object tự tạo sẽ không kiểm tra annotation cache.

Với assembler, kiểm tra link được tạo trong từng request context. Ví dụ chạy hai request với Host hoặc forwarded origin khác nhau trong môi trường test được cấu hình, rồi xác nhận href đúng origin mong đợi. Nếu hệ thống dùng relative link hoặc canonical origin cố định, hãy kiểm tra hợp đồng đó thay vì giả định host từ request.

Các test quan trọng khác:

- Cùng order ID nhưng tenant khác không nhận chung projection/representation nếu dữ liệu phụ thuộc tenant.
- Người xem và người phê duyệt nhận đúng tập action links.
- Thay đổi status làm snapshot cache bị evict và link affordance thay đổi.
- Thay đổi locale/API version/media type không dùng nhầm cache entry.
- Collection filter và pagination link cập nhật khi membership thay đổi.
- Cache provider đọc/ghi đúng kiểu dữ liệu sau khi serialize nếu dùng Redis hoặc provider phân tán.
- Không có cache entry personalized bị phục vụ từ shared HTTP cache.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Cache assembler chỉ theo resource ID | Link có thể sai host, tenant, quyền hoặc version. | Cache projection hoặc dùng composite key đầy đủ. |
| Cache EntityModel rồi để consumer sửa | Request sau có thể nhận link bị thêm/xóa từ request trước. | Tạo model mới hoặc cache representation descriptor bất biến. |
| Cho rằng @Cacheable trên method luôn chạy | Self-invocation không qua proxy nên cache bị bỏ qua. | Tách bean cacheable và gọi qua Spring proxy. |
| Cache absolute href được tạo từ request đầu tiên | Request qua host khác nhận URL cũ. | Assemble theo request hoặc dùng canonical origin. |
| Cache model có link theo quyền trong shared cache | Có thể lộ hành động hoặc resource giữa người dùng. | Cache theo authorization scope hoặc không cache representation cá nhân hóa. |
| Chỉ evict detail key | Collection/search/page vẫn chứa state cũ. | Mô hình hóa dependency và evict key/tag liên quan. |
| Dùng EntityModel làm Redis value mà chưa cấu hình serializer | Deserialize lỗi hoặc mất metadata/link. | Cấu hình serializer rõ và kiểm thử round-trip. |
| Chỉ tăng revision để tránh đọc entry cũ | Entry cũ vẫn chiếm bộ nhớ và dependency ngoài aggregate chưa được xét. | Kết hợp TTL, eviction và dependency version. |
| Cache collection chỉ theo page number | Filter, sort hoặc tenant có thể bị trộn. | Dùng key gồm đầy đủ query và security context. |

## Quy trình quyết định có cache assembler hay không

1. Đo thời gian query, projection, assembler và serialization riêng biệt.
2. Nếu query chiếm chi phí chính, cache domain snapshot/read projection trước.
3. Kiểm tra link có phụ thuộc request, origin, principal, tenant, locale, version hoặc media type không.
4. Nếu có phụ thuộc động, tạo links trong mỗi request và tránh cache EntityModel đã hoàn chỉnh.
5. Nếu representation thực sự context-independent, định nghĩa cache key bao phủ mọi biến thể và dependency revision.
6. Chọn cache provider, TTL, serializer và chính sách eviction phù hợp.
7. Kiểm thử cache hit, invalidation, link correctness, authorization isolation và serialization.
8. Theo dõi hit ratio, cache load, eviction rate, stale response và thời gian assembler.

## Nguyên tắc thiết kế

- Giữ assembler stateless và tập trung vào mapping dữ liệu cùng hypermedia.
- Ưu tiên cache DTO/read projection bất biến, sau đó assemble link theo request.
- Chỉ cache EntityModel/CollectionModel khi chứng minh representation không phụ thuộc context bị bỏ khỏi cache key.
- Đưa tenant, permission scope, locale, API version, media type và origin vào key khi chúng ảnh hưởng output.
- Không dùng raw token làm cache key; dùng security scope được tính ở server.
- Không chia sẻ instance representation mutable giữa các request.
- Hiểu rõ Spring Cache proxy và tránh self-invocation.
- Invalidate cache khi aggregate hoặc dependency ảnh hưởng field/link/affordance thay đổi.
- Tách application cache khỏi HTTP cache; dùng ETag, Cache-Control và Vary đúng lớp.
- Kiểm thử cả hiệu quả cache và tính đúng đắn của link sau cache hit.

Cache assembler có thể giảm chi phí dựng representation, nhưng chỉ an toàn khi cache key đại diện đầy đủ cho dữ liệu và ngữ cảnh tạo ra nó. Trong phần lớn API có link phụ thuộc request hoặc quyền truy cập, cache projection bất biến rồi chạy assembler trên từng request là lựa chọn dễ kiểm soát hơn. Nếu cần cache representation hoàn chỉnh, hãy quản lý biến thể, mutability, serialization và invalidation như một phần của hợp đồng hypermedia.
