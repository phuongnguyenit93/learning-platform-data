# Khởi chạy, tiếp tục và quan sát execution key

Trong chương **Flow đầu tiên**, ta sẽ theo dõi một flow từ lúc trình duyệt mở URL lần đầu đến khi người dùng gửi sự kiện để chuyển sang state kế tiếp. Đây là bước nền tảng khi làm việc với **SPRING_WEB_FLOW**: Spring Web Flow mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow, giúp trạng thái điều hướng được quản lý trong flow thay vì phân tán trong controller.

Bài học này giải thích cách Spring MVC tìm flow, cách một flow execution được tạo và khôi phục giữa các request, ý nghĩa của execution key, và cách quan sát những thay đổi đó khi chạy ứng dụng.

## 1. Phân biệt flow ID, flow execution và execution key

Ba khái niệm này liên quan với nhau nhưng đại diện cho ba thứ khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Flow ID | Định danh của bản định nghĩa flow đã đăng ký trong flow registry | `greeting` |
| Flow execution | Một lần chạy cụ thể của flow cho một hành trình người dùng | Một người dùng đang đi từ màn hình chào đến màn hình xác nhận |
| Execution key | Khóa do Spring Web Flow cấp để tìm lại flow execution khi request tiếp theo được gửi đến | `e1s1` |

Flow ID trả lời câu hỏi **đang chạy loại quy trình nào?** Execution trả lời **đây là lần chạy cụ thể nào?** Execution key giúp framework tìm lại lần chạy đó ở request tiếp theo.

Một flow có thể được nhiều người dùng khởi chạy cùng lúc. Mỗi lần khởi chạy tạo một execution riêng, dù tất cả cùng sử dụng một Flow ID. Vì vậy, không được dùng Flow ID thay cho execution key hoặc lưu một execution key dùng chung cho mọi người dùng.

Execution key là giá trị định danh do framework quản lý. Hãy xem nó như một khóa tham chiếu opaque: ứng dụng chuyển tiếp giá trị do framework tạo ra và không tự phân tích cấu trúc bên trong. Ví dụ `e1s1` chỉ minh họa hình dạng một khóa; mã thực tế phụ thuộc repository và chính sách snapshot. Execution key cũng không thay thế cơ chế đăng nhập, phân quyền hoặc kiểm tra quyền truy cập dữ liệu.

## 2. Spring MVC tìm và khởi chạy flow như thế nào?

Trong ứng dụng Spring MVC tích hợp Spring Web Flow, request đi qua các thành phần chính sau:

- **Flow registry** lưu các định nghĩa flow và ánh xạ chúng với Flow ID.
- **Flow executor** điều phối việc khởi chạy hoặc tiếp tục một flow execution.
- **FlowHandlerMapping** nhận diện URL thuộc về flow nào.
- **FlowHandlerAdapter** chuyển request đã được ánh xạ đến flow executor.

Một cấu hình XML điển hình có thể đăng ký flow và executor như sau:

~~~xml
<webflow:flow-registry id="flowRegistry" base-path="/WEB-INF/flows">
    <webflow:flow-location
        path="/greeting/greeting-flow.xml"
        id="greeting" />
</webflow:flow-registry>

<webflow:flow-executor
    id="flowExecutor"
    flow-registry="flowRegistry" />
~~~

Để request được xử lý bởi Spring Web Flow, ứng dụng còn cần đăng ký các thành phần MVC mapping và adapter:

~~~xml
<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="flowRegistry" ref="flowRegistry" />
    <property name="order" value="0" />
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
</bean>
~~~

Các bean trên phối hợp với DispatcherServlet. FlowHandlerMapping xác định request thuộc flow nào; FlowHandlerAdapter nhận request và gọi flow executor. Cấu hình thực tế cần thống nhất với phiên bản Spring Web Flow, Spring MVC, view resolver và cách tổ chức tài nguyên của ứng dụng.

Trong ví dụ, Flow ID được đăng ký là `greeting`. Ứng dụng có thể ánh xạ URL như `/greeting` đến flow này. Khi người dùng truy cập URL đó lần đầu mà chưa gửi execution key, framework hiểu đây là yêu cầu khởi chạy một execution mới.

## 3. Tạo flow đầu tiên để quan sát vòng đời

Ta dùng một flow ngắn gồm hai view-state và một end-state:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="welcome">

    <view-state id="welcome" view="welcome">
        <transition on="continue" to="details" />
    </view-state>

    <view-state id="details" view="details">
        <transition on="finish" to="completed" />
    </view-state>

    <end-state id="completed" view="completed" />
</flow>
~~~

Ý nghĩa của từng state:

- `welcome` hiển thị màn hình đầu tiên. Khi nhận event `continue`, flow chuyển sang `details`.
- `details` hiển thị màn hình tiếp theo. Khi nhận event `finish`, flow chuyển sang `completed`.
- `completed` kết thúc flow execution và hiển thị kết quả cuối cùng.

Các giá trị trong thuộc tính `view` là tên view được Spring MVC phân giải theo cấu hình view resolver. Các file view tương ứng cần tồn tại trong ứng dụng.

Trong view `welcome`, một nút gửi event có thể được viết như sau:

~~~html
<form method="post">
    <button type="submit" name="_eventId_continue">
        Tiếp tục
    </button>
</form>
~~~

Quy ước tên `_eventId_continue` tạo event có ID là `continue`. Spring Web Flow dùng event này để tìm transition có thuộc tính `on="continue"` trong state hiện tại.

Form phải gửi request về URL của flow execution hiện tại để framework nhận diện đúng execution. Khi dùng view và URL được Spring Web Flow quản lý, framework có thể đưa thông tin execution vào URL hoặc dữ liệu form được render. Nếu tự tạo form action hoặc URL bằng mã thủ công, cần bảo toàn execution key theo cơ chế URL của flow.

## 4. Khởi chạy một execution mới

Giả sử ứng dụng chạy dưới context path `/app` và flow được ánh xạ tại `/greeting`. Người dùng mở:

~~~http
GET /app/greeting HTTP/1.1
Host: localhost:8080
~~~

Request chưa có execution key. Luồng xử lý diễn ra như sau:

1. DispatcherServlet nhận request.
2. FlowHandlerMapping nhận diện URL và tìm Flow ID `greeting` trong flow registry.
3. FlowHandlerAdapter chuyển request đến flow executor.
4. Flow executor khởi chạy flow definition và tạo một flow execution mới.
5. Flow bắt đầu tại state `welcome`.
6. Flow execution repository quản lý việc lưu và tìm lại execution.
7. View của state `welcome` được render để trả về trình duyệt.

Sau khi khởi chạy, Spring Web Flow cấp execution key và sử dụng nó trong URL tiếp tục flow. Một URL minh họa có thể trông như sau:

~~~text
/app/greeting?execution=e1s1
~~~

Tên tham số mặc định thường dùng để truyền execution key là `execution`. Khóa thực tế do framework tạo ra; không được tự đặt thành `e1s1`, tăng số bằng tay hoặc suy ra khóa từ Flow ID.

Điểm cần nhớ: request đầu tiên xác định flow cần khởi chạy, còn execution key được cấp cho lần chạy vừa tạo để các request sau có thể tiếp tục đúng hành trình.

## 5. Gửi event để tiếp tục execution

Khi người dùng bấm nút Tiếp tục trên view `welcome`, trình duyệt gửi request tiếp theo. Request phải mang theo execution key của lần chạy đang hoạt động và event cần xử lý.

Ví dụ minh họa:

~~~http
POST /app/greeting?execution=e1s1 HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

_eventId_continue=
~~~

Trong request này có hai thông tin mang ý nghĩa khác nhau:

- `execution=e1s1` cho biết flow execution nào cần được tiếp tục.
- `_eventId_continue` cho biết người dùng vừa phát ra event `continue`.

Framework sử dụng execution key để tìm execution trong repository, khôi phục trạng thái của nó và xử lý event trong state hiện tại. Transition có `on="continue"` được chọn, nên flow chuyển từ `welcome` sang `details`. View của state mới được render và trả về trình duyệt.

Khi người dùng gửi event `finish` từ view `details`, flow chuyển sang end-state `completed`. Execution kết thúc theo định nghĩa flow. Muốn bắt đầu một hành trình mới, người dùng truy cập URL khởi chạy flow mà không mang execution key của execution đã kết thúc.

### Sơ đồ vòng đời request

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant M as Spring MVC
    participant A as FlowHandlerAdapter
    participant E as Flow Executor
    participant R as Flow Execution Repository

    B->>M: GET /greeting (chưa có execution key)
    M->>A: Ánh xạ request đến flow greeting
    A->>E: Khởi chạy flow
    E->>R: Tạo và lưu execution
    R-->>E: Execution key
    E-->>A: Render state welcome
    A-->>B: View welcome + URL tiếp tục

    B->>M: POST execution key + event continue
    M->>A: Ánh xạ request đến flow greeting
    A->>E: Tiếp tục execution theo key
    E->>R: Tìm và khôi phục execution
    R-->>E: Trạng thái execution
    E->>E: Xử lý event và transition
    E->>R: Lưu trạng thái tiếp theo
    R-->>E: Khóa tiếp tục
    E-->>A: Render state details
    A-->>B: View details + URL tiếp tục
~~~

Sơ đồ tập trung vào vai trò của các thành phần. Chi tiết lưu snapshot, khôi phục trạng thái và cách tạo khóa có thể khác nhau theo cấu hình repository.

## 6. Execution key được quản lý ở đâu?

Flow execution repository là thành phần chịu trách nhiệm lưu trữ và tìm lại flow execution thông qua execution key. Khi request tiếp theo được gửi đến, flow executor dùng key để yêu cầu repository khôi phục đúng execution.

Trong cấu hình thông dụng, trạng thái execution được quản lý phía server và trình duyệt chỉ gửi khóa tham chiếu. Repository có thể quản lý các snapshot để hỗ trợ việc khôi phục trạng thái tại những điểm khác nhau của flow. Cách tổ chức cụ thể phụ thuộc loại repository và cấu hình ứng dụng.

Một số điểm cần lưu ý:

- Mỗi lần khởi chạy flow tạo một execution độc lập. Hai tab cùng mở flow có thể đại diện cho hai execution khác nhau.
- Execution key do framework quản lý. Không lưu nó vào biến static hoặc singleton dùng chung cho tất cả người dùng.
- Không giả định khóa luôn có một định dạng cố định hoặc luôn tăng theo một quy luật mà ứng dụng tự định nghĩa.
- Không dùng execution key để quyết định người dùng có quyền xem hoặc sửa dữ liệu nghiệp vụ hay không. Các kiểm tra xác thực và phân quyền vẫn phải được thực hiện ở tầng phù hợp.
- Khi session hoặc execution hết hạn, key cũ có thể không còn khôi phục được execution. Ứng dụng cần có cách thông báo và hướng dẫn người dùng bắt đầu lại quy trình.

Execution key giúp nối các request HTTP vốn độc lập thành một hành trình có trạng thái. Nó không làm cho HTTP trở thành một kết nối liên tục; mỗi request vẫn được gửi riêng và được framework liên kết với execution thông qua khóa.

## 7. Quan sát execution key khi ứng dụng chạy

Có thể quan sát vòng đời flow bằng công cụ Network của trình duyệt và log của ứng dụng.

### Quan sát trong Network

Thực hiện các bước sau:

1. Mở DevTools của trình duyệt và chọn thẻ Network.
2. Xóa danh sách request cũ để dễ theo dõi.
3. Truy cập URL khởi chạy flow, chẳng hạn `/app/greeting`.
4. Mở request GET và xác nhận URL ban đầu chưa có tham số `execution`.
5. Kiểm tra response và URL của form trong view được render. Tìm execution key mà framework cấp.
6. Bấm Tiếp tục và mở request POST tương ứng.
7. Xác nhận request mang execution key của flow đang chạy và event `_eventId_continue`.
8. Quan sát response tiếp theo để xác nhận view `details` được hiển thị.

Tên request, vị trí tham số và cách render form có thể khác nhau theo view technology và cấu hình URL. Điều cần kiểm tra là request tiếp tục phải mang đúng khóa execution và event phù hợp với transition của state hiện tại.

### Quan sát bằng log

Trong môi trường phát triển, có thể bật log DEBUG cho các package Spring Web Flow:

~~~xml
<logger name="org.springframework.webflow" level="DEBUG" />
<logger name="org.springframework.webflow.mvc.servlet" level="DEBUG" />
~~~

Cú pháp cấu hình logger phụ thuộc hệ thống logging đang dùng, chẳng hạn Logback hoặc Log4j. Log giúp theo dõi request được xử lý, flow được chọn, state được kích hoạt và transition được thực thi.

Khi cần theo dõi sâu hơn, có thể tích hợp FlowExecutionListener với flow executor để quan sát các mốc trong vòng đời execution như bắt đầu session, phát event, đi vào state, thực hiện transition và kết thúc session. Listener phù hợp để ghi nhận thông tin vận hành có chọn lọc, ví dụ Flow ID, state ID, event ID và thời gian xử lý.

Không ghi dữ liệu biểu mẫu nhạy cảm hoặc thông tin cá nhân vào log chỉ để theo dõi flow. Nếu cần tương quan các request, hãy dùng mã tương quan phù hợp với chính sách logging của ứng dụng và xử lý execution key như một giá trị định danh do framework quản lý.

## 8. Xử lý các tình huống thường gặp

| Hiện tượng | Nguyên nhân có thể có | Hướng kiểm tra |
|---|---|---|
| Truy cập URL nhưng không tìm thấy flow | Flow chưa được đăng ký hoặc URL không ánh xạ đến Flow ID | Kiểm tra flow registry, FlowHandlerMapping và đường dẫn request |
| Màn hình đầu tiên hiển thị nhưng bấm Tiếp tục không chạy | Form làm mất execution key hoặc không gửi event | Kiểm tra request POST trong Network, URL form và tên trường `_eventId_continue` |
| Request có key nhưng execution không được tìm thấy | Key không hợp lệ, execution đã kết thúc hoặc session/repository không còn dữ liệu | Kiểm tra session, repository và thời điểm key được cấp |
| Event được gửi nhưng không chuyển state | Event ID không khớp transition của state hiện tại | Đối chiếu `_eventId_...` với thuộc tính `on` trong flow definition |
| Hai tab ảnh hưởng nhầm hành trình | Ứng dụng tự lưu execution key vào trạng thái dùng chung | Để framework quản lý key theo từng request và execution riêng |
| Người dùng quay lại flow đã hết hạn | Execution hoặc session đã hết thời gian tồn tại | Hiển thị thông báo phù hợp và cung cấp đường dẫn khởi chạy flow mới |

Khi gặp lỗi, hãy kiểm tra theo thứ tự: URL và Flow ID, execution key, event ID, state hiện tại, sau đó mới kiểm tra repository và session. Thứ tự này giúp xác định lỗi nằm ở bước định tuyến, tiếp tục execution hay xử lý transition.

## 9. Thực hành: theo dõi một flow qua hai request

Dùng flow `greeting` ở trên và thực hiện bài tập:

1. Khởi chạy flow bằng cách mở URL chưa có execution key.
2. Ghi nhận Flow ID, state đầu tiên và execution key xuất hiện sau khi flow được khởi chạy.
3. Gửi event `continue` từ view `welcome`.
4. Trong Network, kiểm tra request tiếp tục có mang execution key và event ID chính xác hay không.
5. Xác nhận flow chuyển sang state `details`.
6. Gửi event `finish` và xác nhận flow kết thúc.
7. Mở lại URL khởi chạy flow để tạo một execution mới.
8. Mở flow ở hai tab và quan sát hai lần chạy độc lập.

Sau khi hoàn thành, hãy tự trả lời:

- Flow ID có thay đổi khi cùng một flow được khởi chạy ở hai tab không?
- Execution key giúp framework xác định điều gì trong request tiếp theo?
- Vì sao event ID và execution key không thể thay thế cho nhau?
- Khi execution hết hạn, người dùng cần làm gì để tiếp tục sử dụng chức năng?

## 10. Ghi nhớ

Một request không có execution key thường là điểm bắt đầu của một flow execution mới. Spring Web Flow dùng flow registry để tìm định nghĩa flow, flow executor để điều phối và execution repository để quản lý trạng thái của lần chạy. Sau khi khởi chạy, framework cấp execution key để request tiếp theo có thể khôi phục đúng execution. Event được gửi cùng request quyết định transition nào sẽ được thực hiện trong state hiện tại.

Khi đã hiểu vòng đời này, bạn có thể mở rộng flow bằng form binding, validation, scope, subflow và xử lý lỗi mà vẫn giữ được một mô hình điều hướng nhiều bước rõ ràng, phù hợp với mục tiêu của module SPRING_WEB_FLOW.
