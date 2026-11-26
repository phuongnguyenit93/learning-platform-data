# Chi phí assembler

Trong Spring HATEOAS, assembler chuyển dữ liệu domain hoặc DTO thành representation mà client có thể điều hướng. Với một resource đơn lẻ, chi phí này thường nhỏ. Với collection có hàng chục hoặc hàng trăm phần tử, assembler được gọi lặp lại cho từng item; mỗi lần có thể tạo DTO, EntityModel, nhiều Link, kiểm tra trạng thái và đọc thêm dữ liệu liên quan.

Điểm tốn kém thường không nằm ở một lệnh EntityModel.of(...) riêng lẻ. Chi phí lớn xuất hiện khi assembler vô tình truy vấn database, kích hoạt lazy loading, gọi service bên ngoài hoặc chạy cùng một phép kiểm tra quyền cho từng item. Vì vậy, tối ưu assembler bắt đầu bằng việc đo toàn bộ đường đi của request, sau đó đưa dữ liệu cần thiết tới assembler theo lô và giữ phần tạo representation gọn, có thể dự đoán.

## Request HATEOAS tốn thời gian ở đâu?

Một request collection thường đi qua các bước:

~~~mermaid
flowchart LR
    A[HTTP request] --> B[Query và phân trang]
    B --> C[Đọc dữ liệu liên quan]
    C --> D[Assembler tạo model]
    D --> E[Tạo các link]
    E --> F[HAL serialization]
    F --> G[Response qua network]
~~~

Mỗi bước có một loại chi phí khác nhau:

| Giai đoạn | Chi phí thường gặp | Dấu hiệu cần điều tra |
| --- | --- | --- |
| Query | SQL, round trip database, count query | Thời gian truy vấn cao hoặc số SQL tăng theo số item |
| Đọc quan hệ | Lazy loading, N+1, gọi repository trong vòng lặp | Nhiều câu SELECT giống nhau |
| Assembler | Chuyển DTO, tạo model, tính điều kiện | CPU và allocation tăng theo kích thước page |
| Link building | Resolve controller mapping, tạo URI và Link | CPU đáng kể khi số link trên mỗi item lớn |
| Serialization | Chuyển model thành HAL/HAL-FORMS JSON | JSON lớn, object graph sâu |
| Network | Truyền payload và chờ client | Response bytes lớn hoặc latency tăng theo page size |

Đừng mặc định assembler là nút thắt chỉ vì nó chạy một lần trên mỗi item. Một query N+1 có thể tốn nhiều thời gian hơn toàn bộ việc tạo link. Cần đo riêng thời gian query, thời gian assembly, serialization, kích thước response và latency đầu cuối.

## Trách nhiệm của assembler

RepresentationModelAssembler nhận một đối tượng đầu vào và tạo một representation có dữ liệu cùng link. Một assembler dễ tối ưu thường chỉ làm ba việc:

1. Chuyển các trường đã có thành representation DTO.
2. Tạo các link cần thiết cho resource.
3. Thêm affordance hoặc link tùy chọn dựa trên thông tin đã được tính trước.

Assembler nên tránh:

- Gọi repository hoặc EntityManager.
- Truy cập lazy relationship có thể phát sinh SQL.
- Gọi REST client hoặc dịch vụ bên ngoài.
- Tính lại quyền bằng truy vấn cho từng item.
- Thực hiện nghiệp vụ có side effect.
- Tạo một object graph lớn chỉ để serializer loại bỏ sau đó.

Ví dụ, assembler sau đây trộn việc tạo representation với truy cập dữ liệu:

~~~java
@Component
class SlowOrderAssembler {

    private final CustomerRepository customerRepository;
    private final OrderPolicy orderPolicy;

    EntityModel<OrderRepresentation> toModel(
            Order order,
            Authentication authentication) {

        Customer customer = customerRepository.findById(
            order.getCustomerId()).orElseThrow();

        boolean cancellable =
            orderPolicy.canCancel(authentication, order.getId());

        OrderRepresentation body = new OrderRepresentation(
            order.getId(),
            order.getStatus().name(),
            customer.getName()
        );

        // Tạo EntityModel và các link...
        return EntityModel.of(body);
    }
}
~~~

Nếu trang có 50 đơn hàng, customerRepository.findById có thể thêm 50 query. Nếu canCancel cũng truy vấn database, số query có thể tăng thêm 50. Tổng chi phí khi đó tăng theo số item dù controller chỉ gọi một lần để lấy page.

Assembler không nên tự tải dữ liệu cần thiết. Hãy để query/service chuẩn bị dữ liệu trước, sau đó truyền một DTO đầy đủ cho assembler.

## Dùng projection để lấy đúng dữ liệu cần render

Với collection chỉ đọc, DTO projection thường phù hợp hơn khi tải entity rồi để assembler lần theo các quan hệ. Ví dụ repository dùng interface projection:

~~~java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface OrderRow {
    UUID getId();
    OrderStatus getStatus();
    UUID getCustomerId();
    String getCustomerName();
}

interface OrderRepository extends JpaRepository<Order, UUID> {

    @Query("""
        select o.id as id,
               o.status as status,
               c.id as customerId,
               c.name as customerName
        from Order o
        join o.customer c
        where o.tenantId = :tenantId
        """)
    Page<OrderRow> findRowsByTenantId(
        @Param("tenantId") UUID tenantId,
        Pageable pageable
    );
}
~~~

Projection lấy các cột cần dùng và join quan hệ to-one customer ngay trong query. Nó không yêu cầu assembler gọi thêm repository để lấy tên khách hàng.

Service chuyển projection thành DTO riêng cho representation:

~~~java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record OrderSummary(
    UUID id,
    OrderStatus status,
    UUID customerId,
    String customerName,
    boolean cancellable
) {}

@Service
class OrderReadService {

    private final OrderRepository orderRepository;

    OrderReadService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    Page<OrderSummary> findPage(
            UUID tenantId,
            Pageable pageable,
            Authentication authentication) {

        boolean hasCancelScope = authentication.getAuthorities().stream()
            .anyMatch(authority ->
                authority.getAuthority().equals("SCOPE_orders.cancel"));

        return orderRepository.findRowsByTenantId(tenantId, pageable)
            .map(row -> new OrderSummary(
                row.getId(),
                row.getStatus(),
                row.getCustomerId(),
                row.getCustomerName(),
                hasCancelScope && row.getStatus() == OrderStatus.PENDING
            ));
    }
}
~~~

Ví dụ rút gọn giả định quyền hủy phụ thuộc scope orders.cancel và trạng thái PENDING; quyền truy cập tenant đã được giới hạn trong query. Nếu policy thực tế còn phụ thuộc chủ sở hữu, hạn mức hoặc quyền riêng trên từng đơn, hãy lấy tập ID được phép bằng một batch query hoặc một policy query theo danh sách ID. Không gọi orderPolicy.canCancel(...) với truy vấn riêng cho từng row.

Projection cũng giúp giảm lượng dữ liệu đọc từ database. Entity có thể chứa nhiều trường, quan hệ và collection không cần thiết cho response. DTO chỉ giữ những gì representation sử dụng.

## Tạo representation từ DTO thuần

Assembler nhận OrderSummary, không nhận JPA entity. Controller mapping được giả định như sau: OrderController có base path /orders, CustomerController có base path /customers, và OrderWorkflowController có base path /orders.

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

record OrderRepresentation(
    UUID id,
    String status,
    String customerName
) {}

@Component
class OrderModelAssembler implements
        RepresentationModelAssembler<OrderSummary,
            EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(OrderSummary source) {
        OrderRepresentation body = new OrderRepresentation(
            source.id(),
            source.status().name(),
            source.customerName()
        );

        EntityModel<OrderRepresentation> model = EntityModel.of(body);

        model.add(linkTo(OrderController.class)
            .slash(source.id())
            .withSelfRel());

        model.add(linkTo(CustomerController.class)
            .slash(source.customerId())
            .withRel("customer"));

        if (source.cancellable()) {
            model.add(linkTo(OrderWorkflowController.class)
                .slash(source.id())
                .slash("cancellation")
                .withRel("cancel"));
        }

        return model;
    }
}
~~~

Assembler chỉ đọc các giá trị đã có trong DTO và tạo link. Việc kiểm tra scope đơn giản đã được tính một lần trong service; trạng thái đơn nằm ngay trong DTO. Với policy phức tạp hơn, service có thể truyền một boolean hoặc tập quyền đã được tính theo lô.

Nếu route có mapping phức tạp, query parameter hoặc path variable không thể biểu diễn bằng base path và slash, dùng methodOn(...) để lấy mapping từ method controller:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

model.add(linkTo(
    methodOn(OrderController.class).one(source.id())
).withSelfRel());
~~~

linkTo(methodOn(...)) tiện khi cần bám sát mapping của method. Với route đơn giản có base path cố định, linkTo(Controller.class).slash(id) có thể ngắn gọn hơn. Đừng thay link builder bằng cách nối chuỗi URI thủ công chỉ để tiết kiệm vài thao tác; lợi ích CPU cần được đo và URL tự ghép dễ sai khi mapping thay đổi.

## Tránh N+1 khi tải quan hệ

Nếu cần làm việc với entity thay vì projection, hãy chọn chiến lược fetch phù hợp. Ví dụ quan hệ customer là to-one:

Đây là phương án thay thế cho query projection ở trên; trong dự án, thêm method vào OrderRepository hiện có thay vì khai báo một interface trùng tên.

~~~java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<Order, UUID> {

    @EntityGraph(attributePaths = "customer")
    Page<Order> findAllByTenantId(UUID tenantId, Pageable pageable);
}
~~~

EntityGraph yêu cầu quan hệ cần dùng được tải cùng truy vấn theo fetch plan do provider triển khai. Một cách khác là dùng join fetch cho quan hệ to-one hoặc DTO projection như phần trước.

Với quan hệ to-many, cẩn thận khi dùng fetch join trong query phân trang. Join một collection có thể nhân bản row, làm sai kết quả phân trang hoặc khiến Hibernate phải phân trang trong bộ nhớ. Với collection lớn, thường nên:

- Truy vấn page ID trước, sau đó tải dữ liệu cần thiết cho danh sách ID theo batch.
- Dùng projection hoặc aggregate query nếu response chỉ cần vài trường.
- Dùng batch fetching để giảm số round trip khi không thể tải tất cả bằng một query.
- Tránh serialize toàn bộ collection con nếu client chỉ cần link tới resource con.

Batch fetching là biện pháp giảm N+1, không phải lý do để assembler truy cập tùy ý các quan hệ lazy. Query plan vẫn cần được đo bằng dữ liệu có kích thước gần với production.

Đặt spring.jpa.open-in-view=false trong ứng dụng API giúp phát hiện truy cập lazy ngoài ranh giới service transaction:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Khi đó, service phải tải đủ dữ liệu hoặc chuyển sang DTO trước khi kết thúc transaction. Assembler sẽ không vô tình kích hoạt SQL trong giai đoạn serialize response.

## Batch authorization thay vì kiểm tra từng item

Một số policy không thể tính chỉ từ scope và trạng thái. Ví dụ người dùng chỉ được hủy các đơn thuộc nhóm cửa hàng mà họ phụ trách. Nếu canCancel(authentication, orderId) truy vấn dữ liệu cho từng đơn, assembler sẽ tạo thêm một N+1 khác dù query chính đã dùng projection.

Lấy ID của page trước, rồi truy vấn một lần tập ID được phép:

~~~java
import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.security.core.Authentication;

Page<OrderRow> rows =
    orderRepository.findRowsByTenantId(tenantId, pageable);

List<UUID> orderIds = rows.getContent().stream()
    .map(OrderRow::getId)
    .toList();

Set<UUID> cancellableIds = orderIds.isEmpty()
    ? Set.of()
    : orderPolicy.findCancellableOrderIds(authentication, orderIds);

Page<OrderSummary> summaries = rows.map(row -> new OrderSummary(
    row.getId(),
    row.getStatus(),
    row.getCustomerId(),
    row.getCustomerName(),
    cancellableIds.contains(row.getId())
));
~~~

findCancellableOrderIds nên thực hiện một truy vấn theo danh sách ID hoặc một phép tính batch có giới hạn. Số query không còn tăng tuyến tính theo số item trong page. Với page rỗng, bỏ qua batch query để tránh gọi database không cần thiết.

Không truyền toàn bộ danh sách ID không giới hạn vào IN (...). Page size cần có giới hạn; nếu batch rất lớn, chia thành các chunk có kích thước xác định hoặc dùng cơ chế truy vấn phù hợp với database.

## Dùng PagedResourcesAssembler cho collection

Không tự lặp qua page rồi bỏ metadata phân trang. Spring Data cung cấp PagedResourcesAssembler để chuyển Page<T> thành PagedModel<D> và tạo navigation links:

~~~java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderReadService orderReadService;
    private final OrderModelAssembler orderModelAssembler;
    private final PagedResourcesAssembler<OrderSummary> pagedAssembler;
    private final TenantResolver tenantResolver;

    OrderController(
            OrderReadService orderReadService,
            OrderModelAssembler orderModelAssembler,
            PagedResourcesAssembler<OrderSummary> pagedAssembler,
            TenantResolver tenantResolver) {
        this.orderReadService = orderReadService;
        this.orderModelAssembler = orderModelAssembler;
        this.pagedAssembler = pagedAssembler;
        this.tenantResolver = tenantResolver;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    PagedModel<EntityModel<OrderRepresentation>> all(
            Pageable pageable,
            Authentication authentication) {

        UUID tenantId = tenantResolver.tenantId(authentication);
        Page<OrderSummary> page = orderReadService.findPage(
            tenantId, pageable, authentication);

        return pagedAssembler.toModel(page, orderModelAssembler);
    }
}
~~~

PagedResourcesAssembler gọi assembler cho từng item và giữ lại metadata page, size, totalElements, totalPages cùng các link điều hướng. Công việc tạo model vẫn tăng theo số item, nhưng query không nên tăng theo số item.

Giới hạn page size ở tầng API. Một page 20 item thường dễ kiểm soát hơn một request trả 5.000 item cùng hàng chục nghìn link. Nếu client cần xuất dữ liệu lớn, cung cấp luồng export hoặc tác vụ bất đồng bộ thay vì biến collection endpoint thành bulk download.

## Kiểm soát số lượng link và độ sâu embedded resource

Mỗi Link tạo object trong bộ nhớ và thêm JSON vào response. Nếu một page có 100 item, mỗi item có 8 link, server phải tạo và serialize khoảng 800 link cùng các object representation tương ứng.

Hãy giữ các link có giá trị điều hướng thực tế:

- Giữ self cho từng item.
- Thêm relation tới resource liên quan nếu client cần khám phá quan hệ đó.
- Chỉ thêm action link khi hành động có thể thực hiện.
- Đặt link phân trang ở collection model thay vì lặp lại ở từng item.
- Tránh embed một cây object lớn nếu client có thể theo link để tải resource riêng.

Không xóa link có ý nghĩa chỉ để giảm vài byte. Hãy cân nhắc số relation, độ sâu embedded, kích thước payload và số request tiếp theo mà client cần thực hiện. Một embedded resource vừa đủ đôi khi giảm nhiều request hơn chi phí serialize mà nó thêm vào.

## Không cache Link được tạo theo request

Link được tạo từ request có thể phụ thuộc scheme, host, port, context path, forwarded headers hoặc quyền của principal. Không giữ EntityModel hay Link tuyệt đối trong application cache dùng chung nếu chúng được tạo từ request trước.

Với dữ liệu có thể cache:

1. Cache DTO hoặc snapshot domain theo resource và tenant.
2. Khi request đến, lấy Authentication và request context hiện tại.
3. Tạo EntityModel và link trong assembler.
4. Áp dụng HTTP cache policy phù hợp cho response.

Nếu response hoàn toàn công khai và link ổn định, có thể cân nhắc cache representation sau khi đã xác định cache key và validator. Với link cá nhân hóa, tạo link theo request giúp tránh trả affordance của người dùng này cho người dùng khác.

## Không dùng parallelStream để tăng tốc assembler

parallelStream() có thể hấp dẫn khi map một page lớn, nhưng không phải cách tối ưu mặc định:

- JPA persistence context và entity không an toàn khi nhiều thread cùng truy cập.
- WebMvcLinkBuilder dựa vào request context của thread hiện tại; context này không tự truyền sang worker thread.
- Tạo nhiều task song song có thể làm tăng contention và allocation.
- CPU đã bận vì serialize hoặc xử lý request khác có thể bị tranh chấp nhiều hơn.

Nếu cần xử lý song song, hãy tải dữ liệu thành DTO bất biến trước, chụp rõ base URI/context cần dùng và thiết kế executor có giới hạn. Đo end-to-end trước khi triển khai. Với page thông thường, mapping tuần tự thường đơn giản và ổn định hơn.

## Đo thời gian assembly bằng Micrometer

Tách timer cho query và assembly để biết thời gian nằm ở đâu. Ví dụ đo đoạn tạo PagedModel:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

class OrderResponseFactory {

    private final PagedResourcesAssembler<OrderSummary> pagedAssembler;
    private final OrderModelAssembler orderModelAssembler;
    private final Timer assemblyTimer;

    OrderResponseFactory(
            PagedResourcesAssembler<OrderSummary> pagedAssembler,
            OrderModelAssembler orderModelAssembler,
            MeterRegistry meterRegistry) {
        this.pagedAssembler = pagedAssembler;
        this.orderModelAssembler = orderModelAssembler;
        this.assemblyTimer = Timer.builder("api.hateoas.assembly")
            .tag("resource", "order")
            .register(meterRegistry);
    }

    PagedModel<EntityModel<OrderRepresentation>> assemble(
            Page<OrderSummary> page) {

        return assemblyTimer.record(() ->
            pagedAssembler.toModel(page, orderModelAssembler));
    }
}
~~~

Đặt timer quanh đúng đoạn assembly, không bao gồm query nếu muốn so sánh riêng. Có thể tạo timer tương tự cho service query và tổng thời gian endpoint. Dùng tag có cardinality thấp như tên resource hoặc operation; không gắn orderId, userId hay tenantId vào metric tag.

Với Spring Boot Actuator và Micrometer, theo dõi thêm:

- http.server.requests để xem latency và status theo endpoint.
- JDBC/Hikari metrics để phát hiện pool cạn hoặc chờ kết nối.
- JVM memory, allocation và garbage collection để xem chi phí tạo model.
- Hibernate statistics hoặc công cụ theo dõi SQL để đếm query.

Timer assembler không tự cho biết vì sao chậm. Kết hợp nó với SQL log/profiler và kích thước response để tìm đúng nguyên nhân.

## Dùng profiler và benchmark đúng phạm vi

Để điều tra hiệu năng:

1. Chạy với page size và số quan hệ gần với dữ liệu production.
2. Ghi thời gian query, assembly, serialization và tổng request.
3. Dùng Java Flight Recorder hoặc profiler tương đương để xem CPU hotspot và allocation.
4. Kiểm tra số SQL statement và phát hiện truy vấn lặp theo từng item.
5. So sánh trước/sau bằng cùng dataset, cùng JVM warm-up và cùng tải.

JMH phù hợp để so sánh hai cách tạo representation thuần trong isolation, ví dụ mapper A và mapper B. Nó không mô phỏng database, servlet request context, serializer, network hoặc contention trong ứng dụng. Dùng load test hoặc integration benchmark cho latency đầu cuối.

Đừng tối ưu methodOn, Link.of hoặc một phép nối chuỗi khi profiler cho thấy thời gian chủ yếu nằm ở query, serialization hoặc network. Tối ưu đúng tầng thường mang lại hiệu quả lớn hơn.

## Kiểm thử số query không tăng theo số item

Một regression test với Hibernate Statistics có thể phát hiện N+1 trong query projection:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import jakarta.persistence.EntityManagerFactory;

import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

@DataJpaTest(properties = {
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
class OrderRepositoryPerformanceTests {

    @Autowired
    EntityManagerFactory entityManagerFactory;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void loadsPageWithBoundedStatementCount() {
        UUID tenantId = UUID.fromString(
            "d7b9b7e0-7a34-4f9d-a3b1-19d1c7a41a22");

        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);
        Statistics statistics = sessionFactory.getStatistics();
        statistics.setStatisticsEnabled(true);
        statistics.clear();

        Page<OrderRow> page = orderRepository.findRowsByTenantId(
            tenantId, PageRequest.of(0, 20));

        assertThat(page.getContent()).hasSize(20);
        assertThat(page.getTotalElements()).isGreaterThan(20);
        assertThat(statistics.getPrepareStatementCount())
            .isLessThanOrEqualTo(2);
    }
}
~~~

Test giả định fixture đã tạo ít nhất 21 đơn thuộc tenant, page đầu có đủ 20 item và projection query cần một query dữ liệu cùng tối đa một count query. Chuẩn bị fixture và clear statistics trước đoạn đo để không tính SQL tạo dữ liệu test. Không chạy test này song song với test khác dùng chung SessionFactory vì Hibernate Statistics là số liệu cấp SessionFactory.

Với entity graph hoặc batch fetching, số query có thể lớn hơn hai tùy chiến lược. Khi đó, mục tiêu quan trọng là số query bị giới hạn theo batch/page và không tăng thêm một query cho mỗi item. Có thể chạy test với page size 10 và 40 rồi so sánh số statement để phát hiện tăng tuyến tính.

## Kiểm thử link và kích thước response

Hiệu năng không phải lý do để bỏ kiểm tra hợp đồng. Integration test vẫn cần xác nhận link cần thiết và metadata phân trang tồn tại sau khi đổi assembler:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
~~~

Tên relation trong _embedded phụ thuộc cấu hình collection relation của model; ví dụ trên giả định relation là orders. Có thể đo kích thước body để theo dõi thay đổi payload:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MvcResult;

private static final int MAX_ORDER_PAGE_BYTES = 64 * 1024;

MvcResult result = mockMvc.perform(get("/orders")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

int responseBytes = result.getResponse().getContentAsByteArray().length;
assertThat(responseBytes).isLessThan(MAX_ORDER_PAGE_BYTES);
~~~

MAX_ORDER_PAGE_BYTES là ngưỡng được chọn từ yêu cầu sản phẩm và dữ liệu đo được, không phải một con số chung cho mọi API. Nếu payload vượt ngưỡng, xem xét page size, số link, trường representation, embedded resources và compression trước khi loại bỏ thông tin client cần.

## Những lỗi thường gặp

- Assembler gọi repository: một page tạo thêm query cho từng item.
- Đọc lazy relationship trong mapper: serialization hoặc mapping kích hoạt SQL ngoài dự kiến.
- Kiểm tra quyền theo từng ID: policy tạo ra một N+1 khác.
- Fetch toàn bộ entity: đọc nhiều cột và quan hệ mà response không dùng.
- Fetch join collection khi phân trang: có thể làm nhân bản row và sai pagination.
- Tạo quá nhiều link: mỗi item có nhiều relation không cần thiết làm tăng CPU và payload.
- Embed object graph sâu: response lớn và tốn serialization.
- Tự nối URL: dễ tạo URI sai và khó theo dõi khi controller mapping đổi.
- Cache Link theo request: host, scheme hoặc quyền có thể thuộc request trước.
- Dùng parallelStream: request context và persistence context không được chia sẻ an toàn.
- Đo mỗi assembler mà bỏ qua SQL: dễ tối ưu nhầm tầng.
- Chỉ benchmark mapper trong JMH: kết quả không đại diện latency HTTP thực tế.

## Checklist tối ưu chi phí assembler

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| Query | Số SQL có ổn định theo số item trong page không? |
| Data loading | DTO/projection đã có đủ trường assembler cần chưa? |
| Lazy loading | Assembler có vô tình kích hoạt truy vấn không? |
| Authorization | Quyền được tính một lần hoặc theo batch chưa? |
| Link building | Có dùng mapping builder đúng cách và chỉ tạo link cần thiết không? |
| Collection | Page size có giới hạn và metadata phân trang được giữ lại không? |
| Payload | Số link và embedded depth có phù hợp không? |
| Cache | Có tránh tái sử dụng representation mang link của request khác không? |
| Measurement | Đã đo query, assembly, serialization, response bytes và p95 chưa? |
| Regression | Có test query count và hợp đồng link sau tối ưu không? |

Chi phí assembler trong Spring HATEOAS tăng theo số item, số link và độ phức tạp representation. Hãy giữ assembler thuần, tải dữ liệu bằng projection hoặc fetch plan phù hợp, batch các phép kiểm tra quyền, giới hạn page size và chỉ công bố link client cần. Dùng Micrometer, Hibernate Statistics và profiler để xác định nút thắt trước khi thay đổi cách xây link. Sau tối ưu, kiểm tra cả số query, payload, metadata phân trang và các relation trong response để bảo đảm hiệu năng tăng mà hợp đồng hypermedia vẫn đúng.

## Tài liệu tham khảo

- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Data JPA – Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring Data JPA – EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data Web – PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Hibernate ORM – Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
