# 404 do thiếu mapping khác với 404 do nghiệp vụ

HTTP 404 Not Found có thể xuất hiện ở hai thời điểm rất khác nhau trong Spring MVC. Trường hợp thứ nhất là Spring không tìm được handler phù hợp cho request: URL, HTTP method hoặc điều kiện mapping không khớp với endpoint đã đăng ký. Trường hợp thứ hai là request đã được định tuyến tới controller, controller gọi service và nghiệp vụ xác định tài nguyên được yêu cầu không tồn tại.

Hai trường hợp có thể cùng trả status 404 nhưng nguyên nhân và cách sửa khác nhau. Nếu URL sai, cần sửa route hoặc request của client. Nếu URL đúng nhưng mã đơn hàng không tồn tại, response 404 có thể là kết quả nghiệp vụ hoàn toàn đúng. Khi chẩn đoán, cần xác định request đã vào handler nào, service có được gọi hay không và exception nào đã tạo response.

## 1. Hai con đường dẫn tới HTTP 404

### 1.1. Không có handler phù hợp

Spring MVC nhận request qua DispatcherServlet. DispatcherServlet sử dụng HandlerMapping để tìm handler có thể xử lý request dựa trên các điều kiện như path, HTTP method, query parameter, header, Content-Type và Accept.

Nếu không có mapping phù hợp, controller nghiệp vụ không được gọi. Ví dụ ứng dụng khai báo:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse find(@PathVariable long id) {
        // ...
    }
}
~~~

Các request sau không cùng một ý nghĩa:

~~~http
GET /api/orders/42
GET /api/order/42
GET /api/orders/42/details
~~~

Request đầu khớp path đã khai báo. Hai request sau không khớp mapping của controller này. Nếu không có handler khác nhận chúng, Spring trả 404. Phần thân phương thức find không chạy và service không được gọi.

Trong Spring MVC, trường hợp không tìm được handler có thể được biểu diễn bằng NoHandlerFoundException. Với cấu hình resource handler mặc định, một URL không khớp controller đôi khi được chuyển tới ResourceHttpRequestHandler; nếu file tĩnh tương ứng không tồn tại, Spring có thể phát sinh NoResourceFoundException. Đây vẫn là lỗi không tìm được nội dung để phục vụ, nhưng handler đã được chọn là resource handler.

### 1.2. Handler chạy nhưng tài nguyên nghiệp vụ không tồn tại

Với request GET /api/orders/999, mapping /api/orders/{id} vẫn khớp. Spring gọi controller, controller gọi service để tìm đơn hàng. Nếu service không tìm thấy dữ liệu, ứng dụng có thể trả 404 theo hợp đồng API:

~~~java
@GetMapping("/{id}")
OrderResponse find(@PathVariable long id) {
    return orderService.findById(id);
}
~~~

Ví dụ service ném OrderNotFoundException khi id không tồn tại. Controller đã được gọi; lỗi xuất phát từ kết quả nghiệp vụ. Đây là 404 hợp lệ cho một endpoint tồn tại và một tài nguyên không có trong hệ thống.

## 2. So sánh dấu hiệu ở từng trường hợp

| Dấu hiệu | 404 do mapping/định tuyến | 404 do nghiệp vụ |
|---|---|---|
| URL có khớp endpoint không? | Không có handler phù hợp với request | Có handler phù hợp |
| Controller method có chạy không? | Không | Có |
| Service nghiệp vụ có được gọi không? | Thông thường không | Thường có |
| Nguyên nhân | Sai path, route chưa đăng ký hoặc điều kiện mapping không khớp | ID/tài nguyên không tồn tại theo dữ liệu nghiệp vụ |
| Cách khắc phục | Sửa URL, HTTP method, mapping hoặc cấu hình route | Kiểm tra ID, dữ liệu hoặc quy tắc nghiệp vụ |
| Mã lỗi API gợi ý | ROUTE_NOT_FOUND | ORDER_NOT_FOUND hoặc RESOURCE_NOT_FOUND |
| Test trọng tâm | Xác nhận không có handler/controller được gọi | Xác nhận đúng handler chạy và service báo không tìm thấy |

Không nên kết luận chỉ dựa vào status code. Response body, exception, handler đã chọn và log của request mới giúp phân biệt được hai nguyên nhân.

## 3. Những điều kiện ảnh hưởng tới việc chọn mapping

Mapping của Spring MVC không chỉ gồm path. Một phương thức có thể khai báo nhiều điều kiện:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    OrderResponse find(@PathVariable long id) {
        // ...
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE)
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        // ...
    }
}
~~~

Spring xét các yếu tố:

- Path: đường dẫn có khớp route hay không.
- Method: GET, POST, PUT, PATCH, DELETE...
- Params: query parameter có mặt hoặc có giá trị theo điều kiện mapping không.
- Headers: header có đáp ứng điều kiện mapping không.
- Consumes: Content-Type của request có được endpoint hỗ trợ không.
- Produces: endpoint có thể tạo representation phù hợp với Accept hay không.

Do đó, một URL trông có vẻ đúng vẫn có thể không được định tuyến như mong đợi nếu method hoặc điều kiện khác sai. Hãy xem toàn bộ annotation ở cấp class và method, không chỉ nhìn path.

### 3.1. Phân biệt 404 với 405, 415 và 406

Không phải mọi lỗi mapping đều phải là 404:

| Status | Ý nghĩa thường gặp | Ví dụ |
|---|---|---|
| 404 Not Found | Không tìm thấy handler hoặc tài nguyên | GET /api/order/42 trong khi route là /api/orders/{id} |
| 405 Method Not Allowed | Path có tồn tại nhưng HTTP method không được hỗ trợ | POST vào endpoint chỉ khai báo GET |
| 415 Unsupported Media Type | Content-Type không được endpoint hỗ trợ | Gửi XML vào endpoint chỉ nhận JSON |
| 406 Not Acceptable | Server không thể tạo representation phù hợp với Accept | Client chỉ chấp nhận media type endpoint không cung cấp |
| 400 Bad Request | Request không hợp lệ hoặc không bind được tham số theo hợp đồng | Path variable không chuyển được sang kiểu số trong route đã khớp |

Một số điều kiện params hoặc headers không thỏa có thể khiến mapping không được chọn và kết quả phụ thuộc cách các HandlerMapping xử lý request. Không suy luận status chỉ từ việc một annotation không khớp; hãy quan sát exception/status thực tế của phiên bản Spring và cấu hình ứng dụng.

## 4. Xử lý 404 do tài nguyên nghiệp vụ không tồn tại

Một cách rõ ràng là dùng exception domain riêng:

~~~java
public class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(long orderId) {
        super("Order " + orderId + " was not found");
    }
}
~~~

Service:

~~~java
@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    OrderResponse findById(long id) {
        Order order = repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
        return OrderResponse.from(order);
    }
}
~~~

Exception advice ánh xạ exception domain sang HTTP:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception) {

        ApiError error = new ApiError(
                "ORDER_NOT_FOUND",
                "The requested order does not exist.");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(error);
    }
}
~~~

Trong ví dụ, mã lỗi ORDER_NOT_FOUND ổn định và thông điệp không phụ thuộc trực tiếp vào exception message. Điều này giúp client nhận biết lỗi nghiệp vụ theo hợp đồng API. Không nên trả stack trace, SQL hoặc chi tiết nội bộ của repository.

Nếu controller tự biểu diễn trường hợp không tìm thấy bằng Optional hoặc ResponseEntity, cũng có thể trả 404 mà không ném exception:

~~~java
@GetMapping("/{id}")
ResponseEntity<OrderResponse> find(@PathVariable long id) {
    return orderService.findOptional(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

Chọn exception domain hay kết quả Optional tùy quy ước ứng dụng. Điều quan trọng là controller chỉ trả 404 khi tài nguyên được yêu cầu thực sự không tồn tại theo hợp đồng.

## 5. Xử lý lỗi do không có mapping

Nếu API cần response JSON thống nhất cho route không tồn tại, có thể xử lý các exception liên quan đến định tuyến hoặc static resource. Với Spring Framework 6.1 trở lên, NoResourceFoundException được dùng khi ResourceHttpRequestHandler không tìm thấy tài nguyên. NoHandlerFoundException biểu diễn trường hợp DispatcherServlet không tìm được handler phù hợp.

Ví dụ ánh xạ riêng:

~~~java
@RestControllerAdvice
class RoutingExceptionHandler {

    @ExceptionHandler(NoHandlerFoundException.class)
    ResponseEntity<ApiError> noHandler(
            NoHandlerFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ROUTE_NOT_FOUND",
                        "No endpoint matches this request."));
    }

    @ExceptionHandler(NoResourceFoundException.class)
    ResponseEntity<ApiError> noResource(
            NoResourceFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "RESOURCE_PATH_NOT_FOUND",
                        "The requested resource was not found."));
    }
}
~~~

Các kiểu exception và hành vi dispatch phụ thuộc phiên bản Spring MVC. NoResourceFoundException có từ Spring Framework 6.1. Với phiên bản cũ hơn, việc biến trường hợp không có handler thành exception có thể phụ thuộc cấu hình DispatcherServlet như throwExceptionIfNoHandlerFound. Kiểm tra phiên bản framework và cấu hình thực tế trước khi viết advice; không sao chép handler cho một exception mà phiên bản dự án không có.

Trong một số ứng dụng, response lỗi mặc định đã được chuẩn hóa bởi Spring Boot ErrorController hoặc cấu hình lỗi riêng. Khi đó không cần thêm advice chỉ để thay đổi mọi 404. Hãy chỉ thêm handler riêng nếu API contract yêu cầu mã lỗi hoặc body thống nhất.

Không nên bắt mọi Exception rồi trả 404. Lỗi database, lỗi lập trình, timeout hoặc dependency unavailable không có nghĩa route hay tài nguyên không tồn tại. Ánh xạ sai exception làm mất thông tin và khiến client không thể quyết định có nên thử lại.

## 6. Kiểm thử 404 do mapping không khớp

Với Spring MVC, MockMvc có thể gửi request tới URL không được controller khai báo. Test nên xác nhận status 404 và bảo đảm service nghiệp vụ không được gọi.

Ví dụ test slice:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsNotFoundWhenNoControllerMappingMatches() throws Exception {
        mockMvc.perform(get("/api/order/42"))
                .andExpect(status().isNotFound());

        then(orderService).shouldHaveNoInteractions();
    }
}
~~~

Test gọi /api/order/42 trong khi controller khai báo /api/orders/{id}. Controller method không được thực thi, do đó service không có tương tác. Nếu ứng dụng có resource handler hoặc error advice riêng, body có thể khác; test cần kiểm tra đúng error contract đang được công bố.

Một trường hợp khác là route đúng path nhưng sai method:

~~~java
@Test
void distinguishesUnsupportedMethodFromMissingPath() throws Exception {
    mockMvc.perform(post("/api/orders/42"))
            .andExpect(status().isMethodNotAllowed());
}
~~~

Ví dụ này giả định controller chỉ khai báo GET cho path đó và không có handler POST khác. Nếu ứng dụng có route POST, kết quả đương nhiên sẽ khác. Test phải dựa trên toàn bộ mapping thực tế.

## 7. Kiểm thử 404 do nghiệp vụ

Với trường hợp tài nguyên không tồn tại, test cần chứng minh request đã được định tuyến đúng và exception domain được ánh xạ:

~~~java
@Test
void returnsOrderNotFoundWhenMappedHandlerCannotFindOrder() throws Exception {
    given(orderService.findById(999L))
            .willThrow(new OrderNotFoundException(999L));

    mockMvc.perform(get("/api/orders/999")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound())
            .andExpect(handler().handlerType(OrderController.class))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));

    then(orderService).should().findById(999L);
}
~~~

Assertion handler type xác nhận Spring đã chọn OrderController. Service được gọi với ID 999 và exception domain được ánh xạ thành response 404. Điều này khác hoàn toàn test URL sai ở phần trước.

Nếu service trả Optional.empty() thay vì ném exception, test cấu hình mock trả empty và kiểm tra response theo cách tương tự. Không nên mock service để ném NoHandlerFoundException trong test nghiệp vụ; exception đó thuộc tầng định tuyến, không phải kết quả tìm kiếm đơn hàng.

## 8. Viết test chứng minh hai loại 404 khác nhau

Có thể đặt hai test cạnh nhau để hợp đồng được thể hiện rõ:

~~~java
@Test
void unknownRouteDoesNotInvokeOrderService() throws Exception {
    mockMvc.perform(get("/api/unknown-route"))
            .andExpect(status().isNotFound());

    then(orderService).shouldHaveNoInteractions();
}

@Test
void unknownOrderInvokesMappedHandlerAndReturnsDomainCode()
        throws Exception {
    given(orderService.findById(999L))
            .willThrow(new OrderNotFoundException(999L));

    mockMvc.perform(get("/api/orders/999"))
            .andExpect(status().isNotFound())
            .andExpect(handler().handlerType(OrderController.class))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));

    then(orderService).should().findById(999L);
}
~~~

Test đầu chứng minh request không tới service. Test thứ hai chứng minh request đã vào controller và nhận mã lỗi nghiệp vụ. Cả hai đều trả 404 nhưng bảo vệ hai hợp đồng khác nhau.

Nếu ứng dụng chuẩn hóa route error thành JSON với mã ROUTE_NOT_FOUND, bổ sung assertion mã lỗi ở test đầu. Nếu response route được xử lý bởi ErrorController mặc định, kiểm tra body tương ứng với cấu hình ứng dụng thay vì giả định có trường code.

## 9. Chẩn đoán khi thấy 404 trên môi trường thật

Khi một endpoint bất ngờ trả 404, hãy lần lượt kiểm tra:

1. Request có tới đúng host, port, context path và servlet path không?
2. HTTP method có đúng không?
3. Path có đúng prefix, pluralization, version và path variable không?
4. Mapping có điều kiện params, headers, consumes hoặc produces không?
5. Controller có được component scan hoặc đăng ký vào application context không?
6. Có profile hoặc conditional configuration làm bean/route không được đăng ký không?
7. Có gateway, reverse proxy hoặc ingress rewrite path trước khi request tới ứng dụng không?
8. Security có cố ý che giấu tài nguyên bằng 404 không?
9. Nếu handler đã chạy, service/repository có thực sự không tìm thấy tài nguyên không?
10. Exception nào hoặc error handler nào đã tạo response cuối?

Đặc biệt, URL trong browser hoặc client có thể khác URL mà ứng dụng nhận được vì context path, proxy prefix hoặc rewrite rule. Log request URI tại tầng server và đối chiếu với route mapping sẽ giúp xác định lỗi nằm ở client, gateway hay Spring MVC.

## 10. Kiểm tra mapping được đăng ký trong ApplicationContext

Khi nghi ngờ controller không được đăng ký, có thể kiểm tra mapping trong context hoặc dùng endpoint actuator nếu ứng dụng bật và bảo vệ endpoint đó phù hợp.

Trong test, có thể inject RequestMappingHandlerMapping để xem các mapping annotation-based:

~~~java
@Autowired
RequestMappingHandlerMapping handlerMapping;

@Test
void registersOrderLookupMapping() {
    boolean found = handlerMapping.getHandlerMethods()
            .keySet()
            .stream()
            .anyMatch(info ->
                    info.getPatternValues()
                            .contains("/api/orders/{id}"));

    assertThat(found).isTrue();
}
~~~

API lấy pattern có thể khác giữa phiên bản Spring MVC cũ và mới; với phiên bản cũ có thể cần dùng API pattern condition tương ứng. Đây là test cấu hình mapping, không thay thế request test. Mapping có thể được đăng ký nhưng vẫn không khớp vì method, params, headers hoặc media type.

Nếu dùng functional routing, mapping không nhất thiết xuất hiện trong RequestMappingHandlerMapping. Hãy kiểm tra RouterFunction bean hoặc gửi request qua test client để xác nhận route functional.

## 11. Gateway và reverse proxy có thể tạo 404 trước khi request tới Spring

Một response 404 không nhất thiết được tạo bởi ứng dụng Spring. Gateway, API management, ingress hoặc reverse proxy có thể trả 404 khi:

- Route host không được cấu hình.
- Prefix path bị rewrite hoặc không khớp.
- Service đích không được đăng ký.
- Request đi tới sai base path hoặc version.
- Gateway cố tình che giấu endpoint hoặc service.

Trong trường hợp này, Spring có thể không nhận được request nên log ứng dụng không có access log tương ứng. Hãy đối chiếu request ID/correlation ID giữa gateway và ứng dụng, kiểm tra response header hoặc error body do hạ tầng tạo và xem access log tại từng tầng.

Không sửa controller chỉ vì client nhìn thấy 404. Nếu request chưa tới ứng dụng, thay đổi mapping trong Spring không giải quyết được route ở gateway.

## 12. Security có thể cố ý trả 404

Một số hệ thống không muốn tiết lộ tài nguyên có tồn tại hay không cho người gọi không đủ quyền. Security layer có thể trả 404 thay vì 403 để che giấu sự tồn tại của tài nguyên. Khi đó 404 không phải lỗi mapping và cũng không nhất thiết là tài nguyên thực sự không tồn tại.

Ví dụ, user không được phép xem đơn hàng của tenant khác có thể nhận 404 theo chính sách bảo mật. Test cần xác nhận hành vi này một cách có chủ đích:

- User cùng tenant và có quyền: trả 200 khi đơn hàng tồn tại.
- User cùng tenant nhưng đơn hàng không tồn tại: trả 404.
- User khác tenant: trả 404 nếu chính sách yêu cầu che giấu tài nguyên.

Không nên thay 404 thành 403 chỉ vì muốn phân biệt kỹ thuật nếu hợp đồng bảo mật yêu cầu không tiết lộ sự tồn tại. Ngược lại, nếu API công bố rõ quyền truy cập và tài nguyên, 403 có thể phù hợp hơn. Quyết định phải theo security contract của ứng dụng.

## 13. Thiết kế mã lỗi và log để dễ phân biệt

Nếu API cần phân biệt hai loại 404, có thể dùng mã lỗi ổn định:

| Code | Ý nghĩa | Nguồn |
|---|---|---|
| ROUTE_NOT_FOUND | Không có endpoint phù hợp | Dispatcher/handler mapping |
| RESOURCE_PATH_NOT_FOUND | Resource handler không tìm thấy file tĩnh | ResourceHttpRequestHandler |
| ORDER_NOT_FOUND | Endpoint hợp lệ nhưng không có đơn hàng tương ứng | Service/domain |
| CUSTOMER_NOT_FOUND | Endpoint hợp lệ nhưng không có khách hàng tương ứng | Service/domain |

Không bắt buộc mọi API phải dùng đủ các mã trên. Chỉ công bố các mã thực sự có ý nghĩa với client. Nếu client không cần biết chi tiết, có thể dùng một mã NOT_FOUND chung trong response nhưng vẫn phân loại nguyên nhân ở log/metric nội bộ.

Khi ghi log:

- Ghi method, URI đã chuẩn hóa, status, correlation ID và loại lỗi.
- Phân biệt route miss với domain not found trong metric để phát hiện sai URL hoặc client cũ.
- Không ghi token, dữ liệu cá nhân hoặc toàn bộ query nhạy cảm.
- Không ghi stack trace cho mọi 404 thông thường nếu không có lỗi bất thường.
- Giữ exception gốc ở log nội bộ khi cần điều tra lỗi cấu hình.

Một lượng lớn route miss có thể chỉ ra client gọi sai API version hoặc bot dò đường dẫn. Một lượng lớn ORDER_NOT_FOUND có thể là client gửi ID cũ, dữ liệu bị xóa hoặc luồng đồng bộ có vấn đề. Hai metric có ý nghĩa vận hành khác nhau.

## 14. Những lỗi chẩn đoán thường gặp

| Nhận định sai | Vì sao sai | Cách xác minh |
|---|---|---|
| Mọi 404 đều là controller không có mapping | Controller có thể đã chạy và service không tìm thấy dữ liệu | Kiểm tra handler và tương tác service |
| Mọi 404 đều do ID không tồn tại | Path hoặc HTTP method có thể không khớp | Kiểm tra mapping và request thực tế |
| 404 có nghĩa service đã trả null | Service có thể chưa được gọi | Verify mock/service interaction hoặc trace |
| URL đúng nên mapping chắc chắn khớp | Mapping còn phụ thuộc method, params, headers, consumes và produces | Đọc toàn bộ RequestMapping conditions |
| POST sai method chắc chắn là 404 | Nếu path có mapping GET, Spring thường trả 405 | Kiểm tra method exception/status |
| 404 luôn do Spring tạo | Gateway, ingress hoặc security có thể tạo response trước controller | Đối chiếu log ở từng tầng |
| Bật NoHandlerFoundException sẽ sửa mọi 404 | Domain not found và resource handler là các đường lỗi khác | Kiểm tra exception cụ thể và phiên bản Spring |
| Nên bắt mọi exception rồi trả 404 | Có thể che lỗi server hoặc dependency | Ánh xạ exception cụ thể |
| Advice không chạy nghĩa là controller không tồn tại | Exception có thể được xử lý ở resolver hoặc tầng khác trước advice mong đợi | Kiểm tra exception resolver, advice order và trace |

## 15. Quy trình kiểm thử và xử lý một lỗi 404

Khi thêm endpoint hoặc điều tra lỗi 404, làm theo trình tự:

1. Xác định URL, method, context path và request headers mà server thực sự nhận.
2. Kiểm tra mapping có được đăng ký trong context hay không.
3. Kiểm tra toàn bộ điều kiện mapping, không chỉ path.
4. Xác nhận request đã chọn handler nào.
5. Nếu không có handler phù hợp, kiểm tra NoHandlerFoundException hoặc resource handler/error response theo phiên bản Spring.
6. Nếu controller đã chạy, kiểm tra service/repository và exception domain.
7. Viết một test cho route miss và một test cho domain not found.
8. Xác nhận status, error code, handler và service interaction phù hợp.
9. Nếu ứng dụng đứng sau gateway/security, kiểm tra response ở từng tầng.
10. Giữ log và metric phân biệt nguyên nhân nếu vận hành cần theo dõi riêng.

## 16. Kết luận

404 do thiếu mapping và 404 do nghiệp vụ có thể giống nhau ở status nhưng khác nhau ở nơi phát sinh. Khi Spring không tìm được handler phù hợp, controller nghiệp vụ không chạy. Khi endpoint đã khớp và controller gọi service nhưng tài nguyên không tồn tại, 404 là kết quả của nghiệp vụ. Static resource handler, security layer hoặc gateway còn có thể tạo những response 404 khác.

Hãy chẩn đoán theo đường đi của request: request có tới Spring không, HandlerMapping chọn handler nào, controller có chạy không, service có được gọi không và exception/error handler nào tạo response. Trong test, kết hợp assertion status với handler type, service interaction và error code để bảo vệ rõ hai hợp đồng. Nhờ vậy, lỗi route được sửa ở cấu hình hoặc client, còn lỗi tài nguyên được xử lý theo quy tắc domain.
