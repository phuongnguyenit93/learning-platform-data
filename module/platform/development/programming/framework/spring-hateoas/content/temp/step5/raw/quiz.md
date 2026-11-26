Câu 01. Trong Spring HATEOAS, lớp nền nào lưu các liên kết hypermedia của một representation?
A. `LinkRelation` quản lý payload và links của một entity
B. `ResponseEntity` quản lý danh sách link trong HTTP header
C. `RepresentationModel` quản lý danh sách link trên model
D. `HttpEntity` quản lý link relation trong response body
Đáp án đúng: C

Câu 02. Khi cần bao DTO `order` cùng các link của nó thành resource, factory nào phù hợp?
A. `CollectionModel.of(order, selfLink)` bao một entity
B. `EntityModel.of(order, selfLink)` bao payload và link
C. `PagedModel.of(order, selfLink)` bao một entity
D. `RepresentationModel.of(order, selfLink)` bao một entity
Đáp án đúng: B

Câu 03. Khi trả về nhiều `OrderModel` kèm link collection, kiểu nào phù hợp?
A. `PagedModel.PageMetadata.of(orders, collectionLink)`
B. `Link.of(orders, collectionLink)` gói tập phần tử
C. `CollectionModel.of(orders, collectionLink)` gói tập phần tử
D. `EntityModel.of(orders, collectionLink)` gói tập phần tử
Đáp án đúng: C

Câu 04. Khi trả danh sách có cả thông tin trang và link, nên dùng kiểu nào?
A. `Affordance` chứa content, page metadata và links
B. `EntityModel` chứa content, page metadata và links
C. `LinkRelation` chứa content, page metadata và links
D. `PagedModel` chứa content, page metadata và links
Đáp án đúng: D

Câu 05. Muốn tạo representation `OrderModel` có field riêng và hỗ trợ link, khai báo nào đúng?
A. `class OrderModel extends ResponseEntity<OrderModel>`
B. `class OrderModel extends LinkRelation<OrderModel>`
C. `class OrderModel extends PageMetadata<OrderModel>`
D. `class OrderModel extends RepresentationModel<OrderModel>`
Đáp án đúng: D

Câu 06. Với `EntityModel<?> model`, method nào thêm một link mà vẫn giữ payload?
A. `model.add(link)` bổ sung Link vào representation
B. `model.setHref(link)` thay URL trên representation
C. `model.withRel(link)` gán relation cho cả model
D. `model.setBody(link)` thay payload bằng một Link
Đáp án đúng: A

Câu 07. Muốn duyệt toàn bộ link đã gắn trong một `RepresentationModel`, dùng gì?
A. `model.getAffordances()` lấy tập các Link đang có
B. `model.getContent()` lấy tập các Link đang có
C. `model.getMetadata()` lấy tập các Link đang có
D. `model.getLinks()` lấy tập các Link đang có
Đáp án đúng: D

Câu 08. Trong hypermedia link, `rel` diễn tả điều gì khác với `href`?
A. `rel` chứa URI đích, còn `href` là nhãn quan hệ
B. `rel` chứa mã HTTP, còn `href` là HTTP verb
C. `rel` chứa body request, còn `href` là query model
D. `rel` nêu quan hệ/ngữ nghĩa, còn `href` chứa URI đích
Đáp án đúng: D

Câu 09. Khi link trỏ tới representation hiện tại, relation chuẩn IANA nào phù hợp?
A. `IanaLinkRelations.PREV` biểu diễn liên kết tự tham chiếu
B. `IanaLinkRelations.FIRST` biểu diễn liên kết tự tham chiếu
C. `IanaLinkRelations.SELF` biểu diễn liên kết tự tham chiếu
D. `IanaLinkRelations.NEXT` biểu diễn liên kết tự tham chiếu
Đáp án đúng: C

Câu 10. Nếu đơn hàng đang được phép hủy, link relation tùy biến nào rõ nghĩa hành động?
A. `collection` liên kết tới thao tác hủy được cho phép
B. `cancel` liên kết tới thao tác hủy được cho phép
C. `self` liên kết tới thao tác hủy được cho phép
D. `next` liên kết tới thao tác hủy được cho phép
Đáp án đúng: B

Câu 11. Muốn gắn relation `next` theo chuẩn IANA cho link phân trang, dùng gì?
A. `withRel(IanaLinkRelations.SELF)` trên link cần tạo
B. `withRel(IanaLinkRelations.PREV)` trên link cần tạo
C. `withRel(IanaLinkRelations.NEXT)` trên link cần tạo
D. `withRel(IanaLinkRelations.LAST)` trên link cần tạo
Đáp án đúng: C

Câu 12. Controller `OrderController` có `@RequestMapping("/orders")` và GET `/{id}`; câu lệnh nào tạo self link cho id 42?
A. `linkTo(methodOn(OrderController.class).getOrder(42)).withSelfRel()`
B. `linkTo(OrderController.class).withSelfRel()` trỏ collection
C. `linkTo(methodOn(OrderController.class).getOrder(42)).withRel("next")`
D. `linkTo(methodOn(OrderController.class).listOrders()).withSelfRel()`
Đáp án đúng: A

Câu 13. Khi chỉ cần link đến đường dẫn base của `OrderController` gắn `@RequestMapping("/orders")`, dùng gì?
A. `linkTo(OrderController.class).withSelfRel()` theo class mapping
B. `linkTo(methodOn(OrderController.class).cancel(42)).withSelfRel()`
C. `linkTo(OrderController.class).slash(42).withSelfRel()`
D. `linkTo(methodOn(OrderController.class).getOrder(42)).withSelfRel()`
Đáp án đúng: A

Câu 14. Sau khi `linkTo(...)` đã có URL đích, method nào gán IANA self relation?
A. `withRel("next")` chuyển builder thành link rel self
B. `withSelfRel()` chuyển builder thành link với rel self
C. `withRel("prev")` chuyển builder thành link rel self
D. `withRel("item")` chuyển builder thành link rel self
Đáp án đúng: B

Câu 15. Muốn tạo một Link từ URL cụ thể rồi đổi relation thành `details`, lựa chọn nào hợp lệ?
A. `Link.of("/orders/42").withRel("next")`
B. `Link.of("/orders/42").withRel("prev")`
C. `Link.of("/orders/42").withRel("details")`
D. `Link.of("/orders/42").withRel("self")`
Đáp án đúng: C

Câu 16. Với Link có `href="/orders{?page,size}"`, thuộc tính nào cho biết URL vẫn chứa URI template?
A. `link.isAbsolute()` trả true khi URI còn biến template
B. `link.isTemplated()` trả true khi URI còn biến template
C. `link.isExpanded()` trả true khi URI còn biến template
D. `link.isEmbedded()` trả true khi URI còn biến template
Đáp án đúng: B

Câu 17. Muốn điền giá trị `page` và `size` vào URI template của một `Link`, cần dùng API nào?
A. `link.expand(...)` trả link với URI template đã mở rộng
B. `link.expandRel(...)` trả link với URI template đã mở rộng
C. `link.resolveType(...)` trả link với URI template mở rộng
D. `link.getRelation(...)` trả link với URI template mở rộng
Đáp án đúng: A

Câu 18. `WebMvcLinkBuilder.linkTo(methodOn(...))` có lợi ích nào so với ghép chuỗi URL thủ công?
A. Dựa vào transaction manager để tạo đường dẫn nhất quán
B. Dựa vào database metadata để tạo đường dẫn nhất quán
C. Dựa vào DTO serializer để tạo đường dẫn nhất quán
D. Dựa vào mapping controller để tạo đường dẫn nhất quán
Đáp án đúng: D

Câu 19. Khi API trả link có `rel="payment"`, client HATEOAS nên sử dụng theo cách nào?
A. Khám phá link `payment` theo relation thay vì cố định URL
B. Dùng index cố định của phần tử trong `_links` để gọi
C. Tự dựng URL `/payment` từ tên relation trên client
D. Giả định HTTP method GET cho bất cứ relation nào
Đáp án đúng: A

Câu 20. Trong Spring HATEOAS, affordance gắn với link chủ yếu mô tả điều gì?
A. Transaction tự chạy mỗi khi client đọc relation trong link
B. HTTP status dự kiến trả về khi người dùng nhấn link
C. Thao tác có thể thực hiện, gồm method và metadata đầu vào
D. Payload được lưu vào cache sau khi JSON được serialize
Đáp án đúng: C

Câu 21. Trong HAL JSON, object nào chứa các link theo relation?
A. `_templates` lưu self và các relation đến tài nguyên khác
B. `_links` lưu self và các relation đến tài nguyên khác
C. `page` lưu self và các relation đến tài nguyên khác
D. `_embedded` lưu self và các relation đến tài nguyên khác
Đáp án đúng: B

Câu 22. Khi HAL nhúng các representation liên quan để tránh một số lượt GET, dữ liệu thường nằm ở đâu?
A. `page` chứa các resource được nhúng theo relation
B. `_links` chứa các resource được nhúng theo relation
C. `_templates` chứa các resource được nhúng theo relation
D. `_embedded` chứa các resource được nhúng theo relation
Đáp án đúng: D

Câu 23. Giá trị media type nào biểu thị representation theo định dạng HAL JSON?
A. `application/problem+json` chỉ representation HAL JSON
B. `application/x-www-form-urlencoded` cho HAL JSON
C. `application/hal+json` chỉ representation HAL JSON
D. `application/octet-stream` chỉ representation HAL JSON
Đáp án đúng: C

Câu 24. Nếu cấu hình Spring HATEOAS thủ công để bật kiểu hypermedia HAL, annotation nào phù hợp?
A. `@EnableWebMvc(type = HypermediaType.HAL)`
B. `@EnableWebSocket(type = HypermediaType.HAL)`
C. `@EnableHypermediaSupport(type = HypermediaType.UBER)`
D. `@EnableHypermediaSupport(type = HypermediaType.HAL)`
Đáp án đúng: D

Câu 25. Muốn tùy biến tên relation cho model `Order` và collection `orders`, annotation nào hỗ trợ?
A. `@Relation(itemRelation="order", collectionRelation="orders")`
B. `@ResponseStatus(itemRelation="order", collectionRelation="orders")`
C. `@RestController(itemRelation="order", collectionRelation="orders")`
D. `@RequestMapping(itemRelation="order", collectionRelation="orders")`
Đáp án đúng: A

Câu 26. Interface nào của Spring HATEOAS chuyển một domain entity thành representation model?
A. `RepresentationModelAssembler<T,D>` dùng `toModel(T)`
B. `RepresentationModelProcessor<T>` dùng `toModel(T)`
C. `LinkRelationProvider<T>` dùng `toModel(T)`
D. `HandlerMethodArgumentResolver<T>` dùng `toModel(T)`
Đáp án đúng: A

Câu 27. Có assembler cho `Order` sang `OrderModel`; method nào xử lý nhiều entity thành collection?
A. `toPagedModel(orders)` tạo collection representation
B. `toLinksModel(orders)` tạo collection representation
C. `toCollectionModel(orders)` tạo collection representation
D. `toEntityModel(orders)` tạo collection representation
Đáp án đúng: C

Câu 28. Muốn thêm link chuẩn hóa cho một loại representation sau khi dựng, extension point nào phù hợp?
A. `HttpMessageConverter` xử lý relation qua bean lookup
B. `RepresentationModelProcessor` hậu xử lý model được tạo
C. `RepresentationModelAssembler` chỉ hậu xử lý JSON
D. `LinkRelationProvider` hậu xử lý model được tạo
Đáp án đúng: B

Câu 29. So với HAL cơ bản, HAL-FORMS có thể diễn tả thêm thông tin nào cho client?
A. `_templates` mô tả thao tác có thể gửi và input dự kiến
B. `_embedded` mô tả thao tác có thể gửi và input dự kiến
C. `_links` tự sinh schema nhập liệu cho mỗi operation
D. `page` quyết định kiểu form data cho các HTTP method
Đáp án đúng: A

Câu 30. Trong HAL, CURIE giúp ích như thế nào khi API dùng custom relation URI dài?
A. Chuyển custom relation thành relation `self` chuẩn
B. Rút gọn relation có namespace thành dạng prefix:term
C. Thay HTTP method của link dựa trên dấu hai chấm
D. Mã hóa URL đích bằng base64 để giảm kích thước body
Đáp án đúng: B

Câu 31. Đơn hàng trạng thái `SHIPPED` không còn hủy được; response hypermedia nên xử lý link cancel ra sao?
A. Thay URL cancel bằng chuỗi rỗng để client vẫn hiện nút
B. Giữ link cancel và giả định client tự chặn khi gửi request
C. Biến link cancel thành self để giữ cấu trúc JSON không đổi
D. Bỏ link cancel ở trạng thái không cho phép hành động đó
Đáp án đúng: D

Câu 32. Nếu client nhìn thấy link `cancel`, điều gì vẫn cần được thực hiện trên server?
A. Kiểm tra quyền và trạng thái khi request hủy thực sự đến
B. Tin vào link có sẵn nên bỏ qua kiểm tra quyền tại server
C. Xem client đã xác thực chỉ nhờ `rel` là `cancel`
D. Thực hiện lệnh hủy ngay khi serialize link cancel
Đáp án đúng: A

Câu 33. Với `PagedModel`, metadata thường gồm nhóm thông tin nào?
A. HTTP method, request body, HTTP status và server version
B. Cookie, session, authorization token và response headers
C. Tên database, số kết nối, tổng transaction và cache size
D. Kích thước trang, số trang, tổng phần tử và tổng trang
Đáp án đúng: D

Câu 34. Trong collection phân trang, relation chuẩn `next` dùng để mô tả gì?
A. Link đến tài nguyên gốc không mang tham số phân trang
B. Link đến trang trước nếu đang ở trang khác trang đầu
C. Link đến chính trang hiện tại với cùng query params
D. Link đến trang kế tiếp nếu vẫn còn dữ liệu để xem
Đáp án đúng: D

Câu 35. Khi đường dẫn `/v1/orders/42` đổi sang `/orders/42`, client theo HATEOAS nên làm gì?
A. Tiếp tục tìm link theo relation từ response mới
B. Tiếp tục ghép prefix `/v1` lên mỗi link mới trả về
C. Chuyển relation thành chuỗi đường dẫn cũ
D. Bỏ các link từ response và dùng route đã hardcode
Đáp án đúng: A

Câu 36. Với HAL response của order 42, JSONPath nào kiểm URL của self link bằng MockMvc?
A. `$.links.self.url` trỏ đến href của self link
B. `$._links.self.href` trỏ đến href của self link
C. `$.page.self.href` trỏ đến href của self link
D. `$._embedded.self.href` trỏ đến href của self link
Đáp án đúng: B

Câu 37. Trong kiểm thử API có điều hướng, assertion nào bảo vệ tốt hợp đồng hypermedia?
A. Chỉ so chuỗi JSON hoàn chỉnh kể cả thứ tự fields
B. Chỉ kiểm DTO field mà bỏ các link navigation
C. Kiểm relation cần có, href và điều kiện hiển thị link
D. Chỉ kiểm mã HTTP 200 cho các trạng thái đơn hàng
Đáp án đúng: C

Câu 38. Khi cần client yêu cầu HAL bằng content negotiation, HTTP header nào phù hợp?
A. `Content-Type: application/hal+json` chọn output
B. `Authorization: application/hal+json` chọn output
C. `Accept: application/hal+json` yêu cầu HAL response
D. `Location: application/hal+json` yêu cầu HAL response
Đáp án đúng: C

Câu 39. Nếu một relation có nhiều link trong HAL, hình thức JSON hợp lý nào?
A. Relation phải chuyển sang `_embedded` thay vì `_links`
B. Relation chứa mảng các object có `href` tương ứng
C. Relation phải có một object chứa HTTP response status
D. Relation chỉ cho phép một chuỗi href dạng plain text
Đáp án đúng: B

Câu 40. Trong REST API có hypermedia, vai trò chính của self link trong response item là gì?
A. Định nghĩa contract xác thực mới cho các request khác
B. Định danh vị trí có thể truy xuất representation hiện tại
C. Định nghĩa transaction sẽ chạy khi serialize resource
D. Định nghĩa thông điệp WebSocket cho sự kiện tạo item
Đáp án đúng: B
