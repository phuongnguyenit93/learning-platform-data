# Chọn chính sách redirect khi vào view-state

Spring Web Flow mô hình hóa hành trình web nhiều bước bằng flow, state, event, transition và subflow. Trong một flow, **view-state** là điểm dừng tại đó ứng dụng hiển thị một màn hình để người dùng đọc thông tin hoặc nhập dữ liệu. Khi flow đi vào view-state, Spring Web Flow có thể chuyển hướng trình duyệt đến URL của lần thực thi flow rồi mới hiển thị view. Thuộc tính **redirect** cho phép lựa chọn chính sách này.

Chọn đúng chính sách redirect giúp ứng dụng xử lý form theo mô hình POST-Redirect-GET, hạn chế việc trình duyệt gửi lại dữ liệu khi refresh và giữ URL phù hợp với trạng thái hiện tại của flow. Tuy nhiên, redirect tạo thêm một HTTP request và làm thay đổi vòng đời của request hiện tại. Vì vậy, cần hiểu dữ liệu nào được giữ trong flow, dữ liệu nào chỉ tồn tại trong request và thao tác nào có thể bị thực hiện lặp.

## 1. View-state và thời điểm redirect

Một view-state thường có các thành phần:

- **id**: định danh state trong flow.
- **view**: tên view được hiển thị, chẳng hạn một JSP hoặc template được cấu hình cho ứng dụng.
- **model**: đối tượng dữ liệu được bind với view khi state hỗ trợ nhập liệu.
- **transition**: quy tắc chuyển sang state khác khi flow nhận được event.
- **redirect**: chính sách chuyển hướng trình duyệt khi flow đi vào view-state.

Ví dụ, flow đặt chỗ có thể đi qua màn hình nhập thông tin, màn hình rà soát và màn hình hoàn tất. Mỗi view-state là một điểm dừng để người dùng tương tác. Khi người dùng gửi form, request mang event đến flow; transition quyết định state tiếp theo. Nếu state tiếp theo là một view-state, chính sách redirect của state đó quyết định cách view được trả về trình duyệt.

Điều quan trọng là phân biệt hai việc:

1. **Transition** thay đổi trạng thái nghiệp vụ của flow, ví dụ từ nhập thông tin sang rà soát.
2. **Redirect** thay đổi cách trình duyệt nhận view của state vừa được vào, bằng một phản hồi chuyển hướng và một request tiếp theo.

Redirect không tự tạo transition, không quyết định event nào hợp lệ và cũng không tạo một flow mới. Nó điều khiển vòng trao đổi HTTP khi flow tạm dừng tại view-state.

## 2. Hai chính sách redirect

Trong Spring Web Flow, thuộc tính **redirect** của view-state nhận giá trị boolean. Với cấu hình thông dụng, mặc định là **true** nếu không khai báo thuộc tính này. Dù vậy, nên ghi rõ giá trị trong những flow cần thể hiện chủ đích hoặc cần chuyển đổi giữa các phiên bản thư viện.

| Chính sách | Hành vi | Tác động thường gặp |
|---|---|---|
| **redirect=\"true\"** | Spring Web Flow trả phản hồi redirect đến URL tiếp tục flow tại view-state hiện tại; trình duyệt gửi request mới để lấy view. | Hỗ trợ POST-Redirect-GET, URL phản ánh lần thực thi flow đang tạm dừng và refresh thường gửi lại GET. |
| **redirect=\"false\"** | View được render trong request hiện tại mà không có bước redirect bổ sung. | Giảm một lượt request; nếu request hiện tại là POST, thao tác refresh có thể gửi lại POST. |

Sơ đồ với redirect được bật:

~~~text
Browser
  |
  | POST: event + dữ liệu form
  v
Spring Web Flow
  |
  | bind dữ liệu, validation, xử lý transition
  v
View-state tiếp theo
  |
  | HTTP redirect
  v
Browser
  |
  | GET: URL của flow execution
  v
Spring Web Flow
  |
  | render view
  v
HTML response
~~~

Flow execution vẫn được tiếp tục trong cùng hành trình. Redirect không đồng nghĩa với việc xóa dữ liệu flow hoặc khởi tạo lại toàn bộ quy trình. URL được gửi cho trình duyệt chứa thông tin cần thiết để tiếp tục đúng lần thực thi flow.

## 3. Bật redirect để áp dụng POST-Redirect-GET

POST-Redirect-GET (PRG) là cách tổ chức tương tác phổ biến cho form:

1. Trình duyệt gửi dữ liệu bằng POST.
2. Máy chủ xử lý dữ liệu và quyết định kết quả.
3. Máy chủ trả redirect.
4. Trình duyệt gửi GET đến URL được chỉ định để hiển thị kết quả.

Khi người dùng refresh trang kết quả, trình duyệt thường lặp lại GET thay vì gửi lại POST chứa dữ liệu form. Điều này giảm nguy cơ gửi lại form chỉ vì người dùng bấm refresh hoặc mở lại trang kết quả.

Ví dụ cấu hình một flow đặt chỗ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="booking" class="com.example.booking.Booking"/>

    <view-state id="enterDetails"
                view="booking/enterDetails"
                model="booking"
                redirect="true">
        <transition on="submit" to="reviewBooking"/>
    </view-state>

    <view-state id="reviewBooking"
                view="booking/review"
                redirect="true">
        <transition on="confirm" to="complete"/>
        <transition on="edit" to="enterDetails"/>
    </view-state>

    <end-state id="complete"/>
</flow>
~~~

Ở đây, người dùng nhập dữ liệu tại **enterDetails**. Khi gửi event **submit**, flow xử lý dữ liệu và chuyển sang **reviewBooking**. View-state đích có **redirect=\"true\"**, vì vậy trình duyệt nhận redirect rồi gửi GET để hiển thị màn hình rà soát.

Một form JSP có thể gửi event cho transition như sau:

~~~jsp
<form:form method="post" modelAttribute="booking">
    <label for="customerName">Họ tên</label>
    <form:input id="customerName" path="customerName"/>

    <label for="email">Email</label>
    <form:input id="email" path="email"/>

    <button type="submit" name="_eventId_submit">Tiếp tục</button>
</form:form>
~~~

Tên event trong form phải khớp với giá trị **on** của transition. Spring Web Flow nhận event, thực hiện binding và validation theo cấu hình flow, sau đó mới chuyển state nếu dữ liệu hợp lệ. Redirect được quyết định tại view-state mà flow đi vào sau transition.

Trong các flow có nhiều form liên tiếp, bật redirect ở những view-state kết quả sau POST giúp hành vi điều hướng nhất quán. Có thể khai báo tường minh **redirect=\"true\"** ở từng view-state để người đọc nhận biết chính sách ngay trong định nghĩa flow.

## 4. Khi nào nên tắt redirect

Có thể chọn **redirect=\"false\"** khi muốn render view ngay trong request hiện tại, chẳng hạn một màn hình chỉ đọc được hiển thị sau một request GET hoặc một tình huống nội bộ mà ứng dụng chủ động chấp nhận việc không có request redirect bổ sung.

Ví dụ:

~~~xml
<view-state id="showSearchHelp"
            view="search/help"
            redirect="false">
    <transition on="back" to="searchForm"/>
</view-state>
~~~

Ví dụ này phù hợp khi màn hình trợ giúp chỉ được hiển thị từ một request GET và không thực hiện thao tác ghi dữ liệu. Nếu một view-state được vào sau khi xử lý POST, cần cân nhắc kỹ trước khi tắt redirect: khi refresh, trình duyệt có thể gửi lại request POST và làm lặp thao tác đã thực hiện.

Không nên tắt redirect chỉ để tiết kiệm một request khi transition vừa ghi dữ liệu, tạo đơn hàng, trừ tiền hoặc gửi thông báo. Trong các tình huống đó, PRG giúp điều hướng rõ ràng hơn. Nếu bắt buộc render trực tiếp sau POST, nghiệp vụ vẫn cần cơ chế chống thực hiện trùng như mã yêu cầu duy nhất, kiểm tra trạng thái hoặc xử lý idempotent.

## 5. Dữ liệu và scope khi redirect

Redirect kết thúc request HTTP hiện tại và khiến trình duyệt gửi một request mới. Vì vậy, dữ liệu chỉ tồn tại trong request hiện tại không tự động xuất hiện trong request tiếp theo.

Spring Web Flow cung cấp các scope để quản lý dữ liệu theo vòng đời phù hợp:

| Scope | Vòng đời và cách dùng |
|---|---|
| **request scope** | Chỉ tồn tại trong một HTTP request. Dùng cho dữ liệu tạm thời của lần xử lý hiện tại. Không dựa vào scope này để giữ dữ liệu qua redirect. |
| **view scope** | Gắn với một view-state trong thời gian flow ở state đó. Phù hợp với dữ liệu phục vụ màn hình hiện tại. |
| **flow scope** | Tồn tại trong suốt một flow execution. Phù hợp với dữ liệu nghiệp vụ cần dùng qua nhiều view-state, chẳng hạn đối tượng đặt chỗ. |
| **conversation scope** | Có thể chia sẻ dữ liệu giữa flow cha và subflow trong cùng conversation theo cách cấu hình của ứng dụng. Dùng khi nhiều flow liên quan cần trao đổi dữ liệu. |
| **session scope** | Tồn tại theo HTTP session của người dùng và có thể được chia sẻ giữa nhiều request hoặc flow. Chỉ lưu dữ liệu thực sự cần có phạm vi phiên. |

Ví dụ, đối tượng **booking** được giữ trong flow để người dùng có thể nhập dữ liệu ở một view-state và rà soát ở view-state tiếp theo. Không nên chỉ đặt dữ liệu này vào request attribute rồi kỳ vọng nó còn sau redirect.

~~~xml
<var name="booking" class="com.example.booking.Booking"/>

<view-state id="enterDetails"
            view="booking/enterDetails"
            model="booking"
            redirect="true">
    <transition on="submit" to="reviewBooking"/>
</view-state>

<view-state id="reviewBooking"
            view="booking/review"
            redirect="true">
    <transition on="confirm" to="complete"/>
</view-state>
~~~

Biến được khai báo cho flow có vòng đời gắn với flow execution, do đó dữ liệu vẫn sẵn sàng khi trình duyệt gửi request tiếp theo để tiếp tục flow. Dữ liệu trong request scope thì không có bảo đảm tương tự.

Redirect cũng không tự động làm mất view scope hay flow scope. Spring Web Flow lưu trạng thái thực thi theo cơ chế flow execution của nó. Dữ liệu sẽ được giữ theo đúng vòng đời scope, miễn là ứng dụng tiếp tục đúng flow execution và không kết thúc hoặc khởi tạo lại flow.

## 6. Redirect, binding và validation

Khi người dùng gửi form, Spring Web Flow thực hiện binding dữ liệu vào model và chạy validation theo cấu hình của flow. Nếu dữ liệu không hợp lệ, flow thường ở lại view-state để hiển thị lỗi và cho phép người dùng sửa.

Một số nguyên tắc cần nhớ:

- Đặt model ở scope có vòng đời phù hợp với flow; không phụ thuộc request attribute để lưu dữ liệu form qua các request.
- Để validation chạy trước các thao tác nghiệp vụ quan trọng. Không chuyển sang state xác nhận nếu dữ liệu không hợp lệ.
- Thông báo lỗi cần được hiển thị lại trên view tương ứng. Kiểm thử cả đường đi thành công lẫn đường đi validation thất bại.
- Không giả định redirect sẽ tự giải quyết lỗi binding hoặc validation. Cần xác nhận hành vi thực tế của phiên bản Spring Web Flow, view-state và cấu hình binding đang dùng.

Ví dụ, nếu người dùng nhập email không hợp lệ, flow cần giữ người dùng ở màn hình nhập thông tin và hiển thị lỗi. Khi sửa dữ liệu và gửi lại, flow mới chuyển đến màn hình rà soát. Redirect là chính sách điều hướng HTTP; quy tắc validation vẫn do model, validator và cấu hình flow quyết định.

## 7. Redirect và các thao tác có tác dụng phụ

PRG làm giảm việc trình duyệt gửi lại POST khi refresh trang kết quả, nhưng không bảo đảm một thao tác nghiệp vụ chỉ được thực hiện đúng một lần. Một request có thể bị gửi lại do người dùng nhấn nút nhiều lần, mạng chập chờn, client retry hoặc một luồng xử lý bị gọi lặp.

Các thao tác như tạo đơn hàng, giữ chỗ, trừ tiền, gửi email hoặc gọi dịch vụ bên ngoài cần được bảo vệ ở tầng nghiệp vụ:

- Kiểm tra trạng thái hiện tại trước khi thực hiện thao tác.
- Dùng mã giao dịch hoặc idempotency key để nhận diện yêu cầu lặp.
- Lưu kết quả xử lý và trả lại kết quả cũ khi cùng một yêu cầu được gửi lại.
- Chỉ thực hiện thao tác ghi tại transition hoặc action phù hợp, tránh đặt thao tác ghi không idempotent trong logic render view.

Đặc biệt, các action gắn với việc vào state hoặc render view cần được thiết kế cẩn thận. Việc hiển thị lại view có thể xảy ra khi người dùng quay lại, gửi lại event hoặc tiếp tục flow. Logic hiển thị nên an toàn khi được gọi lại; thao tác ghi dữ liệu cần có kiểm soát riêng.

## 8. Những nhầm lẫn thường gặp

### Nghĩ redirect sẽ tạo flow mới

Redirect khi vào view-state tiếp tục flow execution hiện tại. Nó không đồng nghĩa với việc bắt đầu một flow mới. Dữ liệu thuộc flow scope vẫn được quản lý theo flow execution đó.

### Nghĩ redirect thay thế transition

Redirect chỉ quyết định cách trình duyệt nhận view sau khi flow vào state. Transition vẫn chịu trách nhiệm xác định event và state đích. Một redirect không thể thay thế khai báo transition.

### Tắt redirect nhưng vẫn kỳ vọng refresh an toàn

Nếu view được render trực tiếp từ POST, refresh có thể gửi lại POST. Hãy bật redirect cho màn hình kết quả sau thao tác ghi hoặc bảo vệ nghiệp vụ bằng xử lý idempotent.

### Lưu dữ liệu qua request attribute

Request mới sau redirect không tự mang theo request attribute của request trước. Dùng flow scope, view scope hoặc cơ chế lưu trữ phù hợp với vòng đời dữ liệu.

### Cho rằng redirect ngăn mọi yêu cầu trùng lặp

Redirect chỉ điều chỉnh chu trình điều hướng của trình duyệt. Nó không thay thế khóa nghiệp vụ, kiểm tra trạng thái hoặc idempotency ở backend.

### Nhầm redirect của view-state với điều hướng đến website bên ngoài

Thuộc tính **redirect** của view-state phục vụ việc tiếp tục flow tại view-state đó. Nếu nghiệp vụ cần đưa người dùng sang một website bên ngoài, cần dùng cơ chế điều hướng phù hợp với tích hợp đó; không coi redirect của view-state là một URL đích tùy ý.

## 9. Kiểm thử chính sách redirect

Nên kiểm thử chính sách redirect ở cấp tích hợp, nơi có thể quan sát request, response và trạng thái flow thực tế. Một bộ kiểm thử cơ bản cần bao gồm:

1. **Vào view-state với redirect bật.** Xác nhận phản hồi có trạng thái redirect và header Location trỏ đến URL tiếp tục flow.
2. **Theo redirect.** Gửi GET đến URL trong Location và xác nhận view mong đợi được render.
3. **Gửi form bằng POST.** Xác nhận event được nhận, binding và validation chạy, transition đưa flow đến state đích.
4. **Refresh trang kết quả.** Xác nhận trình duyệt thực hiện GET và không lặp lại thao tác ghi chỉ vì refresh.
5. **Kiểm thử redirect tắt.** Xác nhận view được render trong request hiện tại và đánh giá rõ hành vi khi refresh, đặc biệt nếu request ban đầu là POST.
6. **Kiểm tra dữ liệu qua nhiều state.** Xác nhận dữ liệu flow scope vẫn có ở state tiếp theo và dữ liệu request scope không bị dùng nhầm như dữ liệu bền vững.
7. **Kiểm tra validation thất bại.** Xác nhận người dùng vẫn thấy form và thông báo lỗi, không bị chuyển nhầm sang state thành công.
8. **Kiểm tra gửi event lặp.** Xác nhận các thao tác nghiệp vụ không tạo kết quả trùng khi request bị gửi lại.

Khi kiểm thử response redirect, không chỉ kiểm tra mã trạng thái. Cần theo Location đến request tiếp theo, vì lỗi có thể nằm ở URL flow execution, cấu hình mapping, view resolver hoặc dữ liệu không còn trong scope phù hợp.

## 10. Quy trình chọn chính sách cho một view-state

Trước khi đặt giá trị redirect, hãy trả lời lần lượt các câu hỏi:

1. View-state được vào sau một GET hay sau khi xử lý POST?
2. Request vừa xử lý có thực hiện thao tác ghi hoặc tạo tác dụng phụ không?
3. Người dùng có thể refresh, bookmark hoặc mở lại màn hình kết quả không?
4. Dữ liệu cần hiển thị ở view tiếp theo đang nằm trong flow scope, view scope hay chỉ trong request?
5. Có lý do thực tế nào cần render ngay trong request hiện tại không?

Nếu view-state là màn hình kết quả sau khi xử lý POST, thông thường nên dùng **redirect=\"true\"** để áp dụng PRG. Nếu view-state chỉ render một màn hình đọc sau GET, có thể cân nhắc **redirect=\"false\"** khi muốn tránh request bổ sung và đã hiểu rõ hành vi điều hướng. Với màn hình có thao tác ghi, hãy ưu tiên chính sách redirect rõ ràng và đồng thời bảo vệ nghiệp vụ khỏi request lặp.

## 11. Ghi nhớ

Thuộc tính **redirect** của view-state điều khiển cách Spring Web Flow trả view khi flow đi vào state. Bật redirect giúp hình thành POST-Redirect-GET và làm cho refresh trang kết quả thường gửi lại GET. Tắt redirect render view ngay trong request hiện tại và cần thận trọng nếu request đó là POST.

Redirect không thay thế transition, validation hay cơ chế chống giao dịch trùng. Khi thiết kế flow, hãy giữ dữ liệu ở scope phù hợp, để thao tác ghi có tính idempotent và kiểm thử toàn bộ chu trình từ event POST đến request GET tiếp theo. Nhờ vậy, hành trình nhiều bước tích hợp Spring MVC hoạt động ổn định khi người dùng điều hướng, refresh hoặc tiếp tục phiên flow.
