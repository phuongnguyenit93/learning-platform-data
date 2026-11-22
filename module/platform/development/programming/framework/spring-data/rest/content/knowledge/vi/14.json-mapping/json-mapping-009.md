# Quan hệ hai chiều, vòng lặp JSON và tác động của Hibernate proxy trong Spring Data REST

## Mục tiêu

Trong mô hình JPA, hai entity thường tham chiếu lẫn nhau. Ví dụ, một Order có danh sách OrderLine, trong khi mỗi OrderLine lại giữ tham chiếu về Order. Quan hệ này hợp lý ở tầng domain và database, nhưng có thể gây khó khăn khi chuyển object graph thành JSON.

Jackson có thể đi từ Order sang lines, từ từng line quay về Order, rồi lại đi xuống lines. Nếu không có quy tắc xử lý, quá trình serialize có thể lặp vô hạn hoặc ném lỗi do object graph có vòng tham chiếu.

Hibernate bổ sung một vấn đề khác: quan hệ LAZY thường được đại diện bằng proxy hoặc persistent collection chưa được tải. Khi Jackson gọi getter để serialize, Hibernate có thể phải truy vấn database. Nếu Session đã đóng, thao tác đó có thể gây `LazyInitializationException`.

Bài này phân biệt ba lớp vấn đề:

1. **Quan hệ hai chiều của JPA:** cách entity tham chiếu nhau.
2. **Biểu diễn JSON/HAL:** cách Jackson và Spring Data REST chuyển object graph thành response.
3. **Vòng đời persistence context:** thời điểm Hibernate proxy có thể tải dữ liệu.

## 1. Ví dụ quan hệ hai chiều

Giả sử một đơn hàng có nhiều dòng hàng; mỗi dòng hàng thuộc về đúng một đơn hàng.

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public void removeLine(OrderLine line) {
        lines.remove(line);
        line.setOrder(null);
    }

    // getters and setters
}
~~~

~~~java
@Entity
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;

    private int quantity;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    // getters and setters
}
~~~

Đây là quan hệ hai chiều:

- `PurchaseOrder.lines` là phía parent, chứa nhiều OrderLine.
- `OrderLine.order` là phía child, trỏ ngược về PurchaseOrder.
- `mappedBy = "order"` cho biết OrderLine là owning side của quan hệ.
- Khóa ngoại `order_id` nằm ở bảng dòng hàng.

Phương thức `addLine` và `removeLine` cập nhật cả hai phía trong bộ nhớ. Nếu chỉ thêm phần tử vào `order.getLines()` mà không đặt `line.setOrder(order)`, object graph có thể không nhất quán và JPA có thể không ghi quan hệ như mong muốn.

## 2. Vì sao JSON có thể lặp vô hạn?

Một serializer thông thường duyệt các getter và chuyển giá trị trả về thành JSON. Với quan hệ trên, đường đi có thể là:

~~~text
PurchaseOrder
  └── lines
       └── OrderLine
            └── order
                 └── lines
                      └── OrderLine
                           └── order
                                └── ...
~~~

Nếu Jackson serialize trực tiếp toàn bộ graph mà không có cơ chế nhận diện vòng tham chiếu, nó có thể tiếp tục đi qua lại giữa parent và child cho tới khi lỗi do đệ quy quá sâu hoặc lỗi serialize.

Ví dụ JSON mong muốn có thể chỉ cần:

~~~json
{
  "id": 42,
  "orderNumber": "PO-2026-0042",
  "lines": [
    {
      "id": 1,
      "sku": "KB-01",
      "quantity": 2
    },
    {
      "id": 2,
      "sku": "MS-02",
      "quantity": 1
    }
  ]
}
~~~

Không cần lặp lại toàn bộ PurchaseOrder bên trong từng OrderLine. Một representation có chủ đích thường chỉ thể hiện một chiều của quan hệ hoặc dùng ID/link để tham chiếu ngược.

## 3. Spring Data REST mặc định xử lý association bằng HAL links

Cần phân biệt JSON serialization thông thường với representation do Spring Data REST tạo ra.

Spring Data REST sử dụng một ObjectMapper đã được cấu hình cùng các serializer đặc biệt. Framework cố gắng biểu diễn managed association thành hypermedia links thay vì luôn nhúng toàn bộ entity được liên kết như POJO thông thường.

Ví dụ, item resource của Order có thể được trả về như sau:

~~~json
{
  "id": 42,
  "orderNumber": "PO-2026-0042",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/42"
    },
    "lines": {
      "href": "http://localhost:8080/api/orders/42/lines"
    }
  }
}
~~~

Client theo link `lines` để đọc association resource. Mỗi OrderLine có thể có item resource riêng nếu repository tương ứng được export.

Cách biểu diễn này tránh việc mặc định mở rộng toàn bộ graph quan hệ ở mọi response. Client chỉ tải association khi cần, qua URL do server công bố.

Một số điểm quan trọng:

- Spring Data REST thường tạo association link theo tên thuộc tính quan hệ.
- Có thể đổi path và relation bằng `@RestResource` trên thuộc tính.
- Projection, excerpt, custom serializer hoặc controller tự viết có thể thay đổi cách object graph được serialize.
- Nếu custom code trả entity trực tiếp qua một ObjectMapper khác, các quy tắc HAL của Spring Data REST có thể không còn được áp dụng.

Do đó, nếu response Spring Data REST bị lặp JSON, hãy xác định request đi qua repository exporter hay một custom controller/serializer trước khi thêm annotation vào entity. Không phải mọi quan hệ hai chiều đều tự động gây vòng lặp trong HAL response mặc định.

## 4. Cách 1: JsonManagedReference và JsonBackReference

Jackson cung cấp cặp annotation để đánh dấu chiều đi và chiều ngược của một quan hệ hai chiều.

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @JsonManagedReference("order-lines")
    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
    private List<OrderLine> lines = new ArrayList<>();

    // getters and setters
}
~~~

~~~java
@Entity
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;

    @JsonBackReference("order-lines")
    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;

    // getters and setters
}
~~~

Ý nghĩa:

- `@JsonManagedReference` đánh dấu chiều parent/forward. Thuộc tính này được serialize bình thường.
- `@JsonBackReference` đánh dấu chiều child/back. Thuộc tính ngược không được serialize.
- Khi deserialize, Jackson dùng back reference để gán lại tham chiếu parent cho child.
- Giá trị name phải khớp giữa hai annotation. Tên riêng hữu ích khi một class có nhiều cặp quan hệ.

Với ví dụ trên, JSON có thể chứa Order và danh sách lines, nhưng không chứa lại Order bên trong từng line.

**Lưu ý về vị trí annotation:** `@JsonBackReference` phải đặt trên thuộc tính kiểu bean đơn, ví dụ `OrderLine.order`. Không đặt nó trên collection, array hoặc Map. Collection phía parent là nơi phù hợp với `@JsonManagedReference`.

Cách này phù hợp với cây parent-child đơn giản. Nếu domain có nhiều đường quan hệ chéo, nhiều parent hoặc cần biểu diễn tham chiếu theo ID, hãy cân nhắc cách khác thay vì ghép nhiều cặp managed/back reference khó theo dõi.

## 5. Cách 2: JsonIdentityInfo và JsonIdentityReference

Nếu muốn giữ cấu trúc tham chiếu hai chiều mà không lặp lại object, có thể dùng object identity của Jackson.

~~~java
@Entity
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    private String orderNumber;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

~~~java
@Entity
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;

    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;
}
~~~

Jackson serialize lần xuất hiện đầu tiên của một object thành đầy đủ thuộc tính kèm object ID. Khi gặp lại cùng object trong graph, serializer có thể ghi tham chiếu bằng ID thay vì serialize lại toàn bộ object.

Ví dụ minh họa:

~~~json
{
  "id": 42,
  "orderNumber": "PO-2026-0042",
  "lines": [
    {
      "id": 1,
      "sku": "KB-01",
      "order": 42
    }
  ]
}
~~~

Hình dạng cụ thể phụ thuộc thứ tự serialize và cấu hình identity. Nếu muốn một thuộc tính luôn được biểu diễn bằng ID, có thể dùng thêm `@JsonIdentityReference(alwaysAsId = true)` trên thuộc tính quan hệ:

~~~java
@JsonIdentityReference(alwaysAsId = true)
@ManyToOne(fetch = FetchType.LAZY)
private PurchaseOrder order;
~~~

Cách này cần chú ý:

- ID phải duy nhất trong phạm vi identity generator/scope được cấu hình.
- Client phải hiểu rằng giá trị tham chiếu là ID, không phải object đầy đủ.
- Khi deserialize graph, Jackson cần resolve ID về object tương ứng; nếu ID không được định nghĩa trong payload hoặc resolver không thể tìm thấy, quá trình đọc JSON có thể thất bại.
- Đây là quy tắc serialization/deserialization của Jackson, không tự động thay thế cơ chế association resource và URI của Spring Data REST.

Không chọn JsonIdentityInfo chỉ để “ẩn lỗi vòng lặp”. Trước hết hãy xác định hợp đồng JSON mà client cần nhận.

## 6. Cách 3: JsonIgnore hoặc JsonProperty để kiểm soát một chiều

Nếu API không cần trả tham chiếu ngược, có thể bỏ hẳn thuộc tính back-reference khỏi JSON:

~~~java
@Entity
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;

    @JsonIgnore
    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;
}
~~~

Khi serialize, thuộc tính `order` bị bỏ qua và vòng lặp bị cắt tại child.

Tuy nhiên, `@JsonIgnore` thường ảnh hưởng cả serialization lẫn deserialization của logical property. Nếu muốn client chỉ đọc được một field nhưng không ghi được, có thể dùng:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private PurchaseOrder order;
~~~

Hoặc nếu chỉ muốn nhận dữ liệu từ request nhưng không xuất trong response:

~~~java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private PurchaseOrder order;
~~~

Đây là các quy tắc Jackson cho JSON property. Khi áp dụng trên entity được Spring Data REST quản lý, cần kiểm thử cả item representation, association links và request body. Annotation có thể làm thay đổi cả cách framework nhận diện/serialize property, nên không nên áp dụng hàng loạt chỉ để loại bỏ một vòng lặp trong custom endpoint.

## 7. So sánh các chiến lược chống vòng lặp

| Chiến lược | JSON response | Deserialization | Phù hợp khi |
| --- | --- | --- | --- |
| HAL association link | Trả link tới resource liên quan | Dùng association endpoint/URI | API Spring Data REST muốn client điều hướng theo HATEOAS |
| JsonManagedReference / JsonBackReference | Giữ chiều forward, bỏ chiều back | Jackson gán lại back reference | Cây parent-child đơn giản |
| JsonIdentityInfo | Object đầu tiên đầy đủ, lần sau tham chiếu ID | Cần resolve object ID | Graph có nhiều tham chiếu chéo |
| JsonIgnore | Bỏ property khỏi JSON | Thường bỏ qua cả property khi đọc | API không cần chiều tham chiếu đó |
| JsonProperty Access | Chọn read-only hoặc write-only | Theo access mode đã đặt | Field chỉ được phép đọc hoặc ghi |
| DTO / projection | Chỉ xuất field được chọn | Mapping riêng hoặc read model | Contract API cần kiểm soát rõ ràng |

Không có annotation nào phù hợp cho mọi domain model. Hãy chọn theo representation mà client cần, khả năng deserialize request và cách Spring Data REST đang quản lý association.

## 8. Hibernate proxy là gì?

Hibernate thường dùng lazy loading để tránh tải mọi association ngay khi đọc entity. Với `FetchType.LAZY`, một quan hệ có thể được biểu diễn bằng proxy hoặc persistent collection chưa được khởi tạo.

Ví dụ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

Khi truy vấn PurchaseOrder, Hibernate có thể chỉ tải cột của order. Thuộc tính customer có thể là proxy chỉ chứa identifier; lines có thể là persistent collection chưa đọc dữ liệu.

Khi một getter được gọi, Hibernate có thể cần truy vấn database để lấy dữ liệu thực. Điều này giúp tiết kiệm truy vấn và bộ nhớ khi association không được sử dụng.

Proxy không phải entity đã tải đầy đủ. Nó là đối tượng đại diện cho entity/collection và cần persistence context còn hoạt động để tải phần dữ liệu chưa có.

## 9. LazyInitializationException khi serialize sau khi Session đóng

Hibernate ném `LazyInitializationException` khi code truy cập dữ liệu chưa được tải bên ngoài một Session đang mở. Trường hợp thường gặp:

1. Repository lấy PurchaseOrder.
2. Service trả entity ra ngoài sau khi transaction kết thúc.
3. Entity trở thành detached; proxy customer hoặc collection lines vẫn chưa được khởi tạo.
4. Jackson bắt đầu serialize và gọi `getCustomer()` hoặc duyệt `getLines()`.
5. Hibernate không còn Session để tải dữ liệu và ném `LazyInitializationException`.

Ví dụ lỗi thường xuất hiện trong log:

~~~text
org.hibernate.LazyInitializationException:
could not initialize proxy - no Session
~~~

Hoặc:

~~~text
failed to lazily initialize a collection of role:
PurchaseOrder.lines: could not initialize proxy - no Session
~~~

Đây là vấn đề vòng đời persistence context, không phải vòng lặp JSON. Thêm `@JsonManagedReference` có thể cắt vòng lặp nhưng không tự mở Session và không tải association cần thiết.

Ngược lại, giữ Session mở cũng không tự giải quyết vòng lặp: Jackson vẫn có thể đi qua parent-child-parent nếu representation serialize toàn bộ graph.

## 10. Open EntityManager in View và truy vấn phát sinh khi serialize

Trong ứng dụng Spring Boot servlet, Open EntityManager in View được bật mặc định theo cấu hình mặc định. Spring đăng ký interceptor để EntityManager tiếp tục mở trong thời gian xử lý web request, hỗ trợ lazy loading ở tầng view.

Có thể tắt bằng:

~~~properties
spring.jpa.open-in-view=false
~~~

Khi OSIV bật, Jackson hoặc Spring Data REST có thể chạm tới proxy khi serialize và làm phát sinh SQL trong giai đoạn render response, dù service transaction đã kết thúc. Điều này có thể khiến:

- Response chạy được trong môi trường development nhưng lỗi khi OSIV bị tắt ở production.
- Một response duyệt nhiều entity gây nhiều truy vấn bổ sung (N+1).
- Thời gian truy vấn bị phân tán giữa service layer và quá trình serialize, khó quan sát hơn.
- Một association tưởng như chỉ là link/preview lại kích hoạt tải dữ liệu do custom serializer hoặc projection gọi getter.

OSIV là một lựa chọn kiến trúc, không phải giải pháp fetch plan. Nếu tắt OSIV, hãy chuẩn bị dữ liệu cần trả về trong transaction hoặc dùng representation không truy cập proxy chưa tải.

## 11. Kiểm soát dữ liệu cần tải trước khi serialize

### Dùng EntityGraph

Với Spring Data JPA, có thể khai báo association cần tải trên query method:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"lines", "customer"})
    Optional<PurchaseOrder> findWithDetailsById(Long id);
}
~~~

EntityGraph chỉ định các thuộc tính cần fetch cho truy vấn. Nó hữu ích khi một use case cần một graph cụ thể mà không muốn đổi mọi association thành EAGER.

Nếu Spring Data REST đang dùng method repository mặc định `findById`, method custom `findWithDetailsById` không tự động thay thế endpoint item GET. Có thể dùng service/controller tùy chỉnh để gọi query có EntityGraph và map response, hoặc cấu hình repository method exposure phù hợp. Đừng giả định chỉ cần khai báo method là endpoint GET item mặc định sẽ gọi nó.

### Dùng fetch join hoặc query chuyên biệt

Có thể dùng JPQL fetch join khi cần:

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    left join fetch o.lines
    where o.id = :id
    """)
Optional<PurchaseOrder> findDetailedById(@Param("id") Long id);
~~~

Fetch join tải association trong cùng query. Khi fetch nhiều collection, cần lưu ý row multiplication, duplicate root rows, phân trang và count query. Không nên fetch join collection một cách vô điều kiện cho mọi endpoint.

### Map sang DTO bên trong transaction

Đây thường là cách kiểm soát response rõ ràng nhất cho custom API:

~~~java
public record OrderLineResponse(
        Long id,
        String sku,
        int quantity
) {}

public record OrderResponse(
        Long id,
        String orderNumber,
        String customerName,
        List<OrderLineResponse> lines
) {}
~~~

~~~java
@Service
public class OrderQueryService {

    private final PurchaseOrderRepository repository;

    public OrderQueryService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderResponse getOrder(Long id) {
        PurchaseOrder order = repository.findDetailedById(id)
                .orElseThrow();

        List<OrderLineResponse> lines = order.getLines().stream()
                .map(line -> new OrderLineResponse(
                        line.getId(),
                        line.getSku(),
                        line.getQuantity()))
                .toList();

        return new OrderResponse(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomer().getName(),
                lines);
    }
}
~~~

DTO được tạo khi persistence context còn mở. Jackson serialize các giá trị đã materialize, không phải Hibernate proxy. DTO cũng tránh trả trực tiếp toàn bộ entity graph hoặc các thuộc tính nội bộ.

Nếu dùng Spring Data REST mặc định, có thể cân nhắc projection/excerpt để giới hạn dữ liệu. Tuy nhiên, getter của projection truy cập association LAZY vẫn có thể kích hoạt query; projection kiểm soát field xuất ra, không tự đảm bảo fetch plan tối ưu.

## 12. Hibernate.initialize và giới hạn của việc khởi tạo thủ công

Hibernate cung cấp:

~~~java
Hibernate.initialize(order.getLines());
~~~

Lệnh này buộc khởi tạo proxy hoặc persistent collection khi Session còn mở. Có thể kiểm tra trạng thái bằng:

~~~java
boolean initialized = Hibernate.isInitialized(order.getLines());
~~~

Một điểm quan trọng: với association dạng nhiều phần tử, `Hibernate.initialize(collection)` chỉ bảo đảm collection được khởi tạo; không bảo đảm mọi entity bên trong collection cũng đã được tải đầy đủ. Nếu serializer tiếp tục truy cập một association LAZY trên từng OrderLine, truy vấn khác hoặc LazyInitializationException vẫn có thể xảy ra.

Không dùng initialize một cách tràn lan để “chữa” serialization. Fetch plan theo use case, EntityGraph hoặc DTO thường dễ dự đoán và kiểm soát hơn.

## 13. Lombok cũng có thể tạo vòng lặp

Các annotation Lombok như `@Data`, `@ToString` và `@EqualsAndHashCode` có thể đưa các thuộc tính quan hệ vào phương thức sinh tự động.

Ví dụ:

~~~java
@Data
@Entity
public class PurchaseOrder {

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines;
}
~~~

Nếu Order.toString() in lines và OrderLine.toString() in order, việc log entity có thể tạo vòng lặp đệ quy dù Jackson không chạy.

Với entity JPA, nên chọn getter/setter có chủ đích hoặc loại association khỏi các phương thức sinh tự động:

~~~java
@Getter
@Setter
@Entity
public class PurchaseOrder {

    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Cần cân nhắc kỹ equals/hashCode của entity có ID được sinh tự động. So sánh toàn bộ quan hệ có thể gây đệ quy, tải lazy không mong muốn và thay đổi hash code khi entity chuyển từ transient sang persistent.

## 14. Tùy chỉnh ObjectMapper của Spring Data REST

Spring Data REST cho phép bổ sung Jackson module, serializer và deserializer bằng cách override `configureJacksonObjectMapper` trong `RepositoryRestConfigurer`.

Ví dụ cấu trúc:

~~~java
@Configuration
public class RestRepresentationConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureJacksonObjectMapper(
            MapperBuilder<? extends ObjectMapper,
                    ? extends MapperBuilder<?, ?>> mapperBuilder) {

        mapperBuilder.addModule(new SimpleModule("OrderJsonModule") {
            @Override
            public void setupModule(SetupContext context) {
                // Register only the serializers/deserializers
                // required by the application's domain model.
            }
        });
    }
}
~~~

ObjectMapper của Spring Data REST có module đặc biệt để serialize và deserialize PersistentEntity thành representation/links. Khi thêm module tùy chỉnh, cần giữ nguyên cấu hình và module mà exporter yêu cầu; không thay toàn bộ ObjectMapper bằng mapper tự tạo nếu chưa hiểu các serializer của Spring Data REST.

Chỉ dùng custom serializer khi domain model thực sự không thể biểu diễn phù hợp bằng association link, projection hoặc DTO. Serializer nên có output ổn định, tránh tự truy cập graph sâu và không kích hoạt hàng loạt lazy loads.

## 15. Kiểm thử vòng lặp và proxy

Nên kiểm tra hai nhóm độc lập.

### Kiểm tra vòng lặp JSON

Với Jackson ObjectMapper dùng trong custom endpoint, có thể kiểm tra response không lặp parent:

~~~java
@Test
void serializesOrderWithoutBackReferenceLoop() throws Exception {
    String json = objectMapper.writeValueAsString(order);

    JsonNode root = objectMapper.readTree(json);

    assertThat(root.path("lines")).isNotEmpty();
    assertThat(root.path("lines").get(0).has("order")).isFalse();
}
~~~

Test cần dùng đúng ObjectMapper của ứng dụng hoặc ObjectMapper cấu hình tương đương. Test bằng mapper tự tạo không chứng minh Spring Data REST exporter có cùng hành vi.

### Kiểm tra HAL association links

~~~java
mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.lines.href").exists());
~~~

Test này xác nhận association được biểu diễn bằng link theo cấu hình Spring Data REST.

### Kiểm tra lazy loading khi OSIV tắt

Trong integration test, đặt:

~~~properties
spring.jpa.open-in-view=false
~~~

Sau đó gọi endpoint có projection/serializer đọc association và xác nhận:

- Response không ném LazyInitializationException.
- Số lượng SQL phù hợp với fetch plan.
- Không có N+1 query khi collection có nhiều phần tử.
- Association cần thiết được tải trong transaction.
- Association không được chọn không bị tải ngoài ý muốn.

Có thể bật Hibernate statistics hoặc SQL logging trong test profile để quan sát số query. Không nên chỉ kiểm tra HTTP 200 vì response có thể vẫn thành công nhưng phát sinh nhiều truy vấn ngoài dự kiến.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Jackson báo infinite recursion hoặc StackOverflowError | Parent và child serialize tham chiếu qua lại | Dùng HAL links, managed/back references, object identity hoặc DTO |
| Spring Data REST trả association link nhưng custom API bị vòng lặp | Hai đường serialize dùng ObjectMapper/representation khác nhau | Kiểm tra controller và mapper đang xử lý response |
| LazyInitializationException khi GET | Serializer truy cập proxy sau khi Session đóng | Fetch dữ liệu trong transaction hoặc map DTO |
| Response chạy được khi OSIV bật nhưng lỗi khi tắt | Serialization đang dựa vào lazy loading ngoài service transaction | Xác định fetch plan và kiểm thử với OSIV false |
| Response chậm dù entity query nhanh | Jackson/projection kích hoạt nhiều truy vấn lazy | Dùng EntityGraph, fetch query hoặc DTO; đo số SQL |
| JsonBackReference không hoạt động | Đặt annotation lên collection hoặc tên cặp không khớp | Đặt trên thuộc tính bean đơn và dùng cùng reference name |
| Deserialize mất liên kết parent-child | Dùng @JsonIgnore hoặc back-reference không đúng chiều | Kiểm tra cặp managed/back reference và owning side |
| @JsonIdentityInfo tạo ID thay cho object | Jackson đã gặp object trước đó trong graph | Đảm bảo client hỗ trợ ID reference và resolver |
| Log entity bị đệ quy | Lombok toString/equals/hashCode duyệt quan hệ hai chiều | Exclude association hoặc định nghĩa phương thức có chủ đích |

## 17. Chọn cách xử lý theo loại API

| Trường hợp | Hướng xử lý phù hợp |
| --- | --- |
| Repository resource Spring Data REST chuẩn | Ưu tiên association links và HAL navigation |
| Custom REST endpoint cần JSON cây parent-child | DTO hoặc JsonManagedReference/JsonBackReference |
| Domain graph có nhiều tham chiếu chéo | JsonIdentityInfo hoặc DTO có ID reference |
| Response chỉ cần vài field và association tóm tắt | Projection hoặc excerpt |
| Response cần dữ liệu LAZY | EntityGraph/fetch query và map trong transaction |
| Muốn kiểm soát chặt response và tránh lộ field | DTO với allowlist thuộc tính |

Hãy tách câu hỏi “JSON nên có cấu trúc gì?” khỏi câu hỏi “Hibernate cần tải dữ liệu nào?”. Jackson annotation giải quyết hình dạng JSON; EntityGraph/fetch query giải quyết dữ liệu được tải; transaction/persistence context quyết định proxy có thể tải hay không.

## Tài liệu tham khảo

- [Spring Data REST 5.1.2 — Domain Object Representations](https://docs.spring.io/spring-data/rest/reference/representations.html): ObjectMapper đặc biệt của exporter, association links, custom Jackson modules và serializers.
- [Spring Data REST 5.1.2 — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): item resources, association resources và HAL links.
- [Jackson 2.21 — JsonManagedReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml/jackson/annotation/JsonManagedReference.html) và [JsonBackReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml/jackson/annotation/JsonBackReference.html): cặp forward/back reference và quy tắc serialize/deserialize.
- [Jackson 2.21 — JsonIdentityInfo](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml/jackson/annotation/JsonIdentityInfo.html) và [JsonIdentityReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml/jackson/annotation/JsonIdentityReference.html): object identity và tham chiếu bằng ID.
- [Hibernate ORM 7.2 — LazyInitializationException](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/LazyInitializationException.html): lỗi khi truy cập dữ liệu chưa tải ngoài Session đang mở.
- [Hibernate ORM — Hibernate utilities](https://docs.jboss.org/hibernate/orm/current/javadocs/org/hibernate/Hibernate.html): Hibernate.initialize và Hibernate.isInitialized cho proxy/collection.
- [Spring Boot — SQL Databases, Open EntityManager in View](https://docs.spring.io/spring-boot/reference/data/sql.html): mặc định OpenEntityManagerInViewInterceptor và cấu hình spring.jpa.open-in-view.
