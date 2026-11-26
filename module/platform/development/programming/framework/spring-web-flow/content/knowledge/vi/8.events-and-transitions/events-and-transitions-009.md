# Transition cục bộ và global-transitions

*Chương: Event và transition · Module: SPRING_WEB_FLOW*

Trong Spring Web Flow, event cho biết điều gì vừa xảy ra, còn transition xác định flow sẽ chuyển sang state nào để phản hồi event đó. Một hành trình nhiều bước thường có các event riêng cho từng màn hình, chẳng hạn **continue**, **back** hoặc **confirm**. Đồng thời, có những event mang ý nghĩa chung ở nhiều bước, chẳng hạn **cancel**. Spring Web Flow cho phép khai báo transition ngay trong state hoặc gom transition dùng chung vào phần **global-transitions** của flow.

Module SPRING_WEB_FLOW tập trung mô hình hóa hành trình web bằng state, event, transition và subflow, kết hợp form binding, validation, scope, phiên làm việc, Spring MVC, kiểm thử và phục hồi khi luồng gặp lỗi. Bài học này giúp bạn quyết định transition nào nên gắn với một state cụ thể, transition nào nên dùng chung cho cả flow, cách Spring Web Flow chọn transition khi các phạm vi cùng có thể xử lý một event và cách kiểm thử các nhánh đó.

Sau bài học, bạn có thể:

- Giải thích phạm vi của transition cục bộ và transition toàn cục.
- Khai báo transition bên trong state và trong global-transitions.
- Mô tả cách xử lý khi một event khớp cả transition cục bộ lẫn toàn cục.
- Thiết kế event dùng chung như hủy quy trình mà vẫn giữ được hành vi riêng của từng state.
- Tránh lạm dụng global transition làm cho quy trình khó hiểu hoặc bỏ qua bước nghiệp vụ cần thiết.
- Kiểm thử đường đi cục bộ, đường đi toàn cục, trường hợp ghi đè và event không được hỗ trợ.

## 1. Event và transition trong một flow

Flow definition mô tả các state mà một hành trình có thể đi qua. Khi flow đang ở một state, nó nhận event và tìm transition phù hợp. Transition thường xác định hai thông tin: event cần khớp qua thuộc tính on và state đích qua thuộc tính to.

Ví dụ, một quy trình đặt hàng có thể có các state:

1. cart: người dùng xem giỏ hàng.
2. shipping: người dùng nhập địa chỉ giao hàng.
3. review: người dùng kiểm tra lại đơn hàng.
4. completed: đơn hàng đã được xác nhận.

Ở state cart, event continue đưa flow tới shipping. Ở state shipping, cùng event continue đưa flow tới review. Event back tại shipping quay về cart; event confirm tại review bắt đầu thao tác lưu đơn hàng.

Sơ đồ sau minh họa những chuyển tiếp riêng của từng state và một đường hủy có thể dùng chung:

~~~mermaid
flowchart TD
    A[cart] -->|continue| B[shipping]
    B -->|continue| C[review]
    B -->|back| A
    C -->|confirm| D[completed]
    C -->|cancel cục bộ| E[confirmCancel]
    A -. cancel toàn cục .-> F[cancelled]
    B -. cancel toàn cục .-> F
    E -->|confirm| F
    E -->|keep| C
~~~

Event không tự quyết định state đích. Ý nghĩa của event phụ thuộc vào transition có thể được chọn tại state hiện tại. Vì thế, continue có thể dẫn tới các bước khác nhau ở các state khác nhau mà không cần tạo nhiều tên event như continueFromCart và continueFromShipping.

## 2. Transition cục bộ

Transition cục bộ (local transition) được khai báo bên trong định nghĩa của một state. Nó chỉ có hiệu lực khi flow đang ở state chứa transition đó. Đây là lựa chọn mặc định cho các bước điều hướng thuộc riêng một màn hình hoặc một phần của quy trình.

Ví dụ:

~~~xml
<view-state id="cart" view="checkout/cart">
    <transition on="continue" to="shipping"/>
</view-state>

<view-state id="shipping" view="checkout/shipping">
    <transition on="back" to="cart"/>
    <transition on="continue" to="review"/>
</view-state>

<view-state id="review" view="checkout/review">
    <transition on="confirm" to="saveOrder"/>
</view-state>
~~~

Trong ví dụ:

- continue tại cart chỉ có nghĩa là đi tới shipping.
- continue tại shipping có nghĩa là đi tới review.
- back chỉ được khai báo tại shipping, vì vậy đây là hành động thuộc bước nhập địa chỉ.
- confirm chỉ có hiệu lực tại review, nơi người dùng đã có đủ thông tin để xác nhận.

Local transition làm cho hành vi của state được đọc ngay tại nơi state được khai báo. Khi xem một view-state, người đọc có thể biết màn hình đó nhận event nào và mỗi event dẫn tới đâu. Điều này đặc biệt hữu ích khi cùng một event name được tái sử dụng ở nhiều state nhưng có đích đến khác nhau.

Transition cũng có thể chứa action cần chạy trong lúc chuyển state. Ví dụ, một thao tác tiếp tục có thể gọi validator hoặc service trước khi flow đi tiếp:

~~~xml
<view-state id="shipping" view="checkout/shipping">
    <transition on="continue" to="review">
        <evaluate expression="shippingService.prepareReview(flowScope.order)"/>
    </transition>
</view-state>
~~~

Action trong transition cần có trách nhiệm rõ ràng. Nếu thao tác có thể thất bại, hãy xác định cách lỗi được đưa về flow và view. Không nên đưa cả quy tắc nghiệp vụ dài vào biểu thức XML; hãy chuyển phần tính toán, kiểm tra dữ liệu hoặc truy cập hệ thống sang Spring bean.

Local transition phù hợp khi:

- Event chỉ hợp lệ tại một state hoặc một nhóm state cụ thể.
- Đích đến phụ thuộc vào dữ liệu hay bước hiện tại.
- Người dùng có thể quay lại một bước liền trước.
- Mỗi state có quy tắc xác nhận hoặc kiểm tra dữ liệu khác nhau.
- Nhóm phát triển cần nhìn thấy toàn bộ hành vi điều hướng của state ngay tại chỗ.

Nếu một event chỉ có ý nghĩa ở một bước, đừng đưa nó lên phạm vi toàn flow. Ví dụ, confirmPayment chỉ nên xuất hiện ở state xác nhận thanh toán, không nên là global transition vì các state khác không có ngữ cảnh để thực hiện hành động đó.

## 3. Global transitions

Global transition là transition được khai báo ở cấp flow, bên trong phần tử global-transitions. Nó có thể được sử dụng từ nhiều state trong cùng flow definition. Cách này phù hợp với những event có ý nghĩa xuyên suốt hành trình, chẳng hạn yêu cầu hủy quy trình.

Ví dụ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="cart" view="checkout/cart">
        <transition on="continue" to="shipping"/>
    </view-state>

    <view-state id="shipping" view="checkout/shipping">
        <transition on="back" to="cart"/>
        <transition on="continue" to="review"/>
    </view-state>

    <view-state id="review" view="checkout/review">
        <transition on="confirm" to="saveOrder"/>
        <transition on="cancel" to="confirmCancel"/>
    </view-state>

    <view-state id="confirmCancel" view="checkout/confirmCancel">
        <transition on="keep" to="review"/>
        <transition on="confirm" to="cancelled"/>
    </view-state>

    <action-state id="saveOrder">
        <evaluate expression="checkoutService.confirm(flowScope.order)"/>
        <transition to="completed"/>
    </action-state>

    <end-state id="completed" view="checkout/completed"/>
    <end-state id="cancelled" view="checkout/cancelled"/>

    <global-transitions>
        <transition on="cancel" to="cancelled"/>
    </global-transitions>
</flow>
~~~

Global transition cancel cung cấp một đường hủy mặc định cho các state trong flow. Tại cart và shipping, không có local transition cho event cancel, nên global transition xử lý event đó và đưa flow tới cancelled. Tại review, flow có local transition cancel tới confirmCancel; hành vi riêng của bước review được giữ lại. Khi người dùng xác nhận hủy ở màn hình này bằng event confirm, local transition đưa flow tới cancelled.

global-transitions không phải là một flow độc lập và cũng không phải cấu hình áp dụng cho toàn bộ ứng dụng. Nó thuộc về một flow definition cụ thể. Nếu ứng dụng có nhiều flow, mỗi flow cần khai báo các global transition mà chính nó hỗ trợ.

Global transition phù hợp với:

- Hủy hành trình từ nhiều bước.
- Một lối thoát chung khi người dùng chủ động rời khỏi quy trình.
- Một event điều hướng chung đã được định nghĩa rõ ràng cho mọi state liên quan.
- Một hành vi phục hồi có thể thực hiện an toàn ở nhiều vị trí trong flow.

Hãy cân nhắc kỹ trước khi đưa event vào phạm vi toàn cục. Việc khai báo một event toàn cục không tự tạo nút giao diện, không tự đặt bộ đếm thời gian và không tự phát event. View, thành phần tích hợp hoặc mã ứng dụng vẫn phải gửi event tới flow. Global transition chỉ quy định flow phản ứng ra sao khi event đó được nhận.

## 4. Cách Spring Web Flow chọn transition

Khi flow đang ở một state và nhận event, Spring Web Flow tìm transition phù hợp trong ngữ cảnh state hiện tại. Transition cục bộ được ưu tiên. Nếu state hiện tại không có local transition khớp event, flow mới sử dụng global transition tương ứng nếu có.

Có thể diễn đạt quy tắc này như sau:

~~~text
Flow đang ở state S và nhận event E
             |
             v
   Có local transition cho E?
        /           \
      Có             Không
      |                |
      v                v
 Chạy local       Có global transition
 transition          cho E?
                    /    \
                  Có      Không
                  |          |
                  v          v
             Chạy global   Không có
             transition    transition phù hợp
~~~

Quy tắc ưu tiên này cho phép flow định nghĩa một hành vi mặc định nhưng vẫn tùy biến tại các state cần xử lý đặc biệt. Trong ví dụ checkout, global cancel đưa người dùng rời khỏi quy trình; riêng review có local cancel để yêu cầu xác nhận trước.

Nếu local transition và global transition cùng khai báo event cancel, local transition của state hiện tại được chọn. Do đó, khi thêm local transition mới, hãy kiểm tra xem nó có chủ ý thay đổi hành vi mặc định hay không. Một thay đổi nhỏ trong state có thể khiến event vốn đi theo đường toàn cục chuyển sang đường cục bộ.

Nếu không có transition cục bộ hoặc toàn cục phù hợp, flow không có quy tắc để chuyển state theo event đó. Tùy điểm phát event và cách tích hợp, request có thể bị từ chối hoặc execution có thể phát sinh lỗi không có transition phù hợp. Không nên dựa vào hành vi mặc định này để điều khiển nghiệp vụ; hãy chỉ gửi các event mà state hiện tại được thiết kế để nhận và ghi log đủ thông tin khi có event ngoài dự kiến.

## 5. Gửi event từ view

View của Spring Web Flow gửi event tới flow execution đang hoạt động. Với JSP, một nút submit có thể sử dụng tên tham số theo quy ước _eventId_:

~~~jsp
<form method="post">
    <button type="submit" name="_eventId_continue">Tiếp tục</button>
    <button type="submit" name="_eventId_cancel">Hủy</button>
</form>
~~~

Nút Tiếp tục phát event continue; nút Hủy phát event cancel. Cùng một nút Hủy có thể xuất hiện ở nhiều view của cùng flow. Khi event tới flow, state hiện tại quyết định local transition nào có thể xử lý; nếu không có local transition phù hợp, global transition có thể được dùng.

Tên event trong view phải khớp với giá trị on trong flow definition. Ví dụ cancel và cancelOrder là hai event khác nhau. Nếu nút gửi cancelOrder nhưng flow chỉ khai báo on="cancel", transition đó sẽ không được chọn.

Với HTML, Thymeleaf hoặc JavaScript, cách tạo request có thể khác nhau tùy cách tích hợp. Dù dùng công nghệ view nào, cần bảo đảm request tiếp tục đúng flow execution, gửi đúng event và tuân theo cơ chế bảo vệ request của ứng dụng. Không tự ghép URL hoặc execution key theo cách bỏ qua cơ chế quản lý flow của Spring Web Flow.

## 6. Thiết kế event toàn cục mà không phá vỡ quy tắc nghiệp vụ

Global transition giúp giảm lặp lại XML, nhưng việc dùng chung event cũng tạo ra một hợp đồng: mọi state có thể nhận event đó phải có hành vi hợp lệ. Trước khi đưa event thành global, hãy xem xét các câu hỏi sau:

1. Event có thực sự mang cùng ý nghĩa ở mọi state cần hỗ trợ không?
2. Có state nào cần hỏi xác nhận, lưu nháp hoặc hoàn tác trước khi rời đi không?
3. Có thao tác nào phải hoàn tất trước khi chuyển tới state đích không?
4. Event có thể xảy ra trong khi một thao tác đang chạy hoặc dữ liệu chưa được khởi tạo không?
5. Khi người dùng gửi event lặp lại, hành vi có an toàn và nhất quán không?

Ví dụ, event cancel có thể hủy quy trình nhập thông tin ở cart và shipping. Nhưng tại review, người dùng đã dành thời gian xem lại đơn hàng; sản phẩm có thể yêu cầu một màn hình xác nhận. Khi đó local transition tại review ghi đè hành vi toàn cục để mở confirmCancel.

Không nên dùng một global transition để bỏ qua bước giải phóng tài nguyên hoặc hoàn tác thay đổi. Nếu quy trình đã giữ chỗ, tạo bản ghi tạm hoặc mở transaction, việc hủy cần gọi service chịu trách nhiệm xử lý các tác động đó. Hãy xác định rõ điểm chạy cleanup, bảo đảm thao tác có thể được gọi an toàn khi flow kết thúc theo các nhánh khác nhau và tránh giải phóng tài nguyên đã được xác nhận thành công.

Một số quy tắc tổ chức event:

- Dùng event cụ thể, dễ hiểu như cancel, back, continue, confirm.
- Dành global transition cho hành vi thực sự dùng chung, không dùng chỉ để giảm vài dòng XML.
- Giữ các event nghiệp vụ như approvePayment, submitAddress ở local transition của state có đủ ngữ cảnh.
- Tránh để nhiều global transition cùng cạnh tranh xử lý một event.
- Khi local transition ghi đè global transition, ghi chú lý do ngay trong flow hoặc tài liệu thiết kế.
- Đặt tên state đích thể hiện rõ kết quả, ví dụ cancelled, completed hoặc recovery.

## 7. Global transitions và subflow

Mỗi flow definition có phạm vi global transition riêng. Khi flow cha khởi chạy subflow, subflow chạy theo định nghĩa và state của chính nó. Vì vậy, không nên giả định global transition của flow cha sẽ thay thế quy tắc xử lý event bên trong flow con.

Ví dụ, flow checkout gọi subflow địa chỉ:

~~~xml
<subflow-state id="collectAddress" subflow="address">
    <input name="customer" value="flowScope.customer"/>
    <transition on="completed" to="review"/>
    <transition on="cancelled" to="cart"/>
</subflow-state>
~~~

Flow address cần định nghĩa cách xử lý các event của riêng nó, bao gồm event hủy nếu subflow hỗ trợ. Khi subflow kết thúc và trả event cancelled, flow cha đang ở collectAddress mới xử lý event kết thúc đó bằng transition cục bộ tương ứng. Đây là hợp đồng giữa hai flow: tên subflow, input, event kết thúc và output cần được thống nhất.

Nếu cùng một ý nghĩa hủy được hỗ trợ ở cả flow cha và flow con, hãy khai báo và kiểm thử hành vi tại từng flow. Việc lặp lại một tên event không làm hai flow tự động chia sẻ transition hoặc scope.

## 8. Transition toàn cục và phục hồi lỗi

Một event hủy do người dùng gửi và một exception do service ném ra là hai tình huống khác nhau. Global transition cho event chỉ được chạy khi flow nhận event tương ứng. Nó không tự bắt mọi exception và cũng không thay thế cơ chế xử lý lỗi của Spring hoặc của ứng dụng.

Khi service trong transition phát sinh lỗi, cần xác định lỗi thuộc loại nào:

- Dữ liệu người dùng không hợp lệ: đưa thông báo về view phù hợp và cho phép sửa dữ liệu.
- Điều kiện nghiệp vụ không còn đúng, ví dụ hết hàng: giữ flow ở bước có thể giải thích tình trạng và cho phép chọn phương án khác.
- Lỗi hệ thống tạm thời: ghi log, bảo toàn dữ liệu cần thiết và đưa người dùng tới nhánh thử lại hoặc thông báo phù hợp.
- Flow execution hết hạn hoặc không còn tồn tại: xử lý như một tình huống khôi phục phiên, không giả định global transition của execution cũ vẫn có thể chạy.

Nếu phiên bản Spring Web Flow và cách cấu hình của dự án hỗ trợ transition theo exception, có thể dùng cơ chế đó để định tuyến một nhóm exception đã xác định tới state lỗi. Cần khai báo rõ loại exception, phạm vi bắt lỗi và hành động khôi phục. Không nên bắt mọi exception rồi chuyển thẳng tới một end state thành công hoặc bỏ qua lỗi ghi dữ liệu.

Một flow có thể có global transition cho event cancel và một cơ chế riêng để xử lý lỗi. Tách hai ý nghĩa này giúp người đọc hiểu rõ người dùng chủ động hủy khác với hệ thống không thể tiếp tục.

## 9. Kiểm thử local và global transition

Kiểm thử transition nên xác minh state trước khi gửi event, event được gửi và state sau khi flow xử lý. Với Spring Web Flow, có thể dùng bộ hỗ trợ kiểm thử flow để khởi chạy execution, đặt event trong external context và tiếp tục flow. API cụ thể cần khớp phiên bản thư viện mà dự án sử dụng.

Bảng dưới đây là ma trận kiểm thử tối thiểu cho ví dụ checkout:

| State hiện tại | Event | Transition được kỳ vọng | State đích |
|---|---|---|---|
| cart | continue | Local | shipping |
| cart | cancel | Global | cancelled |
| shipping | back | Local | cart |
| shipping | continue | Local | review |
| shipping | cancel | Global | cancelled |
| review | confirm | Local | saveOrder, sau đó completed |
| review | cancel | Local ghi đè global | confirmCancel |
| confirmCancel | keep | Local | review |
| confirmCancel | confirm | Local | cancelled |

Ngoài đường đi thành công, cần kiểm tra các trường hợp:

- Một event chỉ được khai báo cục bộ không thể vô tình được dùng ở state khác.
- Global transition hoạt động ở các state không có local transition cùng event.
- Local transition được ưu tiên khi cùng event có cả local và global transition.
- Khi không có transition phù hợp, ứng dụng ghi nhận được event và state liên quan để chẩn đoán.
- Action nằm trong transition được gọi đúng số lần và lỗi của action được xử lý theo thiết kế.
- Hủy ở từng state không bỏ sót thao tác hoàn tác hoặc giải phóng tài nguyên cần thiết.
- Subflow xử lý event của nó và flow cha xử lý đúng event kết thúc được trả về.

Không chỉ kiểm tra state cuối cùng. Nếu transition có side effect, hãy xác minh dữ liệu được lưu hoặc hoàn tác đúng, service không bị gọi lặp ngoài ý muốn và flow không để lại bản ghi tạm không còn được tham chiếu.

## 10. Lỗi thiết kế thường gặp

| Vấn đề | Hậu quả | Cách khắc phục |
|---|---|---|
| Đưa mọi event thành global | State có thể nhận event không phù hợp với nghiệp vụ | Chỉ dùng global cho hành vi thực sự dùng chung |
| Lặp cùng transition ở nhiều state | XML dài và các nhánh dễ lệch nhau khi sửa | Cân nhắc chuyển hành vi chung lên global-transitions |
| Không biết local ghi đè global | Thay đổi state làm đổi hành vi mà người sửa không nhận ra | Kiểm tra event trùng tên và ghi chú chủ đích ghi đè |
| Dùng tên event chung chung cho nghiệp vụ khác nhau | Khó hiểu event có ý nghĩa gì tại từng bước | Chọn tên event theo hành động nghiệp vụ cụ thể |
| Cho rằng global transition tự phát event | Flow chờ mãi vì không có thành phần gửi event | Kiểm tra view, request hoặc thành phần phát event |
| Dùng cancel để xử lý mọi exception | Lỗi hệ thống bị che khuất hoặc dữ liệu không được phục hồi đúng | Phân biệt event người dùng với exception và thiết kế nhánh lỗi riêng |
| Không kiểm thử state hiện tại | Test có thể đi qua nhánh khác với nhánh dự kiến | Xác minh state trước và sau mỗi event |
| Bỏ qua event của subflow | Flow cha và con có hợp đồng không nhất quán | Kiểm thử riêng flow con và transition nhận event kết thúc ở flow cha |

## 11. Quy trình quyết định phạm vi transition

Khi thêm một event mới, hãy làm theo trình tự:

1. Xác định state nào có thể phát event và ý nghĩa của event ở mỗi state.
2. Nếu event chỉ hợp lệ tại một state, khai báo local transition trong state đó.
3. Nếu event có cùng ý nghĩa và cùng cách xử lý ở nhiều state, cân nhắc khai báo global transition.
4. Kiểm tra xem có state nào cần hành vi đặc biệt; nếu có, khai báo local transition để xử lý riêng và xác nhận chủ đích ghi đè global.
5. Kiểm tra action, validation, cleanup và các điều kiện nghiệp vụ trước khi flow đi tới state đích.
6. Kiểm thử từng state có thể nhận event, bao gồm trường hợp local, global và không có transition phù hợp.
7. Nếu event liên quan subflow, xác định rõ flow nào phát event và flow nào xử lý event kết thúc.

Khi review một flow definition, người đọc nên có thể trả lời được ba câu hỏi: event nào được nhận tại state hiện tại, transition nào sẽ được chọn, và điều kiện nào phải đúng trước khi sang state đích. Nếu câu trả lời phụ thuộc vào nhiều global transition khó tìm hoặc action ẩn trong controller, cần làm rõ lại cách tổ chức.

## Kết luận

Transition cục bộ mô tả hành vi riêng của một state; global-transitions mô tả hành vi chung trong phạm vi một flow definition. Spring Web Flow ưu tiên transition cục bộ khi event khớp cả hai phạm vi, nhờ đó flow có thể định nghĩa một đường đi mặc định và vẫn cho phép state cụ thể ghi đè khi nghiệp vụ cần.

Hãy giữ local transition cho các bước phụ thuộc vào ngữ cảnh, dùng global transition cho event xuyên suốt có cùng ý nghĩa và kiểm thử rõ thứ tự ưu tiên. Khi kết hợp với service có trách nhiệm, quản lý scope phù hợp và xử lý lỗi riêng biệt, cách tổ chức này giúp hành trình nhiều bước dễ đọc, dễ kiểm thử và dễ phục hồi khi người dùng hoặc hệ thống cần rời khỏi luồng bình thường.
