# Dùng chung global transitions và xử lý ngoại lệ

Trong chương **Kế thừa định nghĩa**, Spring Web Flow cho phép tách các quy tắc dùng chung ra khỏi từng flow cụ thể. Hai cơ chế quan trọng là `global-transitions` và `exception-handler`. Global transition cung cấp một đường chuyển tiếp có thể dùng từ nhiều state; exception handler xử lý lỗi phát sinh trong quá trình thực thi flow. Khi đặt các quy tắc chung trong flow cha, nhiều flow con có thể kế thừa hành vi nhất quán mà không phải lặp lại cùng một cấu hình ở mọi state.

Module `SPRING_WEB_FLOW` hướng tới việc mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; thực hành form binding, validation, quản lý scope và phiên; tích hợp Spring MVC; kiểm thử và phục hồi luồng khi gặp lỗi. Trong phạm vi đó, kế thừa định nghĩa giúp dùng chung các hành vi điều hướng và chính sách lỗi giữa những hành trình có cấu trúc tương tự. Cần phân biệt rõ event nghiệp vụ với exception kỹ thuật, xác định phạm vi áp dụng của quy tắc chung và bảo đảm mỗi flow con vẫn có đường phục hồi phù hợp.

## 1. Vì sao cần global transition?

Một flow nhiều bước thường có các state như nhập thông tin, chọn phương án, xem lại và xác nhận. Một số event có thể xuất hiện ở nhiều state, ví dụ `cancel`, `help` hoặc `restart`. Nếu khai báo cùng một transition trong từng state, flow definition dài hơn và dễ không nhất quán: một state có thể quên xử lý event, một state khác lại chuyển tới đích khác.

`global-transitions` cho phép khai báo transition ở cấp flow. Transition đó có thể được dùng từ các state trong flow khi state hiện tại không có transition cục bộ phù hợp với event. Nhờ vậy, hành vi chung được mô tả một lần.

Ví dụ, mọi bước của một quy trình đăng ký đều có thể nhận event `cancel` để đi tới end state `cancelled`:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <global-transitions>
        <transition on="cancel" to="cancelled" />
    </global-transitions>

    <view-state id="enterDetails" view="registration/details">
        <transition on="continue" to="review" />
    </view-state>

    <view-state id="review" view="registration/review">
        <transition on="confirm" to="completed" />
    </view-state>

    <end-state id="cancelled" view="registration/cancelled" />
    <end-state id="completed" view="registration/completed" />
</flow>
```

Trong ví dụ, event `cancel` có một đích chung. Người dùng có thể hủy từ `enterDetails` hoặc `review` mà không cần lặp transition trong từng state. Các event `continue` và `confirm` vẫn được xử lý bởi transition riêng của state tương ứng.

Global transition là quy tắc điều hướng theo event. Nó không tự thực hiện việc hoàn tác dữ liệu, xóa bản nháp, thu hồi tài nguyên hay hủy một giao dịch đã commit. Nếu hủy cần nghiệp vụ bổ sung, hãy gọi service phù hợp trước khi kết thúc hoặc dùng một state xử lý hủy riêng.

## 2. Thứ tự ưu tiên giữa transition cục bộ và global transition

Khi một event được gửi đến state hiện tại, flow trước hết xét các transition gắn trực tiếp với state đó. Nếu có transition cục bộ khớp event và điều kiện của nó được thỏa mãn, flow dùng transition cục bộ. Global transition đóng vai trò đường dùng chung khi state hiện tại không cung cấp transition cục bộ phù hợp.

Ví dụ, hầu hết state dùng event `cancel` để kết thúc quy trình, nhưng state `payment` cần hỏi xác nhận trước khi rời bước thanh toán:

```xml
<global-transitions>
    <transition on="cancel" to="cancelled" />
</global-transitions>

<view-state id="payment" view="checkout/payment">
    <transition on="cancel" to="confirmCancellation" />
    <transition on="pay" to="processingPayment" />
</view-state>

<view-state id="confirmCancellation" view="checkout/confirm-cancel">
    <transition on="yes" to="cancelled" />
    <transition on="no" to="payment" />
</view-state>
```

Từ state `payment`, transition cục bộ `cancel` đưa người dùng tới màn hình xác nhận. Từ state khác không có transition `cancel` riêng, global transition sẽ đưa flow tới `cancelled`.

Không nên khai báo một transition cục bộ cùng event chỉ để lặp lại đích của global transition. Chỉ ghi đè ở state cần hành vi khác. Nếu có điều kiện guard, hãy kiểm tra cả trường hợp guard không thỏa mãn để chắc chắn flow rơi về global transition đúng như mong đợi. Quy tắc phân giải transition và biểu thức điều kiện nên được xác minh với phiên bản Spring Web Flow đang dùng.

## 3. Đưa global transition vào flow cha

Khi nhiều flow có cùng hành vi chung, có thể khai báo global transition trong flow định nghĩa cơ sở và cho flow con kế thừa. Flow cha thường chứa những thành phần dùng chung như end state hủy, transition toàn cục hoặc cấu hình xử lý ngoại lệ.

Ví dụ flow cha `base-checkout-flow.xml`:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      abstract="true">

    <global-transitions>
        <transition on="cancel" to="cancelled" />
    </global-transitions>

    <end-state id="cancelled" view="checkout/cancelled" />
</flow>
```

Flow con `standard-checkout-flow.xml` kế thừa định nghĩa cơ sở:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      parent="base-checkout">

    <view-state id="enterAddress" view="checkout/address">
        <transition on="next" to="chooseDelivery" />
    </view-state>

    <view-state id="chooseDelivery" view="checkout/delivery">
        <transition on="next" to="reviewOrder" />
    </view-state>

    <view-state id="reviewOrder" view="checkout/review">
        <transition on="confirm" to="completed" />
    </view-state>

    <end-state id="completed" view="checkout/completed" />
</flow>
```

Flow con kế thừa global transition `cancel` và end state `cancelled` từ flow cha. Các state và transition riêng mô tả hành trình checkout cụ thể. Nhờ đó, các flow con khác có thể tái sử dụng cùng chính sách hủy.

Đây là cấu trúc minh họa cho flow inheritance. Tên flow, cách tìm flow cha trong registry, schema và chi tiết merge phải phù hợp phiên bản Spring Web Flow của dự án. Flow cha dùng làm định nghĩa cơ sở thường được đánh dấu `abstract="true"` để không khởi chạy trực tiếp. Bảo đảm ID state, ID flow và đường dẫn registry không xung đột.

## 4. Global transition không thay thế hành động theo từng nhánh

Một transition toàn cục chỉ mô tả đường đi khi event xảy ra. Nếu mỗi flow cần thực hiện một hành động hủy khác nhau, hãy tách hành động đó thành một điểm mở rộng rõ ràng thay vì giả định global transition tự biết cách dọn dữ liệu.

Ví dụ, flow checkout có thể cần hủy reservation tạm trước khi kết thúc. Có thể chuyển event `cancel` tới một action-state dùng chung nếu hành động thực sự giống nhau:

```xml
<global-transitions>
    <transition on="cancel" to="cancelReservation" />
</global-transitions>

<action-state id="cancelReservation">
    <evaluate expression="reservationService.cancelDraft(reservation)" />
    <transition on="success" to="cancelled" />
    <transition on="alreadyCompleted" to="completed" />
    <transition on="error" to="cancelError" />
</action-state>
```

Nếu flow con không có đối tượng `reservation` hoặc có quy tắc hủy riêng, không nên ép tất cả flow dùng chung action-state này. Có thể dùng cùng event `cancel` nhưng chuyển tới state xử lý riêng trong từng flow, hoặc cung cấp service/extension point có hợp đồng rõ ràng. Mục tiêu của kế thừa là chia sẻ đúng phần giống nhau, không làm mất khác biệt nghiệp vụ.

Các thao tác có tác dụng phụ như hủy đơn, hoàn tiền hoặc thu hồi tài nguyên cần được bảo vệ trong service/domain layer bằng transaction, kiểm tra trạng thái và idempotency phù hợp. Người dùng có thể gửi lại event, refresh trang hoặc gặp timeout sau khi thao tác đã hoàn tất; global transition không bảo đảm side effect chỉ chạy một lần.

## 5. Event nghiệp vụ và exception là hai loại tín hiệu khác nhau

Global transition xử lý event mà flow nhận được, ví dụ `cancel`, `back`, `retry` hoặc `confirm`. Exception handler xử lý lỗi phát sinh khi flow đang thực thi, ví dụ action ném exception, lỗi repository hoặc một lỗi không mong đợi trong quá trình chuyển state.

| Tình huống | Cơ chế phù hợp | Ví dụ |
|---|---|---|
| Người dùng chọn hủy | Transition cục bộ hoặc global transition | Event `cancel` |
| Người dùng chọn thử lại | Transition theo event | Event `retry` |
| Service trả kết quả nghiệp vụ có thể dự đoán | Action result event và transition | `unavailable`, `alreadyCompleted` |
| Action ném exception | Exception handler hoặc cơ chế xử lý exception của ứng dụng | `FlowExecutionException` có cause là lỗi hạ tầng |
| Flow execution không còn tồn tại hoặc không khôi phục được | Cơ chế xử lý lỗi ở tầng execution/repository và ứng dụng web | Execution key hết hạn hoặc không hợp lệ |

Không nên ném exception để biểu diễn một kết quả nghiệp vụ bình thường như người dùng hủy hoặc dữ liệu chưa đủ. Hãy trả event có ý nghĩa và để flow chọn transition. Exception dành cho tình huống thực thi thất bại hoặc lỗi cần được xử lý theo chính sách lỗi.

## 6. Khai báo exception handler cho flow

Spring Web Flow cho phép đăng ký một bean triển khai `FlowExecutionExceptionHandler` để xử lý exception xảy ra trong quá trình thực thi flow. Flow definition có thể tham chiếu bean handler:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <exception-handler bean="checkoutFlowExceptionHandler" />

    <view-state id="review" view="checkout/review">
        <transition on="confirm" to="completeOrder" />
    </view-state>

    <action-state id="completeOrder">
        <evaluate expression="orderService.complete(order)" />
        <transition on="success" to="completed" />
    </action-state>

    <end-state id="completed" view="checkout/completed" />
</flow>
```

Bean `checkoutFlowExceptionHandler` chịu trách nhiệm phân loại exception và quyết định lỗi nào có thể được xử lý trong flow, lỗi nào phải được truyền tiếp cho cơ chế xử lý cấp cao hơn. Hợp đồng của handler là API `FlowExecutionExceptionHandler`; chữ ký phương thức và cách chuyển execution sang trạng thái lỗi cần đối chiếu phiên bản Spring Web Flow.

Một handler nên làm những việc sau:

1. Xác định exception gốc và phân loại theo loại lỗi, không chỉ dựa vào thông điệp văn bản.
2. Chỉ xử lý các loại lỗi đã được dự kiến và có đường phục hồi rõ ràng.
3. Ghi log với flow ID, state ID và correlation ID cần thiết, không ghi dữ liệu nhạy cảm.
4. Đưa thông tin lỗi an toàn vào ngữ cảnh để hiển thị thông báo phù hợp.
5. Chuyển tới state lỗi hoặc phục hồi phù hợp khi execution còn ở trạng thái có thể tiếp tục.
6. Trả quyền xử lý lại cho cơ chế mặc định nếu exception không thuộc phạm vi handler.

Không nên bắt mọi exception rồi chuyển flow tới trang thành công hoặc bỏ qua lỗi. Điều đó che giấu trạng thái không nhất quán và có thể khiến người dùng tưởng rằng nghiệp vụ đã hoàn tất.

## 7. Phân loại exception và chọn chiến lược phục hồi

Không phải lỗi nào cũng nên được xử lý giống nhau. Một số lỗi là kết quả nghiệp vụ có thể dự đoán; một số lỗi là sự cố tạm thời; một số khác cho thấy flow không thể tiếp tục an toàn.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi nghiệp vụ dự kiến | Reservation đã bị hủy hoặc không còn hiệu lực | Ưu tiên trả event nghiệp vụ và chuyển tới state thông báo phù hợp |
| Lỗi tạm thời | Dịch vụ giá hoặc hệ thống ngoài timeout | Retry có giới hạn nếu thao tác an toàn; nếu không, hiển thị trạng thái chờ hoặc lỗi có thể thử lại |
| Lỗi dữ liệu | Không tìm thấy bản ghi hoặc dữ liệu không nhất quán | Tải lại dữ liệu đáng tin cậy, báo lỗi và yêu cầu người dùng bắt đầu lại khi cần |
| Lỗi bảo mật | Người dùng không có quyền truy cập tài nguyên | Từ chối thao tác, ghi nhận sự kiện bảo mật và không tiết lộ dữ liệu |
| Lỗi lập trình hoặc lỗi không dự kiến | Null pointer, cấu hình sai, invariant bị vi phạm | Ghi nhận đầy đủ ở log bảo vệ, truyền tới cơ chế lỗi cấp cao hơn và không giả thành công |
| Execution/repository failure | Flow hết hạn hoặc không khôi phục được execution | Xử lý ở tầng flow executor/repository hoặc web exception mapping phù hợp |

Với lỗi tạm thời, chỉ retry khi biết thao tác có thể chạy lặp an toàn. Nếu một request timeout sau khi gửi lệnh thanh toán, hệ thống ngoài có thể đã xử lý lệnh. Gửi lại ngay có thể tạo thanh toán trùng. Dùng idempotency key, truy vấn trạng thái hoặc cơ chế đối soát trước khi thử lại.

## 8. Tổ chức state lỗi và đường phục hồi

Một flow có thể khai báo state dành cho lỗi có thể khôi phục, ví dụ `serviceUnavailable`, `dataConflict` hoặc `restartRequired`. State này giúp thông báo cho người dùng và đưa ra hành động tiếp theo phù hợp.

```xml
<view-state id="serviceUnavailable" view="common/service-unavailable">
    <transition on="retry" to="retryOperation" />
    <transition on="restart" to="restartFlow" />
</view-state>

<action-state id="retryOperation">
    <evaluate expression="checkoutService.retryPendingOperation(order)" />
    <transition on="success" to="completed" />
    <transition on="unavailable" to="serviceUnavailable" />
    <transition on="permanentFailure" to="supportRequired" />
</action-state>
```

Ví dụ trên minh họa đường phục hồi có event rõ ràng. `retryPendingOperation` phải kiểm tra trạng thái hiện tại và tính idempotent trước khi thực hiện lại. Nếu lỗi không thể phục hồi, flow nên đưa người dùng tới state giải thích cách tiếp tục hoặc kết thúc an toàn.

Không phải mọi exception đều có thể chuyển về state lỗi của flow. Nếu execution đã hỏng, session hết hạn hoặc repository không thể khôi phục trạng thái, handler trong flow có thể không còn đủ ngữ cảnh để tiếp tục. Những trường hợp này cần được xử lý ở tầng tích hợp web/execution repository, ví dụ hiển thị thông báo flow hết hạn và hướng dẫn bắt đầu hành trình mới.

## 9. Kết hợp global transitions và exception handler trong flow cha

Flow cha có thể cung cấp các quy tắc dùng chung cho các flow con: event hủy, end state chung, state thông báo lỗi hoặc exception handler áp dụng cho những lỗi phổ biến. Flow con bổ sung transition riêng cho nghiệp vụ của nó.

Một cấu trúc khái quát:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      abstract="true">

    <global-transitions>
        <transition on="cancel" to="cancelled" />
    </global-transitions>

    <exception-handler bean="commonFlowExceptionHandler" />

    <end-state id="cancelled" view="common/cancelled" />
</flow>
```

Flow con có thể khai báo transition cục bộ cho event `cancel` nếu cần hỏi xác nhận, hoặc dùng global transition khi hành vi chung đã đủ. Handler dùng chung nên chỉ xử lý các exception có cùng ý nghĩa và cùng chính sách phục hồi. Lỗi đặc thù của một flow có thể cần handler hoặc service chuyên biệt.

Khi dùng kế thừa, hãy xác minh cấu hình sau merge: global transition nào được kế thừa, state đích có tồn tại trong flow con sau khi hợp nhất hay không, handler nào thực sự được đăng ký và child flow có thay thế hoặc bổ sung cấu hình của parent theo quy tắc phiên bản hay không. Tránh dựa vào giả định về thứ tự merge khi có định nghĩa trùng ID.

## 10. Những lưu ý về phạm vi và thứ tự trong kế thừa

Global transition ở flow cha có thể giúp các flow con dùng chung event, nhưng không nên biến flow cha thành nơi tập trung mọi quy tắc nghiệp vụ.

- Đặt global transition cho event thực sự có ý nghĩa chung trong tất cả flow con.
- Đảm bảo state đích của transition được kế thừa hoặc được định nghĩa trong flow đã hợp nhất.
- Dùng transition cục bộ khi một state cần hành vi khác; kiểm tra rõ thứ tự ưu tiên.
- Không dùng event chung như `error` để biểu diễn mọi exception nếu mỗi lỗi cần chính sách khác nhau.
- Giữ handler chung tập trung vào phân loại và định tuyến lỗi; không nhồi toàn bộ xử lý nghiệp vụ vào handler.
- Tránh để handler phụ thuộc vào một biến chỉ tồn tại trong một flow con.
- Không để flow cha phụ thuộc vào view hoặc model đặc thù của một child flow.
- Khi thay đổi ID event, state hoặc bean handler trong flow cha, kiểm tra toàn bộ flow con phụ thuộc qua integration test.

Một global transition quá rộng có thể khiến event được nhận ở state mà người thiết kế không dự định. Vì vậy, hãy chọn tên event cụ thể, ghi rõ ý nghĩa của nó và kiểm thử từ từng nhóm state quan trọng.

## 11. Kiểm thử global transition và exception handling

Kiểm thử cần xác minh hành vi dùng chung thực sự hoạt động sau khi flow definition được kế thừa, đồng thời bảo đảm flow con vẫn có thể tùy biến ở nơi cần thiết.

| Kịch bản | Điều cần xác minh |
|---|---|
| Gửi event có global transition từ state A | Flow chuyển tới state đích chung |
| Gửi cùng event từ state B | Hành vi chung được áp dụng nếu state không có transition cục bộ |
| State có transition cục bộ cùng event | Transition cục bộ được ưu tiên theo cấu hình |
| Guard của transition cục bộ không thỏa mãn | Global fallback hoạt động đúng theo quy tắc phân giải đã cấu hình |
| Flow con kế thừa flow cha | Global transition và end state chung có mặt trong flow đã hợp nhất |
| Child flow có hành vi riêng | Transition hoặc handler đặc thù được dùng đúng phạm vi |
| Action ném exception đã biết | Handler phân loại và đưa execution tới đường lỗi phù hợp |
| Action ném exception không biết | Lỗi được truyền tới cơ chế cấp cao hơn; không giả thành công |
| Exception xảy ra khi repository/session lỗi | Tầng tích hợp xử lý execution không thể khôi phục |
| Retry sau timeout | Không tạo side effect trùng; trạng thái được đối soát |

Spring Web Flow có test support để khởi chạy flow, gửi event và kiểm tra state hiện tại. API cụ thể phụ thuộc phiên bản. Nên kiểm thử flow cha và từng flow con qua registry thực tế để xác minh inheritance/merge, không chỉ unit test một action riêng lẻ.

Với exception handler, dùng test để đưa exception đại diện vào action/service, xác minh handler nhận đúng loại lỗi và kiểm tra kết quả cuối. Bao gồm cả trường hợp handler không nhận diện exception để chắc chắn lỗi không bị nuốt. Các lời gọi kiểm thử có thể dùng mock service ném exception hoặc trả event lỗi có chủ đích.

## 12. Lỗi thiết kế thường gặp

### Dùng global transition cho hành vi không thật sự chung

Một event `cancel` được dùng ở mọi state nhưng một số bước đã phát sinh nghiệp vụ không thể hủy. Nếu global transition kết thúc flow ngay, người dùng có thể bỏ qua bước đối soát hoặc thu hồi tài nguyên. Hãy dùng transition cục bộ ở state cần xử lý riêng và chỉ dùng global fallback khi an toàn.

### Cho rằng global transition tự rollback

Chuyển tới end state không hoàn tác database transaction hoặc side effect đã thực hiện. Cần gọi service hủy/compensate có kiểm soát, xác định trạng thái nghiệp vụ và hỗ trợ idempotency.

### Dùng exception cho kết quả bình thường

Người dùng chọn Cancel hoặc một điều kiện nghiệp vụ không đạt không nhất thiết là exception. Hãy dùng event có tên rõ để flow điều hướng dễ hiểu và tránh log lỗi giả.

### Bắt mọi exception rồi tiếp tục

Nuốt lỗi có thể khiến flow hiển thị thành công trong khi dữ liệu chưa được lưu. Chỉ xử lý exception đã biết và có đường phục hồi; lỗi còn lại phải được truyền tới cơ chế phù hợp.

### Chuyển mọi lỗi tới cùng một state

Lỗi dữ liệu, lỗi bảo mật và lỗi hạ tầng cần cách phản hồi khác nhau. Phân loại theo exception type/cause và chính sách nghiệp vụ; không tiết lộ chi tiết kỹ thuật cho người dùng.

### Giả định flow handler xử lý được execution đã mất

Nếu repository không thể khôi phục execution hoặc session đã hết hạn, flow có thể không còn context để chạy handler. Cần xử lý các lỗi vòng đời execution ở tầng web/repository và hướng dẫn người dùng bắt đầu lại an toàn.

## 13. Checklist trước khi chia sẻ global transition hoặc exception handler

Trước khi đưa quy tắc vào flow cha, hãy trả lời:

1. Event này có ý nghĩa và hành vi giống nhau trong mọi flow con không?
2. State đích của global transition tồn tại trong flow sau khi kế thừa không?
3. State nào cần transition cục bộ ghi đè, và hành vi đó có được kiểm thử không?
4. Event có cần action hủy hoặc bù trừ nghiệp vụ trước khi kết thúc không?
5. Exception nào được handler chung xử lý? Exception nào phải truyền tiếp?
6. Handler có phụ thuộc vào biến, view hoặc service chỉ tồn tại trong một child flow không?
7. Lỗi có thể phục hồi bằng retry không, và thao tác có idempotent không?
8. Execution hết hạn hoặc repository lỗi được xử lý ở tầng nào?
9. Integration test đã nạp flow cha và các flow con qua registry để kiểm tra cấu hình merge chưa?

## Kết luận

`global-transitions` định nghĩa các đường chuyển tiếp dùng chung cho nhiều state trong một flow; flow con có thể kế thừa các quy tắc đó từ flow cha để tránh lặp cấu hình. Transition cục bộ vẫn là nơi diễn tả hành vi riêng của một state và được ưu tiên khi khớp event. `exception-handler` xử lý lỗi phát sinh trong quá trình thực thi flow, với nhiệm vụ phân loại exception và chọn đường phục hồi an toàn.

Hãy dùng global transition cho event thực sự dùng chung, exception handler cho lỗi thực thi đã được phân loại và service/domain layer cho nghiệp vụ có tác dụng phụ. Kiểm thử từng state quan trọng, cấu hình flow sau khi kế thừa, cả exception đã biết lẫn chưa biết và tình huống execution hết hạn. Cách tổ chức này giúp nhiều hành trình Spring Web Flow có hành vi nhất quán mà vẫn giữ được khả năng xử lý riêng và phục hồi khi lỗi xảy ra.
