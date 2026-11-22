# Phân định API công bố repository và API nghiệp vụ tự thiết kế

Spring Data REST có thể tự động công bố repository thành REST API. Cách này rất tiện khi ứng dụng cần các thao tác đọc, tạo, cập nhật và xóa dữ liệu theo quy ước. Tuy nhiên, API của một hệ thống không chỉ là tập hợp thao tác CRUD trên bảng hoặc entity. Nhiều chức năng thể hiện quy trình, chính sách và ý nghĩa nghiệp vụ riêng.

Vì vậy, khi thiết kế Spring Data REST, cần phân biệt hai loại API:

- **Repository API được Spring Data REST công bố:** tài nguyên và thao tác được sinh từ repository, entity và association.
- **Business API tự thiết kế:** endpoint do ứng dụng định nghĩa để diễn đạt một use case hoặc một quy tắc nghiệp vụ cụ thể.

Hai loại API có thể cùng tồn tại trong một ứng dụng. Điều quan trọng là đặt đúng ranh giới: repository API phù hợp với thao tác dữ liệu đơn giản; business API phù hợp với hành vi và quy trình mà client cần thực hiện.

## 1. Repository API được công bố là gì?

Spring Data REST đọc các repository được export và tạo HTTP resource tương ứng. Với một repository như:

~~~java
@RepositoryRestResource(
    path = "products",
    collectionResourceRel = "products"
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Spring Data REST có thể cung cấp các resource theo quy ước:

| Resource | Ví dụ | Mục đích |
|---|---|---|
| Collection | \`GET /products\` | Đọc danh sách Product |
| Item | \`GET /products/10\` | Đọc một Product |
| Collection create | \`POST /products\` | Tạo Product |
| Item update | \`PUT /products/10\`, \`PATCH /products/10\` | Cập nhật Product |
| Item delete | \`DELETE /products/10\` | Xóa Product |
| Search | \`GET /products/search/by-category?category=book\` | Gọi query method được export |

Đường dẫn và các method cụ thể phụ thuộc repository, cấu hình export, association và phiên bản ứng dụng. Client nên khám phá link trong HAL response thay vì coi các URL minh họa là hợp đồng cố định.

Spring Data REST thường trả về HAL representation. HAL chứa dữ liệu và các hypermedia link như \`self\`, link đến collection, association hoặc search resource. Nhờ đó, client có thể khám phá các thao tác được công bố từ response.

Repository API có các ưu điểm:

- Giảm lượng controller và mapping CRUD phải viết thủ công.
- Tận dụng quy ước của Spring Data và repository abstraction.
- Hỗ trợ pagination, sorting và các search resource được export.
- Có hypermedia link để client khám phá tài nguyên.
- Phù hợp với các resource có thao tác dữ liệu đơn giản, dễ hiểu và ít phụ thuộc vào quy trình nhiều bước.

Ví dụ, một API quản lý danh mục sản phẩm nội bộ có thể chỉ cần đọc danh sách, xem chi tiết, thêm, sửa và xóa Product. Repository API có thể đáp ứng phần lớn nhu cầu đó mà không cần tự viết một controller CRUD riêng.

## 2. Business API tự thiết kế là gì?

Business API mô tả chức năng theo ngôn ngữ của nghiệp vụ. Endpoint thường tương ứng với một hành động, một quy trình hoặc một góc nhìn dữ liệu mà client cần.

Ví dụ với đơn hàng:

~~~http
POST /api/orders
POST /api/orders/1001/confirm
POST /api/orders/1001/cancel
GET  /api/customers/42/order-summary
~~~

Các endpoint này thể hiện ý nghĩa nghiệp vụ:

- Tạo một đơn hàng.
- Xác nhận đơn hàng.
- Hủy đơn hàng theo chính sách.
- Lấy tổng hợp đơn hàng của một khách hàng.

Một thao tác như xác nhận đơn hàng có thể cần kiểm tra trạng thái hiện tại, tồn kho, thanh toán, hạn mức, quyền của người dùng và ghi nhận lịch sử. Đây không còn là thao tác cập nhật một vài field đơn giản. Business API cho phép gom toàn bộ quy trình đó vào một use case rõ ràng.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderCommandsController {

    private final ConfirmOrderService confirmOrderService;

    public OrderCommandsController(
            ConfirmOrderService confirmOrderService) {
        this.confirmOrderService = confirmOrderService;
    }

    @PostMapping("/{id}/confirm")
    public OrderView confirm(@PathVariable Long id) {
        return confirmOrderService.confirm(id);
    }
}
~~~

Application service thực hiện use case:

~~~java
@Service
public class ConfirmOrderService {

    private final OrderRepository orderRepository;

    public ConfirmOrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderView confirm(Long id) {
        Order order = orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

        order.confirm();

        return OrderView.from(order);
    }
}
~~~

Ở đây:

- Controller nhận HTTP request và chuyển giao cho application service.
- Application service điều phối use case trong transaction.
- Domain object giữ quy tắc chuyển trạng thái thông qua \`order.confirm()\`.
- Response DTO \`OrderView\` định nghĩa dữ liệu được trả về cho client.

Ví dụ đã lược bỏ các phần như kiểm tra quyền, kiểm tra tồn kho và xử lý lỗi theo hợp đồng API. Trong ứng dụng thực tế, các bước nghiệp vụ cần được triển khai theo quy tắc của domain.

## 3. So sánh hai cách công bố API

| Tiêu chí | Repository API (Spring Data REST) | Business API tự thiết kế |
|---|---|---|
| Điểm xuất phát | Repository và domain entity | Use case và hợp đồng với client |
| Mục tiêu | Thao tác resource theo CRUD và association | Thực hiện hành vi hoặc quy trình nghiệp vụ |
| Endpoint | Chủ yếu theo quy ước repository | Do ứng dụng thiết kế |
| Request/response | Representation do Spring Data REST tạo, có thể tùy biến bằng projection | DTO và schema do ứng dụng kiểm soát |
| Logic nhiều bước | Không phải điểm mạnh của endpoint CRUD mặc định | Phù hợp để điều phối qua application service |
| Hypermedia | HAL và link được Spring Data REST tạo | Ứng dụng tự thiết kế nếu cần |
| Pagination/search | Có sẵn theo cơ chế repository và query method được export | Ứng dụng tự định nghĩa hoặc tái sử dụng thành phần có sẵn |
| Kiểm soát hợp đồng | Phụ thuộc cấu hình và representation của repository | Kiểm soát rõ theo từng endpoint |
| Chi phí ban đầu | Thấp với CRUD thông thường | Cao hơn vì phải thiết kế và triển khai |
| Phù hợp | CRUD đơn giản, dữ liệu tham chiếu, công cụ nội bộ | Workflow, command, báo cáo tổng hợp, API tích hợp ổn định |

Không nên đánh giá business API tốt hơn trong mọi trường hợp hoặc repository API luôn đơn giản hơn về lâu dài. Lựa chọn đúng phụ thuộc vào ý nghĩa của thao tác, độ ổn định của hợp đồng và mức kiểm soát mà client cần.

## 4. Khi nào nên dùng repository API?

Repository API là lựa chọn hợp lý khi các điều kiện sau phần lớn đúng:

1. Resource có vòng đời và thao tác tương đối đơn giản.
2. Client thực sự cần CRUD trực tiếp trên resource đó.
3. Representation gần với dữ liệu mà API muốn công bố.
4. Không cần điều phối một workflow nhiều bước cho mỗi request.
5. Quyền truy cập và chính sách dữ liệu có thể kiểm soát rõ trên repository resource.
6. Client có thể làm việc với HAL và các quy ước hypermedia của Spring Data REST.

Ví dụ phù hợp:

- Quản lý danh mục quốc gia, tỉnh thành hoặc loại sản phẩm.
- Tra cứu dữ liệu tham chiếu.
- CRUD các đối tượng cấu hình nội bộ.
- API dành cho công cụ quản trị có phạm vi quyền hạn rõ ràng.
- Các resource có association đơn giản và có thể biểu diễn bằng link.

Ngay cả với CRUD, vẫn cần quyết định field nào được phép đọc hoặc ghi, repository nào được export và phương thức tìm kiếm nào được công bố.

### Ví dụ: công bố repository có giới hạn

~~~java
@RepositoryRestResource(
    path = "categories",
    collectionResourceRel = "categories"
)
public interface CategoryRepository
        extends JpaRepository<Category, Long> {

    Optional<Category> findByCode(String code);

    @RestResource(exported = false)
    Optional<Category> findByInternalNote(String internalNote);
}
~~~

Query method \`findByCode\` có thể được công bố thành search resource theo quy ước. Method \`findByInternalNote\` được đánh dấu \`exported = false\` để không tạo endpoint tìm kiếm tương ứng.

Nếu không muốn export cả repository, có thể dùng:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, Long> {
}
~~~

Đây là cách giới hạn bề mặt API ở mức repository. Không nên dựa vào việc client không biết URL để bảo vệ một repository hoặc method nội bộ.

## 5. Khi nào nên thiết kế business API?

Nên dùng endpoint nghiệp vụ riêng khi request thể hiện một hành vi có ý nghĩa vượt ra ngoài việc lưu một entity.

Các dấu hiệu thường gặp:

- Một thao tác cần phối hợp nhiều repository hoặc nhiều aggregate.
- Có điều kiện chuyển trạng thái, ví dụ chỉ được xác nhận đơn hàng khi đã thanh toán.
- Cần gọi dịch vụ bên ngoài hoặc phát sinh side effect.
- Request là một command có ý nghĩa nghiệp vụ, chẳng hạn approve, publish, confirm hoặc cancel.
- Response là dữ liệu tổng hợp từ nhiều nguồn.
- Mỗi nhóm người dùng được phép xem hoặc sửa các trường khác nhau.
- Hợp đồng bên ngoài cần ổn định dù cấu trúc entity bên trong thay đổi.
- Cần versioning, idempotency, audit hoặc error model được thiết kế theo use case.

Ví dụ, nếu client gửi:

~~~http
PATCH /orders/1001
Content-Type: application/json

{
  "status": "CONFIRMED"
}
~~~

thì API đang cho client trực tiếp gán trạng thái. Cách này có thể bỏ qua quy trình xác nhận của domain. Một endpoint rõ nghĩa hơn là:

~~~http
POST /api/orders/1001/confirm
~~~

Server tự kiểm tra đơn hàng có thể xác nhận hay không, thực hiện các bước cần thiết và thay đổi trạng thái thông qua domain behavior.

Không phải mọi field update đều cần một command endpoint. Đổi tên ghi chú hoặc cập nhật một thuộc tính không ảnh hưởng quy tắc nghiệp vụ có thể phù hợp với một resource update thông thường. Hãy dựa vào ý nghĩa của hành động thay vì chỉ dựa vào số lượng dòng code.

## 6. Thiết kế theo hướng kết hợp

Một ứng dụng có thể dùng Spring Data REST cho các thao tác dữ liệu thông thường và business API cho các use case quan trọng.

Ví dụ:

~~~text
Client
  |
  +-- GET /products
  |      |
  |      +--> Spring Data REST
  |               |
  |               +--> ProductRepository
  |
  +-- POST /orders/1001/confirm
         |
         +--> OrderCommandsController
                  |
                  +--> ConfirmOrderService
                           |
                           +--> OrderRepository
                           +--> InventoryService
                           +--> PaymentService
~~~

Trong mô hình này:

- Product collection là resource có thể được quản lý qua repository API.
- Confirm order là use case có nhiều quy tắc, được xử lý bởi business API.
- Cả hai có thể dùng chung repository và domain model.
- Logic nghiệp vụ nên nằm trong domain/application service theo trách nhiệm, không sao chép giữa controller tự viết và endpoint tự sinh.

Một nguyên tắc hữu ích là: **repository là cơ chế truy cập dữ liệu; business API là hợp đồng hành động của hệ thống**. Business service có thể dùng repository, nhưng không nên để client phải hiểu cấu trúc repository để hoàn thành một quy trình nghiệp vụ.

### Tách đường dẫn và quyền sở hữu endpoint

Nếu cùng ứng dụng công bố cả hai loại API, hãy đặt quy ước đường dẫn dễ hiểu. Ví dụ:

- \`/data/products\`: resource CRUD do Spring Data REST công bố.
- \`/api/orders/{id}/confirm\`: endpoint nghiệp vụ do ứng dụng thiết kế.

Đây chỉ là một quy ước minh họa. Cần cấu hình base path và mapping nhất quán trong ứng dụng; \`@RestController\` thông thường và controller tích hợp vào Spring Data REST có quy tắc mapping khác nhau. Không nên để hai controller hoặc repository cùng sở hữu một đường dẫn.

## 7. Tùy biến repository API mà không biến nó thành workflow controller

Spring Data REST có một số điểm mở rộng hữu ích:

- \`@RepositoryRestResource\`: tùy chỉnh path, relation name và việc export repository.
- \`@RestResource\`: tùy chỉnh tên relation/path hoặc tắt export của method/property.
- \`@Projection\`: thay đổi representation theo một tập thuộc tính được công bố.
- \`RepositoryRestConfigurer\`: tùy chỉnh cấu hình Spring Data REST.
- Repository event handler: xử lý một số sự kiện trước hoặc sau thao tác repository.

Các cơ chế này giúp điều chỉnh cách repository được công bố. Chúng không nên trở thành nơi chứa toàn bộ quy trình nghiệp vụ phức tạp.

Ví dụ, projection có thể giúp response chỉ chứa những field mà màn hình danh sách cần. Nhưng projection không tự giải quyết authorization, không thay thế workflow service và không phải ranh giới bảo mật duy nhất. Nếu một request cần nhiều bước, hãy tạo use case riêng và gọi domain/application service.

Repository event handler có thể dùng cho validation hoặc phản ứng gắn với thao tác repository. Nếu logic cần điều phối nhiều bước, cần retry, gọi dịch vụ ngoài, kiểm soát transaction hoặc có kết quả nghiệp vụ rõ ràng, một application service tường minh thường dễ đọc và kiểm thử hơn.

## 8. Không công bố toàn bộ domain model chỉ vì repository tồn tại

Một lỗi thiết kế phổ biến là export mọi repository và xem các endpoint được sinh ra như API công khai mặc định.

Điều này có thể dẫn đến:

- Client truy cập được dữ liệu nội bộ mà không cần thiết.
- Query method vô tình trở thành endpoint tìm kiếm.
- Entity và association nội bộ bị biến thành hợp đồng bên ngoài.
- Thay đổi domain model làm thay đổi representation mà client đang phụ thuộc.
- Client có thể thực hiện thao tác CRUD bỏ qua quy trình nghiệp vụ.
- Khó kiểm soát quyền theo use case hoặc theo từng trường dữ liệu.

Hãy chỉ export repository mà ứng dụng thực sự muốn công bố. Tắt export cho repository, method hoặc association nội bộ nếu không cần. Với dữ liệu nhạy cảm, thiết kế response DTO hoặc projection có kiểm soát và áp dụng authorization ở server.

Các biện pháp như \`@JsonIgnore\`, ẩn link trên UI hoặc đặt URL khó đoán không thay thế được phân quyền. Server cần kiểm tra caller có được phép đọc hoặc thay đổi resource cụ thể hay không.

## 9. DTO và entity trong business API

Repository API thường biểu diễn entity thông qua representation do Spring Data REST tạo. Business API nên xem request/response là hợp đồng riêng của endpoint.

Ví dụ DTO cho yêu cầu tạo đơn hàng:

~~~java
public record CreateOrderRequest(
    Long customerId,
    List<CreateOrderLineRequest> lines
) {
}

public record CreateOrderLineRequest(
    Long productId,
    int quantity
) {
}

public record OrderView(
    Long id,
    String orderNumber,
    String status,
    BigDecimal total
) {
}
~~~

Client gửi thông tin cần thiết để tạo đơn hàng. Server chịu trách nhiệm:

- Kiểm tra customer và product có tồn tại.
- Kiểm tra số lượng hợp lệ và quy tắc tồn kho.
- Tính giá theo chính sách của hệ thống.
- Tạo entity và lưu qua repository.
- Trả về OrderView theo hợp đồng API.

Client không cần gửi một entity Order hoàn chỉnh với các field nội bộ như tổng tiền do server tính, trạng thái đã xác nhận hoặc audit timestamp.

DTO giúp ứng dụng giữ quyền kiểm soát hợp đồng ngay cả khi entity thay đổi. Nó cũng cho phép mỗi use case nhận và trả về đúng dữ liệu cần thiết.

## 10. Bảo mật và phân quyền

Dù sử dụng repository API hay business API, bảo mật vẫn phải được thực hiện phía server.

Với repository API:

- Chỉ export repository cần thiết.
- Tắt các query method không được phép công bố.
- Cấu hình authorization cho collection, item, search và association.
- Kiểm tra quyền trên từng resource, không chỉ kiểm tra người dùng đã đăng nhập.
- Không công bố field nhạy cảm qua entity, projection hoặc association lồng.
- Xem xét các thao tác write có thể làm thay đổi domain state.

Với business API:

- Phân quyền theo use case và resource cụ thể.
- Validate dữ liệu đầu vào.
- Không tin các giá trị nhạy cảm do client tự gửi như ownerId, price, status hoặc role.
- Xử lý lỗi theo hợp đồng ổn định, không trả stack trace hoặc thông tin nội bộ.
- Dùng transaction cho các thao tác cần tính nhất quán.
- Xem xét idempotency cho các command có thể được client gửi lại.

Nếu ứng dụng dùng Spring Security, có thể kết hợp request authorization với method-level authorization như \`@PreAuthorize\`. Chính sách cụ thể phải phản ánh vai trò và quy tắc truy cập của domain.

## 11. Kiểm thử hai loại API

Repository API cần kiểm tra những gì thực sự được export:

- Root và collection có các link mong muốn.
- Item và association trả về đúng relation.
- Query method được công bố đúng tên và tham số.
- Repository/method nội bộ không xuất hiện.
- Pagination, sorting và projection hoạt động theo hợp đồng.
- Caller không có quyền không thể đọc hoặc ghi resource.

Business API cần kiểm tra hành vi use case:

- Request hợp lệ tạo đúng kết quả.
- Request sai trạng thái bị từ chối.
- Caller thiếu quyền không thể thực hiện command.
- Transaction rollback khi một bước quan trọng thất bại.
- Response DTO không chứa field nội bộ.
- Error response giữ đúng status và cấu trúc đã công bố.

Nên có integration test ở ranh giới HTTP để xác nhận routing, serialization, security và persistence cùng hoạt động. Unit test cho application service giúp kiểm tra quy tắc nghiệp vụ mà không phụ thuộc HTTP.

## 12. Quy trình ra quyết định

Có thể dùng các câu hỏi sau khi chọn loại API:

1. Client chỉ cần đọc hoặc sửa dữ liệu resource theo CRUD đơn giản? Nếu có, xem xét repository API.
2. Request có tên hành động nghiệp vụ như approve, confirm, cancel, publish hoặc settle? Nếu có, thường nên dùng business API.
3. Một request phải phối hợp nhiều aggregate hoặc dịch vụ? Dùng application service và endpoint nghiệp vụ.
4. Response cần tổng hợp hoặc tùy biến mạnh theo một use case? Dùng DTO và business API.
5. Resource chỉ phục vụ nội bộ hoặc chứa dữ liệu nhạy cảm? Giới hạn export và authorization; cân nhắc endpoint riêng với contract được kiểm soát.
6. Client cần khám phá resource theo HAL và thao tác repository? Spring Data REST là lựa chọn phù hợp.

Nếu câu trả lời nằm giữa hai nhóm, có thể kết hợp. Ví dụ, collection GET dùng Spring Data REST nhưng lệnh publish dùng endpoint nghiệp vụ riêng.

## 13. Ví dụ phân loại chức năng

| Chức năng | Hướng thiết kế thường phù hợp | Lý do |
|---|---|---|
| Xem danh sách Category | Repository API | CRUD/đọc đơn giản |
| Xem chi tiết Product | Repository API hoặc DTO GET | Phụ thuộc representation và quyền |
| Tìm Product theo code | Repository search hoặc business query | Chọn theo độ ổn định và ngữ nghĩa truy vấn |
| Tạo Order từ giỏ hàng | Business API | Cần kiểm tra nhiều dữ liệu và quy tắc |
| Xác nhận thanh toán | Business API | Là command có side effect và kiểm soát trạng thái |
| Hủy Order | Business API | Có điều kiện, chính sách và hoàn tác |
| Đổi tên một nhãn nội bộ | Repository API nếu CRUD đơn giản | Không cần workflow riêng |
| Báo cáo doanh thu theo kỳ | Business API | Dữ liệu tổng hợp và hợp đồng riêng |
| Quản lý dữ liệu tham chiếu | Repository API có giới hạn | Resource độc lập, ít quy trình |
| Quản trị quyền người dùng | Business API hoặc API quản trị chuyên biệt | Yêu cầu phân quyền và audit chặt chẽ |

Đây là hướng lựa chọn ban đầu. Domain cụ thể có thể thay đổi quyết định nếu một thao tác tưởng như CRUD lại mang ý nghĩa nghiệp vụ hoặc yêu cầu bảo mật đặc biệt.

## 14. Kết luận

Spring Data REST giúp công bố repository thành REST resource nhanh chóng, có quy ước và hypermedia. Nó phù hợp với các thao tác dữ liệu đơn giản mà ứng dụng chủ động muốn export. Business API tự thiết kế phù hợp với use case, workflow, command, báo cáo và hợp đồng cần kiểm soát rõ ràng.

Một hệ thống có thể dùng cả hai. Hãy để repository API phục vụ những thao tác resource phù hợp, để business API diễn đạt hành vi của hệ thống và để application/domain service giữ các quy tắc nghiệp vụ. Chỉ công bố repository, method và dữ liệu mà client thực sự cần; luôn kiểm tra quyền truy cập ở phía server.

## Tài liệu tham khảo

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): cách Spring Data REST công bố collection, item, association và search resources.
- [Spring Data REST Reference — Exposing repository resources](https://docs.spring.io/spring-data/rest/reference/exposure.html): kiểm soát repository và method được export.
- [Spring Data REST Reference — Configuring the REST URL path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html): tùy chỉnh đường dẫn và cấu hình REST API.
- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html): các event handler trong vòng đời thao tác repository.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): cơ chế xác thực và phân quyền ở phía server.
