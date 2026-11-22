# Thiết kế trang lỗi và trạng thái lỗi của thành phần giao diện

Trong module **MODEL_VIEW_CONTROLLER**, lỗi có thể xuất hiện ở nhiều phạm vi: toàn bộ request không được xử lý, người dùng không có quyền mở một trang, một phần dữ liệu không tải được hoặc một thành phần giao diện gặp lỗi khi thực hiện thao tác. Cách ứng dụng trình bày lỗi ảnh hưởng trực tiếp đến khả năng hiểu tình huống và tiếp tục công việc của người dùng. Một trang lỗi tốt cho biết điều gì đã xảy ra, việc nào còn có thể thực hiện và cách khôi phục an toàn. Một trạng thái lỗi tốt của component giúp cô lập sự cố để phần giao diện còn hoạt động vẫn dùng được.

Bài học thuộc chương **Xử lý lỗi**. Trọng tâm là thiết kế hai cấp phản hồi: **trang lỗi của ứng dụng** và **trạng thái lỗi của thành phần giao diện**. Ta sẽ phân loại lỗi, ánh xạ exception và HTTP status, tổ chức fallback cho từng phạm vi, phân biệt loading/empty/error/success, hỗ trợ retry và thao tác phục hồi, rồi xem ví dụ Spring MVC và giao diện web.

## 1. Lỗi có nhiều phạm vi

Không phải mọi lỗi đều cần thay toàn bộ trang. Khi API tải danh sách gợi ý thất bại, phần thông tin tài khoản hoặc nội dung chính vẫn có thể hoạt động. Ngược lại, khi request không tìm thấy route hoặc người dùng không được phép truy cập tài nguyên, ứng dụng cần một phản hồi ở cấp trang hoặc cấp request.

Có thể phân loại theo phạm vi ảnh hưởng:

| Phạm vi | Ví dụ | Cách phản hồi phù hợp |
|---|---|---|
| Toàn ứng dụng / hạ tầng | Server bảo trì, database không khả dụng | Trang 500/503 hoặc thông báo bảo trì |
| Request / route | URL không tồn tại, method không hỗ trợ | Trang 404/405 |
| Quyền truy cập | Chưa đăng nhập, không có quyền | Trang đăng nhập hoặc 401/403 |
| Use case | Không thể hủy đơn đã giao, dữ liệu xung đột | Trang hoặc thông báo theo ngữ cảnh, thường 409 |
| Form | Email sai định dạng, trường bắt buộc còn trống | Lỗi cạnh trường và tóm tắt lỗi |
| Component | Widget biểu đồ hoặc bảng gợi ý không tải được | Fallback tại component, nút thử lại |
| Tác vụ nền | Export thất bại sau khi đã tiếp nhận | Trạng thái job FAILED và hành động tiếp theo |

Phạm vi hiển thị nên gần nơi người dùng cần xử lý nhất. Lỗi của một widget không nên làm mất cả trang nếu widget đó độc lập. Nhưng không nên cố cô lập lỗi khi dữ liệu bị lỗi là điều kiện bắt buộc để thực hiện tác vụ chính; khi đó cần ngăn thao tác và giải thích rõ.

### 1.1. Phân biệt lỗi kỹ thuật và lỗi có thể xử lý

Lỗi kỹ thuật là sự cố như timeout, mất kết nối, lỗi truy vấn hoặc exception ngoài dự kiến. Lỗi có thể xử lý theo nghiệp vụ là trường hợp hệ thống hiểu request nhưng không thể thực hiện do trạng thái hiện tại, chẳng hạn đơn hàng đã giao nên không thể hủy.

Người dùng không cần biết stack trace hay tên class exception. Họ cần biết:

- Thao tác nào chưa hoàn tất.
- Dữ liệu nào đã được lưu hoặc chưa được lưu.
- Có thể thử lại, sửa dữ liệu, đăng nhập lại hay liên hệ hỗ trợ không.
- Có cần tải lại trang để lấy trạng thái mới nhất không.

Thông tin kỹ thuật chi tiết thuộc log và công cụ quan sát của đội vận hành. Thông tin hướng dẫn người dùng thuộc trang lỗi hoặc component state.

## 2. Trang lỗi cấp ứng dụng

Trang lỗi cấp ứng dụng xuất hiện khi request không thể tiếp tục theo luồng bình thường hoặc khi không có một vùng giao diện nhỏ nào có thể xử lý tình huống. Trang cần giữ nhận diện và bố cục cơ bản của sản phẩm để người dùng biết họ vẫn ở đúng ứng dụng.

Một trang lỗi thường có:

- Tiêu đề ngắn, diễn đạt tình huống.
- Mã trạng thái hoặc mã tham chiếu nếu hữu ích.
- Giải thích ở mức người dùng có thể hiểu.
- Hành động tiếp theo phù hợp, ví dụ quay về trang chủ, đăng nhập, thử tải lại hoặc liên hệ hỗ trợ.
- Liên kết điều hướng rõ ràng.
- Mã tương quan (correlation ID) để hỗ trợ có thể tra log khi cần.

Không cần đưa mọi thông tin này lên mọi trang. Ví dụ, trang 404 có thể chỉ cần nói không tìm thấy trang và cung cấp liên kết về danh sách; trang 503 có thể nói dịch vụ tạm thời không khả dụng và gợi ý thử lại sau.

### 2.1. Các trang lỗi thường gặp

| HTTP status | Ý nghĩa | Nội dung UI gợi ý |
|---|---|---|
| 400 Bad Request | Request không hợp lệ hoặc không thể binding | Kiểm tra dữ liệu gửi lên hoặc quay lại form |
| 401 Unauthorized | Chưa có thông tin xác thực hợp lệ | Đăng nhập lại |
| 403 Forbidden | Đã xác thực nhưng không được phép | Giải thích quyền truy cập và hướng liên hệ |
| 404 Not Found | Không tìm thấy route hoặc tài nguyên | Kiểm tra URL hoặc quay về trang phù hợp |
| 405 Method Not Allowed | Path có tồn tại nhưng method không được hỗ trợ | Trở lại trang trước hoặc dùng thao tác đúng |
| 409 Conflict | Xung đột với trạng thái hiện tại | Tải lại dữ liệu và thử thao tác phù hợp |
| 413 Content Too Large | Request hoặc tệp vượt giới hạn | Chọn tệp nhỏ hơn |
| 415 Unsupported Media Type | Kiểu nội dung gửi lên không được hỗ trợ | Gửi định dạng được chấp nhận |
| 422 Unprocessable Content | Nội dung đúng cú pháp nhưng không thỏa quy tắc | Sửa các trường được chỉ ra |
| 429 Too Many Requests | Gửi quá nhiều request trong khoảng thời gian | Chờ theo hướng dẫn rồi thử lại |
| 500 Internal Server Error | Lỗi server ngoài dự kiến | Thông báo sự cố và mã tham chiếu |
| 502 Bad Gateway | Gateway nhận phản hồi không hợp lệ từ upstream | Thử lại sau hoặc liên hệ hỗ trợ |
| 503 Service Unavailable | Dịch vụ tạm thời không sẵn sàng | Thử lại sau, có thể hiển thị thời gian bảo trì |
| 504 Gateway Timeout | Upstream phản hồi quá chậm | Kiểm tra trạng thái trước khi gửi lại thao tác |

Status code cần phản ánh bản chất lỗi theo hợp đồng HTTP. Không nên trả 200 cho một trang báo lỗi chỉ để tránh xử lý status ở client; điều đó làm monitoring, cache và client hiểu sai kết quả.

### 2.2. 401 và 403 không giống nhau

401 biểu thị request chưa được xác thực hợp lệ. Với ứng dụng HTML, server có thể redirect người dùng đến trang đăng nhập; với API, thường trả 401 cùng cơ chế challenge phù hợp.

403 biểu thị server hiểu danh tính nhưng từ chối quyền truy cập. Trang có thể giải thích rằng tài khoản hiện tại không được phép thực hiện thao tác và hướng dẫn liên hệ quản trị viên.

Không redirect vòng lặp về trang đăng nhập khi người dùng đã đăng nhập nhưng không có quyền. Điều đó làm che giấu nguyên nhân và tạo trải nghiệm khó hiểu.

### 2.3. 404 có thể áp dụng cho cả route và tài nguyên

Route không tồn tại và tài nguyên không tồn tại đều có thể trả 404. Một số ứng dụng cũng cố ý trả 404 thay cho 403 để không tiết lộ sự tồn tại của tài nguyên mà người dùng không được phép xem. Nếu dùng chính sách này, cần áp dụng nhất quán để tránh rò rỉ qua khác biệt phản hồi.

Trang 404 nên tránh khẳng định người dùng đã xóa tài nguyên nếu hệ thống chỉ biết rằng không tìm thấy nó. Nội dung nên trung lập: “Không tìm thấy trang hoặc tài nguyên bạn yêu cầu”.

### 2.4. 500 và 503 cần thông điệp khác nhau

500 thường là lỗi ngoài dự kiến khi server xử lý request. Người dùng nên nhận thông báo chung, mã tham chiếu và hướng tiếp tục an toàn.

503 phù hợp khi dịch vụ tạm thời không thể đáp ứng, ví dụ bảo trì hoặc quá tải có chủ đích. Nếu biết thời gian dự kiến, có thể thông báo; nếu không, không tự bịa thời gian khôi phục. Header Retry-After có thể hướng dẫn client khi nào nên thử lại.

## 3. Nguyên tắc thiết kế nội dung trang lỗi

Trang lỗi nên trung thực, ngắn gọn và hướng người dùng đến hành động tiếp theo.

### 3.1. Nêu rõ tình huống và hành động tiếp theo

Một số ví dụ:

| Tình huống | Thông báo phù hợp | Hành động |
|---|---|---|
| Không tìm thấy trang | “Trang này không tồn tại hoặc đã được chuyển.” | Về trang chủ / danh sách |
| Phiên đăng nhập hết hạn | “Phiên làm việc đã hết hạn.” | Đăng nhập lại |
| Không có quyền | “Tài khoản hiện tại không có quyền xem nội dung này.” | Quay lại / liên hệ quản trị viên |
| Lỗi server | “Chúng tôi chưa thể xử lý yêu cầu này.” | Thử lại sau, gửi mã tham chiếu cho hỗ trợ |
| Dữ liệu xung đột | “Thông tin đã thay đổi ở nơi khác.” | Tải dữ liệu mới và xem lại |
| Dịch vụ bảo trì | “Dịch vụ tạm thời không khả dụng.” | Thử lại sau |

Tránh các thông báo như “Something went wrong” mà không có ngữ cảnh hoặc hành động. Cũng tránh đổ lỗi cho người dùng như “Bạn đã làm sai”.

### 3.2. Giữ điều hướng có ích

Trang lỗi có thể giữ header và footer chung nếu chúng vẫn hoạt động và không phụ thuộc vào dịch vụ đang lỗi. Tuy nhiên, nếu layout chính cũng gây lỗi, cần một layout tối giản độc lập để tránh vòng lặp render.

Các liên kết như trang chủ, danh sách, trợ giúp hoặc đăng nhập nên trỏ đến đích thực sự có sẵn. Không hiển thị nút “Thử lại” nếu thao tác không thể retry hoặc có thể gây tác dụng phụ trùng lặp.

### 3.3. Không làm mất dữ liệu người dùng

Với lỗi form hoặc lỗi một thao tác cập nhật, hãy giữ dữ liệu hợp lệ đã nhập để người dùng không phải điền lại. Không tự động xóa bản nháp khi server trả lỗi.

Với lỗi cấp trang xảy ra sau một thao tác ghi, không nên giả định thao tác chưa được thực hiện. Ví dụ, server có thể đã lưu đơn hàng nhưng response bị mất do mạng. Trước khi cho phép gửi lại, cần kiểm tra trạng thái hoặc dùng idempotency key để tránh tạo đơn trùng.

## 4. Trạng thái lỗi của component giao diện

Một component thường có vòng đời dữ liệu riêng. Ví dụ, bảng giao dịch có thể tải dữ liệu khi trang mở, nhận filter mới, refresh hoặc phân trang. Component nên biểu diễn các trạng thái riêng thay vì chỉ có một boolean isLoading.

Một state model cơ bản:

| Trạng thái | Ý nghĩa | UI |
|---|---|---|
| idle | Chưa bắt đầu hoặc chưa có yêu cầu | Placeholder hoặc hướng dẫn |
| loading | Đang lấy dữ liệu | Skeleton hoặc spinner |
| success | Có dữ liệu hợp lệ | Nội dung chính |
| empty | Request thành công nhưng không có kết quả | Empty state và gợi ý thay đổi bộ lọc |
| error | Request thất bại | Thông báo lỗi và hành động phục hồi |
| refreshing | Đang cập nhật dữ liệu đã có | Giữ nội dung cũ và chỉ báo refresh |
| partial | Một phần dữ liệu tải được | Nội dung có sẵn và cảnh báo phần thiếu |

empty không phải error: API trả thành công với danh sách rỗng là kết quả hợp lệ. loading cũng không phải lỗi: đó là trạng thái tạm thời. Phân biệt rõ giúp component không hiển thị thông báo “Có lỗi” khi người dùng chỉ chưa có dữ liệu.

~~~mermaid
stateDiagram-v2
    [*] --> idle
    idle --> loading: Bắt đầu request
    loading --> success: Có dữ liệu
    loading --> empty: Thành công, không có kết quả
    loading --> error: Request thất bại
    success --> refreshing: Tải lại
    refreshing --> success: Cập nhật thành công
    refreshing --> error: Cập nhật lỗi, giữ dữ liệu cũ
    error --> loading: Thử lại
    empty --> loading: Đổi bộ lọc / tải lại
    success --> loading: Thay truy vấn
    partial --> loading: Tải phần còn thiếu
    loading --> partial: Chỉ một phần hoàn tất
~~~

Sơ đồ là mô hình khái niệm. Ứng dụng có thể dùng state khác nhau, nhưng cần định nghĩa rõ chuyển trạng thái nào được phép và dữ liệu nào còn được giữ khi request thất bại.

### 4.1. Tránh dùng một cờ boolean cho mọi trạng thái

Một component có thể có isLoading, hasError, isEmpty, hasData và isRefreshing. Nếu các cờ không được cập nhật cùng lúc, component có thể rơi vào trạng thái mâu thuẫn, ví dụ isLoading và hasError cùng true nhưng không rõ UI nên hiển thị gì.

Một state discriminated union hoặc enum trạng thái rõ ràng giúp tránh nhiều tổ hợp không hợp lệ:

~~~typescript
type LoadState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "empty" }
  | { status: "error"; message: string; retryable: boolean }
  | { status: "refreshing"; data: T };
~~~

Ví dụ TypeScript này minh họa mô hình kiểu dữ liệu. Với framework khác, có thể dùng sealed class, enum kèm dữ liệu hoặc state object tương đương.

### 4.2. Giữ dữ liệu cũ khi refresh thất bại

Khi người dùng refresh một bảng đang hiển thị dữ liệu, nếu request mới thất bại, thường nên giữ nội dung cũ và báo rằng lần cập nhật gần nhất không thành công. Xóa sạch nội dung ngay khi bắt đầu refresh có thể khiến người dùng mất ngữ cảnh.

Ngược lại, nếu người dùng thay đổi filter sang một truy vấn hoàn toàn khác, dữ liệu cũ có thể không còn đại diện cho truy vấn mới. Khi đó cần hiển thị loading hoặc xóa kết quả cũ theo chính sách rõ ràng để tránh nhầm lẫn.

### 4.3. Phân biệt empty state với lỗi

Empty state nên giải thích vì sao không có nội dung và gợi ý bước tiếp theo:

- “Chưa có giao dịch nào trong khoảng thời gian này.”
- “Không tìm thấy sách phù hợp với bộ lọc hiện tại.”
- “Bạn chưa tạo báo cáo nào.”

Có thể cung cấp hành động như xóa bộ lọc, tạo bản ghi đầu tiên hoặc mở hướng dẫn. Không hiển thị nút retry cho một kết quả rỗng hợp lệ trừ khi có lý do tải lại dữ liệu.

## 5. Chọn phạm vi xử lý lỗi: component, trang hay toàn ứng dụng

Lỗi nên được xử lý tại phạm vi nhỏ nhất có thể khôi phục an toàn. Có thể phân chia như sau:

- **Field-level:** lỗi của một trường form, hiển thị cạnh trường.
- **Form-level:** lỗi liên quan nhiều trường hoặc không thể lưu form.
- **Component-level:** widget độc lập gặp lỗi, hiển thị fallback tại chỗ.
- **Page-level:** dữ liệu chính của trang không thể tải hoặc route không truy cập được.
- **Application-level:** exception không được xử lý hoặc lỗi hạ tầng làm request thất bại.

Ví dụ trang dashboard có ba widget: doanh thu, số đơn và hoạt động gần đây. Nếu widget hoạt động gần đây lỗi, hai widget còn lại vẫn có thể hiển thị. Nếu xác thực hết hạn, toàn trang có thể cần chuyển đến login. Nếu API lấy dữ liệu quyền truy cập chính thất bại, không nên tiếp tục render nội dung được bảo vệ dựa trên cache client không đáng tin cậy.

### 5.1. Error boundary và fallback

Trong giao diện dùng component framework, error boundary hoặc cơ chế tương đương có thể bắt lỗi render trong một nhánh UI và hiển thị fallback. Nó không nhất thiết bắt được mọi lỗi bất đồng bộ, lỗi event handler hoặc lỗi server; những lỗi đó cần được xử lý ở nơi phù hợp.

Một component fallback nên:

- Nêu phần nào không thể hiển thị.
- Giữ các phần khác của trang hoạt động.
- Có nút thử lại nếu thao tác có thể retry an toàn.
- Có liên kết hoặc hướng liên hệ khi không thể tự khôi phục.
- Không lặp vô hạn việc render component đang lỗi.

### 5.2. Không nuốt lỗi âm thầm

Một component không nên bắt mọi exception rồi trả về danh sách rỗng như thể request thành công. Điều đó biến lỗi hệ thống thành empty state và khiến người dùng đưa ra quyết định dựa trên dữ liệu thiếu.

Nếu component có thể hoạt động với dữ liệu một phần, cần nói rõ phần nào chưa tải được. Nếu dữ liệu thiếu làm kết quả không còn đáng tin cậy, phải hiển thị lỗi và ngăn hành động phụ thuộc.

## 6. Ánh xạ exception thành HTTP status và UI

Controller không nên tự tạo trang lỗi khác nhau cho từng exception bằng nhiều khối try/catch lặp lại. Một exception handler tập trung có thể chuyển lỗi đã biết thành status và view/response thống nhất.

Ví dụ ánh xạ khái niệm:

| Exception / tình huống | HTTP | HTML MVC | REST API |
|---|---|---|---|
| Binding hoặc validation thất bại | 400 hoặc 422 theo hợp đồng | Trả lại form kèm lỗi | Error body có field violations |
| Chưa xác thực | 401 hoặc redirect login | Redirect login | 401 |
| Không đủ quyền | 403 | Trang 403 | 403 |
| Không tìm thấy tài nguyên | 404 | Trang 404 | 404 |
| Xung đột trạng thái | 409 | Trang/thông báo theo ngữ cảnh | 409 |
| Rate limit | 429 | Trang/thông báo thử lại sau | 429 |
| Exception ngoài dự kiến | 500 | Trang lỗi chung | 500 |
| Dịch vụ tạm ngừng | 503 | Trang bảo trì | 503 |

Status 400 hay 422 cho validation là quyết định hợp đồng API; điều quan trọng là dùng nhất quán. Với form HTML, lỗi validation thường nên render lại form thay vì redirect để giữ field errors và dữ liệu đã nhập.

### 6.1. Xử lý lỗi tập trung trong Spring MVC

Ví dụ dưới đây dùng ControllerAdvice để trả trang lỗi cho các exception đã biết:

~~~java
@ControllerAdvice
public class MvcExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ModelAndView handleNotFound(
        BookNotFoundException exception,
        HttpServletRequest request
    ) {
        var model = new ModelAndView("errors/404");
        model.setStatus(HttpStatus.NOT_FOUND);
        model.addObject("path", request.getRequestURI());
        return model;
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ModelAndView handleForbidden() {
        var model = new ModelAndView("errors/403");
        model.setStatus(HttpStatus.FORBIDDEN);
        return model;
    }

    @ExceptionHandler(Exception.class)
    public ModelAndView handleUnexpected(
        Exception exception,
        HttpServletRequest request
    ) {
        var referenceId = UUID.randomUUID().toString();

        // Ghi exception và referenceId vào log nội bộ.
        var model = new ModelAndView("errors/500");
        model.setStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        model.addObject("referenceId", referenceId);
        return model;
    }
}
~~~

Đây là ví dụ rút gọn. Trong ứng dụng thực tế, logger phải ghi stack trace và correlation ID theo chính sách; không tạo mã tham chiếu ngẫu nhiên mà không liên kết nó với log. Cần tránh handler tổng quát nuốt các exception đặc biệt mà framework hoặc security filter phải xử lý.

Lưu ý: lỗi phát sinh trong Spring Security filter chain thường được xử lý qua AuthenticationEntryPoint và AccessDeniedHandler, vì chúng có thể xảy ra trước khi request đi vào Controller. ControllerAdvice xử lý các exception đi qua cơ chế xử lý của MVC; không nên giả định nó bắt mọi lỗi xác thực/phân quyền.

### 6.2. Xử lý lỗi API riêng

Nếu một ứng dụng có cả HTML và REST, không nên trả HTML page cho client đang mong JSON. Có thể dùng các advice riêng theo package, annotation hoặc media type.

Với Spring Framework hiện đại, ProblemDetail có thể biểu diễn lỗi theo dạng Problem Details:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
        BookNotFoundException exception
    ) {
        var problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Không tìm thấy cuốn sách được yêu cầu"
        );
        problem.setTitle("Không tìm thấy tài nguyên");
        problem.setProperty("code", "BOOK_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
~~~

Response body cần tránh đưa message kỹ thuật hoặc dữ liệu nội bộ. API có thể bổ sung code, field errors, trace reference và các thuộc tính mở rộng đã được tài liệu hóa.

### 6.3. Không chuyển mọi exception thành 404

Nếu handler bắt mọi exception và trả 404, monitoring sẽ không nhận ra lỗi server và client hiểu sai rằng tài nguyên không tồn tại. Chỉ ánh xạ exception có ngữ nghĩa tương ứng. Exception không dự kiến thường cần 500 và log đầy đủ ở server.

## 7. Thiết kế template trang lỗi

Các trang lỗi nên dùng template riêng nhưng tái sử dụng phần giao diện chung khi an toàn. Có thể tổ chức:

~~~text
templates/
  errors/
    400.html
    403.html
    404.html
    405.html
    409.html
    429.html
    500.html
    503.html
  layouts/
    main.html
    error.html
~~~

Một trang 404 tối giản:

~~~html
<main class="error-page" aria-labelledby="error-title">
  <p class="error-code">404</p>
  <h1 id="error-title">Không tìm thấy trang</h1>
  <p>
    Địa chỉ có thể đã thay đổi hoặc trang không còn tồn tại.
  </p>
  <a href="/">Về trang chủ</a>
</main>
~~~

Trang 500 có thể thêm mã tham chiếu:

~~~html
<main class="error-page" aria-labelledby="error-title">
  <p class="error-code">500</p>
  <h1 id="error-title">Chưa thể xử lý yêu cầu</h1>
  <p>Hệ thống gặp sự cố. Bạn có thể thử lại sau.</p>
  <p>Mã tham chiếu: <strong>REF-EXAMPLE</strong></p>
  <a href="/">Về trang chủ</a>
</main>
~~~

Mã REF-EXAMPLE chỉ là chỗ giữ chỗ trong ví dụ. Ứng dụng phải truyền mã tương quan thực tế đã được ghi trong log.

### 7.1. Layout lỗi nên độc lập vừa đủ

Nếu lỗi xảy ra do dữ liệu người dùng, có thể dùng layout chính. Nếu lỗi xảy ra trong chính thành phần layout, ví dụ menu phụ thuộc service đang lỗi, trang lỗi nên có layout đơn giản hơn chỉ gồm logo, thông điệp và liên kết an toàn.

Không để template lỗi gọi lại cùng service đã gây lỗi. Nếu trang 500 cố tải menu động từ database đang ngừng hoạt động, nó có thể lỗi lần thứ hai và không hiển thị được fallback.

### 7.2. Không đưa chi tiết nội bộ vào HTML

Không render:

- Stack trace hoặc tên class exception.
- SQL query và tên bảng.
- Đường dẫn filesystem hoặc cấu hình máy chủ.
- Token, cookie, session ID.
- Nội dung request nhạy cảm.
- Thông tin định danh của người dùng khác.

Những thông tin đó có thể giúp kẻ tấn công hiểu cấu trúc hệ thống. Hãy dùng mã tham chiếu để hỗ trợ tra log nội bộ.

## 8. Trạng thái lỗi trong component: ví dụ thực tế

Xét component danh sách sách gần đây. Component gọi API khi được mount, hiển thị loading, empty, data hoặc error. Người dùng có thể thử tải lại khi request thất bại.

~~~typescript
type Book = {
  id: string;
  title: string;
};

type BooksState =
  | { status: "loading" }
  | { status: "success"; books: Book[] }
  | { status: "empty" }
  | { status: "error"; retryable: boolean };

async function loadBooks(): Promise<Book[]> {
  const response = await fetch("/api/books/recent");

  if (!response.ok) {
    throw new Error("BOOKS_LOAD_FAILED");
  }

  return response.json();
}
~~~

Một reducer có thể điều khiển trạng thái:

~~~typescript
type Action =
  | { type: "LOAD" }
  | { type: "SUCCESS"; books: Book[] }
  | { type: "FAIL"; retryable: boolean };

function reducer(state: BooksState, action: Action): BooksState {
  switch (action.type) {
    case "LOAD":
      return { status: "loading" };

    case "SUCCESS":
      return action.books.length === 0
        ? { status: "empty" }
        : { status: "success", books: action.books };

    case "FAIL":
      return { status: "error", retryable: action.retryable };
  }
}
~~~

UI có thể render theo trạng thái:

~~~typescript
function renderBooks(state: BooksState) {
  switch (state.status) {
    case "loading":
      return renderSkeleton();

    case "empty":
      return renderEmptyMessage("Chưa có sách gần đây.");

    case "success":
      return renderBookList(state.books);

    case "error":
      return renderErrorPanel({
        message: "Không thể tải danh sách sách.",
        showRetry: state.retryable
      });
  }
}
~~~

Ví dụ tập trung vào state model, lược bỏ phần wiring của framework UI. Trong code thực tế, hàm tải cần dispatch LOAD trước request, dispatch SUCCESS khi thành công và FAIL khi lỗi; nút retry gọi lại đúng hàm tải.

### 8.1. Tránh response cũ ghi đè request mới

Giả sử người dùng đổi filter hai lần liên tiếp. Request thứ hai hoàn tất trước, nhưng request đầu tiên trả về sau. Nếu component áp dụng response theo thứ tự đến, kết quả cũ có thể ghi đè kết quả mới.

Có thể dùng request sequence hoặc AbortController:

~~~typescript
let activeController: AbortController | undefined;

async function loadForFilter(filter: string) {
  activeController?.abort();

  const controller = new AbortController();
  activeController = controller;

  try {
    const response = await fetch(
      "/api/books?category=" + encodeURIComponent(filter),
      { signal: controller.signal }
    );

    if (!response.ok) {
      throw new Error("BOOKS_LOAD_FAILED");
    }

    const books = await response.json();

    if (activeController !== controller) {
      return;
    }

    renderResult(books);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return;
    }
    if (activeController === controller) {
      renderError();
    }
  }
}
~~~

Đoạn code minh họa cách hủy request cũ và chỉ áp dụng kết quả của request hiện hành. Ứng dụng cần quản lý controller theo component instance và dọn dẹp khi component unmount.

## 9. Retry và phục hồi an toàn

Nút thử lại hữu ích khi lỗi có khả năng tạm thời, nhưng không phải lỗi nào cũng nên retry.

| Loại lỗi | Retry tự động? | Hành động phù hợp |
|---|---|---|
| Mất kết nối hoặc timeout khi đọc dữ liệu | Có thể, với giới hạn và backoff | Thử lại sau |
| 429 Too Many Requests | Theo Retry-After hoặc backoff | Chờ trước khi thử |
| 500/502/503/504 | Có thể với request đọc hoặc thao tác idempotent | Retry có giới hạn |
| 400/422 validation | Không | Sửa dữ liệu |
| 401 | Không lặp vô hạn | Đăng nhập lại hoặc refresh credential theo chính sách |
| 403 | Không | Kiểm tra quyền |
| 404 | Thường không | Kiểm tra URL hoặc tài nguyên |
| 409 conflict | Không gửi lại dữ liệu cũ ngay | Tải trạng thái mới và giải quyết xung đột |
| POST tạo thanh toán/đơn hàng | Không retry mù | Dùng idempotency key hoặc kiểm tra kết quả trước |

### 9.1. Exponential backoff và jitter

Nếu một dịch vụ đang quá tải, nhiều client retry cùng thời điểm có thể làm tình hình nặng hơn. Exponential backoff tăng khoảng chờ theo từng lần thử; jitter thêm độ lệch ngẫu nhiên để các client không đồng loạt gửi lại.

Ví dụ khoảng chờ có thể tăng từ 1 giây, 2 giây, 4 giây rồi giới hạn ở một mức tối đa. Số lần retry phải hữu hạn. Với 429 hoặc 503, cần tôn trọng Retry-After nếu server cung cấp.

### 9.2. Retry phải xét tính idempotent

GET thường phù hợp retry vì được thiết kế an toàn. PUT và DELETE có ngữ nghĩa idempotent theo HTTP nhưng ứng dụng vẫn cần bảo đảm hiệu ứng thực tế và response theo hợp đồng. POST thường có thể tạo tác dụng phụ mới mỗi lần gửi.

Với thao tác tạo đơn hàng hoặc thanh toán, client có thể gửi idempotency key duy nhất cho ý định đó. Server lưu kết quả theo key và trả cùng kết quả cho request lặp trong phạm vi chính sách. Không tạo key mới mỗi lần retry cùng một ý định.

### 9.3. Không retry lỗi nghiệp vụ

Nếu server trả 409 vì đơn hàng đã giao, retry cùng request không giải quyết được gì. Nếu form trả 422 vì thiếu trường, retry không sửa dữ liệu cũng không có ích. Component nên hướng người dùng đến việc sửa input, tải lại dữ liệu hoặc liên hệ người có quyền.

## 10. Accessibility cho trang lỗi và component lỗi

Lỗi thường làm gián đoạn luồng thao tác, nên thông báo phải dễ nhận biết bằng nhiều cách.

- Dùng heading rõ ràng để trình đọc màn hình nhận ra trang lỗi.
- Đặt focus hợp lý sau điều hướng đến trang lỗi hoặc khi hiển thị lỗi form.
- Dùng vùng thông báo phù hợp như aria-live cho trạng thái component cập nhật bất đồng bộ.
- Không chỉ dùng màu đỏ để biểu thị lỗi; cần văn bản và biểu tượng có nhãn.
- Nút thử lại phải có tên mô tả, ví dụ “Thử tải lại danh sách sách”.
- Không tự động chuyển hướng hoặc refresh liên tục khi lỗi.
- Đảm bảo component lỗi có thể điều hướng bằng bàn phím.
- Nếu lỗi xuất hiện trong modal, quản lý focus và cho phép đóng hoặc khôi phục theo thiết kế.

Ví dụ thông báo component:

~~~html
<section aria-labelledby="books-error-title">
  <h2 id="books-error-title">Không thể tải danh sách sách</h2>
  <p role="status" aria-live="polite">
    Kết nối tạm thời không thành công. Hãy thử lại.
  </p>
  <button type="button">Thử tải lại danh sách sách</button>
</section>
~~~

Khi lỗi xuất hiện ngay sau thao tác người dùng, có thể dùng role="alert" cho thông báo khẩn cần được đọc ngay; không nên dùng alert cho mọi cập nhật nhỏ vì nó có thể làm trình đọc màn hình bị ngắt quãng.

## 11. Logging, correlation ID và bảo vệ thông tin

Trang lỗi là phần người dùng nhìn thấy; log là phần đội phát triển và vận hành dùng để điều tra. Hai kênh cần liên kết được nhưng có nội dung khác nhau.

Nên ghi log:

- Correlation ID hoặc trace ID.
- Thời điểm, route và HTTP method.
- Mã lỗi và exception type.
- User/tenant ID ở dạng được phép ghi log theo chính sách.
- Component hoặc use case liên quan.
- Dependency thất bại, thời gian phản hồi và số lần retry.
- Kết quả xử lý hoặc trạng thái transaction nếu cần điều tra.

Không ghi mật khẩu, access token, cookie, session ID, dữ liệu thanh toán hoặc toàn bộ request body nhạy cảm. Log phải có quyền truy cập, thời hạn lưu và cơ chế che dữ liệu.

Correlation ID có thể được tạo ở gateway hoặc server khi request bắt đầu, gắn vào log xuyên suốt và trả về client như một mã tham chiếu không nhạy cảm. Không dùng chính session ID làm mã tham chiếu công khai.

## 12. Những lỗi thiết kế thường gặp

| Dấu hiệu | Hệ quả | Cách cải thiện |
|---|---|---|
| Mọi lỗi đều chuyển về trang chủ | Người dùng mất ngữ cảnh và không hiểu nguyên nhân | Dùng trang lỗi theo status và phạm vi |
| Trang lỗi luôn trả HTTP 200 | Monitoring và client hiểu sai kết quả | Đặt status code thực tế |
| Trang 500 hiển thị stack trace | Lộ cấu trúc và thông tin nội bộ | Thông báo chung và mã tham chiếu |
| Component lỗi làm sập cả trang | Một widget độc lập ngăn người dùng làm việc khác | Dùng fallback tại component |
| Component lỗi trả danh sách rỗng | Lỗi bị hiểu nhầm thành không có dữ liệu | Phân biệt empty và error |
| Chỉ có boolean isLoading | Có thể tạo trạng thái UI mâu thuẫn | Dùng state machine hoặc trạng thái phân biệt |
| Retry vô hạn | Tăng tải và làm UI chờ mãi | Giới hạn retry, backoff và thông báo |
| Retry POST mù | Tạo đơn hàng hoặc thanh toán trùng | Idempotency key và kiểm tra kết quả |
| Lỗi form làm mất dữ liệu đã nhập | Người dùng phải nhập lại | Giữ dữ liệu an toàn và hiển thị field errors |
| Bắt mọi exception rồi bỏ qua | Lỗi bị che giấu và khó điều tra | Xử lý lỗi dự kiến, log lỗi ngoài dự kiến |
| Thông báo chỉ dựa vào màu sắc | Người dùng khó nhận biết lỗi | Văn bản, biểu tượng và accessibility |
| Fallback gọi lại dependency đang lỗi | Trang lỗi tiếp tục thất bại | Layout lỗi tối giản, ít phụ thuộc |
| Dùng cùng một HTML error page cho REST API | Client JSON không thể xử lý hợp đồng lỗi | Tách HTML và API error response |

## 13. Kiểm thử trang lỗi và component state

Kiểm thử cần xác nhận status code, nội dung, khả năng phục hồi và việc lỗi được cô lập đúng phạm vi.

### 13.1. Kiểm thử trang lỗi

- Route không tồn tại trả 404 và render đúng trang.
- Người dùng chưa đăng nhập được xử lý theo chính sách 401/login.
- Người dùng không có quyền nhận 403 hoặc 404 theo chính sách che giấu.
- Exception ngoài dự kiến trả 500, không lộ stack trace.
- Dịch vụ bảo trì trả 503 và Retry-After nếu có.
- API trả JSON/ProblemDetail thay vì HTML.
- Correlation ID trong response có thể tìm thấy trong log.
- Trang lỗi vẫn hiển thị được khi layout chính phụ thuộc vào service đang lỗi.

### 13.2. Kiểm thử component state

- Loading xuất hiện khi request đang chạy.
- Response thành công với danh sách rỗng hiển thị empty state.
- Response thành công có dữ liệu hiển thị nội dung.
- Request lỗi hiển thị fallback và hành động phù hợp.
- Retry thành công chuyển component về success/empty.
- Refresh lỗi giữ dữ liệu cũ nếu thiết kế yêu cầu.
- Request cũ không ghi đè kết quả của request mới.
- Một component lỗi không làm các component độc lập biến mất.
- Component cleanup hủy request hoặc watcher khi bị tháo.

### 13.3. Kiểm thử accessibility và nội dung

- Heading trang lỗi có cấu trúc đúng.
- Thông báo component được trình đọc màn hình nhận biết.
- Nút retry có tên rõ ràng và dùng được bằng bàn phím.
- Lỗi không chỉ được biểu thị bằng màu.
- Thông báo không chứa dữ liệu nhạy cảm.
- Hành động tiếp theo hoạt động và không tạo request trùng.

## 14. Checklist thiết kế lỗi cho MVC

- [ ] Phân loại lỗi theo phạm vi: field, form, component, page hay application.
- [ ] Trang lỗi phản ánh HTTP status thực tế.
- [ ] Phân biệt 401, 403, 404, 409, 429, 500 và 503 theo ngữ nghĩa.
- [ ] Nội dung lỗi giải thích tình huống và hành động tiếp theo.
- [ ] Trang lỗi không phụ thuộc vào service có thể đang gặp sự cố.
- [ ] Không hiển thị stack trace, SQL, token hoặc dữ liệu nhạy cảm.
- [ ] HTML MVC và REST API có định dạng lỗi phù hợp với client.
- [ ] Component phân biệt loading, success, empty, error và partial.
- [ ] Lỗi được xử lý ở phạm vi nhỏ nhất có thể khôi phục an toàn.
- [ ] Retry có giới hạn, backoff và xét idempotency.
- [ ] Trạng thái lỗi có thông báo truy cập được và hỗ trợ bàn phím.
- [ ] Correlation ID nối được phản hồi người dùng với log nội bộ.
- [ ] Có test cho status, template, fallback, retry, stale response và accessibility.

Thiết kế lỗi tốt giúp người dùng hiểu giới hạn hiện tại của ứng dụng mà không mất ngữ cảnh. Trang lỗi cấp ứng dụng xử lý những request không thể tiếp tục; trạng thái lỗi của component cô lập sự cố trong một phần giao diện; Controller và exception handler ánh xạ lỗi thành phản hồi đúng hợp đồng; còn View cung cấp hướng phục hồi dễ hiểu. Khi các phạm vi này được phân định rõ, ứng dụng MVC có thể thất bại một cách có kiểm soát và giúp người dùng tiếp tục công việc an toàn.
