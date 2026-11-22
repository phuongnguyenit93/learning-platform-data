# Trách nhiệm cốt lõi của Model, View và Controller

Trong module **MODEL_VIEW_CONTROLLER**, ta học cách tổ chức ứng dụng theo Model–View–Controller (MVC) để tách biệt trạng thái và nghiệp vụ, phần trình bày, cùng nơi tiếp nhận tương tác. Sự phân tách này giúp người phát triển lần theo luồng request, xác định hợp đồng dữ liệu giữa các phần, và xử lý biểu mẫu, lỗi, bảo mật cũng như kiểm thử ứng dụng web có hệ thống.

MVC không yêu cầu ứng dụng phải có đúng ba lớp hoặc ba thư mục mang tên Model, View và Controller. Đây là cách phân chia **trách nhiệm**. Một dự án có thể triển khai mỗi trách nhiệm bằng nhiều lớp, package hoặc thành phần; điều quan trọng là mỗi phần có mục đích rõ ràng và không chiếm công việc của phần khác.

## 1. MVC giải quyết vấn đề gì?

Khi một ứng dụng nhỏ phát triển, một hàm xử lý request rất dễ phải làm tất cả: đọc dữ liệu biểu mẫu, kiểm tra đầu vào, áp dụng quy tắc nghiệp vụ, truy vấn cơ sở dữ liệu, dựng HTML và quyết định chuyển trang. Cách viết này có vẻ nhanh lúc đầu, nhưng khiến thay đổi ở giao diện có thể ảnh hưởng nghiệp vụ, còn thay đổi quy tắc nghiệp vụ có thể buộc ta sửa mã xử lý HTTP.

MVC chia các mối quan tâm đó thành ba vai trò:

| Thành phần | Câu hỏi mà thành phần chịu trách nhiệm trả lời | Trọng tâm |
| --- | --- | --- |
| **Model** | Ứng dụng đang quản lý dữ liệu và quy tắc nào? | Trạng thái, dữ liệu có ý nghĩa nghiệp vụ và hành vi nghiệp vụ |
| **View** | Thông tin cần được trình bày cho người dùng như thế nào? | HTML, mẫu giao diện, định dạng và hiển thị dữ liệu |
| **Controller** | Ứng dụng cần phản ứng thế nào với tương tác vừa nhận? | Tiếp nhận request, điều phối xử lý và chọn response |

Ba phần phối hợp để hoàn thành một luồng sử dụng. Chúng không phải ba bản sao của cùng một dữ liệu và cũng không nên cùng quyết định một quy tắc.

## 2. Model: quản lý trạng thái và quy tắc nghiệp vụ

Model đại diện cho dữ liệu và hành vi có ý nghĩa đối với ứng dụng. Model trả lời những câu hỏi như: một đơn hàng có những trạng thái nào, tổng tiền được tính ra sao, khi nào đơn hàng được xác nhận, hoặc người dùng có đủ điều kiện thực hiện một thao tác hay không.

### Trách nhiệm chính

- **Biểu diễn khái niệm của miền nghiệp vụ.** Ví dụ: **Order**, **OrderLine**, **Product**, **Account**, **Money** hoặc **Booking**. Những đối tượng này diễn tả khái niệm mà ứng dụng cần quản lý, không chỉ là các cột trong bảng dữ liệu.
- **Giữ và thay đổi trạng thái hợp lệ.** Model xác định trạng thái hiện tại, các thao tác được phép và điều kiện chuyển trạng thái. Một đơn hàng đã bị hủy không nên được xác nhận lại nếu nghiệp vụ không cho phép.
- **Thực thi quy tắc nghiệp vụ.** Quy tắc như “đơn hàng phải có ít nhất một sản phẩm mới được xác nhận” thuộc về nghiệp vụ. Nếu chỉ đặt quy tắc này trong controller, một luồng khác có thể vô tình bỏ qua nó.
- **Cung cấp hành vi hoặc khả năng truy cập dữ liệu cho luồng ứng dụng.** Tùy kiến trúc, phần Model có thể bao gồm đối tượng miền, dịch vụ ứng dụng, giao diện repository và các thành phần quản lý trạng thái. Chi tiết lưu trữ thường được đặt sau một ranh giới để quy tắc nghiệp vụ không phụ thuộc trực tiếp vào SQL hay một hệ quản trị cơ sở dữ liệu cụ thể.

### Model không đồng nghĩa với cơ sở dữ liệu

Một bản ghi trong bảng **orders** có thể chứa **id**, **status**, **created_at** và các khóa ngoại. Đó là cách lưu trữ. Model còn thể hiện ý nghĩa của dữ liệu và những hành động hợp lệ trên dữ liệu ấy.

Tương tự, một lớp chỉ có các thuộc tính cùng getter/setter chưa chắc đã thể hiện đầy đủ Model. Nếu mọi quy tắc đều nằm trong controller hoặc dịch vụ điều phối, các đối tượng dữ liệu có thể trở thành những “túi dữ liệu” thụ động. Điều đó không tự động là sai trong mọi kiến trúc, nhưng nhóm phát triển cần đặt quy tắc ở một nơi thống nhất để mọi luồng gọi đều được bảo vệ.

### Ví dụ: quy tắc của đơn hàng

~~~java
public final class Order {
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    public void addLine(Product product, int quantity) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only a draft order can be changed");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        lines.add(new OrderLine(product, quantity));
    }

    public Money total() {
        return lines.stream()
                .map(OrderLine::subtotal)
                .reduce(Money.zero(), Money::add);
    }

    public void confirm() {
        if (lines.isEmpty()) {
            throw new IllegalStateException("An empty order cannot be confirmed");
        }
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only a draft order can be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }
}
~~~

Ví dụ trên cho thấy Model tự bảo vệ trạng thái đơn hàng. Controller có thể yêu cầu xác nhận đơn hàng, nhưng không cần tự tính tổng tiền hay tự kiểm tra mọi điều kiện chuyển trạng thái. Trong ứng dụng thực tế, các kiểu **OrderLine**, **Money**, **OrderStatus** và cơ chế lưu đơn hàng sẽ được định nghĩa phù hợp với miền nghiệp vụ.

## 3. View: trình bày thông tin và thu nhận thao tác

View chịu trách nhiệm biến dữ liệu đã được chuẩn bị thành nội dung mà người dùng có thể đọc hoặc tương tác. Trong ứng dụng web, View thường là template HTML, trang HTML, component giao diện hoặc một cấu trúc phản hồi được định dạng cho client.

### Trách nhiệm chính

- **Trình bày dữ liệu.** Hiển thị tên sản phẩm, trạng thái đơn hàng, thông báo và các thông tin cần thiết theo bố cục phù hợp.
- **Định dạng cho người dùng.** Chẳng hạn hiển thị ngày giờ theo múi giờ đã chọn, định dạng số tiền, hoặc chuyển trạng thái kỹ thuật thành nhãn dễ hiểu.
- **Thể hiện trạng thái giao diện.** View có thể hiển thị thông báo lỗi gắn với trường biểu mẫu, trạng thái đang tải hoặc nội dung rỗng dựa trên dữ liệu được cung cấp.
- **Tạo điểm tương tác.** Form, nút bấm và liên kết tạo ra request tiếp theo. View mô tả thao tác người dùng có thể thực hiện; Controller tiếp nhận và xử lý request tương ứng.

View nên tập trung vào cách trình bày. Nó không nên tự truy vấn cơ sở dữ liệu, tự quyết định người dùng có quyền xác nhận đơn hàng hay tự thực hiện quy tắc tính giá. Nếu template phải chứa nhiều điều kiện nghiệp vụ, phần trình bày đang gánh quá nhiều trách nhiệm.

### Dữ liệu đưa vào View

View thường nhận một tập dữ liệu đã được chuẩn bị, đôi khi gọi là **view model** hoặc **presentation model**. Đó có thể là một đối tượng riêng chỉ chứa những trường cần hiển thị, ví dụ:

~~~java
public record OrderPageData(
        String orderNumber,
        String statusLabel,
        String formattedTotal,
        List<OrderLinePageData> lines
) {}
~~~

View không cần biết dữ liệu được lấy từ bảng nào, phép tính được thực hiện ở đâu, hoặc hệ thống dùng loại cơ sở dữ liệu nào. Nó chỉ cần hợp đồng dữ liệu đủ rõ để trình bày.

Ví dụ một template có thể sử dụng các trường trên:

~~~html
<h1>Đơn hàng <span th:text="${page.orderNumber}"></span></h1>
<p>Trạng thái: <span th:text="${page.statusLabel}"></span></p>
<p>Tổng cộng: <span th:text="${page.formattedTotal}"></span></p>
~~~

Đây là ví dụ template theo cú pháp Thymeleaf. Với React, Vue, JSP hoặc một công nghệ khác, hình thức View khác nhau nhưng trách nhiệm trình bày vẫn tương tự.

## 4. Controller: tiếp nhận request và điều phối

Controller là điểm tiếp nhận tương tác từ bên ngoài và chuyển tương tác đó thành hành động của ứng dụng. Trong web MVC, tương tác thường đến dưới dạng HTTP request: truy cập một URL, gửi form, chọn bộ lọc hoặc nhấn nút.

### Trách nhiệm chính

- **Tiếp nhận và diễn giải request.** Xác định route, HTTP method, tham số đường dẫn, query parameter, header và dữ liệu trong body.
- **Kiểm tra dữ liệu ở ranh giới đầu vào.** Kiểm tra định dạng, trường bắt buộc, giới hạn độ dài hoặc kiểu dữ liệu. Những kiểm tra này giúp request có cấu trúc hợp lệ trước khi đi sâu vào xử lý.
- **Điều phối use case.** Gọi dịch vụ ứng dụng hoặc hành vi Model phù hợp với ý định của người dùng. Controller quyết định gọi thao tác nào, nhưng không nên tự chứa toàn bộ quy tắc nghiệp vụ.
- **Chọn response.** Sau khi xử lý, Controller quyết định trả trang nào, chuyển hướng đến URL nào, hoặc trả JSON với mã trạng thái HTTP phù hợp.
- **Chuyển lỗi thành phản hồi thích hợp.** Lỗi đầu vào có thể đưa người dùng trở lại form cùng thông báo; tài nguyên không tồn tại có thể thành HTTP 404; lỗi nghiệp vụ có thể được ánh xạ thành phản hồi dễ hiểu.

Controller thường là lớp gần HTTP nhất. Vì vậy, nó có thể biết về route, session, cookie, mã trạng thái và định dạng request/response. Model không nên phải phụ thuộc vào các chi tiết này để thực thi quy tắc nghiệp vụ.

### Controller không nên trở thành nơi chứa nghiệp vụ

Một controller có hàng trăm dòng để tính giá, kiểm tra tồn kho, cập nhật nhiều trạng thái và xây dựng câu truy vấn thường khó đọc và khó kiểm thử. Những thao tác này nên được chuyển đến hành vi Model hoặc dịch vụ ứng dụng có tên diễn tả use case.

Controller vẫn có thể thực hiện điều phối. Ví dụ, nó nhận **CreateOrderRequest**, gọi **PlaceOrderUseCase**, rồi chọn trang chi tiết đơn hàng. Điều phối là trách nhiệm của Controller; các điều kiện để một đơn hàng hợp lệ là trách nhiệm của nghiệp vụ.

## 5. Ba thành phần phối hợp trong một request

Xét tình huống người dùng gửi biểu mẫu tạo đơn hàng. Một luồng điển hình có thể diễn ra như sau:

1. Người dùng mở trang tạo đơn hàng. Browser gửi request **GET /orders/new**.
2. Controller tiếp nhận request và chọn View biểu mẫu. View hiển thị các trường cần nhập.
3. Người dùng điền thông tin và gửi form. Browser gửi **POST /orders**.
4. Controller đọc dữ liệu, kiểm tra cấu trúc và định dạng đầu vào, sau đó gọi use case tạo đơn hàng.
5. Phần nghiệp vụ sử dụng Model để kiểm tra quy tắc, tạo đơn hàng và yêu cầu lưu trạng thái mới qua cơ chế lưu trữ phù hợp.
6. Khi xử lý thành công, Controller chọn response chuyển hướng đến trang chi tiết. Request tiếp theo lấy dữ liệu cần thiết và View trình bày đơn hàng.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant C as Controller
    participant M as Model / use case
    participant V as View

    User->>Browser: Mở form tạo đơn hàng
    Browser->>C: GET /orders/new
    C->>V: Yêu cầu render form
    V-->>Browser: HTML form
    User->>Browser: Nhập và gửi dữ liệu
    Browser->>C: POST /orders
    C->>C: Kiểm tra cấu trúc đầu vào
    C->>M: Gọi use case tạo đơn hàng
    M->>M: Áp dụng quy tắc nghiệp vụ
    M-->>C: Kết quả tạo đơn hàng
    C-->>Browser: Redirect đến trang chi tiết
    Browser->>C: GET /orders/{id}
    C->>M: Lấy dữ liệu đơn hàng
    M-->>C: Dữ liệu nghiệp vụ
    C->>V: Cung cấp dữ liệu trình bày
    V-->>Browser: HTML chi tiết đơn hàng
~~~

Sơ đồ mô tả một cách triển khai phổ biến, không phải giao thức bắt buộc của mọi ứng dụng MVC. Một ứng dụng có thể trả JSON thay vì HTML; khi đó client dùng dữ liệu JSON để cập nhật giao diện. Ranh giới trách nhiệm vẫn có thể giữ nguyên: Controller xử lý giao tiếp, Model thực hiện nghiệp vụ, còn phần giao diện chịu trách nhiệm trình bày.

## 6. Hợp đồng dữ liệu giữa các thành phần

Các thành phần cần trao đổi dữ liệu, nhưng không nên phụ thuộc vào mọi chi tiết nội bộ của nhau. Hợp đồng dữ liệu xác định thông tin nào được gửi qua ranh giới và ý nghĩa của từng trường.

| Hợp đồng | Hướng trao đổi thường gặp | Mục đích |
| --- | --- | --- |
| Request DTO / Form object | Client → Controller | Mô tả dữ liệu người dùng gửi lên |
| Command / tham số use case | Controller → Model hoặc dịch vụ ứng dụng | Diễn đạt hành động cần thực hiện |
| Domain object / kết quả nghiệp vụ | Model → Controller | Trả kết quả có ý nghĩa nghiệp vụ |
| View model / response DTO | Controller → View hoặc client | Chỉ cung cấp dữ liệu cần để trình bày |

Không phải dự án nào cũng cần một kiểu riêng cho mọi hàng. Với ứng dụng nhỏ, một số cấu trúc có thể được dùng chung khi ranh giới vẫn rõ. Tuy nhiên, việc truyền trực tiếp đối tượng ORM hoặc toàn bộ entity vào template/API có thể làm lộ trường nội bộ, tạo phụ thuộc vào cấu trúc lưu trữ và khiến thay đổi cơ sở dữ liệu ảnh hưởng giao diện.

Một nguyên tắc thực tế là chỉ gửi qua mỗi ranh giới lượng dữ liệu cần thiết cho công việc của thành phần nhận. Controller không cần chuyển toàn bộ HTTP request vào Model; View không cần nhận kết nối cơ sở dữ liệu; Model không cần biết template nào đang hiển thị kết quả.

## 7. Đặt kiểm tra, lỗi và bảo mật đúng chỗ

Một request thường phải qua nhiều loại kiểm tra. Cần phân biệt mục đích của chúng để tránh đặt mọi điều kiện vào cùng một lớp.

- **Kiểm tra cấu trúc đầu vào** phù hợp ở biên Controller hoặc tầng binding/validation: trường có tồn tại không, số lượng có đúng định dạng không, chuỗi có vượt giới hạn không.
- **Kiểm tra bất biến nghiệp vụ** phải được bảo vệ trong Model hoặc use case: đơn hàng rỗng không thể xác nhận, số dư không thể âm nếu nghiệp vụ cấm, hoặc một lịch đặt không thể trùng theo quy tắc đã định.
- **Kiểm tra quyền truy cập** cần được thực thi tại ranh giới bảo vệ use case hoặc tài nguyên. Ẩn nút bấm trong View chỉ cải thiện trải nghiệm; nó không ngăn được request trực tiếp đến endpoint.
- **Trình bày lỗi** thuộc về response và View: thông báo cần dễ hiểu, không tiết lộ stack trace, câu SQL, token hoặc dữ liệu nội bộ.

Một quy tắc nghiệp vụ quan trọng không nên chỉ được kiểm tra ở giao diện hay một endpoint. Cùng một use case có thể được gọi từ web, API, tác vụ nền hoặc một luồng nội bộ khác. Đặt quy tắc tại lớp nghiệp vụ giúp các đường gọi cùng tuân thủ một điều kiện.

## 8. Những dấu hiệu phân chia trách nhiệm chưa tốt

| Dấu hiệu | Vấn đề | Hướng điều chỉnh |
| --- | --- | --- |
| Controller tự tính toán giá, cập nhật trạng thái và truy vấn dữ liệu | Controller đang chứa nghiệp vụ và chi tiết lưu trữ | Chuyển quy tắc vào Model, use case hoặc dịch vụ phù hợp; để Controller điều phối |
| View tự gọi cơ sở dữ liệu hoặc tự quyết định quy tắc nghiệp vụ | Giao diện phụ thuộc vào hạ tầng và logic miền | Chuẩn bị dữ liệu trước khi render; truyền view model rõ ràng |
| Model phụ thuộc vào request, session hoặc template | Nghiệp vụ bị gắn với giao thức và giao diện | Đưa chi tiết HTTP và trình bày ra ngoài Model |
| Cùng một quy tắc được lặp lại trong nhiều controller | Các luồng có thể xử lý không nhất quán | Đưa quy tắc về một điểm thực thi chung trong Model/use case |
| View nhận cả entity lưu trữ với nhiều trường nội bộ | Hợp đồng trình bày quá rộng | Tạo response DTO hoặc view model chỉ gồm dữ liệu cần thiết |

Không nên đánh giá thiết kế chỉ bằng số lượng lớp hoặc độ dài file. Một controller ngắn vẫn có thể gọi một dịch vụ chứa quá nhiều trách nhiệm; một Model có nhiều lớp vẫn có thể rối nếu các lớp phụ thuộc vòng tròn. Hãy lần theo một thay đổi cụ thể: nếu chỉ đổi cách hiển thị ngày tháng mà phải sửa quy tắc nghiệp vụ, ranh giới có thể chưa tốt.

## 9. Kiểm thử theo trách nhiệm

Phân chia MVC giúp xác định loại kiểm thử phù hợp:

- **Model:** kiểm thử đơn vị cho phép tính, chuyển trạng thái và bất biến nghiệp vụ. Ví dụ, xác nhận đơn hàng rỗng phải bị từ chối.
- **Controller:** kiểm thử request/response, binding dữ liệu, mã HTTP, chuyển hướng, gọi đúng use case và ánh xạ lỗi. Có thể thay thế phụ thuộc bằng mock hoặc fake khi phù hợp.
- **View:** kiểm thử nội dung và trạng thái trình bày với các dữ liệu đầu vào khác nhau, chẳng hạn đơn hàng có nhiều dòng, danh sách rỗng hoặc có lỗi biểu mẫu.
- **Tích hợp luồng:** kiểm thử một request đi qua Controller, Model và View hoặc bộ tuần tự hóa để xác nhận hợp đồng giữa các phần hoạt động cùng nhau.

Không cần kiểm thử cùng một quy tắc ở mọi tầng với cùng một cách. Quy tắc nên có kiểm thử tập trung ở nơi sở hữu nó; kiểm thử tích hợp xác nhận các thành phần kết nối đúng.

## 10. Cách tự xác định trách nhiệm khi thiết kế

Khi thêm một chức năng, hãy mô tả từng quyết định và tự hỏi:

1. Quyết định này liên quan đến ý nghĩa dữ liệu hoặc quy tắc nghiệp vụ? Đặt trong Model hoặc use case.
2. Quyết định này liên quan đến cách hiển thị, nhãn, bố cục hoặc định dạng? Đặt trong View hoặc thành phần trình bày.
3. Quyết định này liên quan đến request, tham số, HTTP method, điều phối và response? Đặt trong Controller.
4. Quyết định này là kiểm tra đầu vào hay bất biến nghiệp vụ? Kiểm tra đầu vào ở ranh giới; bất biến phải được bảo vệ tại lớp nghiệp vụ.
5. Nhiều luồng cần dùng cùng một quy tắc? Đưa quy tắc về một nơi dùng chung thay vì sao chép vào từng Controller.

Ví dụ với chức năng hủy đơn hàng: View hiển thị nút Hủy khi phù hợp; Controller nhận request hủy và xác thực người gọi; use case kiểm tra quyền và điều phối thao tác; Model bảo vệ điều kiện chuyển trạng thái; Controller trả response; View hiển thị trạng thái mới hoặc thông báo lỗi. Cách phân chia này giúp từng phần có thể thay đổi và kiểm thử với ít ảnh hưởng chéo hơn.

## Kết luận

Model quản lý trạng thái và bảo vệ quy tắc nghiệp vụ; View trình bày thông tin và tạo điểm tương tác; Controller tiếp nhận request, điều phối use case và chọn response. Khi ba trách nhiệm có ranh giới rõ, ứng dụng web dễ thay đổi giao diện, mở rộng luồng xử lý và kiểm thử từng phần hơn. Hãy dùng MVC như một nguyên tắc tổ chức trách nhiệm, đồng thời điều chỉnh số lượng lớp và cách triển khai theo độ phức tạp thực tế của ứng dụng.
