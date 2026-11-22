# Mẫu Front Controller và điểm tiếp nhận tập trung

Trong ứng dụng web, nhiều request có thể cần dùng chung các bước như xác định người dùng, kiểm tra quyền truy cập, ghi log, chọn ngôn ngữ, xử lý lỗi và chuẩn bị phản hồi. Nếu mỗi trang hoặc mỗi Controller tự thực hiện các bước này, mã nguồn dễ bị lặp và cách xử lý giữa các endpoint có thể không nhất quán.

**Front Controller** là mẫu thiết kế đặt một điểm tiếp nhận tập trung trước các chức năng xử lý request cụ thể. Điểm tiếp nhận này nhận request, thực hiện hoặc phối hợp các xử lý dùng chung, xác định handler phù hợp rồi chuyển request đến handler đó. Handler chuyên biệt xử lý chức năng tương ứng, còn Front Controller tập trung vào luồng giao tiếp chung.

Trong kiến trúc **Model–View–Controller (MVC)** trên web, Front Controller thường là cổng vào của tầng web. Nó không thay thế Model, View hay các Controller xử lý từng chức năng. Mục tiêu là thống nhất cách request đi vào ứng dụng và cách kết quả được trả về, trong khi vẫn giữ trách nhiệm của từng chức năng rõ ràng.

## 1. Vấn đề khi mỗi trang tự tiếp nhận request

Hãy hình dung một hệ thống có các chức năng xem sản phẩm, tạo đơn hàng, xem hồ sơ và quản lý tài khoản. Nếu mỗi Servlet hoặc endpoint tự xử lý toàn bộ quy trình tiếp nhận, mã nguồn có thể trông như sau:

~~~java
public class ProductServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response
    ) throws IOException {
        // Tự kiểm tra đăng nhập.
        // Tự ghi log và chọn ngôn ngữ.
        // Tự xử lý lỗi.
        // Tải sản phẩm và hiển thị trang.
    }
}

public class OrderServlet extends HttpServlet {
    @Override
    protected void doPost(
            HttpServletRequest request,
            HttpServletResponse response
    ) throws IOException {
        // Lặp lại kiểm tra đăng nhập.
        // Lặp lại ghi log và chọn ngôn ngữ.
        // Lặp lại xử lý lỗi.
        // Tạo đơn hàng và trả phản hồi.
    }
}
~~~

Khi số lượng endpoint tăng, các vấn đề thường xuất hiện:

- Cùng một bước xác thực hoặc ghi log được viết ở nhiều nơi.
- Mỗi endpoint xử lý lỗi theo một cách khác nhau.
- Việc thay đổi quy tắc chung đòi hỏi sửa nhiều lớp.
- Khó bảo đảm mọi request đều đi qua cùng chính sách bảo mật.
- Luồng request không có một điểm dễ quan sát để đo thời gian, gắn mã tương quan hoặc thu thập thông tin chẩn đoán.

Front Controller gom phần tiếp nhận chung vào một nơi. Các handler riêng vẫn chịu trách nhiệm cho từng chức năng.

## 2. Front Controller là gì?

Front Controller là một thành phần đứng trước các handler của ứng dụng và tiếp nhận các request thuộc phạm vi được cấu hình. Sau khi nhận request, nó thường thực hiện các bước:

1. Tạo hoặc lấy ngữ cảnh request như mã tương quan, thông tin người dùng và locale.
2. Áp dụng các xử lý chung ở tầng web hoặc phối hợp với filter/interceptor.
3. Xác định handler dựa trên đường dẫn, HTTP method và các điều kiện định tuyến.
4. Chuyển request cùng dữ liệu đã được chuẩn bị đến handler.
5. Nhận kết quả hoặc lỗi từ handler.
6. Chuyển kết quả thành View, JSON, redirect hoặc HTTP response.

Front Controller là điểm tiếp nhận tập trung, không phải một lớp phải chứa toàn bộ nghiệp vụ của ứng dụng. Nó có thể ủy quyền cho bộ định tuyến, bộ ánh xạ handler, bộ xử lý lỗi, bộ phân giải View và các Controller chuyên biệt.

~~~mermaid
flowchart TD
    B[Trình duyệt / API client] --> F[Front Controller]
    F --> C[Ngữ cảnh và xử lý chung]
    C --> R[Handler Mapping / Router]
    R --> H1[Product Controller]
    R --> H2[Order Controller]
    R --> H3[Profile Controller]
    H1 --> M[Model / Use case]
    H2 --> M
    H3 --> M
    M --> H1
    M --> H2
    M --> H3
    H1 --> O[Response / View]
    H2 --> O
    H3 --> O
    O --> F
    F --> B
~~~

Sơ đồ mô tả vai trò ở mức khái quát. Trong một framework, handler mapping, adapter và view resolver có thể là các thành phần riêng. Không nhất thiết tất cả phải nằm trong cùng một lớp Front Controller.

## 3. Front Controller phối hợp với MVC như thế nào?

Ba vai trò MVC vẫn giữ ý nghĩa riêng:

| Thành phần | Trách nhiệm trong ứng dụng web |
|---|---|
| **Model** | Quản lý trạng thái và quy tắc nghiệp vụ; cung cấp dữ liệu hoặc kết quả use case |
| **View** | Trình bày dữ liệu thành HTML hoặc định dạng phản hồi phù hợp |
| **Controller chức năng** | Xử lý một nhóm endpoint hoặc thao tác cụ thể; gọi nghiệp vụ và chuẩn bị dữ liệu phản hồi |
| **Front Controller** | Tiếp nhận request tập trung, điều phối định tuyến và các xử lý chung của tầng web |

Ví dụ, request `POST /orders` có thể đi qua Front Controller trước khi được chuyển đến `OrderController`. Front Controller không tự tính tổng tiền hay kiểm tra tồn kho. `OrderController` tiếp nhận dữ liệu biểu mẫu và gọi use case tạo đơn; Model hoặc dịch vụ nghiệp vụ xác định đơn có hợp lệ không.

Điểm cần nhớ là Front Controller là mẫu tổ chức điểm vào của ứng dụng. Nó có thể đứng trước nhiều Controller chức năng, nhưng không làm biến mất các Controller đó.

## 4. Luồng xử lý một request qua Front Controller

Giả sử người dùng gửi request xem chi tiết đơn hàng:

1. Trình duyệt gửi `GET /orders/ORD-1001`.
2. Web server hoặc Servlet container chuyển request đến ứng dụng.
3. Filter chung có thể xử lý CORS, mã tương quan, giới hạn request hoặc xác thực theo cấu hình.
4. Front Controller tiếp nhận request thuộc phạm vi ứng dụng.
5. Router hoặc Handler Mapping tìm handler tương ứng với đường dẫn và HTTP method.
6. Handler được gọi; Controller lấy dữ liệu cần thiết và gọi dịch vụ truy vấn.
7. Model hoặc application service trả về kết quả.
8. Controller chọn View hoặc tạo response JSON.
9. Front Controller hoặc framework phối hợp xử lý kết quả và gửi response về client.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Client as Trình duyệt
    participant Filter as Filter
    participant Front as Front Controller
    participant Map as Handler Mapping
    participant C as OrderController
    participant M as Model / Service
    participant View as View Renderer

    User->>Client: Mở trang chi tiết đơn
    Client->>Filter: GET /orders/ORD-1001
    Filter->>Front: Chuyển request
    Front->>Front: Tạo request context
    Front->>Map: Tìm handler
    Map-->>Front: OrderController.detail
    Front->>C: Gọi handler
    C->>M: getOrderSummary(id)
    M-->>C: OrderSummary
    C-->>Front: View result + dữ liệu
    Front->>View: Render template
    View-->>Front: HTML
    Front-->>Filter: HTTP response
    Filter-->>Client: HTTP response
    Client-->>User: Hiển thị trang
~~~

Đây là một luồng thành công. Khi không tìm thấy handler, hệ thống có thể trả 404; khi HTTP method không được hỗ trợ, có thể trả 405; khi handler phát sinh lỗi, cơ chế xử lý lỗi chung có thể chuyển lỗi thành phản hồi thích hợp.

## 5. Những thành phần thường đứng quanh Front Controller

Trong một ứng dụng web hoàn chỉnh, điểm tiếp nhận tập trung thường phối hợp với nhiều thành phần. Tên gọi cụ thể phụ thuộc framework.

### 5.1. Router hoặc Handler Mapping

Router xác định handler nào chịu trách nhiệm cho request. Việc ánh xạ thường dựa trên:

- HTTP method như GET, POST, PUT, PATCH hoặc DELETE.
- Đường dẫn như `/products/{id}`.
- Content type hoặc `Accept` header khi ứng dụng có nhiều định dạng.
- Điều kiện định tuyến bổ sung do framework hỗ trợ.

Không nên chỉ kiểm tra chuỗi URL một cách tùy tiện. Router cần xử lý rõ đường dẫn, tham số, phương thức HTTP và trường hợp không có route phù hợp.

### 5.2. Handler Adapter

Handler Adapter là thành phần biết cách gọi một loại handler cụ thể. Framework có thể hỗ trợ nhiều kiểu handler khác nhau; adapter giúp Front Controller không cần biết chi tiết cách gọi từng kiểu.

### 5.3. Interceptor

Interceptor có thể chạy trước hoặc sau handler để xử lý những mối quan tâm chung ở mức MVC, chẳng hạn đo thời gian, gắn dữ liệu bổ sung vào model hiển thị hoặc kiểm tra một điều kiện web nhất định. Interceptor thường có hiểu biết về handler hơn filter.

### 5.4. Exception Resolver hoặc Error Handler

Thành phần xử lý lỗi chuyển exception thành phản hồi. Ví dụ:

- Lỗi không tìm thấy tài nguyên thành HTTP 404.
- Lỗi validation thành biểu mẫu có thông báo hoặc HTTP 400.
- Lỗi nghiệp vụ thành thông báo phù hợp hoặc HTTP 409.
- Lỗi không dự kiến thành HTTP 500 cùng mã tương quan để tra log.

### 5.5. View Resolver hoặc Response Renderer

Với ứng dụng trả HTML, View Resolver tìm template dựa trên tên View. Với API, handler có thể trả đối tượng để framework serialize thành JSON hoặc một định dạng khác.

### 5.6. Request Context

Request Context chứa dữ liệu chỉ có ý nghĩa trong một request, chẳng hạn mã tương quan, locale, thông tin principal hoặc metadata đã được xác minh. Dữ liệu request cần được quản lý theo vòng đời request, không đặt trong biến instance dùng chung giữa nhiều request.

## 6. Front Controller và Filter khác nhau thế nào?

Filter và Front Controller đều có thể nằm trên đường đi của request, nhưng vai trò khác nhau.

| Tiêu chí | Servlet Filter | Front Controller |
|---|---|---|
| Vị trí | Bao quanh chuỗi xử lý Servlet | Là điểm tiếp nhận trung tâm của tầng ứng dụng hoặc MVC |
| Mục đích | Xử lý request/response trước hoặc sau Servlet | Định tuyến request đến handler và điều phối phản hồi |
| Hiểu biết về chức năng | Thường không cần biết Controller cụ thể | Thường phối hợp với route hoặc handler mapping |
| Ví dụ | CORS, mã tương quan, nén, xác thực ở tầng web | Chuyển `GET /orders/{id}` đến OrderController |
| Khả năng dừng luồng | Có thể chặn request và tự trả response | Có thể trả lỗi nếu không tìm thấy handler hoặc điều phối không thành công |

Một request có thể đi qua Filter rồi đến Front Controller. Filter không thay thế Router, còn Front Controller không nhất thiết phải tự triển khai mọi chức năng của Filter.

Trong Spring MVC, `DispatcherServlet` là ví dụ điển hình của Front Controller. Nó tiếp nhận request được ánh xạ, phối hợp HandlerMapping, HandlerAdapter, cơ chế xử lý exception và ViewResolver. Spring Security thường tích hợp qua chuỗi Filter trước khi request đến `DispatcherServlet`.

## 7. Ví dụ đơn giản với Jakarta Servlet

Có thể triển khai một Front Controller cơ bản bằng cách ánh xạ một Servlet vào một vùng URL của ứng dụng. Ví dụ sau minh họa ý tưởng; trong dự án thực tế nên dùng framework hoặc cấu trúc router đã được kiểm thử thay vì tự xây bộ định tuyến phức tạp.

### 7.1. FrontControllerServlet tiếp nhận request

~~~java
@WebServlet(urlPatterns = "/app/*")
public class FrontControllerServlet extends HttpServlet {
    private Router router;
    private ViewRenderer viewRenderer;

    @Override
    public void init() throws ServletException {
        router = ApplicationConfig.createRouter();
        viewRenderer = ApplicationConfig.createViewRenderer();
    }

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response
    ) throws ServletException, IOException {
        dispatch(request, response);
    }

    @Override
    protected void doPost(
            HttpServletRequest request,
            HttpServletResponse response
    ) throws ServletException, IOException {
        dispatch(request, response);
    }

    private void dispatch(
            HttpServletRequest request,
            HttpServletResponse response
    ) throws ServletException, IOException {
        String path = request.getPathInfo();
        String method = request.getMethod();

        try {
            RouteMatch match = router.match(method, path);
            if (match == null) {
                response.sendError(HttpServletResponse.SC_NOT_FOUND);
                return;
            }

            HandlerResult result = match.handler().handle(
                    request,
                    match.pathVariables()
            );

            if (!response.isCommitted()) {
                viewRenderer.render(result, request, response);
            }
        } catch (MethodNotAllowedException ex) {
            response.sendError(
                    HttpServletResponse.SC_METHOD_NOT_ALLOWED
            );
        } catch (Exception ex) {
            getServletContext().log(
                    "Unhandled request error",
                    ex
            );
            if (!response.isCommitted()) {
                response.sendError(
                        HttpServletResponse.SC_INTERNAL_SERVER_ERROR
                );
            }
        }
    }
}
~~~

Servlet được ánh xạ vào `/app/*`, nên các request trong vùng đó đi qua cùng một điểm tiếp nhận. `dispatch()` lấy đường dẫn và phương thức HTTP, tìm handler rồi chuyển kết quả sang renderer.

Đoạn mã là skeleton minh họa, không phải router hoàn chỉnh. Một triển khai thực tế cần xử lý chính xác URL context path, trailing slash, query string, encoding, request body, content negotiation, HEAD/OPTIONS, phương thức không được hỗ trợ và các trường hợp response đã được commit. Cũng cần phân biệt 404 với 405 và cung cấp header `Allow` khi thích hợp.

Servlet thường được tạo một lần và xử lý nhiều request đồng thời. Vì vậy, các trường `router` và `viewRenderer` chỉ nên giữ cấu hình hoặc dependency an toàn khi dùng đồng thời; không lưu request, response, user hiện tại hoặc dữ liệu thay đổi theo request trong field của Servlet.

### 7.2. Router ánh xạ request đến handler

Một hợp đồng đơn giản có thể như sau:

~~~java
public interface RequestHandler {
    HandlerResult handle(
            HttpServletRequest request,
            Map<String, String> pathVariables
    ) throws Exception;
}

public record RouteMatch(
        RequestHandler handler,
        Map<String, String> pathVariables
) {}

public interface Router {
    RouteMatch match(String method, String path);
}
~~~

Router chỉ chịu trách nhiệm tìm handler. Nó không nên tự tính giá đơn hàng hoặc truy vấn dữ liệu nghiệp vụ.

### 7.3. Handler chuyên biệt xử lý chức năng

~~~java
public class OrderDetailHandler implements RequestHandler {
    private final OrderQueryService orderQueryService;

    public OrderDetailHandler(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Override
    public HandlerResult handle(
            HttpServletRequest request,
            Map<String, String> pathVariables
    ) {
        String orderId = pathVariables.get("id");
        OrderSummary summary = orderQueryService.getSummary(orderId);

        return HandlerResult.view(
                "orders/detail",
                Map.of("order", summary)
        );
    }
}
~~~

Handler tập trung vào chức năng xem chi tiết đơn hàng. Nó gọi dịch vụ truy vấn và trả kết quả có cấu trúc. Nếu cần phân quyền theo chủ sở hữu đơn, việc kiểm tra phải được thực thi ở phía máy chủ và phù hợp với chính sách ứng dụng.

### 7.4. Kết quả handler có hợp đồng rõ ràng

~~~java
public record HandlerResult(
        String viewName,
        Map<String, Object> model,
        int status
) {
    public static HandlerResult view(
            String viewName,
            Map<String, Object> model
    ) {
        return new HandlerResult(viewName, model, 200);
    }
}
~~~

Đây chỉ là một cách biểu diễn kết quả View đơn giản. Ứng dụng có API JSON hoặc redirect có thể dùng một kiểu kết quả phân biệt rõ các trường hợp, chẳng hạn sealed interface với `ViewResult`, `JsonResult`, `RedirectResult` và `EmptyResult`. Hợp đồng rõ giúp renderer biết cách tạo phản hồi mà không phải suy đoán từ chuỗi tùy ý.

## 8. Định tuyến và xử lý phương thức HTTP

Front Controller cần phối hợp với router để xử lý đúng ý nghĩa của HTTP method.

| Method | Cách dùng thường gặp | Ví dụ |
|---|---|---|
| GET | Đọc tài nguyên, không chủ đích thay đổi trạng thái | `GET /products/42` |
| POST | Tạo tài nguyên hoặc thực hiện một thao tác | `POST /orders` |
| PUT | Thay thế toàn bộ biểu diễn tài nguyên theo hợp đồng API | `PUT /profiles/7` |
| PATCH | Cập nhật một phần tài nguyên | `PATCH /profiles/7` |
| DELETE | Yêu cầu xóa tài nguyên | `DELETE /cart/items/12` |

Không nên định tuyến chỉ theo URL mà bỏ qua method. Ví dụ `GET /orders` và `POST /orders` thường phục vụ hai thao tác khác nhau. Nếu route tồn tại nhưng method không được hỗ trợ, phản hồi 405 phù hợp hơn 404; router nên biết method nào được cho phép.

Với HTML form truyền thống, trình duyệt thường gửi GET hoặc POST. Một số framework hỗ trợ method override để biểu diễn PUT/PATCH/DELETE qua hidden field hoặc header; nếu dùng, cần cấu hình rõ và bảo vệ chống giả mạo request.

## 9. Xử lý lỗi tập trung

Front Controller là nơi thuận tiện để phối hợp một chiến lược xử lý lỗi thống nhất. Nhưng không phải mọi lỗi đều nên bị biến thành cùng một trang 500.

| Tình huống | Phản hồi thường phù hợp |
|---|---|
| Không có route phù hợp | 404 Not Found |
| Có route nhưng method không được hỗ trợ | 405 Method Not Allowed |
| Dữ liệu request sai định dạng | 400 Bad Request hoặc trả lại biểu mẫu |
| Chưa xác thực | 401 Unauthorized hoặc chuyển đến trang đăng nhập theo loại ứng dụng |
| Đã xác thực nhưng không có quyền | 403 Forbidden |
| Xung đột với trạng thái hiện tại | 409 Conflict |
| Lỗi không dự kiến | 500 Internal Server Error |

Lỗi nghiệp vụ nên được biểu diễn bằng kết quả hoặc exception có ý nghĩa trong ứng dụng. Lớp web ánh xạ chúng thành HTTP status, trang lỗi hoặc JSON. Không trả stack trace, SQL hoặc thông tin nội bộ cho client. Log nên có mã tương quan để đội vận hành tìm được request liên quan.

## 10. Bảo mật ở điểm tiếp nhận tập trung

Front Controller có thể giúp thống nhất một số biện pháp bảo mật, nhưng bản thân việc có một điểm vào không bảo đảm ứng dụng an toàn.

### 10.1. Xác thực và phân quyền

Có thể dùng Filter hoặc security framework để xác thực request trước khi gọi handler. Tuy nhiên, quyền truy cập còn có thể phụ thuộc vào tài nguyên cụ thể. Ví dụ, người dùng đã đăng nhập vẫn không được xem đơn hàng của người khác. Kiểm tra quyền theo tài nguyên phải được thực hiện ở phía máy chủ, tại tầng phù hợp.

### 10.2. CSRF và CORS

Với ứng dụng dùng cookie/session để xác thực, các request thay đổi trạng thái cần được bảo vệ CSRF theo cấu hình phù hợp. CORS kiểm soát việc trình duyệt cho phép origin khác truy cập tài nguyên; nó không thay thế xác thực hoặc phân quyền.

### 10.3. Kiểm tra dữ liệu đầu vào

Front Controller có thể phối hợp giới hạn kích thước request, content type và các quy tắc chung. Handler hoặc DTO vẫn cần kiểm tra dữ liệu theo hợp đồng riêng của chức năng. Model phải bảo vệ bất biến nghiệp vụ.

### 10.4. Không tin dữ liệu do client gửi

Không dùng giá, vai trò, quyền hạn hoặc trạng thái do client gửi làm nguồn sự thật. Lấy danh tính từ ngữ cảnh xác thực và xác định các giá trị nhạy cảm ở phía máy chủ.

### 10.5. Tài nguyên tĩnh

Không nhất thiết mọi file CSS, JavaScript, ảnh hoặc font đều phải đi qua Front Controller. Tài nguyên tĩnh thường được phục vụ trực tiếp bởi web server, CDN hoặc static resource handler để tránh chi phí định tuyến và xử lý không cần thiết. Cần cấu hình vùng URL tĩnh rõ ràng để không vô tình bỏ qua chính sách cần thiết hoặc chuyển file tĩnh vào router nghiệp vụ.

## 11. Những việc không nên dồn vào Front Controller

Điểm tiếp nhận tập trung dễ trở thành một lớp quá lớn nếu mọi chức năng đều được đưa vào đó.

Không nên để Front Controller:

- Chứa công thức tính giá, chính sách giảm giá hoặc quy tắc chuyển trạng thái.
- Có một chuỗi `if/else` dài cho từng URL và từng chức năng.
- Trực tiếp truy vấn hoặc cập nhật bảng cơ sở dữ liệu.
- Tạo HTML cho từng trang hoặc biết cấu trúc template cụ thể.
- Giữ dữ liệu người dùng hoặc request trong field dùng chung.
- Trở thành nơi duy nhất chứa mọi logic xác thực và phân quyền tài nguyên.

Hãy ủy quyền cho Router, handler mapping, filter, interceptor, exception handler, Controller chuyên biệt và dịch vụ nghiệp vụ. Front Controller nên làm rõ luồng chung, không hấp thụ trách nhiệm của các thành phần đó.

## 12. Lợi ích và chi phí của mẫu Front Controller

| Lợi ích | Chi phí hoặc đánh đổi |
|---|---|
| Có điểm quan sát tập trung cho request | Điểm vào trở thành thành phần quan trọng cần vận hành ổn định |
| Giảm lặp các bước xử lý chung | Cần thiết kế cơ chế mở rộng và đăng ký handler |
| Định tuyến và xử lý lỗi nhất quán | Router hoặc cấu hình route có thể trở nên phức tạp |
| Dễ tích hợp logging, tracing, locale và context | Xử lý chung quá nhiều có thể làm tăng độ trễ cho mọi request |
| Controller chức năng tập trung vào use case | Cần hiểu rõ thứ tự Filter, Interceptor, handler và renderer |

Front Controller phù hợp khi ứng dụng có nhiều endpoint dùng chung cơ chế tiếp nhận và cần quản lý định tuyến tập trung. Với ứng dụng rất nhỏ chỉ có một vài trang đơn giản, một lớp điều phối riêng có thể chưa tạo đủ giá trị. Framework web hiện đại thường đã cung cấp sẵn mẫu này, nên không cần tự xây lại nếu cơ chế có sẵn đáp ứng yêu cầu.

## 13. Spring MVC: DispatcherServlet là Front Controller

Trong Spring MVC, `DispatcherServlet` là Front Controller của framework. Một request được ánh xạ đến servlet này, sau đó framework phối hợp các thành phần:

1. `HandlerMapping` tìm handler phù hợp.
2. `HandlerAdapter` gọi handler theo kiểu được hỗ trợ.
3. Controller xử lý chức năng và trả kết quả.
4. `HandlerExceptionResolver` có thể xử lý exception phát sinh.
5. `ViewResolver` tìm View nếu handler trả tên View.
6. View được render thành response; với REST controller, dữ liệu có thể được serialize trực tiếp thành JSON.

Một Controller Spring MVC đơn giản:

~~~java
@Controller
@RequestMapping("/products")
public class ProductController {
    private final ProductQueryService productQueryService;

    public ProductController(ProductQueryService productQueryService) {
        this.productQueryService = productQueryService;
    }

    @GetMapping("/{id}")
    public String detail(
            @PathVariable String id,
            Model model
    ) {
        ProductViewData product = productQueryService.getDetail(id);
        model.addAttribute("product", product);
        return "products/detail";
    }
}
~~~

Controller không cần tự đọc socket hoặc tự tìm template. `DispatcherServlet` và các thành phần của Spring MVC phối hợp các bước hạ tầng; Controller tập trung vào chức năng xem sản phẩm.

Với API, có thể dùng:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductApiController {
    private final ProductQueryService productQueryService;

    public ProductApiController(ProductQueryService productQueryService) {
        this.productQueryService = productQueryService;
    }

    @GetMapping("/{id}")
    public ProductViewData detail(@PathVariable String id) {
        return productQueryService.getDetail(id);
    }
}
~~~

Cùng một Front Controller có thể phục vụ Controller trả HTML và Controller trả dữ liệu API. Sự khác nhau nằm ở hợp đồng phản hồi của handler và cơ chế chuyển đổi dữ liệu.

## 14. Kiểm thử Front Controller và định tuyến

Kiểm thử nên bao phủ điểm vào chung và các handler chuyên biệt ở những phạm vi phù hợp.

### Kiểm thử định tuyến

- Đường dẫn và method hợp lệ ánh xạ đến đúng handler.
- Route không tồn tại trả 404.
- Method không được hỗ trợ trả 405 và danh sách method được phép khi cần.
- Path variable được giải mã và chuyển đến handler đúng cách.
- Route cụ thể và route tổng quát không xung đột ngoài dự kiến.

### Kiểm thử xử lý chung

- Mã tương quan được tạo và truyền vào log.
- Locale hoặc request context được thiết lập đúng.
- Exception được ánh xạ thành response phù hợp.
- Filter hoặc interceptor được chạy theo thứ tự đã cấu hình.
- Request bị từ chối bởi chính sách bảo mật không đi tiếp đến handler.

### Kiểm thử Controller chức năng

- Controller chuyển dữ liệu request thành command hoặc query phù hợp.
- Dịch vụ nghiệp vụ được gọi với dữ liệu đúng.
- Kết quả được chuyển thành View, JSON hoặc redirect theo hợp đồng.
- Lỗi nghiệp vụ được phản hồi đúng và không lộ chi tiết nội bộ.

### Kiểm thử tích hợp

Kiểm tra request đi qua toàn bộ chuỗi Filter, Front Controller, handler mapping, Controller, Model và renderer. Các test này giúp phát hiện lỗi cấu hình URL, thứ tự filter, content negotiation và xử lý response mà unit test riêng lẻ có thể bỏ sót.

## 15. Checklist khi thiết kế Front Controller

- [ ] Có một điểm tiếp nhận rõ ràng cho các request thuộc phạm vi ứng dụng.
- [ ] Front Controller ủy quyền định tuyến cho Router hoặc Handler Mapping.
- [ ] Handler chuyên biệt xử lý chức năng riêng.
- [ ] Front Controller không chứa quy tắc nghiệp vụ hoặc truy vấn dữ liệu chức năng.
- [ ] Filter, Interceptor và Front Controller có trách nhiệm phân biệt.
- [ ] HTTP method và trường hợp 404/405 được xử lý rõ.
- [ ] Lỗi được ánh xạ nhất quán mà không lộ chi tiết nội bộ.
- [ ] Xác thực, phân quyền, CSRF và giới hạn request được cấu hình ở vị trí phù hợp.
- [ ] Tài nguyên tĩnh có đường phục vụ phù hợp.
- [ ] Trạng thái theo request không được lưu trong field dùng chung của Servlet.
- [ ] Có kiểm thử route, xử lý chung, handler và luồng tích hợp.

## Kết luận

Front Controller tạo một điểm tiếp nhận tập trung để thống nhất định tuyến, xử lý chung và phản hồi request trong ứng dụng web MVC. Nó phối hợp với Router, Filter, Interceptor, Controller chức năng, bộ xử lý lỗi và View Resolver; mỗi thành phần vẫn giữ trách nhiệm riêng. Mẫu này giúp giảm mã lặp và làm luồng request dễ quan sát, nhưng cần tránh biến điểm vào thành một Controller khổng lồ. Trong Spring MVC, `DispatcherServlet` là ví dụ thực tế của Front Controller: framework đảm nhiệm điều phối hạ tầng, còn Controller chuyên biệt xử lý use case và Model giữ quy tắc nghiệp vụ.
