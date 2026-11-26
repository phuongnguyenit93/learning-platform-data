# Lộ trình học thư viện Spring HATEOAS

Spring HATEOAS là thư viện giúp ứng dụng Spring tạo và xuất bản biểu diễn tài nguyên có hypermedia. Thư viện cung cấp mô hình tài nguyên, kiểu liên kết, công cụ dựng URI từ controller, assembler để chuyển đổi dữ liệu thành representation và hỗ trợ các định dạng như HAL. Khi học theo đúng thứ tự, bạn có thể đi từ một endpoint trả JSON đơn giản đến API mà client khám phá được tài nguyên và bước tiếp theo thông qua các liên kết.

Lộ trình này đi theo một dự án xuyên suốt: API quản lý đơn hàng. Ta sẽ xây dựng representation cho một đơn hàng, thêm liên kết theo trạng thái, xuất dữ liệu bằng HAL, rồi kiểm thử cách client điều hướng. Mục tiêu không phải ghi nhớ mọi lớp trong thư viện, mà hiểu mỗi thành phần giải quyết phần nào của bài toán và biết chọn chúng khi xây dựng API thực tế.

## 1. Chuẩn bị kiến thức và môi trường

Trước khi thêm Spring HATEOAS, bạn nên quen với những nội dung sau:

- **HTTP và REST:** request method, status code, header, URI, tài nguyên và biểu diễn tài nguyên.
- **Spring Boot và Spring MVC:** `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PathVariable`, dependency injection và cách controller trả response.
- **Java và mô hình dữ liệu:** class, interface, generic, DTO, collection và cách tách domain model khỏi dữ liệu công khai của API.
- **JSON và Jackson:** cách object Java được tuần tự hóa thành JSON, tên thuộc tính và cấu trúc dữ liệu lồng nhau.
- **Kiểm thử HTTP:** đọc status code, content type, response body và kiểm tra JSON bằng MockMvc hoặc công cụ tương đương.

Bạn cũng nên biết một API có thể trả nhiều media type. `application/json` thường biểu diễn dữ liệu thuần; `application/hal+json` là media type HAL, trong đó liên kết được biểu diễn theo quy ước hypermedia.

### Thêm thư viện vào dự án

Nếu dự án dùng Spring Boot, có thể thêm starter HATEOAS và để dependency management của Spring Boot quản lý phiên bản tương thích:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-hateoas")
}
```

Với Maven, khai báo dependency `org.springframework.boot:spring-boot-starter-hateoas` trong `pom.xml`. Nếu không dùng Spring Boot, có thể khai báo trực tiếp `org.springframework.hateoas:spring-hateoas` và tự bảo đảm phiên bản tương thích với nền tảng Spring đang dùng.

Sau khi thêm dependency, chạy ứng dụng và gọi một endpoint hiện có. Xác nhận dự án khởi động bình thường trước khi thay đổi cấu trúc response. Trong ứng dụng Spring Boot, cấu hình hypermedia thường được tự động thiết lập bởi auto-configuration tương ứng; nếu dùng cấu hình Spring MVC thủ công, hãy tìm hiểu `@EnableHypermediaSupport` và loại hypermedia cần bật.

## 2. Học mô hình tài nguyên trước khi học cách dựng link

Đây là nhóm kiểu dữ liệu cốt lõi của Spring HATEOAS:

| Kiểu | Vai trò | Khi nên dùng |
| --- | --- | --- |
| `RepresentationModel<T>` | Lớp cơ sở cho representation có thể chứa các liên kết. | Khi muốn tạo kiểu representation riêng và kiểm soát cấu trúc dữ liệu. |
| `EntityModel<T>` | Bọc một đối tượng dữ liệu cùng các liên kết. | Khi một tài nguyên có DTO hoặc view model riêng. |
| `CollectionModel<T>` | Biểu diễn một tập hợp các model, có thể kèm liên kết ở cấp collection. | Khi trả danh sách tài nguyên. |
| `PagedModel<T>` | Biểu diễn kết quả phân trang cùng thông tin và liên kết điều hướng trang. | Khi endpoint trả dữ liệu theo trang. |
| `Link` | Mô tả một liên kết có URI và quan hệ. | Khi thêm liên kết `self`, `next` hoặc quan hệ nghiệp vụ. |

Không nên xem các kiểu này là entity của cơ sở dữ liệu. Domain entity mô tả dữ liệu và quy tắc nghiệp vụ bên trong ứng dụng; representation model mô tả nội dung mà API muốn công bố cho client. Một DTO có thể được bọc bằng `EntityModel` mà không làm lộ các trường nội bộ của entity.

Ví dụ, DTO của đơn hàng có thể chỉ công bố mã đơn, trạng thái và tổng tiền:

```java
public record OrderView(UUID id, String status, BigDecimal total) {}
```

Để bắt đầu, hãy tạo `EntityModel<OrderView>` từ DTO:

```java
OrderView view = new OrderView(order.getId(), order.getStatus().name(), order.getTotal());
EntityModel<OrderView> model = EntityModel.of(view);
```

Ở thời điểm này, model đã bọc dữ liệu nhưng chưa có liên kết. Bước tiếp theo sẽ bổ sung liên kết để client có thể khám phá tài nguyên.

## 3. Nắm vững Link và quan hệ (relation)

Một liên kết trong hypermedia có hai thành phần quan trọng:

- **URI đích (`href`):** nơi client có thể điều hướng hoặc gửi request tiếp theo.
- **Quan hệ (`rel`):** ý nghĩa của liên kết đối với tài nguyên hiện tại.

`self` thường chỉ chính tài nguyên đang được biểu diễn. `next` và `prev` thường dùng cho điều hướng phân trang. Quan hệ nghiệp vụ như `cancel`, `approve` hoặc `shipment` cần được nhóm API định nghĩa và duy trì ý nghĩa nhất quán.

Spring HATEOAS biểu diễn liên kết bằng `Link`. Bạn có thể thêm liên kết vào model bằng `add`:

```java
model.add(Link.of("/orders/42", "self"));
model.add(Link.of("/orders/42/cancel", "cancel"));
```

Đây là ví dụ minh họa cấu trúc. Trong controller Spring MVC, nên ưu tiên dựng URI từ mapping của controller thay vì nối chuỗi đường dẫn bằng tay. Điều này giảm nguy cơ URI bị sai khi đổi mapping hoặc thêm tham số.

Khi dùng relation, hãy phân biệt quan hệ chuẩn và quan hệ riêng. Spring HATEOAS có `IanaLinkRelations` cho các quan hệ chuẩn được thư viện hỗ trợ, chẳng hạn `SELF` và `NEXT`. Với quan hệ riêng, thống nhất tên, định nghĩa ý nghĩa và ghi vào tài liệu hợp đồng API. Client cần biết relation nào nó phải tìm và hành vi tương ứng với relation đó.

## 4. Dựng URI từ controller với WebMvcLinkBuilder

`WebMvcLinkBuilder` cung cấp các hàm giúp tạo liên kết dựa trên mapping của Spring MVC. Hai hàm thường dùng là:

- `linkTo(...)`: xác định đường dẫn từ controller hoặc method.
- `methodOn(...)`: tạo tham chiếu method để Spring HATEOAS suy ra mapping mà không cần gọi method controller thật.

Ví dụ, controller có endpoint đọc đơn hàng theo mã:

```java
@GetMapping("/{id}")
EntityModel<OrderView> one(@PathVariable UUID id) {
    // Lấy đơn hàng và tạo representation.
}
```

Liên kết `self` có thể được tạo như sau:

```java
Link self = linkTo(methodOn(OrderController.class).one(id)).withSelfRel();
model.add(self);
```

Một liên kết nghiệp vụ có thể được tạo bằng `withRel`:

```java
Link cancel = linkTo(methodOn(OrderController.class).cancel(id)).withRel("cancel");
model.add(cancel);
```

Các ví dụ trên giả định `id` là giá trị cần truyền vào method controller. `methodOn` chỉ hỗ trợ Spring HATEOAS phân tích mapping; không dùng nó để thực thi nghiệp vụ. Với ứng dụng đặt sau reverse proxy hoặc có context path, cần cấu hình và kiểm thử cách ứng dụng nhận diện thông tin request bên ngoài để URI được tạo ra đúng với địa chỉ client có thể truy cập.

Thực hành ở giai đoạn này:

1. Tạo liên kết `self` cho endpoint chi tiết đơn hàng.
2. Tạo liên kết quay về collection đơn hàng.
3. Tạo liên kết tới một tài nguyên liên quan, ví dụ khách hàng của đơn hàng.
4. Đổi mapping của controller và xác nhận liên kết vẫn phản ánh mapping mới.

## 5. Tổ chức chuyển đổi bằng RepresentationModelAssembler

Nếu mỗi controller tự chuyển entity thành DTO rồi thêm nhiều liên kết, logic tạo representation dễ bị lặp. `RepresentationModelAssembler<T, D>` cung cấp một điểm mở rộng để chuyển một domain object thành representation model. Interface có phương thức `toModel` và hỗ trợ tạo collection model từ nhiều entity.

Ví dụ assembler cho đơn hàng:

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        UUID id = order.getId();
        OrderView view = new OrderView(
                id,
                order.getStatus().name(),
                order.getTotal()
        );

        EntityModel<OrderView> model = EntityModel.of(
                view,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel("cancel"));
        }

        return model;
    }
}
```

Đây là ví dụ minh họa; các kiểu `Order`, `OrderView`, `OrderController` và quy tắc `canBeCancelled()` thuộc ứng dụng. Assembler chịu trách nhiệm tạo representation và các liên kết được công bố. Quyết định một đơn hàng có được phép hủy hay không vẫn nên xuất phát từ quy tắc nghiệp vụ của domain hoặc service.

Controller sau đó tập trung vào nhận request, gọi service và trả representation:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        return assembler.toCollectionModel(service.findAll());
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        return assembler.toModel(service.getRequired(id));
    }

    @PostMapping("/{id}/cancel")
    ResponseEntity<Void> cancel(@PathVariable UUID id) {
        service.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
```

Khi học assembler, hãy chú ý kiểu generic đầu vào và đầu ra. `Order` là đối tượng domain; `EntityModel<OrderView>` là representation được trả về. Cách tách này giúp thay đổi cấu trúc API mà ít ảnh hưởng tới mô hình lưu trữ và logic nghiệp vụ.

## 6. Tổ chức collection, tài nguyên nhúng và quan hệ

Sau khi làm được tài nguyên đơn, hãy học cách biểu diễn collection và quan hệ giữa các tài nguyên.

- Dùng `CollectionModel` để trả danh sách model. Collection có thể có liên kết ở cấp danh sách như `self`, `next` hoặc liên kết tạo mới nếu hợp đồng API công bố khả năng đó.
- Dùng tài nguyên nhúng khi client thường cần một đối tượng liên quan ngay trong representation hiện tại. Cần cân nhắc kích thước response và mức độ phụ thuộc giữa các tài nguyên.
- Dùng liên kết giữa các tài nguyên khi muốn client điều hướng từ đơn hàng tới khách hàng, mặt hàng hoặc thông tin giao hàng.
- Xác định tên relation cho từng loại tài nguyên và collection. Có thể dùng `@Relation` để tùy chỉnh tên relation khi cần kiểm soát cách tên tài nguyên được biểu diễn trong HAL.

Không phải quan hệ nào trong mô hình dữ liệu cũng nên trở thành dữ liệu nhúng. Hãy dựa trên hành vi client: nếu client cần điều hướng độc lập hoặc dữ liệu có vòng đời riêng, liên kết thường phù hợp; nếu dữ liệu nhỏ, luôn cần cùng tài nguyên cha và ít thay đổi độc lập, nhúng có thể thuận tiện hơn.

Khi chuyển sang dữ liệu phân trang, hãy tìm hiểu `PagedModel` và cách tích hợp với Spring Data. Mục tiêu là để client nhận được thông tin trang hiện tại, tổng số phần tử khi có thể cung cấp, cùng các liên kết điều hướng như `first`, `prev`, `self`, `next` và `last` phù hợp với kết quả. Đừng tự ghép query string phân trang trong nhiều controller; dùng cơ chế phân trang nhất quán và kiểm thử các liên kết được sinh ra.

## 7. Xuất representation bằng HAL

HAL (Hypertext Application Language) là một định dạng biểu diễn hypermedia phổ biến. Trong HAL JSON, liên kết thường nằm dưới `_links`; tài nguyên nhúng nằm dưới `_embedded`. Một response đơn hàng có thể trông như sau:

```json
{
  "id": "42",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "cancel": {
      "href": "/orders/42/cancel"
    }
  }
}
```

Đây là cấu trúc minh họa. Khi controller trả về `EntityModel` hoặc `CollectionModel`, bộ chuyển đổi hypermedia của Spring HATEOAS đảm nhiệm việc tuần tự hóa theo media type đã cấu hình. Client có thể yêu cầu HAL bằng header `Accept: application/hal+json`.

Hãy kiểm tra cả header và body. Một response có JSON hợp lệ chưa đủ để kết luận HAL đã hoạt động đúng: cần xác nhận content type tương thích với HAL và các liên kết được xuất ra theo cấu trúc `_links`. Với collection, kiểm tra cả tên relation của collection và các tài nguyên nhúng nếu API có dùng `_embedded`.

Sau khi nắm HAL cơ bản, có thể học thêm:

- **HAL-FORMS:** mở rộng biểu diễn để mô tả biểu mẫu và các thao tác mà client có thể thực hiện.
- **Affordances:** mô tả các khả năng tương tác gắn với một liên kết, chẳng hạn thông tin về thao tác cập nhật.
- **Media type và profile:** công bố quy ước biểu diễn để client hiểu cấu trúc và ngữ nghĩa của API.

Đây là phần nâng cao. Trước khi học, cần hiểu rõ `Link`, relation, `EntityModel` và HAL cơ bản. Không phải client nào cũng hỗ trợ HAL-FORMS hoặc affordance; hãy chọn định dạng theo khả năng của client và hợp đồng mà hệ thống cần công bố.

## 8. Tích hợp với controller và luồng xử lý nghiệp vụ

Một controller HATEOAS thường thực hiện ba việc: nhận request, gọi lớp nghiệp vụ và trả representation. Việc tạo liên kết có thể nằm trong assembler hoặc một thành phần chuyên trách để nhiều endpoint dùng chung quy tắc.

Với liên kết phụ thuộc trạng thái, quy trình nên diễn ra như sau:

1. Controller nhận request đọc tài nguyên.
2. Service tải tài nguyên và áp dụng quy tắc nghiệp vụ cần thiết.
3. Assembler chuyển dữ liệu thành model và thêm những liên kết phù hợp với trạng thái hiện tại.
4. Spring HATEOAS tuần tự hóa model theo media type được chọn.
5. Client đọc relation và quyết định bước tiếp theo.

Ví dụ, đơn hàng `PENDING` có thể được công bố liên kết `cancel`; đơn hàng `SHIPPED` thì không. Việc không xuất liên kết giúp client biết thao tác hủy hiện không được công bố. Tuy nhiên endpoint `POST /orders/{id}/cancel` vẫn phải kiểm tra quyền và trạng thái khi request đến, vì trạng thái có thể đổi sau lúc client đọc representation.

Nếu ứng dụng dùng Spring Data REST, hãy học phần tích hợp riêng sau khi đã hiểu cách controller và assembler hoạt động. Spring Data REST có cơ chế xuất bản repository và liên kết riêng; không nên nhầm nó với việc tự thiết kế controller bằng Spring HATEOAS.

## 9. Kiểm thử representation và khả năng điều hướng

Kiểm thử HATEOAS cần xác nhận nhiều hơn status code. Với Spring MVC, MockMvc có thể gửi request và kiểm tra response. Ví dụ dưới đây minh họa kiểm tra media type, liên kết `self` và liên kết `cancel`:

```java
mockMvc.perform(get("/orders/{id}", id)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel.href").exists());
```

Với một đơn hàng không thể hủy, hãy kiểm tra relation `cancel` không xuất hiện:

```java
mockMvc.perform(get("/orders/{id}", shippedOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
```

Tên field và cấu trúc nhúng có thể thay đổi theo cấu hình relation của ứng dụng, vì vậy hãy viết assertion dựa trên hợp đồng đã chọn. Tránh phụ thuộc vào thứ tự các liên kết trong JSON.

Một bộ kiểm thử hữu ích nên bao gồm:

- Liên kết `self` trỏ tới đúng tài nguyên.
- Các relation nghiệp vụ xuất hiện khi điều kiện cho phép và biến mất khi điều kiện không còn đúng.
- Collection có liên kết điều hướng và phân trang chính xác.
- Response trả đúng media type khi client gửi `Accept` tương ứng.
- Endpoint thao tác vẫn từ chối request không có quyền hoặc trạng thái không hợp lệ, kể cả khi client tự gửi request mà không dựa vào liên kết.
- Client mẫu có thể bắt đầu từ URI gốc, đọc relation và đi theo `href` mà không tự ghép URI chi tiết.

Với ứng dụng WebFlux, tìm hiểu cách kiểm thử bằng `WebTestClient` và các tích hợp hypermedia tương ứng. Chọn công cụ kiểm thử phù hợp với stack web thực tế của dự án.

## 10. Kiểm thử khả năng tiến hóa hợp đồng API

Một mục tiêu quan trọng của HATEOAS là giảm sự phụ thuộc của client vào URI cụ thể. Để kiểm chứng mục tiêu này, hãy tạo một bài kiểm thử client nhỏ: client bắt đầu từ một entry point đã biết, đọc liên kết `orders` hoặc `self`, rồi tiếp tục theo relation nhận được. Khi đổi mapping đích của một endpoint, client vẫn hoạt động nếu relation và ý nghĩa hợp đồng được giữ ổn định.

Tuy nhiên, hypermedia không tự làm mọi thay đổi trở nên tương thích. Các yếu tố sau vẫn là một phần của hợp đồng:

- Tên và ý nghĩa của relation.
- Media type và cấu trúc representation.
- Tên, kiểu và ý nghĩa của các trường dữ liệu.
- Cách thực hiện thao tác, điều kiện tiền đề và lỗi có thể trả về.

Khi thay đổi API, cần xác định client đang phụ thuộc vào relation, field và media type nào. Nếu đổi relation, hãy có kế hoạch chuyển tiếp hoặc công bố quan hệ mới. Nếu thay đổi schema dữ liệu, kiểm tra client đang dùng trường đó. Kiểm thử hợp đồng nên tập trung vào khả năng client khám phá và hiểu đúng các bước, không chỉ so sánh nguyên văn toàn bộ JSON.

## 11. Dự án thực hành theo từng chặng

Hãy hoàn thiện một API quản lý đơn hàng qua các chặng sau. Mỗi chặng tạo ra một kết quả có thể chạy và kiểm thử trước khi chuyển tiếp.

| Chặng | Việc cần làm | Kết quả cần đạt |
| --- | --- | --- |
| 1. Khởi tạo | Thêm dependency, chạy ứng dụng và xác nhận cấu hình hypermedia. | Dự án khởi động ổn định. |
| 2. Model | Tạo DTO và bọc bằng `EntityModel`. | Endpoint chi tiết trả representation có dữ liệu đơn hàng. |
| 3. Link | Thêm `self`, liên kết collection và liên kết tới tài nguyên liên quan bằng `WebMvcLinkBuilder`. | URI được tạo từ mapping của controller. |
| 4. Assembler | Tách logic chuyển entity thành model vào `RepresentationModelAssembler`. | Controller gọn và nhiều endpoint dùng chung cách tạo representation. |
| 5. Trạng thái | Chỉ công bố `cancel` khi đơn hàng có thể hủy. | Liên kết phản ánh trạng thái nghiệp vụ. |
| 6. HAL | Trả response theo `application/hal+json`; kiểm tra `_links` và `_embedded` nếu có. | Client đọc được cấu trúc HAL. |
| 7. Collection và phân trang | Trả danh sách, thêm liên kết điều hướng trang. | Client duyệt collection mà không tự ghép query string. |
| 8. Kiểm thử | Viết kiểm thử cho relation, media type, trạng thái và quyền. | Các hành vi quan trọng có kiểm thử tự động. |
| 9. Tiến hóa | Đổi URI một endpoint và cập nhật client mẫu để duyệt link. | Client vẫn hoạt động khi relation và hợp đồng được giữ ổn định. |

Khi hoàn thành dự án, hãy thử thêm một luồng phê duyệt. Đơn hàng có thể được duyệt khi ở trạng thái chờ duyệt; representation chỉ công bố relation `approve` khi phù hợp. Bổ sung kiểm thử cho cả trường hợp thành công, trạng thái không hợp lệ và người dùng không đủ quyền.

## 12. Kế hoạch ôn tập và tiêu chí hoàn thành

Có thể chia việc học thành các buổi ngắn, mỗi buổi tập trung vào một năng lực:

1. Buổi đầu: cài đặt thư viện, hiểu media type và các model cơ bản.
2. Buổi hai: tạo `Link`, relation và URI bằng `WebMvcLinkBuilder`.
3. Buổi ba: xây assembler, collection và quan hệ giữa tài nguyên.
4. Buổi bốn: cấu hình HAL, tài nguyên nhúng và phân trang.
5. Buổi năm: tích hợp controller, liên kết theo trạng thái và kiểm thử.
6. Buổi sáu: kiểm thử client traversal, affordance và khả năng tiến hóa hợp đồng.

Bạn đã nắm được nền tảng Spring HATEOAS khi có thể tự thực hiện các việc sau:

- Giải thích vai trò của `RepresentationModel`, `EntityModel`, `CollectionModel` và `Link`.
- Chuyển một domain object thành representation mà không để lộ cấu trúc lưu trữ nội bộ.
- Tạo liên kết từ mapping controller và giải thích ý nghĩa của relation.
- Tổ chức logic tạo representation bằng assembler.
- Xuất và đọc response HAL, bao gồm liên kết và tài nguyên nhúng khi cần.
- Công bố liên kết theo trạng thái nghiệp vụ, đồng thời bảo vệ endpoint ở phía server.
- Kiểm thử media type, URI, relation và khả năng client đi theo liên kết.
- Đánh giá tác động của thay đổi relation, media type và dữ liệu đối với client.

Sau khi hoàn thành các năng lực này, hãy chọn một phần nâng cao theo nhu cầu dự án: HAL-FORMS và affordance cho client cần mô tả thao tác; tích hợp Spring Data REST cho ứng dụng xuất bản repository; hoặc các kiểu liên kết, URI template, pagination và relation tùy chỉnh cho API lớn. Học theo nhu cầu giúp bạn hiểu sâu phần thư viện đang sử dụng và giữ được một lộ trình có thể áp dụng vào sản phẩm thực tế.
