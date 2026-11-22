# Định tuyến và xác định Controller xử lý

Trong module **MODEL_VIEW_CONTROLLER**, ứng dụng web dùng Controller để tiếp nhận request, điều phối xử lý và tạo response phù hợp. Trước khi một phương thức Controller chạy, framework cần xác định request đang nhắm đến chức năng nào. Quá trình đó gọi là **định tuyến** (routing): đối chiếu thông tin request với các quy tắc đã khai báo để chọn handler, thường là một phương thức trong Controller.

Định tuyến tạo ra ranh giới rõ giữa địa chỉ mà client gọi và mã xử lý bên trong ứng dụng. Khi route được thiết kế nhất quán, URL dễ hiểu, Controller dễ tìm, endpoint dễ kiểm thử và ứng dụng có thể thay đổi cách triển khai mà không làm client phải biết cấu trúc lớp nội bộ.

## 1. Định tuyến là gì?

Định tuyến là quá trình xác định request sẽ được chuyển đến handler nào dựa trên một hoặc nhiều thuộc tính của request. Trong ứng dụng HTTP, các thuộc tính thường dùng gồm:

- **Path:** phần đường dẫn của URL, ví dụ /orders/42.
- **HTTP method:** GET, POST, PUT, PATCH, DELETE hoặc method khác.
- **Query parameters:** dữ liệu sau dấu ?, ví dụ ?page=2&sort=date.
- **Headers:** thông tin trong header, đôi khi dùng để phân biệt loại request.
- **Content-Type:** định dạng dữ liệu client gửi lên, thường được kiểm tra qua điều kiện consumes.
- **Accept:** loại nội dung client mong muốn nhận, có thể được kiểm tra qua điều kiện produces.

Ví dụ, cùng một đường dẫn /orders có thể phục vụ nhiều hành động:

| HTTP method | Path | Mục đích thường gặp | Handler minh họa |
| --- | --- | --- | --- |
| GET | /orders | Lấy danh sách đơn hàng | listOrders |
| GET | /orders/42 | Xem đơn hàng có mã 42 | getOrder |
| POST | /orders | Tạo đơn hàng mới | createOrder |
| PATCH | /orders/42 | Cập nhật một phần đơn hàng | updateOrder |
| DELETE | /orders/42 | Xóa hoặc yêu cầu xóa đơn hàng | deleteOrder |

Path và HTTP method thường là căn cứ chính để phân biệt chức năng. Các điều kiện khác có thể bổ sung khi hợp đồng yêu cầu. Không nên thiết kế endpoint chỉ dựa trên tên phương thức Java; client giao tiếp qua URL và HTTP, không cần biết tên lớp hay tên method trong mã nguồn.

## 2. Route kết nối URL với Controller như thế nào?

Một route thường gồm một mẫu đường dẫn, một hoặc nhiều HTTP method được chấp nhận và có thể có thêm điều kiện. Khi request khớp với route, framework chọn handler tương ứng rồi chuyển dữ liệu request vào các tham số của handler.

Trong Spring MVC, các annotation phổ biến để khai báo route là:

- **@RequestMapping:** khai báo ánh xạ tổng quát ở cấp Controller hoặc method.
- **@GetMapping:** ánh xạ request GET.
- **@PostMapping:** ánh xạ request POST.
- **@PutMapping**, **@PatchMapping**, **@DeleteMapping:** ánh xạ các method tương ứng.

Ví dụ:

~~~java
@Controller
@RequestMapping("/orders")
public class OrderController {

    @GetMapping
    public String list() {
        return "orders/list";
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable long id, Model model) {
        // Lấy dữ liệu theo id và cung cấp cho View
        return "orders/detail";
    }

    @PostMapping
    public String create(@Valid @ModelAttribute OrderForm form,
                         BindingResult errors) {
        // Kiểm tra form và gọi use case tạo đơn hàng
        return "redirect:/orders";
    }
}
~~~

Ở đây, @RequestMapping("/orders") đặt tiền tố chung cho các route trong Controller. Các annotation ở method khai báo phần đường dẫn và HTTP method cụ thể. Vì vậy, method list xử lý GET /orders, detail xử lý GET /orders/{id}, còn create xử lý POST /orders.

Một route không nhất thiết tương ứng với một lớp Controller. Một Controller có thể chứa nhiều handler cho cùng một nhóm tài nguyên; nhiều Controller cũng có thể phụ trách các nhóm tài nguyên khác nhau. Nên tổ chức theo chức năng hoặc nhóm tài nguyên để người đọc tìm được handler dễ dàng.

## 3. Các phần của URL và cách lấy dữ liệu

URL có nhiều phần với vai trò khác nhau. Cần phân biệt path variable, query parameter và dữ liệu trong request body để chọn cách khai báo phù hợp.

Giả sử client gọi:

~~~text
GET /orders/42/items?page=2&sort=price
~~~

| Phần request | Giá trị ví dụ | Cách dùng thường gặp |
| --- | --- | --- |
| Path | /orders/42/items | Xác định tài nguyên hoặc nhóm chức năng |
| Path variable | 42 | Xác định một tài nguyên cụ thể |
| Query parameter | page=2 | Bộ lọc, phân trang hoặc tùy chọn truy vấn |
| Query parameter | sort=price | Cách sắp xếp kết quả |
| Request body | JSON hoặc form data | Dữ liệu tạo mới hoặc cập nhật |

Spring MVC cung cấp các annotation binding tương ứng:

~~~java
@GetMapping("/{orderId}/items")
public String items(
        @PathVariable long orderId,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "createdAt") String sort,
        Model model) {
    // Truy vấn các dòng hàng theo đơn, trang và cách sắp xếp
    return "orders/items";
}
~~~

**@PathVariable** lấy giá trị từ phần biến trong path. **@RequestParam** lấy query parameter hoặc tham số request theo cấu hình binding của framework. Với dữ liệu JSON gửi trong body, Spring thường dùng **@RequestBody** để chuyển JSON thành DTO. Với form HTML, **@ModelAttribute** thường được dùng để binding các trường form vào đối tượng.

Không nên đưa mọi dữ liệu vào path. Path thường biểu diễn danh tính hoặc cấu trúc tài nguyên; query parameter phù hợp với bộ lọc và tùy chọn truy vấn; body phù hợp với dữ liệu của thao tác tạo hoặc cập nhật. Thiết kế nhất quán giúp URL dễ đọc và hợp đồng API dễ sử dụng.

## 4. Framework xác định Controller xử lý

Ở mức khái quát, một request đi qua các bước sau:

1. Client gửi request HTTP đến ứng dụng.
2. Web server hoặc servlet container tiếp nhận request.
3. Các filter có thể xử lý request trước, ví dụ logging, CORS hoặc Spring Security.
4. Trong Spring MVC, DispatcherServlet nhận request và yêu cầu cơ chế HandlerMapping tìm handler phù hợp.
5. HandlerMapping đối chiếu path, method và các điều kiện mapping để xác định handler.
6. HandlerAdapter gọi phương thức Controller phù hợp và hỗ trợ binding tham số.
7. Controller gọi tầng ứng dụng hoặc Model, sau đó trả kết quả.
8. Framework xử lý giá trị trả về: render View qua ViewResolver, hoặc ghi response body qua HttpMessageConverter.
9. Response được gửi về client.

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Web server / servlet container]
    B --> C[Filter chain]
    C --> D[DispatcherServlet]
    D --> E[HandlerMapping]
    E -->|Tìm thấy handler| F[HandlerAdapter]
    F --> G[Controller method]
    G --> H[Use case / Model]
    H --> G
    G --> I{Kiểu kết quả}
    I -->|Tên View| J[ViewResolver và View]
    I -->|Response body| K[HttpMessageConverter]
    J --> L[HTTP response]
    K --> L
    E -->|Không có mapping phù hợp| M[404 hoặc lỗi định tuyến]
    M --> L
~~~

DispatcherServlet là front controller của Spring MVC: nó nhận request và điều phối đến handler. **HandlerMapping** chịu trách nhiệm tìm handler theo các mapping đã đăng ký. **HandlerAdapter** biết cách gọi loại handler được chọn. Việc phân chia này giúp framework xử lý nhiều kiểu handler qua một luồng điều phối chung.

Sơ đồ là luồng tổng quát trong Spring MVC. Các framework web khác có router và cơ chế dispatch riêng, nhưng ý tưởng chung vẫn là tiếp nhận request, tìm route phù hợp, gọi handler và tạo response.

## 5. Quy tắc khớp route và độ cụ thể

Một ứng dụng có thể có nhiều route với path giống hoặc gần giống nhau. Framework cần quy tắc để biết route nào phù hợp. Ví dụ:

~~~java
@GetMapping("/reports/summary")
public String summary() {
    return "reports/summary";
}

@GetMapping("/reports/{reportId}")
public String detail(@PathVariable String reportId) {
    return "reports/detail";
}
~~~

Request GET /reports/summary có thể khớp về mặt hình dạng với cả path cố định và path variable. Framework như Spring MVC có quy tắc xếp hạng độ cụ thể của pattern để chọn mapping phù hợp. Dù vậy, nhóm phát triển nên tránh tạo các mapping mơ hồ hoặc dựa vào hành vi khó đoán.

Các nguyên tắc thiết kế:

- Ưu tiên route tĩnh, có ý nghĩa rõ ràng cho các endpoint đặc biệt như /reports/summary.
- Dùng path variable cho định danh tài nguyên, ví dụ /reports/{reportId}.
- Giới hạn định dạng biến nếu có thể, chẳng hạn chỉ nhận chữ số cho ID số.
- Tránh khai báo hai handler cùng khớp một request với cùng điều kiện.
- Dùng HTTP method để phân biệt hành động trên cùng tài nguyên.
- Không dùng route bắt tất cả quá rộng nếu nó có thể che khuất endpoint cụ thể hoặc làm lỗi khó phát hiện.

Spring cho phép khai báo điều kiện bổ sung như params, headers, consumes và produces:

~~~java
@GetMapping(path = "/reports/{id}", produces = "application/json")
public ReportResponse getJson(@PathVariable long id) {
    return reportQuery.get(id);
}

@PostMapping(path = "/reports", consumes = "application/json")
public ResponseEntity<ReportCreatedResponse> createJson(
        @RequestBody CreateReportRequest request) {
    // Tạo báo cáo và trả response
    return ResponseEntity.accepted().build();
}
~~~

Điều kiện **produces** mô tả loại nội dung handler có thể trả; **consumes** mô tả loại nội dung handler chấp nhận trong request body. Nếu client gửi Content-Type hoặc Accept không phù hợp, framework có thể từ chối mapping với lỗi media type thay vì gọi handler.

Không nên thêm điều kiện mapping chỉ để làm route phức tạp hơn. Chỉ dùng chúng khi client và server thực sự có các hợp đồng nội dung khác nhau.

## 6. Path variable, query parameter và request body

Chọn đúng vị trí cho dữ liệu làm route và binding dễ hiểu hơn:

| Nhu cầu | Cách biểu diễn phù hợp | Ví dụ |
| --- | --- | --- |
| Chỉ định tài nguyên | Path variable | /users/15 |
| Chỉ định tài nguyên con | Path lồng nhau | /orders/42/items |
| Lọc hoặc phân trang | Query parameter | /orders?status=PAID&page=2 |
| Tạo tài nguyên | Request body | POST /orders với JSON |
| Cập nhật một phần | Request body | PATCH /orders/42 với các trường thay đổi |
| Chọn định dạng phản hồi | Accept header hoặc endpoint riêng | Accept: application/json |

Path variable thường là phần quan trọng của danh tính tài nguyên. Query parameter thường không làm thay đổi tài nguyên được định danh, mà điều chỉnh tập kết quả hoặc cách trình bày. Request body chứa dữ liệu được gửi để xử lý.

Không nên đặt mật khẩu, token, thông tin cá nhân nhạy cảm hoặc dữ liệu lớn trong query string. URL có thể xuất hiện trong lịch sử trình duyệt, log, proxy hoặc header Referer. Dữ liệu nhạy cảm cần được truyền qua cơ chế phù hợp, thường là body qua HTTPS hoặc header xác thực theo giao thức.

## 7. Phân biệt lỗi định tuyến và lỗi xử lý

Không phải mọi lỗi request đều là lỗi trong phương thức Controller. Cần xác định request thất bại ở giai đoạn nào.

| Tình huống | Ý nghĩa | Phản hồi thường gặp |
| --- | --- | --- |
| Không có route phù hợp với path | Không tìm thấy endpoint | 404 Not Found |
| Path có route nhưng HTTP method không được hỗ trợ | Endpoint tồn tại nhưng method không phù hợp | 405 Method Not Allowed |
| Content-Type không được route chấp nhận | Định dạng request body không phù hợp | 415 Unsupported Media Type |
| Accept không khớp định dạng có thể trả | Không có representation phù hợp | 406 Not Acceptable |
| Route khớp nhưng tham số sai định dạng | Binding hoặc conversion thất bại | Thường là 400 Bad Request |
| Route và binding hợp lệ nhưng tài nguyên không tồn tại | Lỗi xử lý nghiệp vụ hoặc truy vấn | 404 theo hợp đồng ứng dụng |
| Use case từ chối vì trạng thái xung đột | Request hợp lệ về cú pháp nhưng không thể thực hiện | 409 Conflict có thể phù hợp |

**404** do không tìm thấy route khác với 404 do Controller hoặc tầng ứng dụng không tìm thấy tài nguyên. Hai trường hợp có thể cùng dùng status 404 nhưng log, thông báo và cách xử lý nội bộ khác nhau. Khi điều tra sự cố, cần kiểm tra request có được ánh xạ đến handler hay chưa.

Nếu route tồn tại nhưng method không phù hợp, HTTP 405 thường đi kèm header Allow liệt kê các method được hỗ trợ. Không nên tự biến mọi trường hợp này thành 404 vì client sẽ khó hiểu endpoint có tồn tại hay không.

## 8. Thiết kế route rõ ràng và nhất quán

Route là hợp đồng công khai giữa client và server. Một số nguyên tắc hữu ích:

- **Dùng danh từ cho tài nguyên.** Ví dụ /orders, /customers hoặc /products; dùng HTTP method để thể hiện hành động phổ biến trên tài nguyên.
- **Giữ cấu trúc nhất quán.** Nếu tài nguyên con được truy cập qua /orders/{id}/items thì các tài nguyên con khác nên theo quy ước tương tự.
- **Giữ URL ổn định.** Khi đổi tên Controller hoặc di chuyển package, URL công khai không nên đổi nếu không có lý do tương thích.
- **Dùng versioning có chủ đích.** API có thể dùng /api/v1/orders hoặc cơ chế versioning qua header; cần chọn và tài liệu hóa một quy ước nhất quán.
- **Tránh route chứa thông tin nội bộ.** Không để lộ tên bảng, tên class hoặc cấu trúc package trong URL.
- **Xem xét phân trang và lọc.** Danh sách lớn nên hỗ trợ page, size, sort hoặc cursor với giới hạn hợp lý.

Ví dụ một nhóm route cho đơn hàng:

| Route | Mục đích |
| --- | --- |
| GET /api/v1/orders | Liệt kê đơn hàng theo bộ lọc |
| POST /api/v1/orders | Tạo đơn hàng |
| GET /api/v1/orders/{orderId} | Lấy chi tiết đơn hàng |
| PATCH /api/v1/orders/{orderId} | Cập nhật một phần thông tin được phép |
| DELETE /api/v1/orders/{orderId} | Yêu cầu xóa đơn hàng theo chính sách |
| GET /api/v1/orders/{orderId}/items | Liệt kê các dòng hàng |

Không phải hệ thống nào cũng cần đủ các route này. Chỉ công khai những thao tác mà nghiệp vụ cho phép và xác định rõ semantics, status code, quyền truy cập cũng như định dạng dữ liệu.

## 9. Định tuyến và bảo mật

Route xác định handler có thể nhận request; nó không tự chứng minh người gọi được phép thực hiện hành động. Sau khi định tuyến, ứng dụng vẫn cần xác thực và phân quyền theo chính sách.

- **Xác thực (authentication):** xác định danh tính người gọi, thường được thực hiện trong filter chain hoặc cơ chế bảo mật của framework.
- **Phân quyền (authorization):** quyết định người gọi có được phép truy cập endpoint hoặc tài nguyên cụ thể hay không.
- **Kiểm tra quyền trên tài nguyên:** một người dùng đã đăng nhập vẫn có thể không được xem đơn hàng của người khác. Use case hoặc tầng bảo mật cần kiểm tra quyền trên chính tài nguyên.
- **Giới hạn đầu vào:** ràng buộc định dạng path variable, kích thước request và các tham số để giảm dữ liệu không hợp lệ.
- **Không tin tưởng ID từ URL:** việc client biết hoặc đoán được ID không có nghĩa là họ có quyền truy cập tài nguyên đó.

Trong Spring Security, filter chain có thể chặn request trước khi DispatcherServlet gọi Controller. Ngoài ra, ứng dụng có thể dùng method security để bảo vệ thao tác ở tầng ứng dụng. Việc ẩn một liên kết hoặc nút trong View không thay thế kiểm tra quyền ở server.

## 10. Kiểm thử định tuyến và chọn Controller

Kiểm thử route cần xác nhận request được ánh xạ đúng handler và những request không hợp lệ nhận response phù hợp.

Các trường hợp nên kiểm tra:

- Path và HTTP method đúng gọi đúng handler.
- Path variable được binding đúng kiểu và giá trị.
- Query parameter có giá trị mặc định, giới hạn và quy tắc binding đúng.
- Route tĩnh và route động không xung đột.
- Method không được hỗ trợ trả 405 theo hợp đồng.
- Content-Type và Accept không phù hợp được xử lý rõ ràng.
- Endpoint được bảo vệ từ chối người dùng chưa xác thực hoặc không đủ quyền.
- Route không tồn tại trả 404 và không vô tình rơi vào handler bắt tất cả.

Với Spring MVC, có thể dùng **MockMvc** để gửi request giả lập qua cơ chế MVC và xác minh status, view name, model attribute hoặc response body. Ví dụ:

~~~java
record OrderDetailViewModel(String orderNumber) {}

@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    OrderQuery orderQuery;

    @Test
    void getOrderMapsToDetailView() throws Exception {
        given(orderQuery.getDetail("42"))
                .willReturn(new OrderDetailViewModel("ORD-42"));

        mvc.perform(get("/orders/42"))
                .andExpect(status().isOk())
                .andExpect(view().name("orders/detail"))
                .andExpect(model().attributeExists("page"));
    }
}
~~~

Đây là ví dụ minh họa cấu trúc kiểm thử; constructor của view model và cấu hình test cần được điều chỉnh theo mã nguồn thực tế. Ngoài kiểm thử handler riêng lẻ, nên có kiểm thử tích hợp cho những route quan trọng để xác nhận cấu hình bảo mật, binding và exception handler phối hợp đúng.

## 11. Quy trình thêm một route mới

Khi bổ sung endpoint, hãy thực hiện theo thứ tự:

1. Xác định tài nguyên hoặc hành động mà client cần truy cập.
2. Chọn path và HTTP method phản ánh đúng mục đích.
3. Xác định dữ liệu thuộc path, query, header hay request body.
4. Khai báo mapping và điều kiện cần thiết, tránh tạo route mơ hồ.
5. Xác định Controller hoặc handler chịu trách nhiệm và use case sẽ được gọi.
6. Định nghĩa response thành công, các lỗi có thể xảy ra và mã HTTP tương ứng.
7. Xác định yêu cầu xác thực, phân quyền và giới hạn đầu vào.
8. Viết kiểm thử cho route đúng, route sai, method sai và các trường hợp binding quan trọng.
9. Cập nhật tài liệu API hoặc hướng dẫn sử dụng endpoint để client có thể tích hợp.

Ví dụ, khi thêm endpoint xem các dòng hàng của một đơn, ta có thể chọn GET /orders/{orderId}/items. Path variable orderId xác định đơn hàng; query parameter page và size điều khiển phân trang. Controller gọi use case truy vấn, kiểm tra quyền truy cập đơn hàng, sau đó trả View hoặc JSON tùy loại client.

## Kết luận

Định tuyến đối chiếu path, HTTP method và các điều kiện của request để xác định Controller hoặc handler xử lý. Trong Spring MVC, DispatcherServlet phối hợp với HandlerMapping và HandlerAdapter để tìm và gọi handler phù hợp. Khi route có cấu trúc rõ, tham số được đặt đúng vị trí, lỗi định tuyến được phân biệt với lỗi nghiệp vụ và quyền truy cập được kiểm tra ở server, ứng dụng MVC dễ mở rộng, kiểm thử và tích hợp với client hơn.
