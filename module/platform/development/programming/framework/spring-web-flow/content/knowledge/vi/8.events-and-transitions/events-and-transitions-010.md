# Thứ tự xét các transition và trường hợp không khớp

## 1. Transition được chọn như thế nào?

Trong Spring Web Flow, một state có thể nhận nhiều event và mỗi event có thể dẫn tới một state tiếp theo khác nhau. Ví dụ, màn hình xem lại đơn hàng có thể nhận event confirm, edit hoặc cancel. Mỗi transition mô tả điều kiện để phản hồi một event và đích đến của luồng.

Khi một event được phát sinh trong state hiện tại, Web Flow xét các transition được khai báo cho state đó. Với các transition event thông thường, **transition đầu tiên có criteria khớp sẽ được chọn**. Những transition nằm sau transition đã khớp không tiếp tục được xét cho event đó.

Vì vậy, thứ tự khai báo có ảnh hưởng trực tiếp tới hành vi. Transition cụ thể nên được đặt trước transition tổng quát. Nếu đặt wildcard on="*" quá sớm, nó có thể nhận mọi event và che khuất các transition cụ thể phía sau.

Bài học này thuộc chương **Event và transition** của module **SPRING_WEB_FLOW**. Trong một hành trình nhiều bước được mô hình hóa bằng state, event, transition và subflow, quy tắc chọn transition giúp điều hướng có thể dự đoán, tránh event bị xử lý sai và giúp flow phản hồi có kiểm soát khi nhận event không mong đợi. Quy tắc này cũng quan trọng khi tích hợp form binding, validation và xử lý lỗi trong Spring MVC.

## 2. Event và criteria của transition

Một event biểu diễn điều gì vừa xảy ra trong flow. Event có một ID để flow dùng khi đối chiếu transition. Event có thể xuất phát từ thao tác trên view, chẳng hạn người dùng bấm nút continue, hoặc từ một action trong flow trả về kết quả như success hay error.

Ví dụ, form xem lại đơn hàng có thể phát sinh các event:

| Event ID | Ý nghĩa nghiệp vụ | Hành vi mong muốn |
| --- | --- | --- |
| confirm | Người dùng xác nhận đơn hàng | Chuyển tới bước hoàn tất |
| edit | Người dùng muốn sửa thông tin giao hàng | Quay lại màn hình giao hàng |
| cancel | Người dùng hủy quy trình | Đi tới trạng thái kết thúc hủy |
| help | Người dùng yêu cầu trợ giúp | Hiển thị hướng dẫn |
| Một ID ngoài dự kiến | View hoặc action phát ra event chưa được dự liệu | Đi tới nhánh xử lý event không mong đợi hoặc báo lỗi có kiểm soát |

Transition thường dùng thuộc tính on để chỉ event ID cần khớp và to để chỉ state đích:

~~~xml
<transition on="confirm" to="complete"/>
~~~

Trong ví dụ này, transition chỉ phù hợp khi event hiện tại có ID confirm. Việc khớp event ID không tự xác nhận rằng dữ liệu nghiệp vụ hợp lệ. Kiểm tra quyền, trạng thái đơn hàng và validation vẫn cần được thực hiện theo đúng trách nhiệm của action hoặc service.

Một transition có thể dùng wildcard:

~~~xml
<transition on="*" to="unexpectedEvent"/>
~~~

on="*" là tiêu chí tổng quát, có thể khớp event ID bất kỳ. Vì vậy, nó thường được dùng làm nhánh dự phòng cuối danh sách. Wildcard không có nghĩa là “bỏ qua event”; nó vẫn thực hiện transition tới state đích đã khai báo.

## 3. Quy tắc first-match và thứ tự khai báo

Giả sử state review có ba event hợp lệ và một nhánh dự phòng. Thứ tự khai báo nên là:

1. Các event cụ thể, như confirm, edit, cancel.
2. Các criteria cụ thể khác nếu state có sử dụng.
3. Wildcard on="*" ở cuối để nhận event còn lại.

Ví dụ:

~~~xml
<view-state id="review" view="checkout/review">
    <transition on="confirm" to="complete"/>
    <transition on="edit" to="shipping"/>
    <transition on="cancel" to="cancelled"/>
    <transition on="*" to="unexpectedEvent"/>
</view-state>
~~~

Khi event confirm đến, transition đầu tiên khớp và flow đi tới complete. Event edit khớp transition thứ hai và quay về shipping. Event cancel khớp transition thứ ba. Những event khác được chuyển tới unexpectedEvent.

Có thể biểu diễn việc chọn transition như sau:

~~~mermaid
flowchart TD
    A["State hiện tại nhận event"] --> B["Xét transition theo thứ tự khai báo"]
    B --> C{"Criteria có khớp?"}
    C -- "Không" --> D{"Còn transition?"}
    D -- "Có" --> E["Chuyển sang transition kế tiếp"]
    E --> B
    C -- "Có" --> F["Chọn transition đầu tiên khớp"]
    F --> G["Thực hiện transition và tới state đích"]
    D -- "Không" --> H["Không có transition phù hợp"]
~~~

Sơ đồ thể hiện nguyên tắc first-match: criteria không khớp thì tiếp tục xét; criteria đầu tiên khớp quyết định đường đi. Nếu không còn transition nào phù hợp, flow không có đường chuyển tiếp cho event đó.

### 3.1. Wildcard đặt sai vị trí

Đoạn sau có lỗi về thứ tự:

~~~xml
<view-state id="review" view="checkout/review">
    <transition on="*" to="unexpectedEvent"/>
    <transition on="confirm" to="complete"/>
    <transition on="edit" to="shipping"/>
</view-state>
~~~

Vì wildcard đứng đầu, event confirm cũng khớp transition đầu tiên. Transition tới complete không được chọn. Kết quả là event xác nhận đơn hàng lại đi vào nhánh event không mong đợi.

Sửa bằng cách đưa wildcard xuống cuối:

~~~xml
<view-state id="review" view="checkout/review">
    <transition on="confirm" to="complete"/>
    <transition on="edit" to="shipping"/>
    <transition on="*" to="unexpectedEvent"/>
</view-state>
~~~

Khi đọc một flow XML, hãy kiểm tra thứ tự từ trên xuống, đặc biệt khi có wildcard hoặc criteria rộng. Đừng chỉ nhìn thấy transition confirm tồn tại rồi kết luận event confirm chắc chắn tới đúng state.

### 3.2. Transition trùng criteria

Nếu hai transition cùng khớp một event ID, transition được khai báo trước sẽ thắng theo nguyên tắc first-match. Transition phía sau trở thành nhánh không thể được chọn cho event đó trong điều kiện criteria trùng nhau.

Ví dụ:

~~~xml
<transition on="confirm" to="complete"/>
<transition on="confirm" to="manualReview"/>
~~~

Với event confirm, transition tới complete được chọn. Nếu muốn chuyển sang manualReview trong một số điều kiện nghiệp vụ, hãy mô hình hóa điều kiện đó một cách tường minh, ví dụ bằng action hoặc decision-state để xác định nhánh trước khi phát event/điều hướng. Không nên để hai transition cùng event ID rồi kỳ vọng Web Flow tự suy luận theo ý định nghiệp vụ.

## 4. Trường hợp không có transition nào khớp

Một state có thể nhận event mà không transition nào của state đó chấp nhận. Ví dụ, state chỉ khai báo confirm và cancel, nhưng view hoặc action lại phát event retry.

~~~xml
<view-state id="review" view="checkout/review">
    <transition on="confirm" to="complete"/>
    <transition on="cancel" to="cancelled"/>
</view-state>
~~~

Nếu event retry được gửi tới state này, không có criteria event nào khớp. Web Flow không tự đoán state đích, cũng không mặc nhiên bỏ qua event như thể xử lý thành công. Trong trường hợp event cần được điều hướng nhưng không có transition phù hợp, quá trình xử lý flow có thể phát sinh NoMatchingTransitionException.

Hệ quả là request không đi tiếp theo một transition bình thường. Ngoại lệ có thể được xử lý bởi cơ chế xử lý lỗi của ứng dụng hoặc tầng tích hợp; nếu không có cách xử lý phù hợp, người dùng có thể nhận lỗi thay vì được đưa về một màn hình hợp lý.

Cần phân biệt hai trường hợp:

- **Không có transition khớp:** flow không tìm được đường đi cho event hiện tại.
- **Có transition khớp nhưng xử lý thất bại:** transition đã được chọn, nhưng action, binding, validation hoặc logic nghiệp vụ trong quá trình xử lý có thể thất bại.

Hai trường hợp cần cách điều tra khác nhau. Với lỗi không khớp, hãy kiểm tra event ID, state hiện tại và danh sách transition. Với lỗi xử lý sau khi đã khớp, hãy kiểm tra action, validation, service và exception phát sinh.

## 5. Thiết kế nhánh dự phòng cho event không mong đợi

Nếu state cần tiếp nhận event chưa biết trước, có thể khai báo wildcard ở cuối để đưa flow tới một state xử lý phù hợp:

~~~xml
<view-state id="review" view="checkout/review">
    <transition on="confirm" to="complete"/>
    <transition on="edit" to="shipping"/>
    <transition on="cancel" to="cancelled"/>
    <transition on="*" to="unexpectedEvent"/>
</view-state>

<view-state id="unexpectedEvent" view="common/unexpected-event">
    <transition on="back" to="review"/>
    <transition on="restart" to="start"/>
</view-state>
~~~

State unexpectedEvent có thể hiển thị thông báo dễ hiểu và cung cấp lựa chọn quay lại hoặc bắt đầu lại. Tùy nghiệp vụ, nhánh này cũng có thể chuyển tới một action-state để ghi nhận sự kiện bất thường, sau đó quyết định có thể phục hồi hay cần kết thúc flow.

Một nhánh dự phòng tốt nên đáp ứng các yêu cầu sau:

- Không thực hiện thao tác nghiệp vụ quan trọng chỉ vì event không được nhận diện.
- Không coi event lạ là xác nhận, thanh toán hoặc chấp thuận.
- Hiển thị thông báo không tiết lộ chi tiết nội bộ.
- Ghi log đủ để chẩn đoán, chẳng hạn flow ID, state hiện tại và event ID; tránh ghi dữ liệu cá nhân hoặc bí mật không cần thiết.
- Cho phép người dùng quay lại bước an toàn hoặc bắt đầu lại khi phù hợp.

Không phải state nào cũng cần wildcard. Nếu state chỉ có một tập event nhỏ và rõ ràng, để event ngoài hợp đồng phát hiện lỗi có thể hữu ích trong quá trình phát triển. Với flow phục vụ người dùng cuối, cần quyết định rõ ứng dụng muốn trả lỗi có kiểm soát hay cung cấp nhánh dự phòng. Quyết định này nên nhất quán trong toàn hành trình.

## 6. Event wildcard không thay thế xử lý exception

Wildcard on="*" khớp event ID. Nó không phải cơ chế bắt mọi exception Java. Nếu một action ném exception, đó là tình huống lỗi trong quá trình thực thi, không đơn thuần là một event ID không được khai báo.

Spring Web Flow hỗ trợ tiêu chí transition theo exception bằng thuộc tính on-exception trong những trường hợp phù hợp. Ví dụ minh họa:

~~~xml
<transition
    on-exception="com.example.order.InvalidOrderException"
    to="invalidOrder"/>
~~~

Transition trên mô tả nhánh cho loại exception cụ thể. Nó có ý nghĩa khác với:

~~~xml
<transition on="*" to="unexpectedEvent"/>
~~~

Không nên dùng wildcard event để kỳ vọng bắt exception. Hãy thiết kế exception handling theo loại lỗi, phạm vi có thể phục hồi và chính sách của ứng dụng. Lỗi nghiệp vụ có thể phục hồi nên được trình bày thành thông báo phù hợp; lỗi hạ tầng hoặc lỗi lập trình cần được ghi nhận và xử lý theo chính sách lỗi chung.

## 7. Quan hệ với validation và form binding

Trong một view-state, người dùng có thể gửi form và tạo event như submit. Transition có thể tồn tại và khớp event submit, nhưng binding hoặc validation vẫn có thể ngăn flow đi tiếp nếu dữ liệu không hợp lệ.

Ví dụ rút gọn:

~~~xml
<view-state id="shipping" view="checkout/shipping">
    <transition on="continue" to="review" validate="true"/>
</view-state>
~~~

Ví dụ giả định view-state đã có validator phù hợp trong cấu hình ứng dụng. Khi event continue khớp transition, Web Flow thực hiện binding và validation theo cấu hình; nếu dữ liệu không hợp lệ, flow giữ người dùng ở bước biểu mẫu để sửa dữ liệu. Đây không phải trường hợp “không có transition khớp”.

Khi chẩn đoán một form không chuyển màn hình, hãy kiểm tra theo thứ tự:

1. Nút submit có phát đúng event ID mà flow khai báo không?
2. Event có tới đúng flow execution và đúng view-state không?
3. Transition tương ứng có bị một criteria tổng quát đứng trước che khuất không?
4. Binding có chuyển dữ liệu vào model đúng không?
5. Validation có lỗi khiến transition bị ngăn không?
6. Action hoặc service có ném exception không?

Cách kiểm tra này giúp phân biệt lỗi định tuyến event với lỗi dữ liệu biểu mẫu hoặc lỗi nghiệp vụ.

## 8. Event do action và decision-state

Không phải mọi event đều đến từ thao tác người dùng. Một action trong flow có thể trả về event ID, ví dụ success, notFound hoặc failed. State chứa action có thể định tuyến theo các event đó. Quy tắc thứ tự transition vẫn quan trọng nếu nhiều criteria cùng có khả năng khớp.

~~~xml
<action-state id="loadOrder">
    <evaluate expression="orderService.load(orderId)" result="flowScope.order"/>
    <transition on="success" to="review"/>
    <transition on="notFound" to="orderNotFound"/>
    <transition on="*" to="loadError"/>
</action-state>
~~~

Trong ví dụ, kết quả action success và notFound có đường đi cụ thể; event còn lại đi tới loadError. Wildcard được đặt cuối để không che hai event đã biết.

decision-state giải quyết một nhu cầu khác: chọn nhánh dựa trên biểu thức điều kiện thay vì chờ một event ID từ người dùng hoặc action. Ví dụ:

~~~xml
<decision-state id="checkEligibility">
    <if test="flowScope.order.total > 1000"
        then="manualReview"
        else="automaticApproval"/>
</decision-state>
~~~

Dùng decision-state khi cần phân nhánh theo dữ liệu hoặc điều kiện nghiệp vụ. Dùng transition khi cần phản hồi event trong state. Tách hai ý định này giúp flow dễ đọc và giảm việc tạo event giả chỉ để biểu diễn một phép so sánh.

## 9. Kiểm thử thứ tự và trường hợp không khớp

Kiểm thử transition nên kiểm tra kết quả quan sát được: event nào được gửi, state nào được chọn và dữ liệu nào được giữ lại. Không chỉ kiểm tra rằng XML có chứa các dòng transition mong muốn.

Một ma trận kiểm thử cho state review có thể như sau:

| Event gửi vào | Transition mong đợi | State đích |
| --- | --- | --- |
| confirm | Transition cụ thể confirm | complete |
| edit | Transition cụ thể edit | shipping |
| cancel | Transition cụ thể cancel | cancelled |
| help | Wildcard dự phòng | unexpectedEvent |
| retry khi không có wildcard | Không có transition khớp | Kiểm tra lỗi không khớp |

Nên bổ sung các trường hợp sau:

- Đặt wildcard trước transition cụ thể trong một fixture kiểm thử để chứng minh event cụ thể bị wildcard nhận trước; sau đó sửa thứ tự và xác nhận state đích đúng.
- Khai báo hai transition có cùng event ID và xác nhận transition đầu tiên được chọn.
- Gửi event không được khai báo khi không có wildcard và xác nhận cơ chế lỗi không khớp được quan sát đúng.
- Gửi event không được khai báo khi có wildcard và xác nhận flow đi tới state dự phòng.
- Gửi event hợp lệ nhưng dữ liệu form sai để chứng minh lỗi validation khác với lỗi không có transition.
- Cho action phát event success, notFound và một event bất thường để kiểm tra từng nhánh.

Có thể sử dụng các tiện ích kiểm thử Spring Web Flow để khởi chạy flow, gửi event và xác nhận state hiện tại. Khi kiểm thử tích hợp Spring MVC, cần xác nhận tên event mà form thực sự gửi trùng với ID được khai báo trong flow.

## 10. Quy trình điều tra khi flow đi sai nhánh

Khi người dùng báo rằng nút “Xác nhận” lại đi tới màn hình lỗi, hoặc flow không chuyển bước, hãy kiểm tra theo trình tự:

1. **Xác định state hiện tại.** Xem flow execution đang ở state nào tại thời điểm nhận request.
2. **Xác định event ID thực tế.** Đối chiếu ID do view hoặc action phát ra với giá trị on trong XML. Kiểm tra chính tả và chữ hoa/chữ thường.
3. **Liệt kê transition theo thứ tự.** Đọc từ trên xuống và tìm criteria đầu tiên có thể khớp.
4. **Tìm criteria tổng quát.** Kiểm tra on="*" hoặc criteria rộng được khai báo trước transition cụ thể.
5. **Xác nhận state đích.** Đảm bảo transition được chọn trỏ tới state tồn tại và phù hợp với flow.
6. **Phân loại lỗi sau khi chọn.** Nếu transition đã khớp, kiểm tra binding, validation, action, service và exception.
7. **Kiểm tra nhánh phục hồi.** Xác nhận event lạ hoặc lỗi nghiệp vụ được đưa tới thông báo, retry hay kết thúc phù hợp.

Một log chẩn đoán hữu ích có thể ghi flow ID, state ID, event ID và correlation ID của request. Không ghi toàn bộ payload biểu mẫu hoặc thông tin xác thực vào log chỉ để tìm lỗi định tuyến.

## 11. Nguyên tắc thiết kế dễ bảo trì

- Đặt transition cụ thể trước transition tổng quát.
- Chỉ dùng wildcard khi đã xác định rõ cách xử lý event chưa biết.
- Không để hai transition trùng criteria nếu không có chủ đích rõ ràng; transition đầu tiên sẽ chi phối.
- Đặt tên event theo hành động hoặc kết quả nghiệp vụ, dùng nhất quán giữa view, action và flow XML.
- Dùng decision-state cho nhánh dựa trên điều kiện; dùng transition để phản hồi event.
- Phân biệt event không khớp, validation thất bại và exception trong action.
- Kiểm thử cả đường đi hợp lệ lẫn event ngoài dự kiến.
- Khi thay đổi thứ tự transition, kiểm thử lại các event cụ thể và nhánh wildcard vì thứ tự có thể thay đổi kết quả runtime.

Trong Spring Web Flow, transition là một phần của mô hình điều khiển hành trình. Khi hiểu quy tắc first-match và chủ động thiết kế nhánh không khớp, flow sẽ điều hướng rõ ràng hơn, dễ kiểm thử hơn và phản hồi an toàn hơn khi nhận event ngoài dự kiến.

