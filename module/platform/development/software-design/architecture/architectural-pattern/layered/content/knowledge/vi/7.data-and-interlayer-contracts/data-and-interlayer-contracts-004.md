# Đặt mapper tại biên phù hợp và kiểm soát chi phí ánh xạ

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, trong chương **Dữ liệu và hợp đồng giữa các tầng**. Module hướng tới cách tổ chức phần mềm theo kiến trúc phân tầng, trong đó presentation, application, business/domain và data access có trách nhiệm riêng, cộng tác qua các hợp đồng có chủ đích. Bài này tập trung vào việc đặt mapper đúng ranh giới và kiểm soát chi phí khi chuyển dữ liệu giữa các mô hình.

Mapper là thành phần chuyển đổi dữ liệu từ một cấu trúc hoặc hợp đồng sang cấu trúc khác. Một mapper tốt giúp hai phía thay đổi độc lập và làm rõ ý nghĩa dữ liệu tại ranh giới. Tuy nhiên, mỗi lần ánh xạ cũng tạo thêm mã, đối tượng, phép chuyển đổi và khả năng sai lệch. Vì vậy, cần chọn vị trí và mức độ ánh xạ theo nhu cầu thực tế của ứng dụng.

## 1. Mapper giải quyết vấn đề gì?

Trong ứng dụng phân tầng, một thông tin có thể xuất hiện dưới nhiều hình dạng. Ví dụ, yêu cầu tạo đơn hàng từ HTTP, dữ liệu mà ca sử dụng cần, mô hình nghiệp vụ và cấu trúc lưu trong cơ sở dữ liệu có thể khác nhau:

| Mô hình dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| HTTP request/response DTO | Hợp đồng với client và giao thức HTTP | `CreateOrderRequest`, `OrderResponse` |
| Application command/result | Đầu vào và kết quả của một ca sử dụng | `PlaceOrderCommand`, `PlaceOrderResult` |
| Domain model | Trạng thái, hành vi và quy tắc nghiệp vụ | `Order`, `OrderLine`, `Money` |
| Persistence model/entity | Biểu diễn phù hợp với schema và ORM | `OrderJpaEntity`, `OrderLineJpaEntity` |

Các mô hình này có thể trùng nhau trong ứng dụng đơn giản. Chúng nên tách ra khi có khác biệt về mục đích, quyền truy cập, ngữ nghĩa hoặc vòng đời thay đổi.

Ví dụ, API có thể nhận `productCode` và `quantity`; application command biểu diễn ý định đặt hàng; domain cần `ProductId` và một dòng hàng hợp lệ; entity JPA cần khóa ngoại và các trường phục vụ lưu trữ. Mapper chuyển dữ liệu giữa các hình dạng đó.

Nếu dùng chung một đối tượng cho mọi tầng, thay đổi schema có thể ảnh hưởng API, annotation ORM có thể rò rỉ vào mô hình nghiệp vụ, hoặc client có thể gửi những trường nội bộ mà họ không được phép quyết định. Nếu tạo quá nhiều mô hình gần như giống hệt nhau, nhóm phải duy trì nhiều mapper và kiểm tra sự nhất quán giữa chúng.

Mục tiêu không phải tạo càng nhiều DTO càng tốt. Mục tiêu là dùng mapper tại nơi hai hợp đồng thực sự gặp nhau, để mỗi phía giữ được trách nhiệm và quyền kiểm soát của mình.

## 2. Đặt mapper ở biên nào?

Một nguyên tắc thực dụng là: **mapper thuộc về adapter hoặc tầng đang chuyển đổi dữ liệu từ hợp đồng bên ngoài sang hợp đồng mà nó gọi, hoặc ngược lại**. Mapper cần hiểu cả kiểu nguồn và kiểu đích, vì vậy nên đặt ở phía có trách nhiệm kết nối hai phía đó.

Trong ứng dụng Java/Spring, các vị trí thường gặp:

| Ranh giới | Chuyển đổi | Vị trí mapper thường phù hợp |
|---|---|---|
| HTTP vào application | Request DTO → command/input model | Presentation adapter hoặc package API |
| Application ra HTTP | Result/domain view → response DTO | Presentation adapter hoặc package API |
| Domain/application vào lưu trữ | Domain model → persistence entity | Persistence adapter |
| Lưu trữ trả dữ liệu | Persistence entity/projection → domain/read model | Persistence adapter |
| Message vào ca sử dụng | Message payload → command | Messaging adapter |
| Kết quả ca sử dụng ra message | Result/event → message payload | Messaging adapter |

### 2.1. Mapper ở biên HTTP

Controller hoặc presentation adapter biết cấu trúc JSON, kiểu dữ liệu của request và định dạng response. Nó chuyển request DTO thành command mà application service hiểu được. Chiều ngược lại, nó chuyển kết quả ca sử dụng thành response DTO.

Ví dụ:

```java
public record CreateOrderRequest(
        String customerId,
        List<OrderLineRequest> lines
) {}

public record OrderLineRequest(
        String productCode,
        int quantity
) {}

public record PlaceOrderLine(
        String productCode,
        int quantity
) {}

public record PlaceOrderCommand(
        String customerId,
        List<PlaceOrderLine> lines
) {}

public record PlaceOrderResult(
        UUID orderId,
        String status
) {}

public record OrderResponse(
        UUID id,
        String status
) {}
```

Mapper HTTP có thể được viết thủ công:

```java
@Component
class OrderHttpMapper {
    PlaceOrderCommand toCommand(CreateOrderRequest request) {
        var lines = request.lines().stream()
                .map(line -> new PlaceOrderLine(
                        line.productCode(),
                        line.quantity()))
                .toList();

        return new PlaceOrderCommand(request.customerId(), lines);
    }

    OrderResponse toResponse(PlaceOrderResult result) {
        return new OrderResponse(result.orderId(), result.status());
    }
}
```

Controller dùng mapper rồi gọi ca sử dụng:

```java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final PlaceOrderUseCase placeOrder;
    private final OrderHttpMapper mapper;

    OrderController(PlaceOrderUseCase placeOrder, OrderHttpMapper mapper) {
        this.placeOrder = placeOrder;
        this.mapper = mapper;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        var result = placeOrder.handle(mapper.toCommand(request));
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(mapper.toResponse(result));
    }
}
```

Ở đây mapper không quyết định đơn hàng có hợp lệ hay khách hàng có được đặt hàng hay không. Nó chuyển đổi cấu trúc dữ liệu. Validation cú pháp ở biên HTTP có thể kiểm tra trường bắt buộc hoặc định dạng; quy tắc nghiệp vụ vẫn phải được bảo vệ trong application/domain để các đường gọi khác như tác vụ nền hoặc message consumer cũng tuân thủ.

### 2.2. Mapper ở biên lưu trữ

Persistence adapter biết entity JPA, repository cụ thể và cách đọc/ghi dữ liệu. Nó chuyển mô hình mà application/domain sử dụng sang entity, rồi chuyển kết quả truy vấn trở lại.

```java
@Repository
class JpaOrderStore implements OrderStore {
    private final SpringDataOrderRepository repository;
    private final OrderPersistenceMapper mapper;

    JpaOrderStore(
            SpringDataOrderRepository repository,
            OrderPersistenceMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return repository.findById(id.value())
                .map(mapper::toDomain);
    }
}
```

`OrderStore` là hợp đồng mà application/domain cần; `JpaOrderStore` là adapter triển khai hợp đồng bằng Spring Data JPA. Mapper lưu trữ có thể nằm trong cùng package với adapter vì nó phụ thuộc vào cả mô hình nghiệp vụ và entity JPA.

Không phải mọi ứng dụng đều cần tách domain model và entity. Với CRUD đơn giản, ít quy tắc và một vòng đời dữ liệu gần như thống nhất, application service có thể làm việc trực tiếp với entity. Khi đó có thể không cần mapper riêng. Nếu quyết định tách, mapper nên được giữ ở phía persistence để domain không phải biết về annotation, quan hệ hoặc kiểu dữ liệu của JPA.

### 2.3. Mapper không thuộc lõi nghiệp vụ

Một mapper HTTP không nên được gọi từ domain vì domain sẽ phải biết kiểu request/response của Spring MVC. Mapper JPA cũng không nên đặt trong domain nếu nó kéo theo annotation hoặc kiểu của Hibernate.

Lõi nghiệp vụ có thể cung cấp constructor, factory hoặc phương thức khôi phục trạng thái để adapter tạo đối tượng hợp lệ. Ví dụ, `Order.place(...)` có thể tạo đơn hàng mới và kiểm tra bất biến; `Order.reconstitute(...)` có thể khôi phục trạng thái đã lưu theo hợp đồng được thiết kế rõ. Mapper gọi những điểm vào đó, còn quy tắc vẫn thuộc domain.

Cũng không nên tạo một `CommonMapper` khổng lồ dùng chung cho toàn ứng dụng nếu nó gom các chuyển đổi không cùng trách nhiệm. Các mapper nhỏ theo ranh giới thường dễ hiểu, kiểm thử và thay đổi hơn.

## 3. Chuyển đổi cấu trúc không đồng nghĩa với thực thi nghiệp vụ

Mapper nên tập trung vào việc biểu diễn cùng một thông tin dưới hình dạng khác. Một số việc thường phù hợp với mapper:

- Đổi tên trường hoặc chuyển cấu trúc lồng nhau.
- Chuyển kiểu dữ liệu có quy tắc biểu diễn rõ ràng, chẳng hạn chuỗi thành mã định danh.
- Chuyển danh sách phần tử sang danh sách tương ứng.
- Bỏ trường nội bộ khỏi response hoặc đặt giá trị mặc định theo hợp đồng kỹ thuật đã xác định.
- Chuyển kiểu ngày giờ giữa hai biểu diễn có cùng ngữ nghĩa.

Một số việc không nên bị giấu trong mapper:

- Tính giá bán, chiết khấu hoặc thuế theo chính sách.
- Kiểm tra quyền người dùng hoặc điều kiện chuyển trạng thái.
- Tự truy vấn repository để tìm dữ liệu liên quan.
- Phát sự kiện, gửi email hoặc thực hiện side effect.
- Quyết định một đối tượng nghiệp vụ có hợp lệ hay không.

Ví dụ, mapper có thể chuyển `productCode` thành `ProductId`, nhưng việc sản phẩm có tồn tại và có được phép bán hay không thuộc application/domain. Mapper có thể chuyển số tiền từ một DTO sang kiểu `Money`, nhưng quy tắc tổng tiền, giới hạn chiết khấu và làm tròn thuộc chính sách nghiệp vụ.

Nếu mapper phải gọi database hoặc dịch vụ mạng, ranh giới trách nhiệm đang bị mờ. Việc lấy dữ liệu nên do application service hoặc adapter có trách nhiệm điều phối thực hiện; sau đó mapper chuyển đổi dữ liệu đã có. Điều này giúp mapper dễ kiểm thử, không phát sinh I/O bất ngờ và không che giấu chi phí truy vấn.

## 4. Kiểm soát các chi phí của ánh xạ

Ánh xạ có nhiều loại chi phí. Không nên chỉ nhìn vào thời gian CPU của một phép gán thuộc tính.

### 4.1. Chi phí xử lý và cấp phát bộ nhớ

Mỗi lần chuyển đổi có thể tạo đối tượng mới, duyệt collection, chuyển đổi kiểu hoặc sao chép dữ liệu. Trong một request đơn lẻ, chi phí thường nhỏ so với I/O. Nhưng nếu hệ thống xử lý hàng chục nghìn bản ghi, ánh xạ nhiều lượt qua các mô hình gần giống nhau có thể làm tăng allocation và áp lực garbage collection.

Ví dụ, một luồng có thể chuyển entity thành read model, read model thành application DTO, rồi lại thành response DTO dù các mô hình không có khác biệt có ý nghĩa. Hãy xem xét có thể trả về một projection phù hợp ngay từ truy vấn hay không, hoặc liệu một mô hình có thể phục vụ hai ranh giới mà không làm rò rỉ trách nhiệm.

Không nên tối ưu bằng cách bỏ mọi mapper. Hãy đo thời gian và allocation trước khi thay đổi. Một lần chuyển đổi rõ ràng có thể rẻ hơn nhiều so với sự phụ thuộc chặt chẽ và chi phí bảo trì mà nó giúp tránh.

### 4.2. Chi phí truy vấn phát sinh trong lúc ánh xạ

Một mapper có thể trông như chỉ đọc thuộc tính, nhưng entity JPA có quan hệ lazy. Khi mapper duyệt qua collection hoặc gọi getter của quan hệ chưa tải, Hibernate có thể phát sinh truy vấn bổ sung. Lặp qua nhiều entity có thể tạo ra vấn đề N+1.

Ví dụ, chuyển danh sách 100 đơn hàng và đọc `order.getLines()` có thể tạo một truy vấn lấy đơn hàng và thêm nhiều truy vấn lấy dòng hàng, tùy cấu hình và cách tải dữ liệu. Chi phí chính ở đây là I/O cơ sở dữ liệu, không phải phép chuyển đổi Java.

Cách kiểm soát:

- Xác định dữ liệu mà use case hoặc màn hình thực sự cần.
- Tải dữ liệu phù hợp bằng fetch join, entity graph hoặc truy vấn riêng có chủ đích.
- Dùng projection khi chỉ cần một tập trường đọc.
- Phân trang khi xử lý tập dữ liệu lớn.
- Tránh để mapper tự truy vấn hoặc tự quyết định chiến lược tải.
- Kiểm tra số lượng SQL trong integration test hoặc công cụ quan sát khi có nguy cơ N+1.

Mapper nên nhận dữ liệu đã được chuẩn bị phù hợp. Việc truy vấn và tối ưu tải dữ liệu thuộc repository/adapter và application orchestration.

### 4.3. Chi phí bảo trì và đồng bộ hợp đồng

Khi một trường mới được thêm vào, mọi mapper liên quan có thể cần cập nhật. Nếu hệ thống có nhiều bản sao mô hình, nguy cơ quên ánh xạ, ánh xạ sai hoặc mất thông tin tăng lên.

Ví dụ, thêm `deliveryInstruction` vào request nhưng quên chuyển nó vào command khiến dữ liệu biến mất trước khi tới application service. Thêm `currency` vào domain nhưng mapper response chỉ trả số tiền có thể khiến client hiểu sai giá trị. Những lỗi này thường không được phát hiện nếu test chỉ kiểm tra đối tượng có được tạo hay không.

Hãy quản lý hợp đồng một cách có chủ đích:

- Đặt tên trường theo ý nghĩa ở từng phía; không cố ép tên phải giống nhau nếu ngữ nghĩa khác.
- Xác định rõ trường nào bắt buộc, tùy chọn, chỉ đọc hoặc chỉ được hệ thống quyết định.
- Khi thêm trường, kiểm tra toàn bộ đường đi của dữ liệu từ nguồn tới nơi sử dụng.
- Với API công khai, cân nhắc tương thích ngược và phiên bản hợp đồng.
- Với message được lưu hoặc truyền lâu dài, xác định cách xử lý khi consumer nhận phiên bản cũ hoặc mới.

## 5. Những trường hợp ánh xạ cần xử lý cẩn thận

### 5.1. Null, trường vắng mặt và cập nhật một phần

Trong request tạo mới, `null` có thể có nghĩa là không cung cấp giá trị. Trong request cập nhật một phần, ba trạng thái có thể khác nhau:

- Trường không xuất hiện: giữ nguyên giá trị hiện tại.
- Trường xuất hiện với `null`: xóa giá trị nếu hợp đồng cho phép.
- Trường xuất hiện với giá trị: cập nhật thành giá trị đó.

Nếu mapper chuyển cả trường vắng mặt và `null` thành cùng một giá trị Java, nó có thể xóa dữ liệu ngoài ý muốn. Cần dùng kiểu dữ liệu hoặc cấu trúc biểu diễn được sự khác biệt này, chẳng hạn wrapper có trạng thái hiện diện, JSON Merge Patch hoặc command có các thao tác cập nhật rõ ràng.

Không nên dùng phép sao chép toàn bộ thuộc tính từ request vào entity rồi lưu trực tiếp. Cách đó có thể cho phép client ghi vào `id`, `status`, `ownerId`, `createdAt` hoặc các trường chỉ hệ thống được quyền quyết định. Hãy ánh xạ danh sách trường được phép cập nhật và để application/domain thực hiện quy tắc tương ứng.

### 5.2. Tiền tệ và số

Không chuyển tiền sang `double` chỉ để thuận tiện ánh xạ. Dùng `BigDecimal` hoặc kiểu tiền tệ phù hợp, xác định rõ scale, currency và quy tắc làm tròn. Hai giá trị `100` có thể mang ý nghĩa khác nhau nếu một bên là VND và bên kia là USD.

Mapper có thể chuyển cấu trúc như `amount` và `currencyCode` thành một đối tượng `Money`, nhưng cần bảo đảm cách biểu diễn giữ nguyên độ chính xác. Quy tắc cộng, đổi tỷ giá và làm tròn thuộc nghiệp vụ hoặc dịch vụ chuyên trách.

### 5.3. Thời gian và múi giờ

`LocalDate`, `LocalDateTime`, `OffsetDateTime` và `Instant` biểu diễn các khái niệm khác nhau. Không nên chuyển đổi máy móc chỉ vì hai trường cùng được lưu dưới dạng timestamp.

Ví dụ, ngày giao hàng có thể là ngày lịch theo múi giờ địa phương; thời điểm tạo đơn là một thời điểm tuyệt đối. Mapper cần biết hợp đồng nguồn và đích, còn quy tắc xác định múi giờ mặc định phải được thống nhất ở tầng phù hợp. Chuyển sai có thể làm ngày hoặc thời điểm lệch khi client ở múi giờ khác.

### 5.4. Enum và trạng thái

Tên enum nội bộ không nhất thiết là mã công khai của API hoặc giá trị lưu trong database. Nếu đổi tên `CONFIRMED` thành `ACCEPTED` trong Java, dữ liệu lưu theo `EnumType.STRING` có thể bị ảnh hưởng; API cũng có thể cần giữ mã cũ để tương thích.

Nên ánh xạ enum một cách tường minh khi giá trị có ý nghĩa hợp đồng. Tránh dùng ordinal vì thay đổi thứ tự enum có thể làm dữ liệu cũ được diễn giải sai. Với trạng thái nghiệp vụ, mapper chỉ chuyển biểu diễn; việc chuyển từ trạng thái này sang trạng thái khác phải được domain thực hiện theo quy tắc.

### 5.5. Collection, quan hệ hai chiều và vòng tham chiếu

Entity có thể có quan hệ hai chiều như `Order` chứa `OrderLine`, còn `OrderLine` lại tham chiếu về `Order`. Ánh xạ đệ quy cả hai chiều có thể gây vòng lặp hoặc tạo đồ thị đối tượng rất lớn. Response API cũng không nên vô tình trả toàn bộ đồ thị ORM.

Hãy chọn rõ hướng và độ sâu của dữ liệu cần chuyển. Ví dụ response đơn hàng có thể chứa danh sách dòng hàng với mã và số lượng, nhưng không cần lồng lại toàn bộ đơn hàng trong từng dòng. Với collection lớn, cân nhắc phân trang hoặc endpoint riêng.

## 6. Chọn cách triển khai mapper

Không có một công cụ duy nhất phù hợp cho mọi dự án. Ba lựa chọn phổ biến:

| Cách triển khai | Phù hợp khi | Điểm cần chú ý |
|---|---|---|
| Ánh xạ thủ công | Chuyển đổi ít trường, có điều kiện hoặc quy tắc rõ ràng | Có thể lặp mã nếu số mô hình và trường tăng |
| MapStruct | Nhiều chuyển đổi có cấu trúc ổn định, muốn sinh mã lúc biên dịch | Cần cấu hình rõ trường đặc biệt và kiểm tra mã sinh ra |
| Reflection/runtime mapper | Mô hình linh hoạt hoặc có nhu cầu cấu hình động | Có thể khó theo dõi lỗi lúc biên dịch và có chi phí runtime |

Ánh xạ thủ công thường dễ đọc:

```java
OrderResponse toResponse(OrderView view) {
    return new OrderResponse(
            view.id().toString(),
            view.status().apiCode(),
            view.total().amount(),
            view.total().currency().getCurrencyCode());
}
```

Với MapStruct, có thể khai báo hợp đồng chuyển đổi:

```java
@Mapper(componentModel = "spring")
public interface OrderHttpMapper {
    PlaceOrderCommand toCommand(CreateOrderRequest request);

    OrderResponse toResponse(PlaceOrderResult result);
}
```

MapStruct sinh mã Java khi biên dịch, giúp nhiều lỗi ánh xạ có thể được phát hiện sớm. Tuy nhiên, công cụ không tự hiểu ý nghĩa nghiệp vụ. Những chuyển đổi như enum công khai, múi giờ, trường bị bỏ qua hoặc giá trị mặc định cần được cấu hình và xem xét rõ ràng. Dùng thư viện không loại bỏ trách nhiệm thiết kế hợp đồng.

Reflection mapper có thể hữu ích trong một số hệ thống cần cấu hình động, nhưng việc ánh xạ theo tên trường có thể che giấu sai lệch cho đến khi chạy. Cần cân nhắc khả năng debug, hiệu năng, an toàn kiểu và mức độ phức tạp của cấu hình.

Không nên tạo abstraction chung cho mapper chỉ để mọi lớp tuân theo một interface giống nhau. Một mapper có thể là một lớp đơn giản với vài phương thức. Chỉ thêm interface hoặc framework khi nó tạo lợi ích thực tế như thay thế implementation, chuẩn hóa một lượng chuyển đổi lớn hoặc hỗ trợ kiểm tra hợp đồng.

## 7. Kiểm thử mapper và đường đi dữ liệu

Kiểm thử nên tập trung vào những chuyển đổi có thể làm thay đổi ý nghĩa hoặc làm mất dữ liệu. Không cần viết một test riêng cho mọi phép gán hiển nhiên nếu test ở ranh giới đã bảo vệ được hành vi.

Một số mức kiểm thử:

- **Unit test mapper:** kiểm tra trường bắt buộc, trường tùy chọn, enum, tiền, thời gian, collection và các trường hợp null/vắng mặt.
- **Test hợp đồng HTTP/message:** kiểm tra payload thực tế và cách chuyển đổi thành command hoặc response.
- **Integration test persistence adapter:** kiểm tra entity mapping, truy vấn, quan hệ lazy, transaction và dữ liệu sau khi đọc lại.
- **Test đường đi end-to-end của dữ liệu:** hữu ích với luồng quan trọng khi dữ liệu qua nhiều ranh giới có nguy cơ bị mất hoặc đổi nghĩa.

Ví dụ unit test cho mapper:

```java
class OrderHttpMapperTest {
    private final OrderHttpMapper mapper = new OrderHttpMapperImpl();

    @Test
    void mapsEveryRequestLineToCommand() {
        var request = new CreateOrderRequest(
                "C-100",
                List.of(
                        new OrderLineRequest("P-10", 2),
                        new OrderLineRequest("P-20", 1)));

        var command = mapper.toCommand(request);

        assertEquals("C-100", command.customerId());
        assertEquals(2, command.lines().size());
        assertEquals("P-10", command.lines().get(0).productCode());
        assertEquals(2, command.lines().get(0).quantity());
    }
}
```

Ví dụ giả định MapStruct đã sinh `OrderHttpMapperImpl`. Nếu mapper được viết thủ công, test có thể khởi tạo trực tiếp lớp mapper. Điều quan trọng là kiểm tra kết quả có giữ đúng dữ liệu và ý nghĩa, không phụ thuộc vào công cụ sinh mã.

Với mapper persistence, cần test thêm hành vi mà unit test không thể xác minh, chẳng hạn entity có được lưu và khôi phục đúng hay không, enum được ghi đúng dạng hay quan hệ có gây truy vấn ngoài dự kiến không. Đừng chỉ mock repository trong mọi test rồi kết luận mapping JPA đã chính xác.

## 8. Quy trình chọn mapper và kiểm soát chi phí

Khi thêm một ranh giới hoặc thay đổi mô hình, có thể thực hiện theo trình tự:

1. **Xác định hai hợp đồng:** dữ liệu đến từ đâu, sẽ được dùng ở đâu, ai sở hữu mỗi mô hình?
2. **Xác định khác biệt ngữ nghĩa:** trường nào chỉ đổi tên, trường nào đổi kiểu, trường nào cần kiểm tra hoặc biến đổi đặc biệt?
3. **Chọn nơi đặt mapper:** presentation adapter, persistence adapter hay messaging adapter tùy ranh giới đang kết nối.
4. **Chỉ ánh xạ dữ liệu cần thiết:** tránh tải và chuyển cả đồ thị đối tượng nếu use case chỉ cần một vài trường.
5. **Giữ mapper thuần:** không truy vấn database, gọi mạng hoặc thực thi chính sách nghiệp vụ bên trong mapper.
6. **Kiểm thử các trường hợp có rủi ro:** null/vắng mặt, enum, tiền, thời gian, collection, trường được phép cập nhật.
7. **Đo khi có vấn đề hiệu năng:** xem số truy vấn, allocation, thời gian xử lý và kích thước dữ liệu trước khi tối ưu.
8. **Rà soát đường đi dữ liệu khi hợp đồng đổi:** bảo đảm trường mới được chuyển đến đúng nơi và không vô tình lộ dữ liệu nội bộ.

Một ví dụ về quyết định tối ưu: nếu API danh sách đơn hàng chỉ hiển thị mã đơn, ngày tạo và tổng tiền, không nhất thiết tải toàn bộ aggregate cùng các dòng hàng rồi ánh xạ tất cả. Một projection hoặc truy vấn đọc riêng có thể phù hợp hơn. Ngược lại, nếu ca sử dụng cần xác minh bất biến của đơn hàng trước khi thay đổi trạng thái, phải tải đủ dữ liệu cần thiết để domain thực hiện quy tắc. Tối ưu dữ liệu không được làm mất kiểm tra nghiệp vụ.

## 9. Dấu hiệu cần xem lại thiết kế ánh xạ

Hãy xem lại thiết kế nếu gặp một trong các tình huống sau:

- Một mapper chứa logic giá, quyền, trạng thái hoặc gọi repository.
- Nhiều mapper chuyển đổi qua các mô hình trung gian giống nhau mà không tạo ranh giới hữu ích.
- Một trường thường xuyên bị quên khi cập nhật DTO, command hoặc entity.
- Mapper response làm lộ entity hoặc quan hệ ORM ra API.
- Việc chuyển đổi kích hoạt nhiều truy vấn database mà người gọi không nhận ra.
- Một phép copy toàn bộ thuộc tính cho phép client ghi vào trường nội bộ.
- Lỗi mapping chỉ xuất hiện ở runtime dù hợp đồng có thể kiểm tra lúc biên dịch.
- Nhóm tối ưu bằng cách dùng chung mọi mô hình dù các phía có quyền và vòng đời khác nhau.

Giải pháp có thể là chuyển mapper về đúng adapter, làm rõ hợp đồng, giảm số mô hình, dùng projection, tải dữ liệu theo use case hoặc bổ sung test. Không nên mặc định rằng thêm framework hay thêm một tầng mới sẽ giải quyết được vấn đề.

## 10. Ghi nhớ

- Mapper chuyển đổi giữa các hợp đồng dữ liệu; nó nên nằm ở adapter hoặc tầng chịu trách nhiệm kết nối hai phía.
- Mapper HTTP thường thuộc presentation adapter; mapper JPA thường thuộc persistence adapter; mapper message thuộc messaging adapter.
- Domain không nên phụ thuộc DTO HTTP hoặc entity JPA chỉ để thực hiện chuyển đổi.
- Mapper nên tập trung vào cấu trúc và biểu diễn dữ liệu. Quy tắc nghiệp vụ, truy vấn và side effect thuộc trách nhiệm khác.
- Chi phí ánh xạ gồm cấp phát đối tượng, CPU, truy vấn phát sinh, nguy cơ mất dữ liệu và chi phí duy trì nhiều hợp đồng.
- Cần chú ý null/vắng mặt, tiền, thời gian, enum, collection và quan hệ lazy.
- Chọn ánh xạ thủ công, MapStruct hoặc công cụ runtime theo quy mô và độ phức tạp; công cụ không thay thế việc thiết kế hợp đồng.
- Kiểm thử các chuyển đổi có rủi ro và đo hiệu năng trước khi tối ưu. Chỉ tách mô hình khi lợi ích độc lập và kiểm soát thay đổi bù được chi phí duy trì.

