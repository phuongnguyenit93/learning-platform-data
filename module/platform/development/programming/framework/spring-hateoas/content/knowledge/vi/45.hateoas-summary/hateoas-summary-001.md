# Bản đồ khái niệm Spring HATEOAS

## Mục tiêu tổng kết

Bài học này kết nối các khái niệm chính của Spring HATEOAS thành một bản đồ chung. Sau khi hoàn thành, bạn có thể giải thích một response hypermedia được tạo ra như thế nào, lựa chọn đúng kiểu representation, tổ chức link và relation, công bố affordance, hỗ trợ HAL, cũng như kiểm thử và tiến hóa hợp đồng REST API.

Spring HATEOAS hỗ trợ xây dựng REST API trong đó response không chỉ chứa dữ liệu mà còn mô tả các khả năng điều hướng tiếp theo. Server tạo các link gắn với tài nguyên và hành động; client khám phá link rồi sử dụng URI được cung cấp để tiếp tục tương tác.

## 1. Bản đồ tổng thể

Các thành phần của Spring HATEOAS liên kết với nhau theo luồng sau:

~~~mermaid
flowchart TD
    A[Domain model hoặc DTO] --> B[Controller và service]
    B --> C[Representation assembler]
    C --> D[RepresentationModel]
    D --> E[EntityModel / CollectionModel / PagedModel]
    E --> F[Links và relations]
    E --> G[Affordances nếu cần]
    F --> H[Hypermedia serialization]
    G --> H
    H --> I[HAL JSON hoặc media type phù hợp]
    I --> J[HTTP response]
    J --> K[Client khám phá relation]
    K --> L[Theo href hoặc mở rộng URI template]
    L --> B
~~~

Có thể đọc sơ đồ theo bốn lớp:

1. **Dữ liệu và nghiệp vụ:** domain model, DTO, repository và service cung cấp dữ liệu cần thiết.
2. **Representation:** controller và assembler chuyển dữ liệu thành mô hình phản hồi có cấu trúc.
3. **Hypermedia:** link, relation và affordance mô tả đích đến và hành động khả dụng.
4. **Trao đổi với client:** serializer chuyển representation thành HAL hoặc định dạng hypermedia được cấu hình; client khám phá và theo link.

Spring HATEOAS tập trung vào hai lớp representation và hypermedia, đồng thời tích hợp với Spring MVC, Spring Data và Jackson để hoàn thiện luồng HTTP.

## 2. Representation: dữ liệu được đóng gói như thế nào?

Representation là cách server trình bày một tài nguyên cho client. Nó có thể chứa dữ liệu của tài nguyên, link và metadata điều hướng.

Các kiểu model thường dùng:

| Kiểu | Vai trò | Khi sử dụng |
|---|---|---|
| `RepresentationModel<T>` | Lớp cơ sở hỗ trợ gắn link | Khi cần tạo kiểu representation riêng |
| `EntityModel<T>` | Bọc một đối tượng dữ liệu và các link | Response chi tiết của một tài nguyên |
| `CollectionModel<T>` | Biểu diễn một tập hợp các model | Danh sách tài nguyên không cần metadata phân trang chuẩn |
| `PagedModel<T>` | Biểu diễn collection có thông tin trang và link điều hướng | Danh sách lấy từ Spring Data `Page` |

Ví dụ, một đơn hàng có thể được đóng gói thành `EntityModel<Order>`:

~~~java
EntityModel<Order> model = EntityModel.of(
    order,
    selfLink,
    customerLink
);
~~~

Đối tượng `Order` là dữ liệu nghiệp vụ. `EntityModel` thêm khả năng đính kèm link mà không buộc domain model phải kế thừa lớp của Spring HATEOAS.

Nếu API trả về nhiều đơn hàng, có thể dùng `CollectionModel`:

~~~java
CollectionModel<EntityModel<Order>> model =
    CollectionModel.of(orderModels, catalogLink);
~~~

Nếu danh sách có phân trang, `PagedModel` bổ sung thông tin như số trang, kích thước trang và tổng số phần tử. Hãy chọn kiểu model theo hình dạng response mà client cần.

Một nguyên tắc tổ chức hữu ích là giữ domain model độc lập với chi tiết HTTP. Controller hoặc assembler tạo representation ở ranh giới API; service vẫn tập trung vào nghiệp vụ.

## 3. Link và relation: client biết đi đâu tiếp theo

Một hypermedia link có hai phần cốt lõi:

- **Href:** URI đích mà client có thể truy cập.
- **Relation (rel):** tên mô tả mối quan hệ giữa tài nguyên hiện tại và đích đến.

Ví dụ, representation của đơn hàng có thể chứa:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/api/orders/42"
    },
    "customer": {
      "href": "https://api.example.test/api/customers/7"
    }
  }
}
~~~

`self` trỏ đến chính đơn hàng. `customer` trỏ đến khách hàng liên quan. Client sử dụng relation để tìm đúng link, sau đó theo href.

### 3.1. Relation chuẩn và relation mở rộng

Với relation đã được IANA đăng ký, Spring HATEOAS cung cấp các hằng trong `IanaLinkRelations`, ví dụ:

~~~java
linkTo(methodOn(OrderController.class).one(order.id()))
    .withSelfRel();

linkTo(methodOn(OrderController.class).search(null))
    .withRel(IanaLinkRelations.SEARCH);
~~~

Với quan hệ riêng của miền nghiệp vụ, có thể định nghĩa relation mở rộng bằng URI ổn định:

~~~java
private static final LinkRelation CUSTOMER =
    LinkRelation.of("https://api.example.com/rels/customer");
~~~

URI relation tạo định danh rõ ràng và giúp tránh xung đột với relation của hệ thống khác. Tổ chức nên duy trì ý nghĩa relation ổn định và công bố tài liệu mô tả cách sử dụng.

Tên relation là một phần của hợp đồng API. Không nên đổi ý nghĩa relation chỉ vì class hoặc method nội bộ được refactor.

### 3.2. Tạo link từ mapping của controller

`WebMvcLinkBuilder` cung cấp `linkTo` và `methodOn` để tạo URI từ mapping Spring MVC:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(order.id())
).withSelfRel();
~~~

`methodOn` ghi nhận phương thức và đối số trên proxy. Spring HATEOAS dùng thông tin mapping để xây URI tương ứng; phương thức controller không được thực thi như một request thật trong lúc tạo link.

Cách tạo link từ mapping giúp đường dẫn phản ánh cấu hình controller, kể cả khi có path variable. Với URL phụ thuộc request, host hoặc proxy, cần kiểm tra cấu hình forwarded headers và cách ứng dụng tạo base URI để href được công bố chính xác.

### 3.3. URI template

Một số link cần client cung cấp tham số, chẳng hạn từ khóa tìm kiếm hoặc số trang. URI template biểu diễn những biến đó:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/api/orders/search{?q,page,size}",
      "templated": true
    }
  }
}
~~~

`templated: true` cho biết href chứa biến cần được mở rộng. Client sử dụng URI template processor để điền giá trị và mã hóa tham số đúng quy tắc.

Với controller, hãy khai báo tên tham số công khai tường minh bằng annotation như `@RequestParam("q")`. Việc đổi tên query parameter có thể làm thay đổi hợp đồng mà client sử dụng.

## 4. Assembler: tập trung cách tạo representation

Khi một tài nguyên cần nhiều link hoặc được trả về ở nhiều endpoint, assembler giúp gom quy tắc chuyển đổi vào một nơi.

Ví dụ:

~~~java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        Link self = linkTo(
            methodOn(OrderController.class).one(order.id())
        ).withSelfRel();

        Link customer = linkTo(
            methodOn(CustomerController.class).one(order.customerId())
        ).withRel(OrderRelations.CUSTOMER);

        return EntityModel.of(order, self, customer);
    }
}
~~~

Controller chỉ cần gọi assembler:

~~~java
@GetMapping("/{id}")
EntityModel<Order> one(@PathVariable UUID id) {
    return assembler.toModel(orderService.findById(id));
}
~~~

Với collection, `RepresentationModelAssembler` có thể chuyển từng phần tử thành model thông qua `toCollectionModel`. Với dữ liệu phân trang từ Spring Data, `PagedResourcesAssembler` có thể chuyển `Page<Order>` thành `PagedModel<EntityModel<Order>>`.

Assembler nên tập trung chuyển dữ liệu đã được chuẩn bị thành representation. Tránh gọi repository cho từng link hoặc truy cập quan hệ lazy trong vòng lặp. Nếu link cần ID của tài nguyên liên quan, hãy tải ID bằng projection hoặc truy vấn phù hợp ở tầng service để tránh N+1.

## 5. HAL: cách representation được tuần tự hóa

HAL là một định dạng JSON phổ biến để biểu diễn hypermedia. Khi dùng HAL JSON, media type thường là `application/hal+json`.

Các thành phần thường gặp:

| Thành phần HAL | Ý nghĩa |
|---|---|
| `_links` | Các link của representation |
| `_embedded` | Các representation được nhúng bên trong |
| `href` | URI đích của link |
| `templated` | Cho biết href là URI template |
| `page` | Metadata phân trang trong representation phân trang |

Một collection HAL có thể có hình dạng khái quát:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "_links": {
          "self": {
            "href": "https://api.example.test/api/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/api/orders"
    },
    "next": {
      "href": "https://api.example.test/api/orders?page=1"
    }
  }
}
~~~

Tên relation trong `_embedded` phụ thuộc cấu hình relation provider và cách ứng dụng mô tả collection. Ví dụ trên minh họa hình dạng dữ liệu, không phải tên bắt buộc cho mọi collection.

Trong Spring Boot, cấu hình hypermedia thường được tự động thiết lập khi dependency Spring HATEOAS có mặt. Với cấu hình Spring MVC độc lập, có thể bật hỗ trợ hypermedia bằng `@EnableHypermediaSupport` và chọn loại HAL phù hợp.

HAL CURIE có thể được dùng để rút gọn các URI relation mở rộng. Ví dụ, một relation URI dài có thể xuất hiện dưới dạng `ex:customer`; client tra cứu khai báo CURIE để xác định URI đầy đủ. Hãy dùng CURIE khi nó giúp response dễ đọc mà vẫn giữ định danh relation ổn định.

## 6. Affordance: mô tả hành động khả dụng

Link mô tả nơi client có thể điều hướng. Affordance bổ sung metadata về hành động có thể thực hiện tại tài nguyên, chẳng hạn:

- Phương thức HTTP được hỗ trợ.
- Kiểu dữ liệu đầu vào.
- Các trường mà client cần gửi.
- Hình thức biểu diễn request và response.

Ví dụ, một đơn hàng đang chờ xử lý có thể cung cấp khả năng hủy. Khi đơn hàng đã giao, affordance hủy không còn phù hợp.

Affordance giúp client hiểu cách thực hiện hành động thay vì chỉ biết URI. Để biểu diễn thông tin form hoặc thao tác theo cách có cấu trúc, ứng dụng có thể dùng media type hỗ trợ affordance như HAL-FORMS. HAL JSON cơ bản chủ yếu mô tả link và embedded resource; không nên giả định mọi metadata affordance đều tự xuất hiện trong HAL.

Affordance không thực thi hành động và không thay thế xác thực, phân quyền hoặc kiểm tra trạng thái ở endpoint. Server phải xác minh request mỗi khi client gửi hành động.

## 7. Pagination, sorting, filtering và search links

Các endpoint danh sách thường cần nhiều khả năng điều hướng:

- `first`, `prev`, `self`, `next`, `last` để chuyển trang.
- `search` để tìm kiếm theo từ khóa.
- Link template có `sort`, `page`, `size` hoặc bộ lọc phù hợp.

`PagedResourcesAssembler` giúp tạo representation phân trang từ Spring Data `Page` và bổ sung link điều hướng. Khi tạo link, hãy giữ lại các tham số tìm kiếm và lọc đang áp dụng để client có thể chuyển trang mà không mất ngữ cảnh.

Ví dụ, một response có thể công bố link search dạng template:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/api/products/search{?q,category,page,size}",
      "templated": true
    }
  }
}
~~~

Search suggestion là một bước riêng trong luồng tìm kiếm. API có thể cung cấp relation gợi ý với URI template nhận một phần từ khóa; mỗi gợi ý sau đó có link `search` đã điền từ khóa được chọn. Client khám phá các relation này thay vì tự ghép URL.

Khi thiết kế filter và sort, hãy công bố rõ các biến được hỗ trợ và giới hạn hợp lệ. Không nên tạo link cho tham số mà endpoint không xử lý.

## 8. Client điều hướng theo hypermedia

Client hypermedia bắt đầu từ một URI gốc đã biết, đọc representation, tìm relation cần thiết rồi theo href. Với URI template, client mở rộng biến theo đầu vào của người dùng.

Luồng ví dụ với đơn hàng:

1. Client gọi URI gốc của API và nhận representation có link `orders`.
2. Client theo link `orders` để lấy collection.
3. Client chọn một đơn hàng và theo link `self`.
4. Client tìm relation `customer` để mở khách hàng liên quan.
5. Client tìm relation `order-items` để xem các dòng hàng.
6. Nếu representation cung cấp affordance phù hợp, client có thể hiển thị hành động tương ứng.

Lợi ích của cách tiếp cận này là client phụ thuộc vào ý nghĩa relation và các URI được server công bố. Server có thể thay đổi cấu trúc đường dẫn trong khi giữ ổn định relation và cập nhật href tương ứng.

Hypermedia không tự động làm client độc lập hoàn toàn với mọi thay đổi. Client vẫn cần hiểu relation, cấu trúc dữ liệu, media type và các quy tắc nghiệp vụ mà API công bố.

## 9. Kiểm thử hợp đồng hypermedia

Một API HATEOAS cần được kiểm thử ở cả hai mức:

- **Kiểm thử dữ liệu:** status HTTP, trường dữ liệu, validation và kết quả nghiệp vụ.
- **Kiểm thử hypermedia:** relation, href, URI template, embedded resource và affordance nếu có.

Ví dụ với MockMvc:

~~~java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer.href").exists());
~~~

Với relation mở rộng dùng URI đầy đủ, có thể dùng `ObjectMapper` để đọc JSON thành `JsonNode` rồi truy cập key relation chính xác. Với URI template, kiểm tra cả `templated: true` và các biến cần có. Với link hành động, kiểm tra link chỉ xuất hiện khi điều kiện nghiệp vụ cho phép.

Ngoài việc kiểm tra href, hãy gọi endpoint đích trong integration test để xác nhận link có thể điều hướng đến tài nguyên thực. Tránh phụ thuộc vào host hoặc port tuyệt đối nếu môi trường test có cấu hình động.

## 10. Hiệu năng và bảo trì

Mỗi link cần được tạo, đưa vào representation và tuần tự hóa. Với một tài nguyên, chi phí thường nhỏ; với collection lớn, số link tăng theo số phần tử và số relation được tạo cho mỗi phần tử.

Một số nguyên tắc thực tế:

- Dùng pagination để giới hạn số phần tử trong một response.
- Chỉ tạo link quan hệ và hành động có ý nghĩa với tài nguyên hiện tại.
- Tránh tạo cùng một link nhiều lần trong quá trình dựng model.
- Chuẩn bị ID và trạng thái liên quan ở tầng service, tránh truy vấn N+1 trong assembler.
- Đo CPU, allocation, số truy vấn, kích thước JSON và thời gian tuần tự hóa trước khi tối ưu.
- Cẩn trọng khi cache link hoặc representation phụ thuộc host, request, tenant, người dùng, quyền hay trạng thái tài nguyên.

Không nên loại bỏ link quan trọng chỉ để giảm kích thước response. Hãy xác định link dư thừa hoặc số phần tử vượt nhu cầu, rồi so sánh hiệu năng trước và sau bằng dữ liệu đại diện.

## 11. Tiến hóa hợp đồng API

Relation là một phần của hợp đồng mà client sử dụng để khám phá khả năng của server. Khi tiến hóa API:

1. Giữ nguyên ý nghĩa của relation đã công bố.
2. Dùng relation URI ổn định cho các quan hệ mở rộng.
3. Có thể bổ sung relation mới theo cách tương thích nếu client cũ có thể bỏ qua relation chưa biết.
4. Tránh xóa hoặc tái sử dụng relation đang được client sử dụng.
5. Duy trì href đúng với cấu hình triển khai, context path và reverse proxy.
6. Cập nhật tài liệu và kiểm thử khi thay đổi media type, URI template hoặc affordance.

Việc thêm link thường là thay đổi mở rộng, nhưng không tự động đảm bảo tương thích. Nếu client phụ thuộc vào một relation hoặc một dạng dữ liệu cụ thể, hãy giữ hợp đồng đó hoặc cung cấp lộ trình chuyển đổi rõ ràng.

## 12. Bản đồ lựa chọn nhanh

| Nhu cầu | Thành phần nên xem xét |
|---|---|
| Một tài nguyên kèm link | `EntityModel<T>` |
| Collection tài nguyên | `CollectionModel<T>` |
| Collection phân trang | `PagedModel<T>` và `PagedResourcesAssembler` |
| Gắn link vào dữ liệu đã có | `RepresentationModelAssembler` |
| Tạo link theo controller mapping | `linkTo(methodOn(...))` |
| Quan hệ chuẩn | `IanaLinkRelations` |
| Quan hệ nghiệp vụ riêng | `LinkRelation` với URI ổn định |
| Tham số chưa biết trước | URI template |
| Mô tả hành động khả dụng | Affordance và media type hỗ trợ |
| JSON hypermedia | HAL và `application/hal+json` |
| Kiểm tra relation và href | MockMvc, JsonPath hoặc Jackson |
| Kiểm soát response lớn | Pagination và đo hiệu năng |

## 13. Bài tập tổng hợp

Một API bán hàng quản lý sản phẩm và đơn hàng. Hãy phác thảo representation cho hai loại tài nguyên:

- Sản phẩm có `self`, link đến danh mục và link `search` để tìm sản phẩm tương tự.
- Đơn hàng có `self`, link đến khách hàng, link đến dòng hàng và affordance hủy nếu trạng thái cho phép.

Trong thiết kế, hãy trả lời:

1. Bạn sẽ dùng `EntityModel`, `CollectionModel` hay `PagedModel` ở từng endpoint?
2. Relation nào đã có trong IANA và relation nào cần định nghĩa bằng URI?
3. Link nào cần URI template?
4. Assembler sẽ lấy những dữ liệu nào từ service để tránh truy vấn N+1?
5. HAL JSON sẽ biểu diễn link và collection như thế nào?
6. Những assertion nào cần có trong MockMvc để bảo vệ hợp đồng?
7. Khi đổi mapping của controller, client có thể tiếp tục điều hướng bằng cách nào?

Một thiết kế tốt giúp client khám phá tài nguyên và hành động từ relation, còn server quản lý việc ánh xạ các relation đó đến endpoint thực tế.

## Kết luận

Spring HATEOAS kết nối domain data với representation có khả năng điều hướng. `EntityModel`, `CollectionModel` và `PagedModel` xác định hình dạng dữ liệu; `Link` và relation mô tả các đích đến; assembler tập trung quy tắc tạo model; affordance mô tả hành động; HAL chuyển representation thành JSON hypermedia để client khám phá và sử dụng.

Khi thiết kế API, hãy giữ relation ổn định, tạo href từ mapping, chọn đúng media type, phân trang collection lớn, kiểm thử hợp đồng hypermedia và xác minh quyền ở endpoint đích. Những nguyên tắc này giúp REST API dễ điều hướng và có thể tiến hóa mà client ít phụ thuộc vào cấu trúc URL nội bộ.

